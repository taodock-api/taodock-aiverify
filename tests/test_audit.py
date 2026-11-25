import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from algorithms.catalog_copy_audit.taodock_catalog_copy_audit import cli
from algorithms.catalog_copy_audit.taodock_catalog_copy_audit.audit import (
    audit_rows,
    read_csv,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "catalog.csv"


class CatalogAuditTest(unittest.TestCase):
    def test_sample_findings(self):
        result = audit_rows(read_csv(SAMPLE))
        self.assertEqual(
            (result["total"], result["passed"], result["flagged"]), (15, 8, 7)
        )
        findings = {
            finding["sku"]: [issue["kind"] for issue in finding["issues"]]
            for finding in result["findings"]
        }
        self.assertEqual(
            findings,
            {
                "SG-007": ["missing_measurement"],
                "SG-008": ["missing_measurement"],
                "SG-009": ["missing_measurement", "unlisted_measurement"],
                "SG-010": ["unlisted_measurement"],
                "SG-011": ["missing_phrase"],
                "SG-014": ["missing_phrase"],
                "SG-015": ["empty_draft"],
            },
        )

    def test_conversions_and_unicode_whitespace(self):
        row = {
            "sku": "99",
            "measurements": "1.25 L|0.2 kg|0.5 hr|1 kW",
            "required_phrases": "navy blue",
            "draft": "Navy　Blue. １,２５０ ml, 200 g, 30 min, 1000 W.",
        }
        self.assertEqual(audit_rows([row])["passed"], 1)

    def test_phrases_use_boundaries_and_model_ids_are_not_measurements(self):
        row = {
            "sku": "1",
            "measurements": "",
            "required_phrases": "red",
            "draft": "Hundred series ABC-300W and 1,5 L and 1/2 L",
        }
        self.assertEqual(
            audit_rows([row])["findings"][0]["issues"],
            [
                {"kind": "missing_phrase", "value": "red"},
            ],
        )

    def test_rejects_empty_duplicate_and_invalid_measurement(self):
        row = {
            "sku": "SKU-1",
            "measurements": "10 ml",
            "required_phrases": "",
            "draft": "10 ml",
        }
        with self.assertRaisesRegex(ValueError, "at least one SKU"):
            audit_rows([])
        with self.assertRaisesRegex(ValueError, "duplicate SKU"):
            audit_rows([row, {**row, "sku": " sku-1 "}])
        with self.assertRaisesRegex(ValueError, "supported number and unit"):
            audit_rows([{**row, "measurements": "1,5 ml"}])

    def test_rejects_extra_or_missing_csv_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "input.csv"
            for row in ("X,1 L,,1 L,extra", "X,1 L"):
                invalid.write_text(
                    "sku,measurements,required_phrases,draft\n" + row, encoding="utf-8"
                )
                with (
                    self.subTest(row=row),
                    self.assertRaisesRegex(ValueError, "four text values"),
                ):
                    audit_rows(read_csv(invalid))

    def test_result_archive_works_offline_and_omits_full_drafts(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(cli, "request_taodock") as request,
        ):
            path = Path(directory) / "result.zip"
            totals = cli.score(SAMPLE, path)
            with ZipFile(path) as archive:
                self.assertEqual(archive.namelist(), ["results.json"])
                result = json.loads(archive.read("results.json"))
            request.assert_not_called()
            self.assertEqual(result["output"], totals)
            self.assertEqual(result["testArguments"]["testDataset"], SAMPLE.name)
            self.assertEqual(result["testArguments"]["groundTruthDataset"], SAMPLE.name)
            self.assertEqual(result["testArguments"]["groundTruth"], "measurements")
            self.assertNotIn("Navy blue stainless steel bottle", json.dumps(result))


class DraftGenerationTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        scratch = directory.name
        self.source = Path(scratch) / "input.csv"
        self.target = Path(scratch) / "drafts.csv"
        self.source.write_text(
            "sku,measurements,required_phrases,draft\n"
            "TEST-1,500 ml,navy blue,Existing draft retained in source\n",
            encoding="utf-8",
        )
        environment = patch.dict(
            "os.environ", {"TAODOCK_API_KEY": "synthetic-unit-test-key"}
        )
        environment.start()
        self.addCleanup(environment.stop)

    def test_generation_only_sends_rules(self):
        with patch.object(
            cli,
            "request_taodock",
            side_effect=[
                {"data": [{"id": "fixture"}]},
                {
                    "choices": [
                        {
                            "message": {
                                "content": "Navy blue bottle with a 500 mL capacity."
                            }
                        }
                    ]
                },
            ],
        ) as request:
            cli.generate(self.source, self.target, "fixture")
        self.assertEqual(
            [call.args[0] for call in request.call_args_list],
            ["models", "chat/completions"],
        )
        body = request.call_args.args[2]
        self.assertEqual(body["model"], "fixture")
        self.assertEqual(
            json.loads(body["messages"][1]["content"]),
            {
                "measurements": ["500 ml"],
                "required_phrases": ["navy blue"],
            },
        )
        self.assertEqual(audit_rows(read_csv(self.target))["passed"], 1)
        self.assertIn("Existing draft", self.source.read_text(encoding="utf-8"))

    def test_nonexistent_model_skips_generation_and_output(self):
        with patch.object(cli, "request_taodock", return_value={"data": []}) as request:
            with self.assertRaisesRegex(ValueError, "exact model ID"):
                cli.generate(self.source, self.target, "fixture")
            request.assert_called_once()
        self.assertFalse(self.target.exists())

    def test_failed_generation_preserves_previous_output(self):
        self.target.write_text("previous", encoding="utf-8")
        with (
            patch.object(
                cli,
                "request_taodock",
                side_effect=[
                    {"data": [{"id": "fixture"}]},
                    {"choices": []},
                ],
            ),
            self.assertRaisesRegex(ValueError, "no usable draft"),
        ):
            cli.generate(self.source, self.target, "fixture")
        self.assertEqual(self.target.read_text(encoding="utf-8"), "previous")

    def test_request_builds_official_openai_endpoint_and_bearer_header(self):
        with patch.object(cli, "build_opener") as factory:
            factory.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"data":[]}'
            self.assertEqual(cli.request_taodock("models", "fixture-key"), {"data": []})
            request = factory.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://taodock.com/v1/models")
        self.assertEqual(request.get_header("Authorization"), "Bearer fixture-key")
        self.assertEqual(request.get_method(), "GET")
        self.assertIsInstance(factory.call_args.args[0], cli.NoRedirect)


if __name__ == "__main__":
    unittest.main()

"""Produce AI Verify result archives locally, or generate drafts via Taodock."""

import argparse
import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import ZIP_DEFLATED, ZipFile

from .audit import MAX_ROWS, audit_rows, read_csv, split_rules

BASE_URL = "https://taodock.com/v1"
META = Path(__file__).with_name("algo.meta.json")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_taodock(endpoint, key, body=None):
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = Request(f"{BASE_URL}/{endpoint}", data=data, headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=45) as response:
            payload = response.read(4_000_001)
            if len(payload) > 4_000_000:
                raise ValueError("Response exceeded size limit")
            return json.loads(payload)
    except HTTPError as error:
        raise ValueError(f"Taodock {endpoint} returned HTTP {error.code}") from None
    except (URLError, TimeoutError, ValueError):
        raise ValueError(
            f"Taodock {endpoint} could not return a usable JSON response"
        ) from None


def generate_draft(row, number, model, key):
    specification = {
        "measurements": split_rules(row["measurements"], number),
        "required_phrases": split_rules(row["required_phrases"], number),
    }
    response = request_taodock(
        "chat/completions",
        key,
        {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Write one short English product listing from the provided specification. "
                        "Preserve its measurements and required phrases. Add no unlisted measurements "
                        "or product claims. Respond only with the listing copy."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(specification, ensure_ascii=False),
                },
            ],
        },
    )
    try:
        draft = response["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        raise ValueError(f"Row {number}: Taodock returned no usable draft") from None
    if not draft or len(draft) > 4000:
        raise ValueError(f"Row {number}: Taodock returned an empty or oversized draft")
    return draft


def generate(source, target, model):
    key = os.environ.get("TAODOCK_API_KEY", "").strip()
    if not key:
        raise ValueError("Set TAODOCK_API_KEY before generating drafts")
    rows = list(islice(read_csv(source), MAX_ROWS + 1))
    audit_rows(rows)
    catalog = request_taodock("models", key)
    if not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
        raise ValueError("Taodock returned an invalid model list")  # noqa: TRY004
    if not any(
        isinstance(item, dict) and item.get("id") == model for item in catalog["data"]
    ):
        raise ValueError(
            "Choose an exact model ID available to this key in Taodock's model list"
        )
    for number, row in enumerate(rows, start=2):
        row["draft"] = generate_draft(row, number, model, key)
    audit_rows(rows)

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=target.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            writer = csv.DictWriter(
                stream, fieldnames=["sku", "measurements", "required_phrases", "draft"]
            )
            writer.writeheader()
            writer.writerows(rows)
            stream.close()
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


def score(source, target):
    started = datetime.now(timezone.utc)
    timer = monotonic()
    results = audit_rows(read_csv(source))
    meta = json.loads(META.read_text(encoding="utf-8"))
    envelope = {
        "gid": meta["gid"],
        "cid": meta["cid"],
        "version": meta["version"],
        "startTime": started.isoformat(),
        "timeTaken": round(monotonic() - timer, 6),
        "testArguments": {
            "testDataset": source.name,
            "mode": "upload",
            "modelType": "classification",
            "modelFile": "Taodock catalog copy - pre-generated drafts.txt",
            "algorithmArgs": {},
        },
        "output": results,
    }
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr(
                    "results.json", json.dumps(envelope, ensure_ascii=False)
                )
            stream.close()
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    score_parser = commands.add_parser(
        "score", help="Audit drafts offline and write a Toolkit result ZIP"
    )
    score_parser.add_argument("csv", type=Path)
    score_parser.add_argument("result_zip", type=Path)
    generate_parser = commands.add_parser(
        "generate", help="Generate new drafts with the Taodock API"
    )
    generate_parser.add_argument("csv", type=Path)
    generate_parser.add_argument("draft_csv", type=Path)
    generate_parser.add_argument(
        "--model", required=True, help="Exact Chat Completions model ID"
    )
    args = parser.parse_args()
    target = args.result_zip if args.action == "score" else args.draft_csv
    suffix = ".zip" if args.action == "score" else ".csv"
    if target.suffix != suffix or target.resolve() == args.csv.resolve():
        parser.error(f"Choose a separate output path ending in {suffix}")
    try:
        if args.action == "score":
            result = score(args.csv, target)
            print(
                f"{result['total']} checked, {result['passed']} passed, {result['flagged']} flagged"
            )
        else:
            generate(args.csv, target, args.model)
            print("Draft CSV written")
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(1, f"Error: {error}\n")

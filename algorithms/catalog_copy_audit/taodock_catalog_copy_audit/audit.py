"""Compare product-copy drafts against explicit, SKU-level specification rules."""

import csv
import re
import unicodedata
from decimal import Decimal

COLUMNS = {"sku", "measurements", "required_phrases", "draft"}
MAX_ROWS = 500
UNITS = {
    "mm": ("length", "1"),
    "cm": ("length", "10"),
    "m": ("length", "1000"),
    "g": ("weight", "1"),
    "kg": ("weight", "1000"),
    "ml": ("volume", "1"),
    "l": ("volume", "1000"),
    "w": ("power", "1"),
    "kw": ("power", "1000"),
    "hour": ("duration", "60"),
    "hours": ("duration", "60"),
    "hr": ("duration", "60"),
    "hrs": ("duration", "60"),
    "minute": ("duration", "1"),
    "minutes": ("duration", "1"),
    "min": ("duration", "1"),
    "mins": ("duration", "1"),
    "piece": ("count", "1"),
    "pieces": ("count", "1"),
    "pc": ("count", "1"),
    "pcs": ("count", "1"),
    "%": ("percentage", "1"),
}
UNIT_PATTERN = "|".join(sorted(UNITS, key=len, reverse=True))
NUMBER_PATTERN = r"[+\-−]?(?:[0-9]{1,3}(?:,[0-9]{3}){1,3}|[0-9]{1,12})(?:\.[0-9]{1,9})?"
MEASUREMENT = re.compile(
    rf"(?<![\w.,/+\-−])(?P<number>{NUMBER_PATTERN})\s*(?P<unit>{UNIT_PATTERN})(?![\w%])"
)


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def measurement_key(match):
    unit, scale = UNITS[match["unit"]]
    value = Decimal(match["number"].replace(",", "").replace("−", "-"))
    return unit, value * Decimal(scale)


def split_rules(text, row_number):
    values = [value.strip() for value in text.split("|")] if text.strip() else []
    if len(values) > 20 or any(not value or len(value) > 100 for value in values):
        raise ValueError(
            f"Row {row_number}: use up to 20 nonempty rules of 100 characters each per column"
        )
    return values


def audit_row(row, row_number):
    sku = row["sku"].strip()
    if not sku or len(sku) > 80:
        raise ValueError(f"Row {row_number}: SKU must contain 1–80 characters")
    expected = {}
    for text in split_rules(row["measurements"], row_number):
        match = MEASUREMENT.fullmatch(normalize(text))
        if match is None:
            raise ValueError(
                f"Row {row_number}: use a supported number and unit for each measurement"
            )
        expected.setdefault(measurement_key(match), text)

    phrases = split_rules(row["required_phrases"], row_number)
    if not expected and not phrases:
        raise ValueError(
            f"Row {row_number}: enter at least one measurement or required phrase"
        )
    if len(row["draft"]) > 4000:
        raise ValueError(f"Row {row_number}: drafts may contain up to 4,000 characters")
    draft = normalize(row["draft"])
    if not draft:
        return sku, [{"kind": "empty_draft", "value": ""}]

    observed = {}
    for match in MEASUREMENT.finditer(draft):
        observed.setdefault(measurement_key(match), match[0][:100])
    if len(observed) > 100:
        raise ValueError(
            f"Row {row_number}: drafts may contain up to 100 distinct measurements"
        )

    issues = [
        {"kind": "missing_measurement", "value": text}
        for key, text in expected.items()
        if key not in observed
    ]
    issues.extend(
        {"kind": "unlisted_measurement", "value": text}
        for key, text in observed.items()
        if key not in expected
    )
    for phrase in dict.fromkeys(normalize(phrase) for phrase in phrases):
        if not re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", draft):
            issues.append({"kind": "missing_phrase", "value": phrase[:100]})
    return sku, issues


def audit_rows(rows):
    seen = set()
    findings = []
    for number, row in enumerate(rows, start=2):
        if len(seen) == MAX_ROWS:
            raise ValueError(f"Enter at most {MAX_ROWS} rows per audit")
        if row.keys() != COLUMNS or any(
            not isinstance(value, str) for value in row.values()
        ):
            raise ValueError(
                f"Row {number}: expected four text values matching the CSV column names"
            )
        sku, issues = audit_row(row, number)
        key = normalize(sku)
        if key in seen:
            raise ValueError(f"Row {number}: duplicate SKU")
        seen.add(key)
        if issues:
            findings.append({"sku": sku, "issues": issues})
    if not seen:
        raise ValueError("Enter at least one SKU row")
    return {
        "total": len(seen),
        "passed": len(seen) - len(findings),
        "flagged": len(findings),
        "findings": findings,
    }


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        columns = reader.fieldnames or []
        if len(columns) != len(COLUMNS) or set(columns) != COLUMNS:
            raise ValueError(
                "CSV requires exactly these headers: sku, measurements, required_phrases, draft"
            )
        yield from reader

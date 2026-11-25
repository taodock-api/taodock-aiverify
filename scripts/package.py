"""Build a reproducible AI Verify installation archive."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "LICENSE",
    "README.md",
    "audit_catalog.py",
    "examples/catalog.csv",
    "plugin.meta.json",
    "algorithms/catalog_copy_audit/pyproject.toml",
    *(
        f"algorithms/catalog_copy_audit/taodock_catalog_copy_audit/{name}"
        for name in (
            "__init__.py",
            "algo.meta.json",
            "algo.py",
            "algo_init.py",
            "audit.py",
            "cli.py",
            "input.schema.json",
            "output.schema.json",
        )
    ),
    "widgets/catalog_copy_findings.mdx",
    "widgets/catalog_copy_findings.meta.json",
]


def main():
    meta = json.loads((ROOT / "plugin.meta.json").read_text(encoding="utf-8"))
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    target = dist / f"{meta['gid']}-{meta['version']}.zip"
    with ZipFile(target, "w") as archive:
        for relative in sorted(FILES):
            file = ZipInfo(relative)
            file.external_attr = 0o100644 << 16
            archive.writestr(
                file,
                (ROOT / relative).read_bytes(),
                compress_type=ZIP_DEFLATED,
                compresslevel=9,
            )
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (dist / "SHA256SUMS").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()

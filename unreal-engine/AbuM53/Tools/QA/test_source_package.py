#!/usr/bin/env python3
"""Regression: owned temporary fixture ZIP -> unpack -> audit -> identical repack."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from audit_source import audit, REQUIRED_FILES
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Provenance'))
import provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, help="Parent directory for isolated temporary test files")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.work:
        args.work.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(prefix="m53-package-test-", dir=args.work) as temporary:
        base = Path(temporary).resolve()
        source = base / "fixture-source"
        for name in REQUIRED_FILES:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            # These are deliberately tiny test stubs, never a distributable plugin.
            text = "{}\n" if path.suffix == ".json" else "Original package-mechanics test stub only.\n"
            path.write_text(text, encoding="utf-8")
        (source / 'VERSION').write_text('v0.0.0.4\n', encoding='utf-8')
        (source / provenance.DOCUMENT).write_text(
            provenance.START + '\n\n' + provenance.END + '\n\n- **v0.0.0.4** — original mechanics fixture\n', encoding='utf-8')
        ledger = {'schema': 1, 'scope': list(provenance.SCOPE),
                  'origins': {'fixture': {'name': 'Owned mechanics stubs', 'license': 'Apache-2.0', 'source': 'This test'}},
                  'files': {path: {'origins': ['fixture']} for path in provenance.implementation(source)}}
        (source / provenance.RECORD).write_text(json.dumps(ledger), encoding='utf-8')
        provenance.refresh(source, 'original test fixture', '2026-10-26')
        first, second, third = (base / name for name in ("first.zip", "second.zip", "third.zip"))

        def package(root, output):
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("package_source.py")),
                                     "--root", str(root), "--output", str(output)], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)

        package(source, first)
        extracted = base / "extracted"
        with zipfile.ZipFile(first) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names)), "Duplicate archive entries"
            assert names.count("AbuM53/ARTIFACT_MANIFEST.json") == 1
            assert all(name.startswith("AbuM53/") and ".." not in Path(name).parts for name in names)
            archive.extractall(extracted)
        checks.append("one generated manifest and unique safe archive names")
        unpacked = extracted / "AbuM53"
        result = audit(unpacked)
        assert result["passed"], result["violations"]
        assert all(item["path"] != "ARTIFACT_MANIFEST.json" for item in result["files"])
        checks.append("unpacked source audit passes and excludes generated manifest")
        package(unpacked, second)
        assert first.read_bytes() == second.read_bytes(), "Repacked ZIP differs"
        checks.append("unpack and repack produces byte-identical ZIP")
        (unpacked / "ARTIFACT_MANIFEST.json").write_text("stale generated metadata", encoding="utf-8")
        package(unpacked, third)
        assert first.read_bytes() == third.read_bytes(), "Stale input manifest affected new archive"
        checks.append("stale generated manifest is ignored and replaced")
        fixture_hash = hashlib.sha256(first.read_bytes()).hexdigest()
    report = {"schema": 1, "passed": True, "checks": checks, "temporary_fixture_zip_sha256": fixture_hash,
              "scope": "Packaging mechanics on original temporary test stubs; not final plugin archive or legal clearance."}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

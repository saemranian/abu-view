#!/usr/bin/env python3
"""Create a reproducible source-only ZIP from the audited allowlist."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

from audit_source import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    if output == root or root in output.parents:
        parser.error("write the archive outside the source root")
    result = audit(root)
    if not result["passed"]:
        raise SystemExit("Source audit failed: " + "; ".join(result["violations"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".partial", dir=output.parent, delete=False) as temp_file:
        temporary = Path(temp_file.name)
    manifest = {key: value for key, value in result.items() if key != "root"}
    manifest["package"] = "AbuM53 source"
    manifest["contains_engine_or_plugin_binaries"] = False
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for item in result["files"]:
                source_path = root / item["path"]
                if source_path.resolve() != source_path:
                    raise RuntimeError("Source became a link during packaging: " + item["path"])
                data = source_path.read_bytes()
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    raise RuntimeError("Source changed during packaging: " + item["path"])
                entry = zipfile.ZipInfo("AbuM53/" + item["path"], date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, data)
            entry = zipfile.ZipInfo("AbuM53/ARTIFACT_MANIFEST.json", date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, json.dumps(manifest, indent=2) + "\n")
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(json.dumps({"path": str(output), "bytes": output.stat().st_size,
                      "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                      "source_files": result["file_count"],
                      "legal_clearance": "Not implied; see Docs/Legal."}, indent=2))


if __name__ == "__main__":
    main()

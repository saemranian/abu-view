#!/usr/bin/env python3
"""Audit a source release without redistributing build products or user assets."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

IGNORED_PARTS = {".git", ".vs", "Binaries", "Intermediate", "Saved", "build", "Build", "__pycache__"}
GENERATED_ROOT_FILES = {"ARTIFACT_MANIFEST.json"}
FORBIDDEN_SUFFIXES = {".dll", ".exe", ".pdb", ".lib", ".obj", ".a", ".so", ".dylib", ".pak", ".ucas", ".utoc", ".uasset", ".umap", ".pth", ".pt", ".ckpt", ".pem", ".key"}
ALLOWED_ROOT_FILES = {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "README.md", ".gitignore", ".gitattributes", "AbuM53.uplugin", "VERSION", "CHANGELOG.md", "AGENTS.md", "GEMINI.md"}
ALLOWED_ROOT_DIRS = {"Core", "Source", "Shaders", "Resources", "Config", "Tests", "Tools", "Docs", "ThirdParty", ".github"}
SOURCE_SUFFIXES = {".h", ".hpp", ".cpp", ".c", ".cs", ".usf", ".ush", ".py", ".ps1", ".md", ".json", ".yml", ".yaml", ".ini", ".uplugin", ".txt", ".cmake"}
FIXTURE_SUFFIXES = {".ply", ".splat", ".spz", ".am53", ".am53seq"}
REQUIRED_FILES = ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "AbuM53.uplugin", "VERSION", "GEMINI.md", "Core/SPZ_NOTICE.md", "ThirdParty/Zstd/LICENSE", "ThirdParty/Zstd/PROVENANCE.md", "Docs/Legal/Dependencies.json", "Docs/Legal/CodeOrigins.json", "Docs/Legal/Repository_Origins_and_Licensing.md")


def is_link(path: Path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def source_paths(root: Path, violations: list[str]):
    # Prune generated directories before traversing them and never follow a
    # symbolic link/junction into a user's asset directory or the engine tree.
    for directory, dirs, names in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in list(dirs):
            path = parent / name
            if name.casefold() in {part.casefold() for part in IGNORED_PARTS}:
                dirs.remove(name)
            elif is_link(path):
                violations.append(f"Source directory is a link/junction: {path.relative_to(root)}")
                dirs.remove(name)
        for name in names:
            path = parent / name
            if is_link(path):
                violations.append(f"Source file is a link/reparse point: {path.relative_to(root)}")
                continue
            yield path


def audit(root: Path):
    violations, files = [], []
    for path in sorted(source_paths(root, violations)):
        rel = path.relative_to(root)
        if not path.is_file():
            continue
        if len(rel.parts) == 1 and rel.name in GENERATED_ROOT_FILES:
            # An unpacked release contains this generated index. It is never
            # trusted as input or included as source; packaging regenerates it.
            continue
        if rel.parts[0] not in ALLOWED_ROOT_FILES | ALLOWED_ROOT_DIRS:
            violations.append(f"Not in source allowlist: {rel}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            violations.append(f"Forbidden source-release file type: {rel}")
        fixture = rel.parts[:2] == ("Tests", "Fixtures") or rel.parts[:3] == ("Tests", "portable", "fixtures")
        allowed_type = path.suffix.lower() in SOURCE_SUFFIXES or path.name in {"LICENSE", "NOTICE", ".gitignore", ".gitattributes", "VERSION"}
        if not allowed_type and not (fixture and path.suffix.lower() in FIXTURE_SUFFIXES):
            violations.append(f"Unreviewed source-release file type: {rel}")
        if path.name.lower() in {".env", "credentials", "id_rsa", "id_ed25519"}:
            violations.append(f"Possible credential file: {rel}")
        data = path.read_bytes()
        if path.suffix.lower() in {".h", ".hpp", ".cpp", ".c", ".usf", ".ush"}:
            # This is a warning detector, never a substitute for a provenance review.
            lower = data.lower()
            if b"copyright epic games" in lower or b"copyright (c) inria" in lower:
                violations.append(f"External engine/research copyright marker: {rel}")
        files.append({"path": rel.as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    for required in REQUIRED_FILES:
        if not (root / required).is_file():
            violations.append(f"Missing required file: {required}")
    inventory = root / "Docs/Legal/Dependencies.json"
    if inventory.is_file():
        try:
            dependencies = json.loads(inventory.read_text(encoding="utf-8"))
            observed = {item["path"]: item["sha256"] for item in files}
            for component in dependencies.get("bundled_external_code", []):
                for path, expected in component.get("file_sha256", {}).items():
                    if observed.get(path) != expected:
                        violations.append(f"Vendored dependency hash mismatch: {path}")
        except (ValueError, TypeError, AttributeError) as error:
            violations.append(f"Invalid dependency inventory: {error}")
    # Source packaging and deployment both pass through this same review gate.
    if (root / "Docs/Legal/CodeOrigins.json").exists():
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Provenance"))
        from provenance import validate
        violations.extend(validate(root))
    elif (root / "VERSION").exists():
        violations.append("Missing reviewed code origins ledger")
    return {"passed": not violations, "root": str(root), "violations": violations,
            "file_count": len(files), "excluded_directory_names": sorted(IGNORED_PARTS),
            "excluded_generated_root_files": sorted(GENERATED_ROOT_FILES), "files": files,
            "limitations": "Allowlist/hash audit only; human provenance, asset rights and UE distribution review remain required."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = audit(args.root.resolve())
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "files"}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()

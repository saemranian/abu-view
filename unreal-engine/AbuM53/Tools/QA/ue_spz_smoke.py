"""UE Python import/rejection checks for the original SPZ fixtures."""
from pathlib import Path
import json
import traceback
import unreal

FIXTURES = Path(__file__).resolve().parents[2] / "Tests" / "portable" / "fixtures"
REPORT = Path(unreal.Paths.project_saved_dir()) / "AbuM53QA" / "spz-import-smoke.json"
report = {"passed": False, "checks": [], "render_test": False}
try:
    for version in range(1, 5):
        for degree in (0, 3):
            filename = f"spz_v{version}_sh{degree}.spz"
            task = unreal.AssetImportTask()
            task.filename = str(FIXTURES / filename)
            task.destination_path = "/Game/AbuM53QA/SPZ"
            task.destination_name = f"SPZ_v{version}_sh{degree}"
            task.automated = True
            task.replace_existing = True
            task.save = True
            unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
            if not task.imported_object_paths:
                raise RuntimeError(f"Import failed: {filename}")
            asset = unreal.load_asset(task.imported_object_paths[0])
            count = asset.get_splat_count()
            if count != 1 or asset.get_frame_count() != 1:
                raise RuntimeError(f"Wrong shape for {filename}: {count}")
            report["checks"].append({"file": filename, "accepted": True,
                                     "splats": count, "expected_sh_degree": degree})
    for filename in ("spz_bad_toc.spz", "spz_extensions_rejected.spz", "spz_gzip_bomb.spz"):
        task = unreal.AssetImportTask()
        task.filename = str(FIXTURES / filename)
        task.destination_path = "/Game/AbuM53QA/SPZ"
        task.destination_name = "Reject_" + Path(filename).stem
        task.automated = True
        task.replace_existing = True
        task.save = False
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        if task.imported_object_paths:
            raise RuntimeError(f"Malformed or unsupported fixture was accepted: {filename}")
        report["checks"].append({"file": filename, "accepted": False})
    report["passed"] = True
except Exception:
    report["error"] = traceback.format_exc()
    unreal.log_error(report["error"])
REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
unreal.log("ABUM53_SPZ_QA_RESULT " + json.dumps(report))
if not report["passed"]:
    raise RuntimeError("SPZ smoke failed; see " + str(REPORT))

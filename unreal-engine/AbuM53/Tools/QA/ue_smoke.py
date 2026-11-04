"""Run in UE Editor Python to import fixtures and save an isolated QA level.

Example: UnrealEditor-Cmd.exe AbuM53Host.uproject -unattended -NullRHI
         -ExecutePythonScript=<absolute path to this script>
This verifies import/serialization only; NullRHI is not a rendering test.
"""
from pathlib import Path
import json
import traceback
import unreal

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "Tests" / "Fixtures"
DESTINATION = "/Game/AbuM53QA"
REPORT = Path(unreal.Paths.project_saved_dir()) / "AbuM53QA" / "import-smoke.json"


def import_one(filename, asset_name):
    task = unreal.AssetImportTask()
    task.filename = str(FIXTURES / filename)
    task.destination_path = DESTINATION
    task.destination_name = asset_name
    task.automated = True
    task.replace_existing = True
    task.save = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    paths = list(task.imported_object_paths)
    if not paths:
        raise RuntimeError(f"Import created no asset: {filename}")
    asset = unreal.load_asset(paths[0])
    if asset is None:
        raise RuntimeError(f"Cannot load imported asset: {paths[0]}")
    result = {"file": filename, "asset": paths[0], "class": asset.get_class().get_name()}
    if hasattr(asset, "get_splat_count"):
        result["splat_count"] = asset.get_splat_count()
        if result["splat_count"] != 1000:
            raise RuntimeError(f"Unexpected splat count: {result}")
    if hasattr(asset, "get_frame_count"):
        result["frame_count"] = asset.get_frame_count()
    return asset, result


def main():
    report = {"passed": False, "imports": [], "render_test": False}
    try:
        static = None
        sequence = None
        for filename, name in (("shell_0000.ply", "ShellAscii"),
                               ("shell_binary.ply", "ShellBinary"),
                               ("shell.splat", "ShellSplat"),
                               ("shell.am53seq", "ShellSequence")):
            asset, record = import_one(filename, name)
            report["imports"].append(record)
            if name == "ShellAscii":
                static = asset
            if name == "ShellSequence":
                sequence = asset
            if name == "ShellSequence" and record.get("frame_count", 3) != 3:
                raise RuntimeError("Sequence did not preserve all three frames")
        levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        map_path = DESTINATION + "/ShellQA"
        opened = levels.load_level(map_path) if unreal.EditorAssetLibrary.does_asset_exist(map_path) else levels.new_level(map_path)
        if not opened:
            raise RuntimeError("Could not create QA map")
        actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        for old_actor in actors.get_all_level_actors():
            if isinstance(old_actor, (unreal.AbuM53Actor, unreal.CameraActor)):
                actors.destroy_actor(old_actor)
        splat_actor = actors.spawn_actor_from_class(unreal.AbuM53Actor, unreal.Vector(0, 0, 0))
        if splat_actor is None:
            raise RuntimeError("Could not spawn AbuM53Actor")
        splat_actor.set_actor_label("Abu M53 synthetic SH3 shell")
        component = splat_actor.get_editor_property("splat_component")
        component.set_asset(sequence)
        frame_checks = []
        for seconds, expected in ((0.0, 0), (1.5 / 30.0, 1), (2.0 / 30.0, 2), (0.0, 0)):
            component.seek(seconds)
            actual = component.get_current_frame_index()
            frame_checks.append({"time": seconds, "expected": expected, "actual": actual})
            if actual != expected:
                raise RuntimeError(f"Sequence seek failed: {frame_checks[-1]}")
        report["sequence_seek_checks"] = frame_checks
        component.set_asset(static)
        component.set_editor_property("units_to_centimeters", 100.0)
        location = unreal.Vector(330, 0, 100)
        rotation = unreal.MathLibrary.find_look_at_rotation(location, unreal.Vector(0, 0, 0))
        camera = actors.spawn_actor_from_class(unreal.CameraActor, location, rotation)
        camera.set_actor_label("Abu M53 QA camera")
        camera.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
        camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(55.0)
        unreal.EditorLevelLibrary.set_level_viewport_camera_info(location, rotation)
        if not levels.save_current_level():
            raise RuntimeError("Could not save QA map")
        report.update({"passed": True, "map": DESTINATION + "/ShellQA",
                       "camera_location": [330, 0, 100], "source_splats": 1000,
                       "note": "Import and actor setup checked; rendering requires a GPU run."})
    except Exception:
        report["error"] = traceback.format_exc()
        unreal.log_error(report["error"])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    unreal.log("ABUM53_QA_RESULT " + json.dumps(report))
    if not report["passed"]:
        raise RuntimeError("Abu M53 import smoke failed; see " + str(REPORT))


main()

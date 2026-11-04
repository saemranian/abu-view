"""Capture fixed-camera backend comparisons in a rendering UE editor, then quit.

Thirty editor ticks follow each mode change, and another thirty follow each
screenshot request. The JSON records requests; inspect images/logs separately.
The capacity-32 case is an overflow probe, not proof that overflow occurred.
"""
from pathlib import Path
import json
import traceback
import unreal

OUTPUT = Path(unreal.Paths.project_saved_dir()) / "AbuM53QA"
OUTPUT.mkdir(parents=True, exist_ok=True)
REPORT = OUTPUT / "backend-capture-requests.json"
MODES = [
    ("gpu_tiled", 1, 1, 1, 1024),
    ("gpu_quad", 1, 1, 0, 1024),
    ("gpu_overflow_probe", 1, 1, 1, 32),
    ("cpu_assisted", 1, 2, 0, 1024),
    ("disabled", 0, 1, 1, 1024),
    ("cpu_software", 1, 3, 0, 1024),
]
_m53_report = {"completed": False, "width": 1280, "height": 720,
               "camera_location": [330, 0, 100], "requests": [],
               "note": "Requests are not image correctness or overflow telemetry."}
_m53_index = 0
_m53_ticks = 0
_m53_callback = None


def _m53_write_report():
    REPORT.write_text(json.dumps(_m53_report, indent=2) + "\n", encoding="utf-8")


def _m53_set_mode():
    global _m53_ticks
    _m53_ticks = 0
    name, enable, backend, tiles, capacity = MODES[_m53_index]
    commands = [f"r.AbuM53.Enable {enable}", f"r.AbuM53.Backend {backend}",
                f"r.AbuM53.Tiles {tiles}", f"r.AbuM53.TileCapacity {capacity}"]
    for command in commands:
        unreal.SystemLibrary.execute_console_command(_m53_world, command)
    location = unreal.Vector(330, 0, 100)
    rotation = unreal.MathLibrary.find_look_at_rotation(location, unreal.Vector(0, 0, 0))
    unreal.EditorLevelLibrary.set_level_viewport_camera_info(location, rotation)
    unreal.EditorLevelLibrary.editor_set_game_view(True)
    unreal.EditorLevelLibrary.editor_invalidate_viewports()
    _m53_report["requests"].append({"mode": name, "commands": commands,
        "filename": str(OUTPUT / ("backend_" + name + ".png")), "requested": False})
    _m53_write_report()


def _m53_tick(_delta):
    global _m53_ticks, _m53_index
    try:
        _m53_ticks += 1
        unreal.EditorLevelLibrary.editor_invalidate_viewports()
        if _m53_ticks == 30:
            record = _m53_report["requests"][-1]
            accepted = unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, record["filename"])
            record["requested"] = bool(accepted)
            _m53_write_report()
        if _m53_ticks >= 60:
            _m53_index += 1
            if _m53_index < len(MODES):
                _m53_set_mode()
            else:
                _m53_report["completed"] = True
                _m53_write_report()
                unreal.unregister_slate_post_tick_callback(_m53_callback)
                unreal.SystemLibrary.quit_editor()
    except Exception:
        _m53_report["error"] = traceback.format_exc()
        _m53_write_report()
        unreal.log_error(_m53_report["error"])
        unreal.unregister_slate_post_tick_callback(_m53_callback)
        unreal.SystemLibrary.quit_editor()


_m53_levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not _m53_levels.load_level("/Game/AbuM53QA/ShellQA"):
    raise RuntimeError("Run ue_smoke.py first to create the QA map")
_m53_world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if _m53_world is None:
    raise RuntimeError("No editor world is available")
_m53_set_mode()
_m53_callback = unreal.register_slate_post_tick_callback(_m53_tick)

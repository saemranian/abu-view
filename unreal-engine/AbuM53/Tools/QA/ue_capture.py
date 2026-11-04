"""Run in a rendering UE editor (offscreen supported); capture saved QA level after 60 editor ticks.

Do not use this script under NullRHI. The screenshot is evidence to inspect,
not an automatic proof that the renderer produces correct output.
"""
from pathlib import Path
import json
import unreal

OUTPUT = Path(unreal.Paths.project_saved_dir()) / "AbuM53QA"
OUTPUT.mkdir(parents=True, exist_ok=True)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not levels.load_level("/Game/AbuM53QA/ShellQA"):
    raise RuntimeError("Run ue_smoke.py first to create the QA map")
location = unreal.Vector(330, 0, 100)
rotation = unreal.MathLibrary.find_look_at_rotation(location, unreal.Vector(0, 0, 0))
unreal.EditorLevelLibrary.set_level_viewport_camera_info(location, rotation)
unreal.EditorLevelLibrary.editor_set_game_view(True)
unreal.EditorLevelLibrary.editor_invalidate_viewports()
_m53_ticks = 0
_m53_callback = None


def _m53_tick(_delta):
    global _m53_ticks
    _m53_ticks += 1
    if _m53_ticks == 60:
        accepted = unreal.AutomationLibrary.take_high_res_screenshot(
            1280, 720, str(OUTPUT / "shell_gpu.png"))
        (OUTPUT / "capture-request.json").write_text(json.dumps({
            "requested": bool(accepted), "filename": str(OUTPUT / "shell_gpu.png"),
            "width": 1280, "height": 720,
            "note": "Inspect screenshot and GPU logs before marking render validation passed."
        }, indent=2), encoding="utf-8")
    if _m53_ticks >= 90:
        unreal.unregister_slate_post_tick_callback(_m53_callback)
        unreal.SystemLibrary.quit_editor()


_m53_callback = unreal.register_slate_post_tick_callback(_m53_tick)

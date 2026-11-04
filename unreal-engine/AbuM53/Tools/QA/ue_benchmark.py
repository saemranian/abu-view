"""Run an explicitly synthetic 1M / 5M selected-splat editor benchmark.

Run in a rendering UE editor, with ABUM53_BENCHMARK_FILE pointing to the
generated work/AbuM53Benchmark/shell_1000000.ply. Do not use NullRHI.
The saved /Game/AbuM53QA/ShellQA map must already exist. The imported large
asset and modified map are kept unsaved. The editor quits when finished.

Each stage explicitly requests a 1280x720 SceneCapture2D render per Slate tick,
warms for 120 ticks, and captures CSVProfile and 300 consecutive perf_counter
callback intervals. CSV counters must confirm one Abu M53 rendered view with
the expected selected splat count on every interior frame. Boundary alignment
permits exactly two discarded CSV frames at either end. GPUTime is reported
separately. Callback intervals are editor submission/end-to-end wall time, not
GPU timestamps or presented FPS. An evidence PNG is exported from the same
render target after profiling. Explicit captures work with -RenderOffscreen;
normal editor viewports may be skipped when the application is hidden.

Five actors share one 1M asset. Source inputs selected by the configured budget
are counted; visible/contributing splats require renderer readback and are
explicitly unmeasured. This synthetic small-footprint shell is not a substitute
for real-scene, overlap, memory-pressure, or shipping-runtime benchmarks.
"""
from pathlib import Path
from datetime import datetime, timezone
import csv
import json
import math
import os
import statistics
import struct
import time
import traceback
import zlib
import unreal


WARMUP_TICKS = 120
MEASURE_TICKS = 300
FLUSH_TIMEOUT_SECONDS = 120.0
SCREENSHOT_SIZE = (1280, 720)
POSITIONS = [(0, 0, 0), (0, -240, 0), (0, 240, 0),
             (0, 0, -240), (0, 0, 240)]
CONTROLS = {
    "r.AbuM53.Enable": 1, "r.AbuM53.Backend": 1, "r.AbuM53.Tiles": 1,
    "r.AbuM53.MaxSplats": 5_000_000, "r.AbuM53.TileCapacity": 1024,
    "r.VSync": 0, "r.VSyncEditor": 0, "t.MaxFPS": 0,
    "t.IdleWhenNotForeground": 0, "r.ScreenPercentage": 100,
    "r.DynamicRes.OperationMode": 0, "csv.CompressionMode": 0,
    "r.SceneCapture.CullByDetailMode": 0,
}
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
SAVED = Path(unreal.Paths.project_saved_dir()).resolve()
OUTPUT = Path(os.environ.get("ABUM53_BENCHMARK_OUTPUT",
                            str(SAVED / "AbuM53QA" / "Benchmark" / RUN_ID))).resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)
REPORT_PATH = OUTPUT / "benchmark.json"
_m53_report = {
    "schema": 2, "completed": False, "run_id": RUN_ID,
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "warmup_slate_ticks": WARMUP_TICKS, "measured_slate_intervals": MEASURE_TICKS,
    "timing_scope": "offscreen synthetic capture / editor callback submission intervals",
    "timing_is_gpu_time": False, "timing_is_presented_fps": False,
    "gpu_identity": None, "gpu_identity_evidence": "Inspect this run's D3D12 startup log",
    "project_log_directory": str(SAVED / "Logs"),
    "requested_screenshot_size": list(SCREENSHOT_SIZE),
    "render_driver": "one explicit SceneCaptureComponent2D.capture_scene per Slate tick",
    "render_target_format": "RGBA8 / FinalColorLDR",
    "renderer_counter_validation_required": True,
    "controls_requested": CONTROLS, "stages": [],
    "limitations": [
        "1M and 5M refer to selected source inputs; visible splats are unmeasured.",
        "Five instances share one synthetic asset; this is not five unique scenes.",
        "Evidence PNG export reads the capture render target outside the timed window.",
        "The editor viewport is unrelated to the fixed 1280x720 capture workload.",
        "CSV frames and Slate callback intervals may have different boundaries.",
        "Tile overflow may invoke the sorted-quad fallback; no overflow readback is exposed.",
        "Callback time includes submission overhead and possible GPU waiting; it is not FPS.",
        "GPUTime is engine-reported aggregate GPU frame time, not only the splat passes.",
        "No forced GPU synchronization is inserted per capture; callbacks may queue work.",
    ],
}
_m53_callback = None
_m53_csv_active = False
_m53_world = None
_m53_levels = None
_m53_editor = None
_m53_actors = None
_m53_asset = None
_m53_capture_actor = None
_m53_capture = None
_m53_target = None
_m53_instances = []
_m53_stage = None
_m53_phase = "setup"
_m53_ticks = 0
_m53_last_time = 0.0
_m53_phase_start = 0.0
_m53_samples = []
_m53_file_signature = None
_m53_file_stable_since = 0.0


def _m53_write_report():
    REPORT_PATH.write_text(json.dumps(_m53_report, indent=2) + "\n", encoding="utf-8")


def _m53_command(command):
    unreal.SystemLibrary.execute_console_command(_m53_world, command)


def _m53_viewport_size():
    size = _m53_editor.get_level_viewport_size()
    return [int(size.x), int(size.y)] if size is not None else None


def _m53_percentile(ordered, percentile):
    index = (len(ordered) - 1) * percentile / 100.0
    lower = math.floor(index)
    upper = math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _m53_summary(samples):
    ordered = sorted(samples)
    mean = statistics.fmean(samples)
    return {
        "sample_count": len(samples), "total_wall_seconds": sum(samples) / 1000,
        "mean_ms": mean, "minimum_ms": ordered[0], "maximum_ms": ordered[-1],
        "p50_ms": _m53_percentile(ordered, 50), "p90_ms": _m53_percentile(ordered, 90),
        "p95_ms": _m53_percentile(ordered, 95), "p99_ms": _m53_percentile(ordered, 99),
        "percentile_method": "linear interpolation between ordered samples",
    }


def _m53_frame_scene():
    global _m53_capture_actor, _m53_capture, _m53_target
    # All five unit-radius shells fit the same camera, including their depth.
    # The widest stage is +/-342 cm in Y/Z including conservative splat bounds.
    aspect = SCREENSHOT_SIZE[0] / SCREENSHOT_SIZE[1]
    distance = 102.0 + 1.2 * 342.0 * max(1.0, aspect) / math.tan(math.radians(30))
    location = unreal.Vector(distance, 0, 0)
    target = unreal.Vector(0, 0, 0)
    key = _m53_levels.get_active_viewport_config_key()
    if _m53_levels.get_pilot_level_actor(key) is not None:
        _m53_levels.eject_pilot_level_actor(key)
    _m53_levels.set_level_viewport_fov(60.0, key)
    _m53_levels.set_level_viewport_camera_info(
        location, unreal.MathLibrary.find_look_at_rotation(location, target), key)
    # UE5.8's True call only removes a named override and ensures if absent.
    # False adds an override and avoids incidental normal-viewport rendering.
    _m53_levels.editor_set_viewport_realtime(False, key)
    _m53_levels.editor_set_game_view(True, key)
    _m53_levels.editor_invalidate_viewports()
    _m53_report["camera"] = {"location_cm": [distance, 0, 0],
                             "target_cm": [0, 0, 0], "horizontal_fov_degrees": 60}
    rotation = unreal.MathLibrary.find_look_at_rotation(location, target)
    _m53_capture_actor = _m53_actors.spawn_actor_from_class(unreal.SceneCapture2D, location, rotation)
    if _m53_capture_actor is None:
        raise RuntimeError("Could not spawn the offscreen benchmark capture")
    _m53_capture_actor.set_actor_label("Abu M53 benchmark capture (unsaved)")
    _m53_capture = _m53_capture_actor.get_component_by_class(unreal.SceneCaptureComponent2D)
    _m53_capture.set_editor_property("capture_every_frame", False)
    _m53_capture.set_editor_property("capture_on_movement", False)
    _m53_capture.set_editor_property("always_persist_rendering_state", True)
    _m53_capture.set_editor_property("fov_angle", 60.0)
    _m53_capture.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    _m53_target = unreal.RenderingLibrary.create_render_target2d(
        _m53_world, *SCREENSHOT_SIZE, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    if _m53_target is None:
        raise RuntimeError("Could not create the benchmark render target")
    _m53_capture.set_editor_property("texture_target", _m53_target)
    _m53_report["actual_capture_size"] = [
        _m53_target.get_editor_property("size_x"), _m53_target.get_editor_property("size_y")]


def _m53_bounds_in_view():
    # Check the explicit capture camera, not the editor's unrelated viewport.
    distance = _m53_report["camera"]["location_cm"][0]
    aspect = SCREENSHOT_SIZE[0] / SCREENSHOT_SIZE[1]
    for x in (-102, 102):
        for y in (-342, 342):
            for z in (-342, 342):
                half_width = (distance - x) * math.tan(math.radians(30))
                if half_width <= 0 or abs(y) >= half_width or abs(z) >= half_width / aspect:
                    return False
    return True


def _m53_validate_renderer_csv(path, expected_splats):
    """Accept timings only when the renderer actually submitted the expected views."""
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.reader(stream))
    if not rows:
        raise RuntimeError("CSV capture is empty")
    # UE appends a complete header at finalization, including late-created stats.
    header = next((row for row in reversed(rows) if row and row[0] == "EVENTS"), rows[0])

    def column(name, required=True):
        matches = [i for i, value in enumerate(header) if value == name]
        if not matches and "/" in name:
            category, stat = name.split("/", 1)
            matches = [i for i, value in enumerate(header)
                       if value.startswith(category + "/") and value.endswith("/" + stat)]
        if len(matches) != 1:
            if required:
                raise RuntimeError("CSV missing an unambiguous renderer counter: " + name)
            return None
        return matches[0]

    frame_i = column("FrameTime")
    view_i = column("AbuM53/RenderedViews")
    selected_i = column("AbuM53/SelectedSplats")
    gpu_i = column("GPUTime")
    primitive_i = column("RHI/PrimitivesDrawn", required=False)
    splat_gpu_i = column("GPU/AbuM53", required=False)
    frames = []
    for row in rows[1:]:
        if not row or row[0] == "EVENTS" or row[0].startswith("["):
            continue
        try:
            frame_time = float(row[frame_i])
        except (ValueError, IndexError):
            continue
        if not math.isfinite(frame_time) or frame_time <= 0:
            continue

        def value(index):
            if index is None:
                return None
            try:
                result = float(row[index]) if row[index] else 0.0
                return result if math.isfinite(result) else 0.0
            except (ValueError, IndexError):
                return 0.0

        frames.append({"frame_time_ms": frame_time, "rendered_views": value(view_i),
                       "selected_splats": value(selected_i), "gpu_time_ms": value(gpu_i),
                       "rhi_primitives": value(primitive_i), "splat_gpu_time_ms": value(splat_gpu_i)})
    interior = frames[2:-2]
    result = {"passed": False, "csv_frame_rows": len(frames),
              "boundary_rows_discarded_each_end": 2, "validated_frame_rows": len(interior),
              "expected_rendered_views_per_frame": 1, "expected_selected_splats": expected_splats,
              "counter_scope": "CPU render submission counters; not visible splats or GPU completion",
              "rendered_views_total": sum(frame["rendered_views"] for frame in frames)}
    _m53_stage["renderer_validation"] = result
    if not MEASURE_TICKS - 2 <= len(frames) <= MEASURE_TICKS + 4:
        raise RuntimeError("Unexpected CSV frame count; cannot align the 300-callback capture")
    bad = [{"interior_index": i, **frame} for i, frame in enumerate(interior)
           if frame["rendered_views"] != 1 or frame["selected_splats"] != expected_splats
           or frame["gpu_time_ms"] <= 0]
    result["invalid_interior_frames"] = bad[:12]
    result["invalid_interior_frame_count"] = len(bad)
    if bad or len(interior) < MEASURE_TICKS - 6:
        raise RuntimeError("Capture did not render exactly one expected Abu M53 view with positive GPUTime per interior CSV frame")
    result["passed"] = True
    for field, label in (("frame_time_ms", "engine_frame_time"), ("gpu_time_ms", "engine_gpu_frame_time"),
                         ("splat_gpu_time_ms", "abu_m53_gpu_pass_time")):
        values = [frame[field] for frame in interior if frame[field] is not None]
        if values:
            stats = _m53_summary(values)
            stats.pop("total_wall_seconds", None)
            result[label] = stats
    primitives = [frame["rhi_primitives"] for frame in interior if frame["rhi_primitives"] is not None]
    if primitives:
        result["rhi_primitives_range"] = [min(primitives), max(primitives)]
    _m53_stage["timing_validated_against_renderer"] = True


def _m53_spawn(position):
    actor = _m53_actors.spawn_actor_from_class(unreal.AbuM53Actor, unreal.Vector(*position))
    if actor is None:
        raise RuntimeError("Could not spawn benchmark actor")
    actor.set_actor_label("Abu M53 benchmark " + str(len(_m53_instances) + 1))
    component = actor.get_editor_property("splat_component")
    component.set_asset(_m53_asset)
    component.set_editor_property("units_to_centimeters", 100.0)
    component.set_editor_property("backend", unreal.AbuM53Backend.GPU)
    component.set_editor_property("max_visible_splats", 1_000_000)
    component.set_editor_property("enable_crop", False)
    component.pause()
    _m53_instances.append(actor)


def _m53_begin_stage(actor_count):
    global _m53_stage, _m53_phase, _m53_ticks, _m53_phase_start
    while len(_m53_instances) < actor_count:
        _m53_spawn(POSITIONS[len(_m53_instances)])
    name = f"selected_{actor_count}000000"
    csv_name = "AbuM53_" + RUN_ID + "_" + name
    _m53_stage = {
        "name": name, "actor_count": actor_count, "unique_assets": 1,
        "source_splats_per_asset": _m53_asset.get_splat_count(),
        "selected_splats": actor_count * _m53_asset.get_splat_count(),
        "selected_count_basis": "asset count x active actor instances, within 5M view budget",
        "visible_splats": None, "visible_count_measured": False,
        "visible_count_note": "No renderer GPU visibility readback is exposed to Python",
        "actor_positions_cm": POSITIONS[:actor_count],
        "csv_basename": csv_name,
        "csv_path": str(SAVED / "Profiling" / "CSV" / (csv_name + ".csv")),
        "csv_finalized": False, "completed": False,
        "timing_validated_against_renderer": False,
        "screenshot_path": str(OUTPUT / (name + ".png")),
    }
    _m53_report["stages"].append(_m53_stage)
    _m53_phase, _m53_ticks = "warmup", 0
    _m53_phase_start = time.perf_counter()
    _m53_write_report()
    unreal.log(f"ABUM53_BENCHMARK warming {name}")


def _m53_png_completion(path, file_size):
    """Validate bounded PNG chunks through IEND, retaining trailing-byte evidence."""
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            return None
        offset, dimensions, saw_image_data = 8, None, False
        while offset + 12 <= file_size:
            chunk_header = stream.read(8)
            if len(chunk_header) != 8:
                return None
            length, kind = struct.unpack(">I4s", chunk_header)
            end = offset + 12 + length
            if end > file_size or (offset == 8 and (kind != b"IHDR" or length != 13)):
                return None
            crc = zlib.crc32(kind)
            remaining = length
            ihdr = bytearray()
            while remaining:
                block = stream.read(min(remaining, 65536))
                if not block:
                    return None
                crc = zlib.crc32(block, crc)
                if kind == b"IHDR":
                    if offset != 8 or length != 13:
                        return None
                    ihdr.extend(block)
                remaining -= len(block)
            stored_crc = stream.read(4)
            if len(stored_crc) != 4 or crc != struct.unpack(">I", stored_crc)[0]:
                return None
            if kind == b"IHDR":
                dimensions = list(struct.unpack(">II", ihdr[:8]))
                if min(dimensions) <= 0:
                    return None
            elif kind == b"IDAT":
                saw_image_data = True
            elif kind == b"IEND":
                if length != 0 or dimensions is None or not saw_image_data:
                    return None
                return {"screenshot_actual_size": dimensions,
                        "screenshot_png_chunk_crc_valid": True,
                        "screenshot_png_end_offset": end,
                        "screenshot_trailing_bytes": file_size - end,
                        "screenshot_png_has_no_trailing_data": end == file_size,
                        "screenshot_local_only": end != file_size,
                        "screenshot_validation_note": (
                            "Complete PNG through valid IEND; trailing bytes retained; local-only evidence, do not distribute"
                            if end != file_size else "Complete PNG with valid chunk CRCs and final IEND")}
            offset = end
    return None


def _m53_completed_file(path, now, csv_footer=False):
    global _m53_file_signature, _m53_file_stable_since
    if not path.exists():
        return False
    info = path.stat()
    signature = (info.st_size, info.st_mtime_ns)
    if signature != _m53_file_signature:
        _m53_file_signature, _m53_file_stable_since = signature, now
        return False
    if info.st_size == 0 or now - _m53_file_stable_since < 1.0:
        return False
    if csv_footer:
        with path.open("rb") as stream:
            stream.seek(max(0, info.st_size - 65536))
            return b"[HasHeaderRowAtEnd]" in stream.read()
    png = _m53_png_completion(path, info.st_size)
    if png is None:
        return False
    _m53_stage.update(png)
    return True


def _m53_finish(error=None):
    global _m53_callback, _m53_csv_active
    if _m53_csv_active:
        _m53_command("CSVProfile STOP")
        _m53_csv_active = False
    if error:
        _m53_report["error"] = error
        unreal.log_error(error)
    else:
        _m53_report["completed"] = True
    _m53_write_report()
    unreal.log("ABUM53_BENCHMARK_RESULT " + str(REPORT_PATH))
    if _m53_callback is not None:
        unreal.unregister_slate_post_tick_callback(_m53_callback)
        _m53_callback = None
    # No save calls: the large asset and transient map changes stay unsaved.
    unreal.SystemLibrary.quit_editor()


def _m53_tick(_delta):
    global _m53_phase, _m53_ticks, _m53_phase_start, _m53_last_time
    global _m53_samples, _m53_csv_active, _m53_file_signature
    try:
        now = time.perf_counter()
        _m53_ticks += 1
        if _m53_phase in ("warmup", "measure"):
            _m53_capture.capture_scene()
        if _m53_phase == "warmup" and _m53_ticks >= WARMUP_TICKS:
            _m53_stage["warmup_wall_seconds"] = now - _m53_phase_start
            _m53_stage["viewport_size_before_measurement"] = _m53_viewport_size()
            _m53_stage["conservative_five_shell_bounds_inside_capture"] = _m53_bounds_in_view()
            if not _m53_stage["conservative_five_shell_bounds_inside_capture"]:
                raise RuntimeError("Conservative benchmark bounds are outside the capture camera")
            _m53_stage["controls_readback"] = {
                key: unreal.SystemLibrary.get_console_variable_float_value(key) for key in CONTROLS}
            for key in ("r.AbuM53.Enable", "r.AbuM53.Backend", "r.AbuM53.Tiles", "r.AbuM53.MaxSplats"):
                if _m53_stage["controls_readback"][key] != CONTROLS[key]:
                    raise RuntimeError("Benchmark control was not applied: " + key)
            _m53_write_report()
            _m53_command("CSVProfile STARTFILE=" + _m53_stage["csv_basename"])
            _m53_command("CSVProfile START")
            _m53_csv_active = True
            _m53_phase, _m53_ticks, _m53_samples = "measure", 0, []
            _m53_last_time = time.perf_counter()
        elif _m53_phase == "measure":
            _m53_samples.append((now - _m53_last_time) * 1000.0)
            _m53_last_time = now
            if len(_m53_samples) >= MEASURE_TICKS:
                _m53_command("CSVProfile STOP")
                _m53_csv_active = False
                _m53_stage["editor_callback_timing"] = _m53_summary(_m53_samples)
                _m53_stage["viewport_size_after_measurement"] = _m53_viewport_size()
                _m53_stage["viewport_dimensions_stable"] = (
                    _m53_stage["viewport_size_before_measurement"] ==
                    _m53_stage["viewport_size_after_measurement"])
                timing_path = OUTPUT / (_m53_stage["name"] + "_editor_intervals.csv")
                with timing_path.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(["slate_callback_interval", "editor_wall_time_ms"])
                    writer.writerows(enumerate(_m53_samples, 1))
                _m53_stage["editor_interval_csv"] = str(timing_path)
                _m53_phase, _m53_ticks, _m53_phase_start = "csv_flush", 0, now
                _m53_file_signature = None
                _m53_write_report()
        elif _m53_phase == "csv_flush":
            if _m53_completed_file(Path(_m53_stage["csv_path"]), now, csv_footer=True):
                _m53_stage["csv_finalized"] = True
                _m53_stage["csv_bytes"] = Path(_m53_stage["csv_path"]).stat().st_size
                _m53_validate_renderer_csv(Path(_m53_stage["csv_path"]), _m53_stage["selected_splats"])
                image_path = Path(_m53_stage["screenshot_path"])
                # ImageWriteQueue writes the encoded byte length. The legacy UE
                # render-target exporter may append allocator capacity bytes.
                options = unreal.ImageWriteOptions(
                    format=unreal.DesiredImageFormat.PNG, async_=False, overwrite_file=True)
                unreal.ImageWriteBlueprintLibrary.export_to_disk(_m53_target, str(image_path), options)
                _m53_stage["screenshot_exporter"] = "ImageWriteQueue PNG, synchronous, overwrite"
                _m53_stage["screenshot_source"] = "same SceneCapture2D render target as timed workload"
                _m53_phase, _m53_ticks, _m53_phase_start = "screenshot_flush", 0, now
                _m53_file_signature = None
                _m53_write_report()
            elif now - _m53_phase_start > FLUSH_TIMEOUT_SECONDS:
                raise RuntimeError("CSV capture did not finalize within 120 seconds")
        elif _m53_phase == "screenshot_flush":
            if _m53_completed_file(Path(_m53_stage["screenshot_path"]), now):
                _m53_stage["completed"] = True
                _m53_write_report()
                if len(_m53_instances) == 1:
                    _m53_begin_stage(5)
                else:
                    _m53_finish()
            elif now - _m53_phase_start > FLUSH_TIMEOUT_SECONDS:
                raise RuntimeError("Evidence PNG did not finish within 120 seconds")
    except Exception:
        _m53_finish(traceback.format_exc())


def _m53_setup():
    global _m53_world, _m53_levels, _m53_editor, _m53_actors, _m53_asset, _m53_callback
    filename = os.environ.get("ABUM53_BENCHMARK_FILE")
    if not filename:
        raise RuntimeError("Set ABUM53_BENCHMARK_FILE to generated shell_1000000.ply")
    source = Path(filename).resolve(strict=True)
    _m53_report["source_file"] = str(source)
    _m53_report["source_bytes"] = source.stat().st_size
    metadata_path = source.with_suffix(".json")
    if metadata_path.is_file():
        _m53_report["generator_metadata"] = json.loads(metadata_path.read_text(encoding="utf-8"))
    _m53_levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    _m53_editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    _m53_actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not _m53_levels.load_level("/Game/AbuM53QA/ShellQA"):
        raise RuntimeError("Run ue_smoke.py first to create /Game/AbuM53QA/ShellQA")
    _m53_world = _m53_editor.get_editor_world()
    if _m53_world is None:
        raise RuntimeError("A rendering editor world is required")
    for actor in _m53_actors.get_all_level_actors():
        if isinstance(actor, unreal.AbuM53Actor):
            _m53_actors.destroy_actor(actor)
    task = unreal.AssetImportTask()
    task.filename = str(source)
    task.destination_path = "/Game/AbuM53QA/BenchmarkUnsaved"
    task.destination_name = "Shell1M_" + RUN_ID
    task.automated, task.replace_existing, task.save = True, False, False
    started = time.perf_counter()
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    _m53_report["import_wall_seconds"] = time.perf_counter() - started
    paths = list(task.imported_object_paths)
    if len(paths) != 1:
        raise RuntimeError("Benchmark import did not create exactly one asset")
    _m53_asset = unreal.load_asset(paths[0])
    if (_m53_asset is None or _m53_asset.get_splat_count() != 1_000_000 or
            _m53_asset.get_frame_count() != 1):
        raise RuntimeError("Benchmark requires one static asset containing exactly 1,000,000 splats")
    _m53_report["unsaved_asset_path"] = paths[0]
    for name, value in CONTROLS.items():
        _m53_command(f"{name} {value}")
    _m53_command("CSVCategory AbuM53 enable")
    _m53_frame_scene()
    _m53_begin_stage(1)
    _m53_callback = unreal.register_slate_post_tick_callback(_m53_tick)


try:
    _m53_setup()
except Exception:
    _m53_finish(traceback.format_exc())

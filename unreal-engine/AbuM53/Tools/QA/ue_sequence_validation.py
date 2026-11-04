"""Import, render and reopen a prepared independent sequence in the UE editor.

Use UnrealEditor.exe <abu_M53_Test_01.uproject> -unattended -RenderOffscreen
    "-ExecCmds=py <this file>". A rendering RHI is required, not NullRHI.
Do not use -ExecutePythonScript: its commandlet lifecycle exits before the
asynchronous Slate callbacks can finish. The script quits on completion.
Set ABUM53_SEQUENCE_MANIFEST to the prepared sequence.am53seq and
ABUM53_SEQUENCE_OUTPUT to a new private evidence directory outside Git.
ABUM53_SEQUENCE_CACHE_MIB defaults to 3072, ABUM53_SEQUENCE_TIMEOUT to 300s.
ABUM53_SOURCE_CACHE_MIB defaults to 3072 for the independent GPU source cache.
ABUM53_SEQUENCE_CAMERA optionally supplies JSON with source-space location,
target and fov values after scouting a useful viewing angle.
ABUM53_SEQUENCE_AXES defaults to right_down_forward (an explicitly reported
viewing assumption for Skate); raw_xyz is also supported. Original PLYs are
never changed. ABUM53_SEQUENCE_QUIT=0 leaves the isolated test level open.

The script creates unique /Game/AbuM53SkateQA/Run_<UTC> assets and a map, never
overwriting existing user levels or assets. It refuses to replace a dirty map.
The preparation report supplies expected counts; every decoded frame must match.
Actual displayed indices/counts are checked, not merely requested timestamps.
Captures retain the full source-splat budget and test nonblack/color pixels.
The 10-second native warm playback captures CSVProfile and callback intervals;
PNG export/analysis is outside that interval. No presented FPS is claimed.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
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


RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
OUTPUT = Path(os.environ["ABUM53_SEQUENCE_OUTPUT"]).resolve()
MANIFEST = Path(os.environ["ABUM53_SEQUENCE_MANIFEST"]).resolve(strict=True)
TIMEOUT = float(os.environ.get("ABUM53_SEQUENCE_TIMEOUT", "300"))
CACHE_MIB = int(os.environ.get("ABUM53_SEQUENCE_CACHE_MIB", "3072"))
SOURCE_CACHE_MIB = int(os.environ.get("ABUM53_SOURCE_CACHE_MIB", "3072"))
CAMERA = json.loads(os.environ["ABUM53_SEQUENCE_CAMERA"]) if "ABUM53_SEQUENCE_CAMERA" in os.environ else None
AXES = os.environ.get("ABUM53_SEQUENCE_AXES", "right_down_forward")
QUIT = os.environ.get("ABUM53_SEQUENCE_QUIT", "1") != "0"
OUTPUT.mkdir(parents=True, exist_ok=True)
REPORT_PATH = OUTPUT / "sequence-validation.json"
CSV_NAME = "AbuM53_Skate_" + RUN_ID
CSV_PATH = Path(unreal.Paths.project_saved_dir()).resolve() / "Profiling" / "CSV" / (CSV_NAME + ".csv")
DESTINATION = "/Game/AbuM53SkateQA/Run_" + RUN_ID
PREPARATION = json.loads((MANIFEST.parent / "sequence-preparation.json").read_text(encoding="utf-8"))
SEQUENCE = json.loads(MANIFEST.read_text(encoding="utf-8"))
FRAME_COUNT = len(SEQUENCE["frames"])
EXPECTED_COUNTS = [record["vertex_count"] for record in PREPARATION["frames"]]
WIDTH, HEIGHT = 1280, 720
_seq_report = {
    "schema": 1, "passed": False, "run_id": RUN_ID,
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "manifest": str(MANIFEST), "source_files_opened_read_only": True,
    "frame_count": FRAME_COUNT, "expected_splat_counts": EXPECTED_COUNTS,
    "fps_assumption": SEQUENCE["fps"], "fps_is_source_metadata": False,
    "storage": SEQUENCE.get("storage", "embedded"),
    "coordinate_view_assumption": AXES, "cache_mib": CACHE_MIB, "gpu_source_cache_mib_requested": SOURCE_CACHE_MIB,
    "independent_sample_and_hold": True, "interpolation": False,
    "capture_size": [WIDTH, HEIGHT], "render_driver": "explicit SceneCapture2D",
    "frame_checks": [], "warm_seek_checks": [], "reload_checks": [], "playback_observations": [],
    "map": DESTINATION + "/SkateSequenceQA", "asset": DESTINATION + "/SkateSequence",
    "performance_note": "Callback wall intervals are not presented FPS or GPU timestamps.",
    "visual_quality_note": "Nonblack/chromatic checks detect blank output only. Framing, foreground floaters and fidelity require visual review against an appropriate source camera/reference.",
    "csv": {"path": str(CSV_PATH), "name": CSV_NAME, "finalized": False,
            "scope": "ten seconds of native warm playback; PNG processing excluded",
            "timing_is_presented_fps": False},
}
_seq_callback = None
_seq_in_tick = False
_seq_levels = _seq_editor = _seq_actors = _seq_world = None
_seq_actor = _seq_component = _seq_asset = _seq_capture_actor = _seq_capture = _seq_target = None
_seq_phase = "setup"
_seq_started = _seq_phase_started = time.perf_counter()
_seq_frame = _seq_ticks = 0
_seq_settle_ticks = 0
_seq_playback_samples = []
_seq_playback_seen = set()
_seq_reload = False
_seq_warm_targets = list(range(FRAME_COUNT - 2, -1, -1)) + [FRAME_COUNT - 1]
_seq_warm_cursor = 0
_seq_csv_active = False
_seq_csv_signature = None
_seq_playback_last_time = 0.0
_seq_performance_settings = None
_seq_original_background_throttle = None


def _seq_write():
    REPORT_PATH.write_text(json.dumps(_seq_report, indent=2) + "\n", encoding="utf-8")


def _seq_command(command):
    unreal.SystemLibrary.execute_console_command(_seq_world, command)


def _seq_summary(values):
    ordered = sorted(values)
    def percentile(fraction):
        index = (len(ordered) - 1) * fraction
        lower, upper = math.floor(index), math.ceil(index)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)
    return {"samples": len(values), "mean_ms": statistics.fmean(values),
            "minimum_ms": ordered[0], "maximum_ms": ordered[-1],
            "p50_ms": percentile(.5), "p95_ms": percentile(.95), "p99_ms": percentile(.99)}


def _seq_csv_completion(path, previous_signature):
    """Wait for a stable, readable file with UE's real final metadata marker.

    Windows CSV writer sharing violations and transient filesystem errors are
    pending states. The caller owns a bounded timeout; this helper never sleeps.
    """
    try:
        info = path.stat()
        signature = (info.st_size, info.st_mtime_ns)
        if signature != previous_signature or info.st_size == 0:
            return False, signature, None
        with path.open("rb") as stream:
            stream.seek(max(0, info.st_size - 65536))
            footer = b"[HasHeaderRowAtEnd]" in stream.read()
        after = path.stat()
        after_signature = (after.st_size, after.st_mtime_ns)
        return footer and signature == after_signature, after_signature, None
    except OSError as pending_error:
        return False, previous_signature, str(pending_error)


def _seq_analyze_csv():
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    header = next((row for row in reversed(rows) if row and row[0] == "EVENTS"), rows[0] if rows else [])
    def column(name, required=False):
        matches = [i for i, value in enumerate(header) if value == name]
        if not matches and "/" in name:
            category, stat = name.split("/", 1)
            matches = [i for i, value in enumerate(header) if value.startswith(category + "/") and value.endswith("/" + stat)]
        if len(matches) == 1:
            return matches[0]
        if required:
            raise RuntimeError("CSV lacks an unambiguous metric: " + name)
        return None
    keys = ["FrameTime", "GPUTime", "GameThreadTime", "RenderThreadTime", "AbuM53/RenderedViews", "AbuM53/SelectedSplats",
            "AbuM53/SourceUploadCount", "AbuM53/SourceUploadMiB", "AbuM53/SourceCacheHits",
            "AbuM53/SourcePendingReuses", "AbuM53/SourceCacheEvictions", "AbuM53/SourceUncachedUploads",
            "AbuM53/SourceCacheResidentMiB", "AbuM53/SourceCacheReservedMiB", "AbuM53/SourceCacheEntries"]
    columns = {key: column(key, required=key in ("FrameTime", "GPUTime", "AbuM53/RenderedViews", "AbuM53/SelectedSplats")) for key in keys}
    parsed = []
    for row in rows:
        if not row or row[0] == "EVENTS" or row[0].startswith("["):
            continue
        frame = {}
        try:
            for name, index in columns.items():
                frame[name] = float(row[index] or 0) if index is not None else None
        except (ValueError, IndexError):
            continue
        if frame["FrameTime"] > 0 and all(value is None or math.isfinite(value) for value in frame.values()):
            parsed.append(frame)
    # CSV and Slate events have different start/stop boundaries. Discard exactly
    # two engine rows at each boundary; do not hide intermittent interior stalls.
    frames = parsed[2:-2]
    if len(frames) < 4:
        raise RuntimeError("CSV contains too few interior rendering frames")
    invalid = [i for i, frame in enumerate(frames) if frame["AbuM53/RenderedViews"] < 1 or
               frame["AbuM53/SelectedSplats"] not in EXPECTED_COUNTS or frame["GPUTime"] <= 0]
    result = _seq_report["csv"]
    result.update({"frame_rows": len(parsed), "boundary_rows_discarded_each_end": 2,
                   "interior_frame_rows": len(frames), "renderer_invalid_interior_rows": invalid[:16],
                   "source_cache_metrics_present": columns["AbuM53/SourceUploadCount"] is not None,
                   "rendered_views_range": [min(f["AbuM53/RenderedViews"] for f in frames), max(f["AbuM53/RenderedViews"] for f in frames)],
                   "rendered_views_note": "Explicit capture plus any realtime editor views; not a single-view presented FPS benchmark"})
    if invalid:
        raise RuntimeError("CSV interior frames lack expected splats, a rendered view, or positive aggregate GPUTime")
    for metric in ("FrameTime", "GPUTime", "GameThreadTime", "RenderThreadTime"):
        values = [frame[metric] for frame in frames if frame[metric] is not None]
        if values:
            result[metric] = _seq_summary(values)
    cache = {}
    for name in keys[6:]:
        values = [frame[name] for frame in frames if frame[name] is not None]
        if values:
            gauge = name.endswith(("ResidentMiB", "ReservedMiB", "Entries"))
            cache[name.rsplit("/", 1)[1]] = {"minimum": min(values), "maximum": max(values)} if gauge else {"total": sum(values)}
    result["source_cache_metrics"] = cache
    if (_seq_report.get("gpu_source_cache_control_matches_request") and SOURCE_CACHE_MIB > 0
            and not result["source_cache_metrics_present"]):
        raise RuntimeError("GPU source cache CVar applied but its CSV instrumentation is missing")
    if cache:
        hits = cache.get("SourceCacheHits", {}).get("total", 0)
        uploads = cache.get("SourceUploadCount", {}).get("total", 0)
        result["gpu_source_reuse_verified"] = hits > 0 and uploads == 0
        if _seq_report.get("gpu_source_cache_control_matches_request") and SOURCE_CACHE_MIB >= math.ceil(PREPARATION["total_decoded_point_bytes"] / 1024 ** 2):
            if not result["gpu_source_reuse_verified"]:
                raise RuntimeError("Configured GPU source cache did not eliminate repeated uploads during warm playback")
        if _seq_report.get("gpu_source_cache_control_matches_request"):
            over_budget = [frame for frame in frames
                           if (frame.get("AbuM53/SourceCacheResidentMiB") or 0) +
                              (frame.get("AbuM53/SourceCacheReservedMiB") or 0) > SOURCE_CACHE_MIB + .01]
            if over_budget:
                raise RuntimeError("GPU source cache resident plus reserved bytes exceeded its configured budget")
    result["thread_time_note"] = "GameThreadTime/RenderThreadTime may carry delayed scopes across capture boundaries; use validated FrameTime/GPUTime and callback summaries, not these fields, for this run's performance comparison."
    result["renderer_validated"] = True


def _seq_begin_playback():
    global _seq_phase, _seq_phase_started, _seq_playback_last_time, _seq_csv_active
    _seq_component.seek(0)
    _seq_component.set_editor_property("play_rate", 1.0)
    # Remove the capture-only override. Background CPU throttling is separately
    # disabled for this process, otherwise UE adds its own realtime=false override.
    _seq_levels.editor_set_viewport_realtime(True, _seq_levels.get_active_viewport_config_key())
    _seq_report["playback_start_misses"] = int(_seq_component.get_editor_property("streaming_misses"))
    _seq_report["playback_start_time_seconds"] = _seq_component.get_editor_property("time_seconds")
    # UE5.8 HandleCSVProfileCommand consumes only Args[0]. STARTFILE configures
    # the name and START begins capture: these must be separate console commands.
    _seq_command("CSVProfile STARTFILE=" + CSV_NAME)
    _seq_command("CSVProfile START")
    _seq_csv_active = True
    _seq_component.play()
    _seq_phase = "playback"
    _seq_phase_started = _seq_playback_last_time = time.perf_counter()


def _seq_png_stats(path):
    """Validate the PNG and count nonblack/chromatic pixels without Pillow."""
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("Capture is not PNG")
    offset, compressed, ihdr = 8, bytearray(), None
    while offset + 12 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, offset)
        end = offset + 12 + length
        if end > len(data):
            raise RuntimeError("Truncated capture PNG")
        payload = data[offset + 8:offset + 8 + length]
        if zlib.crc32(kind + payload) != struct.unpack_from(">I", data, offset + 8 + length)[0]:
            raise RuntimeError("PNG CRC mismatch")
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            if end != len(data):
                raise RuntimeError("Capture PNG has trailing bytes")
            break
        offset = end
    else:
        raise RuntimeError("Capture PNG lacks IEND")
    if ihdr is None or ihdr[:2] != (WIDTH, HEIGHT) or ihdr[2] != 8 or ihdr[3] not in (2, 6) or ihdr[6] != 0:
        raise RuntimeError("Capture must be a non-interlaced RGB/RGBA8 PNG of the requested dimensions")
    bpp = 3 if ihdr[3] == 2 else 4
    stride = WIDTH * bpp
    raw = zlib.decompress(compressed)
    if len(raw) != HEIGHT * (stride + 1):
        raise RuntimeError("PNG decoded byte count mismatch")
    previous = bytearray(stride)
    nonblack = colored = 0
    for y in range(HEIGHT):
        start = y * (stride + 1)
        method = raw[start]
        row = bytearray(raw[start + 1:start + 1 + stride])
        if method > 4:
            raise RuntimeError("Invalid PNG filter")
        for i in range(stride):
            left = row[i - bpp] if i >= bpp else 0
            above = previous[i]
            upper_left = previous[i - bpp] if i >= bpp else 0
            if method == 1:
                row[i] = (row[i] + left) & 255
            elif method == 2:
                row[i] = (row[i] + above) & 255
            elif method == 3:
                row[i] = (row[i] + ((left + above) // 2)) & 255
            elif method == 4:
                prediction = left + above - upper_left
                da, db, dc = abs(prediction - left), abs(prediction - above), abs(prediction - upper_left)
                predictor = left if da <= db and da <= dc else above if db <= dc else upper_left
                row[i] = (row[i] + predictor) & 255
        for i in range(0, stride, bpp):
            rgb = row[i:i + 3]
            nonblack += max(rgb) > 8
            colored += max(rgb) - min(rgb) > 8
        previous = row
    return {"png_bytes": len(data), "png_sha256": hashlib.sha256(data).hexdigest(),
            "nonblack_pixels": nonblack, "chromatic_pixels": colored,
            "nonblack_fraction": nonblack / (WIDTH * HEIGHT), "png_crc_valid": True}


def _seq_world_position(source):
    if AXES == "right_down_forward":
        return [source[2] * 100, source[0] * 100, -source[1] * 100]
    return [value * 100 for value in source]


def _seq_frame_camera():
    global _seq_capture_actor, _seq_capture, _seq_target
    points = []
    for frame in PREPARATION["frames"]:
        for label in ("p01", "p99"):
            points.append(_seq_world_position(frame["sample_position_percentiles"][label]))
    minimum = [min(p[a] for p in points) for a in range(3)]
    maximum = [max(p[a] for p in points) for a in range(3)]
    center = [(lo + hi) / 2 for lo, hi in zip(minimum, maximum)]
    extent = [(hi - lo) / 2 for lo, hi in zip(minimum, maximum)]
    distance = extent[0] + 1.25 * max(extent[1], extent[2] * WIDTH / HEIGHT, 10) / math.tan(math.radians(30))
    location = unreal.Vector(center[0] + distance, center[1] + distance * .12, center[2] + distance * .05)
    fov = 60.0
    if CAMERA:
        center = _seq_world_position(CAMERA["target"])
        location = unreal.Vector(*_seq_world_position(CAMERA["location"]))
        fov = float(CAMERA.get("fov", 60.0))
    rotation = unreal.MathLibrary.find_look_at_rotation(location, unreal.Vector(*center))
    key = _seq_levels.get_active_viewport_config_key()
    _seq_levels.set_level_viewport_camera_info(location, rotation, key)
    _seq_levels.set_level_viewport_fov(fov, key)
    _seq_levels.editor_set_game_view(True, key)
    _seq_levels.editor_set_viewport_realtime(False, key)
    camera = next((actor for actor in _seq_actors.get_all_level_actors() if isinstance(actor, unreal.CameraActor)), None)
    if camera is None:
        camera = _seq_actors.spawn_actor_from_class(unreal.CameraActor, location, rotation)
        camera.set_actor_label("Abu M53 Skate viewing camera")
        camera.get_component_by_class(unreal.CameraComponent).set_field_of_view(fov)
    _seq_capture_actor = _seq_actors.spawn_actor_from_class(unreal.SceneCapture2D, location, rotation, True)
    _seq_capture = _seq_capture_actor.get_component_by_class(unreal.SceneCaptureComponent2D)
    for name, value in (("capture_every_frame", False), ("capture_on_movement", False),
                        ("always_persist_rendering_state", True), ("fov_angle", fov),
                        ("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)):
        _seq_capture.set_editor_property(name, value)
    _seq_target = unreal.RenderingLibrary.create_render_target2d(
        _seq_world, WIDTH, HEIGHT, unreal.TextureRenderTargetFormat.RTF_RGBA8)
    _seq_capture.set_editor_property("texture_target", _seq_target)
    _seq_report["camera"] = {"location_cm": [location.x, location.y, location.z], "target_cm": center,
                             "horizontal_fov": fov, "source_camera_override": CAMERA,
                             "framing_basis": "explicit source-space view" if CAMERA else "sample p01/p99; no splats cropped"}


def _seq_begin_seek(frame, reloaded=False, warm=False):
    global _seq_frame, _seq_phase, _seq_phase_started, _seq_settle_ticks, _seq_reload
    _seq_frame, _seq_reload = frame, reloaded
    _seq_component.pause()
    _seq_component.seek(float(SEQUENCE["frames"][frame]["time_seconds"]))
    _seq_phase, _seq_phase_started, _seq_settle_ticks = "warm_seek" if warm else "seek", time.perf_counter(), 0
    unreal.log(f"ABUM53_SEQUENCE seeking frame {frame}, reloaded={reloaded}")


def _seq_reopen():
    global _seq_world, _seq_actor, _seq_component, _seq_asset, _seq_callback
    # Save/load progress can pump nested Slate ticks. Suspend the delegate while
    # worlds are serialized/replaced so a nested tick cannot repeat the reopen.
    if _seq_callback is not None:
        unreal.unregister_slate_post_tick_callback(_seq_callback)
        _seq_callback = None
    _seq_component.pause()
    _seq_component.seek(0)
    # Explicit SaveMap is synchronous and uses the known owned destination. The
    # LevelEditorSubsystem shortcut adds a separate source-control checkout flow.
    if not unreal.EditorLoadingAndSavingUtils.save_map(_seq_world, _seq_report["map"]):
        raise RuntimeError("Failed to save isolated Skate map")
    # The standalone index is saved by the importer. Reopen the level through an
    # empty transient map so this checks serialized actor/component references.
    if unreal.EditorLoadingAndSavingUtils.new_blank_map(False) is None:
        raise RuntimeError("Could not open transient map for reload check")
    if not _seq_levels.load_level(_seq_report["map"]):
        raise RuntimeError("Could not reload saved Skate map")
    _seq_world = _seq_editor.get_editor_world()
    found = [actor for actor in _seq_actors.get_all_level_actors() if isinstance(actor, unreal.AbuM53Actor)]
    if len(found) != 1:
        raise RuntimeError("Reloaded map must contain its one test splat actor")
    _seq_actor = found[0]
    _seq_component = _seq_actor.get_editor_property("splat_component")
    _seq_asset = _seq_component.get_editor_property("asset")
    if _seq_asset is None or _seq_asset.get_frame_count() != FRAME_COUNT or not _seq_asset.get_editor_property("external_stream"):
        raise RuntimeError("Saved external sequence asset reference did not survive map reload")
    _seq_report["saved_asset_reference_preserved"] = True
    _seq_frame_camera()
    _seq_begin_seek(0, reloaded=True)
    _seq_callback = unreal.register_slate_post_tick_callback(_seq_tick)


def _seq_finish(error=None):
    global _seq_callback, _seq_csv_active
    if _seq_csv_active:
        _seq_command("CSVProfile STOP")
        _seq_csv_active = False
    if _seq_component is not None:
        _seq_component.pause()
    if _seq_performance_settings is not None and _seq_original_background_throttle is not None:
        _seq_performance_settings.set_editor_property("bThrottleCPUWhenNotForeground", _seq_original_background_throttle)
        _seq_report["editor_background_throttle_restored"] = True
    if error:
        _seq_report["error"] = error
        unreal.log_error(error)
    else:
        _seq_report["passed"] = True
    _seq_report["total_wall_seconds"] = time.perf_counter() - _seq_started
    _seq_write()
    if _seq_callback is not None:
        unreal.unregister_slate_post_tick_callback(_seq_callback)
        _seq_callback = None
    unreal.log("ABUM53_SEQUENCE_RESULT " + str(REPORT_PATH))
    if QUIT:
        unreal.SystemLibrary.quit_editor()


def _seq_tick(_delta):
    """Progress dialogs may pump Slate recursively; permit one active tick only."""
    global _seq_in_tick
    if _seq_in_tick or _seq_callback is None:
        return
    _seq_in_tick = True
    try:
        _seq_tick_impl(_delta)
    finally:
        _seq_in_tick = False


def _seq_tick_impl(_delta):
    global _seq_phase, _seq_phase_started, _seq_settle_ticks, _seq_ticks, _seq_warm_cursor
    global _seq_csv_active, _seq_playback_last_time, _seq_csv_signature
    try:
        now = time.perf_counter()
        _seq_ticks += 1
        if _seq_phase == "csv_flush":
            finalized, _seq_csv_signature, pending_error = _seq_csv_completion(CSV_PATH, _seq_csv_signature)
            if pending_error:
                _seq_report["csv"]["last_pending_read_error"] = pending_error
            if finalized:
                _seq_report["csv"]["finalized"] = True
                try:
                    _seq_analyze_csv()
                except OSError as pending_error:
                    _seq_report["csv"]["finalized"] = False
                    _seq_report["csv"]["last_pending_read_error"] = str(pending_error)
                    if now - _seq_phase_started > 120:
                        raise RuntimeError("Playback CSV remained unavailable for 120 seconds") from pending_error
                    return
                _seq_write()
                _seq_reopen()
            elif now - _seq_phase_started > 120:
                raise RuntimeError("Playback CSV did not finalize within 120 seconds")
            return
        _seq_capture.capture_scene()
        error = _seq_component.get_editor_property("last_streaming_error")
        if error:
            raise RuntimeError("Streaming error: " + error)
        resident = int(_seq_component.get_editor_property("streaming_resident_bytes"))
        if resident > CACHE_MIB * 1024 ** 2:
            raise RuntimeError("Streaming cache exceeded configured resident-byte budget")
        requested = _seq_component.get_current_frame_index()
        displayed = _seq_component.get_displayed_frame_index()
        count = _seq_component.get_displayed_splat_count()
        if _seq_phase in ("seek", "warm_seek"):
            if displayed == _seq_frame and count == EXPECTED_COUNTS[_seq_frame]:
                _seq_settle_ticks += 1
            else:
                _seq_settle_ticks = 0
            if _seq_settle_ticks >= 8:
                record = {"frame_index": _seq_frame, "requested_frame": requested, "displayed_frame": displayed,
                          "displayed_splats": count, "wall_seconds_to_ready_capture": now - _seq_phase_started,
                          "resident_bytes": resident, "streaming_misses": int(_seq_component.get_editor_property("streaming_misses"))}
                if _seq_reload:
                    _seq_report["reload_checks"].append(record)
                    _seq_finish()
                    return
                warm = _seq_phase == "warm_seek"
                prefix = f"warm_seek_{_seq_warm_cursor:02d}_" if warm else ""
                path = OUTPUT / (prefix + f"frame_{_seq_frame:04d}.png")
                options = unreal.ImageWriteOptions(format=unreal.DesiredImageFormat.PNG, async_=False, overwrite_file=False)
                unreal.ImageWriteBlueprintLibrary.export_to_disk(_seq_target, str(path), options)
                record.update(_seq_png_stats(path))
                record["capture"] = str(path)
                if record["nonblack_pixels"] < 64 or record["chromatic_pixels"] < 32:
                    raise RuntimeError("Capture is blank or lacks colored splat pixels")
                _seq_report["warm_seek_checks" if warm else "frame_checks"].append(record)
                _seq_write()
                if warm:
                    _seq_warm_cursor += 1
                    if _seq_warm_cursor < len(_seq_warm_targets):
                        _seq_begin_seek(_seq_warm_targets[_seq_warm_cursor], warm=True)
                    else:
                        _seq_begin_playback()
                elif _seq_frame + 1 < FRAME_COUNT:
                    _seq_begin_seek(_seq_frame + 1)
                else:
                    if FRAME_COUNT > 1 and len({entry["png_sha256"] for entry in _seq_report["frame_checks"]}) < 2:
                        raise RuntimeError("Different source frames produced identical capture pixels")
                    _seq_warm_cursor = 0
                    _seq_begin_seek(_seq_warm_targets[0], warm=True)
            elif now - _seq_phase_started > TIMEOUT:
                raise RuntimeError(f"Frame {_seq_frame} did not become ready within {TIMEOUT}s (displayed {displayed}, count {count})")
        elif _seq_phase == "playback":
            _seq_playback_seen.add(displayed)
            _seq_playback_samples.append({"elapsed_seconds": now - _seq_phase_started,
                                          "callback_interval_ms": (now - _seq_playback_last_time) * 1000,
                                          "requested": requested, "displayed": displayed, "splats": count,
                                          "native_time_seconds": _seq_component.get_editor_property("time_seconds")})
            _seq_playback_last_time = now
            if displayed < 0 or count != EXPECTED_COUNTS[displayed]:
                raise RuntimeError("Warm playback displayed an empty or incomplete frame")
            if now - _seq_phase_started >= 10:
                _seq_component.pause()
                _seq_command("CSVProfile STOP")
                _seq_csv_active = False
                _seq_report["playback_observations"] = _seq_playback_samples
                _seq_report["playback_seen_frames"] = sorted(_seq_playback_seen)
                _seq_report["playback_end_misses"] = int(_seq_component.get_editor_property("streaming_misses"))
                if len({sample["native_time_seconds"] for sample in _seq_playback_samples}) < 2:
                    raise RuntimeError("Native playback time did not advance; enable the editor viewport's base Realtime setting")
                if _seq_playback_seen != set(range(FRAME_COUNT)):
                    raise RuntimeError("Warm playback did not display every source frame")
                if _seq_report["playback_end_misses"] != _seq_report["playback_start_misses"]:
                    raise RuntimeError("Three-frame warm playback requested uncached frame decoding")
                _seq_report["callback_timing"] = _seq_summary([sample["callback_interval_ms"] for sample in _seq_playback_samples[1:]])
                _seq_report["callback_timing"]["initial_interval_discarded"] = True
                _seq_report["callback_timing"]["png_processing_excluded"] = True
                _seq_write()
                _seq_phase, _seq_phase_started = "csv_flush", time.perf_counter()
    except Exception:
        _seq_finish(traceback.format_exc())


def _seq_setup():
    global _seq_levels, _seq_editor, _seq_actors, _seq_world, _seq_actor, _seq_component, _seq_asset, _seq_callback
    global _seq_performance_settings, _seq_original_background_throttle
    if SEQUENCE.get("storage") != "external":
        raise RuntimeError("This QA run requires an explicit storage:external manifest")
    if AXES not in ("raw_xyz", "right_down_forward"):
        raise RuntimeError("ABUM53_SEQUENCE_AXES must be raw_xyz or right_down_forward")
    if unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages():
        raise RuntimeError("Existing map has unsaved changes; run QA in a fresh editor process")
    # This non-Blueprint UDeveloperSettings class is not a global unreal Python
    # type in UE5.8. Resolve its reflected class by the verified native module path.
    performance_class = unreal.load_class(None, "/Script/UnrealEd.EditorPerformanceSettings")
    if performance_class is None:
        raise RuntimeError("Could not resolve native EditorPerformanceSettings class")
    _seq_performance_settings = unreal.get_default_object(performance_class)
    # Use the native FProperty name because a non-exported class may use a base
    # Python wrapper without the generated snake_case property-name mapping.
    _seq_original_background_throttle = _seq_performance_settings.get_editor_property("bThrottleCPUWhenNotForeground")
    _seq_performance_settings.set_editor_property("bThrottleCPUWhenNotForeground", False)
    _seq_report["editor_background_throttle_original"] = _seq_original_background_throttle
    _seq_report["editor_background_throttle_temporarily_disabled"] = True
    _seq_levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    _seq_editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    _seq_actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not _seq_levels.new_level(_seq_report["map"]):
        raise RuntimeError("Could not create isolated Skate QA map")
    _seq_world = _seq_editor.get_editor_world()
    task = unreal.AssetImportTask()
    task.filename = str(MANIFEST)
    task.destination_path = DESTINATION
    task.destination_name = "SkateSequence"
    task.automated, task.replace_existing, task.save = True, False, True
    started = time.perf_counter()
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    _seq_report["index_import_and_save_seconds"] = time.perf_counter() - started
    paths = list(task.imported_object_paths)
    if len(paths) != 1:
        raise RuntimeError("External manifest import did not create exactly one asset")
    _seq_asset = unreal.load_asset(paths[0])
    _seq_report["asset_object"] = paths[0]
    if _seq_asset is None or _seq_asset.get_frame_count() != FRAME_COUNT or not _seq_asset.get_editor_property("external_stream"):
        raise RuntimeError("Importer did not produce the expected external frame index")
    _seq_actor = _seq_actors.spawn_actor_from_class(unreal.AbuM53Actor, unreal.Vector(0, 0, 0))
    _seq_actor.set_actor_label("Abu M53 Skate independent PLY sequence")
    _seq_component = _seq_actor.get_editor_property("splat_component")
    for name, value in (("stream_external_sequences", True), ("streaming_cache_mi_b", CACHE_MIB),
                        ("units_to_centimeters", 100.0), ("backend", unreal.AbuM53Backend.GPU),
                        ("max_visible_splats", max(EXPECTED_COUNTS)), ("enable_crop", False),
                        ("interpolate_stable_ids", False), ("loop", True)):
        _seq_component.set_editor_property(name, value)
    if AXES == "right_down_forward":
        _seq_component.set_editor_property("source_axes", unreal.AbuM53SourceAxes.RIGHT_UP_BACK)
        _seq_actor.set_actor_rotation(unreal.Rotator(180, 0, 0), False)
    else:
        _seq_component.set_editor_property("source_axes", unreal.AbuM53SourceAxes.RAW_XYZ)
    _seq_component.set_asset(_seq_asset)
    for command in ("r.AbuM53.Enable 1", "r.AbuM53.Backend 1", "r.AbuM53.Tiles 1",
                    f"r.AbuM53.SourceCacheMiB {SOURCE_CACHE_MIB}", "csv.CompressionMode 0", "CSVCategory AbuM53 enable",
                    f"r.AbuM53.MaxSplats {max(EXPECTED_COUNTS)}", "r.VSync 0", "r.VSyncEditor 0",
                    "t.MaxFPS 60", "t.IdleWhenNotForeground 0", "r.ScreenPercentage 100"):
        _seq_command(command)
    readback = unreal.SystemLibrary.get_console_variable_int_value("r.AbuM53.SourceCacheMiB")
    _seq_report["gpu_source_cache_mib_readback"] = readback
    _seq_report["gpu_source_cache_control_matches_request"] = readback == SOURCE_CACHE_MIB
    _seq_report["gpu_source_cache_control_note"] = "An older baseline renderer may not expose this CVar; inspect CSV metric availability too."
    _seq_frame_camera()
    _seq_begin_seek(0)
    _seq_write()
    _seq_callback = unreal.register_slate_post_tick_callback(_seq_tick)


try:
    _seq_setup()
except Exception:
    _seq_finish(traceback.format_exc())

"""Exercise CSV validation without importing Unreal or launching an editor.

Helpers are extracted from the real QA script, so these tests execute the same
polling/parser used in UE. CSV shape follows UE5.8's observed duplicated EVENTS
header and [HasHeaderRowAtEnd] metadata row. No private CSV data is committed.
"""
import ast
import csv
import ctypes
import math
import os
from pathlib import Path
import statistics
import tempfile
import types
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("ue_sequence_validation.py")
HELPERS = {"_seq_summary", "_seq_csv_completion", "_seq_analyze_csv", "_seq_tick", "_seq_reopen"}
TREE = ast.parse(SCRIPT.read_text(encoding="utf-8"))
CODE = compile(ast.Module(body=[node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name in HELPERS],
                          type_ignores=[]), str(SCRIPT), "exec")


class SequenceCSVTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "capture.csv"
        self.report = {"csv": {}, "gpu_source_cache_control_matches_request": False}
        self.scope = {"csv": csv, "math": math, "statistics": statistics, "CSV_PATH": self.path,
                      "EXPECTED_COUNTS": [3_000_000] * 3, "SOURCE_CACHE_MIB": 3072,
                      "PREPARATION": {"total_decoded_point_bytes": 2_304_000_000}, "_seq_report": self.report}
        exec(CODE, self.scope)

    def tearDown(self):
        self.temp.cleanup()

    def write_csv(self, cache=False, interior_uploads=0, interior_views=1, count=3_000_000,
                  resident=2197.3, reserved=0, footer=True, rows=20):
        header = ["EVENTS", "FrameTime", "GPUTime", "AbuM53/RenderedViews", "AbuM53/SelectedSplats"]
        if cache:
            header += ["AbuM53/SourceUploadCount", "AbuM53/SourceUploadMiB", "AbuM53/SourceCacheHits",
                       "AbuM53/SourcePendingReuses", "AbuM53/SourceCacheEvictions", "AbuM53/SourceUncachedUploads",
                       "AbuM53/SourceCacheResidentMiB", "AbuM53/SourceCacheReservedMiB", "AbuM53/SourceCacheEntries"]
        with self.path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            for i in range(rows):
                row = ["", 16 + i, 12 + i / 10, interior_views if i == 5 else 2, count]
                if cache:
                    row += [interior_uploads if i == 5 else 0, interior_uploads * 732.4 if i == 5 else 0,
                            2, 0, 0, 0, resident, reserved, 3]
                writer.writerow(row)
            writer.writerow(header)
            if footer:
                writer.writerow(["[HasHeaderRowAtEnd]", "1", "[Platform]", "Windows", "[captureduration]", "10.0"])

    def test_legacy_csv_validates_renderer_and_frame_timings_without_cache_claim(self):
        self.write_csv()
        self.scope["_seq_analyze_csv"]()
        result = self.report["csv"]
        self.assertTrue(result["renderer_validated"])
        self.assertFalse(result["source_cache_metrics_present"])
        self.assertEqual(result["interior_frame_rows"], 16)
        self.assertAlmostEqual(result["FrameTime"]["mean_ms"], 25.5)
        self.assertAlmostEqual(result["GPUTime"]["mean_ms"], 12.95)
        self.assertEqual(result["rendered_views_range"], [1, 2])

    def test_retained_cache_requires_hits_and_zero_interior_uploads(self):
        self.write_csv(cache=True)
        self.report["gpu_source_cache_control_matches_request"] = True
        self.scope["_seq_analyze_csv"]()
        self.assertTrue(self.report["csv"]["gpu_source_reuse_verified"])
        self.assertEqual(self.report["csv"]["source_cache_metrics"]["SourceCacheHits"]["total"], 32)
        self.write_csv(cache=True, interior_uploads=1)
        with self.assertRaisesRegex(RuntimeError, "repeated uploads"):
            self.scope["_seq_analyze_csv"]()

    def test_disabled_cache_allows_upload_baseline_and_does_not_claim_reuse(self):
        self.scope["SOURCE_CACHE_MIB"] = 0
        self.report["gpu_source_cache_control_matches_request"] = True
        self.write_csv(cache=True, interior_uploads=1, resident=0)
        self.scope["_seq_analyze_csv"]()
        self.assertFalse(self.report["csv"]["gpu_source_reuse_verified"])

    def test_renderer_missing_splats_or_views_is_rejected(self):
        for kwargs in ({"interior_views": 0}, {"count": 2_000_000}):
            self.write_csv(**kwargs)
            with self.assertRaisesRegex(RuntimeError, "expected splats"):
                self.scope["_seq_analyze_csv"]()

    def test_applied_cache_missing_counters_or_over_budget_is_rejected(self):
        self.report["gpu_source_cache_control_matches_request"] = True
        self.write_csv()
        with self.assertRaisesRegex(RuntimeError, "instrumentation is missing"):
            self.scope["_seq_analyze_csv"]()
        self.write_csv(cache=True, resident=3000, reserved=100)
        with self.assertRaisesRegex(RuntimeError, "exceeded its configured budget"):
            self.scope["_seq_analyze_csv"]()

    def test_short_capture_is_rejected(self):
        self.write_csv(rows=6)
        with self.assertRaisesRegex(RuntimeError, "too few"):
            self.scope["_seq_analyze_csv"]()

    def test_missing_or_incomplete_file_stays_pending_then_finalizes(self):
        poll = self.scope["_seq_csv_completion"]
        ready, signature, error = poll(self.path, None)
        self.assertFalse(ready)
        self.assertIsNotNone(error)
        self.write_csv(footer=False)
        ready, signature, _ = poll(self.path, signature)
        self.assertFalse(ready)
        ready, signature, _ = poll(self.path, signature)
        self.assertFalse(ready)
        self.write_csv(footer=True)
        ready, signature, _ = poll(self.path, signature)
        self.assertFalse(ready, "A changed file must stabilize for another tick")
        ready, signature, error = poll(self.path, signature)
        self.assertTrue(ready)
        self.assertIsNone(error)

    def test_sharing_violation_is_pending_and_retried(self):
        self.write_csv()
        poll = self.scope["_seq_csv_completion"]
        _, signature, _ = poll(self.path, None)
        with mock.patch.object(Path, "open", side_effect=PermissionError("sharing violation")):
            ready, same_signature, error = poll(self.path, signature)
        self.assertFalse(ready)
        self.assertEqual(signature, same_signature)
        self.assertIn("sharing violation", error)
        self.assertTrue(poll(self.path, signature)[0])

    @unittest.skipUnless(os.name == "nt", "Real Windows exclusive writer regression")
    def test_real_windows_exclusive_writer_handle_retries_after_close(self):
        self.write_csv()
        poll = self.scope["_seq_csv_completion"]
        _, signature, _ = poll(self.path, None)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel32.CreateFileW
        create.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                           ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        create.restype = ctypes.c_void_p
        close = kernel32.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close.restype = ctypes.c_int
        handle = create(str(self.path), 0x40000000, 0, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value, ctypes.get_last_error())
        try:
            ready, pending_signature, error = poll(self.path, signature)
            self.assertFalse(ready)
            self.assertIsNotNone(error)
            self.assertEqual(pending_signature, signature)
        finally:
            close(handle)
        self.assertTrue(poll(self.path, signature)[0])

    def test_nested_slate_ticks_do_not_repeat_work(self):
        self.scope.update(_seq_callback="active", _seq_in_tick=False)
        events = []
        def implementation(delta):
            events.append(delta)
            self.scope["_seq_tick"](99)
        self.scope["_seq_tick_impl"] = implementation
        self.scope["_seq_tick"](1)
        self.scope["_seq_tick"](2)
        self.assertEqual(events, [1, 2])
        self.assertFalse(self.scope["_seq_in_tick"])
        self.scope["_seq_callback"] = None
        self.scope["_seq_tick"](3)
        self.assertEqual(events, [1, 2], "Completed/unregistered callbacks must remain inert")

    def test_tick_guard_resets_after_exception(self):
        self.scope.update(_seq_callback="active", _seq_in_tick=False)
        self.scope["_seq_tick_impl"] = mock.Mock(side_effect=RuntimeError("test failure"))
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            self.scope["_seq_tick"](0)
        self.assertFalse(self.scope["_seq_in_tick"])

    def test_save_reload_suspends_callback_and_saves_only_owned_map(self):
        events = []
        owned_map = "/Game/AbuM53SkateQA/Test/SkateSequenceQA"
        old_world, new_world = object(), object()
        old_component, new_component, asset = mock.Mock(), mock.Mock(), mock.Mock()
        asset.get_frame_count.return_value = 3
        asset.get_editor_property.return_value = True
        new_component.get_editor_property.return_value = asset
        class FakeActor:
            def get_editor_property(self, name):
                return new_component
        def unregister(handle):
            events.append(("unregister", handle))
        def save_map(world, path):
            events.append(("save", world, path))
            self.scope["_seq_tick"](99)  # A real UE save may pump nested Slate ticks.
            self.assertIsNone(self.scope["_seq_callback"])
            return True
        def blank(save_existing):
            events.append(("blank", save_existing))
            return object()
        def load(path):
            events.append(("load", path))
            return True
        def register(callback):
            events.append(("register", callback))
            return "new-handle"
        unreal_stub = types.SimpleNamespace(
            AbuM53Actor=FakeActor, unregister_slate_post_tick_callback=unregister,
            register_slate_post_tick_callback=register,
            EditorLoadingAndSavingUtils=types.SimpleNamespace(save_map=save_map, new_blank_map=blank))
        self.scope.update(
            unreal=unreal_stub, FRAME_COUNT=3, _seq_callback="old-handle", _seq_in_tick=False,
            _seq_world=old_world, _seq_component=old_component, _seq_report={"map": owned_map},
            _seq_levels=types.SimpleNamespace(load_level=load),
            _seq_editor=types.SimpleNamespace(get_editor_world=lambda: new_world),
            _seq_actors=types.SimpleNamespace(get_all_level_actors=lambda: [FakeActor()]),
            _seq_frame_camera=mock.Mock(), _seq_begin_seek=mock.Mock())
        self.scope["_seq_tick_impl"] = lambda delta: self.scope["_seq_reopen"]()
        self.scope["_seq_tick"](0)
        self.assertEqual([event[0] for event in events], ["unregister", "save", "blank", "load", "register"])
        self.assertEqual(events[1], ("save", old_world, owned_map))
        self.assertEqual(events[2], ("blank", False))
        self.assertEqual(events[3], ("load", owned_map))
        self.assertIs(self.scope["_seq_world"], new_world)
        self.assertEqual(self.scope["_seq_callback"], "new-handle")
        self.scope["_seq_begin_seek"].assert_called_once_with(0, reloaded=True)
        self.assertTrue(self.scope["_seq_report"]["saved_asset_reference_preserved"])


if __name__ == "__main__":
    unittest.main()

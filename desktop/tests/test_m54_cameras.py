# SPDX-License-Identifier: Apache-2.0
"""Independent camera coordinate, interpolation and project validation checks."""
import json
import tempfile
import unittest
import sys
import os
import time
from unittest.mock import patch
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from abu_m54_cameras import (CameraPose, CameraKeyframe, CameraPath, RenderSettings,
                             save_camera_project, load_camera_project)


class CameraTests(unittest.TestCase):
    def test_camera_axes_and_projection(self):
        camera = CameraPose("Identity", [10, 20, 30], [1, 0, 0, 0], 60)
        view = camera.view_matrix()
        # Independent expectations: world forward +Z becomes OpenGL -Z;
        # world camera-down +Y becomes negative screen Y.
        np.testing.assert_allclose(view @ [10, 20, 35, 1], [0, 0, -5, 1])
        np.testing.assert_allclose(view @ [11, 22, 35, 1], [1, -2, -5, 1])
        projection = camera.projection_matrix(1920, 1080, .1, 100)
        clip = projection @ view @ [11, 22, 35, 1]
        self.assertGreater(clip[0] / clip[3], 0)
        self.assertLess(clip[1] / clip[3], 0)
        for depth, expected in ((.1, -1), (100, 1)):
            point = projection @ [0, 0, -depth, 1]
            self.assertAlmostEqual(point[2] / point[3], expected)

    def test_large_world_rebasing_and_rotation(self):
        position = np.array([6.3e6, -4.2e6, 8.5e6])
        camera = CameraPose.from_euler("World", position, [25, -81, 162], 47)
        origin, scale = position + [1, -2, 3], 127.0
        view = camera.view_matrix(origin, scale)
        target = position + camera.rotation_matrix @ [2, 3, 5]
        local = (target - origin) / scale
        np.testing.assert_allclose((view @ [*local, 1])[:3], np.array([2, -3, -5])/scale, atol=1e-11)
        np.testing.assert_allclose(camera.rotation_matrix.T @ camera.rotation_matrix, np.eye(3), atol=1e-14)
        self.assertAlmostEqual(np.linalg.det(camera.rotation_matrix), 1)
        with self.assertRaises(ValueError):
            camera.position[0] = 0

    def test_shortest_arc_and_endpoints(self):
        first = CameraPose.from_euler("A", [0, 0, 0], [0, 0, 170], 40)
        last = CameraPose.from_euler("B", [2, 4, 6], [0, 0, -170], 60)
        path = CameraPath((CameraKeyframe(0, first), CameraKeyframe(2, last)))
        middle = path.sample(1)
        np.testing.assert_allclose(middle.position, [1, 2, 3])
        np.testing.assert_allclose(middle.rotation_matrix, np.diag([-1, -1, 1]), atol=1e-14)
        self.assertEqual(middle.fov_y_degrees, 50)
        self.assertIs(path.sample(-1), first)
        self.assertIs(path.sample(9), last)

    def test_smooth_time_aware_continuity(self):
        keys = tuple(CameraKeyframe(t, CameraPose(str(t), xyz, [1, 0, 0, 0]))
                     for t, xyz in ((0, [0, 0, 0]), (1, [1, 2, 0]), (4, [5, 3, 1]), (6, [6, 5, 2])))
        path = CameraPath(keys, "smooth")
        for key in keys:
            np.testing.assert_allclose(path.sample(key.time_seconds).position, key.camera.position)
        epsilon = 1e-5
        before = (path.sample(1).position-path.sample(1-epsilon).position)/epsilon
        after = (path.sample(1+epsilon).position-path.sample(1).position)/epsilon
        np.testing.assert_allclose(before, after, atol=1e-4)
        for time in np.linspace(0, 6, 30):
            matrix = path.sample(time).rotation_matrix
            np.testing.assert_allclose(matrix.T @ matrix, np.eye(3), atol=1e-14)

    def test_project_roundtrip_full_pose(self):
        camera = CameraPose.from_euler("Arbitrary", [10, -3, 7], [32, 61, -149], 71)
        path = CameraPath((CameraKeyframe(0, camera), CameraKeyframe(1, camera)), "smooth")
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "project.json"
            save_camera_project(target, [camera], path)
            cameras, loaded = load_camera_project(target)
            np.testing.assert_allclose(cameras[0].c2w_matrix, camera.c2w_matrix, atol=1e-14)
            self.assertEqual(loaded.to_dict(), path.to_dict())
            self.assertFalse(target.with_suffix(".json.tmp").exists())
            target.write_text(json.dumps({"schema": "bad", "cameras": []}))
            with self.assertRaises(ValueError):
                load_camera_project(target)

    def test_reject_invalid_pose_path_and_settings(self):
        extreme = CameraPose("Huge quaternion", [0, 0, 0], [1e300, 1e300, 0, 0])
        self.assertAlmostEqual(np.linalg.norm(extreme.quaternion_wxyz), 1)
        for position, quaternion, fov in (([np.nan, 0, 0], [1, 0, 0, 0], 45),
                                           ([0, 0, 0], [0, 0, 0, 0], 45),
                                           ([0, 0, 0], [1, 0, 0, 0], 180)):
            with self.assertRaises(ValueError):
                CameraPose("bad", position, quaternion, fov)
        camera = CameraPose("A", [0, 0, 0], [1, 0, 0, 0])
        for times in ((1,), (0, 0), (0, -1)):
            with self.assertRaises(ValueError):
                CameraPath(tuple(CameraKeyframe(t, camera) for t in times))
        for kwargs in ({"width": 1}, {"fps": float("inf")}, {"format": "exe"}, {"near": 100, "far": 10},
                       {"width": 1921, "format": "mp4"}, {"width": 8192, "height": 8192},
                       {"background": [1, 0, -1]}, {"supersampling": 3}):
            with self.assertRaises(ValueError):
                RenderSettings(**kwargs)
        settings = RenderSettings(width=3840, height=2160, supersampling=2)
        self.assertEqual(RenderSettings.from_dict(settings.to_dict()), settings)


@unittest.skipUnless(sys.platform == "win32", "Desktop Tk smoke test on Windows")
class RenderStudioTests(unittest.TestCase):
    def test_launch_failures_restore_controls_and_clean_snapshot(self):
        import tkinter as tk
        from abu_m54_render_ui import open_render_studio
        root = tk.Tk()
        root.withdraw()
        class Viewer(tk.Frame):
            closed = False
            data = {"source": "synthetic"}
            comparison = None
            render_studio = None
            def get_render_camera(self, name="Camera"):
                return CameraPose(name, [0, 0, 0], [1, 0, 0, 0])
            def request(self):
                pass
        viewer = Viewer(root)
        studio = open_render_studio(viewer)
        try:
            with tempfile.TemporaryDirectory() as folder:
                studio.render_vars["output"].set(folder)
                with patch("abu_m54_render_ui.messagebox.showerror") as error:
                    with patch("abu_m54_render_ui.tempfile.TemporaryDirectory", side_effect=OSError("Disk full")):
                        studio.start_render()
                    self.assertTrue(error.called)
                    self.assertFalse(studio.busy)
                    self.assertEqual(str(studio.render_button["state"]), "normal")
                    self.assertEqual(str(studio.cancel_button["state"]), "disabled")
                snapshot = tempfile.TemporaryDirectory(dir=folder)
                snapshot_path = Path(snapshot.name)
                with patch("abu_m54_render_ui.messagebox.showerror") as error:
                    with patch("abu_m54_render_ui.tempfile.TemporaryDirectory", return_value=snapshot), \
                         patch.object(studio, "after", side_effect=tk.TclError("Callback setup failed")):
                        studio.start_render()
                    self.assertTrue(error.called)
                    self.assertFalse(studio.busy)
                    self.assertIsNone(studio.poll_job)
                    self.assertIsNone(studio.worker)
                    self.assertFalse(snapshot_path.exists())
                    self.assertEqual(str(studio.render_button["state"]), "normal")
                snapshot = tempfile.TemporaryDirectory(dir=folder)
                snapshot_path = Path(snapshot.name)
                with patch("abu_m54_render_ui.messagebox.showerror") as error:
                    with patch("abu_m54_render_ui.tempfile.TemporaryDirectory", return_value=snapshot), \
                         patch("abu_m54_render_ui.threading.Thread.start", side_effect=RuntimeError("Cannot launch thread")):
                        studio.start_render()
                    self.assertTrue(error.called)
                    self.assertFalse(studio.busy)
                    self.assertIsNone(studio.poll_job)
                    self.assertIsNone(studio.worker)
                    self.assertIsNone(studio.cancel_file)
                    self.assertFalse(snapshot_path.exists())
                    self.assertEqual(str(studio.render_button["state"]), "normal")
                    self.assertEqual(str(studio.cancel_button["state"]), "disabled")
        finally:
            studio.close()
            root.destroy()

    def test_camera_keyframe_edit_preview_and_lifecycle(self):
        import tkinter as tk
        from abu_m54_render_ui import open_render_studio
        root = tk.Tk()
        root.withdraw()
        class Viewer(tk.Frame):
            closed = False
            data = {"source": "synthetic"}
            comparison = None
            render_studio = None
            pose = CameraPose("View", [1, 2, 3], [1, 0, 0, 0])
            def get_render_camera(self, name="Camera"):
                return CameraPose(name, self.pose.position, self.pose.quaternion_wxyz, self.pose.fov_y_degrees)
            def look_through_render_camera(self, camera):
                self.pose = camera
            def request(self):
                pass
        viewer = Viewer(root)
        studio = open_render_studio(viewer)
        try:
            self.assertIs(open_render_studio(viewer), studio)
            studio.add_camera()
            root.update_idletasks()
            self.assertEqual(len(studio.cameras), 1)
            studio.camera_vars["x"].set("9")
            studio.apply_camera()
            self.assertEqual(viewer.pose.position[0], 9)
            studio.add_key(False)
            studio.key_time.set("3")
            viewer.pose = CameraPose("Later", [20, 4, 5], [1, 0, 0, 0])
            studio.add_key(True)
            self.assertEqual(studio.make_path().duration, 3)
            studio.scrub("1.5")
            np.testing.assert_allclose(viewer.pose.position, [14.5, 3, 4])
            geometry = studio.preview_geometry()
            self.assertIs(geometry, studio.preview_geometry())
            self.assertEqual(len(geometry["cameras"]), 1)
            self.assertGreater(len(geometry["path"]), 2)
            self.assertEqual(studio.settings().width, 1920)
            studio.delete_camera()
            self.assertEqual(len(studio.cameras), 0)
            self.assertEqual(len(studio.keyframes), 2)
            studio.close()
            studio = open_render_studio(viewer)
            self.assertEqual(len(studio.keyframes), 2)
            self.assertEqual(studio.make_path().duration, 3)
        finally:
            studio.close()
            self.assertIsNone(viewer.render_studio)
            root.destroy()

    @unittest.skipUnless(os.environ.get("ABU_TEST_NATIVE_GPU") == "1", "Opt-in actual native export test")
    def test_native_studio_worker_render_progress_and_cancel(self):
        import tkinter as tk
        from PIL import Image
        from abu_m54 import from_records
        from abu_m54_host import ViewerHost
        from abu_m54_native import M54NativeViewer
        from benchmark_m54_gaussian import synthetic_asset
        from abu_m54_render_ui import open_render_studio
        root = tk.Tk()
        root.withdraw()
        root.geometry("640x480")
        viewer = None
        studio = None
        with tempfile.TemporaryDirectory() as folder:
            try:
                viewer = M54NativeViewer(ViewerHost(root), root, compact=True)
                viewer.pack(fill="both", expand=True)
                root.update_idletasks()
                asset = synthetic_asset(100)
                points, colors = asset.preview()
                scene = from_records(dict(points=points, colors=colors, cameras=[], path="synthetic-render-ui"))
                scene["gaussians"] = asset
                scene["gaussian_transform"] = np.eye(4)
                viewer.set_data(scene)
                camera = CameraPose.from_euler("Render", [0, 0, 4], [180, 0, 0], 55)
                viewer.look_through_render_camera(camera)
                actual = viewer.get_render_camera("Roundtrip")
                np.testing.assert_allclose(actual.c2w_matrix, camera.c2w_matrix, atol=1e-12)
                studio = open_render_studio(viewer)
                studio.withdraw()
                studio.add_camera()
                studio.render_vars["width"].set("128")
                studio.render_vars["height"].set("96")
                studio.render_vars["output"].set(folder)
                with patch("abu_m54_render_ui.messagebox.showerror") as errors:
                    studio.start_render()
                    deadline = time.monotonic()+40
                    while studio.busy and time.monotonic() < deadline:
                        root.update()
                        time.sleep(.01)
                    self.assertFalse(studio.busy, "Export worker did not finish")
                    self.assertFalse(errors.called, errors.call_args)
                    self.assertIsNotNone(studio.last_output)
                    self.assertIn("complete", studio.status.get().lower())
                    pngs = list(Path(studio.last_output).glob("*.png"))
                    self.assertEqual(len(pngs), 1)
                    with Image.open(pngs[0]) as image:
                        self.assertEqual(image.size, (128, 96))
                        self.assertGreater(np.asarray(image).std(), 1)
                    self.assertEqual(float(studio.progress["value"]), 100)
                    # A long sequence is cancelled through the real button/file
                    # protocol after a progress message, without killing Tk.
                    studio.keyframes = [CameraKeyframe(0, camera), CameraKeyframe(300, camera)]
                    studio.refresh_path()
                    studio.render_vars["format"].set("sequence")
                    studio.start_render()
                    deadline = time.monotonic()+40
                    while studio.busy and float(studio.progress["value"]) == 0 and time.monotonic() < deadline:
                        root.update()
                        time.sleep(.01)
                    self.assertTrue(studio.busy)
                    studio.cancel_render()
                    while studio.busy and time.monotonic() < deadline:
                        root.update()
                        time.sleep(.01)
                    self.assertFalse(studio.busy, "Cancellation did not reap the worker")
                    self.assertFalse(errors.called, errors.call_args)
                    self.assertIn("cancel", studio.status.get().lower())
                    self.assertIsNone(studio.process)
            finally:
                if studio is not None and not studio.closed:
                    studio.close()
                if viewer is not None and not viewer.closed:
                    viewer.close()
                root.destroy()


if __name__ == "__main__":
    unittest.main()

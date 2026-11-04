# SPDX-License-Identifier: Apache-2.0
"""Shared scene/serialization regressions and optional actual native GPU checks."""
import os
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
import zipfile
from unittest.mock import patch

import numpy as np

from abu_m54 import SceneTransform, export_copy, export_geometry, load_scene, transform_scene
from control_points_comparison import save_scene, read_scene
from test_m54_gaussian import write_ply


class GaussianSceneIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / 'gaussian.ply'
        write_ply(self.source, binary=True)

    def test_shared_loader_preserves_gaussian_fields_beyond_point_preview(self):
        header, payload = self.source.read_bytes().split(b'end_header\n', 1)
        self.source.write_bytes(header.replace(b'element vertex 1\n', b'element vertex 2\n') + b'end_header\n' + payload * 2)
        scene = load_scene(self.source, limit=1)
        self.assertEqual(scene['gaussians'].count, 2)
        self.assertEqual(len(scene['points']), 1)
        self.assertEqual(scene['gaussians'].degree, 1)
        np.testing.assert_array_equal(scene['gaussian_transform'], np.eye(4))
        self.assertFalse(scene['gaussians'].sh.flags.writeable)
        self.assertEqual(scene['gaussians'].positions[0, 0], 6371000.012345)

    def test_transform_composes_without_destroying_source_or_appearance(self):
        scene = load_scene(self.source)
        before = scene['gaussians'].positions.copy()
        first = SceneTransform(np.array([1., 2., 3.]), np.array([12., -23., 34.]), 1.7)
        second = SceneTransform(np.array([-3., 2., 1.]), np.array([-3., 7., 11.]), .8)
        preview = transform_scene(transform_scene(scene, first), second)
        self.assertIs(preview['gaussians'], scene['gaussians'])
        np.testing.assert_allclose(preview['gaussian_transform'], second.matrix() @ first.matrix())
        np.testing.assert_array_equal(scene['gaussians'].positions, before)
        np.testing.assert_allclose(preview['points'], before @ preview['gaussian_transform'][:3, :3].T + preview['gaussian_transform'][:3, 3])

    def test_background_scene_roundtrip_preserves_every_field_and_transform(self):
        scene = transform_scene(load_scene(self.source), SceneTransform(np.array([1., 2., 3.]), np.array([12., 23., 34.]), 2.))
        target = self.folder / 'scene.npz'
        save_scene(target, scene)
        restored = read_scene(target)
        np.testing.assert_array_equal(restored['gaussian_transform'], scene['gaussian_transform'])
        for field in ['positions', 'scales', 'rotations_wxyz', 'opacities', 'sh']:
            np.testing.assert_array_equal(getattr(restored['gaussians'], field), getattr(scene['gaussians'], field))
        self.assertEqual(restored['gaussians'].source, scene['gaussians'].source)
        with np.load(target, allow_pickle=False) as archive:
            self.assertTrue(all(archive[key].dtype != object for key in archive.files))

    def test_gaussian_export_cannot_silently_discard_appearance(self):
        scene = load_scene(self.source)
        destination = self.folder / 'lossy.ply'
        with self.assertRaises(ValueError):
            export_geometry(scene, destination)
        self.assertFalse(destination.exists())

    def test_transforms_json_gaussian_export_rejects_before_any_output(self):
        transforms = self.folder / 'transforms.json'
        transforms.write_text(json.dumps({'frames': [{'file_path': 'synthetic.png', 'transform_matrix': np.eye(4).tolist()}]}))
        companion = transforms.with_suffix('.points.ply')
        companion.write_bytes(self.source.read_bytes())
        before = {p.name for p in self.folder.iterdir()}
        with self.assertRaisesRegex(ValueError, 'Gaussian'):
            export_copy(transforms, self.folder / 'new.json', SceneTransform())
        self.assertEqual({p.name for p in self.folder.iterdir()}, before)

    def test_gaussian_archive_is_uncompressed_and_rejects_forged_npy_shape(self):
        archive_path = self.folder / 'scene.npz'
        save_scene(archive_path, load_scene(self.source))
        with zipfile.ZipFile(archive_path) as archive:
            records = {item.filename: archive.read(item.filename) for item in archive.infolist()}
            self.assertTrue(all(item.compress_type == zipfile.ZIP_STORED for item in archive.infolist()))
        forged = io.BytesIO()
        np.lib.format.write_array_header_1_0(forged, {'descr': '<f8', 'fortran_order': False, 'shape': (19_000_000, 3)})
        # No matching data: reader must reject before allocating the forged shape.
        records['gaussian_positions.npy'] = forged.getvalue()
        with zipfile.ZipFile(archive_path, 'w') as archive:
            for name, payload in records.items():
                archive.writestr(name, payload)
        with self.assertRaisesRegex(ValueError, 'payload size'):
            read_scene(archive_path)


@unittest.skipUnless(sys.platform == 'win32' and os.environ.get('ABU_TEST_NATIVE_GPU') == '1',
                     'Set ABU_TEST_NATIVE_GPU=1 on a Windows OpenGL 4.3+ GPU for native renderer regression.')
class GaussianNativeIntegrationTests(unittest.TestCase):
    def test_standalone_application_isolated_worker_loads_gaussian(self):
        import tkinter as tk
        from abu_m54_app import M54Application
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'synthetic-worker.ply'
            write_ply(source, binary=True)
            root = tk.Tk(); root.withdraw()
            app = M54Application(root)
            try:
                original_popen = subprocess.Popen
                with patch('abu_m54_app.subprocess.Popen', wraps=original_popen) as launched:
                    app.load(source)
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        root.update()
                        if app.viewer.raw_data is not None or app.host.status.get().startswith('Load failed:'):
                            break
                        time.sleep(.01)
                    self.assertIsNotNone(app.viewer.raw_data, app.host.status.get())
                    self.assertEqual(launched.call_count, 1)
                    self.assertIn('--load-worker', launched.call_args.args[0])
                scene = app.viewer.raw_data
                self.assertEqual(scene['gaussians'].count, 1)
                self.assertEqual(scene['gaussians'].degree, 1)
                self.assertEqual(scene['gaussians'].positions[0, 0], 6371000.012345)
                self.assertGreater(scene['extent'], .5)  # A Gaussian has physical support even at one center.
                app.viewer.initialize()
                with patch.object(app.viewer, 'winfo_ismapped', return_value=True):
                    app.viewer.draw(); app.viewer.gl.glFinish()
                self.assertIsNone(app.viewer.gaussian_failure)
                self.assertEqual(app.viewer.gaussian_renderer.count, 1)
                self.assertEqual(app.viewer.gl.glGetError(), 0)
            finally:
                app.close()

    def test_gpu_exception_restores_host_program_and_vertex_array(self):
        import ctypes as ct
        from abu_m54_splat_gpu import GaussianRenderer
        from benchmark_m54_gaussian import NativeTarget, perspective
        target = NativeTarget(128, 96)
        renderer = GaussianRenderer(target.gl)
        try:
            renderer.use(renderer.render)
            renderer.bind_vao(renderer.vao.value)
            with patch.object(renderer, '_draw', side_effect=RuntimeError('synthetic dispatch failure')):
                with self.assertRaisesRegex(RuntimeError, 'synthetic dispatch'):
                    renderer.draw(np.eye(4), perspective(128, 96), 128, 96)
            for state in [0x8B8D, 0x85B5]:  # GL_CURRENT_PROGRAM, GL_VERTEX_ARRAY_BINDING
                value = ct.c_int()
                target.fn('glGetIntegerv', None, ct.c_uint, ct.POINTER(ct.c_int))(state, ct.byref(value))
                self.assertEqual(value.value, 0)
            self.assertEqual(target.error(), 0)
        finally:
            renderer.close(); target.close()

    def test_independent_reference_quality_and_resource_release(self):
        from benchmark_m54_gaussian import run_quality
        with tempfile.TemporaryDirectory() as folder:
            result = run_quality(folder)
        self.assertTrue(result['passed'], result)
        self.assertEqual(len(result['cases']), 7)

    def test_native_host_transform_resize_legacy_switch_and_close(self):
        import tkinter as tk
        from abu_m54 import from_records
        from abu_m54_host import ViewerHost
        from abu_m54_native import M54NativeViewer
        from benchmark_m54_gaussian import synthetic_asset
        root = tk.Tk(); root.withdraw(); root.geometry('640x480')
        viewer = None
        try:
            viewer = M54NativeViewer(ViewerHost(root), root, compact=True)
            viewer.pack(fill='both', expand=True); root.update_idletasks()
            viewer.initialize()
            asset = synthetic_asset(1000)
            points, colors = asset.preview()
            scene = from_records(dict(points=points, colors=colors, cameras=[], path='synthetic-gaussian-host'))
            scene['gaussians'] = asset; scene['gaussian_transform'] = np.eye(4)
            viewer.set_data(scene)
            # Keep the test window hidden; the same native draw method and WGL
            # surface execute without taking focus or exposing private content.
            with patch.object(viewer, 'winfo_ismapped', return_value=True):
                viewer.draw(); viewer.gl.glFinish()
                self.assertIsNone(viewer.gaussian_failure)
                self.assertEqual(viewer.gaussian_renderer.count, 1000)
                self.assertGreater(viewer.gaussian_renderer.allocated_bytes, 0)
                original_buffers = list(viewer.gaussian_renderer.buffers)
                viewer.apply_transform('A', SceneTransform(np.array([1., 2., 3.]), np.array([12., 23., 34.]), 1.2))
                viewer.draw(); viewer.gl.glFinish()
                self.assertEqual(original_buffers, viewer.gaussian_renderer.buffers)
                root.geometry('800x600'); viewer.surface.configure(width=800, height=600); root.update_idletasks()
                viewer.draw(); viewer.gl.glFinish()
                self.assertEqual(viewer.gl.glGetError(), 0)
                legacy = from_records(dict(points=[[0., 0., 0.]], colors=[[255, 100, 50]], cameras=[], path='synthetic-legacy-host'))
                viewer.set_data(legacy); viewer.draw(); viewer.gl.glFinish()
                self.assertEqual(viewer.gaussian_renderer.allocated_bytes, 0)
                self.assertEqual(viewer.gl.glGetError(), 0)
            viewer.close()
            self.assertIsNone(viewer.context)
            self.assertIsNone(viewer.gaussian_renderer)
        finally:
            if viewer is not None and not viewer.closed:
                viewer.close()
            root.destroy()


if __name__ == '__main__':
    unittest.main()

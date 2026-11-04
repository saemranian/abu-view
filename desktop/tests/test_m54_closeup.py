# SPDX-License-Identifier: Apache-2.0
"""Close-camera projection and shared render-camera regressions."""
import os
import sys
import unittest
from unittest.mock import patch
import numpy as np
from scipy.spatial.transform import Rotation


@unittest.skipUnless(sys.platform == 'win32' and os.environ.get('ABU_TEST_NATIVE_GPU') == '1',
                     'Native Windows OpenGL regression')
class CloseupTests(unittest.TestCase):
    def setUp(self):
        from benchmark_m54_gaussian import NativeTarget
        from abu_m54_splat_gpu import GaussianRenderer
        self.target = NativeTarget(320, 240, floating=True)
        self.addCleanup(self.target.close)
        self.renderer = GaussianRenderer(self.target.gl)
        self.addCleanup(self.renderer.close)

    def render(self, asset, view=None):
        from benchmark_m54_gaussian import perspective
        view = np.eye(4) if view is None else view
        projection = perspective(320, 240, 45, near=.0001)
        self.renderer.set_asset(asset)
        self.target.clear()
        self.renderer.draw(view, projection, 320, 240)
        self.target.finish()
        image = self.target.capture()
        self.assertEqual(self.target.error(), 0)
        self.assertTrue(np.isfinite(image).all())
        return image, projection

    def test_offscreen_near_eye_splat_does_not_blank_the_scene(self):
        from abu_m54_gaussian import GaussianAsset, SH_C0
        from benchmark_m54_gaussian import BACKGROUND, reference_image
        # Its mean is 2 units to the side but only .001 in front. The old
        # unconstrained z derivative stretched this blue splat across the view.
        asset = GaussianAsset(np.array([[2., 0., -.001]]), np.full((1, 3), .001),
                              np.array([[1., 0, 0, 0]]), np.array([.99]),
                              ((np.array([[[.2], [.6], [.8]]])-.5)/SH_C0))
        for shift in [0., .0002, -.0002]:
            view = np.eye(4);view[2, 3] = shift
            actual, projection = self.render(asset, view)
            expected = reference_image(asset, view, projection, 320, 240)
            np.testing.assert_allclose(actual, expected, atol=1e-6)
            np.testing.assert_allclose(actual.mean((0, 1), dtype=np.float64), BACKGROUND, atol=1e-6)

    def test_very_thin_rotated_splat_has_finite_nonopaque_tails(self):
        from abu_m54_gaussian import GaussianAsset, SH_C0
        from benchmark_m54_gaussian import BACKGROUND, reference_image
        q = Rotation.from_euler('z', 45, degrees=True).as_quat()[[3, 0, 1, 2]]
        asset = GaussianAsset(np.array([[0., 0., -2.]]), np.array([[100., .001, .001]]),
                              q[None, :], np.array([.8]),
                              ((np.array([[[.9], [.2], [.1]]])-.5)/SH_C0))
        actual, projection = self.render(asset)
        expected = reference_image(asset, np.eye(4), projection, 320, 240)
        self.assertLess(float(np.sqrt(np.mean((actual-expected)**2))), .001)
        np.testing.assert_allclose(actual[20, 20], BACKGROUND, atol=1e-6)
        self.assertGreater(float(np.max(actual[:, :, 0])), .3)

    def test_saved_camera_roundtrip_preserves_shared_view_and_fov(self):
        import tkinter as tk
        from abu_m54_host import ViewerHost
        from abu_m54_native import M54NativeViewer
        from abu_m54_cameras import CameraPose
        root = tk.Tk();root.withdraw()
        viewer = M54NativeViewer(ViewerHost(root), root, compact=True)
        try:
            viewer.origin = np.array([6371000., -2430000., 1200000.])
            viewer.scale = 120.;viewer.distance = .2
            camera = CameraPose.from_euler('Test', viewer.origin+[2., 4., -3.], [12., 43., -79.], 63.)
            viewer.look_through_render_camera(camera)
            captured = viewer.get_render_camera('Saved')
            np.testing.assert_allclose(captured.position, camera.position, atol=1e-9, rtol=0)
            np.testing.assert_allclose(captured.rotation_matrix, camera.rotation_matrix, atol=1e-12)
            self.assertAlmostEqual(captured.fov_y_degrees, 63.)
            viewer.save_view();viewer.fit();viewer.restore_view()
            self.assertAlmostEqual(viewer.get_render_camera().fov_y_degrees, 63.)
        finally:
            viewer.close();root.destroy()


if __name__ == '__main__':
    unittest.main()

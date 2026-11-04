# SPDX-License-Identifier: Apache-2.0
"""Small staged-upload and GPU-residency regressions; no private fixtures."""
import os
import sys
from types import SimpleNamespace
import unittest

import numpy as np

from abu_m54_gaussian import GaussianAsset
from abu_m54_sequence_gpu import SequenceGPUCache, estimate_gpu_bytes


def frame(index, count=3):
    positions = np.column_stack((np.linspace(-.5, .5, count), np.zeros(count), np.full(count, -3.)))
    sh = np.full((count, 3, 1), -1., dtype=np.float32)
    sh[:, index % 3] = 1.
    asset = GaussianAsset(positions, np.full((count, 3), .2),
                          np.tile([1., 0, 0, 0], (count, 1)), np.full(count, .8), sh)
    origin = (asset.positions.min(0) + asset.positions.max(0)) * .5
    scale = max(float(np.linalg.norm(np.ptp(asset.positions, axis=0))), 1e-8)
    packed = asset.packed(origin, scale)
    packed.setflags(write=False)
    return SimpleNamespace(index=index, scene={'gaussians': asset}, packed=packed, origin=origin, scale=scale)


class MemoryTests(unittest.TestCase):
    def test_actual_buffer_size_and_budget_limits(self):
        self.assertEqual(estimate_gpu_bytes(0), 0)
        self.assertEqual(estimate_gpu_bytes(1), 304 + 256*8)
        self.assertEqual(estimate_gpu_bytes(257), 257*304 + 512*8)
        self.assertEqual(estimate_gpu_bytes(3_000_000), 945_554_432)
        for budget in (0, -1, 8*1024**3+1):
            with self.assertRaises(ValueError):
                SequenceGPUCache(None, budget)


@unittest.skipUnless(sys.platform == 'win32' and os.environ.get('ABU_TEST_NATIVE_GPU') == '1',
                     'Native Windows OpenGL regression')
class SequenceGpuTests(unittest.TestCase):
    def setUp(self):
        from benchmark_m54_gaussian import NativeTarget, perspective
        self.target = NativeTarget(160, 120, floating=True)
        self.projection = perspective(160, 120, 60)
        self.addCleanup(self.target.close)

    def cache(self, budget=None):
        value = SequenceGPUCache(self.target.gl, budget or estimate_gpu_bytes(3)*3)
        self.addCleanup(value.close)
        return value

    def finish_upload(self, cache, prepared):
        cache.request(prepared)
        while not cache.step(256):
            pass
        self.assertTrue(cache.contains(prepared.index))
        self.assertIsNone(cache.uploading_index)
        self.assertEqual(self.target.error(), 0)

    def pixels(self, renderer):
        self.target.clear()
        renderer.draw(np.eye(4), self.projection, 160, 120)
        self.target.finish()
        pixels = self.target.capture()
        self.assertEqual(self.target.error(), 0)
        return pixels

    def test_partial_upload_not_drawable_and_matches_static_upload(self):
        from abu_m54_splat_gpu import GaussianRenderer
        a = frame(0)
        renderer = GaussianRenderer(self.target.gl)
        self.addCleanup(renderer.close)
        renderer.begin_asset(a.scene['gaussians'], (a.packed, a.origin, a.scale))
        self.assertIsNone(renderer.asset)
        self.assertFalse(renderer.upload_step(256))
        partial = self.pixels(renderer)
        self.assertLess(float(partial.std((0, 1)).max()), 1e-5)
        while not renderer.upload_step(256):
            pass
        staged = self.pixels(renderer)
        expected = GaussianRenderer(self.target.gl)
        self.addCleanup(expected.close)
        expected.set_asset(a.scene['gaussians'])
        np.testing.assert_array_equal(staged, self.pixels(expected))

    def test_cached_loop_switches_pixels_without_upload_or_reallocation(self):
        cache = self.cache()
        frames = [frame(i) for i in range(3)]
        for prepared in frames:
            self.finish_upload(cache, prepared)
        identities = {i: tuple(cache.get(i).buffers) for i in range(3)}
        images = []
        for i in (0, 1, 2, 0, 1, 2):
            self.assertTrue(cache.request(frames[i]))
            self.assertIsNone(cache.uploading_index)
            self.assertEqual(tuple(cache.get(i).buffers), identities[i])
            images.append(self.pixels(cache.get(i)))
        self.assertGreater(float(np.abs(images[0]-images[1]).max()), .1)
        self.assertGreater(float(np.abs(images[1]-images[2]).max()), .1)
        np.testing.assert_array_equal(images[0], images[3])
        np.testing.assert_array_equal(images[1], images[4])
        self.assertEqual(cache.allocated_bytes, estimate_gpu_bytes(3)*3)

    def test_lru_eviction_preserves_displayed_frame_and_budget(self):
        cache = self.cache(estimate_gpu_bytes(3)*2)
        for i in (0, 1):
            self.finish_upload(cache, frame(i))
        old = cache.get(1)
        protected = cache.get(0)
        cache.protected_index = 0
        self.finish_upload(cache, frame(2))
        self.assertEqual(set(cache.cached_indices), {0, 2})
        self.assertIs(cache.get(0), protected)
        self.assertEqual(old.allocated_bytes, 0)
        self.assertEqual(old.buffers, [])
        self.assertLessEqual(cache.allocated_bytes, cache.budget_bytes)

    def test_insufficient_budget_never_evicts_protected_display(self):
        cache = self.cache(estimate_gpu_bytes(3))
        self.finish_upload(cache, frame(0))
        cache.protected_index = 0
        old = cache.get(0)
        with self.assertRaisesRegex(BufferError, 'displayed frame'):
            cache.request(frame(1))
        self.assertIs(cache.get(0), old)
        self.assertEqual(cache.cached_indices, (0,))
        cache.protected_index = None
        self.finish_upload(cache, frame(1))
        self.assertEqual(old.buffers, [])
        self.assertEqual(cache.cached_indices, (1,))

    def test_scrub_cancels_partial_upload_and_close_frees_everything(self):
        cache = self.cache()
        cache.request(frame(0))
        old = cache._uploading[1]
        self.assertFalse(cache.step(256))
        cache.request(frame(1))
        self.assertEqual(old.buffers, [])
        self.assertIsNone(cache.get(0))
        self.assertFalse(cache.contains(1))
        self.finish_upload(cache, frame(1))
        cache.request(frame(2))
        cache.close()
        cache.close()
        self.assertEqual(cache.allocated_bytes, 0)
        self.assertEqual(cache.cached_indices, ())
        self.assertIsNone(cache.uploading_index)
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            cache.request(frame(0))

    def test_invalid_prepared_data_cleans_all_partial_resources(self):
        cache = self.cache()
        bad = frame(0)
        bad.packed = bad.packed.copy()
        bad.packed[2, 50] = np.nan
        cache.request(bad)
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            while not cache.step(256):
                pass
        self.assertEqual(cache.allocated_bytes, 0)
        self.assertIsNone(cache.uploading_index)
        self.assertFalse(cache.contains(0))
        invalid_shape = frame(0)
        invalid_shape.packed = invalid_shape.packed[:, :-1]
        with self.assertRaisesRegex(ValueError, 'prepared'):
            cache.request(invalid_shape)
        self.assertEqual(cache.allocated_bytes, 0)

    def test_variable_count_frame_replaces_residency_safely(self):
        cache = self.cache(estimate_gpu_bytes(257) + estimate_gpu_bytes(3))
        self.finish_upload(cache, frame(0, 257))
        self.finish_upload(cache, frame(1, 3))
        self.assertEqual(cache.get(0).count, 257)
        self.assertEqual(cache.get(1).count, 3)
        for index in (0, 1):
            self.assertTrue(np.isfinite(self.pixels(cache.get(index))).all())


if __name__ == '__main__':
    unittest.main()

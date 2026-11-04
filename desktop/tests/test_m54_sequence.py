# SPDX-License-Identifier: Apache-2.0
"""Small synthetic PLY sequence timing, import safety and cache regressions."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from abu_m54_sequence import (CPUFrameCache, PlySequence, discover_sequence,
                              inspect_frame, prepare_frame)


def write_frame(path, x=0., count=2, rest=0):
    """Independent minimal conventional Gaussian binary PLY fixture."""
    names = ['x', 'y', 'z', 'opacity', 'scale_0', 'scale_1', 'scale_2',
             'rot_0', 'rot_1', 'rot_2', 'rot_3', 'f_dc_0', 'f_dc_1', 'f_dc_2']
    names.extend(f'f_rest_{i}' for i in range(rest))
    data = np.zeros(count, dtype=[(name, '<f4') for name in names])
    data['x'] = x + np.arange(count) * .1
    data['y'] = .2
    data['z'] = -3.
    data['opacity'] = 1.5
    data['rot_0'] = 1.
    for axis in range(3):
        data[f'scale_{axis}'] = -2.
        data[f'f_dc_{axis}'] = axis * .2
    header = 'ply\nformat binary_little_endian 1.0\nelement vertex ' + str(count) + '\n'
    header += ''.join('property float ' + name + '\n' for name in names) + 'end_header\n'
    path.write_bytes(header.encode('ascii') + data.tobytes())
    return path


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.paths = tuple(write_frame(self.folder / f'frame_{n}.ply', n * .1) for n in (1, 2, 10))

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                self.fail('Timed out waiting for background frame preparation.')
            time.sleep(.01)

    def cache(self, sequence, **kwargs):
        cache = CPUFrameCache(sequence, **kwargs)
        self.addCleanup(lambda: cache.close(wait=True))
        return cache

    def test_numeric_discovery_and_family_selection(self):
        sequence = discover_sequence(self.folder, fps=24)
        self.assertEqual([Path(p).name for p in sequence.paths], ['frame_1.ply', 'frame_2.ply', 'frame_10.ply'])
        self.assertEqual(sequence.count, 3)
        self.assertEqual(sequence.duration, 3 / 24)
        write_frame(self.folder / 'unrelated_1.ply')
        self.assertEqual(discover_sequence(self.folder).count, 3)
        write_frame(self.folder / 'unrelated_2.ply')
        with self.assertRaisesRegex(ValueError, 'multiple numbered sequences'):
            discover_sequence(self.folder)
        selected = discover_sequence(self.paths[1])
        self.assertEqual(selected.paths, sequence.paths)
        write_frame(self.folder / 'frame_01.ply')
        with self.assertRaisesRegex(ValueError, 'same numeric frame number'):
            discover_sequence(self.paths[0])

    def test_sequence_timing_holds_frames_without_interpolation(self):
        sequence = PlySequence(self.paths, 30)
        for i in range(3):
            self.assertEqual(sequence.frame_index(i / 30), i)
            self.assertEqual(sequence.frame_index((i + .9) / 30), i)
        self.assertEqual(sequence.frame_index(-10), 0)
        self.assertEqual(sequence.frame_index(10), 2)
        self.assertEqual(sequence.frame_index(sequence.duration, loop=True), 0)
        self.assertEqual(sequence.frame_index(sequence.duration + 1 / 30, loop=True), 1)
        self.assertEqual(sequence.frame_index(-1 / 30, loop=True), 2)
        with self.assertRaises(ValueError):
            sequence.frame_index(float('nan'))
        for fps in (0, -1, float('nan'), float('inf'), 241, 'invalid'):
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                PlySequence(self.paths, fps)

    def test_manifest_signatures_detect_change_before_export(self):
        sequence = PlySequence(self.paths)
        record = json.loads(json.dumps(sequence.to_dict()))
        copy = PlySequence.from_dict(record)
        self.assertEqual(copy.paths, sequence.paths)
        self.assertEqual(copy.to_dict(), record)
        changed = self.paths[1]
        before = changed.stat()
        os.utime(changed, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
        with self.assertRaisesRegex(ValueError, 'changed'):
            sequence.verify_frame(1)
        with self.assertRaisesRegex(ValueError, 'changed'):
            PlySequence.from_dict(record)
        record['frames'][0]['path'] = 'relative.ply'
        with self.assertRaisesRegex(ValueError, 'absolute'):
            PlySequence.from_dict(record)

    def test_fps_edit_keeps_original_signatures_without_reading_headers(self):
        sequence = PlySequence(self.paths)
        before = self.paths[0].stat()
        os.utime(self.paths[0], ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
        with patch('abu_m54_sequence.inspect_frame', side_effect=AssertionError('Unexpected header read')):
            changed = sequence.with_fps(12)
        self.assertEqual(changed.fps, 12)
        self.assertEqual(changed.duration, .25)
        self.assertIs(changed.frames, sequence.frames)
        self.assertEqual(changed.paths, sequence.paths)
        self.assertEqual(sequence.fps, 30)
        with self.assertRaisesRegex(ValueError, 'changed'):
            changed.verify_frame(0)
        with self.assertRaises(ValueError):
            sequence.with_fps(float('inf'))

    def test_preflight_rejects_non_gaussian_partial_truncated_and_empty(self):
        plain = self.folder / 'plain.ply'
        plain.write_bytes(b'ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n')
        with self.assertRaisesRegex(ValueError, 'Gaussian PLY attributes'):
            inspect_frame(plain)
        truncated = self.folder / 'broken.ply'
        truncated.write_bytes(self.paths[0].read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, 'truncated'):
            inspect_frame(truncated)
        empty = write_frame(self.folder / 'empty.ply', count=0)
        with self.assertRaisesRegex(ValueError, '1–20,000,000'):
            inspect_frame(empty)
        bad_sh = write_frame(self.folder / 'bad_sh.ply', rest=1)
        with self.assertRaisesRegex(ValueError, 'SH degree'):
            inspect_frame(bad_sh)
        with self.assertRaises(ValueError):
            PlySequence((self.paths[0],))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            PlySequence((self.paths[0], self.paths[0]))

    def test_prepared_frame_preserves_source_and_matches_gpu_layout(self):
        write_frame(self.paths[2], x=4, count=3, rest=45)
        sequence = PlySequence(self.paths)
        prepared = prepare_frame(sequence, 2)
        asset = prepared.scene['gaussians']
        self.assertEqual(asset.count, 3)
        self.assertEqual(asset.degree, 3)
        np.testing.assert_array_equal(prepared.packed, asset.packed(prepared.origin, prepared.scale))
        self.assertFalse(prepared.packed.flags.writeable)
        self.assertFalse(prepared.origin.flags.writeable)
        self.assertFalse(prepared.scene['points'].flags.writeable)
        self.assertLessEqual(prepared.nbytes, sequence.frames[2].cpu_bytes)
        padded = max(256, 1 << (asset.count - 1).bit_length())
        self.assertEqual(sequence.frames[2].gpu_bytes, 304 * asset.count + 8 * padded)
        self.assertEqual(sequence.frames[2].decoded_bytes, asset.nbytes)

    def test_cache_prefetches_all_when_budget_fits(self):
        sequence = PlySequence(self.paths)
        cache = self.cache(sequence, budget_bytes=sequence.total_cpu_bytes)
        self.wait_for(lambda: len(cache.cached_indices) == 3)
        self.assertFalse(cache.errors)
        self.assertLessEqual(cache.used_bytes, cache.budget_bytes)
        self.assertEqual(cache.get(1).index, 1)
        events = []
        while not cache.events.empty():
            events.append(cache.events.get_nowait())
        self.assertEqual({event['index'] for event in events if event['event'] == 'ready'}, {0, 1, 2})
        cache.close(wait=True)
        self.assertTrue(cache.closed)
        self.assertEqual(cache.used_bytes, 0)
        self.assertEqual(cache.cached_indices, ())

    def test_cache_evicts_within_byte_limit_and_prioritizes_seek(self):
        sequence = PlySequence(self.paths)
        cache = self.cache(sequence, budget_bytes=sequence.frames[0].cpu_bytes * 2)
        self.wait_for(lambda: set(cache.cached_indices) == {0, 1})
        cache.request(2)
        self.wait_for(lambda: set(cache.cached_indices) == {0, 2})
        self.assertLessEqual(cache.used_bytes, cache.budget_bytes)
        self.assertIsNone(cache.get(1))
        self.assertEqual(cache.get(2).index, 2)
        with self.assertRaises(IndexError):
            cache.request(3)
        with self.assertRaises(IndexError):
            cache.get(1.5)
        with self.assertRaisesRegex(ValueError, 'exceeding the CPU cache budget'):
            CPUFrameCache(sequence, budget_bytes=1)

    def test_seek_and_close_discard_inflight_results(self):
        sequence = PlySequence(self.paths)
        begun, release = threading.Event(), threading.Event()
        loaded = []

        def loader(sequence, index):
            loaded.append(index)
            if index == 0:
                begun.set()
                release.wait(5)
            return prepare_frame(sequence, index)

        cache = self.cache(sequence, budget_bytes=sequence.frames[0].cpu_bytes, loader=loader)
        self.assertTrue(begun.wait(2))
        cache.request(2)
        release.set()
        self.wait_for(lambda: cache.get(2) is not None)
        self.assertEqual(loaded, [0, 2])
        self.assertEqual(cache.cached_indices, (2,))
        begun.clear()
        release.clear()
        cache.request(0)
        self.assertTrue(begun.wait(2))
        cache.close()
        release.set()
        cache.close(wait=True)
        self.assertEqual(cache.cached_indices, ())
        self.assertEqual(cache.used_bytes, 0)

    def test_decode_error_is_reported_once_and_does_not_stall_other_frames(self):
        sequence = PlySequence(self.paths)
        calls = []

        def loader(sequence, index):
            calls.append(index)
            if index == 1:
                raise ValueError('Synthetic invalid Gaussian scalar')
            return prepare_frame(sequence, index)

        cache = self.cache(sequence, budget_bytes=sequence.total_cpu_bytes, loader=loader)
        self.wait_for(lambda: set(cache.cached_indices) == {0, 2})
        self.assertEqual(cache.errors[1], 'Synthetic invalid Gaussian scalar')
        cache.request(1)
        time.sleep(.05)
        self.assertEqual(calls.count(1), 1)


if __name__ == '__main__':
    unittest.main()

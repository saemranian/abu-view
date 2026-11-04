# SPDX-License-Identifier: Apache-2.0
"""Temporal source exports use real small PLY frames, never private fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from abu_m54_cameras import CameraPose, CameraKeyframe, CameraPath, RenderSettings
from abu_m54_render import render_job, validate_job, find_ffmpeg


def small_frame(path, frame):
    names = ['x', 'y', 'z', 'opacity', 'scale_0', 'scale_1', 'scale_2',
             'rot_0', 'rot_1', 'rot_2', 'rot_3', 'f_dc_0', 'f_dc_1', 'f_dc_2']
    count = 3 + frame
    values = np.zeros(count, dtype=[(name, '<f4') for name in names])
    values['x'] = np.linspace(-.6, .6, count)
    values['y'] = (frame - 1) * .2
    values['z'] = -3
    values['opacity'] = 2
    for name in ('scale_0', 'scale_1', 'scale_2'):
        values[name] = np.log(.25)
    values['rot_0'] = 1
    for channel in range(3):
        values[f'f_dc_{channel}'] = (float(channel == frame) - .5) / np.sqrt(1 / (4 * np.pi))
    header = '\n'.join(['ply', 'format binary_little_endian 1.0', f'element vertex {count}',
                        *[f'property float {name}' for name in names], 'end_header', ''])
    with Path(path).open('wb') as stream:
        stream.write(header.encode('ascii'))
        stream.write(values.tobytes())


class SequenceFixture:
    def setUp(self):
        from abu_m54_sequence import PlySequence
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        files = [self.folder / f'frame_{index:04d}.ply' for index in range(3)]
        for index, path in enumerate(files):
            small_frame(path, index)
        self.sequence = PlySequence(tuple(str(path) for path in files), fps=30)
        self.camera = CameraPose('Fixed test camera', [0, 0, 0], [0, 1, 0, 0], 60)

    def job(self, output_fps=30, format='sequence', path=None):
        return {'schema': 1, 'output': str(self.folder), 'camera': self.camera.to_dict(),
                'path': path.to_dict() if path is not None else None,
                'settings': RenderSettings(width=96, height=64, fps=output_fps, format=format).to_dict(),
                'source_sequence': {'sequence': self.sequence.to_dict(), 'transform': np.eye(4).tolist(), 'start_index': 1},
                'cancel_file': str(self.folder / 'cancel')}


class TemporalJobTests(SequenceFixture, unittest.TestCase):
    def test_fixed_camera_sequence_has_source_duration_and_independent_output_fps(self):
        job = self.job(output_fps=60)
        self.assertNotIn('scene', job)
        source, _, _, _, path, times, _ = validate_job(job)
        self.assertIsNone(path)
        self.assertEqual(len(times), 6)
        self.assertEqual([source.sequence.frame_index(t) for t in times], [0, 0, 1, 1, 2, 2])
        self.assertEqual(source.start_index, 1)

    def test_changed_file_and_invalid_transform_are_rejected_before_output(self):
        job = self.job()
        job['source_sequence']['transform'][0][0] = -1
        with self.assertRaises(ValueError):
            validate_job(job)
        job = self.job()
        with Path(self.sequence.paths[1]).open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaises((ValueError, RuntimeError)):
            validate_job(job)
        self.assertFalse(list(self.folder.glob('m54_render_*')))

    def test_invalid_current_index_and_huge_render_are_rejected(self):
        for index in (-1, 3, True, 1.5):
            job = self.job()
            job['source_sequence']['start_index'] = index
            with self.assertRaises(ValueError):
                validate_job(job)
        job = self.job()
        job['settings']['width'] = 8192
        job['settings']['height'] = 8192
        with self.assertRaises(ValueError):
            validate_job(job)

    @unittest.skipUnless(sys.platform == 'win32', 'Desktop Tk source-control lifecycle test')
    def test_studio_updates_when_sequence_opens_after_window(self):
        import tkinter as tk
        from types import SimpleNamespace
        from abu_m54_render_ui import open_render_studio
        root = tk.Tk()
        root.withdraw()
        camera = self.camera
        class Viewer(tk.Frame):
            data = {'source': 'synthetic'}
            comparison = None
            render_studio = None
            sequence_player = None
            closed = False
            def get_render_camera(self, name='Camera'):
                return camera
            def request(self):
                pass
        viewer = Viewer(root)
        studio = open_render_studio(viewer)
        studio.withdraw()
        def tick_until(predicate):
            deadline = time.monotonic() + 2
            while not predicate() and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            self.assertTrue(predicate())
        try:
            studio.render_vars['format'].set('sequence')
            self.assertEqual(str(studio.sequence_check['state']), 'disabled')
            studio.animate_sequence.set(False)
            viewer.sequence_player = SimpleNamespace(sequence=self.sequence)
            tick_until(lambda: studio.animate_sequence.get())
            self.assertEqual(str(studio.sequence_check['state']), 'normal')
            self.assertIn('PLY sequence', studio.summary.get())
            studio.animate_sequence.set(False)
            viewer.sequence_player.sequence = self.sequence.with_fps(12)
            tick_until(lambda: '12 source fps' in studio.sequence_notice.get())
            self.assertFalse(studio.animate_sequence.get(), 'Changing source FPS must preserve an explicit static export choice')
            viewer.sequence_player.sequence = None
            tick_until(lambda: str(studio.sequence_check['state']) == 'disabled')
        finally:
            studio.close()
            self.assertIsNone(studio.sequence_watch_job)
            root.destroy()


@unittest.skipUnless(sys.platform == 'win32' and os.environ.get('ABU_TEST_NATIVE_GPU') == '1',
                     'Set ABU_TEST_NATIVE_GPU=1 for temporal native export qualification.')
class TemporalNativeTests(SequenceFixture, unittest.TestCase):
    def test_three_frames_and_resampling_preserve_temporal_colors_and_count(self):
        from abu_m54 import load_scene
        with patch('abu_m54.load_scene', wraps=load_scene) as loader:
            report, folder = render_job(self.job(60))
        self.assertEqual(report['status'], 'complete', report.get('message'))
        self.assertEqual(loader.call_count, 3, 'Repeated output samples should reuse the loaded source frame')
        self.assertEqual(report['frames_completed'], 6)
        self.assertEqual([frame['source_index'] for frame in report['source_frames']], [0, 0, 1, 1, 2, 2])
        captures = []
        for path in sorted((folder / 'frames').glob('*.png')):
            with Image.open(path) as image:
                captures.append(np.asarray(image).copy())
        for index in range(3):
            np.testing.assert_array_equal(captures[index * 2], captures[index * 2 + 1])
            self.assertEqual(int(captures[index * 2].sum(axis=(0, 1)).argmax()), index)
        self.assertFalse(list(self.folder.glob('*.npz')))
        self.assertEqual(report['gaussian_count'], 5)

    def test_current_frame_still_transform_and_optional_camera_path(self):
        job = self.job(format='png')
        report, folder = render_job(job)
        self.assertEqual(report['status'], 'complete', report.get('message'))
        self.assertEqual(report['source_frames'][0]['source_index'], 1)
        with Image.open(folder / 'still.png') as image:
            pixels = np.asarray(image).copy()
            self.assertEqual(int(pixels.sum(axis=(0, 1)).argmax()), 1)
        offset = [1., 2., 3.]
        for axis in range(3):
            job['source_sequence']['transform'][axis][3] = offset[axis]
        job['camera'] = CameraPose('Translated', offset, self.camera.quaternion_wxyz, 60).to_dict()
        report, folder = render_job(job)
        self.assertEqual(report['status'], 'complete', report.get('message'))
        with Image.open(folder / 'still.png') as image:
            np.testing.assert_array_equal(pixels, np.asarray(image))
        moved = CameraPose('Moved', [.1, 0, 0], [0, 1, 0, 0], 60)
        path = CameraPath((CameraKeyframe(0, self.camera), CameraKeyframe(.01, moved)))
        report, folder = render_job(self.job(path=path))
        self.assertEqual(report['status'], 'complete', report.get('message'))
        self.assertEqual(report['frames_completed'], 3, 'Camera path duration must not truncate source animation')
        self.assertEqual(report['source_duration_seconds'], .1)

    def test_cancel_or_changed_source_keeps_only_completed_frames(self):
        job = self.job()
        def cancel(**event):
            if event.get('stage') == 'render' and event.get('frame') == 1:
                Path(job['cancel_file']).touch()
        report, folder = render_job(job, cancel)
        self.assertEqual(report['status'], 'cancelled')
        self.assertEqual(report['frames_completed'], 1)
        self.assertEqual(len(list((folder / 'frames').glob('*.png'))), 1)
        Path(job['cancel_file']).unlink()
        def mutate(**event):
            if event.get('stage') == 'render' and event.get('frame') == 1:
                with Path(self.sequence.paths[1]).open('ab') as stream:
                    stream.write(b'changed during rendering')
        report, folder = render_job(job, mutate)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['frames_completed'], 1)
        self.assertFalse(list(folder.rglob('*.partial')))

    def test_real_studio_worker_uses_source_descriptor_without_large_npz(self):
        import tkinter as tk
        from abu_m54 import load_scene
        from abu_m54_render_ui import open_render_studio
        root = tk.Tk()
        root.withdraw()
        descriptor = self.job()['source_sequence']
        sequence, camera = self.sequence, self.camera
        class Player:
            index = 1
            paused = False
            def pause(self):
                self.paused = True
            def export_descriptor(self):
                return descriptor
        player = Player()
        player.sequence = sequence
        class Viewer(tk.Frame):
            data = load_scene(sequence.paths[1], attach_companions=False)
            comparison = None
            render_studio = None
            closed = False
            sequence_player = player
            def get_render_camera(self, name='Camera'):
                return camera
            def request(self):
                pass
        viewer = Viewer(root)
        studio = open_render_studio(viewer)
        studio.withdraw()
        try:
            studio.render_vars['output'].set(str(self.folder))
            studio.render_vars['format'].set('sequence')
            studio.render_vars['width'].set('96')
            studio.render_vars['height'].set('64')
            self.assertTrue(studio.animate_sequence.get())
            self.assertIn('PLY sequence', studio.summary.get())
            with patch('control_points_comparison.save_scene', side_effect=AssertionError('Sequence should not stage a scene NPZ')) as snapshot, \
                 patch('abu_m54_render_ui.messagebox.showerror') as error:
                studio.start_render()
                deadline = time.monotonic() + 30
                while studio.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.01)
                self.assertFalse(studio.busy)
                self.assertFalse(error.called, error.call_args)
                self.assertFalse(snapshot.called)
            self.assertTrue(player.paused)
            report = json.loads((Path(studio.last_output) / 'render_report.json').read_text())
            self.assertEqual(report['status'], 'complete', report.get('message'))
            self.assertEqual(report['frames_completed'], 3)
        finally:
            studio.close()
            root.destroy()

    @unittest.skipUnless(os.environ.get('ABU_TEST_VIDEO') == '1', 'Set ABU_TEST_VIDEO=1 for local FFmpeg verification.')
    def test_actual_mp4_has_three_temporal_frames(self):
        report, folder = render_job(self.job(format='mp4'))
        self.assertEqual(report['status'], 'complete', report.get('message'))
        ffprobe = Path(find_ffmpeg()).with_name('ffprobe.exe')
        result = subprocess.run([str(ffprobe), '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                                 '-show_entries', 'stream=width,height,nb_read_frames,r_frame_rate', '-of', 'json',
                                 str(folder / 'video.mp4')], check=True, capture_output=True, text=True,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        stream = json.loads(result.stdout)['streams'][0]
        self.assertEqual(int(stream['nb_read_frames']), 3)
        self.assertEqual(stream['r_frame_rate'], '30/1')
        self.assertEqual([item['source_index'] for item in report['source_frames']], [0, 1, 2])


if __name__ == '__main__':
    unittest.main()

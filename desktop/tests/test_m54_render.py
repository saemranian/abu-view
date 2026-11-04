# SPDX-License-Identifier: Apache-2.0
"""Render-job safety, real native output, cancellation, and encoder regressions."""
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
from abu_m54_render import (RenderCancelled, _run_encoder, encode_video, find_ffmpeg,
                            frame_times, render_job, validate_job)


def camera(position=(0., 0., 0.)):
    return CameraPose('Render camera', position, [0., 1., 0., 0.], 60.)


def make_scene(path, offset=(0., 0., 0.)):
    from abu_m54 import from_records
    from abu_m54_gaussian import GaussianAsset
    from control_points_comparison import save_scene
    positions = np.array([[0., 0., -3.], [-.5, .4, -4.], [.6, -.2, -3.5]]) + offset
    asset = GaussianAsset(positions, np.full((3, 3), .22), np.tile([1., 0, 0, 0], (3, 1)),
                          np.full(3, .8), np.array([[[1.], [-1.], [-1.]], [[-1.], [1.], [-1.]], [[-1.], [-1.], [1.]]]),
                          source='synthetic-render-fixture')
    scene = from_records({'points': positions})
    scene.update(gaussians=asset, gaussian_transform=np.eye(4), geometry_kind='gaussians')
    save_scene(path, scene)
    return scene


class RenderFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.scene = self.folder / 'scene.npz'
        self.scene.write_bytes(b'')

    def job(self, settings=None, path=None):
        return {'schema': 1, 'scene': str(self.scene), 'output': str(self.folder),
                'settings': (settings or RenderSettings(width=64, height=48)).to_dict(),
                'camera': camera().to_dict(), 'path': path.to_dict() if path else None,
                'cancel_file': str(self.folder / 'cancel.flag')}


class RenderJobTests(RenderFixture, unittest.TestCase):
    def test_sequence_samples_preserve_standard_video_duration(self):
        values = frame_times(.105, 30)
        self.assertEqual(len(values), 4)
        self.assertLess(values[-1], .105)
        self.assertEqual(values[0], 0)
        self.assertEqual(len(frame_times(1, 30)), 30)
        self.assertTrue(np.all(np.diff(values) > 0))
        self.assertLessEqual(max(np.diff(values)), 1 / 30 + 1e-12)
        for duration, fps in [(float('nan'), 30), (1, float('inf')), (86400, 240)]:
            with self.assertRaises(ValueError):
                frame_times(duration, fps)

    def test_validation_rejects_incomplete_path_and_excessive_gpu_target(self):
        with self.assertRaisesRegex(ValueError, 'two timed'):
            validate_job(self.job(RenderSettings(width=64, height=48, format='mp4')))
        # Build a crafted record so dataclass validation cannot be skipped by worker.
        job = self.job()
        job['settings'].update(width=8192, height=8192, supersampling=2)
        with self.assertRaises(ValueError):
            validate_job(job)

    def test_cancellation_before_load_creates_no_output_folder(self):
        job = self.job()
        Path(job['cancel_file']).touch()
        with self.assertRaises(RenderCancelled):
            render_job(job)
        self.assertFalse(list(self.folder.glob('m54_render_*')))

    def test_cancelled_encoder_process_is_reaped_promptly(self):
        flag = self.folder / 'cancel.flag'
        flag.touch()
        start = time.monotonic()
        with self.assertRaises(RenderCancelled):
            _run_encoder([sys.executable, '-c', 'import time; time.sleep(20)'], self.folder / 'encoder.log', flag)
        self.assertLess(time.monotonic() - start, 5)

    def test_auto_encoder_retries_cpu_and_keeps_frames(self):
        commands = []

        def run(command, *args, **kwargs):
            commands.append(command)
            if command[-1] == '-':
                return 0  # Hardware probe passes, real encode then fails.
            target = Path(command[-1])
            target.write_bytes(b'valid synthetic encoded payload')
            return 1 if 'h264_nvenc' in command else 0

        with patch('abu_m54_render._run_encoder', side_effect=run):
            result = encode_video(self.folder, RenderSettings(width=64, height=48, format='mp4'), ffmpeg='local-ffmpeg')
        self.assertEqual(result['encoder'], 'libx264')
        self.assertTrue((self.folder / 'video.mp4').is_file())
        self.assertFalse((self.folder / 'video.partial.mp4').exists())
        self.assertEqual(len(commands), 3)

    def test_missing_encoder_retains_completed_sequence(self):
        frames = self.folder / 'frames'
        frames.mkdir()
        image = frames / 'frame_000000.png'
        image.write_bytes(b'complete frame')
        with patch('abu_m54_render.find_ffmpeg', return_value=None), self.assertRaisesRegex(RuntimeError, 'sequence is complete'):
            encode_video(self.folder, RenderSettings(format='mp4'))
        self.assertEqual(image.read_bytes(), b'complete frame')

    def test_auto_encoder_probe_timeout_falls_back_to_cpu(self):
        def run(command, *args, **kwargs):
            if command[-1] == '-':
                raise RuntimeError('Encoder capability check timed out.')
            self.assertIn('libx264', command)
            Path(command[-1]).write_bytes(b'encoded output')
            return 0
        with patch('abu_m54_render._run_encoder', side_effect=run):
            report = encode_video(self.folder, RenderSettings(format='mp4'), ffmpeg='installed-ffmpeg')
        self.assertEqual(report['encoder'], 'libx264')


@unittest.skipUnless(sys.platform == 'win32' and os.environ.get('ABU_TEST_NATIVE_GPU') == '1',
                     'Set ABU_TEST_NATIVE_GPU=1 for actual local WGL render exports.')
class NativeExportTests(RenderFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        make_scene(self.scene)

    def test_png_jpeg_supersampling_and_unique_output(self):
        outputs = []
        for output_format in ('png', 'jpeg'):
            report, folder = render_job(self.job(RenderSettings(width=96, height=64, format=output_format, supersampling=2)))
            self.assertEqual(report['status'], 'complete', report.get('message'))
            self.assertGreater(report['gpu_buffer_bytes'], 0)
            self.assertEqual(report['gaussian_count'], 3)
            extension = 'jpg' if output_format == 'jpeg' else 'png'
            with Image.open(folder / ('still.' + extension)) as image:
                self.assertEqual(image.size, (96, 64))
                self.assertGreater(np.asarray(image).std(), 5)
            outputs.append(folder)
        self.assertNotEqual(*outputs)

    def test_earth_offset_rebasing_preserves_pixel_output(self):
        from abu_m54_offscreen import RenderTarget
        base = make_scene(self.scene)
        offset = np.array([6371000., -2430000., 1200000.])
        shifted = make_scene(self.folder / 'earth.npz', offset)
        captures = []
        for scene, pose in [(base, camera()), (shifted, camera(offset))]:
            with RenderTarget(64, 48) as target:
                target.set_scene(scene)
                captures.append(np.asarray(target.render(pose)))
        np.testing.assert_array_equal(*captures)

    def test_replacing_scene_releases_gpu_and_renders_ordinary_points(self):
        from abu_m54 import from_records
        from abu_m54_offscreen import RenderTarget
        scene = make_scene(self.scene)
        with RenderTarget(64, 48) as target:
            target.set_scene(scene)
            previous = target.gpu
            target.set_scene(from_records({'points': [[0, 0, -3]], 'colors': [[255, 0, 0]]}))
            self.assertEqual(previous.buffers, [])
            self.assertEqual(previous.programs, [])
            self.assertIsNone(target.gpu)
            pixels = np.asarray(target.render(camera()))
            self.assertGreater(pixels[:, :, 0].max(), 200)
        self.assertIsNone(target.context)
        self.assertIsNone(target.dc)
        self.assertIsNone(target.root)

    def test_cli_worker_emits_done_and_valid_image(self):
        request = self.folder / 'job.json'
        request.write_text(json.dumps(self.job()), encoding='utf-8')
        worker = Path(__file__).resolve().parents[1] / 'abu_m54_render.py'
        process = subprocess.run([sys.executable, '-B', str(worker), '--job', str(request)],
                                 capture_output=True, text=True, timeout=30,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        events = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(events[-1]['event'], 'done')
        with Image.open(Path(events[-1]['output']) / 'still.png') as image:
            self.assertEqual(image.size, (64, 48))

    def test_sequence_count_and_cancel_keep_only_completed_frames(self):
        path = CameraPath((CameraKeyframe(0, camera()), CameraKeyframe(.1, camera((.2, 0, 0)))))
        settings = RenderSettings(width=64, height=48, format='sequence', fps=30)
        job = self.job(settings, path)

        def emit(**event):
            if event.get('frame') == 2:
                Path(job['cancel_file']).touch()

        report, folder = render_job(job, emit)
        self.assertEqual(report['status'], 'cancelled')
        self.assertEqual(report['frames_completed'], 2)
        self.assertEqual(len(list((folder / 'frames').glob('*.png'))), 2)
        self.assertFalse(list(folder.rglob('*.partial')))
        Path(job['cancel_file']).unlink()
        report, folder = render_job(job)
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(report['frames_completed'], 3)
        self.assertEqual(len(list((folder / 'frames').glob('*.png'))), 3)

    @unittest.skipUnless(os.environ.get('ABU_TEST_VIDEO') == '1', 'Set ABU_TEST_VIDEO=1 to run installed FFmpeg.')
    def test_actual_video_encoder_and_decoded_frame_count(self):
        ffmpeg = find_ffmpeg()
        self.assertIsNotNone(ffmpeg)
        path = CameraPath((CameraKeyframe(0, camera()), CameraKeyframe(.1, camera((.1, 0, 0)))))
        report, folder = render_job(self.job(RenderSettings(width=96, height=64, format='mp4', fps=30), path))
        self.assertEqual(report['status'], 'complete', report.get('message'))
        self.assertIn(report['encoder'], ('h264_nvenc', 'libx264'))
        ffprobe = Path(ffmpeg).with_name('ffprobe.exe')
        result = subprocess.run([str(ffprobe), '-v', 'error', '-count_frames', '-select_streams', 'v:0',
                                 '-show_entries', 'stream=width,height,nb_read_frames,r_frame_rate', '-of', 'json',
                                 str(folder / 'video.mp4')], check=True, capture_output=True, text=True,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        stream = json.loads(result.stdout)['streams'][0]
        self.assertEqual((stream['width'], stream['height'], int(stream['nb_read_frames'])), (96, 64, 3))
        self.assertEqual(stream['r_frame_rate'], '30/1')
        # Explicit CPU encoding is also usable when the user selects it.
        cpu_settings = RenderSettings(width=96, height=64, format='mp4', fps=30, encoder='cpu')
        cpu_report, cpu_folder = render_job(self.job(cpu_settings, path))
        self.assertEqual(cpu_report['status'], 'complete', cpu_report.get('message'))
        self.assertEqual(cpu_report['encoder'], 'libx264')
        self.assertTrue((cpu_folder / 'video.mp4').is_file())


if __name__ == '__main__':
    unittest.main()

# SPDX-License-Identifier: Apache-2.0
"""Isolated local M54 image/sequence/video export worker.

No encoder binary is downloaded or redistributed. Video uses the user's own
FFmpeg installation. Rendered PNG frames remain available if encoding fails.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from abu_m54_cameras import CameraPose, CameraPath


class RenderCancelled(Exception):
    pass


@dataclass(frozen=True)
class SequenceSource:
    """Validated local source frames; no large temporary scene copies."""
    sequence: object
    transform: object
    start_index: int


def sequence_source(descriptor):
    from abu_m54 import SceneTransform
    from abu_m54_sequence import PlySequence
    if not isinstance(descriptor, dict):
        raise ValueError('Invalid PLY sequence render source.')
    sequence = PlySequence.from_dict(descriptor['sequence'])
    transform = SceneTransform.from_matrix(descriptor['transform'])
    start = descriptor.get('start_index', 0)
    if isinstance(start, bool) or not isinstance(start, int) or not 0 <= start < sequence.count:
        raise ValueError('Sequence start index is outside the source frame range.')
    return SequenceSource(sequence, transform, start)


def frame_times(duration, fps):
    duration, fps = float(duration), float(fps)
    if not math.isfinite(duration) or not 0 < duration <= 86400:
        raise ValueError('Animation duration must be between 0 and 86400 seconds.')
    if not math.isfinite(fps) or not 1 <= fps <= 240:
        raise ValueError('Frame rate must be between 1 and 240.')
    count = max(1, int(math.ceil(duration * fps - 1e-10)))
    if count > 100000:
        raise ValueError('One export is limited to 100,000 frames. Render longer paths in sections.')
    return [index / fps for index in range(count)]


def find_ffmpeg():
    """Discover an existing encoder only; this never installs software."""
    candidates = [os.environ.get('ABU_FFMPEG', ''), shutil.which('ffmpeg'),
                  str(Path.home() / 'ffmpeg' / 'bin' / 'ffmpeg.exe'),
                  r'C:\ffmpeg\bin\ffmpeg.exe', r'C:\Program Files\ffmpeg\bin\ffmpeg.exe']
    return next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()), None)


def _cancelled(cancel_file):
    if cancel_file and Path(cancel_file).is_file():
        raise RenderCancelled('Rendering cancelled. Completed images have been kept.')


def _run_encoder(command, log_path, cancel_file, timeout=None):
    """No pipes to deadlock, no shell, and cancellation reaps the child process."""
    started = time.monotonic()
    with Path(log_path).open('wb') as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while process.poll() is None:
                _cancelled(cancel_file)
                if timeout is not None and time.monotonic() - started > timeout:
                    raise RuntimeError('Encoder capability check timed out.')
                time.sleep(.1)
            return process.returncode
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


def encode_video(folder, settings, cancel_file=None, emit=lambda **kwargs: None, ffmpeg=None):
    """Probe real NVENC operation; auto retries CPU if the full GPU encode fails."""
    folder = Path(folder)
    requested = getattr(settings, 'ffmpeg_path', '')
    if requested and not Path(requested).is_file():
        raise RuntimeError('The selected FFmpeg executable was not found. PNG frames are preserved.')
    ffmpeg = ffmpeg or requested or find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError('FFmpeg was not found. Your PNG sequence is complete. Install FFmpeg or set ABU_FFMPEG to its executable, then encode the sequence.')
    encoder = settings.encoder
    # Test actual device initialization rather than merely trusting -encoders.
    use_nvenc = False
    if encoder in ('auto', 'nvenc'):
        probe = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-f', 'lavfi',
                 '-i', 'color=c=black:s=320x240:r=30', '-frames:v', '1', '-c:v', 'h264_nvenc',
                 '-f', 'null', '-']
        try:
            use_nvenc = _run_encoder(probe, folder / 'nvenc_probe.log', cancel_file, 20) == 0
        except RenderCancelled:
            raise
        except (RuntimeError, OSError):
            if encoder == 'nvenc':
                raise
            use_nvenc = False
        if not use_nvenc and encoder == 'nvenc':
            raise RuntimeError('NVIDIA video encoding is unavailable. PNG frames were kept; choose Auto or CPU to encode them.')
        if not use_nvenc:
            emit(event='progress', message='NVIDIA encoder unavailable; encoding on CPU.', stage='encode')
    chosen = 'h264_nvenc' if use_nvenc else 'libx264'
    crf = max(0, min(51, int(round(51 * (1 - settings.quality / 100)))))
    partial = folder / 'video.partial.mp4'
    final = folder / 'video.mp4'

    def command(codec):
        quality_args = ['-cq', str(crf), '-b:v', '0', '-preset', 'p5'] if codec == 'h264_nvenc' else ['-crf', str(crf), '-preset', 'medium']
        return [ffmpeg, '-hide_banner', '-loglevel', 'warning', '-nostdin', '-n',
                '-framerate', format(settings.fps, '.12g'), '-start_number', '0',
                '-i', str(folder / 'frames' / 'frame_%06d.png'), '-an', '-c:v', codec,
                *quality_args, '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(partial)]

    emit(event='progress', message=f'Encoding video with {chosen}.', stage='encode')
    try:
        code = _run_encoder(command(chosen), folder / 'encoder.log', cancel_file)
        if code and chosen == 'h264_nvenc' and encoder == 'auto':
            partial.unlink(missing_ok=True)
            chosen = 'libx264'
            emit(event='progress', message='NVIDIA encode failed; retrying on CPU. PNG frames are preserved.', stage='encode')
            code = _run_encoder(command(chosen), folder / 'encoder_cpu_retry.log', cancel_file)
        _cancelled(cancel_file)
        if code or not partial.is_file() or partial.stat().st_size == 0:
            raise RuntimeError('Video encoder failed. PNG frames and the encoder log are preserved in the output folder.')
        partial.replace(final)
    finally:
        partial.unlink(missing_ok=True)
    return {'encoder': chosen, 'encoder_path': ffmpeg, 'crf_or_cq': crf, 'video': str(final)}


def validate_job(job):
    from abu_m54_cameras import RenderSettings
    if not isinstance(job, dict) or job.get('schema') != 1:
        raise ValueError('Unsupported M54 render job schema.')
    if job.get('source_sequence') is not None:
        scene_path = sequence_source(job['source_sequence'])
    else:
        scene_path = Path(job['scene']).expanduser().resolve()
        if not scene_path.is_file() or scene_path.suffix.lower() != '.npz':
            raise ValueError('Render scene must be a saved M54 scene (.npz).')
    output = Path(job['output']).expanduser().resolve()
    if not output.is_dir():
        raise ValueError('Choose an existing output folder.')
    settings = RenderSettings.from_dict(job['settings'])
    # Never allow UI defaults or crafted JSON to request an unbounded framebuffer.
    rw, rh = settings.width * settings.supersampling, settings.height * settings.supersampling
    if max(rw, rh) > 8192 or rw * rh > 33554432:
        raise ValueError('Resolution × supersampling exceeds the 8192 edge / 32 megapixel render limit.')
    if settings.format == 'mp4' and (settings.width % 2 or settings.height % 2):
        raise ValueError('MP4 width and height must be even numbers.')
    camera = CameraPose.from_dict(job['camera'])
    path = CameraPath.from_dict(job['path']) if job.get('path') is not None else None
    times = [0.]
    if settings.format in ('sequence', 'mp4'):
        if isinstance(scene_path, SequenceSource):
            times = frame_times(scene_path.sequence.duration, settings.fps)
        elif path is None or len(path.keyframes) < 2:
            raise ValueError('Image sequences and videos need at least two timed camera keyframes.')
        else:
            times = frame_times(path.duration, settings.fps)
    cancel_file = str(Path(job['cancel_file']).resolve()) if job.get('cancel_file') else None
    return scene_path, output, settings, camera, path, times, cancel_file


def render_job(job, emit=lambda **kwargs: None):
    scene_path, output, settings, camera, camera_path, times, cancel_file = validate_job(job)
    source = scene_path if isinstance(scene_path, SequenceSource) else None
    _cancelled(cancel_file)
    folder = output / ('m54_render_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
    folder.mkdir(exist_ok=False)
    report = {'schema': 1, 'status': 'running', 'frames_completed': 0, 'frames_requested': len(times),
              'settings': settings.to_dict(), 'frame_times_seconds': times,
              'camera': camera.to_dict(), 'path': camera_path.to_dict() if camera_path else None,
              'limitations': ['Native export requires Windows OpenGL 4.3+.',
                              'Ordinary clouds render the loaded preview points; Gaussian scenes render the full asset.',
                              'Exports contain scene geometry only, without grid, control, or camera overlays.',
                              'Frames sample time i/fps before the endpoint; count is ceil(animation duration × fps).',
                              'Colors accumulate in RGBA16F and export as 8-bit RGB.']}
    if source is not None:
        report['source_sequence'] = source.sequence.to_dict()
        report['source_transform'] = source.transform.matrix().tolist()
        report['source_frames'] = []
        report['source_duration_seconds'] = source.sequence.duration
        report['limitations'].append('Source frames are held between timestamps, without invented geometry interpolation. Animated exports begin at the first source frame; camera paths clamp at their end.')
    started = time.monotonic()
    emit(event='progress', frame=0, total=len(times), output=str(folder), message='Loading immutable render scene.', stage='load')
    try:
        from control_points_comparison import read_scene
        from abu_m54_offscreen import RenderTarget
        scene = read_scene(scene_path) if source is None else None
        _cancelled(cancel_file)
        rw, rh = settings.width * settings.supersampling, settings.height * settings.supersampling
        with RenderTarget(rw, rh, settings.background) as target:
            if scene is not None:
                target.set_scene(scene)
                report.update(gpu_buffer_bytes=target.buffer_bytes,
                              gaussian_count=scene['gaussians'].count if scene.get('gaussians') else 0,
                              loaded_point_count=len(scene.get('points', [])))
            report.update(device=target.device, opengl=target.version)
            loaded_index = None
            frames_folder = folder / 'frames'
            if settings.format in ('sequence', 'mp4'):
                frames_folder.mkdir()
            for index, timestamp in enumerate(times):
                _cancelled(cancel_file)
                if source is not None:
                    source_index = (source.sequence.frame_index(timestamp, loop=False)
                                    if settings.format in ('sequence', 'mp4') else source.start_index)
                    source_path = source.sequence.verify_frame(source_index)
                    if source_index != loaded_index:
                        emit(event='progress', frame=index, total=len(times), output=str(folder),
                             message=f'Loading source frame {source_index + 1} of {source.sequence.count}.', stage='load')
                        from abu_m54 import load_scene, transform_scene
                        scene = transform_scene(load_scene(source_path, attach_companions=False), source.transform)
                        source.sequence.verify_frame(source_index)
                        _cancelled(cancel_file)
                        target.set_scene(scene)
                        loaded_index = source_index
                        report['gpu_buffer_bytes'] = max(report.get('gpu_buffer_bytes', 0), target.buffer_bytes)
                        report['gaussian_count'] = scene['gaussians'].count if scene.get('gaussians') else 0
                        report['peak_gaussian_count'] = max(report.get('peak_gaussian_count', 0), report['gaussian_count'])
                        report['loaded_point_count'] = len(scene.get('points', []))
                pose = camera_path.sample(timestamp) if camera_path is not None and settings.format in ('sequence', 'mp4') else camera
                image = target.render(pose, settings.near, settings.far, (settings.width, settings.height))
                _cancelled(cancel_file)
                if settings.format == 'jpeg':
                    destination, image_format = folder / 'still.jpg', 'JPEG'
                elif settings.format == 'png':
                    destination, image_format = folder / 'still.png', 'PNG'
                else:
                    destination, image_format = frames_folder / f'frame_{index:06d}.png', 'PNG'
                temporary = destination.with_suffix('.partial')
                try:
                    options = {'quality': max(1, settings.quality), 'subsampling': 0} if image_format == 'JPEG' else {'compress_level': 3}
                    image.save(temporary, format=image_format, **options)
                    temporary.replace(destination)
                finally:
                    image.close()
                    temporary.unlink(missing_ok=True)
                report['frames_completed'] = index + 1
                if source is not None:
                    report['source_frames'].append({'output_index': index, 'source_index': source_index,
                                                    'source_name': source_path.name, 'time_seconds': timestamp,
                                                    'gaussian_count': report['gaussian_count']})
                emit(event='progress', frame=index + 1, total=len(times), output=str(folder),
                     message=f'Rendered {index + 1} of {len(times)}.', stage='render')
        if settings.format == 'mp4':
            report.update(encode_video(folder, settings, cancel_file, emit))
            report['encoded_duration_seconds'] = len(times) / settings.fps
        report['status'] = 'complete'
    except RenderCancelled as error:
        report.update(status='cancelled', message=str(error))
        emit(event='cancelled', output=str(folder), message=str(error))
    except Exception as error:
        report.update(status='failed', message=str(error))
        emit(event='error', output=str(folder), message=str(error))
    finally:
        report['elapsed_seconds'] = time.monotonic() - started
        (folder / 'render_report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    if report['status'] == 'complete':
        emit(event='done', output=str(folder), report=str(folder / 'render_report.json'), message='Render complete.')
    return report, folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', required=True)
    args = parser.parse_args()

    def emit(**value):
        print(json.dumps(value, ensure_ascii=True, allow_nan=False), flush=True)

    try:
        path = Path(args.job)
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('Render request exceeds 16 MiB.')
        report, _ = render_job(json.loads(path.read_text(encoding='utf-8')), emit)
        return 0 if report['status'] == 'complete' else 2 if report['status'] == 'cancelled' else 1
    except RenderCancelled as error:
        emit(event='cancelled', message=str(error))
        return 2
    except Exception as error:
        emit(event='error', message=str(error))
        return 1


if __name__ == '__main__':
    sys.exit(main())

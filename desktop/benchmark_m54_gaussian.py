# SPDX-License-Identifier: Apache-2.0
"""Local synthetic native-GPU Gaussian quality/performance qualification.

No client files are read. The hidden native context renders into an FBO; captures
are synthetic fixtures only. GPU timestamps and synchronized wall times are
reported separately, and are not presented as interactive application FPS.
"""
from __future__ import annotations

import argparse
import ctypes as ct
from ctypes import wintypes as wt
import gc
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time
import tkinter as tk

import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
try:
    from scipy.special import sph_harm_y
except ImportError:  # SciPy before 1.15 uses the opposite argument order.
    from scipy.special import sph_harm

    def sph_harm_y(degree, order, polar, azimuth):
        return sph_harm(order, degree, azimuth, polar)

from abu_m54_gaussian import GaussianAsset

BACKGROUND = np.array([.067, .083, .094], dtype=np.float64)


def perspective(width, height, fov=60., near=.05, far=100.):
    f = 1. / np.tan(np.deg2rad(fov) / 2.)
    p = np.zeros((4, 4), dtype=np.float64)
    p[0, 0], p[1, 1] = f * height / width, f
    p[2, 2], p[2, 3], p[3, 2] = (far + near) / (near - far), 2 * far * near / (near - far), -1
    return p


def synthetic_asset(count=1000, degree=3, seed=54, large_world=False):
    """Nonzero SH, anisotropic covariance and nontrivial orientations."""
    rng = np.random.default_rng(seed)
    positions = rng.uniform([-1.6, -1.05, -5.8], [1.6, 1.05, -2.2], (count, 3))
    if count == 3:
        positions = np.array([[-.16, -.08, -3.2], [.06, .04, -3.5], [.22, -.04, -2.8]])
    size = .055 if count < 10000 else .008
    scales = rng.uniform(.35, 1.8, (count, 3)) * size
    if count == 3:
        scales = np.array([[.28, .11, .07], [.18, .08, .24], [.13, .21, .08]])
    # Rotation.random uses a validated independent implementation.
    xyzw = Rotation.random(count, random_state=rng).as_quat()
    sh = rng.normal(0, .04, (count, 3, (degree + 1) ** 2))
    sh[:, :, 0] = (rng.uniform(.12, .88, (count, 3)) - .5) / math.sqrt(1 / (4 * math.pi))
    opacities = rng.uniform(.2, .85, count)
    if large_world:
        positions += np.array([6371000., -2430000., 1200000.])
    return GaussianAsset(positions, scales, xyzw[:, [3, 0, 1, 2]], opacities, sh, source='synthetic-native-benchmark')


def reference_image(asset, view, projection, width, height, model=None, origin=None, scale=1.):
    """Independent float64 reference using SciPy SH/quaternions, not GPU code.

    Top-left image origin, pixel centers, 0.3 pixel covariance filter, 3-sigma
    footprint, 1/255 alpha cutoff and 0.99 alpha cap. Sort full eye-space depths.
    """
    model = np.eye(4) if model is None else np.asarray(model, dtype=np.float64)
    origin = np.zeros(3) if origin is None else np.asarray(origin, dtype=np.float64)
    view, projection = np.asarray(view, dtype=np.float64), np.asarray(projection, dtype=np.float64)
    normalized = np.eye(4)
    normalized[:3, :3] /= scale
    normalized[:3, 3] = -origin / scale
    model_view = view @ normalized @ model
    camera_object = np.linalg.inv(model_view)[:3, 3]
    directions = asset.positions - camera_object
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    theta = np.arccos(np.clip(directions[:, 2], -1, 1))
    phi = np.arctan2(directions[:, 1], directions[:, 0])
    basis = []
    for degree in range(asset.degree + 1):
        for order in range(-degree, degree + 1):
            harmonic = sph_harm_y(degree, abs(order), theta, phi)
            basis.append(harmonic.real if order == 0 else math.sqrt(2) * (harmonic.imag if order < 0 else harmonic.real))
    rgb = np.maximum(.5 + np.einsum('nck,kn->nc', asset.sh.astype(np.float64), np.asarray(basis)), 0.)
    rotations = Rotation.from_quat(asset.rotations_wxyz[:, [1, 2, 3, 0]]).as_matrix()
    eye_points = asset.positions @ model_view[:3, :3].T + model_view[:3, 3]
    output = np.broadcast_to(BACKGROUND, (height, width, 3)).copy()
    for index in np.argsort(eye_points[:, 2], kind='stable'):
        eye = eye_points[index]
        clip = projection @ np.r_[eye, 1.]
        if clip[3] <= 0 or abs(clip[2]) > clip[3]:
            continue
        ndc = clip[:2] / clip[3]
        center = np.array([(ndc[0] + 1) * width / 2., (1 - ndc[1]) * height / 2.])
        # Linearize inside a modest view guard band, keeping the actual center.
        # This independent float64 matrix derivative checks the GPU's bounded
        # first-order projection, including extreme offscreen near-eye means.
        linearization = eye.copy()
        limits = -eye[2] * 1.3 / np.diag(projection)[:2]
        linearization[:2] = np.clip(linearization[:2], -limits, limits)
        linear_clip = projection @ np.r_[linearization, 1.]
        jacobian = (projection[:2, :3] * linear_clip[3] - linear_clip[:2, None] * projection[3, :3]) / linear_clip[3] ** 2
        jacobian *= np.array([width / 2., -height / 2.])[:, None]
        axes = model_view[:3, :3] @ rotations[index] @ np.diag(asset.scales[index].astype(np.float64))
        covariance = jacobian @ axes @ axes.T @ jacobian.T + np.eye(2) * .3
        radius = 3 * np.sqrt(np.linalg.eigvalsh(covariance)[-1])
        xmin, xmax = max(0, int(np.floor(center[0] - radius))), min(width, int(np.ceil(center[0] + radius)))
        ymin, ymax = max(0, int(np.floor(center[1] - radius))), min(height, int(np.ceil(center[1] + radius)))
        if xmin >= xmax or ymin >= ymax:
            continue
        yy, xx = np.mgrid[ymin:ymax, xmin:xmax]
        delta = np.stack([xx + .5 - center[0], yy + .5 - center[1]], axis=-1)
        q = np.einsum('...i,ij,...j->...', delta, np.linalg.inv(covariance), delta)
        alpha = np.minimum(.99, float(asset.opacities[index]) * np.exp(-.5 * q))
        alpha[(q > 9) | (alpha < 1 / 255)] = 0.
        target = output[ymin:ymax, xmin:xmax]
        target[:] = rgb[index] * alpha[..., None] + target * (1 - alpha[..., None])
    return output


class NativeTarget:
    """Hidden WGL compatibility context plus explicit offscreen framebuffer."""
    def __init__(self, width, height, floating=False):
        if sys.platform != 'win32':
            raise RuntimeError('The current native prototype benchmark requires Windows WGL.')
        from abu_m54_native import PixelFormat
        self.root = tk.Tk(); self.root.withdraw(); self.root.update_idletasks()
        self.user, self.gdi, self.gl = ct.WinDLL('user32'), ct.WinDLL('gdi32'), ct.WinDLL('opengl32')
        self.user.GetDC.argtypes = [wt.HWND]; self.user.GetDC.restype = wt.HDC
        self.user.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
        self.gdi.ChoosePixelFormat.argtypes = [wt.HDC, ct.POINTER(PixelFormat)]
        self.gdi.SetPixelFormat.argtypes = [wt.HDC, ct.c_int, ct.POINTER(PixelFormat)]
        self.gl.wglCreateContext.argtypes = [wt.HDC]; self.gl.wglCreateContext.restype = ct.c_void_p
        self.gl.wglMakeCurrent.argtypes = [wt.HDC, ct.c_void_p]; self.gl.wglDeleteContext.argtypes = [ct.c_void_p]
        self.gl.wglGetProcAddress.argtypes = [ct.c_char_p]; self.gl.wglGetProcAddress.restype = ct.c_void_p
        self.hwnd = self.root.winfo_id(); self.dc = self.user.GetDC(self.hwnd)
        pixel = PixelFormat(); pixel.nSize = ct.sizeof(pixel); pixel.nVersion = 1
        pixel.dwFlags = 4 | 32 | 1; pixel.iPixelType = 0; pixel.cColorBits = 32; pixel.cDepthBits = 24
        pf = self.gdi.ChoosePixelFormat(self.dc, ct.byref(pixel))
        if not pf or not self.gdi.SetPixelFormat(self.dc, pf, ct.byref(pixel)):
            raise RuntimeError('Native pixel format unavailable.')
        self.context = self.gl.wglCreateContext(self.dc)
        if not self.context or not self.gl.wglMakeCurrent(self.dc, self.context):
            raise RuntimeError('Native context unavailable.')
        self.width, self.height, self.floating = width, height, floating
        self._functions = {}
        self.gl.glGetString.argtypes = [ct.c_uint]; self.gl.glGetString.restype = ct.c_char_p
        self.renderer = self.gl.glGetString(0x1F01).decode()
        self.version = self.gl.glGetString(0x1F02).decode()
        self.texture = ct.c_uint(); self.framebuffer = ct.c_uint()
        self.fn('glGenTextures', None, ct.c_int, ct.POINTER(ct.c_uint))(1, ct.byref(self.texture))
        self.fn('glBindTexture', None, ct.c_uint, ct.c_uint)(0x0DE1, self.texture)
        self.fn('glTexImage2D', None, ct.c_uint, ct.c_int, ct.c_int, ct.c_int, ct.c_int, ct.c_int, ct.c_uint, ct.c_uint, ct.c_void_p)(0x0DE1, 0, 0x8814 if floating else 0x8058, width, height, 0, 0x1908, 0x1406, None)
        self.fn('glGenFramebuffers', None, ct.c_int, ct.POINTER(ct.c_uint))(1, ct.byref(self.framebuffer))
        self.fn('glBindFramebuffer', None, ct.c_uint, ct.c_uint)(0x8D40, self.framebuffer)
        self.fn('glFramebufferTexture2D', None, ct.c_uint, ct.c_uint, ct.c_uint, ct.c_uint, ct.c_int)(0x8D40, 0x8CE0, 0x0DE1, self.texture, 0)
        status = self.fn('glCheckFramebufferStatus', ct.c_uint, ct.c_uint)(0x8D40)
        if status != 0x8CD5:
            raise RuntimeError(f'Incomplete native benchmark framebuffer: {status:#x}')
        self.fn('glDisable', None, ct.c_uint)(0x0BD0)  # Dither off for reproducible RGBA8.
        self.fn('glViewport', None, ct.c_int, ct.c_int, ct.c_int, ct.c_int)(0, 0, width, height)

    def fn(self, name, result, *args):
        if name not in self._functions:
            try:
                function = getattr(self.gl, name)
                function.restype, function.argtypes = result, list(args)
            except AttributeError:
                address = self.gl.wglGetProcAddress(name.encode())
                if not address or address in (1, 2, 3, ct.c_void_p(-1).value):
                    raise RuntimeError(f'Missing native GL function: {name}')
                function = ct.WINFUNCTYPE(result, *args)(address)
            self._functions[name] = function
        return self._functions[name]

    def clear(self):
        self.fn('glClearColor', None, *([ct.c_float] * 4))(*BACKGROUND, 1.)
        self.fn('glClear', None, ct.c_uint)(0x4000)

    def finish(self):
        self.fn('glFinish', None)()

    def capture(self):
        array = np.empty((self.height, self.width, 4), dtype=np.float32)
        self.fn('glReadPixels', None, ct.c_int, ct.c_int, ct.c_int, ct.c_int, ct.c_uint, ct.c_uint, ct.c_void_p)(0, 0, self.width, self.height, 0x1908, 0x1406, array.ctypes.data)
        return array[::-1, :, :3].copy()

    def error(self):
        return self.fn('glGetError', ct.c_uint)()

    def close(self):
        if self.context:
            self.fn('glBindFramebuffer', None, ct.c_uint, ct.c_uint)(0x8D40, 0)
            self.fn('glDeleteFramebuffers', None, ct.c_int, ct.POINTER(ct.c_uint))(1, ct.byref(self.framebuffer))
            self.fn('glDeleteTextures', None, ct.c_int, ct.POINTER(ct.c_uint))(1, ct.byref(self.texture))
            self.gl.wglMakeCurrent(None, None); self.gl.wglDeleteContext(self.context); self.context = None
            self.user.ReleaseDC(self.hwnd, self.dc)
        self.root.destroy()


def image_metrics(actual, reference):
    delta = np.asarray(actual, dtype=np.float64) - reference
    mse = float(np.mean(delta ** 2))
    return dict(rmse=math.sqrt(mse), psnr_db=float(-10 * math.log10(max(mse, 1e-30))), max_absolute=float(np.max(np.abs(delta))))


def vram_snapshot():
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.used,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=True)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def run_quality(output):
    from abu_m54_splat_gpu import GaussianRenderer
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    target = NativeTarget(256, 192, floating=True)
    renderer = GaussianRenderer(target.gl)
    reports = []
    try:
        for count, degree, transformed, large_world in [(3, 0, False, False), (3, 1, False, False), (3, 2, False, False), (3, 3, False, False), (1000, 3, False, False), (1000, 3, True, False), (1000, 3, False, True)]:
            asset = synthetic_asset(count, degree, large_world=large_world)
            model, view = np.eye(4), np.eye(4)
            origin = np.array([6371000., -2430000., 1200000.]) if large_world else np.zeros(3)
            if transformed:
                model[:3, :3] = Rotation.from_euler('xyz', [4, 8, 21], degrees=True).as_matrix() * 1.1
                model[:3, 3] = [.1, -.05, .1]
            projection = perspective(target.width, target.height)
            renderer.set_asset(asset)
            target.clear(); renderer.draw(view, projection, target.width, target.height, model=model, origin=origin, scale=1.)
            target.finish(); actual = target.capture()
            expected = reference_image(asset, view, projection, target.width, target.height, model=model, origin=origin)
            metrics = image_metrics(actual, expected)
            # An independent float64 reference compared with FP32 GPU and blending.
            passed = metrics['psnr_db'] >= 45 and metrics['rmse'] <= .005
            name = f'quality_n{count}_sh{degree}_transform{int(transformed)}_earth{int(large_world)}'
            for suffix, image in [('gpu', actual), ('reference', expected), ('error_x10', np.abs(actual - expected) * 10)]:
                Image.fromarray(np.uint8(np.clip(image, 0, 1) * 255 + .5)).save(output / f'{name}_{suffix}.png')
            reports.append(dict(name=name, splats=count, degree=degree, transformed=transformed, large_world=large_world, passed=passed, **metrics))
        error = target.error()
        if error:
            raise RuntimeError(f'GPU quality test GL error: {error:#x}')
        return dict(renderer=target.renderer, opengl=target.version, resolution=[target.width, target.height], framebuffer='RGBA32F', reference='independent NumPy float64 / SciPy SH and rotations', threshold='PSNR >=45 dB and RMSE <=0.005', cases=reports, passed=all(x['passed'] for x in reports))
    finally:
        renderer.close(); target.close()


def run_performance(counts=(100000, 1000000, 5000000), frames=20, warmup=5, output=None):
    from abu_m54_splat_gpu import GaussianRenderer
    import psutil
    before = vram_snapshot(); target = NativeTarget(1920, 1080)
    renderer = GaussianRenderer(target.gl); results = []
    try:
        for count in counts:
            started = time.perf_counter(); asset = synthetic_asset(count, degree=3); renderer.set_asset(asset); target.finish()
            upload_seconds = time.perf_counter() - started
            times, gpu = [], []
            projection = perspective(target.width, target.height)
            for index in range(warmup + frames):
                # Fixed deterministic movement; sorting must update for each view.
                view = np.eye(4); view[:3, :3] = Rotation.from_euler('y', (index % 7 - 3) * .4, degrees=True).as_matrix()
                target.clear(); tick = time.perf_counter()
                renderer.draw(view, projection, target.width, target.height)
                target.finish()
                elapsed = (time.perf_counter() - tick) * 1000
                renderer.poll_timing()
                if index >= warmup:
                    times.append(elapsed)
                    value = getattr(renderer, 'last_gpu_ms', None)
                    if value is not None and value > 0:
                        gpu.append(float(value))
            # Debug readback is outside timing: prove sorting retained every
            # visible synthetic Gaussian instead of silently sampling/dropping.
            order = np.empty((count, 2), dtype=np.uint32)
            target.fn('glBindBuffer', None, ct.c_uint, ct.c_uint)(0x90D2, renderer.buffers[1])
            target.fn('glGetBufferSubData', None, ct.c_uint, ct.c_ssize_t, ct.c_ssize_t, ct.c_void_p)(0x90D2, 0, order.nbytes, order.ctypes.data)
            target.fn('glBindBuffer', None, ct.c_uint, ct.c_uint)(0x90D2, 0)
            valid = order[:, 1] < count
            descending = bool(np.all(order[:-1, 0] >= order[1:, 0]))
            unique = bool(valid.all() and np.all(np.bincount(order[:, 1].astype(np.int64), minlength=count) == 1))
            if not descending or not unique:
                raise RuntimeError('Synthetic performance source indices/depth order did not survive GPU preparation and sorting.')
            if output is not None:
                image = target.capture()
                Image.fromarray(np.uint8(np.clip(image, 0, 1) * 255 + .5)).save(Path(output) / f'performance_{count}_1080p.png')
            results.append(dict(splats=count, sh_degree=3, frames=frames, warmup=warmup, resolution=[1920, 1080], create_upload_seconds=upload_seconds, synchronized_wall_median_ms=statistics.median(times), synchronized_wall_p95_ms=float(np.percentile(times, 95)), offscreen_fps_from_wall_median=1000/statistics.median(times), gpu_median_ms=statistics.median(gpu) if gpu else None, gpu_p95_ms=float(np.percentile(gpu, 95)) if gpu else None, resident_gpu_bytes=int(renderer.allocated_bytes), process_rss_bytes=psutil.Process().memory_info().rss, total_device_vram_sample=vram_snapshot(), verified_unique_visible_source_indices=count, verified_depth_descending=descending))
            print(json.dumps(results[-1]), flush=True)
            del asset, order; gc.collect()
        error = target.error()
        if error:
            raise RuntimeError(f'GPU performance GL error: {error:#x}')
    finally:
        renderer.close(); target.finish(); target.close(); gc.collect()
    return dict(cases=results, total_device_vram_before=before, total_device_vram_after=vram_snapshot(), interpretation='Synthetic offscreen rendering, not application interaction FPS. Wall time includes glFinish; excludes asset creation/upload, presentation, event dispatch and UI. VRAM samples include other processes and are not isolated allocation measurements.')


def run_native_host(counts=(1000000, 5000000), frames=20, warmup=5):
    """Exercise the actual compact M54 window, including SwapBuffers and Tk idle."""
    from abu_m54 import from_records
    from abu_m54_desktop import prepare_desktop
    from abu_m54_host import ViewerHost
    from abu_m54_native import M54NativeViewer
    import psutil
    if sys.platform != 'win32':
        raise RuntimeError('Native presentation qualification currently requires Windows.')
    dpi = prepare_desktop()
    root = tk.Tk(); root.withdraw()
    root.title('Abu M54 synthetic GPU benchmark - closes automatically')
    root.geometry('1920x1080+24+24')
    viewer = M54NativeViewer(ViewerHost(root), root, compact=True)
    viewer.pack(fill='both', expand=True)
    before = vram_snapshot(); cases = []
    try:
        root.deiconify(); root.update()
        if not viewer.context:
            viewer.initialize()
        if not viewer.context:
            raise RuntimeError('M54 native window could not create its GL context.')
        viewer.gl.glFinish.argtypes = []
        viewer.gl.wglGetProcAddress.argtypes = [ct.c_char_p]
        viewer.gl.wglGetProcAddress.restype = ct.c_void_p
        interval = None
        address = viewer.gl.wglGetProcAddress(b'wglGetSwapIntervalEXT') if hasattr(viewer.gl, 'wglGetProcAddress') else None
        if address and address not in (1, 2, 3, ct.c_void_p(-1).value):
            interval = int(ct.WINFUNCTYPE(ct.c_int)(address)())
        for count in counts:
            started = time.perf_counter(); asset = synthetic_asset(count, degree=3)
            points, colors = asset.preview()
            scene = from_records(dict(points=points, colors=colors, cameras=[], path=f'synthetic-native-host-{count}'))
            scene['gaussians'] = asset; scene['gaussian_transform'] = np.eye(4)
            scene['total_points'] = count
            viewer.set_data(scene); root.update_idletasks(); viewer.draw(); viewer.gl.glFinish()
            load_seconds = time.perf_counter() - started
            if viewer.gaussian_failure or viewer.gaussian_renderer is None or viewer.gaussian_renderer.count != count:
                raise RuntimeError(f'M54 native host did not render the complete Gaussian source: {viewer.gaussian_status}')
            width, height = viewer.surface.winfo_width(), viewer.surface.winfo_height()
            times, gpu = [], []
            for index in range(warmup + frames):
                tick = time.perf_counter()
                viewer.yaw = -25. + index * .4
                viewer.draw(); viewer.gl.glFinish(); root.update_idletasks()
                elapsed = (time.perf_counter() - tick) * 1000
                viewer.gaussian_renderer.poll_timing()
                if index >= warmup:
                    times.append(elapsed)
                    if viewer.gaussian_renderer.last_gpu_ms is not None:
                        gpu.append(float(viewer.gaussian_renderer.last_gpu_ms))
            if viewer.gl.glGetError():
                raise RuntimeError('Native host benchmark reported a GL error.')
            item = dict(splats=count, rendered_gaussian_count=viewer.gaussian_renderer.count, point_preview_for_picking=len(points), sh_degree=3, resolution=[width, height], frames=frames, warmup=warmup, create_upload_seconds=load_seconds, native_present_wall_median_ms=statistics.median(times), native_present_wall_p95_ms=float(np.percentile(times, 95)), fps_from_present_wall_median=1000/statistics.median(times), gpu_median_ms=statistics.median(gpu) if gpu else None, gpu_p95_ms=float(np.percentile(gpu, 95)) if gpu else None, resident_gpu_bytes=int(viewer.gaussian_renderer.allocated_bytes), process_rss_bytes=psutil.Process().memory_info().rss, host_status=viewer.gaussian_status, window_mapped=bool(viewer.winfo_ismapped()), total_device_vram_sample=vram_snapshot())
            cases.append(item); print(json.dumps(item), flush=True)
            del scene, asset, points, colors; gc.collect()
        result = dict(renderer=viewer.renderer, opengl=viewer.version, dpi_policy=dpi, reported_wgl_swap_interval=interval, cases=cases, total_device_vram_before=before, interpretation='Actual visible compact M54 native window and resident Gaussian rendering; synchronized wall time includes draw, SwapBuffers, glFinish and Tk idle work. VSync/compositor/driver scheduling may affect timing. Physical input latency, scanout latency and general user-driven event dispatch are not measured. Synthetic scenes only; no client files or desktop captures.')
    finally:
        viewer.close(); root.destroy(); gc.collect()
    result['total_device_vram_after'] = vram_snapshot()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--counts', default='100000,1000000,5000000')
    parser.add_argument('--frames', type=int, default=20)
    parser.add_argument('--quality-only', action='store_true')
    parser.add_argument('--host-only', action='store_true', help='Benchmark actual native M54 presentation in a temporary synthetic-only window.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.host_only:
        report = run_native_host(tuple(int(x) for x in args.counts.split(',')), args.frames)
        (args.output / 'host_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
        return 0
    report = dict(quality=run_quality(args.output))
    if not args.quality_only:
        report['performance'] = run_performance(tuple(int(x) for x in args.counts.split(',')), args.frames, output=args.output)
    destination = args.output / 'benchmark.json'
    destination.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['quality']['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

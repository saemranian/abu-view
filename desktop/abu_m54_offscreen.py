# SPDX-License-Identifier: Apache-2.0
"""Local, overlay-free native M54 rendering into an explicit framebuffer.

The renderer and shaders are shared with the interactive viewport. This module
owns only its hidden WGL context, output framebuffer, and readback resources.
"""
from __future__ import annotations

import ctypes as ct
from ctypes import wintypes as wt
import sys
import tkinter as tk

import numpy as np
from PIL import Image


class RenderTarget:
    """One process-local Windows OpenGL target. Close before exiting the worker."""

    def __init__(self, width, height, background=(.067, .083, .094)):
        if sys.platform != 'win32':
            raise RuntimeError('Native M54 image export currently requires Windows OpenGL 4.3+.')
        self.width, self.height = int(width), int(height)
        if not (16 <= self.width <= 8192 and 16 <= self.height <= 8192):
            raise ValueError('Render dimensions must be between 16 and 8192 pixels.')
        if self.width * self.height > 33554432:
            raise ValueError('Render target exceeds the 32 megapixel memory limit.')
        self.background = tuple(float(x) for x in background)
        if len(self.background) != 3 or not all(np.isfinite(x) and 0 <= x <= 1 for x in self.background):
            raise ValueError('Background must have three values between 0 and 1.')
        self.root = None
        self.context = self.dc = None
        self.gpu = None
        self.texture = ct.c_uint()
        self.framebuffer = ct.c_uint()
        self.depth = ct.c_uint()
        self._functions = {}
        try:
            self._initialize()
        except Exception:
            self.close()
            raise

    def _initialize(self):
        from abu_m54_native import PixelFormat
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.update_idletasks()
        self.user, self.gdi, self.gl = ct.WinDLL('user32'), ct.WinDLL('gdi32'), ct.WinDLL('opengl32')
        self.user.GetDC.argtypes, self.user.GetDC.restype = [wt.HWND], wt.HDC
        self.user.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
        self.gdi.ChoosePixelFormat.argtypes = [wt.HDC, ct.POINTER(PixelFormat)]
        self.gdi.SetPixelFormat.argtypes = [wt.HDC, ct.c_int, ct.POINTER(PixelFormat)]
        self.gl.wglCreateContext.argtypes, self.gl.wglCreateContext.restype = [wt.HDC], ct.c_void_p
        self.gl.wglMakeCurrent.argtypes = [wt.HDC, ct.c_void_p]
        self.gl.wglDeleteContext.argtypes = [ct.c_void_p]
        self.gl.wglGetProcAddress.argtypes, self.gl.wglGetProcAddress.restype = [ct.c_char_p], ct.c_void_p
        self.hwnd = self.root.winfo_id()
        self.dc = self.user.GetDC(self.hwnd)
        pixel = PixelFormat()
        pixel.nSize, pixel.nVersion = ct.sizeof(pixel), 1
        pixel.dwFlags, pixel.iPixelType, pixel.cColorBits, pixel.cDepthBits = 4 | 32 | 1, 0, 32, 24
        pf = self.gdi.ChoosePixelFormat(self.dc, ct.byref(pixel))
        if not pf or not self.gdi.SetPixelFormat(self.dc, pf, ct.byref(pixel)):
            raise RuntimeError('Native render pixel format unavailable.')
        self.context = self.gl.wglCreateContext(self.dc)
        if not self.context or not self.gl.wglMakeCurrent(self.dc, self.context):
            raise RuntimeError('Native render context unavailable.')
        self.gl.glGetString.argtypes, self.gl.glGetString.restype = [ct.c_uint], ct.c_char_p
        self.device = self.gl.glGetString(0x1F01).decode('utf-8', errors='replace')
        self.version = self.gl.glGetString(0x1F02).decode('utf-8', errors='replace')
        f = self.fn
        max_texture = ct.c_int()
        f('glGetIntegerv', None, ct.c_uint, ct.POINTER(ct.c_int))(0x0D33, ct.byref(max_texture))
        if max(self.width, self.height) > max_texture.value:
            raise RuntimeError('Requested image size exceeds this GPU texture limit.')
        f('glGenTextures', None, ct.c_int, ct.POINTER(ct.c_uint))(1, ct.byref(self.texture))
        f('glBindTexture', None, ct.c_uint, ct.c_uint)(0x0DE1, self.texture)
        # Accumulate in FP16; clamp/quantize only at final readback. This preserves
        # bright SH contributions during alpha compositing instead of clipping
        # each Gaussian into an 8-bit intermediate framebuffer.
        f('glTexImage2D', None, ct.c_uint, ct.c_int, ct.c_int, ct.c_int, ct.c_int, ct.c_int, ct.c_uint, ct.c_uint, ct.c_void_p)(0x0DE1, 0, 0x881A, self.width, self.height, 0, 0x1908, 0x1406, None)
        f('glGenFramebuffers', None, ct.c_int, ct.POINTER(ct.c_uint))(1, ct.byref(self.framebuffer))
        f('glBindFramebuffer', None, ct.c_uint, ct.c_uint)(0x8D40, self.framebuffer)
        f('glFramebufferTexture2D', None, ct.c_uint, ct.c_uint, ct.c_uint, ct.c_uint, ct.c_int)(0x8D40, 0x8CE0, 0x0DE1, self.texture, 0)
        f('glGenRenderbuffers', None, ct.c_int, ct.POINTER(ct.c_uint))(1, ct.byref(self.depth))
        f('glBindRenderbuffer', None, ct.c_uint, ct.c_uint)(0x8D41, self.depth)
        f('glRenderbufferStorage', None, ct.c_uint, ct.c_uint, ct.c_int, ct.c_int)(0x8D41, 0x81A6, self.width, self.height)
        f('glFramebufferRenderbuffer', None, ct.c_uint, ct.c_uint, ct.c_uint, ct.c_uint)(0x8D40, 0x8D00, 0x8D41, self.depth)
        if f('glCheckFramebufferStatus', ct.c_uint, ct.c_uint)(0x8D40) != 0x8CD5:
            raise RuntimeError('Native export framebuffer is incomplete.')
        f('glDisable', None, ct.c_uint)(0x0BD0)
        f('glViewport', None, ct.c_int, ct.c_int, ct.c_int, ct.c_int)(0, 0, self.width, self.height)

    def fn(self, name, result, *args):
        if name not in self._functions:
            try:
                function = getattr(self.gl, name)
                function.restype, function.argtypes = result, list(args)
            except AttributeError:
                address = self.gl.wglGetProcAddress(name.encode('ascii'))
                if not address or address in (1, 2, 3, ct.c_void_p(-1).value):
                    raise RuntimeError('Missing native render function: ' + name)
                function = ct.WINFUNCTYPE(result, *args)(address)
            self._functions[name] = function
        return self._functions[name]

    def set_scene(self, scene):
        """Bind immutable source data. Gaussian transforms remain float64."""
        if self.gpu is not None:
            self.gpu.close()
            self.gpu = None
        self.scene = scene
        asset = scene.get('gaussians')
        if asset is not None:
            from abu_m54_splat_gpu import GaussianRenderer
            self.gpu = GaussianRenderer(self.gl)
            self.gpu.set_asset(asset)
        points = np.asarray(scene.get('points', []), dtype=np.float64).reshape(-1, 3)
        colors = np.asarray(scene.get('colors', np.full((len(points), 3), 180)), dtype=np.uint8).reshape(-1, 3)
        if len(colors) != len(points) or not np.isfinite(points).all():
            raise ValueError('Invalid point-cloud geometry for export.')
        self.points, self.colors = points, np.ascontiguousarray(colors)

    def render(self, camera, near=.01, far=100000., output_size=None):
        """Return a PIL RGB image; input camera uses M54 right/down/forward axes."""
        f = self.fn
        origin = np.asarray(camera.position, dtype=np.float64)
        view = camera.view_matrix(origin=origin)
        projection = camera.projection_matrix(self.width, self.height, near, far)
        f('glClearColor', None, *([ct.c_float] * 4))(*self.background, 1.)
        f('glDepthMask', None, ct.c_ubyte)(1)
        f('glClear', None, ct.c_uint)(0x4000 | 0x0100)
        if self.gpu is not None:
            self.gpu.draw(view, projection, self.width, self.height,
                          model=np.asarray(self.scene.get('gaussian_transform', np.eye(4)), dtype=np.float64),
                          origin=origin, scale=1.)
        elif len(self.points):
            # Rebase before FP32 conversion; source coordinates are never edited.
            positions = np.ascontiguousarray(self.points - origin, dtype=np.float32)
            p, v = np.ascontiguousarray(projection.T), np.ascontiguousarray(view.T)
            f('glMatrixMode', None, ct.c_uint)(0x1701)
            f('glLoadMatrixd', None, ct.c_void_p)(p.ctypes.data)
            f('glMatrixMode', None, ct.c_uint)(0x1700)
            f('glLoadMatrixd', None, ct.c_void_p)(v.ctypes.data)
            f('glEnable', None, ct.c_uint)(0x0B71)
            f('glPointSize', None, ct.c_float)(2.)
            f('glEnableClientState', None, ct.c_uint)(0x8074)
            f('glEnableClientState', None, ct.c_uint)(0x8076)
            f('glVertexPointer', None, ct.c_int, ct.c_uint, ct.c_int, ct.c_void_p)(3, 0x1406, 0, positions.ctypes.data)
            f('glColorPointer', None, ct.c_int, ct.c_uint, ct.c_int, ct.c_void_p)(3, 0x1401, 0, self.colors.ctypes.data)
            f('glDrawArrays', None, ct.c_uint, ct.c_int, ct.c_int)(0, 0, len(positions))
            f('glDisableClientState', None, ct.c_uint)(0x8076)
            f('glDisableClientState', None, ct.c_uint)(0x8074)
        array = np.empty((self.height, self.width, 4), dtype=np.uint8)
        f('glReadPixels', None, ct.c_int, ct.c_int, ct.c_int, ct.c_int, ct.c_uint, ct.c_uint, ct.c_void_p)(0, 0, self.width, self.height, 0x1908, 0x1401, array.ctypes.data)
        error = f('glGetError', ct.c_uint)()
        if error:
            raise RuntimeError(f'OpenGL export failed (error {error:#x}).')
        image = Image.fromarray(np.ascontiguousarray(array[::-1, :, :3]))
        if output_size is not None and image.size != tuple(output_size):
            image = image.resize(tuple(output_size), Image.Resampling.LANCZOS)
        return image

    @property
    def buffer_bytes(self):
        return (self.gpu.allocated_bytes if self.gpu else 0) + self.width * self.height * 12

    def close(self):
        if self.context:
            self.gl.wglMakeCurrent(self.dc, self.context)
            if self.gpu is not None:
                self.gpu.close()
                self.gpu = None
            for name, handle in [('glDeleteFramebuffers', self.framebuffer), ('glDeleteRenderbuffers', self.depth), ('glDeleteTextures', self.texture)]:
                if handle.value:
                    self.fn(name, None, ct.c_int, ct.POINTER(ct.c_uint))(1, ct.byref(handle))
            self.gl.wglMakeCurrent(None, None)
            self.gl.wglDeleteContext(self.context)
            self.context = None
        if self.dc:
            self.user.ReleaseDC(self.hwnd, self.dc)
            self.dc = None
        if self.root is not None:
            self.root.destroy()
            self.root = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

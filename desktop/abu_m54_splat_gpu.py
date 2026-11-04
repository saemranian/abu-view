# SPDX-License-Identifier: Apache-2.0
"""Native M54 OpenGL 4.3 Gaussian prototype, using the current host context.

Shaders execute on the display GPU. Python submits commands only; resident
geometry and GPU sorting never make a per-frame round trip through Python.
This first backend uses center-depth sorting, not per-pixel visibility sorting.
"""
import ctypes as ct
import numpy as np
from abu_m54_splat_shaders import PREPARE, SORT, VERTEX, FRAGMENT

UINT = ct.c_uint
INT = ct.c_int
FLOAT = ct.c_float
PTR = ct.c_void_p
SSBO = 0x90D2


class GLFunctions:
    """Resolve extension entry points from the current WGL context."""
    def __init__(self, gl):
        self.gl = gl
        gl.wglGetProcAddress.argtypes = [ct.c_char_p]
        gl.wglGetProcAddress.restype = PTR
        self.cache = {}

    def bind(self, name, result, *arguments):
        if name in self.cache:
            return self.cache[name]
        pointer = self.gl.wglGetProcAddress(name.encode('ascii'))
        if pointer in (None, 0, 1, 2, 3, ct.c_void_p(-1).value):
            try:
                function = getattr(self.gl, name)
                function.restype = result
                function.argtypes = list(arguments)
            except AttributeError as error:
                raise RuntimeError('OpenGL 4.3 GPU function unavailable: ' + name) from error
        else:
            function = ct.WINFUNCTYPE(result, *arguments)(pointer)
        self.cache[name] = function
        return function


class GaussianRenderer:
    """Own GPU objects for one viewport; close while its context is current."""
    def __init__(self, gl, budget_bytes=2 * 1024**3):
        self.api = GLFunctions(gl)
        self.programs = []
        self.buffers = []
        self.queries = []
        self.pending = []
        self.asset = None
        self._upload = None
        self.allocated_bytes = 0
        self.budget_bytes = int(budget_bytes)
        self.last_gpu_ms = None
        self.asset_origin = np.zeros(3)
        self.asset_scale = 1.
        self.locations = {}
        self.count = 0
        self.padded = 0
        self.vao = UINT()
        a = self.api.bind
        self.use = a('glUseProgram', None, UINT)
        self.uniform1ui = a('glUniform1ui', None, INT, UINT)
        self.uniform2f = a('glUniform2f', None, INT, FLOAT, FLOAT)
        self.uniform3f = a('glUniform3f', None, INT, FLOAT, FLOAT, FLOAT)
        self.uniformmat = a('glUniformMatrix4fv', None, INT, INT, ct.c_ubyte, PTR)
        self.bind_buffer = a('glBindBuffer', None, UINT, UINT)
        self.buffer_data = a('glBufferData', None, UINT, ct.c_ssize_t, PTR, UINT)
        self.buffer_sub_data = a('glBufferSubData', None, UINT, ct.c_ssize_t, ct.c_ssize_t, PTR)
        self.bind_base = a('glBindBufferBase', None, UINT, UINT, UINT)
        self.dispatch = a('glDispatchCompute', None, UINT, UINT, UINT)
        self.barrier = a('glMemoryBarrier', None, UINT)
        self.bind_vao = a('glBindVertexArray', None, UINT)
        self.draw_instances = a('glDrawArraysInstanced', None, UINT, INT, INT, INT)
        self.depth_mask = a('glDepthMask', None, ct.c_ubyte)
        self.enable = a('glEnable', None, UINT)
        self.disable = a('glDisable', None, UINT)
        self.blend = a('glBlendFunc', None, UINT, UINT)
        self.get_error = a('glGetError', UINT)
        try:
            self.prepare = self._program([(0x91B9, PREPARE)])
            self.sort = self._program([(0x91B9, SORT)])
            self.render = self._program([(0x8B31, VERTEX), (0x8B30, FRAGMENT)])
            a('glGenVertexArrays', None, INT, PTR)(1, ct.byref(self.vao))
            values = (UINT * 6)()
            a('glGenQueries', None, INT, PTR)(6, values)
            self.queries = list(values)
            self.free_queries = [(self.queries[i], self.queries[i+1]) for i in range(0, 6, 2)]
            self.timestamp = a('glQueryCounter', None, UINT, UINT)
            self.query_available = a('glGetQueryObjectiv', None, UINT, UINT, PTR)
            self.query_result = a('glGetQueryObjectui64v', None, UINT, UINT, PTR)
            self._check('shader initialization')
        except Exception:
            self.close()
            raise

    def _check(self, operation):
        error = self.get_error()
        if error:
            raise RuntimeError(f'Gaussian GPU {operation} failed: OpenGL 0x{error:04x}')

    def _program(self, stages):
        a = self.api.bind
        program = a('glCreateProgram', UINT)()
        shaders = []
        try:
            for kind, source in stages:
                shader = a('glCreateShader', UINT, UINT)(kind)
                shaders.append(shader)
                text = ct.c_char_p(source.encode('utf-8'))
                a('glShaderSource', None, UINT, INT, PTR, PTR)(shader, 1, ct.byref(text), None)
                a('glCompileShader', None, UINT)(shader)
                status = INT()
                a('glGetShaderiv', None, UINT, UINT, PTR)(shader, 0x8B81, ct.byref(status))
                if not status.value:
                    log = ct.create_string_buffer(16384)
                    a('glGetShaderInfoLog', None, UINT, INT, PTR, PTR)(shader, len(log), None, log)
                    raise RuntimeError('M54 Gaussian shader: ' + log.value.decode(errors='replace'))
                a('glAttachShader', None, UINT, UINT)(program, shader)
            a('glLinkProgram', None, UINT)(program)
            status = INT()
            a('glGetProgramiv', None, UINT, UINT, PTR)(program, 0x8B82, ct.byref(status))
            if not status.value:
                log = ct.create_string_buffer(16384)
                a('glGetProgramInfoLog', None, UINT, INT, PTR, PTR)(program, len(log), None, log)
                raise RuntimeError('M54 Gaussian program: ' + log.value.decode(errors='replace'))
            self.programs.append(program)
            return program
        except Exception:
            a('glDeleteProgram', None, UINT)(program)
            raise
        finally:
            for shader in shaders:
                a('glDeleteShader', None, UINT)(shader)

    def location(self, program, name):
        key = program, name
        if key not in self.locations:
            self.locations[key] = self.api.bind('glGetUniformLocation', INT, UINT, ct.c_char_p)(program, name.encode())
        return self.locations[key]

    def matrix(self, program, name, matrix):
        with np.errstate(over='ignore', invalid='ignore'):
            value = np.ascontiguousarray(np.asarray(matrix, dtype=np.float32).T)
        if value.shape != (4, 4) or not np.isfinite(value).all():
            raise ValueError('View/model matrix is outside the finite GPU coordinate range.')
        self.uniformmat(self.location(program, name), 1, 0, value.ctypes.data)

    def _clear_buffers(self):
        if self.buffers:
            values = (UINT * len(self.buffers))(*self.buffers)
            self.api.bind('glDeleteBuffers', None, INT, PTR)(len(values), values)
        self.buffers = []
        self.allocated_bytes = 0
        self.asset = None
        self.count = 0
        self._upload = None

    def set_asset(self, asset):
        if asset is self.asset and self._upload is None:
            return
        self.begin_asset(asset)
        while not self.upload_step():
            pass

    def begin_asset(self, asset, prepared=None):
        """Allocate an asset without displaying incomplete data.

        Sequence workers may supply ``(packed, origin, scale)``. Packing then
        happens off the UI thread; the host submits bounded uploads on its GL
        thread using :meth:`upload_step`. All source arrays remain immutable.
        """
        self._clear_buffers()
        self.last_gpu_ms = None
        self.free_queries.extend(self.pending)
        self.pending = []
        if asset is None or not asset.count:
            return
        count = asset.count
        padded = max(256, 1 << (count-1).bit_length())
        sizes = [count * 256, padded * 8, count * 48]
        limit = ct.c_int64()
        self.api.bind('glGetInteger64v', None, UINT, PTR)(0x90DE, ct.byref(limit))
        if sum(sizes) > self.budget_bytes or max(sizes) > limit.value or padded//256 > 65535:
            raise ValueError(f'{count:,} Gaussians exceed this prototype GPU budget ({self.budget_bytes/1024**3:.1f} GiB). '
                             'Use a smaller asset; streaming is a later phase. The source has not been reduced.')
        if prepared is None:
            origin = (asset.positions.min(axis=0) + asset.positions.max(axis=0)) * .5
            scale = max(float(np.linalg.norm(np.ptp(asset.positions, axis=0))), 1e-8)
            packed = asset.packed(origin, scale)
        else:
            packed, origin, scale = prepared
        origin = np.asarray(origin, dtype=np.float64)
        scale = float(scale)
        if (not isinstance(packed, np.ndarray) or packed.dtype != np.float32
                or packed.shape != (count, 64) or not packed.flags.c_contiguous
                or origin.shape != (3,) or not np.isfinite(origin).all()
                or not np.isfinite(scale) or scale <= 0):
            raise ValueError('Invalid prepared Gaussian upload.')
        self.asset_origin = origin.copy()
        self.asset_scale = scale
        values = (UINT * 3)()
        self.api.bind('glGenBuffers', None, INT, PTR)(3, values)
        self.buffers = list(values)
        try:
            for i, (buffer, size) in enumerate(zip(self.buffers, sizes)):
                self.bind_buffer(SSBO, buffer)
                self.buffer_data(SSBO, size, None, 0x88E4 if i == 0 else 0x88E8)
                self._check('buffer allocation')
            self.allocated_bytes = sum(sizes)
            self._upload = {'asset': asset, 'packed': packed, 'offset': 0, 'padded': padded}
        except Exception:
            self._clear_buffers()
            raise
        finally:
            self.bind_buffer(SSBO, 0)

    def upload_step(self, max_bytes=16 * 1024**2):
        """Upload at most ``max_bytes`` on the current context; return ready.

        Validation is performed per chunk so a 700 MiB preparation cannot
        create a long full-array scan on the UI thread. Failure releases the
        partial allocation. ``draw`` is a no-op until every byte is uploaded.
        """
        if self._upload is None:
            return True
        size = int(max_bytes)
        if size <= 0:
            raise ValueError('Upload chunk size must be positive.')
        size = max(4, size - size % 4)
        upload = self._upload
        packed = upload['packed']
        start = upload['offset']
        end = min(packed.nbytes, start + size)
        try:
            if not np.isfinite(packed.reshape(-1)[start//4:end//4]).all():
                raise ValueError('Prepared Gaussian upload contains nonfinite values.')
            self.bind_buffer(SSBO, self.buffers[0])
            self.buffer_sub_data(SSBO, start, end-start, packed.ctypes.data+start)
            self._check('staged buffer upload')
            upload['offset'] = end
            if end == packed.nbytes:
                self.asset = upload['asset']
                self.count = self.asset.count
                self.padded = upload['padded']
                self._upload = None
                return True
            return False
        except Exception:
            self._clear_buffers()
            raise
        finally:
            self.bind_buffer(SSBO, 0)

    def poll_timing(self):
        while self.pending:
            first, last = self.pending[0]
            available = INT()
            self.query_available(last, 0x8867, ct.byref(available))
            if not available.value:
                break
            begin, end = ct.c_uint64(), ct.c_uint64()
            self.query_result(first, 0x8866, ct.byref(begin))
            self.query_result(last, 0x8866, ct.byref(end))
            self.last_gpu_ms = (end.value-begin.value)/1e6
            self.pending.pop(0)
            self.free_queries.append((first, last))
        return self.last_gpu_ms

    def draw(self, view, projection, width, height, model=None, origin=None, scale=1.):
        try:
            return self._draw(view, projection, width, height, model, origin, scale)
        finally:
            # Also restore the host's compatibility state when an upload,
            # prepare/sort dispatch or uniform operation fails before drawing.
            self.depth_mask(1)
            self.enable(0x0B71)
            self.blend(0x0302, 0x0303)
            self.bind_vao(0)
            self.use(0)
            for slot in range(3):
                self.bind_base(SSBO, slot, 0)

    def _draw(self, view, projection, width, height, model=None, origin=None, scale=1.):
        if self.asset is None or not self.count:
            return
        self.poll_timing()
        query = self.free_queries.pop() if self.free_queries else None
        if query:
            self.timestamp(query[0], 0x8E28)
        model = np.eye(4) if model is None else np.asarray(model, dtype=np.float64)
        origin = np.zeros(3) if origin is None else np.asarray(origin, dtype=np.float64)
        local = np.eye(4)
        local[:3, :3] = model[:3, :3] * (self.asset_scale / scale)
        local[:3, 3] = (model[:3, :3] @ self.asset_origin + model[:3, 3] - origin) / scale
        model_view = np.asarray(view) @ local
        eye = np.linalg.inv(model_view)[:3, 3]
        for slot, buffer in enumerate(self.buffers):
            self.bind_base(SSBO, slot, buffer)
        self.use(self.prepare)
        self.uniform1ui(self.location(self.prepare, 'count'), self.count)
        self.uniform1ui(self.location(self.prepare, 'padded'), self.padded)
        self.uniform2f(self.location(self.prepare, 'viewport'), width, height)
        self.uniform3f(self.location(self.prepare, 'cameraObject'), *eye)
        self.matrix(self.prepare, 'modelView', model_view)
        self.matrix(self.prepare, 'projection', projection)
        self.dispatch(self.padded//256, 1, 1)
        self.barrier(0x2000)
        self.use(self.sort)
        padded = self.location(self.sort, 'padded')
        stage = self.location(self.sort, 'stage')
        stride = self.location(self.sort, 'stride')
        local_pass = self.location(self.sort, 'localPass')
        self.uniform1ui(padded, self.padded)
        self.uniform1ui(local_pass, 1)
        self.dispatch(self.padded//256, 1, 1)
        self.barrier(0x2000)
        k = 512
        while k <= self.padded:
            self.uniform1ui(stage, k)
            self.uniform1ui(local_pass, 0)
            j = k//2
            while j >= 256:
                self.uniform1ui(stride, j)
                self.dispatch(self.padded//256, 1, 1)
                self.barrier(0x2000)
                j //= 2
            self.uniform1ui(local_pass, 2)
            self.dispatch(self.padded//256, 1, 1)
            self.barrier(0x2000)
            k *= 2
        self.use(self.render)
        self.uniform2f(self.location(self.render, 'viewport'), width, height)
        self.bind_vao(self.vao.value)
        self.enable(0x0BE2)
        self.blend(1, 0x0303)
        self.depth_mask(0)
        self.disable(0x0B71)
        try:
            self.draw_instances(0x0004, 0, 6, self.count)
        finally:
            self.depth_mask(1)
            self.enable(0x0B71)
            self.blend(0x0302, 0x0303)
            self.bind_vao(0)
            self.use(0)
            for slot in range(3):
                self.bind_base(SSBO, slot, 0)
        if query:
            self.timestamp(query[1], 0x8E28)
            self.pending.append(query)
        self._check('frame')

    def close(self):
        self._clear_buffers()
        for program in self.programs:
            self.api.bind('glDeleteProgram', None, UINT)(program)
        self.programs = []
        if self.vao.value:
            self.api.bind('glDeleteVertexArrays', None, INT, PTR)(1, ct.byref(self.vao))
            self.vao.value = 0
        if self.queries:
            values = (UINT * len(self.queries))(*self.queries)
            self.api.bind('glDeleteQueries', None, INT, PTR)(len(values), values)
        self.queries = []
        self.pending = []

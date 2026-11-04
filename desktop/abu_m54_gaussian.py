# SPDX-License-Identifier: Apache-2.0
"""Validated Gaussian assets for the shared Abu M54 scene system.

This module is an independent implementation of the scalar PLY file layout and
Gaussian parameter decoding; no upstream renderer/model implementation is copied.
World coordinates remain float64. GPU packing is an explicit derived copy.
"""
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import math
import numpy as np

SH_C0 = math.sqrt(1.0 / (4.0 * math.pi))
MAX_HEADER_BYTES = 65536
DEFAULT_MAX_SPLATS = 20_000_000
DEFAULT_MAX_BYTES = 4 * 1024 ** 3
_SCALARS = {
    'char': 'i1', 'int8': 'i1', 'uchar': 'u1', 'uint8': 'u1',
    'short': '<i2', 'int16': '<i2', 'ushort': '<u2', 'uint16': '<u2',
    'int': '<i4', 'int32': '<i4', 'uint': '<u4', 'uint32': '<u4',
    'float': '<f4', 'float32': '<f4', 'double': '<f8', 'float64': '<f8',
}
_REQUIRED = ('x', 'y', 'z', 'opacity', 'scale_0', 'scale_1', 'scale_2',
             'rot_0', 'rot_1', 'rot_2', 'rot_3', 'f_dc_0', 'f_dc_1', 'f_dc_2')


def _is_gaussian_property(name):
    # Ordinary point PLYs may contain opacity/alpha. Only Gaussian-specific
    # indexed attributes opt a file into this decoder, including partial schemas.
    return any(name.startswith(prefix) and name[len(prefix):].isdecimal()
               for prefix in ('scale_', 'rot_', 'f_dc_', 'f_rest_'))


def _readonly(value, dtype, shape, name):
    with np.errstate(over='ignore', under='ignore', invalid='ignore'):
        result = np.array(value, dtype=dtype, order='C', copy=True)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(f'{name} must have shape {shape} and contain finite numbers.')
    result.setflags(write=False)
    return result


@dataclass(frozen=True, eq=False)
class GaussianAsset:
    """Immutable source-space parameters; SH is channel-major (N, 3, K).

    Scales are linear standard deviations, opacity is in [0,1], and rotations
    are WXYZ unit quaternions. Constructors make owned, read-only array copies.
    """
    positions: np.ndarray
    scales: np.ndarray
    rotations_wxyz: np.ndarray
    opacities: np.ndarray
    sh: np.ndarray
    source: str = ''

    def __post_init__(self):
        positions = np.asarray(self.positions)
        if positions.ndim != 2 or positions.shape[1] != 3:
            raise ValueError('Positions must have shape (N, 3).')
        count = len(positions)
        sh = np.asarray(self.sh)
        if sh.ndim != 3 or sh.shape[:2] != (count, 3) or sh.shape[2] not in (1, 4, 9, 16):
            raise ValueError('SH must have shape (N, 3, K), with degree 0 through 3 (K=1,4,9,16).')
        values = {
            'positions': _readonly(positions, np.float64, (count, 3), 'Positions'),
            'scales': _readonly(self.scales, np.float32, (count, 3), 'Scales'),
            'opacities': _readonly(self.opacities, np.float32, (count,), 'Opacities'),
            'sh': _readonly(sh, np.float32, sh.shape, 'SH'),
        }
        if np.any(values['scales'] <= 0):
            raise ValueError('Gaussian scales must be strictly positive and representable in float32.')
        if np.any((values['opacities'] < 0) | (values['opacities'] > 1)):
            raise ValueError('Gaussian opacity must be between zero and one.')
        rotations = np.array(self.rotations_wxyz, dtype=np.float64, copy=True)
        if rotations.shape != (count, 4) or not np.isfinite(rotations).all():
            raise ValueError('Rotations must have shape (N, 4) and be finite WXYZ quaternions.')
        # Divide by largest component first: finite nonzero quaternions cannot
        # overflow/underflow the norm even when an exporter did not normalize.
        largest = np.max(np.abs(rotations), axis=1) if count else np.empty(0)
        if np.any(largest == 0):
            raise ValueError('A zero quaternion cannot describe a Gaussian rotation.')
        rotations /= largest[:, None]
        rotations /= np.linalg.norm(rotations, axis=1)[:, None]
        values['rotations_wxyz'] = _readonly(rotations, np.float32, (count, 4), 'Rotations')
        for key, value in values.items():
            object.__setattr__(self, key, value)
        object.__setattr__(self, 'source', str(self.source))

    @property
    def count(self):
        return len(self.positions)

    @property
    def degree(self):
        return math.isqrt(self.sh.shape[2]) - 1

    @property
    def nbytes(self):
        return sum(value.nbytes for value in (self.positions, self.scales,
                   self.rotations_wxyz, self.opacities, self.sh))

    def bounds(self):
        """Return source center and diameter; excludes unbounded Gaussian tails."""
        if not self.count:
            return np.zeros(3), 1.0
        low, high = self.positions.min(0), self.positions.max(0)
        return low + (high - low) * .5, max(float(np.linalg.norm(high - low)), 1e-6)

    @cached_property
    def support_bounds(self):
        """Conservative 3-sigma support, cached so gizmos never rescan the asset."""
        if not self.count:
            return np.zeros((2, 3))
        radius = 3. * float(self.scales.max())
        result = np.array([self.positions.min(0)-radius, self.positions.max(0)+radius])
        result.setflags(write=False)
        return result

    def preview(self, limit=50000):
        """Explicit point preview for legacy picking/unsupported renderers only."""
        if int(limit) < 0:
            raise ValueError('Preview limit must be nonnegative.')
        indices = np.linspace(0, max(0, self.count - 1), min(self.count, int(limit)), dtype=np.int64)
        colors = np.clip(.5 + SH_C0 * self.sh[indices, :, 0], 0., 1.)
        return self.positions[indices].copy(), np.rint(colors * 255.).astype(np.uint8)

    def packed(self, origin=None, world_scale=1.0):
        """Create 64 float32 values per splat for the GPU SSBO.

        The display coordinate is (world-origin)/world_scale. Layout:
        [0:4] XYZ/opacity; [4:8] linear scales/SH degree; [8:12] WXYZ;
        [12:60] RGB channel-major SH coefficients, each channel padded to 16;
        [60:64] reserved zeros. Sources and world origin remain unchanged.
        """
        origin = np.zeros(3) if origin is None else np.asarray(origin, dtype=np.float64)
        if origin.shape != (3,) or not np.isfinite(origin).all():
            raise ValueError('GPU origin must be a finite XYZ vector.')
        if not np.isfinite(world_scale) or world_scale <= 0:
            raise ValueError('GPU world scale must be positive and finite.')
        result = np.zeros((self.count, 64), dtype=np.float32)
        with np.errstate(over='ignore', invalid='ignore', under='ignore'):
            result[:, :3] = (self.positions - origin) / world_scale
            result[:, 3] = self.opacities
            result[:, 4:7] = self.scales.astype(np.float64) / world_scale
        if not np.isfinite(result[:, :7]).all() or np.any(result[:, 4:7] <= 0):
            raise ValueError('Scene coordinates/scales exceed float32 GPU range after rebasing.')
        result[:, 7] = self.degree
        result[:, 8:12] = self.rotations_wxyz
        coefficients = result[:, 12:60].reshape(self.count, 3, 16)
        coefficients[:, :, :self.sh.shape[2]] = self.sh
        return result


def _header(stream):
    """Read only a bounded ASCII header; reject ambiguous vertex schemas."""
    if stream.readline(8).strip() != b'ply':
        raise ValueError('Not a PLY file.')
    fmt, element, count, properties = None, None, None, []
    seen_elements = set()
    while stream.tell() <= MAX_HEADER_BYTES:
        line = stream.readline(MAX_HEADER_BYTES + 1)
        if not line:
            raise ValueError('Truncated PLY header.')
        if stream.tell() > MAX_HEADER_BYTES:
            raise ValueError('PLY header exceeds the 64 KiB safety limit.')
        try:
            parts = line.decode('ascii').strip().split()
        except UnicodeDecodeError as error:
            raise ValueError('PLY header must be ASCII.') from error
        if not parts or parts[0] in ('comment', 'obj_info'):
            continue
        tag = parts[0]
        if tag == 'end_header':
            if len(parts) != 1 or fmt is None or count is None or not properties:
                raise ValueError('Incomplete PLY vertex header.')
            return fmt, count, properties, stream.tell()
        if tag == 'format':
            if fmt is not None or len(parts) != 3 or parts[2] != '1.0':
                raise ValueError('Malformed/duplicate PLY format declaration.')
            fmt = parts[1]
            if fmt not in ('ascii', 'binary_little_endian'):
                raise ValueError('Gaussian PLY prototype supports ASCII and binary little-endian PLY 1.0.')
        elif tag == 'element':
            if len(parts) != 3 or parts[1] in seen_elements:
                raise ValueError('Malformed/duplicate PLY element declaration.')
            try:
                element_count = int(parts[2])
            except ValueError as error:
                raise ValueError('Invalid PLY element count.') from error
            if element_count < 0:
                raise ValueError('PLY element count must be nonnegative.')
            element = parts[1]
            if element == 'vertex':
                if seen_elements:
                    raise ValueError('Gaussian PLY vertex element must be first.')
                count = element_count
            seen_elements.add(element)
        elif tag == 'property':
            if element is None:
                raise ValueError('PLY property declared before an element.')
            if element != 'vertex':
                continue  # Elements following the vertex data are not imported.
            if len(parts) != 3 or parts[1] not in _SCALARS:
                raise ValueError('Gaussian PLY vertices require supported scalar properties, not lists.')
            if parts[2] in {name for name, _ in properties}:
                raise ValueError('Duplicate PLY vertex property.')
            if len(properties) >= 128:
                raise ValueError('PLY vertex schema exceeds 128 scalar properties.')
            properties.append((parts[2], _SCALARS[parts[1]]))
        else:
            raise ValueError(f'Unsupported PLY header directive: {tag}.')
    raise ValueError('PLY header exceeds the 64 KiB safety limit.')


def is_gaussian_ply(source):
    """Inspect only the bounded header; do not decode or allocate vertex data.

    Partial Gaussian schemas return True so the full decoder gives an explicit
    diagnostic. Ordinary PLY syntax/encoding remains the ordinary loader's job.
    """
    with Path(source).open('rb') as stream:
        if stream.readline(8).strip() != b'ply':
            return False
        vertex, found = False, False
        while stream.tell() <= MAX_HEADER_BYTES:
            line = stream.readline(MAX_HEADER_BYTES + 1)
            if not line or stream.tell() > MAX_HEADER_BYTES:
                raise ValueError('PLY header is truncated or exceeds 64 KiB.')
            try:
                parts = line.decode('ascii').strip().split()
            except UnicodeDecodeError as error:
                raise ValueError('PLY header must be ASCII.') from error
            if not parts:
                continue
            if parts[0] == 'end_header':
                return found
            if parts[0] == 'element':
                vertex = len(parts) >= 2 and parts[1] == 'vertex'
            if vertex and parts[0] == 'property' and len(parts) >= 3:
                name = parts[-1]
                found = found or _is_gaussian_property(name)
    raise ValueError('PLY header exceeds 64 KiB.')


def load_gaussian_ply(source, *, max_splats=DEFAULT_MAX_SPLATS, max_bytes=DEFAULT_MAX_BYTES):
    """Load conventional log-scale/logit-opacity Gaussian PLY, or return None.

    None denotes an ordinary PLY with no Gaussian properties. Partial Gaussian
    schemas fail loudly instead of silently degrading into point clouds. Input
    count, raw vertex bytes and decoded asset bytes are bounded before allocation.
    This first adapter deliberately rejects unsupported SH degrees and encodings.
    """
    source = Path(source)
    if int(max_splats) < 0 or int(max_bytes) < 1:
        raise ValueError('Gaussian import limits must be nonnegative count and positive bytes.')
    with source.open('rb') as stream:
        fmt, count, properties, offset = _header(stream)
        names = {name for name, _ in properties}
        gaussian_names = any(_is_gaussian_property(name) for name in names)
        if not gaussian_names:
            return None
        missing = sorted(set(_REQUIRED) - names)
        if missing:
            raise ValueError('Incomplete Gaussian PLY properties: ' + ', '.join(missing))
        rest = sorted(name for name in names if name.startswith('f_rest_'))
        if set(rest) != {f'f_rest_{i}' for i in range(len(rest))}:
            raise ValueError('Gaussian f_rest properties must be contiguous, starting at zero.')
        if len(rest) not in (0, 9, 24, 45):
            raise ValueError('Gaussian PLY supports SH degree 0 through 3; unexpected f_rest property count.')
        k = 1 + len(rest) // 3
        dtype = np.dtype(properties)
        if count > int(max_splats):
            raise ValueError(f'Gaussian count {count:,} exceeds import budget {int(max_splats):,}.')
        if max(count * dtype.itemsize, count * (56 + 12 * k)) > int(max_bytes):
            raise ValueError('Gaussian vertex/decoded arrays exceed the configured memory budget.')
        remaining_bytes = source.stat().st_size - offset
        if fmt == 'binary_little_endian':
            if count * dtype.itemsize > remaining_bytes:
                raise ValueError('Truncated binary Gaussian PLY vertex payload.')
            rows = np.fromfile(stream, dtype=dtype, count=count)
            if len(rows) != count:
                raise ValueError('Gaussian PLY changed or was truncated while reading.')
        else:
            # Each scalar requires at least one byte plus separation; this catches
            # forged enormous counts before allocating on short ASCII input.
            if count and remaining_bytes < count * (2 * len(properties) - 1):
                raise ValueError('Truncated ASCII Gaussian PLY vertex payload.')
            rows = np.empty(count, dtype=dtype)
            for index in range(count):
                line = stream.readline(65537)
                if len(line) > 65536:
                    raise ValueError('ASCII Gaussian PLY row exceeds 64 KiB.')
                values = line.split()
                if len(values) != len(properties):
                    raise ValueError(f'Malformed ASCII Gaussian PLY vertex row {index + 1}.')
                try:
                    rows[index] = tuple(values)
                except (ValueError, OverflowError) as error:
                    raise ValueError(f'Invalid ASCII Gaussian PLY scalar at row {index + 1}.') from error
    def columns(fields):
        return np.column_stack([rows[name] for name in fields]).astype(np.float64)
    positions = columns(('x', 'y', 'z'))
    log_scales = columns(('scale_0', 'scale_1', 'scale_2'))
    rotations = columns(('rot_0', 'rot_1', 'rot_2', 'rot_3'))
    logits = rows['opacity'].astype(np.float64)
    if not np.isfinite(log_scales).all() or not np.isfinite(logits).all():
        raise ValueError('Gaussian log scales and opacity logits must be finite.')
    with np.errstate(over='ignore', under='ignore'):
        scales = np.exp(log_scales)
        exp_negative_abs = np.exp(-np.abs(logits))
    opacity = np.where(logits >= 0, 1. / (1. + exp_negative_abs), exp_negative_abs / (1. + exp_negative_abs))
    sh = np.empty((count, 3, k), dtype=np.float32)
    sh[:, :, 0] = columns(('f_dc_0', 'f_dc_1', 'f_dc_2'))
    if rest:
        # Conventional exporters flatten (RGB, non-DC coefficients), not
        # coefficient-major RGB. Property order in the file is immaterial.
        sh[:, :, 1:] = columns([f'f_rest_{i}' for i in range(len(rest))]).reshape(count, 3, k - 1)
    return GaussianAsset(positions, scales, rotations, opacity, sh, str(source.resolve()))

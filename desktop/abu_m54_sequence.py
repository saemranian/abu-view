# SPDX-License-Identifier: Apache-2.0
"""Original local PLY sequence discovery, timing and bounded CPU preparation.

The existing M54 Gaussian PLY decoder remains the only geometry parser. A
sequence consists of discrete exported frames, not a deformation checkpoint.
No interpolation of unmatched splat rows is implied by equal vertex counts.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import math
from pathlib import Path
import queue
import re
import threading

import numpy as np


MAX_FRAMES = 10000
SCHEMA = 'abu-m54-ply-sequence-1'
_NUMBERED = re.compile(r'^(.*?)(\d+)([^\d]*)$', re.IGNORECASE)


def _fps(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError('Sequence FPS must be a number from 0.1 to 240.') from error
    if not math.isfinite(result) or not .1 <= result <= 240:
        raise ValueError('Sequence FPS must be a number from 0.1 to 240.')
    return result


@dataclass(frozen=True)
class FrameInfo:
    path: str
    size: int
    mtime_ns: int
    count: int
    degree: int
    decoded_bytes: int
    packed_bytes: int
    gpu_bytes: int
    cpu_bytes: int

    def signature(self):
        return {'path': self.path, 'size': self.size, 'mtime_ns': self.mtime_ns}


def inspect_frame(path):
    """Bounded metadata preflight through the original Gaussian header reader."""
    from abu_m54_gaussian import (_header, _REQUIRED, DEFAULT_MAX_BYTES,
                                  DEFAULT_MAX_SPLATS)
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() != '.ply' or not source.is_file():
        raise ValueError('A PLY sequence requires existing .ply files: ' + str(source))
    before = source.stat()
    with source.open('rb') as stream:
        fmt, count, properties, offset = _header(stream)
    names = {name for name, _ in properties}
    missing = sorted(set(_REQUIRED) - names)
    if missing:
        raise ValueError(source.name + ': sequence playback needs Gaussian PLY attributes; missing ' + ', '.join(missing))
    rest = {name for name in names if name.startswith('f_rest_')}
    if rest != {f'f_rest_{i}' for i in range(len(rest))} or len(rest) not in (0, 9, 24, 45):
        raise ValueError(source.name + ': Gaussian PLY requires contiguous SH degree 0–3 coefficients.')
    k = 1 + len(rest) // 3
    if not 0 < count <= DEFAULT_MAX_SPLATS:
        raise ValueError(source.name + ': frame must contain 1–20,000,000 Gaussians.')
    raw = count * np.dtype(properties).itemsize
    decoded = count * (56 + 12 * k)
    if max(raw, decoded) > DEFAULT_MAX_BYTES:
        raise ValueError(source.name + ': frame exceeds the existing Gaussian import memory limit.')
    payload = before.st_size - offset
    minimum = raw if fmt == 'binary_little_endian' else count * (2 * len(properties) - 1)
    if payload < minimum:
        raise ValueError(source.name + ': truncated Gaussian PLY payload.')
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(source.name + ': file changed while reading its header; reopen the sequence.')
    packed = count * 256
    padded = max(256, 1 << (count - 1).bit_length())
    gpu = count * 304 + padded * 8
    # Include the scene's sampled XYZ/RGB arrays and small matrix/bounds data.
    cpu = decoded + packed + min(count, 50000) * 27 + 1024
    return FrameInfo(str(source), before.st_size, before.st_mtime_ns, count,
                     math.isqrt(k) - 1, decoded, packed, gpu, cpu)


@dataclass(frozen=True)
class PlySequence:
    paths: tuple[str, ...]
    fps: float = 30.
    frames: tuple[FrameInfo, ...] = field(init=False, repr=False)

    def __post_init__(self):
        if isinstance(self.paths, (str, bytes, Path)):
            raise ValueError('A sequence needs a list of frame paths, not a single path string.')
        paths = tuple(self.paths)
        if not 2 <= len(paths) <= MAX_FRAMES:
            raise ValueError(f'A PLY sequence needs 2–{MAX_FRAMES:,} frames.')
        frames = tuple(inspect_frame(path) for path in paths)
        resolved = tuple(frame.path for frame in frames)
        if len({str(Path(path)).casefold() for path in resolved}) != len(resolved):
            raise ValueError('A sequence cannot contain a duplicate file.')
        object.__setattr__(self, 'paths', resolved)
        object.__setattr__(self, 'fps', _fps(self.fps))
        object.__setattr__(self, 'frames', frames)

    @property
    def count(self):
        return len(self.paths)

    @property
    def duration(self):
        return self.count / self.fps

    @property
    def total_cpu_bytes(self):
        return sum(frame.cpu_bytes for frame in self.frames)

    @property
    def total_gpu_bytes(self):
        return sum(frame.gpu_bytes for frame in self.frames)

    def frame_index(self, timestamp, loop=False):
        try:
            timestamp = float(timestamp)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError('Sequence time must be finite.') from error
        if not math.isfinite(timestamp):
            raise ValueError('Sequence time must be finite.')
        if loop:
            timestamp %= self.duration
        elif timestamp <= 0:
            return 0
        elif timestamp >= self.duration:
            return self.count - 1
        # A tiny boundary tolerance removes binary roundoff at i / FPS while
        # retaining sample-and-hold behavior between discrete source frames.
        return min(self.count - 1, max(0, int(math.floor(timestamp * self.fps + 1e-9))))

    def verify_frame(self, index):
        frame = self.frames[_index(index, self.count)]
        path = Path(frame.path)
        try:
            stat = path.stat()
        except OSError as error:
            raise ValueError(path.name + ': sequence frame is no longer available; reopen the sequence.') from error
        if stat.st_size != frame.size or stat.st_mtime_ns != frame.mtime_ns:
            raise ValueError(path.name + ': sequence frame changed; reopen the sequence before playback/export.')
        return path

    verify_file = verify_frame

    def with_fps(self, fps):
        """Change timing only; retain the original immutable file signatures.

        Reopening or re-preflighting is deliberately not part of a speed edit:
        a file modified after opening must still fail the consistency check.
        """
        value = _fps(fps)
        result = object.__new__(PlySequence)
        object.__setattr__(result, 'paths', self.paths)
        object.__setattr__(result, 'fps', value)
        object.__setattr__(result, 'frames', self.frames)
        return result

    def to_dict(self):
        return {'schema': SCHEMA, 'fps': self.fps,
                'frames': [frame.signature() for frame in self.frames]}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or value.get('schema') != SCHEMA:
            raise ValueError('Unsupported PLY sequence description.')
        records = value.get('frames')
        if not isinstance(records, list) or not 2 <= len(records) <= MAX_FRAMES:
            raise ValueError('Sequence description needs 2–10,000 frame records.')
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get('path'), str):
                raise ValueError('Invalid sequence frame record.')
            if not Path(record['path']).is_absolute():
                raise ValueError('Sequence frame records require absolute local paths.')
            if any(type(record.get(key)) is not int or record[key] < 0 for key in ('size', 'mtime_ns')):
                raise ValueError('Invalid sequence frame file signature.')
        sequence = cls(tuple(record['path'] for record in records), value.get('fps', 30.))
        for frame, record in zip(sequence.frames, records):
            if (frame.size, frame.mtime_ns) != (record['size'], record['mtime_ns']):
                raise ValueError(Path(frame.path).name + ': sequence frame changed; reopen it before export.')
        return sequence


def _index(index, count):
    if isinstance(index, (bool, np.bool_)):
        raise IndexError('Frame index must be an integer within the sequence.')
    try:
        result = int(index)
    except (TypeError, ValueError, OverflowError) as error:
        raise IndexError('Frame index must be an integer within the sequence.') from error
    if result != index or not 0 <= result < count:
        raise IndexError('Frame index must be an integer within the sequence.')
    return result


def discover_sequence(source, fps=30.):
    """Find one numbered file family without silently mixing unrelated models.

    Choose any frame to disambiguate a folder containing several sequences.
    Numbering gaps are allowed: each existing file is one consecutive displayed
    frame. FPS is explicit because standard PLY headers do not define timing.
    """
    source = Path(source).expanduser().resolve()
    if source.is_file():
        if source.suffix.lower() != '.ply':
            raise ValueError('Choose a numbered Gaussian PLY frame.')
        selected = _NUMBERED.fullmatch(source.stem)
        if selected is None:
            raise ValueError('Choose a frame with a number in its filename, such as frame_0001.ply.')
        family = (selected.group(1).casefold(), selected.group(3).casefold())
        folder = source.parent
    elif source.is_dir():
        family = None
        folder = source
    else:
        raise ValueError('Sequence folder or frame does not exist.')
    groups = {}
    # Enumerate one directory only. Never recurse through unrelated datasets.
    for path in folder.iterdir():
        if not path.is_file() or path.suffix.lower() != '.ply':
            continue
        match = _NUMBERED.fullmatch(path.stem)
        if match is None:
            continue
        key = (match.group(1).casefold(), match.group(3).casefold())
        if family is not None and key != family:
            continue
        group = groups.setdefault(key, [])
        group.append((int(match.group(2)), path))
        if len(group) > MAX_FRAMES:
            raise ValueError('Sequence exceeds the 10,000-frame limit.')
    if family is None:
        candidates = {key: paths for key, paths in groups.items() if len(paths) >= 2}
        if len(candidates) > 1:
            raise ValueError('This folder contains multiple numbered sequences. Choose one PLY frame to select its sequence.')
        if not candidates:
            raise ValueError('No sequence found. At least two consistently numbered Gaussian PLY files are needed.')
        frames = next(iter(candidates.values()))
    else:
        frames = groups.get(family, [])
    frames.sort(key=lambda item: item[0])
    if len({number for number, _ in frames}) != len(frames):
        raise ValueError('Two files use the same numeric frame number; rename or separate them before opening the sequence.')
    return PlySequence(tuple(str(path) for _, path in frames), fps)


@dataclass(frozen=True)
class SequenceFrame:
    index: int
    scene: dict
    packed: np.ndarray
    origin: np.ndarray
    scale: float
    nbytes: int


def prepare_frame(sequence, index):
    """Decode and pack on a worker thread; no GPU or Tk calls occur here."""
    from abu_m54 import load_scene
    index = _index(index, sequence.count)
    path = sequence.verify_frame(index)
    scene = load_scene(path, attach_companions=False)
    sequence.verify_frame(index)
    asset = scene.get('gaussians')
    if asset is None or asset.count != sequence.frames[index].count:
        raise ValueError(path.name + ': expected a nonempty Gaussian frame matching the preflight header.')
    origin = (asset.positions.min(axis=0) + asset.positions.max(axis=0)) * .5
    scale = max(float(np.linalg.norm(np.ptp(asset.positions, axis=0))), 1e-8)
    packed = asset.packed(origin, scale)
    packed.setflags(write=False)
    origin.setflags(write=False)
    # Source GaussianAsset arrays are already immutable. Sampled scene geometry
    # is immutable too; host transformations create derived display copies.
    for key in ('points', 'colors', 'gaussian_transform', 'center'):
        value = scene.get(key)
        if isinstance(value, np.ndarray):
            value.setflags(write=False)
    nbytes = asset.nbytes + packed.nbytes + sum(
        value.nbytes for value in scene.values() if isinstance(value, np.ndarray)) + origin.nbytes + 256
    return SequenceFrame(index, scene, packed, origin, scale, nbytes)


def default_cpu_budget():
    """Keep at least two thirds of currently available system memory outside us."""
    try:
        import psutil
        available = int(psutil.virtual_memory().available)
        return max(1, min(6 * 1024**3, available // 3))
    except (ImportError, OSError):
        return 2 * 1024**3


class CPUFrameCache:
    """Single-worker LRU cache with desired-frame priority and forward prefetch.

    The byte limit covers retained decoded arrays and prepared GPU copies owned
    by this cache; temporary allocations inside the existing decoder and assets
    retained by a GPU host are separate. Event records contain no frame arrays.
    Closing invalidates results and releases cached references immediately. An
    in-progress disk decode completes in its daemon worker, then is discarded.
    """

    def __init__(self, sequence, budget_bytes=None, *, loader=None):
        if not isinstance(sequence, PlySequence):
            raise TypeError('CPUFrameCache needs a validated PlySequence.')
        self.sequence = sequence
        self.budget_bytes = int(default_cpu_budget() if budget_bytes is None else budget_bytes)
        if self.budget_bytes < 1:
            raise ValueError('CPU cache budget must be positive.')
        largest = max(frame.cpu_bytes for frame in sequence.frames)
        if largest > self.budget_bytes:
            raise ValueError(f'One prepared frame needs approximately {largest / 1024**3:.2f} GiB, exceeding the CPU cache budget ({self.budget_bytes / 1024**3:.2f} GiB).')
        self.events = queue.Queue()
        self.errors = {}
        self._condition = threading.Condition()
        self._frames = OrderedDict()
        self._used_bytes = 0
        self._wanted = ()
        self._desired = 0
        self._loading_index = None
        self._closed = False
        self._loader = loader or prepare_frame
        self._thread = threading.Thread(target=self._work, name='M54 PLY sequence preparation', daemon=True)
        self._thread.start()
        self.request(0)

    @property
    def cached_indices(self):
        with self._condition:
            return tuple(self._frames)

    @property
    def used_bytes(self):
        with self._condition:
            return self._used_bytes

    @property
    def loading_index(self):
        with self._condition:
            return self._loading_index

    @property
    def closed(self):
        with self._condition:
            return self._closed

    def request(self, index):
        index = _index(index, self.sequence.count)
        with self._condition:
            if self._closed:
                return
            self._desired = index
            wanted, total = [], 0
            for step in range(self.sequence.count):
                candidate = (index + step) % self.sequence.count
                estimate = self.sequence.frames[candidate].cpu_bytes
                if total + estimate > self.budget_bytes:
                    break
                wanted.append(candidate)
                total += estimate
            self._wanted = tuple(wanted)
            self._condition.notify()

    def get(self, index):
        index = _index(index, self.sequence.count)
        with self._condition:
            frame = self._frames.get(index)
            if frame is not None:
                self._frames.move_to_end(index)
            return frame

    def close(self, wait=False):
        with self._condition:
            self._closed = True
            self._wanted = ()
            self._frames.clear()
            self._used_bytes = 0
            self.errors.clear()
            self._condition.notify_all()
        if wait and self._thread is not threading.current_thread():
            self._thread.join(timeout=10)

    def _evict_for(self, size, incoming):
        # Prefer frames outside the new prefetch window, then the oldest frame.
        for index in sorted(self._frames, key=lambda n: (n in self._wanted, n == self._desired)):
            if self._used_bytes + size <= self.budget_bytes:
                break
            old = self._frames.pop(index)
            self._used_bytes -= old.nbytes

    def _work(self):
        while True:
            with self._condition:
                index = next((n for n in self._wanted if n not in self._frames and n not in self.errors), None)
                while not self._closed and index is None:
                    self._condition.wait()
                    index = next((n for n in self._wanted if n not in self._frames and n not in self.errors), None)
                if self._closed:
                    return
                self._loading_index = index
                # Make room before decoding so normal forward streaming does
                # not retain the complete old window beside the new frame.
                self._evict_for(self.sequence.frames[index].cpu_bytes, index)
                self.events.put({'event': 'loading', 'index': index})
            frame = None
            error = None
            try:
                frame = self._loader(self.sequence, index)
                if frame.nbytes > self.budget_bytes:
                    raise ValueError('Decoded sequence frame exceeds the CPU cache byte budget.')
            except Exception as failure:
                error = str(failure)
            with self._condition:
                self._loading_index = None
                if self._closed:
                    return
                if index not in self._wanted:
                    # A seek superseded this disk decode. Never publish the
                    # wrong frame, and let the requested frame take priority.
                    frame = None
                    continue
                if error:
                    self.errors[index] = error
                    self.events.put({'event': 'error', 'index': index, 'error': error})
                else:
                    self._evict_for(frame.nbytes, index)
                    self._frames[index] = frame
                    self._used_bytes += frame.nbytes
                    self.events.put({'event': 'ready', 'index': index})
            # Do not leave an extra reference to a frame evicted by a seek.
            frame = None

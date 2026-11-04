# SPDX-License-Identifier: Apache-2.0
"""Bounded, context-local GPU residency for original M54 PLY sequence playback.

All entry points run on the viewport's current OpenGL thread. Decoding and
packing belong to the CPU sequence worker; this cache owns only GPU objects.
"""
from collections import OrderedDict

from abu_m54_splat_gpu import GaussianRenderer


def estimate_gpu_bytes(count):
    """Actual SSBO bytes: immutable splats, padded sort keys, projected splats."""
    count = int(count)
    if count < 0:
        raise ValueError('Gaussian count must be nonnegative.')
    if not count:
        return 0
    padded = max(256, 1 << (count - 1).bit_length())
    return count * 304 + padded * 8


class SequenceGPUCache:
    """Keep full frames resident, with bounded asynchronous-in-UI uploads.

    ``protected_index`` identifies the currently displayed frame. It is never
    evicted by a request. If the budget cannot hold it and the requested frame,
    ``BufferError`` tells the host to pause or release its display protection.
    The host must stop drawing a released renderer before making that choice.
    """

    def __init__(self, gl, budget_bytes=4 * 1024**3):
        budget = int(budget_bytes)
        if not 0 < budget <= 8 * 1024**3:
            raise ValueError('Sequence GPU budget must be positive and at most 8 GiB.')
        self.gl = gl
        self.budget_bytes = budget
        self.protected_index = None
        self._ready = OrderedDict()
        self._uploading = None
        self.closed = False

    @property
    def allocated_bytes(self):
        return sum(item.allocated_bytes for item in self._ready.values()) + (
            self._uploading[1].allocated_bytes if self._uploading is not None else 0)

    @property
    def cached_indices(self):
        return tuple(self._ready)

    @property
    def uploading_index(self):
        return self._uploading[0] if self._uploading is not None else None

    def contains(self, index):
        return index in self._ready

    def get(self, index):
        renderer = self._ready.get(index)
        if renderer is not None:
            self._ready.move_to_end(index)
        return renderer

    def cancel_upload(self):
        if self._uploading is not None:
            self._uploading[1].close()
            self._uploading = None

    def request(self, frame):
        """Start one prepared upload, or return True for an already ready frame."""
        if self.closed:
            raise RuntimeError('Sequence GPU cache is closed.')
        index = int(frame.index)
        if self.contains(index):
            self._ready.move_to_end(index)
            return True
        if self.uploading_index == index:
            return False
        asset = frame.scene.get('gaussians')
        if asset is None or not asset.count:
            raise ValueError('Sequence frame needs a nonempty Gaussian asset.')
        needed = estimate_gpu_bytes(asset.count)
        if needed > min(self.budget_bytes, 2 * 1024**3):
            raise BufferError('This frame exceeds the sequence or 2 GiB per-frame GPU budget.')
        protected = self._ready.get(self.protected_index)
        if needed + (protected.allocated_bytes if protected else 0) > self.budget_bytes:
            raise BufferError('GPU cache cannot hold the displayed frame and the next frame. '
                              'Increase the cache budget or pause and release the current frame.')
        self.cancel_upload()
        while self.allocated_bytes + needed > self.budget_bytes:
            victim = next((key for key in self._ready if key != self.protected_index), None)
            if victim is None:
                raise BufferError('Sequence GPU cache has no evictable frame.')
            self._ready.pop(victim).close()
        renderer = GaussianRenderer(self.gl, budget_bytes=min(self.budget_bytes, 2 * 1024**3))
        try:
            renderer.begin_asset(asset, prepared=(frame.packed, frame.origin, frame.scale))
        except Exception:
            renderer.close()
            raise
        self._uploading = index, renderer
        return False

    def step(self, max_bytes=16 * 1024**2):
        """Advance one upload; True means no unfinished upload remains."""
        if self._uploading is None:
            return True
        index, renderer = self._uploading
        try:
            ready = renderer.upload_step(max_bytes)
        except Exception:
            self.cancel_upload()
            raise
        if ready:
            self._ready[index] = renderer
            self._uploading = None
        return ready

    def close(self):
        """Release every buffer/program/query while the owning context is current."""
        self.cancel_upload()
        for renderer in self._ready.values():
            renderer.close()
        self._ready.clear()
        self.protected_index = None
        self.closed = True

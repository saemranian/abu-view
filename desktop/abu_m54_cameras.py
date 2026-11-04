# SPDX-License-Identifier: Apache-2.0
"""Original M54 render-camera and path math; world poses use right/down/forward."""
from dataclasses import dataclass
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation, Slerp


def _vector(value, length, label):
    array = np.array(value, dtype=np.float64, copy=True)
    if array.shape != (length,) or not np.isfinite(array).all():
        raise ValueError(f"{label} must contain {length} finite numbers")
    array.setflags(write=False)
    return array


@dataclass(frozen=True, eq=False)
class CameraPose:
    name: str
    position: np.ndarray
    quaternion_wxyz: np.ndarray
    fov_y_degrees: float = 45.0

    def __post_init__(self):
        name = str(self.name).strip()
        if not name or len(name) > 200:
            raise ValueError("Camera name must contain 1–200 characters")
        position = _vector(self.position, 3, "Camera position")
        quaternion = _vector(self.quaternion_wxyz, 4, "Camera quaternion")
        largest = float(np.max(np.abs(quaternion)))
        if largest == 0:
            raise ValueError("Camera quaternion cannot be zero")
        scaled = quaternion / largest
        quaternion = _vector(scaled / np.linalg.norm(scaled), 4, "Camera quaternion")
        fov = float(self.fov_y_degrees)
        if not np.isfinite(fov) or not 1 <= fov <= 170:
            raise ValueError("Vertical field of view must be between 1° and 170°")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "quaternion_wxyz", quaternion)
        object.__setattr__(self, "fov_y_degrees", fov)

    @property
    def rotation_matrix(self):
        return Rotation.from_quat(self.quaternion_wxyz[[1, 2, 3, 0]]).as_matrix()

    @property
    def c2w_matrix(self):
        matrix = np.eye(4, dtype=np.float64)
        matrix[:3, :3] = self.rotation_matrix
        matrix[:3, 3] = self.position
        return matrix

    @property
    def euler_xyz_degrees(self):
        return Rotation.from_matrix(self.rotation_matrix).as_euler("xyz", degrees=True)

    @classmethod
    def from_euler(cls, name, position, rotation_xyz_degrees, fov_y_degrees=45):
        angles = _vector(rotation_xyz_degrees, 3, "Camera rotation")
        quaternion = Rotation.from_euler("xyz", angles, degrees=True).as_quat()
        return cls(name, position, quaternion[[3, 0, 1, 2]], fov_y_degrees)

    def view_matrix(self, origin=(0, 0, 0), scale=1.0):
        origin = _vector(origin, 3, "Scene origin")
        scale = float(scale)
        if not np.isfinite(scale) or scale <= 0:
            raise ValueError("Scene scale must be positive")
        rotation = np.diag([1., -1., -1.]) @ self.rotation_matrix.T
        matrix = np.eye(4, dtype=np.float64)
        matrix[:3, :3] = rotation
        matrix[:3, 3] = -rotation @ ((self.position - origin) / scale)
        return matrix

    def projection_matrix(self, width, height, near=.01, far=100000.):
        width, height = int(width), int(height)
        near, far = float(near), float(far)
        if width <= 0 or height <= 0 or not np.isfinite([near, far]).all() or not 0 < near < far:
            raise ValueError("Projection needs positive dimensions and 0 < near < far")
        f = 1 / math.tan(math.radians(self.fov_y_degrees) / 2)
        matrix = np.zeros((4, 4), dtype=np.float64)
        matrix[0, 0] = f * height / width
        matrix[1, 1] = f
        matrix[2, 2] = (far + near) / (near - far)
        matrix[2, 3] = 2 * far * near / (near - far)
        matrix[3, 2] = -1
        return matrix

    def to_dict(self):
        return {"name": self.name, "position": self.position.tolist(),
                "quaternion_wxyz": self.quaternion_wxyz.tolist(),
                "fov_y_degrees": self.fov_y_degrees}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Invalid camera record")
        return cls(value["name"], value["position"], value["quaternion_wxyz"], value.get("fov_y_degrees", 45))


@dataclass(frozen=True)
class CameraKeyframe:
    time_seconds: float
    camera: CameraPose

    def __post_init__(self):
        time = float(self.time_seconds)
        if not math.isfinite(time) or time < 0 or time > 86400:
            raise ValueError("Keyframe time must be between 0 and 86400 seconds")
        if not isinstance(self.camera, CameraPose):
            raise ValueError("Keyframe needs a camera pose")
        object.__setattr__(self, "time_seconds", time)

    def to_dict(self):
        return {"time_seconds": self.time_seconds, "camera": self.camera.to_dict()}


@dataclass(frozen=True)
class CameraPath:
    keyframes: tuple
    interpolation: str = "linear"

    def __post_init__(self):
        keys = tuple(self.keyframes)
        if not 1 <= len(keys) <= 10000 or not all(isinstance(k, CameraKeyframe) for k in keys):
            raise ValueError("A path must contain 1–10000 camera keyframes")
        times = np.asarray([k.time_seconds for k in keys])
        if times[0] != 0 or np.any(np.diff(times) <= 0):
            raise ValueError("Keyframes must start at 0 and have strictly increasing times")
        if self.interpolation not in ("linear", "smooth"):
            raise ValueError("Path interpolation must be linear or smooth")
        object.__setattr__(self, "keyframes", keys)

    @property
    def duration(self):
        return self.keyframes[-1].time_seconds

    def sample(self, time_seconds):
        time = float(time_seconds)
        if not math.isfinite(time):
            raise ValueError("Preview time must be finite")
        keys = self.keyframes
        if time <= 0 or len(keys) == 1:
            return keys[0].camera
        if time >= self.duration:
            return keys[-1].camera
        times = np.asarray([k.time_seconds for k in keys])
        i = int(np.searchsorted(times, time, side="right")) - 1
        a, b = keys[i], keys[i + 1]
        span = b.time_seconds - a.time_seconds
        u = (time - a.time_seconds) / span
        if self.interpolation == "smooth":
            # Cubic Hermite translation with time-aware tangents; orientation stays
            # shortest-arc SLERP. End tangents follow their adjacent segment.
            def tangent(index):
                left, right = max(0, index - 1), min(len(keys) - 1, index + 1)
                return ((keys[right].camera.position - keys[left].camera.position) /
                        (keys[right].time_seconds - keys[left].time_seconds))
            position = ((2*u**3-3*u**2+1)*a.camera.position +
                        (u**3-2*u**2+u)*span*tangent(i) +
                        (-2*u**3+3*u**2)*b.camera.position +
                        (u**3-u**2)*span*tangent(i + 1))
        else:
            position = (1-u)*a.camera.position + u*b.camera.position
        rotations = Rotation.from_quat(np.array([a.camera.quaternion_wxyz, b.camera.quaternion_wxyz])[:, [1, 2, 3, 0]])
        quaternion = Slerp([0., 1.], rotations)(u).as_quat()[[3, 0, 1, 2]]
        fov = (1-u)*a.camera.fov_y_degrees + u*b.camera.fov_y_degrees
        return CameraPose(f"Path {time:.3f}s", position, quaternion, fov)

    def to_dict(self):
        return {"interpolation": self.interpolation, "keyframes": [key.to_dict() for key in self.keyframes]}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or not isinstance(value.get("keyframes"), list) or len(value["keyframes"]) > 10000:
            raise ValueError("Invalid camera path")
        return cls(tuple(CameraKeyframe(k["time_seconds"], CameraPose.from_dict(k["camera"]))
                         for k in value["keyframes"]), value.get("interpolation", "linear"))


def save_camera_project(path, cameras, camera_path=None):
    cameras = tuple(cameras)
    if len(cameras) > 10000 or not all(isinstance(camera, CameraPose) for camera in cameras):
        raise ValueError("Invalid camera library")
    data = {"schema": "abu-m54-cameras-1", "cameras": [camera.to_dict() for camera in cameras],
            "path": camera_path.to_dict() if camera_path else None}
    target = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=".m54-cameras-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(data, indent=2, allow_nan=False))
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_camera_project(path):
    target = Path(path)
    if target.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Camera project is larger than 16 MiB")
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != "abu-m54-cameras-1":
        raise ValueError("Unsupported M54 camera project")
    records = data.get("cameras")
    if not isinstance(records, list) or len(records) > 10000:
        raise ValueError("Invalid camera library")
    cameras = [CameraPose.from_dict(record) for record in records]
    camera_path = CameraPath.from_dict(data["path"]) if data.get("path") is not None else None
    return cameras, camera_path


@dataclass(frozen=True)
class RenderSettings:
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    format: str = "png"
    supersampling: int = 1
    quality: int = 85
    encoder: str = "auto"
    ffmpeg_path: str = ""
    background: tuple = (0.063, 0.078, 0.09)
    near: float = .01
    far: float = 100000.0

    def __post_init__(self):
        for field, low, high in (("width", 16, 8192), ("height", 16, 8192), ("quality", 1, 100)):
            value = getattr(self, field)
            if isinstance(value, bool) or not float(value).is_integer() or not low <= int(value) <= high:
                raise ValueError(f"{field.capitalize()} must be an integer between {low} and {high}")
            object.__setattr__(self, field, int(value))
        fps = float(self.fps)
        if not math.isfinite(fps) or not 1 <= fps <= 240:
            raise ValueError("Frame rate must be between 1 and 240 fps")
        if self.format not in ("png", "jpeg", "sequence", "mp4"):
            raise ValueError("Unsupported render format")
        if self.encoder not in ("auto", "nvenc", "cpu") or self.supersampling not in (1, 2):
            raise ValueError("Invalid render quality or encoder selection")
        if not isinstance(self.ffmpeg_path, str) or len(self.ffmpeg_path) > 32767 or "\x00" in self.ffmpeg_path:
            raise ValueError("Invalid FFmpeg executable path")
        if max(self.width, self.height) * self.supersampling > 8192 or self.width * self.height * self.supersampling**2 > 33554432:
            raise ValueError("Supersampled output exceeds the 8192-pixel / 32-megapixel render limit")
        if self.format == "mp4" and (self.width % 2 or self.height % 2):
            raise ValueError("MP4 needs even width and height")
        background = _vector(self.background, 3, "Background color")
        if np.any(background < 0) or np.any(background > 1):
            raise ValueError("Background RGB values must be between 0 and 1")
        near, far = float(self.near), float(self.far)
        if not np.isfinite([near, far]).all() or not 0 < near < far:
            raise ValueError("Clipping planes must satisfy 0 < near < far")
        object.__setattr__(self, "fps", fps)
        object.__setattr__(self, "background", tuple(background))
        object.__setattr__(self, "near", near)
        object.__setattr__(self, "far", far)

    def to_dict(self):
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Invalid render settings")
        unknown = set(value) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError("Unknown render setting: " + ", ".join(sorted(unknown)))
        return cls(**value)

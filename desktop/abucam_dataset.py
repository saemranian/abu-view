"""Validated, immutable calibrated AbuCam inputs for independent 3DGS frames.

AbuCam camera poses are authoritative. No feature matching, pose estimation, cloud
reuse between animation frames, reorientation or implicit rescaling is performed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import struct
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation

SCHEMA = 1
FRAME_RE = re.compile(r"^frame_(\d+)$", re.IGNORECASE)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr"}


def create_windows_shortcut(lnk_path, target_path, description: str = "") -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]
            def __init__(self, l, w1, w2, b1, b2, b3, b4, b5, b6, b7, b8):
                super().__init__(l, w1, w2, (ctypes.c_ubyte * 8)(b1, b2, b3, b4, b5, b6, b7, b8))

        clsid_sl = _GUID(0x00021401, 0x0000, 0x0000, 0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46)
        iid_sl = _GUID(0x000214F9, 0x0000, 0x0000, 0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46)
        iid_pf = _GUID(0x0000010B, 0x0000, 0x0000, 0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46)
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        p_sl = ctypes.c_void_p()
        if ole32.CoCreateInstance(ctypes.byref(clsid_sl), None, 1, ctypes.byref(iid_sl), ctypes.byref(p_sl)) < 0 or not p_sl.value:
            return False
        try:
            vtbl_sl = ctypes.cast(ctypes.cast(p_sl, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
            set_path = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR)(vtbl_sl[20])
            set_desc = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR)(vtbl_sl[7])
            query_if = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))(vtbl_sl[0])
            release_sl = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl_sl[2])
            set_path(p_sl, str(Path(target_path).resolve()))
            if description:
                set_desc(p_sl, description)
            p_pf = ctypes.c_void_p()
            if query_if(p_sl, ctypes.byref(iid_pf), ctypes.byref(p_pf)) < 0 or not p_pf.value:
                return False
            try:
                vtbl_pf = ctypes.cast(ctypes.cast(p_pf, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
                save_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, wintypes.BOOL)(vtbl_pf[6])
                release_pf = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl_pf[2])
                return save_fn(p_pf, str(Path(lnk_path).resolve()), True) >= 0
            finally:
                release_pf(p_pf)
        finally:
            release_sl(p_sl)
    except Exception:
        return False


def resolve_windows_shortcut(lnk_path) -> str:
    if os.name != "nt" or not Path(lnk_path).is_file():
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]
            def __init__(self, l, w1, w2, b1, b2, b3, b4, b5, b6, b7, b8):
                super().__init__(l, w1, w2, (ctypes.c_ubyte * 8)(b1, b2, b3, b4, b5, b6, b7, b8))

        clsid_sl = _GUID(0x00021401, 0x0000, 0x0000, 0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46)
        iid_sl = _GUID(0x000214F9, 0x0000, 0x0000, 0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46)
        iid_pf = _GUID(0x0000010B, 0x0000, 0x0000, 0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46)
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        p_sl = ctypes.c_void_p()
        if ole32.CoCreateInstance(ctypes.byref(clsid_sl), None, 1, ctypes.byref(iid_sl), ctypes.byref(p_sl)) < 0 or not p_sl.value:
            return ""
        try:
            vtbl_sl = ctypes.cast(ctypes.cast(p_sl, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
            get_path = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPWSTR, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)(vtbl_sl[3])
            query_if = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))(vtbl_sl[0])
            release_sl = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl_sl[2])
            p_pf = ctypes.c_void_p()
            if query_if(p_sl, ctypes.byref(iid_pf), ctypes.byref(p_pf)) < 0 or not p_pf.value:
                return ""
            try:
                vtbl_pf = ctypes.cast(ctypes.cast(p_pf, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
                load_fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.LPCWSTR, wintypes.DWORD)(vtbl_pf[5])
                release_pf = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl_pf[2])
                if load_fn(p_pf, str(Path(lnk_path).resolve()), 0) < 0:
                    return ""
                buf = ctypes.create_unicode_buffer(2600)
                if get_path(p_sl, buf, 2600, None, 0) < 0:
                    return ""
                return buf.value
            finally:
                release_pf(p_pf)
        finally:
            release_sl(p_sl)
    except Exception:
        return ""



class AbuCamValidationError(ValueError):
    """A calibrated export cannot safely be used as a training input."""


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise AbuCamValidationError(f"Cannot read {path}: {exc}") from exc


def _within(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise AbuCamValidationError(f"Export reference leaves its source folder: {path}")
    return path


def _digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _source_marker(root):
    """Find an exporter marker without treating arbitrary NeRF folders as AbuCam."""
    for folder in (root, root.parent if FRAME_RE.match(root.name) else root):
        for name in ("abucam_dataset.json", "abucam_export_manifest.json", "abucam_render_manifest.json"):
            candidate = folder / name
            if candidate.is_file():
                return candidate, _json(candidate)
        candidate = folder / "metadata" / "point_cloud_sequence.json"
        if candidate.is_file():
            return candidate, _json(candidate)
    return None, {}


def is_abucam_dataset(path):
    """Cheap source picker predicate; validation is deliberately a separate step."""
    root = Path(path).expanduser()
    if root.is_file():
        root = root.parent
    if not root.is_dir():
        return False
    try:
        marker, _ = _source_marker(root)
        if marker:
            return True
    except AbuCamValidationError:
        return True  # Let the detailed inspector explain a malformed marker.
    dirs = [p for p in root.iterdir() if p.is_dir() and FRAME_RE.match(p.name)]
    candidates = dirs or [root]
    return any((p / "transforms.json").is_file() and
               (FRAME_RE.match(p.name) or (p / "cameras.csv").is_file() or
                any(p.glob("cam_*.png"))) for p in candidates)


def _convention(document, marker, marker_path, requested):
    value = requested or document.get("camera_convention") or marker.get("camera_convention")
    if isinstance(value, str):
        value = value.lower().replace("_", "").replace("-", "").replace(" ", "")
        if value in {"opengl", "nerf", "nerfstudio", "blender"}:
            return "opengl"
        if value in {"opencv", "colmap"}:
            return "opencv"
        raise AbuCamValidationError(f"Unsupported camera convention: {value}")
    # UE's existing MRQ export writes documented NeRF/OpenGL c2w matrices. Old
    # Blender builds wrote inconsistent axes, so never infer those from filenames.
    if marker.get("backend") == "MovieRenderQueue" or (
        marker_path and marker_path.name == "point_cloud_sequence.json" and
        marker.get("coordinate_frame") == "RH_Z_UP_world_meters"
    ):
        return "opengl"
    raise AbuCamValidationError(
        "Camera axis convention is not recorded. Re-export using the updated AbuCam "
        "addon or explicitly select the documented OpenGL/OpenCV convention; legacy "
        "Blender transforms must not be guessed."
    )


def _positive(value, name):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AbuCamValidationError(f"Missing or invalid {name} calibration.") from exc
    if not math.isfinite(number) or number <= 0:
        raise AbuCamValidationError(f"{name} must be finite and positive.")
    return number


def _pose(value, convention):
    try:
        matrix = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise AbuCamValidationError("Camera pose is not a numerical 4 by 4 matrix.") from exc
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all():
        raise AbuCamValidationError("Camera pose must be a finite 4 by 4 matrix.")
    if not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-7, rtol=0):
        raise AbuCamValidationError("Invalid homogeneous camera pose.")
    rotation = matrix[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5, rtol=0) or not np.isclose(
        np.linalg.det(rotation), 1, atol=1e-5, rtol=0
    ):
        raise AbuCamValidationError("Camera rotation contains scale, shear or a reflection.")
    matrix = matrix.copy()
    if convention == "opencv":
        matrix[:3, 1:3] *= -1
    return matrix


def _cloud_info(path):
    """Read only PLY's bounded header here; preparation uses M54's shared reader."""
    with Path(path).open("rb") as stream:
        header = []
        for _ in range(1024):
            line = stream.readline(4096)
            if not line or len(line) >= 4096:
                raise AbuCamValidationError(f"Invalid PLY header: {path}")
            text = line.decode("ascii", errors="strict").strip()
            header.append(text)
            if text == "end_header":
                break
        else:
            raise AbuCamValidationError(f"PLY header is too long: {path}")
    if not header or header[0] != "ply" or header[-1] != "end_header":
        raise AbuCamValidationError(f"Invalid PLY file: {path}")
    count = next((int(s.split()[-1]) for s in header if s.startswith("element vertex ")), 0)
    if count <= 0 or count > 20_000_000:
        raise AbuCamValidationError(f"PLY must contain 1 to 20,000,000 seed points: {path}")
    props = {s.split()[-1] for s in header if s.startswith("property ")}
    if not {"x", "y", "z"}.issubset(props):
        raise AbuCamValidationError(f"PLY has no XYZ geometry: {path}")
    return {"point_count": count, "colored": {"red", "green", "blue"}.issubset(props)}


def _colmap_text(folder):
    cameras, images = {}, {}
    camera_path, image_path = folder / "cameras.txt", folder / "images.txt"
    if not camera_path.is_file() or not image_path.is_file():
        return None
    for line in camera_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split()
        camera_id = int(fields[0])
        if camera_id in cameras:
            raise AbuCamValidationError("Duplicate COLMAP camera ID.")
        cameras[camera_id] = (fields[1], int(fields[2]), int(fields[3]), [float(v) for v in fields[4:]])
    lines = image_path.read_text(encoding="utf-8-sig").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line or line.startswith("#"):
            continue
        fields = line.split(maxsplit=9)
        if len(fields) != 10:
            raise AbuCamValidationError("Invalid COLMAP image record.")
        name = fields[9].replace("\\", "/")
        if name in images:
            raise AbuCamValidationError(f"Duplicate COLMAP image name: {name}")
        images[name] = (int(fields[8]), [float(v) for v in fields[1:5]], [float(v) for v in fields[5:8]])
        index += 1  # Observation line belongs to the image, including an empty one.
    return cameras, images


def _colmap_binary(folder):
    cameras, images = {}, {}
    if not (folder / "cameras.bin").is_file() or not (folder / "images.bin").is_file():
        return None
    def exact(stream, count):
        block = stream.read(count)
        if len(block) != count:
            raise AbuCamValidationError("Truncated COLMAP binary calibration.")
        return block
    with (folder / "cameras.bin").open("rb") as stream:
        count = struct.unpack("<Q", exact(stream, 8))[0]
        if count > 1_000_000:
            raise AbuCamValidationError("Invalid COLMAP camera count.")
        for _ in range(count):
            camera_id, model, width, height = struct.unpack("<iiQQ", exact(stream, 24))
            if model not in {0, 1}:
                raise AbuCamValidationError("AbuCam supports undistorted SIMPLE_PINHOLE/PINHOLE calibration only.")
            parameters = struct.unpack("<" + "d" * (3 if model == 0 else 4), exact(stream, 24 if model == 0 else 32))
            if camera_id in cameras:
                raise AbuCamValidationError("Duplicate COLMAP camera ID.")
            cameras[camera_id] = ("SIMPLE_PINHOLE" if model == 0 else "PINHOLE", width, height, parameters)
    with (folder / "images.bin").open("rb") as stream:
        count = struct.unpack("<Q", exact(stream, 8))[0]
        if count > 1_000_000:
            raise AbuCamValidationError("Invalid COLMAP image count.")
        for _ in range(count):
            data = struct.unpack("<idddddddi", exact(stream, 64))
            name = bytearray()
            while True:
                char = exact(stream, 1)
                if char == b"\0":
                    break
                name.extend(char)
                if len(name) > 4096:
                    raise AbuCamValidationError("COLMAP image name is too long.")
            key = name.decode("utf-8").replace("\\", "/")
            if key in images:
                raise AbuCamValidationError("Duplicate COLMAP image name.")
            images[key] = (data[8], data[1:5], data[5:8])
            observations = struct.unpack("<Q", exact(stream, 8))[0]
            if observations > 100_000_000:
                raise AbuCamValidationError("Invalid COLMAP observation count.")
            stream.seek(observations * 24, os.SEEK_CUR)
            if stream.tell() > (folder / "images.bin").stat().st_size:
                raise AbuCamValidationError("Truncated COLMAP observations.")
    return cameras, images


def _validate_colmap(source, expected):
    models = [source / "sparse" / "0", source / "colmap" / "sparse" / "0", source]
    for folder in models:
        for model in (_colmap_text(folder), _colmap_binary(folder)):
            if model is None:
                continue
            cameras, images = model
            expected_names = {camera["image_name"] for camera in expected}
            if set(images) != expected_names:
                raise AbuCamValidationError("COLMAP cameras/images and RGB transforms do not reference the same image names.")
            for camera in expected:
                intrinsics_id, quaternion, translation = images[camera["image_name"]]
                if intrinsics_id not in cameras:
                    raise AbuCamValidationError("COLMAP image references missing camera intrinsics.")
                model_name, width, height, parameters = cameras[intrinsics_id]
                if model_name == "SIMPLE_PINHOLE" and len(parameters) == 3:
                    parameters = [parameters[0], parameters[0], *parameters[1:]]
                elif model_name != "PINHOLE" or len(parameters) != 4:
                    raise AbuCamValidationError("Only undistorted pinhole AbuCam inputs are supported.")
                if (width, height) != (camera["w"], camera["h"]) or not np.allclose(
                    parameters, [camera[k] for k in ("fx", "fy", "cx", "cy")], atol=1e-3, rtol=1e-6
                ):
                    raise AbuCamValidationError(f"COLMAP intrinsics differ from RGB calibration for {camera['image_name']}.")
                q = np.asarray(quaternion, dtype=float)
                if not np.isfinite(q).all() or not np.isclose(np.linalg.norm(q), 1, atol=1e-5):
                    raise AbuCamValidationError("Invalid COLMAP camera quaternion.")
                rotation = Rotation.from_quat(q[[1, 2, 3, 0]]).as_matrix()
                cv_c2w = np.eye(4)
                cv_c2w[:3, :3] = rotation.T
                cv_c2w[:3, 3] = -rotation.T @ np.asarray(translation)
                cv_c2w[:3, 1:3] *= -1
                if not np.allclose(cv_c2w, camera["transform_matrix"], atol=1e-5, rtol=0):
                    raise AbuCamValidationError(f"COLMAP pose differs from RGB transform for {camera['image_name']}.")


def _inspect_frame(source, root, marker, marker_path, requested, index, fps, record):
    frame = {"id": source.name if FRAME_RE.match(source.name) else "frame_0001", "index": index,
             "time_seconds": (index - 1) / fps, "source_dir": str(source), "ready": False,
             "errors": [], "warnings": [], "cameras": []}
    try:
        transform_path = source / "transforms.json"
        if not transform_path.is_file():
            transform_path = source / "metadata" / "transforms.json"
        document = _json(transform_path)
        convention = _convention(document, marker, marker_path, requested)
        frame["source_camera_convention"] = convention
        frame["transforms_path"] = str(transform_path)
        frame["coordinate_frame"] = document.get("coordinate_frame", marker.get("coordinate_frame", "exporter_world"))
        entries = document.get("frames")
        if not isinstance(entries, list) or not entries:
            raise AbuCamValidationError("transforms.json contains no calibrated camera images.")
        seen_names, seen_ids = set(), set()
        for position, entry in enumerate(entries, 1):
            if not isinstance(entry, dict):
                raise AbuCamValidationError("Invalid camera entry in transforms.json.")
            projection = str(entry.get("camera_model", document.get("camera_model", "PINHOLE"))).upper()
            if projection not in {"PINHOLE", "SIMPLE_PINHOLE", "OPENCV", "PERSPECTIVE"}:
                raise AbuCamValidationError(f"Unsupported AbuCam projection {projection}; perspective pinhole RGB is required.")
            raw_name = entry.get("file_path")
            if not isinstance(raw_name, str) or not raw_name:
                raise AbuCamValidationError("Every calibrated camera needs its rendered image file_path.")
            raw_rel = raw_name.replace("\\", "/")
            image_path = _within(transform_path.parent / raw_rel, root)
            if not image_path.is_file():
                lnk_candidate = Path(str(image_path) + ".lnk")
                if lnk_candidate.is_file():
                    resolved_target = resolve_windows_shortcut(lnk_candidate)
                    if resolved_target:
                        image_path = _within(Path(resolved_target), root)
            if not image_path.is_file():
                canonical = root / "passes" / "rgb" / frame["id"] / Path(raw_rel).name
                if canonical.is_file():
                    image_path = _within(canonical, root)
            if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
                raise AbuCamValidationError(f"Missing rendered RGB image: {raw_name}")
            name = image_path.name
            if name.casefold() in seen_names:
                raise AbuCamValidationError(f"Duplicate or ambiguous camera image name: {name}")
            seen_names.add(name.casefold())
            camera_id = entry.get("camera_id", position)
            if str(camera_id) in seen_ids:
                raise AbuCamValidationError("Duplicate camera identity in transforms.json.")
            seen_ids.add(str(camera_id))
            values = {key: entry.get(key, document.get(key)) for key in ("w", "h", "fl_x", "fl_y", "cx", "cy")}
            width, height = _positive(values["w"], "width"), _positive(values["h"], "height")
            if int(width) != width or int(height) != height:
                raise AbuCamValidationError("Calibrated image dimensions must be whole pixels.")
            width, height = int(width), int(height)
            with Image.open(image_path) as image:
                if image.size != (width, height):
                    raise AbuCamValidationError(f"Rendered image dimensions differ from calibration: {name}")
            fx, fy = _positive(values["fl_x"], "fl_x"), _positive(values["fl_y"], "fl_y")
            try:
                cx, cy = float(values["cx"]), float(values["cy"])
            except (TypeError, ValueError) as exc:
                raise AbuCamValidationError("Missing calibrated principal point.") from exc
            if not (math.isfinite(cx) and math.isfinite(cy)):
                raise AbuCamValidationError("Principal point must be finite.")
            for key in ("k1", "k2", "k3", "k4", "p1", "p2"):
                if abs(float(entry.get(key, document.get(key, 0)))) > 1e-12:
                    raise AbuCamValidationError("Distorted camera input requires a matching undistortion adapter.")
            frame["cameras"].append({"camera_id": camera_id, "name": entry.get("camera_name", image_path.stem),
                "image_name": name, "image_path": str(image_path), "w": width, "h": height,
                "fx": fx, "fy": fy, "cx": cx, "cy": cy,
                "transform_matrix": _pose(entry.get("transform_matrix"), convention).tolist()})
        # Cross-check available calibration before deriving any engine input.
        _validate_colmap(source, frame["cameras"])
        cloud = source / "points3D.ply"
        if record:
            if record.get("ply"):
                cloud = _within(root / record["ply"], source)
            if "time_seconds" in record:
                frame["time_seconds"] = float(record["time_seconds"])
        if not cloud.is_file():
            raise AbuCamValidationError(
                f"{frame['id']} has no frame-local points3D.ply. Re-export with per-frame "
                "Mesh2Points enabled in the updated AbuCam addon. A root cloud represents "
                "only its first frame and cannot seed the other animated poses."
            )
        frame["cloud_path"] = str(cloud)
        frame.update(_cloud_info(cloud))
        if not frame["colored"]:
            frame["warnings"].append("Seed cloud has no RGB properties; training still uses the rendered RGB images.")
        frame["image_count"] = len(frame["cameras"])
        frame["fingerprint"] = _fingerprint({"transforms": _digest_file(transform_path),
            "cloud": _digest_file(cloud), "convention": convention,
            "images": [(c["image_name"], _digest_file(c["image_path"])) for c in frame["cameras"]]})
        frame["ready"] = True
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, struct.error) as exc:
        frame["errors"].append(str(exc))
    return frame


def discover_abucam_dataset(path, *, camera_convention=None, strict=False):
    """Inspect an export root or one explicit frame, preserving its exact calibration.

    The JSON-safe report is useful to source pickers even if a legacy/incomplete
    export is not trainable. ``strict=True`` rejects any incomplete frame.
    """
    selected = Path(path).expanduser().resolve()
    if selected.is_file():
        selected = selected.parent
    report = {"schema": SCHEMA, "source_path": str(selected), "source_root": str(selected),
              "kind": "single_frame", "fps": 24.0, "ready": False,
              "frames": [], "errors": [], "warnings": []}
    try:
        if not selected.is_dir():
            raise AbuCamValidationError(f"Dataset folder does not exist: {selected}")
        marker_path, marker = _source_marker(selected)
        if marker.get("schema_version", marker.get("schema", 1)) != 1:
            raise AbuCamValidationError("Unsupported AbuCam export schema. Update Abu Align & Train before opening it.")
        root = marker_path.parent if marker_path and marker_path.parent.name != "metadata" else (
            marker_path.parent.parent if marker_path else selected)
        report["source_root"] = str(root)
        report["exporter"] = marker.get("source_app", marker.get("exporter", "unreal" if marker.get("backend") == "MovieRenderQueue" else "abucam"))
        report["marker_path"] = str(marker_path) if marker_path else None
        status = str(marker.get("status", "complete")).lower()
        if status not in {"complete", "completed", "success", "succeeded"}:
            raise AbuCamValidationError(f"AbuCam export is not complete (status: {status}). Finish or re-export it first.")
        report["fps"] = _positive(marker.get("fps", marker.get("settings", {}).get("fps", 24)), "fps")
        frame_sources = sorted([p for p in selected.iterdir() if p.is_dir() and FRAME_RE.match(p.name)],
                               key=lambda p: int(FRAME_RE.match(p.name).group(1)))
        if not frame_sources:
            frame_sources = [selected]
        if len(frame_sources) > 1:
            report["kind"] = "frame_sequence"
        cloud_manifest = root / "metadata" / "point_cloud_sequence.json"
        records = {}
        declared_frames = marker.get("frames", marker.get("sequence", []))
        if marker_path and marker_path.name == "abucam_dataset.json" and declared_frames:
            declared_sources = []
            for position, record in enumerate(declared_frames, 1):
                frame_id = str(record.get("frame_id", f"frame_{position:04d}"))
                match = FRAME_RE.fullmatch(frame_id)
                if not match:
                    raise AbuCamValidationError("Export manifest contains an invalid frame_id.")
                index = int(record.get("index", match.group(1)))
                if index in records:
                    raise AbuCamValidationError("Duplicate frame in AbuCam dataset manifest.")
                transforms = _within(root / record["transforms"], root)
                frame_source = transforms.parent
                if selected == root or frame_source == selected:
                    normalized = dict(record)
                    normalized["frame"] = index
                    normalized["time_seconds"] = record.get("time_seconds", record.get("timestamp_seconds", (index - 1) / report["fps"]))
                    normalized["ply"] = record.get("point_cloud")
                    records[index] = normalized
                    declared_sources.append(frame_source)
            if declared_sources:
                frame_sources = declared_sources
                report["kind"] = "frame_sequence" if len(frame_sources) > 1 else "single_frame"
        if cloud_manifest.is_file():
            metadata = _json(cloud_manifest)
            if str(metadata.get("status", "complete")).lower() not in {"complete", "completed"}:
                raise AbuCamValidationError("Per-frame point-cloud export is incomplete.")
            report["fps"] = _positive(metadata.get("fps", report["fps"]), "fps")
            for record in metadata.get("frames", []):
                number = int(record.get("frame", record.get("index", 0)))
                existing = records.get(number, {})
                records[number] = {**existing, **record}
        numbers = []
        for position, source in enumerate(frame_sources, 1):
            match = FRAME_RE.match(source.name)
            index = int(match.group(1)) if match else position
            if index < 1 or index in numbers:
                raise AbuCamValidationError("Duplicate animation frame index.")
            numbers.append(index)
            report["frames"].append(_inspect_frame(source, root, marker, marker_path, camera_convention,
                                                    index, report["fps"], records.get(index)))
        report["errors"] = [f"{f['id']}: {error}" for f in report["frames"] for error in f["errors"]]
        report["warnings"] = [warning for f in report["frames"] for warning in f["warnings"]]
        times = [f["time_seconds"] for f in report["frames"]]
        if not all(math.isfinite(t) and t >= 0 for t in times) or any(b <= a for a, b in zip(times, times[1:])):
            report["errors"].append("Animation frame times must be finite and strictly increasing.")
        report["ready"] = bool(report["frames"]) and not report["errors"]
        report["frame_count"] = len(report["frames"])
        report["image_count"] = sum(f.get("image_count", len(f["cameras"])) for f in report["frames"])
        report["fingerprint"] = _fingerprint([(f["id"], f.get("fingerprint"), f["time_seconds"]) for f in report["frames"]])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["errors"].append(str(exc))
    if strict and not report["ready"]:
        raise AbuCamValidationError("\n".join(report["errors"]))
    return report


inspect_abucam_dataset = discover_abucam_dataset


def _write_colmap(folder, cameras, points, colors):
    folder.mkdir(parents=True)
    intrinsics, rows = {}, []
    for image_id, camera in enumerate(cameras, 1):
        key = tuple(camera[k] for k in ("w", "h", "fx", "fy", "cx", "cy"))
        camera_id = intrinsics.setdefault(key, len(intrinsics) + 1)
        cv_c2w = np.asarray(camera["transform_matrix"], dtype=np.float64).copy()
        cv_c2w[:3, 1:3] *= -1
        rotation = cv_c2w[:3, :3].T
        translation = -rotation @ cv_c2w[:3, 3]
        q = Rotation.from_matrix(rotation).as_quat()[[3, 0, 1, 2]]
        rows.append((image_id, q, translation, camera_id, camera["image_name"]))
    with (folder / "cameras.txt").open("w", encoding="utf-8", newline="\n") as text, (folder / "cameras.bin").open("wb") as binary:
        text.write("# CAMERA_ID MODEL WIDTH HEIGHT FX FY CX CY\n")
        binary.write(struct.pack("<Q", len(intrinsics)))
        for (width, height, fx, fy, cx, cy), camera_id in intrinsics.items():
            text.write(f"{camera_id} PINHOLE {width} {height} {fx:.17g} {fy:.17g} {cx:.17g} {cy:.17g}\n")
            binary.write(struct.pack("<iiQQdddd", camera_id, 1, width, height, fx, fy, cx, cy))
    with (folder / "images.txt").open("w", encoding="utf-8", newline="\n") as text, (folder / "images.bin").open("wb") as binary:
        text.write("# IMAGE_ID QW QX QY QZ TX TY TZ CAMERA_ID NAME\n# Next line: observations (seed geometry has no estimated feature tracks).\n")
        binary.write(struct.pack("<Q", len(rows)))
        for image_id, q, t, camera_id, name in rows:
            text.write(f"{image_id} " + " ".join(f"{v:.17g}" for v in [*q, *t]) + f" {camera_id} {name}\n\n")
            binary.write(struct.pack("<idddddddi", image_id, *q, *t, camera_id))
            binary.write(name.encode("utf-8") + b"\0" + struct.pack("<Q", 0))
    with (folder / "points3D.txt").open("w", encoding="utf-8", newline="\n") as text, (folder / "points3D.bin").open("wb") as binary:
        text.write("# POINT3D_ID X Y Z R G B ERROR (exact Mesh2Points geometry; no synthetic feature observations)\n")
        binary.write(struct.pack("<Q", len(points)))
        for index, (point, color) in enumerate(zip(points, colors), 1):
            text.write(f"{index} " + " ".join(f"{v:.17g}" for v in point) + " " + " ".join(str(int(v)) for v in color) + " 0\n")
            binary.write(struct.pack("<QdddBBBdQ", index, *point, *color, 0.0, 0))


def prepare_abucam_frame(frame, output_dir, downscale="original"):
    """Create a derived engine package; never link mutable calibration or cloud files."""
    if not frame.get("ready"):
        raise AbuCamValidationError("; ".join(frame.get("errors", ["Frame has not passed calibration validation."])))
    parent = Path(output_dir).resolve()
    target = parent / "training_input"
    source = Path(frame["source_dir"]).resolve()
    if source.is_relative_to(target) or (target.is_relative_to(source) and target.relative_to(source).parts[0] != "abu_training"):
        raise AbuCamValidationError("Training output must be outside the original frame folder.")
    requested = str(downscale).lower().strip()
    if requested in {"original", "native", "1", "none"}:
        size_limit, divisor = None, 1
    elif requested in {"2", "4", "8"}:
        size_limit, divisor = None, int(requested)
    elif requested in {"1k", "2k", "4k"}:
        size_limit, divisor = {"1k": 1024, "2k": 1920, "4k": 3840}[requested], 1
    else:
        raise AbuCamValidationError("Choose native resolution, a 1/2/4/8 factor, or 1k/2k/4k.")
    prepared_fingerprint = _fingerprint({"source": frame["fingerprint"], "downscale": requested})
    marker = target / "abucam_prepared.json"
    if target.exists():
        if marker.is_file():
            previous = _json(marker)
            if previous.get("fingerprint") == prepared_fingerprint:
                if previous.get("images_dematerialized_to_shortcuts"):
                    rematerialize_training_input_images(target, frame["cameras"])
                for relative, digest in previous.get("files", {}).items():
                    stored = _within(target / relative, target)
                    if not stored.is_file() or _digest_file(stored) != digest:
                        raise AbuCamValidationError("Prepared training input changed. Choose a new output folder.")
                return str(target)
        raise AbuCamValidationError("Prepared frame output already exists for different source data. Choose a new output folder.")
    parent.mkdir(parents=True, exist_ok=True)
    pending = parent / f".training_input_{os.getpid()}.pending"
    if pending.exists():
        raise AbuCamValidationError(f"An unfinished preparation exists: {pending}. Choose a new output or inspect it first.")
    pending.mkdir()
    try:
        images = pending / "images"
        images.mkdir()
        prepared_cameras = []
        for source_camera in frame["cameras"]:
            camera = dict(source_camera)
            ratio = min(1.0, size_limit / max(camera["w"], camera["h"])) if size_limit else 1 / divisor
            width, height = max(1, round(camera["w"] * ratio)), max(1, round(camera["h"] * ratio))
            rx, ry = width / camera["w"], height / camera["h"]
            camera.update(w=width, h=height, fx=camera["fx"] * rx, fy=camera["fy"] * ry,
                          cx=camera["cx"] * rx, cy=camera["cy"] * ry)
            if (width, height) == (source_camera["w"], source_camera["h"]):
                dst_image = images / camera["image_name"]
                try:
                    if dst_image.exists():
                        dst_image.unlink()
                    os.link(camera["image_path"], dst_image)
                except OSError:
                    shutil.copy2(camera["image_path"], dst_image)
            else:
                with Image.open(camera["image_path"]) as image:
                    image.resize((width, height), Image.Resampling.LANCZOS).save(images / camera["image_name"])
            prepared_cameras.append(camera)
        shutil.copy2(frame["cloud_path"], pending / "points3D.ply")
        from abu_m54 import read_ply_geometry
        points, colors, count = read_ply_geometry(frame["cloud_path"], limit=20_000_000)
        if count != frame["point_count"] or len(points) != count:
            raise AbuCamValidationError("Seed cloud contains invalid or truncated geometry.")
        _write_colmap(pending / "sparse" / "0", prepared_cameras, points, colors)
        transforms = {"camera_model": "OPENCV", "camera_convention": "opengl",
            "coordinate_frame": frame["coordinate_frame"], "ply_file_path": "points3D.ply",
            "applied_scale": 1.0,
            "frames": [{"file_path": f"images/{camera['image_name']}",
                "camera_id": camera["camera_id"], "camera_name": camera["name"],
                "w": camera["w"], "h": camera["h"], "fl_x": camera["fx"], "fl_y": camera["fy"],
                "cx": camera["cx"], "cy": camera["cy"], "k1": 0.0, "k2": 0.0, "p1": 0.0, "p2": 0.0,
                "transform_matrix": camera["transform_matrix"]} for camera in prepared_cameras]}
        (pending / "transforms.json").write_text(json.dumps(transforms, indent=2), encoding="utf-8")
        prepared = {"schema": SCHEMA, "source_type": "abucam_calibrated", "frame_id": frame["id"],
            "fingerprint": prepared_fingerprint, "source_fingerprint": frame["fingerprint"], "downscale": requested,
            "source_dir": str(source), "source_cloud": frame["cloud_path"],
            "image_count": len(frame["cameras"]), "point_count": count, "camera_convention": "opengl",
            "coordinate_frame": frame["coordinate_frame"], "pose_estimation": False, "world_scale": 1.0}
        prepared["files"] = {str(path.relative_to(pending)).replace("\\", "/"): _digest_file(path)
                             for path in pending.rglob("*") if path.is_file()}
        (pending / "abucam_prepared.json").write_text(json.dumps(prepared, indent=2), encoding="utf-8")
        pending.rename(target)
    except Exception:
        # Only this function's private, verified child folder is ever removed.
        if pending.is_relative_to(parent) and pending.parent == parent:
            shutil.rmtree(pending, ignore_errors=True)
        raise
    return str(target)


def rematerialize_training_input_images(prepared_dir, cameras):
    """Restore temporary hardlinked/copied PNGs in training_input/images before an engine run."""
    target = Path(prepared_dir).resolve()
    images_dir = target / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for lnk in images_dir.glob("*.lnk"):
        lnk.unlink(missing_ok=True)
    for cam in cameras:
        src = Path(cam["image_path"]).resolve()
        dst = images_dir / cam["image_name"]
        if not dst.is_file() and src.is_file():
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)


def dematerialize_training_input_images(prepared_dir, cameras):
    """Replace duplicate PNG files in training_input/images with 1 KB Windows .lnk shortcuts after training."""
    if os.name != "nt" or not cameras:
        return
    target = Path(prepared_dir).resolve()
    images_dir = target / "images"
    marker = target / "abucam_prepared.json"
    if not images_dir.is_dir():
        return
    canonical_parent = None
    converted = 0
    for cam in cameras:
        src = Path(cam["image_path"]).resolve()
        dst = images_dir / cam["image_name"]
        if not src.is_file() or str(src) == str(dst):
            continue
        canonical_parent = src.parent
        lnk_path = images_dir / (cam["image_name"] + ".lnk")
        if create_windows_shortcut(lnk_path, src, f"Shortcut to {src}"):
            dst.unlink(missing_ok=True)
            converted += 1
    if canonical_parent is not None:
        create_windows_shortcut(
            images_dir / "Open_Rendered_Images_Folder.lnk",
            canonical_parent,
            f"Open canonical rendered images ({canonical_parent})",
        )
    if converted > 0 and marker.is_file():
        try:
            doc = _json(marker)
            doc["images_dematerialized_to_shortcuts"] = True
            marker.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        except Exception:
            pass

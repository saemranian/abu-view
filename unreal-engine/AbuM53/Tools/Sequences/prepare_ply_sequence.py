"""Prepare an independent PLY sequence without changing its Gaussian data.

Python standard library only. Source files are opened read-only. The output must
be a new directory outside Git and outside the source directory. Copies are the
default; --hardlink explicitly permits shared NTFS file contents, with a copy
fallback when hard links are unavailable. Never edit linked frame contents.

This is manifest preparation, not a 4D model conversion or a stable-ID claim.
Sampling describes source positions; UE decoding validates the complete data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import time

GPU_BYTES_PER_SPLAT = 256
DEFAULT_IMPORT_BYTES = 1024 ** 3
SCALARS = {"char": "b", "int8": "b", "uchar": "B", "uint8": "B",
           "short": "h", "int16": "h", "ushort": "H", "uint16": "H",
           "int": "i", "int32": "i", "uint": "I", "uint32": "I",
           "float": "f", "float32": "f", "double": "d", "float64": "d"}


def natural_key(path: Path):
    return [(1, int(item)) if item.isdigit() else (0, item.casefold())
            for item in re.split(r"(\d+)", path.name)]


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def inspect_ply(path: Path, samples: int = 4096):
    """Validate a fixed-width binary vertex PLY and inspect bounded sample rows."""
    before = path.stat()
    header = bytearray()
    properties = []
    count = None
    encoding = None
    current_element = None
    with path.open("rb") as stream:
        while len(header) < 1024 * 1024:
            line = stream.readline(8193)
            if not line or len(line) > 8192:
                raise ValueError(f"Invalid or oversized PLY header: {path.name}")
            header.extend(line)
            try:
                words = line.decode("ascii").strip().split()
            except UnicodeDecodeError as exc:
                raise ValueError(f"PLY header must be ASCII: {path.name}") from exc
            if len(header) == len(line) and words != ["ply"]:
                raise ValueError(f"Not a PLY: {path.name}")
            if not words or words[0] in ("comment", "obj_info"):
                continue
            if words[0] == "format":
                if len(words) != 3 or words[2] != "1.0":
                    raise ValueError("Only PLY format version 1.0 is supported")
                encoding = words[1]
            elif words[0] == "element":
                if len(words) != 3 or words[1] != "vertex" or count is not None:
                    raise ValueError("Preparation requires exactly one vertex element")
                current_element = words[1]
                count = int(words[2])
                if not 0 < count <= 2_147_483_647:
                    raise ValueError("Vertex count is outside supported bounds")
            elif words[0] == "property":
                if current_element != "vertex" or len(words) != 3 or words[1] not in SCALARS:
                    raise ValueError("Preparation requires fixed-width scalar vertex properties")
                if words[2] in [item[1] for item in properties]:
                    raise ValueError("Duplicate PLY property")
                properties.append((words[1], words[2]))
            elif words == ["end_header"]:
                break
        else:
            raise ValueError("PLY header exceeded 1 MiB")
        if encoding not in ("binary_little_endian", "binary_big_endian") or count is None:
            raise ValueError("Preparation requires a binary PLY with vertex count")
        names = [item[1] for item in properties]
        required = ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
                    "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
        if any(name not in names for name in required):
            raise ValueError("PLY is missing standard Gaussian shape, opacity or color properties")
        row = struct.Struct(("<" if encoding == "binary_little_endian" else ">") +
                            "".join(SCALARS[kind] for kind, _ in properties))
        expected = len(header) + row.size * count
        if before.st_size != expected:
            raise ValueError(f"PLY payload size mismatch in {path.name}: {before.st_size} != {expected}")
        n = min(samples, count)
        indices = sorted({int(i * (count - 1) / max(1, n - 1)) for i in range(n)})
        xyz = []
        digest = hashlib.sha256()
        for index in indices:
            stream.seek(len(header) + index * row.size)
            raw = stream.read(row.size)
            if len(raw) != row.size:
                raise ValueError("PLY changed while sampling")
            values = row.unpack(raw)
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"Non-finite scalar in sampled row {index} of {path.name}")
            digest.update(raw)
            xyz.append([values[names.index(axis)] for axis in ("x", "y", "z")])
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed while being inspected")
    rest = sorted(int(name[7:]) for name in names if re.fullmatch(r"f_rest_\d+", name))
    degree = {0: 0, 9: 1, 24: 2, 45: 3}.get(len(rest))
    if degree is None or rest != list(range(len(rest))):
        raise ValueError("SH properties must be contiguous and describe SH0, SH1, SH2 or SH3")
    record = {
        "file": path.name, "source_path": str(path.resolve()), "source_bytes": before.st_size,
        "source_mtime_ns": before.st_mtime_ns, "header_bytes": len(header),
        "header_sha256": hashlib.sha256(header).hexdigest(), "format": encoding,
        "vertex_count": count, "bytes_per_vertex": row.size,
        "properties": [{"type": kind, "name": name} for kind, name in properties],
        "sh_degree": degree, "decoded_point_bytes": count * GPU_BYTES_PER_SPLAT,
        "has_explicit_stable_id": any(name in names for name in ("id", "stable_id")),
        "sample_count": len(xyz), "sample_rows_sha256": digest.hexdigest(),
        "sample_all_scalars_finite": True,
        "sample_bounds_min": [min(p[axis] for p in xyz) for axis in range(3)],
        "sample_bounds_max": [max(p[axis] for p in xyz) for axis in range(3)],
        "sample_position_percentiles": {
            label: [percentile([p[axis] for p in xyz], q) for axis in range(3)]
            for label, q in (("p01", .01), ("p50", .5), ("p99", .99))},
        "sampling_note": "Evenly spaced rows; bounds are sampled, not full-file bounds. No rows are removed.",
    }
    return record, xyz


def _validate_output(source: Path, output: Path):
    if output == source or source in output.parents or output in source.parents:
        raise ValueError("Output must be outside the source directory and its ancestors")
    if output.exists():
        raise ValueError("Output must be a new directory; existing content is never replaced")
    if any((parent / ".git").exists() for parent in (output, *output.parents)):
        raise ValueError("Private frame output must be outside Git repositories")


def prepare(source: Path, output: Path, fps: float, hardlink: bool = False,
            samples: int = 4096, coordinate_frame: str = "source_xyz"):
    if not math.isfinite(fps) or not 0 < fps <= 10000:
        raise ValueError("fps must be finite and in (0, 10000]")
    if not 1 <= samples <= 65536:
        raise ValueError("samples must be in [1, 65536]")
    source = source.resolve(strict=True)
    output = output.resolve()
    if not source.is_dir():
        raise ValueError("Source must be a directory")
    _validate_output(source, output)
    paths = sorted((p for p in source.iterdir() if p.is_file() and p.suffix.lower() == ".ply"),
                   key=natural_key)
    if not 1 <= len(paths) <= 100000:
        raise ValueError("Sequence requires 1 to 100000 PLY files")
    if len({p.name.casefold() for p in paths}) != len(paths):
        raise ValueError("Frame names collide on case-insensitive file systems")
    started = time.perf_counter()
    records = []
    previous = None
    for path in paths:
        record, positions = inspect_ply(path, samples)
        if previous is not None and len(previous) == len(positions):
            distances = [math.dist(a, b) for a, b in zip(previous, positions)]
            record["same_row_position_change_from_previous"] = {
                "changed_sample_rows": sum(distance != 0 for distance in distances),
                "median_distance": percentile(distances, .5),
                "note": "Row differences do not establish stable point correspondences."}
        records.append(record)
        previous = positions
    total = sum(record["decoded_point_bytes"] for record in records)
    largest = max(record["decoded_point_bytes"] for record in records)
    # The component reserves capacity for current, next and held fallback frames.
    minimum_cache = max(16, math.ceil(3 * largest / (1024 ** 2)))
    recommended_cache = min(8192, max(minimum_cache, math.ceil(total / (1024 ** 2))))
    cache_step = 1024 if recommended_cache >= 1024 else 256
    recommended_cache = min(8192, math.ceil(recommended_cache / cache_step) * cache_step)
    if minimum_cache > 8192:
        raise ValueError("A frame exceeds the current 8192 MiB streaming-cache limit")
    output.mkdir(parents=True)
    frame_directory = output / "frames"
    frame_directory.mkdir()
    for path, record in zip(paths, records):
        destination = frame_directory / path.name
        storage = "copy"
        if hardlink and not path.is_symlink():
            try:
                os.link(path, destination)
                storage = "hardlink"
            except OSError as exc:
                record["hardlink_fallback_reason"] = str(exc)
        if storage == "copy":
            with path.open("rb") as origin, destination.open("xb") as target:
                shutil.copyfileobj(origin, target, length=8 * 1024 * 1024)
            shutil.copystat(path, destination)
        current = path.stat()
        if (current.st_size, current.st_mtime_ns) != (record["source_bytes"], record["source_mtime_ns"]):
            raise ValueError("Source changed during preparation; partial output retained for inspection")
        if destination.stat().st_size != record["source_bytes"]:
            raise ValueError("Prepared frame size differs from source")
        record["prepared_path"] = str(destination)
        record["prepared_storage"] = storage
        record["same_file_as_source"] = os.path.samefile(path, destination)
    manifest = {
        "schema": 1, "sequence_type": "independent_3dgs_frames", "stable_ids": False,
        "storage": "external" if total > DEFAULT_IMPORT_BYTES else "embedded",
        "fps": fps, "coordinate_frame": coordinate_frame,
        "frames": [{"file": "frames/" + p.name, "time_seconds": i / fps} for i, p in enumerate(paths)],
        "abu_m53_preparation": {
            "fps_source": "explicit operator assumption; no timing metadata in PLY",
            "recommended_loading": "external_stream" if total > DEFAULT_IMPORT_BYTES else "embedded_or_external_stream",
            "recommended_streaming_cache_mib": recommended_cache,
            "quality": "All original binary payloads and SH coefficients retained; no interpolation or reduction",
        },
    }
    manifest_path = output / "sequence.am53seq"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    report = {
        "schema": 1, "manifest": str(manifest_path), "frame_count": len(paths), "frames": records,
        "fps": fps, "fps_is_assumption": True, "coordinate_frame": coordinate_frame,
        "duration_seconds": len(paths) / fps, "stable_ids_claimed": False,
        "total_source_bytes": sum(record["source_bytes"] for record in records),
        "total_decoded_point_bytes": total, "default_embedded_import_limit_bytes": DEFAULT_IMPORT_BYTES,
        "fits_default_embedded_import": total <= DEFAULT_IMPORT_BYTES,
        "minimum_cache_for_largest_frame_mib": minimum_cache,
        "recommended_streaming_cache_mib": recommended_cache,
        "storage_is_lossless": True, "source_files_opened_read_only": True,
        "hardlinks_explicitly_requested": hardlink,
        "hardlink_note": "Hardlinks share source contents. Do not modify either file. No read-only attribute is applied because it would change the source.",
        "external_files_must_remain_available": True, "external_files_automatically_cooked": False,
        "preparation_wall_seconds": time.perf_counter() - started,
    }
    (output / "sequence-preparation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fps", type=float, required=True, help="Explicit playback assumption; PLY has no timing metadata")
    parser.add_argument("--hardlink", action="store_true", help="Permit shared source-file contents; fallback to copying")
    parser.add_argument("--samples", type=int, default=4096)
    parser.add_argument("--coordinate-frame", choices=("source_xyz", "right_up_back"), default="source_xyz")
    args = parser.parse_args()
    report = prepare(args.source, args.output, args.fps, args.hardlink, args.samples, args.coordinate_frame)
    print(json.dumps({key: report[key] for key in ("manifest", "frame_count", "total_source_bytes",
          "total_decoded_point_bytes", "fits_default_embedded_import", "recommended_streaming_cache_mib",
          "preparation_wall_seconds")}, indent=2))


if __name__ == "__main__":
    main()

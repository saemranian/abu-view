#!/usr/bin/env python3
"""Generate original, deterministic Abu M53 Gaussian fixtures. Python 3.9+."""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import math
from pathlib import Path
import struct

SH_C0 = 1.0 / math.sqrt(4.0 * math.pi)


def cloud(count: int, phase: float = 0.0):
    """A colored anisotropic shell in UE axes, measured in meters."""
    points = []
    for index in range(count):
        z = 1.0 - 2.0 * (index + 0.5) / count
        radial = math.sqrt(max(0.0, 1.0 - z * z))
        angle = index * (math.pi * (3.0 - math.sqrt(5.0)))
        motion = 0.12 * math.sin(phase) * (1.0 - z * z)
        x = radial * math.cos(angle) + motion
        y = radial * math.sin(angle)
        position = (x, y, z * (1.0 + 0.08 * math.sin(phase)))
        hue = (index * 0.6180339887498949) % 1.0
        rgb = colorsys.hsv_to_rgb(hue, 0.68, 0.85)
        half = 0.5 * (angle + 0.2 * math.sin(phase))
        # Common Graphdeco PLY stores a quaternion in w,x,y,z order.
        quaternion_wxyz = (math.cos(half), 0.0, 0.0, math.sin(half))
        scale = (0.020, 0.034, 0.046)
        sh_dc = tuple((component - 0.5) / SH_C0 for component in rgb)
        # 15 non-DC coefficients per channel, channel-major PLY layout.
        sh_rest = [0.0] * 45
        sh_rest[0] = 0.08
        sh_rest[15 + 1] = -0.06
        sh_rest[30 + 2] = 0.04
        points.append((position, scale, quaternion_wxyz, rgb, sh_dc, sh_rest))
    return points


def ply_header(count: int, binary: bool = False) -> bytes:
    fields = [
        "ply", "format binary_little_endian 1.0" if binary else "format ascii 1.0",
        "comment Abu M53 original synthetic fixture; Apache-2.0",
        "comment coordinate_frame ue_x_forward_z_up_meters",
        f"element vertex {count}",
    ]
    fields.extend(f"property float {name}" for name in ("x", "y", "z"))
    fields.extend(f"property float f_dc_{i}" for i in range(3))
    fields.extend(f"property float f_rest_{i}" for i in range(45))
    fields.append("property float opacity")
    fields.extend(f"property float scale_{i}" for i in range(3))
    fields.extend(f"property float rot_{i}" for i in range(4))
    fields.append("end_header")
    return ("\n".join(fields) + "\n").encode("ascii")


def write_ply(path: Path, points, binary: bool = False) -> None:
    with path.open("wb") as stream:
        stream.write(ply_header(len(points), binary))
        for position, scale, quaternion, _rgb, dc, rest in points:
            values = (*position, *dc, *rest, math.log(0.85 / 0.15),
                      *(math.log(v) for v in scale), *quaternion)
            if binary:
                stream.write(struct.pack("<59f", *values))
            else:
                stream.write((" ".join(f"{v:.9g}" for v in values) + "\n").encode("ascii"))


def write_splat(path: Path, points) -> None:
    with path.open("wb") as stream:
        for position, scale, quaternion, rgb, _dc, _rest in points:
            rgba = [round(v * 255.0) for v in rgb] + [round(0.85 * 255.0)]
            q = [min(255, max(0, round(v * 128.0 + 128.0))) for v in quaternion]
            stream.write(struct.pack("<6f8B", *position, *scale, *rgba, *q))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[2] / "Tests" / "Fixtures")
    parser.add_argument("--count", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.count <= 20_000_000:
        parser.error("count must be between 1 and 20,000,000")
    args.output.mkdir(parents=True, exist_ok=True)
    frames = []
    for frame in range(3):
        name = f"shell_{frame:04d}.ply"
        points = cloud(args.count, frame * math.pi / 2.0)
        write_ply(args.output / name, points)
        frames.append({"time_seconds": frame / 30.0, "file": name})
    static = cloud(args.count)
    write_ply(args.output / "shell_binary.ply", static, binary=True)
    write_splat(args.output / "shell.splat", static)
    sequence = {
        "schema": 1,
        "sequence_type": "independent_3dgs_frames",
        "temporal_optimization": False,
        "coordinate_frame": "ue_x_forward_z_up_meters",
        "fps": 30,
        "frames": frames,
    }
    (args.output / "shell.am53seq").write_text(json.dumps(sequence, indent=2) + "\n", encoding="utf-8")
    source_names = [f"shell_{i:04d}.ply" for i in range(3)] + [
        "shell_binary.ply", "shell.splat", "shell.am53seq"]
    manifest = {
        "generator": "Tools/QA/generate_fixtures.py",
        "generator_schema": 1,
        "origin": "Original analytic Gaussian data; no photographs, trained weights or third-party assets.",
        "license": "Apache-2.0",
        "coordinate_frame": "UE X-forward, Y-right, Z-up; position and scale in meters",
        "splats_per_frame": args.count,
        "sh_degree_ply": 3,
        "sh_degree_splat": 0,
        "files": [],
    }
    for name in source_names:
        data = (args.output / name).read_bytes()
        manifest["files"].append({"path": name, "bytes": len(data),
                                  "sha256": hashlib.sha256(data).hexdigest()})
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "count": args.count,
                      "generated_files": len(source_names)}, indent=2))


if __name__ == "__main__":
    main()

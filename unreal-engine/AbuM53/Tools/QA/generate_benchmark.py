#!/usr/bin/env python3
"""Stream one original binary SH3 Gaussian PLY for an explicitly synthetic benchmark."""
from __future__ import annotations
import argparse
import colorsys
import hashlib
import json
import math
from pathlib import Path
import struct
from generate_fixtures import ply_header, SH_C0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Directory outside the published fixtures")
    parser.add_argument("--count", type=int, default=1_000_000)
    args = parser.parse_args()
    if not 1 <= args.count <= 20_000_000:
        parser.error("count must be 1 through 20,000,000")
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / f"shell_{args.count}.ply"
    digest = hashlib.sha256()
    packer = struct.Struct("<59f")
    scale_factor = math.sqrt(1000.0 / args.count)
    log_scale = tuple(math.log(value * scale_factor) for value in (0.020, 0.034, 0.046))
    log_opacity = math.log(0.85 / 0.15)
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    sh_rest = [0.0] * 45
    sh_rest[0], sh_rest[16], sh_rest[32] = 0.08, -0.06, 0.04
    with path.open("wb") as stream:
        header = ply_header(args.count, True)
        stream.write(header)
        digest.update(header)
        buffer = bytearray()
        for index in range(args.count):
            z = 1.0 - 2.0 * (index + 0.5) / args.count
            radial = math.sqrt(max(0.0, 1.0 - z * z))
            angle = index * golden_angle
            position = (radial * math.cos(angle), radial * math.sin(angle), z)
            rgb = colorsys.hsv_to_rgb((index * 0.6180339887498949) % 1.0, 0.68, 0.85)
            dc = tuple((value - 0.5) / SH_C0 for value in rgb)
            quaternion = (math.cos(0.5 * angle), 0.0, 0.0, math.sin(0.5 * angle))
            buffer.extend(packer.pack(*position, *dc, *sh_rest, log_opacity, *log_scale, *quaternion))
            if len(buffer) >= packer.size * 4096:
                stream.write(buffer)
                digest.update(buffer)
                buffer.clear()
        if buffer:
            stream.write(buffer)
            digest.update(buffer)
    report = {"path": str(path.resolve()), "splats": args.count, "bytes": path.stat().st_size,
              "sha256": digest.hexdigest(), "sh_degree": 3, "format": "binary_little_endian_ply",
              "source_units": "meters, UE X-forward Y-right Z-up",
              "scale_multiplier_relative_to_1000_point_fixture": scale_factor,
              "license": "Apache-2.0", "origin": "Original analytic synthetic shell; no third-party assets",
              "limitation": "Footprints shrink with inverse square root of count. This is not a representative high-overlap real-scene benchmark."}
    path.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

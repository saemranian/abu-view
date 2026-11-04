#!/usr/bin/env python3
"""Measure captured RGB images without modifying them. Requires Pillow and NumPy."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image

NAMES = ("gpu_tiled", "gpu_quad", "gpu_overflow_probe", "cpu_assisted", "disabled", "cpu_software")
PAIRS = (("gpu_tiled", "gpu_quad"), ("gpu_tiled", "cpu_software"),
         ("gpu_quad", "cpu_assisted"), ("gpu_quad", "gpu_overflow_probe"))


def metrics(a, b):
    delta = np.abs(a.astype(np.int16) - b.astype(np.int16))
    difference = delta.astype(np.float64)
    foreground = np.any(a != 0, axis=2) | np.any(b != 0, axis=2)
    mse = float(np.mean(difference * difference))
    nonzero = delta[delta != 0]
    foreground_difference = difference[foreground]
    foreground_mse = float(np.mean(foreground_difference * foreground_difference)) if foreground_difference.size else 0.0
    return {
        "exact_pixels": bool(np.array_equal(a, b)),
        "mean_abs_channel_error_8bit": float(np.mean(difference)),
        "max_abs_channel_error_8bit": int(np.max(delta)),
        "max_nonzero_channel_error_8bit": int(np.max(nonzero)) if nonzero.size else 0,
        "mean_nonzero_channel_error_8bit": float(np.mean(nonzero)) if nonzero.size else 0.0,
        "rmse_8bit": math.sqrt(mse),
        "psnr_db": 10.0 * math.log10(255.0 * 255.0 / mse) if mse else None,
        "different_channels": int(np.count_nonzero(delta)),
        "different_pixels": int(np.count_nonzero(np.any(delta != 0, axis=2))),
        "total_pixels": int(a.shape[0] * a.shape[1]),
        "foreground_union_pixels": int(np.count_nonzero(foreground)),
        "foreground_mean_abs_channel_error_8bit": float(np.mean(foreground_difference)) if foreground_difference.size else 0.0,
        "foreground_psnr_db": 10.0 * math.log10(255.0 * 255.0 / foreground_mse) if foreground_mse else None,
        "psnr_null_meaning": "Identical image/region; PSNR is infinite.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    images, records = {}, []
    for name in NAMES:
        path = args.directory / ("backend_" + name + ".png")
        with Image.open(path) as image:
            if image.size != (1280, 720):
                raise ValueError(f"Unexpected dimensions for {path}: {image.size}")
            images[name] = np.asarray(image.convert("RGB"))
        records.append({"mode": name, "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    report = {"schema": 1, "width": 1280, "height": 720, "channels": "RGB",
              "pixel_space": "Captured 8-bit display/output RGB; no linearization; alpha excluded",
              "images": records, "comparisons": [],
              "disabled_nonzero_channels": int(np.count_nonzero(images["disabled"])),
              "disabled_max_channel_value": int(np.max(images["disabled"])),
              "limitations": "One fixed synthetic scene. These image metrics do not verify source fidelity, GPU overflow occurrence, general scene parity or performance."}
    for first, second in PAIRS:
        report["comparisons"].append({"first": first, "second": second, **metrics(images[first], images[second])})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output.resolve()), "comparisons": report["comparisons"],
                      "disabled_nonzero_channels": report["disabled_nonzero_channels"]}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

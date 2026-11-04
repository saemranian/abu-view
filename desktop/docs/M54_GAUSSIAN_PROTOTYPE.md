# Abu M54 native Gaussian prototype

Milestone 1 of the 3DGS/4DGS plan, qualified locally on 25 October 2026.
This is a Windows native GPU prototype, not completion of the whole roadmap.

Update v0.1.8.0: [PLY sequence playback](M54_PLY_SEQUENCE.md) adds exported-frame
animation, bounded GPU caching and temporal image/video rendering. The original
milestone's remaining-work list below is historical; arbitrary 4D checkpoints,
SPZ and per-frame LOD are still unsupported.

Update v0.1.7.9: bounded near-camera projection, stable positive-definite
Gaussian evaluation, and desktop render cameras/path/image/video export are
documented in [Render Studio](M54_RENDER_STUDIO.md). The measurements below
record the original v0.1.7.8 milestone; newer close-up evidence is in that guide.

## Opening and using it

Restart Abu M54 or Abu Align after updating. Open a conventional Gaussian PLY
through M54's normal Open > File command. Leave **3DGS GPU** checked. The footer
reports the full Gaussian count, SH degree, GPU processing milliseconds and
resident buffer bytes. These milliseconds exclude UI and presentation; they are
not an interaction-FPS promise. Existing orbit, pan, zoom, cameras, grids, pivots
and uniform model transforms remain shared with the host tools.

Uncheck the option for the point preview. A-only and B-only show full Gaussians
separately; A/B overlay deliberately uses labelled point previews until a shared
cross-layer sorting pass is implemented. Browser rendering remains a labelled
point preview. Missing GPU functions, invalid shaders or a budget excess produce
a logged, visible explanation and point fallback. Sources are never modified.

## Implementation and decision

The RTX 4090's existing WGL context exposes OpenGL 4.6, compute shaders, shader
storage buffers, instancing and GPU timestamps. This permits a useful native
prototype without a new binary runtime or upstream renderer source. Original
GLSL and a small ctypes binding submit work to the installed graphics driver.
Vulkan versus wgpu selection is still a later portability/scale decision; no
claim is made that those backends were implemented or benchmarked here.

- `abu_m54_gaussian.py`: bounded ASCII/binary little-endian PLY, immutable float64
  centers, linear scale, WXYZ quaternion, opacity and channel-major SH degrees 0-3.
- `abu_m54_splat_shaders.py`: covariance projection, real SH evaluation, visibility
  checks, GPU depth sorting and premultiplied alpha compositing.
- `abu_m54_splat_gpu.py`: persistent buffers, a hybrid shared-memory/global bitonic
  sorter, instanced quads, GPU timing queries, explicit budget and deterministic
  cleanup. No per-frame image or sort-index readback in the application.
- `abu_m54.py`: the single shared loader and transform authority. Only the legacy
  picking/preview arrays are sampled; the Gaussian asset keeps every source splat.
- `control_points_comparison.py`: complete uncompressed local NPZ handoff, bounded
  Gaussian archive/header validation and transform composition for comparison.
- `abu_m54_native.py`: the existing native host, checkbox, timing/status and fallback.
  Main, manual-control and standalone hosts use this same implementation.

World-to-display math is composed in float64 before sending rebased matrices to
the GPU. Source SH directions stay in object space; scale/rotation affect the
covariance through the full model-to-view matrix. Changing a model transform
does not reupload the Gaussian buffer. Unsupported transformed Gaussian export
is rejected before writing files, rather than discarding its appearance.

## Quality evidence

The benchmark compares GPU images to an independent NumPy float64 reference
using SciPy quaternion matrices and complex spherical harmonics. Seven cases
cover SH degrees 0, 1, 2 and 3, anisotropic splats, overlap, arbitrary rotations,
uniform model transforms and Earth-scale offsets. The fixed gate is PSNR >=45 dB
and RGB RMSE <=0.005. All passed; worst PSNR was 86.06 dB, worst RMSE about
0.000050 on RGBA32F 256 x 192 captures. This verifies the implemented rendering
equations; it is not a trained-scene perceptual or accuracy benchmark.

The implemented reference contract is center-depth back-to-front ordering,
0.3 pixel-squared covariance filtering, a 3-sigma elliptical footprint, opacity
capped at 0.99 and contributions below 1/255 discarded. This is not hierarchical
visibility sorting or training-aware Mip-Splatting. Near-plane crossing and
very large splats need further quality work; HDR/display color calibration and
special 2DGS/3DGUT rendering kernels are not claimed.

## Performance evidence

GPU: NVIDIA GeForce RTX 4090, 24 GiB class, driver 610.88 / OpenGL 4.6.
Synthetic anisotropic SH3 assets, 1920 x 1080, five warmup frames then 20 measured
moving-camera frames. Source-index checks verify every source Gaussian occurs
exactly once and the resulting GPU depth order is correct.

| Source splats | Offscreen median | p95 | FPS from median | Resident buffers |
| ---: | ---: | ---: | ---: | ---: |
| 100,000 | 0.815 ms | 1.003 ms | 1,227 | see local JSON |
| 1,000,000 | 10.793 ms | 12.700 ms | 92.65 | see local JSON |
| 5,000,000 | 14.060 ms | 14.977 ms | 71.13 | 1,587,108,864 bytes (1.48 GiB) |

These are synchronized offscreen wall times (including glFinish), excluding
asset creation/upload, display presentation, physical input and UI processing.
Fixed synthetic small-footprint distributions do not represent every trained
scene. GPU fill cost depends strongly on overlap, footprint and resolution.
Report whole-window measurements separately; do not promote these numbers as
guaranteed interactive FPS. Five-million-splat process RSS was about 2.97 GB.
Device-wide VRAM samples also include other apps and cannot isolate this viewer.

Actual visible compact M54 viewport, 1920 x 1080, the same SH3 source counts:

| Source splats | Native present median | p95 | FPS from measured median |
| ---: | ---: | ---: | ---: |
| 1,000,000 | 16.631 ms | 17.046 ms | 60.13 |
| 5,000,000 | 14.149 ms | 17.123 ms | 70.68 |

This second measurement includes the existing native draw, SwapBuffers,
glFinish and Tk idle work. WGL reported swap interval 1; compositor/driver
scheduling can decouple these calls from scanout, so these are not physical
display rates or input-latency measurements. Normal event-driven interaction
can differ. Native loading/creation/upload was approximately 1.65 s and 7.81 s
for these two synthetic assets respectively. The GPU allocation returned to
baseline on close; device VRAM varied with other applications. See the separate
local `host_report.json` for all conditions.

All rendered inputs and captures for qualification are synthetic. No client
dataset was uploaded, included in Git or used in public benchmark artifacts.
Detailed local results and captures are under ignored
`build/m54-gaussian-qualification/`.

## Limits and next phases

The per-viewport buffer budget is 2 GiB. Import guards bound count and arrays;
conversion and transfer temporarily require additional RAM. There is no LOD or
streaming yet. Separate viewports have separate buffers in this first prototype;
GPU sharing and a process-wide budget remain a following milestone. First upload
and command submission still use the host context/thread. Picking uses at most
50,000 point samples. Overlays are inspection aids rendered above the splats,
without Gaussian depth occlusion.

Windows native WGL is qualified here. Mac/Linux native presentation is not yet
implemented. Unsupported machines retain a bounded point preview; no full CPU
Gaussian renderer is claimed. GPU timestamps are collected without blocking
normal frames; benchmark readback/synchronization is test-only.

Remaining steps: qualify actual exported training dialects and complex scenes;
improve scheduling/upload/near-plane and visibility quality; evaluate portable
native backends; add SPZ and other codecs; shared budgets/streaming/LOD; AbuCam
sequence playback; named 4D model adapters; browser full Gaussian rendering;
and clean-machine cross-platform installer qualification. Do not advertise 4DGS,
SPZ, 100-million full-detail rendering or universal formats as implemented.

## Reproduction and distribution

Final local regression: 53 tests passed across `test_m54_gaussian`,
`test_m54_gaussian_integration`, `test_m54_realityscan_csv`, `test_abu_m54` and
`test_m54_objects`, with actual GPU tests enabled. Browser tests need local
loopback access; the restricted runner stalled in Python socketpair creation,
and passed outside that restriction. Viser emitted one nonfatal event-loop
ResourceWarning. All 123 core and 221 public manifest paths validated; a staged
core imported M54 and its renderer independently of the source working directory
and contained the scoped license. This is not a frozen-installer clean-machine
or macOS/Linux qualification.

Use the project's Python environment with NumPy, SciPy, Pillow, psutil and Tk.

```text
python -m unittest discover -s tests -p test_m54_gaussian.py -v
python -m unittest discover -s tests -p test_m54_gaussian_integration.py -v
python benchmark_m54_gaussian.py --output build/m54-gaussian-qualification
python benchmark_m54_gaussian.py --host-only --counts 1000000,5000000 --frames 20 --output build/m54-gaussian-qualification
```

Set `ABU_TEST_NATIVE_GPU=1` for tests that open an actual native context. Quality and
performance tools never open a client dataset. No upstream checkout is modified.
The new original files have the scoped Apache-2.0 grant in `licenses/`; existing
suite licenses remain. `M54_GAUSSIAN_LICENSE_REVIEW.md` describes the concrete
whole-app restrictions; this milestone does not provide legal clearance for all
existing engines or relicense retained VGGT code.

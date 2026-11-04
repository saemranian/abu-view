# Abu M54 close-up rendering and Render Studio

Implemented for v0.1.7.9, qualified locally on 25 October 2026. Restart the
application after updating; an already running Python window retains old code.

Update v0.1.8.0: **Animate loaded PLY sequence** adds changing source geometry to
image/video export, with a fixed camera or existing path. Source FPS determines
clip duration; output FPS determines sample-and-hold output frames. Animated
jobs read PLYs directly without large NPZ staging. See
[PLY sequence guide](M54_PLY_SEQUENCE.md). This supersedes the original milestone's
absence of exported-frame playback; arbitrary 4DGS checkpoints remain unsupported.

## Open Render Studio

Use **Render Studio** above the desktop viewport, **M54 tools > Render Studio ·
cameras & output**, or **Ctrl+R** while the viewport has keyboard focus. This
is part of the shared native viewer used by standalone M54, Abu Align and the
manual-control-point workspace. The browser remains a point-preview host and
does not offer native render export.

## Cameras and paths

1. Navigate to a useful viewpoint. In **Cameras**, choose **+ From current view**.
   This captures the actual world position, full orientation and vertical FOV.
2. Give it a name. Edit XYZ, rotation XYZ in degrees, or vertical FOV, and choose
   **Apply camera fields**. **Look through selected camera** previews that pose;
   double-clicking the list does the same. **Update from view** captures a new
   viewport pose into the selected saved camera.
3. For an animation, open **Camera path** and capture the first pose at time
   **0**. Move to another view, enter its time in seconds and choose **+ Current
   view**, or use **+ Selected camera**. The last key's time sets the duration.
4. Scrub the timeline or **Play preview**. **Linear** follows straight position
   segments. **Smooth** uses time-aware cubic translation and may overshoot
   between keys; inspect the whole route. Both use shortest-arc quaternion
   rotation interpolation. FOV interpolates between keys.
5. Save cameras and path as a separate JSON project. Load it to continue later.
   It stores world-coordinate poses, not the model. The same scene coordinates
   and scale are needed when reusing it with another reconstruction.

Render cameras and keyframes are independent of imported reconstruction cameras.
Keyframes store pose snapshots: editing or deleting a saved camera does not
rewrite existing keys. Replace a key explicitly after changing its view. Gold
camera frustums and a path line appear while Render Studio is open; neither is
baked into exported images. Source cloud, splat and alignment files stay immutable.

## Render settings

| Setting | Practical use |
| --- | --- |
| Scene layer A / B | Export the opened scene or the transformed comparison. One selected layer is exported; a combined A/B splat render is not implemented. |
| PNG | Lossless still image from the selected saved camera, or the current view when no saved camera is selected. |
| JPEG | Smaller still image; quality controls compression. |
| Sequence | Numbered lossless PNG frames following the camera path. |
| MP4 | Render PNG frames, then encode H.264 video. The frames are retained. |
| Width / height | Output pixels; presets include HD, 4K and square. Export uses this aspect ratio, which can differ from the live viewport. |
| FPS | Temporal samples and playback rate. Higher FPS adds frames and work, not spatial detail. A 1-second path at 30 FPS produces 30 frames at t=0 through 29/30 seconds. |
| Antialiasing 1 / 2 | 2 renders twice the width and height and downsamples with Lanczos: four times as many pixels. Internal limit is 8192 pixels per edge and 32 megapixels. |
| Quality 1–100 | JPEG quality or video compression quality; larger values increase file size. PNG ignores it. This is not a Gaussian training-quality control. |
| Auto / NVENC / CPU | Video encoding only. Auto probes actual NVIDIA encoding, then falls back to CPU if unavailable or failed. Gaussian rendering stays on the GPU. |
| FFmpeg executable | Optional path to an already installed encoder. Otherwise the worker checks ABU_FFMPEG, PATH and documented local locations. Nothing is downloaded. |
| Near / far clip | Positive distances in scene units. Too large a near clip removes close surfaces; too small a far clip removes distant geometry. These values do not repair a poorly trained model. |
| Background | Solid RGB background for empty space. This release exports opaque 8-bit RGB images, not transparent/HDR/EXR output. |

Each render creates a unique output subfolder and a `render_report.json`. The
worker keeps the UI responsive, reports progress, checks cancellation between
operations, and writes completed images atomically. Cancel keeps completed
frames. Encoding failure keeps the PNG sequence and encoder logs. No existing
outputs or source files are overwritten by a render job. Camera-project Save
uses the normal explicit Save dialog and may replace the chosen project file.

The renderer uses a separate hidden Windows OpenGL context, the same Gaussian
shader and sorting implementation as the viewport, and a floating-point color
buffer for compositing. Near/far clipping and aspect ratio should match when
comparing output with a live viewport. No grid, camera, control, null or selection
overlays are included. Ordinary XYZ/RGB clouds currently export the points loaded
in the preview; Gaussian PLY assets export every loaded Gaussian, not only the
picking preview.

## Close-up bug and repair

The old perspective Jacobian used unbounded offscreen x/z and y/z. Near the eye
plane that can create a huge ellipse even when its mean is far outside the view.
The covariance determinant and expanded inverse quadratic also subtracted almost
equal float32 values for thin splats. A negative quadratic then increased opacity
instead of reducing it. This combination could cover the image with a flat haze.

The shared shader now:

- bounds the Jacobian's linearization to a 30% view guard band, retaining the
  actual projected center;
- computes the determinant using the cross-product/Lagrange identity and scaled
  vectors, including the pixel filter without subtractive cancellation;
- evaluates the inverse covariance as a sum of squares using inverse Cholesky
  factors, so a valid tail cannot acquire negative squared distance;
- clips bounding rectangles to the viewport while retaining actual pixel offsets.

No source Gaussian positions, sizes, rotations, opacity or SH values are altered.
No upstream repository or rasterizer source is modified or embedded.

## Local verification

RTX 4090, all 2,485,576 splats from a private local SH3 model, 1920×1080. Four
deterministic interior viewpoints were tested, not the exact unsaved screenshot
camera. GPU timings exclude load, UI, readback and presentation.

| Test view | Old GPU time | Corrected GPU time |
| --- | ---: | ---: |
| 1 | 43.39 ms | 5.88 ms |
| 2 | 45.89 ms | 4.70 ms |
| 3 | 48.76 ms | 4.52 ms |
| 4 | 48.43 ms | 9.30 ms |

At those views, drawable footprints exceeding 10,000 pixels in radius fell from
12,365–13,747 to 1–20. Nonpositive determinants fell from 50–73 to zero. The five
sampled pixel positions per view no longer had negative quadratic distances.
All OpenGL error checks passed. These are diagnostic improvements, not a
ground-truth perceptual benchmark or a desktop FPS guarantee. Private model,
images and logs were not added to Git or uploaded.

Regression tests cover extreme offscreen near-eye splats, 100,000:1 anisotropy,
the independent float64 SH0–3 image reference, full camera matrix/position/FOV
roundtrips, smooth-path continuity, validation, JSON roundtrips, actual GPU image
exports, supersampling, Earth-scale rebasing, CLI worker output, partial-sequence
cancellation, encoder fallback and actual NVENC/CPU MP4 decoding. A small retained
synthetic test rendered six 320×240 frames at 24 FPS with 2× supersampling and
verified encoding: NVENC 2.328 seconds including probing, CPU 0.750 seconds. That
tiny-job startup comparison is not a claim that CPU is faster for long videos.

The same production export worker also rendered the complete private model:
1920×1080 PNG in 3.375 seconds and a three-frame 1920×1080 MP4 at 30 FPS in
4.093 seconds using NVENC. These are end-to-end worker times including local
scene loading/upload and file output (plus encoder probing for MP4), not per-frame
render speeds. Decoding confirmed resolution, rate and all three frames. The
temporary 617.8 MB scene snapshot was removed after the check. Output files and
their local qualification report remain under the Git-ignored build directory.

Release verification passed **78 tests**, run in these groups with the vggt
Python environment, `PYTHONPATH=tests;.` and `ABU_TEST_NATIVE_GPU=1`:

```text
python -B -m unittest test_m54_closeup test_m54_gaussian test_m54_gaussian_integration test_m54_realityscan_csv -q
python -B -m unittest test_abu_m54 test_m54_objects -v
python -B -m unittest test_m54_cameras test_m54_render -q
```

The final group also used `ABU_TEST_VIDEO=1` and the existing local FFmpeg. An
initial combined run was interrupted after slow legacy Tk/Viser startup; the
separate legacy group passed all 28 tests in 45.5 seconds, with existing nonfatal
Viser event-loop resource warnings. The other groups passed 28 and 22 tests.
Both package allowlists validated (128 core files, 229 public files). Imports and
an actual image worker passed with an isolated copy of the approved core payload
and the source runtime dispatcher. This is a package-content/dispatch smoke test,
not a newly built or published installer.

GPU buffers remain resident across frames and are released with the export
context. At 1080p the color/depth target needs about 24 MiB; 2× supersampling
quadruples that. The private 2.49M-splat viewport uses about 753 MiB of Gaussian
buffers. Export creates its own GPU buffers, so rendering while the viewport is
open temporarily holds two copies. A 2 GiB Gaussian buffer limit per renderer
and bounded output dimensions remain enforced. Scene snapshot preparation also
needs local temporary disk space and RAM proportional to the complete model.

## Limits and provenance

This is Windows OpenGL 4.3+ native rendering with a working GPU driver. It does
not add a CPU Gaussian rasterizer, cross-platform native backend, 4DGS playback,
multi-layer splat compositing, depth of field, motion blur or ray-based sorting.
Center-depth sorting and first-order Gaussian projection still have limitations
when entering a Gaussian or viewing complex intersecting splats.

Postshot documents nonstandard color-space and antialiasing metadata. This
release does not guess the exact semantics of `postshot.anti_aliasing=1`; it does
not claim pixel-identical Postshot rendering. [Postshot export guide](https://activation.jawset.com/docs/d/Postshot%2BUser%2BGuide/Interface/Radiance%2BField%2BExport).
First-order projection limitations are also discussed in the
[3DGUT paper](https://openaccess.thecvf.com/content/CVPR2025/papers/Wu_3DGUT_Enabling_Distorted_Cameras_and_Secondary_Rays_in_Gaussian_Splatting_CVPR_2025_paper.pdf).
The code here implements its own bounded first-order method, not that renderer.

New original camera, UI, offscreen and worker modules have scoped Apache-2.0
headers and the repository's accompanying license/notice. The encoder is a
separate existing local FFmpeg executable; it is neither downloaded nor bundled.
FFmpeg builds have different license implications depending on enabled codecs;
review the exact binary before adding one to a future installer. See the
[FFmpeg legal page](https://ffmpeg.org/legal.html) and
`M54_GAUSSIAN_LICENSE_REVIEW.md`. This addition does not clear the pre-existing
restricted engines or relicense the entire application.

## Changed active files

- `abu_m54_splat_shaders.py`, `benchmark_m54_gaussian.py`: projection fix and
  independent reference contract.
- `abu_m54_native.py`, `abu_m54_tools.py`, `abu_m54_fileinfo.py`: shared camera
  hooks, Render Studio entry points/overlays and full-asset versus preview labels.
- `abu_m54_cameras.py`, `abu_m54_render_ui.py`, `abu_m54_offscreen.py`,
  `abu_m54_render.py`: camera/path model, UI, GPU target and export worker.
- `tests/test_m54_closeup.py`, `tests/test_m54_cameras.py`, `tests/test_m54_render.py`.
- `docs/ABU_M54.md`, `docs/ABU_M54_GUIDE.md`, `docs/M54_GAUSSIAN_PROTOTYPE.md`,
  this document and `docs/M54_GAUSSIAN_LICENSE_REVIEW.md`.
- `licenses/M54-GAUSSIAN-NOTICE.txt`, `installer/core-files.json`,
  `installer/public-files.json`, walkthrough copies, version headers/launchers,
  synchronized `Abu_Align/` files and version backup snapshots.

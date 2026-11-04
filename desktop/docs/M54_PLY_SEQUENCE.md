# Abu M54 PLY sequence playback · v0.1.8.0

M54 plays independently exported Gaussian PLY frames and renders changing
geometry to images/video. This does not import arbitrary research 4DGS
deformation checkpoints or invent motion between unmatched splats.

## Quick start

1. Restart M54. Choose **Open → PLY sequence…**, the **PLY sequence…** toolbar
   button, or **M54 tools → PLY sequence · animation…** in an embedded viewer.
2. Select any numbered frame, for example `frame_2148.ply`. Matching siblings
   such as `frame_2149.ply` and `frame_2150.ply` are ordered numerically.
3. The first image opens while upcoming frames preload. For a short clip, wait
   for **3/3 GPU frames** in the timeline status before starting smooth looping.
4. Set **Source FPS** to the capture/export rate. The initial **30** is an editable
   assumption; PLY supplies no standard frame-rate metadata.
5. Press **Play**. Use **Loop**, the timeline, **‹ / ›**, or **⏮** to navigate.
   With the viewport focused, **Space** plays/pauses and **Left/Right** step frames.
6. **Speed 0.1, 0.25 or 0.5** slows preview. Three frames at 30 FPS last only
   0.1 seconds. Preview speed does not change export timing.

Orbit, zoom, pan and model transforms remain fixed in world coordinates across
frames. **Close sequence** releases caches and retains the current static model.
Opening an ordinary file also closes playback. File details refresh when paused;
the timeline names the displayed frame. Source files are never changed.

## Source requirements and timing

- 2–10,000 numbered conventional Gaussian PLYs, binary little-endian or ASCII,
  using the existing M54 parser: XYZ, log scales, opacity logits, WXYZ rotation
  and spherical harmonics degree 0–3. Different frame splat counts are allowed.
- Selecting a file restricts discovery to its prefix/suffix family. A folder with
  multiple numbered families requires selecting a particular frame.
- Duplicate numeric IDs are rejected. Gaps are packed: every existing file is one
  consecutive displayed frame, without inserted missing frames.
- Frames use sample-and-hold. Equal vertex counts do not establish splat
  correspondence. No interpolation of unrelated splat rows is performed.
- File sizes and modification times are recorded and checked when loading and
  exporting. Reopen after changing source files. Cached frames remain the loaded
  immutable snapshot. These signatures are consistency checks, not hashes.
- Ordinary XYZ/RGB clouds remain available through the normal static importer.

## Memory and responsiveness

A background CPU worker decodes and prepares frames using `abu_m54.load_scene`;
it never calls Tk or OpenGL. The UI uploads at most 16 MiB per scheduled step.
Incomplete uploads cannot draw. The shared Gaussian renderer retains full SH,
covariance, opacity and GPU sorting for every frame.

**GPU cache Auto** targets up to 4 GiB, bounded to 60% of available GPU memory
when NVIDIA's NVX memory extension is available. Other hardware uses a conservative
1 GiB cap. Explicit 1/2/4/8 GiB choices also respect detected headroom. The existing
**2 GiB per-frame** limit remains; cache capacity does not make an individually
oversized frame supported. Other viewer windows have separate allocations.

The CPU cache retains up to 6 GiB or one quarter of available RAM, whichever is
smaller, with a small minimum. Its figure covers decoded arrays, upload copies
and sampled geometry. Decoder temporaries, driver allocations, Python overhead
and assets referenced by GPU renderers are additional memory. It is not total
process RAM. A frame exceeding the CPU budget fails without reducing quality.

LRU eviction protects the displayed GPU frame during prefetch. A one-frame cache
releases that protection when switching and buffers the next frame. Seeks discard
stale loading results and cancel unrelated staged uploads. The playback clock
holds during buffering. When drawing cannot keep up, display frames can be skipped
to preserve time; video export still renders every requested output frame.
Warmed short loops have no repeated loads/uploads.

Status reports resident frames, GPU bytes, CPU cache bytes and completed viewport
frame-change cadence. GPU milliseconds and playback FPS are distinct. Full
temporal playback requires **native Windows OpenGL 4.3+**; browser view remains a
static sampled frame. Per-frame LOD, SPZ and research checkpoints remain unsupported.

## Render changing geometry

In **Render Studio → Render & export**, leave **Animate loaded PLY sequence**
checked, select layer **A**, then **sequence** for PNG frames or **mp4** for video.

- No camera path is required: use a saved or current fixed camera. If a path
  exists it plays from time zero and holds its last pose when shorter than the
  source clip. The source sequence determines export duration.
- Source FPS controls duration; output FPS controls sampling. Three source frames
  at 30 FPS exported at 60 FPS use indices **0, 0, 1, 1, 2, 2**.
- Animated exports start at source frame zero and cover the full clip. Preview
  speed and scrub position do not trim or slow the export.
- PNG/JPEG stills use the current frame. Uncheck animation to export a camera
  path around the current static model. Comparison layer B remains static.
- Resolution, antialiasing, clipping, background and codec settings remain the
  shared Render Studio settings. MP4 invokes an existing local FFmpeg executable;
  Auto tries NVENC then CPU. Nothing is downloaded or bundled.

Animated jobs read PLY paths directly without multi-GB NPZ staging. Source
signatures are checked before/after loading. Cancellation keeps completed images.
Each job creates a separate output folder and report mapping output indices/times
to source names and splat counts.

## Local verification · 25 October 2026

RTX 4090; three frames of 3,000,000 SH3 Gaussians each. No source data or output
images were uploaded or committed.

| Measurement | Result |
|---|---:|
| Shared native test viewport | 1280 × 743 |
| All three frames preloaded | 18.32 s |
| 30 FPS target, six-second loop | 29.83 completed frame changes/s |
| 60 FPS target, six-second loop | 49.49 completed frame changes/s |
| 30 FPS at 0.25× speed | 7.33 completed frame changes/s |
| Repeated uploads in warmed playback | 0 |
| Three-frame GPU cache | 2,836,663,296 bytes (2.64 GiB) |
| CPU cache | 4,540,051,296 bytes (4.23 GiB) |
| Process working set after preloading | about 6.64 GiB |
| Camera matrix change across frames | 0 |
| OpenGL errors | 0 |
| Sequence GPU / CPU cache after closing | both zero bytes |
| Three-frame 1280 × 720 PNG + NVENC MP4 | 19.313 s total |
| Decoded video check | 3 frames, 30 FPS, 1280 × 720 |
| Export GPU buffers including framebuffer | 956,613,632 bytes |

This used the actual shared component in a transparent test window, with a fixed
world camera. Results do not guarantee 60 FPS, fullscreen/4K performance or equal
performance on long clips. Export timing includes loading, upload, PNG writing
and encoding. Adjacent frames differ numerically; this is not a ground-truth
image-quality evaluation. Removing redundant redraw delay improved the same
30-FPS test from 24.33 to 29.83 FPS.

Regression coverage includes discovery, invalid/mutated inputs, timing, bounded
prefetch, eviction, seeks/cancellation, upload completeness, GPU pixel differences,
cleanup, camera/transform invariance, looping/end behavior, source/output sampling,
fixed/moving cameras, worker lifecycle and video decoding.

111 distinct tests passed: the full M54 regression run passed 109 tests in
66.592 seconds; after adding two UI edge-case regressions, all six sequence UI
tests passed in 11.244 seconds. Existing browser tests emitted nonfatal Viser
event-loop resource warnings.

Packaging validation passed for all 132 core and 237 public manifest entries.
An isolated Python process imported the new modules from a staged core payload
and ran its allowlisted temporal export worker successfully for three synthetic
frames, without NPZ staging. This is a payload integration check, not a new
frozen-installer build or clean-machine qualification. No release was published.

Use project Python with `PYTHONPATH=tests;.`, `ABU_TEST_NATIVE_GPU=1`,
`ABU_TEST_VIDEO=1`:

```text
python -B -m unittest test_m54_sequence test_m54_sequence_gpu test_m54_sequence_ui test_m54_render_sequence
```

Private scalar reports (ignored by Git): `build/m54-skate-sequence-playback-final.json`
and `build/m54-sequence-export-private/qualification.json`.

## Architecture, licensing and changed files

`abu_m54_sequence.py` handles discovery, timing and CPU preparation using the
shared parser. `abu_m54_sequence_gpu.py` manages residency over `GaussianRenderer`.
`abu_m54_sequence_ui.py` drives the existing native navigator. App/tool hosts expose
this controller; export shares its frame contract, transforms and rendering math.

New modules/tests are original Apache-2.0 code, listed in the scoped Gaussian
notice. No upstream code was copied/modified and no new third-party runtime,
model or dataset is bundled. Existing host/dependency licenses remain applicable;
this addition does not relicense the whole suite.

Changed active files: three sequence modules, `abu_m54_splat_gpu.py`,
`abu_m54_native.py`, `abu_m54_app.py`, `abu_m54_tools.py`, `abu_m54_render.py`,
`abu_m54_render_ui.py`, four sequence test modules, both installer manifests,
the scoped notice, M54 architecture/help/prototype/render documents, version
headers, launchers, walkthrough copies, mirrors and version snapshots.

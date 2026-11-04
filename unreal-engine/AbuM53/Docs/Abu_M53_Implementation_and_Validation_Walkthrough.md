# Abu M53 — Implementation and Validation Walkthrough

Historical implementation session: 25 October 2026. First Git release: **v0.0.0.1**.

This walkthrough explains the work completed in the preceding implementation messages, the failures encountered, their corrections and the evidence obtained. It is a retrospective engineering record, not a claim that every item in the original production roadmap is finished. The prior working label was `0.1.0-dev`; the user-requested Git numbering starts at `v0.0.0.1` without changing or relabeling the old evidence.

## 1. Defined the implementation boundary

The requested plugin name is **Abu M53**. “4GDS” was clarified to mean animated 4D Gaussian Splatting. Windows PCs with NVIDIA, AMD or Intel GPUs were the intended target. The implementation uses Unreal rendering interfaces and original C++/HLSL rather than a CUDA-only renderer.

The research and architecture were saved in [ImplementationPlan.md](ImplementationPlan.md). The actual installed engine used for development was UE **5.8.2, CL 56702186**. The code lives in a dedicated plugin folder; synced project material under `sources/` was treated as read-only. Separate hosts under the containing workspace's `work/` directory were used for editor and packaged-game validation.

Animated Gaussian representations do not share one universal file format. The implemented animation paths are timestamped independent frames and explicitly validated stable-ID keyframes. Arbitrary neural checkpoints and native research-model inference are not implied by that support.

## 2. Built the portable data and CPU core

`Core/` supplies the parser, Gaussian representation, container and reference renderer independently of Unreal. The representation retains positions, anisotropic scale, quaternion orientation, opacity and real spherical harmonics through degree 3.

Implemented inputs include Gaussian ASCII and binary little-/big-endian PLY, 32-byte SPLAT, SPZ versions 1–4 and the original AM53 container. The importer handles Graphdeco-style activated/logarithmic fields and quaternion/SH layout conversions rather than treating every PLY as a Gaussian file. SPZ decoding covers gzip and Zstandard paths, preserves supported orientation/antialias metadata and rejects unsupported extensions explicitly.

AM53 provides checked headers, chunk indexing, CRCs and range reading. Range access alone is not a complete Unreal spatial streamer. `Tools/M53Convert/` exposes portable conversion functionality. The CPU renderer serves as a bounded reference and preview; it has contribution/count limits and explicit near-plane limitations.

Original fixtures were generated instead of bundling third-party scans. The final portable test run passed **113 checks**, with CTest **1/1** passing. Coverage includes malformed data, SPZ variants, container ranges/checksums, SH and antialias behavior.

A security review found a tiny PLY capable of declaring billions of propertyless elements, causing empty parsing iterations. Positive-count elements without properties are now rejected before body iteration; regression checks cover the case.

## 3. Added Unreal assets and import tools

The plugin is divided into Runtime, Render and Editor modules. Runtime owns data/assets/components and playback. Render owns shaders and view integration. Editor owns import/reimport factories and actor placement.

Static and sequence assets store decoded frames. The actor/component exposes asset assignment, units, source axes, appearance controls, crop, playback and backend selection. Source origins are rebased for float GPU data while transforms use Unreal's double-precision matrices before conversion.

The editor smoke imported ASCII PLY, binary PLY, SPLAT and a three-frame manifest, with **1,000 points per frame**. Seeks at 0, 0.05, 0.0666667 and 0 seconds selected frames **0, 1, 2 and 0**. A separate SPZ smoke accepted eight version/degree fixtures and rejected malformed TOC, unsupported-extension and gzip-bomb fixtures.

## 4. Implemented animation and bounded external loading

Independent frames use explicit timestamps and sample-and-hold selection. Equal point counts do not establish correspondence. Stable-ID interpolation requires matching unique IDs and compatible AM53 data; it interpolates positions/appearance, quaternion rotations and logarithmic scales on the CPU.

The component supports play, pause and seek, with time exposed for animation. Runtime external sequence loading indexes the manifest and maintains current/next/fallback decoded frames within a cache budget. Missing frames retain the last ready frame and report a miss. Embedded imports remain a separate source-independent asset path.

Generation checks prevent stale asynchronous results from replacing newer requests. A later review found that rapid replacement could still launch overlapping decodes. A shared per-component gate now retains the active worker slot, coalesces queued replacements and starts only the newest pending request after completion. A latent automation test verifies latest-request-wins behavior.

External files are still required for external streaming; this is not automatic cooked IoStore spatial streaming. GPU interpolation and a dedicated Sequencer editor track remain roadmap work.

## 5. Implemented GPU rendering and CPU modes

The original GPU pipeline projects anisotropic covariance, evaluates SH appearance, culls unusable projections, generates depth keys and performs stable global radix sorting across the selected view inputs.

Rendering uses bounded 16×16 tile lists, ordered front-to-back compositing and transmittance termination. If tile storage cannot fit or overflows, the selected view falls back to sorted quads. This preserves a complete selected-view rendering path instead of silently dropping overflowing tile entries.

Persistent source buffers reduce repeated static uploads. The renderer uses Unreal's Render Dependency Graph and a public scene-view extension/post-opaque hook. Captured-color interpretation and pre-exposure are handled explicitly. Opaque occlusion uses center depth; general translucent interleaving, native lighting/shadows and full temporal integration are not established by this path.

CPU-assisted mode sorts on CPU and draws on GPU. Software mode converts transformed covariance, evaluates appearance and uses the portable CPU compositor before display. It is a capped diagnostic path, not a high-count CPU performance claim. Per-point antialias compensation and matching cutoff settings were added during parity review.

## 6. Corrected integration and scaling problems

| Observed problem | Correction and evidence |
|---|---|
| Editor level subsystem absent in the isolated host | Disabling all default engine plugins changed initialization behavior. Normal engine defaults were restored and only unrelated Marketplace plugins disabled. Import/map smoke then passed. |
| Shader compiler failures | Split grouped shader parameter declarations and guarded compute-only code; corrected shader binding declarations. Subsequent SM5/SM6 runs compiled successfully. |
| Entire GPU screenshot black | Unreal copies view families between game and rendering threads; a pointer-keyed lookup lost the snapshot. Data now travels in the public view-family extension payload. The shell rendered after the fix. |
| Incorrect exposure integration risk | Use the actual view uniform pre-exposure in shaders rather than an eye-adaptation estimate. |
| One-dimensional dispatch limit at high counts | Use a two-dimensional dispatch layout with matching linear group indexing. A 16,776,961-element sorting test verified the boundary. |
| Serial radix-prefix bottleneck | Replaced it with an original hierarchical exclusive scan and exact GPU readback tests. |
| Orthographic sorting by clip W | Sort by view-space depth; software preview explicitly reports its perspective-only limitation. |
| C++ array return ABI warning | Added an output-array SH evaluation interface for the Unreal cross-module call. |
| Deprecated UE GPU profiling macro | Used UE 5.8's supported stat event scope and added explicit CSV submission counters. |

The normal SM5 suite passed **eight tests**. The SM6 suite passed **nine**, including the stress test. Scan validation compared **6,520,588 outputs**; ordinary radix tests compared **2,132,841 stable key/index pairs**; the dispatch-boundary stress compared **16,776,961 pairs**. These are algorithm correctness checks, not rendering FPS measurements.

## 7. Compared rendered outputs

A fixed-camera 1,000-point synthetic anisotropic shell was captured using tiled GPU, quad GPU, a low-capacity tile probe, CPU-assisted and CPU software modes. Rendering disabled produced a black control image.

- Quad GPU and CPU-assisted captures were pixel-identical.
- The low-capacity probe matched quad output; this is consistent with fallback, but is not direct overflow readback.
- Tiled GPU versus CPU software differed by at most **2/255** per channel.
- Tiled GPU versus quad output differed by at most **14/255**; no general parity claim or definitive attribution was made.

Metrics, foreground-only means and image hashes are retained in [Validation.md](Validation.md) and [the comparison report](Evidence/backend-image-comparison.json). One scene cannot establish all SH/transform/temporal/cross-vendor behavior.

## 8. Built a benchmark that verifies rendering

The first hidden-editor attempt produced plausible timings while most timed frames did not render the splats. Those timings were rejected. The revised driver explicitly submits a SceneCapture2D into a native **1280×720** render target. CSV counters require the expected selected-splat count and one submitted view per interior measured frame, plus positive engine GPU frame time.

Each stage warms up for 120 ticks and captures 300 frames. The 296 interior CSV rows are validated after discarding two boundary rows at each end. Hardware was an **RTX 4090**, driver **610.88**, on the documented Windows machine, using D3D12 SM6.

| Selected static inputs | Asset/instance arrangement | Mean aggregate GPU frame time | p95 GPU frame time |
|---|---|---:|---:|
| 1,000,000 | One 1M asset, one actor | 3.0390 ms | 3.1754 ms |
| 5,000,000 | The same 1M asset, five actors | 6.8954 ms | 6.9234 ms |

The generator shrinks footprints with count. These are short, small-footprint synthetic workloads, not representative high-overlap scans. Selected count is not measured visibility; tile fallback state was not read back. GPU time is aggregate engine GPU time, not isolated plugin time, and callback/engine intervals are not presented-game FPS. See [the benchmark evidence](Evidence/synthetic-benchmark.json).

The legacy Unreal render-target PNG exporter produced valid PNG data followed by trailing bytes, stalling an EOF-only completion check. Validation now walks bounded PNG chunks and checks CRCs. Export was switched to ImageWriteQueue; final captures have zero trailing bytes. Earlier files were retained locally and excluded from source distribution.

## 9. Verified an actual cooked Shipping application

An isolated host compiled the Runtime/Render code for Win64 Shipping without UnrealEd or the Editor module in its runtime link. Plugin sources were checked against the Shipping copy.

The packaging workflow required several host/environment corrections: move AutomationTool logs into the workspace, use the required installed-engine execution permissions, use disk cook output after a Zen output-store connection problem, and retain default engine resources needed by bundled startup materials.

The successful cook processed **519 packages with zero reported errors/warnings**, then staged and archived the game. The archived Shipping executable loaded the 1,000-point shell, selected the test camera, captured an image after 121 ticks and exited with code 0. Test-host-only cleanup hid the default pawn and set a 90° camera FOV. The final 1280×720 image shows the full unobstructed shell and passes PNG CRC/trailing-byte checks.

This proves one cooked static scene. It does not prove packaged animation, streaming or packaged performance. Test-host instrumentation, engine binaries, images and raw logs remain outside the public source package. See [Shipping evidence](Evidence/shipping-cook.json).

## 10. Prepared a source-only handoff

Original code is Apache-2.0, with reviewed third-party notices and pinned Zstandard provenance. No restricted research rasterizer/training stack or third-party scan corpus was bundled. Code licensing does not clear all patents, model rights or Unreal editor-tool distribution conditions; public GitHub clearance remains unverified.

The historical `AbuM53-0.1.0-dev-source.zip` contained 107 source files plus a generated manifest, was 610,188 bytes, and had SHA-256 `4f8692b8c2820c8dca7a1518cf509d205f7048cf03b75d7f2870e153279e78a0`. ZIP CRCs, unique entries, manifest hashes, unpacked audit and byte-identical repacking passed. The package tool was also corrected so its generated manifest does not break subsequent auditing/repacking.

That archive is preserved unchanged. The new Git baseline adds this walkthrough and version-control documentation under **v0.0.0.1**. Subsequent changes must be recorded in [CHANGELOG.md](../CHANGELOG.md) and `Docs/Changes/` alongside the implementation commit.

## What remains

The full plan is not complete. Cooked spatial streaming/LOD, compact GPU formats, broader source-profile conformance, additional native 4D adapters, GPU interpolation, cinematic/temporal integration, AMD/Intel testing and public distribution review remain explicit work packages. The authoritative current mapping is [ImplementationStatus.md](ImplementationStatus.md); operational limits are in [CurrentScope.md](CurrentScope.md).

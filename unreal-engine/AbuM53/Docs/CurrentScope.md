# Current implementation scope

Version: v0.0.0.4. Date: 26 October 2026.

This table describes code present in the development tree. Actual build, runtime and image-test results are separate in [Validation.md](Validation.md). The research plan remains a roadmap; this development version must not be described as its complete v1.0 implementation.

| Area | Present implementation | Boundary / outstanding work |
|---|---|---|
| Portable core | C++17 parser, math, CPU reference and converter without UE headers | Additional compiler/platform coverage is required |
| Static formats | Gaussian ASCII/binary LE/BE PLY; 32-byte `.splat`; SPZ v1–v4; original `.am53` | SPZ coordinate extensions rejected; unsupported models fail explicitly; SOG, KSPLAT, glTF and compressed PLY remain future adapters |
| Attribute handling | Full SH0–3, activated scale/opacity and normalized XYZW rotation; rebased positions for UE | Runtime uses 256-byte float32 records rather than the proposed compact 128-byte layout |
| Assets/editor | Static/sequence asset, import/reimport factory, placement actor and details controls | No complete custom asset editor, thumbnail workflow or dedicated Sequencer track |
| About/provenance | Window → About Abu M53; installed Markdown inventory, origin declarations and reviewed implementation hashes | Provenance declarations and drift checks cannot certify authorship or public-distribution clearance |
| Animation | Independent frames; stable-ID keyframe interpolation; play/pause/seek; animatable time property | No native XYZT/HexPlane/neural decoder; stable interpolation runs on CPU |
| External streaming | Index-only independent-sequence loading, asynchronous single-frame decode, bounded retained frame cache and stale-result rejection | External files remain required; no automatic cooked IoStore integration or camera-driven spatial hierarchy |
| Cooked data | Versioned contiguous point payloads serialized with assets; packaged static-fixture launch/render smoke passed | Entire embedded clip occupies its budget; not out-of-core spatial streaming; packaged animation/streaming unverified |
| GPU rendering | Covariance projection with clip-depth rejection and an off-axis derivative guard, SH evaluation, common per-view global radix sort, quads; bounded 16×16 tiles with overflow fallback | Basic RTX 4090 validation exists; broader hardware qualification required; center-based clipping/depth/order is approximate; no exact partial-Gaussian near-plane clipping or general translucent interleaving |
| GPU source cache | Global bounded LRU of immutable source buffers, weak CPU identity, protected render-graph extractions, upload/hit/memory telemetry | A source that cannot fit uses uncached uploads; full source buffers are uploaded regardless of selected draw count; GPU caching does not replace spatial LOD or compressed layouts |
| Tile compositing | Per-tile ranks sorted and composited front-to-back, early transmittance exit and single alpha resolve | Capacity overflow falls back to quads; performance must be measured on difficult high-overlap scenes |
| CPU modes | CPU-assisted sort plus bounded software reference/diagnostic rendering | Software scene integration and transformed appearance have explicit limitations; no GPU-equivalent FPS claim |
| Quality/profile | Source parameters retained in portable representation; UE scene-color interpretation in GPU renderer | Strict GPU source-appearance conformance, color-profile interoperability and film effects need additional validation |
| Testing | Original fixtures, portable tests, UE automation/import scripts, GPU cache/readback and projection regression cases, one-scene GPU/backend captures, controlled 1M/5M workload, packaged static smoke and source allowlist tooling | Test presence is distinct from a recorded pass; packaged animation/performance, representative-scene benchmarks and all-vendor parity remain required |

## Current memory/count limits

- UE editor import's default decoded-data budget is 1 GiB: at 256 bytes per point this allows 4,194,304 total points across a complete imported clip, subject to other validation constraints.
- A serialized frame's packed array is additionally limited by UE's signed 32-bit array length. The portable core's wider file offsets do not remove this UE representation constraint.
- Runtime external sequence caching is configurable from 16–8192 MiB, default 512 MiB. One decoded frame is limited to one third of the configured cache budget, leaving room for current/next/fallback frames.
- The CPU streaming limit does not include parser temporary allocations, encoded file storage, temporary copies, uploads or GPU allocations. Do not equate it with total process memory.
- GPU source retention has a separate global budget: `r.AbuM53.SourceCacheMiB`, default 2048 MiB, clamped to 0–8192 MiB. Zero disables retention. Use 3072 MiB alongside a 3072 MiB CPU streaming cache for the three 3-million-splat samples. The GPU cache reserves conservative padded sizes while uploads are pending and accounts actual pool-aligned allocation sizes after extraction.
- GPU cache limits exclude active graph resources, sort/project/tile buffers, transient uploads and allocations retained by Unreal's resource pools. A budget reduction waits for protected pending extractions to complete before evicting those entries. Oversized or pressure-fallback sources still draw through uncached uploads and can therefore upload repeatedly.
- Renderer point budgets control selected input points, not all stored data. The GPU source buffer contains the full decoded sample regardless of a smaller selected count. Current prefix selection does not preserve the image as a trained spatial LOD would. An 8192 MiB aggregate cache does not enable a single 20-million-point, 5.12 GB source in the current packed-array/buffer representation; that scale requires segmentation or a different representation.
- Tile scratch/output sizing is bounded to an estimated 256 MiB with 16 MiB headroom; capacity is a power of two between 32 and 1024. Inability to fit or any tile overflow requests the full selected-view quad fallback.
- CPU software preview is separately capped and is not suitable for unbounded high-count real-time playback.

## Streaming semantics

Editor import embeds the clip by default for source-independent asset loading. A manifest with explicit `storage:"external"` instead saves an external frame index. `LoadFileAsync` can instead read an independent-frame manifest and keep external-frame metadata, then schedule the currently requested and next frame into a bounded cache. Fitting frames remain cached across loop boundaries; the last displayed sample is included in cache accounting. An unavailable frame displays the last ready frame and records a miss. Changing the request invalidates stale results; the current decoder call is not forcibly interrupted.

Stable-ID tracks require matching unique IDs and SH degree in `.am53` inputs. Arbitrary equal-sized PLY frames are not interpolated. A baked-frame sequence does not establish temporal training coherence.

## GPU reuse and projection behavior

GPU sources are keyed by component identity and immutable decoded allocation. Completed entries are retained by recent use while they fit the global budget; they are removed when their CPU allocation expires or after 120 unused view-family callbacks. A weak CPU reference avoids extending the component's decoded cache after an upload. A graph-owned strong reference keeps the source valid during `NoCopy` upload, and heap-stable entries remain alive until queued buffer extraction finishes. Reuse of a pending RDG source is limited to that same graph. A pending entry in another graph is not shared across graphs or overwritten.

The `AbuM53` CSV category includes `SourceUploadCount`, `SourceUploadMiB`, `SourceCacheHits`, `SourcePendingReuses`, `SourceCacheEvictions` and `SourceUncachedUploads` as accumulated frame metrics. `SourceCacheResidentMiB`, `SourceCacheReservedMiB` and `SourceCacheEntries` are gauges. Payload upload MiB and allocated resident MiB differ because GPU buffers can be padded. These diagnostics establish upload/reuse behavior; they do not establish presented FPS. See [the walkthrough](Import_Editing_and_PLY_Sequence_Walkthrough.md) for interpretation and [the release record](Changes/v0.0.0.3.md) for executed checks and measurements.

The projection shader explicitly rejects centers outside Unreal's `[0, w]` clip-depth interval, including the reversed-Z near plane, because its screen-space quads otherwise bypass that clipping. It also clamps the perspective derivative's normalized-device-coordinate input to `[-1.3, 1.3]` to bound unstable off-axis footprints. The real projected mean and source records are unchanged; orthographic derivatives remain exact. This guard is an approximation for perspective covariance outside the guard band, and center rejection is not exact clipping of a Gaussian's partial extent.

## Work still required for the full plan

Spatial error-controlled hierarchy/LOD, bounded cooked streaming, compact GPU layouts, dedicated Sequencer/editor UI, deterministic MRQ/lens sampling, source-profile GPU conformance, full depth/velocity integration, additional interchange/native-4D adapters, sustained high-count optimization, cross-vendor qualification and the final public-distribution review remain explicit work packages. No source archive or successful small-scene screenshot substitutes for these results.

Windows development installation: v0.0.0.3 updates the engine-wide installation and persistent `abu_M53_Test_01` project with the verified Earth fixes and real Skate sequence level. See [installation and ongoing updates](Windows_Installation_and_Test_Project.md) and [the current release record](Changes/v0.0.0.3.md).

The v0.0.0.3 importer, storage, editor lifecycle, source-cache and projection changes are explained in [the import and sequence walkthrough](Import_Editing_and_PLY_Sequence_Walkthrough.md).

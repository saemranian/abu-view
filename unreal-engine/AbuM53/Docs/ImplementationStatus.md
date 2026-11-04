# Implementation status against the original plan

Development version: **v0.0.0.4**, 26 October 2026. The [original implementation plan](ImplementationPlan.md) is retained unchanged as the target roadmap. This document maps that roadmap to the actual development tree; it is not a declaration that the plan or v1.0 definition of done has been completed.

“Implemented” means code exists. “Verified” refers only to the specific checks recorded in [Validation.md](Validation.md) and the [v0.0.0.3 release record](Changes/v0.0.0.3.md). Historical checks below retain their original scope; the presence of a new test is not a claim that its latest execution passed. A successful small synthetic scene does not establish all format variants, realistic-scene quality, platform support or sustained performance. [CurrentScope.md](CurrentScope.md) records count and memory limits.

## Original milestone mapping

| Original phase | Implemented and verified evidence | Remaining exit-gate work |
|---|---|---|
| 0 — requirements and evidence freeze | UE 5.8.2 / Windows / RTX 4090 reference machine identified; original fixtures; Apache/MIT/BSD provenance inventory; unsupported legal and FPS claims excluded | Additional NVIDIA/AMD/Intel reference PCs, broader scene corpus and final UE Engine Tools/publication classification |
| 1 — UE integration and core math spikes | Portable covariance/SH/activation/CPU rendering; UE modules and public rendering hook; synthetic GPU viewport capture and cooked Shipping static-scene launch/render smoke | Full color/depth/fog/temporal feasibility matrix, packaged animation/streaming and strict source-profile image oracle |
| 2 — static import and basic GPU | Gaussian PLY and `.splat`, source metadata, asset/import/reimport factory, actor/component, SH0–3, covariance projection, GPU sorting and quads; earlier four-fixture UE import/map/seek smoke; v0.0.0.3 adds bounded binary PLY chunk reads, worker decoding with cancellation/stage feedback, and Details refresh persistence | Broader transform, multi-view/multi-actor, malformed-file and source-conformance qualification; v0.2 acceptance is not declared complete |
| 3 — tiled renderer and quality | Bounded 16×16 tiles, ordered front-to-back composition, early termination and whole-view quad fallback; prior GPU scan/radix readback and synthetic-shell backend comparisons; v0.0.0.3 adds clip-depth center rejection, bounded off-axis perspective derivatives and targeted projection readback tests | Instrumented overflow/capacity stress, difficult overlap scenes, cross-vendor parity, sustained per-pass timings and quality validation; center clipping does not exactly clip a Gaussian crossing the near plane |
| 4 — cooked data and large-scene streaming | SPZ v1–v4, checksummed `.am53` container/range reading and prior cooked static-scene smoke; v0.0.0.3 adds versioned contiguous frame serialization with legacy-read migration, retained bounded CPU frame caching, explicit external manifests, and a global bounded GPU source-buffer LRU | Cooked bulk/IoStore spatial streaming, error-controlled hierarchy/LOD, spatial GPU page residency, compact/quantized GPU records and packaged large-scene tests; whole-frame caches do not fulfill spatial streaming |
| 5 — animated core and Sequencer | Timestamp manifests including supported AbuAlign-style paths, frame-hold playback, play/pause/seek, explicit stable-ID CPU interpolation and animatable time; v0.0.0.3 adds explicit `storage:"external"`, retained short-loop samples, tick-driven paused loading and ready-frame diagnostics | Dedicated Sequencer track/editor, GPU interpolation, deterministic MRQ sampling and packaged playback/streaming qualification; ready-frame diagnostics alone do not prove presented frames |
| 6 — CPU fallback and optimization | CPU-assisted sort/GPU draw and bounded CPU software diagnostic; earlier one-scene backend comparisons; v0.0.0.3 adds immutable GPU source reuse, uploads without an additional full-payload CPU copy, and upload/cache CSV telemetry | Full capability/failure ladder, sustained high-count optimization, broad CPU/GPU conformance and overload telemetry; source reuse is not a general FPS guarantee, and software diagnostic is not a production CPU performance claim |
| 7 — beta, legal/package review and release | Build/test scripts, current test evidence, source allowlist/hash audit, dependency notices and documentation | All-vendor soak tests, final source/binary review, validated publication route, representative benchmark matrix and v1.0 release gates |

## Feature-level status

| Planned area | Current status | Evidence or boundary |
|---|---|---|
| PLY/.splat/SPZ/importer | Implemented; bounded fixture coverage and newer regression cases present | Binary PLY chunk reads preserve scalar types, endian order, SH and source precision; worker import reports stages and supports cooperative cancellation; exact executed results are in the release record |
| `.am53` and manifest storage | Implemented | Original checksummed storage and frame index; explicit `storage:"external"` opts into source-file-dependent assets; no claim of compatibility with an unrelated file carrying the same extension |
| UE asset storage and editor persistence | Implemented in v0.0.0.3 | Versioned contiguous point payload writes; legacy tagged assets read through their original path and upgrade on save; older plugin versions cannot read upgraded payloads. Temporary Details unregister/register retains valid samples; source/reimport changes invalidate stale data |
| Cooked Shipping static scene | Verified for one owned 1,000-point fixture | Cook/package/launch/render smoke passed, exit 0; no editor-module linkage; packaged animation, streaming and performance unverified |
| Source-preserving attributes | Implemented in portable and float32 UE data | SH0–3 and Gaussian attributes retained; visual source-profile conformance is still a qualification item |
| GPU projection and global sort | Implemented | Covariance/SH projection, global stable radix sorting and hierarchical scan; v0.0.0.3 rejects centers outside UE clip depth and bounds perspective derivatives at NDC ±1.3 while preserving the projected mean and exact orthographic derivative; broader source-appearance qualification remains |
| GPU source-buffer reuse | Implemented in v0.0.0.3 | Global LRU defaults to 2048 MiB, caps at 8192 MiB and supports explicit 3072 MiB retention for the three large samples; accounts aligned allocations, protects pending extractions and emits upload/hit/resident metrics. Full source payload is uploaded regardless of selected draw budget |
| Tiled GPU path | Implemented; one-scene comparison verified | Fixed-capacity per-tile ranks with bounded scratch; capacity failure requests the existing quad path |
| CPU-assisted / software modes | Implemented; one-scene images compared | CPU software has a 50,000-point diagnostic cap and incomplete production scene integration |
| External animation streaming | Implemented; request/index/cache regression cases present | Retained CPU cache defaults to 512 MiB and caps at 8192 MiB, with current/next/fallback reservations; fitting samples persist across loops and Details refreshes. External files remain required, and stale decode work already running is not forcibly interrupted |
| Cooked spatial streaming and LOD | Deferred | Embedded assets serialize whole clips; prefix point budgets are not spatial LOD |
| Packed/quantized GPU layout | Deferred | Current record is 256 bytes, not the proposed compact 128-byte/quantized storage |
| Stable-ID interpolation | CPU implementation and runtime tests present | Explicit AM53 IDs and matching SH degree required; no interpolation inferred from equal frame counts |
| GPU interpolation | Deferred | Current interpolation runs on CPU |
| Native analytic 4D/XYZT and neural checkpoints | Deferred | Independent baked frames are supported; arbitrary model checkpoints are not executed or reconstructed |
| Sequencer/MRQ | Partial | Time property supports generic animation; no dedicated track, deterministic lens/shutter accumulation or full MRQ qualification |
| TSR, motion vectors, VR/XR, nDisplay | Deferred qualification/integration | Viewport rendering is not proof of correct temporal reconstruction or stereo/multi-view behavior |
| Opaque depth and translucency | Partial | Center-depth occlusion is approximate; no general interleaving with arbitrary translucent scene geometry |
| Lumen, shadows, path tracing, reflections and collision | Not implemented as general integration | Splats do not automatically become full UE geometry with these features |
| SOG/KSPLAT/glTF/GSD/compressed PLY adapters | Deferred | Format-specific source/version/license and quality work required |
| Cross-vendor certification | Pending | No AMD/Intel execution evidence yet; lack of CUDA dependencies is not certification |
| Public GitHub/legal release clearance | Pending final review | Own source uses Apache-2.0 with retained MIT/BSD notices; UE editor-tool distribution classification, model rights and unrelated patents are separate |

## Release interpretation

This is a concrete development plugin with a portable core, importer, animation foundation, GPU/CPU rendering paths and reproducible QA. It is not the original plan's completed production release. Do not advertise 100M-source streaming, 5M-at-60-FPS, 120-FPS, all-vendor support or unrestricted publication as achieved facts without the corresponding completed evidence and review.

Windows development installation: v0.0.0.3 continues the engine-wide UE 5.8 installation and persistent `abu_M53_Test_01` project. Its exact installed-build verification, executed test results and real-file measurements are recorded in the [current release record](Changes/v0.0.0.3.md). See [installation and ongoing updates](Windows_Installation_and_Test_Project.md) and the [import, editing and sequence walkthrough](Import_Editing_and_PLY_Sequence_Walkthrough.md) for the workflow and separate CPU/GPU cache settings.

# Abu M53 — UE 5.8 implementation plan

**Research date:** 25 October 2026, Asia/Dubai  
**Deliverable:** research and implementation specification; no plugin implementation or performance certification has been completed.  
**Plugin display name:** Abu M53  
**Code/module prefix:** `AbuM53`  
**Proposed repository name:** `AbuM53`  
**Engine baseline:** Unreal Engine 5.8.2, with separate validation of other 5.8 patch releases.  
**Primary platform:** Windows x64, DirectX 12, NVIDIA / AMD / Intel GPUs.  
**Confirmed terminology:** the requested “4GDS” means animated **4D Gaussian Splatting (4DGS)**.

### Navigation

- [Recommendations and research](#1-recommended-product-and-principal-decisions)
- [Formats and compatibility](#4-import-formats-and-compatibility-tiers)
- [Architecture and build](#5-proposed-source-architecture)
- [GPU pipeline](#7-gpu-rendering-pipeline)
- [UE integration and quality](#8-ue-integration-and-image-quality)
- [4D playback](#9-4d-playback-implementation)
- [Streaming and memory](#10-high-count-streaming-lod-and-memory-management)
- [GPU/CPU fallback](#11-gpu-first-execution-and-cpu-fallback)
- [Performance targets](#12-quality-presets-and-performance-targets)
- [Verification and benchmarks](#14-verification-strategy)
- [Implementation phases](#16-implementation-phases-staffing-and-acceptance-gates)
- [Licensing and GitHub](#17-open-source-licensing-and-github-publication)
- [Completion checklist](#19-definition-of-done)

## 1. Recommended product and principal decisions

Build an original C++/HLSL plugin that imports static and animated Gaussian data, converts it into a documented, streamable representation, and renders it using Unreal's Render Dependency Graph (RDG) and Render Hardware Interface (RHI). Keep the portable import/format/math library independent of Unreal. Use GPU compute for visibility, temporal evaluation, projection, sorting and rendering; use CPU workers for file access, validation, decompression where appropriate, and a bounded software fallback.

The recommended default is a deterministic, tiled Gaussian renderer with explicit quality controls, together with a simpler sorted-quad GPU backend for initial validation and compatibility. Neither CUDA, a Python installation, Niagara, mesh shaders nor ray-tracing hardware should be required. An optional stochastic renderer deserves a later research phase for exceptionally large scenes, but must prove temporal quality before becoming a production option.

**The open-source objective is feasible as a design goal, but “no legal limitations” cannot be guaranteed.** Use Apache-2.0 for original Abu M53 code, carefully audited permissive dependencies, and rights-cleared examples. Unreal remains subject to Epic's EULA; the editor/importer distribution requires a specific Engine Tools classification review before ordinary public-GitHub publication. Do not claim unrestricted clearance for the complete plugin before that review. Section 17 specifies an actionable publication route.

Decisions to adopt:

| Area | Decision | Reason |
|---|---|---|
| Engine | Develop against installed UE 5.8.2; record exact build identity | Test actual interfaces instead of assuming all 5.8 builds match |
| GPU path | DX12 through UE RHI and HLSL | Supports the requested three GPU vendors without proprietary compute interop |
| Static v1 formats | Gaussian PLY, ordinary `.splat`, SPZ with explicit version support | Covers common exports while retaining rich PLY data |
| Dynamic v1 | Timestamped frame sequences plus baked stable-ID tracks | Practical interoperability without executing training checkpoints |
| Other dynamic models | Named, versioned adapters for mathematical representations | “4DGS” is a family of methods, not one interchange format |
| Quality | Preserve source parameters and rendering conventions; make approximations selectable | More splats alone do not guarantee a better image |
| Scale | Spatial hierarchy, temporal indexing, bounded residency, progressive streaming | Source count, resident count and visible count differ |
| Sorting | GPU by default; explicit CPU-assisted and software fallback modes | Avoid recurring full-data transfers and render-thread waits |
| Licensing | Original implementation; per-file dependency audit; Apache-2.0 | A repository's top-level license is insufficient evidence |
| Publishing | Stage independent core, UE runtime and editor tooling separately | Keeps the open-source route concrete without overlooking Epic's distribution terms |

## 2. Research findings and what they imply

### 2.1 UE version and integration

Epic has released UE 5.8. The local engine metadata inspected for this research identifies **5.8.2**, changelist **56702186**, compatible changelist **55116800**, at `C:\Program Files\Epic Games\UE_5.8\Engine\Build\Build.version`. This verifies an available development baseline, not a successful Abu M53 build. [Epic UE 5.8 announcement](https://www.unrealengine.com/news/unreal-engine-5-8-is-now-available)

Use a plugin-owned renderer with a thin, version-specific integration layer. Public render hooks are preferable to engine patches, but support for scene color, depth, velocity, temporal upscaling and post processing must be demonstrated with a small UE 5.8.2 prototype before committing to full feature claims. An editor viewport success is not enough: packaged builds, camera captures and Movie Render Queue require their own tests.

### 2.2 Rendering approaches worth evaluating

| Evidence | Implication for Abu M53 |
|---|---|
| The original 3DGS work establishes anisotropic Gaussians, view-dependent appearance and visibility-aware splatting | Implement the mathematics independently; the original code license is a separate issue |
| Mip-Splatting addresses sampling artifacts | Include opacity-compensated screen-space filtering; do not claim full Mip-Splatting behavior without its required source/training information |
| StopThePop studies inconsistent ordering and popping | Test camera-motion stability and consider local depth refinement; do not copy its restricted renderer wholesale |
| NVIDIA's Vulkan sample compares vertex/mesh paths and GPU/CPU sorting | Benchmark a portable quad path before assuming a more specialized backend is faster |
| 3DGRT/3DGUT support camera and secondary-ray capabilities beyond ordinary splatting | Keep distorted-camera and ray-traced rendering as later extensions, with their own data-model and hardware requirements |
| Gaussian Point Splatting, SIGGRAPH 2026, uses stochastic sampling and atomics to handle extremely large scenes | Reserve a research backend; its noise, convergence and camera-motion behavior must be measured |
| External-memory Gaussian hierarchy research addresses scenes larger than GPU memory | Use explicit residency and view-dependent hierarchy selection rather than trying to upload every source splat |

Sources: [original 3DGS paper/project](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/), [Mip-Splatting](https://niujinshuchong.github.io/mip-splatting/), [StopThePop](https://r4dl.github.io/StopThePop/), [NVIDIA rasterization sample discussion](https://developer.nvidia.com/blog/?p=98796), [3DGRUT](https://github.com/nv-tlabs/3dgrut), [Gaussian Point Splatting](https://jorisar.nl/gaussian_point_splatting/), [A LoD of Gaussians](https://arxiv.org/abs/2507.01110).

The Gaussian Point Splatting paper reports a 425-million-Gaussian example at 1920×1080 on an RTX 4070 Ti SUPER with example view times of **65.6, 37.5 and 24.3 ms**. These correspond to approximately **15, 27 and 41 FPS**, not a universal 60/120 FPS result. The images are converged stochastic results. These measurements motivate research; they are not Abu M53 benchmarks. [Author paper](https://jorisar.nl/gaussian_point_splatting/gaussian_point_splatting.pdf)

### 2.3 Existing UE projects: reference, not automatic foundations

| Project | Useful comparison | Decision |
|---|---|---|
| YaGS | Native UE source, GPU sorting, alternative draw backends | Review selected components and notices; benchmark independently before any reuse |
| OpenSplat4D | Dynamic model adapters and editing workflow | Exclude as a wholesale base: its own third-party notice identifies restricted training code and a restricted native-4D shader derivation |
| SplatRenderer-UEPlugin | `.gsd` playback and Sequencer workflow | Treat as a behavior reference; verify source completeness and provenance before considering reuse |
| NVIDIA `vk_gaussian_splatting` | Sorting, compression, timing and backend experiments | Algorithm/performance reference; do not transplant an entire external renderer into UE |

Sources: [YaGS](https://github.com/yandex/yags), [OpenSplat4D third-party notices](https://github.com/YuanBaoSMadLab/OpenSplat4D/blob/main/THIRD-PARTY-LICENSES.md), [SplatRenderer](https://github.com/DazaiStudio/SplatRenderer-UEPlugin), [NVIDIA sample](https://github.com/nvpro-samples/vk_gaussian_splatting).

## 3. Product scope and support contract

### 3.1 Required for v1.0

- Import static PLY, `.splat` and supported SPZ versions through explicit format profiles.
- Import timestamped PLY sequences and Abu M53 baked dynamic data.
- Provide a scene actor/component, asset preview, reimport, crop controls, playback, Blueprint API and Sequencer track.
- Render anisotropic covariance and all available SH bands through degree 3; preserve higher/unknown source attributes in metadata or report unsupported data explicitly.
- Support multiple overlapping Abu M53 actors using a common visibility and compositing pipeline per view.
- Stream large static scenes and animated segments within user-visible CPU/GPU memory budgets.
- Work in editor, PIE, standalone and cooked Windows builds.
- Provide GPU rendering, CPU-assisted rendering and an actual bounded CPU software renderer.
- Provide a fidelity mode, an adjustable real-time mode, and deterministic cinematic evaluation.
- Ship repeatable quality/performance tests, documented format support and a dependency bill of materials.

### 3.2 Deliberately separate follow-on work

SOG, compressed PLY, KSPLAT, standardized glTF/GLB splats, GSD, native spacetime formats, Vulkan/Linux, XR, nDisplay, arbitrary translucency interleaving, full motion-vector integration, special camera models, relighting, path tracing and stochastic rendering are separate deliverables. They should not delay a correct static/dynamic Windows core unless an identified workflow requires them earlier.

Training, reconstruction from photographs, COLMAP execution, remote GPU services and model downloading are outside the plugin's initial purpose. A captured radiance field is not automatically a relightable material, collision mesh, Nanite asset, Lumen contributor or hardware-ray-tracing primitive.

### 3.3 Important terminology

Every performance report must distinguish:

1. **Source splats:** primitives stored in the complete input dataset.
2. **Resident splats:** primitives currently available in CPU/GPU caches.
3. **Active splats:** primitives selected for the current time and LOD.
4. **Visible splats:** active primitives that survive per-view culling.
5. **Tile references:** splat/tile intersections generated by the rasterizer.
6. **Pixel contributions:** actual blend work, which can dominate everything above.

“100 million splats supported” must state whether it means streamed source size or simultaneous active rendering. FPS must specify output and internal resolution, hardware, quality mode, source SH degree, view path, temporal processing and the cost of the rest of the UE scene.

## 4. Import formats and compatibility tiers

### 4.1 Static formats

| Format | Support target | Required handling |
|---|---|---|
| Gaussian PLY | v0.2 / v1 core | ASCII and binary little-endian first; binary big-endian when tested. Read properties by name/type, not position. Distinguish Gaussian PLY from an ordinary point cloud |
| `.splat` | v0.2 / v1 core | Validate the known 32-byte record profile; decode position, scale, RGBA and quantized quaternion. Usually DC color only; missing SH detail cannot be reconstructed |
| `.spz` | v0.4 / v1 core | Inspect magic/version/flags. Support tested legacy v1–3 gzip and current v4 stream layout; reject unknown versions. Preserve precision and antialiasing metadata where specified |
| PlayCanvas compressed PLY | v1.1 | Treat as a distinct schema with chunk bounds/quantization; never parse it as ordinary Gaussian PLY |
| `.sog` | v1.1 | Versioned manifest plus compressed image payloads; inspect SH/codebook metadata and bounds; audit archive and WebP dependencies |
| `.ksplat` | v1.1 | Pin the producer's version and compression layout; not a universal standard |
| glTF / GLB Gaussian extension | v1.1 | Validate the current `KHR_gaussian_splatting` schema, required extensions, transform and color conventions; explicitly list supported compression extensions |
| Proprietary project/checkpoint containers | No generic promise | Accept documented exports or add a named adapter with permission and tests |

SPZ has evolved beyond the often-cited gzip-only version: current upstream describes v4 with separate Zstandard streams. Version negotiation belongs in the importer, not the filename extension. [SPZ specification and implementation](https://github.com/nianticlabs/spz)

The current Khronos extension is marked ratified. Its static representation and rendering conventions should guide a future standards adapter; it does not supply a general 4D animation standard. Its explicit source color-space and sorting requirements must be retained as a rendering profile. [KHR Gaussian splatting specification](https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Khronos/KHR_gaussian_splatting)

Further format references: [antimatter15 `.splat` viewer](https://github.com/antimatter15/splat), [PlayCanvas splat-transform](https://github.com/playcanvas/splat-transform), [GaussianSplats3D](https://github.com/mkkellogg/GaussianSplats3D).

### 4.2 PLY semantics must be explicit

For the common Graphdeco-style profile, recognize `x/y/z`, `scale_0..2`, `rot_0..3`, `opacity`, `f_dc_0..2`, and `f_rest_*`. The profile specifies whether scale is logarithmic, opacity is a logit, quaternion order, SH ordering and source color conventions. Do not apply `exp()` or sigmoid to already activated data from another exporter.

Build importer presets for named exporters only after obtaining licensed fixtures. A user-selected axis/color profile overrides ambiguous metadata and is saved with the asset. Provide an import report listing source precision, SH degree, dropped attributes, repaired values, coordinate conversion and estimated memory. Fail clearly on invalid required fields; limited repairs should be counted and opt-in when they change appearance.

Support source float64 positions during ingestion without losing precision before rebasing. Skip unknown PLY properties safely, including list properties on unrelated elements. Check integer overflow and file bounds before allocations. A PLY containing only XYZ/RGB can be offered as an explicitly approximate point-cloud conversion; it is not equivalent to a trained Gaussian asset.

### 4.3 Dynamic formats and representations

| Representation | Import/evaluation strategy | Priority |
|---|---|---|
| Independent static frames | Timestamped manifest and per-frame PLY/SPZ; frame hold by default, variable counts permitted | v1 core |
| Stable-ID baked tracks | Time-indexed transforms, opacity, SH and lifetime; deterministic interpolation | v1 core |
| Spacetime Gaussians with analytic motion | Adapter translates known fields and equations into typed track data; evaluate on GPU | v1.1, after exporter fixtures |
| Full 4D Gaussian covariance | Dedicated adapter, positive-definite checks, temporal conditioning and required appearance basis | v1.1/research |
| Canonical Gaussians plus HexPlane/MLP deformation | Prefer external baking into tracks or frame segments; direct neural evaluation is a separate optional module | Later |
| GSD v1/v2 | Version-pinned compatibility decoder; compare with actual encoder fixtures | v1.1 |

The common “4DGS” research repositories represent different models. Neither a `.ply` extension nor the term 4DGS establishes which time function or appearance basis is present. The adapter registry must declare method, exporter version, required fields, time units, basis conventions and supported evaluation features. [4DGaussians](https://github.com/hustvl/4DGaussians), [SpacetimeGaussians](https://github.com/oppo-us-research/SpacetimeGaussians), [Fudan 4D Gaussian Splatting](https://github.com/fudan-zvg/4d-gaussian-splatting)

GSD is useful interoperability work, but its current v2 integration guide contains layout ambiguities and lossy choices. Resolve its header/codebook/padding details against a pinned encoder and binary fixtures before claiming support; it should not become Abu M53's preservation format. [GSD v2 guide](https://github.com/DazaiStudio/4dgs-converter/blob/master/docs/gsd-v2-renderer-integration.md)

### 4.4 Existing AbuCam / AbuAlign integration

Local project output includes sequence manifests identifying `independent_3dgs_frames` with `temporal_optimization: false`, timestamps and per-frame PLY paths. Add a small importer adapter for this existing workflow. Preserve its truthful classification: it is animated playback of separately trained frames, not proof of temporally coherent 4D training.

The inspected completed sample contained one frame, so it validates the adapter schema only, not multi-frame temporal quality. Its `exporter_world` label does not establish units or axis directions; require a saved, explicit exporter-to-UE coordinate profile before conversion.

Use the manifest's timestamps and validated coordinate profile. Resolve relative paths within the chosen input root. Do not depend on an installed training environment or modify the original files. Treat this as an optional convenience adapter over the generic sequence reader.

## 5. Proposed source architecture

```text
AbuM53/
  LICENSE                         # Apache-2.0 for original code
  NOTICE
  THIRD_PARTY_NOTICES.md
  README.md
  CONTRIBUTING.md
  SECURITY.md
  Core/                           # Portable C++; no UE headers
    Include/AbuM53/
    Source/Formats/
    Source/Math/
    Source/Streaming/
    Source/SoftwareRenderer/
    Tests/
  Tools/
    M53Convert/                   # Portable command-line converter
    Benchmark/
  Unreal/AbuM53/
    AbuM53.uplugin
    Source/AbuM53Runtime/
    Source/AbuM53Render/
    Source/AbuM53Editor/           # Separate release/classification boundary
    Source/AbuM53Sequencer/
    Source/AbuM53SequencerEditor/  # Editor UI only
    Shaders/Private/
    Resources/
    Config/
  Tests/Fixtures/                 # Own synthetic or explicitly licensed data
  Docs/
    Formats/
    Architecture/
    Benchmarks/
    Legal/
  ThirdParty/                    # Audited minimal dependencies only
```

This is the development layout. Publication may use separate core/runtime/editor repositories or archives after the legal gate; a directory split alone does not change legal obligations.

### 5.1 Module responsibilities

| Module | Responsibility |
|---|---|
| Portable core | Decoders, canonical data, file validation, container, math, CPU reference rendering, portable tests |
| `AbuM53Runtime` | Asset and component types, actor, playback state, async streaming, Blueprint API and cooked data |
| `AbuM53Render` | Global shaders, RDG passes, GPU allocations, per-view state, profiling and renderer backends |
| `AbuM53Editor` | Import/reimport factory, thumbnails, asset editor, inspectors and diagnostics; editor-only build |
| `AbuM53Sequencer` / `AbuM53SequencerEditor` | Runtime evaluation and editor track UI in separate modules; rational time and deterministic playback |
| `M53Convert` | Offline transcoding, validation and baking without Unreal dependencies |

Use familiar UE facilities such as `UFactory`, `UAssetImportData`, scene components, `FGlobalShader`, RDG resources and scene-view extensions after confirming their 5.8.2 signatures. Register shader directory mapping at the appropriate early loading phase. Editor dependencies must never leak into a Shipping target. Treat exact class names below as proposed, not existing APIs.

### 5.2 Public API surface

- `UAbuM53Asset`: immutable static source description and cooked chunk index.
- `UAbuM53Sequence`: time range, frame rate, segments, track descriptors and external-source provenance.
- `UAbuM53Component` / `AAbuM53Actor`: asset instance, transform, crop, visibility, quality overrides and playback binding.
- `UAbuM53WorldSubsystem`: per-world registration, aggregate budgets and shared streaming cache.
- `FAbuM53ViewExtension`: per-view pipeline scheduling through a version adapter.
- `IAbuM53FormatReader`: probe, inspect, validate and stream decoded chunks.
- `IAbuM53TemporalEvaluator`: evaluate supported track families into current/previous primitive state.
- Blueprint operations: load, play, pause, seek, loop, set rate, set budget, get statistics and subscribe to ready/error events.

Do not create one UObject, Actor or particle-system instance per Gaussian. Keep bulk numeric arrays outside UObject object graphs. Workers produce immutable results; game-thread ownership and render-thread resource changes use explicit handoff and fences. Multiple actors referencing one asset share immutable resident pages.

### 5.3 Build, cooking and continuous integration

Build the portable core with CMake and a supported Windows compiler independently of Unreal. Integrate that core through a narrow UE build module or compatible static library, with compiler/runtime settings matched to the selected engine toolchain. Follow UE 5.8.2's supported compiler/SDK configuration rather than choosing the newest toolchain by assumption.

The plugin descriptor identifies `FriendlyName: Abu M53`, versioned modules and supported platform scope. The shader-owning module uses the validated early loading phase, normally `PostConfigInit`. Keep optional features in explicit shader permutations and provide a generic fallback. The implementation's Build.cs dependencies should use public engine modules and avoid renderer-private include paths.

Cook source data into platform-specific bulk pages with a deterministic cache key containing source digest, importer/schema version, precision/LOD settings and target platform. Serialize portable metadata separately from transient GPU handles. Reimport invalidates affected derived data; schema upgrades require a migration/rebuild policy. Package all required runtime pages and shaders, and test on a machine without the original source files.

Continuous integration should have two lanes:

1. Public portable-core builds, unit tests, parser fuzz smoke tests and format conformance fixtures. These need no Unreal checkout or restricted samples.
2. Authorized engine builds on licensed runners: plugin build/package through Unreal's standard automation tools, cooked test project, shader compilation, launch/image smoke tests and scheduled hardware benchmarks. Gate access to these runners and their engine installation; do not expose private engine material or credentials to arbitrary fork jobs.

Use a clean build/package job for each advertised UE patch version. Keep reviewed source releases separate from compiled plugin artifacts; attach notices, build identity and checksums to each. Compile-only success does not satisfy GPU image tests. Release tags use semantic versions, while the container schema and supported exporter revisions have their own version numbers.

## 6. Canonical representation and Abu M53 container

### 6.1 Source-preserving master representation

Record mean, scale/covariance, quaternion convention, opacity, SH degree/basis, source precision, coordinate basis/units, source color space and rendering profile. Add optional stable ID, time interval, motion parameters and temporal appearance basis. Preserve import provenance and warnings.

Separate the master from derived GPU data. Reimport, quantization experiments and LOD generation must not progressively destroy the only high-quality copy. Store source hashes and deterministic conversion settings so caches can be rebuilt.

### 6.2 Proposed `.am53` / `.am53seq` format

These are **new Abu M53 formats to specify**, not existing standards. Publish the complete binary layout, schemas and a reference reader with the project.

Required layout:

1. Fixed header: eight-byte magic, major/minor version, endianness marker, flags, header length, total source count, metadata length and index offset; 64-bit file offsets/counts.
2. Typed metadata: coordinate and color profile, SH basis/degree, source/exporter/version, temporal model, bounds, duration, rational timebase and codec identifiers.
3. Spatial index: hierarchical node bounds, child ranges, LOD error bounds and page references.
4. Temporal index: segment ranges, keyframe dependencies, swept bounds, frame/track counts and random-access entry points.
5. Page table: offset, compressed/uncompressed sizes, checksum, encoding, local origin and attribute layout.
6. Attribute pages: structure-of-arrays, aligned for decoder and upload efficiency.
7. Optional provenance and extension blocks that old readers can safely skip.

Never equate a file offset with a GPU index. GPU pages use bounded local indices and a separate residency map. Reject unsupported major versions and unknown required extensions. Protect against decompression bombs, overlapping sections, cyclic dependencies and path traversal. Write conversions atomically and retain a checksum-verified index after interruption.

### 6.3 Suggested storage modes

| Mode | Purpose | Encoding |
|---|---|---|
| Preserve | Archival and numerical baseline | Source precision retained, lossless compression; no SH truncation |
| High | Default derived GPU representation after validation | Chunk-local float32 positions; float16 scale/quaternion/opacity/SH where measured error permits; float32 overrides for sensitive attributes |
| Compact | Large real-time scenes | Chunk-local quantization and optional SH/codebook compression with explicit image-error thresholds |

Keep SH coefficients in separate bands/pages where useful so distant splats need not fetch every band. Do not claim a fixed disk compression ratio: it depends on content, SH degree and motion. Disk compression and GPU-resident compression are separate decisions.

### 6.4 Example decoded GPU layout

An illustrative **128-byte SH3 record** contains 12 bytes of float32 position, 6 bytes of float16 scale, 8 bytes of float16 quaternion, 2 bytes of opacity, 96 bytes of SH coefficients and 4 bytes of flags/padding. Normalize decoded quaternions and validate numeric ranges. This is a planning layout; benchmark SoA fetches and actual GPU alignment before freezing it.

The corresponding unpadded float32 representation is 236 bytes: 59 floats. A conservative aligned reference allocation is 256 bytes per splat. Ordinary PLY may store extra normals or properties. Source file size is not a reliable VRAM estimate.

## 7. GPU rendering pipeline

### 7.1 Per-view pass sequence

```text
Resident pages + time state + camera + opaque depth
    -> select hierarchy nodes / temporal segments
    -> evaluate dynamic state and current/previous positions
    -> frustum / temporal / contribution culling
    -> project covariance, evaluate appearance, estimate footprint
    -> count tile intersections
    -> prefix scan and bounded allocation
    -> emit tile/depth/ID references
    -> GPU radix sort
    -> construct tile ranges
    -> front-to-back tile compositing with transmittance termination
    -> resolve color / alpha / optional representative depth and velocity
    -> UE composition at the selected integration point
```

Use one view-wide candidate/sort domain for overlapping actors. Sorting each actor independently and compositing whole actors is incorrect where their splats interleave. Each eye, scene capture and cinematic subview needs appropriate view state and sorting.

### 7.2 Projection and filtering

Compute covariance from scale and orientation, transform it into camera space, and project through the camera Jacobian. For source transform `A`, covariance becomes `A Σ Aᵀ`; merely swapping quaternion components does not cover reflections or nonuniform scaling. Evaluate SH using the verified source-direction convention.

Validate scale ranges, finite covariance, eigenvalue bounds and near-plane behavior. The canonical renderer requires a numerically usable covariance; a source schema allowing zero scale needs an explicit reject/regularize policy rather than an incorrect declaration that the source file is malformed. A Gaussian intersecting the camera/near plane cannot be discarded solely because its center is behind the near plane. Use conservative bounds and a tested fallback for problematic large footprints.

Add a configurable screen-space low-pass filter. Where the selected rendering model supports it, compensate alpha for the determinant change so filtering does not artificially brighten or thicken the scene. Source-trained smoothing must not be applied twice. Keep a source-compatible filter/reference profile, including the exporter's documented dilation or smoothing. An unfiltered diagnostic is a separate mode.

### 7.3 Sorting and compositing

Start with a stable GPU radix sort using a deterministic tie breaker. The sort key is profile-dependent: common camera-depth approximations and the glTF camera-distance convention are not interchangeable. Preserve the source convention in fidelity mode. A quality option may refine local order for large intersecting splats, but it must be labeled as a different rendering method.

For the tiled path, composite front to back with premultiplied color and remaining transmittance. Use a configurable termination threshold and alpha cutoff, and record them in benchmark reports. Test them against the high-precision reference. A globally sorted quad path uses the matching blend order/equation rather than mixing front-to-back and back-to-front rules.

Tile work grows with projected footprint, not only primitive count. Prefix sums and reference emission must detect overflow before writing. Configure a maximum scratch allocation. On overload, reduce the next frame's selected work, use a safe fallback for affected tiles, or fail a strict cinematic frame explicitly; never silently drop arbitrary references or write out of bounds.

### 7.4 Backend strategy

| Backend | Role |
|---|---|
| Sorted instanced quads | First correct GPU prototype; useful compatibility path and A/B baseline |
| Tiled compute | Main production candidate: early termination, bounded tile work and shared per-view compositing |
| Mesh shaders | Optional experiment only if measured gains justify a capability-specific path |
| Stochastic point renderer | Later massive-scene research; independent quality/convergence contract |
| Ray-traced Gaussian renderer | Later camera/secondary-ray work; not required for GPU acceleration |

Prefer UE-owned resources. Avoid CUDA-to-DX12 interop, separate graphics contexts and per-frame CPU readback. Async compute is a measured scheduling option, not a promised speedup: shared GPU bandwidth, graphics dependencies and barriers can erase its benefit.

### 7.5 Stochastic research gate

Evaluate an HLSL/RHI implementation of the 2026 point-sampling approach only after the deterministic pipeline is usable. Measure noise at fixed time, convergence after camera cuts, ghosting on animated subjects, thin-feature retention and image error at fixed GPU time. Deterministic random seeds must be keyed to view/sample/primitive identity.

Probe the exact 64-bit atomic operation and resource binding needed. Shader-model support alone does not guarantee every typed-resource atomic feature. A failed capability probe falls back to deterministic rendering. [Microsoft SM6.6 atomic capabilities](https://microsoft.github.io/DirectX-Specs/d3d/HLSL_SM_6_6_Int64_and_Float_Atomics.html)

The upstream research code uses CUDA; its throughput does not prove that a portable UE shader port will achieve the same results. A paper technique and its implementation/dependencies require separate license review.

## 8. UE integration and image quality

### 8.1 First integration prototype

Make a tiny synthetic splat cloud render into a real UE 5.8.2 view before building the full importer. Verify public API availability, scene-color format, pre-exposure, opaque depth, view rectangles, resource lifetimes and packaged operation. Keep all version-sensitive calls behind `AbuM53UE58Bridge`.

Read-only inspection of the installed engine found public scene-view extension entry points, including `PostRenderBasePassDeferred_RenderThread`, `PrePostProcessPass_RenderThread`, and the current view-aware `SubscribeToPostProcessingPass`. The public post-opaque callback exposes color/depth/velocity resources. Exact declarations must still be compiled against the selected build. [Epic scene-view extension guide](https://dev.epicgames.com/community/learning/knowledge-base/0ql6/unreal-engine-using-sceneviewextension-to-extend-the-rendering-system), [post-opaque parameters](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/RenderCore/FPostOpaqueRenderParameters)

In the inspected 5.8.2 deferred renderer, the post-opaque extension executes after a fog stage and underwater translucency, before later general translucency. It is therefore not a universal insertion point for correct fog/water/glass interaction. The public callback also does not expose an HZB handle. Avoid dependencies on private `FViewInfo` fields or copying engine-private source into the plugin.

Start with frustum culling and ordinary opaque depth occlusion. If occlusion culling provides a measured benefit, build a conservative depth pyramid from an accessible depth texture. Handle reversed-Z, view subrects, camera cuts and incomplete depth. Translucent splats must not automatically become opaque occluders.

### 8.2 Two explicit color/rendering profiles

**Source Appearance** preserves the source reconstruction, blend space, ordering, filtering and intended display transform. Its definitive reference is a rendered image against a known background. Perform nonlinear source-domain blending before conversion. Combining a nonlinear source result with an arbitrary UE background cannot generally be represented exactly by simply converting a premultiplied RGBA layer.

For exact source-appearance preview, compose against a defined background in the source domain, then transform the resolved image for display. A viewport implementation can use an appropriately placed final composite, with its effects limitations documented. Mixing assets with incompatible blend domains requires explicit conversion to a common approximate profile or separate reference previews; the common global sorter alone cannot solve this.

**UE Scene Integration** maps appearance into UE's working scene color and exposure pipeline and permits the supported post effects. It is an intentional artistic interpretation of display-referred captures, not a promise of source-viewer pixel identity. Test conversion order, pre-exposure, HDR output and tone mapping to avoid double exposure or double transfer conversion.

Khronos explicitly requires compositing in the reconstructed color space before transfer/gamut conversion; its display-referred splats are not automatically scene-linear radiance. [Specification color and image-state requirements](https://raw.githubusercontent.com/KhronosGroup/glTF/main/extensions/2.0/Khronos/KHR_gaussian_splatting/README.md)

### 8.3 Depth, temporal reconstruction and effects

| Feature | Initial behavior | Qualification required |
|---|---|---|
| Opaque meshes in front of splats | Depth-aware clipping | Pixel/footprint tests against mesh edges and intersecting surfaces |
| Splats in front of opaque meshes | Alpha composite | Correct source/working color profile and depth convention |
| Other transparent objects | Supported ordering cases only | General interleaving with UE translucency is not solved by actor sorting |
| Fog and water | Explicitly documented limitations | Chosen hook must prove correct ordering; otherwise feature remains unsupported |
| TSR/TAA | First use conservative color-only integration | Representative splat depth/velocity must be available before the appropriate consumer and tested |
| Motion blur / DOF | Shutter sub-sampling for motion blur; separate lens-sampling research for DOF | Native post-effect support needs justified representative depth and motion |
| Lumen, shadows, collision | Optional artist-provided proxy geometry | A splat field does not automatically provide engine geometry services |
| Path Tracer | No initial native support | Requires a distinct rendering/integration solution |
| SceneCapture / orthographic views | Explicit capability tests | Special projection and history behavior; reject unsupported profile combinations |

Store current/previous positions for tracked dynamic splats, and invalidate history on seek, topology changes, camera cuts and representation changes. A single representative velocity cannot encode all transparent layers. Do not claim TSR support merely because the callback exposes a velocity texture. If using a plugin-owned temporal resolve, test interaction with UE's later temporal processing. [Epic TSR documentation](https://dev.epicgames.com/documentation/unreal-engine/temporal-super-resolution-in-unreal-engine?lang=en-US)

### 8.4 Large worlds and transforms

Keep CPU world/chunk origins in double precision, with local/camera-relative float32 GPU positions. Convert source units to UE centimeters once and retain the original coordinate profile. Test origin rebasing and very large translations. Preserve SH orientation by transforming the viewing direction into the original basis or correctly rotating the coefficients, including handedness conventions. [Epic large-world coordinates](https://dev.epicgames.com/documentation/unreal-engine/large-world-coordinates-in-unreal-engine-5)

## 9. 4D playback implementation

### 9.1 Timing model

Use rational frame/time values at the public playback boundary and double-precision seconds for evaluation where needed. Avoid accumulating animation time by repeatedly adding a float delta. Source timestamps can be nonuniform and need not match UE frame rate.

Define all edge cases: inclusive/exclusive clip endpoints, reverse playback, loop wrapping, ping-pong, zero-duration samples, missing frames and out-of-range seeking. Each requested sample gets a generation ID. Late I/O completions for an old seek must not overwrite a new playback position.

Two scheduling policies:

- **Real time:** preserve the clock and show the latest ready sample, reporting dropped/missing samples; optionally let the user choose slower playback that preserves every frame.
- **Cinematic:** obtain the exact requested time, wait off the real-time path for all needed data, and fail visibly if unavailable. No automatic frame skipping or LOD reduction.

### 9.2 Independent frames

Decode/cache current and next frames, plus a bounded reverse/seek cache. Swap frames at their actual timestamps. Equal point counts do not establish correspondence: permuting two same-size frames must not produce erroneous interpolation.

Sample-and-hold is the accurate default for independent captures. Optional image crossfade is a labeled approximation that can ghost and nearly double rendering work. No fabricated motion vectors are generated from index-matched points.

### 9.3 Stable-ID tracks

Within a declared topology epoch, interpolate position, log scale, opacity in the declared domain, and normalized shortest-path quaternion rotation. Interpolate appearance only when the source model permits it. Store birth/death intervals explicitly, with a specified visibility envelope.

Bake adaptive temporal samples by measuring image error and motion curvature, rather than choosing one arbitrary sampling rate for every clip. Use bounded keyframe/delta chains with random-access anchors. A converter must preserve sufficient appearance data; it must not silently replace a time-dependent feature decoder with RGB.

### 9.4 Native 4D Gaussian adapter

For a supported XYZT Gaussian model, import a 4D mean and symmetric covariance, or convert its documented SO(4) representation into them. Partition covariance into spatial and temporal blocks:

```text
mu_x_given_t = mu_x + Sigma_xt / Sigma_tt * (t - mu_t)
Sigma_x_given_t = Sigma_xx - Sigma_xt * Sigma_tx / Sigma_tt
```

The temporal opacity kernel and time-dependent appearance follow the specific producer's model. Validate positive temporal variance and positive-definite conditional covariance. Compare an original scalar CPU implementation with the GPU across support endpoints and interior times. A pair of quaternions for SO(4) is not automatically the rigid-transform dual quaternion used in skeletal animation. [Native 4DGS paper](https://arxiv.org/abs/2310.10642)

### 9.5 Neural deformation and feature-based formats

Do not deserialize executable `.pth`/pickle checkpoints in the UE importer. A safe tensor container still needs an explicitly supported architecture, normalization, time mapping and decoder. For v1, a user-operated exporter in the model's own authorized environment bakes to the documented interchange format. The plugin then reads data only.

Direct GPU neural inference, if later justified, needs a separate model/operator whitelist, numerical parity suite, inference memory budget and independently reviewed dependencies. A single PLY from a canonical-plus-deformation model is not enough to reconstruct its animation. [4DGaussians method](https://guanjunwu.github.io/4dgs/), [Spacetime Gaussian Feature Splatting paper](https://openaccess.thecvf.com/content/CVPR2024/papers/Li_Spacetime_Gaussian_Feature_Splatting_for_Real-Time_Dynamic_View_Synthesis_CVPR_2024_paper.pdf)

### 9.6 Sequencer and Movie Render Queue

Implement time remapping, offset, rate, loop range and exact scrubbing. Sequencer evaluation supplies absolute time; the renderer must not depend on editor tick history. Separate track-editor UI from runtime evaluation code.

For Movie Render Queue: lock LOD/residency, wait for precise temporal samples, evaluate each shutter sub-sample, support warmup and deterministic seeds, and maintain full-frame projection when producing high-resolution tiles. Validate temporal sampling at loop boundaries and camera cuts. Cinematic mode may take longer than real time and must report incomplete frames rather than substitute lower-quality content.

Shutter/time samples address motion blur; they do not automatically create depth of field. Cinematic DOF requires aperture/lens-position sampling with the corresponding camera projection, or a separately validated UE depth-based path. Keep DOF unsupported until that dedicated test passes.

## 10. High-count streaming, LOD and memory management

### 10.1 Spatial hierarchy

Build a deterministic spatial hierarchy over source splats, with local origins, conservative bounds and explicit representative error. A Morton ordering plus clustered hierarchy is an initial construction candidate. Distinguish small culling clusters from larger compressed I/O pages.

Start tuning with roughly 128–512 splats per culling cluster and 256 KiB–2 MiB compressed data pages. These are experiment ranges, not format requirements. Large splats crossing node boundaries must retain conservative support bounds.

Use projected error, view coverage, opacity and a shared per-view budget when selecting LOD. Add hysteresis to prevent camera-motion flicker. Do not repeatedly draw parent and child opacity at full strength during transitions. Preserve fine details where approximation error is high.

Trained hierarchical representations can offer excellent results, but a naive merge or random subsample of arbitrary PLY data does not inherit those guarantees. First deliver full-detail streaming; then qualify representative generation with image comparisons. Simple moment matching may initialize a representative, but does not prove equivalent alpha compositing. [Hierarchical Gaussian research](https://repo-sam.inria.fr/fungraph/hierarchical-3d-gaussians/hierarchical-3d-gaussians_low.pdf)

### 10.2 Residency and scheduling

- Maintain separate disk, decoded CPU, staging-upload and GPU cache budgets.
- Reserve space for UE textures, meshes, transient render targets and other plugins; never consume all adapter VRAM.
- Prefetch using camera direction, current motion and requested sequence time. Reprioritize on camera cuts and seeks.
- Pin coarsest fallback data so a missing detail page does not create arbitrary holes.
- Evict only after GPU fences prove no queued work references the resource.
- Use reusable upload rings and pooled buffers; avoid per-frame allocation churn.
- Build compatible cooked bulk-data/IoStore integration so packaged assets do not depend on original absolute source paths.
- Permit runtime external-file import as a separately controlled feature; ordinary playback uses cooked validated data.

A future World Partition adapter registers Abu M53 chunk groups or proxy actors. It is not automatic Nanite integration, and it must avoid double-counting hierarchy representations.

### 10.3 Memory arithmetic

For the illustrative 128-byte SH3 resident representation:

| Resident splats | Attribute memory, decimal | Attribute memory, binary |
|---:|---:|---:|
| 1 million | 128 MB | 0.119 GiB |
| 5 million | 640 MB | 0.596 GiB |
| 10 million | 1.28 GB | 1.192 GiB |
| 50 million | 6.40 GB | 5.960 GiB |
| 100 million | 12.80 GB | 11.921 GiB |

These values exclude all rendering overhead. A useful planning equation is:

```text
GPU bytes = resident attributes
          + active projected attributes
          + double-buffered sort references
          + visibility / hierarchy / indirect buffers
          + dynamic current/previous/next state as required
          + color / depth / motion / history targets
          + allocator and safety headroom
```

Example: 5M resident splats at 128 bytes, 5M projected records at an assumed 64 bytes, and 40M tile references with two 16-byte sort buffers require **2.24 GB** before other resources. At 40 rather than eight tile references per splat, sort storage alone rises to **6.4 GB**. Tile-reference overflow is therefore a first-class engineering problem.

Independent animation is also bandwidth-heavy: one million 128-byte records at 30 source frames/s is **3.84 GB/s** of decoded attributes; five million is **19.2 GB/s**. Disk compression does not remove decoded memory traffic. Stable tracks, selective attribute updates, visible-page streaming and GPU unpacking are necessary optimization candidates. None of these estimates is a measured performance result.

### 10.4 Dynamic bounds

Use conservative swept bounds per temporal segment. If analytic bounds are unavailable, bake sampled bounds with a justified expansion or subdivide the segment. Bounds that ignore deformation can cull visible moving subjects. Temporal support rejection should happen before expensive deformation and projection where possible.

## 11. GPU-first execution and CPU fallback

### 11.1 Capability ladder

| Level | Work placement | Intended use |
|---|---|---|
| A — full GPU | GPU visibility, evaluation, projection, sort and raster; CPU I/O/decode | Default on certified DX12 devices |
| B — simpler GPU path | Generic compute without optional wave/atomic features, plus quad draw | Capability/driver fallback, often still fully GPU sorted |
| C — CPU assisted | CPU jobs evaluate/cull/sort a reduced set; GPU draws | Explicit diagnostic or limited-device option |
| D — software | CPU SIMD/tiled projection and blending; final image displayed through UE | Low-budget preview, reference validation and offline rendering |

Query real RHI capabilities and run shader smoke tests. Vendor name alone does not prove support. Compile generic and optimized variants; do not assume one fixed wave size. SIMD CPU paths require runtime dispatch with a scalar baseline.

GPU memory pressure should first reduce residency and selected work. Moving a massive workload to CPU does not automatically solve performance. A GPU device-loss event may require engine recovery or restart; do not promise seamless CPU takeover after the graphics device has failed.

### 11.2 What the CPU renderer must actually do

Implement the same importer, projection, source-profile sorting and compositing in independent CPU code. Assign complete tiles to workers to avoid pixel write races. Cache projected data, vectorize footprint evaluation, bound per-tile memory and support cancellation. Start interactive preview with conservative limits, such as 50,000 selected splats at 720p, then expose measured device-dependent recommendations. This is an initial cap, not a guaranteed FPS.

CPU rendering remains slower at high counts. Full-fidelity offline CPU rendering can run without a real-time target. Showing the resulting image in a UE viewport still normally requires a functioning display RHI; an importer or standalone reference tool can run headless without claiming that the full UE viewport is CPU-only.

### 11.3 Division of CPU/GPU work

Keep ordinary file I/O, validation and many decompression tasks on CPU workers unless profiling proves GPU decode beneficial. Use GPU unpack/interpolation for layouts designed for it. Never offload a small task just to label it hardware accelerated if synchronization costs exceed the work. The key metric is total frame latency and image quality.

## 12. Quality presets and performance targets

### 12.1 Presets

| Preset | Contract |
|---|---|
| Source Fidelity | Preserve source SH, precision/profile and supported sampling conventions; disable budget-driven LOD changes; prioritize correspondence with reference images |
| Real Time High | Full available SH where affordable, validated compact storage, spatial filtering, stable LOD and bounded tile work; expose every quality reduction |
| Performance | More aggressive projected-error threshold, optional lower SH bands and lower internal resolution; report active settings |
| Cinematic | Exact time, locked residency/LOD, deterministic samples, high precision and optional supersampling; no FPS guarantee |
| CPU Preview | Reduced working set/resolution, with explicit fallback indicator and measurable limits |

Switching preset must not overwrite the preservation asset. Upscaling is an optional presentation/performance choice; report internal resolution and do not use generated frames to imply a higher native rendering rate.

### 12.2 Proposed engineering targets — not promises

Freeze actual reference PCs, driver versions and benchmark scenes in Phase 0. Use an upper-tier 16–24 GB DX12 GPU as the initial performance tuning machine and separate NVIDIA/AMD/Intel machines for correctness and scaled performance. VRAM capacity alone does not define a performance class.

| Workload | Initial stretch target | Conditions |
|---|---|---|
| Static 2M active SH3 | Plugin GPU cost ≤4 ms; minimal-scene total ≤8.33 ms | 1080p native, defined moderate-overdraw camera path; candidate 120 FPS workload |
| Static 5M active SH3 | Plugin GPU cost ≤10 ms; minimal-scene total ≤16.67 ms | 1080p native, reference GPU, measured bounded tile count |
| Large static 100M source | ≤5M selected, ≤configured residency budget, total target 60 FPS | Streamed LOD workload; not 100M simultaneous full-detail rendering |
| Dynamic 1M active | Plugin GPU cost ≤8 ms; total target 60 FPS | 30 Hz baked source, 1080p native, warm cache; includes temporal evaluation |
| Dynamic independent frames | Publish supported count/rate after I/O measurements | No unconditional multi-million-splat stream-rate promise |
| CPU software | Correct images and bounded memory; publish actual FPS | No parity promise with high-count GPU performance |

Use p95 timings for target decisions, not a best-case single frame. These are deliberately ambitious targets to accept or revise after the first complete pipeline. A missed target triggers profiling and a recorded design decision, not a silent reduction in fidelity or a fabricated claim. At 4K, stereo, high overlap or with a heavy UE scene, different limits apply.

### 12.3 Initial per-frame allocation objective

For the 5M-active/60-FPS prototype, investigate an approximate 10 ms plugin GPU budget: 1.5 ms selection/evaluation, 1.5 ms projection/binning, 3 ms sorting, 3.5 ms compositing and 0.5 ms resolve. This is a profiling hypothesis, not evidence that those costs are attainable. Keep game-thread work below approximately 0.5 ms and plugin render-thread submission below approximately 1 ms on the nominated reference CPU, excluding editor import operations.

## 13. User workflow and diagnostics

### 13.1 Import workflow

1. Choose a file or sequence manifest.
2. Inspect detected type, version, SH degree, frame count, estimated memory and warnings.
3. Confirm the coordinate/color preset only if source metadata is ambiguous.
4. Choose preservation plus a derived runtime preset and destination asset.
5. Import asynchronously with progress and cancellation.
6. Review the asset against a checker/background and orientation gizmo.
7. Place an `Abu M53` actor and choose quality/playback settings.

Use clear labels such as “Source splats,” “Visible splats,” “GPU memory,” “Splat render time” and “Animation frames missed.” Expose technical details in an expandable diagnostics panel. Show specific reasons for unsupported imports; avoid a generic “bad PLY” error.

### 13.2 Asset and actor controls

Provide transform, crop box, opacity/intensity adjustment, visibility, memory budget, quality preset and time controls. Record artistic appearance changes separately from source data. Include bounds, SH-only/DC-only, tile heatmap, residency, LOD, motion and error visualizers for diagnosis.

### 13.3 Data/error behavior

Define stable error codes: unsupported schema, missing Gaussian attributes, invalid covariance, incomplete sequence, decompression limit, unavailable page, GPU budget exceeded and unsupported backend. Logs identify file/chunk/frame and corrective action, without dumping entire assets or user data. Runtime failures should preserve the last valid frame or coarse representation where possible.

## 14. Verification strategy

### 14.1 Numerical and image correctness

- Generate original analytic scenes: one anisotropic Gaussian, intersecting Gaussians, SH lobes, nearly transparent layers, tiny splats, large splats and near-plane crossings.
- Compare CPU/GPU projection, covariance, opacity activation and SH evaluation using scale-aware absolute/relative tolerances.
- Compare matched source-profile images before adding quantization, LOD or artistic color conversion.
- Verify camera rotation, actor rotation, mirrored coordinate imports, nonuniform scale and large-world origin shifts.
- Test all actors in one scene, including mutually intersecting splat fields.
- Test opaque geometry intersections, supported translucency cases, exposure, HDR output and alpha backgrounds.

Proposed initial image gates for synthetic deterministic profiles: CPU/GPU float32 parity with relative numerical errors around `1e-4` where well-conditioned; compare images using RMSE/PSNR/SSIM plus localized error maps. Do not impose that relative threshold near zero without an absolute floor. Lock exact tolerances per operation after measuring baseline cross-vendor variation.

For lossy derived modes, begin with candidate gates of **≤0.2 dB PSNR reduction** and **≤0.002 SSIM reduction** from the matched preservation rendering, measured against the same licensed reference views. Also inspect thin geometry, hair, edges and reflections. These are tuning goals, not universal perceptual guarantees; source loss is measured separately from Abu M53's added loss.

### 14.2 Temporal correctness

Test stable IDs, shuffled equal-count frames, changing counts, births/deaths, nonuniform timestamps, reverse playback, random seeks, loop boundaries and fractional-frame cinematic samples. Measure flicker, popping and ghost trails on camera-motion and object-motion sequences. A good static PSNR score does not establish temporal quality.

Reject stale async completions after a newer seek. Repeated deterministic capture of the same sample must match within the documented precision tolerance. Test camera cuts with cold/warm streaming caches and missing detail pages.

### 14.3 Robustness and parser security

Fuzz portable parsers and the container independently of UE. Test truncated data, huge counts, malformed lengths, corrupt checksums, ZIP traversal, decompression bombs, cyclic indices, NaN/Inf, invalid quaternions and unsupported extensions. Verify bounded memory and clean cancellation on 10M–100M-source files.

Never execute embedded code or install tools from an input file. Cover Unicode/space/long paths and non-English number locales. Import should not destroy a previous valid asset if reimport fails.

### 14.4 Engine/platform matrix

| Axis | Required v1 coverage |
|---|---|
| Engine | Exact UE 5.8.2 build; additional 5.8 patch versions only when separately tested |
| GPU | At least one supported NVIDIA, AMD and Intel DX12 adapter, with documented drivers |
| CPU | Scalar baseline and at least one SIMD path; thread counts and cancellation |
| Targets | Editor Development, packaged Development and Shipping |
| Views | Editor viewport, PIE, standalone, SceneCapture when advertised, MRQ when advertised |
| Lifecycle | Load/unload, repeated PIE, asset removal, world teardown, resize, device capability downgrade |
| Resources | Low memory, oversized splats, maximum scratch demand, cold cache, interrupted reads |

Vulkan/Linux, DX11, mobile, macOS/Metal, consoles, XR and nDisplay are not implicitly supported by success on Windows DX12. Add them only with dedicated certification.

## 15. Benchmark protocol and reporting

Use original or redistribution-cleared scenes with three density patterns: low overlap, realistic capture, and adversarial high overlap. Include 1M/5M/10M active tests, a larger streamed source, a thin-feature scene, and both tracked and independent-frame animation. Use identical camera/time paths across builds.

For each run, record:

- Plugin commit, engine build, compiler, GPU/VRAM, driver, CPU, RAM and storage.
- Source counts, unique finest-level count, resident/active/visible counts and tile-reference counts.
- Source format/profile, SH degree, precision, filter, cutoffs, LOD threshold and backend.
- Output/internal resolution, upscaler, VSync/frame cap, view count and post effects.
- CPU import/decode/upload/scheduling time and GPU pass timings.
- Total frame p50/p95/p99, native FPS, time-to-first-image, seek latency and missing samples.
- Peak resident/transient VRAM, system RAM, I/O bandwidth and upload bandwidth.
- Quality metrics and paired images/video for the exact performance preset.

Warm the shaders and steady-state cache before the normal run, and report cold-start runs separately. Use at least three repeated 60-second camera-path runs with disclosed warmup. Report both a minimal UE scene and a representative production scene; show the scene's cost without splats. Do not subtract overlapping GPU timings as though they were necessarily additive.

Use Unreal Insights and GPU timing markers; use PIX or vendor profilers when investigating a bottleneck. Export machine-readable CSV/JSON and a Markdown report. Store public reports with scene/license identifiers so others can reproduce them without downloading private captures.

## 16. Implementation phases, staffing and acceptance gates

Estimated effort assumes an experienced UE rendering engineer, a C++ formats/streaming engineer and part-time QA/technical art. Calendar estimates are planning ranges, not commitments. A solo developer should expect substantially longer. Native neural 4D support, unrestricted translucency integration and new platforms are not hidden inside the v1 estimate.

| Phase | Approximate duration | Concrete deliverable and exit gate |
|---|---:|---|
| 0 — requirements and evidence freeze | 1 week | Select exact PCs/builds, own test assets, format revisions and dependency policy; open Engine Tools classification review; no unsupported legal/performance promises |
| 1 — UE integration and core math spikes | 2 weeks | Synthetic splats in editor and packaged UE5.8.2 using public APIs; CPU reference; record color/depth/fog/temporal feasibility |
| 2 — static import and basic GPU | 2–3 weeks | PLY/.splat parser, source report, actor, stable quad renderer, full SH and transform tests; release candidate v0.2 |
| 3 — tiled renderer and quality | 3–4 weeks | Per-view multi-actor tiling/sort, bounded scratch, filtering, cross-vendor parity and initial timings |
| 4 — cooked data and large-scene streaming | 3–4 weeks | SPZ versions, `.am53`, CPU/GPU caches, cancellation, packaged bulk data, full-detail streaming then validated LOD; candidate v0.4 |
| 5 — animated core and Sequencer | 3–4 weeks | Independent frames, stable-ID tracks, `.am53seq`, exact time, seeking, MRQ gate, existing AbuAlign manifest adapter; candidate v0.6 |
| 6 — CPU fallback and optimization | 2–3 weeks, partly parallel | Software renderer, capability selector, CPU-assisted path; bottleneck-driven optimization and overload behavior |
| 7 — beta, legal/package review and release | 2–3 weeks | Cross-vendor soak tests, source/binary audit, permitted publication route, complete docs and benchmark evidence; v1.0 |

Allow roughly **18–24 calendar weeks** with the stated team and overlapping work, plus contingency if engine integration or legal classification changes the distribution plan. Re-estimate after Phase 1 rather than treating the table as a fixed deadline.

### 16.1 Follow-on work packages

| Package | Scope | Required evidence before release |
|---|---|---|
| Interchange expansion | Compressed PLY, SOG, KSPLAT, glTF and GSD | Exact version fixtures, per-file license audit and quality reports |
| Native analytic 4D | XYZT conditioning, spacetime tracks and supported appearance decoders | Full model-specific CPU/GPU parity and temporal output tests |
| Massive-scene backend | Stochastic rendering, improved hierarchy, optional mesh shaders | Equal-time quality comparison, dynamic stability and capability fallback |
| Production integration | Better depth/motion/fog/translucency, XR, nDisplay | Explicit supported cases and per-view performance |
| Additional platforms | Vulkan/Linux first; others separately | Build, shader, streaming and image parity on actual hardware |
| Neural inference / RT | Direct deformation models, special cameras, reflections | Independent design, licenses, operators, acceleration structures and performance budget |

### 16.2 First implementation backlog

1. Create repository skeleton and original-code license/notice/provenance records.
2. Freeze small source-profile fixtures and analytic image oracles.
3. Build portable core and scalar covariance/SH/activation math.
4. Implement strict PLY reader and bounded source inspection.
5. Create UE descriptor/modules, early shader registration and version bridge.
6. Render a synthetic cloud through the public-hook prototype.
7. Demonstrate source-appearance preview and documented UE integration mode.
8. Add asset/component registration, resource lifetime and multi-view isolation.
9. Implement stable GPU sort and quad path, with multi-actor correctness.
10. Add per-pass profiling before optimizing.
11. Implement tiled count/scan/emission/sort/composite with overflow tests.
12. Add importer/reimport UI and packaged cook tests.
13. Add SPZ and container/index/caches.
14. Add independent-frame and stable-ID playback plus Sequencer.
15. Implement CPU capability fallback and formal benchmark runs.
16. Complete release/license review and publish only the approved artifact set.

## 17. Open-source licensing and GitHub publication

### 17.1 What this research can establish

The recommended structure is intended to permit open-source and commercial reuse of **original Abu M53 code**. It is not a certification that future implementation files, every input asset, every jurisdiction or the complete UE tool distribution are restriction-free. Final review must examine the actual source, dependencies and release archives. No repository was created or published during this research.

Use **Apache-2.0** for original code and documentation unless a document needs a separately stated license. Preserve adopted code's original licenses and notices. Apache's contributor patent grant is useful but limited; it does not clear unrelated patents or grant trademark rights. [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)

### 17.2 Unreal rules that affect the plan

Epic retains rights in its Licensed Technology. Engine Code redistribution is limited; public Engine Tools distribution is directed to Fab or Epic's UnrealEngine GitHub network. The Engine Tools definition includes specified Editor/Developer code and a broader tools category. Source-only distribution is not an automatic exemption. The EULA also restricts incompatible licensing, including GPL and CC-BY-SA, with a stated LGPL dynamic-linking exception. Seat, royalty and content obligations remain separate. [Unreal EULA, §§1, 3–7](https://www.unrealengine.com/eula/unreal)

Epic's GitHub FAQ identifies MIT, BSD and Apache as acceptable non-copyleft examples. This supports Apache for original integration code; it does not relicense Unreal itself. [Epic GitHub FAQ](https://www.unrealengine.com/ue-on-github?lang=en-US)

**Project release decision:** obtain a written assessment from qualified counsel and/or clarification from Epic for the actual importer/editor functionality and package. Independently authored editor code should not be presumed either prohibited or exempt solely because its module is named Editor. Record the conclusion and the permitted publication channel before releasing that component.

### 17.3 Dependency allow/review/exclude table

“Candidate” means eligible for audit. It does not mean every file or dependency has already been approved for Abu M53. The links below are current research references; the implementation must pin immutable commits and package hashes.

| Component | License evidence | Project decision |
|---|---|---|
| Own core, shaders, tests, converter | Newly authored work with contribution rights | Apache-2.0; original implementations and clear provenance |
| Niantic SPZ | MIT | Candidate codec; retain notices and audit zlib/Zstandard integration |
| zlib | zlib license | Candidate required legacy codec; record exact version and license |
| Zstandard | BSD license option | Candidate; explicitly select the permissive option and retain notices |
| libdeflate | MIT-style license | Optional candidate if measured gzip throughput justifies another dependency |
| libwebp | Permissive license and separate patent terms | Candidate SOG decoder; preserve applicable license/patent notices and audit dependencies |
| PlayCanvas engine / splat-transform | MIT roots | Format/tooling reference; audit copied portions and transitive packages |
| GaussianSplats3D / antimatter15 splat | MIT roots | Candidate static format references; preserve notices for adopted code |
| gsplat | Apache-2.0 root, dependencies separate | External QA/reference candidate; no mandatory runtime PyTorch/CUDA |
| NVIDIA 3DGRUT / Vulkan sample | Apache-2.0 roots, third-party inventory separate | Optional research/reference; audit selected files and SDK redistribution terms |
| Gaussian Point Splatting | BSD-3-Clause root | Research candidate; audit bundled packages before any port/reuse |
| YaGS | Apache-2.0 plus third-party notices | Candidate selective reference after audit; not a pre-verified 5.8 base |
| Graphdeco 3DGS and rasterizer | Research/noncommercial restrictions | Exclude from the permissive plugin, including translated code and compiled extensions |
| Mip-Splatting reference | Follows original 3DGS terms | Research mathematical ideas; do not copy its implementation |
| StopThePop | Mixed licensing; majority restricted, certain components separately permissive | No wholesale reuse; independently implement or audit specifically permissive files |
| HUST / Fudan 4DGS repositories | Permissive root licenses coexist with restricted components/headers | No wholesale reuse; independently implement data adapters and model mathematics |
| OpenSplat4D | Apache root plus explicit restricted training and native-4D shader disclosures | Exclude as a wholesale foundation; removing training code alone is insufficient |
| Dazai SplatRenderer | Apache root; examined package lacks complete C++ source | Behavior/format comparison pending source completeness and provenance review |
| GPL/AGPL code | Permits commercial use, but brings copyleft obligations and UE compatibility concerns | Exclude under this project's permissive dependency policy |
| Research-only, noncommercial or unknown code | Commercial freedom absent or unresolved | Exclude from shipped plugin unless separately licensed and reviewed |

Primary license evidence:

- [SPZ MIT](https://raw.githubusercontent.com/nianticlabs/spz/main/LICENSE), [zlib license](https://zlib.net/zlib_license.html), [Zstandard BSD option](https://raw.githubusercontent.com/facebook/zstd/dev/LICENSE), [libdeflate license](https://raw.githubusercontent.com/ebiggers/libdeflate/master/COPYING), [libwebp license](https://chromium.googlesource.com/webm/libwebp/+/refs/heads/main/COPYING), [libwebp patent terms](https://chromium.googlesource.com/webm/libwebp/+/refs/heads/main/PATENTS).
- [PlayCanvas splat-transform MIT](https://raw.githubusercontent.com/playcanvas/splat-transform/main/LICENSE), [PlayCanvas engine MIT](https://raw.githubusercontent.com/playcanvas/engine/main/LICENSE), [GaussianSplats3D MIT](https://raw.githubusercontent.com/mkkellogg/GaussianSplats3D/main/LICENSE), [antimatter15 MIT](https://raw.githubusercontent.com/antimatter15/splat/main/LICENSE).
- [gsplat Apache](https://raw.githubusercontent.com/nerfstudio-project/gsplat/main/LICENSE), [3DGRUT attributions](https://github.com/nv-tlabs/3dgrut/blob/main/ATTRIBUTIONS.md), [NVIDIA sample Apache](https://raw.githubusercontent.com/nvpro-samples/vk_gaussian_splatting/main/LICENSE), [Gaussian Point Splatting BSD](https://raw.githubusercontent.com/JorisAR/gaussian-point-splatting/main/LICENSE), [YaGS notices](https://raw.githubusercontent.com/yandex/yags/main/NOTICES).
- [Graphdeco license](https://raw.githubusercontent.com/graphdeco-inria/gaussian-splatting/main/LICENSE.md), [rasterizer license](https://raw.githubusercontent.com/graphdeco-inria/diff-gaussian-rasterization/main/LICENSE.md), [Mip-Splatting license](https://github.com/autonomousvision/mip-splatting/blob/main/LICENSE.md), [StopThePop license inventory](https://github.com/r4dl/StopThePop).
- [HUST root license](https://raw.githubusercontent.com/hustvl/4DGaussians/master/LICENSE.md) and [restricted file header](https://raw.githubusercontent.com/hustvl/4DGaussians/master/scene/gaussian_model.py), [Fudan separate restricted license](https://raw.githubusercontent.com/fudan-zvg/4d-gaussian-splatting/main/LICENSE_gaussian_splatting.md), [OpenSplat4D disclosures](https://github.com/YuanBaoSMadLab/OpenSplat4D/blob/main/THIRD-PARTY-LICENSES.md), [Dazai package tree](https://github.com/DazaiStudio/SplatRenderer-UEPlugin/tree/master/SplatRenderer).

### 17.4 Implementation provenance rules

Write requirements and mathematical derivations from publications/specifications, then author the C++/HLSL implementation. Do not translate restricted CUDA line by line, copy it through an intermediate project, or treat generated code as exempt from provenance requirements. Independently authored implementations and adopted permissive code must be identified honestly; do not label the entire project a formally clean-room implementation without the process to support that claim.

For every adopted dependency/file, record repository URL, commit hash, file path, license, changes, required notices, dependency tree and whether it ships at runtime. Review pull requests for contribution rights and require a DCO-style sign-off or other appropriate contributor agreement. Run a license/provenance scan and human review; a scanner cannot resolve contradictory grants by itself.

### 17.5 Data, patents and branding

Maintain separate rights records for code, trained weights, captures, exported scenes, audio, logos and demonstration media. A permissive decoder does not grant ownership of a scene. Conversely, do not assume a code restriction necessarily attaches to all numerical outputs: review the actual data/model/export terms. Use original synthetic fixtures and rights-cleared captures for public examples.

Use MetaHuman-derived or other licensed-content fixtures only after verifying applicable content, training and output terms; private use alone does not establish permission. Do not automatically bundle such captures as permissive sample assets. Native model checkpoints are not needed in the repository.

An independent implementation reduces code-copying risk, but patents are a separate question. No worldwide freedom-to-operate search or trademark clearance for “Abu M53” was completed. Before a commercial branded release, commission a scope-appropriate review and use Unreal's name only to describe compatibility without implying endorsement. [USPTO distinction between rights](https://www.uspto.gov/trademarks/basics/trademark-patent-copyright), [USPTO patent rights](https://www.uspto.gov/patents/basics/manage)

### 17.6 Concrete publication path

1. **Prepare a public independent core:** original portable parsers, container specification, converter, math, CPU renderer and synthetic tests, with reviewed permissive dependencies.
2. **Prepare the UE runtime source package:** original integration and shaders, building against the user's separately obtained engine; audit the actual contents and contractual classification.
3. **Resolve the editor/tooling package:** if its distribution falls under Engine Tools restrictions, use a permitted channel for that component. If review clears ordinary GitHub distribution for the proposed artifact, retain the written reasoning and publish under the approved scope.
4. **Build from an allowlist:** include reviewed source, notices, docs and cleared examples. Exclude copied engine headers/source, engine DLLs/libraries, private captures, credentials, caches and restricted research components.
5. **Verify reproduction:** build the portable core without UE; build the plugin on a licensed clean UE install; compare release binaries with the reviewed source and archive manifest.
6. **Publish an accurate statement:** original Abu M53 code is open source under its stated license; Unreal and third-party components retain their own terms. Never advertise blanket legal immunity.

Required release records: `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, `Docs/Legal/Dependencies.md`, `Docs/Legal/Provenance.md`, an SPDX or CycloneDX SBOM, example-asset rights records and an artifact checksum manifest. These are implementation deliverables, not claims that future code has already passed review.

## 18. Risks, decisions and fallback plans

| Risk | Early detection | Response |
|---|---|---|
| Editor distribution cannot use ordinary public GitHub | Phase 0 classification | Preserve public core; use approved tooling channel and disclose the split |
| Hidden restricted code in an attractive dependency | File-level provenance review before adoption | Exclude or replace with original implementation; obtain permission only if necessary |
| GPU performance collapses on overlap | Tile-reference and contribution histograms | Improve culling/LOD, bounded tiling and load distribution; revise supported workload honestly |
| Memory use exceeds device budget | Peak residency/scratch instrumentation | Stream fewer pages, tighten selection, improve layout; strict mode reports inability to render full fidelity |
| 4D source is incomplete or undocumented | Inspect exporter/model/version and required fields | Reject with a precise message or request a supported bake/export |
| Colors differ from source viewer | Matched-background source-profile tests | Correct activation/basis/blending; distinguish intentional UE interpretation |
| Temporal flicker/ghosting | Motion and camera-path video tests | Adjust ordering/filter/LOD history; disable unreliable temporal options |
| Public UE hooks cannot supply an effect | Phase 1 integration prototype | Document unsupported case; optional separately reviewed engine integration later |
| CPU path is too slow for requested scene | Software timing and working-set reports | Lower preview budget or use offline mode; no hidden FPS parity claim |
| Cross-vendor shader failure | Early NVIDIA/AMD/Intel test matrix | Generic shader variant; isolate optional features and driver workarounds |
| Sample assets cannot be redistributed | Rights ledger before adding files | Substitute original synthetic or properly licensed samples |
| Scope expands into training/relighting | Explicit support matrix | Keep separate work packages and estimates |

## 19. Definition of done

### 19.1 v1.0 engineering completion

- [ ] Abu M53 builds and packages on the exact declared UE 5.8.x versions.
- [ ] Each advertised static/dynamic importer has versioned fixtures and clear unsupported-case behavior.
- [ ] Source attributes and rendering conventions survive preservation import.
- [ ] Multi-actor GPU rendering, source appearance and documented UE integration cases pass image tests.
- [ ] NVIDIA, AMD and Intel supported devices pass the published capability matrix.
- [ ] Streaming/LOD obeys hard CPU/GPU budgets and handles scratch overflow safely.
- [ ] Independent-frame and stable-ID animation pass timing, seeking and deterministic capture tests.
- [ ] CPU-assisted and actual software fallback paths are exercised and honestly described.
- [ ] Benchmarks report quality, count definitions, timings and memory for reproducible workloads.
- [ ] Every claimed effect/platform has passed its own integration tests.
- [ ] User docs explain importing, quality tradeoffs, fallback behavior, animation and troubleshooting.

### 19.2 Publication completion

- [ ] Complete source/dependency and example-asset rights inventory exists.
- [ ] Restrictive research components are absent from permissive release artifacts.
- [ ] Apache/MIT/BSD and other retained notices match every adopted file and library.
- [ ] UE runtime/editor distribution classification and permitted route are resolved.
- [ ] The final archive contains no unapproved engine material or private project data.
- [ ] Clean builds and artifact checksums match the published source.
- [ ] Public README states actual compatibility and measured results; it makes no unconditional legal or FPS claims.

## 20. Research provenance and remaining uncertainty

This document combines current primary-source research, read-only inspection of installed UE 5.8.2 metadata/render interfaces, a small local AbuAlign manifest inspection and original engineering proposals. It does not claim that a plugin, benchmark, patent search or legal sign-off already exists.

Research references point to current documentation and upstream branches as observed on 25 October 2026. Before implementation reuse, record immutable revisions and hash the relevant license files; a mutable `main` URL is not a dependency lock. Exact source files, exporter fixtures, GPU timings, optimum tile sizes, LOD error, CPU throughput and several UE effects integrations remain to be measured.

Additional primary references for the implementer:

- [Epic UE 5.8 release notes](https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-5-8-release-notes?lang=en-US).
- [Epic Render Dependency Graph guide](https://dev.epicgames.com/documentation/unreal-engine/render-dependency-graph-in-unreal-engine?lang=en-US).
- [Epic global shader plugin guide](https://dev.epicgames.com/documentation/unreal-engine/creating-a-new-global-shader-as-a-plugin-in-unreal-engine?lang=en-US).
- [PlayCanvas PLY profile](https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/ply/), [SOG specification](https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/sog/), [streamed SOG](https://developer.playcanvas.com/user-manual/gaussian-splatting/formats/streamed-sog/).
- [SPZ current specification](https://raw.githubusercontent.com/nianticlabs/spz/main/README.md), [KSPLAT implementation schema](https://raw.githubusercontent.com/mkkellogg/GaussianSplats3D/main/src/loaders/SplatBuffer.js).
- [Open Source Definition](https://opensource.org/osd), [Apache licensing FAQ](https://www.apache.org/foundation/license-faq.html).

The immediate development action is Phase 0 followed by a small UE rendering prototype: establish source fidelity, legal publication boundaries and measurable GPU costs before investing in the full asset/editor pipeline.



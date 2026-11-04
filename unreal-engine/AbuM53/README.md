# Abu M53

Abu M53 is an Unreal Engine 5.8 plugin under development for importing and rendering static and animated Gaussian splats. The primary platform is Windows DX12, with original C++/HLSL code intended to run across NVIDIA, AMD and Intel GPUs without CUDA.

This is **v0.0.0.4**, a development implementation, not completion of the entire multi-phase v1.0 plan. Consult [validation evidence](Docs/Validation.md), the [milestone/feature status](Docs/ImplementationStatus.md), and [current scope and limits](Docs/CurrentScope.md). A compiled source tree is not proof of every target format, platform or rendering effect.

## Development history and version control

Open **Window → About Abu M53** in the Unreal Editor for the installed version, repository origins and license record. The [full maintained Markdown document](Docs/Legal/Repository_Origins_and_Licensing.md) identifies original, adopted, upstream-informed, linked and research-only work. ChatGPT and Antigravity must update it with code changes; [the reviewed-file checker](Tools/Provenance/provenance.py) is part of source/package/deployment audits and CI.

Read the [implementation walkthrough](Docs/Abu_M53_Implementation_and_Validation_Walkthrough.md), [change history](CHANGELOG.md) and [version workflow](Docs/Version_Control_and_Change_Workflow.md). `VERSION` is authoritative; releases begin at `v0.0.0.1` and carry from `v0.0.0.9` to `v0.0.1.0`.

The [v0.0.0.3 walkthrough](Docs/Import_Editing_and_PLY_Sequence_Walkthrough.md) covers faster PLY import/save, stable Details editing, GPU frame reuse and the verified three-frame 3M-splat Skate sequence. The [release record](Docs/Changes/v0.0.0.3.md) contains measured results and migration requirements.

## Build and use

For an installed Windows plugin and the persistent `abu_M53_Test_01` development project, see [Windows installation and testing](Docs/Windows_Installation_and_Test_Project.md).

1. Place this directory at `YourProject/Plugins/AbuM53`, or create an isolated validation host with `Tools/QA/create_host.ps1`.
2. Build the project/plugin against a licensed UE 5.8.2 installation and its supported Windows toolchain.
3. Enable **Abu M53** and restart the editor if requested.
4. Import a supported Gaussian file into the Content Browser, then place an **Abu M53 Actor** and assign its asset.
5. Set source units and orientation explicitly. The original QA fixtures use UE axes and meters, with `Units To Centimeters = 100`.

The current importer implementation targets common Graphdeco-style Gaussian PLY, the 32-byte `.splat` format, SPZ v1–v4 without extensions, the original Abu M53 container and explicit `.am53seq` frame manifests. Standalone SPZ v1–v3 decoding requires zlib; v4 uses the bundled BSD Zstandard decoder. Verify actual support in the validation record. A point-only PLY, a neural checkpoint and an arbitrary “4DGS” export are not interchangeable formats.

## Animation

An independent-frame sequence uses timestamped frame files; equal point counts do not imply identity correspondence. The QA manifest is a minimal example:

```json
{
  "schema": 1,
  "sequence_type": "independent_3dgs_frames",
  "coordinate_frame": "ue_x_forward_z_up_meters",
  "fps": 30,
  "frames": [
    {"time_seconds": 0.0, "file": "frame_0000.ply"},
    {"time_seconds": 0.03333333333333333, "file": "frame_0001.ply"}
  ]
}
```

The component exposes play, pause and seek controls. Native research-model decoders, direct neural inference and arbitrary checkpoint execution are not implied by sequence playback.

Stable-ID `.am53` keyframes can opt into CPU interpolation with `sequence_type: "stable_id_keyframes"` and `stable_ids: true`. Their unique IDs and SH degree must match. The implementation interpolates position, logarithmic scale, normalized quaternion orientation and SH coefficients. Independent-frame sequences always retain frame-hold semantics.

Editor imports embed decoded frames by default. A manifest with explicit `"storage": "external"` imports an index instead, enabling large independent-frame sequences without embedding the whole clip. Runtime `LoadFileAsync` also supports this bounded decoded-frame cache when `Stream External Sequences` is enabled; those external paths must remain available. External sequence streaming is distinct from a cooked spatial LOD/IoStore streamer. Use `Tools/Sequences/prepare_ply_sequence.py` to prepare an external PLY sequence outside Git.

## Quality and scope

Keep source data separate from reduced-budget rendering settings. Source splat count is not visible count; geometry attributes are not the complete GPU memory cost. High overlap, large projected splats and independent animation can dominate rendering or upload costs.

Current editor imports are capped at **1 GiB of embedded decoded point data**, approximately **4.19 million points total across all frames**, at 256 bytes per point. The runtime external-frame cache defaults to 512 MiB and allows roughly one third of that budget per frame (about 699,000 points at the default). These budgets exclude decoder temporaries, duplicate CPU arrays and GPU resources. Increasing a renderer splat-count setting does not increase import/cache limits.

CPU frame retention is configurable up to 8192 MiB. GPU source retention has a separate `r.AbuM53.SourceCacheMiB` budget, default 2048 MiB and maximum 8192 MiB. The three 3M-splat Skate samples were tested with **3072 MiB for each cache**, preserving all SH3 attributes. Source buffers upload the full stored frame even when fewer points are selected for rendering.

The renderer contains a global GPU radix-sort/quad path and a bounded 16×16 tile path. Tile capacity overflow requests a whole-view quad fallback; it does not intentionally drop overflowing tile references. The selected-point budget currently limits a prefix of input points and is **not spatial LOD**. CPU-assisted sorting and a bounded CPU software diagnostic are separate modes; equal image quality or frame rate across modes is not assumed.

The full implementation plan includes advanced streaming/LOD, additional codecs, deterministic cinematic rendering and broad integration qualification. Features are not advertised as complete until tested. Do not assume native Lumen lighting, shadows, collision, arbitrary translucent interleaving, path tracing, VR or Movie Render Queue parity from ordinary viewport rendering.

There is no measured 5M-at-60-FPS, 100M-source, 120-FPS or cross-vendor performance guarantee in this development version. Source counts and the plan's stretch targets must not be presented as achieved benchmark results.

A controlled RTX 4090 offscreen test at native 1280×720 measured **3.04 ms / 6.90 ms aggregate GPU frame time** for **1M / 5M selected inputs**. The larger case uses five instances of one synthetic asset with small splat footprints. These are GPU timing measurements, not presented-game FPS or measured visible-splat counts; see [the full benchmark limits](Docs/Validation.md#controlled-1m5m-workload).

## Tests

See [QA workflow](Docs/QA.md), [original fixture manifest](Tests/Fixtures/manifest.json) and [validation evidence](Docs/Validation.md). The portable C++ core is designed to build without Unreal; UE and hardware validation run separately.

Current validation includes 138 portable assertions, 18 UE tests with RHI validation, 33 Python unit tests, 20 real Earth Details captures and real three-frame Skate playback/reopen/cache checks. Earlier backend comparisons and a cooked Shipping static-scene smoke remain documented separately. Packaged animation, streaming and performance remain unverified.

## License and publication

Original code and original synthetic fixtures are Apache-2.0. See [LICENSE](LICENSE), [NOTICE](NOTICE), [third-party inventory](THIRD_PARTY_NOTICES.md) and [provenance](Docs/Legal/Provenance.md).

Unreal Engine is separately licensed. The full editor-tool distribution route still needs review against Epic's terms before claiming ordinary public-GitHub clearance. No research-only renderer or training stack should be bundled. Code licensing does not clear imported model rights or unrelated patents.

Read [the import, Details editing and large PLY sequence walkthrough](Docs/Import_Editing_and_PLY_Sequence_Walkthrough.md) for the v0.0.0.3 changes and migration limits.

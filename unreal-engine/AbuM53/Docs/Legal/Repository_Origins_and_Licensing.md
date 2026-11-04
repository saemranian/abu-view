# Abu M53 — Repository Origins, Original Development and Open-Source Licensing

<!-- provenance-review:start -->
Reviewed release: **v0.0.0.4**. Review date: **2026-10-26**. Reviewing contributor: **ChatGPT AI agent (user-directed)**.

Reviewed implementation files: **108**. Implementation fingerprint (SHA-256): `a12af8a000ea977e256236003ad8bbb3d59f0e610b8f9244777e5d39730542b3`.

The file ledger is a reviewed provenance declaration and drift check; it is not automated legal clearance.
<!-- provenance-review:end -->

## 1. What this record establishes

Abu M53 is an independently developed Unreal Engine plugin. The current tree and its recorded development history identify original runtime/editor/rendering work, a bundled Zstandard decoder, and SPZ compatibility work informed by upstream source. No existing Unreal Gaussian-splat plugin is recorded as its fork or wholesale foundation. Unreal Engine itself is a separately installed dependency.

This is the complete **recorded** repository/dependency inventory for this release, including research references. It does not reconstruct undocumented activity before the first Git baseline or prove that every mathematical idea originated here. Initial development predates the first real Git commit; no historical commits, per-line human/AI authorship, formal clean-room process or legal clearance are invented. New contributions must make their origins explicit.

The file-by-file declarations and reviewed implementation hashes are in [CodeOrigins.json](CodeOrigins.json). Pinned dependency hashes remain in [Dependencies.json](Dependencies.json). This document explains those records in plain language; complete retained licenses and notices control their respective components.

## 2. Software adopted or informed by external repositories

### Zstandard — bundled upstream implementation

- Repository: [facebook/zstd](https://github.com/facebook/zstd); release **v1.5.7**.
- Actual code: `ThirdParty/Zstd/zstddeclib.c`, `zstd.h`, `zstd_errors.h`. The standalone decompressor was generated using upstream's own single-file generator; the recorded generated implementation has no manual changes.
- Used for: SPZ v4 Zstandard stream decompression through the original Abu M53 codec/UE bridge. A complete Zstandard compressor or a Gaussian renderer was not adopted.
- Origin category: **third-party implementation compiled into Abu M53**. This component must never be described as developed from scratch here.
- License choice: **BSD-3-Clause**. Keep its copyright, conditions and disclaimer in source; reproduce the required notices with binary distributions. Names of upstream contributors do not grant endorsement rights. The original dual-license references remain; this project selects the BSD option. [Upstream v1.5.7 terms](https://raw.githubusercontent.com/facebook/zstd/v1.5.7/LICENSE).
- Exact archive/file hashes, generation command and local notice: [Zstandard provenance](../../ThirdParty/Zstd/PROVENANCE.md), [retained license](../../ThirdParty/Zstd/LICENSE).

### xxHash — bundled indirectly inside the Zstandard amalgamation

- Repository: [Cyan4973/xxHash](https://github.com/Cyan4973/xxHash).
- Actual code: the xxHash portions embedded in `ThirdParty/Zstd/zstddeclib.c`; no separately installed xxHash runtime is required.
- Used for: Zstandard's internal hashing/checksum implementation. It is inherited through the pinned Zstandard artifact, not an independently upgraded dependency in this tree.
- Origin category: **transitive third-party code**, specifically Zstandard's adaptation. Its version macros identify xxHash 0.8.2; a separate xxHash commit has not been established. Exact bundled content is pinned by the Zstandard file hash.
- The embedded adaptation's header offers the BSD-style license in its source-tree root or GPLv2. For this pinned Zstandard artifact, the selected root license is **BSD-3-Clause**. Keep the embedded Yann Collet/Meta notices and the Zstandard license; do not substitute an unrelated upstream version's terms. [Zstandard's adaptation source](https://github.com/facebook/zstd/blob/v1.5.7/lib/common/xxhash.h). The standalone [xxHash project's BSD terms](https://github.com/Cyan4973/xxHash/blob/v0.8.2/LICENSE) are a separate upstream reference.

### SPZ — original compatibility reader informed by upstream source

- Repository: [nianticlabs/spz](https://github.com/nianticlabs/spz), recorded commit **affd0ecea7fbb4c265ee119475af7ee5b2997482**.
- Files consulted: upstream `load-spz.cc`, `load-spz.h`, `splat-utils.h`, format descriptions and decoding constants.
- Abu M53 implementation: `Core/Source/Spz.cpp`, with original bounded reading, validation, allocation/cancellation handling and codec-provider integration; UE's `SpzBridge.cpp` compiles that implementation.
- Origin category: **original implementation with upstream-informed format/decoding semantics**, not a vendored complete SPZ library. It is not described as wholly uninformed from-scratch codec design.
- License treatment: original Abu M53 code uses Apache-2.0; the upstream **MIT attribution and full permission notice are conservatively retained** in [SPZ_NOTICE.md](../../Core/SPZ_NOTICE.md). Preserve that notice when redistributing the compatibility work. [Pinned upstream MIT terms](https://raw.githubusercontent.com/nianticlabs/spz/affd0ecea7fbb4c265ee119475af7ee5b2997482/LICENSE).
- SPZ v1–v3 gzip uses zlib; v4 uses the separately attributed Zstandard decoder. Support remains limited to the explicitly tested profiles and extension policy.

### zlib — externally supplied linked compression dependency

- Repository: [madler/zlib](https://github.com/madler/zlib); [official project](https://zlib.net/).
- Used for: gzip/SPZ v1–v3 decoding through `Core/Source/Codecs.cpp` and UE compression-provider integration. The portable build discovers installed zlib; UE uses its installed engine dependency, recorded as version 1.3 for the validated UE build.
- Origin category: **linked external library**, not source vendored in this repository. The bridge/provider code is original Abu M53 work.
- Terms: [zlib license](https://zlib.net/zlib_license.html). Do not misrepresent origin, mark altered source, and retain required source notices. Applicable binary/package notices must accompany redistributed library material. A current upstream version does not automatically change UE's installed dependency version.

## 3. Original Abu M53 development

The following areas are recorded as original implementation, built using published mathematics, public format knowledge and/or the separately licensed UE APIs. Their source is under **Apache-2.0**, subject to the specific exceptions above. “Original” describes implementation provenance; it does not claim invention of Gaussian splatting, SH mathematics, sorting algorithms or Unreal's interfaces.

- **Portable core:** `Core/Include/AbuM53`, `Core/Source/Core.cpp`, `Codecs.cpp`, `Render.cpp`: PLY/SPLAT parsing, original AM53 container, transforms, activation/SH/covariance math, CPU reference rendering and codec abstraction. SPZ and Zstandard exceptions are identified individually above.
- **UE runtime:** `Source/AbuM53Runtime`: asset/frame types, versioned serialization, import conversion, actor/component, animation controls, independent-frame and stable-ID selection/interpolation, asynchronous loading, CPU frame caching and resource lifetime. Bridge translation units connect original core code to installed libraries; they do not relicense their dependencies.
- **UE rendering:** `Source/AbuM53Render` and `Shaders/Private`: UE rendering hooks, GPU projection/SH, stable radix sort and scan, quads, bounded tiles/overflow fallback, source-buffer caching, CPU-assisted mode, telemetry and GPU regression tests. Public papers and engine API declarations informed the design. No restricted CUDA rasterizer is recorded as copied or translated.
- **UE editor:** `Source/AbuM53Editor`: asset actions, placement/import/reimport factories, feedback/cancellation and the About tab. Slate, ToolMenus, AssetTools and UnrealEd are engine interfaces; those frameworks are not original Abu M53 implementations.
- **Tools and tests:** `Tools`, `Tests/portable`, owned synthetic fixtures: fixture/converter/sequence preparation, validation, deployment, source packaging, versioning and provenance checks. Original synthetic fixtures are analytically generated. Third-party photographs, weights or user scenes are not licensed by that fixture claim.
- **Configuration/documentation:** original build rules, plugin/project configuration, workflows, plans and walkthroughs. The standard `LICENSE` text is the Apache Software Foundation's license document, not an original license invented by this project.

The per-file ledger classifies exceptions explicitly. A future copied file placed in an otherwise original folder must be assigned its actual upstream origin; its folder name is not evidence of authorship.

## 4. Other tools/frameworks used, without vendoring their implementations

- **Unreal Engine / EpicGames/UnrealEngine:** [access information](https://www.unrealengine.com/ue-on-github). Installed UE 5.8.2 SDK/runtime, editor frameworks, RHI/RDG, shader compilation, UE Python and Automation. Governed by [Epic's EULA](https://www.unrealengine.com/eula/unreal), not Apache-2.0. No engine implementation source is included in the plugin source archive.
- **Microsoft Visual Studio/MSVC, Windows SDK, DirectX/D3D12:** external build/runtime platform. Original HLSL calls platform/engine interfaces; this is not an adopted CUDA renderer. Redistributable runtime/SDK components have their own terms. No compiler, Windows SDK or GPU driver is included in the source repository.
- **Python / python/cpython:** [repository](https://github.com/python/cpython), [license history](https://docs.python.org/3/license.html). External interpreter/standard library for tooling; Python implementations and their bundled dependencies retain their licenses. No interpreter is vendored. The development Python and UE's Python may be different versions.
- **CMake / Kitware/CMake and CTest:** [repository](https://gitlab.kitware.com/cmake/cmake), [BSD licensing](https://cmake.org/licensing/). External portable build/test tools; no implementation bundled.
- **NumPy / numpy/numpy:** [repository](https://github.com/numpy/numpy), [BSD license](https://numpy.org/doc/stable/license.html). Optional screenshot analysis only, previously tested at 2.2.6; not a UE runtime dependency and not vendored. Binary packages may have additional notices.
- **Pillow / python-pillow/Pillow:** [repository](https://github.com/python-pillow/Pillow), [Pillow/PIL terms](https://pillow.readthedocs.io/en/stable/about.html#license). Optional screenshot analysis, previously tested at 12.2.0; not vendored or required by the renderer. Preserve the applicable distribution's notices if redistributing it.
- **Git / git/git:** [repository](https://github.com/git/git). External version-control tool; no Git implementation is linked into or copied into Abu M53. Its tool license is separate from the code it versions.
- **actions/checkout@v4 and actions/setup-python@v5:** [checkout](https://github.com/actions/checkout), [setup-python](https://github.com/actions/setup-python). Referenced by `.github/workflows/portable-core.yml`, under their [MIT](https://github.com/actions/checkout/blob/v4/LICENSE) [terms](https://github.com/actions/setup-python/blob/v5/LICENSE). These are CI service actions, not renderer dependencies. The workflow currently uses version tags rather than immutable action commits; their runtime/transitive components remain external.
- **ChatGPT/Codex and Antigravity:** development assistants, not bundled libraries or upstream rendering repositories. Provider terms and contribution rights are separate. AI output does not remove copyright/attribution duties or prove original provenance. No claim is made that Antigravity authored existing code unless a contribution record establishes that fact.

## 5. Research/format repositories consulted, not adopted as a code base

The original research plan records the following references. They are listed to explain the research trail, **not** to credit them as bundled code or imply that planned adapters already exist. Their license descriptions in the historical plan are review context, not a fresh approval of all upstream branches/transitive packages.

- [graphdeco-inria/gaussian-splatting](https://github.com/graphdeco-inria/gaussian-splatting) and [diff-gaussian-rasterization](https://github.com/graphdeco-inria/diff-gaussian-rasterization): method/PLY/appearance research; their restricted implementation is excluded by project policy.
- [autonomousvision/mip-splatting](https://github.com/autonomousvision/mip-splatting): filtering research; implementation not adopted.
- [r4dl/StopThePop](https://github.com/r4dl/StopThePop): ordering/quality research; no wholesale reuse.
- [nv-tlabs/3dgrut](https://github.com/nv-tlabs/3dgrut) and [nvpro-samples/vk_gaussian_splatting](https://github.com/nvpro-samples/vk_gaussian_splatting): rendering alternatives/reference investigation; no CUDA/Vulkan renderer imported.
- [JorisAR/gaussian-point-splatting](https://github.com/JorisAR/gaussian-point-splatting): stochastic/high-count research; not the current Abu M53 renderer.
- [yandex/yags](https://github.com/yandex/yags): UE renderer comparison; no recorded fork or port.
- [YuanBaoSMadLab/OpenSplat4D](https://github.com/YuanBaoSMadLab/OpenSplat4D): architecture/license review; excluded as a wholesale foundation.
- [DazaiStudio/SplatRenderer-UEPlugin](https://github.com/DazaiStudio/SplatRenderer-UEPlugin): package/format research; no imported plugin foundation.
- [antimatter15/splat](https://github.com/antimatter15/splat): static SPLAT format reference. Abu M53's parser/renderer are its own implementations; no viewer code is recorded as copied.
- [mkkellogg/GaussianSplats3D](https://github.com/mkkellogg/GaussianSplats3D): format/KSPLAT research; no JavaScript renderer adopted and no KSPLAT support implied.
- [playcanvas/engine](https://github.com/playcanvas/engine) and [playcanvas/splat-transform](https://github.com/playcanvas/splat-transform): PLY/SOG/tooling profile research; no engine/tool implementation adopted.
- [KhronosGroup/glTF](https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Khronos/KHR_gaussian_splatting): interoperability/color conventions and future adapter research; no glTF implementation vendored.
- [hustvl/4DGaussians](https://github.com/hustvl/4DGaussians), [fudan-zvg/4d-gaussian-splatting](https://github.com/fudan-zvg/4d-gaussian-splatting), [oppo-us-research/SpacetimeGaussians](https://github.com/oppo-us-research/SpacetimeGaussians): distinct 4D model/format research; their training, neural inference and restricted components are not included.
- [DazaiStudio/4dgs-converter](https://github.com/DazaiStudio/4dgs-converter): GSD v2 interoperability investigation; no converter implementation adopted and no GSD adapter claimed.
- [ebiggers/libdeflate](https://github.com/ebiggers/libdeflate) and [webm/libwebp](https://chromium.googlesource.com/webm/libwebp): potential future codecs considered in the plan, not current dependencies.

Publications on 3DGS, hierarchical/LOD representations, Gaussian filtering and native 4D mathematics are cited in [ImplementationPlan.md](../ImplementationPlan.md). A mathematical citation is not a code-license grant. A local AbuAlign manifest was also inspected for interoperability; no upstream repository URL or copied implementation is recorded for it. Do not invent one.

## 6. How the licenses apply together

### Original code: Apache-2.0

Original Abu M53 source, documentation and owned synthetic fixtures use [Apache-2.0](../../LICENSE). It permits commercial use, modification and redistribution subject to its conditions. Keep the license and relevant notices; mark modified files and preserve applicable attribution. Its contributor patent grant is limited to covered contributions, with termination provisions; it is not general patent clearance. It grants no general trademark rights or warranty. [Authoritative Apache text](https://www.apache.org/licenses/LICENSE-2.0).

### Adopted code keeps its own terms

Apache-2.0 does not replace the SPZ MIT notice, Zstandard/embedded xxHash BSD terms, zlib terms, or externally supplied platform/tool licenses. Preserve the full applicable texts and attribution in source and binary distributions. `NOTICE`, `THIRD_PARTY_NOTICES.md`, `Core/SPZ_NOTICE.md` and `ThirdParty/Zstd` are part of the required distribution record. Treat a newly adopted dependency and all of its transitive components as a new review, even if its root license looks permissive.

### Unreal Engine and public distribution

Unreal Engine remains proprietary Licensed Technology under Epic's EULA. Abu M53's Apache license cannot grant rights to engine source, engine tools or Marketplace content. Epic's rules govern distribution of Engine Code and **Engine Tools** and the permitted channels for those materials. The current EULA names Fab or Epic's UnrealEngine GitHub network for public Engine Tools distribution; the actual plugin/editor package still needs a recorded classification. A source-only archive or an `Editor` module name does not settle that classification. [Epic EULA, sections 5–7](https://www.unrealengine.com/eula/unreal).

Consequently, original-code licensing is established in the repository, but unrestricted ordinary public-GitHub distribution of every possible UE package is not certified by this inventory. No new clearance, patent opinion or publication authorization is created by the About tab. Existing roadmap/publication review remains open.

### Scene data, models and brands

User PLYs, trained weights, captures, Earth/Skate test scenes and screenshots have separate rights. Importing them does not relicense them under Apache. They stay outside the source repository/archive. There is no declared trademark or worldwide freedom-to-operate clearance for the product name. Unreal compatibility wording does not imply Epic or upstream endorsement.

## 7. Maintenance contract for every human and AI contributor

These requirements apply to ChatGPT/Codex, Antigravity and other contributors working on this checkout. They are in `AGENTS.md` and the root `GEMINI.md` pointer. They are repository instructions and release checks, not a claim that an external AI service can be forced to comply.

1. Before editing, read this record, `CodeOrigins.json`, dependency notices and the current Git/version state.
2. For each change, state whether it is original, upstream-informed, copied, modified, generated, linked or research-only. Cite exact upstream URL/revision/file paths for adopted code. Never label a translation or AI rewrite of third-party code as original merely because its syntax changed.
3. Record the contributor/agent actually doing the work in `Docs/Changes/<version>.md`; ownership remains with the appropriate rights holders, not automatically the agent's product name. Mark unknown historical attribution as unknown.
4. New implementation files require an explicit origin declaration. New dependencies require exact license/notices and transitive-dependency review in `Dependencies.json`, `CodeOrigins.json`, this document and `THIRD_PARTY_NOTICES.md`. Modified vendor files require updated modification records and reviewed hashes, not just a hash refresh.
5. Update the explanation above when feature ownership or repository use changes, append a review-history entry, bump the release version, then refresh reviewed implementation hashes using `Tools/Provenance/provenance.py`. A hash refresh is an attestation step, not automatic proof of authorship or legal permission.
6. Run provenance/source audits, relevant tests, installed-plugin verification and the normal release workflow. CI and local packaging/deployment checks reject stale or undeclared implementation files. Keep private data, engine implementations and credentials outside Git.
7. The About tab reads this installed Markdown document when opened. Build/deploy the matching version to make the updated record available in UE. No separate hidden attribution list should drift from it.

### Review history

- **v0.0.0.1–v0.0.0.3:** initial implementation/provenance and later import/render fixes recorded by ChatGPT-assisted development. The first Git baseline is retrospective; no complete earlier per-line agent history exists. No Antigravity contribution is asserted for that history.
- **v0.0.0.4 — 26 October 2026 — ChatGPT AI agent, user-directed:** added the About tab and consolidated this repository/ownership/license record. Reconciled Zstandard, embedded xxHash, SPZ, zlib, external tools and research-only repositories. Added reviewed-file drift detection and instructions for future ChatGPT/Antigravity work. No rendering library or new third-party code adopted in this change.

# Validation evidence

Current update: 26 October 2026. Historical records below retain their original dates and scope.

This file records completed checks only. It must be updated as implementation and testing finish.

Sanitized, compact copies of the owned test results are included in [Evidence](Evidence/README.md). Raw engine logs and machine identifiers are not part of the source release.

## v0.0.0.4 About/provenance update

The [release record](Changes/v0.0.0.4.md) and [compact evidence](Evidence/v0.0.0.4-validation.json) record 19 passing UE tests with D3D12/SM6/RHI validation, including the packaged-document/tab lifecycle check. Eight provenance safeguard tests, three version tests, eleven deployment tests and four package mechanics checks passed. Editor, Development and Shipping builds completed. The Window menu entry and installed About document were visually inspected in `abu_M53_Test_01`; the existing Skate sample loaded/rendered. No renderer implementation changed, and prior performance results are not relabeled as a new benchmark.

## v0.0.0.3 update

The [v0.0.0.3 release record](Changes/v0.0.0.3.md) and [compact evidence](Evidence/v0.0.0.3-validation.json) supersede the baseline counts below for the current release: **138 portable assertions, 18 UE automation tests with RHI validation, 33 Python unit tests and four packaging regression checks passed**. Win64 Editor, Development and Shipping builds completed.

Real Earth import/save/load measurements, 20 GPU Details-edit captures, and the three supplied 3M-splat Skate samples were tested in `abu_M53_Test_01`. Skate's cold frames, reverse warm seeks, native playback and saved-level reopen passed. The final 596-row warm trace recorded two rendered views per row, zero additional GPU uploads and 1,192 source-cache hits. Aggregate GPU time averaged 11.348 ms, with p99 53.507 ms; engine frame time averaged 16.672 ms under a 60 Hz cap. These offscreen timings are not presented FPS or all-vendor performance guarantees.

The original Earth package was upgraded only after its v2 backup hash matched, with all map files preserved. The source repository excludes the private PLYs, UE assets and screenshots. See the release record for migration requirements, measurement boundaries and remaining roadmap work.

## Historical implementation baseline

The following table and detailed sections preserve the original implementation's evidence, including its earlier assertion counts and test configurations.

| Check | Result | Evidence |
|---|---|---|
| Original QA fixture generation | Passed | Default generator produced six data files plus a manifest, with 1,000 splats per frame; `Tests/Fixtures/manifest.json` records lengths and SHA-256 hashes |
| Isolated UE host creation | Passed | `work/AbuM53Host/AbuM53Host.uproject` created with an external plugin search directory |
| Portable core build/tests | Passed, historical baseline | Release executable reports **113 checks** passed, including gzip SPZ v1–v3, raw/compressed-block SPZ v4, malformed-input and antialias compensation regressions; CTest reports 1/1 passed |
| UE plugin compilation | Passed | Final Win64 Development Editor build against installed UE 5.8.2 completed; no C++ warnings reported |
| Static/sequence import checks | Passed for initial four fixtures | UE report contains successful ASCII PLY, binary PLY, `.splat` and three-frame manifest imports, with expected 1,000-point counts |
| SPZ editor import/rejection smoke | Passed | Eight valid fixtures (v1–v4, SH0/SH3) imported; malformed TOC, unsupported extension and gzip bomb rejected |
| Complete import/map smoke | Passed | `import-smoke.json` reports `passed: true`, four expected imports, sequence seek indices 0/1/2/0 and saved `/Game/AbuM53QA/ShellQA`; this was not a rendering test |
| UE automation | Passed, eight tests | Six runtime tests plus GPU scan/radix tests; 6,520,588 scan outputs and 2,132,841 exact stable key/index pairs checked |
| UE SM6 stress automation | Passed, nine tests | Normal suite plus 16,776,961 exact stable key/index pairs in the 2D dispatch-boundary stress case; sorting evidence only |
| GPU shader compilation and image capture | Passed for initial synthetic scene | UE 5.8.2, NVIDIA RTX 4090, D3D12 SM5, 1280×720 capture shows the 1,000-point colored anisotropic shell; no shader compilation error reported in that run |
| Backend image comparison | Passed for the fixed synthetic scene | Quad and CPU-assisted images match exactly; tiled/software maximum channel difference 2/255; metrics below, no general conformance claim |
| AMD/Intel cross-vendor behavior | Pending | Not claimed |
| Win64 Shipping compile/link | Passed | Source snapshot had zero differences; neither AbuM53 editor module nor UnrealEd appears in the Shipping link |
| Packaged Shipping static smoke | Passed | Owned 1,000-splat SH3 shell cooked, packaged, launched and rendered at 1280×720; process exit 0; packaged animation/performance unverified |
| Controlled high-count workload | Passed, limited synthetic scope | Explicit 1280×720 offscreen capture with 1M/5M selected inputs; aggregate GPU times below; no presented FPS claim |
| Source-release allowlist audit | Passed | Final source allowlist and pinned vendor hashes checked; generated engine/plugin binaries, raw logs and screenshot images excluded |
| Source-package roundtrip | Passed on temporary test fixture | Unpack/audit/repack yields identical ZIP bytes; generated manifest is excluded as input and regenerated once |

No completed check here constitutes unrestricted legal clearance for publishing UE editor tooling. The publication review is tracked separately in `Docs/Legal`.

## Portable test evidence

Executed from the containing workspace:

```powershell
& 'work/AbuM53CoreBuild/Release/AbuM53CoreTests.exe' 'work/AbuM53CoreBuild/final-security-review'
ctest --test-dir 'work/AbuM53CoreBuild' -C Release --output-on-failure
```

Observed output: `PASS 113 checks`; CTest: `100% tests passed, 0 tests failed out of 1`. Durable workspace logs: `work/AbuM53CoreBuild/final-security-test.log` and `work/AbuM53CoreBuild/final-ctest.log`. These are portable-core tests, not GPU rendering or frame-rate evidence.

## UE import evidence

`work/AbuM53Host/Saved/AbuM53QA/import-smoke.json` records successful imports of the original ASCII PLY, binary PLY, 32-byte `.splat` and three-frame `.am53seq` fixtures. Each frame reports 1,000 points. Sequence seeks to 0, 0.05, 0.06666666666666667 and 0 seconds select frames 0, 1, 2 and 0 respectively. Actor/camera setup and map saving completed. The report explicitly records `render_test: false`; successful import and map setup do not validate the GPU image.

## Initial GPU capture

The separate rendering run saved `work/AbuM53Host/Saved/AbuM53QA/shell_gpu.png`; the image was visually inspected. It shows a colored elliptical shell on a black background with visible anisotropic splat footprints. The capture is 1280×720, with a fixed camera at UE coordinates (330, 0, 100) looking toward the origin. `work/AbuM53_gpu.log` records the D3D12/SM5 engine run and screenshot saving. This establishes basic GPU rendering on the tested NVIDIA machine, not source-appearance conformance, backend parity, tile-overflow correctness or high-count performance.

The engine log identifies Windows 11 25H2, an AMD Ryzen Threadripper PRO 3955WX 16-core CPU, NVIDIA GeForce RTX 4090, and NVIDIA driver 610.88 (32.0.16.1088; driver date 22 July 2026). Other adapters and drivers have not been tested.

## UE automation and SPZ

`work/AbuM53AutomationFinal/index.json` records eight successful tests: `ExclusiveScanGPU`, `RadixGPU`, `FrameValidation`, `LatestAsyncRequestWins`, `ManifestIndexSafety`, `SequenceSelection`, `SPZVersionsAndMetadata` and `StableIdInterpolation`. The GPU scan test compared 6,520,588 outputs across 56 size/pattern cases; the radix test compared 2,132,841 exact stable key/index pairs across nine cases. [The compact report](Evidence/ue-automation-final.json) preserves the results without machine identifiers. This validates those helpers on the tested GPU; it is not an end-to-end million-splat benchmark.

A separate D3D12 SM6 run passed all nine tests, including `Radix2DDispatchBoundary`, which compared 16,776,961 exact stable key/index pairs. [The SM6 compact report](Evidence/ue-automation-sm6-stress.json) records this result from `work/AbuM53StressSM6/index.json`. The 16.8M count belongs to an isolated sorting test; it must not be described as 16.8M splats rendered in real time.

`work/AbuM53Host/Saved/AbuM53QA/spz-import-smoke.json` records eight accepted one-point SPZ fixtures covering versions 1–4 and degrees 0/3, and three rejected malformed/unsupported fixtures. It is an import test, not image conformance for all SPZ datasets.

## Backend comparison

The six screenshots requested by `Tools/QA/ue_capture_backends.py` were analyzed using `Tools/QA/compare_captures.py`. Evidence: `work/AbuM53Host/Saved/AbuM53QA/backend-image-comparison.json`, including per-image hashes. Metrics are RGB values after capture in 8-bit output space; they are not linear-radiance errors. The complete image includes a large black background, so foreground-only means are also reported.

| Compared captures | Maximum channel error /255 | Mean absolute channel error, 0–255 | Foreground mean absolute channel error | Full-image PSNR |
|---|---:|---:|---:|---:|
| Tiled GPU / quad GPU | 14 | 0.0309104 | 0.1201233 | 63.129 dB |
| Tiled GPU / CPU software | 2 | 0.0281120 | 0.1092492 | 63.641 dB |
| Quad GPU / CPU-assisted | 0 | 0 | 0 | Identical |
| Quad GPU / tile-capacity-32 probe | 0 | 0 | 0 | Identical |

The disabled-render control is entirely black. The capacity-32 probe matches the quad result, which is consistent with fallback, but the image alone is not direct GPU overflow telemetry. Differences between tiled and quad output have not been fully attributed; floating-point precision and blending order are possible contributors. These comparisons cover one 1,000-point shell at one camera and do not establish general scene, transform, temporal or cross-vendor parity.

## Controlled 1M/5M workload

[The sanitized benchmark report](Evidence/synthetic-benchmark.json) comes from the completed run at `work/AbuM53Benchmark/final-results/benchmark.json`. It used explicit `SceneCaptureComponent2D.capture_scene` submissions into a native 1280×720 RGBA8/FinalColorLDR target, D3D12 SM6, RTX 4090, driver 610.88. The camera was at (1365.7043, 0, 0) cm looking at the origin with 60° horizontal FOV. Each stage warmed up for 120 editor ticks and recorded 300 CSV frames; the report validates the 296 interior rows after excluding two boundary rows at each end. There was one rendered-view submission per measured frame, with the expected selected-input count; visibility was not read back.

| Selected inputs | Actor instances / unique assets | Aggregate GPU frame time, mean | GPU frame time, p95 | Engine frame time, mean |
|---|---:|---:|---:|---:|
| 1,000,000 | 1 / 1 | 3.0390 ms | 3.1754 ms | 10.7465 ms |
| 5,000,000 | 5 / 1 | 6.8954 ms | 6.9234 ms | 9.4241 ms |

GPU time is the engine-reported aggregate GPU frame time, not an isolated splat-pass duration. Engine frame time and Slate callback intervals include editor/submission behavior and are not presented-game FPS. No per-capture forced GPU synchronization was added. The two stages are separate short samples; their CPU timing should not be interpreted as scaling proof.

The source is one original 1M-point SH3 shell (`ec10328d6ad001b67e389d4ad7abbb3bcb2a01f4354775b71b410fa7a47256f9`), with splat scale reduced to 0.0316228 of the 1,000-point fixture scale. The 5M case instantiates that same asset five times; all five shell bounds fit inside the capture. These small synthetic footprints are not representative of large-footprint/high-overlap real scenes. Selected input count is not measured visible splats. Tiles were enabled, but overflow/path readback was not recorded, so these numbers cannot be attributed specifically to tiled composition. Exported PNGs came from the same capture target outside the timed window and passed chunk/CRC/end-of-file checks.

The earlier hidden-viewport timing attempt was invalid because it did not establish renderer execution. Its timings are excluded. No 60-FPS/120-FPS production performance, 100M-source streaming or cross-vendor claim follows from this controlled workload.

## Shipping boundary

[Shipping compile evidence](Evidence/shipping-compile.json) records a successful Win64 Shipping build with zero source-snapshot differences and no editor-module or UnrealEd linkage.

[The separate cooked Shipping report](Evidence/shipping-cook.json) records successful cook, stage, package, archive and launch of the owned `/Game/AbuM53QA/ShellQA` static fixture. The cook processed 519 packages with zero reported errors/warnings. The launched Shipping game initialized the 1,000-point SH3 shell, selected the QA camera and captured the scene at tick 121 before exiting with code 0. The clean 1280×720 image was visually inspected: the complete colored shell has black margins and no default-pawn occlusion; PNG CRCs are valid with zero trailing bytes. Its SHA-256 is `af4822c89f78b71c74ae7665a1297b8e63db847fd6a493135175c72f39fa5f13`.

The 90° camera adjustment, hidden default pawn, screenshot trigger and automatic exit are test-host instrumentation outside the published plugin. This validates a single cooked static scene on the tested Windows/NVIDIA machine. Packaged animation, external streaming and packaged performance were not verified. The compiled game, engine dependencies, screenshots and raw logs remain local and are excluded from the source archive.

## Installed development release v0.0.0.2 — 25 October 2026

Abu M53 was built with BuildPlugin for the UE 5.8.2 editor and Win64 Development/Shipping targets, then installed in the engine Marketplace plugins directory. The persistent `abu_M53_Test_01` project loaded the installed copy and passed four-fixture import/seek setup and eight DX12/SM6 automation tests. A 1280×720 static-fixture GPU capture was visually inspected and its PNG CRCs/trailing length checked. Version-helper tests (3), deployment guard tests (4), source audit and package roundtrip checks (4) passed. No high-count benchmark or packaged-animation test was rerun.

See [the release record](Changes/v0.0.0.2.md), [compact evidence](Evidence/windows-installation-v0.0.0.2.json) and [installation/update guide](Windows_Installation_and_Test_Project.md). Actual editor projects, compiled modules, raw logs and screenshots remain local.

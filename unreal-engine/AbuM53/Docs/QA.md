# Validation workflow

The source tree contains reproducible tests and original fixtures. Test tooling being present does not mean a test has passed. Record actual commands, results and engine/GPU identities in `Docs/Validation.md`.

## Portable checks

```powershell
python Tools/QA/generate_fixtures.py
cmake -S Core -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build --config Release --parallel
ctest --test-dir build -C Release --output-on-failure
python Tools/QA/audit_source.py --report build/source-audit.json
```

`generate_fixtures.py` writes ASCII/binary PLY, a 32-byte `.splat` stream, three animation frames and a sequence manifest. The default set has 1,000 source splats per frame. For performance tests, generate larger files into a separate directory using `--count` and `--output`; do not confuse source count with visible/active count.

## Isolated UE host

```powershell
& Tools/QA/create_host.ps1 -ProjectDirectory 'C:/YourWorkspace/AbuM53Host'
```

The script creates a new test `.uproject` referencing the plugin's parent directory through `AdditionalPluginDirectories`. It does not edit an existing project descriptor or installed engine. Existing user project data stays untouched. The host enables Python and Editor Scripting for QA, retains normal engine plugin defaults for editor subsystem initialization, and disables unrelated installed Marketplace plugins in the new host descriptor. `-EngineDirectory` can identify a nonstandard engine installation.

After the plugin compiles, run `Tools/QA/ue_smoke.py` through UE Editor Python. It imports all standard fixtures, places an Abu M53 actor and a camera, and saves `/Game/AbuM53QA/ShellQA`. Results go into the host's `Saved/AbuM53QA/import-smoke.json`. `NullRHI` can test imports and serialization; it cannot validate GPU rendering.

For a GPU capture, open the saved map in a functioning editor and execute `Tools/QA/ue_capture.py`. It waits 60 editor ticks before requesting a 1280×720 screenshot. Inspect the screenshot and shader logs. The capture-request JSON confirms only the request, not image correctness.

`Tools/QA/ue_capture_backends.py` produces six fixed-camera captures: tiled GPU, quad GPU, a 32-entry tile-capacity overflow probe, CPU-assisted sorting, rendering disabled and CPU software diagnostic. It waits 30 editor ticks after mode changes and 30 after screenshot requests, records requests in `backend-capture-requests.json`, then exits the editor. The capacity probe must be accompanied by actual overflow evidence before claiming fallback coverage.

After the files exist, run `python Tools/QA/compare_captures.py --directory C:/YourWorkspace/AbuM53Host/Saved/AbuM53QA --output C:/YourWorkspace/backend-image-comparison.json`. It preserves the images and records exact hashes, RGB mean/max/RMSE/PSNR, changed pixels and foreground-only metrics. Optional image comparison requires separately installed NumPy and Pillow (tested here with NumPy 2.2.6 and Pillow 12.2.0); ordinary fixture generation uses Python's standard library only.

For a larger original fixture, `python Tools/QA/generate_benchmark.py --output C:/YourWorkspace/AbuM53Benchmark --count 1000000` streams a binary SH3 PLY and records its count, size and SHA-256. The footprints shrink with inverse square root of count to bound geometric overlap. This deliberately controlled shell is not a substitute for a difficult real scene; keep it outside the source release.

## Persistent-project import and sequence regressions (v0.0.0.3)

Use `abu_M53_Test_01` for ongoing installed-plugin tests. Preserve its existing maps: the original `ue_smoke.py` workflow is for an isolated host and must not be rerun over a user's edited ShellQA level.

- `Tools/QA/ue_asset_benchmark.py`: a synchronous editor script driven by `ABUM53_ASSET_BENCHMARK_CONFIG`. The JSON supplies `source`, a **new** `/Game/` destination, `report`, `expected_splats` and optional `load_existing`. It records import and save independently and refuses an existing destination.
- `Tools/QA/ue_asset_reload_validation.py`: a synchronous fresh-process check driven by `ABUM53_ASSET_RELOAD_CONFIG`, with `assets` records containing `path`, `expected_splats`, `expected_frames`, and a `report` path. Optional `migrate_from`/`migrate_to` saves only a new copied asset. Open `/Engine/Maps/Entry` to avoid a startup level preloading the measured asset. NullRHI is sufficient for these two serialization workflows.
- `Tools/Sequences/prepare_ply_sequence.py`: prepares naturally ordered, unchanged binary PLY frames and an external manifest in a new folder outside Git. Supply the intended FPS explicitly. Run its seven unit tests before changing preparation behavior.
- `Tools/QA/ue_sequence_validation.py`: rendering and native playback in unique test assets/maps. Supply `ABUM53_SEQUENCE_MANIFEST` and a new private `ABUM53_SEQUENCE_OUTPUT`; optional `ABUM53_SEQUENCE_CAMERA` is JSON with source-space `location`, `target`, `fov`. CPU and GPU cache settings default to 3072 MiB for the three 3M-splat samples. Use `-ExecCmds="py <script>"`, **not** `-ExecutePythonScript`, because asynchronous Slate callbacks must remain alive. Run in a fresh D3D12/SM6 rendering editor with `-RenderOffscreen -unattended`; do not use NullRHI.

The sequence report checks actual displayed indices/counts, PNG integrity/nonblank output, reverse warm seeks, native playback, CPU misses, GPU upload/hit/budget counters, and a saved-level reopen. CSV polling waits for the Windows writer handle to close and for a complete stable footer. A non-reentrant callback and callback suspension protect save/reload operations from nested Slate ticks. Twelve host-side unit tests cover those reporting and lifecycle checks. Nonblank PNG checks are not source-fidelity certification; inspect the captures separately.

Always inspect JSON `passed`, UE test states and error logs. An editor can exit with status zero after a Python QA failure. The strict GPU suite uses `-rhivalidation`; its readback buffers declare copy-source usage explicitly. Performance measurements should run without concurrent compilation and must identify whether validation overhead, multiple views, frame caps or cold loads are present.

The release's real-file procedure and measured results are in [v0.0.0.3](Changes/v0.0.0.3.md).

## Required reporting

Record exact UE build, CPU/GPU/driver, native/internal resolution, render backend, SH degree, source/resident/visible splat counts, scratch allocation, camera path and quality controls. Record actual frame percentiles rather than only a peak FPS. State explicitly whether the run is editor, standalone or packaged.

Known-good image checks should inspect silhouette, SH coloration, occlusion and anisotropic footprint. Run sequence scrubbing in forward/reverse order and compare timestamps. CPU and GPU references must use the same coordinate, color, sorting and filter conventions before interpreting error metrics.

## Source-release audit

`python Tools/Provenance/provenance.py check` checks the reviewed implementation-file ledger and its origins, the current release's narrative review history, and the document's fingerprint. `Tools/Provenance/test_provenance.py` exercises drift, new-file/removal declarations, stale document metadata and release mismatches. `audit_source.py` invokes the same gate, so packaging and deployment cannot silently use a stale record. Review and update origins/notices before running `refresh`; never use the refresh command as a substitute for origin/license review.

`audit_source.py` creates a file/hash manifest, prunes generated build directories, rejects links/junctions, restricts fixture formats to fixture directories and flags non-allowlisted file types or suspicious engine/research copyright markers. It checks pinned vendor hashes from `Docs/Legal/Dependencies.json` and requires the retained license/provenance files. It does not approve licenses, identify every copied file or replace human provenance review.

After the source and validation record are frozen, create a source-only archive outside the source directory:

```powershell
python Tools/QA/package_source.py --output ../AbuM53-source.zip
```

The archive has normalized timestamps, a per-file hash manifest and no generated engine/plugin binaries. Packaging checks that files have not changed since auditing. A root `ARTIFACT_MANIFEST.json` in an unpacked release is treated as generated metadata: auditing excludes it, and packaging always recreates it without a duplicate entry. `python Tools/QA/test_source_package.py` checks byte-identical unpack/audit/repack behavior on a temporary original fixture. Review the actual archive before publishing it; the script does not decide whether a public distribution route satisfies the UE license.

`Tools/QA/export_evidence.py --workspace C:/YourWorkspace` extracts compact results from this validation host's known report locations into `Docs/Evidence`. It selects only the plugin's own automation cases and removes device/user identifiers, absolute machine paths and raw engine logs. The normal automation report defaults to `work/AbuM53AutomationFinal/index.json`; use `--automation` for a different workspace-relative report. A successful extraction does not make a test more comprehensive than its original assertions.

The separately run SM6 stress report can be exported with `--automation work/AbuM53StressSM6/index.json --automation-output ue-automation-sm6-stress.json`. To include stress-category cases in UE automation, pass a single execution-command string: `-ExecCmds="Automation SetFilter All;RunTests AbuM53"`. Starting a second `Automation` command can reset the filter. The large radix-sort stress case verifies exact output pairs; its count is not a rendered-splat benchmark.

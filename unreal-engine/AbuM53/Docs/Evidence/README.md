# Compact validation evidence

These JSON files preserve results from Abu M53's original tests and synthetic fixtures. `Tools/QA/export_evidence.py` extracts the relevant records from the local validation workspace. Host/user names, machine identifiers, absolute paths and engine log text are excluded. Original report hashes are retained for provenance; the complete raw UE logs are not redistributed.

- `portable-core.json`: portable C++ assertions and CTest completion.
- `ue-automation-final.json`: eight SM5 plugin automation tests, comparison counts and test hardware/configuration.
- `ue-automation-sm6-stress.json`: nine SM6 tests including the 16,776,961-element stable-sort dispatch-boundary stress case. This is a sorting test, not a render-count/FPS result.
- `import-smoke.json`: original PLY/.splat/sequence imports, frame seeking and map creation.
- `spz-import-smoke.json`: original SPZ v1–v4 acceptance/rejection checks.
- `backend-image-comparison.json`: captured-image hashes and RGB error metrics; the screenshots are separate local artifacts.
- `shipping-compile.json`: Win64 Shipping compile/link result with no editor-module/UnrealEd linkage.
- `shipping-cook.json`: cooked, packaged and launched Shipping static-fixture smoke, clean render-image hash and explicit scope limits. Packaged animation/performance are unverified.
- `synthetic-benchmark.json`: explicitly rendered 1M/5M selected-input offscreen workload, counters, aggregate GPU frame times and limitations; no presented FPS claim.
- `source-package-roundtrip.json`: generated-manifest handling and byte-identical unpack/audit/repack regression on temporary test stubs.
- `v0.0.0.3-validation.json`: current import/save measurements, 18 strict UE regression results, 20 Earth Details checks and three-frame 3M-splat Skate playback/cache evidence. Private dataset bytes, screenshots and absolute paths are excluded; source report hashes identify the local originals.
- `v0.0.0.4-validation.json`: 19-test suite including the About tab, provenance/tool safeguard results, source-review fingerprint and native menu/document inspection. No new renderer benchmark is claimed.

See [Validation.md](../Validation.md) for interpretation and limits. The first hidden-viewport timing attempt was invalid because it did not establish that the renderer ran for every measured frame; it is excluded from benchmark evidence. High-count FPS claims require explicit rendered-view verification and a separately reviewed result.

These are development-snapshot results. Tests may cover an earlier compiled snapshot than subsequent changes; build/runtime evidence must be rerun when relevant implementation changes affect its scope. These reports do not certify arbitrary datasets, other vendors or unrestricted publication rights.

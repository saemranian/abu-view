# Abu M53: import, Details editing and PLY animation walkthrough

Development release: v0.0.0.3. This work continues the original implementation plan's importer, asset storage and animation milestones. The full production roadmap remains tracked in [ImplementationStatus.md](ImplementationStatus.md).

## What changed

1. Investigated the reported import dialog. Its long pause was during **asset saving**, after decoding. In normal editor packages, the old reflected byte array serialized each packed byte separately. A versioned native frame serializer now writes the payload in one contiguous block.
2. Retained the old tagged-property reader for existing assets. The first load of an old asset still uses its original representation. Saving upgrades that asset. Keep a backup before migration: older plugin releases cannot read the upgraded representation. Benchmarks used separate assets. After validation, the original Earth package was upgraded with its verified v2 backup preserved; project map hashes remained unchanged.
3. Replaced per-attribute binary PLY reads with bounded chunks of at most 1 MiB and 4096 vertices. The decoder preserves mixed scalar types, both byte orders, SH3, double precision source positions and validation. ASCII and list-bearing PLY files retain the general parser. Truncated binary bodies are rejected before reserving a large decoded cloud.
4. Moved editor decoding to a worker and added truthful read/bounds/packing stage messages. Cancellation is checked in bounded PLY/conversion work; the worker finishes safely before the factory returns. Decompression calls and stable-ID sorting may still delay cancellation. Failed or canceled reimports retain the old asset.
5. Fixed the Details refresh lifecycle. Unreal temporarily unregisters components during edits; the old code cleared point data but retained the keys that marked it as cached. The updated component retains valid data across those refreshes, checks cache validity, and clears stale data when the source or its revision changes.
6. Extended the configurable external frame cache to 8192 MiB and retained recently used frames while they fit the budget. Displayed-frame diagnostics distinguish the decoded sample ready for drawing from the requested timeline position. Paused seeks also progress through component ticks; the diagnostics alone do not prove that a frame was presented on screen.
7. Added a preparation tool and real sequence validation workflow. Private PLY frames and generated UE assets stay outside the plugin repository.
8. Added a separate, bounded GPU source cache. Previously, changing the displayed sequence sample replaced the component's sole GPU source buffer, uploading the full sample again on each loop. The cache now retains recently used immutable samples across loops when they fit its budget. Uploads retain the CPU allocation until the render graph finishes, avoiding an additional full-payload CPU staging copy.
9. Guarded covariance projection at the camera's clipping planes and for means far outside the view. Screen-space splats now reject centers outside Unreal's valid clip-depth interval, including its reversed-Z near plane. Perspective derivatives use a normalized-device-coordinate guard band of `[-1.3, 1.3]`; the actual projected center stays unchanged, and orthographic derivatives remain exact. This bounds unstable off-axis footprints without modifying source records. Center clipping and this derivative approximation do not implement exact clipping of a Gaussian that straddles the near plane.

## Importing a static cloud

Use the Content Browser's Import action for a supported Gaussian PLY, SPLAT, SPZ or AM53 file. The progress dialog names the current stage. Drag the imported Abu M53 asset into the level. Save the asset after import, then edit the actor's transform and Abu M53 component controls normally.

The default embedded import budget remains 1 GiB of packed point data across the entire asset. Records retain FP32 SH0–3 and shape at 256 bytes per splat. This release improves throughput without reducing point count or precision. Parser temporary memory, GPU uploads and GPU buffers are additional to that budget.

## Preparing the three Skate frames

Run the preparation tool from the source checkout, with private output outside Git:

```powershell
python Tools/Sequences/prepare_ply_sequence.py --source '<PLY-folder>' --output '<new-prepared-folder>' --fps 30
```

The tool naturally sorts the filenames, verifies the binary layouts, preserves all input records and writes a schema-1 `sequence.am53seq`. Copies are the default. An explicit `--hardlink` option can avoid duplicate storage on the same volume, with a copy fallback; linked data must not be edited through either path.

The supplied Skate files contain three independent frames of 3,000,000 SH3 splats each. Each frame needs 768,000,000 packed bytes; the complete clip needs 2,304,000,000 bytes. Use external storage and **Streaming Cache MiB = 3072** to retain all three frames. The default 512 MiB cache is too small for one of these frames under the current one-third frame reservation rule.

Also set the GPU source cache in the Unreal console:

```text
r.AbuM53.SourceCacheMiB 3072
```

These are independent budgets: the Details setting retains decoded CPU samples, while the console setting retains GPU source buffers globally across Abu M53 components. Both caches must fit the samples to avoid repeated disk decoding and GPU uploads during a short loop. The GPU setting defaults to 2048 MiB and is clamped to 0–8192 MiB. Zero disables GPU retention. The default can reserve a full 5-million-point source; larger sources or multiple actors need an appropriate aggregate budget.

PLY files provide neither timing nor trustworthy point identities here. The preparation uses an explicit assumed 30 FPS and sample-and-hold playback. It does not invent interpolation between unrelated rows. Three samples form a short loop, not a complete long animation or an analytic/neural 4D model.

An external sequence asset keeps references to the prepared frame files. Preserve that whole folder. External frames are not automatically cooked into a packaged game. Keep user datasets out of the plugin source archive and Git history.

## GPU cache behavior and measurement

The GPU cache identifies an immutable decoded allocation and its component, retains buffers by recent use, and evicts completed buffers when it needs space. It holds CPU samples weakly after upload so it does not silently extend their decoded-cache lifetime. A sample currently being uploaded remains protected until graph execution completes; another view in the same graph can reuse that pending source. References from one render graph are never passed to a different graph.

Pending admissions reserve a conservative padded allocation size. Completed entries use the GPU pool's actual aligned size for accounting. If the budget is reduced during an upload, existing pending reservations remain counted until their graph completes, then the cache applies the smaller budget. A source too large for the budget, or a miss while protected entries occupy the available space, uses an uncached upload and still draws. Such a source may upload again every frame. Unused completed entries also expire after 120 view-family callbacks; this is not a fixed number of seconds.

The renderer uploads the **full source allocation**, even when `Max Visible Splats` or `r.AbuM53.MaxSplats` selects fewer points for drawing. Reducing those controls does not shrink the source buffer. The GPU cache budget excludes active graph lifetimes, transient uploads, sort/project/tile buffers and the engine's resource pools. It is not a cap on total VRAM or process memory. The current signed 32-bit packed-frame array also prevents importing an arbitrarily large single source; the 8192 MiB aggregate GPU cache does not remove that representation limit.

CSV captures expose these metrics in the `AbuM53` category:

| Metric | Meaning |
|---|---|
| `SourceUploadCount`, `SourceUploadMiB` | Upload operations and unpadded source payload MiB accumulated during the CSV frame |
| `SourceCacheHits` | Reuse of completed cached source buffers |
| `SourcePendingReuses` | Reuse of a pending source by another view in the same render graph |
| `SourceCacheEvictions` | Completed entries removed for budget, expired identity or inactivity |
| `SourceUncachedUploads` | Uploads that cannot be retained, including disabled caching |
| `SourceCacheResidentMiB` | Latest gauge of aligned completed source allocations retained by the cache |
| `SourceCacheReservedMiB` | Latest gauge of protected reservations awaiting graph completion |
| `SourceCacheEntries` | Latest count of completed and pending entries |

Counts and upload MiB accumulate across views; gauges report the latest observation and may precede graph completion. A fitting three-frame loop should need only its initial three source uploads while those allocations remain cached. Confirm this in captures alongside actual displayed frame indices and image checks. Cache hits, rendered-view counts and sample changes are not measurements of presented FPS. Measured timings and test outcomes belong to the release record rather than this walkthrough.

## Validation and ongoing updates

Portable regression tests cover chunk boundaries, mixed properties, both endiannesses, lists, truncation and cancellation. UE automation covers old/new serialization, malformed payloads, Details property edits, component reconstruction, source replacement and retained sequence playback. GPU automation includes byte-exact source-cache reuse, eviction, disabled caching, pending budget changes, upload lifetime and guarded projection cases. Real-file validation measures import and save independently, then checks displayed frame indices/counts, playback, cache telemetry and GPU screenshots in isolated test levels in `abu_M53_Test_01`.

The definitive measured results and installation verification belong to the [v0.0.0.3 release record](Changes/v0.0.0.3.md). Future completed changes must bump the version, update documentation, rebuild/install, verify hashes, commit and tag under the [version workflow](Version_Control_and_Change_Workflow.md).

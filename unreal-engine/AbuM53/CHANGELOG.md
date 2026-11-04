# Abu M53 change history

Versions follow the four-part decimal carry convention in [the workflow](Docs/Version_Control_and_Change_Workflow.md). Each release links to its step-by-step record.

## v0.0.0.4 — About tab and maintained repository provenance

- Added a packaged About tab, a full origins and licensing document, reviewed implementation ledger, and shared ChatGPT/Antigravity contribution requirements.
- Validation: 19 UE tests passed with RHI validation, including the new About test; 8 provenance, 3 version and 11 deployment tests plus four packaging checks passed. Editor/Development/Shipping builds and native menu/tab inspection passed; installed files verified.
- [Step-by-step record](Docs/Changes/v0.0.0.4.md).

## v0.0.0.3 — Fast PLY import, stable Details editing and large sequence playback

- Fixed slow PLY import/save and disappearing splats after Details edits. Added retained CPU/GPU sequence caches, external index imports, near-camera projection guards and cancellable import feedback.
- Verified all three supplied Skate frames at 3,000,000 splats each, native playback and saved-level reopen. Warm playback recorded zero additional GPU uploads. Earth import improved from 8.508 s to 2.751 s and package save from 47.059 s to 0.744 s on the reference PC.
- Validation: 138 portable assertions, 18 UE tests with RHI validation, 33 Python unit tests, four packaging checks, 20 real Earth Details captures, and Editor/Development/Shipping builds passed. Updated the installed UE plugin and preserved a backup when upgrading the original Earth asset.
- [Step-by-step record](Docs/Changes/v0.0.0.3.md).

## v0.0.0.2 — Engine installation and persistent UE 5.8 test project

- Added audited Win64 BuildPlugin packaging, engine installation, installed-file verification and safe backups.
- Added the persistent `abu_M53_Test_01` project setup with static and animated sample maps; development releases now require a version bump and installed-copy refresh.
- Fixed missing explicit RHI static-state includes exposed by standalone Development compilation, and included required configuration in the package.
- Validation: editor/Development/Shipping build passed; three version tests, four deployment tests, four package roundtrip checks, four fixture imports and eight UE DX12/SM6 tests passed; GPU screenshot inspected.
- [Step-by-step record](Docs/Changes/v0.0.0.2.md).

## v0.0.0.1 — Initial Git baseline and documented implementation

- Record the existing importer, animation, GPU/CPU rendering and validation work as the first real Git snapshot.
- Add an implementation walkthrough, a durable change-documentation policy and a tested version-management helper.
- Set current plugin, CMake and documentation metadata to the user-requested starting version.
- Preserve the earlier `0.1.0-dev` archive and test evidence as historical artifacts; the numbering reset changes the release convention, not the implementation.
- Details: [v0.0.0.1 change record](Docs/Changes/v0.0.0.1.md).

There was no Git history for the prior implementation session. Its chronology is documented retrospectively, not represented as invented past commits.

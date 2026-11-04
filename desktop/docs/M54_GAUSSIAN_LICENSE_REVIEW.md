# Abu M54 Gaussian prototype: licensing and publication scope

2026-10-26 provenance update: the detailed maintained inventory and About tab are
documented in [M54_PROVENANCE_AND_LICENSES.md](M54_PROVENANCE_AND_LICENSES.md).
An additional concrete combination issue is now explicit: the ordinary shared
PLY reader uses GPLv3 python-plyfile 1.1.3, also required by Viser, and the native
host's comparison helpers import Viser. Viser's shipped LICENSE is Apache-2.0
despite its MIT metadata. Apache on the original Gaussian modules does not resolve
the GPL/custom-VGGT compatibility question. No code is relicensed by this update.

Review date: 25 October 2026. Baseline inspected: Abu Align & Train 0.1.7.7.

v0.1.8.0 scope addition: the original sequence model, GPU cache, player UI and
sequence regression tests are listed in `M54-GAUSSIAN-NOTICE.txt` under the same
Apache-2.0 grant. They use the existing local parser and renderer; no upstream
source, deformation network, model weights, dataset or new runtime is bundled.
Temporal video export uses the existing external encoder policy. The whole-app
restrictions discussed below still apply.

The new, independently authored Gaussian modules can be published under the
included Apache-2.0 grant. This does **not** establish that the entire existing
Abu Align & Train repository is uniformly open source or unrestricted. The
current public source export contains material governed by the custom VGGT
license, and several optional engines have separate restrictions. Those facts
cannot be resolved by changing a badge or replacing the root license.

This is a technical licensing inventory and implementation decision record,
not a legal clearance opinion or a patent freedom-to-operate search.

## What this prototype introduces

The exact original-source scope is recorded in
`licenses/M54-GAUSSIAN-NOTICE.txt`. The full Apache-2.0 terms are in
`licenses/M54-GAUSSIAN-APACHE-2.0.txt`. These cover the new Gaussian asset loader,
native GPU interface, independently authored GLSL shaders, benchmark and their
new tests. The renderer uses the already-installed Windows OpenGL driver through
the existing native M54 host. No upstream repository is changed or vendored,
and no third-party Gaussian rasterizer, research-model runtime or driver is
added by this prototype.

The license text was assembled from the existing packaging distribution's
unmodified Apache-2.0 terms, checked against the
[official Apache text](https://www.apache.org/licenses/LICENSE-2.0.txt), with its
standard appendix retained. The new modules should carry an Apache-2.0 SPDX
header and refer to the scoped notice. Apache-2.0 allows distribution and
modification subject to its conditions, including license and notice retention
and marking modifications. Its patent grant covers qualifying contributor
claims, not every possible third-party patent. See the
[license](https://www.apache.org/licenses/LICENSE-2.0) and
[official application guidance](https://www.apache.org/foundation/license-faq.html#WhatDoesItMEAN).

The new grant does not apply to code imported by these files, existing M54 host
files, retained upstream code, assets or checkpoint data. Adding an SPDX line
to pre-existing third-party-derived code would not grant rights the project
does not own. The project owner's ownership and contributor authority must be
recorded as further contributions arrive.

## Existing publication blockers and qualifications

| Area | Observed evidence | Required treatment |
| --- | --- | --- |
| Root/source identity | `LICENSE.txt` contains the July 2025 VGGT custom grant; `pyproject.toml` points to it. `installer/public-files.json` exports retained `vggt/` source. | Preserve notices. Do not describe the entire repository as Apache-2.0 or claim all source meets the OSI definition. To offer a purely OSI-licensed core, audit provenance, separate or replace restricted material, then qualify a distinct export and dependency graph. |
| Native core dependencies | The existing builder collects dependency notices and a CycloneDX inventory. Native wheel dependencies may have terms beyond their Python package metadata. | Review the exact shipped wheels, DLLs and notices; an automated inventory is evidence, not a license compatibility decision. |
| VGGT-Omega / VGG-T3 | The engine catalog marks them external research integrations. Their grants restrict commercial use. | Keep their code/weights out of an unrestricted core; preserve explicit scope and user obligations for optional integrations. |
| ACE0 | Its grant limits use and permits redistribution in source form only. | Do not freeze or bundle its upstream runtime in the core or imply that a free installer makes binary redistribution permissible. |
| PFGS360 | The inspected upstream repository has no established complete top-level grant, as already recorded in `THIRD_PARTY_NOTICES.md`. | Hold redistribution of its unqualified additions/checkpoints pending permission or a verified grant; a copied Apache header in some files is insufficient. |
| LichtFeld trainer | The local engine catalog describes a pinned, separate GPLv3-or-later executable with a GPU-library exception and corresponding-source assets. | Keep its own license/source obligations. Do not copy its code into this new renderer without evaluating the resulting license combination. Recheck the exact distributed revision and exception before publishing that trainer. |
| User/exported assets | A parser accepting PLY or another format does not establish rights in its model or training data. | Ship synthetic tests only. Keep client images, models, paths, screenshots and local logs out of public releases unless separately authorized and licensed. |

The [Open Source Definition](https://opensource.org/osd) permits commercial use
and does not allow discrimination by field of endeavor. The retained
[VGGT terms](https://github.com/facebookresearch/vggt/blob/main/LICENSE.txt)
incorporate an acceptable-use policy and require redistribution under that
agreement. These are distinct from the standard Apache-2.0 grant for the new
files. A public, free GitHub repository can have mixed or source-available
licenses; that alone does not make every part OSI open source.

The relevant optional-engine primary sources are the
[VGGT-Omega license](https://github.com/facebookresearch/vggt-omega/blob/main/LICENSE),
[VGG-T3 license](https://github.com/nv-dvl/vgg-ttt/blob/main/LICENSE),
[ACE0 license](https://github.com/nianticlabs/acezero/blob/main/LICENSE), and
[PFGS360 repository](https://github.com/zcq15/PFGS360). The current LichtFeld
pin and its packaging obligations were read from the local engine catalog;
fetching its pinned exception URL was unavailable during this review, so this
review does not newly qualify that existing runtime.

## Why no upstream shader was imported

The [Graphdeco Gaussian-Splatting license](https://github.com/graphdeco-inria/gaussian-splatting/blob/main/LICENSE.md)
limits its software to research/evaluation use unless additional permission
is obtained. Merely translating or renaming that implementation would not
remove its license. This prototype therefore uses independently written code
for mathematical operations and file conventions. It does not claim an
independent implementation eliminates patent or model-use obligations.

The driver remains an installed system prerequisite. No GPU-vendor driver or
SDK license is being redistributed by this prototype. The project must not
claim Khronos certification or endorsement; API capability reporting is not
certification. [Khronos legal and trademark guidance](https://www.khronos.org/legal/).

## Release actions for this increment

1. Retain the new file-level license headers, both scoped license files, this
   review, and the existing root and third-party notices in the approved source
   export and installed payload where applicable.
2. Verify all new renderer imports are covered by the existing runtime or the
   explicit manifest. Do not silently acquire a renderer, shader or model from
   an unreviewed repository at first launch.
3. Preserve a source/notice provenance record and exact dependency versions.
   Test an installed build; a working developer checkout is insufficient.
4. Keep benchmark results reproducible with synthetic generators. Local client
   model tests may remain private; public result documents must omit private
   paths and data unless authorized.
5. Use the existing public-export allowlist and dry-run review before any
   authorized push. This implementation does not authorize a remote push.

## Route to a fully open-source M54 release

The v0.1.7.9 close-up fix and Render Studio add original camera/path, UI, native
offscreen-target and export-worker modules to the scoped Apache-2.0 notice.
No upstream renderer was copied or modified. The worker invokes an existing
FFmpeg executable; it does not download or bundle one. A local binary with
NVENC and libx264 was tested, but is not part of this source release. FFmpeg
builds enabling GPL components such as libx264 have different redistribution
requirements from LGPL-only builds. Any future bundled encoder needs its own
exact-build source, notices and licensing review. See the
[official FFmpeg license guidance](https://ffmpeg.org/legal.html).
The existing whole-application licensing limitations below still apply.

Publish the new modules with their scoped Apache-2.0 license now when a release
is authorized. For the entire standalone M54 app, next inventory the complete
host/import graph and each file's provenance. Identify which original host
code the owner can license; isolate or replace retained restricted source and
unnecessary research dependencies without stripping notices. Build a separate
approved standalone export with exact notices and an OSI-compatible dependency
set, then test it offline. That is a concrete path to a clearly licensed M54
distribution; it must not be represented as completed by this prototype.

For the whole Align & Train suite, the restricted optional engines and model
rights still require distinct distribution choices or permissions. A final
qualified review of the actual release bill of materials is needed before
claiming legal clearance or unrestricted commercial use. Neither free pricing,
an Apache license on new code, nor downloading a component after installation
removes an upstream restriction.

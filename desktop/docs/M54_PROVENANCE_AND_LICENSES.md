# Abu 3D Viewer M54: provenance and open-source licenses

Reviewed: **2026-11-01** (initial publication **2026-10-26** with **v0.1.8.1**; updated for Visual Matcher companion modules and manifest review). The application header
reads the running version from VERSION.txt; this review date records the source
and dependency audit, independently of later suite version changes.

## Overview

Abu M54 is the shared reconstruction, camera, point-cloud and Gaussian viewer
developed for Abu Align & Train. The project owner directs its design, assisted
by ChatGPT/Codex and Antigravity agents. Those agent names describe development
assistance, not a transfer of copyright or permission to relicense upstream work.
Third-party authors retain their own copyrights. Individual historic agent
authorship is not fully recorded; this document does not invent per-line credits.

M54 combines original Abu implementation work, reused Abu application helpers,
third-party runtime libraries, platform APIs, and file-format compatibility.
These are different relationships with different licensing consequences.

The independently authored Gaussian/render/sequence modules and new About/audit
modules have a **file-scoped Apache-2.0 grant**. The full application currently
has **mixed terms**, including the retained root VGGT agreement and a GPLv3 PLY
dependency. A free GitHub download is not evidence that every file is unrestricted
or that the complete dependency combination is ready for redistribution.

This is an engineering provenance inventory, not a guarantee of legal clearance.
It records observed evidence and unresolved questions so a release can be reviewed
accurately. See the full local terms under the **Full license texts** tab.

## Original Abu M54 implementation

The source history and existing scoped notices identify the following project
implementation. Calling code original here means it is recorded as authored in
this project rather than imported from a named upstream renderer; it does not
mean that dependencies, standard algorithms, or file conventions were invented
by Abu, or that every historic file already has an independent license grant.

- `abu_m54.py`: shared scene records, float64 transforms, coordinated cloud/camera/
  control transforms, selection math, null-object data, file adapters and explicit
  transformed-copy exports. Uses NumPy/SciPy and the format/library adapters below.
- `abu_m54_native.py`: Windows OpenGL context and viewport, navigation, selection,
  ground grid, camera frustums, linked transforms and host integration. Calls the
  system driver through Python ctypes; no PyOpenGL or third-party native viewer.
- `abu_m54_browser.py`: Abu scene adaptation, normalized world/display frames,
  navigation policy, transforms, nulls, selection and local-server lifecycle.
  Built on **Viser**; browser rendering/UI infrastructure is not authored by Abu.
- `abu_m54_app.py`, `abu_m54_launcher.cs`: standalone opening, isolated load worker,
  Windows launch and per-user Open-with registration. Existing .NET and OS APIs.
- `abu_m54_host.py`: reuses the Manual control points editor's widgets and log
  interface. It is an adapter into existing Abu UI, not an independent application
  framework or license boundary.
- `abu_m54_desktop.py`, `abu_m54_ui.py`: DPI/icon identity, theme, tooltips and dock
  widgets. Uses Tcl/Tk and Pillow; the Abu A icon is a project asset whose owner
  must retain its actual asset provenance.
- `abu_m54_tools.py`, `abu_m54_editing.py`, `abu_m54_inspector.py`: scene tools,
  numeric dragging, undo/redo, exact pose readouts, nulls and mouse gizmo behavior.
- `abu_m54_details.py`, `abu_m54_fileinfo.py`: scene/file information and inspection.
- `abu_m54_help.py`: offline document reader and Guide/About tabs, with Pillow for
  local guide illustrations. Browser links open only after an explicit click.

The following modules are explicitly covered by the scoped Apache-2.0 notice:

- `abu_m54_gaussian.py`: original bounded Gaussian PLY reader and attribute packing.
- `abu_m54_splat_gpu.py`, `abu_m54_splat_shaders.py`: original GPU buffer interface,
  compute projection/sorting, spherical-harmonic evaluation and alpha rendering.
  Uses OpenGL, NumPy and the published Gaussian conventions; no upstream Gaussian
  rasterizer implementation is included.
- `abu_m54_cameras.py`: render-camera records, paths and interpolation using SciPy.
- `abu_m54_offscreen.py`, `abu_m54_render.py`, `abu_m54_render_ui.py`: shared-renderer
  offscreen output, isolated export jobs and Render Studio UI. FFmpeg is invoked
  as a separately installed executable for video output.
- `abu_m54_sequence.py`, `abu_m54_sequence_gpu.py`, `abu_m54_sequence_ui.py`: numbered
  PLY discovery, timing, bounded CPU/GPU caches, background preparation, staged
  uploads, timeline and temporal export integration. No research deformation model.
- `benchmark_m54_gaussian.py` and the exact tests named in the scoped notice:
  synthetic fixtures, quality checks and performance measurements.
- `abu_m54_about.py`, `m54_provenance.py`, `tests/test_m54_about.py`: original About
  presentation and source/dependency review guard added in v0.1.8.1.

The exact grant is [M54-GAUSSIAN-NOTICE.txt](../licenses/M54-GAUSSIAN-NOTICE.txt)
and [Apache-2.0 full text](../licenses/M54-GAUSSIAN-APACHE-2.0.txt). Older host/UI
files without an explicit independent grant remain under the repository's existing
terms pending owner/contributor provenance review; this document does not relicense
them. The new About UI is not a license grant for the code it describes.

## Reused Abu application code

M54 builds on these existing local modules rather than copying their functionality
into a second viewer. This is intra-project reuse, not use of another GitHub
repository. Existing file notices and the enclosing project's terms still apply.

- `fast_viewer.py`: result discovery, legacy point/pose readers, camera import;
  its fallback loaders may call plyfile and Trimesh.
- `control_points_comparison.py`, `viewer_workspace.py`: A/B comparison, scene
  archives, camera pairing, similarity fitting and cloud-distance calculations.
  The latter imports Viser's Icon even in a native-host dependency graph.
- `workspace_3d.py`, `native_inspection.py`: colormaps, existing inspection/display
  helpers and main-workspace integration.
- `control_points_workspace.py`, `control_points_logging.py`: shared widgets,
  scrolling, error handling and local audit logs; the host imports these helpers.
- `control_points_3d.py`, `control_points_model.py`: control geometry and browser
  adapter support; control markers are derived from measurements, not guessed.
- `manual_camera_geometry.py`, `refined_exports.py`: calibrated camera/control
  geometry and reconstruction export adapters, with NumPy/SciPy/OpenCV.
- `abucam_dataset.py`: AbuCam companion calibration/pose format adaptation.
- `desktop_ui.py`, `rig_designer_ui.py`, `manual_ui_lifecycle.py`: theme, toolbar
  wrapping, application widgets and cleanup; `version_manager.py` supplies the
  running suite version. Main and Manual control points remain host applications.
  `desktop_ui.py` also exposes host shortcuts to standalone dataset preparation tools
  including `Visual Matcher` (`visual_matcher_*.py`, independently authored under
  Apache-2.0 with optional local Meta DINOv2-Reg4 Apache-2.0 / LightGlue Apache-2.0 /
  ALIKED BSD-3-Clause inference and zero-weight OpenCV CPU fallback; M54 itself does
  not import `visual_matcher_*`).

A pre-existing mirror-only `Abu_Align/abu_m54_camera_panel.py` is also retained
in the developer tree. It is absent from the canonical root, active M54 imports
and approved public/core manifests; its historic UI work has not been newly
relicensed or added to this release. Run provenance checks from the canonical
workspace or approved source export. A mirror with extra legacy source files
can correctly fail the new-module review check even when active files match.

M54 is not yet an isolated permissively licensed package merely because it has
its own executable. Some dependencies are imported through shared host helpers
even when their optional UI surface is not opened.

## Runtime repositories and their use

Versions below are the inspected developer environment and/or current core pins,
not a claim that every installed user environment is identical. Exact release
wheels, native libraries and their license files take precedence over labels.

- **CPython / Python standard library** — interpreter, ctypes, threading, JSON,
  subprocesses, paths and Tkinter bindings. Developer interpreter 3.11.16.
  [Repository](https://github.com/python/cpython), [PSF and historical terms](https://docs.python.org/3/license.html).
- **Tcl/Tk** — actual desktop widgets, events and windowing underneath Tkinter.
  [Tk repository and Tcl/Tk terms](https://github.com/tcltk/tk/blob/main/license.terms),
  [Tcl repository](https://github.com/tcltk/tcl). Retain their notices in binaries.
- **NumPy 1.26.4** — array storage, transforms, PLY decoding and GPU preparation.
  [Repository/license](https://github.com/numpy/numpy/blob/v1.26.4/LICENSE.txt),
  BSD-3-Clause at project level; BLAS/Fortran and wheel components have own terms.
- **SciPy 1.17.1** — rotations, interpolation, spatial queries, comparison math.
  [Repository/license](https://github.com/scipy/scipy/blob/v1.17.1/LICENSE.txt),
  BSD-3-Clause at project level; preserve included native-component notices.
- **Pillow 11.3.0** — icons, guide images, image inspection and render output.
  [Repository/license](https://github.com/python-pillow/Pillow/blob/11.3.0/LICENSE),
  MIT-CMU; codecs and bundled image libraries have additional notices.
- **Viser 0.2.23** — Python/browser scene primitives, WebGL client, camera controls,
  GUI widgets, transform gizmos and WebSocket transport. M54 writes its own adapter
  on top of these APIs. [Original repository](https://github.com/nerfstudio-project/viser)
  (now redirects to [viser-project/viser](https://github.com/viser-project/viser)).
  The locally installed LICENSE is **Apache-2.0**, despite its metadata saying MIT.
  Preserve actual license files; do not trust the metadata label alone.
- **python-plyfile 1.1.3** — ordinary geometry PLY import in `abu_m54.read_ply_geometry`,
  legacy fallback parsing and a Viser dependency. It is not limited to an unused
  optional route. [Repository/license](https://github.com/dranjan/python-plyfile/blob/v1.1.3/COPYING),
  **GPLv3**; preserve the complete grant and evaluate combination/source obligations.
  The original Gaussian reader being Apache does not remove this dependency.
- **COLMAP / PyCOLMAP 4.2.0** — read COLMAP reconstructions and adapt camera models;
  the viewer does not run an alignment solver just to display a scene.
  [Repository](https://github.com/colmap/colmap), [BSD-3-Clause guidance](https://colmap.github.io/license.html).
  The selected wheel's native dependencies need separate review.
- **Trimesh 5.1.0** — legacy point/mesh fallback reading and Viser dependency.
  [Repository/license](https://github.com/mikedh/trimesh/blob/main/LICENSE.md), MIT.
  Availability of this library does not imply that M54 is a full mesh editor.
- **psutil 7.2.2** — RAM availability and CPU-cache budgeting; Viser also depends
  on it. [Repository/license](https://github.com/giampaolo/psutil/blob/release-7.2.2/LICENSE), BSD-3-Clause.
- **OpenCV 4.11.0 / opencv-python 4.11.0.86** — shared calibrated-camera helpers and
  host image processing. [OpenCV license](https://github.com/opencv/opencv/blob/4.11.0/LICENSE)
  is Apache-2.0; [Python packaging scripts](https://github.com/opencv/opencv-python)
  carry MIT terms. The installed wheel's native/FFmpeg notices also apply.
- **FFmpeg** — external command-line video encoder; M54 does not vendor its source
  or binary. [Repository](https://github.com/FFmpeg/FFmpeg), [legal/build guidance](https://ffmpeg.org/legal.html).
  LGPL-2.1-or-later by default, GPL with selected components such as libx264;
  a nonfree build can be nonredistributable. NVENC availability is a capability,
  not a blanket redistribution license. Exact build configuration matters.
- **Windows / .NET / OpenGL driver** — OS windowing, WGL/OpenGL calls and C# launcher.
  No vendor driver or CUDA toolkit is supplied by the renderer. These are platform
  interfaces/prerequisites with their own terms, not Abu open-source code.
  [Khronos legal/API guidance](https://www.khronos.org/legal/).

The browser's JavaScript frameworks and the full pinned core dependency list are
enumerated in the appendices below. Viser's inclusion in the native helper graph
means the browser dependency/license inventory remains relevant to that host too.

## Browser client repositories

M54 uses Viser's existing prebuilt browser client rather than writing or vendoring
a second JavaScript renderer. Viser acknowledges **React**, **Three.js**,
**react-three-fiber**, **drei**, **Mantine**, **Vite/Rollup** and **vanilla-extract**.
See [upstream acknowledgements](https://github.com/viser-project/viser#acknowledgements).
Their contributions belong to their respective maintainers. The complete direct
package declarations observed in the installed 0.2.23 client are listed below;
declared semver ranges are not exact bundled versions or proof of license clearance.

An exact nested JavaScript lockfile/license rollup was not present in the inspected
wheel. Therefore a complete transitive JavaScript SBOM remains a **release review
item**. Build-tool declarations in package.json do not prove each tool is present
in the runtime bundle. Do not describe this appendix as a complete binary SBOM.

## Format compatibility and scientific references

Reading another tool's output does not mean embedding that tool's source or
obtaining rights to redistribute its models, checkpoints or client datasets.

- **OpenSfM** reconstruction JSON, rotation vectors and spherical/perspective
  camera records: adapter support. [Repository](https://github.com/mapillary/OpenSfM)
  uses BSD terms; no OpenSfM solver is embedded in the M54 renderer.
- **COLMAP** text/binary camera/point conventions: shared readers plus PyCOLMAP
  above; original engine licenses and native dependencies stay separate.
- **NeRF/Nerfstudio transforms JSON**: camera-to-world matrices and optical-axis
  conversion; [Nerfstudio repository](https://github.com/nerfstudio-project/nerfstudio).
  Format support alone does not import its training runtime or gsplat rasterizer.
- **RealityScan / RealityCapture YPR CSV**: uses the documented full world-to-camera
  formula, transposed for M54. [Formula reference](https://forums.unrealengine.com/t/please-help-us-understand-the-internal-external-camera-parameters-export/712503/2).
  RealityScan is proprietary; compatibility does not bundle or license that app.
- **Conventional Gaussian PLY**: log scales, opacity logits, scalar-first rotation
  and SH coefficients follow common 3DGS export conventions. Projection, SH,
  sorting and compositing were independently implemented for M54. The paper/format
  is a mathematical reference, not permission to copy a restricted implementation.
  [Graphdeco project and implementation license](https://github.com/graphdeco-inria/gaussian-splatting/blob/main/LICENSE.md).
- **Numbered PLY sequences**: exported independent Gaussian frames; no research
  4DGS network, deformation checkpoint, pretrained weight or frame correspondence
  algorithm is imported. **TUM / ACE0 pose text**, AbuCam JSON and M54 scene/null/
  camera-path formats likewise have reader or project-schema support.

No implementation from **Graphdeco Gaussian Splatting, Mip-Splatting, StopThePop,
LichtFeld Studio, NVIDIA sample/3DGRUT renderers, Brush, gsplat**, or a research
4DGS deformation renderer was added to the original native Gaussian modules.
Research comparisons are not dependency or copyright-attribution claims.

## Boundaries with alignment and training engines

Abu Align & Train also integrates 360DVO, OpenSfM, VGGT/VGGT-Omega, VGG-T3, ACE0,
PFGS360, COLMAP, PyCuSFM, Nerfstudio/gsplat, LichtFeld and image-processing tools.
These are producers/consumers or optional engines of the enclosing app, not
implementations of M54's native Gaussian rasterizer. Their individual scopes and
upstream repositories remain in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

The public suite export still includes retained **VGGT** source and its custom
agreement; [root LICENSE.txt](../LICENSE.txt) and
[upstream terms](https://github.com/facebookresearch/vggt/blob/main/LICENSE.txt)
must be retained. No evidence in this audit establishes that the entire shared
host graph can be relicensed Apache-2.0. Optional engine restrictions, absent
complete grants, weights and GPL executable/source obligations require their own
review; displaying their output in M54 does not resolve those issues.

## What open-source licensing means here

- **Apache-2.0 for the listed original files:** permits use, modification and
  redistribution under its conditions, including license/notice preservation,
  marking modified files and its contributor patent provisions. It does not
  overwrite another component's license. [Authoritative terms](https://www.apache.org/licenses/LICENSE-2.0).
- **MIT / BSD / MIT-CMU / PSF / Tcl/Tk:** generally permissive, subject to the exact
  notices and conditions. Retain copyrights, grants and disclaimers. Do not remove
  third-party attribution or claim endorsement.
- **GPLv3 dependency:** GPL is open source and allows commercial use, but carries
  copyleft and source-distribution conditions for covered combined works. Since
  M54 imports plyfile and Viser requires it, distribution must evaluate the actual
  combined dependency graph. The custom VGGT terms create a compatibility question
  that is unresolved here. Notice retention alone does not solve it.
- **Native/wheel components:** OpenBLAS, Fortran runtimes, image codecs, C/C++
  solvers, GEOS, Qt/FFmpeg components or other bundled libraries may have their
  own grants and exceptions. Review actual payload contents, not just PyPI labels.
- **Models and user data:** source-code licenses do not automatically license a
  trained scene, images, fonts, trademarks, checkpoints or patents. Public tests
  and examples must have permission; client data stays out of source releases.
- **Free versus open source:** zero price and public source access are different
  from satisfying the [Open Source Definition](https://opensource.org/osd).
  This application must currently be described with its mixed-license scope.

For an independently distributable M54, review and explicitly license owned host
code, isolate/replace restricted retained material, resolve GPL compatibility
(or remove/replace that dependency across the complete graph), obtain exact native
and browser notices/source obligations, and qualify the final standalone payload.
That is remaining release work, not a completed legal clearance in this version.

## Packaging tools and release evidence

**PyInstaller 6.22.3** creates the existing core runtime, not the M54 renderer.
Its GPL-with-exception terms permit bundling applications subject to their own
dependency obligations; some files use Apache-2.0.
[Official guidance](https://pyinstaller.org/en/stable/license.html).
**setuptools, wheel, pip-tools**, native packaging tools and platform installers
are build infrastructure; inclusion in an environment is not proof every tool
is embedded in the executable.

`installer/core-files.json` and `installer/public-files.json` are the source
allowlists; `installer/requirements-core.in` and `.lock` record pinned Python
requirements. The existing builder collects actual license files into
`THIRD_PARTY_LICENSES` and creates `sbom.cdx.json`. Its existing Viser metadata
label is not authoritative; the real LICENSE was checked during this audit.
An older locally built payload/SBOM is evidence of that build, not a new 0.1.8.1
installer qualification. The About tab lists bundled full notices when present.

## Keeping this document current

This file is the canonical text for both desktop **About** and browser **About**.
The UI reads it locally; agents must edit this source document, not a duplicate
hardcoded summary. No background web access, telemetry or dataset upload is used.

Both **AGENTS.md** (ChatGPT/Codex) and **GEMINI.md** (Antigravity) require every
M54 change to review origin, libraries, formats, grants and release contents.
`docs/M54_PROVENANCE_RECORD.json` records SHA-256 fingerprints for M54 files,
shared support and dependency/packaging inputs (text line endings normalized to
LF so Windows/Linux checkouts agree). New `abu_m54*.py` files are detected.
`python m54_provenance.py --check` fails on drift; version bumps, the release
checkpoint and release CI invoke it. Hashes detect stale review; they do not
prove authorship.

After reviewing actual code and updating this document/notice scopes, run:

```text
python m54_provenance.py --refresh --review-date YYYY-MM-DD --reviewer "Agent or reviewer" --note "Actual changes, evidence and unresolved license questions"
python m54_provenance.py --check
```

Put that review date in this document first. Never refresh hashes merely to silence
a failure. Update installer manifests, bundled notices, mirrors, walkthrough and
versioned backups; commit the review together with the code. Add source links,
exact revisions, copied/adapted-file notices and a license decision before bringing
in external code. Material with unclear provenance stays explicitly unresolved.

The guard covers M54 and its listed shared support/packaging inputs, not every
possible future dynamic import. Agents must extend the scope when architecture
changes. It cannot enforce another agent's behavior outside this workflow or
automatically decide whether a new license is compatible.

## Review history

- **2026-10-26 / v0.1.8.1:** audited M54 imports, original-module grants, shared
  helpers, installed license texts, core pins, browser package declarations and
  existing collected notices. Added About, this document and the release guard.
  Explicitly recorded GPLv3 plyfile and the Viser metadata/license mismatch;
  no upstream renderer or runtime was changed or newly bundled.
- **v0.1.7.8–v0.1.8.0:** original native Gaussian renderer, close-up/Render Studio
  and PLY-sequence increments. Historical evidence remains in the scoped Gaussian
  notice, architecture, prototype/render/sequence guides and version walkthroughs.

## Python dependency appendix

The following list is the complete 67-component inventory from the existing
local core build, cross-checked against current pins. It includes transitive,
platform and build packages of the enclosing core; it is not a claim all are
directly used by M54. Names/versions identify what must be reviewed in that build.
Existing collected license texts and per-package native notices are authoritative;
unknown/ambiguous metadata must be resolved before qualification. PyPI project
pages link to their maintainers' repositories.

- [altgraph](https://pypi.org/project/altgraph/0.17.5/) **0.17.5**
- [anyio](https://pypi.org/project/anyio/4.15.1/) **4.15.1**
- [attrs](https://pypi.org/project/attrs/26.1.0/) **26.1.0**
- [certifi](https://pypi.org/project/certifi/2026.7.22/) **2026.7.22**
- [charset-normalizer](https://pypi.org/project/charset-normalizer/3.5.2/) **3.5.2**
- [colorama](https://pypi.org/project/colorama/0.4.6/) **0.4.6**
- [colorlog](https://pypi.org/project/colorlog/6.12.0/) **6.12.0**
- [contourpy](https://pypi.org/project/contourpy/1.3.3/) **1.3.3**
- [cycler](https://pypi.org/project/cycler/0.12.1/) **0.12.1**
- [docstring_parser](https://pypi.org/project/docstring_parser/0.18.0/) **0.18.0**
- [embreex](https://pypi.org/project/embreex/4.4.0/) **4.4.0**
- [fonttools](https://pypi.org/project/fonttools/4.67.0/) **4.67.0**
- [h11](https://pypi.org/project/h11/0.16.0/) **0.16.0**
- [httpcore](https://pypi.org/project/httpcore/1.0.9/) **1.0.9**
- [httpx](https://pypi.org/project/httpx/0.28.1/) **0.28.1**
- [idna](https://pypi.org/project/idna/3.20/) **3.20**
- [ImageIO](https://pypi.org/project/ImageIO/2.38.1/) **2.38.1**
- [jsonschema](https://pypi.org/project/jsonschema/4.26.0/) **4.26.0**
- [jsonschema-specifications](https://pypi.org/project/jsonschema-specifications/2025.9.1/) **2025.9.1**
- [kiwisolver](https://pypi.org/project/kiwisolver/1.5.1/) **1.5.1**
- [lazy-loader](https://pypi.org/project/lazy-loader/0.6/) **0.6**
- [lxml](https://pypi.org/project/lxml/6.1.3/) **6.1.3**
- [macholib](https://pypi.org/project/macholib/1.16.4/) **1.16.4**
- [manifold3d](https://pypi.org/project/manifold3d/3.5.4/) **3.5.4**
- [mapbox_earcut](https://pypi.org/project/mapbox_earcut/2.1.0/) **2.1.0**
- [markdown-it-py](https://pypi.org/project/markdown-it-py/4.2.0/) **4.2.0**
- [matplotlib](https://pypi.org/project/matplotlib/3.11.2/) **3.11.2**
- [mdurl](https://pypi.org/project/mdurl/0.1.2/) **0.1.2**
- [msgspec](https://pypi.org/project/msgspec/0.22.0/) **0.22.0**
- [networkx](https://pypi.org/project/networkx/3.6.1/) **3.6.1**
- [nodeenv](https://pypi.org/project/nodeenv/1.11.0/) **1.11.0**
- [numpy](https://pypi.org/project/numpy/1.26.4/) **1.26.4**
- [opencv-python](https://pypi.org/project/opencv-python/4.11.0.86/) **4.11.0.86**
- [packaging](https://pypi.org/project/packaging/26.3/) **26.3**
- [pefile](https://pypi.org/project/pefile/2024.8.26/) **2024.8.26**
- [pillow](https://pypi.org/project/pillow/11.3.0/) **11.3.0**
- [plyfile](https://pypi.org/project/plyfile/1.1.3/) **1.1.3**
- [psutil](https://pypi.org/project/psutil/7.2.2/) **7.2.2**
- [pycollada](https://pypi.org/project/pycollada/0.9.3/) **0.9.3**
- [pycolmap](https://pypi.org/project/pycolmap/4.2.0/) **4.2.0**
- [Pygments](https://pypi.org/project/Pygments/2.21.0/) **2.21.0**
- [pyinstaller](https://pypi.org/project/pyinstaller/6.22.3/) **6.22.3**
- [pyinstaller-hooks-contrib](https://pypi.org/project/pyinstaller-hooks-contrib/2026.8/) **2026.8**
- [pyparsing](https://pypi.org/project/pyparsing/3.3.3/) **3.3.3**
- [python-dateutil](https://pypi.org/project/python-dateutil/2.9.0.post0/) **2.9.0.post0**
- [pywin32-ctypes](https://pypi.org/project/pywin32-ctypes/0.2.3/) **0.2.3**
- [referencing](https://pypi.org/project/referencing/0.37.0/) **0.37.0**
- [rich](https://pypi.org/project/rich/15.0.0/) **15.0.0**
- [rpds-py](https://pypi.org/project/rpds-py/2026.9.1/) **2026.9.1**
- [rtree](https://pypi.org/project/rtree/1.4.1/) **1.4.1**
- [scikit-image](https://pypi.org/project/scikit-image/0.26.0/) **0.26.0**
- [scipy](https://pypi.org/project/scipy/1.17.1/) **1.17.1**
- [setuptools](https://pypi.org/project/setuptools/79.0.1/) **79.0.1**
- [shapely](https://pypi.org/project/shapely/2.2.0/) **2.2.0**
- [six](https://pypi.org/project/six/1.17.0/) **1.17.0**
- [svg.path](https://pypi.org/project/svg.path/7.1/) **7.1**
- [tifffile](https://pypi.org/project/tifffile/2026.3.3/) **2026.3.3**
- [tqdm](https://pypi.org/project/tqdm/4.70.1/) **4.70.1**
- [trimesh](https://pypi.org/project/trimesh/5.1.0/) **5.1.0**
- [typeguard](https://pypi.org/project/typeguard/4.6.0/) **4.6.0**
- [typing_extensions](https://pypi.org/project/typing_extensions/4.16.0/) **4.16.0**
- [tyro](https://pypi.org/project/tyro/1.0.16/) **1.0.16**
- [vhacdx](https://pypi.org/project/vhacdx/0.1.0/) **0.1.0**
- [viser](https://pypi.org/project/viser/0.2.23/) **0.2.23**
- [websockets](https://pypi.org/project/websockets/17.2/) **17.2**
- [xxhash](https://pypi.org/project/xxhash/4.0.1/) **4.0.1**
- [yourdfpy](https://pypi.org/project/yourdfpy/0.0.60/) **0.0.60**

## Viser client dependency appendix

These are the 46 direct `dependencies` declarations from Viser 0.2.23's installed
`client/package.json`. Fourteen `devDependencies` declarations follow separately.
They are upstream's package declarations, including some tooling entries, not
exact nested bundle versions. Their own licenses and dependency notices survive
Viser's Apache-2.0 license. No extra JavaScript packages are installed by About.

### Declared dependencies

- [@mantine/core](https://www.npmjs.com/package/@mantine/core) `^7.16.0`
- [@mantine/dates](https://www.npmjs.com/package/@mantine/dates) `^7.16.0`
- [@mantine/form](https://www.npmjs.com/package/@mantine/form) `^7.16.0`
- [@mantine/hooks](https://www.npmjs.com/package/@mantine/hooks) `^7.16.0`
- [@mantine/notifications](https://www.npmjs.com/package/@mantine/notifications) `^7.16.0`
- [@mantine/vanilla-extract](https://www.npmjs.com/package/@mantine/vanilla-extract) `^7.16.0`
- [@mdx-js/mdx](https://www.npmjs.com/package/@mdx-js/mdx) `^3.0.1`
- [@mdx-js/react](https://www.npmjs.com/package/@mdx-js/react) `^3.0.1`
- [@msgpack/msgpack](https://www.npmjs.com/package/@msgpack/msgpack) `^3.0.0-beta2`
- [@react-three/drei](https://www.npmjs.com/package/@react-three/drei) `^9.64.0`
- [@react-three/fiber](https://www.npmjs.com/package/@react-three/fiber) `^8.12.0`
- [@tabler/icons-react](https://www.npmjs.com/package/@tabler/icons-react) `^3.1.0`
- [@types/node](https://www.npmjs.com/package/@types/node) `^20.11.30`
- [@types/react](https://www.npmjs.com/package/@types/react) `^18.0.33`
- [@types/react-dom](https://www.npmjs.com/package/@types/react-dom) `^18.0.11`
- [@types/three](https://www.npmjs.com/package/@types/three) `0.170.0`
- [@vanilla-extract/css](https://www.npmjs.com/package/@vanilla-extract/css) `^1.14.1`
- [@vitejs/plugin-react](https://www.npmjs.com/package/@vitejs/plugin-react) `^4.0.1`
- [await-lock](https://www.npmjs.com/package/await-lock) `^2.2.2`
- [clsx](https://www.npmjs.com/package/clsx) `^2.1.0`
- [colortranslator](https://www.npmjs.com/package/colortranslator) `^4.1.0`
- [dayjs](https://www.npmjs.com/package/dayjs) `^1.11.10`
- [detect-browser](https://www.npmjs.com/package/detect-browser) `^5.3.0`
- [fflate](https://www.npmjs.com/package/fflate) `^0.8.2`
- [hold-event](https://www.npmjs.com/package/hold-event) `^1.1.0`
- [immer](https://www.npmjs.com/package/immer) `^10.0.4`
- [its-fine](https://www.npmjs.com/package/its-fine) `^1.2.5`
- [mantine-react-table](https://www.npmjs.com/package/mantine-react-table) `^2.0.0-beta.0`
- [postcss](https://www.npmjs.com/package/postcss) `^8.4.38`
- [prettier](https://www.npmjs.com/package/prettier) `^3.0.3`
- [react](https://www.npmjs.com/package/react) `^18.2.0`
- [react-dom](https://www.npmjs.com/package/react-dom) `^18.2.0`
- [react-error-boundary](https://www.npmjs.com/package/react-error-boundary) `^4.0.10`
- [react-intersection-observer](https://www.npmjs.com/package/react-intersection-observer) `^9.13.1`
- [react-qr-code](https://www.npmjs.com/package/react-qr-code) `^2.0.12`
- [react-router-dom](https://www.npmjs.com/package/react-router-dom) `^6.10.0`
- [rehype-color-chips](https://www.npmjs.com/package/rehype-color-chips) `^0.1.3`
- [remark-gfm](https://www.npmjs.com/package/remark-gfm) `^4.0.0`
- [three](https://www.npmjs.com/package/three) `0.170.0`
- [uuid](https://www.npmjs.com/package/uuid) `^11.0.5`
- [vite](https://www.npmjs.com/package/vite) `^5.2.6`
- [vite-plugin-svgr](https://www.npmjs.com/package/vite-plugin-svgr) `^4.2.0`
- [vite-tsconfig-paths](https://www.npmjs.com/package/vite-tsconfig-paths) `^4.2.0`
- [web-vitals](https://www.npmjs.com/package/web-vitals) `^3.3.1`
- [ws](https://www.npmjs.com/package/ws) `^8.13.0`
- [zustand](https://www.npmjs.com/package/zustand) `^4.3.7`

### Development declarations

- [@types/msgpack](https://www.npmjs.com/package/@types/msgpack) `0.0.34`
- [@types/uuid](https://www.npmjs.com/package/@types/uuid) `^9.0.8`
- [@types/wicg-file-system-access](https://www.npmjs.com/package/@types/wicg-file-system-access) `^2023.10.5`
- [@typescript-eslint/eslint-plugin](https://www.npmjs.com/package/@typescript-eslint/eslint-plugin) `^7.4.0`
- [@typescript-eslint/parser](https://www.npmjs.com/package/@typescript-eslint/parser) `^7.4.0`
- [@typescript-eslint/typescript-estree](https://www.npmjs.com/package/@typescript-eslint/typescript-estree) `^7.4.0`
- [@vanilla-extract/vite-plugin](https://www.npmjs.com/package/@vanilla-extract/vite-plugin) `^4.0.6`
- [browserslist-to-esbuild](https://www.npmjs.com/package/browserslist-to-esbuild) `^2.1.1`
- [eslint](https://www.npmjs.com/package/eslint) `^8.43.0`
- [eslint-plugin-react](https://www.npmjs.com/package/eslint-plugin-react) `^7.32.2`
- [eslint-plugin-react-refresh](https://www.npmjs.com/package/eslint-plugin-react-refresh) `^0.4.1`
- [postcss-preset-mantine](https://www.npmjs.com/package/postcss-preset-mantine) `^1.13.0`
- [typescript](https://www.npmjs.com/package/typescript) `^5.0.4`
- [vite-plugin-eslint](https://www.npmjs.com/package/vite-plugin-eslint) `^1.8.1`

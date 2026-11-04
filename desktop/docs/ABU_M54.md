# Abu 3D Viewer M54 (Abu M54)

**About / provenance (v0.1.8.1):** the standalone About button and
**M54 tools → About · authorship & licenses** open the shared Guide/About tabs.
The browser's **Abu M54 · About** section uses the same maintained
[source and license inventory](M54_PROVENANCE_AND_LICENSES.md). All agents must
keep it current and pass `python m54_provenance.py --check` before release.

PLY-sequence playback and temporal export (v0.1.8.0): see
[M54_PLY_SEQUENCE.md](M54_PLY_SEQUENCE.md). `abu_m54_sequence.py` handles numbered
frame discovery and bounded CPU preparation through the shared parser;
`abu_m54_sequence_gpu.py` manages staged resident GPU frames;
`abu_m54_sequence_ui.py` drives the existing native navigator. App/tools are entry
adapters. No upstream deformation code or alternate parser/orbit is introduced.

Desktop Render Studio and close-up Gaussian stability (v0.1.7.9): see
[M54_RENDER_STUDIO.md](M54_RENDER_STUDIO.md). Render cameras and paths live in
`abu_m54_cameras.py`; `abu_m54_render_ui.py` supplies a shared host-independent
window; `abu_m54_offscreen.py` and `abu_m54_render.py` export through the same
Gaussian renderer in an isolated local process. Native host camera capture and
look-through use the existing navigator, not a second orbit implementation.

Abu M54 is the shared point-cloud and camera-reconstruction viewer in Abu Align &
Train. M54 is its development name pending the future combination with other Abu
3D tools. The embedded main workspace, Manual control points workspace and standalone
application use the same native GPU renderer. Browser surfaces share the scene,
file, transformation and navigation rules through a Viser adapter.

## Open and navigate

- Main app: **04 3D Workspace · Abu M54**, then **M54 tools**.
- Manual controls: each Left/Right selector offers **Image / Grid / 3D**. A 3D
  pane uses the shared M54 renderer with an independent viewpoint. **Tools** opens
  its M54 controls. The separate **3D view** navigator also remains available.
  See [the mixed-view workflow](MANUAL_VIEWS.md).
- Standalone: run `Abu_M54.exe`, then Open file or Run folder. Files also open through
  Windows **Open with → Abu 3D Viewer M54**. The registration is per-user and does
  not replace default applications. The standalone Windows Open with button can
  repair registration after moving the installation.
- Browser: use Browser in the control/standalone viewer, the main app's existing
  browser action, or `python abu_m54_app.py --browser path/to/model.json`.

Drag to orbit, middle/right-drag to pan and wheel to zoom. Click a control, camera
or displayed cloud sample to select it. **Orbit selected**, **O** or double-click
makes the selection the orbit pivot. **Fit** returns to a scene-centred view. Native
M54 tools optionally enables orbit-on-selection; browsers offer the same option
and an explicit Pick one cloud sample mode. Browser picking temporarily captures
one click, then restores normal orbit/pan; it is off by default. Picking never creates a
manual control measurement. It selects an existing display sample, not an arbitrary
surface intersection. Camera optics/frustums are illustrative, not calibrated ERP
perspective lenses.

M54 tools includes world-up selection, ground grid, XY/XZ/YZ plane, elevation in source scene units,
native point shading and size, camera size/trajectory, standard views and view
bookmarks. Existing main-viewer profiles, camera inspector, look-through, photo
inspection and A/B comparison remain available. In the control workspace,
**Compare reconstructions** retains its read-only B workflow and comparison report.

## Transform and export

### Inspect exact poses and create 3D nulls

Open **Objects / nulls** in the standalone/control viewer, or **M54 tools →
Objects, exact poses & 3D nulls** in the compact main workspace. Select an object
in the list or click it in the viewport. Drag the inspector's horizontal divider
to resize its object list and scrollable property form.

The inspector displays world XYZ, camera-to-world XYZ Euler degrees, a scalar-first
quaternion and the world-to-camera rotation vector/translation for cameras. Euler
angles can have multiple equivalent representations; the quaternion is authoritative.
Cloud samples and triangulated control markers have position but **no stored
orientation**. Their rotation fields show not defined. Their model's frame rotation
is shown separately. Display sampling means cloud picks inspect retained samples.

**Add null here** creates an independent world-space reference at the selected item
or current orbit pivot. A camera selection supplies its real initial orientation;
ordinary points start with an identity orientation. Edit a null's XYZ/rotation fields
to update it live, or enable **Mouse gizmo**, choose **Selected null** and drag RGB
arrow shafts for Move or rings for Rotate. Native tools offer World/Local axes.
Esc cancels a native drag; one drag is one Undo step. Rotate/move the camera view to
expose an end-on arrow or edge-on ring. Null Undo/Redo/Delete is separate from manual
control measurements and whole-model history.

Choose gizmo target **Layer A** or **Layer B** to move/rotate the entire reconstruction
with the mouse. All its cameras, cloud and controls move together. A fitted B layer
keeps its current world position when a manual gizmo edit starts and then uses that
manual transform. Uniform scale remains numeric in Scene tools. Camera and point
source data are read-only; this feature edits the linked model transform or independent
nulls, not individual reconstructed camera poses or bundle-adjustment observations.

**Save nulls / Load nulls** writes a separate `.m54nulls.json` document with full
float64 positions and XYZ-degree orientations. Sources in this file are metadata,
never automatically opened. Load is validated atomically and Undo can restore the
previous list. The standalone app asks to save unsaved nulls on close. Embedded hosts
and browsers require explicit Save nulls before closing. Nulls are not survey/GCP
constraints and are not inserted into reconstruction/training exports.

Browser **Objects & 3D nulls** provides the same precise readouts, independent nulls,
live pose fields, local Save/Load and mouse arrows/rings. **Scene tools → Gizmo target**
selects the reconstruction layer or selected null; **Gizmo operation** enables Move,
Rotate or both. Browser axes follow the object's orientation. Browser history groups
updates within 0.5 seconds because the installed Viser API has no drag-end event;
native drags have exact gesture boundaries. Opening the browser from an embedded
viewer copies a null snapshot; browser and desktop edits are separate previews. Save
the browser null document and Load it in the desktop to transfer edits.

Opening a reconstruction JSON also reads its adjacent `.controls.json` when valid,
triangulating markers in that reconstruction's frame. The background scene archive
preserves these markers. Untriangulated controls are not assigned guessed positions.

The standalone sets Windows DPI awareness before creating Tk and uses the existing
Abu green/white-A ICO on the actual titlebar as well as its compiled launcher.
The engine uses monitor pixel density instead of Windows bitmap stretching. Existing
Abu Align processes retain the DPI policy already set by their host.

Select A or B in scene tools, enter move XYZ in source units, rotate XYZ in degrees
and positive uniform scale. Valid values update immediately; no Apply click is
needed. Drag a numeric field left/right for easier adjustment, hold Shift for finer
steps or Ctrl for coarser steps. One native drag is one Undo step. An incomplete or
invalid keyboard number retains the last valid scene. Choose scene centre, a selected
item or world origin as the rotation/scale pivot. The browser also provides a move
and rotate gizmo; scale remains explicit numerically. Transformations move cloud
points, camera centres/orientations and triangulated control markers together.
Native history survives closing/reopening the tools window. Undo, Redo and Reset
affect the preview, and opening a different A model clears the previous model's
history. A manual B transformation disables automatic frame fitting so it is not
immediately fitted away.

**Export transformed copy** reads full source geometry, independently of the display
sample. It writes a new reconstruction JSON when appropriate, cloud PLY, exact
camera CSV and a `.m54.json` transform/provenance record. Generic point sources
export PLY/CSV. A new basename is required; existing targets/companions and sources
are protected. Transforms JSON camera rotations retain orthonormal optics; scale
changes camera positions and points, not the rotation matrix. Original image files
are not copied or altered. Source-relative image paths are rebased where they can
be resolved when exporting transforms JSON elsewhere.

Transforming a reconstruction is a coordinate/model operation, not bundle adjustment
or proof of improved accuracy. It does not transform surveyed coordinates in a
separate control file or regenerate existing training packages. Keep survey/control
frames consistent before refining an exported copy. Camera/cloud comparison values
measure agreement; fitting can remove an origin/rotation/scale difference you might
want to inspect. Keep fitting off when evaluating that difference.

## File support

| Input | Displayed data |
|---|---|
| OpenSfM/native spherical reconstruction JSON | Single component's points and exact poses |
| NeRF/Nerfstudio transforms JSON | Camera-to-world poses; OpenGL-to-OpenCV camera-axis conversion; companion cloud |
| PLY, binary or ASCII | XYZ and RGB when available; double coordinates preserved; companion camera CSV |
| Abu camera CSV | Named centres and explicit scalar-first camera-to-world quaternions |
| RealityScan-style camera CSV | `#name,x,y,alt,yaw,pitch,roll`; full documented world-to-camera YPR matrix, transposed to camera-to-world |
| COLMAP `images.txt` / `images.bin` | Exact image names and world-to-camera poses converted to centres/orientations |
| COLMAP `points3D.txt` / `points3D.bin` | Points/RGB and adjacent image poses if present |
| COLMAP cameras/rigs/frames files | Opens their surrounding model folder |
| TUM trajectories / ACE0 poses files | Existing engine-specific pose readers |
| XYZ / PTS | XYZ, optional RGB; PTS begins with a point count |
| M54 scene NPZ | Pickle-free scene archive |
| Completed engine run folder | Shared discovery of COLMAP, transforms, native reconstruction, cloud and poses |

### RealityScan camera rotations

The angle CSV importer uses [RealityScan's documented full rotation formula](https://forums.unrealengine.com/t/please-help-us-understand-the-internal-external-camera-parameters-export/712503/2).
CSV angles are degrees. The formula produces world-to-camera rotation; M54
transposes it, then stores a scalar-first camera-to-world quaternion. Matrix
columns are camera right, down and forward. Roll participates in the full Euler
rotation; it is not a spin around a forward vector computed from yaw/pitch alone.
In particular, a valid canonical roll of either +180 or -180 can reverse the
optical direction relative to a zero-roll pose with the same yaw and pitch.
Equivalent angle representations describe the same complete physical orientation.

The correction is in shared `abu_m54.load_scene()`, used by the embedded, browser
and standalone hosts. It does not adjust camera centers, rewrite export files,
guess hemispheres, alter JSON axes or change the explicit quaternion CSV branch.
Older Abu-generated angle CSVs may use the former optical-axis roll convention
despite identical column names. They cannot be distinguished reliably by guessing
from angle values; use their original reconstruction/transform JSON or an explicit
camera-to-world quaternion CSV for an unambiguous pose. This change does not
rewrite those legacy exporters or the user's correct UE exports.

Verification uses five small synthetic tests with an independent SciPy intrinsic
ZXY composition (`[-yaw, pitch-180, -roll]`). They check complete matrices,
orthonormality, determinant +1, unmodified float64 centers, quaternion import,
arbitrary roll, ±180, both hemispheres and pole-adjacent views. The new cases fail
against the old importer. A read-only local check through the actual importer also
confirmed all three 4,000-camera CSV/JSON representations point inward, with zero
center differences and maximum matrix difference below `5.35e-15`. The client pose
files and local audit reports are not bundled in test fixtures or public export.

Camera-measurement CSVs are not pose CSVs. Unspecified quaternion/Euler conventions
are rejected rather than guessed. Conventional Gaussian PLY now retains complete
attributes and renders through the original Windows OpenGL 4.3 compute prototype
in a single visible native layer (SH degrees 0-3). Browser, overlay and unsupported
GPU paths explicitly show sampled point previews. See `M54_GAUSSIAN_PROTOTYPE.md`
for measured evidence, limits and remaining 3DGS/4DGS phases. Intrinsics alone,
training weights, diagnostics and reports are not a camera reconstruction. Multiple
disconnected OpenSfM components require a separately selected component; they are
not silently merged into one frame. LAS/LAZ, E57, full mesh editing and CAD operations
are future adapters, not supported-format claims in this release.

## Responsiveness and precision

The control workspace's horizontal and vertical dividers use live resizing. Properties
and Measurements are separate vertical panes: drag their divider upward to enlarge
the table. The property form remains scrollable; Measurement actions provides left/
right opening, predictions, uncertainty and removal without tall permanent toolbars.
Image renders coalesce at a frame interval. While resizing, a coarser mip and nearest
preview reduce work; normal interpolation is restored after 100 ms without resizing.
Marker coordinates and original-image measurements are unchanged by preview quality.

World geometry/pose math stays float64. Native and browser adapters normalize the
display frame before float32 GPU vertex buffers, retaining detail at large world
coordinates. Camera frustums are vectorized and cached; GPU contexts and tool workers
close with their host. Control/standalone displays default to 50,000 points; the
main embedded loader retains up to 150,000, and main browser loading retains up to
one million before its selected display budget. Full exports do not use those caps.
JSON and text parsing can require more temporary RAM than the retained display.

Control/standalone comparison and loading use isolated workers. Main embedded run
loading uses a background worker; large JSON parsing can still contend for CPU time.
Browser geometry/controls remain on a loopback server. Public share requests are
denied on every M54 browser server instance, with the installed Viser hook workaround
retained. No upstream repository or installed package changes are required.

## Architecture for developers and co-development agents

| File | Responsibility |
|---|---|
| `abu_m54.py` | Shared float64 scenes, conventions, transform matrices, picking, grid and file/copy export |
| `abu_m54_native.py` | Shared Windows WGL/OpenGL renderer and interaction |
| `abu_m54_tools.py` | Native scene tools, history and background export |
| `abu_m54_inspector.py` | Modeless exact pose readouts, null object list and parameter editing |
| `abu_m54_editing.py` | Native axis/ring gesture adapter using shared float64 transforms and geometry |
| `abu_m54_desktop.py` | DPI setup before Tk and shared Abu desktop/window identity |
| `abu_m54_browser.py` | Shared browser tools/gizmo/pivots and standalone browser surface |
| `abu_m54_host.py` | Minimal host services/callback interface |
| `abu_m54_app.py`, `abu_m54_launcher.cs`, `Abu_M54.exe` | Standalone app, isolated loading and Open with registration |
| `native_inspection.py`, `viewer_workspace.py` | Main-app host adapters and existing inspection features |
| `control_points_native_3d.py`, `control_points_3d.py` | Control-tool compatibility/browser adapters |

New tools should use these adapters and shared math instead of introducing another
viewer fork. `control_points_native_3d.NativeControlNavigator` is a compatibility
alias for `M54NativeViewer`. Engine outputs remain the authoritative inputs until
the user explicitly exports a transformed copy.

## Research and verification

The selection/pivot workflow follows established
[CloudCompare point-picking](https://www.cloudcompare.org/doc/wiki/index.php/Point_picking)
and [Open3D interaction](https://www.open3d.org/docs/release/tutorial/visualization/interactive_visualization.html)
patterns. Group transformations and explicit matrix copies follow
[CloudCompare transformation concepts](https://www.cloudcompare.org/doc/wiki/index.php/Apply_Transformation).
[COLMAP's format specification](https://colmap.github.io/format.html) defines pose
direction, quaternion order and sparse point records.
[Viser's scene API](https://viser.studio/main/api/core/scene_api/) provides browser
gizmos and scene interaction; implementation was checked against installed 0.2.23,
whose gizmo has translation/rotation and a display-size parameter rather than a
uniform model-scale drag handle.

See `ABU_M54_VERIFICATION.md` for measured runtime, tests, limits and reproduction.
See `M54_OBJECTS_VERIFICATION.md` for the DPI/icon, pose/null/gizmo release checks.


Calibrated 360/perspective measurement and refinement use the full-resolution
`abu_m54.load_calibrated_alignment` API, with lens projection handled by
`manual_camera_geometry`. See [Manual control points](MANUAL_CONTROL_POINTS.md).

## Camera list panel
Opening a camera CSV (or pressing **Camera list**) docks a searchable list of every camera beside the viewport. Selecting a camera in the list or by clicking it in 3D highlights it in both places and shows its world position, XYZ rotation, quaternion, viewing/up direction and neighbour distances. Implemented in `abu_m54_camera_panel.py`.


The camera panel scales with display DPI, shows full-precision pose values in a scrollable readout, and can be resized by dragging its left edge, with **Wider**/**Narrower** buttons, or double-clicking the edge to restore the default width.

## v0.1.6.9 interface
One **Open** menu (file / result folder / Windows Open with), a universal collapsible **File details** panel on the right, a docked collapsible **M54 tools** panel on the left, minimal hover hints, icons and an in-app **Guide** (F1) rendered from `docs/ABU_M54_GUIDE.md`. See that guide for the illustrated tour.

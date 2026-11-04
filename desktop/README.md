# Abu View for Desktop (Powered by Abu M54 Engine · v0.1.8.3)

**Abu View for Desktop** is a native Windows GPU (`WGL/OpenGL` + compute shader) 3D Gaussian Splatting (3DGS), 4D PLY sequence, point cloud, and camera reconstruction viewer and scene transformation studio with full `float64` world-coordinate precision.

---

## Key Features

- **Native GPU Gaussian Splatting & Point Cloud Renderer**:
  - Hardware-accelerated OpenGL compute projection, radix sorting, spherical harmonics (SH0–SH3) evaluation, and alpha blending (`abu_m54_splat_gpu.py`, `abu_m54_splat_shaders.py`).
  - Preserves exact `float64` world coordinates in memory and normalizes display coordinates only when uploading `float32` GPU buffers.
- **4D PLY Sequence Playback & Temporal Export**:
  - Automatic numbered frame discovery (`frame_0000.ply`, `frame_0001.ply`, ...), bounded CPU/GPU frame caching, timeline scrubbing, and video/frame sequence export (`abu_m54_sequence.py`, `abu_m54_sequence_gpu.py`, `abu_m54_sequence_ui.py`).
- **Desktop Render Studio**:
  - Keyframed camera paths, spline interpolation, custom resolution & framerate offscreen rendering, and direct MP4/image sequence export via FFmpeg (`abu_m54_render.py`, `abu_m54_render_ui.py`, `abu_m54_offscreen.py`).
- **Scene Transformation, Exact Pose Inspector & 3D Nulls**:
  - Inspect exact world `XYZ`, Euler angles, and scalar-first quaternions for any reconstructed camera, point sample, or 3D null object (`abu_m54_inspector.py`).
  - Transform entire reconstructions (point clouds, camera frustums, and control markers together) and export transformed copies with a `.m54.json` provenance record.
- **Browser Companion Mode**:
  - Launch a local loopback browser viewer via `python abu_m54_app.py --browser path/to/scene.ply`.

---

## Supported File Formats

| Format | Description |
| :--- | :--- |
| **3DGS / Point Cloud `.ply`** | Binary or ASCII Gaussian Splatting & point cloud PLYs (`float64` coordinates preserved) |
| **4D PLY Sequences** | Numbered `.ply` frame sequences for temporal 4DGS playback & rendering |
| **COLMAP** | `images.txt` / `images.bin`, `points3D.txt` / `points3D.bin`, and model folders |
| **NeRF / Nerfstudio** | `transforms.json` camera-to-world poses + companion point clouds |
| **OpenSfM** | Spherical & perspective reconstruction JSON models |
| **Abu / RealityScan CSV** | Camera pose CSVs (`#name,x,y,alt,yaw,pitch,roll` and quaternion schemas) |
| **Point Clouds (`.xyz`, `.pts`, `.npz`)** | Raw ASCII point clouds and pickle-free M54 `.npz` archives |

---

## Installation & Quick Start

### Option 1: One-Click Windows Launcher
1. Install Python 3.10+ and the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Double-click **`Abu_View_Desktop.bat`** (or run `Abu_M54.exe` if using the `vggt` conda environment).

### Option 2: Command Line & File Association
```bash
# Launch the native desktop GUI
python abu_m54_app.py

# Open a specific PLY, COLMAP folder, or transforms.json directly
python abu_m54_app.py path/to/scene.ply

# Launch in local Web Browser mode (Viser adapter)
python abu_m54_app.py --browser path/to/scene.ply

# Register "Abu 3D Viewer M54" in the Windows right-click "Open with" menu
python abu_m54_app.py --register-open-with
```

---

## Provenance & License Verification

To verify source and provenance integrity at any time:
```bash
python m54_provenance.py --check
```
See [docs/M54_PROVENANCE_AND_LICENSES.md](docs/M54_PROVENANCE_AND_LICENSES.md) and [licenses/M54-GAUSSIAN-NOTICE.txt](licenses/M54-GAUSSIAN-NOTICE.txt) for detailed file-scoped Apache-2.0 and third-party licensing records.

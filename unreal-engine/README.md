# Abu View for Unreal Engine 5.8 (Powered by Abu M53 Engine · v0.0.0.4)

**Abu View for Unreal Engine** (`AbuM53`) is a native C++/HLSL DirectX 12 plugin for **Unreal Engine 5.8** designed to import, inspect, edit, and render static and animated 3D Gaussian Splatting (3DGS / 4DGS) assets across NVIDIA, AMD, and Intel GPUs without requiring CUDA.

---

## Key Capabilities

- **Vendor-Agnostic DX12 / HLSL Compute Pipeline**:
  - Global GPU radix-sort / quad rasterization path and bounded 16×16 tile renderer (`AbuM53Render`, `Shaders/Private/`).
  - Runs natively on Windows DirectX 12 across NVIDIA, AMD, and Intel GPUs without CUDA dependencies.
- **Multi-Format 3DGS & 4DGS Importer**:
  - **Standard Gaussian `.ply`** (Graphdeco-compatible SH0–SH3 attributes)
  - **Compact `.splat`** (32-byte format)
  - **Compressed `.spz` (v1–v4)** (including bundled BSD Zstandard decoder for SPZ v4)
  - **Native `.am53` & `.am53seq` Animated Frame Manifests**
- **4D Sequence Playback & Keyframe Interpolation**:
  - Supports both **independent-frame 3DGS sequences** (`independent_3dgs_frames`) and **stable-ID keyframe interpolation** (`stable_id_keyframes` with position, log-scale, quaternion, and SH interpolation).
  - Supports both embedded editor imports and bounded external streaming (`"storage": "external"`).

---

## Installation & Quick Start (Unreal Engine 5.8)

1. Copy the **`AbuM53`** folder into your Unreal Engine 5.8 project's `Plugins` directory:
   ```text
   YourUnrealProject/
   └── Plugins/
       └── AbuM53/
           ├── AbuM53.uplugin
           ├── Source/
           ├── Shaders/
           └── Core/
   ```
2. Right-click your `.uproject` file → **Generate Visual Studio project files**, then build the project in **Development Editor (Win64)** (or open the project in Unreal Engine 5.8 and click **Yes** when prompted to build `AbuM53Runtime`, `AbuM53Render`, and `AbuM53Editor`).
3. In Unreal Editor, go to **Edit → Plugins**, verify **Abu M53** is enabled, and restart if prompted.
4. Drag and drop a `.ply`, `.splat`, `.spz`, or `.am53seq` file into the **Content Browser**, place an **Abu M53 Actor** in your level, and assign the imported Gaussian asset.

For full technical documentation, CVar memory budgets (`r.AbuM53.SourceCacheMiB`), and sequence preparation tools, see [AbuM53/README.md](AbuM53/README.md) and [AbuM53/Docs/](AbuM53/Docs/).

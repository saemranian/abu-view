# Abu View — 3DGS, 4D Sequence, Point Cloud & Spatial Viewing Suite

**Abu View** is a cross-platform 3D Gaussian Splatting (3DGS), 4D temporal sequence, point cloud, and spatial scene viewing ecosystem across **Web**, **Unreal Engine 5**, and **Windows Desktop**.

🔗 **Live Web Platform**: [https://ahmademranian.dev/abuview](https://ahmademranian.dev/abuview)  
🌐 **Product Overview & Specs**: [https://ahmademranian.dev/products](https://ahmademranian.dev/products)

---

## Editions Overview

| Edition | Directory / Link | Core Engine | Target Platform & Highlights |
| :--- | :--- | :--- | :--- |
| **1. Abu View (Web)** | [ahmademranian.dev/abuview](https://ahmademranian.dev/abuview) | **Abu Web Engine** *(PlayCanvas v2.23.3, SparkJS v2.4.0, Three.js v0.187.0 & upcoming Abu M51 core)* | Cloud & browser-based 3DGS / 3D / WebXR viewer, multi-layer scene composer, smooth camera tour morphing, and interactive spatial webpage publisher. |
| **2. Abu View for Desktop** | [`./desktop/`](./desktop/) | **Abu M54** (`v0.1.8.3`) | Standalone Windows GPU (`WGL/OpenGL` + compute shader) viewer with `float64` coordinate precision for 3DGS `.ply`, 4D PLY sequences, COLMAP, OpenSfM, NeRF `transforms.json`, 3D nulls, and offscreen Render Studio. |
| **3. Abu View for Unreal Engine** | [`./unreal-engine/AbuM53/`](./unreal-engine/AbuM53/) | **Abu M53** (`v0.0.0.4`) | Native C++/HLSL DirectX 12 plugin for **Unreal Engine 5.8** supporting static and animated 3DGS / 4DGS (`.ply`, `.splat`, `.spz` v1–v4, `.am53seq`) across NVIDIA, AMD, and Intel GPUs without CUDA. |

---

## Direct Release Downloads

Pre-packaged archives for immediate installation are available in the [`./releases/`](./releases/) directory:

- 🖥️ **[Download Abu View for Desktop (v0.1.8.3 .zip)](https://github.com/saemranian/abu-view/raw/main/releases/Abu_View_Desktop_v0.1.8.3.zip)**
- 🎮 **[Download Abu View for Unreal Engine 5.8 (v0.0.0.4 .zip)](https://github.com/saemranian/abu-view/raw/main/releases/Abu_View_UnrealEngine_UE5.8_v0.0.0.4.zip)**
- 🌐 **[Launch Abu View (Web App)](https://ahmademranian.dev/abuview)**

---

## Quick Start by Edition

### 1. Abu View for Desktop (`./desktop/` — Abu M54 Engine)

```bash
cd desktop
pip install -r requirements.txt

# Launch the native GPU desktop viewer
python abu_m54_app.py

# Or double-click Abu_View_Desktop.bat on Windows
```

- **Supported Formats**: 3DGS & Point Cloud `.ply`, numbered 4D `.ply` frame sequences, COLMAP (`images.bin/txt`, `points3D.bin/txt`), NeRF/Nerfstudio `transforms.json`, OpenSfM JSON, RealityScan/Abu camera CSV, `.xyz`, `.pts`, and `.npz`.
- **Built-in Tools**:
  - **Render Studio**: Keyframe camera paths and render high-bitrate MP4 videos or frame sequences.
  - **4D Sequence Player**: Scrub and play back multi-frame 3DGS PLY sequences with staged GPU caching.
  - **Objects & 3D Nulls Inspector**: Inspect exact world `XYZ`, Euler angles, and quaternions; place and transform 3D reference nulls; transform and export aligned reconstructions.
- 📖 Full Desktop Guide: [desktop/README.md](./desktop/README.md) | [desktop/docs/ABU_M54.md](./desktop/docs/ABU_M54.md)

---

### 2. Abu View for Unreal Engine 5.8 (`./unreal-engine/AbuM53/` — Abu M53 Engine)

1. Copy [`unreal-engine/AbuM53`](./unreal-engine/AbuM53/) into your Unreal Engine 5.8 project at:
   ```text
   YourProject/Plugins/AbuM53
   ```
2. Build your project in **Development Editor (Win64)** and enable the **Abu M53** plugin.
3. Import any supported Gaussian Splatting file (`.ply`, `.splat`, `.spz` v1–v4, or `.am53seq` animated manifest) into the Content Browser, place an **Abu M53 Actor** in your level, and assign the asset.
- 📖 Full Unreal Engine 5.8 Guide: [unreal-engine/README.md](./unreal-engine/README.md) | [unreal-engine/AbuM53/README.md](./unreal-engine/AbuM53/README.md)

---

### 3. Abu View Web Edition ([ahmademranian.dev/abuview](https://ahmademranian.dev/abuview))

- Open [https://ahmademranian.dev/abuview](https://ahmademranian.dev/abuview) in any modern desktop, mobile, or XR headset browser.
- Compose multi-layer 3DGS (`.ply`, `.spz`, `.sog`, `.rad`, `.splat`), 3D mesh (`.glb`, `.gltf`, `.obj`), point cloud, vector, spatial audio, and chroma-key video scenes.
- Design interactive camera tours with customizable Editor Default views, focal lengths, orbital/positional constraints, and smooth quaternion transitions.

---

## Provenance & Open-Source Licensing

- **Abu View for Unreal Engine (`AbuM53`)**: Original code and synthetic fixtures are licensed under **Apache-2.0** ([unreal-engine/AbuM53/LICENSE](./unreal-engine/AbuM53/LICENSE)). See [THIRD_PARTY_NOTICES.md](./unreal-engine/AbuM53/THIRD_PARTY_NOTICES.md) and [Repository_Origins_and_Licensing.md](./unreal-engine/AbuM53/Docs/Legal/Repository_Origins_and_Licensing.md).
- **Abu View for Desktop (`Abu M54`)**: Original Gaussian splatting, offscreen render studio, 4D sequence, and About/provenance modules carry a file-scoped **Apache-2.0** grant ([desktop/licenses/M54-GAUSSIAN-NOTICE.txt](./desktop/licenses/M54-GAUSSIAN-NOTICE.txt)). See [desktop/docs/M54_PROVENANCE_AND_LICENSES.md](./desktop/docs/M54_PROVENANCE_AND_LICENSES.md) for the complete source and third-party dependency inventory.

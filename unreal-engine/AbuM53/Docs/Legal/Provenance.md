# Source and fixture provenance

Initial inventory: 25 October 2026. Consolidated review: 26 October 2026.

Read [Repository Origins, Original Development and Open-Source Licensing](Repository_Origins_and_Licensing.md) for the maintained full record and agent maintenance contract. [CodeOrigins.json](CodeOrigins.json) declares implementation-file origins and reviewed hashes. This shorter historical overview remains useful context; it is not a substitute for that full inventory.

The initial source is independently authored for this project. It does not claim to be a formally segregated clean-room implementation. Mathematical methods and public format descriptions informed the work; no restricted research rasterizer was intentionally copied or translated.

| Area | Origin | License / treatment |
|---|---|---|
| Portable parsers, container, math and CPU reference | Original Abu M53 implementation | Apache-2.0 |
| UE assets, importer, components and renderer integration | Original Abu M53 implementation using separately installed UE interfaces | Apache-2.0 for original code; UE terms apply separately |
| HLSL shaders | Original Abu M53 implementation | Apache-2.0 |
| SPZ layout/quantization compatibility | Original reader informed by MIT-licensed Niantic/Adobe source | MIT compatibility notice retained in `Core/SPZ_NOTICE.md` |
| Zstandard standalone decoder | Generated unmodified from official v1.5.7 release with upstream generator | BSD-3-Clause option; archive/file hashes and embedded xxHash notices retained in `ThirdParty/Zstd` |
| QA scripts and synthetic data generator | Original analytic construction | Apache-2.0 |
| Synthetic shell fixtures | Deterministic output of `Tools/QA/generate_fixtures.py`; no photos, external models or learned weights | Apache-2.0; hashes in fixture manifest |
| Standard Apache license document | Public Apache Software Foundation license text | Kept as license text; no engine source included |

Contributions must identify adopted external code, its exact source revision, original license, modifications and any dependencies. Contributors must have rights to submit their work. Do not add research-only source, compiled training modules or private captures based only on a repository's root license badge. Zstandard is explicitly adopted code and is not labeled an original Abu M53 implementation.

The independent core can be reviewed separately from the UE adapter/editor. The full actual package needs an Engine Tools distribution classification before an unconditional ordinary public-GitHub publication claim. An editor module name alone does not resolve that classification. See the [implementation plan](../ImplementationPlan.md) and [Epic EULA](https://www.unrealengine.com/eula/unreal).

This record is a source inventory, not a patent search, trademark clearance or legal opinion. Re-check the completed artifact and update this file whenever source or dependencies change.

# Abu M53 — Windows Installation and Persistent Test Project

The local UE 5.8 installation uses `Engine/Plugins/Marketplace/AbuM53`. The persistent development project is `abu_M53_Test_01`, normally under the user's Documents/Unreal Projects folder. Its `.uproject` enables the installed Abu M53 plugin and the engine's Python/editor scripting utilities. Other Marketplace plugins are disabled for test isolation. There is no project-local copy or additional plugin search directory.

## Updating after each development change

Complete each logical edit with an increased version, updated feature documentation, a change record, appropriate validation, a commit and annotated tag, following [the version workflow](Version_Control_and_Change_Workflow.md). Also rebuild and install that same release on this PC. The carry rule remains `v0.0.0.9` → `v0.0.1.0`.

Close editors using Abu M53 before replacing its compiled modules. From the source repository, use a **new** work directory outside the repository:

```powershell
Tools/Deployment/update_windows.ps1 -WorkDirectory C:/Builds/AbuM53/v0.0.0.2-run01
python Tools/Deployment/windows.py verify
```

Supply `-Python <python.exe>` if Python is not on PATH. `-EngineDirectory` can select another UE 5.8 installation. `-BuildOnly` builds the package without installing; installation can then be performed separately:

```powershell
python Tools/Deployment/windows.py install --directory C:/Builds/AbuM53/v0.0.0.2-run01
```

Writing the engine folder may require Windows permission. The helper snapshots audited source without `.git` or generated files, then Unreal's `BuildPlugin` compiles editor, Development and Shipping Win64 targets. `FilterPlugin.ini` includes the portable Core, Zstandard sources, fixtures, notices and documentation required alongside the normal modules/shaders. No build products enter Git.

The installer checks release metadata, source hashes, DLL presence and the module manifest before replacement. It refuses stale snapshots, changed source at the same installed version, and downgrades. It builds a complete staging copy and retains the previous installation under `Engine/AbuM53Deployment/`, outside plugin discovery. A failed final rename restores the previous directory. `verify` checks source/release identity and hashes of installed files. These checks complement actual editor tests; they do not prove arbitrary asset compatibility or performance.

### Testing repairs before the release tag

An intermediate repair to the current logical change can keep its already prepared version while that version remains **untagged**. Build a fresh snapshot in a new work directory, close editors using the plugin, and explicitly request replacement of the earlier candidate:

```powershell
Tools/Deployment/update_windows.ps1 -WorkDirectory C:/Builds/AbuM53/v0.0.0.3-run02 -ReplaceUnreleased
# Or install an already rebuilt package:
python Tools/Deployment/windows.py install --directory C:/Builds/AbuM53/v0.0.0.3-run02 --replace-unreleased
python Tools/Deployment/windows.py verify
```

The option requires an existing installation at exactly the same version, a valid receipt matching its descriptor and VERSION, and an exact installed file inventory with matching hashes. It refuses an existing Git tag, a failed Git lookup, a missing receipt, modified or extra installed files, stale source snapshots, and mismatched package contents. It retains the existing backup/rollback behavior. Ordinary installation still refuses changed source at the same version. This option does not edit versions, move tags, or bypass a build: every code or tool repair needs a fresh package and relevant tests in `abu_M53_Test_01`.

Keep the candidate's actual test results and intermediate repairs in its single change record. After the final installation and verification, finalize documentation and create the release commit/tag. Further changes after that tag require the next version.

Before tagging the current release, actual integration results can be added to its documentation using `python Tools/Deployment/windows.py finalize-docs --directory <build-directory>`. This command accepts only documentation changes to that same snapshot and refuses an already tagged release, code/config/tool changes, removed files, or an unrelated installed build. It refreshes the package documentation and reinstalls it with a backup; the compiled inputs stay identical. Close the test editor first, run `verify` afterward, then commit/tag. Any later edit to a tagged release requires the next version and a new build.

## Initial project setup

Create a new directory using the helper (existing projects are never overwritten):

```powershell
python Tools/Deployment/windows.py project --directory "C:/Users/<user>/Documents/Unreal Projects/abu_M53_Test_01"
```

Run the editor with this project and `-ExecutePythonScript=<source>/Tools/Deployment/setup_test_project.py`. The setup imports four original fixtures, checks the three-frame sequence and seek behavior, and saves `/Game/AbuM53QA/ShellQA` and `/Game/AbuM53QA/AnimationQA`. It refuses to reset an already initialized test project.

Open `abu_M53_Test_01.uproject` for future testing. The default map displays a 1,000-splat static shell. Open AnimationQA for its three-frame loop; enable viewport Realtime or press Play. The camera is positioned for the sample in both maps. These small fixtures exercise correctness and integration rather than high-count performance.

Local paths are kept in the project's `AbuM53-development.json`. Import/setup reports are under `Saved/AbuM53QA`; logs and screenshots stay with the local project. Capture with `Tools/QA/ue_capture.py` using a rendering editor (never NullRHI). After updates, verify installed version, run import/render checks appropriate to the change, and reopen the project. The plugin browser refreshes installed versions on editor restart.

## Running a screenshot check

For tick-based capture scripts, use normal console Python execution so the editor stays alive for the callbacks:

```powershell
& '<UE_5.8>/Engine/Binaries/Win64/UnrealEditor.exe' '<project>/abu_M53_Test_01.uproject' -D3D12 -sm6 -RenderOffscreen -unattended -nosplash -nosound '-ExecCmds=py <source>/Tools/QA/ue_capture.py'
```

Replace placeholders with actual paths; quote the script path inside the console command if it contains spaces. `-ExecutePythonScript` is appropriate for the synchronous initial setup, but exits before this asynchronous screenshot workflow completes. Inspect the resulting PNG and logs, not only the screenshot-request flag.

The first installed integration results are recorded in [v0.0.0.2](Changes/v0.0.0.2.md).

The current [v0.0.0.3 update](Changes/v0.0.0.3.md) adds the verified Earth regression and real Skate sequence level. Its local `AbuM53_v0.0.0.3_Test_Walkthrough.md` identifies the saved map and prepared external files. The test project's separate GPU source cache is 3072 MiB so all three 3M-splat samples can remain resident; the previous project configuration and legacy Earth package are backed up. Existing user maps are preserved. Use the unique-map regression workflows in [QA.md](QA.md) for subsequent updates.

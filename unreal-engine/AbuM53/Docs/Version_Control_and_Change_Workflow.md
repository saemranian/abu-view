# Abu M53 — Version Control and Change Documentation Workflow

## Version convention

`VERSION` is the authoritative current release identifier. The starting release is **v0.0.0.1**. This is the project's custom four-part counter, not Semantic Versioning.

The form is `vA.B.C.D`. The last three fields are single decimal digits, 0–9. Increment D for each completed logical change; carry to the left when a field reaches 10. A may contain multiple digits. Unreal's integer version is `A × 1000 + B × 100 + C × 10 + D`, limited to a positive signed 32-bit integer.

| Previous | Next |
|---|---|
| v0.0.0.1 | v0.0.0.2 |
| v0.0.0.8 | v0.0.0.9 |
| v0.0.0.9 | v0.0.1.0 |
| v0.0.9.9 | v0.1.0.0 |
| v0.9.9.9 | v1.0.0.0 |

The helper synchronizes `VERSION`, `AbuM53.uplugin` (`Version` and `VersionName`), CMake's four-part numeric project version, and current-version labels in README, CurrentScope and ImplementationStatus. Historical reports, release notes and old archives retain their original labels.

## Document each logical change

1. Inspect `git status` and the current version before editing. Preserve unrelated work.
2. Implement one coherent change. Intermediate repairs belong to that same change.
3. Update feature/API/setup documents affected by the change.
   Maintain the [full origins/license record](Legal/Repository_Origins_and_Licensing.md), explicitly classify new implementation files, update relevant notices and identify the actual human/AI contributor in this release's review-history entry. This applies equally to ChatGPT and Antigravity; the root `GEMINI.md` points to the same requirements.
4. Run appropriate checks. Record real results, including failures or checks not run.
5. Prepare the next version and its change record:

   ```powershell
   python Tools/Versioning/version.py bump --summary "Describe the completed change" --details "Explain its implementation and affected behavior" --validation "Record actual checks and results"
   ```

6. Review and expand `Docs/Changes/<version>.md`: include the problem, numbered steps, files changed, validation, limitations and migration notes. The helper starts this record; it does not replace careful documentation.

   After reviewing the code's actual origins and updating the narrative history, refresh the implementation ledger for the new version:

   ```powershell
   python Tools/Provenance/provenance.py refresh --agent "Actual contributor or AI agent" --date YYYY-MM-DD
   python Tools/Provenance/provenance.py check
   ```

   A new file needs an explicit `--declare "origin-id=Source/Module/File.cpp"`; multiple origins use comma-separated IDs. Add the origin's name, license, source/revision and required notices to `CodeOrigins.json` before using a new ID, and update the full inventory. A deleted file needs `--remove "old/path"`. A refresh refuses undeclared additions/removals. Source audits, archive packaging, deployment and CI reject stale hashes/version/history. These checks detect drift; they cannot determine whether an agent's provenance declaration is truthful or legally sufficient.
7. Verify consistency and the source inventory:

   ```powershell
   python Tools/Versioning/version.py check
   python Tools/Versioning/test_version.py
   python Tools/QA/audit_source.py
   git diff --check
   git diff
   ```

8. Stage the intended implementation, version metadata and documentation together. Review `git diff --cached` before committing. For example, for the next release:

   ```powershell
   git add <explicit changed paths>
   git diff --cached --check
   git diff --cached --stat
   git commit -m "v0.0.0.2: describe the change"
   git tag -a v0.0.0.2 -m "Abu M53 v0.0.0.2 — describe the change"
   git status --short
   ```

   Substitute the actual next version. Tag only the checked commit. Do not reuse, move or overwrite an existing tag.

9. Generate a source archive outside the repository when a release artifact is needed:

   ```powershell
   python Tools/QA/package_source.py --output ../AbuM53-v0.0.0.2-source.zip
   ```

The helper checks metadata and required records, but cannot judge the truth or completeness of prose. CI runs consistency and carry-rule tests. `AGENTS.md` makes this workflow an instruction for future coding-agent work; there is no hidden auto-commit or auto-push hook.

10. For development on this PC, rebuild/install the bumped release into UE 5.8, verify the installed version and hashes, and run relevant integration checks in the persistent `abu_M53_Test_01` project. See [Windows installation and test project](Windows_Installation_and_Test_Project.md). Preserve test-project assets and restart the editor to load updated modules. Include the deployment outcome in the same release's validation record before finalizing its commit/tag.

    Intermediate test repairs belong to the already prepared, untagged logical release. Build each repaired candidate into a fresh work directory; use the deployment helper's explicit `--replace-unreleased` option (PowerShell `-ReplaceUnreleased`) to replace a verified earlier candidate at that same version. The helper refuses this path once the version tag exists and checks both the old receipt and the newly built source/package. Record each repair and its actual checks in the same release record. This does not authorize changing or moving a released tag.

## Git boundaries and history

The repository root is the `AbuM53` plugin folder, not the entire UE Projects mirror. Generated `Intermediate`, `Binaries`, `Saved`, portable build outputs and Python caches are ignored. Original synthetic fixtures and reviewed third-party sources are tracked.

The first commit is an honest baseline of already-completed implementation plus the new documentation/versioning setup. Earlier implementation steps are described in the walkthrough; their original timestamps and individual diffs cannot be recovered as real Git history. No backdated commits are created.

Use `git log --oneline --decorate` to browse changes, `git show v0.0.0.1` to inspect the starting release, and `git diff v0.0.0.1..HEAD` to review subsequent work. Use `git revert` for a published mistake rather than silently rewriting history, then record the correction under the next version.

No remote is created or pushed by this setup. Public distribution remains subject to the legal boundaries in `Docs/Legal/Provenance.md`.

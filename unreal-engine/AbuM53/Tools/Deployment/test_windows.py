"""Deployment guard tests using synthetic files, never actual engine binaries."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import windows as deploy


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.engine = self.root / 'UE_5.8'
        build = self.engine / 'Engine/Build'
        build.mkdir(parents=True)
        deploy.write(build / 'Build.version', {'MajorVersion': 5, 'MinorVersion': 8})
        self.work = self.root / 'build'
        self.package = self.work / 'Package'
        (self.package / 'Binaries/Win64').mkdir(parents=True)
        self.state = {'version': 'v0.0.0.2', 'source_sha256': '1' * 64, 'files': []}
        self.write_package()
        for module in ('Runtime', 'Render', 'Editor'):
            (self.package / f'Binaries/Win64/UnrealEditor-AbuM53{module}.dll').write_bytes(b'test stub, not a DLL')
        (self.package / 'Binaries/Win64/UnrealEditor.modules').write_text('{}')
        self.mock = patch.object(deploy, 'source_state', side_effect=lambda: self.state)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def write_package(self):
        deploy.write(self.work / 'source-manifest.json', self.state)
        deploy.write(self.package / 'AbuM53.uplugin', {'FriendlyName': 'Abu M53', 'Installed': True,
            'VersionName': self.state['version'], 'Version': deploy.version.number(self.state['version'])})
        (self.package / 'VERSION').write_text(self.state['version'])

    def test_install_verify_backup_and_tamper(self):
        first = deploy.install(self.work, self.engine)
        self.assertTrue(deploy.verify(self.engine)['passed'])
        self.state = dict(self.state, version='v0.0.0.3', source_sha256='2' * 64)
        self.write_package()
        second = deploy.install(self.work, self.engine)
        self.assertTrue(Path(second['backup']).is_dir())
        self.assertNotIn('Plugins', Path(second['backup']).relative_to(self.engine).parts)
        self.assertTrue(deploy.verify(self.engine)['passed'])
        target = Path(first['installed']) / 'Binaries/Win64/UnrealEditor-AbuM53Render.dll'
        target.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Installed file changed'):
            deploy.verify(self.engine)

    def test_reject_stale_snapshot_and_same_version_edits(self):
        deploy.install(self.work, self.engine)
        self.state = dict(self.state, source_sha256='3' * 64)
        with self.assertRaisesRegex(ValueError, 'Source changed after snapshot'):
            deploy.install(self.work, self.engine)
        self.write_package()
        with self.assertRaisesRegex(ValueError, 'newer version'):
            deploy.install(self.work, self.engine)

    def prepare_same_version_rebuild(self):
        installed = deploy.install(self.work, self.engine)
        self.state = dict(self.state, source_sha256='4' * 64)
        self.write_package()
        (self.package / 'Binaries/Win64/UnrealEditor-AbuM53Render.dll').write_bytes(b'rebuilt test stub')
        return Path(installed['installed'])

    def test_explicit_untagged_rebuild_keeps_backup_and_verifies(self):
        target = self.prepare_same_version_rebuild()
        with patch.object(deploy.subprocess, 'run') as run:
            run.return_value.returncode = 1
            result = deploy.install(self.work, self.engine, replace_unreleased=True)
            run.assert_called_once_with(['git', 'show-ref', '--verify', '--quiet', 'refs/tags/v0.0.0.2'], cwd=deploy.ROOT)
        self.assertEqual((target / 'Binaries/Win64/UnrealEditor-AbuM53Render.dll').read_bytes(), b'rebuilt test stub')
        backup = Path(result['backup'])
        self.assertEqual((backup / 'Binaries/Win64/UnrealEditor-AbuM53Render.dll').read_bytes(), b'test stub, not a DLL')
        self.assertTrue(deploy.verify(self.engine)['passed'])

    def test_explicit_rebuild_rejects_tagged_release_and_git_failure(self):
        target = self.prepare_same_version_rebuild()
        with patch.object(deploy.subprocess, 'run') as run:
            for returncode in (0, 128):
                with self.subTest(returncode=returncode):
                    run.return_value.returncode = returncode
                    with self.assertRaisesRegex(ValueError, 'untagged'):
                        deploy.install(self.work, self.engine, replace_unreleased=True)
                    self.assertEqual((target / 'Binaries/Win64/UnrealEditor-AbuM53Render.dll').read_bytes(), b'test stub, not a DLL')

    def test_explicit_rebuild_rejects_changed_installed_files(self):
        target = self.prepare_same_version_rebuild()
        binary = target / 'Binaries/Win64/UnrealEditor-AbuM53Render.dll'
        binary.write_bytes(b'unrecorded modification')
        with patch.object(deploy.subprocess, 'run') as run:
            run.return_value.returncode = 1
            with self.assertRaisesRegex(ValueError, 'Installed file changed'):
                deploy.install(self.work, self.engine, replace_unreleased=True)
        self.assertEqual(binary.read_bytes(), b'unrecorded modification')

    def test_explicit_rebuild_requires_matching_receipt_and_inventory(self):
        target = self.prepare_same_version_rebuild()
        receipt_path = target / 'AbuM53-installation.json'
        receipt = deploy.load(receipt_path)
        with patch.object(deploy.subprocess, 'run') as run:
            run.return_value.returncode = 1
            receipt_path.unlink()
            with self.assertRaisesRegex(ValueError, 'verified installation receipt'):
                deploy.install(self.work, self.engine, replace_unreleased=True)
            deploy.write(receipt_path, receipt)
            (target / 'unrecorded.txt').write_text('preserve this file')
            with self.assertRaisesRegex(ValueError, 'inventory'):
                deploy.install(self.work, self.engine, replace_unreleased=True)

    def test_explicit_rebuild_still_rejects_stale_source_and_package(self):
        self.prepare_same_version_rebuild()
        self.state = dict(self.state, source_sha256='5' * 64)
        with self.assertRaisesRegex(ValueError, 'Source changed after snapshot'):
            deploy.install(self.work, self.engine, replace_unreleased=True)
        self.write_package()
        (self.package / 'Binaries/Win64/UnrealEditor-AbuM53Render.dll').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing compiled editor module'):
            deploy.install(self.work, self.engine, replace_unreleased=True)

    def test_explicit_rebuild_rejects_changed_packaged_source(self):
        self.prepare_same_version_rebuild()
        source = self.package / 'Source/Changed.cpp'
        source.parent.mkdir()
        source.write_text('// audited source')
        self.state = dict(self.state, files=[{'path': 'Source/Changed.cpp', 'sha256': deploy.digest(source)}])
        self.write_package()
        source.write_text('// stale or changed package')
        with self.assertRaisesRegex(ValueError, 'changed packaged source'):
            deploy.install(self.work, self.engine, replace_unreleased=True)

    def test_explicit_rebuild_rolls_back_failed_final_rename(self):
        target = self.prepare_same_version_rebuild()
        original_rename = Path.rename
        def fail_staging_rename(path, destination):
            if path.name.startswith('staging-'):
                raise OSError('synthetic final rename failure')
            return original_rename(path, destination)
        with patch.object(deploy.subprocess, 'run') as run, patch.object(Path, 'rename', new=fail_staging_rename):
            run.return_value.returncode = 1
            with self.assertRaisesRegex(OSError, 'synthetic final rename'):
                deploy.install(self.work, self.engine, replace_unreleased=True)
        self.assertEqual((target / 'Binaries/Win64/UnrealEditor-AbuM53Render.dll').read_bytes(), b'test stub, not a DLL')
        self.assertEqual(deploy.load(target / 'AbuM53-installation.json')['source_sha256'], '1' * 64)

    def test_reject_released_or_code_documentation_finalization(self):
        with patch.object(deploy.subprocess, 'run') as run:
            run.return_value.returncode = 0
            with self.assertRaisesRegex(ValueError, 'untagged'):
                deploy.finalize_docs(self.work, self.engine)
            run.return_value.returncode = 1
            self.state = dict(self.state, files=[{'path': 'Source/Changed.cpp', 'sha256': 'changed'}])
            with self.assertRaisesRegex(ValueError, 'Non-documentation'):
                deploy.finalize_docs(self.work, self.engine)

    def test_refuse_existing_project(self):
        target = self.root / 'abu_M53_Test_01'
        target.mkdir()
        sentinel = target / 'user-asset.txt'
        sentinel.write_text('preserve')
        with self.assertRaises(FileExistsError):
            deploy.project(target, self.engine)
        self.assertEqual(sentinel.read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()

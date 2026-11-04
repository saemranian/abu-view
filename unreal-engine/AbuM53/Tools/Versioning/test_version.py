"""Counter and synchronization tests; temporary copies only, no engine needed."""
import json
from pathlib import Path
import tempfile
import unittest
import version


class VersionTests(unittest.TestCase):
    def test_carry(self):
        for old, new in [('v0.0.0.1', 'v0.0.0.2'), ('v0.0.0.9', 'v0.0.1.0'),
                         ('v0.0.9.9', 'v0.1.0.0'), ('v0.9.9.9', 'v1.0.0.0'),
                         ('v9.9.9.9', 'v10.0.0.0')]:
            with self.subTest(old=old):
                self.assertEqual(version.next_version(old), new)

    def test_invalid(self):
        for value in ['0.0.0.1', 'v0.0.0.0', 'v00.0.0.1', 'v0.0.0.10',
                      'v0.10.0.0', 'v-1.0.0.0', 'v0.0.0.1-dev', 'v2147483.6.4.8']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                version.number(value)
        with self.assertRaises(ValueError):
            version.next_version('v2147483.6.4.7')

    def test_prepare_and_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in ['VERSION', 'AbuM53.uplugin', 'Core/CMakeLists.txt', 'CHANGELOG.md', *version.LABELS]:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(version.read(version.ROOT, path), encoding='utf-8')
            old = version.read(root, 'VERSION').strip()
            records = root / 'Docs/Changes'
            records.mkdir(parents=True, exist_ok=True)
            (records / (old + '.md')).write_text('# ' + old, encoding='utf-8')
            new = version.prepare(root, 'Test release', 'Changed fixture', 'Temporary-copy test')
            self.assertEqual(new, version.next_version(old))
            self.assertEqual(version.check(root), new)
            self.assertEqual(json.loads(version.read(root, 'AbuM53.uplugin'))['Version'], version.number(new))
            (root / 'VERSION').write_text(old, encoding='utf-8')
            with self.assertRaises(ValueError):
                version.check(root)


if __name__ == '__main__':
    unittest.main()

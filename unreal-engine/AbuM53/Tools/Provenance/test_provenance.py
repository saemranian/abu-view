"""Meaningful drift/declaration/metadata regression checks on original temporary files."""
import json
from pathlib import Path
import tempfile
import unittest
import provenance as p


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'Source').mkdir()
        (self.root / 'Docs/Legal').mkdir(parents=True)
        (self.root / 'VERSION').write_text('v0.0.0.4\n')
        (self.root / 'Source/owned.cpp').write_text('// original test stub\n')
        (self.root / p.DOCUMENT).write_text(p.START + '\n\n' + p.END + '\n\n- **v0.0.0.4** - test review\n', encoding='utf-8')
        self.record = {'schema': 1, 'scope': list(p.SCOPE), 'origins': {
                       'own': {'name': 'Original fixture', 'license': 'Apache-2.0', 'source': 'This test'},
                       'upstream': {'name': 'Declared fixture', 'license': 'MIT', 'source': 'Owned test stub, no adopted library'}},
                       'files': {'Source/owned.cpp': {'origins': ['own']}}}
        self.write()
        p.refresh(self.root, 'test agent', '2026-10-26')

    def write(self):
        (self.root / p.RECORD).write_text(json.dumps(self.record))

    def test_valid_review(self):
        self.assertEqual(p.validate(self.root), [])

    def test_code_drift_and_review_refresh(self):
        (self.root / 'Source/owned.cpp').write_text('// reviewed new implementation\n')
        self.assertTrue(any('changed since' in e for e in p.validate(self.root)))
        p.refresh(self.root, 'another actual agent', '2026-10-26')
        self.assertEqual(p.validate(self.root), [])

    def test_new_code_requires_explicit_classification(self):
        (self.root / 'Source/adopted.cpp').write_text('// upstream stub\n')
        with self.assertRaises(ValueError): p.refresh(self.root, 'test', '2026-10-26')
        p.refresh(self.root, 'test', '2026-10-26', ['upstream=Source/adopted.cpp'])
        self.assertEqual(p.validate(self.root), [])

    def test_invalid_origin_or_outside_path_rejected(self):
        for entry in ('unknown=Source/owned.cpp', 'own=../outside.cpp'):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                p.refresh(self.root, 'test', '2026-10-26', [entry])

    def test_removal_is_explicit(self):
        (self.root / 'Source/owned.cpp').unlink()
        with self.assertRaises(ValueError): p.refresh(self.root, 'test', '2026-10-26')
        p.refresh(self.root, 'test', '2026-10-26', removals=['Source/owned.cpp'])
        self.assertEqual(p.validate(self.root), [])

    def test_document_metadata_and_history_must_match(self):
        doc = self.root / p.DOCUMENT
        doc.write_text(doc.read_text().replace('test agent', 'invented agent'))
        self.assertTrue(any('metadata is stale' in e for e in p.validate(self.root)))
        p.refresh(self.root, 'test agent', '2026-10-26')
        doc.write_text(doc.read_text().replace('- **v0.0.0.4**', '- **v0.0.0.3**'))
        self.assertTrue(any('review history' in e for e in p.validate(self.root)))

    def test_release_bump_requires_review(self):
        (self.root / 'VERSION').write_text('v0.0.0.5\n')
        self.assertTrue(any('differs from VERSION' in e for e in p.validate(self.root)))

    def test_unknown_declared_origin_is_rejected(self):
        record = json.loads((self.root / p.RECORD).read_text())
        record['files']['Source/owned.cpp']['origins'] = ['not-registered']
        (self.root / p.RECORD).write_text(json.dumps(record))
        self.assertTrue(any('Unknown/missing origin' in e for e in p.validate(self.root)))


if __name__ == '__main__': unittest.main()

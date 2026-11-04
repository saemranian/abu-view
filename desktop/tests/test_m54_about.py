# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Abu Align contributors
"""Provenance drift, packaging coverage and actual desktop/browser About contracts."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import abu_m54_about as about
import m54_provenance as provenance

ROOT=Path(__file__).resolve().parents[1]


class ProvenanceTests(unittest.TestCase):
    def test_review_covers_current_m54_and_public_payload(self):
        record=provenance.check_inventory(ROOT)
        text=about.document_text()
        for p in ROOT.glob('abu_m54*.py'):
            self.assertIn(p.name,record['sha256']);self.assertIn(p.name,text)
        public=json.loads((ROOT/'installer/public-files.json').read_text())['files']
        for name in record['sha256']:self.assertIn(name,public)
        self.assertIn('GPLv3',text);self.assertIn('mixed terms',text)
        self.assertIn('metadata saying MIT',text)

    def test_stale_modified_and_new_source_and_dependency_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in provenance.SUPPORT:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture 2026-10-26',encoding='utf-8')
            source=root/'abu_m54_fixture.py';source.write_text('# synthetic\n')
            provenance.refresh(root,'2026-10-26','Unit test','Independent synthetic fixture')
            provenance.check_inventory(root)
            for p in (source,root/'installer/requirements-core.lock'):
                original=p.read_bytes();p.write_bytes(original+b' changed')
                with self.assertRaisesRegex(ValueError,'review required'):provenance.check_inventory(root)
                p.write_bytes(original)
            new=root/'abu_m54_new.py';new.write_text('# new code')
            with self.assertRaisesRegex(ValueError,'abu_m54_new.py'):provenance.check_inventory(root)
            new.unlink();provenance.check_inventory(root)
            source.write_bytes(source.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
            provenance.check_inventory(root)
            with self.assertRaisesRegex(ValueError,'review date'):provenance.refresh(root,'2026-10-27','Reviewer','Reviewed')
            with self.assertRaises(ValueError):provenance.refresh(root,'2026-10-26','Reviewer','')

    def test_manifests_ship_document_record_and_about_module(self):
        for manifest in ('installer/core-files.json','installer/public-files.json'):
            files=json.loads((ROOT/manifest).read_text())['files']
            for required in ('abu_m54_about.py',provenance.RECORD,provenance.DOCUMENT):self.assertIn(required,files)
        self.assertIn('m54_provenance.py --check',(ROOT/'.github/workflows/release.yml').read_text())
        for name in ('AGENTS.md','GEMINI.md'):
            text=(ROOT/name).read_text(encoding='utf-8');self.assertIn(provenance.DOCUMENT,text);self.assertIn('m54_provenance.py --check',text)

    def test_version_bump_refuses_stale_review_before_reading_or_mutating_version(self):
        import version_manager
        with patch('m54_provenance.check_inventory',side_effect=ValueError('stale review')) as guard,patch('version_manager.get_current_version') as read:
            with self.assertRaisesRegex(ValueError,'stale review'):version_manager.bump_and_sync()
            guard.assert_called_once_with(version_manager.ROOT_DIR);read.assert_not_called()

    def test_sections_and_notices_are_local_and_preserve_real_license_text(self):
        with patch('webbrowser.open') as online:
            sections=about.document_sections();notices=about.notice_files()
        online.assert_not_called()
        self.assertIn('Original Abu M54 implementation',sections)
        self.assertIn('Python dependency appendix',sections)
        self.assertIn('Apache License',notices['licenses/M54-GAUSSIAN-APACHE-2.0.txt'].read_text())
        self.assertIn('VGGT',notices['LICENSE.txt'].read_text(encoding='utf-8'))
        self.assertTrue(about.review_date().startswith('2026-'))

    def test_browser_uses_same_document_and_download_only_on_request(self):
        class Handle:
            def __init__(self,value=None,content=''):self.value=value;self.content=content;self.update=None;self.click=None
            def on_update(self,callback):self.update=callback
            def on_click(self,callback):self.click=callback
        class Gui:
            def __init__(self):self.buttons=[]
            def add_folder(self,*args,**kwargs):return self
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def add_markdown(self,content):return Handle(content=content)
            def add_dropdown(self,label,options,initial_value):return Handle(initial_value)
            def add_button(self,label):
                h=Handle();self.buttons.append(h);return h
        server=SimpleNamespace(gui=Gui())
        with patch('webbrowser.open') as online:
            selector,content=about.add_browser_about(server)
            selector.value='What open-source licensing means here';selector.update(None)
        self.assertIn('GPLv3',content.content);online.assert_not_called()
        downloads=[];client=SimpleNamespace(send_file_download=lambda name,data:downloads.append((name,data)))
        server.gui.buttons[0].click(SimpleNamespace(client=client))
        self.assertEqual(downloads,[(about.DOCUMENT.name,about.document_text().encode('utf-8'))])


@unittest.skipUnless(os.name=='nt' or os.environ.get('DISPLAY'),'Desktop display required')
class AboutUITests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        self.root=tk.Tk();self.root.withdraw();self.addCleanup(self.root.destroy)

    def test_about_and_guide_tabs_render_and_copy_offline(self):
        from abu_m54_help import GuideWindow
        with patch('webbrowser.open') as online:
            window=GuideWindow(self.root,page='about');self.root.update()
            self.assertEqual(window.tabs.select(),str(window.about))
            content=window.about.document.text.get('1.0','end')
            self.assertIn('python-plyfile 1.1.3',content);self.assertIn('GPLv3',content)
            self.assertGreater(len(window.about.document.anchors),10)
            window.about.copy_document();self.assertEqual(self.root.clipboard_get(),about.document_text())
            window.select_page('guide');self.assertEqual(window.tabs.select(),str(window.guide))
            self.assertIn('PLY sequence',window.guide.text.get('1.0','end'))
            self.assertGreater(len(window.guide.images),0)
            window.about.pages.select(1);self.root.update()
            self.assertIn('Apache License',window.about.notice_text.get('1.0','end'))
            window.destroy()
        online.assert_not_called()

    def test_embedded_about_reuses_window_and_selects_about(self):
        import tkinter as tk
        host=tk.Frame(self.root)
        a=about.show_about(host);a.select_page('guide')
        b=about.show_about(host)
        self.assertIs(a,b);self.assertEqual(a.tabs.select(),str(a.about));a.destroy()


if __name__=='__main__':unittest.main()

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Abu Align contributors
# Original About UI; see licenses/M54-GAUSSIAN-NOTICE.txt for scope.
"""Shared offline M54 provenance, local notices and About surfaces."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog

ROOT=Path(__file__).resolve().parent
DOCUMENT=ROOT/'docs'/'M54_PROVENANCE_AND_LICENSES.md'


def document_text():
    try:return DOCUMENT.read_text(encoding='utf-8')
    except OSError:return '# Abu M54\n\nThe provenance document is missing from this installation. See the project source and license notices.'


def document_sections():
    """Use exactly the desktop document in browser hosts, with bounded sections."""
    sections={};title='Document record';lines=[]
    for line in document_text().splitlines():
        if line.startswith('## '):
            if lines:sections[title]='\n'.join(lines)
            title=line[3:];lines=[line]
        else:lines.append(line)
    if lines:sections[title]='\n'.join(lines)
    return sections


def review_date():
    import json
    try:return json.loads((ROOT/'docs'/'M54_PROVENANCE_RECORD.json').read_text(encoding='utf-8'))['review_date']
    except (OSError,ValueError,KeyError):return 'Review record unavailable'


def notice_files():
    """Only read local notice text; never import a library or launch a process."""
    result={}
    for rel in ('licenses/M54-GAUSSIAN-NOTICE.txt','licenses/M54-GAUSSIAN-APACHE-2.0.txt','LICENSE.txt','THIRD_PARTY_NOTICES.md'):
        p=ROOT/rel
        if p.is_file():result[rel]=p
    for base in (ROOT/'THIRD_PARTY_LICENSES',ROOT.parent/'THIRD_PARTY_LICENSES'):
        if base.is_dir():
            for p in sorted(base.rglob('*')):
                if p.is_file() and p.suffix.lower() in {'.txt','.md','.terms',''}:
                    if p.stat().st_size<=2*1024*1024:result['Bundled / '+p.relative_to(base).as_posix()]=p
    from importlib.metadata import distribution,PackageNotFoundError
    for name in ('numpy','scipy','Pillow','viser','plyfile','pycolmap','trimesh','psutil','opencv-python'):
        try:dist=distribution(name)
        except PackageNotFoundError:continue
        base=Path(dist.locate_file('')).resolve()
        for item in dist.files or []:
            if not any(word in Path(item).name.lower() for word in ('license','copying','notice','copyright')):continue
            p=Path(dist.locate_file(item)).resolve()
            if p.is_relative_to(base) and p.is_file() and p.suffix.lower() in {'.md','.txt','.terms',''} and p.stat().st_size<=2*1024*1024:
                result['Installed / '+name+' '+dist.version+' / '+str(item)]=p
    return result


def show_about(viewer):
    """Same About tab in every native host, including compact host adapters."""
    window=getattr(viewer,'about_window',None)
    if window is not None and window.winfo_exists():
        window.select_page('about');window.lift();return window
    from abu_m54_help import GuideWindow
    viewer.about_window=GuideWindow(viewer.winfo_toplevel(),page='about')
    return viewer.about_window


class AboutPanel(tk.Frame):
    def __init__(self,parent):
        from abu_m54_ui import BG,PANEL,TEXT,MUTED,ACCENT
        from abu_m54_help import DocumentView
        from version_manager import get_current_version
        super().__init__(parent,bg=BG)
        header=tk.Frame(self,bg=PANEL,padx=14,pady=8);header.pack(fill='x')
        tk.Label(header,text='Abu 3D Viewer M54 · v'+get_current_version(),bg=PANEL,fg=ACCENT,font=('Segoe UI',14,'bold')).pack(anchor='w')
        tk.Label(header,text='Original Abu features · upstream libraries · source provenance · license obligations',bg=PANEL,fg=MUTED,font=('Segoe UI',10)).pack(anchor='w',pady=(3,0))
        self.pages=ttk.Notebook(self);self.pages.pack(fill='both',expand=True)
        self.document=DocumentView(self.pages,DOCUMENT,'Contents');self.pages.add(self.document,text='Provenance & licenses')
        notices=tk.Frame(self.pages,bg=BG);self.pages.add(notices,text='Full license texts')
        self.notices=notice_files();self.notice_name=tk.StringVar(self,next(iter(self.notices),''))
        selector=ttk.Combobox(notices,textvariable=self.notice_name,values=list(self.notices),state='readonly');selector.pack(fill='x',padx=12,pady=10)
        selector.bind('<<ComboboxSelected>>',lambda e:self.read_notice())
        body=tk.Frame(notices,bg=BG);body.pack(fill='both',expand=True)
        self.notice_text=tk.Text(body,bg=BG,fg=TEXT,wrap='word',font=('Consolas',10),padx=16,pady=8,relief='flat')
        bar=ttk.Scrollbar(body,command=self.notice_text.yview);self.notice_text.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');self.notice_text.pack(fill='both',expand=True)
        self.read_notice()
        actions=tk.Frame(self,bg=PANEL,padx=12,pady=7);actions.pack(fill='x')
        ttk.Button(actions,text='Copy document',command=self.copy_document).pack(side='left',padx=3)
        ttk.Button(actions,text='Save document copy…',command=self.save_document).pack(side='left',padx=3)
        tk.Label(actions,text='Reviewed: '+review_date()+' · file-specific terms apply',bg=PANEL,fg=MUTED).pack(side='right')

    def read_notice(self):
        path=self.notices.get(self.notice_name.get())
        try:text=path.read_text(encoding='utf-8',errors='replace') if path else 'No bundled notice was found.'
        except OSError as error:text='Cannot read this notice: '+str(error)
        self.notice_text.configure(state='normal');self.notice_text.delete('1.0','end');self.notice_text.insert('1.0',text);self.notice_text.configure(state='disabled')

    def copy_document(self):
        self.clipboard_clear();self.clipboard_append(document_text())

    def save_document(self):
        path=filedialog.asksaveasfilename(parent=self.winfo_toplevel(),title='Save M54 provenance document',initialfile=DOCUMENT.name,defaultextension='.md',filetypes=[('Markdown document','*.md')])
        if path:
            try:Path(path).write_text(document_text(),encoding='utf-8')
            except OSError as error:
                from tkinter import messagebox
                messagebox.showerror('Save document',str(error),parent=self.winfo_toplevel())


def add_browser_about(server):
    """Local browser About section, reused by standalone and embedded adapters."""
    from version_manager import get_current_version
    sections=document_sections()
    with server.gui.add_folder('Abu M54 · About',expand_by_default=False):
        server.gui.add_markdown('### Abu 3D Viewer M54 · v'+get_current_version())
        section=server.gui.add_dropdown('Read about',tuple(sections),initial_value=next(iter(sections)))
        import re
        # Relative local-file references are available in the downloaded document;
        # do not turn them into broken localhost URLs in the browser client.
        clean=lambda text:re.sub(r'\[([^\]]+)\]\((?!https://)[^)]+\)',r'`\1`',text)
        content=server.gui.add_markdown(clean(sections[section.value]))
        section.on_update(lambda event:setattr(content,'content',clean(sections[section.value])))
        text=document_text().encode('utf-8')
        download=server.gui.add_button('Download provenance document')
        download.on_click(lambda event:event.client.send_file_download(DOCUMENT.name,text) if event.client else None)
    return section,content

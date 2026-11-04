"""In-app Abu M54 guide: renders docs/ABU_M54_GUIDE.md (headings, lists, tables, images) in a help window."""
import re
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from abu_m54_ui import BG,PANEL,BORDER,TEXT,MUTED,ACCENT,ICON,tip

GUIDE=Path(__file__).parent/'docs'/'ABU_M54_GUIDE.md'


class DocumentView(tk.Frame):
    """Offline document reader shared by Guide and About; no remote images."""
    def __init__(self,parent,document=GUIDE,title='Guide'):
        super().__init__(parent,bg=BG);self.document=Path(document);self.images=[];self.anchors={}
        scale=self.scale=max(1.,float(self.winfo_fpixels('1i'))/96)
        nav=tk.Frame(self,bg=PANEL,width=int(230*scale));nav.pack(side='left',fill='y');nav.pack_propagate(False)
        tk.Label(nav,text=title,bg=PANEL,fg=ACCENT,font=('Segoe UI Symbol',13,'bold'),anchor='w',padx=14,pady=12).pack(fill='x')
        canvas=tk.Canvas(nav,bg=PANEL,highlightthickness=0);scroll=ttk.Scrollbar(nav,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
        nav_body=tk.Frame(canvas,bg=PANEL);slot=canvas.create_window((0,0),window=nav_body,anchor='nw')
        nav_body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(slot,width=e.width))
        def nav_wheel(event):
            canvas.yview_scroll(-1 if event.delta>0 else 1,'units');return 'break'
        canvas.bind('<MouseWheel>',nav_wheel);nav_body.bind('<MouseWheel>',nav_wheel)
        self.nav=nav_body;self.nav_wheel=nav_wheel;body=tk.Frame(self,bg=BG);body.pack(side='left',fill='both',expand=True)
        self.text=tk.Text(body,bg=BG,fg=TEXT,relief='flat',bd=0,wrap='word',padx=int(28*scale),pady=int(18*scale),font=('Segoe UI',11),cursor='arrow',highlightthickness=0,spacing3=4)
        bar=ttk.Scrollbar(body,orient='vertical',command=self.text.yview);self.text.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');self.text.pack(side='left',fill='both',expand=True)
        t=self.text;s=scale
        t.tag_configure('h1',font=('Segoe UI',22,'bold'),foreground=TEXT,spacing1=6,spacing3=10);t.tag_configure('h2',font=('Segoe UI',16,'bold'),foreground=ACCENT,spacing1=22,spacing3=8)
        t.tag_configure('h3',font=('Segoe UI',12,'bold'),foreground=TEXT,spacing1=12,spacing3=4);t.tag_configure('bold',font=('Segoe UI',11,'bold'));t.tag_configure('code',font=('Consolas',10),background=PANEL,foreground='#9fe8d4')
        t.tag_configure('bullet',lmargin1=int(18*s),lmargin2=int(36*s));t.tag_configure('table',font=('Consolas',10),background=PANEL,lmargin1=int(10*s),spacing1=2,wrap='none');t.tag_configure('quote',foreground=MUTED,lmargin1=int(14*s),lmargin2=int(14*s),font=('Segoe UI',11,'italic'))
        t.tag_configure('center',justify='center',spacing1=8,spacing3=10)
        t.tag_configure('link',foreground=ACCENT,underline=True)
        self.render();t.configure(state='disabled')
    def inline(self,line,base=()):
        for part in re.split(r'(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`)',line):
            link=re.fullmatch(r'\[([^\]]+)\]\(([^)]+)\)',part)
            if link:
                title,target=link.groups();tag='ref'+str(len(self.text.tag_names()))
                self.text.insert('end',title,base+('link',tag))
                self.text.tag_bind(tag,'<Button-1>',lambda e,value=target:self.open_reference(value))
                self.text.tag_bind(tag,'<Enter>',lambda e:self.text.configure(cursor='hand2'))
                self.text.tag_bind(tag,'<Leave>',lambda e:self.text.configure(cursor='arrow'))
            elif part.startswith('**') and part.endswith('**') and len(part)>4:self.text.insert('end',part[2:-2],base+('bold',))
            elif part.startswith('`') and part.endswith('`') and len(part)>2:self.text.insert('end',part[1:-1],base+('code',))
            elif part:self.text.insert('end',part,base)
    def image(self,alt,path):
        file=(self.document.parent/path).resolve()
        try:
            if not file.is_relative_to(Path(__file__).resolve().parent):raise ValueError('Image outside local documentation')
            from PIL import Image,ImageTk
            image=Image.open(file);width=int(min(image.width,860*self.scale));height=int(image.height*width/image.width)
            photo=ImageTk.PhotoImage(image.resize((width,height),Image.LANCZOS),master=self);self.images.append(photo)
            self.text.insert('end','\n');self.text.image_create('end',image=photo);self.text.insert('end','\n','center')
        except Exception:self.text.insert('end',f'[image: {alt}]\n','quote')
    def render(self):
        try:lines=self.document.read_text(encoding='utf-8').splitlines()
        except OSError:self.text.insert('end','Document not available in this installation: '+self.document.name);return
        in_code=False
        for line in lines:
            if line.startswith('```'):in_code=not in_code;continue
            if in_code:self.text.insert('end',line+'\n','table');continue
            if re.match(r'^\|[\s:|-]+\|$',line.strip()):continue
            image=re.match(r'!\[([^\]]*)\]\(([^)]+)\)',line.strip())
            if image:self.image(*image.groups());continue
            if line.startswith('# '):self.inline(line[2:],('h1',));self.text.insert('end','\n')
            elif line.startswith('## '):
                title=line[3:];self.anchors[title]=self.text.index('end-1c');self.inline(title,('h2',));self.text.insert('end','\n')
                button=tk.Button(self.nav,text=title,command=lambda k=title:self.text.yview(self.anchors[k]),bg=PANEL,fg=TEXT,activebackground=BORDER,activeforeground=TEXT,relief='flat',bd=0,anchor='w',padx=14,pady=5,font=('Segoe UI Symbol',10),cursor='hand2',wraplength=int(190*self.scale),justify='left');button.pack(fill='x');button.bind('<MouseWheel>',self.nav_wheel)
            elif line.startswith('### '):self.inline(line[4:],('h3',));self.text.insert('end','\n')
            elif line.startswith('> '):self.inline(line[2:],('quote',));self.text.insert('end','\n')
            elif re.match(r'^\s*[-*] ',line):self.text.insert('end','•  ','bullet');self.inline(re.sub(r'^\s*[-*] ','',line),('bullet',));self.text.insert('end','\n')
            elif line.startswith('|'):self.text.insert('end',line.strip().strip('|').replace('|','  │  ')+'\n','table')
            elif line.strip():self.inline(line);self.text.insert('end','\n')
            else:self.text.insert('end','\n')

    def open_reference(self,target):
        from urllib.parse import urlsplit
        if urlsplit(target).scheme=='https':
            import webbrowser
            webbrowser.open(target);return
        path=(self.document.parent/target.split('#',1)[0]).resolve()
        if path.is_relative_to(Path(__file__).resolve().parent) and path.suffix.lower() in {'.md','.txt'} and path.is_file():
            window=tk.Toplevel(self);window.title(path.name);window.geometry('1000x720')
            DocumentView(window,path,path.stem).pack(fill='both',expand=True)


class GuideWindow(tk.Toplevel):
    def __init__(self,parent,editor=None,page='guide'):
        super().__init__(parent);self.title('Abu M54 · Guide & About');self.configure(bg=BG)
        scale=max(1.,float(self.winfo_fpixels('1i'))/96);self.geometry(f'{int(1040*scale)}x{int(760*scale)}');self.minsize(int(720*scale),int(480*scale))
        try:
            from abu_m54_desktop import window_identity;window_identity(self)
        except Exception:pass
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True)
        self.guide=DocumentView(self.tabs);self.tabs.add(self.guide,text='Guide')
        from abu_m54_about import AboutPanel
        self.about=AboutPanel(self.tabs);self.tabs.add(self.about,text='About')
        self.select_page(page);self.bind('<Escape>',lambda e:self.destroy())

    def select_page(self,page):
        self.tabs.select(self.about if page=='about' else self.guide)

"""Universal Abu M54 details panel: file facts, scene summary and the searchable camera list."""
import tkinter as tk
from tkinter import ttk
import numpy as np
from abu_m54_ui import BG,PANEL,BORDER,TEXT,MUTED,ACCENT,ICON,tip
from abu_m54_fileinfo import describe_source

KIND_ICONS=dict(cloud='☁',cameras='◈',folder='❐',scene='▣')


class DetailsPanel:
    def __init__(self,viewer,parent):
        self.viewer=viewer;self.editor=viewer.editor;self.parent=parent;self.syncing=False;self.items={};self.shown_key=None;self.tab=None
        s=self.scale=max(1.,float(parent.winfo_fpixels('1i'))/96)
        card=tk.Frame(parent,bg=PANEL,padx=int(10*s),pady=int(8*s));card.pack(fill='x',padx=6,pady=(2,6))
        self.glyph=tk.Label(card,text=ICON['file'],bg=PANEL,fg=ACCENT,font=('Segoe UI Symbol',int(20)));self.glyph.pack(side='left',padx=(0,10))
        text=tk.Frame(card,bg=PANEL);text.pack(side='left',fill='x',expand=True)
        self.name=tk.StringVar(parent,'No file opened');self.kind=tk.StringVar(parent,'Use Open to load a cloud, cameras or a result folder')
        self.name_label=tk.Label(text,textvariable=self.name,bg=PANEL,fg=TEXT,font=('Segoe UI',11,'bold'),anchor='w',justify='left',wraplength=int(280*s));self.name_label.pack(fill='x')
        tk.Label(text,textvariable=self.kind,bg=PANEL,fg=MUTED,font=('Segoe UI',9),anchor='w',justify='left',wraplength=int(280*s)).pack(fill='x')
        self.path_tip=None
        tabs=tk.Frame(parent,bg=BG);tabs.pack(fill='x',padx=6)
        self.buttons={}
        for key,label,hint in [('file',f"{ICON['info']}  File",'Facts about the opened file and scene'),('cameras',f"{ICON['camera']}  Cameras",'Camera list; pick one to see its exact pose')]:
            button=tk.Button(tabs,text=label,command=lambda k=key:self.select_tab(k),relief='flat',bd=0,padx=12,pady=5,font=('Segoe UI Symbol',10),cursor='hand2',activebackground=BORDER,activeforeground=TEXT);button.pack(side='left',fill='x',expand=True,padx=(0,2));self.buttons[key]=button;tip(button,hint)
        self.stack=tk.Frame(parent,bg=BG);self.stack.pack(fill='both',expand=True,padx=6,pady=(2,6))
        self.pages={'file':tk.Frame(self.stack,bg=BG),'cameras':tk.Frame(self.stack,bg=BG)}
        self.file_text=self.make_text(self.pages['file'],wrap='word')
        page=self.pages['cameras']
        search=tk.Frame(page,bg=BG,pady=4);search.pack(fill='x')
        self.filter=tk.StringVar(parent);tk.Label(search,text='⌕',bg=BG,fg=MUTED,font=('Segoe UI Symbol',12)).pack(side='left',padx=(2,6))
        box=self.editor.entry(search,self.filter,12);box.pack(side='left',fill='x',expand=True,ipady=3);tip(box,'Filter cameras by name');self.filter.trace_add('write',lambda *_:self.rebuild(force=True))
        split=tk.PanedWindow(page,orient='vertical',bg=BORDER,sashwidth=max(7,int(8*s)),opaqueresize=True);split.pack(fill='both',expand=True)
        frame=tk.Frame(split,bg=BG);split.add(frame,minsize=int(90*s),height=int(300*s),stretch='always')
        style=ttk.Style(parent);style.configure('M54Cameras.Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,font=('Segoe UI',10),rowheight=int(26*s));style.configure('M54Cameras.Treeview.Heading',font=('Segoe UI',10,'bold'))
        self.tree=ttk.Treeview(frame,columns=('no',),style='M54Cameras.Treeview',selectmode='browse')
        self.tree.heading('#0',text='Camera');self.tree.heading('no',text='#');self.tree.column('no',width=int(64*s),minwidth=int(48*s),stretch=False,anchor='e');self.tree.column('#0',width=int(240*s),minwidth=int(120*s),stretch=True)
        bar=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=bar.set);self.tree.pack(side='left',fill='both',expand=True);bar.pack(side='right',fill='y')
        self.tree.bind('<<TreeviewSelect>>',self.choose);tip(self.tree,'Click a camera to select it in the 3D view')
        lower=tk.Frame(split,bg=BG);split.add(lower,minsize=int(120*s),stretch='always')
        self.camera_text=self.make_text(lower,wrap='none',horizontal=True)
        self.select_tab('file');self.show_camera([('Select a camera in this list or in the 3D view.','muted')])
    def make_text(self,parent,wrap,horizontal=False):
        s=self.scale;text=tk.Text(parent,bg=PANEL,fg=TEXT,relief='flat',bd=0,padx=10,pady=8,wrap=wrap,font=('Consolas',10),height=6,highlightthickness=0,cursor='arrow',tabs=(int(112*s),))
        ys=ttk.Scrollbar(parent,orient='vertical',command=text.yview);text.configure(yscrollcommand=ys.set)
        if horizontal:
            xs=ttk.Scrollbar(parent,orient='horizontal',command=text.xview);text.configure(xscrollcommand=xs.set);xs.pack(side='bottom',fill='x')
        ys.pack(side='right',fill='y');text.pack(side='left',fill='both',expand=True)
        text.tag_configure('head',foreground=ACCENT,font=('Segoe UI',10,'bold'),spacing1=8,spacing3=2);text.tag_configure('name',font=('Segoe UI',11,'bold'));text.tag_configure('muted',foreground=MUTED)
        text.tag_configure('row',lmargin1=int(8*s),lmargin2=int(120*s),tabs=(int(112*s),));text.tag_configure('label',foreground=MUTED);return text
    def fill(self,widget,parts):
        widget.configure(state='normal');widget.delete('1.0','end')
        for line,tag in parts:widget.insert('end',line+'\n',tag)
        widget.configure(state='disabled')
    def show_camera(self,parts):self.fill(self.camera_text,parts)
    def select_tab(self,key):
        if key=='cameras' and not self.items and not getattr(self.viewer,'camera_options',{}):key='file'
        self.tab=key
        for name,page in self.pages.items():
            if name==key:page.pack(fill='both',expand=True)
            else:page.pack_forget()
        for name,button in self.buttons.items():button.configure(bg=ACCENT if name==key else PANEL,fg=DARK_TEXT if name==key else TEXT)
    def set_scene(self,scene):
        """Describe a newly opened file/scene in the universal panel."""
        kind,glyph,sections=describe_source(scene)
        name=next((value for label,value in sections[0][1] if label=='Name'),'Scene')
        self.name.set(name);self.kind.set(kind);self.glyph.configure(text=KIND_ICONS.get(glyph,ICON['file']))
        if self.path_tip:self.path_tip.text=str(scene.get('source',''))
        else:
            from abu_m54_ui import MiniTip
            self.path_tip=MiniTip(self.name_label,str(scene.get('source','')))
        parts=[]
        for title,rows in sections:
            parts.append((title,'head'))
            for label,value in rows:parts.append((f'{label}\t{value}','row'))
        self.fill(self.file_text,parts);self.rebuild(force=True)
        cameras=len(scene.get('centers',{}));self.buttons['cameras'].configure(text=f"{ICON['camera']}  Cameras · {cameras:,}",state='normal' if cameras else 'disabled')
        self.select_tab('cameras' if cameras and (kind.startswith('Camera') or not len(scene.get('points',[]))) else 'file')
    def rebuild(self,force=False):
        options=getattr(self.viewer,'camera_options',{});key=(tuple(options),self.filter.get().strip().lower())
        if key==self.shown_key and not force:return
        self.shown_key=key;text=key[1];self.syncing=True
        self.tree.delete(*self.tree.get_children());self.items={}
        for index,(label,item) in enumerate(options.items(),1):
            if text and text not in label.lower():continue
            self.tree.insert('','end',iid=str(index),text=label,values=(index,));self.items[str(index)]=item
        self.syncing=False;self.sync()
    def choose(self,event=None):
        if self.syncing:return
        selection=self.tree.selection()
        if selection and selection[0] in self.items:
            layer,name=self.items[selection[0]];self.viewer.select_camera(name,layer)
    def sync(self):
        """Highlight the viewer's selected camera and show its exact pose."""
        v=self.viewer
        if getattr(v,'selection_kind','')!='camera' or not v.camera_selected:return
        target=(v.selected_camera_layer,v.camera_selected)
        iid=next((i for i,item in self.items.items() if item==target),None)
        if iid is not None and self.tree.selection()!=(iid,):
            self.syncing=True;self.tree.selection_set(iid);self.tree.see(iid);self.syncing=False
        self.show_camera(self.describe(*target))
        if self.tab!='cameras':self.select_tab('cameras')
    def describe(self,layer,name):
        from abu_m54_editing import selection_record
        record=selection_record(self.viewer)
        if not record or record['kind']!='camera':return [(name,'name')]
        scene=self.viewer.data if layer=='A' else self.viewer.comparison['b'] if self.viewer.comparison else None
        names=list(scene['centers']) if scene else [];index=names.index(name) if name in names else -1
        parts=[(name,'name'),(f'Layer {layer} · camera {index+1:,} of {len(names):,}' if index>=0 else f'Layer {layer}','muted')]
        def vector(title,values,labels='XYZ',digits=10):
            parts.append((title,'head'))
            for label,value in zip(labels,values):parts.append((f'  {label}  {value:.{digits}g}',''))
        vector('Position (world)',record['position'])
        if record.get('rotation_xyz_degrees') is not None:vector('Rotation XYZ (degrees)',record['rotation_xyz_degrees'],digits=8)
        if record.get('quaternion_wxyz') is not None:vector('Quaternion',record['quaternion_wxyz'],'wxyz',10)
        if scene and name in scene.get('camera_rotations',{}):
            r=scene['camera_rotations'][name];vector('Viewing direction',r[:,2],digits=6);vector('Up direction',-r[:,1],digits=6)
        if index>=0:
            parts.append(('Neighbour distance','head'))
            for label,other in [('Previous',index-1),('Next',index+1)]:
                if 0<=other<len(names):parts.append((f'  {label:<9}{np.linalg.norm(scene["centers"][names[other]]-scene["centers"][name]):.8g}',''))
        return parts


DARK_TEXT='#0f1518'

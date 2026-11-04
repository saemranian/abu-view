"""Shared Abu M54 UI helpers: theme, icon glyphs, minimal hover tips and collapsible side docks."""
import tkinter as tk

BG='#1a2024';PANEL='#242d32';BORDER='#344149';TEXT='#e7edef';MUTED='#9aa8af';ACCENT='#70dbc0';DARK='#111518'
ICON=dict(cloud='☁',cameras='◈',controls='✛',rays='↗',fit='⛶',orbit='⟳',tools='⚙',objects='☰',details='▤',compare='⇄',help='❓',open='▣',folder='❐',info='ⓘ',
          browser='⌖',file='▣',camera='◈',grid='⊞',save='⭳',view='◉')


class MiniTip:
    """A very small one-line hover hint; shows after a short pause and never steals focus."""
    def __init__(self,widget,text,delay=450):
        self.widget=widget;self.text=text;self.delay=delay;self.job=None;self.popup=None
        widget.bind('<Enter>',self.schedule,add='+')
        for event in ['<Leave>','<ButtonPress>','<Destroy>','<Key>']:widget.bind(event,self.hide,add='+')
    def schedule(self,event=None):
        self.hide();self.job=self.widget.after(self.delay,self.show)
    def show(self):
        self.job=None
        if not self.widget.winfo_exists() or not self.text:return
        scale=max(1.,float(self.widget.winfo_fpixels('1i'))/96)
        self.popup=tk.Toplevel(self.widget);self.popup.overrideredirect(True);self.popup.attributes('-topmost',True);self.popup.configure(bg=BORDER)
        tk.Label(self.popup,text=self.text,bg=DARK,fg=TEXT,font=('Segoe UI',9),padx=8,pady=3,wraplength=int(300*scale),justify='left').pack(padx=1,pady=1)
        self.popup.update_idletasks()
        x=min(self.widget.winfo_pointerx()+12,self.widget.winfo_screenwidth()-self.popup.winfo_reqwidth()-8)
        y=min(self.widget.winfo_pointery()+20,self.widget.winfo_screenheight()-self.popup.winfo_reqheight()-8)
        self.popup.geometry(f'+{max(0,x)}+{max(0,y)}')
    def hide(self,event=None):
        if self.job:
            try:self.widget.after_cancel(self.job)
            except tk.TclError:pass
            self.job=None
        if self.popup:
            try:self.popup.destroy()
            except tk.TclError:pass
            self.popup=None


def tip(widget,text):
    """Attach a minimal hover hint and return the widget for chaining."""
    MiniTip(widget,text);return widget


def tip_tree(widget,tips):
    """Attach tips to descendants by their visible text/label, e.g. {'Fit': 'Frame everything'}."""
    for child in widget.winfo_children():
        for key in ('text',):
            try:value=str(child.cget(key))
            except tk.TclError:value=''
            if value in tips:tip(child,tips[value])
        tip_tree(child,tips)


class SideDock(tk.Frame):
    """Resizable side panel that collapses to a thin rail with one arrow button."""
    def __init__(self,parent,side,title,icon,width=380,min_width=260,on_toggle=None):
        super().__init__(parent,bg=BG);self.side=side;self.on_toggle=on_toggle;self.expanded=True
        self.scale=max(1.,float(self.winfo_fpixels('1i'))/96);self.default_width=int(width*self.scale);self.min_width=int(min_width*self.scale);self.width=self.default_width
        self.rail_width=int(34*self.scale);self.drag=None;self.pack_propagate(False)
        # Expanded view: drag edge + body. Collapsed view: slim rail.
        self.full=tk.Frame(self,bg=BG);edge=tk.Frame(self.full,bg=BORDER,width=max(5,int(6*self.scale)),cursor='sb_h_double_arrow')
        self.body=tk.Frame(self.full,bg=BG)
        if side=='right':edge.pack(side='left',fill='y');self.body.pack(side='left',fill='both',expand=True)
        else:edge.pack(side='right',fill='y');self.body.pack(side='left',fill='both',expand=True)
        edge.bind('<ButtonPress-1>',lambda e:setattr(self,'drag',(e.x_root,self.width)));edge.bind('<B1-Motion>',self.edge_move);edge.bind('<ButtonRelease-1>',lambda e:setattr(self,'drag',None))
        edge.bind('<Double-Button-1>',lambda e:self.set_width(self.default_width));tip(edge,'Drag to resize · double-click to reset')
        header=tk.Frame(self.body,bg=BG,padx=8,pady=6);header.pack(fill='x')
        arrow_hide='▶' if side=='right' else '◀';arrow_show='◀' if side=='right' else '▶'
        self.title_var=tk.StringVar(self,title);tk.Label(header,text=icon,bg=BG,fg=ACCENT,font=('Segoe UI Symbol',12)).pack(side='left')
        tk.Label(header,textvariable=self.title_var,bg=BG,fg=TEXT,font=('Segoe UI',10,'bold'),anchor='w').pack(side='left',padx=(6,0),fill='x',expand=True)
        def small(text,command,hint):
            button=tk.Button(header,text=text,command=command,bg=PANEL,fg=TEXT,activebackground=BORDER,activeforeground=TEXT,relief='flat',bd=0,padx=7,pady=2,font=('Segoe UI Symbol',9),cursor='hand2');button.pack(side='right',padx=2);tip(button,hint);return button
        small(arrow_hide,self.collapse,'Minimize this panel');small('−',lambda:self.set_width(self.width*.8),'Narrower');small('+',lambda:self.set_width(self.width*1.25),'Wider')
        self.content=tk.Frame(self.body,bg=BG);self.content.pack(fill='both',expand=True)
        self.rail=tk.Frame(self,bg=BG,width=self.rail_width);self.rail_button=tk.Button(self.rail,text=arrow_show,command=self.expand,bg=PANEL,fg=ACCENT,activebackground=BORDER,activeforeground=TEXT,relief='flat',bd=0,font=('Segoe UI Symbol',10),cursor='hand2',pady=8)
        self.rail_button.pack(fill='x',padx=3,pady=(8,4));tip(self.rail_button,'Show '+title.lower())
        tk.Label(self.rail,text=icon,bg=BG,fg=MUTED,font=('Segoe UI Symbol',13)).pack(pady=4)
        self.full.pack(fill='both',expand=True);self.configure(width=self.width)
    def edge_move(self,event):
        if self.drag:
            delta=event.x_root-self.drag[0];self.set_width(self.drag[1]+(-delta if self.side=='right' else delta))
    def set_width(self,value):
        parent=self.master;limit=max(self.min_width,parent.winfo_width()-int(360*self.scale)) if parent.winfo_width()>1 else int(900*self.scale)
        self.width=int(max(self.min_width,min(limit,value)))
        if self.expanded:self.configure(width=self.width)
    def collapse(self):
        if not self.expanded:return
        self.expanded=False;self.full.pack_forget();self.rail.pack(fill='both',expand=True);self.configure(width=self.rail_width)
        if self.on_toggle:self.on_toggle(False)
    def expand(self):
        if self.expanded:return
        self.expanded=True;self.rail.pack_forget();self.full.pack(fill='both',expand=True);self.configure(width=self.width)
        if self.on_toggle:self.on_toggle(True)
    def toggle(self):
        if self.expanded:self.collapse()
        else:self.expand()


class ActivityDock(tk.Frame):
    """One side bar with a vertical icon rail; each icon switches the panel shown beside it.

    Clicking the active icon minimizes the panel to the bare rail; clicking another icon switches panels.
    """
    def __init__(self,parent,side='left',width=380,min_width=260,on_toggle=None):
        super().__init__(parent,bg=BG);self.side=side;self.on_toggle=on_toggle;self.expanded=True;self.active=None;self.pages={};self.buttons={};self.callbacks={}
        self.scale=max(1.,float(self.winfo_fpixels('1i'))/96);self.default_width=int(width*self.scale);self.min_width=int(min_width*self.scale);self.width=self.default_width
        self.rail_width=int(44*self.scale);self.drag=None;self.pack_propagate(False)
        self.rail=tk.Frame(self,bg=DARK,width=self.rail_width);self.rail.pack(side='left',fill='y');self.rail.pack_propagate(False)
        self.panel=tk.Frame(self,bg=BG);self.panel.pack(side='left',fill='both',expand=True)
        edge=tk.Frame(self.panel,bg=BORDER,width=max(5,int(6*self.scale)),cursor='sb_h_double_arrow');edge.pack(side='right',fill='y')
        edge.bind('<ButtonPress-1>',lambda e:setattr(self,'drag',(e.x_root,self.width)));edge.bind('<B1-Motion>',self.edge_move);edge.bind('<ButtonRelease-1>',lambda e:setattr(self,'drag',None))
        edge.bind('<Double-Button-1>',lambda e:self.set_width(self.default_width));tip(edge,'Drag to resize · double-click to reset')
        body=tk.Frame(self.panel,bg=BG);body.pack(side='left',fill='both',expand=True)
        header=tk.Frame(body,bg=BG,padx=8,pady=6);header.pack(fill='x')
        self.header_icon=tk.Label(header,text='',bg=BG,fg=ACCENT,font=('Segoe UI Symbol',12));self.header_icon.pack(side='left')
        self.title_var=tk.StringVar(self);tk.Label(header,textvariable=self.title_var,bg=BG,fg=TEXT,font=('Segoe UI',10,'bold'),anchor='w').pack(side='left',padx=(6,0),fill='x',expand=True)
        def small(text,command,hint):
            button=tk.Button(header,text=text,command=command,bg=PANEL,fg=TEXT,activebackground=BORDER,activeforeground=TEXT,relief='flat',bd=0,padx=7,pady=2,font=('Segoe UI Symbol',9),cursor='hand2');button.pack(side='right',padx=2);tip(button,hint)
        small('◀',self.collapse,'Minimize this panel');small('−',lambda:self.set_width(self.width*.8),'Narrower');small('+',lambda:self.set_width(self.width*1.25),'Wider')
        self.stack=tk.Frame(body,bg=BG);self.stack.pack(fill='both',expand=True)
        self.configure(width=self.rail_width)
        self.panel.pack_forget();self.expanded=False
    def add_page(self,key,icon,title,hint=None,on_show=None):
        frame=tk.Frame(self.stack,bg=BG);self.pages[key]=(icon,title,frame);self.callbacks[key]=on_show
        button=tk.Button(self.rail,text=icon,command=lambda:self.toggle(key),bg=DARK,fg=MUTED,activebackground=BORDER,activeforeground=TEXT,relief='flat',bd=0,font=('Segoe UI Symbol',16),cursor='hand2',pady=int(10*self.scale))
        button.pack(fill='x',padx=3,pady=(8 if not self.buttons else 2,0));tip(button,hint or title);self.buttons[key]=button;return frame
    def edge_move(self,event):
        if self.drag:self.set_width(self.drag[1]+(event.x_root-self.drag[0]))
    def set_width(self,value):
        parent=self.master;limit=max(self.min_width+self.rail_width,parent.winfo_width()-int(360*self.scale)) if parent.winfo_width()>1 else int(900*self.scale)
        self.width=int(max(self.min_width,min(limit,value)))
        if self.expanded:self.configure(width=self.width+self.rail_width)
    def show(self,key):
        icon,title,frame=self.pages[key]
        for name,(_,_,page) in self.pages.items():
            if name==key:page.pack(fill='both',expand=True)
            else:page.pack_forget()
        for name,button in self.buttons.items():button.configure(bg=ACCENT if name==key else DARK,fg=DARK if name==key else MUTED)
        self.header_icon.configure(text=icon);self.title_var.set(title);self.active=key
        if not self.expanded:
            self.expanded=True;self.panel.pack(side='left',fill='both',expand=True);self.configure(width=self.width+self.rail_width)
            if self.on_toggle:self.on_toggle(True)
        if self.callbacks.get(key):self.callbacks[key]()
    def collapse(self):
        if not self.expanded:return
        self.expanded=False;self.panel.pack_forget();self.configure(width=self.rail_width);self.active=None
        for button in self.buttons.values():button.configure(bg=DARK,fg=MUTED)
        if self.on_toggle:self.on_toggle(False)
    def expand(self):
        if not self.expanded:self.show(self.active or next(iter(self.pages)))
    def toggle(self,key):
        if self.expanded and self.active==key:self.collapse()
        else:self.show(key)

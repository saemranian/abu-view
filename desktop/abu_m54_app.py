"""Standalone Abu M54 desktop/browser application and Windows Open-with setup."""
import argparse
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog,messagebox
from abu_m54 import load_scene, FORMATS, NAME


def register_open_with(executable=None):
    """Register a per-user candidate; never change the user's default file app."""
    import winreg
    executable=Path(executable or Path(__file__).with_name('Abu_M54.exe')).resolve()
    if not executable.is_file():raise FileNotFoundError('Build Abu_M54.exe before registering Open with.')
    application='Abu_M54.exe';base=r'Software\Classes\Applications'+'\\'+application
    def put(path,name,value):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,path) as key:winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
    put(base,'FriendlyAppName',NAME);put(base+r'\shell\open\command','',f'"{executable}" "%1"')
    put(base+r'\DefaultIcon','',f'"{executable}",0')
    for suffix in ['.json','.ply','.csv','.txt','.bin','.xyz','.pts','.npz']:
        put(base+r'\SupportedTypes',suffix,'')
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Classes'+'\\'+suffix+r'\OpenWithList'+'\\'+application):pass
    return str(executable)


class M54Application:
    @property
    def process(self):return self.worker_state['process']
    @process.setter
    def process(self,value):self.worker_state['process']=value
    def __init__(self,root):
        self.worker_state={'process':None,'closed':False,'generation':0}
        from abu_m54_host import ViewerHost
        from abu_m54_native import M54NativeViewer
        from version_manager import get_current_version
        self.root=root;root.title(NAME+' · v'+get_current_version());root.geometry('1400x900');root.minsize(920,620);root.configure(bg='#111518')
        from abu_m54_desktop import window_identity
        self.dpi=window_identity(root)
        self.host=ViewerHost(root);self.closed=False;self.generation=0;self.events=queue.Queue();self.process=None
        top=tk.Frame(root,bg='#1a2024',padx=10,pady=7);top.pack(fill='x')
        from abu_m54_ui import ICON,tip
        tk.Label(top,text=ICON['cloud'],bg='#1a2024',fg='#70dbc0',font=('Segoe UI Symbol',15)).pack(side='left',padx=(4,2))
        self.host.label(top,NAME).pack(side='left',padx=(2,14))
        # One Open entry replaces separate file / run-folder / Windows registration buttons.
        opener=tk.Menubutton(top,text=ICON['open']+'  Open  ▾',bg='#70dbc0',fg='#0f1518',activebackground='#8ae8cf',activeforeground='#0f1518',relief='flat',bd=0,padx=14,pady=6,font=('Segoe UI Symbol',10,'bold'),cursor='hand2')
        menu=tk.Menu(opener,tearoff=0,bg='#242d32',fg='#e7edef',activebackground='#31574f',activeforeground='white',bd=0,font=('Segoe UI Symbol',10))
        menu.add_command(label=ICON['file']+'   File…                         Ctrl+O',command=self.open_file)
        menu.add_command(label=ICON['folder']+'   Result folder…',command=self.open_folder)
        menu.add_command(label='▶   PLY sequence…',command=lambda:self.viewer.open_sequence())
        menu.add_separator();menu.add_command(label=ICON['tools']+'   Add M54 to Windows ‘Open with’',command=self.register)
        opener.configure(menu=menu);opener.pack(side='left',padx=3);tip(opener,'Open a cloud, cameras or reconstruction file, or a completed result folder')
        help_button=self.host.button(top,ICON['help']+'  Guide',self.open_guide);help_button.pack(side='right',padx=3);tip(help_button,'Guide, icons and shortcuts  ·  F1')
        about_button=self.host.button(top,ICON['info']+'  About',lambda:self.open_guide('about'));about_button.pack(side='right',padx=3);tip(about_button,'M54 authorship, repositories and open-source license details')
        root.bind('<Control-o>',lambda e:self.open_file());root.bind('<F1>',lambda e:self.open_guide())
        self.host.label(root,variable=self.host.status,muted=True,padx=10,pady=5).pack(side='bottom',fill='x')
        self.viewer=M54NativeViewer(self.host,root);self.viewer.pack(fill='both',expand=True)
        self.viewer.on_sequence_open=self.cancel_load
        self.host.audit.event('m54_desktop',dpi=self.dpi,tk_scaling=float(root.tk.call('tk','scaling')),icon=root._m54_icon_path)
        self.poll_id=root.after(60,self.poll);root.protocol('WM_DELETE_WINDOW',self.close)
    def open_guide(self,page='guide'):
        from abu_m54_help import GuideWindow
        if getattr(self,'guide',None) is not None and self.guide.winfo_exists():self.guide.select_page(page);self.guide.lift();return
        self.guide=GuideWindow(self.root,page=page)
    def register(self):
        try:self.host.status.set('Windows Open with enabled: '+register_open_with())
        except Exception as error:self.host.error('Open with setup failed',error)
    def open_file(self):
        value=filedialog.askopenfilename(parent=self.root,title='Open file · cloud, cameras CSV, COLMAP, JSON or scene',filetypes=[('M54 supported files',FORMATS),('All files','*.*')])
        if value:self.load(value)
    def open_folder(self):
        value=filedialog.askdirectory(parent=self.root,title='Open completed Abu alignment/training result')
        if value:self.load(value)
    def cancel_load(self):
        self.generation+=1;self.worker_state['generation']=self.generation
        if self.process and self.process.poll() is None:self.process.terminate()
    def load(self,source):
        if self.viewer.sequence_player:self.viewer.sequence_player.unload()
        self.generation+=1;generation=self.generation
        state=self.worker_state;state['generation']=generation;events=self.events
        if self.process and self.process.poll() is None:self.process.terminate()
        self.host.status.set('Loading in a separate process…');self.host.audit.event('m54_load',source=str(source))
        def work():
            try:
                with tempfile.TemporaryDirectory(prefix='abu_m54_') as folder:
                    target=Path(folder)/'scene.npz'
                    process=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--load-worker',str(source),'--output',str(target)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    state['process']=process
                    if state['closed'] or generation!=state['generation']:process.terminate()
                    output,_=process.communicate()
                    if state['process'] is process:state['process']=None
                    if state['closed'] or generation!=state['generation']:return
                    if process.returncode:raise RuntimeError(output[-2500:] or 'Cannot load file.')
                    from control_points_comparison import read_scene
                    from abu_m54 import bounds
                    scene=read_scene(target);scene['center'],scene['extent']=bounds(scene);events.put((generation,scene,None))
            except Exception as error:events.put((generation,None,str(error)))
        threading.Thread(target=work,daemon=True).start()
    def poll(self):
        if self.closed:return
        try:
            while True:
                generation,scene,error=self.events.get_nowait()
                if generation!=self.generation:continue
                if error:self.host.status.set('Load failed: '+error)
                else:self.viewer.set_data(scene);self.host.status.set('Opened: '+scene['source'])
        except queue.Empty:pass
        self.poll_id=self.root.after(60,self.poll)
    def close(self):
        if self.closed:return
        if self.viewer.inspector_window and self.viewer.inspector_window.winfo_exists():self.viewer.inspector_window.finish()
        self.viewer.editing.release()
        if self.viewer.nulls.dirty:
            answer=messagebox.askyesnocancel('Unsaved M54 nulls','Save the 3D null objects before closing?',parent=self.root)
            if answer is None:return
            if answer:
                self.viewer.open_inspector()
                if not self.viewer.inspector_window.save():return
        from manual_ui_lifecycle import capture,retire
        retired=capture(self.root,[self,self.host,self.viewer.compare,self.viewer.editing])
        self.closed=True;self.generation+=1;self.root.after_cancel(self.poll_id)
        self.worker_state['closed']=True;self.worker_state['generation']=self.generation
        if self.process and self.process.poll() is None:self.process.terminate()
        self.viewer.close();self.root.destroy();retire(retired)


def main():
    parser=argparse.ArgumentParser(description=NAME);parser.add_argument('path',nargs='?');parser.add_argument('--browser',action='store_true');parser.add_argument('--register-open-with',action='store_true')
    parser.add_argument('--load-worker');parser.add_argument('--output');args=parser.parse_args()
    if args.register_open_with:print(register_open_with());return
    if args.load_worker:
        from control_points_comparison import save_scene
        save_scene(args.output,load_scene(args.load_worker));return
    if args.browser:
        from abu_m54_browser import M54Browser
        import webbrowser
        viewer=M54Browser()
        if args.path:viewer.set_scene(load_scene(args.path))
        webbrowser.open(viewer.url)
        try:
            while True:time.sleep(.25)
        except KeyboardInterrupt:viewer.close()
        return
    from abu_m54_desktop import prepare_desktop
    prepare_desktop();root=tk.Tk();app=M54Application(root)
    if args.path:app.load(args.path)
    root.mainloop()


if __name__=='__main__':main()

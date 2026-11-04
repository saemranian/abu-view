# SPDX-License-Identifier: Apache-2.0
"""Shared native M54 timeline for local, independently exported Gaussian frames."""
from __future__ import annotations

import ctypes as ct
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog

import numpy as np

from abu_m54_ui import tip

GIB = 1024 ** 3


class SequencePlayer:
    """Tk owns navigation/GL. The loader never calls Tk or changes source files."""

    def __init__(self, viewer):
        self.viewer = viewer
        self.sequence = None
        self.cache = self.gpu = None
        self.index = self.desired = 0
        self.playing = self.applying = self.closed = False
        self.generation = 0
        self.events = queue.Queue()
        self.poll_job = None
        self.displayed = False
        self.have_view = False
        self.anchor = 0.
        self.anchor_index = 0
        self.last_present = None
        self.intervals = []
        self.presented_count = 0
        self.last_drawn_index = None
        self.buffering = False
        self.syncing = False
        self.gpu_limit = 0
        self.failure = ''
        self.preparing = False
        self.discovery_thread = None
        self.fps = tk.StringVar(viewer, '30')
        self.speed = tk.StringVar(viewer, '1')
        self.loop = tk.BooleanVar(viewer, True)
        self.budget = tk.StringVar(viewer, 'Auto')
        self.timeline = tk.DoubleVar(viewer, 0)
        self.status = tk.StringVar(viewer, 'Choose the first numbered PLY frame.')
        self.frame_label = tk.StringVar(viewer, '')
        self.panel = tk.Frame(viewer, bg='#1a2024', padx=8, pady=5)
        row = tk.Frame(self.panel, bg='#1a2024');row.pack(fill='x')
        viewer.editor.button(row, 'Open sequence…', self.open).pack(side='left', padx=2)
        viewer.editor.button(row, '⏮', lambda:self.seek(0)).pack(side='left', padx=2)
        viewer.editor.button(row, '‹', lambda:self.step_frame(-1)).pack(side='left', padx=2)
        self.play_button = viewer.editor.button(row, '▶ Play', self.toggle_play)
        self.play_button.pack(side='left', padx=2)
        viewer.editor.button(row, '›', lambda:self.step_frame(1)).pack(side='left', padx=2)
        tip(tk.Checkbutton(row, text='Loop', variable=self.loop, bg='#1a2024', fg='#e7edef', selectcolor='#242d32'),
            'Repeat the available frames. No motion is invented between independently exported splats.').pack(side='left', padx=5)
        for label, var, values, readonly in [('Source FPS', self.fps, (1, 5, 12, 24, 30, 60), False),
                                             ('Speed', self.speed, ('.1', '.25', '.5', '1', '2'), True),
                                             ('GPU cache · GiB', self.budget, ('Auto', '1', '2', '4', '8'), True)]:
            viewer.editor.label(row, label, muted=True).pack(side='left', padx=(8, 3))
            choice = ttk.Combobox(row, textvariable=var, values=values, width=6, state='readonly' if readonly else 'normal')
            choice.pack(side='left')
            choice.bind('<<ComboboxSelected>>', self.settings_changed)
            choice.bind('<Return>', self.settings_changed)
            choice.bind('<FocusOut>', self.settings_changed)
            tip(choice, {'Source FPS':'The original capture/export frame rate (0.1–240). PLY has no standard FPS metadata; 30 is an editable assumption.',
                         'Speed':'Preview speed only; Render Studio uses Source FPS and its own output FPS.',
                         'GPU cache · GiB':'Bounded resident GPU memory. Auto uses up to 4 GiB with headroom. Larger sequences buffer when frames are not resident.'}[label])
        viewer.editor.button(row, 'Close sequence', self.unload).pack(side='right', padx=4)
        from rig_designer_ui import wrap_row
        wrap_row(row)
        scrub = tk.Frame(self.panel, bg='#1a2024');scrub.pack(fill='x', pady=3)
        self.slider = ttk.Scale(scrub, from_=0, to=1, variable=self.timeline, command=self.scrub)
        self.slider.pack(side='left', fill='x', expand=True)
        viewer.editor.label(scrub, variable=self.frame_label, muted=True).pack(side='right', padx=8)
        viewer.editor.label(self.panel, variable=self.status, muted=True).pack(fill='x')

    def show(self):
        if not self.panel.winfo_manager():
            self.panel.pack(side='bottom', fill='x', before=self.viewer.scene_body)

    def open(self, source=None):
        if sys.platform!='win32' or (self.viewer.winfo_ismapped() and not self.viewer.context):
            self.show();self.fail('PLY sequence playback needs the native Windows OpenGL 4.3+ renderer.');return
        if source is None:
            source = filedialog.askopenfilename(parent=self.viewer.winfo_toplevel(),
                title='PLY sequence · select any numbered frame', filetypes=[('Gaussian frame', '*.ply')])
        if not source:return
        # Invalidate a standalone single-file worker before it can overwrite the sequence.
        callback = getattr(self.viewer, 'on_sequence_open', None)
        if callback:callback()
        self.unload(hide=False)
        self.show();self.status.set('Checking sequence headers…');self.preparing=True
        self.generation += 1
        generation = self.generation
        try:fps = float(self.fps.get())
        except ValueError:fps = 30.
        events = self.events
        def discover():
            try:
                from abu_m54_sequence import discover_sequence
                sequence = discover_sequence(source, fps=fps)
                events.put((generation, sequence, None))
            except Exception as error:events.put((generation, None, str(error)))
        self.discovery_thread = threading.Thread(target=discover, name='M54 sequence discovery', daemon=True)
        try:
            self.schedule();self.discovery_thread.start()
        except Exception as error:
            self.generation+=1;self.preparing=False
            if self.poll_job is not None:
                self.viewer.after_cancel(self.poll_job);self.poll_job=None
            self.discovery_thread=None;self.fail(str(error))

    def install(self, sequence):
        """Install a preflighted immutable sequence (also usable by embedded hosts)."""
        from abu_m54_sequence import CPUFrameCache
        self.sequence = sequence
        self.fps.set(f'{sequence.fps:g}')
        self.applied_settings = (self.fps.get(), self.speed.get(), self.budget.get())
        self.index = self.desired = 0;self.displayed=False;self.have_view=False;self.failure=''
        self.preparing=False
        try:
            import psutil
            cpu_limit = min(6*GIB, max(256*1024**2, int(psutil.virtual_memory().available*.25)))
        except Exception:cpu_limit=2*GIB
        self.cache = CPUFrameCache(sequence, budget_bytes=cpu_limit)
        self.slider.configure(to=sequence.count-1)
        self.cache.request(0)
        self.show();self.schedule()
        self.viewer.editor.audit.event('m54_sequence_open', frames=sequence.count, fps=sequence.fps, cpu_budget=cpu_limit)

    def ensure_gpu(self):
        v=self.viewer
        if self.gpu is not None:return True
        if not v.context:return False
        from abu_m54_sequence_gpu import SequenceGPUCache
        v.gl.wglMakeCurrent(v.dc,v.context)
        # NVX is only queried when advertised; other vendors use a conservative cap.
        available = None
        extensions = v.gl.glGetString(0x1F03) or b''
        if b'GL_NVX_gpu_memory_info' in extensions:
            value=ct.c_int()
            v.gl.glGetIntegerv.argtypes=[ct.c_uint,ct.POINTER(ct.c_int)]
            v.gl.glGetIntegerv(0x9049,ct.byref(value))
            if value.value>0:available=value.value*1024
        requested = 4*GIB if self.budget.get()=='Auto' else int(self.budget.get())*GIB
        self.gpu_limit = min(requested, int(available*.6)) if available else min(requested, GIB)
        self.gpu=SequenceGPUCache(v.gl,budget_bytes=self.gpu_limit)
        return True

    def owns_scene(self, scene):
        return self.sequence is not None and scene.get('_m54_sequence_owner') is self

    def renderer_for_scene(self, scene):
        if not self.gpu:return None
        return self.gpu.get(scene.get('_m54_sequence_index',-1))

    def present(self, index):
        frame=self.cache.get(index)
        renderer=self.gpu.get(index)
        if frame is None or renderer is None:return False
        if not self.displayed and self.viewer.gaussian_renderer:
            self.viewer.gaussian_renderer.close();self.viewer.gaussian_renderer=None
        self.gpu.protected_index=index
        scene=dict(frame.scene, _m54_sequence_owner=self, _m54_sequence_index=index)
        self.applying=True
        try:self.viewer.set_sequence_frame(scene,first=not self.have_view)
        finally:self.applying=False
        self.displayed=True;self.have_view=True;self.index=index
        self.syncing=True
        try:self.timeline.set(index)
        finally:self.syncing=False
        self.frame_label.set(f'{index+1} / {self.sequence.count} · {Path(self.sequence.paths[index]).name} · {index/self.sequence.fps:.3f} s')
        self.viewer.editor.status.set('PLY sequence: '+str(self.sequence.paths[index]))
        # The timeline already schedules this frame. A second 16 ms redraw
        # debounce adds avoidable latency and can skip short-clip source frames.
        self.viewer.draw()
        return True

    def on_frame_drawn(self):
        """Count completed viewport draws, not scheduled Tk frame changes."""
        if self.index==self.last_drawn_index:return
        self.last_drawn_index=self.index
        now=time.perf_counter()
        if self.last_present is not None and self.playing:
            self.intervals.append(now-self.last_present);self.intervals=self.intervals[-120:]
        self.last_present=now;self.presented_count+=1

    def schedule(self):
        if not self.closed and self.poll_job is None:
            active=self.playing or self.preparing or (self.gpu and self.gpu.uploading_index is not None) or (self.cache and self.cache.loading_index is not None)
            self.poll_job=self.viewer.after(8 if active else 50,self.poll)

    def poll(self):
        self.poll_job=None
        if self.closed or self.viewer.closed:return
        while True:
            try:generation,sequence,error=self.events.get_nowait()
            except queue.Empty:break
            if generation!=self.generation:continue
            self.preparing=False
            if error:self.fail(error)
            else:
                try:self.install(sequence)
                except Exception as error:self.fail(str(error))
        if self.sequence and self.cache and not self.failure:
            try:self.advance()
            except Exception as error:self.fail(str(error))
        if (self.sequence or self.preparing) and not self.failure:self.schedule()

    def advance(self):
        while True:
            try:self.cache.events.get_nowait()
            except queue.Empty:break
        if not self.ensure_gpu():
            self.status.set('Waiting for the native Windows GPU viewport…');return
        self.viewer.gl.wglMakeCurrent(self.viewer.dc,self.viewer.context)
        if self.playing:
            elapsed=(time.perf_counter()-self.anchor)*float(self.speed.get())
            step=int(elapsed*self.sequence.fps+1e-9)
            wanted=self.anchor_index+step
            if not self.loop.get() and wanted>=self.sequence.count:
                wanted=self.sequence.count-1
                self.pause(refresh=False)
            self.desired=wanted%self.sequence.count
        needed=self.desired
        if needed in self.cache.errors:raise RuntimeError(self.cache.errors[needed])
        upcoming=[(needed+i)%self.sequence.count for i in range(1,min(self.sequence.count,3))]
        self.cache.request(needed)
        if self.gpu.uploading_index is not None:
            self.gpu.step(max_bytes=16*1024**2)
        if self.gpu.uploading_index is None:
            # Give the requested frame priority. Warm all three short-clip frames
            # before Play, while keeping longer clips strictly budget-bounded.
            for index in [needed,*upcoming]:
                if self.gpu.contains(index):continue
                frame=self.cache.get(index)
                if frame is None:continue
                if index!=needed and self.gpu.allocated_bytes+self.sequence.frames[index].gpu_bytes>self.gpu_limit:break
                try:self.gpu.request(frame)
                except BufferError:
                    if index!=needed:break  # Prefetch must not evict the displayed frame.
                    self.gpu.protected_index=None
                    self.gpu.request(frame)
                break
        ready=self.gpu.contains(needed) and self.cache.get(needed) is not None
        if ready and (not self.displayed or needed!=self.index or self.buffering):
            self.present(needed)
            if self.buffering and self.playing:
                self.anchor=time.perf_counter();self.anchor_index=needed
            self.buffering=False
        elif not ready:
            self.buffering=True
            if self.playing:
                # Hold the playback clock while loading instead of racing past
                # uncached frames, which can otherwise starve the loader forever.
                self.anchor=time.perf_counter();self.anchor_index=needed
        resident=len(self.gpu.cached_indices)
        label='Buffering' if self.buffering else 'Playing' if self.playing else 'Paused'
        measured=(1/np.mean(self.intervals)) if self.intervals and self.playing else 0.
        rate=f' · {measured:.1f} presented fps' if measured else ''
        self.status.set(f'{label} · {resident}/{self.sequence.count} GPU frames · {self.gpu.allocated_bytes/GIB:.2f}/{self.gpu_limit/GIB:.2f} GiB GPU · {self.cache.used_bytes/GIB:.2f} GiB RAM cache{rate}')

    def toggle_play(self):
        if self.playing:self.pause();return
        if not self.sequence or self.failure:return
        if not self.settings_changed():return
        if not self.loop.get() and self.index==self.sequence.count-1:self.seek(0)
        self.anchor=time.perf_counter();self.anchor_index=self.desired
        self.playing=True;self.intervals=[];self.last_present=None
        self.play_button.configure(text='Ⅱ Pause');self.schedule()

    def pause(self, refresh=True):
        self.playing=False;self.play_button.configure(text='▶ Play')
        if refresh and self.displayed and self.viewer.details:
            self.viewer.details.set_scene(self.viewer.raw_data)

    def seek(self,index):
        if not self.sequence:return
        self.pause(refresh=False)
        self.desired=max(0,min(self.sequence.count-1,int(index)))
        self.cache.request(self.desired)
        if self.gpu and self.gpu.uploading_index is not None and self.gpu.uploading_index!=self.desired and not self.gpu.contains(self.desired):
            self.viewer.gl.wglMakeCurrent(self.viewer.dc,self.viewer.context)
            self.gpu.cancel_upload()
        self.schedule()

    def step_frame(self,delta):
        self.seek(self.index+delta)

    def scrub(self,value):
        if not self.syncing:self.seek(int(float(value)+.5))

    def settings_changed(self,event=None):
        values=(self.fps.get(),self.speed.get(),self.budget.get())
        if values==getattr(self,'applied_settings',None):return True
        try:
            fps,speed=float(values[0]),float(values[1])
            if not np.isfinite([fps,speed]).all() or not .1<=fps<=240 or not .1<=speed<=2:
                raise ValueError('Source FPS must be 0.1–240 and speed 0.1–2.')
            self.pause(refresh=False)
            if self.sequence:
                # Metadata/signatures are retained; changing FPS does not reread frames.
                self.sequence=self.sequence.with_fps(fps)
            if values[2]!=getattr(self,'applied_settings',values)[2] and self.gpu:
                self.viewer.gl.wglMakeCurrent(self.viewer.dc,self.viewer.context)
                self.gpu.close();self.gpu=None;self.displayed=False
            self.applied_settings=values
            self.schedule();return True
        except Exception as error:
            self.status.set(str(error));return False

    def export_descriptor(self):
        if not self.sequence or not self.displayed:raise ValueError('Wait for the sequence to load its first frame.')
        self.pause()
        return {'sequence':self.sequence.to_dict(),'transform':self.viewer.transforms['A'].matrix().tolist(),'start_index':self.index}

    def fail(self,message):
        self.pause(refresh=False);self.failure=str(message);self.preparing=False
        self.status.set('Sequence stopped: '+str(message))
        self.viewer.editor.audit.error('m54_sequence_error',RuntimeError(str(message)))

    def unload(self,hide=True):
        self.generation+=1;self.preparing=False;self.pause(refresh=False)
        if self.poll_job is not None:
            self.viewer.after_cancel(self.poll_job);self.poll_job=None
        if self.cache:self.cache.close();self.cache=None
        if self.gpu:
            self.viewer.gl.wglMakeCurrent(self.viewer.dc,self.viewer.context)
            self.gpu.close();self.gpu=None
        if self.viewer.data and self.owns_scene(self.viewer.data):
            # Leave the currently displayed frame available as a static asset.
            for data in (self.viewer.data,self.viewer.raw_data):
                data.pop('_m54_sequence_owner',None);data.pop('_m54_sequence_index',None)
        self.sequence=None;self.displayed=False;self.have_view=False;self.failure=''
        self.index=self.desired=0;self.intervals=[];self.last_present=None
        self.last_drawn_index=None
        if hide:self.panel.pack_forget()
        if not self.viewer.closed:self.viewer.request()

    def close(self):
        if self.closed:return
        self.unload();self.closed=True;self.panel.destroy()

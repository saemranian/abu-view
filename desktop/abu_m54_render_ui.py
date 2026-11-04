# SPDX-License-Identifier: Apache-2.0
"""Original shared desktop Render Studio for Abu M54; all exports remain local."""
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

import numpy as np

from abu_m54_cameras import (CameraPose, CameraKeyframe, CameraPath, RenderSettings,
                             save_camera_project, load_camera_project)
from abu_m54_ui import tip


def open_render_studio(viewer):
    existing = getattr(viewer, "render_studio", None)
    if existing is not None and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        return existing
    viewer.render_studio = RenderStudio(viewer)
    return viewer.render_studio


class RenderStudio(tk.Toplevel):
    def __init__(self, viewer):
        super().__init__(viewer.winfo_toplevel())
        from abu_m54_desktop import window_identity
        window_identity(self)
        self.viewer = viewer
        self.title("Abu M54 · Render Studio")
        self.geometry("1080x780")
        self.minsize(860, 620)
        self.protocol("WM_DELETE_WINDOW", self.close)
        session = getattr(viewer, "_render_studio_session", {})
        self.cameras = list(session.get("cameras", []))
        self.keyframes = list(session.get("keyframes", []))
        self._preview_geometry = {"cameras": [], "path": np.empty((0, 3))}
        self.source = session.get("source", str((viewer.data or {}).get("source", "")))
        self.preview_job = None
        self.poll_job = None
        self.sequence_watch_job = None
        self._sequence_state = None
        self.process = None
        self.worker = None
        self.cancel_file = None
        self.events = queue.Queue()
        self.closed = False
        self.busy = False
        self.last_output = None
        self.camera_vars = {key: tk.StringVar(self, value) for key, value in
                            (("name", "Camera 1"), ("x", "0"), ("y", "0"), ("z", "0"),
                             ("rx", "0"), ("ry", "0"), ("rz", "0"), ("fov", "45"))}
        self.interpolation = tk.StringVar(self, session.get("interpolation", "linear"))
        self.key_time = tk.StringVar(self, str(self.keyframes[-1].time_seconds+2 if self.keyframes else 0))
        self.timeline = tk.DoubleVar(self, 0)
        self.status = tk.StringVar(self, "Add cameras from the viewport, then capture keyframes for an animation.")
        self.preview_notice = tk.StringVar(self)
        self.render_vars = {key: tk.StringVar(self, value) for key, value in
                            (("format", "png"), ("width", "1920"), ("height", "1080"),
                             ("fps", "30"), ("supersampling", "1"), ("quality", "85"),
                             ("encoder", "auto"), ("near", "0.01"), ("far", "100000"),
                             ("ffmpeg_path", ""),
                             ("output", str(Path.home() / "Pictures")), ("layer", "A"))}
        self.background = (0.063, 0.078, 0.09)
        self.animate_sequence = tk.BooleanVar(self, session.get("animate_sequence", True))
        for key, value in session.get("render_values", {}).items():
            if key in self.render_vars:
                self.render_vars[key].set(value)
        self.background = session.get("background", self.background)
        header = ttk.Frame(self, padding=12)
        header.pack(fill="x")
        ttk.Label(header, text="Render Studio", font=("Segoe UI", 18)).pack(side="left")
        ttk.Button(header, text="Save cameras & path…", command=self.save_project).pack(side="right", padx=4)
        ttk.Button(header, text="Load cameras & path…", command=self.load_project).pack(side="right", padx=4)
        ttk.Label(self, textvariable=self.preview_notice, wraplength=980, foreground="#c07010").pack(fill="x", padx=14)
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=12)
        self.camera_page = ttk.Frame(tabs, padding=12)
        self.path_page = ttk.Frame(tabs, padding=12)
        self.render_page = ttk.Frame(tabs, padding=12)
        tabs.add(self.camera_page, text="1  Cameras")
        tabs.add(self.path_page, text="2  Camera path")
        tabs.add(self.render_page, text="3  Render & export")
        self.build_cameras()
        self.build_path()
        self.build_render()
        ttk.Label(self, textvariable=self.status, wraplength=1000, padding=12).pack(fill="x")
        self.bind("<FocusIn>", lambda event: self.check_source())
        self.refresh(0 if self.cameras else None)
        initial_sequence = self.active_sequence()
        self._sequence_state = (initial_sequence.paths, initial_sequence.fps) if initial_sequence is not None else None
        self.watch_sequence()

    def check_source(self):
        current = str((self.viewer.data or {}).get("source", ""))
        sequence = self.active_sequence()
        same_sequence = sequence is not None and self.source in sequence.paths and current in sequence.paths
        self.preview_notice.set("The scene has changed. Saved render cameras remain in their original world coordinates; check framing before export."
                                if self.source and self.source != current and not same_sequence else "")
        self.update_summary()

    def active_sequence(self):
        player = getattr(self.viewer, "sequence_player", None)
        return getattr(player, "sequence", None) if player is not None else None

    def watch_sequence(self):
        """Reflect a source opened after this window, without rescanning files."""
        self.sequence_watch_job = None
        if self.closed:
            return
        sequence = self.active_sequence()
        state = (sequence.paths, sequence.fps) if sequence is not None else None
        if state != self._sequence_state:
            if state is not None and (self._sequence_state is None or state[0] != self._sequence_state[0]):
                self.animate_sequence.set(True)
            self._sequence_state = state
            self.update_summary()
        self.sequence_watch_job = self.after(500, self.watch_sequence)

    def action(self, function):
        try:
            return function()
        except Exception as error:
            messagebox.showerror("M54 Render Studio", str(error), parent=self)
            return None

    def build_cameras(self):
        page = self.camera_page
        left = ttk.Frame(page)
        left.pack(side="left", fill="both", expand=True, padx=(0, 18))
        tree_holder = ttk.Frame(left)
        tree_holder.pack(fill="both", expand=True)
        self.camera_list = ttk.Treeview(tree_holder, columns=("name", "fov"), show="headings", selectmode="browse")
        self.camera_list.heading("name", text="Render camera")
        self.camera_list.heading("fov", text="Vertical FOV")
        self.camera_list.column("fov", width=95, stretch=False)
        camera_scroll = ttk.Scrollbar(tree_holder, orient="vertical", command=self.camera_list.yview)
        camera_scroll.pack(side="right", fill="y")
        self.camera_list.configure(yscrollcommand=camera_scroll.set)
        self.camera_list.pack(side="left", fill="both", expand=True)
        self.camera_list.bind("<<TreeviewSelect>>", self.read_camera)
        self.camera_list.bind("<Double-1>", lambda event: self.look_through())
        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=10)
        tip(ttk.Button(buttons, text="+ From current view", command=self.add_camera),
            "Create a separate render camera at the current viewport pose and field of view. Reconstruction cameras stay unchanged.").pack(side="left")
        ttk.Button(buttons, text="Update from view", command=self.update_from_view).pack(side="left", padx=4)
        ttk.Button(buttons, text="Delete", command=self.delete_camera).pack(side="left")
        right = ttk.Frame(page, width=290)
        right.pack(side="right", fill="y")
        for row, (key, text) in enumerate((("name", "Camera name"), ("x", "World X"), ("y", "World Y"),
                                           ("z", "World Z"), ("rx", "Rotation X · degrees"),
                                           ("ry", "Rotation Y · degrees"), ("rz", "Rotation Z · degrees"),
                                           ("fov", "Vertical field of view · degrees"))):
            ttk.Label(right, text=text).grid(row=row*2, column=0, sticky="w", pady=(7, 0))
            entry = ttk.Entry(right, textvariable=self.camera_vars[key], width=31)
            entry.grid(row=row*2+1, column=0, sticky="ew")
            tip(entry, "World position uses the scene's units. Rotation is extrinsic XYZ in degrees, applied to camera right/down/forward axes."
                if key != "fov" else "Vertical perspective angle: smaller values zoom in; larger values show more. Supported range 1–170°. This is not a panorama render.")
        ttk.Button(right, text="Apply camera fields", command=self.apply_camera).grid(row=16, column=0, sticky="ew", pady=(12, 4))
        ttk.Button(right, text="Look through selected camera", command=self.look_through).grid(row=17, column=0, sticky="ew", pady=4)
        ttk.Label(right, text="Camera edits affect render cameras only.\nDouble-click a camera to preview it.\nSaved path keyframes are pose snapshots.", wraplength=280).grid(row=18, column=0, sticky="w", pady=12)

    def selected_camera_index(self):
        selection = self.camera_list.selection()
        return int(selection[0]) if selection else None

    def current_camera(self):
        index = self.selected_camera_index()
        return self.cameras[index] if index is not None else self.viewer.get_render_camera("Current view")

    def add_camera(self):
        def add():
            camera = self.viewer.get_render_camera(f"Camera {len(self.cameras)+1}")
            self.cameras.append(camera)
            self.refresh(len(self.cameras)-1)
            self.status.set("Camera captured. Position, rotation and field of view can be edited on the right.")
        self.action(add)

    def update_from_view(self):
        def update():
            index = self.selected_camera_index()
            if index is None:
                raise ValueError("Select a render camera first")
            self.cameras[index] = self.viewer.get_render_camera(self.cameras[index].name)
            self.refresh(index)
        self.action(update)

    def delete_camera(self):
        index = self.selected_camera_index()
        if index is not None:
            del self.cameras[index]
            self.refresh(min(index, len(self.cameras)-1) if self.cameras else None)
            self.status.set("Camera removed. Existing path keyframes retain their captured poses.")

    def read_camera(self, event=None):
        index = self.selected_camera_index()
        if index is None:
            return
        camera = self.cameras[index]
        self.camera_vars["name"].set(camera.name)
        for key, value in zip(("x", "y", "z", "rx", "ry", "rz", "fov"),
                              [*camera.position, *camera.euler_xyz_degrees, camera.fov_y_degrees]):
            self.camera_vars[key].set(f"{value:.12g}")

    def apply_camera(self):
        def apply():
            index = self.selected_camera_index()
            if index is None:
                raise ValueError("Add or select a render camera first")
            fields = self.camera_vars
            camera = CameraPose.from_euler(fields["name"].get(),
                                           [float(fields[key].get()) for key in ("x", "y", "z")],
                                           [float(fields[key].get()) for key in ("rx", "ry", "rz")],
                                           float(fields["fov"].get()))
            self.cameras[index] = camera
            self.refresh(index)
            self.viewer.look_through_render_camera(camera)
        self.action(apply)

    def look_through(self):
        self.action(lambda: self.viewer.look_through_render_camera(self.current_camera()))

    def build_path(self):
        page = self.path_page
        ttk.Label(page, text="Capture camera poses at increasing times. The first keyframe starts at 0 seconds; later keys set the path duration.",
                  wraplength=950).pack(anchor="w", pady=(0, 10))
        tree_holder = ttk.Frame(page)
        tree_holder.pack(fill="both", expand=True)
        self.key_list = ttk.Treeview(tree_holder, columns=("time", "name", "fov"), show="headings", selectmode="browse", height=12)
        for key, name in (("time", "Time · seconds"), ("name", "Captured camera pose"), ("fov", "Vertical FOV")):
            self.key_list.heading(key, text=name)
        key_scroll = ttk.Scrollbar(tree_holder, orient="vertical", command=self.key_list.yview)
        key_scroll.pack(side="right", fill="y")
        self.key_list.configure(yscrollcommand=key_scroll.set)
        self.key_list.pack(side="left", fill="both", expand=True)
        self.key_list.bind("<<TreeviewSelect>>", self.read_key)
        self.key_list.bind("<Double-1>", lambda event: self.preview_selected_key())
        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=12)
        ttk.Label(controls, text="Time").pack(side="left")
        ttk.Entry(controls, textvariable=self.key_time, width=9).pack(side="left", padx=5)
        ttk.Button(controls, text="+ Selected camera", command=lambda: self.add_key(False)).pack(side="left", padx=3)
        ttk.Button(controls, text="+ Current view", command=lambda: self.add_key(True)).pack(side="left", padx=3)
        ttk.Button(controls, text="Replace selected", command=self.replace_key).pack(side="left", padx=3)
        ttk.Button(controls, text="Delete key", command=self.delete_key).pack(side="left", padx=3)
        ttk.Label(controls, text="Motion").pack(side="left", padx=(14, 4))
        interpolation = ttk.Combobox(controls, textvariable=self.interpolation, values=("linear", "smooth"), state="readonly", width=9)
        interpolation.pack(side="left")
        interpolation.bind("<<ComboboxSelected>>", lambda event: self.refresh_path())
        tip(interpolation, "Linear follows straight segments. Smooth uses a cubic position curve and may pass outside the keyframe bounds; check for obstacles. Both use shortest-arc rotation interpolation.")
        preview = ttk.Frame(page)
        preview.pack(fill="x", pady=6)
        self.play_button = ttk.Button(preview, text="Play preview", command=self.toggle_preview)
        self.play_button.pack(side="left", padx=(0, 8))
        self.slider = ttk.Scale(preview, from_=0, to=1, variable=self.timeline, command=self.scrub)
        self.slider.pack(side="left", fill="x", expand=True)
        ttk.Label(preview, textvariable=self.timeline, width=12).pack(side="left", padx=6)
        ttk.Label(page, text="Preview uses the desktop viewport. Exports use the chosen output aspect ratio and omit grids, axes and editing handles.",
                  wraplength=950).pack(anchor="w", pady=8)

    def make_path(self):
        return CameraPath(tuple(self.keyframes), self.interpolation.get()) if self.keyframes else None

    def add_key(self, from_view):
        def add():
            camera = self.viewer.get_render_camera("Viewport key") if from_view else self.current_camera()
            key = CameraKeyframe(float(self.key_time.get()), camera)
            keys = sorted([*self.keyframes, key], key=lambda item: item.time_seconds)
            CameraPath(tuple(keys), self.interpolation.get())
            self.keyframes = keys
            self.key_time.set(f"{keys[-1].time_seconds+2:g}")
            self.refresh_path()
        self.action(add)

    def read_key(self, event=None):
        selection = self.key_list.selection()
        if selection:
            self.key_time.set(f"{self.keyframes[int(selection[0])].time_seconds:g}")

    def replace_key(self):
        def replace():
            selection = self.key_list.selection()
            if not selection:
                raise ValueError("Select a keyframe to replace")
            keys = list(self.keyframes)
            keys[int(selection[0])] = CameraKeyframe(float(self.key_time.get()), self.viewer.get_render_camera("Viewport key"))
            keys.sort(key=lambda key: key.time_seconds)
            CameraPath(tuple(keys), self.interpolation.get())
            self.keyframes = keys
            self.refresh_path()
        self.action(replace)

    def delete_key(self):
        def delete():
            selection = self.key_list.selection()
            if not selection:
                return
            keys = list(self.keyframes)
            del keys[int(selection[0])]
            if keys and keys[0].time_seconds != 0:
                shift = keys[0].time_seconds
                keys = [CameraKeyframe(key.time_seconds-shift, key.camera) for key in keys]
            self.keyframes = keys
            self.refresh_path()
        self.action(delete)

    def preview_selected_key(self):
        selection = self.key_list.selection()
        if selection:
            self.viewer.look_through_render_camera(self.keyframes[int(selection[0])].camera)

    def scrub(self, value):
        path = self.make_path()
        if path:
            self.viewer.look_through_render_camera(path.sample(float(value)))

    def toggle_preview(self):
        if self.preview_job is not None:
            self.stop_preview()
            return
        path = self.make_path()
        if path is None or path.duration <= 0:
            self.status.set("Add at least two keyframes to play a camera path.")
            return
        self.preview_started = time.monotonic()
        self.play_button.configure(text="Stop preview")
        self.tick_preview()

    def tick_preview(self):
        path = self.make_path()
        elapsed = time.monotonic() - self.preview_started
        if path is None:
            self.stop_preview()
            return
        self.timeline.set(min(elapsed, path.duration))
        self.viewer.look_through_render_camera(path.sample(elapsed))
        if elapsed >= path.duration:
            self.stop_preview()
        else:
            self.preview_job = self.after(33, self.tick_preview)

    def stop_preview(self):
        if self.preview_job is not None:
            self.after_cancel(self.preview_job)
            self.preview_job = None
        self.play_button.configure(text="Play preview")

    def refresh(self, selected=None):
        self.camera_list.delete(*self.camera_list.get_children())
        for index, camera in enumerate(self.cameras):
            self.camera_list.insert("", "end", iid=str(index), values=(camera.name, f"{camera.fov_y_degrees:g}°"))
        if selected is not None and 0 <= selected < len(self.cameras):
            self.camera_list.selection_set(str(selected))
            self.read_camera()
        self.refresh_path()

    def refresh_path(self):
        self.key_list.delete(*self.key_list.get_children())
        for index, key in enumerate(self.keyframes):
            self.key_list.insert("", "end", iid=str(index), values=(f"{key.time_seconds:g}", key.camera.name, f"{key.camera.fov_y_degrees:g}°"))
        path = self.make_path()
        self.slider.configure(to=max(1e-6, path.duration if path else 1))
        points = np.array([path.sample(t).position for t in np.linspace(0, path.duration, min(240, max(2, len(path.keyframes)*20)))]) if path else np.empty((0, 3))
        self._preview_geometry = {"cameras": list(self.cameras), "path": points}
        self.viewer.request()
        self.update_summary()

    def preview_geometry(self):
        return self._preview_geometry

    def save_project(self):
        target = filedialog.asksaveasfilename(parent=self, title="Save render cameras & path", defaultextension=".json", filetypes=[("M54 camera project", "*.json")])
        if target:
            self.action(lambda: save_camera_project(target, self.cameras, self.make_path()))

    def load_project(self):
        target = filedialog.askopenfilename(parent=self, title="Load render cameras & path", filetypes=[("M54 camera project", "*.json")])
        if not target:
            return
        def load():
            cameras, path = load_camera_project(target)
            self.stop_preview()
            self.cameras = cameras
            self.keyframes = list(path.keyframes) if path else []
            self.interpolation.set(path.interpolation if path else "linear")
            self.refresh(0 if cameras else None)
            self.status.set("Camera project loaded. Check the scene's scale and coordinate system before rendering.")
        self.action(load)

    def build_render(self):
        page = self.render_page
        form = ttk.Frame(page)
        form.pack(fill="x")
        rows = [("format", "Output", ("png", "jpeg", "sequence", "mp4"), "PNG/JPEG saves the current source frame. Sequence/MP4 animates the loaded PLY sequence when enabled; otherwise it uses the camera path on one static scene."),
                ("layer", "Scene layer", ("A", "B"), "Choose the transformed A scene or registered B comparison. Each render exports one layer; overlays are not combined."),
                ("width", "Width · pixels", None, "Output width; 1920 × 1080 for HD, 3840 × 2160 for 4K. Larger output needs more rendering time and memory."),
                ("height", "Height · pixels", None, "Output height; MP4 dimensions must be even. The vertical FOV stays fixed as aspect ratio changes."),
                ("fps", "Frames per second", None, "Animation sampling rate. Higher values create more frames; they do not improve each frame's spatial detail."),
                ("supersampling", "Antialiasing scale", ("1", "2"), "2 renders at double width and height, then downsamples. It needs approximately 4× pixel work and framebuffer memory. Internal render limit: 8192 pixels per side and 32 megapixels."),
                ("quality", "JPEG / video quality · 1–100", None, "Higher quality reduces compression loss and increases file size. PNG is lossless and ignores this value."),
                ("encoder", "Video encoder", ("auto", "nvenc", "cpu"), "Auto tries NVIDIA NVENC first, then the local FFmpeg CPU encoder. Rendering remains on the GPU. FFmpeg must already be installed locally."),
                ("near", "Near clip · scene units", None, "Geometry closer than this is excluded. Increase to clip unwanted foreground; decrease to retain close surfaces. Must be positive."),
                ("far", "Far clip · scene units", None, "Geometry beyond this distance is excluded. Keep above the scene's depth; smaller values do not improve splat quality by themselves.")]
        for row, (key, label, values, hint) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 14), pady=5)
            widget = (ttk.Combobox(form, textvariable=self.render_vars[key], values=values, state="readonly", width=23)
                      if values else ttk.Entry(form, textvariable=self.render_vars[key], width=25))
            widget.grid(row=row, column=1, sticky="ew", pady=5)
            tip(widget, hint)
            self.render_vars[key].trace_add("write", lambda *_: self.update_summary())
        extras = ttk.Frame(form)
        extras.grid(row=0, column=2, rowspan=10, sticky="nw", padx=28)
        for title, size in (("HD · 1920 × 1080", (1920, 1080)), ("4K · 3840 × 2160", (3840, 2160)), ("Square · 2048 × 2048", (2048, 2048))):
            ttk.Button(extras, text=title, command=lambda pair=size: self.set_resolution(pair)).pack(fill="x", pady=4)
        ttk.Button(extras, text="Background color…", command=self.choose_background).pack(fill="x", pady=(18, 4))
        ttk.Button(extras, text="Choose FFmpeg executable…", command=self.choose_ffmpeg).pack(fill="x", pady=4)
        tip(ttk.Entry(extras, textvariable=self.render_vars["ffmpeg_path"], width=31),
            "Optional path to your existing FFmpeg executable. Leave blank for automatic discovery. No encoder is downloaded or bundled by this feature.").pack(fill="x", pady=4)
        ttk.Label(extras, text="Native GPU export\nNo grids or editing handles\nOne selected scene layer\nNo internet uploads", wraplength=280).pack(anchor="w", pady=12)
        self.sequence_check = ttk.Checkbutton(extras, text="Animate loaded PLY sequence",
                                              variable=self.animate_sequence, command=self.update_summary)
        self.sequence_check.pack(anchor="w", pady=4)
        tip(self.sequence_check, "For PNG sequence or MP4: export all source frames from the start, at the sequence's source FPS. Output FPS resamples time by holding frames; it never invents intermediate splats. Camera keyframes are optional. Supported for layer A only. PNG/JPEG always saves the current frame.")
        self.sequence_notice = tk.StringVar(self)
        ttk.Label(extras, textvariable=self.sequence_notice, wraplength=280).pack(anchor="w", pady=4)
        output = ttk.Frame(page)
        output.pack(fill="x", pady=(12, 8))
        ttk.Label(output, text="Output folder").pack(side="left")
        ttk.Entry(output, textvariable=self.render_vars["output"]).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(output, text="Browse…", command=self.choose_output).pack(side="left")
        self.summary = tk.StringVar(self)
        ttk.Label(page, textvariable=self.summary, wraplength=980).pack(fill="x", pady=6)
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=10)
        self.render_button = ttk.Button(actions, text="Render to new folder", command=self.start_render)
        self.render_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="Cancel render", command=self.cancel_render, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        self.output_button = ttk.Button(actions, text="Open output folder", command=self.open_output, state="disabled")
        self.output_button.pack(side="right")
        self.progress = ttk.Progressbar(actions, maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=12)

    def set_resolution(self, size):
        self.render_vars["width"].set(str(size[0]))
        self.render_vars["height"].set(str(size[1]))

    def choose_background(self):
        color = colorchooser.askcolor(parent=self, initialcolor="#%02x%02x%02x" % tuple(int(v*255) for v in self.background))[0]
        if color:
            self.background = tuple(v/255 for v in color)

    def choose_output(self):
        folder = filedialog.askdirectory(parent=self, title="Choose render output folder")
        if folder:
            self.render_vars["output"].set(folder)

    def choose_ffmpeg(self):
        executable = filedialog.askopenfilename(parent=self, title="Choose an installed FFmpeg executable", filetypes=[("Executable", "*.exe"), ("All files", "*")])
        if executable:
            self.render_vars["ffmpeg_path"].set(executable)

    def open_output(self):
        def show():
            if not self.last_output or not Path(self.last_output).is_dir():
                raise ValueError("No render output folder is available yet")
            if sys.platform == "win32":
                os.startfile(self.last_output)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", self.last_output])
        self.action(show)

    def update_summary(self):
        if not hasattr(self, "summary"):
            return
        try:
            path = self.make_path()
            sequence = self.active_sequence()
            if hasattr(self, "sequence_check"):
                self.sequence_check.configure(state="normal" if sequence is not None else "disabled")
                self.sequence_notice.set(f"{sequence.count:,} source frames · {sequence.fps:g} source fps · {sequence.duration:g}s"
                                         if sequence is not None else "Open a PLY sequence to animate source geometry.")
            dynamic = sequence is not None and self.animate_sequence.get() and self.render_vars["format"].get() in ("sequence", "mp4")
            duration = sequence.duration if dynamic else (path.duration if path else 0)
            fps = float(self.render_vars["fps"].get())
            frames = max(1, math.ceil(duration*fps-1e-10))
            label = "PLY sequence" if dynamic else "Camera path"
            camera_note = (" Camera path plays from time 0, holding its last pose if shorter; otherwise the selected/current camera stays fixed."
                           if dynamic else "")
            self.summary.set(f"{label}: {duration:g} seconds · {frames:,} frames at {fps:g} fps · encoded duration {frames/fps:.3f}s.{camera_note} "
                             "Frames sample from time 0 up to (not including) the animation end. "
                             "A new output subfolder is created for every render; existing outputs are preserved.")
        except (ValueError, ZeroDivisionError):
            self.summary.set("Enter valid render settings to calculate the animation frame count.")

    def settings(self):
        values = self.render_vars
        return RenderSettings(width=int(values["width"].get()), height=int(values["height"].get()),
                              fps=float(values["fps"].get()), format=values["format"].get(),
                              supersampling=int(values["supersampling"].get()), quality=int(values["quality"].get()),
                              encoder=values["encoder"].get(), ffmpeg_path=values["ffmpeg_path"].get().strip(), background=self.background,
                              near=float(values["near"].get()), far=float(values["far"].get()))

    def start_render(self):
        if self.busy:
            return
        def start():
            self.stop_preview()
            settings = self.settings()
            camera = self.current_camera()
            path = self.make_path()
            player = getattr(self.viewer, "sequence_player", None)
            sequence = self.active_sequence()
            dynamic = sequence is not None and self.animate_sequence.get() and settings.format in ("sequence", "mp4")
            if settings.format in ("sequence", "mp4") and not dynamic and (path is None or path.duration <= 0):
                raise ValueError("Add at least two keyframes with different times before rendering an animation")
            duration = sequence.duration if dynamic else path.duration if path else 0
            if settings.format in ("sequence", "mp4") and math.ceil(duration*settings.fps-1e-10) > 100000:
                raise ValueError("This export exceeds 100,000 frames; shorten the path or lower the frame rate")
            layer = self.render_vars["layer"].get()
            if dynamic and layer != "A":
                raise ValueError("PLY sequence animation uses layer A. Choose A, or disable Animate loaded PLY sequence to export the static B comparison.")
            scene = self.viewer.data if layer == "A" else (self.viewer.comparison or {}).get("b")
            if not scene:
                raise ValueError(f"Open scene layer {layer} before rendering")
            descriptor = None
            if dynamic:
                player.pause()
                descriptor = player.export_descriptor()
            output = Path(self.render_vars["output"].get()).expanduser().resolve()
            output.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.TemporaryDirectory(prefix="abu_m54_render_")
            self.worker = None
            try:
                self.busy = True
                self.render_button.configure(state="disabled")
                self.cancel_button.configure(state="normal")
                self.progress["value"] = 0
                self.status.set("Preparing local PLY sequence rendering…" if dynamic else "Preparing a local scene snapshot in the background…")
                root = Path(temporary.name)
                self.cancel_file = root / "cancel"
                request = {"schema": 1, "scene": str(root / "scene.npz"), "camera": camera.to_dict(),
                           "path": path.to_dict() if path else None, "settings": settings.to_dict(),
                           "output": str(output), "cancel_file": str(self.cancel_file)}
                if descriptor is not None:
                    request.pop("scene")
                    request["source_sequence"] = descriptor
                # A non-daemon cleanup owner finishes snapshot writes and reaps
                # the worker even when Tk closes during staging. Schedule polling
                # before starting it, so a failed Tk callback setup cannot orphan it.
                self.worker = threading.Thread(target=self.run_worker, args=(None if dynamic else scene, request, temporary), daemon=False)
                self.poll_job = self.after(100, self.poll_events)
                self.worker.start()
            except Exception:
                self.busy = False
                if self.poll_job is not None:
                    try:
                        self.after_cancel(self.poll_job)
                    except tk.TclError:
                        pass
                    self.poll_job = None
                try:
                    self.render_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self.status.set("Render could not start. Correct the error and try again.")
                except tk.TclError:
                    pass
                # Thread.start failures occur before the cleanup owner runs.
                if self.worker is None or not self.worker.is_alive():
                    temporary.cleanup()
                    self.worker = None
                    self.cancel_file = None
                elif self.cancel_file is not None:
                    self.cancel_file.touch()
                raise
        self.action(start)

    def run_worker(self, scene, request, temporary):
        process = None
        try:
            if request.get("source_sequence") is None:
                from control_points_comparison import save_scene
                save_scene(Path(request["scene"]), scene)
            if Path(request["cancel_file"]).exists():
                self.events.put({"event": "cancelled", "message": "Cancelled before rendering."})
                return
            job = Path(temporary.name) / "job.json"
            job.write_text(json.dumps(request, allow_nan=False), encoding="utf-8")
            command = [sys.executable, "-B", str(Path(__file__).with_name("abu_m54_render.py")), "--job", str(job)]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding="utf-8", errors="replace",
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.process = process
            last_lines = []
            terminal = False
            for line in process.stdout:
                try:
                    event = json.loads(line)
                    if isinstance(event, dict) and "event" in event:
                        self.events.put(event)
                        terminal |= event["event"] in ("done", "error", "cancelled")
                    else:
                        last_lines.append(line.rstrip())
                except json.JSONDecodeError:
                    last_lines.append(line.rstrip())
                last_lines = last_lines[-15:]
            code = process.wait()
            if not terminal:
                self.events.put({"event": "error", "message": f"Renderer exited ({code}). " + "\n".join(last_lines)})
        except Exception as error:
            self.events.put({"event": "error", "message": str(error)})
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if process is not None and process.stdout is not None:
                process.stdout.close()
            self.process = None
            try:
                temporary.cleanup()
            except OSError as error:
                self.events.put({"event": "error", "message": f"Render finished, but its temporary snapshot could not be removed: {error}"})
            finally:
                self.events.put({"event": "finished"})

    def poll_events(self):
        self.poll_job = None
        if self.closed:
            return
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event.get("event")
            if event.get("output") and Path(event["output"]).is_dir():
                self.last_output = str(event["output"])
                self.output_button.configure(state="normal")
            if kind == "progress":
                frame, total = event.get("frame", 0), event.get("total", 1)
                if "frame" in event and "total" in event:
                    self.progress["value"] = 100 * frame / max(1, total)
                self.status.set(event.get("message", f"Rendering frame {frame:,} / {total:,}"))
            elif kind == "done":
                self.progress["value"] = 100
                self.status.set("Render complete: " + str(event.get("output", "")))
            elif kind == "error":
                self.status.set("Render failed: " + str(event.get("message", "Unknown error")))
                messagebox.showerror("M54 render failed", str(event.get("message", "Unknown error")), parent=self)
            elif kind == "cancelled":
                self.status.set("Render cancelled. " + str(event.get("message", "")) + " " + str(event.get("output", "")))
            elif kind == "finished":
                self.busy = False
                self.render_button.configure(state="normal")
                self.cancel_button.configure(state="disabled")
        if self.busy:
            self.poll_job = self.after(100, self.poll_events)

    def cancel_render(self):
        if self.cancel_file is not None:
            try:
                self.cancel_file.touch()
            except OSError:
                pass
        if self.busy:
            self.status.set("Cancelling after the current render operation…")
            self.cancel_button.configure(state="disabled")

    def close(self):
        if self.closed:
            return
        self.stop_preview()
        self.cancel_render()
        self.closed = True
        if self.sequence_watch_job is not None:
            self.after_cancel(self.sequence_watch_job)
            self.sequence_watch_job = None
        if self.poll_job is not None:
            self.after_cancel(self.poll_job)
            self.poll_job = None
        process = self.process
        if process is not None and process.poll() is None:
            def finish():
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
            threading.Thread(target=finish, daemon=False).start()
        self.viewer.render_studio = None
        self.viewer._render_studio_session = {
            "cameras": tuple(self.cameras), "keyframes": tuple(self.keyframes),
            "interpolation": self.interpolation.get(), "source": self.source,
            "render_values": {key: value.get() for key, value in self.render_vars.items()},
            "background": self.background,
            "animate_sequence": self.animate_sequence.get(),
        }
        self.destroy()
        if not getattr(self.viewer, "closed", False):
            self.viewer.request()

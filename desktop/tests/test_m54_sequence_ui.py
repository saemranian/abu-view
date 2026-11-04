# SPDX-License-Identifier: Apache-2.0
"""Actual shared native sequence controller, navigation and lifecycle checks."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np


@unittest.skipUnless(sys.platform=='win32' and os.environ.get('ABU_TEST_NATIVE_GPU')=='1', 'Native Windows GPU timeline')
class SequenceUITests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from abu_m54_native import M54NativeViewer
        from abu_m54_host import ViewerHost
        from abu_m54_sequence_ui import SequencePlayer
        from abu_m54_sequence import discover_sequence
        from test_m54_render_sequence import small_frame
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.folder=Path(self.temporary.name)
        for i in range(3):small_frame(self.folder/f'frame_{i}.ply',i)
        self.root=tk.Tk();self.root.geometry('800x600+0+0');self.root.attributes('-alpha',0.)
        self.viewer=M54NativeViewer(ViewerHost(self.root),self.root,compact=True)
        self.viewer.pack(fill='both',expand=True)
        self.addCleanup(self.cleanup)
        self.root.update()
        self.assertIsNotNone(self.viewer.context)
        self.player=SequencePlayer(self.viewer);self.viewer.sequence_player=self.player
        self.sequence=discover_sequence(self.folder,fps=5)
        self.player.install(self.sequence)
        self.wait(lambda:self.player.displayed and len(self.player.gpu.cached_indices)==3)

    def cleanup(self):
        self.viewer.close();self.root.destroy()

    def wait(self,condition,timeout=8):
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            self.root.update()
            if condition():return
            if self.player.failure:self.fail(self.player.failure)
            time.sleep(.002)
        self.fail('Timeline did not reach expected state: '+self.player.status.get())

    def test_scrub_step_preserves_full_camera_and_scene_transform(self):
        from abu_m54_cameras import CameraPose
        from abu_m54 import SceneTransform
        camera=CameraPose.from_euler('Fixed',[4,-3,8],[23,-49,17],57)
        self.viewer.look_through_render_camera(camera)
        transform=SceneTransform(translation=np.array([2.,-1.,3.]),scale=1.5)
        self.viewer.apply_transform('A',transform)
        before=self.viewer.get_render_camera()
        for index in (2,1,0):
            self.player.seek(index);self.wait(lambda:self.player.index==index)
            after=self.viewer.get_render_camera()
            np.testing.assert_allclose(after.c2w_matrix,before.c2w_matrix,atol=1e-12)
            self.assertAlmostEqual(after.fov_y_degrees,57)
            np.testing.assert_allclose(self.viewer.data['gaussian_transform'],transform.matrix())
            self.assertEqual(self.viewer.data['gaussians'].count,index+3)
        self.viewer.sequence_key('next');self.wait(lambda:self.player.index==1)
        self.viewer.sequence_key('previous');self.wait(lambda:self.player.index==0)
        self.assertFalse(self.player.playing)

    def test_loop_uses_resident_frames_and_nonloop_stops(self):
        cache=self.player.gpu
        with patch.object(cache,'request',wraps=cache.request) as upload:
            self.player.toggle_play()
            self.wait(lambda:self.player.presented_count>=9,timeout=4)
            self.assertTrue(self.player.playing)
            self.assertFalse(upload.called,'A warmed loop should never upload again')
            self.player.pause()
        self.player.loop.set(False);self.player.seek(0);self.wait(lambda:self.player.index==0)
        self.player.toggle_play()
        self.wait(lambda:not self.player.playing and self.player.index==2,timeout=3)
        self.assertEqual(len(cache.cached_indices),3)

    def test_export_fps_and_close_releases_gpu_and_cpu(self):
        self.player.fps.set('24');self.assertTrue(self.player.settings_changed())
        self.player.seek(1);self.wait(lambda:self.player.index==1)
        descriptor=self.player.export_descriptor()
        self.assertEqual(descriptor['start_index'],1)
        self.assertEqual(descriptor['sequence']['fps'],24)
        self.player.fps.set('nan');self.assertFalse(self.player.settings_changed())
        self.assertEqual(self.player.sequence.fps,24)
        cpu,gpu=self.player.cache,self.player.gpu
        self.player.unload()
        self.assertEqual(gpu.allocated_bytes,0)
        self.assertEqual(cpu.used_bytes,0)
        self.assertTrue(cpu.closed)
        self.assertIsNone(self.player.sequence)
        self.assertNotIn('_m54_sequence_owner',self.viewer.data)
        self.assertEqual(self.viewer.data['gaussians'].count,4)

    def test_static_scene_replaces_sequence_and_stale_discovery_is_ignored(self):
        from abu_m54 import load_scene
        self.viewer.set_data(load_scene(self.folder/'frame_2.ply'))
        self.assertIsNone(self.player.sequence)
        old_generation=self.player.generation
        self.player.events.put((old_generation-1,self.sequence,None))
        self.player.poll()
        self.assertIsNone(self.player.sequence)
        self.assertEqual(self.viewer.data['gaussians'].count,5)

    def test_discovery_start_failures_reset_pending_state(self):
        for target in ('thread','schedule'):
            context=(patch('abu_m54_sequence_ui.threading.Thread.start',side_effect=RuntimeError('Start failed'))
                     if target=='thread' else patch.object(self.player,'schedule',side_effect=RuntimeError('Schedule failed')))
            with context:
                self.player.open(self.folder/'frame_0.ply')
            self.assertFalse(self.player.preparing)
            self.assertIsNone(self.player.poll_job)
            self.assertIsNone(self.player.discovery_thread)
            self.assertIn('failed',self.player.failure.lower())

    def test_seek_back_after_one_frame_budget_eviction_redraws_same_index(self):
        from abu_m54_sequence_gpu import SequenceGPUCache
        self.viewer.gl.wglMakeCurrent(self.viewer.dc,self.viewer.context)
        self.player.gpu.close()
        budget=max(f.gpu_bytes for f in self.sequence.frames)
        self.player.gpu=SequenceGPUCache(self.viewer.gl,budget_bytes=budget)
        self.player.gpu_limit=budget
        self.player.advance();self.player.advance()
        self.assertTrue(self.player.gpu.contains(0))
        before=self.viewer.get_render_camera().c2w_matrix.copy()
        self.player.seek(1);self.player.advance()
        self.assertFalse(self.player.gpu.contains(0))
        self.assertTrue(self.player.buffering)
        self.player.seek(0);self.player.advance();self.player.advance()
        self.assertTrue(self.player.gpu.contains(0))
        self.assertFalse(self.player.buffering)
        self.assertEqual(self.player.index,0)
        np.testing.assert_allclose(self.viewer.get_render_camera().c2w_matrix,before,atol=1e-12)


if __name__=='__main__':unittest.main()

"""Small, independent pose fixtures for M54's shared RealityScan CSV reader."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from abu_m54 import load_scene


def expected_c2w(yaw, pitch, roll):
    # Independent Euler composition, not a copy of the importer's trig formula.
    # Intrinsic ZXY camera-to-world: Rz(-yaw) Rx(pitch-180) Ry(-roll).
    return Rotation.from_euler('ZXY', [-yaw, pitch-180., -roll], degrees=True).as_matrix()


def write_angles(path, records):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['#name', 'x', 'y', 'alt', 'yaw', 'pitch', 'roll'])
        for name, center, angles in records:
            writer.writerow([name, *center, *angles])


class RealityScanCsvTests(unittest.TestCase):
    def assert_rotation(self, actual, expected):
        self.assertEqual(actual.dtype, np.dtype('float64'))
        np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-14)
        np.testing.assert_allclose(actual.T @ actual, np.eye(3), rtol=0, atol=2e-14)
        self.assertAlmostEqual(np.linalg.det(actual), 1., places=13)

    def test_full_matrices_with_roll_hemispheres_and_near_poles(self):
        cases = [(0., 0., 0.), (90., 90., 0.), (-125., 157., 0.),
                 (32., 47., 23.), (-71., 132., -37.), (159., 26., 91.),
                 (27., 35., 180.), (27., 35., -180.), (-112., 146., 180.),
                 (-112., 146., -180.), (41., 1e-7, 73.), (-83., 180.-1e-7, -58.),
                 (119., 1e-7, -180.), (-61., 180.-1e-7, 180.),
                 (360.+29., 90., 180.), (-720.-18., 90., -180.)]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'cameras.csv'
            records = []
            for index, angles in enumerate(cases):
                center = np.array([1e7+index+.123456789, -234.567890123, 789.012345678])
                records.append((f'cam_{index}.png', center, angles))
            write_angles(path, records)
            original = path.read_bytes()
            scene = load_scene(path)
            self.assertEqual(len(scene['centers']), len(cases))
            for name, center, angles in records:
                with self.subTest(angles=angles):
                    np.testing.assert_array_equal(scene['centers'][name], center)
                    self.assert_rotation(scene['camera_rotations'][name], expected_c2w(*angles))
            self.assertEqual(path.read_bytes(), original)

    def test_equivalent_csv_angles_and_json_match_on_both_hemispheres(self):
        cases = [(42., 35., 0.), (-15., 35., -180.), (87., 1e-7, 0.),
                 (-112., 1e-7, -180.), (31., 90.-1e-7, 0.), (-47., 90.-1e-7, -180.)]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); canonical = []; equivalent = []; frames = []
            for index, angles in enumerate(cases):
                name = f'cam_{index}.png'; matrix = expected_c2w(*angles)
                center = -1e7*matrix[:, 2]
                canonical.append((name, center, angles))
                yaw, pitch, roll = angles
                equivalent.append((name, center, (yaw+180., 180.-pitch, roll+180.)))
                opengl = np.eye(4); opengl[:3, :3] = matrix @ np.diag([1., -1., -1.]); opengl[:3, 3] = center
                frames.append({'file_path': 'images/'+name, 'transform_matrix': opengl.tolist()})
            write_angles(root/'cameras.csv', canonical)
            write_angles(root/'compatible.csv', equivalent)
            (root/'transforms.json').write_text(json.dumps({'frames': frames}), encoding='utf-8')
            scenes = [load_scene(root/name) for name in ('cameras.csv', 'compatible.csv', 'transforms.json')]
            for scene in scenes:
                centers = {Path(name).name: center for name, center in scene['centers'].items()}
                matrices = {Path(name).name: matrix for name, matrix in scene['camera_rotations'].items()}
                for name, center, angles in canonical:
                    np.testing.assert_array_equal(centers[name], center)
                    self.assert_rotation(matrices[name], expected_c2w(*angles))
                    self.assertAlmostEqual(np.dot(matrices[name][:, 2], -center/np.linalg.norm(center)), 1., places=13)
                self.assertEqual(sum(center[2]>0 for center in centers.values()), 3)
                self.assertEqual(sum(center[2]<0 for center in centers.values()), 3)

    def test_half_turn_roll_changes_forward_and_right_not_down(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'angles.csv'
            write_angles(path, [('zero', [1, 2, 3], (37, 56, 0)),
                                ('plus', [1, 2, 3], (37, 56, 180)),
                                ('minus', [1, 2, 3], (37, 56, -180))])
            rotations = load_scene(path)['camera_rotations']
            for name in ('plus', 'minus'):
                self.assert_rotation(rotations[name], rotations['zero'] @ np.diag([-1., 1., -1.]))

    def test_cardinal_axes_are_right_down_forward(self):
        cases = [((0, 0, 0), np.diag([1., -1., -1.])),
                 ((0, 90, 0), np.array([[1., 0, 0], [0, 0, 1.], [0, -1., 0]])),
                 ((0, 0, 180), np.diag([-1., -1., 1.]))]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'axes.csv'
            write_angles(path, [(str(i), [0, 0, 1], angles) for i, (angles, _) in enumerate(cases)])
            scene = load_scene(path)
            for i, (_, matrix) in enumerate(cases):
                self.assert_rotation(scene['camera_rotations'][str(i)], matrix)

    def test_explicit_camera_to_world_quaternion_csv_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'quaternions.csv'
            rotations = [Rotation.from_euler('xyz', [23, -71, 146], degrees=True),
                         Rotation.from_euler('z', 180, degrees=True)]
            center = np.array([1e7+.01234567, -23.4567890123, 45.6789012345])
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.writer(stream)
                writer.writerow(['image', 'center_x', 'center_y', 'center_z',
                                 'camera_to_world_qw', 'camera_to_world_qx', 'camera_to_world_qy', 'camera_to_world_qz'])
                for i, rotation in enumerate(rotations):
                    quaternion = rotation.as_quat()[[3, 0, 1, 2]]*(-7 if i else 3)
                    writer.writerow([f'{i}.png', *center, *quaternion])
            scene = load_scene(path)
            for i, rotation in enumerate(rotations):
                np.testing.assert_array_equal(scene['centers'][f'{i}.png'], center)
                self.assert_rotation(scene['camera_rotations'][f'{i}.png'], rotation.as_matrix())


if __name__ == '__main__':
    unittest.main()

# SPDX-License-Identifier: Apache-2.0
"""Small independent format/math regression fixtures; no user datasets."""
import struct
import tempfile
import unittest
from pathlib import Path
import numpy as np
from abu_m54_gaussian import GaussianAsset, is_gaussian_ply, load_gaussian_ply, SH_C0


def asset_fixture():
    return GaussianAsset(np.array([[1e9 + .012345, -2., 3.], [1e9 + .25, 4., 5.]]),
                         [[.1, .2, .3], [.2, .4, .6]],
                         [[2., 0., 0., 0.], [0., 1., 2., 3.]],
                         [.25, .75], np.arange(24).reshape(2, 3, 4) * .01, 'synthetic')


def write_ply(path, binary=False, *, roll_properties=False, overrides=None, rest_count=9):
    fields = [('x', 'double'), ('y', 'double'), ('z', 'double'), ('opacity', 'float')]
    fields += [(f'scale_{i}', 'float') for i in range(3)]
    fields += [(f'rot_{i}', 'float') for i in range(4)]
    fields += [(f'f_dc_{i}', 'float') for i in range(3)]
    fields += [(f'f_rest_{i}', 'float') for i in range(rest_count)]
    values = dict(x=6371000.012345, y=2., z=3., opacity=np.log(3.))
    values.update({f'scale_{i}': np.log(.1 * (i + 1)) for i in range(3)})
    values.update(rot_0=2., rot_1=0., rot_2=0., rot_3=0.)
    values.update({f'f_dc_{i}': i * .1 for i in range(3)})
    values.update({f'f_rest_{i}': i * .01 for i in range(rest_count)})
    values.update(overrides or {})
    if roll_properties:
        fields = fields[5:] + fields[:5]
    fmt = 'binary_little_endian' if binary else 'ascii'
    header = 'ply\nformat ' + fmt + ' 1.0\nelement vertex 1\n'
    header += ''.join(f'property {kind} {name}\n' for name, kind in fields) + 'end_header\n'
    with path.open('wb') as f:
        f.write(header.encode('ascii'))
        if binary:
            for name, kind in fields:
                f.write(struct.pack('<d' if kind == 'double' else '<f', values[name]))
        else:
            f.write((' '.join(str(values[name]) for name, _ in fields) + '\n').encode('ascii'))
    return fields


class GaussianAssetTests(unittest.TestCase):
    def test_arrays_are_owned_readonly_and_positions_preserve_double(self):
        positions = np.array([[1e9 + .012345, 0., 0.]])
        a = GaussianAsset(positions, [[1., 2., 3.]], [[1., 0., 0., 0.]], [.5], np.zeros((1, 3, 1)))
        positions[0, 0] = 0
        self.assertEqual(a.positions[0, 0], 1e9 + .012345)
        self.assertEqual(a.positions.dtype, np.float64)
        for array in (a.positions, a.scales, a.rotations_wxyz, a.opacities, a.sh):
            self.assertFalse(array.flags.writeable)
            with self.assertRaises(ValueError):
                array.flat[0] = 0

    def test_packed_layout_rebases_before_float_conversion(self):
        a = asset_fixture()
        p = a.packed([1e9, 0., 0.], 2.)
        self.assertEqual(p.shape, (2, 64))
        self.assertEqual(p.dtype, np.float32)
        np.testing.assert_allclose(p[:, :3], (a.positions - [1e9, 0., 0.]) / 2., rtol=1e-7)
        np.testing.assert_allclose(p[:, 4:7], a.scales / 2.)
        np.testing.assert_allclose(p[:, 8:12], a.rotations_wxyz)
        self.assertTrue((p[:, 7] == 1).all())
        for channel in range(3):
            np.testing.assert_array_equal(p[:, 12 + channel * 16:16 + channel * 16], a.sh[:, channel])
        self.assertTrue((p[:, 60:] == 0).all())
        self.assertGreater(p[0, 0], 0)  # Would vanish if global XYZ were converted first.

    def test_normalization_and_metadata(self):
        a = asset_fixture()
        np.testing.assert_allclose(np.linalg.norm(a.rotations_wxyz, axis=1), 1., atol=1e-7)
        self.assertEqual(a.count, 2)
        self.assertEqual(a.degree, 1)
        self.assertEqual(a.nbytes, sum(x.nbytes for x in (a.positions, a.scales, a.rotations_wxyz, a.opacities, a.sh)))
        center, diameter = a.bounds()
        np.testing.assert_allclose(center, a.positions.mean(0))
        self.assertAlmostEqual(diameter, float(np.linalg.norm(a.positions[1] - a.positions[0])))
        points, rgb = a.preview(1)
        np.testing.assert_array_equal(points, a.positions[:1])
        np.testing.assert_array_equal(rgb, np.rint(np.clip(.5 + SH_C0 * a.sh[:1, :, 0], 0, 1) * 255).astype(np.uint8))

    def test_invalid_parameters_fail(self):
        base = dict(positions=[[0., 0., 0.]], scales=[[1., 1., 1.]],
                    rotations_wxyz=[[1., 0., 0., 0.]], opacities=[.5], sh=np.zeros((1, 3, 1)))
        invalid = [('positions', [[np.nan, 0., 0.]]), ('scales', [[0., 1., 1.]]),
                   ('scales', [[np.inf, 1., 1.]]), ('rotations_wxyz', [[0., 0., 0., 0.]]),
                   ('rotations_wxyz', [[np.nan, 0., 0., 0.]]), ('opacities', [1.1]),
                   ('sh', np.zeros((1, 3, 25))), ('sh', np.full((1, 3, 1), np.inf))]
        for key, value in invalid:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                GaussianAsset(**dict(base, **{key: value}))
        a = GaussianAsset(**base)
        for scale in (0, -1, np.nan):
            with self.assertRaises(ValueError):
                a.packed(world_scale=scale)
        with self.assertRaises(ValueError):
            a.packed(origin=[np.inf, 0, 0])


class GaussianPlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_ascii_binary_full_attributes_and_sh_layout(self):
        ascii_path, binary_path = self.root / 'a.ply', self.root / 'b.ply'
        write_ply(ascii_path)
        write_ply(binary_path, binary=True, roll_properties=True)
        self.assertTrue(is_gaussian_ply(ascii_path))
        a, b = load_gaussian_ply(ascii_path), load_gaussian_ply(binary_path)
        for field in ('positions', 'scales', 'rotations_wxyz', 'opacities', 'sh'):
            np.testing.assert_array_equal(getattr(a, field), getattr(b, field))
        self.assertEqual(a.positions[0, 0], 6371000.012345)
        np.testing.assert_allclose(a.scales, [[.1, .2, .3]], rtol=1e-6)
        np.testing.assert_allclose(a.rotations_wxyz, [[1., 0., 0., 0.]])
        np.testing.assert_allclose(a.opacities, [.75])
        np.testing.assert_allclose(a.sh[0, :, 0], [0, .1, .2])
        np.testing.assert_allclose(a.sh[0, :, 1:], np.arange(9).reshape(3, 3) * .01)

    def test_all_supported_sh_degrees(self):
        p = self.root / 'degrees.ply'
        for degree, rest in enumerate((0, 9, 24, 45)):
            write_ply(p, rest_count=rest)
            a = load_gaussian_ply(p)
            self.assertEqual(a.degree, degree)
            self.assertEqual(a.sh.shape, (1, 3, (degree + 1) ** 2))
        write_ply(p, rest_count=72)
        with self.assertRaisesRegex(ValueError, 'degree 0 through 3'):
            load_gaussian_ply(p)

    def test_ordinary_and_partial_gaussian_detection(self):
        p = self.root / 'plain.ply'
        p.write_text('ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float y\nproperty float z\nend_header\n1 2 3\n')
        self.assertFalse(is_gaussian_ply(p))
        self.assertIsNone(load_gaussian_ply(p))
        p.write_text(p.read_text().replace('end_header', 'property float opacity\nend_header').replace('1 2 3', '1 2 3 0'))
        self.assertFalse(is_gaussian_ply(p))
        self.assertIsNone(load_gaussian_ply(p))
        p.write_text(p.read_text().replace('property float opacity', 'property float f_dc_0'))
        self.assertTrue(is_gaussian_ply(p))
        with self.assertRaisesRegex(ValueError, 'Incomplete Gaussian'):
            load_gaussian_ply(p)

    def test_nonfinite_zero_quaternion_and_scale_fail(self):
        p = self.root / 'bad.ply'
        for override in ({'rot_0': 0.}, {'scale_1': -1000.}, {'opacity': np.inf}, {'x': np.nan}, {'f_rest_8': np.nan}):
            write_ply(p, overrides=override)
            with self.subTest(override=override), self.assertRaises(ValueError):
                load_gaussian_ply(p)

    def test_truncation_counts_memory_budget_and_property_sequence(self):
        p = self.root / 'bad.ply'
        write_ply(p, binary=True)
        raw = p.read_bytes()
        p.write_bytes(raw[:-1])
        with self.assertRaisesRegex(ValueError, 'Truncated binary'):
            load_gaussian_ply(p)
        p.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'count'):
            load_gaussian_ply(p, max_splats=0)
        with self.assertRaisesRegex(ValueError, 'memory budget'):
            load_gaussian_ply(p, max_bytes=8)
        p.write_bytes(raw.replace(b'element vertex 1', b'element vertex 999999999999999999999'))
        with self.assertRaisesRegex(ValueError, 'count'):
            load_gaussian_ply(p)
        write_ply(p)
        p.write_text(p.read_text().replace('f_rest_8', 'f_rest_9'))
        with self.assertRaisesRegex(ValueError, 'contiguous'):
            load_gaussian_ply(p)

    def test_malformed_bounded_headers(self):
        p = self.root / 'header.ply'
        bad_headers = [b'ply\nformat ascii 1.0\nelement vertex -1\nend_header\n',
                       b'ply\nformat ascii 1.0\nformat ascii 1.0\n',
                       b'ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nproperty float x\nend_header\n',
                       b'ply\ncomment ' + b'x' * 65536 + b'\nend_header\n']
        for content in bad_headers:
            p.write_bytes(content)
            with self.subTest(content=content[:100]), self.assertRaises(ValueError):
                load_gaussian_ply(p)


if __name__ == '__main__':
    unittest.main()

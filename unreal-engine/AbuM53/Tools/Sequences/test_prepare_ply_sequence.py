"""Bounded fixtures verify ordering, preservation and unsafe-input rejection."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

from prepare_ply_sequence import inspect_ply, prepare


PROPERTIES = ["x", "y", "z", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
              "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]


def write_ply(path, x=1.0, endian="little"):
    header = ("ply\nformat binary_" + endian + "_endian 1.0\nelement vertex 2\n" +
              "".join("property float " + name + "\n" for name in PROPERTIES) + "end_header\n")
    row = [x, 2, 3, .1, .2, .3, 1, -2, -2, -2, 1, 0, 0, 0]
    path.write_bytes(header.encode("ascii") + struct.pack(("<" if endian == "little" else ">") + "28f", *(row + row)))


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        write_ply(self.source / "frame_10.ply", 10)
        write_ply(self.source / "frame_2.ply", 2)

    def tearDown(self):
        self.temp.cleanup()

    def test_natural_order_timing_and_lossless_copy(self):
        report = prepare(self.source, self.root / "result", 30)
        manifest = json.loads(Path(report["manifest"]).read_text())
        self.assertEqual([f["file"] for f in manifest["frames"]], ["frames/frame_2.ply", "frames/frame_10.ply"])
        self.assertEqual(manifest["frames"][1]["time_seconds"], 1 / 30)
        self.assertFalse(manifest["stable_ids"])
        self.assertEqual(report["total_decoded_point_bytes"], 4 * 256)
        for frame in report["frames"]:
            self.assertEqual(Path(frame["source_path"]).read_bytes(), Path(frame["prepared_path"]).read_bytes())
            self.assertFalse(frame["same_file_as_source"])

    def test_hardlinks_are_explicit_and_reported(self):
        report = prepare(self.source, self.root / "result", 24, hardlink=True)
        for frame in report["frames"]:
            self.assertIn(frame["prepared_storage"], ("hardlink", "copy"))
            if frame["prepared_storage"] == "hardlink":
                self.assertTrue(frame["same_file_as_source"])

    def test_big_endian_sampling(self):
        write_ply(self.source / "big.ply", 8, "big")
        record, positions = inspect_ply(self.source / "big.ply", samples=2)
        self.assertEqual(record["sh_degree"], 0)
        self.assertEqual(positions[0], [8, 2, 3])

    def test_truncated_payload_rejected_before_output(self):
        path = self.source / "frame_2.ply"
        path.write_bytes(path.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "payload size mismatch"):
            prepare(self.source, self.root / "result", 30)
        self.assertFalse((self.root / "result").exists())

    def test_existing_output_and_source_output_rejected(self):
        output = self.root / "result"
        output.mkdir()
        (output / "keep.txt").write_text("preserve")
        with self.assertRaises(ValueError):
            prepare(self.source, output, 30)
        with self.assertRaises(ValueError):
            prepare(self.source, self.source / "nested", 30)
        self.assertEqual((output / "keep.txt").read_text(), "preserve")

    def test_private_data_cannot_be_prepared_inside_git(self):
        repo = self.root / "repo"
        (repo / ".git").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "outside Git"):
            prepare(self.source, repo / "result", 30)

    def test_nonfinite_sample_and_bad_fps_rejected(self):
        write_ply(self.source / "frame_2.ply", float("nan"))
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            prepare(self.source, self.root / "result", 30)
        with self.assertRaisesRegex(ValueError, "fps"):
            prepare(self.source, self.root / "result", float("inf"))


if __name__ == "__main__":
    unittest.main()

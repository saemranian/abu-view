"""Original synthetic SPZ fixtures, no captures or upstream models.
Zstd uses valid single-segment RAW blocks so generation needs only Python stdlib.
The production decoder is the complete audited Zstd decompressor.
"""
from pathlib import Path
import gzip
import struct
import argparse

DEST = Path(__file__).parent / "fixtures"
DEST.mkdir(exist_ok=True)

def zstd_raw(payload):
    assert len(payload) < 256
    return b"\x28\xb5\x2f\xfd\x20" + bytes([len(payload)]) + ((len(payload) << 3) | 1).to_bytes(3, "little") + payload

def attributes(version, degree):
    positions = (1.25, -2.5, 5.0)
    packed_pos = struct.pack("<3e", *positions) if version == 1 else b"".join((round(v * 4096) & 0xffffff).to_bytes(3,"little") for v in positions)
    rotation = struct.pack("<I", 3 << 30) if version >= 3 else bytes([128,128,128])
    sh = bytearray([128] * (3 * ((degree + 1) ** 2 - 1)))
    if sh:
        sh[0], sh[-1] = 144, 112
    return [packed_pos, bytes([192]), bytes([128,160,96]), bytes([128,144,160]), rotation, bytes(sh)]

for version in range(1,5):
    for degree in (0,3):
        streams = attributes(version, degree)
        if version < 4:
            header = struct.pack("<IIIBBBB", 0x5053474e, version, 1, degree, 12, 1, 0)
            blob = gzip.compress(header + b"".join(streams), mtime=0)
        else:
            nonempty = [s for s in streams if s]
            compressed = [zstd_raw(s) for s in nonempty]
            header = struct.pack("<IIIBBBBI12x", 0x5053474e, version, 1, degree, 12, 1, len(nonempty), 32)
            blob = header + b"".join(struct.pack("<QQ",len(c),len(s)) for s,c in zip(nonempty,compressed)) + b"".join(compressed)
        (DEST/f"spz_v{version}_sh{degree}.spz").write_bytes(blob)

v4 = bytearray((DEST/"spz_v4_sh3.spz").read_bytes())
v4[14] |= 2
(DEST/"spz_extensions_rejected.spz").write_bytes(v4)
v4 = bytearray((DEST/"spz_v4_sh3.spz").read_bytes())
v4[40] += 1
(DEST/"spz_bad_toc.spz").write_bytes(v4)
(DEST/"spz_gzip_bomb.spz").write_bytes(gzip.compress(b"X"*100000,mtime=0))
print("Generated 11 synthetic SPZ fixtures")

parser = argparse.ArgumentParser()
parser.add_argument("--zstd-library", help="Optional installed native Zstd library, used only to generate a compressed-block test")
args = parser.parse_args()
if args.zstd_library:
    import ctypes
    lib = ctypes.CDLL(args.zstd_library)
    lib.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
    lib.ZSTD_compressBound.restype = ctypes.c_size_t
    lib.ZSTD_compress.argtypes = [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int]
    lib.ZSTD_compress.restype = ctypes.c_size_t
    lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
    lib.ZSTD_isError.restype = ctypes.c_uint
    lib.ZSTD_versionNumber.restype = ctypes.c_uint
    streams = [s * 64 for s in attributes(4,3)]
    compressed = []
    for stream in streams:
        bound = lib.ZSTD_compressBound(len(stream))
        dst = ctypes.create_string_buffer(bound)
        src = ctypes.create_string_buffer(stream)
        size = lib.ZSTD_compress(dst,bound,src,len(stream),3)
        assert not lib.ZSTD_isError(size)
        compressed.append(dst.raw[:size])
    header = struct.pack("<IIIBBBBI12x",0x5053474e,4,64,3,12,1,6,32)
    blob = header + b"".join(struct.pack("<QQ",len(c),len(s)) for s,c in zip(streams,compressed)) + b"".join(compressed)
    (DEST/"spz_v4_compressed.spz").write_bytes(blob)
    print(f"Generated compressed-block SPZ fixture using Zstd {lib.ZSTD_versionNumber()}")

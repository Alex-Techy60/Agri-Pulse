"""Minimal TIFF reader for the tiny rasters a WCS point query returns (a few pixels around the farm).

Why not a library: the project has no imaging or GDAL dependency, and a point query returns a few hundred bytes. Supported: tiled or
striped, 8/16/32-bit integer or 32-bit float samples, one band, no compression or zlib (Deflate), predictor 1 or 2. Anything else
raises TiffError, which the caller reports as an unusable response; it never guesses a value.
"""
from __future__ import annotations

import struct
import zlib


class TiffError(ValueError):
    pass


_SIZES = {1: 1, 3: 2, 4: 4, 5: 8, 12: 8}
_FMT = {1: "B", 3: "H", 4: "I", 12: "d"}


def _entries(b: bytes, bo: str) -> dict[int, list]:
    (first,) = struct.unpack(bo + "I", b[4:8])
    (n,) = struct.unpack(bo + "H", b[first:first + 2])
    out: dict[int, list] = {}
    for i in range(n):
        tag, typ, cnt, val = struct.unpack(bo + "HHII", b[first + 2 + i * 12:first + 14 + i * 12])
        size = _SIZES.get(typ)
        if size is None or typ not in _FMT:
            continue  # rationals and strings are not needed
        raw = b[first + 10 + i * 12:first + 14 + i * 12] if cnt * size <= 4 else b[val:val + cnt * size]
        out[tag] = list(struct.unpack(bo + _FMT[typ] * cnt, raw[:cnt * size]))
    return out


def read_tiff(b: bytes) -> list[list[float]]:
    """-> rows of sample values (row 0 first). Raises TiffError for anything outside the supported subset."""
    if b[:2] not in (b"II", b"MM") or len(b) < 8:
        raise TiffError("not a TIFF")
    bo = "<" if b[:2] == b"II" else ">"
    try:
        t = _entries(b, bo)
        width, height, bits = t[256][0], t[257][0], t[258][0]
        comp, predictor, fmt = t.get(259, [1])[0], t.get(317, [1])[0], t.get(339, [1])[0]
        if t.get(277, [1])[0] != 1 or comp not in (1, 8, 32946) or predictor not in (1, 2) or bits not in (8, 16, 32):
            raise TiffError("unsupported TIFF layout")
        code = {(8, 1): "B", (16, 1): "H", (16, 2): "h", (32, 1): "I", (32, 2): "i", (32, 3): "f"}.get((bits, fmt))
        if code is None:
            raise TiffError("unsupported sample type")
        bps = bits // 8
        tiled = 324 in t
        if tiled:
            tw, th, offs, counts = t[322][0], t[323][0], t[324], t[325]
            across = -(-width // tw)
        else:
            tw, th, offs, counts = width, t.get(278, [height])[0], t[273], t[279]
            across = 1
        grid = [[0.0] * width for _ in range(height)]
        for idx, (off, cnt) in enumerate(zip(offs, counts)):
            raw = b[off:off + cnt]
            data = zlib.decompress(raw) if comp in (8, 32946) else raw
            rows_in_tile = th
            samples = struct.unpack(bo + code * (len(data) // bps), data[: (len(data) // bps) * bps])
            row_len = tw
            x0, y0 = ((idx % across) * tw, (idx // across) * th) if tiled else (0, idx * th)
            for r in range(rows_in_tile):
                line = list(samples[r * row_len:(r + 1) * row_len])
                if len(line) < row_len:
                    break
                if predictor == 2:  # horizontal differencing: each sample is the difference to its left neighbour
                    mask = (1 << bits) - 1
                    for c in range(1, row_len):
                        s = line[c - 1] + line[c]
                        line[c] = ((s + (1 << (bits - 1))) & mask) - (1 << (bits - 1)) if code in "hi" else (s & mask if code in "BHI" else s)
                y = y0 + r
                if y >= height:
                    break
                for c in range(min(row_len, width - x0)):
                    grid[y][x0 + c] = line[c]
        return grid
    except (KeyError, IndexError, struct.error, zlib.error) as e:
        raise TiffError(f"unreadable TIFF: {type(e).__name__}") from e

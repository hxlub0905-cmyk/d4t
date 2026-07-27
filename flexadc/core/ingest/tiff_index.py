# Vendored into FlexADC on 2026-07-27.
# Source project: KLIP — file: klarf_tif_probe.py (dependency-free TIFF IFD
# walker; only the pure-struct structural reader is vendored, not the CLI /
# probe / report code).
# Adaptations:
#   - added `from __future__ import annotations` (FlexADC convention)
#   - extracted read_tiff_pages() + helpers (TYPE_SIZE / COMPRESSION /
#     PHOTOMETRIC / TAGS / _read_values / _page_geom) verbatim
#   - added n_pages(path) built on read_tiff_pages (still dependency-free)
#   - added read_page(path, page_index) -> np.ndarray via LAZY
#     `import tifffile` inside the function (pixel decode only there)
#   - Chinese comments kept verbatim.
"""TIFF 結構索引：只讀 IFD（不解碼像素），純標準函式庫。

支援 classic TIFF 與 BigTIFF、兩種 byte order。像素解碼（read_page）
另以 lazy import 的 tifffile 完成。
"""
from __future__ import annotations

import os
import struct


# ---------------------------------------------------------------- TIFF 走訪
# 只讀 IFD 結構（不解碼像素），純標準函式庫。支援 classic TIFF 與 BigTIFF、
# 兩種 byte order。

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4,
             10: 8, 11: 4, 12: 8, 13: 4, 16: 8, 17: 8, 18: 8}

COMPRESSION = {1: "none", 2: "CCITT-RLE", 3: "CCITT-G3", 4: "CCITT-G4",
               5: "LZW", 6: "old-JPEG", 7: "JPEG", 8: "deflate",
               32773: "PackBits", 32946: "deflate"}

PHOTOMETRIC = {0: "white-is-zero", 1: "black-is-zero", 2: "RGB",
               3: "palette", 4: "mask", 5: "CMYK", 6: "YCbCr"}

TAGS = {254: "subfile", 256: "width", 257: "height", 258: "bits",
        259: "compression", 262: "photometric", 270: "description",
        273: "strip_offsets", 277: "spp", 279: "strip_bytes",
        297: "page_number", 305: "software", 306: "datetime",
        322: "tile_w", 323: "tile_h", 324: "tile_offsets", 325: "tile_bytes"}


def _read_values(f, en, vtype, count, raw, big):
    """把 IFD entry 的 value/offset 解成 python 值 list。"""
    size = TYPE_SIZE.get(vtype)
    if size is None:
        return None
    total = size * count
    inline = 8 if big else 4
    if total <= inline:
        data = raw[:total]
    else:
        off = struct.unpack(en + ('Q' if big else 'I'), raw)[0]
        pos = f.tell()
        f.seek(off)
        data = f.read(total)
        f.seek(pos)
        if len(data) < total:
            return None
    if vtype == 2:                        # ASCII
        return [data.split(b'\x00')[0].decode('latin-1', 'replace')]
    fmt = {1: 'B', 3: 'H', 4: 'I', 6: 'b', 7: 'B', 8: 'h', 9: 'i',
           11: 'f', 12: 'd', 13: 'I', 16: 'Q', 17: 'q'}.get(vtype)
    if fmt is None:
        if vtype in (5, 10):              # rational
            f2 = 'I' if vtype == 5 else 'i'
            vals = struct.unpack(en + f2 * (count * 2), data)
            return [vals[i] / vals[i + 1] if vals[i + 1] else 0.0
                    for i in range(0, count * 2, 2)]
        return None
    return list(struct.unpack(en + fmt * count, data))


def read_tiff_pages(path):
    """回傳 (pages, info)。pages = [dict,...]（每頁一筆），info = 檔案層資訊。"""
    pages = []
    with open(path, 'rb') as f:
        head = f.read(8)
        if len(head) < 8:
            raise ValueError("File too short to be a TIFF.")
        if head[:2] == b'II':
            en = '<'
        elif head[:2] == b'MM':
            en = '>'
        else:
            raise ValueError("Not a TIFF (missing II/MM byte-order mark).")
        magic = struct.unpack(en + 'H', head[2:4])[0]
        big = (magic == 43)
        if magic == 42:
            next_ifd = struct.unpack(en + 'I', head[4:8])[0]
        elif big:
            off_size, zero = struct.unpack(en + 'HH', head[4:8])
            if off_size != 8 or zero != 0:
                raise ValueError("Malformed BigTIFF header.")
            next_ifd = struct.unpack(en + 'Q', f.read(8))[0]
        else:
            raise ValueError(f"Unknown TIFF magic {magic} (expected 42 or 43).")

        seen = set()
        while next_ifd:
            if next_ifd in seen or len(pages) > 100000:
                raise ValueError("IFD chain loops — corrupt TIFF.")
            seen.add(next_ifd)
            f.seek(next_ifd)
            n = struct.unpack(en + ('Q' if big else 'H'),
                              f.read(8 if big else 2))[0]
            page = {"index": len(pages), "ifd_offset": next_ifd}
            esize = 20 if big else 12
            entries = f.read(esize * n)
            for k in range(n):
                e = entries[k * esize:(k + 1) * esize]
                tag, vtype = struct.unpack(en + 'HH', e[:4])
                if big:
                    count = struct.unpack(en + 'Q', e[4:12])[0]
                    raw = e[12:20]
                else:
                    count = struct.unpack(en + 'I', e[4:8])[0]
                    raw = e[8:12]
                name = TAGS.get(tag)
                if name is None:
                    continue
                vals = _read_values(f, en, vtype, count, raw, big)
                if vals is None:
                    continue
                page[name] = vals[0] if len(vals) == 1 else vals
            b = page.get("strip_bytes", page.get("tile_bytes", 0))
            page["data_bytes"] = sum(b) if isinstance(b, list) else b
            pages.append(page)
            next_ifd = struct.unpack(en + ('Q' if big else 'I'),
                                     f.read(8 if big else 4))[0]

    info = {"byte_order": "little-endian (II)" if en == '<' else "big-endian (MM)",
            "bigtiff": big, "n_pages": len(pages),
            "file_bytes": os.path.getsize(path)}
    return pages, info


def _page_geom(p):
    bits = p.get("bits", "?")
    if isinstance(bits, list):
        bits = "/".join(str(b) for b in bits)
    return (f'{p.get("width", "?")}x{p.get("height", "?")} '
            f'{bits}-bit {COMPRESSION.get(p.get("compression", 1), "compression?")} '
            f'{PHOTOMETRIC.get(p.get("photometric", -1), "")}'.strip())


# ------------------------------------------------------- FlexADC additions

def n_pages(path) -> int:
    """回傳多頁 TIFF 的頁數（純 IFD 走訪，不解碼像素、不需第三方套件）。"""
    _pages, info = read_tiff_pages(path)
    return info["n_pages"]


def read_page(path, page_index):
    """解碼並回傳第 page_index（0-based）頁的像素 (np.ndarray)。

    像素解碼交給 tifffile（lazy import：只有真的要讀像素才需要它）。
    """
    import tifffile  # lazy: pixel decode only; structural code above stays pure-stdlib
    with tifffile.TiffFile(path) as tf:
        if page_index < 0 or page_index >= len(tf.pages):
            raise IndexError(
                f"TIFF page {page_index} out of range (0..{len(tf.pages) - 1})")
        return tf.pages[page_index].asarray()

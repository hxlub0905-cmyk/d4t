#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADEPT 廠內探測腳本 #2：TIFF/BigTIFF 結構探測（單檔、純標準函式庫、不解碼像素）。

用途：在廠內真實 patch TIFF 上確認 docs/FAB-VALIDATION.md 的假設 ——
  假設 #1「每顆 defect 第 1 張 = test、第 2 張 = ref」（--with-klarf 交叉比對；本腳本最重要的輸出）
  假設 #2「nm_per_px 從哪來」（ImageDescription / Software / Resolution 標籤）

邏輯鏡射自 adept/core/ingest/tiff_index.py（read_tiff_pages / _read_values /
TYPE_SIZE / COMPRESSION / PHOTOMETRIC / TAGS）與 adept/core/ingest/klarf_core.py
（--with-klarf 需要的最小 KLARF 解析 + defect_image_map）。本檔重寫了這些邏輯，
不 import adept、不用第三方套件；那兩個模組改判定規則時，這裡要跟著改。

用法：
    python probe_tiff.py FILE.tif [--pages 8] [--with-klarf FILE.klarf] [--include-ids]

本腳本**不讀任何像素**，只讀 IFD 標籤。要看灰階統計請用 probe_stats.py。
"""

import argparse
import json
import os
import re
import struct
import sys

PROBE_VERSION = "1.0"
SCHEMA = "adept.fab_probe.tiff/1"

# ------------------------------------------------- TIFF 常數（鏡射 tiff_index）

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4,
             10: 8, 11: 4, 12: 8, 13: 4, 16: 8, 17: 8, 18: 8}

COMPRESSION = {1: "none", 2: "CCITT-RLE", 3: "CCITT-G3", 4: "CCITT-G4",
               5: "LZW", 6: "old-JPEG", 7: "JPEG", 8: "deflate",
               32773: "PackBits", 32946: "deflate"}

PHOTOMETRIC = {0: "white-is-zero", 1: "black-is-zero", 2: "RGB",
               3: "palette", 4: "mask", 5: "CMYK", 6: "YCbCr"}

RESUNIT = {1: "none", 2: "inch", 3: "cm"}

# tiff_index.TAGS 的超集：多讀幾個對「假設 #2」有用的標籤
TAGS = {254: "subfile", 256: "width", 257: "height", 258: "bits",
        259: "compression", 262: "photometric", 270: "description",
        271: "make", 272: "model", 273: "strip_offsets",
        277: "spp", 278: "rows_per_strip", 279: "strip_bytes",
        282: "xres", 283: "yres", 284: "planarconfig", 296: "res_unit",
        297: "page_number", 305: "software", 306: "datetime",
        317: "predictor", 322: "tile_w", 323: "tile_h", 324: "tile_offsets",
        325: "tile_bytes", 339: "sample_format", 65000: "vendor_65000"}

# tiff_index 目前有讀的標籤（用來標示「ADEPT 目前沒在看」的欄位）
TAGS_IN_ADEPT = {254, 256, 257, 258, 259, 262, 270, 273, 277, 279, 297,
                 305, 306, 322, 323, 324, 325}


class ProbeError(Exception):
    pass


def _out(line=""):
    print(line)


# ---------------------------------------------------------------- 遮蔽政策
#
# 預設：
#   * 檔名只印副檔名與字元數
#   * ImageDescription / Software / Make / Model / DateTime 這類自由文字：
#     截斷到 160 字元，並把「看起來像識別碼的字」換成 <id:長度>
#     —— 規則：由字母+數字混成、長度 >= 6 的字 → 遮蔽；
#              純數字（含小數、含 nm/um 之類短單位）→ 保留（假設 #2 要看數值）；
#              純字母（<= 24 字）→ 保留（PixelSize、Software 名稱等）
#   * 不輸出任何像素
# --include-ids：上述自由文字與檔名照原樣輸出。

_WORD = re.compile(r"[A-Za-z0-9_.\-]+")
_NUMLIKE = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?[A-Za-z%/]{0,4}$")


def redact_text(s, include_ids=False, limit=160):
    if s is None:
        return None
    s = str(s).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    if not include_ids:
        parts = re.split(r"([^A-Za-z0-9_.\-]+)", s)
        out = []
        for i, chunk in enumerate(parts):
            if i % 2 == 1 or not chunk:              # 分隔符原樣保留
                out.append(chunk)
                continue
            if _NUMLIKE.match(chunk):
                out.append(chunk)
                continue
            core = chunk.replace("_", "").replace(".", "").replace("-", "")
            has_a = any(c.isalpha() for c in core)
            has_d = any(c.isdigit() for c in core)
            if has_a and has_d and len(core) >= 6:
                out.append("<id:%d>" % len(chunk))
            elif has_a and not has_d and len(core) <= 24:
                out.append(chunk)
            elif len(chunk) >= 20:
                out.append("<id:%d>" % len(chunk))
            else:
                out.append(chunk)
        s = "".join(out)
    if len(s) > limit:
        s = s[:limit] + "...(截斷)"
    return s


def redact_name(path, include_ids=False):
    base = os.path.basename(str(path))
    if include_ids:
        return base
    stem, ext = os.path.splitext(base)
    return "<redacted, %d chars>%s" % (len(stem), ext)


def json_block(d):
    items = list(d.items())
    lines = ["{"]
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append("  %s: %s%s" % (json.dumps(k, ensure_ascii=False),
                                     json.dumps(v, ensure_ascii=False), comma))
    lines.append("}")
    return lines


def histogram_lines(counter, width=40):
    if not counter:
        return ["  （無資料）"]
    keys = sorted(counter.keys(), key=lambda k: (isinstance(k, str), k))
    mx = max(counter.values())
    lines = []
    for k in keys:
        n = counter[k]
        lines.append("  %-10s : %8d  %s"
                     % (str(k), n, "#" * max(1, int(round(width * n / float(mx))))))
    return lines


# ------------------------------------------------- IFD 走訪（鏡射 read_tiff_pages）

MAGIC_HINTS = [(b"\x89PNG\r\n\x1a\n", "PNG"), (b"\xff\xd8\xff", "JPEG"),
               (b"BM", "BMP"), (b"GIF8", "GIF"), (b"PK\x03\x04", "ZIP/壓縮檔"),
               (b"%PDF", "PDF")]


def _read_values(f, en, vtype, count, raw, big):
    size = TYPE_SIZE.get(vtype)
    if size is None:
        return None
    total = size * count
    inline = 8 if big else 4
    if total <= inline:
        data = raw[:total]
    else:
        off = struct.unpack(en + ("Q" if big else "I"), raw)[0]
        pos = f.tell()
        f.seek(off)
        data = f.read(total)
        f.seek(pos)
        if len(data) < total:
            return None
    if vtype == 2:
        return [data.split(b"\x00")[0].decode("latin-1", "replace")]
    fmt = {1: "B", 3: "H", 4: "I", 6: "b", 7: "B", 8: "h", 9: "i",
           11: "f", 12: "d", 13: "I", 16: "Q", 17: "q"}.get(vtype)
    if fmt is None:
        if vtype in (5, 10):
            f2 = "I" if vtype == 5 else "i"
            vals = struct.unpack(en + f2 * (count * 2), data)
            return [vals[i] / vals[i + 1] if vals[i + 1] else 0.0
                    for i in range(0, count * 2, 2)]
        return None
    return list(struct.unpack(en + fmt * count, data))


def read_tiff_pages(path, max_pages=200000):
    """回傳 (pages, info)。鏡射 tiff_index.read_tiff_pages，錯誤訊息改成中文。"""
    if not os.path.isfile(path):
        raise ProbeError("找不到檔案：%s" % path)
    if os.path.getsize(path) < 8:
        raise ProbeError("檔案太小（%d bytes），不可能是 TIFF。" % os.path.getsize(path))
    pages = []
    unknown_tags = {}
    with open(path, "rb") as f:
        head = f.read(8)
        if head[:2] == b"II":
            en = "<"
        elif head[:2] == b"MM":
            en = ">"
        else:
            hint = ""
            for sig, name in MAGIC_HINTS:
                if head.startswith(sig):
                    hint = "（看起來是 %s）" % name
                    break
            raise ProbeError(
                "這個檔不是 TIFF/BigTIFF：開頭不是 II 或 MM 位元組序標記%s。" % hint)
        magic = struct.unpack(en + "H", head[2:4])[0]
        big = (magic == 43)
        if magic == 42:
            next_ifd = struct.unpack(en + "I", head[4:8])[0]
        elif big:
            off_size, zero = struct.unpack(en + "HH", head[4:8])
            if off_size != 8 or zero != 0:
                raise ProbeError("BigTIFF 檔頭損毀（offset size=%d）。" % off_size)
            next_ifd = struct.unpack(en + "Q", f.read(8))[0]
        else:
            raise ProbeError("不認得的 TIFF magic %d（應為 42 或 43）。" % magic)

        seen = set()
        while next_ifd:
            if next_ifd in seen:
                raise ProbeError("IFD 串鏈成環（第 %d 頁）—— TIFF 檔損毀。" % len(pages))
            if len(pages) >= max_pages:
                break
            seen.add(next_ifd)
            f.seek(next_ifd)
            nb = f.read(8 if big else 2)
            if len(nb) < (8 if big else 2):
                raise ProbeError("讀 IFD 表頭時檔案就結束了（第 %d 頁）。" % len(pages))
            n = struct.unpack(en + ("Q" if big else "H"), nb)[0]
            page = {"index": len(pages), "ifd_offset": next_ifd}
            esize = 20 if big else 12
            entries = f.read(esize * n)
            for k in range(n):
                e = entries[k * esize:(k + 1) * esize]
                if len(e) < esize:
                    break
                tag, vtype = struct.unpack(en + "HH", e[:4])
                if big:
                    count = struct.unpack(en + "Q", e[4:12])[0]
                    raw = e[12:20]
                else:
                    count = struct.unpack(en + "I", e[4:8])[0]
                    raw = e[8:12]
                name = TAGS.get(tag)
                if name is None:
                    unknown_tags[tag] = unknown_tags.get(tag, 0) + 1
                    continue
                vals = _read_values(f, en, vtype, count, raw, big)
                if vals is None:
                    continue
                page[name] = vals[0] if len(vals) == 1 else vals
            b = page.get("strip_bytes", page.get("tile_bytes", 0))
            page["data_bytes"] = sum(b) if isinstance(b, list) else b
            pages.append(page)
            nb = f.read(8 if big else 4)
            if len(nb) < (8 if big else 4):
                break
            next_ifd = struct.unpack(en + ("Q" if big else "I"), nb)[0]

    if not pages:
        raise ProbeError("這個 TIFF 一頁都沒有（IFD 串鏈是空的）。")
    info = {"byte_order": "little-endian (II)" if en == "<" else "big-endian (MM)",
            "endian": en, "bigtiff": big, "n_pages": len(pages),
            "file_bytes": os.path.getsize(path), "unknown_tags": unknown_tags}
    return pages, info


def page_sig(p):
    bits = p.get("bits", "?")
    if isinstance(bits, list):
        bits = "/".join(str(b) for b in bits)
    return "%sx%s %s-bit spp=%s %s %s %s" % (
        p.get("width", "?"), p.get("height", "?"), bits, p.get("spp", 1),
        COMPRESSION.get(p.get("compression", 1), "compression?%s" % p.get("compression")),
        PHOTOMETRIC.get(p.get("photometric", -1), "photometric?"),
        "tile" if "tile_w" in p else "strip")


def select_pages(n, first):
    """要細看哪幾頁：前 first 頁 + 中段取樣 + 最後兩頁。"""
    idx = set(range(min(first, n)))
    if n > first:
        mid = n // 2
        for i in (mid - 1, mid, mid + 1):
            if 0 <= i < n:
                idx.add(i)
        idx.add(n - 2)
        idx.add(n - 1)
    return sorted(i for i in idx if 0 <= i < n)


# ------------------------------- 最小 KLARF 解析（鏡射 klarf_core，僅 --with-klarf 用）

def _find_matching_brace(text, open_idx):
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def klarf_detect_version(text):
    if re.search(r"Record\s+FileRecord", text):
        return "1.8"
    m = re.search(r"FileVersion\s+(\d+)\s+(\d+)", text)
    if m:
        return "%s.%s" % (m.group(1), m.group(2))
    if re.search(r"\bList\s+\w+\s*\{", text):
        return "1.8"
    return "1.2"


def klarf_parse(path):
    """回傳 {version, columns, rows, imagelist_col18, tiff_file_name, tiff_spec}。"""
    if not os.path.isfile(path):
        raise ProbeError("找不到 KLARF：%s" % path)
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", "replace")
    d = {"version": klarf_detect_version(text), "columns": [], "rows": [],
         "imagelist_col18": None, "tiff_file_name": None, "tiff_spec": None}
    if d["version"] == "1.8":
        dls = list(re.finditer(r"List\s+DefectList\s*\{", text))
        if dls:
            b0 = text.index("{", dls[0].start())
            b1 = _find_matching_brace(text, b0)
            block = text[b0:b1 + 1]
            cm = re.search(r"Columns\s+\d+\s*\{([^}]*)\}", block)
            if cm:
                cols = []
                for c in cm.group(1).split(","):
                    parts = c.strip().split()
                    if not parts:
                        continue
                    cols.append(parts[-1])
                    if len(parts) >= 2 and parts[0].lower() == "imagelist":
                        d["imagelist_col18"] = len(cols) - 1
                d["columns"] = cols
            dm = re.search(r"Data\s+\d+\s*\{", block)
            if dm:
                db0 = block.index("{", dm.start())
                db1 = _find_matching_brace(block, db0)
                for row in block[db0 + 1:db1].split(";"):
                    row = row.strip()
                    if row:
                        d["rows"].append(re.findall(r'[^"\s]+|"[^"]*"', row))
        m = re.search(r'Field\s+TiffFileName\s+\d+\s*\{([^}]*)\}', text)
        if m:
            q = re.findall(r'"([^"]*)"', m.group(1))
            d["tiff_file_name"] = q[0] if q else m.group(1).strip()
        m = re.search(r'Field\s+TiffSpec\s+\d+\s*\{([^}]*)\}', text)
        if m:
            vals = re.findall(r'"([^"]*)"', m.group(1))
            if vals:
                d["tiff_spec"] = {"version": vals[0], "nfields": None,
                                  "fields": vals[1:]}
    else:
        m = re.search(r"DefectRecordSpec\s+\d+\s+([^;]+);", text)
        if m:
            d["columns"] = m.group(1).split()
        m = re.search(r"(?m)^[ \t]*DefectList\b[ \t]*\r?\n([\s\S]*?);", text)
        if m:
            for line in m.group(1).splitlines():
                line = line.strip()
                if line and not line.startswith(";"):
                    d["rows"].append(line.split())
        m = re.search(r"(?m)^[ \t]*TiffFileName\b[ \t]+([^;]*);", text)
        if m:
            d["tiff_file_name"] = m.group(1).strip().strip('"')
        m = re.search(r"(?m)^[ \t]*TiffSpec\b[ \t]+([\d.]+)[ \t]+(\d+)[ \t]*([^;]*);", text)
        if m:
            fields = re.findall(r'"([^"]*)"', m.group(3)) or m.group(3).split()
            n = int(m.group(2))
            if fields and len(fields) != n:
                n = len(fields)
            if n > 0:
                d["tiff_spec"] = {"version": m.group(1), "nfields": n, "fields": fields}
    return d


def _col_index(columns, name):
    up = [c.upper() for c in columns]
    return up.index(name.upper()) if name.upper() in up else -1


def _image_cols(d):
    il = _col_index(d["columns"], "IMAGELIST")
    if il < 0 and d["imagelist_col18"] is not None:
        il = d["imagelist_col18"]
    return _col_index(d["columns"], "IMAGECOUNT"), il


def _img_count(row, ic):
    if ic < 0 or ic >= len(row):
        return 0
    try:
        return max(0, int(row[ic]))
    except ValueError:
        return 0


def _layout(d, ic, il):
    """鏡射 klarf_core.image_layout 的三種變體判定（簡化版）。"""
    if ic < 0:
        return None
    s = il if il >= 0 else ic + 1
    for r in d["rows"]:
        if _img_count(r, ic) > 0:
            if s < len(r) and r[s] == "Images":
                return (s, None, "images18")
            break
    if il >= 0 and d["tiff_spec"] and d["tiff_spec"].get("nfields"):
        return (il, d["tiff_spec"]["nfields"], "declared")
    n = len(d["columns"])
    starts = []
    for cand in ([il] if il >= 0 else []) + [n] + ([n - 1] if ic == n - 2 else []):
        if cand not in starts:
            starts.append(cand)
    best = None
    for st in starts:
        tally, total = {}, 0
        for r in d["rows"]:
            cnt = _img_count(r, ic)
            if cnt <= 0:
                continue
            total += 1
            extra = len(r) - st
            if extra > 0 and extra % cnt == 0:
                tally[extra // cnt] = tally.get(extra // cnt, 0) + 1
        if not tally:
            continue
        nf, votes = max(tally.items(), key=lambda kv: kv[1])
        if nf >= 1 and votes >= total - max(1, total // 10) and best is None:
            best = (st, nf, "inferred")
    return best


def _entries(row, layout, ic):
    cnt = _img_count(row, ic)
    if cnt <= 0 or layout is None:
        return []
    s, nf, how = layout
    if how == "images18":
        m = re.match(r"Images\s+\d+\s*\{(.*)\}\s*$", " ".join(row[s:]))
        if not m:
            return []
        e = [x.split() for x in m.group(1).split(",") if x.strip()]
        return e if len(e) == cnt else []
    toks = row[s:]
    if len(toks) < cnt * nf:
        return []
    return [toks[k * nf:(k + 1) * nf] for k in range(cnt)]


def defect_image_map(d, n_pages):
    """鏡射 klarf_core.defect_image_map。回傳 {mode, base, pages, notes}。"""
    notes = []
    ic, il = _image_cols(d)
    if ic < 0:
        return {"mode": None, "base": None, "pages": [[] for _ in d["rows"]],
                "notes": ["沒有 IMAGECOUNT 欄 → 這份 KLARF 不帶 patch 對應資訊。"]}
    counts = [_img_count(r, ic) for r in d["rows"]]
    total = sum(counts)
    if total == 0:
        return {"mode": None, "base": None, "pages": [[] for _ in d["rows"]],
                "notes": ["每一列的 IMAGECOUNT 都是 0。"]}
    layout = _layout(d, ic, il)
    ids_per_row, usable = [], (layout is not None)
    if usable:
        for r, cnt in zip(d["rows"], counts):
            ents = _entries(r, layout, ic)
            if len(ents) != cnt or not all(e and e[0].lstrip("-").isdigit() for e in ents):
                usable = False
                notes.append("影像條目的第一個欄位不是整數頁碼（可能是檔名或解不出條目）"
                             "→ 改用出現順序連續配頁。")
                break
            ids_per_row.append([int(e[0]) for e in ents])
    if usable and layout and layout[2] == "images18" and all(
            ids == list(range(1, len(ids) + 1)) for ids in ids_per_row):
        usable = False
        notes.append("ImageList 的 id 是「defect 內的第幾張」（1..IMAGECOUNT），"
                     "不是全域 page 編號 → 改用出現順序連續配頁。")
    flat = [i for ids in ids_per_row for i in ids]
    if usable and len(set(flat)) != len(flat):
        usable = False
        notes.append("IMAGELIST 的 id 有重複 → 改用出現順序連續配頁。")
    base = None
    if usable:
        lo, hi = min(flat), max(flat)
        if lo >= 1 and hi <= n_pages:
            base = 1
        elif lo >= 0 and hi <= n_pages - 1:
            base = 0
        else:
            usable = False
            notes.append("IMAGELIST 的 id 範圍 [%d..%d] 塞不進 %d 頁 → 改用連續配頁。"
                         % (lo, hi, n_pages))
    if usable:
        notes.append("IMAGELIST 第一個欄位視為 %s TIFF 頁碼。"
                     % ("1-based（1 = 第一頁）" if base == 1 else "0-based（0 = 第一頁）"))
        return {"mode": "imagelist", "base": base,
                "pages": [[i - base for i in ids] for ids in ids_per_row],
                "notes": notes}
    pages, cum = [], 0
    for cnt in counts:
        pages.append(list(range(cum, cum + cnt)))
        cum += cnt
    if total != n_pages:
        notes.append("IMAGECOUNT 總和（%d）不等於 TIFF 頁數（%d）→ 連續配頁可能對不上。"
                     % (total, n_pages))
    notes.append("依 defect 出現順序連續配頁。")
    return {"mode": "sequential", "base": None, "pages": pages, "notes": notes}


# ---------------------------------------------------------------- 報告

def emit_header(path, include_ids):
    _out("=" * 74)
    _out("ADEPT 廠內探測報告 #2：TIFF 結構（probe_tiff.py v%s）" % PROBE_VERSION)
    _out("=" * 74)
    _out("")
    _out("【這份報告包含什麼】")
    _out("  - TIFF 檔層資訊（位元組序、是否 BigTIFF、頁數、檔案大小）")
    _out("  - 抽樣頁的尺寸/位元深度/通道數/壓縮/光度/tile 或 strip 等結構標籤")
    _out("  - ImageDescription、Software 等文字標籤（截斷 + 識別碼遮蔽，數字保留）")
    _out("  - 搭配 --with-klarf 時：defect 數與頁數的對應關係檢查")
    _out("【這份報告不包含什麼】")
    _out("  - **完全不讀像素**（本腳本只讀 IFD 標籤，連一個 byte 的影像資料都沒解碼）")
    _out("  - 不含檔名原文（只印副檔名與字元數）、不含 defect 座標")
    if include_ids:
        _out("")
        _out("  ** 注意：本次以 --include-ids 執行 → 檔名與文字標籤會照原樣輸出。**")
    _out("")


def emit_file_info(path, info, include_ids):
    _out("-" * 74)
    _out("1. 檔案層資訊")
    _out("-" * 74)
    _out("  檔名          : %s" % redact_name(path, include_ids))
    _out("  大小          : %d bytes" % info["file_bytes"])
    _out("  位元組序      : %s" % info["byte_order"])
    _out("  BigTIFF       : %s" % ("是" if info["bigtiff"] else "否（classic TIFF）"))
    _out("  頁數（IFD 數）: %d" % info["n_pages"])
    if info["unknown_tags"]:
        top = sorted(info["unknown_tags"].items(), key=lambda kv: -kv[1])[:12]
        _out("  未收錄的標籤  : %s"
             % ", ".join("tag %d x%d" % (t, c) for t, c in top))
        _out("                  （probe 沒有解讀這些標籤；若其中有廠商私有的 pixel size，")
        _out("                    請把 tag 編號回報，我們再加進來看）")
    _out("")


def emit_uniformity(pages):
    _out("-" * 74)
    _out("2. 各頁尺寸是否一致")
    _out("-" * 74)
    sigs = {}
    for p in pages:
        sigs.setdefault(page_sig(p), []).append(p["index"])
    _out("  相異的頁面規格數：%d" % len(sigs))
    for sig, idxs in sorted(sigs.items(), key=lambda kv: -len(kv[1])):
        head = ", ".join(str(i) for i in idxs[:8])
        _out("    %-52s x%-6d 頁索引：%s%s"
             % (sig, len(idxs), head, " ..." if len(idxs) > 8 else ""))
    uniform = len(sigs) == 1
    _out("  → %s" % ("所有頁面規格完全一致（uniform）。" if uniform else
                     "**頁面規格不一致 —— ADEPT 假設同一份 patch TIFF 各頁同尺寸，請回報。**"))
    _out("")
    return uniform, len(sigs)


def emit_pages(pages, info, sel, include_ids):
    _out("-" * 74)
    _out("3. 抽樣頁的標籤（前幾頁 + 中段 + 最後兩頁）")
    _out("-" * 74)
    prev_key = None
    for i in sel:
        p = pages[i]
        key = json.dumps(dict((k, v) for k, v in p.items()
                              if k not in ("index", "ifd_offset", "strip_offsets",
                                           "tile_offsets", "data_bytes",
                                           "strip_bytes", "tile_bytes")),
                         sort_keys=True, default=str)
        _out("  [第 %d 頁 / 共 %d]" % (i, info["n_pages"]))
        if key == prev_key:
            _out("     （標籤與上一個列出的頁完全相同；只有影像資料位置不同）")
            continue
        prev_key = key
        _out("     規格        : %s" % page_sig(p))
        if "tile_w" in p:
            _out("     tile        : %sx%s" % (p.get("tile_w"), p.get("tile_h")))
        else:
            _out("     strip       : rows_per_strip=%s，strip 數=%s"
                 % (p.get("rows_per_strip", "?"),
                    len(p["strip_offsets"]) if isinstance(p.get("strip_offsets"), list) else 1))
        _out("     影像資料量  : %s bytes" % p.get("data_bytes", "?"))
        extra = []
        for key, label in (("planarconfig", "planar"), ("sample_format", "sample_format"),
                           ("predictor", "predictor"), ("page_number", "page_number"),
                           ("subfile", "subfile")):
            if key in p:
                extra.append("%s=%s" % (label, p[key]))
        if extra:
            _out("     其他        : %s" % ", ".join(extra))
        if "xres" in p or "yres" in p:
            _out("     解析度      : xres=%s yres=%s unit=%s  <- **假設 #2 的線索**"
                 % (p.get("xres"), p.get("yres"),
                    RESUNIT.get(p.get("res_unit"), p.get("res_unit"))))
        for key, label in (("description", "ImageDescription"), ("software", "Software"),
                           ("make", "Make"), ("model", "Model"), ("datetime", "DateTime")):
            if key in p:
                v = p[key]
                if isinstance(v, list):
                    v = " ".join(str(x) for x in v[:8])
                _out("     %-12s: %s" % (label, redact_text(v, include_ids)))
    _out("")
    _out("  ** ImageDescription / Software 裡若出現像 PixelSize=3.2nm 這種字樣，**")
    _out("  ** 就是 nm_per_px 的來源（假設 #2）—— 請把那一行回報。**")
    _out("")


def emit_desc_pattern(pages, info):
    """頁面文字標籤的週期性 —— 對「哪一頁是 test、哪一頁是 ref」是直接證據。"""
    _out("-" * 74)
    _out("4. 頁面標籤的週期性（判斷 test/ref 交錯的線索）")
    _out("-" * 74)
    keys = []
    for p in pages:
        parts = []
        for k in ("description", "software", "page_number", "photometric",
                  "width", "height"):
            if k in p:
                parts.append("%s=%s" % (k, p[k]))
        keys.append("|".join(parts))
    uniq = {}
    for k in keys:
        uniq[k] = uniq.get(k, 0) + 1
    _out("  相異的標籤組合數：%d（共 %d 頁）" % (len(uniq), len(pages)))
    period = None
    for cand in (1, 2, 3, 4):
        if len(keys) >= 2 * cand and all(
                keys[i] == keys[i % cand] for i in range(len(keys))):
            period = cand
            break
    if period == 1:
        _out("  → 所有頁的標籤完全相同：標籤本身分不出 test / ref。")
    elif period:
        _out("  → 標籤以 %d 頁為週期重複 —— 與「每顆 defect %d 張、順序固定」一致。"
             % (period, period))
    else:
        _out("  → 標籤沒有明顯週期（每頁都帶各自的資訊，例如逐頁編號）。")
    seq = [p.get("page_number") for p in pages[:8]]
    if any(s is not None for s in seq):
        _out("  前 8 頁的 page_number 標籤：%s" % seq)
    _out("")
    return period


def emit_klarf_crosscheck(klarf_path, pages, info, include_ids):
    _out("-" * 74)
    _out("5. 與 KLARF 交叉比對（**假設 #1：本報告最重要的一段**）")
    _out("-" * 74)
    d = klarf_parse(klarf_path)
    ic, il = _image_cols(d)
    n_rows = len(d["rows"])
    n_pages = info["n_pages"]
    counts = {}
    total = 0
    for r in d["rows"]:
        c = _img_count(r, ic)
        counts[c] = counts.get(c, 0) + 1
        total += c
    _out("  KLARF          : %s（版本 %s）"
         % (redact_name(klarf_path, include_ids), d["version"]))
    _out("  defect 列數    : %d" % n_rows)
    _out("  TIFF 頁數      : %d" % n_pages)
    _out("  IMAGECOUNT 總和: %d" % total)
    _out("")
    _out("  每顆 defect 的影像張數分布：")
    for line in histogram_lines(counts):
        _out(line)

    uniq = sorted(k for k in counts.keys())
    if ic < 0:
        _out("")
        _out("  觀察到的排列   : 無法判斷 —— 這份 KLARF 沒有 IMAGECOUNT 欄")
        _out("  → 影像資訊可能寫在列尾的 `Image/Images { \"檔名\" }` 子區塊裡"
             "（每顆 defect 一個獨立影像檔），")
        _out("    那就和這份多頁 TIFF 沒有對應關係。請改跑 probe_klarf.py 看第 5 段的變體判定。")
        _out("")
        return {"klarf_version": d["version"], "n_defect_rows": n_rows,
                "imagecount_total": 0, "pattern": "no-imagecount-column",
                "pages_eq_2x_defects": (n_pages == 2 * n_rows),
                "pages_eq_imagecount": False, "map_mode": None, "map_base": None,
                "map_out_of_range": 0, "imagecount_distribution": {}}
    if uniq == [1]:
        pattern = "single"
        pat_txt = "single（每顆 1 張）"
    elif uniq == [2]:
        pattern = "pairs"
        pat_txt = "pairs（每顆 2 張）"
    elif uniq == [3]:
        pattern = "triples"
        pat_txt = "triples（每顆 3 張）"
    elif len(uniq) == 1:
        pattern = "n=%d" % uniq[0]
        pat_txt = "每顆 %d 張" % uniq[0]
    else:
        pattern = "mixed"
        pat_txt = "mixed（張數不一致：%s）" % ",".join(str(u) for u in uniq)
    _out("")
    _out("  觀察到的排列   : %s" % pat_txt)
    ok_pair = (n_pages == 2 * n_rows)
    _out("  檢查 A：頁數 == 2 x defect 數？  %s（%d vs %d）"
         % ("是" if ok_pair else "否", n_pages, 2 * n_rows))
    ok_total = (n_pages == total)
    _out("  檢查 B：頁數 == IMAGECOUNT 總和？%s（%d vs %d）"
         % ("是" if ok_total else "否", n_pages, total))
    if ok_pair and pattern == "pairs":
        _out("  → 與 ADEPT 目前的假設一致：每顆 defect 兩頁（假設第 1 頁 = test、第 2 頁 = ref）。")
        _out("    注意：這只證明『成對』，**沒有證明哪一張是 test**。")
        _out("    要確認先後順序，請看第 4 段的標籤週期，或用 probe_stats.py 看奇/偶頁的亮度差異。")
    elif pattern == "single":
        _out("  → 每顆 defect 只有一張：沒有 ref，屬 Review SEM 型流程。")
    else:
        _out("  ** → 與 test/ref 成對假設不符，這正是要找的差異，請務必回報這一段。**")

    imap = defect_image_map(d, n_pages)
    _out("")
    _out("  宣告的 page 對應是否解得開：%s"
         % ({"imagelist": "解得開（imagelist 模式，id 直接是頁碼）",
             "sequential": "解不開，退回連續配頁（sequential 模式）",
             None: "沒有對應資訊"}[imap["mode"]]))
    if imap["base"] is not None:
        _out("  id 起算基準    : %d-based" % imap["base"])
    for note in imap["notes"]:
        _out("    - %s" % note)
    shown = [pg for pg in imap["pages"][:5]]
    if shown:
        _out("  前幾顆 defect 對到的頁（0-based 頁索引，不是座標）：")
        for k, pg in enumerate(shown):
            _out("    defect #%d -> %s" % (k, pg))
    out_of_range = 0
    for pg in imap["pages"]:
        for x in pg:
            if x < 0 or x >= n_pages:
                out_of_range += 1
    if out_of_range:
        _out("  ** 有 %d 個對應頁碼落在 0..%d 之外 —— 對應規則和 ADEPT 想的不一樣，請回報。**"
             % (out_of_range, n_pages - 1))
    _out("")
    return {"klarf_version": d["version"], "n_defect_rows": n_rows,
            "imagecount_total": total, "pattern": pattern,
            "pages_eq_2x_defects": ok_pair, "pages_eq_imagecount": ok_total,
            "map_mode": imap["mode"], "map_base": imap["base"],
            "map_out_of_range": out_of_range,
            "imagecount_distribution": dict((str(k), v) for k, v in sorted(counts.items()))}


def emit_json(summary):
    _out("=" * 74)
    _out("請回報這一段（機器可讀摘要，可安全貼出；不含識別碼、不含像素）")
    _out("=" * 74)
    _out(">>>JSON_BEGIN")
    for line in json_block(summary):
        _out(line)
    _out(">>>JSON_END")


# ---------------------------------------------------------------- main

def run(path, n_first=8, with_klarf=None, include_ids=False):
    pages, info = read_tiff_pages(path)
    emit_header(path, include_ids)
    emit_file_info(path, info, include_ids)
    uniform, n_sigs = emit_uniformity(pages)
    sel = select_pages(info["n_pages"], n_first)
    emit_pages(pages, info, sel, include_ids)
    period = emit_desc_pattern(pages, info)
    cross = None
    if with_klarf:
        cross = emit_klarf_crosscheck(with_klarf, pages, info, include_ids)

    p0 = pages[0]
    summary = {}
    summary["schema"] = SCHEMA
    summary["probe_version"] = PROBE_VERSION
    summary["file_bytes"] = info["file_bytes"]
    summary["byte_order"] = info["byte_order"]
    summary["bigtiff"] = info["bigtiff"]
    summary["n_pages"] = info["n_pages"]
    summary["uniform_pages"] = uniform
    summary["n_page_signatures"] = n_sigs
    summary["page0"] = {"width": p0.get("width"), "height": p0.get("height"),
                        "bits": p0.get("bits"), "spp": p0.get("spp", 1),
                        "compression": COMPRESSION.get(p0.get("compression", 1),
                                                       str(p0.get("compression"))),
                        "photometric": PHOTOMETRIC.get(p0.get("photometric", -1),
                                                       str(p0.get("photometric"))),
                        "layout": "tile" if "tile_w" in p0 else "strip"}
    summary["has_description_tag"] = any("description" in p for p in pages)
    summary["has_resolution_tag"] = any("xres" in p for p in pages)
    summary["unknown_tags"] = sorted(info["unknown_tags"].keys())[:32]
    summary["tag_period"] = period
    summary["adept_unread_tags"] = sorted(
        set(t for t, name in TAGS.items()
            if t not in TAGS_IN_ADEPT and any(name in p for p in pages)))
    summary["klarf_crosscheck"] = cross
    summary["ids_included"] = bool(include_ids)
    emit_json(summary)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="ADEPT 廠內探測 #2：TIFF 結構（單檔、純標準函式庫、不解碼像素）")
    ap.add_argument("tiff", help="要探測的 TIFF 檔（例：C:\\path\\to\\lot.tif）")
    ap.add_argument("--pages", type=int, default=8,
                    help="細看前幾頁（另外自動加看中段與最後兩頁，預設 8）")
    ap.add_argument("--with-klarf", default=None,
                    help="同時給對應的 KLARF，做 defect 數 / 頁數的成對檢查（假設 #1）")
    ap.add_argument("--include-ids", action="store_true",
                    help="檔名與文字標籤照原樣輸出（預設遮蔽）")
    args = ap.parse_args(argv)
    try:
        return run(args.tiff, max(1, args.pages), args.with_klarf, args.include_ids)
    except ProbeError as exc:
        sys.stderr.write("錯誤：%s\n" % exc)
        return 2
    except Exception as exc:                      # noqa: BLE001
        sys.stderr.write("錯誤：探測失敗（%s: %s）。請把這行連同檔案大小回報。\n"
                         % (type(exc).__name__, exc))
        return 3


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(errors="replace")
        except Exception:
            pass
    sys.exit(main())

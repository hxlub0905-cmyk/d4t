#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""d4t 廠內探測腳本 #3：灰階統計（單檔、純標準函式庫）。

*** 這是三支腳本裡唯一會「讀像素值」的一支。***
它只輸出彙總統計（直方圖、min/max/平均/標準差、4x4 區塊平均），
不輸出任何一顆像素、不輸出可還原影像的資訊；但既然它碰了像素，
請先確認公司的資料攜出規範，再把報告貼出廠外。

用途：
  - 影像段參數（正規化、對比）要怎麼設，看灰階分布就知道
  - 每頁平均亮度的漂移 → 判斷 test/ref 或前後頁是否有系統性亮度差（假設 #1 的旁證）
  - 4x4 區塊平均 → 看視野是否有大範圍不均（照明/掃描不均）

TIFF 走訪邏輯鏡射自 d4t/core/ingest/tiff_index.py（read_tiff_pages）；
像素解碼在 d4t 是交給 tifffile，這裡為了「不裝任何套件」自己寫了
最小解碼器：**只支援 strip 排列、未壓縮或 PackBits、8/16-bit、單通道**。
遇到解不開的壓縮方式會清楚說明並跳過該頁，不會中斷。

用法：
    python probe_stats.py FILE.tif [--pages 20] [--bins 16] [--max-pixels 2000000]
"""

import argparse
import array
import json
import math
import os
import struct
import sys

PROBE_VERSION = "1.0"
SCHEMA = "d4t.fab_probe.stats/1"

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4,
             10: 8, 11: 4, 12: 8, 13: 4, 16: 8, 17: 8, 18: 8}

COMPRESSION = {1: "none", 2: "CCITT-RLE", 3: "CCITT-G3", 4: "CCITT-G4",
               5: "LZW", 6: "old-JPEG", 7: "JPEG", 8: "deflate",
               32773: "PackBits", 32946: "deflate"}

PHOTOMETRIC = {0: "white-is-zero", 1: "black-is-zero", 2: "RGB",
               3: "palette", 4: "mask", 5: "CMYK", 6: "YCbCr"}

TAGS = {254: "subfile", 256: "width", 257: "height", 258: "bits",
        259: "compression", 262: "photometric", 270: "description",
        273: "strip_offsets", 277: "spp", 278: "rows_per_strip",
        279: "strip_bytes", 284: "planarconfig", 305: "software",
        317: "predictor", 322: "tile_w", 323: "tile_h", 324: "tile_offsets",
        325: "tile_bytes", 339: "sample_format"}

RAMP = ".:-=+*#@"          # 8 級（由暗到亮）；不用空白，方格才看得出來


class ProbeError(Exception):
    pass


def _out(line=""):
    print(line)


def redact_name(path):
    base = os.path.basename(str(path))
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


# ------------------------------------------------- IFD 走訪（鏡射 tiff_index）

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


def read_tiff_pages(f, path):
    pages = []
    head = f.read(8)
    if len(head) < 8:
        raise ProbeError("檔案太小（%d bytes），不可能是 TIFF。" % os.path.getsize(path))
    if head[:2] == b"II":
        en = "<"
    elif head[:2] == b"MM":
        en = ">"
    else:
        hint = ""
        if head.startswith(b"\x89PNG"):
            hint = "（看起來是 PNG）"
        elif head.startswith(b"\xff\xd8\xff"):
            hint = "（看起來是 JPEG）"
        raise ProbeError("這個檔不是 TIFF/BigTIFF：開頭不是 II 或 MM 位元組序標記%s。"
                         "\n      若你的影像是每顆 defect 一個 PNG/JPG（Review SEM 型），"
                         "本腳本目前只吃多頁 TIFF。" % hint)
    magic = struct.unpack(en + "H", head[2:4])[0]
    big = (magic == 43)
    if magic == 42:
        next_ifd = struct.unpack(en + "I", head[4:8])[0]
    elif big:
        off_size, zero = struct.unpack(en + "HH", head[4:8])
        if off_size != 8 or zero != 0:
            raise ProbeError("BigTIFF 檔頭損毀。")
        next_ifd = struct.unpack(en + "Q", f.read(8))[0]
    else:
        raise ProbeError("不認得的 TIFF magic %d（應為 42 或 43）。" % magic)

    seen = set()
    while next_ifd:
        if next_ifd in seen:
            raise ProbeError("IFD 串鏈成環 —— TIFF 檔損毀。")
        seen.add(next_ifd)
        f.seek(next_ifd)
        nb = f.read(8 if big else 2)
        if len(nb) < (8 if big else 2):
            break
        n = struct.unpack(en + ("Q" if big else "H"), nb)[0]
        page = {"index": len(pages)}
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
                continue
            vals = _read_values(f, en, vtype, count, raw, big)
            if vals is None:
                continue
            page[name] = vals[0] if len(vals) == 1 else vals
        pages.append(page)
        nb = f.read(8 if big else 4)
        if len(nb) < (8 if big else 4):
            break
        next_ifd = struct.unpack(en + ("Q" if big else "I"), nb)[0]
    if not pages:
        raise ProbeError("這個 TIFF 一頁都沒有。")
    return pages, {"endian": en, "bigtiff": big, "n_pages": len(pages),
                   "file_bytes": os.path.getsize(path)}


# ---------------------------------------------------------------- 像素解碼

def unpackbits(data, expected):
    """PackBits（TIFF compression 32773）解碼。"""
    out = bytearray()
    i, n = 0, len(data)
    while i < n and len(out) < expected:
        h = data[i]
        i += 1
        if h < 128:
            cnt = h + 1
            out += data[i:i + cnt]
            i += cnt
        elif h > 128:
            if i >= n:
                break
            out += bytes(data[i:i + 1]) * (257 - h)
            i += 1
    return bytes(out)


def _as_list(v):
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def page_reason(p):
    """這頁能不能解？不能的話回一句白話原因；能解回 None。"""
    if "tile_w" in p or "tile_offsets" in p:
        return "以 tile 排列（本腳本只支援 strip 排列）"
    bits = p.get("bits", 8)
    if isinstance(bits, list):
        return "每通道位元深度不一致（%s）" % bits
    spp = p.get("spp", 1)
    if isinstance(spp, list):
        spp = spp[0]
    if spp != 1:
        return "多通道影像（SamplesPerPixel=%s，本腳本只支援單通道灰階）" % spp
    if bits not in (8, 16):
        return "%s-bit（本腳本只支援 8/16-bit）" % bits
    comp = p.get("compression", 1)
    if comp not in (1, 32773):
        return "壓縮方式 %s（本腳本只解得開 未壓縮 與 PackBits）" % COMPRESSION.get(comp, comp)
    pred = p.get("predictor", 1)
    if pred not in (1, None):
        return "predictor=%s（水平差分預測，本腳本不支援）" % pred
    pc = p.get("planarconfig", 1)
    if pc not in (1, None):
        return "planarconfig=%s（分離平面，本腳本只支援 chunky）" % pc
    if "strip_offsets" not in p:
        return "沒有 StripOffsets 標籤（找不到影像資料）"
    if not p.get("width") or not p.get("height"):
        return "缺少寬或高標籤"
    return None


def sample_page(f, p, en, max_pixels):
    """讀一頁的（抽樣）像素，回傳 (rows, w, h, bits, stride)。

    rows = [(列索引, 序列)]；序列是 bytes（8-bit）或 array('H')（16-bit）。
    為了控制記憶體與時間，列會依 stride 抽樣（大圖才會 > 1）。
    """
    w, h = int(p["width"]), int(p["height"])
    bits = int(p.get("bits", 8))
    bypp = bits // 8
    rowbytes = w * bypp
    rps = p.get("rows_per_strip", h)
    if isinstance(rps, list):
        rps = rps[0]
    rps = int(rps) if rps else h
    rps = max(1, min(rps, h))
    offsets = _as_list(p.get("strip_offsets"))
    counts = _as_list(p.get("strip_bytes")) or [rowbytes * rps] * len(offsets)
    comp = p.get("compression", 1)

    max_rows = max(1, int(max_pixels // max(1, w)))
    stride = max(1, int(math.ceil(h / float(max_rows))))
    wanted = set(range(0, h, stride))

    rows = []
    for s, off in enumerate(offsets):
        r0 = s * rps
        r1 = min(h, r0 + rps)
        need = [r for r in range(r0, r1) if r in wanted]
        if not need:
            continue
        nbytes = int(counts[s]) if s < len(counts) else rowbytes * (r1 - r0)
        f.seek(int(off))
        data = f.read(nbytes)
        if comp == 32773:
            data = unpackbits(data, rowbytes * (r1 - r0))
        for r in need:
            a = (r - r0) * rowbytes
            chunk = data[a:a + rowbytes]
            if len(chunk) < rowbytes:
                continue                      # 資料不足的殘列直接不取樣
            if bits == 8:
                rows.append((r, chunk))
            else:
                arr = array.array("H")
                arr.frombytes(chunk)
                if (en == "<") != (sys.byteorder == "little"):
                    arr.byteswap()
                rows.append((r, arr))
    return rows, w, h, bits, stride


def page_summary(rows, w, h, bits):
    """由抽樣列算出 值直方圖 + 4x4 區塊平均。"""
    hist = {}
    if bits == 8:
        buf = b"".join(r[1] for r in rows)
        for v in range(256):
            c = buf.count(bytes([v]))
            if c:
                hist[v] = c
    else:
        for _r, seq in rows:
            for v in seq:
                hist[v] = hist.get(v, 0) + 1

    bsum = [0.0] * 16
    bcnt = [0] * 16
    edges = [int(round(w * k / 4.0)) for k in range(5)]
    for r, seq in rows:
        br = min(3, int(r * 4 // h))
        for bc in range(4):
            a, b = edges[bc], edges[bc + 1]
            if b <= a:
                continue
            bsum[br * 4 + bc] += float(sum(seq[a:b]))
            bcnt[br * 4 + bc] += (b - a)
    grid = [(bsum[i] / bcnt[i]) if bcnt[i] else None for i in range(16)]
    return hist, grid


def hist_stats(hist):
    n = sum(hist.values())
    if n == 0:
        return {"n": 0, "min": None, "max": None, "mean": None, "std": None}
    s = sum(v * c for v, c in hist.items())
    s2 = sum(float(v) * v * c for v, c in hist.items())
    mean = s / float(n)
    var = max(0.0, s2 / float(n) - mean * mean)
    return {"n": n, "min": min(hist), "max": max(hist),
            "mean": mean, "std": math.sqrt(var)}


def select_pages(n, k):
    """抽樣頁：盡量以「相鄰兩頁一組」抽，才看得出 test/ref 這種成對結構。"""
    if n <= k:
        return list(range(n))
    npairs = max(1, k // 2)
    step = max(2, (n // npairs))
    if step % 2:
        step += 1
    sel = []
    i = 0
    while i < n and len(sel) < k:
        sel.append(i)
        if i + 1 < n and len(sel) < k:
            sel.append(i + 1)
        i += step
    return sorted(set(sel))


# ---------------------------------------------------------------- 報告

def emit_header(path):
    _out("=" * 74)
    _out("d4t 廠內探測報告 #3：灰階統計（probe_stats.py v%s）" % PROBE_VERSION)
    _out("=" * 74)
    _out("")
    _out("  ****************************************************************")
    _out("  * 注意：三支探測腳本裡，只有這一支會實際讀取影像的像素值。      *")
    _out("  * 它只輸出彙總統計，不輸出任何一顆像素、不可能還原出影像；      *")
    _out("  * 但請先確認貴公司的資料攜出規範允許，再把這份報告貼出廠外。    *")
    _out("  ****************************************************************")
    _out("")
    _out("【這份報告包含什麼】")
    _out("  - 抽樣頁的灰階直方圖（預設 16 格）與 min / max / 平均 / 標準差")
    _out("  - 每頁的平均與標準差（看亮度漂移、看奇偶頁是否有系統性差異）")
    _out("  - 一張 4x4 的區塊平均 ASCII 圖（只有 16 個數字，粗到無法辨識任何圖樣）")
    _out("【這份報告不包含什麼】")
    _out("  - 不含任何單一像素值、不含 4x4 以外的空間資訊、不含影像縮圖")
    _out("  - 不含檔名原文、不含 defect 座標")
    _out("")


def emit_pages(path, pages, info, sel, results, max_pixels):
    _out("-" * 74)
    _out("1. 檔案與抽樣")
    _out("-" * 74)
    _out("  檔名          : %s" % redact_name(path))
    _out("  大小          : %d bytes" % info["file_bytes"])
    _out("  頁數          : %d（本次抽樣 %d 頁）" % (info["n_pages"], len(sel)))
    _out("  抽樣頁索引    : %s%s" % (", ".join(str(i) for i in sel[:24]),
                                     " ..." if len(sel) > 24 else ""))
    _out("  每頁像素上限  : %d（超過就依列抽樣，抽樣率會標在下表）" % max_pixels)
    _out("")
    _out("-" * 74)
    _out("2. 每頁統計（值域、平均、標準差）")
    _out("-" * 74)
    _out("  %-6s %-12s %-6s %-9s %-9s %-9s %-9s %s"
         % ("頁", "尺寸", "bits", "取樣像素", "min", "max", "平均", "標準差"))
    ok = 0
    for r in results:
        if r["skip"]:
            _out("  %-6d %-12s %s" % (r["index"], "-", "跳過：" + r["skip"]))
            continue
        ok += 1
        st = r["stats"]
        _out("  %-6d %-12s %-6d %-9d %-9s %-9s %-9.2f %-9.2f%s"
             % (r["index"], "%dx%d" % (r["w"], r["h"]), r["bits"], st["n"],
                st["min"], st["max"], st["mean"], st["std"],
                ("  （列抽樣 1/%d）" % r["stride"]) if r["stride"] > 1 else ""))
    _out("")
    if ok == 0:
        _out("  ** 沒有任何一頁解得開 —— 上面的原因就是要回報的重點。**")
        _out("")
    return ok


def emit_histogram(hist, bits, bins):
    _out("-" * 74)
    _out("3. 灰階直方圖（所有抽樣頁合計）")
    _out("-" * 74)
    n = sum(hist.values())
    top = (1 << bits) - 1
    counts = [0] * bins
    for v, c in hist.items():
        k = int(v * bins // (top + 1))
        counts[min(bins - 1, max(0, k))] += c
    mx = max(counts) if counts else 0
    _out("  值域 0..%d 分成 %d 格；合計 %d 個像素" % (top, bins, n))
    for i, c in enumerate(counts):
        lo = int(round(i * (top + 1) / float(bins)))
        hi = int(round((i + 1) * (top + 1) / float(bins))) - 1
        bar = "#" * (int(round(46 * c / float(mx))) if mx else 0)
        _out("  [%6d..%6d] %10d %5.1f%% %s"
             % (lo, hi, c, 100.0 * c / n if n else 0.0, bar))
    st = hist_stats(hist)
    _out("")
    _out("  min=%s  max=%s  平均=%.2f  標準差=%.2f"
         % (st["min"], st["max"], st["mean"], st["std"]))
    sat_lo = hist.get(0, 0)
    sat_hi = hist.get(top, 0)
    _out("  貼邊像素：值=0 有 %d（%.2f%%）、值=%d 有 %d（%.2f%%）"
         % (sat_lo, 100.0 * sat_lo / n if n else 0, top, sat_hi,
            100.0 * sat_hi / n if n else 0))
    if n and (sat_lo + sat_hi) / float(n) > 0.01:
        _out("  → 有明顯的飽和/截斷（超過 1%）；影像段的正規化參數要留意。")
    _out("")
    return counts, st


def emit_drift(results):
    _out("-" * 74)
    _out("4. 每頁亮度漂移（假設 #1 的旁證：奇偶頁是否有系統性差異）")
    _out("-" * 74)
    good = [r for r in results if not r["skip"]]
    means = [r["stats"]["mean"] for r in good]
    stds = [r["stats"]["std"] for r in good]
    if not means:
        _out("  （沒有可用的頁）")
        _out("")
        return None
    lo, hi = min(means), max(means)
    avg = sum(means) / len(means)
    spread = math.sqrt(sum((m - avg) ** 2 for m in means) / len(means))
    _out("  頁平均值：最小 %.2f、最大 %.2f、全體平均 %.2f、頁間標準差 %.2f"
         % (lo, hi, avg, spread))
    _out("  頁標準差：最小 %.2f、最大 %.2f" % (min(stds), max(stds)))
    even = [r["stats"]["mean"] for r in good if r["index"] % 2 == 0]
    odd = [r["stats"]["mean"] for r in good if r["index"] % 2 == 1]
    result = {"page_mean_min": lo, "page_mean_max": hi, "page_mean_spread": spread,
              "even_mean": None, "odd_mean": None}
    if even and odd:
        em = sum(even) / len(even)
        om = sum(odd) / len(odd)
        result["even_mean"] = em
        result["odd_mean"] = om
        _out("  偶數頁平均 %.2f（%d 頁） vs 奇數頁平均 %.2f（%d 頁），差 %.2f"
             % (em, len(even), om, len(odd), em - om))
        if spread > 0 and abs(em - om) > 0.5 * spread and abs(em - om) > 0.5:
            _out("  → 奇偶頁有系統性亮度差：與『兩頁一組、兩頁來源不同（test/ref）』的假設一致。")
        else:
            _out("  → 奇偶頁沒有明顯系統性差異（分不出 test/ref，也可能兩者本來就同亮度）。")
    else:
        _out("  （抽樣頁的奇偶不齊，無法比較）")
    _out("")
    return result


def emit_grid(grids, bits):
    _out("-" * 74)
    _out("5. 4x4 區塊平均（唯一的空間資訊；粗到無法辨識任何圖樣）")
    _out("-" * 74)
    acc = [0.0] * 16
    cnt = [0] * 16
    for g in grids:
        for i, v in enumerate(g):
            if v is not None:
                acc[i] += v
                cnt[i] += 1
    grid = [(acc[i] / cnt[i]) if cnt[i] else 0.0 for i in range(16)]
    lo, hi = min(grid), max(grid)
    rng = hi - lo
    _out("  ASCII（字元梯度 %s，暗 -> 亮；每格 = 全圖 1/16 面積的平均）：" % RAMP)
    for r in range(4):
        line = ""
        for c in range(4):
            v = grid[r * 4 + c]
            k = 0 if rng <= 0 else int(min(len(RAMP) - 1, (v - lo) / rng * (len(RAMP) - 1)))
            line += RAMP[k]
        _out("    %s" % line)
    _out("  區塊平均值：")
    for r in range(4):
        _out("    %s" % "  ".join("%8.2f" % grid[r * 4 + c] for c in range(4)))
    _out("  區塊間最大落差：%.2f（全體平均 %.2f）"
         % (rng, sum(grid) / 16.0))
    if rng > 0.08 * ((1 << bits) - 1):
        _out("  → 視野內有明顯的大範圍不均（照明/掃描不均）；影像段可考慮做背景平坦化。")
    else:
        _out("  → 視野大致平坦。")
    _out("")
    return grid


def emit_json(summary):
    _out("=" * 74)
    _out("請回報這一段（機器可讀摘要；只有彙總數字，沒有任何像素）")
    _out("=" * 74)
    _out(">>>JSON_BEGIN")
    for line in json_block(summary):
        _out(line)
    _out(">>>JSON_END")


# ---------------------------------------------------------------- main

def run(path, n_pages=20, bins=16, max_pixels=2000000):
    if not os.path.isfile(path):
        raise ProbeError("找不到檔案：%s" % path)
    with open(path, "rb") as f:
        pages, info = read_tiff_pages(f, path)    # 先確認檔案讀得開，再輸出抬頭
        emit_header(path)
        sel = select_pages(info["n_pages"], n_pages)
        results = []
        total_hist = {}
        grids = []
        bits_seen = set()
        for i in sel:
            p = pages[i]
            why = page_reason(p)
            if why:
                results.append({"index": i, "skip": why})
                continue
            rows, w, h, bits, stride = sample_page(f, p, info["endian"], max_pixels)
            if not rows:
                results.append({"index": i, "skip": "讀不到任何完整的列（資料被截斷？）"})
                continue
            hist, grid = page_summary(rows, w, h, bits)
            bits_seen.add(bits)
            for v, c in hist.items():
                total_hist[v] = total_hist.get(v, 0) + c
            grids.append(grid)
            results.append({"index": i, "skip": None, "w": w, "h": h, "bits": bits,
                            "stride": stride, "stats": hist_stats(hist)})

    n_ok = emit_pages(path, pages, info, sel, results, max_pixels)
    bits = max(bits_seen) if bits_seen else 8
    if len(bits_seen) > 1:
        _out("  ** 抽樣頁的位元深度不一致（%s）；直方圖以 %d-bit 值域繪製。**"
             % (sorted(bits_seen), bits))
        _out("")
    counts, st = ([], {"n": 0, "min": None, "max": None, "mean": None, "std": None})
    drift = None
    grid = [0.0] * 16
    if n_ok:
        counts, st = emit_histogram(total_hist, bits, bins)
        drift = emit_drift(results)
        grid = emit_grid(grids, bits)

    summary = {}
    summary["schema"] = SCHEMA
    summary["probe_version"] = PROBE_VERSION
    summary["file_bytes"] = info["file_bytes"]
    summary["n_pages"] = info["n_pages"]
    summary["sampled_pages"] = sel
    summary["decoded_pages"] = n_ok
    summary["skipped"] = dict((str(r["index"]), r["skip"]) for r in results if r["skip"])
    summary["bits"] = bits
    summary["bins"] = bins
    summary["sampled_pixels"] = st["n"]
    summary["histogram"] = counts
    summary["min"] = st["min"]
    summary["max"] = st["max"]
    summary["mean"] = round(st["mean"], 4) if st["mean"] is not None else None
    summary["std"] = round(st["std"], 4) if st["std"] is not None else None
    summary["page_means"] = [round(r["stats"]["mean"], 3)
                             for r in results if not r["skip"]]
    summary["page_stds"] = [round(r["stats"]["std"], 3)
                            for r in results if not r["skip"]]
    summary["drift"] = (dict((k, (round(v, 4) if isinstance(v, float) else v))
                             for k, v in drift.items()) if drift else None)
    summary["grid4x4"] = [round(v, 2) for v in grid]
    emit_json(summary)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="d4t 廠內探測 #3：灰階統計（會讀像素值，只輸出彙總統計）")
    ap.add_argument("tiff", help="要探測的多頁 TIFF（例：C:\\path\\to\\lot.tif）")
    ap.add_argument("--pages", type=int, default=20, help="抽樣幾頁（預設 20）")
    ap.add_argument("--bins", type=int, default=16, help="直方圖格數（預設 16）")
    ap.add_argument("--max-pixels", type=int, default=2000000,
                    help="每頁最多取樣幾個像素（超過就依列抽樣，預設 200 萬）")
    args = ap.parse_args(argv)
    if args.bins < 2 or args.bins > 256:
        sys.stderr.write("錯誤：--bins 請給 2..256 之間的值（收到 %d）。\n" % args.bins)
        return 2
    try:
        return run(args.tiff, max(1, args.pages), args.bins, max(1000, args.max_pixels))
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

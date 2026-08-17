#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADEPT 廠內探測腳本 #1：KLARF 結構探測（單檔、純標準函式庫）。

用途：在廠內真實 KLARF 上確認 docs/FAB-VALIDATION.md 的兩個假設 ——
  假設 #3「KLARF 影像佈局變體」（本腳本最重要的輸出）
  假設 #2「nm_per_px 從哪來」（欄位名獵捕）

邏輯鏡射自 adept/core/ingest/klarf_core.py：
  detect_version / _parse_12 / _parse_18 / _parse_tiff_fields /
  image_col_index / _detect_images18 / _infer_image_layout /
  defect_image_entries / row_len_ok / tiff_path
本檔「重寫」了上述邏輯的最小必要部分（不 import adept、不用第三方套件），
所以 klarf_core 那邊改判定規則時，這裡要跟著改（兩邊都要更新）。

用法：
    python probe_klarf.py FILE.klarf [--include-ids] [--rows 20]

輸出：純文字報告（預設遮蔽所有識別碼），最後一段是可貼回的 JSON 摘要。
"""

import argparse
import json
import os
import re
import sys

PROBE_VERSION = "1.0"
SCHEMA = "adept.fab_probe.klarf/1"

# ---------------------------------------------------------------- 遮蔽政策
#
# 預設（不加 --include-ids）：
#   * header 欄位「名稱」全部顯示（名稱本身是格式資訊，不是資料）
#   * header 欄位「值」一律遮蔽成 <redacted, N chars>，
#     只有 STRUCTURAL_FIELDS 白名單（幾何/版本類，判讀格式必需）顯示原值
#   * defect 資料一個 token 都不印；只印欄位名、型別、列數、長度統計
#   * 座標（XREL/YREL/XINDEX/…）永不輸出，連範圍都不輸出
#   * 檔名（KLARF 檔本身、TiffFileName）遮蔽，只留副檔名與字元數
#   * ClassLookup 只報「有幾類」，不報類別名稱
#   * nm_per_px 候選欄位是「刻意的例外」：值會顯示（這正是探測目的），
#     但若欄位名同時落在 ID_FIELDS，仍然遮蔽
#
# 加 --include-ids：上述值全部照原樣輸出（由使用者自行判斷可否攜出）。

STRUCTURAL_FIELDS = {
    "FILEVERSION", "FILETIMESTAMP", "SAMPLETYPE", "SAMPLESIZE", "DIEPITCH",
    "DIEORIGIN", "SAMPLEORIENTATIONMARKTYPE", "ORIENTATIONMARKLOCATION",
    "TIFFSPEC", "INSPECTIONTEST", "RESULTTIMESTAMP", "SLOT", "SLOTNUMBER",
    "COORDINATESMIRRORED", "INSPECTIONORIENTATION",
}

ID_FIELDS = {
    "LOTID", "WAFERID", "DEVICEID", "STEPID", "SETUPID", "SCRIBEID",
    "INSPECTIONSTATIONID", "TIFFFILENAME", "IMAGEFILENAME", "FILENAME",
    "RECIPENAME", "RECIPEID", "JOBID", "OPERATORID", "PRODUCTID",
    "SAMPLECENTERLOCATION", "PROCESSEQUIPMENTSTATE", "ORIENTATIONINSTRUCTIONS",
}

# klarf_core 目前「認得」的 header 欄位（1.2 FIELDS_12 + 1.8 Record 對應 + 影像欄）
KNOWN_FIELDS = {
    "FILEVERSION", "FILETIMESTAMP", "INSPECTIONSTATIONID", "SAMPLETYPE",
    "RESULTTIMESTAMP", "LOTID", "SAMPLESIZE", "DEVICEID", "SETUPID", "STEPID",
    "SAMPLEORIENTATIONMARKTYPE", "ORIENTATIONMARKLOCATION", "DIEPITCH",
    "DIEORIGIN", "WAFERID", "SLOT", "SCRIBEID", "SAMPLECENTERLOCATION",
    "TIFFFILENAME", "TIFFSPEC", "IMAGEFILENAME",
}

# 假設 #2：名稱看起來可能帶「像素尺寸 / 比例尺 / 倍率」的欄位
NM_PATTERNS = [
    ("PIXEL", r"PIXEL|PXL|PX_?SIZE"),
    ("SCALE", r"SCALE|CALIB"),
    ("RESOLUT", r"RESOLUT|\bDPI\b"),
    ("MAG", r"MAGNIF|\bMAG\b"),
    ("NM/UM", r"\bNM\b|NANOM|\bUM\b|MICRON|MICROM"),
    ("SIZE", r"SIZE"),
    ("PITCH/FOV", r"PITCH|\bFOV\b|FIELDOFVIEW|ZOOM"),
]

# KLARF-ness 指標：一個都沒有 → 判定不是 KLARF
KLARF_MARKERS = ["FileVersion", "DefectRecordSpec", "DefectList", "FileRecord",
                 "EndOfFile", "SummarySpec", "InspectionStationID", "Columns"]


# ---------------------------------------------------------------- 小工具

def _out(line=""):
    print(line)


def redact(value, name="", include_ids=False, keep=80):
    """依遮蔽政策把一個 header 值轉成可輸出字串。"""
    v = "" if value is None else str(value)
    if include_ids:
        return v if len(v) <= keep else v[:keep] + "...(截斷)"
    up = name.upper()
    if up in STRUCTURAL_FIELDS and up not in ID_FIELDS:
        return v if len(v) <= keep else v[:keep] + "...(截斷)"
    return "<redacted, %d chars>" % len(v)


def redact_name(path, include_ids=False):
    """檔名遮蔽：只留副檔名與字元數（檔名常含 lot/wafer 編號）。"""
    base = os.path.basename(str(path))
    if include_ids:
        return base
    stem, ext = os.path.splitext(base)
    return "<redacted, %d chars>%s" % (len(stem), ext)


def token_shape(tok):
    """把一個 token 換成型別字元（不帶任何內容）。"""
    if tok in ("{", "}"):
        return tok
    if tok.startswith('"'):
        return "s"
    t = tok.lstrip("+-")
    if t.isdigit():
        return "d"
    try:
        float(tok)
        return "f"
    except ValueError:
        pass
    return "w"


def shape_line(tokens, limit=40):
    """列的 token 型別樣式（連續相同者壓成 d*5）。"""
    shapes = [token_shape(t) for t in tokens[:limit]]
    out, i = [], 0
    while i < len(shapes):
        j = i
        while j < len(shapes) and shapes[j] == shapes[i]:
            j += 1
        n = j - i
        out.append(shapes[i] if n == 1 else "%s*%d" % (shapes[i], n))
        i = j
    tail = " ..." if len(tokens) > limit else ""
    return " ".join(out) + tail


def find_image_block(row):
    """找出列中的 `Image/Images N { ... }` 子區塊，回傳 (起, 迄) token 索引（含端點）。

    概念同 klarf_core.defect_image_filename（它用字串找成對大括號，
    這裡改在 token 串上找，才能算出這個變動長度欄位佔幾個 token）。
    """
    for k, tok in enumerate(row):
        if tok not in ("Image", "Images"):
            continue
        b0 = None
        for j in range(k + 1, min(len(row), k + 4)):
            if "{" in row[j] and not row[j].startswith('"'):
                b0 = j
                break
        if b0 is None:
            return None
        depth = 0
        for j in range(b0, len(row)):
            if row[j].startswith('"'):
                continue
            depth += row[j].count("{") - row[j].count("}")
            if depth <= 0:
                return (k, j)
        return (k, len(row) - 1)
    return None


def collapse_row(row):
    """把影像子區塊壓成一個 token，讓「欄位對齊」在變動長度欄之後仍然成立。"""
    span = find_image_block(row)
    if span is None:
        return row
    a, b = span
    return row[:a] + ["<IMAGEBLOCK>"] + row[b + 1:]


def block_filename(row):
    """取影像子區塊裡第一個帶引號的字串（鏡射 defect_image_filename）。"""
    span = find_image_block(row)
    if span is None:
        return None
    for tok in row[span[0]:span[1] + 1]:
        if tok.startswith('"'):
            return tok.strip('"')
    return None


def json_block(d):
    """一行一個 key 的 JSON（整段仍可被 json.loads 解開）。"""
    items = list(d.items())
    lines = ["{"]
    for i, (k, v) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append("  %s: %s%s" % (json.dumps(k, ensure_ascii=False),
                                     json.dumps(v, ensure_ascii=False), comma))
    lines.append("}")
    return lines


def histogram_lines(counter, label="值", width=40):
    """{值: 次數} → 文字直方圖。"""
    if not counter:
        return ["  （無資料）"]
    keys = sorted(counter.keys(), key=lambda k: (isinstance(k, str), k))
    mx = max(counter.values())
    lines = []
    for k in keys:
        n = counter[k]
        bar = "#" * max(1, int(round(width * n / float(mx))))
        lines.append("  %-8s : %8d  %s" % (str(k), n, bar))
    return lines


# ---------------------------------------------------------------- 讀檔

class ProbeError(Exception):
    pass


def read_text(path):
    """讀 KLARF 文字，回傳 (text, meta)。"""
    if not os.path.isfile(path):
        raise ProbeError("找不到檔案：%s" % path)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except (IOError, OSError) as exc:
        raise ProbeError("讀檔失敗：%s" % exc)
    if not raw:
        raise ProbeError("檔案是空的（0 bytes），沒有東西可以探測。")
    if raw.count(b"\x00") > max(4, len(raw) // 200):
        raise ProbeError("這個檔看起來是二進位檔（含大量 NUL byte），不是 KLARF 文字檔。")

    bom = raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:] if bom else raw
    encoding = "utf-8"
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        encoding = "latin-1 (fallback)"
        text = body.decode("latin-1", "replace")

    crlf = body.count(b"\r\n")
    lf = body.count(b"\n") - crlf
    eol = "CRLF" if crlf and not lf else ("LF" if lf and not crlf else
                                          ("mixed CRLF+LF" if crlf and lf else "none"))
    meta = {"bytes": len(raw), "bom": bom, "encoding": encoding, "eol": eol,
            "lines": body.count(b"\n") + 1}
    hits = [m for m in KLARF_MARKERS if m in text]
    if not hits:
        raise ProbeError(
            "這個檔不像 KLARF（找不到任何 KLARF 關鍵字：%s）。"
            % "/".join(KLARF_MARKERS[:4]))
    meta["markers"] = hits
    return text, meta


# ------------------------------------------------- 版本判定（鏡射 detect_version）

def detect_version(text):
    """回傳 (version, [(名稱, 是否命中, 說明)], 命中的啟發式名稱)。"""
    checks = []
    fired = None
    version = None

    h1 = re.search(r"Record\s+FileRecord", text)
    checks.append(("Record FileRecord", bool(h1), "1.8 的檔頭記錄"))
    if h1 and version is None:
        version, fired = "1.8", "Record FileRecord"

    h2 = re.search(r"FileVersion\s+(\d+)\s+(\d+)", text)
    checks.append(("FileVersion N M", bool(h2),
                   ("宣告 %s.%s" % (h2.group(1), h2.group(2))) if h2 else "無此宣告"))
    if h2 and version is None:
        version, fired = "%s.%s" % (h2.group(1), h2.group(2)), "FileVersion N M"

    h3 = re.search(r"\bList\s+\w+\s*\{", text)
    checks.append(("List XXX {", bool(h3), "1.8 的區塊語法"))
    if h3 and version is None:
        version, fired = "1.8", "List XXX {"

    if version is None:
        version, fired = "1.2", "fallback（以上都沒命中 → 預設 1.2）"
    checks.append(("fallback 1.2", version == "1.2" and fired.startswith("fallback"),
                   "什麼都沒命中時的預設"))
    return version, checks, fired


# ------------------------------------------------- 解析（鏡射 _parse_12 / _parse_18）

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


BLOCK_KEYWORDS = {"DEFECTLIST", "SUMMARYLIST", "ENDOFFILE", "DEFECTRECORDSPEC",
                  "SUMMARYSPEC", "CLASSLOOKUP", "RECORD", "FIELD", "LIST",
                  "COLUMNS", "DATA", "IMAGES", "IMAGE"}


def parse_12(text):
    d = {"header": [], "columns": [], "column_types": [], "rows": [],
         "n_defect_lists": 0, "n_classes": 0, "class_names": [],
         "declared_row_count": None}
    for m in re.finditer(r"(?m)^[ \t]*([A-Za-z][A-Za-z0-9_]*)\b[ \t]+([^;\n]*);", text):
        name, value = m.group(1), m.group(2).strip()
        if name.upper() in BLOCK_KEYWORDS:
            continue
        d["header"].append((name, value))

    m = re.search(r"(?m)^[ \t]*ClassLookup\b[ \t]+(\d+)[ \t]*\r?\n([\s\S]*?);", text)
    if m:
        for line in m.group(2).splitlines():
            cm = re.match(r'\s*(\d+)\s+"([^"]*)"', line)
            if cm:
                d["n_classes"] += 1
                d["class_names"].append(cm.group(2))

    m = re.search(r"DefectRecordSpec\s+(\d+)\s+([^;]+);", text)
    if m:
        d["columns"] = m.group(2).split()
        d["declared_col_count"] = int(m.group(1))
    matches = list(re.finditer(r"(?m)^[ \t]*DefectList\b[ \t]*\r?\n([\s\S]*?);", text))
    d["n_defect_lists"] = len(matches)
    if matches:
        for line in matches[0].group(1).splitlines():
            line = line.strip()
            if line and not line.startswith(";"):
                d["rows"].append(line.split())
    return d


def parse_18(text):
    d = {"header": [], "columns": [], "column_types": [], "rows": [],
         "n_defect_lists": 0, "n_classes": 0, "class_names": [],
         "declared_row_count": None, "imagelist_col": None}
    for m in re.finditer(r"Field\s+(\w+)\s+\d+\s*\{[^}]*\}", text):
        inner = m.group(0)[m.group(0).index("{") + 1:-1].strip()
        d["header"].append((m.group(1), inner))
    rec_field = {"LotRecord": "LotID", "WaferRecord": "WaferID",
                 "DeviceRecord": "DeviceID", "StepRecord": "StepID",
                 "SetupRecord": "SetupID", "FileRecord": "FileVersion"}
    for m in re.finditer(r'Record\s+(\w+Record)\s+("(?:[^"\\]|\\.)*")', text):
        name = rec_field.get(m.group(1))
        if name:
            d["header"].append((name, m.group(2)))

    cl = re.search(r"List\s+ClassLookupList\s*\{", text)
    if cl:
        b0 = text.index("{", cl.start())
        b1 = _find_matching_brace(text, b0)
        body = text[b0 + 1:b1]
        dm = re.search(r"Data\s+\d+\s*\{", body)
        if dm:
            db0 = body.index("{", dm.start())
            db1 = _find_matching_brace(body, db0)
            for row in body[db0 + 1:db1].split(";"):
                cm = re.match(r'\s*(\d+)\s+"([^"]*)"', row)
                if cm:
                    d["n_classes"] += 1
                    d["class_names"].append(cm.group(2))

    dls = list(re.finditer(r"List\s+DefectList\s*\{", text))
    d["n_defect_lists"] = len(dls)
    if dls:
        b0 = text.index("{", dls[0].start())
        b1 = _find_matching_brace(text, b0)
        block = text[b0:b1 + 1]
        cm = re.search(r"Columns\s+(\d+)\s*\{([^}]*)\}", block)
        if cm:
            cols, types = [], []
            for c in cm.group(2).split(","):
                parts = c.strip().split()
                if not parts:
                    continue
                cols.append(parts[-1])
                types.append(parts[0] if len(parts) >= 2 else "?")
                if len(parts) >= 2 and parts[0].lower() == "imagelist":
                    d["imagelist_col"] = len(cols) - 1
            d["columns"] = cols
            d["column_types"] = types
            d["declared_col_count"] = int(cm.group(1))
        dm = re.search(r"Data\s+(\d+)\s*\{", block)
        if dm:
            d["declared_row_count"] = int(dm.group(1))
            db0 = block.index("{", dm.start())
            db1 = _find_matching_brace(block, db0)
            for row in block[db0 + 1:db1].split(";"):
                row = row.strip()
                if row:
                    d["rows"].append(re.findall(r'[^"\s]+|"[^"]*"', row))
    return d


def parse_tiff_fields(text, header):
    """鏡射 _parse_tiff_fields：回傳 (tiff_file_name, tiff_spec, how)。"""
    hd = {}
    for n, v in header:
        hd.setdefault(n, v)
    name = None
    how = None
    m = re.search(r"(?m)^[ \t]*TiffFileName\b[ \t]+([^;]*);", text)
    if m:
        name, how = m.group(1).strip().strip('"'), "1.2 TiffFileName 行"
    elif "TiffFileName" in hd:
        name, how = hd["TiffFileName"].strip().strip('"'), "1.8 Field TiffFileName"
    elif "ImageFileName" in hd:
        q = re.findall(r'"([^"]*)"', hd["ImageFileName"])
        if q:
            name, how = q[0], "1.8 Field ImageFileName"

    spec = None
    m = re.search(r"(?m)^[ \t]*TiffSpec\b[ \t]+([\d.]+)[ \t]+(\d+)[ \t]*([^;]*);", text)
    if m:
        fields = re.findall(r'"([^"]*)"', m.group(3)) or m.group(3).split()
        n = int(m.group(2))
        mismatch = bool(fields) and len(fields) != n
        if mismatch:
            n = len(fields)
        spec = {"version": m.group(1), "nfields": n if n > 0 else None,
                "fields": fields, "source": "1.2 TiffSpec 行", "mismatch": mismatch}
    elif "TiffSpec" in hd:
        vals = re.findall(r'"([^"]*)"', hd["TiffSpec"])
        if vals:
            spec = {"version": vals[0], "nfields": None, "fields": vals[1:],
                    "source": "1.8 Field TiffSpec（欄位是影像類型，不是 token 數）",
                    "mismatch": False}
    return name, spec, how


# ------------------------------------------- 影像佈局（鏡射 image_layout 一族）

def col_index(columns, name):
    up = [c.upper() for c in columns]
    return up.index(name.upper()) if name.upper() in up else -1


def image_col_index(columns, imagelist_col18):
    il = col_index(columns, "IMAGELIST")
    if il < 0 and imagelist_col18 is not None:
        il = imagelist_col18
    return col_index(columns, "IMAGECOUNT"), il


def defect_image_count(row, ic):
    if ic < 0 or ic >= len(row):
        return 0
    try:
        return max(0, int(row[ic]))
    except ValueError:
        return 0


def detect_images18(rows, ic, il):
    """鏡射 _detect_images18。回傳 (layout, 證據字串)。"""
    s = il if il >= 0 else ic + 1
    for k, r in enumerate(rows):
        if defect_image_count(r, ic) > 0:
            if s < len(r) and r[s] == "Images":
                return (s, None, "images18"), \
                    "第一筆帶圖列（第 %d 列）第 %d 欄的 token 正好是 'Images'" % (k, s)
            return None, \
                "第一筆帶圖列（第 %d 列）第 %d 欄不是 'Images'（是 %s 型 token）" % (
                    k, s, token_shape(r[s]) if s < len(r) else "缺欄")
    return None, "沒有任何 IMAGECOUNT > 0 的列"


def infer_image_layout(rows, columns, ic, il):
    """鏡射 _infer_image_layout，另外回傳投票明細當證據。"""
    n = len(columns)
    starts = []
    for s in ([il] if il >= 0 else []) + [n] + ([n - 1] if ic == n - 2 else []):
        if s not in starts:
            starts.append(s)
    cands, evidence = [], []
    for s in starts:
        tally, total = {}, 0
        for r in rows:
            cnt = defect_image_count(r, ic)
            if cnt <= 0:
                continue
            total += 1
            extra = len(r) - s
            if extra > 0 and extra % cnt == 0:
                tally[extra // cnt] = tally.get(extra // cnt, 0) + 1
        if not tally:
            evidence.append("起點欄 %d：沒有任何列的多餘 token 數能被 IMAGECOUNT 整除" % s)
            continue
        nf, votes = max(tally.items(), key=lambda kv: kv[1])
        detail = "、".join("每張圖 %d token → %d 票" % (k, v)
                          for k, v in sorted(tally.items(), key=lambda kv: -kv[1]))
        need = total - max(1, total // 10)
        ok = nf >= 1 and votes >= need
        evidence.append("起點欄 %d：%s（帶圖列共 %d；門檻 %d 票；%s）"
                        % (s, detail, total, need, "通過" if ok else "不通過"))
        if ok:
            cands.append((s, nf, "inferred"))
    if len(cands) <= 1:
        return (cands[0] if cands else None), evidence
    for s, nf, how in cands:
        ids, good = [], True
        for r in rows:
            cnt = defect_image_count(r, ic)
            toks = r[s:]
            if len(toks) < cnt * nf:
                continue
            for k in range(cnt):
                v = toks[k * nf]
                if not v.lstrip("-").isdigit():
                    good = False
                    break
                ids.append(int(v))
            if not good:
                break
        if good and ids and len(set(ids)) == len(ids):
            evidence.append("多個候選 → 選起點欄 %d（首欄像 page 編號：全整數且不重複）" % s)
            return (s, nf, how), evidence
    evidence.append("多個候選且都不像 page 編號 → 取第一個候選")
    return cands[0], evidence


def decide_layout(rows, columns, ic, il, tiff_spec):
    """判定影像佈局變體。回傳 (layout, [證據字串])。

    layout = (起點欄, 每張圖 token 數 或 None, 變體代號)；沒有影像資訊回 None。
    變體代號：images18 / declared / inferred（= klarf_core.image_layout 的三種）
              imagefile（無 IMAGECOUNT 欄、但列中有 Image/Images 子區塊；
                         klarf_core 走 defect_image_filename 這條路）
    """
    ev = []
    if ic >= 0:
        lay18, ev18 = detect_images18(rows, ic, il)
        if lay18 is not None:
            return lay18, ["變體 A（images18）成立：" + ev18]
        ev.append("變體 A（images18）不成立：" + ev18)
        if il >= 0 and tiff_spec and tiff_spec.get("nfields"):
            ev.append("變體 B（declared）成立：有影像清單欄（第 %d 欄）"
                      "且 TiffSpec 宣告每張圖 %d 個 token" % (il, tiff_spec["nfields"]))
            return (il, tiff_spec["nfields"], "declared"), ev
        ev.append("變體 B（declared）不成立：%s"
                  % ("沒有影像清單欄" if il < 0 else "TiffSpec 沒宣告每張圖的 token 數"))
        lay, ev_c = infer_image_layout(rows, columns, ic, il)
        for e in ev_c:
            ev.append("變體 C（inferred）投票：" + e)
        if lay is not None:
            return lay, ev
        return None, ev

    ev.append("沒有 IMAGECOUNT 欄（klarf_core.image_layout() 在這種檔上會回 None）")
    for k, r in enumerate(rows):
        span = find_image_block(r)
        if span is not None:
            ev.append("變體 D（imagefile）成立：第 %d 列的第 %d 欄起有 "
                      "`%s N { ... }` 子區塊，佔 %d 個 token；"
                      "klarf_core 會走 defect_image_filename() 逐列取檔名"
                      % (k, span[0], r[span[0]], span[1] - span[0] + 1))
            return (span[0], None, "imagefile"), ev
    ev.append("列中也找不到 Image/Images 子區塊 → 這份 KLARF 不帶影像資訊")
    return None, ev


def defect_image_entries(row, layout, ic):
    cnt = defect_image_count(row, ic)
    if cnt <= 0 or layout is None:
        return []
    s, nf, how = layout
    if how == "images18":
        m = re.match(r"Images\s+\d+\s*\{(.*)\}\s*$", " ".join(row[s:]))
        if not m:
            return []
        entries = [e.split() for e in m.group(1).split(",") if e.strip()]
        return entries if len(entries) == cnt else []
    toks = row[s:]
    if len(toks) < cnt * nf:
        return []
    return [toks[k * nf:(k + 1) * nf] for k in range(cnt)]


def row_len_ok(row, columns, layout, ic, il):
    """鏡射 row_len_ok。"""
    n = len(columns)
    if ic < 0:
        return len(row) == n
    cnt = defect_image_count(row, ic)
    if layout is not None:
        s, nf, how = layout
        if how == "images18":
            if cnt <= 0:
                tail = " ".join(row[s:]).strip()
                return (len(row) in ({s, n} if s < n else {n})
                        or bool(re.match(r"^Images\s+0\s*\{\s*\}$", tail)))
            return len(defect_image_entries(row, layout, ic)) == cnt
        if cnt <= 0:
            return len(row) in ({s, n} if s < n else {n})
        return len(row) == s + cnt * nf
    base = n - (1 if il >= 0 else 0)
    if cnt <= 0:
        return len(row) in (base, n)
    if il >= 0:
        return len(row) >= base + cnt
    return len(row) == n


def aligned_len(row, layout, ic):
    """把「影像欄」不論多長都算成一欄之後，這一列相當於幾欄。

    用來和宣告的欄位數比對 —— 這是比 klarf_core.row_len_ok() 更寬鬆、
    但更貼近「列到底有沒有對齊欄位」的判準。
    """
    span = find_image_block(row)
    if span is not None:
        return len(row) - (span[1] - span[0] + 1) + 1
    if layout is not None and layout[2] in ("declared", "inferred"):
        s, nf, _how = layout
        cnt = defect_image_count(row, ic)
        if cnt > 0:
            return s + 1 if len(row) == s + cnt * nf else len(row)
        return s + 1 if len(row) == s else len(row)
    return len(row)


def sibling_tiff(klarf_path, tiff_file_name):
    """鏡射 tiff_path 的候選順序；回傳 (找到的路徑, [(候選描述, 是否存在)])。"""
    cands, tried = [], []
    base_dir = os.path.dirname(os.path.abspath(klarf_path))
    if tiff_file_name:
        nm = tiff_file_name.replace("\\", "/")
        cands.append((nm, "TiffFileName 原樣（絕對或相對 cwd）"))
        cands.append((os.path.join(base_dir, os.path.basename(nm)),
                      "TiffFileName 的檔名 + KLARF 同資料夾"))
    stem = os.path.splitext(klarf_path)[0]
    for p, tag in ((stem, "KLARF 去副檔名"), (klarf_path, "KLARF 全名")):
        for ext in (".tif", ".tiff", ".TIF", ".TIFF"):
            cands.append((p + ext, "%s + %s" % (tag, ext)))
    found, seen = None, set()
    for path, desc in cands:
        if not path or path in seen:
            continue
        seen.add(path)
        exists = os.path.isfile(path)
        tried.append((desc, exists))
        if exists and found is None:
            found = path
    return found, tried


# ---------------------------------------------------------------- 報告

def emit_header(path, meta, include_ids):
    _out("=" * 74)
    _out("ADEPT 廠內探測報告 #1：KLARF 結構（probe_klarf.py v%s）" % PROBE_VERSION)
    _out("=" * 74)
    _out("")
    _out("【這份報告包含什麼】")
    _out("  - KLARF 版本判定、header 欄位『名稱』清單、defect 欄位名與型別")
    _out("  - 列數、每張圖佔幾個 token、影像佈局變體判定與其證據")
    _out("  - 各種統計數字（列長分布、每顆 defect 影像張數分布、異常列的索引）")
    _out("【這份報告不包含什麼】")
    _out("  - 不含任何 defect 資料 token（座標 XREL/YREL/XINDEX 一個都不印，連範圍都不印）")
    _out("  - 不含 LotID / WaferID / DeviceID / StepID 等識別碼的值（只印欄位名）")
    _out("  - 不含檔名原文（只印副檔名與字元數）、不含 class 名稱、不含任何影像像素")
    if include_ids:
        _out("")
        _out("  ** 注意：本次以 --include-ids 執行 → 上述識別碼『會』照原樣輸出。**")
        _out("  ** 請先確認公司資料攜出規範允許，再把這份報告貼出廠外。 **")
    _out("")
    _out("-" * 74)
    _out("1. 檔案基本資訊")
    _out("-" * 74)
    _out("  檔名        : %s" % redact_name(path, include_ids))
    _out("  大小        : %d bytes" % meta["bytes"])
    _out("  行數        : %d" % meta["lines"])
    _out("  換行        : %s" % meta["eol"])
    _out("  編碼        : %s%s" % (meta["encoding"], "（含 BOM）" if meta["bom"] else ""))
    _out("  KLARF 關鍵字: %s" % ", ".join(meta["markers"]))
    _out("")


def emit_version(version, checks, fired):
    _out("-" * 74)
    _out("2. 版本判定（鏡射 klarf_core.detect_version 的順序）")
    _out("-" * 74)
    _out("  判定結果    : %s" % version)
    _out("  由哪條命中  : %s" % fired)
    _out("  各啟發式    :")
    for name, hit, note in checks:
        _out("    [%s] %-20s %s" % ("V" if hit else " ", name, note))
    if version not in ("1.2", "1.8"):
        _out("  ** 這個版本字串 ADEPT 沒看過（只處理過 1.2 / 1.8）→ 請務必回報。**")
    _out("")


def emit_header_fields(d, include_ids):
    _out("-" * 74)
    _out("3. Header 欄位（名稱全列，值預設遮蔽）")
    _out("-" * 74)
    seen, unknown = [], []
    _out("  %-30s %-6s %s" % ("欄位名", "klarf", "值"))
    for name, value in d["header"]:
        if name in seen:
            continue
        seen.append(name)
        known = name.upper() in KNOWN_FIELDS
        if not known:
            unknown.append(name)
        _out("  %-30s %-6s %s" % (name, "known" if known else "NEW",
                                  redact(value, name, include_ids)))
    if not seen:
        _out("  （解不出任何 header 欄位 —— 這本身就值得回報）")
    _out("")
    _out("  欄位總數 %d，其中 klarf_core 未涵蓋（NEW）%d 個：%s"
         % (len(seen), len(unknown), ", ".join(unknown) if unknown else "無"))
    _out("  ClassLookup 類別數：%d%s"
         % (d["n_classes"],
            ("（名稱：%s）" % ", ".join(d["class_names"][:20])) if include_ids else "（名稱已遮蔽）"))
    _out("")
    return seen, unknown


def infer_col_type(rows, idx, limit):
    kinds = set()
    for r in rows[:limit]:
        if idx >= len(r):
            continue
        kinds.add(token_shape(r[idx]))
    if not kinds:
        return "?"
    if kinds == {"d"}:
        return "int"
    if kinds <= {"d", "f"}:
        return "float"
    if kinds == {"s"}:
        return "string"
    if kinds == {"w"}:
        return "word"
    return "/".join(sorted(kinds))


def emit_columns(d, ic, il, rows_limit):
    _out("-" * 74)
    _out("4. Defect 欄位與列數")
    _out("-" * 74)
    cols = d["columns"]
    declared = d.get("declared_col_count")
    _out("  欄位數      : %d%s" % (len(cols),
         ("（宣告 %d%s）" % (declared, "，不一致！" if declared != len(cols) else "")
          if declared is not None else "")))
    _out("  DefectList  : %d 個（>1 表示多 test，klarf_core 只吃第一個）" % d["n_defect_lists"])
    _out("  列數        : %d%s" % (len(d["rows"]),
         ("（Data 宣告 %d%s）" % (d["declared_row_count"],
                                "，不一致！" if d["declared_row_count"] != len(d["rows"]) else "")
          if d.get("declared_row_count") is not None else "")))
    _out("")
    _out("  （推斷型別是把 `Image/Images N { … }` 子區塊壓成一個 token 後才對欄的，")
    _out("    所以影像欄之後的欄位也對得起來；d=整數 f=浮點 s=字串 w=字）")
    _out("  %-4s %-24s %-10s %-10s %s" % ("#", "欄位名", "宣告型別", "推斷型別", "備註"))
    collapsed = d["rows_collapsed"]
    for i, c in enumerate(cols):
        dt = d["column_types"][i] if i < len(d["column_types"]) else "-"
        note = []
        if i == ic:
            note.append("<- IMAGECOUNT")
        if i == il:
            note.append("<- 影像清單欄（變動長度）")
        _out("  %-4d %-24s %-10s %-10s %s"
             % (i, c, dt, infer_col_type(collapsed, i, rows_limit), " ".join(note)))
    if not cols:
        _out("  （解不出欄位清單 —— 請回報）")
    _out("")


def emit_image_layout(d, tiff_name, tiff_spec, spec_how, layout, evidence,
                      ic, il, rows_limit, klarf_path, include_ids):
    _out("-" * 74)
    _out("5. 影像佈局變體（**假設 #3：本報告最重要的一段**）")
    _out("-" * 74)
    _out("  IMAGECOUNT 欄索引 : %s" % (ic if ic >= 0 else "無"))
    _out("  影像清單欄索引    : %s%s" % (
        il if il >= 0 else "無",
        ("（欄名 %s）" % d["columns"][il]) if 0 <= il < len(d["columns"]) else ""))
    if tiff_spec:
        _out("  TiffSpec          : version=%s nfields=%s fields=%s（來源：%s）%s"
             % (tiff_spec["version"], tiff_spec["nfields"],
                ",".join(tiff_spec["fields"]) or "-", tiff_spec["source"],
                "  ** 宣告數與實際列出的欄位數不一致 **" if tiff_spec.get("mismatch") else ""))
    else:
        _out("  TiffSpec          : 無")
    how = layout[2] if layout else "none"
    variant = {
        "images18": "變體 A：IMAGECOUNT 欄 + 結構化 `Images N { … }` 子區塊（images18）",
        "declared": "變體 B：IMAGELIST 欄 + TiffSpec 宣告每張圖的 token 數（declared）",
        "inferred": "變體 C：從資料推斷每張圖的 token 數（inferred）",
        "imagefile": "變體 D：沒有 IMAGECOUNT 欄，但列中有 `Image/Images N { \"檔名\" … }` 子區塊"
                     "（imagefile；klarf_core 走 defect_image_filename）",
        "none": "**（四種已知變體都不成立）**"}[how]
    _out("")
    _out("  判定變體          : %s" % variant)
    if layout:
        _out("  影像條目起點欄    : %d" % layout[0])
        _out("  每張圖 token 數   : %s" % (layout[1] if layout[1] is not None else "不定（子區塊）"))
    _out("  證據              :")
    for e in evidence:
        _out("    - %s" % e)
    if how == "none" and (il >= 0 or any(find_image_block(r) for r in d["rows"])):
        _out("")
        _out("  ** 這份 KLARF 看起來帶影像資訊，卻不符合任何一種已知變體 ——")
        _out("     這就是要找的『新花樣』，請務必連同下面的列尾樣式一起回報。**")
    elif how == "none":
        _out("")
        _out("  → 這份 KLARF 不帶影像資訊（沒有 IMAGECOUNT 欄、也沒有 Image 子區塊）。")

    # 帶圖列的 token 型別樣式（無內容）
    _out("")
    _out("  帶圖列的列尾樣式（token 型別，d=整數 f=浮點 s=字串 w=字 {}=括號；無任何內容）：")
    shown = 0
    for k, r in enumerate(d["rows"]):
        has_img = defect_image_count(r, ic) > 0 or find_image_block(r) is not None
        if not has_img:
            continue
        start = max(0, (layout[0] if layout else len(d["columns"])) - 2)
        _out("    列 %-5d 全長 %-4d 從第 %d 欄起: %s"
             % (k, len(r), start, shape_line(r[start:])))
        shown += 1
        if shown >= min(3, rows_limit):
            break
    if shown == 0:
        _out("    （沒有任何帶圖的列）")
    _out("")

    # 每顆 defect 影像張數分布
    counts = {}
    total_imgs = 0
    for r in d["rows"]:
        if ic >= 0:
            c = defect_image_count(r, ic)
        else:                                 # 變體 D：以子區塊有無代表 0/1 張
            c = 1 if find_image_block(r) is not None else 0
        counts[c] = counts.get(c, 0) + 1
        total_imgs += c
    _out("  每顆 defect 的影像張數（%s）分布：" % ("IMAGECOUNT 欄" if ic >= 0 else "有無影像子區塊"))
    for line in histogram_lines(counts):
        _out(line)
    _out("  影像總張數        : %d（defect 列數 %d）" % (total_imgs, len(d["rows"])))
    uniq = sorted(counts.keys())
    if uniq == [2]:
        _out("  → 每顆 defect 都是 2 張：與 ADEPT 目前的 test/ref 成對假設一致（假設 #1）。")
        _out("    但「哪一張是 test、哪一張是 ref」要靠 probe_tiff.py 的頁面資訊確認。")
    elif uniq == [1]:
        _out("  → 每顆 defect 都是 1 張：Review SEM 型（單張，無 ref）。")
    elif uniq == [0]:
        _out("  → 沒有任何 defect 帶圖。")
    else:
        _out("  → 張數不一致（%s）：ADEPT 的 test/ref 成對假設在這份檔上不成立，請回報。"
             % ",".join(str(u) for u in uniq))
    _out("")

    # 每顆 defect 一個獨立影像檔（變體 A/D 常見）→ 只報副檔名與存在與否
    names = [block_filename(r) for r in d["rows"]]
    names = [n for n in names if n]
    n_files_exist = 0
    exts = {}
    if names:
        base_dir = os.path.dirname(os.path.abspath(klarf_path))
        for nm in names:
            ext = os.path.splitext(nm)[1].lower() or "(無副檔名)"
            exts[ext] = exts.get(ext, 0) + 1
            if os.path.isfile(os.path.join(base_dir, nm.replace("\\", "/"))):
                n_files_exist += 1
        _out("  列尾帶檔名的列    : %d / %d（副檔名分布：%s）"
             % (len(names), len(d["rows"]),
                ", ".join("%s x%d" % (k, v) for k, v in sorted(exts.items()))))
        _out("  以 KLARF 所在資料夾為基準，實際找得到的檔案：%d / %d"
             % (n_files_exist, len(names)))
        if n_files_exist == 0:
            _out("  ** 一個都找不到 → 影像可能放在別的資料夾（相對路徑基準不同），請回報。**")
        _out("")

    # 對應的 TIFF
    _out("  TiffFileName      : %s%s"
         % (redact_name(tiff_name, include_ids) if tiff_name else "無",
            ("（來源：%s）" % spec_how) if spec_how else ""))
    found, tried = sibling_tiff(klarf_path, tiff_name)
    for desc, exists in tried:
        _out("    [%s] %s" % ("找到" if exists else "沒有", desc))
    if found:
        _out("  → 使用: %s（%d bytes）" % (redact_name(found, include_ids),
                                          os.path.getsize(found)))
        _out("  → 請對這個 TIFF 再跑一次 probe_tiff.py（假設 #1）。")
    else:
        _out("  → 找不到同伴 TIFF。若影像其實是每顆 defect 一個獨立檔（Review SEM 型），這是正常的。")
    _out("")
    return {"total_images": total_imgs, "counts": counts, "tiff_found": found,
            "n_named": len(names), "n_named_exist": n_files_exist, "exts": exts}


def emit_row_anomalies(d, layout, ic, il, rows_limit):
    _out("-" * 74)
    _out("6. 列長異常（只報索引與數量，不報內容）")
    _out("-" * 74)
    n = len(d["columns"])
    lens, clens = {}, {}
    bad, bad_c = [], []
    for k, r in enumerate(d["rows"]):
        lens[len(r)] = lens.get(len(r), 0) + 1
        al = aligned_len(r, layout, ic)
        clens[al] = clens.get(al, 0) + 1
        if not row_len_ok(r, d["columns"], layout, ic, il):
            bad.append(k)
        if al != n:
            bad_c.append(k)
    _out("  原始列長分布（token 數 : 列數）：")
    for line in histogram_lines(lens):
        _out(line)
    _out("  影像欄不論多長都算一欄之後的列長分布（宣告欄位數 = %d）：" % n)
    for line in histogram_lines(clens):
        _out(line)
    _out("")
    _out("  klarf_core.row_len_ok() 判為不合法：%d / %d" % (len(bad), len(d["rows"])))
    if bad:
        _out("    前幾筆索引：%s%s"
             % (", ".join(str(b) for b in bad[:rows_limit]),
                " ..." if len(bad) > rows_limit else ""))
    _out("  對齊欄位數（影像欄算一欄後的長度 != %d）判為不合法：%d / %d"
         % (n, len(bad_c), len(d["rows"])))
    if bad_c:
        _out("    前幾筆索引：%s%s"
             % (", ".join(str(b) for b in bad_c[:rows_limit]),
                " ..." if len(bad_c) > rows_limit else ""))
    if bad and not bad_c:
        _out("  → 兩者不一致：列其實對得起欄位數，是 klarf_core 的 row_len_ok()")
        _out("    對這種變體判得太嚴（已知落差，不是檔案有問題）。請回報這一行。")
    elif bad_c:
        _out("  ** 真的有列對不上欄位數 → 佈局判定可能不對，請連同第 5 段一起回報。**")
    _out("")
    return len(bad), bad[:rows_limit], len(bad_c), bad_c[:rows_limit]


def emit_nm_hunt(d, include_ids, rows_limit):
    _out("-" * 74)
    _out("7. nm_per_px 獵捕（**假設 #2**：名稱看起來可能帶像素尺寸/比例尺/倍率的欄位）")
    _out("-" * 74)
    hits = []

    def match(name):
        up = name.upper()
        tags = [tag for tag, pat in NM_PATTERNS if re.search(pat, up)]
        return tags

    _out("  [header 欄位]")
    n = 0
    for name, value in d["header"]:
        tags = match(name)
        if not tags:
            continue
        n += 1
        hits.append(name)
        if name.upper() in ID_FIELDS and not include_ids:
            shown = "<redacted, %d chars>（名稱同時像識別碼 → 仍遮蔽）" % len(str(value))
        else:
            v = str(value)
            shown = v if len(v) <= 80 else v[:80] + "...(截斷)"
        _out("    %-28s [%s] = %s" % (name, ",".join(tags), shown))
    if n == 0:
        _out("    （沒有名稱像像素尺寸的 header 欄位）")

    _out("  [defect 欄位]（只報值域統計，不報逐列值）")
    m = 0
    for i, c in enumerate(d["columns"]):
        tags = match(c)
        if not tags:
            continue
        m += 1
        hits.append(c)
        vals = []
        for r in d["rows"]:
            if i < len(r):
                vals.append(r[i])
        nums = []
        for v in vals:
            try:
                nums.append(float(v))
            except ValueError:
                pass
        uniq = sorted(set(vals))
        if nums and len(nums) == len(vals):
            stat = "min=%g max=%g 相異值=%d" % (min(nums), max(nums), len(uniq))
            if len(uniq) <= 5:
                stat += "（值：%s）" % ", ".join(uniq)
        else:
            stat = "非數值或混合；相異值=%d" % len(uniq)
        _out("    #%-3d %-24s [%s] %s" % (i, c, ",".join(tags), stat))
    if m == 0:
        _out("    （沒有名稱像像素尺寸的 defect 欄位）")
    _out("")
    _out("  ** 若上面沒有任何一個欄位真的帶 nm/pixel，代表 nm_per_px 不在 KLARF 裡 —— **")
    _out("  ** 請接著看 probe_tiff.py 的 ImageDescription / Software / Resolution 標籤。 **")
    _out("")
    return hits


def emit_json(summary):
    _out("=" * 74)
    _out("請回報這一段（以下整段是機器可讀摘要，可安全貼出；不含任何識別碼與座標）")
    _out("=" * 74)
    _out(">>>JSON_BEGIN")
    for line in json_block(summary):
        _out(line)
    _out(">>>JSON_END")


# ---------------------------------------------------------------- main

def run(path, include_ids=False, rows_limit=20):
    text, meta = read_text(path)
    version, checks, fired = detect_version(text)
    d = parse_18(text) if version == "1.8" else parse_12(text)
    d.setdefault("imagelist_col", None)
    d.setdefault("declared_col_count", None)
    tiff_name, tiff_spec, spec_how = parse_tiff_fields(text, d["header"])

    d["rows_collapsed"] = [collapse_row(r) for r in d["rows"]]
    ic, il = image_col_index(d["columns"], d.get("imagelist_col"))
    layout, evidence = decide_layout(d["rows"], d["columns"], ic, il, tiff_spec)

    emit_header(path, meta, include_ids)
    emit_version(version, checks, fired)
    names, unknown = emit_header_fields(d, include_ids)
    emit_columns(d, ic, il, rows_limit)
    img = emit_image_layout(d, tiff_name, tiff_spec, spec_how, layout, evidence,
                            ic, il, rows_limit, path, include_ids)
    n_bad, bad_idx, n_bad_c, bad_idx_c = emit_row_anomalies(
        d, layout, ic, il, rows_limit)
    nm_hits = emit_nm_hunt(d, include_ids, rows_limit)

    summary = {}
    summary["schema"] = SCHEMA
    summary["probe_version"] = PROBE_VERSION
    summary["file_bytes"] = meta["bytes"]
    summary["eol"] = meta["eol"]
    summary["encoding"] = meta["encoding"]
    summary["klarf_version"] = version
    summary["version_heuristic"] = fired
    summary["n_header_fields"] = len(names)
    summary["header_fields"] = names
    summary["header_fields_new"] = unknown
    summary["n_classes"] = d["n_classes"]
    summary["n_defect_columns"] = len(d["columns"])
    summary["defect_columns"] = d["columns"]
    summary["defect_column_types"] = d["column_types"]
    summary["n_defect_rows"] = len(d["rows"])
    summary["n_defect_lists"] = d["n_defect_lists"]
    summary["declared_row_count"] = d.get("declared_row_count")
    summary["imagecount_col"] = ic
    summary["imagelist_col"] = il
    summary["image_layout_variant"] = layout[2] if layout else "none"
    summary["image_layout_start_col"] = layout[0] if layout else None
    summary["image_layout_nfields"] = layout[1] if layout else None
    summary["tiffspec"] = ({"version": tiff_spec["version"],
                            "nfields": tiff_spec["nfields"],
                            "fields": tiff_spec["fields"]} if tiff_spec else None)
    summary["imagecount_distribution"] = dict(
        (str(k), v) for k, v in sorted(img["counts"].items()))
    summary["total_images"] = img["total_images"]
    summary["n_rows_with_image_filename"] = img["n_named"]
    summary["n_image_files_found"] = img["n_named_exist"]
    summary["image_file_extensions"] = img["exts"]
    summary["tiff_referenced"] = bool(tiff_name)
    summary["tiff_exists"] = bool(img["tiff_found"])
    summary["row_length_anomalies_klarf_core"] = n_bad
    summary["row_length_anomaly_index"] = bad_idx
    summary["row_length_anomalies_aligned"] = n_bad_c
    summary["row_length_anomaly_index_aligned"] = bad_idx_c
    summary["nm_per_px_candidates"] = nm_hits
    summary["ids_included"] = bool(include_ids)
    emit_json(summary)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="ADEPT 廠內探測 #1：KLARF 結構（單檔、純標準函式庫、不讀像素）")
    ap.add_argument("klarf", help="要探測的 KLARF 檔（例：C:\\path\\to\\file.klarf）")
    ap.add_argument("--include-ids", action="store_true",
                    help="連 LotID/WaferID/DeviceID 等識別碼的值一起輸出（預設遮蔽）")
    ap.add_argument("--rows", type=int, default=20,
                    help="取樣列數上限（型別推斷、樣式與異常索引列出的筆數，預設 20）")
    args = ap.parse_args(argv)
    try:
        return run(args.klarf, args.include_ids, max(1, args.rows))
    except ProbeError as exc:
        sys.stderr.write("錯誤：%s\n" % exc)
        return 2
    except Exception as exc:                      # noqa: BLE001 - 廠內不該看到 traceback
        sys.stderr.write("錯誤：探測失敗（%s: %s）。請把這行連同檔案大小回報。\n"
                         % (type(exc).__name__, exc))
        return 3


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(errors="replace")      # Python 3.7+；舊版忽略
        except Exception:
            pass
    sys.exit(main())

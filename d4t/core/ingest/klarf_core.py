# Vendored into d4t on 2026-07-27.
# Source project: KLIP — file: klarf_core.py (KLARF 1.2/1.8 lossless engine).
# Adaptations:
#   - added `from __future__ import annotations` (d4t convention)
#   - added ONE additive method KlarfDoc.defect_image_filename(row): returns
#     the per-defect image filename for rows whose image tail carries an
#     `Image/Images N { "file" ... }` block (concept ported from GLAS
#     glas/core/klarf_parser.py `_map_row_tokens` / `_image_filename`,
#     re-expressed on klarf_core's raw-token row representation)
#   - KlarfDoc.save() writes atomically (.tmp + os.replace) instead of
#     straight into the target — d4t 鐵則 5, and a truncated KLARF would
#     overwrite the only copy of the fab's raw data (2026-08-24)
#   - no other changes; parse / lossless round-trip behavior is identical
#     to upstream (Chinese docstrings/comments kept verbatim).
"""
klarf_core.py
KLARF 1.2 / 1.8 讀取 + 就地編輯引擎（UI 與檔案格式之間的那一層）

核心原則：span-splice 無損寫回
  - 沒被使用者改到的部分，to_text() 寫回時與原檔「逐位元組相同」。
  - 只有被編輯的區塊（某個 header 欄位、DefectList）才重新產生。
  - 需要的 count（1.8 的 Data N）自動重算；不確定意義的 count（1.2 的
    ClassLookup 數字）一律原樣保留，絕不亂算。

單位備忘：
  - 1.2：座標/尺寸為「微米 µm 浮點」
  - 1.8：座標/尺寸為「奈米 nm 整數」（= µm × 1000）
  引擎內部一律以「原始字串 token」保存 defect 表，不做數值換算，
  單位換算/顯示交給 UI 層處理，避免任何精度漂移。
"""
from __future__ import annotations

import os
import re


# ---------------------------------------------------------------- 小工具

def _find_matching_brace(text, open_idx):
    """從 text[open_idx] 的 '{' 找出成對的 '}' 索引；找不到回 -1。"""
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
    return -1


def detect_version(text):
    """回傳 '1.8' / '1.2'（或 FileVersion 指定的字串）。"""
    if re.search(r'Record\s+FileRecord', text):
        return '1.8'
    m = re.search(r'FileVersion\s+(\d+)\s+(\d+)', text)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    if re.search(r'\bList\s+\w+\s*\{', text):
        return '1.8'
    return '1.2'


# 1.8 的記錄名稱 → 對應到 1.2 的 header 欄位名
REC_FIELD = {
    'LotRecord': 'LotID',
    'WaferRecord': 'WaferID',
    'DeviceRecord': 'DeviceID',
    'StepRecord': 'StepID',
    'SetupRecord': 'SetupID',
    'FileRecord': 'FileVersion',
}

UNIT_INFO = {
    '1.2': {'coord_unit': 'µm', 'coord_type': 'float', 'to_nm': 1000.0},
    '1.8': {'coord_unit': 'nm', 'coord_type': 'int',   'to_nm': 1.0},
}


# ---------------------------------------------------------------- 主類別

class KlarfDoc:
    """一份 KLARF 檔的可編輯模型。UI 對 1.2 / 1.8 用同一組介面操作。"""

    # 1.2 常見的單行 header 欄位（可編輯）；未列出的欄位會被原樣保留
    FIELDS_12 = [
        "FileVersion", "FileTimestamp", "InspectionStationID", "SampleType",
        "ResultTimestamp", "LotID", "SampleSize", "DeviceID", "SetupID",
        "StepID", "SampleOrientationMarkType", "OrientationMarkLocation",
        "DiePitch", "DieOrigin", "WaferID", "Slot", "ScribeID",
        "SampleCenterLocation",
    ]

    def __init__(self, text, source_path=None):
        self._text = text
        self.source_path = source_path
        self.version = detect_version(text)
        self._is18 = (self.version == '1.8')
        self.warnings = []
        self.summary_stale = False
        self.auto_recompute_summary = False  # 決策：SummaryList 一律維持原樣，不自動重算
                                             #（DefectList 常是子集、summary 是全量，重算會洗掉真數字）

        # summary（目前 1.2 支援自動重算；1.8 待真檔）
        self._summary_columns = []
        self._summary_rows = []
        self._summary_orig = None

        # 可編輯元素
        self._header = {}            # name -> {"orig":原字串, "value":現值, "dirty":bool}
        self.class_lookup = {}       # code(int) -> name(str)
        self._classlookup_orig = None
        self._classlookup_dirty = False
        self.defect_columns = []     # 欄位名 list
        self.defects = []            # list[list[str]]，原始 token
        self._defect_dirty = False
        self._defect_orig = None     # 原始 DefectList / Data 區塊字串（供 replace-once）

        # patch 影像（帶圖 KLARF）：TiffFileName 指到多頁 TIFF，
        # TiffSpec 宣告 IMAGELIST 每張圖佔幾個 token
        self.tiff_file_name = None   # 原始字串（可能含 Windows 路徑）
        self.tiff_spec = None        # {"version": str, "nfields": int|None, "fields": [str]}
        self._img_layout = 'unset'   # 快取：(start_col, nfields, how) 或 None
        self._il18 = None            # 1.8：型別為 ImageList 的欄位索引（名稱不限）

        if self._is18:
            self._parse_18()
        else:
            self._parse_12()
        self._parse_tiff_fields()

    # ---------- 對外唯讀資訊 ----------

    def unit_info(self):
        return UNIT_INFO.get(self.version, UNIT_INFO['1.2'])

    def header_items(self):
        """回傳 [(name, value_str), ...] 給 UI 顯示/編輯。"""
        return [(n, h["value"]) for n, h in self._header.items()]

    def col_index(self, name):
        up = [c.upper() for c in self.defect_columns]
        return up.index(name.upper()) if name.upper() in up else -1

    # ---------- 解析 1.2 ----------

    def _parse_12(self):
        t = self._text
        for name in self.FIELDS_12:
            m = re.search(rf'(?m)^[ \t]*{name}\b[ \t]+([^;]*);', t)
            if m:
                self._header[name] = {"orig": m.group(0),
                                      "value": m.group(1).strip(),
                                      "dirty": False}
        # ClassLookup：保留原本那個數字（它常是 class 檔總數，不是列數）
        m = re.search(r'(?m)^[ \t]*ClassLookup\b[ \t]+\d+[ \t]*\r?\n([\s\S]*?);', t)
        if m:
            self._classlookup_orig = m.group(0)
            for line in m.group(1).splitlines():
                cm = re.match(r'\s*(\d+)\s+"([^"]*)"', line)
                if cm:
                    self.class_lookup[int(cm.group(1))] = cm.group(2)

        m = re.search(r'DefectRecordSpec\s+\d+\s+([^;]+);', t)
        if m:
            self.defect_columns = m.group(1).split()

        matches = list(re.finditer(r'(?m)^[ \t]*DefectList\b[ \t]*\r?\n([\s\S]*?);', t))
        if len(matches) > 1:
            self.warnings.append(
                f"Detected {len(matches)} DefectLists (multi-test); only the first is editable.")
        if matches:
            self._defect_orig = matches[0].group(0)
            for line in matches[0].group(1).splitlines():
                line = line.strip()
                if line and not line.startswith(';'):
                    self.defects.append(line.split())

        # SummarySpec / SummaryList
        m = re.search(r'SummarySpec\s+\d+\s+([^;]+);', t)
        if m:
            self._summary_columns = m.group(1).split()
        m = re.search(r'(?m)^[ \t]*SummaryList\b[ \t]*\r?\n([\s\S]*?);', t)
        if m:
            self._summary_orig = m.group(0)
            for line in m.group(1).splitlines():
                line = line.strip()
                if line and not line.startswith(';'):
                    self._summary_rows.append(line.split())

    # ---------- 解析 1.8 ----------

    def _parse_18(self):
        t = self._text
        for m in re.finditer(r'Field\s+(\w+)\s+\d+\s*\{[^}]*\}', t):
            name = m.group(1)
            if name not in self._header:
                inner = m.group(0)[m.group(0).index('{') + 1:-1].strip()
                self._header[name] = {"orig": m.group(0), "value": inner, "dirty": False}

        # 1.8 把 LotID / WaferID 等放在 Record 的名稱上（例：Record LotRecord "N9S641.06"），
        # 不是 Field，所以另外抓出來，讓 Header 頁能和 1.2 一樣檢視／編輯。
        for m in re.finditer(r'Record\s+(\w+Record)\s+("(?:[^"\\]|\\.)*")', t):
            rec = m.group(1)
            name = REC_FIELD.get(rec)
            if name and name not in self._header:
                self._header[name] = {"orig": m.group(0), "value": m.group(2),
                                      "dirty": False, "rec": True}

        cl = re.search(r'List\s+ClassLookupList\s*\{', t)
        if cl:
            b0 = t.index('{', cl.start())
            b1 = _find_matching_brace(t, b0)
            body = t[b0 + 1:b1]
            dm = re.search(r'Data\s+\d+\s*\{', body)
            if dm:
                db0 = body.index('{', dm.start())
                db1 = _find_matching_brace(body, db0)
                for row in body[db0 + 1:db1].split(';'):
                    cm = re.match(r'\s*(\d+)\s+"([^"]*)"', row)
                    if cm:
                        self.class_lookup[int(cm.group(1))] = cm.group(2)

        dls = list(re.finditer(r'List\s+DefectList\s*\{', t))
        if len(dls) > 1:
            self.warnings.append(
                f"Detected {len(dls)} DefectLists; only the first is editable.")
        if dls:
            b0 = t.index('{', dls[0].start())
            b1 = _find_matching_brace(t, b0)
            block = t[b0:b1 + 1]
            cm = re.search(r'Columns\s+\d+\s*\{([^}]*)\}', block)
            if cm:
                cols = []
                for c in cm.group(1).split(','):
                    parts = c.strip().split()
                    cols.append(parts[-1] if parts else c.strip())
                    # 影像欄常不叫 IMAGELIST（例：ImageList ImageInfo），記型別位置
                    if len(parts) >= 2 and parts[0].lower() == 'imagelist':
                        self._il18 = len(cols) - 1
                self.defect_columns = cols
            dm = re.search(r'Data\s+\d+\s*\{', block)
            if dm:
                db0 = block.index('{', dm.start())
                db1 = _find_matching_brace(block, db0)
                self._defect_orig = block[dm.start():db1 + 1]   # 'Data N { ... }'
                for row in block[db0 + 1:db1].split(';'):
                    row = row.strip()
                    if row:
                        self.defects.append(re.findall(r'[^"\s]+|"[^"]*"', row))

    # ---------- 解析 TIFF patch 影像欄位 ----------

    def _parse_tiff_fields(self):
        t = self._text
        # 1.2：TiffFileName xxx; / TiffSpec 6.1 2 "IMAGEVERSION" "IMAGEXYPOS";
        m = re.search(r'(?m)^[ \t]*TiffFileName\b[ \t]+([^;]*);', t)
        if m:
            self.tiff_file_name = m.group(1).strip().strip('"')
        elif 'TiffFileName' in self._header:      # 1.8 放在 Field 裡
            self.tiff_file_name = self._header['TiffFileName']["value"].strip().strip('"')
        elif 'ImageFileName' in self._header:     # 1.8：Field ImageFileName {"x.tif", "TIF"}
            q = re.findall(r'"([^"]*)"', self._header['ImageFileName']["value"])
            if q:
                self.tiff_file_name = q[0]
        m = re.search(r'(?m)^[ \t]*TiffSpec\b[ \t]+([\d.]+)[ \t]+(\d+)[ \t]*([^;]*);', t)
        if m:
            fields = re.findall(r'"([^"]*)"', m.group(3)) or m.group(3).split()
            n = int(m.group(2))
            if fields and len(fields) != n:
                self.warnings.append(
                    f"TiffSpec declares {n} fields but lists {len(fields)}; using {len(fields)}.")
                n = len(fields)
            if n > 0:
                self.tiff_spec = {"version": m.group(1), "nfields": n, "fields": fields}
        elif 'TiffSpec' in self._header:          # 1.8：Field TiffSpec {"6.0", "G", "R"}
            vals = re.findall(r'"([^"]*)"', self._header['TiffSpec']["value"])
            if vals:
                # 這裡的欄位是「影像類型」（例：G/R），不是每張圖的 token 數
                self.tiff_spec = {"version": vals[0], "nfields": None, "fields": vals[1:]}

    # ---------- TIFF patch 影像對應 ----------

    def image_col_index(self):
        """回傳 (IMAGECOUNT 欄索引, 影像清單欄索引)；沒有為 -1。
           影像清單欄優先找名為 IMAGELIST 的欄，其次是 1.8 型別為
           ImageList 的欄（名稱不限，例：ImageInfo）。"""
        il = self.col_index('IMAGELIST')
        if il < 0 and self._il18 is not None:
            il = self._il18
        return self.col_index('IMAGECOUNT'), il

    def defect_image_count(self, row):
        ic, _ = self.image_col_index()
        if ic < 0 or ic >= len(row):
            return 0
        try:
            return max(0, int(row[ic]))
        except ValueError:
            return 0

    def image_layout(self):
        """影像條目在列中的排列：(start_col, nfields, how)；沒有帶圖資訊回 None。
           how = 'declared'（IMAGELIST 欄 + TiffSpec）或 'inferred'（從資料推斷）。

           有些 1.8 檔沒有 TiffSpec、影像欄也不叫 IMAGELIST（甚至掛在宣告欄位
           之後）；此時從所有帶圖列推斷：candidate 起點取「宣告欄位之後」與
           「IMAGECOUNT 的下一欄（若它是最後一欄）」，要求每列多出的 token 數
           都能被自己的 IMAGECOUNT 整除、且每張圖的 token 數全檔一致。"""
        if self._img_layout != 'unset':
            return self._img_layout
        ic, il = self.image_col_index()
        layout = None
        if ic >= 0:
            layout = self._detect_images18(ic, il)
            if layout is None:
                if il >= 0 and self.tiff_spec and self.tiff_spec.get("nfields"):
                    layout = (il, self.tiff_spec["nfields"], 'declared')
                else:
                    layout = self._infer_image_layout(ic, il)
        self._img_layout = layout
        return layout

    def _detect_images18(self, ic, il):
        """1.8 結構化影像欄：儲存格是 'Images N {id "type" ,id "type" …}' 子區塊。
           以第一筆帶圖列判定；回 (start_col, None, 'images18') 或 None。"""
        s = il if il >= 0 else ic + 1
        for r in self.defects:
            if self.defect_image_count(r) > 0:
                return (s, None, 'images18') if s < len(r) and r[s] == 'Images' else None
        return None

    def _infer_image_layout(self, ic, il):
        n = len(self.defect_columns)
        # 候選起點：影像清單欄本身、宣告欄位之後、IMAGECOUNT 的下一欄（若是最後一欄）
        starts = []
        for s in ([il] if il >= 0 else []) + [n] + ([n - 1] if ic == n - 2 else []):
            if s not in starts:
                starts.append(s)
        cands = []
        for s in starts:
            # 多數決：每張圖的 token 數取眾數，容忍少數壞列（health 會另外抓）
            tally, total = {}, 0
            for r in self.defects:
                cnt = self.defect_image_count(r)
                if cnt <= 0:
                    continue
                total += 1
                extra = len(r) - s
                if extra > 0 and extra % cnt == 0:
                    k = extra // cnt
                    tally[k] = tally.get(k, 0) + 1
            if not tally:
                continue
            nf, votes = max(tally.items(), key=lambda kv: kv[1])
            if nf >= 1 and votes >= total - max(1, total // 10):
                cands.append((s, nf, 'inferred'))   # 容忍最多 ~10%（至少 1 列）壞列
        if len(cands) <= 1:
            return cands[0] if cands else None
        # 多個一致解：優先挑「第一個欄位像 page 編號（全整數且不重複）」的
        for s, nf, how in cands:
            ids, good = [], True
            for r in self.defects:
                cnt = self.defect_image_count(r)
                toks = r[s:]
                if len(toks) < cnt * nf:
                    continue        # 壞列不參與判斷
                for k in range(cnt):
                    v = toks[k * nf]
                    if not v.lstrip('-').isdigit():
                        good = False
                        break
                    ids.append(int(v))
                if not good:
                    break
            if good and ids and len(set(ids)) == len(ids):
                return (s, nf, how)
        return cands[0]

    def defect_image_entries(self, row):
        """該列的影像條目 [[tok, ...], ...]，每張圖一條；解不出來回 []。"""
        cnt = self.defect_image_count(row)
        layout = self.image_layout()
        if cnt <= 0 or layout is None:
            return []
        s, nf, how = layout
        if how == 'images18':
            m = re.match(r'Images\s+\d+\s*\{(.*)\}\s*$', ' '.join(row[s:]))
            if not m:
                return []
            entries = [e.split() for e in m.group(1).split(',') if e.strip()]
            return entries if len(entries) == cnt else []
        toks = row[s:]
        if len(toks) < cnt * nf:
            return []
        return [toks[k * nf:(k + 1) * nf] for k in range(cnt)]

    def defect_image_filename(self, row) -> "Optional[str]":
        """回傳該列的 per-defect 影像檔名；沒有則回 None（d4t 增補）。

        1.8（rSEM 類）KLARF 的列尾常帶
        `Image N { "file.jpg" "JPG" ... }` 或 `Images N { ... }` 子區塊；
        取區塊內第一個帶引號的字串當檔名（概念移植自 GLAS klarf_parser 的
        _map_row_tokens / _image_filename，改寫在 raw-token 列表示上）。
        純唯讀查詢，不影響既有解析與無損寫回。"""
        for k, tok in enumerate(row):
            if tok in ('Image', 'Images'):
                tail = ' '.join(row[k:])
                b0 = tail.find('{')
                if b0 < 0:
                    return None
                b1 = _find_matching_brace(tail, b0)
                block = tail[b0 + 1:b1] if b1 > b0 else tail[b0 + 1:]
                m = re.search(r'"([^"]*)"', block)
                return m.group(1) if m else None
        return None

    def total_image_count(self):
        return sum(self.defect_image_count(r) for r in self.defects)

    def defect_image_map(self, n_pages=None):
        """建立 defect → TIFF page（0-based）的對應。

        回傳 {"mode": 'imagelist' | 'sequential' | None,
              "base": 0 | 1 | None,       # imagelist 模式時 id 的起算基準
              "pages": [ [page, ...] 依 self.defects 順序 ],
              "notes": [str]}

        mode 判定：
          - IMAGELIST 每條目的第一個欄位若全是整數且不重複，視為 TIFF 的
            page 編號（KLA 慣例，通常 1-based）→ 'imagelist'
          - 否則退回「依 defect 出現順序連續配頁」→ 'sequential'
        """
        notes = []
        ic, il = self.image_col_index()
        if ic < 0:
            return {"mode": None, "base": None,
                    "pages": [[] for _ in self.defects],
                    "notes": ["No IMAGECOUNT column; this KLARF carries no patch info."]}
        counts = [self.defect_image_count(r) for r in self.defects]
        total = sum(counts)
        if total == 0:
            return {"mode": None, "base": None,
                    "pages": [[] for _ in self.defects],
                    "notes": ["IMAGECOUNT is 0 for every defect."]}

        # 嘗試 imagelist 模式：第一欄全為整數且完整
        ids_per_row, usable = [], (self.image_layout() is not None)
        if usable:
            for r, cnt in zip(self.defects, counts):
                entries = self.defect_image_entries(r)
                if len(entries) != cnt or not all(
                        e and e[0].lstrip('-').isdigit() for e in entries):
                    usable = False
                    break
                ids_per_row.append([int(e[0]) for e in entries])
        layout = self.image_layout()
        if usable and layout and layout[2] == 'images18' and all(
                ids == list(range(1, len(ids) + 1)) for ids in ids_per_row):
            # 1.8 結構化格式：id 是「defect 內的圖序號」，不是全域 page 編號
            usable = False
            notes.append("ImageList ids are per-defect ordinals (1..IMAGECOUNT); "
                         "mapping pages sequentially in defect order.")
        if usable:
            flat = [i for ids in ids_per_row for i in ids]
            if len(set(flat)) != len(flat):
                usable = False
                notes.append("IMAGELIST ids contain duplicates; "
                             "falling back to sequential mapping.")
        if usable:
            lo, hi = min(flat), max(flat)
            if n_pages is not None:
                if lo >= 1 and hi <= n_pages and not (lo == 0):
                    base = 1
                elif lo >= 0 and hi <= n_pages - 1:
                    base = 0
                else:
                    usable = False
                    notes.append(
                        f"IMAGELIST ids [{lo}..{hi}] do not fit in {n_pages} TIFF pages; "
                        "falling back to sequential mapping.")
            else:
                base = 0 if lo == 0 else 1
        if usable:
            if base == 1:
                notes.append("IMAGELIST first field treated as 1-based TIFF page number.")
            else:
                notes.append("IMAGELIST first field treated as 0-based TIFF page index.")
            return {"mode": "imagelist", "base": base,
                    "pages": [[i - base for i in ids] for ids in ids_per_row],
                    "notes": notes}

        # sequential：依出現順序連續分配
        pages, cum = [], 0
        for cnt in counts:
            pages.append(list(range(cum, cum + cnt)))
            cum += cnt
        if n_pages is not None and total != n_pages:
            notes.append(f"Sum of IMAGECOUNT ({total}) != TIFF page count ({n_pages}); "
                         "sequential mapping may be off.")
        notes.append("Pages assigned sequentially in defect order.")
        return {"mode": "sequential", "base": None, "pages": pages, "notes": notes}

    def tiff_path(self):
        """猜出對應的 TIFF 檔路徑（存在才回傳）。
           依序嘗試：TiffFileName（含只取檔名放同資料夾）、KLARF 同名 .tif/.tiff。"""
        cands = []
        base_dir = os.path.dirname(self.source_path) if self.source_path else None
        if self.tiff_file_name:
            name = self.tiff_file_name.replace('\\', '/')
            cands.append(name)                          # 絕對或相對於 cwd
            if base_dir is not None:
                cands.append(os.path.join(base_dir, os.path.basename(name)))
        if self.source_path:
            stem = os.path.splitext(self.source_path)[0]
            for p in (stem, self.source_path):
                for ext in ('.tif', '.tiff', '.TIF', '.TIFF'):
                    cands.append(p + ext)
        seen = set()
        for c in cands:
            if c and c not in seen:
                seen.add(c)
                if os.path.isfile(c):
                    return c
        return None

    def image_block_span(self, row):
        """回傳列中 ``Image(s) N { … }`` 子區塊的 (起始索引, token 數)；沒有回 None。

        d4t 增補（M5）。有一種真實 1.8 變體（fab_probe 稱 variant D）：
        影像欄是 ``ImageList`` 型別（例：IMAGEINFO）且**不在最後一欄**，
        同時整份檔案沒有 IMAGECOUNT 欄。這種列裡 ``Images 1 { "a.jpg" … }``
        佔多個 token 但只算一欄，若直接用 token 數比對欄數會全列誤判違法。
        """
        for k, tok in enumerate(row):
            if tok not in ('Image', 'Images'):
                continue
            depth = 0
            for j in range(k, len(row)):
                depth += row[j].count('{') - row[j].count('}')
                if '{' in row[j] or '}' in row[j]:
                    if depth <= 0:
                        return (k, j - k + 1)
            return (k, len(row) - k)
        return None

    def effective_row_len(self, row):
        """把影像子區塊算成一欄之後的等效欄數（d4t 增補，M5）。"""
        span = self.image_block_span(row)
        return len(row) if span is None else len(row) - (span[1] - 1)

    def row_len_ok(self, row):
        """該列 token 數是否合法。影像欄是變動長度：每張圖佔 image_layout()
           的 nfields 個 token，IMAGECOUNT=0 時可整欄省略。"""
        n = len(self.defect_columns)
        ic, il = self.image_col_index()
        if ic < 0:
            # 沒有 IMAGECOUNT 欄。若列裡帶 Image(s){…} 子區塊（variant D），
            # 把整個區塊折算成一欄再比對；否則維持原本的嚴格比對。
            return self.effective_row_len(row) == n
        cnt = self.defect_image_count(row)
        layout = self.image_layout()
        if layout is not None:
            s, nf, how = layout
            if how == 'images18':
                if cnt <= 0:
                    tail = ' '.join(row[s:]).strip()
                    return (len(row) in ({s, n} if s < n else {n})
                            or bool(re.fullmatch(r'Images\s+0\s*\{\s*\}', tail)))
                return len(self.defect_image_entries(row)) == cnt
            if cnt <= 0:
                return len(row) in ({s, n} if s < n else {n})
            return len(row) == s + cnt * nf
        # 排列推斷不出來：退回保守判斷
        base = n - (1 if il >= 0 else 0)
        if cnt <= 0:
            return len(row) in (base, n)
        if il >= 0:
            return len(row) >= base + cnt
        return len(row) == n

    # ---------- 編輯操作 ----------

    def set_header(self, name, value):
        if name not in self._header:
            raise ValueError(f"header 沒有可編輯欄位 {name}")
        self._header[name]["value"] = value
        self._header[name]["dirty"] = True

    def batch_reclass(self, from_class, to_class):
        """把某 class 的所有 defect 改成另一個 class；回傳筆數。"""
        i = self.col_index('CLASSNUMBER')
        if i < 0:
            raise ValueError("找不到 CLASSNUMBER 欄位")
        n = 0
        for r in self.defects:
            if r[i] == str(from_class):
                r[i] = str(to_class)
                n += 1
        self._defect_dirty = True
        return n

    def batch_set(self, match_col, match_val, set_col, set_val):
        """把「match_col == match_val」的所有 defect 之 set_col 設為 set_val；回傳筆數。
           match_col / set_col 可以是任意欄位（例：where ROUGHBINNUMBER=3 → set FINEBINNUMBER=4）。"""
        mi = self.col_index(match_col)
        si = self.col_index(set_col)
        if mi < 0:
            raise ValueError(f"找不到欄位 {match_col}")
        if si < 0:
            raise ValueError(f"找不到欄位 {set_col}")
        mv, sv = str(match_val), str(set_val)
        n = 0
        for r in self.defects:
            if mi < len(r) and r[mi] == mv and si < len(r):
                r[si] = sv
                n += 1
        if n:
            self._defect_dirty = True
        return n

    def die_stack(self, class_number, target_xindex, target_yindex):
        """把某 class 的 defect 全部歸到同一個 die（只改 XINDEX/YINDEX，
        保留 die 內相對座標 XREL/YREL）。回傳筆數。"""
        ci = self.col_index('CLASSNUMBER')
        xi = self.col_index('XINDEX')
        yi = self.col_index('YINDEX')
        if min(ci, xi, yi) < 0:
            raise ValueError("die stack 需要 CLASSNUMBER / XINDEX / YINDEX 欄位")
        n = 0
        for r in self.defects:
            if r[ci] == str(class_number):
                r[xi] = str(int(target_xindex))
                r[yi] = str(int(target_yindex))
                n += 1
        self._defect_dirty = True
        self.summary_stale = True    # 疊 die 會改變 NDEFDIE
        return n

    def set_cell(self, row_idx, col_name, value):
        j = self.col_index(col_name)
        if j < 0:
            raise ValueError(f"找不到欄位 {col_name}")
        self.defects[row_idx][j] = str(value)
        self._defect_dirty = True

    def delete_defects(self, row_indices):
        for idx in sorted(set(row_indices), reverse=True):
            del self.defects[idx]
        self._defect_dirty = True
        self.summary_stale = True

    def add_defect(self, row_tokens):
        row = [str(x) for x in row_tokens]
        if not self.row_len_ok(row):
            raise ValueError(
                f"欄位數不符：需要 {len(self.defect_columns)} 個，給了 {len(row_tokens)}")
        self.defects.append(row)
        self._defect_dirty = True
        self.summary_stale = True

    # ---------- 寫回（無損拼接） ----------

    def _any_dirty(self):
        return (self._defect_dirty or self._classlookup_dirty or self.summary_stale
                or any(h["dirty"] for h in self._header.values()))

    def _render_header(self, name, h):
        if self._is18:
            if h.get("rec"):     # Record XxxRecord "值"
                return re.sub(r'"(?:[^"\\]|\\.)*"', lambda _m: h["value"], h["orig"], count=1)
            return re.sub(r'\{[^}]*\}', '{' + h["value"] + '}', h["orig"], count=1)
        return re.sub(
            r'(\b' + re.escape(name) + r'\b[ \t]+)[^;]*(;)',
            lambda m: m.group(1) + h["value"] + m.group(2),
            h["orig"], count=1)

    def _eol(self):
        """沿用原檔的換行字元，避免產出檔 CRLF/LF 混用（Klarity 等工具會吃不到）。"""
        return '\r\n' if '\r\n' in self._text else '\n'

    def _render_defects(self):
        nl = self._eol()
        if self._is18:
            rows = nl.join('          ' + ' '.join(r) + ' ;' for r in self.defects)
            return f'Data {len(self.defects)}{nl}        {{{nl}{rows}{nl}        }}'
        rows = nl.join(' ' + ' '.join(r) for r in self.defects)
        return 'DefectList' + nl + rows + ';'

    def _recompute_summary_12(self):
        """依目前 defect 重算 summary：
           NDEFECT/NDEFDIE 直接算；DEFDENSITY 等比縮放；NDIE 保留原值。"""
        if not self._summary_rows:
            return
        sc = [c.upper() for c in self._summary_columns]
        def sidx(n): return sc.index(n) if n in sc else -1
        i_test, i_nd, i_ndd, i_dens = (sidx('TESTNO'), sidx('NDEFECT'),
                                       sidx('NDEFDIE'), sidx('DEFDENSITY'))
        ti = self.col_index('TEST')
        xi, yi = self.col_index('XINDEX'), self.col_index('YINDEX')
        single = (ti < 0 and len(self._summary_rows) == 1)
        for row in self._summary_rows:
            if i_test >= 0 and ti >= 0:
                ds = [d for d in self.defects if d[ti] == row[i_test]]
            elif single:
                ds = self.defects
            else:
                self.warnings.append(
                    "SummaryList has multiple rows but defects have no TEST column; summary not recomputed.")
                return
            new_nd = len(ds)
            old_nd = None
            if i_nd >= 0:
                try:
                    old_nd = int(row[i_nd])
                except ValueError:
                    old_nd = None
                row[i_nd] = str(new_nd)
            if i_ndd >= 0 and xi >= 0 and yi >= 0:
                row[i_ndd] = str(len({(d[xi], d[yi]) for d in ds}))
            if i_dens >= 0 and old_nd:
                try:
                    row[i_dens] = f"{float(row[i_dens]) * new_nd / old_nd:.10e}"
                except (ValueError, ZeroDivisionError):
                    pass

    def _render_summary_12(self):
        nl = self._eol()
        rows = nl.join('  ' + ' '.join(r) for r in self._summary_rows)
        return 'SummaryList' + nl + rows + ';'

    def to_text(self):
        """產生寫回檔案的內容。沒改動時回傳與原檔完全相同的字串。"""
        if not self._any_dirty():
            return self._text
        t = self._text
        for name, h in self._header.items():
            if h["dirty"]:
                t = t.replace(h["orig"], self._render_header(name, h), 1)
        if self._defect_dirty and self._defect_orig is not None:
            t = t.replace(self._defect_orig, self._render_defects(), 1)
        if (self.summary_stale and self.auto_recompute_summary
                and self._summary_orig is not None):
            if self._is18:
                self.warnings.append("1.8 summary auto-recompute is not implemented; kept unchanged.")
            else:
                self._recompute_summary_12()
                t = t.replace(self._summary_orig, self._render_summary_12(), 1)
        return t

    def save(self, path):
        """把目前的內容寫進 ``path``（**atomic**：先 ``.tmp`` 再 ``os.replace``）。

        ⚠ **這一支是 d4t 對上游唯一的行為改動**（2026-08-24）。上游是直接
        ``open(path, 'w')`` 寫進去，而 d4t 的鐵則 5 是「檔案寫入一律 atomic」——
        理由在這個檔案上特別重的：KLARF 寫回是**不可逆**的，而寫到一半斷掉
        （磁碟滿、行程被殺、網路碟斷線）留下的是一份**截斷的 KLARF**，
        它會蓋掉原本那一份，而原本那一份是廠內唯一的一手資料。

        ``.tmp`` + ``os.replace`` 讓那個狀態不存在：要嘛是舊的完整檔案，
        要嘛是新的完整檔案，沒有中間態。

        寫回的正規入口仍然是 `d4t.core.export.klarf_out`（它自己就是 atomic
        的，而且會先給一份「按下去會發生什麼」的預覽）。這一支是
        `KlarfDoc` 上的低階便道 —— 現在它至少不會比正規入口危險。
        """
        path = str(path)
        tmp = path + ".tmp"
        with open(tmp, 'w', encoding='utf-8', newline='') as f:
            f.write(self.to_text())
        os.replace(tmp, path)

    # ---------- API KLARF：用固定 FOV 網格鋪滿一或多塊區域 ----------
    def _grid_centers(self, rects, fov_x, fov_y, overlap):
        """回傳所有矩形合併後的網格中心點 [(cx, cy, cls_or_None), ...]。
           rects 的元素可為 (x0,y0,x1,y1) 或 (x0,y0,x1,y1,class)。"""
        import math
        sx = max(1e-9, fov_x * (1 - overlap))
        sy = max(1e-9, fov_y * (1 - overlap))
        centers = []
        for rect in rects:
            cls = rect[4] if len(rect) > 4 else None
            x0, y0, x1, y1 = rect[0], rect[1], rect[2], rect[3]
            if x1 < x0:
                x0, x1 = x1, x0
            if y1 < y0:
                y0, y1 = y1, y0
            nx = max(1, math.ceil((x1 - x0) / sx))
            ny = max(1, math.ceil((y1 - y0) / sy))
            for j in range(ny):
                for i in range(nx):
                    centers.append((x0 + fov_x/2 + i*sx, y0 + fov_y/2 + j*sy, cls))
        return centers

    def make_api_rows(self, rects, fov_x, fov_y, overlap, dies, class_num, did_start=1,
                      dies_by_class=None):
        """在 die 內相對座標的一或多個矩形內鋪 FOV 網格點，複製到指定的 die。
           rects 可為單一 (x0,y0,x1,y1) 或其 list，元素可帶第 5 個值當 class。
           dies_by_class 可為 {class: [(xi,yi), ...]}，讓每個 class 的選區套用到
           自己的一組 die；沒指定的 class 則退回共用的 dies。
           回傳 (rows, per_die, n_regions)。
           未指定的欄位（TEST/XSIZE/DEFECTAREA…）沿用原檔第一筆 defect 的值，
           避免產出 TEST=0、尺寸全 0 這種下游工具（如 Klarity）吃不到的列。"""
        if rects and isinstance(rects[0], (int, float)):
            rects = [rects]
        cols = self.defect_columns
        pos = {c.upper(): k for k, c in enumerate(cols)}
        # 範本列：優先沿用原檔第一筆 defect，其餘欄位才補 0
        # （帶圖的列比欄位數長，截到欄位數即可；IMAGECOUNT 歸 0）
        if self.defects and len(self.defects[0]) >= len(cols) - 1 \
                and self.row_len_ok(self.defects[0]):
            template = (list(self.defects[0]) + ["0"])[:len(cols)]
        else:
            template = ["0"] * len(cols)
        if 'IMAGECOUNT' in pos:
            template[pos['IMAGECOUNT']] = "0"
        if 'IMAGELIST' in pos:
            template[pos['IMAGELIST']] = "0"

        def fmt(v):
            return f"{v:.3f}" if self.version == '1.2' else str(int(round(v)))

        rows = []
        did = did_start
        per_die = 0
        for rect in rects:
            cls_v = str(rect[4]) if len(rect) > 4 and rect[4] is not None else str(class_num)
            centers = self._grid_centers([rect], fov_x, fov_y, overlap)
            per_die += len(centers)
            rdies = None
            if dies_by_class:
                rdies = dies_by_class.get(cls_v)
            if not rdies:
                rdies = dies
            for (dxi, dyi) in rdies:
                for (cx, cy, _c) in centers:
                    row = list(template)
                    for name, val in (('DEFECTID', str(did)), ('XREL', fmt(cx)),
                                      ('YREL', fmt(cy)), ('XINDEX', str(int(dxi))),
                                      ('YINDEX', str(int(dyi))), ('CLASSNUMBER', cls_v)):
                        if name in pos:
                            row[pos[name]] = val
                    rows.append(row)
                    did += 1
        return rows, per_die, len(rects)

    def api_text(self, rects, fov_x, fov_y, overlap, dies, class_num, did_start=1,
                 keep_classes=None, dies_by_class=None):
        """產生全新的 API KLARF 內容（沿用本檔 header 為範本，換掉 defect list）。
           keep_classes 指定「要保留的原始 defect 之 CLASSNUMBER 集合」，會併入網格點，
           並把所有輸出列的 DEFECTID 從 did_start 起重新排列。
           回傳 (text, per_die, n_regions, total, kept, warnings)。"""
        rows, per_die, n_reg = self.make_api_rows(rects, fov_x, fov_y, overlap,
                                                  dies, class_num, did_start,
                                                  dies_by_class)
        kept = 0
        ci = self.col_index('CLASSNUMBER')
        if keep_classes and ci >= 0:
            ks = {str(c) for c in keep_classes}
            for r in self.defects:
                if ci < len(r) and r[ci] in ks:
                    rows.append(list(r)); kept += 1
        # 重新排列 DEFECTID（網格 + 保留的原始 defect 一起連號）
        di = self.col_index('DEFECTID')
        if di >= 0:
            for k, r in enumerate(rows):
                if di < len(r):
                    r[di] = str(did_start + k)
        clone = load(self._text)
        clone.defects = rows
        clone._defect_dirty = True
        text = clone.to_text()
        warns = []
        total, ndie = len(rows), len(dies)
        if clone._summary_orig and clone._summary_columns and clone._summary_rows:
            # 以原檔第一列為底，只改能安全推算的欄位；其餘（NDIE 等）原值保留，
            # 避免寫出 DEFDENSITY 0 / NDIE 1 這種下游工具會拒收的值。
            row = list(clone._summary_rows[0])
            sc = [c.upper() for c in clone._summary_columns]
            def sidx(n): return sc.index(n) if n in sc else -1
            i_nd, i_ndd, i_dens = sidx('NDEFECT'), sidx('NDEFDIE'), sidx('DEFDENSITY')
            old_nd = None
            if i_nd >= 0:
                try:
                    old_nd = int(row[i_nd])
                except ValueError:
                    old_nd = None
                row[i_nd] = str(total)
            if i_ndd >= 0:
                row[i_ndd] = str(ndie)
            if i_dens >= 0 and old_nd:
                try:
                    row[i_dens] = f"{float(row[i_dens]) * total / old_nd:.10e}"
                except (ValueError, ZeroDivisionError):
                    pass
            nl = clone._eol()
            block = 'SummaryList' + nl + '  ' + ' '.join(row) + ';'
            text = text.replace(clone._summary_orig, block, 1)
        elif self.version == '1.8':
            warns.append("1.8：defect 網格已產生，但 SummaryList 未重算（1.8 summary 尚未支援）。")
        return text, per_die, n_reg, total, kept, warns


def load(src):
    """src 可為檔案路徑或 KLARF 文字內容。"""
    if isinstance(src, str) and ('\n' not in src) and os.path.exists(src):
        with open(src, 'r', encoding='utf-8', errors='replace') as f:
            return KlarfDoc(f.read(), source_path=src)
    return KlarfDoc(src)


# ================================================================ 格式健檢
# 規則多半來自實戰：Klarity 等下游工具吃不到檔案時，最常見的就是這幾類問題。

class Issue:
    """一條健檢結果。fix_code 有值代表可一鍵修正。"""
    def __init__(self, code, level, title, detail, count=0, fixable=False):
        self.code = code          # 規則代號
        self.level = level        # 'error' / 'warn' / 'info'
        self.title = title
        self.detail = detail
        self.count = count        # 受影響的筆數（0=不適用）
        self.fixable = fixable


def _nums(seq):
    out = []
    for v in seq:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def _valid_tests(doc):
    """檔案裡合法的 test 編號：InspectionTest 宣告 + SummaryList 的 TESTNO。"""
    ts = {m.group(1) for m in re.finditer(r'(?m)^[ \t]*InspectionTest[ \t]+(\d+)[ \t]*;', doc._text)}
    sc = [c.upper() for c in (doc._summary_columns or [])]
    if 'TESTNO' in sc:
        j = sc.index('TESTNO')
        for r in doc._summary_rows:
            if j < len(r):
                ts.add(r[j])
    return ts


SIZE_COLS = ('XSIZE', 'YSIZE', 'DEFECTAREA', 'DSIZE')
REQUIRED_12 = ('FileVersion', 'LotID', 'WaferID', 'DiePitch', 'SampleSize',
               'DeviceID', 'StepID', 'InspectionStationID', 'SampleType',
               'OrientationMarkLocation')


def lint(doc):
    """檢查一份 KLARF，回傳 [Issue]。"""
    out = []
    t = doc._text
    cols = doc.defect_columns
    n = len(doc.defects)

    # --- 結構層 ---
    crlf = t.count('\r\n'); lf = t.count('\n') - crlf
    if crlf and lf:
        out.append(Issue('eol', 'error', 'Mixed line endings (CRLF + LF)',
                         f'The file mixes {crlf} CRLF and {lf} LF line breaks. '
                         'Strict parsers (Klarity among them) may fail to read it at all.',
                         fixable=True))
    if not t.rstrip().endswith('EndOfFile;'):
        out.append(Issue('eof', 'error', 'Missing EndOfFile; terminator',
                         'A KLARF must end with EndOfFile; or it is treated as truncated.',
                         fixable=True))
    if not cols:
        out.append(Issue('nospec', 'error', 'No defect column definition found',
                         'DefectRecordSpec / Columns could not be read, so the remaining checks were skipped.'))
        return out

    if not doc._is18:
        m = re.search(r'DefectRecordSpec\s+(\d+)\s+([^;]+);', t)
        if m and int(m.group(1)) != len(cols):
            out.append(Issue('speccount', 'error', 'DefectRecordSpec column count mismatch',
                             f'Declares {m.group(1)} columns but lists {len(cols)}.',
                             fixable=True))

    # IMAGELIST 是變動長度欄（每張圖 TiffSpec.nfields 個 token），用 row_len_ok 判定
    bad_len = sum(1 for r in doc.defects if not doc.row_len_ok(r))
    if bad_len:
        out.append(Issue('rowlen', 'error', 'Defect rows do not match the column definition',
                         f'{bad_len} defect rows do not match the {len(cols)}-column definition '
                         '(IMAGELIST rows are allowed their declared extra image tokens). '
                         'The fix pads with 0 or truncates; rows carrying images are only padded.',
                         bad_len, fixable=True))

    # --- DEFECTID ---
    di = doc.col_index('DEFECTID')
    if di >= 0:
        ids = [r[di] for r in doc.defects if di < len(r)]
        dup = len(ids) - len(set(ids))
        if dup:
            out.append(Issue('dupid', 'error', 'Duplicate DEFECTID',
                             f'{dup} duplicated DEFECTID values. Downstream tools may keep only one of each.',
                             dup, fixable=True))

    # --- TEST 欄與 InspectionTest 對應 ---
    ti = doc.col_index('TEST')
    if ti >= 0 and not doc._is18:
        valid = _valid_tests(doc)
        if valid:
            bad = sum(1 for r in doc.defects if ti < len(r) and r[ti] not in valid)
            if bad:
                out.append(Issue('test', 'error', 'Defect TEST does not match any inspection test',
                                 f'{bad} defects have a TEST value outside {sorted(valid)} '
                                 '(generated files often leave it as 0). Review tools cannot '
                                 'match these defects to an inspection, so they are skipped.',
                                 bad, fixable=True))

    # --- 尺寸欄全 0 ---
    size_idx = [(c, doc.col_index(c)) for c in SIZE_COLS]
    size_idx = [(c, i) for c, i in size_idx if i >= 0]
    if size_idx and n:
        zero = 0
        for r in doc.defects:
            vals = [r[i] for _c, i in size_idx if i < len(r)]
            if vals and all(_isz(v) for v in vals):
                zero += 1
        if zero:
            can = any(any(not _isz(r[i]) for r in doc.defects if i < len(r))
                      for _c, i in size_idx)
            out.append(Issue('zerosize', 'warn', 'Defect size columns are all zero',
                             f'{zero} defects have {"/".join(c for c, _ in size_idx)} all set to 0. '
                             'Many tools discard zero-sized defects or treat them as invalid.'
                             + ('' if can else ' No non-zero values exist in this file, '
                                'so it cannot be fixed automatically.'),
                             zero, fixable=can))

    # --- 座標型別 ---
    xr, yr = doc.col_index('XREL'), doc.col_index('YREL')
    if doc._is18 and xr >= 0:
        frac = sum(1 for r in doc.defects if xr < len(r) and '.' in r[xr])
        if frac:
            out.append(Issue('coordint', 'warn', '1.8 coordinates should be integer nm',
                             f'{frac} XREL values contain a decimal point. KLARF 1.8 stores coordinates as integer nanometres.',
                             frac, fixable=True))
    if (not doc._is18) and xr >= 0 and doc.defects:
        xs = _nums(r[xr] for r in doc.defects if xr < len(r))
        if xs and all(abs(v) > 1e6 for v in xs):
            out.append(Issue('coordunit', 'warn', '1.2 coordinates look like nanometre values',
                             'KLARF 1.2 stores coordinates in micrometres, but every XREL '
                             'exceeds 1e6 — this looks like nanometre values written into a 1.2 '
                             'file. This is not fixed automatically; please check the source.'))

    # --- 座標是否落在 die 內 ---
    try:
        _dp = doc._header.get('DiePitch') or {}
        pit = _nums(re.split(r'[\s,]+', str(_dp.get('value', '')).strip()))
    except Exception:
        pit = []
    if len(pit) >= 2 and pit[0] > 0 and xr >= 0 and yr >= 0:
        tol = 0.02
        oob = 0
        for r in doc.defects:
            try:
                x, y = float(r[xr]), float(r[yr])
            except (ValueError, IndexError):
                continue
            if not (-pit[0]*tol <= x <= pit[0]*(1+tol) and -pit[1]*tol <= y <= pit[1]*(1+tol)):
                oob += 1
        if oob:
            out.append(Issue('oob', 'info', 'Defect coordinates fall outside the die',
                             f'{oob} defects have XREL/YREL outside the die pitch '
                             f'({pit[0]:g} × {pit[1]:g}). This is expected if the file uses '
                             'absolute coordinates or a shifted DieOrigin.',
                             oob))

    # --- ClassLookup ---
    ci = doc.col_index('CLASSNUMBER')
    if ci >= 0 and doc.class_lookup:
        known = {str(k) for k in (doc.class_lookup or {})}
        miss = sorted({r[ci] for r in doc.defects if ci < len(r) and r[ci] not in known})
        if miss:
            out.append(Issue('class', 'warn', 'Defects use classes that are not defined',
                             'ClassLookup does not define: ' + ", ".join(miss[:12])
                             + ('…' if len(miss) > 12 else ''),
                             len(miss)))

    # --- SummaryList ---
    if doc._summary_rows and doc._summary_columns:
        sc = [c.upper() for c in (doc._summary_columns or [])]
        if 'NDEFECT' in sc:
            j = sc.index('NDEFECT')
            declared = sum(int(r[j]) for r in doc._summary_rows
                           if j < len(r) and r[j].lstrip('-').isdigit())
            if declared != n:
                out.append(Issue('summary', 'warn', 'SummaryList defect count does not match the DefectList',
                                 f'The summary declares {declared} defects but the DefectList '
                                 f'has {n}. Note: this difference is normal for files that only '
                                 'contain a sampled review subset.',
                                 abs(declared - n), fixable=True))
        if 'DEFDENSITY' in sc:
            j = sc.index('DEFDENSITY')
            if any(j < len(r) and _isz(r[j]) for r in doc._summary_rows):
                out.append(Issue('density', 'warn', 'DEFDENSITY is zero',
                                 'A zero defect density usually means the summary was rebuilt without recomputing it.'))

    # --- 必要 header ---
    if not doc._is18:
        miss = [f for f in REQUIRED_12 if f not in doc._header]
        if miss:
            out.append(Issue('header', 'warn', 'Common header fields are missing',
                             'Not found: ' + ', '.join(miss) +
                             '. Some tools require these before they will load a file. '
                             'Values cannot be invented, so this is not auto-fixable.',
                             len(miss)))
    return out


def _isz(v):
    try:
        return float(v) == 0.0
    except (TypeError, ValueError):
        return False


def _median(vals):
    s = sorted(vals)
    return s[len(s)//2] if s else None


def autofix(doc, codes):
    """套用選定的修正，回傳 (新的 KLARF 文字, [說明訊息])。原 doc 不動。"""
    d = load(doc.to_text())
    msgs = []
    cols = d.defect_columns
    codes = set(codes)

    if 'rowlen' in codes and cols:
        k = 0
        for r in d.defects:
            if d.row_len_ok(r):
                continue
            k += 1
            cnt = d.defect_image_count(r)
            if cnt <= 0:
                while len(r) < len(cols):
                    r.append('0')
                del r[len(cols):]
            else:
                # 有 patch 影像的列只補不砍，避免破壞影像條目
                target = len(cols)
                layout = d.image_layout()
                if layout is not None and layout[1]:   # images18 無固定寬度，不硬補
                    target = layout[0] + cnt * layout[1]
                while len(r) < target:
                    r.append('0')
        if k:
            d._defect_dirty = True; msgs.append(f'補齊/截斷 {k} 筆欄數不符的 defect')

    if 'zerosize' in codes:
        idx = [(c, d.col_index(c)) for c in SIZE_COLS]
        idx = [(c, i) for c, i in idx if i >= 0]
        fill = {}
        for c, i in idx:
            vals = [float(r[i]) for r in d.defects
                    if i < len(r) and not _isz(r[i]) and _isnum_s(r[i])]
            if vals:
                fill[i] = (c, _median(vals), r'{:g}'.format(_median(vals)))
        if fill:
            k = 0
            for r in d.defects:
                vals = [r[i] for _c, i in idx if i < len(r)]
                if vals and all(_isz(v) for v in vals):
                    for i, (_c, _v, txt) in fill.items():
                        if i < len(r):
                            r[i] = txt
                    k += 1
            if k:
                d._defect_dirty = True
                msgs.append(f'用檔內的中位數尺寸填補 {k} 筆零尺寸 defect')

    if 'test' in codes:
        ti = d.col_index('TEST')
        valid = _valid_tests(d)
        if ti >= 0 and valid:
            good = sorted(valid, key=lambda s: (0, int(s)) if s.isdigit() else (1, s))[0]
            k = 0
            for r in d.defects:
                if ti < len(r) and r[ti] not in valid:
                    r[ti] = good; k += 1
            if k:
                d._defect_dirty = True; msgs.append(f'把 {k} 筆 defect 的 TEST 改成 {good}')

    if 'coordint' in codes and d._is18:
        k = 0
        for name in ('XREL', 'YREL'):
            i = d.col_index(name)
            if i < 0:
                continue
            for r in d.defects:
                if i < len(r) and '.' in r[i] and _isnum_s(r[i]):
                    r[i] = str(int(round(float(r[i])))); k += 1
        if k:
            d._defect_dirty = True; msgs.append(f'把 {k} 個含小數的座標改為整數 nm')

    if 'dupid' in codes:
        di = d.col_index('DEFECTID')
        if di >= 0:
            for k, r in enumerate(d.defects, 1):
                if di < len(r):
                    r[di] = str(k)
            d._defect_dirty = True
            msgs.append(f'把 DEFECTID 重新編號為 1..{len(d.defects)}')

    if 'summary' in codes:
        d.auto_recompute_summary = True
        d.summary_stale = True
        d._defect_dirty = True
        msgs.append('依實際 defect 重算 SummaryList（NDIE 保留原值）')

    text = d.to_text()

    if 'speccount' in codes and not d._is18:
        def _fix(m):
            return f'DefectRecordSpec {len(cols)} {m.group(2)};'
        text2 = re.sub(r'DefectRecordSpec\s+(\d+)\s+([^;]+);', _fix, text, count=1)
        if text2 != text:
            text = text2; msgs.append(f'把 DefectRecordSpec 的欄數改成 {len(cols)}')

    if 'eol' in codes:
        crlf = text.count('\r\n'); lf = text.count('\n') - crlf
        nl = '\r\n' if crlf >= lf else '\n'
        text = text.replace('\r\n', '\n')
        if nl == '\r\n':
            text = text.replace('\n', '\r\n')
        msgs.append('把換行統一為 ' + ('CRLF' if nl == '\r\n' else 'LF'))

    if 'eof' in codes and not text.rstrip().endswith('EndOfFile;'):
        nl = '\r\n' if '\r\n' in text else '\n'
        text = text.rstrip() + nl + 'EndOfFile;' + nl
        msgs.append('補上結尾的 EndOfFile;')

    return text, msgs


def _isnum_s(v):
    try:
        float(v); return True
    except (TypeError, ValueError):
        return False


# ================================================================ KLARF 比對

# 這幾欄已由 added/removed/reclass/moved 表達，不再列入「其他欄位變化」
_SKIP_FIELDS = {'DEFECTID', 'XREL', 'YREL', 'XINDEX', 'YINDEX', 'CLASSNUMBER'}


def _pts_for_compare(doc):
    """把 defect 轉成統一單位(nm)的比對用結構。"""
    f = doc.unit_info()['to_nm']
    xi, yi = doc.col_index('XINDEX'), doc.col_index('YINDEX')
    xr, yr = doc.col_index('XREL'), doc.col_index('YREL')
    ci, di = doc.col_index('CLASSNUMBER'), doc.col_index('DEFECTID')
    out = []
    for k, r in enumerate(doc.defects):
        try:
            die = (int(r[xi]), int(r[yi])) if xi >= 0 and yi >= 0 else (0, 0)
            x = float(r[xr]) * f if xr >= 0 else 0.0
            y = float(r[yr]) * f if yr >= 0 else 0.0
        except (ValueError, IndexError):
            continue
        out.append({'i': k, 'id': r[di] if 0 <= di < len(r) else str(k),
                    'die': die, 'x': x, 'y': y,
                    'cls': r[ci] if 0 <= ci < len(r) else '0', 'row': r})
    return out


def _same_number(a, b):
    """0.03 與 0.030、1e3 與 1000 視為相同，避免格式差異被當成變化。"""
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return False


def compare(doc_a, doc_b, tol_nm=500.0, mode='position'):
    """比對兩份 KLARF。mode='position' 依 die+座標配對（容差 tol_nm），
       mode='id' 依 DEFECTID 配對。回傳結果 dict。"""
    A, B = _pts_for_compare(doc_a), _pts_for_compare(doc_b)
    matched = []          # (a, b)
    used_b = set()

    if mode == 'id':
        idx = {}
        for p in B:
            idx.setdefault(p['id'], []).append(p)
        for pa in A:
            cand = idx.get(pa['id'])
            if cand:
                pb = cand.pop(0)
                matched.append((pa, pb)); used_b.add(pb['i'])
    else:
        # 以 die 分桶，桶內再用網格雜湊找容差內最近的點
        buckets = {}
        for p in B:
            cell = (p['die'], int(p['x']//max(tol_nm, 1)), int(p['y']//max(tol_nm, 1)))
            buckets.setdefault(cell, []).append(p)
        for pa in A:
            cx, cy = int(pa['x']//max(tol_nm, 1)), int(pa['y']//max(tol_nm, 1))
            best, bestd = None, None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for pb in buckets.get((pa['die'], cx+dx, cy+dy), ()):
                        if pb['i'] in used_b:
                            continue
                        d = ((pa['x']-pb['x'])**2 + (pa['y']-pb['y'])**2) ** 0.5
                        if d <= tol_nm and (bestd is None or d < bestd):
                            best, bestd = pb, d
            if best is not None:
                matched.append((pa, best)); used_b.add(best['i'])

    a_matched = {pa['i'] for pa, _ in matched}
    removed = [p for p in A if p['i'] not in a_matched]
    added = [p for p in B if p['i'] not in used_b]
    reclass = [(pa, pb) for pa, pb in matched if pa['cls'] != pb['cls']]
    moved = [(pa, pb) for pa, pb in matched
             if abs(pa['x']-pb['x']) > 1e-6 or abs(pa['y']-pb['y']) > 1e-6]

    # 其他欄位的變化（DSIZE、ROUGHBINNUMBER…）：只比兩邊都有的欄位
    ca = {c.upper(): i for i, c in enumerate(doc_a.defect_columns)}
    cb = {c.upper(): i for i, c in enumerate(doc_b.defect_columns)}
    shared = [c for c in ca if c in cb and c not in _SKIP_FIELDS]
    changed = []
    for pa, pb in matched:
        ra, rb = pa['row'], pb['row']
        diffs = []
        for c in shared:
            ia, ib = ca[c], cb[c]
            va = ra[ia] if ia < len(ra) else ''
            vb = rb[ib] if ib < len(rb) else ''
            if va != vb and not _same_number(va, vb):
                diffs.append((c, va, vb))
        if diffs:
            changed.append((pa, pb, diffs))
    same = len(matched) - len({id(x) for x in reclass} | {id(x) for x in moved})

    # header 差異
    ha = dict(doc_a.header_items()); hb = dict(doc_b.header_items())
    hdr = []
    for k in sorted(set(ha) | set(hb)):
        va, vb = ha.get(k), hb.get(k)
        if va != vb:
            hdr.append((k, va, vb))

    # class 分佈
    def dist(pts):
        d = {}
        for p in pts:
            d[p['cls']] = d.get(p['cls'], 0) + 1
        return d
    da, db = dist(A), dist(B)
    classes = sorted(set(da) | set(db),
                     key=lambda s: (0, int(s)) if s.lstrip('-').isdigit() else (1, s))
    cls_rows = [(c, da.get(c, 0), db.get(c, 0),
                 doc_a.class_lookup.get(int(c)) if c.lstrip('-').isdigit() else None)
                for c in classes]

    # die 分佈（給 wafer 圖用）
    def dies(pts):
        d = {}
        for p in pts:
            d[p['die']] = d.get(p['die'], 0) + 1
        return d

    return {
        'mode': mode, 'tol_nm': tol_nm,
        'a': {'name': os.path.basename(doc_a.source_path or 'A'),
              'version': doc_a.version, 'unit': doc_a.unit_info()['coord_unit'],
              'n': len(A), 'dies': dies(A)},
        'b': {'name': os.path.basename(doc_b.source_path or 'B'),
              'version': doc_b.version, 'unit': doc_b.unit_info()['coord_unit'],
              'n': len(B), 'dies': dies(B)},
        'matched': len(matched), 'same': same,
        'added': added, 'removed': removed, 'reclass': reclass, 'moved': moved,
        'changed': changed, 'shared_fields': shared,
        'header': hdr, 'classes': cls_rows,
        'summary_a': [list(r) for r in doc_a._summary_rows],
        'summary_b': [list(r) for r in doc_b._summary_rows],
        'summary_cols': doc_a._summary_columns or doc_b._summary_columns,
        'geom': _wafer_geom(doc_a) or _wafer_geom(doc_b),
    }


def _wafer_geom(doc):
    """從 header 推出晶圓幾何（與 App 的 wafer map 同一套近似）。
       回傳 {'rx','ry','ar','notch'}；rx/ry = 晶圓半徑（單位: die 數），
       ar = pitchY/pitchX（die 真實長寬比）。推不出來時回傳 None。"""
    def fval(name):
        for n, v in doc.header_items():
            if n == name:
                return [float(x) for x in
                        re.findall(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', v)]
        return []
    try:
        pit = fval('DiePitch')
        ss = fval('SampleSize')
        if len(pit) < 2 or pit[0] <= 0 or pit[1] <= 0 or not ss:
            return None
        mm = max(ss)
        if mm < 10:           # SampleSize 不是 mm 口徑（如 wafer 型號碼）就放棄
            return None
        dia = mm * (1000.0 if doc.unit_info()['coord_unit'] == 'µm' else 1e6)
        rx, ry = (dia / 2) / pit[0], (dia / 2) / pit[1]
        if not (1 <= rx <= 80 and 1 <= ry <= 80):
            return None
        notch = None
        for n, v in doc.header_items():
            if n == 'OrientationMarkLocation':
                notch = v.strip().strip('"').upper() or None
        return {'rx': rx, 'ry': ry, 'ar': pit[1] / pit[0], 'notch': notch}
    except (ValueError, ZeroDivisionError):
        return None



def diff_rows(res):
    """把比對結果整理成並排差異列：(狀態集合, A點或None, B點或None, 有變化的欄位)。
       同一顆 defect 若同時改分類又位移，會合併成一列。"""
    merged = {}
    order = []
    def put(status, pa, pb, fields):
        key = (id(pa) if pa is not None else None, id(pb) if pb is not None else None)
        if key in merged:
            merged[key][0].add(status); merged[key][3].update(fields)
        else:
            merged[key] = [{status}, pa, pb, set(fields)]
            order.append(key)
    for p in res['removed']:
        put('removed', p, None, set())
    for p in res['added']:
        put('added', None, p, set())
    for pa, pb in res['reclass']:
        put('reclass', pa, pb, {'cls'})
    for pa, pb in res['moved']:
        f = set()
        if abs(pa['x']-pb['x']) > 1e-6:
            f.add('x')
        if abs(pa['y']-pb['y']) > 1e-6:
            f.add('y')
        put('moved', pa, pb, f)
    detail = {}
    for pa, pb, diffs in res.get('changed', ()):
        put('changed', pa, pb, {'other'})
        detail[(id(pa), id(pb))] = diffs
    rows = []
    for key in order:
        st, pa, pb, fields = merged[key]
        ref = pa if pa is not None else pb
        rows.append((st, pa, pb, fields, ref['die'], detail.get(key, [])))
    rows.sort(key=lambda r: (-r[4][1], r[4][0]))      # 依 die 排，方便一片片看
    return [(st, pa, pb, f, d) for st, pa, pb, f, _die, d in rows]


STATUS_TXT = {'added': '新增', 'removed': '消失', 'reclass': '分類不同',
              'moved': '座標位移', 'changed': '欄位變更'}
STATUS_ORDER = ['removed', 'added', 'reclass', 'moved', 'changed']


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


HEAT_ZERO = (255, 255, 255)                              # 0
HEAT_LO1, HEAT_LO2 = (255, 229, 229), (255, 170, 170)    # 低值段
HEAT_MD1 = (255, 102, 102)                               # 中值段起點
HEAT_FULL = (255, 0, 0)                                  # >= 上限：正紅
WAFER_DISC_C = "#565b63"     # 晶圓本體：中灰
OUTSIDE_C = "#ffffff"        # 晶圓外：純白
CENTER_DIE_C = "#00ff00"     # 基準晶粒：螢光綠


def _mix(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def heat_rgb(v, cap):
    """0=純白 → 淡粉 → 珊瑚粉 → 洋紅 → 正紅(>=cap 截斷)。與 App 同一套。"""
    if v <= 0:
        c = HEAT_ZERO
    else:
        t = v / max(cap, 1)
        if t >= 1.0:
            c = HEAT_FULL
        elif t <= 0.4:
            c = _mix(HEAT_LO1, HEAT_LO2, t / 0.4)
        else:
            c = _mix(HEAT_MD1, HEAT_FULL, (t - 0.4) / 0.6)
    return 'rgb(%d,%d,%d)' % c



def _svg_wafer(dies_a, dies_b, kind, size=26, cap=10, geom=None):
    """畫一張 die 熱力圖 SVG（與 App 的 Workspace wafer map 同一套視覺）：
       暗灰圓盤 + 白→正紅漸層（超過 cap 截斷）+ 細黑格線 + 格內數字 +
       中心 die 綠框 + 右側色階條 + 缺口標記。
       geom（來自 _wafer_geom）給的話，會像 App 一樣畫出以 die (0,0) 為中心的
       近似完整晶圓 die 網格（含真實 die 長寬比與 header 指定的缺口方位）。
       kind='a'/'b' 顯示各自數量；kind='diff' 顯示 B−A（紅=B多 藍=A多）。"""
    keys = set(dies_a) | set(dies_b)
    if not keys:
        return '<p class="muted">no die data</p>'
    xs = [k[0] for k in keys]; ys = [k[1] for k in keys]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)

    # ---- 與 App 相同的近似完整晶圓網格：中心固定在 die (0,0) ----
    cells = None
    ar = 1.0
    notch_pos = 'DOWN'
    if geom:
        ar = max(0.25, min(4.0, geom.get('ar') or 1.0))
        rx, ry = geom['rx'], geom['ry']
        # 真的有 die 落在推算圓外（座標系不同或 SampleSize 有誤）就撐大半徑
        need = max(abs(bx0), abs(bx1)) + 0.5
        if need > rx:
            rx = need
        need = max(abs(by0), abs(by1)) + 0.5
        if need > ry:
            ry = need
        cs = set()
        for i in range(int(-rx) - 1, int(rx) + 2):
            for j in range(int(-ry) - 1, int(ry) + 2):
                if (i / rx) ** 2 + (j / ry) ** 2 <= 1.0:
                    cs.add((i, j))
        cs |= keys
        if len(cs) <= 5000:          # 太大就退回只畫有 defect 的 die
            cells = cs
        if geom.get('notch') in ('DOWN', 'UP', 'LEFT', 'RIGHT'):
            notch_pos = geom['notch']
    if cells is None:
        cells = set(keys)
    xs2 = [c[0] for c in cells]; ys2 = [c[1] for c in cells]
    x0, x1, y0, y1 = min(xs2), max(xs2), min(ys2), max(ys2)
    ncol, nrow = x1 - x0 + 1, y1 - y0 + 1

    # 格子尺寸自適應：完整晶圓格數多時自動縮小，避免圖爆版
    size = max(9.0, min(float(size), 720.0 / ncol, 720.0 / (nrow * ar)))
    sizex, sizey = size, size * ar
    show_num = min(sizex, sizey) >= 13     # 格子太小就不塞數字（同 App 的行為）

    barw = 46
    gw, gh = ncol * sizex, nrow * sizey
    rad = max(gw, gh) / 2 * 1.04           # 與 App 相同的 4% 邊距
    notch_r = max(4.0, min(sizex, sizey) * 0.30)
    margin = max(8.0, size * 0.5)
    # 畫布同時裝得下 die 網格與晶圓圓盤（含四個方位的缺口圓）——不會被裁切
    half_w = max(gw / 2, rad + notch_r) + margin
    half_h = max(gh / 2, rad + notch_r) + margin
    W, H = half_w * 2 + barw, half_h * 2
    # 圓盤中心 = die (0,0) 的格子中心（KLARF 索引以原點 die 為基準，同 App）
    ox, oy = half_w - gw / 2, half_h - gh / 2
    if geom and (x0 <= 0 <= x1) and (y0 <= 0 <= y1):
        cx = ox + (0 - x0 + 0.5) * sizex
        cy = oy + (y1 - 0 + 0.5) * sizey
    else:
        cx, cy = half_w, half_h
    # 中心若偏離畫布中心（原點 die 不在網格正中），畫布向外擴到涵蓋整個圓盤
    ex_l = max(0.0, rad + notch_r + margin - cx)
    ex_r = max(0.0, cx + rad + notch_r + margin - (W - barw))
    ex_t = max(0.0, rad + notch_r + margin - cy)
    ex_b = max(0.0, cy + rad + notch_r + margin - H)
    ox += ex_l; cx += ex_l
    oy += ex_t; cy += ex_t
    W += ex_l + ex_r
    H += ex_t + ex_b
    src = dies_a if kind == 'a' else dies_b
    if kind == 'diff':
        mx = max([abs(dies_b.get(k, 0)-dies_a.get(k, 0)) for k in keys] or [1])
    else:
        mx = cap

    def diverge(d):
        if d == 0:
            return '#ffffff'
        t = min(1.0, abs(d)/max(mx, 1))
        base = (255, 0, 0) if d > 0 else (20, 55, 150)
        return 'rgb(%d,%d,%d)' % _mix((255, 255, 255), base, t)

    o = [f'<svg viewBox="0 0 {W:.1f} {H:.1f}" class="wafer">']
    o.append(f'<rect x="0" y="0" width="{W:.1f}" height="{H:.1f}" fill="{OUTSIDE_C}"/>')
    o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rad:.1f}" fill="{WAFER_DISC_C}" '
             f'stroke="#000000" stroke-width="1"/>')
    # 方位缺口：依 header 的 OrientationMarkLocation 放在對應邊（同 App）
    nx, ny = {'DOWN': (cx, cy + rad), 'UP': (cx, cy - rad),
              'LEFT': (cx - rad, cy), 'RIGHT': (cx + rad, cy)}[notch_pos]
    o.append(f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="{notch_r:.1f}" '
             f'fill="#ffffff" stroke="#000000" stroke-width="1"/>')
    fs = max(6.5, min(sizex, sizey) * 0.36)
    for (dx, dy) in sorted(cells):
        px = ox + (dx - x0) * sizex; py = oy + (y1 - dy) * sizey
        if kind == 'diff':
            v = dies_b.get((dx, dy), 0) - dies_a.get((dx, dy), 0)
            fill = diverge(v)
            txt = ('%+d' % v) if v else '0'
            dark = abs(v) >= mx*0.55
        else:
            v = src.get((dx, dy), 0)
            fill = heat_rgb(v, mx)
            txt = str(v)
            dark = False          # 數字一律純黑
        tip = f'die ({dx},{dy})  A:{dies_a.get((dx,dy),0)}  B:{dies_b.get((dx,dy),0)}'
        o.append(f'<rect x="{px:.1f}" y="{py:.1f}" width="{sizex:.1f}" height="{sizey:.1f}" '
                 f'fill="{fill}" stroke="#000000" stroke-width="1">'
                 f'<title>{_esc(tip)}</title></rect>')
        if show_num:
            o.append(f'<text x="{px+sizex/2:.1f}" y="{py+sizey/2+fs*0.36:.1f}" font-size="{fs:.1f}" '
                     f'text-anchor="middle" fill="{"#ffffff" if dark else "#000000"}" '
                     f'font-family="Segoe UI,system-ui,sans-serif">{txt}</text>')
        if (dx, dy) == (0, 0):
            o.append(f'<rect x="{px+1:.1f}" y="{py+1:.1f}" width="{sizex-2:.1f}" height="{sizey-2:.1f}" '
                     f'fill="none" stroke="{CENTER_DIE_C}" stroke-width="2"/>')
    # 右側色階條（cy 可能偏離畫布中心，夾住避免超出畫布）
    bx = W - barw + 8; bh = min(gh, rad*1.6); bw = 13
    by = max(6.0, min(H - bh - 6.0, cy - bh/2))
    gid = 'g_' + kind
    if kind == 'diff':
        stops = ('<stop offset="0%" stop-color="rgb(255,0,0)"/>'
                 '<stop offset="50%" stop-color="#ffffff"/>'
                 '<stop offset="100%" stop-color="rgb(20,55,150)"/>')
        labs = [(by, '+%d' % mx), (by+bh/2, '0'), (by+bh, '-%d' % mx)]
    else:
        # 分段漸層：上=cap(正紅) → 洋紅 → 珊瑚粉 → 下=0(白)
        stops = ('<stop offset="0%" stop-color="rgb(255,0,0)"/>'
                 '<stop offset="60%" stop-color="rgb(255,102,102)"/>'
                 '<stop offset="60%" stop-color="rgb(255,170,170)"/>'
                 '<stop offset="100%" stop-color="#ffffff"/>')
        labs = [(by, '%d+' % mx), (by+bh/2, '%g' % (mx/2)), (by+bh, '0')]
    o.append(f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">{stops}'
             f'</linearGradient></defs>')
    o.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="url(#{gid})" '
             f'stroke="#000000" stroke-width="0.8"/>')
    for ly, lab in labs:
        o.append(f'<text x="{bx+bw+3}" y="{ly+3.5:.1f}" font-size="9" fill="#1f2733" '
                 f'font-family="Segoe UI,system-ui,sans-serif">{lab}</text>')
    o.append('</svg>')
    return ''.join(o)


_HTML_CSS = """
:root{--ink:#1f2733;--sub:#5b6672;--line:#e6e8ec;--bg:#f6f7f9;--acc:#2f6feb;--dan:#e0533d;--ok:#12a150}
*{box-sizing:border-box}
body{margin:0;padding:28px;background:var(--bg);color:var(--ink);
 font:14px/1.55 "Segoe UI",system-ui,-apple-system,"Noto Sans TC",sans-serif}
h1{font-size:21px;margin:0 0 4px} h2{font-size:15px;margin:26px 0 10px}
.muted{color:var(--sub);font-size:12.5px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:14px}
.files{display:flex;gap:14px;flex-wrap:wrap}
.files div{flex:1;min-width:230px}
.tag{display:inline-block;padding:1px 7px;border-radius:9px;background:#eef2f8;color:var(--sub);font-size:11.5px}
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin:2px 0 4px}
.kpi{flex:1;min-width:120px;background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi .n{font-size:23px;font-weight:700;line-height:1.1}
.kpi .l{font-size:12px;color:var(--sub);margin-top:2px}
.kpi .n{color:var(--ink)}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:6px 9px;text-align:left;white-space:nowrap}
th{background:#fafbfc;color:var(--sub);font-weight:600;position:sticky;top:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.pos{color:var(--ok)} .neg{color:var(--dan)}
.maps{display:flex;gap:18px;flex-wrap:wrap}
.maps figure{margin:0;text-align:center}
.maps figcaption{font-size:12px;color:var(--sub);margin-top:6px}
.wafer{width:340px;height:auto;background:#fff;border:1px solid var(--line);border-radius:8px}
.scroll{max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:8px}
.legend{font-size:12px;color:var(--sub);margin-top:8px}
.scroll.big{max-height:620px}
#dt th.ha,#dt th.hb{background:#f1f3f6;color:var(--ink);text-align:center;
 font-weight:700;letter-spacing:.02em}
#dt td.sep,#dt th.sep{border-left:2px solid #cfd6e0;padding:0;width:2px;background:#f4f6f9}
#dt td.empty{color:#c3cad4}
#dt td.oth,#dt th.oth{text-align:left;font-size:12px;color:var(--sub);white-space:normal;
 max-width:190px}
#dt td.chg{font-weight:700;text-decoration:underline;text-underline-offset:3px;
 text-decoration-thickness:1.5px;text-decoration-color:#9aa4b2}
#dt tbody tr:nth-child(even){background:#fcfcfd}
#dt tbody tr:hover{background:#f4f6f9}
.pill{display:inline-block;padding:0 7px;border:1px solid #c8cfd9;border-radius:3px;
 font-size:11px;font-weight:600;color:var(--sub);background:#fff;margin-right:3px;white-space:nowrap}
.filters{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.fb{border:1px solid var(--line);background:#fff;border-radius:16px;padding:5px 12px;
 font:inherit;font-size:12.5px;color:var(--sub);cursor:pointer}
.fb:hover{background:#f2f5f9}
.fb.on{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600}
#q{border:1px solid var(--line);border-radius:16px;padding:5px 12px;
 font:inherit;font-size:12.5px;min-width:200px}
.filters select{border:1px solid var(--line);border-radius:16px;padding:5px 10px;
 font:inherit;font-size:12.5px;background:#fff;color:var(--sub);max-width:170px}
.cnt{margin-left:auto;font-size:12.5px;color:var(--sub);white-space:nowrap}
.pager{display:flex;gap:6px;align-items:center;margin-top:10px;font-size:12.5px;color:var(--sub)}
.pager button{border:1px solid var(--line);background:#fff;border-radius:14px;
 padding:4px 12px;font:inherit;font-size:12.5px;color:var(--ink);cursor:pointer}
.pager button:hover:not(:disabled){background:#f2f5f9}
.pager button:disabled{color:#c3cad4;cursor:default}
.pager select{border:1px solid var(--line);border-radius:14px;padding:4px 8px;
 font:inherit;font-size:12.5px;margin-left:auto}
#pinfo{padding:0 8px}
.sw{display:inline-block;width:11px;height:11px;border-radius:3px;vertical-align:-1px;margin:0 4px 0 12px}
"""



_HTML_JS = """<script>
(function(){
  var DATA = JSON.parse(document.getElementById('diffdata').textContent);
  var TXT  = {added:'新增', removed:'消失', reclass:'分類不同',
              moved:'座標位移', changed:'欄位變更'};
  var tb    = document.getElementById('tb');
  var q     = document.getElementById('q');
  var cnt   = document.getElementById('cnt');
  var fcls  = document.getElementById('fcls');
  var fdie  = document.getElementById('fdie');
  var ffld  = document.getElementById('ffld');
  var pinfo = document.getElementById('pinfo');
  var psize = document.getElementById('psize');
  var cur = 'all', page = 0, size = 200, view = [], timer = null;

  // 每列先算好搜尋字串，之後打字就不用重組
  DATA.forEach(function(d){
    d.q = ((d.a ? d.a[0] : '') + ' ' + (d.b ? d.b[0] : '') + ' ' +
           d.d + ' ' + d.c.join(' ') + ' ' + d.f.join(' ')).toLowerCase();
  });

  function esc(v){
    return String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
  var KEYS = ['id','xi','yi','x','y','cls'];
  function cells(arr, marks){
    if (!arr) return '<td class="num empty">—</td>'.repeat(6) + '<td class="oth"></td>';
    var out = '';
    for (var i = 0; i < 6; i++){
      out += '<td class="num' + (marks.indexOf(KEYS[i]) >= 0 ? ' chg' : '') + '">'
           + esc(arr[i]) + '</td>';
    }
    return out + '<td class="oth' + (arr[6] ? ' chg' : '') + '">' + esc(arr[6]) + '</td>';
  }
  function render(){
    var lo = size ? page * size : 0;
    var hi = size ? Math.min(lo + size, view.length) : view.length;
    var html = [];
    for (var i = lo; i < hi; i++){
      var d = view[i];
      var pill = d.s.map(function(x){
        return '<span class="pill ' + x + '">' + TXT[x] + '</span>'; }).join(' ');
      html.push('<tr class="' + d.s[0] + '"><td>' + pill + '</td>'
                + cells(d.a, d.m) + '<td class="sep"></td>' + cells(d.b, d.m) + '</tr>');
    }
    tb.innerHTML = html.join('') ||
      '<tr><td colspan="16" class="muted">沒有符合條件的差異。</td></tr>';
    var pages = size ? Math.max(1, Math.ceil(view.length / size)) : 1;
    if (pinfo) pinfo.textContent = size
      ? ('第 ' + (view.length ? page + 1 : 0) + ' / ' + pages + ' 頁'
         + '（第 ' + (view.length ? lo + 1 : 0) + '–' + hi + ' 列）')
      : ('全部 ' + view.length + ' 列');
    ['pfirst','pprev'].forEach(function(id){
      document.getElementById(id).disabled = (page <= 0 || !size); });
    ['pnext','plast'].forEach(function(id){
      document.getElementById(id).disabled = (page >= pages - 1 || !size); });
  }
  function apply(reset){
    var t  = (q.value || '').trim().toLowerCase();
    var vc = fcls ? fcls.value : '';
    var vd = fdie ? fdie.value : '';
    var vf = ffld ? ffld.value : '';
    view = DATA.filter(function(d){
      return (cur === 'all' || d.s.indexOf(cur) >= 0)
          && (!vc || d.c.indexOf(vc) >= 0)
          && (!vd || d.d === vd)
          && (!vf || d.f.indexOf(vf) >= 0)
          && (!t  || d.q.indexOf(t) >= 0);
    });
    if (reset !== false) page = 0;
    if (cnt) cnt.textContent = '顯示 ' + view.length + ' / ' + DATA.length + ' 列';
    render();
  }

  document.querySelectorAll('.fb').forEach(function(b){
    b.onclick = function(){
      document.querySelectorAll('.fb').forEach(function(x){ x.classList.remove('on'); });
      b.classList.add('on'); cur = b.getAttribute('data-f'); apply();
    };
  });
  [fcls, fdie, ffld].forEach(function(s){ if (s) s.onchange = function(){ apply(); }; });
  q.addEventListener('input', function(){
    clearTimeout(timer); timer = setTimeout(apply, 120);
  });
  psize.onchange = function(){ size = parseInt(psize.value, 10) || 0; page = 0; render(); };
  document.getElementById('pfirst').onclick = function(){ page = 0; render(); };
  document.getElementById('pprev').onclick  = function(){ if (page > 0) { page--; render(); } };
  document.getElementById('pnext').onclick  = function(){
    var pages = size ? Math.ceil(view.length / size) : 1;
    if (page < pages - 1) { page++; render(); } };
  document.getElementById('plast').onclick  = function(){
    page = size ? Math.max(0, Math.ceil(view.length / size) - 1) : 0; render(); };
  apply();
})();
</script>"""


def _rows_table(rows, cols, unit, limit=800):
    if not rows:
        return '<p class="muted">（無）</p>'
    head = ''.join(f'<th class="num">{_esc(c)}</th>' for c in cols)
    body = []
    for r in rows[:limit]:
        body.append('<tr>' + ''.join(f'<td class="num">{_esc(v)}</td>' for v in r) + '</tr>')
    more = ('' if len(rows) <= limit else
            f'<p class="muted">僅顯示前 {limit} 筆，共 {len(rows)} 筆。</p>')
    return (f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>{more}')


def compare_html(res):
    """把 compare() 的結果產生成一份自包含的 HTML 報告。"""
    import datetime
    a, b = res['a'], res['b']
    fu = 1000.0 if a['unit'] == 'µm' else 1.0     # nm → 顯示單位
    du = a['unit']

    def fmt(v):
        return f"{v/fu:.3f}" if du == 'µm' else f"{v:.0f}"

    kpi = f"""<div class="kpis">
      <div class="kpi"><div class="n">{res['matched']}</div><div class="l">配對成功</div></div>
      <div class="kpi add"><div class="n">+{len(res['added'])}</div><div class="l">只在 B（新增）</div></div>
      <div class="kpi rem"><div class="n">-{len(res['removed'])}</div><div class="l">只在 A（消失）</div></div>
      <div class="kpi rc"><div class="n">{len(res['reclass'])}</div><div class="l">分類不同</div></div>
      <div class="kpi"><div class="n">{len(res['moved'])}</div><div class="l">座標位移</div></div>
      <div class="kpi"><div class="n">{len(res.get('changed', ()))}</div><div class="l">其他欄位變更</div></div>
    </div>"""

    hdr = '<p class="muted">兩份檔案的 header 欄位完全相同。</p>'
    if res['header']:
        rows = ''.join(
            f'<tr><td>{_esc(k)}</td><td>{_esc(va if va is not None else "—")}</td>'
            f'<td>{_esc(vb if vb is not None else "—")}</td></tr>'
            for k, va, vb in res['header'])
        hdr = (f'<table><thead><tr><th>欄位</th><th>A</th><th>B</th></tr></thead>'
               f'<tbody>{rows}</tbody></table>')

    crows = []
    for c, na, nb, name in res['classes']:
        d = nb - na
        cls = 'pos' if d > 0 else ('neg' if d < 0 else 'muted')
        crows.append(f'<tr><td>{_esc(c)}</td><td>{_esc(name or "")}</td>'
                     f'<td class="num">{na}</td><td class="num">{nb}</td>'
                     f'<td class="num {cls}">{d:+d}</td></tr>')
    cls_tbl = (f'<table><thead><tr><th>Class</th><th>名稱</th><th class="num">A</th>'
               f'<th class="num">B</th><th class="num">Δ</th></tr></thead>'
               f'<tbody>{"".join(crows)}</tbody></table>')

    # ---- 並排差異表：資料存成 JSON，由瀏覽器只渲染當前頁 ----
    # （整份差異都在檔案裡，不做任何截斷；但一次只把一頁放進 DOM，
    #   否則數萬列的表格光是解析就要十幾秒）
    import json as _json
    drows = diff_rows(res)
    data = []
    for st, pa, pb, fields, chg in drows:
        sts = sorted(st, key=STATUS_ORDER.index)
        ref = pa if pa is not None else pb

        def side(p, which):
            if p is None:
                return None
            oth = ('  '.join('%s %s' % (c, (va if which == 0 else vb))
                             for c, va, vb in chg)) if chg else ''
            return [p['id'], str(p['die'][0]), str(p['die'][1]),
                    fmt(p['x']), fmt(p['y']), p['cls'], oth]

        data.append({
            's': sts,
            'a': side(pa, 0), 'b': side(pb, 1),
            'm': sorted(fields),
            'd': '%d,%d' % ref['die'],
            'c': sorted({p['cls'] for p in (pa, pb) if p is not None}),
            'f': sorted({c for c, _x, _y in chg}),
        })
    payload = _json.dumps(data, separators=(',', ':'), ensure_ascii=False) \
                   .replace('</', '<\\/')

    colhead = (''.join('<th class="num">%s</th>' % c for c in
                       ('DEFECTID', 'XINDEX', 'YINDEX', 'XREL (%s)' % du,
                        'YREL (%s)' % du, 'CLASS'))
               + '<th class="oth">其他欄位</th>')
    head = ('<tr><th rowspan="2">狀態</th>'
            '<th colspan="7" class="ha">A — %s</th>' % _esc(a['name']) +
            '<th rowspan="2" class="sep"></th>'
            '<th colspan="7" class="hb">B — %s</th></tr>' % _esc(b['name']) +
            '<tr>' + colhead + colhead + '</tr>')

    fbtn = ('<button class="fb on" data-f="all">全部 (%d)</button>' % len(drows) +
            ''.join('<button class="fb" data-f="%s">%s (%d)</button>'
                    % (k, STATUS_TXT[k], len(res.get(k, ())))
                    for k in ('added', 'removed', 'reclass', 'moved', 'changed')))

    all_cls = sorted({c for d in data for c in d['c']},
                     key=lambda v: (0, int(v)) if v.lstrip('-').isdigit() else (1, v))
    all_die = sorted({d['d'] for d in data},
                     key=lambda t: (int(t.split(',')[1]), int(t.split(',')[0])))
    all_fld = sorted({f for d in data for f in d['f']})

    def sel(sid, label, opts):
        o = ''.join('<option value="%s">%s</option>' % (_esc(v), _esc(v)) for v in opts)
        return ('<select id="%s"><option value="">%s</option>%s</select>'
                % (sid, _esc(label), o))

    drops = sel('fcls', '所有 class', all_cls) + sel('fdie', '所有 die', all_die)
    if all_fld:
        drops += sel('ffld', '所有變更欄位', all_fld)

    pager = ('<div class="pager"><button id="pfirst">&laquo;</button>'
             '<button id="pprev">上一頁</button><span id="pinfo"></span>'
             '<button id="pnext">下一頁</button><button id="plast">&raquo;</button>'
             '<select id="psize"><option>200</option><option>500</option>'
             '<option>1000</option><option value="0">全部顯示</option></select></div>')

    diff_tbl = ('<div class="filters">' + fbtn + drops +
                '<input id="q" placeholder="搜尋 DEFECTID / die / class…">'
                '<span id="cnt" class="cnt"></span></div>'
                '<div class="scroll big"><table id="dt"><thead>' + head +
                '</thead><tbody id="tb"></tbody></table></div>' + pager +
                '<script id="diffdata" type="application/json">' + payload + '</script>')

    srows = ''
    if res['summary_cols']:
        head = ''.join(f'<th class="num">{_esc(c)}</th>' for c in res['summary_cols'])
        def blk(tag, rs):
            return ''.join('<tr><td>' + tag + '</td>' +
                           ''.join(f'<td class="num">{_esc(v)}</td>' for v in r) + '</tr>'
                           for r in rs)
        srows = (f'<table><thead><tr><th>檔案</th>{head}</tr></thead><tbody>'
                 f'{blk("A", res["summary_a"])}{blk("B", res["summary_b"])}</tbody></table>')

    mode_txt = ('依 DEFECTID 配對' if res['mode'] == 'id'
                else f'依 die + 座標配對（容差 {res["tol_nm"]/fu:g} {du}）')
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<title>KLARF Compare — {_esc(a['name'])} vs {_esc(b['name'])}</title>
<style>{_HTML_CSS}</style></head><body>
<h1>KLARF 比對報告</h1>
<p class="muted">{_esc(mode_txt)} · 產生於 {ts} · KLIP</p>

<div class="card"><div class="files">
  <div><span class="tag">A</span> <b>{_esc(a['name'])}</b><br>
    <span class="muted">KLARF {_esc(a['version'])} · 座標 {_esc(a['unit'])} · {a['n']} 筆 defect</span></div>
  <div><span class="tag">B</span> <b>{_esc(b['name'])}</b><br>
    <span class="muted">KLARF {_esc(b['version'])} · 座標 {_esc(b['unit'])} · {b['n']} 筆 defect</span></div>
</div></div>

{kpi}

<div class="card"><h2 style="margin-top:0">Wafer 分佈</h2><div class="maps">
  <figure>{_svg_wafer(a['dies'], b['dies'], 'a', geom=res.get('geom'))}<figcaption>A：{a['n']} 筆</figcaption></figure>
  <figure>{_svg_wafer(a['dies'], b['dies'], 'b', geom=res.get('geom'))}<figcaption>B：{b['n']} 筆</figcaption></figure>
  <figure>{_svg_wafer(a['dies'], b['dies'], 'diff', geom=res.get('geom'))}<figcaption>差異（B − A）</figcaption></figure>
</div>
<div class="legend">A / B 圖採白→深紅漸層，色階上限 10（≥10 一律最深紅，避免極端值壓縮低值的解析度）；
  格內數字為該 die 的 defect 數，<span class="sw" style="background:#12b83a"></span>綠框為中心 die (0,0)。
  差異圖：<span class="sw" style="background:#8f0f06"></span>B 較多
  <span class="sw" style="background:#143796"></span>A 較多
  <span class="sw" style="background:#ffffff;border:1px solid #ccc"></span>相同。</div>
</div>

<div class="card"><h2 style="margin-top:0">逐筆差異　（左 = A　｜　右 = B）</h2>{diff_tbl}</div>

<div class="card"><h2 style="margin-top:0">Header 差異</h2>{hdr}</div>
<div class="card"><h2 style="margin-top:0">Class 分佈</h2>{cls_tbl}</div>
<div class="card"><h2 style="margin-top:0">SummaryList</h2>{srows or '<p class="muted">（無）</p>'}</div>

{_HTML_JS}
</body></html>"""

#!/usr/bin/env python3
# ADEPT ← GLAS 匯出健檢 — authored 2026-08-18 (F11 Region-3 準備).
"""看一個 GLAS 匯出資料夾，印出一份**可以安心貼出來的**報告。

為什麼需要這支
--------------
Region-3（GDS mode）要吃 GLAS 匯出的 ``<id>_label.png`` + manifest。使用者手上
有真實資料，但那台機器**只能複製文字出來**（`AGENTS.md` §2 的兩台機器）。
而卡片要接對，猜不出來的東西全都是文字：欄位名、id 的格式、檔名慣例。
猜錯的下場不是報錯，是**整批安靜對不上**。

所以這支做兩件事：

1. **把匯出資料夾檢查一遍**，對照 ADEPT 真正需要的幾件事給 PASS / FAIL；
2. **把結果遮蔽成可以貼的文字** —— 預設不印任何廠內識別碼（lot／wafer／
   device／layer 名／路徑／DEFECTID 的值），只印**結構與格式**。
   要看真值請自己加 ``--reveal``（那份**不要**貼出來）。

    python tools/check_glas_export.py D:\\some\\export_dir
    python tools/check_glas_export.py <dir> --klarf <那批的 KLARF>
    python tools/check_glas_export.py <dir> --images <RSEM 影像資料夾>

它**不連網路**、**不寫任何檔案**、模組層只 import 標準函式庫
（`tests/test_offline_tools.py` 會擋）。PNG 是自己讀的（`zlib` + IHDR/IDAT），
所以**不需要 OpenCV 也跑得動** —— 而且那正好是要查的問題之一：label 圖到底是
單通道 uint8 還是 palette／RGB。

⚠ **廠內那份 GLAS 比 GitHub 上的新**（2026-08-18 實測）：manifest 是
``mmh-gds-overlay-v4``，逐列帶 ``id_source`` / ``page`` / ``width_px`` /
``height_px`` / ``nm_per_px``。也就是 `docs/GLAS-INTERFACE.md` §4 的「建議 3」
**已經做完了** —— 有那幾格就不必猜 join key、也不必自己去比尺寸。
這支兩種都吃：v4 用 manifest 自己的欄位，v3 退回去比實際檔案。

這支檢查的每一條，都是讀 GLAS 的程式碼讀出來的
----------------------------------------------
（GLAS commit bef5492 = v3；v4 的部分是從一份真實匯出的報告看到的）

* ``glas/core/overlay_export.py::export_one_image`` —— 檔名是
  ``f"{base}_label.png"``，而 ``base = _safe_name(image_id)``，
  **`_safe_name` 會把非 ``[A-Za-z0-9-_.]`` 的字元換成底線**。所以
  「檔名就是 ``<DEFECTID>_label.png``」只在 id 本來就乾淨時成立 ——
  ADEPT 配對時必須套同一個轉換。這支會告訴你有沒有 id 被改過。
* ``glas/core/fine_align.py::render_label_image`` —— ``lbl[m > 0] = label_id``，
  **後面的層會蓋掉前面的層**。所以某一層可能在某些影像上被蓋到一個像素都不剩，
  而 manifest 的 ``label_map`` 仍然列著它。這支會數每個 id 的像素。
* ``gds_align_tool.py::_write_manifest`` —— ``overlay_manifest.json``；
  ``label_map`` **只有匯出時有開 label 才會寫進去**。而 ``overlay_manifest.csv``
  是用**平台預設編碼**寫的（Windows 上是 cp950），JSON 那一份才安全
  （``json.dump`` 預設 ``ensure_ascii=True``）—— 所以這支只讀 JSON。
* ``gds_align_tool.py::ALIGNMENT_COLUMNS`` —— alignment 檔的**檔名與資料夾都是
  使用者在另一個對話框選的**，所以這支是靠 schema 字串去找它，不是靠檔名，
  而且它常常根本不在匯出資料夾裡（``--alignment`` 可以直接指過去）。

它還會量一件**設計用**的事
--------------------------
把抽樣的那張 label 拆一次，印出每一層的 **pieces（連通元件）** 與
**rectangles（精確矩形分解）**。那不是健康檢查，是 Region-3 的設計輸入：
rectangles 是 ADEPT 真的要存幾個框（既有 Region 卡的 ``max_boxes`` 預設 64，
在這條路上會安靜地砍掉大部分），pieces 是「一份」有幾個。兩者差很大時，
意思是那一層正被後面畫的層切碎。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import struct
import sys
import zlib
from typing import Dict, List, Optional, Tuple

# 讓 `python tools/check_glas_export.py` 從任何工作目錄都 import 得到 adept
# （只有 --klarf 那一段需要它，而它是**函式內** lazy import —— 模組層維持
# stdlib-only，`tests/test_offline_tools.py` 會擋）。跟 make_sample_rsem.py 同招。
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

#: GLAS 寫出來的五種 PNG 後綴（`overlay_export.export_one_image`）。
SUFFIXES = ("_raw.png", "_overlay.png", "_gray.png", "_label.png",
            "_label_view.png")

#: manifest 的固定檔名（`_write_manifest`）。
MANIFEST_JSON = "overlay_manifest.json"
MANIFEST_CSV = "overlay_manifest.csv"

#: ADEPT 需要的 manifest 欄位（`fine_align.OVERLAY_MANIFEST_COLS` 的子集）。
NEEDED_COLS = ("image_id", "label_png", "status")

#: **v4 才有的欄位**（2026-08-18 從一份真實匯出看到的，GitHub 上的 GLAS 還是
#: v3）。它們正好就是 `GLAS-INTERFACE.md` §4 要的東西 —— 有了就不必自己猜：
#:
#: * ``id_source`` —— ``image_id`` 到底是 KLARF 的 DEFECTID 還是檔名 stem。
#:   猜錯的話**整批對不上，而且是安靜的**，所以這一格比什麼都值錢。
#: * ``width_px`` / ``height_px`` —— 不必再拿另一個檔案來比尺寸。
#: * ``nm_per_px`` —— 逐張的（alignment CSV 那一份是全批一個值）。
#: * ``page`` —— 多頁 TIFF 的頁碼（RSEM 是空的，那是對的）。
V4_COLS = ("id_source", "page", "width_px", "height_px", "nm_per_px")

#: alignment 檔的 schema（檔名是使用者選的，所以只能靠這個認）。
ALIGNMENT_SCHEMA = "mmh-gds-alignment-v1"
OVERLAY_SCHEMA_PREFIX = "mmh-gds-overlay-"

#: 這些 key 的值是**列舉或數字**，印原文不會洩漏廠內識別碼。
SAFE_KEYS = frozenset((
    "id", "fg_glv", "score", "status", "schema", "columns",
    "coarse_dx_nm", "coarse_dy_nm", "fine_dx_nm", "fine_dy_nm", "nm_per_px",
))


# --------------------------------------------------------------------------- #
# GLAS 的檔名轉換 —— 這一段必須跟 GLAS 一字不差
# --------------------------------------------------------------------------- #
def safe_name(s: str) -> str:
    """``glas/core/overlay_export.py::_safe_name`` 的複本。

    **抄一份過來是刻意的**：這支要能在只有 ADEPT、沒有 GLAS 的機器上跑
    （公司機兩個 repo 不一定都在）。抄的是六行純字串處理，而且上面的檔頭
    註明了出處與 commit —— 那是 `docs/HANDOVER.md` 講的 vendoring 慣例。
    """
    out = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in str(s))
    return out or "image"


# --------------------------------------------------------------------------- #
# 遮蔽 —— 預設什麼都不洩漏
# --------------------------------------------------------------------------- #
class Masker:
    """把每一個可能是識別碼的字串換成穩定的代號，並保留它的**格式**。

    格式要留是因為那正是 ADEPT 要對的東西：id 有沒有補零、是不是純數字、
    有沒有非 ASCII —— 這幾件事決定配對寫法，而它們本身不洩漏任何東西。
    """

    def __init__(self, reveal: bool = False):
        self.reveal = bool(reveal)
        self._seen: Dict[Tuple[str, str], str] = {}
        self._n: Dict[str, int] = {}

    def alias(self, kind: str, value: object) -> str:
        text = "" if value is None else str(value)
        if self.reveal:
            return text
        if text == "":
            return "(empty)"
        key = (kind, text)
        if key not in self._seen:
            self._n[kind] = self._n.get(kind, 0) + 1
            self._seen[key] = "%s%d" % (kind, self._n[kind])
        return self._seen[key]

    @staticmethod
    def shape_of(value: object) -> str:
        """一個字串的「長相」—— 長度、字元種類、有沒有前導零。"""
        text = "" if value is None else str(value)
        if not text:
            return "empty"
        bits = ["len=%d" % len(text)]
        if text.isdigit():
            bits.append("all-digits")
            if len(text) > 1 and text[0] == "0":
                bits.append("zero-padded")
        elif text.isalnum():
            bits.append("alnum")
        else:
            bits.append("has-punctuation")
        if not all(ord(c) < 128 for c in text):
            bits.append("NON-ASCII")
        return " ".join(bits)


# --------------------------------------------------------------------------- #
# PNG —— 純標準函式庫（不需要 OpenCV，而「它是不是單通道」正是要查的事）
# --------------------------------------------------------------------------- #
#: PNG colour type -> 白話。**2 / 3 / 6 就是那個安靜的坑**：ADEPT 讀進來會被
#: 灰階化，label id 1、2、3 被混成一堆不存在的值，而它不會報錯。
COLOR_TYPES = {0: "grayscale", 2: "RGB", 3: "palette",
               4: "grayscale+alpha", 6: "RGBA"}


def png_header(path: str) -> Optional[Dict[str, int]]:
    """讀 IHDR。不是 PNG 就回 ``None``。"""
    try:
        with open(path, "rb") as f:
            sig = f.read(8)
            if sig != b"\x89PNG\r\n\x1a\n":
                return None
            length = struct.unpack(">I", f.read(4))[0]
            if f.read(4) != b"IHDR" or length < 13:
                return None
            w, h, depth, ctype, comp, filt, inter = struct.unpack(
                ">IIBBBBB", f.read(13))
    except (OSError, struct.error):
        return None
    return {"width": w, "height": h, "bit_depth": depth, "color_type": ctype,
            "compression": comp, "filter": filt, "interlace": inter}


def _idat(path: str) -> bytes:
    """把所有 IDAT chunk 接起來（PNG 允許切成好幾塊）。"""
    out = []
    with open(path, "rb") as f:
        f.read(8)
        while True:
            head = f.read(8)
            if len(head) < 8:
                break
            length, kind = struct.unpack(">I", head[:4])[0], head[4:]
            data = f.read(length)
            f.read(4)                       # CRC，不驗（我們只是要看內容）
            if kind == b"IDAT":
                out.append(data)
            elif kind == b"IEND":
                break
    return b"".join(out)


def _unfilter(raw: bytes, width: int, height: int) -> Optional[bytearray]:
    """PNG 的五種列濾波（每像素 1 byte 的情形）。"""
    stride = width
    out = bytearray(stride * height)
    pos = 0
    prev = bytearray(stride)
    for y in range(height):
        if pos >= len(raw):
            return None
        ft = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        if len(line) < stride:
            return None
        pos += stride
        if ft == 1:                                     # Sub
            for i in range(1, stride):
                line[i] = (line[i] + line[i - 1]) & 0xFF
        elif ft == 2:                                   # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:                                   # Average
            for i in range(stride):
                left = line[i - 1] if i else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ft == 4:                                   # Paeth
            for i in range(stride):
                a = line[i - 1] if i else 0
                b = prev[i]
                c = prev[i - 1] if i else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        elif ft != 0:
            return None
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def png_pixels(path: str):
    """解出來的像素（``bytearray``，row-major）。讀不到回 ``None``。"""
    head = png_header(path)
    if head is None or head["interlace"] or head["bit_depth"] != 8 \
            or head["color_type"] not in (0, 3):
        return None
    try:
        raw = zlib.decompress(_idat(path))
    except (zlib.error, OSError):
        return None
    return _unfilter(raw, head["width"], head["height"])


def png_value_counts(path: str) -> Tuple[Optional[Dict[int, int]], str]:
    """label 圖裡每一個值出現幾次。回傳 ``(counts, 讀不到的原因)``。

    只支援 **8-bit、非交錯、單通道（灰階或 palette）** —— 那正好是 GLAS 寫出來
    的形狀（`cv2.imwrite` 一個 2-D uint8 陣列）。**其他形狀不硬讀**：讀不到本身
    就是答案（「這張圖不是 ADEPT 假設的那一種」），硬猜只會給一個錯的直方圖。
    """
    head = png_header(path)
    if head is None:
        return None, "not a PNG"
    if head["interlace"]:
        return None, "interlaced (Adam7) — not read"
    if head["bit_depth"] != 8:
        return None, "bit depth %d (expected 8)" % head["bit_depth"]
    if head["color_type"] not in (0, 3):
        return None, "colour type %d (%s) — more than one channel" % (
            head["color_type"], COLOR_TYPES.get(head["color_type"], "?"))
    try:
        raw = zlib.decompress(_idat(path))
    except (zlib.error, OSError) as exc:
        return None, "could not inflate (%s)" % exc.__class__.__name__
    flat = _unfilter(raw, head["width"], head["height"])
    if flat is None:
        return None, "unexpected row filter or truncated data"
    counts: Dict[int, int] = {}
    for b in flat:
        counts[b] = counts.get(b, 0) + 1
    return counts, ""


# --------------------------------------------------------------------------- #
# 一層 mask -> 幾塊、幾個矩形  ——  Region-3 的設計就靠這兩個數字
# --------------------------------------------------------------------------- #
def _runs(flat, width: int, height: int, value: int):
    """一層的水平 run：``[(row, x0, x1), …]``（``x1`` 不含）。"""
    out = []
    for y in range(height):
        base = y * width
        x = 0
        while x < width:
            if flat[base + x] == value:
                x0 = x
                while x < width and flat[base + x] == value:
                    x += 1
                out.append((y, x0, x))
            else:
                x += 1
    return out


def rect_count(runs) -> int:
    """把 run 往下合併成**精確的**矩形分解，回傳矩形數。

    合併規則：上一列有一段 ``[x0, x1)`` **完全一樣**的 run，就是同一個矩形往下
    長一格。Manhattan 的 layout 這樣拆是**等價不是近似**（站點的區域本來就都是
    矩形），所以這個數字就是 ADEPT 要放幾個框。
    """
    open_at = {}                       # (x0, x1) -> 還在往下長的矩形
    total = 0
    prev_row = None
    for row, x0, x1 in runs:
        if prev_row is not None and row != prev_row:
            for key in [k for k, r in open_at.items() if r != prev_row]:
                del open_at[key]
        key = (x0, x1)
        if key in open_at and open_at[key] == row - 1:
            open_at[key] = row
        else:
            total += 1
            open_at[key] = row
        prev_row = row
    return total


def blob_count(runs) -> int:
    """幾個**連通元件**（4-連通，以 run 為單位做 union-find）。

    這個數字回答的是完全不同的問題：矩形是**切片**，連通元件才是「一份」。
    非週期的 layout 上這兩個數字差很多，而 ADEPT 的 ``<name>_center`` /
    ``<name>_others`` 只有在「一份」講得通的時候才有意義。
    """
    parent = list(range(len(runs)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    by_row = {}
    for i, (row, _x0, _x1) in enumerate(runs):
        by_row.setdefault(row, []).append(i)
    for row in sorted(by_row):
        above = by_row.get(row - 1, ())
        for i in by_row[row]:
            _r, x0, x1 = runs[i]
            for j in above:
                _r2, a0, a1 = runs[j]
                if a0 < x1 and x0 < a1:
                    union(i, j)
    return len({find(i) for i in range(len(runs))})


# --------------------------------------------------------------------------- #
# TIFF —— 只要寬高（RSEM 的影像可能是 .tif）
# --------------------------------------------------------------------------- #
def tiff_size(path: str) -> Optional[Tuple[int, int]]:
    """第一個 IFD 的 ImageWidth(256) / ImageLength(257)。"""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
            if len(head) < 8 or head[:2] not in (b"II", b"MM"):
                return None
            end = "<" if head[:2] == b"II" else ">"
            if struct.unpack(end + "H", head[2:4])[0] != 42:
                return None
            f.seek(struct.unpack(end + "I", head[4:8])[0])
            n = struct.unpack(end + "H", f.read(2))[0]
            dims: Dict[int, int] = {}
            for _ in range(n):
                entry = f.read(12)
                if len(entry) < 12:
                    break
                tag, typ = struct.unpack(end + "HH", entry[:4])
                if tag in (256, 257):
                    dims[tag] = (struct.unpack(end + "H", entry[8:10])[0]
                                 if typ == 3 else
                                 struct.unpack(end + "I", entry[8:12])[0])
            if 256 in dims and 257 in dims:
                return dims[256], dims[257]
    except (OSError, struct.error):
        return None
    return None


def image_size(path: str) -> Optional[Tuple[int, int]]:
    """認得的格式就回 ``(寬, 高)``，不認得回 ``None``。"""
    head = png_header(path)
    if head is not None:
        return head["width"], head["height"]
    return tiff_size(path)


# --------------------------------------------------------------------------- #
# 報告
# --------------------------------------------------------------------------- #
class Report:
    """一疊文字行 + 一份 PASS / FAIL 清單。"""

    def __init__(self):
        self.lines: List[str] = []
        self.checks: List[Tuple[str, str, str]] = []

    def head(self, title: str) -> None:
        self.lines.append("")
        self.lines.append("== %s " % title + "=" * max(0, 58 - len(title)))

    def say(self, text: str = "") -> None:
        self.lines.append(text)

    def check(self, verdict: str, what: str, detail: str = "") -> None:
        """``verdict`` 是 PASS / FAIL / WARN / SKIP。"""
        self.checks.append((verdict, what, detail))

    def render(self) -> str:
        out = list(self.lines)
        out.append("")
        out.append("== WHAT ADEPT NEEDS " + "=" * 40)
        for verdict, what, detail in self.checks:
            out.append("  [%-4s] %s" % (verdict, what))
            if detail:
                out.append("         %s" % detail)
        bad = sum(1 for v, _w, _d in self.checks if v == "FAIL")
        warn = sum(1 for v, _w, _d in self.checks if v == "WARN")
        out.append("")
        out.append("  %d fail, %d warn, %d checks total"
                   % (bad, warn, len(self.checks)))
        return "\n".join(out)


def scan_folder(export_dir: str, rep: Report, m: Masker) -> Dict[str, List[str]]:
    """資料夾裡有什麼 —— 依後綴分類，並印出檔名的**樣式**而不是檔名。"""
    rep.head("FOLDER")
    try:
        names = sorted(os.listdir(export_dir))
    except OSError as exc:
        rep.say("cannot list the folder: %s" % exc.__class__.__name__)
        rep.check("FAIL", "the export folder can be read")
        return {}

    by_suffix: Dict[str, List[str]] = {s: [] for s in SUFFIXES}
    others: List[str] = []
    for name in names:
        for suf in SUFFIXES:
            if name.endswith(suf):
                by_suffix[suf].append(name)
                break
        else:
            others.append(name)

    for suf in SUFFIXES:
        rep.say("  *%-16s %d file(s)" % (suf, len(by_suffix[suf])))
    rep.say("  other files      %d: %s"
            % (len(others), ", ".join(sorted(
                {os.path.splitext(o)[1] or "(no ext)" for o in others}))))
    rep.say("  subfolders       %d"
            % sum(1 for n in names if os.path.isdir(os.path.join(export_dir, n))))

    if by_suffix["_label.png"]:
        stem = by_suffix["_label.png"][0][:-len("_label.png")]
        rep.say("")
        rep.say("  filename pattern:  <id>_label.png   (id: %s)"
                % Masker.shape_of(stem))
        rep.check("PASS", "label PNGs are present",
                  "%d of them" % len(by_suffix["_label.png"]))
    else:
        rep.check("FAIL", "label PNGs are present",
                  "no *_label.png in this folder — was “export label” on?")
    return by_suffix


def read_manifest(export_dir: str, rep: Report, m: Masker) -> Dict[str, object]:
    """``overlay_manifest.json`` —— 結構、欄位、label_map。"""
    rep.head("MANIFEST")
    path = os.path.join(export_dir, MANIFEST_JSON)
    if not os.path.isfile(path):
        rep.say("  %s: NOT FOUND" % MANIFEST_JSON)
        rep.check("FAIL", "overlay_manifest.json exists",
                  "ADEPT needs it for label id -> layer name")
        return {}
    raw = open(path, "rb").read()
    enc = "utf-8-sig" if raw[:3] == b"\xef\xbb\xbf" else "utf-8"
    try:
        doc = json.loads(raw.decode(enc))
    except (UnicodeDecodeError, ValueError) as exc:
        rep.say("  cannot parse: %s" % exc.__class__.__name__)
        rep.say("  (GLAS writes it with the platform default encoding —"
                " non-ASCII layer names can land as cp950/big5 here)")
        rep.check("FAIL", "overlay_manifest.json parses as UTF-8 JSON",
                  str(exc)[:80])
        return {}

    schema = str(doc.get("schema", ""))
    rep.say("  schema        %s" % (schema or "(missing)"))
    rep.say("  encoding      %s%s" % (enc, "  (has BOM)" if enc.endswith("sig")
                                      else ""))
    rep.say("  top-level     %s" % ", ".join(sorted(doc.keys())))
    rep.check("PASS" if schema.startswith(OVERLAY_SCHEMA_PREFIX) else "WARN",
              "manifest schema is a GLAS overlay manifest",
              "" if schema.startswith(OVERLAY_SCHEMA_PREFIX)
              else "got %r, expected %s*" % (schema, OVERLAY_SCHEMA_PREFIX))

    rows = list(doc.get("images") or [])
    cols = list(doc.get("columns") or (sorted(rows[0]) if rows else []))
    rep.say("  columns       %s" % ", ".join(str(c) for c in cols))
    rep.say("  rows          %d" % len(rows))
    missing = [c for c in NEEDED_COLS if c not in cols]
    rep.check("PASS" if not missing else "FAIL",
              "the manifest has the columns ADEPT reads",
              "" if not missing else "missing: %s" % ", ".join(missing))
    have_v4 = [c for c in V4_COLS if c in cols]
    if "width_px" in cols and "height_px" in cols:
        rep.check("PASS", "per-row image size (width_px / height_px)",
                  "this manifest has it — GLAS-INTERFACE.md §4 “建議 3” is done")
    else:
        rep.check("WARN", "per-row image size (width_px / height_px)",
                  "not in this schema — GLAS-INTERFACE.md §4 “建議 3”; "
                  "this script compares the actual files instead")
    if have_v4:
        rep.say("  v4 extras     %s" % ", ".join(have_v4))

    if rows:
        filled = {c: sum(1 for r in rows if str(r.get(c, "")).strip())
                  for c in cols}
        rep.say("")
        rep.say("  how many rows have a value in each column:")
        for c in cols:
            rep.say("    %-16s %d / %d" % (c, filled[c], len(rows)))
        states: Dict[str, int] = {}
        for r in rows:
            key = str(r.get("status", ""))
            states[key] = states.get(key, 0) + 1
        rep.say("  status        %s" % ", ".join(
            "%s=%d" % (k or "(blank)", v) for k, v in sorted(states.items())))
        with_label = filled.get("label_png", 0)
        rep.check("PASS" if with_label else "FAIL",
                  "some rows carry a label_png",
                  "%d of %d%s" % (with_label, len(rows),
                                  "" if with_label == len(rows) else
                                  " — the rest were gated out by the "
                                  "fine-align score threshold, which is "
                                  "normal"))
        rep.say("")
        rep.say("  image_id (all %d):    %s"
                % (len(rows), _shape_summary([r.get("image_id") for r in rows])))
        # 只看第一列會騙人：真實資料裡第一列的 id 是 1 個字元，而資料夾裡第一
        # 個檔案的 stem 是 6 個字元 —— 兩句話都對，而擺在一起看起來像矛盾。
        srcs = sorted({str(r.get("id_source", "")) for r in rows} - {""})
        if srcs:
            rep.say("  id_source            %s" % ", ".join(srcs))
            klarf_ids = srcs == ["klarf-defectid"]
            rep.check("PASS" if klarf_ids else "WARN",
                      "the manifest says image_id is the KLARF DEFECTID",
                      "" if klarf_ids else
                      "id_source = %s — ADEPT must pair on that instead"
                      % ", ".join(srcs))
        for col in ("width_px", "height_px", "nm_per_px"):
            vals = sorted({str(r.get(col, "")).strip() for r in rows} - {""})
            if vals:
                rep.say("  %-20s %s" % (col, ", ".join(vals[:6])
                                        + (" …(%d distinct)" % len(vals)
                                           if len(vals) > 6 else "")))

    label_map = list(doc.get("label_map") or [])
    rep.say("")
    if not label_map:
        rep.say("  label_map     MISSING")
        rep.check("FAIL", "manifest carries label_map",
                  "GLAS only writes it when “export label” was on. Without it "
                  "ADEPT cannot turn a label id into a region name.")
    else:
        rep.say("  label_map     %d layer(s)" % len(label_map))
        rep.say("    %-4s %-10s %-8s %s" % ("id", "layer", "fg_glv", "name shape"))
        for e in label_map:
            rep.say("    %-4s %-10s %-8s %s"
                    % (e.get("id"), m.alias("L", e.get("layer")),
                       e.get("fg_glv"), Masker.shape_of(e.get("layer"))))
        ids = [e.get("id") for e in label_map]
        want = list(range(1, len(label_map) + 1))
        rep.check("PASS" if ids == want else "WARN",
                  "label ids are 1..N with no gaps",
                  "" if ids == want else "got %s" % ids)
        rep.check("PASS" if len(label_map) <= 255 else "FAIL",
                  "at most 255 layers",
                  "" if len(label_map) <= 255 else
                  "%d layers — the label map is uint8, so ids above 255 wrap "
                  "round silently" % len(label_map))
        bad = [e for e in label_map
               if not str(e.get("layer", "")).replace("_", "").isalnum()]
        rep.check("PASS" if not bad else "WARN",
                  "layer names can be used as ADEPT region names",
                  "" if not bad else
                  "%d name(s) contain characters ADEPT's region-name pattern "
                  "rejects (letters, digits and underscore only) — ADEPT will "
                  "have to rewrite them, so they must be rewritten the SAME way "
                  "every time" % len(bad))
    return {"rows": rows, "columns": cols, "label_map": label_map}


def _shape_summary(values) -> str:
    """一整欄字串的長相 —— 長度範圍、是不是全數字、有沒有補零／非 ASCII。"""
    texts = [str(v) for v in values if str(v or "")]
    if not texts:
        return "empty"
    lens = sorted({len(t) for t in texts})
    bits = ["len=%d" % lens[0] if len(lens) == 1
            else "len %d..%d (%d lengths)" % (lens[0], lens[-1], len(lens))]
    if all(t.isdigit() for t in texts):
        bits.append("all-digits")
        padded = [t for t in texts if len(t) > 1 and t[0] == "0"]
        bits.append("zero-padded" if len(padded) == len(texts)
                    else ("some zero-padded (%d)" % len(padded) if padded
                          else "not zero-padded"))
    elif all(t.isalnum() for t in texts):
        bits.append("alnum")
    else:
        bits.append("%d have punctuation"
                    % sum(1 for t in texts if not t.isalnum()))
    odd = sum(1 for t in texts if not all(ord(c) < 128 for c in t))
    if odd:
        bits.append("%d NON-ASCII" % odd)
    return " · ".join(bits)


def check_pairing(export_dir: str, man: Dict[str, object], rep: Report,
                  m: Masker) -> None:
    """``image_id`` → 檔名。**這是最容易安靜對不上的一步。**"""
    rep.head("PAIRING  (image_id -> filename)")
    rows = list(man.get("rows") or [])
    if not rows:
        rep.check("SKIP", "image_id maps onto the label filename")
        return

    renamed, missing, mismatch = 0, 0, 0
    for r in rows:
        image_id = str(r.get("image_id", ""))
        declared = str(r.get("label_png", "")).strip()
        if not declared:
            continue
        if safe_name(image_id) != image_id:
            renamed += 1
        if declared != "%s_label.png" % safe_name(image_id):
            mismatch += 1
        if not os.path.isfile(os.path.join(export_dir, declared)):
            missing += 1

    rep.say("  rows with a label_png:        %d"
            % sum(1 for r in rows if str(r.get("label_png", "")).strip()))
    rep.say("  ids changed by _safe_name():  %d" % renamed)
    rep.say("  declared name != <safe_id>_label.png: %d" % mismatch)
    rep.say("  declared file not on disk:    %d" % missing)

    rep.check("PASS" if not missing else "FAIL",
              "every label_png named in the manifest is on disk",
              "" if not missing else "%d missing" % missing)
    rep.check("PASS" if not renamed else "WARN",
              "DEFECTID can be used verbatim to build the filename",
              "" if not renamed else
              "%d id(s) get rewritten by GLAS's _safe_name() (non-alphanumeric "
              "characters become '_'), so ADEPT must apply the SAME transform "
              "when pairing — it cannot just concatenate DEFECTID" % renamed)
    rep.check("PASS" if not mismatch else "WARN",
              "the manifest's label_png matches the <id>_label.png convention",
              "" if not mismatch else "%d row(s) differ" % mismatch)

    # 兩個不同的 image_id 可能被 _safe_name 折到同一個檔名（``a/b`` 與 ``a:b``
    # 都變成 ``a_b``）。後寫的那顆會**覆蓋**前一顆的 PNG，而 manifest 裡兩列
    # 的 image_id 仍然不同 —— 於是兩顆 defect 共用一張 mask，沒有任何錯誤訊息。
    buckets: Dict[str, int] = {}
    for r in rows:
        buckets[safe_name(str(r.get("image_id", "")))] = buckets.get(
            safe_name(str(r.get("image_id", ""))), 0) + 1
    clashes = sum(1 for n in buckets.values() if n > 1)
    rep.check("PASS" if not clashes else "FAIL",
              "no two image_ids collapse onto the same filename",
              "" if not clashes else
              "%d filename(s) are claimed by more than one image_id — the "
              "later export overwrote the earlier one, so those defects share "
              "a mask" % clashes)


def check_label_images(export_dir: str, man: Dict[str, object], images_dir:
                       Optional[str], samples: int, rep: Report, m: Masker,
                       klarf_files: Optional[Dict[str, str]] = None) -> None:
    """抽幾張 label 圖真的讀進來看 —— 通道數、值、尺寸。"""
    rep.head("LABEL IMAGES  (sampled)")
    rows = [r for r in (man.get("rows") or [])
            if str(r.get("label_png", "")).strip()]
    if not rows:
        rep.check("SKIP", "label PNG is single-channel 8-bit")
        return

    label_map = list(man.get("label_map") or [])
    known = {int(e.get("id", -1)) for e in label_map}
    picked = rows[:max(1, samples)]
    channel_bad, size_bad, size_seen, unknown_ids = 0, 0, 0, set()
    # 每個 id 在**幾張**取樣影像上一個像素都沒有。用 per-image 而不是聯集：
    # 風險是「這一顆的那一層被蓋光了」，那是逐顆發生的 —— 取聯集的話,只要
    # 有一張圖看得到那一層就會 PASS,而其餘每一顆的那個區域都是空的。
    empty_on: Dict[int, int] = {}
    #: 第一張圖上，每一層拆出來幾塊、幾個矩形。**Region-3 的設計就靠這個** ——
    #: 「一層的框有幾個」在另外兩張定位卡上是個位數，在這裡可能是幾百個，
    #: 而 ``max_boxes`` 的預設值（64）會安靜地砍掉其餘的。
    shapes_of: Dict[int, Tuple[int, int]] = {}
    decoded = 0
    unreadable: List[str] = []

    for r in picked:
        name = str(r.get("label_png"))
        path = os.path.join(export_dir, name)
        head = png_header(path)
        tag = m.alias("IMG", r.get("image_id"))
        if head is None:
            rep.say("  %-8s  not a readable PNG" % tag)
            channel_bad += 1
            continue
        ctype = COLOR_TYPES.get(head["color_type"], "?")
        rep.say("  %-8s  %dx%d  %d-bit  %s  interlace=%d"
                % (tag, head["width"], head["height"], head["bit_depth"],
                   ctype, head["interlace"]))
        if head["color_type"] != 0 or head["bit_depth"] != 8:
            channel_bad += 1

        counts, why = png_value_counts(path)
        if counts is None:
            unreadable.append(why)
            rep.say("            values not read: %s" % why)
        else:
            decoded += 1
            total = float(sum(counts.values())) or 1.0
            parts = []
            for value in sorted(counts):
                parts.append("%d:%.1f%%" % (value, 100.0 * counts[value] / total))
                if value and known and value not in known:
                    unknown_ids.add(value)
            rep.say("            values    %s" % "  ".join(parts))
            if shapes_of is not None and not shapes_of:
                flat = png_pixels(path)
                for i in sorted(known):
                    if counts.get(i):
                        rs = _runs(flat, head["width"], head["height"], i)
                        shapes_of[i] = (blob_count(rs), rect_count(rs))
            gone = sorted(i for i in known if not counts.get(i))
            for i in gone:
                empty_on[i] = empty_on.get(i, 0) + 1
            if gone:
                rep.say("            no pixels for id(s) %s" % gone)

        other = None
        try:                                  # v4：manifest 自己就說得出來
            other = (int(r["width_px"]), int(r["height_px"]))
        except (KeyError, TypeError, ValueError):
            other = _companion_size(export_dir, images_dir, r, klarf_files)
        if other is not None:
            size_seen += 1
            if (head["width"], head["height"]) != other:
                size_bad += 1
                rep.say("            SEM image says %dx%d — DIFFERENT" % other)

    rep.check("PASS" if not channel_bad else "FAIL",
              "label PNG is single-channel 8-bit greyscale",
              "" if not channel_bad else
              "%d of %d sampled are not. ADEPT would grey-average the channels "
              "and blend label ids into values that do not exist — silently. "
              "(Check you are not pointing at *_label_view.png, which is the "
              "colourised preview.)" % (channel_bad, len(picked)))
    # **沒有比到就不能說 PASS。** 「我沒查」跟「查過了沒問題」在報告上長得一樣
    # 的話，這份報告本身就是那種安靜的錯（沒有 _raw.png、也沒給 --images 時，
    # 這一條以前會直接綠燈）。
    if not size_seen:
        rep.check("SKIP", "label PNG is the same size as the SEM image",
                  "nothing to compare against — no width_px/height_px in the "
                  "manifest and no *_raw.png; point --images at the SEM images")
    else:
        rep.check("PASS" if not size_bad else "FAIL",
                  "label PNG is the same size as the SEM image",
                  "compared %d of %d sampled%s"
                  % (size_seen, len(picked),
                     "" if not size_bad else "; %d differ" % size_bad))
    if known:
        rep.check("PASS" if not unknown_ids else "FAIL",
                  "every pixel value appears in label_map",
                  "" if not unknown_ids else
                  "found id(s) %s with no entry" % sorted(unknown_ids))
        rep.check("PASS" if not empty_on else "WARN",
                  "every layer in label_map has pixels on every image",
                  "" if not empty_on else
                  "%s (out of %d decoded). GLAS paints layers in order and "
                  "LATER LAYERS OVERWRITE EARLIER ONES (render_label_image), "
                  "so a layer can be eaten completely on some defects — the "
                  "name stays in label_map and that defect's region comes out "
                  "empty. Raise --samples to see how often."
                  % (", ".join("id %d empty on %d image(s)" % (i, n)
                               for i, n in sorted(empty_on.items())), decoded))
    if shapes_of:
        rep.say("")
        rep.say("  how one image decomposes (this is what ADEPT has to store):")
        rep.say("    %-6s %-10s %-10s" % ("id", "pieces", "rectangles"))
        worst = 0
        for i in sorted(shapes_of):
            blobs, rects = shapes_of[i]
            worst = max(worst, rects)
            rep.say("    %-6d %-10d %-10d" % (i, blobs, rects))
        rep.check("PASS" if worst <= 64 else "WARN",
                  "a layer fits under the Region cards' default box cap (64)",
                  "" if worst <= 64 else
                  "the biggest layer is %d rectangles. ADEPT stores a named "
                  "region as a list of rectangles, and the existing Region "
                  "cards cap that at 64 — a default meant for a handful of "
                  "repeats. Here it would silently drop almost everything, so "
                  "roi_from_mask needs its own much larger cap. Note pieces vs "
                  "rectangles above: where they differ, the layer is being cut "
                  "up by whichever layer is painted after it." % worst)
    if unreadable:
        rep.check("WARN", "the sampled label PNGs could all be decoded",
                  "; ".join(sorted(set(unreadable))))


def _companion_size(export_dir: str, images_dir: Optional[str],
                    row: Dict[str, object],
                    klarf_files: Optional[Dict[str, str]] = None
                    ) -> Optional[Tuple[int, int]]:
    """這一顆的 SEM 影像多大 —— 先找匯出的 ``_raw.png``，再找原始影像資料夾。"""
    raw = str(row.get("raw_png", "")).strip()
    if raw:
        size = image_size(os.path.join(export_dir, raw))
        if size:
            return size
    if not images_dir or not os.path.isdir(images_dir):
        return None
    # 影像常常在 lot 底下的一層子資料夾裡（合成的 RSEM lot 就是 ``<lot>/images``），
    # 所以指到 lot 也要找得到 —— 指錯一層而整條檢查靜靜跳過，等於沒檢查。
    image_id = str(row.get("image_id", ""))
    # KLARF 說得出這一顆的影像檔名（GLAS 也是這樣拿的）。用「stem 剛好等於 id」
    # 去猜是錯的 —— 合成的 RSEM lot 就是 ``DEF_0001.png`` 對 ``DEFECTID = 1``。
    want = {safe_name(image_id), image_id}
    named = (klarf_files or {}).get(image_id)
    if named:
        want.add(os.path.splitext(os.path.basename(named.replace("\\", "/")))[0])
    for root, _dirs, files in os.walk(images_dir):
        for name in sorted(files):
            if os.path.splitext(name)[0] in want:
                size = image_size(os.path.join(root, name))
                if size:
                    return size
    return None


def check_alignment(export_dir: str, extra: str, rep: Report,
                    m: Masker) -> None:
    """alignment 檔 —— **檔名與資料夾都是使用者選的**，所以靠 schema 找。

    GLAS 匯出 alignment 走的是**另一個**存檔對話框（`gds_align_tool` 的
    `_write_alignment_manifest`），所以它常常不在 PNG 那個資料夾裡 ——
    找不到不是錯，`--alignment` 可以直接指過去。
    """
    rep.head("ALIGNMENT")
    found: List[str] = []
    candidates = [os.path.join(export_dir, n)
                  for n in sorted(os.listdir(export_dir))]
    if extra:
        candidates.append(extra)
    for path in candidates:
        name = os.path.basename(path)
        if not os.path.isfile(path):
            continue
        if name.lower().endswith(".json") and name != MANIFEST_JSON:
            try:
                doc = json.loads(open(path, "rb").read().decode("utf-8", "replace"))
            except ValueError:
                continue
            if isinstance(doc, dict) and doc.get("schema") == ALIGNMENT_SCHEMA:
                found.append(name)
                _alignment_stats(list(doc.get("alignments") or []), rep, m)
        elif name.lower().endswith(".csv") and name != MANIFEST_CSV:
            with open(path, "r", newline="", encoding="utf-8",
                      errors="replace") as f:
                rows = list(csv.DictReader(f))
            if rows and "coarse_dx_nm" in rows[0]:
                found.append(name)
                _alignment_stats(rows, rep, m)
    if not found:
        rep.say("  no alignment CSV/JSON here (it is saved through a separate "
                "dialog, so it is often in another folder — use --alignment)")
        rep.check("SKIP", "alignment export is present",
                  "not needed to place boxes (the label PNG is already "
                  "aligned) — only useful later as a per-defect confidence")
    else:
        rep.check("PASS", "alignment export is present",
                  "%d file(s)" % len(found))


def _alignment_stats(rows: List[Dict[str, object]], rep: Report,
                     m: Masker) -> None:
    if not rows:
        return
    rep.say("  columns   %s" % ", ".join(rows[0].keys()))
    rep.say("  rows      %d" % len(rows))
    for col in ("coarse_dx_nm", "coarse_dy_nm", "fine_dx_nm", "fine_dy_nm",
                "score", "nm_per_px"):
        vals = []
        for r in rows:
            try:
                vals.append(float(str(r.get(col, "")).strip()))
            except ValueError:
                pass
        if vals:
            uniq = len(set(vals))
            rep.say("    %-14s n=%-5d min=%-12.4g max=%-12.4g distinct=%d"
                    % (col, len(vals), min(vals), max(vals), uniq))
    npp = {str(r.get("nm_per_px", "")).strip() for r in rows}
    npp.discard("")
    if npp == {"0.0"} or npp == {"0"}:
        rep.check("FAIL", "nm_per_px is a real scale",
                  "every row says 0 — GLAS writes 0.0 when no image was loaded "
                  "in the viewer at export time")
    elif npp:
        rep.check("PASS" if len(npp) == 1 else "WARN",
                  "nm_per_px is one value for the whole lot",
                  "" if len(npp) == 1 else
                  "%d distinct values — it varies per image, so ADEPT cannot "
                  "treat it as a lot constant" % len(npp))


#: Studio 的「Open KLARF」用的副檔名（`ui/studio.py`）—— 同一份慣例。
KLARF_EXTS = (".001", ".klarf", ".txt")


def find_klarf(path: str) -> str:
    """``--klarf`` 給檔案就用它，給**資料夾**就在裡面找一份。

    使用者手上是一個資料夾（KLARF 跟影像放在一起），要他先去看清楚 KLARF 叫
    什麼名字才跑得動，是一個沒有必要的步驟 —— 而每一個沒必要的步驟都是一次
    「算了不跑」的機會（推廣鐵則）。
    """
    if os.path.isfile(path):
        return path
    if not os.path.isdir(path):
        return path
    hits = [os.path.join(path, n) for n in sorted(os.listdir(path))
            if os.path.splitext(n)[1].lower() in KLARF_EXTS
            and os.path.isfile(os.path.join(path, n))]
    return hits[0] if hits else path


def check_klarf_join(klarf_path: str, man: Dict[str, object], rep: Report,
                     m: Masker) -> Dict[str, str]:
    """manifest 的 ``image_id`` 對不對得上 KLARF 的 ``DEFECTID``。

    **一個 id 都不印。** 只印對上幾顆 —— 那足夠回答「join key 是不是同一個」。

    順便回傳 ``{DEFECTID: 影像檔名}``：label 圖要跟**哪一張** SEM 影像比大小，
    答案在 KLARF 裡（GLAS 也是這樣拿的）。用「檔名 stem 剛好等於 id」去猜是錯的
    —— 合成的 RSEM lot 就是 ``DEF_0001.png`` 對 ``DEFECTID = 1``。
    """
    rep.head("KLARF JOIN")
    try:
        from adept.core.ingest import klarf_core          # lazy: 工具是 stdlib-only
    except ImportError as exc:
        rep.say("  cannot import adept (%s)" % exc.__class__.__name__)
        rep.check("SKIP", "manifest image_id == KLARF DEFECTID",
                  "run this from the ADEPT folder so it can read the KLARF")
        return {}
    found = find_klarf(klarf_path)
    rep.say("  looked in            %s"
            % ("a folder" if os.path.isdir(klarf_path) else "the file you gave"))
    if os.path.isdir(found):
        rep.say("  no KLARF (%s) in that folder"
                % "/".join(e for e in KLARF_EXTS))
        rep.check("SKIP", "manifest image_id == KLARF DEFECTID",
                  "point --klarf at the KLARF file itself")
        return {}
    rep.say("  reading    %s" % m.alias("KLARF", os.path.basename(found)))
    try:
        doc = klarf_core.load(found)
    except Exception as exc:                              # noqa: BLE001
        rep.say("  cannot read the KLARF: %s" % exc.__class__.__name__)
        rep.check("SKIP", "manifest image_id == KLARF DEFECTID",
                  "%s on %s — if that folder has no .001/.klarf/.txt, point "
                  "--klarf straight at the KLARF file"
                  % (exc.__class__.__name__,
                     m.alias("KLARF", os.path.basename(found))))
        return {}

    cols = [str(c).upper() for c in doc.defect_columns]
    if "DEFECTID" not in cols:
        rep.check("FAIL", "the KLARF has a DEFECTID column",
                  "columns: %s" % ", ".join(cols))
        return {}
    col = cols.index("DEFECTID")
    ids = {str(r[col]) for r in doc.defects if len(r) > col}
    files: Dict[str, str] = {}
    for r in doc.defects:
        if len(r) > col:
            try:
                name = doc.defect_image_filename(r)
            except Exception:                             # noqa: BLE001
                name = None
            if name:
                files[str(r[col])] = str(name)
    rows = list(man.get("rows") or [])
    mine = {str(r.get("image_id", "")) for r in rows}
    hit = len(mine & ids)

    rep.say("  KLARF defects        %d" % len(ids))
    rep.say("  manifest rows        %d" % len(rows))
    rep.say("  image_ids that are also DEFECTIDs:  %d / %d" % (hit, len(mine)))
    rep.check("PASS" if hit == len(mine) and mine else "FAIL",
              "manifest image_id == KLARF DEFECTID",
              "" if hit == len(mine) and mine else
              "%d of %d matched — if this is 0 the ids are filename stems "
              "(GLAS's folder mode), and ADEPT must pair on the stem instead"
              % (hit, len(mine)))
    return files


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
BANNER = """
GLAS export check for ADEPT Region-3 (GDS mode)
-----------------------------------------------
Everything below is MASKED: layer names are L1, L2 …, defect ids are IMG1,
IMG2 …, and no path or lot/wafer/device name is printed. Only structure,
formats and counts. It is safe to copy this whole report as text.
(Run with --reveal to see the real values on this machine — do NOT paste that.)
"""


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Check a GLAS export folder against what ADEPT needs, "
                    "and print a masked report that is safe to copy out.")
    ap.add_argument("export_dir", help="GLAS 匯出的資料夾（裡面有 *_label.png）")
    ap.add_argument("--klarf", default="",
                    help="那一批的 KLARF（給檔案或給**資料夾**都可以）—— "
                         "驗 image_id 是不是 DEFECTID")
    ap.add_argument("--images", default="",
                    help="原始 SEM 影像資料夾 —— 驗 label 圖跟影像一樣大")
    ap.add_argument("--alignment", default="",
                    help="alignment CSV/JSON —— 它存在另一個對話框選的路徑，"
                         "常常不在匯出資料夾裡")
    ap.add_argument("--samples", type=int, default=3,
                    help="真的讀進來看的 label 圖張數（預設 3；讀圖是純 Python，"
                         "大圖會慢）")
    ap.add_argument("--reveal", action="store_true",
                    help="印真值而不是代號。**這一份不要貼出來。**")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.export_dir):
        sys.stderr.write("not a folder: %s\n" % args.export_dir)
        return 2

    m = Masker(reveal=args.reveal)
    rep = Report()
    rep.say(BANNER.strip() if not args.reveal else
            "GLAS export check — REVEALED OUTPUT, do not paste this.")

    scan_folder(args.export_dir, rep, m)
    man = read_manifest(args.export_dir, rep, m)
    # KLARF 先讀：它說得出每一顆的影像檔名，而尺寸檢查需要那個。
    if args.klarf:
        klarf_files = check_klarf_join(args.klarf, man, rep, m)
    else:
        rep.head("KLARF JOIN")
        rep.say("  not checked — pass --klarf <path> to check it")
        rep.check("SKIP", "manifest image_id == KLARF DEFECTID")
        klarf_files = {}
    if man:
        check_pairing(args.export_dir, man, rep, m)
        check_label_images(args.export_dir, man, args.images or None,
                           args.samples, rep, m, klarf_files)
    check_alignment(args.export_dir, args.alignment, rep, m)

    print(rep.render())
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())

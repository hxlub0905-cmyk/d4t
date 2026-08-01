# ADEPT KLARF write-back — authored 2026-07-28 (M5-1).
"""KLARF 三種寫回模式：inplace / annotate / topn。

角色（見 docs/plans/F0-master-plan.md §7）：pipeline 算完的
``result_to_json_dict`` 結果（``defect_id`` / ``ok`` / ``score`` / ``bin`` /
``features``）要回到 KLARF，讓下游（Klarity、review 站）看得到 ADC 的判定。

三種模式各自的承諾
------------------

``"inplace"`` **只改既有欄位，不動檔案結構**
    走 :meth:`KlarfDoc.set_cell` 的 span-splice：沒被改到的 byte 與原檔
    逐位元組相同（鐵則 6）。**什麼都沒改 → 輸出檔與輸入檔位元組完全相同。**
    要寫的欄位不存在時**直接報錯**（:class:`ExportError`），絕不默默略過
    —— 使用者以為寫進去了但其實沒有，比報錯糟一百倍。

``"annotate"`` **產生新檔，追加欄位**
    在欄位定義（1.2 的 ``DefectRecordSpec`` / 1.8 的 ``Columns N { … }``）
    與每一列 defect 上追加 ``ADCSCORE`` / ``ADCCLASS``（可再加選定的特徵欄）。
    **影像區塊一律留在最後**：插入點取自
    :meth:`KlarfDoc.image_layout`（影像 token 的起始欄），新欄位插在它之前，
    所以 ``IMAGELIST`` / ``Images N { … }`` 仍是列尾 —— 影像對應不會壞。
    1.2 與 1.8 都支援。

``"topn"`` **產生新檔，只留高分的那幾顆**
    依 score 由高到低取前 N 顆（或所有 >= ``min_score`` 的），可重新編號
    DEFECTID，可同時做 annotate 的欄位。

    ★ 影像參照怎麼處理（重要）★
      - **每列自帶檔名**（1.8 rSEM 的 ``Images N { "檔名" … }``）：檔名跟著
        列一起走，抽子集後仍指向原本那張圖 —— 完全安全。
      - **IMAGELIST 帶 TIFF 頁碼**（1.2 EBI patch）：頁碼**原樣保留**，
        指向**原本那份多頁 TIFF**。DEFECTID 重新編號**不會**連動改頁碼，
        因為重新編頁等同要重寫 TIFF，本工具不碰原始影像。
        → 輸出的 KLARF 必須與原 TIFF 放在同一個資料夾才讀得到圖。
      - **依出現順序連續配頁**（沒有 IMAGELIST 頁碼可用）：抽子集後頁序
        必然對不上，這種情況會在 ``notes`` 裡明講。

用法::

    plan = plan_writeback(doc, results, "annotate")   # 乾跑，不寫檔
    print(plan.n_rows_out, plan.columns_added, plan.notes)
    plan = apply_writeback(doc, results, "annotate", out_path)   # 真的寫

``plan_writeback`` 與 ``apply_writeback`` 走同一條計算路徑，回報的數字
保證一致；兩者都**不會改動傳進來的 doc**（內部先複製一份）。
寫檔一律 atomic（``.tmp`` + :func:`os.replace`，鐵則 5）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..ingest import klarf_core
from ..ingest.klarf_core import KlarfDoc

__all__ = [
    "ExportError", "WriteBackPlan", "MODES",
    "plan_writeback", "apply_writeback",
]

#: 支援的寫回模式。
MODES = ("inplace", "annotate", "topn")

_DEFAULT_SCORE_COL = "ADCSCORE"
_DEFAULT_CLASS_COL = "ADCCLASS"


class ExportError(RuntimeError):
    """匯出失敗（訊息一律寫成使用者看得懂的白話，並附上可行的下一步）。"""


# ---------------------------------------------------------------------------
# 計畫書
# ---------------------------------------------------------------------------
@dataclass
class WriteBackPlan:
    """「按下去會發生什麼」的預覽。

    - ``mode``             使用的模式（``inplace`` / ``annotate`` / ``topn``）。
    - ``n_rows_changed``   輸出檔中「內容與原檔不同」的 defect 列數。
      inplace = 真的有格子被改值的列數；annotate = 全部列（每列都多了欄位）；
      topn = 被重新編號或被加註記的列數（兩者都關掉時為 0）。
    - ``columns_touched``  被寫入的**既有**欄位名。
    - ``columns_added``    新增的欄位名。
    - ``n_rows_out``       輸出檔的 defect 列數。
    - ``notes``            白話說明（包含影像參照怎麼處理、對不到的結果…）。
    - ``issues``           對**輸出結果**跑 :func:`klarf_core.lint` 的
      :class:`klarf_core.Issue` 清單（寫檔前就算好，所以預覽也看得到）。
    """

    mode: str
    n_rows_changed: int = 0
    columns_touched: List[str] = field(default_factory=list)
    columns_added: List[str] = field(default_factory=list)
    n_rows_out: int = 0
    notes: List[str] = field(default_factory=list)
    issues: List[Any] = field(default_factory=list)

    def error_issues(self) -> List[Any]:
        """只取 level == 'error' 的健檢問題（UI 用來決定要不要擋下）。"""
        return [i for i in self.issues if getattr(i, "level", "") == "error"]

    def to_dict(self) -> Dict[str, Any]:
        """轉成可 ``json.dumps`` 的 dict（Issue 攤平成欄位）。"""
        return {
            "mode": self.mode,
            "n_rows_changed": int(self.n_rows_changed),
            "columns_touched": list(self.columns_touched),
            "columns_added": list(self.columns_added),
            "n_rows_out": int(self.n_rows_out),
            "notes": list(self.notes),
            "issues": [
                {"code": i.code, "level": i.level, "title": i.title,
                 "detail": i.detail, "count": i.count, "fixable": i.fixable}
                for i in self.issues
            ],
        }


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _clone(doc: KlarfDoc) -> KlarfDoc:
    """複製一份可安全改動的 doc（不動呼叫端傳進來的那份）。

    以 ``doc.to_text()`` 重建：doc 乾淨時字串與原檔完全相同，
    所以「什麼都沒改 → 位元組相同」的承諾在複製後依然成立。
    """
    return KlarfDoc(doc.to_text(), source_path=doc.source_path)


def _atomic_write_text(path: str, text: str) -> str:
    """atomic 寫入文字檔（鐵則 5）。換行沿用文字本身，不做轉換。"""
    path = str(path)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)
    return path


def _norm_id(v: Any) -> str:
    """DEFECTID 正規化：``"007"`` 與 ``7`` 視為同一顆。"""
    s = str(v).strip().strip('"')
    try:
        return str(int(s))
    except (TypeError, ValueError):
        return s


def _num(v: Any, default: float = 0.0) -> float:
    """安全轉 float（None／非數字 → default）——單一顆的怪值不該炸掉整批。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float(default)
    if f != f or f in (float("inf"), float("-inf")):   # nan / inf
        return float(default)
    return f


def _fmt_float(v: Any, decimals: int) -> str:
    """固定小數位數（檔案才 diff 得動）。"""
    return "{:.{d}f}".format(_num(v), d=int(decimals))


def _as_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return int(default)


def _cols_hint(doc: KlarfDoc) -> str:
    return (", ".join(doc.defect_columns) if doc.defect_columns
            else "(column definitions unreadable)")


def _require_col(doc: KlarfDoc, name: str, what: str) -> int:
    """取欄位索引；沒有這欄就報錯（白話 + 可行的下一步）。"""
    j = doc.col_index(name)
    if j < 0:
        raise ExportError(
            "This KLARF has no \"{name}\" column, so it cannot {what}.\n"
            "The defect columns in this file are: {cols}.\n"
            "Point at one of the existing columns instead, or switch to annotate "
            "mode (which adds columns and writes a new KLARF, leaving the "
            "original untouched).".format(
                name=name, what=what, cols=_cols_hint(doc)))
    return j


def _pair_results(doc: KlarfDoc, results: Sequence[Dict[str, Any]]
                  ) -> Tuple[List[Optional[int]], List[str]]:
    """把每筆 result 對到 doc.defects 的列索引。

    優先用 DEFECTID 比對；沒有這一欄時退回「第 n 筆對第 n 列」的位置比對
    並留下警告。回傳 ``(row_idx_per_result, notes)``，對不到的是 ``None``。
    """
    notes: List[str] = []
    di = doc.col_index("DEFECTID")
    out: List[Optional[int]] = []

    if di < 0:
        notes.append(
            "This KLARF has no DEFECTID column, so results are matched to rows "
            "by position (nth result to nth defect row). If the results are in a "
            "different order from the KLARF, the mapping will be wrong.")
        for k in range(len(results)):
            out.append(k if k < len(doc.defects) else None)
        if len(results) > len(doc.defects):
            notes.append("There are {} more results than defect rows in the "
                         "KLARF; the extras are ignored.".format(
                len(results) - len(doc.defects)))
        return out, notes

    exact: Dict[str, int] = {}
    loose: Dict[str, int] = {}
    for i, row in enumerate(doc.defects):
        if di < len(row):
            exact.setdefault(row[di], i)
            loose.setdefault(_norm_id(row[di]), i)

    missed = 0
    for r in results:
        rid = str(r.get("defect_id", ""))
        idx = exact.get(rid)
        if idx is None:
            idx = loose.get(_norm_id(rid))
        if idx is None:
            missed += 1
        out.append(idx)
    if missed:
        notes.append(
            "{} results have no defect with a matching DEFECTID in this KLARF "
            "and were skipped (usually the results and the KLARF are not from "
            "the same wafer — check the source).".format(missed))
    return out, notes


# ---------------------------------------------------------------------------
# 欄位定義改寫（annotate / topn 用）
# ---------------------------------------------------------------------------
_SAFE_COL = re.compile(r"[^A-Z0-9_]")


def _feature_col_name(feat: str) -> str:
    """特徵名 → KLARF 欄位名（大寫、只留 A-Z0-9_）。"""
    name = _SAFE_COL.sub("_", str(feat).upper()).strip("_")
    if not name:
        name = "FEATURE"
    if name[0].isdigit():
        name = "F_" + name
    return name


def _insert_pos(doc: KlarfDoc) -> int:
    """新欄位要插在第幾欄 —— 影像 token 的起始欄之前（沒有影像就接在最後）。"""
    layout = doc.image_layout()
    if layout is None:
        return len(doc.defect_columns)
    return max(0, min(int(layout[0]), len(doc.defect_columns)))


def _rewrite_spec_12(text: str, cols: Sequence[str]) -> str:
    """改寫 1.2 的 ``DefectRecordSpec N …;``（欄數同時更新）。"""
    m = re.search(r"DefectRecordSpec\s+\d+\s+[^;]+;", text)
    if m is None:
        raise ExportError(
            "No DefectRecordSpec found, so the column definitions of this "
            "KLARF 1.2 cannot be read and columns cannot be appended safely. "
            "Use inplace mode instead.")
    new = "DefectRecordSpec {} {} ;".format(len(cols), " ".join(cols))
    return text[:m.start()] + new + text[m.end():]


def _rewrite_columns_18(text: str, entries: Sequence[str]) -> str:
    """改寫 1.8 ``List DefectList`` 內的 ``Columns N { … }``（帶型別的欄位項）。"""
    dl = re.search(r"List\s+DefectList\s*\{", text)
    if dl is None:
        raise ExportError(
            "No List DefectList found — the structure of this KLARF 1.8 is not "
            "what was expected, so columns cannot be appended safely. Use "
            "inplace mode instead.")
    b0 = text.index("{", dl.start())
    b1 = klarf_core._find_matching_brace(text, b0)
    if b1 < 0:
        raise ExportError(
            "The braces of the KLARF 1.8 DefectList are not balanced; the file "
            "may be corrupt.")
    block = text[b0:b1 + 1]
    cm = re.search(r"Columns\s+\d+\s*\{[^}]*\}", block)
    if cm is None:
        raise ExportError(
            "No Columns definition inside the KLARF 1.8 DefectList, so columns "
            "cannot be appended safely. Use inplace mode instead.")
    lines = []
    for k in range(0, len(entries), 4):
        lines.append("  ".join(e + "," for e in entries[k:k + 4]))
    body = "\n          ".join(lines).rstrip(",")
    new = "Columns {} {{ {}  }}".format(len(entries), body)
    block = block[:cm.start()] + new + block[cm.end():]
    return text[:b0] + block + text[b1 + 1:]


def _column_entries_18(doc: KlarfDoc) -> List[str]:
    """讀出 1.8 現有的 ``Columns`` 欄位項原文（含型別），供插入後重組。"""
    t = doc._text
    dl = re.search(r"List\s+DefectList\s*\{", t)
    if dl is None:
        return []
    b0 = t.index("{", dl.start())
    b1 = klarf_core._find_matching_brace(t, b0)
    cm = re.search(r"Columns\s+\d+\s*\{([^}]*)\}", t[b0:b1 + 1])
    if cm is None:
        return []
    return [" ".join(c.split()) for c in cm.group(1).split(",") if c.strip()]


# ---------------------------------------------------------------------------
# annotate：欄位 + 值一起插進去
# ---------------------------------------------------------------------------
def _annotate(doc: KlarfDoc, results: Sequence[Dict[str, Any]],
              row_of_result: Sequence[Optional[int]], *,
              extra_features: Sequence[str] = (),
              decimals: int = 4,
              score_col: str = _DEFAULT_SCORE_COL,
              class_col: str = _DEFAULT_CLASS_COL,
              missing_score: float = 0.0,
              missing_class: int = -1,
              ) -> Tuple[List[str], List[str]]:
    """在 doc 上插入註記欄與每列的值（就地改 doc）。

    回傳 ``(新增的欄位名, notes)``。影像 token 一律留在列尾。
    """
    notes: List[str] = []
    decimals = max(0, int(decimals))
    cols = list(doc.defect_columns)
    if not cols:
        raise ExportError(
            "The defect column definitions of this KLARF cannot be read, so no "
            "columns can be appended. Run the KLARF health check first.")

    new_names = [str(score_col), str(class_col)]
    feat_cols: List[Tuple[str, str]] = []       # (欄位名, 特徵名)
    for f in extra_features or ():
        name = _feature_col_name(f)
        feat_cols.append((name, str(f)))
        new_names.append(name)
        if name != str(f):
            notes.append("Feature \"{}\" is written as KLARF column \"{}\" "
                         "(column names allow upper-case letters, digits and "
                         "underscores only)."
                         .format(f, name))

    dup = [n for n in new_names if doc.col_index(n) >= 0]
    if dup:
        raise ExportError(
            "This KLARF already has the columns {}, and annotate mode never "
            "overwrites existing columns.\nUse inplace mode to write into the "
            "existing columns, or pick an unused column name with score_col= / "
            "class_col=.".format(", ".join(dup)))
    if len(set(new_names)) != len(new_names):
        raise ExportError(
            "The new column names contain duplicates: {}.".format(
                ", ".join(new_names)))

    pos = _insert_pos(doc)

    # ---- 每列的值（先算好，才不會邊改邊查）----
    n_rows = len(doc.defects)
    vals: List[List[str]] = [
        [_fmt_float(missing_score, decimals), str(int(missing_class))]
        + [_fmt_float(missing_score, decimals) for _ in feat_cols]
        for _ in range(n_rows)
    ]
    filled = [False] * n_rows
    n_missing_feat = 0
    for r, idx in zip(results, row_of_result):
        if idx is None or not (0 <= idx < n_rows):
            continue
        feats = r.get("features") or {}
        score = r.get("score")
        b = r.get("bin")
        cell = [
            _fmt_float(missing_score if score is None else score, decimals),
            str(int(missing_class) if b is None else int(b)),
        ]
        for _name, fkey in feat_cols:
            v = feats.get(fkey)
            if v is None:
                n_missing_feat += 1
                v = missing_score
            cell.append(_fmt_float(v, decimals))
        vals[idx] = cell
        filled[idx] = True

    n_unfilled = sum(1 for f in filled if not f)
    if n_unfilled:
        notes.append(
            "{} defect rows have no matching ADC result; column {} is filled "
            "with {} and column {} with {} (meaning \"not judged\").".format(
                n_unfilled, score_col, _fmt_float(missing_score, decimals),
                class_col, int(missing_class)))
    if n_missing_feat:
        notes.append("{} feature values were absent from the results and were "
                     "filled with {}.".format(
            n_missing_feat, _fmt_float(missing_score, decimals)))

    # ---- 插欄位名 ----
    doc.defect_columns = cols[:pos] + list(new_names) + cols[pos:]

    # ---- 插每列的值（影像 token 全部往後推，仍在列尾）----
    for i, row in enumerate(doc.defects):
        if len(row) < pos:                       # 壞列：補 0 後再插，不丟資料
            row.extend(["0"] * (pos - len(row)))
        doc.defects[i] = row[:pos] + vals[i] + row[pos:]
    doc._defect_dirty = True
    doc._img_layout = "unset"                    # 欄位變了，影像佈局快取要重算
    if doc._il18 is not None and doc._il18 >= pos:
        doc._il18 += len(new_names)              # 1.8 的 ImageList 欄往後移了

    layout_note = ("The image column is column {}; new columns are inserted "
                   "before it, so the IMAGELIST / Images block stays at the end "
                   "of the row.".format(pos + 1))
    notes.append(layout_note if doc.image_layout() is not None
                 else "This KLARF has no image column, so new columns are "
                      "appended at the end.")
    return list(new_names), notes


def _render_new_text(doc: KlarfDoc, new_cols: Sequence[str],
                     orig_entries18: Sequence[str], pos: int) -> str:
    """把改過欄位的 doc 產生成新的 KLARF 文字（含欄位定義改寫）。"""
    text = doc.to_text()
    if doc._is18:
        entries = list(orig_entries18)
        if len(entries) != len(doc.defect_columns) - len(new_cols):
            raise ExportError(
                "The KLARF 1.8 Columns definition yields {} columns, which does "
                "not match the {} that were parsed; aborted to avoid writing a "
                "broken file.".format(
                    len(entries), len(doc.defect_columns) - len(new_cols)))
        typed = []
        for name in new_cols:
            typed.append(("int32 " if name.upper() == _DEFAULT_CLASS_COL
                          else "float32 ") + name)
        entries = entries[:pos] + typed + entries[pos:]
        return _rewrite_columns_18(text, entries)
    return _rewrite_spec_12(text, doc.defect_columns)


# ---------------------------------------------------------------------------
# 影像參照的說明（topn 用）
# ---------------------------------------------------------------------------
def _image_notes(doc: KlarfDoc) -> List[str]:
    """抽子集／重新編號之後，影像參照還有效嗎？—— 一律講清楚。"""
    notes: List[str] = []
    if doc.total_image_count() <= 0:
        notes.append("This KLARF carries no image information, so there are "
                     "no image references to handle.")
        return notes
    if any(doc.defect_image_filename(r) for r in doc.defects):
        notes.append(
            "Image references: each defect row carries its own image file name, "
            "and after subsetting these still point at the original image files "
            "(paths are relative to the folder holding the KLARF). Put the "
            "output KLARF in the same folder as the original, or move the images "
            "along with it.")
        return notes
    mode = doc.defect_image_map().get("mode")
    if mode == "imagelist":
        notes.append(
            "Image references: the IMAGELIST TIFF page numbers are kept exactly "
            "as they are and still point at the original multi-page TIFF. Even "
            "when DEFECTID is renumbered the page numbers do not follow — "
            "renumbering pages would mean rewriting the TIFF, and this tool never "
            "touches the original images. Keep the output KLARF in the same "
            "folder as the original TIFF.")
    else:
        notes.append(
            "! Image references: in this KLARF the images are paged "
            "consecutively in defect order (IMAGELIST carries no usable page "
            "numbers), so after subsetting the page order cannot line up. To keep "
            "the images, use annotate mode (which keeps every defect), or rewrite "
            "the TIFF as well (this tool does not).")
    return notes


# ---------------------------------------------------------------------------
# 三種模式的實作
# ---------------------------------------------------------------------------
def _build_inplace(doc: KlarfDoc, results: Sequence[Dict[str, Any]],
                   *, class_col: Optional[str] = None,
                   bin_col: Optional[str] = None,
                   size_col: Optional[str] = None,
                   size_feature: str = "cd_x_px",
                   size_scale: float = 1.0,
                   bin_map: Optional[Dict[Any, Any]] = None,
                   decimals: int = 4,
                   skip_failed: bool = True,
                   ) -> Tuple[str, WriteBackPlan]:
    plan = WriteBackPlan(mode="inplace")
    pairs, notes = _pair_results(doc, results)
    plan.notes.extend(notes)

    targets: List[Tuple[str, str]] = []          # (欄位名, 來源 'bin'/'size')
    if class_col:
        _require_col(doc, class_col, "write the bin into the class column")
        targets.append((str(class_col), "bin"))
    if bin_col:
        _require_col(doc, bin_col, "write the bin into the bin column")
        targets.append((str(bin_col), "bin"))
    if size_col:
        _require_col(doc, size_col, "write the size feature into the size column")
        targets.append((str(size_col), "size"))

    if not targets:
        plan.notes.append(
            "No target column was given (class_col / bin_col / size_col are all "
            "empty), so the output file will be byte-for-byte identical to the "
            "original.")

    # 單位換算是**輸出時**的事，而且使用者自己填（pipeline 全程用 pixel，
    # 見 adept/core/steps/cd.py 的模組 docstring）。scale=1 就是把 pixel
    # 原樣寫進去 —— 那也是預設，因為「不換算」比「用一個猜來的係數換算」誠實。
    try:
        scale = float(size_scale)
        ok_scale = scale > 0 and scale != float("inf")
    except (TypeError, ValueError):
        ok_scale = False
    if not ok_scale:
        raise ExportError(
            "The size scale must be a positive number — it is what each size "
            "value is multiplied by on its way into the size column (your nm "
            "per pixel, for instance). Use 1 to write the measured pixel value "
            "unchanged. Got: {!r}.".format(size_scale))

    if size_col:
        # 預覽必須講出換算，否則「DSIZE 那一欄的數字是什麼單位」只存在於
        # 按下去的那個人的腦子裡。
        plan.notes.append(
            "Size column \"{}\" is written from feature \"{}\" {}.".format(
                size_col, size_feature,
                "as is (pixels)" if scale == 1.0
                else "multiplied by {:g} (e.g. nm per pixel)".format(scale)))

    bmap = {str(k): v for k, v in (bin_map or {}).items()}
    changed_rows = set()
    n_skipped = 0
    n_no_bin = 0
    n_no_feat = 0
    n_short = 0

    for r, idx in zip(results, pairs):
        if idx is None:
            continue
        if skip_failed and not r.get("ok", True):
            n_skipped += 1
            continue
        row = doc.defects[idx]
        for name, src in targets:
            j = doc.col_index(name)
            if src == "bin":
                b = r.get("bin")
                if b is None:
                    n_no_bin += 1
                    continue
                val = str(bmap.get(str(int(b)), int(b)))
            else:
                v = (r.get("features") or {}).get(size_feature)
                if v is None:
                    n_no_feat += 1
                    continue
                val = _fmt_float(_num(v) * scale if scale != 1.0 else v,
                                 decimals)
            if j >= len(row):
                n_short += 1
                continue
            if row[j] != val:
                doc.set_cell(idx, name, val)
                changed_rows.add(idx)

    if n_short:
        plan.notes.append(
            "{} cells sit in defect rows with fewer tokens than the column "
            "definition, so there is no cell to write into and they were skipped "
            "(run the KLARF health check to repair the column count "
            "first).".format(n_short))
    if n_skipped:
        plan.notes.append("{} defects failed to run (ok=False) and were not "
                          "written back.".format(n_skipped))
    if n_no_bin:
        plan.notes.append("{} cells were skipped because the result has no bin "
                          "value.".format(n_no_bin))
    if n_no_feat:
        plan.notes.append("{} cells were skipped because the result has no "
                          "feature \"{}\".".format(
            n_no_feat, size_feature))

    plan.columns_touched = [n for n, _s in targets]
    plan.n_rows_changed = len(changed_rows)
    plan.n_rows_out = len(doc.defects)
    text = doc.to_text()
    plan.issues = klarf_core.lint(doc)
    return text, plan


def _build_annotate(doc: KlarfDoc, results: Sequence[Dict[str, Any]],
                    **opts: Any) -> Tuple[str, WriteBackPlan]:
    plan = WriteBackPlan(mode="annotate")
    pairs, notes = _pair_results(doc, results)
    plan.notes.extend(notes)

    pos = _insert_pos(doc)
    entries18 = _column_entries_18(doc) if doc._is18 else []
    if doc._is18 and not entries18:
        raise ExportError(
            "The Columns definition of this KLARF 1.8 cannot be read, so "
            "columns cannot be appended safely (the file could come out unusable "
            "downstream). Use inplace mode instead.")

    added, anotes = _annotate(doc, results, pairs, **opts)
    plan.columns_added = added
    plan.notes.extend(anotes)
    plan.n_rows_changed = len(doc.defects)
    plan.n_rows_out = len(doc.defects)

    text = _render_new_text(doc, added, entries18, pos)
    plan.issues = klarf_core.lint(klarf_core.load(text))
    return text, plan


def _build_topn(doc: KlarfDoc, results: Sequence[Dict[str, Any]], *,
                n: int = 0, min_score: Optional[float] = None,
                renumber: bool = True, include_annotations: bool = True,
                **annot_opts: Any) -> Tuple[str, WriteBackPlan]:
    plan = WriteBackPlan(mode="topn")
    pairs, notes = _pair_results(doc, results)
    plan.notes.extend(notes)

    n = _as_int(n, 0)
    if n <= 0 and min_score is None:
        raise ExportError(
            "topn mode needs either a count or a score threshold: n = the top N "
            "by descending score, or min_score = keep defects scoring at least "
            "this value. With neither, there is no way to tell what to keep.")

    # 影像參照的說明要在抽子集「之前」判斷（子集本身可能就解不出佈局）
    plan.notes.extend(_image_notes(doc))

    # ---- 挑出候選（有對到列、有分數）----
    cands: List[Tuple[int, float]] = []
    n_no_score = 0
    seen = set()
    for r, idx in zip(results, pairs):
        if idx is None or idx in seen:
            continue
        s = r.get("score")
        if s is None:
            n_no_score += 1
            continue
        try:
            sf = float(s)
        except (TypeError, ValueError):
            n_no_score += 1
            continue
        seen.add(idx)
        cands.append((idx, sf))
    if n_no_score:
        plan.notes.append(
            "{} defects have no score (the run failed, or the score is nan) and "
            "will not appear in the output file."
            .format(n_no_score))

    order = sorted(range(len(cands)), key=lambda k: (-cands[k][1], cands[k][0]))
    picked = [cands[k] for k in order]
    if n > 0:
        if min_score is not None:
            plan.notes.append(
                "Both n={} and min_score={} were given; n wins (the top {} by "
                "score)."
                .format(n, min_score, n))
        picked = picked[:n]
    else:
        thr = float(min_score)
        picked = [p for p in picked if p[1] >= thr]
        plan.notes.append("Keeping defects scoring >= {}: {} in total.".format(
            thr, len(picked)))

    keep_rows = [idx for idx, _s in picked]
    n_before = len(doc.defects)
    doc.defects = [doc.defects[i] for i in keep_rows]
    doc._defect_dirty = True
    doc.summary_stale = True
    plan.notes.append(
        "{} defects originally, {} written out (ordered by descending "
        "score).".format(
            n_before, len(doc.defects)))
    plan.notes.append(
        "SummaryList keeps the original values (it is a whole-wafer statistic, "
        "and recomputing it would wipe out the real numbers); "
        "the health check will flag \"summary does not match DefectList count\", "
        "which is normal for a file that only keeps a subset.")

    n_changed = 0
    if renumber:
        di = doc.col_index("DEFECTID")
        if di < 0:
            plan.notes.append(
                "No DEFECTID column, so renumbering was skipped.")
        else:
            for k, row in enumerate(doc.defects, 1):
                if di < len(row):
                    row[di] = str(k)
            n_changed = len(doc.defects)
            plan.columns_touched.append(doc.defect_columns[di])
            plan.notes.append("DEFECTID renumbered to 1..{}.".format(
                len(doc.defects)))
    else:
        plan.notes.append(
            "DEFECTID keeps the original values (no renumbering).")

    pos = _insert_pos(doc)
    entries18 = _column_entries_18(doc) if doc._is18 else []
    if include_annotations:
        if doc._is18 and not entries18:
            raise ExportError(
                "The Columns definition of this KLARF 1.8 cannot be read, so "
                "annotation columns cannot be appended. Use "
                "include_annotations=False to filter only.")
        # 列索引已經因為抽子集而改變：舊列索引 → 新列索引
        new_of_old = {old: new for new, old in enumerate(keep_rows)}
        sub_pairs = [None if p is None else new_of_old.get(p) for p in pairs]
        added, anotes = _annotate(doc, results, sub_pairs, **annot_opts)
        plan.columns_added = added
        plan.notes.extend(anotes)
        n_changed = len(doc.defects)
        text = _render_new_text(doc, added, entries18, pos)
    else:
        text = doc.to_text()

    plan.n_rows_changed = n_changed
    plan.n_rows_out = len(doc.defects)
    plan.issues = klarf_core.lint(klarf_core.load(text))
    return text, plan


_BUILDERS = {
    "inplace": _build_inplace,
    "annotate": _build_annotate,
    "topn": _build_topn,
}


def _build(doc: KlarfDoc, results: Sequence[Dict[str, Any]], mode: str,
           **opts: Any) -> Tuple[str, WriteBackPlan]:
    mode = str(mode).strip().lower()
    if mode not in _BUILDERS:
        raise ExportError(
            "Unrecognised write-back mode \"{}\". Available: {} "
            "(inplace = edit existing columns only, annotate = add columns, "
            "topn = keep the highest scoring only)."
            .format(mode, ", ".join(MODES)))
    if doc is None:
        raise ExportError(
            "No KLARF was given — load a KLARF before writing back.")
    work = _clone(doc)
    try:
        return _BUILDERS[mode](work, list(results or []), **opts)
    except TypeError as e:                       # 參數打錯 → 講清楚哪個模式吃哪些參數
        if "unexpected keyword argument" in str(e):
            raise ExportError(
                "Mode \"{}\" received an option it does not understand: "
                "{}.".format(mode, e)) from None
        raise


# ---------------------------------------------------------------------------
# 對外 API
# ---------------------------------------------------------------------------
def plan_writeback(doc: KlarfDoc, results: Sequence[Dict[str, Any]], mode: str,
                   **opts: Any) -> WriteBackPlan:
    """乾跑：算出「按下去會發生什麼」，**不寫任何檔案、不改動 doc**。

    參數與 :func:`apply_writeback` 完全相同（少一個 ``out_path``），
    回報的數字也保證一致 —— 兩者走同一條計算路徑。
    """
    _text, plan = _build(doc, results, mode, **opts)
    return plan


def apply_writeback(doc: KlarfDoc, results: Sequence[Dict[str, Any]], mode: str,
                    out_path: str, **opts: Any) -> WriteBackPlan:
    """真的寫出 KLARF（atomic），回傳與 :func:`plan_writeback` 相同的計畫書。

    各模式的選項
    ------------
    ``inplace``
        ``class_col`` / ``bin_col``（把 bin 寫進這些既有欄位，例如
        ``CLASSNUMBER`` / ``ROUGHBINNUMBER`` / ``FINEBINNUMBER``）、
        ``size_col``（把 ``size_feature`` 寫進去，例如 ``DSIZE``）、
        ``size_feature``（預設 ``"cd_x_px"``）、``size_scale``
        （預設 ``1.0``；寫進去之前乘上的係數 —— pipeline 全程用 pixel，
        要 nm 的話由**使用者填 nm/px**，見 ``steps/cd.py``）、``bin_map``
        （``{bin: 要寫的值}``，預設原樣寫）、``decimals``（預設 4）、
        ``skip_failed``（預設 True：ok=False 的不寫）。
        指定的欄位不存在 → :class:`ExportError`。
        全部都不指定 → 輸出檔與原檔**逐位元組相同**。

    ``annotate``
        ``extra_features``（要另外寫成欄位的特徵名 list）、``decimals``
        （預設 4）、``score_col`` / ``class_col``（預設 ``ADCSCORE`` /
        ``ADCCLASS``）、``missing_score`` / ``missing_class``
        （沒有結果的列填什麼，預設 0.0 / -1）。

    ``topn``
        ``n``（取前幾顆，0=改用 min_score）、``min_score``、``renumber``
        （預設 True）、``include_annotations``（預設 True，會一併做
        annotate 的欄位），加上 annotate 的所有選項。
    """
    text, plan = _build(doc, results, mode, **opts)
    _atomic_write_text(str(out_path), text)
    return plan

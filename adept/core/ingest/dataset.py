# Vendored/adapted into ADEPT on 2026-07-27.
# Source project: GLAS — file: glas/app/sem_loader.py (SemImage / load_klarf /
# load_folder patterns: per-defect image resolution relative to the KLARF dir,
# XREL/YREL surfacing, non-recursive folder scan). Detection and page->channel
# mapping are built on KLIP klarf_core (vendored as .klarf_core) and
# klarf_tif_probe (vendored as .tiff_index).
# Adaptations:
#   - added `from __future__ import annotations` (ADEPT convention)
#   - GLAS SemImage generalized to ImageRef / DefectItem / Dataset dataclasses
#     per the ADEPT ingest spec (multi-channel images per defect)
#   - KLARF ingest routed through klarf_core.KlarfDoc instead of GLAS
#     KlarfParser; per-defect filenames come from
#     KlarfDoc.defect_image_filename (ported GLAS concept)
#   - XREL/YREL converted to nm via doc.unit_info() (1.2 um -> x1000, 1.8 nm)
"""Dataset 組裝：KLARF (+ patch TIFF) 或資料夾 → 統一的 DefectItem 清單。

偵測邏輯（load_dataset）：
  1. 找得到 patch TIFF（呼叫端指定或 doc.tiff_path()）且
     doc.defect_image_map() 能對出 page → kind="ebi_patch"。
  2. 否則 defect 列帶 per-defect 檔名（defect_image_filename）
     → kind="rsem"，images={"single": ...}，路徑相對 KLARF 所在資料夾解析。
  3. 兩者皆無 → 仍回 kind="rsem"（僅 defect 中繼資料，無影像）並加 warning。

★ EBI patch 的 channel 指派（已確認 2026-07-30）★
  每個 defect 的 TIFF pages 依「出現順序」對應 channel_order：
  第 1 頁 = channel_order[0]（預設 "test"），第 2 頁 = channel_order[1]
  （預設 "ref"），多出來的頁依序命名 "img3", "img4", …。

  **第 1 頁 = test、第 2 頁 = ref 已由使用者確認**，不再是待驗證的假設。
  `channel_order` 參數保留：它擋的是另一件事 —— 一顆 defect 出三頁以上、
  或某個站點的機台設定不同 —— 那時候不必改程式，換一個順序就好。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import imageio, tiff_index
from . import klarf_core
from .klarf_core import KlarfDoc

_IMAGE_EXTS = {".png", ".tif", ".tiff", ".jpg", ".jpeg", ".bmp"}


@dataclass
class ImageRef:
    """一張影像的來源：多頁 TIFF 的某一頁（page 給 0-based 索引），
    或獨立影像檔（page=None）。channel 例："test" / "ref" / "single"。"""
    path: str
    page: Optional[int]
    channel: str


@dataclass
class DefectItem:
    """一顆 defect + 它的影像們。座標一律已換算為 nm（die 內相對座標）。"""
    defect_id: str
    die: Optional[Tuple[int, int]]          # (xindex, yindex)；folder 模式為 None
    xrel_nm: Optional[float]
    yrel_nm: Optional[float]
    images: Dict[str, ImageRef] = field(default_factory=dict)
    # 目前無來源可推得。**這不擋任何事**：pipeline 全程用 pixel，換算是輸出
    # 那一刻由使用者填的（見 steps/cd.py 與 export/klarf_out.py 的 size_scale）。
    nm_per_px: Optional[float] = None
    klarf_row: int = -1                     # doc.defects 的列索引；folder 模式為 -1
    tags: Dict[str, str] = field(default_factory=dict)

    def load(self, channel: str) -> np.ndarray:
        """讀出該 channel 的像素：TIFF 頁走 tiff_index.read_page，
        獨立影像檔走 imageio.load_gray（CJK 路徑安全）。"""
        if channel not in self.images:
            raise KeyError(
                f"defect {self.defect_id} has no channel {channel!r} "
                f"(available: {sorted(self.images)})")
        ref = self.images[channel]
        if ref.page is not None:
            return tiff_index.read_page(ref.path, ref.page)
        return imageio.load_gray(ref.path)


@dataclass
class Dataset:
    kind: str                               # "ebi_patch" | "rsem" | "folder"
    klarf: Optional[KlarfDoc]
    items: List[DefectItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _resolve_relative(base_dir: str, fname: str) -> str:
    """把 KLARF 內的影像檔名解析成路徑（相對 KLARF 所在資料夾；
    Windows 反斜線先正規化，絕對路徑原樣保留）。"""
    name = fname.replace("\\", "/")
    if os.path.isabs(name):
        return os.path.normpath(name)
    return os.path.normpath(os.path.join(base_dir, name))


def _channel_name(j: int, channel_order: Tuple[str, ...]) -> str:
    """第 j（0-based）頁的 channel 名：channel_order 用完後接 "img3", "img4"…"""
    if j < len(channel_order):
        return channel_order[j]
    return f"img{j + 1}"


def _base_item(doc: KlarfDoc, row_idx: int, row: List[str],
               to_nm: float) -> DefectItem:
    di = doc.col_index("DEFECTID")
    xi, yi = doc.col_index("XINDEX"), doc.col_index("YINDEX")
    xr, yr = doc.col_index("XREL"), doc.col_index("YREL")
    ci, ti = doc.col_index("CLASSNUMBER"), doc.col_index("TEST")

    defect_id = row[di] if 0 <= di < len(row) else str(row_idx + 1)
    die = None
    if 0 <= xi < len(row) and 0 <= yi < len(row):
        dx, dy = _to_int(row[xi]), _to_int(row[yi])
        if dx is not None and dy is not None:
            die = (dx, dy)
    x = _to_float(row[xr]) if 0 <= xr < len(row) else None
    y = _to_float(row[yr]) if 0 <= yr < len(row) else None
    tags: Dict[str, str] = {}
    if 0 <= ci < len(row):
        tags["classnumber"] = row[ci]
    if 0 <= ti < len(row):
        tags["test"] = row[ti]
    return DefectItem(
        defect_id=str(defect_id),
        die=die,
        xrel_nm=(x * to_nm) if x is not None else None,
        yrel_nm=(y * to_nm) if y is not None else None,
        klarf_row=row_idx,
        tags=tags,
    )


def load_dataset(klarf_path, tiff_path=None,
                 channel_order: Tuple[str, ...] = ("test", "ref")) -> Dataset:
    """載入 KLARF（可帶 patch TIFF）成 Dataset。偵測邏輯見模組 docstring。

    channel_order：EBI patch 模式下，每個 defect 的 TIFF 頁依出現順序
    指派到這些 channel（預設第 1 頁 = "test"、第 2 頁 = "ref"；多出的頁
    命名 "img3", "img4", …）。**預設順序已確認**（見模組 docstring）；
    這個參數是給「一顆多於兩頁」或站點慣例不同時換順序用的。
    """
    klarf_path = str(klarf_path)
    doc = klarf_core.load(klarf_path)
    warnings: List[str] = list(doc.warnings)
    base_dir = os.path.dirname(os.path.abspath(klarf_path))
    to_nm = float(doc.unit_info()["to_nm"])

    # ---- patch TIFF 偵測 ----
    tiff = str(tiff_path) if tiff_path is not None else doc.tiff_path()
    if tiff is not None and not os.path.isfile(tiff):
        warnings.append(f"Patch TIFF not found: {tiff}")
        tiff = None

    imap = None
    if tiff is not None:
        try:
            npages = tiff_index.n_pages(tiff)
        except (OSError, ValueError) as e:
            warnings.append(f"Could not index TIFF {tiff}: {e}")
            tiff = None
        else:
            imap = doc.defect_image_map(npages)
            if imap["mode"] is None:
                warnings.extend(imap["notes"])
                imap = None

    items: List[DefectItem] = []

    if imap is not None:
        # ---- kind="ebi_patch"：多頁 TIFF，defect → pages → channels ----
        kind = "ebi_patch"
        warnings.extend(imap["notes"])
        assert tiff is not None
        for k, (row, pages) in enumerate(zip(doc.defects, imap["pages"])):
            item = _base_item(doc, k, row, to_nm)
            for j, pg in enumerate(pages):
                ch = _channel_name(j, tuple(channel_order))
                item.images[ch] = ImageRef(path=tiff, page=int(pg), channel=ch)
            items.append(item)
        return Dataset(kind=kind, klarf=doc, items=items, warnings=warnings)

    # ---- kind="rsem"：per-defect 檔名（Image/Images {...} 區塊）----
    n_named = 0
    for k, row in enumerate(doc.defects):
        item = _base_item(doc, k, row, to_nm)
        fname = doc.defect_image_filename(row)
        if fname:
            n_named += 1
            item.images["single"] = ImageRef(
                path=_resolve_relative(base_dir, fname), page=None,
                channel="single")
        items.append(item)
    if n_named == 0:
        warnings.append(
            "No patch TIFF and no per-defect image filenames; "
            "dataset carries defect metadata only.")
    return Dataset(kind="rsem", klarf=doc, items=items, warnings=warnings)


def load_folder(folder) -> Dataset:
    """掃描資料夾（不遞迴）成 Dataset(kind="folder")。
    無座標資訊（GLAS load_folder 模式）：每個影像檔一個 DefectItem，
    defect_id = 檔名主幹，images={"single": ...}。"""
    d = str(folder)
    items: List[DefectItem] = []
    warnings: List[str] = []
    if not os.path.isdir(d):
        return Dataset(kind="folder", klarf=None, items=[],
                       warnings=[f"Not a directory: {d}"])
    for name in sorted(os.listdir(d)):
        path = os.path.join(d, name)
        stem, ext = os.path.splitext(name)
        if os.path.isfile(path) and ext.lower() in _IMAGE_EXTS:
            items.append(DefectItem(
                defect_id=stem, die=None, xrel_nm=None, yrel_nm=None,
                images={"single": ImageRef(path=path, page=None,
                                           channel="single")},
            ))
    if not items:
        warnings.append(f"No image files found in folder: {d}")
    return Dataset(kind="folder", klarf=None, items=items, warnings=warnings)

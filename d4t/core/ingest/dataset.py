# Vendored/adapted into d4t on 2026-07-27.
# Source project: GLAS — file: glas/app/sem_loader.py (SemImage / load_klarf /
# load_folder patterns: per-defect image resolution relative to the KLARF dir,
# XREL/YREL surfacing, non-recursive folder scan). Detection and page->channel
# mapping are built on KLIP klarf_core (vendored as .klarf_core) and
# klarf_tif_probe (vendored as .tiff_index).
# Adaptations:
#   - added `from __future__ import annotations` (d4t convention)
#   - GLAS SemImage generalized to ImageRef / DefectItem / Dataset dataclasses
#     per the d4t ingest spec (multi-channel images per defect)
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


class DataError(ValueError):
    """資料本身不是 d4t 處理得了的形狀（訊息是白話的，會顯示給使用者）。"""


def require_8bit(arr: np.ndarray, where: str) -> np.ndarray:
    """8-bit 就原樣回傳，否則**擋下來並講清楚**（F11）。

    為什麼是擋下來而不是「幫忙轉一下」
    ----------------------------------
    整條 pipeline 是 8-bit 的（``to_uint8`` / ``normalize`` / 直方圖…），而在這
    之前兩條載入路徑都會**安靜地**毀掉非 8-bit 的資料，實測過：

    * TIFF 頁 → ``to_uint8`` 把 0–4095 clip 到 0–255 → **93.8% 的像素飽和成 255**；
    * 影像檔 → ``load_gray`` 每張圖各自 MINMAX 拉伸 → 亮度砍半的圖載進來平均值
      **一模一樣**（兩張圖之間不再可比，而那是 ``test − ref`` 的前提）。

    而「自動降位」也不是安全的選項：12-in-16 與滿量程 16-bit 在檔案裡長得一樣，
    要除以 16 還是 256 **猜不出來**，猜錯就是全黑或飽和。所以這裡的處置是
    **講出看到了什麼**，然後停下來 —— 跟 ``channel_map`` 對不上時同一個原則：
    不准安靜地硬套。使用者的資料確認是 8-bit（2026-08-17），所以這是保險，
    不是常態路徑；真的遇到 16-bit 那天，轉換規則要**討論**過才加。

    引擎會把它包成這一顆 defect 的失敗（``ok=False``），不會殺掉整批（鐵則 7）。
    """
    a = np.asarray(arr)
    if a.dtype == np.uint8:
        return a
    hi = float(a.max()) if a.size else 0.0
    raise DataError(
        "%s is %s (values up to %g), and d4t works on 8-bit images. "
        "Converting it automatically is not safe - 12-bit-in-16 and full "
        "16-bit look identical in the file, so the scale factor would be a "
        "guess (getting it wrong saturates or blacks out the whole image). "
        "Export the data as 8-bit, or ask for a conversion setting."
        % (where, a.dtype, hi))


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
    #: **同一顆的附加檔**（F11 Region-3）：別的程式產的、跟這顆對應的影像。
    #: 目前只有一種 —— GLAS 的 ``layout_label``（GDS label map）。
    #:
    #: 為什麼**不放進 ``images``**：``images`` 的意思是「機台拍了幾張」，而
    #: ``load_single`` 的契約就建立在那個計數上（一顆兩張它會拒絕載入，而且
    #: 那個拒絕是對的 —— 見 `steps/load.py`）。把 label 混進去的話，每一顆
    #: RSEM defect 都會突然變成「兩張」而載不進來，而錯誤訊息會說謊
    #: （「這顆有 2 張影像」——不，它有 1 張影像跟 1 個附加檔）。
    sidecars: Dict[str, ImageRef] = field(default_factory=dict)
    #: 這一顆在 ``Dataset.items`` 裡的位置（由 :class:`Dataset` 自己編號）。
    #:
    #: F15：`pair_source` 的 ``match="order"`` 要它 —— 「第 n 顆對第 n 顆」在
    #: 卡片裡問不出來，因為卡片手上只有 ``DefectItem``。用 ``klarf_row`` 代替
    #: 不行：folder / stack 模式沒有 KLARF，那個欄位是 −1。
    index: int = -1
    #: 這一顆的 KLARF 欄位（``{欄名大寫: 字串值}``）。**預設是空的**。
    #:
    #: 只有被當成**第二個 source** 掛上來的那一份會填（`ingest/pair_source.py`）
    #: —— 它是 characterization 的關鍵：把配到那一顆的分數欄帶成 feature，
    #: 「配到但分數低、藏在 raw data 內」才答得出來。main 那一份不填，
    #: 因為每一顆多帶 24 個字串對誰都沒有好處。
    fields: Dict[str, str] = field(default_factory=dict)

    def load(self, channel: str) -> np.ndarray:
        """讀出該 channel 的像素：TIFF 頁走 tiff_index.read_page，
        獨立影像檔走 imageio.load_raw（CJK 路徑安全，**保留 dtype**）。

        **8-bit 以外的資料會在這裡被擋下來**（F11）。理由見
        :func:`require_8bit` —— 兩條路以前都會安靜地毀掉數字。
        """
        if channel not in self.images:
            raise KeyError(
                f"defect {self.defect_id} has no channel {channel!r} "
                f"(available: {sorted(self.images)})")
        return self._read(self.images[channel], channel)

    def load_sidecar(self, name: str) -> np.ndarray:
        """讀出一個附加檔的像素（見 :attr:`sidecars`）。

        跟 :meth:`load` 只差一件事，而那件事很重要：走
        :func:`imageio.load_exact`，**不做通道合併**。

        ``load_raw`` 對三通道的輸入會 ``cvtColor(BGR2GRAY)`` —— 對 SEM 影像那是
        對的，對 label map 是致命的：那張圖的像素值**是**層號，加權平均會把
        1、2、3 混成一堆不存在的值，**而且不會報錯**。而 GLAS 匯出時
        ``<id>_label.png`` 旁邊就放著三通道的 ``<id>_label_view.png``，
        指錯一個檔名整批就落在錯的地方。通道數的判斷留給卡片去講。
        """
        if name not in self.sidecars:
            raise KeyError(
                f"defect {self.defect_id} has no sidecar {name!r} "
                f"(available: {sorted(self.sidecars)})")
        return self._read(self.sidecars[name], name, exact=True)

    def _read(self, ref: "ImageRef", what: str,
              exact: bool = False) -> np.ndarray:
        if ref.page is not None:
            arr = tiff_index.read_page(ref.path, ref.page)
        elif exact:
            arr = imageio.load_exact(ref.path)
        else:
            arr = imageio.load_raw(ref.path)
        return require_8bit(arr, "%s of defect %s (%s)"
                            % (what, self.defect_id,
                               os.path.basename(str(ref.path))))


@dataclass
class Dataset:
    kind: str                               # "ebi_patch" | "rsem" | "folder"
    klarf: Optional[KlarfDoc]
    items: List[DefectItem] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    #: **掛在這一份上的第二（第三…）份資料**（F15），``{代號: Dataset}``。
    #:
    #: 這一份是 main：批次的迴圈跑它、route 由它的 ``kind`` 決定、KLARF 寫回
    #: 它。掛上來的那幾份只提供「另一張圖與它的座標」，不寫回、不進導覽。
    #:
    #: 為什麼掛在 Dataset 上而不是讓卡片自己讀檔：影像段快取的簽章是照
    #: 「這份資料是什麼」算的（`batch._dataset_token_for`）。卡片偷偷讀檔的話，
    #: 換一份第二 source 而簽章看不見 → 回舊影像（鐵則 9，F9 踩過兩次）。
    sources: Dict[str, "Dataset"] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.renumber()

    def renumber(self) -> None:
        """把 ``items`` 的位置寫回每一顆的 :attr:`DefectItem.index`。

        在這裡做（而不是每一條 ingest 路徑各自編號）是因為 ``Dataset`` 有六個
        建構點，而漏掉任何一個的症狀是「``match="order"`` 對到第 −1 顆」——
        跑得完、有數字、而且是錯的。
        """
        for i, item in enumerate(self.items or []):
            item.index = i


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


def _bit_depth_warning(path: str) -> Optional[str]:
    """這個 TIFF 不是 8-bit 的話，回一句話（載入時就講，不必等跑到某一顆）。

    位元深度在 IFD 的 tag 裡，所以這個檢查**不解碼像素**（`tiff_index.bit_depths`）。
    真正的守門在 :func:`require_8bit`；這裡只是把它提前到使用者按下 Open 的那一刻。
    """
    depths = [d for d in tiff_index.bit_depths(path) if d]
    if depths and any(d != 8 for d in depths):
        return ("%s is %s-bit; d4t works on 8-bit images and will refuse "
                "these pixels (converting them automatically would be a "
                "guess). Export the data as 8-bit."
                % (os.path.basename(str(path)),
                   "/".join(str(d) for d in depths)))
    return None


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
            note = _bit_depth_warning(tiff)
        except (OSError, ValueError) as e:
            warnings.append(f"Could not index TIFF {tiff}: {e}")
            tiff = None
        else:
            if note:
                warnings.append(note)
            # **不問頁數**（2026-08-20）。問一次頁數＝把整條 IFD 鏈走完，而使用
            # 者實測那在網路碟上是 106 秒（30962 頁）—— 載入的 115 秒裡有 106 秒
            # 是這一行。
            #
            # 而它換到的東西比想像中少：``defect_image_map`` 拿頁數只做兩件事，
            # 一是決定 IMAGELIST 是 0-based 還是 1-based，二是「ids 裝不裝得進
            # 這個檔」。第一件**給不給頁數的結論一模一樣**（兩條路都是
            # ``base = 0 if lo == 0 else 1``，見 `klarf_core.defect_image_map`）；
            # 第二件現在由 `tiff_index.read_page` 在真的讀到那一頁時回答，而且
            # 那句話更明確（「第 N 頁超出範圍，這個檔有 M 頁」）——比安靜地改用
            # sequential 對映**更難忽略**。
            imap = doc.defect_image_map(None)
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


def load_tiff_stack(path, per_defect: int = 1,
                    channel_order: Tuple[str, ...] = ("test", "ref")) -> Dataset:
    """一個**多頁 TIFF、沒有 KLARF** → ``Dataset(kind="tiff_stack")``（F11 Input-2）。

    為什麼要有這一條路
    ------------------
    使用者的多通道資料就是這個形式（「在大 TIFF 內，但這種大 tiff 不會伴隨
    klarf」）。而在這之前它**進不來，而且是安靜地進不來**：丟進
    :func:`load_folder` 的話，一個 15 頁的 TIFF 會變成**一顆** defect ——
    因為 ``imageio.load_gray`` 走 ``cv2.imdecode``，多頁 TIFF 只解得到第 0 頁。

    分組的規則
    ----------
    每 ``per_defect`` 張連續的頁算一顆（``per_defect=1`` 就是「每頁一顆」）。
    頁的名字照 ``channel_order``（第 1 張 ``test``、第 2 張 ``ref``、之後
    ``img3``…）—— **那只是預設名**，要叫 ``bse`` / ``se1`` 由 recipe 裡的
    ``channel_map`` 決定（F11 Input-1）。分組是**資料層**的事、命名是 recipe
    的事，兩件事刻意分開：同一批資料的「一顆幾張」不會因為換一份 recipe 而改變。

    對不齊的尾巴**不吞掉**
    ----------------------
    頁數不是 ``per_defect`` 的整數倍時，完整的那幾組照做，剩下的幾頁
    **不進任何一顆**，並在 ``warnings`` 裡講出剩幾頁 —— 安靜地把它們塞進最後
    一顆（或無聲丟掉）的話，那幾頁的數字會出現在錯的 defect 上。

    沒有 KLARF 的後果
    -----------------
    沒有座標、沒有 die、**不能寫回 KLARF**（輸出只有 CSV／報表）。
    ``Dataset.klarf`` 是 ``None``，UI 與 export 都是照它判斷的。
    """
    p = str(path)
    warnings: List[str] = []
    n = int(per_defect)
    if n < 1:
        return Dataset(kind="tiff_stack", klarf=None, items=[],
                       warnings=["Images per defect must be at least 1 (got %d)." % n])
    if not os.path.isfile(p):
        return Dataset(kind="tiff_stack", klarf=None, items=[],
                       warnings=["Not a file: %s" % p])
    try:
        npages = int(tiff_index.n_pages(p))
    except (OSError, ValueError) as e:
        return Dataset(kind="tiff_stack", klarf=None, items=[],
                       warnings=["Could not index TIFF %s: %s" % (p, e)])
    if npages < 1:
        return Dataset(kind="tiff_stack", klarf=None, items=[],
                       warnings=["%s has no pages." % p])

    groups = npages // n
    left = npages - groups * n
    if groups == 0:
        return Dataset(kind="tiff_stack", klarf=None, items=[], warnings=[
            "%s has %d page(s) but each defect needs %d - not even one "
            "complete defect. Check the images-per-defect setting."
            % (os.path.basename(p), npages, n)])
    if left:
        warnings.append(
            "%s has %d pages, which is not a multiple of %d: the last %d "
            "page(s) are not loaded (they would not make a complete defect)."
            % (os.path.basename(p), npages, n, left))

    note = _bit_depth_warning(p)
    if note:
        warnings.append(note)

    stem = os.path.splitext(os.path.basename(p))[0]
    items: List[DefectItem] = []
    for k in range(groups):
        item = DefectItem(defect_id="%s_%d" % (stem, k + 1), die=None,
                          xrel_nm=None, yrel_nm=None, klarf_row=k)
        for j in range(n):
            ch = _channel_name(j, tuple(channel_order))
            item.images[ch] = ImageRef(path=p, page=k * n + j, channel=ch)
        items.append(item)
    return Dataset(kind="tiff_stack", klarf=None, items=items,
                   warnings=warnings)


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
    multipage: List[str] = []
    for name in sorted(os.listdir(d)):
        path = os.path.join(d, name)
        stem, ext = os.path.splitext(name)
        if os.path.isfile(path) and ext.lower() in _IMAGE_EXTS:
            if ext.lower() in (".tif", ".tiff"):
                # 這條路是「一個檔案一顆、一顆一張圖」，所以多頁 TIFF **只讀得到
                # 第 0 頁**（``imageio.load_gray`` 走 ``cv2.imdecode``）。
                # 以前那件事完全沒有聲音：一個 15 頁的檔案安靜地變成一顆 defect。
                # 現在講出來，並指向那種資料真正的入口（``load_tiff_stack``）。
                try:
                    if int(tiff_index.n_pages(path)) > 1:
                        multipage.append(name)
                except (OSError, ValueError):
                    pass        # 讀不出頁數不是這條路要解的問題
            items.append(DefectItem(
                defect_id=stem, die=None, xrel_nm=None, yrel_nm=None,
                images={"single": ImageRef(path=path, page=None,
                                           channel="single")},
            ))
    if multipage:
        warnings.append(
            "%d file(s) have more than one page, and only the first page is "
            "used here (%s). Open such a file as an image stack instead - "
            "then every page group becomes a defect."
            % (len(multipage), ", ".join(multipage[:3])
               + ("…" if len(multipage) > 3 else "")))
    if not items:
        warnings.append(f"No image files found in folder: {d}")
    return Dataset(kind="folder", klarf=None, items=items, warnings=warnings)

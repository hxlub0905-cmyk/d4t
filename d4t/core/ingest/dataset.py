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
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import imageio, tiff_index
from .rawfile import RAW_EXTS, RawSpec, read_raw, suggest_shift
from . import klarf_core
from .klarf_core import KlarfDoc

#: 「多頁 TIFF」家族的副檔名（小寫比對）。``.i01`` 是使用者點名的新檔名
#: （2026-09-17）：內容是 TIFF、只是副檔名不同，所以它跟 ``.tif`` 走**同一條路**
#: —— 這裡、`klarf_core.PATCH_IMAGE_EXTS`、Studio 的檔案對話框三處要對得上。
_TIFF_EXTS = {".tif", ".tiff", ".i01"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp"} | _TIFF_EXTS

#: 多頁 TIFF 走錯入口時說的那一句 —— **`load_folder` 與 `load_image_file`
#: 共用一份**。這兩條路一樣只讀得到第 0 頁，而一個 15 頁的檔案安靜地變成
#: 一顆 defect 是這句話存在的理由；抄成兩份的那天，其中一份會停在舊的去處。
_MULTIPAGE_WARNING = (
    "%d file(s) have more than one page, and only the first page is "
    "used here (%s). Open such a file as an image stack instead - "
    "then every page group becomes a defect.")


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
    #: `.raw` 專用：**這個檔要怎麼讀**（寬高、位元深度、檔頭長度、降位位移）。
    #:
    #: 為什麼幾何住在**資料**上而不是卡片的參數上（F113）：`.raw` 裡沒有任何
    #: 一個 byte 在講寬高，那是**這一批檔案的性質**，不是「這份 recipe 想怎麼
    #: 量」。放進 recipe 的話，同一份 recipe 換一批不同尺寸的 raw 就會安靜地
    #: 讀出一張斜掉的圖；放在這裡，載入的當下就對得起來或當場報錯。
    raw: Optional["RawSpec"] = None


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
        spec = ref.raw
        if spec is not None:
            arr = read_raw(ref.path, spec)
        elif ref.page is not None:
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
    kind: str                   # "ebi_patch" | "rsem" | "tiff_stack" | "folder"
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

    def source_label(self) -> str:
        """**這份資料是從哪裡來的**，一句給人看的話（F117 F2）。

        有 KLARF 就是那個檔（廠內講的就是那個檔名）；沒有 KLARF 的三種
        （folder / doe_folder / 單張）回第一顆影像所在的資料夾 —— 那是使用者
        在 `Open images…` 挑的那個。

        ⚠ **答不出來就回空字串**，呼叫端那一列就不寫。一列寫著
        ``Source: unknown`` 比沒有那一列更像「我知道，只是弄丟了」。
        """
        import os

        src = str(getattr(self.klarf, "source_path", "") or "")
        if src:
            return src
        for item in self.items or []:
            for ref in (item.images or {}).values():
                path = str(getattr(ref, "path", "") or "")
                if path:
                    return os.path.dirname(path) or path
        return ""

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


def _not_a_tiff_message(path: str, err: Exception) -> str:
    """KLARF 旁邊那個影像檔打不開時說的那一句。

    以前是 ``Could not index TIFF <path>: Not a TIFF``。對 ``.tif`` 那句夠用；
    對 ``.I01`` 不夠 —— 那個副檔名的內容是 TIFF 是**還沒在廠內驗過的假設**
    （`docs/FAB-VALIDATION.md` #8），假設錯的那一天使用者看到的就是這一句，
    所以它要講出下一步：拿 `fab_probe/probe_tiff.py` 探它，把報告貼回來。
    """
    return ("Could not read %s as a TIFF (%s). d4t only knows TIFF-format "
            "image files next to a KLARF, whatever their extension. Run "
            "fab_probe/probe_tiff.py on this file and send the report; the "
            "defects are loaded without images for now."
            % (os.path.basename(str(path)), err))


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
            # 先看 8 個位元組是不是 TIFF —— `bit_depths` 對非 TIFF 是安靜的
            # （刻意的），而「不是 TIFF」要在**這裡**講一次，不是每一顆各講一次。
            tiff_index.check_header(tiff)
            note = _bit_depth_warning(tiff)
        except (OSError, ValueError) as e:
            warnings.append(_not_a_tiff_message(tiff, e))
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
        if doc.tiff_file_name and tiff_path is None:
            # KLARF 說了檔名、檔卻不在旁邊 —— 講那個檔名（2026-09-17：`.I01` 沒
            # 一起搬過來的時候，「沒有 patch TIFF」這句對使用者是謎語）。
            warnings.append(
                "The KLARF names its image file (%s) but that file is not "
                "next to the KLARF; defects are loaded without images."
                % os.path.basename(doc.tiff_file_name.replace("\\", "/")))
        else:
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


def load_image_file(path) -> Dataset:
    """載入**一個影像檔**成 ``Dataset(kind="folder")``（F85，2026-09-07）。

    使用者要的那條路是「一張大圖，沒有 KLARF」（PEAR 的用法），而在這之前
    唯一的入口是 :func:`load_folder` —— 也就是**得先把那張圖放進一個資料夾**。
    那一步沒有換到任何東西。

    ⚠ **``kind`` 仍然是 ``folder``，不新增一種。** 資料形狀跟
    :func:`load_folder` 逐項相同（``images={"single": …}``、沒有座標、寫不回
    KLARF），而多一個 kind 要同時動 `scope.SUPPORTED_KINDS`、
    `recipe_is_supported` 與那幾支測試 —— 換到的是零。代價是資料集標籤上會
    寫 ``folder``（使用者 2026-09-07 看過並接受：kind 講的是資料形狀，
    不是入口名字）。

    多頁 TIFF 跟 :func:`load_folder` 走**同一句警告**（同一份文字、同一個
    去處）—— 這條路一樣只讀得到第 0 頁。
    """
    p = str(path)
    if not os.path.isfile(p):
        return Dataset(kind="folder", klarf=None, items=[],
                       warnings=[f"Not a file: {p}"])
    stem, ext = os.path.splitext(os.path.basename(p))
    if ext.lower() not in _IMAGE_EXTS:
        return Dataset(kind="folder", klarf=None, items=[],
                       warnings=[f"Not an image file: {p} (expected one of "
                                 f"{', '.join(sorted(_IMAGE_EXTS))})"])
    warnings: List[str] = []
    if ext.lower() in _TIFF_EXTS:
        try:
            if int(tiff_index.n_pages(p)) > 1:
                warnings.append(_MULTIPAGE_WARNING % (1, os.path.basename(p)))
        except (OSError, ValueError):
            pass        # 讀不出頁數不是這條路要解的問題
    return Dataset(kind="folder", klarf=None, warnings=warnings, items=[
        DefectItem(defect_id=stem, die=None, xrel_nm=None, yrel_nm=None,
                   images={"single": ImageRef(path=p, page=None,
                                              channel="single")})])


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
            if ext.lower() in _TIFF_EXTS:
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
        warnings.append(_MULTIPAGE_WARNING
                        % (len(multipage), ", ".join(multipage[:3])
                           + ("…" if len(multipage) > 3 else "")))
    if not items:
        warnings.append(f"No image files found in folder: {d}")
    return Dataset(kind="folder", klarf=None, items=items, warnings=warnings)


#: DOE：一個資料夾裡一顆 defect 都湊不出來時說的那一句。
_DOE_EMPTY_WARNING = (
    "%d folder(s) have no image in them, so they are not defects (%s). "
    "In this mode every sub-folder is one defect and the images inside it "
    "are that defect's imaging conditions.")

#: DOE：兩個子目錄同名（不同層）時說的那一句。
_DOE_DUPLICATE_WARNING = (
    "%d folder name(s) appear more than once, and a defect id has to be "
    "unique (%s). Only the first one of each was loaded - rename the others.")


#: `.raw` 一個檔案都湊不出來時說的那一句。
_RAW_EMPTY_WARNING = (
    "No .raw files in: %s. This entry reads headerless raw images - a folder "
    "of PNG/TIFF is \u201cOpen folder\u2026\u201d instead.")


def load_raw_folder(folder, spec: "RawSpec") -> Dataset:
    """一個資料夾的 **`.raw`** → ``Dataset(kind="folder")``，每個檔案一顆 defect。

    ⚠ **kind 仍然是 ``folder``，不是第六種。** `.raw` 跟 PNG／TIFF 的差別只在
    「怎麼把 byte 變成像素」，而那件事在這裡就做完了 —— 一顆一張、沒有 KLARF、
    寫不回 KLARF，那些**形狀**跟 ``folder`` 一模一樣。新開一種 kind 的話，
    `SINGLE_IMAGE_KINDS`／起手卡／每一條 kind lint 都要多一格，而它們的答案會
    跟 ``folder`` 逐字相同 —— 那是抄第二份出來，而抄出來的那份會漂。
    **新的是入口，不是 kind**（`scope.INPUT_SOURCES` 上 ``folder`` 與 ``image``
    早就是兩個入口共用一個 kind 的先例）。

    ``spec.shift`` 是 ``None`` 時**當場量一次並整批共用**：讀第一個檔案，看實際
    用到幾位元（12-in-16 還是滿量程），之後每一張都用同一個位移。
    逐張量會讓兩張圖不再可比，而「比」是這個工具的全部（見 `rawfile` 的說明）。
    """
    d = str(folder)
    if not os.path.isdir(d):
        return Dataset(kind="folder", klarf=None, items=[],
                       warnings=[f"Not a directory: {d}"])
    names = [n for n in sorted(os.listdir(d))
             if os.path.isfile(os.path.join(d, n))
             and os.path.splitext(n)[1].lower() in RAW_EXTS]
    if not names:
        return Dataset(kind="folder", klarf=None, items=[],
                       warnings=[_RAW_EMPTY_WARNING % d])

    warnings: List[str] = []
    use = spec
    if use.shift is None:
        first = os.path.join(d, names[0])
        try:
            probe = read_raw(first, replace(use, shift=None))
        except IOError as e:
            return Dataset(kind="folder", klarf=None, items=[],
                           warnings=[str(e)])
        shift = suggest_shift(probe, use.bits)
        use = replace(use, shift=shift)
        # **決定了什麼要講出來**（同 `require_8bit` 的原則：不准安靜地硬套）。
        warnings.append(
            "Read as %s. The brightest pixel in %s uses %d bits, so every "
            "image in this folder is shifted down by %d bit(s) to 8-bit - the "
            "same shift for all of them, so they stay comparable."
            % (use.describe(), names[0],
               max(1, int(np.asarray(probe).max()).bit_length()), shift))

    items = [DefectItem(defect_id=os.path.splitext(n)[0], die=None,
                        xrel_nm=None, yrel_nm=None,
                        images={"single": ImageRef(
                            path=os.path.join(d, n), page=None,
                            channel="single", raw=use)})
             for n in names]
    return Dataset(kind="folder", klarf=None, items=items, warnings=warnings)


def load_doe_folder(root) -> Dataset:
    """**一個子目錄 = 一顆 defect、裡面每個檔案 = 一個 imaging condition。**

    這是 DOE 要的形狀（F110，使用者定調）：同一顆 defect、位置固定在 FOV 正中間、
    FOV 相同，用不同的 E-beam condition（Landing energy／電流）各拍一張，
    對齊之後在同一組 target／ref box 上比 SNR。對標公司內的 imageY 流程。

    ⚠ **跟 :func:`load_folder` 正好相反**，所以它是**第五種 kind** 而不是那一條
    路上的一個開關：那邊是「一個檔案一顆」，這邊是「一個資料夾一顆」。同一個
    ``kind`` 兩種形狀的下場是畫布說謊 —— ``step.SINGLE_IMAGE_KINDS`` 裡寫著
    ``folder``，而 DOE 的一顆有好幾張，於是畫布上那張預設的 ``load_single``
    對它一定報錯。一種 source 一張載入卡（`CLAUDE.md` §5），而這一種走
    ``load_patch``（它本來就吃 N 張 → N 條流）。

    **分組是資料層的事、命名是 recipe 的事** —— 照 :func:`load_tiff_stack` 那條
    紀律。這裡只按檔名排序給 ``test`` / ``ref`` / ``img3``… 這種位置名
    （:func:`_channel_name`），要叫 ``le300`` / ``le500`` 是 ``load_patch`` 的
    ``channel_map`` 的事。

    ⚠ **流的順序是「檔名排序」**，而那是一個契約：這些 ``ImageRef`` 的 ``page``
    都是 ``None``，所以 `steps/load._in_defect_order` 會退回 **dict 插入順序**
    —— 也就是這裡 ``sorted()`` 的順序，而 ``channel_map`` 的 1-based 編號正是
    照它數的。

    只掃**一層**子目錄：``defect_id`` 是快取 key 與 Studio 的 ``_items_by_id``
    的一部分，而巢狀結構裡同名的目錄天生可能重複 —— 撞名的第二個之後
    **不載入並講出來**，不是安靜地蓋掉（那會讓一顆 defect 拿到另一顆的圖）。
    湊不出東西的空目錄也一樣：進 ``warnings``，不吞掉（同 `load_tiff_stack`
    對零頭的處置）。
    """
    d = str(root)
    if not os.path.isdir(d):
        return Dataset(kind="doe_folder", klarf=None, items=[],
                       warnings=[f"Not a directory: {d}"])
    items: List[DefectItem] = []
    warnings: List[str] = []
    empty: List[str] = []
    dupes: List[str] = []
    seen: set = set()
    for name in sorted(os.listdir(d)):
        sub = os.path.join(d, name)
        if not os.path.isdir(sub):
            continue            # 這條路上「檔案」不是一顆 defect，是放錯地方
        files = [f for f in sorted(os.listdir(sub))
                 if os.path.isfile(os.path.join(sub, f))
                 and os.path.splitext(f)[1].lower() in _IMAGE_EXTS]
        if not files:
            empty.append(name)
            continue
        if name in seen:
            dupes.append(name)
            continue
        seen.add(name)
        item = DefectItem(defect_id=name, die=None, xrel_nm=None,
                          yrel_nm=None)
        for j, f in enumerate(files):
            ch = _channel_name(j, ("test", "ref"))
            item.images[ch] = ImageRef(path=os.path.join(sub, f), page=None,
                                       channel=ch)
        items.append(item)
    if empty:
        warnings.append(_DOE_EMPTY_WARNING
                        % (len(empty), ", ".join(empty[:3])
                           + ("…" if len(empty) > 3 else "")))
    if dupes:
        warnings.append(_DOE_DUPLICATE_WARNING
                        % (len(dupes), ", ".join(dupes[:3])
                           + ("…" if len(dupes) > 3 else "")))
    if not items:
        warnings.append(
            "No sub-folders with images in: %s. In this mode every sub-folder "
            "is one defect and the images inside it are that defect's imaging "
            "conditions - a folder of loose image files is “Open folder…” "
            "instead." % d)
    return Dataset(kind="doe_folder", klarf=None, items=items,
                   warnings=warnings)


# --------------------------------------------------------------------------- #
# KLARF 欄位 → DefectItem.fields（F15 給第二份用，F16 起 main 也用）
# --------------------------------------------------------------------------- #
#: 這兩支**住在這裡**而不是 `ingest/pair_source.py`：它們問的是「一份 Dataset
#: 的 KLARF 有哪些欄、把哪幾欄複製進每一顆」——跟配不配對無關。F15 先在配對那
#: 一支寫出來，F16 讓 main 也要用，於是它們搬回自己的家（`pair_source` 仍然
#: re-export，呼叫端一個字都不用改 —— 那是搬家，不是複製一份）。

def columns_of(dataset: Any) -> List[str]:
    """這一份 KLARF 有哪些欄（大寫）。沒有 KLARF 就是空的。

    UI 拿它當 `carry` 那一格的選單 —— **欄名程式知道，就不該讓使用者用打的**
    （同 `ParamForm` 的 `stream_choices` / `region_choices`）。
    """
    doc = getattr(dataset, "klarf", None)
    if doc is None:
        return []
    return [str(c).upper() for c in (getattr(doc, "defect_columns", None) or [])]


def fill_fields(dataset: Dataset,
                columns: Optional[Sequence[str]] = None) -> int:
    """把每一顆的 KLARF 欄位填進 ``DefectItem.fields``（回填了幾欄）。

    **兩份都會做，而且都只帶被點名的那幾欄。** F15 只有掛上來的第二份會填
    （`carry` 要讀的是配到那一顆的分數欄）；F16 起 main 那一份也填 —— 使用者要
    「利用 feature 內數值資料**跟原始 klarf 帶的資訊**去做分類」，而那些欄在此
    之前進不了 pipeline。規則兩邊一樣：**沒被點名的欄一欄都不帶**（見下面
    ``columns``），所以預設什麼都不填的 recipe 一個位元組都沒多帶。

    ``columns`` 是**只要這幾欄**（大小寫不拘）；``None`` = 全部。
    為什麼要這個參數：raw data 的 lot 是幾十萬顆，×24 欄字串是幾百 MB 的複製，
    而其中 22 欄從來沒有人 `carry`。這幾欄要進 worker（items 會被 pickle
    過去），所以它同時是記憶體與 pickle 的成本。``None`` = 全帶，那是 CLI 與
    測試的路；UI 與 recipe 走的一律是「只帶點名的那幾欄」。

    沒有 KLARF（folder / stack）→ 一欄都沒有，回 0。那不是錯誤，只是
    `carry` 在這種資料上沒有東西可帶。
    """
    doc = getattr(dataset, "klarf", None)
    if doc is None:
        return 0
    cols = columns_of(dataset)
    if not cols:
        return 0
    want = None if columns is None else {str(c).strip().upper()
                                         for c in columns if str(c).strip()}
    keep = [(i, c) for i, c in enumerate(cols) if want is None or c in want]
    rows = list(getattr(doc, "defects", None) or [])
    for item in dataset.items:
        r = int(getattr(item, "klarf_row", -1))
        if not (0 <= r < len(rows)):
            item.fields = {}
            continue
        row = rows[r]
        # **每次都整個換掉**，不是更新 —— 少填一欄的時候舊的那一份還留著的話，
        # 「這一欄現在還在不在」就有兩個答案（而卡片信的是 `fields`）。
        item.fields = {c: (str(row[i]) if i < len(row) else "")
                       for i, c in keep}
    return len(keep)


def missing_columns_of(dataset: Any,
                       columns: Optional[Sequence[str]]) -> List[str]:
    """``columns`` 裡**這一份根本沒有**的那幾欄（大寫，保留順序）。

    為什麼在這裡問而不是等卡片跑：這裡手上有 KlarfDoc，所以答得出「那它有哪些
    欄」——而卡片手上只有複製過去的那幾欄（`fill_fields` 的 ``columns``），
    它列出來的清單會是「你要的那幾欄」，不是「這一份有的那幾欄」。
    打錯一個欄名的時候，後者才是使用者要看的東西。

    （`ingest/pair_source.missing_columns` 是同一支，掛第二份時用；F16 起
    main 那一份也要問同一個問題，所以它住在這裡。）
    """
    have = set(columns_of(dataset))
    if not have:
        return []
    out: List[str] = []
    for c in (columns or ()):
        c = str(c).strip().upper()
        if c and c not in have and c not in out:
            out.append(c)
    return out

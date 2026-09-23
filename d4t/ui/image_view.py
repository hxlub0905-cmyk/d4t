# 影像檢視器 — 從 widgets.py 搬出來 2026-09-08 (U7).
# zoom/pan 骨架 vendored from: PEAR/pear/ui/image_view.py（去掉 ROI 編輯）。
"""``ImageView`` —— ndarray 檢視器（滾輪縮放、拖曳平移、雙擊 fit）。

它是 `widgets.py` 裡最大的一塊（778 行），而它跟旁邊那 23 個類別**一件事都
沒有共用** —— 它吃 ndarray、畫框、發座標訊號，如此而已。U7 那一刀。

這一份是**純搬移**：每一行都是原封搬過來的，一個字都沒有改。

⚠ **記號的顏色由角色決定，而角色住在這裡**（:data:`MARK_ROLE_TOKENS`）：
`d4t/core` 不得 import Qt，所以卡片說的是「這是 `!worst`」，「那是什麼紅」
是主題的事。報表用的是同一組語言（`core/export/overlay.py`），所以同一顆
defect 在畫面上與在報表上，**紅的永遠是「對到哪」、綠的永遠是「瞄準哪」**。
"""
from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QImage, QLinearGradient,
    QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

# ⚠ 顏色從 `export.ramps` 拿，**不要**從 `uniformity_charts`（報表產生器）——
# 後者底下掛著 boxplot／chart_draw／report／klarf_out，而這裡只要一個顏色。
from ..core.export.ramps import heat_hex as uc_heat_hex
from .numbers import format_feature_value_short
from . import theme
from .theme import TOKENS, region_hex

__all__ = [
    "ImageView", "to_uint8", "MARK_ROLE_TOKENS", "MARK_ROLE_WEIGHTS",
]


#: 標記的**角色** → 主題的哪一個顏色權杖（F33）。
#:
#: `Step.overlay_marks` 的 ``labels`` 平常是**具名區域**的名字（顏色因此跟影像
#: 上那個區域的框一模一樣）。``!`` 開頭的是**角色**而不是名字 —— 沿用
#: `decide_tree` 的 ``!failed`` / ``!unbinned`` 那個慣例，而區域名是識別字，
#: 不可能撞到。
#:
#: **卡片說角色，這裡挑顏色**：core 不得 import Qt，而「紅色是什麼紅」是主題的
#: 事。報表用的是同一組語言 —— 框紅、十字綠（`core/export/overlay.py` 的
#: `BOX_COLOR` / `AIM_COLOR`），所以同一顆 defect 在畫面上與在報表上，
#: **紅的永遠是「對到哪」、綠的永遠是「瞄準哪」**，而 `mark_alert` /
#: `mark_aim` 兩個權杖的值跟那兩個常數逐位元組相同。
#:
#: ⚠ **不要用介面的 `danger` / `success`**：那兩個是放在面板上的顏色（要跟白底
#: 相處，所以偏暗偏濁），而這些記號畫在**使用者的影像**上，還要跟
#: `REGION_COLORS` 分得開 —— 疊圖上其餘的框穿的正是那一組。`danger`（#d05a4c）
#: 跟第 8 個區域色（#f08a5f）只差 ΔE 19.9，一整排橘框裡它認不出來。
#: 這條有測試守著（`test_a_mark_role_never_wears_a_region_colour`）。
MARK_ROLE_TOKENS = {
    "!match": "mark_alert",  # 小圖真的對到的那一塊
    "!aim": "mark_aim",      # 機台瞄準的那一點
    "!worst": "mark_alert",  # 逐框比較挑出來的那一格（紅粗框，見下）
}

#: 有些角色要**畫粗**（預設 1.6）。角色 → 線寬。
#:
#: `!worst` 是使用者 2026-09-01 定的：「我傾向異常的那格用**紅框**（或不同
#: 顏色）的**加粗框**把它框出來」。
#:
#: ⚠ **第一版畫琥珀（照抄報表的 `ROI_WINNER_COLOR`），而它在畫面上幾乎看不
#: 出來** —— render 出來才發現：`theme.REGION_COLORS` 裡有 ``#f0b429``（琥珀）
#: 與 ``#f08a5f``（橘），而區域框穿的正是那一組。報表沒有這個問題，因為那張圖
#: 上其餘的框是鋼青色、紅色被「量到的那一塊」佔著。
#:
#: 所以規矩不是「跟報表同一個顏色」，是**在自己這張圖上不會跟旁邊撞**：
#: 螢幕上其餘的框穿區域色（含琥珀橘），紅色沒有人用；報表上紅色有人用，
#: 其餘的框是鋼青，琥珀沒有人用。兩張圖各自挑得出最響的那一個。
#: 加粗那一半兩邊一致（報表 2–3 px、這裡 2.6 px）—— 那是這個記號真正的
#: 共同語言：**最異常的那一格是唯一一個粗框**。
MARK_ROLE_WEIGHTS = {
    "!worst": 2.6,
}


# --------------------------------------------------------------------------- #
# numpy -> Qt
# --------------------------------------------------------------------------- #
def to_uint8(arr: np.ndarray) -> np.ndarray:
    """任意 ndarray -> 可顯示的 uint8。

    * ``uint8`` 直接用（不做任何拉伸，patch 的原始灰階就是原始灰階）。
    * 其他型別（float32 的 diff / snr_map、int16 …）走 min–max 自動拉伸；
      NaN / ±Inf 不參與統計，最後補 0（不會整張變白或炸掉）。
    """
    a = np.asarray(arr)
    if a.dtype == np.uint8:
        return np.ascontiguousarray(a)
    f = np.asarray(a, dtype=np.float64)
    finite = np.isfinite(f)
    if not finite.any():
        return np.zeros(f.shape, dtype=np.uint8)
    lo = float(f[finite].min())
    hi = float(f[finite].max())
    if hi <= lo:
        scaled = np.zeros(f.shape, dtype=np.float64)
    else:
        scaled = (f - lo) * (255.0 / (hi - lo))
    scaled = np.where(finite, scaled, 0.0)
    return np.ascontiguousarray(np.clip(scaled, 0.0, 255.0).astype(np.uint8))


def _qimage_from_uint8(arr: np.ndarray) -> QImage:
    """uint8 (H,W) / (H,W,3) / (H,W,4) -> QImage（deep copy，不依賴原 buffer）。"""
    a = np.ascontiguousarray(arr)
    if a.ndim == 2:
        h, w = a.shape
        img = QImage(a.data, w, h, w, QImage.Format_Grayscale8)
    elif a.ndim == 3 and a.shape[2] == 3:
        h, w, _ = a.shape
        img = QImage(a.data, w, h, 3 * w, QImage.Format_RGB888)
    elif a.ndim == 3 and a.shape[2] == 4:
        h, w, _ = a.shape
        img = QImage(a.data, w, h, 4 * w, QImage.Format_RGBA8888)
    else:
        raise ValueError(f"Unsupported image shape: {a.shape}")
    return img.copy()


# --------------------------------------------------------------------------- #
# 1. ImageView
# --------------------------------------------------------------------------- #
def _focus_set(focus: Any) -> frozenset:
    """``focus`` → 要畫滿的那幾條線的 index。

    吃一個 index（大多數卡片：一條代表線）或**一串** index（一個記號不只一條
    線 —— GLV 的贏家格是一個 X）。``-1`` / 空的 = 一條都不特別畫。
    """
    if focus is None:
        return frozenset()
    if isinstance(focus, (int, float)) and not isinstance(focus, bool):
        i = int(focus)
        return frozenset() if i < 0 else frozenset((i,))
    try:
        return frozenset(int(v) for v in focus if int(v) >= 0)
    except (TypeError, ValueError):  # 顯示用，不能擋畫面
        return frozenset()


#: 兩色格線的襯底色（見 `ImageView.set_overlay_look`）。**不是純黑**：純黑在
#: 暗區會跟影像內容混在一起，而這是一個記號不是內容。帶一點藍的深色跟 SEM 的
#: 中性灰分得開。
_CASING = "#0d1015"


class ImageView(QWidget):
    """ndarray 檢視器：滾輪對游標縮放、拖曳平移、雙擊 fit。

    放大到 1:1 以上時關掉平滑取樣（nearest-neighbour），缺陷 patch 的像素要
    看得出方格 —— 這是看 SEM 小圖的基本要求。
    """

    zoom_changed = Signal(float)
    cursor_info = Signal(str)          # "x 12  y 30  ·  gray 187"（離開時空字串）
    #: 縮放**或**平移之後的完整檢視狀態（scale, offset）。
    #: 並排比對兩張圖時，兩邊靠這個訊號互相跟隨 —— 沒有連動的並排沒有意義，
    #: 使用者得手動把兩邊拖到同一個位置才比得起來。
    view_changed = Signal(float, QPointF)
    #: 量尺拖曳中／拖完：``(axis, start, end)``，影像像素座標。
    #: 放開之後**不會**自動清掉（見 :meth:`set_measure_mode`）。
    measured = Signal(str, float, float)

    _MIN_SCALE = 0.02
    _MAX_SCALE = 60.0
    #: 沒有影像時畫在正中間的字。**可以換** —— 見 :meth:`set_empty_text`。
    _EMPTY_TEXT = "(no image)"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(240, 180)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._image: Optional[np.ndarray] = None      # 顯示用的 uint8
        self._pixmap: Optional[QPixmap] = None
        self._scale = 1.0
        self._offset = QPointF(0.0, 0.0)
        self._auto_fit = True                         # 尺寸變動時是否自動重 fit
        self._panning = False
        self._pan_start = QPointF()
        self._pan_offset = QPointF()
        #: 疊框的外觀（F120）：``None`` = 這個 app 一直以來的樣子（accent 細線）。
        #: 見 :meth:`set_overlay_look`。
        self._overlay_look = None
        #: 量尺模式（F120）：左鍵拖曳改成量，不是平移。見 `set_measure_mode`。
        self._measure_mode = False
        self._measuring: Optional[QPointF] = None
        #: 疊在影像上的 ROI 框（正規化座標）。見 :meth:`set_overlay`。
        self._overlay: List[Tuple[float, float, float, float]] = []
        self._overlay_focus = -1
        #: 每個框屬於哪一個具名區域（跟 ``_overlay`` 等長）。空字串 = 不分。
        self._overlay_labels: List[str] = []
        #: 區域名 -> 顏色索引，依**第一次出現**的順序。畫圖例時也走這一份。
        self._overlay_order: List[str] = []
        #: 回溯面板點了哪個區域（PR-3）：命中的框全強度、其餘降 alpha。
        #: **不 overload focus** —— 顏色=哪塊、粗細=缺陷格、alpha=你問的那塊。
        self._overlay_emphasis: List[str] = []
        #: 熱圖那一層（F87）：一塊一個色，鋪在影像上、框與標記**下面**。
        #: 見 :meth:`set_heat`。
        self._heat: List[Tuple[float, float, float, float]] = []
        self._heat_colors: List[str] = []
        self._heat_legend: Optional[Tuple[float, float, str]] = None
        #: 疊上去的不透明度（PEAR 是 178/255 —— 底下的圖案還看得見，
        #: 而顏色已經讀得出來）。
        self._heat_alpha = 178
        #: 量測標記（F19）：線段、每條線上的點、要畫粗的那一條。見 :meth:`set_marks`。
        self._marks: List[Any] = []
        #: 這一組標記要不要畫滿（`Step.marks_solid`）。
        self._marks_solid = False
        self._mark_points: List[Any] = []
        self._mark_focus: frozenset = frozenset()
        #: 每一條標記屬於哪一個具名區域（跟 ``_marks`` 等長；空字串 = 不分色）。
        self._mark_labels: List[str] = []
        #: 量測尺按著時的那一條帶（axis, 起, 迄；影像像素）。見 :meth:`set_measure`。
        self._measure: Optional[Tuple[str, float, float]] = None
        #: 選取的卡片上那個「以像素為單位」的參數有多大（大小, 標籤）。
        #: 見 :meth:`set_kernel_hint`。
        self._kernel: Optional[Tuple[float, str]] = None

    # -- public API --------------------------------------------------------
    def set_image(self, arr: Optional[np.ndarray]) -> None:
        """設定影像；``None`` 清空並顯示「（無影像）」。

        第一次拿到影像（或尺寸換了）會自動 fit；同尺寸的重繪保留目前的縮放/平移，
        調參數時視野不會被重設。
        """
        if arr is None:
            self._image = None
            self._pixmap = None
            self._auto_fit = True
            self.update()
            return
        u8 = to_uint8(arr)
        old_shape = None if self._image is None else self._image.shape[:2]
        self._image = u8
        self._pixmap = QPixmap.fromImage(_qimage_from_uint8(u8))
        if old_shape != u8.shape[:2]:
            self.fit()
        else:
            self.update()

    def has_image(self) -> bool:
        return self._image is not None

    def image(self) -> Optional[np.ndarray]:
        return self._image

    def scale(self) -> float:
        return self._scale

    def zoom_percent(self) -> int:
        return int(round(self._scale * 100))

    def fit(self) -> None:
        """整張影像置中縮放到剛好塞進畫布（留 4% 邊）。"""
        self._auto_fit = True
        if self._pixmap is None:
            return
        vw, vh = max(1, self.width()), max(1, self.height())
        iw, ih = self._pixmap.width(), self._pixmap.height()
        if iw <= 0 or ih <= 0:
            return
        self._scale = float(np.clip(min(vw / iw, vh / ih) * 0.96,
                                    self._MIN_SCALE, self._MAX_SCALE))
        self._offset = QPointF((vw - iw * self._scale) / 2.0,
                               (vh - ih * self._scale) / 2.0)
        self.update()
        self.zoom_changed.emit(self._scale)
        self.view_changed.emit(self._scale, QPointF(self._offset))

    def zoom_by(self, factor: float, anchor: Optional[QPointF] = None) -> None:
        """以 ``anchor``（畫布座標，預設中心）為定點縮放。"""
        if self._pixmap is None:
            return
        if anchor is None:
            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
        ia = self._to_image(anchor)
        new_scale = float(np.clip(self._scale * factor,
                                  self._MIN_SCALE, self._MAX_SCALE))
        if new_scale == self._scale:
            return
        self._scale = new_scale
        self._offset = QPointF(anchor.x() - ia.x() * self._scale,
                               anchor.y() - ia.y() * self._scale)
        self._auto_fit = False
        self.update()
        self.zoom_changed.emit(self._scale)
        self.view_changed.emit(self._scale, QPointF(self._offset))

    def set_view(self, scale: float, offset: QPointF) -> None:
        """直接套用另一張圖的檢視狀態（並排比對時用）。

        **不回發 view_changed** —— 兩邊互相跟隨會無限來回。跟隨是單向的，
        由發起操作的那一邊推過去。
        """
        s = float(np.clip(float(scale), self._MIN_SCALE, self._MAX_SCALE))
        if s == self._scale and QPointF(offset) == self._offset:
            return
        self._scale = s
        self._offset = QPointF(offset)
        self._auto_fit = False
        self.update()

    def view_state(self) -> Tuple[float, QPointF]:
        return self._scale, QPointF(self._offset)

    def zoom_in(self) -> None:
        self.zoom_by(1.25)

    def zoom_out(self) -> None:
        self.zoom_by(1 / 1.25)

    # -- transforms --------------------------------------------------------
    def set_overlay(self, rects: Optional[Sequence[Sequence[float]]],
                    focus: int = -1,
                    labels: Optional[Sequence[str]] = None) -> None:
        """把 ROI 框疊在影像上（**正規化**座標 ``(nx, ny, nw, nh)``）。

        為什麼要疊在這裡而不是只有「跨顆檢視」那個視窗
        ----------------------------------------------
        定位卡的參數是**一邊拖一邊看**決定的（F7-8 那條：「先想好一個數字再
        輸入」那個順序是反的）。框只出現在另一個要按鈕、要跑完一批才看得到的
        視窗裡，等於把這件事變成「改一次、跑一次、再回來看」——
        而敏感度這種參數要試十幾次。

        座標用正規化的，所以縮放平移都跟著影像走，換一顆 patch 尺寸也不用重算。
        ``focus`` 是要特別標出來的那一個（交會定位的 ``_center``：缺陷所在的
        那一塊），畫成粗線＋角標，其餘畫細線 —— 一堆一模一樣的框看不出哪個是
        「這一顆」的。

        ``labels`` 是每個框屬於**哪一個具名區域**（跟 ``rects`` 等長）。
        給了就一個區域一個顏色，並在左上角畫一份圖例（F11 Region 第八輪，
        使用者回報「Image Stream 顯示上顏色 overlay 重疊會同個顏色（藍色）」）。

        為什麼一定要分色：Region-1 之後**一張卡可以標好幾個區域**，而這裡把它們
        全部攤平成一串框，全部畫成 accent 藍。兩個區域疊在一起的時候畫面上就只是
        一團藍線 —— 而使用者要判斷的正是「哪一塊是 ROI1、哪一塊是 ROI2」。
        顏色跟模板編輯器**同一組**（`theme.REGION_COLORS`）：他在對話框裡把
        ROI1 畫成綠色的，到了 patch 上它就要還是綠色的。

        角色分工：**顏色 = 哪一個區域，線寬與角標 = 哪一塊是缺陷那一塊。**
        兩個問題各佔一個視覺維度，不要用同一個維度回答兩次（這是「焦點框以前
        畫成紅色」被換掉的原因 —— 紅色會被讀成第三個區域）。
        """
        self._overlay = [tuple(float(v) for v in r) for r in (rects or [])
                         if r is not None and len(tuple(r)) == 4]
        self._overlay_focus = int(focus)
        names = [str(v) for v in (labels or [])]
        # 長度對不上就整組不分色 —— 錯位的顏色比沒有顏色糟得多（它會**指錯**
        # 區域，而畫面上沒有任何東西透露這件事）。
        self._overlay_labels = (names if len(names) == len(self._overlay)
                                else [""] * len(self._overlay))
        order: List[str] = []
        for n in self._overlay_labels:
            if n and n not in order:
                order.append(n)
        self._overlay_order = order
        # 換一組框＝上一個「你問的那塊」不再成立（框可能已經是別張卡的）。
        self._overlay_emphasis = []
        self.update()

    def set_overlay_emphasis(self, names: Optional[Sequence[str]]) -> None:
        """把某幾個區域**點亮**（其餘的框降 alpha）—— 回溯面板「點一項亮那
        一塊」用（PR-3）。`set_overlay` 會清掉它：換一組框之後舊的強調指的
        可能已經是別張卡的區域。"""
        self._overlay_emphasis = [str(n) for n in (names or []) if str(n)]
        self.update()

    def overlay_emphasis(self) -> List[str]:
        """現在點亮的區域名（測試讀這個，不去讀畫素）。"""
        return list(self._overlay_emphasis)

    def set_heat(self, cells: Optional[Sequence[Sequence[float]]] = None,
                 colours: Optional[Sequence[str]] = None,
                 legend: Optional[Sequence[Any]] = None,
                 alpha: int = 178) -> None:
        """把**熱圖**鋪在影像上（正規化座標，同 :meth:`set_overlay`）。

        ``cells`` 是 ``[(nx, ny, nw, nh), …]``、``colours`` 等長的 hex 色，
        ``legend`` 是 ``(lo, hi, 一句話)``（沒有就不畫色條）。

        為什麼是第三層，而不是 :meth:`set_overlay` 的一個模式
        ----------------------------------------------------
        框是**空心的線**，回答「recipe 說要看哪裡」；這一層是**填滿的色**，
        回答「這一塊量出來多少」。而且它必須畫在框**底下** —— PEAR 的
        `_paint_heat_cells` 就是這個順序，理由是框的用途是「這一塊的顏色是從
        哪一格量來的」，被色塊蓋掉的話那句話就沒了。

        資料由**卡片自己**交出來（`Step.overlay_heat`），跟
        :meth:`set_marks` 同一條界線：meta 的形狀是那張卡的事，UI 只負責畫。

        兩條保險跟 :meth:`set_overlay` 一字不差：座標正規化（縮放平移、換一顆
        都跟著走），而**長度對不上就整組不畫** —— 錯位的顏色會把值畫在別的
        地方，而畫面上沒有任何東西透露那件事。
        """
        boxes = [tuple(float(v) for v in tuple(c)[:4])
                 for c in (cells or []) if c is not None and len(tuple(c)) >= 4]
        cols = [str(c) for c in (colours or [])]
        if len(cols) != len(boxes):
            boxes, cols = [], []
        self._heat = boxes
        self._heat_colors = cols
        got = tuple(legend or ())
        self._heat_legend = ((float(got[0]), float(got[1]), str(got[2]))
                             if len(got) >= 3 else None)
        self._heat_alpha = int(max(0, min(255, int(alpha))))
        self.update()

    def clear_heat(self) -> None:
        self.set_heat([], [], None)

    def heat_count(self) -> int:
        """現在鋪了幾塊 —— **測試讀這個**，不去讀畫素。"""
        return len(self._heat)

    def heat_legend(self) -> Optional[Tuple[float, float, str]]:
        return self._heat_legend

    def set_marks(self, lines: Optional[Sequence[Any]] = None,
                  points: Optional[Sequence[Any]] = None,
                  focus: Any = -1,
                  labels: Optional[Sequence[str]] = None,
                  solid: bool = False) -> None:
        """把**量測標記**疊在影像上（正規化座標）。

        ``lines`` 是 ``[[(x0, y0), (x1, y1)], …]``，``points[i]`` 是第 i 條線段
        上的點。``focus`` 是要畫粗的那一條（代表值那一條）—— **也可以是一串**
        （一個記號本來就可能不只一條線）。

        ⚠ **不只一條那件事是踩出來的**：GLV 的贏家格畫的是一個 **X**，而 X 是
        兩條線；`focus` 只認得一個 index 的時候，第二條落在 alpha 70、1px 那
        一組 —— 於是畫面上那一格中間是**一條斜線**，不是一個 X。使用者
        2026-09-01 看著截圖問「框中間有一條斜線?」。而當時的測試**把那個形狀
        寫死了**（`assert focus == 1  # X 的第一條`）：測試守住的是 bug 的形狀，
        不是那句「畫一個 X」的意圖。

        為什麼跟 :meth:`set_overlay` 分開
        ---------------------------------
        框回答的是「recipe 說要看哪裡」，標記回答的是「這一顆**真的量到了**
        什麼」—— 後者只有跑過才有，而且它是逐顆變的。混在同一支裡的話，
        「框還在但標記消失了」這個最有用的狀態（這顆量不出來）就講不出來。

        資料由**卡片自己**交出來（`Step.overlay_marks`）：meta 的形狀是那張卡的
        事，UI 只負責畫。所以下一張量測卡不必再發明一套。

        ``solid`` 是**那張卡說的**（`Step.marks_solid`）：交出來的是少少幾條
        結構線（一個框、一個十字）而不是幾十條掃描線時，淡化不是在減少雜訊，
        是在藏起唯一的資訊。預設 False —— CD 與 GLV 都**刻意**靠淡化。

        ``labels`` 是每一條標記屬於**哪一個具名區域**，而顏色**沿用框那一組的
        順序**（:meth:`set_overlay` 已經排好的 ``_overlay_order``）—— 各自從
        自己那邊數的話，同一塊區域的框是綠的、量它的那些線卻是橘的，而畫面上
        沒有任何東西說得出它們是同一塊。沒給 labels 就整組畫 accent。

        兩條保險跟 :meth:`set_overlay` 一字不差：座標正規化（縮放平移、換一顆
        patch 都跟著走），而**長度對不上就整組不畫** —— 錯位的標記會指向錯的
        地方，而畫面上沒有任何東西透露那件事。
        """
        segs = [[(float(a[0]), float(a[1])), (float(b[0]), float(b[1]))]
                for a, b in (lines or []) if a is not None and b is not None]
        pts = [[(float(x), float(y)) for x, y in (grp or [])]
               for grp in (points or [])]
        names = [str(v) for v in (labels or [])]
        self._marks = segs
        self._marks_solid = bool(solid)
        self._mark_points = pts if len(pts) == len(segs) else []
        self._mark_labels = (names if len(names) == len(segs)
                             else [""] * len(segs))
        for n in self._mark_labels:
            if n and n not in self._overlay_order:
                self._overlay_order.append(n)
        self._mark_focus = _focus_set(focus)
        self.update()

    def clear_marks(self) -> None:
        self.set_marks([], [], -1, [])

    def mark_legend(self) -> List[Tuple[str, str]]:
        """標記用到的 ``[(區域名, 顏色 hex), …]``。測試與狀態列讀這個。"""
        index_of = {n: i for i, n in enumerate(self._overlay_order)}
        out: List[Tuple[str, str]] = []
        for n in self._mark_labels:
            if n and n in index_of and n not in [k for k, _c in out]:
                out.append((n, region_hex(index_of[n])))
        return out

    def mark_count(self) -> int:
        """畫了幾條量測線。測試與狀態列讀這個，不去讀畫素。"""
        return len(self._marks)

    def overlay_legend(self) -> List[Tuple[str, str]]:
        """圖例：``[(區域名, 顏色 hex), …]``，依第一次出現的順序。

        測試與狀態列讀這個，不去讀畫素。
        """
        return [(n, region_hex(i)) for i, n in enumerate(self._overlay_order)]

    def legend_visible(self) -> bool:
        """圖例現在畫不畫得出來（測試讀這個，不去讀畫素）。

        **兩個以上的區域才畫** —— 只有一個的時候那個顏色沒有在跟誰對比，
        一行字只是擋住影像。
        """
        return len(self._overlay_order) >= 2

    def overlay_count(self) -> int:
        """現在疊了幾個框（測試與狀態列讀這個，不去讀畫素）。"""
        return len(self._overlay)

    def overlay_rects(self) -> List[Tuple[float, float, float, float]]:
        """現在疊的那幾個框本身（正規化 ``(x, y, w, h)``）。

        為什麼不只給 :meth:`overlay_count`：**數量不是不變量，形狀才是。**
        「只切橫線」這種事只能從框的寬高看出來 —— 一個會把外圈修掉的呼叫者
        （F120 的格線）數量會變，而「每一格都是整張寬」不會變。
        """
        return list(self._overlay)

    def set_measure(self, axis: str, start: float, end: float) -> None:
        """曲線面板上的量測尺按著時，在影像上標出**同一段**（F8 量測尺）。

        為什麼影像上也要標
        ------------------
        曲線面板上的一段只是「第 40 到第 74 個取樣點」。使用者要判斷的是
        「我量到的是不是兩根 MG 的距離」—— 那個問題只有看影像答得出來。
        少了這條同步標記，量測尺量到的東西就得靠腦補對回圖上。

        座標是**影像像素**（投影曲線一個取樣點 = 一個像素列／行，所以兩者
        就是同一個索引）。``axis`` 為 ``"x"`` 時標的是兩條垂直線之間，
        ``"y"`` 是兩條水平線之間。
        """
        axis = str(axis or "")
        if axis not in ("x", "y"):
            self.clear_measure()
            return
        a, b = float(start), float(end)
        self._measure = (axis, min(a, b), max(a, b))
        self.update()

    def set_overlay_look(self, colour: str = "", cased: bool = False) -> None:
        """疊框換個顏色、外加一圈深色襯底（F120，**選配**）。

        為什麼需要襯底
        --------------
        ⚠ **一張灰階影像上沒有任何單一顏色是到處都看得見的** —— 這是量出來的，
        不是美感。在一張 SEM 合成圖上（灰階 1/25/50/75/99 百分位 =
        100/115/156/169/217），各候選對**最糟**那一格的 WCAG 對比是：

            accent 藍 1.04 · stage_measure 1.26 · 綠 1.22
            magenta 1.16 · cyan 1.09 · yellow 1.07   （圖形的門檻是 3.0）

        也就是說**目前這條 accent 藍的線在中灰上等於不存在**。換一個更好的顏色
        救不了：亮色輸在亮區、暗色輸在暗區，而一張 SEM 影像兩種都有。

        兩色線（深色襯底 ＋ 亮芯）就沒有這個問題 —— 每一格取兩者較好的那一個：

            黑襯＋黃芯 最糟 3.92 · 黑襯＋青芯 3.85 · 黑襯＋白芯 4.74

        > **一條在某些地方看不見的格線，比沒有格線更糟** —— 使用者會以為那裡
        > 沒有被切到。

        ⚠ **預設不開**：Studio 的區域框走同一支 `_paint_overlay`，而它們的顏色
        是有意義的（`region_hex` 一區一色）。這是 pitch helper 自己打開的。
        """
        self._overlay_look = (str(colour), bool(cased)) if colour else None
        self.update()

    def overlay_look(self):
        """現在的疊框外觀（``(colour, cased)``；沒設就 None）。測試讀這個。"""
        return self._overlay_look

    def set_empty_text(self, text: str) -> None:
        """沒有影像時，中間那句話要寫什麼（F120）。

        預設的 `(no image)` **只描述現況，沒有告訴人下一步**。在一個空畫布
        佔了 700×700、而唯一要做的事寫在工具列 11px 灰字裡的視窗上，那句話
        待在錯的地方：**指令要在空間裡，不是在角落。**
        """
        self._EMPTY_TEXT = str(text) or "(no image)"
        self.update()

    def set_measure_mode(self, on: bool) -> None:
        """量尺模式：左鍵拖曳**改成量長度**，不再平移（F120）。

        為什麼是一個模式而不是一個修飾鍵
        --------------------------------
        這張圖上左鍵本來就是平移，而平移是這個視窗最常用的手勢。搶走它要讓
        使用者**看得見自己搶走了** —— 一顆按下去會亮的鈕做得到，
        ``Shift`` 做不到（按鍵在畫面上沒有形狀，而一個「為什麼拖不動了」的
        使用者不會想到去放開一個他沒有按下的鍵）。

        ⚠ **放開之後那條帶留著。** 這一點跟 F8 曲線上那把尺**刻意相反**：
        那一把是「現在正在量」的回饋，量完就沒事了；這一把量出來的數字
        **使用者下一步要拿去用**（按一下就填進週期欄），所以它得活到那一下。
        離開模式、換圖、重裁就清掉 —— 那三件事都表示「剛剛量的不算了」。

        量的是**沿著主要拖曳方向的那一段**（|dx| > |dy| 就是 X）：pitch 問的
        是「隔多遠重複一次」，而那是一個軸上的距離，不是一條斜線的長度。
        """
        on = bool(on)
        if on == self._measure_mode:
            return
        self._measure_mode = on
        self._measuring = None
        if not on:
            self.clear_measure()
        self.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)
        if not on:
            self.unsetCursor()

    def measure_mode(self) -> bool:
        return self._measure_mode

    def clear_measure(self) -> None:
        """放開量測尺 —— 標記跟著消失（它是「現在正在量」的回饋，不是註記）。"""
        if self._measure is not None:
            self._measure = None
            self.update()

    def measure_span(self) -> Optional[Tuple[str, float, float]]:
        """現在標著的那一段（沒有就 None）。測試與狀態列讀這個。"""
        return self._measure

    def set_kernel_hint(self, size_px: float, label: str = "") -> None:
        """把「這個核心有多大」畫在影像上（F11 Enhance-UI-A）。

        為什麼這一格要有
        ----------------
        ``flatten`` 的 *Scale to remove* 與 ``denoise`` 的 *Filter size* 的
        help 裡唯一的規則是**跟缺陷比**：前者要「明顯大於」，後者（hot_pixels）
        要「貼著」。而畫面上原本沒有任何尺度參考 —— 使用者只能猜像素數，
        或者去數影像的邊長。

        這跟 F7-8「把 min/max 填好，滑桿是免費的」是同一條：**使用者是一邊看
        影像一邊決定值的**，所以那個參考就該在影像上，不是在 help 裡。

        畫在**影像正中央**：patch 是以缺陷為中心裁的（`ARCHITECTURE.md`），
        所以正中央就是要比大小的那個東西。大張的 RSEM 影像上中央不是缺陷，
        但要比的是「這個框 vs 畫面上的結構」，位置不影響那個判斷。

        方框而不是圓：高斯／中位數的鄰域就是方的。形態學那幾個是橢圓，但**範圍**
        一樣 —— 而使用者要判斷的是範圍。
        """
        n = float(size_px)
        if not np.isfinite(n) or n <= 0:
            self.clear_kernel_hint()
            return
        self._kernel = (n, str(label or ""))
        self.update()

    def clear_kernel_hint(self) -> None:
        if self._kernel is not None:
            self._kernel = None
            self.update()

    def kernel_hint(self) -> Optional[Tuple[float, str]]:
        """現在畫著的核心大小（沒有就 None）。測試讀這個，不去讀畫素。"""
        return self._kernel

    def _paint_heat(self, p: QPainter) -> None:
        """半透明的磚 ＋ 一條橫的色條（PEAR 的版型）。

        磚**不描邊**：相鄰兩塊本來就該連成一片，描了邊之後一片梯度會讀成
        一排小方塊 —— 那正是 `cell_boxes` 鋪滿中線要避免的事。
        """
        if self._pixmap is None or not self._heat:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        s_ = self._scale or 1.0
        p.setPen(Qt.NoPen)
        for (nx, ny, nw, nh), hexcol in zip(self._heat, self._heat_colors):
            col = QColor(hexcol)
            if not col.isValid():
                continue
            col.setAlpha(self._heat_alpha)
            p.setBrush(col)
            # **相鄰兩塊之間不留縫**：各自四捨五入的話會露出一條背景色的細線，
            # 而那條線看起來像資料裡的一道邊界。多畫半個像素蓋掉它。
            p.drawRect(QRectF(self._offset.x() + nx * iw * s_,
                              self._offset.y() + ny * ih * s_,
                              max(1.0, nw * iw * s_) + 0.5,
                              max(1.0, nh * ih * s_) + 0.5))
        p.setBrush(Qt.NoBrush)
        self._paint_heat_bar(p)

    def _paint_heat_bar(self, p: QPainter) -> None:
        """色條 —— **沒有它那些顏色不是資料，只是裝飾**（PEAR 同款：橫的、
        150×12、壓在左下角，兩端寫值）。"""
        if self._heat_legend is None:
            return
        lo, hi, label = self._heat_legend
        f = QFont(p.font())
        f.setPixelSize(theme.font_px("font_small"))
        p.setFont(f)
        fm = QFontMetricsF(f)
        pad, w, h, line = 5.0, 150.0, 12.0, fm.height()
        box = QRectF(6.0, self.height() - (line * 2 + h + pad * 2 + 8.0),
                     w + pad * 2, line * 2 + h + pad * 2)
        # **底下墊一塊**（同 `_paint_overlay_legend`）：色條會落在影像上，
        # 而影像可以是任何亮度 —— 直接寫字的話，深色的圖上那兩個數字看不見，
        # 於是那些顏色不再是資料、只是裝飾。
        chip = QColor(TOKENS["bg_surface"])
        chip.setAlpha(205)
        p.setPen(Qt.NoPen)
        p.setBrush(chip)
        p.drawRoundedRect(box, 3.0, 3.0)
        x, y = box.left() + pad, box.top() + pad + line
        grad = QLinearGradient(x, 0.0, x + w, 0.0)
        for t in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
            grad.setColorAt(t, QColor(uc_heat_hex(t)))
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(x, y, w, h), 2.0, 2.0)
        p.setPen(QColor(TOKENS["text_primary"]))
        p.drawText(QRectF(x, box.top() + pad, w, line),
                   Qt.AlignLeft | Qt.AlignVCenter, str(label))
        p.setPen(QColor(TOKENS["text_secondary"]))
        foot = QRectF(x, y + h, w, line)
        p.drawText(foot, Qt.AlignLeft | Qt.AlignVCenter,
                   format_feature_value_short(lo))
        p.drawText(foot, Qt.AlignRight | Qt.AlignVCenter,
                   format_feature_value_short(hi))
        p.setBrush(Qt.NoBrush)

    def _paint_overlay(self, p: QPainter) -> None:
        if self._pixmap is None or not self._overlay:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        s = self._scale or 1.0
        index_of = {n: i for i, n in enumerate(self._overlay_order)}
        look = self._overlay_look
        plain = QColor(look[0] if look else TOKENS["accent"])
        p.setBrush(Qt.NoBrush)
        for i, (nx, ny, nw, nh) in enumerate(self._overlay):
            name = self._overlay_labels[i] if i < len(self._overlay_labels) else ""
            col = QColor(region_hex(index_of[name])) if name in index_of else plain
            if self._overlay_emphasis and name not in self._overlay_emphasis:
                # 沒被問到的框退到背景 —— 淡，但還在（它們是脈絡，不是雜訊）。
                col.setAlphaF(0.28)
            r = QRectF(self._offset.x() + nx * iw * s,
                       self._offset.y() + ny * ih * s,
                       max(1.0, nw * iw * s), max(1.0, nh * ih * s))
            focused = (i == self._overlay_focus)
            # 框在小 patch 上會很細，所以線寬不隨縮放變薄（**框是給人看的標記，
            # 不是影像內容**）；但也不要粗到把 5px 的框整個蓋掉。
            # 兩色線的芯要比平常的框**粗一點**（1.3 而不是 1.0）：襯底畫在
            # 它兩側，芯太細的話看到的幾乎全是襯底，亮色只剩一絲 —— 實拍的
            # 黃色格線就被襯底吃成橄欖綠。
            width = (1.9 if focused else 1.0)
            if look is not None and look[1] and not focused:
                width = 1.3
            pen = QPen(col, width)
            pen.setCosmetic(True)
            if look is not None and look[1]:
                # 先畫一條粗一點的深色線當襯底，亮芯再蓋上去。兩條都 cosmetic，
                # 所以縮放的時候襯底不會比芯厚得不成比例。
                casing = QPen(QColor(_CASING), pen.widthF() + 1.6)
                casing.setCosmetic(True)
                p.setPen(casing)
                p.drawRect(r)
            p.setPen(pen)
            p.drawRect(r)
            if focused:
                self._paint_focus_ticks(p, r, pen)
        self._paint_overlay_legend(p)

    def _paint_focus_ticks(self, p: QPainter, r: QRectF, pen: QPen) -> None:
        """缺陷那一塊的四個角標。

        以前這件事是用**紅色**講的。分色之後不能再那樣：紅色會被讀成「第三個
        區域」，而它其實跟區域無關。角標是純幾何的記號，跟任何區域顏色都不衝突
        —— 而且在框小到只剩幾個像素、線寬看不出差別的時候，它仍然看得見。
        """
        tick = max(3.0, min(7.0, min(r.width(), r.height()) * 0.35))
        wide = QPen(pen)
        wide.setWidthF(pen.widthF() + 0.9)
        p.setPen(wide)
        for x, dx in ((r.left(), 1.0), (r.right(), -1.0)):
            for y, dy in ((r.top(), 1.0), (r.bottom(), -1.0)):
                p.drawLine(QPointF(x, y), QPointF(x + dx * tick, y))
                p.drawLine(QPointF(x, y), QPointF(x, y + dy * tick))
        p.setPen(pen)

    def _paint_overlay_legend(self, p: QPainter) -> None:
        """左上角的圖例。**兩個以上的區域才畫** —— 只有一個的時候，那個顏色
        沒有在跟誰對比，一行字只是擋住影像。"""
        if not self.legend_visible():
            return
        legend = self.overlay_legend()
        f = QFont(p.font())
        f.setPixelSize(theme.font_px("font_small"))
        p.setFont(f)
        fm = QFontMetricsF(f)
        pad, sw, gap, line = 5.0, 8.0, 5.0, fm.height() + 3.0
        width = max(fm.horizontalAdvance(n) for n, _c in legend) + sw + gap
        box = QRectF(6.0, 6.0, width + pad * 2, line * len(legend) + pad * 2)
        chip = QColor(TOKENS["bg_surface"])
        chip.setAlpha(205)
        p.setPen(Qt.NoPen)
        p.setBrush(chip)
        p.drawRoundedRect(box, 3.0, 3.0)
        for i, (name, hexcol) in enumerate(legend):
            y = box.top() + pad + line * i
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(hexcol))
            p.drawRect(QRectF(box.left() + pad, y + line / 2 - sw / 2, sw, sw))
            p.setPen(QColor(TOKENS["text_primary"]))
            p.drawText(QRectF(box.left() + pad + sw + gap, y, width, line),
                       Qt.AlignLeft | Qt.AlignVCenter, name)
        p.setBrush(Qt.NoBrush)

    def _paint_marks(self, p: QPainter) -> None:
        """掃描線很淡、邊點是實心的小圓，代表那一條加粗。

        **點比線重要**：使用者要判斷的是「邊被判在哪」，線只是告訴他那個判斷
        是在哪一列上做的。所以線畫到幾乎看不見，點畫滿。
        """
        if self._pixmap is None or not self._marks:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        s_ = self._scale or 1.0
        ox, oy = self._offset.x(), self._offset.y()

        def at(pt) -> QPointF:
            return QPointF(ox + pt[0] * iw * s_, oy + pt[1] * ih * s_)

        index_of = {n: i for i, n in enumerate(self._overlay_order)}
        plain = QColor(TOKENS["accent"])

        def role_of(i: int) -> str:
            return (self._mark_labels[i] if i < len(self._mark_labels) else "")

        def colour_of(i: int) -> QColor:
            name = role_of(i)
            token = MARK_ROLE_TOKENS.get(name)
            if token:
                return QColor(TOKENS[token])
            return (QColor(region_hex(index_of[name])) if name in index_of
                    else plain)

        strong = self._marks_solid
        for i, (a, b) in enumerate(self._marks):
            focused = (i in self._mark_focus) or strong
            col = colour_of(i)
            if not focused:
                col = QColor(col)
                col.setAlpha(70)
            heavy = MARK_ROLE_WEIGHTS.get(role_of(i))
            pen = QPen(col, heavy if (heavy and focused)
                       else (2.2 if strong else (1.6 if focused else 1.0)))
            pen.setCosmetic(True)
            p.setPen(pen)
            p.drawLine(at(a), at(b))
        p.setPen(Qt.NoPen)
        for i, grp in enumerate(self._mark_points):
            focused = (i in self._mark_focus) or strong
            col = colour_of(i)
            if not focused:
                col = QColor(col)
                col.setAlpha(70)
            p.setBrush(QBrush(col))
            r = 2.6 if focused else 1.5
            for pt in grp:
                p.drawEllipse(at(pt), r, r)
        p.setBrush(Qt.NoBrush)

    def _paint_measure(self, p: QPainter) -> None:
        """量測尺按著時的那一條帶：兩條綠線 + 中間一層很淡的綠。

        畫在 ROI 框**之後**，因為它是「使用者手上正在做的事」—— 被框壓住的話
        就得先找它在哪。顏色跟框刻意不同色相（框是 accent，尺是綠）：兩者同時
        在畫面上，而「哪一條是我剛剛拉的」不能只靠深淺分辨。
        """
        if self._pixmap is None or self._measure is None:
            return
        axis, a, b = self._measure
        iw, ih = self._pixmap.width(), self._pixmap.height()
        s = self._scale or 1.0
        if axis == "x":
            band = QRectF(self._offset.x() + a * s, self._offset.y(),
                          max(1.0, (b - a) * s), ih * s)
        else:
            band = QRectF(self._offset.x(), self._offset.y() + a * s,
                          iw * s, max(1.0, (b - a) * s))
        green = QColor(TOKENS["success"])
        fill = QColor(green)
        fill.setAlpha(48)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawRect(band)
        pen = QPen(green, 1.6)
        pen.setCosmetic(True)          # 縮到很小時線不能跟著消失
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if axis == "x":
            for x in (band.left(), band.right()):
                p.drawLine(QPointF(x, band.top()), QPointF(x, band.bottom()))
        else:
            for y in (band.top(), band.bottom()):
                p.drawLine(QPointF(band.left(), y), QPointF(band.right(), y))

    def _paint_kernel(self, p: QPainter) -> None:
        """核心大小的方框：虛線 + 一個寫著幾像素的標籤。

        虛線是刻意的：ROI 框（實線 accent）與量測尺（實線綠）都是「資料上的東西」，
        這一個是**尺規**。三者可能同時在畫面上，而使用者要分得出哪一個是他剛剛
        拖出來的。
        """
        if self._pixmap is None or self._kernel is None:
            return
        n, label = self._kernel
        s = self._scale or 1.0
        iw, ih = self._pixmap.width(), self._pixmap.height()
        side = n * s
        cx = self._offset.x() + iw * s / 2.0
        cy = self._offset.y() + ih * s / 2.0
        box = QRectF(cx - side / 2.0, cy - side / 2.0, side, side)
        col = QColor(TOKENS["mark_kernel"])
        pen = QPen(col, 1.4, Qt.DashLine)
        pen.setCosmetic(True)          # 縮很小的時候線不能跟著消失
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(box)
        if not label:
            return
        # 標籤貼在框的上緣外側；框比畫布還大時（核心開到比影像大）就貼回畫布內，
        # 不然那個數字會被裁掉 —— 而「核心比整張圖還大」正是最需要看到它的時候。
        tw, th = 74.0, 14.0
        ty = box.top() - th - 2.0
        if ty < 2.0:
            ty = min(self.height() - th - 2.0, box.top() + 2.0)
        p.setPen(col)
        p.drawText(QRectF(box.center().x() - tw / 2.0, ty, tw, th),
                   Qt.AlignCenter, label)

    def _to_image(self, p: QPointF) -> QPointF:
        s = self._scale or 1.0
        return QPointF((p.x() - self._offset.x()) / s,
                       (p.y() - self._offset.y()) / s)

    # -- painting ----------------------------------------------------------
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
        # 中性灰底：不隨主題變，也不讓背景偏移對灰階的判斷（見 theme 的
        # image_backdrop 說明）
        p.setBrush(QColor(TOKENS["image_backdrop"]))
        p.drawRoundedRect(rect, 6, 6)
        if self._pixmap is None:
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(self.rect(), Qt.AlignCenter, self._EMPTY_TEXT)
            p.end()
            return
        # scale > 1 -> nearest neighbour（像素銳利）；縮小才用平滑取樣（防摩爾紋）
        p.setRenderHint(QPainter.SmoothPixmapTransform, self._scale <= 1.0)
        target = QRectF(self._offset.x(), self._offset.y(),
                        self._pixmap.width() * self._scale,
                        self._pixmap.height() * self._scale)
        p.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        # 順序就是意思：熱色在最底（它是「量出來多少」），框與標記畫在它上面
        # （它們是「量的是哪一塊」）—— 反過來的話框會被色塊蓋掉。
        self._paint_heat(p)
        self._paint_overlay(p)
        self._paint_marks(p)
        self._paint_measure(p)
        self._paint_kernel(p)
        p.end()

    # -- interaction -------------------------------------------------------
    def wheelEvent(self, e) -> None:
        if self._pixmap is None:
            return
        delta = e.angleDelta().y()
        if delta == 0:
            return
        self.zoom_by(1.15 if delta > 0 else 1 / 1.15, QPointF(e.position()))
        e.accept()

    def mousePressEvent(self, e) -> None:
        if self._pixmap is None:
            return
        if self._measure_mode and e.button() == Qt.LeftButton:
            self._measuring = self._to_image(QPointF(e.position()))
            self._auto_fit = False
            return
        if e.button() in (Qt.LeftButton, Qt.MiddleButton, Qt.RightButton):
            self._panning = True
            self._pan_start = QPointF(e.position())
            self._pan_offset = QPointF(self._offset)
            self._auto_fit = False
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:
        pos = QPointF(e.position())
        if self._measuring is not None:
            self._drag_measure(pos)
            return
        if self._panning:
            self._offset = self._pan_offset + (pos - self._pan_start)
            self.update()
            self.view_changed.emit(self._scale, QPointF(self._offset))
            return
        self._emit_cursor(pos)

    def mouseReleaseEvent(self, _e) -> None:
        if self._measuring is not None:
            self._measuring = None
            return
        if self._panning:
            self._panning = False
            self.unsetCursor()

    def _drag_measure(self, pos: QPointF) -> None:
        """拖曳中：沿**主要方向**那一軸標出來，並把讀數發出去。"""
        if self._measuring is None or self._image is None:
            return
        now = self._to_image(pos)
        dx = abs(now.x() - self._measuring.x())
        dy = abs(now.y() - self._measuring.y())
        h, w = self._image.shape[:2]
        if dx >= dy:
            a, b = self._measuring.x(), now.x()
            axis, hi = "x", float(w)
        else:
            a, b = self._measuring.y(), now.y()
            axis, hi = "y", float(h)
        a = min(max(float(a), 0.0), hi)
        b = min(max(float(b), 0.0), hi)
        self.set_measure(axis, a, b)
        self.measured.emit(axis, min(a, b), max(a, b))

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.fit()

    def leaveEvent(self, _e) -> None:
        self.cursor_info.emit("")

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self._auto_fit:
            self.fit()

    def _emit_cursor(self, pos: QPointF) -> None:
        if self._image is None:
            self.cursor_info.emit("")
            return
        ip = self._to_image(pos)
        x, y = int(math.floor(ip.x())), int(math.floor(ip.y()))
        h, w = self._image.shape[:2]
        if 0 <= x < w and 0 <= y < h:
            v = self._image[y, x]
            gray = int(v) if np.ndim(v) == 0 else int(np.mean(v))
            self.cursor_info.emit(f"x {x}  y {y}  ·  gray {gray}")
        else:
            self.cursor_info.emit("")

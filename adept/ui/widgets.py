# ADEPT Studio widget library — authored 2026-07-28 (M3).
# ImageView 的 zoom/pan 骨架 vendored from: PEAR/pear/ui/image_view.py（去掉 ROI 編輯）。
"""Studio 的六個可重用元件 —— 全部「資料驅動」，**不碰引擎**。

設計約束（很重要，別破壞）：

1. 這裡的元件只吃 dict / list / ndarray，只發 Signal。任何一個元件都不會
   import ``adept.core``、不會跑 pipeline、不會開檔案。組裝與呼叫引擎是
   main window / worker 的事。
2. 顏色一律走 ``theme.TOKENS`` / ``theme.seg_color``，不寫死 hex。
3. 每個參數的白話 ``help`` 一定要看得到（``ParamForm`` 的第二行提示）—— 推廣鐵則。

元件一覽：

- :class:`ImageView`        ndarray 檢視器（滾輪縮放、拖曳平移、雙擊 fit）
- :class:`ParamForm`        由 ``Step.describe()`` 自動生成的參數表單
- :class:`LibraryPanel`     三段式卡片庫（影像／算法／ADC）
- :class:`PipelinePanel`    有序節點清單 + Score/Bin 尾卡
- :class:`HistogramWidget`  分數分佈 + 可拖曳門檻線 + 可點擊長條（``bar_clicked``）
- :class:`FeatureTable` / :class:`VerdictChip`  特徵表與判定 chip
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QDialog,
    QDialogButtonBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .theme import TOKENS

__all__ = [
    "ImageView",
    "ParamForm",
    "LibraryPanel",
    "PipelinePanel",
    "HistogramWidget",
    "FeatureTable",
    "VerdictChip",
    "to_uint8",
]


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

    _MIN_SCALE = 0.02
    _MAX_SCALE = 60.0
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
        if e.button() in (Qt.LeftButton, Qt.MiddleButton, Qt.RightButton):
            self._panning = True
            self._pan_start = QPointF(e.position())
            self._pan_offset = QPointF(self._offset)
            self._auto_fit = False
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:
        pos = QPointF(e.position())
        if self._panning:
            self._offset = self._pan_offset + (pos - self._pan_start)
            self.update()
            self.view_changed.emit(self._scale, QPointF(self._offset))
            return
        self._emit_cursor(pos)

    def mouseReleaseEvent(self, _e) -> None:
        if self._panning:
            self._panning = False
            self.unsetCursor()

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


# --------------------------------------------------------------------------- #
# 2. ParamForm
# --------------------------------------------------------------------------- #
#: 浮點滑桿的內部刻度數。滑桿只吃 int，所以 min..max 一律映射到 0..這個數。
#: 1000 格對 gamma（0.1–5）約是 0.005 一格 —— 拖起來連續，又不會抖到看不出。
_SLIDER_TICKS = 1000

#: 整數參數的滑桿上限跨度。超過這個跨度就不給滑桿（一格好幾十，拖了也沒用），
#: 留純數字框比較誠實。
_SLIDER_MAX_INT_SPAN = 5000


class _ParamRow(QFrame):
    """一個參數 = 標題列（名稱 + 滑桿 + 數字框）+ 永遠看得見的白話說明第二行。

    為什麼有上下界的數字都配一支滑桿（F7-8）
    ----------------------------------------
    「gamma 要填多少」對不會寫 code 的人是個沒有答案的問題 —— 他要的是
    **一邊拖一邊看圖**。數字框逼人先想好一個數字再輸入，那個順序是反的。

    數字框沒有被拿掉，是刻意的：滑桿負責找到大概的位置，數字框負責記錄與
    重現（recipe 是要交接給別人的）。兩邊雙向綁定，改哪一邊另一邊都會跟上。
    """

    def __init__(self, spec: Dict[str, Any], editor: QWidget,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.spec = spec
        self.editor = editor
        self.slider: Optional[QSlider] = None
        self.setObjectName("paramRow")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 6)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        self.name_label = QLabel(str(spec.get("name", "")))
        self.name_label.setObjectName("paramLabel")
        self.name_label.setMinimumWidth(104)
        top.addWidget(self.name_label)

        self.slider = _make_slider(spec, editor)
        if self.slider is not None:
            top.addWidget(self.slider, 1)
            editor.setMaximumWidth(96)
            top.addWidget(editor, 0)
        else:
            top.addWidget(editor, 1)
        lay.addLayout(top)

        self.hint = QLabel(str(spec.get("help", "")))
        self.hint.setObjectName("paramHint")
        self.hint.setWordWrap(True)
        self.hint.setProperty("error", "false")
        lay.addWidget(self.hint)

    def set_error(self, msg: Optional[str]) -> None:
        if msg:
            self.hint.setText("⚠ " + str(msg))
            self.hint.setProperty("error", "true")
            self.hint.setStyleSheet(
                "color:%s; font-size:11px; font-weight:600;" % TOKENS["danger_text"])
        else:
            self.hint.setText(str(self.spec.get("help", "")))
            self.hint.setProperty("error", "false")
            self.hint.setStyleSheet("color:%s; font-size:11px;" % TOKENS["text_hint"])
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)

    def has_error(self) -> bool:
        return self.hint.property("error") == "true"

    def set_dimmed(self, dimmed: bool, why: str = "") -> None:
        """把整列調淡（值還在、還能改，只是現在不生效）。

        用在「另一個參數接管了這一個」的情況 —— 例如畫了曲線之後 gamma
        就不再被用到。不 disable 是刻意的：使用者可能只是想比較兩種做法，
        把它鎖死會逼他先把曲線拉平才改得動 gamma。
        """
        self.setProperty("dimmed", "true" if dimmed else "false")
        self.setEnabled(True)
        self.name_label.setStyleSheet(
            "color:%s;" % (TOKENS["text_disabled"] if dimmed
                           else TOKENS["text_primary"]))
        if dimmed and why:
            self.hint.setText("· " + why)
            self.hint.setStyleSheet("color:%s; font-size:11px; font-style:italic;"
                                    % TOKENS["text_disabled"])
        elif not self.has_error():
            self.hint.setText(str(self.spec.get("help", "")))
            self.hint.setStyleSheet("color:%s; font-size:11px;" % TOKENS["text_hint"])


def _make_slider(spec: Dict[str, Any], editor: QWidget) -> Optional[QSlider]:
    """有上下界的 int / float 參數 → 一支跟數字框雙向綁定的滑桿。

    回 ``None`` 表示這個參數不適合滑桿（沒界、跨度是 0、或整數跨度大到
    一格好幾十）。這樣新卡片只要把 min/max 填好就自動有滑桿，
    不必逐張卡去 UI 這邊登記。
    """
    ptype = str(spec.get("type", ""))
    lo, hi = spec.get("min"), spec.get("max")
    if ptype not in ("int", "float") or lo is None or hi is None:
        return None
    lo, hi = float(lo), float(hi)
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return None

    s = QSlider(Qt.Horizontal)
    s.setObjectName("paramSlider")
    s.setToolTip(str(spec.get("help", "")))
    guard = {"busy": False}

    if ptype == "int":
        if hi - lo > _SLIDER_MAX_INT_SPAN:
            return None
        s.setRange(int(lo), int(hi))
        s.setValue(int(editor.value()))

        def from_slider(v: int) -> None:
            if guard["busy"]:
                return
            guard["busy"] = True
            editor.setValue(int(v))
            guard["busy"] = False

        def from_box(v: int) -> None:
            if guard["busy"]:
                return
            guard["busy"] = True
            s.setValue(int(v))
            guard["busy"] = False
    else:
        s.setRange(0, _SLIDER_TICKS)
        span = hi - lo

        def to_tick(v: float) -> int:
            return int(round((float(v) - lo) / span * _SLIDER_TICKS))

        s.setValue(to_tick(editor.value()))

        def from_slider(v: int) -> None:      # noqa: F811 — 兩型別各一份
            if guard["busy"]:
                return
            guard["busy"] = True
            editor.setValue(lo + (float(v) / _SLIDER_TICKS) * span)
            guard["busy"] = False

        def from_box(v: float) -> None:       # noqa: F811
            if guard["busy"]:
                return
            guard["busy"] = True
            s.setValue(to_tick(v))
            guard["busy"] = False

    # 兩邊互相回寫會無限來回（float 還會因為取整而每次都差一點點），
    # 所以用 guard 擋住「因我而起的那一次回呼」。
    s.valueChanged.connect(from_slider)
    editor.valueChanged.connect(from_box)
    return s


class ParamForm(QWidget):
    """由 ``Step.describe()`` 的 ParamSpec dict 自動長出來的參數表單。

    ``set_step(describe, current_params, stream_choices)`` 一次重建整張表；
    使用者改動任何欄位 -> ``param_edited(name, value)``（值已 coerce 成該型別）。
    上層驗證失敗時呼叫 ``show_error(name, msg)`` 把那一列的說明變紅字。
    """

    param_edited = Signal(str, object)

    _EMPTY_TEXT = "(Pick a card from the library, or select a step in the pipeline)"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._rows: Dict[str, _ParamRow] = {}
        self._describe: Optional[Dict[str, Any]] = None
        self._building = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._title = QLabel("")
        self._title.setObjectName("paramTitle")
        self._step_help = QLabel("")
        self._step_help.setObjectName("paramStepHelp")
        self._step_help.setWordWrap(True)
        outer.addWidget(self._title)
        outer.addWidget(self._step_help)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._form = QVBoxLayout(self._host)
        self._form.setContentsMargins(2, 2, 8, 2)
        self._form.setSpacing(2)
        self._placeholder = QLabel(self._EMPTY_TEXT)
        self._placeholder.setObjectName("placeholder")
        self._placeholder.setWordWrap(True)
        self._form.addWidget(self._placeholder)
        self._form.addStretch(1)
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)

        self.set_step(None, {}, [])

    # -- public API --------------------------------------------------------
    def set_step(self, describe: Optional[Dict[str, Any]],
                 current_params: Optional[Dict[str, Any]] = None,
                 stream_choices: Optional[Sequence[str]] = None) -> None:
        """重建表單。``describe=None`` -> 顯示提示語（未選節點）。"""
        current_params = dict(current_params or {})
        streams = [str(s) for s in (stream_choices or [])]
        self._describe = describe
        self._building = True
        try:
            self._clear_rows()
            if not describe:
                self._title.setText("")
                self._title.setVisible(False)
                self._step_help.setText("")
                self._step_help.setVisible(False)
                self._placeholder.setVisible(True)
                return
            self._title.setText(str(describe.get("label")
                                    or describe.get("key") or ""))
            self._title.setVisible(True)
            self._step_help.setText(str(describe.get("help", "")))
            self._step_help.setVisible(bool(describe.get("help")))
            self._placeholder.setVisible(False)
            for spec in describe.get("params", []):
                name = str(spec.get("name", ""))
                value = current_params.get(name, spec.get("default"))
                editor = self._make_editor(spec, value, streams)
                editor.setToolTip(str(spec.get("help", "")))
                row = _ParamRow(spec, editor, self._host)
                self._form.insertWidget(self._form.count() - 1, row)
                self._rows[name] = row
        finally:
            self._building = False
        self._sync_curve_override()

    def _sync_curve_override(self) -> None:
        """曲線一旦不是 y=x，就把 ``gamma`` 那列調淡並說明原因。

        規則本身寫在 ``steps/tone.py``（曲線接管 gamma）。這裡只是**讓它看得
        見** —— 不然使用者會拉了曲線又去動 gamma，然後發現 gamma 沒有反應。
        """
        curve_row = None
        for name, row in self._rows.items():
            if str(row.spec.get("type", "")) == "curve":
                curve_row = row
                break
        if curve_row is None:
            return
        active = not curve_row.editor.is_identity()
        gamma = self._rows.get("gamma")
        if gamma is not None and not gamma.has_error():
            gamma.set_dimmed(active, "Not used while a custom curve is drawn.")

    def step_key(self) -> Optional[str]:
        return None if not self._describe else str(self._describe.get("key"))

    def param_names(self) -> List[str]:
        return list(self._rows)

    def editor(self, name: str) -> Optional[QWidget]:
        row = self._rows.get(name)
        return None if row is None else row.editor

    def slider(self, name: str) -> Optional[QSlider]:
        """那一列的滑桿（沒有上下界的參數沒有滑桿，回 ``None``）。"""
        row = self._rows.get(name)
        return None if row is None else row.slider

    def hint_text(self, name: str) -> str:
        row = self._rows.get(name)
        return "" if row is None else row.hint.text()

    def show_error(self, name: str, msg: str) -> None:
        """把 ``name`` 那一列的說明換成紅色錯誤訊息。"""
        row = self._rows.get(name)
        if row is not None:
            row.set_error(msg)

    def clear_errors(self) -> None:
        """所有列還原成白話說明（灰字）。"""
        for row in self._rows.values():
            if row.has_error():
                row.set_error(None)

    def has_error(self, name: str) -> bool:
        row = self._rows.get(name)
        return bool(row is not None and row.has_error())

    # -- internals ---------------------------------------------------------
    def _clear_rows(self) -> None:
        for row in self._rows.values():
            self._form.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = {}

    def _emit(self, name: str, value: Any) -> None:
        if self._building:
            return
        self.param_edited.emit(name, value)

    def _make_editor(self, spec: Dict[str, Any], value: Any,
                     streams: Sequence[str]) -> QWidget:
        name = str(spec.get("name", ""))
        ptype = str(spec.get("type", "str"))
        unit = str(spec.get("unit", "") or "")
        lo, hi = spec.get("min"), spec.get("max")

        if ptype == "int":
            w = QSpinBox()
            w.setRange(int(lo) if lo is not None else -10 ** 9,
                       int(hi) if hi is not None else 10 ** 9)
            if unit:
                w.setSuffix(" " + unit)
            w.setValue(_safe_int(value))
            w.valueChanged.connect(lambda v, n=name: self._emit(n, int(v)))
            return w

        if ptype == "float":
            w = QDoubleSpinBox()
            w.setDecimals(3)
            w.setRange(float(lo) if lo is not None else -1e9,
                       float(hi) if hi is not None else 1e9)
            span = None if (lo is None or hi is None) else float(hi) - float(lo)
            w.setSingleStep(0.01 if (span is not None and span <= 2.0) else 0.1)
            if unit:
                w.setSuffix(" " + unit)
            w.setValue(_safe_float(value))
            w.valueChanged.connect(lambda v, n=name: self._emit(n, float(v)))
            return w

        if ptype == "bool":
            w = QCheckBox("Enabled")
            w.setChecked(bool(value))
            w.toggled.connect(lambda v, n=name: self._emit(n, bool(v)))
            return w

        if ptype == "choice":
            w = QComboBox()
            choices = [str(c) for c in (spec.get("choices") or [])]
            w.addItems(choices)
            text = str(value)
            if text in choices:
                w.setCurrentIndex(choices.index(text))
            w.currentTextChanged.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "curve":
            w = CurveField()
            w.set_text("" if value is None else str(value))
            w.curve_changed.connect(lambda t, n=name: self._emit(n, str(t)))
            w.curve_changed.connect(lambda _t: self._sync_curve_override())
            return w

        if ptype == "image_key":
            w = QComboBox()
            w.setEditable(True)          # 可挑上游影像流，也可自己打新流名
            items = list(dict.fromkeys([str(s) for s in streams]))
            text = str(value)
            if text and text not in items:
                items.append(text)
            w.addItems(items)
            w.setCurrentText(text)
            w.currentTextChanged.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        w = QLineEdit()
        w.setText("" if value is None else str(value))
        w.textChanged.connect(lambda t, n=name: self._emit(n, str(t)))
        return w


# --------------------------------------------------------------------------- #
# 2b. CurveEditor —— 自己拉的色調曲線（F7-8）
# --------------------------------------------------------------------------- #
class CurveEditor(QWidget):
    """可拖曳的色調曲線編輯器。橫軸 = 輸入灰階，縱軸 = 輸出灰階，兩軸都 0–1。

    操作（右下角就寫著，不用先看說明）
    ----------------------------------
    * 拖控制點 = 改曲線；
    * 在空白處按左鍵 = 加一個控制點；
    * 對控制點右鍵（或雙擊）= 刪掉它。頭尾兩點刪不掉，
      因為曲線必須覆蓋整個灰階範圍。

    **畫出來的線就是影像上套的線** —— 這裡呼叫的是 core 的
    ``algo.curve.curve_lut``，跟 ``gamma`` 卡執行時用的是同一個函式。
    UI 自己再實作一份插值是很容易發生的事，那會讓使用者看到的和跑出來的不一樣。
    這是本檔唯一一處 import ``adept.core``，理由就是這個 —— 而且它是純運算、
    不碰引擎，沒有違反「元件不跑 pipeline」的約束。
    """

    curve_changed = Signal(str)

    _PAD = 10.0                 # 邊界留白（點拖到角落時還抓得到）
    _HIT = 9.0                  # 控制點的點擊半徑（螢幕像素）
    _DOT = 4.0

    def __init__(self, parent: Optional[QWidget] = None, compact: bool = True):
        super().__init__(parent)
        from ..core.pipeline.curve import IDENTITY, parse_curve

        self._parse = parse_curve
        self._points: List[Tuple[float, float]] = list(parse_curve(IDENTITY))
        self._drag: Optional[int] = None
        self._compact = bool(compact)
        self.setMinimumSize(QSize(150, 130 if compact else 300))
        if not compact:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setToolTip("Drag to bend · click to add a point · "
                        "right-click a point to remove it")

    # -- public API --------------------------------------------------------
    def text(self) -> str:
        from ..core.pipeline.curve import format_curve
        return format_curve(self._points)

    def points(self) -> List[Tuple[float, float]]:
        return list(self._points)

    def set_text(self, text: str, emit: bool = False) -> bool:
        """從控制點字串載入。字串壞掉時**保持原樣並回 False**。

        參數表單是「打字即生效」的，使用者打到一半必然出現不合法的中間狀態；
        那時候把曲線清成 y=x 會讓他辛苦拉的線消失。
        """
        try:
            pts = self._parse(text)
        except ValueError:
            return False
        self._points = list(pts)
        self.update()
        if emit:
            self.curve_changed.emit(self.text())
        return True

    def reset(self) -> None:
        from ..core.pipeline.curve import IDENTITY
        self.set_text(IDENTITY, emit=True)

    def is_identity(self) -> bool:
        from ..core.pipeline.curve import is_identity
        return is_identity(self._points)

    # -- 座標轉換 ----------------------------------------------------------
    def _plot_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(self._PAD, self._PAD,
                                            -self._PAD, -self._PAD)

    def _to_px(self, x: float, y: float) -> QPointF:
        r = self._plot_rect()
        return QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())

    def _to_unit(self, p: QPointF) -> Tuple[float, float]:
        r = self._plot_rect()
        w = max(1.0, r.width())
        h = max(1.0, r.height())
        return (float(np.clip((p.x() - r.left()) / w, 0.0, 1.0)),
                float(np.clip((r.bottom() - p.y()) / h, 0.0, 1.0)))

    def _hit(self, p: QPointF) -> Optional[int]:
        for i, (x, y) in enumerate(self._points):
            if (self._to_px(x, y) - p).manhattanLength() <= self._HIT * 1.6:
                return i
        return None

    # -- painting ----------------------------------------------------------
    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        from ..core.algo.curve import curve_lut

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
        p.setBrush(QColor(TOKENS["image_backdrop"]))
        p.drawRoundedRect(r, 5, 5)

        plot = self._plot_rect()
        grid = QColor(TOKENS["border_default"])
        grid.setAlpha(120)
        p.setPen(QPen(grid, 1))
        for i in range(1, 4):
            f = i / 4.0
            p.drawLine(self._to_px(f, 0.0), self._to_px(f, 1.0))
            p.drawLine(self._to_px(0.0, f), self._to_px(1.0, f))

        # y = x 參考線（虛線）—— 使用者隨時看得出自己偏離了多少
        ref = QPen(QColor(TOKENS["text_disabled"]), 1, Qt.DashLine)
        p.setPen(ref)
        p.drawLine(self._to_px(0.0, 0.0), self._to_px(1.0, 1.0))

        accent = QColor(theme.seg_hex("image"))
        n = max(24, int(plot.width()))
        lut = curve_lut(self._points, n)
        p.setPen(QPen(accent, 2.0))
        prev = self._to_px(0.0, float(lut[0]))
        for i in range(1, n):
            cur = self._to_px(i / (n - 1.0), float(lut[i]))
            p.drawLine(prev, cur)
            prev = cur

        p.setPen(QPen(QColor(TOKENS["surface_raised"]), 1.5))
        p.setBrush(accent)
        for x, y in self._points:
            c = self._to_px(x, y)
            p.drawEllipse(c, self._DOT, self._DOT)
        p.end()

    # -- interaction -------------------------------------------------------
    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        pos = QPointF(e.position())
        idx = self._hit(pos)
        if e.button() == Qt.RightButton:
            if idx is not None:
                self._remove(idx)
            return
        if e.button() != Qt.LeftButton:
            return
        if idx is None:
            idx = self._insert(*self._to_unit(pos))
            if idx is None:
                return
        self._drag = idx
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:       # noqa: D102 - Qt hook
        if self._drag is None:
            return
        x, y = self._to_unit(QPointF(e.position()))
        i = self._drag
        if i == 0:
            x = 0.0                       # 頭尾的 x 鎖住：曲線必須從 0 到 1
        elif i == len(self._points) - 1:
            x = 1.0
        else:
            # 不准越過鄰居 —— 越過去就不是函數了（同一個輸入兩個輸出）
            x = float(np.clip(x, self._points[i - 1][0] + 0.01,
                              self._points[i + 1][0] - 0.01))
        self._points[i] = (x, y)
        self.update()
        self.curve_changed.emit(self.text())

    def mouseReleaseEvent(self, _e) -> None:   # noqa: D102 - Qt hook
        if self._drag is not None:
            self._drag = None
            self.setCursor(Qt.CrossCursor)

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: D102 - Qt hook
        idx = self._hit(QPointF(e.position()))
        if idx is not None:
            self._remove(idx)

    def _insert(self, x: float, y: float) -> Optional[int]:
        """在 x 的位置插一個控制點；太靠近既有點就不插（會變成不合法的曲線）。"""
        if any(abs(px - x) < 0.02 for px, _py in self._points):
            return None
        self._points.append((x, y))
        self._points.sort(key=lambda pt: pt[0])
        self.update()
        self.curve_changed.emit(self.text())
        return self._points.index((x, y))

    def _remove(self, idx: int) -> None:
        if idx <= 0 or idx >= len(self._points) - 1:
            return                       # 頭尾刪不掉
        del self._points[idx]
        self.update()
        self.curve_changed.emit(self.text())


class CurveField(QWidget):
    """參數表單裡的曲線欄位：小張的編輯器 + ``Reset`` / ``Enlarge…``。

    小張的可以直接拉（常見的微調不用開視窗），要做細活再按 ``Enlarge…``
    開一張大的。兩邊改的是同一組控制點。
    """

    curve_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        self.editor = CurveEditor(self)
        self.editor.curve_changed.connect(self._on_changed)
        lay.addWidget(self.editor)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(5)
        self.reset_button = QPushButton("Reset to y = x", self)
        self.reset_button.setToolTip("Put the curve back to a straight line "
                                     "(the gamma slider takes over again)")
        self.reset_button.clicked.connect(self.editor.reset)
        self.enlarge_button = QPushButton("Enlarge…", self)
        self.enlarge_button.setToolTip("Open a big curve canvas")
        self.enlarge_button.clicked.connect(self.open_dialog)
        bar.addWidget(self.reset_button)
        bar.addWidget(self.enlarge_button)
        bar.addStretch(1)
        lay.addLayout(bar)

    def text(self) -> str:
        return self.editor.text()

    def set_text(self, text: str, emit: bool = False) -> bool:
        return self.editor.set_text(text, emit=emit)

    def is_identity(self) -> bool:
        return self.editor.is_identity()

    def open_dialog(self) -> "CurveDialog":
        dlg = CurveDialog(self.editor.text(), self)
        dlg.curve_changed.connect(self._adopt)
        dlg.show()
        self._dialog = dlg          # 保住參照，不然 show() 之後會被 GC
        return dlg

    def _adopt(self, text: str) -> None:
        if self.editor.set_text(text):
            self.curve_changed.emit(self.editor.text())

    def _on_changed(self, text: str) -> None:
        self.curve_changed.emit(text)


class CurveDialog(QDialog):
    """放大版的曲線畫布。非模態 —— 一邊拉曲線一邊看主視窗的預覽更新。"""

    curve_changed = Signal(str)

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Tone curve")
        self.setModal(False)
        self.resize(420, 460)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        head = QLabel("Input gray level across, output up. Drag a point to "
                      "bend the curve; click an empty spot to add one; "
                      "right-click a point to remove it.", self)
        head.setWordWrap(True)
        head.setObjectName("paramHint")
        lay.addWidget(head)

        self.editor = CurveEditor(self, compact=False)
        self.editor.set_text(text)
        self.editor.curve_changed.connect(self.curve_changed)
        lay.addWidget(self.editor, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        reset = QPushButton("Reset to y = x", self)
        reset.clicked.connect(self.editor.reset)
        buttons.addButton(reset, QDialogButtonBox.ResetRole)
        buttons.rejected.connect(self.close)
        lay.addWidget(buttons)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return default if (math.isnan(f) or math.isinf(f)) else f


# --------------------------------------------------------------------------- #
# 3. LibraryPanel
# --------------------------------------------------------------------------- #
def draw_group_icon(p: QPainter, group: str, color: str, size: float) -> None:
    """在 ``p`` 的目前原點畫一個 ``size`` × ``size`` 的階段圖示。

    **抽成自由函式**，是為了讓左側 rail 的按鈕、卡片庫的區塊標題、以及畫布上的
    節點卡三處共用完全相同的圖形 —— 使用者在 rail 上看到的尺，在節點上看到的
    也要是同一把尺，不然「圖示」就只是裝飾而不是語言。

    不吃任何圖檔：repo 有「只放純文字檔」的不變量（公司機 DLP 會擋含二進位的
    壓縮檔，見 ``docs/HANDOVER.md`` §5）。``.svg`` 其實是純文字、過得了 DLP，
    但用 QPainter 連「要不要把圖檔加進版控」這個問題都不用問，而且顏色直接吃
    token —— 換主題時圖示自動跟著變。
    """
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), max(1.2, size / 11.0))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    w = h = float(size)
    m = w / 7.5                       # 邊界留白，隨尺寸縮放
    g = str(group)

    if g == "input":                    # 匣子 + 往下的箭頭
        p.drawRect(QRectF(m, h * 0.55, w - 2 * m, h * 0.45 - m))
        p.drawLine(QPointF(w / 2, m), QPointF(w / 2, h * 0.46))
        p.drawLine(QPointF(w / 2 - w * 0.16, h * 0.30), QPointF(w / 2, h * 0.46))
        p.drawLine(QPointF(w / 2 + w * 0.16, h * 0.30), QPointF(w / 2, h * 0.46))
    elif g == "enhance":                # 亮度：半實心圓
        p.drawEllipse(QRectF(m, m, w - 2 * m, h - 2 * m))
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawPie(QRectF(m, m, w - 2 * m, h - 2 * m), -90 * 16, 180 * 16)
    elif g == "region":                 # 取景框（四個角）+ 中心點
        c = w * 0.24
        for x0, y0, dx, dy in ((m, m, 1, 1), (w - m, m, -1, 1),
                               (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            p.drawLine(QPointF(x0, y0), QPointF(x0 + c * dx, y0))
            p.drawLine(QPointF(x0, y0), QPointF(x0, y0 + c * dy))
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        r = w * 0.11
        p.drawEllipse(QRectF(w / 2 - r, h / 2 - r, 2 * r, 2 * r))
    elif g == "compare":                # 兩個交疊的方框
        side = w - 2 * m - w * 0.2
        p.drawRect(QRectF(m, m, side, side))
        p.drawRect(QRectF(m + w * 0.2, m + w * 0.2, side, side))
    elif g == "measure":                # 尺（一條線 + 刻度）
        base = h - m
        p.drawLine(QPointF(m, base), QPointF(w - m, base))
        for i in range(4):
            x = m + i * (w - 2 * m) / 3.0
            p.drawLine(QPointF(x, base),
                       QPointF(x, base - (h * 0.40 if i % 2 == 0 else h * 0.23)))
    elif g == "search":                 # 放大鏡（rail 上的搜尋鈕，不是流程階段）
        r = w * 0.29
        p.drawEllipse(QRectF(m, m, 2 * r, 2 * r))
        p.drawLine(QPointF(m + 2 * r * 0.86, m + 2 * r * 0.86),
                   QPointF(w - m, h - m))
    else:                               # adc / 其他：打勾
        p.drawLine(QPointF(m, h * 0.52), QPointF(w * 0.42, h - m))
        p.drawLine(QPointF(w * 0.42, h - m), QPointF(w - m, m))


class GroupIcon(QWidget):
    """:func:`draw_group_icon` 的 widget 包裝（給 rail 與區塊標題用）。"""

    _SIZE = 15

    def __init__(self, group: str, color: str, parent: Optional[QWidget] = None,
                 size: Optional[int] = None):
        super().__init__(parent)
        self.group = str(group)
        self.color = str(color)
        self._SIZE = int(size or self._SIZE)
        self.setFixedSize(self._SIZE, self._SIZE)

    def set_color(self, color: str) -> None:
        self.color = str(color)
        self.update()

    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        p = QPainter(self)
        draw_group_icon(p, self.group, self.color, float(self._SIZE))
        p.end()


class _LibraryItem(QFrame):
    """卡片庫的一列：名稱 + hover 才出現的「Add」；雙擊也能加入。

    ``set_missing(streams)`` 會把「上游還沒產出它要的影像流」這件事顯示成
    一個灰字 badge（例：``needs diff``）並把整列調淡 —— 但**仍然可以加**。
    卡片庫的順序不等於執行順序，使用者可能先放卡再補上游；擋著不給加只會
    讓人以為工具壞了。
    """

    activated = Signal(str)

    def __init__(self, describe: Dict[str, Any], color: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.step_key = str(describe.get("key", ""))
        self.reads = [str(r) for r in (describe.get("reads") or ())]
        self.setObjectName("libItem")
        self.setCursor(Qt.PointingHandCursor)
        self._base_tip = (str(describe.get("help", ""))
                          or str(describe.get("label", "")))
        if describe.get("requires_ref"):
            self._base_tip += " (needs a ref image)"
        self.setToolTip(self._base_tip)
        self.setStyleSheet(
            "QFrame#libItem { background:transparent; border:1px solid transparent;"
            " border-radius:5px; }"
            "QFrame#libItem:hover { background:%s; border-color:%s; }"
            % (TOKENS["hover_warm"], TOKENS["border_default"])
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 3, 6, 3)
        lay.setSpacing(6)

        self.dot = QFrame()
        self.dot.setFixedSize(5, 5)
        self.dot.setStyleSheet("background:%s; border-radius:2px;" % color)
        lay.addWidget(self.dot)

        self.label = QLabel(str(describe.get("label") or self.step_key))
        self.label.setToolTip(self._base_tip)
        lay.addWidget(self.label, 1)

        self.badge = QLabel("")
        self.badge.setObjectName("libBadge")
        self.badge.setStyleSheet(
            "color:%s; font-size:10px; border:1px solid %s; border-radius:3px;"
            " padding:0px 4px;" % (TOKENS["text_disabled"], TOKENS["border_default"]))
        self.badge.setVisible(False)
        self.missing: List[str] = []
        lay.addWidget(self.badge)

        self.add_button = QPushButton("Add")
        self.add_button.setObjectName("cardButton")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.setToolTip("Append this card to the end of the pipeline")
        self.add_button.setFixedWidth(40)
        self.add_button.clicked.connect(
            lambda: self.activated.emit(self.step_key))
        self.add_button.setVisible(False)
        lay.addWidget(self.add_button)

    # -- 前置條件 badge -----------------------------------------------------
    def set_missing(self, missing: Sequence[str]) -> None:
        """``missing`` = 這張卡要讀、但上游還沒有的影像流。"""
        missing = [str(m) for m in (missing or ())]
        self.missing = list(missing)
        if missing:
            self.badge.setText("needs %s" % ", ".join(missing))
            self.badge.setVisible(True)
            self.label.setStyleSheet("color:%s;" % TOKENS["text_disabled"])
            self.setToolTip(
                "%s\n\nNot available yet: this card reads %s, which nothing "
                "upstream produces so far. You can still add it — the pipeline "
                "order is up to you."
                % (self._base_tip, ", ".join(missing)))
        else:
            self.badge.setVisible(False)
            self.label.setStyleSheet("")
            self.setToolTip(self._base_tip)

    def badge_text(self) -> str:
        """目前的 badge 文字（沒有就空字串）。

        看的是 :attr:`missing` 而不是 ``badge.isVisible()`` —— 視窗還沒 show()
        之前 Qt 的可見性一律是 False，headless 測試會全部誤判。
        """
        return self.badge.text() if self.missing else ""

    def enterEvent(self, e) -> None:      # noqa: D102 - Qt hook
        self.add_button.setVisible(True)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:      # noqa: D102 - Qt hook
        self.add_button.setVisible(False)
        super().leaveEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:   # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self.activated.emit(self.step_key)


class StageButton(QFrame):
    """左側 rail 的一顆大按鈕：icon + 階段名 + 卡片數。

    這是 F7-7 的要求：**先用大 icon 分功能，按下去才帶出裡面的小功能。**
    六個階段一次全展開，等於一開始就把 15 張卡攤在使用者面前 ——
    那正是「太瑣碎」的來源。
    """

    clicked = Signal(str)

    _ICON = 30

    def __init__(self, group: str, title: str, subtitle: str, colour: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.group = str(group)
        self.setObjectName("stageButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("%s — %s" % (title, subtitle))
        self._colour = colour
        self._active = False

        self.setFixedWidth(58)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 7, 2, 5)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignHCenter)

        self.icon = GroupIcon(self.group, colour, self, size=self._ICON)
        lay.addWidget(self.icon, 0, Qt.AlignHCenter)

        self.label = QLabel(title, self)
        self.label.setAlignment(Qt.AlignHCenter)
        self.label.setStyleSheet("font-size:9px; font-weight:600;")
        lay.addWidget(self.label)

        self.count = QLabel("", self)
        self.count.setAlignment(Qt.AlignHCenter)
        self.count.setStyleSheet("font-size:9px; color:%s;" % TOKENS["text_disabled"])
        lay.addWidget(self.count)
        self._restyle()

    def set_count(self, n: int) -> None:
        self.count.setText("" if n <= 0 else str(int(n)))

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self._restyle()

    def is_active(self) -> bool:
        return self._active

    def refresh_colour(self, colour: str) -> None:
        self._colour = colour
        self.icon.set_color(colour)
        self._restyle()

    def _restyle(self) -> None:
        self.setStyleSheet(
            "QFrame#stageButton { background:%s; border:1px solid %s;"
            " border-radius:6px; }"
            "QFrame#stageButton:hover { background:%s; }"
            % (TOKENS["accent_bg"] if self._active else "transparent",
               TOKENS["accent_border"] if self._active else "transparent",
               TOKENS["hover_warm"]))

    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.group)
        super().mousePressEvent(e)


class LibraryPanel(QWidget):
    """卡片庫：依**流程階段**分組（F7-3），每組一個 QPainter 畫的 icon + 標題。

    為什麼不再依 ``category`` 分
    ----------------------------
    ``category``（影像／算法）描述的是「這張卡吐什麼型別」——那是引擎的分類
    （快取切點、驗證順序）。使用者要的是「我想幹嘛」，所以改用 ``group``：

        Input → Enhance → Region → Compare → Measure → ADC

    讀起來是一句話，而且每段有一條機械可判定的規則（見 ``pipeline/step.py``）。

    另外兩件讓 17 列不再瑣碎的事：

    * **搜尋框** —— 打字即時過濾（比對名稱、key 與說明）。
    * **前置條件 badge** —— ``set_available_streams()`` 之後，
      上游還沒產出所需影像流的卡會標成 ``needs diff`` 並調淡。
    """

    add_requested = Signal(str)
    #: 卡片區展開/收起（``True`` = 展開）。主視窗據此縮放左欄寬度 ——
    #: 收起來時整欄只留 rail，工作區才真的變寬。
    panel_toggled = Signal(bool)

    #: 顯示順序與標題。id 對應 ``pipeline/step.py`` 的 ``GROUP_*``。
    GROUPS = (
        ("input", "Input", "Load this defect's images"),
        ("enhance", "Enhance", "Image in, image out"),
        ("region", "Region", "Decide where to look"),
        ("compare", "Compare", "Two images in, difference out"),
        ("measure", "Measure", "Image + region in, numbers out"),
        ("adc", "ADC", "Numbers in, score and bin out"),
    )
    _ORDER = tuple(g for g, _t, _s in GROUPS)
    _EMPTY_TEXT = "(no cards in this section)"
    _NO_MATCH_TEXT = "(no card matches)"

    #: group -> 取哪個 segment 的顏色（三段式的色彩語言不變，只是變細了）。
    _GROUP_SEG = {"input": "image", "enhance": "image", "region": "algo",
                  "compare": "image", "measure": "algo", "adc": "adc"}

    #: 直式 icon rail 的寬度（收起來時整個 panel 就縮到只剩這條）。
    RAIL_W = 66
    #: 展開時卡片區至少要多寬（卡名 + badge 放得下）。
    PANEL_W = 190

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._items: Dict[str, _LibraryItem] = {}
        self._describes: Dict[str, Dict[str, Any]] = {}
        self._section_boxes: Dict[str, QVBoxLayout] = {}
        self._headers: Dict[str, QWidget] = {}
        self._icons: Dict[str, GroupIcon] = {}
        self._available: List[str] = []
        self._query = ""
        self._shown_groups: List[str] = []

        self._open_group: Optional[str] = None

        # 版面：**直式 rail（左）｜ 卡片區（右）**。
        # F7-8：像工作列一樣由上而下，點了 icon 才顯示裡面的卡 ——
        # 這樣左邊的操作區平常是乾淨的。
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.rail = QWidget(self)
        self.rail.setObjectName("stageRail")
        self.rail.setFixedWidth(self.RAIL_W)
        rail_lay = QVBoxLayout(self.rail)
        rail_lay.setContentsMargins(2, 6, 2, 6)
        rail_lay.setSpacing(2)
        self.stage_buttons: Dict[str, StageButton] = {}
        for gid, title, subtitle in self.GROUPS:
            btn = StageButton(gid, title, subtitle,
                              theme.seg_hex(self._GROUP_SEG.get(gid, "image")),
                              self.rail)
            btn.clicked.connect(self.toggle_group)
            rail_lay.addWidget(btn)
            self.stage_buttons[gid] = btn
        rail_lay.addStretch(1)

        # 搜尋鈕留在 rail 上（不是在 panel 裡）—— panel 收起來時搜尋框跟著藏，
        # 沒有這顆就再也打不開搜尋了。
        self.search_button = StageButton(
            "search", "Search", "Find a card by name or description",
            TOKENS["text_secondary"], self.rail)
        self.search_button.clicked.connect(lambda _g: self.focus_search())
        rail_lay.addWidget(self.search_button)
        outer.addWidget(self.rail)

        # 右邊：搜尋 + 卡片清單（收起來時整塊隱藏）
        self.panel = QWidget(self)
        panel_lay = QVBoxLayout(self.panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(0)

        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search cards…")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip("Filter the card library by name or description")
        self.search.textChanged.connect(self._on_search)
        wrap = QWidget(self.panel)
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(6, 6, 8, 4)
        wl.addWidget(self.search)
        panel_lay.addWidget(wrap)

        self._scroll = QScrollArea(self.panel)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._body = QVBoxLayout(self._host)
        self._body.setContentsMargins(6, 2, 8, 6)
        self._body.setSpacing(2)

        for gid, title, subtitle in self.GROUPS:
            self._body.addWidget(self._make_header(gid, title, subtitle))
            box = QVBoxLayout()
            box.setContentsMargins(0, 0, 0, 8)
            box.setSpacing(1)
            self._body.addLayout(box)
            self._section_boxes[gid] = box

        self._body.addStretch(1)
        self._scroll.setWidget(self._host)
        panel_lay.addWidget(self._scroll, 1)
        outer.addWidget(self.panel, 1)

        self.set_steps([])
        self.toggle_group(self._ORDER[0])       # 開窗先展開 Input

    # -- 區塊標題（icon + 標題，取代舊的填滿色塊）---------------------------
    def _make_header(self, gid: str, title: str, subtitle: str) -> QWidget:
        colour = theme.seg_hex(self._GROUP_SEG.get(gid, "image"))
        head = QWidget(self)
        head.setObjectName("libSectionHeader")
        head.setProperty("group", gid)
        head.setToolTip(subtitle)
        lay = QHBoxLayout(head)
        lay.setContentsMargins(4, 8, 4, 2)
        lay.setSpacing(7)

        icon = GroupIcon(gid, colour, head)
        icon.setToolTip(subtitle)
        lay.addWidget(icon)
        self._icons[gid] = icon

        lbl = QLabel(title, head)
        lbl.setObjectName("libSectionTitle")
        lbl.setToolTip(subtitle)
        lbl.setStyleSheet("color:%s; font-weight:700; font-size:11px;"
                          % TOKENS["text_secondary"])
        lay.addWidget(lbl)
        lay.addStretch(1)
        self._headers[gid] = head
        return head

    # -- public API --------------------------------------------------------
    def set_steps(self, steps: Sequence[Dict[str, Any]]) -> None:
        """用 ``Step.describe()`` 的 dict 清單重建整個卡片庫。"""
        self._clear()
        self._describes = {str(d.get("key", "")): dict(d) for d in (steps or [])}
        by_group: Dict[str, List[Dict[str, Any]]] = {g: [] for g in self._ORDER}
        for d in steps or []:
            gid = str(d.get("group") or "") or "enhance"
            by_group.setdefault(gid, []).append(d)

        for gid in self._ORDER:
            box = self._section_boxes[gid]
            entries = by_group.get(gid, [])
            if not entries:
                box.addWidget(self._empty_label(self._EMPTY_TEXT))
                continue
            seg = self._GROUP_SEG.get(gid, "image")
            for d in entries:
                item = _LibraryItem(d, theme.seg_hex(seg), self._host)
                item.activated.connect(self.add_requested)
                box.addWidget(item)
                self._items[item.step_key] = item
        for gid, btn in self.stage_buttons.items():
            btn.set_count(len(by_group.get(gid, [])))
        self._apply_filter()
        self._apply_badges()

    def set_available_streams(self, streams: Sequence[str]) -> None:
        """告訴卡片庫「目前 pipeline 到最後為止產出了哪些影像流」。

        據此標出前置條件未滿足的卡。傳空清單 = 不知道（badge 全清）。
        """
        self._available = [str(s) for s in (streams or [])]
        self._apply_badges()

    def entry(self, step_key: str) -> Optional[_LibraryItem]:
        """取得某張卡片的那一列（給主視窗做 highlight／給測試點擊）。"""
        return self._items.get(step_key)

    def step_keys(self) -> List[str]:
        return list(self._items)

    def visible_step_keys(self) -> List[str]:
        """目前**看得到**的卡（搜尋過濾之後）。

        同樣用明確狀態（``_matches``）而不是 ``isVisible()``，理由見
        :meth:`_LibraryItem.badge_text`。
        """
        return [k for k in self._items
                if self._matches(k)
                and self._group_open(str((self._describes.get(k) or {})
                                         .get("group") or ""))]

    def section_titles(self) -> List[str]:
        return [lbl.text() for lbl in self.findChildren(QLabel)
                if lbl.objectName() == "libSectionTitle"]

    def visible_section_titles(self) -> List[str]:
        """搜尋之後還有卡片的區塊標題（順序同 :data:`GROUPS`）。"""
        return [title for gid, title, _sub in self.GROUPS
                if gid in self._shown_groups]

    # -- 展開 / 收合（F7-7）--------------------------------------------------
    def toggle_group(self, group: Optional[str]) -> None:
        """點同一顆再點一次 = 收起來；點別顆 = 換過去（一次只開一段）。

        傳 ``None`` 直接全部收起來（測試 / 外部呼叫用）。訊號帶過來的是
        ``str``，所以這裡不能用 ``str(group)`` 一律轉字串 —— ``str(None)``
        會變成 ``"None"``，看起來像一個真的存在的段名。
        """
        gid = None if group is None else str(group)
        self._open_group = None if (gid is None or self._open_group == gid) else gid
        for g, btn in self.stage_buttons.items():
            btn.set_active(g == self._open_group)
        self._sync_panel()
        self._apply_filter()

    def panel_open(self) -> bool:
        """卡片區現在是展開的嗎（收起來時只剩 rail）。

        用明確狀態而不是 ``isVisible()`` —— 視窗還沒 show 之前 ``isVisible()``
        一律是 False，那會讓「收起來了嗎」在建構期永遠答錯。
        """
        return self._open_group is not None or bool(self._query)

    def _sync_panel(self) -> None:
        """展開狀態 -> panel 顯示 + 本身的最小寬度 + 通知外面重排欄寬。"""
        show = self.panel_open()
        self.panel.setVisible(show)
        self.setMinimumWidth(self.RAIL_W + (self.PANEL_W if show else 0))
        self.panel_toggled.emit(show)

    def open_group(self) -> Optional[str]:
        """目前展開的是哪一段（都收起來時回 None）。"""
        return self._open_group

    def set_query(self, text: str) -> None:
        """程式化設定搜尋字串（測試 / 外部呼叫用）。"""
        self.search.setText(str(text or ""))

    def focus_search(self) -> None:
        """展開卡片區並把游標放進搜尋框（rail 上的放大鏡鈕）。"""
        if not self.panel_open():
            self.toggle_group(self._ORDER[0])
        self.search.setFocus(Qt.OtherFocusReason)
        self.search.selectAll()

    def refresh_colors(self) -> None:
        """換主題之後重新取色（icon 與圓點都是自繪/內嵌樣式）。"""
        for gid, icon in self._icons.items():
            icon.set_color(theme.seg_hex(self._GROUP_SEG.get(gid, "image")))
        for gid, btn in self.stage_buttons.items():
            btn.refresh_colour(theme.seg_hex(self._GROUP_SEG.get(gid, "image")))
        self.search_button.refresh_colour(TOKENS["text_secondary"])

    # -- internals ---------------------------------------------------------
    def _empty_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("libEmpty")
        lbl.setStyleSheet("color:%s; font-size:11px; padding-left:12px;"
                          % TOKENS["text_disabled"])
        return lbl

    def _on_search(self, text: str) -> None:
        self._query = str(text or "").strip().lower()
        self._sync_panel()
        self._apply_filter()

    def _matches(self, key: str) -> bool:
        if not self._query:
            return True
        d = self._describes.get(key) or {}
        hay = " ".join([key, str(d.get("label", "")), str(d.get("help", "")),
                        str(d.get("group", ""))]).lower()
        return all(tok in hay for tok in self._query.split())

    def _group_open(self, gid: str) -> bool:
        """搜尋中 = 跨全部階段找；沒搜尋 = 只看展開的那一段。"""
        return True if self._query else (gid == self._open_group)

    def _apply_filter(self) -> None:
        """過濾卡片；沒展開的階段整段收起來。"""
        for key, item in self._items.items():
            gid = str((self._describes.get(key) or {}).get("group") or "")
            item.setVisible(self._matches(key) and self._group_open(gid))
        shown: List[str] = []
        for gid, head in self._headers.items():
            box = self._section_boxes[gid]
            hit = False
            opened = self._group_open(gid)
            for i in range(box.count()):
                w = box.itemAt(i).widget()
                if isinstance(w, _LibraryItem):
                    hit = hit or (self._matches(w.step_key) and opened)
                elif isinstance(w, QLabel):
                    # 空區塊的提示語只在該段展開、且沒搜尋時顯示
                    show = opened and not self._query
                    w.setVisible(show)
                    hit = hit or show
            head.setVisible(hit)
            if hit:
                shown.append(gid)
        self._shown_groups = [g for g in self._ORDER if g in shown]

    def _apply_badges(self) -> None:
        avail = set(self._available)
        for key, item in self._items.items():
            if not self._available:
                item.set_missing(())
                continue
            item.set_missing([r for r in item.reads if r not in avail])

    def _clear(self) -> None:
        self._items = {}
        for box in self._section_boxes.values():
            while box.count():
                item = box.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()


# --------------------------------------------------------------------------- #
# 4. PipelinePanel
# --------------------------------------------------------------------------- #
class _NodeCard(QFrame):
    """流程中的一個節點卡：左側 4px 段落色條 + 名稱/摘要 + 啟用勾 + ↑ ↓ ✕。"""

    # 注意：不要把訊號取名 move / remove —— 會蓋掉 QWidget.move() 等既有方法。
    clicked = Signal(str)
    enable_toggled = Signal(str, bool)
    move_requested = Signal(str, int)
    remove_requested = Signal(str)

    def __init__(self, node: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.node_id = str(node.get("node_id", ""))
        self.category = str(node.get("category", ""))
        self.enabled_flag = bool(node.get("enabled", True))
        self.setObjectName("nodeCard")
        self.setCursor(Qt.PointingHandCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(6)

        self.bar = QFrame()
        self.bar.setFixedWidth(4)
        self.bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        lay.addWidget(self.bar)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(2, 5, 0, 5)
        text_box.setSpacing(1)
        self.label = QLabel(str(node.get("label") or node.get("step_key") or ""))
        self.label.setObjectName("nodeLabel")
        self.summary = QLabel(str(node.get("summary", "") or ""))
        self.summary.setObjectName("nodeSummary")
        self.summary.setWordWrap(True)
        text_box.addWidget(self.label)
        text_box.addWidget(self.summary)
        lay.addLayout(text_box, 1)

        self.chk = QCheckBox()
        self.chk.setChecked(self.enabled_flag)
        self.chk.setToolTip("Temporarily skip this step (without removing it)")
        self.chk.toggled.connect(
            lambda v: self.enable_toggled.emit(self.node_id, bool(v)))
        lay.addWidget(self.chk)

        self.btn_up = self._small("↑", "Move one step earlier")
        self.btn_up.clicked.connect(
            lambda: self.move_requested.emit(self.node_id, -1))
        self.btn_down = self._small("↓", "Move one step later")
        self.btn_down.clicked.connect(
            lambda: self.move_requested.emit(self.node_id, +1))
        self.btn_remove = self._small("✕", "Remove from the pipeline")
        self.btn_remove.clicked.connect(
            lambda: self.remove_requested.emit(self.node_id))
        for b in (self.btn_up, self.btn_down, self.btn_remove):
            lay.addWidget(b)

        self.set_selected(False)

    def _small(self, text: str, tip: str) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("cardButton")
        b.setToolTip(tip)
        b.setFixedSize(QSize(22, 22))
        b.setCursor(Qt.PointingHandCursor)
        return b

    def set_selected(self, selected: bool) -> None:
        self.selected = bool(selected)
        on = self.enabled_flag
        bar_color = theme.seg_hex(self.category) if on else TOKENS["seg_disabled"]
        self.bar.setStyleSheet("background:%s; border:0; border-top-left-radius:7px;"
                               "border-bottom-left-radius:7px;" % bar_color)
        if selected:
            bg, border, width = TOKENS["accent_bg"], TOKENS["accent"], 2
        else:
            bg = TOKENS["bg_surface"] if on else TOKENS["seg_disabled_bg"]
            border, width = TOKENS["border_default"], 1
        self.setStyleSheet(
            "QFrame#nodeCard { background:%s; border:%dpx solid %s; border-radius:7px; }"
            % (bg, width, border)
        )
        text_color = TOKENS["text_primary"] if on else TOKENS["text_disabled"]
        sub_color = TOKENS["text_secondary"] if on else TOKENS["text_disabled"]
        self.label.setStyleSheet("color:%s; font-weight:700;" % text_color)
        self.summary.setStyleSheet("color:%s; font-size:11px;" % sub_color)

    def mousePressEvent(self, e) -> None:   # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.node_id)
        super().mousePressEvent(e)


class _ScoreCard(QFrame):
    """流程尾端固定存在的「Score / Bin」卡（ADC 段顏色）。點一下 -> 編分數。"""

    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("scoreCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Edit the score expression and threshold")
        self.setStyleSheet(
            "QFrame#scoreCard { background:%s; border:1px solid %s;"
            " border-radius:7px; }" % (theme.seg_hex("adc", bg=True),
                                       theme.seg_hex("adc"))
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(6)

        bar = QFrame()
        bar.setFixedWidth(4)
        bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        bar.setStyleSheet("background:%s; border:0; border-top-left-radius:7px;"
                          "border-bottom-left-radius:7px;" % theme.seg_hex("adc"))
        lay.addWidget(bar)

        box = QVBoxLayout()
        box.setContentsMargins(2, 5, 0, 5)
        box.setSpacing(1)
        title = QLabel("Score / Bin")
        title.setStyleSheet("color:%s; font-weight:700;" % theme.seg_hex("adc"))
        self.summary = QLabel("(no score set yet)")
        self.summary.setObjectName("scoreSummary")
        self.summary.setWordWrap(True)
        box.addWidget(title)
        box.addWidget(self.summary)
        lay.addLayout(box, 1)

    def mousePressEvent(self, e) -> None:   # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class PipelinePanel(QWidget):
    """有序的節點清單（資料驅動）+ 固定的 Score/Bin 尾卡。

    ``set_nodes`` 吃 dict 清單，每個 dict：
    ``{node_id, step_key, label, category, enabled, summary}``。
    重建時會保留目前選取的節點（只要它還在），所以改參數 -> 重繪 -> 選取不會亂跳。
    """

    node_selected = Signal(str)
    node_toggled = Signal(str, bool)
    move_requested = Signal(str, int)
    remove_requested = Signal(str)
    score_clicked = Signal()

    _EMPTY_TEXT = "(Pipeline is empty — double-click a card in the library to add the first step)"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._cards: Dict[str, _NodeCard] = {}
        self._order: List[str] = []
        self._selected: Optional[str] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._list = QVBoxLayout(self._host)
        self._list.setContentsMargins(4, 4, 8, 4)
        self._list.setSpacing(4)
        self._placeholder = QLabel(self._EMPTY_TEXT)
        self._placeholder.setObjectName("placeholder")
        self._placeholder.setWordWrap(True)
        self._list.addWidget(self._placeholder)
        self._list.addStretch(1)
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)

        self.score_card = _ScoreCard(self)
        self.score_card.clicked.connect(self.score_clicked)
        outer.addWidget(self.score_card)

    # -- public API --------------------------------------------------------
    def set_nodes(self, nodes: Sequence[Dict[str, Any]]) -> None:
        self._clear()
        self._order = []
        for node in nodes or []:
            card = _NodeCard(node, self._host)
            card.clicked.connect(self._on_card_clicked)
            card.enable_toggled.connect(self.node_toggled)
            card.move_requested.connect(self.move_requested)
            card.remove_requested.connect(self.remove_requested)
            self._list.insertWidget(self._list.count() - 1, card)
            self._cards[card.node_id] = card
            self._order.append(card.node_id)
        self._placeholder.setVisible(not self._order)
        if self._selected not in self._cards:
            self._selected = None
        self._refresh_selection()

    def set_score_summary(self, expr: str, threshold: float) -> None:
        """尾卡摘要：``score = <expr>   threshold <threshold>``。"""
        expr = str(expr or "").strip()
        if not expr:
            self.score_card.summary.setText("(no score set yet)")
            return
        self.score_card.summary.setText(
            "score = %s   threshold %s" % (expr, _fmt_number(threshold)))

    def score_summary_text(self) -> str:
        return self.score_card.summary.text()

    def selected(self) -> Optional[str]:
        return self._selected

    def set_selected(self, node_id: Optional[str]) -> None:
        """設定選取（不發 ``node_selected``；那是使用者點擊才發的）。"""
        self._selected = node_id if node_id in self._cards else None
        self._refresh_selection()

    def node_ids(self) -> List[str]:
        return list(self._order)

    def card(self, node_id: str) -> Optional[_NodeCard]:
        return self._cards.get(node_id)

    # -- internals ---------------------------------------------------------
    def _on_card_clicked(self, node_id: str) -> None:
        self._selected = node_id
        self._refresh_selection()
        self.node_selected.emit(node_id)

    def _refresh_selection(self) -> None:
        for nid, card in self._cards.items():
            card.set_selected(nid == self._selected)

    def _clear(self) -> None:
        for card in self._cards.values():
            self._list.removeWidget(card)
            card.setParent(None)
            card.deleteLater()
        self._cards = {}


# --------------------------------------------------------------------------- #
# 5. HistogramWidget
# --------------------------------------------------------------------------- #
class HistogramWidget(QWidget):
    """分數分佈長條圖 + 可拖曳的門檻線 + 可點擊的長條。

    資料來自 ``viewmodel.histogram(scores)``（edges 有 n+1 個、counts 有 n 個）。
    拖曳時持續發 ``threshold_changed``（上層用 ``viewmodel.rebin`` 秒回 bin 數），
    放開才發 ``threshold_committed``（上層才把值寫回 model / 重算）。

    「點一根長條」與「拖門檻」怎麼分（別改成用計時器）
    ------------------------------------------------
    兩件事都從同一顆左鍵 press 開始，所以**在放開的那一刻**才決定它是哪一種：

    ===========================================  ==========================
    放開時的狀況                                  結果
    ===========================================  ==========================
    滑鼠移動 > :data:`_CLICK_SLOP` px             拖門檻 → ``threshold_committed``
    press 落在門檻線 ±:data:`_HANDLE_PX` px 內    拖門檻（原地放開 = 重新確認門檻）
    以上皆非，且點在某根長條上                     ``bar_clicked(lo, hi)``，
                                                  **門檻退回按下去之前的值**
    ===========================================  ==========================

    最後一種情況會補發一次 ``threshold_changed(舊值)``，讓上層拖曳中的即時
    bin 摘要跟著還原 —— 點長條**不會**動到門檻，也不會發 committed。
    """

    threshold_changed = Signal(float)
    threshold_committed = Signal(float)
    #: 點一根長條：``(lo, hi)`` 是那根長條的分數區間（Studio 用來篩 Gallery）。
    bar_clicked = Signal(float, float)

    _EMPTY_TEXT = "(Score distribution appears after a trial run)"
    # 上緣留 20px 給門檻線的標籤（「門檻 3.5」畫在圖面之上，不壓到長條）
    _M_LEFT, _M_RIGHT, _M_TOP, _M_BOTTOM = 46.0, 14.0, 20.0, 30.0
    _SUMMARY_H = 18.0
    #: 按下點與門檻線的距離在這個範圍內 → 視為抓著門檻把手，不是點長條。
    _HANDLE_PX = 6.0
    #: 按下到放開的水平位移超過這個值 → 視為拖曳，不是點擊。
    _CLICK_SLOP = 3.0

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(140)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._edges: List[float] = []
        self._counts: List[int] = []
        self._threshold: Optional[float] = None
        self._bin_text = ""
        self._dragging = False
        self._hover_bin = -1
        # 點擊 vs 拖曳的判定用（見 class docstring）
        self._press_x: Optional[float] = None
        self._press_threshold: Optional[float] = None
        self._press_on_handle = False
        self._moved = False

    # -- public API --------------------------------------------------------
    def set_data(self, edges: Sequence[float], counts: Sequence[int]) -> None:
        """``edges`` / ``counts`` 直接吃 ``viewmodel.histogram()`` 的回傳值。"""
        edges = [float(e) for e in (edges or [])]
        counts = [int(c) for c in (counts or [])]
        if len(edges) != len(counts) + 1 or not counts:
            edges, counts = [], []
        self._edges, self._counts = edges, counts
        if self._threshold is not None:
            self._threshold = self._clamp(self._threshold)
        self.update()

    def set_threshold(self, value: Optional[float]) -> None:
        """設定門檻線位置（不發訊號；程式設定不應該回頭觸發自己）。"""
        self._threshold = None if value is None else self._clamp(float(value))
        self.update()

    def threshold(self) -> Optional[float]:
        return self._threshold

    def set_bin_summary(self, bins: Optional[Dict[int, int]]) -> None:
        """``{0: 812, 1: 96}`` -> 「bin 0=812   bin 1=96」。"""
        if not bins:
            self._bin_text = ""
        else:
            self._bin_text = "   ".join(
                "bin %s=%s" % (k, bins[k]) for k in sorted(bins))
        self.update()

    def bin_summary_text(self) -> str:
        return self._bin_text

    def has_data(self) -> bool:
        return bool(self._counts) and sum(self._counts) > 0

    def bar_range(self, index: int) -> Optional[Tuple[float, float]]:
        """第 ``index`` 根長條的分數區間 ``(lo, hi)``；超出範圍回 None。"""
        i = int(index)
        if not self._counts or not (0 <= i < len(self._counts)):
            return None
        return (float(self._edges[i]), float(self._edges[i + 1]))

    # -- geometry ----------------------------------------------------------
    def _plot_rect(self) -> QRectF:
        extra = self._SUMMARY_H if self._bin_text else 0.0
        w = max(20.0, self.width() - self._M_LEFT - self._M_RIGHT)
        h = max(20.0, self.height() - self._M_TOP - self._M_BOTTOM - extra)
        return QRectF(self._M_LEFT, self._M_TOP, w, h)

    def _span(self) -> Tuple[float, float]:
        if not self._edges:
            return 0.0, 1.0
        lo, hi = self._edges[0], self._edges[-1]
        return (lo, hi if hi > lo else lo + 1.0)

    def _x_at(self, value: float) -> float:
        lo, hi = self._span()
        r = self._plot_rect()
        return r.left() + (float(value) - lo) / (hi - lo) * r.width()

    def _value_at(self, x: float) -> float:
        lo, hi = self._span()
        r = self._plot_rect()
        t = 0.0 if r.width() <= 0 else (float(x) - r.left()) / r.width()
        return self._clamp(lo + t * (hi - lo))

    def _clamp(self, v: float) -> float:
        lo, hi = self._span()
        if not self._edges:
            return float(v)
        return float(min(max(v, lo), hi))

    def _bar_at(self, x: float) -> int:
        if not self._counts:
            return -1
        r = self._plot_rect()
        if x < r.left() or x > r.right():
            return -1
        n = len(self._counts)
        i = int((x - r.left()) / max(1e-9, r.width()) * n)
        return int(min(max(i, 0), n - 1))

    # -- painting ----------------------------------------------------------
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        frame = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
        p.setBrush(QColor(TOKENS["bg_panel"]))
        p.drawRoundedRect(frame, 7, 7)

        if not self.has_data():
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(self.rect(), Qt.AlignCenter, self._EMPTY_TEXT)
            p.end()
            return

        r = self._plot_rect()
        small = QFont(p.font())
        small.setPointSize(8)
        p.setFont(small)

        # 座標軸（低調的細線）
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
        p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.bottom()))
        p.drawLine(QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom()))

        ymax = max(self._counts) or 1
        n = len(self._counts)
        bw = r.width() / n
        bar = QColor(theme.seg_hex("algo"))
        hover = QColor(TOKENS["accent_active"])
        p.setPen(Qt.NoPen)
        for i, c in enumerate(self._counts):
            if c <= 0:
                continue
            bh = c / float(ymax) * r.height()
            x = r.left() + i * bw
            p.setBrush(hover if i == self._hover_bin else bar)
            p.drawRect(QRectF(x + 0.5, r.bottom() - bh, max(1.0, bw - 1.0), bh))

        # 刻度文字
        lo, hi = self._span()
        p.setPen(QColor(TOKENS["text_hint"]))
        p.drawText(QRectF(r.left() - self._M_LEFT + 2, r.top() - 6,
                          self._M_LEFT - 6, 14),
                   Qt.AlignRight | Qt.AlignVCenter, str(ymax))
        p.drawText(QRectF(r.left() - self._M_LEFT + 2, r.bottom() - 7,
                          self._M_LEFT - 6, 14),
                   Qt.AlignRight | Qt.AlignVCenter, "0")
        p.drawText(QRectF(r.left(), r.bottom() + 2, r.width() / 2, 14),
                   Qt.AlignLeft, "%.3g" % lo)
        p.drawText(QRectF(r.center().x(), r.bottom() + 2, r.width() / 2, 14),
                   Qt.AlignRight, "%.3g" % hi)

        # 門檻線
        if self._threshold is not None:
            x = self._x_at(self._threshold)
            pen = QPen(QColor(TOKENS["accent_active"]), 2)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(x, r.top() - 3), QPointF(x, r.bottom() + 3))
            p.setPen(QColor(TOKENS["accent_active"]))
            label = "threshold %s" % _fmt_number(self._threshold)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(label) + 4
            tx = min(max(x + 3, r.left()), max(r.left(), r.right() - tw))
            p.drawText(QRectF(tx, r.top() - self._M_TOP + 2, tw,
                              self._M_TOP - 4),
                       Qt.AlignLeft | Qt.AlignVCenter, label)

        # bin 摘要
        if self._bin_text:
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(r.left(), r.bottom() + 16, r.width(),
                              self._SUMMARY_H),
                       Qt.AlignLeft | Qt.AlignVCenter, self._bin_text)
        p.end()

    # -- interaction -------------------------------------------------------
    def mousePressEvent(self, e) -> None:   # noqa: D102 - Qt hook
        if e.button() != Qt.LeftButton or not self.has_data():
            return
        pos = QPointF(e.position())
        if not self._plot_rect().adjusted(-6, -6, 6, 6).contains(pos):
            return
        self._dragging = True
        self._press_x = float(pos.x())
        self._press_threshold = self._threshold
        self._press_on_handle = (
            self._threshold is not None
            and abs(pos.x() - self._x_at(self._threshold)) <= self._HANDLE_PX)
        self._moved = False
        self._set_from_mouse(pos.x())
        e.accept()

    def mouseMoveEvent(self, e) -> None:    # noqa: D102 - Qt hook
        pos = QPointF(e.position())
        if self._dragging:
            if (self._press_x is not None
                    and abs(pos.x() - self._press_x) > self._CLICK_SLOP):
                self._moved = True
            self._set_from_mouse(pos.x())
            return
        self._update_hover(pos)

    def mouseReleaseEvent(self, e) -> None:  # noqa: D102 - Qt hook
        if not self._dragging:
            return
        self._dragging = False
        idx = -1 if self._press_x is None else self._bar_at(self._press_x)
        rng = self.bar_range(idx)
        if not self._moved and not self._press_on_handle and rng is not None:
            self._restore_press_threshold()
            self.bar_clicked.emit(float(rng[0]), float(rng[1]))
            return
        if self._threshold is not None:
            self.threshold_committed.emit(float(self._threshold))

    def _restore_press_threshold(self) -> None:
        """點長條：門檻退回按下去之前的值（並補一次 changed 讓上層還原顯示）。"""
        old = self._press_threshold
        self._threshold = None if old is None else self._clamp(float(old))
        self.update()
        if self._threshold is not None:
            self.threshold_changed.emit(float(self._threshold))

    def leaveEvent(self, _e) -> None:       # noqa: D102 - Qt hook
        if self._hover_bin != -1:
            self._hover_bin = -1
            self.setToolTip("")
            self.update()

    def _set_from_mouse(self, x: float) -> None:
        value = self._value_at(x)
        if self._threshold is None or value != self._threshold:
            self._threshold = value
            self.update()
        self.threshold_changed.emit(float(value))

    def _update_hover(self, pos: QPointF) -> None:
        idx = -1
        if self.has_data() and self._plot_rect().contains(pos):
            idx = self._bar_at(pos.x())
        if idx == self._hover_bin:
            return
        self._hover_bin = idx
        if idx < 0:
            self.setToolTip("")
        else:
            a, b = self._edges[idx], self._edges[idx + 1]
            self.setToolTip("score %.3g–%.3g: %d defects"
                            % (a, b, self._counts[idx]))
        self.update()


# --------------------------------------------------------------------------- #
# 6. FeatureTable / VerdictChip
# --------------------------------------------------------------------------- #
def _fmt_number(value: Any) -> str:
    """數值 -> 好讀字串：整數不拖小數點、一般值 3 位、極小值退回有效位數。"""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(f):
        return "NaN"
    if math.isinf(f):
        return "∞" if f > 0 else "-∞"
    if f == int(f) and abs(f) < 1e12:
        return str(int(f))
    if 0 < abs(f) < 5e-4:
        return "%.3g" % f
    return "%.3f" % f


class FeatureTable(QTableWidget):
    """特徵 / 數值 兩欄表；``score`` 永遠釘在最後一列且用粗體。"""

    _SCORE = "score"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Feature", "Value"])
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        head = self.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        head.setSectionResizeMode(1, QHeaderView.ResizeToContents)

    def set_features(self, features: Optional[Dict[str, Any]],
                     highlight: Iterable[str] = ()) -> None:
        """填表。``highlight`` 內的特徵名會用 accent 底色標出（例：分數用到的）。"""
        features = dict(features or {})
        hi = set(highlight or ())
        names = [k for k in features if k != self._SCORE]
        if self._SCORE in features:
            names.append(self._SCORE)

        self.setRowCount(len(names))
        for row, name in enumerate(names):
            is_score = name == self._SCORE
            key_item = QTableWidgetItem(str(name))
            val_item = QTableWidgetItem(_fmt_number(features[name]))
            val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if is_score:
                font = key_item.font()
                font.setBold(True)
                key_item.setFont(font)
                val_item.setFont(font)
                key_item.setForeground(QColor(TOKENS["accent_active"]))
                val_item.setForeground(QColor(TOKENS["accent_active"]))
            if name in hi:
                bg = QColor(TOKENS["accent_bg"])
                key_item.setBackground(bg)
                val_item.setBackground(bg)
            self.setItem(row, 0, key_item)
            self.setItem(row, 1, val_item)

    def feature_names(self) -> List[str]:
        return [self.item(r, 0).text() for r in range(self.rowCount())
                if self.item(r, 0) is not None]

    def value_text(self, name: str) -> Optional[str]:
        for r in range(self.rowCount()):
            key = self.item(r, 0)
            if key is not None and key.text() == name:
                val = self.item(r, 1)
                return None if val is None else val.text()
        return None


class VerdictChip(QLabel):
    """判定 chip：``bin 1 · ≥門檻`` / ``bin 0 · <門檻`` / ``—``。

    ``is_real_style=True`` 時色彩語意反轉：bin 1 代表「這是真缺陷」，是壞消息
    （紅），bin 0 是乾淨（綠）。預設（False）則照「過門檻 = 好」來配色。
    文字兩種模式都一樣，只有顏色換邊。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(112)
        self.setMinimumHeight(28)
        self._bin: Optional[int] = None
        self.set_verdict(None)

    def set_verdict(self, bin_value: Optional[Any] = None,
                    is_real_style: bool = False) -> None:
        try:
            b = None if bin_value is None else int(bin_value)
        except (TypeError, ValueError):
            b = None
        self._bin = b
        if b is None:
            text, tone = "—", "neutral"
        elif b == 1:
            text = "bin 1 · ≥ threshold"
            tone = "bad" if is_real_style else "good"
        elif b == 0:
            text = "bin 0 · < threshold"
            tone = "good" if is_real_style else "bad"
        else:
            text, tone = "bin %d" % b, "neutral"
        bg = TOKENS["chip_%s_bg" % tone]
        fg = TOKENS["chip_%s_text" % tone]
        border = TOKENS["chip_%s_border" % tone]
        self.setText(text)
        self.setProperty("tone", tone)
        self.setStyleSheet(
            "background:%s; color:%s; border:1px solid %s; border-radius:8px;"
            "padding:4px 12px; font-weight:700;" % (bg, fg, border))

    def verdict(self) -> Optional[int]:
        return self._bin

    def tone(self) -> str:
        return str(self.property("tone"))

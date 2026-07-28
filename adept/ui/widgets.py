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
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
        raise ValueError(f"不支援的影像形狀：{a.shape}")
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

    _MIN_SCALE = 0.02
    _MAX_SCALE = 60.0
    _EMPTY_TEXT = "（無影像）"

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
        p.setBrush(QColor(TOKENS["bg_panel"]))
        p.drawRoundedRect(rect, 7, 7)
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
            self.cursor_info.emit(f"x {x}  y {y}  ·  灰階 {gray}")
        else:
            self.cursor_info.emit("")


# --------------------------------------------------------------------------- #
# 2. ParamForm
# --------------------------------------------------------------------------- #
class _ParamRow(QFrame):
    """一個參數 = 標題列（名稱 + 編輯器）+ 永遠看得見的白話說明第二行。"""

    def __init__(self, spec: Dict[str, Any], editor: QWidget,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.spec = spec
        self.editor = editor
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


class ParamForm(QWidget):
    """由 ``Step.describe()`` 的 ParamSpec dict 自動長出來的參數表單。

    ``set_step(describe, current_params, stream_choices)`` 一次重建整張表；
    使用者改動任何欄位 -> ``param_edited(name, value)``（值已 coerce 成該型別）。
    上層驗證失敗時呼叫 ``show_error(name, msg)`` 把那一列的說明變紅字。
    """

    param_edited = Signal(str, object)

    _EMPTY_TEXT = "（在左邊點一張卡片，或在流程中選一個節點）"

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

    def step_key(self) -> Optional[str]:
        return None if not self._describe else str(self._describe.get("key"))

    def param_names(self) -> List[str]:
        return list(self._rows)

    def editor(self, name: str) -> Optional[QWidget]:
        row = self._rows.get(name)
        return None if row is None else row.editor

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
            w = QCheckBox("啟用")
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
class _LibraryItem(QFrame):
    """卡片庫的一列：名稱 + hover 才出現的「加入 ▸」；雙擊也能加入。"""

    activated = Signal(str)

    def __init__(self, describe: Dict[str, Any], color: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.step_key = str(describe.get("key", ""))
        self.setObjectName("libItem")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QFrame#libItem { background:%s; border:1px solid %s; border-radius:6px; }"
            % (TOKENS["bg_surface"], TOKENS["border_default"])
        )
        tip = str(describe.get("help", "")) or str(describe.get("label", ""))
        if describe.get("requires_ref"):
            tip += "（需要 ref 影像）"
        self.setToolTip(tip)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 6, 4)
        lay.setSpacing(6)

        dot = QFrame()
        dot.setFixedSize(6, 6)
        dot.setStyleSheet("background:%s; border-radius:3px;" % color)
        lay.addWidget(dot)

        self.label = QLabel(str(describe.get("label") or self.step_key))
        self.label.setToolTip(tip)
        lay.addWidget(self.label, 1)

        self.add_button = QPushButton("加入 ▸")
        self.add_button.setObjectName("cardButton")
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.setToolTip("把這張卡片加到流程尾端")
        self.add_button.setFixedWidth(58)
        self.add_button.clicked.connect(
            lambda: self.activated.emit(self.step_key))
        self.add_button.setVisible(False)
        lay.addWidget(self.add_button)

    def enterEvent(self, e) -> None:      # noqa: D102 - Qt hook
        self.add_button.setVisible(True)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:      # noqa: D102 - Qt hook
        self.add_button.setVisible(False)
        super().leaveEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:   # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self.activated.emit(self.step_key)


class LibraryPanel(QWidget):
    """卡片庫：依三段式分類（影像／算法／ADC）分區，區塊標題帶各段顏色。

    ``set_steps(list_of_describe_dicts)`` 之後，雙擊某列或按該列的「加入 ▸」
    都會發出 ``add_requested(step_key)``。空的區塊會留一行提示，讓使用者知道
    「這一段目前沒有卡片」而不是以為壞掉了。
    """

    add_requested = Signal(str)

    _ORDER = ("image", "algo", "adc")
    _EMPTY_TEXT = "（這一段目前沒有卡片）"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._items: Dict[str, _LibraryItem] = {}
        self._section_boxes: Dict[str, QVBoxLayout] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._body = QVBoxLayout(self._host)
        self._body.setContentsMargins(6, 6, 8, 6)
        self._body.setSpacing(4)

        for cat in self._ORDER:
            header = QLabel(theme.SEG_LABELS[cat])
            header.setObjectName("libSectionHeader")
            header.setProperty("category", cat)
            header.setStyleSheet(
                "background:%s; color:%s; border:1px solid %s; border-radius:5px;"
                "padding:3px 8px; font-weight:700; font-size:11px;"
                % (theme.seg_hex(cat, bg=True), theme.seg_hex(cat),
                   theme.seg_hex(cat, bg=True))
            )
            self._body.addWidget(header)
            box = QVBoxLayout()
            box.setContentsMargins(0, 0, 0, 4)
            box.setSpacing(3)
            self._body.addLayout(box)
            self._section_boxes[cat] = box

        self._body.addStretch(1)
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll)

        self.set_steps([])

    # -- public API --------------------------------------------------------
    def set_steps(self, steps: Sequence[Dict[str, Any]]) -> None:
        """用 ``Step.describe()`` 的 dict 清單重建整個卡片庫。"""
        self._clear()
        by_cat: Dict[str, List[Dict[str, Any]]] = {c: [] for c in self._ORDER}
        for d in steps or []:
            cat = str(d.get("category", ""))
            by_cat.setdefault(cat, []).append(d)
        for cat in self._ORDER:
            box = self._section_boxes[cat]
            entries = by_cat.get(cat, [])
            if not entries:
                empty = QLabel(self._EMPTY_TEXT)
                empty.setObjectName("libEmpty")
                empty.setStyleSheet("color:%s; font-size:11px; padding-left:8px;"
                                    % TOKENS["text_disabled"])
                box.addWidget(empty)
                continue
            for d in entries:
                item = _LibraryItem(d, theme.seg_hex(cat), self._host)
                item.activated.connect(self.add_requested)
                box.addWidget(item)
                self._items[item.step_key] = item

    def entry(self, step_key: str) -> Optional[_LibraryItem]:
        """取得某張卡片的那一列（給主視窗做 highlight／給測試點擊）。"""
        return self._items.get(step_key)

    def step_keys(self) -> List[str]:
        return list(self._items)

    def section_titles(self) -> List[str]:
        return [lbl.text() for lbl in self.findChildren(QLabel)
                if lbl.objectName() == "libSectionHeader"]

    # -- internals ---------------------------------------------------------
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
        self.chk.setToolTip("暫時停用這個步驟（不刪除）")
        self.chk.toggled.connect(
            lambda v: self.enable_toggled.emit(self.node_id, bool(v)))
        lay.addWidget(self.chk)

        self.btn_up = self._small("↑", "往前移一格")
        self.btn_up.clicked.connect(
            lambda: self.move_requested.emit(self.node_id, -1))
        self.btn_down = self._small("↓", "往後移一格")
        self.btn_down.clicked.connect(
            lambda: self.move_requested.emit(self.node_id, +1))
        self.btn_remove = self._small("✕", "從流程移除")
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
        self.setToolTip("設定分數表達式與門檻")
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
        self.summary = QLabel("（尚未設定分數）")
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

    _EMPTY_TEXT = "（流程還是空的 —— 從左邊的卡片庫雙擊加入第一張卡）"

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
        """尾卡摘要：``score = <expr>　門檻 <threshold>``。"""
        expr = str(expr or "").strip()
        if not expr:
            self.score_card.summary.setText("（尚未設定分數）")
            return
        self.score_card.summary.setText(
            "score = %s　門檻 %s" % (expr, _fmt_number(threshold)))

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

    _EMPTY_TEXT = "（試跑後顯示分數分佈）"
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
        """``{0: 812, 1: 96}`` -> 「bin 0=812　bin 1=96」。"""
        if not bins:
            self._bin_text = ""
        else:
            self._bin_text = "　".join(
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
            label = "門檻 %s" % _fmt_number(self._threshold)
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
            self.setToolTip("score %.3g–%.3g：%d 顆"
                            % (a, b, self._counts[idx]))
        self.update()


# --------------------------------------------------------------------------- #
# 6. FeatureTable / VerdictChip
# --------------------------------------------------------------------------- #
def _fmt_number(value: Any) -> str:
    """數值 -> 好讀字串：整數不拖小數點、一般值 3 位、極小值退回有效位數。"""
    if isinstance(value, bool):
        return "是" if value else "否"
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
        self.setHorizontalHeaderLabels(["特徵", "數值"])
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
            text = "bin 1 · ≥門檻"
            tone = "bad" if is_real_style else "good"
        elif b == 0:
            text = "bin 0 · <門檻"
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

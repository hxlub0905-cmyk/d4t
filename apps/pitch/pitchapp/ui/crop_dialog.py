# d4t Studio — authored 2026-09-17 (F102).
"""crop_dialog —— 疊模板之前**先框一塊**。

使用者：「載入 template 的大圖，可以選擇要不要 crop 想要的部分之後再進行計算」。

為什麼要有它
------------
`build_golden_cell` 疊的是**整張**大圖。整張圖裡不只有你要的那種 cell：
RSEM 大圖的正中央就是缺陷本體（疊進去會把一塊暗的平均進模板）、邊上可能有
scribe line 或另一種 layout、機台的量測條會蓋在角落。週期估測看的是整張圖的
投影，這些東西一多，估出來的就不是你要的那個週期 —— 而錯的週期疊出來的模板
**會讓後面每一顆都對錯，畫面上不會有錯誤訊息**（`template_dialog` 模組說明）。

所以要有一個地方讓使用者說「只看這一塊」。那一塊是**在圖上拉出來的**，不是四個
打進去的數字 —— 四個數字沒有一個地方講得清楚它們相對於什麼，一張圖講得清楚
（同 `cell_canvas` 的理由）。

裁的是**原料**，不是結果
------------------------
裁切只影響「拿哪些像素去量週期、疊 cell」。存進 recipe 的仍然只有模板本身
（`template_dialog` 模組說明的「大圖不進 recipe，模板才進」），所以裁切框
**不進 recipe**，它跟大圖的路徑一樣是這一次操作的事。摘要那一行會講出
「從哪一塊疊的」，那是判斷材料，不是設定。

這一支只做一件事
----------------
畫出大圖、讓人拉一個框、回傳 ``(x, y, w, h)``（影像像素）。它不量週期、不疊
cell、不知道模板是什麼 —— 那些都在 `template_dialog`。一塊新的畫布元件＝一個
新模組（`CLAUDE.md` §4）。
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

import numpy as np
from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget,
)

from . import fit_screen
from .theme import TOKENS
from .icons import apply_button_cursors   # 不走 `widgets` 轉出口（見 pitch_helper）
from . import buttons as buttons_mod

__all__ = ["CropView", "CropDialog", "MIN_SIDE", "crop_array"]

Rect = Tuple[int, int, int, int]

#: 一個框最小要幾像素見方。比這個小的框**當成沒拉**（不是「一個很小的框」）：
#: 那多半是手抖點了一下，而一個 3×3 的裁切送進 `build_golden_cell` 只會得到
#: 一句「量不到週期」—— 兩種結果都不是使用者要的，但前者讓他重拉一次就好。
MIN_SIDE = 8


def crop_array(image: Any, rect: Optional[Rect]) -> np.ndarray:
    """``rect=(x, y, w, h)`` 裁下來（裁進影像邊界）；``None`` 就原樣回傳。

    **這裡是唯一一處把框變成像素的地方** —— `template_dialog` 疊 cell 與
    這個對話框畫預覽都走它，兩邊各裁各的那天會出現「預覽上框的跟疊進去的
    不是同一塊」。
    """
    a = np.asarray(image)
    if rect is None or a.ndim < 2 or a.size == 0:
        return a
    h, w = int(a.shape[0]), int(a.shape[1])
    x, y, cw, ch = (int(v) for v in rect)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(w, x + cw), min(h, y + ch)
    if x1 <= x0 or y1 <= y0:
        return a
    return a[y0:y1, x0:x1]


def clamp_rect(rect: Optional[Rect], shape: Tuple[int, int]) -> Optional[Rect]:
    """把框裁進 ``(h, w)`` 的影像裡；裁完不到 :data:`MIN_SIDE` 就回 ``None``。"""
    if rect is None:
        return None
    h, w = int(shape[0]), int(shape[1])
    x, y, cw, ch = (int(v) for v in rect)
    x0, y0 = max(0, min(x, w)), max(0, min(y, h))
    x1, y1 = max(0, min(x + cw, w)), max(0, min(y + ch, h))
    if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def _to_u8(arr: np.ndarray) -> np.ndarray:
    """給畫面看的 8-bit：非 8-bit 就 min-max 拉一下（只是預覽，不進計算）。"""
    a = np.asarray(arr)
    if a.ndim == 3:
        a = a.mean(axis=2)
    if a.dtype == np.uint8:
        return np.ascontiguousarray(a)
    f = a.astype(np.float64)
    lo, hi = float(f.min()), float(f.max())
    if hi <= lo:
        return np.zeros(f.shape, np.uint8)
    return np.ascontiguousarray(((f - lo) * (255.0 / (hi - lo))).astype(np.uint8))


class CropView(QWidget):
    """畫大圖、拉一個框。座標一律是**影像像素**，縮放只發生在畫的時候。"""

    #: 框變了（``(x, y, w, h)`` 或 ``None``）。
    rect_changed = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._image: Optional[np.ndarray] = None
        self._pixmap: Optional[QPixmap] = None
        self._rect: Optional[Rect] = None
        self._anchor: Optional[Tuple[int, int]] = None
        self._dragging = False
        self.setMinimumSize(320, 240)
        self.setMouseTracking(False)
        self.setCursor(Qt.CrossCursor)

    # ---- 資料 ---------------------------------------------------------------
    def set_image(self, image: Any) -> None:
        a = None if image is None else np.asarray(image)
        if a is None or a.size == 0 or a.ndim < 2:
            self._image, self._pixmap, self._rect = None, None, None
            self.update()
            return
        u8 = _to_u8(a)
        h, w = u8.shape[:2]
        self._image = u8
        self._pixmap = QPixmap.fromImage(
            QImage(u8.data, w, h, w, QImage.Format_Grayscale8).copy())
        self._rect = None
        self.update()

    def image_shape(self) -> Optional[Tuple[int, int]]:
        return None if self._image is None else (int(self._image.shape[0]),
                                                  int(self._image.shape[1]))

    def box(self) -> Optional[Rect]:
        """目前的框（影像像素），沒有就 ``None``。

        ⚠ **不能叫 ``rect()``**：那是 ``QWidget.rect()``（整個 widget 的矩形），
        `paintEvent` 靠它填背景。第一版就叫 `rect`，於是還沒拉框的時候
        `self.rect()` 回 ``None``，`fillRect(None, …)` 當場炸在使用者面前
        （2026-09-17 回報）—— 而 headless 測試沒抓到，因為視窗從沒真的畫過。
        現在 `tests/test_ui_crop_dialog.py` 會 ``grab()`` 一次逼它畫。
        """
        return self._rect

    def set_box(self, rect: Optional[Rect]) -> None:
        if self._image is None:
            return
        new = clamp_rect(rect, self._image.shape[:2])
        if new != self._rect:
            self._rect = new
            self.rect_changed.emit(new)
        self.update()

    def clear(self) -> None:
        self.set_box(None)

    # ---- 影像 ↔ 畫面 ----------------------------------------------------------
    def _fit(self) -> Tuple[float, int, int]:
        """``(scale, x0, y0)``：整張圖等比例縮到畫面裡、置中。"""
        if self._image is None:
            return 1.0, 0, 0
        h, w = self._image.shape[:2]
        aw, ah = max(1, self.width()), max(1, self.height())
        s = min(aw / float(w), ah / float(h))
        return s, int((aw - w * s) / 2), int((ah - h * s) / 2)

    def to_image(self, x: float, y: float) -> Tuple[int, int]:
        s, x0, y0 = self._fit()
        return int(round((x - x0) / s)), int(round((y - y0) / s))

    # ---- 滑鼠 ---------------------------------------------------------------
    def mousePressEvent(self, e) -> None:  # Qt hook
        if self._image is None or e.button() != Qt.LeftButton:
            return
        p = e.position() if hasattr(e, "position") else e.localPos()
        self._anchor = self.to_image(p.x(), p.y())
        self._dragging = True
        self._rect_from(self._anchor)

    def mouseMoveEvent(self, e) -> None:  # Qt hook
        if not self._dragging or self._anchor is None:
            return
        p = e.position() if hasattr(e, "position") else e.localPos()
        self._rect_from(self.to_image(p.x(), p.y()))

    def mouseReleaseEvent(self, e) -> None:  # Qt hook
        if not self._dragging:
            return
        p = e.position() if hasattr(e, "position") else e.localPos()
        self._rect_from(self.to_image(p.x(), p.y()))
        self._dragging = False
        self._anchor = None

    def _rect_from(self, corner: Tuple[int, int]) -> None:
        if self._anchor is None:
            return
        ax, ay = self._anchor
        cx, cy = corner
        x0, x1 = sorted((ax, cx))
        y0, y1 = sorted((ay, cy))
        # 拉的中途太小的框也先畫出來（不然剛按下去畫面沒反應）；放開的時候
        # `clamp_rect` 會把不到 MIN_SIDE 的當成沒拉。
        self.set_box((x0, y0, x1 - x0, y1 - y0))

    # ---- 畫 -----------------------------------------------------------------
    def paintEvent(self, _e) -> None:  # Qt hook
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(TOKENS["image_backdrop"]))
        if self._pixmap is None:
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(self.rect(), Qt.AlignCenter, "(no image)")
            p.end()
            return
        s, x0, y0 = self._fit()
        h, w = self._image.shape[:2]
        target = QRect(x0, y0, int(w * s), int(h * s))
        p.setRenderHint(QPainter.SmoothPixmapTransform, s < 1.0)
        p.drawPixmap(target, self._pixmap)
        if self._rect is not None:
            x, y, cw, ch = self._rect
            box = QRect(x0 + int(x * s), y0 + int(y * s),
                        max(1, int(cw * s)), max(1, int(ch * s)))
            # 框外面壓暗：「只看這一塊」要一眼看得出哪一塊。
            shade = QColor(0, 0, 0, 110)
            for part in (QRect(target.left(), target.top(), target.width(),
                               box.top() - target.top()),
                         QRect(target.left(), box.bottom() + 1, target.width(),
                               target.bottom() - box.bottom()),
                         QRect(target.left(), box.top(), box.left() - target.left(),
                               box.height()),
                         QRect(box.right() + 1, box.top(),
                               target.right() - box.right(), box.height())):
                if part.width() > 0 and part.height() > 0:
                    p.fillRect(part, shade)
            p.setPen(QPen(QColor(TOKENS["accent"]), 1.5))
            p.drawRect(box)
        p.end()


class CropDialog(QDialog):
    """「只看這一塊」—— 三選一：這一塊／整張／算了。

    2026-09-17 使用者定調：這個視窗**每次載入大圖都會出現**（「crop 相關功能請直接
    接進 Rebuild from image」），所以「整張」那顆鈕就是以前的「不裁」。
    """

    def __init__(self, image: Any, name: str = "",
                 initial: Optional[Rect] = None,
                 parent: Optional[QWidget] = None,
                 ok_text: str = "Stack from this box"):
        """``ok_text`` —— 那顆確定鈕上的字。

        ⚠ 它是參數而不是寫死的一句話，因為**按下去之後會發生什麼事不只一種**：
        模板那條路按完去疊 cell（"Stack from this box"），而 `pitch_helper`
        按完只是量一次週期，不疊任何東西（F120）。寫死的話那顆鈕會對其中一邊
        說謊，而分叉出第二個裁切對話框會讓「框怎麼變成像素」有兩個家
        （見 :func:`crop_array` 的說明）。
        """
        super().__init__(parent)
        self.setWindowTitle("Where to measure the cell")
        fit_screen.fit(self, 960, 720)
        self._whole = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        hint = QLabel(
            "Drag a box around the part of the image the cell should be "
            "measured from - leave out the defect, scribe lines, the scale bar "
            "and anything that is not the repeating layout. Or use the whole "
            "image.", self)
        hint.setObjectName("paramHint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.view = CropView(self)
        self.view.set_image(image)
        self.view.rect_changed.connect(lambda _r: self._refresh())
        lay.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.size_label = QLabel("", self)
        self.size_label.setObjectName("paramHint")
        row.addWidget(self.size_label, 1)
        self.btn_whole = QPushButton("Use the whole image", self)
        self.btn_whole.setProperty("variant", "secondary")
        self.btn_whole.setToolTip("No crop - measure the cell from every pixel.")
        self.btn_whole.clicked.connect(self._on_whole)
        row.addWidget(self.btn_whole)
        lay.addLayout(row)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttons.button(QDialogButtonBox.Ok).setText(str(ok_text))
        buttons_mod.mark_primary(self.buttons)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)

        self._name = str(name or "")
        if initial is not None:
            self.view.set_box(initial)
        self._refresh()
        apply_button_cursors(self)

    # ---- 結果 ---------------------------------------------------------------
    def box(self) -> Optional[Rect]:
        """接受之後：框（影像像素）；按了「整張」或沒拉框就是 ``None``。
        （同 `CropView.box`：不能叫 ``rect``，那是 Qt 的。）"""
        return None if self._whole else self.view.box()

    def _on_whole(self) -> None:
        self._whole = True
        self.accept()

    def _refresh(self) -> None:
        r = self.view.box()
        shape = self.view.image_shape()
        ok = self.buttons.button(QDialogButtonBox.Ok)
        if r is None:
            ok.setEnabled(False)
            self.size_label.setText(
                "No box yet - the whole image (%d x %d px) would be used."
                % (shape[1], shape[0]) if shape else "")
            return
        ok.setEnabled(True)
        self.size_label.setText("Box %d x %d px at (%d, %d)" % (r[2], r[3], r[0], r[1]))


def describe_crop(rect: Optional[Rect]) -> str:
    """摘要用的一小段字（沒裁就是空字串）—— 一個家，`template_dialog` 兩處都用它。"""
    if rect is None:
        return ""
    return "cropped to %d x %d px at (%d, %d)" % (rect[2], rect[3], rect[0], rect[1])

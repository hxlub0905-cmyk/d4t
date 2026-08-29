# d4t Studio：在 Golden Cell 上畫出「缺陷可能在哪」 — authored 2026-08-28 (F61).
"""**畫在一個週期上，就等於畫在每一個重複上。**

使用者 2026-08-28：「我希望這個製造 defect 的 UI 不僅僅只是製造 inner
spacer，而是使用者可以利用 GC 的方式（**反正都是回推**），畫出 defect 可能
在的位置，UI 去隨機產生。」

那句「反正都是回推」是整件事的關鍵，而它讓這個元件小得出乎意料：大圖是把
GC 照週期鋪出來的，所以**GC 上的一個點就是大圖上那一整排點**。使用者只需要
在一張 205×73 的小圖上塗幾筆，而不是在 1000² 上標幾百個位置。

遮罩住在 **GC 的座標系**（不是螢幕座標）。這一條是這個元件唯一真正的不變量
—— 存進去的是「第幾個畫素」，縮放、視窗大小、螢幕 DPI 都不影響它。

⚠ **這裡不決定「缺陷長什麼樣」**，只決定「可能在哪」。塗到的每一個畫素都是
一個等權的候選，所以塗得大的那一塊被抽中的機會就高 —— 那正是「這一帶比較
容易出事」該有的行為，不必另外做權重（見 `make_lot_from_gc.sites_from_mask`）。
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme

__all__ = ["GcPaintView", "MODE_BRUSH", "MODE_RECT", "MODE_ERASE"]

MODE_BRUSH = "brush"
MODE_RECT = "rect"
MODE_ERASE = "erase"

#: 遮罩畫在影像上的顏色（半透明，底下的圖案要看得見 —— 使用者是**對著圖案**
#: 決定塗哪裡的，蓋掉它等於把唯一的線索拿走）。
_MASK_RGBA = (255, 64, 64, 110)


class GcPaintView(QWidget):
    """一張放大的 GC ＋ 一張塗得上去的遮罩。

    座標有兩個系統，而**混用它們是這種元件最典型的 bug**：

    * **影像座標** —— 遮罩、`mask()`、`sites` 全部用它。原點在 GC 左上角。
    * **視窗座標** —— 滑鼠事件用它。中間隔著一個縮放倍率與一段置中的留白。

    :meth:`to_image` 是唯一的換算，而它有一條測試逐點驗過來回一致。
    """

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._gc: Optional[np.ndarray] = None
        self._mask: Optional[np.ndarray] = None
        self._mode = MODE_BRUSH
        self._radius = 2
        self._last: Optional[Tuple[int, int]] = None
        self._rect_from: Optional[Tuple[int, int]] = None
        self._rect_to: Optional[Tuple[int, int]] = None
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(False)

    # -- 資料 ---------------------------------------------------------------
    def set_gc(self, gc: Optional[np.ndarray]) -> None:
        """換一張 GC。**遮罩跟著清掉** —— 換了圖案，畫在舊圖案上的位置沒有意義。"""
        self._gc = None if gc is None else np.ascontiguousarray(
            gc.astype(np.uint8))
        self._mask = (None if self._gc is None
                      else np.zeros(self._gc.shape, dtype=bool))
        self._rect_from = self._rect_to = None
        self.update()
        self.changed.emit()

    def mask(self) -> Optional[np.ndarray]:
        """目前塗到的地方（bool，GC 座標）。沒有 GC 的話回 ``None``。"""
        return None if self._mask is None else self._mask.copy()

    def set_mask(self, mask: Optional[np.ndarray]) -> bool:
        if self._gc is None or mask is None:
            return False
        m = np.asarray(mask).astype(bool)
        if m.shape != self._gc.shape:
            return False
        self._mask = m.copy()
        self.update()
        self.changed.emit()
        return True

    def clear(self) -> None:
        if self._mask is not None:
            self._mask[:] = False
            self.update()
            self.changed.emit()

    def painted_pixels(self) -> int:
        return 0 if self._mask is None else int(self._mask.sum())

    def seed_from_sites(self, sites: Iterable[Tuple[int, int]],
                        radius: int = 2) -> int:
        """把自動量到的 inner space 畫進遮罩，當**起點**。

        使用者要的是「自己畫」，但從零開始畫是一張白紙 —— 先把自動找到的那些
        放進去，他改的是一份已經接近的東西。回傳塗到幾個畫素。
        """
        if self._mask is None:
            return 0
        for x, y in sites:
            self._stamp(int(x), int(y), int(radius), True)
        self.update()
        self.changed.emit()
        return self.painted_pixels()

    # -- 工具 ---------------------------------------------------------------
    def set_mode(self, mode: str) -> None:
        self._mode = str(mode)

    def mode(self) -> str:
        return self._mode

    def set_radius(self, r: int) -> None:
        self._radius = max(0, int(r))

    def radius(self) -> int:
        return self._radius

    # -- 座標 ---------------------------------------------------------------
    def scale(self) -> float:
        """一個 GC 畫素在畫面上有幾個點（整數倍，最小 1）。

        **整數倍是刻意的**：GC 很小（實測 205×73），非整數倍會讓相鄰畫素的
        寬度一大一小，而使用者正在做的事是「對準那一條邊」。
        """
        if self._gc is None:
            return 1.0
        h, w = self._gc.shape
        return max(1.0, float(min(self.width() // max(1, w),
                                  self.height() // max(1, h))))

    def origin(self) -> Tuple[int, int]:
        """影像左上角畫在視窗的哪裡（置中留白）。"""
        if self._gc is None:
            return 0, 0
        h, w = self._gc.shape
        s = self.scale()
        return (int((self.width() - w * s) // 2),
                int((self.height() - h * s) // 2))

    def to_image(self, pos: QPoint) -> Optional[Tuple[int, int]]:
        """視窗座標 → 影像座標。落在圖外回 ``None``。"""
        if self._gc is None:
            return None
        h, w = self._gc.shape
        ox, oy = self.origin()
        s = self.scale()
        x = int((pos.x() - ox) // s)
        y = int((pos.y() - oy) // s)
        if 0 <= x < w and 0 <= y < h:
            return x, y
        return None

    # -- 畫 -----------------------------------------------------------------
    def _stamp(self, x: int, y: int, r: int, on: bool) -> None:
        if self._mask is None:
            return
        h, w = self._mask.shape
        x0, x1 = max(0, x - r), min(w, x + r + 1)
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        if x0 < x1 and y0 < y1:
            self._mask[y0:y1, x0:x1] = on

    def _stroke(self, a: Tuple[int, int], b: Tuple[int, int], on: bool) -> None:
        """從 a 畫到 b。**中間要補起來**。

        ⚠ 滑鼠事件是離散的：拖快一點，兩次事件之間可以隔十幾個畫素，只在
        事件的位置蓋章的話畫出來是**一串點**，而使用者以為自己畫了一條線。
        """
        (x0, y0), (x1, y1) = a, b
        n = max(abs(x1 - x0), abs(y1 - y0))
        for i in range(n + 1):
            t = 0.0 if n == 0 else i / float(n)
            self._stamp(int(round(x0 + (x1 - x0) * t)),
                        int(round(y0 + (y1 - y0) * t)), self._radius, on)

    def mousePressEvent(self, e) -> None:        # noqa: D102 - Qt hook
        p = self.to_image(e.position().toPoint())
        if p is None:
            return
        if self._mode == MODE_RECT:
            self._rect_from = self._rect_to = p
        else:
            self._last = p
            self._stroke(p, p, self._mode != MODE_ERASE)
            self.update()

    def mouseMoveEvent(self, e) -> None:         # noqa: D102 - Qt hook
        p = self.to_image(e.position().toPoint())
        if p is None:
            return
        if self._mode == MODE_RECT:
            if self._rect_from is not None:
                self._rect_to = p
                self.update()
        elif self._last is not None:
            self._stroke(self._last, p, self._mode != MODE_ERASE)
            self._last = p
            self.update()

    def mouseReleaseEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if self._mode == MODE_RECT and self._rect_from and self._rect_to:
            (x0, y0), (x1, y1) = self._rect_from, self._rect_to
            if self._mask is not None:
                self._mask[min(y0, y1):max(y0, y1) + 1,
                           min(x0, x1):max(x0, x1) + 1] = True
            self._rect_from = self._rect_to = None
        self._last = None
        self.update()
        self.changed.emit()

    # -- 繪製 ---------------------------------------------------------------
    def paintEvent(self, e) -> None:             # noqa: D102 - Qt hook
        p = QPainter(self)
        try:
            p.fillRect(self.rect(), QColor(theme.TOKENS["canvas_bg"]))
            if self._gc is None:
                p.setPen(QColor(theme.TOKENS["text_hint"]))
                p.drawText(self.rect(), Qt.AlignCenter,
                           "Paste a Golden Cell to draw on it")
                return
            h, w = self._gc.shape
            s = self.scale()
            ox, oy = self.origin()
            target = QRect(ox, oy, int(w * s), int(h * s))

            img = QImage(self._gc.data, w, h, w, QImage.Format_Grayscale8)
            # **不要平滑** —— 使用者在對準畫素邊界，插值會把邊界變成一片漸層。
            p.setRenderHint(QPainter.SmoothPixmapTransform, False)
            p.drawPixmap(target, QPixmap.fromImage(img.copy()))

            if self._mask is not None and self._mask.any():
                rgba = np.zeros((h, w, 4), dtype=np.uint8)
                rgba[self._mask] = _MASK_RGBA
                over = QImage(rgba.data, w, h, 4 * w, QImage.Format_RGBA8888)
                p.drawPixmap(target, QPixmap.fromImage(over.copy()))

            if self._rect_from and self._rect_to:
                (x0, y0), (x1, y1) = self._rect_from, self._rect_to
                p.setPen(QPen(QColor(theme.TOKENS["accent"]), 1, Qt.DashLine))
                p.drawRect(QRect(int(ox + min(x0, x1) * s),
                                 int(oy + min(y0, y1) * s),
                                 int((abs(x1 - x0) + 1) * s),
                                 int((abs(y1 - y0) + 1) * s)))
        finally:
            # 鐵則 7 的 UI 版：painter 一定要收尾（見 `PITFALLS.md` 第一列）
            p.end()

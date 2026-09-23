# 區域之間的細線 — authored 2026-09-09 (F100 v3 收尾).
"""`HairlineSplitter`：把手 **5px 抓得到、中間 1px 看得見**的 `QSplitter`。

為什麼不是 QSS：F100 v2 用 `QSplitter::handle { width: 5px; margin: 0 2px }`
想做同一件事，結果是**整條把手塗成分隔色** —— 直向 5px、橫向 9px 的實心灰條
（使用者：「分隔線看起來又怪怪的」）。離線探針量過四種寫法（`margin`、
`border-left/right`、四邊 `border`、硬邊漸層）：Qt 算把手粗細時不分方向、
畫的時候才分，`:horizontal` 與 `:vertical` 的尺寸規則互相干擾，而漸層會被
反鋸齒糊掉。沒有一種在兩個方向都給出「5px／1px」。

所以把手自己畫：`paintEvent` 在正中間畫一條 1px 的 `divider`，滑過時換成
`border_hover`。顏色讀的是 `theme.TOKENS`（換膚時整份會換），畫的時候才取。
QSS 那一邊只剩 `background: transparent` —— 尺寸與顏色都不在那裡。

`tests/test_ui_splitters.py` 真的開一支、抓圖、數像素：把手 5px、分隔色正好
1px、兩個方向、兩個主題。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSplitter, QSplitterHandle

from . import theme

__all__ = ["HairlineSplitter", "HANDLE_PX"]

#: 抓得到的寬度。1px 的線抓不到；5px 是「不會誤抓、也不會找不到」的最小值。
HANDLE_PX = 5


class _HairlineHandle(QSplitterHandle):
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._hover = False
        self.setAttribute(Qt.WA_Hover, True)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.TOKENS["bg_page"]))
        ink = QColor(theme.TOKENS["border_hover" if self._hover else "divider"])
        r = self.rect()
        if self.orientation() == Qt.Horizontal:      # 直的一條線（左右分欄）
            x = r.left() + r.width() // 2
            p.fillRect(x, r.top(), 1, r.height(), ink)
        else:                                        # 橫的一條線（上下分層）
            y = r.top() + r.height() // 2
            p.fillRect(r.left(), y, r.width(), 1, ink)
        p.end()


class HairlineSplitter(QSplitter):
    """跟 `QSplitter` 一模一樣，只有把手長得不一樣。建構子簽名照 Qt。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setHandleWidth(HANDLE_PX)

    def createHandle(self):
        return _HairlineHandle(self.orientation(), self)

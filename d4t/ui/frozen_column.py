# d4t Studio：第一欄不跟著橫捲走 — authored 2026-09-20 (F117 I15).
"""**表格橫捲到第五欄的時候，「這是哪一顆」就不見了。**

走查（F117 I15）記的是 Results 的表：表頭本來就固定（`QHeaderView` 自己會），
但 ``defect`` 那一欄會跟著捲出畫面。而一列數字沒有 id 就只是一列數字 ——
使用者正在做的事（「這一顆為什麼判成這樣」）在那一刻斷掉了。

做法：Qt 沒有內建的凍結欄
-------------------------
標準解法是**疊第二個 view 上去**（Qt 官方的 frozen-column 範例）：它跟主表
**共用同一個 model 與同一個 selection model**，只顯示第 0 欄，蓋在主表左邊。

⚠ **共用 selection model 是關鍵的那一半**：各自一份的話，點左邊那一欄選到的
列跟右邊亮起來的不是同一列 —— 而那是一個「看起來只是有點怪」的錯。

⚠ 排序也是共用的（同一個 model），所以左邊永遠跟右邊對得起來。

⚠ **這一支不碰欄寬以外的任何樣式**：主表的交替列色、選取色、delegate 都是
它自己的；疊上去那一個只是同一份資料的第二個視窗。
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

__all__ = ["FrozenColumn", "attach"]


class FrozenColumn(QTableView):
    """蓋在 ``host`` 左邊、只顯示第 ``column`` 欄的第二個 view。

    ``host`` 自己維持不變 —— 它連知道都不必知道有這一層（除了把那一欄的
    位置讓出來，見 :meth:`sync`）。
    """

    def __init__(self, host: QTableView, column: int = 0) -> None:
        super().__init__(host)
        self._host = host
        self._column = int(column)

        self.setModel(host.model())
        self.setSelectionModel(host.selectionModel())
        self.setFocusPolicy(Qt.NoFocus)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(host.alternatingRowColors())
        self.setShowGrid(host.showGrid())
        self.setWordWrap(False)
        # **一條看得見的界線**：沒有它，凍結的那一欄看起來只是「捲不動的
        # 第一欄」，而使用者會以為表壞了。
        self.setFrameShape(QTableView.NoFrame)
        self.setStyleSheet("QTableView{border-right:1px solid palette(mid);}")
        self.setItemDelegate(host.itemDelegate())

        # 左右兩邊的**直向捲動要綁在一起**（各捲各的就完全對不上）。
        self.verticalScrollBar().valueChanged.connect(
            host.verticalScrollBar().setValue)
        host.verticalScrollBar().valueChanged.connect(
            self.verticalScrollBar().setValue)
        host.horizontalHeader().sectionResized.connect(self._on_resized)
        host.verticalHeader().sectionResized.connect(self._on_row_resized)

        self.setVerticalScrollMode(host.verticalScrollMode())
        self.raise_()
        self.sync()

    # ---- 對外 -------------------------------------------------------------
    def column(self) -> int:
        return self._column

    def sync(self) -> None:
        """跟主表對齊：只留那一欄、寬度與列高照抄、擺到左邊。

        ⚠ **主表那一欄照樣留著**（不 `setColumnHidden`）：藏起來的話它的寬度
        就不再參與版面，而右邊的內容會往左滑到凍結欄底下。留著＋蓋住是
        Qt 官方那個範例的做法，理由一樣。
        """
        host = self._host
        model = host.model()
        if model is None:
            return
        if self.model() is not model:                  # 換過 model
            self.setModel(model)
            self.setSelectionModel(host.selectionModel())
        for col in range(model.columnCount()):
            self.setColumnHidden(col, col != self._column)
        self.setColumnWidth(self._column, host.columnWidth(self._column))
        self.verticalHeader().setDefaultSectionSize(
            host.verticalHeader().defaultSectionSize())
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self._place()
        self.setVisible(not host.isColumnHidden(self._column))

    # ---- 內部 -------------------------------------------------------------
    def _place(self) -> None:
        host = self._host
        width = host.columnWidth(self._column)
        top = host.horizontalHeader().height() if \
            host.horizontalHeader().isVisible() else 0
        frame = host.frameWidth()
        self.setGeometry(host.verticalHeader().width() + frame, frame,
                         width, host.viewport().height() + top)

    def _on_resized(self, index: int, _old: int, new: int) -> None:
        if int(index) == self._column:
            self.setColumnWidth(self._column, int(new))
            self._place()

    def _on_row_resized(self, _index: int, _old: int, new: int) -> None:
        self.verticalHeader().setDefaultSectionSize(int(new))


def attach(host: QTableView, column: int = 0) -> FrozenColumn:
    """把凍結欄接到一個既有的表上，並讓它跟著主表一起重排。

    ⚠ 接法是**包住 `resizeEvent`** 而不是叫呼叫端記得呼叫 `sync()` ——
    「記得呼叫」那一版會在某一條沒人想到的路徑上漏掉，而症狀是凍結的那一欄
    停在錯的寬度上，看起來像畫面裂了。
    """
    frozen = FrozenColumn(host, column)
    original = host.resizeEvent

    def resized(event: Any) -> None:
        original(event)
        frozen.sync()

    host.resizeEvent = resized        # type: ignore[assignment]
    return frozen

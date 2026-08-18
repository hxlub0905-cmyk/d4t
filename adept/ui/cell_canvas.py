# ADEPT Studio — 在 Golden Cell 上標區域的畫布 (F11 Region-1).
"""``CellCanvas`` —— 一格 cell 放大、鋪成一片，區域的框畫在上面、拖得動。

為什麼是「畫」而不是「填四個數字」
----------------------------------
框的座標是**相對於一格 cell** 的（0–1），不是相對於 patch。那件事沒有任何一句
help 講得清楚 —— 使用者看到的是四個 0 到 1 的數字，而它們相對的那張圖以前只在
建模板的對話框裡出現過一次，按下「Use this template」之後就再也看不到了
（F11 §3.3.1 第 2 項）。**參照物不在場**才是那四個數字難用的原因。

為什麼可以用滑鼠拖（而在 patch 上不行）
---------------------------------------
使用者否決過「框可以用滑鼠拖」，理由是「我要跑的是**每一顆** defect」——
在一顆 patch 上拖到好看，第 50 顆可能整個偏掉。**但 cell 不是一顆 defect**：
它是整批共用的同一個模板物件，在它上面標框跟拖四支滑桿產出的是同一組數字。
所以這裡拖的是尺規，不是猜測（同 Enhance-UI-A 的分界）。

鋪成一片，而且畫出一顆 patch 有多大
-----------------------------------
兩件事在畫面上必須是真的，否則使用者會標出一組「看起來對、跑起來錯」的框：

* **cell 會重複**。GC 的原點錨在最強的上升邊，所以要框的結構常常橫跨接縫 ——
  只畫一格的話，那個框看起來像是被切斷了。鋪成一片就看得出來它是連續的。
* **一顆 defect 只看得到一個窗**。模板通常比 patch 大，所以標在別處的區域
  在某些顆上根本不在。畫一個 patch 大小的框，那件事就不必等跑完才發現。

四支工具（F11 Region-1 第二輪，使用者定調）
--------------------------------------------
「定義 ROI 方式分三種：add（又分 click add 跟 multi add）／drag／跟點一顆一顆
pixel 的」。第四支我取名 **paint** —— 畫出來的東西是**像素**不是筆觸，所以圖示
是幾格點亮的方格，不是筆刷。點出來的像素在放手時併成**逐列的矩形**
（run-length），因為區域的資料模型是矩形；那也正是 §3.3.2 答案 B 的做法。

座標一律是**整數 cell 像素**
----------------------------
使用者：「單位是 pixel 但我想要取整數（pixel 是整數才合理吧）」。對 —— 半個
像素的框沒有對應的東西可以量，而它會讓 recipe 的字串長出 `0.3167` 這種讀不懂的
數字。所以每一次新增／搬移／改大小都吸附到整數 cell 像素，寬高至少 1 px。

一次長一整片（multi add）
-------------------------
整排 EPI 一根一根拉，第 20 根的間距已經歪了 —— 而歪掉的框在畫面上看不太出來，
在數字上看得出來。所以有一個**陣列工具**：點兩個錨點（左上、右下那一格的
中心）、給框的大小與數量，中間的間距由端點算出來（``cellrois.array_boxes``）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from adept.core.pipeline.cellrois import array_boxes, array_pitch

from .theme import TOKENS
from .widgets import _qimage_from_uint8

__all__ = ["CellCanvas", "REGION_COLORS", "region_color"]

#: 區域的顏色（依清單順序輪流）。要在深色的 SEM 影像上看得見，所以都偏亮。
#: 不用 ``accent`` 那一組：那是「選取／焦點」的語彙，而這裡的顏色講的是
#: **哪一個區域**，兩件事混在一起使用者會以為藍色的那個是被選中的。
REGION_COLORS = ("#5fd0a0", "#f0b429", "#7aa7ff", "#f07aa7",
                 "#9ad14b", "#d18ef0", "#4bd1c8", "#f08a5f")

#: 拖曳把手的**半徑**（畫面像素）。使用者回報原本的 7 太大很醜 —— 那時候一個
#: 把手是 14×14，在一個 20 px 寬的框上八個把手幾乎把框蓋滿。3 是「抓得到、
#: 但不搶戲」：命中判定另外放寬到 :data:`_GRAB`，所以縮小不會變難抓。
_HANDLE = 3.0
#: 命中判定的半徑 —— 比畫出來的把手大，手不必那麼準。
_GRAB = 7.0

#: 四支工具（使用者定調）。``drag`` 是預設。
TOOL_CURSOR = "cursor"
TOOL_DRAG, TOOL_CLICK, TOOL_ARRAY, TOOL_PAINT = "drag", "click", "array", "paint"
TOOLS = (TOOL_CURSOR, TOOL_DRAG, TOOL_CLICK, TOOL_ARRAY, TOOL_PAINT)

#: 對齊：把選起來的框對到選取範圍的哪一邊。
ALIGNMENTS = ("left", "center", "right", "top", "middle", "bottom")

#: 復原最多記幾步。整份區域的快照很小（幾十個 tuple），記深一點不痛。
UNDO_DEPTH = 40

#: 新區域的預設名（ROI1、ROI2…）—— 使用者的原話就是這個命名。
NAME_STEM = "ROI"


def region_color(index: int) -> QColor:
    return QColor(REGION_COLORS[int(index) % len(REGION_COLORS)])


class CellCanvas(QWidget):
    """一格 cell + 上面的框；可縮放、可平移、可拖拉增刪。

    座標有三層，弄混就會畫錯地方，所以命名一律講清楚：

    * ``norm``  —— 相對於**一格**的 0–1（存進 recipe 的那一種）
    * ``cellpx``—— 一格的像素座標（0…cell_w）
    * ``view``  —— widget 上的像素座標
    """

    #: 使用者改了框（拖曳、新增、刪除）——(region_index, boxes)
    boxes_changed = Signal(int, list)
    #: 選取的框換了（region_index, box_index；box_index = -1 表示沒有）
    selection_changed = Signal(int, int)
    #: 陣列工具的錨點狀態變了（已經點了幾個）
    array_anchors_changed = Signal(int)
    #: 區域**清單本身**變了（自動開了一個新區域）—— 側欄要重畫
    regions_changed = Signal()
    #: 工具換了（畫布自己也會換，例如陣列做完就回到上一支）
    tool_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._cell: Optional[np.ndarray] = None
        #: [(name, [box, …]), …] —— 跟 ``cellrois`` 同一個形狀
        self._regions: List[Tuple[str, List[Tuple[float, float, float, float]]]] = []
        self._current = 0
        #: 選起來的框，每一個是 ``(區域, 框)``（F11 Region-1 第六輪）。
        #:
        #: 為什麼**跨區域**：使用者要「不同 region 對齊」—— EPI 那一排跟 MG 那
        #: 一排要切齊的時候，那兩排本來就在兩個區域裡。選取如果鎖在目前這個
        #: 區域，對齊工具就永遠只對得起同一個區域裡的東西。
        self._selection: List[Tuple[int, int]] = []
        self._undo: List[Any] = []
        self._zoom = 0.0            # 0 = 還沒算過（第一次 paint 時 fit）
        self._pan = QPointF(0.0, 0.0)
        self._tile = True
        self._patch_size: Optional[Tuple[int, int]] = None

        self._drag: Optional[Dict[str, Any]] = None
        self._array: Optional[Dict[str, Any]] = None
        self._tool = TOOL_DRAG
        #: click / array 工具用的框大小（cell 像素）
        self._box_px: Tuple[int, int] = (8, 8)
        #: 陣列工具長幾個（橫、直）
        self._array_n: Tuple[int, int] = (4, 1)
        #: paint 這一筆點到的 cell 像素（放手才併成矩形）
        self._paint: Optional[set] = None
        #: 游標現在在哪（normalized）—— click / array 工具的**下一個框**畫在這裡
        self._hover: Optional[Tuple[float, float]] = None

        self.setMinimumSize(320, 260)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

    # ---- 內容 ---------------------------------------------------------------
    def set_cell(self, cell: Optional[np.ndarray]) -> None:
        self._cell = None if cell is None else np.asarray(cell)
        self._zoom = 0.0                       # 換了模板就重新 fit
        self._pan = QPointF(0.0, 0.0)
        self.update()

    def has_cell(self) -> bool:
        return self._cell is not None and self._cell.size > 0

    def cell_shape(self) -> Tuple[int, int]:
        if not self.has_cell():
            return (1, 1)
        h, w = self._cell.shape[:2]
        return (int(h), int(w))

    def set_regions(self, regions) -> None:
        self._regions = [(str(n), [tuple(float(v) for v in b) for b in boxes])
                         for n, boxes in regions]
        if self._current >= len(self._regions):
            self._current = max(0, len(self._regions) - 1)
        self._selection = []
        self.update()

    def regions(self):
        return [(n, list(b)) for n, b in self._regions]

    def set_current_region(self, index: int) -> None:
        self._current = max(0, int(index))
        self._selection = []
        self.selection_changed.emit(self._current, -1)
        self.update()

    def current_region(self) -> int:
        return self._current

    def selected_box(self) -> int:
        """**目前區域裡**主要選取的那一個（−1 = 沒有）—— 數字表跟著它捲。"""
        for ri, bi in reversed(self._selection):
            if ri == self._current:
                return bi
        return -1

    def selection(self) -> List[Tuple[int, int]]:
        """選起來的每一個 ``(區域, 框)``。"""
        return list(self._selection)

    def handles_visible(self) -> bool:
        """現在畫不畫那八個把手。

        **只有選單一個框的時候才畫**（使用者：「每次 multi add 增加當下都會全框
        很醜」）。選了一整排的時候把手也沒有意義 —— 一個把手拉不動二十個框，
        而「選中了」用外框加粗就講完了。
        """
        return len(self._selection) == 1

    def selection_here(self) -> List[int]:
        """選起來的框裡，屬於**目前區域**的那幾個。"""
        return [bi for ri, bi in self._selection if ri == self._current]

    def set_selection(self, items) -> None:
        """吃 ``(區域, 框)`` 或單純的框索引（後者當成目前區域）。"""
        picked: List[Tuple[int, int]] = []
        for it in items:
            ri, bi = it if isinstance(it, (tuple, list)) else (self._current, it)
            ri, bi = int(ri), int(bi)
            if 0 <= ri < len(self._regions) and 0 <= bi < len(self._regions[ri][1]):
                if (ri, bi) not in picked:
                    picked.append((ri, bi))
        self._selection = picked
        self.selection_changed.emit(self._current, self.selected_box())
        self.update()

    def select_all(self) -> None:
        """**每一個區域**的每一個框 —— 對齊要跨區域才用得上（見 `_selection`）。"""
        self.set_selection([(ri, bi) for ri, (_n, boxes) in enumerate(self._regions)
                            for bi in range(len(boxes))])

    def box_at(self, ri: int, bi: int):
        if 0 <= ri < len(self._regions) and 0 <= bi < len(self._regions[ri][1]):
            return self._regions[ri][1][bi]
        return None

    def put_box(self, ri: int, bi: int, box) -> None:
        if 0 <= ri < len(self._regions) and 0 <= bi < len(self._regions[ri][1]):
            self._regions[ri][1][bi] = tuple(float(v) for v in box)

    def set_patch_size(self, size: Optional[Tuple[int, int]]) -> None:
        """一顆 defect 看得到多大（``(h, w)`` 像素）；``None`` = 不知道就不畫。

        **不知道就不畫**是重點：畫一個猜出來的窗，比不畫更糟 —— 使用者會照著
        那個窗決定哪些區域標得到。
        """
        self._patch_size = None if size is None else (int(size[0]), int(size[1]))
        self.update()

    def set_tiled(self, on: bool) -> None:
        self._tile = bool(on)
        self.update()

    def tiled(self) -> bool:
        return self._tile

    # ---- 工具 ---------------------------------------------------------------
    def tool(self) -> str:
        return self._tool

    def set_tool(self, name: str) -> None:
        """換一支工具。離開陣列模式時把還沒確認的錨點丟掉（不要偷偷留著）。"""
        name = str(name) if str(name) in TOOLS else TOOL_DRAG
        self._hover = None
        if name != TOOL_ARRAY and self._array is not None:
            self._array = None
            self.array_anchors_changed.emit(0)
        self._tool = name
        self._paint = None
        # 選了陣列工具就等於**開始**了一次（錨點是空的）。不這樣的話
        # ``array_active()`` 在第一次點擊之前是 False，而畫面上那支工具已經
        # 亮著 —— 狀態要跟畫面一致。
        if name == TOOL_ARRAY and self._array is None:
            self.start_array()
        self.setCursor(Qt.ArrowCursor if name in (TOOL_CURSOR, TOOL_DRAG)
                       else Qt.CrossCursor)
        self.tool_changed.emit(name)
        self.update()

    def set_box_size(self, w_px: int, h_px: int) -> None:
        """click / array 工具長出來的框有多大（cell 像素）。"""
        self._box_px = (max(1, int(w_px)), max(1, int(h_px)))
        if self._array is not None:
            self._array.update(w=self._box_px[0] / float(self.cell_shape()[1]),
                               h=self._box_px[1] / float(self.cell_shape()[0]))
        self.update()

    def box_size(self) -> Tuple[int, int]:
        return self._box_px

    # ---- 整數 cell 像素 -----------------------------------------------------
    def snap(self, box) -> Tuple[float, float, float, float]:
        """吸附到整數 cell 像素（寬高至少 1 px）。

        半個像素的框沒有對應的東西可以量，而它會讓 recipe 長出 ``0.3167``
        這種讀不懂的數字（使用者：「pixel 是整數才合理吧」）。
        """
        h, w = self.cell_shape()
        x, y, bw, bh = (float(v) for v in box)
        px, py = round(x * w), round(y * h)
        pw, ph = max(1, round(bw * w)), max(1, round(bh * h))
        return (px / float(w), py / float(h), pw / float(w), ph / float(h))

    def to_px(self, box) -> Tuple[int, int, int, int]:
        """框 → **整數** cell 像素（摘要、對齊判斷用；小數請用 :meth:`to_px_f`）。"""
        return tuple(int(round(v)) for v in self.to_px_f(box))

    def to_px_f(self, box) -> Tuple[float, float, float, float]:
        """框 → cell 像素，**小數照留**。

        表格顯示的就是這一份：陣列工具的位置刻意是小數，硬顯示成整數的話
        29.5 會變成一排 29／30 交錯，讀起來像「不穩定」—— 而那是表格說謊，
        不是值在跳（使用者 2026-08-18 回報的那件事）。
        """
        h, w = self.cell_shape()
        x, y, bw, bh = (float(v) for v in box)
        return (x * w, y * h, max(1.0, bw * w), max(1.0, bh * h))

    def from_px(self, box) -> Tuple[float, float, float, float]:
        """cell 像素（可以是小數）→ 相對於一格的比例。"""
        h, w = self.cell_shape()
        x, y, bw, bh = (float(v) for v in box)
        return (x / w, y / h, max(1.0, bw) / w, max(1.0, bh) / h)

    # ---- 縮放 ---------------------------------------------------------------
    def zoom(self) -> float:
        return self._zoom if self._zoom > 0 else self._fit_zoom()

    def set_zoom(self, z: float) -> None:
        self._zoom = max(0.05, min(64.0, float(z)))
        self.update()

    def zoom_by(self, factor: float) -> None:
        self.set_zoom(self.zoom() * float(factor))

    def fit(self) -> None:
        self._zoom = 0.0
        self._pan = QPointF(0.0, 0.0)
        self.update()

    def _fit_zoom(self) -> float:
        h, w = self.cell_shape()
        # 鋪成一片時留一格的邊，看得到接縫
        span_w = w * (3.0 if self._tile else 1.0)
        span_h = h * (3.0 if self._tile else 1.0)
        return max(0.05, min(self.width() / span_w, self.height() / span_h))

    # ---- 座標 ---------------------------------------------------------------
    def _origin(self) -> QPointF:
        """一格 cell 的左上角在 widget 上的位置。"""
        h, w = self.cell_shape()
        z = self.zoom()
        return QPointF(self.width() / 2.0 - w * z / 2.0 + self._pan.x(),
                       self.height() / 2.0 - h * z / 2.0 + self._pan.y())

    def norm_to_view(self, nx: float, ny: float) -> QPointF:
        h, w = self.cell_shape()
        z = self.zoom()
        o = self._origin()
        return QPointF(o.x() + nx * w * z, o.y() + ny * h * z)

    def view_to_norm(self, pt: QPointF) -> Tuple[float, float]:
        h, w = self.cell_shape()
        z = self.zoom()
        o = self._origin()
        return ((pt.x() - o.x()) / (w * z), (pt.y() - o.y()) / (h * z))

    def box_rect(self, box) -> QRectF:
        x, y, bw, bh = box
        a = self.norm_to_view(x, y)
        b = self.norm_to_view(x + bw, y + bh)
        return QRectF(a, b).normalized()

    # ---- 框的編輯 -----------------------------------------------------------
    def _boxes(self) -> List[Tuple[float, float, float, float]]:
        if 0 <= self._current < len(self._regions):
            return self._regions[self._current][1]
        return []

    def _commit(self) -> None:
        self.boxes_changed.emit(self._current, list(self._boxes()))
        self.update()

    def ensure_region(self) -> int:
        """一定要有一個地方可以放框；沒有就開一個，回傳它的索引。

        為什麼不是「沒有區域就拒絕」（這是使用者回報的第 1 個 bug）：從 Studio
        打開一張**已經有模板、還沒有區域**的卡時，區域清單是空的 —— 而那時候
        `add_box` / `add_boxes` 直接回 −1／0，於是**畫出來的框跟按下 Add them
        都安靜地什麼都沒發生**。沒有任何訊息，因為程式覺得自己沒事。

        「使用者做了一個明確的動作」與「沒有容器可以裝」之間，該讓步的是後者。
        """
        if 0 <= self._current < len(self._regions):
            return self._current
        taken = {n for n, _b in self._regions}
        i = 1
        while "%s%d" % (NAME_STEM, i) in taken:
            i += 1
        self._regions.append(("%s%d" % (NAME_STEM, i), []))
        self._current = len(self._regions) - 1
        self.regions_changed.emit()
        return self._current

    def add_box(self, box) -> int:
        """加一個框到目前的區域，回傳它的索引。"""
        self.ensure_region()
        self._snapshot()
        self._boxes().append(self.snap(box))
        self.set_selection([(self._current, len(self._boxes()) - 1)])
        self._commit()
        return len(self._boxes()) - 1

    def add_boxes(self, boxes, snap: bool = True) -> int:
        """一次加一整片（陣列／筆刷工具用）；回傳實際加了幾個。

        ``snap=False`` 給陣列工具用：它算出來的位置**刻意是小數**（見
        ``cellrois.array_boxes`` 的說明）。筆刷點的是像素，所以它照樣吸附。
        """
        added = [self.snap(b) if snap else tuple(float(v) for v in b)
                 for b in boxes]
        if not added:
            return 0
        self.ensure_region()
        self._snapshot()
        self._boxes().extend(added)
        # **加完不要全選**（使用者：「每次 multi add 增加當下都會全框很醜」）。
        # 剛長出來的一整排本來就看得到，再把每一個都套上把手只是把畫面塞滿。
        self.set_selection([])
        self._commit()
        return len(added)

    def delete_selected(self) -> bool:
        """刪掉**每一個**選起來的框（可以跨區域）。"""
        drop = sorted(self._selection, reverse=True)
        if not drop:
            return False
        self._snapshot()
        for ri, bi in drop:                     # 由後往前，索引才不會被洗掉
            if 0 <= ri < len(self._regions) and 0 <= bi < len(self._regions[ri][1]):
                self._regions[ri][1].pop(bi)
        self.set_selection([])
        self.regions_changed.emit()
        self._commit()
        return True

    def select_box(self, index: int, add: bool = False,
                   region: Optional[int] = None) -> None:
        """選一個框；``add=True`` 是 Ctrl＋點（加選／取消選）。"""
        if index < 0:
            self.set_selection([])
            return
        key = (self._current if region is None else int(region), int(index))
        if not add:
            self.set_selection([key])
            return
        picked = list(self._selection)
        if key in picked:
            picked.remove(key)
        else:
            picked.append(key)
        self.set_selection(picked)

    def replace_box(self, index: int, box, snap: bool = True) -> None:
        boxes = self._boxes()
        if 0 <= index < len(boxes):
            self._snapshot()
            boxes[index] = (self.snap(box) if snap
                            else tuple(float(v) for v in box))
            self._commit()

    # ---- 對齊（選起來的那幾個）---------------------------------------------
    def align_selection(self, how: str) -> int:
        """把選起來的框對到**選取範圍**的某一邊。回傳搬動了幾個。

        基準是選取範圍的外框，不是「第一個選的那個」—— 使用者是先框一整排再按
        對齊，那時候「第一個」是哪一個他自己也不知道（那會變成一個看不見的規則）。
        """
        how = str(how)
        picked = [k for k in self._selection if self.box_at(*k) is not None]
        if how not in ALIGNMENTS or len(picked) < 2:
            return 0

        xs = [self.box_at(*k) for k in picked]
        left = min(b[0] for b in xs)
        right = max(b[0] + b[2] for b in xs)
        top = min(b[1] for b in xs)
        bottom = max(b[1] + b[3] for b in xs)

        self._snapshot()
        for k in picked:
            x, y, w, h = self.box_at(*k)
            if how == "left":
                x = left
            elif how == "right":
                x = right - w
            elif how == "center":
                x = (left + right) / 2.0 - w / 2.0
            elif how == "top":
                y = top
            elif how == "bottom":
                y = bottom - h
            elif how == "middle":
                y = (top + bottom) / 2.0 - h / 2.0
            self.put_box(k[0], k[1], self.snap((x, y, w, h)))
        self._commit()
        return len(picked)

    # ---- 復原 ---------------------------------------------------------------
    def _snapshot(self) -> None:
        """改動之前存一份區域的快照（整份，不是差異 —— 幾十個 tuple 而已）。"""
        self._undo.append([(n, list(b)) for n, b in self._regions])
        if len(self._undo) > UNDO_DEPTH:
            self._undo.pop(0)

    def can_undo(self) -> bool:
        return bool(self._undo)

    def undo(self) -> bool:
        """退回上一步。畫錯一個框要能一鍵回去 —— 不然使用者不敢用工具。"""
        if not self._undo:
            return False
        self.set_regions(self._undo.pop())
        self.regions_changed.emit()
        self.boxes_changed.emit(self._current, list(self._boxes()))
        self.update()
        return True

    # ---- 陣列工具（multi add）----------------------------------------------
    def set_array_counts(self, nx: int, ny: int) -> None:
        self._array_n = (max(1, int(nx)), max(1, int(ny)))
        if self._array is not None:
            self._array.update(nx=self._array_n[0], ny=self._array_n[1])
            self.update()

    def array_counts(self) -> Tuple[int, int]:
        return self._array_n

    def start_array(self) -> None:
        """進入陣列模式：接下來兩次點擊是左上／右下那一格的**中心**。"""
        w, h, nx, ny = self._array_defaults()
        self._array = {"w": w, "h": h, "nx": nx, "ny": ny, "anchors": []}
        self._drag = None
        self.array_anchors_changed.emit(0)
        self.update()

    def cancel_array(self) -> None:
        self._array = None
        self.array_anchors_changed.emit(0)
        self.update()

    def array_active(self) -> bool:
        return self._array is not None

    def array_anchor_count(self) -> int:
        return 0 if self._array is None else len(self._array["anchors"])

    def array_preview(self) -> List[Tuple[float, float, float, float]]:
        """目前錨點下會長出來的那一片（錨點不足兩個就只有第一個框）。"""
        if self._array is None or not self._array["anchors"]:
            return []
        a = self._array["anchors"]
        # 只放了第一個錨點時，**游標就是暫時的第二個** —— 使用者要在按下去之前
        # 看到整片（含中間那些），而不是只看到左上角那一個。
        if len(a) == 1 and self._hover is not None:
            a = [a[0], self._hover]
        first = a[0]
        last = a[1] if len(a) > 1 else a[0]
        h, w = self.cell_shape()
        # 位置**不取整**（見 cellrois.array_boxes）：pitch 是設計常數，很少剛好
        # 是整數 px，先取整會讓第 9 個框偏 4 px 而飄離結構。取整發生在落到 patch
        # 上的那一刻（roi_boxes_in_patch），那時候才知道這一顆的相位。
        return array_boxes(first, last, self._array["w"], self._array["h"],
                           self._array["nx"] if len(a) > 1 else 1,
                           self._array["ny"] if len(a) > 1 else 1,
                           cell_size=(w, h))

    def array_provisional(self) -> bool:
        """第二個錨點還是**游標的位置**（還沒按下去）嗎。"""
        return (self._array is not None
                and len(self._array["anchors"]) == 1
                and self._hover is not None)

    def array_pitch(self) -> Tuple[float, float]:
        """這一片實際用的間距（cell 像素，**可以是小數**）—— 提示列要講出來。"""
        if self._array is None or not self._array["anchors"]:
            return (0.0, 0.0)
        h, w = self.cell_shape()
        a = self._array["anchors"]
        if len(a) == 1 and self._hover is not None:
            a = [a[0], self._hover]
        if len(a) < 2:
            return (0.0, 0.0)
        return array_pitch(a[0], a[1], self._array["nx"],
                           self._array["ny"], (w, h))

    def commit_array(self) -> int:
        """把預覽的那一片真的加進區域，**留在陣列模式**（錨點清掉）。

        留著是因為使用者通常要標好幾排（EPI 一排、MG 一排）—— 每加一排就被踢回
        上一支工具的話，每一排都要多按一次「Start」。
        """
        boxes = self.array_preview()
        if self._array is not None:
            self._array["anchors"] = []
        self.array_anchors_changed.emit(0)
        if not boxes:
            self.update()
            return 0
        return self.add_boxes(boxes, snap=False)

    def place_array_anchor(self, nx: float, ny: float) -> int:
        """放一個錨點（第三次點擊會重新從第一個開始）。回傳現在有幾個。"""
        if self._array is None:
            self.start_array()
        a = self._array["anchors"]
        if len(a) >= 2:
            a.clear()
        a.append((float(nx), float(ny)))
        self.array_anchors_changed.emit(len(a))
        self.update()
        return len(a)

    # ---- 滑鼠 ---------------------------------------------------------------
    def _hit(self, pt: QPointF):
        """``((區域, 框), 把手)``；把手是 ``""``（框身）或 ``"nw"``… 之一。

        **目前這個區域先接**，其他區域才接得到 —— 兩個區域的框疊在一起的時候，
        使用者正在編的那一個要優先，否則點下去會跳到另一個區域。
        """
        order = ([self._current]
                 + [i for i in range(len(self._regions)) if i != self._current])
        for ri in order:
            boxes = self._regions[ri][1] if ri < len(self._regions) else []
            for bi in range(len(boxes) - 1, -1, -1):   # 上層的先接
                r = self.box_rect(boxes[bi])
                if (ri, bi) in self._selection and len(self._selection) == 1:
                    for name, corner in self._handles(r, _GRAB).items():
                        if corner.contains(pt):
                            return (ri, bi), name
                if r.contains(pt):
                    return (ri, bi), ""
        return None, ""

    @staticmethod
    def _handles(r: QRectF, d: float = _HANDLE) -> Dict[str, QRectF]:
        pts = {"nw": r.topLeft(), "ne": r.topRight(),
               "sw": r.bottomLeft(), "se": r.bottomRight(),
               "n": QPointF(r.center().x(), r.top()),
               "s": QPointF(r.center().x(), r.bottom()),
               "w": QPointF(r.left(), r.center().y()),
               "e": QPointF(r.right(), r.center().y())}
        return {k: QRectF(p.x() - d, p.y() - d, d * 2, d * 2)
                for k, p in pts.items()}

    def mousePressEvent(self, e) -> None:              # noqa: D102 - Qt hook
        pt = _pos(e)
        # 點了畫布就把鍵盤焦點抓過來 —— 不然按了側欄的鈕之後，方向鍵與
        # Del／Ctrl+Z 全部沒反應，而畫面上看起來框明明還選著。
        self.setFocus(Qt.MouseFocusReason)
        # 右鍵／中鍵／Shift+左鍵都是平移（使用者要的是右鍵；另外兩個留著，
        # 它們是既有的習慣，拿掉只會讓現在會用的人踩空）
        if e.button() in (Qt.RightButton, Qt.MiddleButton) or (
                e.button() == Qt.LeftButton and e.modifiers() & Qt.ShiftModifier):
            self._drag = {"mode": "pan", "from": pt, "pan": QPointF(self._pan)}
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() != Qt.LeftButton:
            return

        if self._tool == TOOL_ARRAY:
            nx, ny = self.view_to_norm(pt)
            self.place_array_anchor(nx, ny)
            return

        if self._tool == TOOL_PAINT:
            self._paint = set()
            self._paint_at(pt)
            return

        if self._tool == TOOL_CLICK:
            # 點下去的那一點是**框的中心**（同陣列工具的錨點，兩支工具對
            # 「按下去代表什麼」要講同一句話）
            h, w = self.cell_shape()
            bw, bh = self._box_px[0] / float(w), self._box_px[1] / float(h)
            nx, ny = self.view_to_norm(pt)
            self.add_box((nx - bw / 2.0, ny - bh / 2.0, bw, bh))
            return

        add = bool(e.modifiers() & Qt.ControlModifier)
        key, handle = self._hit(pt)
        if key is not None:
            if add or key not in self._selection:
                self.select_box(key[1], add=add, region=key[0])
            if handle or key in self._selection:
                # 選了好幾個的時候拖任何一個都**整組一起搬**（跨區域也是）——
                # 不然使用者對齊完想微調，一拖就把選取打散了。
                self._snapshot()
                self._drag = {"mode": handle or "move", "key": key,
                              "from": self.view_to_norm(pt),
                              "group": {k: tuple(self.box_at(*k))
                                        for k in self._selection
                                        if self.box_at(*k) is not None},
                              "box": tuple(self.box_at(*key))}
            return

        nx, ny = self.view_to_norm(pt)
        if self._tool == TOOL_CURSOR:
            # 游標工具在空白處拖 = **框選**，不是畫新的框
            if not add:
                self.set_selection([])
            self._drag = {"mode": "lasso", "from": (nx, ny),
                          "box": (nx, ny, 0.0, 0.0), "add": add,
                          "base": list(self._selection)}
            self.update()
            return
        # 拖曳工具：空白處拖 = 畫一個新框
        self._drag = {"mode": "new", "from": (nx, ny), "box": (nx, ny, 0.0, 0.0)}
        self.update()

    def mouseMoveEvent(self, e) -> None:                # noqa: D102 - Qt hook
        pt = _pos(e)
        # 還沒按下去就先畫出「按下去會長出什麼」（使用者：方便對齊擺放）
        if self._tool in (TOOL_CLICK, TOOL_ARRAY):
            self._hover = self.view_to_norm(pt)
            if self._tool == TOOL_ARRAY and self.array_anchor_count() == 1:
                # 整片的預覽跟著游標走 —— 提示列上的數量與 pitch 也要跟著
                self.array_anchors_changed.emit(1)
            self.update()
        if self._paint is not None and (e.buttons() & Qt.LeftButton):
            self._paint_at(pt)
            return
        if self._drag is None:
            return
        mode = self._drag["mode"]
        if mode == "pan":
            self._pan = self._drag["pan"] + (pt - self._drag["from"])
            self.update()
            return
        nx, ny = self.view_to_norm(pt)
        if mode in ("new", "lasso"):
            x0, y0 = self._drag["from"]
            rect = (min(x0, nx), min(y0, ny), abs(nx - x0), abs(ny - y0))
            self._drag["box"] = self.snap(rect) if mode == "new" else rect
            if mode == "lasso":
                self._sync_lasso()
            self.update()
            return
        self._apply_drag(nx, ny)

    def _sync_lasso(self) -> None:
        """框選：**整個**落在套索裡的框才算 —— 擦到邊就選中會很難只選一個。"""
        lx, ly, lw, lh = self._drag["box"]
        # **每一個區域**都收 —— 不同 region 對齊的前提就是選得到彼此
        inside = [(ri, bi)
                  for ri, (_n, boxes) in enumerate(self._regions)
                  for bi, (x, y, w, h) in enumerate(boxes)
                  if x >= lx and y >= ly and x + w <= lx + lw and y + h <= ly + lh]
        picked = list(self._drag["base"]) if self._drag.get("add") else []
        self.set_selection(picked + inside)

    def _apply_drag(self, nx: float, ny: float) -> None:
        d = self._drag
        x, y, w, h = d["box"]
        dx, dy = nx - d["from"][0], ny - d["from"][1]
        mode = d["mode"]
        if mode == "move":
            for k, (bx, by, bw, bh) in (d.get("group") or {}).items():
                self.put_box(k[0], k[1], self.snap((bx + dx, by + dy, bw, bh)))
            self.update()
            return
        else:
            if "w" in mode:
                x, w = x + dx, w - dx
            if "e" in mode:
                w = w + dx
            if "n" in mode:
                y, h = y + dy, h - dy
            if "s" in mode:
                h = h + dy
            if w < 0:
                x, w = x + w, -w
            if h < 0:
                y, h = y + h, -h
        self.put_box(d["key"][0], d["key"][1],
                     self.snap((x, y, min(1.0, w), min(1.0, h))))
        self.update()

    def mouseReleaseEvent(self, e) -> None:             # noqa: D102 - Qt hook
        if self._paint is not None:
            self._commit_paint()
            return
        if self._drag is None:
            return
        d, self._drag = self._drag, None
        if d["mode"] == "pan":
            self.setCursor(Qt.ArrowCursor
                           if self._tool in (TOOL_CURSOR, TOOL_DRAG)
                           else Qt.CrossCursor)
            return
        if d["mode"] == "lasso":
            self.update()
            return
        if d["mode"] == "new":
            x, y, w, h = d["box"]
            h_px, w_px = self.cell_shape()
            if w * w_px >= 1.5 and h * h_px >= 1.5:
                self.add_box((x, y, min(1.0, w), min(1.0, h)))
            else:
                self.update()          # 只是點一下 —— 不要留一個看不見的框
            return
        self._commit()

    # ---- paint：一顆一顆點像素 ---------------------------------------------
    def _paint_at(self, pt: QPointF) -> None:
        h, w = self.cell_shape()
        nx, ny = self.view_to_norm(pt)
        # 鋪成一片時點到隔壁那幾格也算數 —— 畫面上它們是同一個結構的延續，
        # 而在資料上它們就是同一格（相位是環狀的）
        px, py = int(nx * w) % w, int(ny * h) % h
        if (px, py) not in self._paint:
            self._paint.add((px, py))
            self.update()

    def _commit_paint(self) -> None:
        """一筆點完的像素併成**逐列的矩形**（run-length）。

        區域的資料模型是矩形，所以像素要變回矩形才存得進 recipe；而逐列合併
        是那個轉換裡最省框的一種（一整條 EPI 只會變成一個框，不是 40 個）。
        這也正是 F11 §3.3.2 答案 B 對 label map 講的同一套做法。
        """
        pixels, self._paint = self._paint or set(), None
        if not pixels:
            self.update()
            return
        runs = []
        for py in sorted({p[1] for p in pixels}):
            xs = sorted(p[0] for p in pixels if p[1] == py)
            start = prev = xs[0]
            for x in xs[1:] + [None]:
                if x != prev + 1:
                    runs.append((start, py, prev - start + 1, 1))
                    if x is None:
                        break
                    start = x
                prev = x if x is not None else prev
        self.add_boxes([self.from_px(r) for r in runs])

    def _array_defaults(self):
        h, w = self.cell_shape()
        return (self._box_px[0] / float(w), self._box_px[1] / float(h),
                self._array_n[0], self._array_n[1])

    def leaveEvent(self, _e) -> None:                   # noqa: D102 - Qt hook
        # 游標離開畫布，那個「下一個框」就不該還留在畫面上（畫布不能說謊）
        if self._hover is not None:
            self._hover = None
            self.update()

    def hover_box(self) -> Optional[Tuple[float, float, float, float]]:
        """游標下面那個**還沒放下去**的框（沒有就 ``None``）。"""
        if self._hover is None or self._tool not in (TOOL_CLICK, TOOL_ARRAY):
            return None
        if self._tool == TOOL_ARRAY and self.array_anchor_count() >= 1:
            return None            # 已經有錨點了，預覽的是整片，不是一個
        h, w = self.cell_shape()
        bw, bh = self._box_px[0] / float(w), self._box_px[1] / float(h)
        nx, ny = self._hover
        return self.snap((nx - bw / 2.0, ny - bh / 2.0, bw, bh))

    def wheelEvent(self, e) -> None:                    # noqa: D102 - Qt hook
        delta = e.angleDelta().y()
        if not delta:
            return
        # **對著游標縮放**，不是對著畫面中心（使用者回報）。做法是把游標下面那
        # 一點的 cell 座標記下來，縮放之後再用 pan 把它移回原來的螢幕位置 ——
        # 「我指著的東西不要跑掉」是縮放唯一該保證的事。
        pt = _pos(e)
        before = self.view_to_norm(pt)
        self.zoom_by(1.15 if delta > 0 else 1 / 1.15)
        after = self.norm_to_view(*before)
        self._pan += pt - after
        self.update()

    def keyPressEvent(self, e) -> None:                 # noqa: D102 - Qt hook
        step = 1.0 / max(1, self.cell_shape()[1])       # 一格 cell 像素
        keys = {Qt.Key_Left: (-step, 0.0), Qt.Key_Right: (step, 0.0),
                Qt.Key_Up: (0.0, -step), Qt.Key_Down: (0.0, step)}
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
            return
        if e.key() == Qt.Key_Escape and self._array is not None:
            self.cancel_array()
            return
        if e.key() == Qt.Key_Z and e.modifiers() & Qt.ControlModifier:
            self.undo()
            return
        if e.key() == Qt.Key_A and e.modifiers() & Qt.ControlModifier:
            self.select_all()
            return
        if e.key() in keys and self._selection:
            dx, dy = keys[e.key()]
            self._snapshot()
            for k in self._selection:
                box = self.box_at(*k)
                if box is not None:
                    x, y, w, h = box
                    self.put_box(k[0], k[1], self.snap((x + dx, y + dy, w, h)))
            self._commit()
            return
        super().keyPressEvent(e)

    # ---- 畫 -----------------------------------------------------------------
    def paintEvent(self, _e) -> None:                   # noqa: D102 - Qt hook
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(TOKENS["image_backdrop"]))
        if not self.has_cell():
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "(no template yet — build one from a full-size image)")
            p.end()
            return

        self._paint_cells(p)
        self._paint_patch_window(p)
        self._paint_boxes(p)
        self._paint_stroke(p)
        self._paint_hover(p)
        self._paint_array(p)
        p.end()

    def _paint_cells(self, p: QPainter) -> None:
        h, w = self.cell_shape()
        z = self.zoom()
        o = self._origin()
        pm = QPixmap.fromImage(_qimage_from_uint8(_as_u8(self._cell)))
        # 放大時關平滑：SEM 的小圖要看得出方格（同 ImageView 的理由）
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)

        span = (-1, 0, 1) if self._tile else (0,)
        for ty in span:
            for tx in span:
                here = (tx == 0 and ty == 0)
                if not here:
                    p.setOpacity(0.45)      # 隔壁那幾格是**背景**，不是內容
                p.drawPixmap(QRectF(o.x() + tx * w * z, o.y() + ty * h * z,
                                    w * z, h * z), pm, QRectF(pm.rect()))
                p.setOpacity(1.0)

        # 接縫：框常常橫跨它，所以它要看得見
        p.setPen(QPen(QColor(255, 255, 255, 90), 1.0, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(o.x(), o.y(), w * z, h * z))

    def _paint_patch_window(self, p: QPainter) -> None:
        """一顆 defect 看得到多大 —— 標在窗外的區域在某些顆上根本不在。"""
        if not self._patch_size:
            return
        ph, pw = self._patch_size
        z = self.zoom()
        c = QPointF(self.width() / 2.0 + self._pan.x(),
                    self.height() / 2.0 + self._pan.y())
        r = QRectF(c.x() - pw * z / 2.0, c.y() - ph * z / 2.0, pw * z, ph * z)
        p.setPen(QPen(QColor(TOKENS["accent"]), 1.4, Qt.DotLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        p.setPen(QColor(TOKENS["accent"]))
        p.drawText(QRectF(r.left(), r.top() - 16, max(120.0, r.width()), 15),
                   Qt.AlignLeft | Qt.AlignBottom,
                   "one patch (%d × %d px)" % (pw, ph))

    def _paint_boxes(self, p: QPainter) -> None:
        span = (-1, 0, 1) if self._tile else (0,)
        h, w = self.cell_shape()
        z = self.zoom()
        for ri, (name, boxes) in enumerate(self._regions):
            col = region_color(ri)
            for bi, box in enumerate(boxes):
                base = self.box_rect(box)
                for ty in span:
                    for tx in span:
                        here = (tx == 0 and ty == 0)
                        r = base.translated(tx * w * z, ty * h * z)
                        sel = ((ri, bi) in self._selection and here)
                        p.setPen(QPen(col, 2.2 if sel else 1.4,
                                      Qt.SolidLine if here else Qt.DotLine))
                        fill = QColor(col)
                        fill.setAlpha(70 if sel else (34 if here else 14))
                        p.setBrush(fill)
                        p.drawRect(r)
                        # 把手**只有選單一個框的時候才畫**（使用者：multi add
                        # 加完全部都框起來很醜）。選了一整排的時候把手也沒有
                        # 意義 —— 一個把手拉不動二十個框，而「選中了」用外框
                        # 加粗就講完了。
                        if sel and self.handles_visible():
                            p.setBrush(col)
                            p.setPen(QPen(QColor(255, 255, 255, 210), 0.8))
                            for hr in self._handles(r).values():
                                p.drawRect(hr)
                if boxes and bi == 0:
                    p.setPen(col)
                    p.setBrush(Qt.NoBrush)
                    p.drawText(QRectF(base.left(), base.top() - 15,
                                      max(60.0, base.width()), 14),
                               Qt.AlignLeft | Qt.AlignBottom, str(name))
        # 正在拉的那個新框／套索
        mode = (self._drag or {}).get("mode")
        if mode == "new":
            p.setPen(QPen(region_color(self._current), 1.4, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.box_rect(self._drag["box"]))
        elif mode == "lasso":
            col = QColor(TOKENS["accent"])
            p.setPen(QPen(col, 1.0, Qt.DashLine))
            fill = QColor(col)
            fill.setAlpha(28)
            p.setBrush(fill)
            p.drawRect(self.box_rect(self._drag["box"]))

    def _paint_stroke(self, p: QPainter) -> None:
        """正在點的那些像素 —— 放手前就要看得見，不然使用者不知道點到沒有。"""
        if not self._paint:
            return
        h, w = self.cell_shape()
        col = region_color(self._current)
        fill = QColor(col)
        fill.setAlpha(150)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        span = (-1, 0, 1) if self._tile else (0,)
        z = self.zoom()
        for px, py in self._paint:
            base = self.box_rect(self.from_px((px, py, 1, 1)))
            for ty in span:
                for tx in span:
                    p.drawRect(base.translated(tx * w * z, ty * h * z))

    def _paint_hover(self, p: QPainter) -> None:
        """按下去會長出什麼 —— 先畫給人看，才對得準（使用者定調）。"""
        box = self.hover_box()
        if box is None:
            return
        col = region_color(self._current)
        r = self.box_rect(box)
        p.setPen(QPen(col, 1.2, Qt.DashLine))
        fill = QColor(col)
        fill.setAlpha(26)
        p.setBrush(fill)
        p.drawRect(r)
        # 十字：按下去的那一點是**框的中心**，那件事在放下之前就要看得見
        c = r.center()
        p.setPen(QPen(col, 1.0))
        p.drawLine(QPointF(c.x() - 7, c.y()), QPointF(c.x() + 7, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - 7), QPointF(c.x(), c.y() + 7))

    def _paint_array(self, p: QPainter) -> None:
        if self._array is None:
            return
        col = region_color(self._current)
        for box in self.array_preview():
            p.setPen(QPen(col, 1.2, Qt.DashLine))
            fill = QColor(col)
            fill.setAlpha(28)
            p.setBrush(fill)
            p.drawRect(self.box_rect(box))
        # 十字錨點：使用者按下去的那一點就是**框的中心**，所以要畫出中心
        p.setBrush(Qt.NoBrush)
        for nx, ny in self._array["anchors"]:
            c = self.norm_to_view(nx, ny)
            p.setPen(QPen(QColor(TOKENS["text_primary"]), 2.4))
            p.drawLine(QPointF(c.x() - 9, c.y()), QPointF(c.x() + 9, c.y()))
            p.drawLine(QPointF(c.x(), c.y() - 9), QPointF(c.x(), c.y() + 9))
            p.setPen(QPen(col, 1.4))
            p.drawLine(QPointF(c.x() - 8, c.y()), QPointF(c.x() + 8, c.y()))
            p.drawLine(QPointF(c.x(), c.y() - 8), QPointF(c.x(), c.y() + 8))


def _pos(e) -> QPointF:
    """滑鼠事件的位置（PySide6 6.0 起是 ``position()``，舊版是 ``pos()``）。"""
    return QPointF(e.position()) if hasattr(e, "position") else QPointF(e.pos())


def _as_u8(arr: np.ndarray) -> np.ndarray:
    """畫布只負責顯示 —— 任何值域進來都要看得見（同 widgets 的做法）。"""
    a = np.asarray(arr)
    if a.dtype == np.uint8:
        return a
    a = a.astype(np.float32)
    lo, hi = float(a.min()), float(a.max())
    if hi <= lo:
        return np.zeros(a.shape, np.uint8)
    return ((a - lo) * (255.0 / (hi - lo))).astype(np.uint8)

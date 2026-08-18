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

from adept.core.pipeline.cellrois import array_boxes

from .theme import TOKENS
from .widgets import _qimage_from_uint8

__all__ = ["CellCanvas", "REGION_COLORS", "region_color"]

#: 區域的顏色（依清單順序輪流）。要在深色的 SEM 影像上看得見，所以都偏亮。
#: 不用 ``accent`` 那一組：那是「選取／焦點」的語彙，而這裡的顏色講的是
#: **哪一個區域**，兩件事混在一起使用者會以為藍色的那個是被選中的。
REGION_COLORS = ("#5fd0a0", "#f0b429", "#7aa7ff", "#f07aa7",
                 "#9ad14b", "#d18ef0", "#4bd1c8", "#f08a5f")

#: 拖曳把手的邊長（畫面像素）。太小抓不到，太大蓋住小框。
_HANDLE = 7.0
#: 一個框最少要有幾格 cell 像素 —— 拖到 0 寬的框存不進 recipe。
_MIN_SPAN = 1e-3


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

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._cell: Optional[np.ndarray] = None
        #: [(name, [box, …]), …] —— 跟 ``cellrois`` 同一個形狀
        self._regions: List[Tuple[str, List[Tuple[float, float, float, float]]]] = []
        self._current = 0
        self._selected = -1
        self._zoom = 0.0            # 0 = 還沒算過（第一次 paint 時 fit）
        self._pan = QPointF(0.0, 0.0)
        self._tile = True
        self._patch_size: Optional[Tuple[int, int]] = None

        self._drag: Optional[Dict[str, Any]] = None
        self._array: Optional[Dict[str, Any]] = None

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
        self._selected = -1
        self.update()

    def regions(self):
        return [(n, list(b)) for n, b in self._regions]

    def set_current_region(self, index: int) -> None:
        self._current = max(0, int(index))
        self._selected = -1
        self.selection_changed.emit(self._current, -1)
        self.update()

    def current_region(self) -> int:
        return self._current

    def selected_box(self) -> int:
        return self._selected

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

    def add_box(self, box) -> int:
        """加一個框到目前的區域，回傳它的索引（−1 = 沒有區域可以加）。"""
        if not (0 <= self._current < len(self._regions)):
            return -1
        self._boxes().append(tuple(float(v) for v in box))
        self._selected = len(self._boxes()) - 1
        self.selection_changed.emit(self._current, self._selected)
        self._commit()
        return self._selected

    def add_boxes(self, boxes) -> int:
        """一次加一整片（陣列工具用）；回傳實際加了幾個。"""
        if not (0 <= self._current < len(self._regions)):
            return 0
        added = [tuple(float(v) for v in b) for b in boxes]
        self._boxes().extend(added)
        self._selected = len(self._boxes()) - 1
        self.selection_changed.emit(self._current, self._selected)
        self._commit()
        return len(added)

    def delete_selected(self) -> bool:
        boxes = self._boxes()
        if not (0 <= self._selected < len(boxes)):
            return False
        boxes.pop(self._selected)
        self._selected = min(self._selected, len(boxes) - 1)
        self.selection_changed.emit(self._current, self._selected)
        self._commit()
        return True

    def select_box(self, index: int) -> None:
        boxes = self._boxes()
        self._selected = index if 0 <= index < len(boxes) else -1
        self.selection_changed.emit(self._current, self._selected)
        self.update()

    def replace_box(self, index: int, box) -> None:
        boxes = self._boxes()
        if 0 <= index < len(boxes):
            boxes[index] = tuple(float(v) for v in box)
            self._commit()

    # ---- 陣列工具（multi add）----------------------------------------------
    def start_array(self, box_w: float, box_h: float, nx: int, ny: int) -> None:
        """進入陣列模式：接下來兩次點擊是左上／右下那一格的**中心**。"""
        self._array = {"w": float(box_w), "h": float(box_h),
                       "nx": int(nx), "ny": int(ny), "anchors": []}
        self._drag = None
        self.array_anchors_changed.emit(0)
        self.update()

    def update_array(self, box_w: float, box_h: float, nx: int, ny: int) -> None:
        """陣列模式中改了大小／數量 —— 預覽跟著變，錨點留著。"""
        if self._array is None:
            return
        self._array.update(w=float(box_w), h=float(box_h),
                           nx=int(nx), ny=int(ny))
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
        first = a[0]
        last = a[1] if len(a) > 1 else a[0]
        return array_boxes(first, last, self._array["w"], self._array["h"],
                           self._array["nx"] if len(a) > 1 else 1,
                           self._array["ny"] if len(a) > 1 else 1)

    def commit_array(self) -> int:
        """把預覽的那一片真的加進區域，並離開陣列模式。"""
        boxes = self.array_preview()
        self._array = None
        self.array_anchors_changed.emit(0)
        if not boxes:
            self.update()
            return 0
        return self.add_boxes(boxes)

    def place_array_anchor(self, nx: float, ny: float) -> int:
        """放一個錨點（第三次點擊會重新從第一個開始）。回傳現在有幾個。"""
        if self._array is None:
            return 0
        a = self._array["anchors"]
        if len(a) >= 2:
            a.clear()
        a.append((float(nx), float(ny)))
        self.array_anchors_changed.emit(len(a))
        self.update()
        return len(a)

    # ---- 滑鼠 ---------------------------------------------------------------
    def _hit(self, pt: QPointF):
        """``(box_index, 把手)``；把手是 ``""``（框身）或 ``"nw"``… 之一。"""
        boxes = self._boxes()
        for i in range(len(boxes) - 1, -1, -1):        # 上層的先接
            r = self.box_rect(boxes[i])
            if i == self._selected:
                for name, corner in self._handles(r).items():
                    if corner.contains(pt):
                        return i, name
            if r.contains(pt):
                return i, ""
        return -1, ""

    @staticmethod
    def _handles(r: QRectF) -> Dict[str, QRectF]:
        d = _HANDLE
        pts = {"nw": r.topLeft(), "ne": r.topRight(),
               "sw": r.bottomLeft(), "se": r.bottomRight(),
               "n": QPointF(r.center().x(), r.top()),
               "s": QPointF(r.center().x(), r.bottom()),
               "w": QPointF(r.left(), r.center().y()),
               "e": QPointF(r.right(), r.center().y())}
        return {k: QRectF(p.x() - d, p.y() - d, d * 2, d * 2)
                for k, p in pts.items()}

    def mousePressEvent(self, e) -> None:              # noqa: D102 - Qt hook
        pt = QPointF(e.position()) if hasattr(e, "position") else QPointF(e.pos())
        if e.button() == Qt.MiddleButton or (
                e.button() == Qt.LeftButton and e.modifiers() & Qt.ShiftModifier):
            self._drag = {"mode": "pan", "from": pt, "pan": QPointF(self._pan)}
            return
        if e.button() != Qt.LeftButton:
            return

        if self._array is not None:
            nx, ny = self.view_to_norm(pt)
            self.place_array_anchor(nx, ny)
            return

        idx, handle = self._hit(pt)
        if idx >= 0:
            self.select_box(idx)
            self._drag = {"mode": handle or "move", "index": idx,
                          "from": self.view_to_norm(pt),
                          "box": tuple(self._boxes()[idx])}
            return
        # 空白處拖曳 = 畫一個新框
        nx, ny = self.view_to_norm(pt)
        self._drag = {"mode": "new", "from": (nx, ny), "box": (nx, ny, 0.0, 0.0)}
        self.update()

    def mouseMoveEvent(self, e) -> None:                # noqa: D102 - Qt hook
        pt = QPointF(e.position()) if hasattr(e, "position") else QPointF(e.pos())
        if self._drag is None:
            return
        mode = self._drag["mode"]
        if mode == "pan":
            self._pan = self._drag["pan"] + (pt - self._drag["from"])
            self.update()
            return
        nx, ny = self.view_to_norm(pt)
        if mode == "new":
            x0, y0 = self._drag["from"]
            self._drag["box"] = (min(x0, nx), min(y0, ny),
                                 abs(nx - x0), abs(ny - y0))
            self.update()
            return
        self._apply_drag(nx, ny)

    def _apply_drag(self, nx: float, ny: float) -> None:
        d = self._drag
        x, y, w, h = d["box"]
        dx, dy = nx - d["from"][0], ny - d["from"][1]
        mode = d["mode"]
        if mode == "move":
            x, y = x + dx, y + dy
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
        w, h = max(_MIN_SPAN, w), max(_MIN_SPAN, h)
        boxes = self._boxes()
        if 0 <= d["index"] < len(boxes):
            boxes[d["index"]] = (x, y, min(1.0, w), min(1.0, h))
            self.update()

    def mouseReleaseEvent(self, e) -> None:             # noqa: D102 - Qt hook
        if self._drag is None:
            return
        d, self._drag = self._drag, None
        if d["mode"] == "pan":
            return
        if d["mode"] == "new":
            x, y, w, h = d["box"]
            if w >= _MIN_SPAN * 4 and h >= _MIN_SPAN * 4:
                self.add_box((x, y, min(1.0, w), min(1.0, h)))
            else:
                self.update()          # 只是點一下 —— 不要留一個看不見的框
            return
        self._commit()

    def wheelEvent(self, e) -> None:                    # noqa: D102 - Qt hook
        delta = e.angleDelta().y()
        if delta:
            self.zoom_by(1.15 if delta > 0 else 1 / 1.15)

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
        if e.key() in keys and 0 <= self._selected < len(self._boxes()):
            dx, dy = keys[e.key()]
            x, y, w, h = self._boxes()[self._selected]
            self._boxes()[self._selected] = (x + dx, y + dy, w, h)
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
                        sel = (ri == self._current and bi == self._selected
                               and here)
                        p.setPen(QPen(col, 2.2 if sel else 1.4,
                                      Qt.SolidLine if here else Qt.DotLine))
                        fill = QColor(col)
                        fill.setAlpha(70 if sel else (34 if here else 14))
                        p.setBrush(fill)
                        p.drawRect(r)
                        if sel:
                            p.setBrush(col)
                            p.setPen(Qt.NoPen)
                            for hr in self._handles(r).values():
                                p.drawRect(hr)
                if boxes and bi == 0:
                    p.setPen(col)
                    p.setBrush(Qt.NoBrush)
                    p.drawText(QRectF(base.left(), base.top() - 15,
                                      max(60.0, base.width()), 14),
                               Qt.AlignLeft | Qt.AlignBottom, str(name))
        # 正在拉的那個新框
        if self._drag is not None and self._drag.get("mode") == "new":
            p.setPen(QPen(region_color(self._current), 1.4, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(self.box_rect(self._drag["box"]))

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

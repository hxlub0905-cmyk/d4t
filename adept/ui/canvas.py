# ADEPT Studio 節點畫布 — authored 2026-07-28 (F7-6).
"""``PipelineCanvas`` —— n8n 風格的節點畫布，取代原本的直線清單。

為什麼這件事不用動引擎
----------------------
``core`` 從 F0 起就是 DAG：``Recipe`` 早就有 ``edges`` 欄位、
``execution_order()`` 早就是 Kahn 拓撲排序 + 循環偵測、``validate()`` 早就會
報「這條 route 有循環」。當初刻意寫成「UI v1 只呈現直線，之後上自由畫布時
引擎零改動」。所以這一整個檔案純粹是 UI。

畫布長什麼樣
------------
* 節點卡：左側是所屬階段的色條，卡上是名稱 + 非預設參數摘要。
  停用的節點整張調淡（不是消失 —— 使用者要看得到它還在）。
* 連接埠：左邊是輸入、右邊是輸出。從輸出拖到輸入就連起來。
* 連線：三次貝茲曲線，方向永遠左→右，所以「資料往右流」是看得出來的。
* 選取的節點與連線用 accent 色描邊；``Delete`` 刪掉選取的東西。

位置怎麼決定
------------
**自動排版**：依拓撲深度分欄、同欄內依 ``node_order`` 排列。
使用者可以拖動節點（當下看起來會照他擺的位置），但**位置不寫進 recipe**——
recipe JSON 的結構沒有 ``pos`` 欄位，為了在畫布上存座標而改檔案格式，
會讓每一份既有 recipe 都要遷移，代價和收益不成比例。重新載入就回到自動排版。

循環擋在哪
----------
擋在 ``RecipeModel.add_edge``：拉出來的線若會造成循環，model 直接回 ``False``
不落地，畫布也就不會畫出那條線。使用者看到的是「這條線拉不起來」，
而不是「拉起來之後整條 pipeline 壞掉、跑的時候才報錯」。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QMenu,
)

from . import theme
from .theme import TOKENS

__all__ = ["PipelineCanvas", "NODE_W", "NODE_H", "COL_GAP", "ROW_GAP"]

#: 節點卡尺寸與排版間距（畫布座標）。
NODE_W, NODE_H = 168.0, 52.0
COL_GAP, ROW_GAP = 96.0, 26.0
_PORT_R = 5.0


def layout_columns(node_ids: Sequence[str],
                   edges: Sequence[Tuple[str, str]]) -> Dict[str, Tuple[int, int]]:
    """自動排版：``node_id -> (欄, 列)``。

    欄 = 拓撲深度（最長前置路徑長度），列 = 同欄內依 ``node_ids`` 的原順序。
    沒有任何連線時每個節點各自深度 0 —— 那會全部疊在第一欄，所以退化情況下
    改成「一個接一個往右排」，讓空 recipe 加卡片時看起來仍然是一條鏈。
    """
    ids = [str(n) for n in node_ids]
    idx = {n: i for i, n in enumerate(ids)}
    preds: Dict[str, List[str]] = {n: [] for n in ids}
    for a, b in edges:
        if a in idx and b in idx:
            preds[b].append(a)

    if not any(preds[n] for n in ids):
        return {n: (i, 0) for i, n in enumerate(ids)}   # 還沒連線 -> 直線排

    depth: Dict[str, int] = {}
    for n in ids:                       # ids 已是拓撲順序，一遍就夠
        depth[n] = max((depth.get(p, 0) + 1 for p in preds[n]), default=0)

    rows: Dict[int, int] = {}
    out: Dict[str, Tuple[int, int]] = {}
    for n in sorted(ids, key=lambda x: (depth[x], idx[x])):
        col = depth[n]
        out[n] = (col, rows.get(col, 0))
        rows[col] = rows.get(col, 0) + 1
    return out


class _NodeItem(QGraphicsItem):
    """一張節點卡（自繪；顏色全部取自 ``theme.TOKENS``）。"""

    def __init__(self, info: Dict[str, Any], canvas: "PipelineCanvas"):
        super().__init__()
        self.canvas = canvas
        self.info = dict(info)
        self.node_id = str(info.get("node_id", ""))
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setToolTip("%s — %s" % (self.node_id, info.get("label", "")))

    # -- 幾何 ---------------------------------------------------------------
    def boundingRect(self) -> QRectF:
        return QRectF(-_PORT_R, 0, NODE_W + 2 * _PORT_R, NODE_H)

    def in_port(self) -> QPointF:
        return self.scenePos() + QPointF(0.0, NODE_H / 2.0)

    def out_port(self) -> QPointF:
        return self.scenePos() + QPointF(NODE_W, NODE_H / 2.0)

    def _port_hit(self, pos: QPointF, out: bool) -> bool:
        anchor = QPointF(NODE_W if out else 0.0, NODE_H / 2.0)
        d = pos - anchor
        return (d.x() * d.x() + d.y() * d.y()) <= (_PORT_R * 3.0) ** 2

    # -- 繪製 ---------------------------------------------------------------
    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        enabled = bool(self.info.get("enabled", True))
        selected = self.isSelected()
        body = QRectF(0, 0, NODE_W, NODE_H)

        p.setRenderHint(QPainter.Antialiasing, True)
        border = QColor(TOKENS["accent"] if selected else TOKENS["border_default"])
        p.setPen(QPen(border, 2.0 if selected else 1.0))
        p.setBrush(QColor(TOKENS["bg_surface"] if enabled else TOKENS["disabled_bg"]))
        p.drawRoundedRect(body, 6, 6)

        # 左側階段色條
        cat = str(self.info.get("category", "") or "image")
        bar_col = QColor(theme.seg_hex(cat) if enabled else TOKENS["seg_disabled"])
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 3.0, NODE_H), 1.5, 1.5)
        p.fillPath(path, bar_col)

        # 文字
        fg = TOKENS["text_primary"] if enabled else TOKENS["text_disabled"]
        p.setPen(QColor(fg))
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(max(7.0, f.pointSizeF()))
        p.setFont(f)
        p.drawText(QRectF(11, 6, NODE_W - 20, 16), Qt.AlignVCenter | Qt.AlignLeft,
                   str(self.info.get("label", self.node_id)))
        f.setBold(False)
        f.setPointSizeF(max(6.0, f.pointSizeF() - 1.0))
        p.setFont(f)
        p.setPen(QColor(TOKENS["text_secondary"] if enabled else TOKENS["text_disabled"]))
        p.drawText(QRectF(11, 22, NODE_W - 20, 14), Qt.AlignVCenter | Qt.AlignLeft,
                   self.node_id)
        summary = str(self.info.get("summary", ""))
        if summary:
            p.drawText(QRectF(11, 34, NODE_W - 20, 14),
                       Qt.AlignVCenter | Qt.AlignLeft, summary)

        # 連接埠
        for anchor, filled in ((QPointF(0, NODE_H / 2), False),
                               (QPointF(NODE_W, NODE_H / 2), True)):
            p.setPen(QPen(QColor(TOKENS["canvas_edge"]), 1.2))
            p.setBrush(QBrush(QColor(TOKENS["bg_surface"] if not filled
                                     else TOKENS["canvas_edge"])))
            p.drawEllipse(anchor, _PORT_R, _PORT_R)

    # -- 互動 ---------------------------------------------------------------
    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton and self._port_hit(e.pos(), out=True):
            self.canvas.begin_link(self)       # 從輸出埠拉線
            e.accept()
            return
        self.canvas.node_selected.emit(self.node_id)
        super().mousePressEvent(e)

    def itemChange(self, change, value):        # noqa: D102 - Qt hook
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.canvas.refresh_edges()
        return super().itemChange(change, value)

    def contextMenuEvent(self, e) -> None:      # noqa: D102 - Qt hook
        menu = QMenu()
        act_toggle = menu.addAction(
            "Skip this step" if self.info.get("enabled", True) else "Enable this step")
        act_remove = menu.addAction("Remove")
        chosen = menu.exec(e.screenPos())
        if chosen is act_toggle:
            self.canvas.node_toggled.emit(
                self.node_id, not bool(self.info.get("enabled", True)))
        elif chosen is act_remove:
            self.canvas.remove_requested.emit(self.node_id)
        e.accept()


class _EdgeItem(QGraphicsItem):
    """一條連線（三次貝茲，左→右）。點它可選取，``Delete`` 移除。"""

    def __init__(self, src: _NodeItem, dst: _NodeItem, canvas: "PipelineCanvas"):
        super().__init__()
        self.src, self.dst, self.canvas = src, dst, canvas
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(-1.0)
        self.setToolTip("%s → %s  (select and press Delete to remove)"
                        % (src.node_id, dst.node_id))

    def pair(self) -> Tuple[str, str]:
        return (self.src.node_id, self.dst.node_id)

    def path(self) -> QPainterPath:
        a, b = self.src.out_port(), self.dst.in_port()
        dx = max(40.0, abs(b.x() - a.x()) * 0.5)
        p = QPainterPath(a)
        p.cubicTo(a + QPointF(dx, 0), b - QPointF(dx, 0), b)
        return p

    def boundingRect(self) -> QRectF:
        return self.path().boundingRect().adjusted(-6, -6, 6, 6)

    def shape(self) -> QPainterPath:
        stroker_pen = QPen(Qt.black, 10.0)
        from PySide6.QtGui import QPainterPathStroker
        st = QPainterPathStroker(stroker_pen)
        return st.createStroke(self.path())

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        col = QColor(TOKENS["canvas_edge_active"] if self.isSelected()
                     else TOKENS["canvas_edge"])
        p.setPen(QPen(col, 2.2 if self.isSelected() else 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawPath(self.path())


class PipelineCanvas(QGraphicsView):
    """節點畫布。對外的 API 與訊號刻意與舊的 ``PipelinePanel`` 對齊。

    Studio 只要換掉建構的類別，其餘接線幾乎不動 —— 這是為了讓「換 UI」
    不要順便變成「重寫主視窗」。
    """

    node_selected = Signal(str)
    node_toggled = Signal(str, bool)
    move_requested = Signal(str, int)          # 相容用，畫布不發
    remove_requested = Signal(str)
    score_clicked = Signal()
    edge_added = Signal(str, str)
    edge_removed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setMinimumHeight(180)

        self._items: Dict[str, _NodeItem] = {}
        self._edges: List[_EdgeItem] = []
        self._order: List[str] = []
        self._pairs: List[Tuple[str, str]] = []
        self._selected: Optional[str] = None
        self._score_summary = ""
        self._link_from: Optional[_NodeItem] = None
        self._link_line = None

    # ---- 對外（與 PipelinePanel 對齊）--------------------------------------
    def set_nodes(self, nodes: Sequence[Dict[str, Any]],
                  edges: Sequence[Tuple[str, str]] = ()) -> None:
        """重建整張畫布。``nodes`` 依執行順序，``edges`` 是顯式連線。"""
        self._scene.clear()
        self._items, self._edges = {}, []
        self._order = [str(n.get("node_id", "")) for n in nodes]
        self._pairs = [(str(a), str(b)) for a, b in (edges or ())]

        pos = layout_columns(self._order, self._pairs)
        for info in nodes:
            item = _NodeItem(info, self)
            col, row = pos.get(item.node_id, (0, 0))
            item.setPos(col * (NODE_W + COL_GAP), row * (NODE_H + ROW_GAP))
            self._scene.addItem(item)
            self._items[item.node_id] = item

        for a, b in self._pairs:
            if a in self._items and b in self._items:
                edge = _EdgeItem(self._items[a], self._items[b], self)
                self._scene.addItem(edge)
                self._edges.append(edge)

        self.set_selected(self._selected)
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._scene.setSceneRect(rect)

    def node_ids(self) -> List[str]:
        return list(self._order)

    def edge_pairs(self) -> List[Tuple[str, str]]:
        return list(self._pairs)

    def set_selected(self, node_id: Optional[str]) -> None:
        self._selected = None if node_id is None else str(node_id)
        for nid, item in self._items.items():
            item.setSelected(nid == self._selected)
            item.update()

    def selected_node(self) -> Optional[str]:
        return self._selected

    def selected(self) -> Optional[str]:
        """與舊 ``PipelinePanel.selected()`` 同名同義。"""
        return self._selected

    def card(self, node_id: str) -> Optional["_NodeItem"]:
        """取某個節點的圖元（highlight / 測試用；對應舊的 ``card()``）。"""
        return self._items.get(str(node_id))

    def set_score_summary(self, expr: str, threshold: Any) -> None:
        self._score_summary = "score = %s   threshold %s" % (expr, threshold)

    def score_summary(self) -> str:
        return self._score_summary

    def score_summary_text(self) -> str:
        """與舊 ``PipelinePanel.score_summary_text()`` 同名同義。"""
        return self._score_summary

    def fit(self) -> None:
        """整張圖縮放到看得完。"""
        rect = self._scene.itemsBoundingRect()
        if rect.isValid():
            self.fitInView(rect.adjusted(-30, -30, 30, 30), Qt.KeepAspectRatio)

    def refresh_edges(self) -> None:
        for e in self._edges:
            e.prepareGeometryChange()
            e.update()

    # ---- 拉線 -------------------------------------------------------------
    def begin_link(self, src: _NodeItem) -> None:
        self._link_from = src
        self._link_line = self._scene.addPath(
            QPainterPath(src.out_port()),
            QPen(QColor(TOKENS["canvas_edge_active"]), 1.6, Qt.DashLine))

    def _drop_link(self, scene_pos: QPointF) -> None:
        src, self._link_from = self._link_from, None
        if self._link_line is not None:
            self._scene.removeItem(self._link_line)
            self._link_line = None
        if src is None:
            return
        for item in self._scene.items(scene_pos):
            if isinstance(item, _NodeItem) and item is not src:
                self.edge_added.emit(src.node_id, item.node_id)
                return

    def link_to(self, src_id: str, dst_id: str) -> None:
        """程式化拉一條線（測試用；等同使用者從輸出拖到輸入）。"""
        if str(src_id) in self._items and str(dst_id) in self._items:
            self.edge_added.emit(str(src_id), str(dst_id))

    # ---- Qt hooks ---------------------------------------------------------
    def mouseMoveEvent(self, e) -> None:       # noqa: D102
        if self._link_from is not None and self._link_line is not None:
            a = self._link_from.out_port()
            b = self.mapToScene(e.pos())
            dx = max(40.0, abs(b.x() - a.x()) * 0.5)
            path = QPainterPath(a)
            path.cubicTo(a + QPointF(dx, 0), b - QPointF(dx, 0), b)
            self._link_line.setPath(path)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:    # noqa: D102
        if self._link_from is not None:
            self._drop_link(self.mapToScene(e.pos()))
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e) -> None:        # noqa: D102
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in list(self._scene.selectedItems()):
                if isinstance(item, _EdgeItem):
                    a, b = item.pair()
                    self.edge_removed.emit(a, b)
                elif isinstance(item, _NodeItem):
                    self.remove_requested.emit(item.node_id)
            e.accept()
            return
        super().keyPressEvent(e)

    def wheelEvent(self, e) -> None:           # noqa: D102
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        e.accept()

    def drawBackground(self, p: QPainter, rect: QRectF) -> None:  # noqa: D102
        p.fillRect(rect, QColor(TOKENS["canvas_bg"]))
        step = 24.0
        p.setPen(QPen(QColor(TOKENS["canvas_grid"]), 1.0))
        x = rect.left() - (rect.left() % step)
        while x < rect.right():
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
        y = rect.top() - (rect.top() % step)
        while y < rect.bottom():
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step

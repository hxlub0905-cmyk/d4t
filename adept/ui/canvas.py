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
from .widgets import draw_group_icon

__all__ = ["PipelineCanvas", "NODE_W", "NODE_H", "COL_GAP", "ROW_GAP"]

#: 一個節點最多畫幾個輸出埠（再多就擠不下，退回單一埠）。
_MAX_PORTS = 4

#: 埠標籤佔的寬度（畫在節點右緣之外，boundingRect 必須算進去）。
_PORT_LABEL_W = 52.0

#: 節點左側 icon 的邊長，以及裝著它的圓角色塊。
#: 用**色塊**而不是細色條（F7-8）：n8n 的節點一眼認得出來，靠的就是左邊那顆
#: 有顏色的圖示磚。細條太安靜，遠看整張畫布還是一排一模一樣的方框。
_ICON = 18.0
_TILE = 32.0

#: 節點卡尺寸與排版間距（畫布座標）。
NODE_W, NODE_H = 190.0, 56.0
COL_GAP, ROW_GAP = 96.0, 26.0
_PORT_R = 5.0

#: 連線中點的方向箭頭大小。畫布可以縮放平移，光看曲線不一定分得出資料往哪流。
_ARROW = 5.0

#: 還沒拉線時，一列最多排幾張卡（見 :func:`layout_columns`）。
WRAP = 4


def layout_columns(node_ids: Sequence[str],
                   edges: Sequence[Tuple[str, str]]) -> Dict[str, Tuple[int, int]]:
    """自動排版：``node_id -> (欄, 列)``。

    欄 = 拓撲深度（最長前置路徑長度），列 = 同欄內依 ``node_ids`` 的原順序。
    沒有任何連線時每個節點各自深度 0 —— 那會全部疊在第一欄，所以退化情況下
    改成「一個接一個往右排」，讓空 recipe 加卡片時看起來仍然是一條鏈。

    但那條鏈**會換行**（``WRAP``，F7-9）。一份九張卡、還沒拉線的 recipe 排成
    一列會超過 2500px；``fit()`` 為了塞進畫面得縮到看不出字，而它又有下限
    （縮成小方塊比留捲軸更糟），結果是「一排讀不出來的小方塊 + 一條捲軸」。
    換行之後同樣九張卡是 3×3，每一張都讀得到字。閱讀順序仍然是左到右、
    上到下 —— 跟文字一樣，不需要額外學。
    """
    ids = [str(n) for n in node_ids]
    idx = {n: i for i, n in enumerate(ids)}
    preds: Dict[str, List[str]] = {n: [] for n in ids}
    for a, b in edges:
        if a in idx and b in idx:
            preds[b].append(a)

    if not any(preds[n] for n in ids):
        return {n: (i % WRAP, i // WRAP) for i, n in enumerate(ids)}

    depth: Dict[str, int] = {}
    for n in ids:                       # ids 已是拓撲順序，一遍就夠
        depth[n] = max((depth.get(p, 0) + 1 for p in preds[n]), default=0)

    # 一「帶」= 換行之前的 WRAP 個深度。帶高取「最擠的那個深度有幾個節點」，
    # 這樣換行之後上下兩帶不會疊在一起。
    per_depth: Dict[int, int] = {}
    for n in ids:
        per_depth[depth[n]] = per_depth.get(depth[n], 0) + 1
    band_h = max(per_depth.values(), default=1)

    rows: Dict[int, int] = {}
    out: Dict[str, Tuple[int, int]] = {}
    for n in sorted(ids, key=lambda x: (depth[x], idx[x])):
        d = depth[n]
        band, col = divmod(d, WRAP)
        r = rows.get(d, 0)
        rows[d] = r + 1
        out[n] = (col, band * band_h + r)
    return out


def _draw_elided(p: QPainter, rect: QRectF, text: str) -> None:
    """畫一行文字，太長就切成 ``像這樣…``。

    直接 ``drawText`` 到一個放不下的矩形，Qt 會**硬切在字的中間**，看起來像
    畫面壞掉；``參數摘要=diff · metri`` 這種殘句還會讓人以為值真的是那樣。
    """
    s = str(text)
    fm = p.fontMetrics()
    if fm.horizontalAdvance(s) > rect.width():
        s = fm.elidedText(s, Qt.ElideRight, int(rect.width()))
    p.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, s)


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
        tip = "%s — %s" % (self.node_id, info.get("label", ""))
        if info.get("problem"):
            # 標記說「有問題」，滑鼠停上去說「是什麼問題」。標記本身放不下一句話，
            # 而「有一個紅點但不知道為什麼」比沒有標記更讓人焦慮。
            tip += "\n\n⚠ %s" % info["problem"]
        self.setToolTip(tip)

    # -- 幾何 ---------------------------------------------------------------
    def boundingRect(self) -> QRectF:
        """**要涵蓋所有畫得出去的東西**，否則拖動節點會留下殘影。

        埠標籤（"test" / "ref"）畫在節點右緣之外 —— 之前 boundingRect 只算到
        ``NODE_W + _PORT_R``，Qt 就只重繪那個範圍，標籤的舊位置沒被清掉。
        """
        return QRectF(-_PORT_R - 1, -1,
                      NODE_W + 2 * _PORT_R + _PORT_LABEL_W + 5, NODE_H + 5)

    def in_port(self) -> QPointF:
        return self.scenePos() + self.in_port_local()

    @staticmethod
    def in_port_local() -> QPointF:
        return QPointF(0.0, NODE_H / 2.0)

    def in_names(self) -> List[str]:
        """這個節點讀哪些影像流（用來決定上游的線該接哪個埠）。"""
        return [str(r) for r in (self.info.get("reads") or [])]

    def out_names(self) -> List[str]:
        """這個節點吐出的影像流名稱（決定畫幾個輸出埠）。

        來自 ``Step.describe()`` 的 ``writes``。對 patch 的 Input 節點來說
        那是 ``["test", "ref"]`` —— 畫布上就看得到「一張 defect、一張 reference」，
        而不是一個什麼都不說的單一輸出。
        """
        names = [str(w) for w in (self.info.get("writes") or [])]
        return names[:_MAX_PORTS] or [""]

    def out_anchors_local(self) -> List[QPointF]:
        """每個輸出埠在**本地座標**的位置（由上而下均分節點右緣）。

        ``paint()`` 畫的是本地座標，連線算的是場景座標 —— 兩者差一個
        ``scenePos()``。之前只有場景座標版，``paint()`` 直接拿去畫，於是節點一
        離開原點，輸出埠就被畫到 ``2 × 位移`` 的地方：第一欄的 Input 看起來正常
        （它剛好在原點），後面每一張卡的右側圓點都畫到卡外面去，看起來就是
        **「新增的節點只有前面有圓框、後面沒有」**；拖動 Input 時埠標籤
        （test/ref）也會離開 ``boundingRect``，留下擦不掉的殘影。
        """
        n = len(self.out_names())
        if n <= 1:
            return [QPointF(NODE_W, NODE_H / 2.0)]
        step = NODE_H / (n + 1)
        return [QPointF(NODE_W, step * (i + 1)) for i in range(n)]

    def out_anchors(self) -> List[QPointF]:
        """每個輸出埠在**場景座標**的位置（連線用）。"""
        base = self.scenePos()
        return [base + p for p in self.out_anchors_local()]

    def out_port(self, index: int = 0) -> QPointF:
        anchors = self.out_anchors()
        return anchors[max(0, min(int(index), len(anchors) - 1))]

    def out_port_at(self, pos: QPointF):
        """本地座標 ``pos`` 命中哪一個輸出埠（沒命中回 ``None``）。"""
        for i, local in enumerate(self.out_anchors_local()):
            d = pos - local
            if (d.x() * d.x() + d.y() * d.y()) <= (_PORT_R * 3.0) ** 2:
                return i
        return None

    # -- 繪製 ---------------------------------------------------------------
    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        enabled = bool(self.info.get("enabled", True))
        selected = self.isSelected()
        body = QRectF(0, 0, NODE_W, NODE_H)

        p.setRenderHint(QPainter.Antialiasing, True)

        # 投影：讓節點浮在網格之上。用畫的而不是 QGraphicsDropShadowEffect ——
        # effect 會強迫 Qt 額外開一層離屏 buffer，為了 2px 的陰影不值得。
        shadow = QColor(0, 0, 0, 46 if enabled else 22)
        p.setPen(Qt.NoPen)
        p.setBrush(shadow)
        p.drawRoundedRect(body.translated(1.5, 2.5), 7, 7)

        gid = str(self.info.get("group", "") or "enhance")
        tile_col = QColor(theme.group_hex(gid) if enabled else TOKENS["seg_disabled"])

        border = QColor(TOKENS["accent"] if selected else TOKENS["border_default"])
        # 停用的節點畫虛線框（n8n 的慣例）—— 不是消失，是「還在，但這次不跑」。
        pen = QPen(border, 2.0 if selected else 1.0)
        if not enabled:
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(TOKENS["bg_surface"] if enabled else TOKENS["disabled_bg"]))
        p.drawRoundedRect(body, 7, 7)

        # 左邊的圖示磚：淡色底 + 與左側 rail 完全相同的圖形（F7-8）。
        tile = QRectF(8, (NODE_H - _TILE) / 2.0, _TILE, _TILE)
        wash = QColor(tile_col)
        wash.setAlpha(46 if enabled else 24)
        p.setPen(QPen(tile_col if enabled else QColor(TOKENS["border_default"]), 1.0))
        p.setBrush(wash)
        p.drawRoundedRect(tile, 6, 6)

        icon_rect = QRectF(tile.center().x() - _ICON / 2.0,
                           tile.center().y() - _ICON / 2.0, _ICON, _ICON)
        p.save()
        p.translate(icon_rect.topLeft())
        draw_group_icon(p, gid, tile_col.name(), _ICON)
        p.restore()

        # 「這張卡還不能跑」的標記（F7-13）。lint 早就知道這件事，只是那個知識
        # 以前留在跑之前的檢查裡 —— 於是一張缺模板的卡在畫布上看起來跟設定完整
        # 的一模一樣，使用者要按下 Run trial 才會知道。
        self._paint_badge(p, body)

        text_x = tile.right() + 9
        # 有警示標記時把標題讓開 —— 不讓的話標記正好蓋在卡片名字的尾巴上，
        # 兩個東西都變得難讀。
        text_w = NODE_W - text_x - (8 if not self.problem() else 22)

        fg = TOKENS["text_primary"] if enabled else TOKENS["text_disabled"]
        p.setPen(QColor(fg))
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(max(7.0, f.pointSizeF()))
        p.setFont(f)
        _draw_elided(p, QRectF(text_x, 9, text_w, 15),
                     str(self.info.get("label", self.node_id)))
        f.setBold(False)
        f.setPointSizeF(max(6.0, f.pointSizeF() - 1.0))
        p.setFont(f)
        p.setPen(QColor(TOKENS["text_secondary"] if enabled else TOKENS["text_disabled"]))
        _draw_elided(p, QRectF(text_x, 24, text_w, 13), self.node_id)
        summary = str(self.info.get("summary", ""))
        if summary:
            _draw_elided(p, QRectF(text_x, 36, text_w, 13), summary)

        # 連接埠（**本地座標** —— 見 out_anchors_local 的說明）。
        # 輸入是空心圈、輸出是實心點：一眼看得出線該從哪邊拉到哪邊。
        p.setPen(QPen(QColor(TOKENS["canvas_edge"]), 1.2))
        p.setBrush(QBrush(QColor(TOKENS["bg_surface"])))
        p.drawEllipse(self.in_port_local(), _PORT_R, _PORT_R)

        outs = self.out_names()
        p.setBrush(QBrush(QColor(TOKENS["canvas_edge"])))
        for name, anchor in zip(outs, self.out_anchors_local()):
            p.drawEllipse(anchor, _PORT_R, _PORT_R)
            if not name:
                continue
            # 每個輸出埠都標上它吐的影像流名（F7-9）。以前只有多埠才標，
            # 於是「這張卡到底做在哪一條流上」在畫布上是看不到的 ——
            # 而 Enhance 卡的 target / also apply 講的正是這些名字。
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(anchor.x() + 7, anchor.y() - 7, _PORT_LABEL_W - 8, 14),
                       Qt.AlignVCenter | Qt.AlignLeft, name)
            p.setPen(QPen(QColor(TOKENS["canvas_edge"]), 1.2))

    def problem(self) -> str:
        """這張卡現在有什麼問題（空字串 = 沒問題）。"""
        return str(self.info.get("problem", "") or "")

    def _paint_badge(self, p: QPainter, body: QRectF) -> None:
        """右上角一個小圓標。錯誤紅、警告琥珀。

        文字用 ``!`` 而不是圖形：這個標記只有 14 px，任何再細一點的形狀在
        100% 縮放下都會糊成一個點。
        """
        why = self.problem()
        if not why:
            return
        level = str(self.info.get("problem_level", "error"))
        col = QColor(TOKENS["danger_text"] if level == "error"
                     else TOKENS["warning"])
        r = 7.0
        centre = QPointF(body.right() - r - 3.0, body.top() + r + 3.0)
        p.setPen(QPen(QColor(TOKENS["bg_surface"]), 1.5))
        p.setBrush(QBrush(col))
        p.drawEllipse(centre, r, r)
        p.setPen(QPen(QColor("#ffffff"), 1.0))
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(8.0)
        p.setFont(f)
        p.drawText(QRectF(centre.x() - r, centre.y() - r, 2 * r, 2 * r),
                   Qt.AlignCenter, "!")

    # -- 互動 ---------------------------------------------------------------
    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        hit = (self.out_port_at(e.pos())
               if e.button() == Qt.LeftButton else None)
        if hit is not None:
            self.canvas.begin_link(self, hit)  # 從某一個輸出埠拉線
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
    """一條連線（三次貝茲，左→右）。點它可選取，``Delete`` 移除。

    ``implicit=True`` 是 **route 的隱含順序**（F7-10），畫成虛線、不可選取。
    引擎的依賴是「route 相鄰對 ∪ 顯式 edges」——
    也就是說**畫布上沒有線，不代表沒有連接**。以前只畫顯式 edges，於是載入
    一份沒拉過線的 recipe 看到的是「九張互不相干的卡」，但它其實是照順序跑的。
    使用者只會得到兩種結論，兩種都是錯的：以為要自己連起來才會跑，
    或以為沒連線的卡不會執行。

    不可選取（也就刪不掉）是刻意的：隱含順序來自卡片的排列，
    刪掉它在語意上等於「把這張卡從流程裡拿掉」，那是另一個動作。
    """

    def __init__(self, src: _NodeItem, dst: _NodeItem, canvas: "PipelineCanvas",
                 port: int = 0, implicit: bool = False):
        super().__init__()
        self.src, self.dst, self.canvas, self.port = src, dst, canvas, int(port)
        self.implicit = bool(implicit)
        self.setFlag(QGraphicsItem.ItemIsSelectable, not self.implicit)
        self.setZValue(-2.0 if self.implicit else -1.0)
        if self.implicit:
            self.setToolTip(
                "%s runs before %s because of the order of the cards.\n"
                "Drag from a port to make the connection explicit."
                % (src.node_id, dst.node_id))
        else:
            self.setToolTip("%s → %s  (select and press Delete to remove)"
                            % (src.node_id, dst.node_id))

    def pair(self) -> Tuple[str, str]:
        return (self.src.node_id, self.dst.node_id)

    def path(self) -> QPainterPath:
        a, b = self.src.out_port(self.port), self.dst.in_port()
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
        path = self.path()
        if self.implicit:
            # 虛線 + 半透明：看得出「有順序」，但不會跟使用者親手拉的線搶。
            col.setAlpha(120)
            pen = QPen(col, 1.3, Qt.DashLine)
            p.setPen(pen)
        else:
            p.setPen(QPen(col, 2.2 if self.isSelected() else 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # 中點的方向箭頭。畫布可以縮放、平移、節點也可以拖，光看一條曲線不一定
        # 分得出資料往哪一邊流 —— 這是「這是一張流程圖」的最基本線索。
        mid = path.pointAtPercent(0.5)
        ang = path.angleAtPercent(0.5)
        p.save()
        p.translate(mid)
        p.rotate(-ang)
        head = QPainterPath(QPointF(_ARROW, 0.0))
        head.lineTo(QPointF(-_ARROW * 0.8, _ARROW * 0.72))
        head.lineTo(QPointF(-_ARROW * 0.8, -_ARROW * 0.72))
        head.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPath(head)
        p.restore()


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
        self._pairs: List[Tuple[str, str]] = []      # 使用者拉的線
        self._implicit: List[Tuple[str, str]] = []   # route 順序帶來的依賴
        self._selected: Optional[str] = None
        self._score_summary = ""
        self._link_from: Optional[_NodeItem] = None
        self._link_port = 0
        self._link_line = None

    # ---- 對外（與 PipelinePanel 對齊）--------------------------------------
    def set_nodes(self, nodes: Sequence[Dict[str, Any]],
                  edges: Sequence[Tuple[str, str]] = ()) -> None:
        """重建整張畫布。``nodes`` 依執行順序，``edges`` 是顯式連線。"""
        self._scene.clear()
        self._items, self._edges = {}, []
        self._order = [str(n.get("node_id", "")) for n in nodes]
        self._pairs = [(str(a), str(b)) for a, b in (edges or ())]

        # route 的相鄰對也是**真的依賴**（engine 的 execution_order 是
        # 「route 相鄰對 ∪ edges」），所以排版與繪製都要把它算進去。
        self._implicit = [pair for pair in zip(self._order, self._order[1:])
                          if pair not in set(self._pairs)]

        pos = layout_columns(self._order, self._pairs + self._implicit)
        for info in nodes:
            item = _NodeItem(info, self)
            col, row = pos.get(item.node_id, (0, 0))
            item.setPos(col * (NODE_W + COL_GAP), row * (NODE_H + ROW_GAP))
            self._scene.addItem(item)
            self._items[item.node_id] = item

        for pairs, implicit in ((self._pairs, False), (self._implicit, True)):
            for a, b in pairs:
                if a not in self._items or b not in self._items:
                    continue
                src, dst = self._items[a], self._items[b]
                for port in self._ports_between(src, dst):
                    edge = _EdgeItem(src, dst, self, port, implicit=implicit)
                    self._scene.addItem(edge)
                    self._edges.append(edge)

        self.set_selected(self._selected)
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._scene.setSceneRect(rect)

    def node_item(self, node_id: str):
        """畫布上那個節點（測試與外部檢查用；沒有回 ``None``）。"""
        return self._items.get(str(node_id))

    @staticmethod
    def _ports_between(src: "_NodeItem", dst: "_NodeItem") -> List[int]:
        """一條依賴要畫成幾條線 —— 依**兩端共用的影像流**決定。

        Input 節點吐 ``test`` 與 ``ref``；``subtract`` 兩張都讀，所以
        Input → Subtract 會畫**兩條**線，各自從對應的埠出發。
        這是推導出來的，不是存起來的 —— recipe JSON 的 edge 仍然是
        ``[from, to]`` 兩個 id，格式不用改，重新載入也不會掉資訊。

        兩端沒有共用的流（或下游沒宣告 reads）→ 退回單一條線。
        """
        outs = src.out_names()
        wanted = set(dst.in_names())
        ports = [i for i, name in enumerate(outs) if name in wanted]
        return ports or [0]

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

    #: ``fit()`` 最多縮到多小。還沒拉線的 recipe 會排成一條很長的橫列，
    #: 硬要全部塞進畫面會把節點縮成看不出字的小方塊 —— 那時候寧可留捲軸。
    MIN_FIT_SCALE = 0.45

    def fit(self) -> None:
        """整張圖縮放到看得完（但不縮到看不懂）。"""
        rect = self._scene.itemsBoundingRect()
        if not rect.isValid():
            return
        self.fitInView(rect.adjusted(-30, -30, 30, 30), Qt.KeepAspectRatio)
        s = self.transform().m11()
        if 0 < s < self.MIN_FIT_SCALE:
            self.scale(self.MIN_FIT_SCALE / s, self.MIN_FIT_SCALE / s)

    def refresh_edges(self) -> None:
        for e in self._edges:
            e.prepareGeometryChange()
            e.update()

    # ---- 拉線 -------------------------------------------------------------
    def begin_link(self, src: _NodeItem, port: int = 0) -> None:
        self._link_from = src
        self._link_port = int(port)
        self._link_line = self._scene.addPath(
            QPainterPath(src.out_port(port)),
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
            a = self._link_from.out_port(getattr(self, "_link_port", 0))
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

    #: 背景點陣間距（畫布座標）。
    GRID = 22.0

    def drawBackground(self, p: QPainter, rect: QRectF) -> None:  # noqa: D102
        """點陣底，不是格線底（F7-8）。

        格線會在整張畫布上鋪滿橫豎線，跟連線同一種筆觸，於是「哪條是資料流、
        哪條是背景」要看第二眼才分得出來。點只提供對齊的參考，不會跟線搶。
        """
        p.fillRect(rect, QColor(TOKENS["canvas_bg"]))
        step = self.GRID
        # 縮太小的時候點會糊成一片灰 —— 那時候乾脆不畫
        if self.transform().m11() < 0.45:
            return
        p.setPen(QPen(QColor(TOKENS["canvas_grid"]), 1.6, Qt.SolidLine,
                      Qt.RoundCap))
        x0 = rect.left() - (rect.left() % step)
        y0 = rect.top() - (rect.top() % step)
        y = y0
        while y < rect.bottom():
            x = x0
            while x < rect.right():
                p.drawPoint(QPointF(x, y))
                x += step
            y += step

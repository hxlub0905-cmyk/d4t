# d4t Studio 判定區 — authored 2026-08-24 (F24 ②).
"""判定樹住在畫布上（F24 定稿：「分揀槽也要在畫布上呈現，而且是多步驟判定」）。

這一份管**唯讀渲染**：判定區（淡紫底虛線框）、入口小卡、菱形（一步一問）、
托盤（葉子）、分支流量。編輯互動是 F24 ③ 的事。

三個不變量（`docs/history/plans/F24-decision-tree.md` §4、§10）：

* **樹的每一步就是引擎的一步** —— 這裡畫的樹直接來自 `DecideSpec`
  （`rules` 模式先過 `rules_to_tree`，那個轉換無損，F24 ① 的測試釘住了）。
* **分支流量守恆**：每個菱形 in = yes + no；根 = 這一批跑成功的顆數。
  流量是**拿每一顆的特徵把樹重走一遍**算的（`flow_counts`）——
  引擎的 `meta["decide"]["path"]` 刻意不進結果 JSON（動 schema 動到黃金值），
  而 F24 ① 已證明「拿 features 重走 = 引擎走的那一條」（path replay 測試）。
* **未試跑：數字誠實地不在**（F18 的老規矩，不顯示 0）——
  `counts=None` 時整個判定區一個數字都不畫。

跟 `canvas.py` 的分工：`PipelineCanvas.set_decision` 收一份 **info dict**
（`decision_info` 組的），把這裡的圖元擺進同一個 scene —— 判定區因此跟著
畫布一起平移縮放，它是畫布的一部分，不是側欄。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..core.pipeline.expression import parse_expression
from ..core.pipeline.decide_tree import (          # noqa: F401 — 再匯出
    OPS, count_yes, decision_info, display_tree, flow_counts, format_condition,
    layout_cells, leaf_color, leaf_stats, parse_simple_condition, path_text,
    rows_reaching, suggest_condition,
)
from .theme import TOKENS

__all__ = [
    "decision_info", "display_tree", "layout_cells", "flow_counts",
    "leaf_stats", "leaf_hex", "build_zone", "build_ghosts", "path_text",
    "parse_simple_condition", "format_condition", "rows_reaching",
    "count_yes", "suggest_condition", "OPS",
]


def leaf_hex(bin_: int) -> str:
    """一個 bin 一個穩定的顏色（同一份 recipe 重開顏色不變）。

    ⚠ **調色盤住 `core.pipeline.decide_tree`**（F29 C0）：報表也要畫同一批
    類別，而同一類在畫面與報表上不同色的話，「這根柱子是哪一類」要重新學一次。
    留在這裡的只有 bin 0 那一格 —— 那一個**是**主題的一部分。
    """
    return leaf_color(bin_, TOKENS["seg_disabled"])


# --------------------------------------------------------------------------- #
# 導引式的問題（F25）：一個問題大部分時候就是「哪個數字 · 比什麼 · 多少」
# --------------------------------------------------------------------------- #
#: 比較運算子 → 給人看的話。**順序就是下拉的順序**（最常用的排前面）。
#:
#: 為什麼要這一層：`when` 是一個表達式，而目標使用者是不會寫 code 的製程
#: 工程師（推廣鐵則）。`contrast > 120` 這種東西他讀得懂，但**要他從空白
#: 打出來**就卡住了 —— 打錯一個字得到的是一條 `bad-rule`，而畫面上看起來
#: 只是「這個工具不理我」。挑三格永遠打不錯。
#: ⚠ **這幾個字要放得進 118px 的下拉**（2026-08-24）。以前是
#: ``"is greater than"`` 那一組，在判定面板那一欄被截成 ``is greater tha…``
#: —— 而六個運算子的差別**正好在被截掉的那幾個字**（greater than ／
#: greater than or equal）。少掉一個 ``is``，句子讀起來一樣完整
#: （``glv_max`` ／ ``greater than`` ／ ``67``），而且放得下。
#: 托盤色條的顏色（類別色）。bin 0 慣例上是 nuisance —— 灰；其餘照調色盤輪。
_LEAF_PALETTE = ("#3574d6", "#2e9e62", "#d97706", "#8a5fbf",
                 "#c2418a", "#0e9aa7")


def leaf_hex(bin_: int) -> str:
    """一個 bin 一個穩定的顏色（同一份 recipe 重開顏色不變）。"""
    b = int(bin_)
    if b == 0:
        return TOKENS["seg_disabled"]
    return _LEAF_PALETTE[(b - 1) % len(_LEAF_PALETTE)]


#: 排版格（**畫布座標，所以它留在 UI**）。`layout_cells` 回的是 col/row，
#: 幾何是無單位的格子 —— 一格幾個像素是畫面的事（F29 C0 搬家時分的那一刀）。
CELL_W, CELL_H = 196.0, 92.0


# --------------------------------------------------------------------------- #
# 圖元（**裡面的**全部唯讀：不可拖、不可刪 —— 樹是一個結構，不是幾張散卡。
# 2026-08-25 起**整個判定區**拖得動也拿得掉，把手是外框 `_ZoneItem`：
# 動的是整區的位置，樹的形狀一個位元都沒變。）
# --------------------------------------------------------------------------- #
_ENTRY_W, _ENTRY_H = 204.0, 56.0
_DIA_W, _DIA_H = 156.0, 64.0
_TRAY_W, _TRAY_H = 168.0, 48.0
_PAD = 26.0                       # 判定區框到內容的邊距
_ENTRY_GAP = 30.0                 # 入口卡到根節點的垂直距離


def _adc_color() -> QColor:
    return QColor(TOKENS["seg_adc"])


def _elide(p: QPainter, rect: QRectF, text: str, align=Qt.AlignLeft) -> None:
    fm = p.fontMetrics()
    s = str(text)
    if fm.horizontalAdvance(s) > rect.width():
        s = fm.elidedText(s, Qt.ElideRight, int(rect.width()))
    p.drawText(rect, Qt.AlignVCenter | align, s)


#: ✕ 那顆鈕的大小與它離右上角的距離。
_CLOSE_R = 8.0
_CLOSE_INSET = 14.0


class _ZoneItem(QGraphicsItem):
    """判定區的底：淡紫底、虛線框、DECISION 標題、左緣的 ``numbers →`` 提示。

    量測卡到判定區之間**刻意沒有存的線**（引擎裡數字是一張全域的表，
    畫一條存起來的線就是說謊）—— 只有這一句淡淡的提示。

    **它同時是整個判定區的把手**（2026-08-25，使用者：「ADC 也要能在原畫布上
    拖曳 移除」）。拖的是**整區**，不是裡面某一個菱形 —— 樹是一個結構，
    把某一步單獨拖走只會讓畫面說一句樹上沒有的話。所以：

    * 在框上（不是在卡片上）按住拖 → 整區跟著走；
    * 右上角一顆 ✕ → 請畫布問「要拿掉整個判定嗎」。

    位置**不寫進 recipe**，跟卡片的位置同一個待遇（見 `canvas` 模組說明）——
    所以拖它不會讓檔案變髒，`Tidy up` 也把它一起排回去。
    """

    def __init__(self, rect: QRectF, canvas: Any = None):
        super().__init__()
        self._rect = QRectF(rect)
        self._canvas = canvas
        self._drag_from: Optional[QPointF] = None
        self._hover_close = False
        self.setZValue(-3.0)          # 墊在所有東西（含連線 -1）底下
        if canvas is not None:
            self.setAcceptHoverEvents(True)
            self.setCursor(Qt.OpenHandCursor)

    # ---- ✕ 的位置（畫與打到都用這一個，不要算兩次）----------------------
    def _close_centre(self) -> QPointF:
        return QPointF(self._rect.right() - _CLOSE_INSET,
                       self._rect.top() + _CLOSE_INSET)

    def _on_close(self, pos: QPointF) -> bool:
        d = pos - self._close_centre()
        return (d.x() * d.x() + d.y() * d.y()) <= (_CLOSE_R + 3.0) ** 2

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-84.0, -24.0, 4.0, 4.0)

    # ---- 互動 -------------------------------------------------------------
    def hoverMoveEvent(self, e) -> None:        # noqa: N802 — Qt
        on = self._on_close(e.pos())
        if on != self._hover_close:
            self._hover_close = on
            self.setCursor(Qt.ArrowCursor if on else Qt.OpenHandCursor)
            self.update()
        super().hoverMoveEvent(e)

    def hoverLeaveEvent(self, e) -> None:       # noqa: N802 — Qt
        if self._hover_close:
            self._hover_close = False
            self.update()
        super().hoverLeaveEvent(e)

    def mousePressEvent(self, e) -> None:       # noqa: N802 — Qt
        if self._canvas is None or e.button() != Qt.LeftButton:
            super().mousePressEvent(e)
            return
        if self._on_close(e.pos()):
            e.accept()
            return                              # 真的拿掉在 release（同按鈕慣例）
        self._drag_from = e.scenePos()
        self.setCursor(Qt.ClosedHandCursor)
        e.accept()

    def mouseMoveEvent(self, e) -> None:        # noqa: N802 — Qt
        if self._drag_from is None:
            super().mouseMoveEvent(e)
            return
        delta = e.scenePos() - self._drag_from
        self._drag_from = e.scenePos()
        # **就地移動整區**（不重建）：重建會把滑鼠從把手上搶走，
        # 而那正是 F26 在拖門檻時學到的同一條。
        self._canvas.move_decision_by(delta.x(), delta.y())
        e.accept()

    def mouseReleaseEvent(self, e) -> None:     # noqa: N802 — Qt
        was_dragging = self._drag_from is not None
        self._drag_from = None
        self.setCursor(Qt.OpenHandCursor)
        if (self._canvas is not None and e.button() == Qt.LeftButton
                and not was_dragging and self._on_close(e.pos())):
            self._canvas.decision_remove_requested.emit()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        col = _adc_color()
        pen = QPen(col, 1.2, Qt.DashLine)
        pen.setDashPattern([5.0, 4.0])
        p.setPen(pen)
        p.setBrush(QColor(TOKENS["seg_adc_bg"]))
        p.drawRoundedRect(self._rect, 10, 10)
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.0))
        f.setLetterSpacing(f.SpacingType.AbsoluteSpacing, 1.2)
        p.setFont(f)
        p.setPen(col)
        p.drawText(QRectF(self._rect.left() + 12, self._rect.top() + 4,
                          self._rect.width() - 24, 16),
                   Qt.AlignLeft | Qt.AlignVCenter, "DECISION")
        # 左緣的提示：數字從量測卡「流」過來，但那不是一條存的線。
        f2 = p.font()
        f2.setBold(False)
        f2.setLetterSpacing(f2.SpacingType.AbsoluteSpacing, 0.0)
        p.setFont(f2)
        faded = QColor(TOKENS["text_secondary"])
        faded.setAlpha(140)
        p.setPen(faded)
        p.drawText(QRectF(self._rect.left() - 80, self._rect.top() + 20,
                          72, 16), Qt.AlignRight | Qt.AlignVCenter,
                   "numbers →")

        # 右上角那顆 ✕：拿掉整個判定（2026-08-25）。
        # **只有畫布接得住的時候才畫** —— 畫一顆按不動的鈕比沒有那顆鈕更糟。
        if self._canvas is not None:
            c = self._close_centre()
            if self._hover_close:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(TOKENS["danger_bg"]))
                p.drawEllipse(c, _CLOSE_R, _CLOSE_R)
            pen = QPen(QColor(TOKENS["danger_text"] if self._hover_close
                              else TOKENS["text_secondary"]), 1.4)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            r = _CLOSE_R * 0.45
            p.drawLine(QPointF(c.x() - r, c.y() - r), QPointF(c.x() + r, c.y() + r))
            p.drawLine(QPointF(c.x() - r, c.y() + r), QPointF(c.x() + r, c.y() - r))


class _EntryItem(QGraphicsItem):
    """入口小卡：funnel icon ＋ Decision ＋ ƒ working numbers ＋「N in」。

    **永遠恰好一個、不能刪** —— 所以它不可選取也不可拖（要動的是樹，
    不是這張卡的位置）。點它 = 跳到判定的編輯（canvas 發 `decision_clicked`）。
    """

    def __init__(self, canvas: Any, lets: List[str], n_in: Optional[int],
                 collapsed: bool = False):
        super().__init__()
        self._canvas = canvas
        self._lets = list(lets)
        self._n_in = n_in
        self._collapsed = bool(collapsed)
        tip = ("The decision tree sorts every defect into a class."
               "\nDouble-click to %s the tree."
               % ("show" if collapsed else "collapse"))
        if lets:
            tip += "\n\nWorking numbers:\n" + "\n".join(self._lets)
        self.setToolTip(tip)

    def boundingRect(self) -> QRectF:
        return QRectF(-2, -2, _ENTRY_W + 4, _ENTRY_H + 4)

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        col = _adc_color()
        body = QRectF(0, 0, _ENTRY_W, _ENTRY_H)
        p.setPen(QPen(col, 1.4))
        p.setBrush(QColor(TOKENS["bg_surface"]))
        p.drawRoundedRect(body, 7, 7)
        # funnel（分揀槽）—— 手畫的小漏斗，跟 mockup 同一個記號。
        tile = QRectF(8, (_ENTRY_H - 32) / 2.0, 32, 32)
        wash = QColor(col)
        wash.setAlpha(42)
        p.setPen(QPen(col, 1.0))
        p.setBrush(wash)
        p.drawRoundedRect(tile, 6, 6)
        cx, cy = tile.center().x(), tile.center().y()
        fun = QPainterPath(QPointF(cx - 8, cy - 7))
        fun.lineTo(QPointF(cx + 8, cy - 7))
        fun.lineTo(QPointF(cx + 2.5, cy + 1))
        fun.lineTo(QPointF(cx + 2.5, cy + 8))
        fun.lineTo(QPointF(cx - 2.5, cy + 6))
        fun.lineTo(QPointF(cx - 2.5, cy + 1))
        fun.closeSubpath()
        p.setBrush(col)
        p.setPen(Qt.NoPen)
        p.drawPath(fun)

        text_x = tile.right() + 9
        p.setPen(QColor(TOKENS["text_primary"]))
        f = p.font()
        f.setBold(True)
        p.setFont(f)
        _elide(p, QRectF(text_x, 9, _ENTRY_W - text_x - 8, 16), "Decision")
        f.setBold(False)
        f.setPointSizeF(max(6.0, f.pointSizeF() - 1.0))
        p.setFont(f)
        p.setPen(QColor(TOKENS["text_secondary"]))
        if self._collapsed:
            sub = "tree hidden — double-click to show"
        elif self._lets:
            sub = "ƒ %s" % ", ".join(x.split("=", 1)[0].strip()
                                     for x in self._lets)
        else:
            sub = "sorts by the tree below"
        _elide(p, QRectF(text_x, 30, _ENTRY_W - text_x - 8, 14), sub)
        # 「N in」只在試跑過之後（F18：不顯示 0）。
        if self._n_in is not None:
            chip = "%d in" % int(self._n_in)
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(chip) + 12
            r = QRectF(_ENTRY_W - w - 6, 6, w, 16)
            p.setPen(Qt.NoPen)
            badge = QColor(col)
            badge.setAlpha(36)
            p.setBrush(badge)
            p.drawRoundedRect(r, 8, 8)
            p.setPen(_adc_color())
            p.drawText(r, Qt.AlignCenter, chip)

    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self._canvas.decision_clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: D102 - Qt hook
        # 雙擊＝收合／展開整棵樹（F24 §4：嫌佔位的出口）。
        self._canvas.toggle_tree_collapsed()
        e.accept()


class _DiamondItem(QGraphicsItem):
    """一步一問的菱形（流程圖語言 —— 製程工程師本來就會讀）。

    點它＝右欄變成這一步的編輯面板（跟點卡片同一條路，F24 ③）。
    """

    def __init__(self, when: str, path: str, canvas: Any = None,
                 selected: bool = False):
        super().__init__()
        self.when = str(when)
        self.tree_path = str(path)
        self._canvas = canvas
        self._selected = bool(selected)
        # 幽靈線（F24 ④）：滑鼠停上來 → 這一步用到的數字各自亮出它的來源卡。
        self.setAcceptHoverEvents(True)
        self.setToolTip("%s ?\n\nyes goes right, no goes down. "
                        "Click to edit this step."
                        % (self.when or "(empty question)"))

    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton and self._canvas is not None:
            self._canvas.tree_step_clicked.emit(self.tree_path)
            e.accept()
            return
        super().mousePressEvent(e)

    def hoverEnterEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if self._canvas is not None:
            self._canvas.show_tree_ghosts(self)
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if self._canvas is not None:
            self._canvas.clear_tree_ghosts()
        super().hoverLeaveEvent(e)

    def boundingRect(self) -> QRectF:
        return QRectF(-2, -2, _DIA_W + 4, _DIA_H + 4)

    def shape(self) -> QPainterPath:
        return self._diamond()

    def _diamond(self) -> QPainterPath:
        path = QPainterPath(QPointF(_DIA_W / 2.0, 0.0))
        path.lineTo(QPointF(_DIA_W, _DIA_H / 2.0))
        path.lineTo(QPointF(_DIA_W / 2.0, _DIA_H))
        path.lineTo(QPointF(0.0, _DIA_H / 2.0))
        path.closeSubpath()
        return path

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        col = _adc_color()
        if self._selected:
            halo = QColor(TOKENS["accent"])
            halo.setAlpha(56)
            p.setPen(QPen(halo, 6.0))
            p.setBrush(Qt.NoBrush)
            p.drawPath(self._diamond())
        p.setPen(QPen(QColor(TOKENS["accent"]) if self._selected else col,
                      2.0 if self._selected else 1.4))
        p.setBrush(QColor(TOKENS["bg_surface"]))
        p.drawPath(self._diamond())
        p.setPen(QColor(TOKENS["text_primary"]))
        f = p.font()
        f.setPointSizeF(max(6.5, f.pointSizeF() - 1.0))
        p.setFont(f)
        _elide(p, QRectF(18, _DIA_H / 2.0 - 8, _DIA_W - 36, 16),
               (self.when + " ?") if self.when else "( … ) ?",
               align=Qt.AlignHCenter)


class _TrayItem(QGraphicsItem):
    """葉子＝托盤：類別色條＋名字＋顆數＋「x/y real」＋微型純度條。

    點它＝右欄變成這一類的編輯面板（改名字、換 bin、換成一個新步驟）。
    """

    def __init__(self, cell: Dict[str, Any], count: Optional[int],
                 stats: Optional[Tuple[int, int]], canvas: Any = None,
                 selected: bool = False):
        super().__init__()
        self.cell = dict(cell)
        self.count = count
        self.stats = stats
        self._canvas = canvas
        self._selected = bool(selected)
        tip = "bin %d" % int(cell.get("bin", 0))
        if cell.get("label"):
            tip = "%s — %s" % (cell["label"], tip)
        if cell.get("otherwise"):
            tip += "\nEverything no rule matched lands here."
        self.setToolTip(tip + "\nClick to edit this class.")

    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton and self._canvas is not None:
            self._canvas.tree_leaf_clicked.emit(str(self.cell.get("path", "")))
            e.accept()
            return
        super().mousePressEvent(e)

    def boundingRect(self) -> QRectF:
        return QRectF(-2, -2, _TRAY_W + 4, _TRAY_H + 4)

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        body = QRectF(0, 0, _TRAY_W, _TRAY_H)
        col = QColor(leaf_hex(self.cell.get("bin", 0)))
        if self._selected:
            halo = QColor(TOKENS["accent"])
            halo.setAlpha(56)
            p.setPen(QPen(halo, 6.0))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(body, 6, 6)
        pen = QPen(QColor(TOKENS["accent"] if self._selected
                          else TOKENS["border_default"]),
                   2.0 if self._selected else 1.0)
        if self.cell.get("otherwise"):
            pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(TOKENS["bg_surface"]))
        p.drawRoundedRect(body, 6, 6)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(0, 0, 5, _TRAY_H), 2.5, 2.5)

        label = str(self.cell.get("label") or "")
        if self.cell.get("otherwise") and not label:
            label = "(anything else)"
        title = label or "bin %d" % int(self.cell.get("bin", 0))
        p.setPen(QColor(TOKENS["text_primary"]))
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(max(6.5, f.pointSizeF() - 0.5))
        p.setFont(f)
        _elide(p, QRectF(12, 6, _TRAY_W - 52, 15), title)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(_TRAY_W - 44, 6, 38, 15),
                   Qt.AlignRight | Qt.AlignVCenter,
                   "bin %d" % int(self.cell.get("bin", 0)))

        # 第二行：顆數（試跑後才有）＋ x/y real ＋ 純度條。
        if self.count is None:
            return
        bits = ["%d" % int(self.count)]
        if self.stats is not None:
            real, n = self.stats
            bits.append("%d/%d real" % (int(real), int(n)))
        _elide(p, QRectF(12, 24, _TRAY_W - 60, 14), " · ".join(bits))
        if self.stats is not None and self.stats[1] > 0:
            real, n = self.stats
            bar = QRectF(_TRAY_W - 46, 30, 38, 4)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(TOKENS["seg_disabled"]))
            p.drawRoundedRect(bar, 2, 2)
            frac = max(0.0, min(1.0, float(real) / float(n)))
            if frac > 0:
                p.setBrush(col)
                p.drawRoundedRect(QRectF(bar.left(), bar.top(),
                                         bar.width() * frac, bar.height()),
                                  2, 2)


class _BranchItem(QGraphicsItem):
    """一條分支：yes 往右（水平）或 no 往下（垂直），加「yes · N」標籤。

    ``hot=True``：這條分支在**現在預覽那一顆走過的路**上（F24 §8）——
    畫粗、全彩，整條路徑因此在樹上亮起來。
    """

    def __init__(self, a: QPointF, b: QPointF, word: str,
                 count: Optional[int], hot: bool = False):
        super().__init__()
        self._a, self._b = QPointF(a), QPointF(b)
        self._word = str(word)
        self._count = count
        self._hot = bool(hot)
        self.setZValue(-2.0)

    def _label(self) -> str:
        if not self._word:
            return "" if self._count is None else "%d" % int(self._count)
        if self._count is None:
            return self._word
        return "%s · %d" % (self._word, int(self._count))

    def boundingRect(self) -> QRectF:
        return QRectF(self._a, self._b).normalized().adjusted(-40, -18, 40, 18)

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        col = QColor(TOKENS["accent"]) if self._hot else _adc_color()
        p.setPen(QPen(col, 3.0 if self._hot else 1.4))
        p.drawLine(self._a, self._b)
        # 箭頭在終點。
        d = self._b - self._a
        horiz = abs(d.x()) > abs(d.y())
        s = 4.5
        head = QPainterPath(self._b)
        if horiz:
            head.lineTo(self._b + QPointF(-s * 1.6, -s))
            head.lineTo(self._b + QPointF(-s * 1.6, s))
        else:
            head.lineTo(self._b + QPointF(-s, -s * 1.6))
            head.lineTo(self._b + QPointF(s, -s * 1.6))
        head.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawPath(head)

        text = self._label()
        if not text:
            return
        mid = (self._a + self._b) / 2.0
        f = p.font()
        f.setPointSizeF(max(6.0, f.pointSizeF() - 1.5))
        p.setFont(f)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text) + 8
        if horiz:
            r = QRectF(mid.x() - w / 2.0, mid.y() - 18, w, 14)
        else:
            r = QRectF(mid.x() + 6, mid.y() - 7, w, 14)
        bg = QColor(TOKENS["seg_adc_bg"])
        bg.setAlpha(230)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 4, 4)
        p.setPen(_adc_color())
        p.drawText(r, Qt.AlignCenter, text)


# --------------------------------------------------------------------------- #
# 組裝
# --------------------------------------------------------------------------- #
def _cell_pos(cell: Dict[str, Any], origin: QPointF) -> QPointF:
    """一格的左上角（入口卡佔掉第一列，樹從 origin 下方開始）。"""
    x = origin.x() + cell["col"] * CELL_W
    y = origin.y() + _ENTRY_H + _ENTRY_GAP + cell["row"] * CELL_H
    return QPointF(x, y)


def build_zone(scene: Any, canvas: Any,
               info: Dict[str, Any], origin: QPointF,
               collapsed: bool = False,
               selected_path: Optional[str] = None,
               highlight_path: Optional[str] = None) -> List[QGraphicsItem]:
    """把判定區的圖元擺進 scene，回傳擺了哪些（畫布重建時要清）。

    ``collapsed=True``：整棵樹收成入口小卡一張（F24 §4，雙擊入口卡切換）。
    ``selected_path``：右欄正在編的那一步，畫布上亮起來。
    ``highlight_path``：現在預覽那一顆走過的路（``"yn…"``）—— 沿路的分支
    畫粗（F24 §8）。``None`` = 沒有在看某一顆。
    """
    items: List[QGraphicsItem] = []
    cells = [] if collapsed else list(info.get("cells") or [])
    counts = info.get("counts")           # None = 還沒試跑 → 不畫任何數字
    stats = dict(info.get("leaf_stats") or {})

    entry = _EntryItem(canvas, list(info.get("lets") or []),
                       None if counts is None else int(counts.get("", 0)),
                       collapsed=collapsed)
    entry.setPos(origin)
    scene.addItem(entry)
    items.append(entry)

    by_path: Dict[str, Dict[str, Any]] = {}
    made: Dict[str, QGraphicsItem] = {}
    for cell in cells:
        pos = _cell_pos(cell, origin)
        sel = selected_path == cell["path"]
        if cell["kind"] == "step":
            it: QGraphicsItem = _DiamondItem(cell["when"], cell["path"],
                                             canvas, selected=sel)
        else:
            c = None if counts is None else int(counts.get(cell["path"], 0))
            it = _TrayItem(cell, c, stats.get(cell["path"]), canvas,
                           selected=sel)
        it.setPos(pos)
        scene.addItem(it)
        items.append(it)
        by_path[cell["path"]] = cell
        made[cell["path"]] = it

    def centre(path: str) -> QPointF:
        it = made[path]
        cell = by_path[path]
        w = _DIA_W if cell["kind"] == "step" else _TRAY_W
        h = _DIA_H if cell["kind"] == "step" else _TRAY_H
        return it.pos() + QPointF(w / 2.0, h / 2.0)

    # 入口卡 → 根。根是菱形或（空樹＝只有 otherwise）一個托盤。
    if "" in made:
        root_cell = by_path[""]
        w = _DIA_W if root_cell["kind"] == "step" else _TRAY_W
        a = origin + QPointF(_ENTRY_W / 2.0, _ENTRY_H)
        b = made[""].pos() + QPointF(w / 2.0, 0.0)
        # 位置故意讓兩點同一條垂直線（入口在 col0 上方）——
        # 寬度不同時稍斜一點也讀得懂。
        items.append(_BranchItem(a, b, "",
                                 None if counts is None
                                 else counts.get("", 0),
                                 hot=highlight_path is not None))
        scene.addItem(items[-1])

    # 每個菱形到它的 yes / no。
    for path, cell in by_path.items():
        if cell["kind"] != "step":
            continue
        it = made[path]
        for word, suffix in (("yes", "y"), ("no", "n")):
            child = path + suffix
            if child not in made:
                continue
            ccell = by_path[child]
            cw = _DIA_W if ccell["kind"] == "step" else _TRAY_W
            ch = _DIA_H if ccell["kind"] == "step" else _TRAY_H
            n = None if counts is None else counts.get(child, 0)
            if word == "yes":
                a = it.pos() + QPointF(_DIA_W, _DIA_H / 2.0)
                b = made[child].pos() + QPointF(0.0, ch / 2.0)
            else:
                a = it.pos() + QPointF(_DIA_W / 2.0, _DIA_H)
                b = made[child].pos() + QPointF(cw / 2.0, 0.0)
            hot = (highlight_path is not None
                   and highlight_path.startswith(child))
            branch = _BranchItem(a, b, word, n, hot=hot)
            scene.addItem(branch)
            items.append(branch)

    # 底框（最後算，才知道內容多大）。
    rect = QRectF()
    for it in items:
        rect = rect.united(it.sceneBoundingRect())
    zone = _ZoneItem(rect.adjusted(-_PAD, -_PAD, _PAD, _PAD), canvas)
    scene.addItem(zone)
    items.append(zone)
    return items


# --------------------------------------------------------------------------- #
# 幽靈線（F24 ④）
# --------------------------------------------------------------------------- #
class _GhostWireItem(QGraphicsItem):
    """一條**臨時**的點線：這一步用到的數字是從那張卡來的。

    樣式刻意跟資料流的線不同（點線＋標籤）—— 它是一個「答案」，不是一條連接。
    滑鼠移開就消失（`clear_tree_ghosts`），從不存進 recipe。
    """

    def __init__(self, a: QPointF, b: QPointF, label: str):
        super().__init__()
        self._a, self._b = QPointF(a), QPointF(b)
        self._label = str(label)
        self.setZValue(2.0)               # 臨時的答案畫在所有東西之上

    def boundingRect(self) -> QRectF:
        return QRectF(self._a, self._b).normalized().adjusted(-60, -20, 60, 20)

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        col = QColor(TOKENS["accent"])
        pen = QPen(col, 1.6, Qt.DotLine)
        p.setPen(pen)
        path = QPainterPath(self._a)
        dx = max(40.0, abs(self._b.x() - self._a.x()) * 0.4)
        path.cubicTo(self._a + QPointF(dx, 0), self._b - QPointF(dx, 0),
                     self._b)
        p.drawPath(path)
        if not self._label:
            return
        mid = path.pointAtPercent(0.5)
        f = p.font()
        f.setPointSizeF(max(6.0, f.pointSizeF() - 1.5))
        p.setFont(f)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(self._label) + 10
        r = QRectF(mid.x() - w / 2.0, mid.y() - 18, w, 14)
        bg = QColor(TOKENS["bg_surface"])
        bg.setAlpha(235)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 4, 4)
        p.setPen(col)
        p.drawText(r, Qt.AlignCenter, self._label)


def build_ghosts(scene: Any, canvas: Any, diamond: "_DiamondItem",
                 feat_owner: Dict[str, str]) -> Tuple[List[QGraphicsItem],
                                                      List[Any]]:
    """這個菱形的問題用到哪些數字 → 各畫一條幽靈線回它的來源卡。

    來源從**宣告**推（`RecipeModel.feature_owners`）—— 所以它不說謊：
    卡片宣告會寫出那個數字，線才畫得出來。`let` 的中間值（owner 是空字串）
    指回入口卡。回 ``(幽靈線圖元, 被點亮的卡片)`` —— 清場的人要各清各的。
    """
    from .canvas import NODE_W

    try:
        variables = sorted(parse_expression(str(diamond.when)).variables)
    except Exception:              # noqa: BLE001 — 打到一半的算式沒有變數
        variables = []
    items: List[QGraphicsItem] = []
    cards: List[Any] = []
    target = diamond.pos() + QPointF(0.0, _DIA_H / 2.0)
    entry = next((it for it in canvas.decision_items()
                  if isinstance(it, _EntryItem)), None)
    for var in variables:
        owner = feat_owner.get(var)
        if owner is None:
            continue
        if owner == "":
            if entry is None:
                continue
            src_item, label = entry, "%s · from Decision" % var
            a = src_item.pos() + QPointF(_ENTRY_W, _ENTRY_H / 2.0)
        else:
            src_item = canvas.node_item(owner)
            if src_item is None:
                continue
            card_label = str(src_item.info.get("label", owner))
            label = "%s · from %s" % (var, card_label)
            a = src_item.pos() + QPointF(NODE_W, src_item.height() / 2.0)
            src_item.set_hovered(True)
            cards.append(src_item)
        wire = _GhostWireItem(a, target, label)
        scene.addItem(wire)
        items.append(wire)
    return items, cards

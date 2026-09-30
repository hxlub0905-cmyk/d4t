# d4t Studio 判定區 — authored 2026-08-24 (F24 ②).
"""判定樹住在畫布上（F24 定稿：「分揀槽也要在畫布上呈現，而且是多步驟判定」）。

這一份管**唯讀渲染**：菱形（一步一問）、托盤（葉子）、分支流量。編輯互動是
F24 ③ 的事。**樹掛在畫布上那張 Decision 卡底下**（F123 期 1）—— 以前它自己有一個
淡紫底虛線框和一張入口小卡，而那讓判定在畫布上是跟卡片不同的另一種東西
（使用者：「理論上 input = output」）。

三個不變量（`docs/history/plans/F24-decision-tree.md` §4、§10）：

* **樹的每一步就是引擎的一步** —— 這裡畫的樹直接來自 `DecideSpec`
  （`rules` 模式先過 `rules_to_tree`，那個轉換無損，F24 ① 的測試釘住了）。
* **分支流量守恆**：每個菱形 in = yes + no；根 = 這一批跑成功的顆數。
  流量是**拿每一顆的特徵把樹重走一遍**算的（`flow_counts`）——
  引擎的 `meta["decide"]["path"]` 刻意不進結果 JSON（動 schema 動到黃金值），
  而 F24 ① 已證明「拿 features 重走 = 引擎走的那一條」（path replay 測試）。
* **未試跑：數字誠實地不在**（F18 的老規矩，不顯示 0）——
  `counts=None` 時整棵樹一個數字都不畫。

跟 `canvas.py` 的分工：`PipelineCanvas.set_decision` 收一份 **info dict**
（`decision_info` 組的），把這裡的圖元擺進同一個 scene —— 樹因此跟著
畫布一起平移縮放，它是畫布的一部分，不是側欄。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..core.pipeline.expression import parse_expression
from ..core.pipeline.decide_tree import (
    OPS, count_yes, decision_info, display_tree, flow_counts, format_condition,
    layout_cells, leaf_color, leaf_stats, parse_simple_condition, path_text,
    rows_reaching, suggest_condition,
)
from . import theme
from .theme import TOKENS

__all__ = [
    "decision_info", "display_tree", "layout_cells", "flow_counts",
    "leaf_stats", "leaf_hex", "build_tree", "build_ghosts", "path_text",
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

#: 排版格（**畫布座標，所以它留在 UI**）。`layout_cells` 回的是 col/row，
#: 幾何是無單位的格子 —— 一格幾個像素是畫面的事（F29 C0 搬家時分的那一刀）。
CELL_W, CELL_H = 196.0, 92.0


# --------------------------------------------------------------------------- #
# 圖元（全部唯讀：不可拖、不可刪 —— 樹是一個結構，不是幾張散卡。要動整棵樹
# 就拖那張 Decision 卡，樹跟著它走；拿掉整棵樹就是刪那張卡。）
# --------------------------------------------------------------------------- #
_DIA_W, _DIA_H = 156.0, 64.0
_TRAY_W, _TRAY_H = 168.0, 48.0


def _adc_color() -> QColor:
    return QColor(TOKENS["seg_adc"])


def _elide(p: QPainter, rect: QRectF, text: str, align=Qt.AlignLeft) -> None:
    fm = p.fontMetrics()
    s = str(text)
    if fm.horizontalAdvance(s) > rect.width():
        s = fm.elidedText(s, Qt.ElideRight, int(rect.width()))
    p.drawText(rect, Qt.AlignVCenter | align, s)


class _DiamondItem(QGraphicsItem):
    """一步一問的菱形（流程圖語言 —— 製程工程師本來就會讀）。

    點它＝右欄變成這一步的編輯面板（跟點卡片同一條路，F24 ③）。
    """

    def __init__(self, when: str, path: str, canvas: Any = None,
                 selected: bool = False, missing: Sequence[str] = ()):
        super().__init__()
        self.when = str(when)
        self.tree_path = str(path)
        self._canvas = canvas
        self._selected = bool(selected)
        #: 這一題用到、但這條 pipeline **沒有人產出**的數字（F122 期 3）。
        #: 那一題問不出來 → 每一顆都答「否」，而它在畫面上以前長得跟一題正常的
        #: 問題一模一樣（只有入口卡上一個要點開才讀得到的徽章）。
        self.missing = [str(n) for n in missing]
        # 幽靈線（F24 ④）：滑鼠停上來 → 這一步用到的數字各自亮出它的來源卡。
        self.setAcceptHoverEvents(True)
        tip = ("%s ?\n\nyes goes right, no goes down. Click to edit this step."
               % (self.when or "(empty question)"))
        if self.missing:
            tip = ("%s\n\nNothing in this pipeline measures %s, so this "
                   "question cannot be asked - every defect is answered 'no' "
                   "here. Add the card that measures it, or tick it under "
                   "“Carry these columns” on the Input card if it is a KLARF "
                   "column." % (tip, ", ".join(self.missing)))
        self.setToolTip(tip)

    def mousePressEvent(self, e) -> None:  # Qt hook
        if e.button() == Qt.LeftButton and self._canvas is not None:
            self._canvas.tree_step_clicked.emit(self.tree_path)
            e.accept()
            return
        super().mousePressEvent(e)

    def hoverEnterEvent(self, e) -> None:  # Qt hook
        if self._canvas is not None:
            self._canvas.show_tree_ghosts(self)
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e) -> None:  # Qt hook
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
        pen = QPen(QColor(TOKENS["accent"]) if self._selected else col,
                   2.0 if self._selected else 1.4)
        if self.missing:
            # 問不出來的那一題：紅色虛線框 —— 跟卡片上的錯誤同一個顏色。
            pen = QPen(QColor(TOKENS["danger_text"]), 1.8, Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(TOKENS["danger_bg"] if self.missing
                          else TOKENS["bg_surface"]))
        p.drawPath(self._diamond())
        p.setPen(QColor(TOKENS["text_primary"]))
        f = p.font()
        f.setPixelSize(theme.font_px("font_small"))
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
                 selected: bool = False,
                 sent_away: Tuple[int, Any] = (0, None)):
        super().__init__()
        self.cell = dict(cell)
        self.count = count
        self.stats = stats
        #: ``(幾顆, bin)``：走到這裡、但被「問不出來的送去 bin N」拿走的
        #: （F122）。托盤的顆數仍是「走到這裡的」—— 分支流量要守恆。
        self.sent_away = (int(sent_away[0]), sent_away[1])
        self._canvas = canvas
        self._selected = bool(selected)
        tip = "bin %d" % int(cell.get("bin", 0))
        if cell.get("label"):
            tip = "%s — %s" % (cell["label"], tip)
        if cell.get("otherwise"):
            tip += "\nEverything no rule matched lands here."
        if self.sent_away[0] and self.sent_away[1] is not None:
            tip += ("\n%d of the defects that reached here had a question "
                    "that could not be asked, so they went to bin %d instead."
                    % (self.sent_away[0], int(self.sent_away[1])))
        self.setToolTip(tip + "\nClick to edit this class.")

    def mousePressEvent(self, e) -> None:  # Qt hook
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
        f.setPixelSize(theme.font_px("font_body"))
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
        n_away, away_bin = self.sent_away
        if n_away and away_bin is not None:
            bits.append("%d → bin %d" % (n_away, int(away_bin)))
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
        f.setPixelSize(theme.font_px("font_tiny"))
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
    """一格的左上角（根在 ``origin``）。"""
    return QPointF(origin.x() + cell["col"] * CELL_W,
                   origin.y() + cell["row"] * CELL_H)


def score_summary_text(d: Any) -> str:
    """判定段現在在做什麼，一句話（畫布的 Decision 卡與狀態列讀它）。

    判定樹講「幾個問題」、規則清單講「幾條規則」、什麼都沒有就講沒有。
    （F123 期 2 從 `studio.py` 搬來：那一格只准往下。）
    """
    if d is None:
        return "no decision yet"
    if getattr(d, "tree", None) is not None:
        steps = sum(1 for c in layout_cells(display_tree(d), d)
                    if c["kind"] == "step")
        return "decision tree · %d question%s" % (steps,
                                                  "" if steps == 1 else "s")
    return "decision · %d rule%s" % (len(d.rules),
                                     "" if len(d.rules) == 1 else "s")


def _nobody_makes(when: str, owners: Any) -> List[str]:
    """這一題用到的數字裡，**這條 pipeline 沒有人產出**的那幾個（F122 期 3）。

    「誰產出什麼」只有一份答案：`RecipeModel.feature_owners`（＝
    `verdict_features.bound_specs`，有一把對照引擎的尺）。不知道（``None``）就
    不講 —— 講錯比不講糟。題目解析不出來由 lint 講，這裡不重複。
    """
    if not isinstance(owners, dict) or not str(when or "").strip():
        return []
    try:
        names = parse_expression(str(when)).variables
    except Exception:  # 語法錯由 lint 講
        return []
    return sorted(n for n in names if n not in owners)


def build_tree(scene: Any, canvas: Any,
               info: Dict[str, Any], origin: QPointF,
               anchor: Optional[QPointF] = None,
               selected_path: Optional[str] = None,
               highlight_path: Optional[str] = None) -> List[QGraphicsItem]:
    """把判定樹的圖元擺進 scene，回傳擺了哪些（畫布重建時要清）。

    根的左上角在 ``origin``；``anchor`` 是 Decision 卡的下緣中點 —— 一條線從
    那裡接到根（``None`` = 沒有那張卡，樹自己站著）。收合是畫布的事：收著就
    不叫這一支。
    ``selected_path``：右欄正在編的那一步，畫布上亮起來。
    ``highlight_path``：現在預覽那一顆走過的路（``"yn…"``）—— 沿路的分支
    畫粗（F24 §8）。``None`` = 沒有在看某一顆。
    """
    items: List[QGraphicsItem] = []
    cells = list(info.get("cells") or [])
    counts = info.get("counts")           # None = 還沒試跑 → 不畫任何數字
    stats = dict(info.get("leaf_stats") or {})
    away = dict(info.get("diverted") or {})
    ub = info.get("unanswered_bin")

    by_path: Dict[str, Dict[str, Any]] = {}
    made: Dict[str, QGraphicsItem] = {}
    for cell in cells:
        pos = _cell_pos(cell, origin)
        sel = selected_path == cell["path"]
        if cell["kind"] == "step":
            it: QGraphicsItem = _DiamondItem(
                cell["when"], cell["path"], canvas, selected=sel,
                missing=_nobody_makes(cell["when"], info.get("feat_owner")))
        else:
            c = None if counts is None else int(counts.get(cell["path"], 0))
            it = _TrayItem(cell, c, stats.get(cell["path"]), canvas,
                           selected=sel,
                           sent_away=(int(away.get(cell["path"], 0)), ub))
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

    # Decision 卡 → 根。根是菱形或（空樹＝只有 otherwise）一個托盤。
    if "" in made and anchor is not None:
        root_cell = by_path[""]
        w = _DIA_W if root_cell["kind"] == "step" else _TRAY_W
        b = made[""].pos() + QPointF(w / 2.0, 0.0)
        items.append(_BranchItem(QPointF(anchor), b, "",
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
        f.setPixelSize(theme.font_px("font_tiny"))
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
    卡片宣告會寫出那個數字，線才畫得出來。`let` 的中間值屬於 Decision 卡。
    回 ``(幽靈線圖元, 被點亮的卡片)`` —— 清場的人要各清各的。
    """
    try:
        variables = sorted(parse_expression(str(diamond.when)).variables)
    except Exception:  # 打到一半的算式沒有變數
        variables = []
    target = diamond.pos() + QPointF(0.0, _DIA_H / 2.0)
    return ghost_wires(scene, canvas, target, variables, feat_owner)


def ghost_wires(scene: Any, canvas: Any, target: QPointF,
                variables: Sequence[str],
                feat_owner: Dict[str, str]) -> Tuple[List[QGraphicsItem],
                                                     List[Any]]:
    """``variables`` 這幾個數字各畫一條幽靈線，從它的來源卡回到 ``target``。

    ⚠ **這一支是 F50 從 :func:`build_ghosts` 抽出來的**，因為 Output 卡要用
    同一套：它們也是用**名字**吃數字的（`rank_by` / `size_feature` /
    `columns`），而畫布上因此沒有任何一條線指向它們。使用者定調「不一致會有
    兩套準則」—— 那句話對「判定看得到來源、Output 看不到」一樣成立。

    抽成一支而不是抄第二份：這個 repo 記過三次「同一個判斷抄兩份，長歪的那
    一份會讓畫布跟引擎說出不同的話」。

    來源從**宣告**推（`RecipeModel.feature_owners`）—— 所以它不說謊：
    卡片宣告會寫出那個數字，線才畫得出來。`let` 的中間值屬於 Decision 卡
    （F123 期 1；以前指回判定的入口小卡）。回 ``(幽靈線圖元, 被點亮的卡片)``。
    """
    from .canvas import NODE_W

    items: List[QGraphicsItem] = []
    cards: List[Any] = []
    for var in variables:
        src_item = canvas.node_item(feat_owner.get(var) or "")
        if src_item is None:             # 沒有人產出（或手寫的沒有 Decision 卡）
            continue
        card_label = str(src_item.info.get("label", src_item.node_id))
        label = "%s · from %s" % (var, card_label)
        a = src_item.pos() + QPointF(NODE_W, src_item.height() / 2.0)
        src_item.set_hovered(True)
        cards.append(src_item)
        wire = _GhostWireItem(a, target, label)
        scene.addItem(wire)
        items.append(wire)
    return items, cards

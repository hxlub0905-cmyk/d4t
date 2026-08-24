# d4t Studio 判定區 — authored 2026-08-24 (F24 ②).
"""判定樹住在畫布上（F24 定稿：「分揀槽也要在畫布上呈現，而且是多步驟判定」）。

這一份管**唯讀渲染**：判定區（淡紫底虛線框）、入口小卡、菱形（一步一問）、
托盤（葉子）、分支流量。編輯互動是 F24 ③ 的事。

三個不變量（`docs/plans/F24-decision-tree.md` §4、§10）：

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

import re
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from ..core.pipeline.expression import parse_expression
from ..core.pipeline.recipe import TreeLeaf, TreeStep, rules_to_tree
from .theme import TOKENS

__all__ = [
    "decision_info", "display_tree", "layout_cells", "flow_counts",
    "leaf_stats", "leaf_hex", "build_zone", "build_ghosts", "path_text",
    "parse_simple_condition", "format_condition", "rows_reaching",
    "count_yes", "suggest_condition", "OPS",
]


# --------------------------------------------------------------------------- #
# 導引式的問題（F25）：一個問題大部分時候就是「哪個數字 · 比什麼 · 多少」
# --------------------------------------------------------------------------- #
#: 比較運算子 → 給人看的話。**順序就是下拉的順序**（最常用的排前面）。
#:
#: 為什麼要這一層：`when` 是一個表達式，而目標使用者是不會寫 code 的製程
#: 工程師（推廣鐵則）。`contrast > 120` 這種東西他讀得懂，但**要他從空白
#: 打出來**就卡住了 —— 打錯一個字得到的是一條 `bad-rule`，而畫面上看起來
#: 只是「這個工具不理我」。挑三格永遠打不錯。
OPS = (
    (">", "is greater than"),
    ("<", "is less than"),
    (">=", "is at least"),
    ("<=", "is at most"),
    ("==", "equals"),
    ("!=", "is not"),
)

#: 一個「單純的比較」長什麼樣：一個數字的名字、一個運算子、一個數值。
_SIMPLE_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(>=|<=|==|!=|>|<)\s*"
    r"(-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*$")


def parse_simple_condition(when: str):
    """``"contrast > 120"`` → ``("contrast", ">", 120.0)``；不是單純比較回
    ``None``（那時候編輯器退回「自己寫算式」那一格）。

    刻意**只認最單純的那一種**：複合條件（``(a > 5) * (b < 2)``）用猜的去
    拆成幾格，猜錯的那次會安靜地改掉使用者的判定 —— 而它跑得完、有數字。
    認不得就誠實地說「這一條要用算式編輯」。
    """
    m = _SIMPLE_RE.match(str(when or ""))
    if not m:
        return None
    return (m.group(1), m.group(2), float(m.group(3)))


def format_condition(name: str, op: str, value: float) -> str:
    """三格 → ``when`` 的字串。``%g`` 讓 120.0 寫成 ``120``（使用者打的樣子）。"""
    return "%s %s %g" % (str(name), str(op), float(value))


def rows_reaching(tree: Any, rows: Any, path: str) -> List[Dict[str, Any]]:
    """走到樹上這一步（或這片葉子）的那些顆。

    滑桿的範圍與「幾顆說 yes」都吃它 —— 用**流到這一步**的顆而不是整批，
    因為那才是這一步真正在分的東西（畫布上那條分支的顆數講的也是它，
    兩個數字必須是同一個）。
    """
    out: List[Dict[str, Any]] = []
    if tree is None:
        return out
    want = str(path)
    for r in rows or []:
        if not r.get("ok") or r.get("bin") is None:
            continue
        try:
            p = _path_of(tree, dict(r.get("features") or {}))
        except Exception:              # noqa: BLE001 — 顯示用，走不動就不算
            continue
        if p.startswith(want):
            out.append(r)
    return out


def _compare(value: float, op: str, threshold: float) -> bool:
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == "==":
        return value == threshold
    return value != threshold


def count_yes(rows: Any, name: str, op: str, value: float):
    """``(幾顆說 yes, 有值的顆數)`` —— 拖滑桿時旁邊那一行即時的數字。

    沒有那個數字的顆不算進分母：它們在引擎裡會走 `Let.fill` 或整顆失敗，
    把它們算成「no」會讓這一行說一個不成立的話。
    """
    yes = n = 0
    for r in rows or []:
        v = (r.get("features") or {}).get(str(name))
        if not isinstance(v, (int, float)):
            continue
        n += 1
        if _compare(float(v), str(op), float(value)):
            yes += 1
    return yes, n


#: 建議問題時**不挑**這些（它們不是「量出來的東西」）。
_NOT_A_QUESTION = ("score", "route_taken")


def suggest_condition(rows: Any, prefer: Any = ()):
    """幫使用者挑一個起手的問題：``(名字, ">", 門檻)``；挑不出來回 ``None``。

    規則刻意簡單、而且講得出理由：**挑這一批上分得最開的那個數字**
    （四分位距 ÷ 中位數，量綱無關），門檻放在**中位數**——
    一按就有東西看，剩下的用滑桿調。這不是自動最佳化，是一個
    「不會卡在空白畫面」的起點（推廣鐵則：按了要有東西發生）。

    ``prefer`` 是這份 recipe 的 working numbers（`decide.let` 的名字）——
    使用者自己組出來的數字優先，那是他心裡的量。
    """
    stats: Dict[str, List[float]] = {}
    for r in rows or []:
        if not r.get("ok"):
            continue
        for k, v in (r.get("features") or {}).items():
            k = str(k)
            if k in _NOT_A_QUESTION or k.endswith("_missing") \
                    or k.endswith("_raw"):
                continue
            if isinstance(v, (int, float)):
                stats.setdefault(k, []).append(float(v))
    best = None
    prefer = {str(x) for x in (prefer or ())}
    for name, vals in stats.items():
        if len(vals) < 4:
            continue
        s = sorted(vals)
        med = s[len(s) // 2]
        q1, q3 = s[len(s) // 4], s[(3 * len(s)) // 4]
        spread = (q3 - q1) / (abs(med) or 1.0)
        if spread <= 0:
            continue
        rank = (1 if name in prefer else 0, spread)
        if best is None or rank > best[0]:
            best = (rank, name, med)
    if best is None:
        return None
    return (best[1], ">", round(float(best[2]), 4))


# --------------------------------------------------------------------------- #
# 純資料（headless 測得到）
# --------------------------------------------------------------------------- #
def display_tree(decide: Any) -> Optional[Any]:
    """要畫的那棵樹。``decide`` 是 None → 沒有判定區的樹（回 None）。

    `rules` 模式**畫成等價的鏈狀樹**（`rules_to_tree`，無損）—— 畫布上只有
    一種語言：一步一問。使用者看到的形狀跟引擎走的形狀是同一個。
    """
    if decide is None:
        return None
    if decide.tree is not None:
        return decide.tree
    return rules_to_tree(decide)


def _is_otherwise(decide: Any, path: str, tree: Any) -> bool:
    """這片葉子是不是「(anything else)」—— 全部往 no 走到底的那一片。

    只有 `rules` 模式有 otherwise 的概念（鏈狀樹的最深 no 葉）；手寫的樹
    沒有 —— 每片葉子都是使用者自己放的。
    """
    if decide is None or decide.tree is not None:
        return False
    return path == "n" * len(path) and bool(path) or (
        path == "" and isinstance(tree, TreeLeaf))


#: 排版格（畫布座標）。菱形一格、托盤一格；yes 往右、no 往下。
CELL_W, CELL_H = 196.0, 92.0


def layout_cells(tree: Any, decide: Any = None) -> List[Dict[str, Any]]:
    """樹 → 一串格子：``{"path","kind","col","row", ...}``。

    佈局規則（mockup 定稿）：**yes 往右、no 往下**。yes 那一支排完佔了幾列，
    no 那一支從它下面接著排 —— 所以鏈狀樹（rules）畫出來就是一道樓梯：
    每一步右邊一個托盤、往下一步。
    """
    cells: List[Dict[str, Any]] = []
    if tree is None:
        return cells

    def walk(node: Any, path: str, col: int, row: int) -> int:
        if isinstance(node, TreeLeaf):
            cells.append({"path": path, "kind": "leaf", "col": col, "row": row,
                          "bin": int(node.bin), "label": str(node.label),
                          "otherwise": _is_otherwise(decide, path, tree)})
            return 1
        cells.append({"path": path, "kind": "step", "col": col, "row": row,
                      "when": str(node.when)})
        h_yes = walk(node.yes, path + "y", col + 1, row)
        h_no = walk(node.no, path + "n", col, row + h_yes)
        return h_yes + h_no

    walk(tree, "", 0, 0)
    return cells


def _path_of(tree: Any, feats: Dict[str, Any]) -> str:
    """一顆 defect 的特徵走這棵樹，走的是哪條路（``"yn…"``）。

    判準跟引擎一字不差（`engine._eval_decision`）：**非 0 就是成立**。
    """
    node, path = tree, ""
    while not isinstance(node, TreeLeaf):
        yes = parse_expression(node.when).eval(feats) != 0.0
        node = node.yes if yes else node.no
        path += "y" if yes else "n"
    return path


def flow_counts(tree: Any, rows: Any) -> Dict[str, int]:
    """每個節點「流過幾顆」：``路徑前綴 → 顆數``（``""`` = 根 = 全部）。

    守恆是**構造上的**：一顆走到路徑 p，就把 p 的每一個前綴各 +1 ——
    所以每個菱形的 in 恆等於它 yes + no 的和，不必另外對帳。

    只算**判定真的跑到**的顆（``ok`` 且有 ``bin``）；某一顆的特徵走不動樹
    （表達式炸了）就整顆不計 —— 記半條路會把守恆弄破，而那正是這張圖存在
    的理由。
    """
    counts: Dict[str, int] = {}
    if tree is None:
        return counts
    for r in rows or []:
        if not r.get("ok") or r.get("bin") is None:
            continue
        try:
            p = _path_of(tree, dict(r.get("features") or {}))
        except Exception:              # noqa: BLE001 — 顯示用，走不動就不計
            continue
        for i in range(len(p) + 1):
            prefix = p[:i]
            counts[prefix] = counts.get(prefix, 0) + 1
    return counts


def leaf_stats(tree: Any, rows: Any,
               ground_truth: Optional[Dict[str, Any]]) -> Dict[str, Tuple[int, int]]:
    """每片葉子「幾顆是真的」：``路徑 → (真缺陷數, 對得上 ground truth 的顆數)``。

    沒有 ground truth 就是空的 —— 托盤上那一小條純度就不畫
    （不是畫一條 0%：沒有分母不等於純度是零）。
    """
    out: Dict[str, Tuple[int, int]] = {}
    if tree is None or not ground_truth:
        return out
    for r in rows or []:
        if not r.get("ok") or r.get("bin") is None:
            continue
        gt = ground_truth.get(str(r.get("defect_id")))
        if not isinstance(gt, dict) or "is_real" not in gt:
            continue
        try:
            p = _path_of(tree, dict(r.get("features") or {}))
        except Exception:              # noqa: BLE001
            continue
        real, n = out.get(p, (0, 0))
        out[p] = (real + (1 if gt.get("is_real") else 0), n + 1)
    return out


def decision_info(decide: Any, rows: Any = None,
                  ground_truth: Optional[Dict[str, Any]] = None
                  ) -> Optional[Dict[str, Any]]:
    """`PipelineCanvas.set_decision` 吃的那一份 dict。

    ``decide`` 是 None（recipe 走二元 score 老路）→ 回 None，畫布上沒有
    判定區 —— 那條路的判定住在右欄的門檻滑桿，畫一個空樹只會讓人問這是
    什麼。``rows`` 是 None 或空 = **還沒試跑**：樹的形狀在、數字不在。
    """
    if decide is None:
        return None
    tree = display_tree(decide)
    ran = bool(rows)
    return {
        "lets": ["%s = %s" % (x.name, x.expr) for x in decide.let],
        "cells": layout_cells(tree, decide),
        "counts": flow_counts(tree, rows) if ran else None,
        "leaf_stats": leaf_stats(tree, rows, ground_truth) if ran else {},
    }


def path_text(tree: Any, path: str) -> str:
    """一顆 defect 走過的路，一句給人讀的話（Preview 的 Path，F24 §8）。

    ``cd_deq_missing > 0 ? no → contrast > 120 ? yes`` —— 問題照走過的順序，
    每一步接它的答案。走不完（樹跟 path 對不上）就回空字串，不要硬湊半句。
    """
    node, bits = tree, []
    for ch in str(path):
        if not isinstance(node, TreeStep):
            return ""
        bits.append("%s ? %s" % (node.when, "yes" if ch == "y" else "no"))
        node = node.yes if ch == "y" else node.no
    return " → ".join(bits)


#: 托盤色條的顏色（類別色）。bin 0 慣例上是 nuisance —— 灰；其餘照調色盤輪。
_LEAF_PALETTE = ("#3574d6", "#2e9e62", "#d97706", "#8a5fbf",
                 "#c2418a", "#0e9aa7")


def leaf_hex(bin_: int) -> str:
    """一個 bin 一個穩定的顏色（同一份 recipe 重開顏色不變）。"""
    b = int(bin_)
    if b == 0:
        return TOKENS["seg_disabled"]
    return _LEAF_PALETTE[(b - 1) % len(_LEAF_PALETTE)]


# --------------------------------------------------------------------------- #
# 圖元（全部唯讀：不可拖、不可刪 —— 樹是一個結構，不是幾張散卡）
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


class _ZoneItem(QGraphicsItem):
    """判定區的底：淡紫底、虛線框、DECISION 標題、左緣的 ``numbers →`` 提示。

    量測卡到判定區之間**刻意沒有存的線**（引擎裡數字是一張全域的表，
    畫一條存起來的線就是說謊）—— 只有這一句淡淡的提示。
    """

    def __init__(self, rect: QRectF):
        super().__init__()
        self._rect = QRectF(rect)
        self.setZValue(-3.0)          # 墊在所有東西（含連線 -1）底下

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-84.0, -24.0, 4.0, 4.0)

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
    zone = _ZoneItem(rect.adjusted(-_PAD, -_PAD, _PAD, _PAD))
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

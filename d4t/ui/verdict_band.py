# d4t Studio — 跑完之後的第一個問題：每一類各幾顆（R3，2026-08-24）。
"""**判定段**：一列一類，寬度就是顆數。

為什麼這一段要存在
------------------
跑完一整批之後第一個問題是「每一類各幾顆」，而 Results 這一頁以前答不出來
—— 要一張一張數縮圖。使用者的話是「目前的 results panel 太簡略了」。

而這些數字**全部都是現成的**：`tree_scene.flow_counts` 已經算好每個節點流過
幾顆（畫布上的分支流量吃的就是它），`leaf_stats` 已經算好每片葉子裡有幾顆是
真的。這一段只是把它們畫出來 —— **不自己數第二份**（數第二份的那一份會漂，
而漂掉的時候畫面上兩個數字對不起來，沒有人知道哪一個是對的）。

畫法沿用 F26 的分流條：**顆數變成寬度**。掃一眼就知道這一批是均勻分成三類，
還是九成落在同一類 —— 而那是「這份 recipe 判得合不合理」的第一個訊號。

⚠ 一個 bin 可能有**好幾片葉子**
-------------------------------
所以這一段的一列是**一片葉子**，不是一個 bin —— 使用者取的兩個名字都要看得
到，即使它們寫回 KLARF 的是同一個號碼。也因此篩選不能用 `{"mode": "bin"}`
（那會把另一片葉子的顆一起撈進來），要用這裡算好的 defect_id
（`Row.ids`）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from ..core.pipeline import decide_tree
from .theme import TOKENS

__all__ = ["VerdictBand", "verdict_rows"]

#: 「算不出來」那兩列的 key —— **住 core**（F29 C0），這裡只是再匯出：
#: 面板拿它們比對列，而報表也要認得同樣兩個字。
FAILED_KEY = decide_tree.FAILED_KEY
UNBINNED_KEY = decide_tree.UNBINNED_KEY


def _hex(token: str, fallback: str) -> str:
    return str(TOKENS.get(token, fallback))


# --------------------------------------------------------------------------- #
# 純資料（不碰 Qt 以外的東西，測得起來）
# --------------------------------------------------------------------------- #
def verdict_rows(decide: Any, results: Sequence[Dict[str, Any]],
                 ground_truth: Optional[Dict[Any, Any]] = None
                 ) -> List[Dict[str, Any]]:
    """每一類幾顆 —— **實作住 `core.pipeline.decide_tree`**（F29 C0）。

    搬家的理由：報表也要寫同一份數字，而 `d4t/core` 不得 import Qt（鐵則 1）。
    留在這裡的只有**主題的那兩個顏色** —— 它們是畫面的一部分，而報表沒有主題。
    """
    return decide_tree.verdict_rows(
        decide, results, ground_truth,
        nuisance=_hex("seg_disabled", decide_tree.NUISANCE_HEX),
        danger=_hex("danger", decide_tree.DANGER_HEX))


# --------------------------------------------------------------------------- #
# 畫出來
# --------------------------------------------------------------------------- #
class _Bar(QWidget):
    """一列的顆數條 —— **寬度就是顆數**（跟 F26 的分流條同一套語彙）。"""

    HEIGHT = 16

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._frac = 0.0
        self._colour = "#3574d6"
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, frac: float, colour: str) -> None:
        self._frac = max(0.0, min(1.0, float(frac)))
        self._colour = str(colour)
        self.update()

    def fraction(self) -> float:
        return self._frac

    def paintEvent(self, event) -> None:            # noqa: N802 — Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = float(self.width()), float(self.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_hex("bg_page", "#f4f5f7")))
        p.drawRoundedRect(QRectF(0, 0, w, h), 3, 3)
        if self._frac > 0:
            # **最小 3px**：一顆的那一列仍然要看得見有東西
            #（一條寬度 0.4px 的長條跟沒有畫一模一樣）。
            p.setBrush(QColor(self._colour))
            p.drawRoundedRect(QRectF(0, 0, max(3.0, w * self._frac), h), 3, 3)
        p.end()


class VerdictBand(QWidget):
    """Results 最上面那一段：**這一批判成了什麼**。

    本元件**不自己算任何東西**，也不碰 model —— `set_rows` 收
    :func:`verdict_rows` 的輸出，點一列就把 key 發出去。跟 `ResultsWindow`
    同一個立場（見它的 docstring）：面板只轉訊號，Studio 決定要做什麼。
    """

    #: 使用者點了某一類（``""`` = 取消篩選，看全部）。
    class_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: List[Dict[str, Any]] = []
        self._selected = ""
        self._row_widgets: List[QWidget] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 11, 14, 12)
        lay.setSpacing(2)

        head = QWidget(self)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 6)
        hl.setSpacing(8)
        self.title = QLabel("WHAT CAME OUT", head)
        self.title.setObjectName("paramSection")
        hl.addWidget(self.title)
        self.hint = QLabel("", head)
        self.hint.setObjectName("paramHint")
        hl.addWidget(self.hint, 1)
        lay.addWidget(head)
        self.body_lay = lay

    # ---- 外部餵進來的 ------------------------------------------------------
    def set_rows(self, rows: Sequence[Dict[str, Any]]) -> None:
        """重畫。空的 → 整段藏起來（沒跑過就不要留一塊空白的標題）。"""
        self._rows = [dict(r) for r in (rows or [])]
        if self._selected not in {str(r.get("key")) for r in self._rows}:
            self._selected = ""
        self._rebuild()
        self.setVisible(bool(self._rows))

    def rows(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._rows]

    def selected(self) -> str:
        return self._selected

    def select(self, key: str) -> None:
        """程式化選一列（``""`` = 全部）。不發訊號 —— 見 `_on_row_clicked`。"""
        want = str(key or "")
        if want and want not in {str(r.get("key")) for r in self._rows}:
            return
        self._selected = want
        self._rebuild()

    # ---- 畫 ----------------------------------------------------------------
    def _rebuild(self) -> None:
        for w in self._row_widgets:
            w.setParent(None)
            w.deleteLater()
        self._row_widgets = []
        if not self._rows:
            self.hint.setText("")
            return

        total = sum(int(r.get("count") or 0) for r in self._rows) or 1
        graded = any(int(r.get("labelled") or 0) for r in self._rows)
        n_class = sum(1 for r in self._rows if r.get("kind") == "class"
                      and int(r.get("count") or 0))
        self.hint.setText("%d defects · %d class%s used"
                          % (total, n_class, "" if n_class == 1 else "es"))

        for row in self._rows:
            w = self._row_widget(row, total, graded)
            self.body_lay.addWidget(w)
            self._row_widgets.append(w)

    def _row_widget(self, row: Dict[str, Any], total: int,
                    graded: bool) -> QWidget:
        key = str(row.get("key"))
        count = int(row.get("count") or 0)
        host = _ClickableRow(key, self)
        host.clicked.connect(self._on_row_clicked)
        host.setProperty("picked", "true" if key == self._selected else "false")
        lay = QHBoxLayout(host)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(9)

        # **類別名是主角**（跟 F26 在判定面板上做的同一件事）：使用者想的是
        # 「亮點」不是「bin 2」，而 bin 是 KLARF 的實作細節。
        # ⚠ **沒取名字的那一類就叫 `bin N`，不是「(unnamed)」。**
        # 一份從舊門檻自動轉過來的 recipe，它的每一片葉子本來就沒有名字
        #（使用者還沒取）—— 而 `bin 1` 至少是一個他認得、而且寫得回 KLARF
        # 的東西，「(unnamed)」則是在指責他少做了一件事。縮圖那邊的規則一字
        # 不差（見 `gallery.caption_lines_of`）。
        raw = str(row.get("name") or "").strip()
        fallback = ("" if row.get("bin") is None
                    else "bin %d" % int(row.get("bin")))
        name = QLabel(raw or fallback or str(row.get("kind") or ""), host)
        name.setMinimumWidth(120)
        name.setMaximumWidth(190)
        lay.addWidget(name)

        chip = QLabel("" if row.get("bin") is None or not raw
                      else "bin %d" % int(row.get("bin")), host)
        chip.setObjectName("paramHint")
        chip.setFixedWidth(46)
        chip.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(chip)

        bar = _Bar(host)
        bar.set_value(count / float(total), str(row.get("colour")))
        lay.addWidget(bar, 1)

        n = QLabel(str(count), host)
        n.setFixedWidth(34)
        n.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(n)

        # ⚠ **沒有 ground truth 就整欄不畫**，不是畫一排「—」：那一欄會佔掉
        # 版面，而且每次都在提醒使用者少了一個他可能根本沒有的東西
        #（`_accuracy_text` 對同一件事講過同一句話）。
        if graded:
            labelled = int(row.get("labelled") or 0)
            pure = QLabel("" if not labelled
                          else "%d%% real" % round(100.0 * int(row.get("real") or 0)
                                                   / labelled), host)
            pure.setObjectName("paramHint")
            pure.setFixedWidth(66)
            pure.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lay.addWidget(pure)

        host.setToolTip(_row_tip(row))
        return host

    def _on_row_clicked(self, key: str) -> None:
        """再點一次同一列 = 取消篩選（不必去找一顆「全部」的鈕）。"""
        self._selected = "" if key == self._selected else str(key)
        self._rebuild()
        self.class_selected.emit(self._selected)


def _row_tip(row: Dict[str, Any]) -> str:
    kind = str(row.get("kind"))
    n = int(row.get("count") or 0)
    if kind == "failed":
        return ("%d defect%s had a card fail on them, so they never reached "
                "the decision. Switch to the table to see why."
                % (n, "" if n == 1 else "s"))
    if kind == "unbinned":
        return ("%d defect%s ran, but the decision could not put %s in a class "
                "- usually a missing number in one of the questions."
                % (n, "" if n == 1 else "s", "it" if n == 1 else "them"))
    return "Click to show only these %d in the gallery and the table." % n


class _ClickableRow(QWidget):
    """一列（整列都可以點 —— 一列裡只有一個動作，不必找那個小小的名字）。"""

    clicked = Signal(str)

    def __init__(self, key: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._key = str(key)
        self.setObjectName("verdictRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)

    def key(self) -> str:
        return self._key

    def mouseReleaseEvent(self, event) -> None:     # noqa: N802 — Qt
        if event.button() == Qt.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.clicked.emit(self._key)

# 「為什麼還不能跑」要有一個地方 — authored 2026-09-08 (U2).
"""**紅紅的東西散在三個地方，而沒有一個地方說「一共幾個、先修哪一個」。**

2026-09-08 量的現況：lint 的結果分別出現在

* 節點上的警示點（`canvas.badge_paints`）—— 一次只講一張卡，而且要把滑鼠停
  上去才看得到是什麼；
* 狀態列（`_status`）—— **暫態**，下一句話就把它蓋掉；
* `_unmet_needs` 那句提示 —— 只在剛加一張卡的時候講。

非程式背景的使用者因此卡在「畫面上有東西紅紅的，但我不知道有幾個、也不知道
先修哪一個」。而這正好是推廣鐵則擋的東西：**看不懂發生了什麼事**。

這一條橫條買到什麼
------------------
一個**常駐**的計數（``2 errors · 1 warning``）＋ 一份點得開的清單，
點一項就選中那張卡並捲到它。三句話裡最重要的是第一句 —— 常駐：
一個要去別的地方找的答案，等於沒有答案。

⚠ **它不自己算 lint。** 數字與清單都由宿主餵（`RecipeModel.validate()`），
理由跟 `verdict_band` 一樣：畫布上的警示點與這裡的計數必須是同一份東西，
兩邊各算一次的那天，畫面上會有一張卡是紅的而清單說沒有問題。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QToolButton, QVBoxLayout,
    QWidget,
)

from . import strings, wording
from .theme import TOKENS

__all__ = ["ProblemsBar", "counts_of", "summary_of", "issue_rows"]

#: 由重到輕。清單照這個順序排 —— **error 一定在最上面**：使用者要的是
#: 「先修哪一個」，而那個答案不該取決於 lint 內部的產生順序。
LEVEL_ORDER = ("error", "warning", "info")

#: 每一級在清單上的記號。**寫字不只給顏色**（U13 同一個根）：紅綠對色覺
#: 缺陷者不可分辨，而這一列是「還能不能跑」唯一的答案。
#:
#: ⚠ **字元是挑過的**（F7-23 那條規矩）：廠內是 Windows，Segoe UI 蓋不到
#: ``✕``(U+2715) 那一族，退字型的結果是大小與 baseline 都不一樣，最壞是豆腐
#: 框 —— 而我們在開發機上看不到。``×`` 是 Latin-1、``⚠`` 這個 repo 已經在
#: 結果表的警示欄上用著，兩個都安全。
LEVEL_MARK = {"error": "×", "warning": "⚠", "info": "i"}


def counts_of(issues: Sequence[Any]) -> Dict[str, int]:
    """``{"error": 2, "warning": 1, "info": 0}``。"""
    out = {level: 0 for level in LEVEL_ORDER}
    for issue in issues or ():
        level = str(getattr(issue, "level", "") or "info")
        if level in out:
            out[level] += 1
    return out


def summary_of(issues: Sequence[Any]) -> str:
    """常駐那一行的字。

    **沒有問題也要說一句**（「Nothing is blocking a run」），不是留白：
    一條空白的橫條分不出「都好了」與「這個東西壞了沒在數」。
    """
    c = counts_of(issues)
    parts: List[str] = []
    for level in LEVEL_ORDER:
        n = c[level]
        if not n:
            continue
        word = {"error": "error", "warning": "warning", "info": "note"}[level]
        parts.append("%d %s%s" % (n, word, "" if n == 1 else "s"))
    if not parts:
        return strings.tr("Nothing is blocking a run.")
    text = " · ".join(parts)
    # **error 才擋執行**，而那件事要寫出來 —— 一個使用者看著「1 warning」
    # 不知道自己現在到底能不能按 Run。
    return text + (" — fix the errors before running" if c["error"]
                   else " — you can still run")


def issue_rows(issues: Sequence[Any],
               model: Any = None) -> List[Dict[str, Any]]:
    """lint 的發現 → 清單要顯示的列（**純資料**，排序規則住在這裡）。

    同一級的保持 lint 給的順序 —— 那個順序是照 pipeline 由上游到下游走出來
    的，而「先修上游那個」通常是對的（下游那幾條常常是它的回音）。

    ``model`` 給了就用它把 node id 與參數名換成畫面上的字（`wording`，
    F118）—— **沒給也有一句話**（退回 `detail`），因為這一支的其他使用者
    （測試、CLI 的匯出）手上沒有 model。``detail`` 原樣留著：它是 lint 自己
    的話，而 ``text`` 是畫面那一句，兩個問的不是同一件事。
    """
    rank = {level: i for i, level in enumerate(LEVEL_ORDER)}
    rows = []
    for i, issue in enumerate(issues or ()):
        level = str(getattr(issue, "level", "") or "info")
        rows.append({
            "level": level,
            "node_id": str(getattr(issue, "node_id", "") or ""),
            "title": str(getattr(issue, "title", "") or ""),
            "detail": str(getattr(issue, "detail", "") or ""),
            "text": wording.issue_line(issue, model),
            "code": str(getattr(issue, "code", "") or ""),
            "_sort": (rank.get(level, len(rank)), i),
        })
    rows.sort(key=lambda r: r["_sort"])
    for r in rows:
        r.pop("_sort")
    return rows


class ProblemsBar(QWidget):
    """``[✕ 2 errors · 1 warning — fix the errors before running]  [清單 ▾]``

    點清單裡的一項 → :attr:`problem_activated`（帶 node id）。
    宿主接了去選中那張卡並捲到它 —— **這個 widget 不碰 model**。
    """

    #: 使用者點了清單裡的一項；值是那張卡的 node id（``""`` = 這一條不指向
    #: 任何一張卡，例如「這份 recipe 沒有這個 route」）。
    problem_activated = Signal(str)

    #: 清單最多長這麼高（超過就自己捲）。一份 30 條的清單把設定區整個推出
    #: 畫面的話，使用者就得先關掉它才能去修 —— 而他要修的就是清單上那一條。
    LIST_MAX_HEIGHT = 132

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: List[Dict[str, Any]] = []
        #: 清單攤開了沒有。**用一個旗標而不是 ``list.isVisible()``**：
        #: 一個還沒有被 show 的視窗，裡面每一個 widget 的 `isVisible` 都是
        #: False —— 於是「攤開了嗎」在開窗之前永遠答錯。
        self._open = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QWidget(self)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(10, 3, 8, 3)
        hl.setSpacing(6)
        self.mark = QLabel("", head)
        hl.addWidget(self.mark)
        self.label = QLabel("", head)
        self.label.setObjectName("paramHint")
        hl.addWidget(self.label, 1)
        self.btn_toggle = QToolButton(head)
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        # ⚠ **不要在按鈕上放 ``▾``**（F7-23：Segoe UI 蓋不到 Geometric
        # Shapes，廠內那台會退字型或畫成豆腐框，而
        # `test_ui_f7_23_buttons` 會擋）。這顆鈕的字本來就說完了整件事，
        # 一個箭頭沒有多講任何東西。
        self.btn_toggle.setText(strings.tr("Show the list"))
        self.btn_toggle.clicked.connect(self.toggle)
        hl.addWidget(self.btn_toggle)
        lay.addWidget(head)
        self.head = head

        self.list = QListWidget(self)
        self.list.setObjectName("problemsList")
        self.list.setMaximumHeight(self.LIST_MAX_HEIGHT)
        self.list.setAlternatingRowColors(True)
        self.list.itemClicked.connect(self._on_item)
        self.list.hide()
        lay.addWidget(self.list)

        self.set_issues(())

    # ---- 對外 -------------------------------------------------------------
    def set_issues(self, issues: Sequence[Any], model: Any = None) -> None:
        """換一份 lint 結果（宿主每次 model 變動時餵）。

        ``model`` 是拿來把內部識別碼換成畫面上的字的（F118）—— 宿主一定給得
        出來，所以它預設 None 只是為了讓這個 widget 自己測得動。
        """
        self._rows = issue_rows(issues, model)
        c = counts_of(issues)
        self.label.setText(summary_of(issues))
        worst = next((lv for lv in LEVEL_ORDER if c[lv]), "")
        # 沒有問題就**不畫記號**（不是一個打勾）：那一行字已經把話講完了，
        # 而多一個符號只是多一個要挑「這台機器有沒有這個字」的地方。
        self.mark.setText(LEVEL_MARK.get(worst, ""))
        colour = {"error": TOKENS["danger_text"],
                  "warning": TOKENS["accent"]}.get(worst, "")
        self.mark.setStyleSheet("color: %s" % colour if colour else "")
        self.btn_toggle.setEnabled(bool(self._rows))
        self.btn_toggle.setToolTip(
            "One line per problem - click one to select that card"
            if self._rows else "Nothing to list.")

        self.list.clear()
        for row in self._rows:
            text = "%s  %s" % (LEVEL_MARK.get(row["level"], "·"),
                               row["text"] or row["title"])
            item = QListWidgetItem(text, self.list)
            item.setData(Qt.UserRole, row["node_id"])
            item.setToolTip("%s\n%s" % (row["title"], row["detail"])
                            if row["title"] else row["detail"])
            if row["level"] == "error":
                # 顏色是**冗餘**的第二個訊號 —— 前面那個 ``✕`` 已經把意思講完
                # 了（U13：紅綠對色覺缺陷者不可分辨，而這一列是「還能不能跑」
                # 唯一的答案）。
                item.setForeground(QColor(TOKENS["danger_text"]))
        if not self._rows:
            self.set_open(False)

    def counts(self) -> Dict[str, int]:
        return {level: sum(1 for r in self._rows if r["level"] == level)
                for level in LEVEL_ORDER}

    def rows(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._rows]

    def summary_text(self) -> str:
        return self.label.text()

    def is_open(self) -> bool:
        return bool(self._open)

    def set_open(self, on: bool) -> None:
        show = bool(on) and bool(self._rows)
        self._open = show
        self.list.setVisible(show)
        self.btn_toggle.setText(strings.tr("Hide the list") if show
                                else strings.tr("Show the list"))

    def toggle(self) -> None:
        self.set_open(not self.is_open())

    def activate_row(self, index: int) -> bool:
        """程式化點一列（測試與鍵盤路徑用）。"""
        if not (0 <= int(index) < len(self._rows)):
            return False
        self.problem_activated.emit(self._rows[int(index)]["node_id"])
        return True

    def _on_item(self, item: QListWidgetItem) -> None:
        self.problem_activated.emit(str(item.data(Qt.UserRole) or ""))

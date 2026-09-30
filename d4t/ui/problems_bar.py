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
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QToolButton,
    QVBoxLayout, QWidget,
)

from . import strings, wording
from .theme import TOKENS

__all__ = ["ProblemsBar", "counts_of", "summary_of", "issue_rows",
           "row_text", "connect_text"]

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
            # 「接上這幾張卡就好」（F124，`Issue.connect`）—— 有的話那一列底下
            # 多一顆鈕。鈕上的字是卡片名，不是 node id（`wording.card`）。
            "connect": [str(x) for x in (getattr(issue, "connect", ()) or ())],
            "connect_text": connect_text(
                getattr(issue, "connect", ()) or (), model),
            "_sort": (rank.get(level, len(rank)), i),
        })
    rows.sort(key=lambda r: r["_sort"])
    for r in rows:
        r.pop("_sort")
    return rows


def connect_text(node_ids: Sequence[Any], model: Any = None) -> str:
    """「Connect “GLV”」—— 那顆鈕上的字（沒有要接的就是空字串）。"""
    names = [wording.card(model, n) if model is not None else str(n)
             for n in node_ids if str(n)]
    if not names:
        return ""
    return strings.tr("Connect") + " " + " and ".join("“%s”" % n for n in names)


def row_text(row: Dict[str, Any]) -> str:
    """一列在清單上長什麼樣：**結論一行，細節一行**（J5／J6）。

    ``× “Denoise” has no input yet``
    ``   “Denoise” · “Image streams” — Drag a line from the card that…``

    為什麼是兩行而不是一行
    ----------------------
    走查看到的那一列**要捲到右邊才讀得完**，而一條讀不完的錯誤訊息跟沒有是
    一樣的（J5）。攤成一行也不行：`title` 是結論（「這張卡還沒接上東西」）、
    `text` 是怎麼修，兩件事擠在同一行的時候使用者要先讀完才知道嚴不嚴重 ——
    而他要的第一個答案是「先修哪一個」（J6：**先講結論**）。

    兩個都有才兩行：`title` 與 `text` 一樣（沒搬的那幾條有時是這樣）就只有
    一行 —— 同一句話印兩次比較糟。
    """
    mark = LEVEL_MARK.get(str(row.get("level", "")), "·")
    title = str(row.get("title") or "").strip()
    text = str(row.get("text") or "").strip()
    if not title or title == text:
        return "%s  %s" % (mark, text or title)
    if not text:
        return "%s  %s" % (mark, title)
    return "%s  %s\n     %s" % (mark, title, text)


class ProblemsBar(QWidget):
    """``[✕ 2 errors · 1 warning — fix the errors before running]  [清單 ▾]``

    點清單裡的一項 → :attr:`problem_activated`（帶 node id）。
    宿主接了去選中那張卡並捲到它 —— **這個 widget 不碰 model**。
    """

    #: 使用者點了清單裡的一項；值是那張卡的 node id（``""`` = 這一條不指向
    #: 任何一張卡，例如「這份 recipe 沒有這個 route」）。
    problem_activated = Signal(str)

    #: 使用者按了某一列底下的「Connect ＿」（F124）：``(接到哪張卡, [從哪幾張卡])``。
    #: 宿主走跟手拉的線同一條路（`canvas_edges.connect_into`）—— **這個 widget
    #: 不碰 model**，跟 :attr:`problem_activated` 同一個理由。
    connect_requested = Signal(str, list)

    #: 清單最多長這麼高（超過就自己捲）。一份 30 條的清單把設定區整個推出
    #: 畫面的話，使用者就得先關掉它才能去修 —— 而他要修的就是清單上那一條。
    #:
    #: 2026-09-19（F118 第 4 步）：132 → 168。一列從一行變兩行（結論一行、
    #: 細節一行），132 只剩得下一列半 —— 而「先修哪一個」要看得到第二列。
    LIST_MAX_HEIGHT = 168

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

        # 「點一列會跳到那張卡」以前只寫在**按鈕的 tooltip** 上 —— 一個要把
        # 滑鼠停在別的地方才看得到的說明，等於沒有說明（J5 的「帶我去」）。
        self.hint = QLabel("", self)
        self.hint.setObjectName("paramHint")
        self.hint.setContentsMargins(10, 0, 8, 4)
        self.hint.hide()
        lay.addWidget(self.hint)

        self.list = QListWidget(self)
        self.list.setObjectName("problemsList")
        self.list.setMaximumHeight(self.LIST_MAX_HEIGHT)
        self.list.setAlternatingRowColors(True)
        # ⚠ **換行，不要水平捲軸**（J5）：走查看到的那一列要捲到右邊才讀得完，
        # 而一條讀不完的錯誤訊息跟沒有是一樣的。
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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
            item = QListWidgetItem(row_text(row), self.list)
            item.setData(Qt.UserRole, row["node_id"])
            item.setToolTip("%s\n%s" % (row["title"], row["text"])
                            if row["title"] else row["text"])
            if row["level"] == "error":
                # 顏色是**冗餘**的第二個訊號 —— 前面那個 ``✕`` 已經把意思講完
                # 了（U13：紅綠對色覺缺陷者不可分辨，而這一列是「還能不能跑」
                # 唯一的答案）。
                item.setForeground(QColor(TOKENS["danger_text"]))
            if row["connect"]:
                self._add_connect_row(row)
        # 指得到卡片的那幾條才講「點一下會跳過去」—— 一條指不到任何一張卡的
        # lint（「這份 recipe 沒有這個 route」那種）點下去不會跳，而一句做不到
        # 的提示比沒有提示糟。
        self.hint.setText(strings.tr("Click a line to go to that card.")
                          if any(r["node_id"] for r in self._rows) else "")
        if not self._rows:
            self.set_open(False)
        else:
            self.hint.setVisible(self._open and bool(self.hint.text()))
        # **沒有話要說就整條不畫**（F117 H2）。走查記的是「底部兩條狀態列」——
        # 而它們長得一模一樣（一行字 ＋ 右邊一顆鈕），使用者分不出哪一條在講
        # 什麼。那兩條**確實是兩件事**（這一條講的是常駐的狀態「現在能不能
        # 跑」，狀態列講的是剛剛發生了什麼），所以答案不是把它們併成一條。
        #
        # 答案是：`Nothing is blocking a run.` 是一句**永遠不會帶來消息**的
        # 話，而它佔著 26 px 常駐在畫面最底下。收掉之後，第二條只在它真的有
        # 話要說的時候出現 —— 那時候它帶著 ✕／⚠ 與顏色，跟狀態列一眼分得開。
        #
        # ⚠ 這也是這個 repo 自己的規矩：**一條常駐的 warning 會被學會忽略，
        # 而真的那一條也跟著被忽略**（`Issue` 的 `info` 那一級寫著同一句）。
        self.setVisible(bool(self._rows))

    def _add_connect_row(self, row: Dict[str, Any]) -> None:
        """那一列底下的「Connect ＿」鈕（F124）。

        **另開一列放鈕**，不是把鈕塞進文字那一列：文字那一列照舊是一個普通的
        項目（點了跳到那張卡、測試讀得到它的字），鈕是它下面緊貼的一列。
        """
        item = QListWidgetItem("", self.list)
        item.setFlags(Qt.ItemIsEnabled)
        item.setData(Qt.UserRole, row["node_id"])
        holder = QWidget(self.list)
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(24, 0, 8, 4)
        btn = QPushButton(row["connect_text"], holder)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda _=False, r=row: self.connect_requested.emit(
            r["node_id"], list(r["connect"])))
        hl.addWidget(btn)
        hl.addStretch(1)
        item.setSizeHint(holder.sizeHint())
        self.list.setItemWidget(item, holder)

    def connect_buttons(self) -> List[QPushButton]:
        """清單裡**現在**的「Connect ＿」鈕（測試與鍵盤路徑用）。

        ⚠ 不用 ``findChildren``：`clear()` 拿掉的那幾列，它們的 widget 是
        ``deleteLater`` 的 —— 事件迴圈還沒轉之前照樣找得到，於是每刷新一次
        清單上就「多一顆」。問每一列自己的 widget 才是現在的樣子。
        """
        out: List[QPushButton] = []
        for i in range(self.list.count()):
            holder = self.list.itemWidget(self.list.item(i))
            if holder is not None:
                out.extend(holder.findChildren(QPushButton))
        return out

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
        self.hint.setVisible(show and bool(self.hint.text()))
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

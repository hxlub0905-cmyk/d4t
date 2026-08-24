# d4t Studio — 判定段的編輯器（F22-UI，2026-08-23）。
"""判定段：**一個門檻（兩類）** 或 **一串規則（多類別）**。

為什麼是一個切換，不是兩個並存的區塊
------------------------------------
引擎那一邊 ``score`` 與 ``decide`` **不能並存**（`validate` 的
``ambiguous-decision`` 是 error）—— 同一件事兩個地方存是這個 repo 最怕的形狀。
面板照著那條規矩長：一次只看得到一種，切換是「換一種」而不是「多一種」。

切成多類別時，**現有的門檻會被翻成第一條規則**（`RecipeModel.use_decide`）。
使用者調了半天的那個數字是他的工作成果，不該因為換一個檢視就沒了。

為什麼規則要能拖／要有 ▲▼
--------------------------
判定是**由上往下讀的，第一個對上的就是答案**。所以「換順序」不是排版，是
**換優先權** —— 它跟改門檻是同一級的動作，要在畫面上一樣好按。

為什麼每一條規則右邊有顆數
--------------------------
跟 F18 的灰階面板同一個立論：調規則的人是**一邊改一邊看**的，「先想好一個
門檻再輸入」那個順序是反的。

⚠ 那個數字是 **bin 的顆數**，不是「這條規則抓到幾顆」。兩者只有在「一個 bin
一條規則」時相同，而規則可以共用 bin。所以標籤上寫的是 ``bin 2 · 16 顆``——
講的是哪一個量，不留給使用者猜。要做到逐規則的顆數，得把「第幾條對上」帶進
`DefectResult`，而那會動到 SQLite schema 與 CSV 的欄（見
`docs/plans/F22-adc-multiclass.md` §4）。

這個模組**直接改 model**（不是發 signal 讓 Studio 轉手）—— 它是一個 Studio 層
的面板而不是可重用元件，而 `RecipeModel` 本來就有 listener 機制負責把改動廣播
回畫布與其他面板。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFrame,
    QHBoxLayout, QLabel, QScrollArea,
    QLineEdit, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from .widgets import small_button, split_labelled

__all__ = ["DecidePanel"]

#: 「插入數字 ▾」那一列的標題（沒有東西可插的時候換一句話）。
_PICK_PLACEHOLDER = "Insert a number…"
_PICK_EMPTY = "No numbers upstream yet"


def _feature_combo(items: Sequence[str], on_pick) -> QComboBox:
    """共用的「插入數字 ▾」（F21-B 的那一支，這裡是它的第三個使用者）。

    顯示的是「名字 — 誰算的」，**送出去的只有名字** —— 插錯半邊的話使用者會
    得到一個永遠指不到的變數名，而錯誤要等跑起來才出現。
    """
    combo = QComboBox()
    combo.addItem(_PICK_PLACEHOLDER if items else _PICK_EMPTY, "")
    combo.setEnabled(bool(items))
    for it in items:
        name, owner = split_labelled(it)
        if name:
            combo.addItem("%s   —   %s" % (name, owner) if owner else name, name)
    combo.setToolTip("Pick one of the numbers the cards above work out - "
                     "it is put in at the cursor.")

    def _picked(i: int) -> None:
        if int(i) <= 0:
            return
        token = str(combo.itemData(int(i)) or "")
        combo.setCurrentIndex(0)
        if token:
            on_pick(token)

    combo.activated.connect(_picked)
    return combo


def _tight(w: QWidget, width: int = 0) -> QWidget:
    """不准橫向長大。

    ``small_button`` 的邊長由 QSS 的 ``control_sm`` 給（`widgets.small_button`
    的說明），而**沒有套主題的時候它會撐開** —— 實測（獨立截圖）三顆 ▲▼✕ 各佔
    了 90 px，把它們旁邊那個「條件」欄壓成一格裝得下 `= 3` 的小框。
    元件不該靠外面有沒有套 QSS 才排得對，所以這裡把它釘死。
    """
    w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    if width:
        w.setFixedWidth(int(width))
    return w


def _insert_at_cursor(edit: QLineEdit, token: str) -> str:
    text = edit.text()
    pos = max(0, min(edit.cursorPosition(), len(text)))
    new = text[:pos] + token + text[pos:]
    edit.setText(new)
    edit.setCursorPosition(pos + len(token))
    return new


class _Row(QFrame):
    """一列（中間值／規則）—— 只是一個帶邊界的容器，讓拖曳與刪除有東西可抓。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("decideRow")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.lay = lay


class DecidePanel(QWidget):
    """判定段的面板（見模組說明）。"""

    #: 使用者按了「試跑」以外的任何改動都走 model 的 listener，所以這裡只留
    #: 一個訊號：切換了檢視（Studio 要重排右邊那一欄的高度）。
    mode_changed = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model: Any = None
        self._features: List[str] = []
        self._counts: Dict[int, int] = {}
        self._purity: Dict[int, Any] = {}
        self._building = False
        #: 有人在打字時來的重建請求記在這裡，等焦點離開再補（見 `refresh`）。
        self._stale = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 8, 0)
        outer.setSpacing(10)

        title = QLabel("Decision", self)
        title.setObjectName("paramTitle")
        outer.addWidget(title)

        self.mode = QCheckBox("Sort into several classes (not just one threshold)",
                              self)
        self.mode.setToolTip(
            "Off: one score and one threshold - two bins only.\n"
            "On: a list of rules read top to bottom; the first one that "
            "matches is the answer.")
        self.mode.toggled.connect(self._on_mode)
        outer.addWidget(self.mode)

        self.head = QLabel("", self)
        self.head.setObjectName("paramStepHelp")
        self.head.setWordWrap(True)
        outer.addWidget(self.head)

        # 這一欄的寬度是**使用者拖的**（splitter），而一條規則有八個東西
        # （條件／bin／名字／▲▼✕／顆數）。窄的時候截圖實測會把最右邊的
        # 「純度」切掉、把條件欄壓成一格裝得下 `> 0` 的小框 —— 而被切掉的
        # 那一半看起來只是「這個功能沒做」。所以整段放進一個捲動區：
        # 內容需要多少寬就多少寬，欄位窄就捲。
        self.body = QWidget()
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, 0, 0, 0)
        self.body_lay.setSpacing(12)

        self.scroll = QScrollArea(self)
        self.scroll.setWidget(self.body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(self.scroll, 1)

    # ---- 外面餵進來的東西 --------------------------------------------------
    def set_model(self, model: Any) -> None:
        self._model = model
        self.refresh()

    def set_features(self, labelled: Sequence[str]) -> None:
        """「插入數字 ▾」的清單（``"名字\\t誰算的"``）。"""
        new = [str(x) for x in (labelled or [])]
        if new != self._features:
            self._features = new
            self.refresh()

    def set_counts(self, counts: Optional[Dict[int, int]],
                   purity: Optional[Sequence[Dict[str, Any]]] = None) -> None:
        """這一批的 ``{bin: 顆數}``，以及（有 ground truth 時）每個 bin 的純度。

        **空的就是空的** —— 還沒跑過的時候不要顯示 0，那會讓人以為「這一格
        一顆都沒有」。同一條規矩在 F18 的面板上寫過。
        """
        self._counts = {int(k): int(v) for k, v in (counts or {}).items()}
        self._purity = {}
        for row in (purity or []):
            b = row.get("bin")
            if isinstance(b, int):
                self._purity[b] = row
        self.refresh()

    # ---- 重建 ---------------------------------------------------------------
    def refresh(self, force: bool = False) -> None:
        """重建。**有人正在某一格裡打字就跳過**（除非 ``force``）。

        `set_features` / `set_counts` 是外面餵進來的，而它們可能在使用者正在
        打字的時候到（試跑跑完、換了一張卡）。重建會把游標搶走。
        """
        if self._building:
            return
        if not force and self._typing():
            self._stale = True
            return
        self._stale = False
        self._building = True
        try:
            self._rebuild()
        finally:
            self._building = False

    def _restructure(self, fn, *a) -> None:
        """加／刪／換順序 —— 這些會**改變有幾列**，所以做完要重建。

        ⚠ **打字不走這裡。** `textEdited` 只寫 model、不重建：重建會把游標從
        使用者正在打的那一格搶走（這個 repo 記過同一個形狀 ——
        `set_dynamic_choices` 就是為了這件事才「只換內容、跳過有游標的那一格」）。
        所以這個面板**不訂閱 model 的 listener**，什麼時候重建由動作決定。
        """
        fn(*a)
        self.refresh(force=True)

    def _clear(self) -> None:
        while self.body_lay.count():
            item = self.body_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _rebuild(self) -> None:
        self._clear()
        m = self._model
        if m is None:
            return
        on = getattr(m, "decide", None) is not None
        self.mode.setChecked(on)
        if on:
            self.head.setText("Read top to bottom - the first rule that "
                              "matches is the answer. Reordering the rules "
                              "is how you change which one wins.")
            self._build_decide()
        else:
            self.head.setText("Work the measured numbers into one score, then "
                              "split into two bins with a threshold.")
            self._build_binary()

    # ---- 兩類（老路）--------------------------------------------------------
    def _build_binary(self) -> None:
        m = self._model
        edit = QLineEdit(str(m.expr or ""))
        edit.setPlaceholderText("e.g. glv_max - glv_median")
        edit.textEdited.connect(lambda t: m.set_expr(str(t)))
        self.body_lay.addWidget(self._labelled("Score", edit,
                                               _feature_combo(
                                                   self._features,
                                                   lambda tok: m.set_expr(
                                                       _insert_at_cursor(edit, tok)))))

        spin = QDoubleSpinBox()
        spin.setDecimals(3)
        spin.setRange(-1e9, 1e9)
        spin.setSingleStep(0.5)
        spin.setValue(float(m.threshold))
        spin.setToolTip("score >= threshold -> bin 1, otherwise bin 0")
        spin.valueChanged.connect(lambda v: m.set_threshold(float(v)))
        self.body_lay.addWidget(self._labelled("Threshold", spin))

    # ---- 多類別 -------------------------------------------------------------
    def _build_decide(self) -> None:
        m = self._model
        d = m.decide

        # ── 中間值 ──
        self.body_lay.addWidget(self._section(
            "Working numbers",
            "These land in the CSV like any other number, so you can plot "
            "them."))
        for i, item in enumerate(d.let):
            self.body_lay.addWidget(self._let_row(i, item))
        add_let = small_button("+ Add a line")
        add_let.clicked.connect(lambda: self._restructure(m.add_let))
        self.body_lay.addWidget(add_let)

        if getattr(d, "tree", None) is not None:
            # ── 判定樹模式（F24 ③）──
            # 樹住在畫布上，這裡不擺第二份編輯器：`rules` 與 `tree` 並存是
            # `ambiguous-decision` 的 error，而「同一件事有兩個編輯入口」正是
            # 那個形狀的 UI 版。
            self.body_lay.addWidget(self._section(
                "Sorting",
                "This recipe sorts with the decision tree on the canvas"))
            note = QLabel("Click a diamond on the canvas to edit a step, "
                          "or a tray to edit a class.")
            note.setObjectName("paramHint")
            note.setWordWrap(True)
            self.body_lay.addWidget(note)
        else:
            # ── 規則 ──
            self.body_lay.addWidget(self._section(
                "Rules", "Top to bottom - the first one that matches wins"))
            for i, rule in enumerate(d.rules):
                self.body_lay.addWidget(self._rule_row(i, rule, len(d.rules)))
            add_rule = small_button("+ Add a rule")
            add_rule.clicked.connect(lambda: self._restructure(m.add_rule))
            self.body_lay.addWidget(add_rule)

            # ── 都沒對上 ──
            self.body_lay.addWidget(self._section("Nothing matched", ""))
            self.body_lay.addWidget(self._otherwise_row(d))

        # ── 分數 ──
        self.body_lay.addWidget(self._section(
            "Score",
            "Written into the KLARF DSIZE, and what Top-N sorts by"))
        sc = QLineEdit(str(d.score or ""))
        sc.setPlaceholderText("empty = the score is 0")
        sc.textEdited.connect(lambda t: m.set_decide_score(str(t)))
        self.body_lay.addWidget(self._labelled(
            "", sc, _feature_combo(self._features,
                                   lambda tok: m.set_decide_score(
                                       _insert_at_cursor(sc, tok)))))

    def _let_row(self, i: int, item: Any) -> QWidget:
        m = self._model
        row = _Row(self)
        name = QLineEdit(str(item.name))
        name.setPlaceholderText("give it a name")
        name.setFixedWidth(120)
        name.textEdited.connect(lambda t, k=i: m.set_let(k, name=str(t)))
        eq = QLabel("=")
        eq.setObjectName("paramHint")
        expr = QLineEdit(str(item.expr))
        expr.setPlaceholderText("e.g. cmp_delta_median * cd_deq")
        expr.setMinimumWidth(140)
        expr.textEdited.connect(lambda t, k=i: m.set_let(k, expr=str(t)))
        pick = _feature_combo(self._features,
                              lambda tok, e=expr, k=i:
                              m.set_let(k, expr=_insert_at_cursor(e, tok)))
        pick.setFixedWidth(140)
        # 「跟整批比」（F23 期3）：這一行算完之後換算成整批尺度，判定重算。
        # 跨顆的數字（「這一顆比整批亮多少」）在單顆的 run 裡根本不存在 ——
        # 所以它是這一行的一個屬性，不是另一張卡（F24 §5 定的家）。
        scale = QComboBox()
        for text, val in (("as measured", ""),
                          ("z vs the batch", "z"),
                          ("percentile in batch", "percentile")):
            scale.addItem(text, val)
        j = scale.findData(str(getattr(item, "scale", "") or ""))
        scale.setCurrentIndex(max(0, j))
        scale.setToolTip(
            "How this number is used by the rules:\n"
            "as measured - each defect keeps its own value;\n"
            "z vs the batch - (value - batch median) / spread, so 'how "
            "unusual is this defect';\n"
            "percentile in batch - where it ranks, 0 to 100.\n"
            "Batch scaling needs a run over the batch - the preview shows "
            "the raw value.")
        scale.activated.connect(
            lambda j2, c=scale, k=i:
            m.set_let(k, scale=str(c.itemData(int(j2)) or "")))
        rm = _tight(small_button("✕"), 24)
        rm.setToolTip("Take this line out")
        rm.clicked.connect(lambda _=False, k=i: self._restructure(m.remove_let, k))
        for w in (name, eq, expr, pick, scale, rm):
            row.lay.addWidget(w, 1 if w is expr else 0)
        return row

    def _rule_row(self, i: int, rule: Any, n: int) -> QWidget:
        m = self._model
        row = _Row(self)

        num = QLabel("%d" % (i + 1))
        num.setObjectName("paramHint")
        num.setMinimumWidth(16)
        num.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        when = QLineEdit(str(rule.when))
        when.setPlaceholderText("e.g. contrast > 30")
        when.setToolTip("Anything other than 0 counts as a match. "
                        "Comparisons give 1 or 0,\nso (a > 5) * (b < 2) "
                        "means both have to hold.")
        when.setMinimumWidth(140)
        when.textEdited.connect(lambda t, k=i: m.set_rule(k, when=str(t)))

        arrow = QLabel("→")
        arrow.setObjectName("paramHint")

        binspin = QSpinBox()
        binspin.setRange(0, 999)
        binspin.setPrefix("bin ")
        binspin.setValue(int(rule.bin))
        binspin.setFixedWidth(66)
        binspin.valueChanged.connect(lambda v, k=i: m.set_rule(k, bin=int(v)))

        label = QLineEdit(str(rule.label))
        label.setPlaceholderText("call it")
        label.setFixedWidth(92)
        label.textEdited.connect(lambda t, k=i: m.set_rule(k, label=str(t)))

        up = _tight(small_button("▲"), 24)
        up.setToolTip("Move up - reordering is how you change which rule wins")
        up.setEnabled(i > 0)
        up.clicked.connect(lambda _=False, k=i: self._restructure(m.move_rule, k, -1))
        dn = _tight(small_button("▼"), 24)
        dn.setToolTip("Move down")
        dn.setEnabled(i < n - 1)
        dn.clicked.connect(lambda _=False, k=i: self._restructure(m.move_rule, k, +1))
        rm = _tight(small_button("✕"), 24)
        rm.setToolTip("Take this rule out")
        rm.clicked.connect(lambda _=False, k=i: self._restructure(m.remove_rule, k))

        for w in (num, when, arrow, binspin, label, up, dn, rm):
            row.lay.addWidget(w, 1 if w is when else 0)

        cnt = self._count_label(int(rule.bin))
        if cnt is None:
            return row
        # **顆數放在第二行**，不是接在後面。第一版是一列八個東西，而這一欄的
        # 寬度是使用者拖的 —— 實測（截圖）預設寬度 437 px、內容要 592 px，
        # 於是**最有價值的那一格（顆數與純度）變成要捲才看得到**。
        # 它是這條規則的註腳，本來就該在下面。
        return self._with_note(row, cnt)

    def _otherwise_row(self, d: Any) -> QWidget:
        m = self._model
        row = _Row(self)
        spacer = QLabel("")
        spacer.setMinimumWidth(16)
        rest = QLabel("(anything else)")
        rest.setObjectName("paramHint")
        arrow = QLabel("→")
        arrow.setObjectName("paramHint")
        binspin = QSpinBox()
        binspin.setRange(0, 999)
        binspin.setPrefix("bin ")
        binspin.setValue(int(d.otherwise_bin))
        binspin.setFixedWidth(66)
        binspin.valueChanged.connect(lambda v: m.set_otherwise(bin=int(v)))
        label = QLineEdit(str(d.otherwise_label))
        label.setPlaceholderText("call it")
        label.setFixedWidth(92)
        label.textEdited.connect(lambda t: m.set_otherwise(label=str(t)))
        for w in (spacer, rest, arrow, binspin, label):
            row.lay.addWidget(w, 1 if w is rest else 0)
        cnt = self._count_label(int(d.otherwise_bin))
        return row if cnt is None else self._with_note(row, cnt)

    # ---- 小工具 -------------------------------------------------------------
    def _with_note(self, row: QWidget, note: QWidget) -> QWidget:
        """一列 ＋ 它下面那一行小字（顆數／純度）。"""
        box = QWidget(self)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        lay.addWidget(row)
        indent = QHBoxLayout()
        indent.setContentsMargins(22, 0, 0, 0)
        indent.addWidget(note)
        indent.addStretch(1)
        lay.addLayout(indent)
        return box

    def _count_label(self, b: int) -> Optional[QLabel]:
        """``bin N · 12 顆 · 純度 81%``。**還沒跑過就不畫** —— 見 `set_counts`。"""
        if b not in self._counts:
            return None
        bits = ["bin %d · %d defects" % (b, self._counts[b])]
        row = self._purity.get(b)
        if row and row.get("purity") is not None:
            bits.append("%.0f%% real" % (row["purity"] * 100))
        lab = QLabel("   ".join(bits))
        lab.setObjectName("paramHint")
        lab.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        lab.setToolTip("How many of this batch landed in bin %d.\n"
                       "This is the bin's count, not what this one rule "
                       "caught -\ntwo rules can share a bin." % b)
        return lab

    def _section(self, title: str, hint: str) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(2)
        t = QLabel(title, w)
        t.setObjectName("paramLabel")
        lay.addWidget(t)
        if hint:
            h = QLabel(hint, w)
            h.setObjectName("paramHint")
            h.setWordWrap(True)
            lay.addWidget(h)
        return w

    def _labelled(self, text: str, *widgets: QWidget) -> QWidget:
        w = QWidget(self)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        if text:
            lab = QLabel(text, w)
            lab.setObjectName("paramLabel")
            lab.setMinimumWidth(72)
            lay.addWidget(lab)
        for i, x in enumerate(widgets):
            lay.addWidget(x, 1 if i == 0 else 0)
        return w

    # ---- 切換 ---------------------------------------------------------------
    def _typing(self) -> bool:
        """這個面板裡有沒有哪一格**真的**拿著鍵盤焦點。

        ⚠ 判準是 ``w.hasFocus()``，不是 ``self.focusWidget() is not None``。
        後者是「這個子樹裡最後一個被 setFocus 的是誰」—— 而 Qt 在視窗顯示時
        會自動把焦點給 tab 順序裡的第一個可聚焦元件，所以它**幾乎永遠非
        None**，於是這個守衛會把每一次重建都擋掉（實測：拖完門檻放開之後
        那一格還是 0.0，因為面板從頭到尾沒有重建過）。
        """
        app = QApplication.instance()
        w = app.focusWidget() if app is not None else None
        return bool(w is not None and w.hasFocus() and self.isAncestorOf(w)
                    and isinstance(w, (QLineEdit, QSpinBox, QDoubleSpinBox)))

    def focusOutEvent(self, ev) -> None:            # noqa: N802 — Qt 的名字
        super().focusOutEvent(ev)
        if self._stale:
            self.refresh(force=True)

    def _on_mode(self, on: bool) -> None:
        if self._building or self._model is None:
            return
        self._model.use_decide(bool(on))
        self.mode_changed.emit(bool(on))
        self.refresh(force=True)

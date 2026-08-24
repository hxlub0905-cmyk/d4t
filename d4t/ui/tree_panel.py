# d4t Studio — 判定樹一步的編輯面板（F24 ③，2026-08-24）。
"""點畫布上的菱形（或托盤）→ 右欄變成**這一步**的編輯面板。

跟點卡片同一條路、零新概念（mockup「Editing one step」定稿的形狀）：

* QUESTION：`when` 表達式 ＋「Insert a number ▾」（F21-B 那一支的第四個使用者）。
* Yes → / No → 各自是「一個類別」（名字＋bin，可以就地改）或「另一步」
  （一句摘要＋跳過去編它）。加一步＝把某一邊從葉子換成新菱形。
* THIS BATCH：這一步「有幾顆流到這裡、幾顆走 yes / no」—— 試跑過才有
  （F18：不顯示 0）。
* Insert step above ／ Remove step。拿掉一步＝它的 no 邊接回上游（F24 §6）；
  yes 邊上掛著**一整個子樹**時先問過使用者 —— undo 回得來，但「一個問題把
  三層樹默默吃掉」不是一步該有的重量。

跟 `DecidePanel` 同一個立場：**直接改 model**（Studio 層的面板，`RecipeModel`
的 listener 會把改動廣播回畫布），打字不重建（重建會把游標搶走）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QDoubleSpinBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QScrollArea, QSlider, QSpinBox,
    QVBoxLayout, QWidget,
)

from ..core.pipeline.recipe import TreeLeaf, TreeStep
from .decide_panel import _feature_combo, _insert_at_cursor
from .tree_scene import (
    OPS, count_yes, display_tree, format_condition, parse_simple_condition,
    rows_reaching, suggest_condition,
)
from .widgets import _make_slider, clear_layout_parked, small_button, split_labelled

__all__ = ["TreePanel"]


class TreePanel(QWidget):
    """判定樹一步／一類的編輯面板。`show_path` 決定現在編哪一步。"""

    #: 面板要求跳到另一步（按了「Edit」那顆鈕、或結構變了要跟著移）。
    #: Studio 接住它：換選取、重畫畫布上的亮框。
    step_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model: Any = None
        self._path: str = ""
        self._features: List[str] = []
        #: ``路徑前綴 → 顆數``（tree_scene.flow_counts 的形狀）。None = 沒跑過。
        self._counts: Optional[Dict[str, int]] = None
        self._building = False
        #: 見 `widgets.clear_layout_parked`（閃退的結構性修正，F25）。
        self._parked: list = []
        #: 這一批試跑的結果（F25）。滑桿的範圍與「幾顆說 yes」都吃它 ——
        #: 沒跑過就是空的，那時候一個數字都不畫（F18）。
        self._rows: List[Dict[str, Any]] = []
        #: 哪幾步使用者切到了「自己寫算式」（複合條件本來就只能那樣編）。
        self._advanced: set = set()
        #: 拖滑桿時就地更新的那一行字（不重建 —— 重建會把滑桿從手上搶走）。
        self._yes_label: Optional[QLabel] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body = QWidget(self)
        self.body_lay = QVBoxLayout(body)
        self.body_lay.setContentsMargins(8, 8, 8, 8)
        self.body_lay.setSpacing(6)
        self.body_lay.addStretch(1)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(body)
        outer.addWidget(scroll)

    # ---- 外部餵進來的 ------------------------------------------------------
    def set_model(self, model: Any) -> None:
        self._model = model
        self.refresh()

    def set_features(self, items: Sequence[str]) -> None:
        new = [str(x) for x in items]
        if new != self._features:
            self._features = new
            self.refresh()

    def set_counts(self, counts: Optional[Dict[str, int]]) -> None:
        self._counts = None if counts is None else dict(counts)
        self.refresh()

    def set_rows(self, rows: Any) -> None:
        """這一批試跑的結果（F25）—— 導引式問題的滑桿與即時顆數吃它。"""
        self._rows = list(rows or [])
        self.refresh()

    def show_path(self, path: str) -> None:
        """開始編路徑指到的那一步（菱形）或那一類（托盤）。"""
        self._path = str(path)
        self.refresh(force=True)

    def path(self) -> str:
        return self._path

    # ---- 重建 --------------------------------------------------------------
    def _typing(self) -> bool:
        """使用者的手正放在這個面板的某一格上嗎。

        ⚠ 範圍要含**滑桿與下拉**，不只文字框（F25）：導引式問題是「一邊拖
        一邊看」的，而重建會把滑桿從手上搶走 —— 拖到一半突然失去控制，
        比慢一點更難用。判準跟 `DecidePanel._typing` 同一套（真的拿著焦點、
        而且在這個面板裡），不是 ``focusWidget() is not None``（那幾乎永遠
        非 None，會把每一次重建都擋掉）。
        """
        app = QApplication.instance()
        w = app.focusWidget() if app is not None else None
        return bool(w is not None and w.hasFocus() and self.isAncestorOf(w)
                    and isinstance(w, (QLineEdit, QAbstractSpinBox, QSlider,
                                       QComboBox)))

    def refresh(self, force: bool = False) -> None:
        if self._building or (not force and self._typing()):
            return
        self._building = True
        try:
            self._rebuild()
        finally:
            self._building = False

    def _clear(self) -> None:
        clear_layout_parked(self.body_lay, self._parked)

    def _node(self) -> Any:
        m = self._model
        return None if m is None else m.tree_node(self._path)

    def _rebuild(self) -> None:
        self._clear()
        node = self._node()
        if node is None:
            note = QLabel("Click a diamond on the canvas to edit that step.")
            note.setObjectName("paramHint")
            note.setWordWrap(True)
            self.body_lay.addWidget(note)
            self.body_lay.addStretch(1)
            return
        if isinstance(node, TreeLeaf):
            self._build_leaf(node)
        else:
            self._build_step(node)
        self.body_lay.addStretch(1)

    # ---- 一步（菱形）-------------------------------------------------------
    def _build_step(self, node: TreeStep) -> None:
        self.body_lay.addWidget(self._section("Question"))
        simple = parse_simple_condition(node.when)
        # 空的問題（剛加的一步）也走導引式 —— 一張空白的算式框正是使用者
        # 卡住的地方（2026-08-24：「我目前不太知道怎麼用」）。
        if self._path in self._advanced or (simple is None
                                            and str(node.when).strip()):
            self._build_expression(node)
        else:
            self._build_guided(simple)

        self.body_lay.addWidget(self._side_row("Yes →", self._path + "y",
                                               node.yes))
        self.body_lay.addWidget(self._side_row("No →", self._path + "n",
                                               node.no))

        batch = self._batch_line()
        if batch:
            self.body_lay.addWidget(self._section("This batch", batch))

        row2 = QWidget(self)
        lay2 = QHBoxLayout(row2)
        lay2.setContentsMargins(0, 0, 0, 0)
        ins = small_button("+ Insert step above", shape="wide")
        ins.setToolTip("Ask a new question before this one - everything "
                       "here moves to its no side.")
        ins.clicked.connect(self._insert_above)
        rm = small_button("✕ Remove step", shape="wide")
        rm.setToolTip("The no side takes this step's place.")
        rm.clicked.connect(self._remove_step)
        lay2.addWidget(ins)
        lay2.addWidget(rm)
        # 「自己寫算式」是這一步的**另一種編法**，所以跟加/刪擺在同一列 ——
        # 夾在問題與 Yes/No 中間的話，它會被讀成一個段落標題。
        if self._path not in self._advanced:
            adv = small_button("Expression…", shape="wide")
            adv.setToolTip("Write this question as an expression instead - "
                           "for one that needs more than one comparison, "
                           "e.g. (a > 5) * (b < 2).")
            adv.clicked.connect(self._go_advanced)
            lay2.addWidget(adv)
        lay2.addStretch(1)
        self.body_lay.addWidget(row2)

    # ---- 導引式的問題（F25）------------------------------------------------
    def _feature_names(self) -> List[str]:
        """可以拿來問的數字（`labelled_features` 的前半）。"""
        out: List[str] = []
        for item in self._features:
            name, _owner = split_labelled(item)
            if name and name not in out:
                out.append(name)
        return out

    def _rows_here(self) -> List[Dict[str, Any]]:
        """流到這一步的那些顆（滑桿的範圍與即時顆數都只看它們）。"""
        m = self._model
        if m is None or not self._rows:
            return []
        tree = display_tree(getattr(m, "decide", None))
        return rows_reaching(tree, self._rows, self._path)

    def _range_for(self, name: str, value: float):
        """這個數字在**流到這裡的顆**上的範圍（滑桿用）。回 ``(lo, hi)``。"""
        vals = [float(v) for r in self._rows_here()
                for v in [(r.get("features") or {}).get(str(name))]
                if isinstance(v, (int, float))]
        if len(vals) >= 2 and max(vals) > min(vals):
            lo, hi = min(vals), max(vals)
            pad = (hi - lo) * 0.05
            lo, hi = lo - pad, hi + pad
        else:
            span = abs(float(value)) or 1.0
            lo, hi = float(value) - span, float(value) + span
        # 現在的值一定要在範圍裡，否則滑桿會把它拉走（改到一個沒人要的數）。
        return min(lo, float(value)), max(hi, float(value))

    def _build_guided(self, simple) -> None:
        """``[哪個數字 ▾] [比什麼 ▾] [多少] + 滑桿`` —— 打不出算式也問得出問題。"""
        m = self._model
        name, op, value = simple or ("", ">", 0.0)
        names = self._feature_names()
        if name and name not in names:
            names.insert(0, name)       # recipe 裡指到的數字永遠留著

        row = QWidget(self)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        which = QComboBox()
        which.addItem("(pick a number…)", "")
        for n in names:
            which.addItem(n, n)
        i = which.findData(name)
        which.setCurrentIndex(max(0, i))
        which.setToolTip("Which of the measured numbers this step asks about.")
        which.setMinimumWidth(120)
        which.activated.connect(
            lambda j, c=which: self._guided_changed(
                name=str(c.itemData(j) or ""), rebuild=True))

        opbox = QComboBox()
        opbox.setFixedWidth(118)
        for sym, text in OPS:
            opbox.addItem(text, sym)
        j = opbox.findData(op)
        opbox.setCurrentIndex(max(0, j))
        opbox.activated.connect(
            lambda k, c=opbox: self._guided_changed(op=str(c.itemData(k))))

        lo, hi = self._range_for(name, value)
        spin = QDoubleSpinBox()
        spin.setFixedWidth(84)
        span = hi - lo
        spin.setDecimals(0 if span > 200 else (2 if span > 1 else 4))
        spin.setRange(lo, hi)
        spin.setSingleStep(max(span / 100.0, 1e-6))
        spin.setValue(float(value))
        spin.setToolTip("The value to compare against. Drag the slider and "
                        "watch the count below.")
        spin.valueChanged.connect(lambda v: self._guided_changed(value=float(v)))

        lay.addWidget(which, 1)
        lay.addWidget(opbox)
        lay.addWidget(spin)
        self.body_lay.addWidget(row)

        slider = _make_slider({"type": "float", "min": lo, "max": hi,
                               "help": "Drag to move the threshold."}, spin)
        if slider is not None:
            self.body_lay.addWidget(slider)

        # 即時顆數：**拖的時候就地改這一行**（不重建）。沒跑過就不畫 —— 一個
        # 「0 of 0」比沒有更糟（F18）。
        self._yes_label = QLabel("")
        self._yes_label.setObjectName("paramHint")
        self._yes_label.setWordWrap(True)
        self._sync_yes_label(name, op, value)
        self.body_lay.addWidget(self._yes_label)



    def _sync_yes_label(self, name: str, op: str, value: float) -> None:
        if self._yes_label is None:
            return
        rows = self._rows_here()
        if not rows or not name:
            self._yes_label.setText("")
            return
        yes, n = count_yes(rows, name, op, float(value))
        if not n:
            self._yes_label.setText("")
            return
        self._yes_label.setText(
            "%d of the %d defects that reach here say yes" % (yes, n))

    def _guided_changed(self, name: Optional[str] = None,
                        op: Optional[str] = None,
                        value: Optional[float] = None,
                        rebuild: bool = False) -> None:
        """三格其中一格動了 → 組回 ``when`` 寫進 model。"""
        node = self._node()
        if not isinstance(node, TreeStep):
            return
        cur = parse_simple_condition(node.when) or ("", ">", 0.0)
        new_name = cur[0] if name is None else name
        new_op = cur[1] if op is None else op
        new_value = cur[2] if value is None else value
        if not new_name:
            return                      # 還沒挑數字：不要寫出一句半截的問題
        self._model.set_tree_when(self._path,
                                  format_condition(new_name, new_op, new_value))
        self._sync_yes_label(new_name, new_op, new_value)
        if rebuild:
            # 換了數字 → 滑桿的範圍整個不一樣，非重建不可。
            self.refresh(force=True)

    def _go_advanced(self) -> None:
        self._advanced.add(self._path)
        self.refresh(force=True)

    def _build_expression(self, node: TreeStep) -> None:
        """自己寫算式（複合條件的那條路，以及認不得的舊寫法）。"""
        m = self._model
        when = QLineEdit(str(node.when))
        when.setPlaceholderText("e.g. (contrast > 120) * (cd_deq < 4)")
        when.setToolTip("Anything other than 0 counts as yes. Comparisons "
                        "give 1 or 0,\nso (a > 5) * (b < 2) means both have "
                        "to hold.")
        when.textEdited.connect(
            lambda t, p=self._path: m.set_tree_when(p, str(t)))
        pick = _feature_combo(self._features,
                              lambda tok, e=when, p=self._path:
                              m.set_tree_when(p, _insert_at_cursor(e, tok)))
        row = QWidget(self)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(when, 1)
        lay.addWidget(pick)
        self.body_lay.addWidget(row)
        if parse_simple_condition(node.when) is not None:
            back = small_button("Back to the simple form", shape="wide")
            back.clicked.connect(self._go_simple)
            self.body_lay.addWidget(self._left(back))

    def _go_simple(self) -> None:
        self._advanced.discard(self._path)
        self.refresh(force=True)

    def _side_row(self, word: str, child_path: str, child: Any) -> QWidget:
        m = self._model
        row = QWidget(self)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        tag = QLabel(word)
        tag.setObjectName("paramHint")
        tag.setMinimumWidth(44)
        lay.addWidget(tag)
        if isinstance(child, TreeLeaf):
            label = QLineEdit(str(child.label))
            label.setPlaceholderText("name this class")
            label.textEdited.connect(
                lambda t, p=child_path: m.set_tree_leaf(p, label=str(t)))
            spin = QSpinBox()
            spin.setRange(0, 999)
            spin.setValue(int(child.bin))
            spin.setPrefix("bin ")
            spin.setToolTip("The bin number written back to the KLARF.")
            spin.valueChanged.connect(
                lambda v, p=child_path: m.set_tree_leaf(p, bin=int(v)))
            split = small_button("Split", shape="wide")
            split.setFixedWidth(52)
            split.setToolTip("Turn this class into another step - the class "
                             "moves to the new step's no side.")
            split.clicked.connect(
                lambda _=False, p=child_path: self._split(p))
            lay.addWidget(label, 1)
            lay.addWidget(spin)
            lay.addWidget(split)
        else:
            text = QLabel("next: %s ?" % (str(child.when) or "( … )"))
            text.setObjectName("paramHint")
            go = small_button("Edit", shape="wide")
            go.setToolTip("Edit that step instead.")
            go.clicked.connect(
                lambda _=False, p=child_path: self.step_requested.emit(p))
            lay.addWidget(text, 1)
            lay.addWidget(go)
        return row

    # ---- 一類（托盤）-------------------------------------------------------
    def _build_leaf(self, node: TreeLeaf) -> None:
        m = self._model
        self.body_lay.addWidget(self._section("Class"))
        label = QLineEdit(str(node.label))
        label.setPlaceholderText("name this class")
        label.textEdited.connect(
            lambda t, p=self._path: m.set_tree_leaf(p, label=str(t)))
        spin = QSpinBox()
        spin.setRange(0, 999)
        spin.setValue(int(node.bin))
        spin.setPrefix("bin ")
        spin.setToolTip("The bin number written back to the KLARF.")
        spin.valueChanged.connect(
            lambda v, p=self._path: m.set_tree_leaf(p, bin=int(v)))
        row = QWidget(self)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(label, 1)
        lay.addWidget(spin)
        self.body_lay.addWidget(row)

        batch = self._batch_line()
        if batch:
            self.body_lay.addWidget(self._section("This batch", batch))

        split = small_button("Split into a step", shape="wide")
        split.setToolTip("Ask another question here - this class moves to "
                         "the new step's no side.")
        split.clicked.connect(lambda: self._split(self._path))
        self.body_lay.addWidget(self._left(split))

    # ---- 動作 --------------------------------------------------------------
    def _split(self, path: str) -> None:
        self._model.split_tree_leaf(path)
        self.suggest_question(path)
        self.step_requested.emit(path)         # 新菱形就在原地

    def _insert_above(self) -> None:
        self._model.insert_tree_step_above(self._path)
        self.suggest_question(self._path)
        self.step_requested.emit(self._path)   # 新的一步接住原路徑

    def suggest_question(self, path: str) -> bool:
        """新的一步先擺一個**問得出東西**的問題（F25）。

        一個空白的問題等於把使用者丟回原點（「我不知道怎麼用」）。挑的規則
        講得出理由：這一批上分得最開的那個數字、門檻放中位數 —— 它不是自動
        最佳化，是一個**按了就有東西看**的起點，剩下的用滑桿調。
        沒跑過（沒有 rows）就什麼都不填：那時候沒有分布可言，硬猜一個數字
        比留白更糟。
        """
        node = self._model.tree_node(path) if self._model else None
        if not isinstance(node, TreeStep) or str(node.when).strip():
            return False               # 已經有問題了就不要蓋掉使用者的東西
        rows = rows_reaching(display_tree(getattr(self._model, "decide", None)),
                             self._rows, str(path)) if self._rows else []
        if len(rows) < 4:
            # 這一步下面的顆太少，算不出「哪個數字分得開」——**退回整批**。
            # 建議本來就只是一個起點（滑桿旁邊那一行會誠實地說這裡只有幾顆），
            # 而一格空白會把使用者丟回原點，那才是要避免的東西。
            rows = list(self._rows)
        lets = [str(x.name) for x in getattr(self._model.decide, "let", [])]
        cond = suggest_condition(rows, prefer=lets)
        if cond is None:
            return False
        self._model.set_tree_when(str(path), format_condition(*cond))
        return True

    def _remove_step(self) -> None:
        node = self._node()
        if not isinstance(node, TreeStep):
            return
        if isinstance(node.yes, TreeStep):
            # yes 邊掛著一整個子樹 —— 拿掉這一步會把它整個帶走。undo 回得來,
            # 但那不是一顆按鈕該默默做的事（F24 §6：「葉子孤兒要問使用者」，
            # 子樹更要問）。
            ans = QMessageBox.question(
                self, "Remove this step?",
                "The yes side of this step holds more steps - removing it "
                "throws that whole branch away.\n\nRemove anyway?")
            if ans != QMessageBox.Yes:
                return
        self._model.remove_tree_step(self._path)
        parent = self._path[:-1]
        self.step_requested.emit(parent if self._model.tree_node(
            self._path) is None else self._path)

    # ---- 小零件 ------------------------------------------------------------
    def _batch_line(self) -> str:
        """``47 arrive here → 11 yes · 36 no``（葉子：``20 land here``）。

        沒跑過（counts 是 None）回空字串 —— 一個字都不畫（F18）。
        """
        if self._counts is None:
            return ""
        here = self._counts.get(self._path, 0)
        node = self._node()
        if isinstance(node, TreeLeaf):
            return "%d land here" % here
        return ("%d arrive here → %d yes · %d no"
                % (here, self._counts.get(self._path + "y", 0),
                   self._counts.get(self._path + "n", 0)))

    def _left(self, widget: QWidget) -> QWidget:
        """把一顆按鈕靠左擺 —— 撐滿整列的按鈕讀起來像標題，不像按鈕。"""
        box = QWidget(self)
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(widget)
        lay.addStretch(1)
        return box

    def _section(self, title: str, hint: str = "") -> QWidget:
        box = QWidget(self)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(1)
        head = QLabel(title.upper())
        head.setObjectName("sectionTitle")
        lay.addWidget(head)
        if hint:
            sub = QLabel(hint)
            sub.setObjectName("paramHint")
            sub.setWordWrap(True)
            lay.addWidget(sub)
        return box

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
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from ..core.pipeline.recipe import TreeLeaf, TreeStep
from .decide_panel import _feature_combo, _insert_at_cursor
from .widgets import small_button

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

    def show_path(self, path: str) -> None:
        """開始編路徑指到的那一步（菱形）或那一類（托盤）。"""
        self._path = str(path)
        self.refresh(force=True)

    def path(self) -> str:
        return self._path

    # ---- 重建 --------------------------------------------------------------
    def _typing(self) -> bool:
        w = self.focusWidget()
        return w is not None and isinstance(w, QLineEdit) and w.hasFocus()

    def refresh(self, force: bool = False) -> None:
        if self._building or (not force and self._typing()):
            return
        self._building = True
        try:
            self._rebuild()
        finally:
            self._building = False

    def _clear(self) -> None:
        while self.body_lay.count():
            item = self.body_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

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
        m = self._model
        self.body_lay.addWidget(self._section("Question"))
        when = QLineEdit(str(node.when))
        when.setPlaceholderText("e.g. contrast > 120")
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
        lay2.addStretch(1)
        self.body_lay.addWidget(row2)

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
            split = small_button("Split…", shape="wide")
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

        split = small_button("Split into a step…", shape="wide")
        split.setToolTip("Ask another question here - this class moves to "
                         "the new step's no side.")
        split.clicked.connect(lambda: self._split(self._path))
        self.body_lay.addWidget(split)

    # ---- 動作 --------------------------------------------------------------
    def _split(self, path: str) -> None:
        self._model.split_tree_leaf(path)
        self.step_requested.emit(path)         # 新菱形就在原地

    def _insert_above(self) -> None:
        self._model.insert_tree_step_above(self._path)
        self.step_requested.emit(self._path)   # 新的一步接住原路徑

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

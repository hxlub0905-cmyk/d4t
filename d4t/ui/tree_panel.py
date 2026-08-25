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
from .threshold_view import SplitBar, ThresholdHistogram
from .widgets import clear_layout_parked, small_button, split_labelled
from .viewmodel import MAX_BIN, is_a_constant_expression

__all__ = ["TreePanel"]

#: 導引式問題那一格數字框的上下界。**它的用途是「別讓 Qt 溢位」，不是
#: 「這個門檻應該多大」** —— 後者沒有通用答案（見 `_build_guided` 的說明）。
_SPIN_LIMIT = 1e12


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
        #: 這一批試跑的結果（F25）。分布圖、分流條與麵包屑上的顆數都吃它 ——
        #: 沒跑過就是空的，那時候一個數字都不畫（F18）。
        self._rows: List[Dict[str, Any]] = []
        #: 哪幾步使用者切到了「自己寫算式」（複合條件本來就只能那樣編）。
        self._advanced: set = set()
        #: 拖門檻時**就地更新**的兩個元件（不重建 —— 重建會把滑鼠從把手上
        #: 搶走）。分流條講「切成幾比幾」，分布圖講「切在分布的哪裡」。
        self._split_bar: Optional[SplitBar] = None
        self._plot: Optional[ThresholdHistogram] = None

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

    # ---- 草案 3：我在樹的哪裡 ----------------------------------------------
    def _breadcrumb(self) -> Optional[QWidget]:
        """最上面一行：**這是第幾步、從哪一邊來的、幾顆流到這裡**。

        樹深了以後「我在哪裡」在畫面上完全看不出來 —— 右欄長得一模一樣，
        只有裡面的數字不同。而這三件事全部都是現成的：路徑就是 `self._path`，
        上一步的問題問得到，顆數 `flow_counts` 已經算出來了。

        根（``path == ""``）只說「第 1 步」—— 它沒有上一步，硬要寫一句
        「from …」會是一句空話。
        """
        path = str(self._path)
        bits: List[str] = []
        node = self._node()
        kind = "class" if isinstance(node, TreeLeaf) else "step %d" % (len(path) + 1)
        bits.append("Decision tree · %s" % kind)
        if path:
            parent = self._model.tree_node(path[:-1]) if self._model else None
            side = "yes" if path[-1] == "y" else "no"
            if isinstance(parent, TreeStep) and str(parent.when).strip():
                bits.append("the %s side of “%s”" % (side, str(parent.when)))
            else:
                bits.append("the %s side" % side)
        if self._counts is not None:
            bits.append("%d defects reach here" % self._counts.get(path, 0))
        lab = QLabel(" · ".join(bits))
        lab.setObjectName("paramHint")
        lab.setWordWrap(True)
        return lab

    # ---- 一步（菱形）-------------------------------------------------------
    def _build_step(self, node: TreeStep) -> None:
        crumb = self._breadcrumb()
        if crumb is not None:
            self.body_lay.addWidget(crumb)
        self.body_lay.addWidget(self._section("Question"))
        simple = parse_simple_condition(node.when)
        # 空的問題（剛加的一步）也走導引式 —— 一張空白的算式框正是使用者
        # 卡住的地方（2026-08-24：「我目前不太知道怎麼用」）。
        if self._path in self._advanced or (simple is None
                                            and str(node.when).strip()):
            self._build_expression(node)
        else:
            self._build_guided(simple)

        self.body_lay.addWidget(self._side_row("Yes", self._path + "y",
                                               node.yes))
        self.body_lay.addWidget(self._side_row("No", self._path + "n",
                                               node.no))

        # ⚠ **這裡以前還有一段 THIS BATCH**（``24 arrive here → 11 yes · 13 no``）。
        # 草案 2／3 之後它講的每一件事都已經有更好的位置了：「幾顆流到這裡」
        # 在最上面的麵包屑、「切成幾比幾」是分流條的寬度、而兩邊各幾顆寫在
        # Yes／No 的標籤上。留著就是同一個事實在一個 550px 的面板裡講三次。
        #
        # 葉子那一邊（`_build_leaf`）**留著** —— 一片葉子沒有「切成兩邊」，
        # 「20 land here」是它唯一的批次數字，而它沒有別的地方講。

        # 動作是**兩列**：上面一列是「還要做什麼」，下面一列只有「拿掉」。
        # 一列塞得下三顆（176 + 111 + 92 = 391px）的前提是欄寬 400 以上，
        # 而廠內機器多半是 1366×768 —— 那時候整列會被推出畫面。
        row2 = QWidget(self)
        lay2 = QHBoxLayout(row2)
        lay2.setContentsMargins(0, 0, 0, 0)
        lay2.setSpacing(6)
        ins = small_button("+ Ask one before this", shape="wide")
        ins.setToolTip("Ask a new question before this one - everything "
                       "here moves to its no side.")
        ins.clicked.connect(self._insert_above)
        lay2.addWidget(ins)
        # 「自己寫算式」是這一步的**另一種編法**，所以跟加/刪擺在同一區 ——
        # 夾在問題與 Yes/No 中間的話，它會被讀成一個段落標題。
        if self._path not in self._advanced:
            adv = small_button("As a formula", shape="wide")
            adv.setToolTip("Write this question as an expression instead - "
                           "for one that needs more than one comparison, "
                           "e.g. (a > 5) * (b < 2).")
            adv.clicked.connect(self._go_advanced)
            lay2.addWidget(adv)
        lay2.addStretch(1)
        self.body_lay.addWidget(row2)

        # **拿掉這一步自己一列、推到最右邊**（草案 6）：它是這裡唯一會弄丟
        # 東西的動作，跟「再問一個問題」並排、同一個樣子，是在請人手滑。
        row3 = QWidget(self)
        lay3 = QHBoxLayout(row3)
        lay3.setContentsMargins(0, 0, 0, 0)
        lay3.addStretch(1)
        rm = small_button("✕ Remove", shape="wide")
        rm.setToolTip("The no side takes this step's place.")
        rm.clicked.connect(self._remove_step)
        lay3.addWidget(rm)
        self.body_lay.addWidget(row3)

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

    def _slider_range(self, name: str, value: float):
        """滑桿要跨的範圍，從**流到這一步的顆**推。沒有資料就回 ``None``。

        ⚠ **回 None 的時候不要生一個滑桿出來。** 這一支以前在沒有資料時
        自己編一個範圍（``value ± max(|value|, 1)``），而那有兩個後果，
        第二個是真的擋人的：

        1. 滑桿假裝有一個分布，但它跨的是一個沒有任何意義的區間；
        2. **數字框跟滑桿共用同一組上下界**，所以一個剛加進來的步驟
           （``value`` 是 0）會把使用者夾在 **−1 … 1** —— 想問
           「``cd_median`` 大於 6.5」時，那個 6.5 **打不進去**。
           使用者回報的原話是「搖桿只能填最大 1」。

        資料只有一個值的時候（整批只有一顆，或那個數字每顆都一樣）仍然
        **用得上**：一個量到的 6.5 遠比憑空的 ±1 有用，所以那時候以它為中心
        撐開一個範圍，而不是把資料丟掉退回上面那條老路。
        """
        vals = [float(v) for r in self._rows_here()
                for v in [(r.get("features") or {}).get(str(name))]
                if isinstance(v, (int, float))]
        if len(vals) >= 2 and max(vals) > min(vals):
            lo, hi = min(vals), max(vals)
            pad = (hi - lo) * 0.05
            lo, hi = lo - pad, hi + pad
        elif vals:
            here = vals[0]
            span = abs(here) * 0.5 or 1.0
            lo, hi = here - span, here + span
        else:
            return None
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
        # ⚠ **這一格是三個裡面唯一「截字沒關係」的**，所以窄欄要靠它讓位。
        # 運算子不行（六個的差別正好在尾巴）、數字不行（看不到自己填的值）；
        # 而一個特徵名截掉尾巴仍然認得出來，點開下拉也看得到全名。
        # 不設的話它的 `minimumSizeHint` 會跟著最長的特徵名長到 150px 以上，
        # 把整列的最小寬度撐過欄寬 → 橫向捲軸 → 數字框被藏起來。
        which.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        which.setMinimumContentsLength(9)
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

        rng = self._slider_range(name, value)
        span = (rng[1] - rng[0]) if rng else 0.0
        spin = QDoubleSpinBox()
        # 96 而不是 84：**還沒試跑**的時候沒有 span，小數位只能給到最寬的
        # 那一檔（4 位）—— 而 ``42.0000`` 在 84px 裡剛好把整個框塞滿，看起來
        # 像被切掉一半。小數位不能為了版面砍掉（砍掉＝``0.0001`` 這種門檻
        # 打不進去，那正是 A1 那個 bug 的形狀），所以讓框變寬。
        spin.setFixedWidth(96)
        spin.setDecimals(0 if span > 200 else (2 if span > 1 else 4))
        # ⚠ **數字框不夾人。** 門檻的合理範圍是「這個數字可能是多少」，而那
        # 隨著卡片天差地遠（灰階 0–255、CD 幾個 px、面積上萬 px²、z 分數是負
        # 的、百分位 0–100）—— 沒有一個通用的上下界，所以這裡不要假裝有一個。
        #
        # 而且**跟這一批量到的範圍夾住它也是錯的**：「大於 12」在這批最大只有
        # 9 的時候仍然是一條完全合法的規則（那正是怎麼寫一條今天抓不到、
        # 明天出事才抓得到的規則）。夾住等於把那件事變成打不出來的東西。
        spin.setRange(-_SPIN_LIMIT, _SPIN_LIMIT)
        # ⚠ 上面那個範圍讓 Qt 以為要替 `-1000000000000.0000` 留位置，於是
        # `minimumSizeHint()` 變成 193px —— 而那個值會一路撐到整個面板的
        # 最小寬度，在窄欄裡把自己擠出畫面。固定寬度**壓不過** minimumSizeHint
        # 在 layout 上的傳遞，要明講最小寬度。
        spin.setMinimumWidth(96)
        spin.setSingleStep(max(span / 100.0, 1e-6) if span else 0.1)
        spin.setValue(float(value))
        spin.setToolTip("The value to compare against. Type any number - "
                        "a threshold outside what this batch measured is a "
                        "perfectly good rule.")
        spin.valueChanged.connect(lambda v: self._guided_changed(value=float(v)))

        lay.addWidget(which, 1)
        lay.addWidget(opbox)
        lay.addWidget(spin)
        self.body_lay.addWidget(row)

        # ---- 草案 1：滑桿換成分布圖 ----------------------------------------
        # 以前這裡是一根**沒有刻度**的滑桿：使用者拖的時候不知道自己在 60
        # 還是 200，唯一的回饋是上面那個數字框。而面板手上一直有這一步流到
        # 的每一顆的值（`_rows_here`）—— 這個專案的 Gray level 面板早就在畫
        # 分布了（F18），真正在挑門檻的地方反而沒有。
        #
        # 圖與數字框是**同一個值的兩個把手**：拖圖改數字框、改數字框圖跟著走。
        # 兩邊互相回彈是這種雙向綁定的老坑，所以圖那一邊用 `set_threshold`
        # （不發訊號）回寫。
        # ⚠ **沒有要放進版面就不要生出來。** 這裡以前無條件
        # `ThresholdHistogram(self)`，只在有資料時 `addWidget` —— 而
        # `clear_layout_parked` 清的是**版面裡**的東西，所以沒進版面的那些
        # 就永遠掛在面板上：實測每重建一次多一個，拖一次門檻就是幾十個。
        # 這個面板重建得非常兇（改一格就整段重建），所以「每次多一個」
        # 在一個 session 裡是幾百個看不見的 widget。
        self._plot = None
        vals = self._values_here(name)
        if vals:
            self._plot = ThresholdHistogram(self)
            self._plot.set_data(vals, float(value), above_is_yes=op in (">", ">="))
            self._plot.threshold_changed.connect(
                lambda v, sp=spin: sp.setValue(float(v)))
            spin.valueChanged.connect(
                lambda v, pl=self._plot: pl.set_threshold(float(v)))
            self.body_lay.addWidget(self._plot)
        elif name:
            # 沒有分布的時候要講出**為什麼**，而且那句話要指向能拿回它的動作
            # —— 一個安靜消失的控制項比一個沒有用的控制項更難懂。
            hint = QLabel("Run a trial to see how this batch is spread out "
                          "here, and drag the threshold on it.")
            hint.setObjectName("paramHint")
            hint.setWordWrap(True)
            self.body_lay.addWidget(hint)

        # ---- 草案 2：兩句重複的話收成一條分流條 ----------------------------
        # 以前這裡是「11 of the 24 defects that reach here say yes」，而底下
        # 100px 的 THIS BATCH 又寫一次「24 arrive here → 11 yes · 13 no」——
        # 同一件事、兩種格式、隔著一個段落。一條有寬度的橫條回答同一個問題，
        # 但**顆數變成寬度**，掃一眼就知道這一刀切得均不均。
        self._split_bar = SplitBar(self)
        self._sync_split(name, op, value)
        self.body_lay.addWidget(self._split_bar)

    def _values_here(self, name: str) -> List[float]:
        """流到這一步的顆在 ``name`` 上的值（分布圖與分流條共用的那一份）。"""
        if not name:
            return []
        return [float(v) for r in self._rows_here()
                for v in [(r.get("features") or {}).get(str(name))]
                if isinstance(v, (int, float))]

    def _sync_split(self, name: str, op: str, value: float) -> None:
        """拖的時候**就地改**這一條（不重建 —— 重建會把滑鼠從把手上搶走）。"""
        if self._split_bar is None:
            return
        rows = self._rows_here()
        if not rows or not name:
            self._split_bar.set_counts(0, 0)
            return
        yes, n = count_yes(rows, name, op, float(value))
        self._split_bar.set_counts(yes, max(0, n - yes))

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
        self._sync_split(new_name, new_op, new_value)
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
        """一個分支：``Yes 11 → [類別名] [bin ▾]`` 或 ``No 13 → 再問一個問題``。

        草案 4／5 動了三件事：

        * **兩邊帶顆數**（``Yes 11``）—— 一步分成兩邊，而「各分到幾顆」是
          看這一步時最先想知道的事；以前那個數字只在下面 THIS BATCH 那一行。
        * **兩邊視覺對稱**。以前一邊是輸入框、一邊是灰字＋Edit 連結，
          看起來像兩種不同的東西；其實它們是同一個位置的兩種填法
          （一個類別 / 再問一個問題）。
        * **類別名是主角，bin 降成它的編號**。使用者想的是「亮點」不是
          「bin 2」—— bin 是 KLARF 的實作細節，仍然改得到，只是不再跟名字
          搶同一階的視覺重量。
        """
        m = self._model
        # **兩行，不是一行**。這一欄只有 430px（那正是草案第 7 條在講的事），
        # 而一行要塞下「Yes 11 / 名字 / bin / 再問一個問題」就一定會橫向溢位
        # —— 而橫向捲軸在一個編輯面板上等於把控制項藏起來。
        # 面板底下本來就有 300 多 px 是空的，**高度是免費的、寬度不是**。
        row = QWidget(self)
        outer = QVBoxLayout(row)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        top = QWidget(row)
        lay = QHBoxLayout(top)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        outer.addWidget(top)

        tag = QLabel(self._side_tag(word, child_path))
        tag.setObjectName("paramHint")
        tag.setMinimumWidth(52)
        lay.addWidget(tag)

        if isinstance(child, TreeLeaf):
            label = QLineEdit(str(child.label))
            label.setPlaceholderText("name this class")
            label.setToolTip("What this class is called - this is the name "
                             "that shows up on the canvas and in the report.")
            label.textEdited.connect(
                lambda t, p=child_path: m.set_tree_leaf(p, label=str(t)))
            spin = QSpinBox()
            spin.setRange(0, MAX_BIN)
            spin.setValue(int(child.bin))
            spin.setPrefix("bin ")
            # bin 是編號不是名字：固定一個剛好放得下的寬度，把剩下的都給名字。
            # 66 而不是 74 —— 那一欄右邊還有捲軸要站的位置，多 8px 就會被切掉
            # （而一個被切掉一半的數字框比一個小一點的更難用）。
            spin.setFixedWidth(66)
            spin.setMinimumWidth(60)      # 同上：壓過 range 撐出來的 minHint
            spin.setObjectName("paramHint")
            spin.setToolTip("The bin number written back to the KLARF.")
            spin.valueChanged.connect(
                lambda v, p=child_path: m.set_tree_leaf(p, bin=int(v)))
            lay.addWidget(label, 1)
            lay.addWidget(spin)
            # ⚠ **字剪到「一行放得下」為止**：``about this class`` 那四個字
            # 讓這顆鈕變成 311px，加上縮排 58px 就超過 1366×768 那台機器上
            # 這一欄的寬度 —— 而它上面那一行正是那個類別，缺的脈絡在畫面上。
            ask = small_button("↳ Ask another question", shape="wide")
            ask.setToolTip("Turn this class into another step - the class "
                           "moves to the new step's no side.")
            ask.clicked.connect(
                lambda _=False, p=child_path: self._split(p))
            outer.addWidget(self._indent(ask))
        else:
            text = QLabel("asks: %s" % (str(child.when).strip() or "( … )"))
            text.setObjectName("paramHint")
            text.setWordWrap(True)
            lay.addWidget(text, 1)
            go = small_button("↳ Edit that step", shape="wide")
            go.setToolTip("Edit that step instead.")
            go.clicked.connect(
                lambda _=False, p=child_path: self.step_requested.emit(p))
            outer.addWidget(self._indent(go))
        return row

    def _indent(self, widget: QWidget) -> QWidget:
        """把一顆按鈕靠左、往內縮一格 —— 讀起來是「屬於上面那一行的動作」。"""
        box = QWidget(self)
        lay = QHBoxLayout(box)
        lay.setContentsMargins(58, 0, 0, 0)
        lay.addWidget(widget)
        lay.addStretch(1)
        return box

    def _side_tag(self, word: str, child_path: str) -> str:
        """``Yes`` ／ ``Yes 11`` —— 沒跑過就不帶數字（F18：不顯示 0）。"""
        base = str(word).replace("→", "").strip()
        if self._counts is None:
            return base
        return "%s %d" % (base, self._counts.get(str(child_path), 0))

    # ---- 一類（托盤）-------------------------------------------------------
    def _build_leaf(self, node: TreeLeaf) -> None:
        m = self._model
        self.body_lay.addWidget(self._section("Class"))
        label = QLineEdit(str(node.label))
        label.setPlaceholderText("name this class")
        label.textEdited.connect(
            lambda t, p=self._path: m.set_tree_leaf(p, label=str(t)))
        spin = QSpinBox()
        spin.setRange(0, MAX_BIN)
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

        split = small_button("↳ Ask another question", shape="wide")
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
        if not isinstance(node, TreeStep):
            return False
        # 「已經有問題了就不要蓋掉使用者的東西」—— 但**常數不是問題**
        # （U1，2026-08-24）：`0 >= 0` 對每一顆都成立，它不是使用者的工作成果，
        # 是一個佔位值漏過來的東西。見 `viewmodel.is_a_constant_expression`。
        if not is_a_constant_expression(node.when):
            return False
        # ⚠ **要用「這一步還不存在」的樹去問誰流到這裡**（2026-08-24）。
        # 一個剛加進來的步驟 ``when`` 是空的，而 `_path_of` 走到它就會炸
        # （`parse_expression("")`）—— 那一顆因此**整條路都不算**，於是
        # `rows_reaching` 回空的、下面那段退回整批，而整批算出來的建議
        # 正好就是**上一步已經問過的那一個**（實測：第一步 `glv_max > 67`，
        # 第二步建議一模一樣的 `glv_max > 67`，切出來 0 yes / 13 no）。
        #
        # 把這一格暫時換成一片葉子，`_path_of` 就會**停在這裡**並回傳這條路徑
        # —— 那正是「誰流到這一步」的定義。
        # 不去動 `_path_of` 本身：`flow_counts` 靠它「走不動就整顆不計」
        # 來保住守恆（見那一支的說明），改它會把那件事弄破。
        tree = display_tree(getattr(self._model, "decide", None))
        if tree is not None and str(path):
            tree = self._model._tree_replace(tree, str(path), TreeLeaf(bin=0))
        rows = rows_reaching(tree, self._rows, str(path)) if self._rows else []
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

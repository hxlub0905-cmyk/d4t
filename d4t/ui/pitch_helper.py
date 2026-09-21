# d4t helper：問一張圖的 pitch — authored 2026-09-21 (F120).
"""**Pitch helper —— 丟一張圖進去，回答它的 cell period。**

使用者 2026-09-21：「主要是算 Golden cell（應該在 ROI 內那張卡），命名就叫
pitch helper，主要功能就是丟一張圖進去，算 repeating pattern 的 cell period
（可支援 pixels & X(nm)）。」

這個能力今天**只存在於一條很長的路的中間**：Studio → `roi_reference`
（`method="template"`）→ `TemplateDialog` → 匯入大圖 → 疊模板。週期是那條路的
副產品，而使用者常常只想要那個數字本身。為了一個數字先開 Studio、先有一份
recipe、先加一張卡、先接好線 —— 那不是「功能不存在」，是**入口不存在**。
所以這一支**不新增任何演算法**，它只是一個入口。

⚠ **原功能一個字都沒動。** `roi_reference` / `roi_template` / `TemplateDialog`
照舊，recipe 照舊，黃金值照舊。

量週期不抄第二份
----------------
唯一出處是 `algo/template.measure_period`（三票制：投影法 ＋ 二維自相關 ＋
半週期檢查，F104／F105 的實測全長在它身上）。它本來是私有的
（``_measure_period``），F120 改成公開 —— 第二個呼叫者出現時，選擇只有
「開放那一支」與「抄一份三票制出去」，而後者一定會漂（`CLAUDE.md` §0）。

「假設算不對我該怎麼知道」（使用者 F103 問過的那一句）
------------------------------------------------------
對一個**只輸出一個數字**的工具，這一句更尖銳：一個錯的 pitch 看起來跟對的
一模一樣。所以畫面上攤開三層證據，而它們都已經存在，只是搬進同一個視窗：

1. 每一軸的**信心值**與 `measure_period` 的 notes（換了量法、加倍了、諧波鏈
   不直 —— 每一句都是使用者該知道的決定）；
2. **交錯分數**（交錯晶格 ≈ 1、規則晶格 ≈ 0）；
3. **把 cell 的切點格線鋪回原圖**（`lattice_dialog.lattice_boxes`，F103 那一套）
   —— 每一格框住的東西都一樣就是對的；格線在圖的另一頭漂到別的結構上就是錯的。

⚠ **格線預設開著。** 它要多跑一次 `period.choose_origin`（相位搜尋，4096² 實測
5.3 秒），所以它跟量週期**在同一個 worker 裡一起跑完** —— 不是量完先還一個
數字、再讓使用者按第二顆鈕等第二次。那顆勾勾是「我要看原圖」，不是省時間用的。

單位：px 是答案，nm 是換算
--------------------------
`docs/FAB-VALIDATION.md` 假設 #2 已經定調：``nm_per_px`` 在 KLARF 裡沒有來源，
所以**單位一律 pixel、換算搬到輸出那一刻**。這裡照抄卡片那一套
（`steps/_util.nm_per_px_spec`）：**0 ＝ 不知道，那一欄就不出現**。
顯示一個 `0 nm` 比不顯示糟得多 —— 它看起來像一個量出來的答案。

刻意不放進 Studio 的工具列
--------------------------
同 `gc_generator` 的理由，逐字適用：那條工具列已經滿到把「Results」擠進 Qt 的
overflow 過一次（F48）。這是一個**問一個數字**的工具，不是分析流程的一步。
開法：``python -m d4t pitch``。
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from d4t.core.algo import period as algo_period
from d4t.core.algo import period2d as algo_period2d
from d4t.core.algo import template as algo_template

from . import fit_screen, theme
from .chips import ChoiceChips
from .crop_dialog import CropDialog, crop_array, describe_crop
from .image_view import ImageView
from .lattice_dialog import lattice_boxes
from .widgets import apply_button_cursors, to_uint8

__all__ = [
    "PitchHelperWindow", "AXES", "AXIS_AUTO", "AXIS_X", "AXIS_Y", "AXIS_BOTH",
    "axis_flags", "lattice_periods", "px_text", "nm_text", "pitch_rows",
    "effective_period", "Override", "PITCH_UNSET", "PITCH_NOT_USED",
    "CONF_TYPED", "run",
]

# --------------------------------------------------------------------------- #
# 軸向：使用者說了算（F120，使用者 2026-09-21「也能支援純 X 純 Y」）
# --------------------------------------------------------------------------- #
AXIS_AUTO = "auto"
AXIS_X = "x"
AXIS_Y = "y"
AXIS_BOTH = "both"

#: 四選一，順序就是畫面上膠囊的順序。
AXES = (AXIS_AUTO, AXIS_X, AXIS_Y, AXIS_BOTH)
AXIS_ICONS = ("target_auto", "axis_x", "axis_y", "place_crossing")
AXIS_LABELS = {
    AXIS_AUTO: "Auto",
    AXIS_X: "X only",
    AXIS_Y: "Y only",
    AXIS_BOTH: "X + Y",
}
AXIS_HELP = {
    AXIS_AUTO: ("Use whichever direction the image really repeats in. An axis "
                "whose measurement is not confident enough is left out - a "
                "made-up period is worse than none."),
    AXIS_X: ("This layout only repeats across, so only cut vertical lines. One "
             "cell spans the full height. Use it for line/space patterns."),
    AXIS_Y: ("This layout only repeats down, so only cut horizontal lines. One "
             "cell spans the full width."),
    AXIS_BOTH: ("Cut both ways even where the measurement is not confident - "
                "you are telling it the layout repeats in both directions."),
}

#: 一軸要至少這麼多像素才算得上一個週期（同 `build_golden_cell` 的判準）。
MIN_PERIOD_PX = 2.0

#: 還沒有答案的那一格寫什麼。**一個破折號，不是 0** —— 0 在那一格看起來像一個
#: 量出來的答案（同 `gc_generator.PERIOD_UNSET`，F117 G5 定的）。
PITCH_UNSET = "—"

#: 這一軸被使用者的選擇排除掉時寫什麼。**不是空白、不是消失** —— 那一軸的數字
#: 其實量到了，藏起來的話使用者會以為它量不到，然後回頭去查一個不存在的問題。
PITCH_NOT_USED = "not used"


def axis_flags(axis: str, px: float, py: float,
               conf_x: float = 100.0, conf_y: float = 100.0
               ) -> Tuple[bool, bool]:
    """``(用不用 X, 用不用 Y)`` —— 軸向選擇 ＋ 量到的東西一起決定。

    * **Auto** 照 `build_golden_cell` 的判準：``p >= 2 且 信心 >= 40``。
      「量到一個數字」不等於「真的有週期」—— 純雜訊也會被找出一個假週期
      （實測信心 20 上下，真的有週期的是 87）。
    * **明講的軸**（X only／Y only／X + Y）**跳過信心那一關**：使用者明講的
      一律相信，同 `build_golden_cell` 的 ``given`` 規則。但它變不出一個沒有
      量到的數字 —— ``p < 2`` 仍然是沒有。
    """
    has_x = float(px or 0.0) >= MIN_PERIOD_PX
    has_y = float(py or 0.0) >= MIN_PERIOD_PX
    a = str(axis or AXIS_AUTO)
    if a == AXIS_X:
        return (has_x, False)
    if a == AXIS_Y:
        return (False, has_y)
    if a == AXIS_BOTH:
        return (has_x, has_y)
    ok_x = has_x and float(conf_x or 0.0) >= algo_template.MIN_PERIOD_CONFIDENCE
    ok_y = has_y and float(conf_y or 0.0) >= algo_template.MIN_PERIOD_CONFIDENCE
    return (ok_x, ok_y)


def lattice_periods(shape: Tuple[int, int], px: float, py: float,
                    flags: Tuple[bool, bool]) -> Tuple[float, float]:
    """畫格線／找相位時那兩個週期 —— **沒有週期的軸取整張影像的長度**。

    這是 `build_golden_cell` 對一維 layout 的做法（「那一軸就取整張影像的長度
    當一格 —— 反正它上面沒有相位可言」）。自己再發明一套的話，畫面上的格線
    跟引擎用的格子會差一個量，而那種 bug 極難發現。
    """
    h, w = int(shape[0]), int(shape[1])
    ux = float(px) if flags[0] and float(px or 0) >= MIN_PERIOD_PX else float(w)
    uy = float(py) if flags[1] and float(py or 0) >= MIN_PERIOD_PX else float(h)
    return ux, uy


# --------------------------------------------------------------------------- #
# 數字 → 給人看的字
# --------------------------------------------------------------------------- #
def px_text(value: float, used: bool) -> str:
    """``"40"`` / ``"79.5"`` / ``"not used"`` / ``"—"``。

    小數要留著（``%d`` 會安靜截斷，而 79.5 對 79 在 4000 px 上差 25 px）——
    所以走 `period2d.fmt_px`，跟模板那條路印的是同一個字。
    """
    v = float(value or 0.0)
    if v < MIN_PERIOD_PX:
        return PITCH_UNSET
    return algo_period2d.fmt_px(v) if used else PITCH_NOT_USED


def nm_text(value: float, used: bool, nm_per_px: float) -> str:
    """px × nm/px → ``"3,180 nm"``；**不知道 nm/px 就回空字串**。

    ⚠ 回空字串而不是 ``"0 nm"``／``"—"``：呼叫端拿到空字串就整欄不放
    （見模組說明的「單位」那一段）。一個 `0 nm` 看起來像一個量出來的答案。
    """
    s = float(nm_per_px or 0.0)
    v = float(value or 0.0)
    if s <= 0 or v < MIN_PERIOD_PX or not used:
        return ""
    nm = v * s
    return "%s nm" % ("{:,.1f}".format(nm).rstrip("0").rstrip(".")
                      if nm < 1000 else "{:,.0f}".format(nm))


Override = Tuple[Optional[float], Optional[float]]

#: 使用者自己打了一個週期時，信心那一欄寫什麼。
#:
#: ⚠ **不准沿用量出來的那個分數。** 信心量的是「把圖平移這個週期之後跟自己有
#: 多像」，而那是對**量出來的那個數字**做的。使用者把 40 改成 80 之後還掛著
#: 92/100，等於用一個他沒有問過的問題的答案，去背書他剛打進去的數字。
CONF_TYPED = "you typed it"


def effective_period(measured: Any, override: Override = (None, None)
                     ) -> Tuple[float, float]:
    """真正要用的那一組週期：**使用者打的優先，沒打就用量到的**。

    量出來的週期是**預設值不是結論** —— 這句話是 `template_dialog` 定的
    （使用者原話：有時候他要一個 2× 的大 cell，「例如兩根 MG 才構成他要比的
    那個單元」）。helper 這邊一字不差地適用，而且更需要：這個視窗的**唯一**
    輸出就是那個數字，改不動它等於「算錯了只能關掉視窗」。
    """
    px = float(getattr(measured, "px", 0.0) or 0.0)
    py = float(getattr(measured, "py", 0.0) or 0.0)
    ox, oy = override
    return (float(ox) if ox else px, float(oy) if oy else py)


def pitch_rows(measured: Any, axis: str, nm_per_px: float = 0.0,
               override: Override = (None, None)
               ) -> List[Tuple[str, str, str, str]]:
    """``[(方向, px, nm, 信心), …]`` —— 畫面上那張表的**唯一**算法。

    做成純函式（不碰任何 widget）是為了測得動：軸向 × 有沒有 nm × 量不量得到
    × 有沒有被改過的排列組合各斷言一次，不必為了讀一行字開一次視窗。
    """
    px, py = effective_period(measured, override)
    cx = float(getattr(measured, "conf_x", 0.0) or 0.0)
    cy = float(getattr(measured, "conf_y", 0.0) or 0.0)
    # 打進去的那一軸**跳過信心那一關**（使用者明講的一律相信，同
    # `build_golden_cell` 的 ``given``）—— 拿一個他沒問過的分數去否決他打的
    # 數字，畫面上會變成「我改了，但它不理我」。
    typed_x, typed_y = bool(override[0]), bool(override[1])
    use_x, use_y = axis_flags(axis, px, py,
                              100.0 if typed_x else cx,
                              100.0 if typed_y else cy)
    rows = []
    for label, value, used, conf, typed in (
            ("Across (X)", px, use_x, cx, typed_x),
            ("Down (Y)", py, use_y, cy, typed_y)):
        got = float(value or 0.0) >= MIN_PERIOD_PX
        if typed:
            conf_text = CONF_TYPED
        elif got:
            conf_text = "%.0f / 100" % conf
        else:
            conf_text = PITCH_UNSET
        rows.append((label, px_text(value, used),
                     nm_text(value, used, nm_per_px), conf_text))
    return rows


# --------------------------------------------------------------------------- #
# 背景執行緒
# --------------------------------------------------------------------------- #
class _PitchWorker(QThread):
    """量週期 ＋ 找相位。**不在 GUI 執行緒跑** —— 4096² 合起來要八秒。

    兩種工作，因為**軸向改了不必重量**：週期跟軸向無關（那是影像的性質），
    軸向只改「哪幾軸算數」，而那會換掉要畫的格線與相位。重量一次 2.8 秒，
    只找相位 5.3 秒 —— 省下來的是使用者按一下膠囊之後的等待。
    """

    stage = Signal(str)
    done = Signal(object, object, str)   # (MeasuredPeriod 或 None, origin, 錯誤)

    def __init__(self, image: np.ndarray, axis: str,
                 measured: Optional[Any] = None,
                 override: Override = (None, None), parent=None):
        super().__init__(parent)
        self._image = image
        self._axis = str(axis)
        self._measured = measured        # 有就不重量（只找相位）
        self._override = override        # 使用者自己打的週期（相位照它搜）
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:  # Qt hook
        try:
            m = self._measured
            if m is None:
                self.stage.emit("Measuring the period…")
                m = algo_template.measure_period(self._image)
            if self._stop:
                self.done.emit(None, None, "")
                return
            # **相位要照使用者真的在用的那個週期搜。** 拿量到的 40 去搜、卻用
            # 打進去的 80 畫格線，格線會整排落在半格上 —— 而畫面上看起來就像
            # 「他打的那個週期是錯的」。
            ex, ey = effective_period(m, self._override)
            flags = axis_flags(self._axis, ex, ey,
                               100.0 if self._override[0] else m.conf_x,
                               100.0 if self._override[1] else m.conf_y)
            origin: Tuple[float, float] = (0.0, 0.0)
            if flags[0] or flags[1]:
                self.stage.emit("Finding the phase…")
                ux, uy = lattice_periods(self._image.shape[:2], ex, ey, flags)
                origin = algo_period.choose_origin(
                    self._image.shape, int(round(ux)), int(round(uy)),
                    image=self._image)
        except Exception as e:           # 講出來，不要吞掉（鐵則 7 的 UI 版）
            self.done.emit(None, None, "Could not measure this image: %s" % e)
        else:
            self.done.emit(m, origin, "")


# --------------------------------------------------------------------------- #
# 主視窗
# --------------------------------------------------------------------------- #
class PitchHelperWindow(QMainWindow):
    """一張圖 → 它的 cell period，以及看得出對不對的那張圖。"""

    #: 量完一次（給測試與之後可能的嵌入用）：(MeasuredPeriod, origin)。
    measured = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pitch helper — d4t")

        self._full: Optional[np.ndarray] = None      # 載進來的原圖
        self._work: Optional[np.ndarray] = None      # 裁過的（量的就是它）
        self._crop: Optional[Tuple[int, int, int, int]] = None
        self._name = ""
        self._m: Optional[Any] = None                # 上一次的 MeasuredPeriod
        self._origin: Tuple[float, float] = (0.0, 0.0)
        self._worker: Optional[_PitchWorker] = None

        area, root = fit_screen.scrolled(self)
        self.setCentralWidget(area)
        grid = QGridLayout(root)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setSpacing(10)
        grid.addWidget(self._source_box(), 0, 0)
        grid.addWidget(self._axis_box(), 1, 0)
        grid.addWidget(self._answer_box(), 2, 0)
        grid.addWidget(self._notes_box(), 3, 0)
        # ⚠ 撐高度的是**空的那一列**，不是「What it decided」那一塊。把伸展放在
        # 它身上的話，一次乾淨的量測（沒有任何 note —— 那是最常見的情形）
        # 會得到一個佔掉半個畫面的空框，而畫面上最大的那一塊應該是圖。
        grid.addWidget(QWidget(root), 4, 0)
        grid.addWidget(self._view_box(), 0, 1, 5, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(4, 1)
        fit_screen.fit(self, 1120, 820)
        apply_button_cursors(self)
        self._sync()

    # -- 版面 ---------------------------------------------------------------
    def _source_box(self) -> QWidget:
        box = QGroupBox("1 · The image", self)
        lay = QVBoxLayout(box)
        row = QHBoxLayout()
        self.btn_open = QPushButton("Open image…", box)
        self.btn_open.clicked.connect(self.open_image)
        row.addWidget(self.btn_open)
        self.btn_paste = QPushButton("Paste", box)
        self.btn_paste.setToolTip("Paste an image from the clipboard (Ctrl+V) — "
                                  "a screenshot works.")
        self.btn_paste.clicked.connect(self.paste_image)
        row.addWidget(self.btn_paste)
        self.btn_crop = QPushButton("Crop…", box)
        self.btn_crop.setToolTip(
            "Measure from one part of the image only — leave out the defect, "
            "scribe lines and the scale bar. They are not the repeating layout, "
            "and the period is measured from the whole picture.")
        self.btn_crop.clicked.connect(self.ask_crop)
        row.addWidget(self.btn_crop)
        row.addStretch(1)
        lay.addLayout(row)
        self.lab_source = QLabel("Drop an image here, open one, or paste one.", box)
        self.lab_source.setObjectName("paramHint")
        self.lab_source.setWordWrap(True)
        lay.addWidget(self.lab_source)
        return box

    def _axis_box(self) -> QWidget:
        box = QGroupBox("2 · Which way it repeats", self)
        lay = QVBoxLayout(box)
        self.chips_axis = ChoiceChips(AXES, AXIS_ICONS, AXIS_AUTO,
                                      helps=AXIS_HELP, labels=AXIS_LABELS,
                                      parent=box)
        self.chips_axis.changed.connect(self._on_axis)
        lay.addWidget(self.chips_axis)
        return box

    def _answer_box(self) -> QWidget:
        box = QGroupBox("3 · The pitch", self)
        outer = QVBoxLayout(box)
        self.table = QGridLayout()
        self.table.setHorizontalSpacing(14)
        self._heads: List[QLabel] = []
        for col, head in enumerate(("", "pixels", "", "confidence")):
            lab = QLabel(head, box)
            lab.setObjectName("paramHint")
            self.table.addWidget(lab, 0, col)
            self._heads.append(lab)
        self._cells: List[List[QLabel]] = []
        for r in (1, 2):
            row = []
            for c in range(4):
                lab = QLabel(PITCH_UNSET, box)
                if c == 1:
                    f = lab.font()
                    f.setPointSizeF(f.pointSizeF() * 1.6)
                    f.setBold(True)
                    lab.setFont(f)
                self.table.addWidget(lab, r, c)
                row.append(lab)
            self._cells.append(row)
        outer.addLayout(self.table)

        # 量出來的週期是**預設值不是結論**（`template_dialog` 定的那句話 ——
        # 使用者有時候要一個 2× 的大 cell：「兩根 MG 才構成他要比的那個單元」）。
        # 這個視窗的唯一輸出就是那個數字，**改不動它等於算錯了只能關掉視窗**。
        fix = QHBoxLayout()
        fix.addWidget(QLabel("Use instead", box))
        self.spin_px = self._period_spin(box, "across")
        self.spin_py = self._period_spin(box, "down")
        fix.addWidget(self.spin_px)
        fix.addWidget(QLabel("×", box))
        fix.addWidget(self.spin_py)
        self.btn_double = QPushButton("×2", box)
        self.btn_double.setProperty("variant", "secondary")
        self.btn_double.setToolTip(
            "Double both — for when one cell of yours is two of the repeats "
            "it measured (two MG lines making the unit you compare).")
        self.btn_double.clicked.connect(self._on_double)
        fix.addWidget(self.btn_double)
        self.btn_reset = QPushButton("Reset", box)
        self.btn_reset.setProperty("variant", "secondary")
        self.btn_reset.setToolTip("Go back to the measured period.")
        self.btn_reset.clicked.connect(self._on_reset)
        fix.addWidget(self.btn_reset)
        fix.addStretch(1)
        outer.addLayout(fix)
        self.lab_typed = QLabel("", box)
        self.lab_typed.setObjectName("paramHint")
        self.lab_typed.setWordWrap(True)
        outer.addWidget(self.lab_typed)

        form = QFormLayout()
        self.spin_nm = QDoubleSpinBox(box)
        self.spin_nm.setRange(0.0, 1e6)
        self.spin_nm.setDecimals(3)
        self.spin_nm.setSingleStep(0.1)
        self.spin_nm.setSuffix(" nm/px")
        self.spin_nm.setSpecialValueText("not known")
        self.spin_nm.setToolTip(
            "How many nanometres one pixel is, from the tool's settings. Fill "
            "it in and the pitch also comes out in nanometres. Leave it at 0 "
            "if you do not know it — everything stays in pixels.")
        self.spin_nm.valueChanged.connect(lambda _v: self._fill_answer())
        form.addRow("Pixel size", self.spin_nm)
        outer.addLayout(form)
        return box

    def _period_spin(self, box: QWidget, axis: str) -> QDoubleSpinBox:
        """一格「我自己來」的週期。**0 ＝ 沒打，用量到的那個。**

        ⚠ 小數要收得下（`setDecimals(1)`）：F105 之後週期可以是 79.5，而
        79.5 對 79 在 4000 px 上差 25 px。只收整數的話，使用者「照著量出來的
        數字微調」會把那個小數一起吃掉。
        """
        sp = QDoubleSpinBox(box)
        sp.setRange(0.0, 8192.0)
        sp.setDecimals(1)
        sp.setSingleStep(1.0)
        sp.setSpecialValueText("measured")
        sp.setToolTip(
            "Type the cell size %s if the measured one is not the unit you "
            "want — the grid redraws so you can see whether yours is right. "
            "Leave it at “measured” to use what it found." % axis)
        sp.valueChanged.connect(lambda _v: self._on_override())
        return sp

    def _notes_box(self) -> QWidget:
        box = QGroupBox("4 · What it decided", self)
        lay = QVBoxLayout(box)
        self.notes = QPlainTextEdit(box)
        self.notes.setReadOnly(True)
        self.notes.setMinimumHeight(70)
        self.notes.setMaximumHeight(170)
        self.notes.setPlaceholderText(
            "Anything worth knowing about the measurement shows up here — a "
            "period that was doubled, an axis measured a different way, rows "
            "that look staggered.")
        lay.addWidget(self.notes)
        return box

    def _view_box(self) -> QWidget:
        box = QGroupBox("Check it: every box should frame the same thing", self)
        lay = QVBoxLayout(box)
        self.view = ImageView(box)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        self.chk_grid = QCheckBox("Show the cell grid", box)
        self.chk_grid.setChecked(True)
        self.chk_grid.setToolTip(
            "Draw the cell boundaries on the image. If the boxes frame the "
            "same structure everywhere, the period and phase are right; if "
            "they drift onto something else towards one side, the period is "
            "off by a little.")
        self.chk_grid.toggled.connect(lambda _on: self._draw())
        row.addWidget(self.chk_grid)
        row.addStretch(1)
        self.progress = QProgressBar(box)
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setMaximumWidth(180)
        row.addWidget(self.progress)
        lay.addLayout(row)
        self.caption = QLabel("", box)
        self.caption.setObjectName("paramHint")
        self.caption.setWordWrap(True)
        lay.addWidget(self.caption)
        self.setAcceptDrops(True)
        return box

    # -- 進來的圖 -----------------------------------------------------------
    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open an image of the repeating layout", "",
            "Images (*.tif *.tiff *.png *.jpg *.jpeg *.bmp);;All files (*)")
        if not path:
            return
        from d4t.core.ingest import imageio as ingest_imageio
        try:
            arr = ingest_imageio.load_gray(str(path))
        except Exception as e:
            self._say("Could not open that image: %s" % e)
            return
        import os
        self.set_image(arr, os.path.basename(str(path)), ask_crop=True)

    def paste_image(self) -> None:
        cb = QGuiApplication.clipboard()
        img = cb.image() if cb is not None else None
        arr = _qimage_to_gray(img)
        if arr is None:
            self._say("There is no image on the clipboard.")
            return
        self.set_image(arr, "pasted image", ask_crop=True)

    def set_image(self, arr: Any, name: str = "", ask_crop: bool = False) -> None:
        """換一張圖：清掉上一次的答案，量一次新的。

        ⚠ **舊答案要先清掉**再開始量。留著的話，新圖載進來的那幾秒畫面上寫的
        是上一張圖的 pitch，而那是這個視窗唯一的輸出 —— 沒有比「對著新圖顯示
        舊答案」更糟的失敗方式。
        """
        a = np.asarray(arr)
        if a.ndim < 2 or a.size == 0:
            self._say("That is not an image.")
            return
        self._full = to_uint8(a)
        self._crop = None
        self._name = str(name or "")
        self._m = None
        self._origin = (0.0, 0.0)
        self._apply_crop()
        if ask_crop and not self.ask_crop():
            self.remeasure()

    def ask_crop(self) -> bool:
        """問「只看這一塊」。回 True 表示它已經自己重量過了。

        用的是 `crop_dialog.CropDialog` **本人** —— 模板那條路存在的理由
        （整張圖裡不只有你要的那種 cell）在這裡一字不差地成立，而「框怎麼變成
        像素」只能有一個家（`crop_array` 的說明）。
        """
        if self._full is None:
            return False
        dlg = CropDialog(self._full, self._name, self._crop, self,
                         ok_text="Measure from this box")
        if not dlg.exec():
            return False
        self._crop = dlg.box()
        self._apply_crop()
        self.remeasure()
        return True

    def _apply_crop(self) -> None:
        if self._full is None:
            return
        self._work = crop_array(self._full, self._crop)
        self._m = None
        h, w = self._work.shape[:2]
        bits = ["%s%d x %d px" % ((self._name + " — ") if self._name else "", w, h)]
        crop = describe_crop(self._crop)
        if crop:
            bits.append(crop)
        self.lab_source.setText(", ".join(bits))
        self.view.set_image(self._work)

    # -- 量 -----------------------------------------------------------------
    def remeasure(self, reuse: bool = False) -> None:
        """量一次。``reuse=True`` 只重找相位（軸向或週期改了，影像沒變）。"""
        if self._work is None or self._worker is not None:
            return
        self._worker = _PitchWorker(self._work, self.axis(),
                                    self._m if reuse else None,
                                    self.override(), self)
        self._worker.stage.connect(self._say)
        self._worker.done.connect(self._on_done)
        self._worker.finished.connect(self._on_finished)
        self.progress.setVisible(True)
        self._busy(True)
        self._worker.start()

    def _on_done(self, m: Any, origin: Any, err: str) -> None:
        if err:
            self._say(err)
            return
        if m is None:
            return
        self._m = m
        self._origin = tuple(origin or (0.0, 0.0))
        self._fill_answer()
        self._draw()
        self._fill_notes()
        self.measured.emit(m, self._origin)

    def _on_finished(self) -> None:
        self._worker = None
        self.progress.setVisible(False)
        self._busy(False)

    def _busy(self, on: bool) -> None:
        for w in (self.btn_open, self.btn_paste, self.btn_crop, self.chips_axis,
                  self.spin_px, self.spin_py, self.btn_double, self.btn_reset):
            w.setEnabled(not on)

    def _on_override(self) -> None:
        """使用者自己打了一個週期 —— 同 `_on_axis`：**當場重畫，不等相位**。

        相位還是舊的那一個，所以格線可能整排偏半格幾秒鐘 —— 但**週期對不對**
        （格子有沒有跟著結構走）當場就看得出來，而那才是他打這個數字要問的事。
        """
        if self._m is None:
            self._fill_answer()
            return
        self._fill_answer()
        self._fill_notes()
        self._draw()
        self.remeasure(reuse=True)

    def _on_double(self) -> None:
        """兩格一起 ×2（沒打過就從量到的那個翻倍）。"""
        if self._m is None:
            return
        ex, ey = effective_period(self._m, self.override())
        self._set_override(min(8192.0, ex * 2.0), min(8192.0, ey * 2.0))

    def _on_reset(self) -> None:
        self._set_override(0.0, 0.0)

    def _set_override(self, px: float, py: float) -> None:
        """兩格一起換，**只重畫一次**（各自 `setValue` 會跑兩趟 worker）。"""
        for sp in (self.spin_px, self.spin_py):
            sp.blockSignals(True)
        self.spin_px.setValue(float(px))
        self.spin_py.setValue(float(py))
        for sp in (self.spin_px, self.spin_py):
            sp.blockSignals(False)
        self._on_override()

    def _on_axis(self, _value: str) -> None:
        """軸向改了 —— **週期不重量**（見 `_PitchWorker` 的說明）。

        ⚠ **格線要當場重畫，不能等相位搜尋回來。** 第一版沒有這一行，症狀是
        按下「X only」之後表格立刻寫 `not used`，而圖上的**橫線還在**，一等
        好幾秒 —— 畫面同時在說兩件相反的事，而使用者會相信圖。
        舊的原點先用著（丟掉 Y 軸不會讓 X 的相位改變），worker 回來再換成
        重新搜出來的那一個。
        """
        if self._m is None:
            return
        self._fill_answer()
        self._fill_notes()
        self._draw()
        self.remeasure(reuse=True)

    # -- 畫面 ---------------------------------------------------------------
    def axis(self) -> str:
        return self.chips_axis.text() or AXIS_AUTO

    def nm_per_px(self) -> float:
        return float(self.spin_nm.value())

    def override(self) -> Override:
        """使用者自己打的那一組（``None`` ＝ 那一軸用量到的）。"""
        px, py = float(self.spin_px.value()), float(self.spin_py.value())
        return (px if px >= MIN_PERIOD_PX else None,
                py if py >= MIN_PERIOD_PX else None)

    def _flags(self) -> Tuple[bool, bool]:
        """哪幾軸算數 —— **表格、notes、格線三個地方問的是同一支**。

        各自算一次的話，畫面上會出現「表格說 Y 沒在用、格線卻切了橫線」
        —— 這個視窗已經被那種形狀咬過一次（見 `_on_axis`）。
        """
        if self._m is None:
            return (False, False)
        ov = self.override()
        ex, ey = effective_period(self._m, ov)
        return axis_flags(self.axis(), ex, ey,
                          100.0 if ov[0] else self._m.conf_x,
                          100.0 if ov[1] else self._m.conf_y)

    def _typed_note(self) -> str:
        """「現在用的是誰的數字」那一行 —— 沒改過就是空字串。

        ⚠ 改過了一定要**看得到**。少了這一行，使用者換一張圖之後還掛著上一次
        打的 80，而畫面上沒有任何東西說那個 80 是他自己打的。
        """
        ox, oy = self.override()
        if not ox and not oy:
            return ""
        if self._m is None:
            return "Using the size you typed."
        bits = []
        for name, typed, got in (("across", ox, float(self._m.px or 0)),
                                 ("down", oy, float(self._m.py or 0))):
            if typed:
                bits.append("%s: yours %s, it measured %s"
                            % (name, algo_period2d.fmt_px(typed),
                               algo_period2d.fmt_px(got) if got >= MIN_PERIOD_PX
                               else "nothing"))
        return "Not the measured size — " + "; ".join(bits) + ". “Reset” puts it back."

    def rows(self) -> List[Tuple[str, str, str, str]]:
        """畫面上那張表（測試讀這個，不必去挖 QLabel）。"""
        if self._m is None:
            return [(lab, PITCH_UNSET, "", PITCH_UNSET)
                    for lab in ("Across (X)", "Down (Y)")]
        return pitch_rows(self._m, self.axis(), self.nm_per_px(),
                          self.override())

    def _fill_answer(self) -> None:
        rows = self.rows()
        for cells, row in zip(self._cells, rows):
            for lab, text in zip(cells, row):
                lab.setText(text)
        # nm 那一欄的欄名**跟著那一欄有沒有東西一起出現**。常駐一個
        # 「nanometres」而底下空白的話，它看起來像「算不出來」而不是
        # 「你還沒告訴我一個像素是幾奈米」——後者才是實情，而它有解。
        self._heads[2].setText("nanometres" if any(r[2] for r in rows) else "")
        self.lab_typed.setText(self._typed_note())

    def _fill_notes(self) -> None:
        if self._m is None:
            self.notes.setPlainText("")
            return
        lines = list(getattr(self._m, "notes", None) or [])
        use_x, use_y = self._flags()
        if not use_x and not use_y:
            lines.append("no repeating period could be measured in this image")
        elif self.axis() in (AXIS_X, AXIS_Y):
            lines.append("you chose %s, so only that direction is cut"
                         % AXIS_LABELS[self.axis()])
        elif self.axis() == AXIS_BOTH:
            lines.append("you chose X + Y, so both directions are cut even "
                         "where the measurement was not confident")
        stag = float(getattr(self._m, "stagger", 0.0) or 0.0)
        if use_x and use_y and stag > 0.0:
            lines.append("staggered-lattice score %.2f (near 1 means the rows "
                         "are offset by half a cell; near 0 means a plain "
                         "grid)" % stag)
        if not lines:
            # **沒有話要說也要說一句。** 一個空框答不出「是沒問題，還是它根本
            # 沒跑？」—— 而那兩件事在這個視窗上長得一模一樣。
            lines = ["nothing unusual — both directions were measured straight "
                     "off, no correction was needed"]
        self.notes.setPlainText("\n".join("• %s" % s for s in lines))

    def _draw(self) -> None:
        """格線鋪回原圖 —— **`lattice_boxes` 本人**，不自己再算一次格子。"""
        if self._work is None or self._m is None or not self.chk_grid.isChecked():
            self.view.set_overlay(None)
            if self._m is not None:
                self.caption.setText("Grid hidden — tick “Show the cell grid” "
                                     "to check the period against the image.")
            return
        flags = self._flags()
        if not flags[0] and not flags[1]:
            self.view.set_overlay(None)
            self.caption.setText("No period to draw.")
            return
        shape = self._work.shape[:2]
        # ⚠ **畫的是「真的在用的那一組」，不是量到的那一組。** 少了這一行，
        # 使用者打了 120、表格寫 120，而格線還是照 60 畫 —— 他會看到一張
        # 「我打的數字明明對，格線卻不對」的畫面，然後不相信他自己的答案。
        ex, ey = effective_period(self._m, self.override())
        ux, uy = lattice_periods(shape, ex, ey, flags)
        boxes, total = lattice_boxes(shape, ux, uy, self._origin, flags)
        self.view.set_overlay(boxes)
        text = ("Every box is one cell: %s, %d of them"
                % (algo_template.period_text(ux, uy), total))
        if len(boxes) < total:
            text += " (the %d nearest the centre are drawn)" % len(boxes)
        self.caption.setText(
            text + ". If they frame the same structure everywhere the period "
            "is right; if they drift onto something else towards one side it "
            "is off. Wheel zooms, drag pans, double-click fits.")

    def _say(self, text: str) -> None:
        self.statusBar().showMessage(str(text), 8000)

    def _sync(self) -> None:
        self._fill_answer()

    # -- 手勢 ---------------------------------------------------------------
    def keyPressEvent(self, e) -> None:  # Qt hook
        if e.matches(getattr(e, "Paste", None) or 0) or (
                e.key() == Qt.Key_V and e.modifiers() & Qt.ControlModifier):
            self.paste_image()
            return
        super().keyPressEvent(e)

    def dragEnterEvent(self, e) -> None:  # Qt hook
        if e.mimeData() is not None and e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # Qt hook
        urls = list(e.mimeData().urls()) if e.mimeData() is not None else []
        if not urls:
            return
        path = urls[0].toLocalFile()
        if not path:
            return
        from d4t.core.ingest import imageio as ingest_imageio
        import os
        try:
            arr = ingest_imageio.load_gray(str(path))
        except Exception as exc:
            self._say("Could not open that image: %s" % exc)
            return
        e.acceptProposedAction()
        self.set_image(arr, os.path.basename(str(path)), ask_crop=True)

    def closeEvent(self, e) -> None:  # Qt hook
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(3000)
        super().closeEvent(e)


def _qimage_to_gray(img: Optional[QImage]) -> Optional[np.ndarray]:
    """剪貼簿的 QImage → uint8 灰階 2D。空的或壞的回 ``None``。

    ⚠ **一定要先轉成 ``Format_Grayscale8``**：截圖多半是 ARGB32，它的 `bits()`
    是 BGRA 四個 byte 一組，直接 reshape 會拿到「寬度四倍、內容是交錯通道」的
    東西 —— 而那**看起來仍然像一張圖**（條紋狀），只是每一個數字都不對。
    （同 `gc_generator.qimage_to_gray`；那一支綁在它自己的匯入流程上，這裡只要
    這一段，所以不從那邊 import 一個視窗模組。）
    """
    if img is None or img.isNull():
        return None
    g = img.convertToFormat(QImage.Format_Grayscale8)
    h, w = g.height(), g.width()
    if h < 4 or w < 4:
        return None
    buf = np.frombuffer(bytes(g.constBits()), dtype=np.uint8)
    stride = g.bytesPerLine()
    return buf[:h * stride].reshape(h, stride)[:, :w].copy()


def run(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m d4t pitch`` 的進入點。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(list(argv or []))
    theme.apply_theme(app)
    win = PitchHelperWindow()
    win.show()
    return int(app.exec())

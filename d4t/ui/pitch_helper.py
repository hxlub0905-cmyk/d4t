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

「怎麼證明它是對的」—— 疊起來看（使用者 2026-09-21 指定的做法）
----------------------------------------------------------------
> 「仿照所謂的 AMAT 的 golden cell：將 period 週期用格線切完後，將所有的每個
>  cell 放在一起，如果取的 period 是完美的，他會有疊加 Frame 的效果，GC 影像
>  會很漂亮；如果 period 錯，格線切的差，疊起來就會糊糊的。」

所以畫面上是**兩張圖**，而不是一堆分數：

1. **原圖 ＋ 切點格線** —— 格子有沒有跟著同一種結構走（F103 那一套）；
2. **疊起來的那一格**（`golden.stack_cells`，走 `build_golden_cell` 本人）——
   清楚 ＝ 週期對，糊掉／出現兩層 ＝ 週期錯。**一眼的事，不需要懂任何分數。**

⚠ **旁邊那個數字是 `agreement`，不是 sharpness** —— 而那個選擇是量出來的
（F40，2026-08-26）。使用者的直覺（「或是算 sharpness 這樣評估」）是自然的，
但 `ghosting_score` 只看疊完的那一張圖，**看不到疊進去的那幾格**，所以分不出
「因為對齊了所以銳利」與「因為兩個鬼影各帶一組邊所以銳利」—— 相位錯掉的 stack
實測拿到 **76.1**，而正確的只有 **68.4**；純雜訊在 σ=60 拿 **99.4**。
`golden.stack_agreement` 問的是那幾格**彼此**對得多齊（`var(mean(cells)) /
mean(var(cell))`，扣掉 `1/n` 的地板），無量綱、跨影像可比，所以它才是那個可以
配固定門檻的數字。**人眼看那張圖 ＋ 這個數字，兩個一起才完整。**

單位：px 是答案，nm 是換算
--------------------------
`docs/FAB-VALIDATION.md` 假設 #2 已經定調：``nm_per_px`` 在 KLARF 裡沒有來源，
所以**單位一律 pixel、換算搬到輸出那一刻**。這裡照抄卡片那一套
（`steps/_util.nm_per_px_spec`）：**0 ＝ 不知道，那一欄就不出現**。
顯示一個 `0 nm` 比不顯示糟得多 —— 它看起來像一個量出來的答案。

版面：一分鐘之內要答得完（使用者 2026-09-21）
---------------------------------------------
> 「user 進來是要 1 min 內解決問題，而不是找按鍵還要看一堆文字。」

所以是**一條細工具列 ＋ 左圖右答案**，而右邊由上而下就是使用者的問題順序：

    pitch 是多少 → 哪個方向 → 不對的話我自己改 → 憑什麼相信它

第一版是四個編號方塊由上而下、每一塊都帶一段說明，讀完才知道要按哪裡。
三條換掉它的規則寫在 :class:`PitchHelperWindow` 的 docstring 裡。

刻意不放進 Studio 的工具列
--------------------------
同 `gc_generator` 的理由，逐字適用：那條工具列已經滿到把「Results」擠進 Qt 的
overflow 過一次（F48）。這是一個**問一個數字**的工具，不是分析流程的一步。
開法：``python -m d4t pitch``。
"""
from __future__ import annotations

import os
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QMainWindow, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from d4t.core.algo import period as algo_period
from d4t.core.algo import period2d as algo_period2d
from d4t.core.algo import template as algo_template
from d4t.core.log import swallowed

from . import branding, fit_screen, theme
from .chips import ChoiceChips
from .crop_dialog import CropDialog, crop_array, describe_crop
from .image_view import ImageView
from .lattice_dialog import lattice_boxes
# ⚠ **為了一個常數 import 一整支 1,300 行的對話框**，而那是刻意的：
# `BLURRED_BELOW`（疊出來算不算糊）在模板那條路上已經有一個家，而**同一件事
# 不准有兩個門檻** —— 抄一個 0.5 過來，兩邊哪天分岔了沒有人會發現。
# 代價量過：`import pitch_helper` 408 ms，而其中絕大部分是 Qt／numpy／cv2；
# `template_dialog` 拉進來的 `crop_dialog`／`lattice_dialog` 這一支本來就要用。
# 真要拆的話，正確的做法是把那個常數搬去 `algo/golden.py`（它是
# `stack_agreement` 的門檻，本來就該住在那支旁邊），**不是**在這裡抄一份。
from .template_dialog import BLURRED_BELOW
from .theme import TOKENS
from .widgets import apply_button_cursors, to_uint8

__all__ = [
    "PitchHelperWindow", "Bar", "AXES", "AXIS_AUTO", "AXIS_X", "AXIS_Y",
    "AXIS_BOTH", "axis_flags", "lattice_periods", "px_text", "nm_text",
    "pitch_rows", "effective_period", "conf_tone", "agree_tone", "Override",
    "PITCH_UNSET", "PITCH_NOT_USED", "CONF_TYPED", "TONE_GOOD", "TONE_WARN",
    "TONE_BAD", "CONF_GOOD_FROM", "AGREE_GOOD_FROM", "CELL_BOX",
    "BAR_W", "BAR_H", "candidate_periods", "candidate_label",
    "detail_rows", "trust_note", "MIN_CELLS_TO_TRUST",
    "MAX_CANDIDATES", "cells_along", "trim_to_inner",
    "MIN_CELLS_AFTER_TRIM", "run",
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
#: ⚠ **``X + Y`` 改名成 ``Force both``**（使用者 2026-09-21：「Auto 跟 X+Y 差在
#: 哪裡？」）。差別是真的存在的 —— Auto 會把信心不夠的那一軸丟掉，這一顆不會
#: —— 但 ``X + Y`` 這個字**只講了它做什麼，沒講它跟 Auto 差在哪**，而畫面上
#: 一個看不出差別的選項等於一個陷阱。``Force`` 這個字就是那個差別。
AXIS_LABELS = {
    AXIS_AUTO: "Auto",
    AXIS_X: "X only",
    AXIS_Y: "Y only",
    AXIS_BOTH: "Force both",
}
#: ⚠ 每一句只留**「什麼時候按它」**。第一版四句話加起來 60 個字掛在四顆膠囊
#: 底下，而使用者同一輪說了「UI 內字太多」——  說明的長度跟它被讀到的機率成
#: 反比。
AXIS_HELP = {
    AXIS_AUTO: ("Let the image decide. A direction it is not confident about "
                "is left out - a made-up period is worse than none."),
    AXIS_X: "It only repeats across. One cell is the full height.",
    AXIS_Y: "It only repeats down. One cell is the full width.",
    AXIS_BOTH: ("Both directions, even where Auto was not confident. That is "
                "the only difference from Auto."),
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
    """px × nm/px → ``"0.150 µm"``；**不知道 nm/px 就回空字串**。

    ⚠ **輸入是 nm/px，輸出是 µm**（使用者 2026-09-21 指定）。那不是不一致：
    機台設定裡的像素大小就是以 nm 講的，而 pitch 這種尺度在廠內是以 µm 報的。
    換算住在畫面這一層，core 仍然只有 pixel（`docs/FAB-VALIDATION.md` 假設 #2）。

    ⚠ 回空字串而不是 ``"0 µm"``／``"—"``：呼叫端拿到空字串就整欄不放
    （見模組說明的「單位」那一段）。一個 `0 µm` 看起來像一個量出來的答案。
    """
    s = float(nm_per_px or 0.0)
    v = float(value or 0.0)
    if s <= 0 or v < MIN_PERIOD_PX or not used:
        return ""
    return "%.3f µm" % (v * s / 1000.0)


#: 一張圖裡至少要放得下這麼多格，`agreement` 才讀得出「差一點點」。
#:
#: ⚠ **這個數字是量出來的，而且它推翻了一個我原本以為成立的假設**（F120，
#: 2026-09-21）。漂移 ＝ 誤差 × 格數，所以同一個相對誤差在小圖上根本累積不起來：
#: 真實 pitch 60、故意用 65（差 8.3%）去疊 ——
#:
#: =========  ======  ================
#: 影像        格數    cells agree
#: =========  ======  ================
#: 900 px 寬   15      **0.39**（紅，對）
#: 300 px 寬   5       **0.76**（綠，錯）
#: =========  ======  ================
#:
#: 也就是說**裁太小的時候那個綠燈是假的**。分數本身沒有錯（那幾格在那張小圖上
#: 真的對得起來），錯的是拿它回答「週期對不對」。所以格數太少要講出來。
MIN_CELLS_TO_TRUST = 8

#: 最多提幾個候選（畫面上一排，多了就變成一張表）。
MAX_CANDIDATES = 4


def cells_along(shape: Tuple[int, int], px: float, py: float,
                flags: Tuple[bool, bool]) -> int:
    """**在用的那幾軸裡，格數最少的那一軸有幾格。**

    ⚠ **不是總格數。** 第一版拿 `GoldenCell.n_cells`（= nx × ny）去判斷，而
    那答的是另一個問題：300×240 的圖用 65×44 去切是 4×5 ＝ **20 格**，看起來
    很多 —— 但沿 X 只有 **4** 格，而漂移 ＝ 誤差 × **那一軸的**格數。
    拿 20 去比門檻的話，最該警告的那張圖不會被警告到。
    """
    h, w = int(shape[0]), int(shape[1])
    counts = []
    if flags[0] and float(px or 0) >= MIN_PERIOD_PX:
        counts.append(int(w // float(px)))
    if flags[1] and float(py or 0) >= MIN_PERIOD_PX:
        counts.append(int(h // float(py)))
    return min(counts) if counts else 0


def trust_note(n_along: int) -> str:
    """格數夠不夠讓 `agreement` 說得上話；夠的話回空字串。

    ``n_along`` 是 :func:`cells_along` 的答案（**單軸**，不是總格數）。
    """
    n = int(n_along or 0)
    if n >= MIN_CELLS_TO_TRUST:
        return ""
    return ("only %d cells fit along one direction — “cells agree” cannot tell "
            "a slightly wrong period from a right one at this size. Judge by "
            "the stacked picture, or measure from a larger area." % n)


def candidate_periods(measured: Any, flags: Tuple[bool, bool],
                      current: Tuple[float, float],
                      cap: int = MAX_CANDIDATES
                      ) -> List[Tuple[float, float]]:
    """「取錯怎麼辦」的答案：**諧波上的其他可能**，點一下就套用。

    取錯幾乎永遠是取到諧波裡的另一個（半週期、兩倍、只有一軸是倍數），而
    `estimate_period` **本來就把那份清單算出來了**（`MeasuredPeriod.candidates`）
    —— 它以前算完就被丟掉。分數回答「它為什麼選這個」，這份清單回答
    「**那我現在該怎麼辦**」，而使用者問的是後者。

    規則：現在用的那一組不列（它已經在畫面上了）、沒在用的軸不列
    （純 X 的時候提 `60×88` 是沒有意義的）、同一個值只列一次。
    """
    cur_x, cur_y = float(current[0] or 0.0), float(current[1] or 0.0)
    out: List[Tuple[float, float]] = []
    seen = set()
    for cx, cy in (getattr(measured, "candidates", None) or []):
        x = float(cx or 0.0) if flags[0] else cur_x
        y = float(cy or 0.0) if flags[1] else cur_y
        if flags[0] and x < MIN_PERIOD_PX:
            continue
        if flags[1] and y < MIN_PERIOD_PX:
            continue
        if (abs(x - cur_x) < 0.5 and abs(y - cur_y) < 0.5) or (x, y) in seen:
            continue
        seen.add((x, y))
        out.append((x, y))
        if len(out) >= cap:
            break
    return out


def candidate_label(px: float, py: float, flags: Tuple[bool, bool]) -> str:
    """候選鈕上的字 —— **沒在用的軸不寫**（純 X 的時候 `60 × 88` 是噪音）。"""
    fx = algo_period2d.fmt_px(px)
    fy = algo_period2d.fmt_px(py)
    if flags[0] and flags[1]:
        return "%s × %s" % (fx, fy)
    return fx if flags[0] else fy


def detail_rows(measured: Any, flags: Tuple[bool, bool]
                ) -> List[Tuple[str, str, str]]:
    """三票各自的答案 → ``[(方法, X, Y), …]``（Details 那一塊的唯一算法）。

    ⚠ **三票不一致不是錯誤，是關於這張圖的事實。** 投影法看到 30、二維看到
    60、答案是 60 —— 那句「投影法看到 30」講的是這個 layout 相鄰列交錯，
    而使用者看得懂那件事。
    """
    def cell(v, conf, used):
        if not used:
            return "—"
        if v is None or float(v) < MIN_PERIOD_PX:
            return "not found"
        return "%s  (%.0f)" % (algo_period2d.fmt_px(float(v)), float(conf or 0))

    m = measured
    rows = [
        ("Projection", cell(getattr(m, "proj_px", None),
                            getattr(m, "proj_conf_x", 0), flags[0]),
                       cell(getattr(m, "proj_py", None),
                            getattr(m, "proj_conf_y", 0), flags[1])),
        ("2-D autocorr", cell(getattr(m, "ac_px", None),
                              getattr(m, "ac_conf_x", 0), flags[0]),
                         cell(getattr(m, "ac_py", None),
                              getattr(m, "ac_conf_y", 0), flags[1])),
    ]
    gx = float(getattr(m, "half_gain_x", 0.0) or 0.0)
    gy = float(getattr(m, "half_gain_y", 0.0) or 0.0)
    dx, dy = getattr(m, "doubled", (False, False))
    rows.append(("Half-period",
                 ("doubled (+%.2f)" % gx) if dx else
                 ("no (%+.2f)" % gx if flags[0] else "—"),
                 ("doubled (+%.2f)" % gy) if dy else
                 ("no (%+.2f)" % gy if flags[1] else "—")))
    rows.append(("Used",
                 algo_period2d.fmt_px(float(getattr(m, "px", 0) or 0))
                 if flags[0] else "—",
                 algo_period2d.fmt_px(float(getattr(m, "py", 0) or 0))
                 if flags[1] else "—"))
    return rows


#: 去掉最外一圈之後，每一軸至少要留下這麼多格才值得去。
#:
#: 少於它就不去了 —— 拿掉邊界是為了讓 GC 乾淨，而把 3×3 疊成 1×1 換不到乾淨，
#: 只換到一個「其實沒有在疊」的 stack。
MIN_CELLS_AFTER_TRIM = 3


def trim_to_inner(shape: Tuple[int, int], px: float, py: float,
                  origin: Tuple[float, float], flags: Tuple[bool, bool]
                  ) -> Optional[Tuple[int, int, int, int]]:
    """**把最外一圈格子切掉**的那一塊（``(x0, y0, x1, y1)``；不值得去回 None）。

    使用者 2026-09-21：「邊界其實我有點不太想放。」而那是量得出來的 ——
    帶真實掃描邊緣效應（最外 40 px 偏亮／偏暗 ＋ 額外雜訊）的合成圖上：
    整張疊 `agreement` **0.872**（210 格），去掉最外一圈 **0.980**（156 格）；
    乾淨影像上兩者都是 0.980，也就是**它在不需要的時候不花任何成本**。

    切的是**沿著格線**的一整圈，不是隨便一圈像素 —— 切完之後相位不變
    （``origin`` 相對新的左上角變成 0），所以疊出來的還是同一組格子，只是少了
    貼邊的那些。不在用的軸不切（那一軸一格就是整張影像，切了就什麼都不剩）。
    """
    h, w = int(shape[0]), int(shape[1])
    # ⚠ **沒在用的那一軸，原點是 0。** 這一行跟 `lattice_boxes` 裡的
    # ``oy = float(origin[1]) if periodic[1] else 0.0`` 是**同一個規則**，而這裡
    # 本來沒有 —— 於是 X only 模式整個壞掉：相位搜尋在一個「一格就是
    # 整張高」的軸上也會回一個 `oy`（實測 129），這裡拿它當上邊界，
    # 而格子是從 y=0 開始、700 高—— **一格都塞不進去**。畫面上看到的是
    # 格線消失、「0 cells」、一條紅的 `Cells agree 0.00` 跟一句
    # 「this period is wrong」—— 而那個週期是對的（信心 92）。
    #
    # 這是這一輪**第四次**踩到同一種形狀（`_on_axis`、`_draw` 的週期、
    # 畫的格子跟疊的格子、這裡）：**同一件事在畫面上有兩個算法**。
    ox = float(origin[0] or 0.0) if flags[0] else 0.0
    oy = float(origin[1] or 0.0) if flags[1] else 0.0
    x0, y0, x1, y1 = int(ox), int(oy), w, h
    if flags[0] and float(px or 0) >= MIN_PERIOD_PX:
        nx = int((w - int(ox)) // float(px))
        if nx - 2 < MIN_CELLS_AFTER_TRIM:
            return None
        x0 = int(ox + px)
        x1 = int(ox + px * (nx - 1))
    if flags[1] and float(py or 0) >= MIN_PERIOD_PX:
        ny = int((h - int(oy)) // float(py))
        if ny - 2 < MIN_CELLS_AFTER_TRIM:
            return None
        y0 = int(oy + py)
        y1 = int(oy + py * (ny - 1))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    return (x0, y0, x1, y1)


Override = Tuple[Optional[float], Optional[float]]

#: 使用者自己打了一個週期、而且**這張圖沒辦法替它打分**時，那一欄寫什麼。
#:
#: ⚠ **不准沿用量出來的那個分數。** 信心量的是「把圖平移這個週期之後跟自己
#: 有多像」，而那是對**量出來的那個數字**做的。使用者把 40 改成 80 之後還
#: 掛著 92/100，等於用一個他沒有問過的問題的答案，去背書他剛打進去的數字。
#:
#: ⚠ **但「不能沿用」不等於「沒有分數」**（使用者 2026-09-21：「自定義 period
#: 右上可否也能算 confidence？」）。同一個問題可以**對他打的那個數字重問一次**
#: —— 那正是 :func:`d4t.core.algo.period.confidence_at`：一樣的投影、一樣的
#: 自相關，只是在他指定的 lag 上取值，所以兩個數字同尺度、可以直接比。實測
#: 量到 60 得 92.4，打 59 得 86.6、打 45 得 0.0 —— 打錯的那一刻長條就變紅，
#: 這比任何一句警告都快。
#: 這一格因此只剩**打不出分數**的退路（還沒載圖、lag 大過半張圖）。
#: 字要短：那一格旁邊就是橫條，長句子會被切成「you typ…」（量到過）。
CONF_TYPED = "yours"


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
               override: Override = (None, None),
               typed_conf: Override = (None, None)
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
            tc = typed_conf[0 if label.startswith("Across") else 1]
            conf_text = CONF_TYPED if tc is None else "%.0f / 100" % float(tc)
        elif got:
            conf_text = "%.0f / 100" % conf
        else:
            conf_text = PITCH_UNSET
        rows.append((label, px_text(value, used),
                     nm_text(value, used, nm_per_px), conf_text))
    return rows


# --------------------------------------------------------------------------- #
# 「這個分數是好是壞」—— 一個橫條的顏色（使用者 2026-09-21：「除了數字外也要
# 有視覺 UI（橫向長條／綠黃紅）」）
# --------------------------------------------------------------------------- #
TONE_GOOD, TONE_WARN, TONE_BAD = "good", "warn", "bad"

#: 那條長條的軌道有多長／多高（像素）。**長度是可讀性，不是裝飾**：
#: 92 px 的時候 92 分與 100 分在畫面上分不出來（見 :class:`Bar`）。
BAR_W = 150
BAR_H = 11

#: 信心的三段。**綠那一段不是 100**：真的有週期的實測落在 87–98，而
#: 40 以下 `build_golden_cell` 自己就不採用了（`MIN_PERIOD_CONFIDENCE`）。
#: 中間那一段的意思是「**一定要看下面那張疊出來的 cell**」，不是「壞掉了」。
CONF_GOOD_FROM = 85.0

#: 疊出來的那幾格彼此對得齊不齊（`golden.stack_agreement`，0–1）。
#: 綠那一段從 `template_dialog.BLURRED_BELOW` 來 —— **同一個門檻，同一個家**：
#: 模板那條路說「低於它就是糊的」，helper 沒有理由說另一個數字。
AGREE_GOOD_FROM = 0.75


def conf_tone(value: float) -> str:
    """信心 0–100 → 綠／黃／紅。"""
    v = float(value or 0.0)
    if v >= CONF_GOOD_FROM:
        return TONE_GOOD
    if v >= algo_template.MIN_PERIOD_CONFIDENCE:
        return TONE_WARN
    return TONE_BAD


def agree_tone(value: float) -> str:
    """一致性 0–1 → 綠／黃／紅（黃紅的界線就是模板那條路的 `BLURRED_BELOW`）。"""
    v = float(value or 0.0)
    if v >= AGREE_GOOD_FROM:
        return TONE_GOOD
    if v >= BLURRED_BELOW:
        return TONE_WARN
    return TONE_BAD


class Bar(QWidget):
    """一條 **0–100 的橫向長條**：填到那個分數的比例，顏色按分數綠／黃／紅。

    使用者 2026-09-21：「有一個橫向的長條（示意 0–100），然後裡面可能 80 分
    是綠的（填滿到 80%），60 分黃的（填滿到 60 分）。」

    ⚠ **軌道要夠長，不然「填到幾成」讀不出來。** 第一版 92 px 寬、8 px 高：
    92 分填出來是 85 px，跟填滿的 100 分**在畫面上分不出來** —— 而那個差別
    正是這條長條存在的理由。現在 :data:`BAR_W` / :data:`BAR_H`。

    ⚠ **顏色不是唯一的通道。** 數字一直都在（紅綠色覺缺陷者看不出顏色差別，
    而這一條是「這個答案可不可信」唯一的一眼答案）。這是 F117 U13 定下來的
    規矩：底色是第二個通道，不是唯一的。
    """

    def __init__(self, parent: Optional[QWidget] = None, width: int = 0):
        super().__init__(parent)
        self._frac = 0.0
        self._tone = TONE_WARN
        self._text = ""
        self._track = True
        self._w = int(width) or BAR_W
        self.setMinimumSize(self._w + 46, BAR_H + 8)

    def set_value(self, frac: float, tone: str, text: str) -> None:
        self._frac = float(np.clip(float(frac or 0.0), 0.0, 1.0))
        self._tone = str(tone)
        self._text = str(text)
        self._track = True
        self.update()

    def set_text_only(self, text: str) -> None:
        """**沒有分數可言的時候不要畫那條軌道。**

        使用者自己打的週期就是這一種：畫一條空軌道等於說「這個數字拿了 0 分」，
        而實情是「這個數字根本沒有被評分過」—— 兩件事在畫面上長得一樣就是說謊。
        """
        self._frac, self._tone, self._text = 0.0, TONE_WARN, str(text)
        self._track = False
        self.update()

    def value_text(self) -> str:
        """測試讀這個（不必去解析畫出來的像素）。"""
        return self._text

    def tone(self) -> str:
        return self._tone

    def paintEvent(self, e) -> None:  # Qt hook
        # ⚠ `paintEvent` 不准把例外往外丟：一個沒收尾的 painter 會讓**之後
        # 每一次重繪**都失敗，而壞掉的地方跟看到的地方不一樣
        # （`docs/PITFALLS.md` 第一列）。
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            h = BAR_H
            y = (self.height() - h) // 2
            p.setPen(Qt.NoPen)
            if self._track:
                p.setBrush(QColor(TOKENS["border_default"]))
                p.drawRoundedRect(0, y, self._w, h, h / 2.0, h / 2.0)
                # ⚠ **0 分也要畫**（一顆紅點，寬度 = 高度）。這裡原本是
                # `if self._frac > 0`，於是 0 分畫出來是一條**空軌道** —— 跟
                # `set_text_only` 那個「沒有被評分過」長得一模一樣。而 0 分
                # 是這個視窗最需要講清楚的一格：使用者打了一個週期，圖在那個
                # 週期上完全不重複（實測打 45 對一張 60 的圖就是 0.0）。
                p.setBrush(QColor(_TONE_HEX[self._tone]))
                p.drawRoundedRect(0, y, max(h, int(self._w * self._frac)), h,
                                  h / 2.0, h / 2.0)
            x0 = (self._w + 8) if self._track else 0
            p.setPen(QColor(TOKENS["text_primary"] if self._track
                            else TOKENS["text_hint"]))
            p.drawText(x0, 0, self.width() - x0, self.height(),
                       int(Qt.AlignVCenter | Qt.AlignLeft), self._text)
        except Exception:
            swallowed("ui.pitch_helper.Bar.paintEvent")
        finally:
            p.end()


_TONE_HEX = {
    TONE_GOOD: TOKENS["chip_good_text"],
    TONE_WARN: TOKENS["warning"],
    TONE_BAD: TOKENS["danger"],
}


# --------------------------------------------------------------------------- #
# 背景執行緒
# --------------------------------------------------------------------------- #
class _PitchWorker(QThread):
    """量週期 → 疊 Golden Cell。**不在 GUI 執行緒跑** —— 4096² 要十幾秒。

    ⚠ **疊圖走 `build_golden_cell` 本人**（F120 第三版）。第一版只叫
    `choose_origin` 自己畫格線，而那繞過了整條路最有說服力的那一步：
    **把每一格疊起來**。使用者 2026-09-21 講的就是它 ——「仿照 AMAT 的
    golden cell，period 完美的話疊起來會很漂亮，period 錯的話疊起來糊糊的」。
    那條路已經在 repo 裡而且有測試，繞過它等於抄第二份。

    兩軸的週期**明講給它**（``px=``／``py=``），所以它不會再量一次
    （`build_golden_cell` 的 ``given`` 分支）—— 量已經在這裡做過，
    而且使用者可能自己打了一個。
    """

    stage = Signal(str)
    done = Signal(object, object, str)   # (MeasuredPeriod, GoldenCell, 錯誤)

    def __init__(self, image: np.ndarray, axis: str,
                 measured: Optional[Any] = None,
                 override: Override = (None, None), method: str = "mean",
                 skip_edges: bool = True, parent=None):
        super().__init__(parent)
        self._image = image
        self._axis = str(axis)
        self._measured = measured        # 有就不重量（只重疊）
        self._override = override
        self._method = str(method)       # mean / median（median 免疫稀疏缺陷）
        self._skip_edges = bool(skip_edges)
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
            ex, ey = effective_period(m, self._override)
            flags = axis_flags(self._axis, ex, ey,
                               100.0 if self._override[0] else m.conf_x,
                               100.0 if self._override[1] else m.conf_y)
            gc = None
            if flags[0] or flags[1]:
                ux, uy = lattice_periods(self._image.shape[:2], ex, ey, flags)
                gc = algo_template.build_golden_cell(
                    self._image, px=ux, py=uy, method=self._method,
                    progress=self._tick)
                if self._skip_edges and gc is not None and gc.cell.size:
                    gc = self._without_edges(gc, ux, uy, flags)
        except Exception as e:           # 講出來，不要吞掉（鐵則 7 的 UI 版）
            self.done.emit(None, None, "Could not measure this image: %s" % e)
        else:
            if self._stop:
                # ⚠ **被停掉的那一份不准出去。** 上面那道 `_stop` 只擋在量週期
                # 之後、疊圖之前；`build_golden_cell` 吃的 `progress=self._tick`
                # 也回 `not self._stop`，所以停在疊圖中途的時候它會回一份
                # **只疊了一半、n_cells = 0** 的 GoldenCell —— 而那一份走到畫面
                # 上長得就是「Cells agree 空白、0 cells」，也就是「這個週期不
                # 成立」。實際踩法：4096² 疊十幾秒，中途改一個設定就換掉了。
                #
                # 這是 repo 既有的那條規矩（鐵則 11「被停掉的部分結果拒寫並講
                # 出來」）在這個視窗的版本。`_on_done` 收到 `m is None` 會直接
                # 忽略，畫面因此停在上一個**完整**的答案上。
                self.done.emit(None, None, "")
                return
            self.done.emit(m, gc, "")

    def _without_edges(self, gc: Any, ux: float, uy: float,
                       flags: Tuple[bool, bool]) -> Any:
        """把最外一圈格子拿掉，**只重疊一次，不重跑相位搜尋**。

        相位已經知道了（`gc.origin`），而切掉的那一圈是沿著格線切的 —— 新的
        左上角就落在一條格線上，所以在那一塊裡原點是 (0, 0)。因此這裡叫的是
        `golden.stack_cells` / `stack_agreement` **本人**（`build_golden_cell`
        內部叫的也是這兩支），不是再跑一次整支 —— 相位搜尋在 4096² 要 5 秒，
        而它的答案不會因為少了一圈格子而改變。
        """
        from d4t.core.algo import golden as algo_golden
        box = trim_to_inner(self._image.shape[:2], ux, uy, gc.origin, flags)
        if box is None:
            return gc                       # 格子太少，拿掉不划算（見 `trim_to_inner`）
        x0, y0, x1, y1 = box
        inner = self._image[y0:y1, x0:x1]
        ix, iy = int(round(ux)), int(round(uy))
        before = gc                         # 剪完不划算的話要回得去（見下面）
        cell = algo_golden.stack_cells(inner, ix, iy, method=self._method)
        agree = algo_golden.stack_agreement(inner, ix, iy)
        n = len(algo_golden.tile_coords(inner.shape, ix, iy))
        if n < MIN_CELLS_AFTER_TRIM:
            # ⚠ **剪完什麼都不剩的話，要回到沒剪的那一份，不是報一個 0。**
            # `trim_to_inner` 已經擋掉格數太少的情形，但它算的是「沿著哪一軸
            # 剪幾格」，答不出「剪完那一塊裝不裝得下一個 cell」。而 0 格疊出來
            # 的 `agreement` 是 0.00，畫面上長得跟「這個週期是錯的」一模一樣
            # —— **一個算不出來的答案不准假裝成一個否定的答案**（同卡片那條
            # 「算不出來的那一格不寫」）。
            return before
        gc.cell, gc.agreement = cell, agree
        gc.ghosting, gc.lap_var, _e = algo_golden.ghosting_score(cell)
        gc.n_cells = n
        gc.trimmed = True                   # 畫面上要講出來（少了幾格是事實）
        return gc

    def _tick(self, stage: str, done: int = 0, total: int = 0) -> bool:
        """進度講到哪一步 **而且講到第幾格** —— 7680² 要十幾秒，一條跑不完的
        進度條答不出「它還在動嗎」。"""
        self.stage.emit("%s  %d/%d" % (stage, done, total) if total > 1
                        else str(stage))
        return not self._stop


# --------------------------------------------------------------------------- #
# 主視窗
# --------------------------------------------------------------------------- #
#: 疊出來那張 cell 顯示成多大（放大到這麼多像素見方，保持長寬比）。
#: 一格常常只有 40–80 px，原尺寸在螢幕上小到看不出糊不糊 —— 而「看得出糊不糊」
#: 正是它存在的唯一理由。150 是「放大得夠看出邊緣」與「右欄還排得下一致性
#: 那一格」之間量出來的那個值。
CELL_BOX = 150


class PitchHelperWindow(QMainWindow):
    """一張圖 → 它的 cell period，以及兩個看得出對不對的畫面。

    版面（使用者 2026-09-21：「user 進來是要 1 min 內解決問題，而不是找按鍵
    還要看一堆文字」）
    ------------------------------------------------------------------------
    第一版是四個編號方塊由上而下，每一塊都帶著一段說明 —— 讀完才知道要按哪裡。
    現在是**一條細工具列 ＋ 左圖右答案**，而右邊由上而下就是使用者的問題順序：

        pitch 是多少 → 哪個方向 → 不對的話我自己改 → 憑什麼相信它

    三條規則：

    * **畫面上不放使用者不必讀的字。** 說明退到 tooltip（同 `template_dialog`
      「第一版把每支工具寫成一句話擺在畫面上，使用者回報介面文字太多」）。
    * **警告只在有事的時候出現。** 第一版有一塊常駐的「What it decided」，
      而最常見的情形是它空著 —— 使用者 2026-09-21 的原話是「這我不知道可以
      幹嘛？」。沒有話要說的時候整條不佔位置。
    * **每一個分數都配一條橫條**（綠／黃／紅），數字照樣在（U13：顏色不是
      唯一的通道）。
    """

    #: 量完一次：(MeasuredPeriod, GoldenCell 或 None)。
    measured = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pitch helper — d4t")
        # **自己的圖示**（F120）：工作列上要分得出這不是 Studio。
        self.setWindowIcon(branding.pitch_icon())

        self._full: Optional[np.ndarray] = None      # 載進來的原圖
        self._work: Optional[np.ndarray] = None      # 裁過的（量的就是它）
        self._crop: Optional[Tuple[int, int, int, int]] = None
        self._name = ""
        self._m: Optional[Any] = None                # 上一次的 MeasuredPeriod
        self._gc: Optional[Any] = None               # 上一次疊出來的 Golden Cell
        self._worker: Optional[_PitchWorker] = None

        root = QWidget(self)
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(8)
        outer.addLayout(self._toolbar())

        split = QHBoxLayout()
        split.setSpacing(10)
        split.addWidget(self._image_side(), 1)
        split.addWidget(self._answer_side())
        outer.addLayout(split, 1)

        self.warn = QLabel("", root)
        self.warn.setObjectName("paramHint")
        self.warn.setWordWrap(True)
        self.warn.setVisible(False)
        outer.addWidget(self.warn)

        self.setAcceptDrops(True)
        fit_screen.fit(self, 1180, 780)
        apply_button_cursors(self)
        self._refresh()

    # -- 版面 ---------------------------------------------------------------
    def _toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_open = QPushButton("Open image…", self)
        self.btn_open.clicked.connect(self.open_image)
        self.btn_paste = QPushButton("Paste", self)
        self.btn_paste.setToolTip("Paste an image from the clipboard (Ctrl+V).")
        self.btn_paste.clicked.connect(self.paste_image)
        self.btn_crop = QPushButton("Crop…", self)
        self.btn_crop.setToolTip(
            "Measure from one part only — leave out the defect, scribe lines "
            "and the scale bar. They are not the repeating layout.")
        self.btn_crop.clicked.connect(self.ask_crop)
        # **入口要長得像入口。** 三顆一樣灰的鈕，使用者第一眼不知道該按哪一個
        # —— 而這個視窗只有一個起點。
        self.btn_open.setObjectName("primary")   # 藍的那一顆（見 theme 的 #primary）
        for b in (self.btn_paste, self.btn_crop):
            b.setProperty("variant", "secondary")
        for b in (self.btn_open, self.btn_paste, self.btn_crop):
            row.addWidget(b)
        self.lab_source = QLabel("Drop an image here, open one, or paste one.",
                                 self)
        self.lab_source.setObjectName("paramHint")
        row.addWidget(self.lab_source, 1)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(150)
        self.progress.setVisible(False)
        row.addWidget(self.progress)
        return row

    def _image_side(self) -> QWidget:
        box = QWidget(self)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.view = ImageView(box)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        self.chk_grid = QCheckBox("Cut lines", box)
        self.chk_grid.setChecked(True)
        self.chk_grid.setToolTip("Draw the cell boundaries on the image.")
        self.chk_grid.toggled.connect(lambda _on: self._draw())
        row.addWidget(self.chk_grid)
        self.caption = QLabel("", box)
        self.caption.setObjectName("paramHint")
        row.addWidget(self.caption, 1)
        lay.addLayout(row)
        return box

    @staticmethod
    def _section(parent: QWidget, text: str) -> QLabel:
        """一條分段標題（次要色 ＋ 底線）。

        用的是這個 app 自己的 ``paramSection`` 樣式，**不發明第二種分段長相**
        —— 設定區已經是這個樣子，使用者不必學兩次。它買到的是**節奏**：
        第一版右欄是五塊東西用 6 px 疊在一起，而「排版很怪」多半就是這個。
        """
        lab = QLabel(str(text), parent)
        lab.setObjectName("paramSection")
        return lab

    def _answer_side(self) -> QWidget:
        box = QWidget(self)
        # ⚠ **這個寬度是量出來的，不是挑的。** 340 的時候：四顆膠囊擠成兩排、
        # 疊出來那一格跟旁邊的說明**畫在一起**（Qt 在空間不夠時就是會重疊，
        # 不會報錯 —— 那是版面 bug 最常見的長相）。380 是四顆膠囊排得下、
        # 150 的 cell ＋ 一致性那一欄也排得下的寬度。
        box.setFixedWidth(380)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # ---- 答案 ----------------------------------------------------------
        # **這個視窗只回答一件事**，所以畫面上只有一個東西可以是最大的字。
        # 這一塊就是那件事：一行 `60 × 44 px`、底下換算成 µm、再底下是兩條
        # 信心長條。使用者的話：「顯示的 period（結果）要大一點放中間，
        # 因為是重點」。
        #
        # ⚠ 字級走 **QSS 的 objectName**（`pitchAnswer`），不是 `setFont()`
        # —— theme 的 ``* { font-size }`` 會蓋掉 per-widget 的 QFont，而 Qt
        # 不會抱怨。F120 連三輪「把答案放大」就是這樣安靜地沒有生效
        # （量出來一直是 13px，跟旁邊的說明一樣大）。
        self.grid_answer = QGridLayout()
        self.grid_answer.setHorizontalSpacing(8)
        self.grid_answer.setVerticalSpacing(2)
        self._cells: List[List[QLabel]] = []
        self._bars: List[Bar] = []
        self._tags: List[QLabel] = []
        self.lab_big = QLabel(PITCH_UNSET, box)
        self.lab_big.setObjectName("pitchAnswer")
        self.lab_big.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.grid_answer.addWidget(self.lab_big, 0, 0, 1, 4)
        self.lab_um = QLabel("", box)
        self.lab_um.setObjectName("pitchAnswerSub")
        self.lab_um.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.grid_answer.addWidget(self.lab_um, 1, 0, 1, 4)
        for i, axis_name in enumerate(("X", "Y")):
            tag = QLabel(axis_name, box)
            tag.setObjectName("pitchAnswerUnit")
            tag.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.grid_answer.addWidget(tag, 2, i * 2)
            self._tags.append(tag)
            bar = Bar(box, width=86)
            self.grid_answer.addWidget(bar, 2, i * 2 + 1)
            self._bars.append(bar)
            self._cells.append([QLabel(box), QLabel(box)])   # 舊介面的殘留（測試讀 rows()）
        self.grid_answer.setColumnStretch(1, 1)
        self.grid_answer.setColumnStretch(3, 1)
        lay.addLayout(self.grid_answer)
        # **把答案帶得走** —— 而且它要**貼著那個答案**。
        # 第一版這顆鈕住在下面的 Units 那一段，於是使用者問「copy 是 copy 誰？」
        # ——  一顆按鈕的意思是它旁邊那個東西，不是它自己的字。
        row_copy = QHBoxLayout()
        row_copy.addStretch(1)
        self.btn_copy = QPushButton("Copy", box)
        self.btn_copy.setProperty("variant", "secondary")
        self.btn_copy.setMaximumWidth(72)
        self.btn_copy.clicked.connect(self.copy_answer)
        row_copy.addWidget(self.btn_copy)
        row_copy.addStretch(1)
        lay.addLayout(row_copy)

        # ---- 哪個方向 -----------------------------------------------------
        lay.addWidget(self._section(box, "Which way it repeats"))
        self.chips_axis = ChoiceChips(AXES, AXIS_ICONS, AXIS_AUTO,
                                      helps=AXIS_HELP, labels=AXIS_LABELS,
                                      parent=box)
        self.chips_axis.changed.connect(self._on_axis)
        lay.addWidget(self.chips_axis)

        # ---- 不對的話自己改 -----------------------------------------------
        lay.addWidget(self._section(box, "Not the cell you want?"))
        fix = QHBoxLayout()
        fix.setSpacing(4)
        self.spin_px = self._period_spin(box, "across")
        self.spin_py = self._period_spin(box, "down")
        fix.addWidget(self.spin_px)
        fix.addWidget(QLabel("×", box))
        fix.addWidget(self.spin_py)
        self.btn_double = QPushButton("×2", box)
        self.btn_double.setToolTip(
            "Double both — for when one cell of yours is two of the repeats it "
            "measured (two MG lines making the unit you compare).")
        self.btn_double.clicked.connect(self._on_double)
        self.btn_reset = QPushButton("Reset", box)
        self.btn_reset.setToolTip("Back to the measured period.")
        self.btn_reset.clicked.connect(self._on_reset)
        for b in (self.btn_double, self.btn_reset):
            b.setProperty("variant", "secondary")
            b.setMaximumWidth(64)
            fix.addWidget(b)
        lay.addLayout(fix)

        # ---- 取錯了怎麼辦：諧波上的其他可能，點一下就套用 -------------------
        self.row_try = QHBoxLayout()
        self.row_try.setSpacing(4)
        self.lab_try = QLabel("Or try", box)
        self.lab_try.setObjectName("paramHint")
        self.row_try.addWidget(self.lab_try)
        self._try_buttons: List[QPushButton] = []
        self.row_try.addStretch(1)
        lay.addLayout(self.row_try)

        # ---- 憑什麼相信它：疊出來的 Golden Cell -----------------------------
        # ⚠ 標題走 `_section`（跟其他三段同一種長相），卡片本身**不帶標題**。
        # 第一版是 `QGroupBox` 自己的標題樣式，於是同一個畫面上有兩種分段長相
        # —— 而「排版很怪」多半就是這種不一致累積出來的。
        lay.addWidget(self._section(box, "Stacked cell — sharp means it is right"))
        lay.addWidget(self._proof_box(box))

        # ---- 單位 ---------------------------------------------------------
        lay.addWidget(self._section(box, "Units"))
        unit = QHBoxLayout()
        self.spin_nm = QDoubleSpinBox(box)
        self.spin_nm.setRange(0.0, 1e6)
        self.spin_nm.setDecimals(3)
        self.spin_nm.setSingleStep(0.1)
        self.spin_nm.setSuffix(" nm/px")
        self.spin_nm.setSpecialValueText("pixel size not known")
        self.spin_nm.setKeyboardTracking(False)   # 同上：打字中途不重算
        self.spin_nm.setToolTip(
            "How many nanometres one pixel is, from the tool's settings. Fill "
            "it in and the pitch also comes out in nanometres.")
        self.spin_nm.valueChanged.connect(lambda _v: self._fill_answer())
        unit.addWidget(self.spin_nm)
        unit.addStretch(1)
        lay.addLayout(unit)

        # ---- 細節：**預設收起來** -------------------------------------------
        # 使用者要得到「每個方法的分數」，但同一輪也說了「不要看一堆文字」。
        # 兩件事只有一種解法：**要查的那天它在，平常不佔畫面。**
        self.btn_details = QPushButton("▸  Details", box)
        self.btn_details.setProperty("variant", "secondary")
        self.btn_details.setCheckable(True)
        self.btn_details.setStyleSheet("text-align:left;")
        self.btn_details.toggled.connect(self._on_details)
        lay.addWidget(self.btn_details)
        self.details = QLabel("", box)
        self.details.setObjectName("paramHint")
        self.details.setTextFormat(Qt.RichText)
        # ⚠ 沒有這一行的話那段說明會被右邊界切掉（"the number ir…"）。
        self.details.setWordWrap(True)
        self.details.setVisible(False)
        lay.addWidget(self.details)
        lay.addStretch(1)
        return box

    def _proof_box(self, parent: QWidget) -> QWidget:
        """**疊起來的那一格** —— 這個視窗最有說服力的一塊。

        使用者 2026-09-21：「仿照 AMAT 的 golden cell，將 period 週期用格線切完
        後，將所有的每個 cell 放在一起，如果取的 period 是完美的，他會有疊加
        Frame 的效果，GC 影像會很漂亮；如果 period 錯，格線切的差，疊起來就會
        糊糊的。」

        ⚠ **旁邊那個數字是 `agreement` 不是 sharpness**，而那個選擇是量出來的
        （F40）：`ghosting_score`（銳利度）只看疊完那一張圖，**看不到疊進去的
        那幾格**，所以分不出「因為對齊了所以銳利」與「因為兩個鬼影各帶一組邊
        所以銳利」—— 相位錯掉的 stack 會拿到**更高**的分數（實測：錯的 76.1
        比正確的 68.4 高），而純雜訊在 σ=60 拿 99.4。`stack_agreement` 問的是
        那幾格**彼此**對得多齊，無量綱、跨影像可比，所以它才是那個可以配門檻
        的數字。**人眼看那張圖 ＋ 這個數字**，兩個一起才完整。
        """
        box = QGroupBox(parent)            # 無標題：標題是上面那一條 `_section`
        lay = QHBoxLayout(box)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10)
        self.cell_view = QLabel(box)
        self.cell_view.setFixedSize(CELL_BOX, CELL_BOX)
        self.cell_view.setAlignment(Qt.AlignCenter)
        # ⚠ 線粗與圓角**吃 token**（`hairline` / `radius_sm`），不寫 1px / 4px
        # —— 同 U12 那條「字級、線粗、圓角只有一個家」（`tests/test_ui_design_
        # tokens.py` 會擋）。螢幕變了要一起改，而「一起」的前提是只有一個地方。
        self.cell_view.setStyleSheet(
            "background:%s;border:%s solid %s;border-radius:%s;color:%s;"
            % (TOKENS["bg_page"], TOKENS["hairline"], TOKENS["border_default"],
               TOKENS["radius_sm"], TOKENS["text_hint"]))
        self.cell_view.setText("—")
        self.cell_view.setToolTip(
            "Every cell the grid cut, averaged on top of each other. Crisp "
            "means they landed on each other, so the period is right. Blurred "
            "or doubled means it is not. Click to see it bigger.")
        self.cell_view.setCursor(Qt.PointingHandCursor)
        self.cell_view.mouseReleaseEvent = lambda _e: self.show_cell_big()
        lay.addWidget(self.cell_view)
        side = QVBoxLayout()
        side.setSpacing(2)
        cap = QLabel("Cells agree", box)
        cap.setObjectName("paramHint")
        side.addWidget(cap)
        self.bar_agree = Bar(box, width=118)
        side.addWidget(self.bar_agree)
        self.lab_stack = QLabel("", box)
        self.lab_stack.setObjectName("paramHint")
        self.lab_stack.setWordWrap(True)
        side.addWidget(self.lab_stack)
        # **大圖中間常常就是缺陷本體，而 mean 會把它抹進 GC。** median 對稀疏
        # 缺陷免疫（`golden.stack_cells` 的 `method`），所以那是一個勾選，
        # 不是一個要去別的地方改的設定。
        self.chk_median = QCheckBox("Ignore defects", box)
        self.chk_median.setToolTip(
            "Stack with the median instead of the mean. A defect sitting in "
            "one cell then does not smear into the stacked picture.")
        self.chk_median.toggled.connect(lambda _on: self.remeasure(reuse=True))
        side.addWidget(self.chk_median)
        # 邊界那一圈：**量出來的**（帶掃描邊緣效應的合成圖 0.872 → 0.980，
        # 乾淨影像 0.980 → 0.980），而使用者也說「不太想放」。所以預設打開。
        self.chk_edges = QCheckBox("Skip edge cells", box)
        self.chk_edges.setChecked(True)
        self.chk_edges.setToolTip(
            "Leave out the ring of cells touching the image border. The scan "
            "edge is often brighter, darker or noisier than the rest, and "
            "those cells drag the stacked picture down. Costs nothing on a "
            "clean image.")
        self.chk_edges.toggled.connect(lambda _on: self.remeasure(reuse=True))
        side.addWidget(self.chk_edges)
        side.addStretch(1)
        lay.addLayout(side, 1)
        return box

    def _period_spin(self, box: QWidget, axis: str) -> QDoubleSpinBox:
        """一格「我自己來」的週期。**0 ＝ 沒打，用量到的那個。**

        ⚠ 小數要收得下（`setDecimals(1)`）：F105 之後週期可以是 79.5，而
        79.5 對 79 在 4000 px 上差 25 px。
        """
        sp = QDoubleSpinBox(box)
        sp.setRange(0.0, 8192.0)
        sp.setDecimals(1)
        sp.setSingleStep(1.0)
        # ⚠ 84 的時候 ``specialValueText`` 被切成 "easured" —— 一個**看起來像
        # 壞掉**的畫面，而它其實只是少了 14 px。
        sp.setMinimumWidth(104)
        sp.setSpecialValueText("measured")
        # ⚠ **打字的中途不算。** 預設 Qt 每敲一個鍵就發 `valueChanged`，於是
        # 要打 45 的人會先看到整個視窗用 4 重算一次（使用者 2026-09-21：
        # 「我要輸入 45，但當我輸入到 4，就會強制 trigger 算 4」）—— 一次
        # 疊格子是幾百毫秒，中途那一次是純粹的浪費，而且畫面會閃一個錯的答案。
        # 關掉之後只有 **Enter／離開焦點／按上下鍵** 才算。
        sp.setKeyboardTracking(False)
        sp.setToolTip(
            "Type the cell size %s if the measured one is not the unit you "
            "want — the grid and the stacked cell redraw so you can see "
            "whether yours is right." % axis)
        sp.valueChanged.connect(lambda _v: self._on_override())
        return sp

    # -- 進來的圖 -----------------------------------------------------------
    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open an image of the repeating layout", "",
            "Images (*.tif *.tiff *.png *.jpg *.jpeg *.bmp);;All files (*)")
        if path:
            self._load_path(str(path))

    def _load_path(self, path: str) -> None:
        from d4t.core.ingest import imageio as ingest_imageio
        try:
            arr = ingest_imageio.load_gray(path)
        except Exception as e:
            self._say("Could not open that image: %s" % e)
            return
        self.set_image(arr, os.path.basename(path), ask_crop=True)

    def paste_image(self) -> None:
        cb = QGuiApplication.clipboard()
        arr = _qimage_to_gray(cb.image() if cb is not None else None)
        if arr is None:
            self._say("There is no image on the clipboard.")
            return
        self.set_image(arr, "pasted image", ask_crop=True)

    def set_image(self, arr: Any, name: str = "", ask_crop: bool = False) -> None:
        """換一張圖：清掉上一次的答案，量一次新的。

        ⚠ **舊答案要先清掉**再開始量。留著的話，新圖載進來的那幾秒畫面上寫的
        是上一張圖的 pitch，而那是這個視窗唯一的輸出。
        """
        a = np.asarray(arr)
        if a.ndim < 2 or a.size == 0:
            self._say("That is not an image.")
            return
        self._full = to_uint8(a)
        self._crop = None
        self._name = str(name or "")
        self._m = self._gc = None
        self._apply_crop()
        if ask_crop and not self.ask_crop():
            self.remeasure()

    def ask_crop(self) -> bool:
        """問「只看這一塊」。回 True 表示它已經自己重量過了。

        用的是 `crop_dialog.CropDialog` **本人** —— 「框怎麼變成像素」只能有
        一個家（見 `crop_array` 的說明）。
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
        self._m = self._gc = None
        h, w = self._work.shape[:2]
        bits = ["%s%d × %d px" % ((self._name + " · ") if self._name else "", w, h)]
        crop = describe_crop(self._crop)
        if crop:
            bits.append(crop)
        self.lab_source.setText(" · ".join(bits))
        self.view.set_image(self._work)

    # -- 量 -----------------------------------------------------------------
    def remeasure(self, reuse: bool = False) -> None:
        """量一次。``reuse=True`` 只重疊（軸向或週期改了，影像沒變）。"""
        if self._work is None or self._worker is not None:
            return
        self._worker = _PitchWorker(self._work, self.axis(),
                                    self._m if reuse else None,
                                    self.override(), self.stack_method(),
                                    self.skip_edges(), self)
        self._worker.stage.connect(self._say)
        self._worker.done.connect(self._on_done)
        self._worker.finished.connect(self._on_finished)
        self.progress.setVisible(True)
        self._busy(True)
        self._worker.start()

    def _on_done(self, m: Any, gc: Any, err: str) -> None:
        if err:
            self._say(err)
            return
        if m is None:
            return
        self._m, self._gc = m, gc
        self._refresh()
        self.measured.emit(m, gc)

    def _on_finished(self) -> None:
        self._worker = None
        self.progress.setVisible(False)
        self._busy(False)

    def _busy(self, on: bool) -> None:
        for w in (self.btn_open, self.btn_paste, self.btn_crop, self.chips_axis,
                  self.spin_px, self.spin_py, self.btn_double, self.btn_reset,
                  self.chk_median, self.chk_edges):
            w.setEnabled(not on)
        for b in self._try_buttons:
            b.setEnabled(not on)

    def _on_axis(self, _value: str) -> None:
        """軸向改了 —— **週期不重量**，但格線與疊圖都要重來。

        ⚠ **格線要當場重畫，不能等 worker 回來。** 第一版沒有這一行，症狀是
        按下「X only」之後表格立刻寫 `not used`，而圖上的**橫線還在**，一等
        好幾秒 —— 畫面同時在說兩件相反的事，而使用者會相信圖。
        """
        if self._m is None:
            return
        self._refresh()
        self.remeasure(reuse=True)

    def _on_override(self) -> None:
        """使用者自己打了一個週期 —— 同 `_on_axis`：**當場重畫，不等疊圖**。"""
        if self._m is None:
            self._fill_answer()
            return
        self._refresh()
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

    # -- 畫面 ---------------------------------------------------------------
    def axis(self) -> str:
        return self.chips_axis.text() or AXIS_AUTO

    def nm_per_px(self) -> float:
        return float(self.spin_nm.value())

    def skip_edges(self) -> bool:
        return bool(self.chk_edges.isChecked())

    def stack_method(self) -> str:
        """``"median"`` ＝ 忽略缺陷（`golden.stack_cells` 的那個參數）。"""
        return "median" if self.chk_median.isChecked() else "mean"

    def override(self) -> Override:
        """使用者自己打的那一組（``None`` ＝ 那一軸用量到的）。"""
        px, py = float(self.spin_px.value()), float(self.spin_py.value())
        return (px if px >= MIN_PERIOD_PX else None,
                py if py >= MIN_PERIOD_PX else None)

    def _flags(self) -> Tuple[bool, bool]:
        """哪幾軸算數 —— **答案、格線、疊圖三個地方問的是同一支**。

        各自算一次的話，畫面上會出現「答案說 Y 沒在用、格線卻切了橫線」——
        這個視窗已經被那種形狀咬過兩次（`_on_axis` 與 `_draw` 的回歸測試）。
        """
        if self._m is None:
            return (False, False)
        ov = self.override()
        ex, ey = effective_period(self._m, ov)
        return axis_flags(self.axis(), ex, ey,
                          100.0 if ov[0] else self._m.conf_x,
                          100.0 if ov[1] else self._m.conf_y)

    def typed_conf(self) -> Override:
        """使用者打進去的那一組週期，**在這張圖上**拿幾分。

        ⚠ 量的是 `self._work`（裁過、正在看的那一張），不是原圖 —— 畫面上
        那些格線切的就是它，分數跟它們講的必須是同一件事。
        每一軸沒打就是 ``None``（沒有分數要算），不是 0。

        便宜得可以每次 refresh 都算：一條投影 ＋ 一次自相關，不是一次疊格子。
        """
        ox, oy = self.override()
        work = self._work
        if work is None or not np.asarray(work).size:
            return (None, None)
        return (algo_period.confidence_at(work, float(ox), "x") if ox else None,
                algo_period.confidence_at(work, float(oy), "y") if oy else None)

    def rows(self) -> List[Tuple[str, str, str, str]]:
        """畫面上那兩列（測試讀這個，不必去挖 QLabel）。"""
        if self._m is None:
            return [(lab, PITCH_UNSET, "", PITCH_UNSET)
                    for lab in ("Across (X)", "Down (Y)")]
        return pitch_rows(self._m, self.axis(), self.nm_per_px(),
                          self.override(), self.typed_conf())

    def _refresh(self) -> None:
        """一次把畫面對齊到目前的狀態 —— **只有這一支**（少呼叫一半就是說謊）。"""
        self._fill_answer()
        self._draw()
        self._fill_stack()
        self._fill_try()
        self._fill_details()
        self._fill_warning()

    def _fill_answer(self) -> None:
        """答案那兩列。**沒在用的那一軸整列不顯示**（使用者 2026-09-21 定的）。

        ⚠ 這一條**推翻了第一版的決定**，而理由是使用者的：第一版寫 `not used`，
        想法是「藏起來他會以為量不到」。但**選 X only 的人是自己按的那顆鈕**
        —— 他知道 Y 還在，那一列對他只是噪音。原本的顧慮只在 Auto 自己丟掉
        一軸時才成立，而那一種 Auto 本來就不會把它列出來（`flags` 是 False），
        所以改由**警告條**去講（「這一軸信心不足」），不是留一列半殘的資料。
        """
        rows = self.rows()
        ov = self.override()
        flags = self._flags()
        tc = self.typed_conf()
        confs = (float(getattr(self._m, "conf_x", 0.0) or 0.0) if self._m else 0.0,
                 float(getattr(self._m, "conf_y", 0.0) or 0.0) if self._m else 0.0)
        used = [i for i in range(2) if (flags[i] if self._m is not None else True)]
        self.lab_big.setText(
            " × ".join(rows[i][1] for i in used) + " px" if used and
            rows[used[0]][1] != PITCH_UNSET else PITCH_UNSET)
        ums = [rows[i][2] for i in used if rows[i][2]]
        self.lab_um.setText(" × ".join(ums).replace(" µm ×", " ×") if ums else "")
        # **按鈕自己講它會複製什麼** —— 「copy 是 copy 誰？」的另一半答案。
        what = self.answer_text()
        # **沒有答案的時候那顆鈕是灰的。** 一顆按下去只會說「還沒量到東西」
        # 的按鈕，在畫面上是一個問題，不是一個功能。
        self.btn_copy.setEnabled(bool(what))
        self.btn_copy.setToolTip(
            ("Copy “%s” to the clipboard." % what) if what
            else "Nothing measured yet.")
        for i, (bar, tag) in enumerate(zip(self._bars, self._tags)):
            show = flags[i] if self._m is not None else True
            for w in (tag, bar):
                w.setVisible(show)
            if not show:
                continue
            if self._m is None:
                bar.set_value(0.0, TONE_WARN, "")
            elif ov[i] and tc[i] is None:
                # 打進去了，但這張圖打不出分數（還沒載圖／lag 大過半張圖）。
                bar.set_text_only(CONF_TYPED)
            else:
                # 打進去的那一軸看的是**它自己的**分數（`confidence_at`），
                # 不是量出來那個數字的分數 —— 兩個同尺度，可以直接比。
                c = float(tc[i]) if ov[i] else confs[i]
                bar.set_value(c / 100.0, conf_tone(c), "%.0f" % c)

    def _fill_try(self) -> None:
        """候選那一排 —— **點一下就套用**（見 `candidate_periods` 的說明）。"""
        for b in self._try_buttons:
            self.row_try.removeWidget(b)
            # ⚠ `removeWidget` **不會讓它從畫面上消失** —— 它只是不再由
            # layout 擺位，於是它留在父視窗上最後一次被擺的地方，而
            # `deleteLater` 要等事件迴圈才真的刪。實拍到的樣子是一顆舊的
            # 「60 × 22」候選鈕**疊在最大的那個答案上**。`setParent(None)`
            # 才是「現在就不要再畫它」。
            b.setParent(None)
            b.deleteLater()
        self._try_buttons = []
        flags = self._flags()
        cands = (candidate_periods(self._m, flags,
                                   effective_period(self._m, self.override()))
                 if self._m is not None else [])
        self.lab_try.setVisible(bool(cands))
        for px, py in cands:
            b = QPushButton(candidate_label(px, py, flags), self.lab_try.parentWidget())
            b.setProperty("variant", "secondary")
            # 一排四顆要塞進 380 px：留白收掉，字才不會被切成 "L20 × 44"。
            b.setStyleSheet("padding-left:6px;padding-right:6px;")
            b.setToolTip(
                "Try this instead — it is one of the harmonics of what was "
                "measured, and a wrong period is almost always one of these. "
                "The grid and the stacked cell redraw so you can compare.")
            b.clicked.connect(lambda _c=False, a=px, bb=py: self._set_override(a, bb))
            self.row_try.insertWidget(self.row_try.count() - 1, b)
            self._try_buttons.append(b)

    def _fill_details(self) -> None:
        """三票各自的答案（折在 ``▸ Details`` 後面）。"""
        if self._m is None:
            self.details.setText("")
            return
        rows = detail_rows(self._m, self._flags())
        cells = "".join(
            "<tr><td style='padding-right:12px'>%s</td>"
            "<td style='padding-right:12px'>%s</td><td>%s</td></tr>"
            % r for r in rows)
        self.details.setText(
            "<table><tr><td></td><td><b>X</b></td><td><b>Y</b></td></tr>%s</table>"
            "<br>Each row is one of the three ways it looks for a repeat; the "
            "number in brackets is that method's own confidence. They are "
            "allowed to disagree — that is a fact about the layout, not a "
            "fault." % cells)

    def _on_details(self, on: bool) -> None:
        self.btn_details.setText(("▾  Details" if on else "▸  Details"))
        self.details.setVisible(bool(on))

    def show_cell_big(self) -> None:
        """疊出來那一格點一下 → 放大看。

        150 px 對細 pattern 不夠判斷糊不糊，而**看得出糊不糊是它存在的唯一
        理由**。走 `lattice_dialog` 用的那個 `ImageView`（滾輪縮放、拖曳平移）。
        """
        cell = getattr(self._gc, "cell", None) if self._gc is not None else None
        if cell is None or np.asarray(cell).size == 0:
            return
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Stacked cell")
        fit_screen.fit(dlg, 620, 620)
        lay = QVBoxLayout(dlg)
        view = ImageView(dlg)
        view.set_image(np.asarray(cell))
        lay.addWidget(view, 1)
        hint = QLabel("Crisp edges mean the cells landed on each other. "
                      "Blurred or doubled means the period is off. "
                      "Wheel zooms, drag pans.", dlg)
        hint.setObjectName("paramHint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Close, Qt.Horizontal, dlg)
        bb.rejected.connect(dlg.reject)
        bb.clicked.connect(lambda _b: dlg.reject())
        lay.addWidget(bb)
        apply_button_cursors(dlg)
        dlg.exec()

    def answer_text(self) -> str:
        """Copy 出去的那一段字（測試讀這個）。"""
        rows = self.rows()
        flags = self._flags()
        bits = []
        for i, name in enumerate(("X", "Y")):
            if not flags[i]:
                continue
            piece = "%s %s px" % (name, rows[i][1])
            if rows[i][2]:
                piece += " (%s)" % rows[i][2]
            bits.append(piece)
        return "  ".join(bits)

    def copy_answer(self) -> None:
        text = self.answer_text()
        if not text:
            self._say("Nothing measured yet.")
            return
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(text)
        self._say("Copied: %s" % text)

    def _fill_stack(self) -> None:
        """疊出來那一格 ＋ 一致性 —— 這是「憑什麼相信它」那一塊。"""
        gc = self._gc
        cell = getattr(gc, "cell", None) if gc is not None else None
        if cell is None or np.asarray(cell).size == 0:
            self.cell_view.setPixmap(QPixmap())
            self.cell_view.setText("—")
            # ⚠ **還沒疊過的時候不畫那條軌道**（`set_text_only`）。
            # 這一行本來是 `set_value(0.0, …)`，而自從 0 分改成畫一顆點之後，
            # 「沒有東西可疊」就跟「疊了，而它们完全對不起來」畫成同一個樣子 ——
            # 而那正是那個改動要消掉的歧義。
            self.bar_agree.set_text_only("")
            self.lab_stack.setText("")
            return
        self.cell_view.setPixmap(_pixmap(np.asarray(cell), CELL_BOX))
        agree = float(getattr(gc, "agreement", 0.0) or 0.0)
        self.bar_agree.set_value(agree, agree_tone(agree), "%.2f" % agree)
        n = int(getattr(gc, "n_cells", 0) or 0)
        tone = agree_tone(agree)
        # ⚠ **一句話，不是三句。** 第一版是「144 cells. Edge cells left out.
        # The cells landed on each other — this period is right.」—— 而那個
        # 結論旁邊就是一條綠色的長條寫著 0.98，字只是在重複顏色已經講完的事。
        # 使用者 2026-09-21：「UI 內字太多」。長的那一段留在 tooltip 裡。
        if tone == TONE_GOOD:
            word = "landed on each other."
        elif tone == TONE_WARN:
            word = "look blurred? try ×2."
        else:
            word = "did not agree — this period is wrong."
        edge = ", edges left out" if getattr(gc, "trimmed", False) else ""
        self.lab_stack.setText("%d cells%s — %s" % (n, edge, word))

    def _fill_warning(self) -> None:
        """⚠ **只在有事的時候出現。** 第一版有一塊常駐的「What it decided」，
        而最常見的情形是它空著 —— 使用者 2026-09-21：「這我不知道可以幹嘛？」
        一塊永遠在那裡、內容通常是空的面板，教會使用者不要看它。"""
        lines: List[str] = []
        if self._m is not None:
            nothing = self._flags() == (False, False)
            if nothing:
                # ⚠ **一句話講一次。** 引擎的 note 裡已經有一句
                # "no periodic structure detected"，而它是寫給開發者看的
                # （F118：使用者面的字不准講開發者的話）。兩句並排出現的時候
                # 使用者會去找「它們是不是在講兩件事」—— 而那是找不到答案的。
                lines.append("No repeating period could be measured in this "
                             "image. Try Crop… to leave out anything that is "
                             "not the repeating layout.")
            else:
                lines.extend(getattr(self._m, "notes", None) or [])
            note = ""
            if self._gc is not None and not nothing and self._work is not None:
                ex, ey = effective_period(self._m, self.override())
                note = trust_note(cells_along(self._work.shape[:2], ex, ey,
                                              self._flags()))
            if note:
                lines.append(note)
            ox, oy = self.override()
            if ox or oy:
                got = ", ".join(
                    "%s: yours %s vs measured %s"
                    % (name, algo_period2d.fmt_px(typed),
                       algo_period2d.fmt_px(m) if m >= MIN_PERIOD_PX else "none")
                    for name, typed, m in (
                        ("X", ox, float(self._m.px or 0)),
                        ("Y", oy, float(self._m.py or 0))) if typed)
                lines.append("Not the measured size — %s. “Reset” puts it back."
                             % got)
        text = "  ·  ".join(str(s) for s in lines if str(s).strip())
        self.warn.setText(("⚠  " + text) if text else "")
        self.warn.setVisible(bool(text))

    def _draw(self) -> None:
        """格線鋪回原圖 —— **`lattice_boxes` 本人**，不自己再算一次格子。"""
        if self._work is None or self._m is None or not self.chk_grid.isChecked():
            self.view.set_overlay(None)
            self.caption.setText("")
            return
        flags = self._flags()
        if not flags[0] and not flags[1]:
            self.view.set_overlay(None)
            self.caption.setText("No period to draw.")
            return
        shape = self._work.shape[:2]
        # ⚠ 畫的是**真的在用的那一組**，不是量到的那一組 —— 少了這一行，
        # 使用者打了 120、答案寫 120，而格線還是照 60 畫。
        ex, ey = effective_period(self._m, self.override())
        ux, uy = lattice_periods(shape, ex, ey, flags)
        origin = tuple(getattr(self._gc, "origin", None) or (0.0, 0.0))
        boxes, total = lattice_boxes(shape, ux, uy, origin, flags)
        # ⚠ **畫的格子要跟疊進去的那些是同一批。** 少了這一段，邊界那一圈明明
        # 沒有被疊進去，畫面上卻還框著它 —— 而使用者盯著的正是那張圖。
        # 這是這一輪第三次踩到同一種形狀（`_on_axis`、`_draw` 的週期、這裡），
        # 病根都是「同一件事在畫面上有兩個算法」。
        if getattr(self._gc, "trimmed", False):
            box = trim_to_inner(shape, ux, uy, origin, flags)
            if box is not None:
                h, w = shape
                x0, y0, x1, y1 = (box[0] / w, box[1] / h, box[2] / w, box[3] / h)
                boxes = [b for b in boxes
                         if b[0] >= x0 - 1e-6 and b[1] >= y0 - 1e-6
                         and b[0] + b[2] <= x1 + 1e-6 and b[1] + b[3] <= y1 + 1e-6]
                total = len(boxes)
        self.view.set_overlay(boxes)
        text = "%s px · %d cells" % (algo_template.period_text(ux, uy), total)
        if len(boxes) < total:
            text += " (%d drawn)" % len(boxes)
        self.caption.setText(text)

    def _say(self, text: str) -> None:
        self.statusBar().showMessage(str(text), 8000)

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
        path = urls[0].toLocalFile() if urls else ""
        if not path:
            return
        e.acceptProposedAction()
        self._load_path(str(path))

    def closeEvent(self, e) -> None:  # Qt hook
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(3000)
        super().closeEvent(e)


def _pixmap(arr: np.ndarray, box: int) -> QPixmap:
    """uint8 2D → 放大到 ``box`` 見方的 QPixmap（保持長寬比）。

    ⚠ **放大用 nearest-neighbour**：一格常常只有 40–80 px，而使用者要判斷的
    正是「邊緣是清楚的還是糊的」。平滑取樣會把答案本身抹掉。
    """
    a = np.ascontiguousarray(to_uint8(arr))
    h, w = a.shape[:2]
    img = QImage(a.data, w, h, w, QImage.Format_Grayscale8).copy()
    return QPixmap.fromImage(img).scaled(box, box, Qt.KeepAspectRatio,
                                         Qt.FastTransformation)


def _qimage_to_gray(img: Optional[QImage]) -> Optional[np.ndarray]:
    """剪貼簿的 QImage → uint8 灰階 2D。空的或壞的回 ``None``。

    ⚠ **一定要先轉成 ``Format_Grayscale8``**：截圖多半是 ARGB32，它的 `bits()`
    是 BGRA 四個 byte 一組，直接 reshape 會拿到「寬度四倍、內容是交錯通道」的
    東西 —— 而那**看起來仍然像一張圖**（條紋狀），只是每一個數字都不對。
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
    # 這條路是**獨立**的入口（`python -m d4t pitch`），所以整個 app 的圖示
    # 就是 helper 的，不是 Studio 的。
    app.setWindowIcon(branding.pitch_icon())
    win = PitchHelperWindow()
    win.show()
    return int(app.exec())

"""`pitch helper` **不碰 widget 的那一半** —— 常數、判準、數字 → 字。

為什麼分家
----------
兩個理由，而第二個比較重要：

1. `pitch_helper.py` 長到 2,199 行，而一般上限是 2,200（`tests/
   test_size_ceilings.py`）。下一筆修改不管多小都會撞上去。
2. ⚠ **這一半是獨立出去的那個 app 要帶走的東西**（使用者 2026-09-22：
   「我之後會把這個應用獨立出來」，拆解清單在
   `docs/plans/F120-pitch-helper.md` §28）。它不 import Qt，所以它的測試
   也不必開視窗 —— 軸向 × 單位 × 量不量得到的排列組合各斷言一次，
   **不必為了讀一行字開一次視窗**。

⚠ **`pitch_helper` 會把這裡的每一個名字轉出去**（`from .pitch_core import …`）。
既有的 `ph.axis_flags` / `ph.PITCH_UNSET` 一個都沒有換家 —— 搬家不該連名字一起
換，那會把一次版面調整變成一次全域改名。

⚠ **這裡不准 import `d4t.ui` 底下任何會拉 Qt 的東西。** `tests/test_no_qt.py`
守著核心批要在沒有 Qt 的機器上綠，而這一支的價值有一半就是那件事。
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from pitchapp.core.algo import period2d as algo_period2d
from pitchapp.core.algo import template as algo_template
from pitchapp.core.algo.golden import BLURRED_BELOW

__all__ = [
    "AXES", "AXIS_X", "AXIS_Y", "AXIS_BOTH", "AXIS_ICONS", "AXIS_LABELS",
    "AXIS_HELP", "MIN_PERIOD_PX", "GRID_HEX", "NEXT_STEP", "PITCH_UNSET",
    "PITCH_NOT_USED", "WINDOW_TITLE", "PHASE_PENDING",
    "VERDICT_OK", "VERDICT_BLURRED", "VERDICT_NONE", "VERDICT_TYPED",
    "VERDICT_CHECK", "VERDICT_BUSY_PERIOD", "VERDICT_BUSY_STACK",
    "CONF_TYPED", "TONE_GOOD", "TONE_WARN", "TONE_BAD", "CONF_GOOD_FROM",
    "AGREE_GOOD_FROM", "BLURRED_BELOW", "MIN_CELLS_TO_TRUST", "Override",
    "MIN_CELLS_AFTER_TRIM", "MAX_CANDIDATES",
    "axis_flags", "lattice_periods", "px_text", "nm_text", "cells_along",
    "trust_note", "candidate_periods", "candidate_label", "detail_rows",
    "trim_to_inner", "effective_period", "pitch_rows", "conf_tone",
    "agree_tone",
]

# --------------------------------------------------------------------------- #
# 軸向：使用者說了算（F120，使用者 2026-09-21「也能支援純 X 純 Y」）
# --------------------------------------------------------------------------- #
AXIS_X = "x"
AXIS_Y = "y"
AXIS_BOTH = "both"

#: 三選一，順序就是畫面上膠囊的順序。**預設是兩軸都切。**
#:
#: ⚠ **這裡本來有第四顆 `Auto`，2026-09-21 使用者拿掉了**（「我覺得就分 X+Y
#: 跟 X 跟 Y 就好」）。它上一輪才剛因為「Auto 跟 X+Y 差在哪裡？」被改名成
#: `Force both` —— 而一個要靠改名才講得清楚的差別，多半是那個差別不該存在。
#:
#: ⚠ **而那個差別實測上根本不存在。** Auto 做的唯一一件事是把信心
#: < `MIN_PERIOD_CONFIDENCE`（40）的軸丟掉，但 `estimate_period` 自己的
#: `strength_threshold`（0.18 ≈ 信心 18）在那之前就已經回 `px=None` 了。
#: 實測掃過訊號強度（900×700、σ=30 的雜訊上疊一條週期 60 的線）：
#:
#:   振幅 1 → px=0（引擎自己就擋了）  ·  振幅 2 → px=60、信心 41.3
#:
#: **中間沒有東西。** 那兩道門之間的 18–40 那一段，在這些圖上是空的 ——
#: 所以 Auto 從來沒有丟掉過任何東西，它只是一顆看不出跟隔壁差在哪的鈕。
#: 萬一真的有圖落在那一段，現在的處置是**講出來而不是默默丟掉**
#: （見 `_fill_warning` 的低信心那一句）—— 那比較誠實：使用者看得到那個數字
#: 跟它的紅色長條，而不是一片空白。
AXES = (AXIS_BOTH, AXIS_X, AXIS_Y)
AXIS_ICONS = ("place_crossing", "axis_x", "axis_y")
#: ⚠ ``Force both`` 改回 ``X + Y``：``Force`` 那個字是上一輪拿來講
#: 「跟 Auto 差在哪」的，而 Auto 已經不在了 —— 沒有對照組的時候，
#: ``Force`` 只是一個多出來的字。
AXIS_LABELS = {
    AXIS_X: "X only",
    AXIS_Y: "Y only",
    AXIS_BOTH: "X + Y",
}
#: ⚠ 每一句只留**「什麼時候按它」**。第一版四句話加起來 60 個字掛在四顆膠囊
#: 底下，而使用者同一輪說了「UI 內字太多」——  說明的長度跟它被讀到的機率成
#: 反比。
AXIS_HELP = {
    AXIS_X: "It only repeats across. One cell is the full height.",
    AXIS_Y: "It only repeats down. One cell is the full width.",
    AXIS_BOTH: "It repeats both ways. One cell is a tile.",
}

#: 一軸要至少這麼多像素才算得上一個週期（同 `build_golden_cell` 的判準）。
MIN_PERIOD_PX = 2.0

#: 格線的顏色（亮芯；襯底在 `image_view._CASING`）。
GRID_HEX = "#00e5ff"

#: 拿到答案之後**下一步去哪**（只在有答案時出現）。
#:
#: ⚠ **名字要是真的那個名字，而我第一版寫錯了。** 我原本寫 "Cell size" ——
#: 那四個字只活在 `template_dialog` 的**檔頭註解**裡，畫面上那兩格的標籤是
#: `Cell W` / `Cell H`。一句指路的話寫了一個找不到的名字，比不寫還糟：使用者
#: 會去找一個不存在的東西，然後開始懷疑其他每一句。
#: `tests/test_ui_pitch_helper.py::test_the_next_step_names_something_that_exists`
#: 從 `template_dialog` 的原始碼反查，所以那邊改名這裡就會紅。
NEXT_STEP = "Copy it into your tool's cell size fields."

#: 還沒有答案的那一格寫什麼。**一個破折號，不是 0** —— 0 在那一格看起來像一個
#: 量出來的答案（同 `gc_generator.PERIOD_UNSET`，F117 G5 定的）。
PITCH_UNSET = "—"

#: 這個視窗叫什麼。**只有它自己的名字**，不掛主程式 —— 見 `__init__` 的說明。
WINDOW_TITLE = "Pitch helper"

#: **答案已經上去了，證據還在跑**時圖底下那一行寫什麼（F120 第十七輪）。
#: 這一刻格線是**不畫**的：格子的位置要等相位搜尋回來才知道，先畫在相位 0 上
#: 再跳掉是最糟的一種。所以那一行的工作是說「還在找位置」，不是留白 ——
#: 留白會讓使用者以為格線壞了。
PHASE_PENDING = "Finding where the cells start…"

#: 右欄最上面那一行的狀態（F120 第十七輪，使用者：「要有個標題或一個東西在
#: 右側最上面」）。**左邊是名字，右邊是這一行** —— 兩件事擠在同一排是量出來
#: 的：疊成兩行要 682 px，而 1366×768 的筆電上右欄只有約 700，再碰上廠內常見
#: 的 125% 縮放就會被切。
#:
#: ⚠ **句子要短到跟名字排得下**：411 px 扣掉圖示與名字剩約 290，而
#: 「The cells do not agree — try another period」要 300。「然後怎麼辦」不在
#: 這裡講 —— 它本來就在證據卡的說明行與底下那條警告裡，**不要講第二次**。
VERDICT_BUSY_PERIOD = "Measuring the period…"
VERDICT_BUSY_STACK = "Stacking the cells…"
VERDICT_OK = "Cells stack cleanly"
VERDICT_BLURRED = "Cells do not agree"
VERDICT_NONE = "No period found"
VERDICT_TYPED = "Using your period"
#: 有話要說（引擎的 note、低信心、格數太少…）但疊得起來時寫什麼。
#: ⚠ **這一格存在的理由**：一個**錯的**週期（真正週期的一半）每一格都是半個
#: cell，彼此照樣對得很齊 —— `Cells agree` 會很高。那一刻給一個綠勾等於替一
#: 個可能錯的答案背書。所以判準是「**沒有任何警告**」而不是「分數夠高」，而
#: 那個判準直接讀 `_fill_warning` 算出來的那一份，**不另外算第二份**。
VERDICT_CHECK = "Measured — worth a check"

#: 這一軸被使用者的選擇排除掉時寫什麼。**不是空白、不是消失** —— 那一軸的數字
#: 其實量到了，藏起來的話使用者會以為它量不到，然後回頭去查一個不存在的問題。
PITCH_NOT_USED = "not used"

def axis_flags(axis: str, px: float, py: float,
               conf_x: float = 100.0, conf_y: float = 100.0
               ) -> Tuple[bool, bool]:
    """``(用不用 X, 用不用 Y)`` —— **使用者選的那一顆說了算**。

    三顆膠囊（X + Y／X only／Y only）**都跳過信心那一關**：使用者明講的
    一律相信，同 `build_golden_cell` 的 ``given`` 規則。但它變不出一個沒有量到
    的數字 —— ``p < 2`` 仍然是沒有（而純雜訊實測就是 ``px=0``，因為
    `estimate_period` 自己的 ``strength_threshold`` 在那之前就擋下來了）。

    ``conf_x``／``conf_y`` 留著是為了呼叫端的簽名不要跟著 `AXES` 變 ——
    這一支不再看它們（見 :data:`AXES` 的說明：使用者 2026-09-21 拿掉了
    `Auto`，而那是唯一看信心的那一顆）。低信心現在是**警告**，不是否決權。

    不認得的軸向當成 ``X + Y``（預設那一顆）。
    """
    has_x = float(px or 0.0) >= MIN_PERIOD_PX
    has_y = float(py or 0.0) >= MIN_PERIOD_PX
    a = str(axis or AXIS_BOTH)
    if a == AXIS_X:
        return (has_x, False)
    if a == AXIS_Y:
        return (False, has_y)
    return (has_x, has_y)

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

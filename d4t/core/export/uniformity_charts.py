# -*- coding: utf-8 -*-
# d4t uniformity charts — authored 2026-09-07 (F85).
"""這一群框的四種看法 → 四張圖（**手寫 SVG，零新相依**）。

PEAR 的 Analysis 視窗有四種圖，而它們回答的是四句不同的話：

==============  ==========  ==========  ==================================
值              X 軸        一個點      回答
==============  ==========  ==========  ==================================
``box``         區域        一格框      這幾群各自散多開
``histogram``   灰階值      一格框      值怎麼散開、有沒有兩座山
``profile``     框中心 X/Y  一格框      **有沒有斜掉**
``map``         框的 (x,y)  一格框      不均勻在**哪裡**
==============  ==========  ==========  ==================================

四種都是「**一格框一個點**」—— 一致，所以切換的時候使用者不必重新學「現在
一個點是什麼」。

⚠ **這跟 `export/boxplot.py` 那張盒鬚圖不是同一個東西。**
那一張是「一個盒子＝判定樹的一片葉子，一個點＝一顆 defect」（整批的圖）；
這裡是「一個盒子＝一個區域，一個點＝一格框」（一張圖之內的圖）。兩者在畫面上
長得一模一樣，而「一個點是什麼」是唯一的差別 —— 那正是最容易在半年後被誰
順手合併的形狀。合併的下場是一張畫得出來、看起來正常、而意思是錯的圖。

**``box`` 那一種直接用 `boxplot.build_boxplot_svg`**（同一支函式、同一組
Tukey 鬚）—— 它吃的正好是 ``{name, values, colour}``，而盒鬚圖的幾何跟
「一個點是什麼」無關。同一種圖畫兩份的那天，兩張圖的鬚會不一樣長。

為什麼是 SVG 不是繪圖套件
-------------------------
`export/boxplot.py` 的檔頭寫過一次，這裡逐字適用：公司機是用複製檔案更新的，
多一個套件就是多一件在受限機器上會裝不起來的事。

為什麼顏色是參數
----------------
`core` 不得 import Qt（鐵則 1），所以主題查不到。呼叫端給 —— 跟 `boxplot`
與 `decide_tree.verdict_rows` 同一個理由。:data:`REGION_COLOURS` 是沒有 UI 的
呼叫端（CLI、Output 卡）的退路。

⚠ 它**不再是 `ui.theme.REGION_COLORS` 的副本**（F88 第一刀 b，2026-09-07）——
是同一組色相在**另一個底上的另一階**。理由見那一份的說明；守著它不漂的是
`tests/test_export_uniformity.py`（守的是**色相與順序**，不是逐字相同）。
"""
from __future__ import annotations
from d4t.core.log import swallowed

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# 這四支是 SVG 的共用零件，**唯一出處在 `boxplot.py`**。從那裡 import 而不是
# 抄一份：刻度算法漂掉的那天，同一份報表上兩張圖的軸會對不起來。
# （第三個消費者出現的時候，該做的是把它們搬進 `export/svg.py`，不是再抄一份。）
from .boxplot import (  # 見上
    TITLE_WEIGHT, TITLE_X, _esc, _fmt, _nice_ticks, build_boxplot_svg,
)

__all__ = [
    "resolve_style", "SEQ_RAMP", "seq_hex",
    "CHARTS", "CHART_LABELS", "REGION_COLOURS", "AXES", "UNIF_COLUMNS",
    "summary_columns",
    "chart_series", "build_chart_svg", "build_charts_page",
    "summary_rows", "build_index_page",
]

#: 四種圖的值（recipe / 參數用的 id，不要改）。
CHART_BOX, CHART_HIST = "box", "histogram"
CHART_PROFILE, CHART_MAP = "profile", "map"
#: **使用者自己配的那一張** —— 第一張由 spec 決定長相的圖（`chart_spec` ＋
#: `chart_draw`，F88 第二刀開的、第三刀改名）。其餘四張在第四刀會變成同一個
#: 引擎的預設組合。
#:
#: ⚠ 它一開始叫 `scatter`，而第三刀加了 `line` / `bar` 兩種記號之後那個名字
#: 就開始說謊 —— 同一格畫得出折線圖，檔名卻寫著 `-scatter.svg`。改名的錢在
#: 那個當下**還沒有人付過**（零份 recipe、零份 fixture 用它，它只活在一條還
#: 沒合併的分支上），所以就在那個當下改掉。CLAUDE.md 那段 `bundle` 講的正是
#: 反面：名字含糊而改名要付一道遷移，於是拖著，最後混淆的是人。
CHART_CUSTOM = "chart"
CHARTS: Tuple[str, ...] = (CHART_BOX, CHART_HIST, CHART_PROFILE, CHART_MAP,
                           CHART_CUSTOM)

#: **預設勾哪幾張** —— 刻意**不是** :data:`CHARTS` 全部。
#:
#: `CHART_CUSTOM` 的兩條軸是使用者自己挑的（`pipeline.chart_spec`），所以
#: 預設勾著它等於「一張全新的卡片預設就會寫一個畫不出來的檔案」，而畫布上還
#: 會掛著一條說設定沒做完的黃字。那四張不必問任何問題就畫得出來，這一張要問
#: 兩個。
DEFAULT_CHARTS: Tuple[str, ...] = (CHART_BOX, CHART_HIST, CHART_PROFILE,
                                   CHART_MAP)

#: 畫面與檔名上的字（使用者 2026-09-07 定調 ``position profile``）。
CHART_LABELS: Dict[str, str] = {
    CHART_BOX: "Box plot",
    CHART_HIST: "Histogram",
    CHART_PROFILE: "Position profile",
    CHART_MAP: "Heat map",
    CHART_CUSTOM: "Your own chart",
}

#: 每張圖**用得到**哪幾格「自己的字」（`chart_style.PER_CHART_KEYS` 的子集）。
#:
#: ⚠ 盒鬚圖的 X 軸是**類別**（一個區域一格），「橫著要幾個刻度」在那裡沒有
#: 意思 —— 而 CLAUDE.md 的規矩是**不適用的收起來，不要攤在那裡讓使用者猜**。
#: 一格答了也沒用的設定比沒有那一格更糟（推廣鐵則）。
#:
#: 這張表住在這裡而不是 `pipeline/chart_style`：它講的是「這種圖長什麼樣」，
#: 而 `chart_style` **刻意不認識任何一張圖的名字**（認識的話 `pipeline/` 就
#: 開始依賴 `export/`，方向是反的）。
PER_CHART_APPLIES: Dict[str, Tuple[str, ...]] = {
    CHART_BOX: ("title", "xlabel", "ylabel", "yticks"),
    CHART_HIST: ("title", "xlabel", "ylabel", "xticks", "yticks"),
    CHART_PROFILE: ("title", "xlabel", "ylabel", "xticks", "yticks"),
    # 熱圖兩軸都是**影像上的位置**：沒有刻度數字（色條才是那張圖的尺），
    # 也沒有軸名（「X (px)」對讀圖的人不是一句話，底下那一行
    # `區域 - 統計量` 才是）。所以它只剩標題。
    CHART_MAP: ("title",),
    # 散佈圖的兩條軸是**使用者自己挑的欄**，所以名字與刻度數都用得到。
    # 這一張的兩條軸是**使用者自己挑的欄**，所以名字與刻度數都用得到。
    CHART_CUSTOM: ("title", "xlabel", "ylabel", "xticks", "yticks"),
}

#: 哪幾格**全域**設定只對某幾張圖有意思（沒列的就是四張都用得到）。
#:
#: ⚠ 同 :data:`PER_CHART_APPLIES` 的理由：一格答了也沒用的設定比沒有那一格更
#: 糟。`Write report` 只畫盒鬚圖，而它的設定面板上以前照樣列著「熱圖的每一格
#: 一樣大」「直方圖切幾根柱」—— 兩格永遠不會發生任何事。
#:
#: ⚠ **收起來不等於清掉**：值仍然留在那一格參數裡（把 Heat map 取消勾選再
#: 勾回來，設定要還在），編輯器只是不顯示。
#: ⚠ **`CHART_CUSTOM` 用得到哪幾格，看的是它現在能畫哪幾種記號**
#: （`pipeline.chart_spec.MARKS`）—— 盒子讀 `whiskers` 與填色、格子讀
#: `map_values`、線與盒子讀 `points`。加一種記號而忘了在這裡登記的話，那一格
#: 在編輯器裡是收起來的，而它**在檔案裡是有作用的**：使用者改不到一個真的
#: 會變的東西。`test_every_editor_moves_the_preview` 守著反過來的那一半。
GLOBAL_APPLIES: Dict[str, Tuple[str, ...]] = {
    "bins": (CHART_HIST,),
    "percent": (CHART_HIST,),
    "whiskers": (CHART_BOX, CHART_CUSTOM),
    "equal_cells": (CHART_MAP,),
    "map_values": (CHART_MAP, CHART_CUSTOM),
    # 一格框一個記號：profile 的散點、熱圖照實鋪時描出來的那個框，以及
    # 自己配的那一張畫成線或盒子的時候
    "points": (CHART_PROFILE, CHART_MAP, CHART_CUSTOM),
    "point_fill": (CHART_PROFILE, CHART_CUSTOM),
    "fill_strength": (CHART_BOX, CHART_HIST, CHART_PROFILE, CHART_CUSTOM),
    "fill_color": (CHART_BOX, CHART_HIST, CHART_PROFILE, CHART_CUSTOM),
    # 盒鬚圖的 X 是類別、熱圖兩軸是位置 —— 兩張都沒有「橫著幾個刻度」
    "xticks": (CHART_HIST, CHART_PROFILE, CHART_CUSTOM),
    "yticks": (CHART_BOX, CHART_HIST, CHART_PROFILE, CHART_CUSTOM),
    # 色階只有「顏色代表大小」的那兩張用得到
    "ramp": (CHART_MAP, CHART_CUSTOM),
    # ⚠ **規格線畫在「值那一軸」上，而熱圖沒有那條軸** —— 那張圖的值是顏色。
    # 硬畫的話那條線會落在一條位置軸上，讀起來是「規格在畫面的這個位置」。
    "ref_lines": (CHART_BOX, CHART_HIST, CHART_PROFILE, CHART_CUSTOM),
    # ⚠ **只有自己配的那一張**（F89-5）。四張預設圖各自有一支寫死的繪圖程式
    # 碼（F88 §14 量過為什麼不合併），而它們不讀這兩格 —— 攤在那裡的話，
    # 使用者在 Box plot 分頁上把軸切成 log 會**什麼都不發生**。
    "yscale": (CHART_CUSTOM,),
    "slot_order": (CHART_CUSTOM,),
}

#: `CHART_CUSTOM` 那一張**還要看它畫成哪一種記號** —— ``鍵 -> 哪幾種記號真的
#: 讀它``。沒列的鍵就是「這張圖不管什麼記號都用得到」（標題、刻度數…）。
#:
#: 為什麼要有第二層：:data:`GLOBAL_APPLIES` 是**一張圖一列**，答得出「這一格
#: 管不管得到這張圖」，答不出「這張圖現在畫成散點，那 `Whiskers` 有作用嗎」。
#: 沒有這一層的話，把它配成散點的人在設定裡看得到 `Whiskers` 而它什麼都不做
#: —— 一格答了也沒用的設定比沒有那一格更糟（推廣鐵則）。
#:
#: ⚠ **這張表會跟 `export.chart_draw` 漂**，所以它配著一支**兩個方向都測**的
#: 測試：列出來的每一對（鍵, 記號）必須真的改變 SVG，而**沒**列出來的那幾對
#: 必須不改變。少一邊的話這張表就只是一段註解。
CUSTOM_BY_MARK: Dict[str, Tuple[str, ...]] = {
    # 格子的兩條軸都是類別 —— 「132 在哪裡」在那張圖上沒有答案。
    "ref_lines": ("point", "line", "bar", "box"),
    # 值那一軸是類別的時候沒有 log 可言（格子的 Y 是槽）。
    "yscale": ("point", "line", "bar", "box"),
    # ⚠ **只有長條與盒鬚**：散佈圖與折線排過之後 X 軸不再是那一欄的值
    # （說謊），而格子排過之後 wafer map 的兩條軸會被打亂。
    "slot_order": ("bar", "box"),
    "whiskers": ("box",),
    "map_values": ("cell",),
    "points": ("line", "box"),
    "point_fill": ("point", "line"),
    "fill_strength": ("box", "bar"),
    "fill_color": ("box", "bar"),
}


def applies(key: str, kind: str, mark: str = "") -> bool:
    """這一格設定**改得到**那張圖嗎（`CHART_CUSTOM` 再看記號）。

    UI 問這一支，不要自己讀那兩張表 —— 各讀一份的那天，編輯器收起來的與真的
    沒有作用的會是兩組不一樣的東西。
    """
    uses = GLOBAL_APPLIES.get(str(key))
    if uses is not None and str(kind) not in uses:
        return False
    if str(kind) != CHART_CUSTOM:
        return True
    marks = CUSTOM_BY_MARK.get(str(key))
    return marks is None or str(mark) in marks


#: `profile` 沿哪一個軸。
AXIS_X, AXIS_Y = "x", "y"
AXES: Tuple[str, ...] = (AXIS_X, AXIS_Y)

#: 區域色 —— **同一組色相，畫在白紙上的那一階**（F88 第一刀 b，2026-09-07）。
#:
#: 為什麼跟 `ui.theme.REGION_COLORS` 不逐字相同
#: --------------------------------------------
#: 那一組是為了**畫在深色的 SEM 影像上**取的（那一份自己的說明就寫著「要在
#: 深色的 SEM 影像上看得見，所以都偏亮」）。這幾張圖畫在**白底**上，而同一個
#: 亮綠色在那裡是一條看不太到的細線 —— 用配色檢查器量過（2026-09-07）：
#: 八個裡有四個落在亮度帶之外，八個**全部**對白底的對比度不到 3:1。
#: 投影機上那一排 profile 就是這樣發虛的。
#:
#: 一組顏色服務兩個底是做不到的：往下取步救了紙、毀了影像上的框。所以做法跟
#: **深色模式**一模一樣 —— **同一條色階、不同的一階，各自對著自己的底驗過**，
#: 不是把一組顏色自動翻過來。
#:
#: 身分靠的是**色相與順序**，不是亮度：第 3 個在哪裡都是那個藍。逐色的色相
#: 位移 ≤ 0.5°（OKLCH），所以「他在對話框裡認得的綠色 ROI1」在圖上還是那個綠。
#:
#: 量出來的（`scripts/validate_palette.js`，surface `#ffffff`）：亮度帶、彩度
#: 下限、CVD 分離（最差相鄰 ΔE 9.6 protan）、正常視覺下限（16.9）、對比度
#: **五項全過**。⚠ 改這一組要重跑那支檢查器，不要用眼睛看。
REGION_COLOURS: Tuple[str, ...] = (
    "#049e6f", "#ac7d00", "#4980f0", "#dc4387",
    "#679800", "#b158d7", "#009a93", "#da580e")

#: 熱圖的色階 —— 冷到熱。**刻意不含區域色的任何一個**：這張圖上顏色的意思是
#: 「值多少」，而不是「這是哪一群」。兩種意思共用一個顏色的話，讀圖的人得先
#: 決定現在是哪一種。
HEAT_RAMP: Tuple[str, ...] = (
    "#2b3a67", "#3d6fa8", "#4aa3a2", "#c9c05a", "#e8913c", "#c0392b")

#: **單色階**（由淺到深的藍）—— 表示「大小」的預設。
#:
#: 通用規則是「表示大小用**單一色相、由淺到深**，不要彩虹」：彩虹在中段會製造
#: 出資料裡沒有的假邊界，而讀圖的人會把那道邊界當成一件事。
#: 但半導體的 wafer map 慣例就是彩虹 —— 所以**兩種都留**，預設單色
#: （使用者 2026-09-07：「兩種都可 預設單色」）。切換是 `chart_style` 的
#: `ramp` 那一格。
#:
#: 藍色是這個介面的重音色（`theme.accent` 是 `#3574d6`），所以這一階跟畫面
#: 其他地方是同一個家族。
SEQ_RAMP: Tuple[str, ...] = (
    "#eaf1fc", "#c2d6f2", "#8fb6ec", "#5a8fdd", "#3574d6", "#2b5eb0",
    "#1d3f77")

_AXIS = "#98a2b3"
_TEXT = "#444"
_MUTED = "#777"
_GRID = "#e8eaee"
#: 趨勢線 —— **炭黑，不是琥珀**。
#:
#: PEAR 用琥珀畫它，而 PEAR 的規矩是「no group is ever amber」（琥珀被留給
#: 趨勢線與色階中點）。那條規矩在 d4t **不成立**，而且是兩次不成立：
#:
#: * `theme.REGION_COLORS` 的第 2 個就是 ``#f0b429`` —— 接第二個區域時，
#:   那一群的 profile 實線與它的趨勢虛線會是同一個顏色。實測畫出來看不出
#:   哪條是哪條（2026-09-07 的第一版就是這樣）。
#: * 琥珀在 d4t 已經有一個意思了：**最異常的那一格**
#:   （`overlay.ROI_WINNER_COLOR`、畫布上的粗框）。同一個顏色在同一份報表裡
#:   講兩件事，使用者得先決定現在是哪一種。
#:
#: 炭黑離八個區域色都很遠，而且它讀起來就是「註解」而不是「資料」——
#: 一條最小平方線本來就是註解。
_TREND = "#3a3f4b"

_MISSING = "-"

#: 一張圖**畫得完**所需要的最小尺寸。
#:
#: ⚠ 這不是美觀下限，是**正確性**下限。每一支 `_svg_*` 都把圖區夾在
#: ``max(80, height - 上留白 - 下留白)`` —— 也就是高度不夠時圖區**不會跟著
#: 縮**，於是內容比 viewBox 還高，而 SVG 的 viewBox 會**把超出的部分切掉**。
#: 實測（2026-09-07）：儀表把 profile 畫在 126 px 高的格子裡，斜率那一行
#: （整張圖唯一的數字）被切掉一半，而圖看起來完全正常。
#:
#: 所以 :func:`build_chart_svg` 把尺寸夾在這裡，讓呼叫端**縮整張圖**（等比
#: 例畫小）而不是切內容。字會變小，但沒有一樣東西不見。
MIN_WIDTH, MIN_HEIGHT = 220, 170


# --------------------------------------------------------------------------- #
# 資料層 —— **畫面與檔案吃的是同一份**
# --------------------------------------------------------------------------- #
def chart_series(notes: Sequence[Any], metric: str = "",
                 colours: Sequence[str] = ()) -> Dict[str, Any]:
    """`ctx.meta["glv_hist"]` 的那幾條 → 畫圖要的數字。

    **Qt-free、無繪圖** —— 這是「兩份繪圖程式碼吃同一支」的那個「同一支」。
    畫面上的儀表與寫出去的 SVG 各畫各的，但兩邊的**數字**只有這一個出處；
    各自算一次的話，圖上那一點與 CSV 上那一格會在某一天分岔，而那一天畫面上
    看起來完全正常。

    回 ``{"metric", "metrics", "groups": [{name, colour, values, cx, cy,
    rects}]}``。``metric`` 沒給就用第一條有東西的那一個。
    沒有任何一條帶 ``spread``（沒開 ``report``、或走 pooled）時 ``groups``
    是空的 —— 呼叫端要說得出「沒有東西可畫」跟「畫出來是平的」的差別。
    """
    pal = list(colours) or list(REGION_COLOURS)
    groups: List[Dict[str, Any]] = []
    metrics: List[str] = []
    for note in (notes or ()):
        if not isinstance(note, dict):
            continue
        spread = note.get("spread")
        if not isinstance(spread, dict):
            continue
        stats = spread.get("stats") or {}
        for m in stats:
            if m not in metrics:
                metrics.append(str(m))
    want = str(metric or "") or (metrics[0] if metrics else "")
    for note in (notes or ()):
        if not isinstance(note, dict):
            continue
        spread = note.get("spread")
        if not isinstance(spread, dict):
            continue
        values = (spread.get("stats") or {}).get(want)
        if not values:
            continue
        cx = list(spread.get("cx") or ())
        cy = list(spread.get("cy") or ())
        # 值與位置**共用索引**是所有位置計算的前提 —— 對不上就整組不畫
        # （同 `set_marks` 的規矩：畫一半比不畫糟）。
        if len(cx) != len(values) or len(cy) != len(values):
            continue
        name = str(note.get("region") or "") or str(note.get("prefix") or "")
        groups.append({
            "name": name or "region",
            "colour": pal[len(groups) % len(pal)],
            "values": [float(v) for v in values],
            "cx": [float(v) for v in cx],
            "cy": [float(v) for v in cy],
            "rects": [list(r) for r in (spread.get("rects") or ())],
        })
    return {"metric": want, "metrics": metrics, "groups": groups}


# --------------------------------------------------------------------------- #
# 外觀 —— **每一格都問 `style`，不再寫死**（F87）
# --------------------------------------------------------------------------- #
def _text_attrs(style: Dict[str, Any], which: str,
                fallback_ink: str) -> Tuple[float, str, str]:
    """``(字級, 粗細, 顏色)`` —— ``which`` 是 ``tick`` 或 ``axis``。

    ⚠ **顏色空字串 = auto**，而 auto 在這裡是「主題的墨色」不是「隨便一個
    灰」。PEAR 的 README 說得最直白：*a light grey tick label is not there on
    a projector* —— 而這幾張圖的去處正是投影與報告（使用者 2026-09-07）。
    """
    size = float(style.get("%s_size" % which, 10.0) or 10.0)
    bold = "700" if bool(style.get("%s_bold" % which)) else "400"
    ink = str(style.get("%s_color" % which, "") or "") or fallback_ink
    return size, bold, ink


def fill_attrs(style: Dict[str, Any], base: str,
               opacity: float) -> Tuple[str, float]:
    """填色與濃度 ``(色, opacity)`` —— **柱子／盒子／實心記號共用這一支**。

    * 顏色空的就跟著那一群自己的顏色走（同 :func:`_mark_colour` 的語意）；
    * 濃度是**倍率**不是絕對值：每一種圖自己那個淡度是設計過的（柱 0.45、
      盒子 0.18 —— 盒鬚圖上的墨水本來就多），一格絕對值會把那個關係抹平，
      而且沒有一個值同時等於今天的兩個。1.0 就逐位元組不變。
    """
    ink = str(style.get("fill_color", "") or "") or base
    k = float(style.get("fill_strength", 1.0) or 0.0)
    return ink, max(0.0, min(1.0, opacity * k))


def _mark_colour(style: Dict[str, Any], which: str, fallback: str) -> str:
    """資料的顏色：``point`` / ``line``。空 = **跟著那一群自己的顏色走**。

    那是 PEAR 的語意，而且是對的：使用者八成不想手動指定每一群的顏色，
    他只想在某一個特例上蓋掉。
    """
    return str(style.get("%s_color" % which, "") or "") or fallback


# --------------------------------------------------------------------------- #
# 共用的一點幾何
# --------------------------------------------------------------------------- #
def _span(values: Sequence[float], lock: Optional[Sequence[Any]] = None
          ) -> Tuple[float, float]:
    """要畫的範圍 —— **鎖了就用鎖的**（見 `build_chart_svg` 的 ``style``）。

    auto 縮放在看一批的時候是對的，兩批擺在一起就會騙人：各自挑各自的範圍，
    一樣高的柱子其實不一樣高。所以鎖定是這一輪唯一非做不可的外觀設定。
    """
    if lock:
        try:
            lo, hi = float(lock[0]), float(lock[1])
            if math.isfinite(lo) and math.isfinite(hi) and hi > lo:
                return lo, hi
        except (TypeError, ValueError, IndexError):
            pass
    arr = np.asarray([v for v in values], dtype=np.float64).ravel()
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return 0.0, 1.0
    lo, hi = float(arr.min()), float(arr.max())
    if hi <= lo:
        pad = abs(lo) * 0.05 or 0.5
        return lo - pad, hi + pad
    pad = (hi - lo) * 0.06
    return lo - pad, hi + pad


def resolve_style(look: object, kind: str = CHART_BOX, axis: str = AXIS_X,
                  metric: str = "") -> Dict[str, Any]:
    """一張圖真正要用的那一份設定 —— **所有人唯一的入口**。

    `chart_style.style_for` 只做「全域 ＋ 這張圖自己的覆寫」；還有兩件事需要
    **認識圖的名字**，而那正是 `pipeline/chart_style` 刻意不知道的（知道的話
    `pipeline/` 就開始依賴 `export/`，方向是反的）：

    * 這張圖預設叫什麼（:data:`CHART_LABELS`）；
    * 「值那一軸」的名字要落在**哪一軸** —— 直方圖是 X，盒鬚圖與 profile 是 Y。

    ⚠ **這一支以前住在 `OutputUniformityStep._style_for` 上**，而那讓所有人
    （寫檔的卡片、圖的視窗、設定編輯器的預覽、以及後來的 `Write report`）都
    得去 `get_step("output_uniformity")` 繞一圈才問得到它。實際的代價已經付過
    一次：設定編輯器的預覽少走了它，於是「值那一軸的名字」那一格**畫面上完全
    沒有反應**，而它在寫出去的檔案裡是有作用的。住在這裡，繞路就沒有了。
    """
    from ..pipeline import chart_style

    st = chart_style.style_for(look, str(kind))
    st["axis"] = str(axis or AXIS_X)
    if not st.get("title"):
        st["title"] = CHART_LABELS.get(str(kind), str(kind))
    name = str(st.get("value_name") or "").strip() or str(metric or "")
    if kind == CHART_HIST:
        st["xlabel"] = st.get("xlabel") or name
    elif kind in (CHART_PROFILE, CHART_BOX):
        # 盒鬚圖的 Y 也是值那一軸 —— 以前這裡漏了它，於是同一格設定對三張圖
        # 有效、對一張沒有（而那張正是報表裡最常出現的）。
        st["ylabel"] = st.get("ylabel") or name
    return st


def _opacity(value: float) -> str:
    """opacity 印成字。**倍率 1.0 時要逐位元組等於以前那個字面值** ——
    `0.45` 而不是 `0.450000`（`output_report` 的盒鬚圖沒給 style）。"""
    text = ("%.3f" % float(value)).rstrip("0").rstrip(".")
    return text or "0"


def seq_hex(t: float) -> str:
    """0–1 → **單色階**上的一個顏色（見 :data:`SEQ_RAMP`）。"""
    return _ramp_hex(SEQ_RAMP, t)


def _is_dark(hex_colour: str) -> bool:
    """這個底色上該用白字還是黑字（同 PEAR 的 `_is_dark`）。"""
    t = str(hex_colour or "").strip()
    if len(t) != 7 or t[0] != "#":
        return False
    r, g, b = (int(t[i:i + 2], 16) for i in (1, 3, 5))
    return (0.299 * r + 0.587 * g + 0.114 * b) < 140.0


def _pos_labels(values: Sequence[float]) -> List[str]:
    """熱圖那兩條軸上的刻度字（F117 F8）—— **像素位置要取整**。

    走查記的是 `27.50`。那個 .5 是真的（框中心落在半個像素上），但它**不是
    資訊**：沒有人會去看一個框的中心是 24 還是 24.5，他看的是「左邊那一區比
    右邊暗」。多出來的兩位數字把一排刻度撐寬，而撐寬的代價是刻度變少。

    ⚠ **取整之後兩個刻度撞在一起就不取整。** 框只有幾個像素寬的時候（模板
    很小、或影像被縮過），整數分不開相鄰兩欄 —— 那時候印兩個一樣的數字比印
    `24.50` 糟得多，因為它看起來像畫錯了。
    """
    rounded = ["%d" % int(round(float(v))) for v in values]
    if len(set(rounded)) == len(set(float(v) for v in values)):
        return rounded
    return [_fmt(float(v)) for v in values]


def _slot_labels(o: List[str], centers: Sequence[float], origin: float,
                 step: float, at: float, style: Dict[str, Any],
                 horizontal: bool = True) -> None:
    """格子版的刻度：**一欄一個槽，標的是那一欄代表的位置**。

    槽位不是線性軸（欄距被拉成一樣寬了），所以刻度不能照線性去算 —— 挑幾個
    放得下的槽，標它自己的座標。
    """
    n = len(centers)
    if n == 0:
        return
    size, weight, ink = _text_attrs(style, "tick", _TEXT)
    key = "xticks" if horizontal else "yticks"
    want = max(2, min(int(style.get(key, 5) or 5), n))
    size = min(size, 11.0)
    picked = [int(round(k * (n - 1) / max(1, want - 1))) for k in range(want)]
    label = _pos_labels([centers[i] for i in picked])
    for k in range(want):
        i = picked[k]
        pos = origin + step * (i + 0.5)
        if horizontal:
            o.append("<text x='%.1f' y='%.1f' font-size='%g' font-weight='%s' "
                     "fill='%s' text-anchor='middle'>%s</text>"
                     % (pos, at + size + 4, size, weight, ink,
                        _esc(label[k])))
        else:
            o.append("<text x='%.1f' y='%.1f' font-size='%g' font-weight='%s' "
                     "fill='%s' text-anchor='end'>%s</text>"
                     % (at - 6, pos + size * 0.35, size, weight, ink,
                        _esc(label[k])))


def heat_hex(t: float) -> str:
    """0–1 → **彩虹色階**上的一個顏色（線性內插，兩端夾住）。

    **色階唯一的出處** —— 寫出去的 SVG、疊在影像上的那一層、以及影像上那條
    色條都問這一支。抄一份的那天，畫面上的紅跟報表裡的紅會是兩個紅。
    """
    return _ramp_hex(HEAT_RAMP, t)


def _ramp_hex(ramp: Sequence[str], t: float) -> str:
    """一階色 ＋ 0–1 → 一個顏色（線性內插，兩端夾住）。"""
    if not math.isfinite(t):
        return _MUTED
    t = min(1.0, max(0.0, float(t)))
    pos = t * (len(ramp) - 1)
    i = min(len(ramp) - 2, int(pos))
    f = pos - i
    a, b = ramp[i], ramp[i + 1]
    out = []
    for k in (1, 3, 5):
        ca, cb = int(a[k:k + 2], 16), int(b[k:k + 2], 16)
        out.append(int(round(ca + (cb - ca) * f)))
    return "#%02x%02x%02x" % tuple(out)


def _frame(o: List[str], x: float, y: float, w: float, h: float) -> None:
    """圖區的外框 —— 一張報表裡的圖需要的那道最基本的家具。"""
    o.append("<rect x='%.1f' y='%.1f' width='%.1f' height='%.1f' fill='none' "
             "stroke='%s' stroke-width='1'/>" % (x, y, w, h, _AXIS))


def _ylabels(o: List[str], ticks: Sequence[float], lo: float, hi: float,
             x: float, y: float, h: float, w: float,
             style: Optional[Dict[str, Any]] = None) -> None:
    size, weight, ink = _text_attrs(dict(style or {}), "tick", _TEXT)
    for t in ticks:
        ty = y + h - (t - lo) / (hi - lo) * h
        o.append("<line x1='%.1f' y1='%.1f' x2='%.1f' y2='%.1f' stroke='%s' "
                 "stroke-width='1'/>" % (x, ty, x + w, ty, _GRID))
        o.append("<text x='%.1f' y='%.1f' font-size='%g' font-weight='%s' "
                 "fill='%s' text-anchor='end'>%s</text>"
                 % (x - 6, ty + size * 0.3, size, weight, ink, _esc(_fmt(t))))


#: 參考線的顏色 —— **不是任何一個區域色，也不是趨勢線那個炭黑**。
#:
#: 它講的既不是「哪一群」也不是「資料的走向」，而是**一條外面來的界線**。
#: 磚紅是這個介面裡「注意」的語彙（`theme.danger` 那一族），而規格線正是
#: 那個意思 —— 但它比 `danger` 淡，因為它是**背景上的一條參考**，不是一個
#: 警報：超規的是資料，不是那條線。
REF_COLOUR = "#b4544a"


def draw_refs(o: List[str], style: Dict[str, Any], lo: float, hi: float,
              px: float, py: float, pw: float, ph: float,
              vertical: bool = True) -> None:
    """把規格線畫上去（F89-3）。**每一張有「值那一軸」的圖共用這一支。**

    ``vertical=True``（預設）＝值在 Y 軸上（盒鬚圖、profile、自己配的那張）；
    ``False`` ＝值在 X 軸上（直方圖）。

    ⚠ **超出範圍的那一條不畫。** 一條貼在圖框邊上的線讀起來是「規格剛好在
    這裡」，而真相是「規格在畫面外」—— 那兩件事差很多。反過來說，如果使用者
    鎖了尺度（`lock`），線就會落在他鎖的那個範圍裡，那是對的。

    ⚠ 這一支**不畫圖例**：每一條線自己帶著名字（或值）貼在右端，那比一個要
    對照的圖例少一次跳視。
    """
    from ..pipeline.chart_style import parse_refs

    try:
        refs = parse_refs(style.get("ref_lines", ""))
    except Exception:  # 畫圖不准被一格擋下來
        swallowed("uniformity_charts.draw_refs")
        return
    if not refs or hi <= lo:
        return
    size, weight, _ink = _text_attrs(style, "tick", _TEXT)
    for name, value in refs:
        t = (float(value) - lo) / (hi - lo)
        if not (0.0 <= t <= 1.0):
            continue
        said = "%s %s" % (name, _fmt(float(value))) if name \
            else _fmt(float(value))
        if vertical:
            y = py + ph - t * ph
            o.append("<line x1='%.1f' y1='%.1f' x2='%.1f' y2='%.1f' "
                     "stroke='%s' stroke-width='1.2' stroke-dasharray='6 3'/>"
                     % (px, y, px + pw, y, REF_COLOUR))
            o.append("<text x='%.1f' y='%.1f' font-size='%g' "
                     "font-weight='%s' fill='%s' text-anchor='end'>%s</text>"
                     % (px + pw - 3, y - 3, size, weight, REF_COLOUR,
                        _esc(said)))
        else:
            x = px + t * pw
            o.append("<line x1='%.1f' y1='%.1f' x2='%.1f' y2='%.1f' "
                     "stroke='%s' stroke-width='1.2' stroke-dasharray='6 3'/>"
                     % (x, py, x, py + ph, REF_COLOUR))
            # ⚠ **字要留在圖區裡**，而且靠邊的時候要換錨點：`middle` 的
            # 標籤在最右邊那條線上會有一半跑到框外（render 出來才看到的）。
            # 這裡不量字寬 —— 換錨點就夠了，而且它在任何字級下都成立。
            near = (x - px) / pw if pw else 0.5
            if near > 0.82:
                anchor, tx = "end", x - 3
            elif near < 0.18:
                anchor, tx = "start", x + 3
            else:
                anchor, tx = "middle", x
            o.append("<text x='%.1f' y='%.1f' font-size='%g' "
                     "font-weight='%s' fill='%s' text-anchor='%s'>"
                     "%s</text>"
                     % (tx, py + size + 2, size, weight, REF_COLOUR, anchor,
                        _esc(said)))


def _xlabels(o: List[str], ticks: Sequence[float], to_x, y: float,
             style: Optional[Dict[str, Any]] = None) -> None:
    """X 軸上的刻度數字（三張圖共用 —— 各寫一份的那份會漂）。"""
    size, weight, ink = _text_attrs(dict(style or {}), "tick", _TEXT)
    for t in ticks:
        o.append("<text x='%.1f' y='%.1f' font-size='%g' font-weight='%s' "
                 "fill='%s' text-anchor='middle'>%s</text>"
                 % (to_x(t), y + size * 0.5, size, weight, ink, _esc(_fmt(t))))


def _axis_names(o: List[str], style: Dict[str, Any], width: int, height: int,
                px: float, py: float, pw: float, ph: float,
                xdef: str, ydef: str) -> None:
    xl = str(style.get("xlabel") or "") or xdef
    yl = str(style.get("ylabel") or "") or ydef
    size, weight, ink = _text_attrs(style, "axis", _TEXT)
    if xl:
        o.append("<text x='%.1f' y='%d' font-size='%g' font-weight='%s' "
                 "fill='%s' text-anchor='middle'>%s</text>"
                 % (px + pw / 2, height - 8, size, weight, ink, _esc(xl)))
    if yl:
        cy = py + ph / 2
        o.append("<text x='12' y='%.1f' font-size='%g' font-weight='%s' "
                 "fill='%s' text-anchor='middle' "
                 "transform='rotate(-90 12 %.1f)'>%s</text>"
                 % (cy, size, weight, ink, cy, _esc(yl)))


def _empty(width: int, height: int, why: str) -> str:
    """**畫不出來仍然回一張圖**（`boxplot` 的同一條規矩）。

    呼叫端把它塞進 HTML，而一個消失的區塊讀起來是「這裡本來就沒有東西」。
    """
    return ("<svg xmlns='http://www.w3.org/2000/svg' width='%d' height='%d' "
            "viewBox='0 0 %d %d'><rect width='%d' height='%d' fill='#fff'/>"
            "<text x='%d' y='%d' font-size='12' fill='%s' "
            "text-anchor='middle'>%s</text></svg>"
            % (width, height, width, height, width, height,
               width // 2, height // 2, _MUTED, _esc(why)))


def _head(width: int, height: int, title: str) -> List[str]:
    o = ["<svg xmlns='http://www.w3.org/2000/svg' width='%d' height='%d' "
         "viewBox='0 0 %d %d'>" % (width, height, width, height),
         "<rect width='%d' height='%d' fill='#fff'/>" % (width, height)]
    if title:
        # **靠左，跟盒鬚圖同一套**（F117 F8）—— 同一頁上兩種對齊就是不對。
        # 那兩個常數住在 `boxplot.py`（見它們的說明）。
        o.append("<text x='%d' y='20' font-size='13' font-weight='%s' "
                 "fill='%s'>%s</text>"
                 % (TITLE_X, TITLE_WEIGHT, _TEXT, _esc(title)))
    return o


# --------------------------------------------------------------------------- #
# 直方圖
# --------------------------------------------------------------------------- #
def _svg_histogram(series: Dict[str, Any], style: Dict[str, Any],
                   width: int, height: int) -> str:
    """值怎麼散開 —— 每一群一疊半透明的柱子，共用同一把尺。

    ``percent`` 打開時每一群畫的是**自己的比例**，所以框數差很多的兩群也
    比得起來（PEAR 的 ``%`` 那顆開關）。
    """
    groups = [g for g in series.get("groups") or [] if g.get("values")]
    if not groups:
        return _empty(width, height, "no boxes to plot")
    bins = max(4, min(128, int(style.get("bins") or 24)))
    pct = bool(style.get("percent", False))
    allv = [v for g in groups for v in g["values"]]
    lo, hi = _span(allv, style.get("vlock"))
    edges = np.linspace(lo, hi, bins + 1)

    counts = []
    for g in groups:
        c, _ = np.histogram(np.asarray(g["values"], dtype=np.float64), bins=edges)
        c = c.astype(np.float64)
        if pct and c.sum() > 0:
            c = c / c.sum() * 100.0
        counts.append(c)
    top = float(max((c.max() for c in counts), default=0.0)) or 1.0

    pad_l, pad_r = 62, 16
    pad_t = 30 if style.get("title") else 12
    pad_b = 56
    pw = max(80, width - pad_l - pad_r)
    ph = max(80, height - pad_t - pad_b)
    o = _head(width, height, str(style.get("title") or ""))
    ticks = _nice_ticks(0.0, top, int(style.get("yticks") or 5))
    _ylabels(o, ticks, 0.0, top, pad_l, pad_t, ph, pw, style)
    _frame(o, pad_l, pad_t, pw, ph)

    bw = pw / bins
    for g, c in zip(groups, counts):
        for i, v in enumerate(c):
            if v <= 0:
                continue
            bh = v / top * ph
            ink, alpha = fill_attrs(style, g["colour"], 0.45)
            o.append("<rect x='%.2f' y='%.2f' width='%.2f' height='%.2f' "
                     "fill='%s' fill-opacity='%s' stroke='%s' "
                     "stroke-width='0.6'/>"
                     % (pad_l + i * bw, pad_t + ph - bh, max(0.6, bw - 0.6),
                        bh, ink, _opacity(alpha), g["colour"]))
    _xlabels(o, _nice_ticks(lo, hi, int(style.get("xticks") or 5)),
             lambda t: pad_l + (t - lo) / (hi - lo) * pw, pad_t + ph + 11,
             style)
    # ⚠ 直方圖的**值在 X 軸上** —— 規格線因此是直的，不是橫的。
    draw_refs(o, style, lo, hi, pad_l, pad_t, pw, ph, vertical=False)
    _legend(o, groups, pad_l, pad_t + ph + 32)
    _axis_names(o, style, width, height, pad_l, pad_t, pw, ph,
                str(series.get("metric") or "value"),
                "share of the group (%)" if pct else "boxes")
    o.append("</svg>")
    return "".join(o)


def _line_legend(o: List[str], rows: Sequence[Tuple[str, str, str]],
                 x: float, y: float) -> None:
    """**三種線各是什麼**（F117 F8）—— ``[(顏色, dasharray, 名字)]``。

    走查記的是「Position profile 虛線／點線無圖例」。那張圖上有三種線：實線
    是 profile（**讀平不平的就是它**）、粗虛線是趨勢、細點線是那一群的平均。
    以前只有趨勢線有一句話（斜率），另外兩條要讀原始碼才知道 —— 而這張圖是
    寄給別人看的。

    ⚠ **畫一小段真的線，不是一個色塊**。`_legend` 那種方塊分不出虛實 ——
    而這裡要分的正好就是虛實。
    """
    cur = float(x)
    for colour, dash, name in rows:
        o.append("<line x1='%.1f' y1='%.1f' x2='%.1f' y2='%.1f' stroke='%s' "
                 "stroke-width='1.6'%s/>"
                 % (cur, y - 3, cur + 16, y - 3, colour,
                    " stroke-dasharray='%s'" % dash if dash else ""))
        o.append("<text x='%.1f' y='%.1f' font-size='10' fill='%s'>%s</text>"
                 % (cur + 20, y, _MUTED, _esc(name)))
        cur += 20 + len(name) * 5.4 + 14


def _legend(o: List[str], groups: Sequence[Dict[str, Any]],
            x: float, y: float) -> None:
    """一群一個色塊 ＋ 名字 ＋ **n**（框數）。

    ``n`` 不是裝飾：兩群的框數差十倍時，同樣高的柱子講的是完全不同的事。
    """
    cur = x
    for g in groups:
        o.append("<rect x='%.1f' y='%.1f' width='9' height='9' fill='%s'/>"
                 % (cur, y - 8, g["colour"]))
        text = "%s (n=%d)" % (g["name"], len(g["values"]))
        o.append("<text x='%.1f' y='%.1f' font-size='10' fill='%s'>%s</text>"
                 % (cur + 13, y, _TEXT, _esc(text)))
        cur += 22 + 6.2 * len(text)


# --------------------------------------------------------------------------- #
# Position profile —— 有沒有斜掉
# --------------------------------------------------------------------------- #
def _svg_profile(series: Dict[str, Any], style: Dict[str, Any],
                 width: int, height: int) -> str:
    """值 vs 框中心的位置。三種線，各一個顏色（PEAR §4 的規矩）：

    * **點** —— 一格框一個（空心，免得跟線糊在一起）
    * **profile**（實線，區域色壓深）—— 同一欄的框收成一個點。
      **這是讀平不平的那條線。**
    * **trend**（虛線，琥珀）—— 穿過每一格的最小平方線，斜率標在圖上
      （每 100 px）

    參照線畫在底層、資料畫在上層 —— 反過來的話趨勢線會蓋掉它本來要被拿來
    比較的那條 profile。
    """
    from ..algo import uniformity as unif

    groups = [g for g in series.get("groups") or [] if g.get("values")]
    if not groups:
        return _empty(width, height, "no boxes to plot")
    axis = str(style.get("axis") or AXIS_X).lower()
    axis = axis if axis in AXES else AXIS_X
    key = "cy" if axis == AXIS_Y else "cx"

    allv = [v for g in groups for v in g["values"]]
    allp = [p for g in groups for p in g[key]]
    lo, hi = _span(allv, style.get("vlock"))
    plo, phi = _span(allp, style.get("plock"))

    pad_l, pad_r = 62, 16
    pad_t = 30 if style.get("title") else 12
    # 56 → 70：底下現在是**兩行**（圖例一行、斜率一行）。少了這 14 px，
    # 斜率那一句會被畫到 viewBox 外面 —— SVG 不會報錯，它只是不見了。
    pad_b = 70
    pw = max(80, width - pad_l - pad_r)
    ph = max(80, height - pad_t - pad_b)
    o = _head(width, height, str(style.get("title") or ""))
    _ylabels(o, _nice_ticks(lo, hi, int(style.get("yticks") or 5)),
             lo, hi, pad_l, pad_t, ph, pw, style)
    _frame(o, pad_l, pad_t, pw, ph)

    def sx(p: float) -> float:
        return pad_l + (p - plo) / (phi - plo) * pw

    def sy(v: float) -> float:
        return pad_t + ph - (v - lo) / (hi - lo) * ph

    notes: List[str] = []
    for g in groups:
        pos, vals = g[key], g["values"]
        # ---- 底層：群平均那條淡虛線（完全平的 profile 會落在上面）--------
        mean = float(np.mean(vals))
        o.append("<line x1='%.1f' y1='%.1f' x2='%.1f' y2='%.1f' stroke='%s' "
                 "stroke-width='1' stroke-dasharray='2 3' stroke-opacity='0.5'"
                 "/>" % (pad_l, sy(mean), pad_l + pw, sy(mean), g["colour"]))
        # ---- 底層：趨勢線 -------------------------------------------------
        fit = unif.linear_trend(pos, vals)
        if fit is not None:
            slope, intercept = fit
            o.append("<line x1='%.1f' y1='%.1f' x2='%.1f' y2='%.1f' "
                     "stroke='%s' stroke-width='%g' stroke-dasharray='6 4'/>"
                     % (sx(plo), sy(slope * plo + intercept),
                        sx(phi), sy(slope * phi + intercept), _TREND,
                        float(style.get("line_width") or 1.6)))
            notes.append("%s: %s / 100 px"
                         % (g["name"], _fmt(slope * unif.SLOPE_UNIT_PX)))
        else:
            notes.append("%s: %s" % (g["name"], _MISSING))
        # ---- 上層：profile 線 ---------------------------------------------
        px_, pv = unif.profile_by_position(pos, vals)
        if px_.size >= 2:
            pts = " ".join("%.1f,%.1f" % (sx(a), sy(b))
                           for a, b in zip(px_, pv))
            o.append("<polyline points='%s' fill='none' stroke='%s' "
                     "stroke-width='%g'/>"
                     % (pts, _mark_colour(style, "line", g["colour"]),
                        float(style.get("line_width") or 1.6)))
        # ---- 上層：每一格框 ------------------------------------------------
        if style.get("points", True):
            r = float(style.get("point_size") or 2.6)
            dot = _mark_colour(style, "point", g["colour"])
            # **空心還是實心**（`point_fill`）—— 空心在點很多時看得到重疊，
            # 實心在投影片上比較看得見。兩種都對，看要給誰看。
            if bool(style.get("point_fill")):
                ink, alpha = fill_attrs(style, dot, 1.0)
                face = "fill='%s' fill-opacity='%s'" % (ink, _opacity(alpha))
            else:
                face = "fill='none'"
            for a, b in zip(pos, vals):
                o.append("<circle cx='%.1f' cy='%.1f' r='%.1f' %s "
                         "stroke='%s' stroke-width='1'/>"
                         % (sx(a), sy(b), r, face, dot))
    _xlabels(o, _nice_ticks(plo, phi, int(style.get("xticks") or 5)),
             sx, pad_t + ph + 11, style)
    draw_refs(o, style, lo, hi, pad_l, pad_t, pw, ph)
    # **三種線各是什麼**（F117 F8）。斜率那一句留著 —— 它是一個數字，而圖例
    # 講的是「哪一條是哪一條」，兩件不同的事。
    # ⚠ **好幾群的時候圖例用中性色。** 一群的時候拿那一群的顏色是對的（圖上
    # 就那一個顏色），好幾群的時候那個色塊會變成一句假話 —— 它看起來像在說
    # 「這個顏色＝profile」，而每一群各有各的顏色。圖例講的是**線的樣子**，
    # 誰是誰由那一行斜率上的名字講。
    one = groups[0]["colour"] if len(groups) == 1 else _MUTED
    _line_legend(o, [
        (_mark_colour(style, "line", one) if len(groups) == 1 else _MUTED,
         "", "profile"),
        (_TREND, "6 4", "trend"),
        (one, "2 3", "group average"),
    ], pad_l, pad_t + ph + 32)
    o.append("<text x='%.1f' y='%.1f' font-size='10' fill='%s'>slope %s</text>"
             % (pad_l, pad_t + ph + 46, _TREND, _esc("; ".join(notes))))
    _axis_names(o, style, width, height, pad_l, pad_t, pw, ph,
                "box centre %s (px)" % axis.upper(),
                str(series.get("metric") or "value"))
    o.append("</svg>")
    return "".join(o)


# --------------------------------------------------------------------------- #
# Heat map —— 不均勻在哪裡
# --------------------------------------------------------------------------- #
def _heat_values(series: Dict[str, Any], style: Optional[Dict[str, Any]] = None
                 ) -> Tuple[List[float], List[Any], List[str],
                            Tuple[float, float]]:
    """攤平所有區域的 ``(值, 框, 顏色)`` 與共用的 ``(lo, hi)``。

    **色階跨區域共用**（PEAR 的 vmin/vmax 也是全取）。對不上（框數與值數不等）
    就整組回空 —— 錯位的顏色指向錯的地方，而畫面上不會說。
    """
    st = dict(style or {})
    vals: List[float] = []
    rects: List[Any] = []
    for g in series.get("groups") or []:
        gv = list(g.get("values") or ())
        gr = [tuple(r) for r in (g.get("rects") or ())]
        if not gv or len(gr) != len(gv):
            return [], [], [], (0.0, 0.0)
        vals.extend(float(v) for v in gv)
        rects.extend(gr)
    if not rects:
        return [], [], [], (0.0, 0.0)
    lo, hi = _span(vals, st.get("hlock"))
    span = (hi - lo) or 0.0
    # 單色還是彩虹（`chart_style.ramp`，使用者 2026-09-07 定調預設單色）。
    # **兩種鋪法與疊在影像上的那一層都走這裡**，所以切換一次全部跟著。
    ink = heat_hex if str(st.get("ramp", "")) == "rainbow" else seq_hex
    cols = [ink(0.5 if span <= 0 else (v - lo) / span) for v in vals]
    return vals, rects, cols, (lo, hi)


def heat_lattice(series: Dict[str, Any],
                 style: Optional[Dict[str, Any]] = None
                 ) -> Tuple[List[float], List[float],
                            List[Tuple[int, int, str, float]],
                            Tuple[float, float]]:
    """**每一格一樣大**的版本：``(欄中心, 列中心, [(i, j, 色, 值)…], (lo, hi))``。

    為什麼這是熱圖的預設（PEAR 的 `equal cells`，2026-09-07 使用者：
    「他就是示意圖，但目前顯示上會怪怪的 那個 heatmap 框大小」）
    ------------------------------------------------------------------
    照實鋪（:func:`heat_tiles`）的每一格畫到與鄰居的中線為止 —— 間距不平均、
    或少了一格，相鄰兩格的**面積就明顯不一樣**，而**面積不是這張圖在量的
    東西**。排成格子之後每一格都一樣大，那才是一張 die map 該有的樣子，兩格
    也才一眼比得起來；軸上仍然標著每一欄代表的位置。

    ⚠ 這一支給的是**槽位**（第幾欄第幾列），不是像素 —— 畫圖那一側自己把
    圖區切成 ``欄數 × 列數`` 塞滿。**所以它不保長寬比**，那是刻意的：
    這張圖是示意圖，不是影像的縮圖。

    疊在影像上的那一層**不走這一支**（見 :func:`heat_tiles`）—— 那裡位置要
    對得起影像。
    """
    from ..algo import uniformity as unif

    vals, rects, cols, span = _heat_values(series, style)
    if not rects:
        return [], [], [], (0.0, 0.0)
    cx, cy = unif.rect_centers(rects)
    xc, _xe = unif.cell_edges(cx)
    yc, _ye = unif.cell_edges(cy)
    if xc.size == 0 or yc.size == 0:
        return [], [], [], span
    out: List[Tuple[int, int, str, float]] = []
    for k, v in enumerate(vals):
        i = int(np.abs(xc - cx[k]).argmin())
        j = int(np.abs(yc - cy[k]).argmin())
        out.append((i, j, cols[k], float(v)))
    return [float(v) for v in xc], [float(v) for v in yc], out, span


def heat_tiles(series: Dict[str, Any],
               style: Optional[Dict[str, Any]] = None,
               bounds: Optional[Sequence[Any]] = None
               ) -> Tuple[List[Tuple[float, float, float, float]],
                          List[str], Tuple[float, float]]:
    """熱圖的**磚**：``([(x0, y0, x1, y1), …], [色, …], (lo, hi))``，像素座標。

    ⚠ **照實鋪唯一的出處。** 疊在影像上的那一層
    （`OutputUniformityStep.overlay_heat` → `ImageView.set_heat`）與
    `equal_cells` 關掉時的那張 SVG 都問這一支；格子版走 :func:`heat_lattice`，
    而**兩支的顏色來自同一個 `_heat_values`** —— 各算一份的話，畫面上那一格
    的顏色跟報表裡的會在某一天分岔，而那一天兩張都畫得出來（這個 repo 最貴的
    那種 bug）。

    **所有區域一起鋪一次、色階共用**（PEAR 的 `heat_cells(self._rois, …)` 與
    它那組 vmin/vmax）。``bounds = (w, h)`` 把鋪磚夾回影像裡。
    對不上（框數與值數不等）就整組不畫 —— 錯位的顏色指向錯的地方。
    """
    from ..algo import uniformity as unif

    _vals, rects, colours, span = _heat_values(series, style)
    if not rects:
        return [], [], (0.0, 0.0)
    return unif.cell_boxes(rects, bounds), colours, span


def _svg_map(series: Dict[str, Any], style: Dict[str, Any],
             width: int, height: int) -> str:
    """框放在自己的 (x, y) 上，顏色＝值，旁邊一條色條。

    **兩種鋪法，預設是格子版**（`equal_cells`，PEAR 的預設）：

    * **格子版** —— 一欄一個槽、每一格一樣大，鋪滿整個圖區。**不保長寬比**，
      因為它是示意圖不是影像的縮圖（使用者 2026-09-07：「不用跟影像一樣大或
      比例一樣沒關係，他就是示意圖」）。理由見 :func:`heat_lattice`。
    * **照實鋪** —— 每一格畫到與鄰居的中線為止（`cell_boxes`），等比例置中。
      要看真實的空間關係時用它。量到的只有框裡面，框與框之間是沒有量的，而把
      值鋪滿那一塊等於用最近的一次真實量測去填它 —— 於是整片的梯度看起來是一
      片梯度，不是一排小色塊。

    ⚠ **疊在影像上的那一層永遠是照實鋪**（`Step.overlay_heat` → `heat_tiles`）
    —— 它畫在影像上，位置要對得起那張圖。

    ⚠ **所有區域一起鋪一次**（PEAR 的做法，2026-09-07 使用者定調「都按照
    PEAR 一樣」）。一開始這裡只畫第一群，理由寫的是「兩群的框疊在同一張
    (x, y) 上，後畫的會蓋掉先畫的」—— 而**那個問題只在「一群鋪一次」的做法
    下才存在**。PEAR 的 `heat_cells(self._rois, …)` 吃的是全部 ROI：中線由
    全部的框一起決定，於是每一格各佔各的位置，根本不會互相蓋。我先製造了一
    個問題，再用「只畫第一群」去繞開它。

    由此而來的一句話：**色階跨區域共用**（PEAR 的 vmin/vmax 也是取全部）。
    這一張問的是「這一片場上哪裡不一樣」，而那個問題的座標是位置、不是區域
    ——每個區域各自縮放的話，兩塊一樣紅的地方其實不一樣亮。要比區域**之間**
    請看盒鬚圖，那張的 X 軸就是區域。
    """
    groups = [g for g in series.get("groups") or [] if g.get("values")]
    if not groups:
        return _empty(width, height, "no boxes to plot")

    pad_l, pad_r = 46, 84            # 右邊留給色條
    pad_t = 30 if style.get("title") else 12
    pad_b = 44
    pw = max(60, width - pad_l - pad_r)
    ph = max(60, height - pad_t - pad_b)
    t_size, t_weight, t_ink = _text_attrs(style, "tick", _TEXT)
    o = _head(width, height, str(style.get("title") or ""))

    if bool(style.get("equal_cells", True)):
        xc, yc, slots, (lo, hi) = heat_lattice(series, style)
        if not slots:
            return _empty(width, height, "box positions do not line up")
        ox, oy, dw, dh = float(pad_l), float(pad_t), float(pw), float(ph)
        cw, chh = dw / len(xc), dh / len(yc)
        for i, j, fill, v in slots:
            x, y = ox + cw * i, oy + chh * j
            o.append("<rect x='%.2f' y='%.2f' width='%.2f' height='%.2f' "
                     "fill='%s' stroke='#000000' stroke-opacity='0.18' "
                     "stroke-width='0.8'/>" % (x, y, cw, chh, fill))
            if bool(style.get("map_values")) and cw >= 34 and chh >= 14:
                # 放得下才印（PEAR 同款）—— 印一半的數字比不印糟。
                o.append("<text x='%.2f' y='%.2f' font-size='%g' "
                         "font-weight='700' fill='%s' text-anchor='middle'>"
                         "%s</text>"
                         % (x + cw / 2, y + chh / 2 + t_size * 0.35,
                            min(t_size, chh * 0.5),
                            "#ffffff" if _is_dark(fill) else "#1f2430",
                            _esc(_fmt(v))))
        # 軸上仍然標著每一欄／列**代表的位置**（槽位不是線性軸）
        _slot_labels(o, xc, ox, cw, pad_t + ph, style, horizontal=True)
        _slot_labels(o, yc, oy, chh, pad_l, style, horizontal=False)
    else:
        rects = [tuple(r) for g in groups for r in (g.get("rects") or ())]
        cells, colours, (lo, hi) = heat_tiles(series, style)
        if not cells:
            return _empty(width, height, "box positions do not line up")
        xs = [c[0] for c in cells] + [c[2] for c in cells]
        ys = [c[1] for c in cells] + [c[3] for c in cells]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        if x1 <= x0 or y1 <= y0:
            return _empty(width, height, "boxes have no extent")
        # **等比例** —— 照實鋪的時候長寬比就是那張圖的一部分（使用者是拿它
        # 去對真實影像的）。格子版刻意不保（見 `heat_lattice`）。
        scale = min(pw / (x1 - x0), ph / (y1 - y0))
        dw, dh = (x1 - x0) * scale, (y1 - y0) * scale
        ox = pad_l + (pw - dw) / 2.0
        oy = pad_t + (ph - dh) / 2.0
        vals = [v for g in groups for v in (g.get("values") or ())]
        for (cx0, cy0, cx1, cy1), fill, v in zip(cells, colours, vals):
            x, y = ox + (cx0 - x0) * scale, oy + (cy0 - y0) * scale
            cw = max(0.5, (cx1 - cx0) * scale)
            chh = max(0.5, (cy1 - cy0) * scale)
            o.append("<rect x='%.2f' y='%.2f' width='%.2f' height='%.2f' "
                     "fill='%s' stroke='none'/>" % (x, y, cw, chh, fill))
            # 印值的規矩兩種鋪法**一字不差**（PEAR 兩個分支也是同一套）——
            # 一種印一種不印的話，那一格會變成「有時候有反應」。
            if bool(style.get("map_values")) and cw >= 34 and chh >= 14:
                o.append("<text x='%.2f' y='%.2f' font-size='%g' "
                         "font-weight='700' fill='%s' text-anchor='middle'>"
                         "%s</text>"
                         % (x + cw / 2, y + chh / 2 + t_size * 0.35,
                            min(t_size, chh * 0.5),
                            "#ffffff" if _is_dark(fill) else "#1f2430",
                            _esc(_fmt(float(v)))))
        if style.get("points", True):
            # 量到的那個框仍然描出來 —— 「這一塊的顏色是從哪一格量來的」
            for (rx, ry, rw, rh) in rects:
                o.append("<rect x='%.2f' y='%.2f' width='%.2f' height='%.2f' "
                         "fill='none' stroke='#ffffff' stroke-opacity='0.55' "
                         "stroke-width='0.8'/>"
                         % (ox + (rx - x0) * scale, oy + (ry - y0) * scale,
                            rw * scale, rh * scale))
    _frame(o, ox, oy, dw, dh)

    # ---- 色條 -------------------------------------------------------------
    bx, bw_ = width - pad_r + 16, 14
    ink = heat_hex if str(style.get("ramp", "")) == "rainbow" else seq_hex
    for i in range(64):
        t = 1.0 - i / 63.0
        o.append("<rect x='%.1f' y='%.2f' width='%d' height='%.2f' fill='%s' "
                 "stroke='none'/>"
                 % (bx, pad_t + i * ph / 64.0, bw_, ph / 64.0 + 0.6, ink(t)))
    o.append("<rect x='%.1f' y='%.1f' width='%d' height='%.1f' fill='none' "
             "stroke='%s' stroke-width='1'/>" % (bx, pad_t, bw_, ph, _AXIS))
    for t, ty in ((hi, pad_t + 4), (lo, pad_t + ph)):
        o.append("<text x='%.1f' y='%.1f' font-size='%g' font-weight='%s' "
                 "fill='%s'>%s</text>"
                 % (bx + bw_ + 4, ty, t_size, t_weight, t_ink, _esc(_fmt(t))))
    if style.get("hlock"):
        o.append("<text x='%.1f' y='%.1f' font-size='9' fill='%s'>locked</text>"
                 % (bx + bw_ + 4, pad_t + ph / 2, _MUTED))
    # 底下那一行說出**這張圖畫的是誰** —— 一起鋪之後那不再是一個名字。
    who = ", ".join(str(g.get("name") or "region") for g in groups)
    o.append("<text x='%.1f' y='%d' font-size='%g' font-weight='%s' "
             "fill='%s'>%s - %s</text>"
             % (pad_l, height - 10, t_size, t_weight, _MUTED,
                _esc(who), _esc(str(series.get("metric") or "value"))))
    if len(groups) > 1:
        # **色階是共用的**，而那件事圖上要看得到（見 docstring）——
        # 不然兩個區域的紅會被讀成「各自最紅」。
        o.append("<text x='%d' y='%d' font-size='10' fill='%s' "
                 "text-anchor='end'>one colour scale across "
                 "%d regions</text>"
                 % (width - pad_r, height - 10, _MUTED, len(groups)))
    o.append("</svg>")
    return "".join(o)


# --------------------------------------------------------------------------- #
# 對外
# --------------------------------------------------------------------------- #
def build_chart_svg(series: Dict[str, Any], kind: str = CHART_BOX,
                    style: Optional[Dict[str, Any]] = None,
                    width: int = 640, height: int = 420,
                    frame: Optional[Any] = None,
                    spec: Optional[Any] = None) -> str:
    """一張圖。``kind`` 見 :data:`CHARTS`；認不得的字當 ``box``。

    ``style`` 的每一格都是**選填的覆寫**（空的就自己決定）::

        title    圖上方那一行字
        xlabel   X 軸的名字（空的用這種圖的預設）
        ylabel   Y 軸的名字
        vlock    (lo, hi) —— **鎖住值那一軸**。見 `_span` 的說明
        plock    (lo, hi) —— 鎖住位置那一軸（profile）
        hlock    (lo, hi) —— 鎖住顏色那一軸（map）
        axis     profile 沿 "x" 還是 "y"
        points   要不要畫每一格框（框很多時關掉）
        whiskers 盒鬚圖要不要畫鬚
        bins     直方圖幾個柱
        percent  直方圖畫比例而不是次數
        xticks / yticks   幾個刻度
    """
    st = dict(style or {})
    k = str(kind or CHART_BOX)
    # **夾住尺寸，不夾內容**（見 `MIN_WIDTH` 的警告）。呼叫端把回來的圖
    # 等比例縮進它那一格 —— 縮小的圖讀得完，切掉的圖讀不完而且看不出來。
    width = max(int(width), MIN_WIDTH)
    height = max(int(height), MIN_HEIGHT)
    if k == CHART_HIST:
        return _svg_histogram(series, st, width, height)
    if k == CHART_PROFILE:
        return _svg_profile(series, st, width, height)
    if k == CHART_MAP:
        return _svg_map(series, st, width, height)
    if k == CHART_CUSTOM:
        # ⚠ **這一張吃的是長表，不是 series**（F88 第二刀）—— 兩條軸是使用者
        # 自己挑的欄，而 series 只裝得下「一個統計量 ＋ 位置」。
        #
        # 走**同一個入口**是刻意的：呼叫端（卡片、圖的視窗、設定編輯器的預覽）
        # 只要問這一支就好，「哪一種圖要哪一種資料」是這裡的事。少一份 frame
        # 就說出來，不要畫一張空白。
        from .chart_draw import draw as _draw

        if frame is None or not len(frame):
            return _empty(width, height, "no boxes to plot")
        return _draw(frame, spec, st, width, height)
    # 盒鬚圖走 `boxplot` 那一支（同一組 Tukey 鬚，見檔頭）
    groups = [g for g in series.get("groups") or [] if g.get("values")]
    if not groups:
        return _empty(width, height, "no boxes to plot")
    return build_boxplot_svg(
        [{"name": g["name"], "values": g["values"], "colour": g["colour"]}
         for g in groups],
        title=str(st.get("title") or ""),
        subtitle=str(st.get("subtitle") or ""),
        width=width, height=height, style=st)


def build_charts_page(series: Dict[str, Any], kinds: Sequence[str],
                      title: str, subtitle: str = "",
                      style: Optional[Dict[str, Any]] = None,
                      frame: Optional[Any] = None,
                      spec: Optional[Any] = None) -> str:
    """幾張圖一頁（由上往下）—— 走 `boxplot.build_boxplot_page` 的版型。

    版型共用而不是抄一份：兩頁在同一份報表資料夾裡並排，字級不一樣的那天
    沒有人會知道為什麼。
    """
    from .boxplot import build_boxplot_page

    st = dict(style or {})
    charts = []
    for k in (kinds or CHARTS):
        kk = str(k)
        if kk not in CHARTS:
            continue
        one = dict(st)
        one.setdefault("title", CHART_LABELS.get(kk, kk))
        charts.append({"name": CHART_LABELS.get(kk, kk),
                       "svg": build_chart_svg(series, kk, one,
                                              frame=frame, spec=spec)})
    return build_boxplot_page(charts, title, subtitle=subtitle)


# --------------------------------------------------------------------------- #
# 數字 —— **那一頁本來就該是「一顆的答案」**（F86）
# --------------------------------------------------------------------------- #
#: 摘要表上的欄：``(特徵後綴, 表頭, 單位)``。
#:
#: ⚠ **順序就是使用者讀的順序**：先「散多開」再「往哪邊斜」，最後才是「量了
#: 幾格」（那是信不信得過的旁證，不是答案）。
UNIF_COLUMNS: Tuple[Tuple[str, str, str], ...] = (
    ("cv_pct", "CV", "%"),
    ("range", "range", "gray"),
    ("range_pct", "range", "%"),
    ("slope_x", "left \u2192 right", "/100 px"),
    ("slope_y", "top \u2192 bottom", "/100 px"),
)


def summary_rows(series: Dict[str, Any],
                 features: Optional[Dict[str, Any]] = None
                 ) -> List[Dict[str, Any]]:
    """圖上方那張小表 —— 一個區域一列。

    ⚠ **數字從 `features` 拿，不在這裡重算。** 重算的那一份會漂：同一顆
    defect 的 CSV 與報告頁上會出現兩個 CV%，而沒有人看得出哪一個是對的。
    這一支只做「找到那一格叫什麼名字」這件事。

    ``features`` 沒給（或那一格不在裡面）就留 ``None`` —— 表上印 ``-``，
    而不是一個算出來的替身。
    """
    feats = dict(features or {})
    metric = str(series.get("metric") or "")
    out: List[Dict[str, Any]] = []
    for g in series.get("groups") or []:
        name = str(g.get("name") or "")
        cells: Dict[str, Any] = {}
        for key, _head, _unit in UNIF_COLUMNS:
            # 只接一個區域、一條流時前綴是空的 —— 兩種都找一次
            # （`MultiSourceStep` 的既有文法，見 `steps/_util.stream_prefix`）。
            for cand in ("%s_%s_%s" % (name, metric, key),
                         "%s_%s" % (metric, key)):
                if cand in feats:
                    cells[key] = feats[cand]
                    break
        out.append({"name": name, "metric": metric,
                    "boxes": len(g.get("values") or ()), "cells": cells})
    return out


def _num(value: Any) -> str:
    return _MISSING if value is None else _fmt(float(value))


def summary_columns(rows: Sequence[Dict[str, Any]]
                    ) -> Tuple[Tuple[str, str, str], ...]:
    """這張表要印哪幾欄（F117 F8）—— **一格數字都沒有的欄不印**。

    走查記的是「摘要表 `range` 為 `-`」。那兩欄之所以空著，是因為 GLV 卡的
    「How even are the boxes」沒有勾 range —— 也就是**使用者已經回答過了**。
    印一欄他答過「不要」的問題，等於把那個答案當成一個沒填的空格。

    ⚠ **有一格有值就整欄留著。** 那時候的 `-` 是真的資訊：別的區域量得到，
    這一個量不到。兩種 `-` 長得一樣，而意思差很遠 —— 分得開它們的唯一辦法
    就是「整欄都沒有」才拿掉。
    """
    keep = []
    for col in UNIF_COLUMNS:
        if any(r.get("cells", {}).get(col[0]) is not None for r in rows):
            keep.append(col)
    return tuple(keep)


def build_summary_html(rows: Sequence[Dict[str, Any]]) -> str:
    """:func:`summary_rows` → 一小塊 HTML（沒有列就回空字串）。"""
    if not rows:
        return ""
    columns = summary_columns(rows)
    head = "".join("<th>%s<span>%s</span></th>" % (_esc(h), _esc(u))
                   for _k, h, u in columns)
    body = []
    for r in rows:
        cells = "".join("<td>%s</td>" % _esc(_num(r["cells"].get(k)))
                        for k, _h, _u in columns)
        body.append("<tr><th class='r'>%s</th><td class='m'>%s</td>%s"
                    "<td class='m'>%d</td></tr>"
                    % (_esc(r["name"]), _esc(r["metric"]), cells,
                       int(r["boxes"])))
    return ("<table class='unif'><thead><tr><th>region</th><th>number</th>%s"
            "<th>boxes</th></tr></thead><tbody>%s</tbody></table>"
            % (head, "".join(body)))


#: 摘要表的樣式。**跟 `boxplot.build_boxplot_page` 的版型是同一頁**，所以只補
#: 這張表要的那幾條，不重寫整份 CSS。
SUMMARY_CSS = (
    "table.unif{border-collapse:collapse;margin:0 0 22px;font-size:12px}"
    "table.unif th,table.unif td{border:1px solid #e2e5ea;padding:4px 10px;"
    "text-align:right}"
    "table.unif thead th{background:#f6f7f9;color:#555;font-weight:600}"
    "table.unif thead th span{display:block;font-weight:400;color:#8a94a6;"
    "font-size:10px}"
    "table.unif th.r{text-align:left}"
    "table.unif td.m{color:#666;text-align:left;font-family:monospace}")


def build_index_page(entries: Sequence[Dict[str, Any]], title: str,
                     subtitle: str = "") -> str:
    """好幾顆的入口（F86）。

    ``entries`` 每一項是 ``{"name", "href", "rows"}``（``rows`` 是
    :func:`summary_rows` 的產物）。

    ⚠ **一顆的時候不要寫這一頁**：多一個檔只是多一層要點進去的東西，而
    那一顆的頁面本來就是答案。判斷在呼叫端 —— 這一支只負責畫。
    """
    o = ["<!doctype html><html><head><meta charset='utf-8'>",
         "<title>%s</title>" % _esc(title),
         "<style>",
         "body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222}",
         "h1{font-size:18px;margin:0 0 4px}",
         ".sub{color:#666;font-size:12px;margin:0 0 18px}",
         "a{color:#2b6cb0;text-decoration:none}a:hover{text-decoration:underline}",
         SUMMARY_CSS,
         "table.unif td.m{font-family:inherit}",
         "</style></head><body>",
         "<h1>%s</h1>" % _esc(title)]
    if subtitle:
        o.append("<p class='sub'>%s</p>" % _esc(subtitle))
    if not entries:
        o.append("<p class='sub'>Nothing was drawn.</p>")
    # **整份都沒量到的欄不印**（F117 F8）—— 同 `build_summary_html`，而這裡
    # 問的是「整批」：一顆都沒有那一欄的話，索引頁上那一欄整條都是 `-`。
    columns = summary_columns([r for e in entries for r in (e.get("rows") or [])])
    head = "".join("<th>%s<span>%s</span></th>" % (_esc(h), _esc(u))
                   for _k, h, u in columns)
    o.append("<table class='unif'><thead><tr><th>defect</th><th>region</th>"
             "%s<th>boxes</th></tr></thead><tbody>" % head)
    for e in entries:
        rows = list(e.get("rows") or [])
        span = max(1, len(rows))
        link = "<a href='%s'>%s</a>" % (_esc(e.get("href", "")),
                                        _esc(e.get("name", "")))
        if not rows:
            o.append("<tr><th class='r'>%s</th><td class='m'>%s</td>%s</tr>"
                     % (link, _MISSING,
                        "<td>%s</td>" % _MISSING * (len(columns) + 1)))
            continue
        for i, r in enumerate(rows):
            cells = "".join("<td>%s</td>" % _esc(_num(r["cells"].get(k)))
                            for k, _h, _u in columns)
            first = ("<th class='r' rowspan='%d'>%s</th>" % (span, link)
                     if i == 0 else "")
            o.append("<tr>%s<td class='m'>%s</td>%s<td>%d</td></tr>"
                     % (first, _esc(r["name"]), cells, int(r["boxes"])))
    o.append("</tbody></table></body></html>")
    return "\n".join(o)

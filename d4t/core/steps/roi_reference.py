# d4t step-card library — authored 2026-08-18 (F11 Region-3);
# 2026-08-25 (F29) 收成一張有 method 的卡。
"""roi_reference —— **把圖上「應該長得一樣」的地方全部標出來**。

一張卡，兩種找法，地位相同
--------------------------
使用者 2026-08-25：「golden cell 跟 GDS 同樣重要而且他們要能在同張 card 裡
（都是接區域 ROI 卡）」。

| method | 靠什麼 | 前提 |
|---|---|---|
| ``repeating cells`` | 影像自己的**週期**（`algo/period` ＋ `algo/golden`）| layout 會重複 |
| ``layout layers`` | GLAS 匯出的 **label map** | 有 GDS 對好位 |

兩個回答的是**同一句話**：「哪些地方應該長得一樣」。所以它們是一張卡的兩個
下拉，不是兩張卡（`CLAUDE.md` §3「同一個家族的做法收成一張卡的 `method`」）——
而這個 repo 已經做過一次一模一樣的事：``roi_compare`` → ``glv_stats`` ＋
``method="compare"``（`recipe.py::_migrate_roi_compare_into_glv_stats`）。

標出來之後，**不一樣的那一塊就浮出來**：`pick` 挑一塊當 ``<name>_center``，
其餘的自動變成 ``<name>_others``（＝**參照**），下游
``glv_stats(roi=..._center, reference="the other regions")`` 就是區域級的
detect。不需要任何新卡。

⚠ **``repeating cells`` 不是把 `pattern_ref` 請回來。** 那張卡（Compare 段，
合成一張參照影像）2026-08-20 被刪掉，使用者：「完全沒用，請直接拿掉」。
這裡走的是**區域**那條路：不合成任何影像、不做相減，只是把晶格切成一塊一塊的
具名區域。差別是實質的 —— 合成參照要求每一格逐像素對齊（對不齊就吐一張糊的
ref，而畫面上看不出來），比統計量不要求。

``layout layers``：不搜尋、不對位
---------------------------------
GLAS 產的 mask 已經是對位完的（使用者原話「我們產的那些 png mask，都是在已經
對位完 no shift 情況下產生」）。所以這一支沒有搜尋半徑、沒有分數門檻 ——
它把 label 圖上的形狀原樣搬成區域。使用時機通常是**非週期性重複區域**，
也就是另一支的前提不成立的地方。

``<name>_center`` 的定義換了一種說法（F29）
-------------------------------------------
這張卡以前**刻意不吐** ``_center`` / ``_others``，理由是：另外兩張卡的
``_center`` 是「缺陷所在的那一份」，而那是**幾何保證**的（patch 以缺陷為中心
裁切）；這條路上缺陷不保證在正中央（RSEM 大圖），硬給的話使用者會照 Template
的直覺去用它，而畫面上不會說。

**那個反對意見是對的，而且沒有被推翻 —— 被推翻的是「所以不能有 ``_center``」。**
`pick="strongest"`（訊號最強的那一塊，`_util.pick_defect_box`）不假設缺陷在
中央：**它去找**。所以這條路的用法是 ``strongest``，而 ``centre`` 那個選項
在大圖上仍然只是「離正中心最近的那一塊」—— 那句話在 help 裡逐字寫著。

一層 = 好幾個矩形，而數量比另外兩張卡大一個數量級
------------------------------------------------
幾何在 ``algo/mask.py``（那裡有實測表）。重點：一層**精確**拆出來的矩形數，
實際範圍是幾十到約五千 —— 而既有 Region 卡的 ``max_boxes`` 預設是 **64**，
那是為「重複結構的幾份」設計的，用在這裡會**安靜地砍掉 95%**。

使用者：「max boxes 理想上應該會很多，原因是處理的會是 **RSEM images**
（不是之前的 patch）等級。」對 —— 而「很多」量出來是這樣（1000×1000）：

| 形狀 | pieces | rectangles |
|---|---|---|
| 密集 line/space | 39 | 39 |
| 同上，被另一層橫向切碎 | 975 | 975 |
| 45° 斜帶（`fillPoly` 的 1px 階梯邊）| 10 | **5 295** |
| contact 陣列 6×6/14 | 5 184 | 5 184 |

下游的成本（同一天量的，**每張量測卡每顆各一次**）：
N=1 000 約 3 ms、N=10 000 約 60 ms、N=50 000 約 280 ms、N=200 000 約 1 s。
所以預設 **8192**（蓋得住實測的最壞 5 295 還有餘裕），上限 **65536**
（再上去就是每顆每卡 0.3 s 起跳，400 顆 × 幾張卡會變成用分鐘算的）。

**砍到上限一定要講出來**（``<name>_clipped``）—— 一個少掉一半框的區域仍然
算得出一個很正常的灰階值。

⚠ 多出 ``_others`` 的代價量過了（2026-08-25，1000×1000）：
``set_region_family`` 本身 N=1000 約 8 ms、N=5000 約 36 ms、N=20000 約 157 ms
—— 在實測最壞的 5 295 上是 **36 ms／顆**，只有下游 `glv_stats` 在同一組框上
（105 ms）的三分之一。所以**沒有加抽樣**：抽樣要多一個發明出來的數字，
而它換到的時間比使用者自己接的那張量測卡還少。
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Tuple

import numpy as np

from ..algo import golden as algo_golden
from ..algo import mask as algo_mask
from ..algo import period as algo_period
from ..ingest.glas_export import SIDECAR_LABEL
from ..pipeline.channels import ChannelMapError, parse_channel_map
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_REGION, ParamSpec, Step, StepError, register_step,
    show_when_conditions,
)
from ._util import (
    FEATURE_PREFIX_PATTERN, drop_edge_boxes, drop_edge_specs, ensure_gray,
    output_prefix_spec, pick_defect_box, pick_rule_specs, prefix_features,
    prefix_names, region_family, region_fact_names, region_facts,
    require_image, set_region_family,
    LIMIT_MAX_BOXES,
)

#: ``method`` 的兩個值 —— **地位相同**，順序就是下拉由上到下。
#:
#: 值本身會進 recipe JSON，所以它們是白話短句而不是縮寫（同 `glv_stats` 的
#: ``reference``：``"another region"`` / ``"the other regions"``）。
METHOD_CELLS = "repeating cells"
METHOD_GDS = "layout layers"
METHOD_PROFILE = "stripes in the image"
METHOD_TEMPLATE = "a cell I mark myself"
METHODS = (METHOD_CELLS, METHOD_GDS, METHOD_PROFILE, METHOD_TEMPLATE)

#: 哪一支的程式碼在哪個模組（F30 把四張卡收成一張）。
#:
#: ⚠ **run 的內容沒有搬家。** `roi_cross` / `roi_template` 那兩個檔案還在，
#: 只是不再各自 `@register_step` —— 它們的 ``key`` 改成 ``roi_reference``，
#: 所以錯誤訊息上使用者看到的是他真的放的那張卡。這樣做的理由是代價：把
#: 1100 行演算法搬進來只會讓這個檔案變成 1700 行，而「哪一支怎麼算」本來就
#: 各自看得懂 —— 要合的是**使用者看到的那張卡**，不是檔案。
_IMPL_MODULE = {
    METHOD_PROFILE: ("roi_cross", "RoiCrossStep"),
    METHOD_TEMPLATE: ("roi_template", "RoiTemplateStep"),
}


def _method_of(params: Dict[str, Any]) -> str:
    m = str((params or {}).get("method", "") or "").strip()
    return m if m in METHODS else METHOD_CELLS


def _impl(method: str):
    """這個 method 的實作類別（``None`` = 就在這個檔案裡）。"""
    where = _IMPL_MODULE.get(method)
    if where is None:
        return None
    import importlib
    mod = importlib.import_module("." + where[0], __package__)
    return getattr(mod, where[1])


#: 折進來的那兩支**不再自己宣告**的參數 —— 它們在這張卡上是共用的一格。
#:
#: 為什麼要一張排除表而不是「照抄全部」：``source`` / ``pick`` / ``max_boxes``
#: 那幾格在三支上是同一句話，各留一份的話**同一個名字會有三個 ParamSpec**，
#: 而 `validate_params` 只看得到最後一個 —— 於是使用者在畫面上調的是 A，
#: 引擎讀的是 B，兩者的預設值還不一樣。
_SHARED_PARAMS = ("source", "pick", "pick_source", "drop_edge", "edge_margin",
                  "output_prefix", "max_boxes", "roi_out")


def _params_for(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """交給某一支實作的那一份參數 —— **只留它宣告的鍵，預設值取自這張卡**。

    兩件事缺一不可：

    * **只留它認得的** —— `validate_params` 對未知的鍵是**報錯**（不是忽略），
      而這張卡的 ``params`` 是四支的聯集。
    * **預設值取自這張卡** —— ``source`` / ``roi_out`` / ``max_boxes`` 那幾格
      合併之後只有一份，而實作那一邊還留著自己的舊預設（``ref`` / ``cross`` /
      64）。不覆蓋的話，使用者**沒有動過**那一格時畫面上顯示這張卡的預設、
      引擎讀到的卻是實作的舊預設 —— 而那個差別在畫面上看不出來。
    """
    impl = _impl(method)
    given = dict(params or {})
    if impl is None:
        return given
    mine = {spec.name: spec for spec in RoiReferenceStep.params}
    out: Dict[str, Any] = {}
    for spec in impl.params:
        if spec.name in given:
            out[spec.name] = given[spec.name]
        elif spec.name in mine:
            out[spec.name] = mine[spec.name].default
    return out


def _folded(method: str) -> List[ParamSpec]:
    """把一支實作自己的參數搬過來，並且**加上「method 要是它」這個條件**。

    `show_when` 因此可能有兩條（F30 為此讓它接受一串條件）：``vertical_width``
    要的是「method 是 profile」**而且**「directions 含直的」。
    """
    impl = _impl(method)
    if impl is None:
        return []
    out: List[ParamSpec] = []
    for spec in impl.params:
        if spec.name in _SHARED_PARAMS:
            continue
        mine = ("method", (method,))
        rest = show_when_conditions(spec.show_when)
        out.append(replace(spec, show_when=tuple([mine] + rest)))
    return out

#: 這張卡**多**寫的那一個（`_util.REGION_FACTS` 的五個之外）。
#:
#: ``pieces`` 是連通元件的個數，而 ``boxes`` 是矩形分解出幾個 —— 只有走 label
#: map 這一條路的卡分得出這兩者（另外兩張卡的框本來就是一塊一個）。兩者差很大
#: 的意思是「這一層正被後面畫的層切碎」，而那是使用者要看得到的事實
#: （真實資料上兩者相等，見 `docs/GLAS-INTERFACE.md` §3.6）。
_EXTRA_REGION_FEATURES = ["pieces"]

#: ``layout layers`` 那一支自己的（跟區域無關）。
_GDS_FEATURES = ["layout_ok", "layout_layers"]

#: ``repeating cells`` 那一支自己的。**每一個都是「卡片自動決定了什麼」**
#: （F19 的規矩）：
#:
#: * ``cells_px`` / ``cells_py`` —— 量出來的週期（沒有週期的那一軸 = 整張圖的
#:   邊長，因為那一軸的「一格」就是整條）。整批應該收在一起；散開 = 週期估測
#:   在逐顆給不同的答案，而每一顆都吐得出正常的灰階值。
#: * ``cells_n`` —— 切出幾塊。1 表示**沒有基準**（``_others`` 不存在）。
#: * ``cells_confidence`` —— 兩軸取小的那一個（**0..1，跟
#:   ``Ignore repeats weaker than`` 那一格同一個刻度**）。低的時候框還在、
#:   而「憑什麼在那裡」是猜的。
#: * ``cells_axes`` —— 幾個軸有週期（2 = 晶格、1 = 條紋、0 = 拒絕）。
_CELL_FEATURES = ["cells_px", "cells_py", "cells_n", "cells_confidence",
                  "cells_axes"]

#: 兩支共用的一個（跟另外兩張 ROI 卡逐字同名）：**有沒有真的用訊號挑**。
#: 接不到 ``Judge on`` 就退回「離中心最近」，而安靜地照做是最糟的
#: （見 `_util.pick_defect_box`）。
_PICK_FEATURE = "pick_by_signal"

#: ``max_boxes`` 的預設 —— 這個數字是量出來的，理由見模組說明。
#: 上限（:data:`_util.LIMIT_MAX_BOXES`）三支共用，見那裡的說明。
DEFAULT_MAX_BOXES = 8192


def _layers_of(params: Dict[str, Any]) -> List[Tuple[int, str]]:
    """``layers`` 參數 → ``[(label id, 區域名), …]``。打到一半不准拋。"""
    try:
        return parse_channel_map(params.get("layers", ""), noun="layer")
    except ChannelMapError:
        return []


#: ``roi_out`` 沒填時的名字。**中性**，因為 ``repeating cells`` 與
#: ``stripes in the image`` 共用這一格 —— 叫 ``cell`` 對條紋是錯的、叫
#: ``cross`` 對晶格是錯的，而舊 recipe 的名字由遷移逐字寫進參數裡。
DEFAULT_REGION_NAME = "region"


def _cell_name(params: Dict[str, Any]) -> str:
    return (str((params or {}).get("roi_out", "") or DEFAULT_REGION_NAME)
            .strip() or DEFAULT_REGION_NAME)


@register_step
class RoiReferenceStep(Step):
    """把「應該長得一樣」的地方全部標出來 —— 重複的晶格，或 GDS 的一層。"""

    key = "roi_reference"
    label = "Reference regions"
    category = CATEGORY_ALGO
    group = GROUP_REGION
    help = ("Mark every place on the image that should look the same, so the "
            "one that does not stand out. Four ways to find them, and they "
            "are equally good - pick whichever your sample gives you. Either "
            "way you get the whole set, the one the defect is in, and every "
            "other one as the baseline to compare it against.")
    params = [
        ParamSpec(
            name="method", type="choice", default=METHOD_CELLS,
            choices=list(METHODS), section="1 · How to find them",
            label="Find them by",
            choice_help={
                METHOD_CELLS: "The repeating pattern in the image itself - "
                              "the card measures the period and cuts the "
                              "image into cells. Nothing else to load.",
                METHOD_GDS: "One layer of the layout, from a GDS export. Use "
                            "this where the pattern does not repeat, which is "
                            "where there is nothing to lock onto.",
                METHOD_PROFILE: "The stripes in the image - the card finds "
                                "them and puts a box on every one, so the "
                                "boxes follow the pattern instead of sitting "
                                "at fixed spots on the screen.",
                METHOD_TEMPLATE: "You mark the regions once on one cell of "
                                 "the layout, and the card puts them in the "
                                 "right place on every image. It works both "
                                 "ways round: on a small patch, where one "
                                 "cell is bigger than the patch and you get "
                                 "the one copy this defect can see, and on a "
                                 "full-size SEM image, where the cell is much "
                                 "smaller and every copy across the image "
                                 "gets marked.",
            },
            help=("Both answer the same question - which places should look "
                  "the same. Pick whichever your sample gives you: a "
                  "repeating layout needs nothing extra, a one-off layout "
                  "needs the export."),
        ),
        ParamSpec(
            name="source", type="image_key", direction="in",
            default="test", section="1 · How to find them", label="Image",
            show_when=("method", (METHOD_CELLS, METHOD_PROFILE,
                                  METHOD_TEMPLATE)),
            help=("Which image stream this card works on - drag a line from "
                  "the card that produces it. The pattern has to still be in "
                  "it, so a difference image is the wrong one to point at. "
                  "For the repeating cells, normally the test image. For "
                  "stripes and for a cell you mark yourself, ref is better "
                  "where you have a test/ref pair: it has no defect on it, so "
                  "nothing interferes, and the pair is already aligned so the "
                  "answer applies to test as well. With a single full-size "
                  "image there is only one stream, and the regions are "
                  "repeated across the whole of it."),
        ),
        ParamSpec(
            name="label_source", type="image_key", direction="in",
            default=SIDECAR_LABEL, section="1 · How to find them",
            label="Layout labels", show_when=("method", (METHOD_GDS,)),
            help=("The label map stream, from the “Load layout labels” card. "
                  "Every pixel value in it is a layer number - it is not a "
                  "picture of the wafer."),
        ),
        ParamSpec(
            name="roi_out", type="str", default="region",
            section="2 · Which layers, and what to call them",
            label="Call the regions", pattern=FEATURE_PREFIX_PATTERN,
            pattern_help=("use letters, digits and underscores only, and do "
                          "not start with a digit"),
            show_when=("method", (METHOD_CELLS, METHOD_PROFILE)),
            help=("What to call this set of regions. The name becomes the "
                  "prefix on every number measured in it, and you point the "
                  "measure cards at <name>_center (the one the defect is in) "
                  "and <name>_others (all the rest, your baseline)."),
        ),
        ParamSpec(
            name="min_period", type="int", default=0, min=0, max=4096,
            unit="px", section="2 · Which layers, and what to call them",
            label="Cells are at least", advanced=True,
            show_when=("method", (METHOD_CELLS,)),
            help=("Smallest repeat to look for. Zero lets the card pick a "
                  "range from the image size. Set it when the card locks onto "
                  "something finer than the structure you mean - the value it "
                  "actually used comes out as cells_px / cells_py."),
        ),
        ParamSpec(
            name="max_period", type="int", default=0, min=0, max=4096,
            unit="px", section="2 · Which layers, and what to call them",
            label="Cells are at most", advanced=True,
            show_when=("method", (METHOD_CELLS,)),
            help=("Largest repeat to look for. Zero lets the card pick a "
                  "range from the image size."),
        ),
        ParamSpec(
            name="min_repeat_strength", type="float", default=0.18, min=0.0,
            max=0.95, section="2 · Which layers, and what to call them",
            label="Ignore repeats weaker than",
            show_when=("method", (METHOD_CELLS,)),
            help=("How clear the repeat has to be before the card believes "
                  "it, from 0 (anything) to 0.95 (only very regular "
                  "patterns). Below it the card stops and says so rather than "
                  "cutting the image into a grid that means nothing - a made "
                  "up grid still produces a perfectly normal-looking number "
                  "for every defect. What it measured comes out as "
                  "cells_confidence."),
        ),
        ParamSpec(
            name="layers", type="channel_map", default="", row_kind="labels",
            section="2 · Which layers, and what to call them",
            label="Layer number → region name",
            show_when=("method", (METHOD_GDS,)),
            help=("Which layer numbers to turn into regions, and what to call "
                  "each one. The export knows the layout's own names for them "
                  "(things like L17/D0) and Studio fills those in for you - "
                  "but rename them to something you will recognise, because "
                  "the name becomes the prefix on every number measured in "
                  "that region (epi_glv_mean reads better than "
                  "L17_D0_glv_mean). Layers you leave out simply produce no "
                  "region."),
        ),
        ParamSpec(
            name="min_area", type="int", default=0, min=0, max=1_000_000,
            unit="px", section="2 · Which layers, and what to call them",
            label="Ignore pieces smaller than", advanced=True,
            show_when=("method", (METHOD_GDS,)),
            help=("Drop any separate piece of a layer smaller than this many "
                  "pixels. A layer clipped by the edge of the image can leave "
                  "a sliver a few pixels across, and averaging over it gives a "
                  "number that looks fine and means nothing. Zero keeps "
                  "everything. Whole pieces are dropped, never part of one - "
                  "cutting a corner off a region would change the answer "
                  "without changing how it looks."),
        ),
        # **兩支共用**，而且跟另外兩張 Region 卡逐字相同（`_util` 那兩支）——
        # 同一句話在三張卡上不可以各長各的。
        # 折進來的那兩支（F30）—— **參數定義沒有第二份**，是從實作類別上
        # 搬過來再加一條「method 要是它」的條件（見 `_folded`）。
        *_folded(METHOD_PROFILE),
        *_folded(METHOD_TEMPLATE),
        *pick_rule_specs("3 · Which one is the defect in"),
        *drop_edge_specs("4 · Name and limits"),
        output_prefix_spec("gds"),
        ParamSpec(
            name="max_boxes", type="int", default=DEFAULT_MAX_BOXES, min=1,
            max=LIMIT_MAX_BOXES, section="4 · Name and limits", advanced=True,
            label="At most this many boxes",
            help=("A guard, not a setting you should need to touch. A layer is "
                  "stored as its exact set of rectangles, and a real layer on "
                  "a Review SEM image comes to anywhere from a few dozen to "
                  "about five thousand of them - a diagonal edge alone costs "
                  "one rectangle per row. Past about ten thousand every "
                  "measure card starts costing real time on every defect. If "
                  "this limit ever bites, the boxes nearest the middle are "
                  "kept and <name>_clipped is set to 1 for that defect."),
        ),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = list(_CELL_FEATURES) + list(_GDS_FEATURES) + [_PICK_FEATURE]

    # ---- 宣告 ---------------------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        """**只宣告目前這一支真的會讀的那一條**（同 `glv_stats.resolve_reads`）。

        兩支吃的是兩種完全不同的東西 —— 一張晶圓的照片，與一張「每個像素值就是
        層號」的 label map。共用一格的話畫布上那條線會在切換 method 之後指著
        一個意思完全不同的東西，而畫面上不會說。
        """
        method = _method_of(params)
        if method == METHOD_GDS:
            return [str(params.get("label_source", SIDECAR_LABEL))]
        impl = _impl(method)
        if impl is not None:
            return impl.resolve_reads(_params_for(method, params))
        out = [str(params.get("source", "test"))]
        if str(params.get("pick", "")) == "strongest":
            judge = str(params.get("pick_source", "") or "").strip()
            if judge and judge not in out:
                out.append(judge)
        return out

    @classmethod
    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
        """每一個區域都是**三個名字**（``<name>`` / ``_center`` / ``_others``）。

        ⚠ 這張卡以前**只吐 ``<name>``**，而那個決定的理由沒有被推翻 ——
        幾何的 ``_center``（缺陷在正中央）在一張 RSEM 大圖上仍然沒有意義。
        變的是有了 ``pick="strongest"``：它不假設缺陷在哪，**它去找**
        （見模組說明）。
        """
        method = _method_of(params)
        impl = _impl(method)
        if impl is not None:
            return impl.resolve_regions_out(_params_for(method, params))
        if method == METHOD_GDS:
            names = [name for _lid, name in _layers_of(params)]
        else:
            names = [_cell_name(params)]
        out: List[str] = []
        for name in names:
            out.extend(region_family(name))
        return out

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        impl = _impl(_method_of(params))
        if impl is not None:
            return impl.resolve_features(
                _params_for(_method_of(params), params))
        regions = cls.resolve_regions_out(params)
        if _method_of(params) == METHOD_GDS:
            names = list(_GDS_FEATURES) + region_fact_names(regions)
            for _lid, name in _layers_of(params):
                names.extend("%s_%s" % (name, f)
                             for f in _EXTRA_REGION_FEATURES)
        else:
            names = list(_CELL_FEATURES) + region_fact_names(regions)
        names.append(_PICK_FEATURE)
        return prefix_names(params.get("output_prefix", ""), names)

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """還沒填名字 ≠ 參數填錯（空字串是合法的值）。

        ``repeating cells`` 那一支**沒有這種狀態**：它不需要任何外部資料，
        接上一條影像線就跑得動。
        """
        impl = _impl(_method_of(params))
        if impl is not None:
            return impl.configuration_issues(
                _params_for(_method_of(params), params))
        if _method_of(params) != METHOD_GDS:
            return []
        if not _layers_of(params):
            return ["This card has no layers yet. Use “Open GDS export…” on "
                    "the “Load layout labels” card — attaching the export "
                    "fills in the layer numbers and the layout's own names "
                    "for them; then rename them to something you will "
                    "recognise. Or switch “Find them by” to “%s”, which needs "
                    "nothing but the image." % METHOD_CELLS]
        return []

    # ---- 執行 ---------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        method = _method_of(params)
        impl = _impl(method)
        if impl is not None:
            # ⚠ **參數交給實作自己 validate。** 這張卡的 params 是四支的聯集，
            # 而每一支只認得自己那一份 —— 拿這裡 validate 過的 dict 餵過去
            # 會多帶一堆它沒宣告的鍵，而 `validate_params` 對未知的鍵是沉默的
            # （不是報錯），所以那個錯法會一路安靜到跑出數字為止。
            return impl().run(ctx, _params_for(method, params))
        p = self.validate_params(params)
        if method == METHOD_GDS:
            return self._run_gds(ctx, p)
        return self._run_cells(ctx, p)

    # ---- ① 影像自己的重複結構 ----------------------------------------------- #
    def _run_cells(self, ctx: Context, p: Dict[str, Any]) -> Context:
        """量週期 → 定相位 → 把圖切成一塊一塊的 cell，每一塊一個框。

        **不合成任何影像。** 這裡跟被刪掉的 `pattern_ref` 的差別就在這一句：
        那張卡把幾百格疊成一張參照圖再相減（對不齊就吐一張糊的 ref，而畫面上
        看不出來），這裡只是把晶格切成區域，比的是統計量。
        """
        img = require_image(ctx, self.key, str(p["source"]))
        gray = ensure_gray(np.asarray(img))
        if gray.ndim != 2 or min(gray.shape[:2]) < 4:
            raise StepError(
                self.key,
                "this image is %s - too small to find a repeat in."
                % ("x".join(str(v) for v in gray.shape) or "empty"))
        shape = gray.shape[:2]
        h, w = int(shape[0]), int(shape[1])

        res = algo_period.estimate_period(
            gray,
            min_period=int(p["min_period"]) or None,
            max_period=int(p["max_period"]) or None,
            strength_threshold=float(p["min_repeat_strength"]))

        # **誠實閘門。** 量不到週期就停下來說原因，不可以吐一格猜出來的晶格 ——
        # 一個編出來的網格照樣讓每一顆 defect 吐得出很正常的灰階值，而 CSV 上
        # 沒有任何線索。上一次 rsem route 悄悄變成 12/24 就是這個形狀。
        if res.axis_mode == "NONE":
            raise StepError(
                self.key,
                "no repeating pattern was found in “%s” on this defect (%s). "
                "Nothing is guessed here - a made up grid would still produce "
                "a normal-looking number for every defect. Point it at the "
                "image the pattern is actually in, lower “Ignore repeats "
                "weaker than”, or switch “Find them by” to “%s”."
                % (p["source"], "; ".join(res.warnings) or "the projection is "
                   "too flat on both axes", METHOD_GDS))

        # 沒有週期的那一軸**沒有相位可言**，所以那一軸取滿整張圖（同
        # `algo/template.roi_boxes_in_patch` 的 ``periodic`` 那一段）——
        # 硬給一個位置等於憑空捏造資訊。
        px = int(res.px) if res.px else w
        py = int(res.py) if res.py else h
        origin = algo_period.choose_origin(shape, px, py, gray)
        cells = algo_golden.tile_coords(shape, px, py, origin)
        if not cells:
            raise StepError(
                self.key,
                "the repeat measured %dx%d px, which does not fit inside this "
                "%dx%d image even once. Set “Cells are at most” to something "
                "smaller than the image." % (px, py, w, h))

        name = _cell_name(p)
        boxes = [(int(x), int(y), px, py) for x, y in cells]
        cap = int(p["max_boxes"])
        clipped = len(boxes) > cap
        if clipped:
            # 留下離中心最近的那些（同 `algo/mask.decompose` 的規則），
            # **而且要講出來**。
            cx, cy = w / 2.0, h / 2.0
            boxes.sort(key=lambda b: ((b[0] + b[2] / 2.0 - cx) ** 2
                                      + (b[1] + b[3] / 2.0 - cy) ** 2))
            ctx.warn("[%s] the repeat gives %d cells, more than the %d limit; "
                     "kept the ones nearest the middle. Raise “At most this "
                     "many boxes”." % (self.key, len(boxes), cap))
            boxes = boxes[:cap]

        idx, by_signal = self._pick(ctx, p, boxes, shape)
        dropped = 0
        if bool(p["drop_edge"]) and float(p["edge_margin"]) > 0.0:
            boxes, dropped, idx = drop_edge_boxes(
                boxes, shape, float(p["edge_margin"]), idx)
        norm = [(x / w, y / h, bw / w, bh / h) for x, y, bw, bh in boxes]
        set_region_family(ctx, self.key, name, norm, idx, dropped)

        feats = region_facts(ctx, region_family(name), shape, clipped=clipped,
                             edge_dropped=dropped)
        feats.update({
            "cells_px": float(px), "cells_py": float(py),
            "cells_n": float(len(boxes)),
            # ⚠ 報的是 ``peak_strength``（0..1）**不是 ``confidence``（0..100）**：
            # 使用者那一格（``Ignore repeats weaker than``）擋的就是
            # ``peak_strength``，所以它們必須是同一個數字。報另一個刻度的話，
            # 「我設 0.18，它說 85」這句話沒有人解得開。
            #
            # 兩軸取**小**的那一個：一個方向很清楚、另一個方向是猜的，整個晶格
            # 就是猜的。只報大的那個會讓條紋圖看起來像晶格。單軸的時候另一軸
            # 是 0（那一軸根本沒有週期），所以取大的才是那一軸真正的強度。
            "cells_confidence": float(
                min(res.peak_strength_x, res.peak_strength_y)
                if res.axis_mode == "XY"
                else max(res.peak_strength_x, res.peak_strength_y)),
            "cells_axes": 2.0 if res.axis_mode == "XY" else 1.0,
            _PICK_FEATURE: 1.0 if by_signal else 0.0,
        })
        ctx.add_features(prefix_features(p["output_prefix"], feats))

        # 儀表用（跟另外兩張 Region 卡同一個慣例）：**UI 畫的就是引擎算的這一份**。
        ctx.meta.setdefault("reference_cells", {})[str(p["source"])] = {
            "shape": [h, w], "px": px, "py": py,
            "origin": [int(origin[0]), int(origin[1])],
            "axis_mode": res.axis_mode, "n": len(boxes),
            "centre_index": int(idx), "by_signal": bool(by_signal),
            "confidence_x": round(float(res.confidence_x), 4),
            "confidence_y": round(float(res.confidence_y), 4),
            "warnings": list(res.warnings),
        }
        return ctx

    def _pick(self, ctx: Context, p: Dict[str, Any], boxes, shape):
        """哪一塊是缺陷那一塊 —— **三張 Region 卡逐字同一支**。"""
        judge = None
        if str(p["pick"]) == "strongest":
            key = str(p.get("pick_source", "") or "").strip()
            judge = ctx.images.get(key) if key else None
            if judge is None:
                ctx.warn("[%s] nothing is wired into “Judge on”, so the box "
                         "nearest the middle was used instead." % self.key)
        return pick_defect_box(boxes, shape, str(p["pick"]), judge)

    # ---- ② GDS 的一層 ------------------------------------------------------- #
    def _run_gds(self, ctx: Context, p: Dict[str, Any]) -> Context:
        try:
            layers = parse_channel_map(p["layers"], noun="layer")
        except ChannelMapError as e:
            raise StepError(self.key, str(e)) from None
        if not layers:
            raise StepError(
                self.key,
                "no layers are named yet. Use “Open GDS export…” on the "
                "“Load layout labels” card - "
                "attaching the export fills in the layer numbers and names "
                "from it. On the command line, pass --gds <export folder>.")

        img = require_image(ctx, self.key, p["label_source"])
        arr = np.asarray(img)
        if arr.ndim != 2:
            raise StepError(
                self.key,
                "the layout labels have %d channels; each pixel value IS a "
                "layer number, so this must be a single-channel image."
                % arr.shape[2])
        shape = arr.shape[:2]
        present_ids = set(algo_mask.layer_ids(arr))
        cap = int(p["max_boxes"])

        feats: Dict[str, float] = {}
        found = 0
        by_signal_any = False
        for lid, name in layers:
            try:
                rects, piece_of = algo_mask.decompose(arr, lid)
            except algo_mask.MaskError as e:
                raise StepError(self.key, str(e)) from None
            rects, piece_of, dropped = algo_mask.drop_small_pieces(
                rects, piece_of, int(p["min_area"]))
            clipped = len(rects) > cap
            if clipped:
                # 依離中心遠近排序過了（`algo/mask.decompose`），砍掉的是最外圍
                # 的那些。**而且要講出來** —— 少掉一半框的區域仍然算得出一個
                # 很正常的灰階值。
                ctx.warn("[%s] layer %d (%s) has %d boxes, more than the %d "
                         "limit; kept the ones nearest the middle. Raise “At "
                         "most this many boxes”, or raise “Ignore "
                         "pieces smaller than”."
                         % (self.key, lid, name, len(rects), cap))
                rects, piece_of = rects[:cap], piece_of[:cap]
            if dropped:
                ctx.warn("[%s] layer %d (%s): left out %d piece(s) smaller "
                         "than %d px." % (self.key, lid, name, dropped,
                                          int(p["min_area"])))

            edge_dropped = 0
            if rects:
                # **三個名字，不是一個**（F29）。挑哪一塊是缺陷那一塊走的是三張
                # Region 卡共用的那一支 —— 這條路上正解是 ``strongest``
                # （大圖上缺陷不保證在正中央，見模組說明）。
                idx, by_signal = self._pick(ctx, p, rects, shape)
                by_signal_any = by_signal_any or by_signal
                if bool(p["drop_edge"]) and float(p["edge_margin"]) > 0.0:
                    rects, edge_dropped, idx = drop_edge_boxes(
                        rects, shape, float(p["edge_margin"]), idx)
                set_region_family(ctx, self.key, name,
                                  algo_mask.to_normalised(rects, shape),
                                  idx, edge_dropped)
                found += 1
            else:
                # **不退回整張圖。** 那會安靜地量到全部的像素，而那是錯的
                # （同 roi_template 的「區域沒落在這一顆上」）。
                why = ("layer %d is not in this defect's label map at all"
                       % lid) if lid not in present_ids else (
                    "every piece of layer %d was smaller than the %d px "
                    "minimum" % (lid, int(p["min_area"])))
                ctx.warn("[%s] region '%s' is empty on this defect: %s; "
                         "nothing is measured in it here."
                         % (self.key, name, why))
                ctx.meta.setdefault("regions_absent", {})[name] = why

            # 五個數字，跟另外兩張 ROI 卡同一組（`_util.REGION_FACTS`）＋
            # 這張卡多的那一個。**三個名字各報各的** —— 「這一顆上有沒有
            # `epi_others`」跟「有沒有 `epi`」是兩個不同的問題，而下游問的是
            # 它接的那一個。
            feats.update(region_facts(ctx, region_family(name), shape,
                                      clipped=clipped,
                                      edge_dropped=edge_dropped))
            feats["%s_pieces" % name] = float(len(set(piece_of)))

        feats["layout_ok"] = 1.0 if found else 0.0
        feats["layout_layers"] = float(found)
        feats[_PICK_FEATURE] = 1.0 if by_signal_any else 0.0
        ctx.add_features(prefix_features(p["output_prefix"], feats))

        # 儀表用（跟另外兩張 Region 卡同一個慣例）：**UI 畫的就是引擎算的這一份**。
        ctx.meta.setdefault("gds_layers", {})[str(p["label_source"])] = {
            "shape": [int(v) for v in shape],
            "ids_in_image": sorted(present_ids),
            "layers": [{"id": lid, "name": name,
                        "boxes": int(feats["%s_boxes" % name]),
                        "pieces": int(feats["%s_pieces" % name]),
                        "area_px": int(feats["%s_area_px" % name]),
                        "clipped": bool(feats["%s_clipped" % name])}
                       for lid, name in layers],
        }
        return ctx

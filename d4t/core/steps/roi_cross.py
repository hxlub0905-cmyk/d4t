# d4t step-card library — authored 2026-08-13 (F8).
"""roi_cross —— 找出影像自己的條紋，在條紋上放一組框。純規則，不需要外部檔案。

這張卡在解什麼問題
------------------
站點原有兩招定位 ROI，兩招都要外部的東西：GDS（要 .oas）與 Golden Cell
模板（要一張原大圖）。第三招 —— 只看 patch 自己 —— 就是這一張。

**「一個方向還是兩個方向」是使用者回答的第一個問題**（F11 Region-2c）。
這張卡 F8 寫的時候只做兩個方向，因為需求是那個形狀的（直的 Metal Gate ×
橫的 EPI，要量交界落在 EPI 那一側的那幾小塊）。但那是**需求的形狀，不是
演算法的形狀** —— 一張密集 line/space 的 patch 只有一個方向有結構，
而使用者要的框（每一根線上一條滿版的帶子、或每一根線兩側各一條）
這套投影本來就算得出來。原本的卡對那種圖只會回一句「no flat stripes to
lock onto」然後退回整張圖：一件做得到的事被形狀擋住了。

單方向的實作是把另一個方向換成**一根蓋滿整張圖的條紋**
（``algo/grid.open_axis``）—— 交會的幾何一行都不用改，跟滿版帶子交會出來的
正好就是滿版的框。少一條分支就少一種只在單軸時才會發作的 bug。

其餘的演算法與取捨都寫在 ``algo/grid.py`` 的模組說明裡（為什麼晶格要排在條紋
**中心**而不是邊界、為什麼不用週期估測、已知 pitch 能做什麼）。

一個名字，好幾個框
------------------
框的數量隨影像而異，所以這張卡寫的是**多框區域**（``set_roi_boxes``）。
量統計的卡（``glv_stats``）把它當一個像素母體；要幾何的卡指
``<name>_center`` —— 離 patch 正中心最近的那一塊，也就是**缺陷所在的那一塊**；
``<name>_others`` —— 其餘那幾塊，也就是**同一張圖上同材質的基準**
（為什麼要第三個名字、以及為什麼這張卡不指派 target/reference，
見 ``_util.set_region_family``）。

「這一顆有沒有基準」不必另外給一個數字：``cross_count > 1`` 就是。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..algo import grid as algo_grid
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_REGION, FeatureSpec, ParamSpec, Step, StepError,
)
from ._util import (
    FEATURE_PREFIX_PATTERN, drop_edge_boxes, drop_edge_specs,
    PICK_NONE, output_prefix_spec, pick_defect_box, pick_rule_of,
    pick_rule_specs, prefix_features, region_family,
    REGION_FACT_HELP, SHARED_FEATURE_HELP, region_fact_specs, region_facts,
    region_spec_maker,
    require_image, set_region_family,
    LIMIT_MAX_BOXES,
)

_BESIDE = ("beside_vertical", "beside_horizontal")

#: 會用到 ``gap``（「離邊界多遠」）的那幾種放法 —— **``crossing`` 不在裡面**。
#:
#: ``crossing`` 是「整個交會矩形」：兩軸都只當界線，所以只有 ``inset`` 算數
#: （`algo.grid._spans_for` 的最後一段）。以前這一格對它照樣顯示得出來，
#: 而轉它一整圈**畫面上與數字上都不會有任何變化** —— 2026-09-02 端到端跑一次
#: RSEM 才發現：``gap`` 掃 0/1/3 三個值，24 顆的分數逐位元組相同。
#: `box_size` 與 `side` 早就用 `show_when` 藏對了，漏的只有這一格。
_USES_GAP = ("beside_vertical", "beside_horizontal",
             "between_vertical", "between_horizontal")

#: ``directions`` 的三個值 —— 順序就是圖示列由左到右。
_DIRECTIONS = ("both", "upright", "flat")

#: 哪幾個 ``directions`` 值會用到直的／橫的那一組參數（``show_when``）。
_USES_UPRIGHT = ("both", "upright")
_USES_FLAT = ("both", "flat")

#: ``place`` 的五個選項 —— 順序就是圖示列由左到右的順序，所以它跟 ``icons``
#: 那一串必須逐項對齊（``ParamSpec`` 會擋長度不一樣）。
_PLACE = ("crossing", "beside_vertical", "beside_horizontal",
          "between_vertical", "between_horizontal")


def _prefix_in_section() -> ParamSpec:
    """``output_prefix`` 是共用的那一顆，只差要掛在哪一個小標題底下。"""
    spec = output_prefix_spec("cross")
    spec.section = "5 · Name and limits"
    spec.advanced = True          # 只有同型別的量測卡撞名時才要動它
    return spec


def _norm(rect, shape) -> tuple:
    """像素矩形 → 正規化 (nx, ny, nw, nh)。"""
    h, w = float(shape[0]), float(shape[1])
    x, y, bw, bh = rect
    return (x / w, y / h, bw / w, bh / h)


# ⚠ **這個類別不再自己註冊**（F30，2026-08-25）。使用者：「把 Profile /
# Template 也折進 roi_reference」—— 四張 Region 卡回答的是同一句話（「哪些地方
# 應該長得一樣」），所以它們是一張卡的四個 method，不是四張卡。
#
# 留在這個檔案裡而不是搬進 `roi_reference.py`：把 1100 行演算法搬過去只會讓那
# 個檔案變成 1700 行，而「哪一支怎麼算」本來就各自看得懂 —— 要合的是**使用者
# 看到的那張卡**，不是檔案。`roi_reference` 從這裡取 ``params``（加上一條
# 「method 要是它」的條件）並轉呼叫 ``run`` / ``resolve_*``。
#
# ``key`` 改成 ``roi_reference``：它只剩下「錯誤訊息前面那個名字」這一個用途，
# 而使用者放進畫布的那張卡就叫這個名字。
class RoiCrossStep(Step):
    """交會定位：兩組條紋交叉出格子，在格子上放一組框。"""

    key = "roi_reference"
    label = "Profile"
    category = CATEGORY_ALGO
    group = GROUP_REGION
    help = ("Find the stripes in the image and put a box on every one of them "
            "- so the boxes follow the pattern instead of sitting at fixed "
            "spots on the screen. Stripes running one way give you a box "
            "spanning the image on each stripe; two sets of stripes crossing "
            "each other give you a box on each crossing. Either way one patch "
            "usually has several, and you get a box on each.")
    params = [
        ParamSpec(
            name="source", type="image_key", direction="in", default="ref",
            section="1 · Which image",
            label="Find the pattern in",
            help=("Which image stream to look for the pattern in. Use ref: it "
                  "has no defect on it, so nothing interferes with the search, "
                  "and the pair is already aligned - so one set of boxes is "
                  "correct for both images. Locating on test and on ref "
                  "separately would put the boxes in different places, and "
                  "then the difference between them is no longer only the "
                  "defect."),
        ),
        ParamSpec(
            name="directions", type="chip_choice", default="both",
            choices=list(_DIRECTIONS),
            icons=["dir_both", "dir_upright", "dir_flat"],
            choice_help={
                "both": "Both directions - the box goes where an up-and-down "
                        "stripe meets a left-to-right one.",
                "upright": "Only the up-and-down stripes. The box runs the "
                           "full height of the image.",
                "flat": "Only the left-to-right stripes. The box runs the "
                        "full width of the image.",
            },
            section="1 · Which image",
            label="Which way the pattern runs",
            help=("How many directions of stripe this image has. Most images "
                  "have stripes running one way only - pick that one and the "
                  "box runs the whole way across the other direction. Pick "
                  "both when two sets of stripes cross each other and you want "
                  "the place where they meet. Picking both on an image that "
                  "only has stripes one way finds nothing at all, because the "
                  "card then insists on a crossing that is not there."),
        ),
        ParamSpec(
            name="smooth", type="int", default=3, min=1, max=99, unit="px",
            section="1 · Which image",
            label="Curve smoothing (both directions)",
            help=("Smooth both curves before looking for edges. Too little and "
                  "image noise becomes false edges; too much and real edges "
                  "get rounded away. This one is shared - it is about how the "
                  "image is read, not about either set of stripes."),
            advanced=True,
        ),
        # ---- 直的那組條紋 -------------------------------------------------
        ParamSpec(
            name="vertical_select", type="chip_choice", default="brightest",
            section="2 · The up-and-down stripes",
            choices=list(algo_grid.SELECT_RULES),
            icons=["rank_bright1", "rank_bright2", "rank_bright3",
                   "rank_dark1", "rank_dark2", "rank_dark3",
                   "rank_all"],
            label="Take the up-and-down stripes that are",
            help=("Which of the up-and-down stripes to use, by rank: brightest "
                  "= the brightest group in this image, second_brightest = the "
                  "next group in, and the same from the dark end. This is "
                  "relative to the rest of this image, not an absolute gray "
                  "level, so the same recipe still works when the tool drifts. "
                  "Use the ranks when the image has more than two materials - "
                  "for example brightest for the metal and second_brightest "
                  "for the layer under it."),
            show_when=("directions", _USES_UPRIGHT),
        ),
        ParamSpec(
            name="vertical_kinds", type="int", default=0, min=0, max=6,
            section="2 · The up-and-down stripes",
            label="How many kinds of upright stripe",
            help=("How many different materials run up and down in this image. "
                  "Leave 0 unless the rank above picks up too much. 0 means "
                  "the card assumes just the one kind of stripe plus the space "
                  "between them. Raise it when another material sits on the "
                  "same grid - for example a dark CPODE where a metal gate "
                  "would otherwise be makes it 3 (the gate, the space, the "
                  "CPODE). Getting this wrong is quiet: with two assumed, the "
                  "brightest group takes in the spaces as well, so the card "
                  "finds twice as many stripes at half the pitch."),
            show_when=("directions", _USES_UPRIGHT),
        ),
        ParamSpec(
            name="vertical_width", type="float", default=0.0, min=0.0,
            section="2 · The up-and-down stripes",
            max=10000.0, unit="px", label="Upright stripe width",
            help=("How wide each up-and-down stripe is, in pixels. Leave 0 to "
                  "use the width measured on this image. Filling it in (you "
                  "know it from the layout) means the card only has to find "
                  "the middle of each stripe, and puts the boxes the same "
                  "distance from the drawn edge on every patch - the edge "
                  "sensitivity then decides whether a stripe is found at all, "
                  "not where the box lands. Leave it 0 when the width of the "
                  "stripe is the thing you are measuring."),
            show_when=("directions", _USES_UPRIGHT),
        ),
        ParamSpec(
            name="vertical_pitch", type="float", default=0.0, min=0.0,
            section="2 · The up-and-down stripes",
            max=10000.0, unit="px", label="Upright stripe pitch",
            help=("How far apart the up-and-down stripes are, in pixels. Leave "
                  "0 to measure it from the image. Filling it in (you know it "
                  "from the layout) lets the card check what it found, fill in "
                  "stripes that were too faint or half off the edge, and lock "
                  "on from a single stripe instead of needing several."),
            show_when=("directions", _USES_UPRIGHT),
        ),
        ParamSpec(
            name="vertical_pitch_2", type="float", default=0.0, min=0.0,
            section="2 · The up-and-down stripes",
            max=10000.0, unit="px", label="…and every other one is",
            help=("Only when the spacing alternates between two values - put "
                  "the second spacing here and leave it 0 otherwise. Some "
                  "layouts repeat as wide, narrow, wide, narrow rather than at "
                  "one steady pitch, and a single pitch cannot describe that."),
            advanced=True,
            show_when=("directions", _USES_UPRIGHT),
        ),
        ParamSpec(
            name="vertical_sensitivity", type="float", default=0.35, min=0.0,
            section="2 · The up-and-down stripes",
            max=1.0, label="Upright edge sensitivity",
            help=("How steep a change counts as the edge of an up-and-down "
                  "stripe, compared with the steepest change in this image. "
                  "Lower finds more edges. Watch the panel and drag until the "
                  "lines land where you expect."),
            advanced=True,
            show_when=("directions", _USES_UPRIGHT),
        ),
        # ---- 橫的那組條紋 -------------------------------------------------
        ParamSpec(
            name="horizontal_select", type="chip_choice", default="brightest",
            section="3 · The left-to-right stripes",
            choices=list(algo_grid.SELECT_RULES),
            icons=["rank_bright1", "rank_bright2", "rank_bright3",
                   "rank_dark1", "rank_dark2", "rank_dark3",
                   "rank_all"],
            label="Take the left-to-right stripes that are",
            help="Same as above, for the stripes that run left to right.",
            show_when=("directions", _USES_FLAT),
        ),
        ParamSpec(
            name="horizontal_kinds", type="int", default=0, min=0, max=6,
            section="3 · The left-to-right stripes",
            label="How many kinds of flat stripe",
            help="Same as above, for the stripes that run left to right.",
            show_when=("directions", _USES_FLAT),
        ),
        ParamSpec(
            name="horizontal_width", type="float", default=0.0, min=0.0,
            section="3 · The left-to-right stripes",
            max=10000.0, unit="px", label="Flat stripe width",
            help=("How wide each left-to-right stripe is, in pixels. Leave 0 "
                  "to use the width measured on this image."),
            show_when=("directions", _USES_FLAT),
        ),
        ParamSpec(
            name="horizontal_pitch", type="float", default=0.0, min=0.0,
            section="3 · The left-to-right stripes",
            max=10000.0, unit="px", label="Flat stripe pitch",
            help=("How far apart the left-to-right stripes are, in pixels. "
                  "Leave 0 to measure it from the image."),
            show_when=("directions", _USES_FLAT),
        ),
        ParamSpec(
            name="horizontal_pitch_2", type="float", default=0.0, min=0.0,
            section="3 · The left-to-right stripes",
            max=10000.0, unit="px", label="…and every other one is",
            help=("Only when the spacing alternates between two values - put "
                  "the second spacing here and leave it 0 otherwise."),
            advanced=True,
            show_when=("directions", _USES_FLAT),
        ),
        ParamSpec(
            name="horizontal_sensitivity", type="float", default=0.35, min=0.0,
            section="3 · The left-to-right stripes",
            max=1.0, label="Flat edge sensitivity",
            help="Same as above, for the stripes that run left to right.",
            advanced=True,
            show_when=("directions", _USES_FLAT),
        ),
        # ---- 框放哪 --------------------------------------------------------
        ParamSpec(
            name="place", type="chip_choice", default="beside_vertical",
            choices=list(_PLACE),
            icons=["place_crossing", "place_beside_v", "place_beside_h",
                   "place_between_v", "place_between_h"],
            choice_help={
                "crossing": "The whole overlap — it contains both materials.",
                "beside_vertical": "A thin box hugging each side of an "
                                   "up-and-down stripe, inside a left-to-right "
                                   "one: the boundary between them, measured on "
                                   "the other material.",
                "beside_horizontal": "The same the other way round.",
                "between_vertical": "The clear gap between two up-and-down "
                                    "stripes.",
                "between_horizontal": "The same the other way round.",
            },
            section="4 · Where the box goes",
            label="Put the box",
            help=("Where the box sits relative to the two sets of stripes. "
                  "The pictures show it: the faint bars are the stripes, the "
                  "solid ones are where the box goes."),
        ),
        ParamSpec(
            name="fill_rule", type="chip_choice", default="skip",
            choices=["fill", "skip", "skip_clear"],
            icons=["fill_fill", "fill_skip", "fill_skip_clear"],
            choice_help={
                "fill": "Assume the stripe is there and box it anyway — for "
                        "when a spot is missing only because the stripe was "
                        "too faint to find.",
                "skip": "Look at what is actually there and leave the spot out "
                        "if it is a different material: a dark CPODE sitting "
                        "where a metal gate would be gets no box.",
                "skip_clear": "The same, and also drop the box on the face of "
                              "each neighbouring stripe that looks at it — the "
                              "material next to a CPODE is not the same thing "
                              "as the material next to a gate.",
            },
            section="4 · Where the box goes",
            label="Where a stripe is missing",
            help=("What to do at a spot where the pitch says a stripe should "
                  "be but the image has none. The dotted bar in each picture "
                  "is that missing stripe. Only has an effect when you filled "
                  "in a pitch."),
        ),
        ParamSpec(
            name="box_size", type="float", default=5.0, min=1.0, max=1000.0,
            section="4 · Where the box goes",
            unit="px", label="Box thickness",
            show_when=("place", _BESIDE),
            help=("How thick the box beside the stripe is. Thicker averages "
                  "more pixels but reaches further away from the boundary you "
                  "are actually interested in."),
        ),
        ParamSpec(
            name="side", type="chip_choice", default="both",
            choices=["both", "start", "end"],
            icons=["side_both", "side_start", "side_end"],
            choice_help={
                "both": "A box on each side of every stripe.",
                "start": "Only the left (or upper) side.",
                "end": "Only the right (or lower) side.",
            },
            section="4 · Where the box goes",
            label="Which side",
            show_when=("place", _BESIDE),
            help="Which side of the stripe the box goes on.",
        ),
        *pick_rule_specs("4 · Where the box goes"),
        ParamSpec(
            name="gap", type="float", default=1.0, min=0.0, max=100.0,
            section="4 · Where the box goes",
            show_when=("place", _USES_GAP),
            unit="px", label="Keep clear of the edge",
            help=("How far to stay away from the edge itself. An edge is "
                  "blurred over a few pixels and the gray level there belongs "
                  "to neither material, so measuring it only makes the numbers "
                  "duller. On synthetic data a 5 px box with no clearance took "
                  "one column of the wrong material and read 15% low - and "
                  "that still looks like a perfectly normal number."),
        ),
        ParamSpec(
            name="inset", type="float", default=2.0, min=0.0, max=100.0,
            section="4 · Where the box goes",
            unit="px", label="Keep clear of the other stripes",
            help=("How far to stay inside the stripe that limits the length of "
                  "the box. A box touching both kinds of edge cannot tell you "
                  "which one caused a change."),
        ),
        # ---- 產出 ----------------------------------------------------------
        ParamSpec(
            name="roi_out", type="str", default="cross",
            section="5 · Name and limits",
            label="Name this region", pattern=FEATURE_PREFIX_PATTERN,
            pattern_help=("use letters, digits and underscores only, and do "
                          "not start with a digit"),
            help=("Name for the boxes. Measure cards refer to it by this name. "
                  "When “Which box is the defect in” picks one, you also get "
                  "<name>_center - the picked box - and <name>_others, the "
                  "rest of them, which is the baseline of the same material "
                  "on the same image."),
        ),
        ParamSpec(
            # ⚠ 上限跟合併卡**同一個常數**（`_util.LIMIT_MAX_BOXES`）——
            # 使用者調的是那張卡上的格子，而這裡會再驗一次。見那個常數的說明。
            name="max_boxes", type="int", default=64, min=1,
            max=LIMIT_MAX_BOXES,
            section="5 · Name and limits",
            label="At most this many boxes",
            help=("A guard for images with very fine patterns. The boxes "
                  "nearest the middle are kept, because that is where the "
                  "defect is."),
            advanced=True,
        ),
        ParamSpec(
            name="min_stripe_confidence", type="float", default=5.0, min=0.0,
            section="5 · Name and limits",
            max=200.0, label="Give up below",
            help=("How much of each curve must be real signal rather than "
                  "noise. Some patches sit entirely inside one material and "
                  "have nothing to lock onto - those cannot be located by any "
                  "method, so this card falls back to the whole image and "
                  "marks the defect instead of guessing. A featureless patch "
                  "scores about 1; anything with structure scores 20 or more."),
            advanced=True,
        ),
        *drop_edge_specs("5 · Name and limits"),
        _prefix_in_section(),
    ]
    reads = ["ref"]
    writes: List[str] = []
    features_out = ["cross_count", "cross_pitch_x_px", "cross_pitch_y_px",
                    "cross_filled", "cross_dist_px", "cross_pitch_ratio_x",
                    "cross_pitch_ratio_y", "cross_edge_dropped",
                    "locate_conf", "locate_ok"]
    FEATURE_HELP = dict(
        REGION_FACT_HELP,
        cross_count="how many crossings were found",
        cross_pitch_x_px="spacing of the up-and-down stripes, px",
        cross_pitch_y_px="spacing of the left-to-right stripes, px",
        cross_filled="how many boxes were added where a stripe was missing",
        cross_dist_px="how far the picked crossing is from the middle, px",
        cross_pitch_ratio_x="measured spacing over the one you typed",
        cross_pitch_ratio_y="measured spacing over the one you typed",
        cross_edge_dropped="how many boxes were dropped for touching the edge",
        **SHARED_FEATURE_HELP)

    # ---- 宣告（給 lint / UI）------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [str(params.get("source", "ref"))]

    @classmethod
    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
        return region_family(params.get("roi_out", "cross"),
                             pick_rule_of(params) != PICK_NONE)

    @classmethod
    def resolve_feature_specs(cls, params: Dict[str, Any]) -> List[FeatureSpec]:
        # 卡自己的診斷 ＋ **每個區域那五個**（F11 Region-4：三張 ROI 卡同一組，
        # 見 `_util.REGION_FACTS`）。這張卡以前一個區域數字都沒有 —— 下游要問
        # 「這一顆上到底有沒有 cross_center」只能去看 `locate_ok`，而那是**整張
        # 卡**的旗標，不是那個區域的。
        # ⚠ 這一族的名字文法跟量測卡**相反**：`output_prefix` 在最外、區域名
        # 在 base 裡（`gds_epi_center_present`）——身分因此只有這裡答得出來。
        own = str(params.get("output_prefix", "") or "").strip()

        spec = region_spec_maker(cls.key, own,
                                 cls.resolve_regions_out(params))

        names = list(cls.features_out)
        if pick_rule_of(params) == PICK_NONE:
            # ``none`` 之下「挑中的那一塊離中心多遠」問的東西不存在。
            names.remove("cross_dist_px")
        return ([spec(n) for n in names]
                + [spec(n, region=r, metric=f) for n, r, f in
                   region_fact_specs(cls.resolve_regions_out(params))])

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        return [s.name for s in cls.resolve_feature_specs(params)]

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """方向與放法對不起來 —— 在跑之前就講（F11 Region-2c）。

        「只看直的條紋」＋「框放在兩根**橫**條紋之間」是空集合。它不會報錯，
        它會安靜地產出零個框、退回整張圖、把每一顆都標成 ``locate_ok = 0``
        —— 而畫面上看起來就跟「這批圖沒有結構」一模一樣。使用者要跑完一整批
        才會發現，而那時候他會去調敏感度，因為錯誤訊息指的是那裡。
        """
        want_x, want_y = algo_grid.directions_used(params.get("directions",
                                                              "both"))
        place = str(params.get("place", "beside_vertical"))
        out: List[str] = []
        for need in algo_grid.placement_needs(place):
            if not (want_x if need == "upright" else want_y):
                out.append(
                    "“Put the box” is set to %s, which needs the %s stripes - "
                    "but “Which way the pattern runs” only looks the other "
                    "way. Change one of the two." % (place.replace("_", " "),
                                                     "up-and-down" if need ==
                                                     "upright" else
                                                     "left-to-right"))
        return out

    # ---- 執行 ---------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        name = str(p["roi_out"]).strip()
        if not name:
            raise StepError(self.key, "the region name must not be empty.")

        img = require_image(ctx, self.key, p["source"])
        shape = img.shape[:2]
        res = algo_grid.locate_crossings(
            img,
            vertical_select=str(p["vertical_select"]),
            horizontal_select=str(p["horizontal_select"]),
            vertical_sensitivity=float(p["vertical_sensitivity"]),
            horizontal_sensitivity=float(p["horizontal_sensitivity"]),
            smooth=int(p["smooth"]),
            vertical_pitch=float(p["vertical_pitch"]),
            vertical_pitch_2=float(p["vertical_pitch_2"]),
            horizontal_pitch=float(p["horizontal_pitch"]),
            horizontal_pitch_2=float(p["horizontal_pitch_2"]),
            vertical_kinds=int(p["vertical_kinds"]),
            horizontal_kinds=int(p["horizontal_kinds"]),
            vertical_width=float(p["vertical_width"]),
            horizontal_width=float(p["horizontal_width"]),
            fill_rule=str(p["fill_rule"]),
            placement=str(p["place"]), box_size=float(p["box_size"]),
            side=str(p["side"]), gap=float(p["gap"]), inset=float(p["inset"]),
            min_confidence=float(p["min_stripe_confidence"]),
            max_boxes=int(p["max_boxes"]),
            directions=str(p["directions"]))

        # panel 用的原始資料。**UI 畫的就是引擎算的這一份** —— UI 自己再算一次
        # 很容易變成「畫面上的框」與「真的量下去的框」不一樣，那種 bug 極難發現。
        ctx.meta.setdefault("crossings", {})[name] = {
            "boxes": [[int(v) for v in b] for b in res.boxes],
            "x": _stripe_meta(res.x),
            "y": _stripe_meta(res.y),
            "confidence": float(res.confidence),
            "ok": bool(res.ok),
            "reason": str(res.reason),
            # 面板要分得出「這個方向找不到」與「這個方向沒在找」——
            # 兩者的曲線都是平的，但只有前者是問題。
            "directions": str(p["directions"]),
        }

        if not res.ok:
            # 定位不出來就退回整張圖，**而且說出來**。整張都是同一種材質的
            # patch 本來就不需要定位，但那跟「有結構卻沒找到」是兩件事，
            # 使用者必須分得出來自己拿到的是哪一種。
            ctx.warn("[%s] %s; region '%s' falls back to the whole image and "
                     "this defect is marked locate_ok = 0."
                     % (self.key, res.reason or "could not locate the pattern",
                        name))
            whole = (0.0, 0.0, 1.0, 1.0)
            set_region_family(ctx, self.key, name, [whole],
                              pick=pick_rule_of(p) != PICK_NONE)
            fallback = {
                "cross_count": 0.0,
                "cross_pitch_x_px": float(res.x.pitch_measured),
                "cross_pitch_y_px": float(res.y.pitch_measured),
                "cross_filled": 0.0,
                "cross_pitch_ratio_x": float(res.x.pitch_ratio),
                "cross_pitch_ratio_y": float(res.y.pitch_ratio),
                "cross_edge_dropped": 0.0,
                "locate_conf": float(res.confidence),
                "locate_ok": 0.0,
            }
            if pick_rule_of(p) != PICK_NONE:
                fallback["cross_dist_px"] = -1.0
            ctx.add_features(prefix_features(p["output_prefix"], dict(
                fallback, **region_facts(ctx, self.resolve_regions_out(p), shape,
                              # 退回整張圖 = 框在但那不是這個區域（同
                              # Template；見 `_util.REGION_FACTS` 的 ⚠）。
                              located=False))))
            return ctx

        # 靠邊的框丟掉 —— **在挑出中心那一塊之後**。順序反過來的話，中心會從
        # 「缺陷所在的那一塊」變成「留下來的裡面離中心最近的那一塊」，而那兩者
        # 在缺陷靠近 patch 邊緣時不是同一塊（見 ``_util.drop_edge_boxes``）。
        boxes = list(res.boxes)
        # ``none`` 短路（`pick_defect_box` 沒有「不挑」這個概念）；
        # -1 順便就是 `drop_edge_boxes` 的「沒有受保護的框」。
        idx = (-1 if pick_rule_of(p) == PICK_NONE
               else pick_defect_box(boxes, shape))
        centre = boxes[idx] if idx >= 0 else None
        dropped = 0
        if bool(p["drop_edge"]) and float(p["edge_margin"]) > 0.0:
            boxes, dropped, idx = drop_edge_boxes(
                boxes, shape, float(p["edge_margin"]), idx)
            # 畫面上的框要跟真的量下去的一致（同一條規矩，見上面那段註解）。
            ctx.meta["crossings"][name]["boxes"] = [
                [int(v) for v in b] for b in boxes]
            ctx.meta["crossings"][name]["edge_dropped"] = int(dropped)

        norm_boxes = [_norm(b, shape) for b in boxes]
        set_region_family(ctx, self.key, name, norm_boxes, idx, dropped,
                          pick=pick_rule_of(p) != PICK_NONE)
        if res.reason:
            ctx.warn("[%s] %s." % (self.key, res.reason))

        cx, cy = shape[1] / 2.0, shape[0] / 2.0
        picked: Dict[str, float] = {}
        if centre is not None:
            dist = ((centre[0] + centre[2] / 2.0 - cx) ** 2
                    + (centre[1] + centre[3] / 2.0 - cy) ** 2) ** 0.5
            # 這一格以「挑了一塊」為前提 —— ``pick="none"`` 時**不寫**
            # （不是 0：0 讀起來像「挑中的就在正中心」）。
            picked["cross_dist_px"] = float(dist)
        ctx.add_features(prefix_features(p["output_prefix"], dict({
            "cross_count": float(len(boxes)),
            "cross_pitch_x_px": float(res.x.pitch_used),
            "cross_pitch_y_px": float(res.y.pitch_used),
            # 有幾根條紋是靠已知 pitch 補上的（影像上沒抓到）。0 = 每一根都
            # 真的看得到。這個數字大起來時，框仍然對，但「憑什麼對」變成了
            # 那個 pitch —— 使用者有權知道自己站在哪一邊。
            "cross_filled": float(res.x.filled + res.y.filled),
            # **量到的間距 ÷ 填進去的**。1.0 = 一致；0.5 = 挑錯組；0.75 = pitch
            # 本身填錯（例如換了一台 pixel size 不同的機台）。0/1 的
            # ``locate_ok`` 答不出「錯得多嚴重」，而那兩種的下一步不一樣。
            "cross_pitch_ratio_x": float(res.x.pitch_ratio),
            "cross_pitch_ratio_y": float(res.y.pitch_ratio),
            # 因為靠邊被丟掉幾塊。這個開關會**安靜地改變基準的樣本數**（同一份
            # recipe 在 wafer 中心與邊緣的 defect 上留下的框數不一樣），看得到
            # 才知道某一顆的基準是不是只剩一塊。
            "cross_edge_dropped": float(dropped),
            "locate_conf": float(res.confidence),
            "locate_ok": 1.0,
            # ``picked``：`cross_dist_px` —— 挑中那塊（離中心最近的交會）
            # 離 patch 正中心多遠，本身就是可以畫分布的數字。
        }, **picked, **region_facts(ctx, self.resolve_regions_out(p), shape,
                          clipped=bool(res.clipped), edge_dropped=dropped))))
        return ctx


def _stripe_meta(s: "algo_grid.StripeSet") -> Dict[str, Any]:
    """一個方向的結果攤成純量與清單（要進 meta，所以不留 numpy 陣列）。"""
    return {
        "axis": s.axis,
        "profile": [float(v) for v in s.profile],
        "raw": [float(v) for v in s.raw],
        # ``edges`` 是還沒精修的整數位置（除錯用）。
        "edges": [int(e) for e in s.edges],
        # ``transitions`` 是曲線面板畫線用的鍵，而它畫的必須是**幾何真的用的
        # 那一組**（精修到次像素的）。以前這裡給的是整數版，於是畫面上的線與
        # 塗色的方塊差半格 —— 使用者的原話是「藍線跟藍框應該要 fit，會不重合
        # 的原因是什麼」。答案的一部分就是「面板畫錯了」。
        "transitions": [float(e) for e in (s.edges_sub or s.edges)],
        "bands": [[int(a), int(b)] for a, b in s.bands],
        # 每一段的平均亮度、它屬於第幾群、現在挑的是哪一群，以及**每一群要填
        # 什麼 rule** —— 面板靠這四樣把「第幾亮」畫出來並且點得到（Region-2b）。
        # UI 不自己分群：分幾群取決於現在挑第幾亮，那個規則只該有一份。
        "levels": [float(v) for v in s.levels],
        "groups": [int(g) for g in s.groups],
        "group_picked": int(s.group_picked),
        "group_rules": {str(k): v for k, v in (s.group_rules or {}).items()},
        "selected": [[int(a), int(b)] for a, b in s.selected],
        "pitch_measured": float(s.pitch_measured),
        # 量到的第二個間距（不交錯就是 0）。面板的「量給我填」讀這兩個。
        "pitch_measured_2": float(s.pitch_measured_2),
        # 給了 pitch 卻沒有用的原因，以及晶格把條紋搬了多遠 —— 後者就是
        # 使用者看到的「藍框跟藍線對不齊」。
        "pitch_note": str(s.pitch_note),
        "snap_shift": float(s.snap_shift),
        "pitch_used": float(s.pitch_used),
        "pitches_used": [float(v) for v in s.pitches_used],
        "pitch_error": float(s.pitch_error),
        # 量到的 ÷ 填進去的。1.0 = 一致；0.5 = 典型的「挑錯組」。
        "pitch_ratio": float(s.pitch_ratio),
        # 有多少比例的線明顯對不上晶格，以及**為什麼這個方向不能信**。
        "misfit": float(s.misfit),
        "trust_note": str(s.trust_note),
        "pitch_disagrees": bool(s.pitch_disagrees),
        "filled": int(s.filled),
        # 晶格上被擋掉的位置（那裡是別的材質）。面板要畫得出來 —— 「這一格
        # 我故意不放」跟「這一格我沒找到」在畫面上看起來一模一樣。
        "blocked": [[float(a), float(b)] for a, b in s.blocked],
        "width_used": float(s.width_used),
        "width_fixed": bool(s.width_fixed),
        "confidence": float(s.confidence),
    }

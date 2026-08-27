# d4t step-card library — authored 2026-07-28 (M1); rebuilt 2026-08-21 (F19).
"""cd_measure — **CD**：量什麼形狀 × 在哪量 × 邊界怎麼定義 × 怎麼收。

彼此正交的問題，跟 F18 拆 Gray level 是同一套辦法：

======================  ====================================================
⓪ 量的是什麼形狀？      ``shape`` = 一條線 / 一團東西 —— 問的是**樣品**
① 在哪量？              ``source``（流）× ``roi``（區域）—— 畫布上的線
② 沿哪個方向？          ``axis`` × ``target``（線那一支才有方向）
③ 邊界怎麼定義？        ``criterion`` ＋ ``threshold_pct`` —— **數字從這裡來**
④ 量出來怎麼收？        ``report`` / ``size_report`` 膠囊 ＋ ``target_cd``
======================  ====================================================

⓪ 是一個真的岔路（F19 第二批）
------------------------------
**線與溝有方向，顆粒與孔洞沒有。** 硬挑一個方向去量一團東西，答案就取決於那個
挑選 —— 所以那一支改用旋轉不變的描述（真實面積、等效圓直徑、旋轉卡尺的最大／
最小 Feret）。一條 45° 的刮傷因此量得對，而 bounding box 不會。

它跟「四個 method」的差別仍然是同一句話：**它問的是使用者的樣品**（我要量的是
一條線還是一團東西），而且它真的決定了後面哪幾格算數 —— 方向對一團東西沒有
意義，那一列就該收起來，不是攤在那裡讓人猜它算不算數。

⚠ **``criterion`` 的 ``gradient`` / ``fit`` 只有線那一支有。** 它們是一維剖面上
的構造（梯度峰值、沿爬升擬合 erf），二維沒有對應物 —— 所以團那一支只有門檻
一種，而那一格會收起來。**不要假裝三個判準兩支都有。**
反過來，``threshold_pct``（高度）**兩支共用同一格、同一支函式**
（`algo.edge.threshold_level`）—— 那正是「邊界判準是一個軸，不是一個 method」
這句話兌現的地方。

**刻意不是「四個 method 四選一」。** 那種選項每一個都同時綁死②③④，使用者改一件
事實際上動了三件，而畫面上只有一個下拉在動。判準只有一句話：**這個參數問的是
使用者的樣品，還是問軟體**——「這條線是亮的還是暗的」問樣品，「用 profile 還是
contour」問軟體，後者不該出現在卡片上。

兩支各自的原子單位
------------------
重做之前這張卡量的是區域的 bounding box，而 bbox 是**極值統計量**：邊界上任何
一顆離群像素 100% 傳進答案，圖再大也不會變準。而且它對一個 L 形會錯得離譜
（實測 bbox 是真實面積的 1.9 倍，見 ``tests/test_algo_shape.py``）。

* **線（`algo.edge`）** —— 一條量測線。N 條收成一個分布：平均是 CD、
  **σ 就是 LWR**、min 是頸縮、max 是橋接。粗糙度不是另外加的功能，是副產品。
* **團（`algo.shape`）** —— 區域內的一次門檻切割。旋轉不變的描述：真實覆蓋
  面積、等效圓直徑、旋轉卡尺的最大／最小 Feret。

⚠ 團那一支**不是**被砍掉的那張 blob 分割卡（使用者 2026-08-20：「不需要 也不要
再出現」）。界線是 2026-08-21 劃的一句話：**只在區域內、且不產生具名區域** ——
它不去找「有哪些缺陷」，只量使用者已經用線指給它的那一塊。

四條寫死、不給選的規矩
----------------------
1. **沒有「要不要次像素」的開關。** 1 px 的量化誤差打在 10 px 的線上是 10%，
   不存在「有時候想要比較差的答案」那種時候。
2. **絕不把畫面或框的邊界當成一條邊。** patch 是以缺陷為中心裁的，結構被切掉
   一半是常態；那時候正確的行為是拒絕並講出來（``open_edge``），不是吐出一個
   等於區域寬度的數字——重做之前那張卡正是如此，於是它在既有的三份黃金值上
   **每一顆都是 128 / 128 / 16384**，一個沒有鑑別力的常數欄。
   ⚠ 團那一支**照量但插旗子**（``cd_touches_edge``），而那個不一致是刻意的：
   線寬拿畫面當邊是**發明**一個數字，這裡是一個誠實的下界。見 :data:`ALWAYS_BLOB`。
3. **量不到就不寫那一格**（不是 0、也不是 NaN）。0 進得了分數表達式、寫得進
   DSIZE，一路安靜到最後。
4. **面積是硬門檻的像素數，不做次像素** —— 因為輪廓是硬門檻切出來的，而畫在
   影像上的就是它。面積若來自柔性積分，圖上那一圈與 CSV 上那個數字就不是同一
   件事（見 `algo.shape` 的檔頭）。

單位
----
一律 pixel。填了 nm/px（Load 卡上那一格）就**多配一份 nm 的**，不是換掉——
名字帶著單位就永遠不必回頭查「那份資料當初填了沒」（見 `_util.nm_twins`）。
哪些名字算長度住在 `_util.LENGTH_FEATURES`。

⚠ **舊的 ``cd_x_px`` / ``cd_y_px`` / ``area_px`` 已經沒有了**（F19，使用者
2026-08-21：「就得完全刪掉 以新的為主」）。舊 recipe 的分數表達式引用它們會拿到
``unknown-feature`` warning 指名那個變數——**那正是要看到的**：舊值是 bbox，
跟新值不是同一種量測，安靜地改寫等於換掉那條表達式的意思。

那一團在哪（F29，2026-08-25）
-----------------------------
團那一支**一直都知道位置**：`_note_blob` 存了整條輪廓與最長那條弦，面板上也
畫出來了。它只是從來沒有把位置**吐成特徵** —— 26 個 ``cd_*`` 全部在講「多大、
長什麼樣」，一個都沒在講「在哪」。於是疊圖框不出來、報表排不了序、分數表達式
碰不到它。使用者 2026-08-25：「GLV CD 在 Measurements 就已經量出這顆 defect 或
位置的一些資訊了（這些資訊不能拿來用嗎）」—— 能，缺的只是出口。

所以 :data:`ALWAYS_BLOB` 多了六格：``cd_box_x/y/w/h``（框）與
``cd_cx``/``cd_cy``（質心），**單位是整張影像的像素**（不是區域內的偏移）——
疊圖畫在整張圖上，而換算的地方只該有一個。

⚠ **這沒有把 F19 那個決定翻過來。** 那次刪的是「舊名字的意思被悄悄換掉」，
不是「位置沒用」，所以位置用**新名字**回來，``cd_x_px`` 永遠不會再出現。
而新名字刻意**不叫 ``_px`` 結尾、也不進 `_util.LENGTH_FEATURES`**：這六格是
「畫在哪」不是「多大」，尺寸請看 ``cd_feret_*`` / ``cd_area_px``（有 nm 版的
是那些）。給框配一份 nm 等於請使用者拿 bbox 當尺寸用 —— 那正是 F19 拆掉的東西。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..algo import edge as algo_edge
from ..algo import shape as algo_shape
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_MEASURE,
)
from ._util import (
    MultiSourceStep, ensure_gray, output_prefix_spec, parse_key_list,
    roi_rect_or_none,
)

#: ``report`` 膠囊列得出來的東西。分三群（UI 那邊登記在
#: ``widgets.METRIC_GROUPS``）—— 分群不是排版偏好：粗糙度那一群只有在
#: **量測線夠多**的時候才有意義，而那件事在一排攤平的膠囊上看不出來。
REPORT_CHOICES = (
    # Width —— 這條結構有多寬
    "cd_median", "cd_mean", "cd_min", "cd_max", "cd_range",
    # Roughness —— 它有多不齊
    "cd_std", "ler_a_std", "ler_b_std",
    # Vs target —— 跟規格差多少（要填 target_cd）
    "cd_dev", "cd_dev_frac",
)

#: 預設勾這幾顆。中位數而不是平均（一條線量歪了不該把答案帶走）、σ 是 LWR、
#: min/max 是頸縮與橋接——**殺死良率的是最窄的那一段，不是平均**。
DEFAULT_REPORT = "cd_median,cd_std,cd_min,cd_max"

#: 要填 ``target_cd`` 才算得出來的那兩顆。
_NEEDS_TARGET = ("cd_dev", "cd_dev_frac")

#: ⓪ 的兩個答案。``line`` 是預設 —— 既有 recipe 沒有這個鍵，走的就是它。
SHAPE_LINE = "line"
SHAPE_BLOB = "blob"
SHAPES = (SHAPE_LINE, SHAPE_BLOB)

#: 團那一支的膠囊（`size_report`）。分兩群，同 F18 的理由：Outline 那一群問的
#: 是「長什麼樣」，跟 Size 的「有多大」不是同一個問題，攤成一列看不出來。
#:
#: 群名用 ``Size`` / ``Outline``，**不要用 ``Shape``** —— 那個字在
#: ``widgets.METRIC_GROUPS`` 裡已經是 GLV 的偏度那一群。
SIZE_CHOICES = (
    # Size —— 有多大
    "cd_area_px", "cd_deq", "cd_feret_max", "cd_feret_min",
    # Outline —— 長什麼樣
    "cd_aspect", "cd_roundness",
)

#: 團那一支的預設。四個都是**尺寸**，因為那是這一支存在的理由；形狀那兩個
#: 要的人自己勾。
DEFAULT_SIZE_REPORT = "cd_area_px,cd_deq,cd_feret_max,cd_feret_min"

#: 團那一支一律吐的（不在膠囊裡）。跟線那一支同一條規矩 —— **卡片自動做的每一
#: 個決定，都要變成一個使用者畫得出分布的數字**：
#:
#: * ``cd_pieces`` —— 切出來幾團。它揭露的是「它挑了哪一團」（中心那一團，
#:   沒有就取最大的）；恆為 1 才代表沒有這個問題。
#: * ``cd_touches_edge`` —— 貼到區域邊的那些，面積是**下界**不是尺寸。
#:   使用者定調「照量，但插一支旗子」（2026-08-21）：跟線那一支的「拒絕」不一致
#:   是刻意的 —— 線寬拿畫面當邊是**發明**一個數字，這裡是一個誠實的下界，
#:   而區域卡的 ``<name>_clipped`` 已經是這個做法。
#: * ``cd_feret_angle`` —— 最長的方向。自動算出來的，而且它本身有用
#:   （一條刮傷與一顆顆粒的差別就在這裡）。
#: * ``cd_box_x`` / ``cd_box_y`` / ``cd_box_w`` / ``cd_box_h`` ＋ ``cd_cx`` /
#:   ``cd_cy`` —— **這一團在哪**（F29）。座標是**整張影像的像素**，區域偏移
#:   已經加回去了，所以疊圖與 CSV 上是同一個座標系。
#:
#:   為什麼是「一律吐」而不是 ``size_report`` 上的一個選項：位置不是「要不要
#:   量」的選擇，它是「我剛才量在哪」。少了它，畫面上那一圈輪廓與 CSV 上那一
#:   列就沒有任何東西對得起來。
#:
#:   ⚠ ``cd_box_w`` / ``cd_box_h`` 是**框**不是尺寸（一個 L 形的框是它真實面積
#:   的 1.9 倍，見 `algo.shape` 檔頭）。要尺寸請用 ``cd_feret_*`` /
#:   ``cd_area_px``。這也是它們不配 nm 版的理由。
ALWAYS_BLOB = ("cd_pieces", "cd_touches_edge", "cd_feret_angle",
               "cd_bright", "cd_edge_score",
               "cd_box_x", "cd_box_y", "cd_box_w", "cd_box_h",
               "cd_cx", "cd_cy")

#: 這張卡**一律**吐的五個（不在膠囊裡）。
#:
#: 前兩個是「量得準不準」（同 F18 的 ``glv_pixels``），後兩個是**卡片自己做的
#: 決定**。規矩一句話：**卡片自動做的每一個決定，都要變成一個使用者畫得出分布的
#: 數字**——方向若在整批裡逐顆翻轉，那一欄 CSV 混著兩種不同的量測，而除了
#: ``cd_axis_deg`` 之外沒有任何線索透露這件事。
#:
#: ``cd_bright``（1 = 量了亮的那條、0 = 暗的那條）是**實跑合成 lot 才發現要有
#: 的**：``target="auto"`` 在同一批裡逐顆挑了不同的極性，於是 ``cd_median``
#: 那一欄同時裝著「線寬 6.5」與「溝寬 9.4」兩群 —— 每一顆都吐得出正常數字，
#: 而 CSV 上沒有任何東西透露它們量的不是同一種東西。
ALWAYS = ("cd_n", "cd_lines", "cd_axis_deg", "cd_bright", "cd_edge_score")


@register_step
class CdMeasureStep(MultiSourceStep):
    """CD：一條線有多寬，或一團東西有多大（見模組說明的岔路）。"""

    key = "cd_measure"
    label = "CD"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Measure how big something is, in pixels. Point it at a line or a "
            "gap and it lays measurement lines across, giving the width and "
            "how rough it is; point it at a particle or a void and it gives "
            "the area and a pair of calipers instead, so the answer does not "
            "depend on which way you look at it. Convert to nm by filling in "
            "the pixel size on the card that loaded the images.")
    params = [
        # ⓪ 量的是什麼形狀 ----------------------------------------------------
        ParamSpec(name="shape", type="icon_choice", default=SHAPE_LINE,
                  label="Measuring", choices=list(SHAPES),
                  icons=["shape_line", "shape_blob"],
                  choice_help={
                      SHAPE_LINE: "A line or a gap - something with a "
                                  "direction. Measured across, so you also "
                                  "get how rough it is.",
                      SHAPE_BLOB: "A particle, a void, an irregular defect - "
                                  "something with no direction. Measured as "
                                  "an area and a pair of calipers, so the "
                                  "answer does not depend on which way you "
                                  "look at it.",
                  },
                  help=("Is the thing you want to measure a line, or a blob? "
                        "A line has a direction and a blob does not, and that "
                        "changes what can be measured at all - so the rows "
                        "below change with it.")),
        # ① 在哪量 ------------------------------------------------------------
        ParamSpec(name="source", type="image_keys", direction="in",
                  default="test",
                  help=("Which image stream to find the edges on. Usually the "
                        "test image - a difference image has the structure "
                        "subtracted out of it, so there are no edges left to "
                        "measure.")),
        ParamSpec(name="roi", type="region_keys", direction="in", default="",
                  label="Region",
                  help=("Which region(s) to measure in - drag a line from the "
                        "Region card that defines each one. Two regions here "
                        "means the same measurement in both, and every number "
                        "gets its region's name in front of it. No line means "
                        "the whole image.")),
        # ② 沿哪個方向 --------------------------------------------------------
        ParamSpec(name="axis", type="icon_choice", default="auto",
                  label="Direction", show_when=("shape", (SHAPE_LINE,)),
                  choices=["auto", "x", "y"],
                  icons=["dir_both", "dir_upright", "dir_flat"],
                  choice_help={
                      "auto": "Let the card pick whichever direction the edges "
                              "run across. It writes down what it picked in "
                              "cd_axis_deg.",
                      "x": "Measure left-to-right (for up-and-down lines).",
                      "y": "Measure top-to-bottom (for flat lines).",
                  },
                  help=("Which way to measure across the structure. Pick it "
                        "yourself if the whole lot looks the same - then every "
                        "defect is measured the same way.")),
        ParamSpec(name="target", type="icon_choice", default="auto",
                  label="Measure the",
                  choices=["auto", "bright", "dark"],
                  icons=["target_auto", "target_bright", "target_dark"],
                  choice_help={
                      "auto": "Whichever of the two stands out more where you "
                              "are pointing.",
                      "bright": "The bright one (a line, or a particle).",
                      "dark": "The dark one (a gap, a trench, or a void).",
                  },
                  help=("Is the thing you want to measure the bright one or "
                        "the dark one? This is a question about your sample, "
                        "not about the software.")),
        # ③ 邊界怎麼定義 ------------------------------------------------------
        ParamSpec(name="criterion", type="choice", default="threshold",
                  section="Where the edge is",
                  label="Edge is at", show_when=("shape", (SHAPE_LINE,)),
                  choices=list(algo_edge.CRITERIA),
                  choice_help={
                      "threshold": "Where the brightness crosses a set height "
                                   "between the two sides. Steadiest number "
                                   "of the three.",
                      "gradient": "Where the brightness changes fastest. Least "
                                  "affected by blur and smoothing, so use it "
                                  "when you compare absolute CD across lots.",
                      "fit": "Fits an S-curve to the whole slope. Also "
                             "reports how blurred the edge is.",
                  },
                  help=("There is no single correct edge - CD is defined by "
                        "how you measure it. All three are steady; they just "
                        "differ in what they are steadiest against.")),
        # **兩支共用這一格**（見模組說明）：同一句話、同一支
        # `algo.edge.threshold_level`。所以它**沒有** show_when —— 綁在
        # `criterion` 上的話，切到團那一支就會連它一起藏掉，而那一支唯一的
        # 旋鈕就是它。
        ParamSpec(name="threshold_pct", type="int", default=50, min=1, max=99,
                  unit="%", section="Where the edge is",
                  label="…at this height",
                  help=("How far up from the dark side to the bright side "
                        "counts as the edge. 50% of the local contrast is the "
                        "usual choice. Raising it makes a bright line or "
                        "particle read smaller and a dark gap or void read "
                        "larger.")),
        ParamSpec(name="window", type="int", default=9, min=3, max=64,
                  unit="px", section="Where the edge is", extent=True,
                  label="Look this far around each edge",
                  show_when=("shape", (SHAPE_LINE,)),
                  help=("How much of each side to use when working out the "
                        "two levels the edge sits between. Too small and there "
                        "is no flat part to measure; too large and the "
                        "neighbouring structure gets counted in. The card "
                        "never lets this reach past the next edge.")),
        # ④ 怎麼收 ------------------------------------------------------------
        ParamSpec(name="report", type="metric_chips", default=DEFAULT_REPORT,
                  section="Report", label="Report",
                  choices=list(REPORT_CHOICES),
                  show_when=("shape", (SHAPE_LINE,)),
                  help=("Which numbers to write out. The width ones describe "
                        "the structure; the roughness ones are the spread "
                        "across the measurement lines - cd_std is LWR (the "
                        "usual 3-sigma LWR is three times it), and ler_a / "
                        "ler_b are the two edges wandering on their own.")),
        # 團那一支的膠囊。**另開一格而不是換掉 ``report`` 的 choices**：
        # ``choices`` 是宣告，不是執行期算出來的東西，而既有 recipe 存的
        # ``report`` 值一個字都不用動。
        ParamSpec(name="size_report", type="metric_chips",
                  default=DEFAULT_SIZE_REPORT,
                  section="Report", label="Report",
                  choices=list(SIZE_CHOICES),
                  show_when=("shape", (SHAPE_BLOB,)),
                  help=("Which numbers to write out. The size ones say how big "
                        "it is - the area is the real covered pixels, not the "
                        "box around them, and the two calipers are the widest "
                        "and narrowest it measures whichever way it is turned. "
                        "The outline ones say what it looks like: aspect "
                        "separates a scratch from a particle, roundness "
                        "separates a solid blob from a ragged one.")),
        ParamSpec(name="target_cd", type="float", default=0.0, min=0.0,
                  max=1e6, unit="px", section="Report",
                  label="Target CD", show_when=("shape", (SHAPE_LINE,)),
                  help=("What this structure is supposed to measure, from your "
                        "process spec. Fill it in and you also get how far off "
                        "this defect is - which is usually the number worth "
                        "binning on. Leave it at 0 to skip.")),
        # 進階 ----------------------------------------------------------------
        ParamSpec(name="line_step", show_when=("shape", (SHAPE_LINE,)), type="int", default=1, min=1, max=64,
                  unit="px", advanced=True,
                  label="One line every",
                  help=("Measure only every Nth line. Leave it at 1 unless the "
                        "region is very tall and you want it faster.")),
        ParamSpec(name="line_bin", show_when=("shape", (SHAPE_LINE,)), type="int", default=1, min=1, max=64,
                  unit="px", advanced=True,
                  label="Average this many lines together",
                  help=("Averaging neighbouring lines makes each width less "
                        "noisy, but it also smooths the roughness away - the "
                        "wobble you are trying to measure is exactly what gets "
                        "averaged out. Leave it at 1 to measure roughness.")),
        ParamSpec(name="min_lines", show_when=("shape", (SHAPE_LINE,)), type="int", default=3, min=1, max=999,
                  advanced=True,
                  label="Need at least this many lines",
                  help=("If fewer measurement lines than this succeed, no "
                        "width is written for this defect at all - a mean of "
                        "two lines is not a measurement. The counts are still "
                        "written so you can see what happened.")),
        ParamSpec(name="min_area", type="int", default=algo_shape.MIN_AREA,
                  min=1, max=100000, unit="px", advanced=True,
                  label="Ignore blobs smaller than",
                  show_when=("shape", (SHAPE_BLOB,)),
                  help=("Bits smaller than this are not counted as a blob. "
                        "The smallest thing this card can see at all is about "
                        "3x3 px - below that a real speck and a pair of hot "
                        "pixels look the same, and giving it a size would be "
                        "pretending otherwise.")),
        ParamSpec(name="min_edge", type="float",
                  default=algo_edge.MIN_QUALITY, min=0.0, max=0.95,
                  advanced=True,
                  label="Ignore edges weaker than",
                  help=("How much an edge has to stand out from the noise "
                        "before it counts, from 0 (anything) to 0.95 (only "
                        "very clean edges). The default 0.5 means the step has "
                        "to be about four times the noise. Turn it down only "
                        "if the card is missing edges you can see - turning it "
                        "to 0 lets it measure the noise itself, which produces "
                        "a perfectly normal-looking number for every defect.")),
        ParamSpec(name="smooth", type="float", default=1.0, min=0.0, max=5.0,
                  unit="px", advanced=True,
                  show_when=("shape", (SHAPE_LINE,)),
                  label="Smooth each line by",
                  help=("Smooths each measurement line before looking for "
                        "edges, which is what makes edge finding survive "
                        "noise. Turning it up a long way pushes the threshold "
                        "and S-curve edges outward (measured); the gradient "
                        "one does not move.")),
        output_prefix_spec("cd"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = (list(ALWAYS) + list(REPORT_CHOICES)
                    + list(ALWAYS_BLOB) + list(SIZE_CHOICES))

    #: 這張卡一定要影像 —— 它量的是像素上的邊，不是框的尺寸。
    #: （重做之前是 ``False``，因為 bbox 不必看圖，而那正是問題所在。）
    REQUIRE_IMAGE = True

    #: ``ctx.meta`` 上放掃描線幾何的鍵（面板與影像疊圖都讀它）。
    META_KEY = "cd"

    @classmethod
    def _region_index(cls, p: Dict[str, Any]) -> int:
        """這一輪量的是第幾個區域 —— **顏色的唯一出處**。

        值由基底的迴圈給（`MultiSourceStep.CURRENT_REGION_INDEX`）：這裡拿到的
        ``roi`` 已經被換成當前那**一個**區域，自己數不出來。而區域框走的是
        `resolve_regions_in`，跟 `region_list` 同一個順序 —— 所以同一個區域在
        框、在標記、在面板上是同一個顏色。
        """
        try:
            return max(0, int(p.get(cls.CURRENT_REGION_INDEX, 0) or 0))
        except (TypeError, ValueError):
            return 0

    # ---- 影像上的標記（見 Step.overlay_marks）------------------------------ #
    @classmethod
    def overlay_marks(cls, ctx: Any, params: Dict[str, Any],
                      stream: Optional[str] = None) -> Any:
        """把 ``ctx.meta["cd"]`` 裡的掃描線與邊點交出去。

        線太多會糊成一片，所以最多畫 :data:`MAX_DRAWN_LINES` 條（等距抽樣）——
        但**代表那一條一定在裡面**，它是面板上那張剖面圖畫的同一條。

        ``stream`` 給了就**只交那一條流量到的**。這張卡的 ``source`` 是複數
        型別，接兩條線就在兩條流上各量一次（見 ``docs/USING-CD.md`` §2）——
        而那兩組線是在**兩張不同的影像**上量出來的。全部畫上去的話，你正在看
        的 test 上會有一半的線是量在 ref 上的結果，同一個顏色、同一個標籤，
        分不出來（2026-08-22 在 `0822test/mgext` 的 recipe 上實際看到）。
        比對模式因此也才是對的：左邊畫左邊那條流的、右邊畫右邊那條流的。

        note 沒記流名的時候不過濾 —— 過濾要根據**知道的事**，不是猜的。
        """
        notes = (getattr(ctx, "meta", None) or {}).get(cls.META_KEY) or {}
        lines: List[Any] = []
        points: List[Any] = []
        labels: List[str] = []
        focus = -1
        want = str(stream or "").strip()
        for prefix in sorted(notes):
            note = notes[prefix] or {}
            mine = str(note.get("stream") or "").strip()
            if want and mine and mine != want:
                continue                   # 這一份是量在別張影像上的
            name = str(note.get("region") or "")
            before = len(lines)
            if str(note.get("shape")) == SHAPE_BLOB:
                focus = cls._blob_marks(note, lines, points, focus)
                labels.extend([name] * (len(lines) - before))
                continue
            segs = list(note.get("scan_lines") or [])
            edges = list(note.get("edges") or [])
            if len(segs) != len(edges):
                continue                   # 對不齊就整組不畫（同 set_overlay）
            pick = int(note.get("median_index", -1))
            for i in _thin_out(len(segs), MAX_DRAWN_LINES, pick):
                if i == pick and focus < 0:
                    focus = len(lines)
                lines.append([tuple(pt) for pt in segs[i]])
                points.append([tuple(pt) for pt in edges[i]])
            labels.extend([name] * (len(lines) - before))
        return lines, points, focus, labels

    @staticmethod
    def _blob_marks(note: Dict[str, Any], lines: List[Any], points: List[Any],
                    focus: int) -> int:
        """輪廓 ＋ 最長那條弦。**不需要任何新的 UI 原語** —— 一圈輪廓就是一串
        線段，而弦就是第 N+1 條，兩端各一個點、畫成 focus 的那一條。

        「那個數字是這樣量出來的」因此在影像上是看得見的。
        """
        outline = [tuple(pt) for pt in (note.get("outline") or [])]
        for i in range(len(outline)):
            lines.append([outline[i], outline[(i + 1) % len(outline)]])
            points.append([])
        chord = [tuple(pt) for pt in (note.get("chord") or [])]
        if len(chord) == 2:
            if focus < 0:
                focus = len(lines)
            lines.append([chord[0], chord[1]])
            points.append([chord[0], chord[1]])
        return focus

    # ---- 宣告 ------------------------------------------------------------- #
    @classmethod
    def feature_names(cls, params: Dict[str, object]) -> List[str]:
        """這組參數下會產出哪幾個基本名（不含任何前綴）。

        **兩支各報各的** —— 一張卡不是量線就是量團，所以宣告也不該把另一支的
        名字列出來（列了的話 CSV 與分數表達式的自動完成裡會有一整排永遠是空的
        欄位，而使用者分不出哪些是這張卡真的會給的）。

        ``cd_dev`` 那兩顆**只在填了 ``target_cd`` 時才宣告** —— 這張卡看得到那
        一格，所以它答得出來。
        """
        if _shape_of(params) == SHAPE_BLOB:
            want = [m for m in parse_key_list(str(params.get("size_report", "")))
                    if m in SIZE_CHOICES]
            return list(ALWAYS_BLOB) + want
        want = [m for m in parse_key_list(str(params.get("report", "")))
                if m in REPORT_CHOICES]
        if _target_cd(params) <= 0.0:
            want = [m for m in want if m not in _NEEDS_TARGET]
        return list(ALWAYS) + want

    @classmethod
    def base_specs(cls, params: Dict[str, object]):
        """基本名＋身分（PR-3）：每個基本名就是它自己的統計量 id
        （`METRIC_GROUPS` 的鍵），家族 "cd"。名字的分支照 `feature_names`。"""
        return [(str(n), str(n), "", "", "cd")
                for n in cls.feature_names(params)]

    @classmethod
    def diagnostic_names(cls, params: Dict[str, object]) -> List[str]:
        """「量得準不準」那幾個（``ALWAYS`` 註解裡的前兩個 ＋ 團那支的對應者）。

        ⚠ ``cd_axis_deg`` / ``cd_bright`` **不在這裡**：它們是「卡片自動做的
        決定要變成畫得出分布的數字」那一族（F19）—— 使用者本來就該在表上
        看到它們的分布，收進診斷等於把那條規矩收回去。
        """
        if _shape_of(params) == SHAPE_BLOB:
            return ["cd_touches_edge", "cd_edge_score"]
        return ["cd_n", "cd_lines", "cd_edge_score"]

    @classmethod
    def diagnostic_alarm_names(cls, params: Dict[str, object]) -> List[Tuple[str, bool]]:
        if _shape_of(params) == SHAPE_BLOB:
            return [("cd_touches_edge", True)]  # 1 = 貼著邊，面積只是下限
        return []

    # ---- 量一個區域 -------------------------------------------------------- #
    def measure(self, ctx: Context, img, p: Dict[str, Any]):
        gray = ensure_gray(np.asarray(img))
        rect = roi_rect_or_none(ctx, self.key, gray, p["roi"])
        x, y, w, h = (int(v) for v in rect)
        block = gray[y:y + h, x:x + w]
        if block.size == 0 or min(block.shape[:2]) < 3:
            ctx.warn("[%s] region '%s' is only %d×%d px on this defect - too "
                     "small to measure anything in. Nothing measured for it."
                     % (self.key, p["roi"] or "the image",
                        block.shape[1] if block.ndim > 1 else 0,
                        block.shape[0] if block.ndim > 0 else 0))
            return None

        if _shape_of(p) == SHAPE_BLOB:
            return self._measure_blob(ctx, block, (x, y, w, h), p)

        axis = str(p["axis"])
        if axis == "auto":
            axis, _sx, _sy = algo_edge.choose_axis(block, smooth=p["smooth"])

        res = algo_edge.scan(
            block, axis=axis, criterion=str(p["criterion"]),
            target=str(p["target"]),
            threshold_frac=float(p["threshold_pct"]) / 100.0,
            window=int(p["window"]), smooth=float(p["smooth"]),
            line_step=int(p["line_step"]), line_bin=int(p["line_bin"]),
            min_quality=float(p["min_edge"]))

        used = _target_used(res)
        self._note(ctx, gray, (x, y, w, h), res, p, used)
        self._complain(ctx, res, p)

        n_ok = int(res.widths.size)
        feats: Dict[str, float] = {
            "cd_n": float(n_ok),
            "cd_lines": float(len(res.lines)),
            # 0 = 沿 X 量、90 = 沿 Y 量。**自動選的方向一定要吐出來**（見 ALWAYS）。
            "cd_axis_deg": 0.0 if res.axis == algo_edge.AXIS_X else 90.0,
        }
        if used:
            feats["cd_bright"] = 1.0 if used == "bright" else 0.0
        if n_ok < max(1, int(p["min_lines"])):
            return feats                   # 量不出來的那幾格**不寫**
        feats["cd_edge_score"] = float(np.median(
            [ln.quality for ln in res.lines if not ln.reason]))
        feats.update(self._report(res, p))
        return feats

    # ---- ⓪ 團那一支 -------------------------------------------------------- #
    def _measure_blob(self, ctx: Context, block, rect,
                      p: Dict[str, Any]) -> Optional[Dict[str, float]]:
        """區域內切一團，量它有多大、長什麼樣。

        「切一團」到此為止：**不吐具名區域、不去找還有哪些缺陷**（使用者
        2026-08-21 劃的界線）。所以這裡跟 `Context` 的往來只有 warn 與 meta。
        """
        res = algo_shape.measure_blob(
            block, target=str(p["target"]),
            frac=float(p["threshold_pct"]) / 100.0,
            min_quality=float(p["min_edge"]), min_area=int(p["min_area"]))

        self._note_blob(ctx, block, rect, res, p)

        where = str(p.get("roi") or "the whole image")
        if not res.ok:
            ctx.warn("[%s] nothing to measure in %s: %s. No size is written "
                     "for this defect; the rest of the batch is unaffected."
                     % (self.key, where, _BLOB_REASONS.get(
                         res.reason, res.reason)))
            # 尺寸不寫，但**「量得準不準」那幾個照吐** —— 跟線那一支失敗時仍然
            # 吐 `cd_n` / `cd_lines` 是同一條規矩。`cd_edge_score` 在這裡尤其
            # 重要：它就是「為什麼沒有」的那個數字，而一整批畫出來看得到門檻
            # 該往哪邊調。`cd_touches_edge` 不寫 —— 沒有團的時候它沒有意義。
            # **位置那六格也不寫**（規矩 3）：沒有團的時候「在哪」沒有答案，
            # 而 0 會讓疊圖在左上角畫一個 0×0 的框 —— 看起來像量到了。
            return {"cd_pieces": 0.0,
                    "cd_bright": 1.0 if res.target == "bright" else 0.0,
                    "cd_edge_score": float(res.quality)}
        if res.touches_edge:
            # **照量，但插一支旗子**（使用者 2026-08-21）。不一致於線那一支的
            # 「拒絕」是刻意的 —— 見模組說明的規矩 2。
            ctx.warn("[%s] the blob in %s runs to the edge of it, so its size "
                     "is a lower bound, not the size (cd_touches_edge = 1). "
                     "Widen the region if you need the whole thing."
                     % (self.key, where))

        bx, by, bw, bh = res.bbox
        rx, ry, _rw, _rh = rect
        feats: Dict[str, float] = {
            "cd_pieces": float(res.pieces),
            "cd_touches_edge": 1.0 if res.touches_edge else 0.0,
            "cd_feret_angle": float(res.feret_angle),
            "cd_bright": 1.0 if res.target == "bright" else 0.0,
            "cd_edge_score": float(res.quality),
            # **在哪**（F29）。`res.bbox` / `res.centroid` 是 block 座標，
            # 這裡把區域的左上角加回去 —— 換算只做這一次，其他人拿到的一律是
            # 整張影像的像素（`_note_blob` 的輪廓走同一個 `rect`）。
            "cd_box_x": float(rx + bx), "cd_box_y": float(ry + by),
            "cd_box_w": float(bw), "cd_box_h": float(bh),
            "cd_cx": float(rx + res.centroid[0]),
            "cd_cy": float(ry + res.centroid[1]),
        }
        feats.update(self._size_report(res, p))
        return feats

    @staticmethod
    def _size_report(res: "algo_shape.BlobResult",
                     p: Dict[str, Any]) -> Dict[str, float]:
        table = {
            # **真實覆蓋像素，不是框的面積。** 一個 L 形的 bbox 是它的 1.9 倍。
            "cd_area_px": lambda: float(res.area),
            "cd_deq": lambda: algo_shape.equivalent_diameter(res.area),
            "cd_feret_max": lambda: float(res.feret_max),
            "cd_feret_min": lambda: float(res.feret_min),
            # 細長 vs 圓。1.0 = 圓，越大越細長（分母有地板，一團一像素寬的東西
            # 不該讓整顆 defect 變成 inf）。
            "cd_aspect": lambda: float(res.feret_max / max(1e-6, res.feret_min)),
            # 跟 aspect 問的**不是同一件事**：一條直棒與一團毛毛的圓斑可以有
            # 一樣的 aspect，而周長分得出來。
            "cd_roundness": lambda: algo_shape.roundness(res.area, res.perimeter),
        }
        want = [m for m in parse_key_list(str(p.get("size_report", "")))
                if m in SIZE_CHOICES]
        return {name: table[name]() for name in want if name in table}

    def _note_blob(self, ctx: Context, block, rect,
                   res: "algo_shape.BlobResult", p: Dict[str, Any]) -> None:
        """輪廓、最長那條弦、灰階直方圖與判準 —— 面板與疊圖要的那一份。

        輪廓存**正規化**座標（同線那一支），而且**抽稀到最多
        :data:`MAX_CONTOUR_POINTS` 個點**：一顆 30 px 的團外框有上百個點，
        每顆 defect 存一份會讓 meta 變得很肥（同 `Context._record_change`
        只存摘要的理由）。
        """
        arr = np.asarray(ctx.images.get(str(p.get(self.CURRENT_STREAM, "")),
                                        block))
        h, w = arr.shape[:2] if arr.ndim >= 2 else (0, 0)
        if not (h and w):
            return
        rx, ry, _rw, _rh = rect

        def point(px: float, py: float):
            return round(float(rx + px) / w, 6), round(float(ry + py) / h, 6)

        outline: List[Any] = []
        if res.contour.size:
            pts = res.contour
            step = max(1, int(np.ceil(len(pts) / float(MAX_CONTOUR_POINTS))))
            outline = [point(px, py) for px, py in pts[::step]]
        chord = [point(*res.chord[0]), point(*res.chord[1])] if res.ok else []

        prefix = str(p.get(self.CURRENT_PREFIX, "") or "")
        ctx.meta.setdefault(self.META_KEY, {})[prefix] = {
            "shape": SHAPE_BLOB,
            "region_index": self._region_index(p),
            "criterion": "threshold",
            "region": str(p.get("roi") or ""),
            "stream": str(p.get(self.CURRENT_STREAM, "") or ""),
            "ok": bool(res.ok), "reason": res.reason,
            "target_used": res.target,
            "level": round(float(res.level), 3),
            "bg": round(float(res.bg), 3), "fg": round(float(res.fg), 3),
            "area": int(res.area), "pieces": int(res.pieces),
            "touches_edge": bool(res.touches_edge),
            "feret_max": round(float(res.feret_max), 4),
            "feret_min": round(float(res.feret_min), 4),
            "feret_angle": round(float(res.feret_angle), 2),
            "outline": outline, "chord": chord,
            "hist": {"counts": list(res.hist[0]),
                     "lo": round(float(res.hist[1]), 3),
                     "hi": round(float(res.hist[2]), 3)},
        }

    # ---- ④ 一串距離收成數字 ------------------------------------------------ #
    def _report(self, res: "algo_edge.ScanResult",
                p: Dict[str, Any]) -> Dict[str, float]:
        widths = res.widths
        table = {
            "cd_median": lambda: float(np.median(widths)),
            "cd_mean": lambda: float(np.mean(widths)),
            "cd_min": lambda: float(np.min(widths)),
            "cd_max": lambda: float(np.max(widths)),
            "cd_range": lambda: float(np.max(widths) - np.min(widths)),
            # **一律報 σ，不報 3σ。** LWR 的業界慣例是 3σ，但同一個名字在不同
            # 地方算出不同的東西是這個 repo 最怕的錯 —— 所以名字說 σ，
            # 「LWR = 3 × 它」寫在 help 裡。
            "cd_std": lambda: float(np.std(widths)),
            # 兩條邊**各自**的 σ。兩邊一起晃 = LER 有、LWR 沒有（載台或對位在
            # 漂）；各自晃才是結構本身粗糙。兩個不同的製程故障，而 bbox 那條路
            # 連問都問不出來。
            "ler_a_std": lambda: float(np.std(res.a_positions)),
            "ler_b_std": lambda: float(np.std(res.b_positions)),
        }
        want = [m for m in parse_key_list(str(p.get("report", "")))
                if m in REPORT_CHOICES]
        out: Dict[str, float] = {}
        for name in want:
            fn = table.get(name)
            if fn is not None:
                out[name] = fn()

        target = _target_cd(p)
        if target > 0:
            here = float(np.median(widths))
            if "cd_dev" in want:
                out["cd_dev"] = here - target
            if "cd_dev_frac" in want:
                out["cd_dev_frac"] = (here - target) / target
        return out

    # ---- 講出哪裡不對 ------------------------------------------------------ #
    def _complain(self, ctx: Context, res: "algo_edge.ScanResult",
                  p: Dict[str, Any]) -> None:
        total = max(1, len(res.lines))
        n_ok = int(res.widths.size)
        where = str(p.get("roi") or "the whole image")
        open_edge = int(res.reasons.get("open_edge", 0))
        if open_edge > total // 2:
            ctx.warn(
                "[%s] the structure runs past the edge of %s on %d of %d "
                "measurement lines, so those lines were not measured (a frame "
                "is not an edge). Widen the region, or point the card at a "
                "region that contains the whole structure."
                % (self.key, where, open_edge, total))
        if int(res.reasons.get("too_many", 0)):
            ctx.warn("[%s] only the first %d measurement lines were used in "
                     "%s; raise 'One line every' to spread them out instead."
                     % (self.key, total, where))
        if n_ok < max(1, int(p["min_lines"])):
            ctx.warn(
                "[%s] only %d of %d measurement lines found a pair of edges in "
                "%s (the card asks for at least %d), so no width is written "
                "for this defect. Most common reasons here: %s. The rest of "
                "the batch is unaffected."
                % (self.key, n_ok, total, where, int(p["min_lines"]),
                   reasons_in_words(res.reasons) or "none recorded"))

    # ---- 給面板與影像疊圖的那一份 ----------------------------------------- #
    def _note(self, ctx: Context, image, rect, res: "algo_edge.ScanResult",
              p: Dict[str, Any], used: str = "") -> None:
        """把「畫得出來所需要的一切」放進 ``ctx.meta["cd"][前綴]``。

        座標**正規化**（跟 `ImageView.set_overlay` 同一套慣例），所以縮放平移與
        換一顆 patch 都不必重算。剖面只存**代表那一條**：每一條都存的話，每顆
        defect 的 meta 會變成幾百 KB（同 `Context._record_change` 只存摘要）。
        """
        h, w = np.asarray(image).shape[:2]
        if not (h and w):
            return
        rx, ry, rw, rh = rect
        along_y = res.axis == algo_edge.AXIS_Y

        def point(along: float, across: float):
            """(沿量測軸, 沿堆疊軸) → 正規化的 (x, y)。"""
            px, py = ((rx + across, ry + along) if along_y
                      else (rx + along, ry + across))
            return round(float(px) / w, 6), round(float(py) / h, 6)

        span = float(rh if along_y else rw)
        lines, marks = [], []
        # ``median_index`` 是代表那一條在**這兩份清單裡**的位置（不是 `res.lines`
        # 裡的）—— 兩份清單只裝量得到的那些，而畫圖的人只拿得到這兩份。
        # 記索引而不是讓下游去比對座標：座標是四捨五入過的。
        median_index = -1
        for ln in res.lines:
            if ln.reason:
                continue
            if ln.index == res.median_line:
                median_index = len(lines)
            lines.append([point(0.0, ln.offset), point(span, ln.offset)])
            marks.append([point(ln.a, ln.offset), point(ln.b, ln.offset)])
        prefix = str(p.get(self.CURRENT_PREFIX, "") or "")
        note: Dict[str, Any] = {
            "region_index": self._region_index(p),
            "axis": res.axis, "criterion": str(p["criterion"]),
            "target": res.target, "target_used": used,
            "region": str(p.get("roi") or ""),
            "stream": str(p.get(self.CURRENT_STREAM, "") or ""),
            "n": int(res.widths.size), "lines": len(res.lines),
            "reasons": dict(res.reasons), "fallbacks": int(res.fallbacks),
            "scan_lines": lines, "edges": marks,
            "median_index": median_index,
            "widths": [round(float(v), 4) for v in res.widths],
            "offsets": [round(float(v), 4) for v in res.offsets],
        }
        if res.median_line >= 0 and res.profile is not None:
            pick = res.lines[res.median_line]
            note["profile"] = {
                "values": [round(float(v), 3) for v in res.profile],
                "a": round(float(pick.a), 4), "b": round(float(pick.b), 4),
                "level": (None if res.level is None
                          else round(float(res.level), 3)),
                "offset": round(float(pick.offset), 4),
            }
        ctx.meta.setdefault(self.META_KEY, {})[prefix] = note


#: 一次最多畫幾條掃描線。128 條疊在一張 128 px 的 patch 上是一片實心的網。
MAX_DRAWN_LINES = 24

#: 輪廓最多存幾個點（等距抽稀）。一顆 30 px 的團外框有上百個點，而每顆 defect
#: 都存一份會讓 meta 變得很肥 —— 同 `Context._record_change` 只存摘要的理由。
MAX_CONTOUR_POINTS = 96

#: 團那一支失敗碼 → 給使用者看的一句話。**跟線那一支的
#: :data:`_REASON_WORDS` 分開，但同一條規矩：每一句都要講得出下一步。**
_BLOB_REASONS = {
    "flat": "nothing in it stands out from the noise enough to be a blob",
    "no_blob": "what stands out is smaller than the smallest blob this card "
               "counts",
    "too_small": "the region is too small to hold a blob",
}


def _shape_of(params: Dict[str, object]) -> str:
    """⓪ 的值（舊 recipe 沒有這個鍵 → ``line``，行為一字不變）。"""
    got = str(params.get("shape", SHAPE_LINE) or SHAPE_LINE)
    return got if got in SHAPES else SHAPE_LINE


def _thin_out(n: int, limit: int, keep: int) -> List[int]:
    """從 ``n`` 條裡等距挑 ``limit`` 條，而且**一定包含 ``keep``**。

    代表那一條非留不可：面板上那張剖面圖畫的就是它，兩邊對不起來的話，使用者
    在影像上找不到剖面圖在講哪一條。
    """
    if n <= 0:
        return []
    if n <= limit:
        return list(range(n))
    step = n / float(limit)
    picked = sorted({min(n - 1, int(i * step)) for i in range(limit)})
    if 0 <= keep < n and keep not in picked:
        picked[len(picked) // 2] = keep
        picked = sorted(set(picked))
    return picked


def _target_used(res: "algo_edge.ScanResult") -> str:
    """整批線裡**多數**量到的是哪一種極性（``""`` = 一條都沒量到）。

    逐條線各自決定極性（``auto`` 時），所以這裡取多數 —— 而少數那些通常是
    量歪的線。這個字最後變成 ``cd_bright``，見 :data:`ALWAYS`。
    """
    votes = {}
    for ln in res.lines:
        if ln.reason:
            continue
        votes[ln.target] = votes.get(ln.target, 0) + 1
    if not votes:
        return ""
    return max(sorted(votes), key=lambda k: votes[k])


def _target_cd(params: Dict[str, object]) -> float:
    try:
        return max(0.0, float(params.get("target_cd", 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0


#: 失敗碼 → 給使用者看的一句話。**每一句都要講得出下一步**。
#:
#: 面板也吃這張表（`ui.inspectors.CdInspector`）—— **只有一份**，不然畫面上
#: 講的原因跟警告訊息裡講的會是兩套說法。
_REASON_WORDS = {
    "open_edge": "the structure ran past the edge of the region",
    "no_pair": "no pair of edges around the middle of the region",
    "flat_profile": "nothing with enough contrast to be an edge",
    "fit_failed": "the edge could not be pinned down",
}


def reasons_in_words(reasons: Dict[str, int]) -> str:
    got = [(n, code) for code, n in (reasons or {}).items()
           if code in _REASON_WORDS]
    got.sort(reverse=True)
    return ", ".join("%s (%d lines)" % (_REASON_WORDS[code], n)
                     for n, code in got[:2])

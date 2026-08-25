# d4t step-card library — authored 2026-07-28 (M1).
"""glv_stats — **Gray level**：在哪量 × 量什麼 × 跟誰比。

三個彼此獨立的問題，順序就是使用者腦裡的順序（F18 第 5 步，2026-08-21）：

======================  ==================================================
① 在哪量？              ``source``（流）× ``roi``（區域）—— 畫布上的線
② 量什麼？              ``metrics`` —— **絕對值，永遠吐**
③ 跟誰比？              ``reference`` —— 相對值，疊在絕對值上（可以不比）
======================  ==================================================

**`compare` 不是另一個 method，是 `reference ≠ none` 的情況。**

以前這裡是 ``method = stats | compare`` 的二選一，而那兩種的**接線方式不同**
（清單埠 vs 角色埠）—— 對製程工程師，那是「還沒開始量，就先被問了一個關於
軟體架構的問題」。更實際的坑是：舊的 ``compare`` **從不輸出絕對值**，所以
「這塊 EPI 的平均灰階是 120」跟「它比隔壁亮 12」不能在同一張卡上同時得到，
使用者得放兩張卡、接兩次線，而那兩張卡各自有機會設得不一樣。

``reference`` 的五個答案（:data:`REFERENCES`）—— 前面四個是一張真值表
（**流一不一樣 × 區域一不一樣**），最後一個是它的自動版：

===============================  ==============================  ==============
值                               跟誰比                          誰在用
===============================  ==============================  ==============
``none``                         不比，只要絕對值                兩種資料
``another region``               另一塊 @ 同一條流                RSEM 大圖
``another stream``               同一塊 @ 另一條流                patch
``another region on another      另一塊 @ 另一條流                EBI↔RSEM 對照
stream``
``the other regions``            ``<name>_others`` @ 同一條流     patch
===============================  ==============================  ==============

五個都只吃「現在這一顆」的資料 —— 所以儀表在預覽時就畫得出來（那是
`ui/inspectors.GlvInspector` 成立的前提）。

舊 recipe 由 `recipe._migrate_compare_method_into_reference` 接住，
**相對值的特徵名逐字不變**（``<prefix>_delta``）—— 那是舊分數表達式不必改寫
的前提。更舊的 ``roi_compare`` 節點先被 `_migrate_roi_compare_into_glv_stats`
變成 ``method="compare"``，再走同一道。

``key`` 仍然是 ``glv_stats``（recipe 的鍵）—— 留它而不是留 ``roi_compare``，
理由是黃金值：兩份 fixture recipe 與 `tests/fixtures/golden/` 都指著它。

為什麼 target/reference 住在**這張卡的參數上**（原 `roi_compare` 的立論，保留）
------------------------------------------------------------------------------
使用者定調（2026-08-18）：「以這張 card 的功能（ROI）來說我不太想要去區分
target 跟 reference⋯⋯我傾向這邊 ROI 只 labeled 出區域，之後再給 card 標註 T 跟 R。」

**角色是「這一次比較」的屬性，不是區域的屬性**。同一塊 EPI 在一個比較裡是
target、在另一個裡是 reference —— 角色寫進區域的話，每一種比較都要複製一份區域，
而區域是**畫**出來的。

GDS 那條路特別需要比較：`roi_from_mask` **只吐 `<name>`**（非週期的 layout
上沒有 `_others` —— 形狀不是複本），所以那條路真正該比的是**層 vs 層**，
也就是 ``another region``。

metrics 的規則
--------------
逗號清單，每個 id 產生一個同名 feature：

- 中心：glv_median / glv_mean / glv_trim<NN>（兩端各去 NN%）
- 離散：glv_mad（median(|x−median|)）/ glv_std / glv_iqr
- 端點：glv_min / glv_max / glv_q<NN>
- 形狀：glv_skew / glv_kurt（excess）/ glv_entropy（bits）/ glv_bimodality
- 計數：glv_above<NN>（灰階高於 NN 的比例）/ glv_sat_frac（貼在 0 或 255 的比例）
- 別名：glv_p50 = glv_median；glv_p<NN> = glv_q<NN>

feature 名稱「照使用者列的寫」（別名不改名），數值一致。

**F18（2026-08-21）把後三群補進來，預設也換成 robust 的那一組**
（``glv_median,glv_mad,glv_min,glv_max``，見 :data:`DEFAULT_METRICS`）。
`glv_bimodality` 是拿來**自檢**的：一塊 ROI 的灰階出現兩座山，通常代表這塊
框裡混了兩種材質 —— 也就是「你量的東西不對」，而那比任何平均值都更早該知道。

compare 算什麼（`algo/glv.compare_pixels`）
-------------------------------------------
**`snr` 的分母是框與框之間，而且不帶正負號**
（``|stat_T − stat_R| / std(參照那一塊每一格的 stat)``）—— 使用者定調
2026-08-21：「SNR 的定義全線幫我改成是 by box（by pixel 會太小），然後 SNR
不會有負值，有負代表亮暗差異而已。」方向是 ``delta`` 的事，而 ``delta`` 照樣
帶正負；參照那一塊少於兩格時，``snr`` / ``tstat`` **不寫**（`_too_thin` 那張表的第三欄）。
公式只住在 `algo/glv.compare_pixels` 一份 —— 同一個名字在不同卡片上算出不同
的東西，是最難發現的那種錯。

"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import numpy as np

from ..algo import glv as algo_glv
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_MEASURE,
)
from ._util import (
    MultiSourceStep, output_prefix_spec, parse_key_list, prefix_features,
    prefix_names, roi_pixels,
)

_P_ALIAS = re.compile(r"^glv_p(\d+)$")
_Q_FORM = re.compile(r"^glv_q(\d+)$")

#: 相對量的特徵名一律以這個開頭（見 :func:`cmp_feature_name`）。
CMP_PREFIX = "cmp_"

#: 「Compare their」預設拿哪一個統計量去比。
DEFAULT_COMPARE_STAT = "glv_mean"

#: ``compare`` 預設勾哪幾個。`delta` 與 `snr` 是兩個不同的問題（差多少 /
#: 差幾個 σ），兩個都預設勾著 —— 只給前者的話，使用者要自己想起來後者存在。
DEFAULT_COMPARE_METRICS = "delta,snr"

#: ``stats`` 預設勾哪幾個（**F18 換成 robust 的那一組**，使用者定調
#: 2026-08-21）。以前是 ``glv_mean,glv_std,glv_p50``。
#:
#: 為什麼換得掉而不會動到任何既有的數字：`add_step` 走
#: ``validate_params(cleared_inputs())``，也就是**每一格都會被寫進 recipe**，
#: 所以既有的檔案帶著自己那一份 metrics；兩份 fixture recipe 也都明寫了。
#: 換掉的只有「之後新加的卡」與「手寫時省略這一格的 recipe」。
#:
#: 為什麼是 median/MAD 而不是 mean/std：e-beam 影像有 charging、hot pixel
#: 與掃描條紋，一顆貼在 255 的壞點就能把 std 拉走 —— 於是「這塊亮不亮」
#: 悄悄變成「這塊有沒有壞點」。min/max 留著是因為它們正好是那個壞點本身，
#: 而「有沒有很亮的一點」常常就是缺陷訊號。
DEFAULT_METRICS = "glv_median,glv_mad,glv_min,glv_max"

#: 卡片庫面板上列得出來的那幾顆（**不是**全部合法的 id —— 任意分位數、
#: 任意修剪比例、任意亮度門檻仍然寫得進 recipe，見 `_canonical`）。
#: 順序＝畫面上的順序；分群與短標籤住在 `ui/widgets.METRIC_GROUPS`
#: （引擎說「有哪些」，UI 說「長什麼樣」）。
METRIC_CHOICES = (
    "glv_median", "glv_mean",
    "glv_mad", "glv_std", "glv_iqr",
    "glv_min", "glv_max",
    "glv_skew", "glv_bimodality",
    "glv_above128", "glv_sat_frac",
)

#: **收起來的那幾顆**（使用者 2026-08-21：「請幫我將這些收起來」）。
#:
#: 收起來 ≠ 刪掉（`CLAUDE.md` §5 那張表）：它們仍然算得出來、手寫得進 recipe、
#: 舊 recipe 照跑、黃金值不動 —— 拿掉的只有卡片庫上那一顆膠囊。要回來的成本
#: 是把字串搬回上面那一份。
#:
#: 為什麼是這三顆：`glv_trim10` 夾在 median 與 mean 中間（三顆都留等於同一件
#: 事量三次）、`glv_kurt` 最難解釋而且已經被包在 `glv_bimodality` 的分母裡、
#: `glv_entropy` 常被對比度與雜訊混淆。
HIDDEN_METRICS = ("glv_trim10", "glv_kurt", "glv_entropy")

#: ``Report`` 那一格列得出來的（同樣**不是**全部合法的 id ——
#: :data:`algo_glv.COMPARE_METRICS` 才是，而驗證看的是後者）。
#:
#: `percent` 收起來的理由跟上面同一種：``percent = (ratio − 1) × 100``，
#: 同一個數字兩種寫法。留下 `ratio`，而參照接近黑的時候該用的是 `contrast`。
#: 「Compare their」列得出來的統計量（**不是**全部合法的 —— 任意分位數走
#: 「+ Percentile…」，而手寫 recipe 什麼 `glv_*` 都填得進來）。
#: 只列中心與兩端那幾個：離散度與形狀那一族要比的話，`spread_ratio` 與
#: `overlap` 已經在 Report 那一格答得更直接。
COMPARE_STAT_CHOICES = (
    "glv_median", "glv_mean", "glv_q25", "glv_q75", "glv_q90",
    "glv_min", "glv_max",
)

COMPARE_CHOICES = (
    "delta", "abs_delta", "ratio", "contrast",
    "snr", "tstat", "pct_rank",
    "overlap", "spread_ratio",
)
HIDDEN_COMPARE_METRICS = ("percent",)

#: 「跟誰比」的四個答案（F18 第 5 步，2026-08-21）。順序＝下拉的順序。
#:
#: **這不是 `method` 換個名字。** 舊的 `method` 是二選一：``stats`` 吐絕對值、
#: ``compare`` 吐差異，而且**從不吐絕對值** —— 所以「這塊 EPI 的平均灰階是 120」
#: 跟「它比隔壁亮 12」不能在同一張卡上同時得到，使用者得放兩張卡、接兩次線，
#: 而那兩張卡各自有機會設得不一樣。
#:
#: 現在絕對值**永遠**吐，相對值疊在它上面。三個問題因此互相獨立：
#: 在哪量（線）× 量什麼（metrics）× 跟誰比（這一格）。
#:
#: 值是給人看的字（下拉直接顯示它們）。它們是穩定的字串 id，除了相等比較
#: 之外沒有人解析它們。
REF_NONE = "none"
REF_REGION = "another region"
REF_STREAM = "another stream"
#: 兩邊都不一樣的那一種。**第一版漏了它**（2026-08-21 使用者問「test 取
#: EPI_center、ref 取 EPI_others 要怎麼拉線」才發現）—— 而漏得很難看：
#: ``another stream`` 那條路把 `reference_region` **安靜地忽略掉**，於是那份
#: 設定跑得完、有數字，而那個數字是「同一塊在另一條流上」的答案。
#:
#: 舊的 `method="compare"` 有四個獨立的角色參數，所以它表達得出這一種；
#: 是我把二選一拆成「跟誰比」的時候把它弄丟的。
REF_BOTH = "another region on another stream"
REF_OTHERS = "the other regions"
REFERENCES = (REF_NONE, REF_REGION, REF_STREAM, REF_BOTH, REF_OTHERS)

#: ``the other regions`` 靠的是 Region 卡的家族慣例：``epi`` 這一塊的「其他同類」
#: 叫 ``epi_others``（`_util.set_region_family`）。**不必多接一條線** ——
#: 那個名字跟 ``epi`` 出自同一張卡，畫布上那條線已經在了（F12 的規矩是
#: 「用到的每一個區域都要有一條線指到定義它的那張卡」，而這裡指的是同一張）。
OTHERS_SUFFIX = "_others"

#: 一個區域底下**好幾個框**的時候，要把它們當成一個像素母體，還是一格一格量
#: （F18 第 6 步，2026-08-21）。
#:
#: 兩種都是對的，答的是不同的問題：
#:
#: ==============  =========================================================
#: ``pooled``      「這一整組交界長什麼樣」—— 分散的 N 個框就是一個母體
#:                 （F8 多框區域本來的用途，也是既有 recipe 的行為）
#: ``each box``    「**哪一格**跟別人不一樣」—— RSEM 大圖上一個名字底下可能是
#:                 幾百個重複單元（`roi_template` 在 1000×1000 上鋪出 625 個
#:                 框），把它們平均起來正好把缺陷抹掉
#: ==============  =========================================================
#:
#: 預設是 ``pooled``：既有 recipe 的 JSON 沒有這個鍵，`validate_params` 會補
#: 預設值 —— 一個會動的預設等於安靜地改掉每一份舊 recipe 的數字。
POOLED = "pooled"
EACH_BOX = "each box"
BOX_MODES = (POOLED, EACH_BOX)

#: 一格一格量之後，每個數字會變成三個（外加一個 ``boxes`` 說總共幾格）。
#:
#: 用字而不是 ``med`` / ``p95``：讀它們的人是製程工程師，而 `_typical` 與
#: `_outlier` 這兩個詞不必查就懂。**刻意只有兩個端點**（計畫書原本還列了
#: p95）—— 「典型長什麼樣」與「最不一樣的那一格是誰」是這個問題的全部，
#: 第三個分位數只是多一欄 CSV。
TYPICAL_SUFFIX = "_typical"
OUTLIER_SUFFIX = "_outlier"
OUTLIER_BOX_SUFFIX = "_outlier_box"
BOX_COUNT = "boxes"


def _canonical(mid: str) -> str:
    """把使用者寫的 metric id 轉成 algo.glv 認得的 id；不認得回傳空字串。"""
    if mid in algo_glv.GLV_STATS:
        return mid
    if mid == "glv_p50":
        return "glv_median"          # 慣用別名：P50 = 中位數
    m = _P_ALIAS.match(mid)
    if m and 0 <= int(m.group(1)) <= 100:
        return f"glv_q{m.group(1)}"  # glv_pNN → glv_qNN
    m = _Q_FORM.match(mid)
    if m and 0 <= int(m.group(1)) <= 100:
        return mid
    # 帶一個數字的那三種（F18）。範圍檢查住在 `algo.glv` 那三支解析器裡 ——
    # `glv_trim60` 那種「兩端各去 60%」不是打錯字就是誤解，兩者都該被擋在
    # 這裡而不是安靜地算出一個空集合的平均。
    if (algo_glv.trim_of(mid) is not None
            or algo_glv.above_of(mid) is not None):
        return mid
    return ""


def _reference_of(params: Dict[str, Any]) -> str:
    """這組參數要跟誰比（不認得的字、沒填的一律當「不比」）。

    **不要在別處直接讀 `params["reference"]`**：這一段是那個判斷的唯一出處，
    而「缺席」的意思是舊 recipe（那時候只有絕對值）。
    """
    got = str(params.get("reference", REF_NONE) or REF_NONE).strip()
    return got if got in REFERENCES else REF_NONE


def _compare_metrics_of(params: Dict[str, Any]) -> List[str]:
    return parse_key_list(params.get("compare_metrics", DEFAULT_COMPARE_METRICS))


def _stats_of(params: Dict[str, Any]) -> List[str]:
    """「拿哪幾個統計量去比」（F18 補課第三輪，2026-08-21）。

    使用者：「Compare their 只能單參數嗎？我不能一次選擇 report glv_median
    或 glv_pn 的資訊嗎？」—— 可以了，這一格跟 Statistics 一樣是一串。

    **鍵沒有改名**（仍然是 ``stat``）：舊 recipe 的 ``"glv_mean"`` 本來就是
    一個合法的「一個元素的清單」，所以不需要遷移。改名才需要。
    """
    got = parse_key_list(params.get("stat", DEFAULT_COMPARE_STAT))
    return got or [DEFAULT_COMPARE_STAT]


def cmp_feature_name(metric: str, stat: str) -> str:
    """相對量的特徵名：``cmp_<metric>[_<stat>]``（F18 補課第三輪）。

    使用者：「絕對量的跟相對量的還是要分類好，不然不清楚命名規則會很痛苦。」
    規則一句話講得完：

    ===============  =========================  ===============================
    看到什麼         意思                       例
    ===============  =========================  ===============================
    ``glv_…``        **這一塊自己**的灰階       ``epi_glv_median``
    ``cmp_…``        跟參照**比出來**的         ``epi_cmp_delta_median``
    ===============  =========================  ===============================

    統計量後綴去掉 ``glv_``（``glv_q90`` → ``q90``）—— 留著的話名字會變成
    ``cmp_delta_glv_q90``，中間那個 ``glv_`` 在講一件已經不成立的事：那個數字
    不是一個灰階，是兩個灰階的差。

    :data:`algo_glv.STAT_FREE_METRICS` 那兩個**不帶後綴**（它們不看 stat）。
    """
    if metric in algo_glv.STAT_FREE_METRICS:
        return CMP_PREFIX + metric
    short = stat[4:] if stat.startswith("glv_") else stat
    return "%s%s_%s" % (CMP_PREFIX, metric, short)


def cmp_feature_names(params: Dict[str, Any]) -> List[str]:
    """這組參數會寫出哪幾個 ``cmp_*``（順序＝勾選的順序，去重）。"""
    stats = _stats_of(params)
    out: List[str] = []
    for metric in _compare_metrics_of(params):
        for stat in stats:
            name = cmp_feature_name(metric, stat)
            if name not in out:
                out.append(name)
    return out


@register_step
class GlvStatsStep(MultiSourceStep):
    """Gray level：量一塊的灰階，可以再說「跟誰比」（見模組 docstring）。"""

    key = "glv_stats"
    #: ``key`` 不動（recipe 的鍵）。短名是使用者要的（F16）。
    # ⚠ **只有 `label` 換掉**（使用者 2026-08-25：「Measure 的 card 順序幫我
    # 改命名&重排：GLV → CD → Focus index」）。`key`（`glv_stats`）是 recipe
    # 的鍵、`glv_*` 是分數表達式裡的變數名 —— 兩者都不准動，那是 §5 那張表裡
    # 「只改 label」跟「改名」的差別（前者零代價，後者要一道遷移）。
    label = "GLV"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Gray levels of a region: pick the statistics you want (median, "
            "spread, percentiles, distribution shape…) and, if you also want "
            "to know how far it is from something else, pick what to compare "
            "it against - the difference, the ratio, or the SNR. The absolute "
            "numbers come out either way.")
    params = [
        ParamSpec(name="source", type="image_keys", direction="in", default="test",
                  help="Image stream to compute statistics on."),
        ParamSpec(name="roi", type="region_keys", direction="in", default="",
                  label="Region",
                  help=("Which region(s) to measure in - drag a line from the "
                        "Region card that defines each one. Two regions here "
                        "means the same statistics measured in both, and every "
                        "number gets its region's name in front of it. "
                        "No line means the whole image.")),
        # 勾選而不是用打的（2026-08-14 使用者要求）。清單是常用的那幾個；
        # 手寫 recipe 仍可以放任何 glv_q<0-100>（清單外的值會列出來並勾著）。
        ParamSpec(name="metrics", type="metric_chips",
                  default=DEFAULT_METRICS,
                  label="Statistics",
                  choices=list(METRIC_CHOICES),
                  help=("Pick the statistics to output - each becomes a "
                        "feature with the same name. Hand-written recipes may "
                        "also use any percentile (glv_q37), any trimmed mean "
                        "(glv_trim05) and any brightness share "
                        "(glv_above200).")),
        ParamSpec(
            name="across_boxes", type="choice", default=POOLED,
            choices=list(BOX_MODES), label="Boxes in the region",
            help=("A region can be many boxes at once (a Golden Cell template "
                  "lays hundreds of them across a big image). pooled treats "
                  "them as one pile of pixels; each box measures every box on "
                  "its own and reports the typical one, the odd one out, and "
                  "which box that was."),
        ),
        # ---- 跟誰比（F18 第 5 步）------------------------------------------
        ParamSpec(
            name="reference", type="choice", default=REF_NONE,
            choices=list(REFERENCES), section="3 · Compare against",
            label="Compare against",
            help=("Leave it at none to just report the gray levels above. "
                  "Pick something else and the card also reports how far the "
                  "region is from it - and the ports change to match what you "
                  "picked."),
        ),
        ParamSpec(
            name="reference_region", type="region_key", direction="in", default="",
            section="3 · Compare against", label="That region",
            show_when=("reference", (REF_REGION, REF_BOTH)),
            help=("The region to judge against - the background, the "
                  "neighbouring cell, another layer. Drag a line from the "
                  "Region card that defines it."),
        ),
        ParamSpec(
            name="reference_source", type="image_key", direction="in",
            default="ref", section="3 · Compare against", label="That stream",
            show_when=("reference", (REF_STREAM, REF_BOTH)),
            help=("The image stream to judge against - normally ref, so the "
                  "same block is compared across the pair."),
        ),
        ParamSpec(
            name="stat", type="metric_chips", default=DEFAULT_COMPARE_STAT,
            section="3 · Compare against",
            show_when=("reference", tuple(r for r in REFERENCES if r != REF_NONE)),
            choices=list(COMPARE_STAT_CHOICES),
            label="Compare their",
            help=("Which number stands for each block. The mean is the usual "
                  "choice; the median ignores a few very bright or dark "
                  "pixels, which matters when a region has a speck in it that "
                  "is not what you are measuring. Tick several and every "
                  "report below is computed for each of them - the statistic "
                  "ends up in the feature name (cmp_delta_median, "
                  "cmp_delta_q90), so they never collide. “+ Percentile…” "
                  "adds any percentile you like."),
        ),
        ParamSpec(
            name="compare_metrics", type="metric_chips",
            default=DEFAULT_COMPARE_METRICS, section="3 · Compare against",
            show_when=("reference", tuple(r for r in REFERENCES if r != REF_NONE)),
            choices=list(COMPARE_CHOICES),
            label="Report",
            help=("Three families. Difference is plain arithmetic on the two "
                  "numbers: delta in gray levels (it keeps the direction), "
                  "abs_delta without it, ratio, and contrast, which is the "
                  "difference over the sum and so survives a nearly black "
                  "reference. Vs boxes asks “is this bigger than the normal "
                  "spread?”: snr counts standard deviations of the "
                  "reference's own box-to-box variation, tstat also counts "
                  "how many boxes there are, and pct_rank just says where the "
                  "target ranks among them. Distributions ignore the "
                  "statistic above and compare all the pixels: overlap is how "
                  "much the two gray-level distributions coincide, "
                  "spread_ratio how much rougher the target is."),
        ),
        # ---- 量得準不準（F18 第 4 步）--------------------------------------
        # 三個都**預設不作用**：既有 recipe 的 JSON 沒有這幾個鍵，
        # `validate_params` 會補預設值 —— 一個會動的預設等於安靜地改掉每一份
        # 舊 recipe 的數字。
        ParamSpec(
            name="exclude_saturated", type="bool", default=False,
            section="4 · Which pixels count",
            label="Ignore pixels at 0 or 255",
            help=("Pixels stuck at pure black or pure white have already lost "
                  "whatever was in them. Leaving them in pulls the average "
                  "towards the edge and inflates the spread."),
        ),
        ParamSpec(
            name="trim_percent", type="float", default=0.0, min=0.0, max=49.0,
            unit="%", section="4 · Which pixels count",
            label="Trim each end by",
            help=("Throw away this share of the darkest and the brightest "
                  "pixels before measuring. A couple of hot pixels can move "
                  "the mean and the spread on a small region; the median "
                  "does not care, but min, max and std do."),
        ),
        ParamSpec(
            name="min_pixels", type="int", default=0, min=0, max=100000,
            unit="px", section="4 · Which pixels count",
            label="Need at least",
            help=("Below this many pixels the card writes blanks instead of "
                  "numbers, and says so. A spread measured on 20 pixels is "
                  "not wrong so much as meaningless - and it looks exactly "
                  "like a good one. 0 = always measure."),
        ),
        output_prefix_spec("center"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = ["glv_median", "glv_mad", "glv_min", "glv_max"]

    #: 留給儀表的直方圖有幾個 bin（見 :meth:`_note_distribution`）。
    HIST_BINS = 64

    # ---- 宣告 ---------------------------------------------------------------
    # **只有一條路**（F18 第 5 步）：整張卡都走 MultiSourceStep 的迴圈，
    # 「跟誰比」只是多接一個埠、多吐幾個數字。舊的 `method` 有兩種接線方式
    # （清單埠 vs 角色埠），於是四個 resolve_* 各自分岔，而使用者得先回答
    # 一個關於軟體架構的問題才能開始量。

    @classmethod
    def feature_names(cls, params: Dict[str, Any]) -> List[str]:
        mids = parse_key_list(params.get("metrics", DEFAULT_METRICS))
        base = mids or list(cls.features_out)
        # 「這塊還能不能信」的那兩個跟著每一塊走（見 `_quality_features`）。
        extra = ["glv_pixels"]
        if int(params.get("min_pixels") or 0):
            extra.append("glv_ok")
        # 相對值疊在絕對值上（不是取代它）—— 那正是這一刀的重點。
        # ⚠ 宣告是「**可能**會產出的」：``snr`` / ``tstat`` 在參照只有一格的
        # defect 上算不出來，那一顆就不會有那一格（同 nm 孿生的理由）。
        if _reference_of(params) != REF_NONE:
            base = base + (cmp_feature_names(params)
                           or [cmp_feature_name("delta", DEFAULT_COMPARE_STAT),
                               cmp_feature_name("snr", DEFAULT_COMPARE_STAT)])
        if str(params.get("across_boxes", POOLED)) == EACH_BOX:
            # 一格一格量：每個數字變成「典型 / 最不一樣的那一格 / 那是第幾格」。
            spread = [n + suffix for n in base
                      for suffix in (TYPICAL_SUFFIX, OUTLIER_SUFFIX,
                                     OUTLIER_BOX_SUFFIX)]
            return spread + [BOX_COUNT] + extra
        return base + extra

    @classmethod
    def legacy_feature_renames(cls, params: Dict[str, Any]) -> Dict[str, str]:
        """舊的相對量特徵名 → 新的（``epi_delta`` → ``epi_cmp_delta_mean``）。

        給 `recipe._migrate_compare_features_into_cmp` 改寫分數表達式用。
        **住在這張卡上而不是 recipe.py**：名字的規則是這張卡的事，兩份說法
        必然有一份會漂（`CLAUDE.md` §0），而漂掉的症狀是遷移改寫成一個不存在
        的變數 —— 跑起來才炸，而且炸在別的地方。

        舊 recipe 的 ``stat`` 一定只有一個（那時候那一格是下拉），所以對應是
        一對一的；真的有好幾個時取第一個 —— 那份 recipe 本來就不是舊的。
        """
        if _reference_of(params) == REF_NONE:
            return {}
        stat = _stats_of(params)[0]
        out: Dict[str, str] = {}
        for key in cls.source_list(params) or [""]:
            for region in cls.region_list(params) or [""]:
                pfx = cls.full_prefix(params, key, region)
                for metric in _compare_metrics_of(params):
                    old = prefix_names(pfx, [metric])[0]
                    new = prefix_names(pfx, [cmp_feature_name(metric, stat)])[0]
                    if old != new:
                        out[old] = new
        return out

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        out = list(super().resolve_reads(params))
        if _reference_of(params) in (REF_STREAM, REF_BOTH):
            name = str(params.get("reference_source", "") or "").strip()
            if name and name not in out:
                out.append(name)
        return out

    @classmethod
    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
        out = list(super().resolve_regions_in(params))
        if _reference_of(params) in (REF_REGION, REF_BOTH):
            name = str(params.get("reference_region", "") or "").strip()
            if name and name not in out:
                out.append(name)
        # ``the other regions`` **不宣告**：`epi_others` 跟 `epi` 出自同一張
        # Region 卡，畫布上那條線已經在了（見 :data:`OTHERS_SUFFIX`）。
        return out

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """挑了「跟誰比」卻沒挑到東西，或挑到自己 —— 兩個都在跑之前擋。"""
        # 兩格清單的值互斥，而**填錯格是安靜的**：把 `delta,snr` 打進
        # Statistics 那一格的人會得到一張跑得完、吐著別的數字的卡。
        wrong = cls._metrics_in_the_wrong_box(params)
        if wrong:
            return wrong
        out: List[str] = []
        if (str(params.get("across_boxes", POOLED)) == EACH_BOX
                and not [r for r in cls.region_list(params) if r]):
            # 「一格一格量」講的是**區域裡的那些框**。沒有區域就是量整張圖，
            # 而整張圖只有一格 —— 那時候這個選項不是錯，是**沒有作用**，
            # 而一個沒有作用的設定看起來跟一個有作用的一模一樣。
            out.append("“Boxes in the region” is set to measure each box, but "
                       "no region is wired in - the whole image is a single "
                       "box, so this setting does nothing. Wire a Region card "
                       "in, or set it back to pooled.")
        ref = _reference_of(params)
        if ref == REF_NONE:
            return out
        mine = [r for r in cls.region_list(params) if r]
        if ref in (REF_REGION, REF_BOTH):
            other = str(params.get("reference_region", "") or "").strip()
            if not other:
                out.append("This card is set to compare against another "
                           "region, but no region is picked yet. Drag a line "
                           "from the Region card that defines it into “That "
                           "region”.")
            elif ref == REF_REGION and mine and other in mine:
                # 同一塊比自己 = delta 恆為 0、snr 恆為 0。跑得完、有數字、
                # 而且那些數字不會因為任何缺陷而改變。
                out.append("The region being measured and the one it is "
                           "compared against are the same region on the same "
                           "image, so every comparison this card produces is "
                           "zero no matter what the defect looks like. Pick a "
                           "different region, or compare against another "
                           "image stream instead.")
        if ref in (REF_STREAM, REF_BOTH):
            other = str(params.get("reference_source", "") or "").strip()
            if not other:
                out.append("This card is set to compare against another image "
                           "stream, but none is wired into “That stream” yet.")
            elif (ref == REF_STREAM and other in cls.source_list(params)
                    and len(cls.source_list(params)) == 1):
                out.append("The stream being measured and the one it is "
                           "compared against are the same stream, so every "
                           "comparison this card produces is zero no matter "
                           "what the defect looks like.")
        elif ref == REF_OTHERS and not mine:
            out.append("“The other regions” needs a region to start from - "
                       "there is nothing for the rest to be the others of. "
                       "Wire a Region card in, or compare against a named "
                       "region instead.")
        return out

    @classmethod
    def _metrics_in_the_wrong_box(cls, params: Dict[str, Any]) -> List[str]:
        """把一格清單的值打進另一格（見 `configuration_issues`）。

        兩組值完全不重疊，所以認得出來 —— 而認得出來的安靜失敗就不該讓它安靜。
        """
        compare_names = set(algo_glv.COMPARE_METRICS)
        stray = [m for m in parse_key_list(params.get("metrics", ""))
                 if m in compare_names]
        if stray:
            return ["“%s” belongs in “Report”, not “Statistics” - it is a "
                    "comparison, not a gray level, so it is being ignored "
                    "where it is." % ", ".join(stray)]
        stray = [m for m in parse_key_list(params.get("compare_metrics", ""))
                 if m not in compare_names]
        if stray:
            return ["“%s” belongs in “Statistics”, not “Report” - it is a gray "
                    "level, not a comparison, so it is being ignored where it "
                    "is." % ", ".join(stray)]
        return []

    # ---- 執行 ---------------------------------------------------------------
    def measure(self, ctx: Context, img, p: Dict[str, Any]):
        """量一張影像的一個區域（迴圈在 MultiSourceStep）。

        絕對值先算，「跟誰比」疊在它上面 —— 兩者**同一組前綴**，所以
        ``epi_glv_median`` 與 ``epi_delta`` 講的看得出來是同一塊。
        """
        mids = parse_key_list(p["metrics"])
        if not mids:
            raise StepError(self.key, "metrics is empty; list at least one statistic (e.g. glv_mean).")

        if self._each_box(ctx, p):
            return self._measure_each_box(ctx, img, p, mids)

        # ``roi_pixels`` 而不是 ``crop_to_roi``：統計量只要「有哪些像素」，
        # 所以分散的多個框（F8 的交會處）也答得出來 —— 那正是
        # 「這一組交界整體長什麼樣」這個問題。單框走同一條路。
        raw = np.asarray(roi_pixels(ctx, self.key, img, p["roi"]),
                         dtype=np.float64).ravel()
        patch, n_raw = self._pixels_that_count(raw, p)

        feats: Dict[str, float] = {}
        thin = self._too_thin(patch, p)
        for mid in mids:
            canon = _canonical(mid)
            if not canon:
                raise StepError(
                    self.key,
                    f"unknown statistic '{mid}'; available: "
                    f"{sorted(algo_glv.GLV_STATS)} or glv_q<0-100> / glv_p<0-100>.")
            if thin:
                continue        # 量不出來就**不寫那一格**（見下面 `_too_thin` 的說明）
            # 飽和比例故意量**原始**的那一份：它回答的是「進來的東西長什麼樣」，
            # 而把貼在 0/255 的像素丟掉之後再問這個問題，答案恆為 0。
            src = raw if canon == "glv_sat_frac" else patch
            feats[mid] = algo_glv.glv_value(src, canon)   # feature 名照使用者列的寫

        extra = self._quality_features(patch, p)
        ref_note: Optional[Dict[str, Any]] = None
        if not thin:
            got, ref_note = self._compare_with_reference(ctx, img, patch, p)
            extra.update(got)
        self._note_distribution(ctx, patch, p, feats, n_raw=n_raw, thin=thin,
                                ref=ref_note)
        if thin:
            ctx.warn(
                "[%s] only %d pixels were left to measure in '%s' (the card "
                "asks for at least %d), so its gray levels are not written "
                "for this defect. The rest of the batch is unaffected."
                % (self.key, int(patch.size), str(p.get("roi") or "the image"),
                   int(p.get("min_pixels") or 0)))
        feats.update(extra)
        return feats

    # ---- 一格一格量（F18 第 6 步）------------------------------------------
    @classmethod
    def _each_box(cls, ctx: Context, p: Dict[str, Any]) -> bool:
        """要一格一格量嗎（只有「這個區域真的有好幾格」時才算數）。"""
        if str(p.get("across_boxes", POOLED)) != EACH_BOX:
            return False
        region = str(p.get(cls.REGION) or "").strip()
        return bool(region) and ctx.roi_count(region) > 1

    def _measure_each_box(self, ctx: Context, img, p: Dict[str, Any],
                          mids: List[str]) -> Dict[str, float]:
        """一個框一個框量，再把幾百格收成三個數字。

        為什麼不是每一格各吐一個特徵：`roi_template` 在一張 1000×1000 上鋪得出
        625 個框，而框的數量**隨影像而異**（換一顆 defect 就不一樣）。逐格吐的
        話 recipe 得寫死一個不存在的數量，CSV 也會多出幾千欄。

        所以吐的是**分布的兩端加一個地址**：

        =====================  ================================================
        ``<n>_typical``        每一格算完之後的中位數 —— 「這一批單元長什麼樣」
        ``<n>_outlier``        離 typical 最遠的那一格的值
        ``<n>_outlier_box``    那是第幾格（0 起算）—— 缺陷定位的答案
        ``boxes``              總共量了幾格
        =====================  ================================================

        「跟誰比」也一格一格算（參照那一塊是共用的），所以 `delta` 那幾個吃的
        是同一套後綴 —— 「跟隔壁材質比，哪一格最不一樣」是 RSEM 大圖上真正的
        問題，而它只有在這個模式下答得出來。
        """
        region = str(p.get(self.REGION) or "")
        arr = np.asarray(img)
        rects = ctx.roi_rects(region, arr.shape[:2])
        ref_px, boxes_by_stat = None, {}
        if _reference_of(p) != REF_NONE:
            ref_px, ref_image, ref_region = self._reference_block(
                ctx, img, p, _reference_of(p))
            # **參照的每一格算一次就好**：它對每一顆 target 的格子都一樣，
            # 而 RSEM 的大圖上「每一格都重算一次」是幾百倍的工。
            boxes_by_stat = self._reference_boxes(ctx, ref_image, p, ref_region)
        compare_names = (cmp_feature_names(p) if ref_px is not None else [])

        per_box: List[Dict[str, float]] = []
        kept_index: List[int] = []
        total_px = 0
        for i, (x, y, w, h) in enumerate(rects):
            if w <= 0 or h <= 0:
                continue
            raw = arr[y:y + h, x:x + w].reshape(-1).astype(np.float64)
            patch, _n_raw = self._pixels_that_count(raw, p)
            total_px += int(patch.size)
            # 太小的格子**跳過**，不是寫 0 —— 一格壓在影像邊上只剩幾個像素是
            # 正常的（框是鋪出來的），而它的統計量會把 typical 拉走。
            if patch.size == 0 or self._too_thin(patch, p):
                continue
            one: Dict[str, float] = {}
            for mid in mids:
                canon = _canonical(mid)
                if not canon:
                    raise StepError(
                        self.key,
                        f"unknown statistic '{mid}'; available: "
                        f"{sorted(algo_glv.GLV_STATS)} or glv_q<0-100> / "
                        f"glv_p<0-100>.")
                one[mid] = algo_glv.glv_value(
                    raw if canon == "glv_sat_frac" else patch, canon)
            if ref_px is not None:
                one.update(self._compare_values(patch, ref_px, p, boxes_by_stat))
            per_box.append(one)
            kept_index.append(i)

        out: Dict[str, float] = {BOX_COUNT: float(len(per_box)),
                                 "glv_pixels": float(total_px)}
        if int(p.get("min_pixels") or 0):
            out["glv_ok"] = 1.0 if per_box else 0.0
        if not per_box:
            ctx.warn(
                "[%s] none of the %d boxes in '%s' had enough pixels to "
                "measure, so this defect has no gray levels from this card. "
                "The rest of the batch is unaffected."
                % (self.key, len(rects), region))
            self._note_distribution(ctx, np.zeros(0), p, {}, n_raw=0, thin=True)
            return out

        for name in list(mids) + list(compare_names):
            values = [b[name] for b in per_box if name in b]
            if not values:
                continue            # 每一格都算不出來（例：參照只有一格）
            typical = float(np.median(values))
            k = int(np.argmax([abs(v - typical) for v in values]))
            out[name + TYPICAL_SUFFIX] = typical
            out[name + OUTLIER_SUFFIX] = float(values[k])
            out[name + OUTLIER_BOX_SUFFIX] = float(kept_index[k])

        # 面板畫的是**典型那一格**的分布（把幾百格疊起來畫等於畫了一張
        # 什麼都看不出來的圖）。
        mid_box = kept_index[int(np.argsort(
            [b[mids[0]] for b in per_box])[len(per_box) // 2])]
        x, y, w, h = rects[mid_box]
        typical_px, n_raw = self._pixels_that_count(
            arr[y:y + h, x:x + w].reshape(-1).astype(np.float64), p)
        self._note_distribution(
            ctx, typical_px, p,
            {n: out[n + TYPICAL_SUFFIX] for n in mids}, n_raw=n_raw,
            box=mid_box, boxes=len(per_box))
        return out

    # ---- 量得準不準（F18 第 4 步）------------------------------------------
    @classmethod
    def _pixels_that_count(cls, raw, p: Dict[str, Any]):
        """哪些像素算數 —— 回 ``(留下來的, 原本有幾個)``。

        三個旋鈕**預設全部不作用**（False / 0 / 0），這不是保守，是必要：
        既有 recipe 的 JSON 裡沒有這幾個鍵，`validate_params` 會補上預設值，
        所以一個會動的預設 = 安靜地改掉每一份舊 recipe 的數字。
        """
        n_raw = int(raw.size)
        kept = raw
        if bool(p.get("exclude_saturated")) and kept.size:
            kept = kept[(kept > 0.0) & (kept < 255.0)]
        trim = float(p.get("trim_percent") or 0.0)
        if trim > 0.0 and kept.size:
            lo, hi = np.percentile(kept, trim), np.percentile(kept, 100.0 - trim)
            kept = kept[(kept >= lo) & (kept <= hi)]
        return kept, n_raw

    @staticmethod
    def _too_thin(patch, p: Dict[str, Any]) -> bool:
        """使用者設的「至少要幾個像素」沒過嗎（``min_pixels=0`` = 永遠量）。

        沒過的時候這張卡**不寫那幾格特徵**（連同一句話），而不是寫 0，也不是
        寫 NaN。三種都想過，這是唯一不會安靜出錯的：

        =========  ==========================================================
        寫 0       0 進得了分數表達式、寫得進 KLARF 的 DSIZE，一路安靜到最後
                   （`cd_x_nm` 恆為 0 就是這樣咬過一次的，見 `steps/cd.py`）
        寫 NaN     **看起來**比較誠實，其實更糟：``NaN < threshold`` 是 False，
                   於是那顆 defect 被安靜地判成真缺陷。這條有測試守著
                   （`tests/test_card_invariants.py` 的 I5），而它是對的 ——
                   NaN 的下游政策要 ADC 段先有（F19），現在還沒有
        不寫       沒有人引用 → 什麼事都不會發生；**有人引用 → 那顆 defect 當場
                   失敗**，訊息裡帶著變數名。吵，但吵在正確的地方
        =========  ==========================================================

        ``glv_ok`` 仍然會寫（值是 0），所以分數表達式有一個乾淨的分支點。
        """
        floor = int(p.get("min_pixels") or 0)
        return bool(floor) and int(patch.size) < floor

    @classmethod
    def _quality_features(cls, patch, p: Dict[str, Any]) -> Dict[str, float]:
        """跟著每一塊一起吐的那幾個「這塊還能不能信」的數字。

        * ``glv_pixels`` —— **永遠吐**。patch 的 ROI 常常只有幾百個像素，而在那個
          數量下離散度本身沒有意義；一個算得出來的 std 看起來跟一個可信的 std
          一模一樣，所以樣本數必須跟著數字一起走。

          ⚠ 名字**不是** ``glv_n_px``（計畫書原本寫的那個）：以 ``_px`` 結尾的
          特徵會被 nm 孿生規則自動配一個 ``_nm``（`_util.nm_twin_names`），
          而「幾個像素」換算成奈米沒有意義。這一格是個**數量**，不是長度。
        * ``glv_ok`` —— **只有設了 ``min_pixels`` 才吐**。沒設的時候它恆為 1，
          而一整欄的 1 是雜訊：它看起來像個答案，實際上什麼都沒說。
        """
        out = {"glv_pixels": float(int(patch.size))}
        if int(p.get("min_pixels") or 0):
            out["glv_ok"] = 0.0 if cls._too_thin(patch, p) else 1.0
        return out

    # ---- 影像上標出「面板正在講的那一格」（2026-08-22）---------------------
    @classmethod
    def overlay_marks(cls, ctx: Any, params: Dict[str, Any],
                      stream: Optional[str] = None) -> Any:
        """把**典型那一格**的外框交出去（正規化座標）。

        為什麼需要它
        ------------
        一個具名區域常常是**一組**框（`roi_cross` 一張 patch 上放二十個很正常）。
        那時候面板畫的是「典型那一格」的分布 —— 把二十格疊起來畫等於畫了一張
        什麼都看不出來的圖 —— 而標題老實地寫著 ``typical box #7 of 20``。

        但**影像上沒有任何東西指得出第 7 格是哪一格**：二十個一模一樣的框，
        使用者只能猜。於是面板與影像在講同一件事，畫面上卻連不起來 ——
        那正是 `Step.overlay_marks` 這個 hook 存在的理由（F18 §9.0：
        「影像上把正在量的那一塊點出來」是整個 Measure 段共用的）。

        只有**一格**的時候不畫：那時候區域框本身就是答案，再描一次只是把線加粗。

        怎麼畫：**四個角各一個實心點**，不是再描一圈外框。
        `ImageView._paint_marks` 的規矩是「線畫到幾乎看不見（alpha 70）、
        點畫滿」—— 用線描的外框會跟區域框**完全重疊、同一個顏色**，等於沒畫
        （2026-08-22 截圖出來才看到）。四個角點是這個畫面既有的語彙，
        而且不會被誤讀成一個新的邊界。

        ``labels`` 給區域名，顏色因此跟影像上那個區域的框一模一樣；
        ``focus`` 指著它，所以是滿的 alpha。
        """
        notes = (getattr(ctx, "meta", None) or {}).get("glv_hist") or []
        want = str(stream or "").strip()
        lines: List[Any] = []
        points: List[Any] = []
        labels: List[str] = []
        focus = -1
        for note in notes:
            if not isinstance(note, dict):
                continue
            mine = str(note.get("stream") or "").strip()
            if want and mine and mine != want:
                continue               # 這一份是量在別張影像上的
            if int(note.get("boxes") or 0) <= 1:
                continue               # 只有一格 —— 區域框本身就是答案
            name = str(note.get("region") or "")
            idx = int(note.get("box", -1))
            try:
                rects = list(ctx.roi_norm_rects(name)) if name else []
            except Exception:          # noqa: BLE001 — 顯示用，不能擋畫面
                continue
            if not (0 <= idx < len(rects)):
                continue               # 對不上就整組不畫（同 `set_marks` 的規矩）
            x, y, w, h = (float(v) for v in rects[idx])
            corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            if focus < 0:
                focus = len(lines)     # 面板畫的就是這一格 → 滿的 alpha
            # 一條線段（上緣，畫得很淡）＋ 四個角點（畫滿）。線段是必要的：
            # ``points[i]`` 的定義是「第 i 條線段上的點」，兩串必須等長。
            lines.append([corners[0], corners[1]])
            points.append(corners)
            labels.append(name)
        return lines, points, focus, labels

    def _note_distribution(self, ctx: Context, patch, p: Dict[str, Any],
                           feats: Dict[str, float], n_raw: int = 0,
                           thin: bool = False, box: int = -1,
                           boxes: int = 0,
                           ref: Optional[Dict[str, Any]] = None) -> None:
        """把這一塊的灰階分布留給儀表（F18 第 2 步）。

        **畫面上的那張圖就是引擎算的這一份** —— UI 不自己再跑一次統計，不然
        面板上的曲線跟真的寫出去的數字有機會不一樣（`ui/inspectors.py` 檔頭
        的第 2 條）。這跟 Enhance 卡的 ``stream_change`` 是同一條路，而那正是
        它的面板**預覽就有東西**、Spread 卻要跑完一批的差別。

        64 個 bin：面板寬度撐死兩百多個畫素，256 個 bin 有一半畫不出來，而這
        份東西會跟著結果被送進 worker 與資料庫。
        """
        arr = np.asarray(patch, dtype=np.float64).ravel()
        counts, _edges = algo_glv.pixel_hist(arr, bins=self.HIST_BINS)
        ctx.meta.setdefault("glv_hist", []).append({
            "stream": str(p.get(self.CURRENT_STREAM, "") or ""),
            "region": str(p.get(self.REGION, "") or ""),
            "prefix": str(p.get(self.CURRENT_PREFIX, "") or ""),
            "n": int(arr.size),
            # 三個旋鈕丟掉了幾成 —— 面板要說得出「你量的不是整塊」。
            "n_raw": int(n_raw or arr.size),
            "thin": bool(thin),
            # 一格一格量的時候，畫的是**典型那一格**（把幾百格疊起來畫等於
            # 畫了一張什麼都看不出來的圖）—— 面板要說得出那是哪一格。
            "box": int(box),
            "boxes": int(boxes),
            # 「貼在 0 或 255 的比例」永遠記著 —— 它不是使用者勾了才成立的事實，
            # 而面板要用它回答「這塊還能不能信」。勾了 `glv_sat_frac` 的人另外
            # 得到一個同名特徵，那是**輸出**，這裡這個是**診斷**。
            "sat": float(((arr <= 0.0) | (arr >= 255.0)).mean()) if arr.size else 0.0,
            "bins": [int(c) for c in counts],
            "marks": {str(k): float(v) for k, v in feats.items()},
            # 參照那一塊（`reference == none` 時是 None）—— 面板把它**疊在
            # 同一把尺上**（使用者 2026-08-21：「疊上參照那條分布」）。
            # 「相對」在這張卡上一直都只是幾個數字，而數字看不出「這個差在不在
            # 雜訊裡」；兩條分布疊起來一眼就看得出來。
            "ref": dict(ref) if ref else None,
        })

    # ---- 跟誰比（F18 第 5 步）----------------------------------------------
    def _compare_with_reference(self, ctx: Context, img, patch,
                                p: Dict[str, Any]) -> Dict[str, float]:
        """這一塊跟它的參照差多少（``reference == none`` 時回空的）。

        原 `roi_compare` / `method="compare"` 的算術逐行搬過來 —— **算法沒有
        變**，變的是它不再需要一組自己的角色埠：target 就是這張卡正在量的那
        一塊（迴圈給的），reference 由 `reference` 那一格決定。

        ``snr`` 的公式仍然是 ``(μ_T − μ_R) / σ_R``（`algo.glv.compare_pixels`）
        —— 不發明第三種寫法，同一個名字在不同卡片上算出不同的東西是最難發現
        的那種錯。
        """
        ref = _reference_of(p)
        if ref == REF_NONE:
            return {}, None
        metrics = _compare_metrics_of(p)
        if not metrics:
            raise StepError(self.key, "tick at least one thing to report "
                                      "(delta, snr, …).")
        bad = [m for m in metrics if m not in algo_glv.COMPARE_METRICS]
        if bad:
            raise StepError(self.key, "unknown comparison %r; available: %s"
                            % (bad[0], ", ".join(algo_glv.COMPARE_METRICS)))

        ref_px, ref_image, ref_region = self._reference_block(ctx, img, p, ref)
        boxes_by_stat = self._reference_boxes(ctx, ref_image, p, ref_region)
        ref_boxes = boxes_by_stat.get(_stats_of(p)[0]) or []
        out = self._compare_values(patch, ref_px, p, boxes_by_stat)
        if len(ref_boxes) < 2 and set(algo_glv.BOX_METRICS) & set(metrics):
            # 分母沒有東西可裝的時候要講話，而不是留一格 nan 讓人猜。
            ctx.warn(
                "[%s] the block it compares against ('%s') is a single box, so "
                "there is no box-to-box spread to divide by - snr, tstat and "
                "pct_rank are blank for this defect. Point it at a region "
                "that is laid "
                "out as repeated boxes (a Golden Cell template, for example)."
                % (self.key, self._ref_label(p, ref)))

        # 儀表用（同其他卡的慣例）：**畫面上的數字就是引擎算的這一份**。
        here = str(p.get(self.REGION) or "the image")
        ctx.meta.setdefault("compares", {})["%s_vs_%s" % (here, self._ref_label(p, ref))] = {
            "target": here,
            "reference": self._ref_label(p, ref),
            "target_source": str(p.get(self.CURRENT_STREAM, "")),
            "reference_source": (str(p.get("reference_source", ""))
                                 if ref == REF_STREAM
                                 else str(p.get(self.CURRENT_STREAM, ""))),
            "stat": ",".join(_stats_of(p)),
            "target_px": int(np.asarray(patch).size),
            "reference_px": int(np.asarray(ref_px).size),
            # **完整的特徵名**（含前綴）—— 特徵表要靠它說得出「這個數字是跟誰
            # 比出來的」，而那件事名字裡沒有（`epi_cmp_delta_median` 不講 mg）。
            "names": [prefix_names(str(p.get(self.CURRENT_PREFIX, "") or ""),
                                   [n])[0] for n in out],
            "values": dict(out),
        }
        # 面板要**把參照那條分布疊上去**（使用者 2026-08-21：「疊上參照那條
        # 分布」）。算式與畫面的數字因此出自同一次計算 —— UI 不自己再跑一次。
        ref_counts, _e = algo_glv.pixel_hist(
            np.asarray(ref_px, dtype=np.float64).ravel(), bins=self.HIST_BINS)
        note = {
            "label": self._ref_label(p, ref),
            "bins": [int(c) for c in ref_counts],
            "n": int(np.asarray(ref_px).size),
            "boxes": len(ref_boxes),
            # 兩邊的 stat 各一個 —— 面板用它們畫那一段 Δ。
            "marks": {stat: float(algo_glv.glv_value(
                np.asarray(ref_px, dtype=np.float64).ravel(),
                _canonical(stat) or DEFAULT_COMPARE_STAT))
                for stat in _stats_of(p)},
            "here": {stat: float(algo_glv.glv_value(
                np.asarray(patch, dtype=np.float64).ravel(),
                _canonical(stat) or DEFAULT_COMPARE_STAT))
                for stat in _stats_of(p)},
            "values": dict(out),
        }
        return out, note

    @classmethod
    def _reference_boxes(cls, ctx: Context, image, p: Dict[str, Any],
                         region: str) -> Dict[str, List[float]]:
        """參照那一塊**每一格**的 stat —— 一個勾到的統計量一份。

        算一次就好：一格一格量的時候，這一份對**每一顆 target 的格子都一樣**
        （參照是共用的），而 RSEM 的大圖上那是幾百次重算。
        """
        out: Dict[str, List[float]] = {}
        for stat in _stats_of(p):
            out[stat] = cls._box_values(ctx, image, p, region, stat)
        return out

    @classmethod
    def _compare_values(cls, patch, ref_px, p: Dict[str, Any],
                        boxes_by_stat: Dict[str, List[float]]
                        ) -> Dict[str, float]:
        """一塊像素跟參照比出來的所有 ``cmp_*``（勾幾個統計量就算幾輪）。

        **算不出來的那一格不寫**（同 `_too_thin` 的三選一）：NaN 看起來比較
        誠實，實際更糟 —— ``NaN < threshold`` 是 False，那顆 defect 會被
        安靜地判成真缺陷（`tests/test_card_invariants.py` 的 I5 守著）。
        """
        metrics = _compare_metrics_of(p)
        out: Dict[str, float] = {}
        for stat in _stats_of(p):
            # **不看 stat 的那兩個只算第一輪**：它們對每一個統計量都是同一個
            # 答案，而 `overlap` 是一趟 256 bin 的直方圖 —— 一格一格量的 RSEM
            # 大圖上，沒有這一行就是同一張圖重算幾百次。
            want = [m for m in metrics if cmp_feature_name(m, stat) not in out]
            if not want:
                continue
            canon = _canonical(stat) or DEFAULT_COMPARE_STAT
            got = algo_glv.compare_pixels(
                patch, ref_px, canon,
                reference_boxes=boxes_by_stat.get(stat) or [], want=want)
            for m in want:
                v = got.get(m)
                if v is not None and np.isfinite(v):
                    out[cmp_feature_name(m, stat)] = float(v)
        return out

    @classmethod
    def _ref_label(cls, p: Dict[str, Any], ref: str) -> str:
        """參照那一塊叫什麼（面板與 `ctx.meta` 用）—— **講得出流與區域**。"""
        region = str(p.get("reference_region", "") or "?")
        stream = str(p.get("reference_source", "") or "?")
        if ref == REF_REGION:
            return region
        if ref == REF_STREAM:
            return "%s @ %s" % (str(p.get(cls.REGION) or "the image"), stream)
        if ref == REF_BOTH:
            return "%s @ %s" % (region, stream)
        return str(p.get(cls.REGION) or "") + OTHERS_SUFFIX

    def _reference_block(self, ctx: Context, img, p: Dict[str, Any], ref: str):
        """參照那一塊 → ``(全部像素, 它住的那張影像, 它的區域名)``。

        後兩個是給 :meth:`_reference_boxes` 用的：勾了好幾個統計量的時候，
        「每一格的 stat」一個統計量一份，而算它需要影像與區域名。

        第二個回傳值是 ``snr`` / ``tstat`` 的分母來源 —— **框與框之間**，不是
        像素與像素之間（使用者定調 2026-08-21：「SNR 的定義全線幫我改成是
        by box（by pixel 會太小）」，算式見 `algo.glv.compare_pixels`）。
        參照只有一格時它是空的，那兩個數字就不寫；**不退回 per-pixel** ——
        同一個名字在不同情況下算出不同的東西，是最難發現的那種錯。

        拿不到那一塊的時候講出**真正的原因**：`<name>_others` 在只有一份的
        patch 上是**不存在**的（不是空的）—— 那不是設定錯，是這一顆沒有基準，
        而使用者要分得出那兩件事（見 `_util.set_region_family`）。
        """
        region = str(p.get(self.REGION) or "")
        image = img
        if ref in (REF_STREAM, REF_BOTH):
            name = str(p.get("reference_source", "") or "").strip()
            image = ctx.images.get(name)
            if image is None:
                raise StepError(
                    self.key,
                    "the stream to compare against ('%s') does not exist "
                    "here; available: %s."
                    % (name, ", ".join(sorted(ctx.images)) or "none"))
        want = region if ref == REF_STREAM else (
            str(p.get("reference_region", "") or "").strip()
            if ref in (REF_REGION, REF_BOTH) else region + OTHERS_SUFFIX)
        if not want:
            raise StepError(
                self.key,
                "this card is set to compare against another region, but "
                "none is picked - drag a line from the Region card that "
                "defines it.")
        if want not in ctx.roi_names():
            why = dict(ctx.meta.get("regions_absent") or {}).get(want, "")
            raise StepError(
                self.key,
                "the region to compare against ('%s') is not on this "
                "defect%s. The rest of the batch is unaffected."
                % (want, (" — %s" % why) if why else
                   " (no card upstream produced it)"))
        return (roi_pixels(ctx, self.key, image, want), image, want)

    @classmethod
    def _box_values(cls, ctx: Context, image, p: Dict[str, Any],
                    region: str, stat: str) -> List[float]:
        """一個區域**每一格**的 ``stat``（只有一格時回空的）。"""
        if ctx.roi_count(region) <= 1:
            return []
        canon = _canonical(stat) or DEFAULT_COMPARE_STAT
        arr = np.asarray(image)
        out: List[float] = []
        for x, y, w, h in ctx.roi_rects(region, arr.shape[:2]):
            if w <= 0 or h <= 0:
                continue
            kept, _n = cls._pixels_that_count(
                arr[y:y + h, x:x + w].reshape(-1).astype(np.float64), p)
            if kept.size:
                out.append(algo_glv.glv_value(kept, canon))
        return out

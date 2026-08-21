# d4t step-card library — authored 2026-07-28 (M1).
"""glv_stats — **Gray level**：一張卡，兩種問法。

F16（2026-08-20）把 `roi_compare`（Compare regions）併進來 —— 使用者：
「Gray level Stats 跟 Compare regions 應該是做同樣的事（量 GLV 相關）吧，
留其中一個就好」。

它們**不是**同一件事，而那正是它變成 `method` 而不是被刪掉的理由：

===========  ==================================  ==============================
method       吃什麼                              吐什麼
===========  ==================================  ==============================
``stats``    一條以上的流 × 一個以上的區域        **絕對值** glv_mean / glv_std
             （多連一累加）                       / 任意分位數
``compare``  **兩個角色**：target 與 reference    **差異** delta / ratio /
             （各自一條流 + 一個區域）            percent / snr / tstat
===========  ==================================  ==============================

`compare` 的 ``stat`` 只是「用哪個數字代表每一塊」，它**從不輸出那個絕對值** ——
所以「這塊 EPI 的平均灰階是 120」只有 ``stats`` 答得出來，而它是 ADC 判亮暗常常
要的東西。留一張刪一張會少掉一整類問題，收成一個下拉才是「同一家族收成一張卡的
method」（F7-10／F7-20 的慣例）。

⚠ **兩種 method 的接線方式不同**，這是這張卡唯一特別的地方：``stats`` 的來源是
清單（`image_keys` / `region_keys`，第二條線**累加**），``compare`` 的來源是
**角色埠**（`image_key` / `region_key`，第二條線**取代**）。畫布上的埠因此隨
``method`` 變形 —— 那是 `resolve_reads` / `resolve_regions_in` 本來就是
param-dependent 的直接後果，不是新機制。`tests/test_ui_f10_canvas_reality.py`
的 `ROLE_PORTS` 那條不變量改成「**兩種接線方式各自合法、而且不同時出現**」。

``key`` 仍然是 ``glv_stats``（recipe 的鍵）—— 留它而不是留 ``roi_compare``，
理由是黃金值：兩份 fixture recipe 與 `tests/fixtures/golden/` 都指著它。
舊的 ``roi_compare`` 節點由 `recipe._migrate_roi_compare_into_glv_stats` 接住。

metrics（``stats``）的規則
--------------------------
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
`delta` / `ratio` / `percent` / `snr` / `tstat`。``snr`` 的公式是
``(μ_T − μ_R) / σ_R`` —— 那是 e-beam 帶正負號的 SNR 慣例，而這個 repo 已經有
兩個地方在用它（`algo.glv.group_snr`、`algo/snr`）。**不發明第三種寫法**：
同一個名字在不同卡片上算出不同的東西，是最難發現的那種錯。

為什麼 target/reference 住在**這張卡的參數上**（原 `roi_compare` 的立論，保留）
------------------------------------------------------------------------------
使用者定調（2026-08-18）：「以這張 card 的功能（ROI）來說我不太想要去區分
target 跟 reference⋯⋯我傾向這邊 ROI 只 labeled 出區域，之後再給 card 標註 T 跟 R。」

**角色是「這一次比較」的屬性，不是區域的屬性**。同一塊 EPI 在一個比較裡是
target、在另一個裡是 reference —— 角色寫進區域的話，每一種比較都要複製一份區域，
而區域是**畫**出來的。

而且是**兩對**（流 + 區域）不是一條流兩個區域，因為使用者列的三種情況裡有一種
兩邊的流不一樣：

| 情況 | target | reference |
|---|---|---|
| patch，跟自己兩側的 EPI 比 | `epi_center` @ test | `epi_others` @ test |
| patch，跟 ref 那張的同一塊比 | `epi` @ **test** | `epi` @ **ref** |
| 單張 source（沒有 ref）| `epi_center` @ single | `epi_others` @ single |

GDS 那條路特別需要 compare：`roi_from_mask` **只吐 `<name>`**（非週期的 layout
上沒有 `_others` —— 形狀不是複本），所以那條路真正該比的是**層 vs 層**。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

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
    "glv_median", "glv_mean", "glv_trim10",
    "glv_mad", "glv_std", "glv_iqr",
    "glv_min", "glv_max",
    "glv_skew", "glv_kurt", "glv_entropy", "glv_bimodality",
    "glv_above128", "glv_sat_frac",
)

#: 這張卡的兩種問法。順序＝下拉的順序，第一個是預設。
METHOD_STATS = "stats"
METHOD_COMPARE = "compare"
METHODS = (METHOD_STATS, METHOD_COMPARE)

#: 只在 ``stats`` 下顯示 / 只在 ``compare`` 下顯示。
_WHEN_STATS = ("method", (METHOD_STATS,))
_WHEN_COMPARE = ("method", (METHOD_COMPARE,))


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


def _method_of(params: Dict[str, Any]) -> str:
    """這組參數用的是哪一種問法（不認得的字一律當 ``stats``）。

    **不要用 `params.get("method")` 直接比**：`method` 缺席的意思是「舊 recipe」，
    而舊的 `glv_stats` 就是 ``stats``。這一段是那個判斷的唯一出處。
    """
    return (METHOD_COMPARE if str(params.get("method", METHOD_STATS)).strip()
            == METHOD_COMPARE else METHOD_STATS)


def _compare_metrics_of(params: Dict[str, Any]) -> List[str]:
    return parse_key_list(params.get("compare_metrics", DEFAULT_COMPARE_METRICS))


@register_step
class GlvStatsStep(MultiSourceStep):
    """Gray level：量一塊的絕對灰階，或比兩塊的差異（見模組 docstring）。"""

    key = "glv_stats"
    #: ``key`` 不動（recipe 的鍵）。短名是使用者要的（F16）。
    label = "Gray level"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Gray levels, two ways: measure a region and write out its "
            "statistics (median, spread, percentiles, distribution shape…), "
            "or compare two regions and write out how far apart they are. "
            "Pick which with “What to do”.")
    params = [
        ParamSpec(
            name="method", type="choice", default=METHOD_STATS,
            choices=list(METHODS), label="What to do",
            help=("stats = measure one region (or several) and report its own "
                  "gray levels. compare = take two regions, one as the target "
                  "and one as the reference, and report how far apart they "
                  "are. The two need different connections, so the ports on "
                  "this card change when you switch."),
        ),
        # ---- method = stats ------------------------------------------------
        ParamSpec(name="source", type="image_keys", direction="in", default="test",
                  show_when=_WHEN_STATS,
                  help="Image stream to compute statistics on."),
        ParamSpec(name="roi", type="region_keys", direction="in", default="",
                  label="Region", show_when=_WHEN_STATS,
                  help=("Which region(s) to measure in - drag a line from the "
                        "Region card that defines each one. Two regions here "
                        "means the same statistics measured in both, and every "
                        "number gets its region's name in front of it. "
                        "No line means the whole image.")),
        # 勾選而不是用打的（2026-08-14 使用者要求）。清單是常用的那幾個；
        # 手寫 recipe 仍可以放任何 glv_q<0-100>（清單外的值會列出來並勾著）。
        ParamSpec(name="metrics", type="metric_chips",
                  default=DEFAULT_METRICS,
                  label="Statistics", show_when=_WHEN_STATS,
                  choices=list(METRIC_CHOICES),
                  help=("Pick the statistics to output - each becomes a "
                        "feature with the same name. Hand-written recipes may "
                        "also use any percentile (glv_q37), any trimmed mean "
                        "(glv_trim05) and any brightness share "
                        "(glv_above200).")),
        # ---- method = compare ----------------------------------------------
        ParamSpec(
            name="target_source", type="image_key", direction="in",
            default="test", section="1 · Target (the thing being judged)",
            label="Measure it on", show_when=_WHEN_COMPARE,
            help="Which image stream the target region is measured on.",
        ),
        ParamSpec(
            name="target_region", type="region_key", direction="in", default="",
            section="1 · Target (the thing being judged)",
            label="Target region", show_when=_WHEN_COMPARE,
            help=("The region being judged - normally the one the defect is "
                  "in. Leave a Region card upstream and its names appear "
                  "here."),
        ),
        ParamSpec(
            name="reference_source", type="image_key", direction="in",
            default="test", section="2 · Reference (what it is judged against)",
            label="Measure it on", show_when=_WHEN_COMPARE,
            help=("Which image stream the reference region is measured on. "
                  "Point it at ref to compare the same block across the pair; "
                  "leave it on the same stream as the target to compare "
                  "against another region of the same image."),
        ),
        ParamSpec(
            name="reference_region", type="region_key", direction="in", default="",
            section="2 · Reference (what it is judged against)",
            label="Reference region", show_when=_WHEN_COMPARE,
            help=("What the target is judged against - the same material "
                  "elsewhere on this image (<name>_others), the same block on "
                  "the other image, or a different layer entirely."),
        ),
        ParamSpec(
            name="stat", type="choice", default="glv_mean",
            section="3 · What to compare", show_when=_WHEN_COMPARE,
            choices=["glv_mean", "glv_median", "glv_q25", "glv_q75",
                     "glv_q90", "glv_min", "glv_max"],
            label="Compare their",
            help=("Which single number stands for each region. The mean is "
                  "the usual choice; the median ignores a few very bright or "
                  "dark pixels, which matters when a region has a speck in it "
                  "that is not what you are measuring."),
        ),
        ParamSpec(
            name="compare_metrics", type="multi_choice",
            default=DEFAULT_COMPARE_METRICS,
            section="3 · What to compare", show_when=_WHEN_COMPARE,
            choices=list(algo_glv.COMPARE_METRICS),
            label="Report",
            help=("delta is the plain difference in gray levels. snr divides "
                  "it by how much the reference itself varies, which answers "
                  "“is this bigger than the normal spread?” - the same signed "
                  "convention the rest of d4t uses. tstat is snr with the "
                  "region sizes taken into account, which matters when one "
                  "region has far more pixels than the other. ratio and "
                  "percent are the same difference expressed relative to the "
                  "reference."),
        ),
        # ---- 量得準不準（F18 第 4 步）--------------------------------------
        # 三個都**預設不作用**：既有 recipe 的 JSON 沒有這幾個鍵，
        # `validate_params` 會補預設值 —— 一個會動的預設等於安靜地改掉每一份
        # 舊 recipe 的數字。
        ParamSpec(
            name="exclude_saturated", type="bool", default=False,
            section="4 · Which pixels count", show_when=_WHEN_STATS,
            label="Ignore pixels at 0 or 255",
            help=("Pixels stuck at pure black or pure white have already lost "
                  "whatever was in them. Leaving them in pulls the average "
                  "towards the edge and inflates the spread."),
        ),
        ParamSpec(
            name="trim_percent", type="float", default=0.0, min=0.0, max=49.0,
            unit="%", section="4 · Which pixels count", show_when=_WHEN_STATS,
            label="Trim each end by",
            help=("Throw away this share of the darkest and the brightest "
                  "pixels before measuring. A couple of hot pixels can move "
                  "the mean and the spread on a small region; the median "
                  "does not care, but min, max and std do."),
        ),
        ParamSpec(
            name="min_pixels", type="int", default=0, min=0, max=100000,
            unit="px", section="4 · Which pixels count", show_when=_WHEN_STATS,
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
    # `compare` 那一半不走 MultiSourceStep 的迴圈（它的兩條流有角色，排不成
    # 一串），所以四個 resolve_* 都要分岔。分岔點只有 `_method_of` 一個。

    @classmethod
    def feature_names(cls, params: Dict[str, Any]) -> List[str]:
        mids = parse_key_list(params.get("metrics", DEFAULT_METRICS))
        base = mids or list(cls.features_out)
        # 「這塊還能不能信」的那兩個跟著每一塊走（見 `_quality_features`）。
        extra = ["glv_pixels"]
        if int(params.get("min_pixels") or 0):
            extra.append("glv_ok")
        return base + extra

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        if _method_of(params) != METHOD_COMPARE:
            return super().resolve_reads(params)
        out: List[str] = []
        for key in ("target_source", "reference_source"):
            name = str(params.get(key, "") or "").strip()
            if name and name not in out:
                out.append(name)
        return out

    @classmethod
    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
        if _method_of(params) != METHOD_COMPARE:
            return super().resolve_regions_in(params)
        out: List[str] = []
        for key in ("target_region", "reference_region"):
            name = str(params.get(key, "") or "").strip()
            if name and name not in out:
                out.append(name)
        return out

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        if _method_of(params) != METHOD_COMPARE:
            return super().resolve_features(params)
        # compare **只吃 output_prefix**，不加流名／區域名前綴 —— 那兩個前綴的
        # 意思是「同一件事做在好幾個東西上」，而這裡的兩條流有角色之分。
        # （也是舊 `roi_compare` recipe 的特徵名逐字不變的前提。）
        return prefix_names(params.get("output_prefix", ""),
                            _compare_metrics_of(params)
                            or ["delta", "snr"])

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """`compare` 要兩塊、不能挑到同一塊，而且清單不能填錯格。

        （`stats` 只有最後那一條 —— 它沒有「兩塊」的概念。）
        """
        # 兩種 method 各有一格清單，而**填錯格是安靜的**：`compare` 只看
        # `compare_metrics`，所以把 `delta,snr` 打進 Statistics 那一格的人
        # 會得到一張跑得完、吐著預設值、而且完全不理他的卡。兩組值互斥，
        # 所以認得出來 —— 認得出來的安靜失敗就不該讓它安靜。
        wrong = cls._metrics_in_the_wrong_box(params)
        if wrong:
            return wrong
        if _method_of(params) != METHOD_COMPARE:
            return []
        t = str(params.get("target_region", "") or "").strip()
        r = str(params.get("reference_region", "") or "").strip()
        ts = str(params.get("target_source", "") or "").strip()
        rs = str(params.get("reference_source", "") or "").strip()
        out: List[str] = []
        if not t or not r:
            out.append("This card has no pair to compare yet. Pick a "
                       "“Target region” and a “Reference region” - the names "
                       "come from the Region card upstream.")
        elif t == r and ts == rs:
            # 同一塊比自己 = delta 恆為 0、snr 恆為 0。跑得完、有數字、
            # 而且那些數字不會因為任何缺陷而改變。
            out.append("The target and the reference are the same region on "
                       "the same image, so every number this card produces is "
                       "zero no matter what the defect looks like. Pick a "
                       "different region, or point one of them at another "
                       "image stream.")
        return out

    @classmethod
    def _metrics_in_the_wrong_box(cls, params: Dict[str, Any]) -> List[str]:
        """把一種 method 的清單打進另一種的格子裡（見 `configuration_issues`）。"""
        compare_names = set(algo_glv.COMPARE_METRICS)
        if _method_of(params) == METHOD_COMPARE:
            stray = [m for m in parse_key_list(params.get("metrics", ""))
                     if m in compare_names]
            if stray:
                return ["“%s” belongs in “Report”, not “Statistics” - this "
                        "card is set to compare, so the Statistics box is not "
                        "read at all and those values are being ignored."
                        % ", ".join(stray)]
            return []
        stray = [m for m in parse_key_list(params.get("compare_metrics", ""))
                 if m not in compare_names]
        if stray:
            return ["“%s” belongs in “Statistics”, not “Report” - this card is "
                    "set to measure one region, so the Report box is not read "
                    "at all and those values are being ignored."
                    % ", ".join(stray)]
        return []

    # ---- 執行 ---------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        if _method_of(params) != METHOD_COMPARE:
            return super().run(ctx, params)      # MultiSourceStep 的迴圈
        return self._run_compare(ctx, params)

    def measure(self, ctx: Context, img, p: Dict[str, Any]):
        """``stats``：量一張影像的一個區域（迴圈在 MultiSourceStep）。"""
        mids = parse_key_list(p["metrics"])
        if not mids:
            raise StepError(self.key, "metrics is empty; list at least one statistic (e.g. glv_mean).")

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
        self._note_distribution(ctx, patch, p, feats, n_raw=n_raw, thin=thin)
        if thin:
            ctx.warn(
                "[%s] only %d pixels were left to measure in '%s' (the card "
                "asks for at least %d), so its gray levels are not written "
                "for this defect. The rest of the batch is unaffected."
                % (self.key, int(patch.size), str(p.get("roi") or "the image"),
                   int(p.get("min_pixels") or 0)))
        feats.update(extra)
        return feats

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

    def _note_distribution(self, ctx: Context, patch, p: Dict[str, Any],
                           feats: Dict[str, float], n_raw: int = 0,
                           thin: bool = False) -> None:
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
            # 「貼在 0 或 255 的比例」永遠記著 —— 它不是使用者勾了才成立的事實，
            # 而面板要用它回答「這塊還能不能信」。勾了 `glv_sat_frac` 的人另外
            # 得到一個同名特徵，那是**輸出**，這裡這個是**診斷**。
            "sat": float(((arr <= 0.0) | (arr >= 255.0)).mean()) if arr.size else 0.0,
            "bins": [int(c) for c in counts],
            "marks": {str(k): float(v) for k, v in feats.items()},
        })

    def _run_compare(self, ctx: Context, params: Dict[str, Any]) -> Context:
        """``compare``：兩塊區域比一次（原 `roi_compare` 的 run，逐行搬過來）。"""
        p = self.validate_params(params)
        target, reference = (str(p["target_region"]).strip(),
                             str(p["reference_region"]).strip())
        if not target or not reference:
            raise StepError(
                self.key,
                "pick a target region and a reference region - this card "
                "compares two, and which is which is the whole point of it.")
        metrics = _compare_metrics_of(p)
        if not metrics:
            raise StepError(self.key, "tick at least one thing to report "
                                      "(delta, snr, …).")
        bad = [m for m in metrics if m not in algo_glv.COMPARE_METRICS]
        if bad:
            raise StepError(self.key, "unknown comparison %r; available: %s"
                            % (bad[0], ", ".join(algo_glv.COMPARE_METRICS)))

        px = {}
        for role, region, source in (("target", target, p["target_source"]),
                                     ("reference", reference,
                                      p["reference_source"])):
            img = ctx.images.get(str(source))
            if img is None:
                raise StepError(
                    self.key,
                    "the %s image stream '%s' does not exist here; available: "
                    "%s." % (role, source, ", ".join(sorted(ctx.images))
                             or "none"))
            # **區域不在的時候要講出真正的原因。** `<name>_others` 在只有一份的
            # patch 上是**不存在**的（不是空的）—— 那不是設定錯，是這一顆沒有
            # 基準，而使用者要分得出那兩件事（見 `_util.set_region_family`）。
            if region not in ctx.roi_names():
                why = dict(ctx.meta.get("regions_absent") or {}).get(region, "")
                raise StepError(
                    self.key,
                    "the %s region '%s' is not on this defect%s. The rest of "
                    "the batch is unaffected."
                    % (role, region, (" — %s" % why) if why else
                       " (no card upstream produced it)"))
            px[role] = roi_pixels(ctx, self.key, img, region)

        got = algo_glv.compare_pixels(px["target"], px["reference"],
                                      str(p["stat"]))
        ctx.add_features(prefix_features(
            p["output_prefix"], {m: got[m] for m in metrics}))

        # 儀表用（同其他卡的慣例）：**畫面上的數字就是引擎算的這一份**。
        ctx.meta.setdefault("compares", {})["%s_vs_%s" % (target, reference)] = {
            "target": target, "reference": reference,
            "target_source": str(p["target_source"]),
            "reference_source": str(p["reference_source"]),
            "stat": str(p["stat"]),
            "target_px": int(px["target"].size),
            "reference_px": int(px["reference"].size),
            "values": {m: float(got[m]) for m in metrics},
        }
        return ctx

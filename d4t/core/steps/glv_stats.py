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

metrics（``stats``）的規則沒變
------------------------------
逗號清單，每個 id 產生一個同名 feature：
- 固定集：glv_mean / glv_median / glv_std / glv_min / glv_max / glv_q25 / glv_q75
- 動態分位數：glv_q<NN>（例 glv_q90）
- 別名：glv_p50 = glv_median；glv_p<NN> = glv_q<NN>
feature 名稱「照使用者列的寫」（別名不改名），數值一致。

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
            "statistics (mean, standard deviation, percentiles…), or compare "
            "two regions and write out how far apart they are. Pick which "
            "with “What to do”.")
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
        ParamSpec(name="metrics", type="multi_choice",
                  default="glv_mean,glv_std,glv_p50",
                  label="Statistics", show_when=_WHEN_STATS,
                  choices=["glv_mean", "glv_std", "glv_p50", "glv_min",
                           "glv_max", "glv_q25", "glv_q75", "glv_q90",
                           "glv_q99"],
                  help=("Tick the statistics to output - each becomes a "
                        "feature with the same name. glv_p50 is the median; "
                        "hand-written recipes may also use any percentile "
                        "like glv_q37.")),
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
        output_prefix_spec("center"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = ["glv_mean", "glv_std", "glv_p50"]

    # ---- 宣告 ---------------------------------------------------------------
    # `compare` 那一半不走 MultiSourceStep 的迴圈（它的兩條流有角色，排不成
    # 一串），所以四個 resolve_* 都要分岔。分岔點只有 `_method_of` 一個。

    @classmethod
    def feature_names(cls, params: Dict[str, Any]) -> List[str]:
        mids = parse_key_list(params.get("metrics", "glv_mean,glv_std,glv_p50"))
        return mids or list(cls.features_out)

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
        patch = roi_pixels(ctx, self.key, img, p["roi"])

        feats: Dict[str, float] = {}
        for mid in mids:
            canon = _canonical(mid)
            if not canon:
                raise StepError(
                    self.key,
                    f"unknown statistic '{mid}'; available: "
                    f"{sorted(algo_glv.GLV_STATS)} or glv_q<0-100> / glv_p<0-100>.")
            feats[mid] = algo_glv.glv_value(patch, canon)   # feature 名照使用者列的寫
        return feats

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

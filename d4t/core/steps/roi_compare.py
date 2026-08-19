# d4t step-card library — authored 2026-08-18 (F11 Measure：比較兩個區域).
"""roi_compare —— **拿哪兩塊比**，變成一張看得見的卡。

Region 段出名詞，這裡出動詞
---------------------------
使用者定調（2026-08-18）：「以這張 card 的功能（ROI）來說我不太想要去區分
target 跟 reference，原因是會有很多種組合⋯⋯我傾向這邊 ROI 只 labeled 出區域，
之後再給 card 標註 T 跟 R。」

理由比「情況太多」更硬：**角色是「這一次比較」的屬性，不是區域的屬性**。同一塊
EPI 在一個比較裡是 target、在另一個裡是 reference —— 角色寫進區域的話，每一種
比較都要複製一份區域，而區域是**畫**出來的。所以 T/R 住在**這張卡的參數上**：
recipe 的 diff 看得懂「這一次比的是哪兩塊」，而同一組區域可以被三張這種卡用三種
方式比（那正是使用者說的「很多種組合」，而組合屬於消費端）。

為什麼是**兩對**（流 + 區域），不是一條流兩個區域
--------------------------------------------------
使用者列的三種情況（計畫書 §3.3.6）裡，中間那一種**兩邊的流不一樣**：

| 情況 | target | reference |
|---|---|---|
| patch，跟自己兩側的 EPI 比 | `epi_center` @ test | `epi_others` @ test |
| patch，跟 ref 那張的同一塊比 | `epi` @ **test** | `epi` @ **ref** |
| 單張 source（沒有 ref）| `epi_center` @ single | `epi_others` @ single |

一條流配兩個區域表達不出第二種。所以是**兩個輸入埠**（`target_source` /
`reference_source`），而畫布上那就是兩條線 —— 正好是 F9 的規矩：資料從哪來由
線決定，一個輸入埠一條線。三種情況用同一張卡、同一組參數說得完。

**這張卡不是解鎖功能，是把一件現在藏起來的事變成看得見的。** 今天沒有它也比得
出來，只是比較發生在**分數表達式**裡（`test_epi_glv_mean - ref_epi_glv_mean`）
—— 而表達式裡的減法，畫布上看不到、diff 讀不懂、也沒有人擋得住兩邊挑錯區域。

GDS 那條路特別需要它
--------------------
`roi_from_mask` **只吐 `<name>`**（非週期的 layout 上沒有 `_others` —— 形狀不是
複本）。所以那條路真正該比的是**層 vs 層**（EPI 對 MG），而那件事只有這張卡
做得到。

算什麼（`algo/glv.compare_pixels`）
-----------------------------------
`delta` / `ratio` / `percent` / `snr` / `tstat`。``snr`` 的公式是
``(μ_T − μ_R) / σ_R`` —— 那是 e-beam 帶正負號的 SNR 慣例，而這個 repo 已經有
兩個地方在用它（`algo.glv.group_snr`、`algo/snr`）。**不發明第三種寫法**：
同一個名字在不同卡片上算出不同的東西，是最難發現的那種錯。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..algo import glv as algo_glv
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, GROUP_MEASURE, ParamSpec, Step, StepError, register_step,
)
from ._util import output_prefix_spec, prefix_features, prefix_names, roi_pixels

#: 預設勾哪幾個。`delta` 與 `snr` 是兩個不同的問題（差多少 / 差幾個 σ），
#: 兩個都預設勾著 —— 只給前者的話，使用者要自己想起來後者存在。
DEFAULT_METRICS = "delta,snr"


def _metrics_of(params: Dict[str, Any]) -> List[str]:
    from ._util import parse_key_list

    return parse_key_list(params.get("metrics", DEFAULT_METRICS))


@register_step
class RoiCompareStep(Step):
    """比較兩塊區域：一塊當 target、一塊當 reference。"""

    key = "roi_compare"
    label = "Compare regions"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Compare one region against another and write out how far apart "
            "they are. Which region is the target and which is the reference "
            "is decided here, on this card - not upstream where the regions "
            "are drawn, because the same region is the target in one "
            "comparison and the reference in another. The two can be on "
            "different image streams, so “this block on test versus the same "
            "block on ref” is the same card as “this block versus its "
            "neighbours”.")
    params = [
        ParamSpec(
            name="target_source", type="image_key", direction="in",
            default="test", section="1 · Target (the thing being judged)",
            label="Measure it on",
            help="Which image stream the target region is measured on.",
        ),
        ParamSpec(
            name="target_region", type="region_key", default="",
            section="1 · Target (the thing being judged)",
            label="Target region",
            help=("The region being judged - normally the one the defect is "
                  "in. Leave a Region card upstream and its names appear "
                  "here."),
        ),
        ParamSpec(
            name="reference_source", type="image_key", direction="in",
            default="test", section="2 · Reference (what it is judged against)",
            label="Measure it on",
            help=("Which image stream the reference region is measured on. "
                  "Point it at ref to compare the same block across the pair; "
                  "leave it on the same stream as the target to compare "
                  "against another region of the same image."),
        ),
        ParamSpec(
            name="reference_region", type="region_key", default="",
            section="2 · Reference (what it is judged against)",
            label="Reference region",
            help=("What the target is judged against - the same material "
                  "elsewhere on this image (<name>_others), the same block on "
                  "the other image, or a different layer entirely."),
        ),
        ParamSpec(
            name="stat", type="choice", default="glv_mean",
            section="3 · What to compare",
            choices=["glv_mean", "glv_median", "glv_q25", "glv_q75",
                     "glv_q90", "glv_min", "glv_max"],
            label="Compare their",
            help=("Which single number stands for each region. The mean is "
                  "the usual choice; the median ignores a few very bright or "
                  "dark pixels, which matters when a region has a speck in it "
                  "that is not what you are measuring."),
        ),
        ParamSpec(
            name="metrics", type="multi_choice", default=DEFAULT_METRICS,
            section="3 · What to compare",
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
        output_prefix_spec("epi_vs_mg"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = ["delta", "snr"]

    # ---- 宣告 ---------------------------------------------------------------
    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        out = []
        for key in ("target_source", "reference_source"):
            name = str(params.get(key, "") or "").strip()
            if name and name not in out:
                out.append(name)
        return out

    @classmethod
    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
        out = []
        for key in ("target_region", "reference_region"):
            name = str(params.get(key, "") or "").strip()
            if name and name not in out:
                out.append(name)
        return out

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        return prefix_names(params.get("output_prefix", ""),
                            _metrics_of(params) or list(cls.features_out))

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """兩塊都要挑，而且不能挑到同一塊。"""
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

    # ---- 執行 ---------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        target, reference = (str(p["target_region"]).strip(),
                             str(p["reference_region"]).strip())
        if not target or not reference:
            raise StepError(
                self.key,
                "pick a target region and a reference region - this card "
                "compares two, and which is which is the whole point of it.")
        metrics = _metrics_of(p)
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

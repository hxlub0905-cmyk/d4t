# d4t step-card library — authored 2026-07-28 (M1).
"""subtract —— 比較卡：兩條流 → 一條「它們差在哪裡」。

``invert`` 已於 F7-20 併進 ``tone`` 卡（它跟亮度/gamma 一樣是逐像素的
色調映射，使用者的問題只有一個「把這張圖調得看得清楚」）。

⚠ **2026-09-18（F110）拆成兩張卡。** 這張卡以前有五個 ``op``，而那是兩件事：
``subtract`` / ``ratio`` 在問「這兩張哪裡不一樣」（比較，天生 a 對 b），
``max`` / ``min`` / ``mean`` 在問「把這幾張併成一張」（融合，天生 N 條流）。
後三個搬去 :mod:`d4t.core.steps.combine`，連同 ``Image Combination`` 這個名字
—— 那才真的是「把影像組合起來」。這張卡回到它的意思：``Compare``（跟 ``roi_reference``／``ROI`` 同一個先例 ——一段裡最正統的那一張卡就叫那一段的名字）。

``key`` 仍然是 ``subtract``：那是 recipe 的鍵，改了舊檔就開不起來。舊檔案裡
``op`` 是 max/min/mean 的那幾個節點由 `recipe._migrate_split_out_combine`
換成 ``combine``。

注意：產出的 diff 流是 **float32**（可能含負值，取決於 ``sign``），
下游卡（glv_stats…）都吃得下 float32。
"""
from __future__ import annotations
from d4t.core.log import swallowed

from typing import Any, Dict, List

import numpy as np

from ..algo import glv as algo_glv
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_COMPARE,
)
from ._util import require_image

#: 行/列平均曲線最多留幾個點。條紋殘留（半像素對位）在預覽上肉眼看不出、
#: 在行列平均上一眼看得出方向與強度 —— 但整張 RSEM 大圖一列一個 float 會把
#: meta 撐肥（同 `cd.MAX_CONTOUR_POINTS` 只存摘要的理由）。128 點對「有沒有
#: 條紋、往哪個方向」綽綽有餘。
MAX_CURVE_POINTS = 128


def _thin_curve(vals: "np.ndarray", limit: int = MAX_CURVE_POINTS) -> List[float]:
    """等距抽稀到 ≤ ``limit`` 點（同 `cd._thin_out` 的 stride 做法）。"""
    n = int(vals.size)
    if n <= limit:
        return [float(v) for v in vals]
    step = int(np.ceil(n / float(limit)))
    return [float(v) for v in vals[::step]]


@register_step
class SubtractStep(Step):
    """影像相減：out = a - b（float32；absolute=True 時取絕對值）。"""

    key = "subtract"
    #: ``key`` 仍然是 ``subtract`` —— 那是 recipe 的鍵，改了舊檔就開不起來。
    #:
    #: 名字換過兩次，而**兩次的理由是同一個，只是方向相反**：F16 從
    #: ``Compare two streams`` 改叫 ``Image Combination``（使用者定調：「五個
    #: op 只有一個是相減」），F110 又改回比較那一族 —— 因為那四個「不是相減」
    #: 的 op 裡，有三個已經搬去 `combine` 了。名字跟著卡片真的在做的事走。
    label = "Compare"
    category = CATEGORY_IMAGE
    group = GROUP_COMPARE
    help = ("Combine two image streams into one - normally test minus ref, "
            "which is what makes defects stand out. The result stream is "
            "float32.")
    requires_ref = True
    params = [
        ParamSpec(name="a", type="image_key", direction="in", default="test",
                  label="First stream",
                  help="The image being judged (usually test)."),
        # 預設 ``ref`` 而不是 ``ref_aligned``（2026-08-14 使用者指正）：
        # patch 是機台以 defect 為中心裁切的，**本來就對齊**，「一定要先
        # Align」是這個預設造出來的假前置。Align 留給之後非 patch 的輸入、
        # 或站點真的量到殘餘位移時用 —— 那時候把這一格改指 ref_aligned。
        ParamSpec(name="b", type="image_key", direction="in", default="ref",
                  label="Second stream",
                  help=("What to compare it against (usually ref - patches "
                        "already arrive centred on the defect, so no "
                        "alignment step is needed). If your images do need "
                        "registration first, add an Align card and point "
                        "this at ref_aligned.")),
        # op 是 F7-10 加的：差分之外的做法跟相減是**同一個問題的不同答案**
        # （「這兩張哪裡不一樣」），所以是同一張卡的一排膠囊，不是好幾張新卡。
        # ⚠ F110 把 max/min/mean 搬去 `combine`：那三個回答的不是這個問題
        # （它們在問「把這幾張併成一張」），而判準是**訊號形狀** ——
        # 比較是 2 條進 1 條出，融合是 N 條進 1 條出。
        ParamSpec(
            name="op", type="chip_choice", default="subtract",
            choices=["subtract", "ratio", "normalized", "over_sigma"],
            icons=["op_subtract", "op_ratio", "op_normalized", "op_over_sigma"],
            choice_labels={"over_sigma": "Over sigma"},
            label="How to combine",
            help=("subtract = a minus b, the normal die-to-die difference; "
                  "ratio = a divided by b, which stays meaningful when the "
                  "two images have different overall brightness; normalized = "
                  "the difference over the sum, which does not blow up where "
                  "the reference is nearly black; over sigma = the difference "
                  "in units of how noisy b is, so the number means the same "
                  "thing on a quiet image and a grainy one."),
        ),
        # F110：`absolute`（bool）→ `sign`（三選一）。兩個值的那一格答不出
        # 第三種答案，而第三種是使用者真的要的：**亮的缺陷與暗的缺陷分兩條流
        # 出去**。用 `absolute=True` 的話兩者被壓成同一個訊號（分不出來），
        # 用 `False` 的話下游每一個統計量都得自己處理正負號。
        ParamSpec(
            name="sign", type="chip_choice", default="abs",
            choices=["abs", "signed", "split"],
            icons=["sign_abs", "sign_signed", "sign_split"],
            choice_labels={"abs": "Ignore it"},
            label="Bright and dark",
            choice_help={
                "abs": "Both become positive signal. One stream out, and a "
                       "big number means “very different” either way.",
                "signed": "Keep the sign: bright defects come out positive, "
                          "dark ones negative. One stream out.",
                "split": "Two streams out - one holding only what is brighter "
                         "than the reference, one only what is darker. Use it "
                         "when the two kinds need different thresholds.",
            },
            help=("What to do about defects that are darker than the "
                  "reference. Not used by ratio.")),
        ParamSpec(name="out", type="image_key", direction="out", default="diff",
                  label="Write result to",
                  help="Name of the image stream the result is written to (float32)."),
    ]
    reads = ["test", "ref"]
    writes = ["diff"]
    features_out: List[str] = []

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("a", "test"), params.get("b", "ref")]

    #: ``sign="split"`` 時輸出流名的兩個後綴。
    SPLIT_SUFFIX = ("_bright", "_dark")

    @classmethod
    def _out_names(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("out", "diff") or "").strip()
        if not name:
            return []
        if str(params.get("sign", "abs") or "abs") == "split":
            return [name + s for s in cls.SPLIT_SUFFIX]
        return [name]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return cls._out_names(params)

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        a = require_image(ctx, self.key, p["a"])
        b = require_image(ctx, self.key, p["b"])
        if a.shape != b.shape:
            raise StepError(self.key, f"'{p['a']}' and '{p['b']}' differ in size "
                            f"({a.shape} vs {b.shape}); cannot subtract.")
        fa, fb = a.astype(np.float32), b.astype(np.float32)
        op, sign = str(p["op"]), str(p.get("sign", "abs") or "abs")
        if op == "ratio":
            # 0 除法：分母補一個極小值而不是讓它變 inf —— inf 會一路帶到
            # 特徵與分數，最後變成一顆「分數是 nan」的 defect，而使用者
            # 完全看不出是哪一步造成的。
            out = fa / np.maximum(np.abs(fb), 1e-6) * np.sign(np.where(fb == 0, 1.0, fb))
            sign = "signed"          # 比值沒有「取絕對值」的意思
        elif op == "normalized":
            # Michelson：分母是**和**不是參照，所以參照接近黑的時候不會爆掉
            # （`ratio` 在那裡會噴出幾千）。跟 `algo/glv.compare_pixels` 的
            # `contrast` 是同一個式子，只是那邊在統計量上做、這邊逐像素做。
            total = fa + fb
            out = np.where(np.abs(total) > 1e-6, (fa - fb) / np.maximum(
                np.abs(total), 1e-6) * np.sign(np.where(total == 0, 1.0, total)),
                0.0)
        elif op == "over_sigma":
            # 「差了幾個 b 自己的 σ」—— 讓門檻在安靜的圖與有顆粒的圖上意思一樣。
            # σ 是**整張 b 的**（不是逐像素的鄰域）：逐像素的那一種叫 SNR map，
            # 而那是量測段的事，不是這裡。
            sd = float(np.std(fb))
            out = (fa - fb) / sd if sd > 1e-6 else np.zeros_like(fa)
        else:
            out = fa - fb
        if sign == "abs":
            out = np.abs(out)
        out = out.astype(np.float32)
        if ctx.track_changes:
            # 儀表用（PR-2）。`diff` 是**新**流，`set_image` 的 stream_change
            # 只在覆寫時記（context.py），所以這張卡自己 note —— 跟 Enhance
            # 面板同一個生命週期：預覽（track_changes）才記，批次零成本。
            # 記錄永遠不准弄壞跑（同 `Context._record_change` 的形狀）。
            try:
                self._note_diagnostics(ctx, out, p)
            except Exception:
                swallowed("arith.run")
        names = self._out_names(p)
        if sign == "split":
            # **兩條流，而且各自只留自己那一半**（不是把負的變 0 再丟同一條）：
            # 分開的整個意思就是讓下游各給一個門檻。
            ctx.set_image(names[0], np.maximum(out, 0.0).astype(np.float32))
            ctx.set_image(names[1],
                          np.maximum(-out, 0.0).astype(np.float32))
        else:
            ctx.set_image(names[0], out)
        return ctx

    def _note_diagnostics(self, ctx: Context, out: "np.ndarray",
                          p: Dict[str, Any]) -> None:
        """差影像是 D2D 的心臟，而它以前一格儀表都沒有。留三樣東西：

        * **有號直方圖**（`algo_glv.signed_hist`，0 置中）—— 差影像的中心是
          0 不是 128，0/255 的 `sat` 診斷對它不適用；
        * **殘留數字**：median、MAD、超出 ±3×MAD 的像素比例；
        * **行/列平均曲線**（各 ≤ 128 點）—— 抓半像素對位殘留的主角：條紋
          在預覽上肉眼看不出，行列平均一眼看出方向與強度。

        面板畫的就是這一份（`ui/inspectors.py` 檔頭第 2 條），全部 cast 成
        int/float/list —— 快取 payload 的 `_meta_snapshot` 只留 JSON-safe。
        """
        v = out.astype(np.float64).ravel()
        counts, edges, clipped = algo_glv.signed_hist(out)
        med = float(np.median(v)) if v.size else 0.0
        mad = float(np.median(np.abs(v - med))) if v.size else 0.0
        beyond3 = (float((np.abs(v - med) > 3.0 * mad).mean())
                   if v.size and mad > 0.0 else 0.0)
        ctx.meta.setdefault("subtract", {})[str(p["out"])] = {
            "a": str(p["a"]), "b": str(p["b"]),
            "op": str(p["op"]), "sign": str(p.get("sign", "abs") or "abs"),
            "bins": [int(c) for c in counts],
            "hi": float(edges[-1]),
            "clipped": float(clipped),
            "n": int(out.size),
            "median": med, "mad": mad, "beyond3": beyond3,
            "rows": _thin_curve(out.mean(axis=1)),
            "cols": _thin_curve(out.mean(axis=0)),
            "rows_n": int(out.shape[0]), "cols_n": int(out.shape[1]),
        }

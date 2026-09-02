# d4t step-card library — authored 2026-07-28 (M1).
"""影像算術卡：subtract。

``invert`` 已於 F7-20 併進 ``tone`` 卡（它跟亮度/gamma 一樣是逐像素的
色調映射，使用者的問題只有一個「把這張圖調得看得清楚」）。

注意：subtract 產出的 diff 流是 **float32**（可能含負值，取決於 absolute），
下游卡（snr_map / glv_stats…）都吃得下 float32。
"""
from __future__ import annotations

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
    #: 給人看的名字改了（F16，使用者定調）：這張卡的五個 ``op`` 只有一個是
    #: 相減，叫它「Compare two streams」會讓另外四個看起來不屬於這裡。
    label = "Image Combination"
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
        # op 是 F7-10 加的。差分之外的四種組合以前得靠外部工具做，但它們跟
        # 相減是同一個問題的不同答案（「這兩張哪裡不一樣」），所以是同一張卡的
        # 一個下拉 —— 不是四張新卡片。
        ParamSpec(
            name="op", type="chip_choice", default="subtract",
            choices=["subtract", "ratio", "max", "min", "mean"],
            icons=["op_subtract", "op_ratio", "op_max", "op_min", "op_mean"],
            label="How to combine",
            help=("subtract = a minus b, the normal die-to-die difference; "
                  "ratio = a divided by b, which stays meaningful when the "
                  "two images have different overall brightness; max / min = "
                  "take the brighter or darker pixel of the two; mean = "
                  "average them (useful for building a cleaner reference)."),
        ),
        ParamSpec(name="absolute", type="bool", default=True,
                  label="Ignore the sign",
                  help=("True = absolute value (bright and dark defects both become "
                        "positive signal); False = keep the sign so bright and dark "
                        "defects stay distinguishable. Only used by subtract.")),
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

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [params.get("out", "diff")]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        a = require_image(ctx, self.key, p["a"])
        b = require_image(ctx, self.key, p["b"])
        if a.shape != b.shape:
            raise StepError(self.key, f"'{p['a']}' and '{p['b']}' differ in size "
                            f"({a.shape} vs {b.shape}); cannot subtract.")
        fa, fb = a.astype(np.float32), b.astype(np.float32)
        op = str(p["op"])
        if op == "ratio":
            # 0 除法：分母補一個極小值而不是讓它變 inf —— inf 會一路帶到
            # 特徵與分數，最後變成一顆「分數是 nan」的 defect，而使用者
            # 完全看不出是哪一步造成的。
            out = fa / np.maximum(np.abs(fb), 1e-6) * np.sign(np.where(fb == 0, 1.0, fb))
        elif op == "max":
            out = np.maximum(fa, fb)
        elif op == "min":
            out = np.minimum(fa, fb)
        elif op == "mean":
            out = (fa + fb) * 0.5
        else:
            out = fa - fb
            if p["absolute"]:
                out = np.abs(out)
        out = out.astype(np.float32)
        if ctx.track_changes:
            # 儀表用（PR-2）。`diff` 是**新**流，`set_image` 的 stream_change
            # 只在覆寫時記（context.py），所以這張卡自己 note —— 跟 Enhance
            # 面板同一個生命週期：預覽（track_changes）才記，批次零成本。
            # 記錄永遠不准弄壞跑（同 `Context._record_change` 的形狀）。
            try:
                self._note_diagnostics(ctx, out, p)
            except Exception:  # noqa: BLE001
                pass
        ctx.set_image(p["out"], out)
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
            "op": str(p["op"]), "absolute": bool(p["absolute"]),
            "bins": [int(c) for c in counts],
            "hi": float(edges[-1]),
            "clipped": float(clipped),
            "n": int(out.size),
            "median": med, "mad": mad, "beyond3": beyond3,
            "rows": _thin_curve(out.mean(axis=1)),
            "cols": _thin_curve(out.mean(axis=0)),
            "rows_n": int(out.shape[0]), "cols_n": int(out.shape[1]),
        }

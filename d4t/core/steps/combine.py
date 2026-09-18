# d4t step-card library — authored 2026-09-18 (F110).
"""combine —— 融合卡：把好幾條流併成一條。

**這張卡從 `subtract` 拆出來**（F110）。`subtract` 的五個 ``op`` 是**兩件事**
擠在一張卡上：

* ``subtract`` / ``ratio`` 在問「**這兩張哪裡不一樣**」——
  那是比較，天生是 a 對 b；
* ``max`` / ``min`` / ``mean`` 在問「**把這幾張併成一張**」——
  那跟「兩張」沒有關係，它天生是 N 條流。

擠在一起的代價實際看得見：那張卡有 ``a`` 與 ``b`` **兩顆埠**，所以想把三張
condition 併成一張 reference 的人得放兩張卡串起來，而畫布上那兩張卡看起來
是在比較兩次。名字也跟著說謊 —— F16 把它從 ``Compare two streams`` 改叫
``Image Combination``（使用者定調：「五個 op 只有一個是相減」），而改完之後
變成**比較那兩個 op** 的名字不對了。拆開之後兩邊的名字都回到自己的意思。

⚠ **`Image Combination` 這個名字歸這裡**：它才真的是「把影像組合起來」。
比較那一張現在叫 ``Compare two images``，key 仍然是 ``subtract``
（那是 recipe 的鍵，改了舊檔就開不起來）。

為什麼 median 是預設
--------------------
它是**唯一一個拿得掉離群值的**：N 張裡有一張帶著缺陷、或有一張被 charging
掃壞了，``mean`` 會把它抹進結果裡（每一張都貢獻 1/N），而 ``median`` 直接
不看它。「用好幾張造一張乾淨的 reference」正是這張卡最常見的用途，
而那個用途要的就是「**不要**被其中一張帶歪」。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_COMPARE, ParamSpec, Step, StepError, register_step,
)
from ._util import parse_key_list, require_image

#: 修剪平均要各砍掉幾成（每一端）。0.25 = 兩端各砍 25%，剩中間一半。
TRIM_FRACTION = 0.25

METHODS = ("median", "mean", "trimmed", "max", "min")

#: 剛拉出來的那張卡預設讀哪幾條 —— 見 `streams` 那一格的說明。
DEFAULT_STREAMS = "test,ref"


@register_step
class CombineStep(Step):
    """N 條流 → 一條（median / mean / trimmed / max / min）。"""

    key = "combine"
    label = "Image Combination"
    category = CATEGORY_IMAGE
    group = GROUP_COMPARE
    help = ("Merge several image streams into one. The usual reason is to "
            "build a cleaner reference out of several images of the same "
            "place: the median throws away whatever only one of them has, "
            "which is exactly what a defect is. Every stream has to be the "
            "same size. The result is float32.")
    params = [
        # ⚠ **預設不能是空字串**（同 `align` 的 `DEFAULT_STREAMS`，F109 那一輪
        # 付過的錢）：`resolve_*` 會拿到「還沒填過任何東西」的 params ——
        # 畫布上剛拉出來的節點就是那樣，而預設值是 `validate_params` 當下才套的。
        # 空字串會讓一張剛加上去的 `combine` 宣告自己**不讀任何流**，而畫布是
        # 照宣告畫的（那顆埠根本不會出現，於是線也拉不上去）。
        ParamSpec(name="streams", type="image_keys", direction="in",
                  default=DEFAULT_STREAMS, label="Merge these",
                  help=("Which image streams to merge - drag a line from each "
                        "one. Two is the minimum; there is no maximum.")),
        ParamSpec(
            name="method", type="chip_choice", default="median",
            choices=list(METHODS),
            icons=["op_median", "op_mean", "op_trimmed", "op_max", "op_min"],
            label="How to merge",
            choice_help={
                "median": "The middle value at every pixel. Whatever only one "
                          "image has - a defect, a scan artefact - is dropped "
                          "rather than averaged in.",
                "mean": "The plain average. Quietest result when every image "
                        "is clean, but one bad image contaminates all of it.",
                "trimmed": "Throw away the brightest and darkest quarter at "
                           "every pixel, then average the rest. Between the "
                           "other two.",
                "max": "The brightest of the images at every pixel.",
                "min": "The darkest of the images at every pixel.",
            },
            help=("How to merge them at each pixel. Median is the one that "
                  "does not let a single bad image through.")),
        ParamSpec(name="out", type="image_key", direction="out",
                  default="merged", label="Write result to",
                  help="Name of the image stream the result is written to "
                       "(float32)."),
    ]
    reads: List[str] = []
    writes = ["merged"]
    features_out: List[str] = []

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return parse_key_list(params.get("streams", ""))

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("out", "merged") or "").strip()
        return [name] if name else []

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        """一條流併不出東西來 —— 而那在設定期就看得出來。"""
        got = parse_key_list(params.get("streams", ""))
        if len(got) == 1:
            return ["only one stream is connected, so there is nothing to "
                    "merge it with. Drag a line from a second one."]
        return []

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        names = parse_key_list(p.get("streams", ""))
        if len(names) < 2:
            raise StepError(self.key,
                            "connect at least two image streams to merge.")
        imgs = [require_image(ctx, self.key, n) for n in names]
        shape = imgs[0].shape[:2]
        for name, img in zip(names, imgs):
            if img.shape[:2] != shape:
                raise StepError(
                    self.key,
                    "'%s' is %s but '%s' is %s - merging works pixel by pixel, "
                    "so they all have to be the same size. Line them up with "
                    "an Align card first." % (names[0], shape, name,
                                              img.shape[:2]))
        stack = np.stack([i.astype(np.float32) for i in imgs], axis=0)
        method = str(p["method"])
        if method == "mean":
            out = stack.mean(axis=0)
        elif method == "max":
            out = stack.max(axis=0)
        elif method == "min":
            out = stack.min(axis=0)
        elif method == "trimmed":
            out = self._trimmed(stack)
        else:
            out = np.median(stack, axis=0)
        ctx.set_image(p["out"], np.ascontiguousarray(out.astype(np.float32)))
        return ctx

    @staticmethod
    def _trimmed(stack: "np.ndarray") -> "np.ndarray":
        """兩端各砍 :data:`TRIM_FRACTION`，剩下的平均。

        ⚠ **砍到一張都不剩的時候退回 median**，不是回 NaN：三張流兩端各砍
        25% 就是各砍 0.75 張 —— 取整之後有可能把三張全砍光。那時候「算不出來」
        的答案是錯的（中位數明明算得出來），而 NaN 會一路流進分數表達式。
        """
        n = int(stack.shape[0])
        cut = int(n * TRIM_FRACTION)
        if n - 2 * cut < 1:
            return np.median(stack, axis=0)
        ordered = np.sort(stack, axis=0)
        return ordered[cut:n - cut].mean(axis=0)

# ADEPT step-card library — authored 2026-07-29 (F7-10).
"""flatten / local_contrast —— 處理**空間性**假訊號的兩張 Enhance 卡。

為什麼是兩張卡而不是六張
------------------------
「背景平坦化」「去掃描線條紋」「top-hat」「black-hat」看起來是四種不同的東西，
但它們的結構完全一樣：**估一個大尺度的成分，然後把它減掉**。差別只在怎麼估
（高斯模糊／逐列中位數／形態學開閉運算）。所以它們是同一張卡的 ``method``，
不是四張卡 —— 卡片庫多四列，使用者要多讀四段說明才能知道該用哪一個；
一張卡的一個下拉，他只要讀一次。

CLAHE 分開放，是因為它不是「減掉什麼」而是「局部重新拉伸」，
而且它跟既有的三張 Normalize 卡是同一個家族（都是把灰階重新映射），
所以命名跟著那個家族走（``Normalize · Local contrast``）。

輸出 dtype
----------
兩張卡都輸出 float32。既有的 Enhance 卡多半維持 uint8，但這幾種運算會產生
負值（背景移除）或需要小數精度（CLAHE 後再做別的），硬轉回 uint8 會在
量測之前就先截掉資訊。下游的量測卡與 ``subtract`` 都吃得下 float32
（``diff`` 流本來就是 float32）。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..algo import enhance as algo_enhance
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_ENHANCE, ParamSpec, Step, register_step,
)
from ._util import parse_key_list, require_image

#: ``Apply to`` / ``Also apply to`` 兩個參數的共同說明（見 CLAUDE.md §5）。
_APPLY_HELP = ("Which image stream this card works on; the result is written "
               "back to that same stream. Streams are the named lines on the "
               "canvas - test is the defect image, ref is the reference image.")
_ALSO_HELP = ("Other streams that get exactly the same treatment. Keep ref "
              "ticked so test and ref stay comparable; untick it to treat the "
              "two images differently.")


class _StreamsStep(Step):
    """共用：主影像流 + ``also_apply``（同 tone / normalize 卡的慣例）。"""

    category = CATEGORY_IMAGE
    group = GROUP_ENHANCE
    reads = ["test"]
    writes = ["test"]
    features_out: List[str] = []

    @classmethod
    def _targets(cls, params: Dict[str, Any]) -> List[str]:
        keys = [str(params.get("target", "test"))]
        keys += parse_key_list(params.get("also_apply", ""))
        seen, out = set(), []
        for k in keys:
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        return cls._targets(params)

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return cls._targets(params)

    def _apply_each(self, ctx: Context, params: Dict[str, Any], fn) -> Context:
        primary = str(params.get("target", "test"))
        require_image(ctx, self.key, primary)      # 主流不存在才算錯
        for key in self._targets(params):
            img = ctx.images.get(key)
            if img is None:
                ctx.warn(f"[{self.key}] also_apply stream '{key}' does not "
                         f"exist; skipped.")
                continue
            ctx.set_image(key, np.asarray(fn(img), dtype=np.float32))
        return ctx


@register_step
class FlattenStep(_StreamsStep):
    """移除大尺度的假訊號：亮度梯度、掃描線條紋、不平的背景。"""

    key = "flatten"
    label = "Remove background / stripes"
    help = ("Remove large-scale artifacts that are not defects - charging "
            "brightness gradients, scan-line stripes, or an uneven background "
            "- so they stop showing up in the difference image.")
    params = [
        ParamSpec(name="target", type="image_key", default="test",
                  label="Apply to", help=_APPLY_HELP),
        ParamSpec(name="also_apply", type="image_keys", default="ref",
                  label="Also apply to", help=_ALSO_HELP),
        ParamSpec(
            name="method", type="choice", default="background",
            choices=["background", "stripes_h", "stripes_v",
                     "bright_spots", "dark_spots"],
            label="Remove",
            help=("background = a smooth brightness gradient (charging); "
                  "stripes_h / stripes_v = scan-line stripes running across "
                  "or down the image; bright_spots / dark_spots = keep only "
                  "features smaller than the size below and drop everything "
                  "larger, whatever shape the background is."),
        ),
        ParamSpec(
            name="size", type="int", default=31, min=3, max=999, unit="px",
            label="Scale to remove",
            help=("How large the artifact is, in pixels. It must be clearly "
                  "BIGGER than your defects - anything smaller than this "
                  "survives, anything larger is removed. A quarter to a half "
                  "of the patch width is a good starting point. "
                  "(Not used for the stripe methods.)"),
        ),
        ParamSpec(
            name="strength", type="float", default=1.0, min=0.0, max=1.0,
            label="Strength",
            help=("How much of the estimated artifact to take out; 1 = all of "
                  "it. Only used by the stripe methods - real stripes are not "
                  "always purely additive, so full correction can overshoot."),
        ),
        ParamSpec(
            name="keep_level", type="bool", default=True,
            label="Keep original brightness",
            help=("Add the original average brightness back, so the image "
                  "stays in the gray range it started in and the thresholds "
                  "downstream still mean the same thing."),
        ),
    ]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        method = str(p["method"])
        size = int(p["size"])
        strength = float(p["strength"])
        keep = bool(p["keep_level"])

        def fn(img: Any) -> np.ndarray:
            if method == "background":
                return algo_enhance.remove_background(img, size, keep_level=keep)
            if method in ("stripes_h", "stripes_v"):
                return algo_enhance.remove_stripes(
                    img, axis=0 if method == "stripes_h" else 1,
                    strength=strength)
            out = algo_enhance.morph_residual(
                img, size, dark=(method == "dark_spots"))
            if keep:
                # top-hat / black-hat 的輸出以 0 為基準；把原本的亮度加回去，
                # 讓「輸出仍落在原本的灰階區間」這件事對五種方法都成立。
                out = out + float(np.nanmean(np.asarray(img, dtype=np.float32)))
            return out

        return self._apply_each(ctx, p, fn)


@register_step
class LocalContrastStep(_StreamsStep):
    """CLAHE：分格子做直方圖等化，暗區裡的小缺陷也拉得起來。"""

    key = "local_contrast"
    label = "Normalize · Local contrast"
    help = ("Stretch contrast tile by tile (CLAHE) instead of over the whole "
            "image, so a faint defect sitting in a dark area becomes visible "
            "- a global stretch can never do that.")
    params = [
        ParamSpec(name="target", type="image_key", default="test",
                  label="Apply to", help=_APPLY_HELP),
        ParamSpec(name="also_apply", type="image_keys", default="ref",
                  label="Also apply to", help=_ALSO_HELP),
        ParamSpec(
            name="clip_limit", type="float", default=2.0, min=0.1, max=40.0,
            label="Contrast limit",
            help=("Ceiling on how much contrast one tile may gain. Raise it "
                  "for more punch; too high and flat areas amplify their own "
                  "noise until it looks like signal."),
        ),
        ParamSpec(
            name="tiles", type="int", default=8, min=1, max=32,
            label="Tiles per side",
            help=("The image is divided into this many tiles across and down. "
                  "More tiles follow local brightness more closely, but a "
                  "defect larger than one tile starts being treated as "
                  "background and fades out - lower this if that happens."),
        ),
    ]

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        clip, tiles = float(p["clip_limit"]), int(p["tiles"])
        return self._apply_each(
            ctx, p, lambda img: algo_enhance.clahe(img, clip, tiles))

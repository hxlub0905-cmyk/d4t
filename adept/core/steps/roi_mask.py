# ADEPT step-card library — authored 2026-08-14 (F8c).
"""roi_mask —— 把具名區域畫成一條 0/255 的 mask 影像流。

為什麼要有這張卡（F8 計畫書 §7 的 (c)，2026-08-14 使用者核准）
--------------------------------------------------------------
跨 patch 比 EPI 的 GLV 時，**MG 佔多少面積是隨 crop 變的**：64px 的 patch，
一根 MG 進出畫面就是 12% 的面積差。任何吃「整張圖統計」的 Enhance 卡
（percentile normalize 首當其衝）都把這個變異灌進 EPI 的數字裡 ——
同一片 EPI，隔壁的 MG 多一根，正規化完就變了一個值。

解法是讓統計**只看該看的像素**：這張卡把 Region 卡定義的具名區域轉成一條
0/255 的影像流，Normalize 的 ``Use only`` 接上它之後，範圍只從 mask 內量、
**套用仍是整張圖**。

界線（跟 F7-17 的教訓同一條）
-----------------------------
mask 是給**影像段**用的（它是一條影像流，畫布上是一條看得見的線）。
量測段照樣引用 ROI 名字 —— 兩條平行的路會腐爛，所以量測卡**不**改吃 mask。

多個區域 = 聯集：像素落在任何一個名字裡就算在 mask 內。
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_REGION, ParamSpec, Step, register_step,
)
from ._util import parse_key_list, require_image

__all__ = ["RoiMaskStep"]


@register_step
class RoiMaskStep(Step):
    """具名區域 → 0/255 mask 影像流（多名字取聯集）。"""

    key = "roi_mask"                # recipe JSON 的鍵 —— **不改**（改了舊檔就開不起來）
    label = "Mask from regions"
    category = CATEGORY_IMAGE
    group = GROUP_REGION
    help = ("Turn named regions into a mask image stream (255 inside, 0 "
            "outside), so a Normalize card can measure its range from just "
            "that pattern instead of the whole patch.")
    params = [
        ParamSpec(
            name="regions", type="str", default="",
            label="Regions",
            help=("Comma-separated region names from the cards above. Several "
                  "names are combined: a pixel inside any of them is inside "
                  "the mask.")),
        ParamSpec(
            name="source", type="image_key", default="test",
            label="Same size as",
            help=("The mask is drawn at this stream's size. Pick the stream "
                  "the mask will be used on.")),
        ParamSpec(
            name="out", type="image_key", default="mask",
            label="Write mask to",
            help=("Name of the image stream the mask is written to. Point a "
                  "Normalize card's 'Use only' at this name.")),
    ]
    reads = ["test"]
    writes = ["mask"]
    features_out: List[str] = []

    # ---- 契約 -------------------------------------------------------------
    @classmethod
    def region_list(cls, params: Dict[str, Any]) -> List[str]:
        return parse_key_list(params.get("regions", ""))

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        # 與 run() 的正規化**同一套**（空／空白 → 預設值）。兩邊各自演化的
        # 下場：lint 與畫布講 test → mask，執行卻去找 '' —— 畫布在說謊。
        return [str(params.get("source", "test") or "").strip() or "test"]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        return [str(params.get("out", "mask") or "").strip() or "mask"]

    @classmethod
    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
        return cls.region_list(params)

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        # 空的 regions 是完全合法的 str —— 但這張卡跑起來每一顆都是全 0 的
        # mask，下游的 Normalize 又會退回整張圖：跑得完、有數字、而且什麼都
        # 沒做。參數合法 ≠ 設定完成（F7-13）。
        if not cls.region_list(params):
            return ["Name at least one region in the Regions box. No regions "
                    "yet? Add one of the ROI cards from the library first "
                    "(Library → ROI…) - its region names fill in here "
                    "automatically."]
        return []

    # ---- 運算 -------------------------------------------------------------
    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        # 空字串照 resolve_reads / resolve_writes 的同一套預設走。那兩個
        # 欄位是可編輯的下拉，清空是清得出來的 —— 清空之後 lint 與畫布講的
        # 是 test → mask，執行就**必須**也是 test → mask，否則就是「畫布在
        # 說謊」：下游 Normalize 找不到它明明看得到的那條流。
        source = str(p["source"] or "").strip() or "test"
        out = str(p["out"] or "").strip() or "mask"
        src = require_image(ctx, self.key, source)
        h, w = src.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        for name in self.region_list(p):
            # 不存在的名字讓 require_roi 拋帶說明的錯（lint 的 unknown-region
            # 平常就會先擋下來；跑到這裡代表使用者硬跑，錯誤要講得出話）。
            ctx.require_roi(name)
            for (x, y, bw, bh) in ctx.roi_rects(name, (h, w)):
                x0, y0 = max(0, int(x)), max(0, int(y))
                x1 = min(w, int(x) + int(bw))
                y1 = min(h, int(y) + int(bh))
                if x1 > x0 and y1 > y0:
                    mask[y0:y1, x0:x1] = 255
        if not mask.any():
            # 區域存在但全部落在影像外／退化成零面積 —— mask 全 0 時下游會
            # 退回整張圖，這裡先講一聲，不然這條路整段都是安靜的。
            ctx.warn("roi_mask: the regions cover no pixels at this patch "
                     "size; downstream cards will fall back to the whole "
                     "image.")
        ctx.set_image(out, mask)
        return ctx

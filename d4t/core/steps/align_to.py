# d4t step-card library — authored 2026-08-19 (F15-C).
"""align_to —— **小圖在大圖裡的哪裡**，裁一塊同尺寸的出來。

為什麼需要它
------------
EBI 的 patch 是 128²、RSEM 的影像是 1000² —— 兩者放在一起，下游沒有一張卡比得
起來（`subtract` 要同尺寸、`glv_stats` 量的是整張）。這張卡把大圖裁成「跟小圖
同尺寸、而且對齊到同一個結構」的一塊，之後 Enhance / ROI / Measure **一行都不用
改**。

它同時是配對的**確認**
----------------------
`pair_source` 用座標挑候選，而兩邊的座標都是近似的 —— 疊到的那一塊 RSEM 可能
根本不是同一個東西。`ncc_score` 就是那個答案：配錯的時候它會掉下來，而它是一個
擋得掉的數字（寫進分數表達式，或用 `min_score`）。

`candidates` > 1 時，**座標給候選、NCC 選最像的**：`pair_source` 把前 K 顆都
留在 `meta`，這張卡逐一算 NCC 取最高。座標最近的那一顆不一定是對的。

為什麼在 Compare 段
-------------------
這個 repo 的分段規則：**Compare = 兩張圖進、一張圖出**（`subtract` 是原型）。
這張卡吃 template + search、吐一張裁切對齊過的圖 —— 逐字符合。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from ..algo.align import locate_template
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_COMPARE, ParamSpec, Step, StepError, register_step,
)
from ._util import ensure_gray, require_image, resize_to


@register_step
class AlignToStep(Step):
    """小圖當模板在大圖裡找位置，裁一塊同尺寸的出來。"""

    key = "align_to"
    label = "Align to another stream"
    category = CATEGORY_IMAGE
    group = GROUP_COMPARE
    help = ("Find where the small image sits inside the big one and cut out a "
            "piece the same size, so the two can be compared at all. The match "
            "score comes out as a feature - when the two are not the same "
            "defect it drops, which is how a wrong pairing shows up instead of "
            "quietly producing numbers.")
    params = [
        ParamSpec(name="template", type="image_key", direction="in",
                  default="test", label="Small image",
                  help="The small image to look for (an EBI patch, typically)."),
        ParamSpec(name="search", type="image_key", direction="in",
                  default="paired", label="Search inside",
                  help=("The big image to look in - normally the stream a "
                        "Pair card brought in.")),
        ParamSpec(name="min_score", type="float", default=0.3, min=-1.0, max=1.0,
                  label="Accept above",
                  help=("How alike the two have to be before the match counts. "
                        "Below this the card stops and says so, and the rest "
                        "of the batch carries on.")),
        ParamSpec(name="scale", type="float", default=0.0, min=0.0, max=100.0,
                  label="Size ratio",
                  advanced=True,
                  help=("How much bigger one pixel of the small image is than "
                        "one pixel of the big one. Leave it at 0 and the card "
                        "works it out from the pixel size you put on the two "
                        "cards that read the data. Put a number in to override "
                        "that. Two tools rarely have the same pixel size, and "
                        "matching does not work at all if the ratio is more "
                        "than a few percent out.")),
        ParamSpec(name="out", type="image_key", direction="out",
                  default="aligned", label="Name this image",
                  help=("The piece cut out of the big image, at the big "
                        "image's pixel size. Nothing is resampled on the way "
                        "out - resampling changes grey levels, and grey levels "
                        "are what the cards downstream measure.")),
    ]
    reads = ["test", "paired"]
    writes = ["aligned"]
    features_out = ["ncc_score", "align_ok", "align_dx_px", "align_dy_px",
                    "align_scale"]

    @classmethod
    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
        out = []
        for name in ("template", "search"):
            v = str(params.get(name, "") or "").strip()
            if v and v not in out:
                out.append(v)
        return out

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("out", "aligned") or "").strip()
        return [name] if name else []

    # ---- 候選：座標給的那幾顆，這裡挑最像的 -------------------------------
    def _candidates(self, ctx: Context, search: np.ndarray) -> List[np.ndarray]:
        """要在哪幾張大圖裡找（`pair_source` 留在 meta 的那幾顆）。

        沒有候選清單時就只有一張 —— 那是最常見的情形，也是這張卡單獨使用
        （不接 `pair_source`）時的樣子。
        """
        extra = list(ctx.meta.get("pair_candidates") or [])
        return [search] + [np.asarray(a) for a in extra]

    def _scale_for(self, ctx: Context, p: Dict[str, Any]) -> float:
        """小圖要縮放幾倍才跟大圖同一個尺度（2026-08-20）。

        ``scale > 0`` = 使用者自己填的，說了算。``0`` = 自動：拿兩條流各自的
        nm/px 相除（`Context.stream_nm_per_px`，由讀資料的那張卡填）。
        兩邊有一邊不知道就是 1.0（＝「當作一樣」），而**算出來的值會變成一個
        特徵**（``align_scale``）—— 這個數字影響每一顆的結果，不可以只活在
        某個人的腦子裡。
        """
        given = float(p.get("scale", 0.0) or 0.0)
        if given > 0:
            return given
        t = ctx.stream_nm_per_px(str(p["template"]))
        s = ctx.stream_nm_per_px(str(p["search"]))
        if not t or not s or s <= 0:
            return 1.0
        return float(t) / float(s)

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        tmpl = ensure_gray(require_image(ctx, self.key, str(p["template"])))
        search = ensure_gray(require_image(ctx, self.key, str(p["search"])))

        # ---- 尺度：兩台機台的像素大小不一樣，NCC 本身不含縮放 ---------------
        scale = self._scale_for(ctx, p)
        ctx.add_feature("align_scale", float(scale))
        if abs(scale - 1.0) > 1e-6:
            # **只有拿去比對的那一份被重採樣**，裁出來的那一塊沒有（見 `out`）。
            th0, tw0 = tmpl.shape[:2]
            new_w = max(1, int(round(tw0 * scale)))
            new_h = max(1, int(round(th0 * scale)))
            tmpl = resize_to(tmpl, (new_h, new_w))

        th, tw = tmpl.shape[:2]
        sh, sw = search.shape[:2]
        if th > sh or tw > sw:
            raise StepError(
                self.key,
                "the small image (%d×%d) does not fit inside the one being "
                "searched (%d×%d). “Small image” and “Search inside” are the "
                "wrong way round." % (tw, th, sw, sh))

        best = (0.0, 0.0, -2.0, 0)          # x, y, score, 第幾個候選
        for i, cand in enumerate(self._candidates(ctx, search)):
            c = ensure_gray(np.asarray(cand))
            if c.shape[0] < th or c.shape[1] < tw:
                continue
            x, y, score = locate_template(c, tmpl)
            if score > best[2]:
                best = (x, y, score, i)
        x, y, score, which = best

        ctx.add_feature("ncc_score", float(max(score, 0.0) if score > -2 else 0.0))
        ctx.add_feature("align_dx_px", float(x))
        ctx.add_feature("align_dy_px", float(y))
        ok = score >= float(p["min_score"])
        ctx.add_feature("align_ok", 1.0 if ok else 0.0)
        ctx.meta["align_to"] = {"x": float(x), "y": float(y),
                                "score": float(score), "candidate": int(which)}
        if not ok:
            raise StepError(
                self.key,
                "the best match scores %.2f, below the %.2f you asked for - "
                "these two are probably not the same defect. It is recorded as "
                "align_ok = 0 and the rest of the batch is unaffected."
                % (score, float(p["min_score"])))

        picked = self._candidates(ctx, search)[which]
        picked = ensure_gray(np.asarray(picked))
        # 裁在整數格上（次像素的那一點點留在 align_dx_px 裡）——**不要為了
        # 對齊而重採樣**：重採樣會動到灰階，而下游量的正是灰階。
        x0 = int(max(0, min(round(x), picked.shape[1] - tw)))
        y0 = int(max(0, min(round(y), picked.shape[0] - th)))
        out_key = str(p["out"]).strip() or "aligned"
        ctx.set_image(out_key, np.ascontiguousarray(picked[y0:y0 + th,
                                                          x0:x0 + tw]))
        # 裁出來的那一塊是**大圖的像素**，所以它帶的是大圖的 nm/px ——
        # 下游在它身上量 CD 的時候，`_nm` 那一份才會是對的。
        ctx.set_stream_nm_per_px(out_key, ctx.stream_nm_per_px(str(p["search"])))
        return ctx

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

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..algo.align import locate_template_peaks
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
        ParamSpec(name="search_within", type="float", default=15.0,
                  min=0.0, max=100.0, unit="% of FOV",
                  label="Look this far from the middle",
                  help=("The tool moves to the defect's coordinate before it "
                        "takes the big image, so the defect is near the middle "
                        "- it is only off by however far the stage missed. "
                        "Searching just that patch is faster and, more "
                        "importantly, cannot land on a lookalike at the far "
                        "side of the image. Set it to 0 to search the whole "
                        "image.")),
        ParamSpec(name="expect_dx_px", type="float", default=0.0,
                  min=-100000.0, max=100000.0, unit="px",
                  label="Expected shift across", advanced=True,
                  help=("Where the middle really is, if the stage misses by "
                        "about the same amount every time. Run a batch, take "
                        "the middle value of align_off_x_px, put it here - the "
                        "search patch then sits where the defect actually "
                        "lands, so it can be smaller.")),
        ParamSpec(name="expect_dy_px", type="float", default=0.0,
                  min=-100000.0, max=100000.0, unit="px",
                  label="Expected shift down", advanced=True,
                  help="Same as the one above, down the image."),
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
    #: 順序＝**調這張卡的時候要先看哪一個**（儀表一次畫五條，`MeasureInspector`
    #: 依這個順序取）。分數、可不可信、偏了多少 —— 那三件事決定要不要動參數；
    #: 絕對座標與尺度是查問題時才看的。
    features_out = ["ncc_score", "align_peak_ratio",
                    "align_off_x_px", "align_off_y_px",
                    "align_ok", "align_dx_px", "align_dy_px", "align_scale"]

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

    # ---- 只在該找的地方找（2026-08-20）-----------------------------------
    @staticmethod
    def _expected_topleft(search_shape, tmpl_shape, p) -> Tuple[float, float]:
        """模板左上角**預期**落在哪：影像中心（＋使用者量到的系統性偏移）。

        機台是先移到那一顆的座標才拍的，所以 defect 就在中間 —— 差的只有
        stage 沒對準的那一點（使用者：「抓 FOV ~15% 左右」）。
        """
        sh, sw = int(search_shape[0]), int(search_shape[1])
        th, tw = int(tmpl_shape[0]), int(tmpl_shape[1])
        ex = sw / 2.0 - tw / 2.0 + float(p.get("expect_dx_px", 0.0) or 0.0)
        ey = sh / 2.0 - th / 2.0 + float(p.get("expect_dy_px", 0.0) or 0.0)
        return ex, ey

    def _window(self, img: np.ndarray, tmpl_shape, p):
        """要在大圖的哪一塊裡找 —— 回 ``((x0, y0), 那一塊)``。

        ``search_within = 0`` = 整張圖（這張卡單獨使用時的樣子）。
        框永遠夾在影像裡，而且至少裝得下模板。
        """
        pct = float(p.get("search_within", 0.0) or 0.0)
        sh, sw = img.shape[:2]
        th, tw = int(tmpl_shape[0]), int(tmpl_shape[1])
        if pct <= 0:
            return (0, 0), img
        ex, ey = self._expected_topleft((sh, sw), (th, tw), p)
        mx, my = pct / 100.0 * sw, pct / 100.0 * sh
        x0 = int(max(0, min(round(ex - mx), sw - tw)))
        y0 = int(max(0, min(round(ey - my), sh - th)))
        x1 = int(min(sw, max(x0 + tw, round(ex + tw + mx))))
        y1 = int(min(sh, max(y0 + th, round(ey + th + my))))
        return (x0, y0), np.ascontiguousarray(img[y0:y1, x0:x1])

    @staticmethod
    def _window_note(p, window, search_shape) -> str:
        """配不上的時候，如果框是縮小過的，那件事要講出來。"""
        pct = float(p.get("search_within", 0.0) or 0.0)
        if pct <= 0 or not window:
            return ""
        return (" (only the middle %g%% of the image was searched, %d×%d of "
                "%d×%d - raise “Look this far from the middle”, or set it to 0 "
                "to search all of it)"
                % (pct, window[2], window[3],
                   int(search_shape[1]), int(search_shape[0])))

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

        best = (0.0, 0.0, -2.0, 0.0, 0)     # x, y, score, second, 第幾個候選
        window = None
        for i, cand in enumerate(self._candidates(ctx, search)):
            c = ensure_gray(np.asarray(cand))
            if c.shape[0] < th or c.shape[1] < tw:
                continue
            (x0, y0), patch = self._window(c, (th, tw), p)
            if i == 0:
                window = (x0, y0, patch.shape[1], patch.shape[0])
            x, y, score, second = locate_template_peaks(patch, tmpl)
            if score > best[2]:
                best = (x + x0, y + y0, score, second, i)
        x, y, score, second, which = best

        # 預期位置（框的中心）—— `align_off_*` 是「偏離它多少」，也就是這一顆的
        # stage offset。整批取中位數就是這台機器**系統性**的那一份，填回
        # `expect_dx_px` 之後框就可以縮小。
        ex, ey = self._expected_topleft(search.shape[:2], (th, tw), p)
        ctx.add_feature("ncc_score", float(max(score, 0.0) if score > -2 else 0.0))
        ctx.add_feature("align_dx_px", float(x))
        ctx.add_feature("align_dy_px", float(y))
        ctx.add_feature("align_off_x_px", float(x - ex))
        ctx.add_feature("align_off_y_px", float(y - ey))
        # 第一名與第二名的比 —— 越接近 1，這個位置越是猜的（週期性結構）。
        ratio = (float(second) / float(score)) if score > 1e-9 else 1.0
        ctx.add_feature("align_peak_ratio", float(min(max(ratio, 0.0), 1.0)))
        ok = score >= float(p["min_score"])
        ctx.add_feature("align_ok", 1.0 if ok else 0.0)
        ctx.meta["align_to"] = {"x": float(x), "y": float(y),
                                "score": float(score), "second": float(second),
                                "candidate": int(which),
                                "expected": [float(ex), float(ey)],
                                "window": list(window) if window else None}
        if not ok:
            raise StepError(
                self.key,
                "the best match scores %.2f, below the %.2f you asked for - "
                "these two are probably not the same defect%s. It is recorded "
                "as align_ok = 0 and the rest of the batch is unaffected."
                % (score, float(p["min_score"]),
                   self._window_note(p, window, search.shape[:2])))

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

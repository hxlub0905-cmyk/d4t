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

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..algo.align import locate_template_peaks
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_COMPARE, ParamSpec, Step, StepError, register_step,
)
from ._util import ensure_gray, require_image, resize_to

#: 標記的**角色**（`Step.overlay_marks` 的 ``labels``）。``!`` 開頭表示
#: 「這不是區域名，是一個角色」—— UI 據此上色，而顏色住在 UI（core 不得
#: import Qt）。報表那邊是同一組語言：框紅、十字綠（`export/overlay.py`）。
MARK_MATCH = "!match"        # 小圖真的對到的那一塊
MARK_AIM = "!aim"            # 機台瞄準的那一點


@register_step
class AlignToStep(Step):
    """小圖當模板在大圖裡找位置，裁一塊同尺寸的出來。"""

    key = "align_to"
    #: ``key`` 不動（recipe 的鍵）。名字是使用者取的（F16）：**H2H = head to
    #: head**。三個字母在卡片庫裡看不出它做什麼，所以 ``help`` 的**第一句**要
    #: 把全稱與這張卡做的事一起講完 —— 那一句同時是節點副標與 tooltip 的開頭，
    #: 是使用者唯一會讀到的地方。
    label = "H2H"
    category = CATEGORY_IMAGE
    group = GROUP_COMPARE
    help = ("Head to head: find where this small image sits inside a bigger "
            "one and cut out a piece the same size, so the two can be compared "
            "at all. The match score comes out as a feature - when the two are "
            "not the same defect it drops, which is how a wrong pairing shows "
            "up instead of quietly producing numbers.")
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
                  help=("Only search this much of the image, measured out from "
                        "the middle. It fits a review tool, which moves to the "
                        "defect's coordinate before it takes the picture, so "
                        "the defect is near the middle and is only off by "
                        "however far the stage missed. Searching just that "
                        "patch is faster and cannot land on a lookalike at the "
                        "far side of the image. ⚠ Set it to 0 whenever the "
                        "picture is NOT taken around this defect - a blanket "
                        "scan, where the defect sits wherever it happened to "
                        "be found. Leaving it at 15 there does not fail "
                        "loudly: the card searches the middle, finds the best "
                        "of a bad lot, and reports a wrong position with a "
                        "score that can still pass “Accept above”.")),
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
    FEATURE_HELP = {
        "ncc_score": "how well the small image matched, -1 to 1",
        "align_peak_ratio": "best match over the runner-up (near 1 = not sure)",
        "align_off_x_px": "where it landed inside the big image, px",
        "align_off_y_px": "where it landed inside the big image, px",
        "align_ok": "1 when the match was good enough to use",
        "align_dx_px": "how far it moved, px (left/right)",
        "align_dy_px": "how far it moved, px (up/down)",
        "align_scale": "size ratio between the two images",
    }

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

    @staticmethod
    def _upstream_found_nothing(ctx: Context, keys: Sequence[str]) -> bool:
        """接進來的流不在，**而且**是上游配對卡沒配到造成的（F33）。

        三個條件缺一不可，因為「讓路」與「接錯線」不可以長得一樣：

        1. 那條流真的不在 —— 有圖就照比，這張卡不去猜；
        2. `meta["pair_match"]["index"] == -1` —— 上游確實跑過而且沒配到；
        3. 那張卡的 ``out`` **就是**缺的那一條 —— 少了這一條，畫布上另一條線
           接錯（打錯流名）的 recipe 也會被當成「沒配到」而安靜跳過，於是每一
           顆都沒有數字、而畫面上沒有任何一句話說為什麼。

        ⚠ **兩個輸入都要問**。配對卡的圖接在哪一個埠是使用者拉的線決定的，
        而 characterization 那條 recipe 正是接**在 template 上**（小圖是 EBI
        的 patch、大圖是 RSEM 空拍）。只問 ``search`` 的話，那條 recipe 上
        「沒配到」的每一顆仍然會炸 —— 而那正是要數的那一類。
        （這一條是端對端跑出來的：單元測試只接了 ``search``，八顆裡的三顆
        照樣 `ok=False`。）

        接錯線的那一種照舊從 `require_image` 炸出帶說明的錯誤。
        """
        pm = ctx.meta.get("pair_match") or {}
        try:
            missed = int(pm.get("index", 0)) == -1
        except (TypeError, ValueError):
            return False
        if not missed:
            return False
        out_key = str(pm.get("out", ""))
        return bool(out_key) and any(
            str(k) == out_key and str(k) not in ctx.images for k in keys)

    # ---- 影像上的標記（見 Step.overlay_marks）------------------------------ #
    #: 這張卡交的是**結構**（一個框、一個十字），不是掃描線 —— 線本身就是
    #: 答案，淡化只會把唯一的資訊藏起來。見 `Step.marks_solid`。
    marks_solid = True

    @classmethod
    def overlay_marks(cls, ctx: Any, params: Dict[str, Any],
                      stream: Optional[str] = None) -> Any:
        """在預覽上畫**對到哪（框）**與**瞄準哪（十字）**（F33）。

        這張卡以前在預覽上什麼都不畫 —— 而它做的事偏偏是「位置」。使用者
        2026-08-26：「名義上 defect 會在 FOV 正中央…可是這樣就沒有明確在圖上
        指出 defect 位置。」報表那邊已經畫了（`output_char` 的 `mark_defect`），
        這裡是**同一件事在調參數的時候**：拖 `search_within`、填 `expect_dx_px`
        的當下就看得到框往哪裡跑，而不是跑完一整批才知道。

        兩個記號各自回答一半，而**它們的間距就是這一顆的 stage 偏移**
        （＝`align_off_*`，見 `docs/history/plans/F33-ebi-characterization.md` §8.6）：

        * **框** —— 小圖真的對到的那一塊（``x/y`` ＋ 模板尺寸）；
        * **十字** —— 機台瞄準的那一點（``expected`` 的中心）。

        ⚠ **只畫在被搜的那條流上。** 座標是**大圖**的，畫到 ``test``（模板）或
        ``aligned``（裁出來的那一塊）上就指著錯的地方 —— 而正規化座標會讓它看
        起來像個正常的框。`stream` 不知道是哪一條時不過濾（同 CD：**過濾要
        根據知道的事，不是猜的**），因為 Studio 一定會給。
        """
        note = dict((getattr(ctx, "meta", None) or {}).get("align_to") or {})
        want = str(stream or "").strip()
        mine = str(note.get("search") or "").strip()
        if want and mine and mine != want:
            return [], [], -1, []
        shape = list(note.get("shape") or [])
        size = list(note.get("size") or [])
        if len(shape) != 2 or len(size) != 2:
            return [], [], -1, []
        sw, sh = float(shape[0]), float(shape[1])
        tw, th = float(size[0]), float(size[1])
        if sw <= 0 or sh <= 0:
            return [], [], -1, []

        lines: List[Any] = []
        try:
            x0, y0 = float(note["x"]) / sw, float(note["y"]) / sh
        except (KeyError, TypeError, ValueError):
            return [], [], -1, []
        x1, y1 = x0 + tw / sw, y0 + th / sh
        # 四邊 ＋ **四個角各一個實心點**。角點是這個畫面既有的語彙（GLV 的
        # 典型格用同一招），而且小圖上框縮成幾個像素時，角點還認得出來。
        lines += [[(x0, y0), (x1, y0)], [(x1, y0), (x1, y1)],
                  [(x1, y1), (x0, y1)], [(x0, y1), (x0, y0)]]
        corners = [[(x0, y0)], [(x1, y0)], [(x1, y1)], [(x0, y1)]]

        exp = list(note.get("expected") or [])
        if len(exp) == 2:
            cx = (float(exp[0]) + tw / 2.0) / sw
            cy = (float(exp[1]) + th / 2.0) / sh
            arm = 0.04
            lines += [[(cx - arm, cy), (cx + arm, cy)],
                      [(cx, cy - arm), (cx, cy + arm)]]
            corners += [[(cx, cy)], []]     # 十字的中心也點一個
        # `points` 要跟 `lines` 等長（長度對不上就整組不畫）。
        while len(corners) < len(lines):
            corners.append([])
        # **卡片說角色，UI 挑顏色**（同 `overlay_marks` 那句「meta 的形狀是那張
        # 卡的事，UI 只負責畫」）。``!`` 開頭＝這不是一個區域名，是一個角色
        # （沿用 `decide_tree` 的 ``!failed`` / ``!unbinned`` 那個慣例）——
        # 區域名是識別字，不可能撞到。
        roles = [MARK_MATCH] * 4 + [MARK_AIM] * (len(lines) - 4)
        return lines, corners, -1, roles

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        if self._upstream_found_nothing(ctx, (p["template"], p["search"])):
            # 上游那張配對卡沒配到 → 這一顆沒有東西可以比，**安靜讓路**
            # （F33）：一個數字都不寫（算不出來的不寫），這一顆繼續走完，
            # 由判定樹的第一題 `pair_found` 去數它。以前這裡會炸，於是
            # 「根本沒偵測到」那一類全部變成 ok=False —— 而那正是要數的東西。
            ctx.warn("[%s] the pair card upstream found no match for this "
                     "defect (pair_found = 0), so there is nothing to compare "
                     "it with - skipped." % self.key)
            return ctx
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
        # **第二名答不出來（NaN）就不寫這一格**：搜尋窗縮到比遮罩半徑還小的
        # 時候整張回應圖都被蓋掉，而那時候硬寫一個 0.00 等於說「遙遙領先」——
        # 剛好在陣列區、剛好在使用者最需要它講實話的時候（F33）。
        if second == second:                       # 不是 NaN
            ratio = (float(second) / float(score)) if score > 1e-9 else 1.0
            ctx.add_feature("align_peak_ratio",
                            float(min(max(ratio, 0.0), 1.0)))
        ok = score >= float(p["min_score"])
        ctx.add_feature("align_ok", 1.0 if ok else 0.0)
        # ``search`` / ``size`` 是給**報表畫標記**用的（F33）：框要畫在
        # 「這張卡真的搜過的那條流」上，不是隨便一張圖。少了這兩個，出圖那邊
        # 只能用流名去猜，而猜錯的那一次是「圖上有一個框、指著錯的地方」——
        # 比沒有框糟得多（同 `_draw_roi_boxes` 的「不猜」）。
        ctx.meta["align_to"] = {"x": float(x), "y": float(y),
                                "score": float(score), "second": float(second),
                                "candidate": int(which),
                                "expected": [float(ex), float(ey)],
                                "search": str(p["search"]),
                                "size": [int(tw), int(th)],
                                "shape": [int(sw), int(sh)],
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

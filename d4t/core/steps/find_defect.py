# d4t step-card library — authored 2026-08-25 (F29).
"""find_defect — **這張圖上最可疑的東西在哪**。

使用者 2026-08-25（defect team 的分析工程師）：「我跑完整筆 image，想要看到的
是這種結果（defect 抓出來 …… 我希望也能針對 RSEM image 也能 detect 出來）」。

這張卡吐什麼（以及**不**吐什麼）
--------------------------------
使用者問過一句「Detect 你要 detect 什麼？數字？」—— 答案是**不是數字，是一個
框**。而且只欠那一個框：

* **排序**已經有了 —— 就是使用者自己寫的 ``score``
  （`export.overlay.pick_overlay_results` 現在就照它由大到小排）。
* **多大、長什麼樣**已經有了 —— `cd_measure` 的團那一支。
* **哪一塊不一樣**已經有了 —— `glv_stats` 的 ``the other regions``。

所以這張卡只做剩下的那一件事：在一條流（可以再指定一塊區域）裡切出過門檻的
每一團，照「比背景高出幾個 σ」排序，**取最強的那一個**，把它的框與強度吐成
特徵。框那四個名字（``blob_x``/``blob_y``/``blob_w``/``blob_h``）**是
`export.overlay.primary_blob_box` 本來就在讀的那四個** —— 疊圖因此一行都不用改。

什麼時候需要它（它是退路，不是主力）
------------------------------------
CD 卡量團的時候順手就知道位置，而 F29 已經把那個位置接出來了
（``cd_box_*``，見 `cd.py` 檔頭）。所以**已經在量 CD 的人不需要這張卡**。
需要它的是那三種：

1. **沒有在量 CD**（只想框出來、排個序，不需要尺寸）；
2. **CD 在線那一支**（它的「位置」是一條掃描線，不是一個東西）；
3. **一塊區域裡不只一個東西**，而你要的是最突出的那一個 —— CD 挑的是
   **中心那一團**（patch 以缺陷為中心裁切），這張卡**去找**。

那個差別在 RSEM 大圖上是全部：缺陷不保證在正中央。

界線：**可以找一個框，不可以產生具名區域**
------------------------------------------
使用者 2026-08-20 定調「Blob 分割不需要 也不要再出現」。這張卡把界線往前挪了
一格，而挪的是哪一格要講清楚 —— 它**不呼叫 `ctx.add_region()`**，一個具名區域
都不生。

理由不是形式：具名區域是**下游每一張卡的輸入**（``roi=`` 那一格），一張卡自動
長出區域等於畫布上出現一條沒有人拉過的線，而 F9 那六個「跑得完、有數字、而且
是錯的」全部長那個樣子。一個框只是一組數字：它進 CSV、進疊圖、進分數表達式，
跟任何一個特徵一樣**要有人接才會被用到**。

⚠ 也**不寫 ``ctx.meta["blobs"]``**（`render_overlay` 認得的那條 richer path）。
同一件事存兩份的話兩份會漂，而特徵那一份已經夠疊圖用了。要畫在預覽上的那一份
走 :meth:`overlay_marks`，讀的是 ``ctx.meta["find_defect"]`` —— 那一份存的是
**畫得出來所需要的東西**（框與質心），不是特徵的副本。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from ..algo import edge as algo_edge
from ..algo import shape as algo_shape
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, register_step, GROUP_MEASURE,
)
from ._util import (
    MultiSourceStep, ensure_gray, output_prefix_spec, roi_rect_or_none,
)

#: 找不到東西的時候那一句話（跟 `cd.py` 的 ``_BLOB_REASONS`` 同一組字 ——
#: **同一個原因在兩張卡上要講同一句話**，否則使用者會以為是兩件事）。
_REASONS = {
    "flat": "nothing stands out from the background there",
    "no_blob": "everything that crossed the threshold is smaller than the "
               "minimum size",
    "too_small": "the region is too small to look in",
}

#: 一律吐的三個 —— 「它看了、它決定了什麼」。
#:
#: * ``blob_n`` —— 過門檻的候選有幾個。**只有一個候選跟有十七個是兩件事**，
#:   而 ``blob_x`` 那幾格看起來一模一樣（F19「量得準不準」那一族）。
#: * ``blob_bright`` —— ``target="auto"`` 這一顆挑了哪一個極性。逐顆翻轉的話，
#:   ``blob_strength`` 那一欄會同時裝著兩種東西，而 CSV 上沒有別的線索
#:   （同 ``cd_bright``，那是實跑合成 lot 才發現要有的）。
#: * ``blob_edge_score`` —— **「為什麼沒找到」的那個數字**。一整批畫出來就看得到
#:   門檻該往哪邊調（同 ``cd_edge_score``，而且是同一支 `edge_quality`）。
ALWAYS = ("blob_n", "blob_bright", "blob_edge_score")

#: 找到東西才吐的（找不到就**一格都不寫** —— 不是 0、也不是 NaN）。
#:
#: 0 會讓疊圖在左上角畫一個 0×0 的框，看起來像量到了；而 ``blob_strength = 0``
#: 進得了分數表達式，一路安靜到 bin。
WHEN_FOUND = ("blob_x", "blob_y", "blob_w", "blob_h",
              "blob_cx", "blob_cy",
              "blob_strength", "blob_area_px", "blob_deq")


@register_step
class FindDefectStep(MultiSourceStep):
    """在一條流（可再指定一塊區域）裡找出最突出的那一團，給框與強度。"""

    key = "find_defect"
    label = "Find defect"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Find the thing that stands out most in the image and put a box "
            "round it. Use it when you want the defect found for you rather "
            "than measured where you point - on a full-size SEM image the "
            "defect is not in the middle. It writes where the box is and how "
            "far the thing inside it stands out from the background, so the "
            "overlay images have a box on them and the report can be sorted "
            "worst-first.")
    params = [
        ParamSpec(name="source", type="image_keys", direction="in",
                  default="diff",
                  help=("Which image stream to look in. A difference image is "
                        "the easiest place to look, because the structure has "
                        "already been subtracted out of it and whatever is "
                        "left is the defect. Without one, look in the test "
                        "image and narrow it down with a region.")),
        ParamSpec(name="roi", type="region_keys", direction="in", default="",
                  label="Region",
                  help=("Which region(s) to look in - drag a line from the "
                        "Region card that defines each one. Two regions here "
                        "means look in both, and every number gets its "
                        "region's name in front of it. No line means look in "
                        "the whole image.")),
        ParamSpec(name="target", type="icon_choice", default="auto",
                  label="Look for the",
                  choices=["auto", "bright", "dark"],
                  icons=["target_auto", "target_bright", "target_dark"],
                  choice_help={
                      "auto": "Whichever of the two stands out more. It writes "
                              "down what it picked in blob_bright.",
                      "bright": "Something brighter than its surroundings (a "
                                "particle, a residue).",
                      "dark": "Something darker than its surroundings (a void, "
                              "a missing pattern).",
                  },
                  help=("Is the thing you are looking for brighter or darker "
                        "than what is round it? This is a question about your "
                        "sample, not about the software.")),
        # **跟 CD 同一格、同一支函式**（`algo.edge.threshold_level`）。
        # 分成兩份的那天，同一句話會長出兩種意思。
        ParamSpec(name="threshold_pct", type="int", default=50, min=1, max=99,
                  unit="%", section="Where the edge is",
                  label="…at this height",
                  help=("How far up from the background to the brightest part "
                        "counts as being part of the thing. 50% of the local "
                        "contrast is the usual choice. Raising it finds "
                        "smaller, more definite blobs.")),
        ParamSpec(name="min_area", type="int", default=algo_shape.MIN_AREA,
                  min=1, max=100000, unit="px", advanced=True,
                  label="Ignore blobs smaller than",
                  help=("Bits smaller than this are not counted at all. The "
                        "smallest thing this card can see is about 3x3 px - "
                        "below that a real speck and a pair of hot pixels look "
                        "the same.")),
        ParamSpec(name="min_edge", type="float",
                  default=algo_edge.MIN_QUALITY, min=0.0, max=0.95,
                  advanced=True,
                  label="Ignore blobs weaker than",
                  help=("How much something has to stand out from the noise "
                        "before it counts at all, from 0 (anything) to 0.95 "
                        "(only very clean ones). Turning it to 0 lets the card "
                        "find the noise itself, which produces a perfectly "
                        "normal-looking box on every defect.")),
        output_prefix_spec("hot"),
    ]
    reads = ["diff"]
    writes: List[str] = []
    features_out = list(ALWAYS) + list(WHEN_FOUND)

    REQUIRE_IMAGE = True

    #: ``ctx.meta`` 上放「畫得出來的那一份」的鍵。
    META_KEY = "find_defect"

    # ---- 宣告 ------------------------------------------------------------- #
    @classmethod
    def feature_names(cls, params: Dict[str, object]) -> List[str]:
        return list(ALWAYS) + list(WHEN_FOUND)

    # ---- 量 --------------------------------------------------------------- #
    def measure(self, ctx: Context, img, p: Dict[str, Any]):
        gray = ensure_gray(np.asarray(img))
        rect = roi_rect_or_none(ctx, self.key, gray, p["roi"])
        x, y, w, h = (int(v) for v in rect)
        block = gray[y:y + h, x:x + w]
        where = str(p.get("roi") or "the whole image")
        if block.size == 0 or min(block.shape[:2]) < 3:
            ctx.warn("[%s] region '%s' is only %d×%d px on this defect - too "
                     "small to look in. Nothing found for it."
                     % (self.key, where,
                        block.shape[1] if block.ndim > 1 else 0,
                        block.shape[0] if block.ndim > 0 else 0))
            return None

        scan = algo_shape.find_blobs(
            block, target=str(p["target"]),
            frac=float(p["threshold_pct"]) / 100.0,
            min_quality=float(p["min_edge"]), min_area=int(p["min_area"]))

        self._note(ctx, gray, (x, y, w, h), scan, p)

        feats: Dict[str, float] = {
            "blob_n": float(len(scan.hits)),
            "blob_bright": 1.0 if scan.target == "bright" else 0.0,
            "blob_edge_score": float(scan.quality),
        }
        if not scan.hits:
            ctx.warn("[%s] found nothing in %s: %s. No box is written for this "
                     "defect; the rest of the batch is unaffected."
                     % (self.key, where,
                        _REASONS.get(scan.reason, scan.reason)))
            return feats

        # **最強的那一個**（使用者定調 2026-08-25：「最強的那一個」）——
        # 一顆 defect 一列的結果模型因此一個位元都不用動。其餘的候選數得出來
        # （`blob_n`），但只有這一個有座標。
        best = scan.hits[0]
        bx, by, bw, bh = best.bbox
        feats.update({
            # **整張影像的像素**（區域偏移在這裡加回去，換算只做這一次）——
            # 疊圖畫在整張圖上，同 `cd_box_*`。
            "blob_x": float(x + bx), "blob_y": float(y + by),
            "blob_w": float(bw), "blob_h": float(bh),
            "blob_cx": float(x + best.centroid[0]),
            "blob_cy": float(y + best.centroid[1]),
            "blob_strength": float(best.strength),
            "blob_area_px": float(best.area),
            "blob_deq": algo_shape.equivalent_diameter(best.area),
        })
        return feats

    # ---- 給預覽畫的那一份 --------------------------------------------------- #
    def _note(self, ctx: Context, gray, rect, scan, p: Dict[str, Any]) -> None:
        """框與質心，**正規化座標**（同 `cd._note_blob`）。

        存的是「畫得出來所需要的東西」，不是特徵的副本 —— 特徵是整張影像的
        像素，這裡是 0..1，而 :meth:`overlay_marks` 只吃後者。
        """
        arr = np.asarray(gray)
        h, w = arr.shape[:2] if arr.ndim >= 2 else (0, 0)
        if not (h and w):
            return
        rx, ry, _rw, _rh = rect
        best = scan.hits[0] if scan.hits else None
        box: List[Any] = []
        centre: List[Any] = []
        if best is not None:
            bx, by, bw, bh = best.bbox
            x0, y0 = (rx + bx) / float(w), (ry + by) / float(h)
            x1, y1 = (rx + bx + bw) / float(w), (ry + by + bh) / float(h)
            box = [(round(x0, 6), round(y0, 6)), (round(x1, 6), round(y0, 6)),
                   (round(x1, 6), round(y1, 6)), (round(x0, 6), round(y1, 6))]
            centre = [(round((rx + best.centroid[0]) / float(w), 6),
                       round((ry + best.centroid[1]) / float(h), 6))]
        prefix = str(p.get(self.CURRENT_PREFIX, "") or "")
        ctx.meta.setdefault(self.META_KEY, {})[prefix] = {
            "region": str(p.get("roi") or ""),
            "stream": str(p.get(self.CURRENT_STREAM, "") or ""),
            "ok": bool(scan.hits), "reason": scan.reason,
            "target_used": scan.target,
            "level": round(float(scan.level), 3),
            "n": len(scan.hits),
            "strength": round(float(best.strength), 4) if best else 0.0,
            "box": box, "centre": centre,
        }

    @classmethod
    def overlay_marks(cls, ctx: Any, params: Dict[str, Any],
                      stream: Optional[str] = None) -> Any:
        """框的四條邊 ＋ 質心那一點（見 :meth:`Step.overlay_marks`）。

        ``stream`` 給了就只交那一條流找到的 —— 這張卡的 ``source`` 是複數
        型別，接兩條線就在兩張**不同的影像**上各找一次，全部畫上去的話，你正在
        看的那張圖上會有一個框是在另一張圖上找到的（同 `cd_measure`）。
        """
        notes = (getattr(ctx, "meta", None) or {}).get(cls.META_KEY) or {}
        lines: List[Any] = []
        points: List[Any] = []
        labels: List[str] = []
        want = str(stream or "").strip()
        for prefix in sorted(notes):
            note = notes[prefix] or {}
            mine = str(note.get("stream") or "").strip()
            if want and mine and mine != want:
                continue
            box = [tuple(pt) for pt in (note.get("box") or [])]
            if len(box) != 4:
                continue
            name = str(note.get("region") or "")
            centre = [tuple(pt) for pt in (note.get("centre") or [])]
            for i in range(4):
                lines.append([box[i], box[(i + 1) % 4]])
                # 質心畫在**最後一條邊**上，這樣四條邊都是同一種東西，而點只有
                # 一個 —— `points[i]` 必須跟 `lines` 等長（set_overlay 的規矩）。
                points.append(centre if i == 3 else [])
                labels.append(name)
        # 框沒有「代表的那一條」—— 四條邊一樣重要，畫粗任何一條都是在說謊。
        return lines, points, -1, labels

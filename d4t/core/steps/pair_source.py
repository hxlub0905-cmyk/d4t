# d4t step-card library — authored 2026-08-19 (F15).
"""pair_source —— **這一顆在另一份資料裡是哪一顆**，把它的圖帶進來。

要解的事：EBI ↔ RSEM(API) characterization
------------------------------------------
RSEM API 空拍（拍滿、直接對影像抓 defect）是 ground truth；拿它回疊 EBI 掃過的
位置，就答得出「這顆真 defect，EBI 到底有沒有掃出來」。而那件事有**三種**結果，
不是兩種：

* 配到、分數高 → 抓到了；
* **配到、但分數低沒被 sample → 藏在 raw data 內**；
* 沒配到 → 根本沒偵測到。

中間那一列是這張卡存在的理由，而它要答得出來就必須把配到那一顆的 **KLARF 欄位**
帶成 feature（`carry`）——否則第一列與第二列在資料上長得一模一樣。

卡片不自己讀檔
--------------
「這張卡 load 自己的 source」是**使用者看到的事**。第二份資料是由 Studio / CLI
載成 `Dataset` 掛在 main 上的（`ingest/pair_source.attach`），這張卡只從已經掛好
的那一份裡挑一顆。理由是快取簽章：卡片偷偷讀檔的話，換一份第二 source 而簽章
看不見 → 回舊影像（鐵則 9，F9 踩過兩次）。

配不到的那一顆
--------------
**不吐流、`paired = 0`。** 下游要那條流的卡會失敗，於是那一顆 `ok=False` 而整批
照跑（鐵則 7）—— 跟 `load_sidecar` 遇到沒有 label 的那一顆是同一個行為，
不發明第二套。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from ..algo import pairing
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_INPUT, ParamSpec, Step, StepError, register_step,
)
from ._util import parse_key_list

#: 配對方式。``position`` 是主力，另外兩個是「先把管線打通」與「兩邊本來就有
#: 共同 id」的路。
MATCHES = ("position", "id", "order")


def _carry_names(params: Dict[str, Any]) -> List[str]:
    return [c.upper() for c in parse_key_list(params.get("carry", ""))]


@register_step
class PairSourceStep(Step):
    """另一份資料的對應那一顆 → 一條影像流。"""

    key = "pair_source"
    label = "Pair with another source"
    category = CATEGORY_IMAGE
    group = GROUP_INPUT
    help = ("Bring in the matching defect from a second lot - the RSEM ground "
            "truth for an EBI scan, for example. Open that lot with the button "
            "on this card, and every defect here is matched to one over there "
            "by wafer position. The match distance and the columns you carry "
            "over become features, so \"detected but scored too low\" is "
            "something you can write into the score. Defects with no match "
            "get paired = 0 and fail this card; the rest of the batch carries "
            "on.")
    params = [
        ParamSpec(
            name="source", type="str", default="",
            label="Source name",
            pattern=r"^([A-Za-z_][A-Za-z0-9_]*)?$",
            pattern_help=("use letters, digits and underscores only, and do "
                          "not start with a digit"),
            help=("Which of the loaded lots to pair with - the name you gave "
                  "it when you opened it on this card. The path is not stored "
                  "in the recipe, so the same recipe runs on the next lot.")),
        ParamSpec(
            name="match", type="choice", default="position", choices=list(MATCHES),
            label="Match by",
            help=("position = nearest defect within the tolerance, in wafer "
                  "coordinates (the usual choice). id = same DEFECTID on both "
                  "sides. order = first with first, second with second - only "
                  "useful when the two lots are known to line up.")),
        ParamSpec(
            name="tol_nm", type="float", default=500.0, min=1.0, max=1e7,
            unit="nm", label="Within",
            show_when=("match", ("position",)),
            help=("How far away a defect on the other side may be and still "
                  "count as the same one. Too big and you pair with the "
                  "neighbour; the match distance comes out as a feature so "
                  "you can see which way to move it.")),
        ParamSpec(
            name="candidates", type="int", default=1, min=1, max=8,
            label="Keep this many candidates",
            show_when=("match", ("position",)),
            help=("Keep the nearest N instead of just the nearest one, so an "
                  "Align card downstream can pick whichever one actually "
                  "looks like this defect. Coordinates are approximate on both "
                  "sides - the nearest one is not always the right one.")),
        ParamSpec(
            name="carry", type="str", default="",
            label="Carry these columns",
            help=("KLARF column names from the matched defect to bring over as "
                  "features, comma separated (for example DEFECTID, "
                  "ROUGHBINNUMBER). This is what makes \"it was detected but "
                  "scored too low\" answerable.")),
        ParamSpec(
            name="channel", type="str", default="",
            label="Which image",
            help=("Which of the matched defect's images to bring in. Leave "
                  "empty for its first one.")),
        ParamSpec(
            name="out", type="image_key", direction="out", default="paired",
            label="Name this image",
            help="Name of the image stream this card produces."),
    ]
    reads: List[str] = []
    writes = ["paired"]
    features_out = ["paired", "match_dist_nm", "match_ambiguous"]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("out", "paired") or "").strip()
        return [name] if name else []

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        out = list(cls.features_out)
        out += ["pair_%s" % c for c in _carry_names(params)]
        return out

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        if not str(params.get("source", "") or "").strip():
            return ["This card has no second lot yet. Use “Open data…” on this "
                    "card - the name you give it is what “Source name” holds."]
        return []

    # ---- 挑哪一顆 --------------------------------------------------------
    def _pick(self, item: Any, others: List[Any], p: Dict[str, Any]):
        """回 ``(配到的那一顆, 距離nm, 容差內還有沒有別人)``；配不到回 ``(None, …)``。

        ``candidates > 1`` 時，**其餘候選留在 ``self._rest``** 讓 `align_to`
        用 NCC 挑 —— 座標最近的那一顆不一定是對的（兩邊的座標都是近似的）。
        """
        self._rest: List[Any] = []
        mode = str(p["match"])
        if mode == "order":
            i = int(getattr(item, "index", -1))
            hit = others[i] if 0 <= i < len(others) else None
            return hit, 0.0, False
        if mode == "id":
            want = str(getattr(item, "defect_id", ""))
            hit = next((o for o in others
                        if str(getattr(o, "defect_id", "")) == want), None)
            return hit, 0.0, False

        # position：座標最近的一顆（演算法見 `algo/pairing`）
        me = pairing.point_of(item)
        if me is None:
            return None, float("nan"), False
        tol = float(p["tol_nm"])
        index = pairing.build_index(others, tol)
        found = pairing.nearest(me, index, tol, k=int(p["candidates"]))
        if not found:
            return None, float("nan"), False
        best, dist = found[0]
        self._rest = [q["item"] for q, _d in found[1:]]
        return best["item"], float(dist), len(found) > 1

    def _image_of(self, hit: Any, channel: str) -> np.ndarray:
        images = dict(getattr(hit, "images", None) or {})
        if not images:
            raise StepError(self.key,
                            "the matched defect %s has no image."
                            % getattr(hit, "defect_id", "?"))
        name = str(channel or "").strip()
        if name and name not in images:
            raise StepError(
                self.key,
                "the matched defect has no image called '%s' (it has: %s)."
                % (name, ", ".join(sorted(images))))
        return hit.load(name or sorted(images)[0])

    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
        p = self.validate_params(params)
        sid = str(p["source"]).strip()
        if not sid:
            raise StepError(self.key, "no second lot chosen yet; use “Open "
                                      "data…” on this card.")
        item = ctx.meta.get("_defect_item")
        if item is None:
            raise StepError(self.key, "no defect data in the Context "
                            "(meta['_defect_item']); this card must be run by "
                            "the engine after a dataset is loaded.")
        others = list((ctx.meta.get("_sources") or {}).get(sid) or [])
        if not others:
            raise StepError(
                self.key,
                "no lot is loaded as '%s'. Open one with “Open data…” on this "
                "card - the second lot is not stored in the recipe, so it has "
                "to be chosen for this run." % sid)

        hit, dist, ambiguous = self._pick(item, others, p)
        # **每一顆都要有這幾個數字**，配到與否都一樣 —— 「沒配到」本身就是
        # characterization 的結論之一，它不可以只是一個缺席的欄位。
        ctx.add_feature("paired", 1.0 if hit is not None else 0.0)
        ctx.add_feature("match_dist_nm", float(dist))
        ctx.add_feature("match_ambiguous", 1.0 if ambiguous else 0.0)
        fields = dict(getattr(hit, "fields", None) or {}) if hit is not None else {}
        for col in _carry_names(p):
            raw = str(fields.get(col, ""))
            try:
                ctx.add_feature("pair_%s" % col, float(raw))
            except (TypeError, ValueError):
                # 帶不動的欄位（DEFECTID 那種字串）留在 meta，讓報表拿得到 ——
                # feature 是**數字**的地盤，塞一個字串進去會讓分數表達式炸在
                # 一個跟它無關的地方。
                ctx.meta.setdefault("pair_fields", {})[col] = raw
        ctx.meta["pair_match"] = {
            "source": sid,
            "defect_id": str(getattr(hit, "defect_id", "")) if hit else "",
            "index": int(getattr(hit, "index", -1)) if hit else -1,
            "dist_nm": float(dist),
            "candidates": int(p["candidates"]),
        }
        # **打錯一個欄位名不可以安靜地沒事**：這張卡的存在理由就是把那幾欄帶
        # 過來（「偵測到但分數太低」只有靠它答得出來），少了一欄的 CSV 跟成功
        # 的 CSV 長得一模一樣。擋在這裡＝這幾顆 ok=False 而整批照跑（鐵則 7）。
        missing = [c for c in _carry_names(p) if hit is not None and c not in fields]
        if missing:
            raise StepError(
                self.key,
                "'%s' has no KLARF column %s. Its columns are: %s. Fix “Carry "
                "these columns” - nothing is carried over until you do."
                % (sid, ", ".join(missing),
                   ", ".join(sorted(fields)) or "(none - that lot has no "
                                                "defect table)"))

        if hit is None:
            raise StepError(
                self.key,
                "no defect in '%s' is within %.0f nm of this one, so there is "
                "nothing to compare it with. It is recorded as paired = 0 and "
                "the rest of the batch is unaffected."
                % (sid, float(p["tol_nm"])))

        ctx.set_image(str(p["out"]).strip() or "paired",
                      self._image_of(hit, p["channel"]))
        # 其餘候選的圖留給 `align_to` 挑（座標給候選、NCC 選最像的）。
        # 讀不出來的候選就跳過 —— 少一個候選不值得殺掉這一顆。
        rest = []
        for other in getattr(self, "_rest", []) or []:
            try:
                rest.append(self._image_of(other, p["channel"]))
            except StepError:
                continue
        ctx.meta["pair_candidates"] = rest
        return ctx

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

排名為什麼算在這裡（F33，2026-08-25）
------------------------------------
「分數低到沒被 sample」問的是**名次**：sample 是照分數排序、每個 die 取前幾名
去 review 的。而那個名次的母體是**第二份的完整 defect list**（幾千筆），
不是這一批跑過 pipeline 的那三十顆。

判定段有一個現成的「跟整批比」（`Let.scale`）—— 它在這裡是錯的，因為它看得到
的只有跑過 pipeline 的那幾十顆，那是「這顆在我挑出來看的 30 顆裡排第幾」，
對 sample 門檻沒有意義。整份只有**掛上來的這一層**看得到，所以排名算在這張卡
（而它本來就是「讀那份資料」的那一層 —— 同「一格 nm/px 長在把那份資料讀進來
的那張卡上」）。

卡片不自己讀檔
--------------
「這張卡 load 自己的 source」是**使用者看到的事**。第二份資料是由 Studio / CLI
載成 `Dataset` 掛在 main 上的（`ingest/pair_source.attach`），這張卡只從已經掛好
的那一份裡挑一顆。理由是快取簽章：卡片偷偷讀檔的話，換一份第二 source 而簽章
看不見 → 回舊影像（鐵則 9，F9 踩過兩次）。

配不到的那一顆**要留下來**（F33，2026-08-25）
--------------------------------------------
**不吐流、`pair_found = 0`、這一顆繼續走。** 以前這裡是 `raise StepError` ——
那一顆於是 `ok=False`、沒有分數也沒有 bin，**走不到判定樹**。而上面那三種結果
裡的第三種（「根本沒偵測到」）正是 characterization 要數的那一類：它被當成錯誤
處理，就等於這個功能問不出自己的結論。CSV 上還看不出來 —— 少了幾列，跟「本來
就沒那幾顆」長得一模一樣。

所以配不到的那一顆現在：`pair_found = 0`（**一律寫**，它就是那個結論）、
其餘 `pair_*` 一格都不寫、下游的 compare 卡靠 `meta["pair_match"]` 安靜讓路
（見 `align_to`）、而這一顆照樣進判定樹。

⚠ `match_dist_nm` 在配不到時**不寫**（以前寫 NaN）。理由有兩層：算不出來的
那一格本來就不該寫（`CLAUDE.md` 共通規矩），而 NaN 更糟 —— 判定樹問問題是
`expr.eval(feats) != 0.0`，`NaN != 0.0` 是 **True**，於是 `match_dist_nm > X`
會對一顆根本沒配到的 defect 答「是」。

判定樹的第一步請問 `pair_found`：`walk` 只評走得到的那條路，所以第三類那一支
永遠問不到 ncc / 分數那幾題，`decide_unanswered` 維持 0。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from ..algo import pairing
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_IMAGE, GROUP_INPUT, ParamSpec, Step, StepError, register_step,
)
from ._util import nm_per_px_spec, parse_key_list

#: 配對方式。``position`` 是主力，另外兩個是「先把管線打通」與「兩邊本來就有
#: 共同 id」的路。
MATCHES = ("position", "id", "order")


def _carry_names(params: Dict[str, Any]) -> List[str]:
    return [c.upper() for c in parse_key_list(params.get("carry", ""))]


def _rank_by(params: Dict[str, Any]) -> str:
    return str(params.get("rank_by", "") or "").strip().upper()


def _rank_within(params: Dict[str, Any]) -> List[str]:
    return [c.upper() for c in parse_key_list(params.get("rank_within", ""))]


def _rank_columns(params: Dict[str, Any]) -> List[str]:
    """排名要用到的欄位（分組欄 + 排序欄）—— 沒設排序欄就一欄都不要。

    這幾欄跟 `carry` 走同一條路進 `DefectItem.fields`（見
    :func:`columns_for_source`）：掛第二份的時候只複製指名的那幾欄，
    而排名讀的是**整份**的那一欄 —— 沒複製過去的話它讀到的是一片空白。
    """
    by = _rank_by(params)
    if not by:
        return []
    out = list(_rank_within(params))
    if by not in out:
        out.append(by)
    return out


def _rank_key(params: Dict[str, Any]) -> Optional[tuple]:
    """這組排名設定的身分；沒設排序欄回 ``None``（＝不算排名）。

    同一份第二 source 可以被兩張卡指著、各自排各自的（一張照分數、一張照
    另一欄）—— 所以備忘是**一組設定一個 key**，不是一份資料一個。
    """
    by = _rank_by(params)
    if not by:
        return None
    return (tuple(_rank_within(params)), by, bool(params.get("rank_desc", True)))


def _rank_all(others: List[Any], key: tuple, sid: str, step_key: str) -> None:
    """把整份第二來源分組排名，結果掛回每一顆 item 上。

    **一份資料算一次**（O(N log N)），不是逐顆算：整份本來就在記憶體裡，
    而 raw KLARF 是幾千幾萬筆 —— 逐顆重排的話 30 顆就掃 30 遍。備忘掛在
    item 物件上（`_d4t_rank`），因為 `sources_for_run` 重建的是 list、
    item 物件是共用的，而重掛一份 lot 會產生全新的 item —— 過期不了。

    **tie-break 是 DEFECTID**：同分的兩筆誰在前面必須是確定的，否則同一份
    資料跑兩次名次會變（而黃金值會抓不到真正的迴歸）。
    """
    within, by, desc = key
    groups: Dict[tuple, List[Any]] = {}
    for item in others:
        fields = dict(getattr(item, "fields", None) or {})
        missing = [c for c in within if c not in fields] or (
            [] if by in fields else [by])
        if missing:
            raise StepError(
                step_key,
                "cannot rank the defects in '%s': the column %s did not come "
                "over. What did: %s. Ranking reads those columns from that "
                "whole lot, so they are copied over with the carried ones."
                % (sid, ", ".join(missing),
                   ", ".join(sorted(fields)) or "(nothing)"))
        raw = str(fields.get(by, ""))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            # **不可以安靜地全部並列第一**：那樣每一顆都拿到 rank 1，
            # 而報表上它跟「真的是第一名」長得一模一樣。
            raise StepError(
                step_key,
                "cannot rank by '%s' in '%s': defect %s has %r there, which "
                "is not a number. Pick the column that holds the tool's own "
                "score in “Rank by”."
                % (by, sid, getattr(item, "defect_id", "?"), raw))
        groups.setdefault(tuple(fields[c] for c in within), []).append(
            (value, str(getattr(item, "defect_id", "")), item))

    for rows in groups.values():
        rows.sort(key=lambda r: (-r[0] if desc else r[0], r[1]))
        total = len(rows)
        for i, (_v, _did, item) in enumerate(rows, start=1):
            memo = getattr(item, "_d4t_rank", None)
            if memo is None:
                memo = {}
                setattr(item, "_d4t_rank", memo)
            memo[key] = (i, total)


def _ensure_ranks(others: List[Any], key: tuple, sid: str,
                  step_key: str) -> None:
    """還沒排過就排一次（探第一顆就知道）。"""
    if not others:
        return
    memo = getattr(others[0], "_d4t_rank", None)
    if memo is not None and key in memo:
        return
    _rank_all(others, key, sid, step_key)


def columns_for_source(nodes: Any, source_id: str) -> List[str]:
    """指著 ``source_id`` 的每一張配對卡，`carry` **＋排名欄位**的聯集（大寫）。

    掛第二份的時候只複製這幾欄（`ingest/pair_source.fill_fields` 的 ``columns``）
    —— raw data 是幾十萬顆，×24 欄字串是幾百 MB，而那幾欄還要 pickle 進 worker。

    **聯集**而不是「某一張卡的」：同一份第二 source 可以被兩張卡指著（兩種配對
    方式各一張），照其中一張填的話另一張會少欄位。

    ``nodes`` 吃的是「有 ``.step`` 與 ``.params`` 的東西」的可迭代物 ——
    `Recipe.nodes.values()`（CLI）與 `RecipeModel.nodes.values()`（Studio）
    都是。**這件事只寫在這裡**：`carry` 的意思是這張卡的事，抄第二份出去的
    那一份會漂。
    """
    want: List[str] = []
    for node in nodes:
        if str(getattr(node, "step", "")) != PairSourceStep.key:
            continue
        params = dict(getattr(node, "params", None) or {})
        if str(params.get("source", "") or "").strip() != str(source_id):
            continue
        # 排名欄位跟 carry 走同一條路：排名讀的是**整份**的那一欄，
        # 沒複製過去的話它讀到一片空白（而那會變成一個很難查的錯誤）。
        for col in _carry_names(params) + _rank_columns(params):
            if col not in want:
                want.append(col)
    return want


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
            "something you can write into the score. A defect with no match "
            "gets pair_found = 0 and still goes through to the decision - "
            "\"the other tool never saw it\" is one of the answers you are "
            "counting, not an error. Ask pair_found first in the tree.")
    params = [
        ParamSpec(
            name="source", type="str", default="",
            label="Source name",
            choices_from="sources",
            pattern=r"^([A-Za-z_][A-Za-z0-9_]*)?$",
            pattern_help=("use letters, digits and underscores only, and do "
                          "not start with a digit"),
            help=("Which of the loaded lots to pair with - pick one you have "
                  "opened with the button on this card. The path is not "
                  "stored in the recipe, so the same recipe runs on the next "
                  "lot.")),
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
            name="carry", type="multi_choice", default="",
            label="Carry these columns",
            choices_from="source_columns",
            help=("KLARF columns from the matched defect to bring over as "
                  "features (for example DEFECTID, ROUGHBINNUMBER). The list "
                  "is what that lot actually has. This is what makes \"it was "
                  "detected but scored too low\" answerable.")),
        ParamSpec(
            name="rank_within", type="multi_choice", default="",
            label="Rank within",
            choices_from="source_columns",
            help=("Columns that say which defects to rank against each other "
                  "- pick XINDEX and YINDEX to rank inside each die. Leave it "
                  "empty to rank the whole lot as one group.")),
        ParamSpec(
            name="rank_by", type="str", default="",
            label="Rank by",
            choices_from="source_columns",
            help=("Rank every defect in that whole lot by this column - the "
                  "other tool's own score, usually. This is how \"it was "
                  "detected, but it ranked too low to be sampled\" becomes a "
                  "number: the rank comes from that lot's full defect list, "
                  "not from the few defects in this run. Leave it empty and "
                  "no rank is worked out.")),
        ParamSpec(
            name="rank_desc", type="bool", default=True,
            label="Highest first",
            # ⚠ 沒有 `show_when`：它比的是「值在不在這幾個之中」，而
            # 「Rank by 有沒有填」不是一組固定的值（那一格是欄位名）。
            # 這一格在沒排名的時候不影響任何結果（見 `_rank_key`）。
            help=("On: the biggest value is rank 1 - right for a score. Off: "
                  "the smallest is rank 1, for a column that already counts "
                  "up from the best one.")),
        ParamSpec(
            name="channel", type="str", default="",
            label="Which image",
            choices_from="source_images",
            help=("Which of the matched defect's images to bring in - it has "
                  "one name per image the tool took (a lot with one image per "
                  "defect has just one). Leave empty for its first one.")),
        ParamSpec(
            name="out", type="image_key", direction="out", default="paired",
            label="Name this image",
            help="Name of the image stream this card produces."),
        nm_per_px_spec(),
    ]
    reads: List[str] = []
    writes = ["paired"]
    features_out = ["pair_found", "match_dist_nm", "match_ambiguous"]

    @classmethod
    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
        name = str(params.get("out", "paired") or "").strip()
        return [name] if name else []

    @classmethod
    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
        out = list(cls.features_out)
        out += ["pair_%s" % c for c in _carry_names(params)]
        if _rank_by(params):
            # 沒填「Rank by」就**一格都不宣告** —— 宣告了而永遠不寫的話，
            # CSV 上會多出兩欄空的，而空欄跟「這一顆算不出來」講的是同一句話。
            out += ["pair_die_rank", "pair_die_total"]
        return out

    @classmethod
    def legacy_feature_renames(cls, params: Dict[str, Any]) -> Dict[str, str]:
        """``paired`` → ``pair_found``（F33，2026-08-25）。

        **特徵名與影像流名共用一個字是個坑**：這張卡的 `out` 預設就叫
        ``paired``，於是「有沒有配到」那個數字跟那條流在畫面上、在表達式裡
        長得一樣。流名不動（它是畫布上的接線身分，改了等於剪掉所有人的線），
        改的是特徵 —— 而 `pair_found` 順帶跟 `pair_<欄位>` 排成同一家族。

        給 `recipe._compare_feature_renames` 收（那一支對每一張卡問這件事）。
        右邊的名字不在左邊 → 第二次跑是 no-op，`to_json_dict → from_json_dict`
        仍然是 identity（鐵則 9）。
        """
        return {"paired": "pair_found"}

    @classmethod
    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
        if not str(params.get("source", "") or "").strip():
            return ["This card has no second lot yet. Use “Open data…” on this "
                    "card - the name you give it is what “Source name” holds."]
        if _rank_within(params) and not _rank_by(params):
            return ["“Rank within” says which defects to rank against each "
                    "other, but “Rank by” is empty - pick the column that "
                    "orders them (the other tool's score, usually)."]
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
        out_key = str(p["out"]).strip() or "paired"
        # **每一顆都有這個數字**，配到與否都一樣 —— 「沒配到」本身就是
        # characterization 的結論之一，它不可以只是一個缺席的欄位。
        ctx.add_feature("pair_found", 1.0 if hit is not None else 0.0)
        if hit is None:
            # 配不到 → 不吐流、其餘 pair_* 一格都不寫，**但這一顆繼續走**
            # （見模組說明）。`out` 也記進 meta：下游要靠它分辨「上游沒配到」
            # 與「這條線根本接錯了」。
            ctx.meta["pair_match"] = {
                "source": sid,
                "defect_id": "",
                "index": -1,
                "dist_nm": float("nan"),
                "candidates": int(p["candidates"]),
                "out": out_key,
            }
            ctx.warn(
                "[%s] no defect in '%s' is within %.0f nm of this one - "
                "recorded as pair_found = 0. The compare cards downstream let "
                "this defect through, and it still reaches the decision: "
                "\"the other lot never saw it\" is one of the answers."
                % (self.key, sid, float(p["tol_nm"])))
            return ctx

        ctx.add_feature("match_dist_nm", float(dist))
        ctx.add_feature("match_ambiguous", 1.0 if ambiguous else 0.0)

        # 排名：母體是**那一份的完整 defect list**（幾千筆），不是這一批跑過
        # pipeline 的那幾十顆。判定段的「跟整批比」答的是另一個問題 ——
        # 「這顆在我挑出來看的 30 顆裡排第幾」對 sample 門檻沒有意義。
        rank_key = _rank_key(p)
        if rank_key is not None:
            _ensure_ranks(others, rank_key, sid, self.key)
            rank, total = getattr(hit, "_d4t_rank", {})[rank_key]
            ctx.add_feature("pair_die_rank", float(rank))
            # **「第 7 名」在 10 筆裡跟在 3000 筆裡是兩件事**，而 rank 那一格
            # 看起來一模一樣。
            ctx.add_feature("pair_die_total", float(total))

        fields = dict(getattr(hit, "fields", None) or {})
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
            "defect_id": str(getattr(hit, "defect_id", "")),
            "index": int(getattr(hit, "index", -1)),
            "dist_nm": float(dist),
            "candidates": int(p["candidates"]),
            "out": out_key,
        }
        # **打錯一個欄位名不可以安靜地沒事**：這張卡的存在理由就是把那幾欄帶
        # 過來（「偵測到但分數太低」只有靠它答得出來），少了一欄的 CSV 跟成功
        # 的 CSV 長得一模一樣。擋在這裡＝這幾顆 ok=False 而整批照跑（鐵則 7）。
        missing = [c for c in _carry_names(p) if c not in fields]
        if missing:
            # **列的是「帶過來的是哪幾欄」，不是「那一份有哪幾欄」**：卡片手上
            # 只有複製過去的那幾欄（第二份的 KlarfDoc 刻意不進 worker）。
            # 「那一份有哪些欄」由掛的那一刻回答 —— 那時候 doc 還在手上，
            # 而使用者正看著那張卡（`ingest/pair_source.missing_columns`）。
            raise StepError(
                self.key,
                "nothing carried over from '%s' for %s. What did come over: "
                "%s. Fix “Carry these columns” - that lot has no such column."
                % (sid, ", ".join(missing),
                   ", ".join(sorted(fields)) or "(nothing)"))

        ctx.set_image(out_key, self._image_of(hit, p["channel"]))
        # **第二份的像素大小掛在它自己那條流上**（2026-08-20）：兩台機台不一樣，
        # 而那正是 `align_to` 要縮放才對得起來的原因。
        ctx.set_stream_nm_per_px(out_key, p.get("nm_per_px"))
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

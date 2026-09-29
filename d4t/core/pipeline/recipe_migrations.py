# d4t pipeline engine — recipe 的遷移（2026-09-24 從 recipe.py 拆出）.
"""舊 recipe 變成新形狀的**每一道遷移**，與它們共用的改名工具。

⚠ **呼叫順序不在這裡**，在 :meth:`recipe.Recipe.from_json_dict` —— 那裡的註解
講了哪幾道之間的先後是要緊的。這一支只放「每一道自己怎麼做」。

鐵則 9：遷移只能靠「舊東西在不在」判斷，不能靠「新東西不在」
（`to_json_dict → from_json_dict` 必須是 identity，不然 workers=1 與 2 算得不一樣）。
"""
from __future__ import annotations

import os
import re
from dataclasses import replace
from typing import Any, Dict, List, Optional, Tuple, Type

from d4t.core.log import swallowed

from . import chart_style
from .recipe_schema import (
    RECIPE_VERSION,
    DecideSpec,
    Edge,
    RecipeNode,
    ScoreSpec,
    TreeLeaf,
    TreeStep,
    _as_int,
    _cycles_with,
    _region_producer,
)
from .step import (
    FEATURE_TYPES,
    IMAGE_TYPES,
    REGISTRY,
    SINGLE_IMAGE_KINDS,
    Step,
)


def describe_migration(raw: Any, recipe: Any) -> List[str]:
    """載入一份舊 recipe 的時候，**畫布上多了什麼／換了什麼**，講成人話。

    為什麼需要它（U17，2026-09-08）
    ------------------------------
    舊版 recipe 開起來會靜默升級 —— 補區域線（F42）、拆載入卡（F11 Input-4）、
    換掉改過名的卡。畫布上因此多了東西，而**沒有任何一句話說明**；接著存檔
    就寫成新格式。這是「畫布不說謊」唯一還沒守到的角落：畫面是對的，但使用者
    不知道它為什麼跟他上次存的不一樣，而他手上那份檔案已經被改寫了。

    為什麼是「比對前後」而不是讓每一道遷移自己回報
    ----------------------------------------------
    有 19 道 ``_migrate_*``，而讓每一道多回一個「我做了什麼」是 19 個要維護
    的字串 —— 而且**第 20 道一定會忘**（這個 repo 的 `ALLOWED_ERRORS` 學到的
    同一課：靠人記得的東西會漂）。原始 dict 與載好的 `Recipe` 兩邊都在手上，
    差在哪裡是**算得出來**的，所以新加一道遷移不必改這裡。

    代價講明：它說得出「多了 2 條線」，說不出「那是 F42 那一道補的」。對使用者
    來說前者才是他要知道的事 —— 後者是我們的事。

    回一串句子（空的 = 什麼都沒變，那時候不要講話）。
    """
    says: List[str] = []
    if not isinstance(raw, dict):
        return says
    try:
        old_version = _as_int(raw.get("version", 1), "recipe 'version'")
    except Exception:  # 只是一句提示，不准擋載入
        return says

    # 補線、拆出新卡 —— 那幾道遷移都掛在版本閘底下，所以只問舊版本的檔案
    # （目前版本的檔案沒被那幾道碰過，不該講話）。
    raw_nodes = raw.get("nodes") or {}
    if old_version < RECIPE_VERSION:
        raw_edges = raw.get("edges") or []
        added = len(getattr(recipe, "edges", []) or []) - len(raw_edges)
        if added > 0:
            says.append("added %d wire%s" % (added, "" if added == 1 else "s"))
        if isinstance(raw_nodes, dict):
            extra = len(getattr(recipe, "nodes", {}) or {}) - len(raw_nodes)
            if extra > 0:
                says.append("split %d card%s"
                            % (extra, "" if extra == 1 else "s"))

    # **換卡不看版本號**（F121 期 2，2026-09-24）：有幾道換卡看的是「舊東西在
    # 不在」（`load_single` → Input），對**目前版本**的檔案一樣會動手 —— 以前
    # 這裡整段被「目前版本就不用講」擋掉，那幾次升級因此是安靜的。比對前後對
    # 沒被換過的卡講不出任何一句話，所以不會多出雜訊。
    if isinstance(raw_nodes, dict):
        became: Dict[str, str] = {}
        for nid, node in (getattr(recipe, "nodes", {}) or {}).items():
            old = str((raw_nodes.get(nid) or {}).get("step", "")) \
                if isinstance(raw_nodes.get(nid), dict) else ""
            new = str(getattr(node, "step", "") or "")
            if old and new and old != new:
                became.setdefault(old, new)
        if became:
            says.append("renamed %s" % ", ".join(
                "“%s” → “%s”" % (_card_word(old), _card_word(new))
                for old, new in sorted(became.items())))
    return says


#: 已經不在卡片庫裡、但舊檔案還寫著的卡 → 使用者當時在畫面上看到的名字。
#: 升級的那一句話要講**他認得的字**（「SEM image」），不是 recipe 的鍵。
_RETIRED_CARD_LABELS = {
    "load_single": "SEM image",     # F121 期 2 併進 Input（`load_patch`）
}


def _card_word(key: str) -> str:
    """一張卡在升級提示裡叫什麼：卡片庫裡有就用它的 label，退役的查上表，
    都沒有就原樣（認不得的 key 本身就是線索，不要猜一個漂亮的名字）。"""
    cls = REGISTRY.get(key)
    if cls is not None:
        return str(getattr(cls, "label", "") or key)
    return _RETIRED_CARD_LABELS.get(key, key)


def _migrate_region_params_into_edges(
        nodes: Dict[str, "RecipeNode"], routes: Dict[str, List[str]],
        edges: List["Edge"],
        registry: Optional[Dict[str, Type[Step]]] = None) -> None:
    """v1（區域存在**參數**裡）→ v2（存在**線**裡）。F42 B3，2026-08-27。

    判準是**版本號**（``version < RECIPE_VERSION``），不是「有參數但沒有線」
    —— 後者是鐵則 9 明文禁止的「靠新東西不在判斷」，而這個 repo 為它付過一次
    ``workers=1`` 與 ``workers=2`` 算出不同分數的錢。

    補線的來源用 :func:`_region_producer`（＝ UI 的 ``region_producer``，
    「上游最後一個」；B0 之後「最後一個」＝「唯一一個」）。三種情形：

    ① **上游找得到** —— 補一條線，畫布跟以前長得一樣。

    ② **指到一個沒有人產出的名字** —— 不補線，而且**那個字留著**。
       壞的 recipe 遷移完仍然要壞，訊息也不准變差：留著它，
       `unknown-region` 才問得到；清掉的話 `glv_stats` 的空 ``roi`` 是完全
       合法的「量整張圖」，症狀會從一句紅字變成安靜地算錯。

    ③ **產出它的那張卡排在下游** —— **補線**。這是一個**刻意的行為改變**：
       補完之後 `execution_order` 會把 Region 卡排到前面，於是一份原本
       「量測卡先跑、安靜地量整張圖」的 recipe 開始算對的數字。
       那正是這一輪存在的理由（見 `docs/history/plans/F42-region-edges-plan-b.md` §1）。

    ④ **補上去會成環** —— 不補（見 :func:`_cycles_with`），而且由
       `validate` 的 `region-has-no-line` 講出來。一份今天跑得動的 recipe
       不可以因為遷移而打不開。

    **不做「順手接線」**：只補參數已經指名的那幾條。使用者從來沒有表達過的
    連線，遷移沒有資格代他畫（鐵則 10）。
    """
    if registry is None:
        registry = REGISTRY
    have = {(e.dst, e.dst_in, e.src_out) for e in edges}
    for _kind, route in routes.items():
        route = list(route)
        in_route = set(route)
        for i, nid in enumerate(route):
            node = nodes.get(nid)
            if node is None:
                continue
            step_cls = registry.get(node.step)
            if step_cls is None:
                continue
            try:
                params = step_cls.validate_params(node.params)
            except Exception:  # 壞參數交給 validate
                params = dict(node.params)
            for spec in step_cls.region_input_specs():
                raw = str(params.get(spec.name, "") or "")
                for name in [x.strip() for x in raw.split(",") if x.strip()]:
                    if (nid, spec.name, name) in have:
                        continue           # 已經有線了（跑第二次是 no-op）
                    src = _region_producer(name, route, i, nodes, registry)
                    if not src or src == nid or src not in in_route:
                        continue           # ② 沒有人產出它 —— 那個字留著
                    new = Edge(src=src, dst=nid, src_out=name,
                               dst_in=spec.name)
                    if _cycles_with(edges, new, in_route):
                        continue           # ④ 補上去會成環
                    edges.append(new)
                    have.add((nid, spec.name, name))


# ---------------------------------------------------------------------------
# 舊 recipe 相容遷移（F7-18）：``also_apply`` → 一張卡一條流
# ---------------------------------------------------------------------------
#: 哪些卡片以前有 ``also_apply``，以及它們的主要影像流參數叫什麼。
_ALSO_APPLY_CARDS: Dict[str, str] = {
    "percentile_norm": "source",
    "glv_mask_norm": "source",
    "denoise": "target",
    "flatten": "target",
    "local_contrast": "target",
    "brightness_contrast": "target",
    "gamma": "target",
}

#: 這兩張卡另外還有 ``anchor``：``source`` = 其他流借主流量出來的拉伸範圍。
#: 那個能力現在叫 ``range_from``（一條影像流的名字），所以遷移得動兩個參數。
_ANCHOR_CARDS = ("percentile_norm", "glv_mask_norm")


def _fresh_id(taken: Dict[str, Any], base: str) -> str:
    nid = base
    i = 2
    while nid in taken:
        nid = "%s_%d" % (base, i)
        i += 1
    return nid


def _migrate_also_apply(nodes: Dict[str, "RecipeNode"],
                        routes: Dict[str, List[str]]) -> None:
    """把 ``also_apply`` 展開成一張卡一條流（就地改寫 nodes 與 routes）。

    為什麼要遷移而不是直接不認得
    ----------------------------
    ``also_apply`` 是使用者存在磁碟上的 recipe 裡的字，而 recipe 是拿來交接的
    東西。認不得它會讓一份跑得好好的檔案在升級之後變成 ``unknown parameters``
    —— 對不會寫 code 的人那就是「工具壞了」。

    為什麼順序看 ``anchor``
    -----------------------
    ``anchor="source"`` 的語意是「ref 用 **test 原本的** 灰階範圍」。拆成兩張卡
    之後，如果 test 那張先跑，它會把 test 拉成 0–255，ref 那張再去借就借到
    「拉伸後」的範圍 —— 數字不一樣，而畫面上兩者都是一張看起來正常的圖。
    所以 ``anchor="source"`` 時把借範圍的那幾張排在**前面**，此時主流還沒被改過，
    輸出與舊版逐位元組相同。``anchor="self"`` 沒有這個相依，維持原順序。
    """
    extra: Dict[str, tuple] = {}          # 原節點 id -> (新節點 ids, 要不要排前面)
    for nid, node in list(nodes.items()):
        primary_name = _ALSO_APPLY_CARDS.get(node.step)
        if primary_name is None:
            continue
        params = dict(node.params)
        if "also_apply" not in params and "anchor" not in params:
            continue
        also_raw = params.pop("also_apply", "")
        anchor = params.pop("anchor", None)
        primary = str(params.get(primary_name, "") or "")
        also: List[str] = []
        for tok in str(also_raw or "").split(","):
            tok = tok.strip()
            if tok and tok != primary and tok not in also:
                also.append(tok)
        borrow = node.step in _ANCHOR_CARDS and str(anchor or "source") == "source"
        if node.step in _ANCHOR_CARDS:
            params.setdefault("range_from", "")
        node.params = params

        made: List[str] = []
        for stream in also:
            new_id = _fresh_id(nodes, "%s_%s" % (nid, stream))
            p = dict(params)
            p[primary_name] = stream
            if node.step in _ANCHOR_CARDS:
                p["range_from"] = primary if borrow else ""
            nodes[new_id] = RecipeNode(id=new_id, step=node.step, params=p,
                                       enabled=node.enabled)
            made.append(new_id)
        if made:
            extra[nid] = (made, borrow)

    if not extra:
        return
    for k, route in list(routes.items()):
        out: List[str] = []
        for nid in route:
            made, first = extra.get(nid, ([], False))
            if first:
                out.extend(made)
                out.append(nid)
            else:
                out.append(nid)
                out.extend(made)
        routes[k] = out


# ---------------------------------------------------------------------------
# 舊 recipe 相容遷移（F7-20）：合併卡片 + 主流參數改名 streams
# ---------------------------------------------------------------------------
#: 舊 step key → (新 key, 主流參數的舊名, 要補上的固定參數, 參數改名表)
#:
#: 四張 Normalize 卡與三張 tone 卡在 F7-20 各自併成一張，方法變成一個下拉。
#: 遷移要做的事有三件：換 key、把主流參數改名成 ``streams``、把「是哪一張卡」
#: 這個資訊變成 ``method`` 的值。
#:
#: 為什麼要遷移而不是直接不認得：跟 §22.6 同一個理由 —— recipe 是使用者存在
#: 磁碟上、拿來交接的檔案，認不得等於「工具壞了」。
_MERGED_CARDS: Dict[str, tuple] = {
    # 舊 key:          (新 key,      主流舊名,    固定參數,                   改名表)
    "percentile_norm": ("normalize", "source", {"method": "percentile"}, {}),
    "glv_mask_norm":   ("normalize", "source", {"method": "glv_band"}, {}),
    "local_contrast":  ("normalize", "target", {"method": "local"}, {}),
    # hist_match 的舊 ``method``（exact/linear/percentile）跟合併後的方法選擇
    # 撞名，所以改叫 match_method。
    "hist_match":      ("normalize", "moving", {"method": "match"},
                        {"method": "match_method"}),
    "brightness_contrast": ("tone", "target", {}, {}),
    "gamma":               ("tone", "target", {}, {}),
    "invert":              ("tone", "target", {"invert": True}, {}),
}

#: 沒有合併、但主流參數一起改名成 ``streams`` 的卡（F7-19）。
_RENAMED_STREAM_PARAM: Dict[str, str] = {
    "denoise": "target",
    "flatten": "target",
}


#: 改過名的**參數值**：``(step, param) -> {舊值: 新值}``。
#:
#: F8 第一版的 ``roi_cross`` 只有兩層灰階，所以「要哪一組」是 ``dark`` /
#: ``bright``。實際的 layout 常常三層以上（站點回報 MG 約 220、EPI 約 180），
#: 二分法把那兩層併在一起，於是規則改成排名。舊檔案的兩個值仍然說得通
#: —— 它們就是排名的兩端。
#:
#: 為什麼是遷移而不是把舊值留在 choices 裡：留著的話下拉選單會有兩個意思一樣
#: 的選項，而使用者不知道該挑哪個。**相容性是檔案格式的事，不是 UI 的事。**
_RENAMED_VALUES: Dict[Tuple[str, str], Dict[str, str]] = {
    ("roi_cross", "vertical_select"): {"dark": "darkest", "bright": "brightest"},
    ("roi_cross", "horizontal_select"): {"dark": "darkest", "bright": "brightest"},
}


def _migrate_renamed_values(nodes: Dict[str, "RecipeNode"]) -> None:
    """把改過名的參數**值**換成新的（就地改寫 nodes）。"""
    for nid, node in list(nodes.items()):
        params = dict(node.params)
        touched = False
        for (step, name), mapping in _RENAMED_VALUES.items():
            if node.step != step or name not in params:
                continue
            new = mapping.get(str(params[name]))
            if new is not None:
                params[name] = new
                touched = True
        if touched:
            nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                    enabled=node.enabled)


def _migrate_template_regions(nodes: Dict[str, "RecipeNode"]) -> None:
    """``roi_template`` 的一框一區域 → ``regions`` 字串（F11 Region-1）。

    舊的：``roi_out="epi"`` ＋ ``roi_x/y/w/h`` 四個數字（一張卡只框得出一個矩形）。
    新的：``regions="epi: 0.35,0,0.2,1"``（一張卡好幾個區域，每個好幾個矩形）。

    ⚠ 判準是**舊東西在不在**（``roi_out`` 有沒有出現），不是「新東西不在」
    （鐵則 9）。後者分不出「舊檔案靠舊預設」與「新 recipe 的區域剛好還沒標」
    —— 而 ``to_json_dict → from_json_dict`` 是 ``run_batch`` 送 recipe 進 worker
    的路，它一旦不是 identity，``workers=1`` 與 ``workers=2`` 就會算出不同的分數。

    四個座標**沒有**預設值可以靠：舊卡的預設是整格（0,0,1,1），所以缺哪一個就
    補那一個的舊預設，結果與舊版逐位元組相同。
    """
    from .cellrois import format_cell_rois

    old_defaults = {"roi_x": 0.0, "roi_y": 0.0, "roi_w": 1.0, "roi_h": 1.0}
    for nid, node in list(nodes.items()):
        if node.step != "roi_template" or "roi_out" not in node.params:
            continue
        params = dict(node.params)
        name = str(params.pop("roi_out", "") or "").strip()
        box = tuple(float(params.pop(k, d) or 0.0)
                    for k, d in old_defaults.items())
        for k in old_defaults:
            params.pop(k, None)
        if name and box[2] > 0.0 and box[3] > 0.0:
            params["regions"] = format_cell_rois([(name, [box])])
        nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                enabled=node.enabled)


#: 單張影像的 route（一顆一張圖）—— 這幾條上的 `load_patch` 要換成 `load_single`。
#: PR-2 起定義搬到 `step.SINGLE_IMAGE_KINDS`（`Step.kind_issues` 的判準要
#: 從卡片那邊 import 得到，而卡片不 import recipe）；這裡留舊名給遷移用。
_SINGLE_IMAGE_KINDS = SINGLE_IMAGE_KINDS


def _migrate_split_load_cards(nodes: Dict[str, "RecipeNode"],
                              routes: Dict[str, List[str]],
                              version: Any = 1) -> None:
    """單張影像那條 route 上的 ``load_patch`` → ``load_single``（F11 Input-4）。

    為什麼需要這一道
    ----------------
    Input 卡拆成兩張之前，``load_patch`` 服務四種資料型別，而它對單張資料的做法是
    「載 ``single`` 並**順手鏡射一份到 `test`**」。舊 recipe 的 rsem route 就是靠
    那個鏡射活著的（`golden_cell` 讀 `test`）。拆卡之後鏡射沒了，所以這裡把它換成
    ``load_single`` 並把輸出名設成 ``test`` —— **行為逐項相同**（下游本來就只用
    `test`；沒有人用過那條多出來的 `single`），黃金值因此不動。

    判準是「**舊東西在不在**」（鐵則 9）：這條 route 的 kind 是單張影像的那幾種，
    而它上面有一張 ``load_patch``。不是靠「新東西不在」—— 那分不出「舊檔案」與
    「新 recipe 剛好沒填」。

    ⚠ **F121 期 2（2026-09-24）起這一道只對第 1 版的檔案跑**（``version``）。
    `load_single` 併回 `load_patch`（「Input」）之後，「單張 route 上有一張
    `load_patch`」變成**新檔案的正常樣子** —— 那個「舊東西」不再只屬於舊檔案，
    再照它判斷的話，每一次 `to_json_dict → from_json_dict` 都會把 Input 卡換成
    `load_single(out="test")`、再被下一道換回 `load_patch("1:test")`，名字表從
    `1:single` 變成 `1:test`，下游的線全斷（鐵則 9 的形狀）。拆卡（F11，08-17）
    早於第 2 版（F42 B3，08-27），所以第 2 版以上的檔案一定已經拆過了。

    ⚠ **兩條 route 可以共用同一個節點**，而 v1 的雙輸入 recipe 正是那樣寫的
    （``dual_route_basic.json`` 的 ebi_patch 與 rsem 共用九個節點裡的八個，
    包含那張 load 卡）。就地換掉共用的那一張會**把另一條 route 弄壞** ——
    第一版這樣寫，黃金值當場抓到（patch 那 8 顆全部 ok=False：「這張卡只載一張圖，
    但這顆有 2 張」）。所以共用的情況要**多開一個節點**給單張那條 route 用，
    而不是改掉大家的那一張。
    """
    if _as_int(version, "recipe 'version'") >= 2:
        return
    single = [k for k in routes if str(k) in _SINGLE_IMAGE_KINDS]
    if not single:
        return
    shared_with_others = set()
    for kind, order in routes.items():
        if str(kind) not in _SINGLE_IMAGE_KINDS:
            shared_with_others.update(order)

    for kind in single:
        order = routes[kind]
        for i, nid in enumerate(list(order)):
            node = nodes.get(nid)
            if node is None or node.step != "load_patch":
                continue
            if nid in shared_with_others:
                # 共用 → 這條 route 換成自己的一張新卡（別條 route 不受影響）
                new_id = nid + "_single"
                n = 2
                while new_id in nodes:
                    new_id, n = "%s_single%d" % (nid, n), n + 1
                nodes[new_id] = RecipeNode(id=new_id, step="load_single",
                                           params={"out": "test"},
                                           enabled=node.enabled)
                order[i] = new_id
            else:
                nodes[nid] = RecipeNode(id=node.id, step="load_single",
                                        params={"out": "test"},
                                        enabled=node.enabled)


def _migrate_decision_into_a_card(nodes: Dict[str, "RecipeNode"],
                                  routes: Dict[str, List[str]],
                                  decide: Optional["DecideSpec"],
                                  score: "ScoreSpec") -> None:
    """有判定的舊檔案 → 畫布上補一張 Decision 卡（F123 期 1）。

    **只對第 5 版以前的檔案**（`Recipe.from_json_dict` 的版本閘；鐵則 9：第 6 版
    起「有判定就有那張卡」是存檔時就成立的事，所以不能拿「卡不在」當判準 ——
    一份手寫的新 recipe 刻意沒有那張卡，不該被補）。

    有判定＝有 ``decide``，或舊的分數門檻（`recipe_schema.legacy_decision` 會把它
    變成一題樹）。卡排在每一條 route 上**第一張 Output 卡的前面**：沒有線的卡照
    route 的排列跑、也照它排版，而判定在量測之後、Output 之前。卡沒有參數，判定
    的內容照舊住在 ``decide`` —— 所以引擎算出來的數字一個都不變。
    """
    if decide is None and not str(getattr(score, "expr", "") or "").strip():
        return
    if any(n.step == "decision" for n in nodes.values()):
        return
    nid = _fresh_id(nodes, "decision")
    nodes[nid] = RecipeNode(id=nid, step="decision", params={})
    for key, order in routes.items():
        at = next((i for i, x in enumerate(order)
                   if x in nodes and getattr(REGISTRY.get(nodes[x].step),
                                             "scale", "") == "lot"),
                  len(order))
        routes[key] = list(order[:at]) + [nid] + list(order[at:])


def _migrate_single_into_input(nodes: Dict[str, "RecipeNode"]) -> None:
    """``load_single``「SEM image」→ ``load_patch``「Input」（F121 期 2）。

    使用者 2026-09-24 同意把兩張 Input 卡合回一張（「入口簡單化」）。
    `load_single(out="x")` 與 `load_patch(channel_map="1:x")` 在一顆一張的資料上
    像素與特徵逐一相同（實測），所以換卡**不動節點 id、不動流名**：
    ``recipe.edges`` 上的埠名照樣對得上，一條線都不用改。其餘參數
    （``nm_per_px`` / ``carry`` / ``only_*``）兩張卡同名同義，原樣帶過去。

    判準是「**舊東西在不在**」（鐵則 9）：節點的 step 是 ``load_single`` 就換。
    換完之後不再有 ``load_single``，所以跑第二次是 no-op。
    ⚠ **排在 :func:`_migrate_split_load_cards` 之後**：那一道（只對第 1 版）會
    產出 ``load_single``，而這一道要把它接著換掉 —— 遷移鏈一段一段接。
    """
    for nid, node in list(nodes.items()):
        if node.step != "load_single":
            continue
        params = dict(node.params)
        # 空的 ``out`` 在 `load_single` 上是「一條流都不吐」—— 那張卡本來就跑不動，
        # 換成預設名是讓畫布上至少有一顆埠可以接，而不是造出一張沒有埠的卡。
        out = str(params.pop("out", "single") or "").strip() or "single"
        params["channel_map"] = "1:%s" % out
        nodes[nid] = RecipeNode(id=node.id, step="load_patch", params=params,
                                enabled=node.enabled)


def _migrate_merged_cards(nodes: Dict[str, "RecipeNode"]) -> None:
    """把 F7-20 之前的卡片名與參數名換成合併後的（就地改寫 nodes）。

    ⚠ 這一道**必須跑在 :func:`_migrate_also_apply` 之後**：那一道會把
    ``also_apply`` 展開成好幾張**舊 key** 的卡，展開出來的那幾張也要一起換名。
    先展開再收合看起來繞了一圈，但遷移鏈要一段一段接 —— 寫一條
    「``also_apply`` 直接變 ``streams``」的捷徑只有舊檔案會走到，
    永遠不會有人在上面測試。
    """
    for nid, node in list(nodes.items()):
        params = dict(node.params)
        merged = _MERGED_CARDS.get(node.step)
        if merged is not None:
            new_key, primary_name, fixed, renames = merged
            for old, new in renames.items():
                if old in params:
                    params[new] = params.pop(old)
            if primary_name in params:
                params["streams"] = params.pop(primary_name)
            for k, v in fixed.items():
                params.setdefault(k, v)
            nodes[nid] = RecipeNode(id=node.id, step=new_key, params=params,
                                    enabled=node.enabled)
            continue
        primary_name = _RENAMED_STREAM_PARAM.get(node.step)
        if primary_name is not None and primary_name in params:
            params["streams"] = params.pop(primary_name)
            nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                    enabled=node.enabled)


#: 只是**改了名字**的卡（key → 新 key，參數名一個都沒動）。
#:
#: 目前只有一筆：``golden_cell`` →「Reference from pattern」
#: （2026-08-18）。改名的理由是使用者的一句話 ——「那可能要拿回來 不過要改名字
#: 不然會誤會」：Template 卡的設定對話框裡也在疊 golden cell，畫面上兩個地方
#: 同名，看起來像同一個功能做了兩次。
#:
#: 判準照鐵則 9 是「**舊東西在不在**」：node 的 step 是舊 key 就換。不看新 key
#: 在不在 —— 那分不出「舊檔案」與「新 recipe 剛好長這樣」。
#:
#: ⚠ **feature 名也換了**（``golden_ghost`` / ``golden_px`` / ``golden_py`` →
#: ``ref_sharpness`` / ``ref_px`` / ``ref_py``），而分數表達式裡可能寫著舊名字。
#: 那一段由 :func:`_migrate_renamed_features` 處理，兩件事要一起做才完整。
_RENAMED_CARDS = {
    "golden_cell": "pattern_ref",
}

#: 跟著 :data:`_RENAMED_CARDS` 一起改名的 feature（舊名 → 新名）。
_RENAMED_FEATURES = {
    "golden_ghost": "ref_sharpness",
    "golden_px": "ref_px",
    "golden_py": "ref_py",
}


def _migrate_renamed_cards(nodes: Dict[str, "RecipeNode"]) -> None:
    """只改了 key 的卡（參數原封不動）。"""
    for nid, node in list(nodes.items()):
        new_key = _RENAMED_CARDS.get(node.step)
        if new_key is None:
            continue
        nodes[nid] = RecipeNode(id=node.id, step=new_key,
                                params=dict(node.params),
                                enabled=node.enabled)


def _migrate_chart_params_into_look(nodes: Dict[str, "RecipeNode"]) -> None:
    """`output_uniformity` 的五格外觀折進一格 ``look``（F87，2026-09-07）。

    ``value_name`` / ``value_lo`` / ``value_hi`` / ``points`` / ``bins`` /
    ``percent`` 六格變成一格 ``chart_style``。理由見
    `pipeline/chart_style.py` 的檔頭：使用者要 PEAR 那種 chart settings，
    而攤成 ParamSpec 是二十五列。

    **不遷移的話舊檔案打不開**：`validate_params` 對認不得的 key 是
    ``unknown parameters`` 的硬錯，而那句話的意思是「這份檔案壞了」——
    真正的情況是「這一格搬家了」。

    判準是**「舊東西在不在」**（鐵則 9）：那幾格在就折進去，不在就什麼都
    不做。所以跑第二次是 no-op，``to_json_dict → from_json_dict`` 仍然是
    identity —— 那是 ``run_batch`` 送 recipe 進 worker 的路。

    ⚠ **鎖定那一組要把「規則」翻成「開關」**：舊的約定是「上界高過下界才算
    鎖住」，而新的有一顆明著的 ``lock``。翻錯的話一份本來鎖著的 recipe 會
    安靜地變成 auto —— 兩張圖擺在一起，一樣高的柱子其實不一樣高。
    """
    moved = ("value_name", "value_lo", "value_hi", "points", "bins", "percent")
    for node in nodes.values():
        if node.step != "output_uniformity":
            continue
        if not any(k in node.params for k in moved):
            continue
        style: Dict[str, Any] = {}
        try:
            style.update(chart_style.parse_style(node.params.get("look", "")))
        except Exception:  # 遷移不准當機
            style = {}
        lo = node.params.pop("value_lo", None)
        hi = node.params.pop("value_hi", None)
        if lo is not None and hi is not None:
            try:
                lo_f, hi_f = float(lo), float(hi)
            except (TypeError, ValueError):
                lo_f = hi_f = 0.0
            if hi_f > lo_f:            # 舊的「算不算鎖住」就是這一條
                style.update({"lock": True, "lo": lo_f, "hi": hi_f})
        for old, new in (("value_name", "value_name"), ("points", "points"),
                         ("bins", "bins"), ("percent", "percent")):
            if old in node.params:
                style[new] = node.params.pop(old)
        try:
            node.params["look"] = chart_style.format_style(style)
        except Exception:  # 同上
            node.params["look"] = ""


def _migrate_drop_use_within(nodes: Dict[str, "RecipeNode"]) -> None:
    """``normalize`` 的 ``use_within`` 那一格拿掉（2026-09-02）。

    產得出 mask 影像流的那張卡（``roi_mask``「Mask from regions」）刪了，所以
    這一格再也接不到東西 —— 而它是 ``image_key``，設定區唯讀、只能靠拉線填。

    **不拿掉的話舊檔案打不開**：``validate_params`` 對認不得的 key 是
    ``unknown parameters`` 的硬錯，而那句話的意思是「這份檔案壞了」——
    真正的情況是「這一格不存在了」（同 :data:`Recipe.app_version` 那一段）。

    判準是**「舊東西在不在」**（鐵則 9）：這一格在就拿掉，不在就什麼都不做。
    所以它跑第二次是 no-op，``to_json_dict → from_json_dict`` 仍然是 identity
    —— 那是 ``run_batch`` 送 recipe 進 worker 的路。

    ⚠ **值不是空字串的那些不必額外處理**：那種 recipe 必然還有一個
    ``roi_mask`` 節點（沒有別的卡產得出那條流），而它開起來是一條
    ``unknown-step``。跑不起來的 recipe 沒有必要幫它接線（同
    :func:`_migrate_rescued_feature_names` 裡那段 ``feature_math`` 的說明）。
    """
    for node in nodes.values():
        if node.step == "normalize" and "use_within" in node.params:
            node.params.pop("use_within", None)


def _migrate_roi_from_mask_into_roi_reference(nodes: Dict[str, "RecipeNode"]
                                             ) -> None:
    """``roi_from_mask`` → ``roi_reference`` + ``method="layout layers"``（F29）。

    使用者 2026-08-25：「golden cell 跟 GDS 同樣重要而且他們要能在同張 card 裡
    （都是接區域 ROI 卡）」。兩支回答的是同一句話（「哪些地方應該長得一樣」），
    所以是一張卡的兩個 method —— 跟 ``roi_compare`` → ``glv_stats`` 一模一樣的
    形狀，連遷移的寫法都照抄（見 :func:`_migrate_roi_compare_into_glv_stats`）。

    這一次 key 真的換掉（不像那一次留了 ``glv_stats``），理由是**沒有黃金值
    指著它**：``tests/fixtures/golden/`` 三份 recipe 用到的是
    ``load_patch / normalize / denoise / align / subtract / glv_stats /
    cd_measure`` —— 一張 Region 卡都沒有。而 ``roi_from_mask`` 這個 key 在有了
    第二個 method 之後是一句謊話。

    ``source`` 要跟著換名字：新卡有**兩個**來源參數（一張晶圓的照片、一張
    label map），因為那是兩種完全不同的東西 —— 共用一格的話畫布上那條線會在
    切換 method 之後指著一個意思完全不同的東西。

    判準是「**舊 step 名在不在**」（鐵則 9）。換完之後不再命中，所以
    ``to_json_dict → from_json_dict`` 走第二次什麼都不會發生（identity）——
    `run_batch` 送 recipe 進 worker 走的正是那條路，它一旦不是 identity，
    ``workers=1`` 與 ``workers=2`` 會算出不同的分數。
    """
    for nid, node in list(nodes.items()):
        if node.step != "roi_from_mask":
            continue
        params = dict(node.params)
        params["method"] = "layout layers"
        params["label_source"] = str(
            params.pop("source", "") or "layout_label").strip() or "layout_label"
        nodes[nid] = RecipeNode(id=node.id, step="roi_reference",
                                params=params, enabled=node.enabled)


#: 折進 ``roi_reference`` 的那兩張卡：舊 key → ``method`` 的值（F30）。
_FOLDED_REGION_CARDS = {
    "roi_cross": "stripes in the image",
    "roi_template": "a cell I mark myself",
}

#: 合併之後**只有一格**，而舊卡各有各的預設 —— 遷移要把舊預設**逐字寫進參數**。
#:
#: 為什麼不是「讓新卡的預設剛好等於舊的」：三支的舊預設互相衝突
#: （``source`` 是 ``test`` vs ``ref``、``roi_out`` 是 ``cell`` vs ``cross``、
#: ``max_boxes`` 是 8192 vs 64）。挑任何一個當共用預設，另外兩支的舊 recipe
#: 就會**安靜地換一個值跑** —— ``max_boxes`` 從 64 變 8192 不會報錯，它會多量
#: 一百個框然後吐出一組不一樣的統計量。
_FOLDED_CARD_OLD_DEFAULTS = {
    "roi_cross": {"source": "ref", "roi_out": "cross", "max_boxes": 64},
    "roi_template": {"source": "ref", "max_boxes": 8192},
}

#: 撞名而**意思不同**的那一格：舊名 → 新名（每張卡各自一份）。
#:
#: ``min_confidence`` 在 ``roi_cross`` 上是「條紋的信心」（0..100 那種刻度，
#: 預設 5.0），在 ``repeating cells`` 上是「週期的強度」（0..1，預設 0.18）。
#: 共用一格的話，切換 method 會留下一組對方**看得懂但意思完全不同**的值 ——
#: 而它不會報錯，它會照著跑（同 `_migrate_roi_compare_into_glv_stats` 裡
#: ``metrics`` 那一段記下的教訓）。
_FOLDED_CARD_RENAMES = {
    "roi_cross": {"min_confidence": "min_stripe_confidence"},
    "roi_reference": {"min_confidence": "min_repeat_strength"},
}


def _migrate_output_image_into_bundle(nodes: Dict[str, "RecipeNode"]) -> None:
    """``output_image`` → ``output_bundle`` ＋ 只勾「圖」（F37，2026-08-26）。

    `output_image`（Write images）的**七格參數一格不差全部是 `output_bundle`
    的子集**，而它寫出來的東西正好是後者少了報表、表格與 recipe 三個檔案 ——
    也就是同一張卡的一個程度，不是另一件事（`CLAUDE.md` §3，前例 F29 的
    `roi_reference` 與 F19 的 CD）。

    **兩個差別要明講，因為它們就是這道遷移在補的東西**：

    ==================  =====================================================
    檔案格式            `output_image` 寫 PNG、`output_bundle` 寫 JPEG。
                        不指定 ``picture_format`` 的話，一份舊 recipe 會安靜
                        地換一種副檔名 —— 而使用者的下游認的正是副檔名。
    放在哪              `output_image` 把圖直接放在資料夾裡，`output_bundle`
                        放進 ``images/``。那一層存在的理由是**報表要用相對
                        路徑連過去**，所以沒有報表就沒有那一層（規則寫在
                        `OutputBundleStep.run_batch` 的 ``nested``）。
    ==================  =====================================================

    判準是「**舊 step 名在不在**」（鐵則 9）。換完之後不再命中，所以
    ``to_json_dict → from_json_dict`` 走第二次什麼都不會發生（identity）。
    """
    for nid, node in list(nodes.items()):
        if node.step != "output_image":
            continue
        params = dict(node.params)
        params["contents"] = "pictures"
        params["picture_format"] = "png"
        nodes[nid] = RecipeNode(id=node.id, step="output_bundle",
                                params=params, enabled=node.enabled)


#: 折進 ``output_report`` 的那四張卡（F38，2026-08-26）：
#: 舊 key → (``contents`` 要勾什麼, 路徑那一格的舊名, 參數改名表)。
#:
#: ``None`` 的那一列是 ``output_bundle`` —— 它本來就是資料夾那張卡，勾選也
#: 已經有了，所以只換 key。
_FOLDED_OUTPUT_CARDS: Dict[str, tuple] = {
    # 舊 key:           (勾什麼,     路徑舊名,  參數改名表)
    "output_csv":       ("table",   "path",   {}),
    "output_html":      ("report",  "path",   {}),
    "output_boxplot":   ("boxplot", "path",   {"features": "plot_features"}),
    "output_bundle":    (None,      "folder", {}),
}

#: ``output_bundle`` 沒寫 ``contents`` 時要明寫進去的那幾個（＝合併之前的行為）。
#:
#: **不是**去讀 ``steps.output.DEFAULT_CONTENTS``：那是「新卡片的預設」，而這裡
#: 要的是「舊檔案當時的行為」。同一個值，兩個意思 —— 綁在一起的話，哪天有人動
#: 了預設，這些舊 recipe 會跟著換一個行為，而它們一個字都沒改過。
_BUNDLE_OLD_CONTENTS = "report,table,pictures,recipe"


def _migrate_folded_output_cards(nodes: Dict[str, "RecipeNode"]) -> None:
    """四張報表卡 → ``output_report`` ＋ 對應的 ``contents``（F38，2026-08-26）。

    使用者：「七張裡有五張在回答同一個問題，收成三張」。四張被折的卡與
    ``output_report`` 自己（原本是「寫一個 Excel 檔」）合成一張寫資料夾的卡，
    要哪幾樣是一格勾選 —— 跟 F37 把 ``output_image`` 折進來時同一個形狀，
    連遷移的寫法都照抄（見 :func:`_migrate_folded_region_cards`）。

    **這道遷移在補的東西：產物的形狀從「一個檔案」變成「一個資料夾」。**
    被折的四張裡有三張是「一格路徑＝一個檔案」，而合併後那張卡寫的是一個
    資料夾、裡面的檔名是寫死的。所以**內容逐位元組相同，路徑會位移**：

    ==========================================  ===============================
    舊                                          新（實際寫出）
    ==========================================  ===============================
    ``output_csv path=/x/my.csv``               ``/x/defects.csv``
    ``output_html path=/x/page.html``           ``/x/report.html``
    ``output_boxplot path=/x/spread.html``      ``/x/spread.html``（同名）
    ``output_report path=/x/book.xlsx``         ``/x/report.xlsx``
    ``output_bundle folder=/x``                 ``/x``（一個字都沒動）
    ==========================================  ===============================

    使用者取的檔名因此會不見，而那是**使用者定調的取捨**（2026-08-26，
    「一律資料夾」）。`os.path.dirname` 的 ``or "."`` 不能省：
    ``path="report.html"``（沒有目錄的相對路徑）的 dirname 是空字串，而空字串
    在那張卡上的意思是「還沒填」—— 一份跑得動的 recipe 會變成一條設定錯誤。

    **``contents`` 一律明寫**（連 ``output_bundle`` 沒寫過那一格的也補）：
    把「舊檔案的行為」跟「新卡片的預設」脫鉤，之後有人動了預設，這些 recipe
    不會跟著改。F38 加進 Excel 與 box plot 兩個勾的那一刻，這件事就是必要的。

    判準是「**舊東西在不在**」（鐵則 9）——而**兩種節點的「舊東西」不一樣**：

    * 被折的四張：``node.step`` 是舊 key。換完 key 就不再命中。
    * ``output_report`` 自己：key 沒變，所以只能問**舊的參數名還在不在**
      （``"path" in params``）。換完 ``path`` 就 pop 掉了，也不再命中。
      **不准**寫成「``folder`` 不在就補」—— 那分不出「舊檔案」與「新 recipe
      剛好還沒填路徑」，而 ``to_json_dict → from_json_dict`` 一旦不是
      identity，``workers=1`` 與 ``workers=2`` 會算出不同的分數（真的發生過，
      見 `docs/PITFALLS.md`）。

    兩邊換完之後第二次走這一道什麼都不會發生 —— identity 成立。
    """
    for nid, node in list(nodes.items()):
        folded = _FOLDED_OUTPUT_CARDS.get(node.step)
        # ``output_report`` 自己那一張（原本的 Excel 卡）：key 沒換，靠舊參數名。
        own = node.step == "output_report" and "path" in node.params
        if folded is None and not own:
            continue
        params = dict(node.params)
        if own:
            tick, path_name, renames = "excel", "path", {}
        else:
            tick, path_name, renames = folded
        for old, new in renames.items():
            if old in params:
                params[new] = params.pop(old)
        if path_name == "path":
            # 一個檔案的路徑 → 裝它的那個資料夾（見 docstring 那張表）。
            path = str(params.pop("path", "") or "").strip()
            params["folder"] = (os.path.dirname(path) or ".") if path else ""
        if tick is not None:
            params["contents"] = tick
        else:
            params.setdefault("contents", _BUNDLE_OLD_CONTENTS)
        nodes[nid] = RecipeNode(id=node.id, step="output_report",
                                params=params, enabled=node.enabled)


def _migrate_folded_region_cards(nodes: Dict[str, "RecipeNode"]) -> None:
    """``roi_cross`` / ``roi_template`` → ``roi_reference`` ＋ 對應的 ``method``（F30）。

    使用者 2026-08-25：「把 Profile / Template 也折進 roi_reference」。當時那四張
    Region 卡回答的是同一句話（「哪些地方應該長得一樣」），所以它們折成了一張卡
    的 method —— 跟 ``roi_from_mask``（F29）與 ``roi_compare``（F16）同一個形狀，
    連遷移的寫法都照抄。（**今天幾個 method 看 ``roi_reference.METHODS``**。）

    判準是「**舊 step 名在不在**」（鐵則 9）。換完之後不再命中，所以
    ``to_json_dict → from_json_dict`` 走第二次什麼都不會發生（identity）——
    `run_batch` 送 recipe 進 worker 走的正是那條路。

    ⚠ ``roi_reference`` 自己那一格的改名（``min_confidence`` →
    ``min_repeat_strength``）也在這裡，而它的判準一樣是「舊鍵在不在」——
    F29 到 F30 之間存下來的檔案帶著舊名字。
    """
    for nid, node in list(nodes.items()):
        method = _FOLDED_REGION_CARDS.get(node.step)
        renames = _FOLDED_CARD_RENAMES.get(node.step) or {}
        if method is None and not (node.step == "roi_reference" and renames):
            continue
        params = dict(node.params)
        for old, new in renames.items():
            if old in params:
                params[new] = params.pop(old)
        if method is None:
            nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                    enabled=node.enabled)
            continue
        for name, value in (_FOLDED_CARD_OLD_DEFAULTS.get(node.step) or {}).items():
            params.setdefault(name, value)
        params["method"] = method
        nodes[nid] = RecipeNode(id=node.id, step="roi_reference",
                                params=params, enabled=node.enabled)


def _migrate_roi_compare_into_glv_stats(nodes: Dict[str, "RecipeNode"]) -> None:
    """``roi_compare`` → ``glv_stats`` + ``method="compare"``（F16）。

    使用者 2026-08-20：「Gray level Stats 跟 Compare regions 應該是做同樣的事
    （量 GLV 相關）吧，留其中一個就好」。它們其實不是同一件事（一個吐絕對值、
    一個吐差異），所以是**收成一張卡的兩個 method**，不是刪掉一張。

    留 ``glv_stats`` 這個 key 而不是 ``roi_compare``，理由是黃金值：兩份
    fixture recipe 與 ``tests/fixtures/golden/`` 都指著它。

    判準是「**舊東西在不在**」（鐵則 9）：這個節點的 step 就是 ``roi_compare``。
    不是靠「``method`` 這個新參數不在」—— 那分不出「舊檔案」與「新 recipe 剛好
    用預設的 stats」，而 ``to_json_dict → from_json_dict`` 一旦不是 identity，
    ``workers=1`` 與 ``workers=2`` 就會算出不同的分數（那真的發生過）。

    只有 ``metrics`` 要換名字：兩種 method 的可選值完全不同（``delta``/``snr``
    對上 ``glv_mean``/``glv_std``），共用一格的話，切換 method 會留下一組對方
    不認得的值 —— 而它跑起來是一條看不懂的錯誤訊息。
    """
    for nid, node in list(nodes.items()):
        if node.step != "roi_compare":
            continue
        params = dict(node.params)
        if "metrics" in params:
            params["compare_metrics"] = params.pop("metrics")
        params["method"] = "compare"
        nodes[nid] = RecipeNode(id=node.id, step="glv_stats", params=params,
                                enabled=node.enabled)


def _migrate_compare_method_into_reference(nodes: Dict[str, "RecipeNode"]) -> None:
    """``glv_stats`` 的 ``method="compare"`` → ``reference`` 那一格（F18 第 5 步）。

    使用者 2026-08-21 定調把 ``compare`` 併進「跟誰比」這個維度：**絕對值永遠
    吐，相對值疊在上面**。舊的二選一最實際的坑是 ``compare`` 從不輸出絕對值，
    所以「這塊 EPI 的平均灰階是 120」跟「它比隔壁亮 12」不能在同一張卡上同時
    得到 —— 使用者得放兩張卡、接兩次線，而那兩張各自有機會設得不一樣。

    對照：

    ======================  ==========================================
    舊                      新
    ======================  ==========================================
    ``target_source``       ``source``（本來就是這張卡在量的那條流）
    ``target_region``       ``roi``
    ``reference_source``    ``reference_source``（兩條流不同時才有意義）
    ``reference_region``    ``reference_region``
    ``stat``                ``stat`` ＋ ``metrics``（絕對值現在也吐）
    ======================  ==========================================

    ``metrics`` 補成 ``stat``：舊卡片用那個統計量代表每一塊，所以「它的絕對值」
    正是使用者心裡的那個數字。**相對值的名字逐字不變**（``<prefix>_delta``）——
    那是舊 recipe 的分數表達式不必改寫的前提。

    判準是「**舊東西在不在**」（鐵則 9）：``method`` 這個鍵還在，而且是
    ``compare``。做完把它刪掉，所以 ``to_json_dict → from_json_dict`` 走第二次
    時什麼都不會發生（identity）—— `run_batch` 送 recipe 進 worker 走的正是那
    條路，它一旦不是 identity，``workers=1`` 與 ``workers=2`` 會算出不同的分數。

    ⚠ **這一道不是終點**：它產出的 ``reference`` 由
    :func:`_migrate_reference_into_ports`（F67）再變成兩顆埠上的線。這裡繼續
    寫那一格是對的 —— 遷移鏈要一段一段接，寫一條直達的捷徑只有舊檔案會走到，
    永遠不會有人在上面測試。
    """
    for nid, node in list(nodes.items()):
        if node.step != "glv_stats":
            continue
        params = dict(node.params)
        method = str(params.pop("method", "") or "").strip()
        if not method:
            continue                      # 新 recipe：沒有這個鍵，什麼都不做
        if method != "compare":
            nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                    enabled=node.enabled)
            continue                      # ``stats`` 就是現在的預設行為
        target_source = str(params.pop("target_source", "") or "test").strip()
        ref_source = str(params.pop("reference_source", "") or "").strip()
        ref_region = str(params.pop("reference_region", "") or "").strip()
        params["source"] = target_source
        params["roi"] = str(params.pop("target_region", "") or "").strip()
        # 哪一種「跟誰比」，由**舊參數的值**決定（不是猜的）：流一不一樣 ×
        # 區域一不一樣，正好是一張真值表。
        #
        # ⚠ 第一版漏了「兩邊都不一樣」那一格，於是那種舊 recipe 被轉成
        # 「同一塊、另一條流」—— 跑得完、有數字，而那個數字**答的是另一個
        # 問題**。舊卡片有四個獨立的角色參數，所以它表達得出這一種。
        other_stream = bool(ref_source) and ref_source != target_source
        other_region = bool(ref_region) and ref_region != params["roi"]
        if other_stream and other_region:
            params["reference"] = "another region on another stream"
            params["reference_source"] = ref_source
            params["reference_region"] = ref_region
        elif other_stream:
            params["reference"] = "another stream"
            params["reference_source"] = ref_source
        else:
            params["reference"] = "another region"
            params["reference_region"] = ref_region
        params.setdefault("metrics", str(params.get("stat", "") or "glv_mean"))
        nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                enabled=node.enabled)


def _migrate_reference_into_ports(nodes: Dict[str, "RecipeNode"],
                                  edges: List["Edge"]) -> None:
    """``glv_stats`` 的 ``reference`` 那一格 → **兩顆埠上的線**（F67，2026-09-01）。

    使用者 2026-09-01：「GLV card 這邊的 ROI 接線我覺得對 user 來說還是會有點
    混淆 (Compare against) 跟最上方 What do I want to measure 相關」。那一格
    下拉的五個答案是一張真值表 —— **參照區域那顆埠有沒有線 × 參照流那顆埠有
    沒有線** —— 也就是把線複述了一遍（見 `steps.glv_stats._reference_of`）。

    對照：

    ================================  ==========================================
    舊 ``reference``                  新（兩顆埠）
    ================================  ==========================================
    ``none``                          兩顆都不接 —— **而且要把線剪掉**（見下）
    ``another region``                只接 ``reference_region``
    ``another stream``                只接 ``reference_source``
    ``another region on another       兩顆都接
    stream``
    ``the other regions``             ``reference_region`` 接 ``<roi>_others``
    ================================  ==========================================

    **剪線那一半才是這道遷移的重點。** 舊的 ``reference`` 一旦選回 ``none``
    （或從「兩邊都不一樣」改成「另一條流」），另一顆埠上的線**不會跟著剪掉**
    —— 引擎讀的是那一格所以沒事，但線還在檔案裡。照抄過來的話，那些線在
    F67 之後**就是答案**：一份原本只報絕對值的 recipe 會開始吐 ``cmp_*``，
    而且是安靜地吐。所以這裡對每一種情況都明確地寫下**哪一顆埠該留、哪一顆
    該剪**，兩邊都做。

    ``the other regions`` 是唯一要補東西的一種（它以前不接線，靠
    ``<roi>_others`` 這個家族慣例）。一個區域的那種補完**數字與特徵名逐字
    不變**；量好幾個區域的那種以前是「每一塊各自跟自己的其餘同類比」，一條線
    表達不出來 —— 補第一塊的，而 `GlvStatsStep.configuration_issues` 從此對
    那個形狀講一句話（那是 F67 新加的一條 lint，見那一支）。

    判準是「**舊東西在不在**」（鐵則 9）：``reference`` 這個鍵還在。做完把它
    刪掉，所以 ``to_json_dict → from_json_dict`` 走第二次什麼都不會發生
    （identity）—— `run_batch` 送 recipe 進 worker 走的正是那條路。
    """
    keep_region = {"another region", "another region on another stream",
                   "the other regions"}
    keep_stream = {"another stream", "another region on another stream"}
    for nid, node in list(nodes.items()):
        if node.step != "glv_stats" or "reference" not in node.params:
            continue
        params = dict(node.params)
        ref = str(params.pop("reference", "") or "").strip()
        if ref == "the other regions":
            # 量的是哪一塊 —— 參數或線，兩種檔案都要認得（v1 的值在參數裡，
            # v2 的在線上，而 `to_json_dict` 會把跟線一致的那一格丟掉）。
            roi_edges = [e for e in edges
                         if e.dst == nid and e.dst_in == "roi" and e.src_out]
            names = [x.strip() for x
                     in str(params.get("roi", "") or "").split(",") if x.strip()]
            names = names or [e.src_out for e in roi_edges]
            if names:
                params["reference_region"] = names[0] + "_others"
                # 線在的話**這裡就補**：那條 ``<roi>_others`` 跟 ``roi`` 出自
                # 同一張卡（家族慣例），而 `_migrate_region_params_into_edges`
                # 只對 ``version < RECIPE_VERSION`` 的檔案跑。
                src = next((e.src for e in roi_edges
                            if e.src_out == names[0]), "")
                have = {(e.dst, e.dst_in, e.src_out) for e in edges}
                if src and (nid, "reference_region",
                            params["reference_region"]) not in have:
                    edges.append(Edge(src=src, dst=nid,
                                      src_out=params["reference_region"],
                                      dst_in="reference_region"))
        for pname, keep in (("reference_region", ref in keep_region),
                            ("reference_source", ref in keep_stream)):
            if keep:
                continue
            params[pname] = ""
            edges[:] = [e for e in edges
                        if not (e.dst == nid and e.dst_in == pname)]
        nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                enabled=node.enabled)


def _migrate_align_into_streams(nodes: Dict[str, "RecipeNode"],
                               edges: List["Edge"]) -> None:
    """``align`` 換形狀：一條 moving 對一條 fixed → 一組 ``streams`` 就地對齊（F109）。

    舊形狀是 ``moving`` / ``fixed`` / ``out``，只寫出**一條**新流（預設
    ``ref_aligned``）。新形狀是 ``streams``（含基準）＋ ``fixed``，每條**寫回原名**
    —— 因為新卡會把所有參與的流一起裁成共同重疊區，基準那一條不跟著裁的話，
    出去的幾條尺寸就對不起來。

    所以這一道要做兩件事，少做第二件的話**舊檔案會安靜地拿不同尺寸的兩張圖去相減**：

    1. 把三個舊參數換成兩個新的；
    2. **把下游指著 ``out`` 的地方改成指 ``moving``** —— 參數格與線上的埠名都要。

    ⚠ **判準是版本號，不是「舊 key 在不在」。** 一般的遷移該看舊東西存不存在
    （鐵則 9），但這一道不行：實測 ``tests/fixtures/recipes/dual_route_basic.json``
    的 align 節點**三個舊參數一個都沒寫**，整個靠預設值跑 —— 而那正是鐵則 9 說
    「分不出來」的那種訊號。版本號是這裡唯一看得見的差異，所以
    ``RECIPE_VERSION`` 跟著升到 4。

    ⚠ 第 2 件事要問 ``REGISTRY`` 「這一格是不是影像流」，所以它跟
    :func:`_migrate_folded_output_cards` 一樣**要求卡片庫已經 import 過**
    （CLI、Studio、worker 的 ``_init_worker`` 三個入口都會）。
    只 import ``recipe`` 而不 import ``d4t.core.steps`` 的話，第 1 件照做、
    第 2 件靜靜跳過 —— 那是既有的慣例，不是這一道新增的風險。
    """
    for nid, node in list(nodes.items()):
        if node.step != "align":
            continue
        params = dict(node.params)
        moving = str(params.pop("moving", "ref") or "ref").strip()
        fixed = str(params.get("fixed", "test") or "test").strip()
        out = str(params.pop("out", "ref_aligned") or "").strip()
        params["fixed"] = fixed
        params["streams"] = "%s,%s" % (fixed, moving) if fixed != moving else fixed
        params["suffix"] = ""
        nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                enabled=node.enabled)
        if not out or out == moving:
            continue
        # 下游別再指著那條不再存在的流。
        for other_id, other in list(nodes.items()):
            if other_id == nid:
                continue
            spec = REGISTRY.get(other.step)
            if spec is None:
                continue
            changed = dict(other.params)
            touched = False
            for ps in spec.params:
                if ps.type not in IMAGE_TYPES or ps.direction != "in":
                    continue
                if str(changed.get(ps.name, "") or "").strip() == out:
                    changed[ps.name] = moving
                    touched = True
            if touched:
                nodes[other_id] = RecipeNode(id=other.id, step=other.step,
                                             params=changed,
                                             enabled=other.enabled)
        for i, e in enumerate(list(edges)):
            if e.src == nid and e.src_out == out:
                edges[i] = Edge(src=e.src, dst=e.dst, src_out=moving,
                                dst_in=e.dst_in)


def _migrate_split_out_combine(nodes: Dict[str, "RecipeNode"],
                               edges: List["Edge"]) -> None:
    """`subtract` 的 max/min/mean → 新的 `combine` 卡（F110，2026-09-18）。

    那三個 ``op`` 回答的不是這張卡在問的問題。判準是**訊號形狀**：比較是
    2 條進 1 條出，融合是 N 條進 1 條出 —— 而 max/min/mean 跟「兩張」沒有關係。

    換卡要換三件事，少任何一件舊檔案都開不起來：

    1. ``step``：``subtract`` → ``combine``；
    2. 參數：``a`` / ``b`` 兩顆埠併成一格 ``streams``，``op`` → ``method``；
    3. **線上的埠名**：指進來的邊 ``dst_in`` 從 ``a`` / ``b`` 變成 ``streams``。
       少了這一件，畫布上那兩條線指向不存在的埠 —— 而畫布會照實畫出來（F9），
       使用者看到的是「我的 recipe 壞了」。

    判準照鐵則 9 看**舊的值**（``op`` 是不是那三個之一），不是看新鍵缺席 ——
    所以跑第二次是 no-op。``absolute`` 一起帶過去嗎？**不帶**：融合沒有
    「取絕對值」的意思（它不產生負值），而那一格在舊檔案裡對 max/min/mean
    本來就沒有作用（舊的 `run` 只在 ``subtract`` 那一支讀它）。
    """
    moved = {"max": "max", "min": "min", "mean": "mean"}
    for nid, node in list(nodes.items()):
        if node.step != "subtract":
            continue
        op = str(node.params.get("op", "subtract") or "subtract").strip()
        if op not in moved:
            continue
        old = dict(node.params)
        a = str(old.get("a", "test") or "").strip()
        b = str(old.get("b", "ref") or "").strip()
        params: Dict[str, Any] = {
            "streams": ",".join([x for x in (a, b) if x]),
            "method": moved[op],
        }
        if old.get("out"):
            params["out"] = old["out"]
        nodes[nid] = RecipeNode(id=node.id, step="combine", params=params,
                                enabled=node.enabled)
        for i, e in enumerate(list(edges)):
            if e.dst == nid and e.dst_in in ("a", "b"):
                edges[i] = Edge(src=e.src, dst=e.dst, src_out=e.src_out,
                                dst_in="streams")


def _migrate_absolute_into_sign(nodes: Dict[str, "RecipeNode"]) -> None:
    """`subtract` 的 ``absolute``（bool）→ ``sign``（三選一）（F110）。

    判準是**「舊鍵在不在」**（鐵則 9 的正牌用法），而這一道剛好用得上它 ——
    跟 F109 的 align 不一樣。

    ⚠ 差別在**預設值的意思有沒有變**：align 那一道非得靠版本號，因為舊預設
    （``moving="ref"``、``out="ref_aligned"``）跟新預設是兩種不同的行為，
    從「缺一個 key」分不出是哪一種。這一道沒有那個問題 ——
    舊的 ``absolute=True`` 跟新的 ``sign="abs"`` **是同一件事**，所以
    **檔案裡沒寫 ``absolute`` 就什麼都不要做**：不寫也跑得出一模一樣的結果，
    而寫下去就是「讀檔幫使用者填了一個他沒寫的值」
    （`test_reading_a_recipe_never_invents_a_parameter` 守的正是這件事 ——
    這一道第一版真的踩到了它）。

    ``True`` → ``abs``、``False`` → ``signed``。沒有一個舊值會變成 ``split``
    —— 那是這一輪新長出來的第三種答案。
    """
    for nid, node in list(nodes.items()):
        if node.step != "subtract" or "absolute" not in node.params:
            continue
        params = dict(node.params)
        keep = bool(params.pop("absolute"))
        params["sign"] = "abs" if keep else "signed"
        nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                enabled=node.enabled)


def _migrate_glv_ref_pairing(nodes: Dict[str, "RecipeNode"]) -> None:
    """v<3 的 `glv_stats`：把逐框比較的參照**釘回 ``pooled``**（F68）。

    F68 讓「逐框比較 ＋ 參照在另一張影像」預設**第 i 格對第 i 格**
    （使用者 2026-09-01：「patch 預設就用逐格配對」，因為混成一堆的那種
    讓「照跟參照差多少挑」變成空包彈 —— 見 `steps.glv_stats.REF_PAIRINGS`）。

    但**一個會動的預設等於安靜地改掉每一份舊 recipe 的數字**（`CLAUDE.md` §3
    那句話）。所以舊檔案在這裡把當時的行為寫明：跑出來的數字逐位元組不變，
    而畫面上那一格會顯示 ``pooled`` —— 使用者看得到自己在用哪一種，也改得動。

    判準是**版本號**（`version < RECIPE_VERSION`），不是「有參數但沒有值」
    —— 後者分不出「舊檔案」與「新 recipe 剛好選了 pooled」（鐵則 9）。
    只補**用得到它**的那幾張卡（逐框 ＋ 只接了參照流），其餘一個字不動。
    """
    for nid, node in list(nodes.items()):
        if node.step != "glv_stats" or "ref_pairing" in node.params:
            continue
        params = dict(node.params)
        if str(params.get("across_boxes", "") or "").strip() != "each box":
            continue
        if not str(params.get("reference_source", "") or "").strip():
            continue
        if str(params.get("reference_region", "") or "").strip():
            continue                    # 另一塊區域 —— 本來就配不起來
        params["ref_pairing"] = "pooled"
        nodes[nid] = RecipeNode(id=node.id, step=node.step, params=params,
                                enabled=node.enabled)


def _renamed_idents(expr: str, table: Dict[str, str]) -> str:
    """一條表達式裡的**整個識別字**照 ``table`` 換掉（子字串不算）。

    ``str.replace`` 會把 ``my_delta_ratio`` 這種自訂名字打斷 —— 所以用邊界比對，
    而且**長的先比**：``epi_delta`` 與 ``delta`` 同時在表裡時，前者要先中。
    """
    if not expr or not table:
        return expr
    keys = sorted(table, key=len, reverse=True)
    return re.sub(r"\b(%s)\b" % "|".join(map(re.escape, keys)),
                  lambda m: table[m.group(1)], expr)


def _rename_in_expr(score: "ScoreSpec", table: Dict[str, str]) -> "ScoreSpec":
    """分數表達式裡的舊 feature 名換成新的（見 :func:`_renamed_idents`）。"""
    expr = str(getattr(score, "expr", "") or "")
    new_expr = _renamed_idents(expr, table)
    return score if new_expr == expr else replace(score, expr=new_expr)


def _rename_in_tree(node: Any, table: Dict[str, str]) -> Any:
    """判定樹每一步的 ``when`` 照 ``table`` 換名（葉子沒有表達式）。"""
    if node is None or isinstance(node, TreeLeaf):
        return node
    when = _renamed_idents(str(getattr(node, "when", "") or ""), table)
    yes = _rename_in_tree(node.yes, table)
    no = _rename_in_tree(node.no, table)
    if when == node.when and yes is node.yes and no is node.no:
        return node
    return TreeStep(when=when, yes=yes, no=no)


def mentions_feature(text: str, name: str) -> bool:
    """一條算式（或一格參數值）裡有沒有**整個識別字** ``name``。

    用邊界比對而不是 ``in``：``glv_median in "epi_glv_median"`` 是 True，
    而那是兩個不同的數字。同 :func:`_renamed_idents` 的理由，只是反過來問。
    """
    if not text or not name:
        return False
    return re.search(r"\b%s\b" % re.escape(str(name)), str(text)) is not None


def feature_referrers(name: str, nodes: Dict[str, "RecipeNode"],
                      score_expr: str = "", decide: Any = None,
                      skip: str = "",
                      registry: Optional[Dict[str, Any]] = None) -> List[str]:
    """誰還指著 ``name`` —— 回一串**給人看的位置**（F37 A2）。

    每一個地方跟改名遷移走的**同一份清單**（`_rename_in_node_params` 的說明）：
    分數表達式、判定段、以及型別在 `step.FEATURE_TYPES` 裡的參數值
    （`feature_math` 的算式曾經是第三種，那張卡 2026-08-27 刪了）。
    兩支要一起看 —— 遷移是「自動搬」，
    這一支是「搬不動的時候說出搬不動的是哪幾個」。

    ``skip`` 是**改名的那張卡自己**：它不算引用者（它是來源）。

    ``score_expr`` 吃的是**字串**而不是 `ScoreSpec`：編輯中的 model 上分數就
    是一個字串（`RecipeModel.expr`），為了呼叫這一支去湊一個完整的 ScoreSpec
    等於發明一個假的門檻與 bins。
    """
    if registry is None:
        registry = REGISTRY
    out: List[str] = []
    if mentions_feature(score_expr, name):
        out.append("the score expression")
    if decide is not None:
        spots = [str(getattr(decide, "score", "") or "")]
        spots += [str(getattr(lt, "expr", "") or "") for lt in decide.let]
        spots += [str(getattr(r, "when", "") or "") for r in decide.rules]

        def walk(node: Any) -> None:
            if node is None or isinstance(node, TreeLeaf):
                return
            spots.append(str(getattr(node, "when", "") or ""))
            walk(node.yes)
            walk(node.no)

        walk(getattr(decide, "tree", None))
        if any(mentions_feature(t, name) for t in spots):
            out.append("the decision")
    for nid, node in (nodes or {}).items():
        if nid == skip:
            continue
        step_cls = registry.get(node.step)
        if step_cls is None:
            continue
        for spec in getattr(step_cls, "params", ()) or ():
            if spec.type not in FEATURE_TYPES:
                continue
            raw = node.params.get(spec.name)
            if not isinstance(raw, str) or not raw.strip():
                continue
            hit = (mentions_feature(raw, name) if spec.type == "expr"
                   else name in [x.strip() for x in raw.split(",")])
            if hit:
                out.append("“%s” (%s)" % (nid, spec.label or spec.name))
    return out


def _swap_padded(part: str, swap) -> str:
    """``"  worst_score "`` → ``"  glv_worst_score "``（前後空白原樣留著）。"""
    core = part.strip()
    if not core:
        return part
    lead = part[:len(part) - len(part.lstrip())]
    tail = part[len(part.rstrip()):]
    return lead + swap(core) + tail


def _rename_in_node_params(nodes: Dict[str, "RecipeNode"],
                           table: Dict[str, str],
                           registry: Optional[Dict[str, Any]] = None) -> None:
    """節點參數裡的舊 feature 名換成新的（**就地改**，F37）。

    以前改名遷移只走兩條路：分數表達式與判定段（曾經還有第三條 ——
    `feature_math` 的算式，而那張卡 2026-08-27 刪了）。還有一條沒有人走
    —— **參數值**：Output 卡的 ``rank_by`` / ``columns``、`output_boxplot` 的
    ``features``、`output_klarf` 的 ``size_feature`` 每一格都裝著特徵名。

    漏掉它的症狀特別壞，因為**它跑得完**：`rank_by` 指到一個不存在的數字時，
    出圖卡排不出順序就安靜地退回檔案順序，於是使用者拿到 N 張正常的圖，
    而「最值得看的那 N 顆」這件事完全沒有發生（那正是 F30 修過一次的 bug，
    只是這次的來源是遷移）。

    **照型別走，不照卡片清單走**（:data:`step.FEATURE_TYPES`）：第五張會用到
    特徵名的卡不必回來這裡登記。三種型別裝法不同，所以改寫方式也不同：

    ==================  ==========================================
    ``expr``            一條算式 → 換整個識別字（`_renamed_idents`）
    ``feature_keys``    逗號清單 → **逐項整格比對**
    ``feature_key``     單獨一個名字 → 整格比對
    ==================  ==========================================

    清單與單格刻意**不走識別字比對**：那一格的值就是一個名字，而
    `_renamed_idents` 對 ``score`` 這種哨兵值（`rank_by` 的預設）也會照樣
    比對 —— 整格比對讓「這一格裝的是不是舊名字」只有一個答案。

    **判準仍然是「舊東西在不在」**（鐵則 9）：換完留下的新名字不在表的左邊，
    所以第二次跑是 no-op，``to_json_dict → from_json_dict`` 仍然是 identity。
    """
    if not table or not nodes:
        return
    if registry is None:
        registry = REGISTRY

    def one(name: str) -> str:
        return table.get(str(name).strip(), str(name).strip())

    for node in nodes.values():
        step_cls = registry.get(node.step)
        if step_cls is None:
            continue
        for spec in getattr(step_cls, "params", ()) or ():
            if spec.type not in FEATURE_TYPES or spec.name not in node.params:
                continue
            raw = node.params[spec.name]
            if not isinstance(raw, str) or not raw.strip():
                continue
            if spec.type == "expr":
                new = _renamed_idents(raw, table)
            elif spec.type == "feature_keys":
                # **每一項的前後空白照原樣留著**：一份 recipe 被 diff 的時候，
                # 沒有改到名字的那幾項不該因為重排空白而變成一行改動。
                new = ",".join(_swap_padded(part, one) for part in raw.split(","))
            else:
                new = one(raw)
            if new != raw:
                node.params[spec.name] = new


def _rename_in_decide(decide: Optional["DecideSpec"],
                      table: Dict[str, str]) -> Optional["DecideSpec"]:
    """判定段裡的舊 feature 名換成新的（F33，2026-08-25）。

    **這一支是補上來的**：改名遷移本來只走 `score.expr`
    （:func:`_rename_in_expr`），而判定段的 ``let`` / ``rules`` / ``tree``
    裡的表達式一個都沒人改寫。F30 之後那裡才是問問題的地方 ——
    樹上的 ``pair_found < 1`` 沒跟著換，開起來就是一題**永遠答「否」**的問題
    （問不到的特徵算否），而畫面上它長得跟一條正常的規則一模一樣：
    跑得完、有數字、而且是錯的。

    **判準仍然是「舊東西在不在」**（鐵則 9）：表達式裡真的出現舊名字才動它，
    換完留下的新名字不在表的左邊 → 第二次跑是 no-op，
    ``to_json_dict → from_json_dict`` 仍然是 identity。
    """
    if decide is None or not table:
        return decide
    score = _renamed_idents(str(decide.score or ""), table)
    lets = [replace(lt, expr=_renamed_idents(str(lt.expr or ""), table))
            for lt in decide.let]
    rules = [replace(r, when=_renamed_idents(str(r.when or ""), table))
             for r in decide.rules]
    tree = _rename_in_tree(decide.tree, table)
    unchanged = (score == decide.score
                 and all(a.expr == b.expr for a, b in zip(lets, decide.let))
                 and all(a.when == b.when for a, b in zip(rules, decide.rules))
                 and tree is decide.tree)
    if unchanged:
        return decide
    return replace(decide, let=lets, rules=rules, score=score, tree=tree)


def _migrate_renamed_features(score: "ScoreSpec") -> "ScoreSpec":
    """分數表達式裡的舊 feature 名換成新的。

    **不換的話，舊 recipe 打開來是一條 `unknown-feature` 警告加一個算不出來的
    分數** —— 而那個分數是這份 recipe 存在的理由。改卡片的名字卻不改它寫出來的
    數字的名字，等於只搬了一半。

    只換**整個識別字**（用邊界比對），不做子字串取代：``golden_px`` 若用
    ``str.replace`` 去換，``my_golden_px_ratio`` 這種自訂名字會被打斷。
    """
    expr = str(getattr(score, "expr", "") or "")
    if not expr:
        return score
    new_expr = re.sub(
        r"\b(%s)\b" % "|".join(map(re.escape, _RENAMED_FEATURES)),
        lambda m: _RENAMED_FEATURES[m.group(1)], expr)
    if new_expr == expr:
        return score
    return replace(score, expr=new_expr)


def _compare_feature_renames(nodes: Dict[str, "RecipeNode"]) -> Dict[str, str]:
    """舊的相對量特徵名 → ``cmp_*``（F18 補課第三輪，2026-08-21）。

    使用者：「絕對量的跟相對量的還是要分類好，不然不清楚命名規則會很痛苦。」
    ``epi_delta`` 因此變成 ``epi_cmp_delta_median`` —— 而分數表達式裡指著舊
    名字的那一份，不換就是一條 `unknown-feature` 加一個算不出來的分數
    （同 :func:`_migrate_renamed_features` 的理由）。

    **對照表跟名字的規則住在同一個地方**（`GlvStatsStep.legacy_feature_renames`）：
    抄一份到這裡的話，改一次名字有兩個地方要跟上，而漏掉的那一次會改寫成一個
    不存在的變數 —— 跑起來才炸，而且炸在別的地方（`CLAUDE.md` §0）。

    **判準是「舊東西在不在」**（鐵則 9）：只有表達式裡真的出現舊名字才動它。
    換完之後留下的是 ``cmp_…``，它不在對照表的左邊 —— 所以第二次跑是 no-op，
    而 ``to_json_dict → from_json_dict`` 仍然是 identity。
    """
    out: Dict[str, str] = {}
    for node in nodes.values():
        try:
            step_cls = REGISTRY[node.step]
        except Exception:  # 不認得的卡就跳過
            swallowed("recipe._compare_feature_renames")
            continue
        renames = getattr(step_cls, "legacy_feature_renames", None)
        if renames is None:
            continue
        try:
            out.update(renames(dict(node.params)))
        except Exception:  # 遷移不該讓開檔失敗
            swallowed("recipe._compare_feature_renames")
            continue
    return out


def _rescued_name_renames(nodes: Dict[str, "RecipeNode"],
                          routes: Optional[Dict[str, List[str]]] = None,
                          registry: Optional[Dict[str, Any]] = None
                          ) -> Dict[str, str]:
    """撞名時「被蓋掉那份」的舊名字 → 新名字（F17-②）。

    以前的前綴是**節點 id**（``norm_clip_frac``），現在是那條流的名字
    （``test_clip_frac``）。舊 recipe 的表達式如果指著舊名字，不換的話它會變成
    一條 `unknown-feature`，而分數算不出來 —— 同 :func:`_migrate_renamed_features`
    的理由。

    **判準是「舊東西在不在」**（鐵則 9）：只有當
    ``<節點 id>_<這張卡真的會產出的特徵名>`` 這個形狀成立、而且那張卡的新前綴
    跟節點 id 不同，才算數。少了最後那個條件會把使用者自己取的名字
    （`output_prefix` 剛好叫 `norm` 的那種）也改掉。

    ⚠ **逐 route 算，不是整份 nodes 一起算**（F17 審查抓到的）。執行時
    `_run_nodes` 拿的是**那一條 route 的 order**，而 `feature_prefixes` 的去重
    池子就是那份清單。整份一起算的話池子多了別條 route 的節點 → 多判出撞名 →
    多退回節點 id。實測：兩條 route 各一張 `normalize`，執行時兩邊都是 ``test``，
    整份一起算卻是「撞名」→ **一個字都不遷移**，而引擎產出的是新名字。

    同一個節點在兩條 route 上算出**不同**前綴時退回節點 id（不遷移）：那時候
    沒有一個正確答案 —— 分數表達式是兩條 route 共用的。
    """
    from .engine import feature_prefixes  # 延後匯入：避免 import 迴圈

    if registry is None:
        from .step import REGISTRY as registry  # type: ignore[no-redef]
    holder = type("_R", (), {"nodes": nodes})()
    lists = [list(v) for v in (routes or {}).values()] or [list(nodes or {})]

    # 每條 route 各算一次，再合併；答案不一致的節點退回節點 id。
    prefixes: Dict[str, str] = {}
    for order in lists:
        for nid, pfx in feature_prefixes(order, holder, registry).items():
            if prefixes.setdefault(nid, pfx) != pfx:
                prefixes[nid] = nid

    out: Dict[str, str] = {}
    for nid, node in (nodes or {}).items():
        step_cls = registry.get(node.step)
        if step_cls is None:
            continue
        prefix = prefixes.get(nid, nid)
        if prefix == nid:
            continue                   # 名字沒變，沒得遷移
        try:
            p = step_cls.validate_params(dict(node.params))
        except Exception:
            p = dict(node.params)
        try:
            feats = list(step_cls.resolve_features(p))
        except Exception:
            swallowed("recipe._rescued_name_renames")
            continue
        for f in feats:
            out["%s_%s" % (nid, f)] = "%s_%s" % (prefix, f)
    return out


def _migrate_rescued_feature_names(nodes: Dict[str, "RecipeNode"],
                                   score: "ScoreSpec",
                                   routes: Optional[Dict[str, List[str]]] = None
                                   ) -> "ScoreSpec":
    """把舊的「節點 id 前綴」名字換成流名前綴 —— 分數表達式與 Algo 卡的算式。

    跟 :func:`_migrate_renamed_features` 一樣**只換整個識別字**（邊界比對），
    不做子字串取代。

    ⚠ **這一道只在 :meth:`Recipe.load` 跑**（讀檔案），不在
    :meth:`Recipe.from_json_dict`（重建物件）—— 理由見 `Recipe.load` 的說明：
    它不冪等，而重建那條路是 worker 走的（鐵則 9）。
    """
    renames = _rescued_name_renames(nodes, routes)
    if not renames:
        return score
    pattern = re.compile(r"\b(%s)\b" % "|".join(map(re.escape, renames)))

    def swap(text: str) -> str:
        return pattern.sub(lambda m: renames[m.group(1)], str(text or ""))

    # ⚠ 這裡以前還有一條「改寫 `feature_math` 節點的算式」。那張卡 2026-08-27
    # 刪掉了（Phase 3），而帶著它的舊 recipe 開起來是一條 `unknown-step` ——
    # **跑不起來的 recipe 沒有必要幫它改名**。
    #
    # 判定段（`decide` 的 `let` / 樹）**這一道不改**，而那是對的：這個前綴規則
    # （F17-②，2026-08-21）比判定段（F21-D，2026-08-23）早出生，存得出判定段的
    # 檔案一開始就是新前綴。這裡以前寫「走 `_migrate_decide_renames`，那一條還在」
    # —— 那支函式從來不存在（F122 查到的）；判定段唯一的改名遷移是
    # `_rename_in_decide`（相對量改叫 `cmp_*` 那一張表）。
    expr = str(getattr(score, "expr", "") or "")
    new_expr = swap(expr)
    return score if new_expr == expr else replace(score, expr=new_expr)

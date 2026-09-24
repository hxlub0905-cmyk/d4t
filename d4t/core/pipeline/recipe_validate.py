# d4t pipeline engine — recipe 的 lint（2026-09-24 從 recipe.py 拆出）.
"""Recipe 的 lint：:func:`validate` 一次列出**所有**問題（KLIP ``Issue`` 結構）。

⚠ 用到 :class:`recipe.Recipe` 與 :func:`recipe.execution_order` 的地方**延遲
import**：`recipe.py` 在最後才轉出口這一支，模組層互相 import 會繞成圈。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, Type

from .expression import ExpressionError, parse_expression
from .recipe_schema import (
    LET_SCALES,
    OUTCOMES,
    DecideSpec,
    RecipeError,
    RecipeNode,
    RouteBy,
    _tree_depth,
    _tree_whens,
    is_region_edge,
    let_names_written,
    version_skew,
)
from .step import (
    GROUP_COMPARE,
    GROUP_ENHANCE,
    IMAGE_TYPES,
    REGION_TYPES,
    REGISTRY,
    SCALE_LOT,
    ParamError,
    Step,
)

if TYPE_CHECKING:
    from .recipe import Recipe


#: 哪幾種 lint 講的是**判定段**（F50，2026-08-28）。
#:
#: 為什麼需要這張表：`Issue.node_id` 是「哪一張卡」，而判定不是一張卡 ——
#: 它是 recipe 的頂層鍵，所以它的 issue 一律 ``node_id=None``。而 UI 的
#: `studio._node_problems()` 第一件事就是把沒有節點的 issue 丟掉
#: （`if not nid: continue`）—— 於是**判定的警告畫不出徽章**，只在跑完之後
#: 的狀態列尾巴出現一次，而跑一次是好幾分鐘。
#:
#: ⚠ **不能用「``node_id`` 是 None」當判準。** 那一組裡還有三條講分流
#: （`bad-route-by` / `route-not-reachable` / `unknown-route`）與一條講整張
#: 圖（`cycle`）—— 把它們掛到判定的入口卡上，那張卡就會替別人的問題背鍋。
#: 所以列出來，而 `tests/test_decision_issue_codes.py` 反過來守：**每一條
#: 沒有節點的 lint 都要被分類到**，新加一條而忘了分類會紅（不然它會安靜地
#: 掉回地上，也就是這一輪在修的那個洞）。
DECISION_ISSUE_CODES = frozenset({
    "ambiguous-decision", "bad-bins", "bad-let", "bad-rule",
    "deep-tree", "no-rules", "score-expr", "unknown-feature",
    "conflicting-outcome", "unknown-outcome",                  # F119
})

#: 沒有節點、但**不是**判定的那幾條（見上）。兩張表合起來要蓋滿。
NON_DECISION_NODELESS_CODES = frozenset({
    "bad-route-by", "route-not-reachable", "unknown-route",   # 分流
    "cycle",                                                  # 整張圖
})


# ---------------------------------------------------------------------------
# 多類別判定（F21-D）
# ---------------------------------------------------------------------------
def _decide_issues(recipe: "Recipe", decide: "DecideSpec") -> List["Issue"]:
    """`decide` 的健檢（F21-D）。

    最重要的一條是 ``ambiguous-decision``：``score`` 與 ``decide`` **不能並存**。
    這個 repo 最怕的形狀就是「同一件事有兩個地方存」—— 挑一個贏的話，另一份會
    安靜地漂，而使用者改了沒用的那一份時畫面上看不出來。
    """
    out: List[Issue] = []
    if str(recipe.score.expr or "").strip():
        out.append(Issue(
            code="ambiguous-decision", level="error", node_id=None,
            title="This recipe decides the bin in two different ways",
            detail="it has both a 'score' expression and a 'decide' block. "
                   "Keep one of them: 'decide' is the one with several "
                   "classes; 'score' is the two-bin threshold. Clear "
                   "score.expr to use 'decide'."))
    # ---- 判定樹（F24）----
    if decide.tree is not None and decide.rules:
        out.append(Issue(
            code="ambiguous-decision", level="error", node_id=None,
            title="This decide block sorts in two different ways",
            detail="it has both a flat 'rules' list and a 'tree'. Keep one: "
                   "the rules list is just a chain-shaped tree, so move the "
                   "rules into the tree (or drop the tree)."))
    if decide.tree is not None:
        depth = _tree_depth(decide.tree)
        if depth > 16:
            out.append(Issue(
                code="deep-tree", level="warning", node_id=None,
                title="The decision tree is very deep",
                detail="%d questions deep. A defect only ever takes one path, "
                       "but nobody can read a tree this tall - consider "
                       "combining conditions ((a > 5) * (b < 2) means both)."
                       % depth))
        for when in _tree_whens(decide.tree):
            try:
                parse_expression(when)
            except ExpressionError as e:
                out.append(Issue(
                    code="bad-rule", level="error", node_id=None,
                    title="A tree step's question does not parse",
                    detail=str(e)))
    if not decide.rules and decide.tree is None:
        out.append(Issue(
            code="no-rules", level="warning", node_id=None,
            title="The decide block has no rules",
            detail="every defect will land in the 'otherwise' bin (%d). "
                   "Add a rule, or use a score expression instead."
                   % int(decide.otherwise_bin)))
    seen: Set[str] = set()
    for i, item in enumerate(decide.let):
        if item.is_blank:
            continue                      # 整行空白＝當成沒填（見 `Let.is_blank`）
        name = str(item.name).strip()
        if not name:
            advice = ("Every 'let' line needs a name - that name is what "
                      "the rules below refer to.")
            out.append(Issue(
                code="bad-let", level="error", node_id=None,
                title="A 'let' line has no name",
                detail="let line %d: %s" % (i + 1, advice), advice=advice))
        elif name in seen:
            advice = ("It is called '%s' again - the second one would "
                      "quietly replace the first." % name)
            out.append(Issue(
                code="bad-let", level="error", node_id=None,
                title="Two 'let' lines have the same name",
                detail="let line %d: %s" % (i + 1, advice),
                names=(str(name),), advice=advice))
        seen.add(name)
        try:
            parse_expression(item.expr)
        except ExpressionError as e:
            out.append(Issue(
                code="bad-let", level="error", node_id=None,
                title="A 'let' line does not parse", detail=str(e)))
        fill = str(getattr(item, "fill", "") or "")
        if fill:
            try:
                float(fill)
            except ValueError:
                advice = ("It says 'if missing use %s' - that has to be "
                          "a plain number (it stands in for the value when "
                          "the measurement is not there)." % fill)
                out.append(Issue(
                    code="bad-let", level="error", node_id=None,
                    title="A 'let' line's missing-value fallback is not "
                          "a number",
                    detail="let line %d: %s" % (i + 1, advice),
                    advice=advice))
        scale = str(getattr(item, "scale", "") or "")
        if scale not in LET_SCALES:
            # 打錯的 scale 不能安靜地當成「照算」：那一行看起來在跟整批比,
            # 實際上每一顆還是自己的原始值 —— 跑得完、有數字、而且是錯的。
            advice = ("It says scale='%s'; the choices are '' (as "
                      "measured), 'z' (robust z against the batch) and "
                      "'percentile' (rank within the batch)." % scale)
            out.append(Issue(
                code="bad-let", level="error", node_id=None,
                title="A 'let' line has an unknown batch scaling",
                detail="let line %d: %s" % (i + 1, advice),
                suggest=closest(scale, LET_SCALES), advice=advice))
    for i, rule in enumerate(decide.rules):
        try:
            parse_expression(rule.when)
        except ExpressionError as e:
            out.append(Issue(
                code="bad-rule", level="error", node_id=None,
                title="Rule %d does not parse" % (i + 1), detail=str(e)))
    if str(decide.score or "").strip():
        try:
            parse_expression(decide.score)
        except ExpressionError as e:
            out.append(Issue(
                code="bad-rule", level="error", node_id=None,
                title="The decide block's score expression does not parse",
                detail=str(e)))
    out.extend(_outcome_issues(decide))
    return out


def _doubled_names(step_cls, params: Dict[str, Any]) -> List[str]:
    """這張卡會寫出哪些**同一個字連著出現兩次**的欄名（F117 F5）。

    `cells_cells_area_px` —— 一次是使用者填的 `output_prefix`，一次是這張卡
    自己給那個區域的名字。兩個都合法、兩個都是他打的，而疊起來的那個字誰都
    沒有打算要。

    ⚠ **只看相鄰的重複。** `epi_center_epi` 那種（同一個字隔開出現兩次）是
    另一回事：區域 `epi` 的 center 那半，跟一個叫 `epi` 的 output_prefix ——
    讀起來繞口，但它講的是兩件不同的事。這一支問的是「有沒有一個字白寫了」。

    ⚠ **只在使用者填了 `output_prefix` 的時候查。** 那一格是他唯一改得動的
    東西 —— 沒填的話這條 warning 給不出任何他做得到的動作，而一條沒有後果的
    提醒會把真的那一條一起教成雜訊（推廣鐵則）。
    """
    own = str(params.get("output_prefix", "") or "").strip()
    if not own:
        return []
    out: List[str] = []
    try:
        names = list(step_cls.resolve_features(params))
    except Exception:  # 卡片自己的程式；lint 不准比它守的東西更會壞
        return []
    for name in names:
        parts = str(name).split("_")
        if any(a == b for a, b in zip(parts, parts[1:])):
            out.append(str(name))
    return out


def _outcome_issues(decide: "DecideSpec") -> List["Issue"]:
    """「哪一類是好消息」標錯或標不一致（F119）。

    ⚠ **「還沒說」不是一條 lint。** 一份每個舊 recipe 都會亮的訊息會被學會
    忽略，而真的那一條也跟著被忽略（`_feature_collisions` 上面那段記過同一
    件事，而 `test_the_reference_recipes_stay_completely_clean` 鎖的正是
    「一條都沒有」—— 那些參考檔案就是沒標的）。「還沒說」講在它該講的地方：
    判定樹的托盤上，就在那一排膠囊旁邊（F119 第 4 步）。

    所以下面兩條**只在使用者真的標了東西的時候**才可能響。
    """
    out: List["Issue"] = []
    known = tuple(x for x in OUTCOMES if x)
    seen: Dict[int, Tuple[str, str]] = {}
    for b, label, outcome in decide.entries():
        text = outcome.strip()
        if not text:
            continue
        who = Q % label if label.strip() else "bin %d" % b
        if text not in known:
            advice = ("The choices are %s. That word is ignored, so this "
                      "class has no colour on the verdict chip."
                      % ", ".join("'%s'" % x for x in known))
            out.append(Issue(
                code="unknown-outcome", level="warning", node_id=None,
                title="A class says something nobody understands",
                detail="%s says outcome='%s'. %s" % (who, text, advice),
                names=(text,), suggest=closest(text, known), advice=advice))
            continue
        prev = seen.get(b)
        if prev is None:
            seen[b] = (text, label)
            continue
        if prev[0] != text:
            # **第一個贏**（同 `bin_labels`），所以要講出贏的是哪一個 ——
            # 不然使用者改了後面那一片，畫面上一點反應都沒有。
            advice = ("Two classes both write bin %d, and they disagree: "
                      "%s says '%s' and %s says '%s'. The first one wins, so "
                      "the second has no effect. Give them the same answer, "
                      "or a different bin." % (b, Q % prev[1] if prev[1].strip()
                                               else "the first one", prev[0],
                                               who, text))
            out.append(Issue(
                code="conflicting-outcome", level="warning", node_id=None,
                title="Two classes disagree about whether bin %d is good news"
                      % b,
                detail=advice, names=(prev[0], text), advice=advice))
    return out


def _decide_unknown(decide: "DecideSpec", feats: Set[str],
                    kind: str) -> List["Issue"]:
    """判定段的表達式指到**沒有人算得出來的數字**時講一句（F21-D 漏掉的那一半）。

    為什麼這一段一定要有
    --------------------
    `validate` 對舊的 ``score.expr`` 一直有這道檢查（``unknown-feature``），
    而 F21-D 加上 ``decide`` 之後，那一段變成「有 decide 就整個跳過」——
    理由是對的（有 decide 的時候 ``score.expr`` 根本不會跑），但**替代的檢查
    從來沒有補上**。於是打錯一個數字名字的下場是：

    * ``validate`` 全綠、畫布上一片正常；
    * 跑起來**每一顆都失敗**，訊息是 ``variable 'nosuch' is not available``。

    而 F25 把二元門檻的 UI 整個拿掉之後，``decide`` 是使用者唯一走得到的路
    —— 也就是說唯一有人用的那條路，lint 覆蓋比沒人用的那條還少。

    看得到哪些名字（順序是規格，不是實作細節）
    ------------------------------------------
    跟 `engine._eval_decision` 逐項對齊：

    * 卡片算出來的特徵（``feats``）；
    * ``score`` —— 判定段自己寫進 ``ctx.features`` 的那一個；
    * ``let`` 的名字，而且**是累加的**：第 n 行看得到前 n−1 行，看不到自己
      後面的（引擎就是照順序算的）；
    * 有 ``fill`` 的 let 會多寫一個 ``<名字>_missing``（F24 ⑤），
      有 ``scale`` 的會多留一個 ``<名字>_raw``（F23 期3）——
      判定樹的第一步常常問的就是 ``_missing``。

    ⚠ **級別是 warning 不是 error**，跟舊的那一條一致：一份 recipe 可以在
    「還沒接上那張量測卡」的中間狀態被打開，那時候擋住編輯比講一句更煩。
    """
    out: List[Issue] = []
    seen = set(feats) | {"score"}

    def check(where: str, text: str, fill: str = "", name: str = "") -> None:
        try:
            e = parse_expression(str(text))
        except ExpressionError:
            return                      # 語法錯已經由 `_decide_issues` 講過了
        unknown = sorted(e.variables - seen)
        if not unknown:
            return
        # **「missing ⇒ 用 __」的那幾行不會失敗** —— 而這句話以前照樣對它們
        # 講「every defect will fail on this line at run time」。那是**假的**，
        # 而且它剛好只在 `fill` 真的派上用場的時候出現：使用者寫這一行的意思
        # 正是「這個數字可能不在」。這支 lint 本來就看得見 `fill`（下面那個
        # 迴圈拿它來登記 `<name>_missing`），只是沒有拿來講話。
        if str(fill or ""):
            tail = ("That is not a failure here: this line says “missing ⇒ "
                    "use %s”, so a defect without that number gets %s and "
                    "“%s_missing = 1”. Add the card that measures it if you "
                    "did mean to measure it." % (fill, fill, name or "it"))
        else:
            tail = ("Check the spelling, or add the card that measures it - "
                    "every defect will fail on this line at run time.")
        out.append(Issue(
            code="unknown-feature", level="warning", node_id=None,
            title="The decision uses a number nobody produces",
            detail="route '%s': %s uses %s, but no card in this route "
                   "writes those out (available here: %s). %s"
                   % (kind, where, ", ".join(unknown),
                      ", ".join(sorted(seen)) or "none", tail),
            names=tuple(unknown), suggest=closest(unknown[0], seen),
            route=str(kind), advice="%s %s" % (where, tail)))

    for i, item in enumerate(decide.let):
        if item.is_blank:
            continue                      # 同 `_decide_issues`：空白行不存在
        name = str(item.name).strip()
        check("working number '%s'" % (name or "#%d" % i), item.expr,
              fill=str(getattr(item, "fill", "") or ""), name=name)
        # 第 i 行看得到前 i 行寫的（`let_names_written` 是唯一的家）。
        seen |= set(let_names_written(decide, upto=i + 1))

    if decide.tree is not None:
        for when in _tree_whens(decide.tree):
            check("the question \"%s\"" % when, when)
    else:
        for i, rule in enumerate(decide.rules):
            check("rule %d (\"%s\")" % (i + 1, rule.when), rule.when)

    if str(decide.score or "").strip():
        check("the score", decide.score)
    return out


def referenced_features(recipe: "Recipe") -> Set[str]:
    """判定段與分數表達式**讀了**哪些名字（F57）。

    「這個名字被誰讀」跟「這個名字被誰寫」是兩件事，而只有前者決定一次撞名
    痛不痛：兩張卡都寫 `glv_pixels` 而沒有人讀它，那是雜訊；兩張卡都寫
    `glv_max` **而判定樹正拿它問問題**，那是「這個答案取決於哪一張卡排在
    後面」，而使用者沒有辦法用那個名字表達他要哪一張。

    ⚠ **壞掉的表達式回空的，不 raise。** 語法錯有自己那條 lint
    （`score-expr` / `_decide_issues`），在這裡再炸一次只會讓一個打錯的括號
    連帶蓋掉別的檢查。
    """
    out: Set[str] = set()

    def add(text: Any) -> None:
        t = str(text or "").strip()
        if not t:
            return
        try:
            out.update(parse_expression(t).variables)
        except ExpressionError:
            pass                        # 語法錯有自己那條 lint

    decide = getattr(recipe, "decide", None)
    if decide is None:
        add(getattr(recipe.score, "expr", ""))
        return out
    for item in decide.let:
        if getattr(item, "is_blank", False):
            continue
        add(item.expr)
        add(getattr(item, "scale", ""))
    if decide.tree is not None:
        for when in _tree_whens(decide.tree):
            add(when)
    else:
        for rule in decide.rules:
            add(rule.when)
    add(decide.score)
    return out


def _param_diff_text(step_cls, pa: Dict[str, Any], pb: Dict[str, Any],
                     ka: str, kb: str) -> str:
    """兩張同型卡片差在哪幾格，一句白話（`routes-drift` 的 detail）。

    影像流／區域參數刻意不比（`_treatment_sig` 的同一個理由）：兩條 route
    各接各的流本來就不同，比它們的話這支 lint 對每一份分流 recipe 都叫 ——
    而「一支會誤報的 lint 比沒有 lint 更糟」（F11 Enhance-3）。
    """
    skip = {s.name for s in step_cls.params
            if s.type in ("image_key", "image_keys",
                          "region_key", "region_keys")}
    names = {s.name: (s.label or s.name) for s in step_cls.params}
    diff = sorted(n for n in set(pa) | set(pb)
                  if n not in skip and pa.get(n) != pb.get(n))
    return ", ".join(
        "%s is %s on route '%s' but %s on route '%s'"
        % (names.get(n, n), pa.get(n, "(unset)"), ka,
           pb.get(n, "(unset)"), kb)
        for n in diff[:3])


def _routes_drift_issues(recipe: "Recipe", kinds: List[str],
                         clean_params: Dict[str, Dict[str, Any]],
                         registry) -> List["Issue"]:
    """分流的兩條 route 用了**同一張卡、不同設定**時提個醒（F23 §5 選項 A）。

    這不是 error —— 「刻意不同」正是分流的目的。它存在的理由是選項 A 的
    風險本身：兩條幾乎一樣的 route，改了 A 路的卡忘了 B 路的，畫布一次只看
    一條所以**看不出來**。提示講出差在哪幾格，看一眼就分得出「這是我設計的」
    還是「這是我忘了的」。
    """
    out: List[Issue] = []
    per_route: Dict[str, Dict[str, List[str]]] = {}
    for k in kinds:
        by_step: Dict[str, List[str]] = {}
        for nid in recipe.routes.get(k, []):
            node = recipe.nodes.get(nid)
            if node is None or not node.enabled:
                continue
            by_step.setdefault(node.step, []).append(nid)
        per_route[k] = by_step
    ordered = list(kinds)
    for i, ka in enumerate(ordered):
        for kb in ordered[i + 1:]:
            shared = set(per_route[ka]) & set(per_route[kb])
            for step_key in sorted(shared):
                step_cls = registry.get(step_key)
                if step_cls is None:
                    continue
                for na in per_route[ka][step_key]:
                    for nb in per_route[kb][step_key]:
                        if na == nb:
                            continue    # 共用同一個節點＝同一組設定，沒得漂
                        pa = clean_params.get(na, {})
                        pb = clean_params.get(nb, {})
                        bits = _param_diff_text(step_cls, pa, pb, ka, kb)
                        if not bits:
                            continue
                        advice = ("%s on route '%s' and %s on route "
                                  "'%s', but %s. If that is deliberate, "
                                  "fine - this note is here so an edit on "
                                  "one side is not quietly forgotten on the "
                                  "other."
                                  % (Q % card_name(recipe.nodes, na), ka,
                                     Q % card_name(recipe.nodes, nb), kb,
                                     bits))
                        out.append(Issue(
                            code="routes-drift", level="warning", node_id=na,
                            title=("Two routes use %s with different settings"
                                   % (Q % getattr(step_cls, "label",
                                                  step_key))),
                            detail=advice, advice=advice))
                        break       # 一對 route 一張卡講一次就夠
                    else:
                        continue
                    break
    return out


def _route_by_issues(recipe: "Recipe", rb: "RouteBy") -> List["Issue"]:
    """``route_by`` 的健檢（F23 §4.1）。

    兩條 error 擋的是同一個形狀：**寫了一條沒有人走得到的路**。map 或 default
    指到不存在的 route，那幾顆會逐顆失敗 —— 而那是整批跑完才發現的最貴發現法。
    「欄位在不在這份 KLARF 裡」不在這裡查：validate 手上沒有資料集，那一條在
    CLI／Studio 開跑之前查（`missing_columns_of`）。
    """
    out: List[Issue] = []
    if not str(rb.column or "").strip():
        out.append(Issue(
            code="bad-route-by", level="error", node_id=None,
            title="route_by has no column",
            detail="route_by.column is empty - name the KLARF column whose "
                   "value picks the route (CLASSNUMBER is the usual one)."))
    if not rb.map:
        out.append(Issue(
            code="bad-route-by", level="error", node_id=None,
            title="route_by has an empty map",
            detail="route_by.map has no entries, so no defect can ever be "
                   "routed. Map at least one column value to a route."))
    targets = [str(v) for v in rb.map.values()]
    if str(rb.default or "").strip():
        targets.append(str(rb.default).strip())
    missing = sorted({t for t in targets if t not in recipe.routes})
    if missing:
        advice = ("Every defect sent there would fail. This recipe's "
                  "routes are %s."
                  % (", ".join("'%s'" % r for r in sorted(recipe.routes))
                     or "none"))
        out.append(Issue(
            code="bad-route-by", level="error", node_id=None,
            title="route_by points at a route that does not exist",
            detail="%s is not among this recipe's routes. %s"
                   % (", ".join("'%s'" % m for m in missing), advice),
            names=tuple(missing),
            suggest=closest(missing[0], recipe.routes), advice=advice))
    # 寫了但 route_by 指不到的 route：**永遠不會有人走**（route_by 存在時它
    # 覆蓋 kind 選路，§4.2），而寫了沒人走的路最容易爛。
    unreachable = sorted(set(recipe.routes) - set(targets))
    if unreachable:
        advice = ("With route_by present the route is picked per defect "
                  "from '%s' only, and nothing maps to them - so no defect "
                  "will ever run them." % rb.column)
        out.append(Issue(
            code="route-not-reachable", level="warning", node_id=None,
            title="Some routes can never be taken",
            detail="%s are defined but unreachable. %s"
                   % (", ".join("'%s'" % r for r in unreachable), advice),
            names=tuple(unreachable), advice=advice))
    return out


# ---------------------------------------------------------------------------
# lint 式驗證（KLIP Issue 風格：一次列出所有問題）
# ---------------------------------------------------------------------------
@dataclass
class Issue:
    """一條驗證發現：``level`` 為 "error"、"warning" 或 "info"。

    ``info``（PR-2）是「值得知道、但連 warning 都算不上」的那一級：畫布
    **不**為它畫徽章（只進卡片的 tooltip 與 CLI 的清單）、run 之前的提示
    也不攔 —— 一條常駐的 warning 會被學會忽略，而真的那一條也跟著被忽略
    （推廣鐵則）。
    """
    code: str
    level: str
    node_id: Optional[str]
    title: str
    detail: str

    # ---- 給畫面組句子用的欄位（F118）--------------------------------------
    #
    # ⚠ **全部選配，預設空** —— 48 個產地一個一個搬，中途不會半好半壞：
    # UI 有結構就用結構，沒有就退回 `detail`（`ui/wording.issue_line`）。
    #
    # 為什麼句子不在這裡組（F118 §3）：`detail` 現在寫的是
    # ``route 'ebi_patch': the variables ['nosuch_feature'] …`` —— 三個問題
    # 疊在一句話裡（引擎的詞、Python 的 repr、把整條 route 的特徵全列出來）。
    # 而其中一個**只有畫面答得出來**：「只有一條 route 的時候不要講 route」
    # 要知道使用者現在在看什麼，core 不知道。
    #
    # ⚠ **`detail` 不刪**：CLI（`d4t run` 的 lint 清單）與測試照舊拿得到一句
    # 完整的話，而那邊的讀者本來就接受 `route 'x'` 這種講法。
    #: 這條在講哪一格（參數名）—— 畫面會把它換成那一格上面寫的字。
    param: Optional[str] = None
    #: 句子裡要列出來的名字（**畫面決定怎麼排版**：引號、逗號、列幾個就夠）。
    names: Tuple[str, ...] = ()
    #: 「你是不是要打這個」——最接近的幾個（拼錯字時比列出全部有用得多）。
    suggest: Tuple[str, ...] = ()
    #: 哪一條 route。畫面**只在多於一條時**才講 —— 單 route 的 recipe 上
    #: 那個字只是雜訊。
    route: Optional[str] = None
    #: 那句「所以你該怎麼辦」。**`detail` 是把上面這些攤平成一句話的版本，
    #: 而這一段是它的尾巴** —— 兩邊共用同一個字串，所以話只寫一次。
    #:
    #: ⚠ 有結構的時候畫面**不接 `detail`**（接了就是把剛剛拆開的東西再貼
    #: 回去），只接這一段。
    #:
    #: ⚠ **句子裡提到別的卡時，卡片名在這裡就要是名字**（`card_name`）——
    #: 第 3 步試過讓畫面翻（一個 `nodes` 欄位），結果是「`“A”` 和 `“B”`」
    #: 這種**沒有動詞**的句子：那兩張卡之間是什麼關係，每一條 lint 都不一樣，
    #: 而通用的組句器造不出那個動詞。`Step.label` 本來就住在 core，所以這件事
    #: 在產地做又對又便宜；畫面留著的是**它才答得出來**的那兩件
    #: （幾條 route、列到第幾個）。
    advice: str = ""


#: 使用者面的名字在句子裡一律**加彎引號**。一個沒有引號的名字在一串英文中間
#: 分不出哪裡開始哪裡結束（``Adjust tone compares…`` 讀起來像半句話），而
#: 這個 repo 的畫面已經在用這一對（`ui/wording.py` 的 `name_list`）。
#: ⚠ 直引號 ``'x'`` 留給**使用者要打進去的字**（feature 名、node id）——
#: 兩種引號在同一句話裡是有分工的，不是兩種寫法。
Q = "“%s”"


def card_name(nodes: Any, nid: Any) -> str:
    """node id → 卡片庫上那張卡的名字（``dn`` → ``Denoise``）。

    ⚠ **這一支在 core，而且應該在 core**：`Step.label` 本來就住在
    `core.pipeline.step`，所以「那張卡叫什麼」core 自己答得出來 —— 而
    `detail` 的讀者（CLI、log、匯出的檔案）跟畫面一樣讀不懂 ``'dn'``。
    F118 §3 交給畫面的是**另外那兩件**：只有一條 route 就不要講 route，
    以及一串名字列到第幾個就夠 —— 那兩件 CLI 的答案跟畫面不一樣。

    認不得就回 node id 本身（同 `ui/wording.card`：**不要猜**）。
    """
    node = (nodes or {}).get(str(nid or ""))
    cls = REGISTRY.get(str(getattr(node, "step", "") or "")) if node else None
    return str(getattr(cls, "label", "") or "") or str(nid or "")


def closest(name: Any, pool: Any, n: int = 3) -> Tuple[str, ...]:
    """「你是不是要打這個」—— `pool` 裡最接近 `name` 的幾個。

    打錯一個字的時候，**列出全部**（走查那一句列了二十幾個）幫不上忙，而
    最接近的兩三個通常一眼就看得出來。放寬到 0.5 是故意的：預設的 0.6 對
    ``glv_max`` ↔ ``glv_mad`` 這種只差兩個字母的名字**答不出東西來**。
    """
    import difflib
    got = difflib.get_close_matches(str(name or ""), sorted(pool or ()),
                                    n=n, cutoff=0.5)
    return tuple(str(x) for x in got)


def _clean_params_for(step_cls: Type[Step], raw: Dict[str, Any],
                      issues: List[Issue], nid: str,
                      skew: str = "") -> Dict[str, Any]:
    """驗證參數；壞參數記 Issue 並改用預設值，讓後續模擬檢查照常進行。

    ``skew`` 有值時附在訊息後面 —— 「認不得這個參數」最常見的原因不是檔案壞了，
    是**這台的程式比較舊**（開發機與公司機是靠複製檔案同步的，見 AGENTS.md）。
    """
    try:
        return step_cls.validate_params(raw)
    except ParamError as e:
        detail = str(e)
        if skew:
            detail = "%s  %s" % (detail, skew)
        issues.append(Issue(
            code="bad-param", level="error", node_id=nid,
            title="Invalid parameter", detail=detail))
        try:
            return step_cls.validate_params(None)  # 全預設值
        except ParamError:  # pragma: no cover — 預設值本身壞掉屬程式錯誤
            return {}


def _feature_collisions(step_cls, p: Dict[str, Any], nid: str, k: str,
                        feat_owner: Dict[str, Any],
                        used: Optional[Set[str]] = None,
                        nodes: Optional[Dict[str, "RecipeNode"]] = None
                        ) -> List["Issue"]:
    """這張卡寫的特徵有沒有蓋掉別張卡的（就地更新 ``feat_owner``）。

    後面的卡會**安靜地**蓋掉前面的（``Context.add_feature`` 允許覆寫，只在 meta
    留紀錄）。最典型的踩法是「量兩個 ROI」—— 兩張 glv_stats 都寫 glv_mean，
    跑完只剩後面那張的值，而分數表達式完全沒有辦法指到前面那一個。

    F57 改了兩件事，而**級別一件都沒有改**
    --------------------------------------
    ① **句子看得見「有沒有人在讀這個名字」**（``used`` = 判定段與分數表達式
    讀到的名字，見 :func:`referenced_features`）。同樣一次撞名，
    「判定樹正拿 ``glv_max`` 問問題」跟「沒有人讀它」是兩種不同的處境，而以前
    那一句話對兩種**逐字相同** —— 它甚至在沒有人讀的時候也宣稱「``glv_max``
    在分數表達式裡指的是這張卡」。

    ② **被蓋掉的那一張卡也要講**（`feature-renamed`，`info`）。以前只有**後**
    面那張拿得到訊息，而畫面上真正說不通的是**前**面那張：它的
    ``glv_median`` 從此叫 ``a_glv_median``，而它自己那張卡上一個字都沒有。
    級別是 `info` 所以不畫第二顆琥珀點 —— 一次撞名畫兩顆點是把同一件事數成
    兩件（`canvas.badge_paints` 只畫 error 與 warning）。

    ⚠ **就算判定正在讀也不升成 error。** 判準寫在 :func:`_region_collisions`
    上：差別不是嚴重程度，是**有沒有第二條路拿得到被蓋掉的那一份**。特徵有
    （引擎救成 ``<節點名>_<特徵>``），區域沒有。擋掉一份跑得出數字、而且那個
    數字使用者換個名字就指得到的 recipe，比講一句更糟（推廣鐵則）。

    抽成函式是因為 F11 Input-0 之後**入口卡也要跑這一段** —— 兩張 load 卡都寫
    `n_channels`。同一段判斷抄兩份的話，總有一份會長歪（這個 repo 記過三次）。
    """
    out: List[Issue] = []
    used = used or set()
    diag = set(step_cls.diagnostic_features(p))
    for f in step_cls.resolve_features(p):
        prev = feat_owner.get(f)
        owner, owner_diag = (prev if isinstance(prev, tuple) else (prev, False))
        if owner is None or owner == nid:
            feat_owner.setdefault(f, (nid, f in diag))
            continue
        # **兩邊都是診斷數字就不講**（F11 Enhance-3，F57 量過之後保留）：
        # `clip_frac` 是每一張 Enhance 卡都會產出的，所以兩張 Enhance 卡必然
        # 撞名 —— 在每一份正常的 recipe 上都出現的訊息會被學會忽略，而真的
        # 那一條也一起被忽略。值沒有丟（engine 救成 `<節點名>_clip_frac`）。
        #
        # ⚠ F57 想過把它降成 `info`（「不畫琥珀點，但寫下來」），**而那是錯
        # 的**：`info` 一樣進卡片的 tooltip，而且
        # `test_the_reference_recipes_stay_completely_clean` 鎖的是**一條都
        # 沒有**。「每一份正常的 recipe 都乾淨」是一個有人選過的不變量，
        # 換成「每一份都有兩行不痛不癢的話」就是把它丟掉。
        if f in diag and owner_diag:
            feat_owner[f] = (nid, True)
            continue
        # ⚠ **這裡講的是「那張卡」而 `%s_%s` 裡的是 node id**（`owner`）：
        # 救回來的那個名字**真的**叫 `<node id>_<特徵>`（`engine` 就是那樣
        # 命名的），所以它不能換成卡片名 —— 換了使用者照著打就指不到。
        # 卡片名講「是哪一張」，node id 講「要打什麼字」，兩個都要在。
        who, mine = Q % card_name(nodes, owner), Q % card_name(nodes, nid)
        # 兩張**同型別**的卡是這條 lint 最常見的形狀（量兩個 ROI 的 glv_stats）
        # —— 而那時候兩個名字一模一樣，印成「“GLV” first, then “GLV”」等於沒講。
        #
        # ⚠ **只有句子裡改口，`title` 不改**：標題要回答「是哪一張卡」，而
        # 「this one overwrites…」在狀態列上是一句沒有主詞的話（真的跑出來
        # 過）。句子裡可以說「這一張」，因為前面剛講完另一張是誰。
        first, second = who, mine
        if who == mine:
            first, second = "another %s card" % who, "this one"
        rescued = "%s_%s" % (owner, f)
        if f in used:
            advice = ("The decision reads %s, and two cards write it - %s "
                      "first, then %s. The later one wins, so the decision "
                      "is reading this card's value. Say which one you mean: "
                      "type '%s' for the first one, and '%s' means the "
                      "second. Or give one of the two a different output "
                      "name." % (Q % f, first, second, rescued, f))
        else:
            advice = ("%s already produces %s, and the later card wins - so "
                      "a plain '%s' anywhere means this card's value, and "
                      "the first one's is called '%s'. Nothing reads it at "
                      "the moment; give one of the two a different output "
                      "name if that is clearer." % (first, Q % f, f, rescued))
        out.append(Issue(
            code="feature-collision", level="warning", node_id=nid,
            title=("%s overwrites the number %s" % (mine, Q % f)),
            detail="route '%s': %s" % (k, advice),
            names=(str(f),), route=str(k), advice=advice))
        # 被蓋掉的那一張也要知道它的數字改叫什麼了（見上面的說明）。
        # ⚠ 這一條掛在**前面那張**卡上（`node_id=owner`），所以「哪一張是
        # 別人」的方向跟上面那一句相反 —— 上面的 `second`（"this one"）在這裡
        # 指的會是錯的那一張。
        later = ("another %s card" % mine) if who == mine else mine
        renamed = ("%s also writes %s and runs later, so it keeps the plain "
                   "name. This card's value is still measured - it is called "
                   "'%s' in the results, in the CSV, and in the decision."
                   % (later[0].upper() + later[1:], Q % f, rescued))
        out.append(Issue(
            code="feature-renamed", level="info", node_id=owner,
            title=("%s now writes '%s' as '%s'" % (who, f, rescued)),
            detail="route '%s': %s" % (k, renamed),
            names=(str(f),), route=str(k), advice=renamed))
        feat_owner[f] = (nid, f in diag)
    return out


def _region_collisions(step_cls, p: Dict[str, Any], nid: str, k: str,
                       region_owner: Dict[str, str],
                       nodes: Optional[Dict[str, "RecipeNode"]] = None
                       ) -> List["Issue"]:
    """這張卡定義的具名區域有沒有跟同一條 route 上別張卡撞名（就地更新表）。

    **這一條是 error，而特徵撞名（:func:`_feature_collisions`）只是 warning。**
    差別不是嚴重程度，是「有沒有第二條路拿得到被蓋掉的那一份」：特徵被蓋掉時
    引擎會把前一份救成 ``<節點名>_<特徵>``，所以那句話是「你可能不是故意的」；
    ``Context.set_roi`` **同名直接覆寫**，沒有救援，前一張卡畫的框就是不見了。

    真正逼它變成 error 的是**線**（F42 方案 B）：區域依賴從此存進
    ``recipe.edges``，而一條線指著一個特定的節點。名字唯一的時候
    「線指的那張卡」＝「引擎真的給的那個框」恆成立；名字撞了就不是 ——
    畫布會指著第一張，引擎會給第二張的框。那正是這個 repo 記過六次的
    「跑得完、有數字、而且是錯的」，而擋掉撞名就讓引擎一行都不用改
    （身分模型不動，見 F42 計畫書 §2）。

    只看 ``resolve_regions_out``（**這張卡真的定義了什麼**）。畫布上那種
    「接進來、原樣送出去」的區域埠不算 —— 它送出去的是別人的框，不是第二份
    定義（`viewmodel.region_outputs` 才是那一份，而它刻意跟這裡分家：
    F12 §7-①「副標仍然只印真的產出什麼」）。

    ``_center`` / ``_others`` 不必特別處理：它們本來就在
    ``resolve_regions_out`` 的回傳裡（`_util.region_family` 是唯一那一份），
    所以兩張都吐 ``epi`` 的 Region 卡在這裡撞的是三個名字，不是一個。
    """
    out: List[Issue] = []
    for name in step_cls.resolve_regions_out(p):
        if not name:
            continue
        owner = region_owner.get(name)
        if owner is not None and owner != nid:
            # ⚠ **名字只講一次**：`title` 已經說了是哪一個區域名，而這一段
            # 接在畫面那句話的後面（`issue_line` 的前面已經有 `names`）——
            # 再講一次就是同一個字在同一行出現三次。
            #
            # ⚠ 這裡是**卡片名不是 node id**，而兩張卡可能同名（兩張 Profile
            # 正是最常見的撞法）。那不是退步：`node_id` 指著後面那張，使用者
            # 點清單就選到它；另一張在畫布上有一條線指著。用 `'b'` 那種字
            # 他一樣找不到，而且還看不懂。
            advice = ("“%s” already defines a region with this name. The "
                      "later card's box replaces the earlier one, so every "
                      "card that measures it quietly gets this card's box - "
                      "and the canvas still draws the line to that other "
                      "card. Give one of the two a different region name."
                      % card_name(nodes, owner))
            out.append(Issue(
                code="duplicate-region", level="error", node_id=nid,
                title=("two cards both define the region “%s”" % name),
                detail=f"route '{k}': the region is “{name}”. {advice}",
                names=(str(name),), route=str(k), advice=advice))
        else:
            region_owner.setdefault(name, nid)
    return out


# --------------------------------------------------------------------------- #
# 兩支「跑得完、有數字、而且是錯的」的 lint（F11 Enhance-3）
# --------------------------------------------------------------------------- #
def _treatment_sig(step_cls, p: Dict[str, Any]):
    """這張卡對一條流做的處理的「指紋」（**不含接線**）。

    影像流參數（`image_key` / `image_keys`）刻意不算進去：一張接 test、一張接 ref
    的兩張 Normalize，差別就只在那裡，而「兩條流有沒有受到同樣的處理」問的正是
    **設定**是否相同。把接線算進去的話，兩張卡永遠不相等，這支 lint 就永遠在叫。
    """
    skip = {s.name for s in step_cls.params
            if s.type in ("image_key", "image_keys")}
    return (step_cls.key,
            tuple(sorted((str(k), str(v)) for k, v in p.items()
                         if k not in skip)))


def _late_normalize(step_cls, p: Dict[str, Any], nid: str, k: str,
                    history: Dict[str, List[Any]]) -> List[Issue]:
    """自動正規化排在手動調色**之後**（F11 Enhance-3）。

    `tone.py` 的 docstring 早就寫了這條：「手動那張通常放在正規化之後，
    否則正規化會把你剛調的東西再拉回去」——但**沒有任何人檢查它**，
    而它的後果是「畫面上看起來調了、實際上被拉回去了」：跑得完、有數字、
    而且使用者的那一步完全沒有作用。

    只認這一組（`tone` → `normalize`），不去猜其他順序：一支會誤報的 lint
    比沒有 lint 更糟（使用者學會忽略它之後，真的那一條也被忽略了）。
    """
    if step_cls.key != "normalize":
        return []
    out: List[Issue] = []
    for key in step_cls.stream_list(p) if hasattr(step_cls, "stream_list") else []:
        earlier = [c for c in history.get(key, []) if c[0] == "tone"]
        if not earlier:
            continue
        advice = ("It goes through Adjust tone and then through this "
                  "Normalize, which measures the image again and stretches "
                  "it - so the brightness / gamma set by hand upstream is "
                  "pulled back and has no effect on what gets measured. Put "
                  "the manual card after the automatic one.")
        out.append(Issue(
            code="card-order", level="warning", node_id=nid,
            title="This Normalize undoes the manual tone adjustment before it",
            detail="route '%s': %s %s" % (k, Q % key, advice),
            names=(str(key),), route=str(k), advice=advice))
        break               # 一張卡一條訊息就夠（每條流各講一次是噪音）
    return out


def _chart_metric_issues(recipe: "Recipe", step_cls, p: Dict[str, Any],
                         nid: str, k: str, registry) -> List["Issue"]:
    """`Write charts` 要畫的統計量，上游真的有量嗎（F86）。

    使用者打成 ``glv_mena`` 的下場是**四張圖全空，而且沒有任何訊息** ——
    那一格是自由文字，而 d4t 對「指名上游東西」的欄位向來是有型別的
    （``image_key`` / ``region_key`` / ``feature_key``）。它不是特徵名（是統計量
    id），所以套不上那幾種型別，也就落在既有的 ``stale-feature-ref`` 之外。

    為什麼這一支住在 `recipe.py` 而不是卡片上：`configuration_issues` 只看得到
    **這張卡自己**的參數，而這個問題的答案在**別的節點**上（上游 Gray level 的
    ``Statistics``）。同一條路上的 `_late_normalize` / `_uneven_treatment` 也是
    這個形狀。

    兩種都是 **warning**：卡片照樣跑得完、資料夾照樣出得來，只是裡面的圖是空的。
    """
    if step_cls.key != "output_uniformity":
        return []
    metric = str(p.get("metric", "") or "").strip()
    if not metric:
        return []       # 空的 = 「用上游量的第一個」，那是合法而且是預設
    # **這條 route 上的每一張 GLV 卡都算數，不看先後**：問的是「有沒有人量
    # 這個統計量」，而順序那件事已經有 `execution_order` 在管。第一版寫了
    # `for other in order: if other == nid: break`，而 `Recipe` 根本沒有
    # `route()` —— 於是那個迴圈一次都沒跑，正常的 recipe 也被報一句話。
    have: List[str] = []
    each_box = False
    for other in list(recipe.routes.get(k, []) or []):
        if other == nid:
            continue
        node = recipe.nodes.get(other)
        if node is None or not getattr(node, "enabled", True):
            continue
        if node.step != "glv_stats":
            continue
        cls2 = registry.get("glv_stats")
        if cls2 is None:
            continue
        try:
            q = cls2.validate_params(dict(node.params))
        except Exception:  # lint 不准當機
            q = dict(node.params)
        if str(q.get("across_boxes", "")) == "each box":
            each_box = True
        have.extend(x.strip() for x in
                    str(q.get("metrics", "") or "").split(",") if x.strip())
    if not each_box:
        advice = ("Every one of these charts is one point per measurement "
                  "box, and no Gray level card upstream is set to “each "
                  "box”. This card will run and write nothing. Set the Gray "
                  "level card to “each box” (its “Odd box out” preset does "
                  "it) and tick something under “How even are the boxes”.")
        return [Issue(
            code="charts-need-each-box", level="warning", node_id=nid,
            title=(Q % card_name(recipe.nodes, nid)
                   + " has no box-by-box numbers to draw"),
            detail="route '%s': %s" % (k, advice),
            route=str(k), advice=advice)]
    if metric not in have:
        advice = ("The Gray level card upstream measures %s instead, so "
                  "the charts would come out empty. Fix the spelling, or "
                  "tick '%s' under Statistics on that card."
                  % (", ".join(sorted(set(have))) or "nothing", metric))
        return [Issue(
            code="unknown-chart-metric", level="warning", node_id=nid,
            title=(Q % card_name(recipe.nodes, nid)
                   + " plots a statistic nobody measured"),
            detail="route '%s': “Which number to plot” is '%s'. %s"
                   % (k, metric, advice),
            param="metric", names=(str(metric),),
            suggest=closest(metric, set(have)), route=str(k), advice=advice)]
    return []


def _content_written(step_cls, p: Dict[str, Any]) -> Dict[str, str]:
    """這張卡寫出去的每一條流**裝的是什麼**（``{流名: "gray"|"label"}``）。

    只有明著宣告 ``content`` 的輸出格會說出不一樣的答案；其餘一律灰階。
    一張卡把 label map 讀進來又寫出去（今天沒有這種卡）不會自動保留 label ——
    宣告不推導，跟 `ParamSpec.direction` 同一個理由。
    """
    out: Dict[str, str] = {}
    for spec in step_cls.params:
        what = spec.content_written()
        if not what:
            continue
        raw = str(p.get(spec.name, "") or "").strip()
        for v in ([x.strip() for x in raw.split(",")]
                  if spec.type.endswith("s") else [raw]):
            if v:
                out[v] = what
    return out


def _wrong_content(step_cls, p: Dict[str, Any], nid: str, k: str,
                   content: Dict[str, str],
                   nodes: Optional[Dict[str, "RecipeNode"]] = None
                   ) -> List[Issue]:
    """一條 label map 接進了一格只收灰階的輸入（F110）。

    **今天這條線完全合法，而三層都沒擋。** label map 的像素值*就是*層號
    （0 = 背景、1..N = 第 N 個 POI 層），所以正規化它、拉對比、平滑它 ——
    三件事都跑得完、都不報錯，而 1、2、3 被混成 1.7 這種不存在的層號之後，
    下游的每一個區域都是錯的。`steps/load_sidecar.py` 的模組說明逐字寫著這件事，
    但在這一輪之前那句話只是一句話。

    error 級而不是 warning：這不是「你可能不想這樣做」，是**下游拿到的東西
    一定是錯的**，而且錯得看不出來。
    """
    bad: List[Issue] = []
    for spec in step_cls.params:
        if not spec.is_image_input():
            continue
        raw = str(p.get(spec.name, "") or "").strip()
        vals = ([x.strip() for x in raw.split(",")]
                if spec.type.endswith("s") else [raw])
        for v in vals:
            what = content.get(v, "")
            if not v or not what or spec.accepts(what):
                continue
            advice = ("Send the label map straight to the Region card "
                      "instead.")
            bad.append(Issue(
                code="wrong-content", level="error", node_id=nid,
                title=("“%s” is being fed a layout label map"
                       % card_name(nodes, nid)),
                detail=(
                    "route '%s': '%s' is a label map - every pixel value in it "
                    "IS a layer number, not a brightness. “%s” on this card "
                    "works on pictures, and running it on layer numbers "
                    "blends 1, 2 and 3 into values like 1.7 that are not any "
                    "layer at all. It would not fail; every region after it "
                    "would just be wrong. %s"
                    % (k, v, spec.label or spec.name, advice)),
                param=str(spec.name), names=(str(v),), route=str(k),
                advice=advice))
    return bad


def _uneven_treatment(step_cls, p: Dict[str, Any], nid: str, k: str,
                      history: Dict[str, List[Any]],
                      from_input: Set[str], registry,
                      nodes: Optional[Dict[str, "RecipeNode"]] = None
                      ) -> List[Issue]:
    """兩條要互相比較的流受到**不同的**處理（F11 Enhance-3）。

    最典型：test 接了 Normalize，ref 沒接。兩張圖各自都好看，但它們已經不在同一個
    灰階尺度上 —— 而 `subtract` 減出來的整片偏移看起來就是一個大面積的缺陷。
    F7-19 之後正確的寫法是**一張卡接兩條流**（同一組設定），所以這句話要講得出
    那條路。

    只在**兩條流都直接來自輸入**時才檢查：`diff` 這種中途產生的流跟 `test` 比
    「處理歷史」沒有意義（它們的來歷本來就不同）。
    """
    if step_cls.resolve_group() != GROUP_COMPARE:
        return []
    keys, seen = [], set()
    for spec in step_cls.input_specs():
        raw = str(p.get(spec.name, "") or "").strip()
        # ⚠ **複數的輸入格要拆開**（F109）：`align` 的 `streams` 是 `image_keys`，
        # 值長得像 ``"test,ref"`` —— 整串去比對 `from_input` 永遠不會中，於是這條
        # lint 對它一聲都不吭。這裡拆開之後，任何「一格吃好幾條流」的 Compare 卡
        # 都回到這條檢查底下。
        vals = ([x.strip() for x in raw.split(",")]
                if spec.type in IMAGE_TYPES and spec.type.endswith("s") else [raw])
        for v in vals:
            if v and v in from_input and v not in seen:
                seen.add(v)
                keys.append(v)
    if len(keys) < 2:
        return []
    a, b = keys[0], keys[1]
    ha, hb = history.get(a, []), history.get(b, [])
    if ha == hb:
        return []
    advice = ("%s. The two images are on different gray scales now, so "
              "this card reports that difference as if it were a defect. "
              "Point ONE Enhance card at both streams (a card can process "
              "several streams with the same settings) instead of one card "
              "per stream." % _how_they_differ(a, ha, b, hb, registry))
    return [Issue(
        code="uneven-treatment", level="warning", node_id=nid,
        title=("%s compares two images that were not treated alike"
               % (Q % card_name(nodes, nid))),
        detail="route '%s': %s" % (k, advice),
        names=(str(a), str(b)), route=str(k), advice=advice)]


def _how_they_differ(a: str, ha: List[Any], b: str, hb: List[Any],
                     registry) -> str:
    """兩條流的處理歷史**差在哪裡**，一句白話。

    分兩種情況，因為它們的下一步完全不同：卡片不一樣是「漏了一張」，
    設定不一樣是「兩張卡調歪了」。以前這兩種擠在同一句話裡，於是「同樣的卡、
    不同的參數」會印成「'test' 經過 Normalize，而 'ref' 經過 Normalize」——
    一句自我矛盾的話（實際的兩張卡差在 p_low 是 2 還是 10）。
    """
    def label_of(key: str) -> str:
        cls = registry.get(key)
        return getattr(cls, "label", key) if cls else key

    la = [label_of(key) for key, _ in ha]
    lb = [label_of(key) for key, _ in hb]
    if la != lb:
        return ("'%s' went through %s, but '%s' went through %s"
                % (a, ", ".join(la) or "nothing", b, ", ".join(lb) or "nothing"))

    # 同樣的卡、同樣的順序 —— 那就是某一張的設定不一樣。指出第一張與差哪幾格。
    for (key, sa), (_kb, sb) in zip(ha, hb):
        if sa == sb:
            continue
        da, db = dict(sa), dict(sb)
        cls = registry.get(key)
        names = {s.name: (s.label or s.name) for s in getattr(cls, "params", [])}
        diff = sorted(n for n in set(da) | set(db) if da.get(n) != db.get(n))
        bits = ", ".join("%s is %s for '%s' but %s for '%s'"
                         % (names.get(n, n), da.get(n, "(unset)"), a,
                            db.get(n, "(unset)"), b)
                         for n in diff[:3])
        return ("both '%s' and '%s' went through %s, but with different "
                "settings (%s)" % (a, b, label_of(key), bits))
    return ("'%s' and '%s' were treated differently upstream" % (a, b))


def validate(recipe: Recipe, kind: Optional[str] = None,
             registry: Optional[Dict[str, Type[Step]]] = None) -> List[Issue]:
    """lint 式驗證：收集**所有**問題後一次回傳（不會 raise）。

    檢查項（code）：unknown-step / bad-param / not-configured（error）/
    half-configured（warning）/ unknown-node /
    unknown-route / cycle / missing-image / unknown-region /
    duplicate-region（error）/ region-edge-no-port（warning）/
    region-has-no-line（warning）/ port-not-produced（warning）/
    requires-ref /
    ambiguous-input / score-expr / unknown-feature（warning）/
    stale-feature-ref（warning）/ feature-collision（warning）/ bad-bins /
    uneven-treatment（warning）/ card-order（warning）/
    feature-renamed（info，F57：被蓋掉的那一張卡也要知道它的數字改叫什麼）/
    port-not-produced（warning），加上各卡
    `Step.kind_issues` 宣告的 kind 條件項（PR-2；GLV 的
    center-on-big-image（warning）/ each-box-on-patch（info））。
    """
    from .recipe import execution_order  # 延遲：見檔頭
    if registry is None:
        registry = REGISTRY
    issues: List[Issue] = []

    # ---- 判定段（F21-D）：兩種寫法只能有一種 ----
    #
    # **這一段要排在 score 的檢查之前**：有 `decide` 的時候整個 score 區塊都
    # 不會跑（`_eval_score` 的第一行就分了岔），下面兩道檢查因此要跳過它。
    decide = getattr(recipe, "decide", None)
    if decide is not None:
        issues.extend(_decide_issues(recipe, decide))

    # ---- 分流（F23）：map/default 指到的 route 要存在 ----
    route_by = getattr(recipe, "route_by", None)
    if route_by is not None:
        issues.extend(_route_by_issues(recipe, route_by))

    # ---- bins 必須含 below / above ----（有 decide 就整段跳過，見上）
    if decide is None:
        bins = recipe.score.bins or {}
        for key in ("below", "above"):
            if key not in bins:
                advice = ("Both a below and an above bin value are "
                          "required; this recipe only sets %s."
                          % (", ".join("'%s'" % b for b in sorted(bins))
                             or "neither"))
                issues.append(Issue(
                    code="bad-bins", level="error", node_id=None,
                    title="Incomplete bin settings",
                    detail="score.bins has no '%s'. %s" % (key, advice),
                    names=(str(key),), advice=advice))

    # ---- 要檢查哪些 route ----
    #
    # ``route_by`` 存在時它**覆蓋 kind 選路**（F23 §4.2）：route 鍵是任意字串
    # （``particle_route``），dataset kind 本來就不該在 routes 裡 —— 對它報
    # `unknown-route` 等於「recipe 是對的，但健檢說它壞了」。所以這時一律檢查
    # **全部** route（每一條都可能被某個 class 走到）。
    if route_by is not None:
        kinds = list(recipe.routes)
    elif kind is not None:
        if kind not in recipe.routes:
            advice = ("This recipe only defines %s."
                      % (", ".join("'%s'" % r for r in sorted(recipe.routes))
                         or "no routes at all"))
            issues.append(Issue(
                code="unknown-route", level="error", node_id=None,
                title=f"Unknown input-type route '{kind}'",
                detail=advice, names=(str(kind),),
                suggest=closest(kind, recipe.routes), advice=advice))
            kinds: List[str] = []
        else:
            kinds = [kind]
    else:
        kinds = list(recipe.routes)

    # ---- 每個節點：step 存在？參數合法？----
    # 認不得的參數 / 認不得的卡片，最常見的原因是**這台的程式比較舊**。
    skew = version_skew(getattr(recipe, "app_version", ""))
    clean_params: Dict[str, Dict[str, Any]] = {}
    for nid, node in recipe.nodes.items():
        step_cls = registry.get(node.step)
        if step_cls is None:
            # ⚠ **step key 原樣，不翻**（`ui/wording` 同一條規矩）：認不得的
            # key 本身就是線索，而這條 lint 正是「這台的程式比較舊」最常見的
            # 長相 —— 換成一個猜出來的漂亮名字會把線索蓋掉。
            advice = ("This card is not in the card library. "
                      + (skew or "Check the spelling, or open this recipe on "
                                 "a machine that has that card."))
            issues.append(Issue(
                code="unknown-step", level="error", node_id=nid,
                title=f"Unknown card '{node.step}'",
                detail=("the card '%s' is not in the card library. "
                        "Available: %s."
                        % (node.step, ", ".join(sorted(registry)))
                        + ("  %s" % skew if skew else "")),
                # ⚠ **`names` 不填**：`title` 已經把那個 key 講了一次，
                # 而畫面的定位前綴（卡片名）認不得它的時候回的也是同一個字
                # —— 填了就變成「“glv_statz” · “glv_statz”」。
                suggest=closest(node.step, registry), advice=advice))
            continue
        clean_params[nid] = _clean_params_for(step_cls, node.params, issues,
                                              nid, skew)

        # 參數全部合法，卡片還是可能**沒設定完**（F7-13）。空字串的模板是完全
        # 合法的 str —— 但那張卡跑起來每一顆都會失敗，而以前要跑過一次才知道。
        try:
            unset = list(step_cls.configuration_issues(clean_params[nid]))
        except Exception:  # 卡片自己的程式
            unset = []
        for msg in unset:
            issues.append(Issue(
                code="not-configured", level="error", node_id=nid,
                title=f"{step_cls.label} is not set up yet", detail=str(msg)))

        # **跑得起來、但八成不是他要的**（F35）—— warning，不擋 CLI。
        # 分成兩支而不是在同一支上加一個級別欄位：級別是**呼叫端**的事
        # （lint 決定怎麼呈現），而卡片要回答的是一個它自己答得出來的問題
        # 「這會不會跑不起來」。見 `Step.configuration_hints`。
        try:
            hints = list(step_cls.configuration_hints(clean_params[nid]))
        except Exception:  # 卡片自己的程式
            hints = []
        for msg in hints:
            issues.append(Issue(
                code="half-configured", level="warning", node_id=nid,
                title=f"{step_cls.label} will run, but check this",
                detail=str(msg)))

        # **同一個字連著出現兩次**（F117 F5）。出貨的均勻度 recipe 寫出來的
        # 欄名是 `cells_cells_area_px` —— 一次是 `output_prefix`，一次是這張
        # 卡自己給那個區域的名字。
        #
        # ⚠ **不改組名字的規則**（「遇到同名不疊」）。那條規則改一個字，全
        # repo 的特徵名就換一批：分數表達式要遷移、黃金值要重錄，而換來的是
        # 一個**看不見的**行為（下一個人讀 `full_prefix` 不會知道有這回事）。
        # 一條講得出後果的 warning 便宜得多，而且它擋得住**每一張卡**，不只
        # 被走查點到的那一張。
        for name in _doubled_names(step_cls, clean_params[nid]):
            issues.append(Issue(
                code="doubled-prefix", level="warning", node_id=nid,
                param="output_prefix", names=(name,),
                title="This card repeats a word in its column names",
                advice=("Clear the name you put in front of the results, or "
                        "use a different one - this card already puts the "
                        "region's name there."),
                detail=("node '%s': the column %r repeats a word; clear "
                        "'output_prefix' or pick a different one"
                        % (nid, name))))

    # ---- 區域線的來源埠要填（F42 B1）----
    # 方案 B 之後區域線跟影像線住在同一個 ``edges`` 裡，而它們**兩個埠的分工
    # 不一樣**：``dst_in`` 說「落在哪一格」（沒有它連是不是區域線都判不出來，
    # 見 :func:`is_region_edge`），``src_out`` 說「是哪一個區域」。
    #
    # ``src_out`` 空著的區域線**仍然排得出順序**（`execution_order` 只看
    # src/dst），所以它跑得完 —— 它只是沒有講出量的是哪一塊。那正是這裡要
    # 出聲的理由：畫布上看得到一條接好的線，而那張卡實際上退回量整張圖。
    # warning 不是 error：真正「那一格是空的」由 `not-connected` / 卡片自己的
    # `configuration_issues` 講，這一條講的是**線本身沒講完**。
    for e in recipe.edges:
        if e.src_out or not is_region_edge(e, recipe.nodes, registry):
            continue
        step_cls = registry.get(recipe.nodes[e.dst].step)
        labels = {sp.name: (sp.label or sp.name) for sp in step_cls.params}
        src_name = Q % card_name(recipe.nodes, e.src)
        advice = ("The line from %s lands on it, but it does not name a "
                  "region - so this card does not know which one to use. "
                  "Drag the line again from the region port (the diamond) "
                  "on %s that has the name you want." % (src_name, src_name))
        issues.append(Issue(
            code="region-edge-no-port", level="warning", node_id=e.dst,
            title=("the region line into %s does not say which region"
                   % (Q % card_name(recipe.nodes, e.dst))),
            detail="“%s”: %s" % (labels.get(e.dst_in, e.dst_in), advice),
            param=str(e.dst_in), advice=advice))

    # ---- 線的**來源埠**要真的存在（F55）----
    #
    # 「那張卡有哪些輸出埠」的定義**不是 `resolve_writes`**，是
    # **`writes` ＋ 原樣送出的 `reads`**（F9-6「同進同出」，區域同理見
    # `RecipeModel.region_outputs`）。引擎那邊本來就成立：跑一張卡的 local
    # Context 是用它的**輸入**種出來的，跑完整份收成
    # ``produced[(節點, 名字)]``，所以輸入本來就在裡面送得出去
    # （`engine._run_nodes`）。
    #
    # ⚠ **這一段第一版就是踩在這裡。** 它拿 `resolve_writes` 當那張表，於是
    # 對一條完全正確的線報錯：`roi_reference` 的 `writes` 是空的（它只產出
    # 區域），但它 `reads` 了 `ref`，所以畫布上它右邊**真的有**一顆 `ref` 埠，
    # 而從那顆埠拉出去的線是「經過這張卡的那條 ref」—— 那是這個畫布刻意提供
    # 的寫法（不然量測卡就是一條死路，第二張要用同一條流的卡只能回頭橫跨整張
    # 畫布去接）。
    #
    # **教訓**：要問「畫布有沒有說謊」，那就得用**畫布的**定義去問，不是用
    # 引擎某一支宣告的定義。兩邊的差別正好是這一條 lint 要守的東西本身。
    #
    # 剩下要擋的是真的不存在的埠 —— 手改過的 JSON、改名之後沒跟上的線：
    # 執行期會安靜地退回「名字對得上的那張圖」（`Context` 照名字查），
    # 跑得完、有數字，而畫布上那條線指著錯的卡。
    #
    # 為什麼是 warning 不是 error：結果通常仍然是對的，擋掉一份跑得出正確
    # 數字的 recipe 比讓它跑更糟（推廣鐵則）。它要說的是「把線重拉一次」。
    #
    # ⚠ **三種線不算**：埠空著的（只表達先後順序，見 :class:`Edge`）、
    # ``dst_in`` 指到的參數不是影像／區域的、以及**來源卡還沒接上東西的**
    # （那張卡在畫布上前後都是空的，而 `not-connected` 已經在講那件事了）。
    for e in recipe.edges:
        if not (e.src_out and e.dst_in):
            continue
        src_node = recipe.nodes.get(e.src)
        dst_node = recipe.nodes.get(e.dst)
        if src_node is None or dst_node is None or not src_node.enabled:
            continue
        src_cls = registry.get(src_node.step)
        dst_cls = registry.get(dst_node.step)
        if src_cls is None or dst_cls is None:
            continue                            # 已記 unknown-step
        want = {sp.name: sp.type for sp in dst_cls.params}.get(e.dst_in, "")
        sp = clean_params.get(e.src, {})
        if src_cls.missing_inputs(sp):
            continue                            # 已記 not-connected
        if want in REGION_TYPES:
            produced = (set(src_cls.resolve_regions_out(sp))
                        | set(src_cls.resolve_regions_in(sp)))
            what, a_what, port = "region", "a region", "diamond"
        elif want in IMAGE_TYPES:
            # **kind 相依的宣告要取聯集**：load 卡會依資料型別決定產出哪幾條
            # 流，而這一段不在 per-route 的迴圈裡。取聯集是保守的方向 ——
            # 寧可漏報一條，也不要對一份在別條 route 上完全正確的線報錯。
            produced = set(src_cls.resolve_reads(sp))       # 原樣送出的
            for k in kinds:
                produced |= set(src_cls.resolve_writes_for_kind(sp, k))
            if not kinds:
                produced |= set(src_cls.resolve_writes(sp))
            what, a_what, port = "image stream", "an image stream", "dot"
        else:
            continue
        if e.src_out in produced:
            continue
        has = ("it has %s" % ", ".join("“%s”" % n for n in sorted(produced))
               if produced else "it has none at all")
        src_name = Q % card_name(recipe.nodes, e.src)
        advice = ("The line says it comes from %s, but that card has no such "
                  "%s on its right-hand side (%s). It still runs — the "
                  "engine looks %s up by its name alone, so this card gets "
                  "whichever card really made it — but the canvas is "
                  "pointing at the wrong one. Drag the line again from the "
                  "%s on the card that really has it."
                  % (src_name, what, has, a_what, port))
        issues.append(Issue(
            code="port-not-produced", level="warning", node_id=e.dst,
            title=("the line into %s comes from a port %s does not have"
                   % (Q % card_name(recipe.nodes, e.dst), src_name)),
            detail="“%s”: %s" % (e.src_out, advice),
            names=(str(e.src_out),), advice=advice))

    # ---- 一個輸入埠只能有一條線（F9-7）----
    # 引擎查資料從哪來的 key 是 ``(下游節點, 流名)``，所以兩條線落在同一個 key
    # 上時只有一條算數 —— 而**贏的是 ``edges`` 裡排在後面的那條**，那個順序在
    # 畫布上完全看不出來。跑得完、有數字、而且其中一條使用者畫的線是裝飾。
    # 典型踩法：舊版 Studio 加卡時會自動接一條線，使用者接著自己拉一條進同一
    # 張卡，於是同一個輸入有兩個來源。
    seen_inputs: Dict[Tuple[str, str], str] = {}
    for e in recipe.edges:
        if not (e.src_out and e.dst_in):
            continue                            # 沒填埠的線只表達先後順序
        node = recipe.nodes.get(e.dst)
        step_cls = registry.get(node.step) if node is not None else None
        if step_cls is None:
            continue
        ptype = {str(p["name"]): str(p["type"])
                 for p in step_cls.describe()["params"]}.get(e.dst_in, "")
        if ptype == "image_keys":
            local = e.src_out
        elif ptype == "image_key":
            local = str(clean_params.get(e.dst, {}).get(e.dst_in, "") or "")
        else:
            continue
        if not local:
            continue
        prev = seen_inputs.get((e.dst, local))
        if prev is not None and prev != e.src:
            advice = ("“%s” and “%s” both feed this input. Only one of "
                      "them is used (the later one wins), so the other line "
                      "does nothing. Delete the line you do not want."
                      % (card_name(recipe.nodes, prev),
                         card_name(recipe.nodes, e.src)))
            issues.append(Issue(
                code="ambiguous-input", level="error", node_id=e.dst,
                title=("“%s” has two lines into the same input"
                       % card_name(recipe.nodes, e.dst)),
                detail=f"route '{k}': {advice}",
                param=str(e.dst_in), advice=advice))
        else:
            seen_inputs[(e.dst, local)] = e.src

    # ---- score 表達式解析 ----
    #
    # ⚠ 有 `decide` 的時候**整個 score 區塊都不會跑**（`_eval_score` 的第一行
    # 就分了岔），所以它連解析都不該解析：一份走多類別的 recipe 的 score.expr
    # 是空字串，而空字串解析不出來 —— 對它報一條 error 等於「recipe 是對的，
    # 但健檢說它壞了」，而使用者只會相信健檢。
    expr = None
    if decide is None:
        try:
            expr = parse_expression(recipe.score.expr)
        except ExpressionError as e:
            issues.append(Issue(
                code="score-expr", level="error", node_id=None,
                title="Score expression failed to parse", detail=str(e)))

    # 判定段與分數表達式**讀了**哪些名字（F57）。撞名分級要看這一份 ——
    # 一次撞名痛不痛，取決於有沒有人在讀那個名字，不取決於直覺。
    # 一份算一次（它跟 route 無關），而不是每張卡算一次。
    used_features = referenced_features(recipe)

    # ---- 每條 route：unknown-node / cycle / reads 模擬 / requires_ref ----
    for k in kinds:
        route = recipe.routes[k]
        for nid in route:
            if nid not in recipe.nodes:
                advice = ("This route lists a card that is not in the "
                          "recipe at all - the file has been hand-edited, or "
                          "an edit was only half saved. Remove it from the "
                          "route, or add the card back.")
                # ⚠ **這一條真的要印 node id**，而它是唯一一條：那張卡
                # 根本不在 `recipe.nodes` 裡，所以沒有卡片名可以翻 ——
                # 使用者要拿這個字去 JSON 裡找出是哪一行。寫成 `%` 是
                # 刻意的（`tests/test_ui_wording.py` 擋的是把 id **插進
                # f-string 句子**那種，不是這種）。
                issues.append(Issue(
                    code="unknown-node", level="error", node_id=nid,
                    title="route '%s' refers to a step that does not exist: "
                          "'%s'" % (k, nid),
                    detail="nodes has no '%s'. %s Defined: %s."
                           % (nid, advice,
                              ", ".join("'%s'" % x for x in
                                        sorted(recipe.nodes)) or "nothing"),
                    names=(str(nid),), route=str(k), advice=advice))
        try:
            order = execution_order(recipe, k)
        except RecipeError as e:
            issues.append(Issue(
                code="cycle", level="error", node_id=None,
                title=f"route '{k}' has a cycle in its step connections",
                detail=str(e), route=str(k), advice=str(e)))
            continue

        # reads-satisfaction 模擬：seed = 第一張啟用卡（load 卡）的 writes；
        # 之後每張卡 reads 必須 ⊆ 累積 writes。停用節點跳過（與 runtime 一致）。
        avail: Set[str] = set()
        feats: Set[str] = {"score"}
        regions: Set[str] = set()
        #: feature 名 -> (第一個產出它的節點, 那是不是一個診斷數字)。
        #: 特徵是**扁平的全域命名空間**，所以兩張同型別的量測卡（例如量兩個 ROI
        #: 的 glv_stats）會寫同一組名字，後面那張安靜地蓋掉前面那張 ——
        #: 跑得完、有數字、少一半。診斷數字那一半見 `Step.diagnostic_features`。
        feat_owner: Dict[str, Any] = {}
        #: 區域名 -> 第一個定義它的節點。特徵那張表是 warning 級的「誰蓋掉誰」，
        #: 這一張是 error 級的「不准有第二個」—— 理由見 `_region_collisions`。
        #: **一條 route 一張表**：兩條 route 各有一張 Region 卡叫 `epi` 是常態
        #: （`ebi_patch` 與 `rsem` 各走各的），它們永遠不會在同一次執行裡碰面。
        region_owner: Dict[str, str] = {}
        #: 每一條流被哪幾張 Enhance 卡動過（照順序）。兩支 lint 都讀它 ——
        #: 「兩條流受到一樣的處理嗎」與「自動的排在手動的後面嗎」問的都是這段歷史。
        history: Dict[str, List[Any]] = {}
        #: 直接來自輸入卡的那幾條流。`diff` 這種中途產生的流不算 ——
        #: 拿它跟 `test` 比「處理歷史」沒有意義（來歷本來就不同）。
        from_input: Set[str] = set()
        #: 每一條流**裝的是什麼**（F110）。跟 `history` 同一個形狀、同一個
        #: 迴圈餵：來源是產出那一格的 `content` 宣告，沿著線傳下去。
        content: Dict[str, str] = {}
        for nid in order:
            node = recipe.nodes.get(nid)
            if node is None or not node.enabled:
                continue
            step_cls = registry.get(node.step)
            if step_cls is None:
                continue  # 已記 unknown-step
            p = clean_params.get(nid, {})
            if step_cls.is_source():
                # **入口卡**（沒有輸入埠 —— 見 Step.is_source）：reads /
                # requires_ref 不檢查，因為它的資料不是從別張卡來的。
                # 一份 recipe 可以有好幾張，每一張都拿 kind-aware 的 writes
                # 宣告（load 卡依資料型別決定會有哪些流）。
                avail |= set(step_cls.resolve_writes_for_kind(p, k))
                from_input |= set(step_cls.resolve_writes_for_kind(p, k))
                # **撞名檢查對入口卡也要跑**（F11 Input-0）。以前這一段沒有它，
                # 因為「入口」只有一張所以撞不起來 —— 現在兩張 load 卡都寫
                # n_channels，後面那張會安靜地蓋掉前面那張。
                issues.extend(_feature_collisions(step_cls, p, nid, k,
                                                  feat_owner, used_features,
                                                  recipe.nodes))
                issues.extend(_region_collisions(step_cls, p, nid, k,
                                                 region_owner, recipe.nodes))
                feats |= set(step_cls.resolve_features(p))
                regions |= set(step_cls.resolve_regions_out(p))
                # ⚠ 內容型別的**唯一來源是入口卡**（`load_sidecar` 就是一張
                # 入口卡），所以這一行非在 `continue` 之前不可。
                content.update(_content_written(step_cls, p))
                continue
            # **還沒接上來源**（F10）。這一條要排在 missing-image 前面，
            # 而且擋掉後面所有以「這張卡會產出什麼」為前提的檢查 ——
            # 一張沒有來源的卡什麼都不產出，拿它去比對下游只會生出一串
            # 指不到重點的錯誤（真正該講的只有一句：這張卡還沒有接上東西）。
            not_connected = step_cls.missing_inputs(p)
            if not_connected:
                labels = {s.name: (s.label or s.name) for s in step_cls.params}
                advice = ("Drag a line from the card that produces the "
                          "image into this one.")
                issues.append(Issue(
                    code="not-connected", level="error", node_id=nid,
                    title=("“%s” has no input yet"
                           % card_name(recipe.nodes, nid)),
                    detail=("route '%s': %s — %s Available upstream: %s"
                            % (k, ", ".join("“%s” is empty" % labels[n]
                                            for n in not_connected),
                               advice,
                               ", ".join(sorted(avail)) or "(nothing yet)")),
                    # ⚠ 這裡的 `names` 已經是**欄位上寫的字**（`labels`）而不是
                    # 參數名 —— `ParamSpec.label` 本來就住在 core。畫面只負責
                    # 排版（列到第幾個就夠），不再翻一次。
                    names=tuple(labels[n] for n in not_connected),
                    route=str(k), advice=advice)
                )
                continue
            missing = [x for x in step_cls.resolve_reads(p) if x not in avail]
            if missing:
                advice = ("Nothing upstream produces it. Drag a line from "
                          "the card that does, or change which stream this "
                          "card reads.")
                issues.append(Issue(
                    code="missing-image", level="error", node_id=nid,
                    title=("“%s” is missing an upstream image"
                           % card_name(recipe.nodes, nid)),
                    detail="route '%s': it needs %s, but upstream only "
                           "provides %s. %s"
                           % (k, ", ".join(missing),
                              ", ".join(sorted(avail)) or "nothing", advice),
                    names=tuple(missing),
                    suggest=closest(missing[0], avail),
                    route=str(k), advice=advice))
            if k == "rsem" and step_cls.resolve_requires_ref(p) \
                    and "ref" not in avail:
                advice = ("On this route one defect is one image, so "
                          "there is no reference to compare against - add a "
                          "card upstream that produces one (Golden cell, or "
                          "a second lot through the Pair card).")
                issues.append(Issue(
                    code="requires-ref", level="error", node_id=nid,
                    title=("“%s” needs a reference image"
                           % card_name(recipe.nodes, nid)),
                    detail="route '%s': %s Currently provided: %s."
                           % (k, advice, ", ".join(sorted(avail)) or "nothing"),
                    route=str(k), advice=advice))
            # 具名區域走跟影像流一樣的檢查（F7-9）。沒有這一段的話，
            # 「量測卡指到沒人定義的區域」在跑之前是看不出來的 ——
            # 名字打錯要等執行期 StepError，而上游那張 Region 卡被拿掉更慘：
            # 它會安靜地退回量整張圖，跑得完、有數字、且是錯的。
            missing_roi = [x for x in step_cls.resolve_regions_in(p)
                           if x not in regions]
            if missing_roi:
                advice = ("No upstream card defines it. Add a Region card "
                          "upstream and drag a line from its diamond port "
                          "into this one; cut the line to measure the whole "
                          "image instead.")
                issues.append(Issue(
                    code="unknown-region", level="error", node_id=nid,
                    title=("“%s” uses a region nobody defines"
                           % card_name(recipe.nodes, nid)),
                    detail="route '%s': it measures %s. %s Currently "
                           "defined: %s."
                           % (k, ", ".join(missing_roi), advice,
                              ", ".join(sorted(regions)) or "nothing"),
                    names=tuple(missing_roi),
                    suggest=closest(missing_roi[0], regions),
                    route=str(k), advice=advice))
            # **有名字、卻沒有線**（F42 B3）。B2 之後那一格的值是線推出來的，
            # 所以這個狀態只剩兩種來歷，而上面那一條只講得出其中一種：
            #
            # * 指到一個沒有人定義的名字 → `unknown-region`（上面，error）；
            # * 產出它的那張卡**在**，但那條線補不上去 —— 補了會成環
            #   （`_migrate_region_params_into_edges` 的第 ④ 種）。
            #
            # 第二種今天跑得動（順序由影像線決定），所以是 warning 不是 error。
            # 但它不能安靜：畫布上兩張卡看起來互不相干，而其中一張真的在量
            # 另一張畫的框 —— 那正是 F12 一開始要修的那句「畫布不能說謊」。
            wired = {e.dst_in for e in recipe.edges
                     if e.dst == nid and e.src_out
                     and is_region_edge(e, recipe.nodes, registry)}
            for spec in step_cls.region_input_specs():
                value = str(p.get(spec.name, "") or "")
                if not value or spec.name in wired:
                    continue
                known = [x for x in
                         (y.strip() for y in value.split(",")) if x in regions]
                if not known:
                    continue           # 沒有人定義它 —— 上面那一條已經講了
                advice = ("An upstream card does define it, but there is "
                          "no line on the canvas between them - so two cards "
                          "that depend on each other look unrelated. That "
                          "usually means the line could not be drawn without "
                          "making the pipeline loop back on itself (a Region "
                          "card feeding an image into the very card that "
                          "defines its regions). It still runs - the order "
                          "comes from the image lines - but check that the "
                          "two cards really are meant to depend on each "
                          "other that way.")
                issues.append(Issue(
                    code="region-has-no-line", level="warning", node_id=nid,
                    title=("“%s” measures a region with no line to say where "
                           "it comes from" % card_name(recipe.nodes, nid)),
                    detail="route '%s': “%s” is set to %s. %s"
                           % (k, spec.label or spec.name, value, advice),
                    param=str(spec.name), names=tuple(known),
                    route=str(k), advice=advice))

            # 只在某種資料型別上成立的發現（PR-2）—— 判準在卡片上
            # （`Step.kind_issues`）：`configuration_issues` 看不到 kind，
            # 而「這組設定對不對」有時取決於一顆 defect 拿到的是置中的
            # patch 還是一張大圖。
            for code, level, title, detail in step_cls.kind_issues(p, str(k)):
                # 句子是卡片寫的（它才知道 patch 與一張大圖差在哪），所以這裡
                # 只補**畫面自己答得出來的那一件**：單 route 就不要講 route。
                issues.append(Issue(
                    code=str(code), level=str(level), node_id=nid,
                    title=str(title),
                    detail="route '%s': %s" % (k, detail),
                    route=str(k), advice=str(detail)))

            # 吃**特徵**的卡（F16，Algo 段）：指到一個沒人算出來的數字，在跑
            # 之前就講。沒有這一段的話它要等**每一顆 defect 都失敗**才看得出來
            # —— 跟具名區域當初的處境一字不差（F7-9 的 unknown-region）。
            # 「少了只會退化，不會失敗」那一半（F37）—— 見
            # `Step.optional_features_in`。**warning，不是 error**：出圖卡的
            # `rank_by` 指到一個沒人算出來的數字時它照樣寫得出圖，只是順序
            # 安靜地退回檔案順序。這一條同時是改名的安全網：量測卡多接一條
            # 區域線會把它寫的每一個名字都改掉，而指著舊名字的地方不會跟著改。
            # **整批一次的卡看得到 working numbers**（2026-09-09）：它們在每
            # 一顆判定完之後才跑，`let` 的名字那時候真的在每一列的 features
            # 裡。逐顆的卡不行 —— 判定在它們之後才算。
            known = feats if step_cls.scale != SCALE_LOT else \
                feats | set(let_names_written(recipe.decide))
            stale = [x for x in step_cls.optional_features_in(p)
                     if x not in known]
            if stale:
                advice = ("Nothing upstream produces it. This card still "
                          "runs - it just quietly does without - so check "
                          "the spelling, or whether a card upstream renamed "
                          "its numbers (measuring two regions instead of one "
                          "puts the region's name in front of every number "
                          "it writes).")
                issues.append(Issue(
                    code="stale-feature-ref", level="warning", node_id=nid,
                    title=("“%s” points at a number nobody produces"
                           % card_name(recipe.nodes, nid)),
                    detail="route '%s': it refers to %s. %s Available: %s."
                           % (k, ", ".join(stale), advice,
                              ", ".join(sorted(known)) or "none"),
                    names=tuple(stale), suggest=closest(stale[0], known),
                    route=str(k), advice=advice))

            missing_feat = [x for x in step_cls.resolve_features_in(p)
                            if x not in known]
            if missing_feat:
                advice = ("No card before it in this route writes that "
                          "out. Check the spelling, or move this card after "
                          "the card that measures it.")
                issues.append(Issue(
                    code="unknown-feature-input", level="error", node_id=nid,
                    title=("“%s” uses a number nobody produces"
                           % card_name(recipe.nodes, nid)),
                    detail="route '%s': it reads %s. %s Available here: %s."
                           % (k, ", ".join(missing_feat), advice,
                              ", ".join(sorted(known)) or "none"),
                    names=tuple(missing_feat),
                    suggest=closest(missing_feat[0], known),
                    route=str(k), advice=advice))

            # **整批一次的卡是 end point**（F17-④）。使用者 2026-08-20 定調
            # Output 段「他就是個 end point」，而在此之前那件事只是「這幾張卡
            # 的 resolve_writes 剛好是空的」—— 一份手寫的 recipe 照樣可以從它
            # 拉一條線出去，而那條線**永遠不會有資料**：整批那一層是在所有結果
            # 收齊之後才跑的，它下游的逐顆卡早就跑完了。
            #
            # 症狀是「畫布上有一條線，但下游那張卡什麼都沒收到」——
            # 跑得完、有數字、而且跟畫布上畫的東西沒有關係。
            if step_cls.scale == SCALE_LOT:
                downstream = sorted({e.dst for e in recipe.edges
                                     if e.src == nid and e.dst in set(order)})
                if downstream:
                    after = tuple(card_name(recipe.nodes, d)
                                  for d in downstream)
                    advice = ("%s %s input from it, but it only runs once "
                              "every defect has already been through the "
                              "pipeline — those cards would never receive "
                              "anything. Remove the connection."
                              % (" and ".join(Q % a for a in after),
                                 "take" if len(after) > 1 else "takes"))
                    issues.append(Issue(
                        code="batch-card-has-downstream", level="error",
                        node_id=nid,
                        title=("“%s” runs once for the whole lot, so nothing "
                               "can come after it"
                               % card_name(recipe.nodes, nid)),
                        detail="route '%s': %s" % (k, advice),
                        names=after, route=str(k), advice=advice))

            issues.extend(_feature_collisions(step_cls, p, nid, k,
                                              feat_owner, used_features,
                                              recipe.nodes))
            # 順序那一支看的是**這張卡之前**的歷史，所以要排在記錄之前。
            issues.extend(_late_normalize(step_cls, p, nid, k, history))
            issues.extend(_uneven_treatment(step_cls, p, nid, k, history,
                                            from_input, registry,
                                            recipe.nodes))
            # 問的是**這張卡吃進來的**，所以排在它自己的宣告記進去之前。
            issues.extend(_wrong_content(step_cls, p, nid, k, content,
                                         recipe.nodes))
            content.update(_content_written(step_cls, p))
            issues.extend(_chart_metric_issues(recipe, step_cls, p, nid, k,
                                               registry))
            if step_cls.resolve_group() == GROUP_ENHANCE:
                sig = _treatment_sig(step_cls, p)
                for key in step_cls.resolve_writes(p):
                    history.setdefault(key, []).append(sig)

            issues.extend(_region_collisions(step_cls, p, nid, k,
                                             region_owner, recipe.nodes))
            avail |= set(step_cls.resolve_writes(p))
            feats |= set(step_cls.resolve_features(p))
            regions |= set(step_cls.resolve_regions_out(p))

        # score 變數 ⊆ 此 route 會產出的特徵 ∪ {"score"}（僅警告）
        # ⚠ 有 `decide` 的時候 `score.expr` **根本不會跑**，對它報一條警告等於
        # 叫使用者去修一個不影響結果的地方 —— 但**判定段自己的表達式要檢查**，
        # 那正是下面那一段（在此之前它整段不見了，見 :func:`_decide_unknown`）。
        if expr is not None and getattr(recipe, "decide", None) is None:
            unknown = sorted(expr.variables - feats)
            if unknown:
                advice = ("Check the spelling, or add the card that "
                          "measures it - the score may not be computable at "
                          "run time.")
                issues.append(Issue(
                    code="unknown-feature", level="warning", node_id=None,
                    title="The score uses a number nobody produces",
                    detail="route '%s': the score uses %s, but no card in this "
                           "route writes those out (available here: %s). %s"
                           % (k, ", ".join(unknown),
                              ", ".join(sorted(feats)) or "none", advice),
                    names=tuple(unknown), suggest=closest(unknown[0], feats),
                    route=str(k), advice=advice))
        decide = getattr(recipe, "decide", None)
        if decide is not None:
            issues.extend(_decide_unknown(decide, feats, k))

    # ---- 分流的 route 之間有沒有漂（F23 §5 選項 A 的配套）----
    # 只在 route_by 存在時看：多 route 在此之前的意思是「一種 kind 一條路」
    # （ebi_patch / rsem），兩條路的卡不同設定是常態，不是漂。
    if route_by is not None and len(kinds) > 1:
        issues.extend(_routes_drift_issues(recipe, kinds, clean_params,
                                           registry))

    return issues

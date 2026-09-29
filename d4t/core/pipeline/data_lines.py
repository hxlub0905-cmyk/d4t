# d4t 數字線與結果線 — authored 2026-09-29 (F123 期 2).
"""**數字線與結果線**：量測卡 → Decision → Output 的那兩種線（F123 期 2）。

使用者（2026-09-29）選了做法 B：Decision、Output 跟 Input 一樣是真的卡，線由
使用者拉。三個答案（`docs/history/plans/F123-decision-and-output-cards.md` §1）：

* **數字線必要** —— 判定樹只能問「有線接進 Decision 的那幾張卡」的數字；
* **Output 寫的是線上游的東西** —— 接 Decision 有類別，直接接量測卡沒有；
* 線的顏色照資料種類（期 4）。

線住在 ``recipe.edges``（一條線就是一條線，F42 B4）；是不是資料線由
`recipe_schema.is_data_edge` 判斷（下游那顆埠是它宣告的資料入埠）。這一支管
兩件事，兩件都**不動引擎算出來的任何一個數字**：

1. :func:`data_line_issues` —— lint。「數字線必要」由這裡守：Studio 與 CLI 在
   error 時都不跑，所以它真的是必要的；而引擎照舊把整張數字表給判定。
2. :func:`rows_for_output` —— 一張 Output 卡看得到哪幾欄。**判準是排除**：宣告
   上屬於「不在上游的卡」的數字拿掉，認不出是誰的留著 —— 列舉的話，一個宣告
   漏掉的數字會安靜地從報表上消失（這個 repo 最貴的那種失敗）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Type

from ..log import swallowed
from .recipe_schema import is_data_edge, upstream_of
from .step import DATA_PORTS, NUMBERS, REGISTRY, RESULTS, Step

__all__ = ["data_line_issues", "rows_for_output", "wired_into",
           "DECISION_KEY"]

#: Decision 卡的 key（`steps/decision.py`）。core 不 import steps（卡片是外掛），
#: 所以這裡寫字面值 —— `tests/test_data_lines.py` 對著 registry 比。
DECISION_KEY = "decision"

#: 引擎寫、但**不是判定寫**的那一個（分流走哪一條，F23）。其餘沒有卡的數字
#: （``score``、``decide_unanswered``、let）是判定的產物，上游沒有 Decision 就不寫。
_NOT_THE_DECISIONS = frozenset({"route_taken"})


def wired_into(recipe: Any, node_id: str) -> List[str]:
    """用 ``numbers`` 線直接接進 ``node_id`` 的卡（依線的順序、不重複）。"""
    out: List[str] = []
    for e in recipe.edges:
        if (e.dst == node_id and e.src_out == NUMBERS
                and is_data_edge(e, recipe.nodes) and e.src not in out):
            out.append(e.src)
    return out


def _owners(recipe: Any, kinds: Sequence[str],
            registry: Optional[Dict[str, Type[Step]]]) -> Dict[str, Set[str]]:
    """數字名 → 宣告它的卡（跨這幾條 route；``""`` = 引擎／判定）。"""
    from .verdict_features import bound_specs   # 延後：它 import recipe

    out: Dict[str, Set[str]] = {}
    for kind in kinds:
        try:
            specs = bound_specs(recipe, kind, registry)
        except Exception:  # 壞掉的 route 由 lint 講
            swallowed("data_lines._owners")
            continue
        for b in specs:
            out.setdefault(str(b.spec.name), set()).add(str(b.node_id or ""))
    return out


def rows_for_output(recipe: Any, node_id: str, rows: Sequence[Dict[str, Any]],
                    kinds: Sequence[str],
                    registry: Optional[Dict[str, Type[Step]]] = None,
                    ) -> Tuple[List[Dict[str, Any]], bool]:
    """一張 Output 卡看得到的結果表 → ``(rows, 有沒有類別)``。

    「上游」＝沿**所有**線往回走得到的卡（`recipe_schema.upstream_of`）。上游
    有一張啟用的 Decision 才有類別；沒有的話 ``score`` 與 ``bin`` 兩格是空的、
    判定自己算的數字也不寫。宣告上屬於不在上游的卡的數字拿掉；認不出是誰的
    （沒有人宣告）留著。
    """
    nodes = recipe.nodes
    up = upstream_of(node_id, recipe.edges)
    decided = any(n in nodes and nodes[n].step == DECISION_KEY and nodes[n].enabled
                  for n in up)
    drop: Set[str] = set()
    for name, owners in _owners(recipe, kinds, registry).items():
        cards = {o for o in owners if o}
        if cards and not (cards & up):
            drop.add(name)
        elif ("" in owners and not cards and not decided
              and name not in _NOT_THE_DECISIONS):
            drop.add(name)
    if decided and not drop:
        return list(rows), True
    out: List[Dict[str, Any]] = []
    for r in rows:
        r2 = dict(r)
        r2["features"] = {k: v for k, v in (r.get("features") or {}).items()
                          if k not in drop}
        if not decided:
            r2["score"], r2["bin"] = None, None
        out.append(r2)
    return out, decided


def data_line_issues(recipe: Any, kind: str, order: Sequence[str],
                     registry: Optional[Dict[str, Type[Step]]] = None,
                     ) -> List[Any]:
    """這條 route 上的數字線／結果線 lint（`recipe_validate.validate` 叫它）。"""
    from .recipe_validate import Issue, card_name, referenced_features

    reg = REGISTRY if registry is None else registry
    nodes = recipe.nodes
    in_route = set(order)
    issues: List[Any] = []

    def cls_of(nid: str) -> Optional[Type[Step]]:
        node = nodes.get(nid)
        return reg.get(node.step) if node is not None else None

    # ---- 1. 接錯的線 --------------------------------------------------------
    for e in recipe.edges:
        if e.src not in in_route or e.dst not in in_route:
            continue
        data = is_data_edge(e, nodes, reg)
        if not data and e.src_out not in DATA_PORTS:
            continue                      # 影像線與區域線不是這一支的事
        src_cls, dst_cls = cls_of(e.src), cls_of(e.dst)
        if src_cls is None or dst_cls is None:
            continue                      # unknown-step 另外講
        try:
            p = src_cls.validate_params(nodes[e.src].params)
            sends = src_cls.data_output(p)
            streams = set(src_cls.resolve_writes_for_kind(p, kind))
        except Exception:  # 參數壞了由 bad-param 講
            sends, streams = "", set()
        if not data and (e.src_out != sends or e.src_out in streams):
            continue                      # 一條剛好叫 numbers 的影像流
        why = ""
        if not data:
            why = ("%s is not an input for %s - numbers go into a Decision "
                   "or an Output card" % (e.dst_in or "(no port)",
                                           Q % card_name(nodes, e.dst)))
        elif e.src_out != sends:
            why = ("%s does not send %s" % (Q % card_name(nodes, e.src),
                                            e.src_out or "anything"))
        elif e.dst_in == NUMBERS and e.src_out != NUMBERS:
            why = ("a Decision takes numbers, not the results of another "
                   "decision")
        if why:
            advice = "Remove this line and draw it again from the right port."
            issues.append(Issue(
                code="data-port-mismatch", level="error", node_id=e.dst,
                title="A line goes into the wrong port",
                detail="route '%s': %s. %s" % (kind, why, advice),
                route=str(kind), advice=advice))

    # ---- 2. 判定問到的數字要有線（必要）--------------------------------------
    cards = [nid for nid in order if nid in nodes
             and nodes[nid].step == DECISION_KEY]
    decide_like = (getattr(recipe, "decide", None) is not None
                   or str(getattr(recipe.score, "expr", "") or "").strip())
    if cards and nodes[cards[0]].enabled:
        dec = cards[0]
        wired = set(wired_into(recipe, dec))
        owners = _owners(recipe, [kind], reg)
        missing: Dict[str, List[str]] = {}
        for name in sorted(referenced_features(recipe)):
            found = {o for o in owners.get(name, ()) if o}
            if found and not (found & wired):
                for o in sorted(found):
                    missing.setdefault(o, []).append(name)
        if missing:
            who = tuple(card_name(nodes, o) for o in missing)
            names = tuple(n for ns in missing.values() for n in ns)
            advice = ("Draw a line from the numbers port of %s into the "
                      "Decision card - the decision can only ask about "
                      "numbers that are wired into it."
                      % " and ".join(Q % w for w in who))
            issues.append(Issue(
                code="decision-not-wired", level="error", node_id=dec,
                title="The decision asks about numbers that are not wired in",
                detail="route '%s': it asks about %s. %s"
                       % (kind, ", ".join(names), advice),
                names=names, route=str(kind), advice=advice))
    elif decide_like and not cards and any(
            RESULTS in getattr(cls_of(n), "data_inputs", ()) for n in order):
        advice = ("Add the Decision card and wire it into the Output cards - "
                  "without it nothing writes the classes out.")
        issues.append(Issue(
            code="decide-without-card", level="warning", node_id=None,
            title="The decision is not on the canvas",
            detail="route '%s': this recipe decides, but has no Decision "
                   "card. %s" % (kind, advice),
            route=str(kind), advice=advice))

    # ---- 3. Output 卡：要有東西進來；寫類別的要有 Decision ------------------
    for nid in order:
        c = cls_of(nid)
        if c is None or RESULTS not in c.data_inputs or not nodes[nid].enabled:
            continue
        if not any(e.dst == nid for e in recipe.edges):
            advice = ("Draw a line into its results port - from the Decision "
                      "card for the classes, or from a measuring card for its "
                      "numbers alone.")
            issues.append(Issue(
                code="output-not-connected", level="error", node_id=nid,
                title="%s has nothing to write" % (Q % card_name(nodes, nid)),
                detail="route '%s': nothing is wired into it. %s"
                       % (kind, advice),
                route=str(kind), advice=advice))
            continue
        up = upstream_of(nid, recipe.edges)
        decided = any(u in nodes and nodes[u].step == DECISION_KEY
                      and nodes[u].enabled for u in up)
        issues.extend(_numbers_not_upstream(recipe, nid, c, kind, up, decided,
                                            reg))
        if getattr(c, "needs_decision", False):
            if not decided:
                advice = ("It writes each defect's class, so wire the "
                          "Decision card into it.")
                issues.append(Issue(
                    code="needs-decision", level="error", node_id=nid,
                    title="%s needs the classes"
                          % (Q % card_name(nodes, nid)),
                    detail="route '%s': there is no Decision upstream of it. "
                           "%s" % (kind, advice),
                    route=str(kind), advice=advice))
    return issues



def _numbers_not_upstream(recipe: Any, nid: str, c: Type[Step], kind: str,
                          up: Set[str], decided: bool,
                          reg: Dict[str, Type[Step]]) -> List[Any]:
    """Output 卡用**名字**吃的數字（排序、欄位、要畫的數字），產出它的卡不在
    這張卡上游（F123 期 3）。

    Output 寫的是線上游的東西（`rows_for_output`）—— 所以一格指著上游以外的
    數字，跑得完、資料夾出得來，只是**那一欄整排空白**，而空白的一欄跟「這一批
    真的量不到」長得一模一樣。warning：卡片照樣寫得出東西。
    """
    from .recipe_validate import Issue, card_name

    try:
        names = [str(n) for n in c.feature_names_in(
            c.validate_params(recipe.nodes[nid].params))]
    except Exception:  # 參數壞了由 bad-param 講
        return []
    owners = _owners(recipe, [kind], reg)
    away: List[str] = []
    who: List[str] = []
    for name in names:
        found = owners.get(name, set())
        cards = {o for o in found if o}
        if cards and not (cards & up):
            away.append(name)
            who.extend(card_name(recipe.nodes, o) for o in sorted(cards)
                       if card_name(recipe.nodes, o) not in who)
        elif "" in found and not cards and not decided \
                and name not in _NOT_THE_DECISIONS:
            away.append(name)
            if "Decision" not in who:
                who.append("Decision")
    if not away:
        return []
    advice = ("Wire %s into this card (its numbers port into the results "
              "port) - it only writes what is upstream of its lines, so that "
              "column would be empty." % " and ".join(Q % w for w in who))
    return [Issue(
        code="output-number-not-upstream", level="warning", node_id=nid,
        title="%s uses numbers from a card that is not wired into it"
              % (Q % card_name(recipe.nodes, nid)),
        detail="route '%s': it uses %s. %s" % (kind, ", ".join(away), advice),
        names=tuple(away), route=str(kind), advice=advice)]


Q = "“%s”"

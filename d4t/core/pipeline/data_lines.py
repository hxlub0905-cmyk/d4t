# d4t 數字線與結果線 — authored 2026-09-29 (F123 期 2); F124 2026-09-30.
"""**送去判定的線與送去寫出的線**：量測卡 → Decision → Output（F123 期 2、F124）。

F123 做法 B：Decision、Output 跟 Input 一樣是真的卡，線由使用者拉
（`docs/history/plans/F123-decision-and-output-cards.md`）。F124 改了規則
（`docs/plans/F124-measured-flow.md` §1，使用者 2026-09-29）：

* **線只講「流到哪裡」，不講「准你用哪些數字」。** 流過去的是整顆 defect ——
  判定問得到的是 Decision **上游**每一張卡的數字（`recipe_schema.upstream_of`），
  不是只有直接接進來的那幾張。問到一張沒流進來的卡：提醒＋接誰（warning，不擋）。
* **送去判定的埠只長在量測卡上**（`Step.measures`）；其餘卡順手記的數字跟著流。
* **Output 寫整張表**；上游有 Decision 才有類別。

線住在 ``recipe.edges``（一條線就是一條線，F42 B4）；是不是資料線由
`recipe_schema.is_data_edge` 判斷（下游那顆埠是它宣告的資料入埠）。這一支管
兩件事，兩件都**不動引擎算出來的任何一個數字**：

1. :func:`data_line_issues` —— lint。
2. :func:`rows_for_output` —— 一張 Output 卡寫出去的結果表（整張；沒有 Decision
   在上游時類別那兩格空著、判定自己算的數字不寫）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Type

from ..log import swallowed
from .recipe_schema import is_data_edge, upstream_of
from .step import DATA_PORTS, NUMBERS, REGISTRY, RESULTS, Step

__all__ = ["data_line_issues", "rows_for_output", "wired_into", "feeder",
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


def feeder(recipe: Any, owner: str,
           registry: Optional[Dict[str, Type[Step]]] = None) -> str:
    """要從哪一張卡拉線，``owner`` 記的數字才流得進 Decision／Output（F124）。

    ``owner`` 自己送得出數字（量測卡）就是它；不然沿**它往下游的線**找第一張
    送得出數字的卡（Normalize 記的 ``clip_frac`` 跟著圖流到 GLV，接 GLV 就到了）。
    找不到回 ``""``：那個數字在這份 recipe 裡沒有路可以流過去，一鍵接不起來。
    """
    reg = REGISTRY if registry is None else registry
    nodes = recipe.nodes

    def sends(nid: str) -> bool:
        node = nodes.get(nid)
        cls = reg.get(node.step) if node is not None else None
        if cls is None:
            return False
        try:
            return cls.data_output(cls.validate_params(node.params)) == NUMBERS
        except Exception:  # 參數壞了由 bad-param 講
            return False

    seen, todo = {owner}, [owner]
    while todo:
        nid = todo.pop(0)
        if sends(nid):
            return nid
        for e in recipe.edges:
            if e.src == nid and e.dst not in seen \
                    and not is_data_edge(e, nodes, reg):
                seen.add(e.dst)
                todo.append(e.dst)
    return ""


def _not_flowing(recipe: Any, dst: str, names: Sequence[str], kind: str,
                 reg: Dict[str, Type[Step]], decided: bool,
                 ) -> Dict[str, List[str]]:
    """``names`` 裡**沒有流進** ``dst`` 的：卡 id → 那張卡的數字。

    流進來＝產出它的卡在 ``dst`` 上游。判定自己寫的數字（``score``、let、
    ``decide_unanswered``，沒有卡）要上游有 Decision（``decided``）—— 沒有的話
    歸在 ``""`` 底下。認不出是誰的（沒有人宣告）不算：那是別的 lint 的事。
    """
    up = upstream_of(dst, recipe.edges)
    owners = _owners(recipe, [kind], reg)
    away: Dict[str, List[str]] = {}
    for name in names:
        found = owners.get(name, set())
        cards = {o for o in found if o}
        if cards and not (cards & up):
            for o in sorted(cards):
                away.setdefault(o, []).append(name)
        elif ("" in found and not cards and not decided
              and name not in _NOT_THE_DECISIONS):
            away.setdefault("", []).append(name)
    return away


def rows_for_output(recipe: Any, node_id: str, rows: Sequence[Dict[str, Any]],
                    kinds: Sequence[str],
                    registry: Optional[Dict[str, Type[Step]]] = None,
                    ) -> Tuple[List[Dict[str, Any]], bool]:
    """一張 Output 卡寫出去的結果表 → ``(rows, 有沒有類別)``。

    **整張表**（F124）：線講的是流到哪裡，不是准寫哪幾欄。上游（沿**所有**線往回
    走，`recipe_schema.upstream_of`）有一張啟用的 Decision 才有類別；沒有的話
    ``score`` 與 ``bin`` 兩格是空的、判定自己算的數字也不寫。

    ⚠ F123 的版本是「只寫上游卡片的數字」（排除式）。F124 起量測卡以外的卡沒有
    送出去的埠，照那個判準一張量測卡接進來、它上游那幾張卡以外的數字全被排掉
    —— 報表會安靜地少欄。
    """
    nodes = recipe.nodes
    up = upstream_of(node_id, recipe.edges)
    decided = any(n in nodes and nodes[n].step == DECISION_KEY and nodes[n].enabled
                  for n in up)
    if decided:
        return list(rows), True
    drop = {name for name, owners in _owners(recipe, kinds, registry).items()
            if "" in owners and not {o for o in owners if o}
            and name not in _NOT_THE_DECISIONS}
    out: List[Dict[str, Any]] = []
    for r in rows:
        r2 = dict(r)
        r2["features"] = {k: v for k, v in (r.get("features") or {}).items()
                          if k not in drop}
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

    # ---- 2. 判定問到的數字要流得進來（提醒，不擋；F124）------------------------
    cards = [nid for nid in order if nid in nodes
             and nodes[nid].step == DECISION_KEY]
    decide_like = (getattr(recipe, "decide", None) is not None
                   or str(getattr(recipe.score, "expr", "") or "").strip())
    if cards and nodes[cards[0]].enabled:
        dec = cards[0]
        away = _not_flowing(recipe, dec, sorted(referenced_features(recipe)),
                            kind, reg, decided=True)
        if away:
            issues.append(_not_flowing_issue(
                recipe, "decision-not-wired", dec, away, kind, reg,
                title="The decision asks about numbers that do not flow into it",
                where="the Decision card"))
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

    # ---- 3. Output 卡：要有東西流進來；寫類別的要有 Decision --------------------
    # 「流得進來的東西」：一張 Decision，或一張送得出數字的量測卡。一份只有影像
    # 卡的 recipe（整理圖片的 DOE）沒有任何東西接得進 Output —— 那時候講「沒接」
    # 是一條修不好的紅字（推廣鐵則），所以不講。
    can_feed = any(
        cls_of(n) is not None and (
            nodes[n].step == DECISION_KEY or feeder(recipe, n, reg) == n)
        for n in order if nodes.get(n) is not None and nodes[n].enabled)
    for nid in order:
        c = cls_of(nid)
        if c is None or RESULTS not in c.data_inputs or not nodes[nid].enabled:
            continue
        # 任何一條線都算（Write comparison 的左圖右圖也是流進來的東西）。
        if not any(e.dst == nid for e in recipe.edges):
            if not can_feed:
                continue
            advice = ("Draw a line into it - from the Decision card for the "
                      "classes, or from a measuring card for its numbers "
                      "alone.")
            issues.append(Issue(
                code="output-not-connected", level="error", node_id=nid,
                title="Nothing flows into %s" % (Q % card_name(nodes, nid)),
                detail="route '%s': nothing is wired into it. %s"
                       % (kind, advice),
                route=str(kind), advice=advice))
            continue
        up = upstream_of(nid, recipe.edges)
        decided = any(u in nodes and nodes[u].step == DECISION_KEY
                      and nodes[u].enabled for u in up)
        issues.extend(_numbers_not_upstream(recipe, nid, c, kind, decided, reg))
        if getattr(c, "needs_decision", False):
            if not decided:
                advice = ("It writes each defect's class, so wire the "
                          "Decision card into it.")
                dec_ids = tuple(n for n in cards if nodes[n].enabled)
                issues.append(Issue(
                    code="needs-decision", level="error", node_id=nid,
                    title="%s needs the classes"
                          % (Q % card_name(nodes, nid)),
                    detail="route '%s': there is no Decision upstream of it. "
                           "%s" % (kind, advice),
                    route=str(kind), advice=advice, connect=dec_ids[:1]))
    return issues


def _not_flowing_issue(recipe: Any, code: str, dst: str,
                       away: Dict[str, List[str]], kind: str,
                       reg: Dict[str, Type[Step]], title: str,
                       where: str) -> Any:
    """「用到的數字沒有流進 ``dst``」那一條（Decision 與 Output 共用，F124）。

    **warning**：引擎照舊拿得到每一個數字（整顆 defect 都在），跑得完、寫得出來
    —— 只是畫布講的流跟實際用到的對不上，使用者看著畫布講不出那個數字從哪來。
    ``connect`` 給畫面那顆鈕：每張卡找一張拉了線就流得進來的（`feeder`）。
    """
    from .recipe_validate import Issue, card_name

    nodes = recipe.nodes
    names = tuple(n for ns in away.values() for n in ns)
    who: List[str] = []
    connect: List[str] = []
    stuck: List[str] = []
    for owner in away:
        if owner == "":
            dec = next((n for n, node in nodes.items()
                        if node.step == DECISION_KEY and node.enabled), "")
            via = dec
            who.append("Decision")
        else:
            via = feeder(recipe, owner, reg)
            who.append(card_name(nodes, owner))
        if via and via != dst and via not in connect:
            connect.append(via)
        elif not via:
            stuck.append(who[-1])
    if connect:
        advice = ("Connect %s to %s so the canvas shows where %s come%s from."
                  % (" and ".join(Q % card_name(nodes, c) for c in connect),
                     where, "that number" if len(names) == 1 else "those numbers",
                     "s" if len(names) == 1 else ""))
    else:
        advice = ("Nothing that measures after %s flows into %s - add a "
                  "measuring card after it, or ask about another number."
                  % (" and ".join(Q % w for w in stuck), where))
    return Issue(
        code=code, level="warning", node_id=dst, title=title,
        detail="route '%s': it uses %s, from %s. %s"
               % (kind, ", ".join(names), " and ".join(Q % w for w in who),
                  advice),
        names=names, route=str(kind), advice=advice, connect=tuple(connect))


def _numbers_not_upstream(recipe: Any, nid: str, c: Type[Step], kind: str,
                          decided: bool,
                          reg: Dict[str, Type[Step]]) -> List[Any]:
    """Output 卡用**名字**吃的數字（排序、欄位、要畫的數字），產出它的卡沒有
    流進這張卡（F123 期 3；F124 起是提醒）。

    F124 起 Output 寫整張表，所以那一欄不會空 —— 這一條留著是因為畫布講的流跟
    實際用到的對不上（跟 Decision 那一條同一個理由、同一顆「Connect」鈕）。
    """
    try:
        names = [str(n) for n in c.feature_names_in(
            c.validate_params(recipe.nodes[nid].params))]
    except Exception:  # 參數壞了由 bad-param 講
        return []
    away = _not_flowing(recipe, nid, names, kind, reg, decided)
    if not away:
        return []
    from .recipe_validate import card_name
    return [_not_flowing_issue(
        recipe, "output-number-not-upstream", nid, away, kind, reg,
        title="%s uses numbers that do not flow into it"
              % (Q % card_name(recipe.nodes, nid)),
        where="this card")]


Q = "“%s”"

# d4t core — 判定用到哪些特徵（PR-1，2026-08-27）。
"""**結果表分層的資料來源：這份 recipe 的判定到底問了哪幾個數字。**

結果表五六十欄平鋪的解法是分兩層：判定層（預設可見）與其餘（按產出卡摺疊）。
分層是**自動的**（由 recipe 推導，沒有手動挑欄的設定頁），所以「哪幾欄屬於
判定層」要有一個唯一的出處 —— 就是這一份。

為什麼是新模組而不是塞進 ``recipe.py``：``decide_tree.py`` 在模組層
``from .recipe import …``，recipe.py 反過來 import 它就是循環。這裡站在兩者
之上，可以自由用兩邊已經寫好的抽取邏輯（**不寫第二份**，CLAUDE.md §0）：

* 算式的變數名 —— ``expression.parse_expression(...).variables``；
* 判定樹問過的特徵 —— ``decide_tree.features_used``（let 中間名已展開，含巢狀）；
* 卡片宣告 —— ``Step.optional_features_in`` / ``resolve_features_in`` /
  ``diagnostic_features`` / ``diagnostic_alarms``；
* 撞名救援的名字 —— ``engine.feature_prefixes`` + ``qualified_feature_name``。

這裡全部是**純函式、顯示層 metadata**：不碰數字、不碰匯出、不進快取簽章。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple, Type

from .decide_tree import features_used
from .engine import feature_prefixes, qualified_feature_name
from .expression import ExpressionError, parse_expression
from .recipe import Recipe, RecipeError, execution_order
from .step import FeatureSpec, REGISTRY, Step

__all__ = [
    "features_in_verdict",
    "diagnostic_columns",
    "diagnostic_alarm_map",
    "BoundSpec",
    "bound_specs",
    "ENGINE_LABEL",
]


def _route_steps(recipe: Recipe, kind: str,
                 registry: Dict[str, Type[Step]],
                 ) -> Iterator[Tuple[str, Type[Step], Dict[str, Any]]]:
    """這條 route 上啟用中的卡，執行順序，參數已清過（容錯，照 validate 的路）。

    壞參數退回預設值、認不得的卡直接跳過 —— 這裡是顯示層的資料來源，
    問題本身由 ``validate`` 負責講（bad-param / unknown-step），不抄第二份。
    ``execution_order`` 排不出來（cycle / unknown kind）就退回 route 的原始
    順序：欄位分組頂多不準，不能因此沒有表。
    """
    try:
        order = execution_order(recipe, kind)
    except RecipeError:
        order = list(recipe.routes.get(kind, ()))
    for nid in order:
        node = recipe.nodes.get(nid)
        if node is None or not node.enabled:
            continue
        step_cls = registry.get(node.step)
        if step_cls is None:
            continue
        try:
            p = step_cls.validate_params(dict(node.params))
        except Exception:  # noqa: BLE001 — 顯示層：壞參數用預設值繼續
            try:
                p = step_cls.validate_params(None)
            except Exception:  # noqa: BLE001
                p = dict(node.params)
        yield nid, step_cls, p


def features_in_verdict(recipe: Recipe, kind: str,
                        registry: Optional[Dict[str, Type[Step]]] = None,
                        ) -> List[str]:
    """判定引用了哪幾個特徵名 —— **有序去重，照引用順序**。

    四個來源的聯集（工作單 1a）：判定樹（let 已展開成底層特徵，含巢狀 ——
    let 名不是欄位）、score 算式的變數名（decide 在的時候 score 根本不跑，
    recipe.py 的互斥檢查守著，所以兩者取其一）、route 上啟用卡片的
    ``optional_features_in`` 與 ``resolve_features_in``。

    **不**過濾「沒人產出的名字」：score 引用了一個打錯的名字時，一個看得到的
    空欄比默默消失好 —— 那正是使用者需要看見的錯。回傳型別是 list 不是 set，
    因為判定層的欄序就是引用順序（1b）；當 set 用照樣成立。
    """
    if registry is None:
        registry = REGISTRY
    out: List[str] = []
    seen = set()

    def take(names: Any) -> None:
        for n in names:
            n = str(n)
            if n and n not in seen:
                seen.add(n)
                out.append(n)

    if recipe.decide is not None:
        take(features_used(recipe.decide))
    else:
        try:
            take(sorted(parse_expression(recipe.score.expr).variables))
        except ExpressionError:
            pass  # validate 已用 score-expr 報過，這裡沒有第二句話好講
    for _nid, step_cls, p in _route_steps(recipe, kind, registry):
        take(step_cls.optional_features_in(p))
        take(step_cls.resolve_features_in(p))
    return out


def diagnostic_columns(recipe: Recipe, kind: str,
                       registry: Optional[Dict[str, Type[Step]]] = None,
                       ) -> List[str]:
    """這條 route 上所有卡宣告的診斷特徵名（含撞名時的救援名）。

    救援名跟引擎用**同一支**（``feature_prefixes`` + ``qualified_feature_name``，
    F17-② 的教訓：自己組前綴的那一份漂掉之後，救回來的診斷值會以量測值的
    身分出現）。
    """
    if registry is None:
        registry = REGISTRY
    steps = list(_route_steps(recipe, kind, registry))
    try:
        prefixes = feature_prefixes([nid for nid, _, _ in steps],
                                    recipe, registry)
    except Exception:  # noqa: BLE001 — 顯示層，退回節點 id
        prefixes = {}
    out: List[str] = []
    seen = set()
    for nid, step_cls, p in steps:
        diag = list(step_cls.diagnostic_features(p))
        pfx = prefixes.get(nid, nid)
        for name in diag + [qualified_feature_name(pfx, f) for f in diag]:
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def diagnostic_alarm_map(recipe: Recipe, kind: str,
                         registry: Optional[Dict[str, Type[Step]]] = None,
                         ) -> Dict[str, bool]:
    """特徵名 → 出事時的布林值。**只有這張表上的名字可以亮警示徽章。**

    數值型診斷（``glv_sat_frac`` 那類）不在表上，所以 UI 想警示也沒有依據 ——
    「不對數值發明門檻」不是自律，是做不到。同名撞上時後面的卡勝，跟引擎的
    覆寫語意一致。
    """
    if registry is None:
        registry = REGISTRY
    out: Dict[str, bool] = {}
    for _nid, step_cls, p in _route_steps(recipe, kind, registry):
        for name, bad in step_cls.diagnostic_alarms(p):
            out[str(name)] = bool(bad)
    return out


@dataclass(frozen=True)
class BoundSpec:
    """一個特徵的**完整**身分：spec ＋ 它掛在哪個節點上（PR-3）。

    ``node_id == ""`` 是**引擎/判定段**（score / decide_unanswered /
    route_taken / let 那些）—— UI 對映到「Score / Bin」那張偽卡。
    """
    node_id: str
    label: str
    spec: FeatureSpec


#: 引擎/判定段那一組在 UI 上的名字 —— 跟 `studio._SCORE_LIBRARY_ENTRY` 的
#: label 同一個字（那邊是它的別名，這裡是家）。
ENGINE_LABEL = "Score / Bin"


def bound_specs(recipe: Recipe, kind: str,
                registry: Optional[Dict[str, Type[Step]]] = None,
                ) -> List[BoundSpec]:
    """這條 route 上**每一個會出現的特徵名**的完整身分，執行順序。

    取代 PR-1 的 `feature_groups_by_card`（卡層分組）：卡 → 區域 → 統計量
    的樹、維度過濾、回溯面板的「點項找來源卡」全部從這一份長出來 ——
    分組結構只有一個家。三個來源：

    * route 上啟用卡片的 `resolve_feature_specs`（名字歸**第一個**產出者，
      同 ``_feature_collisions`` 的 setdefault 語意）；
    * 撞名時的**救援名**（`FeatureSpec.qualified`，前綴跟引擎同一支
      `feature_prefixes` —— 這裡收斂了 `diagnostic_columns` 與
      `studio._feature_sections` 以前各自手組的那兩份）；
    * 引擎/判定段：``score``（**有算式才宣告** —— 引擎沒算式就不寫那一格）、
      ``decide_unanswered``（有 decide 恆有）、``route_taken``（有
      route_by 才有）、每個 let（＋ fill → ``_missing``、scale → ``_raw``）。

    同名卡片出現兩次以上才把 node id 帶進 label（每一組都掛 id 是在正常
    recipe 上加噪音）。
    """
    if registry is None:
        registry = REGISTRY
    steps = list(_route_steps(recipe, kind, registry))
    try:
        prefixes = feature_prefixes([nid for nid, _, _ in steps],
                                    recipe, registry)
    except Exception:  # noqa: BLE001 — 顯示層，退回節點 id
        prefixes = {}
    # ---- 先問「每個名字有哪幾張卡宣告」（執行順序）------------------------
    #
    # ⚠ **這一段 2026-08-28 整個重寫（F51）**，因為舊的跟引擎講的是相反的話。
    # 引擎（`engine._rescue_overwritten_features`）是這樣的：後寫的贏，
    # **被蓋掉的那一張**被救成 `<它的前綴>_<原名>`。所以撞名的時候：
    #
    # * **裸名歸最後一張**（它的值才是 `ctx.features[name]` 裡的那個）；
    # * 前面每一張各拿一個救援名。
    #
    # 舊的寫法剛好相反（第一張拿裸名、後面的拿救援名），而且**只對診斷數字**
    # 加救援名、還是**無條件**加（沒撞名也加）。實測的下場：
    #
    # * `glv2_glv_pixels` 這種欄位在結果表上出現，而引擎從來不寫（幽靈欄）；
    # * `glv_glv_max` / `glv_glv_mean` 這些引擎真的寫進 CSV 的數字，UI 完全
    #   不知道 —— 分不了組、篩不到、回溯面板指不到；
    # * 裸名掛在第一張卡上，而值來自最後一張 —— 回溯面板會跳到錯的卡。
    #
    # 尺在 `tests/test_feature_names_match_the_engine.py`：**真的跑一次引擎**，
    # 拿它的 keys 當基準。兩份預測要再漂，那裡會紅。
    declared: List[Tuple[str, Any, List[Any]]] = []
    producers: Dict[str, List[str]] = {}
    for nid, step_cls, p in steps:
        try:
            specs = list(step_cls.resolve_feature_specs(p))
        except Exception:  # noqa: BLE001 — 顯示層
            specs = []
        declared.append((nid, step_cls, specs))
        for s in specs:
            producers.setdefault(str(s.name), []).append(nid)

    out: List[BoundSpec] = []
    owned = set()
    for nid, step_cls, specs in declared:
        pfx = prefixes.get(nid, nid)
        for s in specs:
            who = producers.get(str(s.name)) or [nid]
            if who[-1] == nid:
                # 最後一張 —— 裸名是它的（引擎後寫的贏）。
                bound = s
            else:
                # 被蓋掉的那一張：引擎把它救成 `<前綴>_<原名>`。
                # `feature_prefixes` 已經替撞在一起的前綴退回節點 id 了，
                # 所以這裡不必再抄引擎那一層 runtime 的去重。
                bound = s.qualified(pfx)
            if bound.name not in owned:
                owned.add(bound.name)
                out.append(BoundSpec(nid, str(step_cls.label), bound))

    def engine(name: str, **kw: Any) -> None:
        if name not in owned:
            owned.add(name)
            out.append(BoundSpec("", ENGINE_LABEL,
                                 FeatureSpec(name=name, family="engine", **kw)))

    decide = recipe.decide
    has_score = bool((decide.score if decide is not None
                      else recipe.score.expr).strip())
    if has_score:
        engine("score", base="score", metric="score")
    if decide is not None:
        engine("decide_unanswered", base="decide_unanswered",
               metric="decide_unanswered")
        for item in decide.let:
            name = str(item.name).strip()
            if not name:
                continue
            engine(name, base=name)
            if str(getattr(item, "fill", "") or ""):
                engine(name + "_missing", base=name, variant="missing")
            if str(getattr(item, "scale", "") or ""):
                engine(name + "_raw", base=name, variant="raw")
    if getattr(recipe, "route_by", None) is not None:
        engine("route_taken", base="route_taken", metric="route_taken")

    labels = [b.label for b in out]
    return [BoundSpec(b.node_id,
                      ("%s · %s" % (b.label, b.node_id)
                       if b.node_id and labels.count(b.label) > 1
                       and len({x.node_id for x in out
                                if x.label == b.label}) > 1
                       else b.label), b.spec)
            for b in out]

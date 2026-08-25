# d4t pipeline engine — authored 2026-07-28 (M1).
"""Recipe 模型：DAG JSON serde、執行順序（拓撲排序）、lint 式驗證。

Recipe JSON 形狀（見 docs/plans/F0-master-plan.md §3.4）：

.. code-block:: json

    {
      "recipe_id": "M1_EBI_bridge", "version": 3, "author": "HX",
      "description": "...",
      "routes": {"ebi_patch": ["load","align","subtract","snr"],
                 "rsem":      ["load","golden","subtract","snr"]},
      "nodes": {"align": {"step": "align", "params": {"method": "phase"},
                          "enabled": true}},
      "edges": [["subtract", "diff", "snr", "source"]],
      "score": {"expr": "snr_max * sqrt(area_px)", "threshold": 3.0,
                "bins": {"below": 0, "above": 1}}
    }

- ``routes`` 說的是「這條 route 有哪些卡」，``edges`` 是畫布上的線。
  **執行順序只看線**（F17-①）：edges（限制在該 route 內）的 Kahn 拓撲排序，
  平手時依 route 位置決定（deterministic）。route 的排列是**排版**不是語意 ——
  以前它的相鄰對也算成邊，於是「兩張沒有線相連的卡誰先跑」由使用者把卡片拖到
  哪裡決定，而畫面上看不出來（見 :func:`execution_order`）。
- **邊帶埠**（F9-1，2026-08-16）：``[來源, 來源的輸出埠, 下游, 下游的輸入參數]``。
  舊的兩欄位格式 ``["subtract","snr"]`` 照讀，埠留空。**執行順序目前不看埠** ——
  F9-1 換的是資料形狀不是語意，見 ``docs/plans/F9-dag-streams.md``。
- 驗證走 lint 模式（KLIP ``Issue`` 結構）：一次列出**所有**問題，
  不是碰到第一個就停。
"""
from __future__ import annotations

import heapq
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Set, Tuple, Type

from .expression import ExpressionError, parse_expression
from .step import (
    GROUP_COMPARE, GROUP_ENHANCE, SCALE_LOT, ParamError, Step, REGISTRY,
)

__all__ = [
    "RecipeError", "RecipeNode", "ScoreSpec", "Edge", "Recipe",
    "RouteBy", "resolve_route", "route_miss_message",
    "Issue", "execution_order", "validate",
]


class RecipeError(ValueError):
    """Recipe 結構性錯誤（循環、未知 route、JSON 缺欄位…）。"""


#: 判定樹的巢狀上限。**存在的理由是訊息，不是安全。**
#:
#: `_tree_from_json` / `_tree_depth` / `_eval_decision` 都是遞迴的，所以一份
#: 巢狀夠深的 JSON 會撞 Python 的遞迴上限 —— 而 `RecursionError` 不是
#: `RecipeError`，讀檔那條路接不住它，使用者看到的是一段 traceback（推廣鐵則）。
#: 200 層遠遠超過任何人畫得出來的判定樹（F24 的驗收案例最深是 4 層），
#: 所以擋在這裡的一定是寫壞的檔案，而它現在會拿到一句白話。
MAX_TREE_DEPTH = 200


def _as_number(raw: Any, where: str, cast, kind: str):
    """把 JSON 裡的一個值轉成數字，**轉不動就講人話**。

    recipe 是使用者留在磁碟上的檔案，而它會被手改（這個 repo 沒有存檔功能，
    所以手改是唯一的編輯方式）。直接 ``int()`` / ``float()`` 下去的話，一個
    打錯的欄位吐出來的是 ``invalid literal for int() with base 10: '1.0'`` ——
    那句話沒有講出是**哪一個欄位**，而使用者是不會寫 code 的製程工程師。
    """
    if isinstance(raw, bool):      # bool 是 int 的子類，但當數字用一定是筆誤
        raise RecipeError("%s must be %s, got the true/false value %r"
                          % (where, kind, raw))
    try:
        return cast(raw)
    except (TypeError, ValueError):
        raise RecipeError("%s must be %s, got %r" % (where, kind, raw))


def _as_int(raw: Any, where: str) -> int:
    return _as_number(raw, where, int, "a whole number")


def _as_float(raw: Any, where: str) -> float:
    return _as_number(raw, where, float, "a number")


def _app_version() -> str:
    """現在跑的這一版 d4t。"""
    from d4t import __version__
    return str(__version__)


def _version_tuple(text: str):
    """``"0.2.1"`` → ``(0, 2, 1)``；比不出來回 ``None``（就不硬說誰新誰舊）。"""
    parts = []
    for chunk in str(text or "").split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else None


def version_skew(recipe_version: str) -> str:
    """這份 recipe 是不是**比現在這個程式新**存的；是的話回一句白話，否則空字串。

    講得出這句話，「unknown parameters」才有正確的意思。沒有它，使用者看到的
    是「這份檔案壞了」，於是他會去重做一份 recipe —— 而該做的是更新程式。
    """
    theirs = str(recipe_version or "").strip()
    if not theirs:
        return ""
    mine = _app_version()
    if theirs == mine:
        return ""
    a, b = _version_tuple(theirs), _version_tuple(mine)
    if a is not None and b is not None and a <= b:
        return ""                      # 檔案比較舊 → 遷移的事，不是版本落差
    return ("This recipe was saved by d4t %s and this build is %s — update "
            "d4t on this machine before using it." % (theirs, mine))


# ---------------------------------------------------------------------------
# 資料模型
# ---------------------------------------------------------------------------
@dataclass
class RecipeNode:
    """pipeline 上的一張卡：``id`` 節點名、``step`` 卡片 key、``params`` 參數。"""
    id: str
    step: str
    params: Dict[str, Any]
    enabled: bool = True


@dataclass
class ScoreSpec:
    """ADC 判定段：score 表達式 + 門檻 + bin 對應（{"below": 0, "above": 1}）。

    **只分得出兩類。** 多類別走 :class:`DecideSpec`（F21-D）。
    """
    expr: str
    threshold: float
    bins: Dict[str, int]


@dataclass(frozen=True)
class Rule:
    """判定的一條規則：``when`` 成立就是 ``bin``（``label`` 只是給人看的字）。"""
    when: str
    bin: int
    label: str = ""


#: `Let.scale` 認得的值：""＝照算（逐顆）、"z"＝跟整批比（robust z：
#: (值 − 整批中位數) / (1.4826 × MAD)，跟 `algo/enhance.py` 同一個係數）、
#: "percentile"＝在整批裡排第幾百分位（0–100，midrank）。
LET_SCALES = ("", "z", "percentile")


@dataclass(frozen=True)
class Let:
    """判定段的一個中間值：``name = expr``，算完寫進 ``ctx.features``。

    ``scale``（F23 期3，「跟整批比」）：非空時這一行是**兩趟**算的 ——
    第一趟逐顆算出原始值，整批收齊後把它換算成整批尺度（robust z 或
    百分位），原始值改名 ``<name>_raw`` 留著，然後**用換算後的值重算判定**
    （`batch.apply_lot_scaling`）。為什麼要兩趟：跨顆算出來的數字（「這一顆
    比整批亮多少」）在單顆的 `run_defect` 裡根本不存在 —— 那正是舊
    `lot_stats` 卡一直卡住的地方（F23 §8）。

    取整批統計時**排除 `feature_fill` 補過值的顆**（`<變數>_missing == 1`
    的列不進中位數 —— A1 當時就記下的規矩）；那幾顆自己仍然拿到換算值
    （用大家的統計換算它，數字看得出它是補的）。

    ``fill``（F24 ⑤，「missing ⇒ 用 __」）：非空時，這一行用到的數字**缺了**
    （上游量不出來、那一格沒寫 —— F19：算不出來的不寫）就不讓整顆失敗，
    值改用這個數字，並寫 ``<name>_missing = 1``（有 fill 時每顆都寫這個旗標,
    0 或 1 —— CSV 那一欄才是完整的）。判定樹的第一步問
    ``<name>_missing > 0`` 就是它的形狀。留空＝照舊：缺了就是這一顆失敗，
    訊息講出缺哪個數字。這正是 `feature_fill` 卡的那件事搬進 working number
    一行 —— 補值跟著「誰要用它」住，不再是一張要另外接的卡。
    """
    name: str
    expr: str
    scale: str = ""
    fill: str = ""


@dataclass(frozen=True)
class TreeLeaf:
    """判定樹的葉子：走到這裡就是這一類。"""
    bin: int
    label: str = ""


@dataclass(frozen=True)
class TreeStep:
    """判定樹的一步：問一個問題，yes 一邊、no 一邊（各自是步驟或葉子）。

    為什麼是二叉不是多叉（F24）：一步一問是**流程圖語言**，製程工程師本來就
    會讀；多叉要在一顆節點上排好幾個互斥條件，而「互斥」在畫面上驗不了 ——
    那正是 F22 挑「第一個成立的贏」而不是「每條算分取最高」的同一個理由。
    多路分岔用巢狀的步驟表達，畫出來就是一條 yes 鏈。
    """
    when: str
    yes: Any            # TreeStep | TreeLeaf
    no: Any             # TreeStep | TreeLeaf


def rules_to_tree(spec: "DecideSpec") -> Any:
    """把平面規則清單翻成**等價的鏈狀樹**（F24 §3）。

    「由上往下第一個成立的贏」就是一條每步 yes → 葉子、no → 下一步的鏈，
    所以這個轉換**無損**：同一組特徵值走 rules 與走轉出來的樹，bin 與 label
    逐項相同（`tests/test_decide_tree.py` 用值網格驗）。空清單＝直接是
    otherwise 那片葉子。
    """
    node: Any = TreeLeaf(bin=int(spec.otherwise_bin),
                         label=str(spec.otherwise_label))
    for rule in reversed(list(spec.rules)):
        node = TreeStep(when=rule.when,
                        yes=TreeLeaf(bin=int(rule.bin), label=rule.label),
                        no=node)
    return node


def _tree_to_json(node: Any) -> Dict[str, Any]:
    if isinstance(node, TreeLeaf):
        return {"bin": int(node.bin), "label": node.label}
    return {"when": node.when,
            "yes": _tree_to_json(node.yes),
            "no": _tree_to_json(node.no)}


def _tree_from_json(raw: Any, where: str = "decide.tree", depth: int = 0) -> Any:
    """讀一個樹節點。格式錯**當場講**（同 `_decide_from_json` 的理由）。

    判準：有 ``when`` 是步驟（要有 ``yes`` 與 ``no``）、有 ``bin`` 是葉子 ——
    兩個都有或都沒有就是寫壞了，不猜。

    ``depth`` 擋的是 :data:`MAX_TREE_DEPTH`（見那裡的說明）：這一支是遞迴的，
    而撞到 Python 遞迴上限吐出來的 ``RecursionError`` 不是 ``RecipeError``，
    讀檔那條路接不住。
    """
    if depth > MAX_TREE_DEPTH:
        # ``where`` 到這裡已經是 200 段 ".no" —— 印全長只會把訊息淹掉。
        raise RecipeError(
            "the decision tree is nested more than %d levels deep - that is "
            "not a tree anyone drew, so the file is almost certainly damaged "
            "(the path starts %s...)" % (MAX_TREE_DEPTH, where[:60]))
    if not isinstance(raw, dict):
        raise RecipeError("%s must be an object (dict), got %s"
                          % (where, type(raw).__name__))
    has_when, has_bin = "when" in raw, "bin" in raw
    if has_when and has_bin:
        raise RecipeError("%s has both 'when' and 'bin' - a node is either a "
                          "step (when/yes/no) or a leaf (bin/label), not both"
                          % where)
    if has_bin:
        return TreeLeaf(bin=_as_int(raw["bin"], where + ".bin"),
                        label=str(raw.get("label", "") or ""))
    if has_when:
        if "yes" not in raw or "no" not in raw:
            raise RecipeError("%s is a step ('when') but is missing its "
                              "'yes' or 'no' side" % where)
        return TreeStep(when=str(raw["when"]),
                        yes=_tree_from_json(raw["yes"], where + ".yes",
                                            depth + 1),
                        no=_tree_from_json(raw["no"], where + ".no",
                                           depth + 1))
    raise RecipeError("%s must have either 'when' (a step) or 'bin' (a leaf)"
                      % where)


def _tree_depth(node: Any) -> int:
    if isinstance(node, TreeLeaf):
        return 0
    return 1 + max(_tree_depth(node.yes), _tree_depth(node.no))


def _tree_whens(node: Any) -> List[str]:
    if isinstance(node, TreeLeaf):
        return []
    return [node.when] + _tree_whens(node.yes) + _tree_whens(node.no)


@dataclass
class DecideSpec:
    """ADC 判定段（多類別，F21-D）—— **一張由上往下讀的篩子**。

    為什麼是「第一個成立的贏」而不是「每條算分取最高」
    --------------------------------------------------
    使用者是不會寫 code 的製程工程師（推廣鐵則）。「由上往下，第一個對上的
    就是答案」是一句他讀得懂、而且**改順序就等於改優先權**的規則；算分取最高
    要他同時想像好幾條分數線的相對高度，而那件事在畫面上畫不出來。

    ``let``：中間值，而且它們是**真的特徵**
    ---------------------------------------
    每一行 ``{"name": …, "expr": …}`` 算完就寫進 ``ctx.features`` —— 所以它們
    會進 CSV、進報表，使用者畫得出它們的分布。這正是 `feature_math` 存在的唯一
    真理由（「一份 recipe 只有一條表達式，中間值沒有地方放」），而在這裡它不必
    是一張卡：**判定段吃的是「這一次跑出來的全部」，沒有「哪一個」可以選**
    —— 那是 F17 對 Output 卡講過的話，對這一段一字不差地成立。

    ⚠ 使用者 2026-08-23 提出「ADC 也可以有線」，而那句話**不在這一版否決**：
    多類別之後每條規則吃的是**特定幾個**數字，不是全部，那時候線是有意義的。
    這一版只做引擎，畫布留在後面（見 `docs/history/plans/F22-adc-multiclass.md`）。

    跟 :class:`ScoreSpec` 的關係：**二選一，不能並存**
    -------------------------------------------------
    並存的話同一件事會有兩個地方存，而這個 repo 最怕的就是那個形狀
    （抄第二份出來的那份一定會漂）。所以 ``validate`` 把「兩個都寫」判成
    ``ambiguous-decision`` 的 error，而不是挑一個贏。

    這一版**沒有自動遷移**：舊 recipe 照舊走 ``score``，一個位元都不動。
    理由不是保守，是寫這一版的當下**黃金值是壞的**（見
    `docs/history/plans/F21-algo-and-roi.md` §6）—— 沒有那條防線的時候，
    「改了判定段但數字沒變」這句話沒有人證得了。
    （尺 2026-08-23 已重凍、三份全綠；**不遷移這個決定仍然成立** ——
    舊 recipe 照舊走 ``score`` 是使用者定的，不是那把尺定的。）
    """
    #: 中間值（一行一個），算完寫進 features。
    let: List[Let] = field(default_factory=list)
    rules: List[Rule] = field(default_factory=list)
    #: 一條都沒對上的時候。
    otherwise_bin: int = 0
    otherwise_label: str = ""
    #: 這一顆的分數（KLARF 的 DSIZE／Top-N 排序要一個數字）。空字串 = 0.0。
    score: str = ""
    #: 判定樹（F24）。有它就走樹、忽略 ``rules``/``otherwise`` —— 但**兩個都
    #: 寫**是 `ambiguous-decision` 的 error（同 `score` vs `decide`：同一件事
    #: 兩個地方存，挑一個贏的話另一份會安靜地漂）。``rules`` 是它的特例
    #: （鏈狀樹，見 :func:`rules_to_tree`），所以舊寫法照讀不誤。
    tree: Any = None


@dataclass(frozen=True)
class RouteBy:
    """分流（F23）：**跑之前**逐顆看 KLARF 的一欄，決定這一顆走哪條 route。

    為什麼它是 recipe 頂層的一個區塊、不是一張卡也不是 decide 的規則
    ------------------------------------------------------------------
    它在**跑之前**就要決定 —— 卡片是在 route 裡面跑的（雞生蛋），而 decide 的
    變數是特徵、特徵要跑完才有。分流要的是 Class 2 的顆**根本不跑** A 組卡：
    省的是實打實的計算，擋的是「對 Class 2 跑 A 組 CD 卡量出一個看起來正常、
    但問錯問題的數字」。

    語意（F23 §4，使用者 2026-08-24 定調）：

    * ``column`` 是 KLARF 的欄名（一律大寫存放）；值**先 strip 再比字串**
      （KLARF 的值都是字串，``"1"`` 與 ``" 1"`` 要落在同一格）。
    * 對不上 ``map`` 的走 ``default``；``default`` 留空＝那一顆**失敗**
      （``ok=False``，訊息講出值 X 不在對照表裡）。兩種都要支援 ——
      「沒見過的 class 該怎麼辦」是站點政策，不是軟體能替使用者決定的。
    * ``route_by`` 存在時**覆蓋 kind 選路**（§4.2）：route 鍵因此可以是任意
      字串（``particle_route``），不必是 dataset kind。
    * **鐵則 9 條款**：這個區塊不在 → 一個位元都不動（同 ``decide`` 的嚴格
      附加模式）。round-trip 是 identity。
    """
    column: str
    map: Dict[str, str] = field(default_factory=dict)
    default: str = ""


def _route_by_from_json(raw: Any) -> Optional["RouteBy"]:
    """讀 ``route_by`` 區塊。**沒有就回 None** —— 那份 recipe 照舊用 kind 選路。

    格式錯**當場講**而不是安靜地退回老路（同 `_decide_from_json` 的理由）：
    安靜退回的話，一份打錯字的分流 recipe 會整批走同一條路 —— 跑得完、有數字、
    而且 CSV 上沒有任何線索說它沒分流。
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise RecipeError("the 'route_by' block must be an object (dict), got "
                          "%s" % type(raw).__name__)
    missing = [k for k in ("column", "map") if k not in raw]
    if missing:
        raise RecipeError("route_by is missing %s - it needs 'column' (the "
                          "KLARF column to look at) and 'map' (value -> route "
                          "name)" % missing)
    m = raw["map"]
    if not isinstance(m, dict):
        raise RecipeError("route_by.map must be an object mapping column "
                          "values to route names, got %s" % type(m).__name__)
    return RouteBy(
        column=str(raw["column"]).strip().upper(),
        map={str(k).strip(): str(v) for k, v in m.items()},
        default=str(raw.get("default", "") or ""),
    )


def resolve_route(recipe: "Recipe", item: Any, kind: str
                  ) -> Tuple[Optional[str], str, str]:
    """這一顆走哪條 route：``(route 鍵, 欄位值, 決定的來源)``。

    來源三種：``"kind"``（沒有 ``route_by``，維持舊語意 —— route 鍵就是
    dataset kind）、``"map"``（值對上了對照表）、``"default"``（沒對上、走
    預設路）。對不上而且 ``default`` 留空時 route 鍵是 **None** ——
    呼叫端把那一顆判失敗（訊息用 :func:`route_miss_message`）。

    欄位值從 ``item.fields`` 讀（`ingest.dataset.fill_fields` 填的那一份，
    大寫欄名）—— **這一支不碰 KLARF**，跟卡片同一條規矩（鐵則：讀檔在 ingest
    層）。欄位沒被填進來時值是空字串，走「對不上」那條路。
    """
    rb = getattr(recipe, "route_by", None)
    if rb is None:
        return kind, "", "kind"
    fields = getattr(item, "fields", None) or {}
    raw = fields.get(str(rb.column).strip().upper())
    value = str(raw).strip() if raw is not None else ""
    if value in rb.map:
        return str(rb.map[value]), value, "map"
    default = str(rb.default or "").strip()
    if default:
        return default, value, "default"
    return None, value, "miss"


def route_miss_message(route_by: "RouteBy", value: str) -> str:
    """「這一顆對不上對照表」的白話訊息（每一顆失敗都帶著它）。"""
    mapped = ", ".join("'%s'" % k for k in sorted(route_by.map)) or "(none)"
    return ("route_by: the %s value '%s' is not in the route map (mapped "
            "values: %s) and no default route is set. Add this value to the "
            "map, or set a default route for everything else."
            % (route_by.column, value, mapped))


@dataclass(frozen=True)
class Edge:
    """畫布上的一條線：**來源節點的哪個輸出埠 → 下游節點的哪個輸入參數**。

    F9-1（2026-08-16）把邊從 ``[src, dst]`` 換成帶埠的四個欄位。為什麼要這樣，
    見 ``docs/plans/F9-dag-streams.md``：影像流的身分要從「全域的名字」變成
    「哪個節點的哪個輸出」，同一條 ``ref`` 才分得出兩條互不干擾的支線。

    **``dst_in`` 綁的是參數名不是流名**（``"b"`` / ``"streams"``，不是
    ``"ref"``）。因為流名之後只是**顯示用的標籤** —— 使用者把 ``ref_2`` 改叫
    ``ref_soft``，接線不該因此斷掉。

    兩個埠都可以是空字串 = **還沒指定**。F9-1 只換形狀不換語意，所以舊檔案
    遷移進來的邊、以及目前 UI 拉出來的線，埠都是空的；執行順序完全不看它們
    （見 :func:`execution_order`）。F9-2 才開始用埠來組每個節點的輸入。

    欄位順序（``src, dst, src_out, dst_in``）**刻意跟 JSON 的順序不同**：
    JSON 寫成 ``[src, src_out, dst, dst_in]``（讀起來是「load 的 test →
    denoise 的 streams」），但建構式維持 ``Edge(src, dst)`` 這個直覺的形狀，
    免得少寫兩個參數就變成 ``src_out=dst``。
    """
    src: str
    dst: str
    src_out: str = ""
    dst_in: str = ""

    def to_json(self) -> List[str]:
        """``[src, src_out, dst, dst_in]`` —— 讀起來是「誰的哪個出口 → 誰的哪個入口」。"""
        return [self.src, self.src_out, self.dst, self.dst_in]

    @classmethod
    def from_json(cls, raw: Any) -> "Edge":
        """吃新格式（4 個）或**舊格式（2 個）**。

        舊格式的判斷依據是「**長度就是 2**」—— 那是舊東西**在**，不是新東西
        不在（鐵則 9）。所以一份新 recipe 永遠不會被誤判成舊的。
        """
        e = list(raw)
        if len(e) == 2:
            return cls(src=str(e[0]), dst=str(e[1]))
        if len(e) == 4:
            return cls(src=str(e[0]), src_out=str(e[1]),
                       dst=str(e[2]), dst_in=str(e[3]))
        raise RecipeError(
            "an edge must be [from, to] or [from, from_port, to, to_param] — "
            "got %d item(s): %r" % (len(e), e))


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
        for i, when in enumerate(_tree_whens(decide.tree)):
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
        name = str(item.name).strip()
        if not name:
            out.append(Issue(
                code="bad-let", level="error", node_id=None,
                title="A 'let' line has no name",
                detail="decide.let[%d] must have a name - that name is what "
                       "the rules below refer to." % i))
        elif name in seen:
            out.append(Issue(
                code="bad-let", level="error", node_id=None,
                title="Two 'let' lines have the same name",
                detail="decide.let[%d] is called '%s' again - the second one "
                       "would quietly replace the first." % (i, name)))
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
                out.append(Issue(
                    code="bad-let", level="error", node_id=None,
                    title="A 'let' line's missing-value fallback is not "
                          "a number",
                    detail="decide.let[%d] says 'if missing use %s' - that "
                           "has to be a plain number (it stands in for the "
                           "value when the measurement is not there)."
                           % (i, fill)))
        scale = str(getattr(item, "scale", "") or "")
        if scale not in LET_SCALES:
            # 打錯的 scale 不能安靜地當成「照算」：那一行看起來在跟整批比,
            # 實際上每一顆還是自己的原始值 —— 跑得完、有數字、而且是錯的。
            out.append(Issue(
                code="bad-let", level="error", node_id=None,
                title="A 'let' line has an unknown batch scaling",
                detail="decide.let[%d] says scale='%s'; the choices are '' "
                       "(as measured), 'z' (robust z against the batch) and "
                       "'percentile' (rank within the batch)." % (i, scale)))
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

    def check(where: str, text: str) -> None:
        try:
            e = parse_expression(str(text))
        except ExpressionError:
            return                      # 語法錯已經由 `_decide_issues` 講過了
        unknown = sorted(e.variables - seen)
        if unknown:
            out.append(Issue(
                code="unknown-feature", level="warning", node_id=None,
                title="The decision uses a number nobody produces",
                detail="route '%s': %s uses %s, but no card in this route "
                       "writes those out (available here: %s). Check the "
                       "spelling, or add the card that measures it - every "
                       "defect will fail on this line at run time."
                       % (kind, where, unknown, sorted(seen) or "none")))

    for i, item in enumerate(decide.let):
        check("working number '%s'" % (str(item.name).strip() or "#%d" % i),
              item.expr)
        name = str(item.name).strip()
        if name:
            seen.add(name)
            if str(getattr(item, "fill", "") or ""):
                seen.add(name + "_missing")
            if str(getattr(item, "scale", "") or ""):
                seen.add(name + "_raw")

    if decide.tree is not None:
        for when in _tree_whens(decide.tree):
            check("the question \"%s\"" % when, when)
    else:
        for i, rule in enumerate(decide.rules):
            check("rule %d (\"%s\")" % (i + 1, rule.when), rule.when)

    if str(decide.score or "").strip():
        check("the score", decide.score)
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
                        out.append(Issue(
                            code="routes-drift", level="warning", node_id=na,
                            title="Two routes use the same card with "
                                  "different settings",
                            detail="'%s' (route '%s') and '%s' (route '%s') "
                                   "are both %s, but %s. If that is "
                                   "deliberate, fine - this note is here so "
                                   "an edit on one side is not quietly "
                                   "forgotten on the other."
                                   % (na, ka, nb, kb,
                                      getattr(step_cls, "label", step_key),
                                      bits)))
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
        out.append(Issue(
            code="bad-route-by", level="error", node_id=None,
            title="route_by points at a route that does not exist",
            detail="%s are not among this recipe's routes (%s) - every defect "
                   "sent there would fail." % (missing, sorted(recipe.routes))))
    # 寫了但 route_by 指不到的 route：**永遠不會有人走**（route_by 存在時它
    # 覆蓋 kind 選路，§4.2），而寫了沒人走的路最容易爛。
    unreachable = sorted(set(recipe.routes) - set(targets))
    if unreachable:
        out.append(Issue(
            code="route-not-reachable", level="warning", node_id=None,
            title="Some routes can never be taken",
            detail="with route_by present, the route is picked per defect "
                   "from %s only - %s are defined but nothing maps to them, "
                   "so no defect will ever run them."
                   % (rb.column, unreachable)))
    return out


def _decide_from_json(raw: Any) -> Optional["DecideSpec"]:
    """讀 ``decide`` 區塊。**沒有就回 None** —— 那份 recipe 走 ``score`` 老路。

    格式錯要**當場講**而不是安靜地退回老路：安靜退回的話，一份打錯字的多類別
    recipe 會跑得完、有數字、而且每一顆都是 bin 0（推廣鐵則的老形狀）。
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise RecipeError("the 'decide' block must be an object (dict), got "
                          "%s" % type(raw).__name__)
    lets: List[Let] = []
    for i, item in enumerate(list(raw.get("let") or [])):
        if not isinstance(item, dict) or "name" not in item or "expr" not in item:
            raise RecipeError("decide.let[%d] must be an object with 'name' "
                              "and 'expr'" % i)
        lets.append(Let(name=str(item["name"]).strip(),
                        expr=str(item["expr"]),
                        scale=str(item.get("scale", "") or ""),
                        fill=str(item.get("fill", "") or "")))
    rules: List[Rule] = []
    for i, item in enumerate(list(raw.get("rules") or [])):
        if not isinstance(item, dict) or "when" not in item or "bin" not in item:
            raise RecipeError("decide.rules[%d] must be an object with 'when' "
                              "and 'bin'" % i)
        rules.append(Rule(when=str(item["when"]),
                          bin=_as_int(item["bin"], "decide.rules[%d].bin" % i),
                          label=str(item.get("label", "") or "")))
    other = raw.get("otherwise") or {}
    if not isinstance(other, dict):
        raise RecipeError("decide.otherwise must be an object with 'bin'")
    tree = (None if raw.get("tree") is None
            else _tree_from_json(raw.get("tree")))
    return DecideSpec(
        let=lets, rules=rules,
        otherwise_bin=_as_int(other.get("bin", 0), "decide.otherwise.bin"),
        otherwise_label=str(other.get("label", "") or ""),
        score=str(raw.get("score", "") or ""),
        tree=tree,
    )


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
_SINGLE_IMAGE_KINDS = ("rsem", "folder")


def _migrate_split_load_cards(nodes: Dict[str, "RecipeNode"],
                              routes: Dict[str, List[str]]) -> None:
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

    ⚠ **兩條 route 可以共用同一個節點**，而 v1 的雙輸入 recipe 正是那樣寫的
    （``dual_route_basic.json`` 的 ebi_patch 與 rsem 共用九個節點裡的八個，
    包含那張 load 卡）。就地換掉共用的那一張會**把另一條 route 弄壞** ——
    第一版這樣寫，黃金值當場抓到（patch 那 8 顆全部 ok=False：「這張卡只載一張圖，
    但這顆有 2 張」）。所以共用的情況要**多開一個節點**給單張那條 route 用，
    而不是改掉大家的那一張。
    """
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


def _migrate_folded_region_cards(nodes: Dict[str, "RecipeNode"]) -> None:
    """``roi_cross`` / ``roi_template`` → ``roi_reference`` ＋ 對應的 ``method``（F30）。

    使用者 2026-08-25：「把 Profile / Template 也折進 roi_reference」。四張
    Region 卡回答的是同一句話（「哪些地方應該長得一樣」），所以它們是一張卡的
    四個 method —— 跟 ``roi_from_mask``（F29）與 ``roi_compare``（F16）同一個
    形狀，連遷移的寫法都照抄。

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
    lets = [replace(l, expr=_renamed_idents(str(l.expr or ""), table))
            for l in decide.let]
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
        except Exception:              # noqa: BLE001 — 不認得的卡就跳過
            continue
        renames = getattr(step_cls, "legacy_feature_renames", None)
        if renames is None:
            continue
        try:
            out.update(renames(dict(node.params)))
        except Exception:              # noqa: BLE001 — 遷移不該讓開檔失敗
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
    from .engine import feature_prefixes        # 延後匯入：避免 import 迴圈

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
        except Exception:              # noqa: BLE001
            p = dict(node.params)
        try:
            feats = list(step_cls.resolve_features(p))
        except Exception:              # noqa: BLE001
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

    for node in nodes.values():
        if node.step == "feature_math" and node.params.get("expr"):
            node.params["expr"] = swap(node.params["expr"])
    expr = str(getattr(score, "expr", "") or "")
    new_expr = swap(expr)
    return score if new_expr == expr else replace(score, expr=new_expr)


@dataclass
class Recipe:
    """一份完整 recipe（單一 JSON 檔可互傳）。"""
    recipe_id: str
    routes: Dict[str, List[str]]      # dataset kind → 依序的節點 id（v1 線性）
    nodes: Dict[str, RecipeNode]
    score: ScoreSpec
    version: int = 1
    author: str = ""
    description: str = ""
    edges: List[Edge] = field(default_factory=list)   # 畫布上的線（見 Edge）
    #: **哪一版的 d4t 存的**（存檔時自動填；舊檔案沒有這欄，是空字串）。
    #:
    #: 為什麼需要：開發在家用機、執行在公司機，而公司機是用複製檔案更新的
    #: （`AGENTS.md`），所以兩邊的版本本來就會不同步。一份新版存的 recipe 在
    #: 舊版上打開，看到的是「unknown parameters: ['…']」—— 那句話的意思是
    #: 「這份檔案壞了」，但真正的情況是「我的程式舊了」。差一個字，使用者會去
    #: 重做一份 recipe 而不是去更新程式。
    #: 新建的 recipe 就是「這一版寫的」，所以預設值是現在這一版 ——
    #: 空字串保留給**舊檔案**（那些檔案是真的沒有這個欄位）。
    app_version: str = field(default_factory=_app_version)
    #: 多類別判定（F21-D）。``None`` = 這份 recipe 走 ``score`` 那條老路
    #: （一個位元都不動）。兩個都寫是 ``ambiguous-decision`` 的 error。
    decide: Optional["DecideSpec"] = None
    #: 分流（F23）。``None`` = 照舊用 dataset kind 選 route（一個位元都不動）。
    #: 有它時每一顆逐顆看 KLARF 的一欄決定走哪條 route（:func:`resolve_route`）。
    route_by: Optional["RouteBy"] = None

    # ---- JSON serde -------------------------------------------------------
    def to_json_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "recipe_id": self.recipe_id,
            "version": int(self.version),
            # 存檔時一律寫**現在這一版**（不是讀進來的那一版）——
            # 這個欄位要回答的是「這個檔案是誰寫的」。
            "app_version": _app_version(),
            "author": self.author,
            "description": self.description,
            "routes": {k: list(v) for k, v in self.routes.items()},
            "nodes": {
                nid: {
                    "step": n.step,
                    "params": dict(n.params),
                    "enabled": bool(n.enabled),
                }
                for nid, n in self.nodes.items()
            },
            "edges": [e.to_json() for e in self.edges],
            "score": {
                "expr": self.score.expr,
                "threshold": float(self.score.threshold),
                "bins": dict(self.score.bins),
            },
        }
        # **沒有就不寫這個鍵** —— 一份走老路的 recipe 存出來要跟以前逐位元組
        # 相同（`test_a_json_round_trip_changes_nothing` 與 export parity 都
        # 靠這件事）。
        if self.decide is not None:
            # ``scale`` / ``fill`` **有才寫**（嚴格附加）：沒用到的 recipe
            # 存出來要跟以前逐位元組相同。
            d_out: Dict[str, Any] = {
                "let": [dict(
                    {"name": x.name, "expr": x.expr},
                    **({"scale": x.scale} if str(
                        getattr(x, "scale", "") or "") else {}),
                    **({"fill": x.fill} if str(
                        getattr(x, "fill", "") or "") else {}))
                    for x in self.decide.let],
            }
            # 樹與清單**只寫在用的那一種** —— 兩個都寫出去，讀回來就是
            # `ambiguous-decision`，一份自己存的檔案不該把自己弄壞。
            if self.decide.tree is not None:
                d_out["tree"] = _tree_to_json(self.decide.tree)
            else:
                d_out["rules"] = [{"when": r.when, "bin": int(r.bin),
                                   "label": r.label}
                                  for r in self.decide.rules]
                d_out["otherwise"] = {"bin": int(self.decide.otherwise_bin),
                                      "label": self.decide.otherwise_label}
            d_out["score"] = self.decide.score
            out["decide"] = d_out
        # 同一條規矩：**沒有就不寫這個鍵**（嚴格附加，鐵則 9）。
        if self.route_by is not None:
            out["route_by"] = {"column": self.route_by.column,
                               "map": dict(self.route_by.map),
                               "default": self.route_by.default}
        return out

    @classmethod
    def from_json_dict(cls, d: Dict[str, Any]) -> "Recipe":
        if not isinstance(d, dict):
            raise RecipeError(f"the top level of a recipe JSON must be an object "
                              f"(dict), got {type(d).__name__}")
        # ``score`` **只有在沒有 ``decide`` 的時候才是必填**（2026-08-24）。
        # 兩者是二選一的契約（見 :class:`DecideSpec` 的說明），而硬性要求
        # ``score`` 等於逼一份判定樹 recipe 也帶一個它根本不用的區塊 ——
        # 手寫一份 decide recipe 會拿到「missing required fields: ['score']」，
        # 那句話對使用者是死路。自己存出來的檔案不受影響：:meth:`to_json_dict`
        # 一直都會寫 ``score``（空表達式），所以 round-trip 逐位元組不變。
        need = ["recipe_id", "routes", "nodes"]
        if "decide" not in d:
            need.append("score")
        missing = [k for k in need if k not in d]
        if missing:
            raise RecipeError(f"recipe JSON is missing required fields: {missing}")

        if not isinstance(d["nodes"], dict):
            raise RecipeError("recipe JSON field 'nodes' must be an object "
                              "(dict), got %s" % type(d["nodes"]).__name__)
        nodes: Dict[str, RecipeNode] = {}
        for nid, nd in dict(d["nodes"]).items():
            if not isinstance(nd, dict) or "step" not in nd:
                raise RecipeError(f"step '{nid}' has no 'step' field")
            raw_params = nd.get("params") or {}
            if not isinstance(raw_params, dict):
                raise RecipeError(
                    "the 'params' of step '%s' must be an object (dict), got %s"
                    % (nid, type(raw_params).__name__))
            nodes[str(nid)] = RecipeNode(
                id=str(nid),
                step=str(nd["step"]),
                params=dict(raw_params),
                enabled=bool(nd.get("enabled", True)),
            )

        sd = d.get("score") or {"expr": ""}
        if not isinstance(sd, dict) or "expr" not in sd:
            raise RecipeError(
                "the score block must be an object containing 'expr'")
        score = ScoreSpec(
            expr=str(sd["expr"]),
            threshold=_as_float(sd.get("threshold", 0.0), "score.threshold"),
            bins={str(k): _as_int(v, "score.bins[%r]" % str(k))
                  for k, v in dict(sd.get("bins") or {}).items()},
        )

        decide = _decide_from_json(d.get("decide"))
        route_by = _route_by_from_json(d.get("route_by"))

        if not isinstance(d["routes"], dict):
            raise RecipeError("recipe JSON field 'routes' must be an object "
                              "(dict) of route name -> list of step ids, got "
                              "%s" % type(d["routes"]).__name__)
        routes: Dict[str, List[str]] = {}
        for k, v in dict(d["routes"]).items():
            # ⚠ 字串也是可迭代的 —— ``"abc"`` 會安靜地變成三個節點 id。
            if not isinstance(v, (list, tuple)):
                raise RecipeError(
                    "route '%s' must be a list of step ids, got %s"
                    % (k, type(v).__name__))
            routes[str(k)] = [str(x) for x in v]

        edges: List[Edge] = [Edge.from_json(e) for e in (d.get("edges") or [])]

        # ── 遷移的鐵則：**只能靠「舊東西在不在」判斷，不能靠「新東西不在」** ──
        #
        # 下面三道都是看舊 key／舊值存不存在才動手，所以一份全新的 recipe 永遠
        # 不會被它們碰到。曾經有第四道不是這樣寫的（2026-08-14，subtract 的預設
        # 從 ref_aligned 改成 ref，於是「檔案裡沒寫 b」就補回 ref_aligned），
        # 而「檔案很舊、靠舊預設」跟「recipe 很新、靠新預設」這兩件事**從缺一個
        # key 是分不出來的**。後果是 :meth:`to_json_dict` → :meth:`from_json_dict`
        # 不再是 identity —— 而 ``run_batch`` 正是用這一對把 recipe 送進 worker
        # 行程的，所以同一份 recipe ``workers=1`` 算 test-ref、``workers=2`` 算
        # test-ref_aligned，兩邊都跑得完、都有數字、而且不一樣
        # （實測 glv_max 50 vs 43）。已於 2026-08-16 移除，迴歸測試見
        # ``tests/test_recipe.py::test_a_json_round_trip_changes_nothing``。
        #
        # 要改一個參數的預設值又要保住舊檔行為，就把新舊差異寫成**看得見的東西**
        # （改參數名、加一個值、寫 app_version），不要靠「沒寫」這個訊號。
        #
        # 舊 recipe（F7-18 之前）的 also_apply / anchor：展開成一張卡一條流。
        # 做在這裡而不是各張卡的 validate_params 裡，因為它會**增加節點**——
        # 那是 recipe 層級的事，一張卡看不到自己以外的東西。
        _migrate_also_apply(nodes, routes)
        # 再把合併掉的卡片名／參數名換過來（順序不可顛倒，見函式 docstring）。
        _migrate_merged_cards(nodes)
        # 最後把改過名的**參數值**換掉（F8：兩層的 dark/bright → 排名）。
        _migrate_renamed_values(nodes)
        # Input 卡按 source 拆成兩張之後，單張影像那條 route 要換卡（F11 Input-4）。
        _migrate_split_load_cards(nodes, routes)
        # roi_template 的一框一區域 → regions 字串（F11 Region-1）。
        _migrate_template_regions(nodes)
        # 只改了名字的卡（＋分數表達式裡它寫出來的 feature 名）。
        _migrate_renamed_cards(nodes)
        # GDS 那張卡收成「參照區域」的一個 method（F29）。
        _migrate_roi_from_mask_into_roi_reference(nodes)
        # Profile / Template 也折進去（F30）—— 四張 Region 卡變一張。
        _migrate_folded_region_cards(nodes)
        # 兩張 GLV 卡收成一張的兩個 method（F16）。
        _migrate_roi_compare_into_glv_stats(nodes)
        # 順序要緊：上面那一道會產生 ``method="compare"``，這一道再把它變成
        # ``reference``。反過來的話 roi_compare 的節點會漏掉第二段。
        _migrate_compare_method_into_reference(nodes)
        score = _migrate_renamed_features(score)
        # 相對量改叫 `cmp_*` 之後，舊表達式裡的 `epi_delta` 要跟著換
        # （順序要緊：上面兩道遷移跑完，節點的參數才是新的形狀）。
        renames = _compare_feature_renames(nodes)
        score = _rename_in_expr(score, renames)
        # **判定段吃同一張表**（F33）：F30 之後問問題的地方在這裡，
        # 改名只換 `score.expr` 的話樹上那一題會安靜地永遠答「否」。
        decide = _rename_in_decide(decide, renames)
        # ⚠ **撞名前綴那一道遷移不在這裡**（`_migrate_rescued_feature_names`）。
        # 它住在 :meth:`load` —— 理由見那一支的說明：這裡是「重建一個物件」，
        # 而那是 `run_batch` 送 recipe 進 worker 走的路。
        return cls(
            recipe_id=str(d["recipe_id"]),
            routes=routes,
            nodes=nodes,
            score=score,
            app_version=str(d.get("app_version", "") or ""),
            version=_as_int(d.get("version", 1), "recipe 'version'"),
            author=str(d.get("author", "")),
            description=str(d.get("description", "")),
            edges=edges,
            decide=decide,
            route_by=route_by,
        )

    @classmethod
    def load(cls, path: Any) -> "Recipe":
        """從磁碟讀一份 recipe。

        **這裡跟 :meth:`from_json_dict` 差一道遷移**，而那個差別是刻意的
        （F17 審查，2026-08-20）：

        * :meth:`from_json_dict` ＝ **重建一個物件**。``to_json_dict`` →
          ``from_json_dict`` 是 `run_batch` 送 recipe 進 worker 的路
          （`batch.py`），所以它**必須是 identity**（鐵則 9）——
          不是的話 ``workers=1`` 與 ``workers=2`` 會算出不同的分數。
        * :meth:`load` ＝ **讀一個檔案**。檔案是使用者留在磁碟上的舊東西，
          遷移屬於這一層。

        為什麼只有這一道搬過來、其他幾道留在 ``from_json_dict``
        --------------------------------------------------------
        其他幾道**冪等是構造上的**：``also_apply`` 被 pop 掉就不在了、改名的卡
        換成新 key 之後就不再符合舊 key。跑第二次是純粹的 no-op。

        `_migrate_rescued_feature_names` 沒有那個性質：**它換出來的新名字與它
        要換掉的舊名字活在同一個命名空間裡**。``<節點 id>_<特徵>`` 與
        ``<流名>_<特徵>`` 長得一模一樣，而節點 id **真的**可能等於流名 ——
        節點 id 就是 step key（`viewmodel._new_id`），而 `snr_map` 既是 step key
        也是那張卡吐出來的流名。實測過：一個叫 `test` 的節點會讓
        ``norm_clip_frac`` 第一次變成 ``test_clip_frac``、第二次變成
        ``diff_clip_frac``。

        所以它不能靠「寫得夠小心」冪等，要靠**根本不會跑第二次**。
        迴歸測試：`tests/test_recipe_roundtrip.py`。
        """
        with open(str(path), "r", encoding="utf-8") as f:
            d = json.load(f)
        recipe = cls.from_json_dict(d)
        # 撞名時「被蓋掉那份」的前綴：節點 id → 流名（F17-②）。
        # **排在所有遷移之後** —— 它問的是「這張卡讀／寫哪一條流」，而前面那幾道
        # 會換卡、拆卡、改參數，都會改變那個答案。
        return replace(recipe, score=_migrate_rescued_feature_names(
            recipe.nodes, recipe.score, recipe.routes))


# ---------------------------------------------------------------------------
# 執行順序（Kahn 拓撲排序，平手依 route 位置 → deterministic）
# ---------------------------------------------------------------------------
def execution_order(recipe: Recipe, kind: str) -> List[str]:
    """回傳 ``kind`` 這條 route 的節點執行順序。

    **邊只有一種來源：使用者拉的線**（``recipe.edges``，兩端都在該 route 內才
    算）。``route`` 的排列只當平手時的次序 —— 它是排版，不是語意。
    循環或未知 kind → :class:`RecipeError`。

    順序只有一個家（F17-①，2026-08-20）
    -----------------------------------
    在此之前這裡多做一件事：**把 route 上相鄰的每一對也當成一條邊** ——

    .. code-block:: python

        for a, b in zip(route, route[1:]):     # 沒有人拉過的線
            pair_edges.add((a, b))

    那串隱含邊構成一條走遍全部節點的鏈，所以執行順序**恆等於 route 順序**，
    而 route 順序在畫布上就是卡片的左右位置：**兩張沒有任何線相連的卡，誰先跑
    由使用者把它拖到哪裡決定**。鐵則 9 說「資料從哪來由線決定，而畫布上每一條
    線都是使用者拉的」是真的，但**執行順序的邊有一半不是線** —— UI 照純 DAG
    畫，引擎不照純 DAG 跑。那個落差正是「特徵沒有線」「Output 卡沒有埠」
    這一類問題的根（見 `docs/ARCHITECTURE.md`）。

    **拿掉它不會改變任何一份跑得起來的 recipe 的順序**，這是可以證明的：

    1. 隱含邊是一條 Hamiltonian path，所以舊的拓撲排序**唯一**，就是 route 順序；
    2. 一份今天跑得起來的 recipe，它的線必然都往前走（往回會跟隱含邊組成
       cycle，今天就開不起來）；
    3. 所有邊都往前 ⇒ Kahn 每一步的「位置最小的可執行節點」正好是 route 上的
       下一個 ⇒ 新的順序也是 route 順序。

    唯一的行為差異：**線與 route 順序矛盾**的 recipe 今天是 cycle 錯誤，
    之後會照線跑。那是改善（見 `docs/PITFALLS.md`）。
    """
    if kind not in recipe.routes:
        raise RecipeError(
            f"unknown input-type route '{kind}'; this recipe only defines: "
            f"{sorted(recipe.routes)}")
    route = list(recipe.routes[kind])
    if not route:
        return []
    pos = {nid: i for i, nid in enumerate(route)}
    node_set = set(route)

    pair_edges: Set[tuple] = set()
    for e in recipe.edges:
        # **只看 src/dst，不看埠。** F9-1 換的是資料形狀不是語意：執行順序必須
        # 跟換之前逐項相同（黃金值 `tools/freeze_golden.py` 對著這件事）。
        # 埠要到 F9-2 組每個節點的輸入時才有作用。
        if e.src in node_set and e.dst in node_set:
            pair_edges.add((e.src, e.dst))  # 自迴圈也收進來 → Kahn 會偵測為循環

    indeg = {n: 0 for n in route}
    adj: Dict[str, List[str]] = {n: [] for n in route}
    for a, b in pair_edges:
        adj[a].append(b)
        indeg[b] += 1

    heap = [pos[n] for n in route if indeg[n] == 0]
    heapq.heapify(heap)
    out: List[str] = []
    while heap:
        n = route[heapq.heappop(heap)]
        out.append(n)
        for m in sorted(adj[n], key=lambda x: pos[x]):
            indeg[m] -= 1
            if indeg[m] == 0:
                heapq.heappush(heap, pos[m])
    if len(out) != len(route):
        stuck = [n for n in route if n not in out]
        raise RecipeError(
            f"route '{kind}' has a cycle in its step connections, so no "
            f"execution order can be determined; stuck steps: {stuck}")
    return out


# ---------------------------------------------------------------------------
# lint 式驗證（KLIP Issue 風格：一次列出所有問題）
# ---------------------------------------------------------------------------
@dataclass
class Issue:
    """一條驗證發現：``level`` 為 "error" 或 "warning"。"""
    code: str
    level: str
    node_id: Optional[str]
    title: str
    detail: str


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
                        feat_owner: Dict[str, Any]) -> List["Issue"]:
    """這張卡寫的特徵有沒有蓋掉別張卡的（就地更新 ``feat_owner``）。

    後面的卡會**安靜地**蓋掉前面的（``Context.add_feature`` 允許覆寫，只在 meta
    留紀錄）。最典型的踩法是「量兩個 ROI」—— 兩張 glv_stats 都寫 glv_mean，
    跑完只剩後面那張的值，而分數表達式完全沒有辦法指到前面那一個。
    這是**警告**不是 error：同名覆寫有時是刻意的（例如重跑一次 normalize），
    但它必須看得見。

    抽成函式是因為 F11 Input-0 之後**入口卡也要跑這一段** —— 兩張 load 卡都寫
    `n_channels`。同一段判斷抄兩份的話，總有一份會長歪（這個 repo 記過三次）。
    """
    out: List[Issue] = []
    diag = set(step_cls.diagnostic_features(p))
    for f in step_cls.resolve_features(p):
        prev = feat_owner.get(f)
        owner, owner_diag = (prev if isinstance(prev, tuple) else (prev, False))
        # **兩邊都是診斷數字就不講**（F11 Enhance-3）：`clip_frac` 是每一張
        # Enhance 卡都會產出的，所以兩張 Enhance 卡必然撞名 —— 在每一份正常的
        # recipe 上都出現的警告會被學會忽略，而真的那一條也一起被忽略。
        # 值沒有丟（engine 救成 `<節點名>_clip_frac`），跳掉的只是那句話。
        if owner is not None and owner != nid and f in diag and owner_diag:
            feat_owner[f] = (nid, True)
            continue
        if owner is not None and owner != nid:
            out.append(Issue(
                code="feature-collision", level="warning", node_id=nid,
                title=f"step '{nid}' overwrites the feature '{f}'",
                detail=f"route '{k}': '{f}' is already produced by "
                       f"'{owner}'; the later value wins, so '{f}' in "
                       f"the score expression means this card's value. "
                       f"The earlier one is still available as "
                       f"'{owner}_{f}'. Give one of the two cards a "
                       f"different output name if that is clearer."))
        else:
            feat_owner.setdefault(f, (nid, f in diag))
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
        out.append(Issue(
            code="card-order", level="warning", node_id=nid,
            title=f"step '{nid}' undoes the manual tone adjustment before it",
            detail=(f"route '{k}': '{key}' goes through Adjust tone and then "
                    f"through this Normalize, which measures the image again "
                    f"and stretches it - so the brightness / gamma set by hand "
                    f"upstream is pulled back and has no effect on what gets "
                    f"measured. Put the manual card after the automatic one.")))
        break               # 一張卡一條訊息就夠（每條流各講一次是噪音）
    return out


def _uneven_treatment(step_cls, p: Dict[str, Any], nid: str, k: str,
                      history: Dict[str, List[Any]],
                      from_input: Set[str], registry) -> List[Issue]:
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
        v = str(p.get(spec.name, "") or "").strip()
        if v and v in from_input and v not in seen:
            seen.add(v)
            keys.append(v)
    if len(keys) < 2:
        return []
    a, b = keys[0], keys[1]
    ha, hb = history.get(a, []), history.get(b, [])
    if ha == hb:
        return []
    return [Issue(
        code="uneven-treatment", level="warning", node_id=nid,
        title=f"step '{nid}' compares two images that were not treated alike",
        detail=(f"route '{k}': {_how_they_differ(a, ha, b, hb, registry)}. "
                f"The two images are on different gray scales now, so this "
                f"card reports that difference as if it were a defect. Point "
                f"ONE Enhance card at both streams (a card can process several "
                f"streams with the same settings) instead of one card per "
                f"stream."))]


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

    檢查項（code）：unknown-step / bad-param / not-configured / unknown-node /
    unknown-route / cycle / missing-image / unknown-region / requires-ref /
    ambiguous-input / score-expr / unknown-feature（warning）/
    feature-collision（warning）/ bad-bins /
    uneven-treatment（warning）/ card-order（warning）。
    """
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
                issues.append(Issue(
                    code="bad-bins", level="error", node_id=None,
                    title="Incomplete bin settings",
                    detail=f"score.bins has no '{key}' (both below and above "
                           f"bin values are required); it currently has: "
                           f"{sorted(bins)}"))

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
            issues.append(Issue(
                code="unknown-route", level="error", node_id=None,
                title=f"Unknown input-type route '{kind}'",
                detail=f"this recipe only defines routes: "
                       f"{sorted(recipe.routes)}"))
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
            issues.append(Issue(
                code="unknown-step", level="error", node_id=nid,
                title=f"Unknown card '{node.step}'",
                detail=(f"step '{nid}' uses '{node.step}', which is not in the "
                        f"card library; available cards: {sorted(registry)}"
                        + (f"  {skew}" if skew else ""))))
            continue
        clean_params[nid] = _clean_params_for(step_cls, node.params, issues,
                                              nid, skew)

        # 參數全部合法，卡片還是可能**沒設定完**（F7-13）。空字串的模板是完全
        # 合法的 str —— 但那張卡跑起來每一顆都會失敗，而以前要跑過一次才知道。
        try:
            unset = list(step_cls.configuration_issues(clean_params[nid]))
        except Exception:                       # noqa: BLE001 — 卡片自己的程式
            unset = []
        for msg in unset:
            issues.append(Issue(
                code="not-configured", level="error", node_id=nid,
                title=f"{step_cls.label} is not set up yet", detail=str(msg)))

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
            issues.append(Issue(
                code="ambiguous-input", level="error", node_id=e.dst,
                title=f"step '{e.dst}' has two lines into the same input",
                detail=(f"both '{prev}' and '{e.src}' feed '{local}' into "
                        f"'{e.dst}'. Only one of them is used (the later one "
                        f"wins), so the other line does nothing. Delete the "
                        f"line you do not want.")))
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

    # ---- 每條 route：unknown-node / cycle / reads 模擬 / requires_ref ----
    for k in kinds:
        route = recipe.routes[k]
        for nid in route:
            if nid not in recipe.nodes:
                issues.append(Issue(
                    code="unknown-node", level="error", node_id=nid,
                    title=f"route '{k}' refers to a step that does not exist: "
                          f"'{nid}'",
                    detail=f"nodes has no '{nid}'; defined steps: "
                           f"{sorted(recipe.nodes)}"))
        try:
            order = execution_order(recipe, k)
        except RecipeError as e:
            issues.append(Issue(
                code="cycle", level="error", node_id=None,
                title=f"route '{k}' has a cycle in its step connections",
                detail=str(e)))
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
        #: 每一條流被哪幾張 Enhance 卡動過（照順序）。兩支 lint 都讀它 ——
        #: 「兩條流受到一樣的處理嗎」與「自動的排在手動的後面嗎」問的都是這段歷史。
        history: Dict[str, List[Any]] = {}
        #: 直接來自輸入卡的那幾條流。`diff` 這種中途產生的流不算 ——
        #: 拿它跟 `test` 比「處理歷史」沒有意義（來歷本來就不同）。
        from_input: Set[str] = set()
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
                issues.extend(_feature_collisions(step_cls, p, nid, k, feat_owner))
                feats |= set(step_cls.resolve_features(p))
                regions |= set(step_cls.resolve_regions_out(p))
                continue
            # **還沒接上來源**（F10）。這一條要排在 missing-image 前面，
            # 而且擋掉後面所有以「這張卡會產出什麼」為前提的檢查 ——
            # 一張沒有來源的卡什麼都不產出，拿它去比對下游只會生出一串
            # 指不到重點的錯誤（真正該講的只有一句：這張卡還沒有接上東西）。
            not_connected = step_cls.missing_inputs(p)
            if not_connected:
                labels = {s.name: (s.label or s.name) for s in step_cls.params}
                issues.append(Issue(
                    code="not-connected", level="error", node_id=nid,
                    title=f"step '{nid}' has no input yet",
                    detail=("route '%s': %s — drag a line from the card that "
                            "produces the image into this one. Available "
                            "upstream: %s"
                            % (k, ", ".join("“%s” is empty" % labels[n]
                                            for n in not_connected),
                               ", ".join(sorted(avail)) or "(nothing yet)")))
                )
                continue
            missing = [x for x in step_cls.resolve_reads(p) if x not in avail]
            if missing:
                issues.append(Issue(
                    code="missing-image", level="error", node_id=nid,
                    title=f"step '{nid}' is missing an upstream image",
                    detail=f"route '{k}': it needs image streams {missing}, but "
                           f"upstream only provides {sorted(avail)}"))
            if k == "rsem" and step_cls.resolve_requires_ref(p) \
                    and "ref" not in avail:
                issues.append(Issue(
                    code="requires-ref", level="error", node_id=nid,
                    title=f"step '{nid}' needs a reference image",
                    detail=f"'{node.step}' needs ref, but a single-image rsem "
                           f"input has none and no upstream card produces "
                           f"'ref' (currently provided: {sorted(avail)})"))
            # 具名區域走跟影像流一樣的檢查（F7-9）。沒有這一段的話，
            # 「量測卡指到沒人定義的區域」在跑之前是看不出來的 ——
            # 名字打錯要等執行期 StepError，而上游那張 Region 卡被拿掉更慘：
            # 它會安靜地退回量整張圖，跑得完、有數字、且是錯的。
            missing_roi = [x for x in step_cls.resolve_regions_in(p)
                           if x not in regions]
            if missing_roi:
                issues.append(Issue(
                    code="unknown-region", level="error", node_id=nid,
                    title=f"step '{nid}' uses a region nobody defines",
                    detail=f"route '{k}': it measures region(s) {missing_roi}, "
                           f"but no upstream card defines them (currently "
                           f"defined: {sorted(regions)}). Add a Region card "
                           f"upstream, or clear the roi parameter to measure "
                           f"the whole image."))

            # 吃**特徵**的卡（F16，Algo 段）：指到一個沒人算出來的數字，在跑
            # 之前就講。沒有這一段的話它要等**每一顆 defect 都失敗**才看得出來
            # —— 跟具名區域當初的處境一字不差（F7-9 的 unknown-region）。
            missing_feat = [x for x in step_cls.resolve_features_in(p)
                            if x not in feats]
            if missing_feat:
                issues.append(Issue(
                    code="unknown-feature-input", level="error", node_id=nid,
                    title=f"step '{nid}' uses a number nobody produces",
                    detail=f"route '{k}': it reads {missing_feat}, but no card "
                           f"before it in this route writes those out "
                           f"(available here: {sorted(feats) or 'none'}). "
                           f"Check the spelling, or move this card after the "
                           f"card that measures it."))

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
                    issues.append(Issue(
                        code="batch-card-has-downstream", level="error",
                        node_id=nid,
                        title=f"step '{nid}' runs once for the whole lot, so "
                              f"nothing can come after it",
                        detail=f"route '{k}': {downstream} take input from "
                               f"'{nid}', but that card only runs once every "
                               f"defect has already been through the pipeline "
                               f"— those cards would never receive anything. "
                               f"Remove the connection."))

            issues.extend(_feature_collisions(step_cls, p, nid, k, feat_owner))
            # 順序那一支看的是**這張卡之前**的歷史，所以要排在記錄之前。
            issues.extend(_late_normalize(step_cls, p, nid, k, history))
            issues.extend(_uneven_treatment(step_cls, p, nid, k, history,
                                            from_input, registry))
            if step_cls.resolve_group() == GROUP_ENHANCE:
                sig = _treatment_sig(step_cls, p)
                for key in step_cls.resolve_writes(p):
                    history.setdefault(key, []).append(sig)

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
                issues.append(Issue(
                    code="unknown-feature", level="warning", node_id=None,
                    title="Score expression uses unknown features",
                    detail=f"route '{k}': the variables {unknown} are not among "
                           f"the features this route produces ({sorted(feats)}), "
                           f"so the score may not be computable at run time"))
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

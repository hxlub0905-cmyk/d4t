# d4t pipeline engine — recipe 的資料模型（2026-09-24 從 recipe.py 拆出）.
"""Recipe 的**資料模型**：節點、線、判定樹、分流、版本號與它們的 JSON 形狀。

`recipe.py` 原本一支 4,522 行，schema、22 道遷移、lint 與執行順序全擠在一起。
拆成四支之後的分工：

* ``recipe_schema``（這一支）—— 資料長什麼樣。不 import 另外三支。
* ``recipe_migrations`` —— 舊檔案怎麼變成新形狀（鐵則 9：只看「舊東西在不在」）。
* ``recipe`` —— :class:`Recipe` 本人（``from_json_dict`` 在那裡依序叫遷移）與
  :func:`execution_order`；也是**對外唯一的入口**，其餘三支的名字都從那裡轉出口。
* ``recipe_validate`` —— lint（:func:`validate` 與它的幫手）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, Type

from d4t.core.log import swallowed

from .step import (
    REGION_TYPES,
    REGISTRY,
    Step,
)

if TYPE_CHECKING:
    from .recipe import Recipe


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
        raise RecipeError(
            "%s must be %s, got %r" % (where, kind, raw)) from None


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
    #: 這一類是好消息還是壞消息（F119）。見 :data:`OUTCOMES`。
    outcome: str = ""


#: `TreeLeaf.outcome` / `Rule.outcome` / `DecideSpec.otherwise_outcome`
#: 認得的值 —— **這一類是好消息還是壞消息**（F119）。
#:
#: 為什麼要有這個欄位（F117 D2）
#: -----------------------------
#: 判定膠囊的紅綠以前是**看 bin 的號碼**決定的（bin 1 綠、bin 0 紅），而
#: 號碼本身沒有意義 —— 意義是寫 recipe 的人給的。2026-09-20 量到的：三份
#: 出貨的 recipe **全部反了**（``nothing stands out`` 是紅的、``a spot
#: stands out`` 是綠的）。最高指導原則說「站點差異封裝進 recipe」，而
#: 「哪一個 bin 是好消息」正是站點自己說了算的東西。
#:
#: ⚠ **``""`` 是「還沒說」，不是「中性」。** 兩件事要分得出來：畫面對前者
#: 要講一句「這份 recipe 還沒說哪一類是好消息」，對後者不必。而**不准補一條
#: 「bin 0 一律是好消息」的猜測** —— 這次就是這樣錯的，而且
#: `rsem-worst-box` 的 bin 2（更多格不對）比 bin 1 更嚴重，任何按號碼排的
#: 規則都答不出來。
#:
#: 三個名字跟 `ui/theme.TOKENS` 的 ``chip_good_*`` / ``chip_bad_*`` /
#: ``chip_neutral_*`` **一比一**，中間不放翻譯表（那種表遲早會漂）。
OUTCOMES = ("", "good", "bad", "neutral")

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

    @property
    def is_blank(self) -> bool:
        """**整行都是空的** —— 每一格都沒填（F53，2026-08-28）。

        判定面板上按一下「+ Add a line」就會多一列空的，而在這之前那一列
        **立刻讓整份 recipe 跑不動**：`_decide_issues` 對它報兩條 error
        （沒有名字 ＋ 算式空的）。使用者按了三次就是六條，而工具列只講
        「and 5 more problems」—— 看起來像六個不同的毛病，其實是同一個東西
        的三份。真實案例：使用者 2026-08-28 拿一份 recipe 來問為什麼跑不動。

        所以空白的那一行**當成沒填**（同載入卡那兩格篩選的處理）。
        ⚠ **填了一半仍然要講話**：寫了算式沒取名字是真的錯（那個值誰都指不
        到），取了名字算式空的也是（每一顆都會失敗）。忽略的只有「什麼都
        沒填」那一種。

        **定義只有一個家。** 走 `decide.let` 的地方有四個（引擎、兩支 lint、
        `bound_specs`），而「什麼叫空白」抄四份的話，遲早有一個說引擎跳過
        了、lint 卻還在報。`tests/test_blank_let_lines.py` 掃那四處。
        """
        return not any(str(getattr(self, f, "") or "").strip()
                       for f in ("name", "expr", "scale", "fill"))


@dataclass(frozen=True)
class TreeLeaf:
    """判定樹的葉子：走到這裡就是這一類。"""
    bin: int
    label: str = ""
    #: 這一類是好消息還是壞消息（F119）。見 :data:`OUTCOMES`。
    outcome: str = ""


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


def let_names_written(decide: Optional["DecideSpec"],
                      upto: Optional[int] = None) -> List[str]:
    """判定段的 ``let`` 會寫進 features 的**每一個名字**，照行序（2026-09-09）。

    名字、有 ``fill`` 就多 ``<名字>_missing``、有 ``scale`` 就多
    ``<名字>_raw``（`engine._eval_decision` / `batch.apply_lot_scaling` 真的
    寫的那幾個）。``upto``＝只算前 n 行 —— 第 n 行 let 只看得到前 n−1 行。

    **一個家**：`_decide_unknown`（判定段自己的 lint）與 `validate` 裡
    Output 卡的 ``stale-feature-ref`` 都問它。以前前者把這條規則寫在自己的
    迴圈裡、後者根本不知道 let 存在 —— 於是一張 Output 卡的 ``rank_by`` 指到
    一個 working number 會被標成「nobody produces it」，而引擎那時候明明有它
    （整批一次的卡在每一顆判定完之後才跑）。
    """
    out: List[str] = []
    if decide is None:
        return out
    lets = list(decide.let)
    if upto is not None:
        lets = lets[:max(0, int(upto))]
    for item in lets:
        if item.is_blank:
            continue
        name = str(item.name).strip()
        if not name:
            continue
        out.append(name)
        if str(getattr(item, "fill", "") or ""):
            out.append(name + "_missing")
        if str(getattr(item, "scale", "") or ""):
            out.append(name + "_raw")
    return out


def _tree_to_json(node: Any) -> Dict[str, Any]:
    if isinstance(node, TreeLeaf):
        # ``outcome`` **有才寫**（嚴格附加，同 `Let.scale` / `fill`）：沒標的
        # recipe 存出來要跟以前逐位元組相同，所以這個欄位不必遷移，
        # `RECIPE_VERSION` 也不必動（F119 §3.3）。
        out = {"bin": int(node.bin), "label": node.label}
        if str(getattr(node, "outcome", "") or ""):
            out["outcome"] = str(node.outcome)
        return out
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
                        label=str(raw.get("label", "") or ""),
                        outcome=str(raw.get("outcome", "") or ""))
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
    #: 一條都沒對上的那一類是好消息還是壞消息（F119）。見 :data:`OUTCOMES`。
    otherwise_outcome: str = ""
    #: 這一顆的分數（KLARF 的 DSIZE／Top-N 排序要一個數字）。空字串 = 0.0。
    score: str = ""
    #: 判定樹（F24）。有它就走樹、忽略 ``rules``/``otherwise`` —— 但**兩個都
    #: 寫**是 `ambiguous-decision` 的 error（同 `score` vs `decide`：同一件事
    #: 兩個地方存，挑一個贏的話另一份會安靜地漂）。``rules`` 是它的特例
    #: （鏈狀樹，見 :func:`rules_to_tree`），所以舊寫法照讀不誤。
    tree: Any = None
    #: **問不出來的那一顆送去哪個 bin**（評價清單 #1，2026-09-24）。``None``
    #: ＝照 F30 的規則：問不出來的那一題算「否」，照樣往下走（預設、舊檔案）。
    #: 設了的話，只要有任何一題問不出來（``decide_unanswered > 0``），不管樹
    #: 走到哪裡，那一顆都改判進這個 bin —— 「量不到」就不會被當成一個有把握
    #: 的分類。JSON 是 ``decide.unanswered = {"bin": N, "label": "…"}``，**沒設
    #: 就不寫這個鍵**（嚴格附加：舊檔案 round-trip 一個 byte 都不變，不需要遷移）。
    unanswered_bin: Optional[int] = None
    unanswered_label: str = ""

    def entries(self) -> List[Tuple[int, str, str]]:
        """每一類的 ``(bin, 名字, 好壞)``，**照使用者由上往下讀的順序**。

        樹（有的話）→ 規則 → otherwise。`bin_labels` / `bin_outcomes` 與
        `validate` 的兩條 lint 都走這一支 —— 四個地方各走一次的那天，它們對
        「哪一片葉子排在前面」會有四個答案（而第一個贏就是靠那個順序）。

        ⚠ **不去重、不過濾**：判準住在呼叫端，因為它們不一樣（名字要非空、
        好壞要認得、lint 要看得到重複的那幾片）。
        """
        out: List[Tuple[int, str, str]] = []

        def _take(b: Any, label: Any, outcome: Any) -> None:
            try:
                out.append((int(b), str(label or ""), str(outcome or "")))
            except (TypeError, ValueError):
                return

        def _walk(node: Any) -> None:
            if node is None:
                return
            if isinstance(node, TreeLeaf):
                _take(node.bin, node.label, node.outcome)
                return
            _walk(getattr(node, "yes", None))
            _walk(getattr(node, "no", None))

        _walk(self.tree)
        for rule in self.rules:
            _take(rule.bin, rule.label, rule.outcome)
        _take(self.otherwise_bin, self.otherwise_label,
              self.otherwise_outcome)
        if self.unanswered_bin is not None:
            _take(self.unanswered_bin, self.unanswered_label, "")
        return out

    def bin_labels(self) -> Dict[int, str]:
        """``bin`` → 使用者給它的名字（沒取名的不在裡面）。

        **廠內講的是 real / nuisance 或某個 class name，不是 ``bin 1``**（X7）。
        那些名字本來就存得下來 —— `Rule.label`、`TreeLeaf.label`、
        `otherwise_label` 三個欄位從 F21-D／F24 起就在，只是**沒有人拿它們去
        畫**：判定 chip 上顯示的一直是 ``bin 1 · ≥ threshold``。這一支就是那條
        缺的路。

        同一個 bin 被取了兩個名字時**第一個贏**（由上往下讀，跟判定本身同一個
        方向）—— 不是挑最長的、也不是接起來：那兩種都會讓畫面上的字隨著一條
        不相干的規則改動而變，而使用者記住的是他自己打的第一個名字。

        ⚠ 這一支不 import Qt，也不該（鐵則 1）—— 它回一個 dict，UI 拿去畫。
        """
        out: Dict[int, str] = {}
        for b, label, _ in self.entries():
            if label.strip():
                out.setdefault(b, label.strip())
        return out

    def bin_outcomes(self) -> Dict[int, str]:
        """``bin`` → **這一類是好消息還是壞消息**（沒標的不在裡面）。

        跟 :meth:`bin_labels` 是同一個形狀、住在一起，因為它們是同一條路的
        兩半：判定膠囊上那一行字（名字）與那一行字的顏色（好壞），兩個都是
        **葉子上存得下來、而以前沒有人拿去畫**的東西。

        判準也逐字相同 —— **同一個 bin 被標了兩次時第一個贏**（由上往下讀，
        跟判定本身同一個方向）。標得不一致是使用者寫錯了，不是要猜的東西：
        `validate` 有一條 `conflicting-outcome` 會講。

        ⚠ **認不得的值當成沒標**（不在回傳裡）：一個打錯的 ``"gud"`` 不該
        變成一個猜出來的顏色。而「為什麼沒生效」留得下來 —— 同一條 lint。

        ⚠ 這一支不 import Qt，也不該（鐵則 1）—— 它回一個 dict，UI 拿去畫。
        """
        out: Dict[int, str] = {}
        for b, _, outcome in self.entries():
            text = outcome.strip()
            if text and text in OUTCOMES:
                out.setdefault(b, text)
        return out


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
                          "KLARF column to look at) and 'map' (value → route "
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


def is_region_edge(edge: "Edge", nodes: Dict[str, "RecipeNode"],
                   registry: Optional[Dict[str, Type[Step]]] = None) -> bool:
    """這條線是**區域線**嗎（F42 B1）——「``dst_in`` 指到的參數是不是區域」。

    **全 repo 只准用這一支判斷。** 方案 B 之後區域依賴跟影像流住在同一個
    ``recipe.edges`` 裡，而畫布、排版、引擎、健檢四個地方都要分得出兩種線。
    這種「同一個判斷抄四份」的形狀，這個 repo 記過三次 ——
    改動其中一份不會讓任何測試變紅，而長歪的那一份會讓畫布跟引擎說出不同的話。

    判準只有一件事：``dst_in`` 那一格的型別是不是 ``region_key`` /
    ``region_keys``（``step.REGION_TYPES`` 是那張表唯一的家）。**不看
    ``src_out``**，因為 ``src_out`` 是「哪一個區域」，而這裡問的是「這是不是
    區域線」—— 兩件事分開，一條還沒填來源的區域線才講得出它是什麼
    （那條線由 ``region-edge-no-port`` 講話）。

    **``dst_in`` 沒填就一律不是區域線。** 那不是漏判，是舊語意：埠空著的邊
    「只表達先後順序」（見 :class:`Edge` 與 :func:`execution_order`），
    分不出型別也就沒有區域可言。方案 B 因此規定區域線的 ``dst_in`` **必填**。

    參數用 ``nodes`` 而不是整份 :class:`Recipe`：一條 :class:`Edge` 身上只有
    節點 **id**，而型別住在下游那張**卡**上，所以節點表非進來不可 ——
    而收 ``nodes`` 讓 UI 的 ``RecipeModel.nodes`` 原樣就餵得進來
    （兩邊都是 ``Dict[str, RecipeNode]``），畫布才不必為了呼叫它先組一份
    ``Recipe``。
    """
    if registry is None:
        registry = REGISTRY
    # 這一行是**規則寫出來**，不是最佳化：下面那個迴圈也找不到叫 "" 的參數，
    # 所以拿掉它一條測試都不會紅。留著是因為「埠空著 = 只表達先後順序」是
    # 契約的一部分，而讓它只是「剛好沒有參數叫空字串」是一種靠巧合的正確。
    if not edge.dst_in:
        return False
    node = nodes.get(edge.dst)
    step_cls = registry.get(node.step) if node is not None else None
    if step_cls is None:
        return False
    for spec in step_cls.params:
        if spec.name == edge.dst_in:
            return spec.type in REGION_TYPES
    return False

#: 目前這一版 recipe 的形狀（F42 B3，2026-08-27）。
#:
#: 1 = 區域依賴存在**參數**裡（F12 §3）；
#: 2 = 存在**線**裡（方案 B）；
#: 4 = ``align`` 從「一條 moving 對一條 fixed，吐一條新流」變成「一組 streams
#:     就地對齊」（F109）。**這一道只能靠版本號判斷** —— 舊檔案的 `align`
#:     多半一個舊參數都沒寫（靠 `moving="ref"` / `out="ref_aligned"` 那組預設），
#:     而「舊檔案靠舊預設」跟「新 recipe 靠新預設」從缺一個 key 是分不出來的
#:     （鐵則 9 那個坑的原文就在下面 `from_json_dict` 裡）。
#:
#: 5 = `subtract` 拆成**比較卡**（留著 `subtract` 這個 key）與**融合卡**
#:     （新的 `combine`），而 `absolute`（bool）換成 `sign`（三選一）（F110）。
#:     換卡那一道看的是**舊的值**（``op`` 是不是 max/min/mean，合鐵則 9）；
#:     `absolute` 那一道跟第 4 版同一個理由只能靠版本號 —— 它有預設值，
#:     舊檔案多半沒寫它。
#:
#: 新建的 recipe 就是「這一版寫的」，所以 :class:`Recipe` 的預設值是它 ——
#: 那不是裝飾：遷移以 ``version < RECIPE_VERSION`` 為判準，而一份記憶體裡組出來
#: 的 recipe（Studio 的 ``to_recipe()``）也會走
#: ``to_json_dict → from_json_dict``（`run_batch` 送進 worker 的路）。
#: 預設留在 1 的話，**每一次送進 worker 都會再跑一次遷移**，而遷移會把版本號
#: 改成 2 —— 那一對就不再是 identity 了（鐵則 9）。
RECIPE_VERSION = 5


def _cycles_with(edges: List["Edge"], extra: "Edge",
                 nodes: Set[str]) -> bool:
    """``extra`` 加進去會讓 ``nodes`` 這組節點成環嗎（只看 src/dst）。

    遷移補線之前問這一句。真實的踩法只有一種形狀，而它**曾經**是真的存在的：
    **Profile 吃 roi_mask 吐的 mask 影像，而 roi_mask 又吃 Profile 定義的區域。**
    ⚠ ``roi_mask`` 2026-09-02 刪掉了，所以今天沒有一張卡組得出這個形狀（吃區域
    的只剩量測卡，而它們不吐影像流）。這道檢查**留著**：它是圖層級的規矩，而
    下一張「吃區域、吐影像流」的卡會讓那個形狀立刻回來。測試跟著搬到它真正住
    的那一層（``test_region_edges_migration::test_the_cycle_guard_is_graph_level``）
    —— 沒有那一步的話，證人一走，防線就跟著安靜消失。
    在 F12 的世界裡它跑得動 —— 順序由那條影像線決定，而區域那一半根本不在圖上。
    補上去就成環，`execution_order` 會 raise，一份今天跑得動的 recipe 明天打不開。

    所以那條線**不補**，而且不能安靜地不補（`region-has-no-line` 那條 lint）。
    """
    adj: Dict[str, List[str]] = {}
    indeg: Dict[str, int] = {n: 0 for n in nodes}
    seen: Set[Tuple[str, str]] = set()
    for e in list(edges) + [extra]:
        if e.src not in nodes or e.dst not in nodes:
            continue
        if (e.src, e.dst) in seen:
            continue
        seen.add((e.src, e.dst))
        adj.setdefault(e.src, []).append(e.dst)
        indeg[e.dst] = indeg.get(e.dst, 0) + 1
    queue = [n for n in nodes if indeg.get(n, 0) == 0]
    done = 0
    while queue:
        n = queue.pop()
        done += 1
        for m in adj.get(n, ()):
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    return done != len(nodes)


def _region_producer(name: str, route: List[str], upto: int,
                     nodes: Dict[str, "RecipeNode"],
                     registry: Dict[str, Type[Step]]) -> str:
    """誰定義了區域 ``name``（沒有人回空字串）—— 遷移補線用。

    語意跟 UI 的 ``RecipeModel.region_producer`` 一字不差：**取上游最後一個**
    （``ctx.set_roi`` 同名覆寫），而 B0 之後「最後一個」＝「唯一一個」。

    找不到就往**整條 route** 再找一次 —— 那是「參數指到排在下游的那張卡」
    的情形，而補了線之後 `execution_order` 會把順序排對。
    見 :func:`_migrate_region_params_into_edges` 的說明。
    """
    def owner_in(seq: List[str]) -> str:
        found = ""
        for nid in seq:
            node = nodes.get(nid)
            if node is None or not node.enabled:
                continue
            step_cls = registry.get(node.step)
            if step_cls is None:
                continue
            try:
                if name in step_cls.resolve_regions_out(
                        step_cls.validate_params(node.params)):
                    found = nid
            except Exception:  # 壞參數交給 validate
                swallowed("recipe._region_producer")
                continue
        return found

    return owner_in(route[:upto]) or owner_in(route)


def region_edge_values(nodes: Dict[str, "RecipeNode"],
                       edges: List["Edge"],
                       registry: Optional[Dict[str, Type[Step]]] = None
                       ) -> Dict[Tuple[str, str], str]:
    """每一格區域參數**線說它是什麼**：``(節點, 參數) → 值``（F42 B2）。

    方案 B 之後「用哪個區域」的唯一儲存是**線**（``src_out`` 那一欄），
    參數只是那條線的呈現 —— 跟 F12 §3 的方向正好相反，理由見那一輪的計畫書。
    這一支是那個換算的**唯一一份**：序列化（:meth:`Recipe.to_json_dict` 要知道
    哪幾格不必寫）、還原（:func:`hydrate_regions`）與 UI 的水合都問它。

    ``region_keys``（一串）**照 ``edges`` 的順序接起來**，``region_key``
    （單一角色）取**最後一條**——跟引擎的 ``ctx.set_roi`` 同名覆寫一字不差。
    順序取自 ``edges`` 而不是排序過的集合，因為那個順序要**穩定**：
    ``to_json_dict`` 丟掉那一格、``from_json_dict`` 再算回來，兩次算出來的
    字必須逐位元組相同，不然 ``run_batch`` 的 worker 拿到的 recipe 跟主行程
    的不一樣（鐵則 9）。
    """
    if registry is None:
        registry = REGISTRY
    order: List[Tuple[str, str]] = []
    got: Dict[Tuple[str, str], List[str]] = {}
    for e in edges:
        if not e.src_out or not is_region_edge(e, nodes, registry):
            continue
        key = (e.dst, e.dst_in)
        if key not in got:
            got[key] = []
            order.append(key)
        if e.src_out not in got[key]:
            got[key].append(e.src_out)
    out: Dict[Tuple[str, str], str] = {}
    for key in order:
        nid, pname = key
        step_cls = registry.get(nodes[nid].step)
        spec = next((sp for sp in step_cls.params if sp.name == pname), None)
        names = got[key]
        out[key] = ",".join(names) if (spec is not None
                                       and spec.type == "region_keys") \
            else names[-1]
    return out


def hydrate_regions(nodes: Dict[str, "RecipeNode"], edges: List["Edge"],
                    registry: Optional[Dict[str, Type[Step]]] = None
                    ) -> List[Tuple[str, str]]:
    """把區域線推回它落在的那一格參數（**就地**）；回傳被線管著的那幾格。

    這是 :meth:`Recipe.to_json_dict` 丟掉區域參數之後的**還原**那一半 ——
    兩邊算的是同一件事（:func:`region_edge_values`），所以
    ``to_json_dict → from_json_dict`` 仍然是 identity（鐵則 9）。

    ⚠ **只填有線的那幾格，不清空沒有線的。** 兩個理由：

    1. B3 之前的舊檔案，區域參數還沒有線 —— 那一格是它**唯一**的儲存。
       在這裡清掉等於每一份既有 recipe 安靜地改量整張圖。
    2. 「剪掉線＝那一格空掉」是**編輯**動作，住在畫布那一層
       （`studio._unpoint_stream` 與 `RecipeModel._hydrate_regions`）——
       那裡才知道「使用者剛剪了一條線」與「這份檔案還沒遷移」的差別。

    B3 之後每一格區域參數都有線，兩種講法就合而為一了。
    """
    values = region_edge_values(nodes, edges, registry)
    for (nid, pname), value in values.items():
        nodes[nid].params[pname] = value
    return list(values)


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
                          label=str(item.get("label", "") or ""),
                          outcome=str(item.get("outcome", "") or "")))
    other = raw.get("otherwise") or {}
    if not isinstance(other, dict):
        raise RecipeError("decide.otherwise must be an object with 'bin'")
    tree = (None if raw.get("tree") is None
            else _tree_from_json(raw.get("tree")))
    return DecideSpec(
        let=lets, rules=rules,
        otherwise_bin=_as_int(other.get("bin", 0), "decide.otherwise.bin"),
        otherwise_label=str(other.get("label", "") or ""),
        otherwise_outcome=str(other.get("outcome", "") or ""),
        score=str(raw.get("score", "") or ""),
        tree=tree,
        **_unanswered_from_json(raw.get("unanswered")),
    )


def _unanswered_from_json(raw: Any) -> Dict[str, Any]:
    """``decide.unanswered`` → DecideSpec 的兩個欄位（沒寫＝照舊，見 `unanswered_bin`）。"""
    if raw is None:
        return {}
    if not isinstance(raw, dict) or "bin" not in raw:
        raise RecipeError("decide.unanswered must be an object with 'bin'")
    return {"unanswered_bin": _as_int(raw["bin"], "decide.unanswered.bin"),
            "unanswered_label": str(raw.get("label", "") or "")}

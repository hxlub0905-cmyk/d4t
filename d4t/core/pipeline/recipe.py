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

- 每條 route 是線性鏈；``edges`` 是畫布上的線。
  執行順序 = route 相鄰對邊 ∪ edges（限制在該 route 內）的 Kahn 拓撲排序，
  平手時依 route 位置決定（deterministic）。
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
    GROUP_COMPARE, GROUP_ENHANCE, ParamError, Step, REGISTRY,
)

__all__ = [
    "RecipeError", "RecipeNode", "ScoreSpec", "Edge", "Recipe",
    "Issue", "execution_order", "validate",
]


class RecipeError(ValueError):
    """Recipe 結構性錯誤（循環、未知 route、JSON 缺欄位…）。"""


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
    """ADC 判定段：score 表達式 + 門檻 + bin 對應（{"below": 0, "above": 1}）。"""
    expr: str
    threshold: float
    bins: Dict[str, int]


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


def _rescued_name_renames(nodes: Dict[str, "RecipeNode"],
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
    """
    from .engine import feature_prefixes        # 延後匯入：避免 import 迴圈

    if registry is None:
        from .step import REGISTRY as registry  # type: ignore[no-redef]
    # **跟執行時同一支** —— 兩邊各算一次的話，遷移換出來的名字有機會跟引擎
    # 真的產出的名字不一樣，而那比不遷移更糟（表達式指到一個永遠不存在的數字）。
    holder = type("_R", (), {"nodes": nodes})()
    prefixes = feature_prefixes(list(nodes or {}), holder, registry)
    out: Dict[str, str] = {}
    for nid, node in (nodes or {}).items():
        step_cls = registry.get(node.step)
        if step_cls is None:
            continue
        try:
            p = step_cls.validate_params(dict(node.params))
        except Exception:              # noqa: BLE001
            p = dict(node.params)
        prefix = prefixes.get(nid, nid)
        if prefix == nid:
            continue                   # 名字沒變，沒得遷移
        try:
            feats = list(step_cls.resolve_features(p))
        except Exception:              # noqa: BLE001
            continue
        for f in feats:
            out["%s_%s" % (nid, f)] = "%s_%s" % (prefix, f)
    return out


def _migrate_rescued_feature_names(nodes: Dict[str, "RecipeNode"],
                                   score: "ScoreSpec") -> "ScoreSpec":
    """把舊的「節點 id 前綴」名字換成流名前綴 —— 分數表達式與 Algo 卡的算式。

    跟 :func:`_migrate_renamed_features` 一樣**只換整個識別字**（邊界比對），
    不做子字串取代。
    """
    renames = _rescued_name_renames(nodes)
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

    # ---- JSON serde -------------------------------------------------------
    def to_json_dict(self) -> Dict[str, Any]:
        return {
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

    @classmethod
    def from_json_dict(cls, d: Dict[str, Any]) -> "Recipe":
        if not isinstance(d, dict):
            raise RecipeError(f"the top level of a recipe JSON must be an object "
                              f"(dict), got {type(d).__name__}")
        missing = [k for k in ("recipe_id", "routes", "nodes", "score") if k not in d]
        if missing:
            raise RecipeError(f"recipe JSON is missing required fields: {missing}")

        nodes: Dict[str, RecipeNode] = {}
        for nid, nd in dict(d["nodes"]).items():
            if not isinstance(nd, dict) or "step" not in nd:
                raise RecipeError(f"step '{nid}' has no 'step' field")
            nodes[str(nid)] = RecipeNode(
                id=str(nid),
                step=str(nd["step"]),
                params=dict(nd.get("params") or {}),
                enabled=bool(nd.get("enabled", True)),
            )

        sd = d["score"]
        if not isinstance(sd, dict) or "expr" not in sd:
            raise RecipeError(
                "the score block must be an object containing 'expr'")
        score = ScoreSpec(
            expr=str(sd["expr"]),
            threshold=float(sd.get("threshold", 0.0)),
            bins={str(k): int(v) for k, v in dict(sd.get("bins") or {}).items()},
        )

        routes = {str(k): [str(x) for x in v] for k, v in dict(d["routes"]).items()}

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
        # 兩張 GLV 卡收成一張的兩個 method（F16）。
        _migrate_roi_compare_into_glv_stats(nodes)
        score = _migrate_renamed_features(score)
        # 撞名時「被蓋掉那份」的前綴：節點 id → 流名（F17-②）。
        # **一定要排在最後** —— 它問的是「這張卡讀／寫哪一條流」，而上面那幾道
        # 遷移會換卡、拆卡、改參數，都會改變那個答案。
        score = _migrate_rescued_feature_names(nodes, score)
        return cls(
            recipe_id=str(d["recipe_id"]),
            routes=routes,
            nodes=nodes,
            score=score,
            app_version=str(d.get("app_version", "") or ""),
            version=int(d.get("version", 1)),
            author=str(d.get("author", "")),
            description=str(d.get("description", "")),
            edges=edges,
        )

    @classmethod
    def load(cls, path: Any) -> "Recipe":
        with open(str(path), "r", encoding="utf-8") as f:
            d = json.load(f)
        return cls.from_json_dict(d)


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

    # ---- bins 必須含 below / above ----
    bins = recipe.score.bins or {}
    for key in ("below", "above"):
        if key not in bins:
            issues.append(Issue(
                code="bad-bins", level="error", node_id=None,
                title="Incomplete bin settings",
                detail=f"score.bins has no '{key}' (both below and above bin "
                       f"values are required); it currently has: "
                       f"{sorted(bins)}"))

    # ---- 要檢查哪些 route ----
    if kind is not None:
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
    expr = None
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
        if expr is not None:
            unknown = sorted(expr.variables - feats)
            if unknown:
                issues.append(Issue(
                    code="unknown-feature", level="warning", node_id=None,
                    title="Score expression uses unknown features",
                    detail=f"route '{k}': the variables {unknown} are not among "
                           f"the features this route produces ({sorted(feats)}), "
                           f"so the score may not be computable at run time"))

    return issues

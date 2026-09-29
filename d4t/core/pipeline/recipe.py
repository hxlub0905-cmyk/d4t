# d4t pipeline engine — authored 2026-07-28 (M1).
"""Recipe 模型：DAG JSON serde、執行順序（拓撲排序）、lint 式驗證。

Recipe JSON 形狀（見 docs/history/plans/F0-master-plan.md §3.4）：

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
import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Set, Tuple

from .step import (  # noqa: F401  有人從 recipe 拿 REGISTRY／Step 等（拆檔前就這樣）
    FEATURE_TYPES, GROUP_COMPARE, GROUP_ENHANCE, IMAGE_TYPES, REGION_TYPES,
    SCALE_LOT, SINGLE_IMAGE_KINDS, ParamError, Step, REGISTRY,
)

__all__ = [
    "RecipeError", "RecipeNode", "ScoreSpec", "Edge", "Recipe",
    "RouteBy", "resolve_route", "route_for", "route_miss_message",
    "Issue", "execution_order", "validate", "is_region_edge", "is_data_edge",
    "region_edge_values", "hydrate_regions", "RECIPE_VERSION",
    "describe_migration",
    "referenced_features",
]

# ⚠ 2026-09-24：recipe.py 拆成四支（見 `recipe_schema` 的檔頭）。這裡是對外
# 唯一的入口 —— 引擎、UI、測試照舊 `from .recipe import X`，所以另外三支的
# 名字全部從這裡轉出口（包括底線開頭的：測試直接叫某一道遷移）。
from .recipe_schema import (  # noqa: F401
    DecideSpec,
    Edge,
    LET_SCALES,
    Let,
    MAX_TREE_DEPTH,
    OUTCOMES,
    RECIPE_VERSION,
    RecipeError,
    RecipeNode,
    RouteBy,
    Rule,
    ScoreSpec,
    TreeLeaf,
    TreeStep,
    _app_version,
    _as_float,
    _as_int,
    _as_number,
    _cycles_with,
    _decide_from_json,
    _region_producer,
    _route_by_from_json,
    _tree_depth,
    _tree_from_json,
    _tree_to_json,
    _tree_whens,
    _version_tuple,
    hydrate_regions,
    is_data_edge,
    is_region_edge,
    let_names_written,
    region_edge_values,
    resolve_route,
    route_for,
    route_miss_message,
    rules_to_tree,
    version_skew,
)
from .recipe_migrations import (  # noqa: F401
    _ALSO_APPLY_CARDS,
    _ANCHOR_CARDS,
    _BUNDLE_OLD_CONTENTS,
    _FOLDED_CARD_OLD_DEFAULTS,
    _FOLDED_CARD_RENAMES,
    _FOLDED_OUTPUT_CARDS,
    _FOLDED_REGION_CARDS,
    _MERGED_CARDS,
    _RENAMED_CARDS,
    _RENAMED_FEATURES,
    _RENAMED_STREAM_PARAM,
    _RENAMED_VALUES,
    _SINGLE_IMAGE_KINDS,
    _compare_feature_renames,
    _fresh_id,
    _migrate_absolute_into_sign,
    _migrate_align_into_streams,
    _migrate_also_apply,
    _migrate_chart_params_into_look,
    _migrate_compare_method_into_reference,
    _migrate_data_lines,
    _migrate_decision_into_a_card,
    _migrate_drop_use_within,
    _migrate_folded_output_cards,
    _migrate_folded_region_cards,
    _migrate_glv_ref_pairing,
    _migrate_merged_cards,
    _migrate_output_image_into_bundle,
    _migrate_reference_into_ports,
    _migrate_region_params_into_edges,
    _migrate_renamed_cards,
    _migrate_renamed_features,
    _migrate_renamed_values,
    _migrate_rescued_feature_names,
    _migrate_roi_compare_into_glv_stats,
    _migrate_roi_from_mask_into_roi_reference,
    _migrate_single_into_input,
    _migrate_split_load_cards,
    _migrate_split_out_combine,
    _migrate_template_regions,
    _rename_in_decide,
    _rename_in_expr,
    _rename_in_node_params,
    _rename_in_tree,
    _renamed_idents,
    _rescued_name_renames,
    _swap_padded,
    describe_migration,
    feature_referrers,
    mentions_feature,
)


#: ``to_json_dict`` 問「這一格是不是線管的、而且值就是線說的」的那一句。
#: 抽出來只是為了讓上面那個 dict comprehension 讀得完；判斷本身仍然只有一份
#: （:func:`region_edge_values`）。找不到就回一個**不可能等於任何參數值**的
#: 哨兵，於是那一格照常寫出去。
_NOT_A_LINE = object()


def _region_line_says(recipe: "Recipe", nid: str, param: str) -> Any:
    return recipe._region_values().get((nid, param), _NOT_A_LINE)


@dataclass
class Recipe:
    """一份完整 recipe（單一 JSON 檔可互傳）。"""
    recipe_id: str
    routes: Dict[str, List[str]]      # route 鍵 → 節點 id（只有一條時鍵只是標籤，見 route_for）
    nodes: Dict[str, RecipeNode]
    score: ScoreSpec
    #: 這份 recipe 的形狀版本（見 :data:`RECIPE_VERSION`）。**預設是現在這一版**
    #: —— 新建的 recipe 就是這一版寫的，而遷移以 ``version < RECIPE_VERSION``
    #: 為判準：留在 1 的話，每一次送進 worker 都會再跑一次遷移（鐵則 9）。
    version: int = RECIPE_VERSION
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
    #: 分流（F23）。``None`` = 由 `route_for` 選 route（一條就是那一條，見那一支）。
    #: 有它時每一顆逐顆看 KLARF 的一欄決定走哪條 route（:func:`resolve_route`）。
    route_by: Optional["RouteBy"] = None

    # ---- JSON serde -------------------------------------------------------
    def _region_values(self) -> Dict[Tuple[str, str], str]:
        """這份 recipe 上每一格區域參數**線說它是什麼**（F42 B2）。

        壞掉的 recipe（認不得的卡、參數對不上）不准讓存檔爆掉 —— 存檔是
        「別弄丟我的工作」，不是「你做完了嗎」（見 :meth:`save`）。
        算不出來就當成一格都沒有線管，那一格照常寫出去。
        """
        try:
            return region_edge_values(self.nodes, self.edges)
        except Exception:  # 存檔不准因為健檢而失敗
            return {}

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
            # **線管著的區域參數不寫**（F42 B2）。「用哪個區域」的唯一儲存是
            # 那條線（``src_out``），而寫第二份的話兩份會漂 —— F9 記過的六個
            # 「跑得完、有數字、而且是錯的」有一半是這個形狀。
            #
            # 讀回來由 :func:`hydrate_regions` 算同一件事補回去，所以
            # ``to_json_dict → from_json_dict`` 仍然是 identity（鐵則 9）。
            # ⚠ 只丟**值跟線說的一模一樣**的那幾格：不一樣的時候丟掉就是改了
            # 使用者的 recipe，而那種不一致本身有斷言在畫布那一層擋。
            "nodes": {
                nid: {
                    "step": n.step,
                    "params": {k: v for k, v in n.params.items()
                               if _region_line_says(self, nid, k) != v},
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
                # ``outcome`` 有才寫 —— 同 `_tree_to_json` 那一段的理由。
                d_out["rules"] = [dict(
                    {"when": r.when, "bin": int(r.bin), "label": r.label},
                    **({"outcome": r.outcome} if str(
                        getattr(r, "outcome", "") or "") else {}))
                    for r in self.decide.rules]
                d_out["otherwise"] = dict(
                    {"bin": int(self.decide.otherwise_bin),
                     "label": self.decide.otherwise_label},
                    **({"outcome": self.decide.otherwise_outcome}
                       if str(self.decide.otherwise_outcome or "") else {}))
            d_out["score"] = self.decide.score
            if self.decide.unanswered_bin is not None:   # 沒設就不寫（嚴格附加）
                d_out["unanswered"] = {"bin": int(self.decide.unanswered_bin),
                                       "label": self.decide.unanswered_label}
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
                              "(dict) of route name → list of step ids, got "
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
        # Input 卡：F11 拆卡（只對第 1 版，見那一支）→ F121 期 2 把 `load_single` 併回。
        _migrate_split_load_cards(nodes, routes, d.get("version", 1))
        _migrate_single_into_input(nodes)
        # roi_template 的一框一區域 → regions 字串（F11 Region-1）。
        _migrate_template_regions(nodes)
        # 只改了名字的卡（＋分數表達式裡它寫出來的 feature 名）。
        _migrate_renamed_cards(nodes)
        # `roi_mask` 走了之後 normalize 的 `use_within` 那一格不存在了
        # （2026-09-02）。**要排在下面那幾道換卡的遷移之前**：它問的是
        # `node.step == "normalize"`，而那個 key 從來沒有被改過名，所以早跑
        # 晚跑都對 —— 排在這裡只是讓「拿掉一格」跟「換一張卡」讀起來分得開。
        _migrate_drop_use_within(nodes)
        # 圖表外觀六格收成一格（F87）。
        _migrate_chart_params_into_look(nodes)
        # GDS 那張卡收成「參照區域」的一個 method（F29）。
        _migrate_roi_from_mask_into_roi_reference(nodes)
        # Profile / Template 也折進去（F30）—— 四張 Region 卡變一張。
        _migrate_folded_region_cards(nodes)
        # 出圖那張卡折進報表資料夾那張（F37）。
        _migrate_output_image_into_bundle(nodes)
        # 四張報表卡再折進 `output_report`（F38）。**順序要緊**：上面那一道
        # 會產出 `output_bundle` 節點，而這一道要把它換成 `output_report` ——
        # 遷移鏈要一段一段接。寫一條 `output_image` 直達 `output_report` 的
        # 捷徑只有舊檔案會走到，永遠不會有人在上面測試。
        #
        # 也**必須在底下 `_compare_feature_renames` 之前**：改名是靠
        # `REGISTRY.get(node.step)` 找型別的，留在舊 key 上的節點對它是隱形的
        # —— 而 `plot_features` / `rank_by` 那幾格裝的正是特徵名。
        _migrate_folded_output_cards(nodes)
        # 兩張 GLV 卡收成一張的兩個 method（F16）。
        _migrate_roi_compare_into_glv_stats(nodes)
        # 順序要緊：上面那一道會產生 ``method="compare"``，這一道再把它變成
        # ``reference``。反過來的話 roi_compare 的節點會漏掉第二段。
        _migrate_compare_method_into_reference(nodes)
        # 「跟誰比」那一格 → 兩顆埠上的線（F67）。**順序要緊**：上面那一道會
        # 產生 ``reference``，而這一道是它的最後一段；而且要排在
        # `_compare_feature_renames` **前面** —— 那張改名表問的是「這張卡有沒有
        # 在比」，而 F67 之後那個問題的答案由這裡整理好的埠決定。
        _migrate_reference_into_ports(nodes, edges)
        score = _migrate_renamed_features(score)
        # 相對量改叫 `cmp_*` 之後，舊表達式裡的 `epi_delta` 要跟著換
        # （順序要緊：上面兩道遷移跑完，節點的參數才是新的形狀）。
        renames = _compare_feature_renames(nodes)
        score = _rename_in_expr(score, renames)
        # **判定段吃同一張表**（F33）：F30 之後問問題的地方在這裡，
        # 改名只換 `score.expr` 的話樹上那一題會安靜地永遠答「否」。
        decide = _rename_in_decide(decide, renames)
        # **參數值也吃同一張表**（F37）：Output 卡的 `rank_by` / `columns`
        # 那幾格裝的就是特徵名，而漏掉它們**跑得完** —— 排不出順序就安靜地
        # 退回檔案順序。同一張表第四個消費者，見 `_rename_in_node_params`。
        _rename_in_node_params(nodes, renames)
        # ⚠ **撞名前綴那一道遷移不在這裡**（`_migrate_rescued_feature_names`）。
        # 它住在 :meth:`load` —— 理由見那一支的說明：這裡是「重建一個物件」，
        # 而那是 `run_batch` 送 recipe 進 worker 走的路。
        #
        # 區域線推回參數（F42 B2）。**排在所有遷移的最後**：遷移會換卡、拆卡、
        # 改參數名，而「這條線落在哪一格」的答案跟著那些一起變 —— 而且 B3 那道
        # 遷移會**加線**，算在它前面就看不到那幾條。
        #
        # 這一步是 :meth:`to_json_dict` 丟掉區域參數的**還原**那一半，兩邊算的
        # 是同一件事，所以這一對仍然是 identity（鐵則 9）。它不是遷移：
        # 它對新舊檔案做完全一樣的事，而且跑第二次是 no-op。
        # 區域參數 → 線（F42 B3）。**以版本號為判準**，而且要排在
        # `hydrate_regions` **前面** —— 它補的線正是下一行要讀的東西。
        version = _as_int(d.get("version", 1), "recipe 'version'")
        if version < 5:
            _migrate_region_params_into_edges(nodes, routes, edges)
            # 逐框比較的參照怎麼取（F68）—— 舊檔案釘回當時的行為。
            _migrate_glv_ref_pairing(nodes)
            # align 換形狀（F109）—— 連下游指著 `ref_aligned` 的地方一起改。
            _migrate_align_into_streams(nodes, edges)
        if version < 6:      # 判定變成一張卡（F123 期 1）
            _migrate_decision_into_a_card(nodes, routes, decide, score)
        wire = version < 7   # 數字線與結果線（F123 期 2）—— 要整份 recipe，見下面
        version = max(version, RECIPE_VERSION)
        # F110：`subtract` 拆成比較卡與融合卡。**兩道都看舊的東西在不在**
        # （鐵則 9 的正牌用法），所以不掛在版本閘底下 —— 跑第二次是 no-op。
        # ⚠ 換卡那一道要排在 `absolute` 那一道**前面**：換完之後的節點已經不是
        # `subtract` 了，而 `absolute` 對融合卡沒有意義。
        _migrate_split_out_combine(nodes, edges)
        _migrate_absolute_into_sign(nodes)
        hydrate_regions(nodes, edges)
        rec = cls(
            recipe_id=str(d["recipe_id"]),
            routes=routes,
            nodes=nodes,
            score=score,
            app_version=str(d.get("app_version", "") or ""),
            version=version,
            author=str(d.get("author", "")),
            description=str(d.get("description", "")),
            edges=edges,
            decide=decide,
            route_by=route_by,
        )
        if wire:
            _migrate_data_lines(rec)
        return rec

    def save(self, path: Any) -> None:
        """寫成一份 recipe JSON（utf-8、``indent=2``、**atomic**，鐵則 5）。

        2026-08-26 做回來（2026-08-16 拿掉，理由是「先把整個 engine 用好，
        再來支援」）。使用者這一輪的話是「接下來幫我做一個重要的功能，
        存 recipe」—— Phase 1 已於 2026-08-16 收斂，那個前提到期了。

        **這一支跟 :meth:`load` 不是對稱的一對**，而那個不對稱是刻意的：

        * ``save`` 寫的永遠是 **現在這一版的形狀**（:meth:`to_json_dict` 會把
          ``app_version`` 蓋成現在這一版）—— 它回答的是「這個檔案是誰寫的」。
        * ``load`` 會多跑一道**只在讀檔案時才成立**的遷移
          （`_migrate_rescued_feature_names`，見那支的說明）。

        合起來的後果值得寫下來，因為它是這個功能真正的行為改變：**打開一份
        舊檔案再存回去，磁碟上的東西會被換成新形狀**（遷移過的名字、
        Studio 把門檻翻成的那棵樹）。那是對的 —— 使用者看到的就是新形狀，
        存出跟畫面不一樣的東西才是說謊 —— 但它不是 no-op，所以
        `StudioWindow._on_save_recipe` 會在覆寫別人的檔案時講一句話。

        ⚠ **不做驗證**。一份還在調、`validate` 有紅字的 pipeline 必須存得下來
        —— 存檔是「別弄丟我的工作」，不是「你做完了嗎」。健檢在畫布上一直都在
        講話，不必在這裡再擋一次。
        """
        path = str(path)
        tmp = path + ".tmp"
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.to_json_dict(), f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp, path)
        except BaseException:
            # ``json.dump`` 是**邊算邊寫**的，所以中途失敗會留下半份檔案。
            # 原檔沒事（還沒 replace），但那個 ``.tmp`` 會留在使用者的資料夾
            # 裡 —— 而它跟他要的檔案只差三個字元，看起來像是「存出來了」。
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

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

# lint 住在 `recipe_validate`；它延遲 import 這一支，所以轉出口放在最後。
from .recipe_validate import (  # noqa: E402,F401
    DECISION_ISSUE_CODES,
    Issue,
    NON_DECISION_NODELESS_CODES,
    Q,
    _chart_metric_issues,
    _clean_params_for,
    _content_written,
    _decide_issues,
    _decide_unknown,
    _doubled_names,
    _feature_collisions,
    _how_they_differ,
    _late_normalize,
    _outcome_issues,
    _param_diff_text,
    _region_collisions,
    _route_by_issues,
    _routes_drift_issues,
    _treatment_sig,
    _uneven_treatment,
    _wrong_content,
    card_name,
    closest,
    referenced_features,
    validate,
)

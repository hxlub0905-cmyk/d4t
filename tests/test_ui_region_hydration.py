# -*- coding: utf-8 -*-
"""區域參數 **＝ 線說的**（F42 方案 B 的 B2）。

F12 §3 定的是相反的方向：``roi="epi"`` 那個參數是唯一的儲存，線是它的呈現。
這一輪反過來 —— 線進了 ``recipe.edges``，參數變成**水合**出來的值。理由是
F12 §3 的前提（「route 相鄰對已經保證了順序」）在 F17-① 就失效了，
見 `docs/plans/F42-region-edges-plan-b.md`。

這一份鎖住五個入口與那條不變量
------------------------------
拉線、剪線、undo、redo、載檔 —— 五條路都要走同一支
``RecipeModel._hydrate_regions()``，而 `tests/conftest.py` 讓
``CHECK_REGION_INVARIANT`` 在**每一條測試**上常開：任何一次 model 改動之後，
「有線的那幾格 ≠ 線說的」就當場炸。

為什麼要一條常開的斷言而不是幾條測試：方案 B 的安全性建立在「用哪個區域只有
一個家」上，而破壞它的方式是**加一條新路徑**（一個忘了水合的新入口），
不是改壞既有的那五條。既有測試不會走那條還不存在的路徑。

⚠ **沒有線的那一格不在不變量裡**，而那是刻意的（見 `_hydrate_regions`
的說明）：那個狀態有兩種來歷，兩種都要留著 —— B3 之前的舊檔案（參數是它唯一
的儲存），以及打錯字的名字（`unknown-region` 那條 lint 守的東西）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from conftest import first_source                        # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication               # noqa: E402

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.recipe import (                   # noqa: E402
    Edge, Recipe, RecipeNode, ScoreSpec, execution_order, hydrate_regions,
    is_region_edge, region_edge_values,
)
from d4t.ui import studio as studio_mod                  # noqa: E402
from d4t.ui import theme as theme_mod                    # noqa: E402
from d4t.ui.viewmodel import RecipeModel                 # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


def _gds(window, layers: str = "1:epi, 2:mg"):
    """``load_single → roi_reference(GDS) → glv_stats``，線都接好了。"""
    src = first_source(window, "load_single")
    gds = window.add_card_after(src, "roi_reference")
    window.model.set_param(gds, "method", "layout layers")
    glv = window.add_card_after(gds, "glv_stats")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", layers)
    window._on_edge_added(src, glv, "single", "source")
    return src, gds, glv


def _region_edges(model):
    return [e for e in model.edges if is_region_edge(e, model.nodes)]


# --------------------------------------------------------------------------- #
# 1. 拉線 —— 線進 edges，參數是水合出來的
# --------------------------------------------------------------------------- #
def test_pulling_a_region_line_stores_a_real_edge(window):
    """F12 §3 推翻的那一句：區域線**現在**存進 `recipe.edges`。"""
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "roi")

    assert _region_edges(window.model) == [
        Edge(src=gds, dst=glv, src_out="epi", dst_in="roi")]
    assert window.model.nodes[glv].params["roi"] == "epi"


def test_the_parameter_is_what_the_line_says_not_the_other_way_round(window):
    """換個問法：**線是儲存**。把線改掉，那一格跟著走。"""
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "roi")
    window._on_edge_added(gds, glv, "mg", "roi")
    assert window.model.nodes[glv].params["roi"] == "epi,mg"
    assert region_edge_values(window.model.nodes, window.model.edges) == {
        (glv, "roi"): "epi,mg"}


def test_a_role_port_replaces_instead_of_accumulating(window):
    """``region_key``（單一角色）第二條線是**取代**（F12 §7-②）。

    影像那邊同一條規矩由 `_drop_conflicting_edges` 執行；區域這邊更簡單 ——
    同一格上的舊線全部讓位，所以那一格只放得下一個名字這件事是**結構性**的。
    """
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "reference_region")
    window._on_edge_added(gds, glv, "mg", "reference_region")

    on = [e for e in _region_edges(window.model)
          if e.dst_in == "reference_region"]
    assert on == [Edge(src=gds, dst=glv, src_out="mg",
                       dst_in="reference_region")], "舊線沒有跟著消失"
    assert window.model.nodes[glv].params["reference_region"] == "mg"


# --------------------------------------------------------------------------- #
# 2. 剪線
# --------------------------------------------------------------------------- #
def test_cutting_the_line_removes_the_edge_and_empties_the_box(window):
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "roi")
    window._on_edge_removed(gds, glv, "epi", "roi")

    assert _region_edges(window.model) == []
    assert window.model.nodes[glv].params["roi"] == ""


def test_cutting_one_of_two_lines_leaves_the_other(window):
    """一串（``region_keys``）剪掉一條，剩下的那條說了算 —— 不是整格空掉。"""
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "roi")
    window._on_edge_added(gds, glv, "mg", "roi")
    window._on_edge_removed(gds, glv, "epi", "roi")

    assert window.model.nodes[glv].params["roi"] == "mg"


def test_deleting_the_region_card_empties_the_box(window):
    """刪掉定義它的那張卡 = 線跟著走 = 那一格空掉。

    以前 `studio._on_remove_requested` 得自己再清一次（區域線是推導的，
    沒有 Edge 可刪）。現在它是水合的自然結果。
    """
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "roi")
    window._on_remove_requested(gds)
    assert window.model.nodes[glv].params["roi"] == ""


# --------------------------------------------------------------------------- #
# 3. undo / redo —— 不信任快照裡的區域參數
# --------------------------------------------------------------------------- #
def test_undo_and_redo_keep_the_box_and_the_line_together(window):
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "roi")
    assert window.model.nodes[glv].params["roi"] == "epi"

    assert window.model.undo()
    assert _region_edges(window.model) == []
    assert window.model.nodes[glv].params["roi"] == ""

    assert window.model.redo()
    assert len(_region_edges(window.model)) == 1
    assert window.model.nodes[glv].params["roi"] == "epi"


def test_undo_does_not_trust_a_snapshot_that_disagrees_with_its_lines(window):
    """快照存的是兩份東西（線與參數），而它們講的是同一件事。

    只要有一條路徑寫錯了一邊，復原就會把那個不一致原樣端回畫面上，
    **而且從此活下去** —— 所以復原之後重算一次，不信任快照。

    這裡把快照弄壞（模擬那條寫錯的路徑），然後要求 undo 把它修回來。
    """
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "roi")
    window.model.set_param(glv, "min_pixels", 3)  # 隨便一步，好讓 undo 有東西可退

    # 上一份快照裡的 roi 被動了手腳（線還在，值變成別的）。
    snap = window.model._undo[-1]
    step, params, enabled = snap["nodes"][glv]
    snap["nodes"][glv] = (step, dict(params, roi="mg"), enabled)

    assert window.model.undo()
    assert window.model.nodes[glv].params["roi"] == "epi", \
        "復原之後那一格要重新照線算，不是照快照抄"


# --------------------------------------------------------------------------- #
# 4. 載檔 —— 線推回參數
# --------------------------------------------------------------------------- #
def test_loading_a_recipe_hydrates_the_boxes_from_its_lines(window):
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "roi")
    kind = window.model.kind
    doc = json.loads(json.dumps(window.model.to_recipe().to_json_dict()))

    assert "roi" not in doc["nodes"][glv]["params"], \
        "線管著的那一格不該再寫進 JSON —— 那就是第二個家"
    again = RecipeModel.from_recipe(Recipe.from_json_dict(doc), kind=kind)
    assert again.nodes[glv].params["roi"] == "epi"


def test_an_old_style_box_with_no_line_is_left_alone(window):
    """B3 之前的舊檔案：區域參數還沒有線，那一格是它**唯一**的儲存。

    在載入時清掉的話，每一份既有 recipe 打開就安靜地少量一塊 —— 而那正是
    F7-9 的 `unknown-region` 當初要擋的那種「跑得完、有數字、而且是錯的」。
    """
    model = RecipeModel(kind="rsem")
    img = model.add_step("load_single")
    gds = model.add_step("roi_reference")
    glv = model.add_step("glv_stats")
    model.set_param(gds, "method", "layout layers")
    model.set_param(gds, "layers", "1:epi")
    model.set_param(glv, "source", "single")
    model.set_param(glv, "roi", "epi")         # 舊世界：用打的，沒有線
    assert model.edges == [] and img

    again = RecipeModel.from_recipe(model.to_recipe(), kind="rsem")
    assert again.nodes[glv].params["roi"] == "epi"
    assert _region_edges(again) == []


def test_a_typo_keeps_its_name_so_the_lint_can_still_say_so(window):
    """指到一個沒有人定義的區域 —— 那個字要**留著**。

    看不到就被靜靜刪掉是最糟的一種「幫忙」：清掉之後 `unknown-region` 問不到
    它，而 `glv_stats` 的空 ``roi`` 是完全合法的「量整張圖」。
    """
    model = RecipeModel(kind="rsem")
    model.add_step("load_single")
    glv = model.add_step("glv_stats")
    model.set_param(glv, "source", "single")
    model.set_param(glv, "roi", "nope")

    again = RecipeModel.from_recipe(model.to_recipe(), kind="rsem")
    assert again.nodes[glv].params["roi"] == "nope"
    assert "unknown-region" in [i.code for i in again.validate()]


# --------------------------------------------------------------------------- #
# 5. 序列化 —— 一個家，而且 round-trip 逐位元組相同（鐵則 9）
# --------------------------------------------------------------------------- #
def test_a_hydrated_box_is_not_written_twice(window):
    """線管著的那一格**不寫進 JSON**。寫了就是第二個家，而兩份會漂。"""
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "roi")
    doc = window.model.to_recipe().to_json_dict()
    assert "roi" not in doc["nodes"][glv]["params"]
    assert [gds, "epi", glv, "roi"] in doc["edges"]


def test_the_round_trip_is_still_identity(window):
    """``to_json_dict → from_json_dict`` 是 `run_batch` 送 recipe 進 worker
    的路。它一旦不是 identity，``workers=1`` 與 ``workers=2`` 會算出不同的
    分數 —— 而區域參數掉一格的後果正好是「量整張圖 vs 量那一塊」。"""
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "roi")
    rec = window.model.to_recipe()
    again = Recipe.from_json_dict(json.loads(json.dumps(rec.to_json_dict())))
    assert again == rec
    assert again.nodes[glv].params == rec.nodes[glv].params
    assert again.to_json_dict() == rec.to_json_dict()


def test_a_box_that_disagrees_with_its_line_is_written_out_anyway():
    """**只丟值跟線說的一模一樣的那幾格。**

    不一樣的時候丟掉就是改了使用者的 recipe（而且是安靜地改）。畫布那一層
    有常開的斷言擋這種不一致，序列化這一層的責任只有一個：別弄丟東西。
    """
    rec = Recipe(
        recipe_id="t", routes={"rsem": ["r", "g"]},
        nodes={"r": RecipeNode("r", "roi_reference",
                               {"method": "layout layers",
                                "layers": "1:epi", "label_source": "lbl"}),
               "g": RecipeNode("g", "glv_stats",
                               {"source": "test", "roi": "mg"})},
        edges=[Edge("r", "g", "epi", "roi")],       # 線說 epi，那一格寫 mg
        score=ScoreSpec(expr="1", threshold=0.0, bins={"below": 0, "above": 1}))
    doc = rec.to_json_dict()
    assert doc["nodes"]["g"]["params"]["roi"] == "mg", "不一致的值不准被丟掉"


# --------------------------------------------------------------------------- #
# 6. 核心那一支 —— 只填不清
# --------------------------------------------------------------------------- #
def test_the_core_hydration_only_fills_it_never_clears():
    """`recipe.hydrate_regions` 服務的是 ``from_json_dict``，而 B3 之前的
    舊檔案沒有區域線 —— 在那裡清空等於每一份既有 recipe 都被改掉。

    「剪掉線＝那一格空掉」是**編輯**動作，住在畫布那一層。
    """
    nodes = {"g": RecipeNode("g", "glv_stats",
                             {"source": "test", "roi": "epi"})}
    hydrate_regions(nodes, [])                 # 一條線都沒有
    assert nodes["g"].params["roi"] == "epi"

    hydrate_regions(nodes, [Edge("r", "g", "mg", "roi")])
    assert nodes["g"].params["roi"] == "mg", "有線的時候線說了算"


def test_the_region_edge_orders_the_route_after_a_round_trip(window):
    """B1 修的那個 bug 的**端對端**版：Region 卡在量測卡右邊，存檔、讀回來，
    順序仍然是 ROI 先 —— 因為那條線現在真的在 `recipe.edges` 裡。"""
    _src, gds, glv = _gds(window)
    window._on_edge_added(gds, glv, "epi", "roi")
    kind = window.model.kind
    rec = window.model.to_recipe()
    # 把 route 的排列改成「量測卡在前」（畫布上把 Region 卡拖到右邊）。
    rec.routes[kind] = ([n for n in rec.routes[kind] if n not in (gds, glv)]
                        + [glv, gds])
    again = Recipe.from_json_dict(json.loads(json.dumps(rec.to_json_dict())))
    order = execution_order(again, kind)
    assert order.index(gds) < order.index(glv)


# --------------------------------------------------------------------------- #
# 7. 兩件工作單點名、而答案是「本來就對」的事
# --------------------------------------------------------------------------- #
def test_comparing_against_the_other_boxes_is_a_second_line(window):
    """「跟其餘那些比」F67 起就是把 ``epi_others`` 接進參照那顆埠。

    以前它是 ``reference="the other regions"``：**沒有**自己的那一格，所以
    沒有埠 —— ``epi_others`` 從 ``roi`` 算出來，而它跟 ``epi`` 出自同一張
    Region 卡（`_util.region_family` 一次吐三個名字），所以接進 ``roi`` 的
    那條線「已經指著定義它的那張卡了」。

    那句話對**引擎**是對的，對**使用者**不是：畫面上兩張卡之間只有一條線，
    而那條線講不出「這張卡在跟其餘那些比」。同一件事因此有兩種寫法（一種看
    得見、一種看不見），而 F44 教使用者的是看得見那一種。F67 收成一種。
    """
    from d4t.core.pipeline import get_step

    _src, gds, glv = _gds(window, layers="1:epi")
    window._on_edge_added(gds, glv, "epi", "roi")
    window._on_edge_added(gds, glv, "epi_others", "reference_region")

    cls = get_step("glv_stats")
    params = window.model.nodes[glv].params
    assert "epi_others" in cls.resolve_regions_in(params)
    assert params["reference_region"] == "epi_others"
    # 兩條線，同一張 Region 卡 —— 而**兩條都畫得出來**（那是重點）。
    assert _region_edges(window.model) == [
        Edge(src=gds, dst=glv, src_out="epi", dst_in="roi"),
        Edge(src=gds, dst=glv, src_out="epi_others", dst_in="reference_region")]
    assert "unknown-region" not in [i.code for i in window.model.validate()]


def test_the_intent_row_says_what_the_buttons_leave_out(window):
    """**鈕 ＋ note ＝ 這張卡真的在做的事**（F67 續）。

    走的是真的那條路（選卡 → `_sync_glv_intent` → 表單那一排），因為這一條
    要守的正是**畫面上**那行字 —— model 算得對而沒有人畫出來是同一種說謊。
    """
    _src, gds, glv = _gds(window, layers="1:epi, 2:mg")
    window._on_edge_added(gds, glv, "epi", "roi")
    window.select_node(glv)
    form = window.param_form
    assert form.has_intent_row()
    assert form.intent_buttons()["region_stats"].isChecked()
    assert window.model.glv_intent_note(glv) == "", "三顆鈕已經說完了"

    # 接一條參照**流** —— 鈕不覆蓋那一軸，所以那行字要補上它
    window.model.set_param(glv, "reference_source", "ref")
    window.select_node(glv)
    assert form.intent_buttons()["region_stats"].isChecked(), \
        "跟另一張圖比是疊上去的第二個問題，不是第四種形狀"
    assert window.model.glv_intent_note(glv) == \
        "measuring epi, compared against epi @ ref."

    # 接一條參照**區域**（不是 `_center` 那組）—— 三顆都對不上
    window._on_edge_added(gds, glv, "mg", "reference_region")
    window.select_node(glv)
    assert not any(b.isChecked() for b in form.intent_buttons().values())
    assert window.model.glv_intent_note(glv) == \
        "custom - measuring epi, compared against mg @ ref."


def test_a_region_line_now_moves_the_layout(window):
    """**接受的代價**（工作單 B2-6）：`add_edge` 會重排 ``node_order``，
    所以拉一條區域線之後排版會動 —— 以前不會，因為它根本不在 `edges` 裡。

    那是對的：它一直都是一條真的依賴，只是以前畫布看得到、引擎看不到。
    這裡把它釘成一條測試，免得下一個人以為那是 bug。
    """
    src = first_source(window, "load_single")
    glv = window.add_card_after(src, "glv_stats")
    gds = window.add_card_after(glv, "roi_reference")   # Region 卡在量測卡右邊
    window.model.set_param(gds, "method", "layout layers")
    window._on_edge_added(src, gds, "single", "label_source")
    window.model.set_param(gds, "layers", "1:epi")
    window._on_edge_added(src, glv, "single", "source")
    order = list(window.model.node_order)
    assert order.index(glv) < order.index(gds), "接線之前它排在後面"

    window._on_edge_added(gds, glv, "epi", "roi")
    moved = list(window.model.node_order)
    assert moved.index(gds) < moved.index(glv), \
        "區域線是一條真的依賴 —— 排版跟著它走"


def test_the_ui_and_the_core_agree_on_who_defines_a_region(window):
    """便利貼（F42 B4）：``RecipeModel.region_producer`` 在 `d4t/` 底下**沒有
    呼叫者了** —— 它的消費者 `region_lines()` 在 B4 刪掉。

    它是刻意留著的（工作單指名保留），而留著的理由是它回答的問題還在，
    **而且核心那一份還在用同一個語意**：`recipe._region_producer` 是遷移補線
    時找來源的那一支。兩邊逐字相同（「上游最後一個」），要動那個語意的時候
    兩邊要一起動。

    沒有這一條的話，下一個人會把它當死碼順手清掉 —— 這個 repo 對
    `algo/period.py` 差一步就做過同一件事（`CLAUDE.md` §5 那張便利貼）。
    """
    from d4t.core.pipeline.recipe import _region_producer
    from d4t.core.pipeline.step import REGISTRY

    _src, gds, glv = _gds(window, layers="1:epi")
    model = window.model
    assert model.region_producer("epi", before_node=glv) == gds

    route = list(model.node_order)
    assert _region_producer("epi", route, route.index(glv),
                            model.nodes, REGISTRY) == gds

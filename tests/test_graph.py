"""F9 Phase 2 驗收：**線就是資料通道**。

這一支釘的是「換了執行模型之後，畫布不再說謊」的那幾條性質。舊行為由既有的
`test_engine.py` / `test_batch_cache.py` / `test_e2e_*.py` 守著（那些一個字都
沒改，全綠就表示線性 pipeline 的結果沒有變）。

dummy Step 以 "t_g_" 前綴註冊，teardown 一律 pop 掉（沿用 test_engine 的規矩）。
"""
from __future__ import annotations

import numpy as np
import pytest

from adept.core.pipeline import (
    CATEGORY_ALGO,
    CATEGORY_IMAGE,
    Context,
    REGISTRY,
    Recipe,
    RecipeNode,
    ScoreSpec,
    Step,
    register_step,
    run_defect,
)
from adept.core.pipeline.graph import Packet, Wire, compile_recipe, run_graph

_KEYS = ["t_g_load", "t_g_gain", "t_g_peak", "t_g_route"]


@pytest.fixture()
def cards():
    for k in _KEYS:
        REGISTRY.pop(k, None)

    @register_step
    class TLoad(Step):
        key = "t_g_load"
        label = "測試載入"
        category = CATEGORY_IMAGE
        help = "測試用：造一張 test 影像"
        writes = ["test"]

        def run(self, ctx: Context, params) -> Context:
            item = ctx.meta["_defect_item"]
            ctx.set_image("test", np.full((4, 4), float(item.level), np.float32))
            return ctx

    @register_step
    class TGain(Step):
        key = "t_g_gain"
        label = "測試放大"
        category = CATEGORY_IMAGE
        help = "測試用：把 test 乘上 gain"
        reads = writes = ["test"]

        def run(self, ctx: Context, params) -> Context:
            # **產生新陣列，不就地改寫**（F9 §4.1 對卡片作者的規矩）
            ctx.set_image("test", ctx.require_image("test") * 2.0)
            ctx.warn("gain ran")
            return ctx

    @register_step
    class TPeak(Step):
        key = "t_g_peak"
        label = "測試量測"
        category = CATEGORY_ALGO
        help = "測試用：量 test 的最大值"
        reads = ["test"]
        features_out = ["peak"]

        def run(self, ctx: Context, params) -> Context:
            ctx.add_feature("peak", float(ctx.require_image("test").max()))
            return ctx

    @register_step
    class TRoute(Step):
        key = "t_g_route"
        label = "測試分流"
        category = CATEGORY_ALGO
        help = "測試用：依 item.klass 決定從哪個埠吐出去"
        inputs = ("in",)
        outputs = ("match", "else")

        def run(self, ctx: Context, params):
            hit = int(ctx.meta["_defect_item"].klass) == 1
            return {"match" if hit else "else": ctx}

    yield
    for k in _KEYS:
        REGISTRY.pop(k, None)


def _item(defect_id="D1", level=10.0, klass=1):
    from types import SimpleNamespace
    return SimpleNamespace(defect_id=defect_id, level=level, klass=klass,
                           nm_per_px=None)


def _recipe(node_ids, nodes, expr="peak", edges=None):
    return Recipe(
        recipe_id="g", routes={"ebi_patch": list(node_ids)}, nodes=nodes,
        edges=edges or [],
        score=ScoreSpec(expr=expr, threshold=0.0, bins={"below": 0, "above": 1}))


# --------------------------------------------------------------------------- #
# 1. 線就是資料 —— 這是今天壞掉的那一條
# --------------------------------------------------------------------------- #
def test_a_linear_recipe_compiles_into_a_real_chain_of_wires(cards):
    """以前 recipe 的 `edges` 可以是空的而照樣跑對。現在編出來一定有線。"""
    rec = _recipe(["l", "g", "m"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "g": RecipeNode("g", "t_g_gain", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
    })
    assert rec.edges == []                      # 檔案裡一條線都沒有
    graph = compile_recipe(rec, "ebi_patch")
    assert [(w.src, w.dst) for w in graph.wires] == [("l", "g"), ("g", "m")]


def test_cutting_a_wire_really_disconnects_the_downstream_card(cards):
    """**剪掉線，下游就真的收不到東西。**

    這是整個 F9 的理由：以前剪掉畫布上的線什麼都不會發生，因為那張卡的參數
    還寫著 `source="test"`，它照樣去全域字典拿。
    """
    rec = _recipe(["l", "m"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
    })
    graph = compile_recipe(rec, "ebi_patch")

    ctx = Context()
    ctx.meta["_defect_item"] = _item()
    _out, runs, err, _last = run_graph(graph, Packet(ctx))
    assert err is None and runs[-1].features_added == {"peak": 10.0}

    # 同一張圖，只把那條線剪掉
    graph.wires = [w for w in graph.wires if not (w.src == "l" and w.dst == "m")]
    ctx2 = Context()
    ctx2.meta["_defect_item"] = _item()
    _o2, _r2, err2, _l2 = run_graph(graph, Packet(ctx2))
    assert err2 is not None and "test" in err2, err2


# --------------------------------------------------------------------------- #
# 2. 分岔：兩條分支互不影響
# --------------------------------------------------------------------------- #
def test_a_fork_gives_each_branch_its_own_copy(cards):
    """一個輸出接到兩張卡：一邊放大不該影響另一邊量到的值。

    以前所有卡共用一個 Context，所以「兩條分支」根本不存在 —— 誰先跑誰就
    把 test 改掉了，而且畫面上看不出來。
    """
    rec = _recipe(["l", "g", "m"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "g": RecipeNode("g", "t_g_gain", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
    })
    graph = compile_recipe(rec, "ebi_patch")
    # 手工把它接成分岔：load 同時餵 gain 與 peak
    graph.wires = [Wire("l", "out", "g", "in"), Wire("l", "out", "m", "in")]

    ctx = Context()
    ctx.meta["_defect_item"] = _item(level=10.0)
    outbox, runs, err, _last = run_graph(graph, Packet(ctx))
    assert err is None

    by_id = {r.node_id: r for r in runs}
    # gain 那條變成 20，但 peak 量的是**原圖** 10
    assert by_id["m"].features_added == {"peak": 10.0}
    assert float(outbox[("g", "out")].ctx.images["test"].max()) == 20.0
    assert float(outbox[("m", "out")].ctx.images["test"].max()) == 10.0


def test_a_fork_does_not_leak_warnings_between_branches(cards):
    """meta 裡的 list 也要各自一份 —— 一邊 append 另一邊看得到的話，
    兩條分支的診斷訊息會莫名其妙混在一起（不報錯，只是變得看不懂）。"""
    rec = _recipe(["l", "g", "m"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "g": RecipeNode("g", "t_g_gain", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
    })
    graph = compile_recipe(rec, "ebi_patch")
    graph.wires = [Wire("l", "out", "g", "in"), Wire("l", "out", "m", "in")]

    ctx = Context()
    ctx.meta["_defect_item"] = _item()
    outbox, _runs, err, _last = run_graph(graph, Packet(ctx))
    assert err is None
    assert outbox[("g", "out")].ctx.meta.get("warnings") == ["gain ran"]
    assert outbox[("m", "out")].ctx.meta.get("warnings") is None


def test_a_fork_shares_pixels_instead_of_copying_them(cards):
    """分岔不該複製像素 —— 一萬顆 × 好幾條流，複製的成本是真的。

    共用得起的前提是卡片**產生新陣列、不就地改寫**（F9 §4.1）。
    """
    rec = _recipe(["l", "m"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
    })
    graph = compile_recipe(rec, "ebi_patch")
    ctx = Context()
    ctx.meta["_defect_item"] = _item()
    ctx.set_image("test", np.zeros((4, 4), np.float32))

    pk = Packet(ctx)
    twin = pk.fork()
    assert twin.ctx.images["test"] is ctx.images["test"]      # 同一塊記憶體
    assert twin.ctx.images is not ctx.images                  # 但 dict 是新的


# --------------------------------------------------------------------------- #
# 3. 條件分流（使用者要的 CLASSNUMBER 分流）
# --------------------------------------------------------------------------- #
def test_a_router_runs_only_the_branch_it_picked(cards):
    """一張卡兩個輸出埠，只吐其中一個 —— 沒被選到的那一邊整段安靜不跑。

    「安靜不跑」跟「報錯」是兩件事：這裡是上游決定不吐，不是接線接錯。
    """
    nodes = {
        "l": RecipeNode("l", "t_g_load", {}),
        "r": RecipeNode("r", "t_g_route", {}),
        "a": RecipeNode("a", "t_g_gain", {}),      # match 那一邊
        "b": RecipeNode("b", "t_g_peak", {}),      # else 那一邊
    }
    graph = compile_recipe(_recipe(["l", "r", "a", "b"], nodes), "ebi_patch")
    graph.wires = [Wire("l", "out", "r", "in"),
                   Wire("r", "match", "a", "in"),
                   Wire("r", "else", "b", "in")]

    for klass, expect in ((1, ["l", "r", "a"]), (2, ["l", "r", "b"])):
        ctx = Context()
        ctx.meta["_defect_item"] = _item(klass=klass)
        _o, runs, err, _l = run_graph(graph, Packet(ctx))
        assert err is None, err
        assert [r.node_id for r in runs] == expect, (klass, runs)


# --------------------------------------------------------------------------- #
# 4. 舊行為不變
# --------------------------------------------------------------------------- #
def test_run_defect_still_produces_the_same_answer(cards):
    """圖執行器換進去之後，一條線性 pipeline 的分數與 trace 形狀不變。"""
    rec = _recipe(["l", "g", "m"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "g": RecipeNode("g", "t_g_gain", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
    })
    r = run_defect(rec, _item(level=3.0), "ebi_patch", keep_context=True)
    assert r.ok and r.score == 6.0 and r.bin == 1
    assert [t.node_id for t in r.traces] == ["l", "g", "m"]
    assert r.context.images["test"].max() == 6.0


def test_a_disabled_node_is_bypassed_not_left_dangling(cards):
    """停用中間那張卡，線要**接過去**，不是讓下游斷掉。"""
    rec = _recipe(["l", "g", "m"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "g": RecipeNode("g", "t_g_gain", {}, enabled=False),
        "m": RecipeNode("m", "t_g_peak", {}),
    })
    graph = compile_recipe(rec, "ebi_patch")
    assert [(w.src, w.dst) for w in graph.wires] == [("l", "m")]

    r = run_defect(rec, _item(level=7.0), "ebi_patch")
    assert r.ok and r.score == 7.0             # 沒被放大

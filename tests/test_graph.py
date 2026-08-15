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
from adept.core.pipeline.graph import (
    KIND_STREAM, Packet, Wire, compile_recipe, run_graph,
)
from adept.core.pipeline.step import ParamSpec

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
        help = "測試用：造 test 與 ref 兩張影像（像真的 load_patch）"
        writes = ["test", "ref"]

        def run(self, ctx: Context, params) -> Context:
            item = ctx.meta["_defect_item"]
            ctx.set_image("test", np.full((4, 4), float(item.level), np.float32))
            ctx.set_image("ref", np.full((4, 4), float(item.level) * 0.6,
                                         np.float32))
            return ctx

    @register_step
    class TGain(Step):
        key = "t_g_gain"
        label = "測試放大"
        category = CATEGORY_IMAGE
        help = "測試用：把 test 乘上 gain"
        params = [ParamSpec(name="streams", type="image_keys", default="test",
                            help="要處理哪幾條流。")]
        reads = writes = ["test"]

        def run(self, ctx: Context, params) -> Context:
            for name in str(params["streams"]).split(","):
                name = name.strip()
                # **產生新陣列，不就地改寫**（F9 §4.1 對卡片作者的規矩）
                ctx.set_image(name, ctx.require_image(name) * 2.0)
            ctx.warn("gain ran")
            return ctx

    @register_step
    class TPeak(Step):
        key = "t_g_peak"
        label = "測試量測"
        category = CATEGORY_ALGO
        help = "測試用：量某一條流的最大值"
        params = [ParamSpec(name="source", type="image_key", default="test",
                            help="要量哪一條流。")]
        reads = ["test"]
        features_out = ["peak"]

        def run(self, ctx: Context, params) -> Context:
            ctx.add_feature(
                "peak", float(ctx.require_image(params["source"]).max()))
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
    backbone = [(w.src, w.src_port, w.dst) for w in graph.wires
                if w.kind != KIND_STREAM]
    assert backbone == [("l", "test", "g"), ("g", "test", "m")]
    # 另外還有 stream 線：「這張卡動哪一條流」—— 它不搬狀態，所以不算分岔
    streams = [(w.src, w.src_port, w.dst, w.dst_port) for w in graph.wires
               if w.kind == KIND_STREAM]
    assert streams == [("l", "test", "g", "streams"),
                       ("g", "test", "m", "source")]


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
    graph.wires = [Wire("l", "test", "g", "in"), Wire("l", "test", "m", "in")]

    ctx = Context()
    ctx.meta["_defect_item"] = _item(level=10.0)
    outbox, runs, err, _last = run_graph(graph, Packet(ctx))
    assert err is None

    by_id = {r.node_id: r for r in runs}
    # gain 那條變成 20，但 peak 量的是**原圖** 10
    assert by_id["m"].features_added == {"peak": 10.0}
    assert float(outbox[("g", "test")].ctx.images["test"].max()) == 20.0
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
    graph.wires = [Wire("l", "test", "g", "in"), Wire("l", "test", "m", "in")]

    ctx = Context()
    ctx.meta["_defect_item"] = _item()
    outbox, _runs, err, _last = run_graph(graph, Packet(ctx))
    assert err is None
    assert outbox[("g", "test")].ctx.meta.get("warnings") == ["gain ran"]
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
    graph.wires = [Wire("l", "test", "r", "in"),
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
    backbone = [(w.src, w.dst) for w in graph.wires if w.kind != KIND_STREAM]
    assert backbone == [("l", "m")]

    r = run_defect(rec, _item(level=7.0), "ebi_patch")
    assert r.ok and r.score == 7.0             # 沒被放大


# --------------------------------------------------------------------------- #
# 5. 判定是圖上的卡片（F9 Phase 3a）
# --------------------------------------------------------------------------- #
def _adc(node_id, expr, threshold, label=""):
    return RecipeNode(node_id, "adc", {"expr": expr, "threshold": threshold,
                                       "bin_below": 0, "bin_above": 1,
                                       "label": label})


def test_a_decide_card_replaces_the_score_field(cards):
    """圖上有判定卡的時候，分數由那張卡決定，不再看 recipe.score。"""
    rec = _recipe(["l", "m", "d"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
        "d": _adc("d", "peak", 5.0),
    }, expr="9999")                             # 舊欄位故意給一個很離譜的值
    r = run_defect(rec, _item(level=7.0), "ebi_patch")
    assert r.ok and r.score == 7.0 and r.bin == 1     # 用的是卡片，不是 9999
    r2 = run_defect(rec, _item(level=3.0), "ebi_patch")
    assert r2.ok and r2.score == 3.0 and r2.bin == 0


def test_two_branches_can_use_different_thresholds(cards):
    """**一份 recipe 兩套標準** —— 這是判定變成卡片的理由。

    分流之後兩條分支各有自己的判定卡，門檻不一樣：同一個 level=7 的 defect，
    走 A 是 bin 1（門檻 5）、走 B 是 bin 0（門檻 100）。
    """
    nodes = {
        "l": RecipeNode("l", "t_g_load", {}),
        "r": RecipeNode("r", "t_g_route", {}),
        "ma": RecipeNode("ma", "t_g_peak", {}),
        "da": _adc("da", "peak", 5.0, label="A"),
        "mb": RecipeNode("mb", "t_g_peak", {}),
        "db": _adc("db", "peak", 100.0, label="B"),
    }
    graph = compile_recipe(
        _recipe(["l", "r", "ma", "da", "mb", "db"], nodes), "ebi_patch")
    graph.wires = [Wire("l", "test", "r", "in"),
                   Wire("r", "match", "ma", "in"),
                   Wire("ma", "out", "da", "in"),
                   Wire("r", "else", "mb", "in"),
                   Wire("mb", "out", "db", "in")]

    from adept.core.pipeline.engine import _collect_verdicts
    from adept.core.pipeline.step import REGISTRY as REG

    for klass, expect_bin, by in ((1, 1, "A"), (2, 0, "B")):
        ctx = Context()
        ctx.meta["_defect_item"] = _item(level=7.0, klass=klass)
        outbox, _runs, err, _l = run_graph(graph, Packet(ctx))
        assert err is None, err
        got = _collect_verdicts(graph, outbox, REG)
        assert len(got) == 1, got               # 只有一張判定卡跑到
        assert got[0]["bin"] == expect_bin and got[0]["by"] == by


def test_no_decision_is_recorded_as_no_decision_not_as_zero(cards):
    """分流走到一條**沒有判定卡**的分支 → 沒有結論，不是 0 分。

    0 是個看起來很像答案的答案：它會被排序、寫進報表、看起來像「很乾淨」。
    （跟 cd_x_nm 恆為 0 那個坑同一類，見 CLAUDE.md §8。）
    """
    rec = _recipe(["l", "r", "m", "d", "b"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "r": RecipeNode("r", "t_g_route", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
        "d": _adc("d", "peak", 5.0),
        "b": RecipeNode("b", "t_g_gain", {}),   # else 這條沒有判定卡
    }, edges=[["r", "match", "m", "in"],
              ["m", "out", "d", "in"],
              ["r", "else", "b", "in"]])

    hit = run_defect(rec, _item(level=7.0, klass=1), "ebi_patch")
    miss = run_defect(rec, _item(level=7.0, klass=2), "ebi_patch",
                      keep_context=True)

    assert hit.ok and hit.score == 7.0 and hit.bin == 1
    # 沒有結論的那一顆：跑完了、沒有錯，但**沒有分數**，而且說得出為什麼
    assert miss.ok and miss.score is None and miss.bin is None
    assert any("no decision" in w for w in miss.context.meta.get("warnings", []))


def test_two_decisions_firing_at_once_is_an_error_not_a_coin_flip(cards):
    """兩張判定卡同時生效 = recipe 接錯了。不要偷偷挑一個。"""
    rec = _recipe(["l", "m", "d1", "d2"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
        "d1": _adc("d1", "peak", 5.0, label="A"),
        "d2": _adc("d2", "peak", 100.0, label="B"),
    }, edges=[["m", "out", "d1", "in"], ["m", "out", "d2", "in"]])
    r = run_defect(rec, _item(level=7.0), "ebi_patch")
    assert not r.ok and "both made a decision" in r.error, r.error


def test_a_decide_card_with_no_expression_says_so_before_you_run_it(cards):
    """空的分數式子是合法的 str —— 但那張卡跑起來每一顆都失敗。
    `configuration_issues` 要在 lint 階段就講（F7-13 的機制）。"""
    from adept.core.pipeline import validate
    rec = _recipe(["l", "m", "d"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
        "d": RecipeNode("d", "adc", {}),        # expr 沒填
    })
    codes = [i.code for i in validate(rec, kind="ebi_patch")]
    assert "not-configured" in codes, codes


def test_a_branching_recipe_survives_a_save_and_load(cards):
    """**分支 recipe 要存得起來。** 四段式的線 `[src, src_port, dst, dst_port]`
    就是為此存在的 —— 只寫 `["r", "m"]` 說不出這條線是從 match 還是 else 出去的。
    """
    rec = _recipe(["l", "r", "m", "d", "b"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "r": RecipeNode("r", "t_g_route", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
        "d": _adc("d", "peak", 5.0),
        "b": RecipeNode("b", "t_g_gain", {}),
    }, edges=[["r", "match", "m", "in"],
              ["m", "out", "d", "in"],
              ["r", "else", "b", "in"]])

    again = Recipe.from_json_dict(rec.to_json_dict())
    assert again.edges == rec.edges
    graph = compile_recipe(again, "ebi_patch")
    assert Wire("r", "match", "m", "in") in graph.wires
    assert Wire("r", "else", "b", "in") in graph.wires
    # 兩顆走不同分支，結果跟存檔前一樣
    assert run_defect(again, _item(level=7.0, klass=1), "ebi_patch").bin == 1
    assert run_defect(again, _item(level=7.0, klass=2), "ebi_patch").score is None


def test_an_edge_with_a_silly_shape_is_rejected_at_load_time(cards):
    """三個元素的線是打錯了 —— 講清楚，不要猜使用者的意思。"""
    from adept.core.pipeline import RecipeError
    d = _recipe(["l"], {"l": RecipeNode("l", "t_g_load", {})}).to_json_dict()
    d["edges"] = [["a", "b", "c"]]
    with pytest.raises(RecipeError) as ei:
        Recipe.from_json_dict(d)
    assert "from_port" in str(ei.value)


# --------------------------------------------------------------------------- #
# 6. 流由線決定（使用者 2026-08-15 的兩條原則，F9 Phase 3b）
# --------------------------------------------------------------------------- #
def test_the_wire_decides_which_stream_a_card_works_on(cards):
    """**原則 1：卡片裡不再選 image source，改成從節點拉。**

    同一張卡、同一份參數，只把線從 `test` 埠改接到 `ref` 埠 —— 它就改動 ref。
    參數只是那條線的落腳處，不是使用者要去挑的東西。
    """
    rec = _recipe(["l", "g", "m"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "g": RecipeNode("g", "t_g_gain", {}),      # streams 用預設值 "test"
        "m": RecipeNode("m", "t_g_peak", {}),
    })
    graph = compile_recipe(rec, "ebi_patch")

    def _seed():
        c = Context()
        c.meta["_defect_item"] = _item(level=10.0)   # test=10, ref=6
        return Packet(c)

    outbox, _r, err, _l = run_graph(graph, _seed())
    assert err is None
    got = outbox[("g", "test")].ctx
    assert float(got.images["test"].max()) == 20.0   # 動的是 test
    assert float(got.images["ref"].max()) == 6.0     # ref 沒被動到

    # **只改線**（參數一個字都沒動）：g 的 streams 埠改接到 load 的 ref
    graph.wires = [w for w in graph.wires
                   if not (w.dst == "g" and w.dst_port == "streams")] + [
        Wire("l", "ref", "g", "streams", KIND_STREAM)]
    outbox2, _r2, err2, _l2 = run_graph(graph, _seed())
    assert err2 is None, err2
    got2 = outbox2[("g", "test")].ctx
    assert float(got2.images["ref"].max()) == 12.0   # 現在動的是 ref
    assert float(got2.images["test"].max()) == 10.0  # test 沒被動到


def test_one_output_port_can_feed_several_cards(cards):
    """**原則 2：同一顆輸出埠拉得出好幾條線。**

    Load 的 `ref` 同時餵一張處理卡與一張量測卡 —— 兩張都在動 ref，而且
    **特徵仍然累積到同一包**（stream 線不搬狀態，所以那不是分岔）。
    """
    rec = _recipe(["l", "g", "m"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "g": RecipeNode("g", "t_g_gain", {"streams": "ref"}),
        "m": RecipeNode("m", "t_g_peak", {"source": "ref"}),
    })
    graph = compile_recipe(rec, "ebi_patch")
    from_ref = [(w.dst, w.dst_port) for w in graph.wires
                if w.kind == KIND_STREAM and w.src_port == "ref"]
    assert ("g", "streams") in from_ref, from_ref

    c = Context()
    c.meta["_defect_item"] = _item(level=10.0)      # test=10, ref=6
    _o, _runs, err, last = run_graph(graph, Packet(c))
    assert err is None, err
    # g 放大 ref（6 -> 12），m 量的是**放大後**的 ref，而且兩者在同一包裡
    assert last.ctx.features["peak"] == 12.0
    # 累積的證據：上游那張卡留下的東西跟量測結果在**同一包**裡
    assert last.ctx.meta.get("warnings") == ["gain ran"]


def test_stream_wires_are_not_forks(cards):
    """三張卡讀同一條流 = 三條 stream 線，**不是三岔**。

    這一條是踩過的坑：一開始把「照名字接線」做成 packet 線，於是一條流被
    三張卡讀就變成三個複本，量出來的數字散在三包裡，而分數式子只看得到一份。
    """
    rec = _recipe(["l", "g", "m"], {
        "l": RecipeNode("l", "t_g_load", {}),
        "g": RecipeNode("g", "t_g_gain", {}),
        "m": RecipeNode("m", "t_g_peak", {}),
    })
    graph = compile_recipe(rec, "ebi_patch")
    # 每個節點最多只有一條 packet 線進來（backbone 是一條鏈）
    for nid in graph.order:
        n_packet = sum(1 for w in graph.incoming(nid) if w.kind != KIND_STREAM)
        assert n_packet <= 1, (nid, graph.incoming(nid))
    # 而 stream 線不計入扇出（扇出 > 1 才複製）
    assert graph.fanout("l", "test") == 1

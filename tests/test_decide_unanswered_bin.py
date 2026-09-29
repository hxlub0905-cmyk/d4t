# 評價清單 #1：「問不出來的送去 bin N」（選配；沒設＝照 F30 答「否」）。
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.engine import _eval_score  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    DecideSpec, Recipe, RecipeNode, Rule, ScoreSpec, TreeLeaf, TreeStep,
)
from d4t.core.pipeline.verdict_trace import verdict_trace  # noqa: E402

TREE = TreeStep(when="cd_area_px > 50",
                yes=TreeLeaf(bin=2, label="big"),
                no=TreeLeaf(bin=1, label="small"))


def _recipe(decide):
    return Recipe(
        recipe_id="t", routes={"ebi_patch": ["load"]},
        nodes={"load": RecipeNode("load", "load_patch", {})},
        score=ScoreSpec(expr="", threshold=0.0, bins={"below": 0, "above": 1}),
        decide=decide)


def _ctx(**feats):
    c = Context(images={})
    c.add_features(feats)
    return c


def test_off_by_default_the_old_rule_holds():
    """沒設 → 問不出來那一題答「否」，照 F30 走下去（舊檔案的數字不變）。"""
    ctx = _ctx(glv_max=10.0)                   # cd_area_px 沒量到
    _, b = _eval_score(_recipe(DecideSpec(tree=TREE)), ctx)
    assert b == 1 and ctx.features["decide_unanswered"] == 1.0
    assert ctx.meta["decide"]["unanswered_routed"] is False


def test_set_it_and_the_unanswered_go_to_that_bin():
    d = DecideSpec(tree=TREE, unanswered_bin=99, unanswered_label="not measured")
    ctx = _ctx(glv_max=10.0)
    _, b = _eval_score(_recipe(d), ctx)
    assert b == 99
    assert ctx.meta["decide"]["label"] == "not measured"
    assert ctx.meta["decide"]["unanswered_routed"] is True
    assert any("bin 99" in w for w in ctx.meta.get("warnings", []))
    # 答得出來的照樹走，一點都不受影響
    ctx = _ctx(cd_area_px=80.0)
    _, b = _eval_score(_recipe(d), ctx)
    assert b == 2 and ctx.meta["decide"]["unanswered_routed"] is False


def test_rules_mode_too():
    d = DecideSpec(rules=[Rule(when="cd_area_px > 50", bin=2, label="big")],
                   otherwise_bin=0, unanswered_bin=7)
    _, b = _eval_score(_recipe(d), _ctx(glv_max=1.0))
    assert b == 7


def test_the_json_key_is_only_there_when_set():
    """嚴格附加：沒設就不寫，所以舊檔案 round-trip 一個 byte 都不變（鐵則 9）。"""
    plain = _recipe(DecideSpec(tree=TREE))
    assert "unanswered" not in plain.to_json_dict()["decide"]
    again = Recipe.from_json_dict(plain.to_json_dict())
    assert again.to_json_dict() == plain.to_json_dict()
    assert again.decide.unanswered_bin is None

    on = _recipe(DecideSpec(tree=TREE, unanswered_bin=99, unanswered_label="nm"))
    js = on.to_json_dict()
    assert js["decide"]["unanswered"] == {"bin": 99, "label": "nm"}
    back = Recipe.from_json_dict(js)
    assert (back.decide.unanswered_bin, back.decide.unanswered_label) == (99, "nm")
    assert back.to_json_dict() == js


def test_the_bin_gets_its_name_in_the_class_list():
    d = DecideSpec(tree=TREE, unanswered_bin=99, unanswered_label="not measured")
    assert d.bin_labels().get(99) == "not measured"


def test_the_why_panel_names_the_bin_it_really_went_to():
    d = DecideSpec(tree=TREE, unanswered_bin=99, unanswered_label="nm")
    t = verdict_trace(_recipe(d), "ebi_patch", {"glv_max": 1.0})
    assert t.leaf_bin == 99 and t.unanswered_routed
    t = verdict_trace(_recipe(dataclasses.replace(d, unanswered_bin=None)),
                      "ebi_patch", {"glv_max": 1.0})
    assert t.leaf_bin == 1 and not t.unanswered_routed


def test_the_editor_sets_it_and_undo_keeps_it():
    """Studio 那一邊：設定、關掉、改名字；undo 不准把它（或 outcome）弄丟。"""
    from d4t.ui.viewmodel import RecipeModel

    m = RecipeModel(kind="ebi_patch")
    if m.decide is None:
        m.decide = DecideSpec(tree=TREE)
    m.set_unanswered(99)
    m.set_unanswered(label="not measured")
    assert (m.decide.unanswered_bin, m.decide.unanswered_label) == (99, "not measured")
    m.set_otherwise(bin=3)                     # 另一個動作，然後 undo 它
    m.undo()
    assert m.decide.unanswered_bin == 99, "undo 不准把這個設定弄丟"
    m.set_unanswered(None)
    assert m.decide.unanswered_bin is None


def test_undo_keeps_the_outcomes_too():
    from d4t.ui.viewmodel import _decide_restore, _decide_snapshot
    d = DecideSpec(rules=[Rule(when="a > 1", bin=2, label="x", outcome="bad")],
                   otherwise_bin=0, otherwise_outcome="good",
                   unanswered_bin=9, unanswered_label="nm")
    back = _decide_restore(_decide_snapshot(d))
    assert back == d


# --------------------------------------------------------------------------- #
# F122：「每一類幾顆」要跟引擎放的 bin 一樣
# --------------------------------------------------------------------------- #
def _rows_from_the_engine(decide, feats_list):
    rows = []
    for i, feats in enumerate(feats_list):
        ctx = _ctx(**feats)
        score, b = _eval_score(_recipe(decide), ctx)
        rows.append({"defect_id": "d%d" % i, "ok": True, "score": score,
                     "bin": b, "features": dict(ctx.features)})
    return rows


def test_the_verdict_rows_count_them_where_the_engine_put_them():
    """判定帶、HTML 報表、box plot 都吃 `verdict_rows`，而它是**重走樹**算的 ——
    以前重走的人不知道有這一格：引擎放進 bin 99 的那顆，這裡被算在「small」。"""
    from d4t.core.pipeline.decide_tree import (
        UNANSWERED_KEY, decision_info, verdict_rows,
    )

    d = DecideSpec(tree=TREE, unanswered_bin=99, unanswered_label="not measured")
    rows = _rows_from_the_engine(d, [{"cd_area_px": 60.0},
                                     {"glv_max": 1.0}])      # 第二顆問不出來
    assert [r["bin"] for r in rows] == [2, 99]
    got = {v["key"]: v for v in verdict_rows(d, rows)}
    assert got[UNANSWERED_KEY]["bin"] == 99
    assert got[UNANSWERED_KEY]["ids"] == ["d1"]
    assert got[UNANSWERED_KEY]["name"] == "not measured"
    by_bin = {}
    for v in got.values():
        by_bin[v["bin"]] = by_bin.get(v["bin"], 0) + v["count"]
    engine_bins = {}
    for r in rows:
        engine_bins[r["bin"]] = engine_bins.get(r["bin"], 0) + 1
    assert {b: n for b, n in by_bin.items() if n} == engine_bins
    # 畫布：托盤仍是「走到這裡的」（流量守恆），旁邊講幾顆去了 bin 99。
    info = decision_info(d, rows)
    assert info["counts"]["n"] == 1 and info["diverted"] == {"n": 1}


def test_without_the_setting_nothing_is_diverted():
    """**反向**：沒設 → 問不出來的照 F30 答「否」，算在「否」那片葉子上。"""
    from d4t.core.pipeline.decide_tree import UNANSWERED_KEY, verdict_rows

    d = DecideSpec(tree=TREE)
    rows = _rows_from_the_engine(d, [{"glv_max": 1.0}])
    keys = [v["key"] for v in verdict_rows(d, rows)]
    assert UNANSWERED_KEY not in keys
    assert rows[0]["bin"] == 1

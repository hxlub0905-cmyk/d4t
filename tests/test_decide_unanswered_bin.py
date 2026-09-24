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

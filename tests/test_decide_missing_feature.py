# 量不到的那一顆，判定樹要走得完（F30，2026-08-25）。
"""**一顆什麼都沒量到的 defect 不是執行失敗。**

量測卡的規矩 3 是「量不到就不寫那一格」（不是 0、也不是 NaN）—— 所以
``cd_area_px`` 在那樣一顆上**本來就不存在**，而那是**正確**的行為。

F30 之前，樹上只要問到它，`Expression.eval` 就 raise，`run_defect` 接成整顆
``ok=False``、訊息 ``[score] unknown variable 'cd_area_px'``。於是：

* 它不進 Results 的統計（`flow_counts` 只算 ``ok`` 的）；
* 疊圖的 ``ok=True`` 過濾把它濾掉；
* 而「什麼都沒量到」正是使用者最想看到的那一類之一。

使用者 2026-08-25 定調：**那一題答「否」，繼續走。**

這一份同時鎖住**引擎與畫布走的是同一條路** —— 那兩邊曾經是兩段各自寫的迴圈，
而 `_path_of` 的說明寫著「判準跟引擎一字不差」。只改一邊的那一天，畫布上的
顆數與引擎判的類別會對不起來，而畫面上沒有任何東西看得出來。
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import Recipe  # noqa: E402
from d4t.core.pipeline import decide_tree, engine  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.expression import ExpressionError  # noqa: E402


def tree_recipe(when: str = "cd_area_px > 50", score: str = "") -> Recipe:
    return Recipe.from_json_dict({
        "version": 1, "recipe_id": "t", "nodes": {},
        "routes": {"ebi_patch": []}, "edges": [],
        "score": {"expr": "", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
        "decide": {"let": [], "score": score,
                   "tree": {"when": when,
                            "yes": {"bin": 2, "label": "big"},
                            "no": {"bin": 1, "label": "small"}}},
    })


def rules_recipe() -> Recipe:
    return Recipe.from_json_dict({
        "version": 1, "recipe_id": "t", "nodes": {},
        "routes": {"ebi_patch": []}, "edges": [],
        "score": {"expr": "", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
        "decide": {"let": [],
                   "rules": [{"when": "cd_area_px > 50", "bin": 2,
                              "label": "big"},
                             {"when": "focus_lapvar > 1", "bin": 3,
                              "label": "sharp"}],
                   "otherwise": {"bin": 0, "label": "none"}},
    })


# --------------------------------------------------------------------------- #
# 問不出來 = 答「否」，不是失敗
# --------------------------------------------------------------------------- #
def test_a_defect_that_measured_nothing_still_gets_classified():
    ctx = Context()
    _score, b = engine._eval_score(tree_recipe(), ctx)
    assert b == 1                                   # 走了 no 那一支
    assert ctx.meta["decide"]["label"] == "small"
    assert ctx.meta["decide"]["path"] == ["no"]


def test_it_says_which_number_was_missing():
    """答「否」不可以是**安靜的** —— 缺了什麼要留得下來。"""
    ctx = Context()
    engine._eval_score(tree_recipe(), ctx)
    assert ctx.features["decide_unanswered"] == 1.0
    assert ctx.meta["decide"]["unanswered"] == ["cd_area_px"]
    warn = " ".join(ctx.meta.get("warnings") or [])
    assert "cd_area_px" in warn and "answered 'no'" in warn


def test_the_count_is_written_even_when_it_is_zero():
    """``decide_unanswered`` 是「幾題」——**0 是一個真的答案**，不是「沒量到」。

    這跟量測卡的「量不到就不寫」不衝突：那條規矩講的是**量測**，而這一格
    每一顆都答得出來。不寫 0 的話，CSV 上「這一欄是空的」會同時代表
    「全部問得出來」與「這一顆根本沒跑判定」。
    """
    ctx = Context(features={"cd_area_px": 90.0})
    engine._eval_score(tree_recipe(), ctx)
    assert ctx.features["decide_unanswered"] == 0.0
    assert ctx.meta["decide"]["unanswered"] == []
    assert not (ctx.meta.get("warnings") or [])


def test_missing_is_not_the_same_as_zero():
    """``0 > 50`` 與「問不出來」都走 no —— 但 CSV 上分得出來。"""
    zero = Context(features={"cd_area_px": 0.0})
    gone = Context()
    _s1, b1 = engine._eval_score(tree_recipe(), zero)
    _s2, b2 = engine._eval_score(tree_recipe(), gone)
    assert b1 == b2 == 1                            # 同一個 bin
    assert zero.features["decide_unanswered"] == 0.0
    assert gone.features["decide_unanswered"] == 1.0   # ← 唯一的線索


def test_a_rule_that_cannot_be_asked_falls_through_to_the_next_one():
    """`rules` 那一支同一條規矩 —— 問不出來的規則不成立，往下一條試。"""
    ctx = Context(features={"focus_lapvar": 5.0})
    _score, b = engine._eval_score(rules_recipe(), ctx)
    assert b == 3                                   # 第一條問不出來，第二條中
    assert ctx.features["decide_unanswered"] == 1.0
    assert ctx.meta["decide"]["unanswered"] == ["cd_area_px"]


def test_every_rule_unanswerable_lands_on_otherwise():
    ctx = Context()
    _score, b = engine._eval_score(rules_recipe(), ctx)
    assert b == 0 and ctx.meta["decide"]["label"] == "none"
    assert ctx.features["decide_unanswered"] == 2.0


# --------------------------------------------------------------------------- #
# 值不是數字仍然要炸（那不是「量不到」）
# --------------------------------------------------------------------------- #
def test_a_non_numeric_value_still_raises():
    """安靜地答「否」會把一個真的 bug 埋掉 —— 沒有卡片會往 features 塞字串。"""
    ctx = Context(features={"cd_area_px": "large"})
    with pytest.raises(Exception):
        engine._eval_score(tree_recipe(), ctx)


# --------------------------------------------------------------------------- #
# 老路（單一分數表達式）沒有退路，但要講人話
# --------------------------------------------------------------------------- #
def test_the_old_single_score_path_still_fails_but_explains_itself():
    """一條分數表達式算不出來時沒有第二個答案，硬給 0 分是發明一個數字。"""
    r = Recipe.from_json_dict({
        "version": 1, "recipe_id": "t", "nodes": {},
        "routes": {"ebi_patch": []}, "edges": [],
        "score": {"expr": "cd_area_px * 2", "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}}})
    with pytest.raises(ExpressionError) as e:
        engine._eval_score(r, Context())
    msg = str(e.value)
    assert "cd_area_px" in msg
    assert "not measured" in msg                  # 為什麼不見了
    assert "decision tree" in msg                 # 有退路的那條路在哪


# --------------------------------------------------------------------------- #
# 引擎與畫布走同一條路（這才是那兩段迴圈合併的理由）
# --------------------------------------------------------------------------- #
#: ⚠ **`<` 與負的門檻不是為了多樣性，是這條性質測試唯一有鑑別力的地方。**
#:
#: 第一版只生 ``x > k``（k ≥ 0），於是「問不出來 → 答否」與「缺值當 0」
#: **在每一題上都給同一個答案**（``0 > k`` 對 k ≥ 0 恆為否）。實測：把畫布那
#: 一邊換成「缺值當 0」再自己走一遍迴圈，200 棵隨機樹**一棵都沒抓到**。
#: ``x < 5`` 那一題才分得出來：缺值當 0 會答「是」，而正確答案是「否」。
_OPS = (">", "<", ">=", "<=")


def _random_tree(rng, depth, names):
    if depth == 0:
        return {"bin": rng.randint(0, 5), "label": "leaf%d" % rng.randint(0, 9)}
    return {"when": "%s %s %d" % (rng.choice(names), rng.choice(_OPS),
                                  rng.randint(-3, 10)),
            "yes": _random_tree(rng, depth - 1, names),
            "no": _random_tree(rng, depth - 1, names)}


def test_missing_is_answered_no_not_treated_as_zero():
    """**這一條是那個 bug 的形狀**，而它比 `decide_unanswered` 更難看出來。

    ``cd_area_px < 5`` 在一顆什麼都沒量到的 defect 上：把缺值當 0 的話答「是」
    （0 < 5），而正確答案是「否」—— 那一顆會落到**另一片葉子**、被歸成另一類，
    而 CSV 上兩者都是一個正常的類別名。
    """
    ctx = Context()
    _score, b = engine._eval_score(tree_recipe(when="cd_area_px < 5"), ctx)
    assert b == 1 and ctx.meta["decide"]["path"] == ["no"]
    assert decide_tree.answer("cd_area_px < 5", {}) == (False, ["cd_area_px"])
    # 有值的時候它當然照常成立 —— 否則上面那句話只是「這一題永遠答否」
    assert decide_tree.answer("cd_area_px < 5", {"cd_area_px": 1.0})[0] is True


def test_the_engine_and_the_canvas_walk_the_same_path():
    """隨機樹 × 隨機**缺了幾個數字**的 features，兩邊走的路要逐字相同。

    缺數字是這條性質測試的重點：兩段迴圈在「全部都問得出來」時本來就一致，
    漂掉只會漂在邊界上。
    """
    rng = random.Random(20260825)
    names = ["a", "b", "c", "d"]
    for _ in range(200):
        spec = _random_tree(rng, rng.randint(1, 4), names)
        r = Recipe.from_json_dict({
            "version": 1, "recipe_id": "t", "nodes": {},
            "routes": {"ebi_patch": []}, "edges": [],
            "score": {"expr": "", "threshold": 1.0,
                      "bins": {"below": 0, "above": 1}},
            "decide": {"let": [], "tree": spec}})
        feats = {n: float(rng.randint(0, 10)) for n in names
                 if rng.random() > 0.4}          # 有些顆就是缺
        ctx = Context(features=dict(feats))
        _score, b = engine._eval_score(r, ctx)
        engine_path = "".join("y" if p == "yes" else "n"
                              for p in ctx.meta["decide"]["path"])
        canvas_path = decide_tree._path_of(r.decide.tree, feats)
        assert engine_path == canvas_path, (spec, feats)
        # 走到的葉子也要是同一片
        leaf, _p, _m = decide_tree.walk(r.decide.tree, feats)
        assert int(leaf.bin) == b


def test_the_property_test_really_sees_missing_features():
    """上面那條要真的走到「缺數字」的分支，否則它永遠是綠的。"""
    rng = random.Random(20260825)
    names = ["a", "b", "c", "d"]
    seen_missing = 0
    for _ in range(200):
        spec = _random_tree(rng, rng.randint(1, 4), names)
        feats = {n: float(rng.randint(0, 10)) for n in names
                 if rng.random() > 0.4}
        tree = Recipe.from_json_dict({
            "version": 1, "recipe_id": "t", "nodes": {},
            "routes": {"ebi_patch": []}, "edges": [],
            "score": {"expr": "", "threshold": 1.0,
                      "bins": {"below": 0, "above": 1}},
            "decide": {"let": [], "tree": spec}}).decide.tree
        if decide_tree.walk(tree, feats)[2]:
            seen_missing += 1
    assert seen_missing > 60, seen_missing


def test_flow_counts_now_includes_the_defects_that_measured_nothing():
    """畫布上的分支流量以前把它們整顆丟掉（表達式炸了 → `except` 跳過）。

    守恆因此是**假的**：根上的數字比「跑成功的顆數」少，而畫面上沒有說明。
    """
    tree = tree_recipe().decide.tree
    rows = [{"ok": True, "bin": 2, "features": {"cd_area_px": 90.0}},
            {"ok": True, "bin": 1, "features": {}}]          # 什麼都沒量到
    counts = decide_tree.flow_counts(tree, rows)
    assert counts[""] == 2                                   # 兩顆都算數
    assert counts["y"] == 1 and counts["n"] == 1

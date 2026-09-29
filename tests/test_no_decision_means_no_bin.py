# F122 期 1：還沒有判定＝沒有 bin（不是每一顆 bin 1、分數 0）。
"""**畫面說什麼，引擎就做什麼。**

2026-09-29 以前，還沒加判定的新 recipe 在 Studio 上寫著「Nothing sorts the
defects yet - every one comes out unclassified」，而引擎把每一顆分進 bin 1、
分數 0 —— 因為 `RecipeModel` 給新 recipe 塞了一個佔位值 ``score.expr = "0"``
（空的會讓每一顆失敗），而 ``0 >= 0`` 在老路上是一條真的判定。

現在：沒有 ``decide``、``score.expr`` 也空著 → 每一顆**量完、沒分類**
（``score=None``、``bin=None``；`verdict_rows` 叫它「no verdict」、KLARF 寫 -1）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.engine import _eval_score  # noqa: E402
from d4t.core.pipeline.recipe import Recipe, RecipeNode, ScoreSpec  # noqa: E402
from d4t.core.pipeline.recipe_validate import validate  # noqa: E402


def _recipe(expr="", threshold=0.0):
    return Recipe(
        recipe_id="t", routes={"ebi_patch": ["load", "glv"]},
        nodes={"load": RecipeNode("load", "load_patch", {}),
               "glv": RecipeNode("glv", "glv_stats",
                                 {"source": "test", "metrics": "glv_max"})},
        score=ScoreSpec(expr=expr, threshold=threshold,
                        bins={"below": 0, "above": 1}))


def _ctx(**feats):
    c = Context(images={})
    c.add_features(feats)
    return c


def test_no_decision_gives_no_bin_and_no_score():
    ctx = _ctx(glv_max=10.0)
    assert _eval_score(_recipe(""), ctx) == (None, None)
    assert "score" not in ctx.features


def test_no_decision_is_not_an_error_in_the_health_check():
    errors = [i for i in validate(_recipe(""), "ebi_patch")
              if i.level == "error"]
    assert not errors, errors


def test_a_real_threshold_still_decides():
    """**反向**：老路本身沒動 —— 一條用得到量測數字的分數照舊分兩類。"""
    assert _eval_score(_recipe("glv_max", 5.0), _ctx(glv_max=10.0))[1] == 1
    assert _eval_score(_recipe("glv_max", 5.0), _ctx(glv_max=1.0))[1] == 0


def test_a_new_studio_recipe_carries_no_placeholder():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from d4t.ui.viewmodel import RecipeModel

    m = RecipeModel()
    m.add_step("load_patch")
    r = m.to_recipe()
    assert r.decide is None and r.score.expr == ""
    assert _eval_score(r, _ctx(glv_max=10.0)) == (None, None)


def test_an_old_file_with_the_placeholder_opens_as_no_decision():
    """UI 層的遷移（同 `_adopt_threshold_as_a_tree`）：畫面本來就說「沒有判定」，
    所以打開就照畫面改，存檔寫的就是畫面上那一份。"""
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from d4t.ui.viewmodel import RecipeModel

    assert RecipeModel.from_recipe(_recipe("0")).expr == ""
    # **反向**：真的門檻不動（它由 Studio 載入時轉成樹，那是另一條路）。
    assert RecipeModel.from_recipe(_recipe("glv_max", 5.0)).expr == "glv_max"

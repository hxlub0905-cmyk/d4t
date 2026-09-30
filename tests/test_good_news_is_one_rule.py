# F122 期 3：「判成真的」只有一個判準 —— 每一類標的好消息／壞消息。
"""**顏色、正確率、Results 表上紅著的格子，講同一件事。**

F119 讓使用者在判定的每一類上標「好消息／壞消息／中性」，膠囊的顏色照它畫；
而正確率、抓漏、誤殺、表上「判錯了」的格子以前一律看 ``bin != 0``。出貨的
EBI recipe 上那兩個答案就不一樣：「nothing to measure」bin 9 標成中性（沒量到
不是找到缺陷），卻被算成「判成真的」。

規則（`decide_tree.called_real`）：標了 ``bad`` ＝判成真的；``good`` /
``neutral`` ＝不是；**沒標的照舊** ``bin != 0`` —— 舊 recipe 一個數字都不變。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.export import summarize  # noqa: E402
from d4t.core.pipeline.decide_tree import called_real, positive_bins  # noqa: E402
from d4t.core.pipeline.recipe import Recipe  # noqa: E402


def _ebi_decide():
    return Recipe.load(str(REPO / "recipes" / "ebi-die-to-die.json")).decide


def test_the_rule():
    marks = {1: "bad", 0: "good", 9: "neutral"}
    assert called_real(1, marks) is True
    assert called_real(0, marks) is False
    assert called_real(9, marks) is False            # 中性不是「找到缺陷」
    assert called_real(5, marks) is True             # 沒標 → 照舊 bin != 0
    assert called_real(0, {}) is False
    assert called_real(3, {}) is True
    assert called_real(None, marks) is None


def test_the_shipped_ebi_recipe_no_longer_counts_nothing_to_measure_as_real():
    decide = _ebi_decide()
    assert decide.bin_outcomes()[9] == "neutral"      # 前提
    rows = [{"defect_id": "a", "ok": True, "bin": 9},
            {"defect_id": "b", "ok": True, "bin": 1}]
    truth = {"a": {"is_real": False}, "b": {"is_real": True}}
    assert positive_bins(decide, rows) == [1]
    g = summarize(rows, ground_truth=truth,
                  positive_bins=positive_bins(decide, rows))["ground_truth"]
    assert (g["tp"], g["fp"], g["tn"], g["fn"]) == (1, 0, 1, 0)
    # 以前（bin != 0）：bin 9 那一顆被算成誤殺。
    old = summarize(rows, ground_truth=truth)["ground_truth"]
    assert old["fp"] == 1


def test_an_unmarked_recipe_keeps_the_old_numbers():
    """**反向**：一類都沒標 → ``None`` → `summarize` 的預設，逐位元組照舊。"""
    from d4t.core.pipeline.recipe import DecideSpec, TreeLeaf, TreeStep

    d = DecideSpec(tree=TreeStep(when="x > 1", yes=TreeLeaf(bin=1),
                                 no=TreeLeaf(bin=0)))
    assert positive_bins(d, [{"bin": 1}]) is None
    assert positive_bins(None, [{"bin": 1}]) is None


def test_the_baseline_strip_counts_with_the_same_rule():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from d4t.ui import baseline

    rows = [{"defect_id": "a", "ok": True, "bin": 9},
            {"defect_id": "b", "ok": True, "bin": 1}]
    assert baseline.snapshot(rows, decide=_ebi_decide())["flagged"] == 1
    assert baseline.snapshot(rows)["flagged"] == 2          # 沒給判定 → 照舊

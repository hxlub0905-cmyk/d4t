# 判定邏輯只有一個家 — authored 2026-08-24（全專案 review 的 F3／F4）。
"""**這一份鎖住的是「重算判定」只有一條路。**

在這之前有兩份實作：`batch.apply_lot_scaling` 走引擎的 `_eval_score`，而
`store.rescore` 自己讀 ``recipe.score``、比 ``threshold``、分 below/above ——
**它從來沒有看過 ``decide``**。F21–F25 把整個判定段搬進 `DecideSpec`（F25 更把
二元門檻的 UI 整個拿掉，「舊 recipe 一打開就是判定樹」）之後，第二份就漂了。

漂掉的症狀分兩種，後面那種是這個 repo 最怕的形狀：

* 正規的 decide recipe（``score.expr == ""``）→ 一句「the expression is empty
  — enter a formula such as snr_max * 2」。使用者從來沒寫過分數表達式。
* 兩個區塊都有值的過渡期 recipe → **安靜地**用廢棄的 ``score`` 算完、
  回報 ``n_errors: 0``、每一顆都是 bin 0，而 ``--save-as`` 把那份錯的存成新 run
  ——「跑得完、有數字、而且是錯的」。

順帶鎖住 F4：`apply_lot_scaling` 跑第二次不可以二次換算。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import Recipe, apply_lot_scaling, redecide  # noqa: E402
from d4t.core.store import RunStore, rescore  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _tree_recipe(score_expr: str = "") -> Recipe:
    """判定樹：``a > 2`` → bin 7，否則 bin 3。

    ``score_expr`` 給的是**老路那個區塊**的內容 —— 空字串是正規的 decide
    recipe，非空是「兩個區塊都有值」的過渡期檔案。
    """
    return Recipe.from_json_dict({
        "version": 1, "recipe_id": "t", "nodes": {},
        "routes": {"ebi_patch": []}, "edges": [],
        "score": {"expr": score_expr, "threshold": 1.0,
                  "bins": {"below": 0, "above": 1}},
        "decide": {"let": [],
                   "tree": {"when": "a > 2",
                            "yes": {"bin": 7, "label": "big"},
                            "no": {"bin": 3, "label": "small"}},
                   "score": "a"},
    })


def _rows(n: int = 6):
    """第 i 顆的 ``a`` 就是 i，所以 i > 2 的那三顆是 bin 7。"""
    return [{"defect_id": str(i), "ok": True, "bin": (7 if i > 2 else 3),
             "score": float(i), "features": {"a": float(i)}}
            for i in range(n)]


@pytest.fixture()
def store(tmp_path):
    with RunStore(str(tmp_path / "runs.db")) as st:
        yield st


# --------------------------------------------------------------------------- #
# 1. rescore 對判定樹要給出跟原本那一輪一樣的答案
# --------------------------------------------------------------------------- #
def test_rescore_reproduces_the_tree_verdict(store):
    """這是那個「安靜地全部 bin 0」的迴歸測試。

    ⚠ 用的是 ``score.expr`` **非空**的過渡期 recipe —— 正是舊實作會安靜算錯的
    那一種（空的那一種會大聲壞掉，見下一條）。舊實作在這裡回 ``{0: 6}``。
    """
    r = _tree_recipe(score_expr="0")
    store.save_run(r, _rows(), run_id="R1", klarf_path="", dataset_kind="ebi_patch")

    summary = rescore(store, "R1")

    assert summary["bin_counts"] == {3: 3, 7: 3}, summary["bin_counts"]
    assert summary["n_errors"] == 0
    assert summary["n"] == 6


def test_rescore_works_on_a_recipe_that_has_no_score_expression(store):
    """正規的 decide recipe：``score.expr`` 是空的。

    舊實作在這裡丟 ``ExpressionError: the expression is empty`` —— 而使用者
    做的是一棵樹，那句話對他沒有意義。
    """
    r = _tree_recipe(score_expr="")
    store.save_run(r, _rows(), run_id="R1", klarf_path="", dataset_kind="ebi_patch")

    summary = rescore(store, "R1")

    assert summary["bin_counts"] == {3: 3, 7: 3}
    assert summary["n_errors"] == 0


def test_saving_a_rescored_tree_run_stores_the_tree_verdict(store):
    """``--save-as`` 是這件事真正會留下傷害的地方：錯的 bin 會進 DB。"""
    r = _tree_recipe(score_expr="0")
    store.save_run(r, _rows(), run_id="R1", klarf_path="", dataset_kind="ebi_patch")

    rescore(store, "R1", save_as="R2")

    assert [x["bin"] for x in store.iter_results("R2")] == [3, 3, 3, 7, 7, 7]
    assert [x["score"] for x in store.iter_results("R2")] == [0., 1., 2., 3., 4., 5.]


def test_the_old_knobs_are_refused_instead_of_silently_ignored(store):
    """``--expr`` / ``--threshold`` / ``--bins`` 在一棵樹上沒有東西可以改。

    安靜忽略的話，使用者拖完門檻按下去、看到「成功」、而數字一個都沒動。
    """
    r = _tree_recipe(score_expr="0")
    store.save_run(r, _rows(), run_id="R1", klarf_path="", dataset_kind="ebi_patch")

    for kwargs in ({"expr": "a * 2"}, {"threshold": 4.0},
                   {"bins": {"below": 0, "above": 1}}):
        with pytest.raises(ValueError) as err:
            rescore(store, "R1", **kwargs)
        assert "tree" in str(err.value), str(err.value)


def test_the_single_threshold_path_is_untouched(store):
    """**老路一個位元都不准動**（黃金值與既有的 store 測試靠它）。"""
    r = Recipe.from_json_dict({
        "version": 1, "recipe_id": "t", "nodes": {},
        "routes": {"ebi_patch": []}, "edges": [],
        "score": {"expr": "a", "threshold": 2.5,
                  "bins": {"below": 0, "above": 1}},
    })
    store.save_run(r, _rows(), run_id="R1", klarf_path="", dataset_kind="ebi_patch")

    summary = rescore(store, "R1")
    # a = 0..5，門檻 2.5 → 三顆 below、三顆 above
    assert summary["bin_counts"] == {0: 3, 1: 3}

    # 門檻可以改，而且改了要有作用
    assert rescore(store, "R1", threshold=4.5)["bin_counts"] == {0: 5, 1: 1}


# --------------------------------------------------------------------------- #
# 2. redecide 是那條路本身
# --------------------------------------------------------------------------- #
def test_redecide_is_what_both_callers_use():
    """`apply_lot_scaling` 與 `rescore` 都叫它 —— 判定邏輯只有一個家。"""
    rows = _rows()
    for r in rows:                       # 先把答案弄髒
        r["bin"], r["score"] = 0, 0.0
    assert redecide(_tree_recipe(), rows) == 6
    assert [r["bin"] for r in rows] == [3, 3, 3, 7, 7, 7]


def test_redecide_never_kills_the_batch_on_one_bad_defect():
    """鐵則 7：單顆出錯不得殺掉整批。"""
    rows = _rows()
    del rows[2]["features"]["a"]         # 這一顆缺了樹要用的數字
    assert redecide(_tree_recipe(), rows) == 5
    assert rows[2]["ok"] is False and rows[2]["bin"] is None
    assert [r["bin"] for r in rows if r["ok"]] == [3, 3, 7, 7, 7]


# --------------------------------------------------------------------------- #
# 3. F4：「跟整批比」跑第二次不可以二次換算
# --------------------------------------------------------------------------- #
def _scaled_recipe() -> Recipe:
    return Recipe.from_json_dict({
        "version": 1, "recipe_id": "t", "nodes": {},
        "routes": {"ebi_patch": []}, "edges": [],
        "score": {"expr": "", "threshold": 0.0,
                  "bins": {"below": 0, "above": 1}},
        "decide": {"let": [{"name": "x", "expr": "a", "scale": "z"}],
                   "rules": [{"when": "x > 1", "bin": 1}],
                   "otherwise": {"bin": 0}, "score": "x"},
    })


def test_lot_scaling_twice_gives_the_same_answer_as_once():
    """``<name>_raw`` 是**冪等的錨**。

    以前它被無條件覆寫，所以第二次寫進去的是「已經 z 化過的值」——
    原始量測值就此消失（CSV 上再也畫不出換算前的分布），而 ``x`` 被換算兩次。
    """
    r = _scaled_recipe()
    rows = [{"defect_id": str(i), "ok": True, "bin": 0, "score": 0.0,
             "features": {"a": float(i), "x": float(i)}} for i in range(5)]

    apply_lot_scaling(r, rows)
    once = [(rw["features"]["x"], rw["features"]["x_raw"]) for rw in rows]
    apply_lot_scaling(r, rows)
    twice = [(rw["features"]["x"], rw["features"]["x_raw"]) for rw in rows]

    assert once == twice
    # 原始值還在，而且是原始值（0..4），不是 z 分數
    assert [rw["features"]["x_raw"] for rw in rows] == [0., 1., 2., 3., 4.]


def test_percentile_scaling_is_idempotent_too():
    """百分位那一支走的是另一個分支，所以分開驗。"""
    r = Recipe.from_json_dict({
        "version": 1, "recipe_id": "t", "nodes": {},
        "routes": {"ebi_patch": []}, "edges": [],
        "score": {"expr": "", "threshold": 0.0,
                  "bins": {"below": 0, "above": 1}},
        "decide": {"let": [{"name": "x", "expr": "a", "scale": "percentile"}],
                   "rules": [{"when": "x > 50", "bin": 1}],
                   "otherwise": {"bin": 0}, "score": "x"},
    })
    rows = [{"defect_id": str(i), "ok": True, "bin": 0, "score": 0.0,
             "features": {"a": float(i), "x": float(i)}} for i in range(5)]

    apply_lot_scaling(r, rows)
    once = [rw["features"]["x"] for rw in rows]
    apply_lot_scaling(r, rows)

    assert [rw["features"]["x"] for rw in rows] == once
    assert [rw["features"]["x_raw"] for rw in rows] == [0., 1., 2., 3., 4.]

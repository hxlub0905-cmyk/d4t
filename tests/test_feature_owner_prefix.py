# F17-②：特徵的身分是結構，撞名的前綴是流名。
"""同一件事在 d4t 裡有兩種做法，而它們以前給出兩種名字：

=========================================  =====================================
做法                                       名字（F17-② 之後）
=========================================  =====================================
一張 Gray level 卡，test 與 ref 都接進來     ``test_glv_mean`` ``ref_glv_mean``
兩張 Gray level 卡，一張接 test 一張接 ref   ``test_glv_mean`` ``glv_mean``
=========================================  =====================================

改的是**被蓋掉那一份**的前綴：``glv_A_glv_mean``（節點 id，等於 `node_3`）
→ ``test_glv_mean``（那條流的名字）。上面那一種是 `MultiSourceStep` 的規則
（使用者 2026-08-17 定調的「自動加流名前綴」），這一輪把下面那一種的**前綴**
補齊成同一套。`engine.py` 的舊註解本來就寫著這件事：「F9-5 之後線會有自己的
身分，那時前綴可以換成線名」。

⚠ **兩種做法的名字仍然不會完全一樣，那是刻意的。** 兩張卡那一種，最後寫的
那個保留短名 ``glv_mean``（D2，使用者 2026-08-16 定調）。要讓它也變成
``ref_glv_mean``，就得**把贏的那個改名** —— 而那會讓 ``glv_mean`` 突然不存在，
每一份既有 recipe 的分數表達式當場失效。所以這裡只補前綴，不動短名。
下面 `test_the_two_ways_still_differ_on_purpose` 把這件事釘住。

這一份鎖住四件事：

1. **被蓋掉那份的前綴是流名**（這一輪的重點），而短名的規則沒有變；
2. 沒撞名時**一個字都不會變**（D2 —— 那是黃金值不動的前提）；
3. **擁有者是寫進來的當下記的**，不是事後比對 dict 差異推的；
4. 舊 recipe 指著舊名字時**遷移得過去**，不是變成一條 unknown-feature ——
   而那一道遷移住在 `Recipe.load`（讀檔案）**不是** `from_json_dict`（重建物件），
   因為它不冪等而重建那條路是 worker 走的（鐵則 9）。整條性質見
   `tests/test_recipe_roundtrip.py`。

⚠ **`feature_math` / `feature_fill` 2026-08-27 刪掉了**（Phase 3）。這一檔跟著
少了一條：``the_migration_also_reaches_the_algo_card``（改名遷移會不會走進那張
卡的算式）。**帶著那張卡的舊 recipe 現在是一條 `unknown-step`，跑不起來** ——
跑不起來的 recipe 不需要有人幫它改名。判定段的算式（`let` / 樹）走
``_migrate_decide_renames``，那條路還在，由 ``test_rename_fallout.py`` 守。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest.dataset import load_dataset  # noqa: E402
from d4t.core.pipeline import run_defect  # noqa: E402
from d4t.core.pipeline.context import FEATURE_OWNER_KEY, Context  # noqa: E402
from d4t.core.pipeline.engine import feature_prefix  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    Edge, Recipe, RecipeNode, ScoreSpec,
)
from d4t.core.pipeline.step import get_step  # noqa: E402

KIND = "ebi_patch"


@pytest.fixture(scope="module")
def item():
    from make_sample import generate
    import tempfile
    lot = generate(tempfile.mkdtemp(), n=3, seed=7)
    return load_dataset(lot["klarf"]).items[0]


def _run(nodes, edges, order):
    rec = Recipe(recipe_id="t", routes={KIND: order},
                 edges=[Edge(*e) for e in edges], nodes=nodes,
                 score=ScoreSpec(expr="1", threshold=1.0, bins={}))
    return rec


def _glv(nid, source):
    return RecipeNode(nid, "glv_stats", {"source": source,
                                         "metrics": "glv_mean"})


# --------------------------------------------------------------------------- #
# 1. 兩種做法給同一組名字
# --------------------------------------------------------------------------- #
def test_the_rescued_name_is_the_stream_not_the_node_id(item):
    """**這一條就是這一輪的全部。**

    兩邊算出來的數字一模一樣（實測 107.2673 / 107.2712 逐位元組相同），而
    被蓋掉那一份的名字以前叫 ``glv_A_glv_mean``（節點 id，對使用者等於
    `node_3`），現在叫 ``test_glv_mean``。
    """
    one = _run({"load": RecipeNode("load", "load_patch", {}),
                "glv": _glv("glv", "test,ref")},
               [("load", "glv", "test", "source"),
                ("load", "glv", "ref", "source")],
               ["load", "glv"])
    two = _run({"load": RecipeNode("load", "load_patch", {}),
                "glv_A": _glv("glv_A", "test"),
                "glv_B": _glv("glv_B", "ref")},
               [("load", "glv_A", "test", "source"),
                ("load", "glv_B", "ref", "source")],
               ["load", "glv_A", "glv_B"])

    a = {k: v for k, v in run_defect(one, item, KIND).features.items()
         if "glv_mean" in k}
    b = {k: v for k, v in run_defect(two, item, KIND).features.items()
         if "glv_mean" in k}
    assert set(a) == {"test_glv_mean", "ref_glv_mean"}
    assert set(b) == {"test_glv_mean", "glv_mean"}, (
        "被蓋掉的那份還在用節點 id 當前綴：%s" % sorted(b))
    # **數字是同兩個** —— 名字的差別跟算出來的東西無關。
    assert a["test_glv_mean"] == pytest.approx(b["test_glv_mean"])
    assert a["ref_glv_mean"] == pytest.approx(b["glv_mean"])
    assert not [k for k in b if k.startswith("glv_A") or k.startswith("glv_B")]


def test_the_two_ways_still_differ_on_purpose(item):
    """**贏的那個保留短名** —— 這是 D2，不是漏掉的。

    要讓兩種做法的名字完全一樣，就得把贏的那個也改名（``glv_mean`` →
    ``ref_glv_mean``）。那會讓 ``glv_mean`` 突然不存在，每一份既有 recipe 的
    分數表達式當場失效 —— 而「救回舊的是純粹加東西，沒有任何既有的東西被拿走」
    正是這套機制當初成立的理由。
    """
    two = _run({"load": RecipeNode("load", "load_patch", {}),
                "glv_A": _glv("glv_A", "test"),
                "glv_B": _glv("glv_B", "ref")},
               [("load", "glv_A", "test", "source"),
                ("load", "glv_B", "ref", "source")],
               ["load", "glv_A", "glv_B"])
    feats = run_defect(two, item, KIND).features
    assert "glv_mean" in feats and "ref_glv_mean" not in feats


def test_the_last_writer_still_keeps_the_short_name(item):
    """D2 沒有變：**撞名時最後寫的那個保留原名**，只有被蓋掉的加前綴。

    反過來做（把新的改名）會讓 `glv_mean` 突然不存在，一份跑得好好的 recipe
    的分數表達式當場失效。
    """
    two = _run({"load": RecipeNode("load", "load_patch", {}),
                "glv_A": _glv("glv_A", "test"),
                "glv_B": _glv("glv_B", "ref")},
               [("load", "glv_A", "test", "source"),
                ("load", "glv_B", "ref", "source")],
               ["load", "glv_A", "glv_B"])
    r = run_defect(two, item, KIND)
    assert "glv_mean" in r.features                       # 短名還在
    # 短名的值 = **最後寫的那張卡**（glv_B，接 ref）算出來的。
    assert r.features["glv_mean"] != pytest.approx(r.features["test_glv_mean"])


# --------------------------------------------------------------------------- #
# 2. 沒撞名 → 一個字都不變（黃金值不動的前提）
# --------------------------------------------------------------------------- #
def test_without_a_collision_nothing_is_renamed(item):
    one = _run({"load": RecipeNode("load", "load_patch", {}),
                "glv": _glv("glv", "test")},
               [("load", "glv", "test", "source")],
               ["load", "glv"])
    feats = run_defect(one, item, KIND).features
    assert "glv_mean" in feats
    assert not [k for k in feats if k.endswith("_glv_mean")], (
        "沒有撞名卻有人被加了前綴：%s" % sorted(feats))


# --------------------------------------------------------------------------- #
# 3. 前綴怎麼挑：先問「寫哪一條」，再問「讀哪一條」
# --------------------------------------------------------------------------- #
def test_the_prefix_prefers_the_stream_the_card_writes():
    """`normalize` 可以**讀兩條、寫一條**（`range_from` 借另一條的範圍）。

    它的 `clip_frac` 講的是「被處理的那一條被削掉多少」，所以前綴要是它
    **寫**的那條，不是它看過的兩條。
    """
    cls = get_step("normalize")
    assert feature_prefix("norm_ref", cls,
                          {"streams": "ref", "range_from": "test"}) == "ref"
    assert feature_prefix("norm", cls, {"streams": "test"}) == "test"


def test_the_prefix_falls_back_to_the_node_id():
    """退路一定要在：不吃影像的卡、以及一張卡吃好幾條流的時候。"""
    assert feature_prefix("rep", get_step("output_report"),
                          {"folder": "/tmp/x"}) == "rep"
    assert feature_prefix("glv", get_step("glv_stats"),
                          {"source": "test,ref"}) == "glv"
    assert feature_prefix("x", None, {}) == "x"


# --------------------------------------------------------------------------- #
# 4. 擁有者是寫進來的當下記的
# --------------------------------------------------------------------------- #
def test_the_owner_is_recorded_at_write_time():
    """以前引擎是**比對 dict 前後差異**回推「這張卡產出了什麼」——
    而那份差異在「後面那張卡剛好算出一樣的值」時是空的（F9-3 踩過）。
    寫入當下就記，那個巧合就不存在了。
    """
    ctx = Context()
    ctx.current_node = "a"
    ctx.add_feature("x", 1.0)
    ctx.current_node = "b"
    ctx.add_feature("x", 1.0)          # **值一樣**
    assert ctx.meta[FEATURE_OWNER_KEY]["x"] == "b"
    assert ctx.meta["feature_overwrites"] == ["x"]


def test_nobody_owns_a_feature_written_outside_a_card():
    """跑完之後（或測試裡）直接寫的特徵不該掛在最後一張卡頭上。"""
    ctx = Context()
    ctx.add_feature("x", 1.0)
    assert FEATURE_OWNER_KEY not in ctx.meta


# --------------------------------------------------------------------------- #
# 5. 舊 recipe 遷移得過去
# --------------------------------------------------------------------------- #
def _loaded(tmp_path, d):
    """走**檔案**那一路 —— 遷移住在 `Recipe.load`（F17 審查之後）。"""
    import json
    path = tmp_path / "old.json"
    path.write_text(json.dumps(d), encoding="utf-8")
    return Recipe.load(path)


def test_an_old_expression_is_migrated(tmp_path):
    old = {
        "recipe_id": "old", "version": 3,
        "routes": {KIND: ["load", "norm_ref", "norm"]},
        "nodes": {
            "load": {"id": "load", "step": "load_patch", "params": {}},
            "norm_ref": {"id": "norm_ref", "step": "normalize",
                         "params": {"streams": "ref", "range_from": "test"}},
            "norm": {"id": "norm", "step": "normalize",
                     "params": {"streams": "test"}}},
        "score": {"expr": "norm_clip_frac + norm_ref_clip_frac * 2",
                  "threshold": 1.0, "bins": {"below": 0, "above": 1}},
    }
    assert _loaded(tmp_path, old).score.expr == "test_clip_frac + ref_clip_frac * 2"


def test_the_migration_leaves_a_users_own_name_alone(tmp_path):
    """判準是「舊東西在不在」（鐵則 9）：只有
    ``<節點 id>_<那張卡真的會產出的特徵名>`` 這個形狀才算數。

    少了最後那個條件，使用者自己取的名字（剛好以某個節點 id 開頭的那種）
    也會被改掉 —— 而那是**安靜地改壞一份跑得好好的 recipe**。
    """
    old = {
        "recipe_id": "old", "version": 3,
        "routes": {KIND: ["load", "norm"]},
        "nodes": {
            "load": {"id": "load", "step": "load_patch", "params": {}},
            "norm": {"id": "norm", "step": "normalize",
                     "params": {"streams": "test"}}},
        "score": {"expr": "norm_my_own_number + 1",
                  "threshold": 1.0, "bins": {"below": 0, "above": 1}},
    }
    assert _loaded(tmp_path, old).score.expr == "norm_my_own_number + 1"



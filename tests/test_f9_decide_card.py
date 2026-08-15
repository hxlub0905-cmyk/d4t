# F9 Phase 3d 第一批：分數不再是 recipe 上的一個欄位（2026-08-15）。
"""判定是畫布上的一張卡，`Recipe.score` 那個固定欄位退場。

這一支鎖住的是**使用者看得到的那幾件事**：

* 舊檔案照樣載得進來（`score` 區塊 → route 尾端一張 Decide 卡）；
* 存出去的檔案不再有 `score` 區塊，而且 round-trip 不會長出第二張卡；
* 沒有判定卡的 recipe 跑得完，但**沒有結論**（score/bin 是 None，不是 0）；
* 判定卡的算式欄配得到「Insert feature ▾」，列的是**上游**的特徵名
  （UI 那一半在 ``test_ui_f9_decide_card.py`` —— Qt 一律 lazy import）；
* `rescore` 兩種格式都讀得懂（資料庫裡是歷史快照，沒辦法遷移）。
"""
from __future__ import annotations

import json

import pytest

# 卡片註冊是 import 的副作用 —— 只 import pipeline 的話 registry 裡沒有 adc
# （CLAUDE.md §7 有這一列）。
import adept.core.steps  # noqa: F401

from adept.core.pipeline import Recipe, RecipeNode, validate
from adept.core.pipeline.step import PARAM_TYPES


# --------------------------------------------------------------------------- #
# 1. 舊檔案的 score 區塊
# --------------------------------------------------------------------------- #
def _legacy_dict(routes=None):
    return {
        "recipe_id": "legacy",
        "version": 1,
        "routes": routes or {"ebi_patch": ["load"]},
        "nodes": {"load": {"step": "load_patch", "params": {}}},
        "score": {"expr": "glv_max * 2", "threshold": 7.5,
                  "bins": {"below": 3, "above": 4}},
    }


def test_an_old_score_block_becomes_a_decide_card_at_the_end():
    rec = Recipe.from_json_dict(_legacy_dict())
    route = rec.routes["ebi_patch"]
    assert route[-1] == "decide", route
    p = rec.nodes["decide"].params
    assert rec.nodes["decide"].step == "adc"
    assert p["expr"] == "glv_max * 2"
    assert p["threshold"] == pytest.approx(7.5)
    # bins 的兩個值也要跟著搬 —— 掉了的話舊 recipe 會安靜地換一組 bin 編號
    assert p["bin_below"] == 3 and p["bin_above"] == 4


def test_each_route_gets_its_own_decide_card():
    """共用一張的話，「改 rsem 的門檻」會順手改掉 patch 的。"""
    rec = Recipe.from_json_dict(_legacy_dict(
        {"ebi_patch": ["load"], "rsem": ["load"]}))
    tails = {k: v[-1] for k, v in rec.routes.items()}
    assert len(set(tails.values())) == 2, tails
    for nid in tails.values():
        assert rec.nodes[nid].step == "adc"


def test_saving_no_longer_writes_a_score_block():
    rec = Recipe.from_json_dict(_legacy_dict())
    assert "score" not in rec.to_json_dict()


def test_a_round_trip_does_not_grow_a_second_decide_card():
    """遷移的判準是「這個 dict 有 score 這個鍵」，而 ``to_json_dict`` 不寫它。

    ``run_batch`` 會把 recipe 序列化送進 worker 再反序列化 —— 那趟往返如果又
    被當成「舊檔案」，子進程就會多一張判定卡，然後 ``_judge`` 判定兩張都跑到、
    整批失敗。跟 CLAUDE.md §7 的 ``subtract.b`` 是同一個坑。
    """
    rec = Recipe.from_json_dict(_legacy_dict())
    again = Recipe.from_json_dict(rec.to_json_dict())
    assert sorted(again.nodes) == sorted(rec.nodes)
    assert again.routes == rec.routes


# --------------------------------------------------------------------------- #
# 2. 沒有判定卡 = 沒有結論（不是 0 分）
# --------------------------------------------------------------------------- #
def test_a_recipe_with_no_decide_card_is_linted_and_scores_nothing(tmp_path):
    from types import SimpleNamespace

    from adept.core.pipeline.engine import NO_DECIDE_CARD_NOTE, run_defect

    rec = Recipe(recipe_id="silent", routes={"ebi_patch": ["load"]},
                 nodes={"load": RecipeNode("load", "load_patch", {})})

    codes = [i.code for i in validate(rec, kind="ebi_patch")]
    assert "no-decision" in codes
    assert [i for i in validate(rec, kind="ebi_patch")
            if i.code == "no-decision"][0].level == "warning"

    item = SimpleNamespace(defect_id="d1", nm_per_px=None,
                           images={"test": None})
    r = run_defect(rec, item, "ebi_patch", keep_context=True)
    # 載入會失敗（這個假 item 沒有真的影像），但重點是 score 從來不會是 0
    assert r.score is None and r.bin is None
    if r.ok:
        assert NO_DECIDE_CARD_NOTE in r.context.meta.get("warnings", [])


# --------------------------------------------------------------------------- #
# 3. expr 參數型別
# --------------------------------------------------------------------------- #
def test_expr_is_a_real_param_type_and_the_decide_card_uses_it():
    from adept.core.steps.adc import AdcStep

    assert "expr" in PARAM_TYPES
    spec = [s for s in AdcStep.params if s.name == "expr"][0]
    assert spec.type == "expr"
    # 型別上仍是 str —— recipe JSON 的格式沒有變
    assert spec.validate("a + b") == "a + b"


# --------------------------------------------------------------------------- #
# 4. rescore 兩種格式都要讀得懂
# --------------------------------------------------------------------------- #
def _run_dict(nodes, extra=None):
    d = {"recipe_id": "r", "version": 1, "author": "", "description": "",
         "routes": {"ebi_patch": list(nodes)}, "nodes": nodes, "edges": []}
    d.update(extra or {})
    return d


def test_rescore_reads_the_decide_card():
    from adept.core.store.results import _decision_spec

    rdict = _run_dict({"d": {"step": "adc", "params": {
        "expr": "glv_max", "threshold": 5.0,
        "bin_below": 2, "bin_above": 9}}})
    spec, write_back = _decision_spec(rdict, "run1")
    assert spec["expr"] == "glv_max"
    assert spec["threshold"] == pytest.approx(5.0)
    assert spec["bins"] == {"below": 2, "above": 9}

    write_back({"expr": "glv_mean", "threshold": 1.0,
                "bins": {"below": 0, "above": 1}})
    assert rdict["nodes"]["d"]["params"]["expr"] == "glv_mean"
    assert rdict["nodes"]["d"]["params"]["bin_above"] == 1


def test_rescore_still_reads_a_legacy_score_block():
    """資料庫裡存的是 recipe **歷史快照**，沒有辦法遷移。"""
    from adept.core.store.results import _decision_spec

    rdict = _run_dict({}, {"score": {"expr": "old", "threshold": 3.0,
                                     "bins": {"below": 0, "above": 1}}})
    spec, write_back = _decision_spec(rdict, "run0")
    assert spec["expr"] == "old"
    write_back({"expr": "new", "threshold": 3.0, "bins": {}})
    assert rdict["score"]["expr"] == "new"


def test_rescore_refuses_to_guess_between_two_decide_cards():
    from adept.core.store.results import _decision_spec

    rdict = _run_dict({
        "da": {"step": "adc", "params": {"expr": "a", "threshold": 1.0}},
        "db": {"step": "adc", "params": {"expr": "b", "threshold": 2.0}}})
    with pytest.raises(ValueError) as e:
        _decision_spec(rdict, "run2")
    assert "da" in str(e.value) and "db" in str(e.value)


# --------------------------------------------------------------------------- #
# 5. 卡片庫上得了台面
# --------------------------------------------------------------------------- #
def test_the_decide_card_is_in_the_library():
    """收在 ``HIDDEN_STEPS`` 裡的判定卡 = 做好了但沒有人打開。"""
    from adept.core.pipeline import list_steps
    from adept.ui.scope import visible_steps

    keys = [d["key"] for d in visible_steps([s.describe() for s in list_steps()])]
    assert "adc" in keys


def test_the_example_recipe_ships_in_the_new_shape():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "examples" / "recipes" \
        / "cross_regions.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "score" not in raw, "範例 recipe 還是舊格式"
    adc = [n for n in raw["nodes"].values() if n["step"] == "adc"]
    assert len(adc) == 1 and str(adc[0]["params"]["expr"]).strip()

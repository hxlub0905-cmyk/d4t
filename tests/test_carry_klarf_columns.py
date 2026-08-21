# F16 Stage 4：main lot 的 KLARF 欄位帶成 feature。
"""使用者對 ADC 的定調（2026-08-20）是

> 主要就是利用 feature 內數值資料留跟**原始 klarf 帶的資訊**去做分類

而在此之前那些欄位**進不了 pipeline**：`DefectItem.fields` 只有掛上來的第二份
會填（F15 的 `pair_source`），main 那一份是空的 —— `ingest/dataset.py` 的註解
當時寫的理由是「每一顆多帶 24 個字串對誰都沒有好處」。

這一份鎖住的是那個缺口補起來之後的四件事：

1. **沒勾就一欄都不帶**（既有的 recipe 一個位元組都沒多帶，黃金值不動）；
2. 勾了就變成 feature，而且**名字就是欄名**（打進分數表達式不用翻譯）；
3. **打錯欄名擋在跑之前**（少一欄的 CSV 跟成功的 CSV 長得一模一樣）；
4. 非數字的欄位不進 features（features 是 `Dict[str, float]`），而且**要講出來**
   ——它去了 meta，報表拿得到。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest.dataset import (  # noqa: E402
    columns_of, fill_fields, missing_columns_of,
)
from d4t.core.ingest.dataset import load_dataset  # noqa: E402
from d4t.core.pipeline import get_step, run_defect  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    Recipe, RecipeNode, ScoreSpec,
)
from d4t.core.pipeline.step import StepError  # noqa: E402
from d4t.core.steps.load import columns_for_main  # noqa: E402


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("carry")), n=4, seed=7)


@pytest.fixture(scope="module")
def dataset(lot):
    return load_dataset(lot["klarf"])


def _recipe(carry=""):
    return Recipe(
        recipe_id="t", routes={"ebi_patch": ["load"]},
        nodes={"load": RecipeNode("load", "load_patch", {"carry": carry})},
        score=ScoreSpec(expr="n_channels", threshold=1.0,
                        bins={"below": 0, "above": 1}))


# --------------------------------------------------------------------------- #
# 1. 沒勾就一欄都不帶
# --------------------------------------------------------------------------- #
def test_nothing_ticked_carries_nothing(dataset):
    """既有的 recipe 一個位元組都沒多帶 —— 那是黃金值不動的前提。"""
    assert columns_for_main(_recipe().nodes.values()) == []
    res = run_defect(_recipe(), dataset.items[0], dataset.kind)
    assert res.ok, res.error
    assert set(res.features) == {"n_channels", "score"}, sorted(res.features)


def test_the_declaration_follows_the_parameter(dataset):
    card = get_step("load_patch")
    assert card.resolve_features({}) == ["n_channels"]
    assert card.resolve_features({"carry": "roughbinnumber"}) == [
        "n_channels", "ROUGHBINNUMBER"]


# --------------------------------------------------------------------------- #
# 2. 勾了就進 features，名字就是欄名
# --------------------------------------------------------------------------- #
def _pick_numeric_column(dataset):
    """挑一個這份合成 KLARF 上真的是數字的欄。"""
    fill_fields(dataset, None)
    fields = dict(dataset.items[0].fields)
    for name, raw in fields.items():
        try:
            float(raw)
        except (TypeError, ValueError):
            continue
        return name
    pytest.skip("這份 KLARF 沒有數字欄")


def test_a_carried_column_becomes_a_feature_under_its_own_name(dataset):
    col = _pick_numeric_column(dataset)
    recipe = _recipe(col)
    fill_fields(dataset, columns_for_main(recipe.nodes.values()))
    res = run_defect(recipe, dataset.items[0], dataset.kind)
    assert res.ok, res.error
    assert col in res.features, sorted(res.features)
    # 名字**就是欄名**：KLARF 的欄名本來就是合法的變數名，打進分數表達式
    # 不用翻譯。（`pair_source` 加 pair_ 前綴是因為它帶的是另一份的同名欄。）
    assert res.features[col] == pytest.approx(
        float(dataset.items[0].fields[col]))


def test_the_column_names_are_what_the_ui_offers(dataset):
    """欄名程式知道，就不該讓使用者用打的（同 stream_choices / region_choices）。"""
    cols = columns_of(dataset)
    assert cols and all(c == c.upper() for c in cols)
    spec = next(p for p in get_step("load_patch").params if p.name == "carry")
    assert spec.choices_from == "main_columns"
    # `choice` 會擋掉不在清單裡的值，而 recipe 是在資料載進來**之前**讀的
    assert spec.type == "multi_choice", \
        "用 choice 的話，每一份存了欄名的 recipe 都會在開檔那一刻爆掉"


# --------------------------------------------------------------------------- #
# 3. 打錯欄名擋在跑之前
# --------------------------------------------------------------------------- #
def test_a_column_this_lot_does_not_have_is_caught(dataset):
    recipe = _recipe("NOSUCHCOLUMN")
    fill_fields(dataset, columns_for_main(recipe.nodes.values()))
    res = run_defect(recipe, dataset.items[0], dataset.kind)
    assert not res.ok
    assert "NOSUCHCOLUMN" in res.error
    # 訊息要列出**它有的那幾欄**（打錯字的人最需要的正是這個）
    assert "does have" in res.error


def test_missing_columns_are_answered_where_the_doc_still_is(dataset):
    """「那它有哪些欄」只有 ingest 那一層答得出來（卡片手上只有複製過去的）。"""
    assert missing_columns_of(dataset, ["nosuchcolumn"]) == ["NOSUCHCOLUMN"]
    assert missing_columns_of(dataset, columns_of(dataset)[:1]) == []


# --------------------------------------------------------------------------- #
# 4. 非數字的欄位不進 features
# --------------------------------------------------------------------------- #
def test_a_text_column_goes_to_meta_not_to_features(dataset):
    """features 是 `Dict[str, float]` —— 塞一個字串進去會讓分數表達式炸在
    一個跟它無關的地方。同 `pair_source` 的處置，不發明第二種。"""
    from d4t.core.pipeline.context import Context

    from d4t.core.steps.load import _carry_features

    class _Item:
        fields = {"WORDS": "abc", "NUM": "12.5"}

    ctx = Context(images={})
    _carry_features(ctx, _Item(), {"carry": "WORDS,NUM"}, "load_patch")
    assert ctx.features == {"NUM": 12.5}
    assert ctx.meta["klarf_fields"] == {"WORDS": "abc"}


# --------------------------------------------------------------------------- #
# 5. 只複製點名的那幾欄（記憶體與 pickle 的成本）
# --------------------------------------------------------------------------- #
def test_only_the_named_columns_are_copied(dataset):
    """一份 raw data 是幾十萬顆 ×24 欄字串。這一條鎖的是那個成本沒有被忘記。"""
    col = _pick_numeric_column(dataset)
    n = fill_fields(dataset, [col])
    assert n == 1
    assert set(dataset.items[0].fields) == {col}
    # 一格都沒指定 = 全帶（CLI 與測試的路）
    assert fill_fields(dataset, None) == len(columns_of(dataset))


def test_the_union_across_load_cards_is_what_gets_copied():
    """兩張 Load 卡（patch + sidecar 那種 recipe）各要幾欄 → 聯集。

    **這件事只寫在 `columns_for_main` 裡**：抄第二份出去的話，「哪幾欄要帶」
    就有兩個答案，而少複製一欄的症狀是「這一欄不見了」——而它其實在。
    """
    nodes = [RecipeNode("a", "load_patch", {"carry": "aa, bb"}),
             RecipeNode("b", "load_single", {"carry": "bb,cc"}),
             RecipeNode("c", "glv_stats", {"carry": "zz"})]   # 不是 Load 卡
    assert columns_for_main(nodes) == ["AA", "BB", "CC"]


def test_a_dict_of_nodes_is_not_silently_empty():
    """`recipe.nodes` 是 ``{id: RecipeNode}``，而**直接迭代它拿到的是 id 字串**。

    這個 bug 踩到了（CLI 那條路），而它的症狀離原因很遠：`columns_for_main`
    安靜地回空清單 → 一欄都沒填 → 每一顆都說「這份 KLARF 沒有那個欄位」，
    而那句話是錯的（欄位在，只是沒複製）。所以這支自己吃得下 dict，而不是
    要求每個呼叫端記得加 `.values()`。
    """
    nodes = {"a": RecipeNode("a", "load_patch", {"carry": "xrel"})}
    assert columns_for_main(nodes) == ["XREL"]
    assert columns_for_main(nodes.values()) == ["XREL"]
    assert columns_for_main(None) == []


def test_the_cli_really_carries_the_column(tmp_path, lot):
    """端到端：`python -m d4t run` 之後，那一欄要出現在 CSV 上。

    這一條走的是**跟使用者一樣的路**（recipe JSON → CLI → CSV），而上面那個
    dict 的 bug 正是只有這條路踩得到 —— 單元測試傳的是 list。
    """
    import json
    import subprocess

    repo = Path(__file__).resolve().parent.parent
    doc = {"recipe_id": "carry", "version": 1,
           "routes": {"ebi_patch": ["load", "glv"]},
           "nodes": {
               "load": {"step": "load_patch", "params": {"carry": "XREL"},
                        "enabled": True},
               "glv": {"step": "glv_stats",
                       "params": {"source": "test", "metrics": "glv_max"},
                       "enabled": True}},
           "edges": [],
           "score": {"expr": "glv_max", "threshold": 1.0,
                     "bins": {"below": 0, "above": 1}}}
    rp = tmp_path / "r.json"
    rp.write_text(json.dumps(doc), encoding="utf-8")
    csv_path = tmp_path / "out.csv"
    proc = subprocess.run(
        [sys.executable, "-m", "d4t", "run", str(rp), lot["klarf"],
         "--csv", str(csv_path)],
        cwd=str(repo), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    header = csv_path.read_text(encoding="utf-8-sig").splitlines()[0]
    assert "XREL" in header, header


def test_the_cli_refuses_a_column_the_lot_does_not_have(tmp_path, lot):
    """整批跑完才發現「那一欄根本不存在」是最貴的一種發現方式（F15-2）。"""
    import json
    import subprocess

    repo = Path(__file__).resolve().parent.parent
    doc = {"recipe_id": "carry", "version": 1,
           "routes": {"ebi_patch": ["load"]},
           "nodes": {"load": {"step": "load_patch",
                              "params": {"carry": "NOSUCHCOL"},
                              "enabled": True}},
           "edges": [],
           "score": {"expr": "n_channels", "threshold": 1.0,
                     "bins": {"below": 0, "above": 1}}}
    rp = tmp_path / "bad.json"
    rp.write_text(json.dumps(doc), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "d4t", "run", str(rp), lot["klarf"]],
        cwd=str(repo), capture_output=True, text=True)
    assert proc.returncode == 2, proc.stdout
    assert "NOSUCHCOL" in proc.stderr
    # 要列出**它有的那幾欄** —— 打錯字的人最需要的正是這個
    assert "DEFECTID" in proc.stderr

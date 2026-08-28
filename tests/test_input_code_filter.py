# F50：Input 的「只跑這幾個 code」（2026-08-28）。
"""使用者：「直接在 Input 內加入 input code 的功能（可選，選擇 KLARF 內哪個
column code 的 image 才要跑運算）」。

**「不跑」的意思是根本不進來，不是跑了再跳過。** 那個選擇是這一支測試的骨架
—— 它買到的三件事各有一條：

* 不需要第三種結果狀態 → **CSV 的欄、bin 的統計一個位元組都不用動**；
* **被篩掉的那幾顆 KLARF 不會被改寫**（它們沒有結果，寫回那一支碰不到）；
* **它會進快取簽章，而那是刻意的** —— 簽章收那張卡的每一個參數（`carry`
  也一樣），要排除就得發明「這一格不影響結果」的標記，而標錯的下場是拿到
  上一次設定算出來的影像。代價不對等：進去最壞是慢一次，漏標最壞是錯的。

還有一條是**嚴格附加**：兩格都空 = 既有的每一份 recipe 一個位元都沒變。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline.batch import item_filters, select_items  # noqa: E402
from d4t.core.pipeline.engine import image_segment_signature  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    Recipe, RecipeNode, ScoreSpec,
)
from d4t.core.pipeline.step import REGISTRY  # noqa: E402


class _Item:
    def __init__(self, did: str, code: str) -> None:
        self.defect_id = did
        self.fields = {"CLASSNUMBER": code}


class _DS:
    kind = "ebi_patch"

    def __init__(self) -> None:
        self.items = [_Item("1", "1"), _Item("2", "2"), _Item("3", "5"),
                      _Item("4", "2"), _Item("5", "9")]


def _recipe(**params) -> Recipe:
    return Recipe(
        recipe_id="f50",
        routes={"ebi_patch": ["load"]},
        nodes={"load": RecipeNode("load", "load_patch", dict(params))},
        score=ScoreSpec(expr="1.0", threshold=0.5,
                        bins={"below": 0, "above": 1}))


# --------------------------------------------------------------------------- #
# 1. 嚴格附加
# --------------------------------------------------------------------------- #
def test_no_filter_means_not_one_defect_is_dropped():
    ds = _DS()
    r = _recipe()
    assert item_filters(r) == []
    assert select_items(r, ds, ds.items) == ds.items


def test_a_card_that_does_not_declare_one_is_never_asked_to():
    """預設的 `Step.item_filter` 回 None —— 既有的每一張卡都沒變。"""
    for key, cls in REGISTRY.items():
        p = {s.name: s.default for s in cls.params}
        assert cls.item_filter(p) is None, key


# --------------------------------------------------------------------------- #
# 2. 篩對了
# --------------------------------------------------------------------------- #
def test_it_keeps_exactly_the_listed_codes():
    ds = _DS()
    r = _recipe(only_column="CLASSNUMBER", only_codes="2, 5")
    kept = [i.defect_id for i in select_items(r, ds, ds.items)]
    assert kept == ["2", "3", "4"]


def test_matching_ignores_case_and_spaces():
    """KLARF 的欄值進來是字串，而使用者填的 `2` 與檔案裡的 ` 2 ` 要對得上。"""
    ds = _DS()
    ds.items = [_Item("a", " 2 "), _Item("b", "x"), _Item("c", "X")]
    r = _recipe(only_column="classnumber", only_codes=" 2 , x ")
    assert [i.defect_id for i in select_items(r, ds, ds.items)] == ["a", "b", "c"]


def test_the_column_comes_from_the_card_not_a_hardcoded_load_list():
    """判準是 `Step.item_filter`，所以下一張讀資料的卡不必回來改引擎。"""
    r = _recipe(only_column="CLASSNUMBER", only_codes="2")
    assert item_filters(r) == [("load", "CLASSNUMBER", ("2",))]


def test_a_disabled_card_filters_nothing():
    r = _recipe(only_column="CLASSNUMBER", only_codes="2")
    r.nodes["load"].enabled = False
    assert item_filters(r) == []


# --------------------------------------------------------------------------- #
# 3. 填一半 = 不篩，而且要講一句
# --------------------------------------------------------------------------- #
def test_a_column_with_no_values_filters_nothing():
    """字面上「值要在一個空清單裡」＝一顆都不跑 —— 那絕對不是使用者的意思。"""
    ds = _DS()
    r = _recipe(only_column="CLASSNUMBER", only_codes="  ")
    assert select_items(r, ds, ds.items) == ds.items


def test_and_it_says_so():
    cls = REGISTRY["load_patch"]
    hints = cls.configuration_hints({"only_column": "CLASSNUMBER",
                                     "only_codes": ""})
    assert hints and "no values" in hints[0].lower()
    assert not cls.configuration_hints({"only_column": "CLASSNUMBER",
                                        "only_codes": "2"})


# --------------------------------------------------------------------------- #
# 4. 不准進快取簽章（鐵則 9 的反面）
# --------------------------------------------------------------------------- #
def test_the_filter_goes_into_the_cache_signature_and_that_is_deliberate():
    """**這一條翻過面，而理由比結論重要。**

    第一版寫的是「篩選不該進簽章」：它影響的是**哪幾顆**跑，不是任何一顆
    **怎麼**跑，所以改一次篩選就丟掉整份快取是白丟的。那個推論是對的。

    但簽章收的是那張卡的**每一個參數**（`carry` 也一樣在裡面，而它也不改
    影像），而那個保守是刻意的：要讓篩選不進去，就得發明一個「這一格不影響
    結果」的標記 —— 而那個標記標錯的下場是**拿到上一次設定算出來的影像**，
    也就是這個 repo 踩過七次的那個形狀。

    **代價與風險不對等：** 進了簽章，最壞是改篩選之後第一次跑比較慢；
    漏標一格，最壞是跑得完、有數字、而且是錯的。所以保守留著。
    這一條守的是那個決定 —— 哪天有人想加排除機制，先讀這段。
    """
    a = image_segment_signature(_recipe(), "ebi_patch")
    b = image_segment_signature(
        _recipe(only_column="CLASSNUMBER", only_codes="2, 5"), "ebi_patch")
    assert a != b, "篩選被排除在簽章外了 —— 那需要一個新機制，先讀這段"


# --------------------------------------------------------------------------- #
# 5. 端到端：篩了之後 CSV 的欄一個都沒變
# --------------------------------------------------------------------------- #
def test_the_result_shape_is_untouched(tmp_path):
    """沒有第三種狀態 —— 被篩掉的顆**不在結果裡**，不是一列 `skipped`。"""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from make_sample import generate

    from d4t.core.ingest.dataset import load_dataset
    from d4t.core.pipeline.batch import run_batch
    from d4t.core.export.report import BASE_COLUMNS

    lot = generate(str(tmp_path / "lot"), n=8, seed=7, class_by_truth=True)
    ds = load_dataset(lot["klarf"])
    recipe = _recipe()

    full = run_batch(recipe, ds, workers=1)
    picked = run_batch(_recipe(only_column="CLASSNUMBER", only_codes="1"),
                       ds, workers=1)

    assert 0 < len(picked) < len(full), (len(picked), len(full))
    for row in picked:
        for col in BASE_COLUMNS:
            assert col in row, col
        assert "skipped" not in row, "多出了一種結果狀態"

    # 留下來的那幾顆，**逐項跟沒篩的時候相同**（篩選不改任何一顆怎麼算）。
    by_id = {str(r["defect_id"]): r for r in full}
    for row in picked:
        same = by_id[str(row["defect_id"])]
        assert row["features"] == same["features"]
        assert row["score"] == same["score"] and row["bin"] == same["bin"]

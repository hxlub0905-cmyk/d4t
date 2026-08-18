# F11 Region-1 驗收：標在 Golden Cell 上的具名區域（一個名字好幾個矩形）。
"""這一份鎖住的是**編碼**，不是幾何（幾何在 `test_roi_template.py`）。

為什麼編碼值得一份自己的測試：``to_json_dict → from_json_dict`` 是
``run_batch`` 送 recipe 進 worker 的路，它一旦不是 identity，``workers=1``
與 ``workers=2`` 就會算出不同的分數（鐵則 9，真的發生過）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adept.core.pipeline.cellrois import (  # noqa: E402
    CellRoiError, format_cell_rois, parse_cell_rois, region_names,
)


def test_nothing_marked_yet_is_legal():
    """空的 = 還沒標，那是新卡片的預設值 —— 由 configuration_issues 講，不是錯誤。"""
    assert parse_cell_rois("") == []
    assert parse_cell_rois(None) == []


def test_one_region_several_rectangles():
    got = parse_cell_rois("epi: 0.1,0,0.25,1; 0.62,0,0.25,1")
    assert got == [("epi", [(0.1, 0.0, 0.25, 1.0), (0.62, 0.0, 0.25, 1.0)])]


def test_several_regions():
    got = parse_cell_rois("epi: 0,0,1,1 | mg: 0.2,0,0.3,1")
    assert [name for name, _b in got] == ["epi", "mg"]
    assert region_names("epi: 0,0,1,1 | mg: 0.2,0,0.3,1") == ["epi", "mg"]


@pytest.mark.parametrize("text", [
    "epi: 0.1,0,0.25,1",
    "epi: 0.1,0,0.25,1; 0.62,0,0.25,1 | mg: 0,0,0.2,1",
])
def test_the_round_trip_changes_nothing(text):
    """正規化過的字串再走一次 parse→format 必須逐字元相同（鐵則 9）。"""
    once = format_cell_rois(parse_cell_rois(text))
    assert format_cell_rois(parse_cell_rois(once)) == once


def test_typed_and_drawn_values_normalise_to_the_same_string():
    """手打的 ``0.2000`` 與編輯器拉出來的 ``0.2`` 在 recipe 裡要長得一樣。"""
    a = format_cell_rois(parse_cell_rois("epi:0.2000,0.0000,0.3000,1.0000"))
    b = format_cell_rois(parse_cell_rois("epi: 0.2,0,0.3,1"))
    assert a == b == "epi: 0.2,0,0.3,1"


def test_the_order_is_kept():
    """排序會讓編輯器的清單在每次拖曳之後跳動 —— 這裡要的是穩定。"""
    text = "b: 0,0,1,1 | a: 0,0,1,1"
    assert format_cell_rois(parse_cell_rois(text)) == text


@pytest.mark.parametrize("text, says", [
    ("epi 0,0,1,1", "name"),
    ("my region: 0,0,1,1", "letters, digits and underscores"),
    ("epi: 0,0,1,1 | epi: 0,0,0.5,1", "twice"),
    ("epi: 0,0,1", "four numbers"),
    ("epi: 0,0,x,1", "not four numbers"),
    ("epi: 0,0,0,1", "no width or no height"),
    ("epi: 0,0,1.5,1", "bigger than one cell"),
    ("epi: 9,0,0.2,1", "more than one cell away"),
    ("epi:", "no boxes"),
])
def test_every_bad_value_gets_a_plain_sentence(text, says):
    """壞值不准跑到演算法裡，而擋下來的那句話要是白話的（鐵則 4）。"""
    with pytest.raises(CellRoiError) as e:
        parse_cell_rois(text)
    assert says in str(e.value)


def test_a_box_may_straddle_the_seam():
    """GC 的原點錨在最強的上升邊，所以要框的結構常常橫跨一格的接縫。"""
    assert parse_cell_rois("epi: 0.9,0,0.3,1") == [
        ("epi", [(0.9, 0.0, 0.3, 1.0)])]


def test_region_names_stays_quiet_on_a_half_typed_value():
    """宣告用的那一支不准拋 —— 打到一半的時候畫布不能整個消失。"""
    assert region_names("epi: 0,0,") == []


# --------------------------------------------------------------------------- #
# multi add —— 一次長出一整片等距的框
# --------------------------------------------------------------------------- #
def test_an_array_is_evenly_spaced_between_the_two_anchors():
    """間距是**算**出來的，不是拖出來的 —— pitch 是設計常數。"""
    from adept.core.pipeline.cellrois import array_boxes

    boxes = array_boxes((0.1, 0.5), (0.7, 0.5), 0.05, 0.4, nx=4, ny=1)
    assert len(boxes) == 4
    centres = [b[0] + b[2] / 2.0 for b in boxes]
    assert centres[0] == pytest.approx(0.1)
    assert centres[-1] == pytest.approx(0.7)
    gaps = [b - a for a, b in zip(centres, centres[1:])]
    assert all(g == pytest.approx(gaps[0]) for g in gaps)


def test_an_array_of_one_sits_on_the_first_anchor():
    """n=1 沒有「間距」可言 —— 不要除以零，也不要偷偷變成兩個。"""
    from adept.core.pipeline.cellrois import array_boxes

    boxes = array_boxes((0.3, 0.4), (0.9, 0.8), 0.2, 0.2, nx=1, ny=1)
    assert len(boxes) == 1
    assert boxes[0] == pytest.approx((0.2, 0.3, 0.2, 0.2))


def test_a_two_dimensional_array_is_the_product():
    from adept.core.pipeline.cellrois import array_boxes

    boxes = array_boxes((0.1, 0.1), (0.9, 0.9), 0.1, 0.1, nx=4, ny=3)
    assert len(boxes) == 12
    assert len({round(b[1], 6) for b in boxes}) == 3


def test_an_array_round_trips_through_the_recipe_string():
    """編輯器長出來的東西要存得進 recipe（也就是要過 parse 的每一條規則）。"""
    from adept.core.pipeline.cellrois import array_boxes

    text = format_cell_rois([("epi", array_boxes(
        (0.1, 0.5), (0.7, 0.5), 0.05, 0.4, nx=4, ny=1))])
    assert len(parse_cell_rois(text)[0][1]) == 4

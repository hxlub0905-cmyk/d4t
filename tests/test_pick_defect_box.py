# F20 驗收：「這一組框裡，哪一塊是缺陷那一塊」（2026-08-22）。
"""在這之前這件事是寫死的：**離 patch 正中心最近的那一塊**。

那句話假設 patch 是以缺陷為中心裁的。假設成立時它完全夠用而且不必接線；
但座標會偏 —— 在 ``0822test/mgepi_real3`` 上（缺陷離正中心中位數 7.1 px）
「離中心最近」只有 11/24 顆真的框到缺陷，換成「訊號最強」是 24/24，
而下游的凸出量 AUC 從 0.680 變成 0.985。

這一份鎖住三件事：兩種規則各自挑對、**沒接線要退回而且講出來**、
以及判斷用的那條流有進 ``resolve_reads``（不進去的話它就不在拓撲排序與
快取簽章裡，改一條線而簽章看不見 —— 鐵則 10）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from d4t.core.steps._util import pick_defect_box  # noqa: E402
from d4t.core.steps.roi_cross import RoiCrossStep  # noqa: E402
from d4t.core.steps.roi_template import RoiTemplateStep  # noqa: E402

SHAPE = (81, 81)
#: 三個框：左、正中間、右。故意讓「離中心最近」與「訊號最強」是不同的兩塊。
BOXES = [(6, 34, 12, 12), (35, 34, 12, 12), (63, 34, 12, 12)]


def _signal_on(box, value=200.0):
    img = np.full(SHAPE, 10.0)
    x, y, w, h = box
    img[y + 4:y + 8, x + 4:x + 8] = value
    return img


def test_centre_rule_picks_the_middle_one():
    idx, by_signal = pick_defect_box(BOXES, SHAPE, "centre")
    assert idx == 1
    assert by_signal is False


def test_strongest_rule_follows_the_signal_not_the_centre():
    """訊號在最右邊那塊 —— 挑它，不是挑正中間那塊。"""
    idx, by_signal = pick_defect_box(BOXES, SHAPE, "strongest",
                                     _signal_on(BOXES[2]))
    assert idx == 2
    assert by_signal is True


def test_strongest_rule_agrees_when_the_defect_really_is_in_the_middle():
    idx, by_signal = pick_defect_box(BOXES, SHAPE, "strongest",
                                     _signal_on(BOXES[1]))
    assert (idx, by_signal) == (1, True)


def test_nothing_wired_falls_back_and_says_so():
    """**這一條是重點。** 安靜地照做才是最糟的：使用者以為挑的是訊號最強的那塊，
    整批其實是用正中心挑的，而每一顆都吐得出正常的數字。"""
    idx, by_signal = pick_defect_box(BOXES, SHAPE, "strongest", None)
    assert idx == 1                     # 退回「離中心最近」
    assert by_signal is False           # 而且看得出來退了


def test_a_single_hot_pixel_does_not_steal_the_box():
    """挑之前先做 3×3 均值 —— 一顆熱點不該把整塊框挑走。"""
    img = np.full(SHAPE, 10.0)
    img[38, 40] = 255.0                                  # 正中間那塊：一顆熱點
    x, y, _w, _h = BOXES[2]
    img[y + 4:y + 8, x + 4:x + 8] = 90.0                 # 最右那塊：一小片
    idx, by_signal = pick_defect_box(BOXES, SHAPE, "strongest", img)
    assert (idx, by_signal) == (2, True)


def test_empty_box_list_does_not_raise():
    assert pick_defect_box([], SHAPE, "strongest", np.zeros(SHAPE)) == (0, False)


@pytest.mark.parametrize("step", [RoiCrossStep, RoiTemplateStep])
def test_the_judging_stream_is_declared_as_an_input(step):
    """它會改變框挑到哪一塊 ＝ 會改變下游的結果，所以它必須是一條真的線。"""
    base = {"source": "ref", "pick": "centre", "pick_source": "diff"}
    assert step.resolve_reads(base) == ["ref"]
    assert step.resolve_reads(dict(base, pick="strongest")) == ["ref", "diff"]
    # 選了規則但沒接線 —— 不能宣告一條不存在的流
    assert step.resolve_reads(dict(base, pick="strongest",
                                   pick_source="")) == ["ref"]


@pytest.mark.parametrize("step,name", [(RoiCrossStep, "cross_pick_by_signal"),
                                       (RoiTemplateStep, "pick_by_signal")])
def test_both_cards_report_whether_the_signal_was_really_used(step, name):
    params = {"output_prefix": "", "regions": "", "roi_out": "cross"}
    assert name in step.resolve_features(params)


def test_both_cards_say_it_the_same_way():
    """同一件事在兩張卡上要一字不差 —— 使用者只學一次。"""
    a = {q.name: q for q in RoiCrossStep.params}
    b = {q.name: q for q in RoiTemplateStep.params}
    for key in ("pick", "pick_source"):
        assert a[key].help == b[key].help
        assert a[key].label == b[key].label
        assert list(a[key].choices or []) == list(b[key].choices or [])

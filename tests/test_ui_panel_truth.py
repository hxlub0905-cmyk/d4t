# 面板不能說謊（常駐）。起於 F20 的 UI 這一半；2026-08-27 從
# `test_ui_f20_panel_truth.py` 改名（F39 A 組）——`row_labels` /
# `_focus_box_index` 別的地方沒有人碰。
"""面板與疊圖不能說謊（2026-08-22 起）。

兩件事，都是「同一個東西在兩個地方要一致」：

1. **列標題要說出真正把兩列分開的那件事。** 量測卡的面板一列一份記錄，而
   「一份」可以是一個區域、也可以是同一個區域的另一條影像流。標題原本一律
   寫區域名 —— 於是接了 test 與 ref 兩條流時兩列標的是同一個名字、同一個顏色。
2. **影像上醒目的那一個框，要是卡片真的挑走的那一塊。** 它的意思一直都是
   ``<name>_center``；F20 之前那等於「離正中心最近」，之後不是了。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from d4t.ui.inspectors import row_labels  # noqa: E402


def test_one_region_two_streams_says_the_stream():
    """接 test 與 ref 之後兩列都叫 ``mg_center`` —— 那是 2026-08-22 實際看到的。"""
    got = row_labels([{"region": "mg_center", "stream": "test"},
                      {"region": "mg_center", "stream": "ref"}])
    assert got == ["test", "ref"]


def test_several_regions_one_stream_still_says_the_region():
    """多區域是常態，那時候流名是多餘的 —— **把不變的那一半省掉**。"""
    got = row_labels([{"region": "epi", "stream": "test"},
                      {"region": "mg", "stream": "test"}])
    assert got == ["epi", "mg"]


def test_both_differ_says_both():
    got = row_labels([{"region": "epi", "stream": "test"},
                      {"region": "epi", "stream": "ref"},
                      {"region": "mg", "stream": "test"}])
    assert got == ["epi @ test", "epi @ ref", "mg @ test"]


def test_no_region_falls_back_to_the_whole_image():
    assert row_labels([{"region": "", "stream": "test"}]) == ["whole image"]
    assert row_labels([]) == []


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_the_highlighted_box_is_the_one_the_card_picked(qapp, monkeypatch):
    """疊圖上醒目的那一個 ＝ ``<name>_center``，**不是**離畫面中心最近的那個。

    這一條在 F20 之前恆真（那時候 `_center` 就是這樣定義的），
    所以它鎖住的是「改了挑框規則之後畫面有沒有跟上」。
    """
    from d4t.ui import studio as studio_mod

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        boxes = [(0.05, 0.45, 0.1, 0.1),      # 左邊
                 (0.45, 0.45, 0.1, 0.1),      # 正中心
                 (0.80, 0.45, 0.1, 0.1)]      # 右邊
        monkeypatch.setattr(type(win), "_defines_regions",
                            lambda self: True, raising=False)
        monkeypatch.setattr(type(win), "_picks_a_center",
                            lambda self: True, raising=False)
        # 卡片挑走的是最右邊那一塊（＝ 訊號最強的那一塊）
        monkeypatch.setattr(type(win), "_center_rects",
                            lambda self: [boxes[2]], raising=False)
        assert win._focus_box_index(boxes) == 2
        # 問不到（還沒跑過）→ Region 卡退回舊規則，不是不畫
        monkeypatch.setattr(type(win), "_center_rects",
                            lambda self: [], raising=False)
        assert win._focus_box_index(boxes) == 1
        # `pick="none"`（F31 T4）：卡片明講「沒有哪一格是缺陷那一塊」——
        # 退回舊規則畫一個醒目的，等於畫布替引擎說一句它沒說的話。
        monkeypatch.setattr(type(win), "_picks_a_center",
                            lambda self: False, raising=False)
        assert win._focus_box_index(boxes) == -1
    finally:
        win.close()
        win.deleteLater()


def test_a_measure_card_does_not_highlight_an_arbitrary_box(qapp, monkeypatch):
    """量測卡**引用**別人的區域，沒有哪一格是特別的 —— 就不要指。

    一個 24 格的區域被 pooled 成一堆像素時，把離畫面中心最近的那一格畫成醒目
    等於在說一件不成立的事。量測卡要指哪一格走自己的 `overlay_marks`。
    """
    from d4t.ui import studio as studio_mod

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        boxes = [(0.05, 0.45, 0.1, 0.1), (0.45, 0.45, 0.1, 0.1)]
        monkeypatch.setattr(type(win), "_center_rects",
                            lambda self: [], raising=False)
        monkeypatch.setattr(type(win), "_defines_regions",
                            lambda self: False, raising=False)
        assert win._focus_box_index(boxes) == -1
    finally:
        win.close()
        win.deleteLater()


def test_the_glv_card_outlines_the_box_its_panel_is_describing():
    """面板寫著 ``typical box #N of M``，影像上就要指得出第 N 格。

    只有一格的時候不畫 —— 那時候區域框本身就是答案，再描一次只是把線加粗。
    """
    import numpy as np

    from d4t.core.pipeline.context import Context
    from d4t.core.pipeline.step import get_step

    ctx = Context(images={"test": np.zeros((40, 40), np.float32)})
    ctx.set_roi_boxes("sp", [(0.1, 0.1, 0.2, 0.2), (0.6, 0.1, 0.2, 0.2),
                             (0.1, 0.6, 0.2, 0.2)])
    ctx.meta["glv_hist"] = [{"region": "sp", "stream": "test",
                             "box": 2, "boxes": 3}]
    card = get_step("glv_stats")
    lines, points, focus, labels = card.overlay_marks(ctx, {}, "test")
    # 一條線段 ＋ **四個角點**（線畫得很淡、點畫滿 —— 見那支的說明）
    assert len(lines) == len(points) == 1
    assert len(points[0]) == 4
    assert focus == 0 and set(labels) == {"sp"}
    xs = [pt[0] for pt in points[0]]
    ys = [pt[1] for pt in points[0]]
    assert min(xs) == pytest.approx(0.1) and max(xs) == pytest.approx(0.3)
    assert min(ys) == pytest.approx(0.6) and max(ys) == pytest.approx(0.8)

    # 別條流的不畫
    assert card.overlay_marks(ctx, {}, "ref")[0] == []
    # 只有一格 → 不畫
    ctx.meta["glv_hist"] = [{"region": "sp", "stream": "test",
                             "box": 0, "boxes": 1}]
    assert card.overlay_marks(ctx, {}, "test")[0] == []


def test_cd_marks_are_filtered_to_the_stream_you_are_looking_at():
    """一張卡在兩條流上各量一次 —— 那兩組線是在**兩張不同的影像**上量的。"""
    import numpy as np

    from d4t.core.pipeline.context import Context
    from d4t.core.pipeline.step import get_step

    ctx = Context(images={"test": np.zeros((20, 20), np.float32)})
    seg = [[(0.1, 0.5), (0.4, 0.5)]]
    ctx.meta["cd"] = {
        "test_": {"region": "mg", "stream": "test", "shape": "line",
                  "scan_lines": seg, "edges": [[(0.1, 0.5), (0.4, 0.5)]],
                  "median_index": 0},
        "ref_": {"region": "mg", "stream": "ref", "shape": "line",
                 "scan_lines": seg, "edges": [[(0.1, 0.5), (0.4, 0.5)]],
                 "median_index": 0},
    }
    card = get_step("cd_measure")
    assert len(card.overlay_marks(ctx, {})[0]) == 2          # 不給流 = 全部
    assert len(card.overlay_marks(ctx, {}, "test")[0]) == 1
    assert len(card.overlay_marks(ctx, {}, "ref")[0]) == 1
    assert card.overlay_marks(ctx, {}, "diff")[0] == []      # 沒量過這一條

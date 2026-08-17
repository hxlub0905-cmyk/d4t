# F11 Enhance-UI：兩個「單顆畫面上看不出來」的輔助（A 與 H）。
"""挑選標準沿用 F7-17：**這張卡最常見的失敗，在單顆畫面上看不出來嗎。**

A. **核心大小畫在影像上。** `flatten` 的 *Scale to remove* 與 `denoise` 的
   *Filter size* 的 help 裡唯一的規則是跟缺陷比大小（前者要明顯大於、後者要
   貼著），而畫面上原本沒有任何尺度參考 —— 使用者只能猜像素數。這跟 F7-8
   「把 min/max 填好滑桿是免費的」同一條：**使用者是一邊看影像一邊決定值的**。

H. **整批的削平走勢。** Enhance 的失敗是「某幾顆」的事，而調參數的人看的是
   第 1 顆。這是 `AlignInspector` 教過的那一課，換到 Enhance 上。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import wire_up  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import inspectors as insp_mod
    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    from adept.ui import widgets as widgets_mod
    g.update(QApplication=QApplication, insp_mod=insp_mod,
             studio_mod=studio_mod, theme_mod=theme_mod,
             widgets_mod=widgets_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1400, 900)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# A. 核心大小畫在影像上
# --------------------------------------------------------------------------- #
def test_the_flag_is_declared_not_guessed_from_the_unit():
    """``unit="px"`` 的參數有一半不是鄰域範圍 —— 拿方框表示「條紋間距」會讓
    **影像**說謊，而那跟畫布說謊是同一件事（F9/F10）。"""
    from adept.core.pipeline import get_step
    import adept.core.steps  # noqa: F401

    def spec(key, name):
        return [s for s in get_step(key).params if s.name == name][0]

    assert spec("flatten", "size").extent is True
    assert spec("denoise", "ksize").extent is True
    # 同樣是 unit="px"，但這些不是鄰域邊長
    assert spec("roi_cross", "vertical_pitch").extent is False
    assert spec("roi_cross", "inset").extent is False
    # 宣告要進 describe()，UI 才看得到
    got = {p["name"]: p for p in get_step("flatten").describe()["params"]}
    assert got["size"]["extent"] is True
    assert got["method"]["extent"] is False


def test_selecting_a_card_with_a_kernel_draws_it_on_the_image(window, tmp_path):
    from make_sample import generate

    out = generate(str(tmp_path / "lotA"), n=4, seed=41)
    window.load_dataset_path(out["klarf"], sync=True)
    src = window.model.node_order[0]
    f = wire_up(window.model, window.add_card_after(src, "flatten"))
    window._on_edge_added(src, f, "test")
    window.model.set_param(f, "size", 21)
    window.select_node(f)

    hint = window.image_view.kernel_hint()
    assert hint is not None
    assert hint[0] == 21.0 and hint[1] == "21 px"
    # 並排比對時左右都要有 —— 那個判斷在兩邊都要做
    assert window.image_view_b.kernel_hint() == hint


def test_dragging_the_slider_moves_the_box(window, tmp_path):
    """**這一支是這個輔助的全部意義**：值變了框要跟著變，不然它只是一張裝飾。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lotA2"), n=4, seed=42)
    window.load_dataset_path(out["klarf"], sync=True)
    src = window.model.node_order[0]
    f = wire_up(window.model, window.add_card_after(src, "flatten"))
    window._on_edge_added(src, f, "test")
    window.select_node(f)
    window._on_param_edited("size", 45)         # ParamForm 的唯一出口
    assert window.image_view.kernel_hint()[0] == 45.0


def test_a_card_without_a_kernel_clears_the_box(window, tmp_path):
    """換到 Normalize 的時候框要消失 —— 留著的話它會被讀成「這張卡的核心」。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lotA3"), n=4, seed=43)
    window.load_dataset_path(out["klarf"], sync=True)
    src = window.model.node_order[0]
    f = wire_up(window.model, window.add_card_after(src, "flatten"))
    window._on_edge_added(src, f, "test")
    n = wire_up(window.model, window.add_card_after(f, "normalize"))
    window._on_edge_added(f, n, "test")

    window.select_node(f)
    assert window.image_view.kernel_hint() is not None
    window.select_node(n)
    assert window.image_view.kernel_hint() is None


def test_a_hidden_row_does_not_leave_a_box_behind(window, tmp_path):
    """`size` 被 ``show_when`` 藏起來（去條紋方法用不到它）的時候，畫面上不該有
    一個跟著一列看不見的參數變的方框。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lotA4"), n=4, seed=44)
    window.load_dataset_path(out["klarf"], sync=True)
    src = window.model.node_order[0]
    f = wire_up(window.model, window.add_card_after(src, "flatten"))
    window._on_edge_added(src, f, "test")
    window.select_node(f)
    assert window.image_view.kernel_hint() is not None
    window._on_param_edited("method", "stripes_h")
    assert window.image_view.kernel_hint() is None


def test_no_filtering_means_no_box(window, tmp_path):
    """`denoise` 的 ksize=1 就是原樣回傳 —— 畫一個 1px 的框只會變成正中央一個
    看不懂的點。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lotA5"), n=4, seed=45)
    window.load_dataset_path(out["klarf"], sync=True)
    src = window.model.node_order[0]
    d = wire_up(window.model, window.add_card_after(src, "denoise"))
    window._on_edge_added(src, d, "test")
    window.model.set_param(d, "ksize", 1)
    window.select_node(d)
    assert window.image_view.kernel_hint() is None
    window._on_param_edited("ksize", 5)
    assert window.image_view.kernel_hint()[0] == 5.0


def test_the_view_takes_the_size_in_image_pixels(qapp):
    """框的單位是**影像像素**，所以縮放平移都跟著影像走（同 ROI 框的做法）。"""
    import numpy as np

    view = widgets_mod.ImageView()
    view.resize(200, 200)
    view.set_image(np.zeros((64, 64), np.uint8))
    view.set_kernel_hint(21, "21 px")
    assert view.kernel_hint() == (21.0, "21 px")
    view.zoom_by(2.0)                       # 縮放不改宣告的值
    assert view.kernel_hint() == (21.0, "21 px")
    view.set_kernel_hint(0)                 # 0 / 負數 = 清掉，不是畫一個怪東西
    assert view.kernel_hint() is None


# --------------------------------------------------------------------------- #
# H. 整批的削平走勢
# --------------------------------------------------------------------------- #
def _batch(vals, name="clip_frac"):
    return [{"defect_id": i, "ok": True, "features": {name: v}}
            for i, v in enumerate(vals)]


def _change():
    return {"stream_change": {"test": {"before": [10, 20], "after": [12, 18],
                                       "clipped_low": 0.0, "clipped_high": 0.0,
                                       "was_clipped_low": 0.0,
                                       "was_clipped_high": 0.0}}}


def test_it_says_how_many_other_defects_are_worse(qapp):
    """調參數的人看的是第 1 顆，而出問題的是第 57 顆。"""
    insp = insp_mod.EnhanceInspector()
    vals = [0.0] * 97 + [0.03, 0.05, 0.02]
    insp.set_context("flatten", params={"streams": "test"}, meta=_change(),
                     result={"features": {"clip_frac": 0.0}},
                     batch=_batch(vals))
    assert insp.batch_over_limit() == (3, 100)
    text = insp.summary()
    assert "3 of the 100 defects" in text and "not the worst case" in text


def test_a_clean_batch_says_nothing_extra(qapp):
    """每一顆都好的時候不要多印一行 —— 每次都出現的東西沒有人會讀。"""
    insp = insp_mod.EnhanceInspector()
    insp.set_context("flatten", params={"streams": "test"}, meta=_change(),
                     result={"features": {"clip_frac": 0.0}},
                     batch=_batch([0.0, 0.0001, 0.0]))
    assert insp.batch_over_limit() == (0, 3)
    assert "defects" not in insp.summary()


def test_the_batch_numbers_follow_the_per_stream_feature_name(qapp):
    """兩條流時特徵名帶前綴（F10-3）—— 整批那一版也要跟著，不然它會安靜地空掉。"""
    insp = insp_mod.EnhanceInspector()
    meta = _change()
    meta["stream_change"]["ref"] = dict(meta["stream_change"]["test"])
    insp.set_context("flatten", params={"streams": "test,ref"}, meta=meta,
                     batch=_batch([0.2, 0.0], name="test_clip_frac"))
    assert insp.batch_pushed_out("test") == [0.2, 0.0]
    assert insp.batch_pushed_out("ref") == []


def test_the_strip_only_takes_space_once_there_is_a_batch(qapp):
    """跑過一次 trial 之前它是空的，而一條空的軸線只是雜訊。"""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainter, QPixmap

    insp = insp_mod.EnhanceInspector()
    insp.resize(320, 200)
    pm = QPixmap(320, 200)
    for batch in ([], _batch([0.0, 0.02])):
        insp.set_context("flatten", params={"streams": "test"}, meta=_change(),
                         batch=batch)
        p = QPainter(pm)
        insp.paint_body(p, QRectF(0, 0, 300, 180))   # 不能爆（兩種都要畫得出來）
        p.end()
    assert insp.batch_over_limit() == (1, 2)


def test_the_whole_way_through_from_a_real_trial(window, tmp_path):
    """整條路：引擎跑一批 → trial_results → 面板的整批那一條。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lotH"), n=6, seed=47)
    window.load_dataset_path(out["klarf"], sync=True)
    src = window.model.node_order[0]
    f = wire_up(window.model, window.add_card_after(src, "flatten"))
    window._on_edge_added(src, f, "test")
    window.model.set_param(f, "method", "dark_spots")
    window.model.set_param(f, "size", 9)
    window.select_node(f)
    assert window.run_trial(n=6, sync=True) is True
    assert window.refresh_preview(sync=True) is True

    insp = window.inspector()
    assert isinstance(insp, insp_mod.EnhanceInspector)
    over, total = insp.batch_over_limit("test")
    assert total == 6, "整批的 clip_frac 沒有進 trial_results"
    assert 0 <= over <= 6

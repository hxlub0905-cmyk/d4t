# F11 Enhance-1 驗收：右下角的 Before/after 面板多講兩個數字。
"""兩個「調旋鈕的人現在看不到、但那個旋鈕就是以它為單位」的數字。

1. **雜訊 σ**（Denoise）。``strength`` 的單位就是它 —— 「濾掉幾個 σ 的擾動」。
   在這之前它只活在演算法內部，也就是使用者在調一個以他看不到的數字為單位的
   旋鈕，於是 1.0 在安靜的 lot 與吵的 lot 上是同一個字、不同的意思。
2. **算出值域外、被壓回來的比例**。跟直方圖兩端那根柱子**不是同一件事**：
   柱子是「輸出裡有多少畫素坐在 0 / 255」（原圖本來就有的黑也算在內、而且看得
   見）；這個數字是「這張卡算出了 0–255 以外的值」，而它在圖上**看不見**。

面板讀的是引擎算的那一份（``clip_frac`` 特徵、``ctx.meta['noise_sigma']``），
UI 不自己再量一次 —— 不然畫面上的數字跟真的跑出來的有機會不一樣。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source, wire_up  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import inspectors as insp_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    g.update(QApplication=QApplication, insp_mod=insp_mod,
             studio_mod=studio_mod, theme_mod=theme_mod)


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


def _change(streams=("test",)):
    """引擎那份 before/after 記錄的最小形狀（面板沒有它就整片空白）。"""
    return {"stream_change": {s: {"before": [10, 20], "after": [12, 18],
                                  "clipped_low": 0.0, "clipped_high": 0.0,
                                  "was_clipped_low": 0.0,
                                  "was_clipped_high": 0.0}
                              for s in streams}}


def _result(features):
    return {"features": dict(features)}


# --------------------------------------------------------------------------- #
# 1. σ
# --------------------------------------------------------------------------- #
def test_the_panel_prints_the_noise_sigma_the_engine_measured(qapp):
    insp = insp_mod.EnhanceInspector()
    meta = _change()
    meta["noise_sigma"] = {"test": 6.12}
    insp.set_context("denoise", params={"streams": "test"}, meta=meta)
    assert insp.sigma() == pytest.approx(6.12)
    assert "noise σ ≈ 6.1" in insp.summary()


def test_each_stream_gets_its_own_sigma(qapp):
    """兩條流一起接進來時，σ 是逐流的 —— 印錯一條比不印更糟。"""
    insp = insp_mod.EnhanceInspector()
    meta = _change(("test", "ref"))
    meta["noise_sigma"] = {"test": 9.0, "ref": 0.5}
    insp.set_context("denoise", params={"streams": "test,ref"}, meta=meta)
    assert insp.sigma("ref") == pytest.approx(0.5)
    text = insp.summary()
    assert "“test” " in text and "noise σ ≈ 9.0" in text
    assert "noise σ ≈ 0.5" in text


def test_cards_that_do_not_measure_sigma_do_not_print_a_line(qapp):
    """只有 Denoise 量 σ。其他卡不要憑空生一個 0.0 出來。"""
    insp = insp_mod.EnhanceInspector()
    insp.set_context("tone", params={"streams": "test"}, meta=_change())
    assert insp.sigma() is None
    assert "σ" not in insp.summary()


# --------------------------------------------------------------------------- #
# 2. 被壓回值域的比例
# --------------------------------------------------------------------------- #
def test_it_prints_what_the_card_pushed_out_of_range(qapp):
    insp = insp_mod.EnhanceInspector()
    insp.set_context("flatten", params={"streams": "test"}, meta=_change(),
                     result=_result({"clip_frac": 0.024}))
    assert insp.pushed_out() == pytest.approx(0.024)
    assert "2.4% computed outside 0–255 and clipped back" in insp.summary()


def test_it_reads_the_per_stream_feature_name_when_two_are_connected(qapp):
    """特徵名的前綴規則（F10-3）：兩條以上才加流名。面板要跟引擎同一條規則。"""
    insp = insp_mod.EnhanceInspector()
    insp.set_context("flatten", params={"streams": "test,ref"},
                     meta=_change(("test", "ref")),
                     result=_result({"test_clip_frac": 0.05,
                                     "ref_clip_frac": 0.0}))
    assert insp.pushed_out("test") == pytest.approx(0.05)
    assert insp.pushed_out("ref") == 0.0
    text = insp.summary()
    assert "5.0% computed outside" in text
    assert text.count("computed outside") == 1, "0 的那一條不用講"


def test_nothing_out_of_range_says_nothing(qapp):
    """沒有壓過就不要印一行 0.0% —— 每張卡都印一次的東西沒有人會讀。"""
    insp = insp_mod.EnhanceInspector()
    insp.set_context("flatten", params={"streams": "test"}, meta=_change(),
                     result=_result({"clip_frac": 0.0}))
    assert "computed outside" not in insp.summary()


def test_the_two_numbers_are_not_the_same_number(qapp):
    """直方圖的削平與「算出界外」是兩件事，所以兩句話要能同時出現。"""
    insp = insp_mod.EnhanceInspector()
    meta = _change()
    meta["stream_change"]["test"].update(clipped_low=0.3, clipped_high=0.0)
    insp.set_context("flatten", params={"streams": "test"}, meta=meta,
                     result=_result({"clip_frac": 0.02}))
    text = insp.summary()
    assert "30.0% at black" in text and "2.0% computed outside" in text


# --------------------------------------------------------------------------- #
# 2b. 換掉了幾顆壞點（F11 Enhance-2）
# --------------------------------------------------------------------------- #
def test_it_prints_how_many_pixels_were_replaced_as_damage(qapp):
    """調 threshold 時這是唯一看得到的回饋 —— 影像上只是少了幾顆亮點。"""
    insp = insp_mod.EnhanceInspector()
    insp.set_context("denoise", params={"streams": "test",
                                        "method": "hot_pixels"},
                     meta=_change(), result=_result({"hot_px_frac": 0.0013}))
    assert insp.replaced() == pytest.approx(0.0013)
    assert "0.13% replaced as hot/dead pixels" in insp.summary()


def test_zero_replaced_is_still_worth_printing(qapp):
    """0 在這裡**是**訊息（「這張卡什麼都沒做，門檻可能太高」），
    跟 clip_frac 的 0 不一樣（那個是「一切正常」）。"""
    insp = insp_mod.EnhanceInspector()
    insp.set_context("denoise", params={"streams": "test",
                                        "method": "hot_pixels"},
                     meta=_change(), result=_result({"hot_px_frac": 0.0}))
    assert "0.00% replaced" in insp.summary()


def test_the_other_denoise_methods_do_not_print_that_line(qapp):
    """median 動的是每一個畫素 —— 「換掉的比例」對它恆等於 1，印出來沒有意義。"""
    insp = insp_mod.EnhanceInspector()
    insp.set_context("denoise", params={"streams": "test", "method": "median"},
                     meta=_change(), result=_result({"clip_frac": 0.0}))
    assert insp.replaced() is None
    assert "replaced" not in insp.summary()


# --------------------------------------------------------------------------- #
# 2c. 磨掉的是雜訊還是訊號（F11 Enhance-UI-E）
# --------------------------------------------------------------------------- #
def test_it_prints_how_much_the_filter_removed_in_units_of_noise(qapp):
    """≈1 = 磨掉的就是雜訊；≫1 = 連結構一起磨掉了。**兩種在單顆畫面上都
    「看起來乾淨了」**，那正是它需要一個數字的理由。"""
    insp = insp_mod.EnhanceInspector()
    insp.set_context("denoise", params={"streams": "test", "method": "median"},
                     meta=_change(),
                     result=_result({"removed_over_noise": 0.93}))
    assert insp.removed_over_noise() == pytest.approx(0.93)
    assert "removed 0.9× the noise" in insp.summary()


def test_hot_pixels_prints_the_other_number(qapp):
    """兩種方法問的是不同的問題，所以面板上也是兩句不同的話。"""
    insp = insp_mod.EnhanceInspector()
    insp.set_context("denoise", params={"streams": "test",
                                        "method": "hot_pixels"},
                     meta=_change(), result=_result({"hot_px_frac": 0.001}))
    assert insp.removed_over_noise() is None
    assert "the noise" not in insp.summary()


# --------------------------------------------------------------------------- #
# 2d. 兩條流還有多像（F11 Enhance-UI-B）
# --------------------------------------------------------------------------- #
def test_it_says_whether_the_two_streams_are_comparable_now(qapp):
    """面板本來並排畫兩條直方圖，但**沒有一個數字說它們有多像**。"""
    insp = insp_mod.EnhanceInspector()
    meta = _change(("test", "ref"))
    insp.set_context("normalize", params={"streams": "test,ref"}, meta=meta,
                     result=_result({"pair_level_delta": 0.8,
                                     "pair_spread_ratio": 1.04}))
    assert insp.pair() == (0.8, 1.04)
    text = insp.summary()
    assert "“test” vs “ref” now: 0.8 gray levels apart, spread 1.04×" in text
    assert "not comparable" not in text


def test_a_gap_that_will_look_like_a_defect_is_called_out(qapp):
    insp = insp_mod.EnhanceInspector()
    meta = _change(("test", "ref"))
    insp.set_context("normalize", params={"streams": "test,ref"}, meta=meta,
                     result=_result({"pair_level_delta": 42.0,
                                     "pair_spread_ratio": 2.9}))
    text = insp.summary()
    assert "still not comparable" in text and "as if it were a defect" in text


def test_one_stream_has_no_pair_to_talk_about(qapp):
    insp = insp_mod.EnhanceInspector()
    insp.set_context("normalize", params={"streams": "test"}, meta=_change(),
                     result=_result({"clip_frac": 0.0}))
    assert insp.pair() is None
    assert "vs" not in insp.summary()


# --------------------------------------------------------------------------- #
# 3. 整條路：引擎 → meta / features → 面板
# --------------------------------------------------------------------------- #
def test_the_whole_way_through_from_a_real_preview(window, tmp_path):
    """**這一支是重點**：兩個字串（``clip_frac`` / ``noise_sigma``）在引擎與 UI
    兩邊各寫了一次，而寫錯的那一半是安靜的（面板就只是不印那一行）。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lotN"), n=4, seed=31)
    window.load_dataset_path(out["klarf"], sync=True)
    src = first_source(window)
    d = wire_up(window.model, window.add_card_after(src, "denoise"))
    window._on_edge_added(src, d, "test")
    window.model.set_param(d, "method", "bilateral")
    window.model.set_param(d, "ksize", 5)
    window.select_node(d)
    assert window.refresh_preview(sync=True) is True

    insp = window.inspector()
    assert isinstance(insp, insp_mod.EnhanceInspector)
    sigma = insp.sigma("test")
    assert sigma is not None and sigma > 0.0, "引擎量了 σ，面板要拿得到"
    assert "noise σ ≈" in window.inspector_summary.text()
    # clip_frac 一定有值（跑得動就有），只是這張卡通常是 0 —— 拿得到才是重點。
    assert insp.pushed_out("test") is not None

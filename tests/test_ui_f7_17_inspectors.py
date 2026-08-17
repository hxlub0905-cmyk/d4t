# F7-17 驗收：右下角是**這張卡自己的儀表**。
"""原本那塊固定是一張「特徵 / 數值」表。問題不是它佔位子，是那些數字**沒有辦法
判讀** —— `blob_dist_center 11.170` 是大還是小？而且使用者在問的問題每張卡都
不一樣：調 Align 時他要知道「搜尋半徑夠不夠」，調 Denoise 時他要知道「我有沒有
把訊號一起磨掉」。

這一支測兩件事：**機制**（換卡片就換儀表、沒註冊的卡不會變成一片空白）與
**每個儀表回答的那個問題**。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import wire_up  # noqa: E402  —— F10：加完卡要接線

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import inspectors as insp_mod
    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
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


def _batch(points, extra=None):
    """把 (dx, dy) 清單做成 trial_results 的形狀。"""
    out = []
    for i, (dx, dy) in enumerate(points):
        feats = {"align_dx": float(dx), "align_dy": float(dy)}
        feats.update(extra or {})
        out.append({"defect_id": i, "ok": True, "score": 0.0, "features": feats})
    return out


# --------------------------------------------------------------------------- #
# 1. 機制
# --------------------------------------------------------------------------- #
def test_selecting_a_card_swaps_in_its_own_panel(window):
    src = window.model.node_order[0]
    a = window.add_card_after(src, "align")
    # F10：Align 有**兩格**輸入（要對的那張、對齊到哪張），所以要拉兩條線 ——
    # 那正是使用者現在在畫布上做的事（以前一條都不用拉也照跑，因為兩格都有
    # 預設值）。
    window._on_edge_added(src, a, "ref", "moving")
    window._on_edge_added(src, a, "test", "fixed")
    assert isinstance(window.inspector(), insp_mod.AlignInspector)
    assert window.bottom_page() == 0
    assert window.btn_tab_card.text() == "Alignment"


def test_a_card_without_a_panel_falls_back_to_the_feature_table(window):
    """沒註冊儀表的卡**不能**變成一片空白 —— 那比原本的特徵表還糟。"""
    src = window.model.node_order[0]
    a = window.add_card_after(src, "align")
    # F10：Align 有**兩格**輸入（要對的那張、對齊到哪張），所以要拉兩條線 ——
    # 那正是使用者現在在畫布上做的事（以前一條都不用拉也照跑，因為兩格都有
    # 預設值）。
    window._on_edge_added(src, a, "ref", "moving")
    window._on_edge_added(src, a, "test", "fixed")
    window.add_card_after(a, "subtract")        # subtract 還沒有自己的儀表
    assert window.inspector() is None
    assert window.bottom_page() == 1
    assert window.btn_tab_card.isEnabled() is False


def test_you_can_still_get_to_the_features(window):
    src = window.model.node_order[0]
    _nid = window.add_card_after(src, "align")
    window._on_edge_added(src, _nid, "test")
    window.show_bottom_page(1)
    assert window.bottom_page() == 1
    window.show_bottom_page(0)
    assert window.bottom_page() == 0


def test_adding_a_new_card_does_not_need_this_module_touched():
    """約定 1：沒登記的卡就沒有儀表，不是壞掉。"""
    assert insp_mod.inspector_for("subtract") is None
    assert insp_mod.inspector_for("subtract") is None
    assert insp_mod.inspector_for("") is None
    assert insp_mod.inspector_for("align") is insp_mod.AlignInspector


def test_an_empty_panel_says_why_it_is_empty(qapp):
    """空白面板本身不是訊息。最常見的原因是「還沒跑過」。"""
    insp = insp_mod.AlignInspector()
    insp.set_context("align", params={"search_radius": 8})
    assert insp.has_data() is False
    assert "Run a trial" in insp.empty_reason()
    assert insp.summary() == ""


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_panel_paints_in_both_themes(qapp, theme_name):
    from PySide6.QtGui import QColor, QPixmap

    theme_mod.apply_theme(qapp, theme_name)
    insp = insp_mod.AlignInspector()
    insp.resize(260, 200)
    for batch in ([], _batch([(1.0, -2.0), (7.9, 0.5)])):
        insp.set_context("align", params={"search_radius": 8},
                         result={"features": {"align_dx": 1.0, "align_dy": -2.0}},
                         batch=batch)
        pm = QPixmap(insp.size())
        pm.fill(QColor("#ffffff"))
        insp.render(pm)                    # 例外會在這裡冒出來
        assert not pm.isNull()
    theme_mod.apply_theme(qapp, "light")


# --------------------------------------------------------------------------- #
# 2. Align：搜尋半徑夠不夠大
# --------------------------------------------------------------------------- #
def test_it_counts_the_defects_that_ran_out_of_room(qapp):
    """對位失敗在單顆上看不出來 —— 演算法一定會回一個位移，而 8 是一個看起來
    完全正常的數字。真正的訊號是「位移**貼在搜尋框的邊上**」。"""
    insp = insp_mod.AlignInspector()
    pts = [(0.5, 0.2), (-1.0, 2.0), (8.0, 1.0), (-8.0, -3.0), (2.0, 7.95)]
    insp.set_context("align", params={"search_radius": 8}, batch=_batch(pts))
    assert insp.has_data() is True
    assert insp.at_the_limit() == 3


def test_the_warning_says_what_to_do_about_it(qapp):
    insp = insp_mod.AlignInspector()
    insp.set_context("align", params={"search_radius": 8},
                     batch=_batch([(8.0, 0.0), (0.1, 0.2)]))
    text = insp.summary()
    assert "1 of them sit on the search limit" in text
    assert "Search radius" in text, "要講得出下一步是什麼"


def test_a_healthy_batch_does_not_cry_wolf(qapp):
    insp = insp_mod.AlignInspector()
    insp.set_context("align", params={"search_radius": 8},
                     batch=_batch([(0.4, -0.2), (1.1, 0.9), (-2.0, 1.5)]))
    assert insp.at_the_limit() == 0
    assert "⚠" not in insp.summary()
    assert "3 defects" in insp.summary()


def test_sub_pixel_shifts_still_count_as_at_the_limit(qapp):
    """次像素對位會回 7.9 這種值 —— 用嚴格相等比對會一顆都抓不到，
    而那正是最需要被抓到的情況。"""
    insp = insp_mod.AlignInspector()
    insp.set_context("align", params={"search_radius": 8},
                     batch=_batch([(7.94, 0.0)]))
    assert insp.at_the_limit() == 1


def test_broken_values_do_not_break_the_panel(qapp):
    """單顆失敗不會殺整批（引擎的契約），所以這裡一定會遇到缺值。"""
    insp = insp_mod.AlignInspector()
    batch = _batch([(1.0, 1.0)])
    batch.append({"defect_id": 9, "ok": False, "features": {}})
    batch.append({"defect_id": 10, "ok": True,
                  "features": {"align_dx": float("nan"), "align_dy": 1.0}})
    insp.set_context("align", params={"search_radius": 4}, batch=batch)
    assert insp.points() == [(1.0, 1.0)]


def test_it_reads_the_engine_numbers_not_its_own(window, tmp_path):
    """整條路跑一次：引擎算的 align_dx/dy → trial_results → 儀表。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lot"), n=8, seed=17)
    window.load_dataset_path(out["klarf"], sync=True)
    src = window.model.node_order[0]
    a = window.add_card_after(src, "align")
    # F10：Align 有**兩格**輸入（要對的那張、對齊到哪張），所以要拉兩條線 ——
    # 那正是使用者現在在畫布上做的事（以前一條都不用拉也照跑，因為兩格都有
    # 預設值）。
    window._on_edge_added(src, a, "ref", "moving")
    window._on_edge_added(src, a, "test", "fixed")
    window.model.set_param(a, "search_radius", 6)
    assert window.run_trial(n=8, sync=True) is True
    window.select_node(a)

    insp = window.inspector()
    assert len(insp.points()) == 8
    assert insp.radius() == 6.0
    first = window.trial_results[0]["features"]
    assert insp.points()[0] == (first["align_dx"], first["align_dy"])
    assert "8 defects" in window.inspector_summary.text()


# --------------------------------------------------------------------------- #
# 3. Enhance：我把資訊弄掉了嗎
# --------------------------------------------------------------------------- #
def _change(before, after, was_lo=0.0, was_hi=0.0, lo=0.0, hi=0.0):
    return {"stream_change": {"test": {
        "before": before, "after": after,
        "clipped_low": lo, "clipped_high": hi,
        "was_clipped_low": was_lo, "was_clipped_high": was_hi}}}


def test_the_enhance_panel_needs_the_engine_record(qapp):
    insp = insp_mod.EnhanceInspector()
    insp.set_context("tone", params={"streams": "test"})
    assert insp.has_data() is False
    assert "“test”" in insp.empty_reason()


def test_it_reports_how_much_the_card_flattened(qapp):
    """削平是 Enhance 唯一會安靜毀掉資訊的方式：那些畫素之間的差異回不來了。"""
    insp = insp_mod.EnhanceInspector()
    insp.set_context("tone", params={"streams": "test"},
                     meta=_change([10, 20, 10], [40, 0, 40],
                                  was_lo=0.0, was_hi=0.0, lo=0.30, hi=0.12))
    assert insp.has_data() is True
    assert insp.clipped() == (0.30, 0.12)
    assert insp.added_clipping() == (0.30, 0.12)
    text = insp.summary()
    assert "30.0% at black" in text and "“test”" in text
    assert "⚠" in text and "measure card downstream" in text


def test_it_does_not_blame_this_card_for_pre_existing_black(qapp):
    """原圖本來就有一片全黑（缺陷本身、或上一張卡幹的）—— 那不是這張卡的帳，
    而每次都喊狼來了跟不喊一樣沒有用。"""
    insp = insp_mod.EnhanceInspector()
    insp.set_context("denoise", params={"streams": "test"},
                     meta=_change([5, 5], [5, 5], was_lo=0.22, lo=0.22))
    assert insp.clipped()[0] == 0.22
    assert insp.added_clipping() == (0.0, 0.0)
    assert "⚠" not in insp.summary()


def test_it_follows_the_stream_the_card_works_on(qapp):
    """一張只做在 ref 上的卡，要比的是 ref 的 before/after，不是 test 的。"""
    insp = insp_mod.EnhanceInspector()
    meta = _change([1, 2], [3, 4])
    meta["stream_change"]["ref"] = {"before": [9], "after": [8],
                                    "clipped_low": 0.5, "clipped_high": 0.0,
                                    "was_clipped_low": 0.0,
                                    "was_clipped_high": 0.0}
    insp.set_context("denoise", params={"streams": "ref"}, meta=meta)
    assert insp.stream() == "ref"
    assert insp.clipped()[0] == 0.5

    # 兩條流的卡：目前畫得出第一條（計畫書 §23.7）—— 重點是它**不會退回 test**
    insp.set_context("denoise", params={"streams": "ref,test"}, meta=meta)
    assert insp.stream() == "ref"


def test_the_engine_only_records_when_asked(qapp, tmp_path):
    """批次跑一萬顆時每次 set_image 都算兩個直方圖是白花的力氣。"""
    from adept.core.pipeline.context import Context
    import numpy as np

    ctx = Context()
    ctx.set_image("test", np.zeros((4, 4), np.uint8))
    ctx.set_image("test", np.full((4, 4), 255, np.uint8))
    assert "stream_change" not in ctx.meta

    ctx2 = Context()
    ctx2.track_changes = True
    ctx2.set_image("test", np.zeros((4, 4), np.uint8))
    assert "stream_change" not in ctx2.meta, "第一次寫入不是「改」，是「產生」"
    ctx2.set_image("test", np.full((4, 4), 255, np.uint8))
    rec = ctx2.meta["stream_change"]["test"]
    assert rec["was_clipped_low"] == 1.0 and rec["clipped_high"] == 1.0


def test_the_studio_preview_turns_recording_on(window, tmp_path):
    """整條路：預覽 → ctx.meta → 儀表。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lotE"), n=4, seed=23)
    window.load_dataset_path(out["klarf"], sync=True)
    src = window.model.node_order[0]
    b = window.add_card_after(src, "tone")
    window._on_edge_added(src, b, "test")
    window.model.set_param(b, "contrast", 4.0)
    window.select_node(b)
    assert window.refresh_preview(sync=True) is True

    insp = window.inspector()
    assert isinstance(insp, insp_mod.EnhanceInspector)
    assert insp.has_data() is True
    assert insp.added_clipping()[0] > 0.05, "對比拉到 4 倍一定會壓黑一大片"
    assert "⚠" in window.inspector_summary.text()


# --------------------------------------------------------------------------- #
# 4. Measure：這張卡量出來的東西分不分得開
# --------------------------------------------------------------------------- #
def _feats(values):
    return [{"defect_id": i, "ok": True, "features": dict(f)}
            for i, f in enumerate(values)]


def test_it_only_shows_this_cards_own_numbers(qapp):
    """整份 feature 表是 ADC 的事。調這張卡的時候要看的是**這張卡**的產出。"""
    insp = insp_mod.MeasureInspector()
    batch = _feats([{"glv_mean": 10.0 + i, "blob_area": 3.0} for i in range(6)])
    insp.set_context("glv_stats", batch=batch, feature_names=["glv_mean"])
    assert insp.rows() == ["glv_mean"]


def test_it_calls_out_a_feature_that_separates_nothing(qapp):
    """整批擠成一根柱子 = 門檻設哪裡都一樣。那是使用者最需要知道的事。"""
    insp = insp_mod.MeasureInspector()
    batch = _feats([{"flat": 5.0, "spread": float(i)} for i in range(20)])
    insp.set_context("glv_stats", batch=batch,
                     feature_names=["flat", "spread"])
    assert insp._is_flat("flat") is True
    assert insp._is_flat("spread") is False
    assert "flat barely varies" in insp.summary()


def test_it_says_where_this_defect_sits(qapp):
    insp = insp_mod.MeasureInspector()
    batch = _feats([{"m": float(i)} for i in range(100)])
    insp.set_context("glv_stats", result={"features": {"m": 97.0}},
                     batch=batch, feature_names=["m"])
    assert insp.percentile_of("m") == 97.0
    assert "top 5%" in insp.summary()


def test_a_value_outside_the_batch_range_does_not_draw_off_the_chart(qapp):
    """改了參數之後預覽會立刻重算，而整批還是上一次跑的 —— 這是正常狀態，
    不是錯誤。把線畫到圖外會蓋到旁邊的文字。"""
    from PySide6.QtGui import QColor, QPixmap

    insp = insp_mod.MeasureInspector()
    insp.resize(320, 120)
    batch = _feats([{"m": float(i)} for i in range(10)])
    insp.set_context("glv_stats", result={"features": {"m": -500.0}},
                     batch=batch, feature_names=["m"])
    pm = QPixmap(insp.size())
    pm.fill(QColor("#ffffff"))
    insp.render(pm)                    # 這裡以前會 segfault（drawPolygon overload）
    assert not pm.isNull()


# --------------------------------------------------------------------------- #
# 5. Input：哪一頁變成哪一條流
# --------------------------------------------------------------------------- #
def test_the_page_to_stream_mapping_is_on_screen(window, tmp_path):
    """這是全專案第一條待廠內驗證的假設（docs/FAB-VALIDATION.md）。錯了的話 diff 會整個
    反號，而畫面上完全看不出來 —— 兩張圖本來就長得很像。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lotF"), n=4, seed=29)
    window.load_dataset_path(out["klarf"], sync=True)
    window.select_node(window.model.node_order[0])
    assert window.refresh_preview(sync=True) is True

    insp = window.inspector()
    assert isinstance(insp, insp_mod.InputInspector)
    pages = insp.pages()
    assert [d["channel"] for d in pages] == ["test", "ref"]
    assert [d["page"] for d in pages] == [0, 1]
    assert all(d["shape"] == [128, 128] for d in pages)
    assert all(d["mean"] is not None for d in pages)


def test_it_says_measurements_are_in_pixels(window, tmp_path):
    """nm/px 沒有來源，而 2026-07-30 的決定是**不去猜**：量測全程 pixel，
    換算搬到 Export（使用者自己填 nm/px）。

    所以這一行要講的不是「有個值不見了」，而是**單位是什麼、要換算去哪裡填**。
    以前它說「CD in nm will read 0」—— 那個 0 已經不存在了。
    """
    from make_sample import generate

    out = generate(str(tmp_path / "lotG"), n=2, seed=31)
    window.load_dataset_path(out["klarf"], sync=True)
    window.select_node(window.model.node_order[0])
    window.refresh_preview(sync=True)
    summary = window.inspector().summary()
    assert "pixels" in summary and "export" in summary
    assert "will read 0" not in summary


# --------------------------------------------------------------------------- #
# 6. roi_profile：曲線面板收進同一個機制
# --------------------------------------------------------------------------- #

def test_the_old_name_still_answers_when_another_card_is_selected(window):
    """`profile_panel` 在別的卡片上要回一個**空的替身**，不是 None ——
    呼叫端不必到處寫 if is None。"""
    window.select_node(window.model.node_order[0])
    assert window.profile_panel is not None
    assert window.profile_panel.has_data() is False
    assert window.profile_panel_visible() is False


# --------------------------------------------------------------------------- #
# 7. roi_template：定位失敗有三個完全不同的原因
# --------------------------------------------------------------------------- #
def _match(score=0.9, margin=0.4, structure=30.0, ok=True):
    return {"templates": {"cell": {
        "cell_w": 40, "cell_h": 240, "phase_x": 7, "phase_y": 0,
        "score": score, "margin": margin, "structure": structure,
        "ok": ok, "norm": [0.0, 0.0, 1.0, 1.0], "axis": "x"}}}


_TPL_PARAMS = {"roi_out": "cell", "min_score": 0.3, "min_margin": 0.05,
               "min_structure": 5.0, "template": "gc1:xxx"}


def test_it_names_which_gate_failed(qapp):
    """三個原因的**處置完全不同**，分不出來的話使用者會一直去調錯的門檻。"""
    insp = insp_mod.TemplateInspector()

    insp.set_context("roi_template", params=_TPL_PARAMS,
                     meta=_match(score=0.1, ok=False))
    assert insp.failing() == ["match"]
    assert "does not look like the template" in insp.summary()

    insp.set_context("roi_template", params=_TPL_PARAMS,
                     meta=_match(margin=0.01, ok=False))
    assert insp.failing() == ["certainty"]
    assert "more than one position fits" in insp.summary()


def test_no_structure_is_not_a_setting_to_fix(qapp):
    """整張 patch 都在同一種材質裡 —— 那不是參數問題，退回整張圖就是對的答案。
    不講清楚的話使用者會去把門檻一路調低，直到它開始亂放框。"""
    insp = insp_mod.TemplateInspector()
    insp.set_context("roi_template", params=_TPL_PARAMS,
                     meta=_match(structure=1.0, ok=False))
    assert insp.failing() == ["structure"]
    text = insp.summary()
    assert "nothing to match" in text
    assert "not a setting to fix" in text


def test_a_good_match_says_where_it_landed(qapp):
    insp = insp_mod.TemplateInspector()
    insp.set_context("roi_template", params=_TPL_PARAMS, meta=_match())
    assert insp.failing() == []
    assert "matched at phase 7,0" in insp.summary()


def test_it_says_to_build_a_template_first(qapp):
    insp = insp_mod.TemplateInspector()
    insp.set_context("roi_template", params={"roi_out": "cell", "template": ""})
    assert insp.has_data() is False
    assert "No template yet" in insp.empty_reason()


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_the_gate_bars_paint(qapp, theme_name):
    from PySide6.QtGui import QColor, QPixmap

    theme_mod.apply_theme(qapp, theme_name)
    insp = insp_mod.TemplateInspector()
    insp.resize(320, 160)
    insp.set_context("roi_template", params=_TPL_PARAMS,
                     meta=_match(score=0.1, ok=False))
    pm = QPixmap(insp.size())
    pm.fill(QColor("#ffffff"))
    insp.render(pm)
    assert not pm.isNull()
    theme_mod.apply_theme(qapp, "light")


def test_it_reads_the_engine_verdict_end_to_end(window, tmp_path):
    """整條路：卡片跑完把三個數字放進 ctx.meta['templates'] → 儀表。"""
    import numpy as np

    from adept.core.algo import template as at
    from make_sample import generate

    out = generate(str(tmp_path / "lotT"), n=4, seed=61)
    window.load_dataset_path(out["klarf"], sync=True)
    nid = wire_up(window.model, window.model.add_step("roi_template"))
    window.select_node(nid)

    img = np.zeros((240, 320), np.float32)
    for k in range(8):
        x = k * 40
        img[:, x:x + 40] = 120.0
        img[:, x + 14:x + 34] = 60.0
        img[:, x + 12:x + 16] = 210.0
        img[:, x + 32:x + 36] = 210.0
    img += np.random.default_rng(0).normal(0, 4, img.shape).astype(np.float32)
    window._apply_template(nid, at.encode_cell(at.build_golden_cell(img).cell),
                           "x")
    assert window.refresh_preview(sync=True) is True

    insp = window.inspector()
    assert isinstance(insp, insp_mod.TemplateInspector)
    assert insp.has_data() is True
    names = [g[0] for g in insp.gates()]
    assert names == ["match", "certainty", "structure"]
    assert window.inspector_summary.text() != ""

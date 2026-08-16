# F7-5 驗收：Results 視窗 —— 跑完才有意義的東西不該常駐在編輯畫面上。
"""主視窗只留「編流程 + 看單顆」；分數分佈、Gallery、輸出搬到 Results 視窗。

最重要的一條是最後那個測試：**搬家不可以弄丟秒回**。拖門檻線走的是
``viewmodel.rebin()`` 的純計算路徑（不重跑影像），這是這個工具調參迴圈的
一半價值，換視窗時最容易不小心接成「每動一次就重跑」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "recipes" \
    / "die_to_die_basic.json"


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from adept.ui import results as results_mod
    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    from adept.ui import viewmodel as vm_mod
    g.update(QApplication=QApplication, results_mod=results_mod,
             studio_mod=studio_mod, theme_mod=theme_mod, vm_mod=vm_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("f7_results")), n=8, seed=7)


@pytest.fixture(scope="module")
def window(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.load_dataset_path(lot["klarf"], sync=True)
    win.load_recipe_path(str(EXAMPLE), sync=True)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 主視窗乾淨了
# --------------------------------------------------------------------------- #
def test_main_window_keeps_only_the_editing_surface(window):
    root = window.root_splitter
    assert [root.widget(i) for i in range(root.count())] == [
        window.library, window.canvas_column, window.preview_pane]
    assert window.histogram.parent() is not window
    assert window.gallery.parent() is not window


def test_preview_gets_the_widest_column(window):
    """使用者要求「影像大一點」—— 單顆預覽要拿到最寬的一欄。

    看的是**設定值**而不是 ``sizes()``：QSplitter 要視窗真的 show 過才會排版，
    離屏測試裡 ``sizes()`` 只會回一組沒有意義的相等數字。
    """
    lib, mid, preview = studio_mod.COLUMN_SIZES
    assert preview == max(studio_mod.COLUMN_SIZES)
    assert preview > lib + mid * 0.5, studio_mod.COLUMN_SIZES
    assert window.root_splitter.count() == 3


def test_results_window_is_not_shown_until_there_is_something_to_show(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.results_visible() is False
        assert win.results.summary_text() == "No results yet."
        assert win.results.btn_export.isEnabled() is False
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# 2. 跑完就把結果端出來
# --------------------------------------------------------------------------- #
def test_running_populates_and_presents_the_results_window(window):
    assert window.run_trial(8, workers=1, sync=True) is True

    assert window.results_visible() is True, "按 Run 想看的就是這個"
    assert window.histogram.has_data() is True
    assert window.gallery.displayed_count() == 8
    assert window.results.btn_export.isEnabled() is True

    summary = window.results.summary_text()
    assert "8 defects" in summary and "8 ok" in summary and "0 failed" in summary


def test_summary_line_reports_counts_and_score_span():
    text = results_mod.summarize_run(10, 9, 1.25, [3.0, 7.5, 1.0])
    assert "10 defects" in text and "9 ok" in text and "1 failed" in text
    assert "1.25 s" in text or "1.2 s" in text
    assert "1 – 7.5" in text

    assert "score" not in results_mod.summarize_run(2, 2, 0.1, [])


def test_export_button_in_results_reaches_the_studio_dialog(window):
    window.run_trial(8, workers=1, sync=True)
    seen = []
    window.results.export_requested.connect(lambda: seen.append(True))
    window.results.btn_export.click()
    assert seen, "Results 視窗的輸出鈕要接回 Studio 的輸出精靈"


# --------------------------------------------------------------------------- #
# 3. **搬家不可以弄丟秒回**
# --------------------------------------------------------------------------- #
def test_threshold_drag_is_still_the_pure_rescore_path(window):
    """拖曳中只重算 bin 數（不寫 model、不重跑影像），放開才 commit。"""
    window.run_trial(8, workers=1, sync=True)
    window._on_threshold_committed(40.0)
    before = window.model.threshold

    window._on_threshold_changed(77.25)
    assert window.model.threshold == pytest.approx(before), \
        "拖曳中絕對不可以動到 model —— 那會觸發重跑"
    live = window.histogram.bin_summary_text()
    # 前綴比對：合成資料旁邊有 ground_truth.json，同一行後面還會接一段準確率
    # （Phase 1）。這一條要驗的是 bin 數跟著門檻走，不是那一行長什麼樣子。
    assert live.startswith("   ".join(
        "bin %s=%s" % (k, v)
        for k, v in sorted(vm_mod.rebin(window.trial_scores, 77.25,
                                        window.model.bins).items())))

    window._on_threshold_committed(55.0)
    assert window.model.threshold == pytest.approx(55.0)


def test_bar_click_filters_the_gallery_in_the_same_window(window):
    window.run_trial(8, workers=1, sync=True)
    lo, hi = window.histogram.bar_range(0)
    window.histogram.bar_clicked.emit(lo, hi)

    assert window.gallery.filter_text(), "點長條要篩 Gallery"
    assert window.results_visible() is True
    # 再點同一根 = 取消
    window.histogram.bar_clicked.emit(lo, hi)
    assert window.gallery.filter_text() == ""


def test_closing_results_does_not_lose_them(window):
    window.run_trial(8, workers=1, sync=True)
    window.results.close()
    assert window.results_visible() is False
    assert window.trial_results, "關掉視窗不該丟掉結果"

    window.show_gallery()
    assert window.results_visible() is True
    assert window.gallery.displayed_count() == 8

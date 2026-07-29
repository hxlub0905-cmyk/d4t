# ADEPT Studio 主視窗煙霧測試 — authored 2026-07-28 (M3 收尾).
"""``adept/ui/studio.py`` 的離屏（offscreen）煙霧測試。

執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_studio_smoke.py -q``

**為什麼所有 Qt import 都是 lazy 的（別改回去）**

``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有任何
PySide6 模組。pytest 先蒐集全部測試檔、再開始跑，所以只要這個檔案在**模組層**
``import PySide6``（或 import ``adept.ui.studio``），蒐集階段就會把 Qt 塞進
``sys.modules``，那個守門測試就會紅 —— 即使它先跑。

因此：所有 Qt / ``adept.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
每個測試都必須（直接或間接）要求 ``qapp`` fixture，否則那些名字不存在。

測試一律走 ``StudioWindow`` 的公開 API（``load_dataset_path`` / ``select_node`` /
``run_trial`` …）或直接 emit 元件的訊號，**不開任何對話框**、不依賴 event loop
（背景 worker 全部走 ``sync=True`` 的同步路徑）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_RECIPE = REPO / "examples" / "recipes" / "die_to_die_basic.json"

sys.path.insert(0, str(REPO / "tools"))
from make_sample import generate  # noqa: E402


def _load_qt() -> None:
    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
    from PySide6.QtWidgets import QApplication  # noqa: F401

    from adept.ui import studio as studio_mod  # noqa: F401
    from adept.ui import theme as theme_mod  # noqa: F401
    from adept.ui import viewmodel as vm_mod  # noqa: F401

    from adept.core.pipeline import Recipe  # noqa: F401

    globals().update(locals())


@pytest.fixture(scope="module")
def qapp():
    """離屏 QApplication（整個模組共用一個）+ 套用主題。"""
    _load_qt()
    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
    theme_mod.apply_theme(app)
    yield app
    app.processEvents()


@pytest.fixture(scope="module")
def synlot(tmp_path_factory):
    """合成 lot（8 顆 defect，seed=7）—— 與 M1 端到端測試同一支產生器。"""
    out = tmp_path_factory.mktemp("studio_lot")
    return generate(str(out), n=8, seed=7)


@pytest.fixture(scope="module")
def window(qapp):
    """整個模組共用一個主視窗（最後一個測試才把它關掉）。"""
    win = studio_mod.StudioWindow()
    yield win
    win.close()


def _loaded(window, synlot):
    """把資料集 + 範例 recipe 灌進視窗（冪等，讓每個測試都能單獨跑）。"""
    if window.dataset is None:
        assert window.load_dataset_path(synlot["klarf"], sync=True) is True
    if not window.model.node_order:
        assert window.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
    return window


# --------------------------------------------------------------------------- #
# 1. 建構 + 卡片庫
# --------------------------------------------------------------------------- #
def test_window_constructs_with_library_cards(window):
    assert window.windowTitle().startswith("ADEPT Studio")
    # 卡片庫用的是真實 registry，不是手捏假資料
    assert window.library.entry("snr_map") is not None
    assert window.library.entry("load_patch") is not None
    assert window.library.section_titles() == [
        "Input", "Enhance", "Region", "Compare", "Measure", "ADC"]

    # 空狀態：流程沒有節點、預覽沒有影像、直方圖沒有資料
    assert window.model.node_order == []
    assert window.pipeline.node_ids() == []
    assert window.image_view.has_image() is False
    assert window.histogram.has_data() is False
    assert window.status_text()          # 一開始就給使用者一句提示

    # 工具列：試跑筆數 10–5000 預設 200，主要動作按鈕掛 objectName "primary"
    assert (window.spin_trial_n.minimum(), window.spin_trial_n.maximum()) == (10, 5000)
    assert window.spin_trial_n.value() == 200
    assert window.btn_trial.objectName() == "primary"


# --------------------------------------------------------------------------- #
# 2. 載入資料集 + recipe
# --------------------------------------------------------------------------- #
def test_load_dataset_and_recipe(window, synlot):
    _loaded(window, synlot)

    assert window.dataset is not None
    assert len(window.dataset.items) == 8
    assert window.defect_combo.count() == 8
    assert window.defect_index == 0
    assert "8" in window.defect_label.text()

    recipe = Recipe.load(str(EXAMPLE_RECIPE))
    assert window.model.node_order == recipe.routes["ebi_patch"]
    assert len(window.pipeline.node_ids()) == len(window.model.node_order)
    assert window.pipeline.node_ids() == window.model.node_order
    assert window.model.kind == "ebi_patch"

    # 標題帶 recipe id，狀態列有講人話
    assert "die_to_die_basic" in window.windowTitle()
    assert window.status_text()
    # Score/Bin 尾卡摘要跟著 model 走
    summary = window.pipeline.score_summary_text()
    assert recipe.score.expr in summary and "50" in summary
    # 節點摘要 = 非預設參數的 k=v（最多 3 個）—— F7-6 起節點是自繪圖元
    assert "window=15" in window.pipeline.card("snr").info["summary"]


# --------------------------------------------------------------------------- #
# 3. 選節點 + 預覽
# --------------------------------------------------------------------------- #
def test_select_node_and_preview(window, synlot):
    _loaded(window, synlot)

    assert window.select_node("snr") is True
    assert window.selected_node == "snr"
    assert window.pipeline.selected() == "snr"
    assert window.stack.currentWidget() is window.param_form
    assert window.param_form.step_key() == "snr_map"

    assert window.refresh_preview(sync=True) is True
    assert window.image_view.has_image() is True

    streams = [window.stream_combo.itemText(i)
               for i in range(window.stream_combo.count())]
    assert "snr_map" in streams and "test" in streams
    # 選了 snr 節點 → 預設看它寫出來的那條流
    assert window.stream_combo.currentText() == "snr_map"

    assert window.feature_table.rowCount() > 0
    assert "snr_max" in window.feature_table.feature_names()

    # 換一條影像流，畫面要跟著換（不用重跑 pipeline）
    window.stream_combo.setCurrentText("test")
    assert window.image_view.has_image() is True


# --------------------------------------------------------------------------- #
# 4. 參數編輯（合法 / 不合法）
# --------------------------------------------------------------------------- #
def test_param_edit_valid_then_invalid(window, synlot):
    _loaded(window, synlot)
    assert window.select_node("snr") is True

    window._on_param_edited("window", 21)
    assert window.model.nodes["snr"].params["window"] == 21
    assert window.param_form.has_error("window") is False

    window._on_param_edited("window", 15)
    assert window.model.nodes["snr"].params["window"] == 15

    # 999 超過 ParamSpec 上限 201 → 不可以丟例外，該列要變紅字，值不落地
    window._on_param_edited("window", 999)
    assert window.model.nodes["snr"].params["window"] == 15
    assert window.param_form.has_error("window") is True
    assert "maximum" in window.param_form.hint_text("window")

    # 再改一個合法值 → 錯誤狀態清掉
    window._on_param_edited("window", 15)
    assert window.param_form.has_error("window") is False


# --------------------------------------------------------------------------- #
# 5. 純滑鼠組流程（只發訊號，不碰 model）
# --------------------------------------------------------------------------- #
def test_mouse_only_pipeline_build(qapp):
    win = studio_mod.StudioWindow()
    try:
        win.library.add_requested.emit("load_patch")
        win.library.add_requested.emit("percentile_norm")
        assert win.model.node_order == ["load_patch", "percentile_norm"]
        assert win.pipeline.node_ids() == ["load_patch", "percentile_norm"]
        # 加入後自動選取新節點，右邊換成它的參數表單
        assert win.selected_node == "percentile_norm"
        assert win.param_form.step_key() == "percentile_norm"

        win.pipeline.move_requested.emit("percentile_norm", -1)
        assert win.model.node_order == ["percentile_norm", "load_patch"]
        assert win.pipeline.node_ids() == ["percentile_norm", "load_patch"]

        # 停用 / 移除也要走同一條路
        win.pipeline.node_toggled.emit("load_patch", False)
        assert win.model.nodes["load_patch"].enabled is False
        win.pipeline.remove_requested.emit("load_patch")
        assert win.model.node_order == ["percentile_norm"]

        # 點 Score 尾卡 → 換到分數編輯頁
        win.pipeline.score_clicked.emit()
        assert win.stack.currentWidget() is win.score_pane
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# 6. 試跑 → 直方圖
# --------------------------------------------------------------------------- #
def test_run_trial_fills_histogram(window, synlot):
    _loaded(window, synlot)

    assert window.run_trial(8, workers=1, sync=True) is True
    assert len(window.trial_scores) == 8
    assert window.histogram.has_data() is True
    assert sum(window.histogram._counts) == 8
    assert window.histogram.bin_summary_text().startswith("bin ")
    assert "Run finished" in window.status_text()


# --------------------------------------------------------------------------- #
# 7. 門檻：拖曳只是預覽，放開才寫回 model
# --------------------------------------------------------------------------- #
def test_threshold_live_preview_vs_commit(window, synlot):
    _loaded(window, synlot)
    if not window.trial_scores:
        window.run_trial(8, workers=1, sync=True)

    window._on_threshold_committed(42.5)
    assert window.model.threshold == pytest.approx(42.5)
    assert window.model.to_recipe().score.threshold == pytest.approx(42.5)
    assert window.threshold_spin.value() == pytest.approx(42.5)

    # 拖曳中（changed）只重算 bin 摘要，絕對不能動 model
    before = window.model.threshold
    window._on_threshold_changed(77.25)
    assert window.model.threshold == pytest.approx(before)
    live = window.histogram.bin_summary_text()
    assert live == "   ".join(
        "bin %s=%s" % (k, v)
        for k, v in sorted(vm_mod.rebin(window.trial_scores, 77.25,
                                        window.model.bins).items()))

    window._on_threshold_committed(50.0)
    assert window.model.threshold == pytest.approx(50.0)


# --------------------------------------------------------------------------- #
# 8. 存檔往返
# --------------------------------------------------------------------------- #
def test_save_recipe_round_trip(window, synlot, tmp_path):
    _loaded(window, synlot)
    out = tmp_path / "x.json"

    assert window.save_recipe_path(str(out)) is True
    assert out.is_file()
    json.loads(out.read_text(encoding="utf-8"))     # 是合法 JSON

    loaded = Recipe.load(str(out))
    assert loaded.routes[window.model.kind] == window.model.node_order
    assert loaded.score.expr == window.model.expr
    assert loaded.score.threshold == pytest.approx(window.model.threshold)
    assert sorted(loaded.nodes) == sorted(window.model.nodes)
    assert loaded.nodes["snr"].params["window"] == \
        window.model.nodes["snr"].params["window"]


# --------------------------------------------------------------------------- #
# 8.5 M7 推廣鐵則：前置條件不滿足的動作要「變灰 + 說明原因」，不是按了才罵人
# --------------------------------------------------------------------------- #
def test_actions_are_disabled_until_their_preconditions_hold(qapp, synlot):
    """按鈕的可用性要跟著狀態走，而且 tooltip 要講得出為什麼不能按。

    舊行為是全部亮著、按下去才在狀態列說「還沒有載入資料集」——狀態列在螢幕
    最下角，第一次用的人只會覺得「我按了，沒反應」。
    """
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        # 什麼都還沒有：跑不了、存不了、輸出不了
        assert win.btn_trial.isEnabled() is False
        assert win.act_run_all.isEnabled() is False
        assert win.spin_trial_n.isEnabled() is False
        assert win.btn_save_recipe.isEnabled() is False
        assert win.btn_export.isEnabled() is False
        for w in (win.btn_trial, win.btn_save_recipe, win.btn_export):
            assert w.toolTip().strip(), "變灰的按鈕一定要說明原因"

        # 只有資料集 → 還是不能跑（流程是空的），但理由要換一句
        assert win.load_dataset_path(synlot["klarf"], sync=True) is True
        assert win.btn_trial.isEnabled() is False
        assert "pipeline is empty" in win.btn_trial.toolTip()
        assert win.btn_save_recipe.isEnabled() is False

        # 資料集 + 流程 → 可以跑；但還沒有結果，所以還不能輸出
        assert win.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
        assert win.btn_trial.isEnabled() is True
        assert win.act_run_all.isEnabled() is True
        assert win.spin_trial_n.isEnabled() is True
        assert win.btn_save_recipe.isEnabled() is True
        assert win.btn_export.isEnabled() is False
        assert "No results yet" in win.btn_export.toolTip()

        # 跑完 → 輸出解鎖
        assert win.run_trial(8, workers=1, sync=True) is True
        assert win.btn_export.isEnabled() is True
    finally:
        win.close()


def test_trial_count_follows_the_dataset_size(qapp, synlot):
    """對一份只有 8 顆的 lot 顯示「First 200」沒有意義，只會讓人以為看錯了。"""
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.spin_trial_n.value() == studio_mod.DEFAULT_TRIAL_N
        win.load_dataset_path(synlot["klarf"], sync=True)
        assert win.spin_trial_n.value() == max(win.spin_trial_n.minimum(), 8)
    finally:
        win.close()


def test_run_all_lives_in_the_trial_button_menu(window):
    """主要動作只留一顆 ▶；破壞性比較大的「跑整批」降級成選單項目。"""
    menu = window.btn_trial.menu()
    assert menu is not None, "「跑整批」要收在試跑鈕的下拉裡"
    assert [a.text() for a in menu.actions()] == ["Run all defects"]
    assert window.btn_trial.text() == "▶ Run trial"
    # 舊版並排的第二顆 ▶ 鈕已經不存在
    assert not hasattr(window, "btn_full")


# --------------------------------------------------------------------------- #
# 8.6 M7：游標讀數有自己的位置，不准洗掉狀態列
# --------------------------------------------------------------------------- #
def test_cursor_readout_does_not_overwrite_the_status_bar(window, synlot):
    _loaded(window, synlot)
    window._status("Run finished: 8 defects")

    window._on_cursor_info("x 12  y 30  ·  gray 187")
    assert window.cursor_text() == "x 12  y 30  ·  gray 187"
    assert window.status_text() == "Run finished: 8 defects", \
        "滑鼠飄過影像不該把剛才的結果訊息洗掉"

    window._on_cursor_info("")            # 游標離開影像
    assert window.cursor_text() == ""
    assert window.status_text() == "Run finished: 8 defects"


# --------------------------------------------------------------------------- #
# 9. 關窗：三個 worker 都收乾淨
# --------------------------------------------------------------------------- #
def test_close_stops_workers(window, synlot):
    _loaded(window, synlot)

    # 真的丟一份非同步預覽出去（會開一條 QThread），再關窗
    assert window.refresh_preview(sync=False) is True
    window.close()

    for worker in (window.preview_worker, window.trial_worker,
                   window.dataset_worker):
        assert worker.is_running() is False
        assert worker.thread_obj is None
    assert window._preview_timer.isActive() is False


# --------------------------------------------------------------------------- #
# 10. F7-7 進度條：載入與試跑要看得到進度，不能只有狀態列一行字
# --------------------------------------------------------------------------- #
def test_progress_bar_is_hidden_when_idle_and_tracks_a_run(window, synlot):
    _loaded(window, synlot)
    assert window.progress_visible() is False, "閒著時不該佔位子"

    window._on_trial_progress(3, 8)
    assert window.progress_visible() is True
    assert window.progress.value() == 3
    assert window.progress.maximum() == 8

    window.run_trial(8, workers=1, sync=True)
    assert window.progress_visible() is False, "跑完要收起來"


def test_loading_uses_an_indeterminate_bar(window):
    """載入 KLARF 沒有可回報的百分比 —— 用跑馬燈回答「還在動嗎」。

    謊報一個假的百分比比不報還糟。
    """
    window._progress_busy("Loading…")
    assert window.progress_visible() is True
    assert (window.progress.minimum(), window.progress.maximum()) == (0, 0)
    window._progress_done()
    assert window.progress_visible() is False

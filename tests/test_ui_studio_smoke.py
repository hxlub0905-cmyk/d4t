# d4t Studio 主視窗煙霧測試 — authored 2026-07-28 (M3 收尾).
"""``d4t/ui/studio.py`` 的離屏（offscreen）煙霧測試。

執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_studio_smoke.py -q``

**為什麼所有 Qt import 都是 lazy 的（別改回去）**

``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有任何
PySide6 模組。pytest 先蒐集全部測試檔、再開始跑，所以只要這個檔案在**模組層**
``import PySide6``（或 import ``d4t.ui.studio``），蒐集階段就會把 Qt 塞進
``sys.modules``，那個守門測試就會紅 —— 即使它先跑。

因此：所有 Qt / ``d4t.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
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
EXAMPLE_RECIPE = REPO / "tests" / "fixtures" / "recipes" / "die_to_die_basic.json"

sys.path.insert(0, str(REPO / "tools"))
from make_sample import generate  # noqa: E402


def _load_qt() -> None:
    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
    from PySide6.QtWidgets import QApplication  # noqa: F401

    from d4t.ui import studio as studio_mod  # noqa: F401
    from d4t.ui import theme as theme_mod  # noqa: F401
    from d4t.ui import viewmodel as vm_mod  # noqa: F401

    from d4t.core.pipeline import Recipe  # noqa: F401

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
    # 判斷依據是「載過 recipe 了沒」，不是「畫布上有沒有節點」——
    # F7-9 起開窗就有一張起手 Input 卡，後者永遠是 True。
    if window.recipe_path is None:
        assert window.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
    return window


# --------------------------------------------------------------------------- #
# 1. 建構 + 卡片庫
# --------------------------------------------------------------------------- #
def test_window_constructs_with_library_cards(window):
    assert window.windowTitle().startswith("d4t Studio")
    # 卡片庫用的是真實 registry，不是手捏假資料
    assert window.library.entry("glv_stats") is not None
    assert window.library.entry("load_patch") is not None
    # 同 tests/test_ui_widgets.py：順序的出處是 LibraryPanel.GROUPS，不要再抄一份。
    from d4t.ui.widgets import LibraryPanel
    assert window.library.section_titles() == [
        t for _gid, t, _sub in LibraryPanel.GROUPS]

    # 空狀態：**畫布是空的**（F11 Enhance-4，使用者定調：「Load image 卡片改成
    # 預設沒有，user 可以選擇要 Load images or Load one image，add 才會出現」）。
    # F7-9 起這裡有一張起手的 `load_patch`；Input-4 把載入卡拆成兩張之後，
    # 預先放一張就是替使用者決定了他還沒決定的事。
    assert window.model.node_order == []
    assert window.pipeline.node_ids() == []
    assert window.selected_node is None
    # 兩張載入卡都在卡片庫裡，讓他挑
    assert window.library.entry("load_single") is not None
    assert window.model.dirty is False, "使用者什麼都還沒做，不該被問「要存檔嗎」"
    # 預覽沒有影像、直方圖沒有資料
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
    # 判定段的摘要跟著 model 走。F25 起**開起來的 recipe 一律是判定樹**
    # （舊的門檻自動變成第一個問題），所以這裡問的是那棵樹，不是門檻。
    summary = window.pipeline.score_summary_text()
    assert "decision tree" in summary and "question" in summary
    # 節點摘要 = 非預設參數的 k=v（最多 3 個）—— F7-6 起節點是自繪圖元
    # 摘要 = **非預設**參數的 k=v。以前這裡指著 `snr` 的 `window=15`；
    # 那張卡（Z-map）2026-08-25 刪掉了，而影像段剩下的幾張在這份 fixture 裡
    # 全部吃預設值 —— 摘要因此是空的（那是對的，不是壞的）。改指真的有
    # 非預設參數的那一張。
    assert "target=bright" in window.pipeline.card("cd").info["summary"]


# --------------------------------------------------------------------------- #
# 3. 選節點 + 預覽
# --------------------------------------------------------------------------- #
def test_select_node_and_preview(window, synlot):
    _loaded(window, synlot)

    assert window.select_node("dn") is True
    assert window.selected_node == "dn"
    assert window.pipeline.selected() == "dn"
    assert window.stack.currentWidget() is window.param_form
    assert window.param_form.step_key() == "denoise"

    assert window.refresh_preview(sync=True) is True
    assert window.image_view.has_image() is True

    streams = [window.stream_combo.itemText(i)
               for i in range(window.stream_combo.count())]
    assert "diff" in streams and "test" in streams
    # 選了 dn 節點 → 預設看它寫出來的那條流
    assert window.stream_combo.currentText() == "diff"

    assert window.feature_table.rowCount() > 0
    # 特徵表看的是**跑到這一個節點為止**算出來的東西 —— `dn` 是影像段的卡，
    # 所以這裡該有的是它自己那一個，不是後面量測卡的 `glv_*`。
    assert "removed_over_noise" in window.feature_table.feature_names()

    # 換一條影像流，畫面要跟著換（不用重跑 pipeline）
    window.stream_combo.setCurrentText("test")
    assert window.image_view.has_image() is True


def test_compare_shows_two_streams_with_linked_zoom_and_pan(window, synlot):
    """F7-8：並排比對預設關著，開了就自動配成 test | ref 並連動。

    預設關著是刻意的 —— F7-5 把 Gallery 搬走就是為了讓影像變大，
    預設並排等於把剛爭取到的寬度再砍一半。
    """
    from PySide6.QtCore import QPointF

    _loaded(window, synlot)
    assert window.refresh_preview(sync=True) is True
    window.stream_combo.setCurrentText("test")

    assert window.compare_enabled() is False
    assert window.image_view_b.has_image() is False

    assert window.set_compare(True) is True
    assert window.compare_check.isChecked() is True
    # 左邊是 test → 右邊自動給 ref（並排最常見的用途就是比這一對）
    assert window.stream_combo_b.currentText() == "ref"
    assert window.image_view_b.has_image() is True

    # 連動：沒有連動的並排，使用者得自己把兩邊拖到同一個位置才比得起來
    window.image_view.zoom_by(2.0)
    assert window.image_view_b.view_state()[0] == pytest.approx(
        window.image_view.view_state()[0])
    # 反向也要連動，而且不可以互相回寫到爆掉
    window.image_view_b.zoom_by(1.5)
    assert window.image_view.view_state()[0] == pytest.approx(
        window.image_view_b.view_state()[0])

    # 平移一樣連動
    before = window.image_view_b.view_state()[1]
    window.image_view.set_view(window.image_view.view_state()[0],
                               QPointF(11.0, 7.0))
    window.image_view.view_changed.emit(window.image_view.view_state()[0],
                                        QPointF(11.0, 7.0))
    assert window.image_view_b.view_state()[1] != before

    # 關掉之後右邊要真的放掉影像，不然它會留在記憶體裡也留在畫面上
    assert window.set_compare(False) is False
    assert window.image_view_b.has_image() is False


# --------------------------------------------------------------------------- #
# 4. 參數編輯（合法 / 不合法）
# --------------------------------------------------------------------------- #
def test_param_edit_valid_then_invalid(window, synlot):
    _loaded(window, synlot)
    assert window.select_node("dn") is True

    window._on_param_edited("ksize", 5)
    assert window.model.nodes["dn"].params["ksize"] == 5
    assert window.param_form.has_error("ksize") is False

    window._on_param_edited("ksize", 3)
    assert window.model.nodes["dn"].params["ksize"] == 3

    # 999 超過 ParamSpec 上限 15 → 不可以丟例外，該列要變紅字，值不落地
    window._on_param_edited("ksize", 999)
    assert window.model.nodes["dn"].params["ksize"] == 3
    assert window.param_form.has_error("ksize") is True
    assert "maximum" in window.param_form.hint_text("ksize")

    # 再改一個合法值 → 錯誤狀態清掉
    window._on_param_edited("window", 15)
    assert window.param_form.has_error("window") is False


# --------------------------------------------------------------------------- #
# 5. 純滑鼠組流程（只發訊號，不碰 model）
# --------------------------------------------------------------------------- #
def test_mouse_only_pipeline_build(qapp):
    win = studio_mod.StudioWindow()
    try:
        # 畫布是空的（F11 Enhance-4），所以兩張都要自己加
        assert win.model.node_order == []
        win.library.add_requested.emit("load_patch")
        win.library.add_requested.emit("normalize")
        assert win.model.node_order == ["load_patch", "normalize"]
        assert win.pipeline.node_ids() == ["load_patch", "normalize"]
        # 加入後自動選取新節點，右邊換成它的參數表單
        assert win.selected_node == "normalize"
        assert win.param_form.step_key() == "normalize"

        win.pipeline.move_requested.emit("normalize", -1)
        assert win.model.node_order == ["normalize", "load_patch"]
        assert win.pipeline.node_ids() == ["normalize", "load_patch"]

        # 停用 / 移除也要走同一條路
        win.pipeline.node_toggled.emit("load_patch", False)
        assert win.model.nodes["load_patch"].enabled is False
        win.pipeline.remove_requested.emit("load_patch")
        assert win.model.node_order == ["normalize"]

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
    # ⚠ **「bin 0=5   bin 1=3」那一行只在二元那條路上**（R1，2026-08-24）。
    # 這份 recipe 一打開就是一棵樹（F25），而樹判出來的顆數在判定段上有更好
    # 的位置（每一類一列、寬度就是顆數）—— 在這裡再寫一次的話，那個「再一次」
    # 是用門檻**重算**的，跟樹判出來的對不起來。實測過的下場：每一張縮圖說
    # `bin 3`，而 150px 底下的圖例說 `bin 1=24`。
    assert window.model.decide is not None
    assert window.histogram.bin_summary_text() == ""
    assert [r["count"] for r in window.results.verdict.rows()], \
        "顆數要在判定段上"
    assert sum(r["count"] for r in window.results.verdict.rows()) == 8
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
    # F25：門檻**沒有編輯格了**（使用者：「二元門檻的 UI 完全拿掉」）。
    # 這一條守的是底下那條規矩本身 —— 拖曳只預覽、放開才寫回 model ——
    # 而那條規矩對任何一個「拖了才算數」的控制項都要成立。
    from PySide6.QtWidgets import QDoubleSpinBox
    assert window.decide_panel.findChild(QDoubleSpinBox) is None

    # 拖曳中（changed）只重算 bin 摘要，絕對不能動 model
    before = window.model.threshold
    window._on_threshold_changed(77.25)
    assert window.model.threshold == pytest.approx(before)
    live = window.histogram.bin_summary_text()
    # 前綴比對而不是整句相等：合成資料旁邊就有 ground_truth.json，於是同一行
    # 後面還會接一段正確率（Phase 1）。這一條要驗的是**bin 數跟著門檻走**，
    # 不是那一行長什麼樣子 —— 整句相等會讓它每加一個讀數就紅一次。
    assert live.startswith("   ".join(
        "bin %s=%s" % (k, v)
        for k, v in sorted(vm_mod.rebin(window.trial_scores, 77.25,
                                        window.model.bins).items())))

    window._on_threshold_committed(50.0)
    assert window.model.threshold == pytest.approx(50.0)


# --------------------------------------------------------------------------- #
# 8. 編輯中的 model 轉得成 recipe
# --------------------------------------------------------------------------- #
def test_the_model_converts_to_a_runnable_recipe(window, synlot):
    """**畫面上的 model 要轉得成引擎吃得下的 recipe** —— ``run_trial`` 與
    ``run_batch`` 走的正是這條路。

    2026-08-16 到 2026-08-26 之間這是唯一問得到這件事的地方（存檔拿掉了）。
    存檔回來之後**這一支仍然留著**：它問的是 model → recipe 那一步，
    而經過磁碟的那條路在 `tests/test_ui_save_recipe.py`。兩者一起紅的時候
    分得出斷在哪一段。"""
    _loaded(window, synlot)
    rec = window.model.to_recipe()
    assert rec.routes[window.model.kind] == window.model.node_order
    assert rec.score.expr == window.model.expr
    # 而且轉成 JSON 再讀回來要一模一樣（run_batch 就是這樣送進 worker 的）
    again = Recipe.from_json_dict(json.loads(json.dumps(rec.to_json_dict())))
    assert again == rec
    assert again.score.threshold == pytest.approx(window.model.threshold)
    assert sorted(again.nodes) == sorted(window.model.nodes)
    assert again.nodes["dn"].params["ksize"] == \
        window.model.nodes["dn"].params["ksize"]


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
        # 還沒有資料、畫布也是空的（F11 Enhance-4）：跑不了、輸出不了
        assert win.btn_trial.isEnabled() is False
        # 箭頭是 F7-23 起的第二顆真按鈕，要跟主鈕同進退 —— 還打得開一個
        # 「每一項都是灰的」選單，等於讓使用者多按一次才知道不能按。
        assert win.btn_trial_more.isEnabled() is False
        assert win.act_run_all.isEnabled() is False
        assert win.spin_trial_n.isEnabled() is False
        # 兩件事都還沒做（沒有資料、畫布也是空的，F11 Enhance-4）——
        # tooltip 要把**兩件**都講出來，不是只講其中一件。
        assert "Load a KLARF and add at least one card" in win.btn_trial.toolTip()
        for w in (win.btn_trial, win.btn_trial_more):
            assert w.toolTip().strip(), "變灰的按鈕一定要說明原因"
        assert win.act_run_all.toolTip().strip(), "變灰的選單項也要說明原因"

        # 加一張卡進去 → 理由要換一句（缺的只剩資料）
        win.library.add_requested.emit("load_patch")
        assert "No dataset" in win.btn_trial.toolTip()

        # 載入資料 → 兩個條件都滿足了（畫布上有卡、也有資料）
        assert win.load_dataset_path(synlot["klarf"], sync=True) is True
        assert win.btn_trial.isEnabled() is True

        # 把卡片刪掉 → 流程真的空了，理由要換一句
        win.pipeline.remove_requested.emit(win.model.node_order[0])
        assert win.btn_trial.isEnabled() is False
        assert "pipeline is empty" in win.btn_trial.toolTip()

        # 資料集 + 流程 → 都能按。「Run all & write」跟 Run trial 是**同一個
        # 前提** —— 它自己就是那一次跑，不必先有結果（F16 Stage 5c：以前這一格
        # 是輸出精靈，那時候「先跑一次才會亮」是對的）。
        assert win.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
        assert win.btn_trial.isEnabled() is True
        assert win.btn_trial_more.isEnabled() is True
        assert win.act_run_all.isEnabled() is True
        assert win.spin_trial_n.isEnabled() is True
        assert win.act_run_all.toolTip().strip()

        assert win.run_trial(8, workers=1, sync=True) is True
        assert win.act_run_all.isEnabled() is True
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
    """主要動作只留一顆 ▶；破壞性比較大的「跑整批」降級成選單項目。

    F7-23 第二輪把那顆 ``MenuButtonPopup`` 拆成兩顆真的按鈕（主體 + ▾）——
    **選單的擁有者換了，但這條測試問的事沒有換**：跑整批仍然只在下拉裡。
    箭頭改成一顆自己的按鈕的理由（QSS 修不了那半邊的外觀）見計畫書 §27.5。

    2026-08-24 這條規矩被恢復成唯一的答案：工具列上那顆重複的
    「Run all & write」拿掉了（同一支 `run_all()`），而選單這一項改成
    **跟 Results 視窗上那顆逐字相同**的名字 —— 同一個動作在兩個地方叫兩個
    名字，正是它一開始變成兩顆鈕的那一步。
    """
    assert [a.text() for a in window.trial_menu.actions()] == ["Run all && write"]
    # F7-23 第四輪把 ``▶`` 與 ``▾`` 換成自繪圖示（那兩個字元在廠內的 Windows
    # 上不保證有字型），所以問的是圖示的名字，不是那顆字。
    assert window.btn_trial.text() == "Run trial"
    assert window.btn_trial.glyph_name() == "play"
    assert window.btn_trial_more.glyph_name() == "chevron_down"
    # 主鈕本身不再掛選單 —— 掛著的話 Qt 會回頭自己畫那個下拉區
    assert window.btn_trial.menu() is None
    assert window.btn_trial_more.menu() is None, \
        "箭頭鈕也不能掛 menu，否則 Qt 會再加一個自己的下拉指示器"
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

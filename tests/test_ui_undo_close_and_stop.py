# 退一步／關窗／停止（常駐）：四件會讓使用者**丟掉工作成果**的事。
# 起於 F7-16；2026-08-27 從 `test_ui_f7_16_safety_net.py` 改名（F39 A 組）。
# ⚠ `docs/PITFALLS.md` 指名這一支守「`_update_action_states` 蓋掉 tooltip」。
"""這四項不是「不方便」，是「一個誤按就沒了」：

* 刪錯一張卡沒得退 —— 而這是一個「一直在試」的工具，試錯就是主要動作；
* 沒有任何快捷鍵，存檔／跑一次／退一步每次都要把手移到滑鼠；
* 關窗不問「還沒存」，調了一小時的 recipe 關掉就沒了；
* 跑到一半不能停 —— 而「按下去才發現參數設錯」是最常見的情況。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

#: 「先載一份真的 pipeline 進來」用的 recipe。
#:
#: 以前這幾條測試呼叫的是 ``window.load_template()``。範例 recipe 2026-08-16
#: 全部拿掉之後那支會找不到檔案、回 ``False`` —— 而**這些測試仍然會過**，
#: 因為它們沒有檢查回傳值，而 ``run_trial`` 用空流程也跑得完。
#: 那是最糟的一種綠燈：中止鈕的行為在「有東西可跑」的前提下才有意義。
FIXTURE_RECIPE = (Path(__file__).resolve().parent
                  / "fixtures" / "recipes" / "die_to_die_basic.json")


def _import_qt(g):
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QApplication

    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    g.update(QApplication=QApplication, QKeySequence=QKeySequence,
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
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 復原（model 層，Qt-free）
# --------------------------------------------------------------------------- #
def _model():
    import d4t.core.steps  # noqa: F401 — 註冊卡片
    from d4t.ui.viewmodel import RecipeModel

    m = RecipeModel.starter()
    # F11 Enhance-4：`starter()` 現在是**空白畫布**（使用者要自己挑載入卡）。
    # 復原這幾題問的是「刪掉一張卡退得回來嗎」，所以先放一張進去 ——
    # 而它不算「使用者做過的一步」，同起手卡當年的理由。
    m.add_step("load_patch")
    m.dirty = False
    m.clear_history()
    return m


def test_a_fresh_recipe_has_nothing_to_undo():
    """起手卡不是「使用者做過的一步」—— Ctrl+Z 不該把畫布退成空白。"""
    m = _model()
    assert m.can_undo() is False
    assert m.dirty is False


def test_deleting_a_card_can_be_taken_back():
    m = _model()
    nid = m.add_step("align")
    m.remove(nid)
    assert m.node_order == ["load_patch"]
    assert m.undo() is True
    assert m.node_order == ["load_patch", nid]
    assert m.nodes[nid].step == "align"


def test_one_ctrl_z_undoes_a_whole_slider_drag():
    """拖一次滑桿會發幾十次 set_param。每一次各記一步的話，按一次 Ctrl+Z 只退
    回一個畫素 —— 使用者得按四十次才回得到動之前的樣子，那等於沒有復原。"""
    m = _model()
    nid = m.add_step("align")
    before = m.nodes[nid].params["search_radius"]
    for v in (2, 3, 4, 5, 6, 7):
        m.set_param(nid, "search_radius", v)
    assert m.nodes[nid].params["search_radius"] == 7
    assert m.undo() is True
    assert m.nodes[nid].params["search_radius"] == before


def test_two_separate_visits_to_the_same_slider_are_two_steps():
    """「調 A → 去做別的 → 再調 A」是兩件事。中間那個動作切開它們。"""
    m = _model()
    nid = m.add_step("align")
    m.set_param(nid, "search_radius", 3)
    m.end_coalescing()                      # Studio 在換節點/存檔時呼叫
    m.set_param(nid, "search_radius", 9)
    assert m.undo() is True
    assert m.nodes[nid].params["search_radius"] == 3


def test_undo_covers_the_side_effects_too():
    """``add_edge`` 會重排 ``node_order`` —— 復原是整份狀態的快照，
    所以連帶的重排也會一起回去（反向操作很容易漏掉這種）。"""
    m = _model()
    a = m.add_step("align")
    b = m.add_step("subtract")
    m.move(b, -1)
    order_before = list(m.node_order)
    assert m.add_edge(a, b) is True
    assert m.node_order != order_before
    assert m.undo() is True
    assert m.node_order == order_before
    assert m.edges == []


def test_redo_puts_it_back_and_a_new_edit_drops_it():
    m = _model()
    nid = m.add_step("align")
    m.undo()
    assert m.can_redo() is True
    assert m.redo() is True
    assert nid in m.node_order

    m.undo()
    m.add_step("denoise")                   # 新的一步 → 舊的重做鏈作廢
    assert m.can_redo() is False


def test_the_history_does_not_grow_without_bound():
    m = _model()
    nid = m.add_step("align")
    for i in range(m.UNDO_DEPTH + 30):
        m.end_coalescing()
        m.set_param(nid, "search_radius", (i % 15) + 1)
    assert len(m._undo) == m.UNDO_DEPTH


def test_loading_a_recipe_starts_a_new_history(window):
    """載進來的檔案在那之前發生的事，不屬於這一份 recipe。"""
    window.model.add_step("align")
    assert window.model.can_undo() is True
    assert window.load_recipe_path(str(FIXTURE_RECIPE), sync=True) is True
    assert window.model.can_undo() is False


def test_studio_says_so_when_there_is_nothing_to_undo(window):
    """按了 Ctrl+Z 卻什麼都沒發生，使用者第一個念頭是「這工具壞了嗎」。"""
    assert window.undo() is False
    assert "Nothing to undo" in window.status_text()
    window.model.add_step("align")
    assert window.undo() is True
    assert "Undone" in window.status_text()


# --------------------------------------------------------------------------- #
# 2. 快捷鍵
# --------------------------------------------------------------------------- #
def test_the_usual_keys_all_exist(window):
    keys = {sc.key().toString() for sc in window._shortcuts}
    for want in ("Ctrl+O", "Ctrl+R", "Ctrl+Z", "Ctrl+0"):
        assert QKeySequence(want).toString() in keys, want


def test_ctrl_z_is_wired_to_undo(window):
    window.model.add_step("align")
    n = len(window.model.node_order)
    for sc in window._shortcuts:
        if sc.key() == QKeySequence("Ctrl+Z"):
            sc.activated.emit()
            break
    assert len(window.model.node_order) == n - 1


def test_the_shortcut_is_written_where_it_will_be_found(window):
    """按鍵存在還不夠 —— 要發現得到。而且 ``_update_action_states`` 每次
    refresh 都會重寫這幾顆的 tooltip，設一次的話第一次 refresh 就沒了。

    F14-1 之後 ``Ctrl+O`` 那顆鈕在**空白狀態**上：工具列那幾顆資料入口拿掉了，
    而快捷鍵要在**還看得到的**那顆鈕上講出來，不然它就只活在原始碼裡。

    ``Ctrl+S`` 這一條 2026-08-26 回來了 —— 它是原本這支測試的例子，而且它
    正好踩在同一個坑上：``_update_action_states`` 會重寫存檔鈕的 tooltip
    （它要講「存回哪一個檔案」），所以設一次的話第一次 refresh 就沒了。
    """
    assert "Ctrl+O" in window.btn_empty_open.toolTip()
    assert "Ctrl+R" in window.btn_trial.toolTip()
    assert "Ctrl+S" in window.btn_save_recipe.toolTip()
    window.model.add_step("align")
    window._refresh_all()
    assert "Ctrl+O" in window.btn_empty_open.toolTip(), "refresh 之後不見了"
    assert "Ctrl+S" in window.btn_save_recipe.toolTip(), "refresh 之後不見了"


def test_ctrl_f_opens_the_card_search(window):
    window.focus_card_search()
    assert window.library.panel_open() is True


# --------------------------------------------------------------------------- #
# 3. 關窗前的確認
# --------------------------------------------------------------------------- #
def test_a_clean_recipe_closes_without_asking(window):
    assert window.unsaved_changes() is False
    asked = []
    window._ask_unsaved = lambda: asked.append(1) or "discard"
    window.PROMPT_ON_CLOSE = True
    try:
        assert window.confirm_close() is True
        assert asked == []
    finally:
        window.PROMPT_ON_CLOSE = False


@pytest.mark.parametrize("answer,expected", [
    ("discard", True), ("cancel", False),
])
def test_the_three_answers_do_what_they_say(window, answer, expected):
    window.model.add_step("align")
    assert window.unsaved_changes() is True
    window._ask_unsaved = lambda: answer
    window.PROMPT_ON_CLOSE = True
    try:
        assert window.confirm_close() is expected
    finally:
        window.PROMPT_ON_CLOSE = False


def test_saving_from_the_close_prompt_really_saves(window, tmp_path):
    """第三個答案 2026-08-26 回來了 —— 而它要**真的存下去**才算可以關。

    2026-08-16 到 2026-08-26 之間這裡只有兩個答案（存檔功能拿掉了），
    這支測試那時候斷言的是「``_on_save_recipe`` 不存在」。
    """
    path = tmp_path / "kept.json"
    window.model.add_step("align")
    window.recipe_path = str(path)          # 已經有原檔 → Ctrl+S 不會問路徑
    window._ask_unsaved = lambda: "save"
    window.PROMPT_ON_CLOSE = True
    try:
        assert window.confirm_close() is True
    finally:
        window.PROMPT_ON_CLOSE = False
    assert path.is_file(), "答「存」之後檔案要真的在磁碟上"
    assert window.unsaved_changes() is False


def test_a_save_that_did_not_happen_is_not_permission_to_close(window):
    """**存檔失敗（或使用者在另存對話框按取消）不算可以關。**

    那是「我改變主意了」，不是「丟掉吧」—— 而這兩者的差別是一整份 pipeline。
    """
    window.model.add_step("align")
    window._ask_unsaved = lambda: "save"
    window._on_save_recipe = lambda: False   # 使用者在另存對話框按了取消
    window.PROMPT_ON_CLOSE = True
    try:
        assert window.confirm_close() is False
    finally:
        window.PROMPT_ON_CLOSE = False


def test_the_close_event_is_actually_gated(window):
    """真的走 closeEvent 那條路，不是只測那個判斷函式。"""
    from PySide6.QtGui import QCloseEvent

    window.model.add_step("align")
    window._ask_unsaved = lambda: "cancel"
    window.PROMPT_ON_CLOSE = True
    try:
        e = QCloseEvent()
        window.closeEvent(e)
        assert e.isAccepted() is False
    finally:
        window.PROMPT_ON_CLOSE = False


# --------------------------------------------------------------------------- #
# 4. 跑到一半可以停
# --------------------------------------------------------------------------- #
def test_stop_only_shows_while_something_is_running(window, tmp_path):
    from make_sample import generate

    assert window.stop_available() is False
    out = generate(str(tmp_path / "lot"), n=6, seed=1)
    window.load_dataset_path(out["klarf"], sync=True)
    assert window.load_recipe_path(str(FIXTURE_RECIPE), sync=True) is True
    assert window.run_trial(n=6, sync=True) is True
    assert window.stop_available() is False, "同步跑完之後不該還留著中止鈕"
    assert window.stop_run() is False


def test_the_stop_button_is_there_while_a_real_run_is_in_flight(window, tmp_path,
                                                                qapp):
    """同步路徑測不到這一項 —— 中止鈕存在的**唯一**意義就是背景跑的時候。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lot3"), n=40, seed=5)
    window.load_dataset_path(out["klarf"], sync=True)
    assert window.load_recipe_path(str(FIXTURE_RECIPE), sync=True) is True
    assert window.run_trial(n=40, sync=False) is True
    try:
        assert window.stop_available() is True
        assert window.progress_visible() is True
        assert window.stop_run() is True
        assert "Stopping" in window.status_text()
    finally:
        window.trial_worker.stop()          # 收乾淨，不留背景執行緒
        qapp.processEvents()


def test_stopping_keeps_what_already_finished(window, tmp_path):
    """按停止是「不要再等了」，不是「把剛才那五分鐘丟掉」。"""
    from make_sample import generate

    out = generate(str(tmp_path / "lot2"), n=8, seed=2)
    window.load_dataset_path(out["klarf"], sync=True)
    assert window.load_recipe_path(str(FIXTURE_RECIPE), sync=True) is True
    window._trial_t0 = 0.0
    # 直接模擬「跑到一半被按停」：worker 中止後仍會把部分結果送出來
    window.trial_worker.abort()
    partial = [{"defect_id": i, "ok": True, "score": 0.1 * i, "features": {},
                "bin": 0} for i in range(3)]
    window._apply_trial_results(partial, 1.0)
    assert len(window.trial_results) == 3
    assert "Run stopped" in window.status_text()
    assert "finished" not in window.status_text().split(":")[0]

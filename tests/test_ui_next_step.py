# X5／X6／U21／U17：一句話說完之後，接下來能做什麼 — authored 2026-09-08.
"""**畫面說出發生了什麼，卻沒有說接下來能做什麼。**

四個抱怨，兩個機制：

* **X5** 整批跑完寫出報表資料夾，路徑印在狀態列 —— 然後使用者自己去開檔案
  總管、自己把它貼進去。
* **X6** `_say_fallout` 說「這條線接上去，那兩條被拿掉了」，一閃即逝。
  **誤操作後的三秒鐘，是使用者最不想去找 Ctrl+Z 的三秒鐘。**
* **U21** `Results` 那顆鈕不會說裡面有沒有東西 —— 而使用者的心智模型裡
  「關掉視窗」通常等於「丟掉」。
* **U17** 舊 recipe 開起來靜默升級，畫布上多了東西而沒有一句話說明，
  接著存檔就寫成新格式。這是「畫布不說謊」唯一還沒守到的角落。

前兩個共用 `ui/status_action.py`（那一句話旁邊的一顆鈕），後兩個各自在
`studio.py` 上接線。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# --------------------------------------------------------------------------- #
# 1. 那顆鈕本身
# --------------------------------------------------------------------------- #
def test_it_starts_with_nothing_on_it(qapp):
    from d4t.ui.status_action import StatusAction
    a = StatusAction()
    try:
        assert not a.armed() and a.label() == ""
    finally:
        a.deleteLater()


def test_arming_it_shows_a_label_and_running_it_calls_back(qapp):
    from d4t.ui.status_action import StatusAction
    a = StatusAction()
    seen = []
    try:
        a.arm("Undo", lambda: seen.append(1), "Undo that change")
        assert a.armed() and a.label() == "Undo"
        a.click()
        assert seen == [1]
    finally:
        a.deleteLater()


def test_it_disarms_itself_before_the_callback_runs(qapp):
    """**先收再跑。**

    反過來的話（先跑再收），callback 裡講的下一句話會自己 arm 一顆新的鈕，
    而接著那個 `disarm` 會把新的那顆一起收掉 —— 症狀是「復原之後那顆鈕閃
    一下就不見了」。
    """
    from d4t.ui.status_action import StatusAction
    a = StatusAction()
    during = []
    try:
        a.arm("Undo", lambda: during.append(a.armed()))
        a.click()
        assert during == [False], "callback 跑的時候那顆鈕應該已經收掉了"
    finally:
        a.deleteLater()


def test_an_empty_label_or_no_callback_arms_nothing(qapp):
    """半個「下一步」比沒有更糟 —— 一顆沒有字的鈕看起來像畫面壞了。"""
    from d4t.ui.status_action import StatusAction
    a = StatusAction()
    try:
        a.arm("", lambda: None)
        assert not a.armed()
        a.arm("Undo", None)         # type: ignore[arg-type]
        assert not a.armed()
    finally:
        a.deleteLater()


def test_open_folder_never_raises_on_a_path_that_is_not_there(qapp):
    """它是補充用的鈕，不准害死呼叫端（路徑照樣寫在訊息裡）。"""
    from d4t.ui.status_action import open_folder
    assert open_folder("/no/such/place/at/all") is False
    assert open_folder(None) is False


# --------------------------------------------------------------------------- #
# 2. 接進 Studio
# --------------------------------------------------------------------------- #
def _studio(qapp):
    from d4t.ui.studio import StudioWindow
    return StudioWindow()


def test_the_next_message_always_takes_the_button_away(qapp):
    """**這是那顆鈕的第一條規矩。**

    一顆停在那裡的「復原」按鈕，在使用者做了三件別的事之後按下去，復原的不是
    他以為的那一件。收在 `_status` 裡（而不是每個呼叫端）是為了讓「忘了收」
    在設計上不會發生。
    """
    win = _studio(qapp)
    try:
        win._status_next_step("Something happened", "Undo", lambda: None)
        assert win.status_action.armed()
        win._status("Something else happened")
        assert not win.status_action.armed()
    finally:
        win.close()


def test_dropping_a_wire_offers_an_undo_right_there(qapp):
    """X6：`_say_fallout` 那句話旁邊要有一條反悔的路。"""
    win = _studio(qapp)
    from d4t.ui import canvas_edges

    try:
        canvas_edges.say_fallout(win, ["Two wires were removed."])
        assert win.status_action.armed()
        assert win.status_action.label() == "Undo"
        assert win.status_level() == "error"
    finally:
        win.close()


def test_nothing_to_say_means_no_button(qapp):
    """沒有連帶影響的時候那句話是「接好了」—— 那不需要反悔的入口。"""
    win = _studio(qapp)
    from d4t.ui import canvas_edges

    try:
        canvas_edges.say_fallout(win, [], "Connected a to b")
        assert not win.status_action.armed()
    finally:
        win.close()


def test_the_results_button_says_how_many_are_in_there(qapp):
    """U21：關掉那個視窗之後，鈕上的數字是唯一的線索。

    ⚠ **它不會被 disable。** U21 原本寫的是「沒跑過就 disabled」，而那跟使用者
    2026-08-28 自己講的話衝突（「加一個按鈕獨立呼叫一個視窗」—— 那顆鈕存在的
    唯一理由就是隨時叫得出那個視窗）。U21 真正的抱怨是「鈕上沒有東西說明裡面
    有沒有結果」，而那件事由計數與 tooltip 回答。
    """
    win = _studio(qapp)
    try:
        assert win.btn_results.isEnabled(), \
            "隨時叫得出那個視窗是它存在的理由（使用者 2026-08-28）"
        assert "empty" in win.btn_results.toolTip().lower(), \
            "沒跑過的時候 tooltip 要說「裡面是空的」"
        win.trial_results = [{"ok": True}, {"ok": False}, {"ok": True}]
        win._refresh_results_button()
        assert win.btn_results.text() == "Results · 3", win.btn_results.text()
    finally:
        win.close()


def test_the_count_includes_the_ones_that_failed(qapp):
    """鐵則 7：單顆出錯不殺整批，而那幾顆在 Results 裡看得到 —— 所以要算。"""
    win = _studio(qapp)
    try:
        win.trial_results = [{"ok": False}, {"ok": False}]
        win._refresh_results_button()
        assert win.btn_results.text() == "Results · 2"
    finally:
        win.close()


def test_a_new_dataset_empties_the_count(qapp):
    """換資料集 = 舊結果作廢，而鈕上的數字不能停在上一批。"""
    win = _studio(qapp)
    try:
        win.trial_results = [{"ok": True}]
        win._refresh_results_button()
        assert win.btn_results.text() == "Results · 1"
        win.trial_results = []
        win._refresh_results_button()
        assert win.btn_results.text() == "Results"
        assert win.btn_results.isEnabled(), "清空不該把它鎖起來"
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# 3. U17：升級要說話
# --------------------------------------------------------------------------- #
def test_an_upgrade_is_described_in_words():
    """不 import Qt 的那一半：比對前後，講成人話。"""
    from d4t.core.pipeline.recipe import RECIPE_VERSION, describe_migration

    class _Fake:
        edges = [1, 2, 3]
        nodes = {"a": object(), "b": object()}

    raw = {"version": 1, "edges": [1], "nodes": {"a": {"step": "load_patch"}}}
    says = describe_migration(raw, _Fake())
    assert any("wire" in t for t in says), says
    assert any("split" in t for t in says), says
    assert describe_migration({"version": RECIPE_VERSION}, _Fake()) == [], \
        "已經是現在這一版的檔案沒有被升級，不該講話"


def test_the_decision_card_the_upgrade_adds_is_not_called_a_split():
    """第 6 版補上來的 Decision 卡不是「拆出來的」（F123 期 1）—— 判定一直都在，
    只是以前不是一張卡。那一句要講它是什麼。"""
    from d4t.core.pipeline.recipe import Recipe, describe_migration

    raw = {"recipe_id": "old", "version": 5, "routes": {"ebi_patch": ["load"]},
           "nodes": {"load": {"step": "load_patch", "params": {}}},
           "score": {"expr": "glv_max", "threshold": 3.0,
                     "bins": {"below": 0, "above": 1}}}
    says = describe_migration(raw, Recipe.from_json_dict(raw))
    assert any("decision" in t and "card" in t for t in says), says
    assert not any("split" in t for t in says), says


def test_a_renamed_card_is_named():
    """「多了兩條線」講得出來，「那張卡換了名字」也要 —— 那是畫布上最明顯的差別。"""
    from d4t.core.pipeline.recipe import describe_migration

    class _Node:
        step = "roi_reference"

    class _Fake:
        edges: list = []
        nodes = {"n1": _Node()}

    says = describe_migration(
        {"version": 1, "edges": [], "nodes": {"n1": {"step": "roi_mask"}}},
        _Fake())
    assert any("roi_mask" in t for t in says), says


def test_garbage_in_never_takes_the_recipe_down():
    """這只是一句提示 —— 它不准把一份載得起來的 recipe 變成一個錯誤。"""
    from d4t.core.pipeline.recipe import describe_migration

    class _Fake:
        edges: list = []
        nodes: dict = {}

    for raw in (None, [], "nope", {"version": "not a number"},
                {"version": 1, "nodes": "not a dict"}):
        assert describe_migration(raw, _Fake()) == []

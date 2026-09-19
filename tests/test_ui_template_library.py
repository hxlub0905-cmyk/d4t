# X4：範本庫關著的前提已經到期 — authored 2026-09-08.
"""**對著空白畫布，「我該放哪張卡」是一個沒有答案的問題。**

`SHOW_SAMPLE_ENTRIES` 2026-08-16 關掉的理由是「範例 recipe 全部拿掉了」——
那時候 Templates… 按下去只會開一個空對話框，而**按了撞牆的鈕比沒有那顆鈕
更糟**（推廣鐵則）。

那個理由到期了：`recipes/` 有出貨的 recipe，而且 `test_shipped_recipes.py`
逐份真的跑一次（舊的 ``examples/`` 就是因為沒人測而爛掉的）。

驗收條件是「**開窗 → Templates → 選一份 → 直接 Run trial 跑得完，全程不碰
檔案總管**」。所以這一支從那條動線走一次，外加三件會安靜壞掉的事：

1. **旗標拆成兩個**，而且拆得對 —— 範本庫回來了，範例資料**沒有**（它產得出
   資料卻不載 pipeline，那是另一個缺口）。一個旗標管兩顆鈕的話，打開其中
   一個會順手把另一顆仍然撞牆的鈕放回畫面上。
2. **庫指的是真的那個資料夾**（在這之前它指著 `examples/recipes`，一個已經
   不存在的路徑 —— 那正是「開起來是空的」的機制）。
3. **每一份都講得出自己在做什麼**：清單上顯示的字是 recipe JSON 的
   ``description``，少了它使用者看到的是一個檔名，而他要決定的正是
   「哪一份最接近我的層」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication              # noqa: E402

from d4t.ui import scope                                # noqa: E402
from d4t.ui import studio as studio_mod                 # noqa: E402
from d4t.ui import theme as theme_mod                   # noqa: E402
from d4t.ui import welcome as welcome_mod               # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 前提
# --------------------------------------------------------------------------- #
def test_the_library_points_at_the_shipped_recipes():
    """在這之前它指著 `examples/recipes` —— 一個 2026-08-16 就刪掉的路徑。"""
    assert welcome_mod.RECIPES_DIR == REPO / "recipes"
    assert welcome_mod.RECIPES_DIR.is_dir()
    assert welcome_mod.list_recipe_files(), "recipes/ 裡一份 JSON 都沒有？"


def test_the_two_entries_are_two_flags_now():
    """**它們的死法不一樣，所以它們不是同一個決定。**

    範本庫：庫是空的 → `recipes/` 填回來就活了（2026-09-08）。
    範例資料：`run_demo` 產得出資料，但 `load_template` 指著一份不存在的
    ``ebi_patch`` recipe —— 那不是「庫空了」，是這條路本來就少一半。
    **2026-09-09 補上了**（`recipes/ebi-die-to-die.json`），兩個都開著。
    """
    assert scope.SHOW_TEMPLATE_LIBRARY is True
    assert scope.SHOW_SAMPLE_DATA is True
    assert not hasattr(scope, "SHOW_SAMPLE_ENTRIES"), (
        "舊的那個旗標還在 —— 兩個名字描述同一件事，遲早有一個先過期")


def test_the_sample_data_flag_matches_whether_the_recipe_exists():
    """旗標與事實要一致，**兩個方向都問**。

    關著：要有一個還成立的理由（那份 recipe 真的不在）—— 修好了卻沒打開，
    這一條會紅（`CLAUDE.md`：任何「例外清單」都要有那支反向的測試）。
    開著：那份 recipe 要在、而且 route 要是 `run_demo` 產的那種（``ebi_patch``）
    —— 不然按下去又是一批資料配一張空白畫布。
    """
    from d4t.core.pipeline import Recipe

    if not scope.SHOW_SAMPLE_DATA:
        assert not studio_mod.TEMPLATE_RECIPE.is_file(), (
            "「用範例資料試一次」的那份 recipe 現在存在了，而旗標還關著 —— "
            "把 scope.SHOW_SAMPLE_DATA 打開，或說明為什麼還不行")
        return
    assert studio_mod.TEMPLATE_RECIPE.is_file(), (
        "旗標開著，但 %s 不在 —— 按下去會撞牆" % studio_mod.TEMPLATE_RECIPE)
    assert "ebi_patch" in Recipe.load(studio_mod.TEMPLATE_RECIPE).routes


# --------------------------------------------------------------------------- #
# 畫面上真的看得到
# --------------------------------------------------------------------------- #
def test_both_entries_are_back_on_the_screen(qapp, window):
    """**要真的 show 過再問。**

    `QToolBar.addWidget` 把 widget 包進一個 QWidgetAction，而 Qt 在工具列
    真的顯示出來以前把它們**全部**藏著 —— 沒有 show 的話每一顆都答 hidden，
    這條測試就永遠是綠的而且什麼都沒問到（`studio_layout.build_toolbar` 裡那段分隔線的
    註解記著同一件事）。
    """
    window.show()
    qapp.processEvents()
    assert window.btn_examples.isVisible() is True
    assert window.btn_empty_sample.isHidden() is False, \
        "「用範例資料試一次」2026-09-09 回來了（recipes/ebi-die-to-die.json）"


def test_the_welcome_dialog_agrees_with_the_toolbar(qapp):
    """導覽是第一次用的人看到的第一個畫面 —— 上面不能有按了撞牆的鈕，
    而現在兩顆都通了（2026-09-09），兩顆都要看得到。"""
    dlg = welcome_mod.WelcomeDialog()
    try:
        dlg.show()
        qapp.processEvents()
        assert dlg.btn_library.isVisible() is scope.SHOW_TEMPLATE_LIBRARY
        assert dlg.btn_demo.isVisible() is scope.SHOW_SAMPLE_DATA
    finally:
        dlg.close()


def test_the_empty_state_only_mentions_a_button_that_is_there(window):
    """空白狀態那句話必須跟旁邊真的看得到的鈕一致 —— 兩個方向都問：
    鈕在，話要提；鈕不在，話不准提。"""
    mentioned = "sample data" in window.empty_state_hint.text().lower()
    assert mentioned is bool(scope.SHOW_SAMPLE_DATA)


def test_every_listed_template_says_what_it_does(window):
    """清單上顯示的是 recipe 自己的 ``description``，不是檔名。"""
    dlg = window.open_recipe_library()
    try:
        assert dlg.count() >= 1, "範本庫是空的"
        for info in dlg.entries():
            assert info["description"].strip(), (
                "%s 沒有 description —— 使用者看到的會是一個檔名，而他要決定"
                "的正是「哪一份最接近我的層」" % info["file"])
            assert not info["error"], info["error"]
    finally:
        dlg.close()


# --------------------------------------------------------------------------- #
# 驗收條件本身：開窗 → Templates → 選一份 → Run trial 跑得完
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def rsem_lot(tmp_path_factory):
    from make_sample_rsem import generate
    return generate(str(tmp_path_factory.mktemp("tpl")), n=6, seed=11)


def test_pick_a_template_and_run_it_without_touching_the_file_manager(
        window, rsem_lot):
    """**驗收條件**：全程只在 Studio 裡，跑得出結果。

    先載資料（那一步本來就要開檔案，不在這條驗收裡），然後 **Templates… →
    選 rsem 那一份 → Run trial**，一次都不必去找 recipe 檔在哪。
    """
    assert window.load_dataset_path(rsem_lot["klarf"], sync=True) is True

    dlg = window.open_recipe_library()
    try:
        rows = [i for i, e in enumerate(dlg.entries())
                if "rsem" in e["routes"]]
        assert rows, [e["routes"] for e in dlg.entries()]
        assert dlg.select(rows[0]) is True
        # 使用者按的那一顆「Load」—— 回傳的是載了哪一個檔。
        assert dlg.load_selected() == dlg.path_at(rows[0])
    finally:
        dlg.close()

    # 載進來的是真的那一份，而且它認得這批資料。
    assert window.model.node_order, "選了範本，畫布上卻什麼都沒有"
    assert window.model.kind == "rsem"

    assert window.run_trial(4, workers=1, sync=True) is True
    assert window.trial_results, "跑完了卻沒有結果"
    assert all(r.get("ok") for r in window.trial_results), \
        [r.get("error") for r in window.trial_results if not r.get("ok")]

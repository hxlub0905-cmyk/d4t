# -*- coding: utf-8 -*-
"""Studio 的存檔（2026-08-26 做回來）。

引擎那一半在 `tests/test_recipe_save.py`。這一份問的是**畫面上的那件事**：
按了會不會存、存的是不是使用者看到的那一份、標題列的星號會不會說謊、
關窗時第三個答案接得對不對（那一支在 `test_ui_f7_16_safety_net.py`）。

⚠ 一律走 :meth:`StudioWindow.save_recipe_path`，**不開檔案對話框** ——
headless 測試碰到 modal 對話框會永遠停在那裡（不是失敗），那種卡住最難查。
Qt import 全部 lazy，理由見 `test_ui_studio_smoke.py` 的模組說明。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_RECIPE = REPO / "tests" / "fixtures" / "recipes" / "die_to_die_basic.json"


def _load_qt() -> None:
    from PySide6.QtWidgets import QApplication  # noqa: F401

    from d4t.ui import studio as studio_mod  # noqa: F401
    from d4t.ui import theme as theme_mod  # noqa: F401

    from d4t.core.pipeline import Recipe  # noqa: F401

    globals().update(locals())


@pytest.fixture(scope="module")
def qapp():
    _load_qt()
    app = QApplication.instance() or QApplication(
        [sys.argv[0] if sys.argv else "t"])
    theme_mod.apply_theme(app)
    yield app
    app.processEvents()


@pytest.fixture()
def window(qapp):
    """**每個測試一個新視窗** —— 這一份測的是 dirty / 標題 / recipe_path
    這幾個帶狀態的東西，共用一個視窗的話前一支測試的存檔會影響下一支。"""
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.PROMPT_ON_CLOSE = False
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 存出來的就是畫面上那一份
# --------------------------------------------------------------------------- #
def test_what_lands_on_disk_is_what_is_on_the_canvas(window, tmp_path):
    """使用者在畫布上做的每一件事都要在檔案裡。

    這支測試刻意**經過磁碟**（不是 `to_recipe()` 比一比）：`to_recipe` 對不對
    在 smoke test 裡已經有人問了，這裡問的是「存檔這條路有沒有在中間掉東西」。
    """
    window.model.add_step("load_single")
    nid = window.model.add_step("glv_stats")
    window.model.set_param(nid, "source", "single")
    window.model.recipe_id = "my_pipeline"

    path = tmp_path / "mine.json"
    assert window.save_recipe_path(path) is True

    again = Recipe.load(path)
    assert again.recipe_id == "my_pipeline"
    assert again.routes[window.model.kind] == window.model.node_order
    assert again.nodes[nid].params["source"] == "single"


def test_an_edge_the_user_dragged_is_in_the_file(window, tmp_path):
    """**線也要存下去。**

    資料從哪來由線決定（鐵則 9／F9），所以一份沒有線的檔案是一份不一樣的
    pipeline —— 而它照樣跑得完（route 的排列還在，順序仍然對），只是每一張卡
    接到的東西可能不是使用者接的那一個。
    """
    src = window.model.add_step("load_single")
    dst = window.model.add_step("glv_stats")
    window.model.add_edge(src, dst, src_out="single", dst_in="source")

    path = tmp_path / "wired.json"
    assert window.save_recipe_path(path) is True
    got = {(e.src, e.src_out, e.dst, e.dst_in) for e in Recipe.load(path).edges}
    assert (src, "single", dst, "source") in got


def test_saving_an_empty_pipeline_is_refused_and_says_why(window, tmp_path):
    """空的 pipeline 沒東西可存 —— 而那要**講出來**，不是寫一份空檔案。"""
    assert window.model.node_order == []
    path = tmp_path / "empty.json"
    assert window.save_recipe_path(path) is False
    assert not path.exists()
    assert "empty" in window.status_text().lower()


def test_the_save_button_is_grey_until_there_is_something_to_save(window):
    """按鈕的前置條件不滿足 → 變灰 **並在 tooltip 說明原因**（推廣鐵則）。"""
    assert window.btn_save_recipe.isEnabled() is False
    assert "nothing to save" in window.btn_save_recipe.toolTip().lower()
    window.model.add_step("load_single")
    window._refresh_all()
    assert window.btn_save_recipe.isEnabled() is True


# --------------------------------------------------------------------------- #
# 2. 「還沒存」這件事要看得見
# --------------------------------------------------------------------------- #
def test_the_title_grows_a_star_while_there_are_unsaved_changes(window,
                                                                tmp_path):
    """星號是「還沒存」的唯一一個常駐訊號（每個編輯器都是這個慣例）。"""
    window.model.add_step("load_single")
    window._refresh_all()
    assert window.windowTitle().endswith("*")

    assert window.save_recipe_path(tmp_path / "t.json") is True
    assert not window.windowTitle().endswith("*")
    assert window.unsaved_changes() is False

    window.model.add_step("glv_stats")
    window._refresh_all()
    assert window.windowTitle().endswith("*"), "又改了就要再長回來"


def test_opening_a_recipe_does_not_look_unsaved(window):
    """剛載進來的 recipe **沒有**星號 —— 使用者什麼都還沒做。"""
    assert window.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
    assert window.unsaved_changes() is False
    assert not window.windowTitle().endswith("*")
    assert window.windowTitle().endswith(window.model.recipe_id)


# --------------------------------------------------------------------------- #
# 3. Ctrl+S 存回原檔，Ctrl+Shift+S 才問
# --------------------------------------------------------------------------- #
def test_ctrl_s_writes_back_to_the_file_it_came_from(window, tmp_path):
    """**有原檔就不要再問一次路徑。**

    存檔是每分鐘都在做的事（那正是它有快捷鍵的理由）；每一次都彈一個對話框
    出來，使用者就會不存。
    """
    path = tmp_path / "round.json"
    window.model.add_step("load_single")
    assert window.save_recipe_path(path) is True

    window.model.add_step("glv_stats")
    asked = []
    window._on_save_recipe_as = lambda: asked.append(1) or False
    assert window._on_save_recipe() is True
    assert asked == [], "已經有原檔了，不該再問路徑"
    assert len(Recipe.load(path).routes[window.model.kind]) == 2


def test_the_first_save_has_to_ask_where(window):
    """沒有原檔的時候 `Ctrl+S` 就是「另存」—— 那是唯一誠實的行為。"""
    window.model.add_step("load_single")
    assert window.recipe_path is None
    asked = []
    window._on_save_recipe_as = lambda: asked.append(1) or True
    assert window._on_save_recipe() is True
    assert asked == [1]


def test_both_shortcuts_are_registered(window):
    """`Ctrl+S` / `Ctrl+Shift+S` 兩個都要在，而且照 OS 慣例。"""
    keys = dict(studio_mod.StudioWindow.SHORTCUTS)
    assert keys["Ctrl+S"] == "save_recipe"
    assert keys["Ctrl+Shift+S"] == "save_recipe_as"


# --------------------------------------------------------------------------- #
# 4. 讀 → 改 → 存 → 再讀
# --------------------------------------------------------------------------- #
def test_a_round_trip_through_the_window_keeps_the_pipeline(window, tmp_path):
    """整條路走一遍：載一份 fixture、改一格、存、再載回來。

    ⚠ 這裡**不比整份檔案**：載入時 Studio 會把門檻翻成一棵判定樹
    （`_adopt_threshold_as_a_tree`），所以存回去的形狀本來就跟原檔不同 ——
    那是設計，見 `Recipe.save` 的說明。這支測試守的是**那個換法不會弄丟
    使用者的東西**。
    """
    assert window.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
    order = list(window.model.node_order)
    window.model.set_param("dn", "ksize", 5)

    path = tmp_path / "edited.json"
    assert window.save_recipe_path(path) is True
    assert window.load_recipe_path(str(path), sync=True) is True

    assert window.model.node_order == order
    assert window.model.nodes["dn"].params["ksize"] == 5
    assert window.recipe_path == str(path)
    assert window.unsaved_changes() is False


def test_a_threshold_recipe_saves_as_the_tree_the_user_is_looking_at(
        window, tmp_path):
    """**存出來的東西要跟畫面上一樣** —— 即使那不是他打開的那個形狀。

    `die_to_die_basic.json` 是一份門檻 recipe，而 Studio 載入時當場把它翻成
    一棵判定樹（F25，使用者：「二元門檻的 UI 完全拿掉」）。存檔存回門檻的話，
    使用者下次打開會看到一份跟他離開時**不一樣**的 recipe。

    2026-08-16 到 2026-08-26 之間這件事不可能發生（存不了檔），而
    `_adopt_threshold_as_a_tree` 的說明就是那樣寫的 —— 存檔回來之後那句話
    變成假的，這支測試是它的替代品。
    """
    assert window.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
    assert window.model.decide is not None, "載入時就該已經是一棵樹了"

    path = tmp_path / "as_tree.json"
    assert window.save_recipe_path(path) is True
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "decide" in raw
    # `score` 與 `decide` 並存是 `ambiguous-decision` —— 一份自己存出來的檔案
    # 不該把自己弄壞。
    assert str(raw["score"]["expr"]).strip() == ""
    assert Recipe.load(path).decide is not None


# --------------------------------------------------------------------------- #
# 5. 存不下去的時候
# --------------------------------------------------------------------------- #
def test_a_failed_save_says_so_and_does_not_pretend(window, tmp_path):
    """寫不進去（路徑指到一個資料夾）→ 回 False、狀態列講原因、**星號還在**。

    這一條的重點在最後那一句：把 dirty 清掉的話，使用者會以為存好了。
    """
    window.model.add_step("load_single")
    folder = tmp_path / "a_folder"
    folder.mkdir()
    assert window.save_recipe_path(folder) is False
    assert window.unsaved_changes() is True
    window._refresh_all()
    assert window.windowTitle().endswith("*")

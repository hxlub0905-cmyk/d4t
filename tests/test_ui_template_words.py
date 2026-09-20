# F117 G3／G4：範本庫上寫的是給人看的字，說明不被捲軸壓住（2026-09-20）。
"""**G3** 清單第一行是 `ebi_die_to_die`、第二行是 `route: ebi_patch` —— 兩個都
是 recipe JSON 的鍵，而使用者在那個清單上要決定的是「哪一份最接近我的層」。
右邊那塊還寫著 `score = (no score expression)`，讀起來像**這一份不會判定** ——
而它是用判定樹判定的。

**G4** 工具列底下那句說明被切、還壓著一條橫向捲軸。原因在版面樹上看不出來：
那句話被包進了 `fit_screen.scroll_row`，而那一支把高度鎖成「一列鈕 ＋ 捲軸」。
**鈕排不下要橫向捲，說明排不下要換行 —— 兩種相反的處理不能待在同一個容器裡。**
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from d4t.ui import scope                                 # noqa: E402
from d4t.ui import theme as theme_mod                    # noqa: E402
from d4t.ui.welcome import (                             # noqa: E402
    HEADLINE_MAX, RecipeLibraryDialog, list_recipe_files, read_recipe_info,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def _infos():
    return [read_recipe_info(p) for p in list_recipe_files()]


# --------------------------------------------------------------------------- #
# G3：清單上的兩行
# --------------------------------------------------------------------------- #
def test_the_list_leads_with_the_sentence_the_author_wrote():
    """第一行是**描述**，不是 `recipe_id`。

    使用者要決定的是「哪一份最接近我的層」，而 `ebi_die_to_die` 答不出那個
    問題 —— 那是 JSON 的鍵。
    """
    for info in _infos():
        head = RecipeLibraryDialog._item_text(info).splitlines()[0]
        assert head, info["file"]
        assert info["recipe_id"] not in head or info["description"]. \
            startswith(info["recipe_id"]), (info["file"], head)


def test_the_headline_is_short_enough_to_scan():
    """⚠ 出貨那三份的第一句有 150～400 個字 —— 整句放進清單就變成一面牆。

    那個清單上要做的是「掃過去挑一份」，完整的一段在右邊那一塊。
    """
    for info in _infos():
        head = RecipeLibraryDialog._item_text(info).splitlines()[0]
        assert len(head) <= HEADLINE_MAX + 1, (info["file"], len(head), head)


def test_a_question_keeps_its_question_mark():
    """出貨那三份裡真的有一份的第一句是問句 —— 沒有問號讀起來像被切斷了。"""
    heads = [RecipeLibraryDialog._item_text(i).splitlines()[0]
             for i in _infos()]
    assert any(h.endswith("?") for h in heads), heads


def test_the_second_line_says_the_data_not_the_route_key():
    """`route: ebi_patch` → `patch images`。"""
    for info in _infos():
        second = RecipeLibraryDialog._item_text(info).splitlines()[1]
        assert "route:" not in second, second
        for route in info["routes"]:
            assert scope.kind_word(route) in second, (info["file"], second)


def test_an_unknown_kind_is_not_guessed():
    """認不得的 kind 原樣回去 —— 猜一個漂亮名字會把線索蓋掉。"""
    assert scope.kind_word("some_new_kind") == "some_new_kind"
    assert scope.kind_word("") == ""


# --------------------------------------------------------------------------- #
# G3：右邊那一塊不准說「沒有判定」
# --------------------------------------------------------------------------- #
def test_a_tree_recipe_does_not_claim_it_has_no_decision():
    """⚠ `score = (no score expression)` 讀起來像這一份不會判定。

    走判定樹的 recipe **沒有分數表達式是正常的** —— 它用另一種方式判定。
    """
    for info in _infos():
        text = RecipeLibraryDialog._detail_text(info)
        if info["has_tree"]:
            assert "no score expression" not in text, info["file"]
            assert "decision tree" in text, info["file"]
            # 門檻跟著 score 走，一樣不准印（不然像是跟一個數字比大小）。
            assert "threshold =" not in text, info["file"]


def test_it_says_how_many_classes_the_tree_sorts_into():
    """「分成幾類」是使用者挑 recipe 時真的會問的事。"""
    got = [RecipeLibraryDialog._detail_text(i) for i in _infos()
           if i["has_tree"]]
    assert got, "前提：出貨的 recipe 裡有走判定樹的"
    assert any("classes" in t for t in got)


def test_a_broken_file_is_still_one_red_row(tmp_path):
    """鐵則 7 的精神：壞掉的檔案不准讓整個庫開不起來。"""
    bad = tmp_path / "broken.json"
    bad.write_text("{ not json", encoding="utf-8")
    info = read_recipe_info(bad)
    assert info["error"]
    assert "unreadable" in RecipeLibraryDialog._item_text(info)


# --------------------------------------------------------------------------- #
# G4：說明不在捲軸裡
# --------------------------------------------------------------------------- #
def test_the_tool_hint_lives_outside_the_scrolling_row(qapp):
    """⚠ **鈕排不下要橫向捲，說明排不下要換行。**

    兩種相反的處理待在同一個容器裡的下場，就是走查看到的那一幕：說明被切、
    而捲軸壓在它上面。
    """
    from d4t.ui.template_dialog import TemplateDialog

    dlg = TemplateDialog()
    dlg.resize(900, 700)
    try:
        dlg.show()
        qapp.processEvents()
        hint = dlg.tool_hint
        assert hint.wordWrap(), "說明不換行的話，搬出捲軸也沒有用"
        inside = [a for a in dlg.findChildren(QScrollArea)
                  if a.isAncestorOf(hint)]
        assert not inside, "說明還在捲軸裡 —— 它會被鎖住的高度切掉"
    finally:
        dlg.close()


def test_a_long_hint_grows_instead_of_being_clipped(qapp):
    from d4t.ui.template_dialog import TemplateDialog

    dlg = TemplateDialog()
    dlg.resize(900, 700)
    try:
        dlg.show()
        qapp.processEvents()
        one = dlg.tool_hint.height()
        dlg.tool_hint.setText(
            "Drag a box on the image, then use W and H to set its size and "
            "X and Y to say how many of them to lay down end to end across "
            "the pattern.")
        qapp.processEvents()
        assert dlg.tool_hint.height() > one, "長說明沒有長高 —— 它被切掉了"
    finally:
        dlg.close()

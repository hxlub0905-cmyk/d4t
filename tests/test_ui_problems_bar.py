# U2：「為什麼還不能跑」要有一個地方 — authored 2026-09-08.
"""紅紅的東西以前散在三個地方，**而沒有一個地方說「一共幾個、先修哪一個」**。

驗收條件：「一份有兩個 error 的 recipe，Problems 列數字正確；點第二項後
``selected_node()`` 等於那張卡」。這一支就是那兩句，加上三件會安靜壞掉的事：

* **常駐**：沒有問題的時候也要說一句（一條空白的橫條分不出「都好了」與
  「這個東西壞了沒在數」）；
* **順序**：error 一定排在 warning 前面 —— 使用者要的是「先修哪一個」，
  而那個答案不該取決於 lint 內部的產生順序；
* **同一份**：畫布上的警示點與這裡的計數走同一次 `validate()`。兩邊各算
  一次的那天，畫面上會有一張卡是紅的而清單說沒有問題。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication              # noqa: E402

from d4t.core.pipeline.recipe import Issue              # noqa: E402
from d4t.ui import problems_bar as pb                   # noqa: E402
from d4t.ui import studio as studio_mod                 # noqa: E402
from d4t.ui import theme as theme_mod                   # noqa: E402

sys.path.insert(0, str(REPO / "tests"))
from conftest import first_source                       # noqa: E402


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


def _issue(level, node_id="", title="t", detail="d", code="c"):
    return Issue(code=code, level=level, node_id=node_id or None,
                 title=title, detail=detail)


# --------------------------------------------------------------------------- #
# 純資料
# --------------------------------------------------------------------------- #
def test_the_count_reads_like_a_sentence():
    issues = [_issue("error"), _issue("error"), _issue("warning")]
    assert pb.counts_of(issues) == {"error": 2, "warning": 1, "info": 0}
    text = pb.summary_of(issues)
    assert "2 errors" in text and "1 warning" in text


def test_it_says_whether_you_can_run():
    """「1 warning」本身答不出使用者唯一的問題：*我現在到底能不能按 Run*。"""
    assert "fix the errors" in pb.summary_of([_issue("error")])
    assert "can still run" in pb.summary_of([_issue("warning")])


def test_no_problems_is_still_a_sentence():
    """一條空白的橫條分不出「都好了」與「這個東西壞了沒在數」。"""
    assert pb.summary_of([]) == "Nothing is blocking a run."


def test_errors_come_first_whatever_order_lint_produced_them_in():
    rows = pb.issue_rows([_issue("info", detail="i"), _issue("warning", detail="w"),
                          _issue("error", detail="e")])
    assert [r["level"] for r in rows] == ["error", "warning", "info"]


def test_within_one_level_lint_order_is_kept():
    """同一級照 pipeline 由上游到下游 —— 下游那幾條常常是上游那條的回音。"""
    rows = pb.issue_rows([_issue("error", detail="upstream"),
                          _issue("error", detail="downstream")])
    assert [r["detail"] for r in rows] == ["upstream", "downstream"]


# --------------------------------------------------------------------------- #
# 畫面
# --------------------------------------------------------------------------- #
def test_the_list_is_hidden_until_asked_and_empty_disables_the_button(qapp):
    bar = pb.ProblemsBar()
    assert bar.is_open() is False
    assert bar.btn_toggle.isEnabled() is False

    bar.set_issues([_issue("error", node_id="n1")])
    assert bar.btn_toggle.isEnabled() is True
    bar.toggle()
    assert bar.is_open() is True
    # 問題修完了 → 清單自己收起來（一個空的清單佔著版面沒有意義）。
    bar.set_issues([])
    assert bar.is_open() is False
    bar.deleteLater()


# --------------------------------------------------------------------------- #
# 一列長什麼樣（F118 第 4 步：J5 讀不完、J6 結論在後面）
# --------------------------------------------------------------------------- #
def test_a_row_puts_the_conclusion_first_and_the_details_underneath():
    """J6：**先講結論。** 使用者的第一個問題是「先修哪一個」。"""
    row = {"level": "error", "title": "“Denoise” has no input yet",
           "text": "“Denoise” · “Image streams” — Drag a line…",
           "node_id": "dn"}
    lines = pb.row_text(row).splitlines()
    assert len(lines) == 2
    assert lines[0] == "×  “Denoise” has no input yet"      # 結論，含級別記號
    assert "Drag a line" in lines[1]
    assert lines[1].startswith("  "), "第二行要縮排，不然兩行看起來是兩條"


def test_a_row_does_not_say_the_same_thing_twice():
    """`title` 跟 `text` 一樣的時候只有一行 —— 同一句話印兩次比較糟。

    沒搬去交結構的那幾條會走到這裡（`issue_line` 退回 `detail`，而有些
    lint 的 `detail` 本來就等於 `title`）。
    """
    same = {"level": "warning", "title": "one sentence", "text": "one sentence"}
    assert pb.row_text(same) == "⚠  one sentence"
    assert pb.row_text({"level": "info", "title": "", "text": "only text"})         == "i  only text"
    assert pb.row_text({"level": "info", "title": "only title", "text": ""})         == "i  only title"


def test_the_list_says_out_loud_that_a_row_takes_you_there(qapp):
    """J5 的「帶我去」：**那句話以前只在按鈕的 tooltip 上。**

    一個要把滑鼠停在別的地方才看得到的說明，等於沒有說明。而指不到任何一張
    卡的時候不要講 —— 一句做不到的提示比沒有提示糟。
    """
    bar = pb.ProblemsBar()
    bar.set_issues([_issue("error", node_id="a")])
    bar.set_open(True)
    # ⚠ **問 `isHidden()` 不是 `isVisible()`**：一個還沒有被 show 的視窗，
    # 裡面每一個 widget 的 `isVisible` 都是 False（`_open` 那個旗標存在的
    # 理由一模一樣）。`isHidden` 問的是「有沒有人叫它躲起來」。
    assert bar.hint.text() and bar.hint.isHidden() is False

    bar.set_issues([_issue("error")])            # 指不到卡片的那種
    assert bar.hint.text() == ""
    assert bar.hint.isHidden() is True
    bar.deleteLater()


def test_a_long_row_wraps_instead_of_scrolling_sideways(qapp):
    """走查看到的那一列**要捲到右邊才讀得完** —— 而讀不完等於沒有。"""
    from PySide6.QtCore import Qt

    bar = pb.ProblemsBar()
    assert bar.list.wordWrap() is True
    assert bar.list.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    bar.deleteLater()


def test_clicking_a_row_says_which_card(qapp):
    bar = pb.ProblemsBar()
    seen = []
    bar.problem_activated.connect(seen.append)
    bar.set_issues([_issue("error", node_id="a"), _issue("error", node_id="b")])
    assert bar.activate_row(1) is True
    assert seen == ["b"]
    bar.deleteLater()


# --------------------------------------------------------------------------- #
# 接上主視窗（驗收條件本身）
# --------------------------------------------------------------------------- #
def test_two_errors_show_up_and_the_second_one_selects_its_card(window):
    """**驗收條件**：兩個 error → 數字對；點第二項 → 選中那張卡。

    造法是使用者真的會走到的那一種：兩張需要上游影像的卡，一條線都沒有拉
    （F10 之後剛加進來的卡就是這樣）——lint 會各報一條 ``missing-image``。
    """
    first_source(window)
    window._on_add_requested("glv_stats")
    window._on_add_requested("cd_measure")

    rows = [r for r in window.problems.rows()
            if r["level"] == "error" and r["node_id"]]
    assert len(rows) >= 2, window.problems.rows()
    counts = window.problems.counts()
    assert counts["error"] == len([r for r in window.problems.rows()
                                   if r["level"] == "error"])
    assert "%d errors" % counts["error"] in window.problems.summary_text()

    window.problems.activate_row(
        window.problems.rows().index(rows[1]))
    assert window.selected_node == rows[1]["node_id"]


def test_the_bar_and_the_canvas_badges_come_from_the_same_lint_run(window):
    """兩邊各算一次的那天，畫布是紅的而清單說沒有問題 —— 而且不會有人發現。"""
    first_source(window)
    window._on_add_requested("glv_stats")
    badge_nodes = set(window._node_problems())
    listed = {r["node_id"] for r in window.problems.rows() if r["node_id"]}
    assert badge_nodes <= listed, (badge_nodes, listed)


def test_a_clean_pipeline_says_so(window):
    """開窗（空畫布）就該講得出「現在沒有東西擋著」。"""
    assert "Nothing is blocking" in window.problems.summary_text() \
        or window.problems.counts()["error"] == 0


# --------------------------------------------------------------------------- #
# 狀態列的歷史（U2 的後半：「status bar 另給一份可展開的歷史 log」）
# --------------------------------------------------------------------------- #
def test_the_status_bar_keeps_what_it_said(window):
    """**下一句話就把上一句蓋掉**，而上一句可能是唯一講出「沒成功」的地方。"""
    window._status("first thing")
    window._status("Could not save: PermissionError", "error")
    lines = window.status_history.lines()
    texts = [r["text"] for r in lines]
    assert "first thing" in texts and any("PermissionError" in t for t in texts)
    # 級別要留著 —— 一份看不出哪幾句是紅字的歷史，跟沒有差不多。
    assert [r["level"] for r in lines if "PermissionError" in r["text"]] \
        == ["error"]


def test_the_same_sentence_twice_in_a_row_is_kept_once(window):
    """刷新一次面板會把同一則訊息再說一遍 —— 40 次同一句等於沒有歷史。"""
    before = len(window.status_history.lines())
    for _ in range(5):
        window._status("same message over and over")
    assert len(window.status_history.lines()) == before + 1


def test_the_button_says_how_many_and_is_dead_when_empty(qapp):
    from d4t.ui.status_log import StatusHistory

    btn = StatusHistory()
    assert btn.isEnabled() is False
    assert btn.open_history() is None      # 沒東西就不要開一個空視窗
    btn.add("something happened")
    assert btn.isEnabled() is True
    assert "(1)" in btn.text()
    btn.deleteLater()


def test_the_history_button_is_really_on_the_status_bar(window):
    """**`statusBar()` 會自己建一個，而 `setStatusBar` 把它整個換掉。**

    第一版就是這樣壞的：那顆鈕掛在一個已經沒有人看得到的 `QStatusBar` 上，
    而畫面上沒有任何錯誤 —— 只是那顆鈕不見了。這一條問的正是「它真的在那裡
    嗎」，不是「有沒有建出來」。
    """
    assert window.status_history in window.statusBar().children()

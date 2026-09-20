# F117 H2／H3／I12：同一件事只有一種長相（2026-09-20）。
"""三條走查、同一句話：**畫面上同一種東西長成兩個樣子，使用者就要學兩次。**

* **H2** 底部**兩條**狀態列 —— 一行字 ＋ 右邊一顆鈕，兩條長得一模一樣，而它們
  講的是兩件不同的事。另外那一句「跑完了還沒寫」在 Results 裡又出現一次，
  而它叫使用者去他**已經在**的地方。
* **H3** 空白畫面上三種資料的說明各有 115～169 個字，在那一欄折成 7～9 行 ——
  1366×768 上那一塊看得到的只有 160 px，所以三列全部要捲。
* **I12** 對話框主要動作兩種顏色 —— 不是有人選了兩種，是**兩種來路**：自己
  `QPushButton` 的都標了 `primary`，`QDialogButtonBox` 生出來的沒有人去標。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (                        # noqa: E402
    QApplication, QDialogButtonBox,
)

from d4t.ui import scope, wording                      # noqa: E402
from d4t.ui import theme as theme_mod                  # noqa: E402
from d4t.ui.buttons import mark_primary                # noqa: E402
from d4t.ui.problems_bar import ProblemsBar            # noqa: E402
from d4t.ui.results import extra_only                  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


# --------------------------------------------------------------------------- #
# H2：第二條狀態列只在它有話要說的時候出現
# --------------------------------------------------------------------------- #
def test_the_problems_bar_disappears_when_there_is_nothing_to_say(qapp):
    """⚠ `Nothing is blocking a run.` 是一句**永遠不會帶來消息**的話。

    它佔著畫面最底下 26 px 常駐著，而旁邊 35 px 就是狀態列 —— 兩條長得一樣的
    橫條，使用者分不出哪一條在講什麼。
    """
    bar = ProblemsBar()
    try:
        bar.set_issues(())
        assert not bar.isVisible() and bar.isHidden()
    finally:
        bar.deleteLater()


def test_it_comes_back_the_moment_there_is_a_problem(qapp):
    """**反向測試** —— 收起來不等於弄丟。"""
    from d4t.core.pipeline.recipe import Issue

    bar = ProblemsBar()
    try:
        bar.set_issues((Issue(code="x", level="error", node_id="a",
                              title="Bad", detail="something is wrong"),))
        assert not bar.isHidden()
        assert bar.rows()
        bar.set_issues(())
        assert bar.isHidden()
    finally:
        bar.deleteLater()


def test_the_two_bars_are_still_two_different_things():
    """⚠ **沒有把它們併成一條，而那是刻意的。**

    問題列講的是**常駐的狀態**（現在能不能跑），狀態列講的是**剛剛發生了
    什麼**。併成一條的話，一句「Run finished」會把一條擋著跑的錯誤洗掉。
    這一條釘住那個決定：問題列還是自己的 widget。
    """
    assert ProblemsBar.__name__ == "ProblemsBar"
    assert hasattr(ProblemsBar, "set_issues")


# --------------------------------------------------------------------------- #
# H2：那句話不要在 Results 裡再講一次
# --------------------------------------------------------------------------- #
WRITE = ("Run finished: 24 defects (24 ok, 0 failed) in 0.1 s"
         "  ·  Run only - nothing written yet. When the numbers look right, "
         "press “Write outputs” in Results to let the 2 Output cards write.")


def test_results_does_not_tell_you_to_go_where_you_already_are():
    """⚠ 讀到它的人**就在 Results**，那顆鈕就在他上面。"""
    assert "nothing written yet" not in extra_only(WRITE)
    assert extra_only(WRITE) == ""


def test_the_rest_of_the_message_survives():
    """⚠ 剪掉中間一句，前後**不准跟著消失**。"""
    got = extra_only(WRITE + "  ·  2 warnings on the canvas.")
    assert got == "2 warnings on the canvas.", got


def test_no_orphan_separator_is_left_behind():
    """⚠ 一個孤零零的分隔點在句首讀起來像畫面壞了。"""
    got = extra_only(WRITE + "  ·  2 warnings on the canvas.")
    assert not got.startswith("·") and not got.startswith(" ")


def test_being_stopped_still_gets_said():
    """⚠ 「你叫我停的時候跑到哪裡」不是重複的 —— 工具列那一行講不出這件事。"""
    got = extra_only("Run stopped: 5 of 24  ·  Run only - nothing written "
                     "yet. press x to let the 1 Output card write.")
    assert got.startswith("Stopped part-way")


# --------------------------------------------------------------------------- #
# H3：一句話，全文在 tooltip
# --------------------------------------------------------------------------- #
def test_the_empty_screen_says_one_sentence_per_kind(qapp):
    """⚠ 使用者站在那個畫面前面時手上已經有檔案了 —— 他要回答的是「我這一堆
    算哪一種」，那是一句話答得完的問題。"""
    for src in scope.INPUT_SOURCES:
        head = wording.headline(src.what)
        assert head, src.key
        assert len(head) <= wording.HEADLINE_MAX + 1, (src.key, len(head))
        assert len(head) < len(src.what), (src.key, "這一句根本沒有被收短")


def test_the_full_text_is_one_hover_away(qapp):
    """⚠ 收短不是刪掉 —— 副檔名、要不要 KLARF 那些細節還在。"""
    from d4t.ui import studio as studio_mod
    from PySide6.QtWidgets import QLabel

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        win.resize(1366, 768)
        labels = [w for w in win.empty_state.findChildren(QLabel)
                  if w.text().startswith(("A KLARF", "A folder"))]
        assert len(labels) == len(scope.INPUT_SOURCES), len(labels)
        for lab in labels:
            assert lab.toolTip(), lab.text()
            assert len(lab.toolTip()) > len(lab.text())
    finally:
        win.close()


def test_the_block_got_shorter_on_a_fab_screen(qapp):
    """⚠ **那個數字是量出來的。**

    修之前這一塊是 623 px 高，而 1366×768 上看得到的只有 ~170 —— 三列說明
    全部要捲。現在是 340 上下，前兩列不必捲就看得到。

    340 是門檻不是目標：它擋的是「有人又把說明寫回一整段」。
    """
    from d4t.ui import studio as studio_mod

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        win.resize(1366, 768)
        win.show()
        qapp.processEvents()
        assert win.empty_state.height() <= 360, win.empty_state.height()
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# I12：主要動作只有一種長相
# --------------------------------------------------------------------------- #
def test_the_accept_button_gets_the_primary_look(qapp):
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    try:
        btn = mark_primary(box)
        assert btn is not None and btn.objectName() == "primary"
        other = box.button(QDialogButtonBox.Cancel)
        assert other.objectName() == "", "只標一顆 —— 兩顆都藍等於沒有主要動作"
    finally:
        box.deleteLater()


def test_a_close_only_box_has_no_primary(qapp):
    """⚠ 看一看就關掉的那種**沒有主要動作**。

    硬標一顆藍的，等於把「離開」講成「完成」。
    """
    box = QDialogButtonBox(QDialogButtonBox.Close)
    try:
        assert mark_primary(box) is None
        assert all(b.objectName() == "" for b in box.buttons())
    finally:
        box.deleteLater()


def test_every_accept_box_in_the_ui_goes_through_the_helper():
    """**反向測試** —— 下一個對話框不准再長出第三種長相。

    ⚠ 判準是「這個檔案裡有 `QDialogButtonBox(` 就要有 `mark_primary(`」，而
    **只有 `Close` 的 box 不算**：它沒有要標的東西。那幾支列在下面，每一支
    附一句為什麼。
    """
    CLOSE_ONLY = {
        "fields.py": "曲線編輯器：看一看、改一改，關掉就生效",
        "lattice_dialog.py": "格線對不對是用看的，沒有「確定」這個動作",
    }
    bad = []
    for path in sorted((REPO / "d4t" / "ui").glob("*.py")):
        src = path.read_text(encoding="utf-8")
        if "QDialogButtonBox(" not in src:
            continue
        if path.name in CLOSE_ONLY:
            assert "QDialogButtonBox.Ok" not in src, \
                "%s 現在有 Ok 了 —— 它不該再列在 CLOSE_ONLY 上" % path.name
            continue
        if "QDialogButtonBox.Ok" in src and "mark_primary(" not in src:
            bad.append(path.name)
    assert not bad, "這幾支的主要動作沒有標：%s" % bad


def test_the_helper_lives_where_nothing_can_import_it_wrongly():
    """`buttons.py` 只 import Qt 與 `theme`／`strings`（它是最底層那一塊）。"""
    src = (REPO / "d4t" / "ui" / "buttons.py").read_text(encoding="utf-8")
    # ⚠ `from . import strings` 的 `module` 是 **None**（名字在 `names` 裡），
    # 而 `from .theme import TOKENS` 的 `module` 才是 `"theme"`。只看其中一邊
    # 的話，這條測試會對半數的 import 視而不見。
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if not isinstance(n, ast.ImportFrom) or n.level != 1:
            continue
        mods |= ({n.module} if n.module
                 else {a.name for a in n.names})
    assert mods <= {"strings", "theme"}, mods

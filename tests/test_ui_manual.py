# F117 K1：使用手冊在 app 裡打得開（2026-09-20）。
"""走查那一列寫的是「`docs/USING-*.md` 只在 repo 裡，廠內使用者不會去翻」。

那句話底下是兩個不同的問題：**他不知道有這份東西**，以及**他打不開**
（公司機上不保證有任何一個看得懂 `.md` 的程式）。所以入口長在用得到它的那張
卡上，而內容是 d4t 自己畫的。

這一支最重要的兩條在最底下：**每一份手冊都有人連得到**（反向測試 —— 新加一份
而沒有任何一張卡指過去的話，它會跟現在一樣沒有人看得到），以及**連結不會把
檔案交給作業系統**（那是一台受限的機器上會失敗得很難看的一步）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl                        # noqa: E402
from PySide6.QtWidgets import QApplication             # noqa: E402

from d4t.core import steps as _steps                   # noqa: E402,F401
from d4t.core.pipeline.step import REGISTRY            # noqa: E402
from d4t.ui import manual                              # noqa: E402
from d4t.ui import theme as theme_mod                  # noqa: E402
from d4t.ui.param_form import ParamForm                # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def elsewhere(tmp_path):
    """把手冊目錄換掉（覆寫點 —— 測試不准依賴真正的那一份會不會在）。"""
    old = manual.DOCS_DIR
    manual.DOCS_DIR = tmp_path
    try:
        yield tmp_path
    finally:
        manual.DOCS_DIR = old


def _cards_with_manuals():
    return {k: c.manual for k, c in REGISTRY.items() if getattr(c, "manual", "")}


# --------------------------------------------------------------------------- #
# 1. 卡片宣告的那個檔案要真的在
# --------------------------------------------------------------------------- #
def test_every_card_manual_is_a_file_that_ships():
    """⚠ 一個指向不存在檔案的宣告，在畫面上是「什麼都沒有」—— 沒有人會發現。"""
    assert _cards_with_manuals(), "前提：至少有一張卡宣告了手冊"
    for key, name in sorted(_cards_with_manuals().items()):
        assert manual.path_for(name) is not None, (key, name)


def test_the_manual_is_carried_by_the_bundle():
    """⚠ 公司機拿程式碼的唯一路徑是 bundle —— 手冊不在清單裡就等於沒有。"""
    listed = (REPO / "tools" / "FILELIST.txt").read_text(encoding="utf-8")
    for name in sorted(set(_cards_with_manuals().values())):
        assert "docs/%s" % name in listed, name


def test_every_manual_has_somebody_pointing_at_it():
    """**反向測試** —— 這一條比上面兩條都重要。

    `docs/` 裡多一份手冊而沒有任何一個地方連得到，它就跟走查抱怨的那一刻
    一模一樣：東西在，而使用者不知道。

    ⚠ `USING-SIMGEN.md` 不屬於任何一張卡（它講的是那個產模擬資料的視窗），
    所以這裡把那個視窗也算進來 —— **它是唯一的例外，而例外要指得出名字。**
    """
    from d4t.ui.gc_generator import MANUAL as SIMGEN_MANUAL

    reachable = set(_cards_with_manuals().values()) | {SIMGEN_MANUAL}
    on_disk = {name for name, _ in manual.manuals()}
    assert on_disk, "前提：docs/ 底下有手冊"
    assert on_disk - reachable == set(), \
        "這幾份手冊沒有任何入口：%s" % sorted(on_disk - reachable)


# --------------------------------------------------------------------------- #
# 2. 只讀得到 docs/ 裡的東西
# --------------------------------------------------------------------------- #
def test_it_only_ever_looks_inside_the_docs_folder(elsewhere):
    """⚠ 卡片宣告的是一個字串，而一個字串不該有本事讀到任何別的地方。"""
    (elsewhere / "USING-X.md").write_text("# X\n", encoding="utf-8")
    assert manual.path_for("USING-X.md") is not None
    assert manual.path_for("../../CLAUDE.md") is None
    assert manual.path_for("C:/Windows/win.ini") is None
    assert manual.path_for("") is None


def test_a_missing_manual_is_not_a_crash(elsewhere):
    assert manual.path_for("USING-NOPE.md") is None
    assert manual.title_of("USING-NOPE.md") == "USING-NOPE.md"
    assert manual.manuals() == []


def test_the_title_comes_from_the_file_and_follows_the_folder(elsewhere):
    """⚠ 標題有快取，而 `DOCS_DIR` 是可以換的 —— 換了要跟著換答案。"""
    (elsewhere / "USING-X.md").write_text("# The X manual\n", encoding="utf-8")
    assert manual.title_of("USING-X.md") == "The X manual"
    manual.DOCS_DIR = None
    assert manual.title_of("USING-X.md") == "USING-X.md"


# --------------------------------------------------------------------------- #
# 3. 參數區那一行
# --------------------------------------------------------------------------- #
def test_only_a_card_with_a_manual_shows_the_link(qapp):
    """⚠ 一個每張卡都在、而多數時候沒東西的連結，第三次之後沒有人再點了。"""
    form = ParamForm()
    form.show()
    try:
        with_manual = sorted(_cards_with_manuals())[0]
        form.set_step(REGISTRY[with_manual].describe(), {})
        assert form._manual_link.isVisibleTo(form)
        assert form.manual() == REGISTRY[with_manual].manual

        without = next(k for k, c in REGISTRY.items()
                       if not getattr(c, "manual", ""))
        form.set_step(REGISTRY[without].describe(), {})
        assert not form._manual_link.isVisibleTo(form)
        assert form.manual() == ""
        assert form._manual_link.text() == "", \
            "上一張卡的連結字留在那裡 —— 藏起來不等於清掉"
    finally:
        form.deleteLater()


def test_the_link_goes_away_when_nothing_is_selected(qapp):
    form = ParamForm()
    form.show()
    try:
        form.set_step(REGISTRY[sorted(_cards_with_manuals())[0]].describe(), {})
        form.set_step(None, {})
        assert not form._manual_link.isVisibleTo(form)
        assert form.manual() == ""
    finally:
        form.deleteLater()


def test_no_link_when_the_docs_did_not_travel(qapp, elsewhere):
    """⚠ 點下去說「找不到」的連結比沒有連結更糟。

    它每一次都在提醒使用者這個工具少了一塊，而他做不了任何事。
    """
    form = ParamForm()
    form.show()
    try:
        form.set_step(REGISTRY[sorted(_cards_with_manuals())[0]].describe(), {})
        assert not form._manual_link.isVisibleTo(form)
    finally:
        form.deleteLater()


# --------------------------------------------------------------------------- #
# 4. 視窗自己
# --------------------------------------------------------------------------- #
def test_the_dialog_renders_the_markdown(qapp):
    name = sorted(set(_cards_with_manuals().values()))[0]
    dlg = manual.ManualDialog(name)
    try:
        text = dlg.view.toPlainText()
        assert len(text) > 200, "手冊是空的 —— Markdown 沒有被畫出來"
        assert "# " not in text.splitlines()[0], \
            "第一行還是 Markdown 原文 —— setMarkdown 沒有生效"
        assert dlg.windowTitle() == manual.title_of(name)
        assert str(manual.path_for(name)) in dlg.where.text()
    finally:
        dlg.deleteLater()


def test_it_says_where_it_looked_when_the_file_is_gone(qapp, elsewhere):
    """⚠ 「打不開」跟「我找錯地方」是兩件事，而使用者要回報的正是那條路徑。"""
    dlg = manual.ManualDialog("USING-NOPE.md")
    try:
        assert "not installed" in dlg.view.toPlainText()
        assert str(elsewhere) in dlg.where.text()
    finally:
        dlg.deleteLater()


def test_a_link_to_another_manual_opens_in_the_same_window(qapp):
    names = sorted(set(_cards_with_manuals().values()))
    if len(names) < 2:
        pytest.skip("只有一份手冊，沒有「另一份」可以跳")
    dlg = manual.ManualDialog(names[0])
    try:
        dlg._on_link(QUrl("../docs/%s" % names[1]))
        assert dlg.name() == names[1]
        assert dlg.windowTitle() == manual.title_of(names[1])
    finally:
        dlg.deleteLater()


def test_it_never_hands_a_link_to_the_operating_system(qapp):
    """⚠ **這一條守的是一個不存在的呼叫。**

    `QDesktopServices.openUrl` 會把一個連結交給我們不知道是什麼的程式 ——
    而使用者按的時候以為自己只是在讀一份說明。手冊裡真的有指向原始碼與外部
    網址的連結，所以這件事是會發生的，不是假想。
    """
    import ast

    src = (REPO / "d4t" / "ui" / "manual.py").read_text(encoding="utf-8")
    # ⚠ 用 `ast`，不是 `in src`：第一版是 substring，而這個模組的**註解裡**
    # 就寫著為什麼不准呼叫它 —— 於是那條測試咬了自己的說明。
    # 一條會誤報的測試最後一定會被關掉，而關掉的那天它守的東西也跟著沒了。
    names = {n.attr for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
    assert "openUrl" not in names
    assert "QDesktopServices" not in names

    name = sorted(set(_cards_with_manuals().values()))[0]
    dlg = manual.ManualDialog(name)
    try:
        assert not dlg.view.openLinks()
        assert not dlg.view.openExternalLinks()
        # 外部連結按下去：什麼都不該發生（留在原來那一份）。
        dlg._on_link(QUrl("https://example.invalid/x"))
        dlg._on_link(QUrl("../../d4t/core/steps/cd.py"))
        assert dlg.name() == name
    finally:
        dlg.deleteLater()

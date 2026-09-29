# F117 D4：判定那一段的五個字，有一張表說它們怎麼串起來（2026-09-20）。
"""走查記的是「Decision / Verdict / bin / class / score 多種叫法」。

⚠ **掃過整個畫面之後：沒有亂用的同義詞。** `grade`／`bucket`／`judgement`
一個都沒有出現，五個字各自都用得很一致。真正缺的是**沒有任何地方告訴使用者
它們怎麼串起來** —— 而它們在同一個畫面上同時出現。

所以這一輪加的不是一次重新命名，是**一張看得到的表**（歡迎頁上五行）。
這一支守兩件事：那張表在、而且畫面上沒有第六個字偷偷長出來。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication            # noqa: E402

from d4t.ui import theme as theme_mod                 # noqa: E402
from d4t.ui.welcome import GLOSSARY, WelcomeDialog    # noqa: E402

#: 這五個字的**同義詞**。畫面上出現任何一個，就是有人自己發明了第六種叫法
#: —— 而使用者要在腦裡多維護一張對照表。
#:
#: ⚠ **整個字比對**（``\b…\b``）而不是 substring：第一版用 substring，
#: 於是 `upgraded the file's shape` 被 `grade` 咬中了。一條會誤報的測試最後
#: 一定會被關掉，而關掉的那一天它守的東西也跟著沒了。
#:
#: ⚠ **`category` 不在這張表上**：這個 repo 裡它指的是**卡片的分類**
#: （image／algo／adc），跟判定那一段沒有關係。名字像不代表是同一件事。
FORBIDDEN = ("bucket", "grade", "grades", "judgement", "judgment",
             "classification")

CJK = re.compile(r"[　-鿿＀-￯]")
STRING = re.compile(r'"([^"\n]{4,200})"')


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


# --------------------------------------------------------------------------- #
# 1. 那張表本身
# --------------------------------------------------------------------------- #
def test_the_table_covers_the_words_the_screen_still_uses():
    """走查點名了五個字；F122 期 3 收掉了第五個（「verdict」講的就是一顆 defect
    的 class —— 畫面上那一格現在也叫 Class）。"""
    assert [name for name, _ in GLOSSARY] == [
        "score", "decision", "class", "bin"]
    assert "Verdict" not in " ".join(text for _, text in GLOSSARY)


def test_it_reads_in_the_order_you_meet_them():
    """⚠ **順序不是字母序**：分數 → 問題 → 類別 → 編號 → 結果。

    這張表要讀起來像一句話 —— 照字母排的話 `bin` 會排在 `class` 前面，
    而「編號」在「類別」之前講不通。
    """
    names = [name for name, _ in GLOSSARY]
    assert names != sorted(names)
    assert names.index("class") < names.index("bin")
    assert names.index("score") < names.index("decision")


def test_every_line_points_at_something_on_screen():
    """⚠ **每一句都要講「它在畫面上是哪一個東西」，不是給一個定義。**

    一個不寫 code 的製程工程師要的是「我看到的那一格叫什麼」。
    """
    where = ("canvas", "tree", "KLARF", "chip", "cards", "yourself",
             "expression", "preview")
    for name, line in GLOSSARY:
        assert line.endswith("."), name
        assert any(w in line for w in where), (name, line)


# --------------------------------------------------------------------------- #
# 2. 它真的在畫面上
# --------------------------------------------------------------------------- #
def test_the_welcome_page_shows_it(qapp):
    dlg = WelcomeDialog()
    try:
        text = dlg.glossary.text()
        for name, _ in GLOSSARY:
            assert "<b>%s</b>" % name in text, name
    finally:
        dlg.deleteLater()


# --------------------------------------------------------------------------- #
# 3. 不准長出第六種叫法
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("word", FORBIDDEN)
def test_nobody_invents_a_sixth_name(word):
    """⚠ 這一條比那張表重要：表可以補，而一個偷偷長出來的同義詞沒有人會發現。

    只掃英文字串（中文的註解是寫給開發者的，F118 §3 的同一條界線）。
    """
    hits = []
    for root in ("d4t/ui", "d4t/core"):
        for path in sorted((REPO / root).rglob("*.py")):
            for i, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                for m in STRING.finditer(line):
                    text = m.group(1)
                    if CJK.search(text) or not re.search(r"[a-zA-Z]{3}", text):
                        continue
                    if re.search(r"\b%s\b" % word, text, re.I):
                        hits.append("%s:%d  %s"
                                    % (path.relative_to(REPO).as_posix(), i,
                                       text[:70]))
    assert not hits, "畫面上出現了 %r —— 五個字的表在 `welcome.GLOSSARY`：\n  %s" % (
        word, "\n  ".join(hits[:8]))


def test_the_scan_would_actually_catch_one():
    """⚠ **反向測試** —— 而這一條是付了學費才加的。

    第一版的 `\b` 在編輯的路上被吃掉了，regex 變成 ``r"\x08grade\x08"`` ——
    **它永遠不會match，所以整組測試都是綠的**。一條只會綠的測試比沒有測試
    糟：它讓人以為那件事有人在看。

    這裡把一句真的違規的話餵回去，確認判準會咬它；順便確認它**不會**咬
    `upgraded`（那就是第一版誤報的那個字）。
    """
    assert re.search(r"\bbucket\b", "drop it in the bucket", re.I)
    assert not re.search(r"\bgrade\b", "upgraded the file's shape", re.I)

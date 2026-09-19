# F117 I13：使用者面的字只用一套符號（2026-09-20）。
"""走查看到的：`—`、` - `、`->`、`→` 四種混在一起，歡迎頁寫的是
``Score -> bin -> write back``，而別的地方寫 ``→``。

**混用本身不是大事，但它是「這個畫面沒有人整體看過一遍」的味道** —— 而那正是
一個不寫 code 的製程工程師對一個工具的第一印象。

⚠ **這一支只看英文字串。** 中文的註解與 docstring 是寫給開發者的，那一側愛用
哪個破折號都行（F118 §3 劃的是同一條界線：畫面是給人讀的，程式碼的註解是給
下一個開發者讀的）。

⚠ **為什麼是 `→` 而不是 `->`**：`→`（U+2192）在 WGL4 裡，Segoe UI 蓋得到
—— 而 F7-23 擋的是 Geometric Shapes（`●`）與 Dingbats（`✕`）那兩族，不是
箭頭。repo 裡本來就有 25 處在用 `→`，8 處用 `->`：少數服從多數，而且
`->` 讀起來是程式碼。

⚠ **這一支不管「哪些符號安全」** —— 那是 F7-23 的工作，而且它問得比這裡準
（它看的是真的畫上按鈕的那些字）。這裡只管**同一件事有沒有兩種寫法**。
鍵盤提示裡的 `↑` `↓`、樹上那個 `↳` 都是合法的，它們各自講的是別的事。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

#: 掃哪些檔案 —— `d4t/ui` 全部，加上 core 裡**會被印給使用者看**的那幾支
#: （卡片的 help、演算法的 notes 都會出現在畫面上）。
ROOTS = ("d4t/ui", "d4t/core")

CJK = re.compile(r"[　-鿿＀-￯]")
STRING = re.compile(r'"([^"\n]{4,200})"')

#: 不准出現在使用者面英文字串裡的寫法 → 該用什麼。
BANNED = {
    "->": "→（U+2192，repo 的多數派；`->` 讀起來是程式碼）",
    " -- ": "—（em dash）",
    "=>": "→",
}


def _user_strings():
    """``(檔名, 行號, 字串)`` —— 看起來是給使用者看的英文字串。

    判準刻意寬鬆（沒有中文 ＋ 有三個以上連續英文字母），因為這一支要問的是
    「這個 repo 的畫面用字一致嗎」，而不是「這一行到底有沒有被 setText」。
    誤抓一句開發者的英文註解，代價只是那一句也要照規矩寫。
    """
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            for i, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                for m in STRING.finditer(line):
                    text = m.group(1)
                    if CJK.search(text) or not re.search(r"[a-zA-Z]{3}", text):
                        continue
                    yield (path.relative_to(REPO).as_posix(), i, text)


@pytest.mark.parametrize("bad", sorted(BANNED))
def test_the_screen_uses_one_arrow_and_one_dash(bad):
    """**一種意思一個符號。** 四種混用是「沒有人整體看過一遍」的味道。"""
    hits = ["%s:%d  %s" % (f, i, t)
            for f, i, t in _user_strings() if bad in t]
    assert not hits, "%r 該寫成 %s：\n  %s" % (
        bad, BANNED[bad], "\n  ".join(hits[:12]))


def test_it_would_have_caught_the_one_the_review_found():
    """⚠ **反向測試**：上面那條真的抓得到走查看到的那一句嗎。

    一條只會綠的測試等於沒有測試 —— 這裡把那句話餵回去，確認判準會咬它。
    """
    sample = "Score -> bin -> write back to KLARF"
    assert any(b in sample for b in BANNED)
    assert not CJK.search(sample) and re.search(r"[a-zA-Z]{3}", sample)

# 文件之間的指標不准爛掉 — authored 2026-08-24（全專案 review 的 F6）。
"""**`CLAUDE.md` §0 第一句話是「同一件事只寫在一個地方」，而做到那件事的手段
是「其他地方連過來」—— 所以連結爛掉的代價，正好等於那條規矩的價值。**

這個 repo 用測試守住了不得 import Qt（`test_no_qt.py`）、不得有廠內識別碼
（`test_no_real_fab_data.py`）、搬運清單不得過期（`test_offline_tools.py`）、
每張卡都要有 help（`test_card_invariants.py`）、3.9 語法（同上）——
**唯獨沒有任何東西守著文件之間的交叉引用**。於是它們漂了：2026-08-24 這一輪
掃出 8 條指向不存在章節的引用，全部是 `CLAUDE.md §7/§8/§9` —— 那些內容早就
搬進 `PITFALLS.md` / `FAB-VALIDATION.md` / `ROADMAP.md` 了，**指標沒跟著搬**。

這一份鎖住兩件事：

1. 每一條相對連結指到的檔案要存在；
2. 每一條 ``<檔名> §N`` 指到的章節要存在。

⚠ **它抓不到「章節存在、但內容不對」** —— `AGENTS.md` 曾經寫「開發流程見
`CLAUDE.md` §6」而開發流程在 §4（§6 是 vendoring 對照表）。那種只有人看得出來。
所以這一份是**下限**，不是保證。

⚠ `docs/history/` 底下是**封存**（做完不再改的計畫書、按月的 SESSION_LOG）。
它們寫的時候是對的，而封存的意思正是「不再跟著現在的結構動」——
所以那些檔案只驗自己內部的相對連結，不驗 § 引用。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

#: 有編號章節、會被別人用 ``§N`` 指的那幾份。
NUMBERED = ("CLAUDE.md", "AGENTS.md")

#: 封存區：只驗檔案連結，不驗 § 引用（見檔頭）。
ARCHIVE = "history"

_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
#: ``CLAUDE.md §4`` / ``` `AGENTS.md` §3.5 ``` / ``[`CLAUDE.md`](CLAUDE.md) §4``
_SECTION = re.compile(r"(%s)[`）)\]]*\s*(?:的)?\s*§\s*(\d+(?:\.\d+)*)"
                      % "|".join(re.escape(n) for n in NUMBERED))
_HEADING = re.compile(r"^#{1,6}\s+(\d+(?:\.\d+)*)[.、 ]")


def _markdown_files():
    return sorted(p for p in REPO.rglob("*.md") if ".git" not in p.parts)


def _sections(name: str):
    """那一份文件裡有編號的章節（``## 3.5 …`` → ``"3.5"``）。"""
    out = set()
    for line in (REPO / name).read_text(encoding="utf-8").splitlines():
        m = _HEADING.match(line)
        if m:
            out.add(m.group(1))
    return out


def _ids(paths):
    return [str(p.relative_to(REPO)) for p in paths]


@pytest.mark.parametrize("doc", _markdown_files(), ids=_ids(_markdown_files()))
def test_every_relative_link_points_at_a_file_that_exists(doc: Path):
    """相對連結指到的東西要真的在那裡。

    網址、錨點（``#…``）、``mailto:`` 不驗 —— 這一支管的是 repo 內部的指標。
    """
    text = doc.read_text(encoding="utf-8")
    broken = []
    for m in _LINK.finditer(text):
        target = m.group(1)
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        rel = target.split("#")[0]
        if not rel:
            continue
        if not (doc.parent / rel).resolve().exists():
            broken.append("第 %d 行 → %s"
                          % (text[:m.start()].count("\n") + 1, target))
    assert not broken, "%s 有指不到的連結：\n  %s" % (
        doc.relative_to(REPO), "\n  ".join(broken))


_LIVE = [p for p in _markdown_files() if ARCHIVE not in p.parts]


@pytest.mark.parametrize("doc", _LIVE, ids=_ids(_LIVE))
def test_every_section_reference_points_at_a_section_that_exists(doc: Path):
    """``CLAUDE.md §4`` 這種引用，那個章節要真的存在。

    這是那 8 條爛掉的指標的迴歸測試 —— 內容搬家的時候，指著它的那幾行會紅。
    """
    text = doc.read_text(encoding="utf-8")
    have = {name: _sections(name) for name in NUMBERED}
    dangling = []
    for m in _SECTION.finditer(text):
        name, sec = m.group(1), m.group(2).rstrip(".")
        if sec not in have[name]:
            dangling.append("第 %d 行 → %s §%s（那一份有的是：%s）"
                            % (text[:m.start()].count("\n") + 1, name, sec,
                               "、".join(sorted(have[name]))))
    assert not dangling, "%s 指到不存在的章節：\n  %s" % (
        doc.relative_to(REPO), "\n  ".join(dangling))


def test_the_numbered_docs_really_are_numbered():
    """上面那一支靠「抓得到章節」才有意義。

    有人把 `CLAUDE.md` 的標題從 ``## 3. 加一張新卡片`` 改成 ``## 加一張新卡片``
    的話，``have[name]`` 會變成空集合 —— 那時候每一條 § 引用都會紅，而紅的
    原因跟使用者以為的不一樣。這一條把那個前提講明白。
    """
    for name in NUMBERED:
        assert len(_sections(name)) >= 4, (
            "%s 沒有編號章節了 —— test_every_section_reference… 的前提不成立，"
            "要嘛把標題編號加回去，要嘛把 NUMBERED 裡的它拿掉" % name)


# --------------------------------------------------------------------------- #
# 值的漂移：文件寫的常數要跟程式碼一樣
# --------------------------------------------------------------------------- #
def test_claude_md_quotes_the_real_hidden_steps():
    """`CLAUDE.md` §5 把 ``HIDDEN_STEPS`` 的值抄了一份，而**它每個 session 都
    會被讀進去** —— 抄錯的代價是每一次都讀到錯的值。

    真的漂過：F24 把 ``feature_math`` / ``feature_fill`` 收起來之後，
    這一份還寫著 ``("align",)``。
    """
    from d4t.ui import scope

    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    for key in scope.HIDDEN_STEPS:
        assert '"%s"' % key in text, (
            "CLAUDE.md 沒有提到 HIDDEN_STEPS 裡的 %r —— 那一段抄的值過期了" % key)


def test_the_docs_agree_with_group_order_on_how_many_stages_there_are():
    """段落的唯一出處是 `step.py` 的 ``GROUP_ORDER``。

    真的漂過：F24 §5 把 Algo 解散成七段之後，`ARCHITECTURE.md`（自稱「架構的
    唯一出處」）與 `ROADMAP.md` 兩份都還畫著含 Algo 的八段。
    """
    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊
    from d4t.core.pipeline.step import GROUP_ALGO, GROUP_ORDER

    assert GROUP_ALGO not in GROUP_ORDER, (
        "Algo 回到 GROUP_ORDER 了 —— 這一條的前提要重寫")
    for name in ("docs/ARCHITECTURE.md", "docs/ROADMAP.md"):
        text = (REPO / name).read_text(encoding="utf-8")
        assert "Measure → Algo → Compare" not in text, (
            "%s 還畫著含 Algo 的八段，而 GROUP_ORDER 是 %d 段"
            % (name, len(GROUP_ORDER)))

"""文件裡寫的「幾張卡」「幾份 recipe」要跟 registry 與 `recipes/` 對得上。

2026-09-09 量到的：`CLAUDE.md` 說出貨 recipe「目前只有一份」、`ROADMAP.md`
說「目前三份」、實際兩份；`README.md` 說卡片 18 張可見 17 張、registry 是
19 與 18。四處數字三種答案 —— 而 `CLAUDE.md` §0 自己宣導的就是「同一件事只
寫在一個地方，抄出來的那份一定會漂」。這一支把那幾個數字釘回真值：文件可以
寫數字，但寫了就要對。

不想被這支測試管的做法只有一種：**把那句話裡的數字拿掉**，改成連結。

2026-09-17 又量了一次，這次抓的是另一種形狀。`test_docs_links.py`（指標）、
`test_doc_file_tree.py`（樹上的名字）、還有上面那幾條（數字）合起來，**抓不到
「名字對、說明錯」** —— 三支測試的檔頭都自己這樣寫著。而這一輪量到的十幾條
漂移，全部落在那個盲區裡：

* `ARCHITECTURE.md` 同一份文件裡「Output 段是三張卡」與「Output 段四張」並存
  （`output_uniformity` 是 F85 加的，前面那一段沒跟上）；
* 同一份文件裡「`roi_reference` 三個 method」與「四種找法」並存 ——
  而那張卡**對使用者說的那句 help 也寫著 "Four ways"**，`METHODS` 只有三個。
  那不是文件漂移，是推廣鐵則的 bug：使用者照著那句話找第四個，找不到；
* `ARCHITECTURE.md` 的 CLI 清單漏掉 `simgen`，而同一份文件下面自己在教
  `python -m d4t simgen`；
* 文件裡還留著 `SHOW_SAMPLE_ENTRIES` —— 那個旗標名 F91 X4 就拆掉了，
  `tests/test_ui_template_library.py` 甚至有一條斷言它**不存在**；
* `recipes/README.md` 少了第三份出貨 recipe 的章節（那份 recipe 有測試跑）；
* `README.md` 的文件索引少了兩份 `docs/*.md`；
* `AGENTS.md` §2 那張**盯搬運包水位的表**自己停在兩週前，而那兩週包又翻了一倍。

下面每一條守的都是「可以從程式碼／磁碟算出真值」的那一種。算不出真值的
（幾支測試、幾行、跑幾秒）一律照上面那句話辦：**把數字拿掉，改成連結**。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_CN = {1: "一", 2: "兩", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九"}


def _registry():
    import d4t.core.steps  # noqa: F401 — 註冊
    from d4t.core.pipeline.step import list_steps
    from d4t.ui import scope
    keys = [s.key for s in list_steps()]
    visible = [k for k in keys if k not in scope.HIDDEN_STEPS]
    return len(keys), len(visible)


def _shipped():
    return sorted(p for p in (REPO / "recipes").glob("*.json")
                  if json.loads(p.read_text(encoding="utf-8")))


def _text(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_the_readme_counts_the_cards_the_registry_has():
    registered, visible = _registry()
    m = re.search(r"(\d+) 張步驟卡片（卡片庫現行可見 (\d+) 張", _text("README.md"))
    assert m, "README.md 那句「N 張步驟卡片（卡片庫現行可見 M 張」不見了"
    assert (int(m.group(1)), int(m.group(2))) == (registered, visible), (
        "README.md 說 %s 張／可見 %s 張，registry 是 %d／%d"
        % (m.group(1), m.group(2), registered, visible))


def test_the_architecture_tree_counts_the_cards_the_registry_has():
    registered, visible = _registry()
    m = re.search(r"註冊 (\d+) 張，卡片庫可見 (\d+) 張", _text("docs/ARCHITECTURE.md"))
    assert m, "docs/ARCHITECTURE.md 那句「註冊 N 張，卡片庫可見 M 張」不見了"
    assert (int(m.group(1)), int(m.group(2))) == (registered, visible), m.group(0)


@pytest.mark.parametrize("rel", ["CLAUDE.md", "docs/ROADMAP.md", "README.md"])
def test_the_docs_count_the_shipped_recipes(rel):
    n = len(_shipped())
    text = _text(rel)
    hits = re.findall(r"目前(?:只有)?([一兩二三四五六七八九十\d]+)份", text)
    assert hits, "%s 裡沒有「目前 N 份」那句話了 —— 改了句型就把這條測試一起改" % rel
    want = {str(n), _CN[n]} if n in _CN else {str(n)}
    bad = [h for h in hits if h not in want]
    assert not bad, "%s 說出貨 recipe「目前%s份」，recipes/ 裡是 %d 份" % (rel, bad, n)


def test_no_doc_names_the_next_card_by_number():
    """「加第 18 張卡的人」那種句子每加一張卡就過期一次 —— 不准用數字指下一張。"""
    for rel in ("CLAUDE.md", "README.md", "docs/ROADMAP.md", "docs/ARCHITECTURE.md"):
        assert not re.search(r"第 ?\d+ 張卡", _text(rel)), rel


# --------------------------------------------------------------------------- #
# 2026-09-17：「名字對、說明錯」那一類 —— 見檔頭。
# --------------------------------------------------------------------------- #

#: 會被掃的文件。**`docs/history/` 與 `SESSION_LOG.md` 不在裡面** —— 它們是
#: 封存與逐輪紀錄，寫的時候是對的，封存的意思正是「不再跟著現在的結構動」
#: （`tests/test_docs_links.py` 立的先例）。
DOC_FILES = ("README.md", "CLAUDE.md", "AGENTS.md", "recipes/README.md") + tuple(
    "docs/" + p.name for p in sorted((REPO / "docs").glob("*.md")))

_CN_VALUE = {"一": 1, "兩": 2, "二": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_NUM = "[一二兩三四五六七八九十\\d]+"
#: 卡片 help 是英文的（使用者面的字走 `ui/strings.py`，而 `ParamSpec.help`
#: 與 `Step.help` 的原句就是鍵）。
_EN_VALUE = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def _value(token: str) -> int:
    return int(token) if token.isdigit() else _CN_VALUE[token]


def _output_cards():
    import d4t.core.steps  # noqa: F401 — 註冊
    from d4t.core.pipeline.step import GROUP_OUTPUT, list_steps
    return [s for s in list_steps() if s.group == GROUP_OUTPUT]


@pytest.mark.parametrize("rel,pattern", [
    ("README.md", r"(%s)張 Output 卡" % _NUM),
    ("docs/ARCHITECTURE.md", r"Output 段是\*\*(%s)張卡\*\*" % _NUM),
])
def test_the_docs_count_the_output_cards(rel, pattern):
    """`output_uniformity`（F85）加進來之後，這兩句話一個多月都還寫著「三張」。

    ⚠ 真值不是「`steps/output.py` 裡有幾個 class」，是 **registry 裡 group 是
    Output 的有幾張** —— 那才是使用者在卡片庫最下面那一區看到的東西。
    """
    n = len(_output_cards())
    m = re.search(pattern, _text(rel))
    assert m, "%s 裡那句「N 張 Output 卡」不見了 —— 改了句型就把這條測試一起改" % rel
    assert _value(m.group(1)) == n, (
        "%s 說 Output 段是「%s」張，registry 是 %d 張（%s）"
        % (rel, m.group(1), n, ", ".join(s.key for s in _output_cards())))


def _cli_subcommands():
    """`d4t/__main__.py` 裡 `sub.add_parser("…")` 的那幾個名字。"""
    src = _text("d4t/__main__.py")
    return set(re.findall(r'add_parser\(\s*"([a-z_]+)"', src))


def test_the_architecture_lists_every_cli_subcommand():
    """`simgen` 2026-08-30 就加了，而那張目錄樹上的 CLI 清單沒跟上 ——
    同一份文件下面自己在教 `python -m d4t simgen`。"""
    want = _cli_subcommands()
    assert want, "抓不到任何子命令 —— `__main__.py` 的寫法變了，改這支測試"
    m = re.search(r"# CLI：(.+)", _text("docs/ARCHITECTURE.md"))
    assert m, "docs/ARCHITECTURE.md 目錄樹裡那行「# CLI：…」不見了"
    got = {p.strip() for p in m.group(1).split("/")}
    assert got == want, (
        "docs/ARCHITECTURE.md 的 CLI 清單跟 `__main__.py` 對不上。\n"
        "  文件多寫的：%s\n  文件漏掉的：%s" % (sorted(got - want), sorted(want - got)))


def _known_show_flags():
    """`d4t/ui/` 底下所有 module-level 的 `SHOW_*`（`scope` 與 `crashlog` 各有）。"""
    names = set()
    for path in sorted((REPO / "d4t" / "ui").glob("*.py")):
        names |= set(re.findall(r"^(SHOW_[A-Z][A-Z0-9_]*)",
                                path.read_text(encoding="utf-8"), re.M))
    return names


@pytest.mark.parametrize("rel", DOC_FILES)
def test_no_doc_names_a_flag_that_no_longer_exists(rel):
    """文件裡提到的旗標名要真的存在。

    `SHOW_SAMPLE_ENTRIES` F91 X4 就拆成兩個旗標了，而 `ARCHITECTURE.md` 還教人
    「把那個常數改 `True`」 —— 照著做的人會得到一個**新增的模組層變數**，
    程式一個位元都不會變。`tests/test_ui_template_library.py` 甚至有一條斷言
    那個名字不存在，兩邊隔著一個月各說各話。
    """
    known = _known_show_flags()
    assert known, "掃不到任何 SHOW_* —— `d4t/ui/` 的寫法變了，改這支測試"
    used = set(re.findall(r"SHOW_[A-Z][A-Z0-9_]*", _text(rel)))
    gone = sorted(used - known)
    assert not gone, (
        "%s 提到了 `d4t/ui/` 裡不存在的旗標：%s\n"
        "  現有的是：%s" % (rel, gone, sorted(known)))


def test_the_recipes_readme_has_a_section_for_every_shipped_recipe():
    """`recipes/README.md` 自己寫著「加一份新的 recipe 就在那支測試裡加一段」——
    而 `one-image-uniformity.json` 加進來的時候，這份 README 沒有跟上。
    一份少一節的目錄比沒有目錄更糟：它看起來是完整的。"""
    want = {p.stem for p in _shipped()}
    got = set(re.findall(r"^## `([a-z0-9-]+)\.json`", _text("recipes/README.md"), re.M))
    assert got == want, (
        "recipes/README.md 的章節跟 recipes/*.json 對不上。\n"
        "  README 多寫的：%s\n  README 漏掉的：%s" % (sorted(got - want), sorted(want - got)))


def test_the_roi_card_help_counts_its_own_methods():
    """**這一條守的不是文件，是使用者看得到的那句話。**

    `roi_reference` 的 help 寫著 "Four ways to find them"，而 `METHODS` 只有三個
    （`repeating cells` 2026-08-25 刪掉）。照那句話去找第四個的人找不到 ——
    而第二原則說：讓使用者看不懂的設計是 bug。
    """
    import d4t.core.steps  # noqa: F401 — 註冊
    from d4t.core.steps.roi_reference import METHODS, RoiReferenceStep
    m = re.search(r"\b(One|Two|Three|Four|Five) ways to find them\b",
                  RoiReferenceStep.help)
    assert m, "roi_reference 的 help 裡那句「N ways to find them」不見了"
    assert _EN_VALUE[m.group(1)] == len(METHODS), (
        "roi_reference 的 help 對使用者說「%s ways」，METHODS 只有 %d 個：%s"
        % (m.group(1), len(METHODS), list(METHODS)))


def test_the_readme_links_every_doc():
    """README 的文件索引自稱「每個主題只有一個出處」，而它少列了兩份手冊 ——
    沒被列到的那一份，等於沒有人找得到。"""
    actual = {p.name for p in (REPO / "docs").glob("*.md")}
    linked = set(re.findall(r"\(docs/([A-Za-z0-9_-]+\.md)\)", _text("README.md")))
    missing = sorted(actual - linked)
    assert not missing, (
        "README.md 沒有連到這幾份文件：%s\n"
        "  —— 加一份 `docs/*.md` 就在 README 的〈文件索引〉補一列。" % missing)


#: 搬運包水位的容差。**這一條刻意不是「相等」**：`bundle/d4t_bundle.py` 每次
#: `tools/release.py` 都會長幾 KB，要求逐 KB 相符只會逼每個 commit 都去改那張表
#: ——那是劇場，不是煞車。做成上限，意思才是「漲太多要有人回來補一列」。
_WATER_HIGH = 1.25
_WATER_LOW = 0.80


def _water_mark_kb():
    """`AGENTS.md` §2 水位表上最高的那一列（KB）。

    ⚠ 只認**第一格是日期**的列 —— 同一份文件裡還有一張「三種打包格式」的表，
    那張表的 KB 不是水位。
    """
    rows = re.findall(r"^> \|\s*\d{4}-\d{2}-\d{2}[^|]*\|\s*\*{0,2}([\d,]+) KB\*{0,2}\s*\|",
                      _text("AGENTS.md"), re.M)
    assert rows, "AGENTS.md §2 的水位表不見了（或格式變了）"
    return max(int(r.replace(",", "")) for r in rows)


def _bundle_kb():
    return (REPO / "bundle" / "d4t_bundle.py").stat().st_size // 1024


def test_the_bundle_has_not_outgrown_the_water_mark_table():
    """那張表存在的唯一理由就是盯這件事，而 2026-09-17 量到的是：
    表停在 2,172 KB（09-02），實際已經 4,234 KB —— 兩週又翻一倍，沒有人發現。"""
    mark, actual = _water_mark_kb(), _bundle_kb()
    assert actual <= mark * _WATER_HIGH, (
        "bundle 現在 %d KB，AGENTS.md §2 水位表最高只寫到 %d KB。\n"
        "  回去補一列（日期 + 大小 + 一句為什麼），這條就綠了。" % (actual, mark))


def test_the_water_mark_table_is_not_stale_the_other_way():
    """反向：包**縮小**了而表沒跟上也要叫。

    那正好是最該記一筆的時候 —— 2026-09-02 那次封存一次省了 182 KB，
    而「省了多少」是下一次有人想省的時候唯一的依據。
    """
    mark, actual = _water_mark_kb(), _bundle_kb()
    assert actual >= mark * _WATER_LOW, (
        "bundle 掉到 %d KB，而 AGENTS.md §2 水位表還寫著 %d KB。\n"
        "  有人把東西搬出包了 —— 補一列把成果鎖住。" % (actual, mark))

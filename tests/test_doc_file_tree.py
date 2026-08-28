# 文件裡畫的目錄結構要跟磁碟上一樣 — authored 2026-08-28.
"""**`docs/ARCHITECTURE.md` 自稱「架構的唯一出處」，而它畫的那棵樹沒有人在守。**

於是它漂了。2026-08-28 這一輪掃出來的：

* `tests/`、`tools/`、`fab_probe/`、`docs/` 被畫成 `d4t/` 的**子目錄** ——
  它們是 repo 根的同層目錄。照那張圖去找 `d4t/tests/` 的人會找不到。
* `recipes/`、`bundle/`、`.github/`、根目錄那幾個檔案**一個都沒畫**。
* 漏掉十幾支模組：`pipeline/` 少了 `decide_tree` / `verdict_features` /
  `verdict_trace` / `channels` / `cellrois` / `curve`，`ingest/` 少了
  `pair_source` / `glas_export`，`ui/` 少了十三支（F22 之後每一塊新面板都是
  一個新模組 —— 那條規矩本身就保證這張圖會被拋在後面）。

`tests/test_docs_links.py` 守的是**指標**（連結、§ 引用），這一份守的是**內容**
的一種：那棵樹上的每一個名字。兩支合起來仍然抓不到「名字對、說明錯」——
所以這是**下限**，不是保證。

守兩個方向，缺一不可：

1. 樹上畫的東西要真的在磁碟上（畫了一個不存在的檔案 → 紅）；
2. `d4t/` 底下每一支模組都要在樹上（加了新模組沒畫上去 → 紅）。

只有 (1) 的話，「漏畫」永遠不會紅 —— 而上面那十幾支正是漏畫，不是畫錯。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "docs" / "ARCHITECTURE.md"

#: 這一份守的是哪一節。節名改了要一起改 —— 而 `test_the_parser_found_a_tree`
#: 會在改了沒跟上的時候變紅（找不到節 ＝ 一個條目都抓不到）。
SECTION = "## 目錄結構"

#: 樹的連接線之後才是條目名。註解（`#` 之後）不算 —— 註解裡會提到別的檔案
#: （`tests/test_no_qt.py`、`tools/freeze_golden.py`…），那些是**說明**不是條目。
_ENTRY = re.compile(r"──\s+(.*)$")


def _tracked():
    out = subprocess.run(["git", "ls-files"], cwd=REPO, check=True,
                         capture_output=True, text=True).stdout
    return [p for p in out.splitlines() if p]


def _universe():
    """所有被追蹤的路徑，**加上它們的每一層父目錄**（樹上畫得到目錄）。"""
    paths = set()
    for rel in _tracked():
        paths.add(rel)
        parts = rel.split("/")
        for i in range(1, len(parts)):
            paths.add("/".join(parts[:i]))
    return paths


def _entries():
    """`docs/ARCHITECTURE.md` §目錄結構 的每一個條目名（去掉尾巴的 ``/``）。"""
    text = DOC.read_text(encoding="utf-8")
    start = text.index(SECTION)
    body = text[start:]
    out = []
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            continue
        m = _ENTRY.search(line)
        if not m:
            continue
        for tok in m.group(1).split("#")[0].split():
            tok = tok.rstrip("/")
            if tok:
                out.append(tok)
    return out


ENTRIES = _entries()


def _resolves(tok: str, universe) -> bool:
    """條目名對得上某個真實路徑的**尾段**。

    樹是縮排的，重建完整路徑要靠縮排推父目錄 —— 那個 parser 比它守的東西還
    容易壞（一行放兩個名字就崩）。改成比尾段：``store/results.py`` 對得上
    ``d4t/core/store/results.py``，而 ``theme.py`` 對得上 ``d4t/ui/theme.py``。
    代價是抓不到「畫在錯的父目錄底下」—— 那一種留給人看。
    """
    return any(p == tok or p.endswith("/" + tok) for p in universe)


@pytest.mark.parametrize("entry", ENTRIES)
def test_every_entry_in_the_tree_exists_on_disk(entry: str):
    """樹上畫的每一個名字，磁碟上要有。"""
    assert _resolves(entry, _universe()), (
        "docs/ARCHITECTURE.md §目錄結構 畫了 %r，但 git 追蹤的檔案裡沒有這個東西"
        % entry)


def test_every_module_under_the_package_is_on_the_tree():
    """`d4t/` 底下每一支模組都要畫上去 —— **漏畫也是漂移**。

    ``__init__.py`` 不算（每個套件一支，畫上去只是噪音）。
    """
    named = {e.rsplit("/", 1)[-1] for e in ENTRIES}
    missing = sorted(
        rel for rel in _tracked()
        if rel.startswith("d4t/") and rel.endswith(".py")
        and not rel.endswith("__init__.py")
        and rel.rsplit("/", 1)[-1] not in named)
    assert not missing, (
        "這幾支模組不在 docs/ARCHITECTURE.md §目錄結構 的樹上：\n  %s\n"
        "（新的 UI 面板一律開新模組 —— 所以這一條會常常紅，加一行就好）"
        % "\n  ".join(missing))


def test_every_top_level_directory_is_on_the_tree():
    """repo 根的每一個目錄都要畫上去。

    `recipes/`（出貨的 recipe）與 `bundle/`（搬運用的單檔包）以前都不在圖上，
    而它們正是**新來的人最需要知道在哪**的兩個。
    """
    text = DOC.read_text(encoding="utf-8")[DOC.read_text(encoding="utf-8")
                                           .index(SECTION):]
    tops = sorted({rel.split("/")[0] for rel in _tracked() if "/" in rel})
    missing = [d for d in tops
               if d + "/" not in text and d not in ENTRIES]
    assert not missing, (
        "docs/ARCHITECTURE.md §目錄結構 沒有畫到這幾個頂層目錄：%s"
        % "、".join(missing))


def test_every_top_level_file_is_on_the_tree():
    """repo 根的每一個檔案也要（點開頭的設定檔不算）。"""
    named = {e.rsplit("/", 1)[-1] for e in ENTRIES}
    missing = sorted(rel for rel in _tracked()
                     if "/" not in rel and not rel.startswith(".")
                     and rel not in named)
    assert not missing, (
        "docs/ARCHITECTURE.md §目錄結構 沒有畫到根目錄的：%s" % "、".join(missing))


def test_the_parser_found_a_tree():
    """上面每一支都靠「抓得到條目」才有意義。

    有人把節名從 ``## 目錄結構`` 改掉、或把樹從 ``` 區塊搬出來的話，
    `ENTRIES` 會變成空的 —— 那時候 (1) 一條都不跑、(2) 會報「全部漏畫」，
    而紅的原因跟使用者以為的不一樣。這一條把那個前提講明白。

    （這就是 `tests/test_shipped_recipes.py` 的 ``ALLOWED_ERRORS`` 學到的那一課：
    **任何靠掃描得出結論的測試，都要有一支反向的測試守著它掃得到東西。**）
    """
    assert len(ENTRIES) >= 60, (
        "只從 §目錄結構 抓到 %d 個條目 —— parser 或節名壞了，"
        "這一份的其他測試都不算數" % len(ENTRIES))

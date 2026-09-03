# 授權文件裡的兩張表要跟事實一致 — authored 2026-08-28.
"""**`docs/LICENSING.md` 抄了兩份「別的地方才是正典」的清單，所以它們會漂。**

那兩張表是：

* §3 —— d4t 裡哪幾支是 vendored 的。正典是**那些模組自己的檔頭**
  （d4t 的 vendoring 規矩就是「檔頭註明來源與改動」）。
* §4 —— 執行時相依套件的授權。正典是 `pyproject.toml` 與 `requirements.txt`。

兩張都是「加東西的時候會忘記回來改」的形狀：加一支 vendored 模組、加一個相依
套件，程式碼都跑得好好的，只有那份文件安靜地少一列。而一份少一列的授權清單
**比沒有那份清單更糟** —— 它看起來完整。

2026-08-28 授權定案（專有／內部使用）之後又多守兩條，都是**同一個形狀**：
`LICENSE` 要真的在（一份說「已經加了授權」的文件配上不存在的檔案，比沒有那份
文件更糟），而 `LICENSE` 的第三方 carve-out 要蓋到每一個相依套件 ——
一份「保留所有權利」的聲明只點名五個套件、漏掉第六個 LGPL 的，就是把那一個
蓋進了自己的專有聲明裡。

這一份守的是**涵蓋範圍**，不是內容。「表上有這一列」跟「那一列寫對了」是兩件
事，後者只有人回來看才知道 —— 所以 `LICENSING.md` 頂上寫著查證日期。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "docs" / "LICENSING.md"
LICENSE = REPO / "LICENSE"
PKG = REPO / "d4t"

#: 檔頭「這一支是 vendored 的」怎麼寫 —— 前三行、`#` 開頭、``vendored into/from``。
#:
#: 三行是量出來的：最寬的一支（`dataset.py`）寫 ``# Vendored/adapted into d4t``
#: 在第 1 行，最窄的（`widgets.py` / `theme.py`）在第 2 行。放寬到整個檔案的話
#: 會抓到一堆**提到** vendoring 的散文（`algo/__init__.py`、`algo/pairing.py`
#: 的說明段），那些不是「這一支是搬來的」。
_VENDORED = re.compile(r"^#.*[Vv]endored\S*\s+(into|from)")


def _vendored_modules():
    out = []
    for py in sorted(PKG.rglob("*.py")):
        with py.open(encoding="utf-8") as fh:
            head = [fh.readline() for _ in range(3)]
        if any(_VENDORED.match(line) for line in head):
            out.append(str(py.relative_to(REPO)).replace("\\", "/"))
    return out


def _dev_extra_packages():
    """`[project.optional-dependencies]` 的 ``dev`` 那一項宣告了什麼。

    只有這一項 —— `gui`（PySide6）是**執行時**相依，只是選配，所以它照樣
    要進 `LICENSE` 的 carve-out。
    """
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    extras = re.search(r"^\[project\.optional-dependencies\]\n(.*?)(?=^\[|\Z)",
                       text, re.S | re.M)
    if not extras:
        return set()
    block = re.search(r"^dev\s*=\s*\[(.*?)\]", extras.group(1), re.S | re.M)
    if not block:
        return set()
    return {re.match(r"[A-Za-z0-9_.\-]+", item).group(0)
            for item in re.findall(r'"([^"]+)"', block.group(1))}


def _declared_packages():
    """`pyproject.toml` ＋ `requirements.txt` 宣告的套件名（去掉版本限制）。

    不用 ``tomllib``：那是 3.11 才有的，而這個 repo 的底線是 3.9。
    兩份都是每行／每項一個 ``名字>=版本``，正規表示式綽綽有餘。

    ⚠ **只讀 `dependencies` 與 `[project.optional-dependencies]` 兩處。**
    掃全檔的 ``= [...]`` 會抓到 ``package-data`` 的 ``assets/*.svg`` 與
    ``testpaths`` 的 ``tests`` —— 然後要求授權表上有一列叫「assets」。
    （真的發生過，就在寫這一份的時候。）
    """
    names = set()
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    blocks = re.findall(r"^dependencies\s*=\s*\[(.*?)\]", text, re.S | re.M)
    extras = re.search(r"^\[project\.optional-dependencies\]\n(.*?)(?=^\[|\Z)",
                       text, re.S | re.M)
    if extras:
        blocks += re.findall(r"=\s*\[(.*?)\]", extras.group(1), re.S)
    for block in blocks:
        for item in re.findall(r'"([^"]+)"', block):
            names.add(re.match(r"[A-Za-z0-9_.\-]+", item).group(0))
    for line in (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.add(re.match(r"[A-Za-z0-9_.\-]+", line).group(0))
    return names


def test_the_vendored_table_lists_every_vendored_module():
    """檔頭說自己是 vendored 的模組，§3 那張表要有它。"""
    text = DOC.read_text(encoding="utf-8")
    missing = [rel for rel in _vendored_modules() if rel not in text]
    assert not missing, (
        "這幾支的檔頭寫著它們是 vendored 的，但 docs/LICENSING.md §3 沒列：\n  %s"
        % "\n  ".join(missing))


def test_the_vendored_table_has_no_ghosts():
    """反過來也要成立：表上列的模組要真的存在、而且檔頭真的說它是 vendored 的。

    少了這一條，「模組刪掉了、表上那一列留著」永遠不會紅 —— 而這個 repo
    刪過的東西不少（`pattern_ref`、`cell_period`、`snr_map`、`find_defect`）。
    """
    text = DOC.read_text(encoding="utf-8")
    listed = set(re.findall(r"`(d4t/[^`]+\.py)`", text))
    real = set(_vendored_modules())
    ghosts = sorted(listed - real)
    assert not ghosts, (
        "docs/LICENSING.md §3 列了這幾支，但它們不存在、或檔頭沒說自己是 "
        "vendored 的：\n  %s" % "\n  ".join(ghosts))


def test_every_declared_dependency_has_a_license_row():
    """`pyproject.toml` / `requirements.txt` 宣告的每一個套件，§4 都要提到。

    加一個相依套件而沒回來寫，那張表就從「相依套件的授權」變成
    「其中幾個相依套件的授權」—— 而它不會告訴你是哪幾個。
    """
    text = DOC.read_text(encoding="utf-8")
    missing = sorted(p for p in _declared_packages()
                     if p.lower() not in text.lower())
    assert not missing, (
        "這幾個相依套件不在 docs/LICENSING.md §4 的授權表上：%s"
        % "、".join(missing))


def test_the_scanners_actually_found_something():
    """上面三支都靠「掃得到東西」才有意義 —— 這一條把那個前提講明白。

    改了檔頭的寫法、或把相依搬去別的檔案，`_vendored_modules()` /
    `_declared_packages()` 會變成空的，而那時候上面三支會**全部變綠**。
    這正是 `tests/test_shipped_recipes.py` 的 ``ALLOWED_ERRORS`` 學到的那一課：
    **任何靠掃描得出結論的測試，都要有一支反向的測試守著它掃得到東西。**
    """
    vendored = _vendored_modules()
    deps = _declared_packages()
    assert len(vendored) >= 15, (
        "只掃到 %d 支 vendored 模組（預期 15 支以上）—— 檔頭的寫法變了？"
        % len(vendored))
    assert len(deps) >= 5, (
        "只掃到 %d 個宣告的相依套件（預期 5 個以上）—— 相依搬家了？" % len(deps))


def test_the_doc_says_when_it_was_checked():
    """GitHub 的可見性與 PyPI 的授權欄位都會變，而測試看不到那兩件事。

    唯一能做的是**逼這一份講出它是什麼時候查的** —— 讀的人才有辦法判斷
    要不要重查一次。
    """
    text = DOC.read_text(encoding="utf-8")
    assert re.search(r"20\d\d-\d\d-\d\d", text), (
        "docs/LICENSING.md 沒有任何查證日期 —— 那張表就沒有保存期限了")


# --------------------------------------------------------------------------- #
# 2026-08-28 授權定案之後：LICENSE 這個檔案本身
# --------------------------------------------------------------------------- #
def test_the_license_file_exists_and_matches_what_the_doc_claims():
    """`LICENSING.md` §1 說授權是「專有／內部使用」—— 那個檔案要真的在，
    而且真的那樣寫。

    這一條防的是最蠢也最容易發生的一種：文件先寫好了，檔案忘了加（或後來被
    誰刪了），而**沒有任何測試會注意到** —— 讀的人以為有授權，`pip` 裝出來的
    套件中繼資料卻是空的。
    """
    assert LICENSE.is_file(), "repo 根沒有 LICENSE —— 但 docs/LICENSING.md 說有"
    text = LICENSE.read_text(encoding="utf-8")
    assert "PROPRIETARY" in text and "INTERNAL USE ONLY" in text, (
        "LICENSE 的內容不是 docs/LICENSING.md §1 說的那一種（專有／內部使用）")
    assert "PROPRIETARY" in DOC.read_text(encoding="utf-8"), (
        "docs/LICENSING.md 沒有引到 LICENSE 實際寫的字 —— 兩邊會各說各話")


def test_pyproject_points_at_the_license_file():
    """`pyproject.toml` 要宣告授權，否則 `pip install` 出來的中繼資料是空的。

    ⚠ 這裡**不管**用的是 `{file = ...}` 還是 PEP 639 的 `LicenseRef-…`
    —— 那是 setuptools 版本底線的取捨（見 `docs/LICENSING.md` §1），
    換寫法不該讓這一條紅。要守的只有「有宣告」。
    """
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r"^license\s*=", text, re.M), (
        "pyproject.toml 沒有 license 欄位 —— 打包出來的東西不會帶授權資訊")


def test_the_license_carve_out_covers_every_dependency():
    """`LICENSE` 的第三方 carve-out 要點名每一個相依套件。

    **這一條看起來多餘，它不是。** 那份聲明是「保留所有權利」，而它底下跑著
    LGPL 的 PySide6 —— carve-out 漏掉哪一個，就等於把那一個蓋進了自己的專有
    聲明裡。加相依套件的時候 `LICENSE` 與 `docs/LICENSING.md` §4 **兩邊都要加**，
    而紅的那一條會告訴你漏了哪一邊。

    （`shiboken6` 不算：它是 PySide6 拖進來的，沒有人直接宣告它 ——
    `LICENSE` 寫的 "PySide6 and its dependencies" 就是在講它。）

    **`dev` extra 裡的也不算**，而判準是讀出來的、不是寫死的名字：那一段
    carve-out 的原文是「this software depends on **at run time**」，而 `dev`
    裡的東西（`pytest`、`ruff`）一次都不執行、也不隨任何一條搬運路徑進廠。
    這裡以前寫死一個 ``!= "pytest"``，於是 2026-09-03 加 `ruff` 的時候它紅了
    —— 紅得對（有東西變了），但指的方向錯（它要人去改 `LICENSE`，而那是錯的
    答案）。判準改成問 `dev` extra 本身之後，下一個開發工具不會再問一次。
    """
    text = LICENSE.read_text(encoding="utf-8").lower()
    dev_only = {n.lower() for n in _dev_extra_packages()}
    missing = sorted(p for p in _declared_packages()
                     if p.lower() not in text and p.lower() not in dev_only)
    assert not missing, (
        "LICENSE 的第三方 carve-out 沒有點名這幾個相依套件：%s\n"
        "（漏掉的那一個，等於被蓋進了 d4t 自己的專有聲明裡）" % "、".join(missing))

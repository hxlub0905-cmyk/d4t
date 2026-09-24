# U14：使用者面的字只有一個進出口 — authored 2026-09-08.
"""**註解全中文、UI 字串 100% 英文硬編碼，沒有 tr() 也沒有 catalog。**

之後要出中文版＝改 38 個檔案，而那時候正是最不想動 UI 的時候。

這一份守的是那個前置真的成立：翻譯層擺在**共用的那幾支**（工具列的鈕、
`small_button`、參數說明、狀態列），所以包一次涵蓋幾百句而呼叫端一個字都不用
改；而**卡片名與階段名不准被翻**（它們是 recipe JSON 的鄰居與廠內的共同
語彙 —— 翻掉的話同一份 recipe 在兩台機器上講的是兩個名字）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from d4t.ui import strings                   # noqa: E402 — 不 import Qt


@pytest.fixture(autouse=True)
def _english_again():
    """**測試不准把語言留給下一支測試。**

    它是模組層的狀態，而模組在一個行程裡只 import 一次 —— 忘了還原的話後面
    每一支測試看到的是中文，而失敗會出現在別的檔案上。
    """
    before = strings.current()
    yield
    strings.install(before)


# --------------------------------------------------------------------------- #
# 1. catalog 本身
# --------------------------------------------------------------------------- #
def test_without_a_catalog_it_gives_back_the_original():
    """**漏包一句話的代價是「那句話沒有被翻譯」，不是畫面上出現一個鍵。**

    這正是「鍵就是英文原句」換到的東西。
    """
    strings.install("en")
    assert strings.tr("Run trial") == "Run trial"
    assert strings.tr("") == ""


def test_a_missing_locale_file_falls_back_to_english():
    """一個少了翻譯檔的安裝應該是「英文版的 d4t」，不是一個開不起來的 d4t。"""
    assert strings.install("kl_ingon") == "en"
    assert strings.current() == "en"
    assert strings.tr("Run trial") == "Run trial"


def test_a_catalog_translates_and_the_gaps_stay_english(tmp_path, monkeypatch):
    """**一份翻到一半的 catalog 是可以出貨的** —— 那正是要的。"""
    monkeypatch.setattr(strings, "LOCALE_DIR", tmp_path)
    (tmp_path / "zz.json").write_text(
        json.dumps({"Run trial": "試跑", "Results": ""}), encoding="utf-8")
    assert strings.install("zz") == "zz"
    assert strings.tr("Run trial") == "試跑"
    assert strings.tr("Results") == "Results", "空字串的譯文不算翻譯"
    assert strings.tr("Never translated") == "Never translated"


def test_a_broken_catalog_does_not_take_the_app_down(tmp_path, monkeypatch):
    monkeypatch.setattr(strings, "LOCALE_DIR", tmp_path)
    (tmp_path / "bad.json").write_text("{ not json", encoding="utf-8")
    (tmp_path / "list.json").write_text("[1, 2]", encoding="utf-8")
    assert strings.install("bad") == "en"
    assert strings.install("list") == "en"


def test_it_says_which_sentences_still_need_translating(tmp_path, monkeypatch):
    """「先翻哪一句」要有依據 —— 出現最多次的那一句使用者看到的機會最大。

    手寫一份待翻清單的話，下一個人加一句話而忘了加進清單，那句話會安靜地
    永遠不被翻譯。
    """
    monkeypatch.setattr(strings, "LOCALE_DIR", tmp_path)
    (tmp_path / "zz.json").write_text(json.dumps({"A": "甲"}), encoding="utf-8")
    strings.install("zz")
    strings.forget()
    strings.tr("A")
    strings.tr("B"); strings.tr("B"); strings.tr("B")
    strings.tr("C")
    assert strings.missing()[0] == "B", strings.missing()
    assert "A" not in strings.missing()


def test_english_has_nothing_missing():
    strings.install("en")
    strings.forget()
    strings.tr("anything at all")
    assert strings.missing() == []


def test_english_is_always_available():
    assert "en" in strings.available()


# --------------------------------------------------------------------------- #
# 2. 不翻譯的兩類
# --------------------------------------------------------------------------- #
def test_card_names_never_go_through_the_catalog():
    """卡片名是 recipe JSON 的鄰居與廠內的共同語彙。

    「Denoise」翻成「去雜訊」之後，一份 recipe 在兩台機器上講的是兩個名字。
    """
    import ast
    hits = []
    for rel in ("d4t/ui/library.py", "d4t/ui/param_form.py", "d4t/ui/canvas.py"):
        src = (REPO / rel).read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name != "tr":
                continue
            inside = ast.dump(node)
            if "'label'" in inside or '"label"' in inside:
                hits.append("%s:%d" % (rel, node.lineno))
    assert not hits, (
        "這幾個地方把卡片名送進翻譯層了：%s\n"
        "  卡片名與階段名不翻 —— 見 d4t/ui/strings.py 的「不翻譯的兩類」。"
        % hits)


def test_stage_titles_are_not_translated(tmp_path, monkeypatch):
    """階段名印在 rail 上、CLI 上、文件上 —— 三個地方要講同一個字。"""
    from d4t.core.pipeline.step import GROUPS, group_title
    monkeypatch.setattr(strings, "LOCALE_DIR", tmp_path)
    (tmp_path / "zz.json").write_text(
        json.dumps({t: "翻掉了" for _g, t, _s in GROUPS}), encoding="utf-8")
    strings.install("zz")
    assert group_title("region") == "ROI", \
        "階段名被翻譯層碰到了 —— core 不該知道 UI 的語言（鐵則 1 的同一個道理）"


# --------------------------------------------------------------------------- #
# 3. 翻譯層真的在那幾支共用的地方
# --------------------------------------------------------------------------- #
_CHOKE_POINTS = {
    "d4t/ui/buttons.py": "small_button —— 卡片控制、畫布縮放、換 defect",
    "d4t/ui/studio.py": "_tool_button（整條工具列）＋ 狀態列",
    "d4t/ui/fields.py": "_HintLabel.set_full_text（每一句參數說明）",
    "d4t/ui/param_form.py": "editor 的 tooltip 與卡片說明",
}


@pytest.mark.parametrize("rel", sorted(_CHOKE_POINTS))
def test_the_shared_helpers_translate(rel):
    """**這一條是「之後不必改 38 個檔案」那句話的執行機構。**

    翻譯層一旦從這幾支掉出去，剩下的路只有「每個呼叫端各包一次」——
    而那正是 U14 要避免的那件事。
    """
    src = (REPO / rel).read_text(encoding="utf-8")
    assert "strings.tr(" in src, (
        "%s 沒有走翻譯層了（它是 %s）" % (rel, _CHOKE_POINTS[rel]))


def test_a_toolbar_button_really_comes_out_translated(tmp_path, monkeypatch,
                                                      qapp_or_skip):
    """結構對還不夠 —— 真的開一個視窗，讀那顆鈕上的字。"""
    monkeypatch.setattr(strings, "LOCALE_DIR", tmp_path)
    (tmp_path / "zz.json").write_text(
        json.dumps({"Results": "結果"}), encoding="utf-8")
    strings.install("zz")
    from d4t.ui.studio import StudioWindow
    win = StudioWindow()
    try:
        assert win.btn_results.text() == "結果"
    finally:
        win.close()


@pytest.fixture(scope="module")
def qapp_or_skip():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# --------------------------------------------------------------------------- #
# 4. 出貨的那一份 catalog
# --------------------------------------------------------------------------- #
def test_the_shipped_catalog_loads_and_translates():
    """`zh_TW` 是**真的一份**，不是一個空殼 —— 機制要看得到它跑完全程。"""
    assert "zh_TW" in strings.available()
    assert strings.install("zh_TW") == "zh_TW"
    assert strings.tr("Run trial") == "試跑"
    assert strings.tr("Results") == "結果"


def test_the_shipped_catalog_is_a_flat_table_of_real_sentences():
    """每一列都要是「英文原句 → 譯文」，而且**兩邊都不是空的**。

    空譯文在 `install()` 那裡會被丟掉（那是刻意的），但留在檔案裡會讓人以為
    那一句翻過了 —— 而它其實還在待翻清單上。
    """
    raw = json.loads(
        (REPO / "d4t" / "ui" / "locales" / "zh_TW.json")
        .read_text(encoding="utf-8"))
    assert isinstance(raw, dict) and raw
    for src, dst in raw.items():
        assert src.strip(), "有一列的原句是空的"
        assert str(dst).strip(), "「%s」的譯文是空的 —— 沒翻就整列拿掉" % src


def test_the_catalog_does_not_translate_a_card_name():
    """**這一條是那條規矩的執行機構。**

    catalog 是一張平表，鍵就是英文原句 —— 所以哪天有人把「Denoise」加進去，
    卡片名就會被翻掉，而畫布上的字與 recipe JSON 從此講不同的話。
    """
    import d4t.core.steps                    # noqa: F401
    from d4t.core.pipeline.step import GROUPS, list_steps

    raw = json.loads(
        (REPO / "d4t" / "ui" / "locales" / "zh_TW.json")
        .read_text(encoding="utf-8"))
    forbidden = ({str(s.label) for s in list_steps() if s.label}
                 | {t for _g, t, _s in GROUPS})
    # 「Card」「Features」那兩顆切換鈕跟階段名沒有關係，而 `Build` 是版面模式
    # —— 它們剛好同名的話這一條會誤報，所以只比**真的是卡片名**的那一組。
    clash = sorted(set(raw) & forbidden)
    assert not clash, (
        "catalog 裡有卡片名或階段名：%s\n"
        "  它們是 recipe JSON 的鄰居與廠內的共同語彙 —— 翻掉的話同一份 recipe "
        "在兩台機器上講的是兩個名字。" % clash)


def test_the_todo_tool_exists_and_says_how_to_run_it():
    """待翻清單是**跑一次收集**出來的，不是掃原始碼 —— 那件事要寫下來。

    翻譯層擺在共用的那幾支，所以大部分句子在原始碼裡看起來不像要翻的東西
    （它們是 `ParamSpec.help` 的字串）。下一個接手的人如果去掃原始碼，
    會得到一份漏掉大半的清單。
    """
    src = (REPO / "tools" / "i18n_todo.py").read_text(encoding="utf-8")
    assert "strings.tr()" in src or "strings.tr" in src
    assert "掃原始碼" in src, "要講明為什麼不是掃原始碼"

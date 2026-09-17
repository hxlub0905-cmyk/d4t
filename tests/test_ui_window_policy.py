# U15：頂層視窗的規則要有人守 — authored 2026-09-08.
"""**十一個頂層視窗，而沒有一條規則說什麼時候該開一個。**

那是 2026-09-08 那份外部檢視數出來的。規則寫在
`docs/ARCHITECTURE.md`「什麼時候可以開一個新視窗」，一句話：

> 只有「要跟主視窗並排對照」的才開頂層視窗，其餘一律 modal。

這一份是那條規則的執行機構。它**擋不住你做出錯的決定** —— 它擋得住的是
「沒有人做過那個決定」：加第十二個視窗類別而沒有在下面那兩張表裡表態的話，
這裡會叫，而那一刻就是回答「使用者需不需要一邊看著它、一邊動主視窗」的時候。

⚠ 這一份**不 import Qt**（讀原始碼、用 `ast` 解析），所以它跑在核心那一批
裡。理由跟 `test_size_ceilings.py` 一樣：一條「這個檔案裡有沒有這個東西」的
規則不需要一個 QApplication，而付得起才會有人跑。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

#: **要跟主視窗並排對照的**，每一列附一句為什麼（規則的正面）。
_SIDE_BY_SIDE = {
    "StudioWindow": "主視窗本人",
    "ResultsWindow": "一邊看結果表、一邊在畫布上改參數 —— 調 recipe 的迴圈",
    "RegionCheckWindow": "一邊看區域畫在很多顆上、一邊改那張 Region 卡",
    "GcGeneratorWindow": "產模擬資料跟目前的 recipe 無關，它自己是一個小工具",
    "LatticeDialog": "一邊看格線鋪在原圖上對不對、一邊在模板對話框改 cell 尺寸 ——"
                     " 它是那顆「Grid」開關的另一半（F104）",
}

#: **進去做完一件事再出來的**（規則的反面）—— 這些必須是 modal 對話框。
_MODAL = {
    "WelcomeDialog", "TemplateDialog", "ChartSettingsDialog",
    "GraphBuilderDialog", "CurveDialog", "StatusHistoryDialog",
    "RecipeLibraryDialog", "CropDialog",
}

_TOP_LEVEL_BASES = ("QMainWindow", "QDialog")


def _window_classes():
    """`d4t/ui` 底下每一個直接繼承 QMainWindow / QDialog 的類別。"""
    found = {}
    for path in sorted((REPO / "d4t" / "ui").glob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")
                     for b in node.bases]
            if any(b in _TOP_LEVEL_BASES for b in bases):
                found[node.name] = (path.name, bases)
    return found


def test_every_top_level_window_took_a_side():
    """新加一個頂層視窗，就要在那兩張表裡表一次態。"""
    known = set(_SIDE_BY_SIDE) | _MODAL
    found = _window_classes()
    strangers = sorted(set(found) - known)
    assert not strangers, (
        "這幾個頂層視窗沒有在 docs/ARCHITECTURE.md 的規則裡表態：\n  %s\n"
        "  先回答那一句：使用者需不需要一邊看著它、一邊動主視窗？\n"
        "  要 → 加進 _SIDE_BY_SIDE 並寫下理由；不要 → 做成 modal 並加進 _MODAL。"
        % "\n  ".join("%s（%s）" % (n, found[n][0]) for n in strangers))


def test_the_lists_do_not_rot():
    """反向的那一支：表上列著的類別要真的還在。

    刪掉一個視窗卻沒從表上拿掉的話，這張表會慢慢變成一份考古紀錄，而下一個人
    讀它的時候分不出哪幾列還算數（`CLAUDE.md`：任何例外清單都要有反向測試）。
    """
    found = set(_window_classes())
    gone = sorted((set(_SIDE_BY_SIDE) | _MODAL) - found)
    assert not gone, (
        "這幾個已經不是頂層視窗了，把它們從表上拿掉：%s" % gone)


def test_the_side_by_side_ones_each_say_why():
    """正面那張表的每一列都要講得出理由 —— 沒有理由的話它只是一份名單。"""
    for name, why in _SIDE_BY_SIDE.items():
        assert why.strip(), "%s 沒有寫為什麼要開一個頂層視窗" % name


def test_the_rule_is_written_down_where_people_look():
    """規則住在 ARCHITECTURE.md，而不只是住在這支測試裡。

    只寫在測試裡的規則，只有踩到的人讀得到 —— 而那時候他已經做完了。
    """
    doc = (REPO / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "什麼時候可以開一個新視窗" in doc
    for name in _SIDE_BY_SIDE:
        assert name in doc, "%s 在規則那一段裡沒有被提到" % name

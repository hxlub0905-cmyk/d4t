# 按鈕上的字：一個動作一顆鈕，而字要照原樣畫出來（2026-08-24）。
"""兩條規矩，都是使用者從**畫面上**看出來的（不是從程式碼）。

1. **同一個動作不要有兩顆鈕。** 使用者：「UI 上有兩個相同功能的鍵 …
   若沒差或差不多 請留一個即可」。而它們真的沒差 —— 兩邊都是同一支
   ``StudioWindow.run_all()``，一個位元的差別都沒有。

2. **`&` 要寫兩個。** Qt 把單一個 ``&`` 當成助憶鍵的記號吃掉，於是
   ``"Run all & write"`` 畫出來是 **``Run all _write``** —— 而那正是使用者
   用來稱呼它的名字。這一條是**執行期**掃的，不是掃原始碼：有些字是組出來
   的，而畫出來的那一份才算數。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton, QApplication, QMenu, QWidget,
)
from PySide6.QtGui import QAction  # noqa: E402

from d4t.ui import studio as studio_mod, theme as theme_mod  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        yield win
    finally:
        win.close()


def _owner_window(obj):
    """這個東西**畫在哪一個視窗上**。

    ⚠ 不能只用 ``root.findChildren`` 就算數：Results 視窗是 Studio 的子物件
    （parent 是主視窗，這樣它才會跟著關掉），所以掃主視窗會**連 Results 上
    那顆一起掃到**。第一版因此把「兩個視窗各一顆」誤判成「主視窗上有兩顆」。

    ⚠ **`QMenu` 自己就是一個視窗**（彈出式的），所以也不能直接用
    ``obj.window()``：選單項會回報自己屬於那個 QMenu，而不是掛著它的那顆
    工具列按鈕所在的視窗 —— 於是主視窗那一份變成空的。往上走要跳過 popup。
    """
    while obj is not None:
        if (isinstance(obj, QWidget) and not isinstance(obj, QMenu)
                and obj.isWindow()):
            return obj
        obj = obj.parent()
    return None


def _labels(root):
    """**畫在這一個視窗上**的每一個看得到的字（按鈕與選單項）。"""
    out = []
    for w in root.findChildren(QAbstractButton):
        if w.text() and _owner_window(w) is root:
            out.append((w.text(), type(w).__name__))
    for a in root.findChildren(QAction):
        if a.text() and _owner_window(a) is root:
            out.append((a.text(), "QAction"))
    return out


def _has_lone_ampersand(text: str) -> bool:
    """有沒有一個**沒有成對**的 ``&``（那一個會被 Qt 吃掉）。

    ``&&`` 是「畫一個 &」的寫法，成對的要先拿掉再看剩下什麼。
    """
    return "&" in str(text).replace("&&", "")


def test_no_label_eats_its_own_ampersand(window):
    """畫出來的字要跟寫下去的一樣。

    ``"Run all & write"`` 在畫面上是 ``Run all _write``：``&`` 不見了，
    後面多一條底線。這個 repo 沒有在用助憶鍵（一顆都沒有），所以**任何**
    落單的 ``&`` 都是這個 bug，不是刻意的。
    """
    bad = [t for t, _kind in _labels(window) if _has_lone_ampersand(t)]
    bad += [t for t, _kind in _labels(window.results)
            if _has_lone_ampersand(t)]
    assert not bad, "這些字會被 Qt 吃掉一個 &：%r" % (bad,)


def test_running_the_whole_batch_has_exactly_one_entry_point_per_window(window):
    """一個視窗上，「跑整批然後寫出去」只有一個入口。

    以前工具列上有一顆 ``Run all & write``，而 ``Run trial ▾`` 的選單裡也有
    一項「跑整批」—— **兩邊都是 `run_all()`**。兩個決定各自都對，只是沒有
    互相看到（M7 把全跑收進下拉、F16 Stage 5c 把 Export… 空出來的那一格改成
    整批入口）。

    Results 視窗上那一顆**留著**，而且是刻意的：使用者正在看試跑的結果，
    下一步才是整批 —— 那是同一個動作在**另一個視窗**上的入口，不是同一個
    畫面上的第二顆鈕。
    """
    main = [t for t, _k in _labels(window) if "Run all" in t]
    assert main == ["Run all && write"], main

    res = [t for t, _k in _labels(window.results) if "Run all" in t]
    assert res == ["Run all && write"], res


def test_the_two_entry_points_call_the_same_thing_and_read_the_same(window):
    """兩個入口的字**逐字相同** —— 同一個動作叫兩個名字是它變成兩顆鈕的第一步。"""
    assert window.act_run_all.text() == window.results.btn_run_all.text()


def test_the_toolbar_kept_only_one_primary_action(window):
    """工具列上唯一的主要動作是 ``Run trial``（它的 ▾ 是同一件事的另一半）。"""
    coloured = [b.text() or "(▾)"
                for b in window.toolbar.findChildren(QAbstractButton)
                if b.objectName() == "primary"
                or b.property("variant") == "secondary"]
    assert coloured == ["Run trial", "(▾)"], coloured


# --------------------------------------------------------------------------- #
# 掃原始碼：畫面上的字不只在主視窗的工具列上
# --------------------------------------------------------------------------- #
#: 會把字**當成按鈕標籤畫出來**的呼叫（這些會做助憶鍵處理）。
#:
#: ⚠ 這份名單是**白名單而不是黑名單**，而那是這條測試唯一能站得住的形狀：
#: 同一個 `&` 在別的地方是完全正確的。實際踩到的三種：
#:
#: * ``setWindowTitle("Template & regions")`` —— 視窗標題**不做**助憶鍵處理，
#:   寫成 ``&&`` 反而會畫出兩個 ``&``；
#: * ``QPainter.drawText(...)``（`inspectors.EmptyState`）—— 沒有帶
#:   ``Qt.TextShowMnemonic`` 就是照字面畫；
#: * tooltip —— 同上。
LABEL_CALLS = (
    "setText", "setTitle", "setPlaceholderText",
    "QAction", "QPushButton", "QToolButton", "QCheckBox", "QRadioButton",
    "QLabel", "small_button", "addAction",
)


def _label_literals():
    """``d4t/ui`` 裡所有「會被當成按鈕標籤畫出來」的字面字串。"""
    import ast

    out = []
    for path in sorted((REPO / "d4t" / "ui").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name not in LABEL_CALLS:
                continue
            for arg in list(node.args) + [k.value for k in node.keywords]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    out.append((path.name, arg.lineno, arg.value))
    return out


def test_no_button_label_anywhere_eats_its_own_ampersand():
    """主視窗掃不到的那些也要掃 —— 卡片上的按鈕只在選到那張卡時才存在。

    實測漏掉的正是這一種：`widgets.TemplatePicker` 的
    ``Edit template & regions…``（畫出來是 ``Edit template _regions…``）。
    它不在任何一個開機就存在的視窗上，所以執行期那一條看不到它。
    """
    bad = ["%s:%d %r" % (f, n, t) for f, n, t in _label_literals()
           if _has_lone_ampersand(t)]
    assert not bad, "這些字會被 Qt 吃掉一個 &：\n%s" % "\n".join(bad)


def test_the_source_scan_is_not_vacuous():
    """白名單真的掃得到東西 —— 否則上面那條永遠是綠的。"""
    found = _label_literals()
    assert len(found) > 100, len(found)
    assert any("&&" in t for _f, _n, t in found), \
        "一個成對的 && 都沒掃到，白名單八成漏了真正在用的那些呼叫"


def test_no_separator_fences_off_an_empty_stretch_of_toolbar(window):
    """分隔線講的是「這裡換一種事情」—— 隔開空氣的那一條只是雜訊。

    這一條是**拿掉重複那顆鈕時自己種的**：「Templates…」平常是藏著的
    （`scope.SHOW_SAMPLE_ENTRIES`），而它那一段本來還有「Run all & write」
    撐著。那顆走了之後那一段變成空的，工具列上就出現兩條連在一起的分隔線。
    """
    # ⚠ 這一條**一定要先 `show()`**：沒有顯示過的視窗底下，每一個子元件的
    # 可見性都答不準（第一版量出來是「三條分隔線、一個元件都沒有」）。
    # 而這裡問的正是「畫出來長什麼樣」—— 那就得真的畫一次。
    window.show()
    QApplication.instance().processEvents()
    kinds = []
    for act in window.toolbar.actions():
        if act.isSeparator():
            kinds.append("|")
            continue
        w = window.toolbar.widgetForAction(act)
        if w is None or not w.isVisible():
            continue
        kinds.append("w")
    window.hide()
    joined = "".join(kinds)
    assert "||" not in joined, joined
    assert not joined.startswith("|") and not joined.endswith("|"), joined

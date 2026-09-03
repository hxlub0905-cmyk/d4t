# 焦點環只在鍵盤導覽時出現（F80）。
"""按完一顆鈕，它不該留著一圈藍框。

`QPushButton` 預設是 `Qt::StrongFocus` —— 滑鼠點一下它就拿到焦點，而 QSS 的
`:focus` 對滑鼠點擊一樣生效。於是按完「Run trial」之後那顆按鈕留著一圈 2px 的
藍框，看起來像「還在啟用中」，要再點畫布上別的地方才甩得掉。

焦點環是**給鍵盤使用者的路標**；用滑鼠的人自己知道剛剛點了哪裡。CSS 有
`:focus-visible` 表達這件事，Qt 沒有 —— `d4t/ui/focus_visible.py` 補的就是它。

這個檔案問四件事：

1. 鍵盤走過去 → 有環；滑鼠點下去 → 沒有環。
2. **文字輸入不受影響** —— 點進一個輸入框卻沒有任何邊框變化是錯的。
3. 樣式表與餵它屬性的那支東西**一起到**（分開的話環從此不出現，而且不報錯）。
4. 過濾器活得比裝它的那一行久（`QApplication` 不持有它的所有權）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _import_qt(g):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QColor, QFocusEvent, QMouseEvent, QPixmap
    from PySide6.QtWidgets import (
        QApplication, QLineEdit, QPushButton, QVBoxLayout, QWidget,
    )

    from d4t.ui import focus_visible as fv_mod
    from d4t.ui import theme as theme_mod
    g.update(QEvent=QEvent, QPointF=QPointF, Qt=Qt, QColor=QColor,
             QFocusEvent=QFocusEvent,
             QMouseEvent=QMouseEvent, QPixmap=QPixmap, QApplication=QApplication,
             QLineEdit=QLineEdit, QPushButton=QPushButton,
             QVBoxLayout=QVBoxLayout, QWidget=QWidget,
             fv_mod=fv_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


#: 中性灰背板：兩個主題都不會剛好同色。
BACKDROP = "#808080"


def _host(qapp, focus_first=True):
    """一個有「別處」可以放焦點的小視窗，回 ``(host, decoy, button)``。"""
    host = QWidget()
    lay = QVBoxLayout(host)
    decoy = QPushButton("elsewhere", host)
    lay.addWidget(decoy)
    button = QPushButton("Run trial", host)
    lay.addWidget(button)
    host.show()
    qapp.processEvents()
    host.activateWindow()
    if focus_first:
        decoy.setFocus(Qt.TabFocusReason)
        qapp.processEvents()
    return host, decoy, button


def _ring_pixels(button):
    """按鈕最外那一圈裡，有多少格是焦點環的顏色。"""
    button.resize(140, 30)
    pm = QPixmap(button.size())
    pm.fill(QColor(BACKDROP))
    button.render(pm)
    img = pm.toImage()
    want = QColor(theme_mod.TOKENS["border_focus"])
    n = 0
    for y in range(6, 24):                    # 避開圓角
        for x in (0, 1, 138, 139):
            c = img.pixelColor(x, y)
            if (abs(c.red() - want.red()) + abs(c.green() - want.green())
                    + abs(c.blue() - want.blue())) <= 24:
                n += 1
    return n


# --------------------------------------------------------------------------- #
# 1. 鍵盤有環、滑鼠沒有
# --------------------------------------------------------------------------- #
def test_tabbing_to_a_button_shows_the_ring(qapp):
    host, _decoy, button = _host(qapp)
    button.setFocus(Qt.TabFocusReason)
    qapp.processEvents()

    assert button.property(fv_mod.PROP) is True
    assert _ring_pixels(button) > 20, "Tab 過去卻沒有焦點環 —— 鍵盤路徑看不見了"
    host.hide()


def test_clicking_a_button_leaves_no_ring_behind(qapp):
    """**這一輪的原始症狀。** 按完一顆鈕，它不該留著一圈藍框。"""
    host, _decoy, button = _host(qapp)
    button.setFocus(Qt.MouseFocusReason)      # 滑鼠點擊給的正是這個 reason
    qapp.processEvents()

    assert button.hasFocus() is True, "前提不成立：這顆按鈕根本沒拿到焦點"
    # 沒設過是 None、設過是 False —— QSS 的 `[kbFocus="true"]` 兩個都不匹配，
    # 所以這裡問的是「不是 true」而不是「等於 False」。
    assert not button.property(fv_mod.PROP)
    assert _ring_pixels(button) == 0, "點完之後那圈藍框還在"
    host.hide()


def test_the_premise_of_this_whole_feature_still_holds(qapp):
    """為什麼會有這個 bug：**滑鼠點一下按鈕，它真的會拿到焦點。**

    ⚠ 這件事在離屏平台上**驗不到** —— 派送真的滑鼠事件之後 `hasFocus()` 仍然
    是 False（實測），所以「點擊 → 焦點 → 留下一圈框」那條完整路徑只有在真的
    視窗系統上跑得出來。這裡改成釘住它的兩個前提，那是 headless 問得到的：

    1. `QPushButton` 預設是 `StrongFocus`（所以點擊會拿焦點 —— 如果哪天 Qt 或
       我們把它改成 `NoFocus`，這個功能就沒有存在的必要了）。
    2. `MouseFocusReason` **不在**我們的鍵盤清單裡（翻譯表本身）。

    第 1 條也順便說明工具列為什麼不受這個症狀影響：`QToolButton` 預設是
    `TabFocus` —— **鍵盤到得了、滑鼠不給焦點**。（所以它的規則還是要 gate：
    Tab 過去的人要看得到自己在哪裡。）
    """
    from PySide6.QtWidgets import QToolButton

    host, _decoy, button = _host(qapp)
    assert button.focusPolicy() == Qt.StrongFocus, (
        "QPushButton 不再是 StrongFocus —— 點擊不會拿焦點，這個功能可以拿掉了")
    host.hide()

    tb = QToolButton()
    assert tb.focusPolicy() == Qt.TabFocus, (
        "QToolButton 的 focusPolicy 變成 %s —— 它以前是 TabFocus"
        "（鍵盤到得了、滑鼠不給焦點），變成含 ClickFocus 的話工具列那一排也會"
        "開始留框" % tb.focusPolicy())

    assert Qt.MouseFocusReason not in fv_mod.KEYBOARD_REASONS
    assert Qt.TabFocusReason in fv_mod.KEYBOARD_REASONS


def test_the_ring_comes_back_when_you_tab_again(qapp):
    """點過之後再 Tab 回來，環要回來 —— 屬性不能卡在 false。"""
    host, decoy, button = _host(qapp)
    button.setFocus(Qt.MouseFocusReason)
    qapp.processEvents()
    decoy.setFocus(Qt.TabFocusReason)
    qapp.processEvents()
    button.setFocus(Qt.TabFocusReason)
    qapp.processEvents()

    assert button.property(fv_mod.PROP) is True
    assert _ring_pixels(button) > 20
    host.hide()


def test_switching_windows_does_not_take_the_ring_away(qapp):
    """視窗切出去再切回來不是「使用者在移動焦點」。

    把 `ActiveWindowFocusReason` 當成滑鼠的話，Tab 到一半去看別的視窗、
    回來環就沒了 —— 而使用者的手還在鍵盤上。
    """
    host, _decoy, button = _host(qapp)
    button.setFocus(Qt.TabFocusReason)
    qapp.processEvents()
    assert button.property(fv_mod.PROP) is True

    # 真的模擬「視窗失去作用 → 取得作用」那一對事件。
    # 不能用 `clearFocus()` —— 它送的是 OtherFocusReason（我們**算**鍵盤），
    # 那樣測到的是另一條路。
    QApplication.sendEvent(
        button, QFocusEvent(QEvent.FocusOut, Qt.ActiveWindowFocusReason))
    QApplication.sendEvent(
        button, QFocusEvent(QEvent.FocusIn, Qt.ActiveWindowFocusReason))
    qapp.processEvents()

    assert button.property(fv_mod.PROP) is True, "切回視窗把焦點環吃掉了"
    host.hide()


# --------------------------------------------------------------------------- #
# 2. 文字輸入不受影響
# --------------------------------------------------------------------------- #
def test_a_text_field_still_shows_where_you_are_typing(qapp):
    """**輸入框刻意不走 focus-visible。**

    點進一個輸入框卻沒有任何邊框變化是錯的：游標在那裡閃，而「我現在打的字
    會進哪一格」需要那條框說出來。瀏覽器的 `:focus-visible` 對文字輸入也是
    永遠成立。所以這一條問的是 QSS —— 輸入框那條規則**沒有**被 gate 住。
    """
    import re

    qss = re.sub(r"/\*.*?\*/", "", theme_mod.build_stylesheet(), flags=re.S)
    guilty = []
    for sel, _decls in re.findall(r"([^{}]+)\{([^{}]*)\}", qss):
        sel = " ".join(sel.split())
        if ":focus" not in sel:
            continue
        text_input = any(w in sel for w in ("QLineEdit", "QSpinBox",
                                            "QDoubleSpinBox", "QComboBox",
                                            "QPlainTextEdit", "QTextEdit"))
        if text_input and "kbFocus" in sel:
            guilty.append(sel)
    assert guilty == [], (
        "文字輸入的 :focus 被 gate 住了：%s —— 用滑鼠點進去會看不出焦點在哪"
        % guilty)


def test_every_button_focus_rule_is_gated(qapp):
    """反過來：按鈕那一邊**一條都不能漏**。

    漏掉的那一條會留著舊行為（點完留一圈框），而畫面上其他按鈕都正常 ——
    那種「只有某一顆怪怪的」最難查。
    """
    import re

    qss = re.sub(r"/\*.*?\*/", "", theme_mod.build_stylesheet(), flags=re.S)
    missing = []
    for sel, _decls in re.findall(r"([^{}]+)\{([^{}]*)\}", qss):
        sel = " ".join(sel.split())
        if ":focus" not in sel:
            continue
        if not re.search(r"QPushButton|QToolButton", sel):
            continue
        if "kbFocus" not in sel:
            missing.append(sel)
    assert missing == [], "這些按鈕的 :focus 沒有 gate：%s" % missing


# --------------------------------------------------------------------------- #
# 3-4. 安裝這件事本身
# --------------------------------------------------------------------------- #
def test_the_sheet_and_the_thing_that_feeds_it_arrive_together(qapp):
    """`apply_theme` 一定要把過濾器裝上。

    分開的話會有一種很難查的狀態：QSS 裡的 `[kbFocus="true"]:focus` 永遠沒有
    人把那個屬性設成 true，於是**焦點環從此不會出現**，而畫面上沒有任何錯誤。
    """
    assert theme_mod.build_stylesheet().count("kbFocus") > 0
    assert getattr(qapp, "_d4t_focus_visible", None) is not None


def test_installing_twice_does_not_stack_filters(qapp):
    """換一次主題就多裝一支的話，一顆焦點事件會被處理很多次。"""
    first = fv_mod.install(qapp)
    theme_mod.apply_theme(qapp, "dark")
    theme_mod.apply_theme(qapp, "light")
    assert fv_mod.install(qapp) is first


def test_the_filter_outlives_the_line_that_installed_it(qapp):
    """`QApplication` 不持有過濾器的所有權。

    本地變數一離開作用域就被回收，而**症狀是「有時候有環有時候沒有」** ——
    沒有錯誤訊息。所以它要有人抓著（`install` 把它掛回 app 身上）。
    """
    import gc

    gc.collect()
    filt = getattr(qapp, "_d4t_focus_visible", None)
    assert filt is not None
    host, _decoy, button = _host(qapp)
    button.setFocus(Qt.TabFocusReason)
    qapp.processEvents()
    assert button.property(fv_mod.PROP) is True, "過濾器被回收了"
    host.hide()

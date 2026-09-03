# 焦點環只在鍵盤導覽時出現（F80）。
"""按完一顆鈕，它不該留著一圈藍框。

症狀
----
``QPushButton`` 預設是 ``Qt::StrongFocus`` —— **滑鼠點一下它就拿到焦點**，
而 QSS 的 ``:focus`` 對滑鼠點擊一樣生效。於是按完「Run trial」之後，那顆按鈕
留著一圈 2px 的藍框，看起來像「還在啟用中」；使用者要再點畫布上別的地方才
把它甩掉。

（工具列不會有「按完留一圈框」這個症狀：``QToolButton`` 預設是
``Qt::TabFocus`` —— **鍵盤到得了、滑鼠不給焦點**。但正因為鍵盤到得了，它的規則
還是要一起 gate，否則 Tab 到工具列的人會看不到自己走到哪裡。）

桌面與網頁的慣例都是：焦點環是**給鍵盤使用者的路標**，用滑鼠的人不需要它，
因為他自己知道剛剛點了哪裡。CSS 有 ``:focus-visible`` 表達這件事，Qt 沒有。

做法
----
一支裝在 ``QApplication`` 上的事件過濾器：看 ``QFocusEvent.reason()``，
把「這一次焦點是不是從鍵盤來的」寫成 widget 的一個 ``kbFocus`` 屬性，
QSS 那邊改成 ``[kbFocus="true"]:focus``。

三件事值得寫下來：

* **文字輸入不走這條路。** ``QLineEdit`` / ``QSpinBox`` / ``QComboBox`` 的
  ``:focus`` 保持原樣 —— 點進一個輸入框卻沒有任何邊框變化是**錯的**：游標在
  那裡閃，而「我現在打的字會進哪一格」需要那條框說出來。瀏覽器的
  ``:focus-visible`` 也是這樣（文字輸入永遠算 visible）。所以這裡只管按鈕。
* **改屬性不會自己重畫。** 外觀住在 QSS，屬性一動要 ``unpolish``/``polish``
  才會重新套規則 —— 少這一步等於完全沒反應（`test_the_stage_button_repolishes_
  when_it_opens` 記的是同一個坑）。
* **切出去再切回來不算滑鼠。** 視窗失去／取得作用時 Qt 會送
  ``ActiveWindowFocusReason``，那不是使用者在移動焦點 —— 那時候**維持原狀**，
  否則 Tab 到一半去看別的視窗，回來環就沒了。

安裝在哪
--------
:func:`theme.apply_theme` —— 樣式表與餵給它屬性的那支東西**必須一起到**。
分開的話會有一種很難查的狀態：QSS 裡的 ``[kbFocus="true"]:focus`` 永遠沒有人
把那個屬性設成 true，於是**焦點環從此不會出現**，而畫面上沒有任何錯誤。
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QWidget

__all__ = ["KEYBOARD_REASONS", "FocusVisibleFilter", "install"]

#: 算「鍵盤在移動焦點」的理由。
#:
#: ``OtherFocusReason`` 是程式呼叫 ``setFocus()`` 不帶參數時給的 —— 對話框開起來
#: 把焦點放在第一個控制項上走的正是這一條，而**那時候鍵盤使用者最需要那個環**
#: （他還沒按過任何鍵，畫面得先告訴他起點在哪）。
KEYBOARD_REASONS = (
    Qt.TabFocusReason,
    Qt.BacktabFocusReason,
    Qt.ShortcutFocusReason,
    Qt.MenuBarFocusReason,
    Qt.OtherFocusReason,
)

#: 這個屬性名字同時寫在 QSS 的選擇器裡（``[kbFocus="true"]``）—— 兩邊要一致。
PROP = "kbFocus"


def _apply(widget, visible: bool) -> None:
    # **一定要問是不是 widget。** 裝在 QApplication 上的過濾器看得到送給
    # **所有**物件的事件，而焦點事件也會經過非 widget 的物件（實測會拿到
    # `QCommonStyle`）—— 不擋的話 `widget.style()` 當場 AttributeError，
    # 而那個例外是從 `eventFilter` 裡丟出來的，訊息會層層包起來很難讀。
    if not isinstance(widget, QWidget):
        return
    if bool(widget.property(PROP)) == bool(visible):
        return
    widget.setProperty(PROP, bool(visible))
    style = widget.style()
    if style is not None:                     # 外觀住在 QSS：不 repolish 等於沒改
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


class FocusVisibleFilter(QObject):
    """把 ``QFocusEvent.reason()`` 翻譯成 ``kbFocus`` 屬性。"""

    def eventFilter(self, obj, event) -> bool:    # noqa: D102 - Qt hook
        etype = event.type()
        if etype == QEvent.FocusIn:
            reason = event.reason()
            # 視窗切出去再切回來：不是使用者在移動焦點，維持原狀。
            if reason != Qt.ActiveWindowFocusReason:
                _apply(obj, reason in KEYBOARD_REASONS)
        elif etype == QEvent.FocusOut:
            if event.reason() != Qt.ActiveWindowFocusReason:
                _apply(obj, False)
        return False                              # 從不吃掉事件


def install(app) -> "FocusVisibleFilter":
    """裝到 ``app`` 上（重複呼叫只裝一次）。

    過濾器存回 app 身上：``QApplication`` 不持有過濾器的所有權，本地變數一
    離開作用域就被回收，而**症狀是「有時候有環有時候沒有」** —— 沒有錯誤訊息。
    """
    existing = getattr(app, "_d4t_focus_visible", None)
    if existing is not None:
        return existing
    filt = FocusVisibleFilter(app)
    app.installEventFilter(filt)
    app._d4t_focus_visible = filt
    return filt

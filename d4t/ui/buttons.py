# 到處都用得到的那幾個小元件 — 從 widgets.py 搬出來 2026-09-08 (U7).
"""按鈕的小工具、一顆可移除的條件 chip、以及「停放而不銷毀」。

U7 那一刀把 `widgets.py` 拆開之後，**這一支是最底層的那一塊**：拆出去的每一
個模組（`library` / `chips` / `fields` / …）都用得到 `small_button`，而它們
不能反過來 import `widgets`（那是轉出口，會繞回來）。

所以這裡**只放沒有上游的東西** —— 它只 import Qt 與 `theme`。加東西進來之前
先問：它會不會需要 import 另一個 UI 模組？會的話它不屬於這裡。

這一份是**純搬移**：每一行都是原封搬過來的，一個字都沒有改。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialogButtonBox, QPushButton, QSizePolicy, QWidget,
)

from . import strings

__all__ = ["small_button", "FilterChip", "clear_layout_parked",
           "mark_primary"]


def mark_primary(box: QDialogButtonBox) -> Optional[QPushButton]:
    """一排對話框鈕裡，**把「答應」那一顆標成主要動作**（F117 I12）。

    走查記的是「範本庫的 `Load` 是藍的、Chart settings 的 `OK` 是白的」。
    原因不是有人選了兩種樣式，是**兩種來路**：自己 `QPushButton` 再
    `setObjectName("primary")` 的都是藍的，而 `QDialogButtonBox` 生出來的
    那一顆沒有人去標。同一個畫面上「按這裡完成」因此有兩種長相。

    ⚠ **只標 Accept 那一顆。** 一排 `Close` 的 box（看一看就關掉那種）**沒有
    主要動作** —— 硬標一顆藍的，等於把「離開」講成「完成」。

    回傳被標的那顆（沒有就 ``None``），方便呼叫端再改字。
    """
    btn = box.button(QDialogButtonBox.Ok) or box.button(QDialogButtonBox.Apply)
    if btn is None:
        for b in box.buttons():
            if box.buttonRole(b) == QDialogButtonBox.AcceptRole:
                btn = b
                break
    if btn is None:
        return None
    btn.setObjectName("primary")
    # ⚠ **改了 objectName 要重算樣式**：Qt 的 QSS 是在 polish 的時候比對
    # selector 的，而這顆鈕早就 polish 過了 —— 不 unpolish 的話它會留在白色，
    # 而程式碼看起來完全正確。
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    return btn



# --------------------------------------------------------------------------- #
# 按鈕的兩個小工具（F7-23 第二輪）
# --------------------------------------------------------------------------- #
def small_button(text: str, tip: str = "", parent: Optional[QWidget] = None,
                 shape: str = "square", kind: str = "ghost") -> QPushButton:
    """一顆小按鈕（卡片控制、畫布縮放、換 defect、Card/Features 切換）。

    **尺寸不在這裡填。** ``shape`` 只說「方的還是帶文字的」，實際邊長由 QSS 的
    ``control_sm`` 決定 —— 以前六個呼叫端各自寫死一組尺寸（22×22、24×22、
    30×22、寬 28、寬 40、高 20），於是同一種視覺語言沒有兩顆一樣大。

    ``kind="icon"`` 給浮在畫布或影像上的那幾顆一個自己的底：那裡沒有卡片當
    底色，透明的按鈕要滑到才看得出是按鈕（同 F7-13 給工具列加邊框的理由）。
    """
    # 翻譯層擺在共用的那一支（U14）—— 卡片控制、畫布縮放、換 defect、
    # Card/Features 全部流過這裡。**卡片名不走這條路**：它是 `Step.label`，
    # 由 ParamForm 與畫布自己畫（見 `ui/strings.py` 的「不翻譯的兩類」）。
    text = strings.tr(text)
    tip = strings.tr(tip) if tip else tip
    b = QPushButton(text, parent)
    b.setObjectName("cardButton")
    b.setProperty("shape", str(shape))
    b.setProperty("kind", str(kind))
    b.setCursor(Qt.PointingHandCursor)
    if tip:
        b.setToolTip(str(tip))
    return b


class FilterChip(QPushButton):
    """一顆可移除的條件 chip：``排序：score ↓  ✕``。點一下就把該條件拿掉。

    PR-3 從 `gallery._Chip` 升格搬來（結果表的維度過濾也要 chip，而同一種
    視覺語言只能有一份）。objectName 沿用 ``galleryChip`` —— 外觀的家在 QSS 的
    ``QPushButton#galleryChip``（F7-23 第三輪），名字跟著搬會讓兩邊各長一份
    樣式。
    """

    def __init__(self, text: str, tip: str, parent: Optional[QWidget] = None):
        # ``×`` 是 U+00D7（Latin-1），不是 U+2715 那個 Dingbats 的 ``✕`` ——
        # 後者在 Windows 上要退到 Segoe UI Symbol（F7-23 第四輪）。
        super().__init__("%s  ×" % text, parent)
        self.setObjectName("galleryChip")
        self.label_text = text
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tip)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


def clear_layout_parked(layout, graveyard: list) -> None:
    """把 ``layout`` 裡的 widget 全部拿下來 —— **停放，不銷毀**（F25）。

    為什麼不能直接 ``setParent(None)``
    ---------------------------------
    這幾個面板（判定、判定樹的一步、分流）是「改一格就整段重建」的：
    使用者動了某一格 → 那一格的訊號寫進 model → model 的 listener 打回來
    → 面板重建 → **舊的那一格就是正在發訊號的那一個**。

    ``setParent(None)`` 之後 Python 就是它唯一的持有者，而 layout item 一丟
    參考數歸零 → C++ 物件當場解構 —— 而 Qt 的訊號還在那個物件的堆疊上。
    那是 use-after-free：跑得完的時候什麼事都沒有，跑不完的時候是**閃退**，
    而且跟平台的事件流有關（offscreen 重現不出來，真機上「有機會」發生）。
    使用者 2026-08-24 回報的正是這個形狀：「輸入 bin 有機會閃退」。

    所以這裡只做兩件事：把它藏起來、把它從版面上拿掉，**參考留著**。
    真正的解構排到下一輪 event loop（那時候訊號早就返回了）。

    ``graveyard`` 是呼叫端持有的一個 list —— 停屍間必須活得比這一次事件久，
    所以它不能是這支函式裡的區域變數。
    """

    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is None:
            sub = item.layout()
            if sub is not None:
                clear_layout_parked(sub, graveyard)
            continue
        w.hide()
        w.setParent(None)
        graveyard.append(w)
    if graveyard:
        # 排到下一輪：這一輪的訊號返回之後才真的釋放。
        QTimer.singleShot(0, graveyard.clear)

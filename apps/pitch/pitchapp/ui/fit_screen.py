# 視窗要裝得進廠內那台螢幕 — authored 2026-09-08 (U1).
"""**寫死的視窗尺寸在 1366×768 的機台旁 PC 上放不下，而 Qt 不會自己捲。**

症狀
----
2026-09-08 量的：`ui/app.py` 開窗 ``resize(1440, 900)``、主視窗最小高 760、
對話框一律寫死（chart_settings 1180×940、template_dialog 1320×880、
gc_generator 1060×900、graph_builder 720×780）。開發機是 1920×1080，所以這
件事在開發時**看不出來**；而目標機器是機台旁那台 PC。

放不下的下場不是「小一點」，是**按鈕在螢幕外面**：Qt 的視窗可以比螢幕大，
底部那一排 OK / Cancel 就在畫面下緣以下，而畫面上沒有任何東西說它在那裡。

三件事，順序有意義
------------------
1. **最小尺寸先降**（:func:`relax_minimum`）。Qt 不會把視窗縮到比
   ``minimumSizeHint`` 小 —— 所以一個 ``setMinimumHeight(760)`` 的視窗在
   一個可用高 728 的螢幕上，``resize()`` 是**沒有效果**的。先降它，
   後面兩步才有意義。
2. **要多大取小的那個**（:func:`fit`）：``min(想要的, 可用的 × 0.9)``。
   留 10% 是給工作列與視窗邊框 —— ``availableGeometry`` 已經扣掉工作列了，
   這 10% 扣的是**視窗自己的邊框與標題列**，那個 Qt 量不到（視窗還沒有被
   視窗管理員貼上裝飾）。
3. **推回螢幕裡**（:func:`keep_on_screen`）：置中對齊父視窗的那些對話框，
   在父視窗本身靠邊的時候會開到螢幕外面去。

還有一條退路：:func:`scroll_host`
---------------------------------
內容本身就比螢幕高的對話框（`graph_builder` 那種一路疊下來的），縮視窗沒有
用 —— 內容的 ``minimumSizeHint`` 撐在那裡。那種要在**建構的時候**把內容放進
一個 `QScrollArea`，見 :func:`scroll_host` 的用法。

⚠ **不要事後把既有版面搬進捲軸。** 「把 ``dialog.layout()`` 偷出來塞進一個
新的 content widget」那個寫法在 PySide6 上是 **segfault**（2026-09-08 實測），
不是例外。捲軸要在建構時就決定。
"""
from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import (
    QApplication, QFrame, QScrollArea, QVBoxLayout, QWidget,
)

__all__ = [
    "SCREEN_FRACTION", "FORCE_RECT", "available_rect", "relax_minimum", "fit",
    "keep_on_screen", "scrolled", "scroll_host", "scroll_row",
    "fits_on_screen",
]

#: **測試用的假螢幕**（``None`` = 用真的那個）。
#:
#: 為什麼要有這個鉤子：這件事要驗的是「1366×768 上放不放得下」，而測試跑在
#: offscreen 平台上，那個平台的螢幕是 800×800 —— 一個誰也沒有的尺寸。沒有
#: 這個鉤子的話，唯一能驗的就是「在這台 CI 上放得下」，而那句話對機台旁那
#: 台 PC 什麼都沒有保證。
#:
#: 跟 `studio.PROMPT_ON_CLOSE` / `canvas.ANIMATE` 同一種東西：**一個具名的
#: 開關，預設是真的行為**，測試自己開自己關。
FORCE_RECT: Optional[QRect] = None

#: 視窗最多佔可用區域的幾成。
#:
#: 0.9 不是美感：``availableGeometry()`` 扣掉的是工作列，**扣不掉視窗自己的
#: 標題列與邊框** —— 那要等視窗被視窗管理員裝飾之後才量得到，而那時已經太
#: 晚了。10% 是那一圈裝飾的餘裕，在 1366×768 上約 76 px 高，比任何一個桌面
#: 環境的標題列都寬裕。
SCREEN_FRACTION = 0.9


def available_rect(widget: Optional[QWidget] = None) -> QRect:
    """這個 widget 所在螢幕的可用區域（沒有螢幕資訊時回一個保守的 1024×720）。

    **跟著 widget 走**而不是一律用主螢幕：雙螢幕的機器上，對話框開在父視窗
    那一面，而兩面的解析度可以差很多。
    """
    if FORCE_RECT is not None:
        return QRect(FORCE_RECT)
    screen = None
    if widget is not None:
        handle = widget.window().windowHandle()
        screen = handle.screen() if handle is not None else None
        if screen is None:
            screen = QApplication.screenAt(widget.window().pos())
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:                      # pragma: no cover — 沒有螢幕的環境
        return QRect(0, 0, 1024, 720)
    rect = screen.availableGeometry()
    return rect if rect.width() > 0 and rect.height() > 0 \
        else QRect(0, 0, 1024, 720)


def relax_minimum(widget: QWidget, rect: Optional[QRect] = None,
                  fraction: float = SCREEN_FRACTION) -> None:
    """把「最小尺寸」降到裝得進螢幕 —— **`fit` 之前一定要先做這一步**。

    只降不升：螢幕夠大的時候這一支什麼都不做，所以 1920×1080 上的行為
    一個像素都沒有變。
    """
    r = available_rect(widget) if rect is None else rect
    cap_w, cap_h = int(r.width() * fraction), int(r.height() * fraction)
    if widget.minimumWidth() > cap_w:
        widget.setMinimumWidth(cap_w)
    if widget.minimumHeight() > cap_h:
        widget.setMinimumHeight(cap_h)


def fit(widget: QWidget, width: int = 0, height: int = 0,
        fraction: float = SCREEN_FRACTION) -> Tuple[int, int]:
    """``resize(min(想要的, 可用的 × fraction))``，回傳真的用了多大。

    ``width`` / ``height`` 給 0 ＝「維持現在這個值」（給只想被裁掉、不想指定
    尺寸的呼叫者用）。

    這一支**取代 ``widget.resize(w, h)``**，而不是包在它外面：寫死的那一行
    在小螢幕上是錯的，留著它等於留一條會漂回去的路。
    """
    rect = available_rect(widget)
    relax_minimum(widget, rect, fraction)
    want_w = int(width) or widget.width()
    want_h = int(height) or widget.height()
    w = max(widget.minimumWidth(), min(want_w, int(rect.width() * fraction)))
    h = max(widget.minimumHeight(), min(want_h, int(rect.height() * fraction)))
    widget.resize(w, h)
    return w, h


def keep_on_screen(widget: QWidget) -> None:
    """視窗已經開出去了 → 推回可用區域裡（只動位置，不動大小）。

    對話框置中對齊的是**父視窗**，而父視窗自己可能靠著螢幕邊 —— 一個
    1200 px 寬的對話框對齊一個靠右的主視窗，右半就在螢幕外面。
    """
    rect = available_rect(widget)
    frame = widget.frameGeometry()
    x = min(max(frame.x(), rect.x()), max(rect.x(),
                                          rect.right() - frame.width() + 1))
    y = min(max(frame.y(), rect.y()), max(rect.y(),
                                          rect.bottom() - frame.height() + 1))
    if (x, y) != (frame.x(), frame.y()):
        widget.move(widget.x() + (x - frame.x()),
                    widget.y() + (y - frame.y()))


def fits_on_screen(widget: QWidget) -> bool:
    """這個視窗現在整個在可用區域裡嗎（測試與 `keep_on_screen` 的判準）。"""
    return available_rect(widget).contains(widget.frameGeometry())


def scroll_row(row: QWidget, parent: Optional[QWidget] = None) -> QScrollArea:
    """一列排不下的按鈕 → **橫向捲**（高度照它自己的，不長高）。

    為什麼不是「讓它換行」：那一列的順序有意義（工具由左到右是一段流程），
    換行之後第二列的第一顆看起來像另一組。橫向捲把「還有東西在右邊」講得出
    來，而且一個像素都不改變它在大螢幕上的樣子。

    小心 ``minimumSizeHint``：一個 1,023 px 寬的按鈕列會讓**整個對話框**縮
    不到 1,024 px 的螢幕裡（2026-09-08 實測的 `TemplateDialog` 就是這樣），
    而那件事在版面樹上看不出來 —— 它只是一列鈕。
    """
    area = QScrollArea(parent if parent is not None else row.parent())
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setWidget(row)
    hint = row.sizeHint().height()
    area.setMinimumHeight(hint)
    area.setMaximumHeight(hint + 14)      # 捲軸自己的高度
    return area


def scrolled(parent: Optional[QWidget] = None) -> Tuple[QScrollArea, QWidget]:
    """一個空的捲軸 ＋ 它裡面那個「東西要放進去」的 widget。

    **`QMainWindow` 用這一支**（它的 layout 是 Qt 自己的，不能再裝一個）::

        area, root = fit_screen.scrolled(self)
        self.setCentralWidget(area)
        grid = QGridLayout(root)

    `QDialog` / 一般 widget 用 :func:`scroll_host`，少一行。
    """
    area = QScrollArea(parent)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    content = QWidget(area)
    area.setWidget(content)
    return area, content


def scroll_host(window: QWidget, margins: Tuple[int, int, int, int] = (0, 0, 0, 0)
                ) -> QWidget:
    """**建構時**把一個視窗的內容包進捲軸；回傳「東西要放進去的那個 widget」。

    用法是把原本的 ::

        root = QVBoxLayout(self)

    換成 ::

        root = QVBoxLayout(fit_screen.scroll_host(self))

    子元件仍然可以用 ``self`` 當 parent 建 —— ``addWidget`` 會把它們接過去。

    ⚠ 兩件事：**事後**搬既有版面是 segfault（見模組說明），所以只能在建構時
    用；而 `QMainWindow` 要用 :func:`scrolled`，它的 layout 位置是 Qt 自己的。
    """
    area, content = scrolled(window)
    outer = QVBoxLayout(window)
    outer.setContentsMargins(*margins)
    outer.setSpacing(0)
    outer.addWidget(area)
    return content

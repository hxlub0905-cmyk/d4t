# 卡片庫那一欄 — 從 widgets.py 搬出來 2026-09-08 (U7).
"""三段式卡片庫（影像／算法／ADC）＋ 它的區塊標題、階段鈕與拖曳。

U7 那一刀：它跟 `widgets.py` 裡其餘 20 幾個類別沒有任何共用 —— 它吃
`Step.describe()` 的 dict 清單、發 `add_requested`，如此而已。

這一份是**純搬移**：每一行都是原封搬過來的，一個字都沒有改。

⚠ **階段的順序、標題與副標都不住在這裡**（U9，2026-09-08）：三樣東西的家是
`pipeline/step.py::GROUPS`，這一份只是把它接過來畫。`LibraryPanel.GROUPS`
那個常數已經不存在 —— 它曾經是 `GROUP_ORDER` 的第二份，靠
`test_ui_f16_stages.py` 綁著不漂，而一條測試是補丁不是解法。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import QMimeData, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
    QVBoxLayout, QWidget,
)

from ..core.pipeline.step import GROUPS as STAGE_GROUPS
from . import strings
from . import theme
from .buttons import clear_layout, small_button
from .icons import restyle
from .theme import TOKENS

__all__ = [
    "LibraryPanel", "StageButton", "GroupIcon", "CARD_MIME",
    "draw_group_icon", "column_header",
]



# --------------------------------------------------------------------------- #
# 3. LibraryPanel
# --------------------------------------------------------------------------- #
def draw_group_icon(p: QPainter, group: str, color: str, size: float) -> None:
    """在 ``p`` 的目前原點畫一個 ``size`` × ``size`` 的階段圖示。

    **抽成自由函式**，是為了讓左側 rail 的按鈕、卡片庫的區塊標題、以及畫布上的
    節點卡三處共用完全相同的圖形 —— 使用者在 rail 上看到的尺，在節點上看到的
    也要是同一把尺，不然「圖示」就只是裝飾而不是語言。

    不吃任何圖檔：repo 有「只放純文字檔」的不變量（公司機 DLP 會擋含二進位的
    壓縮檔，見 ``docs/HANDOVER.md`` §5）。``.svg`` 其實是純文字、過得了 DLP，
    但用 QPainter 連「要不要把圖檔加進版控」這個問題都不用問，而且顏色直接吃
    token —— 換主題時圖示自動跟著變。
    """
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), max(1.2, size / 11.0))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    w = h = float(size)
    m = w / 7.5                       # 邊界留白，隨尺寸縮放
    g = str(group)

    if g == "input":                    # 匣子 + 往下的箭頭
        p.drawRect(QRectF(m, h * 0.55, w - 2 * m, h * 0.45 - m))
        p.drawLine(QPointF(w / 2, m), QPointF(w / 2, h * 0.46))
        p.drawLine(QPointF(w / 2 - w * 0.16, h * 0.30), QPointF(w / 2, h * 0.46))
        p.drawLine(QPointF(w / 2 + w * 0.16, h * 0.30), QPointF(w / 2, h * 0.46))
    elif g == "enhance":                # 亮度：半實心圓
        p.drawEllipse(QRectF(m, m, w - 2 * m, h - 2 * m))
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawPie(QRectF(m, m, w - 2 * m, h - 2 * m), -90 * 16, 180 * 16)
    elif g == "region":                 # 取景框（四個角）+ 中心點
        c = w * 0.24
        for x0, y0, dx, dy in ((m, m, 1, 1), (w - m, m, -1, 1),
                               (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
            p.drawLine(QPointF(x0, y0), QPointF(x0 + c * dx, y0))
            p.drawLine(QPointF(x0, y0), QPointF(x0, y0 + c * dy))
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        r = w * 0.11
        p.drawEllipse(QRectF(w / 2 - r, h / 2 - r, 2 * r, 2 * r))
    elif g == "compare":                # 兩個交疊的方框
        side = w - 2 * m - w * 0.2
        p.drawRect(QRectF(m, m, side, side))
        p.drawRect(QRectF(m + w * 0.2, m + w * 0.2, side, side))
    elif g == "measure":                # 尺（一條線 + 刻度）
        base = h - m
        p.drawLine(QPointF(m, base), QPointF(w - m, base))
        for i in range(4):
            x = m + i * (w - 2 * m) / 3.0
            p.drawLine(QPointF(x, base),
                       QPointF(x, base - (h * 0.40 if i % 2 == 0 else h * 0.23)))
    elif g == "search":                 # 放大鏡（rail 上的搜尋鈕，不是流程階段）
        r = w * 0.29
        p.drawEllipse(QRectF(m, m, 2 * r, 2 * r))
        p.drawLine(QPointF(m + 2 * r * 0.86, m + 2 * r * 0.86),
                   QPointF(w - m, h - m))
    # ⚠ **這裡以前還有一顆 ``g == "algo"`` 的 Σ 圖示，2026-08-28 刪掉了**（F48）。
    # 它畫的是卡片庫的 Algo 那一段，而那一段 F24 §5 就從 `GROUPS` 拿掉、
    # F48 連 `GROUP_ALGO` 這個常數一起刪了 —— `GroupIcon` 只被兩個地方叫
    # （rail 的 StageButton 與區塊標題），兩邊的 gid 都來自 `step.GROUPS`，
    # 所以那一支 `elif` 再也走不到。**不是把它留成便利貼**：這個檔案裡的
    # 圖示是一段一顆，而「有圖示、沒有那一段」正好是下一個人會照著加卡的形狀。
    elif g == "adc":                    # 標籤：給這顆 defect 一個 bin
        # ADC 這一段的產物是 score + **bin**，而「貼上一個分類」就是標籤。
        # 尖的那一頭讓輪廓在 15 px 下仍然不像任何一個方框（region 是四個角、
        # compare 是兩個疊起來的框）。
        p.drawPolygon(QPolygonF([
            QPointF(m, h * 0.26), QPointF(w * 0.62, h * 0.26),
            QPointF(w - m, h / 2), QPointF(w * 0.62, h - h * 0.26),
            QPointF(m, h - h * 0.26)]))
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        r = w * 0.075                   # 標籤上的孔。實心的 —— 15 px 下描邊會糊掉
        p.drawEllipse(QRectF(m + w * 0.14 - r, h / 2 - r, 2 * r, 2 * r))
    elif g == "output":                 # 敞口的托盤 + 往外走的箭頭
        # 跟 ``input`` 是**一對**（跟 glyph 的 save / export 同一種對比）：
        # 一樣是托盤加箭頭，差別在**箭頭往哪走**，而那正好是這兩段唯一的差別。
        # 托盤這裡是**敞口的**（只有左、下、右三邊）—— input 那個是封起來的
        # 方匣（東西掉進去），output 是東西離開的地方，所以上緣不封。
        base = h - m
        p.drawLine(QPointF(m, h * 0.62), QPointF(m, base))
        p.drawLine(QPointF(m, base), QPointF(w - m, base))
        p.drawLine(QPointF(w - m, base), QPointF(w - m, h * 0.62))
        p.drawLine(QPointF(w / 2, h * 0.60), QPointF(w / 2, m))
        a = w * 0.17
        p.drawLine(QPointF(w / 2, m), QPointF(w / 2 - a, m + a))
        p.drawLine(QPointF(w / 2, m), QPointF(w / 2 + a, m + a))
    else:                               # 沒見過的 group：打勾（保底，不是某一段）
        p.drawLine(QPointF(m, h * 0.52), QPointF(w * 0.42, h - m))
        p.drawLine(QPointF(w * 0.42, h - m), QPointF(w - m, m))



def missing_words(missing) -> str:
    """卡片庫上「上游還沒有的影像流」那個灰字 badge 的字。

    ``["test"]`` → ``needs a “test” stream``；
    ``["test", "ref"]`` → ``needs “test” + “ref” streams``。
    """
    names = [str(m) for m in (missing or ()) if str(m)]
    if not names:
        return ""
    if len(names) == 1:
        return "needs a “%s” stream" % names[0]
    return "needs %s streams" % " + ".join("“%s”" % n for n in names)

class GroupIcon(QWidget):
    """:func:`draw_group_icon` 的 widget 包裝（給 rail 與區塊標題用）。"""

    _SIZE = 15

    def __init__(self, group: str, color: str, parent: Optional[QWidget] = None,
                 size: Optional[int] = None):
        super().__init__(parent)
        self.group = str(group)
        self.color = str(color)
        self._SIZE = int(size or self._SIZE)
        self.setFixedSize(self._SIZE, self._SIZE)

    def set_color(self, color: str) -> None:
        self.color = str(color)
        self.update()

    def paintEvent(self, _e) -> None:  # Qt hook
        p = QPainter(self)
        draw_group_icon(p, self.group, self.color, float(self._SIZE))
        p.end()


#: 從卡片庫拖出去時帶的 MIME 型別（F7-22）。用自訂型別而不是純文字：
#: 純文字會讓「從別的視窗拖一段字進畫布」也變成新增卡片。
CARD_MIME = "application/x-d4t-card"


class _LibraryItem(QFrame):
    """卡片庫的一列：名稱 + hover 才出現的「Add」；雙擊也能加入。

    ``set_missing(streams)`` 會把「上游還沒產出它要的影像流」這件事顯示成
    一個灰字 badge（例：``needs diff``）並把整列調淡 —— 但**仍然可以加**。
    卡片庫的順序不等於執行順序，使用者可能先放卡再補上游；擋著不給加只會
    讓人以為工具壞了。
    """

    activated = Signal(str)

    def __init__(self, describe: Dict[str, Any], color: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.step_key = str(describe.get("key", ""))
        self.reads = [str(r) for r in (describe.get("reads") or ())]
        self.setObjectName("libItem")
        self.setCursor(Qt.PointingHandCursor)
        self._base_tip = (str(describe.get("help", ""))
                          or str(describe.get("label", "")))
        if describe.get("requires_ref"):
            self._base_tip += " (needs a ref image)"
        self.setToolTip(self._base_tip)
        self.setProperty("missing", "false")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 3, 6, 3)
        lay.setSpacing(6)

        self.dot = QFrame()
        self.dot.setFixedSize(5, 5)
        # 5×5 的點：圓角是它自己的一半，不是 `radius_sm`（4px 會把它畫成一顆
        # 幾乎全圓的球）。半徑跟著上面那個 setFixedSize 走。
        self.dot.setStyleSheet("background:%s; border-radius:%dpx;"
                               % (color, 5 // 2))
        lay.addWidget(self.dot)

        self.label = QLabel(str(describe.get("label") or self.step_key))
        self.label.setToolTip(self._base_tip)
        lay.addWidget(self.label, 1)

        self.badge = QLabel("")
        self.badge.setObjectName("libBadge")
        self.badge.setVisible(False)
        self.missing: List[str] = []
        lay.addWidget(self.badge)

        self.add_button = small_button(
            "Add", "Append this card to the end of the pipeline", shape="wide")
        self.add_button.clicked.connect(
            lambda: self.activated.emit(self.step_key))
        self.add_button.setVisible(False)
        lay.addWidget(self.add_button)

    # -- 前置條件 badge -----------------------------------------------------
    def set_missing(self, missing: Sequence[str]) -> None:
        """``missing`` = 這張卡要讀、但上游還沒有的影像流。"""
        missing = [str(m) for m in (missing or ())]
        self.missing = list(missing)
        self.setProperty("missing", "true" if missing else "false")
        restyle(self)
        if missing:
            # **不印裸的流名**（F99 P1-4）：「needs test」會被讀成「需要測試」——
            # 而它的意思是「上游還沒有一條叫 test 的影像流」。名字加引號、
            # 說出它是一條 stream，那句話就只剩一種讀法。
            self.badge.setText(missing_words(missing))
            self.badge.setVisible(True)
            self.setToolTip(
                "%s\n\nNot available yet: this card reads %s, which nothing "
                "upstream produces so far. You can still add it — the pipeline "
                "order is up to you."
                % (self._base_tip, ", ".join(missing)))
        else:
            self.badge.setVisible(False)
            self.setToolTip(self._base_tip)

    def badge_text(self) -> str:
        """目前的 badge 文字（沒有就空字串）。

        看的是 :attr:`missing` 而不是 ``badge.isVisible()`` —— 視窗還沒 show()
        之前 Qt 的可見性一律是 False，headless 測試會全部誤判。
        """
        return self.badge.text() if self.missing else ""

    def enterEvent(self, e) -> None:  # Qt hook
        self.add_button.setVisible(True)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # Qt hook
        self.add_button.setVisible(False)
        super().leaveEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:  # Qt hook
        if e.button() == Qt.LeftButton:
            # 這一下不是要拖 —— 而第二次按下不會再進 `mousePressEvent`
            # （Qt 送的是 DblClick），所以按下那一點得在這裡自己收掉，
            # 不然它會留著當作起點（見 :meth:`mouseReleaseEvent`）。
            self._press_at = None
            self.activated.emit(self.step_key)

    # -- 拖到畫布上（F7-22）-------------------------------------------------
    #
    # 「Add」是**工具決定位置**（接在選著的那張後面）；拖是**使用者決定位置**。
    # 兩個都留著：n8n 兩種都有，而且第一次用的人多半先看到按鈕。
    def mousePressEvent(self, e) -> None:  # Qt hook
        if e.button() == Qt.LeftButton:
            self._press_at = e.pos()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:  # Qt hook
        """放開＝那一下結束了，按下的位置跟著作廢。

        ⚠ 這支以前不存在，而 `_press_at` 因此**跨得過一次點擊**：快速點兩下
        的時候，第一次按下留下的起點還在，第二下（DblClick）按著的那幾 px 抖動
        就湊得出拖曳的門檻 —— 畫面上是一張卡的殘影跳出來又消失
        （`QDrag` 的 pixmap），使用者兩下想做的其實是「加這張卡」。
        """
        self._press_at = None
        super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, e) -> None:  # Qt hook
        start = getattr(self, "_press_at", None)
        if start is None or not (e.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(e)
        if (e.pos() - start).manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(e)
        self._press_at = None
        self.start_drag()

    def start_drag(self) -> None:
        """開始把這張卡拖出去（測試直接呼叫這支，不模擬滑鼠軌跡）。"""
        mime = QMimeData()
        mime.setData(CARD_MIME, self.step_key.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.exec(Qt.CopyAction)


class StageButton(QFrame):
    """左側 rail 的一顆大按鈕：icon + 階段名 + 卡片數。

    這是 F7-7 的要求：**先用大 icon 分功能，按下去才帶出裡面的小功能。**
    六個階段一次全展開，等於一開始就把 15 張卡攤在使用者面前 ——
    那正是「太瑣碎」的來源。
    """

    clicked = Signal(str)

    _ICON = 30

    def __init__(self, group: str, title: str, subtitle: str, colour: str,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.group = str(group)
        self.setObjectName("stageButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("%s — %s" % (title, subtitle))
        # 輔具讀得到它是哪一段（F99 P2-4）；圖示磚與 9 px 的計數對讀屏是空的。
        self.setAccessibleName("%s stage — %s" % (title, subtitle))
        self._colour = colour
        self._active = False

        self.setFixedWidth(58)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 7, 2, 5)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignHCenter)

        self.icon = GroupIcon(self.group, colour, self, size=self._ICON)
        lay.addWidget(self.icon, 0, Qt.AlignHCenter)

        self.label = QLabel(title, self)
        self.label.setAlignment(Qt.AlignHCenter)
        self.label.setStyleSheet("font-size:%s; font-weight:600;"
                                 % TOKENS["font_micro"])
        lay.addWidget(self.label)

        self.count = QLabel("", self)
        self.count.setAlignment(Qt.AlignCenter)
        self.count.setObjectName("stageCount")
        lay.addWidget(self.count, 0, Qt.AlignHCenter)
        self._style_count()
        self.setProperty("active", "false")

    def _style_count(self) -> None:
        """「有幾張卡」那個數字的顏色（F13-3）。

        **階段色，沒有網底**（使用者第二輪定調：「不要有網底色，單純數字的
        顏色即可」）。顏色由 `theme.count_color` 算在 rail 的底色上 ——
        它會把字推到過得了 AA 為止，所以淺色主題不會像以前那樣看不見。

        顏色本身就講完了「這是這一段的東西」：它跟上面那個圖示、卡片庫的圓點、
        畫布上那塊圖示磚是同一個。
        """
        self.count.setStyleSheet(
            "background:transparent; color:%s; font-size:%s; font-weight:600;"
            % (theme.count_color(self.group), TOKENS["font_micro"]))

    def set_count(self, n: int) -> None:
        self.count.setText("" if n <= 0 else str(int(n)))
        # 空的時候不要留一塊有底色的小方塊。
        self.count.setVisible(n > 0)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self.setProperty("active", "true" if self._active else "false")
        restyle(self)

    def is_active(self) -> bool:
        return self._active

    def refresh_colour(self, colour: str) -> None:
        # 這裡**只剩**階段色（那是每一顆各自的顏色，不是主題的）。底色、邊框、
        # 圓角、hover、選中都在 QSS 裡了。
        self._colour = colour
        self.icon.set_color(colour)
        self._style_count()          # 藥丸的兩個顏色也是算出來的（F13-3）

    def mousePressEvent(self, e) -> None:  # Qt hook
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.group)
        super().mousePressEvent(e)


def column_header(title: str, parent: Optional[QWidget] = None) -> QLabel:
    """一欄工作區的小標題（F13-4）。

    主視窗有四個直欄，而以前它們之間只有一條 splitter —— **沒有任何東西說
    「這一欄是什麼」**。使用者要靠內容反推自己在看哪一塊，而那件事在他還不熟
    的時候正是最貴的。

    刻意做得很輕（10px、大寫、字距拉開、`text_hint`）：它是一個**地標**不是
    一個標題列，佔的高度要小到不值得為它讓出畫面。
    """
    lbl = QLabel(str(title).upper(), parent)
    lbl.setObjectName("columnHeader")
    return lbl


class LibraryPanel(QWidget):
    """卡片庫：依**流程階段**分組（F7-3），每組一個 QPainter 畫的 icon + 標題。

    為什麼不再依 ``category`` 分
    ----------------------------
    ``category``（影像／算法）描述的是「這張卡吐什麼型別」——那是引擎的分類
    （快取切點、驗證順序）。使用者要的是「我想幹嘛」，所以改用 ``group``：

        Input → Enhance → Region → Compare → Measure → ADC

    讀起來是一句話，而且每段有一條機械可判定的規則（見 ``pipeline/step.py``）。

    另外兩件讓 17 列不再瑣碎的事：

    * **搜尋框** —— 打字即時過濾（比對名稱、key 與說明）。
    * **前置條件 badge** —— ``set_available_streams()`` 之後，
      上游還沒產出所需影像流的卡會標成 ``needs diff`` 並調淡。
    """

    add_requested = Signal(str)
    #: 卡片區展開/收起（``True`` = 展開）。主視窗據此縮放左欄寬度 ——
    #: 收起來時整欄只留 rail，工作區才真的變寬。
    panel_toggled = Signal(bool)

    #: 顯示順序、標題與副標 —— **一份都不住在這裡**（U9，2026-09-08）。
    #:
    #: 它以前是這個類別上一個叫 ``GROUPS`` 的常數，跟
    #: ``pipeline/step.py::GROUP_ORDER`` 是同一件事的兩半（那邊排順序、這邊多帶
    #: 給人看的標題與副標），靠 ``tests/test_ui_f16_stages.py`` 綁著不漂。
    #: **而一條測試是補丁不是解法**：它擋得住「兩份不一致」，擋不住「改的人
    #: 根本不知道有第二份」。現在三樣東西都在 `step.py` 的 ``GROUPS`` 上，
    #: 這裡只是把它接過來的一個別名，UI 只讀不寫。
    _GROUPS = STAGE_GROUPS
    _ORDER = tuple(g for g, _t, _s in STAGE_GROUPS)
    _EMPTY_TEXT = "(no cards in this section)"
    _NO_MATCH_TEXT = "(no card matches)"

    #: group -> 所屬的三段式 segment。**顏色不再從這裡取**（F7-9 起走
    #: ``theme.group_hex``，六個階段各一個色相）；這份對照留著是因為
    #: 「這個階段屬於哪一段」在說明文字與排序上仍然成立。
    _GROUP_SEG = {"input": "image", "enhance": "image", "region": "algo",
                  "compare": "image", "measure": "algo", "adc": "adc"}

    #: 直式 icon rail 的寬度（收起來時整個 panel 就縮到只剩這條）。
    RAIL_W = 66
    #: 展開時卡片區至少要多寬（卡名 + badge 放得下）。
    PANEL_W = 190

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._items: Dict[str, _LibraryItem] = {}
        self._describes: Dict[str, Dict[str, Any]] = {}
        self._section_boxes: Dict[str, QVBoxLayout] = {}
        self._sections: Dict[str, QWidget] = {}
        self._headers: Dict[str, QWidget] = {}
        self._icons: Dict[str, GroupIcon] = {}
        self._available: List[str] = []
        self._query = ""
        self._shown_groups: List[str] = []

        self._open_group: Optional[str] = None

        # 版面：**直式 rail（左）｜ 卡片區（右）**。
        # F7-8：像工作列一樣由上而下，點了 icon 才顯示裡面的卡 ——
        # 這樣左邊的操作區平常是乾淨的。
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.rail = QWidget(self)
        self.rail.setObjectName("stageRail")
        self.rail.setFixedWidth(self.RAIL_W)
        rail_lay = QVBoxLayout(self.rail)
        rail_lay.setContentsMargins(2, 6, 2, 6)
        rail_lay.setSpacing(2)
        self.stage_buttons: Dict[str, StageButton] = {}
        for gid, title, subtitle in self._GROUPS:
            btn = StageButton(gid, title, subtitle, theme.group_hex(gid),
                              self.rail)
            btn.clicked.connect(self.toggle_group)
            rail_lay.addWidget(btn)
            self.stage_buttons[gid] = btn
        rail_lay.addStretch(1)

        # 搜尋鈕留在 rail 上（不是在 panel 裡）—— panel 收起來時搜尋框跟著藏，
        # 沒有這顆就再也打不開搜尋了。
        self.search_button = StageButton(
            "search", "Search", "Find a card by name or description",
            TOKENS["text_secondary"], self.rail)
        self.search_button.clicked.connect(lambda _g: self.focus_search())
        rail_lay.addWidget(self.search_button)
        outer.addWidget(self.rail)

        # 右邊：搜尋 + 卡片清單（收起來時整塊隱藏）
        self.panel = QWidget(self)
        panel_lay = QVBoxLayout(self.panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(0)

        # 地標自己不帶內距 —— 這裡用跟搜尋框同一組邊界（左 6 / 右 8），
        # 兩者才會對齊在同一條線上。
        head_wrap = QWidget(self.panel)
        hw = QHBoxLayout(head_wrap)
        hw.setContentsMargins(8, 6, 8, 0)
        self.header = column_header("Library", head_wrap)
        hw.addWidget(self.header)
        panel_lay.addWidget(head_wrap)

        self.search = QLineEdit(self)
        self.search.setPlaceholderText(strings.tr("Search cards…"))
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(strings.tr("Filter the card library by name or description"))
        self.search.textChanged.connect(self._on_search)
        wrap = QWidget(self.panel)
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(6, 2, 8, 4)
        wl.addWidget(self.search)
        panel_lay.addWidget(wrap)

        self._scroll = QScrollArea(self.panel)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._body = QVBoxLayout(self._host)
        self._body.setContentsMargins(6, 2, 8, 6)
        self._body.setSpacing(2)

        for gid, title, subtitle in self._GROUPS:
            self._body.addWidget(self._make_header(gid, title, subtitle))
            # 卡片列裝在**一個自己的 widget 裡**，而不是直接 addLayout 一個
            # QVBoxLayout（F17）。收起來的那七段要真的不佔位置：
            # 一個藏起來的 widget 在父層 layout 裡是零，但一個**空的巢狀
            # layout 不是** —— 它的 contentsMargins（這裡是下緣 8 px）照算。
            # 於是「展開哪一段」會決定那一段往下掉多少：Input 的標題貼在最上面，
            # Output 的被前面七段各推 8 px，整整低了 56 px。使用者看到的就是
            # 「點 Input 跟點 Output 帶出來的高度不一樣」。
            body = QWidget(self._host)
            body.setObjectName("libSection")
            box = QVBoxLayout(body)
            box.setContentsMargins(0, 0, 0, 8)
            box.setSpacing(1)
            self._body.addWidget(body)
            self._sections[gid] = body
            self._section_boxes[gid] = box

        self._body.addStretch(1)
        self._scroll.setWidget(self._host)
        panel_lay.addWidget(self._scroll, 1)
        outer.addWidget(self.panel, 1)

        self.set_steps([])
        self.toggle_group(self._ORDER[0])       # 開窗先展開 Input

    # -- 區塊標題（icon + 標題，取代舊的填滿色塊）---------------------------
    def _make_header(self, gid: str, title: str, subtitle: str) -> QWidget:
        colour = theme.group_hex(gid)
        head = QWidget(self)
        head.setObjectName("libSectionHeader")
        head.setProperty("group", gid)
        head.setToolTip(subtitle)
        lay = QHBoxLayout(head)
        lay.setContentsMargins(4, 8, 4, 2)
        lay.setSpacing(7)

        icon = GroupIcon(gid, colour, head)
        icon.setToolTip(subtitle)
        lay.addWidget(icon)
        self._icons[gid] = icon

        lbl = QLabel(title, head)
        lbl.setObjectName("libSectionTitle")
        lbl.setToolTip(subtitle)
        lbl.setStyleSheet("color:%s; font-weight:700; font-size:%s;"
                          % (TOKENS["text_secondary"], TOKENS["font_small"]))
        lay.addWidget(lbl)
        lay.addStretch(1)
        self._headers[gid] = head
        return head

    # -- public API --------------------------------------------------------
    def set_steps(self, steps: Sequence[Dict[str, Any]]) -> None:
        """用 ``Step.describe()`` 的 dict 清單重建整個卡片庫。"""
        self._clear()
        self._describes = {str(d.get("key", "")): dict(d) for d in (steps or [])}
        by_group: Dict[str, List[Dict[str, Any]]] = {g: [] for g in self._ORDER}
        for d in steps or []:
            gid = str(d.get("group") or "") or "enhance"
            by_group.setdefault(gid, []).append(d)

        for gid in self._ORDER:
            box = self._section_boxes[gid]
            entries = by_group.get(gid, [])
            if not entries:
                box.addWidget(self._empty_label(self._EMPTY_TEXT))
                continue
            colour = theme.group_hex(gid)
            for d in entries:
                item = _LibraryItem(d, colour, self._sections[gid])
                item.activated.connect(self.add_requested)
                box.addWidget(item)
                self._items[item.step_key] = item
        for gid, btn in self.stage_buttons.items():
            btn.set_count(len(by_group.get(gid, [])))
        self._apply_filter()
        self._apply_badges()

    def set_available_streams(self, streams: Sequence[str]) -> None:
        """告訴卡片庫「目前 pipeline 到最後為止產出了哪些影像流」。

        據此標出前置條件未滿足的卡。傳空清單 = 不知道（badge 全清）。
        """
        self._available = [str(s) for s in (streams or [])]
        self._apply_badges()

    def entry(self, step_key: str) -> Optional[_LibraryItem]:
        """取得某張卡片的那一列（給主視窗做 highlight／給測試點擊）。"""
        return self._items.get(step_key)

    def step_keys(self) -> List[str]:
        return list(self._items)

    def visible_step_keys(self) -> List[str]:
        """目前**看得到**的卡（搜尋過濾之後）。

        同樣用明確狀態（``_matches``）而不是 ``isVisible()``，理由見
        :meth:`_LibraryItem.badge_text`。
        """
        return [k for k in self._items
                if self._matches(k)
                and self._group_open(str((self._describes.get(k) or {})
                                         .get("group") or ""))]

    def section_titles(self) -> List[str]:
        return [lbl.text() for lbl in self.findChildren(QLabel)
                if lbl.objectName() == "libSectionTitle"]

    def visible_section_titles(self) -> List[str]:
        """搜尋之後還有卡片的區塊標題（順序同 `step.GROUPS`）。"""
        return [title for gid, title, _sub in self._GROUPS
                if gid in self._shown_groups]

    # -- 展開 / 收合（F7-7）--------------------------------------------------
    def toggle_group(self, group: Optional[str]) -> None:
        """點同一顆再點一次 = 收起來；點別顆 = 換過去（一次只開一段）。

        傳 ``None`` 直接全部收起來（測試 / 外部呼叫用）。訊號帶過來的是
        ``str``，所以這裡不能用 ``str(group)`` 一律轉字串 —— ``str(None)``
        會變成 ``"None"``，看起來像一個真的存在的段名。
        """
        gid = None if group is None else str(group)
        self._open_group = None if (gid is None or self._open_group == gid) else gid
        for g, btn in self.stage_buttons.items():
            btn.set_active(g == self._open_group)
        self._sync_panel()
        self._apply_filter()

    def panel_open(self) -> bool:
        """卡片區現在是展開的嗎（收起來時只剩 rail）。

        用明確狀態而不是 ``isVisible()`` —— 視窗還沒 show 之前 ``isVisible()``
        一律是 False，那會讓「收起來了嗎」在建構期永遠答錯。
        """
        return self._open_group is not None or bool(self._query)

    def _sync_panel(self) -> None:
        """展開狀態 -> panel 顯示 + 本身的最小寬度 + 通知外面重排欄寬。"""
        show = self.panel_open()
        self.panel.setVisible(show)
        self.setMinimumWidth(self.RAIL_W + (self.PANEL_W if show else 0))
        self.panel_toggled.emit(show)

    def open_group(self) -> Optional[str]:
        """目前展開的是哪一段（都收起來時回 None）。"""
        return self._open_group

    def set_query(self, text: str) -> None:
        """程式化設定搜尋字串（測試 / 外部呼叫用）。"""
        self.search.setText(str(text or ""))

    def focus_search(self) -> None:
        """展開卡片區並把游標放進搜尋框（rail 上的放大鏡鈕）。"""
        if not self.panel_open():
            self.toggle_group(self._ORDER[0])
        self.search.setFocus(Qt.OtherFocusReason)
        self.search.selectAll()

    def refresh_colors(self) -> None:
        """換主題之後重新取色（icon 與圓點都是自繪/內嵌樣式）。"""
        for gid, icon in self._icons.items():
            icon.set_color(theme.group_hex(gid))
        for gid, btn in self.stage_buttons.items():
            btn.refresh_colour(theme.group_hex(gid))
        self.search_button.refresh_colour(TOKENS["text_secondary"])

    # -- internals ---------------------------------------------------------
    def _empty_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("libEmpty")
        lbl.setStyleSheet("color:%s; font-size:%s; padding-left:12px;"
                          % (TOKENS["text_disabled"], TOKENS["font_small"]))
        return lbl

    def _on_search(self, text: str) -> None:
        self._query = str(text or "").strip().lower()
        self._sync_panel()
        self._apply_filter()

    def _matches(self, key: str) -> bool:
        if not self._query:
            return True
        d = self._describes.get(key) or {}
        hay = " ".join([key, str(d.get("label", "")), str(d.get("help", "")),
                        str(d.get("group", ""))]).lower()
        return all(tok in hay for tok in self._query.split())

    def _group_open(self, gid: str) -> bool:
        """搜尋中 = 跨全部階段找；沒搜尋 = 只看展開的那一段。"""
        return True if self._query else (gid == self._open_group)

    def _apply_filter(self) -> None:
        """過濾卡片；沒展開的階段整段收起來。"""
        for key, item in self._items.items():
            gid = str((self._describes.get(key) or {}).get("group") or "")
            item.setVisible(self._matches(key) and self._group_open(gid))
        shown: List[str] = []
        for gid, head in self._headers.items():
            box = self._section_boxes[gid]
            hit = False
            opened = self._group_open(gid)
            for i in range(box.count()):
                w = box.itemAt(i).widget()
                if isinstance(w, _LibraryItem):
                    hit = hit or (self._matches(w.step_key) and opened)
                elif isinstance(w, QLabel):
                    # 空區塊的提示語只在該段展開、且沒搜尋時顯示
                    show = opened and not self._query
                    w.setVisible(show)
                    hit = hit or show
            head.setVisible(hit)
            # 標題與卡片列是一起出現、一起消失的（見建構式裡的說明）：
            # 只藏標題的話，收起來的那一段仍然會用它 layout 的下緣把後面的
            # 每一段往下推。
            self._sections[gid].setVisible(hit)
            if hit:
                shown.append(gid)
        self._shown_groups = [g for g in self._ORDER if g in shown]

    def _apply_badges(self) -> None:
        avail = set(self._available)
        for _key, item in self._items.items():
            if not self._available:
                item.set_missing(())
                continue
            item.set_missing([r for r in item.reads if r not in avail])

    def _clear(self) -> None:
        self._items = {}
        for box in self._section_boxes.values():
            clear_layout(box)

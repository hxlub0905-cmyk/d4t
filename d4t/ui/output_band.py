# d4t Studio 畫布：Output 段那一塊 — authored 2026-08-25 (F30 Phase D).
"""Output 段的框：**這幾張卡跟其他卡不一樣，它們整批只跑一次。**

畫布上其他每一張卡都是「一顆 defect 跑一次」。Output 段那幾張不是 ——
它們在**整批跑完之後**才跑，而且只跑一次（`Step.scale == SCALE_LOT`）。
在這之前，畫面上沒有任何東西說得出那件事：它們就是右邊飄著的幾張卡，
長得跟 Denoise 一模一樣。

所以給它跟判定區同一套視覺 —— 虛線框、一行段名、左緣一句淡的提示。
**不加埠、不加線**：進到這幾張卡的是「整批的結果表」，那不是一條影像流；
畫一條存起來的線就是說謊（同 `tree_scene` 那塊判定區左緣的 ``numbers →``）。

為什麼是一個新模組（CLAUDE.md §4）
----------------------------------
一塊新的畫布元件＝一個新模組。`studio.py` 留給接線，不留給內容。
`canvas.py` 也一樣：它負責算 origin、清舊圖元、把新的擺進去，
「這一塊長什麼樣」住這裡。

⚠ **它跟判定區的差別在「誰決定有沒有」。** 判定區是 recipe 上的一個東西
（`recipe.decide`），可以整個拿掉；Output 段是**一群卡片的共同身分**，
沒有卡就沒有框 —— 所以這裡沒有 ✕，也不能拖：要拿掉的是那幾張卡本身。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

from .theme import TOKENS, group_hex

__all__ = ["OUTPUT_TITLE", "OUTPUT_WHEN", "OUTPUT_HINT", "band_rect",
           "card_rect", "build_band",
           "encloses_a_stranger", "runs_of", "SAME_ROW_TOL"]

#: 框上那一行字。**講的是「什麼時候跑」，不是「這是什麼段」** ——
#: 段名畫布上已經有了（卡片的顏色與圖示），而「整批跑完之後跑一次」沒有。
OUTPUT_TITLE = "OUTPUT"

#: 標題底下那一行 —— **講的是「什麼時候跑」**，而那正是這一塊存在的理由。
OUTPUT_WHEN = "once per lot"

#: 左緣那一句。跟判定區的 ``numbers →`` 同一個位置、同一個理由：
#: 東西**是**從左邊流過來的，但那不是一條存起來的線。
OUTPUT_HINT = "results →"

#: 框比卡片本身大多少（左上右下）。
#:
#: ⚠ **上下只留一點點**（不是判定區那種 26px 的頂邊）。畫布的列距實測是 90px
#: 而卡片本身就有 92px 高 —— 上下各留 26 的話，換行之後相鄰兩列的框會疊在
#: 一起（實測疊了 42px），看起來像畫壞了。所以那一行字改放**左邊那條走廊**，
#: 跟 ``results →`` 疊成三行（見 `_BandItem.paint`）。
PAD_L, PAD_T, PAD_R, PAD_B = 14.0, 8.0, 14.0, 8.0

#: 左邊那條走廊有多寬（字畫在框外面）。
GUTTER_W = 92.0


def _colour() -> QColor:
    return QColor(group_hex("output"))


def card_rect(item: Any) -> Optional[QRectF]:
    """一張卡**看得見的那塊**（scene 座標）。

    ⚠ **不是 ``sceneBoundingRect()``。** 那個把埠的抓取範圍與埠標籤都算進去，
    左右各多出幾十像素、上下也多一點 —— 拿它當框的依據的話，相鄰兩列的框會
    上下疊在一起（實測疊了 74px）。框框的是卡片，不是卡片的碰撞盒。
    """
    try:
        from .canvas import NODE_W
        return QRectF(item.scenePos(), QPointF(item.scenePos().x() + NODE_W,
                                               item.scenePos().y()
                                               + item.height()))
    except Exception:                  # noqa: BLE001 — 不是節點就退回碰撞盒
        try:
            return QRectF(item.sceneBoundingRect())
        except Exception:              # noqa: BLE001 — 圖元被銷毀
            return None


def band_rect(items: Sequence[Any]) -> Optional[QRectF]:
    """把這幾張卡框起來的那個矩形（一張都沒有回 ``None``）。

    ⚠ **一張都沒有的時候回 None，不是一個空框。** 一個框著空氣的虛線框讀起來
    像「這裡本來有東西」——而正確的答案是「這份 recipe 還沒有要寫出任何東西」。
    """
    rect: Optional[QRectF] = None
    for it in items or ():
        r = card_rect(it)
        if r is None:
            continue
        rect = QRectF(r) if rect is None else rect.united(r)
    if rect is None:
        return None
    return rect.adjusted(-PAD_L, -PAD_T, PAD_R, PAD_B)


class _BandItem(QGraphicsItem):
    """框本身。**不可選、不可拖、沒有 ✕** —— 見模組說明。"""

    def __init__(self, rect: QRectF, titled: bool = True):
        super().__init__()
        self._rect = QRectF(rect)
        self._titled = bool(titled)
        self.setZValue(-3.0)           # 墊在所有東西（含連線 -1）底下
        self.setAcceptedMouseButtons(Qt.NoButton)   # 點它等於點到畫布

    def boundingRect(self) -> QRectF:
        # 左邊要留給那三行字（它們畫在框外面）。
        return self._rect.adjusted(-(GUTTER_W + 6.0), -4.0, 4.0, 4.0)

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        col = _colour()
        pen = QPen(col, 1.2, Qt.DashLine)
        pen.setDashPattern([5.0, 4.0])
        p.setPen(pen)
        wash = QColor(col)
        wash.setAlpha(20)              # 比判定區更淡：這一塊不是主角
        p.setBrush(wash)
        p.drawRoundedRect(self._rect, 10, 10)

        if not self._titled:
            return          # 卡片換行時的第二、第三串：框在，字不重複

        # 三行字都在**左邊那條走廊**裡，由上往下：段名、什麼時候跑、
        # 東西從哪來。放在框上面的話換行之後會撞到上一列（見 PAD_* 那一段）。
        left = self._rect.left() - GUTTER_W - 4.0
        top = self._rect.top() + 4.0
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.0))
        f.setLetterSpacing(f.SpacingType.AbsoluteSpacing, 1.2)
        p.setFont(f)
        p.setPen(col)
        p.drawText(QRectF(left, top, GUTTER_W, 14),
                   Qt.AlignRight | Qt.AlignVCenter, OUTPUT_TITLE)

        f2 = p.font()
        f2.setBold(False)
        f2.setLetterSpacing(f2.SpacingType.AbsoluteSpacing, 0.0)
        p.setFont(f2)
        p.setPen(col)
        p.drawText(QRectF(left, top + 14, GUTTER_W, 14),
                   Qt.AlignRight | Qt.AlignVCenter, OUTPUT_WHEN)

        faded = QColor(TOKENS["text_secondary"])
        faded.setAlpha(140)
        p.setPen(faded)
        p.drawText(QRectF(left, top + 30, GUTTER_W, 14),
                   Qt.AlignRight | Qt.AlignVCenter, OUTPUT_HINT)


def encloses_a_stranger(rect: QRectF, others: Sequence[Any]) -> bool:
    """這個框裡有別的段的卡片嗎。

    用**中心點**在不在框裡，不是矩形相不相交：框比卡片大一圈（`PAD_*`），
    而隔壁那張卡的邊緣蹭到那一圈是常態 —— 拿相交當判準的話，畫面稍微擠一點
    這個框就整個消失了。
    """
    for it in others or ():
        r = card_rect(it)
        if r is not None and rect.contains(r.center()):
            return True
    return False


#: 兩張卡的中心 y 差多少以內算「同一列」。
#:
#: 半張卡的高度：畫布的列距是「最高的那張卡 ＋ ROW_GAP」，所以同一列的中心
#: 幾乎完全對齊，而下一列至少差一整張卡。
SAME_ROW_TOL = 32.0


def runs_of(items: Sequence[Any], others: Sequence[Any] = ()
            ) -> List[List[Any]]:
    """把 Output 卡切成**一列一列、中間沒有別人**的幾串。

    為什麼不是一個大框：畫布會**換行**（`layout_columns` 的 wrap）。實測四張
    Output 卡在 1280px 的視窗上排成「第一列最後一格 ＋ 第二列前三格」，而那四
    張的外接矩形會把上一列的 Normalize 與 GLV 一起框進去 —— 那個框說的
    「裡面這幾張整批只跑一次」就變成假的。

    所以照畫面上真正的樣子切：同一列、而且**中間沒有夾別的卡**的算一串，
    一串一個框。使用者把某一張拖到別的地方，它就自己成一串。
    """
    placed: List[Any] = []
    for it, mine in ([(x, False) for x in others or ()]
                     + [(x, True) for x in items or ()]):
        r = card_rect(it)
        if r is None:
            continue
        placed.append((r.center().y(), r.center().x(), mine, it))
    out: List[List[Any]] = []
    for _row_y, group in _by_row(placed):
        run: List[Any] = []
        for _y, _x, mine, it in group:
            if mine:
                run.append(it)
            elif run:
                out.append(run)
                run = []
        if run:
            out.append(run)
    return out


def _by_row(placed):
    """``[(y, x, mine, item)]`` → ``[(列的 y, 那一列照 x 排好的東西)]``。"""
    rows: List[Any] = []
    for entry in sorted(placed, key=lambda e: (e[0], e[1])):
        if rows and abs(entry[0] - rows[-1][0]) <= SAME_ROW_TOL:
            rows[-1][1].append(entry)
        else:
            rows.append((entry[0], [entry]))
    return rows


def build_band(scene: Any, items: Sequence[Any],
               others: Sequence[Any] = ()) -> List[QGraphicsItem]:
    """把框擺進 scene，回傳擺了哪些（畫布重建時要清）。

    ``items`` 是那幾張 Output 卡的圖元，``others`` 是畫布上其餘的卡。
    空的（或算不出矩形）→ 什麼都不擺，回一個空 list。

    卡片換行或被拖散時**一串一個框**（見 :func:`runs_of`），而**只有第一個框
    寫字** —— 四個一模一樣的標題是雜訊，而那句話講的是這一段，不是這一串。

    ⚠ **框裡出現別的段的卡片時，那一串不畫。** 這個框說的是「裡面這幾張整批
    只跑一次」；畫布不能說謊，一個消失的框只是少了一個提示，一個說謊的框是
    錯的。
    """
    made: List[QGraphicsItem] = []
    for run in runs_of(items, others):
        rect = band_rect(run)
        if rect is None or encloses_a_stranger(rect, others):
            continue
        band = _BandItem(rect, titled=not made)
        scene.addItem(band)
        made.append(band)
    return made

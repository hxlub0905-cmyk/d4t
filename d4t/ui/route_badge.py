# d4t Studio — 畫布上的分流徽章（F25-B，2026-08-24）。
"""``route_by``（pre-filter）在畫布上的樣子。

為什麼它**不是一張卡**（使用者 2026-08-24 問「需要獨立一張 card 嗎」）
--------------------------------------------------------------------
雞生蛋：卡片是在 route **裡面**跑的，而 pre-filter 要決定的正是走哪一條
route。它也不能是判定樹的一步 —— 那些變數是特徵，而特徵要跑完才有。
兩段判定的分工是一句話：

    **pre-filter 問「這一顆是什麼」**（KLARF 帶進來的欄位，跑之前就知道），
    **ADC 問「這一顆量出來怎麼樣」**（跑完才有的數字）。

前者決定走哪幾張卡，後者決定分哪個 bin。

那為什麼還要畫在畫布上
----------------------
因為「同一批資料分兩條路跑」是真的，而畫布在此之前**完全不講這件事** ——
使用者只能靠工具列一個下拉切著看（鐵則 9 的那句「畫布不能說謊」在這裡
還沒兌現）。所以給它一個**徽章**：不可拖、沒有埠、接不了線（它不是
pipeline 的一步），但它站在所有卡片的前面，說出三件事 ——
看哪一欄、對照表長怎樣、**現在這一顆走哪一條**。

真正把分岔畫出來（一張畫布看到兩條支線）要 F17-⑤「一份 recipe 一張圖」，
那是大手術；使用者定調先做徽章（B），等 route 真的開始漂再談（C）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from . import theme
from .theme import TOKENS

__all__ = ["route_badge_info", "RouteBadgeItem", "build_badge", "BADGE_W"]

#: 徽章的大小（畫布座標）。跟節點卡同寬 —— 它站在同一排上。
BADGE_W, BADGE_H = 204.0, 64.0
#: 一格對照表佔多高（多到畫不下就收成 `+N`）。
_ROW_H = 15.0
_MAX_ROWS = 4


def route_badge_info(model: Any, rows: Any = None,
                     current: Optional[Tuple[str, str]] = None
                     ) -> Optional[Dict[str, Any]]:
    """畫布徽章要畫的東西；沒有分流回 ``None``（畫布上就沒有這個東西）。

    ``rows`` 是這一批的結果 —— 每條 route 幾顆**從 ``route_taken`` 讀**
    （F19 的規矩：自動做的每個決定都要是一個畫得出分布的數字，而它正是
    當初為了這件事寫出去的）。沒跑過就是 ``None``，那時候一個數字都不畫。
    ``current`` 是現在預覽那一顆的 ``(欄位值, route)``。
    """
    rb = getattr(model, "route_by", None)
    if rb is None:
        return None
    keys = sorted(model.route_keys())
    counts: Optional[Dict[str, int]] = None
    for r in (rows or []):
        idx = (r.get("features") or {}).get("route_taken")
        if not isinstance(idx, (int, float)):
            continue
        i = int(idx)
        if 0 <= i < len(keys):
            counts = counts or {}
            counts[keys[i]] = counts.get(keys[i], 0) + 1
    return {
        "column": str(rb.column),
        "map": sorted(rb.map.items()),
        "default": str(rb.default or ""),
        "counts": counts,
        "current": None if current is None else (str(current[0]),
                                                 str(current[1])),
        "editing": str(getattr(model, "kind", "") or ""),
    }


def _colour() -> QColor:
    """Input 段的階段色 —— 它讀的是**資料帶進來的**東西，站的也是那一排。"""
    return QColor(theme.group_hex("input"))


class RouteBadgeItem(QGraphicsItem):
    """畫布上的分流徽章。**不可拖、不可選、沒有埠** —— 它不是 pipeline 的一步。"""

    def __init__(self, info: Dict[str, Any], canvas: Any):
        super().__init__()
        self.info = dict(info)
        self._canvas = canvas
        self.setZValue(-2.0)
        rows = list(self.info.get("map") or [])
        bits = ["%s → %s" % (v, r) for v, r in rows]
        if self.info.get("default"):
            bits.append("anything else → %s" % self.info["default"])
        else:
            bits.append("anything else → that defect fails")
        self.setToolTip(
            "Pre-filter - the FIRST of the two sorting steps.\n"
            "Every defect reads %s BEFORE anything runs, and that value "
            "picks which cards it goes through.\n\n%s\n\n"
            "The second one is the Decision on the right: it sorts by the "
            "numbers the cards measured, once they have run.\n"
            "Click to edit this one."
            % (self.info.get("column", "?"), "\n".join(bits)))

    def height(self) -> float:
        n = min(len(self.info.get("map") or []), _MAX_ROWS)
        return max(BADGE_H, 34.0 + _ROW_H * (n + 1))

    def boundingRect(self) -> QRectF:
        return QRectF(-3, -3, BADGE_W + 6, self.height() + 6)

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        col = _colour()
        body = QRectF(0, 0, BADGE_W, self.height())
        wash = QColor(col)
        wash.setAlpha(20)
        pen = QPen(col, 1.2, Qt.DashLine)
        pen.setDashPattern([5.0, 4.0])
        p.setPen(pen)
        p.setBrush(wash)
        p.drawRoundedRect(body, 8, 8)

        # 標題：漏斗形的小記號 ＋ PRE-FILTER ＋ 欄名
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(max(6.5, f.pointSizeF() - 1.0))
        p.setFont(f)
        p.setPen(col)
        p.drawText(QRectF(10, 6, BADGE_W - 20, 14),
                   Qt.AlignLeft | Qt.AlignVCenter, "PRE-FILTER")
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(TOKENS["text_primary"]))
        p.drawText(QRectF(10, 20, BADGE_W - 20, 14),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   str(self.info.get("column", "")))

        # 對照表（值 → route）。試跑過就在右邊寫這條路幾顆。
        counts = self.info.get("counts")
        editing = str(self.info.get("editing") or "")
        current = self.info.get("current")
        y = 34.0
        rows = list(self.info.get("map") or [])
        for value, route in rows[:_MAX_ROWS]:
            here = bool(current and current[0] == value)
            p.setPen(QColor(TOKENS["text_primary"] if here or route == editing
                            else TOKENS["text_secondary"]))
            fr = p.font()
            fr.setBold(here)
            p.setFont(fr)
            p.drawText(QRectF(10, y, BADGE_W - 60, _ROW_H),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "%s → %s" % (value, route))
            if counts is not None:
                p.setPen(QColor(TOKENS["text_secondary"]))
                fr.setBold(False)
                p.setFont(fr)
                p.drawText(QRectF(BADGE_W - 54, y, 44, _ROW_H),
                           Qt.AlignRight | Qt.AlignVCenter,
                           "%d" % int(counts.get(route, 0)))
            y += _ROW_H
        hidden = len(rows) - _MAX_ROWS
        p.setPen(QColor(TOKENS["text_secondary"]))
        f2 = p.font()
        f2.setBold(False)
        p.setFont(f2)
        if hidden > 0:
            p.drawText(QRectF(10, y, BADGE_W - 20, _ROW_H),
                       Qt.AlignLeft | Qt.AlignVCenter, "+%d more" % hidden)
        else:
            tail = ("anything else → %s" % self.info["default"]
                    if self.info.get("default")
                    else "anything else → fails")
            p.drawText(QRectF(10, y, BADGE_W - 20, _ROW_H),
                       Qt.AlignLeft | Qt.AlignVCenter, tail)

    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton and self._canvas is not None:
            self._canvas.prefilter_clicked.emit()
            e.accept()
            return
        super().mousePressEvent(e)


class _FeedItem(QGraphicsItem):
    """徽章 → 第一張卡的那條**細箭頭**：分流之後才進 pipeline。

    刻意畫得跟資料流的線不一樣（細、虛、沒有埠）—— 它搬的不是像素，
    是「這一顆該走哪一組卡」。
    """

    def __init__(self, a: QPointF, b: QPointF):
        super().__init__()
        self._a, self._b = QPointF(a), QPointF(b)
        self.setZValue(-2.5)

    def boundingRect(self) -> QRectF:
        return QRectF(self._a, self._b).normalized().adjusted(-8, -8, 8, 8)

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        p.setRenderHint(QPainter.Antialiasing, True)
        col = _colour()
        pen = QPen(col, 1.2, Qt.DotLine)
        p.setPen(pen)
        p.drawLine(self._a, self._b)
        head = QPainterPath(self._b)
        head.lineTo(self._b + QPointF(-6.0, -3.5))
        head.lineTo(self._b + QPointF(-6.0, 3.5))
        head.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawPath(head)


def build_badge(scene: Any, canvas: Any, info: Dict[str, Any],
                origin: QPointF, feed_to: Optional[QPointF] = None
                ) -> List[QGraphicsItem]:
    """把徽章擺進 scene，回傳擺了哪些（畫布重建時要清）。"""
    items: List[QGraphicsItem] = []
    badge = RouteBadgeItem(info, canvas)
    badge.setPos(origin)
    scene.addItem(badge)
    items.append(badge)
    if feed_to is not None:
        arrow = _FeedItem(origin + QPointF(BADGE_W, badge.height() / 2.0),
                          feed_to)
        scene.addItem(arrow)
        items.append(arrow)
    return items

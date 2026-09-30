# d4t Studio：線不從卡背後穿過 — authored 2026-09-30 (F124 期 3).
"""**一條往前走的線，碰到夾在中間的卡就繞過去。**

為什麼需要它
------------
畫布上的線從來源右邊出來、平滑地彎進目標左邊（三次貝茲）。兩張卡**中間隔著
另一張卡**的時候（同一列的 Input → GLV，中間是 ROI），那條曲線直接從中間那張
卡的**背後**穿過去 —— 線畫在卡片底下，於是看起來像是從中間那張卡吐出來的。
使用者（F124）：「希望 user 看得懂、講得出來畫布在幹嘛」—— 一條看起來從
ROI 出來的線，會讓他講出一句錯的話。

怎麼繞
------
跟換行的線（F123 期 4，`_EdgeItem.path` 往回走那一支）同一種折法：從來源右邊
出來、走到被擋住的那幾張卡上方（或下方）的空隙、沿空隙水平走、再下來進目標。
空隙是列與列之間那一帶（``ROW_GAP``），所以水平那一段不壓任何卡；兩段垂直的
落在欄與欄之間（``BACK_REACH`` 比欄距小得多）。

判斷「有沒有被擋住」用**取樣**，不用 `QPainterPath.intersects`：後者問的是
**填滿的面積**，一條開放的曲線會被自動閉合成一大塊（F123 期 4 那條測試第一版
就是這樣量錯的）。這一支每一次重畫都會被叫（`path` 也是 `boundingRect` 與
`shape` 的來源），取三十幾個點、每點問幾個矩形，比描邊再求交便宜得多。

本模組只算幾何，不碰任何圖元。
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from PySide6.QtCore import QPointF, QRectF

__all__ = ["forward_detour", "lane", "SAMPLES"]

#: 沿著曲線取幾個點。一張卡寬 204、兩欄之間的曲線頂多兩三千 px，32 個點的
#: 間距遠小於一張卡的高度（64），被擋住的那一段不會從兩點之間漏過去。
SAMPLES = 32


def _cubic(a: QPointF, c1: QPointF, c2: QPointF, b: QPointF,
           t: float) -> QPointF:
    u = 1.0 - t
    return (a * (u * u * u) + c1 * (3 * u * u * t) + c2 * (3 * u * t * t)
            + b * (t * t * t))


def lane(reach_side: float, dst_port: int) -> float:
    """繞行的線**最後那段垂直的**離目標多遠：一顆輸入埠一條道。

    兩條繞行的線進同一張卡的不同埠時，垂直那一段以前疊在同一條 x 上 ——
    characterization 的 Write comparison 左邊因此是一束分不開的線。越下面的埠
    離卡越遠：它的垂直那段才不會切過上面那幾顆埠的水平那一小段。
    """
    return reach_side + 10.0 * max(0, int(dst_port))


def forward_detour(a: QPointF, b: QPointF, reach: float, bodies: Sequence[QRectF],
                   reach_side: float, gap: float,
                   reach_in: Optional[float] = None) -> Optional[List[QPointF]]:
    """``a`` → ``b`` 那條往前走的曲線壓到 ``bodies`` 裡的卡 → 繞行的折線點；
    沒壓到回 ``None``（照舊畫曲線）。

    ``reach`` 是曲線的水平推力（`_EdgeItem.path` 算好的那一個，兩邊要是同一條
    曲線）；``reach_side`` 是繞行時從埠水平走出去多遠，``reach_in`` 是進目標
    之前那一段（:func:`lane`；沒給就跟 ``reach_side`` 一樣）；``gap`` 是列距。
    ``bodies`` 不含來源與目標那兩張卡。
    """
    c1, c2 = a + QPointF(reach, 0.0), b - QPointF(reach, 0.0)
    hit: List[QRectF] = []
    for i in range(1, SAMPLES):
        pt = _cubic(a, c1, c2, b, i / float(SAMPLES))
        for body in bodies:
            if body not in hit and body.adjusted(1, 1, -1, -1).contains(pt):
                hit.append(body)
    if not hit:
        return None
    top = min(r.top() for r in hit)
    bottom = max(r.bottom() for r in hit)
    # 兩端都在被擋住的卡的上半 → 從上面繞；否則從下面。一列裡的線（最常見的
    # 那種）兩端都跟中間那張卡同高，平手走上面 —— 上面那一帶是這一列跟上一列
    # 之間的空隙，第一列的話就是畫布最上緣，都是空的。
    middle = (top + bottom) / 2.0
    above = (a.y() + b.y()) / 2.0 <= middle
    gy = top - gap / 2.0 if above else bottom + gap / 2.0
    back = reach_side if reach_in is None else reach_in
    return [a, QPointF(a.x() + reach_side, a.y()),
            QPointF(a.x() + reach_side, gy), QPointF(b.x() - back, gy),
            QPointF(b.x() - back, b.y()), b]

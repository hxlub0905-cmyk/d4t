# d4t Studio：自動排版 — split out of canvas.py 2026-09-30 (F124 期 3).
"""**卡片排在哪一欄、哪一列**：純函式，不碰任何圖元。

`canvas.py` 叫它（`set_nodes` 與 `tidy`），名字也從那裡轉出去給既有的呼叫端。
搬出來的理由是 `canvas.py` 在規模尺上（`tests/test_size_ceilings.py`），而這一支
從頭到尾是一個 ``(node ids, 線) → (欄, 列)`` 的函式，跟畫東西無關。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

__all__ = ["WRAP", "layout_columns"]

#: 還沒拉線時，一列最多排幾張卡（見 :func:`layout_columns`）。
WRAP = 4


def layout_columns(node_ids: Sequence[str],
                   edges: Sequence[Tuple[str, str]],
                   wrap: Optional[int] = None) -> Dict[str, Tuple[int, int]]:
    """自動排版：``node_id -> (欄, 列)``。

    欄 = 拓撲深度（最長前置路徑長度），列 = 同欄內依 ``node_ids`` 的原順序。
    沒有任何連線時每個節點各自深度 0 —— 那會全部疊在第一欄，所以退化情況下
    改成「一個接一個往右排」，讓空 recipe 加卡片時看起來仍然是一條鏈。

    但那條鏈**會換行**（``WRAP``，F7-9）。一份九張卡、還沒拉線的 recipe 排成
    一列會超過 2500px；``fit()`` 為了塞進畫面得縮到看不出字，而它又有下限
    （縮成小方塊比留捲軸更糟），結果是「一排讀不出來的小方塊 + 一條捲軸」。
    換行之後同樣九張卡是 3×3，每一張都讀得到字。閱讀順序仍然是左到右、
    上到下 —— 跟文字一樣，不需要額外學。
    """
    wrap = WRAP if wrap is None else max(1, int(wrap))
    ids = [str(n) for n in node_ids]
    idx = {n: i for i, n in enumerate(ids)}
    preds: Dict[str, List[str]] = {n: [] for n in ids}
    for a, b in edges:
        if a in idx and b in idx:
            preds[b].append(a)

    if not any(preds[n] for n in ids):
        return {n: (i % wrap, i // wrap) for i, n in enumerate(ids)}

    depth: Dict[str, int] = {}
    for n in ids:                       # ids 已是拓撲順序，一遍就夠
        depth[n] = max((depth.get(p, 0) + 1 for p in preds[n]), default=0)

    # 一「帶」= 換行之前的 ``wrap`` 個深度。帶高取「最擠的那個深度有幾個節點」，
    # 這樣換行之後上下兩帶不會疊在一起。
    per_depth: Dict[int, int] = {}
    for n in ids:
        per_depth[depth[n]] = per_depth.get(depth[n], 0) + 1
    band_h = max(per_depth.values(), default=1)

    # 同欄內的列序用 **barycenter**（上游都排在第幾列，我就往那個平均靠）。
    # 以前照 node_order 排：上游在第 0 列、下游被排到第 2 列，線就斜跨整欄，
    # 而三條斜線交叉起來「亂」的觀感比任何配色問題都大。跟上游對齊之後，
    # 大部分的線接近水平 —— 交叉不是被畫得更好看，是**根本不發生**。
    # 平手（沒有上游、或平均相同）退回原順序，既有測試鎖的就是這個順序。
    rows_of: Dict[str, int] = {}
    out: Dict[str, Tuple[int, int]] = {}
    for d in sorted(set(depth.values())):
        members = [n for n in ids if depth[n] == d]

        def _bary(n: str) -> float:
            prs = [rows_of[p] for p in preds[n] if p in rows_of]
            return (sum(prs) / float(len(prs))) if prs else float(idx[n])

        members.sort(key=lambda n: (_bary(n), idx[n]))
        band, col = divmod(d, wrap)
        for r, n in enumerate(members):
            rows_of[n] = r
            out[n] = (col, band * band_h + r)
    return _tuck_the_tail(out, depth, preds, edges, wrap, band_h)


def _tuck_the_tail(out: Dict[str, Tuple[int, int]], depth: Dict[str, int],
                   preds: Dict[str, List[str]], edges: Sequence[Tuple[str, str]],
                   wrap: int, band_h: int) -> Dict[str, Tuple[int, int]]:
    """**最後一帶只剩終點的時候，不換行**（F124 期 3）。

    終點＝沒有下游的卡（Output 那幾張）。照深度排，它常常是換行之後孤零零
    落在下一帶的**第 0 欄** —— 接進它的每一條線都得從最右邊繞回最左邊：
    ebi-die-to-die 的 Write report、characterization 的 Write comparison
    （三條線疊成一束橫過整張畫布）。改成排在它**最深的那張上游**那一欄、
    那一欄最下面：接進來的線短、而且讀起來仍然是「做完這裡，寫出去」。

    最後一帶裡只要有一張不是終點，就照舊換行（那一帶還有流要往下走）。
    """
    if not out:
        return out
    last = max(depth.values()) // wrap
    if last == 0:
        return out
    has_next = {a for a, _b in edges}
    tail = [n for n in out if depth[n] // wrap == last]
    if any(n in has_next for n in tail):
        return out
    moved = dict(out)
    done: set = set()
    for n in tail:
        ups = [p for p in preds[n] if p in moved and p not in tail]
        if not ups:
            return out
        deepest = max(ups, key=lambda p: (depth[p], moved[p][1]))
        col = moved[deepest][0]
        # 那一欄最下面（不含還在搬的終點；同一張上游的第二個終點疊在第一個下面）。
        below = max(r for m, (c, r) in moved.items()
                    if c == col and (m not in tail or m in done))
        moved[n] = (col, below + 1)
        done.add(n)
    return moved

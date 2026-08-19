# d4t algo — authored 2026-08-19 (F15). 演算法來源：KLIP `klarf_core.compare`。
"""兩批 defect 的配對：**座標最近的一顆**，容差內、一對一。

用在哪
------
`steps/pair_source.py`（EBI ↔ RSEM(API) characterization）：main 那一份的每一顆
要問「這一顆在另一份資料裡是哪一顆」。

演算法跟 `ingest/klarf_core.compare()` 是同一支
------------------------------------------------
KLIP 的 `compare()` 做的是**整份 KLARF 對整份 KLARF** 的 diff（新增／消失／
改分類／改欄位 + 一份 HTML 報告），輸入是 `KlarfDoc`。這裡要的是**逐顆問一次**，
輸入是 `DefectItem`（worker 裡拿得到的東西——`KlarfDoc` 刻意不進 worker）。

輸入與輸出都不一樣，所以是兩個函式；但**桶的算法必須一模一樣**，不然「KLIP 說
配到、d4t 說沒配到」會變成一個沒有人查得動的差異。
`tests/test_pairing.py::test_the_two_matchers_agree` 拿同一組點餵兩邊，
逐顆比對結果——兩邊漂了它會紅。

為什麼不是「兩邊都呼叫同一支」：`klarf_core` 是 vendored 進來的獨立模組
（`fab_probe/` 也鏡射著它的規則），讓它反過來 import `core.algo` 會把一個
不依賴 d4t 的檔案綁進來。一條測試比一個相依便宜。

座標系
------
點的位置是 **die + die 內相對座標**，距離只在**同一個 die 內**算。跨 die 比
距離要知道 die 的尺寸，而那個數字 KLARF 不一定給——與其猜一個，不如讓
「不同 die 就不是同一顆」成立（同一片 wafer 的兩次量測，同一顆本來就在同一個
die 裡）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

#: 沒有 die 資訊時大家都放同一個桶（folder / stack 這種沒有 KLARF 的資料）。
_NO_DIE = (0, 0)


def point_of(item: Any) -> Optional[Dict[str, Any]]:
    """``DefectItem`` → 配對用的點；座標缺一不可，缺了回 ``None``。

    回 ``None`` 而不是塞 0：把座標不明的那幾顆當成「都在原點」的話，它們會
    互相配到對方，而且距離是 0（看起來配得完美）。
    """
    x, y = getattr(item, "xrel_nm", None), getattr(item, "yrel_nm", None)
    if x is None or y is None:
        return None
    die = getattr(item, "die", None)
    return {
        "i": int(getattr(item, "index", -1)),
        "id": str(getattr(item, "defect_id", "")),
        "die": tuple(die) if die else _NO_DIE,
        "x": float(x),
        "y": float(y),
        "item": item,
    }


def points_of(items: Sequence[Any]) -> List[Dict[str, Any]]:
    """一整批的點（座標不明的那幾顆不在裡面）。"""
    return [p for p in (point_of(it) for it in items or ()) if p is not None]


def _bucket(points: Sequence[Dict[str, Any]], cell: float) -> Dict[Any, List[Dict[str, Any]]]:
    """以 ``die`` 分桶，桶內再用 ``cell`` 大小的網格雜湊（同 KLIP）。"""
    out: Dict[Any, List[Dict[str, Any]]] = {}
    for p in points:
        key = (p["die"], int(p["x"] // cell), int(p["y"] // cell))
        out.setdefault(key, []).append(p)
    return out


def nearest(point: Dict[str, Any], index: Dict[Any, List[Dict[str, Any]]],
            tol_nm: float, k: int = 1,
            taken: Optional[set] = None) -> List[Tuple[Dict[str, Any], float]]:
    """離 ``point`` 最近的前 ``k`` 個（容差內、由近而遠）。

    只掃自己那一格與周圍八格 —— 網格邊長就是容差，所以容差內的點一定落在
    這九格裡（KLIP 的那一段是同一個推理）。
    """
    cell = max(float(tol_nm), 1.0)
    cx, cy = int(point["x"] // cell), int(point["y"] // cell)
    found: List[Tuple[Dict[str, Any], float]] = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for q in index.get((point["die"], cx + dx, cy + dy), ()):
                if taken is not None and q["i"] in taken:
                    continue
                d = ((point["x"] - q["x"]) ** 2 + (point["y"] - q["y"]) ** 2) ** 0.5
                if d <= tol_nm:
                    found.append((q, d))
    found.sort(key=lambda pair: (pair[1], pair[0]["i"]))
    return found[:max(1, int(k))]


def build_index(items: Sequence[Any], tol_nm: float) -> Dict[Any, List[Dict[str, Any]]]:
    """一批 ``DefectItem`` → 給 :func:`nearest` 用的網格索引。"""
    return _bucket(points_of(items), max(float(tol_nm), 1.0))


def pair_all(a_items: Sequence[Any], b_items: Sequence[Any],
             tol_nm: float = 500.0) -> List[Tuple[int, int, float]]:
    """整批對整批、**一對一**：回 ``[(a.index, b.index, 距離), …]``。

    一對一（``taken``）跟 KLIP 的 ``used_b`` 是同一件事：B 的一顆不會同時被 A
    的兩顆認領。順序決定誰先挑，所以按 A 的順序走 —— 跟 KLIP 逐字相同。

    ⚠ 這一支是**離線**用的（儀表、報表、測試）。逐顆跑的那條路走
    :func:`build_index` + :func:`nearest`，因為 worker 裡不會有整份 A。
    """
    index = build_index(b_items, tol_nm)
    taken: set = set()
    out: List[Tuple[int, int, float]] = []
    for pa in points_of(a_items):
        hit = nearest(pa, index, tol_nm, k=1, taken=taken)
        if hit:
            q, d = hit[0]
            taken.add(q["i"])
            out.append((pa["i"], q["i"], d))
    return out

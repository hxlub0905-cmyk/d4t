# 畫布上的「加一張卡」選單 — authored 2026-09-08 (F99 P1-1).
"""兩個以前是死路的手勢，現在各開一張選單：

* **空白處按右鍵** → 整個卡片庫，照階段分組（跟左邊那一欄同一個順序、同一
  個字，`step.GROUPS`）。
* **把線拖到空白處放開** → 只列**接得上**的卡：那條線帶的是影像就列吃影像的
  卡，帶的是區域就列吃區域的卡。挑一張就加在放開的地方、線自動接上 ——
  這不違反「加卡不准順手接線」（`CLAUDE.md` 鐵則 10）：那條線是使用者拉的，
  只是終點那張卡晚一秒才出現。

畫布自己不認得卡片庫（它只發 `add_menu_requested` / `link_dropped`），
Studio 也不該長出第三份「卡片庫長什麼樣」—— 所以分組與相容性住在這裡，
兩邊都只是呼叫。純函式那一半（:func:`grouped`、:func:`compatible`）不碰 Qt，
測試不用開視窗。
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence, Tuple

import d4t.core.steps  # noqa: F401 — 觸發卡片註冊（同 `batch.py`：REGISTRY 是 import 時填的）

from ..core.pipeline import get_step
from ..core.pipeline.step import DATA_PORTS, GROUPS, NUMBERS, RESULTS, ParamSpec

__all__ = ["grouped", "compatible", "input_param_for", "build_menu"]

_IMAGE_TYPES = ("image_key", "image_keys")
_REGION_TYPES = ("region_key", "region_keys")


def _inputs(step_key: str) -> List[ParamSpec]:
    """這張卡**吃**的那幾格（不含 ``direction="out"`` 的）。"""
    try:
        cls = get_step(step_key)
    except KeyError:
        return []
    return [p for p in cls.params
            if str(getattr(p, "direction", "in") or "in") != "out"
            and p.type in _IMAGE_TYPES + _REGION_TYPES]


def grouped(step_keys: Sequence[str]) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """``[(階段標題, [(step_key, 卡片名), …]), …]``，照 `step.GROUPS` 的順序；
    空的階段不列（一個空的子選單讀起來像壞掉）。"""
    by_group: Dict[str, List[Tuple[str, str]]] = {}
    for key in step_keys:
        try:
            cls = get_step(str(key))
        except KeyError:
            continue
        gid = str(cls.resolve_group() if hasattr(cls, "resolve_group")
                  else getattr(cls, "group", "") or "")
        by_group.setdefault(gid, []).append((str(key), str(cls.label or key)))
    out: List[Tuple[str, List[Tuple[str, str]]]] = []
    for gid, title, _sub in GROUPS:
        if by_group.get(gid):
            out.append((title, by_group[gid]))
    seen = {gid for gid, _t, _s in GROUPS}
    for gid, items in by_group.items():          # 外掛卡宣告的別的階段
        if gid not in seen and items:
            out.append((gid or "Other", items))
    return out


def _takes_data(step_key: str, kind: str) -> str:
    """這張卡收 ``kind``（``numbers`` / ``results``）那種線的資料埠（沒有回空）。

    Decision 只收數字；Output 卡的 ``results`` 兩種都收（F123 期 2：Output
    寫的是線上游的東西，直接接量測卡也可以）。
    """
    try:
        ports = tuple(get_step(step_key).data_inputs)
    except KeyError:
        return ""
    if RESULTS in ports and kind in DATA_PORTS:
        return RESULTS
    return NUMBERS if (kind == NUMBERS and NUMBERS in ports) else ""


def compatible(step_keys: Sequence[str], kind: str) -> List[str]:
    """``kind`` 是 ``image`` / ``region`` / ``numbers`` / ``results``：哪些卡
    接得上那種線。順序照給的。"""
    if str(kind) in DATA_PORTS:
        return [str(k) for k in step_keys if _takes_data(str(k), str(kind))]
    want = _REGION_TYPES if str(kind) == "region" else _IMAGE_TYPES
    return [str(k) for k in step_keys
            if any(p.type in want for p in _inputs(str(k)))]


def input_param_for(step_key: str, kind: str) -> str:
    """``kind`` 那種線接進這張卡時該落在哪一格（第一格吃那種東西的參數名）。"""
    if str(kind) in DATA_PORTS:
        return _takes_data(str(step_key), str(kind))
    want = _REGION_TYPES if str(kind) == "region" else _IMAGE_TYPES
    for p in _inputs(step_key):
        if p.type in want:
            return str(p.name)
    return ""


def build_menu(parent, step_keys: Sequence[str],
               on_pick: Callable[[str], None], *,
               title: str = "", flat: bool = False):
    """開一張 QMenu。``flat=True`` 不分組（拖線那張只有幾項，分組反而要多點
    一層）。空的時候放一句灰字說為什麼，不放一張空選單。"""
    from PySide6.QtWidgets import QMenu

    menu = QMenu(parent)
    if title:
        head = menu.addAction(title)
        head.setEnabled(False)
        menu.addSeparator()
    groups = grouped(step_keys)
    if not groups:
        act = menu.addAction("no card can take this")
        act.setEnabled(False)
        return menu
    for gtitle, items in groups:
        host = menu if flat else menu.addMenu(gtitle)
        for key, label in items:
            act = host.addAction(label)
            act.triggered.connect(lambda _c=False, k=key: on_pick(k))
    return menu


def pick_at(menu, global_pos) -> Optional[str]:
    """把選單開在 ``global_pos``；只是 `exec` 的薄包裝，測試好替換。"""
    menu.exec(global_pos)
    return None

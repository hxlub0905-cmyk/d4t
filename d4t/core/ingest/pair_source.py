# d4t ingest — authored 2026-08-19 (F15). 把第二份資料掛到 main 上。
"""把**另一份 lot** 掛到已經載好的那一份上（`Dataset.sources[sid]`）。

跟 `glas_export.attach` 同一個位置、同一個理由
----------------------------------------------
卡片**不自己讀檔**。使用者看到的是「這張卡 load 自己的 source」，但引擎裡讀檔
的仍然是 ingest —— 因為影像段快取的簽章是照「這份資料是什麼」算的
（`pipeline/batch._dataset_token_for`）。卡片偷偷讀檔的話，換一份第二 source
而簽章看不見 → 回舊影像，也就是「跑得完、有數字、而且是錯的」（鐵則 9）。

這裡跟 GLAS 那條路差一件事：**這裡不做配對**。GLAS 的 label map 是靠
`image_id == DEFECTID` 精確 join（無參數、不會配錯），所以在 ingest 配好剛好；
這一輪的配對有容差、有取捨、而且會配錯，所以規則在卡片上（`steps/pair_source`），
ingest 只負責「把那一份讀進來、放好」。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .dataset import Dataset


class PairSourceError(Exception):
    """掛不上去，而且**在掛的當下**就講得出為什麼。"""


@dataclass
class AttachReport:
    """掛完之後的一句話（狀態列與測試讀它）。"""
    source_id: str
    kind: str
    items: int
    with_coords: int
    fields: int

    def summary(self) -> str:
        bits = ["%s: %d defect(s), kind=%s" % (self.source_id, self.items,
                                               self.kind)]
        if self.items:
            bits.append("%d with coordinates" % self.with_coords)
        if self.fields:
            bits.append("%d KLARF column(s) carried" % self.fields)
        return " · ".join(bits)


def columns_of(dataset: Any) -> List[str]:
    """這一份 KLARF 有哪些欄（大寫）。沒有 KLARF 就是空的。

    UI 拿它當 `carry` 那一格的選單 —— **欄名程式知道，就不該讓使用者用打的**
    （同 `ParamForm` 的 `stream_choices` / `region_choices`）。
    """
    doc = getattr(dataset, "klarf", None)
    if doc is None:
        return []
    return [str(c).upper() for c in (getattr(doc, "defect_columns", None) or [])]


def fill_fields(dataset: Dataset,
                columns: Optional[Sequence[str]] = None) -> int:
    """把每一顆的 KLARF 欄位填進 ``DefectItem.fields``（回填了幾欄）。

    **只有被掛上來的那一份會做這件事**：`carry` 要讀的是它的欄位（配到那一顆的
    分數欄），而 main 那一份每顆多帶 24 個字串對誰都沒有好處。

    ``columns`` 是**只要這幾欄**（大小寫不拘）；``None`` = 全部。
    為什麼要這個參數：raw data 的 lot 是幾十萬顆，×24 欄字串是幾百 MB 的複製，
    而其中 22 欄從來沒有人 `carry`。這幾欄要進 worker（`sources_for_run` 只送
    items），所以它同時是記憶體與 pickle 的成本。**認得的欄要留著**：一格都
    沒指定就全帶，那是 CLI 與測試的路。

    沒有 KLARF（folder / stack）→ 一欄都沒有，回 0。那不是錯誤，只是
    `carry` 在這種資料上沒有東西可帶。
    """
    doc = getattr(dataset, "klarf", None)
    if doc is None:
        return 0
    cols = columns_of(dataset)
    if not cols:
        return 0
    want = None if columns is None else {str(c).strip().upper()
                                         for c in columns if str(c).strip()}
    keep = [(i, c) for i, c in enumerate(cols) if want is None or c in want]
    rows = list(getattr(doc, "defects", None) or [])
    for item in dataset.items:
        r = int(getattr(item, "klarf_row", -1))
        if not (0 <= r < len(rows)):
            item.fields = {}
            continue
        row = rows[r]
        # **每次都整個換掉**，不是更新 —— 少填一欄的時候舊的那一份還留著的話，
        # 「這一欄現在還在不在」就有兩個答案（而卡片信的是 `fields`）。
        item.fields = {c: (str(row[i]) if i < len(row) else "")
                       for i, c in keep}
    return len(keep)


def missing_columns(dataset: Any,
                    columns: Optional[Sequence[str]]) -> List[str]:
    """``columns`` 裡**這一份根本沒有**的那幾欄（大寫，保留順序）。

    為什麼在這裡問而不是等卡片跑：這裡手上有 KlarfDoc，所以答得出「那它有哪些
    欄」——而卡片手上只有複製過去的那幾欄（`fill_fields` 的 ``columns``），
    它列出來的清單會是「你要的那幾欄」，不是「這一份有的那幾欄」。
    打錯一個欄名的時候，後者才是使用者要看的東西。
    """
    have = set(columns_of(dataset))
    if not have:
        return []
    out: List[str] = []
    for c in (columns or ()):
        c = str(c).strip().upper()
        if c and c not in have and c not in out:
            out.append(c)
    return out


def refill_fields(main: Any, source_id: str,
                  columns: Optional[Sequence[str]] = None) -> int:
    """`carry` 改了之後重填掛著的那一份（回填了幾欄；沒掛回 0）。

    掛的時候只複製「當時 recipe 要的那幾欄」，所以使用者**之後**才在卡片上加
    一欄的話，那一欄不在 `fields` 裡 —— 卡片會照它的規矩擋下來（「這一份沒有
    這個欄位」），而那句話是錯的：欄位在，只是沒複製。KlarfDoc 還在手上
    （`main.sources[sid].klarf`），所以重填是便宜的。
    """
    src = (getattr(main, "sources", None) or {}).get(str(source_id))
    if src is None:
        return 0
    return fill_fields(src, columns)


def attach(main: Dataset, second: Dataset, source_id: str,
           columns: Optional[Sequence[str]] = None) -> AttachReport:
    """把 ``second`` 掛成 ``main`` 的 ``source_id``（**就地修改 main**）。

    掛上去之後 `pair_source` 卡就找得到它了。第二份**不寫回 KLARF、不進 defect
    導覽、不進 Export** —— 它只提供另一張圖與它的座標。
    """
    sid = str(source_id or "").strip()
    if not sid:
        raise PairSourceError("a second source needs a name to refer to it by "
                              "(the card's “Source name” field).")
    if second is None or not getattr(second, "items", None):
        raise PairSourceError("that source has no defects in it.")
    if second is main:
        raise PairSourceError("a lot cannot be paired with itself.")
    second.renumber()
    n_fields = fill_fields(second, columns)
    with_coords = sum(1 for it in second.items
                      if it.xrel_nm is not None and it.yrel_nm is not None)
    main.sources[sid] = second
    return AttachReport(source_id=sid, kind=str(getattr(second, "kind", "")),
                        items=len(second.items), with_coords=with_coords,
                        fields=n_fields)


def source_items(main: Any, source_id: str) -> List[Any]:
    """``main`` 上掛著的那一份的 items（沒掛回空 list）。"""
    src = (getattr(main, "sources", None) or {}).get(str(source_id))
    return list(getattr(src, "items", None) or [])


def sources_for_run(main: Any) -> Dict[str, List[Any]]:
    """要送進 worker 的那一份：``{代號: [DefectItem, …]}``。

    **只送 items，不送 `Dataset`**：`Dataset` 掛著 `KlarfDoc`，而那個東西刻意
    不進 worker（`pipeline/batch` 的模組說明）。`DefectItem` 裝的是路徑不是
    像素，pickle 很便宜。
    """
    out: Dict[str, List[Any]] = {}
    for sid, ds in (getattr(main, "sources", None) or {}).items():
        out[str(sid)] = list(getattr(ds, "items", None) or [])
    return out

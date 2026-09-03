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

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .dataset import (
    # `columns_of` 這個模組自己沒有用到，但它是**轉出口**：`ui/studio.py` 與
    # `__main__.py` 問「那一份第二 lot 有哪些欄」的時候問的是
    # `pair_ingest.columns_of(...)` —— 掛第二份的那一層答得出來才合理。
    # 拿掉它會變成一個 AttributeError，而它只在打錯欄名的那條錯誤路徑上爆。
    Dataset, columns_of, fill_fields, missing_columns_of,   # noqa: F401
)


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


def missing_columns(dataset: Any,
                    columns: Optional[Sequence[str]]) -> List[str]:
    """``columns`` 裡**這一份根本沒有**的那幾欄 —— 見
    :func:`d4t.core.ingest.dataset.missing_columns_of`。

    掛第二份時用它，而 main 那一份問的是同一個問題（F16），所以定義住在
    `ingest/dataset.py`。這裡留一個名字是為了呼叫端不用改 —— **那是搬家，
    不是複製一份**。
    """
    return missing_columns_of(dataset, columns)


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

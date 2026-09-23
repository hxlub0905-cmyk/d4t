# d4t Studio：特徵值印成字 — authored 2026-08-28 (F52).
"""畫面上的數字寫法。**規則本體住在 `d4t/core/numbers.py`**（F117 起）。

搬下去的理由與那整段「六種寫法」的故事都在那一支的說明裡 —— 一句話：
`core/export/html.py` 是第七份，而 core 不 import ui，所以共用的東西往下放。

留在這裡的只有 :func:`format_feature_value_short` —— 它畫**在影像上**，
是刻意的例外，而例外要講得出邊界（見它自己的說明）。
"""
from __future__ import annotations

# 轉出口：呼叫端一直是 `ui.numbers`，F117 搬家時那 14 處一個都沒改。
from pitchapp.core.numbers import (
    FEATURE_SIG_FIGS,
    finite as _finite,
    format_feature_value,
)
from typing import Any

__all__ = ["format_feature_value", "format_feature_value_short",
           "FEATURE_SIG_FIGS"]

#: 極小值的門檻：比這個小就一定走有效位數，不走固定小數。
#:
#: 沒有它的話 `format_feature_value_short` 會把 ``0.000312`` 印成 ``0.00``
#: —— 讀起來是**零**，而那個標記畫在影像上，是使用者盯著看的地方。
_TINY = 5e-3


def format_feature_value_short(value: Any, signed: bool = False) -> str:
    """畫**在影像上**的短版（10 px 高的字，`SNR 66` 比 `SNR 66.116` 好讀）。

    ⚠ **它是刻意的例外，而例外要講得出邊界。** 短的代價是精度，所以：

    * 只在**畫在影像上**的標記用它（`inspectors` 的疊圖），表格與面板一律走
      :func:`format_feature_value`；
    * **極小值退回有效位數**（`_TINY`）—— 舊版把 ``0.000312`` 印成 ``0.00``，
      而「0.00」跟「太小所以看不出來」是兩句完全不同的話。

    ``signed=True`` 時正數前面補 ``+``（差值那種「往哪邊偏」的量）。
    """
    ok, out = _finite(value)
    if not ok:
        return out
    f = float(out)
    a = abs(f)
    if a and a < _TINY:
        text = "%.*g" % (2, f)              # 短版也是短的：兩位有效數字
    elif f == int(f) and a < 1e12:
        text = str(int(f))
    else:
        text = ("%.0f" % f) if a >= 10 else (("%.1f" % f) if a >= 1
                                             else ("%.2f" % f))
    if signed and f > 0:
        text = "+" + text
    # 真的減號（U+2212），跟畫面其他地方一致 —— ASCII 的 `-` 在小字級下
    # 跟連字號分不出來。
    return text.replace("-", "−")

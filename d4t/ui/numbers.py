# d4t Studio：特徵值印成字 — authored 2026-08-28 (F52).
"""**一個特徵值，一種寫法。**

在這一支出生之前，同一個數字在畫面上有**六種**寫法 —— 六個各自寫的格式化
函式，沒有一個共用：

===========================  ==================================
`results_table` 的 DisplayRole  ``%.4g``
`why_panel._fmt`               ``%.4g``（抄的第二份）
`widgets._fmt_number`          整數捷徑 ＋ ``%.3f`` ＋極小值 ``%.3g``
`gallery._fmt_score`           整數捷徑 ＋ ``%.3g``
`inspectors._fmt`              ``%.3g`` / ``%.3f`` / ``%.1f`` 三段
`inspectors._short_number`     ``%.0f`` / ``%.1f`` / ``%.2f`` 三段
===========================  ==================================

實測同一個值印出來長這樣：

=========  ==========  ==========  ==========  =========
值          結果表       特徵表       Gallery     影像標記
=========  ==========  ==========  ==========  =========
66.1163    66.12       66.116      66.1        66
1234.5     **1234**    1234.500    1.23e+03    1234
99.995     **100**     99.995      100         100
0.000312   0.000312    0.000312    0.000312    **0.00**
=========  ==========  ==========  ==========  =========

三個真的會出事的地方：

1. **``99.995`` 在結果表寫 100、在單顆特徵表寫 99.995。** 使用者在 Results
   看到一顆是 100，點進去變成 99.995 —— 他會以為自己點錯顆。
2. **``1234.5`` 一邊丟掉 ``.5``、一邊補三位假精度**（``1234.500``），
   方向剛好相反。
3. **``0.000312`` 畫在影像上是 ``0.00``** —— 那讀起來是零，而影像上的標記
   正是使用者盯著看的地方。

為什麼是 ``%.5g``
-----------------
第一版提案寫的是 ``%.4g``（結果表原本那一份，最多地方在用）。**算過之後那
是錯的**：``%.4g`` 把 ``99.995`` 印成 ``100``，而那正是上面第 1 條的危害 ——
統一到一個會誤導的寫法上，只是把不一致換成一致地錯。

``%.5g`` 讓 ``99.995`` 與 ``1234.5`` 都完整留著，而且仍然比 ``%.6g`` 短。
**有效位數而不是固定小數**，所以不會出現 ``1234.500`` 那種發明出來的精度。

> **統一之前先算一次。** 挑「最多人用的那一份」是一個看起來安全、實際上沒有
> 檢查過的判準。

⚠ **這一支不管 CSV。** 匯出走 `core/export`，寫的是原值（`repr`）——
畫面是給人讀的，檔案是給下游程式讀的，兩件事。
"""
from __future__ import annotations

import math
from typing import Any

__all__ = ["format_feature_value", "format_feature_value_short",
           "FEATURE_SIG_FIGS"]

#: 顯示用的有效位數（見模組說明為什麼不是 4）。
FEATURE_SIG_FIGS = 5

#: 極小值的門檻：比這個小就一定走有效位數，不走固定小數。
#:
#: 沒有它的話 `format_feature_value_short` 會把 ``0.000312`` 印成 ``0.00``
#: —— 讀起來是**零**，而那個標記畫在影像上，是使用者盯著看的地方。
_TINY = 5e-3


def _finite(value: Any):
    """``(是不是數字, float 值 或 已經決定好的字串)``。三種非數字各有各的字。"""
    if value is None:
        # **沒有值就留白**（F30）。以前某些地方走 `str(value)`，於是 ``None``
        # 會在縮圖說明列上畫出 `None` 那四個字 —— 判定樹是分類器，多數樹沒有
        # 分數表達式，那時候**每一格**都會是它。
        return False, ""
    if isinstance(value, bool):
        return False, "Yes" if value else "No"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False, str(value)
    if math.isnan(f):
        return False, "NaN"
    if math.isinf(f):
        return False, "∞" if f > 0 else "-∞"
    return True, f


def format_feature_value(value: Any) -> str:
    """一個特徵值 → 畫面上的字。**全 UI 只有這一支。**

    * ``None`` → 空字串（不是 ``None`` 那四個字）；
    * ``True`` / ``False`` → ``Yes`` / ``No``（診斷旗標是布林，而 ``1.0``
      對使用者不是一句話）；
    * 整數 → 不拖小數（``12``，不是 ``12.000``）；
    * 其他 → :data:`FEATURE_SIG_FIGS` 位**有效數字**。
    """
    ok, out = _finite(value)
    if not ok:
        return out
    f = float(out)
    if f == int(f) and abs(f) < 1e12:
        return str(int(f))
    return "%.*g" % (FEATURE_SIG_FIGS, f)


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

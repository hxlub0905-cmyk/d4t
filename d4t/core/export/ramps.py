"""色階 —— **一階色 ＋ 0–1 → 一個顏色**，而且只有這一個家。

⚠ 這一支 2026-09-23 從 `uniformity_charts.py` 拆出來（F120 的獨立 app）。
理由是一條**跨層的線**：`ui/image_view.py` 為了畫影像上那條色條要一個
`heat_hex`，於是一個 widget import 了**報表產生器** —— 而那一支底下掛著
`boxplot`／`chart_draw`／`report`／`klarf_out`／`klarf_core`。實測：為了一個
顏色函式，任何用到 `image_view` 的東西都多背 **10 支模組、7,672 行**。

拆出來的**不是**第二份：`uniformity_charts` 從這裡轉出去，所以
`uniformity_charts.heat_hex` / `SEQ_RAMP` 這些既有的名字一個都沒換家。
**色階抄第二份的那天，畫面上的紅跟報表裡的紅會是兩個紅。**
"""
from __future__ import annotations

import math
from typing import Sequence, Tuple

__all__ = ["HEAT_RAMP", "SEQ_RAMP", "heat_hex", "seq_hex"]

#: 熱圖的色階 —— 冷到熱。**刻意不含區域色的任何一個**：這張圖上顏色的意思是
#: 「值多少」，而不是「這是哪一群」。兩種意思共用一個顏色的話，讀圖的人得先
#: 決定現在是哪一種。
HEAT_RAMP: Tuple[str, ...] = (
    "#2b3a67", "#3d6fa8", "#4aa3a2", "#c9c05a", "#e8913c", "#c0392b")

#: **單色階**（由淺到深的藍）—— 表示「大小」的預設。
#:
#: 通用規則是「表示大小用**單一色相、由淺到深**，不要彩虹」：彩虹在中段會製造
#: 出資料裡沒有的假邊界，而讀圖的人會把那道邊界當成一件事。
#: 但半導體的 wafer map 慣例就是彩虹 —— 所以**兩種都留**，預設單色
#: （使用者 2026-09-07：「兩種都可 預設單色」）。切換是 `chart_style` 的
#: `ramp` 那一格。
#:
#: 藍色是這個介面的重音色（`theme.accent` 是 `#3574d6`），所以這一階跟畫面
#: 其他地方是同一個家族。
SEQ_RAMP: Tuple[str, ...] = (
    "#eaf1fc", "#c2d6f2", "#8fb6ec", "#5a8fdd", "#3574d6", "#2b5eb0",
    "#1d3f77")

#: 算不出來的那一格畫什麼（灰，不是色階上的任何一格）。
_MUTED = "#777"


def _ramp_hex(ramp: Sequence[str], t: float) -> str:
    """一階色 ＋ 0–1 → 一個顏色（線性內插，兩端夾住）。"""
    if not math.isfinite(t):
        return _MUTED
    t = min(1.0, max(0.0, float(t)))
    pos = t * (len(ramp) - 1)
    i = min(len(ramp) - 2, int(pos))
    f = pos - i
    a, b = ramp[i], ramp[i + 1]
    out = []
    for k in (1, 3, 5):
        ca, cb = int(a[k:k + 2], 16), int(b[k:k + 2], 16)
        out.append(int(round(ca + (cb - ca) * f)))
    return "#%02x%02x%02x" % tuple(out)


def seq_hex(t: float) -> str:
    """0–1 → **單色階**上的一個顏色（見 :data:`SEQ_RAMP`）。"""
    return _ramp_hex(SEQ_RAMP, t)


def heat_hex(t: float) -> str:
    """0–1 → **彩虹色階**上的一個顏色（線性內插，兩端夾住）。

    **色階唯一的出處** —— 寫出去的 SVG、疊在影像上的那一層、以及影像上那條
    色條都問這一支。抄一份的那天，畫面上的紅跟報表裡的紅會是兩個紅。
    """
    return _ramp_hex(HEAT_RAMP, t)

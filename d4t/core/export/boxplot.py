# -*- coding: utf-8 -*-
# d4t box plot — authored 2026-08-26 (F36).
"""一批的分布 → 一張 box plot（**手寫 SVG，零新相依**）。

為什麼是 SVG 而不是 matplotlib
------------------------------
這個 repo 的相依只有 numpy / opencv / tifffile / PySide6 / openpyxl，而公司機
是**用複製檔案更新的**（`AGENTS.md`）—— 多一個套件就是多一件在受限機器上會
裝不起來的事。而 box plot 的幾何就是幾條線與幾個矩形：手寫的 SVG 比一個
繪圖後端小得多，也不會在沒有顯示器的機器上出問題。

前例已經在了：`ingest/klarf_core._svg_wafer` 用同一套辦法畫 die 熱力圖。

`core` 不得 import Qt（鐵則 1），所以顏色是**參數**不是主題查表 ——
跟 `decide_tree.verdict_rows` 同一個理由，而這張圖的顏色正好從那一支來
（一片葉子一個盒子，顏色跟畫布上的樹一樣）。

一個盒子 = 一片葉子
-------------------
不是「一個 bin 一個盒子」：兩片葉子共用一個 bin 是合法的，而它們是使用者眼中
兩個不同的類別（`verdict_rows` 的說明）。用葉子還有兩個免費的好處 ——
盒子上的名字就是他自己寫的那一句，順序跟畫布上的樹一樣。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

__all__ = ["box_stats", "build_boxplot_svg", "build_boxplot_page"]

#: 盒鬚圖的鬚要伸多遠 —— **1.5 × IQR**（Tukey），統計課本上那一個。
#: 不是「min/max」：一顆離群點會把整張圖的尺度拉走，而那正是它要標出來的東西。
WHISKER_IQR = 1.5

#: 畫不動的時候用的灰（顏色是參數，這一格是最後的退路）。
FALLBACK_COLOUR = "#8a94a6"

_AXIS = "#98a2b3"
_TEXT = "#444"
_MUTED = "#777"
_GRID = "#e8eaee"


def box_stats(values: Sequence[Any]) -> Optional[Dict[str, Any]]:
    """一組數字 → 盒鬚圖要的那幾個數（**算不出來回 ``None``**）。

    ``{n, q1, med, q3, lo, hi, outliers, vmin, vmax}``。``lo``/``hi`` 是鬚的
    端點：**落在 1.5×IQR 之內的真實資料點**，不是 ``q1 − 1.5·IQR`` 那個算出來
    的邊界。差別在圖上看得見 —— 後者會畫出一條伸進沒有資料的地方的鬚。

    NaN / inf **丟掉**（`F19`：算不出來的那一格本來就不寫，而混進來的 NaN 會
    讓整組統計變成 NaN）。一顆都不剩就回 ``None`` —— 那不是「分布是空的」，
    是「這一類沒有這個數字」，而呼叫端要講得出這兩者的差別。
    """
    arr = np.asarray([v for v in (values or [])], dtype=np.float64).ravel()
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    q1, med, q3 = (float(x) for x in np.percentile(arr, [25, 50, 75]))
    iqr = q3 - q1
    lo_fence, hi_fence = q1 - WHISKER_IQR * iqr, q3 + WHISKER_IQR * iqr
    inside = arr[(arr >= lo_fence) & (arr <= hi_fence)]
    # 全部都在柵欄外是做得到的（IQR == 0 且有離群點）—— 那時候鬚就是盒子本身。
    lo = float(inside.min()) if inside.size else q1
    hi = float(inside.max()) if inside.size else q3
    out = arr[(arr < lo_fence) | (arr > hi_fence)]
    return {
        "n": int(arr.size), "q1": q1, "med": med, "q3": q3,
        "lo": lo, "hi": hi,
        "outliers": [float(v) for v in np.unique(out)],
        "vmin": float(arr.min()), "vmax": float(arr.max()),
    }


def _nice_ticks(lo: float, hi: float, want: int = 5) -> List[float]:
    """好讀的刻度（1 / 2 / 5 × 10ⁿ）。"""
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return [lo] if math.isfinite(lo) else [0.0]
    raw = (hi - lo) / max(1, want)
    mag = 10.0 ** math.floor(math.log10(raw))
    step = next((m * mag for m in (1, 2, 5, 10) if m * mag >= raw), 10 * mag)
    first = math.ceil(lo / step) * step
    ticks, v = [], first
    while v <= hi + step * 1e-9 and len(ticks) < 40:
        ticks.append(round(v, 12))
        v += step
    return ticks or [lo, hi]


def _fmt(v: float) -> str:
    if not math.isfinite(v):
        return "-"
    if v == int(v) and abs(v) < 1e15:
        return "%d" % int(v)
    a = abs(v)
    return ("%.3g" if (a < 0.01 or a >= 10000) else "%.2f") % v


def _esc(text: Any) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def build_boxplot_svg(series: Sequence[Dict[str, Any]], title: str = "",
                      subtitle: str = "", width: int = 720,
                      height: int = 340) -> str:
    """一張圖。``series`` 的每一項是 ``{name, values, colour?}``。

    **一組都畫不出來時仍然回一張圖**（一句「沒有數字」），不是空字串 ——
    呼叫端把它塞進 HTML，而一個消失的區塊讀起來是「這裡本來就沒有東西」。
    """
    pad_l, pad_r, pad_t, pad_b = 66, 18, 34 if title else 14, 52
    plot_w = max(80, width - pad_l - pad_r)
    plot_h = max(80, height - pad_t - pad_b)

    boxes = []
    for i, s in enumerate(series or []):
        st = box_stats(s.get("values"))
        boxes.append({"name": str(s.get("name", "")),
                      "colour": str(s.get("colour") or FALLBACK_COLOUR),
                      "stats": st})
    live = [b for b in boxes if b["stats"]]

    o: List[str] = ['<svg viewBox="0 0 %d %d" width="%d" height="%d" '
                    'xmlns="http://www.w3.org/2000/svg" class="boxplot" '
                    'role="img">' % (width, height, width, height)]
    if title:
        o.append('<text x="%d" y="18" font-size="13" font-weight="600" '
                 'fill="%s">%s</text>' % (pad_l - 46, _TEXT, _esc(title)))
    if subtitle:
        o.append('<text x="%d" y="%d" font-size="11" fill="%s">%s</text>'
                 % (pad_l - 46, 32 if title else 16, _MUTED, _esc(subtitle)))
    if not live:
        o.append('<text x="%d" y="%d" font-size="12" fill="%s">no numbers to '
                 'plot</text>' % (pad_l, pad_t + plot_h / 2, _MUTED))
        o.append("</svg>")
        return "\n".join(o)

    lo = min(min(b["stats"]["vmin"], b["stats"]["lo"]) for b in live)
    hi = max(max(b["stats"]["vmax"], b["stats"]["hi"]) for b in live)
    if hi <= lo:                       # 每一顆都一樣 —— 給它一點高度才畫得出來
        lo, hi = lo - 0.5, hi + 0.5
    span = hi - lo
    lo, hi = lo - span * 0.06, hi + span * 0.06

    def y_of(v: float) -> float:
        return pad_t + plot_h - (float(v) - lo) / (hi - lo) * plot_h

    # ---- 座標軸 ----
    for t in _nice_ticks(lo, hi):
        y = y_of(t)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s"/>'
                 % (pad_l, y, pad_l + plot_w, y, _GRID))
        o.append('<text x="%d" y="%.1f" font-size="10" text-anchor="end" '
                 'fill="%s">%s</text>' % (pad_l - 6, y + 3, _MUTED, _fmt(t)))
    o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s"/>'
             % (pad_l, pad_t, pad_l, pad_t + plot_h, _AXIS))

    slot = plot_w / float(len(boxes))
    bw = min(58.0, slot * 0.52)
    for i, b in enumerate(boxes):
        cx = pad_l + slot * (i + 0.5)
        name = b["name"]
        st = b["stats"]
        if not st:
            # **這一類沒有這個數字** —— 說出來，不是留一格空白（那讀起來像
            # 「這一類不存在」，而它存在，只是每一顆都沒量到）。
            o.append('<text x="%.1f" y="%.1f" font-size="10" '
                     'text-anchor="middle" fill="%s">no data</text>'
                     % (cx, pad_t + plot_h / 2, _MUTED))
        else:
            col = b["colour"]
            y1, y3, ym = y_of(st["q1"]), y_of(st["q3"]), y_of(st["med"])
            ylo, yhi = y_of(st["lo"]), y_of(st["hi"])
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                     'stroke="%s" stroke-width="1.2"/>'
                     % (cx, ylo, cx, yhi, col))
            for yy in (ylo, yhi):      # 鬚的兩端各一橫
                o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                         'stroke="%s" stroke-width="1.2"/>'
                         % (cx - bw / 4, yy, cx + bw / 4, yy, col))
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                     'fill="%s" fill-opacity="0.18" stroke="%s" '
                     'stroke-width="1.4" rx="2"/>'
                     % (cx - bw / 2, min(y1, y3), bw, max(1.0, abs(y1 - y3)),
                        col, col))
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                     'stroke="%s" stroke-width="2.2"/>'
                     % (cx - bw / 2, ym, cx + bw / 2, ym, col))
            for v in st["outliers"]:
                o.append('<circle cx="%.1f" cy="%.1f" r="2" fill="none" '
                         'stroke="%s" stroke-width="1"/>'
                         % (cx, y_of(v), col))
            o.append('<title>%s: n=%d, median %s, q1 %s, q3 %s</title>'
                     % (_esc(name), st["n"], _fmt(st["med"]),
                        _fmt(st["q1"]), _fmt(st["q3"])))
        # ---- 底下的名字與顆數 ----
        label = name if len(name) <= 18 else name[:17] + "…"
        o.append('<text x="%.1f" y="%d" font-size="11" text-anchor="middle" '
                 'fill="%s">%s</text>'
                 % (cx, pad_t + plot_h + 16, _TEXT, _esc(label)))
        o.append('<text x="%.1f" y="%d" font-size="10" text-anchor="middle" '
                 'fill="%s">n=%d</text>'
                 % (cx, pad_t + plot_h + 30, _MUTED,
                    st["n"] if st else 0))
    o.append("</svg>")
    return "\n".join(o)


def build_boxplot_page(charts: Sequence[Dict[str, Any]], title: str,
                       subtitle: str = "", note: str = "") -> str:
    """一份只有圖的 HTML（一個特徵一張圖，由上往下）。

    刻意**不共用 `html.CSS`**：那一份是為了一張幾千列的表寫的（sticky 表頭、
    `max-height:70vh` 的捲動框），而這一頁上一張表都沒有。抄過來的話，改那一份
    的人會不知道自己也在改這一頁。
    """
    o = ["<!doctype html><html><head><meta charset='utf-8'>",
         "<title>%s</title>" % _esc(title),
         "<style>",
         "body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222}",
         "h1{font-size:18px;margin:0 0 4px}",
         ".sub{color:#666;font-size:12px;margin:0 0 18px}",
         ".note{color:#666;font-size:12px;margin:0 0 20px;max-width:60em}",
         "figure{margin:0 0 26px}",
         "svg.boxplot{display:block;max-width:100%;height:auto}",
         "</style></head><body>",
         "<h1>%s</h1>" % _esc(title)]
    if subtitle:
        o.append("<p class='sub'>%s</p>" % _esc(subtitle))
    if note:
        o.append("<p class='note'>%s</p>" % _esc(note))
    if not charts:
        o.append("<p class='note'>Nothing to plot: none of the numbers you "
                 "picked came out of this run.</p>")
    for ch in charts or []:
        o.append("<figure>%s</figure>" % build_boxplot_svg(
            ch.get("series") or [], title=str(ch.get("title", "")),
            subtitle=str(ch.get("subtitle", ""))))
    o.append("</body></html>")
    return "\n".join(o)

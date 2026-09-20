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
from typing import Any, Dict, List, Optional, Sequence, Tuple

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


#: **圖標題放哪、多粗**（F117 F8）—— 四張圖共用一份。
#:
#: 走查記的是「Box plot 標題靠左、其他置中」。兩種都好看，而**同一頁上兩種
#: 就是不對**：眼睛會以為那是兩類東西。選靠左的理由有兩個 ——
#:
#: * 盒鬚圖的副標就在標題正下方、而且是靠左的；標題置中會把那一對拆開。
#: * 那一頁是**一疊圖**，上面還有標題與一張表，全部靠左 —— 置中的圖標題在
#:   那一疊裡是唯一一個不對齊的東西。
#:
#: ⚠ 這兩個常數住在 `boxplot.py` 是因為 `uniformity_charts` import 它（反過來
#: 是循環，見那一邊 `_fill` 的說明）。
TITLE_X = 20
TITLE_WEIGHT = "600"


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


def _fill(style: Dict[str, Any], base: str, opacity: float) -> Tuple[str, str]:
    """填色與濃度 —— **跟 `uniformity_charts.fill_attrs` 同一套規則**。

    ⚠ 這裡不 import 那一支：``uniformity_charts`` 是 import **這個模組**的那
    一邊（見檔頭），反過來會是循環。規則只有六行，而兩邊有一條測試對著。
    倍率 1.0 時 opacity 逐位元組等於以前那個字面值。
    """
    ink = str(style.get("fill_color", "") or "") or base
    k = float(style.get("fill_strength", 1.0) or 0.0)
    a = max(0.0, min(1.0, float(opacity) * k))
    text = ("%.3f" % a).rstrip("0").rstrip(".") or "0"
    return ink, text


def _refs(o: List[str], style: Dict[str, Any], lo: float, hi: float,
          px: float, py: float, pw: float, ph: float) -> None:
    """規格線 —— **借 `uniformity_charts.draw_refs`**，不在這裡再畫一次。

    ⚠ 這裡的 SVG 用雙引號、那邊用單引號（兩套序列化，F88 §14 量過），但
    **SVG 不在乎引號**，而「規格線長什麼樣」只有一個出處才不會漂。
    """
    from .uniformity_charts import draw_refs

    draw_refs(o, dict(style or {}), lo, hi, px, py, pw, ph)


def build_boxplot_svg(series: Sequence[Dict[str, Any]], title: str = "",
                      subtitle: str = "", width: int = 720,
                      height: int = 340,
                      style: Optional[Dict[str, Any]] = None) -> str:
    """一張圖。``series`` 的每一項是 ``{name, values, colour?}``。

    **一組都畫不出來時仍然回一張圖**（一句「沒有數字」），不是空字串 ——
    呼叫端把它塞進 HTML，而一個消失的區塊讀起來是「這裡本來就沒有東西」。
    """
    # 外觀（F87）：`style` 沒給就是以前那幾個寫死的值 —— 既有呼叫端
    # （`output_report` 的盒鬚圖）一個位元組都沒有變。
    #
    # ⚠ **四張圖要吃同一份設定。** 盒鬚圖是唯一走這一支的那一張，而
    # 「字級只對四張裡的兩張有效」是最難發現的那種不一致：使用者調了、
    # 有三張變了、一張沒有，而畫面上沒有任何線索說為什麼。
    # ⚠ ``st`` 在下面的迴圈裡被**重新綁定**成每一組的統計量（`box_stats`），
    # 所以設定那一份另外留一個名字 —— 迴圈之後還要用它畫軸名。
    st_all = dict(style or {})
    st = st_all
    tick_size = float(st.get("tick_size", 10) or 10)
    tick_w = "700" if st.get("tick_bold") else "400"
    tick_ink = str(st.get("tick_color", "") or "") or _TEXT
    axis_size = float(st.get("axis_size", 11) or 11)
    axis_w = "700" if st.get("axis_bold") else "400"
    axis_ink = str(st.get("axis_color", "") or "") or _TEXT
    # ⚠ **線與記號也要吃設定**（F87 第七刀）。F87 第二刀只接了字 —— 而那一刀
    # 的 commit 訊息自己寫著「四張圖要吃同一份設定，字級只對四張裡的兩張有效
    # 是最難發現的那種不一致」。線寬與記號大小是同一句話的下半：使用者把
    # `Lines width` 拉到 4，三張變粗、盒鬚圖沒有；`Whiskers` 關掉，什麼都沒
    # 發生（那一格在這之前**沒有任何程式碼讀它**）。
    #
    # 做法是**按比例縮放既有的常數**，不是換成一個新數字：預設值下每一條線
    # 的粗細逐位元組不變（`output_report` 的盒鬚圖沒給 style）。
    k_line = float(st.get("line_width", 1.6) or 1.6) / 1.6
    line_ink = str(st.get("line_color", "") or "")
    k_dot = float(st.get("point_size", 2.6) or 2.6) / 2.6
    dot_ink = str(st.get("point_color", "") or "")
    whiskers = bool(st.get("whiskers", True))
    pad_l, pad_r, pad_t, pad_b = 66, 18, 34 if title else 14, 52
    plot_w = max(80, width - pad_l - pad_r)
    plot_h = max(80, height - pad_t - pad_b)

    boxes = []
    for s in series or []:
        st = box_stats(s.get("values"))
        boxes.append({"name": str(s.get("name", "")),
                      "colour": str(s.get("colour") or FALLBACK_COLOUR),
                      "stats": st})
    live = [b for b in boxes if b["stats"]]

    o: List[str] = ['<svg viewBox="0 0 %d %d" width="%d" height="%d" '
                    'xmlns="http://www.w3.org/2000/svg" class="boxplot" '
                    'role="img">' % (width, height, width, height),
                    # **白底要畫出來**（F87 第七刀，使用者 2026-09-07：
                    # 「暗色模式下 preview chart box plot 的表示會跟其他人不
                    # 一樣」）。以前這一張沒有底：在報表的白色頁面上看不出來，
                    # 但 Studio 的圖視窗會用主題色當底 —— 暗色主題下這張圖是
                    # **透明**的，深灰的字落在近黑的底上幾乎看不見，而旁邊三
                    # 張都是白卡片。
                    #
                    # 補的是**底**不是主題：這四張圖會被寫進 HTML 報表、貼進
                    # 投影片，那些地方是白的。四張一致才是重點。
                    '<rect width="%d" height="%d" fill="#fff"/>'
                    % (width, height)]
    if title:
        o.append('<text x="%d" y="18" font-size="13" font-weight="%s" '
                 'fill="%s">%s</text>'
                 % (TITLE_X, TITLE_WEIGHT, _TEXT, _esc(title)))
    if subtitle:
        o.append('<text x="%d" y="%d" font-size="11" fill="%s">%s</text>'
                 % (TITLE_X, 32 if title else 16, _MUTED, _esc(subtitle)))
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
    for t in _nice_ticks(lo, hi, int(st_all.get("yticks", 5) or 5)):
        y = y_of(t)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s"/>'
                 % (pad_l, y, pad_l + plot_w, y, _GRID))
        o.append('<text x="%d" y="%.1f" font-size="%g" font-weight="%s" text-anchor="end" '
                 'fill="%s">%s</text>'
                 % (pad_l - 6, y + tick_size * 0.3, tick_size, tick_w,
                    tick_ink, _fmt(t)))
    o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s"/>'
             % (pad_l, pad_t, pad_l, pad_t + plot_h, _AXIS))

    # ⚠ **規格線畫在盒子之前** —— 它是背景上的一條參考，不是資料；畫在
    # 資料之上會從盒子上壓過去。走的是**跟另外四張圖同一支**（`draw_refs`），
    # 不然「規格線長什麼樣」會在同一份報表裡有兩種答案。
    _refs(o, st_all, lo, hi, pad_l, pad_t, plot_w, plot_h)

    slot = plot_w / float(len(boxes))
    bw = min(58.0, slot * 0.52)
    for i, b in enumerate(boxes):
        cx = pad_l + slot * (i + 0.5)
        name = b["name"]
        st = b["stats"]
        if not st:
            # **這一類沒有這個數字** —— 說出來，不是留一格空白（那讀起來像
            # 「這一類不存在」，而它存在，只是每一顆都沒量到）。
            o.append('<text x="%.1f" y="%.1f" font-size="%g" font-weight="%s" '
                     'text-anchor="middle" fill="%s">no data</text>'
                     % (cx, pad_t + plot_h / 2, tick_size, tick_w, _MUTED))
        else:
            col = b["colour"]
            ink = line_ink or col
            dot = dot_ink or col
            y1, y3, ym = y_of(st["q1"]), y_of(st["q3"]), y_of(st["med"])
            ylo, yhi = y_of(st["lo"]), y_of(st["hi"])
            if whiskers:
                o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                         'stroke="%s" stroke-width="%.1f"/>'
                         % (cx, ylo, cx, yhi, ink, 1.2 * k_line))
                for yy in (ylo, yhi):      # 鬚的兩端各一橫
                    o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                             'stroke="%s" stroke-width="%.1f"/>'
                             % (cx - bw / 4, yy, cx + bw / 4, yy, ink,
                                1.2 * k_line))
            face, alpha = _fill(st_all, col, 0.18)
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                     'fill="%s" fill-opacity="%s" stroke="%s" '
                     'stroke-width="%.1f" rx="2"/>'
                     % (cx - bw / 2, min(y1, y3), bw, max(1.0, abs(y1 - y3)),
                        face, alpha, ink, 1.4 * k_line))
            o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                     'stroke="%s" stroke-width="%.1f"/>'
                     % (cx - bw / 2, ym, cx + bw / 2, ym, ink, 2.2 * k_line))
            for v in st["outliers"]:
                # 離群點是**資料**，不受 `points`（「一格框一個記號」）管 ——
                # 關掉它們等於把「有一顆特別遠」這件事藏起來。
                o.append('<circle cx="%.1f" cy="%.1f" r="%g" fill="none" '
                         'stroke="%s" stroke-width="1"/>'
                         % (cx, y_of(v), round(2.0 * k_dot, 2), dot))
            o.append('<title>%s: n=%d, median %s, q1 %s, q3 %s</title>'
                     % (_esc(name), st["n"], _fmt(st["med"]),
                        _fmt(st["q1"]), _fmt(st["q3"])))
        # ---- 底下的名字與顆數 ----
        label = name if len(name) <= 18 else name[:17] + "…"
        o.append('<text x="%.1f" y="%d" font-size="%g" font-weight="%s" text-anchor="middle" '
                 'fill="%s">%s</text>'
                 % (cx, pad_t + plot_h + 16, axis_size, axis_w, axis_ink,
                    _esc(label)))
        o.append('<text x="%.1f" y="%d" font-size="%g" font-weight="%s" text-anchor="middle" '
                 'fill="%s">n=%d</text>'
                 % (cx, pad_t + plot_h + 30, tick_size, tick_w, _MUTED,
                    st["n"] if st else 0))

    # ---- 兩條軸的名字（F87 第七刀）------------------------------------------
    # ⚠ 這一段以前**不存在**：於是設定編輯器 Box plot 那一頁的「Bottom axis
    # name」「Side axis name」是兩個打得進去、卻什麼都不會發生的格子。
    # 一格答了也沒用的設定比沒有那一格更糟（推廣鐵則），而它是
    # `test_every_editor_moves_the_preview` 逐格試出來的。
    #
    # 位置與另外三張一字不差（`uniformity_charts._axis_names`）—— 四張圖擺在
    # 同一頁上，軸名跳來跳去讀起來像四份不同的報表。
    xl = str(st_all.get("xlabel") or "")
    yl = str(st_all.get("ylabel") or "")
    if xl:
        o.append('<text x="%.1f" y="%d" font-size="%g" font-weight="%s" '
                 'fill="%s" text-anchor="middle">%s</text>'
                 % (pad_l + plot_w / 2, height - 8, axis_size, axis_w,
                    axis_ink, _esc(xl)))
    if yl:
        cy = pad_t + plot_h / 2
        o.append('<text x="12" y="%.1f" font-size="%g" font-weight="%s" '
                 'fill="%s" text-anchor="middle" '
                 'transform="rotate(-90 12 %.1f)">%s</text>'
                 % (cy, axis_size, axis_w, axis_ink, cy, _esc(yl)))
    o.append("</svg>")
    return "\n".join(o)


def build_boxplot_page(charts: Sequence[Dict[str, Any]], title: str,
                       subtitle: str = "", note: str = "",
                       lead: str = "", extra_css: str = "") -> str:
    """一份只有圖的 HTML（一張圖一列，由上往下）。

    ``charts`` 的每一項要嘛帶 ``series``（這裡畫成盒鬚圖），要嘛帶 ``svg``
    （已經畫好的，原樣放進去）—— 後者是 F85 的四種均勻度圖走的路。

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
         "figure{margin:0}",
         # **寬的頁面排兩欄**（F117 F7）。走查記的是「四張圖單欄，寬頁右半
         # 空白」—— 那四張圖問的是同一張影像的四個面向，而使用者是拿它們
         # **互相對照**的：一張在螢幕上、一張要捲下去，等於沒有並排。
         #
         # ⚠ **用 `auto-fit` 而不是寫死兩欄**：窄的頁面（筆電、投影、印出來
         # 的 A4）自己收回一欄，不必判斷誰在看。一張圖的那一頁也照樣是一欄
         # —— 它本來就只有一欄可排。
         #
         # 560px 是那幾張 SVG（640 寬）縮到還讀得出刻度的寬度；再窄就寧可
         # 排一欄，因為**讀不到刻度的兩張圖不如一張讀得到的**。
         ".sheet{display:grid;gap:26px;"
         "grid-template-columns:repeat(auto-fit,minmax(560px,1fr))}",
         "svg.boxplot{display:block;max-width:100%;height:auto}",
         "figure svg{display:block;max-width:100%;height:auto}",
         # 呼叫端補的樣式（F86：均勻度那一頁的摘要表）。版型仍然只有一份 ——
         # 兩頁會並排在同一個報表資料夾裡。
         str(extra_css or ""),
         "</style></head><body>",
         "<h1>%s</h1>" % _esc(title)]
    if subtitle:
        o.append("<p class='sub'>%s</p>" % _esc(subtitle))
    if note:
        o.append("<p class='note'>%s</p>" % _esc(note))
    # 圖**上方**那一塊（F86：均勻度的數字表）。原樣放進去 —— 呼叫端已經
    # 跳脫過了；`note` 那一格才是純文字。
    if lead:
        o.append(str(lead))
    if not charts:
        o.append("<p class='note'>Nothing to plot: none of the numbers you "
                 "picked came out of this run.</p>")
    o.append("<div class='sheet'>")
    for ch in charts or []:
        # 已經畫好的就直接放（F85：均勻度那四種圖不是盒鬚圖，但**版型只有
        # 一份** —— 兩頁會並排在同一個報表資料夾裡，字級不一樣的那天沒有人
        # 會知道為什麼）。沒有 `svg` 的照舊由這裡畫，既有呼叫端一個字不動。
        ready = str(ch.get("svg") or "")
        o.append("<figure>%s</figure>" % (ready or build_boxplot_svg(
            ch.get("series") or [], title=str(ch.get("title", "")),
            subtitle=str(ch.get("subtitle", "")))))
    o.append("</div>")
    o.append("</body></html>")
    return "\n".join(o)

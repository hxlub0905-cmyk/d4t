# d4t report rendering — authored 2026-08-25 (F29 C2).
"""一份可以寄出去的 HTML 報表 —— **兩張卡共用同一支**。

`output_html`（一個檔案）與 `output_bundle`（一個資料夾：報表 ＋ 一顆一張的
疊圖 ＋ CSV ＋ recipe）產的是同一份東西，差別只在「圖放不放得進來」。
以前 `output_html` 把整份 HTML inline 在 `run_batch` 裡 —— 第二張卡要嘛抄一份
（兩份會漂），要嘛長得不一樣（同一批資料兩種報表，而使用者分不出差別）。

版面照 Results 那三段（F27）
----------------------------
使用者跑完一整批之後問的是**三個依序的問題**，而報表要照那個順序排：

1. **判定** —— 每一類幾顆。一列一片葉子（不是一個 bin：兩片葉子共用一個 bin
   是合法的），**顆數就是那條橫條的寬度**。
2. **哪幾顆** —— 一顆一列的表，可以照任何一欄排序。
3. **憑什麼** —— 同一列上量出來的每一個數字（就是上面那張表的右半）。

⚠ **表格裡預設不放縮圖。** 6000 個 ``<tr>`` 各塞一個 ``<img>``，即使 lazy
load，光是 DOM 節點就會讓瀏覽器很鈍。改成**點一列 → 右邊那一格換圖**，
整份報表從頭到尾只有**一個** ``<img>``。

**而 characterization 那一份剛好相反**（:func:`build_char_report`，F33）：
那種批次是三十顆，使用者要的是「一一對應」—— 圖跟數字在同一列上，一眼掃完。
點一列換一張圖答不出那句話，因為任何一個時刻畫面上只有一顆。上面那個取捨的
每一項在幾十顆的規模都反過來，所以它是**第二支函式**（共用這裡的 CSS／跳脫／
判定那一段），而不是這一支的一個旗標。

⚠ **圖是相對路徑，不是 base64。** 6000 張 JPEG 嵌進 HTML 是 ~76 MB 的一個
檔案（而 PNG 是 566 MB）；擺成 ``images/<id>.jpg`` 的話報表本身約 3 MB，
瀏覽器一次只載看得到的那一張。代價是「一個資料夾而不是一個檔案」——
所以 `output_html` 那張卡**沒有圖**（它的賣點就是單檔可轉寄），
要圖的走 bundle。

沒有 Qt（鐵則 1）
-----------------
每一類幾顆是 `core.pipeline.decide_tree` 算的 —— 那份邏輯 2026-08-25 從
`ui/tree_scene.py` 搬進 core 正是為了這一支（**不留第二份**）。
類別的顏色也來自那裡（`LEAF_PALETTE`），所以報表上那一類的顏色跟畫面上是
同一個。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

from ..pipeline import decide_tree

__all__ = ["build_report", "build_char_report", "write_html", "escape",
           "number", "bin_summary", "CSS", "NUISANCE_HEX"]

#: bin 0（慣例上的 nuisance）在報表上的顏色 —— **跟 core 那一份同一個**
#: （畫面上會換成主題的 `theme.TOKENS["seg_disabled"]`）。
NUISANCE_HEX = decide_tree.NUISANCE_HEX

CSS = """
body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222}
h1{font-size:18px;margin:0 0 4px} .sub{color:#666;font-size:12px;margin:0 0 18px}
h2{font-size:13px;margin:22px 0 8px;color:#444;font-weight:600}
table{border-collapse:collapse;font-size:12px}
th,td{border:1px solid #ddd;padding:4px 8px;text-align:right;white-space:nowrap}
th{background:#f4f5f7;position:sticky;top:0;text-align:center;cursor:pointer}
td.id,td.err{text-align:left} tr.bad td{background:#fdeeeb}
tr.pick td{outline:2px solid #3574d6;outline-offset:-2px}
.cards{margin:0 0 18px;font-size:12px;color:#444}
.cards b{font-weight:600}
.verdict{margin:0 0 18px}
.vrow{display:flex;align-items:center;gap:8px;font-size:12px;margin:3px 0}
.vname{width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.vbin{width:52px;color:#666}
.vbar{height:12px;border-radius:2px;min-width:2px}
.vn{width:56px;color:#444}
.vpure{width:70px;color:#666}
.split{display:flex;gap:18px;align-items:flex-start}
.tablewrap{overflow:auto;max-height:70vh}
.viewer{position:sticky;top:0;flex:0 0 auto}
.viewer img{max-width:520px;border:1px solid #ddd;display:block}
.viewer .cap{font-size:12px;color:#666;margin:4px 0 0}
td.shot{text-align:center;padding:4px}
td.shot img{max-width:180px;max-height:180px;border:1px solid #ddd;display:block}
td.shot a{display:block}
td.none{color:#999;font-style:italic;text-align:center}
td.verdict{text-align:left}
.chip{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px}
"""


def escape(value: Any) -> str:
    """給 HTML 用的跳脫。**自己寫一份**是因為 `html.escape` 也在 stdlib，
    但這裡要順便把 None 變成空字串。"""
    if value is None:
        return ""
    s = str(value)
    for a, b in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;")):
        s = s.replace(a, b)
    return s


def number(value: Any) -> str:
    """數字 → 短一點的字（NaN 是空的 —— **不是 0**）。"""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return escape(value)
    if f != f:                      # nan
        return ""
    return ("%.4g" % f) if abs(f) < 1e15 else "%g" % f


def bin_summary(bins: Dict[Any, int]) -> str:
    """``bin 0=12, bin 1=8, (none)=1`` —— 沒跑起來的那幾顆 bin 是 None，
    而它們**要出現在這一行上**（少了的話「這批有幾顆沒跑」看不出來）。"""
    def order(item):
        k = item[0]
        return (k is None, k if k is not None else 0)

    return ", ".join("%s=%d" % ("(none)" if k is None else k, v)
                     for k, v in sorted(bins.items(), key=order))


def _verdict_html(entries: Sequence[Dict[str, Any]]) -> List[str]:
    """判定那一段 —— **一列一片葉子，顆數就是那條橫條的寬度**（同 Results）。

    ``entries`` 來自 `decide_tree.verdict_rows`，跟畫面上那一條用的是同一支
    ——「每一類幾顆」在兩個地方要是同一個數字。
    """
    if not entries:
        return []
    biggest = max(int(e["count"]) for e in entries) or 1
    out = ["<h2>1 &middot; What it decided</h2>", "<div class='verdict'>"]
    for e in entries:
        width = max(2, int(round(220.0 * int(e["count"]) / float(biggest))))
        labelled = int(e.get("labelled") or 0)
        # 沒有 ground truth 就**不畫純度**（不是畫 0%：沒有分母不等於零）。
        pure = ("%.0f%% real" % (100.0 * int(e.get("real") or 0) / labelled)
                if labelled else "")
        out.append(
            "<div class='vrow'><div class='vname'>%s</div>"
            "<div class='vbin'>%s</div>"
            "<div class='vbar' style='width:%dpx;background:%s'></div>"
            "<div class='vn'>%d</div><div class='vpure'>%s</div></div>"
            % (escape(e["name"]),
               # 沒有判定樹的時候那一列本來就叫 "bin 1" —— 再放一格
               # "bin 1" 在旁邊只是把同一句話講兩次。
               "" if (e.get("bin") is None
                      or str(e["name"]) == "bin %s" % e["bin"])
               else "bin %s" % escape(e["bin"]),
               width, escape(e["colour"]), int(e["count"]), escape(pure)))
    out.append("</div>")
    return out


#: 點一列換圖的那幾行。**整份報表只有一個 ``<img>``** —— 見模組說明。
_VIEWER_JS = """
(function(){
  var img=document.getElementById('shot'), cap=document.getElementById('shotcap');
  if(!img) return;
  var last=null;
  document.querySelectorAll('tr[data-img]').forEach(function(tr){
    tr.addEventListener('click', function(){
      if(last) last.classList.remove('pick');
      tr.classList.add('pick'); last=tr;
      img.src=tr.getAttribute('data-img');
      cap.textContent=tr.getAttribute('data-cap')||'';
    });
  });
  var first=document.querySelector('tr[data-img]');
  if(first) first.click();
})();
"""


def _page_head(title: str, rows: Sequence[Dict[str, Any]],
               decide: Any = None, note: str = "") -> List[str]:
    """兩份報表**逐字相同**的那個開頭（F37 B2）。

    標題、「幾顆／幾顆沒跑起來／bins 摘要」那一行、可有可無的一句說明，
    以及第 1 段「判定」。

    以前這 14 行在 :func:`build_report` 與 :func:`build_char_report` 裡各寫
    一次 —— **而它們是同一句話**。版面確實該分開（那個取捨在 6000 顆與 30 顆
    是反過來的，見模組說明），但一樣的那一段沒有理由寫兩次：改了其中一份的
    那一天，同一批資料的兩份報表會有兩個不同的開頭，而沒有任何測試會問。
    """
    rows = list(rows or [])
    bins: Dict[Any, int] = {}
    for r in rows:
        bins[r.get("bin")] = bins.get(r.get("bin"), 0) + 1
    n_bad = sum(1 for r in rows if not r.get("ok"))
    out = ["<!doctype html>", "<html><head><meta charset='utf-8'>",
           "<title>%s</title>" % escape(title),
           "<style>%s</style></head><body>" % CSS,
           "<h1>%s</h1>" % escape(title),
           "<p class='sub'>%d defect(s)%s &middot; bins: %s</p>"
           % (len(rows),
              (" &middot; <b>%d did not run</b>" % n_bad) if n_bad else "",
              escape(bin_summary(bins)))]
    if note:
        out.append("<p class='cards'>%s</p>" % escape(note))
    out += _verdict_html(decide_tree.verdict_rows(decide, rows))
    return out


def build_report(rows: Sequence[Dict[str, Any]], title: str,
                 feature_keys: Sequence[str],
                 decide: Any = None,
                 images: Optional[Dict[Any, str]] = None,
                 cards: str = "") -> str:
    """整批的結果 → 一份完整的 HTML 頁（字串）。

    ``images`` 是 ``{defect_id: 相對路徑}``。給了就多一欄可以點的列與一個
    右邊的看圖區；沒給就完全不產生那些節點（`output_html` 走的是這一條，
    它的賣點是單檔可轉寄）。
    """
    rows = list(rows or [])
    keys = list(feature_keys or [])
    imgs = {str(k): str(v) for k, v in (images or {}).items()}

    out = _page_head(title, rows, decide, cards)
    out.append("<h2>2 &middot; Which ones%s</h2>"
               % (" (click a row to see it)" if imgs else ""))
    if imgs:
        out.append("<div class='split'><div class='tablewrap'>")
    out.append("<table><tr><th>defect</th><th>ok</th><th>score</th>"
               "<th>bin</th>")
    out += ["<th>%s</th>" % escape(k) for k in keys]
    out.append("<th>error</th></tr>")
    for r in rows:
        did = str(r.get("defect_id", ""))
        attrs = "" if r.get("ok") else " class='bad'"
        rel = imgs.get(did)
        if rel:
            attrs += (" data-img=\"%s\" data-cap=\"%s\""
                      % (escape(rel), escape("#%s  score=%s  bin=%s"
                                             % (did, number(r.get("score")),
                                                r.get("bin")))))
        cells = ["<td class='id'>%s</td>" % escape(r.get("defect_id")),
                 "<td>%s</td>" % ("yes" if r.get("ok") else "no"),
                 "<td>%s</td>" % number(r.get("score")),
                 "<td>%s</td>" % escape(r.get("bin"))]
        feats = r.get("features") or {}
        cells += ["<td>%s</td>" % number(feats.get(k)) for k in keys]
        cells.append("<td class='err'>%s</td>" % escape(r.get("error")))
        out.append("<tr%s>%s</tr>" % (attrs, "".join(cells)))
    out.append("</table>")
    if imgs:
        out.append("</div><div class='viewer'><img id='shot' alt=''>"
                   "<p class='cap' id='shotcap'></p></div></div>")
        out.append("<script>%s</script>" % _VIEWER_JS)
    out.append("</body></html>")
    return "\n".join(out)


def _thumb_cell(rel: Optional[str], alt: str) -> str:
    """一格縮圖。**沒有圖的那一格完全不產生 ``<img>``**（F33）。

    空的 ``src`` 在瀏覽器裡是一個破圖示 —— 而那一格要講的話是「這一顆在
    另一份資料裡不存在」，那是 characterization 的結論之一，不是一個載入失敗。
    """
    if not rel:
        return "<td class='none'>&mdash;</td>"
    return ("<td class='shot'><a href='%s' target='_blank'>"
            "<img src='%s' alt='%s' loading='lazy'></a></td>"
            % (escape(rel), escape(rel), escape(alt)))


def build_char_report(rows: Sequence[Dict[str, Any]], title: str,
                      columns: Sequence[str],
                      thumbs: Dict[Any, Dict[str, Optional[str]]],
                      verdicts: Optional[Dict[Any, Dict[str, Any]]] = None,
                      decide: Any = None,
                      headings: Sequence[str] = ("ground truth", "second lot"),
                      note: str = "") -> str:
    """characterization 的點對點報表 —— **一顆一列，圖跟數字在同一列上**。

    跟 :func:`build_report` 的差別只有一個，而那個差別就是這張卡存在的理由：
    **縮圖直接排在列上**，不是點一列才換圖。使用者原話是「我可以一一對應
    這樣子」—— 點一列換一張圖的版面答不出那句話，因為任何一個時刻畫面上
    只有一顆。

    那個取捨在 6000 顆時是反過來的（見模組說明），所以這是**第二張卡**而不是
    第一張卡的一格參數：一格參數的話「這張卡長什麼樣」就有兩個答案。
    這裡只服務幾十顆的 characterization 批次，顆數上限由卡片講出來。

    ``thumbs`` 是 ``{defect_id: {"main": 相對路徑或 None, "pair": …}}``；
    ``verdicts`` 是 ``{defect_id: decide_tree.verdict_rows 的那一列}`` ——
    葉子的名字**不在 rows 裡**（engine 刻意不放進 CSV schema），所以由呼叫端
    反查一次再送進來。
    """
    rows = list(rows or [])
    keys = [str(c) for c in (columns or [])]
    shots = {str(k): dict(v or {}) for k, v in (thumbs or {}).items()}
    seats = {str(k): dict(v or {}) for k, v in (verdicts or {}).items()}
    left, right = (list(headings) + ["ground truth", "second lot"])[:2]

    out = _page_head(title, rows, decide, note)
    out.append("<h2>2 &middot; Defect by defect</h2>")
    out.append("<div class='tablewrap'><table><tr><th>defect</th>"
               "<th>%s</th><th>%s</th>" % (escape(left), escape(right)))
    out += ["<th>%s</th>" % escape(k) for k in keys]
    out.append("<th>verdict</th></tr>")
    for r in rows:
        did = str(r.get("defect_id", ""))
        pair = shots.get(did) or {}
        cells = ["<td class='id'>%s</td>" % escape(r.get("defect_id")),
                 _thumb_cell(pair.get("main"), "%s %s" % (did, left)),
                 _thumb_cell(pair.get("pair"), "%s %s" % (did, right))]
        feats = r.get("features") or {}
        cells += ["<td>%s</td>" % number(feats.get(k)) for k in keys]
        seat = seats.get(did) or {}
        name = seat.get("name")
        if name:
            cells.append("<td class='verdict'><span class='chip' "
                         "style='background:%s'></span>%s</td>"
                         % (escape(seat.get("colour") or NUISANCE_HEX),
                            escape(name)))
        else:
            cells.append("<td class='verdict'>%s</td>"
                         % escape(r.get("error") or ""))
        out.append("<tr%s>%s</tr>"
                   % ("" if r.get("ok") else " class='bad'", "".join(cells)))
    out.append("</table></div>")
    out.append("</body></html>")
    return "\n".join(out)


def write_html(text: str, path: str) -> str:
    """atomic（鐵則 5）：``.tmp`` + :func:`os.replace`，跟 `report.write_csv` 一樣。"""
    path = str(path)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return path

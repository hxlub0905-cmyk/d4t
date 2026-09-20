# d4t Studio：使用者面的字 — authored 2026-09-19 (F118 第 1 步).
"""**訊息裡不准出現開發者的字。** 全 UI 只有這一支在做這件翻譯。

為什麼需要它（推廣鐵則）
------------------------
`CLAUDE.md` §1：目標使用者是**不會寫 code 的製程／設備工程師**，任何讓他們
看不懂的設計都是 bug。而在這一支出生之前，畫面上會出現這幾種東西：

===========================  ==========================================
``Removed “dn”``              node **id**（`dn` 是自動產的，不是他取的名字）
``[glv_stats] no input …``    step **key**，而畫面上那張卡叫「GLV」
``'source' is empty``         參數**名**，而那一格上面寫的是「Measure on」
``['glv_max']``               Python 的 list repr
===========================  ==========================================

四樣都是「**內部識別碼漏到使用者面**」的同一個病根（F117 J1／I11／J5／J6），
而它們的解法都是同一句話：**那個名字在畫面上叫什麼，就說什麼**。

為什麼是自己一個模組
--------------------
狀態列、問題清單、參數表的錯誤、Results 的 warning —— **四個地方都要用**。
抄第二份出來的那份一定會漂（`numbers.py` 就是六份寫法收成一份才存在的），
所以這一支的地位跟 `numbers.py` 一樣：**全 UI 只有這一支**。

⚠ **翻譯的邊界**（`CLAUDE.md` §3）
----------------------------------
翻的是**卡片名與欄位 label**（`Step.label` / `ParamSpec.label`）—— 那兩個本來
就是「給人看的字」。**feature 名不翻**（`glv_max` 是 recipe 的鍵，使用者在分數
表達式裡就是這樣打的），**step key 與階段名也不翻**（它們是 recipe JSON 的
鄰居）。把 `glv_max` 翻成「灰階最大值」會讓畫面上的字跟他要打的字對不起來。

本模組 **Qt-free**（純字串），所以可以 headless 測。
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from d4t.core.pipeline import get_step

__all__ = ["card", "card_of_step", "field", "name_list",
           "step_error_text", "trace_error_text", "issue_line",
           "headline", "HEADLINE_MAX"]

#: 一行摘要最長幾個字（F117 G3 定的，H3 起兩個地方共用）。
HEADLINE_MAX = 72


def headline(text: Any, limit: int = HEADLINE_MAX) -> str:
    """一段說明 → **一行摘要**（第一句，太長就切在字之間加省略號）。

    兩個地方用它：範本庫上那一列（F117 G3），以及空白畫面上那三列「這條路吃
    什麼樣的檔案」（F117 H3）。**同一件事只寫在一個地方** —— 兩份的那一天，
    其中一份會學會留問號而另一份不會。

    ⚠ **句號不是唯一的結尾**：出貨的 recipe 裡有一份的第一句是問句
    （``is the gray level even across the field?``）。
    ⚠ **問號與驚嘆號留著，句號不留**：一個問句沒有問號讀起來像被切斷了，
    而句尾的句號在一行摘要上是雜訊。
    """
    body = " ".join(str(text or "").split())
    if not body:
        return ""
    limit = max(1, int(limit))
    cut = min((i for i in (body.find(c) for c in ".?!") if i > 0), default=-1)
    end = cut + (1 if 0 < cut < len(body) and body[cut] in "?!" else 0)
    first = body[:end] if 0 < cut <= limit else body
    if len(first) <= limit:
        return first
    return "%s…" % first[:limit].rsplit(" ", 1)[0]


def card_of_step(step_key: Any) -> str:
    """step key → 卡片庫上那張卡的名字（``glv_stats`` → ``GLV``）。

    認不得的 key 原樣回去 —— **不要猜**：一個沒註冊的 step 出現在訊息裡本身
    就是要給人看的線索（舊 recipe 開在新版上就是這樣）。
    """
    key = str(step_key or "").strip()
    if not key:
        return ""
    try:
        return str(get_step(key).label) or key
    except Exception:          # 沒註冊的 step：原樣回去比猜一個名字好
        return key


def card(model: Any, node_id: Any) -> str:
    """node id → 畫面上那張卡的名字（``dn`` → ``Denoise``）。

    ``model`` 是 `viewmodel.RecipeModel`（或任何有 ``.nodes`` 的東西）。
    找不到那個節點就回 node id 本身 —— 使用者至少還看得到一個可以對照的字。
    """
    nid = str(node_id or "").strip()
    if not nid:
        return ""
    node = (getattr(model, "nodes", None) or {}).get(nid)
    label = card_of_step(getattr(node, "step", "")) if node is not None else ""
    return label or nid


def field(step_key: Any, param: Any) -> str:
    """``(step key, 參數名)`` → 那一格上面寫的字（``source`` → ``Measure on``）。

    沒有 `label` 的參數回參數名本身 —— 那是既有的約定（`ParamSpec.label` 是
    選配的，沒填就直接顯示 `name`），所以這裡跟參數表看到的是同一個字。
    """
    name = str(param or "").strip()
    if not name:
        return ""
    try:
        params = get_step(str(step_key or "")).describe().get("params") or []
    except Exception:
        return name
    for spec in params:
        if str(spec.get("name")) == name:
            return str(spec.get("label") or name)
    return name


def name_list(names: Sequence[Any], limit: int = 4,
              quote: str = "“%s”", conj: str = "and") -> str:
    """一串名字 → 一句話裡讀得下去的字（**不是 Python 的 list repr**）。

    ``['a']`` → ``“a”`` ／ ``['a','b']`` → ``“a” and “b”`` ／
    五個以上 → ``“a”, “b”, “c”, “d” and 3 more``。

    為什麼要截斷：走查看到的那一句把**整條 route 產出的每一個 feature** 都列
    出來（二十幾個），一行變五行 —— 而使用者要找的是「我打錯的那個字最接近
    哪一個」，不是一份清單。清單有它的地方（Features 面板），錯誤訊息不是。
    """
    items = [str(n) for n in (names or ()) if str(n).strip()]
    if not items:
        return ""
    shown, rest = items[:max(1, int(limit))], max(0, len(items) - max(1, int(limit)))
    quoted = [quote % s for s in shown]
    if rest:
        return "%s %s %d more" % (", ".join(quoted), conj, rest)
    if len(quoted) == 1:
        return quoted[0]
    return "%s %s %s" % (", ".join(quoted[:-1]), conj, quoted[-1])


def issue_line(issue: Any, model: Any = None) -> str:
    """一條 lint（`recipe.Issue`）→ **畫面上那一句**。

    有結構就用結構，**沒有就原樣回 `detail`**（F118 §3）—— 48 個產地因此可以
    一個一個搬：搬一個畫面就好一條，中途不會有「半好半壞」的破畫面。

    畫面知道而 core 不知道的兩件事，都在這裡決定：

    * **只有一條 route 就不要講 route。** `route` 是引擎的詞，而單 route 的
      recipe（絕大多數）上那個字純粹是雜訊。多於一條時才講 —— 那時它是使用者
      真的需要的定位資訊。
    * **列幾個名字就夠。** `names` 是一串字，怎麼排版（引號、逗號、列到第幾個
      就說「還有 N 個」）是畫面的事 —— 走查看到的那一句把整條 route 的二十幾個
      feature 全列出來，一行變五行。CLI 那一份要全部（`detail` 裡就是全部），
      所以這是 `numbers.py` 那條界線的同一件事，不是兩套寫法。

    ⚠ **有結構的時候接的是 `advice` 不是 `detail`。** `detail` 是把同樣這些
    東西攤平成一句話的版本（給 CLI／檔案的讀者），接上去等於把剛剛拆開的
    東西再貼回去 —— 那一句會**同時**有「“nosuch_feature”」和
    「the variables nosuch_feature are not among…」。

    ⚠ 這一支**不改 `title`**：那一句是結論，而結論本來就該排在最前面（J6）。
    只有在 `detail` 是空的時候才拿 `title` 來頂 —— **這一支不准回空字串**：
    問題清單上一列空白比沒有那一列更糟（使用者看得到計數，卻讀不到內容）。
    """
    detail = (str(getattr(issue, "detail", "") or "").strip()
              or str(getattr(issue, "title", "") or "").strip())
    names = tuple(getattr(issue, "names", ()) or ())
    suggest = tuple(getattr(issue, "suggest", ()) or ())
    param = str(getattr(issue, "param", "") or "")
    route = str(getattr(issue, "route", "") or "")
    advice = str(getattr(issue, "advice", "") or "").strip()
    if not (names or suggest or param or advice):
        return detail                      # 還沒搬的那幾條：原樣

    bits = []
    nid = str(getattr(issue, "node_id", "") or "")
    where = card(model, nid) if (model is not None and nid) else ""
    if where and param:
        step = getattr((getattr(model, "nodes", None) or {}).get(nid, None),
                       "step", "")
        bits.append("“%s” › %s" % (where, field(step, param)))
    elif where:
        bits.append("“%s”" % where)
    if names:
        bits.append(name_list(names))
    if suggest:
        bits.append("did you mean %s?" % name_list(suggest, limit=3,
                                                   conj="or"))
    # **多於一條 route 才講** —— 而那件事只有畫面答得出來。
    if route and len(getattr(model, "routes", ()) or ()) > 1:
        bits.append("on %s" % route)
    line = " · ".join(b for b in bits if b)
    tail = advice or detail
    return "%s — %s" % (line, tail) if (line and tail) else (line or tail)


def trace_error_text(trace: Any, model: Any = None) -> str:
    """一筆 `StepTrace` → 一句話（``[glv_stats] …`` → ``“GLV”: …``）。

    ⚠ **這裡的 `error` 已經被壓成字串了**：`engine` 存的是 ``str(e)``，而
    `StepError.__str__` 會補上 ``[step_key] `` 前綴。`node_id` / `step_key`
    就在同一筆 trace 上，只是那句話已經不帶結構了（F118 §2 的「結構被字串
    吃掉」）。

    所以這一支**把那個前綴拿掉**，而它不是「對散文做正則」（F118 §3 明著
    否決的那條路）—— 前綴的內容是已知的（``"[%s] " % trace.step_key``），
    對得上才拿掉，對不上就原樣留著。

    ⚠ 那個前綴對**檔案**的讀者有用（CSV 的 `error` 欄讀得出是哪張卡），
    所以拿掉只發生在畫面這一側 —— 同 `numbers.py` 那條界線。
    """
    text = str(getattr(trace, "error", "") or "").strip()
    if not text:
        return ""
    key = str(getattr(trace, "step_key", "") or "")
    prefix = "[%s] " % key
    if key and text.startswith(prefix):
        text = text[len(prefix):]
    who = card(model, getattr(trace, "node_id", "")) if model is not None else ""
    if not who:
        who = card_of_step(key)
    return ("“%s”: %s" % (who, text)) if who else text


def step_error_text(err: Any, model: Any = None,
                    node_id: Optional[str] = None) -> str:
    """一個 :class:`~d4t.core.pipeline.step.StepError`（或任何例外）→ 一句話。

    ⚠ **`StepError` 本來就帶著結構**：`step_key` 與一份**不含** ``[key]`` 前綴
    的 `detail`，而它的說明從一開始就寫著「那句話是給使用者看的（推廣鐵則），
    不是給 log 看的」。畫面上那個 ``[glv_stats]`` 前綴是 `str(e)` 來的 ——
    **這一支要做的只是改用已經在那裡的東西**（F118 §2）。

    ``model`` ＋ ``node_id`` 給了就用**畫布上那張卡的名字**（同一張卡可以放
    兩次，node id 才分得出是哪一張）；只有例外就退回 step key 的 label。
    """
    detail = str(getattr(err, "detail", "") or "").strip()
    if not detail:                         # 不是 StepError：原樣（已經是人話）
        return str(err or "").strip()
    who = ""
    if model is not None and node_id:
        who = card(model, node_id)
    if not who:
        who = card_of_step(getattr(err, "step_key", ""))
    return ("“%s”: %s" % (who, detail)) if who else detail

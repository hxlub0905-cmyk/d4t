# d4t Studio — Preview 欄的特徵面板（F76 刀 4，2026-09-02）。
"""**一張平表裝不下一個立方體。**

使用者 2026-09-02：「目前 feature 顯示面板跟後面帶的數值我覺得好亂……我建議
大改版」。量出來的病（出貨的 `rsem-worst-box`，118 個特徵）：

* GLV 一張卡佔 **75 列**，而那 75 列是 **區域 × 統計量 × 身分** 的乘積 ——
  攤成長字串之後，每一串裡真正在變的只有最後一段；
* 兩個身分（``_typical`` / ``_worst``；``_outlier`` 那一族 2026-10-02 砍了）在畫面
  上**不相鄰**：`glv_q75_worst` 跟 `glv_q75_typical` 差 13 列，因為列序是
  ``features`` dict 的插入序 —— **排版跟著計算順序走，不是跟著意思走**；
* ``glv_worst_*`` 那 13 個是「這一區的結論」，卻跟量測值混在同一串列裡。

這一份怎麼解
------------
**橫過來。** 它們是同一個量的幾種身分，所以是**欄**不是列：

    統計量      這批典型     那一格      自己最極端
    Q75            189         191       191  = 同一格
    median         186         187       188  ← #46

19 列 → 1 個標題 + 2 列。而「自己最極端」那一欄**永遠帶著框號** —— 實測 24 顆：
judge 那個量 24/24 跟贏家同一格，其他量只有 2–5/24，而名字上沒有這個資訊
（使用者原話：「反而這樣會誤導別人以為他是最 worst 的」）。

⚠ **這一份沒有一行是 GLV 專屬的。** 欄數由 `FeatureSpec.variant` 決定，所以
CD 的 px↔nm 孿生自動就是兩欄，沒有 variant 的卡就是一欄（＝以前那張清單）。
真正屬於某一張卡的只有標題那一句話，而它走 `Step.panel_headline` 那個掛鉤 ——
同 `Step.overlay_marks`：**讀 features 的程式碼住在那張卡上，UI 只負責畫**。

分組不是這裡發明的
------------------
卡 → 區域 → 統計量那棵樹住在 `ui/feature_tree.py`（F76 刀 3 從 `results_table`
搬出來的），而每個名字的身分住在 `core/pipeline/verdict_features.bound_specs`。
Results 是 *N 顆 × M 特徵*，Preview 是 *一顆* —— **同一棵樹的轉置**。
兩棵樹一定會漂，而漂出來的第一個症狀就是 F76 刀 1 修的那個區域顏色 bug。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .buttons import clear_layout
from .numbers import format_feature_value
from .theme import TOKENS, region_hex
from .feature_text import VARIANT_COLUMNS as _VARIANT_COLUMNS
from .widgets import (
    FEATURE_RELATIVE, feature_gloss, feature_html, feature_unit, metric_face,
)

__all__ = ["FeaturePanel", "panel_model", "VARIANT_COLUMNS",
           "VARIANT_COLUMN_LABELS"]

#: 轉出口 —— **本體住 `ui/feature_text.py`**（F117 C2 搬的，說明也在那裡）。
#: 既有的 import 都指著這個名字，所以它留在這裡。
VARIANT_COLUMNS = _VARIANT_COLUMNS

#: 一列上那兩欄的最小寬度（F117 C1）。名字有寬度，值才對得齊；
#: 值有寬度，一欄數字才讀得成一欄。量的是最常見的那幾個名字
#: （`cmp_delta_median`、`glv_worst_baseline`）。
NAME_W = 150
VALUE_W = 72

#: 欄名（使用者 2026-09-02 在 mock 上定的字；改字只改這裡）。
#:
#: ``""`` 是「沒有變體」那一欄 —— 大部分卡片只有這一欄，而那時候整段就是
#: 以前那張 name/value 清單。
VARIANT_COLUMN_LABELS = {
    "": "value",
    "typical": "typical of them all",
    "worst": "the odd one out",
    "nm": "nm",
    "nm2": "nm²",
}


def _row_label(spec: Any) -> str:
    """一列的名字：統計量的短標籤（`metric_face` —— metric id 的天然落點）。"""
    if getattr(spec, "metric", ""):
        return metric_face(spec.metric)[1]
    return str(getattr(spec, "base", "") or getattr(spec, "name", ""))


def panel_model(features: Optional[Dict[str, Any]],
                bounds: Sequence[Any],
                highlight: Sequence[str] = (),
                about: Optional[Dict[str, str]] = None,
                diagnostics: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """**純函式** —— 一顆 defect 的特徵 → 面板要畫的那幾段。

    沒有 Qt，所以「畫成什麼樣」測得起來，不必開一個視窗（同
    `widgets.feature_html` / `why_panel.why_rows` 的立場）。

    一段 = **一張卡 × 一個區域**（`bounds` 已經是執行順序，同一段的相鄰）。
    每一段裡：

    * ``headline`` —— 那張卡自己說的一句結論（`Step.panel_headline`）；
    * ``grid`` —— 有 variant 的那些，一列一個統計量、一欄一個 variant；
    * ``flat`` —— 其餘（沒有 variant、也沒被標題吃掉的）照原順序。

    ``diagnostics`` 裡的名字歸到最後一段（``kind="diagnostics"``）——
    規矩跟結果表同一條：**判定引用 > 診斷隱藏**（被 `highlight` 點名的不藏）。
    """
    feats = dict(features or {})
    hi = set(highlight or ())
    drop = {d for d in map(str, diagnostics) if d not in hi}

    # ---- 先照「卡 × 區域」切段（bounds 已是執行順序）----------------------
    groups: List[Dict[str, Any]] = []
    for b in bounds or ():
        name = str(b.spec.name)
        if name not in feats:
            continue                       # 這一顆沒有寫出來（F19：算不出來的不寫）
        region = str(b.spec.region or "")
        if not (groups and groups[-1]["node_id"] == b.node_id
                and groups[-1]["region"] == region):
            groups.append({"node_id": str(b.node_id), "label": str(b.label),
                           "region": region,
                           "region_index": int(b.spec.region_index),
                           "specs": [], "diag": []})
        (groups[-1]["diag"] if name in drop
         else groups[-1]["specs"]).append(b.spec)

    out: List[Dict[str, Any]] = []
    diag_specs: List[Any] = []
    for g in groups:
        diag_specs.extend(g["diag"])
        if not g["specs"]:
            continue
        headline, eaten = _headline_of(g, feats)
        out.append({
            "node_id": g["node_id"], "label": g["label"],
            "region": g["region"], "region_index": g["region_index"],
            "kind": "card", "headline": headline,
            "grid": _grid_of(g["specs"], feats, hi, eaten),
            "flat": _flat_of(g["specs"], feats, hi, about, eaten),
            # **畫在標題行的那些也還在畫面上**，只是不佔一列 —— 所以取用口
            # 要查得到它們（`feature_names` / `value_text`）。少了這一份的
            # 下場實測過：`glv_worst_i` 明明就寫在標題上，`value_text` 卻回
            # None —— 取用口跟畫面說的是兩件事。
            "elsewhere": [{"name": n, "value": feats.get(n)}
                          for n in sorted(eaten) if n in feats],
        })
    if diag_specs:
        out.append({"node_id": "", "label": "Diagnostics", "region": "",
                    "region_index": -1, "kind": "diagnostics", "headline": [],
                    "grid": {"columns": [], "rows": []},
                    "flat": _flat_of(diag_specs, feats, hi, about, set())})

    # **沒人認領的仍然要出現**（F13-1 的老規矩，F76 刀 4 一度弄丟）。
    # 漏掉一個 = 那個數字從畫面上消失，而使用者不會知道它存在過 —— 而
    # `bound_specs` 漏宣告是會發生的（fixture 造的名字、宣告跟引擎漂開的那天）。
    # 這一段就是那件事的警報器：它一長出來，就代表有人的宣告不完整。
    claimed = {str(b.spec.name) for b in (bounds or ())}
    orphans = [n for n in feats if n not in claimed]
    if orphans:
        out.append({"node_id": "", "label": "Other", "region": "",
                    "region_index": -1, "kind": "other", "headline": [],
                    "grid": {"columns": [], "rows": []},
                    "flat": [{"name": n, "value": feats[n], "unit": "",
                              "gloss": "", "kind": "",
                              "verdict": n in hi} for n in orphans]})
    return out


def _headline_of(group: Dict[str, Any], feats: Dict[str, Any]):
    """問那張卡要一句結論，順便回「被它吃掉的名字」（那些不再佔一列）。"""
    from ..core.pipeline import get_step

    specs = list(group["specs"])
    try:
        card = get_step(_card_key(specs))
        parts = list(card.panel_headline(feats, specs))
    except Exception:  # 顯示用，不能擋畫面
        return [], set()
    if not parts:
        return [], set()
    # 標題吃掉的是**它真的用到的那幾個 metric**，而那件事由卡片自己講 ——
    # 這裡不猜：再問一次同一支，但只給它一個名字，看它還講不講得出話。
    eaten = set()
    for spec in specs:
        if not card.panel_headline(feats, [spec]):
            continue
        eaten.add(str(spec.name))
    # 座標那幾個沒進標題，但它們是給疊圖用的 —— 同一族一起收起來。
    for spec in specs:
        if str(spec.metric) in ("glv_worst_x", "glv_worst_y",
                                "glv_worst_w", "glv_worst_h"):
            eaten.add(str(spec.name))
    return parts, eaten


def _card_key(specs: Sequence[Any]) -> str:
    for s in specs:
        if getattr(s, "card", ""):
            return str(s.card)
    return ""


def _grid_of(specs: Sequence[Any], feats: Dict[str, Any],
             hi: set, eaten: set) -> Dict[str, Any]:
    """有 variant 的那些 → 一列一個統計量、一欄一個 variant。"""
    by_metric: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    seen_cols: List[str] = []
    for s in specs:
        var = str(getattr(s, "variant", "") or "")
        if var not in VARIANT_COLUMNS:
            continue
        if str(s.name) in eaten:
            continue
        mid = str(s.metric or s.base or s.name)
        if mid not in by_metric:
            by_metric[mid] = {"label": _row_label(s), "cells": {},
                              "unit": "", "verdict": False}
            order.append(mid)
        row = by_metric[mid]
        row["verdict"] = row["verdict"] or str(s.name) in hi
        if var not in seen_cols:
            seen_cols.append(var)
        row["cells"][var] = {"name": str(s.name),
                             "value": feats.get(str(s.name)),
                             # 格子上不畫這一句（欄名已經說了），但
                             # `about_text` 要答得出來 —— 它是懸停與測試的路。
                             "gloss": feature_gloss(str(s.name), None, s)[1]}
        row["unit"] = row["unit"] or feature_unit(s)
    columns = [c for c in VARIANT_COLUMNS if c in seen_cols]
    # 認不得的 variant（CD 的 nm 那種）接在後面 —— **照原順序**，不排序。
    columns += [c for c in seen_cols if c not in columns]
    return {"columns": columns, "rows": [by_metric[mid] for mid in order]}


def _flat_of(specs: Sequence[Any], feats: Dict[str, Any], hi: set,
             about: Optional[Dict[str, str]], eaten: set) -> List[Dict[str, Any]]:
    """沒有 variant（也沒被標題吃掉）的那些 —— 就是以前那張 name/value 清單。"""
    out = []
    for s in specs:
        name = str(s.name)
        if name in eaten:
            continue
        if str(getattr(s, "variant", "") or "") in VARIANT_COLUMNS:
            continue
        out.append({"name": name, "value": feats.get(name),
                    "html": feature_html(name, s.parts()),
                    "unit": feature_unit(s),
                    "gloss": feature_gloss(name, about, s)[1],
                    "kind": feature_gloss(name, about, s)[0],
                    "verdict": name in hi})
    return out


# --------------------------------------------------------------------------- #
# Widget
# --------------------------------------------------------------------------- #
class FeaturePanel(QScrollArea):
    """一顆 defect 的特徵，卡 › 區域 分段，四胞胎橫過來。

    對外的取用口跟被它取代的 `widgets.FeatureTable` 同名同義
    （`feature_names` / `value_text` / `about_text` / `section_titles`），
    所以既有的呼叫端與測試不必改一個字。
    """

    feature_clicked = Signal(str)
    #: 滑鼠進到某一段（＝某一張卡的那幾個數字）—— 送出那張卡的 node id；
    #: 離開送空字串（F117 I6）。
    #:
    #: **為什麼是「一段」而不是「一列」**：一段就是一張卡，而一列屬於它所在的
    #: 那一段 —— 滑過任何一列都會經過這一段。逐列發訊號的話，同一張卡在使用者
    #: 的手往下移的路上會被指十幾次，而畫布那邊每一次都要清掉再亮一次。
    card_hovered = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        host = QWidget(self)
        self._lay = QVBoxLayout(host)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)
        self.setWidget(host)
        self._host = host
        self._model: List[Dict[str, Any]] = []
        self._values: Dict[str, Any] = {}
        self._glosses: Dict[str, str] = {}
        self._collapsed: Dict[str, bool] = {}
        self._search = ""

    # ---- 填 ---------------------------------------------------------------
    def set_model(self, model: Sequence[Dict[str, Any]]) -> None:
        """吃 :func:`panel_model` 的輸出（**這個 widget 不去問引擎**）。"""
        self._model = [dict(s) for s in (model or [])]
        self._values, self._glosses = {}, {}
        for sec in self._model:
            for row in sec["flat"]:
                self._values[row["name"]] = row["value"]
                self._glosses[row["name"]] = row["gloss"]
            for row in sec["grid"]["rows"]:
                for cell in row["cells"].values():
                    self._values[cell["name"]] = cell["value"]
                    self._glosses[cell["name"]] = cell.get("gloss", "")
            # 標題行上的那幾個（`glv_worst_i` / `locate_ok` / …）。
            for got in sec.get("elsewhere") or ():
                self._values[got["name"]] = got["value"]
        self._rebuild()

    def eventFilter(self, obj, event):  # Qt hook
        """段落進出 → :attr:`card_hovered`（F117 I6）。

        ⚠ **離開時送空字串，不是不送。** 畫布那邊要有一個「熄掉」的訊號 ——
        不送的話，滑鼠移出面板之後那張卡會一直亮著，而使用者早就不在看它了。
        """
        kind = event.type()
        if kind in (QEvent.Enter, QEvent.Leave):
            nid = str(obj.property("d4tNode") or "")
            if nid:
                self.card_hovered.emit(nid if kind == QEvent.Enter else "")
        return super().eventFilter(obj, event)

    def set_search(self, text: str) -> None:
        self._search = str(text or "").strip().lower()
        self._rebuild()

    # ---- 取用口（跟 FeatureTable 同名同義）--------------------------------
    def feature_names(self) -> List[str]:
        return list(self._values)

    def value_text(self, name: str) -> Optional[str]:
        if str(name) not in self._values:
            return None
        return format_feature_value(self._values[str(name)])

    def about_text(self, name: str) -> Optional[str]:
        return self._glosses.get(str(name))

    def section_titles(self) -> List[str]:
        return [_title_of(sec) for sec in self._model]

    def is_section_collapsed(self, title: str) -> bool:
        return bool(self._collapsed.get(str(title)))

    def toggle_section(self, title: str) -> None:
        key = str(title)
        self._collapsed[key] = not self._collapsed.get(key, False)
        self._rebuild()

    # ---- 畫 ---------------------------------------------------------------
    def _rebuild(self) -> None:
        clear_layout(self._lay)
        for sec in self._model:
            if not self._matches(sec):
                continue
            self._lay.addWidget(self._section_widget(sec))
        self._lay.addStretch(1)

    def _matches(self, sec: Dict[str, Any]) -> bool:
        if not self._search:
            return True
        hay = [_title_of(sec)]
        hay += [r["name"] for r in sec["flat"]]
        hay += [c["name"] for r in sec["grid"]["rows"]
                for c in r["cells"].values()]
        return any(self._search in str(h).lower() for h in hay)

    def _section_widget(self, sec: Dict[str, Any]) -> QWidget:
        box = QFrame(self._host)
        box.setObjectName("featureSection")
        # **滑過這一段＝在畫布上指出那張卡**（F117 I6）。
        #
        # ⚠ 用 `enterEvent`／`leaveEvent` 而不是追滑鼠座標：`QFrame` 本來就
        # 收得到這兩個事件，而它們**進出各一次** —— 追座標要自己去分辨「還在
        # 同一段裡」，那是把 Qt 已經算好的事再算一遍。
        nid = str(sec.get("node_id") or "")
        if nid:
            box.setAttribute(Qt.WA_Hover, True)
            box.installEventFilter(self)
            box.setProperty("d4tNode", nid)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        title = _title_of(sec)
        collapsed = bool(self._collapsed.get(title))
        head = QPushButton("%s %s" % ("▸" if collapsed else "▾", title), box)
        head.setObjectName("featureSectionHead")
        head.setCursor(Qt.PointingHandCursor)
        head.setFlat(True)
        head.setStyleSheet(_head_style(sec))
        head.clicked.connect(lambda _c=False, t=title: self.toggle_section(t))
        lay.addWidget(head)

        if sec["headline"]:
            lay.addWidget(_headline_widget(sec["headline"], box))
        if collapsed:
            return box
        if sec["grid"]["rows"]:
            lay.addWidget(_grid_widget(sec["grid"], box))
        for row in sec["flat"]:
            lay.addWidget(_flat_widget(row, box))
        return box


def _title_of(sec: Dict[str, Any]) -> str:
    return ("%s › %s" % (sec["label"], sec["region"])) if sec["region"] \
        else str(sec["label"])


def _head_style(sec: Dict[str, Any]) -> str:
    colour = (region_hex(int(sec["region_index"]))
              if int(sec["region_index"]) >= 0 else TOKENS["text_secondary"])
    return ("text-align:left; padding:4px 8px; font-weight:600;"
            "border-left:3px solid %s; color:%s;"
            % (colour, TOKENS["text_primary"]))


def _headline_widget(parts: Sequence[Any], parent: QWidget) -> QWidget:
    """標題那一行：``odd one out #21 · 1.35 σ · 100 boxes``。"""
    host = QWidget(parent)
    lay = QHBoxLayout(host)
    lay.setContentsMargins(14, 1, 8, 3)
    lay.setSpacing(6)
    for i, (label, value, unit) in enumerate(parts):
        if i:
            dot = QLabel("·", host)
            dot.setStyleSheet("color:%s;" % TOKENS["text_hint"])
            lay.addWidget(dot)
        if label:
            lab = QLabel(str(label), host)
            lab.setObjectName("paramHint")
            lay.addWidget(lab)
        text = value if isinstance(value, str) else format_feature_value(value)
        val = QLabel(text + ((" " + unit) if unit else ""), host)
        val.setStyleSheet("font-weight:600; color:%s;" % TOKENS["text_primary"])
        lay.addWidget(val)
    lay.addStretch(1)
    return host


def _grid_widget(grid: Dict[str, Any], parent: QWidget) -> QWidget:
    host = QWidget(parent)
    lay = QGridLayout(host)
    lay.setContentsMargins(14, 2, 8, 4)
    lay.setHorizontalSpacing(12)
    lay.setVerticalSpacing(2)
    columns = list(grid["columns"])
    for c, var in enumerate(columns):
        head = QLabel(VARIANT_COLUMN_LABELS.get(var, var), host)
        head.setObjectName("paramHint")
        head.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(head, 0, c + 1)
    for r, row in enumerate(grid["rows"], start=1):
        name = QLabel(str(row["label"]), host)
        if row["verdict"]:
            name.setStyleSheet("color:%s; font-weight:600;"
                               % TOKENS["accent_active"])
        lay.addWidget(name, r, 0)
        for c, var in enumerate(columns):
            cell = row["cells"].get(var)
            text = "" if cell is None else format_feature_value(cell["value"])
            item = QLabel(text, host)
            item.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item.setStyleSheet("font-family:monospace;")
            lay.addWidget(item, r, c + 1)
        unit = QLabel(str(row["unit"] or ""), host)
        unit.setObjectName("paramHint")
        lay.addWidget(unit, r, len(columns) + 1)
    lay.setColumnStretch(len(columns) + 2, 1)
    return host


def _flat_widget(row: Dict[str, Any], parent: QWidget) -> QWidget:
    host = QWidget(parent)
    lay = QHBoxLayout(host)
    lay.setContentsMargins(14, 0, 8, 0)
    lay.setSpacing(8)
    # **名字用上下標畫**（F37 A4：區域是上標＋區域色、影像流是下標）——
    # 那件事以前住在 `FeatureTable` 的 delegate 上，而 QLabel 本來就吃 rich
    # text，所以搬過來只要換一個 setText。純文字仍然是 `row["name"]`，
    # `feature_names()` / `value_text()` 讀到的都還是那一串打得進分數表達式的字。
    name = QLabel(host)
    name.setTextFormat(Qt.RichText)
    name.setText(row.get("html") or str(row["name"]))
    name.setStyleSheet(
        "font-family:monospace;%s"
        % (" color:%s; font-weight:600;" % TOKENS["accent_active"]
           if row["verdict"] else ""))
    name.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    # ⚠ **名字有一個最小寬度，值才排得成一欄**（F117 C1）。沒有它的話每一列
    # 的值都黏在自己名字後面，長短不一。⚠ 它是**最小**不是固定：比 `NAME_W`
    # 長的名字（`glv_worst_baseline`）照樣把自己那一列的值往右推 —— 截名字
    # 比讓值跳更糟，而名字是使用者要打進分數表達式的字。
    name.setMinimumWidth(NAME_W)
    lay.addWidget(name)
    # ⚠ **值排在名字旁邊，不排在最右邊**（F117 C1）。以前說明那一欄是
    # `Expanding` 的，它把值與單位一路推到可視範圍外 —— 面板預設寬度要橫捲
    # 約 270 px 才看得到數字，而**數字正是這個面板存在的理由**。說明改成收在
    # 後面：它是查閱用的（同設定區那條「說明不佔版面」的決定）。
    value = QLabel(format_feature_value(row["value"]), host)
    value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    value.setStyleSheet("font-family:monospace;")
    value.setMinimumWidth(VALUE_W)
    lay.addWidget(value)
    unit = QLabel(str(row["unit"] or ""), host)
    unit.setObjectName("paramHint")
    unit.setMinimumWidth(34)
    lay.addWidget(unit)
    gloss = QLabel(str(row["gloss"] or ""), host)
    gloss.setObjectName("paramHint")
    gloss.setToolTip(str(row["gloss"] or ""))     # 擠掉的那幾個字讀得回來
    # **絕對量與相對量用顏色分**（F18 補課第三輪，使用者：「絕對量的跟相對量的
    # 還是要分類好，不然不清楚命名規則會很痛苦」）：相對量走強調色。文字本身
    # 也講得出來（`… vs mg`），所以不是只靠顏色。
    if row.get("kind") == FEATURE_RELATIVE:
        gloss.setStyleSheet("color:%s;" % TOKENS["accent_active"])
    # ⚠ **最小寬度 0**：說明不准把面板撐寬。窄的時候它先被擠掉，而名字與值
    # 還在 —— 那個取捨的方向就是 C1 記的那件事。
    gloss.setMinimumWidth(0)
    gloss.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
    lay.addWidget(gloss, 1)
    return host

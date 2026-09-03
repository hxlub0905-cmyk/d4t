# d4t Studio — 逐顆的表（R7，2026-08-24）。
"""**200 顆的時候，一牆縮圖掃不動。**

使用者：「目前的 results panel 太簡略了」。縮圖回答的是「這一顆長什麼樣」，
而跑完一整批之後有一整類問題它答不出來：

* 照 ``cd_median`` 排一下，把 ``glv_mad`` 那一欄跟類別對照著看；
* 哪幾顆算不出來、**為什麼**（引擎每一顆都留了訊息 —— 鐵則 7：單顆出錯不殺
  整批，回 ``ok=False`` 並帶原因）；
* 把一顆的每一個數字一次看完，而不是點進去看儀表。

CLI 的 ``--csv`` 早就吐得出這張表了。這一份是把它搬到畫面上。

欄位跟 CSV 同一份
-----------------
``defect_id · ok · error · score · bin`` 來自 `report.BASE_COLUMNS`，
特徵欄來自 `report.feature_keys` —— **同一支函式**，不是抄第二份
（抄第二份的那一份會漂，而漂掉的時候「畫面上的表」與「匯出的檔案」
會是兩個不同的東西）。

⚠ 多一欄 ``class``，而 CSV 沒有：那是使用者在樹上取的名字，加進 CSV 會動到
檔案格式（黃金值、下游腳本）。這裡加得起來是因為它只影響畫面。

⚠ **只有 ``bin`` 那一欄改得動，而且只改在畫面上**（F48，2026-08-28）。
F27 §5 把「看到判錯的那一顆就地改掉」列為待定調，理由是那會讓這一頁從
「看結果」變成「編結果」；使用者 2026-08-28 定調「**只在畫面上，標成手動
改過**」——所以兩件事仍然是兩件事，改的那個值一個位元組都不會流出這張表：

* 它住在 model 自己那份 row 副本的 ``bin_override`` 鍵上（`set_results` 收到
  的 dict 是 `dict(r)` 淺拷貝，原本那份 result 不會被動到）；
* CSV、KLARF、SQLite 全部走 `core.export` 讀原本的 result —— 那條路看不到
  這個鍵。`tests/test_ui_results_bin_override.py` 拿匯出的位元組守著；
* **再跑一批就沒了**（`set_results` 重建 rows）。那是刻意的：那些記號講的是
  上一批的數字，留到下一批會變成一句沒有主詞的話。

改的方式有兩條（都不動既有的滑鼠手勢 —— 單擊 ``bin`` 仍然是問「為什麼」、
雙擊仍然是去看那一顆）：選起來按 ``F2``／``Enter``，或右鍵選 “Set bin…”。

為什麼是 `QTableView` 而不是 `QTableWidget`
--------------------------------------------
一顆 defect 一列、一個特徵一欄，而一批可以是幾千顆 —— `QTableWidget` 會替
每一格生一個 item 物件。model/view 只算看得到的那幾列。

兩層欄位（PR-1，2026-08-27）
----------------------------
五六十欄平鋪找不到重點，所以欄位分兩層，**分層是自動的**（由 recipe 推導，
`core/pipeline/verdict_features.py` 是唯一出處；沒有手動挑欄的設定頁）：

* **判定層**（預設可見）＝徽章欄 ＋ base ＋ class ＋ 判定引用的特徵
  （照引用順序；引用了沒人產出的名字 → 一個看得到的空欄，比默默消失好）。
* **其餘**照產出卡分組排在後面，「All measurements (N)」一顆鈕整批展開；
  欄位搜尋框用子字串把摺疊的欄叫出來。展開狀態是 session 級（純 attr）。
* **診斷欄**（卡片宣告的，`diagnostic_features`）兩層都不出現 —— 除非判定
  引用了它（使用者 2026-08-27 定調：判定引用 > 診斷隱藏）。值沒有不見：
  每列一個警示徽章，點/懸停看明細；匯出照舊含診斷欄（匯出不走這個模組）。
* 警示**只**來自卡片宣告的布林（`diagnostic_alarms`）與整列的 ``error`` ——
  UI 不對數值型診斷發明門檻。

卡 → 區域 → 統計量（PR-3，2026-08-27）
--------------------------------------
分組吃的是 `verdict_features.bound_specs`（每個特徵名的**結構化身分**，
`FeatureSpec` 在名字誕生的地方組出來）——**不拆特徵字串猜語意**：

* :func:`column_tree` 把欄位排成卡 → 區域 → 統計量的樹，**只算一次**，
  摺疊順序、雙層表頭、維度過濾共用同一份（表頭不自己推＝不留第二套）；
* 表頭兩層：上半是**區域**（同一張卡同一個區域的欄相鄰，跨欄一次、
  用疊框同一組顏色 `theme.region_hex`），下半是**統計量**的短標籤
  （`widgets.metric_face` —— metric id 的天然落點）。懸停看得到原始欄名 ——
  字串仍是分數表達式的變數名，永不改；
* 維度過濾（Region / Statistic / Card 三顆下拉 + chips）：chip **限縮**
  兩層（固定欄與命中欄留下；同維 OR、跨維 AND），欄位搜尋照舊是**現身**
  （子字串把摺疊的欄叫出來，搜尋命中 > 維度限縮 —— 指名要看的贏過大範圍
  的篩子）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QRect, QSize, Qt, Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QInputDialog, QLineEdit,
    QMenu, QSpinBox, QStyledItemDelegate, QTableView, QToolButton, QToolTip,
    QVBoxLayout, QWidget,
)

from .numbers import format_feature_value
from .theme import TOKENS, region_hex
from .widgets import FilterChip, metric_face

__all__ = [
    "ResultsTable", "ResultsTableModel", "ResultsTablePane", "TwoLevelHeader",
    "table_columns", "column_tree", "visible_columns", "row_warnings",
    "header_spans",
]

# ⚠ **這一段 2026-09-02 搬到 `feature_tree.py`**（F76 刀 3）：Preview 欄的新
# 面板要吃同一棵樹，而同一件事兩份說法一定會漂 —— 區域顏色那個 bug 就是漂
# 出來的第一個症狀。這裡留的是取用口，行為一個位元組都沒有變。
from .feature_tree import (            # noqa: E402 — 位置沿用被搬走那一段
    BADGE_COLUMN, CLASS_COLUMN, column_tree, fixed_columns, stat_label,
)

#: 手動改過的 bin 住在 row 副本的這個鍵上（F48）。**不是 result 的欄位** ——
#: 引擎判的那個值仍然原封不動留在 ``bin``，兩個都要留得住才講得出「從 5 改成 3」。
OVERRIDE_KEY = "bin_override"

_fixed_columns = fixed_columns
_stat_label = stat_label



def table_columns(results: Sequence[Dict[str, Any]],
                  verdict_features: Sequence[str] = (),
                  specs: Sequence[Any] = (),
                  diagnostics: Sequence[str] = ()) -> List[str]:
    """這張表有哪幾欄（順序就是顯示順序）。

    不帶引數＝以前的平鋪行為（base + class + 特徵照字母序）加上徽章欄。
    診斷欄（沒被判定引用的）**完全不在**回傳裡 —— 值走徽章明細與匯出，
    不走表格。
    """
    return list(column_tree(results, verdict_features, specs,
                            diagnostics)["columns"])


def _stat_menu_text(metric_id: str) -> str:
    """Statistic 下拉／chip 上的字：``分群 · 短標籤``。只給短標籤的話
    GLV 的 Median 與 CD 的 Median 在選單裡是兩條一模一樣的字。"""
    group, label, _glyph = metric_face(metric_id)
    return "%s · %s" % (group, label)


def _dim_value(bound: Any, kind: str) -> str:
    """一欄在某個維度上的值。``region`` 是區域名前綴（含 ``_center`` 那種
    後綴全名）、``stat`` 是 metric id、``card`` 是（消歧後的）卡片 label。"""
    if kind == "region":
        return str(bound.spec.region)
    if kind == "stat":
        return str(bound.spec.metric)
    return str(bound.label)


def visible_columns(columns: Sequence[str], verdict_columns: Sequence[str],
                    expanded: bool, search: str,
                    spec_of: Optional[Dict[str, Any]] = None,
                    dims: Sequence[Tuple[str, str]] = ()) -> List[str]:
    """現在看得到哪幾欄 —— 分層的**全部**邏輯，純函式（不變量測試打這裡）。

    展開＝全部；收合＝判定層 ∪ 搜尋命中的欄（子字串、不分大小寫）。
    清空搜尋就還原 —— 搜尋不改展開狀態。

    ``dims``（PR-3 的維度 chips，``[(維度, 值), …]``，維度 ∈ region / stat
    / card）是**限縮**：兩層都只留固定欄（沒有 spec 的）與命中欄 —— 同維
    OR、跨維 AND。搜尋命中的欄**不受限縮**（指名要看的贏過大範圍的篩子）。
    不給 ``dims`` / ``spec_of`` ＝ PR-1 的行為逐字不變。
    """
    keep = set(verdict_columns)
    s = str(search or "").strip().lower()

    def layer_ok(c: str) -> bool:
        return expanded or c in keep or bool(s and s in c.lower())

    wanted: Dict[str, set] = {}
    for kind, value in dims or ():
        wanted.setdefault(str(kind), set()).add(str(value))

    def dim_ok(c: str) -> bool:
        if not wanted or not spec_of:
            return True
        b = spec_of.get(c)
        if b is None:
            return True                       # 固定欄／沒人產出的判定欄
        if s and s in c.lower():
            return True                       # 搜尋命中 > 維度限縮
        return all(_dim_value(b, kind) in values
                   for kind, values in wanted.items())

    return [c for c in columns if layer_ok(c) and dim_ok(c)]


def header_spans(visible: Sequence[str],
                 spec_of: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """上層表頭的跨欄段：可見欄序列 → ``[{start, count, region,
    region_index, node_id}, …]``（start 是可見序的索引）。

    同一張卡（node_id）同一個區域的**連續**欄合成一段；沒有區域的欄不成段。
    畫的跟測的都走這一支 —— 表頭不自己推一份。
    """
    spans: List[Dict[str, Any]] = []
    prev = None
    for i, name in enumerate(visible):
        b = (spec_of or {}).get(str(name))
        region = str(b.spec.region) if b is not None else ""
        key = (b.node_id, region) if (b is not None and region) else None
        if key is not None and key == prev:
            spans[-1]["count"] += 1
        elif key is not None:
            spans.append({"start": i, "count": 1, "region": region,
                          "region_index": int(b.spec.region_index),
                          "node_id": str(b.node_id)})
        prev = key
    return spans


def row_warnings(row: Dict[str, Any],
                 alarms: Optional[Dict[str, bool]]) -> List[Tuple[str, Any]]:
    """這一列要不要亮徽章 —— **只有**這兩種情況，別的一律不亮：

    * ``error`` 非空（鐵則 7 留下來的那句話）；
    * 卡片宣告的布林診斷（`diagnostic_alarms`）落在它宣告的壞值上。

    數值型診斷（``glv_sat_frac`` 那類）不在 ``alarms`` 表上，所以想亮也
    沒有依據 —— 「UI 不發明門檻」是結構保證，不是自律。
    """
    out: List[Tuple[str, Any]] = []
    err = row.get("error")
    if err:
        out.append(("error", str(err)))
    feats = row.get("features") or {}
    for name, bad in (alarms or {}).items():
        value = feats.get(name)
        if value is not None and bool(value) == bool(bad):
            out.append((name, value))
    return out


def _cell(row: Dict[str, Any], column: str) -> Any:
    if column == BADGE_COLUMN:
        return None
    if column == CLASS_COLUMN:
        return str(row.get("cls") or "")
    if column == "error":
        return "" if row.get("error") is None else str(row.get("error"))
    if column == "bin":
        # 手動改過的話**排序也要跟著它走** —— `sort` 跟 `data` 都走這一支，
        # 所以「畫面上寫 3」與「排在 3 那一群」不可能各說各話。
        return row.get(OVERRIDE_KEY, row.get("bin"))
    if column in ("defect_id", "score", "ok"):
        return row.get(column)
    return (row.get("features") or {}).get(column)


class ResultsTableModel(QAbstractTableModel):
    """一顆 defect 一列。排序自己做（不套 proxy —— 幾千列時少一層複製）。"""

    def __init__(self, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self._rows: List[Dict[str, Any]] = []
        self._columns: List[str] = []
        self._verdict_columns: List[str] = []
        self._diagnostics: List[str] = []
        self._alarms: Dict[str, bool] = {}
        self._spec_of: Dict[str, Any] = {}

    # ---- 資料 --------------------------------------------------------------
    def set_results(self, results: Sequence[Dict[str, Any]],
                    class_names: Optional[Dict[str, str]] = None,
                    layout: Optional[Dict[str, Any]] = None,
                    alarms: Optional[Dict[str, bool]] = None) -> None:
        """``layout`` 來自 :func:`column_tree`；不給＝平鋪（每一欄都是判定層，
        沒有摺疊區）。``alarms`` 來自 `verdict_features.diagnostic_alarm_map`。"""
        names = dict(class_names or {})
        self.beginResetModel()
        if layout is None:
            self._columns = table_columns(results)
            self._verdict_columns = list(self._columns)
            self._diagnostics = []
            self._spec_of = {}
        else:
            self._columns = list(layout.get("columns") or [])
            self._verdict_columns = list(layout.get("verdict_columns") or [])
            self._diagnostics = list(layout.get("diagnostics") or [])
            self._spec_of = dict(layout.get("spec_of") or {})
        self._alarms = dict(alarms or {})
        self._rows = []
        for r in results or []:
            row = dict(r)
            row["cls"] = names.get(str(r.get("defect_id", "")), "")
            self._rows.append(row)
        self.endResetModel()

    def columns(self) -> List[str]:
        return list(self._columns)

    def verdict_columns(self) -> List[str]:
        return list(self._verdict_columns)

    def n_more(self) -> int:
        """摺疊區有幾欄（「All measurements (N)」的那個 N）。"""
        return len(self._columns) - len(self._verdict_columns)

    def warnings_at(self, row: int) -> List[Tuple[str, Any]]:
        if not (0 <= row < len(self._rows)):
            return []
        return row_warnings(self._rows[row], self._alarms)

    def diagnostic_details(self, row: int) -> List[Tuple[str, Any, str]]:
        """這一顆的診斷明細：(名字, 值, 來自哪張卡) —— 徽章的懸停/點擊畫這個。

        歸戶走該列的 ``traces[].features_added``（**引擎在跑的當下記的**，
        不是 UI 猜的 —— inspectors 檔頭第 2 條）；歸不到的卡名留空。
        """
        if not (0 <= row < len(self._rows)):
            return []
        r = self._rows[row]
        feats = r.get("features") or {}
        producer: Dict[str, str] = {}
        for t in r.get("traces") or []:
            who = str(t.get("node_id") or t.get("step_key") or "")
            for name in t.get("features_added") or []:
                producer.setdefault(str(name), who)
        return [(n, feats[n], producer.get(n, ""))
                for n in self._diagnostics if n in feats]

    def _badge_tip(self, row: int, warns: List[Tuple[str, Any]]) -> str:
        """徽章的懸停文字：先講為什麼亮，再列這一顆的全部診斷明細。"""
        fmt = format_feature_value

        lines = ["%s = %s" % (n, fmt(v)) for n, v in warns]
        flagged = {n for n, _ in warns}
        rest = ["%s = %s%s" % (n, fmt(v), " · %s" % who if who else "")
                for n, v, who in self.diagnostic_details(row)
                if n not in flagged]
        if rest:
            lines.append("")
            lines.extend(rest)
        return "\n".join(lines)

    def defect_id_at(self, row: int) -> str:
        if 0 <= row < len(self._rows):
            return str(self._rows[row].get("defect_id", ""))
        return ""

    def row_of(self, defect_id: str) -> int:
        want = str(defect_id)
        for i, r in enumerate(self._rows):
            if str(r.get("defect_id", "")) == want:
                return i
        return -1

    # ---- QAbstractTableModel ----------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:      # noqa: N802 — Qt
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:   # noqa: N802 — Qt
        return 0 if parent.isValid() else len(self._columns)

    def spec_of(self) -> Dict[str, Any]:
        """欄名 → BoundSpec（`TwoLevelHeader` 的跨欄段吃這個）。"""
        return self._spec_of

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if orientation != Qt.Horizontal or \
                not (0 <= section < len(self._columns)):
            return None
        name = self._columns[section]
        bound = self._spec_of.get(name)
        if role == Qt.DisplayRole:
            # 徽章欄的表頭留白 —— ``!warn`` 是程式的哨兵，不是給人看的字。
            if name == BADGE_COLUMN:
                return ""
            # 有身分的欄顯示統計量短標籤（區域在上層表頭）；沒有的照舊
            # 顯示欄名 —— 不猜。
            return _stat_label(bound) if bound is not None else name
        if role == Qt.ToolTipRole and bound is not None:
            # 第一行**永遠是原始欄名** —— 它是分數表達式的變數名、CSV 的
            # 欄名，短標籤再漂亮也不能把它藏死。
            bits = [x for x in (bound.label, bound.spec.region,
                                _stat_label(bound)) if x]
            return "%s\n%s" % (name, " · ".join(bits))
        return None

    def data(self, index, role=Qt.DisplayRole):           # noqa: N802 — Qt
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = self._columns[index.column()]
        if column == BADGE_COLUMN:
            warns = row_warnings(row, self._alarms)
            if role == Qt.DisplayRole:
                return "⚠" if warns else ""
            if role == Qt.EditRole:
                return bool(warns)             # 排序把有警示的聚在一起
            if role == Qt.ToolTipRole and warns:
                return self._badge_tip(index.row(), warns)
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            if role == Qt.ForegroundRole and not row.get("ok", True):
                return QColor(TOKENS.get("danger_text", "#a83f33"))
            return None
        value = _cell(row, column)

        if column == "bin" and OVERRIDE_KEY in row:
            was = row.get("bin")
            if role == Qt.DisplayRole:
                # **兩個數字都寫在格子裡。** 只顯示新的值再配一個記號的話，
                # 使用者要把滑鼠停上去才知道原本是幾 —— 而「引擎判 5，我說是
                # 3」正是這一欄現在在講的整句話。沒有原值時（那一顆engine
                # 根本沒判出來）寫 manual，不要寫一個假的 was。
                return ("%d (was %d)" % (int(value), int(was))
                        if isinstance(was, int) else "%d (manual)" % int(value))
            if role == Qt.ToolTipRole:
                return ("Bin changed by hand on this screen.\n"
                        "The engine says %s. Exports (CSV, KLARF, the run "
                        "database) still get the engine's value — this mark "
                        "is a note for you, and a new run clears it."
                        % ("bin %d" % int(was) if isinstance(was, int)
                           else "it could not bin this defect"))
            if role == Qt.ForegroundRole:
                return QColor(TOKENS.get("accent", "#2f6fb2"))

        if role == Qt.DisplayRole:
            # ⚠ **算不出來的那一格留白，不是 0、也不是 NaN**（F19 那一條）——
            # `format_feature_value(None)` 就是空字串。
            return format_feature_value(value)
        if role == Qt.EditRole:
            return value                       # 排序吃這個（保留原型別）
        if role == Qt.TextAlignmentRole:
            return (int(Qt.AlignRight | Qt.AlignVCenter)
                    if isinstance(value, (int, float)) and column != "defect_id"
                    else int(Qt.AlignLeft | Qt.AlignVCenter))
        if role == Qt.ForegroundRole and not row.get("ok", True):
            # 失敗的那一列整列是紅的 —— 它是使用者最需要先挑出來的那幾顆，
            # 而只有 error 那一欄變色的話，一張幾百列的表上找不到它。
            return QColor(TOKENS.get("danger_text", "#a83f33"))
        if role == Qt.ToolTipRole and column == "error" and value:
            return str(value)
        return None

    def flags(self, index):                               # noqa: N802 — Qt
        base = super().flags(index)
        if index.isValid() and self._columns[index.column()] == "bin":
            return base | Qt.ItemIsEditable
        return base

    def setData(self, index, value, role=Qt.EditRole) -> bool:  # noqa: N802
        """``bin`` 那一欄改得動 —— **只改這份 row 副本**（F48）。

        改回引擎判的那個值＝把記號拿掉（不是再蓋一層「手動改成跟原本一樣」）：
        使用者要反悔的時候，唯一想得到的動作就是把原本那個數字打回去。
        """
        if role != Qt.EditRole or not index.isValid():
            return False
        if self._columns[index.column()] != "bin":
            return False
        row = self._rows[index.row()]
        try:
            new = int(value)
        except (TypeError, ValueError):
            return False
        if new == row.get("bin"):
            row.pop(OVERRIDE_KEY, None)
        else:
            row[OVERRIDE_KEY] = new
        self.dataChanged.emit(index, index)
        return True

    def bin_overrides(self) -> Dict[str, int]:
        """``defect_id`` → 手動改成的 bin（沒改過的不在裡面）。"""
        return {str(r.get("defect_id", "")): int(r[OVERRIDE_KEY])
                for r in self._rows if OVERRIDE_KEY in r}

    def clear_bin_overrides(self) -> int:
        """把所有手動記號拿掉，回傳拿掉幾個。"""
        n = 0
        for i, r in enumerate(self._rows):
            if r.pop(OVERRIDE_KEY, None) is not None:
                n += 1
                if "bin" in self._columns:
                    idx = self.index(i, self._columns.index("bin"))
                    self.dataChanged.emit(idx, idx)
        return n

    def sort(self, column: int, order=Qt.AscendingOrder) -> None:  # noqa: N802
        """``None`` 一律排到最後（不管升冪降冪）—— 跟 Gallery 同一條規矩。

        「沒量到」不是一個小的值，把它排在最前面會讓一張照數字排的表最上面
        全部是空白格。
        """
        if not (0 <= column < len(self._columns)):
            return
        name = self._columns[column]
        rev = order == Qt.DescendingOrder

        def key(row: Dict[str, Any]):
            v = _cell(row, name)
            if v is None or v == "":
                return (1, 0.0, "")
            if isinstance(v, bool):
                return (0, float(v), "")
            if isinstance(v, (int, float)):
                return (0, float(v), "")
            return (0, 0.0, str(v))

        self.layoutAboutToBeChanged.emit()
        self._rows.sort(key=key, reverse=rev)
        # 空值那一組要留在最後，所以反轉之後把它們撈回來。
        if rev:
            missing = [r for r in self._rows if key(r)[0] == 1]
            if missing:
                self._rows = ([r for r in self._rows if key(r)[0] == 0]
                              + missing)
        self.layoutChanged.emit()


class TwoLevelHeader(QHeaderView):
    """雙層表頭：上半是**區域**（同卡同區域的欄跨欄一次、顏色跟影像上的
    疊框同源 `theme.region_hex`），下半是 Qt 原生畫的節區（統計量短標籤
    來自 model 的 DisplayRole，排序箭頭是預設行為）。

    沒有任何欄帶區域時退回**單層** —— 平鋪與舊 recipe 的表一個像素都不變。
    上半的點擊不特殊處理（預設 QHeaderView 行為＝排序該欄 —— 上下兩半是
    同一個節區）。跨欄段由 :func:`header_spans`（純函式）算 —— 畫的跟測的
    是同一份，表頭不自己推第二套。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(Qt.Horizontal, parent)

    # ---- 資料（都來自 model —— 表頭自己不存一份） --------------------------
    def _spec_of(self) -> Dict[str, Any]:
        get = getattr(self.model(), "spec_of", None)
        return get() if callable(get) else {}

    def _column_names(self) -> List[str]:
        get = getattr(self.model(), "columns", None)
        return get() if callable(get) else []

    def _has_region_row(self) -> bool:
        return any(getattr(b.spec, "region", "")
                   for b in self._spec_of().values())

    # ---- Qt ----------------------------------------------------------------
    def sizeHint(self) -> QSize:  # noqa: N802 — Qt
        sz = super().sizeHint()
        if self._has_region_row():
            sz.setHeight(sz.height() * 2)
        return sz

    def paintSection(self, painter, rect, logicalIndex) -> None:  # noqa: N802
        if not self._has_region_row():
            super().paintSection(painter, rect, logicalIndex)
            return
        top_h = rect.height() // 2
        painter.save()
        super().paintSection(painter, rect.adjusted(0, top_h, 0, 0),
                             logicalIndex)
        painter.restore()

        top = rect.adjusted(0, 0, 0, -(rect.height() - top_h))
        painter.save()
        painter.setClipRect(top)
        painter.fillRect(top, QColor(TOKENS.get("bg_panel", "#fafbfc")))
        names = self._column_names()
        vis = [(i, c) for i, c in enumerate(names)
               if not self.isSectionHidden(i)]
        spans = header_spans([c for _i, c in vis], self._spec_of())
        pos = next((p for p, (li, _c) in enumerate(vis)
                    if li == logicalIndex), -1)
        span = next((s for s in spans
                     if s["start"] <= pos < s["start"] + s["count"]), None)
        if span is not None:
            band = QColor(region_hex(span["region_index"]))
            band.setAlphaF(0.30)
            painter.fillRect(top, band)
            # 字畫在**整段**的座標上、剪在自己這一節 —— 局部重繪（只髒中間
            # 一節）也不會把跨欄的字畫掉一半。
            first_li = vis[span["start"]][0]
            last_li = vis[span["start"] + span["count"] - 1][0]
            x0 = self.sectionViewportPosition(first_li)
            x1 = (self.sectionViewportPosition(last_li)
                  + self.sectionSize(last_li))
            span_rect = QRect(x0 + 6, top.y(), max(0, x1 - x0 - 12),
                              top.height())
            painter.setPen(QColor(TOKENS.get("text_primary", "#1f2430")))
            painter.drawText(
                span_rect, int(Qt.AlignLeft | Qt.AlignVCenter),
                painter.fontMetrics().elidedText(
                    str(span["region"]), Qt.ElideRight, span_rect.width()))
        painter.restore()


class _BinDelegate(QStyledItemDelegate):
    """``bin`` 那一格的編輯器：一個上下界擋好的 QSpinBox（鐵則 4 的精神）。

    上界 999 不是猜的 —— bin 最後會寫進 KLARF 的 ``CLASSNUMBER``，那是一個
    整數欄；這裡要擋的是「打了一個字母」與「打了一個負數」，不是替使用者
    決定他的廠內編號要編到幾號。
    """

    def createEditor(self, parent, option, index):        # noqa: N802 — Qt
        box = QSpinBox(parent)
        box.setRange(0, 999)
        box.setAccelerated(True)
        return box


class ResultsTable(QTableView):
    """逐顆的表。``bin`` **改得動但只改在畫面上**（見模組說明），
    雙擊一列 = 去看那一顆。"""

    #: 使用者要去看某一顆（跟 `GalleryPanel.defect_activated` 同一個約定）。
    defect_activated = Signal(str)
    #: 使用者點了判定欄（score / bin / class）＝「這一顆**為什麼**判成這樣」
    #: —— 回溯面板（PR-3）。值是 defect_id；面板開不開由宿主決定。
    trace_requested = Signal(str)
    #: 手動改過的 bin 變了（改了、改回去、或整批清掉）。帶的是**現在還有
    #: 幾顆是手動的** —— 宿主用它講那句「這只在畫面上」。
    bin_overrides_changed = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = ResultsTableModel(self)
        self.setModel(self._model)
        # 換表頭要在 setSortingEnabled **之前** —— 排序把「可點、有箭頭」
        # 接在呼叫當下的那顆表頭上。
        self.setHorizontalHeader(TwoLevelHeader(self))
        self.setObjectName("resultsTable")
        # ⚠ **不要加 `DoubleClicked` 或 `SelectedClicked`**（F48）：這張表的
        # 單擊（判定欄 = 問「為什麼」）與雙擊（= 去看那一顆）都已經有人用了，
        # 而 Qt 的 edit trigger 是**整張表**的設定 —— 加上去的話同一個手勢會
        # 同時開回溯面板跟一個編輯框。`EditKeyPressed` 是 F2／Enter，
        # 一個還沒有人用的手勢；發現得到那條路走右鍵選單。
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)
        self.setItemDelegate(_BinDelegate(self))
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(22)
        head = self.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.Interactive)
        head.setStretchLastSection(False)
        head.setHighlightSections(False)
        self.doubleClicked.connect(self._on_double_click)
        self.clicked.connect(self._on_click)

    # ---- 外部 --------------------------------------------------------------
    def set_results(self, results: Sequence[Dict[str, Any]],
                    class_names: Optional[Dict[str, str]] = None,
                    layout: Optional[Dict[str, Any]] = None,
                    alarms: Optional[Dict[str, bool]] = None) -> None:
        self._model.set_results(results, class_names, layout, alarms)
        # 表頭可能在單層/雙層之間切換（有沒有欄帶區域）—— 高度要重新量。
        self.horizontalHeader().updateGeometry()
        self.resizeColumnsToContents()
        for i in range(self._model.columnCount()):
            # 一個很長的錯誤訊息會把那一欄撐到整張表都看不到別的東西。
            if self.columnWidth(i) > 220:
                self.setColumnWidth(i, 220)

    def columns(self) -> List[str]:
        return self._model.columns()

    def row_count(self) -> int:
        return self._model.rowCount()

    def cell_text(self, row: int, column: str) -> str:
        cols = self._model.columns()
        if column not in cols or not (0 <= row < self._model.rowCount()):
            return ""
        return str(self._model.data(
            self._model.index(row, cols.index(column)), Qt.DisplayRole) or "")

    def select_defect(self, defect_id: str) -> bool:
        i = self._model.row_of(defect_id)
        if i < 0:
            return False
        self.selectRow(i)
        self.scrollTo(self._model.index(i, 0))
        return True

    def selected_ids(self) -> List[str]:
        return [self._model.defect_id_at(i.row())
                for i in self.selectionModel().selectedRows()]

    def bin_overrides(self) -> Dict[str, int]:
        """``defect_id`` → 手動改成的 bin。"""
        return self._model.bin_overrides()

    def clear_bin_overrides(self) -> int:
        n = self._model.clear_bin_overrides()
        if n:
            self.bin_overrides_changed.emit(len(self.bin_overrides()))
        return n

    def set_bin_override(self, row: int, value: Optional[int]) -> bool:
        """改（或用 ``None`` 改回引擎判的那個）—— 右鍵選單與測試走這一支。"""
        cols = self._model.columns()
        if "bin" not in cols or not (0 <= row < self._model.rowCount()):
            return False
        idx = self._model.index(row, cols.index("bin"))
        if value is None:
            value = self._model._rows[row].get("bin")
            if value is None:                  # 引擎也沒判 → 只能整個拿掉
                self._model._rows[row].pop(OVERRIDE_KEY, None)
                self._model.dataChanged.emit(idx, idx)
                self.bin_overrides_changed.emit(len(self.bin_overrides()))
                return True
        ok = self._model.setData(idx, int(value), Qt.EditRole)
        if ok:
            self.bin_overrides_changed.emit(len(self.bin_overrides()))
        return ok

    # ---- 右鍵：改 bin ------------------------------------------------------
    def _on_context_menu(self, pos) -> None:
        """選了幾列就改幾列 —— **複審是一次看一群，不是一顆一顆**。

        右鍵的位置那一列如果不在選取範圍裡，就以它為準（Qt 各處的慣例：
        右鍵不會偷偷把你選好的那一群換掉，但點在別的地方就以那裡為準）。
        """
        index = self.indexAt(pos)
        rows = sorted({i.row() for i in self.selectionModel().selectedRows()})
        if index.isValid() and index.row() not in rows:
            rows = [index.row()]
        if not rows:
            return
        menu = QMenu(self)
        act_set = menu.addAction("Set bin… (%d selected)" % len(rows)
                                 if len(rows) > 1 else "Set bin…")
        marked = [r for r in rows if OVERRIDE_KEY in self._model._rows[r]]
        act_clear = menu.addAction("Undo the manual bin")
        act_clear.setEnabled(bool(marked))
        act_set.setToolTip("On screen only - exports keep the engine's bin")
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen is act_set:
            first = self._model._rows[rows[0]]
            start = int(first.get(OVERRIDE_KEY, first.get("bin") or 0))
            value, ok = QInputDialog.getInt(
                self, "Set bin",
                "Bin for %d defect(s) — on screen only; exports and KLARF "
                "keep the engine's value." % len(rows),
                start, 0, 999)
            if ok:
                for r in rows:
                    self.set_bin_override(r, int(value))
        elif chosen is act_clear:
            for r in marked:
                self.set_bin_override(r, None)

    def _on_double_click(self, index) -> None:
        did = self._model.defect_id_at(index.row())
        if did:
            self.defect_activated.emit(did)

    def _on_click(self, index) -> None:
        """點徽章＝把明細攤開來看（跟懸停同一份字 —— 資料只有一份）。
        點判定欄（score / bin / class）＝問「為什麼」（PR-3 的回溯面板）。
        ``clicked`` 在 selection 更新**之後**發，所以兩者都不擋列選取。"""
        cols = self._model.columns()
        if not (0 <= index.column() < len(cols)):
            return
        name = cols[index.column()]
        if name in ("score", "bin", CLASS_COLUMN):
            did = self._model.defect_id_at(index.row())
            if did:
                self.trace_requested.emit(did)
            return
        if name != BADGE_COLUMN:
            return
        tip = self._model.data(index, Qt.ToolTipRole)
        if tip:
            QToolTip.showText(
                self.viewport().mapToGlobal(self.visualRect(index).center()),
                str(tip), self)


class ResultsTablePane(QWidget):
    """表 ＋ 分層的控制列（搜尋框、「All measurements (N)」）。

    分層的**邏輯**全在 :func:`visible_columns`（純函式）；這裡只把它的答案
    套到 `setColumnHidden` 上。展開狀態與搜尋字是純 instance attr ——
    session 級，開新視窗就歸零（跟這個 UI 其他的暫態一樣，不進 QSettings）。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._expanded = False

        self.search = QLineEdit(self)
        self.search.setObjectName("resultsColumnSearch")
        self.search.setPlaceholderText("Search columns…")
        self.search.setClearButtonEnabled(True)
        self.search.setToolTip(
            "Type part of a column name to pull it out of the folded set. "
            "Clearing the box puts things back the way they were.")
        self.search.textChanged.connect(self._apply_visibility)

        self.more = QToolButton(self)
        self.more.setObjectName("resultsMoreColumns")
        self.more.setCheckable(True)
        self.more.setToolTip(
            "The table starts with just the columns the verdict actually "
            "uses. This shows every measured number as well.")
        self.more.toggled.connect(self._on_toggled)

        # 維度過濾（PR-3）：三顆下拉，值只列 spec 裡**真的存在**的。
        # chip 是限縮（同維 OR、跨維 AND），跟搜尋框的「現身」互不侵犯 ——
        # 語意都在 :func:`visible_columns`（純函式）。
        self._dims: List[Tuple[str, str]] = []
        self._chips: List[FilterChip] = []
        self.dim_buttons: Dict[str, QToolButton] = {}
        for kind, text, tip in (
                ("region", "Region",
                 "Show only the columns measured on one region."),
                ("stat", "Statistic",
                 "Show only one statistic across every card and region."),
                ("card", "Card",
                 "Show only the columns one card produced.")):
            b = QToolButton(self)
            b.setObjectName("resultsDim_%s" % kind)
            b.setText(text)
            b.setToolTip(tip)
            b.setPopupMode(QToolButton.InstantPopup)
            b.setMenu(QMenu(b))
            b.setVisible(False)            # set_results 有維度值才現身
            self.dim_buttons[kind] = b

        self.table = ResultsTable(self)
        #: 轉出去給宿主接的訊號（跟以前 `ResultsTable` 的約定一字不變）。
        self.defect_activated = self.table.defect_activated
        self.trace_requested = self.table.trace_requested
        self.bin_overrides_changed = self.table.bin_overrides_changed

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(self.search, 1)
        for b in self.dim_buttons.values():
            bar.addWidget(b, 0)
        bar.addWidget(self.more, 0)
        self._chip_bar = QHBoxLayout()
        self._chip_bar.setContentsMargins(0, 0, 0, 0)
        self._chip_bar.setSpacing(4)
        self._chip_bar.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addLayout(bar)
        lay.addLayout(self._chip_bar)
        lay.addWidget(self.table, 1)

    # ---- 外部（沿用 ResultsTable 的介面，宿主換上來不用改） ---------------
    def set_results(self, results: Sequence[Dict[str, Any]],
                    class_names: Optional[Dict[str, str]] = None,
                    layout: Optional[Dict[str, Any]] = None,
                    alarms: Optional[Dict[str, bool]] = None) -> None:
        self.table.set_results(results, class_names, layout, alarms)
        n = self.table._model.n_more()
        self.more.setText("All measurements (%d)" % n)
        # 沒有摺疊區（平鋪模式、或判定引用了每一欄）就不擺一顆沒事做的鈕。
        self.more.setVisible(n > 0)
        # 新的一批＝欄位變了：舊 chip 可能指著不存在的值，全部清掉
        # （跟 Gallery 換批清分數篩選同一條規矩）。
        self._clear_dims()
        self._rebuild_dim_menus()
        self._apply_visibility()

    def columns(self) -> List[str]:
        return self.table.columns()

    def visible_column_names(self) -> List[str]:
        cols = self.table.columns()
        return [c for i, c in enumerate(cols)
                if not self.table.isColumnHidden(i)]

    def row_count(self) -> int:
        return self.table.row_count()

    def cell_text(self, row: int, column: str) -> str:
        return self.table.cell_text(row, column)

    def select_defect(self, defect_id: str) -> bool:
        return self.table.select_defect(defect_id)

    def selected_ids(self) -> List[str]:
        return self.table.selected_ids()

    def set_expanded(self, expanded: bool) -> None:
        self.more.setChecked(bool(expanded))

    def is_expanded(self) -> bool:
        return self._expanded

    # ---- 維度過濾（PR-3） --------------------------------------------------
    def dims(self) -> List[Tuple[str, str]]:
        return list(self._dims)

    def add_dim(self, kind: str, value: str) -> None:
        """加一顆維度 chip（下拉選單也走這裡）。重複加是 no-op。"""
        pair = (str(kind), str(value))
        if pair in self._dims:
            return
        self._dims.append(pair)
        shown = _stat_menu_text(value) if kind == "stat" else value
        chip = FilterChip("%s: %s" % (self.dim_buttons[kind].text(), shown),
                          "Click to remove this filter.", self)
        chip.clicked.connect(lambda _=False, p=pair: self.remove_dim(*p))
        self._chips.append(chip)
        self._chip_bar.insertWidget(self._chip_bar.count() - 1, chip)
        self._apply_visibility()

    def remove_dim(self, kind: str, value: str) -> None:
        pair = (str(kind), str(value))
        if pair not in self._dims:
            return
        i = self._dims.index(pair)
        self._dims.pop(i)
        chip = self._chips.pop(i)
        chip.setParent(None)
        chip.deleteLater()
        self._apply_visibility()

    def _clear_dims(self) -> None:
        self._dims = []
        for chip in self._chips:
            chip.setParent(None)
            chip.deleteLater()
        self._chips = []

    def _rebuild_dim_menus(self) -> None:
        """三顆下拉只列**存在的**值（region 照出現序、stat 用短標籤顯示、
        card 用消歧後的 label）。一個值都沒有的維度整顆鈕收起來。"""
        spec_of = self.table._model.spec_of()
        values: Dict[str, List[Tuple[str, str]]] = {
            "region": [], "stat": [], "card": []}
        seen: Dict[str, set] = {k: set() for k in values}
        for b in spec_of.values():
            for kind in values:
                v = _dim_value(b, kind)
                if not v or v in seen[kind]:
                    continue
                seen[kind].add(v)
                shown = _stat_menu_text(v) if kind == "stat" else v
                values[kind].append((v, shown))
        for kind, button in self.dim_buttons.items():
            menu = button.menu()
            menu.clear()
            for v, shown in values[kind]:
                menu.addAction(shown).triggered.connect(
                    lambda _=False, k=kind, val=v: self.add_dim(k, val))
            button.setVisible(bool(values[kind]))

    # ---- 內部 --------------------------------------------------------------
    def _on_toggled(self, checked: bool) -> None:
        self._expanded = bool(checked)
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        cols = self.table.columns()
        vis = set(visible_columns(cols, self.table._model.verdict_columns(),
                                  self._expanded, self.search.text(),
                                  self.table._model.spec_of(), self._dims))
        for i, c in enumerate(cols):
            self.table.setColumnHidden(i, c not in vis)

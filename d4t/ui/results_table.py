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

⚠ **唯讀。** 「看到判錯的那一顆就地改掉」很自然，但那會讓這一頁從「看結果」
變成「編結果」——而那是兩件事，還沒定調（見 `docs/plans/F27-results-panel.md`）。

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

分組只到卡層級（區域層級等 PR-3 的 FeatureSpec）——**不拆特徵字串猜語意**。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLineEdit, QTableView,
    QToolButton, QToolTip, QVBoxLayout, QWidget,
)

from ..core.export.report import BASE_COLUMNS, feature_keys
from .theme import TOKENS

__all__ = [
    "ResultsTable", "ResultsTableModel", "ResultsTablePane",
    "table_columns", "column_layout", "visible_columns", "row_warnings",
]

#: 類別名那一欄插在哪（``defect_id`` 之後）——**它是這一顆判成了什麼**，
#: 跟 id 一起看才有意義，排在最後面等於要橫向捲過整排特徵才看得到。
CLASS_COLUMN = "class"

#: CSV 有、但畫面上沒有用的欄。``ok`` 的資訊已經在 ``error`` 與整列的顏色上，
#: 而一欄 0/1 在一張要用眼睛掃的表上只是雜訊。
_HIDDEN = ("ok",)

#: 警示徽章那一欄（永遠在最左）。名字帶 ``!`` 所以撞不到任何特徵名 ——
#: 特徵名都是 Python 識別字。它跟 ``class`` 一樣只存在於畫面上，CSV 沒有。
BADGE_COLUMN = "!warn"


def _fixed_columns() -> List[str]:
    """每一份表都有的前段：徽章 ＋ base（去 ``ok``）＋ ``class`` 緊鄰 id。"""
    base = [c for c in BASE_COLUMNS if c not in _HIDDEN]
    i = base.index("defect_id") + 1 if "defect_id" in base else 0
    return [BADGE_COLUMN] + base[:i] + [CLASS_COLUMN] + base[i:]


def _layout_columns(results: Sequence[Dict[str, Any]],
                    verdict_features: Sequence[str],
                    groups: Sequence[Tuple[str, str, Sequence[str]]],
                    hidden: Sequence[str],
                    ) -> Tuple[List[str], List[str]]:
    """(判定層的欄, 摺疊區的欄)。`table_columns` 與 `column_layout` 都走這裡
    —— 判定層是哪幾欄只能有一個答案。"""
    drop = set(hidden)
    vcols = list(_fixed_columns())
    placed = set(vcols)
    for f in verdict_features:
        f = str(f)
        # 判定引用了沒人產出的名字 → **照樣是一欄**（整欄留白）。
        if f and f not in placed and f not in drop:
            placed.add(f)
            vcols.append(f)
    rest: List[str] = []
    for _nid, _label, names in groups:
        for n in names:
            n = str(n)
            if n and n not in placed and n not in drop:
                placed.add(n)
                rest.append(n)
    # 歸不到任何一張卡的放最後（`route_taken`、let 產物、救援名那些）。
    for n in feature_keys(results):
        if n not in placed and n not in drop:
            placed.add(n)
            rest.append(n)
    return vcols, rest


def table_columns(results: Sequence[Dict[str, Any]],
                  verdict_features: Sequence[str] = (),
                  groups: Sequence[Tuple[str, str, Sequence[str]]] = (),
                  hidden: Sequence[str] = ()) -> List[str]:
    """這張表有哪幾欄（順序就是顯示順序）。

    不帶引數＝以前的平鋪行為（base + class + 特徵照字母序）加上徽章欄。
    ``hidden``（診斷欄）**完全不在**回傳裡 —— 值走徽章明細與匯出，不走表格。
    """
    vcols, rest = _layout_columns(results, verdict_features, groups, hidden)
    return vcols + rest


def column_layout(results: Sequence[Dict[str, Any]],
                  verdict_features: Sequence[str] = (),
                  groups: Sequence[Tuple[str, str, Sequence[str]]] = (),
                  diagnostics: Sequence[str] = ()) -> Dict[str, Any]:
    """`ResultsTableModel.set_results` 吃的分層描述。

    「判定引用 > 診斷隱藏」那條規矩住在這裡：被判定引用的診斷特徵**不**藏
    （使用者 2026-08-27 定調 —— 「這顆為什麼判 NG」要看得到比的那個值），
    其餘的診斷欄兩層都不出現。
    """
    verdict = [str(f) for f in verdict_features]
    hidden = [d for d in diagnostics if d not in set(verdict)]
    vcols, rest = _layout_columns(results, verdict, groups, hidden)
    return {"columns": vcols + rest, "verdict_columns": vcols,
            "n_more": len(rest), "diagnostics": [str(d) for d in diagnostics]}


def visible_columns(columns: Sequence[str], verdict_columns: Sequence[str],
                    expanded: bool, search: str) -> List[str]:
    """現在看得到哪幾欄 —— 分層的**全部**邏輯，純函式（不變量測試打這裡）。

    展開＝全部；收合＝判定層 ∪ 搜尋命中的欄（子字串、不分大小寫）。
    清空搜尋就還原 —— 搜尋不改展開狀態。
    """
    if expanded:
        return list(columns)
    keep = set(verdict_columns)
    s = str(search or "").strip().lower()
    return [c for c in columns if c in keep or (s and s in c.lower())]


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
    if column in ("defect_id", "score", "bin", "ok"):
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

    # ---- 資料 --------------------------------------------------------------
    def set_results(self, results: Sequence[Dict[str, Any]],
                    class_names: Optional[Dict[str, str]] = None,
                    layout: Optional[Dict[str, Any]] = None,
                    alarms: Optional[Dict[str, bool]] = None) -> None:
        """``layout`` 來自 :func:`column_layout`；不給＝平鋪（每一欄都是判定層，
        沒有摺疊區）。``alarms`` 來自 `verdict_features.diagnostic_alarm_map`。"""
        names = dict(class_names or {})
        self.beginResetModel()
        if layout is None:
            self._columns = table_columns(results)
            self._verdict_columns = list(self._columns)
            self._diagnostics = []
        else:
            self._columns = list(layout.get("columns") or [])
            self._verdict_columns = list(layout.get("verdict_columns") or [])
            self._diagnostics = list(layout.get("diagnostics") or [])
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
        def fmt(v: Any) -> str:
            return "%.4g" % v if isinstance(v, float) else str(v)

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

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        if 0 <= section < len(self._columns):
            name = self._columns[section]
            # 徽章欄的表頭留白 —— ``!warn`` 是程式的哨兵，不是給人看的字。
            return "" if name == BADGE_COLUMN else name
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

        if role == Qt.DisplayRole:
            if value is None:
                # ⚠ **算不出來的那一格留白，不是 0、也不是 NaN**（F19 那一條）。
                return ""
            if isinstance(value, float):
                return "%.4g" % value
            return str(value)
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


class ResultsTable(QTableView):
    """逐顆的表。**唯讀**（見模組說明），雙擊一列 = 去看那一顆。"""

    #: 使用者要去看某一顆（跟 `GalleryPanel.defect_activated` 同一個約定）。
    defect_activated = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model = ResultsTableModel(self)
        self.setModel(self._model)
        self.setObjectName("resultsTable")
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
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

    def _on_double_click(self, index) -> None:
        did = self._model.defect_id_at(index.row())
        if did:
            self.defect_activated.emit(did)

    def _on_click(self, index) -> None:
        """點徽章＝把明細攤開來看（跟懸停同一份字 —— 資料只有一份）。"""
        cols = self._model.columns()
        if not (0 <= index.column() < len(cols)):
            return
        if cols[index.column()] != BADGE_COLUMN:
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

        self.table = ResultsTable(self)
        #: 轉出去給宿主接的訊號（跟以前 `ResultsTable` 的約定一字不變）。
        self.defect_activated = self.table.defect_activated

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.more, 0)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addLayout(bar)
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

    # ---- 內部 --------------------------------------------------------------
    def _on_toggled(self, checked: bool) -> None:
        self._expanded = bool(checked)
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        cols = self.table.columns()
        vis = set(visible_columns(cols, self.table._model.verdict_columns(),
                                  self._expanded, self.search.text()))
        for i, c in enumerate(cols):
            self.table.setColumnHidden(i, c not in vis)

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
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget

from ..core.export.report import BASE_COLUMNS, feature_keys
from .theme import TOKENS

__all__ = ["ResultsTable", "ResultsTableModel", "table_columns"]

#: 類別名那一欄插在哪（``defect_id`` 之後）——**它是這一顆判成了什麼**，
#: 跟 id 一起看才有意義，排在最後面等於要橫向捲過整排特徵才看得到。
CLASS_COLUMN = "class"

#: CSV 有、但畫面上沒有用的欄。``ok`` 的資訊已經在 ``error`` 與整列的顏色上，
#: 而一欄 0/1 在一張要用眼睛掃的表上只是雜訊。
_HIDDEN = ("ok",)


def table_columns(results: Sequence[Dict[str, Any]]) -> List[str]:
    """這張表有哪幾欄（順序就是顯示順序）。"""
    base = [c for c in BASE_COLUMNS if c not in _HIDDEN]
    i = base.index("defect_id") + 1 if "defect_id" in base else 0
    return base[:i] + [CLASS_COLUMN] + base[i:] + list(feature_keys(results))


def _cell(row: Dict[str, Any], column: str) -> Any:
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

    # ---- 資料 --------------------------------------------------------------
    def set_results(self, results: Sequence[Dict[str, Any]],
                    class_names: Optional[Dict[str, str]] = None) -> None:
        names = dict(class_names or {})
        self.beginResetModel()
        self._columns = table_columns(results)
        self._rows = []
        for r in results or []:
            row = dict(r)
            row["cls"] = names.get(str(r.get("defect_id", "")), "")
            self._rows.append(row)
        self.endResetModel()

    def columns(self) -> List[str]:
        return list(self._columns)

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
            return self._columns[section]
        return None

    def data(self, index, role=Qt.DisplayRole):           # noqa: N802 — Qt
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = self._columns[index.column()]
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

    # ---- 外部 --------------------------------------------------------------
    def set_results(self, results: Sequence[Dict[str, Any]],
                    class_names: Optional[Dict[str, str]] = None) -> None:
        self._model.set_results(results, class_names)
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

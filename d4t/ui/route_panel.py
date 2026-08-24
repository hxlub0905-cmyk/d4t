# d4t Studio — 分流的編輯區塊（F23 期2，2026-08-24）。
"""``route_by`` 的編輯器：**判定欄上方的一個小區塊**（F23 §6 定的位置）。

不是卡片、不進畫布 —— 它在**跑之前**就決定每一顆走哪條 route，而畫布畫的是
跑的東西。形狀照計畫書：欄位下拉（KLARF 的欄，程式知道就不讓使用者用打的）＋
值 → route 的對照表＋「對不上怎麼辦」（走某條 route，或那一顆失敗）。

跟 `DecidePanel` 同一個立場：直接改 model（`set_route_by` / `clear_route_by`
整包換掉，一次改動一步 undo），打字不重建。
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QVBoxLayout, QWidget,
)

from .widgets import small_button

__all__ = ["RouteByBox"]

#: 「對不上」下拉的第一格：不走 default、那一顆失敗（站點政策的另一半）。
_FAIL_CHOICE = "(fail that defect)"


class RouteByBox(QWidget):
    """``route_by`` 的編輯區塊。沒有分流時只剩一顆勾選框。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._model: Any = None
        self._columns: List[str] = []
        self._building = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 0)
        lay.setSpacing(4)
        self.toggle = QCheckBox("Route by a KLARF column", self)
        self.toggle.setToolTip(
            "Each defect reads one KLARF column BEFORE anything runs, and "
            "that value picks which route (which cards) it goes through.")
        self.toggle.toggled.connect(self._on_toggle)
        lay.addWidget(self.toggle)
        self.body = QWidget(self)
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(16, 0, 0, 0)
        self.body_lay.setSpacing(4)
        lay.addWidget(self.body)

    # ---- 外部餵進來的 ------------------------------------------------------
    def set_model(self, model: Any) -> None:
        self._model = model
        self.refresh()

    def set_columns(self, columns: Sequence[str]) -> None:
        """這份 KLARF 有哪些欄（下拉用；沒資料集時空的，改用打的那一格）。"""
        new = [str(c) for c in columns]
        if new != self._columns:
            self._columns = new
            self.refresh()

    # ---- 重建 --------------------------------------------------------------
    def _typing(self) -> bool:
        w = self.focusWidget()
        return w is not None and isinstance(w, QLineEdit) and w.hasFocus()

    def refresh(self, force: bool = False) -> None:
        if self._building or (not force and self._typing()):
            return
        self._building = True
        try:
            self._rebuild()
        finally:
            self._building = False

    def _clear(self) -> None:
        while self.body_lay.count():
            item = self.body_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _rb(self):
        return None if self._model is None else getattr(self._model,
                                                        "route_by", None)

    def _rebuild(self) -> None:
        self._clear()
        rb = self._rb()
        self.toggle.blockSignals(True)
        self.toggle.setChecked(rb is not None)
        self.toggle.blockSignals(False)
        self.body.setVisible(rb is not None)
        if rb is None:
            return

        routes = list(self._model.route_keys())

        # ── 欄位 ──
        row = QWidget(self.body)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        tag = QLabel("Column", row)
        tag.setObjectName("paramHint")
        lay.addWidget(tag)
        col = QComboBox(row)
        col.setEditable(True)      # 沒載資料時欄名清單是空的，還是要打得進去
        for c in self._columns:
            col.addItem(c)
        col.setCurrentText(str(rb.column))
        col.setToolTip("The KLARF column whose value picks the route "
                       "(CLASSNUMBER is the usual one).")
        col.currentTextChanged.connect(
            lambda t: self._write(column=str(t)))
        lay.addWidget(col, 1)
        self.body_lay.addWidget(row)

        # ── 對照表 ──
        for i, (value, route) in enumerate(sorted(rb.map.items())):
            self.body_lay.addWidget(self._map_row(i, value, route, routes))
        add = small_button("+ Add a value", shape="wide")
        add.setToolTip("Map one more column value to a route.")
        add.clicked.connect(self._add_row)
        self.body_lay.addWidget(add)

        # ── 對不上 ──
        row2 = QWidget(self.body)
        lay2 = QHBoxLayout(row2)
        lay2.setContentsMargins(0, 0, 0, 0)
        tag2 = QLabel("Everything else →", row2)
        tag2.setObjectName("paramHint")
        lay2.addWidget(tag2)
        other = QComboBox(row2)
        other.addItem(_FAIL_CHOICE, "")
        for rk in routes:
            other.addItem(rk, rk)
        idx = other.findData(str(rb.default or "").strip())
        other.setCurrentIndex(max(0, idx))
        other.setToolTip("A value not in the table either takes this route, "
                         "or fails that defect with a message - whichever "
                         "your site wants for classes it has not seen.")
        other.activated.connect(
            lambda i, c=other: self._write(default=str(c.itemData(i) or "")))
        lay2.addWidget(other, 1)
        self.body_lay.addWidget(row2)

    def _map_row(self, i: int, value: str, route: str,
                 routes: List[str]) -> QWidget:
        row = QFrame(self.body)
        row.setObjectName("decideRow")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(6)
        val = QLineEdit(str(value), row)
        val.setPlaceholderText("value")
        val.setFixedWidth(72)
        val.setToolTip("The column value, compared as text after stripping "
                       "spaces ('1' and ' 1' are the same cell).")
        val.editingFinished.connect(
            lambda v=val, old=value: self._rename_value(old, v.text()))
        arrow = QLabel("→", row)
        arrow.setObjectName("paramHint")
        combo = QComboBox(row)
        for rk in routes:
            combo.addItem(rk)
        if route not in routes:
            combo.addItem(route)       # 指到不存在的 route：照顯示，lint 會講
        combo.setCurrentText(str(route))
        combo.activated.connect(
            lambda _i, c=combo, v=value: self._write_map(v, c.currentText()))
        rm = small_button("✕", shape="square")
        rm.setToolTip("Take this value out of the table")
        rm.clicked.connect(lambda _=False, v=value: self._remove_value(v))
        for w, s in ((val, 0), (arrow, 0), (combo, 1), (rm, 0)):
            lay.addWidget(w, s)
        return row

    # ---- 寫回 model --------------------------------------------------------
    def _write(self, column: Optional[str] = None,
               default: Optional[str] = None) -> None:
        rb = self._rb()
        if rb is None:
            return
        self._model.set_route_by(
            rb.column if column is None else column,
            dict(rb.map),
            rb.default if default is None else default)

    def _write_map(self, value: str, route: str) -> None:
        rb = self._rb()
        if rb is None:
            return
        mapping = dict(rb.map)
        mapping[str(value)] = str(route)
        self._model.set_route_by(rb.column, mapping, rb.default)
        self.refresh(force=True)

    def _rename_value(self, old: str, new: str) -> None:
        rb = self._rb()
        new = str(new).strip()
        if rb is None or new == str(old) or not new:
            return
        mapping = dict(rb.map)
        mapping[new] = mapping.pop(str(old), self._model.route_keys()[0])
        self._model.set_route_by(rb.column, mapping, rb.default)
        self.refresh(force=True)

    def _add_row(self) -> None:
        rb = self._rb()
        if rb is None:
            return
        mapping = dict(rb.map)
        n = 1
        while str(n) in mapping:
            n += 1
        mapping[str(n)] = self._model.route_keys()[0]
        self._model.set_route_by(rb.column, mapping, rb.default)
        self.refresh(force=True)

    def _remove_value(self, value: str) -> None:
        rb = self._rb()
        if rb is None:
            return
        mapping = dict(rb.map)
        mapping.pop(str(value), None)
        self._model.set_route_by(rb.column, mapping, rb.default)
        self.refresh(force=True)

    def _on_toggle(self, on: bool) -> None:
        if self._model is None:
            return
        if on and self._rb() is None:
            column = self._columns[0] if self._columns else "CLASSNUMBER"
            self._model.set_route_by(column, {}, "")
        elif not on and self._rb() is not None:
            self._model.clear_route_by()
        self.refresh(force=True)

    # ---- 查詢（測試用）-----------------------------------------------------
    def rows(self) -> List[Tuple[str, str]]:
        rb = self._rb()
        return [] if rb is None else sorted(rb.map.items())

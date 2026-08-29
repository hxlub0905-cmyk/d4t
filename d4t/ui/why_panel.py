# d4t Studio — 這一顆為什麼判成這樣（PR-3，2026-08-28）。
"""**三次點擊的回溯**：結果表點 score/bin → 這塊面板 → 點一項跳到產出它的卡。

「這顆為什麼判 NG」以前要人腦重放：打開 recipe、找到樹、逐格查 CSV。
`core.pipeline.verdict_trace` 把那個過程做成純函式，這裡只負責**畫它的輸出**
—— 面板上每一個數字要嘛是 features 裡的值、要嘛是引擎寫的（三條立身規矩
見那個模組的 docstring），這裡一個都不算。

跟 `verdict_band` 同一個立場：純函式（:func:`why_rows`）在前、薄 widget
在後，面板不碰 model、不驅動任何東西 —— 點了什麼只發訊號，Studio 決定跳去
哪。措辭沿用畫面上已有的那幾句（「Working numbers」是判定面板的字、
「if missing ⇒」是 let 那一格的字、缺值的說法跟引擎的 warning 同族）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout,
    QWidget,
)

from ..core.pipeline.expression import ExpressionError, parse_expression
from ..core.pipeline.verdict_trace import _collect_var_spans
from .numbers import format_feature_value

__all__ = ["WhyPanel", "why_rows"]


def _fmt(value: Any) -> str:
    """**沒有值印 `?` 是這裡刻意的**（其他地方留白）。

    回溯面板一列講的是「這一題問了什麼、答案是幾」—— 一個空格讀起來像
    「這一題沒問」，而真相是「問了，但那個數字這一顆沒量到」。
    值本身走 `format_feature_value`（F52，全 UI 只有那一支）。
    """
    return "?" if value is None else format_feature_value(value)


def _first_var(expr_text: str) -> str:
    """一題裡**最先出現**的變數 —— 點那一步要跳去的名字。

    一題可以問到好幾個數字；挑位置最前的那一個（使用者讀到的第一個），
    比挑字母序或猜「最重要的」誠實。
    """
    try:
        expr = parse_expression(str(expr_text or ""))
    except ExpressionError:
        return ""
    spans: List[Any] = []
    _collect_var_spans(expr._ast, spans)
    if not spans:
        return ""
    return str(min(spans, key=lambda x: x[1])[0])


def why_rows(trace: Any) -> List[Dict[str, Any]]:
    """`verdict_trace.Trace` → 要畫的列（純函式，不變量測試打這裡）。

    每列 ``{"kind", "text", "name", "note"?}``；``kind`` ∈ head / let / step
    / leaf / score / missing。``name`` 是點下去要跳的特徵名（"" = 不可點）
    —— let 列是 let 自己的名字（引擎的、對映 Score / Bin 偽卡），step 列是
    那一題最先問到的名字。
    """
    rows: List[Dict[str, Any]] = []
    if trace is None or trace.mode == "none":
        return rows

    if trace.lets:
        rows.append({"kind": "head", "text": "Working numbers", "name": ""})
        for let in trace.lets:
            row: Dict[str, Any] = {
                "kind": "let", "name": let.name,
                "text": "%s = %s   (= %s)" % (let.name, _fmt(let.value),
                                              let.valued)}
            if let.scaled:
                row["note"] = ("scaled against the whole lot" +
                               ("" if let.raw is None
                                else " · before scaling it was %s"
                                % _fmt(let.raw)))
            if let.filled:
                row["note"] = "if missing ⇒ %s — used on this defect" % \
                    (let.fill or "?")
            elif let.missing_vars and "note" not in row:
                row["note"] = ("%s was never measured on this defect"
                               % ", ".join(let.missing_vars))
            rows.append(row)

    if trace.mode in ("tree", "rules"):
        rows.append({"kind": "head", "text": "The path it took", "name": ""})
        for step in trace.steps:
            row = {"kind": "step", "name": _first_var(step.when),
                   "text": "%s ? %s" % (step.valued, step.answer),
                   "expr": str(step.when)}
            if step.missing:
                row["note"] = ("%s was never measured on this defect, "
                               "so the answer is no"
                               % ", ".join(step.missing))
            rows.append(row)
        label = str(trace.leaf_label or "")
        tail = "" if trace.leaf_bin is None else "bin %d" % trace.leaf_bin
        text = " · ".join(x for x in (label, tail) if x)
        rows.append({"kind": "leaf", "name": "",
                     "text": "⇒ %s" % (text or "?"),
                     "bin": trace.leaf_bin})
        if trace.score_expr:
            rows.append({"kind": "score", "name": "score",
                         "text": "score = %s   (= %s)"
                         % (_fmt(trace.score), trace.score_valued)})
    elif trace.mode == "score":
        rows.append({"kind": "head", "text": "Score", "name": ""})
        rows.append({"kind": "score", "name": "score",
                     "text": "score = %s   (= %s)"
                     % (_fmt(trace.score), trace.score_valued)})
        if trace.threshold is not None:
            rows.append({"kind": "score", "name": "",
                         "text": "threshold %s" % _fmt(trace.threshold)})
        if trace.leaf_bin is not None:
            rows.append({"kind": "leaf", "name": "",
                         "text": "⇒ bin %d" % trace.leaf_bin,
                         "bin": trace.leaf_bin})

    if trace.missing:
        rows.append({"kind": "missing", "name": "",
                     "text": "Never measured on this defect: %s"
                     % ", ".join(trace.missing)})
    return rows


class _Row(QFrame):
    """一列。有 ``name`` 的可以點 —— 一列一個動作（同 `verdict_band` 的列）。"""

    clicked = Signal(str)

    def __init__(self, row: Dict[str, Any],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.row = dict(row)
        name = str(row.get("name") or "")
        kind = str(row.get("kind") or "")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10 if kind != "head" else 2, 2, 2, 2)
        lay.setSpacing(0)
        text = QLabel(str(row.get("text") or ""), self)
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if kind == "head":
            text.setObjectName("paramSection")
        if kind == "leaf":
            f = text.font()
            f.setBold(True)
            text.setFont(f)
        lay.addWidget(text)
        note = str(row.get("note") or "")
        if note:
            hint = QLabel(note, self)
            hint.setObjectName("paramHint")
            hint.setWordWrap(True)
            lay.addWidget(hint)
        if name:
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip("Click to jump to whatever produced ‘%s’." % name)

    def mouseReleaseEvent(self, event) -> None:     # noqa: N802 — Qt
        name = str(self.row.get("name") or "")
        if name and event.button() == Qt.LeftButton and \
                self.rect().contains(event.position().toPoint()):
            self.clicked.emit(name)
        super().mouseReleaseEvent(event)


class WhyPanel(QWidget):
    """回溯面板本體。`set_trace` 收 `verdict_trace` 的輸出，點一項就把名字
    發出去（`item_activated`）—— **不擋列選取**：它住在結果表旁邊的
    splitter 裡，show 的時候不搶焦點，Esc 關掉。"""

    #: 使用者點了一項（值是特徵名）。跳去哪由 Studio 決定。
    item_activated = Signal(str)
    #: 面板被關掉（Esc 或右上的 ×）。
    closed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("whyPanel")
        self._defect_id = ""
        self._rows: List[Dict[str, Any]] = []
        self._row_widgets: List[_Row] = []
        # Esc 要收得到，但 show() 不搶焦點（見 `present`）。
        self.setFocusPolicy(Qt.ClickFocus)

        head = QWidget(self)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(8, 6, 4, 2)
        hl.setSpacing(6)
        self.title = QLabel("Why this verdict", head)
        self.title.setObjectName("paramSection")
        hl.addWidget(self.title, 1)
        self.btn_close = QToolButton(head)
        self.btn_close.setText("×")
        self.btn_close.setToolTip("Close (Esc)")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.dismiss)
        hl.addWidget(self.btn_close, 0)

        self._body = QWidget(self)
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(0, 0, 0, 6)
        self._body_lay.setSpacing(2)
        self._body_lay.addStretch(1)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._body)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(head)
        lay.addWidget(scroll, 1)
        self.setMinimumWidth(220)

    # ---- 外部 --------------------------------------------------------------
    def set_trace(self, defect_id: str, trace: Any) -> None:
        self._defect_id = str(defect_id)
        self.title.setText("Why defect %s" % self._defect_id
                           if self._defect_id else "Why this verdict")
        self._rows = why_rows(trace)
        for w in self._row_widgets:
            w.setParent(None)
            w.deleteLater()
        self._row_widgets = []
        for row in self._rows:
            w = _Row(row, self._body)
            w.clicked.connect(self.item_activated)
            self._body_lay.insertWidget(self._body_lay.count() - 1, w)
            self._row_widgets.append(w)

    def rows(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._rows]

    def defect_id(self) -> str:
        return self._defect_id

    def present(self) -> None:
        """秀出來但**不搶焦點** —— 使用者正在表上選列，焦點留在表上。"""
        self.show()

    def dismiss(self) -> None:
        self.hide()
        self.closed.emit()

    def activate_row(self, name: str) -> None:
        """程式化點一項（測試用 —— 跟滑鼠走同一條訊號）。"""
        if any(str(r.get("name") or "") == str(name) for r in self._rows):
            self.item_activated.emit(str(name))

    # ---- Qt ----------------------------------------------------------------
    def keyPressEvent(self, event) -> None:         # noqa: N802 — Qt
        if event.key() == Qt.Key_Escape:
            self.dismiss()
            event.accept()
            return
        super().keyPressEvent(event)

"""M0 驗收：flexadc 全套件零 Qt import（原始碼掃描 + 實際 import 檢查）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "flexadc"
QT_PAT = re.compile(r"^\s*(import|from)\s+(PyQt\d?|PySide\d?|qtpy|Qt)\b", re.M)


def test_no_qt_in_source():
    offenders = []
    for py in PKG.rglob("*.py"):
        if QT_PAT.search(py.read_text(encoding="utf-8")):
            offenders.append(str(py))
    assert not offenders, f"Qt import found in: {offenders}"


def test_no_qt_after_import():
    import flexadc.core.algo  # noqa: F401
    import flexadc.core.ingest  # noqa: F401
    import flexadc.core.calibration  # noqa: F401

    loaded = [m for m in sys.modules if m.split(".")[0] in ("PyQt5", "PyQt6", "PySide2", "PySide6")]
    assert not loaded, f"Qt modules loaded: {loaded}"


def test_py39_syntax():
    import ast
    for py in PKG.rglob("*.py"):
        ast.parse(py.read_text(encoding="utf-8"), filename=str(py), feature_version=(3, 9))

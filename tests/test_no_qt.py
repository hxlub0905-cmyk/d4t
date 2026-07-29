"""M0 驗收：adept 全套件零 Qt import（原始碼掃描 + 實際 import 檢查）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "adept"
CORE = PKG / "core"
QT_PAT = re.compile(r"^\s*(import|from)\s+(PyQt\d?|PySide\d?|qtpy|Qt)\b", re.M)


def test_no_qt_in_core_source():
    """core 禁 Qt；adept/ui 是唯一允許 Qt 的地方（__main__ 須 lazy import）。"""
    offenders = []
    for py in CORE.rglob("*.py"):
        if QT_PAT.search(py.read_text(encoding="utf-8")):
            offenders.append(str(py))
    main_py = PKG / "__main__.py"
    if main_py.exists() and QT_PAT.search(main_py.read_text(encoding="utf-8")):
        offenders.append(str(main_py))
    assert not offenders, f"Qt import found in: {offenders}"


def test_no_qt_after_import():
    """在**乾淨的子行程**裡 import core，然後看 Qt 有沒有被拖進來。

    以前是在測試行程裡直接看 ``sys.modules``，那讓這條測試變成**跟執行順序
    有關**：只要有任何一個 UI 測試檔排在 ``test_no_qt.py`` 前面跑過，Qt 就
    已經在 ``sys.modules`` 裡，這裡就會誤報 —— 而它報的位置離真正的原因
    （另一個檔案的 fixture）很遠，看訊息完全猜不到。加一支新測試檔就可能踩到，
    只因為檔名的字母序。子行程沒有這個問題：問的就是「單獨 import core 時
    會不會拉進 Qt」，而那本來就是這條測試唯一想問的事。
    """
    import subprocess

    code = (
        "import sys\n"
        "import adept.core.algo, adept.core.ingest, adept.core.calibration\n"
        "qt = [m for m in sys.modules "
        "      if m.split('.')[0] in ('PyQt5','PyQt6','PySide2','PySide6')]\n"
        "print(','.join(sorted(qt)))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code],
                          cwd=str(PKG.parent), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    loaded = [m for m in proc.stdout.strip().split(",") if m]
    assert not loaded, f"Qt modules loaded: {loaded}"


def test_py39_syntax():
    import ast
    for py in PKG.rglob("*.py"):
        ast.parse(py.read_text(encoding="utf-8"), filename=str(py), feature_version=(3, 9))

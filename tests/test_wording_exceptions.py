# 例外 → 一句話（2026-09-24，評價清單 #4）：畫面上不准出現 Python 的型別名。
from __future__ import annotations

import logging
import re
from pathlib import Path

from d4t.core.pipeline.step import StepError
from d4t.ui import wording

REPO = Path(__file__).resolve().parent.parent


def test_file_problems_say_which_file_and_what_to_do():
    e = PermissionError(13, "Permission denied", "/x/y/report.xlsx")
    said = wording.exception_text(e)
    assert "report.xlsx" in said and "another program" in said
    assert "PermissionError" not in said and "/x/y" not in said
    said = wording.exception_text(FileNotFoundError(2, "No such file", "/a/b.001"))
    assert "b.001" in said and "moved" in said


def test_no_type_names_leak():
    for e in (KeyError("glv_max"), MemoryError(), OSError(5, "I/O error"),
              ValueError("the width must be positive"), RuntimeError()):
        said = wording.exception_text(e)
        assert said and not re.search(r"\b\w+(Error|Exception)\b", said), said
    assert wording.exception_text(ValueError("the width must be positive")) \
        == "the width must be positive", "core 寫好的人話原樣"


def test_step_error_uses_the_card_name():
    said = wording.exception_text(StepError("glv_stats", "no input wired"))
    assert "no input wired" in said and "[glv_stats]" not in said


def test_failure_logs_the_traceback(caplog):
    caplog.set_level(logging.WARNING, logger="d4t")
    try:
        raise KeyError("x")
    except KeyError as e:
        said = wording.failure("test.here", e)
    assert "KeyError" not in said
    rec = [r for r in caplog.records if "test.here" in r.getMessage()]
    assert rec and rec[0].exc_info, "原始例外要進 log"


def test_the_ui_never_shows_a_type_name_again():
    """反向守門：`type(e).__name__` 拼進給人看的字，只准出現在當機回報。"""
    allowed = {"crashlog.py": "當機對話框：那份是要貼給開發者的",
               "wording.py": "說明文字裡提到它"}
    bad = []
    for py in sorted((REPO / "d4t" / "ui").glob("*.py")):
        if py.name in allowed:
            continue
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"type\((e|exc|err)\)\.__name__", line):
                bad.append("%s:%d" % (py.name, i))
    assert not bad, "改走 wording.failure(where, e)：%s" % bad

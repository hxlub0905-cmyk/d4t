# 評價清單 #1 的 UI 那一半：判定區的勾選框、Results 工具列的常駐警告。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app, "light")
    yield app


def test_ticking_the_box_writes_the_bin_and_unticking_clears_it(qapp):
    from d4t.ui.decide_panel import DecidePanel
    from d4t.ui.viewmodel import RecipeModel

    m = RecipeModel()
    m.use_decide(True)
    p = DecidePanel()
    p.set_model(m)
    p.refresh(force=True)
    assert not p.chk_unanswered.isChecked(), "預設關著（照 F30 答「否」）"
    p.chk_unanswered.setChecked(True)
    assert m.decide.unanswered_bin == 99
    p.chk_unanswered.setChecked(False)
    assert m.decide.unanswered_bin is None


def test_the_results_line_counts_the_unanswered(qapp):
    from d4t.ui.results import summarize_run
    rows = [{"features": {"decide_unanswered": 2.0}},
            {"features": {"decide_unanswered": 0.0}},
            {"features": {}}]
    said = summarize_run(3, 3, 0.1, (), rows)
    assert "1 had a question that could not be answered" in said
    assert "could not be answered" not in summarize_run(3, 3, 0.1, (), rows[1:])

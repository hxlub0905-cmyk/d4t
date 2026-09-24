# 評價清單 #5：Run all 與寫出失敗時跳對話框（其他失敗照舊只在狀態列）。
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from make_sample import generate  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app, "light")
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    return generate(str(tmp_path_factory.mktemp("fd")), n=4, seed=7)


@pytest.fixture
def window(qapp, lot, monkeypatch):
    from d4t.ui import failure_dialog, studio
    told = []
    monkeypatch.setattr(failure_dialog, "tell",
                        lambda parent, what, detail, tips, log_folder=None:
                        told.append((what, detail)) or {})
    win = studio.StudioWindow(show_welcome_on_start=False)
    assert win.load_dataset_path(lot["klarf"], sync=True)
    win.told = told
    yield win
    win.close()


def test_the_words_say_what_to_do(qapp):
    from d4t.ui import failure_dialog
    said = failure_dialog.compose("Run all did not finish", "a file is missing",
                                  ["Check the folder."], "/tmp/logs")
    assert said["title"] == "Run all did not finish"
    assert "a file is missing" in said["text"]
    assert "Check the folder." in said["info"] and "/tmp/logs" in said["info"]


def test_a_failed_run_all_opens_the_dialog(window):
    window.run_ctl._running_all = True
    window.run_ctl._on_trial_failed("a file it needs is not there.")
    assert window.told and window.told[0][0] == "Run all did not finish"
    assert window.run_ctl._running_all is False


def test_a_failed_trial_stays_in_the_status_bar(window):
    window.run_ctl._on_trial_failed("boom")
    assert window.told == []
    assert "Trial run failed" in window.statusBar().currentMessage()


def test_an_early_return_does_not_leave_the_flag_armed(window):
    """Run all 被 lint 擋下（沒開跑）之後，下一次試跑失敗不該跳 Run all 的框。"""
    window.dataset = None                  # 沒資料 → run_trial 提早 return
    window.run_ctl._running_all = True
    assert window.run_ctl.run_trial(2, sync=True) is False
    assert window.run_ctl._running_all is False


def test_a_failed_write_opens_the_dialog(window):
    window.run_ctl._on_outputs_failed("no permission to use report.xlsx")
    assert window.told and window.told[0][0] == "The outputs were not written"

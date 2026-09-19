# F117 G9：關窗要把**每一條**背景執行緒收乾淨（2026-09-20）。
"""走查看到的是關程式時 Qt 印的一行：

    QThread: Destroyed while thread is still running

那不是一句警告，是**未定義行為**（最壞是當掉）。查出來的原因很簡單：
`studio.closeEvent` 裡列了一張六個 worker 的表，而視窗身上有**八個** ——
`region_check_worker` 與 `calibrate_worker` 從來沒有被停過。而它只在那兩個
功能真的被按過的那一次出現，所以平常看不到。

⚠ **這一支守的不是那兩個名字，是「一個都不准漏」。** 名單現在由
`workers.owned_workers()` 自己找出來，而這裡問的是「找出來的每一個都被停
了嗎」—— 加第九個 worker 的人什麼都不必記得。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication            # noqa: E402

from d4t.ui import studio as studio_mod               # noqa: E402
from d4t.ui import theme as theme_mod                 # noqa: E402
from d4t.ui import workers as workers_mod             # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture()
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    if not win.isHidden():
        win.close()


# --------------------------------------------------------------------------- #
# 1. 一條都不准漏
# --------------------------------------------------------------------------- #
def test_it_finds_every_thread_the_window_owns(window):
    """⚠ **八個，不是六個。** 兩個 controller 身上也有。"""
    found = {type(w).__name__ for w in workers_mod.owned_workers(window)}
    assert {"PreviewWorker", "TrialWorker", "DatasetLoadWorker",
            "OutputWorker", "RegionCheckWorker", "CalibrateWorker",
            "ThumbWorker"} <= found, found
    # 去重：`dataset_worker` 與 `attach_ctl.pair_worker` 是同一個型別的兩個
    # 物件，兩個都要收 —— 但同一個物件不准收兩次。
    got = workers_mod.owned_workers(window)
    assert len({id(w) for w in got}) == len(got)
    assert len(got) >= 8, [type(w).__name__ for w in got]


def test_closing_the_window_stops_all_of_them(window, monkeypatch):
    """**這就是那一行 `QThread: Destroyed…` 的測試。**

    問的是「每一個 `owned_workers` 找得到的都被 `stop()` 了」，不是「那六個
    被停了」—— 前者會在有人加第九個的那天紅，後者不會。
    """
    stopped = []
    for worker in workers_mod.owned_workers(window):
        monkeypatch.setattr(worker, "stop",
                            lambda *a, _w=worker, **k: stopped.append(_w))
    expect = [id(w) for w in workers_mod.owned_workers(window)]
    window.close()
    assert [id(w) for w in stopped] == expect, "有 worker 沒被停"


def test_the_windows_close_before_the_threads_stop(window, monkeypatch):
    """⚠ **順序是刻意的**：視窗先關、執行緒後停。

    反過來的話，最後一批結果會送到一個正在拆的 widget 上 —— 那是 Qt 裡最難
    重現的一種當機。
    """
    order = []
    window.results.show()          # 讓它真的在名單裡
    for dlg in workers_mod.window_children(window):
        monkeypatch.setattr(dlg, "close", lambda *a: order.append("window"))
    for worker in workers_mod.owned_workers(window):
        monkeypatch.setattr(worker, "stop", lambda *a, **k: order.append("thread"))
    window.close()
    assert order, "什麼都沒收"
    assert order.index("window") < order.index("thread"), order


def test_the_window_list_is_the_one_the_menu_uses(window):
    """子視窗的名單讀 `_open_windows()` —— **U15 那張表只有一份**。

    抄第二份出來的那份一定會漂：Windows 下拉列開得出來、而關窗時不收。
    """
    window.results.show()
    got = {id(w) for w in workers_mod.window_children(window)}
    for _, dlg in window._open_windows():
        if dlg is not None:
            assert id(dlg) in got

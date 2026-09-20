# F117 K3：一批要跑多久，畫面上說得出來（2026-09-20）。
"""走查記的是「沒有 ETA」，而底下那句話才是重點：`.I01` 一批可以到六萬顆。

「Running: 3 / 60000」答不出使用者在那一刻唯一的問題 —— **現在要不要走開去
做別的事**。三分鐘跟三小時是兩種完全不同的決定，而那個分數答不出來。

這一支守兩件事，而**第二件比第一件重要**：

1. 講得出來的時候要講，而且用人話的單位（`about 4 min left`）。
2. **證據不夠的時候一個字都不准講。** 第一顆要載影像、暖快取、開 worker，
   它比後面每一顆都慢好幾倍 —— 拿它去乘六萬會生出一個大到荒謬的數字，而一個
   一看就知道是假的估計，會讓使用者連後面真的那個也不信。
"""
from __future__ import annotations

import sys
import time
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from d4t.ui.run_controller import (                      # noqa: E402
    ETA_MIN_DONE, ETA_MIN_SECONDS, RunController, eta_text,
)


def _eta(done, total, elapsed):
    """跑了 ``elapsed`` 秒、做完 ``done`` 顆的時候，那一行寫什麼。"""
    return eta_text(done, total, time.time() - elapsed)


# --------------------------------------------------------------------------- #
# 1. 不猜
# --------------------------------------------------------------------------- #
def test_it_says_nothing_before_it_has_seen_enough_defects():
    """⚠ 頭幾顆不能算數 —— 它們扛著整批的暖機成本。"""
    assert _eta(ETA_MIN_DONE - 1, 60000, 30.0) == ""


def test_it_says_nothing_in_the_first_couple_of_seconds():
    """幾顆小圖在一秒內跑完，除出來的速率是量測誤差不是速率。"""
    assert _eta(ETA_MIN_DONE + 50, 60000, ETA_MIN_SECONDS / 2) == ""


def test_it_says_nothing_when_the_clock_never_started():
    """⚠ `_trial_t0` 是 `0.0` 的時候（同步那條路沒有設它）不准算。

    `0.0` 減出來的「已經跑了」是 1970 年到現在 —— 那會生出一個以年為單位的
    估計，而它會出現在一個本來好好的畫面上。
    """
    assert eta_text(100, 60000, 0.0) == ""
    assert eta_text(100, 60000, None) == ""


def test_the_last_defect_does_not_get_an_estimate():
    """跑完了就不要再講「還要多久」—— 那一行接下來會被結果換掉。"""
    assert _eta(60000, 60000, 600.0) == ""
    assert _eta(60001, 60000, 600.0) == ""


# --------------------------------------------------------------------------- #
# 2. 講得出來的時候，講人話
# --------------------------------------------------------------------------- #
def test_a_long_batch_reads_in_minutes():
    """六萬顆跑了 600 秒做完兩萬顆 → 還要 1200 秒 = 20 分鐘。"""
    assert _eta(20000, 60000, 600.0) == "about 20 min left"


def test_a_short_wait_reads_in_seconds():
    """⚠ 一分鐘以內講「about 1 min」等於叫人去泡咖啡，而它 40 秒就好了。"""
    assert _eta(100, 200, 40.0) == "about 40 s left"


def test_seconds_are_rounded_so_the_number_stops_twitching():
    """⚠ **秒是取整到 5 的** —— 一個每半秒變一次的數字讀起來像壞掉的。

    那個 5 買到的是「同一句話要站得住幾秒」：進度每跑一顆就回報一次，而
    六萬顆的批次一秒會回報好幾次。
    """
    for elapsed in (20.0, 20.4, 21.0, 25.0, 30.0):
        text = _eta(100, 300, elapsed)
        assert text.endswith(" s left"), text
        assert int(text.split()[1]) % 5 == 0, text
    # 相鄰兩次回報（真值差不到一秒）講的是同一句話。
    assert _eta(100, 300, 20.0) == _eta(100, 300, 20.4)


def test_a_very_long_one_switches_to_hours():
    """⚠ `about 240 min left` 要在腦裡除一次，而使用者只想知道是不是今天。"""
    assert _eta(1000, 60000, 600.0) == "about 9.8 h left"


def test_the_tail_end_does_not_promise_a_number():
    """剩不到十秒的時候報一個數字沒有意義 —— 講完它就跑完了。"""
    assert _eta(195, 200, 39.0) == "almost done"


def test_more_done_means_less_left():
    """同一個速率下，做得越多剩得越少 —— 這是這支函式唯一的物理。"""
    seen = [_eta(n, 60000, n / 10.0) for n in (1000, 10000, 30000, 50000)]
    assert seen == sorted(seen, key=lambda s: -_minutes(s))


def _minutes(text):
    n = float(text.split()[1]) if text.split()[1][0].isdigit() else 0.0
    return n * 60 if " h " in text else n if "min" in text else n / 60


# --------------------------------------------------------------------------- #
# 3. 那一行真的長這樣
# --------------------------------------------------------------------------- #
class _Win:
    def __init__(self):
        self.said = ""
        self.bar = ()

    def _progress_set(self, done, total, fmt):
        self.bar = (done, total, fmt)

    def _status(self, text, *a):
        self.said = text


def _line(done, total, elapsed):
    """⚠ 不建 `RunController`（它是 QObject，而這裡只要那一行字）。

    用一個假的 self 直接叫那個方法 —— 要的是**畫面上那一串**，不是 Qt。
    """
    win = _Win()
    me = types.SimpleNamespace(w=win, _trial_t0=time.time() - elapsed)
    RunController._on_trial_progress(me, done, total)
    return win


def test_the_status_line_carries_both_the_count_and_the_time():
    win = _line(20000, 60000, 600.0)
    assert win.said == "Running: 20000 / 60000  ·  about 20 min left"
    assert win.bar == (20000, 60000, "%v / %m defects")


def test_the_count_survives_when_there_is_no_estimate_yet():
    """⚠ 沒有估計的時候那一行要乾淨 —— 不准留一個孤零零的分隔點。"""
    win = _line(2, 60000, 0.5)
    assert win.said == "Running: 2 / 60000"
    assert "·" not in win.said

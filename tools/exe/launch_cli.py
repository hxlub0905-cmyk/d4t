# d4t.exe 的進入點 — authored 2026-10-02 (F125).
"""PyInstaller 用的啟動腳本：``d4t.exe`` ＝ ``python -m d4t``。

不直接拿 ``d4t/__main__.py`` 當進入腳本，是為了讓**第一句**可以是
``multiprocessing.freeze_support()``：Windows 的 spawn 是「再跑一次這個 exe」，
``run_batch`` 開 N 個 worker 就會再開 N 次這支程式 —— ``freeze_support()`` 認出
自己是 worker 時就只做 worker 的事然後結束。少了它的症狀是 ``--workers 4`` 開出
四個一樣的程式。這一行的位置有測試守（``tests/test_build_exe.py``）。
"""
import multiprocessing
import sys

multiprocessing.freeze_support()


def _run() -> int:
    from d4t.__main__ import main
    return int(main())


if __name__ == "__main__":
    sys.exit(_run())

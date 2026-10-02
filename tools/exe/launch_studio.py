# d4t-studio.exe 的進入點 — authored 2026-10-02 (F125).
"""PyInstaller 用的啟動腳本：``d4t-studio.exe`` ＝ ``python -m d4t gui``，但沒有 console。

* 第一句 ``multiprocessing.freeze_support()`` —— 理由見 ``launch_cli.py``；在 GUI
  這一邊更要緊：Studio 的試跑是從 QThread 開 spawn worker，少了這一行每個 worker
  都會再開一個 Studio 視窗。
* ``console=False`` 的 exe 沒有 stdout／stderr（``sys.stdout is None``）。``print``
  碰到 ``None`` 會安靜略過，但 ``logging`` 的 StreamHandler 與任何 ``.write`` 不會
  —— 所以先把它們導到 devnull。當機紀錄本來就寫檔（``ui/crashlog.py``），不靠 console。
"""
import multiprocessing
import os
import sys

multiprocessing.freeze_support()


def _run() -> int:
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    from d4t.ui.app import main
    return int(main(sys.argv))


if __name__ == "__main__":
    sys.exit(_run())

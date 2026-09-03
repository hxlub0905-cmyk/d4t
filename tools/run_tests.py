#!/usr/bin/env python3
# d4t 測試跑法 — authored 2026-08-15，2026-09-03 收進 main（F84）。
"""**每個測試檔各自一個行程**跑完全套，並印出最慢的幾個。

    python tools/run_tests.py                # 全套
    python tools/run_tests.py --fast         # 略過 UI（開 Qt 視窗的那些）
    python tools/run_tests.py tests/test_recipe.py tests/test_steps.py

為什麼需要這支
--------------
**一、一個行程跑整套會慢到沒有人想跑。** 差距在 Qt：UI 測試前面每一支建立的
``QWidget`` 都還掛在同一個 ``QApplication`` 底下 —— Qt 物件不會因為測試結束
就消失，於是後面的測試每開一個視窗都要跟愈來愈多的殘留物一起做版面計算。
時間是**超線性**成長的，所以檔案愈多差距愈大。行程結束就全部歸零，
分開跑因此不只是「平行」，是把那個累積整個拿掉。

實測（同一套測試、同一台機器）：

=========================================  =================  ==============
                                           一個行程            逐檔各一行程
=========================================  =================  ==============
2026-08-15（25 支 UI 測試檔）               > 11 分鐘           約 2.5 分鐘
2026-08-24（CI runner，`.github` 有記）      **1:39:09**        約 7 分鐘
=========================================  =================  ==============

⚠ **UI 測試檔已經從 25 支長到 84 支**（2026-09-03），而上面那條曲線是超線性的
—— 這支的理由只會愈來愈強，不會過期。

這不是繞過問題 —— 每個檔案本來就該獨立，共用行程只是 pytest 的預設值。

**二、`CLAUDE.md` 教的那一行在家用機上跑不動。** 那裡寫的是

    for f in tests/test_ui_*.py; do pytest -q "$f"; done

而那是 **bash**；家用機是 Windows（同一節上面就寫著 ``.venv\\Scripts\\activate``）。
一份寫下來的程序，在它要服務的那台機器上跑不動 —— 這支是 stdlib-only 的
Python，兩邊都能跑。

⚠ **這支不取代 CI。** CI **也是**逐檔跑的（2026-08-24 起分兩批：核心一次
``pytest -q --ignore-glob="*test_ui_*"``，UI 一個檔案一個行程），理由與數字
見 ``.github/workflows/ci.yml`` 的註解。這支是給**開發迴圈**用的：同一個
做法、加上逐檔計時與「最慢的幾個」，而且失敗全部收集到最後一起印。

stdlib-only（跟 ``tools/`` 其他腳本同一條規矩，見 ``AGENTS.md``）。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(REPO, "tests")

#: 開 Qt 視窗的測試檔前綴。**判準是檔名**，跟 CI 的 ``--ignore-glob`` 與
#: ``AGENTS.md`` §5 講的是同一條線 —— 三個地方要一起改，不然 ``--fast``
#: 會漏掉一支真的會開視窗的檔案，而症狀是「本機很快、CI 很慢」。
#: （這裡以前寫著「跟 `tests/conftest.py` 的 slow marker 同一條規則」，
#: 而那個 marker 已經不存在了。）
UI_PREFIX = "test_ui_"


def test_files(only_fast: bool = False):
    """``tests/test_*.py`` 依檔名排序；``only_fast`` 時略過 UI 那些。"""
    out = []
    for name in sorted(os.listdir(TESTS)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        if only_fast and name.startswith(UI_PREFIX):
            continue
        out.append(os.path.join("tests", name))
    return out


def run_one(path: str, env: dict) -> tuple:
    """跑一個檔案，回 ``(秒數, returncode, 最後一行輸出)``。"""
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", path],
        cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    secs = time.time() - t0
    text = proc.stdout.decode("utf-8", "replace").strip()
    last = text.splitlines()[-1] if text else ""
    return secs, proc.returncode, text, last


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", help="要跑哪幾個（預設：全部）")
    ap.add_argument("--fast", action="store_true",
                    help="略過 UI 測試檔（開 Qt 視窗的那些，佔全套七成時間）")
    ap.add_argument("--slowest", type=int, default=8, metavar="N",
                    help="最後印出最慢的 N 個檔案（預設 8）")
    a = ap.parse_args(argv)

    files = a.files or test_files(only_fast=a.fast)
    if not files:
        print("找不到測試檔。")
        return 2

    env = dict(os.environ)
    # Linux/macOS 的 headless 需要它；Windows 上多設這個變數無害。
    env.setdefault("QT_QPA_PLATFORM", "offscreen")

    timings = []
    failed = []
    t0 = time.time()
    for i, path in enumerate(files, 1):
        secs, rc, text, last = run_one(path, env)
        timings.append((secs, path))
        mark = "✓" if rc == 0 else "✗"
        print("%s [%d/%d] %-52s %5.1fs  %s"
              % (mark, i, len(files), path, secs, last), flush=True)
        if rc != 0:
            failed.append((path, text))

    total = time.time() - t0
    print("\n最慢的 %d 個：" % a.slowest)
    for secs, path in sorted(timings, reverse=True)[:a.slowest]:
        print("  %5.1fs  %s" % (secs, path))

    if failed:
        print("\n%d 個檔案有測試沒過：" % len(failed))
        for path, text in failed:
            print("\n" + "=" * 70 + "\n" + path + "\n" + "=" * 70)
            print(text)
        print("\n總共 %.0f 秒，**%d 個檔案紅了**。" % (total, len(failed)))
        return 1

    print("\n總共 %.0f 秒，%d 個檔案全綠。" % (total, len(files)))
    if a.fast:
        print("（--fast 略過了 UI 測試 —— commit 之前請跑一次不加 --fast 的。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# pyright 那道關 — authored 2026-09-09.
"""跑 pyright（basic）掃 ``d4t/core``，錯誤數不准超過這裡寫的上限。

為什麼是「上限」不是「零」
--------------------------
第一次跑就是 136 條，而它們大部分是真的可疑（``"execute" is not a known
attribute of "None"`` 那種 —— 一個 Optional 沒檢查就用）。一次修完不是這一輪
的事，但**從今天起不准變多**：這跟 ``tests/test_size_ceilings.py`` 是同一把尺
的形狀 —— 上限寫在這裡、調高要在 commit 訊息裡說一句為什麼、掉下去要把上限
跟著降（不然那段距離是白送的成長空間）。

為什麼只掃 ``d4t/core``
-----------------------
UI 那一半的 PySide6 stub 品質參差，先開會得到一堆「Qt 的 overload 對不上」；
core 是數字算對不對的地方，先守它。

⚠ **只裝在開發機**（``dev`` extra）。pyright 是 npm 套件包成 pip，第一次跑會
下載 node —— 廠內離線那條路一個位元都不受影響。

    python tools/typecheck.py           # 跑一次，超過上限回非零
    python tools/typecheck.py --show    # 順便把每一條印出來
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

#: 錯誤數上限。**調高要說為什麼；降下去要跟著改。**
#: 2026-09-09：第一次跑，136（pyright 1.1.408，basic，pythonVersion 3.9，只掃 d4t/core）。
#: 2026-09-17（F105）：128 —— `template._measure_period` 從 5-tuple 改成 dataclass、
#: `GoldenCell.origin` 放寬成 float，順手把那一帶的 Optional 算術寫清楚了。
CEILING = 128

#: 反向門檻：掉到 ``上限 - SLACK`` 以下就要求把上限降下來（同 size_ceilings 的 2%）。
SLACK = max(3, CEILING // 50)

TARGET = "d4t/core"


def run_pyright(show: bool) -> int:
    exe = shutil.which("pyright")
    if exe is None:
        print("✗ 找不到 pyright。開發機：pip install pyright（或 pip install -e .[dev]）。")
        return -1
    proc = subprocess.run([exe, "--outputjson", TARGET],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        print("✗ pyright 沒有吐出 JSON（上面是它的原始輸出）。")
        return -1
    errors = [d for d in data.get("generalDiagnostics", []) if d.get("severity") == "error"]
    if show:
        for d in errors:
            r = d.get("range", {}).get("start", {})
            print("  %s:%s:%s  %s" % (d.get("file"), r.get("line", 0) + 1,
                                      r.get("character", 0) + 1, d.get("message")))
    return len(errors)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="pyright（basic）掃 d4t/core，錯誤數不准超過上限。")
    ap.add_argument("--show", action="store_true", help="把每一條錯誤印出來")
    a = ap.parse_args(argv)
    n = run_pyright(a.show)
    if n < 0:
        return 2
    if n > CEILING:
        print("✗ pyright：%d 條錯誤，超過上限 %d（+%d）。" % (n, CEILING, n - CEILING))
        print("  修掉新加的那幾條；真的該漲 → 改 tools/typecheck.py 的 CEILING 並在 commit 訊息說為什麼。")
        return 1
    if n <= CEILING - SLACK:
        print("△ pyright：只剩 %d 條，而上限還留在 %d —— 把 CEILING 改成 %d，把成果鎖住。"
              % (n, CEILING, n))
        return 1
    print("✓ pyright：%d 條錯誤（上限 %d）。" % (n, CEILING))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

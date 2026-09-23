"""Golden Cell generator —— 從一張 Golden Cell 產一整批模擬資料。

獨立的進入點：``python main.py``（或 ``python -m simgenapp``）。
"""
from __future__ import annotations

import sys


def main() -> int:
    from simgenapp.ui.gc_generator import run
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

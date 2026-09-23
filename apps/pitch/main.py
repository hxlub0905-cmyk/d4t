"""Pitch helper —— 丟一張圖進去，回答它的 cell period。

獨立的進入點：``python main.py``（或 ``python -m pitchapp``）。
"""
from __future__ import annotations

import sys


def main() -> int:
    from pitchapp.ui.pitch_helper import run
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())

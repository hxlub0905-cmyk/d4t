# CLI 在 cp950 console 上不准 crash（F20 §5 記下、2026-08-24 修）
"""廠內機器的 console 是 cp950，而 CLI 印 ✓ / ✗ / △ / →（cp950 沒有這幾個字）。

修之前的症狀特別壞：跑完 48 顆、CSV 也寫好了，使用者看到的卻是一條
UnicodeEncodeError 的 traceback —— 在**成功**的那一刻。而那正是「工具壞了」
的樣子，不是「console 字碼舊」的樣子。

用 subprocess 測（不是 monkeypatch sys.stdout）：`PYTHONIOENCODING=cp950`
讓子行程的 stdout 真的是 strict cp950 —— 跟廠內那台機器一模一樣。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RECIPE = REPO / "tests" / "fixtures" / "recipes" / "dual_route_basic.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ,
               PYTHONIOENCODING="cp950",
               PYTHONPATH=str(REPO))
    return subprocess.run(
        [sys.executable, "-m", "d4t", *args],
        cwd=str(REPO), env=env,
        capture_output=True, timeout=120)


def test_validate_survives_a_cp950_console():
    """`validate` 成功時印「✓ 無問題」—— ✓ 就是炸掉的那個字。"""
    got = _run_cli("validate", str(RECIPE))
    assert b"UnicodeEncodeError" not in got.stderr, got.stderr.decode("utf-8", "replace")
    assert got.returncode == 0, got.stderr.decode("utf-8", "replace")
    # 中文照常（cp950 本來就有中文）,印不出的字換成 ?,兩件事都要成立
    assert "無問題".encode("cp950") in got.stdout


def test_steps_listing_survives_a_cp950_console():
    got = _run_cli("steps")
    assert b"UnicodeEncodeError" not in got.stderr
    assert got.returncode == 0

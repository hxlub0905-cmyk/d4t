# pytest 根設定 — authored 2026-07-29.
"""讓 ``pytest``（不加 ``python -m``）也找得到 ``d4t`` 套件。

為什麼需要這個檔
----------------
``python -m pytest`` 會把**目前工作目錄**放進 ``sys.path``，``pytest`` 不會。
測試都是從 repo 根目錄跑的，所以兩種寫法的差別就是 ``import d4t`` 成不成立：

===========================  ==========================================
``python -m pytest -q``      CWD 進 sys.path → 找得到 d4t ✓
``pytest -q``                CWD **不**進 sys.path → ModuleNotFoundError ✗
===========================  ==========================================

CI（``.github/workflows/ci.yml``）跑的是後者，所以整套測試在 CI 上是
**收集階段就中斷**，一個都沒真的跑到。本機開發用前者，於是這件事一直沒被發現。

修法：pytest 在載入 conftest 時，會把該 conftest 所在目錄（= repo 根目錄）
插進 ``sys.path``。所以這個檔案存在本身就是修正 —— 底下再明確補一次，
讓意圖看得出來，也不依賴 pytest 的 import-mode 細節。

比 ``pip install -e .`` 好在哪：廠內機器不一定裝得了可編輯安裝
（見 ``docs/NO-GIT-SETUP.md``：使用者是解壓 zip 直接跑），
所以「從 repo 根目錄直接跑得動」是這個專案要維持的性質。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# tools/ 不是套件，但有幾支測試要 import make_sample / make_sample_rsem
# 來產合成資料（tools 本身刻意保持 stdlib-only 的單檔腳本）。
_TOOLS = _ROOT / "tools"
if _TOOLS.is_dir() and str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

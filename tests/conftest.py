# 測試共用設定。
"""**測試裡不准跳出 modal 對話框。**

Studio 關窗時會問「還沒存要不要存」（F7-16）。那在真的使用時是必要的，但在
headless 測試裡，一個 modal 對話框不會讓測試失敗 —— 它會讓測試**永遠停在那裡**，
而且沒有任何訊息。那種卡住是最難查的一種，所以在這裡一次關掉。

要驗那個對話框本身的測試（`test_ui_f7_16_safety_net.py`）自己把它打開，
驗完再關回去。

刻意**不**在這裡 import Qt：core 的測試不該因為一個 conftest 就把 PySide6 拉
進來。等到某個 UI 測試把 `adept.ui.studio` 載進來之後，這個 fixture 才動它。
（fixture 的建立順序保證得了這件事：module-scoped 的 `qapp` 比 function-scoped
的 autouse fixture 早建立，而 `qapp` 就是 import Studio 的那一步。）
"""
from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _no_modal_dialogs_in_tests():
    mod = sys.modules.get("adept.ui.studio")
    if mod is not None:
        mod.StudioWindow.PROMPT_ON_CLOSE = False
    yield


# --------------------------------------------------------------------------- #
# `slow` marker（2026-08-15）
# --------------------------------------------------------------------------- #
#: 開 Qt 視窗的測試檔。實測它們佔全套時間的絕大部分：非 UI 的 50 幾個檔案
#: 加起來十幾秒，而 UI 的每一個檔案都要各自把 QApplication 與 Studio 主視窗
#: 建起來。在雲端容器上這件事比家用機慢一個數量級。
_SLOW_PREFIXES = ("test_ui_",)

#: 不開視窗但一樣慢的：跑整批 defect、開子行程、或把整個 repo 打包一次。
_SLOW_FILES = frozenset({
    "test_e2e_dual_route.py",
    "test_e2e_die_to_die.py",
    "test_example_recipes.py",
    "test_batch_cache.py",
    "test_batch_thread_safety.py",
    "test_offline_tools.py",
    "test_fab_probe.py",
    "test_make_sample.py",
})


def pytest_collection_modifyitems(config, items):
    """依**檔名**自動套上 ``slow``，不必在每個函式上寫 decorator。

    為什麼是自動而不是手動標：手動標的東西會漏 —— 新增一支 UI 測試檔的人
    不會想到要標它，於是 ``-m "not slow"`` 隨著時間慢慢變回全套，而且沒有人
    會發現（它只是變慢，不會變紅）。檔名規則沒有這個問題。

    ⚠ 這個 marker 說的是「這一支**慢**」，不是「這一支**不重要**」。
    CI 跑的是不加 ``-m`` 的全套（見 ``.github/workflows/ci.yml``）。
    """
    for item in items:
        name = item.path.name if hasattr(item, "path") else item.fspath.basename
        if name.startswith(_SLOW_PREFIXES) or name in _SLOW_FILES:
            item.add_marker(pytest.mark.slow)

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

# 測試共用設定。
"""**測試裡不准跳出 modal 對話框。**

Studio 關窗時會問「還沒存要不要存」（F7-16）。那在真的使用時是必要的，但在
headless 測試裡，一個 modal 對話框不會讓測試失敗 —— 它會讓測試**永遠停在那裡**，
而且沒有任何訊息。那種卡住是最難查的一種，所以在這裡一次關掉。

要驗那個對話框本身的測試（`test_ui_undo_close_and_stop.py`）自己把它打開，
驗完再關回去。

刻意**不**在這裡 import Qt：core 的測試不該因為一個 conftest 就把 PySide6 拉
進來。等到某個 UI 測試把 `d4t.ui.studio` 載進來之後，這個 fixture 才動它。
（fixture 的建立順序保證得了這件事：module-scoped 的 `qapp` 比 function-scoped
的 autouse fixture 早建立，而 `qapp` 就是 import Studio 的那一步。）
"""
from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _no_modal_dialogs_in_tests():
    mod = sys.modules.get("d4t.ui.studio")
    if mod is not None:
        mod.StudioWindow.PROMPT_ON_CLOSE = False
    yield


@pytest.fixture(autouse=True)
def _no_view_animations_in_tests():
    """**測試裡不准跑視角動畫**（F80）。

    跟上面那支「不准跳 modal」是同一種東西：動畫不會讓測試失敗，它會讓
    「按了 fit 之後縮放是多少」變成一個**跟時間有關**的問題 —— 於是那些測試開始
    間歇性變紅，然後被關掉。

    要驗動畫本身的測試（`test_ui_canvas_animation.py`）自己把它打開，驗完關回去。

    刻意**不**在這裡 import Qt：core 的測試不該因為一個 conftest 就把 PySide6
    拉進來（同上面兩支的理由）。
    """
    mod = sys.modules.get("d4t.ui.canvas")
    before = None if mod is None else mod.ANIMATE
    if mod is not None:
        mod.ANIMATE = False
    yield
    mod = sys.modules.get("d4t.ui.canvas")
    if mod is not None and before is not None:
        mod.ANIMATE = before


@pytest.fixture(autouse=True)
def _regions_always_match_their_lines():
    """**方案 B 的常開斷言**（F42 B2）：每一次 model 改動都問一次
    「每一格區域參數是不是正好等於線說的」。

    為什麼是一條常開的斷言而不是幾條測試：方案 B 的整個安全性建立在
    「用哪個區域只有一個家（那條線）」上，而破壞它的方式是**加一條新路徑**
    —— 一個忘了水合的新入口 —— 不是改壞既有的那五條。既有測試不會走那條還
    不存在的路徑，所以只有「每一次改動都問一次」抓得到。

    跟上面那一支同一個理由不 import Qt：`d4t.ui.viewmodel` 進不進來由測試
    自己決定（核心那一輪不該因為一個 conftest 就把 UI 拉進來）。
    """
    mod = sys.modules.get("d4t.ui.viewmodel")
    before = None if mod is None else mod.RecipeModel.CHECK_REGION_INVARIANT
    if mod is not None:
        mod.RecipeModel.CHECK_REGION_INVARIANT = True
    yield
    mod = sys.modules.get("d4t.ui.viewmodel")
    if mod is not None:
        mod.RecipeModel.CHECK_REGION_INVARIANT = (
            True if before is None else before)


@pytest.fixture(autouse=True)
def _the_theme_does_not_leak_into_the_next_test():
    """一條測試切換過的主題，收工時要收回來。

    ``theme.TOKENS`` 是**就地**更新的模組層 dict（那是刻意的 —— 各模組都
    ``import`` 過它了，換掉物件會讓它們抱著舊的那一份）。代價是它變成一份
    跨測試共享的全域狀態：40 幾個 UI 測試檔在動它，而**忘記還原不會在當場
    失敗**，只會讓「下一條測試看到的是什麼顏色」變成檔案順序的函數。

    真的發生過（2026-08-24 這一輪查出來的）：`test_ui_gds_panel.py` 的
    module fixture 把主題切成 dark 沒還原，字母序排在 `test_ui_widgets.py`
    前面，於是 `test_theme_is_neutral_and_flat` 讀到的是 dark 那一組 ——
    **一個檔案一個行程跑（開發者的做法）全綠，一個行程跑整套（CI 的做法）
    紅**，而 CI 因此紅了三週沒有人看得出原因。

    這一支收的是 function scope 的洩漏。module/session scope 的 fixture 要
    自己在 ``yield`` 之後還原（`test_ui_gds_panel.py` 就是那樣做的）——
    它們比這一支早建立、比它晚拆除，這裡接不到。

    刻意用 ``sys.modules.get``：核心那一輪不該因為一個 conftest 就把
    `d4t.ui.theme` 載進來（同上面那一支的理由）。
    """
    theme = sys.modules.get("d4t.ui.theme")
    if theme is None:
        yield
        return
    before = theme.current_theme()
    yield
    if theme.current_theme() != before:
        theme.set_theme(before)


def wire_up(model, node_id: str) -> str:
    """把這張卡的每一格輸入接上它的預設流（F10）。

    F10 起**剛加進來的卡沒有來源** —— 畫布上沒有線，那它就沒有輸入，跑起來會
    被擋下來（那正是使用者要的：「一張卡片剛被 new add 時，前後應該都是空的
    乾淨的」）。所以測試裡凡是「先放一張卡、再看它算出什麼」的場景，中間都少
    了使用者真的會做的那一步：**把線拉過去**。

    這個 helper 就是那一步的最短寫法 —— 每一格輸入接上它 ``ParamSpec`` 宣告的
    預設流，等同使用者照最直覺的方式接完。要接別條流的測試自己 ``set_param``。
    """
    from d4t.core.pipeline import get_step

    node = model.nodes[str(node_id)]
    for spec in get_step(node.step).input_specs():
        if spec.default:
            model.set_param(str(node_id), spec.name, spec.default)
    return str(node_id)


def first_source(window, step: str = "load_patch") -> str:
    """畫布上那張**輸入卡**的 id（沒有就加一張）。

    F11 Enhance-4 之後開窗是**空白畫布**（使用者定調：「Load image 卡片改成預設
    沒有，add 才會出現」）—— 所以 `window.model.node_order[0]` 這個寫法在還沒
    載入資料的測試裡會 IndexError。

    這個 helper 就是使用者真的會做的那一步（從卡片庫拉一張輸入卡進來）的最短
    寫法。載過資料的測試不必用它：`load_dataset_path` 會照資料的型別補上那一張
    （`studio._adopt_source_for`），所以 `node_order[0]` 仍然成立。
    """
    if not window.model.node_order:
        window._on_add_requested(str(step))   # 卡片庫按下去走的正是這一條
    return window.model.node_order[0]

# PR-2：info 級別在畫布上的樣子 —— 不畫點、輸給 error/warning。
"""`info` 是「值得知道、但連 warning 都算不上」：畫布**不**為它畫圓標
（畫了琥珀點就跟 warning 分不開，常駐的點會被學會忽略——推廣鐵則），
它只住在卡片 tooltip 與 CLI 清單（CLI 面在 `test_glv_kind_lints.py`）。
run 前的攔截照舊只看 error、run 後訊息只收 warning —— studio 的兩個字面
過濾天然忽略 info，這裡鎖住排序那一半（error > warning > info）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from d4t.ui.canvas import badge_paints  # noqa: E402


def test_the_badge_paints_errors_and_warnings_but_not_info():
    assert badge_paints("error") is True
    assert badge_paints("warning") is True
    assert badge_paints("info") is False


def test_node_problems_rank_error_over_warning_over_info(qapp=None):
    """同一張卡好幾條發現時，tooltip 只留最嚴重的那一則。

    以前的比較只認得兩級（「error 蓋過 warning」）—— info 進來之後那句話
    會讓 info 蓋過 warning，所以改成 rank。這裡不開整個 Studio：排序邏輯
    抽不出來（method 在 StudioWindow 上），就用一個假 model 餵它。
    """
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme as theme_mod
    from d4t.ui.studio import StudioWindow

    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")

    class _Issue:
        def __init__(self, level, node_id, title):
            self.level, self.node_id = level, node_id
            self.title, self.detail = title, title
            self.code = "x"

    class _Model:
        dirty = False        # 關窗提示會問（PROMPT_ON_CLOSE 之外的那條路）

        def validate(self):
            return [_Issue("info", "n1", "fyi"),
                    _Issue("warning", "n1", "careful"),
                    _Issue("info", "n2", "fyi only"),
                    _Issue("warning", "n3", "careful"),
                    _Issue("error", "n3", "broken")]

    win = StudioWindow(show_welcome_on_start=False)
    try:
        win.model = _Model()
        got = win._node_problems()
        assert got["n1"] == ("careful", "warning"), "warning 蓋過 info"
        assert got["n2"] == ("fyi only", "info"), \
            "只有 info 的卡也要進表（tooltip 要看得到），只是不畫點"
        assert got["n3"] == ("broken", "error"), "error 蓋過 warning"
    finally:
        win.close()

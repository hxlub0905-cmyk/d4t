# PR-2（2b）：`region_words` —— 埠 hover / GLV 標題 / Profile 圖例的唯一字典。
"""三個地方講同一顆埠，字只能有一份（CLAUDE.md §0）。這裡鎖三方同源、
`role_of` 的四個案例、以及 core 與 UI 對 kind 分群的一致性。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from d4t.core.pipeline.step import PATCH_KINDS, SINGLE_IMAGE_KINDS  # noqa: E402
from d4t.ui import region_words, scope  # noqa: E402
from d4t.ui.region_words import (  # noqa: E402
    ROLE_ALL, ROLE_CENTER, ROLE_OTHERS, role_of,
)


def test_role_of_reads_the_declared_suffixes():
    assert role_of("epi") == ROLE_ALL
    assert role_of("epi_center") == ROLE_CENTER
    assert role_of("epi_others") == ROLE_OTHERS
    # `<n>_center_others` 那種怪名（REF_OTHERS 的動機失敗案例）照後綴讀：
    # 最後一節是 _others，就當 others —— 不做更聰明的猜測。
    assert role_of("epi_center_others") == ROLE_OTHERS
    assert role_of("") == ROLE_ALL


def test_every_role_has_a_hover_sentence():
    for role in (ROLE_ALL, ROLE_CENTER, ROLE_OTHERS):
        assert region_words.PORT_HOVER[role].strip()


def test_the_glv_title_and_the_hover_share_one_home():
    """GLV 標題的意圖語言必須是這本字典的字 —— 不是自己再寫一句。"""
    from d4t.ui.inspectors import GlvInspector

    named = GlvInspector._intent_name("epi_center")
    assert region_words.INTENT_PHRASE[ROLE_CENTER] in named
    assert "epi_center" in named, "原名要括號保留（對得回畫布上那顆埠）"
    assert GlvInspector._intent_name("epi") == "epi", "沒有意圖語言就用原名"


def test_the_legend_text_lives_here_too():
    import inspect

    from d4t.ui import widgets

    src = inspect.getsource(widgets.ProfilePanel.paintEvent)
    assert "LEFT_OUT_LEGEND" in src, \
        "Profile 圖例要引用 region_words.LEFT_OUT_LEGEND，不是自己抄一句"
    assert region_words.LEFT_OUT_LEGEND.strip()


def test_the_ui_and_the_core_agree_on_the_kind_grouping():
    """core 的 PATCH/SINGLE 分群要剛好蓋滿 scope.SUPPORTED_KINDS ——
    第五種 kind 出現時兩邊一起紅，而不是安靜地漏掉分群。"""
    assert set(PATCH_KINDS) | set(SINGLE_IMAGE_KINDS) \
        == set(scope.SUPPORTED_KINDS)

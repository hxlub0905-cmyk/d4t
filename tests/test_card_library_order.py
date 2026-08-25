# 卡片庫由上而下的順序（F29，2026-08-25）。
"""**使用者看到的第一張卡是哪一張** —— 這件事以前沒有任何一條測試問過。

2026-08-25 使用者說「Measure 的 card 順序幫我改命名&重排：GLV → CD →
Focus index」。那一輪照著改了 ``d4t/core/steps/__init__.py`` 的 import 順序，
還在那裡寫下「卡片庫裡看到的先後住在這三行」—— **而畫面上一格都沒有動**：
`list_steps` 同一類裡是照 ``key`` 排的（字母序 = CD、Focus index、GLV）。
整個改動看起來完成了，全套測試也全綠。

所以這一份釘的是**順序本身**，不是「有沒有這張卡」：

* 使用者點名的那三張，照他點名的順序；
* 每一段裡的順序 = 註冊順序 = ``steps/__init__.py`` 的 import 順序
  = **資料流過的順序**（load → normalize → … → measure → output）。
  對不會寫 code 的製程工程師來說那是唯一看得懂的順序，而字母序把
  ``align`` 排在 ``normalize`` 前面。
"""
from __future__ import annotations

import d4t.core.steps  # noqa: F401 — registration side-effect
from d4t.core.pipeline.step import REGISTRY, GROUP_ORDER, list_steps


def order_in(group: str):
    return [s.key for s in list_steps() if getattr(s, "group", None) == group]


def test_the_measure_stage_reads_the_way_the_user_asked_for():
    """使用者 2026-08-25：「GLV → CD → Focus index」。逐字。"""
    assert order_in("measure")[:3] == ["glv_stats", "cd_measure",
                                       "focus_quality"]


def test_find_defect_comes_after_the_three_he_named():
    """在中間插一張等於替他重排一次。"""
    assert order_in("measure") == ["glv_stats", "cd_measure", "focus_quality",
                                   "find_defect"]


def test_every_stage_reads_in_registration_order():
    """「卡片庫裡看到的先後住在 import 那幾行」—— 讓那句話是真的。"""
    reg = {key: i for i, key in enumerate(REGISTRY)}
    for group in GROUP_ORDER:
        keys = order_in(group)
        assert keys == sorted(keys, key=lambda k: reg[k]), group


def test_the_enhance_stage_is_not_alphabetical():
    """**這一條是「上面那條不是同義反覆」的證據。**

    字母序與註冊序在 Enhance 段是不同的答案（``denoise`` < ``normalize``，
    但資料是先 normalize 再 denoise）。少了這一條，上面那三條在「順序又被改回
    字母序」的那天有可能還是綠的 —— 只要剛好每一段都字母有序。
    """
    keys = order_in("enhance")
    assert keys != sorted(keys)
    assert keys[0] == "normalize"


def test_the_stages_themselves_are_in_pipeline_order():
    """段與段之間的順序住在 ``GROUP_ORDER``（卡片庫的分區照它排）。"""
    assert GROUP_ORDER[:2] == ("input", "enhance")
    assert GROUP_ORDER[-1] == "output"
    assert "measure" in GROUP_ORDER

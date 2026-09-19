# F117 B2：勾選格子上寫的是給人看的字，存的是 recipe 的鍵（2026-09-20）。
"""走查看到的：均勻度那張卡的「How even are the boxes」直接印 ``range``、
``range_pct``、``cv_pct``、``slope_x`` —— 那幾個是寫進 JSON 的鍵，不是一個
製程工程師會用的詞。

⚠ **這不是「feature 名要翻譯」**（F118 §3 明著否決了那條：`glv_max` 是使用者
在分數表達式裡要打的字，翻掉就對不起來）。這一格不一樣：``cv_pct`` 是一個
**選項**，使用者永遠不必打它 —— 他只是勾。勾的東西該寫人話。

⚠ **值跟著 box 的屬性走，不跟著它的字走。** 讀 `box.text()` 的那一版會把
「Spread (%)」存進 recipe —— 跑得完、存得下、下次開起來全錯。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication            # noqa: E402

import d4t.core.steps  # noqa: F401,E402              —— 觸發卡片註冊
from d4t.core.pipeline import get_step                # noqa: E402
from d4t.ui import theme as theme_mod                 # noqa: E402
from d4t.ui.fields import MultiChoicePicker           # noqa: E402

LABELS = {"cv_pct": "Spread (%)", "slope_x": "Tilt across"}


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


def _picker(value="cv_pct", **kw):
    return MultiChoicePicker(["range", "cv_pct", "slope_x"], value,
                             labels=LABELS, **kw)


# --------------------------------------------------------------------------- #
# 1. 字是給人看的，值是 recipe 的
# --------------------------------------------------------------------------- #
def test_the_box_shows_the_label_and_stores_the_key(qapp):
    w = _picker()
    try:
        assert [b.text() for b in w._boxes] == ["range", "Spread (%)",
                                                "Tilt across"]
        assert w.choice_names() == ["range", "cv_pct", "slope_x"]
        assert w.text() == "cv_pct", "存進 recipe 的必須是鍵"
    finally:
        w.deleteLater()


def test_reading_a_recipe_back_still_ticks_the_right_boxes(qapp):
    """`set_text` 比的也是鍵 —— 比字的話一份存好的 recipe 開起來會全空。"""
    w = _picker()
    try:
        w.set_text("slope_x,range")
        assert w.text() == "range,slope_x"
        assert [b.isChecked() for b in w._boxes] == [True, False, True]
    finally:
        w.deleteLater()


def test_a_choice_nobody_named_shows_its_key(qapp):
    """手寫 recipe 帶進來的 ``glv_q37`` 沒有人給得出白話名字。

    顯示鍵至少跟他打的字對得起來 —— 而**看不到就被靜靜刪掉**是最糟的那種
    「幫忙」（`MultiChoicePicker` 本來就守著這一條）。
    """
    w = _picker()
    try:
        w.set_choices(["range", "cv_pct", "glv_q37"], "glv_q37")
        assert "glv_q37" in [b.text() for b in w._boxes]
        assert w.text() == "glv_q37"
    finally:
        w.deleteLater()


# --------------------------------------------------------------------------- #
# 2. 那張卡真的填了
# --------------------------------------------------------------------------- #
def test_the_uniformity_choices_all_have_a_plain_name():
    """走查看到的那一排 —— 五個選項一個都不准是裸鍵。"""
    spec = next(p for p in get_step("glv_stats").describe()["params"]
                if p["name"] == "report")
    labels = spec.get("choice_labels") or {}
    assert set(labels) == set(spec["choices"]), \
        "有選項還印著 recipe 的鍵：%s" % sorted(set(spec["choices"]) - set(labels))
    for key, text in labels.items():
        assert text and text != key
        # 每一個都該配著一句說明 —— 短名字講「是什麼」，說明講「怎麼用」。
        assert (spec.get("choice_help") or {}).get(key), key

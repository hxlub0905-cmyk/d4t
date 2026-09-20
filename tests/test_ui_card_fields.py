# F117 B4：那一格寫的是給人看的字（2026-09-20）。
"""走查在 `Write charts` 卡上記了三件事，而它們是三種不同的錯：

* **`At most this many defects 0`** —— 一個特殊值沒有名字。`0` 在這裡是
  「全部」，而畫面上它就是一個 `0`：一個把上限設成零的框讀起來像「一顆都
  不寫」。那句話本來只寫在 help 裡，而**要點開 tooltip 才懂的預設值等於沒講**。
* **第五格勾選框叫 `chart`** —— recipe 的鍵漏到畫面上。那是 `CHART_CUSTOM`
  的值（檔名 `-chart.svg` 用的那個字），而 `CHART_LABELS` 裡早就寫著
  `Your own chart`，只是沒有人把它接上去。
* **`Enabled` 當 label** —— 一個通用詞佔著那一格。那一列本來長這樣：
  `Also write a table, one row per box │ ☐ Enabled`，左邊已經是一句具體的話。

⚠ 三件事各自的修法不同，而**沒有一件是「把字改短一點」**。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (                          # noqa: E402
    QApplication, QCheckBox, QSpinBox,
)

from d4t.core import steps as _steps                     # noqa: E402,F401
from d4t.core.export import uniformity_charts as charts  # noqa: E402
from d4t.core.pipeline.step import REGISTRY              # noqa: E402
from d4t.ui import theme as theme_mod                    # noqa: E402
from d4t.ui.param_form import ParamForm                  # noqa: E402

CARD = "output_uniformity"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture
def form(qapp):
    f = ParamForm()
    f.show()
    yield f
    f.deleteLater()


def _spec(card, name):
    return next(p for p in REGISTRY[card].params if p.name == name)


# --------------------------------------------------------------------------- #
# 1. `0` 有名字
# --------------------------------------------------------------------------- #
def test_the_zero_that_means_everything_has_a_name():
    assert _spec(CARD, "limit").min_label


def test_the_box_shows_the_word_instead_of_the_number(form):
    """⚠ Qt 的 `specialValueText` 綁的是 **`min`**，不是字面的零 ——
    所以這一條順便確認那一格的 `min` 真的是 0。"""
    form.set_step(REGISTRY[CARD].describe(), {"limit": 0})
    box = next(w for w in form.findChildren(QSpinBox) if w.minimum() == 0
               and w.specialValueText())
    assert box.specialValueText() == _spec(CARD, "limit").min_label
    assert box.value() == 0
    assert box.text() == box.specialValueText(), \
        "格子裡還是寫著 0 —— 那正是走查記的那一幕"


def test_a_real_limit_still_shows_the_number(form):
    """⚠ **只有最小值換字**。20 就是 20，不然使用者看不到自己設了多少。"""
    form.set_step(REGISTRY[CARD].describe(), {"limit": 20})
    box = next(w for w in form.findChildren(QSpinBox) if w.specialValueText())
    assert box.text().strip() == "20"


def test_every_zero_means_all_field_got_the_same_treatment():
    """**反向測試** —— 同一個約定在三張卡上，不准只修被走查點到的那一張。

    判準是那句共用的 help（`LIMIT_ZERO_HELP`）：寫著「Zero means every
    defect」的每一格都要有名字，不然下一個人讀到的是「有的有、有的沒有」。
    """
    from d4t.core.steps.output import LIMIT_ZERO_HELP

    found = [(k, p.name) for k, c in REGISTRY.items() for p in c.params
             if LIMIT_ZERO_HELP in str(p.help)]
    assert len(found) >= 3, found
    for key, name in found:
        spec = _spec(key, name)
        assert spec.min_label, (key, name)
        assert spec.min == 0, (key, name, spec.min)


# --------------------------------------------------------------------------- #
# 2. 第五格
# --------------------------------------------------------------------------- #
def test_the_fifth_chart_is_not_called_by_its_key(form):
    form.set_step(REGISTRY[CARD].describe(), {})
    words = {w.text() for w in form.findChildren(QCheckBox)}
    assert charts.CHART_LABELS[charts.CHART_CUSTOM] in words
    assert charts.CHART_CUSTOM not in words, \
        "格子上寫著 recipe 的鍵 —— 那正是走查記的那一幕"


def test_all_five_charts_use_the_label_table(form):
    """⚠ 五個都要 —— 只接一個上去的話，下一張圖又會漏。"""
    form.set_step(REGISTRY[CARD].describe(), {})
    words = {w.text() for w in form.findChildren(QCheckBox)}
    for key in charts.CHARTS:
        assert charts.CHART_LABELS[key] in words, key


def test_the_value_stored_is_still_the_key(form):
    """⚠ **格子上寫的字與存進 recipe 的值是兩件事**（同 F117 B2）。

    畫面換了字，而 recipe 裡還是 `chart` —— 不然這就變成一次改名，要付一道
    遷移，而且檔名（`-chart.svg`）也要跟著動。
    """
    form.set_step(REGISTRY[CARD].describe(), {"charts": charts.CHART_CUSTOM})
    assert form.values()["charts"] == charts.CHART_CUSTOM


# --------------------------------------------------------------------------- #
# 3. 勾選框自己就寫著那句話
# --------------------------------------------------------------------------- #
def test_a_checkbox_says_what_ticking_it_does(form):
    form.set_step(REGISTRY[CARD].describe(), {})
    words = {w.text() for w in form.findChildren(QCheckBox)}
    assert _spec(CARD, "boxes_csv").label in words
    assert "Enabled" not in words


def test_no_card_anywhere_still_says_enabled(form):
    """**反向測試**：`Enabled` 是 `param_form` 給所有 bool 的通用詞 ——
    它不准在任何一張卡上回來。"""
    for key, card in sorted(REGISTRY.items()):
        if not any(p.type == "bool" for p in card.params):
            continue
        form.set_step(card.describe(), {})
        words = {w.text() for w in form.findChildren(QCheckBox)}
        assert "Enabled" not in words, key


#: 一個 bool 的 label 搬到勾選框上之後，這幾個字會讓那一格變回 `Enabled`：
#: 它們講的是**這個設定叫什麼**，不是**勾了會發生什麼**。
#:
#: ⚠ **這張表不是在評英文。** 第一版想用「至少兩個字」當判準，而 `tone` 的
#: `Invert` 是一個字、讀起來完全沒問題 —— 一條判不出自己在判什麼的測試，最後
#: 只會被調整到剛好讓現況通過。這裡只擋**指名道姓的那幾個通用詞**。
GENERIC = {"enabled", "enable", "on", "off", "active", "use", "mode",
           "option", "flag", "yes", "no", "toggle"}


def test_no_bool_label_is_a_generic_word():
    """⚠ `Enabled` 之所以出現，是因為它是 `param_form` 寫死給所有 bool 的字。

    它現在不見了，而同一個坑在**卡片那一側**還開著：一張新卡把 label 寫成
    `Mode`，畫面上就會再出現一個什麼都沒說的勾選框。
    """
    bad = []
    for key, card in sorted(REGISTRY.items()):
        for p in card.params:
            if p.type != "bool":
                continue
            words = str(p.label or p.name).strip()
            assert words, "%s.%s 連 label 都沒有" % (key, p.name)
            if words.lower().strip(" .") in GENERIC:
                bad.append("%s.%s = %r" % (key, p.name, words))
    assert not bad, bad


def test_the_scan_would_actually_catch_one():
    """**反向測試** —— 這個 repo 為這件事付過兩次學費。

    一次是 regex 裡的「字界」符號在編輯的路上被吃掉（判準永遠不 match，
    整組測試因此都是綠的），一次是 `openUrl` 的 substring 掃描咬到了模組
    自己的註解。兩次的教訓是同一句：**一條沒有人驗過的判準不算判準。**

    ⚠ 寫這一行的時候那個符號**又**被吃掉了一次（留下一個 0x08 控制字元
    在原始碼裡）—— 所以這段話現在一個反斜線都不寫。
    """
    assert "enabled" in GENERIC and "Enabled".lower() in GENERIC
    assert "also write a table, one row per box" not in GENERIC


def test_the_name_column_does_not_repeat_the_checkbox(form):
    """同一個字在一列上出現兩次就是版面在說廢話（`_label_is_echo`）。"""
    from d4t.ui.fields import _ParamRow

    form.set_step(REGISTRY[CARD].describe(), {})
    rows = [r for r in form.findChildren(_ParamRow)
            if isinstance(r, _ParamRow)]
    assert rows, "找不到任何一列 —— 這條測試沒在測東西"
    for row in rows:
        if row.name_label.isVisibleTo(form):
            assert row.name_label.text() != _spec(CARD, "boxes_csv").label

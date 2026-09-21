"""量週期那一支是**公開的**，而且只有一個家（F120）。

2026-09-21 加了 `ui/pitch_helper.py`（丟一張圖進去只問 cell period）。在那之前
「這張圖的 pitch 是多少」只存在於 `_measure_period` —— 一支私有函式，而它的
唯一呼叫者是 `build_golden_cell`。

第二個呼叫者出現的那一天，選擇只有兩個：

* **開放那一支**（做了這個），或
* **抄一份三票制出去** —— 投影法 ＋ 二維自相關 ＋ 半週期檢查，四個月的實測、
  諧波修正、交錯晶格的加倍規則。抄出來的那一份一定會漂（`CLAUDE.md` §0），
  而它漂掉的後果是「兩個地方對同一張圖給出不同的 pitch」。

這一支守的就是不要回頭：名字公開、進 `__all__`、**舊的私有名字不存在**
（一件事兩個名字正是 §0 在擋的東西）。

⚠ 這一份**不 import Qt**（它問的是 core 的 API），所以它跑在核心那一批裡。
"""
from __future__ import annotations

import numpy as np
import pytest

from d4t.core.algo import template as algo_template


def _tiles(px: int = 40, py: int = 24, w: int = 480, h: int = 360) -> np.ndarray:
    """一張真的有週期的圖（固定種子，逐位元組可重現）。"""
    rng = np.random.default_rng(0)
    y, x = np.mgrid[0:h, 0:w]
    img = 60 + 60 * ((x % px) < px * 0.45) + 40 * ((y % py) < py * 0.5)
    return np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)


def test_it_is_public_and_on_the_all_list():
    assert callable(algo_template.measure_period)
    assert "measure_period" in algo_template.__all__


def test_the_old_private_name_is_gone():
    """別名 ＝ 一件事兩個名字。下一個人會挑到其中一個，而文件講的是另一個。"""
    assert not hasattr(algo_template, "_measure_period"), (
        "`_measure_period` 又出現了 —— F120 把它改成 `measure_period` 並且"
        "刻意沒有留別名，見那一支的 docstring")


def test_it_answers_the_period_it_was_given():
    m = algo_template.measure_period(_tiles(px=40, py=24))
    assert round(float(m.px)) == 40
    assert round(float(m.py)) == 24
    assert m.conf_x >= algo_template.MIN_PERIOD_CONFIDENCE
    assert m.conf_y >= algo_template.MIN_PERIOD_CONFIDENCE


def test_a_flat_image_gets_no_period_rather_than_a_made_up_one():
    """**量不到要回 0，不是猜一個。** 假週期疊出來的模板會讓後面每一顆都對錯。"""
    flat = np.full((240, 320), 128, np.uint8)
    m = algo_template.measure_period(flat)
    assert float(m.px) < 2 or m.conf_x < algo_template.MIN_PERIOD_CONFIDENCE
    assert float(m.py) < 2 or m.conf_y < algo_template.MIN_PERIOD_CONFIDENCE


def test_the_golden_cell_path_still_goes_through_the_same_one():
    """`build_golden_cell` 與 helper 問的是**同一支** —— 那是這一份的全部重點。

    判準是「疊出來的 cell 尺寸 ＝ 那一支量到的週期」：兩邊各量各的那天，
    這一條會紅。
    """
    img = _tiles(px=40, py=24)
    m = algo_template.measure_period(img)
    gc = algo_template.build_golden_cell(img)
    assert gc.px == round(float(m.px))
    assert gc.py == round(float(m.py))


@pytest.mark.parametrize("bad", [np.zeros((3, 3), np.uint8),
                                 np.zeros((0, 0), np.uint8)])
def test_a_useless_image_does_not_raise(bad):
    """helper 會把使用者丟進來的任何東西餵給它 —— 炸掉不是一個選項。"""
    m = algo_template.measure_period(bad)
    assert float(m.px) >= 0 and float(m.py) >= 0

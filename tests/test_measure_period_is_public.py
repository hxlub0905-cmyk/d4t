"""量週期那一支是**公開的**，而且只有一個家（F120）。

2026-09-21 加了一個只問 cell period 的小工具（pitch helper，2026-09-23 搬去自己
的 repo 了）。在那之前「這張圖的 pitch 是多少」只存在於 `_measure_period` ——
一支私有函式，而它的唯一呼叫者是 `build_golden_cell`。

⚠ **那個工具走了，這一份留著。** 它守的不是那個工具，是「量週期只有一個家」；
把 `measure_period` 收回 private 只會讓下一個第二呼叫者重走一次同一個選擇：

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


# --------------------------------------------------------------------------- #
# 量週期只有一個家：三票制不准有第二份，而兩條路要給同一個數字
# （起點是使用者 2026-09-23：「請幫我確保 d4t 自己算 pitch 的演算法與 pitch
#   helper 一致」。那個工具搬走之後守的對象變成 d4t 自己的兩條路）
# --------------------------------------------------------------------------- #
#: 只有這一支可以叫那三個原始的估測器。**其餘任何一支叫了 = 第二份三票制。**
PERIOD_PRIMITIVES = ("estimate_period", "estimate_period_2d",
                     "half_period_check")
PERIOD_HOME = "d4t/core/algo/template.py"


def test_the_raw_estimators_have_exactly_one_caller():
    """⚠ **這一條擋的是「再寫一份」，不是「算錯」。**

    `estimate_period`（投影法）與 `estimate_period_2d`（二維自相關）是原料；
    把它們仲裁成一個答案的三票制**只准住在 `template.measure_period`**。
    哪一天有人為了「只要快速估一下」在別處直接叫原料，那一刻就有了第二個
    pitch —— 而兩個地方對同一張圖給出不同的數字，是這個工具最糟的失敗。
    """
    import ast
    import io
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    strays = []
    for dirpath, dirs, files in os.walk(os.path.join(root, "d4t")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if rel == PERIOD_HOME:
                continue
            tree = ast.parse(io.open(path, encoding="utf-8").read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                got = (fn.attr if isinstance(fn, ast.Attribute)
                       else fn.id if isinstance(fn, ast.Name) else "")
                if got in PERIOD_PRIMITIVES:
                    strays.append((rel, node.lineno, got))
    assert not strays, (
        "只有 %s 可以叫那三個原始估測器，這幾個地方也叫了 —— 那是第二份三票制：\n  %s"
        % (PERIOD_HOME, "\n  ".join("%s:%d %s()" % s for s in strays)))


@pytest.mark.parametrize("px,py", [(60, 44), (30, 30), (79, 51), (120, 88)])
def test_the_two_ways_in_give_the_same_number(px, py):
    """⚠ **同一張圖，兩條路，一個答案。**

    直接問 `measure_period` 與走 `build_golden_cell` 是進同一個演算法的兩個門，
    而模板對話框的 `Cell W` / `Cell H` 讀的是後者。兩邊給出不同的數字的話，
    畫面上不會有任何地方說它們不一樣 —— 那正是這個工具最糟的失敗。

    判準是模板那條路對外給的 `period_x` / `period_y`（Cell W/H 讀的就是它），
    **不是** `px`／`py`（那是 cell 陣列的尺寸 = round）。
    """
    img = _tiles(px=px, py=py, w=600, h=480)
    m = algo_template.measure_period(img)
    gc = algo_template.build_golden_cell(img)
    assert abs(gc.period_x - m.px) < 1e-9, (gc.period_x, m.px)
    assert abs(gc.period_y - m.py) < 1e-9, (gc.period_y, m.py)
    assert round(float(m.px)) == px and round(float(m.py)) == py


def test_a_one_dimensional_layout_agrees_too():
    """⚠ **一維是常態，不是邊角。** 垂直條紋只有 X 有週期。

    ⚠ 判準是**沒有週期的那一軸取整張影像的長度當「一格」**，不是 0、不是
    NaN。任何一個畫格線的呼叫者都要靠它 —— 它一旦變成 0，那一軸的格線會鋪成
    無限多條，而那不會拋例外，只會畫出一片黑。
    """
    rng = np.random.default_rng(7)
    y, x = np.mgrid[0:480, 0:600]
    img = np.clip(60 + 80 * ((x % 48) < 48 * 0.45) + rng.normal(0, 6, (480, 600)),
                  0, 255).astype(np.uint8)
    m = algo_template.measure_period(img)
    gc = algo_template.build_golden_cell(img)
    assert round(float(m.px)) == 48 and float(m.py) < 2
    assert gc.periodic_x and not gc.periodic_y
    assert gc.py == img.shape[0], "沒有週期的那一軸要取整張影像的高"

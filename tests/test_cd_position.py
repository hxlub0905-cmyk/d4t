# CD 的團那一支：**那一團在哪**（F29，2026-08-25）。
"""位置一直都量得到，只是沒有出口。

使用者 2026-08-25：「GLV CD 在 Measurements 就已經量出這顆 defect 或位置的
一些資訊了（這些資訊不能拿來用嗎）」。查下去他是對的 —— `_note_blob` 存了整條
輪廓、面板也畫出來了，可是 26 個 ``cd_*`` 特徵全在講「多大、長什麼樣」，
一個都沒在講「在哪」。於是疊圖框不出來、報表排不了序。

這一份鎖住的是那六格：``cd_box_x/y/w/h`` ＋ ``cd_cx``/``cd_cy``。
最重要的一條是 :func:`test_the_box_is_in_whole_image_pixels_not_region_pixels`
—— 少了「把區域左上角加回去」那一步，每一顆的框都會擠在左上角，而**框的大小
還是對的**，所以畫面上看起來只像是「框歪了」。
"""
from __future__ import annotations

import numpy as np
import pytest

import d4t.core.steps  # noqa: F401 — registration side-effect
from d4t.core.pipeline.context import Context
from d4t.core.pipeline.step import REGISTRY
from d4t.core.steps._util import AREA_FEATURES, LENGTH_FEATURES, nm_twin_names
from d4t.core.steps.cd import ALWAYS_BLOB, SHAPE_BLOB, SHAPE_LINE

from tests.test_algo_shape import add_ellipse, canvas, l_shape

CARD = "cd_measure"
POSITION = ("cd_box_x", "cd_box_y", "cd_box_w", "cd_box_h", "cd_cx", "cd_cy")


def run(img, **params):
    cls = REGISTRY[CARD]
    p = cls.validate_params(dict({"shape": SHAPE_BLOB}, **params))
    ctx = Context(images={"test": np.asarray(img, dtype=np.float32)})
    return cls().run(ctx, p)


def blob_at(cx, cy, r=6.0, size=96):
    img = canvas(size)
    add_ellipse(img, cx, cy, r, r)
    return img


# --------------------------------------------------------------------------- #
# 量得對
# --------------------------------------------------------------------------- #
def test_the_box_lands_on_the_blob():
    got = run(blob_at(70, 30, r=7.0)).features
    assert got["cd_box_x"] + got["cd_box_w"] / 2 == pytest.approx(70, abs=2)
    assert got["cd_box_y"] + got["cd_box_h"] / 2 == pytest.approx(30, abs=2)
    assert got["cd_box_w"] == pytest.approx(14, abs=2)
    assert got["cd_box_h"] == pytest.approx(14, abs=2)
    assert got["cd_cx"] == pytest.approx(70, abs=2)
    assert got["cd_cy"] == pytest.approx(30, abs=2)


def test_the_centroid_is_not_the_centre_of_the_box():
    """一個 L 的質心落在轉角上，框的中心落在**背景**上。

    兩個都吐是刻意的：框是拿來畫的，質心才是「東西在哪」。這一條同時證明
    質心不是偷懶用框算出來的。
    """
    got = run(l_shape(size=96, arm=40, thick=10)).features
    box_cx = got["cd_box_x"] + got["cd_box_w"] / 2
    box_cy = got["cd_box_y"] + got["cd_box_h"] / 2
    assert abs(got["cd_cx"] - box_cx) + abs(got["cd_cy"] - box_cy) > 4.0


def test_the_box_is_in_whole_image_pixels_not_region_pixels():
    """**這一條是那個 bug 的形狀。**

    區域擺在右下角，團擺在區域裡面。忘了把區域的左上角加回去的話，框會回到
    影像的左上角 —— 而 ``cd_box_w`` / ``cd_box_h`` **仍然是對的**，所以症狀
    是「框歪了」而不是「框壞了」，很容易被當成畫圖的偏移。
    """
    cls = REGISTRY[CARD]
    img = blob_at(72, 76, r=6.0, size=96)
    ctx = Context(images={"test": img.astype(np.float32)})
    ctx.set_roi("corner", (0.5, 0.5, 0.5, 0.5))          # 右下那一塊 = (48,48)
    got = cls().run(ctx, cls.validate_params(
        {"shape": SHAPE_BLOB, "roi": "corner"})).features
    assert got["cd_box_x"] > 48.0 and got["cd_box_y"] > 48.0
    assert got["cd_cx"] == pytest.approx(72, abs=2)
    assert got["cd_cy"] == pytest.approx(76, abs=2)


def test_the_outline_drawn_on_screen_and_the_box_agree():
    """畫布不能說謊：meta 裡那一圈輪廓要落在吐出去的框裡面。

    兩者走的是同一個 ``rect``，但它們是**兩段各自寫的程式碼** —— 只改一邊的
    那一天，畫面上那一圈與 CSV 上那一列會指著不同的地方，而沒有人看得出來。
    """
    out = run(blob_at(70, 30, r=7.0))
    got = out.features
    outline = out.meta["cd"][""]["outline"]
    assert outline
    xs = [px * 96 for px, _py in outline]
    ys = [py * 96 for _px, py in outline]
    assert got["cd_box_x"] - 1 <= min(xs) and max(xs) <= (
        got["cd_box_x"] + got["cd_box_w"] + 1)
    assert got["cd_box_y"] - 1 <= min(ys) and max(ys) <= (
        got["cd_box_y"] + got["cd_box_h"] + 1)


# --------------------------------------------------------------------------- #
# 量不到就不寫（規矩 3）
# --------------------------------------------------------------------------- #
def test_nothing_there_writes_no_position_at_all():
    """0 會讓疊圖在左上角畫一個 0×0 的框 —— 看起來像量到了。"""
    got = run(canvas(96)).features
    for name in POSITION:
        assert name not in got, name
    assert got["cd_pieces"] == 0.0          # 「量得準不準」那幾個照吐


def test_the_line_branch_writes_no_position():
    """線那一支的「位置」是一條掃描線，不是一個東西 —— 刻意留白。"""
    cls = REGISTRY[CARD]
    declared = set(cls.resolve_features(cls.validate_params({})))
    assert not (declared & set(POSITION))

    img = canvas(96)
    img[:, 40:52] += 120.0
    ctx = Context(images={"test": img.astype(np.float32)})
    got = cls().run(ctx, cls.validate_params({"shape": SHAPE_LINE})).features
    assert got.get("cd_n", 0) > 0           # 真的量到了線
    for name in POSITION:
        assert name not in got, name


# --------------------------------------------------------------------------- #
# 宣告與單位
# --------------------------------------------------------------------------- #
def test_position_is_always_written_not_a_tick_box():
    """位置不是「要不要量」的選擇，是「我剛才量在哪」。"""
    assert set(POSITION) <= set(ALWAYS_BLOB)
    cls = REGISTRY[CARD]
    # `size_report` 一個都不勾，位置照樣在
    p = cls.validate_params({"shape": SHAPE_BLOB, "size_report": ""})
    assert set(POSITION) <= set(cls.resolve_features(p))
    got = cls().run(Context(images={"test": blob_at(70, 30).astype(np.float32)}),
                    p).features
    assert set(POSITION) <= set(got)


def test_the_box_gets_no_nm_twin():
    """框是「畫在哪」不是「多大」—— 配一份 nm 等於請人拿 bbox 當尺寸用。

    而那正是 F19 拆掉的東西（``cd_x_px`` / ``area_px`` 全刪，理由是「舊值是
    bbox，跟新值不是同一種量測」）。尺寸有 nm 版的是 ``cd_feret_*`` /
    ``cd_area_px``，這一條同時確認那些**還在**。
    """
    assert nm_twin_names(POSITION) == []
    assert not (set(POSITION) & set(LENGTH_FEATURES))
    assert not (set(POSITION) & set(AREA_FEATURES))
    assert nm_twin_names(["cd_feret_max", "cd_area_px"]) == [
        "cd_feret_max_nm", "cd_area_nm2"]


def test_the_old_names_never_come_back():
    """F19 刪掉的是「舊名字的意思被悄悄換掉」，所以舊名字要一直不在。"""
    cls = REGISTRY[CARD]
    declared = set(cls.resolve_features(cls.validate_params(
        {"shape": SHAPE_BLOB}))) | set(cls.features_out)
    assert not (declared & {"cd_x_px", "cd_y_px", "area_px"})


def test_regions_prefix_the_position_like_everything_else():
    """兩個以上區域時位置也帶前綴 —— 否則兩塊的框會撞成同一格。"""
    cls = REGISTRY[CARD]
    img = canvas(96)
    add_ellipse(img, 24, 24, 6.0, 6.0)
    add_ellipse(img, 72, 72, 6.0, 6.0)
    ctx = Context(images={"test": img.astype(np.float32)})
    ctx.set_roi("a", (0.0, 0.0, 0.5, 0.5))
    ctx.set_roi("b", (0.5, 0.5, 0.5, 0.5))
    got = cls().run(ctx, cls.validate_params(
        {"shape": SHAPE_BLOB, "roi": "a,b"})).features
    assert got["a_cd_cx"] == pytest.approx(24, abs=2)
    assert got["b_cd_cx"] == pytest.approx(72, abs=2)
    assert "cd_cx" not in got

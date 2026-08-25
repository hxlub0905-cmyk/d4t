# find_defect：**這張圖上最可疑的東西在哪**（F29，2026-08-25）。
"""使用者是 defect team 的分析工程師，跑完一整筆 image 之後要看到的是
「缺陷被抓出來」。這張卡只欠那一件事 —— 一個框。

排序不是它的工作（那是使用者自己寫的 ``score``），尺寸也不是（那是 CD）。
所以這一份問的只有四句話：**框在對的地方嗎、挑對那一團了嗎、找不到的時候
安靜下來了嗎、以及它有沒有偷偷長出區域來。**

最後那一句是這張卡最重要的一條界線（使用者 2026-08-20：「Blob 分割不需要
也不要再出現」）。F29 把界線挪成「可以找一個框，不可以產生具名區域」——
:func:`test_it_never_grows_a_region` 就是那一句話的執行版。
"""
from __future__ import annotations

import numpy as np
import pytest

import d4t.core.steps  # noqa: F401 — registration side-effect
from d4t.core.export import overlay
from d4t.core.pipeline.context import Context
from d4t.core.pipeline.step import REGISTRY, GROUP_MEASURE

from tests.test_algo_shape import canvas

CARD = "find_defect"
BOX = ("blob_x", "blob_y", "blob_w", "blob_h")
PLACE = BOX + ("blob_cx", "blob_cy")


def run(img, **params):
    cls = REGISTRY[CARD]
    p = cls.validate_params(dict({"source": "test"}, **params))
    ctx = Context(images={"test": np.asarray(img, dtype=np.float32)})
    return cls().run(ctx, p)


def spot(img, x, y, w, h, amp):
    img[y:y + h, x:x + w] = amp
    return img


# --------------------------------------------------------------------------- #
# 找得到、而且挑對那一個
# --------------------------------------------------------------------------- #
def test_the_box_lands_on_the_thing():
    img = spot(canvas(96), 60, 20, 12, 8, 200.0)
    got = run(img).features
    assert got["blob_x"] == pytest.approx(60, abs=1)
    assert got["blob_y"] == pytest.approx(20, abs=1)
    assert got["blob_w"] == pytest.approx(12, abs=1)
    assert got["blob_h"] == pytest.approx(8, abs=1)
    assert got["blob_cx"] == pytest.approx(66, abs=1)
    assert got["blob_cy"] == pytest.approx(24, abs=1)
    assert got["blob_n"] == 1.0
    assert got["blob_strength"] > 0.0


def test_it_takes_the_strongest_one_not_the_first_one():
    """**排序真的有作用。** 兩團都過門檻，弱的排在掃描順序的前面。

    少了排序（或排序寫成「照標籤編號」）的話，回的是**比較上面的那一團** ——
    而它每一顆都吐得出一個看起來很正常的框。
    """
    img = canvas(96)
    spot(img, 10, 10, 10, 10, 150.0)          # 弱，而且在上面（標籤 1）
    spot(img, 60, 60, 10, 10, 240.0)          # 強，在下面（標籤 2）
    got = run(img, threshold_pct=20).features
    assert got["blob_n"] == 2.0
    assert got["blob_x"] == pytest.approx(60, abs=1)
    assert got["blob_y"] == pytest.approx(60, abs=1)


def test_only_the_strongest_gets_coordinates():
    """使用者定調「最強的那一個」—— 一顆 defect 一列的結果模型不動。

    其餘的候選**數得出來**（``blob_n``），但只有一組座標。少了 ``blob_n``
    的話，「只有一個候選」跟「有十七個」在 CSV 上長得一模一樣。
    """
    img = canvas(96)
    for i, x in enumerate((8, 30, 52, 74)):
        spot(img, x, 40, 8, 8, 180.0 + 10 * i)
    got = run(img, threshold_pct=20).features
    assert got["blob_n"] == 4.0
    assert len([k for k in got if k.startswith("blob_x")]) == 1


def test_the_polarity_it_picked_is_written_down():
    """``target="auto"`` 逐顆挑不同極性的話，``blob_strength`` 那一欄會同時
    裝著兩種東西 —— 而 CSV 上沒有別的線索（同 ``cd_bright``）。"""
    bright = run(spot(canvas(96), 60, 20, 12, 8, 220.0)).features
    dark = run(spot(canvas(96, bg=200.0), 60, 20, 12, 8, 40.0)).features
    assert bright["blob_bright"] == 1.0
    assert dark["blob_bright"] == 0.0
    assert dark["blob_x"] == pytest.approx(60, abs=1)


# --------------------------------------------------------------------------- #
# 區域
# --------------------------------------------------------------------------- #
def test_it_does_not_look_outside_the_region():
    """接了區域就只在那裡面找 —— 外面那一團**比較強**，正是為了讓這條會紅。"""
    cls = REGISTRY[CARD]
    img = canvas(96)
    spot(img, 60, 60, 10, 10, 250.0)          # 右下（區域外，比較強）
    spot(img, 10, 10, 10, 10, 180.0)          # 左上（區域內）
    ctx = Context(images={"test": img.astype(np.float32)})
    ctx.set_roi("topleft", (0.0, 0.0, 0.5, 0.5))
    got = cls().run(ctx, cls.validate_params(
        {"source": "test", "roi": "topleft", "threshold_pct": 20})).features
    assert got["blob_x"] == pytest.approx(10, abs=1)
    assert got["blob_y"] == pytest.approx(10, abs=1)


def test_the_box_is_in_whole_image_pixels():
    """區域偏移要加回去 —— 疊圖畫在整張圖上（同 ``cd_box_*``）。

    忘了加的話框會擠到左上角，而**大小仍然是對的**，所以症狀是「框歪了」。
    """
    cls = REGISTRY[CARD]
    img = spot(canvas(96), 70, 74, 10, 8, 220.0)
    ctx = Context(images={"test": img.astype(np.float32)})
    ctx.set_roi("corner", (0.5, 0.5, 0.5, 0.5))
    got = cls().run(ctx, cls.validate_params(
        {"source": "test", "roi": "corner"})).features
    assert got["blob_x"] == pytest.approx(70, abs=1)
    assert got["blob_y"] == pytest.approx(74, abs=1)


def test_two_regions_prefix_their_numbers():
    cls = REGISTRY[CARD]
    img = canvas(96)
    spot(img, 10, 10, 10, 10, 200.0)
    spot(img, 60, 60, 10, 10, 200.0)
    ctx = Context(images={"test": img.astype(np.float32)})
    ctx.set_roi("a", (0.0, 0.0, 0.5, 0.5))
    ctx.set_roi("b", (0.5, 0.5, 0.5, 0.5))
    got = cls().run(ctx, cls.validate_params(
        {"source": "test", "roi": "a,b"})).features
    assert got["a_blob_x"] == pytest.approx(10, abs=1)
    assert got["b_blob_x"] == pytest.approx(60, abs=1)
    assert "blob_x" not in got


# --------------------------------------------------------------------------- #
# 界線：可以找一個框，不可以產生具名區域
# --------------------------------------------------------------------------- #
def test_it_never_grows_a_region():
    """使用者 2026-08-20：「Blob 分割不需要 也不要再出現」。

    界線在 F29 挪成「**可以找一個框，不可以產生具名區域**」，而挪的是哪一格
    要守得住：具名區域是下游每一張卡的輸入（``roi=``），自動長出一個等於畫布上
    出現一條沒有人拉過的線。
    """
    cls = REGISTRY[CARD]
    img = spot(canvas(96), 60, 20, 12, 8, 220.0)
    ctx = Context(images={"test": img.astype(np.float32)})
    ctx.set_roi("mine", (0.0, 0.0, 1.0, 1.0))
    before = sorted(ctx.roi_names())
    cls().run(ctx, cls.validate_params({"source": "test", "roi": "mine"}))
    assert sorted(ctx.roi_names()) == before
    assert cls.resolve_regions_out(cls.validate_params({"source": "test"})) == []


# --------------------------------------------------------------------------- #
# 找不到的時候
# --------------------------------------------------------------------------- #
def test_nothing_there_writes_no_box_but_says_why():
    """0 會讓疊圖在左上角畫一個 0×0 的框 —— 看起來像找到了。"""
    out = run(canvas(96))
    got = out.features
    for name in PLACE + ("blob_strength", "blob_area_px", "blob_deq"):
        assert name not in got, name
    assert got["blob_n"] == 0.0
    assert "blob_edge_score" in got          # 「為什麼沒有」的那個數字
    assert "found nothing" in " ".join(out.meta["warnings"])


def test_noise_alone_is_not_a_defect():
    """門檻調到 0 就會找到雜訊本身 —— 預設要擋得住（同 CD 的 ``min_edge``）。"""
    rng = np.random.default_rng(3)
    img = canvas(96) + rng.normal(0.0, 2.0, (96, 96))
    assert run(img).features["blob_n"] == 0.0


def test_a_region_too_small_says_so():
    cls = REGISTRY[CARD]
    ctx = Context(images={"test": canvas(96).astype(np.float32)})
    ctx.set_roi("sliver", (0.4, 0.4, 0.02, 0.02))
    out = cls().run(ctx, cls.validate_params(
        {"source": "test", "roi": "sliver"}))
    assert not any(k.startswith("blob_") for k in out.features)
    assert "too small" in " ".join(out.meta["warnings"])


# --------------------------------------------------------------------------- #
# 接得上疊圖與預覽
# --------------------------------------------------------------------------- #
def test_overlay_reads_the_four_numbers_straight_off():
    """框那四個名字**就是** `primary_blob_box` 本來在讀的那四個 ——
    所以 `export/overlay.py` 一行都不用改。"""
    got = run(spot(canvas(96), 60, 20, 12, 8, 220.0)).features
    assert overlay.primary_blob_box(None, got) == (60, 20, 12, 8)


def test_the_preview_draws_the_box_it_found():
    """量測卡要在影像上標出它正在量哪裡（F19 定的 Measure 段共用路）。"""
    cls = REGISTRY[CARD]
    p = cls.validate_params({"source": "test"})
    ctx = Context(images={"test": spot(canvas(96), 60, 20, 12, 8,
                                       220.0).astype(np.float32)})
    cls().run(ctx, p)
    lines, points, focus, labels = cls.overlay_marks(ctx, p)
    assert len(lines) == 4                      # 一個框四條邊
    assert len(points) == len(lines) == len(labels)
    assert focus == -1                          # 四條邊一樣重要
    xs = [pt[0] for seg in lines for pt in seg]
    assert min(xs) == pytest.approx(60 / 96, abs=0.02)
    assert max(xs) == pytest.approx(72 / 96, abs=0.02)
    assert sum(len(p) for p in points) == 1     # 質心那一點


def test_the_preview_draws_nothing_when_it_found_nothing():
    cls = REGISTRY[CARD]
    p = cls.validate_params({"source": "test"})
    ctx = Context(images={"test": canvas(96).astype(np.float32)})
    cls().run(ctx, p)
    assert cls.overlay_marks(ctx, p)[0] == []


def test_it_does_not_write_a_second_copy_of_the_box():
    """同一件事存兩份的話兩份會漂 —— 特徵那一份已經夠疊圖用了。"""
    ctx = run(spot(canvas(96), 60, 20, 12, 8, 220.0)).meta
    assert "blobs" not in ctx


# --------------------------------------------------------------------------- #
# 單位
# --------------------------------------------------------------------------- #
def test_area_converts_with_the_square_and_lengths_do_not():
    """``blob_area_px`` 結尾是 ``_px`` 但意思是面積 —— 少乘一次會很安靜。

    **這一條抓過一次真的 bug**：卡片剛寫好的時候宣告出來的是 ``blob_area_nm``
    （少乘一次），因為 `nm_twins` 的規則是「``_px`` 結尾 → ×s」，而面積要 ×s²。
    面積住在 `_util.AREA_FEATURES` 那張表上，加一張新卡就要記得加一行。
    """
    cls = REGISTRY[CARD]
    ctx = Context(images={"test": spot(canvas(96), 60, 20, 12, 8,
                                       220.0).astype(np.float32)},
                  meta={"nm_per_px": 3.0})
    got = cls().run(ctx, cls.validate_params({"source": "test"})).features
    assert got["blob_area_nm2"] == pytest.approx(got["blob_area_px"] * 9.0)
    assert got["blob_deq_nm"] == pytest.approx(got["blob_deq"] * 3.0)
    assert "blob_area_nm" not in got          # 那是少乘一次的那個名字


def test_where_it_is_gets_no_nm_twin():
    """框與質心是「畫在哪」不是「多大」（同 ``cd_box_*``）；σ 本來就沒有單位。"""
    cls = REGISTRY[CARD]
    ctx = Context(images={"test": spot(canvas(96), 60, 20, 12, 8,
                                       220.0).astype(np.float32)},
                  meta={"nm_per_px": 3.0})
    got = cls().run(ctx, cls.validate_params({"source": "test"})).features
    for name in PLACE + ("blob_strength", "blob_n", "blob_edge_score"):
        assert name + "_nm" not in got, name


# --------------------------------------------------------------------------- #
# 它站在哪一段
# --------------------------------------------------------------------------- #
def test_it_is_a_measure_card_wired_like_the_others():
    cls = REGISTRY[CARD]
    assert cls.group == GROUP_MEASURE
    names = {s.name: s for s in cls.params}
    assert names["source"].type == "image_keys"      # 畫布上是一條線
    assert names["roi"].type == "region_keys"        # 畫布上是一條虛線
    for spec in cls.params:
        assert str(spec.help).strip(), spec.name


def test_the_declaration_matches_what_comes_out():
    cls = REGISTRY[CARD]
    p = cls.validate_params({"source": "test"})
    got = run(spot(canvas(96), 60, 20, 12, 8, 220.0)).features
    assert set(got) <= set(cls.resolve_features(p))
    assert set(PLACE) <= set(got)

# F11 Region-3 第 3 步：GDS label map → 具名區域。
# 2026-08-25（F29）：這張卡收成「參照區域」的一個 method（``layout layers``），
# 另一個是 ``repeating cells``。這一份仍然只測 GDS 那一支 ——
# 週期那一支住 `tests/test_roi_reference_cells.py`。
"""這一份鎖住的是**框真的等於那一層**，不是「卡片跑得完」。

d4t 的區域是一組軸對齊矩形，而 GLAS 給的是任意形狀的 mask。中間那個轉換有
兩種做法，而錯的那一種**不會報錯**：

* **取 bounding box** —— 一個 L 形的 bbox 會框到別的材質，然後吐出一個看起來
  完全正常的灰階值；
* **精確拆解** —— 站點的 layout 是 Manhattan 的，所以那是等價不是近似。

所以最重要的一條測試是「聯集起來**逐像素**等於 ``label == id``」，而且它要一路
測到**正規化來回之後**（0–1 座標是為了換尺寸不錯位，但它同時是一個會偷偷四捨
五入掉一個像素的地方）。

另外三件：**非週期**（這條路的前提就是前兩張卡的前提都不成立）、
**三個名字**（``<name>`` / ``_center`` / ``_others`` —— F29 之前只有第一個，
換掉的理由與沒有被推翻的那一半見卡片檔頭）、以及**砍到上限要講出來**
（少掉一半框的區域仍然算得出很正常的數字）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.algo import mask as algo_mask  # noqa: E402
from d4t.core.ingest import glas_export  # noqa: E402
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from d4t.core.pipeline.step import StepError  # noqa: E402

LAYERS = "1:epi, 2:mg"


CARD = "roi_reference"
GDS = {"method": "layout layers"}


def _params(**over):
    p = dict(GDS, label_source="layout_label", layers=LAYERS, min_area=0,
             output_prefix="", max_boxes=8192)
    p.update(over)
    return p


def _run(label, **over):
    ctx = Context(images={"layout_label": np.asarray(label, np.uint8)})
    get_step(CARD)().run(ctx, _params(**over))
    return ctx


def _union(ctx, name, shape):
    back = np.zeros(shape, bool)
    for x, y, w, h in ctx.roi_rects(name, shape):
        back[y:y + h, x:x + w] = True
    return back


# --------------------------------------------------------------------------- #
# 1. 幾何：框聯集起來就是那一層，一個像素都不差
# --------------------------------------------------------------------------- #
def test_an_L_shape_is_two_rectangles_not_a_bounding_box():
    """L 形的 bounding box 會把右下那塊背景一起框進去 —— 而那一塊是別的材質。"""
    lab = np.zeros((6, 6), np.uint8)
    lab[0:4, 0:6] = 1
    lab[4:6, 0:2] = 1
    ctx = _run(lab)
    assert ctx.roi_count("epi") == 2
    assert (_union(ctx, "epi", lab.shape) == (lab == 1)).all()
    # bbox 會多框到 8 個像素 —— 這一行是「錯的做法錯多少」的紀錄
    assert int(((lab[0:6, 0:6] == 0)).sum()) == 8


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_the_boxes_are_pixel_exact_after_the_round_trip(seed):
    """**這是這張卡唯一不能錯的東西。**

    正規化（0–1）是為了換影像尺寸不錯位（F7-4 的坑），但它同時是一個會偷偷
    四捨五入掉一個像素的地方 —— 所以要測的是**來回之後**還相同。
    """
    rng = np.random.default_rng(seed)
    lab = np.zeros((64, 96), np.uint8)
    for value in (1, 2):
        for _ in range(6):
            x, y = int(rng.integers(0, 80)), int(rng.integers(0, 50))
            w, h = int(rng.integers(3, 20)), int(rng.integers(3, 14))
            lab[y:y + h, x:x + w] = value
    ctx = _run(lab)
    for lid, name in ((1, "epi"), (2, "mg")):
        assert (_union(ctx, name, lab.shape) == (lab == lid)).all(), name


def test_a_diagonal_edge_costs_one_rectangle_per_row():
    """`fillPoly` 沒有 LINE_AA，所以斜邊就是 1px 的階梯。那是**精確的代價**，
    不是 bug —— 而它正是 `max_boxes` 要開大的原因。"""
    n = 20
    lab = np.array([[1 if x <= y else 0 for x in range(n)] for y in range(n)],
                   np.uint8)
    rects, piece_of = algo_mask.decompose(lab, 1)
    assert len(rects) == n and len(set(piece_of)) == 1


def test_separate_shapes_are_separate_pieces_but_one_region():
    """一個名字底下好幾塊 —— 這條路上「一份」不是複本，所以 pieces 只是資訊。"""
    lab = np.zeros((8, 12), np.uint8)
    lab[1:4, 1:4] = 1
    lab[5:7, 8:11] = 1
    ctx = _run(lab)
    assert ctx.roi_count("epi") == 2
    assert ctx.features["epi_pieces"] == 2.0
    assert ctx.features["epi_area_px"] == 3 * 3 + 2 * 3


def test_the_layout_does_not_have_to_repeat():
    """這條路的前提就是**前兩張卡的前提都不成立** —— 不准偷偷需要週期性。"""
    rng = np.random.default_rng(9)
    lab = np.zeros((48, 48), np.uint8)
    for _ in range(7):
        x, y = int(rng.integers(0, 40)), int(rng.integers(0, 40))
        lab[y:y + int(rng.integers(2, 9)), x:x + int(rng.integers(2, 9))] = 1
    ctx = _run(lab)
    assert ctx.roi_count("epi") > 0
    assert (_union(ctx, "epi", lab.shape) == (lab == 1)).all()


# --------------------------------------------------------------------------- #
# 2. 三個名字（F29 之前只有 <name>）
# --------------------------------------------------------------------------- #
def test_it_declares_the_whole_family():
    """``_center`` / ``_others`` 在 F29 補上了 —— 而**原本的反對意見沒有被推翻**。

    當初不吐它們的理由是：另外兩張卡的 ``_center`` 是「缺陷所在的那一份」，
    那是幾何保證的（patch 以缺陷為中心裁切）；這條路上缺陷不保證在正中央。
    那句話今天仍然成立 —— 變的是有了 ``pick="strongest"``：它不假設缺陷在哪，
    **它去找**（下面那條測試就是在測這件事）。
    """
    out = get_step(CARD).resolve_regions_out(_params())
    assert out == ["epi", "epi_center", "epi_others",
                   "mg", "mg_center", "mg_others"]


def test_it_really_produces_those(tmp_path):
    lab = np.zeros((8, 8), np.uint8)
    lab[1:4, 1:4] = 1
    lab[5:7, 5:7] = 1
    ctx = _run(lab)
    assert sorted(ctx.roi_names()) == ["epi", "epi_center", "epi_others"]


def test_one_piece_means_no_baseline_at_all():
    """只有一塊的時候 ``_others`` **不存在**（不是空的、也不是退回整張圖）。"""
    lab = np.zeros((8, 8), np.uint8)
    lab[1:4, 1:4] = 1
    ctx = _run(lab)
    assert "epi_others" not in ctx.roi_names()
    assert "epi_others" in (ctx.meta.get("regions_absent") or {})


def test_strongest_finds_the_odd_box_out():
    """**這條路真正的用法。** 缺陷不在正中央，所以用訊號去找那一塊。"""
    lab = np.zeros((40, 40), np.uint8)
    for x in (2, 14, 26):
        lab[4:12, x:x + 8] = 1
    sig = np.zeros((40, 40), np.float32)
    sig[4:12, 26:34] = 200.0                     # 最右邊那一塊才是缺陷
    ctx = Context(images={"layout_label": lab, "diff": sig})
    get_step(CARD)().run(ctx, _params(pick="strongest", pick_source="diff"))
    box = ctx.roi_rects("epi_center", lab.shape)[0]
    assert box[0] >= 26
    assert ctx.roi_count("epi_others") == 2


def test_falling_back_to_the_middle_is_said_out_loud():
    """接不到 ``Judge on`` 就退回「離中心最近」—— 而安靜地照做是最糟的。"""
    lab = np.zeros((40, 40), np.uint8)
    for x in (2, 14, 26):
        lab[4:12, x:x + 8] = 1
    ctx = Context(images={"layout_label": lab})
    get_step(CARD)().run(ctx, _params(pick="strongest"))
    assert ctx.features["pick_by_signal"] == 0.0
    assert "Judge on" in " ".join(ctx.meta["warnings"])


def test_the_declared_features_match_what_it_writes():
    lab = np.zeros((8, 8), np.uint8)
    lab[1:4, 1:4] = 1
    lab[5:7, 5:7] = 2
    declared = set(get_step(CARD).resolve_features(_params()))
    assert set(_run(lab).features) == declared


def test_the_prefix_applies_to_everything():
    lab = np.zeros((8, 8), np.uint8)
    lab[1:4, 1:4] = 1
    ctx = _run(lab, output_prefix="g")
    assert "g_epi_present" in ctx.features and "g_layout_ok" in ctx.features


# --------------------------------------------------------------------------- #
# 3. 上限與丟小塊 —— **都要講出來**
# --------------------------------------------------------------------------- #
def test_hitting_the_cap_is_said_out_loud():
    """少掉一半框的區域仍然算得出一個很正常的灰階值。"""
    n = 40
    lab = np.array([[1 if x <= y else 0 for x in range(n)] for y in range(n)],
                   np.uint8)
    ctx = _run(lab, max_boxes=10)
    assert ctx.roi_count("epi") == 10
    assert ctx.features["epi_clipped"] == 1.0
    assert any("more than the 10 limit" in w for w in ctx.meta["warnings"])


def test_not_hitting_the_cap_leaves_clipped_at_zero():
    lab = np.zeros((8, 8), np.uint8)
    lab[1:4, 1:4] = 1
    assert _run(lab).features["epi_clipped"] == 0.0


def test_the_cap_keeps_the_boxes_nearest_the_middle():
    """砍掉的要是最外圍的 —— 缺陷比較可能在中間。"""
    lab = np.zeros((20, 20), np.uint8)
    lab[0:2, 0:2] = 1                      # 角落
    lab[9:11, 9:11] = 1                    # 正中央
    ctx = _run(lab, max_boxes=1)
    (x, y, w, h), = ctx.roi_rects("epi", lab.shape)
    assert (x, y) == (9, 9)


def test_a_piece_smaller_than_the_minimum_goes_whole():
    """丟整塊不丟小矩形 —— 把一塊挖掉一角會改變答案而不改變它的樣子。"""
    lab = np.zeros((10, 20), np.uint8)
    lab[1:5, 1:9] = 1                      # 32 px
    lab[8:9, 15:17] = 1                    # 2 px
    ctx = _run(lab, min_area=10)
    assert ctx.roi_count("epi") == 1
    assert ctx.features["epi_area_px"] == 32
    assert any("smaller than 10 px" in w for w in ctx.meta["warnings"])


def test_a_layer_with_nothing_left_does_not_fall_back_to_the_whole_image():
    """退回整張圖會**安靜地**量到全部的像素，而那是錯的。"""
    lab = np.zeros((8, 8), np.uint8)
    lab[1:4, 1:4] = 1                      # 只有第 1 層
    ctx = _run(lab)
    assert "mg" not in ctx.roi_names()
    assert ctx.features["mg_present"] == 0.0
    assert "not in this defect's label map" in ctx.meta["regions_absent"]["mg"]


def test_the_two_reasons_for_an_empty_layer_are_told_apart():
    """「這一顆沒有那一層」跟「那一層都被最小面積濾掉了」的下一步不同。"""
    lab = np.zeros((8, 8), np.uint8)
    lab[1:4, 1:4] = 1
    lab[6:7, 6:7] = 2                      # 1 px 的第 2 層
    ctx = _run(lab, min_area=5)
    assert "smaller than the 5 px minimum" in ctx.meta["regions_absent"]["mg"]


# --------------------------------------------------------------------------- #
# 4. 設定與壞輸入
# --------------------------------------------------------------------------- #
def test_no_layers_yet_is_a_configuration_issue_not_a_crash():
    """空字串是合法的值，但這張卡跑起來每一顆都會失敗 —— 要在跑之前就講。"""
    says = get_step(CARD).configuration_issues(_params(layers=""))
    # 訊息必須指向一個**按得下去**的東西（`tests/test_ui_f7_9_feedback.py` 的
    # 那條不變量）—— 「還沒設定完」而沒有下一步，就是死路。
    assert says and "Open GDS export…" in says[0]
    assert get_step(CARD).configuration_issues(_params()) == []
    # ``repeating cells`` 那一支**沒有這種狀態** —— 它不需要任何外部資料。
    assert get_step(CARD).configuration_issues(
        {"method": "repeating cells"}) == []


def test_running_with_no_layers_says_what_to_fill_in():
    lab = np.zeros((8, 8), np.uint8)
    with pytest.raises(StepError) as e:
        _run(lab, layers="")
    text = str(e.value)
    assert "Open GDS export…" in text          # GUI 那條路
    assert "--gds" in text                     # CLI 那條路


def test_a_three_channel_source_is_refused():
    """label 的像素值**是**層號 —— 三通道多半是指到了 `_label_view.png`。"""
    lab = np.zeros((8, 8, 3), np.uint8)
    with pytest.raises(StepError) as e:
        _run(lab)
    assert "single-channel" in str(e.value)


def test_a_shredded_image_is_refused_rather_than_run_for_ever():
    """棋盤格會產生幾十萬個 run。「跑很久」跟「當掉」對使用者是同一件事。"""
    yy, xx = np.mgrid[0:700, 0:700]
    lab = ((yy + xx) % 2).astype(np.uint8)
    with pytest.raises(algo_mask.MaskError) as e:
        algo_mask.decompose(lab, 1)
    assert "not a label map" in str(e.value)


def test_a_half_typed_layer_map_does_not_kill_the_canvas():
    """宣告用的那幾支不准拋 —— 打到一半的時候畫布不能整個消失。"""
    card = get_step(CARD)
    assert card.resolve_regions_out(_params(layers="1:")) == []
    assert card.resolve_features(_params(layers="1:"))


# --------------------------------------------------------------------------- #
# 5. layer 名的改寫（GLAS 的 `L17/D0` 不能當變數）
# --------------------------------------------------------------------------- #
def test_a_layout_layer_name_becomes_a_usable_region_name():
    assert glas_export.region_name_for("L17/D0") == "L17_D0"
    assert glas_export.region_name_for("EPI (L17/D0)") == "EPI_L17_D0"
    assert glas_export.region_name_for("") == "layer"
    assert glas_export.region_name_for("9x")[0].isalpha(), "不能以數字開頭"


def test_two_layers_that_would_collide_get_different_names():
    """撞名的話後面那層會蓋掉前面那層，而畫面上只看得到一個區域。"""
    taken = []
    for raw in ("a/b", "a:b", "a b"):
        taken.append(glas_export.region_name_for(raw, taken))
    assert len(set(taken)) == 3


def test_the_default_layer_map_parses_as_the_card_parameter():
    """預設值要能直接餵進 `channel_map` 的驗證（整數、不重複、名字能當變數）。"""
    from d4t.core.pipeline.channels import parse_channel_map

    doc = {"label_map": [{"id": 1, "layer": "L17/D0"},
                         {"id": 2, "layer": "L21/D0"}]}
    text = glas_export.default_layer_map(doc)
    assert parse_channel_map(text) == [(1, "L17_D0"), (2, "L21_D0")]


# --------------------------------------------------------------------------- #
# 6. 儀表看到的就是引擎算的
# --------------------------------------------------------------------------- #
def test_the_panel_sees_the_same_numbers(tmp_path):
    lab = np.zeros((10, 10), np.uint8)
    lab[1:5, 1:5] = 1
    ctx = _run(lab)
    rec = ctx.meta["gds_layers"]["layout_label"]
    assert rec["shape"] == [10, 10]
    assert rec["ids_in_image"] == [1]
    by_name = {e["name"]: e for e in rec["layers"]}
    assert by_name["epi"]["boxes"] == ctx.roi_count("epi")
    assert by_name["mg"]["boxes"] == 0

# F7-12 驗收：Golden Cell 模板定位（patch 比一個週期還小也定得出來）。
"""這一段的前提，是使用者釐清的一個尺寸關係：

**patch 通常比一個重複單元還小**，所以每張 patch 只看到週期裡的一小片，
不同 defect 落在不同相位 —— 拿這些小片互相對位，根本沒有共同的東西可以對。

但 patch 是從機台吐出的**大圖**上裁下來的，而大圖裡有好幾個週期。
所以把方向反過來：在大圖上疊出一個乾淨的週期當模板，再把小 patch 滑進去。
模板比 patch 大，這才是一個有唯一解的問題。

所以測試斷言的是：
1. 框跟著相位跑，而且**框裡真的是使用者標的那種材質**；
2. 亮度／對比變了還是對得上（NCC 的重點）；
3. 定不出來的 patch **講出來**，不是靠運氣給一個位置；
4. 模板的原點錨得住 —— 換一批資料重算，框不可以平移。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from adept.core.algo import template as algo_template  # noqa: E402
from adept.core.pipeline import ParamError, get_step  # noqa: E402
from adept.core.pipeline.context import Context  # noqa: E402
from adept.core.pipeline.step import StepError  # noqa: E402
from adept.core.steps._util import roi_pixels  # noqa: E402

PERIOD = 40
BIG_H = 240
N_CELLS = 8
PATCH = 32          # 比一個週期小 —— 這正是整件事的前提


def big_image(seed: int = 0, gain: float = 1.0, offset: float = 0.0,
              noise: float = 4.0) -> np.ndarray:
    """機台吐出的大圖：MG | 亮交界 | EPI | 亮交界，重複 8 次。"""
    rng = np.random.default_rng(seed)
    img = np.zeros((BIG_H, PERIOD * N_CELLS), np.float32)
    for k in range(N_CELLS):
        x = k * PERIOD
        img[:, x:x + PERIOD] = 120.0            # MG
        img[:, x + 14:x + 34] = 60.0            # EPI（暗）
        img[:, x + 12:x + 16] = 210.0           # 交界（最亮）
        img[:, x + 32:x + 36] = 210.0
    return img * gain + offset + rng.normal(0, noise, img.shape).astype(np.float32)


def cut(img: np.ndarray, phase: int, y: int = 100) -> np.ndarray:
    """從大圖上裁一張 patch（相位 = 落在週期的哪裡）。"""
    x = 3 * PERIOD + phase
    return img[y:y + PATCH, x:x + PATCH]


def flat_patch(seed: int = 0) -> np.ndarray:
    """整張都在 EPI 裡面 —— 沒有任何東西可以定位。"""
    rng = np.random.default_rng(seed)
    return np.full((PATCH, PATCH), 60.0, np.float32) + \
        rng.normal(0, 4.0, (PATCH, PATCH)).astype(np.float32)


def epi_regions(cell: np.ndarray, name: str = "epi") -> str:
    """``epi_band`` 的區域字串形式（卡片參數用）。"""
    from adept.core.pipeline.cellrois import format_cell_rois
    return format_cell_rois([(name, [epi_band(cell)])])


def epi_band(cell: np.ndarray):
    """在 GC 上找出 EPI 那一段（= 使用者會標的框），回傳正規化矩形。"""
    prof = cell.mean(axis=0)
    dark = np.where(prof < 90)[0]
    lo, hi = int(dark.min()), int(dark.max()) + 1
    w = cell.shape[1]
    return (lo / w, 0.0, (hi - lo) / w, 1.0)


# --------------------------------------------------------------------------- #
# 1. 疊模板
# --------------------------------------------------------------------------- #
def test_the_period_is_measured_from_the_big_image_not_asked_for():
    """週期在大圖上量得到，所以不必請使用者填 —— 那是這條路的好處之一。"""
    gc = algo_template.build_golden_cell(big_image())
    assert gc.px == PERIOD
    assert gc.n_cells >= N_CELLS - 1
    assert gc.ghosting > 50.0, "疊得夠銳利（週期估錯的話會糊掉）"


def test_a_one_dimensional_layout_is_normal_not_a_failure():
    """垂直條紋在 Y 上量不到週期 —— 那是**正確的**，不是失敗。

    第一版把它當失敗擋掉了，於是使用者最常見的 layout 直接不能用。
    """
    gc = algo_template.build_golden_cell(big_image())
    assert gc.periodic == (True, False)
    assert gc.py == BIG_H, "沒有週期的那一軸取整張影像的長度"
    assert gc.cell.size > 0
    assert any("no period down" in w for w in gc.warnings)


def test_an_image_with_no_repeat_at_all_says_so_instead_of_guessing():
    rng = np.random.default_rng(1)
    noise = rng.normal(120.0, 6.0, (128, 128)).astype(np.float32)
    gc = algo_template.build_golden_cell(noise)
    assert gc.cell.size == 0
    assert any("periodic layout" in w for w in gc.warnings)


def test_the_cell_is_anchored_to_a_landmark_so_it_does_not_drift():
    """**這條是模板法最容易安靜壞掉的地方。**

    ``choose_origin`` 挑的是「疊起來最銳利」的相位 —— 但週期性影像的任何相位都
    一樣銳利，所以它在等價的候選之間挑哪一個是任意的。換一批資料重算模板，
    相位一變，使用者標在模板上的框就跟著平移了，而且畫面上不會有任何錯誤訊息。
    """
    profiles = [algo_template.build_golden_cell(big_image(seed)).cell.mean(axis=0)
                for seed in (0, 7, 11, 23)]
    # 不看「最亮的欄在哪」—— 亮帶有好幾欄一樣亮，argmax 會被雜訊決定。
    # 要問的是**整條曲線是不是同一條**：那才是「標在模板上的框不會平移」。
    base = profiles[0]
    for i, prof in enumerate(profiles[1:], 1):
        assert float(np.max(np.abs(prof - base))) < 8.0, \
            "第 %d 份模板跟第一份對不起來（相位漂移了）" % i

    # 而且錨定的目標真的達成了：最強的上升邊被捲到第 0 欄
    for prof in profiles:
        grad = np.roll(prof, -1) - np.roll(prof, 1)
        assert int(np.argmax(grad)) % len(prof) <= 1


def test_anchoring_leaves_an_axis_alone_when_it_has_no_landmark():
    """硬要錨一個不存在的地標，等於用雜訊決定相位 —— 比不錨還糟。"""
    flat = np.full((16, 16), 100.0, np.float32)
    out, roll = algo_template.anchor_cell(flat)
    assert roll == (0, 0)
    assert np.array_equal(out, flat)


# --------------------------------------------------------------------------- #
# 2. 存進 recipe（純文字）
# --------------------------------------------------------------------------- #
def test_the_template_round_trips_through_plain_text():
    """recipe 必須是**一個可以寄給別人的純文字檔** —— 存路徑的話，圖被換掉之後
    結果會安靜地變。"""
    gc = algo_template.build_golden_cell(big_image())
    text = algo_template.encode_cell(gc.cell)

    assert text.startswith(algo_template.CELL_ENCODING + ":")
    assert text.isascii(), "必須是純 ASCII，否則進不了 JSON、也過不了 DLP"
    assert np.array_equal(algo_template.decode_cell(text), gc.cell)


@pytest.mark.parametrize("bad", ["", "not a template", "gc1:oops",
                                 "gc1:4x4:!!!!", "png:4x4:AAAA"])
def test_a_broken_template_string_decodes_to_nothing_instead_of_raising(bad):
    assert algo_template.decode_cell(bad) is None


# --------------------------------------------------------------------------- #
# 3. 比對
# --------------------------------------------------------------------------- #
def test_the_phase_moves_one_for_one_with_the_cut():
    """patch 往右裁 1 px，相位就該往右 1 px。這是「定位真的成立」的核心。"""
    gc = algo_template.build_golden_cell(big_image())
    img = big_image(5)
    base = None
    for cut_at in range(0, PERIOD, 4):
        m = algo_template.match_patch(gc.cell, cut(img, cut_at),
                                      periodic=gc.periodic)
        assert m.ok, "cut@%d 沒有對上" % cut_at
        if base is None:
            base = (m.phase_x - cut_at) % PERIOD
        assert (m.phase_x - cut_at) % PERIOD == base, \
            "相位沒有跟著裁切位置線性移動（cut@%d)" % cut_at


def test_brightness_and_contrast_changes_do_not_break_the_match():
    """大圖與 patch 是不同時間、不同增益拍的 —— 這是用 NCC 的唯一理由。"""
    gc = algo_template.build_golden_cell(big_image())
    for gain, offset in ((0.6, 40.0), (1.5, -30.0), (1.0, 0.0)):
        m = algo_template.match_patch(
            gc.cell, cut(big_image(9, gain=gain, offset=offset), 17),
            periodic=gc.periodic)
        assert m.ok, "gain=%.1f offset=%.0f 對不上" % (gain, offset)
        assert m.score > 0.9


def test_a_featureless_patch_is_refused_however_lucky_the_correlation_is():
    """**只看分數是不夠的**，實測過：32 寬的純雜訊曲線跟模板的隨機相關
    標準差約 1/√32 ≈ 0.18，靠運氣就拿得到 0.5。所以先問「這張有結構嗎」。
    """
    gc = algo_template.build_golden_cell(big_image())
    lucky = 0
    for seed in range(20):
        m = algo_template.match_patch(gc.cell, flat_patch(seed),
                                      periodic=gc.periodic)
        assert m.ok is False, "seed=%d 的純雜訊被當成對上了" % seed
        assert m.structure < 5.0
        lucky = max(lucky, m.score)
    assert lucky > 0.35, "前提：分數確實會靠運氣衝高，所以不能只看分數"


def test_structure_separates_the_two_populations_by_an_order_of_magnitude():
    gc = algo_template.build_golden_cell(big_image())
    real = [algo_template.match_patch(gc.cell, cut(big_image(s), 7),
                                      periodic=gc.periodic).structure
            for s in range(5)]
    none = [algo_template.match_patch(gc.cell, flat_patch(s),
                                      periodic=gc.periodic).structure
            for s in range(5)]
    assert min(real) > 10 * max(none)


def test_matching_a_direction_that_does_not_repeat_only_dilutes_the_peak():
    """一維 layout 硬要在兩軸上搜尋，會把峰的突出程度稀釋掉 ——
    也就是把「定得出來」誤判成「定不出來」。"""
    gc = algo_template.build_golden_cell(big_image())
    patch = cut(big_image(3), 11)
    right = algo_template.match_patch(gc.cell, patch, periodic=(True, False))
    both = algo_template.match_patch(gc.cell, patch, periodic=(True, True))
    assert right.margin > both.margin


# --------------------------------------------------------------------------- #
# 4. 把框搬到 patch 上
# --------------------------------------------------------------------------- #
def test_a_box_marked_on_the_cell_lands_on_the_right_material_every_time():
    """**整張卡存在的理由。** 標一次，每張 patch 都框到同一種材質。"""
    gc = algo_template.build_golden_cell(big_image())
    norm = epi_band(gc.cell)
    img = big_image(4)

    for cut_at in range(0, PERIOD, 5):
        patch = cut(img, cut_at)
        m = algo_template.match_patch(gc.cell, patch, periodic=gc.periodic)
        boxes = algo_template.roi_boxes_in_patch(
            norm, m, gc.cell.shape, patch.shape, periodic=gc.periodic)
        assert boxes, "框一份都沒落進 patch（cut@%d)" % cut_at
        for x, _y, w, _h in boxes:
            assert float(patch[:, x:x + w].mean()) < 90.0, \
                "cut@%d 框到的不是 EPI（平均 %.1f）" % (
                    cut_at, patch[:, x:x + w].mean())


def test_every_copy_of_the_region_in_the_patch_gets_a_box():
    """框是**整片鋪過去**的：一格在 patch 裡出現幾次就畫幾個框。

    只取「離缺陷最近的那一份」是舊行為，而它在 cell 比 patch 小的時候會
    **只量到一根 EPI，其餘的靜靜漏掉** —— 使用者標的是重複結構上的一塊
    （「EPI 扣掉 MG 交集」），那種東西在圖上有幾份就該量幾份。
    """
    gc = algo_template.build_golden_cell(big_image())
    norm = epi_band(gc.cell)
    # 這裡刻意讓 patch 比一格大（3 格），模擬「cell 比 patch 小」那一邊
    wide = big_image(5)[100:100 + PATCH, 3 * PERIOD:6 * PERIOD]
    m = algo_template.match_patch(gc.cell, wide, periodic=gc.periodic)
    boxes = algo_template.roi_boxes_in_patch(
        norm, m, gc.cell.shape, wide.shape, periodic=gc.periodic)

    assert len(boxes) >= 3, "3 格寬的 patch 只拿到 %d 個框" % len(boxes)
    for x, _y, w, _h in boxes:
        assert float(wide[:, x:x + w].mean()) < 90.0
    starts = sorted(b[0] for b in boxes)
    assert all(abs((b - a) - PERIOD) <= 2 for a, b in zip(starts, starts[1:])), \
        "相鄰兩份的間距應該就是一個週期，實際 %s" % starts


def test_the_box_nearest_the_defect_is_among_them():
    """缺陷永遠在 patch 正中央，所以中間那一份一定要在（截斷時也留它）。"""
    gc = algo_template.build_golden_cell(big_image())
    patch = cut(big_image(6), 0)
    m = algo_template.match_patch(gc.cell, patch, periodic=gc.periodic)
    boxes = algo_template.roi_boxes_in_patch(
        epi_band(gc.cell), m, gc.cell.shape, patch.shape,
        periodic=gc.periodic)
    centre = patch.shape[1] / 2.0
    assert boxes
    nearest = min(abs(x + w / 2.0 - centre) for x, _y, w, _h in boxes)
    assert nearest <= PERIOD / 2.0 + 1


def test_a_region_that_falls_between_two_patches_gets_no_box_at_all():
    """**空的是一個合法答案**，不是「算不出來」。

    模板比 patch 大的時候，這張 patch 只看得到 cell 的一部分 —— 標在別處的
    區域就是不在這一顆上。舊行為是「照樣回離中心最近的那一份」，於是呼叫端
    拿到一個**整個在畫面外**的框，再靠事後裁切發現不對；現在直接回空的，
    而卡片把它記成「這一顆沒有這個區域」（不是退回整張圖）。
    """
    gc = algo_template.build_golden_cell(big_image())
    patch = cut(big_image(6), 0)
    m = algo_template.match_patch(gc.cell, patch, periodic=gc.periodic)
    # 相位 8、一格 40 px：這個框的每一份都剛好落在 patch 的兩側
    assert m.phase_x == 8
    assert algo_template.roi_boxes_in_patch(
        (0.0, 0.0, 0.2, 1.0), m, gc.cell.shape, patch.shape,
        periodic=gc.periodic) == []


def test_too_many_copies_keeps_the_ones_nearest_the_defect():
    """細到放不下的時候留中間那些 —— 缺陷在正中央（同 roi_cross 的 max_boxes）。"""
    gc = algo_template.build_golden_cell(big_image())
    wide = big_image(7)[100:100 + PATCH, 0:PERIOD * 6]
    m = algo_template.match_patch(gc.cell, wide, periodic=gc.periodic)
    boxes = algo_template.roi_boxes_in_patch(
        epi_band(gc.cell), m, gc.cell.shape, wide.shape,
        periodic=gc.periodic, max_boxes=2)
    assert len(boxes) == 2
    centre = wide.shape[1] / 2.0
    assert all(abs(x + w / 2.0 - centre) < PERIOD * 1.5
               for x, _y, w, _h in boxes)


def test_a_direction_with_no_period_takes_the_whole_patch():
    """沒有週期就沒有相位可言 —— 那個方向硬給一個位置等於憑空捏造資訊。"""
    gc = algo_template.build_golden_cell(big_image())
    patch = cut(big_image(2), 9)
    m = algo_template.match_patch(gc.cell, patch, periodic=gc.periodic)
    boxes = algo_template.roi_boxes_in_patch(
        (0.2, 0.3, 0.3, 0.2), m, gc.cell.shape, patch.shape,
        periodic=gc.periodic)
    assert boxes
    assert all((y, h) == (0, patch.shape[0]) for _x, y, _w, h in boxes)


# --------------------------------------------------------------------------- #
# 5. 卡片
# --------------------------------------------------------------------------- #
def _params(gc, **over):
    p = dict(source="ref", template=algo_template.encode_cell(gc.cell),
             locate_axis="x", regions=epi_regions(gc.cell))
    p.update(over)
    return p


def _run(ctx, params):
    return get_step("roi_template")().run(ctx, params)


def test_the_card_places_the_region_and_reports_the_evidence():
    gc = algo_template.build_golden_cell(big_image())
    img = big_image(8)
    for cut_at in (0, 13, 27, 35):
        patch = cut(img, cut_at)
        ctx = Context(images={"ref": patch, "test": patch})
        _run(ctx, _params(gc))
        assert ctx.features["locate_ok"] == 1.0
        assert ctx.features["epi_present"] == 1.0
        vals = roi_pixels(ctx, "t", patch, "epi")
        assert float(vals.mean()) < 90.0
        assert ctx.features["match_score"] > 0.9
        assert ctx.features["match_structure"] > 10.0


def test_a_card_can_define_several_regions_at_once():
    """一張卡好幾個區域 —— 「EPI 扣掉 MG 交集」那種形狀就是這樣表達的。"""
    gc = algo_template.build_golden_cell(big_image())
    patch = cut(big_image(9), 17)
    ctx = Context(images={"ref": patch})
    epi = epi_band(gc.cell)
    regions = "epi: %s | mg: 0,0,0.25,1" % ",".join(
        str(round(v, 4)) for v in epi)
    _run(ctx, _params(gc, regions=regions))

    assert set(ctx.roi_names()) >= {"epi", "mg"}
    assert ctx.features["epi_present"] == 1.0
    assert ctx.features["mg_present"] == 1.0


def test_one_region_can_be_several_rectangles():
    """一個名字好幾個矩形，量測時是**一個像素母體**（同 roi_cross 的多框）。"""
    gc = algo_template.build_golden_cell(big_image())
    patch = cut(big_image(10), 5)
    ctx = Context(images={"ref": patch})
    lo, _y, w, _h = epi_band(gc.cell)
    half = w / 2.0
    regions = "epi: %.4f,0,%.4f,1; %.4f,0,%.4f,1" % (lo, half, lo + half, half)
    _run(ctx, _params(gc, regions=regions))

    assert ctx.roi_count("epi") >= 2
    assert float(roi_pixels(ctx, "t", patch, "epi").mean()) < 90.0


def test_the_card_falls_back_and_marks_the_defect_when_it_cannot_locate():
    gc = algo_template.build_golden_cell(big_image())
    ctx = Context(images={"ref": flat_patch(3)})
    _run(ctx, _params(gc))

    assert ctx.features["locate_ok"] == 0.0
    assert ctx.features["epi_present"] == 0.0
    assert ctx.roi_rect("epi", (PATCH, PATCH)) == (0, 0, PATCH, PATCH)
    assert any("locate_ok" in w for w in ctx.meta.get("warnings", []))


def test_a_region_that_misses_this_patch_says_so_instead_of_measuring_everything():
    """模板比 patch 大 → 某些顆的窗就是沒蓋到某個區域。

    **不可以退回整張圖**：那會安靜地把所有像素都算進去，而那是錯的。
    這一顆的那個區域就是沒有，而下游要問得出真正的原因。
    """
    gc = algo_template.build_golden_cell(big_image())
    patch = cut(big_image(11), 0)
    ctx = Context(images={"ref": patch})
    # 一個窄到只有一格 2% 的框，擺在離相位最遠的地方 —— 落不進這張 patch
    _run(ctx, _params(gc, regions="epi: 0.49,0,0.02,1", max_boxes=64))

    if ctx.features["epi_present"] == 0.0:
        assert "epi" not in ctx.roi_names()
        assert "regions_absent" in ctx.meta
        with pytest.raises(StepError) as e:
            roi_pixels(ctx, "t", patch, "epi")
        assert "not on this defect" in str(e.value)


def test_a_card_without_a_template_says_where_to_get_one():
    """沒有模板不是「跑出壞結果」，是**還沒設定完** —— 要講清楚去哪裡設定。"""
    ctx = Context(images={"ref": flat_patch(0)})
    with pytest.raises(StepError) as e:
        _run(ctx, dict(source="ref", template="", regions="epi: 0,0,1,1"))
    assert "Edit template & regions" in str(e.value)


def test_a_card_with_no_regions_says_where_to_draw_them():
    """框畫不出來的地方在編輯器上，不是在參數表單上 —— 要指過去。"""
    gc = algo_template.build_golden_cell(big_image())
    ctx = Context(images={"ref": flat_patch(0)})
    with pytest.raises(StepError) as e:
        _run(ctx, _params(gc, regions=""))
    assert "no regions are marked" in str(e.value)
    assert get_step("roi_template").configuration_issues(
        {"template": "x", "regions": ""})


def test_the_panel_data_is_the_engines_own_calculation():
    gc = algo_template.build_golden_cell(big_image())
    patch = cut(big_image(1), 21)
    ctx = Context(images={"ref": patch})
    _run(ctx, _params(gc))

    panel = ctx.meta["templates"]["epi"]
    assert panel["cell_w"] == gc.cell.shape[1]
    assert panel["ok"] is True
    assert panel["phase_x"] == int(ctx.features["phase_x"])
    assert panel["boxes"], "面板要拿得到引擎真的放下去的框"
    import json
    json.dumps(panel)          # 面板資料要進得了快取的 meta 快照


def test_the_region_name_must_be_usable_as_a_variable_name():
    with pytest.raises(ParamError):
        get_step("roi_template").validate_params({"regions": "my region: 0,0,1,1"})


def test_the_card_declares_the_regions_it_defines():
    cls = get_step("roi_template")
    params = cls.validate_params({"regions": "epi: 0,0,1,1 | mg: 0,0,0.2,1"})
    assert cls.resolve_regions_out(params) == [
        "epi", "epi_center", "epi_others",
        "mg", "mg_center", "mg_others"]
    feats = cls.resolve_features(cls.validate_params(
        {"regions": "epi: 0,0,1,1", "output_prefix": "t"}))
    assert "t_locate_ok" in feats
    assert "t_epi_present" in feats
    assert "t_epi_others_present" in feats


def test_an_old_recipe_keeps_its_single_box_region():
    """舊檔的 ``roi_out`` + 四個座標 → ``regions``，結果不變（鐵則 9）。"""
    from adept.core.pipeline.recipe import Recipe

    doc = {"recipe_id": "r", "routes": {"main": ["n1"]},
           "score": {"expr": "0", "bins": []},
           "nodes": {"n1": {"id": "n1", "step": "roi_template",
                            "params": {"roi_out": "epi", "roi_x": 0.35,
                                       "roi_y": 0.0, "roi_w": 0.2,
                                       "roi_h": 1.0}}}}
    params = Recipe.from_json_dict(doc).nodes["n1"].params
    assert params["regions"] == "epi: 0.35,0,0.2,1"
    assert "roi_out" not in params and "roi_x" not in params


# --------------------------------------------------------------------------- #
# 6. 基準（<name>_others）—— 卡片不指派 target/reference
# --------------------------------------------------------------------------- #
def test_a_region_also_gives_the_rest_as_a_baseline():
    """「缺陷那一塊」跟「旁邊同材質那幾塊」要分得開。

    拿 ``<name>`` 當基準是**有偏的**：N 塊的時候缺陷佔 1/N 的像素，缺陷本身把
    基準往自己那邊拉。所以多一個 ``<name>_others``。
    """
    gc = algo_template.build_golden_cell(big_image())
    # 3 格寬的 patch -> 同一個區域在圖上有好幾份
    wide = big_image(12)[100:100 + PATCH, 3 * PERIOD:6 * PERIOD]
    ctx = Context(images={"ref": wide})
    _run(ctx, _params(gc))

    assert ctx.features["epi_present"] == 1.0
    assert ctx.features["epi_others_present"] == 1.0
    assert ctx.roi_count("epi_others") == ctx.roi_count("epi") - 1

    # center 不可以出現在 others 裡（那正是「基準被缺陷污染」的樣子）
    centre = ctx.roi_rect("epi_center", wide.shape[:2])
    rest = ctx.roi_rects("epi_others", wide.shape[:2])
    assert centre not in rest


def test_one_copy_means_there_is_no_baseline_and_it_says_so():
    """只有一份的時候框還在、但**沒有東西可以拿來比** —— 兩個不同的問題。"""
    gc = algo_template.build_golden_cell(big_image())
    patch = cut(big_image(13), 20)          # 32 px 的 patch、40 px 的一格
    ctx = Context(images={"ref": patch})
    _run(ctx, _params(gc))

    assert ctx.features["epi_present"] == 1.0
    assert ctx.features["epi_others_present"] == 0.0
    assert "epi_others" not in ctx.roi_names()
    with pytest.raises(StepError) as e:
        roi_pixels(ctx, "t", patch, "epi_others")
    assert "no other copy" in str(e.value)


def test_the_card_never_says_which_one_is_the_target():
    """**角色是「這一次比較」的屬性，不是區域的屬性。**

    同一塊 EPI 在一個比較裡是 target、在另一個裡是 reference（使用者定調）。
    所以 Region 卡只出名詞 —— 它不可以有任何一個叫 target/reference 的參數，
    也不可以在區域上標記角色。
    """
    cls = get_step("roi_template")
    names = {p["name"] for p in cls.describe()["params"]}
    assert not {n for n in names if "target" in n or "reference" in n}

    gc = algo_template.build_golden_cell(big_image())
    ctx = Context(images={"ref": cut(big_image(14), 7)})
    _run(ctx, _params(gc))
    assert all(r.roi_type == "reference" for r in ctx.rois.rois), \
        "vendored 的 target 型別是死的，不要把它救活（F11 §3.3.6）"


# --------------------------------------------------------------------------- #
# 7. 模板過期健檢（檔頭承諾了、而它一直不存在的那一支）
# --------------------------------------------------------------------------- #
def _judge(scores, margins, structures, **over):
    kw = dict(min_score=0.3, min_margin=0.05, min_structure=5.0)
    kw.update(over)
    return algo_template.judge_template(scores, margins, structures, **kw)


def test_a_template_that_fits_says_so():
    h = _judge([0.95] * 10, [0.40] * 10, [50.0] * 10)
    assert h.verdict == "ok"
    assert (h.located, h.checked) == (10, 10)


def test_patches_with_nothing_to_match_are_not_the_templates_fault():
    """「這批 patch 沒有結構」與「模板過期」長得一模一樣，而處置完全相反。"""
    h = _judge([0.5] * 10, [0.10] * 10, [1.0] * 10)
    assert h.verdict == "no-structure"
    assert "not the template" in h.message
    assert "No setting will change it" in h.message


def test_structure_but_no_resemblance_means_the_template_is_stale():
    """**這就是那個健檢要抓的東西**：有東西可比，但比出來不像。"""
    h = _judge([0.10] * 10, [0.02] * 10, [50.0] * 10)
    assert h.verdict == "stale"
    assert "rebuild it" in h.message


def test_matching_well_but_not_uniquely_is_a_threshold_problem():
    h = _judge([0.90] * 10, [0.01] * 10, [50.0] * 10)
    assert h.verdict == "too-tight"
    assert "Minimum certainty" in h.message


def test_a_few_bad_defects_do_not_condemn_the_template():
    """一兩顆爛的是常態 —— 中位數而不是平均，成功率而不是「有沒有失敗過」。"""
    h = _judge([0.95] * 9 + [0.05], [0.40] * 9 + [0.0], [50.0] * 9 + [0.5])
    assert h.verdict == "ok"
    assert h.located == 9 and h.checked == 10
    assert h.score > 0.9                       # 那一顆爛的沒有把中位數拉走


def test_no_run_yet_says_so_instead_of_guessing():
    h = _judge([], [], [])
    assert h.verdict == "unknown"
    assert "Run a trial" in h.message
    assert h.rate == 0.0

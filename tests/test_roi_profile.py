# F7-11 驗收：投影定位（找結構，而不是把框放在畫面的固定位置）。
"""這一段的前提是一個領域事實：

patch 是機台**以缺陷為正中心**裁出來的，所以缺陷永遠在中央 —— 但缺陷**周圍**
的東西每張都不一樣。中心固定框只對缺陷本身成立；只要框大過缺陷，它就可能在
某些 patch 上吃進別種材質，量出來的數字忽高忽低，而**變動的原因不是缺陷**。

所以測試斷言的不是「函式跑得動」，而是：
1. 框真的跟著結構跑（結構位移了，框也跟著位移）；
2. 沒有結構可認的 patch **講出來**，不是硬給一個位置。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from adept.core.algo import profile as algo_profile  # noqa: E402
from adept.core.pipeline import Recipe, RecipeNode, ScoreSpec, get_step, validate  # noqa: E402
from adept.core.pipeline.context import Context  # noqa: E402

W = H = 128


def _layout(shift: int = 0, noise: float = 3.0, seed: int = 0,
            defect: float = 0.0) -> np.ndarray:
    """MG | 亮交界 | EPI | 亮交界 | MG。``shift`` 把整個結構左右移動。

    這正是使用者描述的情況：EBI 鎖定在 EPI 上，所以每張 patch 裡一定有 EPI，
    但缺陷可能落在 EPI 的中間或靠邊，於是**結構在 patch 裡的位置逐顆不同**。
    """
    rng = np.random.default_rng(seed)
    img = np.full((H, W), 120.0, np.float32)          # MG
    lo, hi = 40 + shift, 88 + shift
    img[:, max(0, lo):max(0, hi)] = 60.0              # EPI（暗）
    for edge in (lo, hi):
        if 2 <= edge <= W - 2:
            img[:, edge - 2:edge + 2] = 210.0         # 交界（最亮）
    if defect:
        img[60:68, 60:68] += defect                   # 缺陷永遠在中央
    return img + rng.normal(0, noise, (H, W)).astype(np.float32)


def _run(ctx: Context, **params) -> Context:
    return get_step("roi_profile")().run(ctx, params)


# --------------------------------------------------------------------------- #
# 1. 演算法
# --------------------------------------------------------------------------- #
def test_the_band_follows_the_structure_not_the_screen():
    """**這條是整張卡存在的理由。** 結構左右移動時，框要跟著移動。

    如果框固定在畫面中央，位移大的那幾張就會框到別種材質 —— 那正是要避免的。
    """
    centres = []
    for shift in (-16, 0, 16):
        res = algo_profile.locate(_layout(shift), axis="x")
        assert res.picked is not None, "shift=%d 沒有找到任何一段" % shift
        centres.append((res.picked[0] + res.picked[1]) / 2.0)

    # 框的中心要跟著位移走（不是固定在 64）
    assert centres[0] < centres[1] < centres[2]
    for got, shift in zip(centres, (-16, 0, 16)):
        assert abs(got - (64 + shift)) < 6, \
            "框沒跟上結構：shift=%d 時框中心在 %.1f" % (shift, got)


def test_a_featureless_patch_reports_no_confidence_instead_of_a_position():
    """整張同一種材質的 patch **不可能**定位 —— 那是資訊不夠，不是演算法不夠。

    這種時候必須講出來，不能硬給一個位置。
    """
    rng = np.random.default_rng(3)
    flat = rng.normal(120.0, 6.0, (H, W)).astype(np.float32)
    assert algo_profile.locate(flat).confidence < 2.0

    # 有結構的差了一個數量級 —— 門檻放在個位數就分得很開
    assert algo_profile.locate(_layout()).confidence > 20.0


def test_confidence_survives_a_sharp_edge():
    """信心的分母必須用 MAD 而不是標準差。

    銳利的邊界會讓平滑吃掉一點真訊號，那幾格殘差很大；用標準差當分母，
    邊界越銳利分母被灌得越大 —— 變成「結構越清楚、信心越低」，完全相反。
    """
    soft = algo_profile.locate(_layout(noise=3.0)).confidence
    sharp = np.full((H, W), 120.0, np.float32)
    sharp[:, 64:] = 30.0
    sharp += np.random.default_rng(4).normal(0, 3.0, (H, W))
    assert algo_profile.locate(sharp).confidence > soft * 0.3
    assert algo_profile.locate(sharp).confidence > 20.0


def test_a_constant_slope_is_not_a_pile_of_boundaries():
    """一段固定斜率的漸層上每一格梯度都相等 —— 用 ``>=`` 找局部極大會把整段
    都判成轉折。斜率是背景漂移，該交給 Enhance 的背景平坦化卡。"""
    ramp = np.linspace(60.0, 180.0, W)[None, :].repeat(H, axis=0).astype(np.float32)
    prof, _ = algo_profile.projection(ramp, "x", smooth=1)
    assert algo_profile.find_transitions(prof) == []


def test_sensitivity_is_relative_so_it_carries_across_lots():
    """門檻是相對於「這張圖最陡的地方」，不是絕對灰階 ——
    所以整體亮度或對比變了，同一個設定還是找到同樣的邊界。"""
    a = _layout()
    b = a * 0.5 + 30.0                      # 對比砍半、整體提亮
    ta = algo_profile.locate(a).transitions
    tb = algo_profile.locate(b).transitions
    assert len(ta) == len(tb)
    for x, y in zip(ta, tb):
        assert abs(x - y) <= 2


def test_both_scan_directions_work():
    img = _layout().T.copy()                # 把結構轉成水平的
    assert algo_profile.locate(img, axis="y").picked is not None
    assert algo_profile.locate(img, axis="x").confidence < 2.0, \
        "轉錯方向就該看不到結構（這是使用者要能自己選方向的理由）"


def test_bands_cover_the_whole_curve_without_gaps():
    bands = algo_profile.bands_from([10, 40, 90], 128)
    assert bands == [(0, 10), (10, 40), (40, 90), (90, 128)]
    assert algo_profile.bands_from([], 128) == [(0, 128)]


@pytest.mark.parametrize("rule", list(algo_profile.PICK_RULES))
def test_every_pick_rule_returns_a_band(rule):
    res = algo_profile.locate(_layout(), rule=rule, index=1)
    assert res.picked is not None
    assert res.picked[1] > res.picked[0]


def test_degenerate_input_does_not_crash():
    for img in (np.zeros((0, 0), np.float32), np.zeros((2, 2), np.float32),
                np.full((8, 8), 7.0, np.float32)):
        res = algo_profile.locate(img)
        assert res.confidence >= 0.0


# --------------------------------------------------------------------------- #
# 2. 卡片
# --------------------------------------------------------------------------- #
def test_the_card_writes_a_named_region_that_tracks_the_structure():
    rects = []
    for shift in (-16, 16):
        ctx = Context(images={"ref": _layout(shift), "test": _layout(shift)})
        _run(ctx, source="ref", roi_out="epi")
        assert ctx.roi_names() == ["epi"]
        rects.append(ctx.roi_rect("epi", (H, W)))
    assert rects[0][0] < rects[1][0], "區域沒有跟著結構移動"


def test_the_neighbouring_sections_can_be_named_too():
    """量測幾乎都是成對的：訊號要跟**同一種材質**的背景比才有意義。"""
    ctx = Context(images={"ref": _layout()})
    _run(ctx, source="ref", roi_out="epi", also_neighbours=True)
    assert set(ctx.roi_names()) == {"epi", "epi_before", "epi_after"}
    a = ctx.roi_rect("epi", (H, W))
    before = ctx.roi_rect("epi_before", (H, W))
    assert before[0] < a[0], "before 應該在左邊"


def test_a_patch_with_nothing_to_lock_onto_falls_back_and_says_so():
    """跑得完、有數字、而且是錯的 —— 是這個工具最不能接受的失敗。"""
    rng = np.random.default_rng(9)
    ctx = Context(images={"ref": rng.normal(120.0, 6.0, (H, W)).astype(np.float32)})
    _run(ctx, source="ref", roi_out="epi")

    assert ctx.features["locate_ok"] == 0.0
    assert ctx.roi_rect("epi", (H, W)) == (0, 0, W, H), "退回整張圖"
    assert any("locate_ok" in w for w in ctx.meta.get("warnings", []))


def test_distance_to_the_boundary_is_reported_as_a_feature():
    """使用者原本把「缺陷可能靠中間、可能靠邊」當成一個麻煩 ——
    但它是一個可以拿去打分的數字。"""
    near = Context(images={"ref": _layout(shift=20)})   # 交界被推到接近中央
    far = Context(images={"ref": _layout(shift=0)})
    _run(near, source="ref")
    _run(far, source="ref")
    assert near.features["band_dist_px"] < far.features["band_dist_px"]


def test_the_panel_data_is_the_engines_own_calculation():
    """UI 自己再算一次，就有機會讓「畫面上的框」跟「真的量下去的框」不一樣。"""
    ctx = Context(images={"ref": _layout()})
    _run(ctx, source="ref", roi_out="epi")
    panel = ctx.meta["profiles"]["epi"]

    assert len(panel["profile"]) == W
    assert panel["picked"] is not None
    a, b = panel["picked"]
    x, _y, w, _h = ctx.roi_rect("epi", (H, W))
    assert x == a and w == b - a, "面板畫的段與寫進去的區域必須是同一個"
    # 純量與 list，能進 JSON（快取的 meta 快照會過濾掉不能序列化的東西）
    import json
    json.dumps(panel)


def test_the_output_names_can_be_prefixed():
    ctx = Context(images={"ref": _layout()})
    _run(ctx, source="ref", output_prefix="epi")
    assert "epi_locate_ok" in ctx.features
    assert "locate_ok" not in ctx.features


# --------------------------------------------------------------------------- #
# 3. 兩個區域一起量 —— 這是整件事的目的
# --------------------------------------------------------------------------- #
def _recipe() -> Recipe:
    """量 EPI，也量旁邊的 MG，兩組數字都要留得住。"""
    nodes = {
        "load": RecipeNode("load", "load_patch", {}),
        "loc": RecipeNode("loc", "roi_profile",
                          {"source": "ref", "roi_out": "epi",
                           "also_neighbours": True, "output_prefix": "loc"}),
        "g_epi": RecipeNode("g_epi", "glv_stats",
                            {"source": "test", "roi": "epi",
                             "metrics": "glv_mean", "output_prefix": "epi"}),
        "g_mg": RecipeNode("g_mg", "glv_stats",
                           {"source": "test", "roi": "epi_before",
                            "metrics": "glv_mean", "output_prefix": "mg"}),
    }
    return Recipe(recipe_id="two_regions",
                  routes={"ebi_patch": ["load", "loc", "g_epi", "g_mg"]},
                  nodes=nodes,
                  score=ScoreSpec(expr="epi_glv_mean - mg_glv_mean",
                                  threshold=0.0, bins={"below": 0, "above": 1}))


def test_measuring_two_regions_keeps_both_numbers():
    """沒有輸出名前綴的話，兩張 glv_stats 都寫 glv_mean，後面那張蓋掉前面那張。"""
    recipe = _recipe()
    issues = validate(recipe, kind="ebi_patch")
    assert [i for i in issues if i.code == "feature-collision"] == []
    assert [i for i in issues if i.level == "error"] == []

    feats = set()
    for nid in ("g_epi", "g_mg"):
        node = recipe.nodes[nid]
        feats |= set(get_step(node.step).resolve_features(node.params))
    assert feats == {"epi_glv_mean", "mg_glv_mean"}


def test_the_two_regions_really_measure_different_materials():
    """跑一顆真的資料：EPI 是暗的、旁邊的 MG 是亮的，數字必須分得開。"""
    from adept.core.pipeline.engine import run_defect

    class _Item:
        """最小的 DefectItem 替身：``load_patch`` 只用到 images 的鍵與 load()。"""

        defect_id = "d1"
        nm_per_px = None

        def __init__(self):
            self._data = {"test": _layout(defect=0.0), "ref": _layout()}
            self.images = dict(self._data)

        def load(self, channel):
            return self._data[channel]

    res = run_defect(_recipe(), _Item(), "ebi_patch", keep_context=True)
    assert res.ok is True, res.error
    assert res.features["epi_glv_mean"] < res.features["mg_glv_mean"] - 20.0

# F8 驗收：兩組正交條紋的交會處 → 一組方框（純規則，不需要外部檔案）。
"""使用者的需求，逐字保留：

> 「我還是希望有一種是不需要外部（單純靠純 rule）就能將 ROI 區域的 BOX 訂出來，
>   我本來預期投影要可以的 …
>   例如 patch 內我有 MG（Metal Gate）跟 EPI 位置，MG 是直的 EPI 是橫的，
>   我想要框的位置可能是 MG 跟 EPI 交界處（**在 EPI 上**）…
>   因為一張 patch 會有好幾根 MG 跟好幾根 EPI 所以 **ROI 會是分散的 BOX**」

他的直覺是對的：投影本來就做得到。``roi_profile`` 差的不是演算法，是最後一步
—— 它依設計只吐**一條滿版的條紋**（單軸投影對另一個方向一無所知，所以它拒絕
猜）。那個拒絕對**一次**投影是對的；它擋掉的是「再投影一次就量得到」。

所以測試斷言的不是「函式跑得動」，而是三件會出錯而且**不會報錯**的事：

1. 框真的落在**要的那種材質**上（差一個像素就吃到隔壁，而數字看起來完全正常）；
2. 結構相位變了，框跟著跑（框固定在畫面上的話，這張卡就沒有存在的理由）；
3. 定位不出來時**講出來、講出是哪個方向**，不是硬給一個位置。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from adept.core.algo import grid as algo_grid  # noqa: E402
from adept.core.pipeline import get_step  # noqa: E402
from adept.core.pipeline.context import Context  # noqa: E402
from adept.core.pipeline.step import StepError  # noqa: E402

SIZE = 128
MG_PITCH, MG_W = 24, 8          # 直的 Metal Gate（暗）
EPI_PITCH, EPI_W = 34, 14       # 橫的 EPI（亮）
BASE, EPI_LV, MG_LV = 90.0, 170.0, 45.0


def _mg_epi(ox: int = 0, oy: int = 0, noise: float = 2.0, seed: int = 0,
            epi_width: int = EPI_W, defect: float = 0.0) -> np.ndarray:
    """直的 MG（暗）壓在橫的 EPI（亮）上面。``ox``/``oy`` 是晶格相位。

    相位逐顆不同正是這件事的難處：patch 是以**缺陷**為中心裁的，不是以晶格
    為中心，所以「畫面上的固定位置」跨 defect 不成立。
    """
    rng = np.random.default_rng(seed)
    img = np.full((SIZE, SIZE), BASE, np.float32)
    if epi_width > 0:
        img[(np.arange(SIZE) + oy) % EPI_PITCH < epi_width, :] = EPI_LV
    img[:, (np.arange(SIZE) + ox) % MG_PITCH < MG_W] = MG_LV
    if defect:
        img[SIZE // 2 - 3:SIZE // 2 + 3, SIZE // 2 - 3:SIZE // 2 + 3] += defect
    return img + rng.normal(0, noise, (SIZE, SIZE)).astype(np.float32)


def _locate(img, **kw):
    kw.setdefault("placement", "beside_vertical")
    kw.setdefault("box_size", 5)
    kw.setdefault("inset", 3)
    return algo_grid.locate_crossings(img, **kw)


def _levels(img, boxes):
    return [float(img[y:y + h, x:x + w].mean()) for x, y, w, h in boxes]


# --------------------------------------------------------------------------- #
# 1. 演算法：框落在對的材質上
# --------------------------------------------------------------------------- #
def test_the_boxes_land_on_the_material_that_was_asked_for():
    """**這條是整張卡存在的理由。**

    「MG 跟 EPI 的交界，在 EPI 上」—— 框要全部落在 EPI（亮）上面。
    吃到一欄 MG 不會報錯，只會讓數字低一點，而那看起來完全正常。
    """
    img = _mg_epi()
    res = _locate(img)
    assert res.ok is True, res.reason
    assert len(res.boxes) > 4, "一張 128px 的 patch 上交會處不只四處"

    lv = _levels(img, res.boxes)
    assert min(lv) > EPI_LV - 8, \
        "有框吃到別種材質：最低的一個是 %.1f（EPI 應該是 %.0f）" % (min(lv), EPI_LV)
    assert float(np.std(lv)) < 3.0, "框跟框之間差太多，代表有幾個沒對準"


def test_leaving_no_clearance_quietly_poisons_the_numbers():
    """``gap`` 不是保險係數 —— 它擋掉一種安靜的錯。

    轉折是在**平滑過的**曲線上用中央差分找的，實測位置會早一格左右；而邊界
    本身在 SEM 上就糊在好幾個像素上。``gap=0`` 時 5px 的框吃進一欄另一種材質，
    平均值被拉掉一成多，**而那仍然是個看起來很正常的數字**。
    """
    img = _mg_epi()
    dirty = _levels(img, _locate(img, gap=0).boxes)
    clean = _levels(img, _locate(img, gap=1).boxes)

    assert min(dirty) < EPI_LV - 15, "這條測試的前提（gap=0 會吃到隔壁）不成立了"
    assert min(clean) > EPI_LV - 8
    assert np.std(dirty) > np.std(clean) * 5


def test_the_boxes_follow_the_lattice_phase():
    """相位逐顆不同 —— 框固定在畫面上的話這張卡就沒有意義。"""
    seen = []
    for ox in (0, 5, 11):
        res = _locate(_mg_epi(ox=ox))
        assert res.ok is True and res.center_box is not None
        seen.append(res.center_box[0])
    assert len(set(seen)) == 3, "相位換了三次，中心框卻沒有動：%s" % seen
    # 相位往右移，框跟著往右（不是隨機跳）
    assert seen[0] > seen[1] > seen[2] or seen[0] < seen[1] < seen[2]


# --------------------------------------------------------------------------- #
# 2. 已知 pitch（GDS 給的）能做什麼
# --------------------------------------------------------------------------- #
def test_a_known_pitch_fills_in_a_stripe_the_image_lost():
    """邊緣只露一半、對比不足的那幾根抓不到 —— 64px 的 patch 上線本來就沒幾根，
    漏一根影響很大。知道 pitch 就補得回來。"""
    faint = _mg_epi()
    faint[:, :MG_W] = BASE          # 把最左邊那根 MG 抹掉

    without = algo_grid.find_stripes(faint, axis="x", select="dark")
    with_pitch = algo_grid.find_stripes(faint, axis="x", select="dark",
                                        pitch=MG_PITCH)
    assert with_pitch.filled >= 1, "已知 pitch 卻沒有把漏掉的那根補回來"
    assert len(with_pitch.selected) > len(without.selected)
    assert with_pitch.pitch_used == pytest.approx(MG_PITCH)


def test_a_wrong_pitch_loses_to_the_image():
    """pitch 是外面（GDS）帶進來的假設，影像是這一顆真的長的樣子。

    兩者衝突時相信影像，並把證據（``pitch_error``）留下來讓上層講出來 ——
    安靜地照一個錯的 pitch 排格子，會給出一整排位置錯誤但看起來很整齊的框。
    """
    s = algo_grid.find_stripes(_mg_epi(), axis="x", select="dark",
                               pitch=MG_PITCH * 1.7)
    assert s.filled == 0
    assert s.pitch_error > 0
    assert s.pitch_used == pytest.approx(s.pitch_measured)
    assert s.pitch_measured == pytest.approx(MG_PITCH, abs=1.5)


def test_the_lattice_sits_on_the_stripe_centres_not_on_the_edges():
    """最容易做錯的一件事。

    一根寬 8、週期 24 的條紋，它的**邊界**間距是 8、16、8、16… 交錯的，
    只有**中心**才是每 24 一次。拿邊界去對等距晶格，會把一根條紋的兩條邊併成
    一格 —— 條紋寬度整個消失、框落到隨機的地方，**而且看起來還很像對的**。
    """
    s = algo_grid.find_stripes(_mg_epi(), axis="x", select="dark",
                               pitch=MG_PITCH)
    widths = [b - a for a, b in s.selected]
    assert all(abs(w - MG_W) <= 2 for w in widths), \
        "條紋寬度沒有保住：%s（應該都接近 %d）" % (widths, MG_W)
    assert s.pitch_measured == pytest.approx(MG_PITCH, abs=1.5)


# --------------------------------------------------------------------------- #
# 3. 做不到的時候要說出來，而且說得出是哪個方向
# --------------------------------------------------------------------------- #
def test_a_featureless_patch_is_reported_not_guessed():
    flat = np.random.default_rng(3).normal(120.0, 4.0, (SIZE, SIZE)).astype(np.float32)
    res = _locate(flat)
    assert res.ok is False and res.boxes == []
    assert res.confidence < 5.0


def test_it_says_which_direction_had_nothing_to_lock_onto():
    """「信心不足」只說得出「失敗了」。使用者下一步要做什麼（調哪一組參數、
    還是這種 patch 本來就沒有橫的條紋）完全取決於是哪一邊。"""
    res = _locate(_mg_epi(epi_width=0))          # 只有直的 MG，沒有橫的 EPI
    assert res.ok is False
    assert "flat stripes" in res.reason, res.reason
    assert res.x.confidence > 20.0 and res.y.confidence < 5.0


# --------------------------------------------------------------------------- #
# 4. 卡片：多框區域怎麼交出去
# --------------------------------------------------------------------------- #
def _ctx(**img_kw) -> Context:
    img = _mg_epi(**img_kw)
    return Context(images={"test": img.copy(), "ref": img.copy()})


def _run(ctx: Context, **params) -> Context:
    p = {"source": "ref", "place": "beside_vertical", "box_size": 5.0,
         "inset": 3.0, "vertical_pitch": MG_PITCH,
         "horizontal_pitch": EPI_PITCH}
    p.update(params)
    return get_step("roi_cross")().run(ctx, p)


def test_one_name_holds_every_box_and_center_holds_exactly_one():
    """交會處的數量隨影像而異，所以 recipe 不可能寫死 ``cross_0 … cross_n``。

    一個名字 = 一組框；要幾何的卡指 ``<name>_center``（缺陷所在的那一塊）。
    """
    ctx = _run(_ctx())
    assert ctx.roi_count("cross") > 4
    assert ctx.roi_count("cross_center") == 1
    # 名字列一次就好 —— 列成 ['cross', 'cross', …] 只會讓人以為自己接錯了
    assert ctx.roi_names().count("cross") == 1
    assert ctx.features["locate_ok"] == 1.0
    assert ctx.features["cross_count"] == float(ctx.roi_count("cross"))


def test_stats_are_measured_across_all_the_boxes():
    """統計量只需要「有哪些像素」，不需要它們排成什麼形狀 —— 所以分散的 N 個
    框對這類卡就是一個像素母體，而「這一組交界整體長什麼樣」也就問得出來。"""
    ctx = _run(_ctx())
    get_step("glv_stats")().run(ctx, {"source": "test", "roi": "cross",
                                      "metrics": "glv_mean,glv_std",
                                      "output_prefix": "epi"})
    assert ctx.features["epi_glv_mean"] == pytest.approx(EPI_LV, abs=6.0)

    # 整張圖的平均混了三種材質 —— 框確實有在挑東西
    get_step("glv_stats")().run(ctx, {"source": "test", "roi": "",
                                      "metrics": "glv_mean",
                                      "output_prefix": "whole"})
    assert ctx.features["whole_glv_mean"] < EPI_LV - 30


def test_a_card_that_needs_one_box_says_so_instead_of_taking_the_first():
    """安靜地拿第一個框，會給出一組看起來正常、實際上只描述了其中一塊的數字。
    訊息要**指得出路在哪**（去用 ``_center``）。"""
    ctx = _run(_ctx())
    with pytest.raises(StepError) as err:
        get_step("cd_measure")().run(ctx, {"source": "test", "roi": "cross"})
    msg = str(err.value)
    assert "cross_center" in msg and "separate boxes" in msg

    # 而 _center 走得通（它就是一個框）
    get_step("cd_measure")().run(ctx, {"source": "test", "roi": "cross_center"})
    assert "cd_x_px" in ctx.features


def test_failing_to_locate_falls_back_loudly():
    """退回整張圖是刻意的，但**一定要說出來** —— 不然使用者拿到的是一組看起來
    很正常、實際上量的是整張圖的數字。"""
    flat = np.random.default_rng(5).normal(120.0, 4.0, (SIZE, SIZE)).astype(np.float32)
    ctx = Context(images={"test": flat.copy(), "ref": flat.copy()})
    _run(ctx)

    assert ctx.features["locate_ok"] == 0.0
    assert ctx.roi_count("cross") == 1                 # 整張圖
    assert ctx.roi_rect("cross_center", (SIZE, SIZE)) == (0, 0, SIZE, SIZE)
    assert any("locate_ok = 0" in w for w in ctx.meta.get("warnings", []))


def test_the_card_declares_both_regions_so_lint_can_see_them():
    """量測卡指到沒人定義的區域是安靜出錯的老坑（§7）—— 兩個名字都要宣告
    得出來，lint 才擋得住打錯字。"""
    step = get_step("roi_cross")
    out = step.resolve_regions_out({"roi_out": "xing"})
    assert out == ["xing", "xing_center"]


def test_how_many_stripes_were_invented_is_visible():
    """框仍然對，但「憑什麼對」變成了那個 pitch —— 使用者有權知道自己站在哪一邊。"""
    faint = _mg_epi()
    faint[:, :MG_W] = BASE
    ctx = Context(images={"test": faint.copy(), "ref": faint.copy()})
    _run(ctx)
    assert ctx.features["cross_filled"] >= 1.0
    assert ctx.features["cross_pitch_x_px"] == pytest.approx(MG_PITCH)

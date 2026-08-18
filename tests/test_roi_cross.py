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
MG_PITCH, MG_W = 24, 8          # 直的 Metal Gate
EPI_PITCH, EPI_W = 34, 14       # 橫的 EPI
#: 灰階照站點回報的極性：**MG 最亮（約 220）、EPI 次之（約 180）**、其餘更暗。
#: 這件事值得照抄而不是隨便挑：極性反過來的話，「要哪一組」的預設值就會是錯的，
#: 而錯的結果是一組**看起來完全正常**的數字（框落在別種材質上）。
BASE, EPI_LV, MG_LV = 120.0, 180.0, 220.0


def _mg_epi(ox: int = 0, oy: int = 0, noise: float = 2.0, seed: int = 0,
            epi_width: int = EPI_W, defect: float = 0.0,
            poly: float = 0.0) -> np.ndarray:
    """直的 MG 壓在橫的 EPI 上面。``ox``/``oy`` 是晶格相位。

    相位逐顆不同正是這件事的難處：patch 是以**缺陷**為中心裁的，不是以晶格
    為中心，所以「畫面上的固定位置」跨 defect 不成立。

    ``poly`` > 0 時，在兩根 MG 之間再插一根**比較不亮**的直條紋 —— 那讓
    **直的那個方向有三層灰階**，也就是 ``second_brightest`` 要處理的情況。
    """
    rng = np.random.default_rng(seed)
    img = np.full((SIZE, SIZE), BASE, np.float32)
    if epi_width > 0:
        img[(np.arange(SIZE) + oy) % EPI_PITCH < epi_width, :] = EPI_LV
    col = (np.arange(SIZE) + ox) % MG_PITCH
    if poly > 0:
        img[:, (col >= MG_W + 4) & (col < MG_W + 4 + MG_W)] = float(poly)
    img[:, col < MG_W] = MG_LV
    if defect:
        img[SIZE // 2 - 3:SIZE // 2 + 3, SIZE // 2 - 3:SIZE // 2 + 3] += defect
    return img + rng.normal(0, noise, (SIZE, SIZE)).astype(np.float32)


def _locate(img, **kw):
    kw.setdefault("placement", "beside_vertical")
    kw.setdefault("box_size", 5)
    kw.setdefault("inset", 3)
    kw.setdefault("vertical_select", "brightest")     # MG 是最亮的那組欄
    kw.setdefault("horizontal_select", "brightest")   # EPI 是最亮的那組列
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
    # **極性會決定偏差往哪一邊倒**，所以這條刻意用「MG 比較暗」的那一種 ——
    # 站點的實際極性（MG 最亮）在這組參數下剛好不overlap，但那是巧合不是保證：
    # 邊界是混合區這件事跟誰亮誰暗無關，而 gap 擋的是那個。
    img = _mg_epi()
    img = np.where(img > (MG_LV + EPI_LV) / 2.0, BASE - 40.0, img).astype(np.float32)
    dirty = _levels(img, _locate(img, gap=0, vertical_select="darkest").boxes)
    clean = _levels(img, _locate(img, gap=1, vertical_select="darkest").boxes)

    assert min(dirty) < EPI_LV - 15, "這條測試的前提（gap=0 會吃到隔壁）不成立了"
    assert min(clean) > EPI_LV - 8
    assert np.std(dirty) > np.std(clean) * 5


def test_the_boxes_follow_the_lattice_phase():
    """相位逐顆不同 —— 框固定在畫面上的話這張卡就沒有意義。

    要問的是「跟著結構跑」而不是「往同一個方向移動」：``center_box`` 是**離
    patch 中心最近的那一個**，相位一移，最近的那根就換成隔壁那根，位置因此會
    跳一個 pitch。真正的不變量是**每一個框都還落在 EPI 上**。
    """
    seen = []
    for ox in (0, 5, 11, 17):
        img = _mg_epi(ox=ox)
        res = _locate(img)
        assert res.ok is True and res.center_box is not None
        lv = _levels(img, res.boxes)
        assert min(lv) > EPI_LV - 8, \
            "相位 %d 時有框掉出 EPI（最低 %.1f）" % (ox, min(lv))
        seen.append(tuple(b[0] for b in res.boxes[:4]))
    assert len(set(seen)) == 4, "相位換了四次，框卻停在原地：%s" % (seen,)


# --------------------------------------------------------------------------- #
# 2. 已知 pitch（GDS 給的）能做什麼
# --------------------------------------------------------------------------- #
def test_a_known_pitch_fills_in_a_stripe_the_image_lost():
    """邊緣只露一半、對比不足的那幾根抓不到 —— 64px 的 patch 上線本來就沒幾根，
    漏一根影響很大。知道 pitch 就補得回來。"""
    faint = _mg_epi()
    faint[:, :MG_W] = BASE          # 把最左邊那根 MG 抹掉

    # **這裡要 fill_rule="fill"**：抹成背景材質之後，那一格的灰階說的是
    # 「這裡沒有 MG」，而預設的 "skip" 就是在聽這句話（見
    # test_roi_cross_lattice.py）。這條測的是補線機制本身，所以明講要補。
    without = algo_grid.find_stripes(faint, axis="x", select="brightest")
    with_pitch = algo_grid.find_stripes(faint, axis="x", select="brightest",
                                        pitch=MG_PITCH, fill_rule="fill")
    assert with_pitch.filled >= 1, "已知 pitch 卻沒有把漏掉的那根補回來"
    assert len(with_pitch.selected) > len(without.selected)
    assert with_pitch.pitch_used == pytest.approx(MG_PITCH)


def test_a_wrong_pitch_loses_to_the_image():
    """pitch 是外面（GDS）帶進來的假設，影像是這一顆真的長的樣子。

    兩者衝突時相信影像，並把證據（``pitch_error``）留下來讓上層講出來 ——
    安靜地照一個錯的 pitch 排格子，會給出一整排位置錯誤但看起來很整齊的框。
    """
    s = algo_grid.find_stripes(_mg_epi(), axis="x", select="brightest",
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
    s = algo_grid.find_stripes(_mg_epi(), axis="x", select="brightest",
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
         "horizontal_pitch": EPI_PITCH,
         "vertical_select": "brightest", "horizontal_select": "brightest"}
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

    # 整張圖混了三種材質，框裡只有一種 —— 用**離散程度**比才問得出這件事
    # （平均值可能碰巧接近，那是巧合不是證據）。
    get_step("glv_stats")().run(ctx, {"source": "test", "roi": "",
                                      "metrics": "glv_std",
                                      "output_prefix": "whole"})
    assert ctx.features["whole_glv_std"] > ctx.features["epi_glv_std"] * 3


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
    """量測卡指到沒人定義的區域是安靜出錯的老坑（§7）—— **三個**名字都要宣告
    得出來，lint 才擋得住打錯字。

    第三個 ``_others`` 是 F11 Region-1 加的基準（除了缺陷那一塊以外的每一塊）。
    """
    step = get_step("roi_cross")
    out = step.resolve_regions_out({"roi_out": "xing"})
    assert out == ["xing", "xing_center", "xing_others"]


def test_how_many_stripes_were_invented_is_visible():
    """框仍然對，但「憑什麼對」變成了那個 pitch —— 使用者有權知道自己站在哪一邊。"""
    faint = _mg_epi()
    faint[:, :MG_W] = BASE
    ctx = Context(images={"test": faint.copy(), "ref": faint.copy()})
    _run(ctx, fill_rule="fill")          # 補線機制本身；預設的 skip 見 lattice
    assert ctx.features["cross_filled"] >= 1.0
    assert ctx.features["cross_pitch_x_px"] == pytest.approx(MG_PITCH)


# --------------------------------------------------------------------------- #
# 5. 三層以上的灰階（站點：MG 約 220 最亮、EPI 約 180 次之）
# --------------------------------------------------------------------------- #
def test_two_materials_in_one_direction_are_told_apart_by_rank():
    """中位數二分法會把 220 跟 180 併成「亮的那一組」—— 於是「我要第二亮的那組」
    講不出來。所以規則是排名：要第幾亮，就分幾群。"""
    img = _mg_epi(poly=185.0)          # 直的方向多一組比較不亮的條紋

    top = algo_grid.find_stripes(img, axis="x", select="brightest")
    second = algo_grid.find_stripes(img, axis="x", select="second_brightest")

    assert top.selected and second.selected
    assert not set(top.selected) & set(second.selected), "兩組挑到同一批條紋"

    # 段的邊界是**次像素**的（見 algo_grid.refine_edges），所以要切陣列得先取整
    prof = top.profile
    hi = np.mean([prof[int(a):int(b) + 1].mean() for a, b in top.selected])
    mid = np.mean([prof[int(a):int(b) + 1].mean() for a, b in second.selected])
    assert hi > mid + 8, "第二亮的那組沒有比最亮的暗（%.1f vs %.1f）" % (hi, mid)


def test_level_groups_splits_at_the_gaps_not_evenly():
    """材質之間的灰階差是一個個台階，台階之間的間隙遠大於材質內部的起伏 ——
    所以切在最大的間隙上。等分會把同一種材質切成兩半。"""
    levels = [120.0, 122.0, 119.0, 180.0, 181.0, 220.0, 219.0]
    groups = algo_grid.level_groups(levels, 3)
    assert groups[:3] == [0, 0, 0]         # 120 那三個同一群
    assert groups[3] == groups[4]          # 180 那兩個同一群
    assert groups[5] == groups[6]          # 220 那兩個同一群
    assert len(set(groups)) == 3


def test_the_rank_is_relative_so_a_gain_change_does_not_break_it():
    """整張圖亮度漂移不該讓「第幾亮」換人 —— 那正是不用絕對灰階的理由。"""
    img = _mg_epi(poly=185.0)
    a = algo_grid.find_stripes(img, axis="x", select="second_brightest")
    b = algo_grid.find_stripes(img * 0.75 + 20.0, axis="x",
                               select="second_brightest")
    # 次像素邊界比到小數點後幾位沒有意義（灰階換算會動到最後幾個 bit）——
    # 要問的是「挑到的是不是同一批條紋」。
    assert ([(round(x), round(y)) for x, y in a.selected]
            == [(round(x), round(y)) for x, y in b.selected])


# --------------------------------------------------------------------------- #
# 6. 交錯的 pitch（站點：EPI 與 EPI 之間有兩種間距）
# --------------------------------------------------------------------------- #
def _alternating(gap_a: int = 14, gap_b: int = 26, width: int = 10,
                 noise: float = 2.0, drop: int = -1) -> np.ndarray:
    """橫條紋的間距在兩個值之間交錯（寬、窄、寬、窄…）。

    ``drop`` >= 0 時把第幾根抹掉 —— 用來驗「已知 pitch 補得回漏掉的那一根」。
    """
    rng = np.random.default_rng(1)
    img = np.full((SIZE, SIZE), BASE, np.float32)
    y, i, kept = 6, 0, 0
    while y + width < SIZE:
        if kept != drop:
            img[y:y + width, :] = EPI_LV
        kept += 1
        y += width + (gap_a if i % 2 == 0 else gap_b)
        i += 1
    # 直的那組照樣要有 —— 交會處是兩組條紋**共同**定義的，少一組整張就定位不了，
    # 而這幾條測的是「交錯的間距」不是「單軸也能過」。
    img[:, np.arange(SIZE) % MG_PITCH < MG_W] = MG_LV
    return img + rng.normal(0, noise, (SIZE, SIZE)).astype(np.float32)


def test_two_alternating_pitches_are_accepted():
    """一個 pitch 描述不了「寬、窄、寬、窄」的排法 —— 硬用單一 pitch 去對，
    誤差會大到整組被丟掉，等於這個功能沒有用。"""
    img = _alternating()
    # 條紋寬 10、間距 14/26 → 中心距在 24 與 36 之間交錯
    both = algo_grid.find_stripes(img, axis="y", select="brightest",
                                  pitch=24.0, pitch_2=36.0)
    single = algo_grid.find_stripes(img, axis="y", select="brightest",
                                    pitch=24.0)

    assert both.pitches_used == [24.0, 36.0]
    assert both.pitch_error < single.pitch_error, (
        "交錯的 pitch 沒有比單一 pitch 更貼合（%.2f vs %.2f）"
        % (both.pitch_error, single.pitch_error))


def test_an_alternating_pitch_fills_in_a_missing_stripe():
    img = _alternating(drop=2)
    without = algo_grid.find_stripes(img, axis="y", select="brightest")
    filled = algo_grid.find_stripes(img, axis="y", select="brightest",
                                    pitch=24.0, pitch_2=36.0,
                                    fill_rule="fill")
    assert filled.filled >= 1, "抹掉的那一根沒有被補回來"
    assert len(filled.selected) > len(without.selected)


def test_the_card_passes_both_pitches_through():
    img = _alternating()
    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
    get_step("roi_cross")().run(ctx, {
        "source": "ref", "place": "crossing", "roi_out": "xing",
        "vertical_select": "brightest", "horizontal_select": "brightest",
        "horizontal_pitch": 24.0, "horizontal_pitch_2": 36.0})
    rec = ctx.meta["crossings"]["xing"]
    assert rec["y"]["pitches_used"] == [24.0, 36.0]
    # 兩種間距時「pitch 是多少」沒有單一答案 —— 特徵報的是平均
    assert ctx.features["cross_pitch_y_px"] == pytest.approx(30.0)


def test_an_old_recipe_still_loads_after_the_rank_rename():
    """F8 第一版只有兩層，「要哪一組」是 dark / bright。改成排名之後，
    舊檔案裡的那兩個值仍然說得通（就是排名的兩端）—— **相容性是檔案格式的事，
    不是把兩個意思一樣的選項留在下拉選單裡**。"""
    import json
    import tempfile

    from adept.core.pipeline import Recipe

    doc = {
        "recipe_id": "old", "version": 1,
        "routes": {"ebi_patch": ["load", "x"]},
        "nodes": {
            "load": {"step": "load_patch", "params": {}},
            "x": {"step": "roi_cross",
                  "params": {"vertical_select": "dark",
                             "horizontal_select": "bright"}},
        },
        "score": {"expr": "1", "threshold": 0.5},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as f:
        json.dump(doc, f)
        path = f.name

    r = Recipe.load(path)
    assert r.nodes["x"].params["vertical_select"] == "darkest"
    assert r.nodes["x"].params["horizontal_select"] == "brightest"


# --------------------------------------------------------------------------- #
# 7. 框不可以左右歪（試用回饋：「Box 目前好像左右會歪歪的」）
# --------------------------------------------------------------------------- #
def _blurred_mg(ox: int = 3) -> np.ndarray:
    """邊界糊掉的版本 —— 真實 SEM 的邊界佔好幾個像素，而**這個 bug 只在糊的
    邊界上出現**（銳利的階梯剛好沒有平台）。"""
    import cv2

    img = _mg_epi(ox=ox, noise=0.0)
    return cv2.GaussianBlur(img, (0, 0), 1.2)


def test_the_two_boxes_beside_a_stripe_are_the_same_distance_from_it():
    """**這是使用者回報的「左右歪歪的」。**

    ``|梯度|`` 的峰通常是 2 格寬的平台，而挑局部極大的規則左右不對稱
    （``> 左鄰`` 但 ``>= 右鄰``），於是同一根條紋的兩條邊各挑到平台的不同側 ——
    段往一邊胖一格，貼在兩側的框就一邊有縫一邊沒縫。

    兩個框量的是同一種材質，所以**數字上完全看不出來**，只有畫面上看得出來。
    """
    img = _blurred_mg()
    s = algo_grid.find_stripes(img, axis="x", select="brightest")
    spans = sorted(algo_grid._edge_spans(s.selected, 5.0, "both", 1.0, SIZE))

    checked = 0
    for a, b in s.selected:
        if a <= 0 or b >= SIZE - 1:
            continue                      # 邊緣被切掉的不算
        left = [t for t in spans if t[1] <= a]
        right = [t for t in spans if t[0] >= b]
        if not left or not right:
            continue
        gap_l = a - max(left, key=lambda t: t[1])[1]
        gap_r = min(right, key=lambda t: t[0])[0] - b
        assert abs(gap_l - gap_r) < 0.01, (
            "條紋 [%.1f, %.1f) 左縫 %.2f 右縫 %.2f —— 框歪了"
            % (a, b, gap_l, gap_r))
        checked += 1
    assert checked >= 3, "這條測試沒有真的檢查到幾根條紋"


def test_the_stripe_width_survives_the_edge_detection():
    """段寬要等於真實的條紋寬。差一格不會報錯，但它就是上一條那個歪掉的來源。"""
    s = algo_grid.find_stripes(_blurred_mg(), axis="x", select="brightest")
    widths = [b - a for a, b in s.selected if a > 0 and b < SIZE - 1]
    assert widths
    for w in widths:
        assert abs(w - MG_W) < 0.6, "段寬 %.2f，真值 %d" % (w, MG_W)


def test_every_box_has_the_width_that_was_asked_for():
    """切到影像邊緣而窄掉的框要**丟掉**，不是留一個比較短的。

    那幾個框的意義是「同一種東西的同一種取樣」；一個只有六成寬的殘框戴著同一個
    名字進 mask，統計上是稀釋、畫面上是那一排裡突然有一個比較短。
    """
    res = _locate(_blurred_mg(), box_size=5, gap=1)
    assert res.ok is True
    assert {w for _, _, w, _ in res.boxes} == {5}, \
        "框寬不只一種：%s" % sorted({w for _, _, w, _ in res.boxes})


# --------------------------------------------------------------------------- #
# 8. pitch 除不盡、以及線寬（試用回饋：1.5 nm/px 配 44 nm 的 pitch）
# --------------------------------------------------------------------------- #
def _lines(pitch_px: float, width_px: float = 12.0, jitter: float = 0.0,
           seed: int = 0, drop: int = -1):
    """以**非整數**週期畫直條紋（抗鋸齒），回 ``(影像, 真實的每一根)``。

    站點的實例：EBI 的 pixel size 1.5 nm、MG pitch 44 nm → 29.333 px。
    整數週期的合成資料驗不出「除不盡會怎樣」—— 那正是這幾條要問的事。
    """
    import cv2

    rng = np.random.default_rng(seed)
    img = np.full((SIZE, SIZE), BASE, np.float32)
    img[np.arange(SIZE) % 40 < 16, :] = EPI_LV
    truth, k = [], 0
    while True:
        c = 6.0 + k * pitch_px
        if c - width_px / 2.0 > SIZE:
            break
        w = width_px + (rng.normal(0, jitter) if jitter else 0.0)
        a, b = c - w / 2.0, c + w / 2.0
        if k != drop:
            xs = np.arange(SIZE)
            cover = np.clip(np.minimum(xs + 1, b) - np.maximum(xs, a), 0.0, 1.0)
            img[:, cover > 0.5] = MG_LV
        truth.append((a, b))
        k += 1
    return cv2.GaussianBlur(img, (0, 0), 1.2), truth


def test_a_pitch_that_does_not_divide_evenly_is_kept_as_a_fraction():
    """**pitch 常常除不盡**（1.5 nm/px × 44 nm = 29.333 px），而晶格是一路
    累加出來的 —— 自己先四捨五入成 29 的話，誤差會隨著離錨點越遠而越大。

    參數是 float、欄位收三位小數，所以照著填分數就好；這條鎖住「填分數真的
    比自己捨去準」。
    """
    img, truth = _lines(44.0 / 1.5)
    # **被影像邊界切到的不比** —— 它們只露一半，量到的中心依定義就是偏的。
    centres = [(a + b) / 2.0 for a, b in truth
               if a > 0.5 and b < SIZE - 0.5]

    def errors(p):
        s = algo_grid.find_stripes(img, axis="x", select="brightest", pitch=p)
        got = [(a + b) / 2.0 for a, b in s.selected
               if a > 0.5 and b < SIZE - 0.5]
        # 配**最近的**真值，不用索引 —— 錯的 pitch 會多生一根，索引就對不上了
        return [min(abs(g - c) for c in centres) for g in got]

    right, rounded = errors(29.333), errors(29.0)
    assert max(right) <= 0.6, "填了正確的分數，偏差仍有 %.2f px" % max(right)
    assert max(right) < max(rounded), \
        "填分數（%.2f）沒有比自己四捨五入（%.2f）準" % (max(right), max(rounded))


def test_the_lattice_never_quantises_the_pitch_it_was_given():
    """**晶格全程用浮點累加**，不會每走一步就捨一次。

    這是「pitch 除不盡照樣填得下去」的前提：1.5 nm/px 配 44 nm 的 pitch 是
    29.333… px，若晶格內部先捨成整數，第 k 根就會偏掉 k × 0.333 px ——
    而 patch 中央（缺陷所在）那幾根看起來還好好的，最外圍才歪掉。
    """
    pitch = 44.0 / 1.5
    lat = sorted(algo_grid._walk(20.0, [pitch], 400, 0))
    steps = [b - a for a, b in zip(lat, lat[1:])]
    assert steps == pytest.approx([pitch] * len(steps), abs=1e-9), \
        "每一步不是完整的 pitch：%s" % [round(v, 4) for v in steps[:5]]
    # 走 10 步之後仍然剛好在 10 個 pitch 上（沒有累積捨入誤差）
    i = lat.index(min(lat, key=lambda v: abs(v - 20.0)))
    assert lat[i + 10] - lat[i] == pytest.approx(10 * pitch, abs=1e-9)


def test_the_stripe_width_is_measured_not_assumed():
    """線寬**沒有**參數 —— 它是從影像量的。換一個線寬不必改 recipe。"""
    for width in (8.0, 12.0, 18.0):
        img, _ = _lines(44.0 / 1.5, width_px=width)
        s = algo_grid.find_stripes(img, axis="x", select="brightest")
        got = [b - a for a, b in s.selected if a > 1 and b < SIZE - 1]
        assert got, "width=%s 一根都沒抓到" % width
        assert all(abs(w - width) <= 1.0 for w in got), \
            "線寬 %s 量成 %s" % (width, [round(w, 2) for w in got])


def test_filling_in_the_pitch_does_not_flatten_the_line_widths():
    """**pitch 講的是「每隔多遠有一根」，它對線寬一個字都沒說。**

    早期版本把整排的寬度統一成中位數，於是 line-width roughness 被抹平 ——
    而框是貼著段的邊界放的，所以在**線寬異常的那一根**上，框會被推進 MG 裡面。
    最需要量準的那一根，量得最髒。
    """
    img, truth = _lines(44.0 / 1.5, jitter=1.6, seed=3)
    plain = algo_grid.find_stripes(img, axis="x", select="brightest")
    with_pitch = algo_grid.find_stripes(img, axis="x", select="brightest",
                                        pitch=29.333)

    w_plain = [b - a for a, b in plain.selected]
    w_pitch = [b - a for a, b in with_pitch.selected]
    assert len(set(round(w, 2) for w in w_pitch)) > 2, \
        "填了 pitch 之後寬度被統一了：%s" % [round(w, 2) for w in w_pitch]
    # 中段（沒被影像邊界切到的）要跟沒填 pitch 時量到的一樣
    assert w_pitch[1:-1] == pytest.approx(w_plain[1:-1], abs=0.6)


def test_only_the_invented_stripes_borrow_the_median_width():
    """補出來的那一根沒有自己的量測值 —— 它只能用中位數，而那要講得出來。"""
    img, truth = _lines(44.0 / 1.5, jitter=1.6, seed=3, drop=2)
    s = algo_grid.find_stripes(img, axis="x", select="brightest",
                               pitch=29.333, fill_rule="fill")
    assert s.filled >= 1
    widths = [b - a for a, b in s.selected]
    assert len(set(round(w, 2) for w in widths)) > 2, \
        "整排寬度不該被補線的那一根拉平：%s" % [round(w, 2) for w in widths]


def test_the_other_crossings_are_the_baseline():
    """「缺陷那一塊」跟「同一張圖上同材質的其餘那幾塊」要分得開（F11 Region-1）。

    拿 ``<name>`` 當基準是**有偏的**：N 塊的時候缺陷佔 1/N 的像素。
    """
    img = _mg_epi()
    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
    _run(ctx)

    n = ctx.roi_count("cross")
    assert n >= 2, "這張測試圖本來就該有好幾個交會處"
    assert ctx.roi_count("cross_others") == n - 1
    centre = ctx.roi_rect("cross_center", (SIZE, SIZE))
    assert centre not in ctx.roi_rects("cross_others", (SIZE, SIZE))


def test_one_crossing_means_there_is_no_baseline():
    """只有一塊的時候 ``_others`` **不存在** —— 這張圖上就是沒有基準。"""
    flat = np.full((SIZE, SIZE), BASE, np.float32)
    ctx = Context(images={"test": flat.copy(), "ref": flat.copy()})
    _run(ctx)                                   # 定位失敗 -> 只有「整張圖」一塊

    assert ctx.roi_count("cross") == 1
    assert "cross_others" not in ctx.roi_names()
    assert "no other copy" in ctx.meta["regions_absent"]["cross_others"]

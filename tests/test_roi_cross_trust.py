# F8 第六輪 (b)：批次跑完之後，那些數字能不能信。
"""使用者問的是「這樣的設定方法通用性會不會不夠 robust，我是要 batch 去跑
patch 的，然後也要能跨站點比」。量下來，最危險的不是「跑不出來」，是
**跑得出來而且看起來很正常，但框在錯的地方**。

實測 300 顆混合批次（相位隨機、雜訊/增益/偏壓漂移、一半有 CPODE）：

    定位錯誤 134 顆，其中 **68 顆的 ``pitch_error`` < 0.5**（很多是 0.00），
    而且信心值比正確的那些還高（285.9 vs 215.8）。

原因是 ``pitch_error`` 問的是「我挑的這幾根**等距**嗎」——鎖在空隙上的時候，
空隙也是完美等距的。真正該問的是「我挑**對**了嗎」，而那個問題有一個免費的
答案：**把量到的間距跟填進去的比一比**。

只擋小的那一邊，而這個不對稱有道理：
量到的比較小 = 挑進了不該挑的東西（補線救不了）；
量到的比較大 = 有幾根沒抓到（補線就是為了它）。
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

SIZE, MG_PITCH, MG_W, EPI_PITCH = 128, 24, 8, 34


def _img(cpode=(), pitch: int = MG_PITCH, w: int = MG_W, ox: int = 0,
         seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((SIZE, SIZE), 90.0, np.float32)
    img[np.arange(SIZE) % EPI_PITCH < 14, :] = 180.0
    img[:, (np.arange(SIZE) + ox) % pitch < w] = 220.0
    for site in cpode:
        lo = site * pitch - ox
        if 0 <= lo < SIZE:
            img[:, lo:lo + w] = 30.0
    return img + rng.normal(0, 2.0, (SIZE, SIZE)).astype(np.float32)


def _locate(img, **kw):
    p = dict(vertical_select="brightest", vertical_pitch=MG_PITCH,
             horizontal_pitch=EPI_PITCH, placement="beside_vertical",
             box_size=5.0)
    p.update(kw)
    return algo_grid.locate_crossings(img, **p)


# --------------------------------------------------------------------------- #
# 1. 擋得住那個安靜的錯答案
# --------------------------------------------------------------------------- #
def test_locking_onto_the_wrong_stripes_is_refused_not_reported_as_fine():
    """三種材質卻只分兩群 → 挑到的是 MG **加上空隙**，量到的間距剛好一半。

    這是 F8 到目前為止唯一一個「跑得完、有數字、而且是錯的」的失敗模式。
    """
    res = _locate(_img(cpode=(2, 5)))           # kinds 沒填
    assert res.ok is False
    assert "measure" in res.reason and "apart" in res.reason
    assert "how many kinds" in res.reason, "沒有講出使用者下一步該做什麼"


def test_the_same_image_set_up_right_goes_through():
    """擋掉錯的不能連對的一起擋 —— 不然這個檢查就只是把功能關掉。"""
    res = _locate(_img(cpode=(2, 5)), vertical_kinds=3)
    assert res.ok is True, res.reason
    assert len(res.boxes) > 4


def test_the_old_number_could_not_have_caught_it():
    """記錄**為什麼**需要新的檢查：舊的那個在這一顆上是滿分。"""
    s = algo_grid.find_stripes(_img(cpode=(2, 5)), axis="x",
                               select="brightest", pitch=MG_PITCH)
    assert s.pitch_error == pytest.approx(0.0, abs=0.05), (
        "pitch_error 是 %.2f —— 如果它抓得到，這條檢查就不必存在" % s.pitch_error)
    assert s.pitch_disagrees is True
    assert s.pitch_ratio == pytest.approx(0.5, abs=0.1)


# --------------------------------------------------------------------------- #
# 2. 只擋小的那一邊
# --------------------------------------------------------------------------- #
def test_missing_stripes_is_not_a_failure():
    """量到的**比較大** = 有幾根沒抓到，而補線就是為了它。把這一邊也擋掉的話，
    「敏感度差一點」會變成「整顆作廢」。

    （順帶：漏掉**幾根**現在根本不會讓量到的變大 —— ``measure_pitches`` 會把
    那些「兩倍」的間距除回去。要造出這個情況得**每隔一根就漏一根**，
    那時候整排的間距真的就是兩倍，沒有任何辦法從影像上分辨。）
    """
    img = _img()
    for k in (1, 3, 5):                  # 每隔一根就淡掉一根
        img[:, k * MG_PITCH:k * MG_PITCH + MG_W] = 150.0
    s = algo_grid.find_stripes(img, axis="x", select="brightest",
                               pitch=MG_PITCH)
    assert s.pitch_ratio > 1.5, "合成資料沒有真的漏掉那幾根（%.2f）" % s.pitch_ratio
    assert s.pitch_disagrees is False, "大的那一邊被擋掉了"
    assert _locate(img).ok is True


def test_a_pitch_from_another_tool_is_caught():
    """跨站點：同一份 recipe 換一台 pixel size 不同的機台。差得夠多的時候
    容差本來就擋得住，差得**不夠多**的時候才是問題 —— 實測填 24、真實 18
    的時候舊版收下了那個 pitch，框安靜地歪了 6.5 px。"""
    s = algo_grid.find_stripes(_img(pitch=18, w=6), axis="x",
                               select="brightest", pitch=MG_PITCH)
    assert s.pitch_ratio == pytest.approx(18.0 / 24.0, abs=0.1)
    assert s.pitch_disagrees is True


def test_no_pitch_given_means_nothing_to_disagree_with():
    """沒填 pitch 就沒有「對不對得上」這個問題 —— 不能因此判它失敗。"""
    s = algo_grid.find_stripes(_img(), axis="x", select="brightest")
    assert s.pitch_disagrees is False
    assert s.pitch_ratio == 0.0


# --------------------------------------------------------------------------- #
# 3. 批次看得到（這是整件事的目的）
# --------------------------------------------------------------------------- #
def _run(**over) -> Context:
    params = {"source": "ref", "place": "beside_vertical", "box_size": 5.0,
              "roi_out": "xing", "vertical_pitch": MG_PITCH,
              "horizontal_pitch": EPI_PITCH}
    params.update(over)
    img = _img(cpode=(2, 5))
    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
    get_step("roi_cross")().run(ctx, params)
    return ctx


def test_a_refused_defect_is_marked_so_the_batch_can_filter_it():
    """批次跑完之後唯一能問的東西是特徵表。定位失敗必須在那裡看得到，
    不然「跑完 200 顆」跟「跑完 200 顆而其中 90 顆是錯的」長得一樣。"""
    ctx = _run()
    assert ctx.features["locate_ok"] == 0.0
    assert any("locate_ok = 0" in w for w in ctx.meta.get("warnings", []))


def test_the_ratio_itself_is_a_feature():
    """0/1 答不出「錯得多嚴重」。0.50 是挑錯組、0.75 是 pitch 填錯 ——
    兩者的下一步不一樣，而分數表達式跟報表都指得到這個數字。"""
    ctx = _run()
    assert ctx.features["cross_pitch_ratio_x"] == pytest.approx(0.5, abs=0.1)
    ok = _run(vertical_kinds=3)
    assert ok.features["locate_ok"] == 1.0
    assert ok.features["cross_pitch_ratio_x"] == pytest.approx(1.0, abs=0.1)


def test_the_reason_says_which_direction_and_what_to_do():
    """使用者拿到的是一句話，而那句話要足以決定下一步。"""
    ctx = _run()
    warn = " ".join(ctx.meta.get("warnings", []))
    assert "upright" in warn
    assert "how many kinds" in warn

# -*- coding: utf-8 -*-
"""F58：拿一張 Golden Cell 鋪成整批資料 —— **週期量對了嗎**。

這支工具的一切都踩在一個數字上：**GC 的週期**。量錯的話每一格都錯位，
而鋪出來的圖看起來仍然像那個圖案 —— 跑得完、有資料、而且是錯的。

⚠ 這一輪為了這個數字改了三版，兩版都會鋪出錯位的圖。兩個坑各有一條測試：

* **固定寬度的比對視窗**（為了消掉「位移越大重疊越少越容易對上」的偏差）
  —— 那個視窗裝不下「哪一根缺席」這個地標，於是量到三根當成一個週期。
* **「第一個夠好的位移」當基頻** —— 五根的位移在重疊區裡也對得上
  （缺席的那一根剛好落在窗外），而它不是週期。

最後的判準是：**取最深的那一個，再問它是不是某個更小週期的整數倍**。

測試用的 GC 是**合成的**（`_synth_mgepi`）—— 真的那張是廠內圖案，
不進版控（鐵則 8）。合成那張的性質一樣：六根一個週期、第三根缺席。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (REPO, os.path.join(REPO, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _synth_mgepi as mgepi  # noqa: E402
import make_lot_from_gc as gcl  # noqa: E402
from d4t.core.ingest.dataset import load_dataset  # noqa: E402


G = mgepi.GEOMETRY
_SPAN = G.mg_pitch * G.period


def _gc_of(periods_x: float, periods_y: float = 2.15) -> np.ndarray:
    w = int(round(_SPAN * periods_x))
    h = int(round(G.epi_pitch * periods_y))
    return np.clip(mgepi.frame(h, w, G), 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def gc():
    """兩個多週期寬 —— **看得到兩個「缺席的位置」**，週期才定得下來。"""
    return _gc_of(2.4)


@pytest.fixture(scope="module")
def narrow_gc():
    """一個多週期寬 —— 跟使用者那張一樣的處境（205 px ≈ 1.16 個週期）。"""
    return _gc_of(1.16)


# --------------------------------------------------------------------------- #
# 1. 週期
# --------------------------------------------------------------------------- #
def test_it_finds_the_six_line_period_not_a_harmonic(gc):
    px, py = gcl.periods(gc)
    assert abs(px - _SPAN) < 1.0, "水平週期量成 %.2f，期望 %.2f" % (px, _SPAN)
    assert abs(py - G.epi_pitch) < 1.0


def test_it_does_not_settle_for_a_near_match_at_five_lines(gc):
    """⚠ 五根的位移在重疊區裡對得起來（缺席那一根落在窗外）—— 但它不是週期。

    量真的那張 GC：lag 147（五根）的平均差 8.00、176（六根）6.00，
    而「第一個夠好的」會挑 147。
    """
    px, _ = gcl.periods(gc)
    five = G.mg_pitch * 5
    assert abs(px - five) > 2.0, "挑到了五根（%.2f）" % px


def test_a_narrow_gc_cannot_pin_the_period_which_is_why_the_override_exists(
        narrow_gc):
    """⚠ **這一條記的是一個原理上的限制，不是一個 bug。**

    這個 layout 的週期靠「哪一根缺席」定義。位移五根的時候，缺席的那一根
    剛好落在重疊區外面 —— 兩個窗口都只有正常的根，**逐點相同**，量到的
    「週期」因此是五根。要分得出來得看到**兩個**缺席的位置。

    使用者那張真的 GC（205 px = 1.16 個週期）量出 175.96 是對的，但那是
    **真實影像的雜訊打破了平手**，不是因為資訊夠。所以 `generate` 收得下
    明講的週期，而這一條測的正是「明講的那個會贏」。
    """
    px, _ = gcl.periods(narrow_gc)
    assert abs(px - _SPAN) > 2.0, (
        "這張窄 GC 居然量對了（%.2f）—— 那表示這條測試的前提變了，"
        "回去看 `periods` 的說明還成不成立" % px)


def test_a_clean_multi_period_gc_gives_the_fundamental():
    """GC 裡裝三個完整週期時，要回**一個**週期，不是三個。

    ⚠ 這一條曾經被拿來論證一段「檢查它是不是某個更小週期的倍數」的程式碼，
    而突變測試證明**那段程式碼拿掉它照樣綠** —— 位移一個週期與三個週期的
    平均差都是 0，而取最小值本來就會回到前者。那段程式碼因此刪掉了：
    **一個做不出反例的防護，是一個沒有被驗證過的防護。**
    """
    w = int(round(_SPAN * 3))
    img = np.clip(mgepi.frame(int(G.epi_pitch * 3), w, G), 0, 255).astype(np.uint8)
    px, _ = gcl.periods(img)
    assert abs(px - _SPAN) < 1.5, "回了 %.2f，期望一個週期 %.2f" % (px, _SPAN)


def test_tiling_with_the_measured_period_has_no_seam(gc):
    """量對了的話，鋪出來的圖跟自己位移一個週期**逐點幾乎相同**。"""
    px, py = gcl.periods(gc)
    big = gcl.tile(gc, 400, 700, px, py)
    s = int(round(px))
    assert float(np.abs(big[:, :700 - s] - big[:, s:]).mean()) < 3.0


# --------------------------------------------------------------------------- #
# 2. 缺陷落點是量出來的，不是寫死的
# --------------------------------------------------------------------------- #
def test_the_inner_space_sites_sit_on_bright_epi_bands(gc):
    sites = gcl.inner_space_sites(gc)
    assert sites, "量不到任何 inner space"
    rows = gc.astype(np.float32).mean(axis=1)
    hi = float(rows.max())
    for _x, y in sites:
        assert rows[y] > 0.9 * hi, "y=%d 落在暗帶上（%.0f / %.0f）" % (y, rows[y], hi)


def test_the_sites_straddle_an_edge_not_a_flat_area(gc):
    """交界的意思是「兩邊不一樣」—— 落在一片均勻的地方就不是交界。"""
    g = gc.astype(np.float32)
    for x, y in gcl.inner_space_sites(gc):
        x0, x1 = max(0, x - 3), min(g.shape[1], x + 4)
        strip = g[max(0, y - 3):y + 4, x0:x1]
        assert float(strip.max() - strip.min()) > 20.0


# --------------------------------------------------------------------------- #
# 3. 兩份 lot 都要讀得回來
# --------------------------------------------------------------------------- #
def test_both_lots_load_back_through_ingest(tmp_path, gc):
    from d4t.core.ingest.dataset import load_dataset
    out = gcl.generate(str(tmp_path / "lot"), gc, images=2, size=900,
                       defects=12, patch=81, seed=3)
    rsem = load_dataset(out["rsem_klarf"])
    assert rsem.kind == "rsem" and len(rsem.items) == 2
    assert rsem.items[0].load("single").shape == (900, 900)
    patch = load_dataset(out["patch_klarf"])
    assert patch.kind == "ebi_patch" and len(patch.items) == 12
    first = patch.items[0]
    assert first.load("test").shape == (81, 81)
    assert first.load("ref").shape == (81, 81)


def test_the_reference_crop_is_not_the_same_pixels_as_the_test_crop(tmp_path, gc):
    """ref 取「往旁邊一個完整週期」—— 同樣的圖案、沒有這顆缺陷。

    取成同一塊的話 `subtract` 恆為零，而整條 pipeline 照樣跑得完。
    """
    from d4t.core.ingest.dataset import load_dataset
    out = gcl.generate(str(tmp_path / "lot"), gc, images=1, size=900,
                       defects=8, patch=81, real_frac=1.0, seed=4)
    ds = load_dataset(out["patch_klarf"])
    same = sum(1 for it in ds.items
               if np.array_equal(it.load("test"), it.load("ref")))
    assert same == 0, "%d 顆的 ref 跟 test 是同一塊" % same


def test_the_same_seed_gives_the_same_bytes(tmp_path, gc):
    import hashlib

    def sha(p):
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    a = gcl.generate(str(tmp_path / "a"), gc, images=2, size=900, defects=10,
                     patch=81, seed=9)
    b = gcl.generate(str(tmp_path / "b"), gc, images=2, size=900, defects=10,
                     patch=81, seed=9)
    assert sha(a["patch_tiff"]) == sha(b["patch_tiff"])
    assert [sha(p) for p in a["rsem_images"]] == [sha(p) for p in b["rsem_images"]]


def test_every_defect_type_is_planted_on_an_inner_space(gc):
    """使用者：「defect 都在這邊」。"""
    px, py = gcl.periods(gc)
    big = gcl.tile(gc, 300, 400, px, py)
    for kind in gcl.REAL_TYPES:
        img = big.copy()
        gcl.plant(img, kind, 200.0, 150.0, np.random.default_rng(1), px)
        assert float(np.abs(img - big).max()) >= 50.0, kind


def test_whatever_it_returns_tiles_seamlessly():
    """⚠ **這才是這支工具真正要的性質** —— 不是「數字最小」，是「鋪得準」。

    次像素位移要線性插值，而插值本身在高對比的圖上就要付約 1 GLV —— 於是
    **整數**位移（不必插值）永遠比非整數的漂亮一點。實測一張 1000² 的乾淨圖
    垂直真週期 34.0，量出來是 170（五倍）：34 要插值、170 剛好整數。

    那**沒有修**，因為倍數也是週期，鋪出來的圖一模一樣。所以這裡斷言的是
    性質不是數值 —— 拿它回的那個數字去鋪，接縫要對得起來。
    """
    G2 = mgepi.GEOMETRY
    img = np.clip(mgepi.frame(1000, 1000, G2), 0, 255).astype(np.uint8)
    px, py = gcl.periods(img)
    big = gcl.tile(img, 600, 600, px, py)
    sx, sy = int(round(px)), int(round(py))
    assert float(np.abs(big[:, :600 - sx] - big[:, sx:]).mean()) < 3.0
    assert float(np.abs(big[:600 - sy, :] - big[sy:, :]).mean()) < 3.0


def test_a_thin_bright_stripe_inside_the_space_is_not_an_mg_line(gc):
    """⚠ **這一條是突變測試逼出來的。**

    「交界要跨在兩種東西之間」那條測試**擋不住這件事** —— space 正中央那條
    細亮芯的左右緣也是貨真價實的交界，只是它不是 MG↔space 的交界。拿掉寬度
    篩選，那條測試照樣綠，而缺陷會有一半種在 space 中間。

    所以這裡鎖**數量**：一個週期上 MG 有 `period` 根、缺席一根，每根兩個
    交界 → 2 × (period − 1)。亮芯若也算進來會多一倍。
    """
    G2 = mgepi.GEOMETRY
    xs = sorted({x for x, _ in gcl.inner_space_sites(gc)})
    span = G2.mg_pitch * G2.period
    per_period = len([x for x in xs if x < span])
    want = 2 * (G2.period - 1)
    assert per_period <= want + 2, (
        "一個週期量到 %d 個交界，期望 ~%d —— 細亮芯大概也被當成 MG 了"
        % (per_period, want))


def test_defects_only_land_where_the_mask_says(tmp_path, gc):
    """⚠ **這是「畫在 GC 上」整件事的驗收**（F61）。

    使用者畫的那一塊會照週期鋪到大圖的每一個重複上。要驗那個「回推」對不對，
    麻煩的地方是每張大圖有自己的隨機相位，而相位沒有被記下來 —— 折回去就少
    一個未知數。

    **繞過它的方法是把未知數變成常數**：遮罩只留**一個**畫素、只產**一張**
    大圖。那麼所有缺陷都來自同一個 GC 座標、同一個相位，於是它們的 x 座標
    必須**兩兩相差週期的整數倍**。相位是多少完全不必知道。

    鋪錯的話（少乘一次週期、把 GC 座標當成大圖座標…）這一條立刻紅，
    而畫面上完全看不出來。
    """
    mask = np.zeros(gc.shape, dtype=bool)
    mask[11, 34] = True                      # 只准這一個點
    out = gcl.generate(str(tmp_path), gc=gc, images=1, size=900, defects=12,
                       patch=41, seed=5, sites=gcl.sites_from_mask(mask))
    px, py = out["period"]
    ds = load_dataset(out["patch_klarf"])
    assert len(ds.items) == 12
    xs = [float(d.xrel_nm) for d in ds.items]   # 1 nm = 1 px（見 KLARF 那一段）
    ys = [float(d.yrel_nm) for d in ds.items]

    def off_grid(vals, period):
        base = vals[0]
        return [v for v in vals
                if min((v - base) % period, period - (v - base) % period) > 1.5]

    assert not off_grid(xs, px), (
        "同一個 GC 座標種出來的缺陷，x 不是差週期的整數倍：%s（週期 %.2f）"
        % (sorted(xs), px))
    assert not off_grid(ys, py), (
        "y 不是差週期的整數倍：%s（週期 %.2f）" % (sorted(ys), py))


def test_the_painted_area_is_the_only_thing_that_moves_the_defects(tmp_path, gc):
    """畫在**別的地方**，缺陷就跟著搬家 —— 而且搬的距離對得上。"""
    px, py = gcl.periods(gc)
    outs = []
    for gx in (20, 60):
        mask = np.zeros(gc.shape, dtype=bool)
        mask[11, gx] = True
        outs.append(gcl.generate(str(tmp_path / str(gx)), gc=gc, images=1,
                                 size=900, defects=6, patch=41, seed=5,
                                 sites=gcl.sites_from_mask(mask)))
    a = [float(d.xrel_nm) for d in load_dataset(outs[0]["patch_klarf"]).items]
    b = [float(d.xrel_nm) for d in load_dataset(outs[1]["patch_klarf"]).items]
    shift = (b[0] - a[0]) % px
    assert min(abs(shift - 40.0), abs(shift - 40.0 + px)) < 2.0, (
        "畫的位置移了 40 px，缺陷卻移了 %.1f" % shift)


# --------------------------------------------------------------------------- #
# 缺陷長什麼樣（F62）
# --------------------------------------------------------------------------- #
def _planted(gc, spec, kind, seed=3):
    """在一塊乾淨的圖案上種一顆，回 (加上去的東西, 乾淨的底)。"""
    px, py = gcl.periods(gc)
    clean = gcl.tile(gc, 80, 80, px, py)
    dirty = clean.copy()
    gcl.plant(dirty, kind, 40.0, 40.0, np.random.default_rng(seed), px, spec)
    return dirty - clean, clean


def test_the_size_you_type_is_the_size_you_measure(gc):
    """填的是**直徑**不是 σ —— 使用者量得到的東西才填得下去。"""
    for want in (4.0, 12.0):
        spec = gcl.DefectSpec(diameter=(want, want), contrast=(80.0, 80.0))
        delta, _ = _planted(gc, spec, "bright_blob")
        # 半高全寬那一圈：> 一半的峰值
        wide = int((delta[40, :] > delta.max() * 0.5).sum())
        assert abs(wide - want) <= max(2.0, want * 0.35), (
            "填 %.0f px，量到 %d px" % (want, wide))


def test_a_bigger_size_really_is_bigger(gc):
    small, _ = _planted(gc, gcl.DefectSpec(diameter=(4.0, 4.0)), "bright_blob")
    big, _ = _planted(gc, gcl.DefectSpec(diameter=(14.0, 14.0)), "bright_blob")
    assert (big > 5).sum() > 3 * (small > 5).sum()


def test_contrast_is_in_grey_levels(gc):
    delta, _ = _planted(gc, gcl.DefectSpec(contrast=(70.0, 70.0)),
                        "bright_blob")
    assert abs(float(delta.max()) - 70.0) < 6.0


@pytest.mark.parametrize("pol,want", [("bright", ("bright_blob",)),
                                      ("dark", ("dark_blob",)),
                                      ("both", ("bright_blob", "dark_blob"))])
def test_the_polarity_picker_decides_which_kinds_exist(pol, want):
    spec = gcl.DefectSpec(polarity=pol, bridge=False)
    assert spec.kinds() == want
    assert gcl.DefectSpec(polarity=pol).kinds() == want + ("bridge",)


def test_dark_only_never_makes_a_bright_defect(tmp_path, gc):
    """**整條路**都要照設定走，不只 `kinds()` 那一格。"""
    out = gcl.generate(str(tmp_path), gc=gc, images=2, size=900, defects=20,
                       patch=41, seed=7, real_frac=1.0,
                       defect=gcl.DefectSpec(polarity="dark", bridge=False))
    import json
    truth = json.load(open(out["patch_ground_truth"], encoding="utf-8"))
    kinds = {v["type"] for v in truth.values()}
    assert kinds == {"dark_blob"}, kinds


def test_a_dark_defect_goes_down_and_a_bright_one_goes_up(gc):
    up, _ = _planted(gc, gcl.DEFECT, "bright_blob")
    down, _ = _planted(gc, gcl.DEFECT, "dark_blob")
    assert up.max() > 40 and abs(up.min()) < 1
    assert down.min() < -40 and abs(down.max()) < 1


def test_the_width_convention_is_fwhm_like_everywhere_else(gc):
    """⚠ 「寬度」在這個 repo 只有一個意思：**FWHM**。

    第一版用「±2σ」換算，於是填 12 量到 7 —— ±2σ 那一圈只剩峰值的 13%，
    量不到。`make_mgepi_real.py` 的檔頭早就寫著線寬是 FWHM 定義，
    而同一個 repo 裡同一個字不能有兩種意思。
    """
    for want in (5.0, 11.0):
        spec = gcl.DefectSpec(diameter=(want, want), contrast=(80.0, 80.0))
        delta, _ = _planted(gc, spec, "bright_blob")
        wide = int((delta[40, :] > delta.max() * 0.5).sum())
        assert abs(wide - want) <= 1.5, "填 %.0f，半高量到 %d" % (want, wide)

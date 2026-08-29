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


# --------------------------------------------------------------------------- #
# 配對輸出（F63）—— 給訓練用的乾淨版 ＋ 缺陷足跡
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def paired(tmp_path_factory, gc):
    d = tmp_path_factory.mktemp("pairs")
    return gcl.generate(str(d), gc=gc, images=2, size=900, defects=10,
                        patch=41, seed=9, real_frac=1.0, pairs=True)


def test_the_clean_copy_differs_only_where_the_defects_are(paired):
    """⚠ **這是整個配對輸出唯一真正要保證的事。**

    雜訊必須**產一次、兩邊都加**。各自 `rng.normal` 一次的話兩張圖每一個
    畫素都不一樣，而那種資料訓出來的模型學的是「去雜訊」，不是「把缺陷拿掉」
    —— 看起來完全正常，loss 也會乖乖下降。

    所以斷言的是：**離缺陷遠的地方要逐位元組相同**。
    """
    import cv2
    for i, dirty_path in enumerate(paired["rsem_images"], start=1):
        dirty = cv2.imread(dirty_path, cv2.IMREAD_GRAYSCALE).astype(int)
        clean = cv2.imread(os.path.join(paired["rsem_clean_dir"],
                                        "DEF_%04d.png" % i),
                           cv2.IMREAD_GRAYSCALE).astype(int)
        diff = np.abs(dirty - clean)
        assert diff.size and (diff == 0).mean() > 0.99, (
            "只有 %.2f%% 的畫素相同 —— 雜訊大概是各抽各的"
            % (100 * (diff == 0).mean()))
        # 有差的那些要**擠在一起**（缺陷），不是撒滿整張
        ys, xs = np.nonzero(diff)
        assert len(ys) < 0.01 * diff.size


def test_the_mask_marks_the_defects_and_nothing_else(paired):
    import cv2
    for i, dirty_path in enumerate(paired["rsem_images"], start=1):
        dirty = cv2.imread(dirty_path, cv2.IMREAD_GRAYSCALE).astype(int)
        clean = cv2.imread(os.path.join(paired["rsem_clean_dir"],
                                        "DEF_%04d.png" % i),
                           cv2.IMREAD_GRAYSCALE).astype(int)
        mask = cv2.imread(os.path.join(paired["rsem_mask_dir"],
                                       "DEF_%04d.png" % i),
                          cv2.IMREAD_GRAYSCALE) > 0
        assert mask.any(), "整張沒有標到任何東西"
        diff = np.abs(dirty - clean)
        # 標到的地方一定有差（不能標在沒事的地方）
        assert diff[mask].min() > 0
        # ⚠ 標的是**半高**那一圈，跟 `DefectSpec.diameter` 同一個定義，
        # 所以高斯的尾巴會落在遮罩外面 —— 那不是錯，是這個定義的意思。
        assert diff[~mask].max() <= diff[mask].max()


def test_the_paired_pages_line_up_with_the_main_tiff(paired):
    """第 n 頁對第 n 頁，**沒有例外** —— 拿去訓練的人會照著 index 取。"""
    import tifffile
    main = tifffile.imread(paired["patch_tiff"])
    clean = tifffile.imread(paired["patch_clean_tiff"])
    mask = tifffile.imread(paired["patch_mask_tiff"])
    assert len(main) == len(clean) == len(mask)
    # 奇數頁是 ref（沒有缺陷）：遮罩全黑、乾淨版就是它自己
    for i in range(1, len(main), 2):
        assert not mask[i].any()
        assert (clean[i] == main[i]).all()


def test_every_defect_records_what_it_actually_looked_like(paired):
    """分類標籤之外還有 regression target（位置／對比／尺寸）。"""
    import json
    truth = json.load(open(paired["patch_ground_truth"], encoding="utf-8"))
    assert truth
    for v in truth.values():
        assert {"is_real", "type", "x", "y"} <= set(v)
        if v["is_real"]:
            assert 5.0 <= v["contrast"] <= 200.0
            assert 0.5 <= v["size"] <= 80.0


def test_without_the_flag_nothing_extra_is_written(tmp_path, gc):
    """**預設不寫** —— 配對資料是主檔的兩倍大，不要讓沒要的人付這個錢。"""
    out = gcl.generate(str(tmp_path), gc=gc, images=1, size=900, defects=4,
                       patch=41, seed=1)
    assert "rsem_clean_dir" not in out and "patch_clean_tiff" not in out
    assert not os.path.isdir(os.path.join(str(tmp_path), "rsem", "clean"))


# --------------------------------------------------------------------------- #
# 擬真：實際不會這麼好看（F64）
# --------------------------------------------------------------------------- #
def test_two_repeats_are_no_longer_identical(gc):
    """**這就是使用者要的那一句。**

    「GLV 也不會每區每個 layout 都一樣」—— 而在 F63 之前，鋪出來的兩個重複
    是**逐位元組相同**的（GC 是疊出來的平均臉，複製一百次）。
    """
    px, py = 175.96, 34.0
    rng = np.random.default_rng(5)
    flat = gcl.tile(gc, 400, 400, px, py)

    def block_means(img):
        n = int(img.shape[1] / px)
        return [float(img[:, int(i * px):int((i + 1) * px)].mean())
                for i in range(n)]

    # ⚠ 比的是**每一格的平均**，不是逐畫素。週期是 175.96 —— 用整數切出來的
    # 兩塊本來就差 0.96 px 的相位，逐畫素比會比到「切歪了」而不是「不一樣」。
    a = block_means(flat)
    assert max(a) - min(a) < 0.5, "沒有擬真的時候每一格本來就該一樣：%s" % a

    b = block_means(gcl.roughen(flat, px, py, 0.0, 0.0, rng, gcl.REALISM))
    assert max(b) - min(b) > 1.5, (
        "每一格的平均只差 %.2f GLV —— 還是太像了：%s" % (max(b) - min(b), b))


def test_the_warp_makes_a_line_wander_a_little_not_a_lot(gc):
    """⚠ **量的是位移場本身，不是產出來的影像。**

    第一版拿影像去估線的位置，量到 0.88 px，而場的真值是 3–4 px —— 那個估計量
    在窗口邊界會夾住。場是沒有歧義的那一份，所以斷言對著它下。
    """
    rng = np.random.default_rng(5)
    dx, dy = gcl.warp_field(800, 800, 175.96, rng, gcl.REALISM)
    assert not dy.any(), "直的是 MG，它扭的是左右 —— y 不該動"
    # 一根線沿著自己的長度走過的距離：要看得出來，又不能變成波浪
    for x in (100, 400, 700):
        pp = float(dx[:, x].max() - dx[:, x].min())
        assert 0.6 < pp < 4.0, "x=%d 的線 p-p %.2f px" % (x, pp)


def test_the_warp_is_smooth_not_speckle(gc):
    """扭是**連續**的：相鄰的兩列不會差一整個畫素。"""
    rng = np.random.default_rng(5)
    dx, _ = gcl.warp_field(400, 400, 175.96, rng, gcl.REALISM)
    step = np.abs(np.diff(dx, axis=0))
    assert step.max() < 0.35, "相鄰列差 %.2f px —— 那是雜訊不是彎曲" % step.max()


def _period_residual(out, path):
    """相隔正好一個週期的兩個畫素差多少（平均，GLV）。

    完美鋪出來的圖上它們一樣 —— 那正是使用者說的那句話（「GLV 不會每區每個
    layout 都一樣」）。**不必知道相位**，也不受切格子的影響。

    ⚠ 第一版比的是「每一格的平均」，而那個數字在不同 seed 之間從 0.41 跳到
    2.80（週期 175.96，用整數切出來的每一格捕捉到的相位都不一樣）——
    一條會自己抖的斷言不是斷言。
    """
    import cv2
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE).astype(float)
    k = int(round(out["period"][0]))
    return float(np.abs(img[:, :-k] - img[:, k:]).mean())


def _gen(tmp_path, gc, tag, spec):
    out = gcl.generate(str(tmp_path / tag), gc=gc, images=1, size=900,
                       defects=2, patch=41, seed=6, noise=0.0, realism=spec)
    return _period_residual(out, out["rsem_images"][0])


#: 只有幾何（線扭），沒有明暗變化。
_WARP_ONLY = gcl.Realism(cell_gain=0.0, cell_bias=0.0, shade=0.0, shot=0.0)


def test_the_generated_image_really_gets_the_warp(tmp_path, gc):
    """⚠ **突變測試逼出來的第一半。**

    單元測試直接呼叫 `warp_field` / `roughen` 驗過了 —— 但那回答不了
    「`generate` 那條路上有沒有真的走過去」。把那一行拿掉，35 條全綠。
    """
    flat = _gen(tmp_path, gc, "flat", gcl.FLAT)
    warp = _gen(tmp_path, gc, "warp", _WARP_ONLY)
    assert flat < 1.0, "完美鋪圖上相隔一週期本來就該一樣，量到 %.2f" % flat
    assert warp > 3.0, "套了 warp 卻只差 %.2f GLV" % warp


def test_the_generated_image_really_gets_the_per_repeat_glv(tmp_path, gc):
    """⚠ **第二半，而它需要一個對照組。**

    「相隔一週期差多少」這個數字**warp 自己就撐得起來**（5.8），所以拿它跟
    `FLAT` 比抓不到「`roughen` 沒被呼叫」。要抓，對照組得是**只有 warp**
    的那一份 —— 多出來的那一截才是明暗變化的貢獻。
    """
    warp = _gen(tmp_path, gc, "w2", _WARP_ONLY)
    full = _gen(tmp_path, gc, "full", gcl.Realism(shot=0.0))
    assert full > warp * 1.3, (
        "只有 warp %.2f，全部 %.2f —— 每個重複的 GLV 大概沒有套上"
        % (warp, full))


def test_shot_noise_is_louder_where_the_signal_is(gc):
    """SEM 的雜訊是訊號相依的（電子數的 Poisson）—— 亮的地方比暗的地方吵。

    只加固定 σ 的話暗區會比真的乾淨，而那正是「量得準不準」最容易被高估的
    地方。
    """
    rng = np.random.default_rng(3)
    dark = np.full((300, 300), 20.0, np.float32)
    bright = np.full((300, 300), 220.0, np.float32)
    sd_dark = float(gcl.grain(dark, 0.0, rng, gcl.REALISM).std())
    sd_bright = float(gcl.grain(bright, 0.0, rng, gcl.REALISM).std())
    assert sd_bright > 2.5 * sd_dark, (
        "亮 %.2f vs 暗 %.2f —— 沒有訊號相依" % (sd_bright, sd_dark))
    # 固定 σ 的讀出雜訊仍然在（兩者都有底）
    assert float(gcl.grain(dark, 6.0, rng, gcl.FLAT).std()) > 5.0


def test_flat_really_turns_everything_off(gc):
    """`FLAT` 要能回到 F59–F63 的完美鋪圖 —— 想比較的時候有個對照組。"""
    rng = np.random.default_rng(1)
    dx, dy = gcl.warp_field(200, 200, 100.0, rng, gcl.FLAT)
    assert not dx.any() and not dy.any()
    flat = gcl.tile(gc, 200, 200, 175.96, 34.0)
    assert np.array_equal(
        gcl.roughen(flat, 175.96, 34.0, 0.0, 0.0, rng, gcl.FLAT), flat)
    assert not gcl.grain(flat, 0.0, rng, gcl.FLAT).any()


def test_the_clean_pair_survives_the_realism(tmp_path, gc):
    """⚠ **擬真不可以把 F63 的那條不變量弄壞。**

    shot noise 的 σ 取自**乾淨版**的訊號 —— 取自缺陷版的話，缺陷那幾個畫素
    會因為更亮而更吵，於是「乾淨版與缺陷版只差在缺陷」就不再成立，而那是
    整個配對輸出唯一要保證的事。
    """
    import cv2
    out = gcl.generate(str(tmp_path), gc=gc, images=1, size=900, defects=6,
                       patch=41, seed=4, real_frac=1.0, pairs=True)
    d = cv2.imread(out["rsem_images"][0], cv2.IMREAD_GRAYSCALE).astype(int)
    c = cv2.imread(os.path.join(out["rsem_clean_dir"], "DEF_0001.png"),
                   cv2.IMREAD_GRAYSCALE).astype(int)
    same = float((np.abs(d - c) == 0).mean())
    assert same > 0.99, "只有 %.2f%% 相同 —— 擬真把配對弄壞了" % (100 * same)


# --------------------------------------------------------------------------- #
# 種類的比例（F65）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("frac", [0.0, 0.15, 0.5, 1.0])
def test_the_bridge_share_is_the_share_you_asked_for(frac):
    """⚠ **這一條是實跑資料看出來的。**

    原本 `bridge` 是 `True`／`False`，而 `True` 的時候三種**等機率**抽 ——
    於是 bridge 佔了 1/3。60 顆裡量到 16/35 是 bridge，比 blob 還多，
    而真實世界通常反過來。
    """
    spec = gcl.DefectSpec(bridge=frac)
    rng = np.random.default_rng(5)
    got = [spec.pick(rng) for _ in range(4000)]
    share = got.count("bridge") / float(len(got))
    assert abs(share - frac) < 0.03, "要 %.2f，抽出來 %.3f" % (frac, share)


def test_turning_bridges_off_leaves_only_blobs():
    spec = gcl.DefectSpec(bridge=0.0)
    assert "bridge" not in spec.kinds()
    rng = np.random.default_rng(1)
    assert "bridge" not in {spec.pick(rng) for _ in range(500)}


def test_bright_and_dark_split_the_rest_evenly():
    """比例只管 bridge —— 剩下的照極性分，`both` 是一半一半。"""
    spec = gcl.DefectSpec(bridge=0.2, polarity="both")
    rng = np.random.default_rng(2)
    got = [spec.pick(rng) for _ in range(4000)]
    b, d = got.count("bright_blob"), got.count("dark_blob")
    assert abs(b - d) / float(b + d) < 0.06, "亮 %d 暗 %d" % (b, d)


def test_the_share_reaches_the_written_lot(tmp_path, gc):
    """**整條路**都要照比例走，不只 `pick()` 那一格。

    ⚠ 第一版拿 ``bridge=0`` 來驗，而那**抓不到**「`generate` 回去等機率抽」
    —— `kinds()` 在 0 的時候本來就不含 bridge，兩種寫法都產不出 bridge。
    要分得出來，比例就得是一個**不平凡**的值：0.06 對上等機率的 1/3。
    """
    import json
    out = gcl.generate(str(tmp_path), gc=gc, images=4, size=900, defects=200,
                       patch=41, seed=3, real_frac=1.0,
                       defect=gcl.DefectSpec(bridge=0.06))
    truth = json.load(open(out["patch_ground_truth"], encoding="utf-8"))
    kinds = [v["type"] for v in truth.values()]
    share = kinds.count("bridge") / float(len(kinds))
    assert len(kinds) > 100
    assert share < 0.15, (
        "要 6%%，寫出去的是 %.1f%% —— 大概還是等機率抽（那會是 33%%）"
        % (100 * share))


def test_turning_the_share_to_zero_reaches_the_written_lot(tmp_path, gc):
    import json
    out = gcl.generate(str(tmp_path), gc=gc, images=3, size=900, defects=90,
                       patch=41, seed=3, real_frac=1.0,
                       defect=gcl.DefectSpec(bridge=0.0))
    truth = json.load(open(out["patch_ground_truth"], encoding="utf-8"))
    assert "bridge" not in {v["type"] for v in truth.values()}

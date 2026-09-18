# F77：OP-301 的對焦清晰度分數（`algo/iqi.py`）— authored 2026-09-02.
"""**規格的五條驗收標準，一條一支測試。**

規格（使用者 2026-09-02 給的三份說明）明列了驗收條件，所以這一份就是那張
清單的可執行形式。另外兩支測的是兩份說明**互相矛盾**的地方 —— 那兩條不是
規格要的，是這一輪量出來的，而它們正是「兩種選法都跑得完、都有數字」的證據。

最後一節（F115，2026-09-18）測的是第三件事：**同一個指標換一種區域型態就
換一種行為**。那一輪的資料不能進這個 repo（鐵則 8），所以用的是合成出來的
形狀（`tests/iqi_fixtures.py`）；廠外量到的那些相關係數住在
`docs/USING-FOCUS.md`，一個都不會出現在斷言裡。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tests.iqi_fixtures as fixtures  # noqa: E402
from d4t.core.algo import iqi  # noqa: E402


def _checker(size=512, pitch=16, blur=0, noise=0.0, seed=0):
    """一張棋盤 pattern —— 銳利、高對比，而且 blur 得動。"""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size]
    img = 128.0 + 100.0 * (np.sign(np.sin(2 * np.pi * x / pitch))
                           * np.sign(np.sin(2 * np.pi * y / pitch)))
    if blur:
        k = int(blur) * 2 + 1
        pad = np.pad(img, k // 2, mode="edge")
        out = np.zeros_like(img)
        for dy in range(k):
            for dx in range(k):
                out += pad[dy:dy + size, dx:dx + size]
        img = out / (k * k)
    if noise:
        img = img + rng.normal(0, noise, img.shape)
    return np.clip(img, 0.0, 255.0)


# --------------------------------------------------------------------------- #
# 規格的驗收標準
# --------------------------------------------------------------------------- #
def test_the_answer_is_one_number():
    got = iqi.focus_index(_checker())
    assert isinstance(got["iqi"], float)
    assert np.isfinite(got["iqi"])


def test_blur_makes_the_score_go_down_every_time():
    """**這是這個指標的定義**：失焦 → 邊緣糊 → 對比弱 → 分數低。

    ⚠ 它同時是「濾波方向」那個疑問的判準（模組說明 ①）：低通版本在越模糊的
    圖上分數反而越高，這一條會直接紅。
    """
    scores = [iqi.focus_index(_checker(blur=b))["iqi"]
              for b in (0, 1, 2, 3, 5, 8)]
    assert scores == sorted(scores, reverse=True), scores
    assert scores[0] > scores[-1] * 100, "糊到看不見時要掉兩個數量級以上"


def test_a_flat_grey_image_scores_zero():
    """整張都是 128 —— 沒有 pattern，理論最小值。"""
    got = iqi.focus_index(np.full((512, 512), 128.0))
    assert got["iqi"] == pytest.approx(0.0, abs=1e-9)
    assert got["pattern_frac"] == pytest.approx(0.0), \
        "全灰的圖梯度處處為 0，所以『有 pattern 的地方』是 0 成"


def test_the_image_size_does_not_change_the_answer():
    """1024 與 2000 用**完全相同的參數**跑通，而且分數比得起來。

    這一條靠兩件事成立：塊數固定 64（不隨尺寸變），而 cutoff 是**佔 Nyquist
    的百分比**、能量**除以像素數** —— 三個都跟塊的絕對大小無關。
    """
    got = {n: iqi.focus_index(_checker(size=n))["iqi"]
           for n in (512, 1024, 2000)}
    lo, hi = min(got.values()), max(got.values())
    assert hi / lo < 1.05, got
    assert all(r["blocks"] == 19
               for r in (iqi.focus_index(_checker(size=n)) for n in (512, 1024)))


def test_each_step_is_its_own_function():
    """規格：四個步驟各是一個獨立 function，而且組得回同一個答案。"""
    img = _checker(size=256)
    pieces = iqi.slice_blocks(img, 8)                      # Step 1
    assert len(pieces) == 64 and pieces[0].shape == (32, 32)
    density, mag = iqi.pattern_density(img, 8)             # Step 1 的第二半
    assert density.shape == (64,) and mag.shape == img.shape
    spec = iqi.fft_denoise(pieces[0])                      # Step 2
    assert np.iscomplexobj(spec) and spec.shape == pieces[0].shape
    back = iqi.ifft_block(spec)                            # Step 3
    assert np.iscomplexobj(back)
    assert iqi.block_energy(back) >= 0.0                   # Step 4

    # 手動走完四步 == focus_index 的第一塊分數
    assert iqi.focus_index(img)["scores"][0] == pytest.approx(
        iqi.block_energy(iqi.ifft_block(iqi.fft_denoise(pieces[0]))))


# --------------------------------------------------------------------------- #
# 兩份說明矛盾的地方（見模組說明 ①②）
# --------------------------------------------------------------------------- #
def test_a_noisy_blank_block_scores_high_until_you_wash_the_grain_out():
    """**投影片那句「filter out high-frequency noise」指的是一個真的失效模式。**

    純高通（詳細版描述的行為）把**雜訊當成清晰度**：一塊什麼都沒有、只有
    感測器顆粒的背景拿到的分數不是 0。壓掉最高頻之後它掉一個數量級，而
    pattern 只掉不到兩倍 —— 訊號背景比因此變好五倍。

    這一條不是在說哪一份規格對，是在**量代價**：`iqi_noise_percent` 那一格
    要不要開，由站點看著這兩個數字決定。
    """
    rng = np.random.default_rng(1)
    blank = np.full((512, 512), 128.0) + rng.normal(0, 8.0, (512, 512))
    sharp = _checker()

    plain = (iqi.focus_index(blank)["iqi"], iqi.focus_index(sharp)["iqi"])
    band = (iqi.focus_index(blank, noise_percent=40.0)["iqi"],
            iqi.focus_index(sharp, noise_percent=40.0)["iqi"])

    assert plain[0] > 10.0, "純高通下，一塊只有雜訊的背景並不是 0 分"
    assert band[0] < plain[0] / 5.0, "壓掉最高頻之後它應該掉一個數量級"
    assert band[1] > plain[1] / 3.0, "而 pattern 不該跟著垮掉"
    assert (band[1] / band[0]) > (plain[1] / plain[0]) * 3.0, \
        "訊號背景比要明顯變好 —— 那才是開這一格的理由"


def test_parseval_says_the_ifft_is_optional():
    """``Σ|iFFT(X)|² = (1/N)·Σ|X|²`` —— Step 3 對最終數字沒有貢獻。

    留著 iFFT 是因為規格要四個獨立步驟，而空間域那張圖之後要畫在儀表上。
    **哪天嫌慢，這一條就是刪掉 Step 3 的許可證。**
    """
    block = iqi.slice_blocks(_checker(size=256), 8)[10]
    spec = iqi.fft_denoise(block)
    n = float(spec.size)
    assert iqi.block_energy(iqi.ifft_block(spec)) == pytest.approx(
        float(np.sum(np.abs(spec) ** 2)) / (n * n), rel=1e-9)


def test_the_gradient_step_is_not_dead_code():
    """梯度圖有兩個下游 —— 一個看得見的數字，以及（要的話）篩塊。

    詳細版把它列成一個獨立步驟卻沒有任何人讀它的輸出，而「跑得完、有數字、
    而且有一段是空轉的」是這個 repo 記過六次的形狀。
    """
    half = np.full((512, 512), 128.0)
    half[:, :256] = _checker()[:, :256]          # 左半有 pattern，右半全灰

    got = iqi.focus_index(half)
    assert 0.05 < got["pattern_frac"] < 0.95, got["pattern_frac"]
    # 篩掉沒有 pattern 的塊 → 參與平均的塊數變少（投影片那條路）
    picky = iqi.focus_index(half, min_pattern=0.2)
    assert picky["blocks"] < got["blocks"]
    # 而篩到一塊都不剩時**退回不篩**，不是拋錯
    none_left = iqi.focus_index(half, min_pattern=1.1)
    assert none_left["blocks"] == got["blocks"]


def test_a_block_too_small_to_measure_says_so():
    """打不進去的圖要當場講（鐵則 4），而且講得出兩條出路。"""
    with pytest.raises(ValueError) as e:
        iqi.slice_blocks(np.zeros((12, 12)), 8)
    assert "per block" in str(e.value) and "fewer blocks" in str(e.value)


# --------------------------------------------------------------------------- #
# F115：四個步驟跑在哪一張圖上（``domain``）
#
# 2026-09-18 的廠外驗證量到一件事：這個指標**在兩種區域上的表現差一個數量級**，
# 而差別不在參數，在區域型態。那一輪的資料不能進這個 repo（鐵則 8），所以下面
# 用的是兩張合成出來的**形狀**（`tests/iqi_fixtures.py`），斷言的是結構 ——
# 廠外那些相關係數一個都不會出現在斷言裡，它們住在 `docs/USING-FOCUS.md`。
# --------------------------------------------------------------------------- #
def _sep(gen, domain, blur=2):
    """這張圖「對焦準 ÷ 失焦」差幾倍 —— 一個指標的鑑別力就是這個數字。"""
    sharp = iqi.focus_index(gen(blur=0), domain=domain)["iqi"]
    soft = iqi.focus_index(gen(blur=blur), domain=domain)["iqi"]
    return sharp / soft


def test_measuring_on_the_image_is_byte_for_byte_what_it_always_was():
    """**黃金值的守門。** 預設那條路多了一格參數，數字一個位元都不准動。

    ⚠ 這一條不是形式主義：新的那一格是在 ``pattern_density`` **之後**才分岔
    的，而那一步原本排在切塊後面。順序換了而答案沒換，只有逐項相等講得出來。
    """
    for img in (_checker(), _checker(blur=3), fixtures.logic_blocks(),
                fixtures.array_blocks()):
        base = iqi.focus_index(img)
        named = iqi.focus_index(img, domain=iqi.DOMAIN_PIXEL)
        assert named["iqi"] == base["iqi"]
        assert named["scores"] == base["scores"]
        assert named["pattern_frac"] == base["pattern_frac"]
        assert named["blocks"] == base["blocks"]


def test_the_gradient_route_runs_the_same_four_steps_on_the_gradient():
    """規格沒有第二套步驟 —— 換的只有**餵進去的那張圖**。

    手動走完「換圖 → 四個步驟」要跟 ``domain="gradient"`` 逐項相同；不同的話
    就是那條路上偷偷多做或少做了一件事。
    """
    img = fixtures.array_blocks()
    got = iqi.focus_index(img, domain=iqi.DOMAIN_GRADIENT)
    want = iqi.focus_index(iqi.gradient_magnitude(img), domain=iqi.DOMAIN_PIXEL)
    assert got["scores"] == want["scores"]
    assert got["iqi"] == want["iqi"]


def test_the_gradient_has_exactly_one_definition_in_this_module():
    """`pattern_density` 數的那張梯度圖，跟梯度那條路吃的是**同一張**。

    兩份定義的下場是它們遲早不一樣，而那時候 ``pattern_frac`` 講的就不再是
    分數是從哪裡來的（見模組說明最後一節）。
    """
    img = fixtures.logic_blocks()
    _density, mag = iqi.pattern_density(img, 8)
    assert np.array_equal(mag, iqi.gradient_magnitude(img))


def test_which_image_it_measured_does_not_change_how_much_pattern_there_is():
    """``pattern_frac`` 講的是**這張影像**有多少地方有 pattern。

    那是影像的性質，不是這一格選了什麼的性質 —— 兩條路上要是同一個數字。
    """
    for gen in (fixtures.logic_blocks, fixtures.array_blocks):
        a = iqi.focus_index(gen(), domain=iqi.DOMAIN_PIXEL)["pattern_frac"]
        b = iqi.focus_index(gen(), domain=iqi.DOMAIN_GRADIENT)["pattern_frac"]
        assert a == b


def test_blur_still_makes_the_score_go_down_on_the_gradient():
    """換了一張圖不代表可以換一個定義：失焦 → 分數低，**兩條路都要成立**。"""
    for gen in (fixtures.logic_blocks, fixtures.array_blocks):
        for domain in iqi.DOMAINS:
            scores = [iqi.focus_index(gen(blur=b), domain=domain)["iqi"]
                      for b in (0, 1, 2, 3, 5, 8)]
            assert scores == sorted(scores, reverse=True), (gen, domain, scores)


def test_on_a_repeating_array_the_gradient_separates_more():
    """**這一格為什麼存在**，寫成一條測試。

    array 區上灰階那條路鑑別力很低（廠外實測每一種調法都卡在 r ≈ 0.3），
    而梯度是那台機台上量到的局部最好。這裡量的是同一件事的合成版：同一張圖、
    同一個模糊量，梯度那條路「準 ÷ 糊」的倍數要明顯大一些。
    """
    pixel = _sep(fixtures.array_blocks, iqi.DOMAIN_PIXEL)
    grad = _sep(fixtures.array_blocks, iqi.DOMAIN_GRADIENT)
    assert grad > pixel * 1.5, (pixel, grad)


def test_on_a_logic_area_the_gradient_is_not_worse():
    """**反面**：它不准是一個「在別處變差」的選項。

    廠外實測機台 B（logic 區）0.9593 → 0.9596 —— 也就是沒有變差。合成版問的
    是同一句話：梯度那條路的鑑別力不准比灰階那條**差過 5%**。
    """
    pixel = _sep(fixtures.logic_blocks, iqi.DOMAIN_PIXEL)
    grad = _sep(fixtures.logic_blocks, iqi.DOMAIN_GRADIENT)
    assert grad >= pixel * 0.95, (pixel, grad)


def test_a_domain_that_does_not_exist_says_so():
    """打錯的那一格要當場講，而且講得出有哪幾條路（鐵則 4）。"""
    with pytest.raises(ValueError) as e:
        iqi.focus_index(_checker(size=128), domain="edges")
    assert "edges" in str(e.value) and "gradient" in str(e.value)


# --------------------------------------------------------------------------- #
# F115：前 30% 那一刀與梯度預篩，在哪一種區域上**有作用**
# --------------------------------------------------------------------------- #
def test_on_a_logic_area_the_sharpest_30_percent_picks_the_blocks_with_pattern():
    """logic 區 = 這兩步的**前提成立**的樣子：一半的塊有東西、一半是空的。

    那一刀要挑中的**全部**是有圖案的那些 —— 空背景塊一塊都不准混進平均裡，
    因為它們分數低不是因為失焦，是因為那裡本來就沒有東西。
    """
    textured = fixtures.logic_textured_blocks()
    for domain in iqi.DOMAINS:
        got = iqi.focus_index(fixtures.logic_blocks(), domain=domain)
        order = np.argsort(np.array(got["scores"]))[::-1][:got["blocks"]]
        assert got["blocks"] == 19
        assert textured[order].all(), (domain, sorted(order.tolist()))


def test_on_a_repeating_array_keeping_19_or_40_blocks_is_the_same_answer():
    """array 區 = 這兩步的**前提不成立**的樣子：64 塊長得一模一樣。

    廠外實測（2026-09-18）：留下來的塊數從 19 掃到 40，兩台機台的相關係數
    一動都不動。**那不是 bug，是前提不成立** —— 挑 19 個一樣的東西跟挑 40 個
    一樣的東西是同一件事。它同時結掉了規格「前 30」與「前 30%」的措辭歧義。

    ⚠ 反面在上面那一條：同樣的掃法在 logic 區會把分數改掉三成以上。
    """
    for domain in iqi.DOMAINS:
        kept = [iqi.focus_index(fixtures.array_blocks(), keep_percent=p,
                                domain=domain)
                for p in (30.0, 62.5)]          # 64 × 30% = 19、× 62.5% = 40
        assert [k["blocks"] for k in kept] == [19, 40]
        moved = abs(kept[0]["iqi"] - kept[1]["iqi"]) / kept[0]["iqi"]
        assert moved < 0.01, (domain, moved, [k["iqi"] for k in kept])

    logic = [iqi.focus_index(fixtures.logic_blocks(), keep_percent=p)
             for p in (30.0, 62.5)]
    assert abs(logic[0]["iqi"] - logic[1]["iqi"]) / logic[0]["iqi"] > 0.2, \
        "同樣的掃法在 logic 區要**明顯**動到分數 —— 不然上面那條沒有在測東西"

# F8 第五輪：同一個晶格上不只一種材質，而線寬可以是**給定**的。
"""兩件使用者提出來的事，各自解掉一個安靜的失敗。

1. **CPODE** —— 一排 MG 裡有一根被挖掉換成很暗的東西，位置在**同一個晶格上、
   寬度跟 MG 一樣**。曲線因此有三個台階，而「挑最亮的那一組」預設只分兩群
   （線，跟線之間的空隙）。三個台階分兩群的結果是：最亮的那群 = MG **加上
   空隙**。挑到的條紋是實際的兩倍、量到的 pitch 是實際的一半 —— 而畫面上不會
   有任何一個字說出這件事。

2. **線寬由使用者給定** —— 「MG 的線寬理論上要一樣」。給了之後，這條曲線只剩
   一件事要做對：每一根線的**中心**在哪。中心是整段的重心，比單邊的邊界穩得多。

兩件事合起來正好是使用者描述的流程：
先用 profile 定出 MG 中心 → 給定 MG 寬度 → 從 MG 寬度往外長 ROI。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.algo import grid as algo_grid  # noqa: E402
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402
from tests.region_cards import region_card  # noqa: E402

SIZE, MG_PITCH, MG_W, EPI_PITCH = 128, 24, 8, 34
CPODE_SITES = (2, 5)          # 由左到右：MG MG CPODE MG MG CPODE


def _mg_cpode(cpode: bool = True, seed: int = 0) -> np.ndarray:
    """MG（亮）＋ EPI（橫的，中亮）＋ CPODE（很暗，在 MG 的晶格上）。"""
    rng = np.random.default_rng(seed)
    img = np.full((SIZE, SIZE), 90.0, np.float32)
    img[np.arange(SIZE) % EPI_PITCH < 14, :] = 180.0
    img[:, (np.arange(SIZE) % MG_PITCH) < MG_W] = 220.0
    if cpode:
        for site in CPODE_SITES:
            img[:, site * MG_PITCH:site * MG_PITCH + MG_W] = 30.0
    return img + rng.normal(0, 2.0, (SIZE, SIZE)).astype(np.float32)


def _centres(bands) -> list:
    return sorted(round((float(a) + float(b)) / 2.0, 1) for a, b in bands)


# --------------------------------------------------------------------------- #
# 1. CPODE：三種材質，兩群是不夠的
# --------------------------------------------------------------------------- #
def test_a_third_material_quietly_doubles_the_stripe_count():
    """記錄**為什麼**需要這個參數 —— 這是舊行為，而它不報錯。

    這條測試不是在保護一個行為，是在鎖住一個已知的陷阱：三個台階分兩群時，
    「最亮的那一組」會連空隙一起收進來。哪天分群改法了，這條會紅 ——
    那正是要停下來看一眼的時候。
    """
    s = algo_grid.find_stripes(_mg_cpode(), axis="x", select="brightest")
    assert len(s.selected) > 6, "沒有把空隙也收進來？那這個坑不存在了"
    assert s.pitch_measured == pytest.approx(MG_PITCH / 2.0, abs=1.0), (
        "量到 %.1f —— 這個坑的症狀是 pitch 剛好變一半" % s.pitch_measured)


def test_saying_how_many_kinds_there_are_picks_out_just_the_metal():
    s = algo_grid.find_stripes(_mg_cpode(), axis="x", select="brightest",
                               kinds=3)
    # 六個晶格點裡有四個是 MG（另外兩個是 CPODE），影像上看得到的就是這四個
    assert len(s.selected) == 4
    assert s.pitch_measured == pytest.approx(MG_PITCH, abs=1.0)


def test_the_cpode_sites_come_back_when_you_ask_for_fill():
    """CPODE 跟 MG **共用同一個 pitch**（使用者原話），所以填了 MG 的 pitch
    之後晶格排得到那兩個位置 —— ``fill_rule="fill"`` 就是要它們。"""
    s = algo_grid.find_stripes(_mg_cpode(), axis="x", select="brightest",
                               kinds=3, pitch=MG_PITCH, fill_rule="fill")
    assert len(s.selected) == 6, _centres(s.selected)
    assert s.filled == 2, "補回來的應該正好是那兩個 CPODE"

    got = _centres(s.selected)
    for site in CPODE_SITES:
        want = site * MG_PITCH + MG_W / 2.0
        assert min(abs(c - want) for c in got) < 1.5, (
            "CPODE 應該在 %.1f，補出來的是 %s" % (want, got))


def test_the_cpode_can_be_the_thing_you_pick():
    """反過來也要成立：CPODE 是最暗的那一群，所以指名它就拿得到那兩根。"""
    s = algo_grid.find_stripes(_mg_cpode(), axis="x", select="darkest",
                               kinds=3)
    assert len(s.selected) == 2
    got = _centres(s.selected)
    for site in CPODE_SITES:
        want = site * MG_PITCH + MG_W / 2.0
        assert min(abs(c - want) for c in got) < 1.5, got


def test_the_rank_still_wins_when_it_needs_more_groups():
    """「第三亮」至少要分四群 —— 使用者說有兩種材質也不能少分，
    不然那個排名根本指不到東西。"""
    levels = [10.0, 90.0, 150.0, 220.0]
    bands = [(0, 4), (10, 14), (20, 24), (30, 34)]
    picked = algo_grid.select_bands(bands, levels, "third_brightest", kinds=2)
    assert picked == [(10, 14)], picked


def test_two_kinds_is_what_it_always_did():
    """預設 0 = 舊行為。這個參數是出口不是新規則。"""
    plain = _mg_cpode(cpode=False)
    a = algo_grid.find_stripes(plain, axis="x", select="brightest")
    b = algo_grid.find_stripes(plain, axis="x", select="brightest", kinds=2)
    assert a.selected == b.selected


# --------------------------------------------------------------------------- #
# 2. 給定線寬
# --------------------------------------------------------------------------- #
def test_a_given_width_is_the_width_every_stripe_gets():
    s = algo_grid.find_stripes(_mg_cpode(), axis="x", select="brightest",
                               kinds=3, pitch=MG_PITCH, width=MG_W,
                               fill_rule="fill")
    inside = [(a, b) for a, b in s.selected if a > 0.5 and b < SIZE - 0.5]
    assert len(inside) >= 4
    for a, b in inside:
        assert (b - a) == pytest.approx(MG_W, abs=0.01), s.selected
    assert s.width_used == pytest.approx(MG_W)
    assert s.width_fixed is True


def test_a_given_width_keeps_the_middle_where_the_image_says_it_is():
    """給的是**寬度**，不是位置。中心仍然來自影像 —— 不然這個參數就變成
    「假裝這裡有一根線」，那是另一件（危險得多的）事。"""
    img = _mg_cpode()
    free = algo_grid.find_stripes(img, axis="x", select="brightest", kinds=3)
    fixed = algo_grid.find_stripes(img, axis="x", select="brightest", kinds=3,
                                   width=MG_W)
    a, b = _centres(free.selected), _centres(fixed.selected)
    assert len(a) == len(b)
    # 左右兩端被影像切到的那幾根中心本來就會變（切掉一半），所以只比中間的
    for u, v in zip(a[1:-1], b[1:-1]):
        assert u == pytest.approx(v, abs=0.05)


def test_a_stripe_hanging_off_the_edge_is_cut_not_pushed_back_in():
    """只露出半根的線就是只有半根。把它推回影像裡等於捏造一個不存在的位置，
    而框正是貼著它放的。"""
    s = algo_grid.find_stripes(_mg_cpode(), axis="x", select="brightest",
                               kinds=3, pitch=MG_PITCH, width=MG_W,
                               fill_rule="fill")
    first = min(s.selected)
    assert first[0] == pytest.approx(0.0, abs=0.01)
    assert (first[1] - first[0]) < MG_W, (
        "邊上那根被補成整根寬 —— 它有一半在影像外面")


def test_a_given_width_works_without_a_pitch():
    """兩件事是分開的：一個講「每隔多遠有一根」，一個講「一根多寬」。
    只知道其中一個也要用得上。"""
    s = algo_grid.find_stripes(_mg_cpode(), axis="x", select="brightest",
                               kinds=3, width=MG_W)
    assert s.width_fixed is True
    inside = [(a, b) for a, b in s.selected if a > 0.5 and b < SIZE - 0.5]
    assert inside
    for a, b in inside:
        assert (b - a) == pytest.approx(MG_W, abs=0.01)


def test_a_given_width_survives_a_stripe_that_is_drawn_too_wide():
    """這是給定線寬真正在買的東西。一根線寬異常的 MG（缺陷、或只是製程變異）
    會讓貼著它放的框往外挪 —— 而那正是最需要量準的那一根。"""
    img = _mg_cpode(cpode=False)
    img[:, 3 * MG_PITCH:3 * MG_PITCH + MG_W + 5] = 220.0     # 這一根胖了 5px

    free = algo_grid.find_stripes(img, axis="x", select="brightest",
                                  pitch=MG_PITCH)
    fixed = algo_grid.find_stripes(img, axis="x", select="brightest",
                                   pitch=MG_PITCH, width=MG_W)

    def width_at(s, site):
        want = site * MG_PITCH + MG_W / 2.0
        a, b = min(s.selected, key=lambda t: abs((t[0] + t[1]) / 2.0 - want))
        return b - a

    assert width_at(free, 3) > MG_W + 3, "合成資料沒有真的變胖？"
    assert width_at(fixed, 3) == pytest.approx(MG_W, abs=0.01)


# --------------------------------------------------------------------------- #
# 3. 接到卡片上（使用者描述的那條流程整條走一次）
# --------------------------------------------------------------------------- #
def _run(**over):
    params = {"source": "ref", "place": "beside_vertical", "box_size": 5.0,
              "gap": 1.0, "inset": 3.0, "roi_out": "xing",
              "vertical_pitch": MG_PITCH, "horizontal_pitch": EPI_PITCH}
    params.update(over)
    img = _mg_cpode()
    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
    region_card("roi_cross")().run(ctx, params)
    return ctx


def test_the_card_takes_both_new_settings():
    ctx = _run(vertical_kinds=3, vertical_width=float(MG_W),
               fill_rule="fill")
    rec = ctx.meta["crossings"]["xing"]["x"]
    assert rec["width_fixed"] is True
    assert rec["width_used"] == pytest.approx(MG_W)
    assert len(rec["selected"]) == 6, "六個晶格點（四根 MG + 兩個 CPODE）"


def test_the_boxes_hug_the_metal_edge_on_both_kinds_of_site():
    """使用者的流程：profile 定中心 → 給定 MG 寬度 → 從 MG 邊界往外長 ROI。
    CPODE 那一格也要有框，而且**貼的距離跟 MG 那幾格一樣** —— 它是同一排的
    一部分，量到的東西才比得起來。"""
    ctx = _run(vertical_kinds=3, vertical_width=float(MG_W), gap=1.0,
               box_size=5.0, side="end", fill_rule="fill")
    boxes = ctx.roi_rects("xing", (SIZE, SIZE))
    assert boxes

    # 每個框的左緣離它右邊那根線的左緣有多遠 —— 全部應該一樣（gap）。
    lefts = []
    for x, _y, _w, _h in boxes:
        site = round((x - MG_W - 1.0) / MG_PITCH)
        lefts.append(x - (site * MG_PITCH + MG_W))
    assert max(lefts) - min(lefts) <= 1, (
        "框離線的距離不一致：%s —— CPODE 那一格跟 MG 那幾格對不起來" % sorted(lefts))

    # 而且 CPODE 那格真的有框（不是只剩 MG 那幾格）。
    # 只驗 site 2：site 5 的線貼著影像右緣，它 end 側的框整個落在影像外面 ——
    # 那一格沒有框是對的（框放不下就是放不下，不是定位失敗）。
    sites = {round((x - MG_W - 1.0) / MG_PITCH) for x, _y, _w, _h in boxes}
    assert 2 in sites, sorted(sites)
    assert {0, 1, 2, 3, 4} <= sites, sorted(sites)


def test_leaving_both_at_zero_changes_nothing():
    """新參數預設不作用 —— 舊 recipe 逐格相同。"""
    a = _run().meta["crossings"]["xing"]
    b = _run(vertical_kinds=0, vertical_width=0.0,
             horizontal_kinds=0, horizontal_width=0.0
             ).meta["crossings"]["xing"]
    assert a["boxes"] == b["boxes"]
    assert a["x"]["selected"] == b["x"]["selected"]


# --------------------------------------------------------------------------- #
# 4. 晶格上「該有一根卻沒有」怎麼辦（F8 第六輪 —— 使用者：靠近 CPODE 不要有框）
# --------------------------------------------------------------------------- #
def _faint_mg(level: float, seed: int = 0) -> np.ndarray:
    """最左邊那根 MG 換成 ``level``。夠淡就抓不到，但它**還在**。"""
    img = _mg_cpode(cpode=False, seed=seed)
    img[:, :MG_W] = level
    return img


def test_a_faint_stripe_is_still_filled_in():
    """補線本來就是為了它 —— 這根線在，只是對比不足抓不到。
    ``skip`` 不能把這種也殺掉，不然它就只是把補線關掉而已。"""
    s = algo_grid.find_stripes(_faint_mg(150.0), axis="x", select="brightest",
                               pitch=MG_PITCH)          # 預設 skip
    assert s.filled >= 1, "淡掉的那根沒有被補回來"
    assert not s.blocked


def test_a_spot_that_is_plainly_another_material_is_left_out():
    """CPODE：亮度說「這裡沒有 MG」。補上去就是無中生有 —— 而框會貼著那個
    不存在的邊界放，看起來跟其他框一模一樣。"""
    s = algo_grid.find_stripes(_mg_cpode(), axis="x", select="brightest",
                               kinds=3, pitch=MG_PITCH)  # 預設 skip
    assert len(s.blocked) == 2, _centres(s.blocked)
    got = _centres(s.blocked)
    for site in CPODE_SITES:
        want = site * MG_PITCH + MG_W / 2.0
        assert min(abs(c - want) for c in got) < 1.5, got
    # 而且不在條紋裡 —— 也就不會有框長在上面
    for c in got:
        assert all(abs((a + b) / 2.0 - c) > 2.0 for a, b in s.selected)


def test_the_margin_is_what_separates_faint_from_absent():
    """把最左邊那根 MG 換成各種灰階，看規則切在哪。

    沒有邊際的話，「那一格就是背景」會變成擲硬幣 —— 灰階與背景只差雜訊，
    補不補得回來由 seed 決定。邊際取的是**反差的比例**不是固定灰階值，
    因為反差會隨機台漂移（跟 ``select`` 用排名同一個道理）。

    背景（沒有 MG 的那幾欄）約 127，目標約 220 → 邊際 23，切在 104 附近。
    """
    seen = {}
    for level in (220.0, 190.0, 150.0, 120.0, 90.0, 60.0):
        s = algo_grid.find_stripes(_faint_mg(level), axis="x",
                                   select="brightest", kinds=3,
                                   pitch=MG_PITCH)
        seen[level] = (s.filled, len(s.blocked))

    # 還看得出是一根線（在背景之上或就在背景附近）→ 補回來，不擋
    for level in (220.0, 190.0, 150.0, 120.0):
        assert seen[level][1] == 0, "level %.0f 被擋掉了：%s" % (level, seen)
    assert seen[190.0][0] >= 1 and seen[150.0][0] >= 1, seen
    # 掉到背景**以下**一大截 → 有正面證據說它是別的東西
    for level in (90.0, 60.0):
        assert seen[level][1] == 1, "level %.0f 沒被擋：%s" % (level, seen)
        assert seen[level][0] == 0, seen


def test_the_material_check_cannot_save_a_broken_selection():
    """順序很重要，而且這條順序解釋了為什麼 ``kinds`` 仍然要填。

    材質檢查只審**補出來的**位置。挑組挑錯的時候根本不會有補出來的位置
    （量到的 pitch 已經是實際的一半，晶格也就跟著錯），所以它一個字都講不出來
    —— 下游的檢查救不了上游的錯。
    """
    very_dark = _faint_mg(20.0)          # 第三種材質，跟 CPODE 一樣
    broken = algo_grid.find_stripes(very_dark, axis="x", select="brightest",
                                    pitch=MG_PITCH)          # kinds 沒填
    fixed = algo_grid.find_stripes(very_dark, axis="x", select="brightest",
                                   kinds=3, pitch=MG_PITCH)

    assert broken.pitch_measured == pytest.approx(MG_PITCH / 2.0, abs=1.0)
    assert not broken.blocked, "挑組是錯的，材質檢查卻以為一切正常"
    assert fixed.pitch_measured == pytest.approx(MG_PITCH, abs=1.0)
    assert len(fixed.blocked) == 1


def test_fill_is_still_available_for_when_you_know_better():
    """使用者說「這裡就是有一根，只是這台機器照不出來」時要有地方講。"""
    a = algo_grid.find_stripes(_mg_cpode(), axis="x", select="brightest",
                               kinds=3, pitch=MG_PITCH, fill_rule="fill")
    b = algo_grid.find_stripes(_mg_cpode(), axis="x", select="brightest",
                               kinds=3, pitch=MG_PITCH, fill_rule="skip")
    assert len(a.selected) == len(b.selected) + 2
    assert not a.blocked


def _boxes(**over):
    params = {"source": "ref", "place": "beside_vertical", "box_size": 5.0,
              "gap": 1.0, "inset": 3.0, "roi_out": "xing", "side": "both",
              "vertical_kinds": 3, "vertical_width": float(MG_W),
              "vertical_pitch": MG_PITCH, "horizontal_pitch": EPI_PITCH,
              "max_boxes": 999}
    params.update(over)
    img = _mg_cpode()
    ctx = Context(images={"test": img.copy(), "ref": img.copy()})
    region_card("roi_cross")().run(ctx, params)
    return sorted({x for x, _y, _w, _h in ctx.roi_rects("xing", (SIZE, SIZE))})


def test_skip_clear_also_drops_the_box_facing_the_odd_one_out():
    """使用者原話：「靠近 CPODE 的不能出現 BOX」。

    ``skip`` 只保證 CPODE **那一格**沒有框；它左右兩根 MG 面向它的那一側仍然
    有框，而那一小條 EPI 的對面不是 MG —— 「MG 旁邊的 EPI」跟「CPODE 旁邊的
    EPI」不是同一個東西，混在同一組數字裡就分不出來了。
    """
    skip = _boxes(fill_rule="skip")
    clear = _boxes(fill_rule="skip_clear")
    assert len(clear) < len(skip), "skip_clear 沒有少掉任何框"

    gone = sorted(set(skip) - set(clear))
    assert len(gone) == 3, gone       # 第 2 格左右各一、第 5 格左邊一個
    for x in gone:
        near = min(abs(x - (s * MG_PITCH + MG_W / 2.0)) for s in CPODE_SITES)
        assert near < MG_PITCH, "拿掉的框 x=%d 不在任何 CPODE 旁邊" % x


def test_skip_clear_keeps_every_box_that_faces_a_real_stripe():
    """只砍面向 CPODE 的那一側 —— 同一根 MG 的**另一側**照樣要有框，
    不然這個選項就變成「CPODE 附近整根 MG 都不要」。"""
    clear = _boxes(fill_rule="skip_clear")
    assert clear, "全砍光了"
    for site in (0, 1, 3, 4):
        want = site * MG_PITCH + MG_W / 2.0
        assert any(abs(x - want) < MG_PITCH for x in clear), (
            "第 %d 格（真的 MG）附近一個框都沒有：%s" % (site, clear))


def test_a_layout_with_no_odd_sites_is_untouched_by_the_rule():
    """沒有 CPODE 的 patch，三種設定要給出一模一樣的框 ——
    這個規則是出口，不是新行為。"""
    def run(rule):
        img = _mg_cpode(cpode=False)
        ctx = Context(images={"test": img.copy(), "ref": img.copy()})
        region_card("roi_cross")().run(ctx, {
            "source": "ref", "place": "beside_vertical", "box_size": 5.0,
            "roi_out": "xing", "vertical_pitch": MG_PITCH,
            "horizontal_pitch": EPI_PITCH, "fill_rule": rule})
        return ctx.meta["crossings"]["xing"]["boxes"]

    assert run("fill") == run("skip") == run("skip_clear")

# F11 Region-5：同一張 Template 卡也是「單張大圖」那條路（2026-08-18）。
"""使用者原本以為那要另一張卡：

> 「他是用在 repeating pattern 的 SEM（單張影像圖），他鋪 ROI 的方式就是跟
>   template 很像，只不過他是反向把單 cell 鋪回去，不過這樣的話他應該就是要放在
>   ROI 內的，你覺得他要叫什麼名字?」

**量過之後答案是「不必新卡」**：`algo/template.roi_boxes_in_patch` 明講自己同時
涵蓋兩種大小關係，而餵一張 1000×1000 進去確實得到 625 個框、相位正確。
兩種用法的差別完全在「接哪一條流」（F9：資料從哪來由線決定），不是一個下拉。

這一份鎖住那個「不必新卡」的判斷 —— 它一旦不成立（例如哪天有人把大圖那條路
擋掉），這裡會紅，而那正是該回來重開一張卡的時候。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.algo import template as algo_template  # noqa: E402
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.context import Context  # noqa: E402

PITCH = 40


def periodic(n: int = 400, pitch: int = PITCH, seed: int = 0) -> np.ndarray:
    """兩軸都重複的合成 SEM（跟 `make_sample_rsem` 同一種東西，小一點）。"""
    rng = np.random.default_rng(seed)
    img = np.zeros((n, n), np.float32)
    for x in range(0, n, pitch):
        img[:, x:x + pitch // 2] = 190.0
    for y in range(0, n, pitch):
        img[y:y + pitch // 3, :] += 25.0
    img += rng.normal(0, 2.0, img.shape).astype(np.float32)
    return np.clip(img, 0, 255).astype(np.uint8)


def _frozen(src: np.ndarray) -> str:
    return algo_template.encode_cell(algo_template.build_golden_cell(src).cell)


def _run(image, regions="epi: 0.05,0.05,0.35,0.35", **over):
    ctx = Context(images={"ref": np.asarray(image)})
    params = dict({"source": "ref", "template": _frozen(periodic()),
                   "regions": regions, "locate_axis": "both"}, **over)
    get_step("roi_template")().run(
        ctx, get_step("roi_template").validate_params(params))
    return ctx


# --------------------------------------------------------------------------- #
# 1. 大圖上每一份都要畫
# --------------------------------------------------------------------------- #
def test_a_full_size_image_gets_a_box_on_every_repeat():
    """cell 比圖小很多 —— 400/40 = 10×10 = 100 份，一份都不能少。

    只取離中心最近的那一份，會在「cell 比圖小」的時候**只量到一根 EPI，其餘的
    靜靜漏掉**，而那正是「跑得完、有數字、而且是錯的」。
    """
    ctx = _run(periodic(seed=3))
    assert ctx.features["locate_ok"] == 1.0
    assert ctx.roi_count("epi") == 100
    assert ctx.features["epi_present"] == 1.0
    assert ctx.features["epi_clipped"] == 0.0


def test_the_centre_copy_and_the_rest_are_still_split():
    """`_center` / `_others` 在大圖上一樣成立 —— 缺陷仍然在正中心。

    這就是單張影像做 cell-to-cell 比較的入口：`Compare regions` 拿
    `epi_center` 對 `epi_others`。
    """
    ctx = _run(periodic(seed=4))
    assert ctx.roi_count("epi_center") == 1
    assert ctx.roi_count("epi_others") == ctx.roi_count("epi") - 1
    (x, y, w, h), = ctx.roi_rects("epi_center", (400, 400))
    # 中心那一份要真的靠近正中央（一格之內）
    assert abs(x + w / 2 - 200) <= PITCH and abs(y + h / 2 - 200) <= PITCH


def test_a_patch_smaller_than_one_cell_still_works_the_old_way():
    """另一半不可以壞掉：cell 比 patch 大 → 最多一份，可能一份都沒有。"""
    patch = periodic(seed=5)[100:132, 100:132]      # 32 px，比一格 40 小
    ctx = _run(patch, regions="epi: 0.05,0.05,0.35,0.35")
    assert ctx.roi_count("epi") <= 2
    assert ctx.features["epi_boxes"] == float(ctx.roi_count("epi"))


# --------------------------------------------------------------------------- #
# 2. 那個上限：唯一真的擋路的東西
# --------------------------------------------------------------------------- #
def test_the_default_limit_no_longer_silently_keeps_64_of_them():
    """預設 64 會把 100 份安靜留 64 份 —— 而那 64 份算得出一個很正常的灰階值。"""
    spec = {p.name: p for p in get_step("roi_template").params}["max_boxes"]
    assert spec.default == 8192, "預設要撐得住整張大圖"
    # 跟 `roi_from_mask` 用同一組數字：兩張會吐幾千個框的 ROI 卡不該有兩套上限
    gds = {p.name: p for p in get_step("roi_from_mask").params}["max_boxes"]
    assert (spec.default, spec.max) == (gds.default, gds.max)


def test_hitting_the_limit_is_reported_not_silent():
    ctx = _run(periodic(seed=6), max_boxes=25)
    assert ctx.roi_count("epi") == 25
    assert ctx.features["epi_clipped"] == 1.0
    # 整個家族拿到同一個旗標（下游手上只有一個名字）
    assert ctx.features["epi_center_clipped"] == 1.0
    assert ctx.features["epi_others_clipped"] == 1.0


def test_not_capping_a_finely_repeating_image_is_still_fast():
    """上限存在是為了下游的成本，不是因為這一段慢。

    實測（1000×1000、4 px pitch、62500 個框）83 ms —— 所以把預設從 64 拉到
    8192 沒有效能代價，而那個代價才是原本那個小數字唯一站得住的理由。
    """
    src = periodic(n=400, pitch=8, seed=7)
    frozen = algo_template.encode_cell(
        algo_template.build_golden_cell(src).cell)
    ctx = Context(images={"ref": src})
    params = get_step("roi_template").validate_params(
        {"source": "ref", "template": frozen,
         "regions": "epi: 0.05,0.05,0.35,0.35", "locate_axis": "both",
         "max_boxes": 65536})
    t = time.perf_counter()
    get_step("roi_template")().run(ctx, params)
    dt = time.perf_counter() - t
    assert ctx.roi_count("epi") > 1000
    assert dt < 5.0, "不封頂就慢到不能用的話，那個小預設才有理由回來（%.1fs）" % dt


# --------------------------------------------------------------------------- #
# 3. 卡片自己要講得出兩種用法
# --------------------------------------------------------------------------- #
def test_the_card_says_it_works_on_a_full_size_image_too():
    """使用者不會自己猜到 Template 吃得下大圖 —— 猜不到的功能等於沒有。"""
    d = get_step("roi_template").describe()
    blurb = str(d["help"]).lower()
    assert "full-size" in blurb or "full size" in blurb
    source = {p["name"]: p for p in d["params"]}["source"]
    assert "single" in str(source["help"]).lower()

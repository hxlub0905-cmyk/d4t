# -*- coding: utf-8 -*-
"""區域線進了 ``recipe.edges`` 之後，引擎那一頭要對（F42 方案 B 的 B1）。

這一份鎖住四件事
----------------
1. **判準只有一支**：``recipe.is_region_edge``（``dst_in`` 指到的參數是不是
   ``region_key`` / ``region_keys``）。
2. **影像綁定跳過區域線** —— ``engine._explicit_bindings`` 那段 ``else:
   continue``。收它進去的話，這條線會被當成一條指向不存在的流的影像線。
3. **``execution_order`` 自然吃到它**（它只看 src/dst）——
   **這一條就是本輪要修的 bug 的回歸測試**，見下面。
4. 來源埠沒填的區域線 → ``region-edge-no-port``（warning）。

那個 bug 長什麼樣
-----------------
把 Region 卡放在量測卡**右邊**（route 上排在後面），畫布上一條區域線指著它。
F17-① 之後 ``execution_order`` 只看線，而**區域線不在 ``edges`` 裡**（F12 §3）
—— 所以那兩張卡在引擎眼裡毫無關係，量測卡先跑，``ctx.rois`` 還是空的，
於是它**安靜地退回量整張圖**。

跑得完、有數字、而且是錯的。第七個。

為什麼用假卡片而不是真的 ``roi_reference``
------------------------------------------
真的那張要在影像上**找**得到條紋才吐得出區域，於是這一份會同時測到「找得準
不準」—— 而它要問的是順序。假卡片把區域寫死，答案因此只有一個變因。
（同一個理由，``tests/test_recipe.py`` 的 dummy 卡片也是這樣做的。）
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps  # noqa: F401,E402 — 真的卡片（§1 第二組斷言用）
from d4t.core.pipeline.engine import _explicit_bindings, run_defect  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    Edge, Recipe, RecipeNode, ScoreSpec, execution_order, is_region_edge,
    validate,
)
from d4t.core.pipeline.step import (  # noqa: E402
    CATEGORY_ALGO, CATEGORY_IMAGE, REGISTRY, ParamSpec, Step, get_step,
)

KIND = "ebi_patch"
H = W = 64
#: 影像左半 200、右半 100。整張圖的平均是 150，只量左半是 200 ——
#: **一個數字就分得出「有沒有吃到區域」**。
LEFT = (0.0, 0.0, 0.5, 1.0)


# --------------------------------------------------------------------------- #
# 假卡片（只給這一份用；不註冊進 REGISTRY）
# --------------------------------------------------------------------------- #
class TLoad(Step):
    key = "t_load"
    label = "測試載入"
    category = CATEGORY_IMAGE
    help = "測試用：寫一張左亮右暗的圖進 test。"
    writes = ["test"]

    def run(self, ctx, params):
        img = np.full((H, W), 100, np.float32)
        img[:, :W // 2] = 200.0
        ctx.set_image("test", img)
        return ctx


class TRegion(Step):
    key = "t_region"
    label = "測試區域"
    category = CATEGORY_IMAGE
    help = "測試用：把左半張圖定義成區域 'epi'。"
    reads = ["test"]

    @classmethod
    def resolve_regions_out(cls, params):
        return ["epi"]

    def run(self, ctx, params):
        ctx.set_roi("epi", LEFT)
        return ctx


class TMeasure(Step):
    key = "t_measure"
    label = "測試量測"
    category = CATEGORY_ALGO
    help = "測試用：量 roi 那一塊的平均（沒有那個區域就量整張）。"
    reads = ["test"]
    features_out = ["glv_mean"]
    params = [
        ParamSpec(name="source", type="image_key", default="test",
                  direction="in", help="要量哪一條影像流。"),
        ParamSpec(name="roi", type="region_key", default="", direction="in",
                  help="要量哪一個具名區域（空的 = 整張圖）。"),
    ]

    @classmethod
    def resolve_regions_in(cls, params):
        name = str(params.get("roi", "") or "")
        return [name] if name else []

    def run(self, ctx, params):
        p = self.validate_params(params)
        img = ctx.require_image(str(p["source"]))
        name = str(p["roi"] or "")
        # **這正是真卡片的行為**：區域不在就退回整張圖（`_util.crop_to_roi`）。
        # bug 的症狀就長在這一行 —— 它不會失敗，它會給一個別的數字。
        if name and name in ctx.roi_names():
            x, y, w, h = ctx.roi_rects(name, img.shape)[0]
            img = img[y:y + h, x:x + w]
        ctx.add_feature("glv_mean", float(np.mean(img)))
        return ctx


REG = {c.key: c for c in (TLoad, TRegion, TMeasure)}


def _recipe(route, edges=(), roi="epi"):
    nodes = {
        "load": RecipeNode("load", "t_load", {}),
        "roi": RecipeNode("roi", "t_region", {}),
        "glv": RecipeNode("glv", "t_measure", {"source": "test", "roi": roi}),
    }
    return Recipe(
        recipe_id="t", routes={KIND: list(route)},
        nodes={n: nodes[n] for n in route},
        edges=[e if isinstance(e, Edge) else Edge(*e) for e in edges],
        score=ScoreSpec(expr="glv_mean", threshold=0.0,
                        bins={"below": 0, "above": 1}))


#: 「量測卡排在 Region 卡**前面**」——bug 的排法。
BACKWARDS = ["load", "glv", "roi"]
#: 那條區域線：Region 卡的 ``epi`` 埠 → 量測卡的 ``roi`` 那一格。
REGION_EDGE = Edge("roi", "glv", "epi", "roi")
#: 影像線（兩種排法都要有，不然 `not-connected` 會先擋下來）。
IMAGE_EDGES = [Edge("load", "roi", "test", "source"),
               Edge("load", "glv", "test", "source")]


# --------------------------------------------------------------------------- #
# 1. is_region_edge —— 唯一的判準
# --------------------------------------------------------------------------- #
def test_a_line_landing_on_a_region_parameter_is_a_region_edge():
    nodes = _recipe(BACKWARDS).nodes
    assert is_region_edge(REGION_EDGE, nodes, REG) is True


def test_a_line_landing_on_an_image_parameter_is_not():
    nodes = _recipe(BACKWARDS).nodes
    assert is_region_edge(Edge("load", "glv", "test", "source"),
                          nodes, REG) is False


def test_a_line_with_no_destination_port_is_never_a_region_edge():
    """埠空著的邊「只表達先後順序」（見 `Edge`）—— 分不出型別，也就沒有區域
    可言。方案 B 因此規定區域線的 ``dst_in`` **必填**。

    這**不是漏判**：把它判成區域線的話，每一條舊格式的兩欄邊都會變成區域線
    （下面 §5 最後一條就是那個後果）。

    ⚠ 這一條釘的是**契約**，不是那個 early return —— 拿掉那兩行判準也照樣答
    False（沒有參數叫空字串）。契約要釘，因為 B2／B3 整個踩在它上面。
    """
    nodes = _recipe(BACKWARDS).nodes
    assert is_region_edge(Edge("roi", "glv"), nodes, REG) is False
    # 只有來源埠、沒有落點也一樣（那條線沒說它要進哪一格）。
    assert is_region_edge(Edge("roi", "glv", "epi", ""), nodes, REG) is False


def test_a_line_into_a_card_or_parameter_that_does_not_exist_is_not_one():
    """壞掉的 recipe 不准讓判準爆掉 —— 壞在哪由別的 lint 講。"""
    nodes = _recipe(BACKWARDS).nodes
    assert is_region_edge(Edge("roi", "ghost", "epi", "roi"),
                          nodes, REG) is False
    assert is_region_edge(Edge("roi", "glv", "epi", "no_such_param"),
                          nodes, REG) is False


def test_it_agrees_with_the_real_cards_in_the_registry():
    """假卡片測完之後對真的問一次 —— 兩張型別各不同的真卡。

    `roi_mask` 的 ``regions`` 是 ``region_keys``（一串），`glv_stats` 的
    ``roi`` 是 ``region_key``（單一）。**兩種都要算區域線**，不然「多連一」
    那條路上的線會被當成影像線。
    """
    nodes = {
        "m": RecipeNode("m", "roi_mask",
                        {"regions": "epi", "source": "test", "out": "mask"}),
        "g": RecipeNode("g", "glv_stats", {"source": "test", "roi": "epi"}),
    }
    assert is_region_edge(Edge("r", "m", "epi", "regions"), nodes) is True
    assert is_region_edge(Edge("r", "g", "epi", "roi"), nodes) is True
    assert is_region_edge(Edge("r", "m", "test", "source"), nodes) is False


def test_every_region_parameter_in_the_card_library_is_recognised():
    """整個卡片庫掃一次：`region_input_specs()` 說是區域的那幾格，
    `is_region_edge` 一格都不准漏。

    兩支各自寫一份判斷的話，新加一張卡時會有一份長歪 —— 而那一份長歪的後果是
    「畫布畫一條線，引擎當它不存在」。
    """
    seen = 0
    for key, cls in REGISTRY.items():
        nodes = {"n": RecipeNode("n", key, {})}
        for spec in cls.region_input_specs():
            seen += 1
            assert is_region_edge(Edge("up", "n", "epi", spec.name), nodes), \
                f"{key}.{spec.name} 是區域格，卻沒被當成區域線"
    assert seen, "卡片庫裡一個區域參數都沒有 —— 這條測試在空轉"


# --------------------------------------------------------------------------- #
# 2. 引擎的影像綁定要跳過區域線
# --------------------------------------------------------------------------- #
def test_the_image_binding_ignores_a_region_edge():
    """`_explicit_bindings` 收的是 ``(節點, 流名) → (來源節點, 來源埠)``。

    區域走的是 ``ctx.rois`` 那一套，不是這張表。放它進來的話 ``epi`` 會變成
    一條**指向不存在的影像流**的線 —— 而那張表是量測卡拿影像的唯一依據。
    """
    rec = _recipe(BACKWARDS, IMAGE_EDGES + [REGION_EDGE])
    bind = _explicit_bindings(rec, REG)
    assert ("glv", "test") in bind, "影像線照樣要在"
    assert ("glv", "epi") not in bind, "區域線不准變成一條影像流"
    assert not any(k[1] == "epi" for k in bind), \
        "區域名一個字都不該出現在影像表裡"


def test_only_the_image_edges_survive_into_the_binding_table():
    """換個問法：**加一條區域線不改變影像表的任何一格。**"""
    without = _explicit_bindings(_recipe(BACKWARDS, IMAGE_EDGES), REG)
    with_region = _explicit_bindings(
        _recipe(BACKWARDS, IMAGE_EDGES + [REGION_EDGE]), REG)
    assert without == with_region


# --------------------------------------------------------------------------- #
# 3. 執行順序 —— 本輪那個 bug 的回歸測試
# --------------------------------------------------------------------------- #
def test_the_region_card_runs_first_even_when_it_sits_to_the_right():
    """**這一條就是修好的證明。**

    route 的排列是 load → glv → roi（Region 卡在量測卡右邊），而區域線指著
    它。線說了算（F17-①），所以 roi 要排在 glv 前面。
    """
    rec = _recipe(BACKWARDS, IMAGE_EDGES + [REGION_EDGE])
    order = execution_order(rec, KIND)
    assert order.index("roi") < order.index("glv"), \
        f"區域線沒有排出順序：{order}"


def test_without_the_region_edge_the_order_follows_the_layout():
    """**bug 的形狀**：沒有那條線的時候，順序由卡片被拖到哪裡決定。

    這一條不是「應該的行為」，它是 F12 §3 之下唯一可能的行為 —— 留著是為了讓
    上一條的差異看得見：兩份 recipe 只差一條線。
    """
    rec = _recipe(BACKWARDS, IMAGE_EDGES)
    assert execution_order(rec, KIND) == BACKWARDS


def test_a_region_edge_does_not_disturb_an_already_correct_order():
    """Region 卡本來就在左邊時，加線不改變任何東西（純重構的前提）。"""
    forward = ["load", "roi", "glv"]
    plain = execution_order(_recipe(forward, IMAGE_EDGES), KIND)
    wired = execution_order(
        _recipe(forward, IMAGE_EDGES + [REGION_EDGE]), KIND)
    assert plain == wired == forward


# --------------------------------------------------------------------------- #
# 4. 端對端：那條線真的換掉了算出來的數字
# --------------------------------------------------------------------------- #
def _mean(edges):
    res = run_defect(_recipe(BACKWARDS, edges), None, KIND, registry=REG)
    assert res.ok, res.error
    return res.features["glv_mean"]


def test_the_line_is_the_difference_between_200_and_150():
    """左半 200、右半 100 的一張圖。

    * 有區域線 → 量的是左半 → **200**
    * 沒有區域線 → 量測卡先跑，``ctx.rois`` 是空的 → 退回整張圖 → **150**

    兩邊都 ``ok=True``、都有數字。這就是「跑得完、有數字、而且是錯的」。
    """
    assert _mean(IMAGE_EDGES + [REGION_EDGE]) == pytest.approx(200.0)
    assert _mean(IMAGE_EDGES) == pytest.approx(150.0)


# --------------------------------------------------------------------------- #
# 5. 來源埠沒填的區域線
# --------------------------------------------------------------------------- #
def _codes(rec):
    return [i.code for i in validate(rec, kind=KIND, registry=REG)]


def test_a_region_edge_with_no_source_port_is_a_warning():
    """``src_out`` 空著的區域線**排得出順序**（`execution_order` 只看 src/dst），
    所以它跑得完 —— 它只是沒有講出量的是哪一塊。

    畫布上看得到一條接好的線，而那張卡實際上退回量整張圖。
    """
    rec = _recipe(BACKWARDS, IMAGE_EDGES + [Edge("roi", "glv", "", "roi")],
                  roi="")
    issues = [i for i in validate(rec, kind=KIND, registry=REG)
              if i.code == "region-edge-no-port"]
    assert len(issues) == 1
    assert issues[0].level == "warning"
    assert issues[0].node_id == "glv"
    # 訊息要指得出**哪一條線**與**該去哪裡重拉**。
    assert "roi" in issues[0].detail and "diamond" in issues[0].detail


def test_a_properly_wired_region_edge_says_nothing():
    rec = _recipe(BACKWARDS, IMAGE_EDGES + [REGION_EDGE])
    assert "region-edge-no-port" not in _codes(rec)


def test_an_image_edge_with_no_source_port_is_not_this_warning():
    """埠空著的**影像**線是舊格式的常態（F9-1 之前的檔案全都是）——
    對它們講這句話等於每一份舊 recipe 都冒一條 warning。"""
    rec = _recipe(BACKWARDS, [Edge("load", "glv"), Edge("load", "roi")])
    assert "region-edge-no-port" not in _codes(rec)


# --------------------------------------------------------------------------- #
# 6. 區域線只是一條 Edge —— round-trip 一個位元都不會動
# --------------------------------------------------------------------------- #
def test_a_region_edge_survives_a_json_round_trip_unchanged():
    """鐵則 9：``to_json_dict → from_json_dict`` 是 `run_batch` 送 recipe 進
    worker 的路。區域線在那條路上掉一條，``workers=1`` 與 ``workers=2``
    就會算出不同的分數（200 vs 150，見 §4）。"""
    rec = _recipe(BACKWARDS, IMAGE_EDGES + [REGION_EDGE])
    again = Recipe.from_json_dict(rec.to_json_dict())
    assert again.edges == rec.edges
    assert again.to_json_dict() == rec.to_json_dict()
    assert execution_order(again, KIND) == execution_order(rec, KIND)

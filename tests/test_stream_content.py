# F110 驗收：一條影像流裝的是什麼（灰階／layout label map）。
"""**把 layout label map 接進 Normalize，今天是一條完全合法的線。**

而它是這個 repo 最貴的那種錯：label map 的像素值**就是層號**（0 = 背景、
1..N 是第 N 個 POI 層），所以正規化它、拉對比、平滑它 —— 三件事都跑得完、
都不報錯，而 1、2、3 被混成 1.7 這種不存在的層號之後，下游的每一個區域都是錯的。

`steps/load_sidecar.py` 的模組說明從 2026-08-18 起就逐字寫著這件事
（「label 一個像素都不能動」），但在 F110 之前那句話只是一句話 ——
lint 沒擋、畫布沒擋、引擎沒擋。這一份是把它變成三層裡的第一層。

⚠ 唯一擋得住它的時機是**接線的當下**：跑完之後沒有任何數字看得出來。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 註冊卡片
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    Edge, Recipe, RecipeNode, ScoreSpec, validate,
)
from d4t.core.pipeline.step import (  # noqa: E402
    CONTENT_KINDS, GRAY, LABEL, IMAGE_TYPES, REGISTRY, ParamError, ParamSpec,
)

LABEL_STREAM = "layout"


def _recipe(nodes, edges, kind: str = "ebi_patch") -> Recipe:
    return Recipe(
        recipe_id="content_test",
        routes={kind: [n[0] for n in nodes]},
        nodes={n[0]: RecipeNode(n[0], n[1], dict(n[2])) for n in nodes},
        score=ScoreSpec(expr="0", threshold=0.0, bins={"below": 0, "above": 1}),
        version=2, author="unit", description="content",
        edges=[Edge(*e) for e in edges])


def _codes(recipe) -> list:
    return [i.code for i in validate(recipe)]


def _issue(recipe, code: str):
    got = [i for i in validate(recipe) if i.code == code]
    assert got, "沒有 %s：%s" % (code, _codes(recipe))
    return got[0]


LOAD = ("load", "load_patch", {})
SIDECAR = ("gds", "load_sidecar", {"out": LABEL_STREAM})


# --------------------------------------------------------------------------- #
# 1. 那條線現在擋得住了
# --------------------------------------------------------------------------- #
def test_a_label_map_wired_into_normalize_is_an_error():
    r = _recipe(
        [LOAD, SIDECAR, ("n1", "normalize", {"streams": LABEL_STREAM})],
        [("gds", "n1", LABEL_STREAM, "streams")])
    issue = _issue(r, "wrong-content")
    assert issue.level == "error", "下游拿到的東西**一定**是錯的，不是可能"
    assert issue.node_id == "n1"
    assert LABEL_STREAM in issue.detail
    # 訊息要講得出**為什麼**，不能只說「型別不對」——目標使用者不會寫 code
    assert "layer number" in issue.detail
    assert "would not fail" in issue.detail, "最關鍵的那句話：它不會報錯"


@pytest.mark.parametrize("key,param", [
    ("normalize", "streams"), ("denoise", "streams"),
    ("tone", "streams"), ("flatten", "streams"),
    ("subtract", "a"), ("align", "streams"),
    ("glv_stats", "source"), ("focus_quality", "source"),
])
def test_every_ordinary_image_port_refuses_a_label_map(key, param):
    """**保守的預設是刻意的。** 加一張新卡的人不必想這件事就受保護；
    真的想收 label map 的那一張要明講。"""
    r = _recipe([LOAD, SIDECAR, ("x", key, {param: LABEL_STREAM})],
                [("gds", "x", LABEL_STREAM, param)])
    assert "wrong-content" in _codes(r), "%s 的 %s 收下了 label map" % (key, param)


def test_the_region_card_is_the_one_place_it_belongs():
    """接到它該去的地方**不能**報錯 —— 一條擋掉所有東西的 lint 是個 bug。"""
    r = _recipe(
        [LOAD, SIDECAR,
         ("roi", "roi_reference", {"method": "layout layers",
                                   "label_source": LABEL_STREAM})],
        [("gds", "roi", LABEL_STREAM, "label_source")])
    assert "wrong-content" not in _codes(r)


def test_plain_gray_goes_everywhere_it_used_to():
    """反向：沒有 label map 的 recipe **一條新 lint 都不該多出來**。"""
    r = _recipe(
        [LOAD, ("n1", "normalize", {"streams": "test,ref"}),
         ("sub", "subtract", {"a": "test", "b": "ref", "out": "diff"})],
        [("load", "n1", "test", "streams"), ("load", "n1", "ref", "streams"),
         ("n1", "sub", "test", "a"), ("n1", "sub", "ref", "b")])
    assert "wrong-content" not in _codes(r)


# --------------------------------------------------------------------------- #
# 2. 宣告本身
# --------------------------------------------------------------------------- #
def test_the_only_card_that_makes_a_label_map_says_so():
    out = [s for s in get_step("load_sidecar").params if s.name == "out"][0]
    assert out.content == LABEL
    assert out.content_written() == LABEL


def test_an_output_that_says_nothing_is_gray():
    """**沒宣告 = 灰階**，而那要是一個明確的答案不是空字串 ——
    傳播那一段拿它去比對，空字串會變成「不知道」而靜靜放行。"""
    out = [s for s in get_step("subtract").params if s.name == "out"][0]
    assert out.content == ""
    assert out.content_written() == GRAY
    assert out.accepts(GRAY) and not out.accepts(LABEL)


def test_a_content_kind_nobody_recognises_is_refused_at_import_time():
    """打錯字的下場要是註冊失敗，不是一格安靜地退化成「收所有東西」。"""
    with pytest.raises(ParamError):
        ParamSpec(name="x", type="image_key", default="", direction="out",
                  content="labels", help="typo'd kind")
    with pytest.raises(ParamError):
        ParamSpec(name="x", type="int", default=1, content=LABEL,
                  min=0, max=9, help="content on a number makes no sense")


def test_anything_that_can_be_made_can_also_be_taken():
    """**反向**：宣告得出 `label` 的輸出，要有至少一張卡收得下它。

    收不下的話，那條線在畫布上**永遠畫不出來** —— 而使用者會一直找那個埠。
    這一條也是下一次加內容型別時的清單：加了一種就要同時有人吐、有人吃。
    """
    made, taken = set(), set()
    for cls in REGISTRY.values():
        for spec in cls.params:
            if spec.type not in IMAGE_TYPES:
                continue
            if spec.direction == "out" and spec.content:
                made.add(spec.content)
            if spec.direction == "in" and spec.content:
                taken.add(spec.content)
    assert made <= taken, "產得出來卻沒有任何一格收得下：%s" % sorted(made - taken)
    assert made <= set(CONTENT_KINDS) and taken <= set(CONTENT_KINDS)


# --------------------------------------------------------------------------- #
# 3. `Context.labels` 真的不在了
# --------------------------------------------------------------------------- #
def test_the_second_way_to_pass_a_label_is_gone():
    """`Context.labels` 從 F7-9 起在引擎與快取裡被搬來搬去，而**沒有任何一張
    卡寫過它**。

    一個沒有人寫的欄位不是「還沒用到」，是一條**看起來存在的第二條路**：
    下一個要傳 label 的人會挑它，而它不進快取簽章、畫布上也沒有線 ——
    於是那條路上的每一個決定都看不見。
    """
    from d4t.core.pipeline.context import Context

    assert not hasattr(Context(), "labels"), (
        "`Context.labels` 又回來了 —— label map 走影像流（load_sidecar 的 out "
        "→ roi_reference 的 label_source），那條路上的每一格都畫得出線。")


def test_the_cache_snapshot_version_moved_with_the_field():
    """欄位集合改了就要換版本 —— 舊目錄裡的快照不會安靜地餵回來。"""
    from d4t.core.pipeline.cache import StageCache

    assert StageCache.FORMAT_VERSION >= 5

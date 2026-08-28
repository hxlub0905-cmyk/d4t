# PR-2（2a）：GLV 的兩條 kind 感知健檢 + info 級別的 CLI 面。
"""「這組設定對不對」有時取決於資料型別：`_center` 的幾何意義來自「patch 是
以 defect 為中心裁切的」，一顆一張大圖的 route 沒有這個保證；反過來 patch 上
缺陷位置已知，開 each box 去「找」worst 可能被髒污的參照格帶走。

判準住在卡片上（`Step.kind_issues`），`validate` 逐 route 呼叫 —— 這裡鎖正反
兩面，加一條「乾淨 recipe 不長新問題」的反空洞。
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout

import d4t.core.steps  # noqa: F401 - 註冊卡片
from d4t.core.pipeline.recipe import (
    Edge, Recipe, RecipeNode, ScoreSpec, hydrate_regions, validate,
)
from d4t.core.pipeline.step import PATCH_KINDS, REGISTRY, SINGLE_IMAGE_KINDS


def _recipe(kind, glv_params, edges=()):
    load = "load_single" if kind in SINGLE_IMAGE_KINDS else "load_patch"
    nodes = {
        "load": RecipeNode("load", load, {}),
        "roi": RecipeNode("roi", "roi_reference",
                          {"method": "stripes in the image",
                           "roi_out": "cells"}),
        "m1": RecipeNode("m1", "glv_stats", dict(glv_params)),
    }
    r = Recipe(
        recipe_id="kind_lint", routes={kind: ["load", "roi", "m1"]},
        nodes=nodes,
        score=ScoreSpec(expr="glv_median", threshold=0.0,
                        bins={"below": 0, "above": 1}),
        version=2, author="unit", description="",
        edges=[Edge(*e) for e in (
            ("load", "roi", "test", "source"),
            ("load", "m1", "test", "source")) + tuple(edges)])
    # 區域值從線水合（`from_json_dict` 對載入的檔案做的那一步）——
    # 直接建構的 Recipe 要自己補，不然 roi 那一格是空的。
    hydrate_regions(r.nodes, r.edges, REGISTRY)
    return r


def _found(recipe, code, kind=None):
    return [i for i in validate(recipe, kind=kind) if i.code == code]


CENTER_WIRE = (("roi", "m1", "cells_center", "roi"),)
PLAIN_WIRE = (("roi", "m1", "cells", "roi"),)


def test_center_roi_on_a_single_image_route_warns():
    r = _recipe("rsem", {"source": "test"}, edges=CENTER_WIRE)
    got = _found(r, "center-on-big-image")
    assert len(got) == 1
    assert got[0].level == "warning"
    assert got[0].node_id == "m1"
    # 那句話要講得出下一步：接全部的框 + each box。
    assert "each box" in got[0].detail and "cells" in got[0].detail


def test_the_same_wiring_on_a_patch_route_is_silent():
    r = _recipe("ebi_patch", {"source": "test"}, edges=CENTER_WIRE)
    assert _found(r, "center-on-big-image") == []


def test_each_box_on_a_patch_route_is_an_info():
    r = _recipe("ebi_patch", {"source": "test", "across_boxes": "each box"},
                edges=PLAIN_WIRE)
    got = _found(r, "each-box-on-patch")
    assert len(got) == 1
    assert got[0].level == "info", "工作單指定 info —— 不是 warning"
    assert "_center" in got[0].detail


def test_each_box_stays_silent_when_pooled_or_already_centred():
    pooled = _recipe("ebi_patch", {"source": "test"}, edges=PLAIN_WIRE)
    assert _found(pooled, "each-box-on-patch") == []
    # 已經接了 _center 的人不需要被建議去接 _center。
    centred = _recipe("ebi_patch",
                      {"source": "test", "across_boxes": "each box"},
                      edges=CENTER_WIRE)
    assert _found(centred, "each-box-on-patch") == []
    # 大圖上開 each box 正是那條 warning 建議的用法 —— 不報 info。
    rsem = _recipe("rsem", {"source": "test", "across_boxes": "each box"},
                   edges=PLAIN_WIRE)
    assert _found(rsem, "each-box-on-patch") == []


def test_a_clean_recipe_gains_no_new_issues():
    """反空洞的另一半：兩條新 lint 不在乾淨的組合上亂叫。"""
    r = _recipe("ebi_patch", {"source": "test"}, edges=PLAIN_WIRE)
    codes = {i.code for i in validate(r)}
    assert "center-on-big-image" not in codes
    assert "each-box-on-patch" not in codes


def test_the_kind_groups_cover_no_overlap():
    assert not (set(PATCH_KINDS) & set(SINGLE_IMAGE_KINDS))


# --------------------------------------------------------------------------- #
# info 級別（CLI 面；畫布面在 tests/test_ui_info_level.py）
# --------------------------------------------------------------------------- #
def test_cli_prints_a_dot_for_info_and_it_is_not_an_error():
    from d4t.__main__ import _print_issues

    r = _recipe("ebi_patch", {"source": "test", "across_boxes": "each box"},
                edges=PLAIN_WIRE)
    issues = [i for i in validate(r) if i.code == "each-box-on-patch"]
    assert issues, "反空洞：真的有一條 info 可印"
    buf = io.StringIO()
    with redirect_stdout(buf):
        has_error = _print_issues(issues)
    assert has_error is False, "info 不是 error，validate CLI 不該回非零"
    line = buf.getvalue().splitlines()[0]
    assert line.strip().startswith("·"), "info 印 ·，不是 warning 的 △"

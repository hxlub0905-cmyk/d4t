# F121 期 1：recipe 不再以資料型別當鑰匙。
"""**只有一條 route 的 recipe，不管資料是哪一種都跑那一條。**

使用者回報（2026-09-24）：跑沒有 KLARF 的 RSEM 影像，每一顆都報
``unknown input-type route 'folder'; this recipe only defines: ['ebi_patch']``。
recipe 用資料型別當 route 的鍵，而影像資料夾是 ``folder`` —— 鍵名對不上，
於是一條本來跑得動的 pipeline（一顆一張的卡在 `rsem` 與 `folder` 上一模一樣）
每一顆都在第一步失敗。

這一份鎖四件事：

1. 判準本身（`route_for`）—— 一條就是那一條、好幾條照舊挑同名的；
2. 引擎、整批、健檢、CLI 用的是**同一支**（健檢說會跑的那一條就是真的跑的那一條）；
3. kind 相依的 lint 問的是**資料**的型別，不是鍵名；
4. **反向**：手寫的多型別 recipe 碰到沒有的那一種，照舊講出來（不是安靜地挑一條）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")

import d4t.core.steps  # noqa: E402,F401 — 註冊卡片
from d4t.core.pipeline import (  # noqa: E402
    Recipe, route_for, run_batch, run_batch_steps, run_defect, validate,
)
from d4t.core.pipeline.recipe import (  # noqa: E402
    Edge, RecipeNode, ScoreSpec, hydrate_regions,
)
from d4t.core.pipeline.step import REGISTRY  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
DUAL = REPO / "tests" / "fixtures" / "recipes" / "dual_route_basic.json"


def _single_image_recipe(route_key: str, glv_edges=(("roi", "m1", "cells",
                                                     "roi"),)) -> Recipe:
    """一顆一張的 pipeline（Input 一列 → ROI → GLV），**鍵名由呼叫端給**。"""
    nodes = {
        "load": RecipeNode("load", "load_patch", {"channel_map": "1:single"}),
        "roi": RecipeNode("roi", "roi_reference",
                          {"source": "single",
                           "method": "stripes in the image",
                           "roi_out": "cells"}),
        "m1": RecipeNode("m1", "glv_stats", {"source": "single"}),
    }
    r = Recipe(
        recipe_id="route_is_a_label", routes={route_key: ["load", "roi", "m1"]},
        nodes=nodes,
        score=ScoreSpec(expr="glv_median", threshold=0.0,
                        bins={"below": 0, "above": 1}),
        version=2, author="unit", description="",
        edges=[Edge(*e) for e in (
            ("load", "roi", "single", "source"),
            ("load", "m1", "single", "source")) + tuple(glv_edges)])
    hydrate_regions(r.nodes, r.edges, REGISTRY)
    return r


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    """一個資料夾的單張影像、沒有 KLARF —— 使用者回報的那一種資料。"""
    from make_sample_rsem import generate

    from d4t.core.ingest.dataset import load_folder

    out = generate(str(tmp_path_factory.mktemp("rsem")), n=3, seed=5)
    ds = load_folder(out["images_dir"])
    assert ds.kind == "folder" and len(ds.items) == 3
    return ds


# --------------------------------------------------------------------------- #
# 1. 判準
# --------------------------------------------------------------------------- #
def test_one_route_is_the_route_whatever_the_data_is():
    r = _single_image_recipe("ebi_patch")
    for kind in ("ebi_patch", "rsem", "folder", "anything"):
        assert route_for(r, kind) == "ebi_patch"


def test_several_routes_still_pick_the_one_named_after_the_data():
    r = Recipe.load(str(DUAL))
    assert sorted(r.routes) == ["ebi_patch", "rsem"]
    assert route_for(r, "ebi_patch") == "ebi_patch"
    assert route_for(r, "rsem") == "rsem"
    assert route_for(r, "folder") is None      # 反向：不是安靜地挑一條


def test_no_route_is_no_route():
    r = _single_image_recipe("rsem")
    assert route_for(Recipe(recipe_id="x", routes={}, nodes={},
                            score=r.score), "rsem") is None


# --------------------------------------------------------------------------- #
# 2. 引擎／整批／健檢 同一支
# --------------------------------------------------------------------------- #
def test_the_reported_case_runs_instead_of_failing_every_defect(folder):
    """鍵名是 `rsem`（例：在一份 KLARF 資料上蓋的），資料是一個影像資料夾。"""
    r = _single_image_recipe("rsem")
    for item in folder.items:
        res = run_defect(r, item, folder.kind)
        assert res.ok, res.error
        assert "glv_median" in res.features


def test_a_mismatch_now_says_what_is_really_wrong(folder):
    """一條 patch 的 pipeline 開在單張影像上**還是跑不動** —— 但講的是真正的
    原因（Input 卡的名字表要兩張、這顆只有一張），不是一個使用者看不到的鍵名。
    期 3 會把這句話提前到開跑之前、掛在 Input 卡上。"""
    r = Recipe.load(str(REPO / "recipes" / "ebi-die-to-die.json"))
    assert list(r.routes) == ["ebi_patch"]
    res = run_defect(r, folder.items[0], folder.kind)
    assert not res.ok
    assert "unknown input-type route" not in res.error
    assert "load_patch" in res.error and "1 (single)" in res.error


def test_the_health_check_agrees_with_the_engine(folder):
    r = _single_image_recipe("ebi_patch")
    codes = {i.code for i in validate(r, kind=folder.kind)}
    assert "unknown-route" not in codes
    assert not [i for i in validate(r, kind=folder.kind) if i.level == "error"]


def test_the_lot_layer_runs_the_same_route(folder):
    """整批那一層（`run_batch_steps`）挑 route 用同一支 —— 不然逐顆跑得動、
    整批那幾張 Output 卡卻一張都沒跑（「No output was written」）。"""
    r = _single_image_recipe("ebi_patch")
    rows = run_batch(r, folder, workers=1)
    assert len(rows) == 3 and all(row["ok"] for row in rows), \
        [row.get("error") for row in rows]
    bctx = run_batch_steps(r, folder, rows)
    assert not [w for w in bctx.warnings if "No output was written" in w], \
        bctx.warnings


# --------------------------------------------------------------------------- #
# 3. kind 相依的 lint 問的是資料
# --------------------------------------------------------------------------- #
def test_kind_lints_ask_about_the_data_not_the_route_name():
    """`_center` 在一張大圖上沒有意義（GLV 的 kind lint）。鍵名寫著 `ebi_patch`
    不代表資料是 patch —— 開的是影像資料夾時那條 warning 要出來。"""
    r = _single_image_recipe("ebi_patch",
                             glv_edges=(("roi", "m1", "cells_center", "roi"),))
    on_folder = {i.code for i in validate(r, kind="folder")}
    on_patch = {i.code for i in validate(r, kind="ebi_patch")}
    assert "center-on-big-image" in on_folder
    assert "center-on-big-image" not in on_patch


# --------------------------------------------------------------------------- #
# 4. 反向：多型別 recipe 碰到沒有的那一種
# --------------------------------------------------------------------------- #
def test_a_several_route_recipe_still_says_it_has_nothing_for_this_data(folder):
    r = Recipe.load(str(DUAL))
    got = [i for i in validate(r, kind=folder.kind) if i.code == "unknown-route"]
    assert len(got) == 1 and got[0].level == "error"
    assert "'ebi_patch'" in got[0].detail and "'rsem'" in got[0].detail
    res = run_defect(r, folder.items[0], folder.kind)
    assert not res.ok and "unknown input-type route 'folder'" in res.error

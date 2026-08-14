# ADEPT 範例 recipe 庫的迴歸網 — authored 2026-07-28 (M6-2).
"""``examples/recipes/*.json`` 每一份都必須「載得起來、驗得過、真的跑得動」。

為什麼要有這個檔：範例 recipe 是**新使用者的起點**（Studio 的「範例 recipe」
庫直接列它們）。一份跑不動的範例比沒有範例更糟 —— 第一次用的人會以為
是自己弄壞的。卡片庫改了預設值、改了 reads/writes、改了 feature 名字，
都會在這裡被抓到。

這個檔案**完全不碰 Qt**（它測的是 recipe JSON 與引擎，不是 UI），
所以照一般測試寫法在模組層 import 即可。

測法：
- 靜態：JSON 讀得開、有非空的 ``description``（庫對話框顯示的就是它）、
  ``score.expr`` 非空、每條 route 的節點都存在。
- ``validate(recipe, kind=route)`` 對每一條 route 都必須 **0 個 error**。
- 動態：對應型別的合成資料（ebi + rsem 各一批，模組層產一次）真的跑一遍，
  每一顆 defect 都要 ``ok`` 且分數是有限數。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RECIPES_DIR = REPO / "examples" / "recipes"

sys.path.insert(0, str(REPO / "tools"))
from make_sample import generate as gen_ebi          # noqa: E402
from make_sample_rsem import generate as gen_rsem    # noqa: E402

import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from adept.core.ingest.dataset import load_dataset   # noqa: E402
from adept.core.pipeline import Recipe, run_dataset, validate  # noqa: E402

#: 每批合成資料的 defect 數（跑五份 recipe × 兩種輸入，數量要克制）。
N_DEFECTS = 6

RECIPE_FILES = sorted(RECIPES_DIR.glob("*.json"))
RECIPE_IDS = [p.stem for p in RECIPE_FILES]

#: 這一版庫裡「至少」要有的幾份。
#:
#: F8 第五輪：ROI 收斂成 Profile / Template / GDS 三條路，舊的五份教學範例
#: 全部依賴被拿掉的 ``roi_define`` / ``blob_segment``，使用者決定「等 APP 完成
#: 再給範例」。所以現在只剩示範新 ROI 卡的那一份 —— 這條測試仍然守著
#: 「庫不可以是空的」，只是門檻降到一份。
REQUIRED = {"cross_regions"}


# --------------------------------------------------------------------------- #
# fixtures：兩種輸入各產一批（module scope，只產一次）
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def lots(tmp_path_factory):
    """``{dataset_kind: 已載好的 Dataset}``（ebi_patch 與 rsem 各一批）。"""
    ebi = gen_ebi(str(tmp_path_factory.mktemp("recipes_ebi")),
                  n=N_DEFECTS, seed=7)
    rsem = gen_rsem(str(tmp_path_factory.mktemp("recipes_rsem")),
                    n=N_DEFECTS, seed=11)
    out = {}
    for lot in (ebi, rsem):
        ds = load_dataset(lot["klarf"])
        out[ds.kind] = ds
    assert set(out) == {"ebi_patch", "rsem"}, sorted(out)
    return out


# --------------------------------------------------------------------------- #
# 靜態檢查
# --------------------------------------------------------------------------- #
def test_library_is_not_empty_and_has_the_teaching_set():
    assert RECIPE_FILES, "examples/recipes/ 裡沒有任何 recipe JSON"
    missing = REQUIRED - set(RECIPE_IDS)
    assert not missing, "範例 recipe 庫少了教學用的：%s" % sorted(missing)


def test_readme_exists_and_mentions_every_recipe():
    """README 是非工程師挑起點的地方 —— 新增 recipe 一定要同時寫進表格。"""
    readme = RECIPES_DIR / "README.md"
    assert readme.is_file(), "examples/recipes/README.md 不見了"
    text = readme.read_text(encoding="utf-8")
    for name in RECIPE_IDS:
        assert name in text, "README.md 沒有介紹 %s.json" % name


@pytest.mark.parametrize("path", RECIPE_FILES, ids=RECIPE_IDS)
def test_recipe_loads_and_is_self_consistent(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    recipe = Recipe.load(str(path))

    assert recipe.recipe_id == path.stem, (
        "recipe_id 要和檔名一致（庫對話框顯示的就是 recipe_id）")
    # description 是庫對話框唯一顯示的說明文字 —— 空的等於這份範例沒人看得懂
    assert len(recipe.description.strip()) >= 20, (
        "%s 的 description 太短：非工程師要靠它決定用不用這份" % path.name)
    assert recipe.score.expr.strip(), "score.expr 不可以是空的"
    assert set(recipe.score.bins) >= {"below", "above"}
    assert recipe.routes, "至少要有一條 route"
    for kind, route in recipe.routes.items():
        assert route, "route '%s' 是空的" % kind
        for nid in route:
            assert nid in recipe.nodes, (
                "route '%s' 引用了不存在的節點 '%s'" % (kind, nid))
    # 每個定義出來的節點都要真的被某條 route 用到（沒人用 = 誤導讀者）
    used = {nid for route in recipe.routes.values() for nid in route}
    assert used == set(recipe.nodes), (
        "有節點沒被任何 route 使用：%s" % sorted(set(recipe.nodes) - used))
    # JSON 原檔的 routes 順序 = 執行順序，別被 dict 化吃掉
    assert list(raw["routes"]) == list(recipe.routes)


@pytest.mark.parametrize("path", RECIPE_FILES, ids=RECIPE_IDS)
def test_recipe_validates_with_zero_errors_on_every_route(path):
    recipe = Recipe.load(str(path))
    for kind in recipe.routes:
        issues = validate(recipe, kind=kind)
        errors = [i for i in issues if i.level == "error"]
        assert not errors, "%s route '%s' 有 %d 個 error：%s" % (
            path.name, kind, len(errors),
            [(i.code, i.node_id, i.detail) for i in errors])


# --------------------------------------------------------------------------- #
# 動態檢查：真的跑一遍
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", RECIPE_FILES, ids=RECIPE_IDS)
def test_recipe_actually_runs_and_scores_every_defect(path, lots):
    """每條 route 都要在對應的合成資料上跑完，且**每一顆**都有有限的分數。"""
    recipe = Recipe.load(str(path))
    ran = 0
    for kind in recipe.routes:
        ds = lots.get(kind)
        if ds is None:                       # 未來若出現第三種輸入型別
            pytest.skip("沒有 '%s' 型別的合成資料可以測" % kind)
        results = run_dataset(recipe, ds)
        assert len(results) == N_DEFECTS
        failed = [(r.defect_id, r.error) for r in results if not r.ok]
        assert not failed, "%s route '%s' 有 defect 跑失敗：%s" % (
            path.name, kind, failed)
        for r in results:
            assert r.score is not None, "%s: defect %s 沒有分數" % (path.name,
                                                                   r.defect_id)
            assert math.isfinite(float(r.score)), (
                "%s: defect %s 的分數不是有限數（%r）" % (path.name, r.defect_id,
                                                        r.score))
            assert r.bin in (0, 1), "%s: defect %s 的 bin 是 %r" % (
                path.name, r.defect_id, r.bin)
            assert "score" in r.features
        # 分數不能整批一模一樣 —— 那代表這份 recipe 其實沒有在分辨任何東西
        scores = {round(float(r.score), 9) for r in results}
        assert len(scores) > 1, (
            "%s route '%s'：%d 顆 defect 全部同分（%s），這份範例沒有鑑別力"
            % (path.name, kind, N_DEFECTS, scores))
        ran += 1
    assert ran, "%s 一條 route 都沒跑到" % path.name


def test_every_route_kind_is_a_known_dataset_kind():
    """route 名稱必須對得上 ingest 層真的會產出的 dataset kind。"""
    known = {"ebi_patch", "rsem", "folder"}
    for path in RECIPE_FILES:
        recipe = Recipe.load(str(path))
        unknown = set(recipe.routes) - known
        assert not unknown, "%s 有不認識的 route：%s" % (path.name, sorted(unknown))

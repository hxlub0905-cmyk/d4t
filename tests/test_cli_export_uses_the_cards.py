# F122 期 4：`d4t export` 照那一輪 recipe 上的 Output 卡寫。
"""**CLI 寫出來的東西跟 Studio 寫的是同一份。**

以前 `d4t export` 只有一條路：`--csv` / `--excel` / `--klarf-out` 各自直接叫寫入器，
卡上的資料夾、勾選、圖、KLARF 模式一個都不算數 —— 同一份 recipe，Studio 按
「Write outputs」寫一份、CLI 寫另一份。使用者同意的建議：「CLI 的 export 也照
卡片寫」。

現在沒有給一次性的出口時，`export` 跑那一輪存下來的 recipe 上的 Output 卡（同一支
`run_batch_steps`）；`--dry-run` 列每一張卡會寫到哪。三個一次性的旗標照舊（不看卡片）。
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.__main__ import main  # noqa: E402
from d4t.core.pipeline.recipe import Recipe, RecipeNode, ScoreSpec  # noqa: E402
from d4t.core.store import RunStore  # noqa: E402


def _recipe(**outputs):
    nodes = {"load": RecipeNode("load", "load_patch", {}),
             "glv": RecipeNode("glv", "glv_stats",
                               {"source": "test", "metrics": "glv_max"})}
    for nid, (step, params) in outputs.items():
        nodes[nid] = RecipeNode(nid, step, params)
    return Recipe(recipe_id="exp", routes={"ebi_patch": list(nodes)},
                  nodes=nodes,
                  score=ScoreSpec(expr="glv_max", threshold=1.0,
                                  bins={"below": 0, "above": 1}))


@pytest.fixture
def ran(tmp_path):
    """跑一次、存進批次歷史，然後把 `run` 寫出來的東西刪掉 —— `export` 要自己寫。"""
    from make_sample import generate

    lot = generate(str(tmp_path / "lot"), n=3, seed=4)
    recipe_path = tmp_path / "r.json"
    _recipe(rep=("output_report", {"contents": "table,recipe"}),
            kl=("output_klarf", {"mode": "annotate"})).save(str(recipe_path))
    db = tmp_path / "runs.db"
    assert main(["run", str(recipe_path), lot["klarf"], "--workers", "1",
                 "--db", str(db)]) == 0
    here = Path(lot["klarf"]).parent
    stem, ext = os.path.splitext(lot["klarf"])
    shutil.rmtree(here / "d4t_report")
    os.remove(stem + "_adc" + ext)
    with RunStore(str(db)) as store:
        run_id = store.list_runs()[0]["run_id"]
    return {"db": str(db), "run_id": run_id, "here": here,
            "klarf_out": stem + "_adc" + ext, "klarf": lot["klarf"]}


def test_export_writes_what_the_cards_say(ran):
    assert main(["export", ran["run_id"], "--db", ran["db"]]) == 0
    assert (ran["here"] / "d4t_report" / "defects.csv").exists()
    assert (ran["here"] / "d4t_report" / "recipe.json").exists()
    assert os.path.exists(ran["klarf_out"])


def test_a_dry_run_says_where_each_card_would_write_and_writes_nothing(
        ran, capsys):
    assert main(["export", ran["run_id"], "--db", ran["db"], "--dry-run"]) == 0
    said = capsys.readouterr().out
    assert "Write report" in said and "defects.csv" in said
    assert "Write KLARF" in said and ran["klarf_out"] in said
    assert not (ran["here"] / "d4t_report").exists()
    assert not os.path.exists(ran["klarf_out"])


def test_a_one_off_flag_does_not_run_the_cards(ran, tmp_path):
    """**反向**：`--csv` 是一次性的出口 —— 只寫那一個檔，卡片不跑。"""
    out = tmp_path / "one_off.csv"
    assert main(["export", ran["run_id"], "--db", ran["db"],
                 "--csv", str(out)]) == 0
    assert out.exists()
    assert not (ran["here"] / "d4t_report").exists()


def test_a_recipe_without_output_cards_says_how_to_write_anyway(tmp_path, capsys):
    from make_sample import generate

    lot = generate(str(tmp_path / "lot"), n=2, seed=4)
    recipe_path = tmp_path / "r.json"
    _recipe().save(str(recipe_path))
    db = tmp_path / "runs.db"
    assert main(["run", str(recipe_path), lot["klarf"], "--workers", "1",
                 "--db", str(db)]) == 0
    with RunStore(str(db)) as store:
        run_id = store.list_runs()[0]["run_id"]
    assert main(["export", run_id, "--db", str(db)]) == 1
    assert "--csv" in capsys.readouterr().err

# F122 期 2：Output 卡安靜做錯／擋錯的那幾件（core 那一半）。
"""**「Write to」空著有預設、沒有 KLARF 就跳過並講、兩張卡不准寫同一個檔。**

使用者（2026-09-29）：「先修會安靜做錯的，接著按照你的建議修」，而建議是：

* 「Write to」空著 → 寫到資料旁邊的預設位置（以前是一條 error，**擋住試跑** ——
  試跑根本不寫）；
* Write KLARF 開在沒有 KLARF 的資料上 → 開資料時在卡上講、寫的時候**跳過並講**，
  其他輸出照寫（以前開跑前不講，寫的時候才失敗）；
* 兩張卡指到同一個地方、寫同名的檔 → error（以前後寫的安靜地蓋掉前一張）；
* `Write comparison` 的左右兩張圖是**名字**，打錯了 → warning（以前那一格安靜地空著）；
* CLI 跑 0 顆 → 停下來（以前照樣寫，而相對路徑落在「現在站在哪」）。

畫面那一半（寫之前比對 recipe、試跑子集要講）在 `test_ui_write_only_on_run_all.py`。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest.dataset import DataProfile, load_dataset  # noqa: E402
from d4t.core.pipeline import run_batch, run_batch_steps  # noqa: E402
from d4t.core.pipeline.batch import (  # noqa: E402
    decision_signature, measurement_signature,
)
from d4t.core.pipeline.recipe import Recipe, RecipeNode, ScoreSpec  # noqa: E402
from d4t.core.pipeline.recipe_validate import validate  # noqa: E402
from d4t.core.pipeline.step import get_step  # noqa: E402

KIND = "ebi_patch"


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate

    return generate(str(tmp_path_factory.mktemp("lot")), n=3, seed=5)


def _recipe(**outputs):
    nodes = {"load": RecipeNode("load", "load_patch", {}),
             "glv": RecipeNode("glv", "glv_stats",
                               {"source": "test", "metrics": "glv_max"})}
    for nid, (step, params) in outputs.items():
        nodes[nid] = RecipeNode(nid, step, params)
    return Recipe(recipe_id="out", routes={KIND: list(nodes)}, nodes=nodes,
                  score=ScoreSpec(expr="glv_max", threshold=1.0,
                                  bins={"below": 0, "above": 1}))


def _codes(recipe, **kw):
    return {i.code: i for i in validate(recipe, KIND, **kw)}


# --------------------------------------------------------------------------- #
# 1. 「Write to」空著＝資料旁邊
# --------------------------------------------------------------------------- #
def test_an_empty_folder_writes_next_to_the_data(lot):
    ds = load_dataset(lot["klarf"])
    r = _recipe(rep=("output_report", {"folder": "", "contents": "table"}))
    assert "not-configured" not in _codes(r)
    bctx = run_batch_steps(r, ds, run_batch(r, ds, workers=1))
    assert not bctx.errors, bctx.errors
    here = Path(lot["klarf"]).parent / "d4t_report" / "defects.csv"
    assert here.exists()


def test_every_folder_card_has_its_own_default():
    """兩張卡都空著時不寫進同一個資料夾（下面那條 collision 的前提）。"""
    defaults = [get_step(k).DEFAULT for k in
                ("output_report", "output_char", "output_uniformity")]
    assert all(defaults) and len(set(defaults)) == 3, defaults


def test_write_klarf_defaults_beside_the_original(lot):
    card = get_step("output_klarf")
    src = lot["klarf"]
    stem, ext = os.path.splitext(src)
    assert card.default_path("annotate", src) == stem + "_adc" + ext
    assert card.default_path("topn", src) == stem + "_top" + ext
    assert card.default_path("inplace", src) == src      # in place 就是原檔
    ds = load_dataset(src)
    r = _recipe(kl=("output_klarf", {"path": "", "mode": "annotate"}))
    bctx = run_batch_steps(r, ds, run_batch(r, ds, workers=1))
    assert not bctx.errors, bctx.errors
    assert os.path.exists(stem + "_adc" + ext)
    assert Path(src).read_bytes() != Path(stem + "_adc" + ext).read_bytes()


# --------------------------------------------------------------------------- #
# 2. 沒有 KLARF：開資料時講、寫的時候跳過
# --------------------------------------------------------------------------- #
def _profile(has_klarf):
    return DataProfile(kind=KIND if has_klarf else "folder", n_items=3,
                       images_min=2, images_max=2, image_names=("test", "ref"),
                       has_klarf=has_klarf, columns=())


def test_write_klarf_on_data_without_a_klarf_is_said_on_the_card():
    r = _recipe(kl=("output_klarf", {}))
    got = _codes(r, data=_profile(False))
    assert got["klarf-out-no-klarf"].level == "warning"
    assert got["klarf-out-no-klarf"].node_id == "kl"
    assert "klarf-out-no-klarf" not in _codes(r, data=_profile(True))


# --------------------------------------------------------------------------- #
# 3. 兩張卡寫同一個檔
# --------------------------------------------------------------------------- #
def test_two_cards_writing_the_same_file_is_an_error():
    r = _recipe(a=("output_report", {"folder": "x", "contents": "report"}),
                b=("output_char", {"folder": "x"}))
    got = _codes(r)
    assert got["output-collision"].level == "error"
    assert "report.html" in got["output-collision"].detail
    # 兩張報表卡都空著 → 同一個預設資料夾、同名的檔
    r2 = _recipe(a=("output_report", {"contents": "table"}),
                 b=("output_report", {"contents": "table"}))
    assert "output-collision" in _codes(r2)


def test_sharing_a_folder_without_sharing_a_file_is_fine():
    """**反向**：出貨的均勻度 recipe 刻意讓兩張卡共用一個資料夾，而它們寫的
    檔名不重疊 —— 比的是檔名，不是資料夾。"""
    r = _recipe(a=("output_report", {"folder": "x", "contents": "table"}),
                b=("output_uniformity", {"folder": "x"}))
    assert "output-collision" not in _codes(r)
    shipped = Recipe.load(str(REPO / "recipes" / "one-image-uniformity.json"))
    assert not [i for i in validate(shipped, "folder")
                if i.code == "output-collision"]


# --------------------------------------------------------------------------- #
# 4. 左右兩張圖是名字
# --------------------------------------------------------------------------- #
def test_a_mistyped_picture_stream_is_a_warning():
    r = _recipe(c=("output_char", {"folder": "x", "main_stream": "tset",
                                   "pair_stream": ""}))
    got = _codes(r)
    assert got["stale-stream-ref"].level == "warning"
    assert "tset" in got["stale-stream-ref"].detail
    ok = _recipe(c=("output_char", {"folder": "x", "main_stream": "test",
                                    "pair_stream": ""}))
    assert "stale-stream-ref" not in _codes(ok)


# --------------------------------------------------------------------------- #
# 5. 判定的簽章：Write outputs 拿它對「結果還是不是這份 recipe 的」
# --------------------------------------------------------------------------- #
def test_the_decision_signature_moves_with_the_decision_only():
    a = _recipe(rep=("output_report", {"folder": "x"}))
    b = _recipe(rep=("output_report", {"folder": "y"}))       # 只改 Output 卡
    c = _recipe(rep=("output_report", {"folder": "x"}))
    c.score = ScoreSpec(expr="glv_max", threshold=5.0,
                        bins={"below": 0, "above": 1})
    assert decision_signature(a) == decision_signature(b)
    assert decision_signature(a) != decision_signature(c)
    assert measurement_signature(a) == measurement_signature(c)


# --------------------------------------------------------------------------- #
# 6. CLI：0 顆就停
# --------------------------------------------------------------------------- #
def test_the_cli_stops_on_data_with_no_defects(tmp_path, monkeypatch):
    """以前照樣寫 —— 而沒有一顆影像可以當錨點，相對的「Write to」落在 cwd。"""
    import numpy as np

    from d4t.__main__ import main
    from d4t.core.ingest import imageio

    data = tmp_path / "data"
    (data / "day1").mkdir(parents=True)
    imageio.save_gray(str(data / "day1" / "a.png"),
                      np.full((8, 8), 9, np.uint8))
    recipe = tmp_path / "r.json"
    _recipe(rep=("output_report", {"folder": "rel_out",
                                   "contents": "table,recipe"})).save(
        str(recipe))
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert main(["run", str(recipe), str(data)]) == 2
    assert not (cwd / "rel_out").exists()

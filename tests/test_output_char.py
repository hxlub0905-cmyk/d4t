# F33：characterization 的點對點報表 — authored 2026-08-25.
"""`output_char` —— **一顆一列，兩張圖跟數字在同一列上**。

這張卡跟 `output_bundle` 的差別只有一個，而那個差別就是它存在的理由：
使用者原話是「我可以一一對應這樣子」。點一列換一張圖的版面答不出那句話 ——
任何一個時刻畫面上只有一顆。

鎖在這裡的四件事：

1. **圖在列上**，而且路徑是**相對的**（整個資料夾寄給別人的時候連結還是通的）；
2. **配不到的那一顆那一格留白** —— 不是破圖：留白正是它要講的話；
3. **超過上限就講出來、但版面不換**（使用者要知道他拿到的是哪一種報表）；
4. 判定那一欄講的是**葉子的名字**（它不在 rows 裡，要反查一次）。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.export import html as export_html                   # noqa: E402
from d4t.core.ingest.dataset import load_dataset                  # noqa: E402
from d4t.core.pipeline import (                                   # noqa: E402
    run_batch, run_batch_steps,
)
from d4t.core.pipeline.recipe import (                            # noqa: E402
    Recipe, RecipeNode, ScoreSpec,
)
from d4t.core.pipeline.step import REGISTRY                       # noqa: E402

KIND = "ebi_patch"


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("char")), n=6, seed=5)


@pytest.fixture(scope="module")
def dataset(lot):
    return load_dataset(lot["klarf"])


def recipe_for(folder, **over):
    params = {"folder": str(folder)}
    params.update(over)
    return Recipe(
        recipe_id="char_demo", routes={KIND: ["load", "glv", "out"]},
        nodes={
            "load": RecipeNode("load", "load_patch", {}),
            "glv": RecipeNode("glv", "glv_stats",
                              {"source": "test", "metrics": "glv_max"}),
            "out": RecipeNode("out", "output_char", params),
        },
        score=ScoreSpec(expr="glv_max", threshold=1.0,
                        bins={"below": 0, "above": 1}))


def run(dataset, folder, **over):
    r = recipe_for(folder, **over)
    rows = run_batch(r, dataset, workers=1)
    bctx = run_batch_steps(r, dataset, rows)
    assert not bctx.errors, bctx.errors
    return bctx, rows


def _report(folder):
    return (Path(folder) / "report.html").read_text(encoding="utf-8")


def _rows_of(html):
    """報表表格裡的每一個 ``<tr>``（含表頭那一列）。"""
    return re.findall(r"<tr[^>]*>.*?</tr>", html, flags=re.S)


# --------------------------------------------------------------------------- #
# 1. 資料夾裡有什麼
# --------------------------------------------------------------------------- #
def test_the_folder_has_the_report_the_numbers_and_the_recipe(dataset,
                                                              tmp_path):
    """**沒有 recipe.json，半年後沒人重現得出這份報表** —— 一疊數字沒有配方，
    等於一句「我們那時候量到這樣」。"""
    out = tmp_path / "char"
    bctx, rows = run(dataset, out, columns="glv_max")
    assert (out / "report.html").is_file()
    assert (out / "defects.csv").is_file()
    assert (out / "recipe.json").is_file()
    assert (out / "images").is_dir()
    assert str(out) in bctx.outputs

    import json
    saved = json.loads((out / "recipe.json").read_text(encoding="utf-8"))
    assert saved["recipe_id"] == "char_demo"


def test_every_defect_is_a_row_with_its_picture_on_it(dataset, tmp_path):
    """一顆一列，而圖**在那一列上** —— 那是這張卡跟 bundle 的全部差別。"""
    out = tmp_path / "char"
    _bctx, rows = run(dataset, out, columns="glv_max")
    html = _report(out)
    body = _rows_of(html)
    assert len(body) == len(rows) + 1            # 加表頭那一列
    for tr in body[1:]:
        assert "<img" in tr, tr
    # 而不是 bundle 那種「整份只有一個 <img>、點一列換圖」的版面
    assert "id='shot'" not in html and "data-img" not in html


# --------------------------------------------------------------------------- #
# 2. 相對路徑 —— 「把資料夾寄給別人」的那一刻會破的東西
# --------------------------------------------------------------------------- #
def test_every_img_src_is_relative_and_points_at_a_real_file(dataset, tmp_path):
    """⚠ 先問「它是相對的嗎」再問「它存在嗎」。

    `Path(out) / "/abs/x.jpg"` 在 pathlib 底下會直接變成那個絕對路徑，
    所以只檢查 `is_file()` 的話，一個絕對路徑也會過 —— 而那正是把資料夾
    寄給別人的那一刻會破的東西（`test_output_bundle.py` 那個洞）。
    """
    out = tmp_path / "char"
    run(dataset, out, columns="glv_max")
    srcs = re.findall(r"<img[^>]+src='([^']+)'", _report(out))
    assert srcs
    for rel in srcs:
        assert not os.path.isabs(rel) and ":" not in rel, rel
        assert not rel.startswith(("/", "\\")), rel
        assert (out / rel).is_file(), rel


def test_the_pictures_are_beside_the_report_not_inside_it(dataset, tmp_path):
    out = tmp_path / "char"
    run(dataset, out, columns="glv_max")
    html = _report(out)
    assert "base64" not in html
    assert list((out / "images").glob("*.jpg"))


def test_two_pictures_per_defect_get_distinct_names(dataset, tmp_path):
    """一顆兩張圖 → 檔名要分得開（不然第二張會蓋掉第一張）。"""
    out = tmp_path / "char"
    run(dataset, out, main_stream="test", pair_stream="test",
        columns="glv_max")
    names = sorted(p.name for p in (out / "images").glob("*.jpg"))
    assert any(n.endswith("_main.jpg") for n in names)
    assert any(n.endswith("_pair.jpg") for n in names)
    # 每一顆兩張，沒有互相蓋掉
    assert len(names) == len(set(names)) == 2 * len(
        [n for n in names if n.endswith("_main.jpg")])


# --------------------------------------------------------------------------- #
# 3. 配不到的那一顆：**留白，不是破圖**
# --------------------------------------------------------------------------- #
def test_a_defect_with_no_second_picture_gets_an_empty_cell(dataset, tmp_path):
    """沒有第二張圖的那一格**完全不產生 `<img>`**。

    空的 `src` 在瀏覽器裡是一個破圖示，而那一格要講的話是「這一顆在另一份
    資料裡不存在」—— characterization 的結論之一，不是一個載入失敗。
    """
    out = tmp_path / "char"
    # `pair_stream` 指著一條沒有人產出的流 → 右邊那一欄整欄都是空的
    run(dataset, out, pair_stream="nothing_makes_this", columns="glv_max")
    html = _report(out)
    for tr in _rows_of(html)[1:]:
        assert tr.count("<img") == 1, tr        # 只有左邊那一張
        assert "src=''" not in tr and 'src=""' not in tr
    assert "&mdash;" in html                    # 那一格畫的是一個破折號


def test_the_empty_cell_is_the_same_shape_when_it_is_built_by_hand():
    """直接餵 `build_char_report`：`pair=None` 那一列只有一個 `<img>`。"""
    rows = [{"defect_id": "a", "ok": True, "score": 1.0, "bin": 1,
             "features": {"ncc_score": 0.97}},
            {"defect_id": "b", "ok": True, "score": 0.0, "bin": 3,
             "features": {}}]
    thumbs = {"a": {"main": "images/a_main.jpg", "pair": "images/a_pair.jpg"},
              "b": {"main": "images/b_main.jpg", "pair": None}}
    html = export_html.build_char_report(rows, "t", ["ncc_score"], thumbs)
    body = _rows_of(html)
    assert body[1].count("<img") == 2
    assert body[2].count("<img") == 1
    assert "src=''" not in html


# --------------------------------------------------------------------------- #
# 4. 顆數上限：**講出來，不要自動換版面**
# --------------------------------------------------------------------------- #
def test_over_the_cap_it_says_so_and_names_the_other_card(dataset, tmp_path):
    out = tmp_path / "char"
    bctx, rows = run(dataset, out, limit=2, columns="glv_max")
    said = " ".join(bctx.warnings)
    assert "Write report folder" in said
    assert str(len(rows)) in said and "2" in said


def test_over_the_cap_the_layout_does_not_change(dataset, tmp_path):
    """使用者要知道他拿到的是哪一種報表 —— 版面自動換掉的話他不會知道。"""
    out = tmp_path / "char"
    _bctx, rows = run(dataset, out, limit=2, columns="glv_max")
    body = _rows_of(_report(out))
    assert len(body) == len(rows) + 1            # 每一顆仍然是一列
    with_pic = [tr for tr in body[1:] if "<img" in tr]
    assert len(with_pic) == 2                    # 只有前兩列有圖
    assert "data-img" not in _report(out)        # 沒有偷偷變成 bundle 的版面


# --------------------------------------------------------------------------- #
# 5. 判定那一欄：葉子的名字**不在 rows 裡**
# --------------------------------------------------------------------------- #
def _tree_recipe_for(folder, **over):
    params = {"folder": str(folder)}
    params.update(over)
    raw = recipe_for(folder, **over).to_json_dict()
    raw["nodes"]["out"]["params"] = params
    raw["score"] = {"expr": "", "threshold": 1.0,
                    "bins": {"below": 0, "above": 1}}
    raw["decide"] = {"let": [],
                     "tree": {"when": "glv_max > 200",
                              "yes": {"bin": 2, "label": "bright"},
                              "no": {"bin": 1, "label": "plain"}}}
    return Recipe.from_json_dict(raw)


def test_the_verdict_column_says_the_leaf_name(dataset, tmp_path):
    out = tmp_path / "char"
    r = _tree_recipe_for(out, columns="glv_max", rank_by="glv_max")
    rows = run_batch(r, dataset, workers=1)
    bctx = run_batch_steps(r, dataset, rows)
    assert not bctx.errors, bctx.errors

    from d4t.core.pipeline import decide_tree
    names = {e["name"] for e in decide_tree.verdict_rows(r.decide, rows)}
    html = _report(out)
    assert names and any(n in html for n in names)
    # 顏色的小方塊跟畫面上是同一個色（`decide_tree.LEAF_PALETTE`）
    assert "class='chip'" in html


def test_a_defect_that_failed_still_gets_an_honest_row():
    """跑不起來的那一顆**留在表上**，而那一格講的是它為什麼沒有結果。"""
    rows = [{"defect_id": "boom", "ok": False, "error": "glv: no image",
             "score": None, "bin": None, "features": {}}]
    html = export_html.build_char_report(rows, "t", [], {"boom": {}})
    assert "boom" in html and "no image" in html
    assert "class='bad'" in html


# --------------------------------------------------------------------------- #
# 6. 參數
# --------------------------------------------------------------------------- #
def test_ncc_score_is_a_column_by_default():
    """配對是這條 recipe 唯一的風險，而 `ncc_score` 是唯一的擋板 ——
    它要**在表格裡**，不是收在進階裡。"""
    spec = next(p for p in REGISTRY["output_char"].params
                if p.name == "columns")
    assert "ncc_score" in str(spec.default)


def test_the_two_folder_cards_agree_word_for_word():
    """同一句話在兩張卡上長出兩種意思，是這個 repo 最常踩的形狀。"""
    char = {p.name: p for p in REGISTRY["output_char"].params}
    bundle = {p.name: p for p in REGISTRY["output_bundle"].params}
    for name in ("rank_by", "jpeg_quality"):
        a, b = char[name], bundle[name]
        assert (a.type, a.default, a.label) == (b.type, b.default, b.label)
    assert REGISTRY["output_char"].RECIPE_NAME == \
        REGISTRY["output_bundle"].RECIPE_NAME
    assert REGISTRY["output_char"].IMAGE_DIR == \
        REGISTRY["output_bundle"].IMAGE_DIR


def test_it_is_an_end_point_like_every_other_output_card():
    card = REGISTRY["output_char"]
    assert card.is_batch
    assert card.resolve_reads({}) == []
    assert card.resolve_writes({}) == []
    assert card.resolve_features({}) == []
    assert "Write to" in " ".join(card.configuration_issues({}))


def test_pointing_it_at_a_file_says_so(dataset, tmp_path):
    target = tmp_path / "not_a_folder.txt"
    target.write_text("x", encoding="utf-8")
    r = recipe_for(target, columns="glv_max")
    rows = run_batch(r, dataset, workers=1)
    bctx = run_batch_steps(r, dataset, rows)
    assert bctx.errors and "folder" in str(bctx.errors).lower()

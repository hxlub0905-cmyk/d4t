# F121 期 3：Input 卡看資料 —— 對不上的話，開跑之前、在那張卡上講一次。
"""**使用者回報的那一個，最後一段。**

2026-09-24：一條 EBI（Patch，test/ref）的 pipeline 開在一個沒有 KLARF 的 RSEM
影像資料夾上，每一顆都報錯。期 1 之後那句話講的是真正的原因（「名字表要 2 張、
這顆只有 1 張」），但**還是每一顆講一次**，而且要跑下去才知道。

那句話的每一個字在開資料那一刻就知道了：一顆幾張、有沒有 KLARF、有哪幾欄
（`ingest.dataset.DataProfile`）。這一份鎖：

1. 那份「資料長什麼樣」算得對（一顆幾張、第幾張叫什麼、KLARF 與欄位）；
2. Input 卡的三類發現（`LoadPatchStep.data_issues`）—— 張數不夠是 error、
   名字比張數少是 info、要 KLARF 欄位而資料沒有是 error；
3. 它們掛在 **Input 卡**上（`node_id`），只在給了資料時出現（**反向**：沒開資料
   的健檢一句都不多講）；
4. 三份出貨 recipe × 三種資料的那張表 —— 就是 F121 開案時實測的那一張；
5. CLI 開跑前擋下（不是跑完每一顆都錯）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: E402,F401 — 註冊卡片
from d4t.core.ingest.dataset import (  # noqa: E402
    Dataset, DefectItem, ImageRef, data_profile, load_dataset, load_folder,
)
from d4t.core.pipeline import Recipe, validate  # noqa: E402
from d4t.core.pipeline.step import get_step  # noqa: E402

RECIPES = REPO / "recipes"


@pytest.fixture(scope="module")
def lots(tmp_path_factory):
    from make_sample import generate as patch_lot
    from make_sample_rsem import generate as rsem_lot

    root = tmp_path_factory.mktemp("lots")
    r = rsem_lot(str(root / "rsem"), n=3, seed=5)
    p = patch_lot(str(root / "patch"), n=3, seed=5)
    return {
        "folder": load_folder(r["images_dir"]),     # 使用者手上那一種
        "rsem": load_dataset(r["klarf"]),
        "ebi_patch": load_dataset(p["klarf"], p["tiff"]),
    }


def _input_issues(recipe, data):
    return [i for i in validate(recipe, data=data) if i.code.startswith("input-")]


# --------------------------------------------------------------------------- #
# 1. 這批資料長什麼樣
# --------------------------------------------------------------------------- #
def test_the_profile_says_how_many_images_and_whether_there_is_a_klarf(lots):
    folder, rsem, patch = (data_profile(lots[k])
                           for k in ("folder", "rsem", "ebi_patch"))
    assert (folder.images_min, folder.images_max) == (1, 1)
    assert folder.image_names == ("single",)
    assert folder.has_klarf is False and folder.columns == ()
    assert rsem.image_names == ("single",) and rsem.has_klarf is True
    assert {"XREL", "YREL", "CLASSNUMBER"} <= set(rsem.columns)
    assert patch.image_names == ("test", "ref")
    assert (patch.images_min, patch.images_max) == (2, 2)
    assert data_profile(None) is None


def test_a_lot_where_some_defects_have_fewer_images_says_the_range(tmp_path):
    ref = ImageRef(str(tmp_path / "x.png"), None, "single")
    ds = Dataset(kind="folder", klarf=None, items=[
        DefectItem("a", None, None, None, images={"single": ref}),
        DefectItem("b", None, None, None,
                   images={"test": ref, "ref": ref})])
    prof = data_profile(ds)
    assert (prof.images_min, prof.images_max) == (1, 2)
    got = get_step("load_patch").data_issues(
        {"channel_map": "1:test, 2:ref"}, prof)
    assert [c for c, *_ in got] == ["input-too-few-images"]
    assert "1 to 2 images" in got[0][3]


# --------------------------------------------------------------------------- #
# 2. Input 卡的三類發現
# --------------------------------------------------------------------------- #
def test_names_that_ask_for_more_images_than_the_data_has_are_an_error(lots):
    card = get_step("load_patch")
    got = card.data_issues(card.validate_params({}), data_profile(lots["folder"]))
    assert [(c, lv) for c, lv, _t, _d in got] == [("input-too-few-images",
                                                  "error")]
    detail = got[0][3]
    assert "1 image per defect (single)" in detail
    assert "asks for 2 (test, ref)" in detail


def test_fewer_names_than_images_is_only_an_info(lots):
    card = get_step("load_patch")
    got = card.data_issues({"channel_map": "1:single"},
                           data_profile(lots["ebi_patch"]))
    assert [(c, lv) for c, lv, _t, _d in got] == [("input-unnamed-images",
                                                  "info")]
    assert "(ref)" in got[0][3], "講得出沒載入的是哪一張"


def test_klarf_columns_on_data_without_a_klarf_are_an_error(lots):
    card = get_step("load_patch")
    prof = data_profile(lots["folder"])
    carry = card.data_issues({"channel_map": "1:single",
                              "carry": "XREL, YREL"}, prof)
    assert [c for c, *_ in carry] == ["input-needs-klarf"]
    assert "XREL, YREL" in carry[0][3]
    only = card.data_issues({"channel_map": "1:single",
                             "only_column": "CLASSNUMBER",
                             "only_codes": "1"}, prof)
    # 以前這一種講的是「篩選條件一顆都沒對上」—— 真正的原因（沒有 KLARF）沒講。
    assert [c for c, *_ in only] == ["input-needs-klarf"]
    assert "Only run this column" in only[0][2]


def test_a_column_the_klarf_does_not_have_is_an_error(lots):
    card = get_step("load_patch")
    got = card.data_issues({"channel_map": "1:single", "carry": "NOPE"},
                           data_profile(lots["rsem"]))
    assert [c for c, *_ in got] == ["input-no-such-column"]
    assert "NOPE" in got[0][2] and "XREL" in got[0][3], "講得出它有哪幾欄"


def test_a_card_that_fits_its_data_says_nothing(lots):
    card = get_step("load_patch")
    assert card.data_issues(card.validate_params({}),
                            data_profile(lots["ebi_patch"])) == []
    assert card.data_issues({"channel_map": "1:single", "carry": "XREL"},
                            data_profile(lots["rsem"])) == []


def test_fitting_the_names_keeps_every_wire_it_can(lots):
    """「照這份資料填」（`fit_channel_map`）：資料有的位置留原名（線不動）、
    沒有的拿掉、多出來的補 ingest 的名字。"""
    from d4t.core.steps.load import channel_map_for, fit_channel_map

    one = lots["folder"].items[0]           # 一顆一張（single）
    two = lots["ebi_patch"].items[0]        # 一顆兩張（test, ref）
    assert fit_channel_map("1:test, 2:ref", one) == "1:test"
    assert fit_channel_map("1:se1, 2:bse", two) == "1:se1, 2:bse"
    assert fit_channel_map("1:single", two) == "1:single, 2:ref"
    assert fit_channel_map("", one) == channel_map_for(one) == "1:single"
    assert fit_channel_map("not a map", two) == "1:test, 2:ref"


# --------------------------------------------------------------------------- #
# 3. 掛在 Input 卡上，只在給了資料時出現
# --------------------------------------------------------------------------- #
def test_the_findings_sit_on_the_input_card(lots):
    r = Recipe.load(str(RECIPES / "ebi-die-to-die.json"))
    got = _input_issues(r, data_profile(lots["folder"]))
    assert {i.node_id for i in got} == {"load"}
    assert all(i.level == "error" for i in got)


def test_without_data_the_health_check_says_nothing_more(lots):
    """**反向**：沒開資料時沒有東西可以對 —— 一句都不准多。"""
    for name in ("ebi-die-to-die", "rsem-worst-box", "one-image-uniformity"):
        r = Recipe.load(str(RECIPES / ("%s.json" % name)))
        assert not [i for i in validate(r) if i.code.startswith("input-")]


# --------------------------------------------------------------------------- #
# 4. 出貨 recipe × 資料：F121 開案時實測的那張表
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("recipe,kind,expected", [
    ("ebi-die-to-die", "folder", {"input-too-few-images", "input-needs-klarf"}),
    ("ebi-die-to-die", "rsem", {"input-too-few-images"}),
    ("ebi-die-to-die", "ebi_patch", set()),
    ("rsem-worst-box", "folder", {"input-needs-klarf"}),
    ("rsem-worst-box", "rsem", set()),
    ("rsem-worst-box", "ebi_patch", {"input-unnamed-images"}),
    ("one-image-uniformity", "folder", set()),
    ("one-image-uniformity", "rsem", set()),
    ("one-image-uniformity", "ebi_patch", {"input-unnamed-images"}),
])
def test_the_shipped_recipes_against_each_kind_of_data(lots, recipe, kind,
                                                       expected):
    r = Recipe.load(str(RECIPES / ("%s.json" % recipe)))
    got = {i.code for i in _input_issues(r, data_profile(lots[kind]))}
    assert got == expected


# --------------------------------------------------------------------------- #
# 5. CLI 開跑前擋下
# --------------------------------------------------------------------------- #
def test_the_cli_stops_before_running_instead_of_failing_every_defect(lots):
    folder = Path(lots["folder"].items[0].images["single"].path).parent
    out = subprocess.run(
        [sys.executable, "-m", "d4t", "run",
         str(RECIPES / "ebi-die-to-die.json"), str(folder)],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
        timeout=300)
    said = out.stdout + out.stderr
    assert out.returncode == 1, said
    assert "input-too-few-images" in said
    assert "執行" not in said.split("Recipe 健檢")[-1], "不該開跑"

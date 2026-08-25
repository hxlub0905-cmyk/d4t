# F15：兩筆資料逐顆對起來 — authored 2026-08-19.
"""EBI ↔ RSEM(API) characterization 的三件事，逐條鎖在這裡。

1. **配對本身**（座標／id／順序），以及配不到的那一顆會怎樣；
2. **`carry`** —— 把配到那顆的 KLARF 欄位帶成 feature。少了它，
   「抓到了」與「藏在 raw data 內」在資料上長得一模一樣，而那正是這個功能
   存在的理由；
3. **圖對圖**（`align_to`）：座標給候選、NCC 選最像的，而配錯的那一顆
   分數會掉下來。

外加兩條不變量：**第二份 source 要進快取簽章**（鐵則 9），以及
**`workers=1` 與 `workers=4` 逐位元組相同**。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.algo import pairing                                 # noqa: E402
from d4t.core.algo.align import locate_template                   # noqa: E402
from d4t.core.ingest import pair_source as pair_ingest            # noqa: E402
from d4t.core.ingest.dataset import Dataset, DefectItem, ImageRef  # noqa: E402
from d4t.core.pipeline import get_step                            # noqa: E402
from d4t.core.pipeline.batch import _dataset_token_for            # noqa: E402
from d4t.core.pipeline.context import Context                     # noqa: E402
from d4t.core.pipeline.step import StepError                      # noqa: E402


# --------------------------------------------------------------------------- #
# 工具：兩份假 lot（座標是重點，影像用畫的）
# --------------------------------------------------------------------------- #
def _item(did, x, y, die=(1, 1), fields=None):
    it = DefectItem(defect_id=did, die=die, xrel_nm=float(x), yrel_nm=float(y))
    it.fields = dict(fields or {})
    return it


def _lot(points, kind="rsem"):
    return Dataset(kind=kind, klarf=None,
                   items=[_item(*p) if isinstance(p, tuple) else p
                          for p in points])


def _ctx(main_item, sources):
    ctx = Context()
    ctx.meta["_defect_item"] = main_item
    ctx.meta["_dataset_kind"] = "rsem"
    ctx.meta["_sources"] = dict(sources)
    return ctx


def _run(ctx, **over):
    p = {"source": "ebi", "match": "position", "tol_nm": 500.0,
         "candidates": 1, "carry": "", "channel": "", "out": "paired"}
    p.update(over)
    get_step("pair_source")().run(ctx, p)
    return ctx


# --------------------------------------------------------------------------- #
# 1. 配對
# --------------------------------------------------------------------------- #
def test_the_nearest_defect_within_the_tolerance_wins():
    main = _item("gt1", 0, 0)
    others = _lot([("ebi_far", 900, 0), ("ebi_near", 120, 40)]).items
    ctx = _ctx(main, {"ebi": others})
    with pytest.raises(StepError):
        _run(ctx)                      # 沒有影像 → 配到了但載不出圖
    assert ctx.features["pair_found"] == 1.0
    assert ctx.features["match_dist_nm"] == pytest.approx(126.49, abs=0.1)
    assert ctx.meta["pair_match"]["defect_id"] == "ebi_near"


def test_nothing_within_the_tolerance_is_recorded_not_guessed():
    """配不到**不是**「取最近的那顆」——EBI 根本沒偵測到，就是這個結論本身。

    而那個結論要**留得下來**（F33）：這一顆不吐流、不炸，繼續走到判定樹。
    以前這裡是 raise，於是「根本沒偵測到」那一整類都變成 `ok=False`
    —— characterization 要數的正是那一類。
    """
    ctx = _ctx(_item("gt1", 0, 0), {"ebi": _lot([("ebi", 9000, 0)]).items})
    _run(ctx)                                   # 不再 raise
    assert ctx.features["pair_found"] == 0.0
    assert "paired" not in ctx.images           # 不吐流
    # **算不出來的不寫**：NaN 更糟 —— 判定樹問 `expr != 0`，而 `NaN != 0` 是真，
    # 於是 `match_dist_nm > X` 會對一顆根本沒配到的 defect 答「是」。
    assert "match_dist_nm" not in ctx.features
    assert "match_ambiguous" not in ctx.features
    assert ctx.meta["pair_match"]["index"] == -1
    assert any("pair_found = 0" in w for w in ctx.meta.get("warnings", []))


def test_a_second_defect_inside_the_tolerance_is_flagged():
    """兩顆都在容差內 = 這個配對是猜的，而使用者要看得見。"""
    ctx = _ctx(_item("gt1", 0, 0),
               {"ebi": _lot([("a", 100, 0), ("b", 200, 0)]).items})
    with pytest.raises(StepError):
        _run(ctx, candidates=2)
    assert ctx.features["match_ambiguous"] == 1.0


def test_a_defect_with_no_coordinates_does_not_pair_with_everything():
    """座標不明的那幾顆若當成「都在原點」，它們會互相配到而且距離是 0。"""
    ctx = _ctx(DefectItem(defect_id="no_xy", die=(1, 1), xrel_nm=None,
                          yrel_nm=None),
               {"ebi": _lot([("a", 0, 0)]).items})
    _run(ctx)
    assert ctx.features["pair_found"] == 0.0
    assert "match_dist_nm" not in ctx.features


def test_matching_by_order_and_by_id():
    others = _lot([("x", 0, 0), ("y", 0, 0), ("z", 0, 0)])
    main = _item("y", 5000, 5000)
    main.index = 1
    ctx = _ctx(main, {"ebi": others.items})
    with pytest.raises(StepError):
        _run(ctx, match="order")
    assert ctx.meta["pair_match"]["defect_id"] == "y"

    ctx2 = _ctx(main, {"ebi": others.items})
    with pytest.raises(StepError):
        _run(ctx2, match="id")
    assert ctx2.meta["pair_match"]["defect_id"] == "y"


def test_no_second_lot_says_which_button_to_press():
    ctx = _ctx(_item("gt1", 0, 0), {})
    with pytest.raises(StepError) as e:
        _run(ctx)
    assert "Open data…" in str(e.value)


# --------------------------------------------------------------------------- #
# 2. carry —— 「藏在 raw data 內」才答得出來
# --------------------------------------------------------------------------- #
def test_carried_columns_become_features():
    hit = _item("ebi_near", 100, 0, fields={"ROUGHBINNUMBER": "12",
                                            "DEFECTID": "8801"})
    ctx = _ctx(_item("gt1", 0, 0), {"ebi": [hit]})
    with pytest.raises(StepError):
        _run(ctx, carry="ROUGHBINNUMBER,DEFECTID")
    assert ctx.features["pair_ROUGHBINNUMBER"] == 12.0
    assert ctx.features["pair_DEFECTID"] == 8801.0


def test_a_column_that_is_not_a_number_goes_to_meta_not_to_features():
    """feature 是**數字**的地盤。塞一個字串進去會讓分數表達式炸在一個跟它
    無關的地方。"""
    hit = _item("ebi", 100, 0, fields={"CLASS": "particle"})
    ctx = _ctx(_item("gt1", 0, 0), {"ebi": [hit]})
    with pytest.raises(StepError):
        _run(ctx, carry="CLASS")
    assert "pair_CLASS" not in ctx.features
    assert ctx.meta["pair_fields"]["CLASS"] == "particle"


def test_a_column_that_does_not_exist_is_said_out_loud():
    """打錯一個欄位名**不可以安靜地沒事**。

    這張卡的存在理由就是把那幾欄帶過來（「偵測到但分數太低」只有靠它答得出
    來），而少了一欄的 CSV 跟成功的 CSV 長得一模一樣 —— 跑得完、有數字、
    而且是錯的。擋在這裡＝這幾顆 ok=False 而整批照跑（鐵則 7）。

    ⚠ 這是**第二道**。第一道在掛上來的那一刻（`missing_columns`）——
    那時候 KlarfDoc 還在手上，所以答得出「那它有哪些欄」；卡片手上只有複製
    過去的那幾欄（第二份的 doc 刻意不進 worker），所以它只講得出「帶過來的
    是哪幾欄」。兩句話都要，而且**都不可以假裝自己是另一句**。
    """
    hit = _item("ebi", 100, 0, fields={"ROUGHBINNUMBER": "12"})
    ctx = _ctx(_item("gt1", 0, 0), {"ebi": [hit]})
    with pytest.raises(StepError) as e:
        _run(ctx, carry="ROUHGBINNUMBER")      # 打錯字
    msg = str(e.value)
    assert "ROUHGBINNUMBER" in msg              # 錯的那一個要講出來
    assert "ROUGHBINNUMBER" in msg              # 帶過來的是哪幾欄
    assert "Carry these columns" in msg         # 要改哪一格


def test_only_the_columns_asked_for_are_copied():
    """raw data 是幾十萬顆，×24 欄字串是幾百 MB —— 而那幾欄還要 pickle 進
    worker。`columns=None`（CLI／測試的路）才是全帶。"""
    class _Doc:
        defect_columns = ["DEFECTID", "XREL", "ROUGHBINNUMBER"]
        defects = [["11", "0", "7"], ["12", "0", "9"]]

    def lot():
        ds = Dataset(kind="ebi_patch", klarf=_Doc(),
                     items=[_item("a", 0, 0), _item("b", 0, 0)])
        ds.items[0].klarf_row = 0
        ds.items[1].klarf_row = 1
        return ds

    all_ds = lot()
    assert pair_ingest.fill_fields(all_ds) == 3
    assert set(all_ds.items[0].fields) == {"DEFECTID", "XREL", "ROUGHBINNUMBER"}

    some = lot()
    assert pair_ingest.fill_fields(some, ["roughbinnumber"]) == 1
    assert some.items[1].fields == {"ROUGHBINNUMBER": "9"}


def test_refilling_replaces_instead_of_adding_up():
    """少填一欄的時候舊的那一份還留著的話，「這一欄現在還在不在」就有兩個
    答案 —— 而卡片信的是 `fields`。"""
    class _Doc:
        defect_columns = ["DEFECTID", "ROUGHBINNUMBER"]
        defects = [["11", "7"]]

    second = Dataset(kind="ebi_patch", klarf=_Doc(), items=[_item("a", 0, 0)])
    second.items[0].klarf_row = 0
    main = _lot([("gt", 0, 0)])
    pair_ingest.attach(main, second, "ebi", columns=["DEFECTID"])
    assert set(second.items[0].fields) == {"DEFECTID"}

    pair_ingest.refill_fields(main, "ebi", ["ROUGHBINNUMBER"])
    assert set(second.items[0].fields) == {"ROUGHBINNUMBER"}


def test_the_lot_says_which_columns_it_has_while_the_doc_is_still_in_hand():
    """打錯字的人要看的是「那一份有哪些欄」，而只有掛的那一刻答得出來。"""
    class _Doc:
        defect_columns = ["DEFECTID", "ROUGHBINNUMBER"]
        defects = [["11", "7"]]

    ds = Dataset(kind="ebi_patch", klarf=_Doc(), items=[_item("a", 0, 0)])
    assert pair_ingest.columns_of(ds) == ["DEFECTID", "ROUGHBINNUMBER"]
    assert pair_ingest.missing_columns(ds, ["defectid", "ROUHGBIN"]) == ["ROUHGBIN"]
    # 沒有 KLARF 的那種資料**不是**「每一欄都缺」——它是「carry 在這裡沒有
    # 東西可帶」，而那句話不該長成一串假的缺欄清單。
    assert pair_ingest.missing_columns(_lot([("x", 0, 0)]), ["ANY"]) == []


def test_the_columns_come_from_the_cards_that_point_at_that_source():
    """同一份第二 source 可以被兩張卡指著，照其中一張填的話另一張會少欄位。"""
    from d4t.core.steps.pair_source import columns_for_source

    class _N:
        def __init__(self, step, params):
            self.step, self.params = step, params

    nodes = [_N("pair_source", {"source": "gt", "carry": "defectid, Class"}),
             _N("pair_source", {"source": "gt", "carry": "DEFECTID"}),
             _N("pair_source", {"source": "other", "carry": "SIZE"}),
             _N("glv_stats", {})]
    assert columns_for_source(nodes, "gt") == ["DEFECTID", "CLASS"]
    assert columns_for_source(nodes, "nobody") == []


def test_the_declared_features_include_the_carried_ones():
    """lint 與畫布靠宣告，而使用者要在分數表達式的下拉裡看到它們。"""
    card = get_step("pair_source")
    names = card.resolve_features(card.validate_params({"carry": "SCORE"}))
    assert "pair_SCORE" in names and "pair_found" in names


def test_carry_reads_the_columns_ingest_filled_in():
    """`fields` 是 ingest 掛第二份時填的（`fill_fields`）——卡片不碰 KLARF。"""
    class _Doc:
        defect_columns = ["DEFECTID", "XREL", "ROUGHBINNUMBER"]
        defects = [["11", "0", "7"], ["12", "0", "9"]]

    second = Dataset(kind="ebi_patch", klarf=_Doc(),
                     items=[_item("a", 0, 0), _item("b", 0, 0)])
    second.items[0].klarf_row = 0
    second.items[1].klarf_row = 1
    main = _lot([("gt", 0, 0)])
    rep = pair_ingest.attach(main, second, "ebi")
    assert rep.fields == 3
    assert second.items[1].fields["ROUGHBINNUMBER"] == "9"


# --------------------------------------------------------------------------- #
# 3. 圖對圖（align_to）
# --------------------------------------------------------------------------- #
def _noise(h, w, seed=0):
    return np.random.default_rng(seed).integers(0, 255, (h, w)).astype(np.uint8)


def test_the_small_image_is_found_inside_the_big_one():
    big = _noise(300, 300, 1)
    ctx = Context(images={"test": big[90:154, 40:104].copy(), "paired": big})
    # `search_within=0` = 整張圖。這一條驗的是「找得到」，而那一塊刻意放在角落
    # —— 只在中間找的那條規矩有自己的驗收（見下面）。
    get_step("align_to")().run(ctx, {"template": "test", "search": "paired",
                                     "min_score": 0.3, "out": "aligned",
                                     "search_within": 0.0})
    assert ctx.features["ncc_score"] > 0.99
    assert ctx.features["align_dx_px"] == pytest.approx(40, abs=1)
    assert ctx.features["align_dy_px"] == pytest.approx(90, abs=1)
    # 裁出來的那一塊跟小圖同尺寸，而且**就是**那一塊
    assert ctx.images["aligned"].shape == ctx.images["test"].shape
    assert np.array_equal(ctx.images["aligned"], ctx.images["test"])


def test_a_wrong_pairing_shows_up_as_a_low_score():
    """配錯的那一顆不會安靜地產出數字——這是整個 C 步存在的理由。"""
    ctx = Context(images={"test": _noise(64, 64, 2), "paired": _noise(300, 300, 3)})
    with pytest.raises(StepError) as e:
        get_step("align_to")().run(ctx, {"template": "test", "search": "paired",
                                         "min_score": 0.5, "out": "aligned"})
    assert "not the same defect" in str(e.value)
    assert ctx.features["align_ok"] == 0.0
    assert ctx.features["ncc_score"] < 0.5


def test_the_candidates_are_ranked_by_ncc_not_by_distance():
    """座標最近的那一顆不一定是對的——這正是使用者說的「疊到的 patch 跟
    RSEM 不符合」。"""
    right = _noise(300, 300, 4)
    patch = right[120:184, 200:264].copy()
    wrong = _noise(300, 300, 5)
    ctx = Context(images={"test": patch, "paired": wrong})
    ctx.meta["pair_candidates"] = [right]          # 座標第二近的才是對的
    get_step("align_to")().run(ctx, {"template": "test", "search": "paired",
                                     "min_score": 0.3, "out": "aligned",
                                     "search_within": 0.0})
    assert ctx.meta["align_to"]["candidate"] == 1, "應該挑第二個候選"
    assert ctx.features["ncc_score"] > 0.99
    assert np.array_equal(ctx.images["aligned"], patch)


def test_the_two_images_the_wrong_way_round_says_so():
    ctx = Context(images={"test": _noise(300, 300, 6), "paired": _noise(64, 64, 7)})
    with pytest.raises(StepError) as e:
        get_step("align_to")().run(ctx, {"template": "test", "search": "paired",
                                         "min_score": 0.3, "out": "aligned"})
    assert "wrong way round" in str(e.value)


def test_locate_template_is_silent_on_a_flat_image():
    """常數影像的 NCC 是 0/0——OpenCV 回的是垃圾而不是錯誤。"""
    assert locate_template(np.zeros((100, 100), np.uint8),
                           np.zeros((10, 10), np.uint8)) == (0.0, 0.0, 0.0)


# --------------------------------------------------------------------------- #
# 4. 鐵則 9：第二份 source 要進快取簽章
# --------------------------------------------------------------------------- #
def test_attaching_a_second_source_changes_the_cache_token(tmp_path):
    main = _lot([("gt", 0, 0)])
    before = _dataset_token_for(main)
    pair_ingest.attach(main, _lot([("a", 0, 0)], kind="ebi_patch"), "ebi")
    after = _dataset_token_for(main)
    assert before != after, "換一份第二 source，快取簽章看不見的話會回舊影像"


def test_the_token_is_unchanged_when_nothing_is_attached():
    """一份都沒掛時 token 要**逐字元不變** —— 既有的快取目錄與黃金值不受影響。"""
    main = _lot([("gt", 0, 0)])
    assert "+src:" not in _dataset_token_for(main)


def test_the_source_id_is_part_of_the_token():
    """同一份資料換一個代號，`pair_source` 卡指的就是另一個東西。"""
    a = _lot([("gt", 0, 0)])
    b = _lot([("gt", 0, 0)])
    pair_ingest.attach(a, _lot([("x", 0, 0)], kind="ebi_patch"), "ebi")
    pair_ingest.attach(b, _lot([("x", 0, 0)], kind="ebi_patch"), "rsem")
    assert _dataset_token_for(a) != _dataset_token_for(b)


# --------------------------------------------------------------------------- #
# 5. 演算法：跟 KLIP 的那一支不准漂
# --------------------------------------------------------------------------- #
def test_the_two_matchers_agree():
    """`algo/pairing` 與 `ingest/klarf_core.compare` 是同一個演算法的兩個轉接。

    輸入與輸出不一樣（KlarfDoc 對 DefectItem、整份 diff 對逐顆問），所以是兩支；
    但**桶的算法必須一模一樣**，不然「KLIP 說配到、d4t 說沒配到」會變成一個
    沒有人查得動的差異。
    """
    from d4t.core.ingest import klarf_core

    pts_a = [("a1", 0, 0), ("a2", 1000, 1000), ("a3", 50000, 0)]
    pts_b = [("b1", 120, 40), ("b2", 1400, 1000), ("b3", 90000, 0)]

    class _Doc:
        version = "1.8"
        defect_columns = ["DEFECTID", "XINDEX", "YINDEX", "XREL", "YREL",
                          "CLASSNUMBER"]

        def __init__(self, pts):
            self.defects = [[did, "1", "1", str(x), str(y), "0"]
                            for did, x, y in pts]

        def unit_info(self):
            return {"to_nm": 1.0, "coord_unit": "nm"}

        def col_index(self, name):
            up = name.upper()
            return self.defect_columns.index(up) if up in self.defect_columns else -1

        # compare() 還要下面這些才跑得完整份 diff（header／class／summary），
        # 但配對本身一個都用不到 —— 給空的就好。
        source_path = ""
        class_lookup = {}
        _summary_rows = ()
        _summary_columns = ()

        def header_items(self):
            return []

    mine = pairing.pair_all(_lot(pts_a).items, _lot(pts_b).items, tol_nm=500.0)
    theirs = klarf_core.compare(_Doc(pts_a), _Doc(pts_b), tol_nm=500.0,
                                mode="position")
    # compare() 的 'matched' 只有顆數，配對本身要從 'moved' 拿（每一對的座標都
    # 差了一點，所以三對配到的全都在裡面）。
    assert theirs["matched"] == len(mine)
    assert [(a, b) for a, b, _d in mine] == \
        [(pa["i"], pb["i"]) for pa, pb in theirs["moved"]]
    # 沒配到的那一顆兩邊也要是同一顆
    assert [p["i"] for p in theirs["removed"]] == [2]
    assert [p["i"] for p in theirs["added"]] == [2]


def test_one_defect_is_not_claimed_by_two():
    """一對一（KLIP 的 ``used_b``）：B 的一顆不會同時被 A 的兩顆認領。"""
    a = _lot([("a1", 0, 0), ("a2", 60, 0)])
    b = _lot([("b1", 30, 0)])
    got = pairing.pair_all(a.items, b.items, tol_nm=500.0)
    assert len(got) == 1 and got[0][0] == 0


# --------------------------------------------------------------------------- #
# 6. 端到端：第二份要**進得了 worker**
# --------------------------------------------------------------------------- #
def _two_lots(tmp_path):
    import os
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from make_sample import generate

    main = generate(str(tmp_path / "main"), n=6, seed=7)
    gt = generate(str(tmp_path / "gt"), n=6, seed=7)
    renamed = os.path.join(os.path.dirname(gt["klarf"]), "LOT_GT.001")
    os.replace(gt["klarf"], renamed)
    gt["klarf"] = renamed
    return main, gt


def _paired_recipe():
    from d4t.core.pipeline.recipe import Recipe, RecipeNode, ScoreSpec

    nodes = {
        "load": RecipeNode("load", "load_patch", {}),
        "pair": RecipeNode("pair", "pair_source",
                           {"source": "gt", "match": "position",
                            "tol_nm": 100000.0, "candidates": 2,
                            "carry": "DEFECTID"}),
        "align": RecipeNode("align", "align_to",
                            {"template": "test", "search": "paired",
                             "min_score": 0.0, "out": "aligned"}),
        "glv": RecipeNode("glv", "glv_stats", {"source": "aligned"}),
    }
    return Recipe(recipe_id="f15", routes={"ebi_patch": list(nodes)}, nodes=nodes,
                  score=ScoreSpec(expr="pair_found", threshold=0.5,
                                  bins={"below": 0, "above": 1}))


def test_the_second_lot_reaches_the_workers(tmp_path):
    """鐵則 9 的形狀：``workers=1`` 與 ``workers=2`` 要算出**一模一樣**的東西。

    第二份是 `run_batch` 另外送進 worker 的（`Dataset` 本身不進 pickle）——
    漏送的話 `workers=2` 每一顆都會失敗，而 `workers=1` 好好的。
    """
    from d4t.core.ingest.dataset import load_dataset
    from d4t.core.ingest import pair_source as pair_ingest
    from d4t.core.pipeline import run_batch

    main_paths, gt_paths = _two_lots(tmp_path)
    ds = load_dataset(main_paths["klarf"])
    pair_ingest.attach(ds, load_dataset(gt_paths["klarf"]), "gt")

    def features(workers):
        res = run_batch(_paired_recipe(), ds, workers=workers)
        return [(r.get("defect_id"), r.get("ok"),
                 sorted((r.get("features") or {}).items())) for r in res]

    one = features(1)
    assert len(one) == 6 and all(ok for _d, ok, _f in one)
    assert dict(one[0][2])["pair_found"] == 1.0
    assert dict(one[0][2])["pair_DEFECTID"] > 0
    assert dict(one[0][2])["ncc_score"] > 0.9
    assert features(2) == one


def test_a_recipe_with_a_pair_card_survives_the_round_trip():
    """`to_json_dict → from_json_dict` 是 `run_batch` 送 recipe 進 worker 的路
    （鐵則 9）—— 它一旦不是 identity，workers=1 與 workers=2 就會不一樣。"""
    from d4t.core.pipeline.recipe import Recipe

    rec = _paired_recipe()
    again = Recipe.from_json_dict(rec.to_json_dict())
    assert again.to_json_dict() == rec.to_json_dict()
    assert again.nodes["pair"].params["source"] == "gt"


# --------------------------------------------------------------------------- #
# 7. 像素大小：兩台機台不一樣，NCC 本身不含縮放
# --------------------------------------------------------------------------- #
def test_the_two_sides_can_have_different_pixel_sizes():
    """使用者：「像素尺寸不同，可以預設一樣，或給 user 輸入」。

    不處理的話它不是「差一點」而是**整個對不上**：同一塊區域、1.5 倍的像素
    大小差，NCC 分數從 0.93 掉到 0.03。而掉下去的那一顆看起來就像「配錯了」
    —— 那是最難查的一種錯，因為每一顆都一樣。
    """
    import cv2

    big = _noise(300, 300, 3)                       # 大圖：1.0 nm/px
    same = big[90:154, 40:104].copy()               # 同一塊，64×64
    finer = cv2.resize(same, (96, 96))              # 拍得更細 → 64/96 nm/px

    def run(**extra):
        ctx = Context(images={"test": finer, "paired": big})
        ctx.set_stream_nm_per_px("test", 64 / 96.0)
        ctx.set_stream_nm_per_px("paired", 1.0)
        params = {"template": "test", "search": "paired", "min_score": 0.0,
                  "out": "aligned", "search_within": 0.0}
        params.update(extra)
        get_step("align_to")().run(ctx, params)
        return ctx

    auto = run()
    assert auto.features["align_scale"] == pytest.approx(64 / 96.0, abs=1e-6)
    assert auto.features["ncc_score"] > 0.9
    assert auto.features["align_dx_px"] == pytest.approx(40, abs=1)
    assert auto.features["align_dy_px"] == pytest.approx(90, abs=1)
    # 裁出來的是**大圖的像素**，所以它帶的是大圖的 nm/px
    assert auto.images["aligned"].shape == (64, 64)
    assert auto.stream_nm_per_px("aligned") == 1.0

    # 使用者自己填的說了算
    manual = run(scale=0.6667)
    assert manual.features["align_scale"] == pytest.approx(0.6667)
    assert manual.features["ncc_score"] > 0.9

    # 不處理尺度的話 —— 這就是「整個對不上」長什麼樣
    blind = Context(images={"test": finer, "paired": big})
    get_step("align_to")().run(blind, {"template": "test", "search": "paired",
                                       "min_score": -1.0, "out": "aligned"})
    assert blind.features["align_scale"] == 1.0      # 兩邊都不知道 → 當作一樣
    assert blind.features["ncc_score"] < 0.2


def test_the_second_lot_carries_its_own_pixel_size():
    """一格 nm/px 長在**把那份資料讀進來的那張卡**上 —— 第二份也是。

    規則要是一句話而不是兩句：主 lot 的那一格在 Load 卡上，第二份的在這張卡
    上，而兩者都是「這份資料的一個像素是幾奈米」。`align_to` 因此不必知道誰
    是誰 —— 它問的是**那條流**（`Context.stream_nm_per_px`）。
    """
    class _Hit:
        """有影像的第二份那一顆（`DefectItem` 要真的檔案，這裡只要像素）。"""

        defect_id = "ebi"
        die, xrel_nm, yrel_nm, index = (1, 1), 100.0, 0.0, 0
        fields = {}
        images = {"single": object()}

        def load(self, _name):
            return np.zeros((8, 8), np.uint8)

    ctx = _ctx(_item("gt1", 0, 0), {"ebi": [_Hit()]})
    _run(ctx, nm_per_px=3.0)
    assert ctx.stream_nm_per_px("paired") == 3.0

    # 沒填就是不知道 —— 不要編一個數字出來
    ctx2 = _ctx(_item("gt1", 0, 0), {"ebi": [_Hit()]})
    _run(ctx2)
    assert ctx2.stream_nm_per_px("paired") is None


# --------------------------------------------------------------------------- #
# 8. 只在該找的地方找（使用者：「可以抓 FOV ~15% 左右」）
# --------------------------------------------------------------------------- #
def _fov(size=400, seed=5):
    return _noise(size, size, seed)


def _cut(img, cx, cy, side=64):
    return img[cy - side // 2:cy + side // 2, cx - side // 2:cx + side // 2].copy()


def _align(big, tmpl, **extra):
    ctx = Context(images={"test": tmpl, "paired": big})
    p = {"template": "test", "search": "paired", "min_score": 0.3,
         "out": "aligned"}
    p.update(extra)
    try:
        get_step("align_to")().run(ctx, p)
        return ctx, None
    except StepError as e:
        return ctx, str(e)


def test_the_search_stays_near_the_middle_because_the_stage_went_there():
    """機台是先移到那一顆的座標才拍的，所以 defect 就在中間 —— 差的只有 stage
    沒對準的那一點。

    只找那一塊有兩個好處，而**第二個才是重點**：快，以及**不會對到影像另一端
    那個長得一模一樣的結構上**。
    """
    big = _fov()
    near = _cut(big, 200 + 30, 200 - 20)        # 偏 30 px = FOV 的 7.5%
    ctx, err = _align(big, near)
    assert err is None and ctx.features["ncc_score"] > 0.99
    # 偏離預期位置多少 —— 這一顆的 stage offset
    assert ctx.features["align_off_x_px"] == pytest.approx(30, abs=1)
    assert ctx.features["align_off_y_px"] == pytest.approx(-20, abs=1)


def test_a_match_outside_the_window_is_said_out_loud_not_swallowed():
    """框把對的那一塊排除掉的時候，錯誤訊息要**講出框的存在** ——
    不然使用者看到的是「這兩張不像」，而那句話是錯的。"""
    big = _fov()
    far = _cut(big, 200 + 150, 200)             # 偏 150 px = FOV 的 37%
    ctx, err = _align(big, far)
    assert err is not None
    assert "15" in err and "search all of it" in err
    assert ctx.features["align_ok"] == 0.0

    ctx2, err2 = _align(big, far, search_within=0.0)     # 關掉就找得到
    assert err2 is None and ctx2.features["ncc_score"] > 0.99


def test_a_systematic_stage_offset_can_be_measured_and_put_back():
    """stage offset 是**系統性**的，所以量一次就可以全批共用。

    整批的 `align_off_x_px` 取中位數 → 填進 `expect_dx_px` → 框就可以縮小，
    而縮小的框正是「不會對到隔壁」的保證。
    """
    big = _fov()
    far = _cut(big, 200 + 150, 200)
    ctx, err = _align(big, far, expect_dx_px=150.0, search_within=5.0)
    assert err is None and ctx.features["ncc_score"] > 0.99
    # 填對了之後，這一顆就「沒有偏離預期」
    assert ctx.features["align_off_x_px"] == pytest.approx(0, abs=1)


def test_a_repeating_pattern_shows_up_as_a_peak_ratio_near_one():
    """陣列區裡同一個模板在好幾個地方都拿到一樣高的分數，而**峰值本身完全看不
    出這件事**。第一名與第二名的比才看得出來。"""
    rng = np.random.default_rng(11)
    tile = np.tile(rng.integers(0, 255, (20, 20)).astype(np.uint8), (20, 20))
    ctx, err = _align(tile, tile[190:210, 190:210].copy(), search_within=0.0)
    assert err is None
    assert ctx.features["ncc_score"] > 0.99          # 分數滿分
    assert ctx.features["align_peak_ratio"] > 0.95   # 而且完全不可信

    plain = _fov(seed=9)
    ctx2, err2 = _align(plain, _cut(plain, 200, 200), search_within=0.0)
    assert ctx2.features["align_peak_ratio"] < 0.5   # 這種才是真的對到


# --------------------------------------------------------------------------- #
# 9. F33：配不到的那一顆要**留下來**（③「根本沒偵測到」是一個結論，不是錯誤）
# --------------------------------------------------------------------------- #
def test_align_to_lets_an_unpaired_defect_through_quietly():
    """上游沒配到 → 這張卡沒有東西可比，**安靜讓路**而不是炸。

    炸掉的話那一顆 `ok=False`、沒有 bin，於是 ③ 那一類從輸出裡整個消失 ——
    而 CSV 上看不出來（少了幾列，跟「本來就沒那幾顆」長得一模一樣）。
    """
    ctx = Context(images={"test": _noise(64, 64, 3)})
    ctx.meta["pair_match"] = {"source": "ebi", "defect_id": "", "index": -1,
                              "dist_nm": float("nan"), "candidates": 1,
                              "out": "paired"}
    get_step("align_to")().run(ctx, {"template": "test", "search": "paired",
                                     "min_score": 0.3, "out": "aligned"})
    # 一個數字都不寫（算不出來的不寫），也不吐流
    assert "ncc_score" not in ctx.features and "align_ok" not in ctx.features
    assert "aligned" not in ctx.images
    assert any("no match" in w for w in ctx.meta.get("warnings", []))


def test_align_to_still_errors_when_the_line_is_just_wrong():
    """讓路與**接錯線**不可以長得一樣。

    少了「那張卡的 out 就是我要的這條流」這個條件，打錯流名的 recipe 會被當成
    「沒配到」而安靜跳過 —— 每一顆都沒有數字，而畫面上沒有一句話說為什麼。
    """
    # ① 完全沒有配對卡：照舊炸
    ctx = Context(images={"test": _noise(64, 64, 3)})
    with pytest.raises(Exception) as e1:
        get_step("align_to")().run(ctx, {"template": "test", "search": "paired",
                                         "min_score": 0.3, "out": "aligned"})
    assert "paired" in str(e1.value)

    # ② 有配對卡、也沒配到，但它吐的是**另一條**流 → 這裡要的那條是接錯的
    ctx2 = Context(images={"test": _noise(64, 64, 3)})
    ctx2.meta["pair_match"] = {"source": "ebi", "index": -1, "out": "second"}
    with pytest.raises(Exception):
        get_step("align_to")().run(ctx2, {"template": "test", "search": "typo",
                                          "min_score": 0.3, "out": "aligned"})


def _tree_recipe():
    """characterization 的樹：先問「有沒有配到」，才分得出 ②③。"""
    from d4t.core.pipeline.recipe import (
        DecideSpec, Recipe, RecipeNode, ScoreSpec, TreeLeaf, TreeStep,
    )

    nodes = {
        "load": RecipeNode("load", "load_patch", {}),
        "pair": RecipeNode("pair", "pair_source",
                           {"source": "gt", "match": "position",
                            "tol_nm": 100000.0, "carry": "DEFECTID"}),
    }
    tree = TreeStep(
        when="pair_found < 1",
        yes=TreeLeaf(bin=3, label="not detected"),
        no=TreeStep(when="pair_DEFECTID > 0",
                    yes=TreeLeaf(bin=1, label="caught"),
                    no=TreeLeaf(bin=2, label="detected, not sampled")))
    return Recipe(recipe_id="f33", routes={"ebi_patch": list(nodes)},
                  nodes=nodes,
                  score=ScoreSpec(expr="", threshold=0.5,
                                  bins={"below": 0, "above": 1}),
                  decide=DecideSpec(tree=tree))


def test_an_unmatched_defect_still_reaches_the_third_verdict(tmp_path):
    """③ 那一類要**數得出來**：它是輸出裡的一列、有 bin、進得了判定樹。

    這是整個 characterization 的地基 —— ③ 的顆數就是這份分析的結論。
    """
    from d4t.core.ingest.dataset import load_dataset
    from d4t.core.pipeline import run_batch
    from d4t.core.pipeline import decide_tree

    main_paths, gt_paths = _two_lots(tmp_path)
    ds = load_dataset(main_paths["klarf"])
    second = load_dataset(gt_paths["klarf"])
    # 第二份少一顆 → 那一顆在 main 裡配不到，就是「EBI 根本沒偵測到」
    missing_id = second.items[0].defect_id
    second.items = second.items[1:]
    pair_ingest.attach(ds, second, "gt", columns=["DEFECTID"])

    rec = _tree_recipe()
    rows = run_batch(rec, ds, workers=1)
    lost = [r for r in rows if r["defect_id"] == missing_id]
    assert len(lost) == 1, "配不到的那一顆必須仍然是輸出裡的一列"
    row = lost[0]
    assert row["ok"] is True and row["bin"] == 3
    assert row["features"]["pair_found"] == 0.0
    # 樹只評走得到的那條路 → 第三類那一支不會累積「問不到」
    assert row["features"].get("decide_unanswered", 0.0) == 0.0
    # Results 面板的顆數加總對得起來
    entries = decide_tree.verdict_rows(rec.decide, rows)
    not_detected = [e for e in entries if e["name"] == "not detected"]
    assert not_detected and missing_id in not_detected[0]["ids"]
    assert sum(e["count"] for e in entries) == len(rows)


def test_an_old_recipe_that_says_paired_is_migrated_everywhere():
    """改名要**連同它被寫進去的每一個地方**一起遷移。

    以前遷移只換 `score.expr` —— F30 之後問問題的地方是判定樹，而樹上沒跟著
    換的那一題會安靜地永遠答「否」（問不到的特徵算否），畫面上它跟一條正常的
    規則長得一模一樣。
    """
    from d4t.core.pipeline.recipe import Recipe

    raw = {
        "recipe_id": "old",
        "routes": {"ebi_patch": ["pair"]},
        "nodes": {"pair": {"step": "pair_source",
                           "params": {"source": "gt", "carry": "DEFECTID"}}},
        "score": {"expr": "paired * 10", "threshold": 0.5,
                  "bins": {"below": 0, "above": 1}},
        "decide": {
            "let": [{"name": "hit", "expr": "paired"}],
            "rules": [{"when": "paired < 1", "bin": 3, "label": "missed"}],
            "score": "paired",
            "tree": {"when": "paired < 1",
                     "yes": {"bin": 3, "label": "missed"},
                     "no": {"bin": 1, "label": "caught"}},
        },
    }
    rec = Recipe.from_json_dict(raw)
    assert rec.score.expr == "pair_found * 10"
    assert rec.decide.let[0].expr == "pair_found"
    assert rec.decide.rules[0].when == "pair_found < 1"
    assert rec.decide.score == "pair_found"
    assert rec.decide.tree.when == "pair_found < 1"

    # 冪等 —— 第二趟是 no-op，`to_json_dict → from_json_dict` 仍是 identity
    # （鐵則 9：那是 `run_batch` 送 recipe 進 worker 的路）。
    again = Recipe.from_json_dict(rec.to_json_dict())
    assert again.to_json_dict() == rec.to_json_dict()


def test_a_name_that_merely_contains_paired_is_left_alone():
    """換的是**整個識別字**：`my_paired_ratio` 不是 `paired`。"""
    from d4t.core.pipeline.recipe import Recipe

    raw = {
        "recipe_id": "old",
        "routes": {"ebi_patch": ["pair"]},
        "nodes": {"pair": {"step": "pair_source", "params": {"source": "gt"}}},
        "score": {"expr": "my_paired_ratio", "threshold": 0.5,
                  "bins": {"below": 0, "above": 1}},
    }
    assert Recipe.from_json_dict(raw).score.expr == "my_paired_ratio"

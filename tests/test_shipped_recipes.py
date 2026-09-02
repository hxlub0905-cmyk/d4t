# -*- coding: utf-8 -*-
"""`recipes/` 裡出貨的 recipe —— **每一份都要跑得動**。

為什麼這支測試比那幾份檔案還重要
--------------------------------
這個 repo 上一次有「範例 recipe」是 `examples/`，而它 2026-08-16 被整個刪掉，
理由不是「不需要範例」——是**它們爛了**：卡片改名、參數換了、其中五份根本
載不進來，而沒有任何一條測試問過它們。留下來的是兩個按了會撞牆的入口
（`scope.SHOW_SAMPLE_ENTRIES`），而**按了撞牆的鈕比沒有那顆鈕更糟**（推廣鐵則）。

所以這一次 recipe 跟測試一起進來。這裡問三種問題：

1. **載得進來**（`Recipe.load`）而且 **`validate` 沒有 error** ——
   一份出貨的 recipe 打開來就有紅字，等於送出去的東西是壞的。
2. **接線是對的**：線在該在的埠上（F9／鐵則 9 —— 資料從哪來由線決定）。
3. **真的跑得出那三類**：端對端跑一次，① ② ③ 都要數得出來。

⚠ 第 3 條刻意跑**整條路**（`run_batch` + `run_batch_steps`），不是 mock ——
這份 recipe 的價值就在「照著跑會得到什麼」，而那件事只有真的跑才問得到。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.ingest.dataset import load_dataset             # noqa: E402
from d4t.core.pipeline import Recipe, run_batch, validate    # noqa: E402
from d4t.core.pipeline.batch import run_batch_steps          # noqa: E402

RECIPES = REPO / "recipes"
RSEM = RECIPES / "rsem-worst-box.json"

#: **允許出現的 error，一份 recipe 一張表**（``{檔名: {(節點, code)}}``）。
#:
#: 預設是「一條都不准」，而**現在這張表是空的** ——
#: 2026-09-02 刪掉 `patch-dsnr-by-class.json` 之後唯一的例外跟著走了
#: （那一條是「模板是一張影像，塞不進 JSON」）。
#:
#: 表空著但**機制留著**，因為它配著下面那支反向測試：例外只給一種東西 ——
#: 那一格的值根本不是文字。寫成一張明列的表而不是「這份 recipe 跳過檢查」，
#: 是為了讓它長出**別的** error 的時候這支測試照樣要紅。
ALLOWED_ERRORS = {}


def _shipped():
    return sorted(RECIPES.glob("*.json"))


# --------------------------------------------------------------------------- #
# 1. 每一份都載得進來、健檢沒有 error
# --------------------------------------------------------------------------- #
def test_there_is_at_least_one_shipped_recipe():
    """空的 `recipes/` 會讓底下每一支測試變成「什麼都沒測、而且是綠的」。"""
    assert _shipped(), "recipes/ 是空的 —— 底下的測試就全部空轉了"


@pytest.mark.parametrize("path", _shipped(), ids=lambda p: p.name)
def test_a_shipped_recipe_loads_and_passes_its_own_lint(path):
    """**沒有 error**，除了 `ALLOWED_ERRORS` 明列的那幾條（warning 一律可以）。

    warning 放行是刻意的：一份 recipe 可以誠實地留著「這一格要你填」的欄位，
    而 lint 對那件事講的是 warning。擋掉 warning 等於逼一份誠實的 recipe 說謊。
    """
    allowed = ALLOWED_ERRORS.get(path.name, set())
    recipe = Recipe.load(path)
    for kind in recipe.routes:
        errors = [i for i in validate(recipe, kind=kind)
                  if i.level == "error"
                  and (str(i.node_id), i.code) not in allowed]
        assert not errors, "\n".join(
            "%s @%s: %s" % (i.code, i.node_id, i.detail) for i in errors)


@pytest.mark.parametrize("path", _shipped(), ids=lambda p: p.name)
def test_the_allowed_errors_are_all_still_happening(path):
    """**表上的例外要真的還在。**

    修好了卻沒把它從表上拿掉的話，這份 recipe 從此少一條防線 —— 而畫面上
    看不出來（測試照樣綠）。這是「例外表」這種東西唯一會爛的方式。
    """
    allowed = ALLOWED_ERRORS.get(path.name, set())
    if not allowed:
        return
    recipe = Recipe.load(path)
    seen = set()
    for kind in recipe.routes:
        seen |= {(str(i.node_id), i.code) for i in validate(recipe, kind=kind)
                 if i.level == "error"}
    assert allowed <= seen, "已經不會發生了，請從 ALLOWED_ERRORS 拿掉：%s" % (
        sorted(allowed - seen),)


@pytest.mark.parametrize("path", _shipped(), ids=lambda p: p.name)
def test_a_shipped_recipe_survives_a_round_trip(path):
    """存檔那一對是 `run_batch` 送 recipe 進 worker 的路（鐵則 9）。"""
    recipe = Recipe.load(path)
    assert Recipe.from_json_dict(recipe.to_json_dict()).to_json_dict() \
        == recipe.to_json_dict()


@pytest.mark.parametrize("path", _shipped(), ids=lambda p: p.name)
def test_a_shipped_recipe_says_which_version_wrote_it(path):
    """`app_version` 在的話，使用者在舊版打開它會被告知「你的程式舊了」，
    而不是「這份檔案壞了」（`docs/PITFALLS.md`）。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert str(raw.get("app_version", "")).strip()


# --------------------------------------------------------------------------- #
# 4. RSEM 單張：鋪滿整張圖，挑最異常的那一格
# --------------------------------------------------------------------------- #
_PLACES = (("roi_on_pattern", "on_pattern", "crossing"),
           ("roi_between_columns", "between_columns", "between_vertical"),
           ("roi_between_rows", "between_rows", "between_horizontal"))


def _rsem_lot(tmp_path, n=12, seed=11):
    from make_sample_rsem import generate

    made = generate(str(tmp_path / "rsem"), n=n, seed=seed)
    gt = json.loads(Path(made["ground_truth"]).read_text(encoding="utf-8"))
    return load_dataset(made["klarf"]), gt


def _rsem(folder):
    recipe = Recipe.load(RSEM)
    recipe.nodes["report"].params["folder"] = str(folder)
    return recipe


def test_the_rsem_recipe_tiles_the_whole_image_not_just_the_pattern():
    """**三張 Region 卡，三種放法，三條線都接在同一個 Region 埠上。**

    那個埠是 `region_keys`（複數）—— 第二條線是**累加**不是取代（F13-⑥）。
    少接一條不會報錯：那個區域的框就不存在了，而底下 `max(...)` 那一行少一
    項，跑得完、有數字。所以這三條線是宣告層唯一問得到的地方。
    """
    recipe = Recipe.load(RSEM)
    wires = {(e.src, e.src_out, e.dst, e.dst_in) for e in recipe.edges}
    for nid, region, place in _PLACES:
        assert recipe.nodes[nid].params["place"] == place
        assert recipe.nodes[nid].params["roi_out"] == region
        assert ("load", "single", nid, "source") in wires
        assert (nid, region, "glv", "roi") in wires, \
            "%s 的區域沒接到 GLV —— 那一塊就沒人量" % region
    assert ("load", "single", "glv", "source") in wires
    assert recipe.nodes["glv"].params["across_boxes"] == "each box"


def test_the_three_cards_do_not_step_on_each_others_numbers():
    """三張**同一種卡**在同一條 route 上 —— 診斷特徵會一模一樣地撞名。

    `output_prefix` 各給一個就沒事了，而**沒給的代價是 21 條 warning**：
    一份出貨的 recipe 打開來滿滿黃字，使用者第一個反應是「這份壞了」。
    """
    recipe = Recipe.load(RSEM)
    for nid, region, _place in _PLACES:
        assert recipe.nodes[nid].params["output_prefix"] == region


def test_a_defect_it_cannot_measure_gets_its_own_bin():
    """**`worst` 帶 fill，而樹的第一問就是它。**

    三個區域都鋪不出框的那一顆（條紋找不到、圖全黑）沒有 `glv_worst_score`。
    沒有 fill 的話 `max(...)` 算不出來 → 那一題答「否」→ 它安靜地滑進
    「one box stands out」，跟一顆真的缺陷長得一模一樣。
    """
    recipe = Recipe.load(RSEM)
    lets = {x.name: x for x in recipe.decide.let}
    assert lets["worst"].fill == "-1"
    assert recipe.decide.tree.when.replace(" ", "") == "worst<0"
    assert recipe.decide.tree.yes.bin == 9
    # **「什麼都沒有」＝ bin 0**：`bin != 0` 就是這套工具認定的「判成真缺陷」
    # （`export/report._confusion` 的預設）。挑別的號碼的話 CLI 的 ground-truth
    # 那一行會說誤殺率 100%，而它下面兩行的純度表寫著相反的事。
    assert recipe.decide.tree.no.yes.bin == 0
    # 報表照 `score` 排，而 `score` 就是那個 worst —— 一個數字，不是兩個。
    assert recipe.decide.score == "worst"
    assert recipe.nodes["report"].params["rank_by"] == "score"


def test_it_tells_the_real_defects_from_the_nuisance(tmp_path):
    """整條路跑一次，而且**分得開** —— 這份 recipe 唯一的驗收條件。

    合成 RSEM（一半是真的）上實測 24 顆 23 中。這裡的門檻放在 80%：低於它
    就不是「調一下就好」，是這份 recipe 承諾的那件事沒有發生。
    """
    ds, gt = _rsem_lot(tmp_path)
    rows = run_batch(_rsem(tmp_path / "out"), ds, workers=1)
    assert all(r.get("ok") for r in rows), \
        [r.get("error") for r in rows if not r.get("ok")]

    assert {int(r["bin"]) for r in rows} <= {0, 1, 2, 9}
    assert all(int(r["features"]["decide_unanswered"]) == 0 for r in rows), \
        "每一題都答得出來 —— fill 與樹的順序在做的就是這件事"

    hit = sum(1 for r in rows
              if (int(r["bin"]) != 0)
              == bool(gt[str(r["defect_id"])]["is_real"]))
    assert hit >= 0.8 * len(rows), "%d/%d" % (hit, len(rows))
    # 真的那幾顆分數要**高**，而不只是「剛好落在對的一邊」。
    real = [float(r["features"]["score"]) for r in rows
            if gt[str(r["defect_id"])]["is_real"]]
    nuis = [float(r["features"]["score"]) for r in rows
            if not gt[str(r["defect_id"])]["is_real"]]
    assert max(real) > 3 * max(nuis)


def test_boxing_only_the_pattern_walks_straight_past_the_dark_defects(tmp_path):
    """**這一條是三張卡存在的理由**（`recipes/README.md` 的那張表）。

    暗缺陷掉在兩條之間的溝裡，而只鋪在圖案上的框正好從它旁邊跨過去 ——
    那一顆跑得完、有數字、每一格都正常。合成資料上實測：只鋪圖案 75%、
    三個都鋪 96%。

    所以這裡比的是**同一批資料、同一棵樹**，只有「鋪哪裡」不一樣。拿掉
    README 那張表的依據，就是拿掉這一條。
    """
    ds, gt = _rsem_lot(tmp_path)

    def _hits(keep):
        recipe = _rsem(tmp_path / "out")
        drop = [nid for nid, _r, _p in _PLACES if nid not in keep]
        for nid in drop:
            del recipe.nodes[nid]
        recipe.edges = [e for e in recipe.edges
                        if e.src not in drop and e.dst not in drop]
        recipe.routes["rsem"] = [n for n in recipe.routes["rsem"]
                                 if n not in drop]
        # ⚠ `roi` 那一格是**載入時從線水合出來的**（F42），所以砍掉線之後
        # 要跟著改 —— 不改的話 GLV 照樣要那三個區域，而它們已經沒人定義了。
        recipe.nodes["glv"].params["roi"] = ",".join(
            r for nid, r, _p in _PLACES if nid in keep)
        rows = run_batch(recipe, ds, workers=1)
        assert all(r.get("ok") for r in rows), \
            [r.get("error") for r in rows if not r.get("ok")]
        return sum(1 for r in rows
                   if (int(r["bin"]) != 0)
                   == bool(gt[str(r["defect_id"])]["is_real"]))

    only_pattern = _hits({"roi_on_pattern"})
    everywhere = _hits({nid for nid, _r, _p in _PLACES})
    assert everywhere > only_pattern, \
        "鋪滿整張圖沒有比只鋪圖案好（%d vs %d）—— 那三張卡就白放了" % (
            everywhere, only_pattern)


def test_the_report_it_writes_has_a_picture_for_every_defect(tmp_path):
    """整條路走到底：報表、CSV、圖、還有那份 recipe 的複本。

    ⚠ 這裡**沒有**斷言表格照分數排 —— 因為它不會。`rank_by`（「Worst
    first, by」）決定的是**哪幾顆有圖**（`limit` 那一刀），表格照的是檔案
    順序。help 講得很清楚（「otherwise the pictures come out in file
    order」），但 `limit = 0`（全部都有圖）時那句警告寫的是「put the name
    of a number ... if you want the worst at the top」—— 而那件事不會發生。
    2026-09-02 的驗收上量到的；留給使用者決定表格要不要跟著排。
    """
    ds, _gt = _rsem_lot(tmp_path)
    folder = tmp_path / "out"
    recipe = _rsem(folder)
    rows = run_batch(recipe, ds, workers=1)
    bctx = run_batch_steps(recipe, ds, rows, kind="rsem")
    assert not bctx.errors, bctx.errors

    html = (folder / "report.html").read_text(encoding="utf-8")
    for name in ("one box stands out", "more than one box is off",
                 "nothing stands out"):
        assert name in html, name
    assert (folder / "defects.csv").is_file()
    assert (folder / "recipe.json").is_file()

    # 每一顆都有一張圖，而圖上的標題帶著這一顆的分數與 bin。
    top = max(rows, key=lambda r: float(r["features"]["score"]))
    assert (folder / "images").is_dir()
    assert len(list((folder / "images").iterdir())) == len(rows)
    assert (folder / "images" /
            ("overlay_%s.jpg" % top["defect_id"])).is_file()
    assert html.count("data-img=") == len(rows), \
        "有一列點下去沒有圖 —— 報表跟圖是同一件事的兩半"



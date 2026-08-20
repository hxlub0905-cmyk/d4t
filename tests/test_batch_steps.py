# F16 Stage 5a：跨顆那一層（batch-level step）。
"""`run_defect` 一顆一顆跑、從不 raise（鐵則 7），所以任何「要看過整批才算得
出來」的東西以前都沒有地方放。四個需求卡在同一件事上：

* Output 的 CSV / KLARF / Report / HTML（一批一個檔案）
* 離群旗標（Tukey IQR、z-score —— 門檻由整批的分布決定）
* F15 欠的那份點對點 report
* `H2H` 的 `expect_dx_px` 建議值（整批取中位數）

先做機制，四個都便宜；不做機制，四個各自發明一套。

這一份鎖住的是機制本身的五條性質：

1. **跨顆卡不在 `run_defect` 裡跑**（那裡只有一顆），而且**跳過不是報錯** ——
   一份含 Output 卡的 recipe 在單顆預覽上仍然要跑得完（那是調參數的畫面）；
2. `run_batch_steps` 收齊之後跑它一次，拿得到整批的結果表；
3. **一張跨顆卡出錯不影響其他卡**（鐵則 7 的跨顆版）；
4. **試跑不寫**（使用者定調）—— 而那不是一個旗標，是「試跑那條路根本不叫
   `run_batch_steps`」；
5. Output 段的卡是 **end point**（不吐流、不吐特徵）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.export import report as export_report  # noqa: E402
from d4t.core.ingest.dataset import load_dataset  # noqa: E402
from d4t.core.pipeline import (  # noqa: E402
    BatchContext, get_step, run_batch, run_batch_steps, run_defect,
)
from d4t.core.pipeline.recipe import (  # noqa: E402
    Recipe, RecipeNode, ScoreSpec,
)
from d4t.core.pipeline.step import REGISTRY  # noqa: E402

KIND = "ebi_patch"


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("batchsteps")), n=4, seed=7)


@pytest.fixture(scope="module")
def dataset(lot):
    return load_dataset(lot["klarf"])


def _recipe(csv_path, **over):
    params = {"path": str(csv_path)}
    params.update(over)
    return Recipe(
        recipe_id="t", routes={KIND: ["load", "glv", "out"]},
        nodes={
            "load": RecipeNode("load", "load_patch", {}),
            "glv": RecipeNode("glv", "glv_stats",
                              {"source": "test", "metrics": "glv_max"}),
            "out": RecipeNode("out", "output_csv", params),
        },
        score=ScoreSpec(expr="glv_max", threshold=1.0,
                        bins={"below": 0, "above": 1}))


# --------------------------------------------------------------------------- #
# 1. 跨顆卡不在 run_defect 裡跑，而且跳過不是報錯
# --------------------------------------------------------------------------- #
def test_a_single_defect_run_skips_the_batch_card(dataset, tmp_path):
    """單顆預覽是**調參數的畫面** —— 一份含 Output 卡的 recipe 在那裡要跑得完。

    報錯的話，使用者一加上 Output 卡，預覽就整個壞掉（而他什麼都沒做錯）。
    """
    csv_path = tmp_path / "out.csv"
    res = run_defect(_recipe(csv_path), dataset.items[0], KIND)
    assert res.ok, res.error
    assert "glv_max" in res.features
    assert not csv_path.exists(), "單顆跑不該寫出任何東西"


def test_running_a_batch_card_the_per_defect_way_says_so(tmp_path):
    """哪天有人照普通 Step 的樣子叫它，症狀要是一句講得清楚的話，
    而不是「CSV 沒寫出來」。"""
    from d4t.core.pipeline.context import Context
    from d4t.core.pipeline.step import StepError

    with pytest.raises(StepError) as e:
        get_step("output_csv")().run(Context(images={}),
                                     {"path": str(tmp_path / "x.csv")})
    assert "once per defect" in str(e.value)


# --------------------------------------------------------------------------- #
# 2. run_batch_steps 拿得到整批
# --------------------------------------------------------------------------- #
def test_the_batch_card_sees_every_row_and_writes_once(dataset, tmp_path):
    csv_path = tmp_path / "out.csv"
    recipe = _recipe(csv_path)
    rows = run_batch(recipe, dataset, workers=1)
    assert len(rows) == len(dataset.items)
    assert not csv_path.exists(), "run_batch 自己不寫 —— 那是另一支的事"

    bctx = run_batch_steps(recipe, dataset, rows)
    assert bctx.errors == {}, bctx.errors
    assert bctx.outputs == [str(csv_path)]
    lines = csv_path.read_text(encoding="utf-8-sig").splitlines()
    assert len(lines) == len(rows) + 1          # 表頭 + 一顆一列
    assert "glv_max" in lines[0]


def test_it_is_byte_for_byte_what_the_export_path_already_produces(dataset,
                                                                   tmp_path):
    """**這一條是之後拿掉 Export 精靈的前提**：換一條路，東西不能變。

    兩邊呼叫的是同一支 `core/export/report.write_csv`，所以這裡驗的是「卡片沒有
    在中間偷改什麼」（例如只送成功的那幾顆、或重排欄位）。
    """
    a, b = tmp_path / "card.csv", tmp_path / "direct.csv"
    recipe = _recipe(a)
    rows = run_batch(recipe, dataset, workers=1)
    run_batch_steps(recipe, dataset, rows)
    export_report.write_csv(rows, str(b))
    assert a.read_bytes() == b.read_bytes()


def test_failed_defects_stay_in_the_table(dataset, tmp_path):
    """跑失敗的那幾顆**留在 CSV 裡**（`error` 欄就是為它們存在的）。

    只寫成功的那幾顆的話，「這批有幾顆沒跑起來」在報表上看不出來 ——
    而那正是使用者最需要知道的事之一。
    """
    csv_path = tmp_path / "out.csv"
    rows = [{"defect_id": "1", "ok": True, "error": "", "score": 1.0,
             "bin": 1, "features": {"glv_max": 5.0}},
            {"defect_id": "2", "ok": False, "error": "boom", "score": None,
             "bin": None, "features": {}}]
    bctx = run_batch_steps(_recipe(csv_path), dataset, rows)
    assert not bctx.errors
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "boom" in text
    assert len(text.splitlines()) == 3


# --------------------------------------------------------------------------- #
# 3. 一張跨顆卡出錯不影響其他卡（鐵則 7 的跨顆版）
# --------------------------------------------------------------------------- #
def test_one_batch_card_failing_does_not_stop_the_others(dataset, tmp_path):
    good = tmp_path / "good.csv"
    recipe = Recipe(
        recipe_id="t", routes={KIND: ["load", "bad", "good"]},
        nodes={
            "load": RecipeNode("load", "load_patch", {}),
            # 指到一個**資料夾** → IsADirectoryError → StepError。
            # （寫到不存在的資料夾**不是**錯誤：`write_csv` 會自己建它。）
            "bad": RecipeNode("bad", "output_csv", {"path": str(tmp_path)}),
            "good": RecipeNode("good", "output_csv", {"path": str(good)}),
        },
        score=ScoreSpec(expr="0", threshold=1.0,
                        bins={"below": 0, "above": 1}))
    rows = run_batch(recipe, dataset, workers=1)
    bctx = run_batch_steps(recipe, dataset, rows)
    assert "bad" in bctx.errors and "good" not in bctx.errors
    assert good.exists(), "一張卡出錯不該讓後面那張也不跑"
    assert bctx.outputs == [str(good)]


def test_a_disabled_batch_card_does_not_run(dataset, tmp_path):
    csv_path = tmp_path / "out.csv"
    recipe = _recipe(csv_path)
    recipe.nodes["out"].enabled = False
    rows = run_batch(recipe, dataset, workers=1)
    bctx = run_batch_steps(recipe, dataset, rows)
    assert bctx.outputs == [] and not csv_path.exists()


# --------------------------------------------------------------------------- #
# 4. 試跑不寫 —— 那不是旗標，是「那條路根本不叫它」
# --------------------------------------------------------------------------- #
def test_run_batch_alone_never_writes_anything(dataset, tmp_path):
    """使用者定調：「**試跑不寫，只有整批才寫**」。

    Studio 的 Run trial 是調參數的迴圈（拖門檻、改參數跟著跑），每拖一下就
    覆寫一次 KLARF 是不可逆的。把「寫出去」做成 `run_batch` 的一個旗標的話，
    那個旗標遲早有人忘記關 —— 做成另一支要自己叫的函式，試跑那條路就是根本
    沒叫它。這一條把那個結構鎖住。
    """
    csv_path = tmp_path / "trial.csv"
    run_batch(_recipe(csv_path), dataset, workers=1, limit=2)
    assert not csv_path.exists()


def test_the_studio_trial_path_does_not_call_the_batch_steps():
    """掃原始碼：`d4t/ui` 底下**不該有人**叫 `run_batch_steps`（目前）。

    掃字串是刻意的，跟 `test_ui_f15_pair_source` 掃 `sources=` 同一招：
    它擋得住「哪天有人順手在試跑那條路上加了它」——而那個改動的症狀是
    使用者拖一下門檻就覆寫一次輸出檔，沒有任何錯誤訊息。

    ⚠ Studio 之後會有自己的「跑整批並寫出」入口（見 docs/ROADMAP.md）。
    那一天這條測試要改成「只有那一個入口叫得到」，不是刪掉它。
    """
    ui = REPO / "d4t" / "ui"
    hits = [p.name for p in ui.glob("*.py")
            if "run_batch_steps" in p.read_text(encoding="utf-8")]
    assert hits == [], (
        "d4t/ui 底下叫了 run_batch_steps：%s。試跑不該寫出檔案 —— "
        "如果這是刻意的（Studio 的整批入口），請改這條測試並說明。" % hits)


# --------------------------------------------------------------------------- #
# 5. Output 段的卡是 end point
# --------------------------------------------------------------------------- #
def test_every_batch_card_declares_itself_properly():
    """自動套用到 registry 裡每一張跨顆卡。"""
    batch = [c for c in REGISTRY.values() if c.is_batch]
    assert batch, "一張跨顆卡都沒有 —— 這組測試沒測到什麼"
    for cls in batch:
        params = {p.name: p.default for p in cls.params}
        assert cls.resolve_writes(params) == [], cls.key
        assert cls.resolve_features(params) == [], cls.key
        assert cls.resolve_reads(params) == [], cls.key
        # 有實作 run_batch（沒實作的話 `Step.run_batch` 會丟 NotImplementedError）
        assert cls.run_batch is not REGISTRY["load_patch"].run_batch, cls.key


def test_nothing_configured_yet_points_at_the_field(tmp_path):
    card = get_step("output_csv")
    says = card.configuration_issues({"path": ""})
    assert says and "Write to" in says[0]
    # 指到一個資料夾（貼了路徑忘了加檔名）也要在跑之前講
    says = card.configuration_issues({"path": str(tmp_path)})
    assert says and "is a folder" in says[0]
    assert not card.configuration_issues({"path": str(tmp_path / "x.csv")})
    # **不存在的資料夾不算設定錯**：write_csv 會自己建它（精靈走同一支）
    assert not card.configuration_issues({"path": str(tmp_path / "new" / "x.csv")})


# --------------------------------------------------------------------------- #
# 6. F16 Stage 5b：Output 段的另外四張
# --------------------------------------------------------------------------- #
def _out_recipe(node_id, step, params):
    return Recipe(
        recipe_id="out", routes={KIND: ["load", "glv", node_id]},
        nodes={
            "load": RecipeNode("load", "load_patch", {}),
            "glv": RecipeNode("glv", "glv_stats",
                              {"source": "test", "metrics": "glv_max"}),
            node_id: RecipeNode(node_id, step, params),
        },
        score=ScoreSpec(expr="glv_max", threshold=1.0,
                        bins={"below": 0, "above": 1}))


def test_the_whole_output_section_is_end_points():
    """使用者：「他就是個 end point」—— 自動套用到這一段的每一張卡。"""
    section = [c for c in REGISTRY.values() if c.resolve_group() == "output"]
    assert len(section) >= 5, [c.key for c in section]
    for cls in section:
        params = {p.name: p.default for p in cls.params}
        assert cls.is_batch, "%s 不是 is_batch —— Output 段的卡都是" % cls.key
        assert cls.resolve_writes(params) == [] , cls.key
        assert cls.resolve_features(params) == [], cls.key
        assert cls.resolve_reads(params) == [], cls.key
        # 每一張都要在沒填路徑時講得出要填哪一格
        says = cls.configuration_issues(params)
        assert says and "Write to" in says[0], (cls.key, says)


def test_write_images_is_a_batch_card_even_though_it_is_per_defect(dataset,
                                                                   tmp_path):
    """它看起來是逐顆的 —— 但做成普通 Step 的話它會在 `run_defect` 裡跑，
    而那條路**每切換一顆 defect 就走一次**：使用者瀏覽 defect 時會一直寫
    PNG 出來。所以它也是整批跑完之後跑一次。"""
    folder = tmp_path / "pngs"
    recipe = _out_recipe("img", "output_image", {"folder": str(folder)})
    # 單顆跑：什麼都不該寫
    run_defect(recipe, dataset.items[0], KIND)
    assert not folder.exists()
    # 整批之後：一顆一張
    rows = run_batch(recipe, dataset, workers=1)
    bctx = run_batch_steps(recipe, dataset, rows)
    assert not bctx.errors, bctx.errors
    pngs = sorted(folder.glob("*.png"))
    assert len(pngs) == len(rows), [p.name for p in pngs]


def test_write_html_is_self_contained(dataset, tmp_path):
    """報表要能單獨寄給別人 —— 一個外部 .css 在轉寄的那一刻就不見了。"""
    path = tmp_path / "r.html"
    recipe = _out_recipe("html", "output_html", {"path": str(path)})
    rows = run_batch(recipe, dataset, workers=1)
    bctx = run_batch_steps(recipe, dataset, rows)
    assert not bctx.errors, bctx.errors
    text = path.read_text(encoding="utf-8")
    assert "<style>" in text and "link" not in text.lower().split("<body")[0]
    assert "glv_max" in text
    # 一顆一列 + 表頭
    assert text.count("<tr") == len(rows) + 1


def test_write_html_shows_the_defects_that_did_not_run(tmp_path, dataset):
    """少了的話，「這批有幾顆沒跑起來」在報表上看不出來。"""
    path = tmp_path / "r.html"
    rows = [{"defect_id": "1", "ok": True, "error": "", "score": 2.0,
             "bin": 1, "features": {"glv_max": 9.0}},
            {"defect_id": "2", "ok": False, "error": "boom", "score": None,
             "bin": None, "features": {}}]
    bctx = run_batch_steps(
        _out_recipe("html", "output_html", {"path": str(path)}), dataset, rows)
    assert not bctx.errors, bctx.errors
    text = path.read_text(encoding="utf-8")
    assert "did not run" in text and "boom" in text
    assert "(none)=1" in text


def test_write_klarf_says_so_when_there_is_no_klarf(tmp_path):
    """folder / tiff_stack 沒有 KLARF —— 那件事在載入的當下就講過了，
    這裡不要假裝是別的問題。"""
    class _NoKlarf:
        """一份沒有 KLARF 的資料集（folder / tiff_stack 就是這樣）。"""
        kind = KIND          # route 用 fixture 那一條，這條測的不是 route
        klarf = None
        items = []

    recipe = _out_recipe("kl", "output_klarf",
                         {"path": str(tmp_path / "x.001")})
    bctx = run_batch_steps(recipe, _NoKlarf(), [], kind=KIND)
    assert "kl" in bctx.errors
    assert "no KLARF" in bctx.errors["kl"]


def test_write_klarf_annotates_without_touching_the_original(dataset, tmp_path,
                                                             lot):
    """`annotate` 的承諾是「原檔不動」—— 那是使用者敢按下去的唯一理由。"""
    original = Path(lot["klarf"]).read_bytes()
    out = tmp_path / "annotated.001"
    recipe = _out_recipe("kl", "output_klarf",
                         {"mode": "annotate", "path": str(out)})
    rows = run_batch(recipe, dataset, workers=1)
    bctx = run_batch_steps(recipe, dataset, rows)
    assert not bctx.errors, bctx.errors
    assert out.exists()
    assert Path(lot["klarf"]).read_bytes() == original, "原檔被動到了"
    # 寫回是不可逆的，所以「改了幾列」要講出來
    assert any("row(s) changed" in w for w in bctx.warnings), bctx.warnings

# F51：UI 說會有的特徵名，要跟引擎真的寫出來的一樣（2026-08-28）。
"""**這一支是一把尺，不是一組案例。**

「誰產出這個特徵」在這個 repo 裡有三份實作：

===================================  ===============  ==========================
`engine._rescue_overwritten_features`  執行期（真相）   CSV / KLARF / 分數表達式
`verdict_features.bound_specs`         靜態預測         結果表分層、回溯面板
`viewmodel.feature_owners`             靜態預測（更弱） 淡線
===================================  ===============  ==========================

而 2026-08-28 實測發現**兩份預測跟真相都對不上**。一份放兩張 GLV 卡的
recipe 跑一次：

* UI 說會有 ``glv2_glv_pixels`` —— **引擎從來不寫**（幽靈欄）；
* 引擎寫出 ``glv_glv_max`` / ``glv_glv_mean`` / ``glv_glv_q99`` ——
  **UI 完全不知道**（結果表分不了組、篩不到、回溯面板指不到）。

方向反了：引擎救的是**被蓋掉的那一張**（先來的改名，後來的保留裸名），
而 `bound_specs` 讓先來的保留裸名、後來的改名，而且**只對診斷數字**這樣做。

> 跑得完、有數字、而且是錯的 —— 第八個，這次在顯示層。

所以這一支的做法是：**真的跑一次引擎**，拿它的 keys 當基準。
案例可以再加，但那把尺只有一把。
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
from d4t.core.ingest.dataset import load_dataset  # noqa: E402
from d4t.core.pipeline.batch import run_batch  # noqa: E402
from d4t.core.pipeline.recipe import Recipe  # noqa: E402
from d4t.core.pipeline.verdict_features import bound_specs  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "recipes" / "die_to_die_basic.json"


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("f51")), n=3, seed=7)


def _every_feature_computable(raw: dict) -> dict:
    """把 nm/px 填起來 —— **讓這份 recipe 宣告的每一個名字都真的算得出來**。

    ⚠ 不填的話尺就沒辦法要求「逐項相同」：F19 定的是**算不出來的那一格不寫**
    （`cd_*_nm` 要有 nm/px），於是引擎少那幾個名字，而 UI 照宣告預測 ——
    那個落差是**對的**，不是 bug。與其把尺放寬到「多出來的可以是宣告過的」
    （那條放寬正好也會放過真的發明出來的名字），不如**把落差的來源拿掉**。
    """
    from d4t.core.pipeline.step import REGISTRY

    out = json.loads(json.dumps(raw))
    for node in out["nodes"].values():
        cls = REGISTRY.get(str(node.get("step") or ""))
        if cls is None:
            continue
        # ⚠ **看卡片宣告，不看 JSON 有沒有那個鍵** —— recipe 省略預設值是
        # 合法的，所以「params 裡有 nm_per_px」跟「這張卡吃 nm_per_px」是
        # 兩件事。第一版問了 JSON，於是一個都沒設到，而尺照樣紅。
        if any(spec.name == "nm_per_px" for spec in cls.params):
            node.setdefault("params", {})["nm_per_px"] = 5.0
    return out


def _clone_card(raw: dict, src: str, dst: str) -> dict:
    """複製一張卡（連它的入線），讓它跟原本那張**撞名**。"""
    out = json.loads(json.dumps(raw))
    out["nodes"][dst] = dict(out["nodes"][src])
    for k, route in out["routes"].items():
        if src in route:
            out["routes"][k] = list(route) + [dst]
    for e in list(out.get("edges", [])):
        if e[2] == src:
            out["edges"].append([e[0], e[1], dst, e[3]])
    return out


def _engine_names(recipe: Recipe, lot) -> set:
    rows = run_batch(recipe, load_dataset(lot["klarf"]), workers=1)
    assert rows and rows[0].get("ok"), "前提：這份 recipe 真的跑得起來"
    names: set = set()
    for r in rows:
        names |= set((r.get("features") or {}).keys())
    return names


def _ui_names(recipe: Recipe, kind: str) -> set:
    return {b.spec.name for b in bound_specs(recipe, kind)}


# --------------------------------------------------------------------------- #
# 那把尺
# --------------------------------------------------------------------------- #
def _both(clone):
    raw = _every_feature_computable(
        json.loads(FIXTURE.read_text(encoding="utf-8")))
    if clone:
        raw = _clone_card(raw, clone, clone + "_2")
    return Recipe.from_json_dict(raw)


@pytest.mark.parametrize("clone", [None, "glv", "cd"])
def test_the_ui_predicts_exactly_what_the_engine_writes(lot, clone):
    """**兩邊逐項相同。**

    ``clone=None`` 是沒有撞名的基準線（證明修法沒有把好的那條路弄壞）。
    另外兩格各複製一張量測卡，製造撞名。

    兩個方向各講一句，因為它們壞掉的樣子完全不同：

    * **UI 有、引擎沒有** = 結果表上一欄永遠是空的（幽靈欄）；
    * **引擎有、UI 沒有** = 那個數字在 CSV 裡，但畫面上分不了組、篩不到、
      回溯面板指不到。
    """
    recipe = _both(clone)
    engine = _engine_names(recipe, lot)
    ui = _ui_names(recipe, "ebi_patch")

    ghosts = sorted(ui - engine)
    hidden = sorted(engine - ui)
    assert not ghosts, "UI 說有、引擎不寫（結果表上一欄永遠是空的）：%s" % ghosts
    assert not hidden, "引擎寫了、UI 不知道（分不了組、篩不到）：%s" % hidden


def test_the_bare_name_belongs_to_the_card_whose_value_wins(lot):
    """撞名時**裸名歸最後一張**，因為引擎是後寫的贏。

    這一條分開寫是因為上面那條只比名字的集合 —— 而「這個數字是誰算的」錯了
    的話，結果表會把它分到錯的卡底下，回溯面板也會跳到錯的卡。
    """
    recipe = _both("glv")
    owner = {b.spec.name: b.node_id for b in bound_specs(recipe, "ebi_patch")}

    bare = [n for n in owner if n.startswith("glv_") and "glv_glv" not in n]
    assert bare, "前提：這份 recipe 真的有 glv_* 的裸名"
    for name in bare:
        assert owner[name] == "glv_2", (
            "%s 的裸名掛在 %r 上，但引擎最後寫它的是 glv_2" % (name, owner[name]))


def test_feature_owners_is_a_projection_of_bound_specs(lot):
    """淡線那一份**不准是第三份實作** —— 它要從 `bound_specs` 長出來。

    第三份的代價實測過：`feature_owners` 知道 23 個名字、`bound_specs` 知道
    34 個，差的 11 個是救援名與引擎特徵（`score`、`decide_unanswered`）。
    於是最常見的那一條淡線 —— 報表照 `score` 排序 —— **一條都畫不出來**。
    """
    pytest.importorskip("PySide6")
    from d4t.ui.viewmodel import RecipeModel

    recipe = _both("glv")
    model = RecipeModel.from_recipe(recipe, kind="ebi_patch")

    owners = model.feature_owners()
    want = {b.spec.name: b.node_id for b in bound_specs(recipe, "ebi_patch")}
    assert owners == want

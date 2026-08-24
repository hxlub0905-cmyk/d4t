# F24 ⑤：「missing ⇒ 用 __」—— working number 一行吸收 feature_fill。
"""鎖住六條性質：

1. **嚴格附加**（鐵則 9）：沒有 ``fill`` 的 recipe —— JSON 沒有那個鍵、
   缺數字照舊整顆失敗（一個位元都沒變）。
2. fill 有值：缺了就用 fallback，``<name>_missing = 1``；量得到就照算，
   旗標寫 0 —— **有 fill 的行每顆都寫旗標**（CSV 那一欄才是完整的）。
3. 判定樹的第一步問 ``<name>_missing > 0`` 就能把補值的顆分去自己的托盤。
4. 壞的 fallback（不是數字）是 `bad-let` 的 error，跑起來訊息講得出人話。
5. 「跟整批比」的統計**排除這一行自己補過值的顆**（A1 的規矩延伸）。
6. serde round-trip 是 identity。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from d4t.core.pipeline import (  # noqa: E402
    Context, Recipe, RecipeNode, ScoreSpec, apply_lot_scaling, validate,
)
from d4t.core.pipeline.engine import _eval_decision  # noqa: E402
from d4t.core.pipeline.recipe import (  # noqa: E402
    DecideSpec, Let, Rule,
)

KIND = "ebi_patch"


def _recipe(lets, rules):
    return Recipe(
        recipe_id="t", routes={KIND: []}, nodes={},
        score=ScoreSpec(expr="", threshold=0.0, bins={"below": 0, "above": 1}),
        decide=DecideSpec(let=list(lets), rules=list(rules),
                          otherwise_bin=0, otherwise_label="", score=""))


def _ctx(**feats):
    ctx = Context()
    ctx.features.update({k: float(v) for k, v in feats.items()})
    return ctx


# --------------------------------------------------------------------------- #
# 1. 嚴格附加
# --------------------------------------------------------------------------- #
def test_no_fill_writes_no_such_key_and_still_fails_on_missing():
    r = _recipe([Let(name="c", expr="cd_deq * 2")],
                [Rule(when="c > 1", bin=1)])
    assert all("fill" not in x for x in r.to_json_dict()["decide"]["let"])
    with pytest.raises(Exception):
        _eval_decision(r, _ctx())            # cd_deq 缺 → 照舊爆（呼叫端收）


def test_fill_survives_the_json_round_trip():
    r = _recipe([Let(name="c", expr="cd_deq * 2", fill="-1")],
                [Rule(when="c > 1", bin=1)])
    d1 = r.to_json_dict()
    assert d1["decide"]["let"][0]["fill"] == "-1"
    assert Recipe.from_json_dict(d1).to_json_dict() == d1


# --------------------------------------------------------------------------- #
# 2.–3. 引擎
# --------------------------------------------------------------------------- #
def test_missing_input_takes_the_fallback_and_raises_the_flag():
    r = _recipe([Let(name="c", expr="cd_deq * 2", fill="-1")],
                [Rule(when="c_missing > 0", bin=9, label="not measurable"),
                 Rule(when="c > 1", bin=1)])
    ctx = _ctx()                             # cd_deq 缺
    _score, b = _eval_decision(r, ctx)
    assert ctx.features["c"] == -1.0
    assert ctx.features["c_missing"] == 1.0
    assert b == 9                            # 樹（規則）把補值的顆分去自己的托盤


def test_present_input_computes_and_writes_flag_zero():
    r = _recipe([Let(name="c", expr="cd_deq * 2", fill="-1")],
                [Rule(when="c_missing > 0", bin=9),
                 Rule(when="c > 1", bin=1)])
    ctx = _ctx(cd_deq=3.0)
    _score, b = _eval_decision(r, ctx)
    assert ctx.features["c"] == 6.0
    assert ctx.features["c_missing"] == 0.0  # 有 fill 的行每顆都寫旗標
    assert b == 1


def test_a_later_line_can_use_the_filled_value():
    r = _recipe([Let(name="c", expr="cd_deq * 2", fill="-1"),
                 Let(name="d", expr="c + 10")],
                [Rule(when="d > 5", bin=1)])
    ctx = _ctx()
    _eval_decision(r, ctx)
    assert ctx.features["d"] == 9.0          # -1 + 10：後面的行看到 fallback


# --------------------------------------------------------------------------- #
# 4. 壞的 fallback
# --------------------------------------------------------------------------- #
def test_a_non_numeric_fallback_is_a_lint_error_and_a_readable_failure():
    r = _recipe([Let(name="c", expr="cd_deq", fill="banana")],
                [Rule(when="c > 1", bin=1)])
    assert any(i.code == "bad-let" and i.level == "error"
               and "banana" in i.detail for i in validate(r))
    with pytest.raises(Exception) as e:
        _eval_decision(r, _ctx())
    assert "if missing" in str(e.value)


# --------------------------------------------------------------------------- #
# 5. 跟整批比：補值的顆不進統計
# --------------------------------------------------------------------------- #
def test_lot_scaling_skips_rows_this_line_filled():
    r = _recipe([Let(name="c", expr="cd_deq", scale="z", fill="-1")],
                [Rule(when="c > 1", bin=1)])

    def row(i, v, filled):
        return {"defect_id": str(i), "ok": True, "error": None,
                "score": v, "bin": 0,
                "features": {"c": float(v),
                             "c_missing": 1.0 if filled else 0.0,
                             **({} if filled else {"cd_deq": float(v)})}}

    rows = [row(1, 10.0, False), row(2, 12.0, False), row(3, 14.0, False),
            row(4, -1.0, True)]              # 補值的顆
    apply_lot_scaling(r, rows)
    # 統計只看 10/12/14（med=12、MAD=2）——補值的 -1 沒把中位數拖歪
    spread = 1.4826 * 2.0
    assert rows[0]["features"]["c"] == pytest.approx((10 - 12) / spread)
    assert rows[3]["features"]["c"] == pytest.approx((-1 - 12) / spread)


# --------------------------------------------------------------------------- #
# 6. viewmodel：fill 可編可 undo
# --------------------------------------------------------------------------- #
def test_the_model_edits_the_fill_and_undo_restores_it():
    from d4t.ui.viewmodel import RecipeModel

    m = RecipeModel()
    m.decide = DecideSpec(let=[Let(name="c", expr="cd_deq")],
                          rules=[Rule(when="c > 1", bin=1)],
                          otherwise_bin=0, otherwise_label="", score="")
    m.clear_history()
    m.set_let(0, fill="-1")
    assert m.decide.let[0].fill == "-1"
    m.undo()
    assert m.decide.let[0].fill == ""

# d4t tests — F21-B：算式那一格要說得出「有哪些數字、誰算的」
"""這一份鎖住的是 F21 實測掉出來的**最痛的那一項**。

第一次真的用 `feature_math` 的時候，痛的順序跟先前猜的相反：

    🔴 不知道有哪些數字可以用   ← 得跑 Python 呼叫 resolve_features() 才知道
                                  cmp_delta_median 存在
    🟡 量不到就整顆失敗          ← A1（feature_fill）已修
    🟢 看不出數字從哪來          ← 只有一張 glv 卡時一次都沒混淆過

所以測四件事：

1. `expr` 是一個**型別**，不是一個 `str`（值的格式一字不差，recipe JSON 不變）；
2. 那一格配得出「插入數字 ▾」，而且清單裡的每一項說得出**誰算的**；
3. **插進去的是名字，不是給人看的那一串** —— 插錯半邊的話使用者會得到一個
   永遠指不到的變數名，而錯誤要等跑起來才出現；
4. 拿不到清單的時候它**仍然是一個能填的文字框**（Studio 以外的宿主）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.step import PARAM_TYPES  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _form(dynamic=None):
    from d4t.ui.widgets import ParamForm
    f = ParamForm()
    f.set_step(get_step("feature_math").describe(), {"expr": "", "out": "value"},
               [], [], dynamic or {})
    return f


def _editor(form):
    """那一格的 (文字框, 下拉)。"""
    from PySide6.QtWidgets import QComboBox, QLineEdit
    row = form._rows["expr"]
    return row.findChild(QLineEdit), row.findChild(QComboBox)


# --------------------------------------------------------------------------- #
# 1. expr 是一個型別
# --------------------------------------------------------------------------- #
def test_expr_is_its_own_type_and_the_card_uses_it():
    assert "expr" in PARAM_TYPES
    spec = next(p for p in get_step("feature_math").params if p.name == "expr")
    assert spec.type == "expr"


def test_the_stored_value_is_still_just_a_string():
    """recipe JSON **一個位元都沒變** —— 差別只在 UI（同 `image_keys` 的先例）。"""
    card = get_step("feature_math")
    p = card.validate_params({"expr": "glv_max - glv_median", "out": "v"})
    assert p["expr"] == "glv_max - glv_median"
    assert isinstance(p["expr"], str)


# --------------------------------------------------------------------------- #
# 2. 清單說得出誰算的
# --------------------------------------------------------------------------- #
def test_the_picker_lists_the_numbers_and_who_works_them_out(qapp):
    form = _form({"features": ["cd_median\tCD", "glv_mad\tGray level"]})
    edit, combo = _editor(form)
    assert edit is not None and combo is not None
    shown = [combo.itemText(i) for i in range(combo.count())]
    assert any("cd_median" in t and "CD" in t for t in shown), shown
    assert any("glv_mad" in t and "Gray level" in t for t in shown), shown


def test_two_cards_of_the_same_kind_are_told_apart_by_who_works_them_out(qapp):
    """一份 recipe 可以有兩張 `Gray level`（量兩個區域）—— 名字自帶前綴的只有
    **撞名被蓋掉**的那一份（F17-②），所以清單上光看名字選不出要哪一個。"""
    from d4t.ui.widgets import split_labelled
    assert split_labelled("glv_mad\tGray level (epi)") == \
        ("glv_mad", "Gray level (epi)")
    assert split_labelled("glv_mad") == ("glv_mad", "")


# --------------------------------------------------------------------------- #
# 3. 插進去的是名字，不是給人看的那一串
# --------------------------------------------------------------------------- #
def test_choosing_one_puts_the_name_in_at_the_cursor(qapp):
    form = _form({"features": ["cd_median\tCD"]})
    edit, combo = _editor(form)
    got = {}
    form.param_edited.connect(lambda n, v: got.__setitem__(n, v))
    edit.setText("2 * ")
    edit.setCursorPosition(4)
    combo.setCurrentIndex(1)
    form._insert_feature(1, combo, edit, "expr")
    assert edit.text() == "2 * cd_median", edit.text()
    # **給人看的那一串不准進去** —— 那會是一個永遠指不到的變數名
    assert "—" not in edit.text() and "CD" not in edit.text().replace("cd_median", "")
    assert got.get("expr") == "2 * cd_median"


def test_the_picker_snaps_back_so_it_can_be_used_twice(qapp):
    form = _form({"features": ["a\tX", "b\tY"]})
    edit, combo = _editor(form)
    form._insert_feature(1, combo, edit, "expr")
    assert combo.currentIndex() == 0
    edit.setCursorPosition(len(edit.text()))
    form._insert_feature(2, combo, edit, "expr")
    assert edit.text() == "ab", edit.text()


# --------------------------------------------------------------------------- #
# 4. 沒有清單的時候仍然填得進去
# --------------------------------------------------------------------------- #
def test_with_no_list_it_is_still_a_working_text_box(qapp):
    form = _form({})
    edit, combo = _editor(form)
    got = {}
    form.param_edited.connect(lambda n, v: got.__setitem__(n, v))
    assert not combo.isEnabled(), "沒有清單時下拉要是停用的,而不是一個空選單"
    assert combo.itemText(0).strip(), "停用的那一格也要講一句為什麼"
    edit.setText("glv_max * 2")
    edit.textEdited.emit("glv_max * 2")
    assert got.get("expr") == "glv_max * 2"


def test_the_list_stops_at_this_card(qapp):
    """`labelled_features(upto_node=…)` 只列**這張卡之前**算得出來的數字。

    列出一個排在自己後面才算出來的數字，點下去就是一份跑起來每一顆都失敗的
    recipe（`available_features` 當初為 nm 那一組留的也是這句話）。
    """
    from d4t.ui.viewmodel import RecipeModel
    assert hasattr(RecipeModel, "labelled_features")
    import inspect
    assert "upto_node" in inspect.signature(
        RecipeModel.labelled_features).parameters


# --------------------------------------------------------------------------- #
# 5. 一張卡不能吃自己還沒寫的東西（實跑截圖抓到的）
# --------------------------------------------------------------------------- #
def test_a_card_does_not_offer_its_own_output(qapp):
    """`Feature math` 的清單裡出現過 `defect_score` —— 它自己要寫出去的名字。

    點下去就是 `defect_score = defect_score`。引擎擋得住
    （`unknown-feature-input`），但**讓使用者點一個保證壞掉的選項本身就是
    bug**（推廣鐵則）。這是把 Studio 跑起來、把選單印出來才看到的 ——
    元件測試看不到，因為清單是 Studio 填的。
    """
    from d4t.ui.viewmodel import RecipeModel
    m = RecipeModel()
    m.add_step("glv_stats")
    algo = m.add_step("feature_math")
    m.set_param(algo, "out", "defect_score")
    inclusive = [x.split("\t", 1)[0]
                 for x in m.labelled_features(upto_node=algo)]
    exclusive = [x.split("\t", 1)[0]
                 for x in m.labelled_features(upto_node=algo,
                                              include_upto=False)]
    assert "defect_score" in inclusive, "預設仍然含它自己（分數那一格要用）"
    assert "defect_score" not in exclusive, exclusive
    assert "glv_max" in exclusive, "上游的還是要在"


# --------------------------------------------------------------------------- #
# 6. 「守哪幾個數字」那一格也有同一支挑選器
# --------------------------------------------------------------------------- #
def _fill_form(dynamic=None):
    from d4t.ui.widgets import ParamForm
    f = ParamForm()
    f.set_step(get_step("feature_fill").describe(),
               {"features": "", "fill": 0.0}, [], [], dynamic or {})
    return f


def test_the_guard_card_has_the_same_picker(qapp):
    """`feature_fill` 的那一格是**同一個痛點** —— 昨天做的那張卡如果沒有挑選器，
    使用者一樣得先知道 `cd_deq` 這個名字才填得出來。"""
    from PySide6.QtWidgets import QComboBox, QLineEdit
    spec = next(p for p in get_step("feature_fill").params
                if p.name == "features")
    assert spec.type == "feature_keys"
    row = _fill_form({"features": ["cd_deq\tCD"]})._rows["features"]
    assert row.findChild(QLineEdit) is not None
    assert row.findChild(QComboBox) is not None


def test_a_list_appends_instead_of_inserting_at_the_cursor(qapp):
    """一串名字插在中間會把別人的名字剖成兩半 —— 所以它接在後面。"""
    from PySide6.QtWidgets import QComboBox, QLineEdit
    form = _fill_form({"features": ["cd_deq\tCD", "cd_area_px\tCD"]})
    row = form._rows["features"]
    edit, combo = row.findChild(QLineEdit), row.findChild(QComboBox)
    edit.setText("cd_min")
    edit.setCursorPosition(2)              # 游標在中間 —— 清單不理它
    form._insert_feature(1, combo, edit, "features", "feature_keys")
    assert edit.text() == "cd_min, cd_deq", edit.text()
    form._insert_feature(2, combo, edit, "features", "feature_keys")
    assert edit.text() == "cd_min, cd_deq, cd_area_px", edit.text()


def test_the_same_name_is_not_added_twice(qapp):
    from PySide6.QtWidgets import QComboBox, QLineEdit
    form = _fill_form({"features": ["cd_deq\tCD"]})
    row = form._rows["features"]
    edit, combo = row.findChild(QLineEdit), row.findChild(QComboBox)
    form._insert_feature(1, combo, edit, "features", "feature_keys")
    form._insert_feature(1, combo, edit, "features", "feature_keys")
    assert edit.text() == "cd_deq", edit.text()

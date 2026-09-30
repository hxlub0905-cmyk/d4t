# d4t — 「插入數字 ▾」一個下拉、三個家（2026-09-09）。
"""使用者：「Output card 中也要能夠連動 working numbers（其他類似要選
features 的也要能連動）」。

1. 設定區的 `feature_key` / `feature_keys` 那幾格用的是**同一支** picker
   （`ui/number_picker.py`），一張卡一組、每一項帶說明；
2. `feature_key`（單一個名字）**有**下拉 —— 以前它掉到純文字框；挑了就是
   換掉，不是插在游標處；
3. Output 卡的清單多列 working numbers；量測卡**不列**（判定在它之後才算）。

Qt 一律 lazy import（`tests/test_no_qt.py`）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from d4t.core.pipeline import get_step  # noqa: E402
from d4t.core.pipeline.recipe import DecideSpec, Let, TreeLeaf  # noqa: E402
from d4t.ui.viewmodel import RecipeModel  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    from d4t.ui import theme as theme_mod
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


def _model():
    m = RecipeModel()
    glv = m.add_step("glv_stats")
    m.set_param(glv, "output_prefix", "N")
    out = m.add_step("output_report")
    # Output 卡的清單只列它上游的數字（F123 期 3）—— GLV 接進來。
    m.add_edge(glv, out, src_out="numbers", dst_in="results")
    m.decide = DecideSpec(let=[Let(name="QAA", expr="N_glv_max * 2", fill="0")],
                          tree=TreeLeaf(bin=0))
    return m


def _pickers(form):
    from PySide6.QtWidgets import QComboBox
    return [c for c in form.findChildren(QComboBox)
            if c.itemText(0).startswith(("Insert a number", "No numbers"))]


def test_a_single_feature_field_has_a_picker_and_picking_replaces(qapp):
    from PySide6.QtWidgets import QLineEdit

    from d4t.ui.param_form import ParamForm
    f = ParamForm()
    f.set_step(get_step("output_report").describe(),
               {"rank_by": "glv_median"}, ["test"], [],
               {"features": ["glv_median\tGLV", "glv_max\tGLV"]})
    combos = _pickers(f)
    assert combos, "rank_by（feature_key）以前根本沒有下拉"
    combo = combos[0]
    got = {}
    f.param_edited.connect(lambda n, v: got.__setitem__(n, v))
    i = combo.findData("glv_max")
    combo.setCurrentIndex(i)
    combo.activated.emit(i)
    assert got.get("rank_by") == "glv_max", "單一個名字：挑了就是換掉，不是接在後面"
    edits = [e for e in f.findChildren(QLineEdit) if e.text() == "glv_max"]
    assert edits


def test_the_settings_picker_is_grouped_and_carries_tips(qapp):
    from PySide6.QtCore import Qt

    from d4t.ui.number_picker import number_tips
    from d4t.ui.param_form import ParamForm
    m = _model()
    f = ParamForm()
    f.number_info_provider = lambda: (number_tips(m), m.feature_regions())
    f.set_step(get_step("output_report").describe(), {}, ["test"], [],
               {"features": m.labelled_features() + m.decision_features()})
    combo = _pickers(f)[0]
    model = combo.model()
    texts = [combo.itemText(i) for i in range(combo.count())]
    heads = [i for i in range(1, combo.count())
             if not (model.flags(model.index(i, 0)) & Qt.ItemIsSelectable)]
    assert texts[heads[0]] == RecipeModel.DECISION_LABEL, texts[:4]
    assert get_step("glv_stats").label in [texts[h] for h in heads]
    i = combo.findData("QAA")
    assert i > 0
    assert str(model.data(model.index(i, 0), Qt.ToolTipRole)).startswith("= N_glv_max")


def test_output_cards_see_working_numbers_and_measure_cards_do_not(qapp):
    from d4t.ui import studio as studio_mod
    win = studio_mod.StudioWindow()
    try:
        m = _model()
        win._apply_model(m)
        ids = list(m.nodes)
        glv, out = m.nodes[ids[0]], m.nodes[ids[1]]
        assert m.nodes[ids[1]].step == "output_report"
        names = lambda node: [x.split("\t", 1)[0]  # noqa: E731
                              for x in win._dynamic_choices_for(node)["features"]]
        assert "QAA" in names(out) and "QAA_missing" in names(out)
        assert "N_glv_max" in names(out), "卡片算的還是要在"
        assert "QAA" not in names(glv), "量測卡列了判定段的名字 —— 點下去每一顆都失敗"
    finally:
        win.close()

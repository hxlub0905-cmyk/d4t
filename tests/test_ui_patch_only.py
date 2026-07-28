# F7-1 驗收：Studio 收斂成 patch-only（但 core 一行都沒少）。
"""Studio 目前只吃 EBI patch —— 而且是**收起來**，不是刪掉。

這支測試同時鎖住兩件事：

1. **GUI 真的收斂了**：卡片庫沒有 RSEM 專用卡、範本庫沒有純 rsem 的 recipe、
   載到 rsem 資料集會被擋下並講清楚原因。
2. **core 完全沒被動到**：兩張卡仍在 registry、RSEM ingest 仍然讀得出來、
   rsem recipe 仍然驗證得過。這一條才是重點 —— 使用者說的是「暫時」，
   所以「打開開關就回得來」必須是有測試保護的事實，不是口頭承諾。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "recipes"


def _import_qt(g):
    """把 Qt 與待測模組 import 進來（只在 fixture 裡呼叫，維持 lazy import 鐵則）。"""
    from PySide6.QtWidgets import QApplication

    from adept.ui import scope as scope_mod
    from adept.ui import studio as studio_mod
    from adept.ui import theme as theme_mod
    g.update(QApplication=QApplication, scope_mod=scope_mod,
             studio_mod=studio_mod, theme_mod=theme_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture(scope="module")
def patch_lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("f7_patch")), n=6, seed=7)


@pytest.fixture(scope="module")
def rsem_lot(tmp_path_factory):
    from make_sample_rsem import generate
    return generate(str(tmp_path_factory.mktemp("f7_rsem")), n=4, seed=11)


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. GUI 收斂了
# --------------------------------------------------------------------------- #
def test_rsem_only_cards_are_not_in_the_library(window):
    for key in scope_mod.HIDDEN_STEPS:
        assert window.library.entry(key) is None, \
            "%s 是 RSEM 專用卡，patch-only 期間不該出現在卡片庫" % key
    # 其他卡照常在
    for key in ("load_patch", "align", "subtract", "snr_map", "glv_stats"):
        assert window.library.entry(key) is not None


def test_loading_an_rsem_dataset_is_refused_with_a_reason(window, rsem_lot,
                                                          patch_lot):
    # 先載一份正常的 patch，等一下要確認它不會被弄丟
    assert window.load_dataset_path(patch_lot["klarf"], sync=True) is True
    before = window.dataset

    assert window.load_dataset_path(rsem_lot["klarf"], sync=True) is False
    msg = window.status_text()
    assert "EBI patch" in msg and "rsem" in msg
    assert "python -m adept run" in msg, "要講得出替代路徑，不能只是拒絕"
    assert window.dataset is before, "被擋下來時不該動到使用者手上的資料集"


def test_template_library_hides_rsem_only_recipes(window):
    dlg = window.open_recipe_library()
    listed = [e["recipe_id"] for e in dlg.entries()]

    assert "rsem_golden_cell" not in listed, "純 rsem 的範本要收起來"
    assert "die_to_die_basic" in listed
    # 雙 route 的照列：載進來會走 ebi_patch，完全跑得動
    assert "dual_route_basic" in listed


def test_a_dual_route_template_loads_into_the_patch_route(window, patch_lot):
    window.load_dataset_path(patch_lot["klarf"], sync=True)
    assert window.load_recipe_path(str(EXAMPLES / "dual_route_basic.json"),
                                   sync=True) is True
    assert window.model.kind == "ebi_patch"
    assert window.run_trial(6, workers=1, sync=True) is True
    assert len(window.trial_scores) == 6


# --------------------------------------------------------------------------- #
# 2. core 完全沒被動到（「打開開關就回得來」）
# --------------------------------------------------------------------------- #
def test_hidden_cards_are_still_registered_and_runnable():
    """只是不列在 UI 上；registry、參數驗證、既有 recipe 全都照舊。"""
    from adept.core.pipeline import get_step
    import adept.core.steps  # noqa: F401

    for key in ("golden_cell", "cell_period"):
        step = get_step(key)
        assert step.key == key
        assert step.validate_params({}), "預設參數要還驗證得過"


def test_rsem_ingest_and_recipe_still_work(rsem_lot):
    """core 不知道 UI 收斂這件事 —— RSEM 從 ingest 到驗證整條都還在。"""
    from adept.core.ingest.dataset import load_dataset
    from adept.core.pipeline import Recipe, validate

    ds = load_dataset(rsem_lot["klarf"])
    assert ds.kind == "rsem" and len(ds.items) == 4

    recipe = Recipe.load(str(EXAMPLES / "rsem_golden_cell.json"))
    issues = [i for i in validate(recipe, kind="rsem") if i.level == "error"]
    assert not issues, issues


def test_period_module_is_not_orphaned():
    """``algo/period.py`` 看起來只有 Golden Cell 在用，但它是之後做
    pattern-frame ROI 的唯一工具（F7 §4）—— 這條測試就是那張便利貼。"""
    from adept.core.algo import period

    assert hasattr(period, "estimate_period")
    assert hasattr(period, "choose_origin"), \
        "choose_origin 的相位搜尋是 M4 補完原專案 stub 的成果，不要刪"


def test_turning_rsem_back_on_is_one_constant(qapp, monkeypatch, rsem_lot):
    """把 'rsem' 加進 SUPPORTED_KINDS 就該整條路線回來 —— 用測試證明它是真的。"""
    monkeypatch.setattr(scope_mod, "SUPPORTED_KINDS", ("ebi_patch", "rsem"))
    monkeypatch.setattr(scope_mod, "HIDDEN_STEPS", ())

    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.library.entry("golden_cell") is not None
        assert win.load_dataset_path(rsem_lot["klarf"], sync=True) is True
        assert win.dataset.kind == "rsem"
        dlg = win.open_recipe_library()
        assert "rsem_golden_cell" in [e["recipe_id"] for e in dlg.entries()]
    finally:
        win.close()

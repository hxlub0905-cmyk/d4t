# F11 Input-3 驗收：Studio 吃四種輸入（原 F7-1 的 patch-only 鎖）。
"""**一種 source 一個入口**（使用者定調 2026-08-17：「source 不一樣本來就要分」）。

這個檔案原本叫 `test_ui_patch_only.py`，鎖的是相反的事：Studio 只吃 EBI patch，
載到 rsem 會被擋下來。F7-1 那一輪的用字是「**暫時**只支援 patch」，而做法是
**收起來、不刪掉** —— 於是這一輪要打開時，改的是 `scope.py` 的兩個常數，
`ingest` / `golden_cell` / `algo/period.py` 一行都沒動。

**那個判斷現在被驗證了，所以這支測試換一個方向鎖同一件事**：

1. 四種 kind 都進得來（`ebi_patch` / `rsem` / `tiff_stack` / `folder`），
   而每一種有自己的入口；
2. 沒有 KLARF 的那兩種**當場講**「寫不回 KLARF」；
3. 收起來的機制還在（`HIDDEN_STEPS` 空著但 `visible_steps()` 照樣管用）——
   下一次要暫時藏一張卡時，加一個字串就好；
4. `algo/period.py` 仍然不是孤兒（那張便利貼留著）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import first_source  # noqa: E402

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
# 1. 四種輸入都進得來
# --------------------------------------------------------------------------- #
def test_all_four_kinds_are_supported():
    from adept.ui import scope          # Qt-free，不必等 qapp
    for kind in ("ebi_patch", "rsem", "tiff_stack", "folder"):
        assert scope.is_supported_kind(kind), kind
    assert not scope.is_supported_kind("something_else")


def test_the_single_image_cards_are_in_the_library_now(window):
    """`golden_cell` / `cell_period` 回來了 —— 它們是單張那條路**唯一**的 ref 來源。

    收著它們的理由是「Studio 只吃兩兩成對的 patch」。那個前提沒了，繼續收著
    就等於把功能打開一半。
    """
    for key in ("golden_cell", "cell_period", "load_patch", "align", "subtract"):
        assert window.library.entry(key) is not None, key


def test_an_rsem_dataset_loads_instead_of_being_refused(window, rsem_lot):
    """以前這一條斷言的是**被擋下來**。現在它要真的載進去。"""
    assert window.load_dataset_path(rsem_lot["klarf"], sync=True) is True
    assert window.dataset.kind == "rsem"
    assert len(window.dataset.items) > 0
    # route 跟著資料走（空流程時）——不然使用者加的卡會落在 ebi_patch 那條 route
    assert window.model.kind == "rsem"


def test_a_folder_of_images_loads(window, tmp_path):
    import numpy as np
    from adept.core.ingest import imageio
    for i in range(3):
        imageio.save_gray(str(tmp_path / ("d%d.png" % i)),
                          np.full((16, 16), 20 * (i + 1), np.uint8))
    assert window.load_folder_path(str(tmp_path), sync=True) is True
    assert window.dataset.kind == "folder"
    assert len(window.dataset.items) == 3


def test_the_two_kinds_without_a_klarf_say_so_where_it_stays(window, tmp_path):
    """沒有 KLARF ⇒ 寫不回 KLARF，而那句話掛在資料集標籤上（常駐）。"""
    import numpy as np
    from adept.core.ingest import imageio
    imageio.save_gray(str(tmp_path / "d1.png"), np.full((16, 16), 30, np.uint8))
    window.load_folder_path(str(tmp_path), sync=True)
    assert "no KLARF" in window.defect_label.text()


def test_an_unknown_kind_is_still_refused_with_a_reason(window, patch_lot,
                                                       monkeypatch):
    """開關還是開關：把 `ebi_patch` 拿掉，它就該被擋下來並講得出替代路徑。"""
    assert window.load_dataset_path(patch_lot["klarf"], sync=True) is True
    before = window.dataset
    monkeypatch.setattr(scope_mod, "SUPPORTED_KINDS", ("rsem",))
    monkeypatch.setattr(studio_mod, "is_supported_kind",
                        scope_mod.is_supported_kind)
    assert window.load_dataset_path(patch_lot["klarf"], sync=True) is False
    assert "python -m adept run" in window.status_text(), \
        "要講得出替代路徑，不能只是拒絕"
    assert window.dataset is before, "被擋下來時不該動到使用者手上的資料集"


def test_the_hide_a_card_mechanism_still_works(window):
    """`HIDDEN_STEPS` 空了，但機制要留著 —— 下次要暫時藏一張卡時加一個字串就好。"""
    steps = [{"key": "load_patch"}, {"key": "golden_cell"}]
    assert scope_mod.visible_steps(steps) == steps        # 現在什麼都不藏
    import adept.ui.scope as s
    keep = s.HIDDEN_STEPS
    try:
        s.HIDDEN_STEPS = ("golden_cell",)
        assert [d["key"] for d in s.visible_steps(steps)] == ["load_patch"]
    finally:
        s.HIDDEN_STEPS = keep


def test_the_single_image_cards_are_registered_and_runnable():
    """registry、參數驗證、既有 recipe 全都照舊（這一條沒有變）。"""
    from adept.core.pipeline import get_step
    import adept.core.steps  # noqa: F401

    for key in ("golden_cell", "cell_period"):
        step = get_step(key)
        assert step.key == key
        assert step.validate_params({}), "預設參數要還驗證得過"


def test_period_module_is_not_orphaned():
    """``algo/period.py`` 看起來只有 Golden Cell 在用，但它是之後做
    pattern-frame ROI 的唯一工具（F7 §4）—— 這條測試就是那張便利貼。"""
    from adept.core.algo import period

    assert hasattr(period, "estimate_period")
    assert hasattr(period, "choose_origin"), \
        "choose_origin 的相位搜尋是 M4 補完原專案 stub 的成果，不要刪"




def test_switching_route_repaints_the_canvas(window, rsem_lot):
    """**換 kind 必須重畫。**

    `model.kind` 是直接設的屬性、不會通知 listener，而畫布的輸出埠是照 kind 算
    的。少了那一次重畫，載一份 rsem 資料之後畫布上還留著 patch 的 `test` / `ref`
    兩顆埠 —— 而資料只有一條 `single`。使用者回報的「畫布跟實際對不起來」第一層
    就是這個（第二層是 Input 卡還沒按 source 拆開，見計畫書 §3.1.13）。
    """
    window.load_dataset_path(rsem_lot["klarf"], sync=True)
    nid = first_source(window)
    ports = window.pipeline.node_item(nid).out_names()
    assert "ref" not in ports, ports          # patch 的 ref 不該還在畫布上
    assert "single" in ports

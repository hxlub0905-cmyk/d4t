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
3. 收起來的機制還在（`HIDDEN_STEPS` 現在收著 `align`，見 §4）——
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

    from d4t.ui import scope as scope_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
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
    from d4t.ui import scope          # Qt-free，不必等 qapp
    for kind in ("ebi_patch", "rsem", "tiff_stack", "folder"):
        assert scope.is_supported_kind(kind), kind
    assert not scope.is_supported_kind("something_else")


def test_the_single_image_cards_are_in_the_library_now(window):
    """單張那條路要有自己的載入卡與量測卡。

    2026-08-18：這一條原本點的是 `golden_cell` / `cell_period`，後來改點
    `pattern_ref` —— 而那一張 2026-08-20 刪掉了（見
    `test_pattern_ref_is_gone_and_nothing_quietly_replaced_it`）。現在點的是
    單張那條路**真正在用**的四張：載入、找區域（大圖上鋪 ROI 也是它）、
    Gray level（`method="compare"` 就是以前的 Compare regions）、相減。
    """
    for key in ("load_single", "roi_reference", "glv_stats", "subtract"):
        assert window.library.entry(key) is not None, key
    # `align` 曾經在這一列上。2026-08-18 使用者把它收起來了 ——
    # 見 test_align_is_hidden_but_still_runs。
    # `golden_cell` / `cell_period` 也曾經在這一列上 —— 見
    # test_the_golden_cell_cards_are_gone_for_good（一張刪了、一張改了名）。


def test_an_rsem_dataset_loads_instead_of_being_refused(window, rsem_lot):
    """以前這一條斷言的是**被擋下來**。現在它要真的載進去。"""
    assert window.load_dataset_path(rsem_lot["klarf"], sync=True) is True
    assert window.dataset.kind == "rsem"
    assert len(window.dataset.items) > 0
    # route 跟著資料走（空流程時）——不然使用者加的卡會落在 ebi_patch 那條 route
    assert window.model.kind == "rsem"


def test_a_folder_of_images_loads(window, tmp_path):
    import numpy as np
    from d4t.core.ingest import imageio
    for i in range(3):
        imageio.save_gray(str(tmp_path / ("d%d.png" % i)),
                          np.full((16, 16), 20 * (i + 1), np.uint8))
    assert window.load_folder_path(str(tmp_path), sync=True) is True
    assert window.dataset.kind == "folder"
    assert len(window.dataset.items) == 3


def test_the_two_kinds_without_a_klarf_say_so_where_it_stays(window, tmp_path):
    """沒有 KLARF ⇒ 寫不回 KLARF，而那句話掛在資料集標籤上（常駐）。"""
    import numpy as np
    from d4t.core.ingest import imageio
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
    assert "python -m d4t run" in window.status_text(), \
        "要講得出替代路徑，不能只是拒絕"
    assert window.dataset is before, "被擋下來時不該動到使用者手上的資料集"


def test_align_is_hidden_but_still_runs(window):
    """使用者 2026-08-18：「我不喜歡 align 卡……拉 align 反而會飄掉 shift」。

    **收起來、不刪掉**（CLAUDE.md §5 的判斷）：卡片庫看不到它，但已經在用它的
    recipe 照跑、CLI 照跑、黃金值一個字不動 —— 而
    `tests/fixtures/recipes/dual_route_basic.json` 正好用了它，撐著三組黃金值裡
    的兩組。刪掉的話那兩組要重新定錨，而使用者說的是「之後真需要我再回來」。
    """
    from d4t.core.pipeline import get_step

    assert "align" in scope_mod.HIDDEN_STEPS
    assert window.library.entry("align") is None      # 卡片庫看不到
    assert get_step("align") is not None              # 但引擎照樣認得
    assert window.model.add_step("align")             # 舊 recipe 也放得進來


def test_pattern_ref_is_gone_and_nothing_quietly_replaced_it(window):
    """使用者 2026-08-20（F16）：「Compare 中 pattern_ref 這項功能完全沒用，
    請直接拿掉」——**這一次是刪掉，不是收起來**。

    這張卡走完了這個 repo 的四種下場：刪掉（`golden_cell`，2026-08-18 早上）→
    量代價（rsem route 24/24 → 12/24）→ 要回來並改名（`pattern_ref`）→
    收起來（同日晚間）→ **刪掉**（今天）。判準每一次都是使用者說的那句話。

    代價這一次**真的付了**：`dual_route_basic.json` 的 rsem route 因此重做成
    「直接量單張影像」，而 `tests/test_e2e_dual_route.py` 的 rsem 斷言從準確率
    改成「跑得完、算得出分數」。那個 24/24 的證據沒有了 —— 這一條連同它一起
    釘住，免得哪天有人看到那份 fixture 以為它還在證明什麼。
    """
    from d4t.core.pipeline import Recipe, validate
    from d4t.core.pipeline.step import REGISTRY

    assert "pattern_ref" not in REGISTRY
    assert "pattern_ref" not in scope_mod.HIDDEN_STEPS     # 不是收起來，是不在了
    assert window.library.entry("pattern_ref") is None

    # 那份 fixture 照樣開得起來、照樣沒有錯 —— 但它已經不含這張卡。
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    recipe = Recipe.load(os.path.join(here, "fixtures", "recipes",
                                      "dual_route_basic.json"))
    assert not any(n.step == "pattern_ref" for n in recipe.nodes.values())
    assert not [i for i in validate(recipe, kind="rsem") if i.level == "error"]
    # 而且沒有別的卡偷偷接手「造一張 ref」—— rsem 那條 route 現在就是沒有 ref。
    assert not any("ref" in REGISTRY[n.step].resolve_writes(n.params)
                   for n in recipe.nodes.values()
                   if n.id in recipe.routes["rsem"] and n.step in REGISTRY)


def test_the_hide_a_card_mechanism_still_works(window):
    """機制本身要留著 —— 下次要暫時藏別張卡時加一個字串就好。"""
    steps = [{"key": "load_patch"}, {"key": "subtract"}]
    assert scope_mod.visible_steps(steps) == steps        # 這兩張都沒被藏
    import d4t.ui.scope as s
    keep = s.HIDDEN_STEPS
    try:
        s.HIDDEN_STEPS = ("subtract",)
        assert [d["key"] for d in s.visible_steps(steps)] == ["load_patch"]
    finally:
        s.HIDDEN_STEPS = keep


def test_the_golden_cell_family_is_gone_for_good():
    """那一家的三個 key 現在一個都不在 registry 裡了。

    走過的路（時間序）：

    * `cell_period` —— 2026-08-18 **刪掉**（使用者：「不需要這功能」）。
    * `golden_cell` —— 同日先刪，看了代價的數字之後要回來並**改名**成
      `pattern_ref`（「那可能要拿回來 不過要改名字 不然會誤會」），當晚收起來。
    * `pattern_ref` —— 2026-08-20 **刪掉**（「完全沒用，請直接拿掉」）。

    ⚠ **演算法一層仍然沒動**，而且現在更容易被誤刪：`algo/golden.py` 與
    `algo/period.py` 的呼叫者只剩 `algo/template.py` 一個（Template 卡疊
    Golden Cell 模板時要用）。只剩一個呼叫者的模組正是最容易被當成死碼清掉的
    那一種 —— 這一條與下一條 (`test_period_module_is_not_orphaned`) 是那張便利貼。
    """
    from d4t.core.pipeline.step import REGISTRY
    import d4t.core.steps  # noqa: F401

    for key in ("golden_cell", "cell_period", "pattern_ref"):
        assert key not in REGISTRY, key

    from d4t.core.algo import golden, template
    assert hasattr(golden, "stack_cells")
    assert hasattr(template, "build_golden_cell"), \
        "Template 卡的 golden cell 疊圖還在用 algo/golden.py"


def test_period_module_is_not_orphaned():
    """``algo/period.py`` 看起來只有 Golden Cell 在用，但它是之後做
    pattern-frame ROI 的唯一工具（F7 §4）—— 這條測試就是那張便利貼。"""
    from d4t.core.algo import period

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

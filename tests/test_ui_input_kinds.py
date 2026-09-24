# F11 Input-3 驗收：Studio 吃四種輸入（原 F7-1 的 patch-only 鎖）。
"""**一種 source 一個入口**（使用者定調 2026-08-17：「source 不一樣本來就要分」）。

這個檔案原本叫 `test_ui_patch_only.py`，鎖的是相反的事：Studio 只吃 EBI patch，
載到 rsem 會被擋下來。F7-1 那一輪的用字是「**暫時**只支援 patch」，而做法是
**收起來、不刪掉** —— 於是這一輪要打開時，改的是 `scope.py` 的兩個常數，
`ingest` / `golden_cell` / `algo/period.py` 一行都沒動。

**那個判斷現在被驗證了，所以這支測試換一個方向鎖同一件事**：

1. `SUPPORTED_KINDS` 上的每一種都進得來，而每一種有自己的入口
   （⚠ **不寫死那張清單** —— F114 拿掉 `tiff_stack` 時付過這筆錢）；
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
# 1. 支援的輸入都進得來，而且每一種都有入口
# --------------------------------------------------------------------------- #
def test_every_supported_kind_is_supported_and_has_a_way_in():
    """**這一條刻意不寫死任何一種 kind 的名字。**

    它本來抄著 `("ebi_patch", "rsem", "tiff_stack", "folder")`，而 2026-09-18
    （F114）使用者把 stack 拿掉（「我們用不到」）的那一刻，這支測試紅了 ——
    紅得沒有道理：**壞掉的不是「支援的 kind 都進得來」這個機制**，只是那張清單
    短了一個。把值抄進測試裡的下場，是每一次產品範圍的決定都要順手改一次測試
    （`test_ui_scope_profiles.py` 付過同一筆錢）。

    問的改成機制本身：`SUPPORTED_KINDS` 上的每一種都要 (a) 被認得、(b) **有一個
    入口打得開**。少了 (b) 就是「支援一種使用者點不到的資料」。
    """
    from d4t.ui import scope          # Qt-free，不必等 qapp

    assert scope.SUPPORTED_KINDS, "一種都不支援的話這支測試問不出任何事"
    reachable = {k for src in scope.INPUT_SOURCES for k in src.kinds}
    for kind in scope.SUPPORTED_KINDS:
        assert scope.is_supported_kind(kind), kind
        assert kind in reachable, (
            "%s 在 SUPPORTED_KINDS 上，但沒有任何一個 INPUT_SOURCES 打得開它"
            % kind)
    assert not scope.is_supported_kind("something_else")


def test_the_single_image_cards_are_in_the_library_now(window):
    """單張那條路要有自己的載入卡與量測卡。

    2026-08-18：這一條原本點的是 `golden_cell` / `cell_period`，後來改點
    `pattern_ref` —— 而那一張 2026-08-20 刪掉了（見
    `test_pattern_ref_is_gone_and_nothing_quietly_replaced_it`）。現在點的是
    單張那條路**真正在用**的四張：載入、找區域（大圖上鋪 ROI 也是它）、
    Gray level（`method="compare"` 就是以前的 Compare regions）、相減。
    """
    # 載入卡：F11 起是 `load_single`，F121 期 2 併回 Input（`load_patch`）。
    for key in ("load_patch", "roi_reference", "glv_stats", "subtract"):
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


def test_one_image_on_its_own_loads_as_a_single_defect(window, tmp_path):
    """F85：**一張大圖**那條路 —— 不必先把它放進一個資料夾。"""
    import numpy as np
    from d4t.core.ingest import imageio
    f = tmp_path / "field.png"
    imageio.save_gray(str(f), np.full((32, 48), 90, np.uint8))
    assert window.load_image_path(str(f), sync=True) is True
    assert window.dataset.kind == "folder"        # 形狀相同，不新增一種 kind
    assert len(window.dataset.items) == 1
    assert window.dataset.items[0].defect_id == "field"
    # 沒有 KLARF ⇒ 寫不回 —— 那句話跟另外兩條路走同一個地方（常駐標籤）
    assert "no KLARF" in window.defect_label.text()


def test_opening_something_that_is_not_an_image_says_so(window, tmp_path):
    """副檔名不認得 → **零顆 defect 加一句講得出原因的話**，不是當機。

    形狀刻意跟 `load_folder`「資料夾裡沒有影像」那一種**逐項相同**（0 顆
    加一句 warning）—— 兩條路的資料形狀本來就一樣，錯誤的形狀不一樣的話，
    下游每一段都要各認一種。
    """
    from d4t.core.ingest import load_image_file
    f = tmp_path / "notes.txt"
    f.write_text("not an image", encoding="utf-8")
    ds = load_image_file(str(f))
    assert ds.kind == "folder" and ds.items == []
    assert ds.warnings and "Not an image file" in ds.warnings[0]
    # 那句話要**指得出該用什麼副檔名** —— 「不行」而不說為什麼是推廣鐵則擋的
    assert ".png" in ds.warnings[0]


def test_opening_a_file_that_is_not_there_does_not_crash(window, tmp_path):
    missing = tmp_path / "missing.png"
    assert window.load_image_path(str(missing), sync=True) is False
    from d4t.core.ingest import load_image_file
    ds = load_image_file(str(missing))
    assert ds.items == [] and "Not a file" in ds.warnings[0]


def test_a_multipage_tiff_opened_as_one_image_says_where_to_go(tmp_path):
    """多頁 TIFF 走這條路只讀得到第 0 頁 —— 那件事以前完全沒有聲音。

    ⚠ 那句話**跟 `load_folder` 共用一份**（`_MULTIPAGE_WARNING`）。抄成兩份
    的那天，其中一份會停在舊的去處，而使用者照著它走會到一個不存在的入口。
    """
    import numpy as np
    import tifffile

    from d4t.core.ingest import dataset as ds_mod
    f = tmp_path / "stack.tif"
    # 明寫 photometric —— 不寫的話 tifffile 把 (3, h, w) 當成 RGB 的三個
    # 分量平面（一頁），而這條測試問的正是「有幾頁」。
    tifffile.imwrite(str(f), np.zeros((3, 8, 8), np.uint8),
                     photometric="minisblack")
    ds = ds_mod.load_image_file(str(f))
    assert len(ds.items) == 1                      # 仍然載得進來
    assert ds.warnings and "image stack" in ds.warnings[0]
    # **兩條路講的是同一句話** —— 這一條就是那份唯一出處的防線：
    # 同一個檔案，`Open image…` 與 `Open folder…` 的警告逐字相同。
    same = ds_mod.load_folder(str(tmp_path))
    assert same.warnings == ds.warnings


def test_every_entry_is_on_the_one_table_that_grows_the_buttons():
    """加一個入口＝改 `INPUT_SOURCES`，不動 UI（`CLAUDE.md` §5）。

    工具列那顆鈕、空白狀態那一列、以及它的處理函式全部從這張表長出來，
    所以這一條同時守住三個地方 —— 少接一個的下場實測過（F11 Input-5：
    `layout(GDS)` 的入口鈕根本沒被 addWidget 到工具列上）。

    ⚠ **2026-09-18（F114-2）起這一條不點名任何一個 key。** 它本來叫
    `..._the_image_entry_...` 並寫死 `key == "image"`，而那一輪五顆入口併成
    三顆（`folder`／`image`／`raw` → 一顆 `Open images…`）的時候它就紅了 ——
    紅得沒道理：壞掉的不是「入口從一張表長出來」這個機制。這已經是這幾輪
    第四次付同一筆錢（見 `test_ui_scope_profiles.py` 與這一份上面那條）。
    """
    from d4t.ui import open_dialogs

    assert scope_mod.INPUT_SOURCES, "一個入口都沒有的話這支測試問不出任何事"
    for src in scope_mod.INPUT_SOURCES:
        assert src.kinds, "%s 沒有說它開得出哪一種 kind" % src.key
        for kind in src.kinds:
            assert scope_mod.is_supported_kind(kind), (
                "`%s` 開的是 `%s`，而那一種不在 SUPPORTED_KINDS 上" %
                (src.key, kind))
        assert src.title.strip() and src.what.strip(), src.key
        # ⚠ 問的是機制，不是那一支方法：以前一種入口一支
        # `StudioWindow._on_open_<key>`，而那正好讓上面那句話（「改一張表就好」）
        # **在程式碼裡是假的**。現在全部共用 `open_dialogs.open_source`。
        assert src.key in open_dialogs.OPENABLE, (
            "`%s` 在 INPUT_SOURCES 上，但 open_source 不認得它 —— "
            "那顆鈕按下去只會講一句「還沒有辦法開」。" % src.key)
    # 每顆 Open 的圖示要各不相同（F7-24）——「輪廓要分得出來」那一條
    icons = [s.icon for s in scope_mod.INPUT_SOURCES]
    assert len(set(icons)) == len(icons)


def test_the_one_button_that_takes_a_file_or_a_folder_routes_like_the_cli(
        tmp_path):
    """**`Open images…` 與命令列要對同一份資料給同一個答案。**

    F114-2 把 `folder`／`image`／`raw` 併成一顆，而併得起來的唯一理由是
    「是哪一種**看那條路徑就知道**」。那條規則於是有了**兩份實作** ——
    UI 的 `open_dialogs.raw_folder_for` 與 CLI 的 `d4t.__main__._open_input`
    —— 而兩份實作一定會漂（`CLAUDE.md` §0 的第一句話）。這一條把它們釘在一起。

    釘的是最容易漂的那一格：**`.raw` 認不認得**。`.raw` 解不開，所以它
    **不在** `dataset._IMAGE_EXTS` 裡，兩邊都得自己多問一次 —— 少問的那一邊
    會把 `.raw` 當成「沒有影像的資料夾」而給出一個空的 lot。
    """
    import numpy as np

    from d4t import __main__ as cli
    from d4t.core.ingest import imageio
    from d4t.ui import open_dialogs

    raw_dir = tmp_path / "raws"
    raw_dir.mkdir()
    (raw_dir / "a.raw").write_bytes(np.zeros((8, 8), "<u2").tobytes())

    png_dir = tmp_path / "pngs"
    png_dir.mkdir()
    imageio.save_gray(str(png_dir / "a.png"), np.full((8, 8), 20, np.uint8))

    # UI：資料夾與裡面那個檔案都要指到同一個 lot 資料夾
    assert open_dialogs.raw_folder_for(str(raw_dir)) == str(raw_dir)
    assert open_dialogs.raw_folder_for(str(raw_dir / "a.raw")) == str(raw_dir)
    # ……而不是 raw 的那條路上，它要說「不是我」
    assert open_dialogs.raw_folder_for(str(png_dir)) is None
    assert open_dialogs.raw_folder_for(str(png_dir / "a.png")) is None

    # CLI：同一個資料夾也要走 raw 那條（8x8 的 16-bit 只有一組正方形解）
    ds = cli._open_input(str(raw_dir), raw="8x8@16")
    assert ds.kind == "folder" and len(ds.items) == 1
    assert cli._open_input(str(png_dir)).kind == "folder"


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


def test_hiding_a_card_only_takes_it_out_of_the_library(window):
    """**收起來、不刪掉**（`CLAUDE.md` §5 的判斷）：卡片庫看不到它，但已經在用它
    的 recipe 照跑、CLI 照跑、黃金值一個字不動。

    ⚠ **這一條 2026-09-17（F109）從「align 是收起來的」改寫成「收起來這件事是
    怎麼運作的」。** 使用者 2026-08-18 說的是「我不喜歡 align 卡……拉 align 反而
    會飄掉 shift……**之後真需要我再回來**」，而 DOE 就是那個「之後」—— align 回到
    卡片庫了，`HIDDEN_STEPS` 現在是空的。

    寫死那張卡的那一版在這一輪只會紅一次然後被改掉，而**壞掉的不是這條測試在問
    的東西**：收起來只過濾卡片庫這件事一個字都沒變。所以這裡當場塞一張卡進
    `HIDDEN_STEPS` 試給它看 —— 空的清單過濾不掉任何東西，那正是這種測試最危險
    的時候。
    """
    from d4t.core.pipeline import get_step

    assert window.library.entry("align") is not None, \
        "align 2026-09-17 拿回卡片庫了（F109）"

    victim = "align"
    before = scope_mod.HIDDEN_STEPS
    try:
        scope_mod.HIDDEN_STEPS = (victim,)
        # 卡片庫是在建構時吃 `visible_steps()` 的；這一支會重吃一次
        # （不另開一扇窗：Qt 物件在測試行程裡不會消失，時間是超線性的）。
        window._repaint_for_theme()
        assert window.library.entry(victim) is None       # 卡片庫看不到
        assert get_step(victim) is not None               # 但引擎照樣認得
        assert window.model.add_step(victim)              # 舊 recipe 也放得進來
    finally:
        scope_mod.HIDDEN_STEPS = before
        window._repaint_for_theme()


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

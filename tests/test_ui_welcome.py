# ADEPT 首次開啟導覽測試 — authored 2026-07-28 (M6-2).
"""``adept/ui/welcome.py`` 與 Studio 導覽接線的離屏（offscreen）測試。

執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_welcome.py -q``

**為什麼所有 Qt import 都是 lazy 的（別改回去）**

``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有
任何 PySide6 模組。pytest 先蒐集全部測試檔、再開始跑，所以只要這個檔案在
**模組層** ``import PySide6``（或 import ``adept.ui.welcome``），蒐集階段就會把
Qt 塞進 ``sys.modules``，那個守門測試就會紅 —— 即使它先跑。

因此：所有 Qt / ``adept.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
每個測試都必須（直接或間接）要求 ``qapp`` fixture，否則那些名字不存在。

**QSettings 不准弄髒開發機**：``welcome.app_settings()`` 用的是
``IniFormat`` + ``UserScope``，所以 ``qapp`` fixture 一開始就把這個 scope 的
路徑導到 pytest 的暫存目錄；「不再顯示」寫出來的檔案落在那裡。

對話框一律**非 modal**（``show()``、不用 ``exec()``），而且動作都有可以直接
呼叫的方法（``click_demo`` / ``load_selected`` / ``run_demo(sync=True)``），
所以整個檔案不需要 event loop，也不會有任何一個測試卡住。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RECIPES_DIR = REPO / "examples" / "recipes"


def _load_qt() -> None:
    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
    from PySide6.QtCore import QSettings  # noqa: F401
    from PySide6.QtWidgets import QApplication  # noqa: F401

    from adept.ui import studio as studio_mod  # noqa: F401
    from adept.ui import theme as theme_mod  # noqa: F401
    from adept.ui import welcome as welcome_mod  # noqa: F401

    globals().update(locals())


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    """離屏 QApplication + 主題 + 把 QSettings 導到暫存目錄。"""
    _load_qt()
    settings_dir = tmp_path_factory.mktemp("qsettings")
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(settings_dir))
    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
    theme_mod.apply_theme(app)
    yield app
    app.processEvents()


@pytest.fixture(autouse=True)
def clean_settings(qapp):
    """每個測試都從「沒勾過不再顯示」開始（避免測試之間互相影響）。"""
    welcome_mod.set_welcome_disabled(False)
    yield
    welcome_mod.set_welcome_disabled(False)


@pytest.fixture(scope="module")
def demo_lot(tmp_path_factory):
    """給 ``run_demo`` 用的輸出資料夾（不碰使用者家目錄的 ~/.adept）。"""
    return tmp_path_factory.mktemp("demo_lot")


def _catch(signal):
    """把訊號的參數 append 到一個 list（沒有 pytest-qt，手動接）。"""
    seen = []
    signal.connect(lambda *args: seen.append(tuple(args)))
    return seen


# --------------------------------------------------------------------------- #
# WelcomeDialog：三顆鈕真的會發訊號
# --------------------------------------------------------------------------- #
def test_welcome_dialog_constructs_with_the_three_actions(qapp):
    dlg = welcome_mod.WelcomeDialog()
    try:
        assert dlg.isModal() is False, "導覽不可以是 modal（會卡住主視窗與測試）"
        for btn in (dlg.btn_demo, dlg.btn_open, dlg.btn_library):
            assert btn.text().strip(), "動作鈕沒有文字"
            assert btn.toolTip().strip(), "動作鈕沒有 tooltip（推廣鐵則）"
        # 最重要的那顆要長得像主要動作
        assert dlg.btn_demo.objectName() == "primary"
        # 三段式視覺：影像 / 算法 / ADC 各一張，顏色來自 theme token
        cats = [c.property("category") for c in dlg.segments.cards]
        assert cats == ["image", "algo", "adc"]
        for cat in cats:
            assert theme_mod.seg_hex(cat) in dlg.segments.cards[cats.index(cat)] \
                .styleSheet()
        assert "KLARF" in dlg.intro_label.text()
    finally:
        dlg.close()


@pytest.mark.parametrize("button, signal_name", [
    ("btn_demo", "demo_requested"),
    ("btn_open", "open_klarf_requested"),
    ("btn_library", "library_requested"),
])
def test_welcome_buttons_emit_their_signal(qapp, button, signal_name):
    dlg = welcome_mod.WelcomeDialog()
    try:
        seen = _catch(getattr(dlg, signal_name))
        getattr(dlg, button).click()
        assert len(seen) == 1, "按了 %s 卻沒有發出 %s" % (button, signal_name)
    finally:
        dlg.close()


def test_demo_and_open_buttons_close_the_dialog_first(qapp):
    """按了「試一次」/「開我的 KLARF」要先關掉導覽，使用者才看得到結果。"""
    for button in ("btn_demo", "btn_open"):
        dlg = welcome_mod.WelcomeDialog()
        dlg.show()
        assert dlg.isVisible() is True
        getattr(dlg, button).click()
        assert dlg.isVisible() is False, "%s 按完應該關掉導覽" % button
        dlg.close()


def test_dont_show_again_writes_the_qsettings_flag(qapp):
    assert welcome_mod.welcome_disabled() is False
    dlg = welcome_mod.WelcomeDialog()
    try:
        assert dlg.chk_dont_show.isChecked() is False
        dlg.set_dont_show_again(True)
        assert welcome_mod.welcome_disabled() is True
        # 設定要真的落到 QSettings（換一個 QSettings 物件也讀得到）
        st = welcome_mod.app_settings()
        assert str(st.value(welcome_mod.SKIP_WELCOME_KEY)).lower() in ("true", "1")
        dlg.set_dont_show_again(False)
        assert welcome_mod.welcome_disabled() is False
    finally:
        dlg.close()


def test_new_dialog_reflects_the_saved_flag(qapp):
    welcome_mod.set_welcome_disabled(True)
    dlg = welcome_mod.WelcomeDialog()
    try:
        assert dlg.chk_dont_show.isChecked() is True
    finally:
        dlg.close()


def test_quick_reference_button_is_guarded_when_pdf_missing(qapp, tmp_path):
    """docs/ 沒有 PDF 時：鈕還在（使用者知道有這東西）但停用，按了不會炸。"""
    assert welcome_mod.quick_reference_pdf(tmp_path) is None
    dlg = welcome_mod.WelcomeDialog()
    try:
        if dlg.quickref_path is None:
            assert dlg.btn_quickref.isEnabled() is False
            assert dlg.btn_quickref.toolTip().strip()
            assert dlg.open_quick_reference() is False   # 按下去也不炸
        else:
            assert dlg.btn_quickref.isEnabled() is True
    finally:
        dlg.close()


def test_quick_reference_finds_a_pdf_and_prefers_the_named_one(tmp_path, qapp):
    (tmp_path / "aaa-other.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "adept-quick-reference.pdf").write_bytes(b"%PDF-1.4\n")
    found = welcome_mod.quick_reference_pdf(tmp_path)
    assert found is not None and found.name == "adept-quick-reference.pdf"


# --------------------------------------------------------------------------- #
# RecipeLibraryDialog：內容全部從 JSON 讀
# --------------------------------------------------------------------------- #
def test_library_lists_every_supported_recipe_file(qapp):
    """清單完全由資料夾內容決定（沒有任何檔名寫死）。

    F7-1 起會再過一層 :func:`adept.ui.scope.recipe_is_supported`：純 rsem 的
    範本在 patch-only 期間不列出來。原本的重點沒變 —— 列出來的東西與順序
    仍然只由 ``examples/recipes/`` 決定。
    """
    from adept.ui.scope import recipe_is_supported

    files = sorted(RECIPES_DIR.glob("*.json"))
    assert files, "examples/recipes/ 是空的"
    expected = [p.name for p in files
                if recipe_is_supported(welcome_mod.read_recipe_info(p))]
    assert expected, "至少要有一份目前 build 跑得動的範本"

    dlg = welcome_mod.RecipeLibraryDialog()
    try:
        assert dlg.count() == len(expected)
        assert [Path(e["path"]).name for e in dlg.entries()] == expected
    finally:
        dlg.close()


def test_library_shows_description_routes_steps_and_expr_from_json(qapp):
    """對話框上的每一個字都要來自 JSON —— 沒有任何一份 recipe 被寫死。"""
    dlg = welcome_mod.RecipeLibraryDialog()
    try:
        for i, info in enumerate(dlg.entries()):
            raw = json.loads(Path(info["path"]).read_text(encoding="utf-8"))
            assert info["recipe_id"] == raw["recipe_id"]
            assert info["description"] == raw["description"]
            assert info["description"].strip(), "%s 沒有 description" % info["file"]
            assert info["routes"] == list(raw["routes"])
            assert info["n_steps"] == len(raw["nodes"])
            assert info["expr"] == raw["score"]["expr"]
            assert info["threshold"] == pytest.approx(raw["score"]["threshold"])

            # 清單那一列要看得到 recipe 名稱與 route
            text = dlg.item_text(i)
            assert raw["recipe_id"] in text
            for route in raw["routes"]:
                assert route in text

            # 右邊細節要看得到說明與分數式
            assert dlg.select(i) is True
            detail = dlg.detail.text()
            assert raw["description"] in detail
            assert raw["score"]["expr"] in detail
            for route in raw["routes"]:
                assert route in detail
    finally:
        dlg.close()


def test_library_emits_recipe_chosen_with_the_right_path(qapp):
    dlg = welcome_mod.RecipeLibraryDialog()
    try:
        seen = _catch(dlg.recipe_chosen)
        target = len(dlg.entries()) - 1
        assert dlg.select(target) is True
        expected = dlg.path_at(target)
        assert dlg.load_selected() == expected
        assert seen == [(expected,)]
        assert Path(expected).is_file()
    finally:
        dlg.close()


def test_library_reads_a_custom_directory_and_survives_broken_json(tmp_path, qapp):
    good = json.loads((RECIPES_DIR / "die_to_die_basic.json").read_text(encoding="utf-8"))
    (tmp_path / "a_good.json").write_text(json.dumps(good), encoding="utf-8")
    (tmp_path / "b_broken.json").write_text("{ this is not json", encoding="utf-8")
    dlg = welcome_mod.RecipeLibraryDialog(directory=tmp_path)
    try:
        assert dlg.count() == 2
        entries = dlg.entries()
        assert entries[0]["error"] == ""
        assert entries[1]["error"], "壞掉的 JSON 應該被標記成讀不開"
        # 選到壞的那一列：載入鈕停用、按下去也不發訊號
        seen = _catch(dlg.recipe_chosen)
        assert dlg.select(1) is True
        assert dlg.btn_load.isEnabled() is False
        assert dlg.load_selected() is None
        assert seen == []
    finally:
        dlg.close()


def test_library_with_empty_directory_does_not_crash(tmp_path, qapp):
    dlg = welcome_mod.RecipeLibraryDialog(directory=tmp_path)
    try:
        assert dlg.count() == 0
        assert dlg.load_selected() is None
    finally:
        dlg.close()


# --------------------------------------------------------------------------- #
# Studio 接線
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def window(qapp):
    """整個模組共用一個主視窗（**建構時不准彈任何對話框**）。"""
    win = studio_mod.StudioWindow()
    yield win
    win.close()


def test_constructing_studio_never_pops_the_welcome(window):
    assert window.welcome_dialog is None
    assert window.library_dialog is None
    # 明確關掉也一樣安全
    other = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert other.welcome_dialog is None
    finally:
        other.close()


def test_toolbar_has_help_and_examples_entries(window):
    assert window.btn_help.text() == "Help"
    assert window.btn_examples.text() == "Templates…"
    for b in (window.btn_help, window.btn_examples):
        assert b.toolTip().strip()


def test_show_welcome_respects_and_overrides_the_flag(window):
    welcome_mod.set_welcome_disabled(True)
    assert window.show_welcome() is None, "勾了「不再顯示」就不該自己跳出來"
    dlg = window.show_welcome(force=True)
    assert dlg is not None and dlg.isVisible() is True
    assert window.show_welcome(force=True) is dlg, "重複開啟要重用同一個對話框"
    dlg.close()


def test_welcome_library_button_opens_the_library_from_studio(window):
    dlg = window.show_welcome(force=True)
    assert dlg is not None
    dlg.btn_library.click()
    lib = window.library_dialog
    try:
        assert lib is not None and lib.count() > 0
    finally:
        if lib is not None:
            lib.close()
        dlg.close()


def test_library_choice_loads_the_recipe_into_the_model(window):
    lib = window.open_recipe_library()
    try:
        names = [e["recipe_id"] for e in lib.entries()]
        idx = names.index("die_to_die_basic")
        assert lib.select(idx) is True
        path = lib.load_selected()
        assert path is not None
    finally:
        lib.close()
    assert window.model.recipe_id == "die_to_die_basic"
    assert window.model.node_order, "載入 recipe 之後流程不該是空的"


def test_welcome_demo_button_is_wired_to_studio_run_demo(window, monkeypatch):
    """導覽只發訊號，動作在 Studio —— 這裡驗接線（不真的跑，也不寫 ~/.adept）。"""
    calls = []

    def fake_run_demo(*args, **kwargs):
        calls.append((args, kwargs))
        return True

    monkeypatch.setattr(window, "run_demo", fake_run_demo)
    dlg = window.show_welcome(force=True)
    assert dlg is not None
    try:
        dlg.btn_demo.click()
        assert len(calls) == 1, "「用範例資料試一次」沒有接到 StudioWindow.run_demo"
    finally:
        dlg.close()


def test_demo_runs_end_to_end_and_populates_the_window(window, demo_lot):
    """「用範例資料試一次」：跑完必須有資料集、有流程、有分數分佈、有 Gallery。"""
    # 同步跑（不進 event loop）並指定輸出位置，免得測試去寫使用者家目錄的
    # ~/.adept/demo_lot。
    assert window.run_demo(out_dir=str(demo_lot), n=6, sync=True) is True

    assert window.dataset is not None
    assert len(window.dataset.items) == 6
    assert window.model.recipe_id == "die_to_die_basic"
    assert len(window.trial_results) == 6
    assert all(r.get("ok") for r in window.trial_results)
    assert len(window.trial_scores) == 6
    assert window.histogram.has_data() is True, "直方圖沒有資料"
    assert window.histogram.bin_summary_text().strip()
    assert window.gallery.displayed_count() == 6
    assert window.results_visible() is True
    assert window.btn_export.isEnabled() is True
    assert "Sample run finished" in window.status_text()


def test_demo_lot_generation_is_reused_not_regenerated(demo_lot):
    """同一個資料夾第二次呼叫要直接沿用（第二次按那顆鈕是秒回的）。"""
    paths = studio_mod.generate_demo_lot(str(demo_lot), n=6)
    assert Path(paths["klarf"]).is_file()
    before = Path(paths["tiff"]).stat().st_mtime_ns
    again = studio_mod.generate_demo_lot(str(demo_lot), n=6)
    assert again["klarf"] == paths["klarf"]
    assert Path(again["tiff"]).stat().st_mtime_ns == before


def test_demo_reports_failure_instead_of_raising(window, tmp_path, monkeypatch):
    """產資料失敗只在狀態列說明（鐵則：不准把 traceback 丟給使用者）。"""
    def boom(*_a, **_kw):
        raise RuntimeError("磁碟滿了")

    monkeypatch.setattr(studio_mod, "generate_demo_lot", boom)
    assert window.run_demo(out_dir=str(tmp_path), n=4, sync=True) is False
    assert "磁碟滿了" in window.status_text()


def test_generated_demo_lot_matches_the_builtin_template_route(demo_lot):
    """範例資料一定要走得通內建範本的 route，不然那顆鈕會給人第一印象是壞的。"""
    from adept.core.ingest.dataset import load_dataset
    from adept.core.pipeline import Recipe

    paths = studio_mod.generate_demo_lot(str(demo_lot), n=6)
    ds = load_dataset(paths["klarf"])
    recipe = Recipe.load(str(studio_mod.TEMPLATE_RECIPE))
    assert ds.kind in recipe.routes

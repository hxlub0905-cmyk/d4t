# F121 期 4：Studio 端 —— 一顆「Open data…」。
"""**入口只有一顆，而它按下去就是對話框，挑完就照路徑開。**

使用者（2026-09-24）：「我想把入口簡單化」。這一份鎖：

1. 表上只有一列，而它打得開每一種支援的資料（``SUPPORTED_KINDS``）；
2. Input 卡上那顆鈕與空白畫面上那一顆**是同一個字**，而且按下去**直接開**
   （以前是一張選單，先問「你要開哪一種」）；
3. 挑完之後的分岔走 core 那一份判斷（`plan_open`）：KLARF 檔、lot 資料夾、
   影像資料夾、單張影像各走各的載入；
4. **反向**：畫面上的字不再叫使用者去按已經退役的鈕（`Open KLARF…` /
   `Open images…` / `Open conditions…`）。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication              # noqa: E402

from d4t.ui import open_dialogs                         # noqa: E402
from d4t.ui import scope                                # noqa: E402
from d4t.ui import studio as studio_mod                 # noqa: E402
from d4t.ui import theme as theme_mod                   # noqa: E402

RETIRED = ("Open KLARF…", "Open images…", "Open conditions…")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    yield win
    win.close()


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate

    return generate(str(tmp_path_factory.mktemp("lot")), n=2, seed=3)


# --------------------------------------------------------------------------- #
# 1. 一列，打得開每一種
# --------------------------------------------------------------------------- #
def test_there_is_one_entry_and_it_opens_every_kind():
    assert [s.key for s in scope.INPUT_SOURCES] == ["data"]
    assert set(scope.INPUT_SOURCES[0].kinds) == set(scope.SUPPORTED_KINDS)
    assert open_dialogs.OPENABLE == ("data",)


# --------------------------------------------------------------------------- #
# 2. 卡上那顆與空白畫面那顆同一個字，按下去直接開
# --------------------------------------------------------------------------- #
def test_the_card_button_and_the_empty_screen_say_the_same_thing(window):
    assert window.DATA_SOURCE_LABEL == scope.INPUT_SOURCES[0].title
    assert window.btn_empty_open.text() == scope.INPUT_SOURCES[0].title


def test_the_card_button_opens_the_dialog_without_a_menu_first(window,
                                                               monkeypatch):
    asked = []
    monkeypatch.setattr(open_dialogs, "ask_data",
                        lambda parent: asked.append(parent) or None)
    window._on_add_requested("load_patch")
    window.select_node(window.model.node_order[0])
    window._on_source_requested()
    assert asked == [window], "按下去就是對話框（不是先跳一張選單）"


# --------------------------------------------------------------------------- #
# 3. 挑完照路徑開
# --------------------------------------------------------------------------- #
def test_what_was_picked_decides_how_it_is_opened(window, lot, tmp_path,
                                                  monkeypatch):
    import numpy as np

    from d4t.core.ingest import imageio

    calls = []
    for name in ("load_dataset_path", "load_folder_path", "load_image_path"):
        monkeypatch.setattr(window, name,
                            lambda p, n=name: calls.append((n, str(p))))
    png_dir = tmp_path / "pngs"
    png_dir.mkdir()
    png = png_dir / "a.png"
    imageio.save_gray(str(png), np.full((8, 8), 20, np.uint8))
    lot_dir = str(Path(lot["klarf"]).parent)

    for picked in (lot["klarf"], lot_dir, str(png_dir), str(png)):
        open_dialogs.open_path(window, picked)
    assert calls == [("load_dataset_path", lot["klarf"]),
                     ("load_dataset_path", lot["klarf"]),   # lot 資料夾 → 它的 KLARF
                     ("load_folder_path", str(png_dir)),
                     ("load_image_path", str(png))]


# --------------------------------------------------------------------------- #
# 4. 反向：不叫使用者去按已經不在的鈕
# --------------------------------------------------------------------------- #
def test_no_message_points_at_a_retired_open_button():
    """`No dataset loaded yet — use “Open KLARF…” first.` 那一句在六個地方寫死過；
    按鈕合成一顆之後它們指著一顆不存在的鈕。只掃**字串**，不掃註解（註解裡講
    歷史是對的）。"""
    bad = []
    for path in sorted((REPO / "d4t" / "ui").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if any(name in node.value for name in RETIRED) \
                        and not _is_docstring(tree, node):
                    bad.append("%s:%d" % (path.name, node.lineno))
    assert not bad, "還在叫使用者按退役的鈕：%s" % bad


def _is_docstring(tree, const) -> bool:
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and body[0].value is const:
            return True
    return False

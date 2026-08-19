# F15：第二份 lot 從卡片上開 — authored 2026-08-19.
"""使用者：「我只想把它做成一個小功能 card，這張 card 會 load 自己的 source」。

那句話裡有兩件事，這一份把兩件都鎖住：

1. **入口在卡片上**（沿用 F14-1 的那顆 `Open data…`），而它開的是**第二份**
   —— 不取代目前的資料集。main 決定批次跑幾顆、走哪一條 route、KLARF 寫回誰。
2. **畫布不能說謊**：那張卡上印的檔名要是**它自己那一份**。它跟 Load 卡一樣
   是 `is_source()`，所以什麼都不做的話它會印 main 的檔名 —— 跑得完、有數字、
   而且畫布是錯的。

⚠ 卡片自己**不讀檔**：第二份是 Studio/CLI 載成 `Dataset` 掛在
`Dataset.sources[代號]` 上的。理由是快取簽章（鐵則 9）—— 驗收在
`tests/test_pair_source.py`，這裡只管 UI 那一段。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication            # noqa: E402

import d4t.core.steps  # noqa: F401,E402
from d4t.core.pipeline import get_step                # noqa: E402
from d4t.ui import studio as studio_mod               # noqa: E402
from d4t.ui import theme as theme_mod                 # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app, "light")
    yield app


@pytest.fixture(scope="module")
def lots(tmp_path_factory):
    """兩份合成 lot：main 與「第二份」（同一組座標，換一個名字）。"""
    import os

    from make_sample import generate
    root = tmp_path_factory.mktemp("f15")
    main = generate(str(root / "main"), n=5, seed=3)
    gt = generate(str(root / "gt"), n=5, seed=3)
    # 兩份的檔名要**不一樣**，不然「印的是哪一份的名字」這件事驗不出來。
    renamed = os.path.join(os.path.dirname(gt["klarf"]), "LOT_GT.001")
    os.replace(gt["klarf"], renamed)
    gt["klarf"] = renamed
    return {"main": main, "gt": gt}


@pytest.fixture
def window(qapp):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.resize(1500, 950)
    yield win
    win.close()


def _pair_node(window):
    nid = window.model.add_step("pair_source")
    window.select_node(nid)
    return nid


# --------------------------------------------------------------------------- #
# 1. 入口在卡片上
# --------------------------------------------------------------------------- #
def test_the_card_carries_the_entry(window):
    nid = _pair_node(window)
    assert window.param_form.has_source_action()
    assert window.param_form.source_button().text() == \
        studio_mod.StudioWindow.DATA_SOURCE_LABEL
    assert nid in window.model.nodes


def test_it_opens_the_second_lot_not_the_menu(window, monkeypatch):
    """Load 卡那顆鈕開的是「三條路」的選單；這一張只有一條路，直接開。"""
    called = []
    monkeypatch.setattr(window, "_on_open_pair_source",
                        lambda nid: called.append(nid))
    nid = _pair_node(window)
    window._on_source_requested()
    assert called == [nid]


def test_without_a_main_lot_it_says_so(window, monkeypatch):
    """main 還沒載的時候掛第二份是沒有意義的 —— 配對是「這一顆對到哪一顆」。"""
    said = []
    monkeypatch.setattr(window, "_status",
                        lambda msg, *a, **k: said.append(msg))
    nid = _pair_node(window)
    assert window.param_form._source_note.text() == "Load the main lot first"
    window._on_open_pair_source(nid)
    assert said and "main lot" in said[0]


# --------------------------------------------------------------------------- #
# 2. 掛上去之後
# --------------------------------------------------------------------------- #
def test_attaching_names_the_source_and_says_what_it_is(window, lots):
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    assert window.param_form._source_note.text().startswith("No second lot")

    msg = window.attach_pair_source(nid, lots["gt"]["klarf"])
    assert "Paired source" in msg

    # 代號使用者沒打 → 從檔名推一個（而它要能當變數名）
    sid = window.model.nodes[nid].params["source"]
    assert sid and (sid[0].isalpha() or sid[0] == "_")
    assert sid.replace("_", "a").isalnum()

    # 掛在 main 上，不是取代 main
    assert window.dataset.kind == "ebi_patch"
    assert len(window.dataset.items) == 5
    assert sid in window.dataset.sources
    assert len(window.dataset.sources[sid].items) == 5

    window.select_node(nid)
    note = window.param_form._source_note.text()
    assert Path(lots["gt"]["klarf"]).name in note
    assert "5 defects" in note


def test_the_card_on_the_canvas_shows_its_own_lot_not_the_main_one(window, lots):
    """這張卡是 `is_source()`，所以什麼都不做的話它會印 main 的檔名。"""
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    window.attach_pair_source(nid, lots["gt"]["klarf"])
    parts = window.pipeline.node_item(nid).summary_parts()
    assert Path(lots["gt"]["klarf"]).name in parts, parts
    assert Path(lots["main"]["klarf"]).name not in parts, parts


def test_a_bad_path_is_reported_not_raised(window, lots, tmp_path):
    """UI 邊界一律回報 —— 選錯檔案不該讓 Studio 掉下去。"""
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    bad = tmp_path / "not-a-klarf.001"
    bad.write_text("hello", encoding="utf-8")
    msg = window.attach_pair_source(nid, str(bad))
    assert msg and "Could not load" in msg or "no defect" in msg.lower()
    assert not window.dataset.sources


# --------------------------------------------------------------------------- #
# 3. 沒掛的時候，畫布要講得出「還沒設定完」
# --------------------------------------------------------------------------- #
def test_an_unconfigured_card_is_flagged_on_the_canvas(window, lots):
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    issues = [i for i in window.model.validate()
              if getattr(i, "node_id", None) == nid]
    assert any(i.code == "not-configured" for i in issues), issues
    # 訊息要指得到一個按得到的東西
    detail = next(i.detail for i in issues if i.code == "not-configured")
    assert studio_mod.StudioWindow.DATA_SOURCE_LABEL.rstrip("…") in detail


def test_the_source_id_rule_is_stable(window):
    """代號是**每次都一樣**的推導 —— 同一個檔名不會兩次得到不同的代號。"""
    f = studio_mod._source_id_from
    assert f("/x/y/LOT_SYN.001") == f("/z/LOT_SYN.001") == "LOT_SYN"
    assert f("/x/2026-lot.001") == "s2026_lot"       # 開頭是數字 → 補一個 s
    assert f("/x/ .001") == "src"                    # 推不出東西也要有個名字


# --------------------------------------------------------------------------- #
# 4. 儀表：分布答不出來的那兩件事
# --------------------------------------------------------------------------- #
def test_the_inspector_says_which_defect_it_paired_with(qapp):
    """對到的是哪一顆、帶過來的字串欄位 —— 兩件都不在特徵表裡。"""
    from d4t.ui.inspectors import PairInspector, inspector_for

    assert inspector_for("pair_source") is PairInspector
    ins = PairInspector()
    ins.set_context(
        "n1", params={"source": "gt"},
        result={"features": {"paired": 1.0, "match_dist_nm": 132.0}},
        batch=[{"features": {"paired": 1.0, "match_dist_nm": 132.0}}],
        meta={"pair_match": {"source": "gt", "defect_id": "8801",
                             "index": 3, "dist_nm": 132.0, "candidates": 2},
              "pair_fields": {"CLASS": "particle"}},
        feature_names=["paired", "match_dist_nm"])
    text = ins.summary()
    assert "8801" in text and "gt" in text
    assert "132 nm" in text
    assert "CLASS=particle" in text          # 字串欄位只有這裡看得到
    assert ins.has_data()


def test_the_inspector_says_it_when_there_was_no_match(qapp):
    from d4t.ui.inspectors import PairInspector

    ins = PairInspector()
    ins.set_context("n1", params={"source": "gt"},
                    meta={"pair_match": {"source": "gt", "defect_id": "",
                                         "index": -1, "dist_nm": float("nan"),
                                         "candidates": 1}})
    assert "no match" in ins.summary()


def test_the_align_card_has_the_spread_panel(qapp):
    """0.62 是高是低要看其他顆長什麼樣 —— 對圖的分數只有跟整批比才讀得懂。"""
    from d4t.ui.inspectors import MeasureInspector, inspector_for

    assert inspector_for("align_to") is MeasureInspector

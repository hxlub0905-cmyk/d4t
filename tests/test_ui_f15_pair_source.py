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

    msg = window.attach_pair_source(nid, lots["gt"]["klarf"], sync=True)
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
    window.attach_pair_source(nid, lots["gt"]["klarf"], sync=True)
    parts = window.pipeline.node_item(nid).summary_parts()
    assert Path(lots["gt"]["klarf"]).name in parts, parts
    assert Path(lots["main"]["klarf"]).name not in parts, parts


def test_a_bad_path_is_reported_not_raised(window, lots, tmp_path):
    """UI 邊界一律回報 —— 選錯檔案不該讓 Studio 掉下去。"""
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    bad = tmp_path / "not-a-klarf.001"
    bad.write_text("hello", encoding="utf-8")
    msg = window.attach_pair_source(nid, str(bad), sync=True)
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


def test_the_align_card_keeps_the_spread_panel_and_gains_a_headline(qapp):
    """0.62 是高是低要看其他顆長什麼樣 —— 對圖的分數只有跟整批比才讀得懂，
    所以**分布留著**。

    F33 在它上面多一行：這張卡的產物是一個**位置**，而「對到哪、歪了多少、
    可不可信」分布答不出來。所以是 `MeasureInspector` 的**子類**，不是換掉它。
    """
    from d4t.ui.inspectors import H2HInspector, MeasureInspector, inspector_for

    panel = inspector_for("align_to")
    assert panel is H2HInspector
    assert issubclass(panel, MeasureInspector)      # 分布沒有被拿掉


def test_the_h2h_headline_says_where_it_matched_and_how_far_off(qapp):
    """這張卡的產物是一個**位置**：對到哪、歪了多少、可不可信。"""
    from d4t.ui.inspectors import H2HInspector

    ins = H2HInspector()
    feats = {"ncc_score": 0.94, "align_peak_ratio": 0.12,
             "align_off_x_px": -22.6, "align_off_y_px": 33.8}
    ins.set_context(
        "n1", params={"template": "paired", "search": "single"},
        result={"features": feats}, batch=[{"features": feats}],
        meta={"align_to": {"x": 120.0, "y": 60.0, "search": "single",
                           "size": [40, 40], "shape": [200, 200],
                           "expected": [80.0, 80.0]}},
        feature_names=list(feats))
    text = ins.summary()
    assert "(120, 60)" in text                 # 對到哪
    assert "-23" in text and "+34" in text     # 歪了多少（stage 偏移）
    assert "0.94" in text                      # 分數


def test_a_repeating_pattern_is_called_out_even_when_the_score_looks_great(qapp):
    """⚠ **`ncc_score` 一個不夠。** 陣列區裡 NCC 0.98 而位置每一顆都錯 ——
    只看分數的人會被騙，所以那一行要**兩個數字一起講**。"""
    from d4t.ui.inspectors import H2HInspector

    ins = H2HInspector()
    feats = {"ncc_score": 0.98, "align_peak_ratio": 1.0,
             "align_off_x_px": 3.0, "align_off_y_px": -1.0}
    ins.set_context(
        "n1", params={}, result={"features": feats},
        batch=[{"features": feats}],
        meta={"align_to": {"x": 10.0, "y": 10.0, "search": "single",
                           "size": [40, 40], "shape": [200, 200],
                           "expected": [80.0, 80.0]}},
        feature_names=list(feats))
    text = ins.summary()
    assert "guess" in text and "0.98" in text


def test_the_h2h_panel_tells_run_it_from_matched_apart(qapp):
    """**對到了**跟**還沒跑**是兩句不同的話（同 `PairInspector`）。"""
    from d4t.ui.inspectors import H2HInspector

    ins = H2HInspector()
    ins.set_context("n1", params={}, result=None, batch=[], meta={},
                    feature_names=[])
    assert "wired up" in ins.empty_reason()


# --------------------------------------------------------------------------- #
# 5. 背景載入：raw data 是幾十萬顆，UI 不可以停住（F15-2 第 1 步）
# --------------------------------------------------------------------------- #
def _pump(qapp, done, timeout_s=20.0):
    """轉 event loop 直到 ``done()`` 為真（或逾時）。"""
    import time

    t0 = time.time()
    while not done() and time.time() - t0 < timeout_s:
        qapp.processEvents()
    return done()


def test_the_second_lot_loads_in_the_background(qapp, window, lots):
    """第一版是同步的，於是開一份 raw data 時整個 Studio 沒有反應好一陣子。

    main 那一份**早就**在背景載了（`dataset_worker`），第二份沒有跟上 ——
    同一件事兩種做法，而慢的那一種是使用者會遇到的那一種。
    """
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)

    msg = window.attach_pair_source(nid, lots["gt"]["klarf"])   # 沒有 sync=True
    # **立刻**回來（還沒載完），而且講得出正在做什麼
    assert "Loading" in msg and Path(lots["gt"]["klarf"]).name in msg
    assert window._pending_pair is not None
    assert not window.dataset.sources                # 還沒掛上

    assert _pump(qapp, lambda: bool(window.dataset.sources)), "背景載入沒有完成"
    sid = window.model.nodes[nid].params["source"]
    assert sid in window.dataset.sources
    assert window._pending_pair is None


def test_a_broken_file_in_the_background_is_reported_not_swallowed(qapp, window,
                                                                   lots, tmp_path):
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    bad = tmp_path / "not-a-klarf.001"
    bad.write_text("hello", encoding="utf-8")
    said = []
    window.pair_worker.failed.connect(lambda m: said.append(m))

    window.attach_pair_source(nid, str(bad))
    assert _pump(qapp, lambda: bool(said) or window._pending_pair is None)
    assert not window.dataset.sources


# --------------------------------------------------------------------------- #
# 6. 只複製要用的那幾欄
# --------------------------------------------------------------------------- #
def test_only_the_carried_columns_are_copied(window, lots):
    """raw data ×24 欄字串是幾百 MB，而其中 22 欄從來沒有人 carry。"""
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    window.model.set_param(nid, "carry", "CLASSNUMBER")
    window.attach_pair_source(nid, lots["gt"]["klarf"], sync=True)

    sid = window.model.nodes[nid].params["source"]
    fields = window.dataset.sources[sid].items[0].fields
    assert set(fields) == {"CLASSNUMBER"}


def test_ticking_a_column_afterwards_refills_it(window, lots):
    """之後才勾起來的那一欄不在 `fields` 裡的話，卡片會說「這一份沒有這個
    欄位」—— 而那句話是錯的：欄位在，只是沒複製。"""
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    window.attach_pair_source(nid, lots["gt"]["klarf"], sync=True)
    sid = window.model.nodes[nid].params["source"]
    assert window.dataset.sources[sid].items[0].fields == {}

    window.select_node(nid)
    window.param_form.param_edited.emit("carry", "DEFECTID,CLASSNUMBER")
    fields = window.dataset.sources[sid].items[0].fields
    assert set(fields) == {"DEFECTID", "CLASSNUMBER"}


def test_two_cards_on_the_same_source_both_get_their_columns(window, lots):
    """`fields` 是掛在**那一份**上的一份，照其中一張卡填的話另一張會少欄位。"""
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    a = _pair_node(window)
    window.model.set_param(a, "carry", "DEFECTID")
    window.attach_pair_source(a, lots["gt"]["klarf"], sync=True)
    sid = window.model.nodes[a].params["source"]

    b = window.model.add_step("pair_source")
    window.model.set_param(b, "source", sid)
    window.select_node(b)
    window.param_form.param_edited.emit("carry", "CLASSNUMBER")

    fields = window.dataset.sources[sid].items[0].fields
    assert set(fields) == {"DEFECTID", "CLASSNUMBER"}


# --------------------------------------------------------------------------- #
# 7. 三格用選的（F15-2 第 2 步）
# --------------------------------------------------------------------------- #
def test_the_three_fields_are_pickers_not_free_text(window, lots):
    """使用者：「太不方便，要自己填（希望可以自動帶出來用選的）」。"""
    from PySide6.QtWidgets import QComboBox
    from d4t.ui.widgets import MultiChoicePicker

    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    window.attach_pair_source(nid, lots["gt"]["klarf"], sync=True)
    window.select_node(nid)

    sid = window.model.nodes[nid].params["source"]
    src = window.param_form._rows["source"].editor
    assert isinstance(src, QComboBox)
    assert [src.itemText(i) for i in range(src.count())] == [sid]

    img = window.param_form._rows["channel"].editor
    assert isinstance(img, QComboBox)
    assert [img.itemText(i) for i in range(img.count())] == ["ref", "test"]

    carry = window.param_form._rows["carry"].editor
    assert isinstance(carry, MultiChoicePicker)
    assert "CLASSNUMBER" in carry.choice_names()
    assert "IMAGELIST" in carry.choice_names()


def test_the_source_field_still_takes_a_name_that_is_not_loaded(window):
    """recipe 是在資料掛上來**之前**讀進來的。鎖死選單 = 開一份寫好的 recipe
    會把那一格清空。"""
    from PySide6.QtWidgets import QComboBox

    nid = _pair_node(window)
    window.model.set_param(nid, "source", "not_loaded_yet")
    window.select_node(nid)
    src = window.param_form._rows["source"].editor
    assert isinstance(src, QComboBox) and src.isEditable()
    assert src.currentText() == "not_loaded_yet"


def test_pointing_at_a_source_that_is_not_attached_shows_nothing(window, lots):
    """拿「唯一掛著的那一份」去頂替是不行的 —— 那一格印的欄位就是另一份的。"""
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    window.attach_pair_source(nid, lots["gt"]["klarf"], sync=True)
    window.model.set_param(nid, "source", "somewhere_else")
    window.select_node(nid)
    assert window.param_form._rows["carry"].editor.choice_names() == []


def test_a_half_typed_name_survives_the_lists_changing(window, lots):
    """換選單**不重建表單**，所以打到一半的字還在。"""
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    window.attach_pair_source(nid, lots["gt"]["klarf"], sync=True)
    window.select_node(nid)

    src = window.param_form._rows["source"].editor
    src.setEditText("half_typed")
    window.param_form.set_dynamic_choices({"sources": ["a", "b"]})
    assert src.currentText() == "half_typed"


def test_the_field_you_are_typing_in_is_left_alone(window, lots):
    """有游標的那一格**整格跳過**。

    只保住文字不夠：``clear() + addItems()`` 會把游標推到字尾，所以在名字
    中間補一個字的時候，下一個字元會跑到最後面去。這件事最常發生的時機正是
    「使用者剛在 Source name 那一格打字」（那一格一改，另外兩格的清單就變）。

    offscreen 平台不會真的給 focus，所以這裡直接把那格的 ``hasFocus`` 換掉 ——
    要驗的是 `set_dynamic_choices` 的取捨，不是 Qt 的 focus 管理。
    """
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    nid = _pair_node(window)
    window.attach_pair_source(nid, lots["gt"]["klarf"], sync=True)
    window.select_node(nid)

    src = window.param_form._rows["source"].editor
    before = [src.itemText(i) for i in range(src.count())]
    src.hasFocus = lambda: True
    window.param_form.set_dynamic_choices({"sources": ["a", "b"]})
    assert [src.itemText(i) for i in range(src.count())] == before

    # 沒有游標的那一格照常跟上
    assert window.param_form._rows["carry"].editor.choice_names() == []


# --------------------------------------------------------------------------- #
# 8. 第二份要走進**每一條**跑 pipeline 的路（2026-08-20 使用者回報）
# --------------------------------------------------------------------------- #
def test_the_preview_sees_the_second_lot(window, lots):
    """使用者：「載入 image（RSEM 的 GT）不會有圖，拉過去 Align 也沒有圖」。

    原因不是圖檔格式 —— 是 `run_batch` 那條路傳了 `sources`，而**單顆預覽那條
    沒有**。於是同一份 pipeline「試跑」有圖、切換 defect 沒圖，而使用者看到的
    是「載進來就是沒有圖」，那句話怎麼查都查不到真正的原因上。
    """
    from d4t.ui.workers import PreviewWorker

    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    load = window.model.node_order[0]
    pair = window.model.add_step("pair_source")
    align = window.model.add_step("align_to")
    window.attach_pair_source(pair, lots["gt"]["klarf"], sync=True)
    window._connect(load, align, "test", dst_in="template")
    window._connect(pair, align, "paired", dst_in="search")

    r = PreviewWorker.run_sync(window.model.to_recipe(), window.dataset.items[0],
                               window.model.kind,
                               sources=window.sources_for_run())
    assert r.ok, r.error
    assert "paired" in r.context.images and "aligned" in r.context.images

    # 沒帶的話就是使用者遇到的那個症狀 —— 這一行是為了證明上面那一行不是
    # 湊巧成立的。
    blind = PreviewWorker.run_sync(window.model.to_recipe(),
                                   window.dataset.items[0], window.model.kind)
    assert not blind.ok and "no lot is loaded" in str(blind.error)


def test_the_answer_to_which_second_lots_lives_in_one_place(window, lots):
    """`sources_for_run()` 是那個答案的**唯一**去處。"""
    assert window.sources_for_run() == {}          # 還沒載資料
    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    assert window.sources_for_run() == {}          # 載了 main，還沒掛第二份

    pair = window.model.add_step("pair_source")
    window.attach_pair_source(pair, lots["gt"]["klarf"], sync=True)
    sid = window.model.nodes[pair].params["source"]
    got = window.sources_for_run()
    assert list(got) == [sid] and len(got[sid]) == 5
    # 送進去的是 items，不是整個 Dataset（KlarfDoc 刻意不進 worker）
    assert not hasattr(got[sid], "klarf")


def test_every_path_that_runs_a_defect_passes_the_second_lot():
    """便利貼：**下一條單顆的路也躲不掉**。

    這個 bug 的形狀是「傳了四條路裡的三條」，而漏掉的那一條要跑起來才看得見。
    所以這裡直接掃原始碼：`d4t/ui` 底下每一個 `run_defect(...)` 呼叫都要帶
    `sources=`。掃字串是刻意的 —— 它擋得住「新加一條路而忘了傳」。
    """
    import ast

    ui = Path(__file__).resolve().parent.parent / "d4t" / "ui"
    missing = []
    for path in sorted(ui.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "run_defect":
                continue
            if not any(kw.arg == "sources" for kw in node.keywords):
                missing.append("%s:%d" % (path.name, node.lineno))
    assert not missing, (
        "這幾個地方跑了一顆 defect 但沒有把第二份 lot 送進去 —— "
        "有配對卡的 pipeline 在那裡會變成「沒有圖」：%s" % missing)


def test_the_image_shows_up_as_soon_as_the_second_lot_is_attached(qapp, window,
                                                                  lots):
    """按完 `Open data…` **畫面要有反應**。

    以前掛完只重整了畫布與 lint，預覽沒有重跑 —— 於是影像流的下拉裡沒有
    `paired`，要再去點一張卡才會出現。而「按了鈕、畫面沒事發生」讀起來就是
    「載不進來」，那正是使用者連續兩次回報的那句話。
    """
    def names():
        return [window.stream_combo.itemText(i)
                for i in range(window.stream_combo.count())]

    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    _pump(qapp, lambda: "test" in names())
    assert "paired" not in names()

    nid = _pair_node(window)                     # 使用者按鈕之前一定先點了卡
    window.attach_pair_source(nid, lots["gt"]["klarf"], sync=True)

    assert _pump(qapp, lambda: "paired" in names()), names()
    # 而且畫面直接跳到那張卡吐的那條流 —— 不用自己去下拉裡找
    assert window.stream_combo.currentText() == "paired"


def test_the_aligned_image_needs_the_align_card_selected(qapp, window, lots):
    """預覽**只跑到選中的那張卡為止** —— 那是刻意的（點哪張卡就看哪張卡）。

    所以停在 `Pair` 上是看不到 `aligned` 的，那不是壞掉。這一條把那件事釘住，
    因為它看起來很像「對圖沒有作用」。
    """
    def names():
        return [window.stream_combo.itemText(i)
                for i in range(window.stream_combo.count())]

    window.load_dataset_path(lots["main"]["klarf"], sync=True)
    load = window.model.node_order[0]
    pair = window.model.add_step("pair_source")
    align = window.model.add_step("align_to")
    window.select_node(pair)
    window.attach_pair_source(pair, lots["gt"]["klarf"], sync=True)
    window._connect(load, align, "test", dst_in="template")
    window._connect(pair, align, "paired", dst_in="search")

    window.select_node(pair)
    assert _pump(qapp, lambda: "paired" in names())
    assert "aligned" not in names()              # 停在 Pair 上：還沒跑到那裡

    window.select_node(align)
    assert _pump(qapp, lambda: "aligned" in names()), names()
    assert window.stream_combo.currentText() == "aligned"


def test_h2h_marks_are_drawn_solid_but_the_scan_line_cards_are_not(qapp):
    """「線畫到幾乎看不見」是為 **CD 的幾十條掃描線**寫的規矩 —— 線只是說那個
    判斷在哪一列上做的，點才是答案。

    H2H 交的是**結構**：少少幾條，而線本身就是答案（一個框、一個十字）。
    那時候淡化不是在減少雜訊，是在**藏起唯一的資訊**（使用者：「預覽框太不
    明顯了」）。所以是**卡片自己宣告**的一格，而不是把畫法改掉 ——
    CD 與 GLV 都刻意靠淡化（GLV：描邊會跟區域框重疊，等於沒畫）。
    """
    from d4t.core.pipeline.step import REGISTRY

    assert REGISTRY["align_to"].marks_solid is True
    for key in ("cd_measure", "glv_stats"):
        assert REGISTRY[key].marks_solid is False, key


def test_the_view_remembers_whether_to_draw_them_solid(qapp):
    from d4t.ui.widgets import ImageView

    v = ImageView()
    v.set_marks([[(0.1, 0.1), (0.9, 0.1)]], [[]], -1, [])
    assert v._marks_solid is False              # 預設不變
    v.set_marks([[(0.1, 0.1), (0.9, 0.1)]], [[]], -1, [], solid=True)
    assert v._marks_solid is True
    v.clear_marks()
    assert v._marks_solid is False


def test_studio_asks_the_card_not_itself(window):
    """「幾條線算少」是卡片自己才知道的事。"""
    h2h = window.model.add_step("align_to")
    window.select_node(h2h)
    assert window._marks_solid() is True
    glv = window.model.add_step("glv_stats")
    window.select_node(glv)
    assert window._marks_solid() is False


def test_the_two_marks_are_different_colours(qapp):
    """紅框＝對到哪、綠十字＝瞄準哪 —— 兩個同色的話，畫面上分不出哪個是哪個
    （使用者：「預覽也分」）。"""
    from d4t.core.steps.align_to import MARK_AIM, MARK_MATCH
    from d4t.ui.widgets import MARK_ROLE_TOKENS

    # 卡片只說**角色**，顏色是 UI 挑的（core 不得 import Qt）
    assert MARK_ROLE_TOKENS[MARK_MATCH] != MARK_ROLE_TOKENS[MARK_AIM]
    # 角色名以 `!` 開頭 —— 那不是一個區域名（沿用 decide_tree 的慣例）
    for role in (MARK_MATCH, MARK_AIM):
        assert role.startswith("!"), role


def test_both_themes_have_the_colours_the_roles_ask_for(qapp):
    """角色指的是**權杖**不是色碼，所以 light / dark 兩套都要有。"""
    from d4t.ui import theme as theme_mod
    from d4t.ui.widgets import MARK_ROLE_TOKENS

    for name in ("light", "dark"):
        theme_mod.apply_theme(qapp, name)
        for token in MARK_ROLE_TOKENS.values():
            assert theme_mod.TOKENS.get(token), (name, token)
    theme_mod.apply_theme(qapp, "light")        # 收拾乾淨


def test_the_card_labels_every_mark_with_its_role(qapp):
    from d4t.core.pipeline import get_step
    from d4t.core.pipeline.context import Context
    from d4t.core.steps.align_to import MARK_AIM, MARK_MATCH

    ctx = Context()
    ctx.meta["align_to"] = {"x": 120.0, "y": 60.0, "search": "single",
                            "size": [40, 40], "shape": [200, 200],
                            "expected": [80.0, 80.0]}
    lines, points, _focus, labels = get_step("align_to").overlay_marks(
        ctx, {}, "single")
    assert len(labels) == len(lines) == len(points)   # 三串要等長
    assert labels[:4] == [MARK_MATCH] * 4             # 框
    assert set(labels[4:]) == {MARK_AIM}              # 十字

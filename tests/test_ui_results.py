# F7-5 驗收：Results 視窗 —— 跑完才有意義的東西不該常駐在編輯畫面上。
"""主視窗只留「編流程 + 看單顆」；分數分佈、Gallery、輸出搬到 Results 視窗。

最重要的一條是最後那個測試：**搬家不可以弄丟秒回**。拖門檻線走的是
``viewmodel.rebin()`` 的純計算路徑（不重跑影像），這是這個工具調參迴圈的
一半價值，換視窗時最容易不小心接成「每動一次就重跑」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "recipes" \
    / "die_to_die_basic.json"


def _import_qt(g):
    from PySide6.QtWidgets import QApplication

    from d4t.ui import results as results_mod
    from d4t.ui import studio as studio_mod
    from d4t.ui import theme as theme_mod
    from d4t.ui import viewmodel as vm_mod
    g.update(QApplication=QApplication, results_mod=results_mod,
             studio_mod=studio_mod, theme_mod=theme_mod, vm_mod=vm_mod)


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    theme_mod.apply_theme(app)
    yield app


@pytest.fixture(scope="module")
def lot(tmp_path_factory):
    from make_sample import generate
    return generate(str(tmp_path_factory.mktemp("f7_results")), n=8, seed=7)


@pytest.fixture(scope="module")
def window(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    win.load_dataset_path(lot["klarf"], sync=True)
    win.load_recipe_path(str(EXAMPLE), sync=True)
    yield win
    win.close()


# --------------------------------------------------------------------------- #
# 1. 主視窗乾淨了
# --------------------------------------------------------------------------- #
def test_main_window_keeps_only_the_editing_surface(window):
    root = window.root_splitter
    assert [root.widget(i) for i in range(root.count())] == [
        window.library, window.canvas_column, window.preview_pane]
    assert window.histogram.parent() is not window
    assert window.gallery.parent() is not window


def test_preview_gets_the_widest_column(window):
    """使用者要求「影像大一點」—— 單顆預覽要拿到最寬的一欄。

    看的是**設定值**而不是 ``sizes()``：QSplitter 要視窗真的 show 過才會排版，
    離屏測試裡 ``sizes()`` 只會回一組沒有意義的相等數字。
    """
    lib, mid, preview = studio_mod.COLUMN_SIZES
    assert preview == max(studio_mod.COLUMN_SIZES)
    assert preview > lib + mid * 0.5, studio_mod.COLUMN_SIZES
    assert window.root_splitter.count() == 3


def test_results_window_is_not_shown_until_there_is_something_to_show(qapp, lot):
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert win.results_visible() is False
        assert win.results.summary_text() == "No results yet."
        assert win.results.btn_run_all.isEnabled() is False
    finally:
        win.close()


# --------------------------------------------------------------------------- #
# 2. 跑完就把結果端出來
# --------------------------------------------------------------------------- #
def test_running_populates_and_presents_the_results_window(window):
    assert window.run_trial(8, workers=1, sync=True) is True

    assert window.results_visible() is True, "按 Run 想看的就是這個"
    assert window.histogram.has_data() is True
    assert window.gallery.displayed_count() == 8
    assert window.results.btn_run_all.isEnabled() is True

    summary = window.results.summary_text()
    assert "8 defects" in summary and "8 ok" in summary and "0 failed" in summary


def test_summary_line_reports_counts_and_score_span():
    text = results_mod.summarize_run(10, 9, 1.25, [3.0, 7.5, 1.0])
    assert "10 defects" in text and "9 ok" in text and "1 failed" in text
    assert "1.25 s" in text or "1.2 s" in text
    assert "1 – 7.5" in text

    assert "score" not in results_mod.summarize_run(2, 2, 0.1, [])


def test_the_write_button_in_results_reaches_the_studio(window):
    """試跑看起來對了之後的**下一步**：整批跑一次並照 Output 卡寫出去。

    F16 Stage 5c 之前這顆鈕開的是輸出精靈。精靈拿掉之後它接的是同一件事的
    另一半 —— 而「寫什麼、寫去哪」現在在畫布上看得見。
    """
    window.run_trial(8, workers=1, sync=True)
    seen = []
    window.results.run_all_requested.connect(lambda: seen.append(True))
    window.results.btn_run_all.click()
    assert seen, "Results 視窗那顆鈕要接回 Studio 的整批入口"


# --------------------------------------------------------------------------- #
# 3. **搬家不可以弄丟秒回**
# --------------------------------------------------------------------------- #
def test_threshold_drag_is_still_the_pure_rescore_path(window):
    """拖曳中只重算 bin 數（不寫 model、不重跑影像），放開才 commit。"""
    window.run_trial(8, workers=1, sync=True)
    window._on_threshold_committed(40.0)
    before = window.model.threshold

    window._on_threshold_changed(77.25)
    assert window.model.threshold == pytest.approx(before), \
        "拖曳中絕對不可以動到 model —— 那會觸發重跑"
    live = window.histogram.bin_summary_text()
    # 前綴比對：合成資料旁邊有 ground_truth.json，同一行後面還會接一段準確率
    # （Phase 1）。這一條要驗的是 bin 數跟著門檻走，不是那一行長什麼樣子。
    assert live.startswith("   ".join(
        "bin %s=%s" % (k, v)
        for k, v in sorted(vm_mod.rebin(window.trial_scores, 77.25,
                                        window.model.bins).items())))

    window._on_threshold_committed(55.0)
    assert window.model.threshold == pytest.approx(55.0)


def test_bar_click_filters_the_gallery_in_the_same_window(window):
    window.run_trial(8, workers=1, sync=True)
    lo, hi = window.histogram.bar_range(0)
    window.histogram.bar_clicked.emit(lo, hi)

    assert window.gallery.filter_text(), "點長條要篩 Gallery"
    assert window.results_visible() is True
    # 再點同一根 = 取消
    window.histogram.bar_clicked.emit(lo, hi)
    assert window.gallery.filter_text() == ""


def test_closing_results_does_not_lose_them(window):
    window.run_trial(8, workers=1, sync=True)
    window.results.close()
    assert window.results_visible() is False
    assert window.trial_results, "關掉視窗不該丟掉結果"

    window.show_gallery()
    assert window.results_visible() is True
    assert window.gallery.displayed_count() == 8


# --------------------------------------------------------------------------- #
# 4. Spread 的新家（F18 第 2 步）
# --------------------------------------------------------------------------- #
def test_spread_moved_here_and_lists_the_features_that_really_ran(window):
    """量測卡的儀表以前放整批的分佈，而它在跑之前永遠是空的。

    使用者原話：「他在 run 之前都是空的，我覺得這塊 UI 可以放別的」。
    它真正回答的問題（這個特徵分不分得開）是跑完才問得出來的 —— 而這個視窗
    本來就是「跑完才有意義的東西」的家。
    """
    assert window.run_trial(8, workers=1, sync=True) is True
    combo = window.results.feature_combo
    # ⚠ **預設不再是 Score**（R2，2026-08-24）：樹的 recipe 沒有分數表達式，
    # 開在 Score 上畫出來是一根柱子，什麼都沒說。現在開在「你的第一個問題問
    # 的那個數字」上 —— 而 Score 仍然選得到（下面那一行）。
    assert window.results.shown_feature() != window.results.SCORE
    names = [combo.itemData(i) for i in range(combo.count())]
    assert names[0] == window.results.SCORE
    # 下拉列的是**真的算出來的**那些（從結果讀，不是從 recipe 宣告讀）
    ran = set()
    for r in window.trial_results:
        ran |= set(r.get("features") or {})
    assert ran and set(names[1:]) == ran


def test_a_feature_spread_does_not_pretend_the_threshold_applies(window):
    """門檻是**分數**的門檻 —— 看別的特徵時整張圖唯讀。

    一條看起來能拖、拖了卻什麼都不會發生的線，比沒有線更糟；而拖得動又真的
    寫回去更糟 —— 那會拿一個跟畫面無關的值改掉 bin。
    """
    assert window.run_trial(8, workers=1, sync=True) is True
    feature = next(n for n in (window.results.feature_combo.itemData(i)
                               for i in range(window.results.feature_combo.count()))
                   if n != window.results.SCORE)

    window.results.show_feature(feature)
    assert window.histogram.is_interactive() is False
    assert window.histogram.threshold() is None
    assert window.histogram.has_data() is True
    assert feature in window.results.spread_hint_text() \
        or "defects" in window.results.spread_hint_text()

    # 拖不動：按下去不該有任何訊號
    fired = []
    window.histogram.threshold_committed.connect(fired.append)
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent
    pos = QPointF(window.histogram.width() / 2.0, window.histogram.height() / 2.0)
    window.histogram.mousePressEvent(
        QMouseEvent(QEvent.MouseButtonPress, pos, pos, Qt.LeftButton,
                    Qt.LeftButton, Qt.NoModifier))
    window.histogram.mouseReleaseEvent(
        QMouseEvent(QEvent.MouseButtonRelease, pos, pos, Qt.LeftButton,
                    Qt.NoButton, Qt.NoModifier))
    assert fired == []

    # ⚠ **選回 Score 之後門檻線也不一定回來**（R1，2026-08-24）。
    #
    # F25 之後每一份 recipe 一打開就是一棵樹，而樹判出來的 bin 跟門檻無關 ——
    # 那時候畫一條可以拖的線是在說一件不成立的話。實測過的下場：每一張縮圖
    # 說 `bin 3`，而 150px 底下的圖例說 `bin 1=24`，還附一行用那條門檻算出來
    # 的 `accuracy 50%`。同一批 24 顆，畫面上兩個答案。
    window.results.show_feature(window.results.SCORE)
    assert window.model.decide is not None, "這份 recipe 開起來就該是一棵樹"
    assert window.histogram.is_interactive() is False
    assert window.histogram.threshold() is None
    assert window.histogram.bin_summary_text() == "", \
        "樹判出來的顆數在判定段上，不該在這裡再講一次"
    assert window.results.spread_hint_text() == ""


def test_the_threshold_line_is_still_there_for_a_binary_recipe(window):
    """**而沒有判定樹的時候它要在。**

    這一條接住上面那一條讓出來的地盤：R1 拿掉的是「門檻在不該出現的時候
    出現」，不是門檻本身 —— 二元 score 那條老路仍然靠它調。
    """
    keep = window.model.decide
    try:
        window.model.decide = None
        window.results.show_feature(window.results.SCORE)
        window._refresh_spread()
        assert window.histogram.is_interactive() is True
        assert window.histogram.threshold() is not None
        assert "bin " in window.histogram.bin_summary_text()
    finally:
        window.model.decide = keep
        window._refresh_spread()


# --------------------------------------------------------------------------- #
# 三段（R2–R7，2026-08-24）：「目前的 results panel 太簡略了」
# --------------------------------------------------------------------------- #
def test_the_panel_says_what_came_out(window):
    """跑完之後第一個問題是「每一類各幾顆」，而這一頁以前答不出來。"""
    assert window.run_trial(8, workers=1, sync=True) is True
    rows = window.results.verdict.rows()
    assert rows, "跑完了卻沒有判定段"
    assert sum(r["count"] for r in rows) == 8, rows
    assert not window.results.verdict.isHidden()


def test_the_verdict_band_and_the_canvas_agree(window):
    """判定段與畫布的分支流量**吃同一份** —— 不是兩份各自數出來的。

    數第二份的那一份會漂，而漂掉的時候畫面上兩個數字對不起來，
    沒有人知道哪一個是對的。這一輪修的 R1 正是那個形狀。
    """
    from d4t.ui.tree_scene import decision_info

    assert window.run_trial(8, workers=1, sync=True) is True
    info = decision_info(window.model.decide, window.trial_results,
                         window.ground_truth)
    counts = (info or {}).get("counts") or {}
    for row in window.results.verdict.rows():
        if row["kind"] != "class":
            continue
        assert row["count"] == counts.get(row["key"], 0), row


def test_clicking_a_class_filters_the_gallery(window):
    assert window.run_trial(8, workers=1, sync=True) is True
    row = max((r for r in window.results.verdict.rows() if r["kind"] == "class"),
              key=lambda r: r["count"])
    window.results.verdict._on_row_clicked(row["key"])
    assert window.gallery.displayed_count() == row["count"]
    assert sorted(window.gallery.displayed_ids()) == sorted(row["ids"])
    # 再點一次 = 看全部（不必去找一顆「清除」的鈕）
    window.results.verdict._on_row_clicked(row["key"])
    assert window.gallery.displayed_count() == 8


def test_the_thumbnails_carry_the_name_the_user_typed(window):
    """縮圖底下第一行是**類別名**，不是 ``bin 3``（R5）。

    ⚠ 這份 fixture 的樹是從舊門檻自動轉過來的，所以它的葉子**本來沒有名字**
    —— 那時候第一行退回 ``bin N``（見下一條）。這裡先取名字，才問得出這一條。
    """
    for path, label in (("y", "bright blob"), ("n", "nuisance")):
        window.model.set_tree_leaf(path, label=label)
    assert window.run_trial(8, workers=1, sync=True) is True
    caps = [window.gallery.caption_at(i)
            for i in range(window.gallery.displayed_count())]
    assert caps, caps
    assert any("bright blob" in c or "nuisance" in c for c in caps), caps
    assert not [c for c in caps if c.startswith("bin ")], caps


def test_a_class_with_no_name_falls_back_to_its_bin_not_a_scolding(window):
    """**沒取名字的那一類就叫 ``bin 1``**，不是「(unnamed)」。

    一份從舊門檻自動轉過來的 recipe，它的每一片葉子本來就沒有名字 ——
    而 ``bin 1`` 至少是一個使用者認得、而且寫得回 KLARF 的東西；
    「(unnamed)」則是在指責他少做了一件事。
    """
    from PySide6.QtWidgets import QLabel

    for path in ("y", "n"):
        window.model.set_tree_leaf(path, label="")
    assert window.run_trial(8, workers=1, sync=True) is True
    texts = [w.text() for w in window.results.verdict.findChildren(QLabel)
             if w.text()]
    assert not [t for t in texts if "unnamed" in t.lower()], texts
    assert [t for t in texts if t.startswith("bin ")], texts
    caps = [window.gallery.caption_at(i)
            for i in range(window.gallery.displayed_count())]
    assert caps and all(c.startswith("bin ") for c in caps), caps


def test_the_table_holds_the_same_batch_as_the_tiles(window):
    """同一份資料兩種看法，不是兩個地方各存一份（R7）。"""
    assert window.run_trial(8, workers=1, sync=True) is True
    assert window.results.table.row_count() == window.gallery.total_count() == 8
    assert "class" in window.results.table.columns()
    window.results.show_view(1)
    assert window.results.shown_view() == 1
    window.results.show_view(0)
    assert window.results.shown_view() == 0


def test_the_status_bar_does_not_repeat_the_toolbar(window):
    """同一個事實兩個位置，遲早有一個先過期（R4）。

    工具列說 ``8 defects · 8 ok · 0 failed · 0.1 s``，而狀態列以前說
    ``Run finished: 8 defects (8 ok, 0 failed) in 0.1 s`` —— 隔 30px。
    """
    assert window.run_trial(8, workers=1, sync=True) is True
    assert "defects" in window.results.summary_text()
    assert window.results.status_text() == "", window.results.status_text()


def test_the_spread_opens_on_the_number_the_first_question_asks_about(window):
    """**不是空的 Score**（R2）。

    樹的 recipe 沒有分數表達式 → 每一顆都是 0 → 這一頁最大的那張圖畫出來是
    一根柱子，什麼都沒說。
    """
    assert window.model.decide is not None
    picked = window._default_spread_feature(window.trial_results)
    assert picked and picked != window.results.SCORE
    # 根是簡單條件時，挑的就**正好是它問的那個數字**；複合條件拆不開，
    # 那時候退回「這一批分得最開的那個」—— 兩條路都不會回空的 Score。
    from d4t.ui.tree_scene import display_tree, parse_simple_condition
    root = parse_simple_condition(str(display_tree(window.model.decide).when))
    if root:
        assert picked == root[0]
    assert picked in [window.results.feature_combo.itemData(i)
                      for i in range(window.results.feature_combo.count())]


def test_the_spread_is_coloured_by_class(window):
    """一根單色的長條答不出「這一段裡是哪一類」（R2 第二半）。

    而「分得開誰」正是看這張圖的人真正在問的事 —— 兩座駝峰各是什麼顏色，
    一眼就是答案。
    """
    for path, label in (("y", "bright"), ("n", "nuisance")):
        window.model.set_tree_leaf(path, label=label)
    assert window.run_trial(8, workers=1, sync=True) is True
    # ⚠ 染色是**看某個特徵**時的事。看「Score」時不染 —— 那條路上的類別就是
    # 門檻切出來的兩邊，而門檻線本身已經畫在那裡了（再上一次色是講兩次）。
    window.results.show_feature(_a_feature(window))
    segs = window.histogram.segments()
    assert segs is not None, "分布圖沒有照類別染色"
    used = {c for cell in segs for c, _n in cell}
    assert len(used) >= 2, used
    # 染出來的顆數不可以超過那一格的高度（否則會畫到框外）
    for i, cell in enumerate(segs):
        assert sum(n for _c, n in cell) <= window.histogram._counts[i], (i, cell)


def test_the_colours_are_the_ones_the_verdict_band_uses(window):
    """圖上的綠色跟判定段那一列的綠色**是同一個**。

    兩份色表的話，同一類在兩個地方是兩種顏色 —— 而使用者就是靠顏色把它們
    對起來的。
    """
    assert window.run_trial(8, workers=1, sync=True) is True
    window.results.show_feature(_a_feature(window))
    band = {str(r["colour"]) for r in window.results.verdict.rows()
            if r["kind"] == "class" and r["count"]}
    plot = {c for cell in (window.histogram.segments() or []) for c, _n in cell}
    assert plot and plot <= band, (plot, band)


def test_the_colours_account_for_exactly_the_defects_that_have_that_number(window):
    """換一個數字看，染的是**那個數字上的那些顆**。

    ⚠ 這一條**不比較「換之前跟換之後不一樣」**：合成資料上兩個特徵可能落在
    同一格，那時候兩份分段逐字相同，而那不是 bug。要驗的是守恆 ——
    每一格染出來的顆數加起來，正好等於「有這個數字、而且判進了某一類」的那些顆。
    """
    assert window.run_trial(8, workers=1, sync=True) is True
    for name in (window.results.feature_combo.itemData(i)
                 for i in range(window.results.feature_combo.count())):
        if name == window.results.SCORE:
            continue
        window.results.show_feature(name)
        segs = window.histogram.segments() or []
        painted = sum(n for cell in segs for _c, n in cell)
        classed = {did for r in window.results.verdict.rows()
                   if r["kind"] == "class" for did in r["ids"]}
        have = sum(1 for r in window.trial_results
                   if str(r.get("defect_id")) in classed
                   and isinstance((r.get("features") or {}).get(name),
                                  (int, float)))
        assert painted == have, (name, painted, have)


def _a_feature(window):
    """下拉裡任何一個真的特徵（不是「Score」）。"""
    return next(n for n in (window.results.feature_combo.itemData(i)
                            for i in range(window.results.feature_combo.count()))
                if n != window.results.SCORE)


def test_the_colours_follow_this_run_not_the_last_one(window):
    """**改了樹再跑一次，圖上的顏色要跟著這一批走。**

    這一條是實作時自己種的：分布圖的分段染色讀的是判定段算好的「哪一類是
    哪幾顆」，而判定段當初排在分布圖**後面**才更新 —— 於是圖上染的是上一批
    的類別。跑得完、有顏色、而且是錯的（這個 repo 最怕的那個形狀）。

    ⚠ 抓得到它的關鍵是**改變顏色本身**（換 bin），而不是只跑第二次：
    連跑兩次一樣的東西，上一批跟這一批的類別剛好相同，錯的順序也會通過。
    """
    window.model.set_tree_leaf("y", bin=2)
    assert window.run_trial(8, workers=1, sync=True) is True
    window.results.show_feature(_a_feature(window))   # 跑過才有得選
    before = {c for cell in (window.histogram.segments() or []) for c, _n in cell}

    window.model.set_tree_leaf("y", bin=5)      # 換一個 bin = 換一個顏色
    assert window.run_trial(8, workers=1, sync=True) is True
    after = {c for cell in (window.histogram.segments() or []) for c, _n in cell}
    band = {str(r["colour"]) for r in window.results.verdict.rows()
            if r["kind"] == "class" and r["count"]}

    assert after != before, "換了 bin，圖上的顏色卻沒變 —— 它染的是上一批"
    assert after <= band, (after, band)


# --------------------------------------------------------------------------- #
# 6. Results 有自己的入口（F48，2026-08-28）
# --------------------------------------------------------------------------- #
def test_results_has_a_button_of_its_own(qapp):
    """**還沒跑過也叫得出 Results 視窗。**

    使用者 2026-08-28：「可以改成加一個按鈕獨立呼叫一個視窗嗎（目前是跑完
    才會出來）」。在這之前只有兩條路會開它：跑完自動彈出、或在直方圖上點一根
    長條 —— 兩條都要先跑過一批，所以關掉之後想再看一次就只能再跑一次。
    （而 `results.py` 的檔頭一直寫著「關掉它不會丟掉結果」：結果確實還在，
    只是沒有一顆鈕叫得出來。）

    ⚠ 這一條用**自己的視窗**，不用 module 級的 `window` fixture ——
    它問的正是「一顆都還沒跑的時候」，而那個 fixture 已經載過資料了。
    """
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        assert not win.trial_results, "這一條要的是還沒跑過的狀態"
        assert win.results_visible() is False
        win.btn_results.click()
        assert win.results_visible() is True, "按了 Results 卻沒有視窗出來"

        # 空的時候要講得出**在等什麼**（F44 的 empty_reason 同一條規矩）。
        # 工具列上那句 `No results yet.` 答得出「是空的」，答不出「所以呢」。
        said = win.results.status_text()
        assert "Run trial" in said, said
    finally:
        win.close()


def test_the_results_button_is_actually_visible_at_the_default_size(qapp):
    """**放不下 = 沒有這顆鈕。**

    第一版把它加在工具列最右邊，而工具列在預設視窗大小下**已經是滿的**
    （內容 916 px / 視窗 948 px）—— Qt 於是把它收進右邊那個 ``»`` 溢位選單，
    `isVisible()` 是 False。一顆藏在兩層選單底下的鈕答不了使用者的要求。

    所以預設視窗大小改成由工具列的 `sizeHint` 決定。這一條守的是那個結論
    本身，而不是那個數字：**下一顆鈕加上去而放不下的時候，紅的是這裡。**
    """
    win = studio_mod.StudioWindow(show_welcome_on_start=False)
    try:
        win.show()
        QApplication.instance().processEvents()
        assert win.btn_results.isVisible(), (
            "Results 掉進工具列的溢位選單了 —— 視窗預設 %d px，工具列要 %d px"
            % (win.width(), win.toolbar.sizeHint().width()))
        for act in win.toolbar.actions():
            if win.toolbar.widgetForAction(act) is win.btn_results:
                break
        else:
            raise AssertionError("btn_results 建了，但沒有加到工具列上")
    finally:
        win.hide()
        win.close()

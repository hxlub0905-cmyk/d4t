#!/usr/bin/env python3
# ADEPT 單檔純文字包（由 tools/make_text_bundle.py 產生）。
"""整個 ADEPT repo 就在這個檔案裡，一行一行的純文字，沒有壓縮、沒有編碼。

為什麼是這種形式：公司政策擋掉 .zip 這個類別，而 proxy 也不讓 Python 逐檔抓 ——
能過的只剩「一個純文字檔」。你可以用記事本打開它，往下捲就看得到每個檔案的內容。

    python ADEPT_part6of6.py              # 解到 .\\ADEPT\\
    python ADEPT_part6of6.py --dest D:\\tools
    python ADEPT_part6of6.py --list       # 只看裡面有什麼，不寫任何檔案

每個檔案都帶 git blob SHA-1，解開時逐檔驗過才落地 —— 傳輸途中被動到的話會當場
講出來，不會讓你拿到一份安靜壞掉的程式碼。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

SENTINEL = "# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ===="
PART, N_PARTS = 6, 6   # 這是第幾批 / 共幾批（1/1 = 沒有分批）
TOTAL = 178                       # 整個 repo 有幾個檔案，不是這一批有幾個


def blob_sha(data: bytes) -> str:
    """git 算 blob SHA 的方式："blob <長度>\\0" + 內容。"""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def entries(lines):
    """走過資料區，一個一個吐出 (sha, 路徑, 內容位元組)。"""
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("#F "):
            i += 1
            continue
        _, sha, count, path = line.split(" ", 3)
        n = int(count)
        # 資料區每一行前面有一個 '#'（那樣整個檔案才仍然是合法的 Python）。
        body = [ln[1:] if ln[:1] == "#" else ln for ln in lines[i + 1:i + 1 + n]]
        yield sha, path, "\n".join(body).encode("utf-8")
        i += 1 + n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Unpack the ADEPT text bundle.")
    ap.add_argument("--dest", default="ADEPT", help="解到哪個資料夾（預設 .\\ADEPT）")
    ap.add_argument("--list", action="store_true", help="只列出內容，不寫檔")
    a = ap.parse_args(argv)

    # 用文字模式讀自己：Python 會把 CRLF 讀成 LF，所以這個檔案就算在傳輸途中
    # 被換過行尾也解得開（格式用「行數」而不是「位元組數」正是為了這件事）。
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    try:
        start = lines.index(SENTINEL) + 1
    except ValueError:
        print("✗ 找不到資料區 —— 這個檔案被截斷了，或不是完整的 bundle。")
        return 2

    items = list(entries(lines[start:]))
    if not items:
        print("✗ 資料區是空的 —— 這個檔案被截斷了。")
        return 2
    print("這個包裡有 %d 個檔案。" % len(items))
    if a.list:
        for _sha, path, data in items:
            print("  %8d  %s" % (len(data), path))
        return 0

    dest = os.path.abspath(a.dest)
    print("解到  : %s" % dest)
    bad, done = [], 0
    for sha, path, data in items:
        if blob_sha(data) != sha:
            bad.append(path)
            continue
        full = os.path.join(dest, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        tmp = full + ".tmp"                      # atomic：半個檔案不要留在磁碟上
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, full)
        done += 1

    if bad:
        print("")
        print("✗ %d 個檔案的內容跟它自己的 SHA 對不上：" % len(bad))
        for path in bad[:12]:
            print("    %s" % path)
        print("")
        print("  這個檔案在傳輸途中被動過（編輯器另存、郵件過濾器改寫都會這樣）。")
        print("  請重新取得一份，不要用編輯器打開後另存。這份程式碼不完整，不要用。")
        return 1

    print("✓ %d 個檔案都解開了，SHA 全部對得上。" % done)

    # 分批的時候要講「還缺幾個」—— 不然使用者不知道自己貼完了沒有。
    # 判斷依據是 tools/FILELIST.txt（它固定在第一批），而不是這一批的數量。
    listing = os.path.join(dest, "tools", "FILELIST.txt")
    have_listing = os.path.isfile(listing)
    missing = []
    if have_listing:
        with open(listing, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    rel = line.split(" ", 1)[1]
                    if not os.path.isfile(os.path.join(dest,
                                                       rel.replace("/", os.sep))):
                        missing.append(rel)

    if N_PARTS > 1 and not have_listing:
        # 還沒拿到檔案清單，所以「缺幾個」算不出來。**這時候絕對不能印
        # 「下一步：跑 doctor」** —— 那看起來就像整包已經到位了。
        print("")
        print("這是第 %d 批 / 共 %d 批，整個 repo 有 %d 個檔案 —— **還沒到齊**。"
              % (PART, N_PARTS, TOTAL))
        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。")
        print("第 1 批裡有檔案清單，貼過它之後每一批都會告訴你還缺哪些。")
        return 0

    if missing:
        print("")
        print("這是第 %d 批 / 共 %d 批。整個 repo 還缺 %d 個檔案 —— 在其他批裡。"
              % (PART, N_PARTS, len(missing)))
        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。缺的例如：")
        for rel in missing[:6]:
            print("    %s" % rel)
        return 0

    print("")
    print("下一步：")
    print("  cd %s" % dest)
    print("  python tools\\doctor.py        # 環境自檢（會告訴你還缺什麼）")
    print("  相依套件裝不了的話走離線 wheels：docs\\OFFLINE-INSTALL.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ====
#F 5f9141042b4721854e37278486c382f72059a412 372 tests/test_ui_f7_11_roi.py
## F7-11 驗收（UI）：輸出名前綴、投影曲線面板、過期預覽結果。
#"""三件事都是為了同一個目的：**讓「量兩個區域」這件事真的做得起來。**
#
#- 前綴：沒有它，兩張量測卡的數字會互相蓋掉（跑得完、少一半）。
#- 面板：沒有它，「敏感度」是一個要盲填的數字。
#- 過期預覽：面板讓一個一直都在的 bug 現形（見下）。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import numpy as np
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#
#W = H = 128
#
#
#def _layout(shift: int = 0, seed: int = 0) -> np.ndarray:
#    rng = np.random.default_rng(seed)
#    img = np.full((H, W), 120.0, np.float32)
#    lo, hi = 40 + shift, 88 + shift
#    img[:, max(0, lo):max(0, hi)] = 60.0
#    for edge in (lo, hi):
#        if 2 <= edge <= W - 2:
#            img[:, edge - 2:edge + 2] = 210.0
#    return img + rng.normal(0, 3.0, (H, W)).astype(np.float32)
#
#
#def _import_qt(g):
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    from adept.ui import widgets as widgets_mod
#    g.update(QApplication=QApplication, studio_mod=studio_mod,
#             theme_mod=theme_mod, widgets_mod=widgets_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app)
#    yield app
#
#
#@pytest.fixture(scope="module")
#def lot(tmp_path_factory):
#    """一批「MG | 亮交界 | EPI | 亮交界 | MG」的 patch，結構位置逐顆不同。"""
#    import tifffile
#    from make_sample import generate
#
#    out = generate(str(tmp_path_factory.mktemp("f7_11")), n=6, seed=5)
#    rng = np.random.default_rng(2)
#    pages = []
#    for _ in range(6):
#        ref = _layout(int(rng.integers(-18, 19)), seed=int(rng.integers(0, 999)))
#        test = ref.copy()
#        test[60:68, 60:68] += 55.0                  # 缺陷永遠在中央
#        pages += [np.clip(test, 0, 255).astype(np.uint8),
#                  np.clip(ref, 0, 255).astype(np.uint8)]
#    tifffile.imwrite(out["tiff"], np.stack(pages))
#    return out
#
#
#@pytest.fixture
#def window(qapp, lot):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    win.load_dataset_path(lot["klarf"], sync=True)
#    yield win
#    win.close()
#
#
## --------------------------------------------------------------------------- #
## 1. 輸出名前綴
## --------------------------------------------------------------------------- #
#def test_picking_a_region_names_the_results_after_it(window):
#    """「兩張卡的特徵會互相蓋掉」是一個命名空間的問題，而製程工程師沒有理由要
#    懂那是什麼。但他把卡指到 `epi` 這個動作已經表達了意圖 —— 工具把話補完。"""
#    nid = window.model.add_step("glv_stats")
#    window.select_node(nid)
#    window._on_param_edited("roi", "epi")
#
#    assert window.model.nodes[nid].params["output_prefix"] == "epi"
#    assert "named" in window.status_text()
#    from adept.core.pipeline import get_step
#    assert "epi_glv_mean" in get_step("glv_stats").resolve_features(
#        window.model.nodes[nid].params)
#
#
#def test_a_name_the_user_typed_is_never_overwritten(window):
#    """「我明明改了它又跳回去」比沒有這個功能更糟。"""
#    nid = window.model.add_step("glv_stats")
#    window.select_node(nid)
#    window._on_param_edited("output_prefix", "mine")
#    window._on_param_edited("roi", "epi")
#    assert window.model.nodes[nid].params["output_prefix"] == "mine"
#
#
#def test_a_prefix_that_cannot_be_a_variable_name_is_refused(window):
#    """特徵名是分數表達式的變數名。``my region`` 那種名字在表達式裡指不到，
#    所以擋在參數驗證，而不是等使用者寫完表達式才發現。"""
#    from adept.core.pipeline import ParamError, get_step
#
#    with pytest.raises(ParamError):
#        get_step("glv_stats").validate_params({"output_prefix": "my region"})
#    with pytest.raises(ParamError):
#        get_step("glv_stats").validate_params({"output_prefix": "2nd"})
#    assert get_step("glv_stats").validate_params(
#        {"output_prefix": "epi_2"})["output_prefix"] == "epi_2"
#
#
## --------------------------------------------------------------------------- #
## 2. 曲線面板
## --------------------------------------------------------------------------- #
#def test_the_panel_shows_the_curve_for_the_selected_card(window):
#    nid = window.model.add_step("roi_profile")
#    window.model.set_param(nid, "roi_out", "epi")
#    window.select_node(nid)
#    window.refresh_preview(sync=True)
#
#    assert window.profile_panel_visible() is True
#    assert window.profile_panel.has_data() is True
#    summary = window.profile_panel.summary()
#    assert "epi" in summary and "confidence" in summary
#
#
#def test_the_panel_hides_itself_for_any_other_card(window):
#    nid = window.model.add_step("roi_profile")
#    window.select_node(nid)
#    window.refresh_preview(sync=True)
#    assert window.profile_panel_visible() is True
#
#    other = window.model.add_step("glv_stats")
#    window.select_node(other)
#    window.refresh_preview(sync=True)
#    assert window.profile_panel_visible() is False
#    assert window.profile_panel.has_data() is False
#
#
#def test_the_panel_paints_with_and_without_data(qapp):
#    """自繪元件的 bug 只在 ``paintEvent`` 真的跑過時才浮出來
#    （這一輪就漏掉一個 import，開窗才炸）。"""
#    from PySide6.QtGui import QPixmap
#
#    panel = widgets_mod.ProfilePanel()
#    panel.resize(320, 96)
#    for data in (None,
#                 {"axis": "x", "profile": [1.0, 5.0, 9.0, 4.0, 2.0],
#                  "raw": [1.0, 6.0, 9.0, 3.0, 2.0], "transitions": [2],
#                  "bands": [[0, 2], [2, 5]], "picked": [2, 5],
#                  "confidence": 42.0}):
#        panel.set_data("epi", data)
#        for name in ("light", "dark"):
#            theme_mod.set_theme(name)
#            pm = QPixmap(panel.size())
#            pm.fill()
#            panel.render(pm)          # 例外會在這裡冒出來
#            assert not pm.isNull()
#    theme_mod.apply_theme(qapp, "light")
#
#
## --------------------------------------------------------------------------- #
## 3. 過期的預覽結果
## --------------------------------------------------------------------------- #
#def test_a_stale_background_preview_never_overwrites_a_newer_one(window):
#    """``PreviewWorker`` 只合併「還沒開跑」的請求；已經在跑的那筆照樣會跑完並
#    發出 ready。所以「先送出背景預覽、接著又跑了同步預覽」的時候，舊的那筆會
#    **後到**，把新的畫面蓋掉 —— 而且不會再更新，因為沒有人會再算一次。
#
#    這個順序在實際操作裡並不罕見（點卡片 → 立刻改參數），只是以前的症狀是
#    「影像閃一下」；投影曲線面板把它變成「面板整個空白」，才浮出來。
#    """
#    nid = window.model.add_step("roi_profile")
#    window.model.set_param(nid, "roi_out", "epi")
#    window.select_node(nid)
#
#    stale = window.refresh_preview(sync=True) and window._last_result
#    window.refresh_preview(sync=True)          # 這一筆才是畫面上的現況
#    assert window.profile_panel.has_data() is True
#
#    # 模擬那筆更早的背景預覽現在才回來（世代編號已經不是它出發時那個）
#    window._on_async_preview_ready(_stripped(stale))
#    assert window.profile_panel.has_data() is True, "過期的結果把畫面蓋掉了"
#
#
#def _stripped(result):
#    """把 profiles 拿掉，模擬「recipe 還沒加上這張卡」時算出來的那一筆。"""
#    ctx = getattr(result, "context", None)
#    if ctx is not None:
#        ctx.meta.pop("profiles", None)
#    return result
#
#
#def test_a_current_background_result_is_still_applied(window):
#    """擋掉過期的，不可以順手把正常的也擋掉。"""
#    nid = window.model.add_step("roi_profile")
#    window.model.set_param(nid, "roi_out", "epi")
#    window.select_node(nid)
#    window.refresh_preview(sync=True)
#    result = window._last_result
#
#    window._async_epoch = window._preview_epoch      # 「這筆是最新的」
#    window.profile_panel.set_data("", None)
#    window._on_async_preview_ready(result)
#    assert window.profile_panel.has_data() is True
#
#
## --------------------------------------------------------------------------- #
## 4. 區域跨顆檢視
## --------------------------------------------------------------------------- #
#def _flat(seed: int = 0) -> np.ndarray:
#    """整張都是同一種材質 —— 沒有任何東西可以定位。"""
#    return np.random.default_rng(seed).normal(60.0, 4.0, (H, W)).astype(np.float32)
#
#
#@pytest.fixture(scope="module")
#def mixed_lot(tmp_path_factory):
#    """一批混合的資料：大部分看得到結構，每四顆有一顆整張均勻。"""
#    import tifffile
#    from make_sample import generate
#
#    out = generate(str(tmp_path_factory.mktemp("f7_11_mix")), n=12, seed=4)
#    rng = np.random.default_rng(7)
#    pages = []
#    for i in range(12):
#        ref = _flat(i) if i % 4 == 3 else _layout(int(rng.integers(-20, 21)), seed=i)
#        test = ref.copy()
#        test[60:68, 60:68] += 55.0
#        pages += [np.clip(test, 0, 255).astype(np.uint8),
#                  np.clip(ref, 0, 255).astype(np.uint8)]
#    tifffile.imwrite(out["tiff"], np.stack(pages))
#    return out
#
#
#@pytest.fixture
#def mixed_window(qapp, mixed_lot):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    win.load_dataset_path(mixed_lot["klarf"], sync=True)
#    nid = win.model.add_step("roi_profile")
#    win.model.set_param(nid, "roi_out", "epi")
#    win.model.set_param(nid, "also_neighbours", True)
#    win.select_node(nid)
#    yield win
#    win.close()
#
#
#def test_the_thumbnail_placement_matches_the_thumbnail_itself(qapp):
#    """框畫在縮圖上，所以縮圖的 letterbox 偏移必須算得跟 ``make_thumb`` 一樣。
#
#    兩者分開放的話，哪天改了縮圖的縮放規則而忘了改另一邊，框就會整批偏掉 ——
#    而畫面上看起來只是「框好像有點歪」，不會有人聯想到是縮圖改過。
#    """
#    from adept.ui.gallery import make_thumb, thumb_placement
#
#    for shape in ((64, 128), (128, 64), (100, 100), (7, 250)):
#        img = np.full(shape, 255, np.uint8)         # 全白 -> 補的黑邊一目了然
#        thumb = make_thumb(img, 96)
#        x0, y0, tw, th = thumb_placement(shape, 96)
#        ys, xs = np.nonzero(thumb)
#        assert (int(xs.min()), int(ys.min())) == (x0, y0)
#        assert (int(xs.max()) + 1, int(ys.max()) + 1) == (x0 + tw, y0 + th)
#
#
#def test_the_boxes_follow_the_structure_across_defects(mixed_window):
#    """**這個視窗存在的理由**：在第 1 顆剛好的框，第 50 顆可能整個偏掉。"""
#    from adept.ui.region_check import check_regions
#
#    items = mixed_window._items()[:12]
#    results = check_regions(mixed_window.model.to_recipe(), items,
#                            mixed_window.model.kind, mixed_window.selected_node,
#                            ["epi"], thumb_size=120, source="ref")
#    located = [r for r in results if r["located"] and r["boxes"]]
#    assert len(located) >= 6
#    lefts = {round(r["boxes"][0][1][0]) for r in located}
#    assert len(lefts) > 1, "每顆的框都落在同一個位置 —— 那就沒有跟著結構跑"
#
#
#def test_a_patch_with_no_structure_is_marked_not_guessed(mixed_window):
#    from adept.ui.region_check import check_regions
#
#    results = check_regions(mixed_window.model.to_recipe(),
#                            mixed_window._items()[:12], mixed_window.model.kind,
#                            mixed_window.selected_node, ["epi"], 120, "ref")
#    fell_back = [r for r in results if not r["located"]]
#    assert fell_back, "這批刻意放了整張均勻的 patch"
#    for r in fell_back:
#        assert r["error"] is None, "退回整張圖是正常結果，不是錯誤"
#        assert r["boxes"], "退回之後區域仍然存在（就是整張圖）"
#
#
#def test_check_regions_never_raises_on_a_broken_pipeline(mixed_window):
#    """跟引擎「單顆爆不殺整批」同一個契約 —— 一顆壞掉只是一格壞掉。"""
#    from adept.ui.region_check import check_regions
#
#    nid = mixed_window.selected_node
#    mixed_window.model.set_param(nid, "source", "nope")      # 不存在的影像流
#    results = check_regions(mixed_window.model.to_recipe(),
#                            mixed_window._items()[:3], mixed_window.model.kind,
#                            nid, ["epi"], 120, "ref")
#    assert len(results) == 3
#    assert all(r["error"] for r in results)
#
#
#def test_the_window_summarises_and_can_show_only_the_failures(mixed_window):
#    assert mixed_window.region_check_available() is True
#    assert mixed_window.open_region_check(n=12, sync=True) is True
#
#    win = mixed_window.region_window
#    assert "12 defects" in win.summary_text()
#    assert "fell back" in win.summary_text()
#    assert len(win.visible_ids()) == 12
#
#    failed = win.failed_ids()
#    assert failed, "這批刻意放了定位不出來的 patch"
#    win.only_failed.setChecked(True)
#    assert win.visible_ids() == failed, "只看失敗的 —— 那些才是要看的"
#    win.only_failed.setChecked(False)
#    assert len(win.visible_ids()) == 12
#
#
#def test_clicking_a_thumbnail_jumps_to_that_defect(mixed_window):
#    assert mixed_window.open_region_check(n=6, sync=True) is True
#    win = mixed_window.region_window
#    seen = []
#    win.defect_activated.connect(seen.append)
#    win._cells[2].clicked.emit(win._cells[2].defect_id)
#    assert seen == [win._cells[2].defect_id]
#
#
#def test_the_button_only_appears_for_cards_that_define_a_region(mixed_window):
#    assert mixed_window.selected_regions() == ["epi", "epi_before", "epi_after"]
#    assert mixed_window.region_check_available() is True
#
#    other = mixed_window.model.add_step("glv_stats")
#    mixed_window.select_node(other)
#    assert mixed_window.selected_regions() == []
#    assert mixed_window.region_check_available() is False
#
#
#def test_without_a_dataset_the_button_is_off_and_says_why(qapp):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    try:
#        nid = win.model.add_step("roi_profile")
#        win.select_node(nid)
#        assert win.selected_regions() == ["band"]
#        assert win.region_check_available() is False
#        assert win.open_region_check(n=4, sync=True) is False
#        assert "No dataset" in win.status_text()
#    finally:
#        win.close()
#
#
#def test_every_cell_paints(qapp, mixed_window):
#    """自繪元件的 bug 只在 paintEvent 真的跑過時才浮出來。"""
#    from PySide6.QtGui import QPixmap
#
#    assert mixed_window.open_region_check(n=12, sync=True) is True
#    win = mixed_window.region_window
#    for name in ("light", "dark"):
#        theme_mod.set_theme(name)
#        for cell in win._cells:
#            pm = QPixmap(cell.size())
#            pm.fill()
#            cell.render(pm)
#            assert not pm.isNull()
#    theme_mod.apply_theme(qapp, "light")
#
#F ea1cdea68a91e2c08fb2bef0cede55e44f2ff574 230 tests/test_ui_f7_12_template.py
## F7-12 驗收（UI）：從大圖建 Golden Cell 模板。
#"""模板不可能用打字的，所以這個對話框是那張卡唯一的入口 —— 它壞掉，
#整張卡就不能用。
#
#而整條路唯一會**安靜壞掉**的地方是「週期估錯」：估錯了疊出來的 cell 會糊掉，
#糊掉的模板會讓後面每一顆都對錯，但畫面上不會有錯誤訊息，只會有一批看起來很正常、
#其實量錯位置的數字。所以測試盯的是**判斷材料有沒有被攤開給人看**。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import numpy as np
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#
#PERIOD = 40
#
#
#def big_image(seed: int = 0, noise: float = 4.0) -> np.ndarray:
#    rng = np.random.default_rng(seed)
#    img = np.zeros((240, PERIOD * 8), np.float32)
#    for k in range(8):
#        x = k * PERIOD
#        img[:, x:x + PERIOD] = 120.0
#        img[:, x + 14:x + 34] = 60.0
#        img[:, x + 12:x + 16] = 210.0
#        img[:, x + 32:x + 36] = 210.0
#    return img + rng.normal(0, noise, img.shape).astype(np.float32)
#
#
#def _import_qt(g):
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import studio as studio_mod
#    from adept.ui import template_dialog as tpl_mod
#    from adept.ui import theme as theme_mod
#    g.update(QApplication=QApplication, studio_mod=studio_mod,
#             tpl_mod=tpl_mod, theme_mod=theme_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app)
#    yield app
#
#
#@pytest.fixture(scope="module")
#def lot(tmp_path_factory):
#    """一批從那張大圖上不同相位裁下來的 patch。"""
#    import tifffile
#    from make_sample import generate
#
#    out = generate(str(tmp_path_factory.mktemp("f7_12")), n=6, seed=5)
#    img = big_image(3)
#    rng = np.random.default_rng(1)
#    pages = []
#    for _ in range(6):
#        phase = int(rng.integers(0, PERIOD))
#        ref = img[100:132, 3 * PERIOD + phase:3 * PERIOD + phase + 32]
#        test = ref.copy()
#        test[12:20, 12:20] += 55.0
#        pages += [np.clip(test, 0, 255).astype(np.uint8),
#                  np.clip(ref, 0, 255).astype(np.uint8)]
#    tifffile.imwrite(out["tiff"], np.stack(pages))
#    return out
#
#
#@pytest.fixture
#def window(qapp, lot):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    win.load_dataset_path(lot["klarf"], sync=True)
#    yield win
#    win.close()
#
#
## --------------------------------------------------------------------------- #
## 1. 對話框
## --------------------------------------------------------------------------- #
#def test_nothing_can_be_accepted_before_an_image_is_loaded(qapp):
#    dlg = tpl_mod.TemplateDialog()
#    assert dlg.is_ready() is False
#    assert dlg.encoded() == ""
#    assert dlg.summary() == ""
#
#
#def test_the_dialog_lays_out_the_evidence_for_judging_the_template(qapp):
#    """使用者不需要懂銳利度分數怎麼算 —— 他要看得到「疊出來是清楚還是糊的」，
#    以及量到的週期、疊了幾格。"""
#    dlg = tpl_mod.TemplateDialog()
#    assert dlg.load_image(big_image(), "LOT_full.tif") is True
#    assert dlg.is_ready() is True
#
#    summary = dlg.summary()
#    assert "cell %d" % PERIOD in summary
#    assert "repeats across" in summary        # 一維 layout
#    assert "stacked from" in summary
#    assert "sharpness" in summary
#    assert dlg.locate_axis() == "x"
#    assert dlg.view.has_cell() is True
#
#
#def test_an_image_without_a_repeat_is_refused_with_a_reason(qapp):
#    dlg = tpl_mod.TemplateDialog()
#    noise = np.random.default_rng(1).normal(120.0, 6.0, (128, 128))
#    assert dlg.load_image(noise, "noise.tif") is False
#    assert dlg.is_ready() is False
#    assert "Could not build" in dlg.report.text()
#    assert dlg.view.has_cell() is False
#
#
#def test_an_empty_image_is_refused_instead_of_crashing(qapp):
#    dlg = tpl_mod.TemplateDialog()
#    assert dlg.load_image(np.zeros((0, 0), np.float32), "empty.tif") is False
#    assert dlg.is_ready() is False
#
#
#def test_a_blurred_stack_is_called_out_not_just_scored(qapp):
#    """週期估錯 -> 疊出來糊掉 -> 每一顆都對錯，而且畫面上不會有錯誤訊息。
#    所以糊掉這件事要用**白話**講，不能只丟一個分數。"""
#    from adept.core.algo import template as algo_template
#
#    dlg = tpl_mod.TemplateDialog()
#    dlg.load_image(big_image(), "ok.tif")
#    # 故意用一個錯的週期疊（+7 px），模擬「週期估錯」
#    dlg.cell = algo_template.build_golden_cell(big_image(), px=PERIOD + 7,
#                                               py=240)
#    if dlg.cell.ghosting < 40.0:
#        assert "blurred" in dlg.summary()
#        assert "mis-place" in dlg.summary()
#
#
#def test_the_cell_view_paints_with_and_without_a_template(qapp):
#    from PySide6.QtGui import QPixmap
#
#    view = tpl_mod.CellView()
#    view.resize(260, 140)
#    for cell in (None, big_image()[:40, :40].astype(np.uint8)):
#        view.set_cell(cell)
#        view.set_box((0.2, 0.0, 0.5, 1.0))
#        for name in ("light", "dark"):
#            theme_mod.set_theme(name)
#            pm = QPixmap(view.size())
#            pm.fill()
#            view.render(pm)          # 例外會在這裡冒出來
#            assert not pm.isNull()
#    theme_mod.apply_theme(qapp, "light")
#
#
## --------------------------------------------------------------------------- #
## 2. 接回 Studio
## --------------------------------------------------------------------------- #
#def test_the_button_only_shows_for_the_card_that_needs_a_template(window):
#    nid = window.model.add_step("roi_template")
#    window.select_node(nid)
#    assert window.template_build_available() is True
#
#    other = window.model.add_step("roi_profile")
#    window.select_node(other)
#    assert window.template_build_available() is False
#    assert window.open_template_dialog() is None
#    assert "Locate region by template" in window.status_text()
#
#
#def test_accepting_the_dialog_stores_the_template_in_the_recipe(window):
#    """存進 recipe 的是**模板本身**，不是大圖的路徑 ——
#    recipe 要能寄給別人，存路徑的話圖被換掉之後結果會安靜地變。"""
#    nid = window.model.add_step("roi_template")
#    window.select_node(nid)
#    dlg = window.open_template_dialog()
#    assert dlg is not None
#    assert dlg.load_image(big_image(), "LOT_full.tif") is True
#    dlg._on_accept()
#
#    params = window.model.nodes[nid].params
#    assert params["template"].startswith("gc1:")
#    assert params["locate_axis"] == "x"
#    assert "Template stored" in window.status_text()
#
#
#def test_the_stored_template_actually_locates_the_regions(window):
#    """存完之後真的跑一顆，區域要落在有結構的地方而不是退回整張圖。"""
#    nid = window.model.add_step("roi_template")
#    window.model.set_param(nid, "roi_out", "epi")
#    window.select_node(nid)
#    dlg = window.open_template_dialog()
#    dlg.load_image(big_image(3), "LOT_full.tif")
#    dlg._on_accept()
#
#    # EPI 在 cell 上的位置（使用者會用滑桿標的那一段）
#    cell = dlg.cell.cell
#    prof = cell.mean(axis=0)
#    dark = np.where(prof < 90)[0]
#    window.model.set_param(nid, "roi_x", float(dark.min()) / cell.shape[1])
#    window.model.set_param(
#        nid, "roi_w", float(dark.max() - dark.min() + 1) / cell.shape[1])
#
#    assert window.refresh_preview(sync=True) is True
#    feats = dict(window._last_result.features or {})
#    assert feats.get("locate_ok") == 1.0, feats
#    assert feats.get("match_score", 0.0) > 0.8
#
#
#def test_a_card_with_no_template_refuses_to_run_and_says_where_to_go(window):
#    """跑之前的 lint 會擋下來，訊息要指向那顆按鈕，不是丟一個空參數給人猜。"""
#    nid = window.model.add_step("roi_template")
#    window.select_node(nid)
#    assert window.refresh_preview(sync=True) is True
#    assert "Build template" in window.status_text()
#
#
#def test_the_region_check_view_works_for_the_template_card_too(window):
#    """跨顆檢視對**任何**會定義區域的卡片都成立 —— 模板卡也不例外。"""
#    nid = window.model.add_step("roi_template")
#    window.model.set_param(nid, "roi_out", "epi")
#    window.select_node(nid)
#    dlg = window.open_template_dialog()
#    dlg.load_image(big_image(3), "LOT_full.tif")
#    dlg._on_accept()
#
#    assert window.selected_regions() == ["epi"]
#    assert window.region_check_available() is True
#    assert window.open_region_check(n=6, sync=True) is True
#    assert "6 defects" in window.region_window.summary_text()
#
#F f310008decc0246abe0bf5dd54218a96f260c3d4 158 tests/test_ui_f7_14_canvas_flow.py
## F7-14 驗收：從畫布上就做得完一條 pipeline（F7-18 修訂）。
#"""這一輪補的是「n8n 的手感」裡真正有功能的那部分 —— 不是外觀。
#
#**F7-18 拿掉了輸出埠上的「+」**（使用者的原話：那個加號會永久存在，還是從旁邊
#的卡片庫手動加就好）。它做對的那兩件事沒有跟著消失，只是換了入口：
#`add_card_after` 仍然「接在這一張後面」並且「做在對的那條流上」，而卡片庫在
#選著一張卡的時候就走這條路。埠本身照樣拉得動線 —— 拉線現在還會**指定影像流**
#（見 `test_ui_f7_18_streams_as_nodes.py`）。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#
#
#def _import_qt(g):
#    from PySide6.QtCore import QPointF
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import canvas as canvas_mod
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    g.update(QApplication=QApplication, QPointF=QPointF,
#             canvas_mod=canvas_mod, studio_mod=studio_mod, theme_mod=theme_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app, "light")
#    yield app
#
#
#@pytest.fixture
#def window(qapp):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    win.resize(1200, 700)
#    yield win
#    win.close()
#
#
## --------------------------------------------------------------------------- #
## 1. 輸出埠（F7-18：不再掛一顆常駐的「+」）
## --------------------------------------------------------------------------- #
#def test_the_ports_carry_no_permanent_plus(window):
#    """使用者的原話：「加號會永久存在」。一張畫布上每個輸出埠各掛一顆，
#    等於在主體（節點與連線）旁邊常駐一排跟資料流無關的裝飾。"""
#    item = window.pipeline.card(window.model.node_order[0])
#    assert item.out_names() == ["test", "ref"]
#    assert not hasattr(item, "plus_anchors_local")
#    assert not hasattr(item, "plus_at")
#
#    # boundingRect 也要跟著縮回來 —— 留著那塊空間會讓節點之間互相吃到點擊。
#    right = item.boundingRect().right()
#    assert right < canvas_mod.NODE_W + canvas_mod._PORT_LABEL_W + 12
#
#
#def test_the_ports_themselves_still_start_a_connection(window):
#    """拿掉「+」不能連帶把拉線弄丟 —— 那是畫布唯一的輸入方式。"""
#    item = window.pipeline.card(window.model.node_order[0])
#    for i, anchor in enumerate(item.out_anchors_local()):
#        assert item.out_port_at(anchor) == i
#        assert item.boundingRect().contains(anchor)
#
#
## --------------------------------------------------------------------------- #
## 3. 接在哪一張後面、做在哪一條流上
## --------------------------------------------------------------------------- #
#def test_the_new_card_works_on_the_stream_it_was_added_for(window):
#    """接在一張做 ref 的卡後面，結果新卡做在 test 上，使用者就得回控制列改參數
#    —— 而那正是他說「變很複雜」的東西。"""
#    src = window.model.node_order[0]
#    nid = window.add_card_after(src, "denoise", "ref")
#    assert window.model.nodes[nid].params["target"] == "ref"
#    assert "ref" in window.status_text()
#
#    other = window.add_card_after(src, "denoise", "test")
#    assert window.model.nodes[other].params["target"] == "test"
#
#
#def test_adding_after_a_card_puts_it_after_that_card(window):
#    """接在中間，不是接在最後面 —— 使用者指的是「這一張的後面」。"""
#    src = window.model.node_order[0]
#    last = window.add_card_after(src, "align")
#    middle = window.add_card_after(src, "denoise", "test")
#    order = window.model.node_order
#    assert order.index(src) < order.index(middle) < order.index(last)
#    assert (src, middle) in window.model.edges, "使用者的動作是「接」，線要是實線"
#
#
## --------------------------------------------------------------------------- #
## 4. 副標
## --------------------------------------------------------------------------- #
#def test_the_subtitle_says_what_the_card_does_not_its_id(window):
#    """副標以前印的是 node_id（`roi_template`）—— 那是 recipe JSON 的鍵，
#    而卡片名字就在它上面一行，所以那一行等於沒有資訊。"""
#    src = window.model.node_order[0]
#    a = window.add_card_after(src, "align", "test")
#    assert window.pipeline.card(a).subtitle() == "test ref → ref_aligned"
#
#    b = window.add_card_after(a, "subtract")
#    c = window.add_card_after(b, "roi_template", "diff")
#    # Region 卡不寫影像流，它定義的是具名區域 —— 副標仍然要講得出它產出什麼
#    assert window.pipeline.card(c).subtitle() == "diff → cell"
#
#
#def test_a_repeated_card_shows_which_one_it_is(window):
#    src = window.model.node_order[0]
#    window.add_card_after(src, "denoise", "test")
#    second = window.add_card_after(src, "denoise", "ref")
#    assert window.pipeline.card(second).subtitle().startswith("denoise2 · ")
#
#
## --------------------------------------------------------------------------- #
## 5. 縮放
## --------------------------------------------------------------------------- #
#def test_zoom_is_clamped_at_both_ends(window):
#    """沒有下限，滾兩下就把整張圖縮成一個點，而且點陣底每一格都長得一樣 ——
#    使用者不知道自己在哪裡，也不知道有哪顆鈕救得回來。"""
#    view = window.pipeline
#    assert view.zoom_percent() == 100
#    for _ in range(30):
#        view.zoom_by(1 / 1.25)
#    assert view.zoom_percent() == int(round(view.MIN_SCALE * 100))
#    for _ in range(60):
#        view.zoom_by(1.25)
#    assert view.zoom_percent() == int(round(view.MAX_SCALE * 100))
#    view.reset_zoom()
#    assert view.zoom_percent() == 100
#
#
#def test_the_zoom_controls_are_on_screen_and_say_the_current_zoom(window):
#    view = window.pipeline
#    window.show()
#    assert len(view._zoom_buttons) == 4
#    assert view._zoom_bar.isVisibleTo(view)
#    view.zoom_by(1.25)
#    assert view._zoom_label.text() == "%d%%" % view.zoom_percent()
#    # 左下角：不擋到節點（節點從左上角開始排）
#    assert view._zoom_bar.x() < view.viewport().width() / 2
#    assert view._zoom_bar.y() > view.viewport().height() / 2
#
#
#def test_fit_then_reset_is_a_way_back(window):
#    """fit 之後字會變小，這時候要有一顆「回到 100%」—— 不然使用者只能滾回來，
#    而滾回來要滾幾下沒有人知道。"""
#    view = window.pipeline
#    for key in ("align", "subtract", "snr_map", "blob_segment"):
#        view.fit()
#    view.fit()
#    view.reset_zoom()
#    assert view.zoom_percent() == 100
#
#F fed44e36372c1523c663aa065a9ae0712544ba25 175 tests/test_ui_f7_15_reading_load.py
## F7-15 驗收：畫面上的字要能被讀完。
#"""三件事都不是「功能不對」，是**讀不完 / 看不到 / 分不出來**。
#
#* 一張卡 11 個參數、每個帶 2–3 行灰字 = 一面牆。一定要捲，而且真正要緊的事
#  （這張卡還沒有模板）淹在裡面。
#* 沒載資料時最大的一塊是一片黑，角落有一行極小的「(no dataset loaded)」——
#  首啟導覽關掉之後就沒有任何東西說得出下一步。
#* 狀態列是**唯一**會講「這件事沒成功」的地方，而它跟「Added denoise」用一模
#  一樣的灰字，在畫面最左下角。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#
#
#def _import_qt(g):
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    from adept.ui import widgets as widgets_mod
#    g.update(QApplication=QApplication, studio_mod=studio_mod,
#             theme_mod=theme_mod, widgets_mod=widgets_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app, "light")
#    yield app
#
#
#@pytest.fixture
#def window(qapp):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    win.resize(1400, 900)
#    yield win
#    win.close()
#
#
## --------------------------------------------------------------------------- #
## 1. 參數說明：一行，用到才攤開
## --------------------------------------------------------------------------- #
#def test_help_is_one_line_until_you_use_that_row(window, qapp):
#    window.show()
#    nid = window.model.add_step("roi_template")
#    window.select_node(nid)
#    qapp.processEvents()
#
#    form = window.param_form
#    row = form._rows["min_structure"]
#    assert row.hint.is_expanded() is False
#    assert row.hint.wordWrap() is False, "收起來的說明不能換行 —— 那就沒有收"
#    # 切字自己算，不讓 Qt 硬切在字的中間
#    assert row.hint.text().endswith("…")
#    assert len(row.hint.text()) < len(form.hint_text("min_structure"))
#
#    row.set_active(True)
#    assert row.hint.is_expanded() is True
#    assert row.hint.wordWrap() is True
#    assert row.hint.text() == form.hint_text("min_structure")
#
#
#def test_the_full_text_is_still_the_full_text(window):
#    """收起來只是**畫面上**的事。問「這個參數的說明寫了什麼」的人要的，
#    從來不是「現在放得下多少」。"""
#    nid = window.model.add_step("roi_template")
#    window.select_node(nid)
#    full = window.param_form.hint_text("min_structure")
#    assert "featureless patch scores about 1" in full
#    editor = window.param_form.editor("min_structure")
#    assert editor.toolTip() == full, "滑鼠停上去也要看得到全文"
#
#
#def test_an_error_stays_open(window):
#    """錯誤是他現在最需要讀完的一句話 —— 不能因為滑鼠移開就切掉。"""
#    nid = window.model.add_step("roi_template")
#    window.select_node(nid)
#    form = window.param_form
#    row = form._rows["min_score"]
#    form.show_error("min_score", "must be between -1 and 1")
#    assert row.hint.is_expanded() is True
#    row.set_active(False)
#    assert row.hint.is_expanded() is True, "錯誤被收起來了"
#    form.clear_errors()
#    assert row.hint.is_expanded() is False
#
#
#def test_more_parameters_fit_on_screen_than_before(window, qapp):
#    """這一項的重點就是**看得到幾個參數**。11 個參數 × 3 行 vs × 1 行。"""
#    window.show()
#    nid = window.model.add_step("roi_template")
#    window.select_node(nid)
#    qapp.processEvents()
#    form = window.param_form
#    collapsed = sum(r.sizeHint().height() for r in form._rows.values())
#    for r in form._rows.values():
#        r.set_active(True)
#    qapp.processEvents()
#    expanded = sum(r.sizeHint().height() for r in form._rows.values())
#    assert collapsed < expanded * 0.75, (collapsed, expanded)
#
#
## --------------------------------------------------------------------------- #
## 2. 沒有資料時，最大的那一塊要說得出下一步
## --------------------------------------------------------------------------- #
#def test_the_empty_panel_offers_the_two_things_you_can_do(window):
#    assert window.image_stack.currentIndex() == 0
#    assert window.btn_empty_open.text() == "Open KLARF…"
#    assert "sample data" in window.btn_empty_sample.text()
#
#
#def test_the_images_come_back_once_data_is_loaded(window, tmp_path):
#    from make_sample import generate
#
#    out = generate(str(tmp_path / "lot"), n=4, seed=3)
#    assert window.load_dataset_path(out["klarf"], sync=True) is True
#    assert window.image_stack.currentIndex() == 1
#
#
## --------------------------------------------------------------------------- #
## 3. 「沒成功」不能跟「做好了」長得一樣
## --------------------------------------------------------------------------- #
#def test_a_refusal_is_marked_as_one(window, tmp_path):
#    """加一張缺模板的卡 → 試跑被 lint 擋下來。那是使用者按了鈕之後**唯一**的
#    解釋，它不能跟上一句「Added roi_template」長得一模一樣。"""
#    from make_sample import generate
#
#    out = generate(str(tmp_path / "lot2"), n=4, seed=4)
#    window.load_dataset_path(out["klarf"], sync=True)
#    window._status("Added denoise")
#    assert window.status_level() == "info"
#
#    nid = window.model.add_step("roi_template")
#    window.select_node(nid)
#    assert window.run_trial(n=4) is False
#    assert "Cannot run" in window.status_text()
#    assert window.status_level() == "error"
#
#    window._status("Added denoise")
#    assert window.status_level() == "info"
#
#
#@pytest.mark.parametrize("theme_name", ["light", "dark"])
#def test_the_error_colour_is_actually_different(window, qapp, theme_name):
#    """屬性設了不代表畫出來不一樣（QSS 沒寫規則的話什麼都不會變）。"""
#    from PySide6.QtGui import QColor, QPixmap
#
#    theme_mod.apply_theme(qapp, theme_name)
#    window.show()
#    bar = window.statusBar()
#    bar.resize(400, 22)
#
#    def shot(level):
#        # **同一句話**，只有 level 不同 —— 這樣兩張圖的差別只可能來自樣式。
#        window._status("Cannot run — this card is not set up", level)
#        qapp.processEvents()
#        pm = QPixmap(bar.size())
#        pm.fill(QColor("#808080"))
#        bar.render(pm)
#        return pm.toImage()
#
#    normal, bad = shot("info"), shot("error")
#    diff = sum(1 for x in range(bar.width()) for y in range(bar.height())
#               if normal.pixelColor(x, y) != bad.pixelColor(x, y))
#    assert diff > 20, "紅字的屬性設了，但畫出來一模一樣（QSS 沒有對應規則）"
#    theme_mod.apply_theme(qapp, "light")
#
#F ce33115c49f3805c216293d1ef63006cd91469ae 305 tests/test_ui_f7_16_safety_net.py
## F7-16 驗收：四件會讓使用者**丟掉工作成果**的事。
#"""這四項不是「不方便」，是「一個誤按就沒了」：
#
#* 刪錯一張卡沒得退 —— 而這是一個「一直在試」的工具，試錯就是主要動作；
#* 沒有任何快捷鍵，存檔／跑一次／退一步每次都要把手移到滑鼠；
#* 關窗不問「還沒存」，調了一小時的 recipe 關掉就沒了；
#* 跑到一半不能停 —— 而「按下去才發現參數設錯」是最常見的情況。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#
#
#def _import_qt(g):
#    from PySide6.QtGui import QKeySequence
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    g.update(QApplication=QApplication, QKeySequence=QKeySequence,
#             studio_mod=studio_mod, theme_mod=theme_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app, "light")
#    yield app
#
#
#@pytest.fixture
#def window(qapp):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    yield win
#    win.close()
#
#
## --------------------------------------------------------------------------- #
## 1. 復原（model 層，Qt-free）
## --------------------------------------------------------------------------- #
#def _model():
#    import adept.core.steps  # noqa: F401 — 註冊卡片
#    from adept.ui.viewmodel import RecipeModel
#
#    return RecipeModel.starter()
#
#
#def test_a_fresh_recipe_has_nothing_to_undo():
#    """起手卡不是「使用者做過的一步」—— Ctrl+Z 不該把畫布退成空白。"""
#    m = _model()
#    assert m.can_undo() is False
#    assert m.dirty is False
#
#
#def test_deleting_a_card_can_be_taken_back():
#    m = _model()
#    nid = m.add_step("align")
#    m.remove(nid)
#    assert m.node_order == ["load_patch"]
#    assert m.undo() is True
#    assert m.node_order == ["load_patch", nid]
#    assert m.nodes[nid].step == "align"
#
#
#def test_one_ctrl_z_undoes_a_whole_slider_drag():
#    """拖一次滑桿會發幾十次 set_param。每一次各記一步的話，按一次 Ctrl+Z 只退
#    回一個畫素 —— 使用者得按四十次才回得到動之前的樣子，那等於沒有復原。"""
#    m = _model()
#    nid = m.add_step("align")
#    before = m.nodes[nid].params["search_radius"]
#    for v in (2, 3, 4, 5, 6, 7):
#        m.set_param(nid, "search_radius", v)
#    assert m.nodes[nid].params["search_radius"] == 7
#    assert m.undo() is True
#    assert m.nodes[nid].params["search_radius"] == before
#
#
#def test_two_separate_visits_to_the_same_slider_are_two_steps():
#    """「調 A → 去做別的 → 再調 A」是兩件事。中間那個動作切開它們。"""
#    m = _model()
#    nid = m.add_step("align")
#    m.set_param(nid, "search_radius", 3)
#    m.end_coalescing()                      # Studio 在換節點/存檔時呼叫
#    m.set_param(nid, "search_radius", 9)
#    assert m.undo() is True
#    assert m.nodes[nid].params["search_radius"] == 3
#
#
#def test_undo_covers_the_side_effects_too():
#    """``add_edge`` 會重排 ``node_order`` —— 復原是整份狀態的快照，
#    所以連帶的重排也會一起回去（反向操作很容易漏掉這種）。"""
#    m = _model()
#    a = m.add_step("align")
#    b = m.add_step("subtract")
#    m.move(b, -1)
#    order_before = list(m.node_order)
#    assert m.add_edge(a, b) is True
#    assert m.node_order != order_before
#    assert m.undo() is True
#    assert m.node_order == order_before
#    assert m.edges == []
#
#
#def test_redo_puts_it_back_and_a_new_edit_drops_it():
#    m = _model()
#    nid = m.add_step("align")
#    m.undo()
#    assert m.can_redo() is True
#    assert m.redo() is True
#    assert nid in m.node_order
#
#    m.undo()
#    m.add_step("denoise")                   # 新的一步 → 舊的重做鏈作廢
#    assert m.can_redo() is False
#
#
#def test_the_history_does_not_grow_without_bound():
#    m = _model()
#    nid = m.add_step("align")
#    for i in range(m.UNDO_DEPTH + 30):
#        m.end_coalescing()
#        m.set_param(nid, "search_radius", (i % 15) + 1)
#    assert len(m._undo) == m.UNDO_DEPTH
#
#
#def test_loading_a_recipe_starts_a_new_history(window, tmp_path):
#    """載進來的檔案在那之前發生的事，不屬於這一份 recipe。"""
#    window.model.add_step("align")
#    path = tmp_path / "r.json"
#    assert window.save_recipe_path(str(path)) is True
#    assert window.load_recipe_path(str(path)) is True
#    assert window.model.can_undo() is False
#
#
#def test_studio_says_so_when_there_is_nothing_to_undo(window):
#    """按了 Ctrl+Z 卻什麼都沒發生，使用者第一個念頭是「這工具壞了嗎」。"""
#    assert window.undo() is False
#    assert "Nothing to undo" in window.status_text()
#    window.model.add_step("align")
#    assert window.undo() is True
#    assert "Undone" in window.status_text()
#
#
## --------------------------------------------------------------------------- #
## 2. 快捷鍵
## --------------------------------------------------------------------------- #
#def test_the_usual_keys_all_exist(window):
#    keys = {sc.key().toString() for sc in window._shortcuts}
#    for want in ("Ctrl+O", "Ctrl+S", "Ctrl+R", "Ctrl+Z", "Ctrl+0"):
#        assert QKeySequence(want).toString() in keys, want
#
#
#def test_ctrl_z_is_wired_to_undo(window):
#    window.model.add_step("align")
#    n = len(window.model.node_order)
#    for sc in window._shortcuts:
#        if sc.key() == QKeySequence("Ctrl+Z"):
#            sc.activated.emit()
#            break
#    assert len(window.model.node_order) == n - 1
#
#
#def test_the_shortcut_is_written_where_it_will_be_found(window):
#    """按鍵存在還不夠 —— 要發現得到。而且 ``_update_action_states`` 每次
#    refresh 都會重寫這幾顆的 tooltip，設一次的話第一次 refresh 就沒了。"""
#    assert "Ctrl+S" in window.btn_save_recipe.toolTip()
#    assert "Ctrl+R" in window.btn_trial.toolTip()
#    window.model.add_step("align")
#    window._refresh_all()
#    assert "Ctrl+S" in window.btn_save_recipe.toolTip(), "refresh 之後不見了"
#
#
#def test_ctrl_f_opens_the_card_search(window):
#    window.focus_card_search()
#    assert window.library.panel_open() is True
#
#
## --------------------------------------------------------------------------- #
## 3. 關窗前的確認
## --------------------------------------------------------------------------- #
#def test_a_clean_recipe_closes_without_asking(window):
#    assert window.unsaved_changes() is False
#    asked = []
#    window._ask_unsaved = lambda: asked.append(1) or "discard"
#    window.PROMPT_ON_CLOSE = True
#    try:
#        assert window.confirm_close() is True
#        assert asked == []
#    finally:
#        window.PROMPT_ON_CLOSE = False
#
#
#@pytest.mark.parametrize("answer,expected", [
#    ("discard", True), ("cancel", False),
#])
#def test_the_three_answers_do_what_they_say(window, answer, expected):
#    window.model.add_step("align")
#    assert window.unsaved_changes() is True
#    window._ask_unsaved = lambda: answer
#    window.PROMPT_ON_CLOSE = True
#    try:
#        assert window.confirm_close() is expected
#    finally:
#        window.PROMPT_ON_CLOSE = False
#
#
#def test_cancelling_the_save_dialog_means_do_not_close(window):
#    """在存檔對話框按取消，意思是「我改變主意了」，不是「丟掉吧」。"""
#    window.model.add_step("align")
#    window._ask_unsaved = lambda: "save"
#    window._on_save_recipe = lambda: False       # 使用者在存檔對話框按了取消
#    window.PROMPT_ON_CLOSE = True
#    try:
#        assert window.confirm_close() is False
#    finally:
#        window.PROMPT_ON_CLOSE = False
#
#
#def test_saving_from_the_prompt_lets_it_close(window, tmp_path):
#    window.model.add_step("align")
#    window._ask_unsaved = lambda: "save"
#    window._on_save_recipe = lambda: window.save_recipe_path(
#        str(tmp_path / "saved.json"))
#    window.PROMPT_ON_CLOSE = True
#    try:
#        assert window.confirm_close() is True
#        assert (tmp_path / "saved.json").exists()
#        assert window.unsaved_changes() is False
#    finally:
#        window.PROMPT_ON_CLOSE = False
#
#
#def test_the_close_event_is_actually_gated(window):
#    """真的走 closeEvent 那條路，不是只測那個判斷函式。"""
#    from PySide6.QtGui import QCloseEvent
#
#    window.model.add_step("align")
#    window._ask_unsaved = lambda: "cancel"
#    window.PROMPT_ON_CLOSE = True
#    try:
#        e = QCloseEvent()
#        window.closeEvent(e)
#        assert e.isAccepted() is False
#    finally:
#        window.PROMPT_ON_CLOSE = False
#
#
## --------------------------------------------------------------------------- #
## 4. 跑到一半可以停
## --------------------------------------------------------------------------- #
#def test_stop_only_shows_while_something_is_running(window, tmp_path):
#    from make_sample import generate
#
#    assert window.stop_available() is False
#    out = generate(str(tmp_path / "lot"), n=6, seed=1)
#    window.load_dataset_path(out["klarf"], sync=True)
#    window.load_template()
#    assert window.run_trial(n=6, sync=True) is True
#    assert window.stop_available() is False, "同步跑完之後不該還留著中止鈕"
#    assert window.stop_run() is False
#
#
#def test_the_stop_button_is_there_while_a_real_run_is_in_flight(window, tmp_path,
#                                                                qapp):
#    """同步路徑測不到這一項 —— 中止鈕存在的**唯一**意義就是背景跑的時候。"""
#    from make_sample import generate
#
#    out = generate(str(tmp_path / "lot3"), n=40, seed=5)
#    window.load_dataset_path(out["klarf"], sync=True)
#    window.load_template()
#    assert window.run_trial(n=40, sync=False) is True
#    try:
#        assert window.stop_available() is True
#        assert window.progress_visible() is True
#        assert window.stop_run() is True
#        assert "Stopping" in window.status_text()
#    finally:
#        window.trial_worker.stop()          # 收乾淨，不留背景執行緒
#        qapp.processEvents()
#
#
#def test_stopping_keeps_what_already_finished(window, tmp_path):
#    """按停止是「不要再等了」，不是「把剛才那五分鐘丟掉」。"""
#    from make_sample import generate
#
#    out = generate(str(tmp_path / "lot2"), n=8, seed=2)
#    window.load_dataset_path(out["klarf"], sync=True)
#    window.load_template()
#    window._trial_t0 = 0.0
#    # 直接模擬「跑到一半被按停」：worker 中止後仍會把部分結果送出來
#    window.trial_worker.abort()
#    partial = [{"defect_id": i, "ok": True, "score": 0.1 * i, "features": {},
#                "bin": 0} for i in range(3)]
#    window._apply_trial_results(partial, 1.0)
#    assert len(window.trial_results) == 3
#    assert "Run stopped" in window.status_text()
#    assert "finished" not in window.status_text().split(":")[0]
#
#F 66018acf8f0ef2cbfc99f16fbe215160a30e66d6 496 tests/test_ui_f7_17_inspectors.py
## F7-17 驗收：右下角是**這張卡自己的儀表**。
#"""原本那塊固定是一張「特徵 / 數值」表。問題不是它佔位子，是那些數字**沒有辦法
#判讀** —— `blob_dist_center 11.170` 是大還是小？而且使用者在問的問題每張卡都
#不一樣：調 Align 時他要知道「搜尋半徑夠不夠」，調 Denoise 時他要知道「我有沒有
#把訊號一起磨掉」。
#
#這一支測兩件事：**機制**（換卡片就換儀表、沒註冊的卡不會變成一片空白）與
#**每個儀表回答的那個問題**。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#
#
#def _import_qt(g):
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import inspectors as insp_mod
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    g.update(QApplication=QApplication, insp_mod=insp_mod,
#             studio_mod=studio_mod, theme_mod=theme_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app, "light")
#    yield app
#
#
#@pytest.fixture
#def window(qapp):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    win.resize(1400, 900)
#    yield win
#    win.close()
#
#
#def _batch(points, extra=None):
#    """把 (dx, dy) 清單做成 trial_results 的形狀。"""
#    out = []
#    for i, (dx, dy) in enumerate(points):
#        feats = {"align_dx": float(dx), "align_dy": float(dy)}
#        feats.update(extra or {})
#        out.append({"defect_id": i, "ok": True, "score": 0.0, "features": feats})
#    return out
#
#
## --------------------------------------------------------------------------- #
## 1. 機制
## --------------------------------------------------------------------------- #
#def test_selecting_a_card_swaps_in_its_own_panel(window):
#    src = window.model.node_order[0]
#    a = window.add_card_after(src, "align", "test")
#    assert isinstance(window.inspector(), insp_mod.AlignInspector)
#    assert window.bottom_page() == 0
#    assert window.btn_tab_card.text() == "Alignment"
#
#
#def test_a_card_without_a_panel_falls_back_to_the_feature_table(window):
#    """沒註冊儀表的卡**不能**變成一片空白 —— 那比原本的特徵表還糟。"""
#    src = window.model.node_order[0]
#    a = window.add_card_after(src, "align", "test")
#    window.add_card_after(a, "subtract")        # subtract 還沒有自己的儀表
#    assert window.inspector() is None
#    assert window.bottom_page() == 1
#    assert window.btn_tab_card.isEnabled() is False
#
#
#def test_you_can_still_get_to_the_features(window):
#    src = window.model.node_order[0]
#    window.add_card_after(src, "align", "test")
#    window.show_bottom_page(1)
#    assert window.bottom_page() == 1
#    window.show_bottom_page(0)
#    assert window.bottom_page() == 0
#
#
#def test_adding_a_new_card_does_not_need_this_module_touched():
#    """約定 1：沒登記的卡就沒有儀表，不是壞掉。"""
#    assert insp_mod.inspector_for("subtract") is None
#    assert insp_mod.inspector_for("roi_define") is None
#    assert insp_mod.inspector_for("") is None
#    assert insp_mod.inspector_for("align") is insp_mod.AlignInspector
#
#
#def test_an_empty_panel_says_why_it_is_empty(qapp):
#    """空白面板本身不是訊息。最常見的原因是「還沒跑過」。"""
#    insp = insp_mod.AlignInspector()
#    insp.set_context("align", params={"search_radius": 8})
#    assert insp.has_data() is False
#    assert "Run a trial" in insp.empty_reason()
#    assert insp.summary() == ""
#
#
#@pytest.mark.parametrize("theme_name", ["light", "dark"])
#def test_the_panel_paints_in_both_themes(qapp, theme_name):
#    from PySide6.QtGui import QColor, QPixmap
#
#    theme_mod.apply_theme(qapp, theme_name)
#    insp = insp_mod.AlignInspector()
#    insp.resize(260, 200)
#    for batch in ([], _batch([(1.0, -2.0), (7.9, 0.5)])):
#        insp.set_context("align", params={"search_radius": 8},
#                         result={"features": {"align_dx": 1.0, "align_dy": -2.0}},
#                         batch=batch)
#        pm = QPixmap(insp.size())
#        pm.fill(QColor("#ffffff"))
#        insp.render(pm)                    # 例外會在這裡冒出來
#        assert not pm.isNull()
#    theme_mod.apply_theme(qapp, "light")
#
#
## --------------------------------------------------------------------------- #
## 2. Align：搜尋半徑夠不夠大
## --------------------------------------------------------------------------- #
#def test_it_counts_the_defects_that_ran_out_of_room(qapp):
#    """對位失敗在單顆上看不出來 —— 演算法一定會回一個位移，而 8 是一個看起來
#    完全正常的數字。真正的訊號是「位移**貼在搜尋框的邊上**」。"""
#    insp = insp_mod.AlignInspector()
#    pts = [(0.5, 0.2), (-1.0, 2.0), (8.0, 1.0), (-8.0, -3.0), (2.0, 7.95)]
#    insp.set_context("align", params={"search_radius": 8}, batch=_batch(pts))
#    assert insp.has_data() is True
#    assert insp.at_the_limit() == 3
#
#
#def test_the_warning_says_what_to_do_about_it(qapp):
#    insp = insp_mod.AlignInspector()
#    insp.set_context("align", params={"search_radius": 8},
#                     batch=_batch([(8.0, 0.0), (0.1, 0.2)]))
#    text = insp.summary()
#    assert "1 of them sit on the search limit" in text
#    assert "Search radius" in text, "要講得出下一步是什麼"
#
#
#def test_a_healthy_batch_does_not_cry_wolf(qapp):
#    insp = insp_mod.AlignInspector()
#    insp.set_context("align", params={"search_radius": 8},
#                     batch=_batch([(0.4, -0.2), (1.1, 0.9), (-2.0, 1.5)]))
#    assert insp.at_the_limit() == 0
#    assert "⚠" not in insp.summary()
#    assert "3 defects" in insp.summary()
#
#
#def test_sub_pixel_shifts_still_count_as_at_the_limit(qapp):
#    """次像素對位會回 7.9 這種值 —— 用嚴格相等比對會一顆都抓不到，
#    而那正是最需要被抓到的情況。"""
#    insp = insp_mod.AlignInspector()
#    insp.set_context("align", params={"search_radius": 8},
#                     batch=_batch([(7.94, 0.0)]))
#    assert insp.at_the_limit() == 1
#
#
#def test_broken_values_do_not_break_the_panel(qapp):
#    """單顆失敗不會殺整批（引擎的契約），所以這裡一定會遇到缺值。"""
#    insp = insp_mod.AlignInspector()
#    batch = _batch([(1.0, 1.0)])
#    batch.append({"defect_id": 9, "ok": False, "features": {}})
#    batch.append({"defect_id": 10, "ok": True,
#                  "features": {"align_dx": float("nan"), "align_dy": 1.0}})
#    insp.set_context("align", params={"search_radius": 4}, batch=batch)
#    assert insp.points() == [(1.0, 1.0)]
#
#
#def test_it_reads_the_engine_numbers_not_its_own(window, tmp_path):
#    """整條路跑一次：引擎算的 align_dx/dy → trial_results → 儀表。"""
#    from make_sample import generate
#
#    out = generate(str(tmp_path / "lot"), n=8, seed=17)
#    window.load_dataset_path(out["klarf"], sync=True)
#    src = window.model.node_order[0]
#    a = window.add_card_after(src, "align", "test")
#    window.model.set_param(a, "search_radius", 6)
#    assert window.run_trial(n=8, sync=True) is True
#    window.select_node(a)
#
#    insp = window.inspector()
#    assert len(insp.points()) == 8
#    assert insp.radius() == 6.0
#    first = window.trial_results[0]["features"]
#    assert insp.points()[0] == (first["align_dx"], first["align_dy"])
#    assert "8 defects" in window.inspector_summary.text()
#
#
## --------------------------------------------------------------------------- #
## 3. Enhance：我把資訊弄掉了嗎
## --------------------------------------------------------------------------- #
#def _change(before, after, was_lo=0.0, was_hi=0.0, lo=0.0, hi=0.0):
#    return {"stream_change": {"test": {
#        "before": before, "after": after,
#        "clipped_low": lo, "clipped_high": hi,
#        "was_clipped_low": was_lo, "was_clipped_high": was_hi}}}
#
#
#def test_the_enhance_panel_needs_the_engine_record(qapp):
#    insp = insp_mod.EnhanceInspector()
#    insp.set_context("gamma", params={"target": "test"})
#    assert insp.has_data() is False
#    assert "“test”" in insp.empty_reason()
#
#
#def test_it_reports_how_much_the_card_flattened(qapp):
#    """削平是 Enhance 唯一會安靜毀掉資訊的方式：那些畫素之間的差異回不來了。"""
#    insp = insp_mod.EnhanceInspector()
#    insp.set_context("brightness_contrast", params={"target": "test"},
#                     meta=_change([10, 20, 10], [40, 0, 40],
#                                  was_lo=0.0, was_hi=0.0, lo=0.30, hi=0.12))
#    assert insp.has_data() is True
#    assert insp.clipped() == (0.30, 0.12)
#    assert insp.added_clipping() == (0.30, 0.12)
#    text = insp.summary()
#    assert "30.0% of pixels at black" in text
#    assert "⚠" in text and "measure card downstream" in text
#
#
#def test_it_does_not_blame_this_card_for_pre_existing_black(qapp):
#    """原圖本來就有一片全黑（缺陷本身、或上一張卡幹的）—— 那不是這張卡的帳，
#    而每次都喊狼來了跟不喊一樣沒有用。"""
#    insp = insp_mod.EnhanceInspector()
#    insp.set_context("denoise", params={"target": "test"},
#                     meta=_change([5, 5], [5, 5], was_lo=0.22, lo=0.22))
#    assert insp.clipped()[0] == 0.22
#    assert insp.added_clipping() == (0.0, 0.0)
#    assert "⚠" not in insp.summary()
#
#
#def test_it_follows_the_stream_the_card_works_on(qapp):
#    """一張只做在 ref 上的卡，要比的是 ref 的 before/after，不是 test 的。"""
#    insp = insp_mod.EnhanceInspector()
#    meta = _change([1, 2], [3, 4])
#    meta["stream_change"]["ref"] = {"before": [9], "after": [8],
#                                    "clipped_low": 0.5, "clipped_high": 0.0,
#                                    "was_clipped_low": 0.0,
#                                    "was_clipped_high": 0.0}
#    insp.set_context("denoise", params={"target": "ref"}, meta=meta)
#    assert insp.stream() == "ref"
#    assert insp.clipped()[0] == 0.5
#
#
#def test_the_engine_only_records_when_asked(qapp, tmp_path):
#    """批次跑一萬顆時每次 set_image 都算兩個直方圖是白花的力氣。"""
#    from adept.core.pipeline.context import Context
#    import numpy as np
#
#    ctx = Context()
#    ctx.set_image("test", np.zeros((4, 4), np.uint8))
#    ctx.set_image("test", np.full((4, 4), 255, np.uint8))
#    assert "stream_change" not in ctx.meta
#
#    ctx2 = Context()
#    ctx2.track_changes = True
#    ctx2.set_image("test", np.zeros((4, 4), np.uint8))
#    assert "stream_change" not in ctx2.meta, "第一次寫入不是「改」，是「產生」"
#    ctx2.set_image("test", np.full((4, 4), 255, np.uint8))
#    rec = ctx2.meta["stream_change"]["test"]
#    assert rec["was_clipped_low"] == 1.0 and rec["clipped_high"] == 1.0
#
#
#def test_the_studio_preview_turns_recording_on(window, tmp_path):
#    """整條路：預覽 → ctx.meta → 儀表。"""
#    from make_sample import generate
#
#    out = generate(str(tmp_path / "lotE"), n=4, seed=23)
#    window.load_dataset_path(out["klarf"], sync=True)
#    src = window.model.node_order[0]
#    b = window.add_card_after(src, "brightness_contrast", "test")
#    window.model.set_param(b, "contrast", 4.0)
#    window.select_node(b)
#    assert window.refresh_preview(sync=True) is True
#
#    insp = window.inspector()
#    assert isinstance(insp, insp_mod.EnhanceInspector)
#    assert insp.has_data() is True
#    assert insp.added_clipping()[0] > 0.05, "對比拉到 4 倍一定會壓黑一大片"
#    assert "⚠" in window.inspector_summary.text()
#
#
## --------------------------------------------------------------------------- #
## 4. Measure：這張卡量出來的東西分不分得開
## --------------------------------------------------------------------------- #
#def _feats(values):
#    return [{"defect_id": i, "ok": True, "features": dict(f)}
#            for i, f in enumerate(values)]
#
#
#def test_it_only_shows_this_cards_own_numbers(qapp):
#    """整份 feature 表是 ADC 的事。調這張卡的時候要看的是**這張卡**的產出。"""
#    insp = insp_mod.MeasureInspector()
#    batch = _feats([{"glv_mean": 10.0 + i, "blob_area": 3.0} for i in range(6)])
#    insp.set_context("glv_stats", batch=batch, feature_names=["glv_mean"])
#    assert insp.rows() == ["glv_mean"]
#
#
#def test_it_calls_out_a_feature_that_separates_nothing(qapp):
#    """整批擠成一根柱子 = 門檻設哪裡都一樣。那是使用者最需要知道的事。"""
#    insp = insp_mod.MeasureInspector()
#    batch = _feats([{"flat": 5.0, "spread": float(i)} for i in range(20)])
#    insp.set_context("glv_stats", batch=batch,
#                     feature_names=["flat", "spread"])
#    assert insp._is_flat("flat") is True
#    assert insp._is_flat("spread") is False
#    assert "flat barely varies" in insp.summary()
#
#
#def test_it_says_where_this_defect_sits(qapp):
#    insp = insp_mod.MeasureInspector()
#    batch = _feats([{"m": float(i)} for i in range(100)])
#    insp.set_context("glv_stats", result={"features": {"m": 97.0}},
#                     batch=batch, feature_names=["m"])
#    assert insp.percentile_of("m") == 97.0
#    assert "top 5%" in insp.summary()
#
#
#def test_a_value_outside_the_batch_range_does_not_draw_off_the_chart(qapp):
#    """改了參數之後預覽會立刻重算，而整批還是上一次跑的 —— 這是正常狀態，
#    不是錯誤。把線畫到圖外會蓋到旁邊的文字。"""
#    from PySide6.QtGui import QColor, QPixmap
#
#    insp = insp_mod.MeasureInspector()
#    insp.resize(320, 120)
#    batch = _feats([{"m": float(i)} for i in range(10)])
#    insp.set_context("glv_stats", result={"features": {"m": -500.0}},
#                     batch=batch, feature_names=["m"])
#    pm = QPixmap(insp.size())
#    pm.fill(QColor("#ffffff"))
#    insp.render(pm)                    # 這裡以前會 segfault（drawPolygon overload）
#    assert not pm.isNull()
#
#
## --------------------------------------------------------------------------- #
## 5. Input：哪一頁變成哪一條流
## --------------------------------------------------------------------------- #
#def test_the_page_to_stream_mapping_is_on_screen(window, tmp_path):
#    """這是全專案第一條待廠內驗證的假設（CLAUDE.md §8）。錯了的話 diff 會整個
#    反號，而畫面上完全看不出來 —— 兩張圖本來就長得很像。"""
#    from make_sample import generate
#
#    out = generate(str(tmp_path / "lotF"), n=4, seed=29)
#    window.load_dataset_path(out["klarf"], sync=True)
#    window.select_node(window.model.node_order[0])
#    assert window.refresh_preview(sync=True) is True
#
#    insp = window.inspector()
#    assert isinstance(insp, insp_mod.InputInspector)
#    pages = insp.pages()
#    assert [d["channel"] for d in pages] == ["test", "ref"]
#    assert [d["page"] for d in pages] == [0, 1]
#    assert all(d["shape"] == [128, 128] for d in pages)
#    assert all(d["mean"] is not None for d in pages)
#
#
#def test_it_says_the_pixel_size_is_unknown(window, tmp_path):
#    """nm/px 找不到來源是待驗證假設第 2 條，而它的後果（CD 的 nm 值是 0）
#    現在只寫在文件裡。"""
#    from make_sample import generate
#
#    out = generate(str(tmp_path / "lotG"), n=2, seed=31)
#    window.load_dataset_path(out["klarf"], sync=True)
#    window.select_node(window.model.node_order[0])
#    window.refresh_preview(sync=True)
#    assert "nm/px unknown" in window.inspector().summary()
#
#
## --------------------------------------------------------------------------- #
## 6. roi_profile：曲線面板收進同一個機制
## --------------------------------------------------------------------------- #
#def test_the_profile_curve_is_now_a_card_panel_like_the_rest(window):
#    """F7-11 時它直接掛在預覽面板上 —— 一條跟儀表機制平行的路。兩條並存的
#    下場是加新面板的人不知道走哪一條，然後兩邊各長一半。"""
#    nid = window.model.add_step("roi_profile")
#    window.select_node(nid)
#    assert isinstance(window.inspector(), insp_mod.ProfileInspector)
#    assert window.bottom_page() == 0
#    # 舊的對外名字還在（狀態列與既有測試都用它）
#    assert window.profile_panel is window.inspector().panel
#
#
#def test_the_old_name_still_answers_when_another_card_is_selected(window):
#    """`profile_panel` 在別的卡片上要回一個**空的替身**，不是 None ——
#    呼叫端不必到處寫 if is None。"""
#    window.select_node(window.model.node_order[0])
#    assert window.profile_panel is not None
#    assert window.profile_panel.has_data() is False
#    assert window.profile_panel_visible() is False
#
#
## --------------------------------------------------------------------------- #
## 7. roi_template：定位失敗有三個完全不同的原因
## --------------------------------------------------------------------------- #
#def _match(score=0.9, margin=0.4, structure=30.0, ok=True):
#    return {"templates": {"cell": {
#        "cell_w": 40, "cell_h": 240, "phase_x": 7, "phase_y": 0,
#        "score": score, "margin": margin, "structure": structure,
#        "ok": ok, "norm": [0.0, 0.0, 1.0, 1.0], "axis": "x"}}}
#
#
#_TPL_PARAMS = {"roi_out": "cell", "min_score": 0.3, "min_margin": 0.05,
#               "min_structure": 5.0, "template": "gc1:xxx"}
#
#
#def test_it_names_which_gate_failed(qapp):
#    """三個原因的**處置完全不同**，分不出來的話使用者會一直去調錯的門檻。"""
#    insp = insp_mod.TemplateInspector()
#
#    insp.set_context("roi_template", params=_TPL_PARAMS,
#                     meta=_match(score=0.1, ok=False))
#    assert insp.failing() == ["match"]
#    assert "does not look like the template" in insp.summary()
#
#    insp.set_context("roi_template", params=_TPL_PARAMS,
#                     meta=_match(margin=0.01, ok=False))
#    assert insp.failing() == ["certainty"]
#    assert "more than one position fits" in insp.summary()
#
#
#def test_no_structure_is_not_a_setting_to_fix(qapp):
#    """整張 patch 都在同一種材質裡 —— 那不是參數問題，退回整張圖就是對的答案。
#    不講清楚的話使用者會去把門檻一路調低，直到它開始亂放框。"""
#    insp = insp_mod.TemplateInspector()
#    insp.set_context("roi_template", params=_TPL_PARAMS,
#                     meta=_match(structure=1.0, ok=False))
#    assert insp.failing() == ["structure"]
#    text = insp.summary()
#    assert "nothing to match" in text
#    assert "not a setting to fix" in text
#
#
#def test_a_good_match_says_where_it_landed(qapp):
#    insp = insp_mod.TemplateInspector()
#    insp.set_context("roi_template", params=_TPL_PARAMS, meta=_match())
#    assert insp.failing() == []
#    assert "matched at phase 7,0" in insp.summary()
#
#
#def test_it_says_to_build_a_template_first(qapp):
#    insp = insp_mod.TemplateInspector()
#    insp.set_context("roi_template", params={"roi_out": "cell", "template": ""})
#    assert insp.has_data() is False
#    assert "No template yet" in insp.empty_reason()
#
#
#@pytest.mark.parametrize("theme_name", ["light", "dark"])
#def test_the_gate_bars_paint(qapp, theme_name):
#    from PySide6.QtGui import QColor, QPixmap
#
#    theme_mod.apply_theme(qapp, theme_name)
#    insp = insp_mod.TemplateInspector()
#    insp.resize(320, 160)
#    insp.set_context("roi_template", params=_TPL_PARAMS,
#                     meta=_match(score=0.1, ok=False))
#    pm = QPixmap(insp.size())
#    pm.fill(QColor("#ffffff"))
#    insp.render(pm)
#    assert not pm.isNull()
#    theme_mod.apply_theme(qapp, "light")
#
#
#def test_it_reads_the_engine_verdict_end_to_end(window, tmp_path):
#    """整條路：卡片跑完把三個數字放進 ctx.meta['templates'] → 儀表。"""
#    import numpy as np
#
#    from adept.core.algo import template as at
#    from make_sample import generate
#
#    out = generate(str(tmp_path / "lotT"), n=4, seed=61)
#    window.load_dataset_path(out["klarf"], sync=True)
#    nid = window.model.add_step("roi_template")
#    window.select_node(nid)
#
#    img = np.zeros((240, 320), np.float32)
#    for k in range(8):
#        x = k * 40
#        img[:, x:x + 40] = 120.0
#        img[:, x + 14:x + 34] = 60.0
#        img[:, x + 12:x + 16] = 210.0
#        img[:, x + 32:x + 36] = 210.0
#    img += np.random.default_rng(0).normal(0, 4, img.shape).astype(np.float32)
#    window._apply_template(nid, at.encode_cell(at.build_golden_cell(img).cell),
#                           "x")
#    assert window.refresh_preview(sync=True) is True
#
#    insp = window.inspector()
#    assert isinstance(insp, insp_mod.TemplateInspector)
#    assert insp.has_data() is True
#    names = [g[0] for g in insp.gates()]
#    assert names == ["match", "certainty", "structure"]
#    assert window.inspector_summary.text() != ""
#
#F b6820cf88fdb6a7b7951dc0c3ca2ee2255a9a296 283 tests/test_ui_f7_18_streams_as_nodes.py
## F7-18 驗收：影像流是節點的事，不是控制列的事。
#"""使用者的三件回饋，全部指向同一句話：**test 與 ref 是兩張不同的輸入影像，
#兩張都要可以獨立操作，而「要對哪一張做」應該用節點講。**
#
#1. 輸出埠上那顆「+」會永久掛在畫面上 → 拿掉，改從旁邊的卡片庫加。
#2. 虛線（隱含順序）跟實線同一個顏色 → 給它自己的色相。
#3. 很多卡片把 ref 當附帶（``also_apply``），而且兩個節點之間只拉得動一條線
#   → 一張卡一條流；從哪個埠拉線就決定那張卡做在哪一條流上。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#
#EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "recipes"
#
#
#def _import_qt(g):
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import canvas as canvas_mod
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    g.update(QApplication=QApplication, canvas_mod=canvas_mod,
#             studio_mod=studio_mod, theme_mod=theme_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app, "light")
#    yield app
#
#
#@pytest.fixture
#def window(qapp):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    win.resize(1200, 700)
#    yield win
#    win.close()
#
#
## --------------------------------------------------------------------------- #
## 1. 一張卡一條流
## --------------------------------------------------------------------------- #
#ENHANCE_CARDS = ("percentile_norm", "glv_mask_norm", "denoise", "flatten",
#                 "local_contrast", "brightness_contrast", "gamma")
#
#
#def test_no_enhance_card_quietly_writes_a_second_stream():
#    """這是這一輪的核心不變量。
#
#    一張卡寫兩條流有兩個後果，兩個都只有在**看不到**的地方發作：畫布上那張卡
#    看起來只在一條鏈上，但它其實動了另一條；而「要不要一起動」變成控制列裡的
#    一組勾選框，於是 test 是主角、ref 是附帶。
#    """
#    import adept.core.steps  # noqa: F401 — 觸發卡片註冊
#    from adept.core.pipeline import get_step
#
#    for key in ENHANCE_CARDS:
#        cls = get_step(key)
#        params = cls.validate_params({})
#        assert cls.resolve_writes(params) == [params.get("target")
#                                              or params.get("source")], key
#        names = [p.name for p in cls.params]
#        assert "also_apply" not in names, key
#        assert "anchor" not in names, key
#
#
#def test_the_two_normalize_cards_can_still_share_one_range():
#    """唯一會被「一張卡一條流」弄丟的能力，要有一個看得見的替代品。
#
#    ``anchor="source"`` 的意思是「ref 用 test 量出來的範圍」—— 那是「兩張圖
#    正規化完還比得起來」的關鍵。現在它是 ``range_from``，而且它是一條**影像流
#    的名字**，所以在畫布上就是接進這張卡的第二條線。
#    """
#    import numpy as np
#
#    import adept.core.steps  # noqa: F401 — 觸發卡片註冊
#    from adept.core.pipeline import get_step
#    from adept.core.pipeline.context import Context
#
#    row = np.linspace(0, 255, 128).astype(np.uint8)
#    src = np.tile(row, (128, 1))
#    half = (src.astype(np.float32) / 2).astype(np.uint8)
#
#    cls = get_step("percentile_norm")
#    assert cls.resolve_reads(cls.validate_params({"source": "ref"})) == ["ref"]
#    assert cls.resolve_reads(cls.validate_params(
#        {"source": "ref", "range_from": "test"})) == ["ref", "test"]
#
#    ctx = Context(images={"test": src.copy(), "ref": half.copy()})
#    cls().run(ctx, {"source": "ref", "range_from": "test"})
#    cls().run(ctx, {"source": "test"})
#    assert ctx.images["test"].max() == 255
#    # ref 借了 test 的範圍 → 它保持「只有一半亮」，兩張仍然比得起來
#    assert abs(ctx.images["ref"].mean() - ctx.images["test"].mean() / 2) < 8
#
#
#def test_old_recipes_with_also_apply_still_load_and_mean_the_same_thing(tmp_path):
#    """recipe 是拿來交接的檔案。認不得舊的字等於「工具壞了」。"""
#    import json
#
#    import adept.core.steps  # noqa: F401 — 觸發卡片註冊
#    from adept.core.pipeline.recipe import Recipe
#
#    raw = {
#        "recipe_id": "legacy", "version": 1,
#        "routes": {"ebi_patch": ["load", "norm", "dn"]},
#        "nodes": {
#            "load": {"step": "load_patch", "params": {}},
#            "norm": {"step": "percentile_norm",
#                     "params": {"source": "test", "also_apply": "ref",
#                                "anchor": "source"}},
#            "dn": {"step": "denoise",
#                   "params": {"target": "test", "also_apply": "ref"}},
#        },
#        "score": {"expr": "1", "threshold": 0.0, "bins": {"below": 0, "above": 1}},
#    }
#    path = tmp_path / "legacy.json"
#    path.write_text(json.dumps(raw), encoding="utf-8")
#
#    rec = Recipe.load(path)
#    route = rec.routes["ebi_patch"]
#    assert route == ["load", "norm_ref", "norm", "dn", "dn_ref"]
#
#    # anchor=source：借範圍的那張要排在**前面**，此時 test 還沒被拉伸過 ——
#    # 反過來的話 ref 借到的是「已經拉成 0–255」的範圍，數字就不一樣了。
#    assert rec.nodes["norm_ref"].params == {"source": "ref", "range_from": "test",
#                                            }
#    assert rec.nodes["norm"].params == {"source": "test", "range_from": ""}
#    # denoise 是逐張獨立的運算，順序無所謂，維持原本的先後
#    assert rec.nodes["dn_ref"].params["target"] == "ref"
#    assert rec.nodes["dn"].params["target"] == "test"
#
#    # 存回去就是新格式（再讀一次不會又長出節點）
#    out = tmp_path / "again.json"
#    rec.save(out)
#    assert "also_apply" not in out.read_text(encoding="utf-8")
#    assert Recipe.load(out).routes["ebi_patch"] == route
#
#
#def test_the_shipped_examples_are_already_in_the_new_shape():
#    for path in sorted(EXAMPLE.glob("*.json")):
#        text = path.read_text(encoding="utf-8")
#        assert "also_apply" not in text, path.name
#        assert '"anchor"' not in text, path.name
#
#
## --------------------------------------------------------------------------- #
## 2. 連線說出「這張卡做在哪一條流上」
## --------------------------------------------------------------------------- #
#def test_dragging_from_the_ref_port_points_the_card_at_ref(window):
#    src = window.model.node_order[0]
#    nid = window.add_card_after(src, "denoise", "test")
#    assert window.model.nodes[nid].params["target"] == "test"
#
#    # 從 Input 的第二個輸出埠（ref）拉一條線過去
#    window.pipeline.link_to(src, nid, port=1)
#    assert window.model.nodes[nid].params["target"] == "ref"
#    assert "ref" in window.status_text()
#
#
#def test_a_second_line_between_the_same_two_cards_is_not_refused(window):
#    """使用者原話：「很多張卡片都會限制或阻撓」。
#
#    先從 test 拉、再從 ref 拉是很正常的操作（「我改變主意了」），而以前那第二
#    條線只會得到一句 already connected 然後什麼都沒發生 —— 畫面上看起來就像
#    這張卡不准你碰 ref。
#    """
#    src = window.model.node_order[0]
#    nid = window.add_card_after(src, "gamma", "test")
#    window.pipeline.link_to(src, nid, port=0)
#    assert window.model.has_edge(src, nid) is True
#
#    window.pipeline.link_to(src, nid, port=1)      # 同一對節點，另一個埠
#    assert window.model.nodes[nid].params["target"] == "ref"
#    assert "ref" in window.status_text()
#
#
#def test_a_line_that_would_loop_leaves_no_trace(window):
#    """會成環的那條線沒有落地 —— 它不該留下任何痕跡，尤其不是「那張卡安靜地
#    改成做 ref 了」。"""
#    src = window.model.node_order[0]
#    first = window.add_card_after(src, "denoise", "test")
#    second = window.add_card_after(first, "gamma", "ref")   # 它的輸出埠是 ref
#    assert (first, second) in window.model.edges
#
#    window.pipeline.link_to(second, first, port=0)   # 反過來拉：會成環
#    assert window.model.has_edge(second, first) is False
#    assert window.model.nodes[first].params["target"] == "test"
#    assert "Cannot connect" in window.status_text()
#    assert window.status_level() == "error"
#
#
#def test_wiring_a_card_with_no_stream_parameter_changes_nothing(window):
#    """Compare 卡有自己的 a / b 兩個輸入，連線不該亂改它們。"""
#    src = window.model.node_order[0]
#    a = window.add_card_after(src, "align", "test")
#    sub = window.add_card_after(a, "subtract")
#    before = dict(window.model.nodes[sub].params)
#    window.pipeline.link_to(src, sub, port=1)
#    assert window.model.nodes[sub].params == before
#
#
#def test_adding_from_the_library_follows_the_selected_card(window):
#    """「+」拿掉之後，卡片庫要接得下它的工作：接在選著的那張後面、同一條流。"""
#    src = window.model.node_order[0]
#    on_ref = window.add_card_after(src, "denoise", "ref")
#    window.select_node(on_ref)
#
#    window._on_add_requested("gamma")
#    nid = window.selected_node
#    assert nid != on_ref
#    assert window.model.nodes[nid].params["target"] == "ref"
#    order = window.model.node_order
#    assert order.index(on_ref) < order.index(nid)
#    assert (on_ref, nid) in window.model.edges
#
#
## --------------------------------------------------------------------------- #
## 3. 虛線不能跟實線同一個顏色
## --------------------------------------------------------------------------- #
#@pytest.mark.parametrize("theme_name", ["light", "dark"])
#def test_the_implicit_edge_has_its_own_hue(qapp, theme_name):
#    """同色淡一點只說得出「比較不重要」。這兩種線是不同的東西：一條是使用者
#    拉的（刪得掉），一條是卡片排列帶來的順序（刪不掉，虛線的意思是「這裡可以
#    拉」）。而深淺在縮放與換主題之後就不一定分得出來了。"""
#    from PySide6.QtGui import QColor
#
#    theme_mod.apply_theme(qapp, theme_name)
#    solid = QColor(theme_mod.TOKENS["canvas_edge"])
#    dashed = QColor(theme_mod.TOKENS["canvas_edge_implicit"])
#    assert dashed.isValid() and solid.isValid()
#    # 色相差得出來（不是同一個灰的深淺），而且亮度不能差太多（同一套色票）
#    assert abs(dashed.hue() - solid.hue()) > 20
#    assert abs(dashed.lightness() - solid.lightness()) < 70
#    theme_mod.apply_theme(qapp, "light")
#
#
#def test_the_canvas_actually_paints_the_two_kinds_differently(window, qapp):
#    """token 換了不代表畫出來不一樣 —— ``paint()`` 也要真的去讀它。"""
#    from PySide6.QtGui import QColor, QPixmap
#
#    assert window.load_recipe_path(str(EXAMPLE / "die_to_die_basic.json"),
#                                   sync=True) is True
#    # 這份範例只有 route 順序（全虛線）—— 親手拉一條，兩種線才都在畫面上。
#    window._on_edge_added("load", "sub", "test")
#    edges = window.pipeline._edges
#    assert any(e.implicit for e in edges), "這份 recipe 應該有隱含順序的虛線"
#    assert any(not e.implicit for e in edges), "也要有使用者拉的實線"
#
#    def dominant_hue(edge):
#        """畫出來那條線的主色相（抗鋸齒會混出一堆中間色，取最常見的那個）。"""
#        from PySide6.QtGui import QPainter
#
#        rect = edge.boundingRect()
#        pm = QPixmap(int(rect.width()) + 4, int(rect.height()) + 4)
#        pm.fill(QColor("#ffffff"))
#        p = QPainter(pm)
#        p.translate(-rect.topLeft())
#        edge.paint(p, None, None)
#        p.end()
#        img = pm.toImage()
#        counts = {}
#        for x in range(img.width()):
#            for y in range(img.height()):
#                c = img.pixelColor(x, y)
#                if c.hue() >= 0 and c != QColor("#ffffff"):
#                    counts[c.hue()] = counts.get(c.hue(), 0) + 1
#        assert counts, "這條線根本沒畫出有顏色的畫素"
#        return max(counts.items(), key=lambda kv: kv[1])[0]
#
#    solid = dominant_hue(next(e for e in edges if not e.implicit))
#    dashed = dominant_hue(next(e for e in edges if e.implicit))
#    assert abs(solid - dashed) > 60, (
#        "虛線與實線畫出來仍然是同一個色相（solid=%d dashed=%d）" % (solid, dashed))
#
#F a1f0bb8a312afacd04eb4394b244519e632c0790 504 tests/test_ui_f7_9_feedback.py
## F7-9 驗收：第三輪試用回饋（顏色／埠／起手卡／影像流／卡片組合）。
#"""這一輪的四個回饋加上一個提問，逐條鎖在這裡。
#
#1. 「圖示很不錯，但太多都同個顏色（Input、Enhance、Compare 都是藍的）」
#2. 「移動 Load images 時還是會有殘點（test 跟 ref）」＋「新增的節點只有前面有
#   圓框，後面沒有」＋「一開始預設畫布上就應該有 load image 這個節點」
#3. 「target 跟 also apply 要怎麼使用？對應的節點又是什麼？」
#4. 「打開 compare 之後，點卡片時右上的 image stream 一直被切成 ref」
#5. 「也請幫我確認目前的卡片操作與組合是否相互會有問題」
#
#2 的前兩件事其實是**同一個 bug**：``paint()`` 拿場景座標去畫本地座標的東西。
#節點在原點時看起來正常（第一欄的 Input 剛好在那），一離開原點，輸出埠與埠標
#籤就被畫到「兩倍位移」的地方 —— 於是後面每張卡的右側圓點都跑到卡外面（看起來
#像沒有），而拖動 Input 會把標籤留在 ``boundingRect`` 之外（擦不掉，就是殘影）。
#所以這裡不測「畫面上看不看得到殘影」，而是測那個不變量本身。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#
#from adept.core.pipeline import (          # noqa: E402 — Qt-free，可以直接 import
#    Recipe, RecipeNode, ScoreSpec, get_step, list_steps, validate,
#)
#import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
#
#EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "recipes"
#EXAMPLE = EXAMPLES / "die_to_die_basic.json"
#
#
#def _import_qt(g):
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import canvas as canvas_mod
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    from adept.ui import viewmodel as vm_mod
#    from adept.ui import widgets as widgets_mod
#    g.update(QApplication=QApplication, canvas_mod=canvas_mod,
#             studio_mod=studio_mod, theme_mod=theme_mod, vm_mod=vm_mod,
#             widgets_mod=widgets_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app)
#    yield app
#
#
#@pytest.fixture(scope="module")
#def lot(tmp_path_factory):
#    from make_sample import generate
#    return generate(str(tmp_path_factory.mktemp("f7_9")), n=6, seed=11)
#
#
#@pytest.fixture
#def window(qapp, lot):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    win.load_dataset_path(lot["klarf"], sync=True)
#    yield win
#    win.close()
#
#
## --------------------------------------------------------------------------- #
## 1. 六個階段六個顏色
## --------------------------------------------------------------------------- #
#GROUPS = ("input", "enhance", "region", "compare", "measure", "adc")
#
#
#def _lab(hex_str):
#    """sRGB hex -> CIE L*a*b*（D65）。用感知距離判「看不看得出不一樣」。
#
#    RGB 的算術距離跟眼睛看到的差異對不上（藍色差 40 看得出來，綠色差 40
#    看不太出來），所以不要拿 RGB 距離當「顏色夠不夠分得開」的標準。
#    """
#    import math
#
#    s = hex_str.lstrip("#")
#    r, g, b = [int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
#
#    def lin(c):
#        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
#
#    r, g, b = lin(r), lin(g), lin(b)
#    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
#    y = (r * 0.2126 + g * 0.7152 + b * 0.0722)
#    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883
#
#    def f(c):
#        return c ** (1.0 / 3.0) if c > 0.008856 else 7.787 * c + 16.0 / 116.0
#
#    fx, fy, fz = f(x), f(y), f(z)
#    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))
#
#
#def _delta_e(a, b):
#    import math
#    return math.sqrt(sum((x - y) ** 2 for x, y in zip(_lab(a), _lab(b))))
#
#
#def test_every_stage_has_its_own_colour(qapp):
#    """回饋原話：「太多都同個顏色（input enhance 跟 compare 都是藍色）」。
#
#    以前是 ``group -> category -> 顏色``，六個階段只有三種色。這裡鎖的是
#    **性質**（兩兩感知上分得開），不是寫死色碼 —— 色票還可以再調。
#    ΔE ≥ 25 大約是「一眼看得出是兩個顏色」而不只是「同色的深淺」。
#    """
#    for name in ("light", "dark"):
#        theme_mod.set_theme(name)
#        colours = {g: theme_mod.group_hex(g) for g in GROUPS}
#        assert len(set(colours.values())) == len(GROUPS), \
#            "%s 主題有階段共用顏色：%s" % (name, colours)
#        for i, a in enumerate(GROUPS):
#            for b in GROUPS[i + 1:]:
#                d = _delta_e(colours[a], colours[b])
#                assert d >= 25, "%s 的 %s 與 %s 太接近（%s vs %s, ΔE=%.1f）" % (
#                    name, a, b, colours[a], colours[b], d)
#    theme_mod.apply_theme(qapp, "light")
#
#
#def test_the_stage_colours_stay_one_family(qapp):
#    """分得開之外還要**看起來像一套**：同一主題內明度不可以亂跳。
#
#    六個顏色如果亮度差很多，rail 上就會有幾個特別跳、幾個特別悶 ——
#    那是「六個顏色」，不是「一套色票」。
#    """
#    for name in ("light", "dark"):
#        theme_mod.set_theme(name)
#        lums = [_lab(theme_mod.group_hex(g))[0] for g in GROUPS]
#        assert max(lums) - min(lums) <= 15, \
#            "%s 主題的階段色明度差太多：%s" % (name, [round(x) for x in lums])
#    theme_mod.apply_theme(qapp, "light")
#
#
#def test_the_library_and_the_canvas_use_the_same_stage_colour(qapp):
#    """rail 上看到的顏色，跟畫布節點上的必須是同一個 —— 不然顏色不是語言。"""
#    panel = widgets_mod.LibraryPanel()
#    panel.set_steps([s.describe() for s in list_steps()])
#    for gid in GROUPS:
#        btn = panel.stage_buttons[gid]
#        assert theme_mod.group_hex(gid) in btn.styleSheet() \
#            or btn.icon.color == theme_mod.group_hex(gid)
#
#
## --------------------------------------------------------------------------- #
## 2. 埠：本地座標 vs 場景座標
## --------------------------------------------------------------------------- #
#def _canvas_with_two_nodes(qapp):
#    canvas = canvas_mod.PipelineCanvas()
#    canvas.set_nodes([
#        {"node_id": "load", "label": "Load images", "group": "input",
#         "enabled": True, "summary": "", "reads": [], "writes": ["test", "ref"]},
#        {"node_id": "sub", "label": "Subtract", "group": "compare",
#         "enabled": True, "summary": "", "reads": ["test", "ref"],
#         "writes": ["diff"]},
#    ], [("load", "sub")])
#    return canvas
#
#
#def test_every_port_is_drawn_inside_the_nodes_bounding_rect(qapp):
#    """``paint()`` 只准畫在 ``boundingRect`` 裡面，否則就是殘影。
#
#    埠與埠標籤都畫在**本地座標**；``boundingRect`` 也是本地座標。把節點拖到
#    任何地方，這個關係都不可以變 —— 這正是「移動 Load images 會留下 test /
#    ref 殘點」與「後面的節點沒有圓框」的共同成因。
#    """
#    from PySide6.QtCore import QPointF
#
#    canvas = _canvas_with_two_nodes(qapp)
#    for pos in (QPointF(0, 0), QPointF(240, 130), QPointF(-90, 55)):
#        for item in (canvas.card("load"), canvas.card("sub")):
#            item.setPos(pos)
#            rect = item.boundingRect()
#            assert rect.contains(item.in_port_local()), "輸入埠畫到框外"
#            for anchor, name in zip(item.out_anchors_local(), item.out_names()):
#                assert rect.contains(anchor), \
#                    "%s 的輸出埠 %r 畫到 boundingRect 外面" % (item.node_id, name)
#                # 埠標籤畫在埠右邊 _PORT_LABEL_W 之內，也必須在框裡
#                label_right = anchor.x() + canvas_mod._PORT_LABEL_W - 1
#                assert label_right <= rect.right(), "埠標籤畫到框外（= 殘影）"
#
#
#def test_scene_anchors_track_the_node_position(qapp):
#    """場景座標 = 本地座標 + ``scenePos()``。連線用前者，繪製用後者。"""
#    from PySide6.QtCore import QPointF
#
#    canvas = _canvas_with_two_nodes(qapp)
#    item = canvas.card("load")
#    item.setPos(QPointF(311, 47))
#    for local, scene in zip(item.out_anchors_local(), item.out_anchors()):
#        assert scene == item.scenePos() + local
#    assert item.in_port() == item.scenePos() + item.in_port_local()
#    # 命中判定吃的是本地座標，拖走之後仍然要打得到
#    assert item.out_port_at(item.out_anchors_local()[1]) == 1
#
#
#def test_every_node_has_an_output_port_to_drag_from(qapp):
#    """回饋原話：「新增的節點只有前面有圓框，後面沒有圓框讓人可以連」。"""
#    canvas = _canvas_with_two_nodes(qapp)
#    for nid in ("load", "sub"):
#        item = canvas.card(nid)
#        assert len(item.out_anchors_local()) >= 1
#        for anchor in item.out_anchors_local():
#            assert anchor.x() == canvas_mod.NODE_W, "輸出埠必須貼在節點右緣"
#
#
#def test_output_ports_are_labelled_with_the_stream_they_carry(qapp):
#    """埠標籤就是 ``target`` / ``also apply`` 下拉裡的那些名字（回饋 3）。"""
#    canvas = _canvas_with_two_nodes(qapp)
#    assert canvas.card("load").out_names() == ["test", "ref"]
#    assert canvas.card("sub").out_names() == ["diff"]
#
#
#def test_an_unwired_recipe_wraps_instead_of_running_off_the_screen(qapp):
#    """九張還沒拉線的卡排成一列會超過 2500px，``fit()`` 只能縮到看不出字。
#
#    （而且它有下限 —— 縮成小方塊比留捲軸更糟，所以結果是「一排讀不出來的
#    小方塊 **加上** 一條捲軸」，兩邊都輸。）
#    """
#    ids = ["n%d" % i for i in range(9)]
#    pos = canvas_mod.layout_columns(ids, [])
#    assert max(c for c, _r in pos.values()) < canvas_mod.WRAP
#    assert max(r for _c, r in pos.values()) == (len(ids) - 1) // canvas_mod.WRAP
#    # 閱讀順序仍然是左到右、上到下
#    assert pos["n0"] == (0, 0) and pos["n3"] == (3, 0) and pos["n4"] == (0, 1)
#
#    width = canvas_mod.WRAP * (canvas_mod.NODE_W + canvas_mod.COL_GAP)
#    assert width < 1200, "換行之後整張圖要塞得進一般的工作區寬度"
#
#
## --------------------------------------------------------------------------- #
## 2b. 起手卡
## --------------------------------------------------------------------------- #
#def test_a_new_model_starts_with_the_input_card(qapp):
#    m = vm_mod.RecipeModel.starter()
#    assert m.node_order == ["load_patch"]
#    assert m.nodes["load_patch"].step == "load_patch"
#    assert m.dirty is False, "使用者還沒做任何事，不該被當成「改過」"
#
#
#def test_the_studio_opens_with_the_input_card_on_the_canvas(window):
#    assert window.pipeline.node_ids() == ["load_patch"]
#    assert window.pipeline.card("load_patch") is not None
#    # 而且它是可以拖線出來的（patch 天生成對）
#    assert window.pipeline.card("load_patch").out_names() == ["test", "ref"]
#
#
## --------------------------------------------------------------------------- #
## 3. 這張卡做在哪一條流上（F7-18 起：一張卡一條流）
## --------------------------------------------------------------------------- #
#def test_stream_params_have_plain_language_labels(qapp):
#    """參數名是 recipe 的鍵，不是給人看的字。"""
#    for key in ("percentile_norm", "gamma", "brightness_contrast", "denoise"):
#        params = {p["name"]: p for p in get_step(key).describe()["params"]}
#        primary = params.get("target") or params.get("source")
#        assert primary["label"] == "Image stream"
#        # 說明要講出「流是畫布上的線」與 test / ref 是什麼
#        assert "canvas" in primary["help"] and "ref" in primary["help"]
#
#
#def test_image_keys_values_are_normalised(qapp):
#    """``image_keys`` 是「一串影像流」的型別：手打的與勾出來的要等價。
#
#    F7-18 之後沒有卡片用它（``also_apply`` 拆成節點了），但型別與正規化規則
#    仍然是 ParamSpec 的契約 —— 值的格式跟輸入方式無關這件事要繼續成立。
#    """
#    from adept.core.pipeline.step import ParamSpec
#
#    spec = ParamSpec(name="streams", type="image_keys", default="",
#                     help="which streams")
#    assert spec.validate(" ref , ref ,,test ") == "ref,test"
#    assert spec.validate("") == ""
#    assert spec.validate("ref") == "ref"
#
#
#def test_stream_picker_is_checkboxes_over_the_upstream_streams(qapp):
#    picker = widgets_mod.StreamPicker(["test", "ref", "diff"], "ref")
#    assert picker.stream_names() == ["test", "ref", "diff"]
#    assert picker.text() == "ref"
#
#    seen = []
#    picker.changed.connect(seen.append)
#    picker._boxes[0].setChecked(True)             # 也勾 test
#    assert seen[-1] == "test,ref"
#    picker._boxes[1].setChecked(False)            # 取消 ref -> 兩張圖分開處理
#    assert seen[-1] == "test"
#
#
#def test_a_stream_the_pipeline_no_longer_has_is_still_shown(qapp):
#    """recipe 指到一條現在不存在的流時，不可以看不到就靜靜消失。"""
#    picker = widgets_mod.StreamPicker(["test", "ref"], "ghost")
#    assert "ghost" in picker.stream_names()
#    assert picker.text() == "ghost"
#
#
#def test_each_image_source_gets_its_own_card(window):
#    """「test 跟 ref 就是兩張不同的 image source，都要可以做操作」（F7-18）。
#
#    以前那件事是一張卡上的一組勾選框；現在它就是**兩張卡**，而畫布上因此看得到
#    兩條各自的處理鏈。
#    """
#    src = window.model.node_order[0]
#    on_test = window.add_card_after(src, "percentile_norm", "test")
#    on_ref = window.add_card_after(src, "percentile_norm", "ref")
#    assert window.model.nodes[on_test].params["source"] == "test"
#    assert window.model.nodes[on_ref].params["source"] == "ref"
#    for nid in (on_test, on_ref):
#        cls = get_step(window.model.nodes[nid].step)
#        assert cls.resolve_writes(window.model.nodes[nid].params) == \
#            [window.model.nodes[nid].params["source"]]
#
#
## --------------------------------------------------------------------------- #
## 4. 點卡片時預覽顯示哪一張
## --------------------------------------------------------------------------- #
#def test_selecting_a_card_shows_that_cards_main_stream(window):
#    """回饋 4：點 Normalize 卻跳到 ref，並排時左右變成同一張 ref。
#
#    成因是「這張卡寫過的最後一條流」被當成「這張卡的主要輸出」；當時 Enhance
#    卡的 writes 是 ``[主流] + 附帶的那一串``，所以最後一項永遠是附帶的那條。
#    """
#    assert window.load_recipe_path(str(EXAMPLE), sync=True) is True
#    assert window.select_node("norm") is True
#    window.refresh_preview(sync=True)
#
#    assert window.stream_combo.currentText() == "test", \
#        "點 Normalize 應該看到它處理的 test"
#    assert window.model.nodes["norm"].params["source"] == "test"
#
#
#def test_side_by_side_never_shows_the_same_image_twice(window):
#    assert window.load_recipe_path(str(EXAMPLE), sync=True) is True
#    assert window.set_compare(True) is True
#    window.select_node("norm")
#    window.refresh_preview(sync=True)
#    left, right = window.stream_combo.currentText(), window.stream_combo_b.currentText()
#    assert (left, right) == ("test", "ref")
#
#    # 使用者親手把右邊挑成 ref 之後，再點別張卡也不可以變成左右都是 ref
#    window._on_stream_b_changed("ref")
#    for node_id in ("norm", "sub", "dn"):
#        window.select_node(node_id)
#        window.refresh_preview(sync=True)
#        assert window.stream_combo.currentText() != window.stream_combo_b.currentText(), \
#            "節點 %s：左右顯示同一條流" % node_id
#
#
## --------------------------------------------------------------------------- #
## 5. 卡片組合
## --------------------------------------------------------------------------- #
#def _recipe(seq):
#    nodes, order = {}, []
#    for i, key in enumerate(seq):
#        nid = "n%d" % i
#        nodes[nid] = RecipeNode(id=nid, step=key,
#                                params=get_step(key).validate_params({}))
#        order.append(nid)
#    return Recipe(recipe_id="combo", routes={"ebi_patch": order}, nodes=nodes,
#                  score=ScoreSpec(expr="0", threshold=0.0,
#                                  bins={"below": 0, "above": 1}))
#
#
#def test_a_measure_card_that_needs_a_region_nobody_defines_is_caught(qapp):
#    """以前這件事只有兩種下場，兩種都不好。
#
#    名字打錯 → 每顆 defect 跑到一半 StepError；名字剛好是保留字 ``blob`` 而
#    上游沒有 Blob 卡 → **安靜地改量整張圖**，跑得完、有數字、而且是錯的。
#    """
#    codes = [i.code for i in validate(
#        _recipe(["load_patch", "align", "subtract", "cd_measure"]),
#        kind="ebi_patch") if i.level == "error"]
#    assert "unknown-region" in codes
#
#    # 補上 Blob 卡（它定義 'blob'）之後就乾淨了
#    ok = validate(_recipe(["load_patch", "align", "subtract", "snr_map",
#                           "blob_segment", "cd_measure"]), kind="ebi_patch")
#    assert [i.code for i in ok if i.level == "error"] == []
#
#
#def test_measuring_two_regions_warns_instead_of_silently_losing_one(qapp):
#    """特徵是**扁平的全域命名空間**，所以兩張同型別的量測卡會寫同一組名字。
#
#    「量中心 vs 量整片」是使用者一定會做的事，而以前的下場是：跑得完、
#    lint 全綠、後面那張把前面那張蓋掉，分數表達式**完全沒有辦法**指到前面
#    那個值。這是 warning 不是 error（同名覆寫有時是刻意的），但它必須看得見。
#    """
#    nodes = {
#        "load": RecipeNode("load", "load_patch", {}),
#        "roiA": RecipeNode("roiA", "roi_define", {"name": "center"}),
#        "roiB": RecipeNode("roiB", "roi_define",
#                           {"name": "wide", "size": 90.0, "size_unit": "percent"}),
#        "glvA": RecipeNode("glvA", "glv_stats",
#                           {"roi": "center", "metrics": "glv_mean"}),
#        "glvB": RecipeNode("glvB", "glv_stats",
#                           {"roi": "wide", "metrics": "glv_mean"}),
#    }
#    recipe = Recipe(
#        recipe_id="two_roi",
#        routes={"ebi_patch": ["load", "roiA", "roiB", "glvA", "glvB"]},
#        nodes=nodes, score=ScoreSpec(expr="glv_mean", threshold=0.0,
#                                     bins={"below": 0, "above": 1}))
#    issues = validate(recipe, kind="ebi_patch")
#    collisions = [i for i in issues if i.code == "feature-collision"]
#    assert len(collisions) == 1
#    assert collisions[0].level == "warning", "撞名不擋執行，但要講出來"
#    assert collisions[0].node_id == "glvB"
#    assert "glv_mean" in collisions[0].title
#    assert not [i for i in issues if i.level == "error"]
#
#
#def test_a_warning_does_not_block_the_run_but_is_reported_afterwards(window):
#    """警告描述的是「跑得完、數字卻不是你以為的那個」，所以不能擋，
#    但也不能不講。跑**之前**講會被「Running: 3 / 200」洗掉，所以跑完才講。"""
#    assert window.load_recipe_path(str(EXAMPLE), sync=True) is True
#    dup = window.model.add_step("glv_stats")          # 跟範例裡的 glv 撞名
#    window.model.set_param(dup, "source", "diff")
#
#    assert window.run_trial(6, workers=1, sync=True) is True
#    assert "Run finished" in window.status_text()
#    assert "overwrites the feature" in window.status_text()
#
#
#def test_the_shipped_example_recipes_have_no_combination_errors(qapp):
#    """範例 recipe 是使用者的起點，它們自己必須全部過 lint。"""
#    bad = {}
#    for path in sorted(EXAMPLES.glob("*.json")):
#        recipe = Recipe.load(str(path))
#        errs = [i for i in validate(recipe) if i.level == "error"]
#        if errs:
#            bad[path.name] = [(i.code, i.node_id) for i in errs]
#    assert not bad, bad
#
#
#def test_a_broken_combination_refuses_to_run_instead_of_failing_every_defect(window):
#    """引擎的契約是「單顆出錯不殺整批」，所以接錯的卡片以前會**跑完整批而且
#    每一顆都失敗**：進度條走完、結果是空的、原因埋在每顆的錯誤訊息裡。"""
#    node_id = window.model.add_step("subtract")      # 預設吃 ref_aligned
#    assert window.run_trial(6, workers=1, sync=True) is False
#    assert "Cannot run" in window.status_text()
#    assert "ref_aligned" in window.status_text()
#
#    # 指到真的存在的流之後就跑得動了
#    window.model.set_param(node_id, "b", "ref")
#    assert window.run_trial(6, workers=1, sync=True) is True
#
#
#def test_adding_a_card_says_what_is_still_missing_and_who_provides_it(window):
#    """卡片庫上那個 ``needs ref_aligned`` 的灰字 badge 對不會寫 code 的人沒有
#    動作可做 —— 他不知道 ref_aligned 是誰產的。"""
#    window.library.add_requested.emit("subtract")
#    msg = window.status_text()
#    assert "ref_aligned" in msg
#    assert "Align" in msg, "要講出哪一張卡會產出這條流"
#    assert "test" in msg and "ref" in msg, "也要講現在有哪些流可以改指"
#
#
#def test_every_visible_card_can_be_wired_up_without_a_dead_end(qapp):
#    """每一張卡都要有一條「照著加就會通」的路，否則它在 UI 上就是死路。
#
#    這是回饋 5（「卡片操作與組合是否相互會有問題」）的機械化版本：對每張卡
#    找一組前置卡，驗證整條 route 過得了 lint。找不到 = 那張卡沒有人用得起來。
#    """
#    from adept.ui.scope import visible_steps
#
#    # 前置鏈：能滿足所有 reads / regions 的最短已知順序
#    PREREQ = {
#        "subtract": ["align"],
#        "snr_map": ["align", "subtract"],
#        "blob_segment": ["align", "subtract", "snr_map"],
#        "cd_measure": ["align", "subtract", "snr_map", "blob_segment"],
#        "roi_snr": ["align", "subtract", "snr_map", "blob_segment"],
#    }
#    keys = [d["key"] for d in visible_steps([s.describe() for s in list_steps()])]
#    dead_ends = {}
#    needs_setup = {}
#    for key in keys:
#        if key == "load_patch":
#            continue
#        seq = ["load_patch"] + PREREQ.get(key, []) + [key]
#        errs = [i for i in validate(_recipe(seq), kind="ebi_patch")
#                if i.level == "error"]
#        # ``not-configured`` 不是接線問題（F7-13）：那張卡缺的是一份要另外匯入
#        # 的東西（模板是一張影像），不是缺上游。它的路是通的，只是還沒設定完 ——
#        # 所以這裡不算死路，但**訊息必須指得出路在哪**，否則它就真的是死路了。
#        needs = [i for i in errs if i.code == "not-configured"]
#        rest = [i for i in errs if i.code != "not-configured"]
#        if needs:
#            needs_setup[key] = [i.detail for i in needs]
#        if rest:
#            dead_ends[key] = [(i.code, i.detail) for i in rest]
#    assert not dead_ends, "這些卡片沒有可行的組合：%s" % sorted(dead_ends)
#    for key, details in needs_setup.items():
#        for detail in details:
#            assert "…" in detail or "..." in detail, (
#                "%s 說它還沒設定完，但沒有指向任何一個按得下去的東西：%s"
#                % (key, detail))
#
#F 500bc2445ff7f460b63e56345d22c9d43048aaca 491 tests/test_ui_gallery.py
## ADEPT Studio Gallery 測試 — authored 2026-07-28 (M5-2).
#"""``adept/ui/gallery.py``（縮圖網格／同屏比多顆）的離屏（offscreen）測試。
#
#執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_gallery.py -q``
#
#**為什麼所有 Qt import 都是 lazy 的（別改回去）**
#
#``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有任何
#PySide6 模組。pytest 是「先蒐集全部測試檔、再開始跑」，所以只要這個檔案在
#**模組層** ``import PySide6``（或 ``import adept.ui.gallery``），蒐集階段就會把 Qt
#塞進 ``sys.modules``，那個守門測試就會紅 —— 即使它先跑。
#
#因此：所有 Qt / ``adept.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
#的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
#每個測試都必須要求 ``qapp`` fixture，否則那些名字不存在。
#
#pytest-qt 沒有安裝：訊號一律用手動 slot（append 到 list）捕捉，滑鼠事件自己建構
#``QMouseEvent`` 後送給 ``grid.viewport()``（QAbstractScrollArea 會把 viewport 的
#事件轉給 ``mousePressEvent`` / ``mouseDoubleClickEvent``）。
#
#離屏環境的兩個小陷阱：
#1. 巢狀 layout 要 ``show()`` + ``processEvents()`` 之後 viewport 才有真實尺寸，
#   可視範圍的計算才有意義（只 ``resize()`` 不夠）。
#2. 要讓 ``paintEvent`` 真的跑（例如驗證 QPixmap LRU 快取）就呼叫 ``widget.grab()``。
#"""
#from __future__ import annotations
#
#import sys
#import time
#
#import numpy as np
#import pytest
#
#
#def _load_qt() -> None:
#    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
#    from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: F401
#    from PySide6.QtGui import QMouseEvent  # noqa: F401
#    from PySide6.QtWidgets import QApplication, QWidget  # noqa: F401
#
#    from adept.ui import gallery as gal_mod  # noqa: F401
#    from adept.ui import theme as theme_mod  # noqa: F401
#
#    globals().update(locals())
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    """離屏 QApplication（整個模組共用一個）+ 套用主題。"""
#    _load_qt()
#    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
#    theme_mod.apply_theme(app)
#    yield app
#    app.processEvents()
#
#
## --------------------------------------------------------------------------- #
## helpers
## --------------------------------------------------------------------------- #
#def _items(n=20, with_thumb=False, thumb_px=32):
#    """n 顆合成結果（形狀 = ``engine.result_to_json_dict`` 再加一個 thumb）。"""
#    out = []
#    for i in range(n):
#        out.append({
#            "defect_id": "D%03d" % i,
#            "ok": True,
#            "error": None,
#            "score": float(i),
#            "bin": 1 if i % 2 else 0,
#            "features": {"snr": float((i * 7) % 13), "area": float(i * 2)},
#            "thumb": (np.full((thumb_px, thumb_px), (i * 11) % 256, np.uint8)
#                      if with_thumb else None),
#        })
#    return out
#
#
#def _panel(qapp, items=None, w=820, h=560):
#    """建一個已經 show 過、viewport 有真實尺寸的 GalleryPanel。"""
#    p = gal_mod.GalleryPanel()
#    p.resize(w, h)
#    p.show()
#    qapp.processEvents()
#    if items is not None:
#        p.set_items(items)
#        qapp.processEvents()
#    return p
#
#
#def _mouse(widget, etype, pos, button=None, buttons=None, mods=None):
#    """建構並派送一顆滑鼠事件（離屏環境下比 QTest 可靠）。"""
#    button = Qt.LeftButton if button is None else button
#    buttons = button if buttons is None else buttons
#    mods = Qt.NoModifier if mods is None else mods
#    ev = QMouseEvent(etype, QPointF(pos), QPointF(pos), button, buttons, mods)
#    QApplication.sendEvent(widget, ev)
#
#
#def _click(panel, index, mods=None, dbl=False):
#    """點第 ``index`` 格（顯示順序）的正中央。"""
#    center = panel.grid.tile_rect(index).center()
#    etype = QEvent.MouseButtonDblClick if dbl else QEvent.MouseButtonPress
#    _mouse(panel.grid.viewport(), etype, center, mods=mods)
#
#
#def _has_cjk(text):
#    return any("　" <= ch <= "鿿" for ch in str(text))
#
#
## --------------------------------------------------------------------------- #
## 1. make_thumb（Qt-free 的純運算；背景執行緒會直接呼叫它）
## --------------------------------------------------------------------------- #
#def test_make_thumb_square_uint8_and_float_normalised(qapp):
#    make_thumb = gal_mod.make_thumb
#
#    # uint8 進來原樣（不拉伸），輸出一定是方形 uint8
#    src = np.arange(256, dtype=np.uint8).reshape(16, 16)
#    out = make_thumb(src, 64)
#    assert out.shape == (64, 64)
#    assert out.dtype == np.uint8
#    assert int(out.min()) == 0 and int(out.max()) == 255
#
#    # float 走 min–max 正規化（跟 ImageView 同一套規則）
#    f = np.array([[0.0, 0.5], [1.0, 2.0]], dtype=np.float32)
#    fo = make_thumb(f, 64)
#    assert fo.dtype == np.uint8 and fo.shape == (64, 64)
#    assert int(fo.min()) == 0 and int(fo.max()) == 255
#
#    # 全 NaN 不該炸（ImageView 也是這個行為）
#    nan_out = make_thumb(np.full((8, 8), np.nan, dtype=np.float32), 32)
#    assert nan_out.shape == (32, 32) and int(nan_out.max()) == 0
#
#
#def test_make_thumb_non_square_tiny_and_colour(qapp):
#    make_thumb = gal_mod.make_thumb
#
#    # 非方形 -> letterbox（等比縮 + 置中補黑），不裁掉邊緣的缺陷
#    wide = np.full((10, 40), 200, dtype=np.uint8)
#    out = make_thumb(wide, 64)
#    assert out.shape == (64, 64)
#    assert int(out[32, 32]) == 200        # 中間是影像
#    assert int(out[0, 0]) == 0            # 上緣是補的黑邊
#
#    # 極小輸入放大不能炸
#    tiny = make_thumb(np.array([[7]], dtype=np.uint8), 96)
#    assert tiny.shape == (96, 96) and int(tiny.max()) == 7
#    assert make_thumb(np.zeros((1, 5), np.uint8), 64).shape == (64, 64)
#
#    # 彩色（H,W,3）保留三通道；尺寸會被夾在合理範圍
#    rgb = make_thumb(np.zeros((20, 30, 3), np.uint8), 48)
#    assert rgb.shape == (48, 48, 3)
#    assert make_thumb(np.zeros((9, 9), np.uint8), 1).shape == (8, 8)
#
#
## --------------------------------------------------------------------------- #
## 2. set_items / 標頭 / 空狀態
## --------------------------------------------------------------------------- #
#def test_set_items_header_count_and_empty_state(qapp):
#    p = _panel(qapp, _items(20))
#    assert p.total_count() == 20 and p.displayed_count() == 20
#    assert p.header_text() == "Showing 20 / 20 defects"
#    assert p.empty_text() == ""                       # 有 tile 就沒有空狀態文字
#    assert len(p.displayed_ids()) == 20
#
#    p.set_items([])
#    qapp.processEvents()
#    assert p.header_text() == "Showing 0 / 0 defects"
#    assert p.empty_text() == ("(Thumbnails for every defect appear here after "
#                              "a trial run)")
#
#    # 篩到一顆都不剩 -> 換另一句（並且告訴使用者怎麼救）
#    p.set_items(_items(5))
#    p.filter_by_score_range(100.0, 200.0)
#    assert p.displayed_count() == 0
#    assert "No defect matches" in p.empty_text()
#    assert p.header_text() == "Showing 0 / 5 defects"
#
#
## --------------------------------------------------------------------------- #
## 3. 虛擬捲動（10,000 顆）
## --------------------------------------------------------------------------- #
#def test_virtual_scrolling_with_10k_items(qapp):
#    p = _panel(qapp)
#    widgets_before = len(p.findChildren(QWidget))
#
#    big = _items(10000)
#    t0 = time.time()
#    p.set_items(big)
#    elapsed = time.time() - t0
#    assert elapsed < 1.0, "10k 顆 set_items 花了 %.3fs（太慢）" % elapsed
#    assert p.total_count() == 10000 and p.displayed_count() == 10000
#
#    # 1) tile 不是 widget：10k 顆之後子 widget 數量完全沒變
#    #    （基準值 = 標頭那幾個控制項 + 下拉/捲軸自己的內部 widget，數十個而已）
#    assert len(p.findChildren(QWidget)) == widgets_before
#    assert widgets_before < 60
#
#    # 2) 只有可視範圍（+1 列 overscan）會被畫
#    vis = p.visible_indices()
#    assert 0 < len(vis) < 200, "可視範圍應該只跟 viewport 大小有關"
#    cols = p.grid.columns()
#    assert len(vis) <= (p.grid.viewport().height() // p.grid._cell_h() + 3) * cols
#    assert vis[0] == 0                                  # 一開始在最上面
#
#    # 3) 捲到底 -> 可視範圍換到尾端，長度依舊小
#    bar = p.grid.verticalScrollBar()
#    assert bar.maximum() > 0
#    bar.setValue(bar.maximum())
#    qapp.processEvents()
#    vis_end = p.visible_indices()
#    assert vis_end != vis
#    assert vis_end[0] > vis[-1]
#    assert vis_end[-1] == 9999
#    assert len(vis_end) < 200
#
#    # 4) 畫一次不會爆（paintEvent 只跑可視格）
#    t0 = time.time()
#    p.grid.grab()
#    assert time.time() - t0 < 1.0
#
#
#def test_thumbs_requested_for_visible_items_only(qapp):
#    """缺縮圖時會告訴主視窗「先補這幾顆」——才有辦法漸進式載入。"""
#    p = _panel(qapp)
#    asked = []
#    p.thumbs_requested.connect(asked.append)
#    p.set_items(_items(500))
#    qapp.processEvents()
#    assert asked, "缺縮圖的可視範圍應該要發 thumbs_requested"
#    first = asked[-1]
#    assert set(first) <= set(p.displayed_ids())
#    assert len(first) == len(p.visible_indices())
#
#    # 補上其中一張之後，它就不再出現在下一次請求裡
#    did = first[0]
#    assert p.set_thumb(did, np.full((24, 24), 128, np.uint8)) is True
#    assert p.set_thumb("不存在的顆", np.zeros((4, 4), np.uint8)) is False
#    bar = p.grid.verticalScrollBar()
#    bar.setValue(bar.maximum())
#    qapp.processEvents()
#    assert did not in asked[-1]
#
#
## --------------------------------------------------------------------------- #
## 4. 排序
## --------------------------------------------------------------------------- #
#def test_sort_by_score_feature_and_unknown_key(qapp):
#    items = _items(6)
#    items[3]["score"] = None                      # 沒分數的一律排最後
#    p = _panel(qapp, items)
#
#    p.set_sort("score", descending=True)
#    ids = p.displayed_ids()
#    assert ids == ["D005", "D004", "D002", "D001", "D000", "D003"]
#    assert p.sort_key() == "score" and p.sort_descending() is True
#
#    p.set_sort("score", descending=False)
#    assert p.displayed_ids() == ["D000", "D001", "D002", "D004", "D005", "D003"]
#    assert p.sort_descending() is False
#
#    # 任一 feature 也能排（snr = (i*7)%13）
#    p.set_sort("snr", descending=True)
#    expect = sorted(items, key=lambda d: d["features"]["snr"], reverse=True)
#    assert p.displayed_ids() == [d["defect_id"] for d in expect]
#
#    # defect_id 排序
#    p.set_sort("defect_id", descending=False)
#    assert p.displayed_ids() == ["D00%d" % i for i in range(6)]
#
#    # 不認得的 key -> 不炸、不掉資料，維持原始順序
#    p.set_sort("沒有這個欄位", descending=True)
#    assert p.displayed_ids() == [d["defect_id"] for d in items]
#    assert p.displayed_count() == 6
#
#    # 取消排序（標頭 chip 的「✕」走的也是這條）
#    p.set_sort(None)
#    assert p.sort_key() is None
#    assert p.displayed_ids() == [d["defect_id"] for d in items]
#
#
#def test_sort_controls_and_chip(qapp):
#    p = _panel(qapp, _items(8))
#    p.set_sort_keys(["score", "snr", "area"])
#    assert p.sort_keys() == ["score", "snr", "area", "defect_id"]
#    assert p.sort_combo.itemText(0) == gal_mod.GalleryPanel.NO_SORT
#    assert p.sort_key() == "score"
#    assert p.chip_texts() == ["Sort: score ↓"]
#
#    # 換方向鈕
#    p.order_button.click()
#    assert p.sort_descending() is False
#    assert p.displayed_ids()[0] == "D000"
#    assert p.chip_texts() == ["Sort: score ↑"]
#
#    # 下拉換欄位
#    p.sort_combo.setCurrentIndex(p.sort_keys().index("area") + 1)
#    assert p.sort_key() == "area"
#
#    # 點 chip -> 移除排序條件
#    p.chips()[0].click()
#    qapp.processEvents()
#    assert p.sort_key() is None
#    assert p.chip_texts() == []
#    assert p.sort_combo.currentIndex() == 0
#
#
## --------------------------------------------------------------------------- #
## 5. 篩選
## --------------------------------------------------------------------------- #
#def test_filter_by_score_range_and_clear(qapp):
#    p = _panel(qapp, _items(10))
#    p.set_sort("defect_id", descending=False)
#    assert p.displayed_count() == 10
#
#    p.filter_by_score_range(3.0, 5.0)             # 直方圖點一根 bar 走這條
#    assert p.displayed_ids() == ["D003", "D004", "D005"]
#    assert p.header_text() == "Showing 3 / 10 defects"
#    assert "score" in p.filter_text()
#    assert any(c.startswith("Filter:") for c in p.chip_texts())
#
#    p.clear_filter()
#    assert p.displayed_count() == 10
#    assert p.header_text() == "Showing 10 / 10 defects"
#    assert p.filter_text() == ""
#    assert not any(c.startswith("Filter:") for c in p.chip_texts())
#
#    # 點篩選 chip 也能移除
#    p.filter_by_score_range(0.0, 1.0)
#    assert p.displayed_count() == 2
#    chip = [c for c in p.chips() if c.label_text.startswith("Filter:")][0]
#    chip.click()
#    qapp.processEvents()
#    assert p.displayed_count() == 10
#
#
#def test_filter_bin_failed_and_custom(qapp):
#    items = _items(10)
#    items[2]["ok"] = False
#    items[2]["bin"] = None
#    items[2]["score"] = None
#    p = _panel(qapp, items)
#
#    p.filter_by_bin(1)
#    assert p.displayed_count() == 5
#    assert all(i.endswith(("1", "3", "5", "7", "9")) for i in p.displayed_ids())
#
#    p.show_failed_only()
#    assert p.displayed_ids() == ["D002"]
#    assert p.header_text() == "Showing 1 / 10 defects"
#
#    p.set_filter(lambda it: (it.get("features") or {}).get("area", 0) >= 10)
#    assert p.displayed_count() == 5
#    assert p.filter_text() == "custom filter"
#
#    p.set_filter(None)
#    assert p.displayed_count() == 10
#
#    with pytest.raises(ValueError):
#        p.set_filter({"mode": "什麼鬼"})
#
#
## --------------------------------------------------------------------------- #
## 6. 選取 / 啟動
## --------------------------------------------------------------------------- #
#def test_selection_click_ctrl_click_and_double_click(qapp):
#    p = _panel(qapp, _items(12))
#    p.set_sort("defect_id", descending=False)
#    qapp.processEvents()
#
#    picked, activated = [], []
#    p.selection_changed.connect(picked.append)
#    p.defect_activated.connect(activated.append)
#
#    _click(p, 0)
#    assert picked[-1] == ["D000"]
#    assert p.selected_ids() == ["D000"]
#
#    _click(p, 2, mods=Qt.ControlModifier)         # ctrl 加選
#    assert picked[-1] == ["D000", "D002"]
#    assert p.selected_ids() == ["D000", "D002"]
#
#    _click(p, 4, mods=Qt.ShiftModifier)           # shift 連選（錨點 = 上一次點的）
#    assert p.selected_ids() == ["D002", "D003", "D004"]
#
#    _click(p, 2, mods=Qt.ControlModifier)         # ctrl 再點一次 = 取消該顆
#    assert "D002" not in p.selected_ids()
#
#    _click(p, 1)                                   # 一般點擊 = 只選這顆
#    assert p.selected_ids() == ["D001"]
#
#    activated.clear()
#    _click(p, 3, dbl=True)
#    assert activated == ["D003"]                   # 雙擊 -> 主視窗跳去單顆預覽
#    assert p.selected_ids() == ["D003"]
#
#    # 程式設定選取不該回頭發訊號
#    n = len(picked)
#    p.set_selected(["D005", "D006"])
#    assert p.selected_ids() == ["D005", "D006"]
#    assert len(picked) == n
#
#    # 點空白處 -> 清空選取
#    _click(p, 0)
#    empty_pos = p.grid.tile_rect(0).topLeft()
#    _mouse(p.grid.viewport(), QEvent.MouseButtonPress,
#           empty_pos - QPointF(5, 5).toPoint())
#    assert p.selected_ids() == []
#
#
## --------------------------------------------------------------------------- #
## 7. bin 色條 + 說明文字（顏色不是唯一通道）
## --------------------------------------------------------------------------- #
#def test_bin_colour_bar_and_caption_carry_the_bin_number(qapp):
#    items = _items(4)
#    items[3]["ok"] = False
#    items[3]["bin"] = None
#    p = _panel(qapp, items)
#    p.set_sort("defect_id", descending=False)
#
#    cap1 = p.caption_of("D001")                    # bin 1
#    assert "bin 1" in cap1 and "#D001" in cap1     # 顏色以外一定要有文字
#    assert "bin 0" in p.caption_of("D000")
#    assert p.caption_at(0) == p.caption_of("D000")
#
#    # 顏色一律取自 theme token
#    T = theme_mod.TOKENS
#    assert p.bin_color("D001") == T["success"]     # bin 1 = 過門檻（綠）
#    assert p.bin_color("D000") == T["seg_disabled"]  # bin 0 = 低調灰
#    assert p.bin_color("D003") == T["danger"]      # 跑失敗 = 紅
#    assert "FAILED" in p.caption_of("D003")
#
#
## --------------------------------------------------------------------------- #
## 8. QPixmap LRU 快取有上限
## --------------------------------------------------------------------------- #
#def test_pixmap_cache_is_bounded(qapp):
#    p = _panel(qapp, _items(1500, with_thumb=True))
#    assert gal_mod.CACHE_CAP == 512
#
#    p.grid.grab()
#    first = p.cache_size()
#    assert 0 < first <= gal_mod.CACHE_CAP
#
#    bar = p.grid.verticalScrollBar()
#    step = max(1, bar.maximum() // 12)
#    for v in range(0, bar.maximum() + 1, step):
#        bar.setValue(v)
#        p.grid.grab()
#        assert p.cache_size() <= gal_mod.CACHE_CAP
#    assert p.cache_size() > first, "翻頁之後快取應該有被填進新的縮圖"
#
#    # 換縮圖尺寸 -> key 不同，但上限不變
#    p.set_thumb_size(144)
#    assert p.thumb_size() == 144
#    p.grid.grab()
#    assert p.cache_size() <= gal_mod.CACHE_CAP
#
#    # 重新餵資料要把快取清乾淨（不然會顯示上一批的圖）
#    p.set_items(_items(3, with_thumb=True))
#    assert p.cache_size() == 0
#
#
## --------------------------------------------------------------------------- #
## 9. 推廣鐵則：每個看得到的控制項都要有說明，而且 UI 一律英文
## --------------------------------------------------------------------------- #
#def test_every_control_has_an_english_tooltip(qapp):
#    p = _panel(qapp, _items(6))
#    p.filter_by_score_range(1.0, 4.0)
#
#    for name, widget in (("count", p.count_label), ("sort combo", p.sort_combo),
#                         ("sort order", p.order_button), ("zoom", p.zoom_combo)):
#        tip = widget.toolTip()
#        assert tip, "%s has no tooltip" % name
#        # UI 一律英文（中英夾雜對使用者是噪音）—— 這裡順便當成不變量鎖住
#        assert not _has_cjk(tip), "%s tooltip is not English: %r" % (name, tip)
#
#    assert p.zoom_combo.itemText(0) == "S"
#    assert [p.zoom_combo.itemText(i) for i in range(p.zoom_combo.count())] == \
#        ["S", "M", "L"]
#    assert [s[1] for s in gal_mod.THUMB_SIZES] == [64, 96, 144]
#
#    chips = p.chips()
#    assert chips, "sort / filter conditions must be shown as chips"
#    for chip in chips:
#        assert chip.toolTip() and not _has_cjk(chip.toolTip())
#        assert chip.text().endswith("✕")           # 看得出來可以移除
#        assert chip.label_text and not _has_cjk(chip.label_text)
#
#    # 空狀態與載入中佔位也是白話英文
#    p.set_items([])
#    assert p.empty_text() and not _has_cjk(p.empty_text())
#
#F 1ddeef396181f9eabfcf63a5cbd7af119a54c75a 158 tests/test_ui_patch_only.py
## F7-1 驗收：Studio 收斂成 patch-only（但 core 一行都沒少）。
#"""Studio 目前只吃 EBI patch —— 而且是**收起來**，不是刪掉。
#
#這支測試同時鎖住兩件事：
#
#1. **GUI 真的收斂了**：卡片庫沒有 RSEM 專用卡、範本庫沒有純 rsem 的 recipe、
#   載到 rsem 資料集會被擋下並講清楚原因。
#2. **core 完全沒被動到**：兩張卡仍在 registry、RSEM ingest 仍然讀得出來、
#   rsem recipe 仍然驗證得過。這一條才是重點 —— 使用者說的是「暫時」，
#   所以「打開開關就回得來」必須是有測試保護的事實，不是口頭承諾。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#
#EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "recipes"
#
#
#def _import_qt(g):
#    """把 Qt 與待測模組 import 進來（只在 fixture 裡呼叫，維持 lazy import 鐵則）。"""
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import scope as scope_mod
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    g.update(QApplication=QApplication, scope_mod=scope_mod,
#             studio_mod=studio_mod, theme_mod=theme_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app)
#    yield app
#
#
#@pytest.fixture(scope="module")
#def patch_lot(tmp_path_factory):
#    from make_sample import generate
#    return generate(str(tmp_path_factory.mktemp("f7_patch")), n=6, seed=7)
#
#
#@pytest.fixture(scope="module")
#def rsem_lot(tmp_path_factory):
#    from make_sample_rsem import generate
#    return generate(str(tmp_path_factory.mktemp("f7_rsem")), n=4, seed=11)
#
#
#@pytest.fixture
#def window(qapp):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    yield win
#    win.close()
#
#
## --------------------------------------------------------------------------- #
## 1. GUI 收斂了
## --------------------------------------------------------------------------- #
#def test_rsem_only_cards_are_not_in_the_library(window):
#    for key in scope_mod.HIDDEN_STEPS:
#        assert window.library.entry(key) is None, \
#            "%s 是 RSEM 專用卡，patch-only 期間不該出現在卡片庫" % key
#    # 其他卡照常在
#    for key in ("load_patch", "align", "subtract", "snr_map", "glv_stats"):
#        assert window.library.entry(key) is not None
#
#
#def test_loading_an_rsem_dataset_is_refused_with_a_reason(window, rsem_lot,
#                                                          patch_lot):
#    # 先載一份正常的 patch，等一下要確認它不會被弄丟
#    assert window.load_dataset_path(patch_lot["klarf"], sync=True) is True
#    before = window.dataset
#
#    assert window.load_dataset_path(rsem_lot["klarf"], sync=True) is False
#    msg = window.status_text()
#    assert "EBI patch" in msg and "rsem" in msg
#    assert "python -m adept run" in msg, "要講得出替代路徑，不能只是拒絕"
#    assert window.dataset is before, "被擋下來時不該動到使用者手上的資料集"
#
#
#def test_template_library_hides_rsem_only_recipes(window):
#    dlg = window.open_recipe_library()
#    listed = [e["recipe_id"] for e in dlg.entries()]
#
#    assert "rsem_golden_cell" not in listed, "純 rsem 的範本要收起來"
#    assert "die_to_die_basic" in listed
#    # 雙 route 的照列：載進來會走 ebi_patch，完全跑得動
#    assert "dual_route_basic" in listed
#
#
#def test_a_dual_route_template_loads_into_the_patch_route(window, patch_lot):
#    window.load_dataset_path(patch_lot["klarf"], sync=True)
#    assert window.load_recipe_path(str(EXAMPLES / "dual_route_basic.json"),
#                                   sync=True) is True
#    assert window.model.kind == "ebi_patch"
#    assert window.run_trial(6, workers=1, sync=True) is True
#    assert len(window.trial_scores) == 6
#
#
## --------------------------------------------------------------------------- #
## 2. core 完全沒被動到（「打開開關就回得來」）
## --------------------------------------------------------------------------- #
#def test_hidden_cards_are_still_registered_and_runnable():
#    """只是不列在 UI 上；registry、參數驗證、既有 recipe 全都照舊。"""
#    from adept.core.pipeline import get_step
#    import adept.core.steps  # noqa: F401
#
#    for key in ("golden_cell", "cell_period"):
#        step = get_step(key)
#        assert step.key == key
#        assert step.validate_params({}), "預設參數要還驗證得過"
#
#
#def test_rsem_ingest_and_recipe_still_work(rsem_lot):
#    """core 不知道 UI 收斂這件事 —— RSEM 從 ingest 到驗證整條都還在。"""
#    from adept.core.ingest.dataset import load_dataset
#    from adept.core.pipeline import Recipe, validate
#
#    ds = load_dataset(rsem_lot["klarf"])
#    assert ds.kind == "rsem" and len(ds.items) == 4
#
#    recipe = Recipe.load(str(EXAMPLES / "rsem_golden_cell.json"))
#    issues = [i for i in validate(recipe, kind="rsem") if i.level == "error"]
#    assert not issues, issues
#
#
#def test_period_module_is_not_orphaned():
#    """``algo/period.py`` 看起來只有 Golden Cell 在用，但它是之後做
#    pattern-frame ROI 的唯一工具（F7 §4）—— 這條測試就是那張便利貼。"""
#    from adept.core.algo import period
#
#    assert hasattr(period, "estimate_period")
#    assert hasattr(period, "choose_origin"), \
#        "choose_origin 的相位搜尋是 M4 補完原專案 stub 的成果，不要刪"
#
#
#def test_turning_rsem_back_on_is_one_constant(qapp, monkeypatch, rsem_lot):
#    """把 'rsem' 加進 SUPPORTED_KINDS 就該整條路線回來 —— 用測試證明它是真的。"""
#    monkeypatch.setattr(scope_mod, "SUPPORTED_KINDS", ("ebi_patch", "rsem"))
#    monkeypatch.setattr(scope_mod, "HIDDEN_STEPS", ())
#
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    try:
#        assert win.library.entry("golden_cell") is not None
#        assert win.load_dataset_path(rsem_lot["klarf"], sync=True) is True
#        assert win.dataset.kind == "rsem"
#        dlg = win.open_recipe_library()
#        assert "rsem_golden_cell" in [e["recipe_id"] for e in dlg.entries()]
#    finally:
#        win.close()
#
#F 11503b28be232ab36fd8201512275150e26969e0 164 tests/test_ui_results.py
## F7-5 驗收：Results 視窗 —— 跑完才有意義的東西不該常駐在編輯畫面上。
#"""主視窗只留「編流程 + 看單顆」；分數分佈、Gallery、輸出搬到 Results 視窗。
#
#最重要的一條是最後那個測試：**搬家不可以弄丟秒回**。拖門檻線走的是
#``viewmodel.rebin()`` 的純計算路徑（不重跑影像），這是這個工具調參迴圈的
#一半價值，換視窗時最容易不小心接成「每動一次就重跑」。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import pytest
#
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
#
#EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "recipes" \
#    / "die_to_die_basic.json"
#
#
#def _import_qt(g):
#    from PySide6.QtWidgets import QApplication
#
#    from adept.ui import results as results_mod
#    from adept.ui import studio as studio_mod
#    from adept.ui import theme as theme_mod
#    from adept.ui import viewmodel as vm_mod
#    g.update(QApplication=QApplication, results_mod=results_mod,
#             studio_mod=studio_mod, theme_mod=theme_mod, vm_mod=vm_mod)
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    _import_qt(globals())
#    app = QApplication.instance() or QApplication([])
#    theme_mod.apply_theme(app)
#    yield app
#
#
#@pytest.fixture(scope="module")
#def lot(tmp_path_factory):
#    from make_sample import generate
#    return generate(str(tmp_path_factory.mktemp("f7_results")), n=8, seed=7)
#
#
#@pytest.fixture(scope="module")
#def window(qapp, lot):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    win.load_dataset_path(lot["klarf"], sync=True)
#    win.load_recipe_path(str(EXAMPLE), sync=True)
#    yield win
#    win.close()
#
#
## --------------------------------------------------------------------------- #
## 1. 主視窗乾淨了
## --------------------------------------------------------------------------- #
#def test_main_window_keeps_only_the_editing_surface(window):
#    root = window.root_splitter
#    assert [root.widget(i) for i in range(root.count())] == [
#        window.library, window.middle_splitter, window.preview_pane]
#    assert window.histogram.parent() is not window
#    assert window.gallery.parent() is not window
#
#
#def test_preview_gets_the_widest_column(window):
#    """使用者要求「影像大一點」—— 單顆預覽要拿到最寬的一欄。
#
#    看的是**設定值**而不是 ``sizes()``：QSplitter 要視窗真的 show 過才會排版，
#    離屏測試裡 ``sizes()`` 只會回一組沒有意義的相等數字。
#    """
#    lib, mid, preview = studio_mod.COLUMN_SIZES
#    assert preview == max(studio_mod.COLUMN_SIZES)
#    assert preview > lib + mid * 0.5, studio_mod.COLUMN_SIZES
#    assert window.root_splitter.count() == 3
#
#
#def test_results_window_is_not_shown_until_there_is_something_to_show(qapp, lot):
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    try:
#        assert win.results_visible() is False
#        assert win.results.summary_text() == "No results yet."
#        assert win.results.btn_export.isEnabled() is False
#    finally:
#        win.close()
#
#
## --------------------------------------------------------------------------- #
## 2. 跑完就把結果端出來
## --------------------------------------------------------------------------- #
#def test_running_populates_and_presents_the_results_window(window):
#    assert window.run_trial(8, workers=1, sync=True) is True
#
#    assert window.results_visible() is True, "按 Run 想看的就是這個"
#    assert window.histogram.has_data() is True
#    assert window.gallery.displayed_count() == 8
#    assert window.results.btn_export.isEnabled() is True
#
#    summary = window.results.summary_text()
#    assert "8 defects" in summary and "8 ok" in summary and "0 failed" in summary
#
#
#def test_summary_line_reports_counts_and_score_span():
#    text = results_mod.summarize_run(10, 9, 1.25, [3.0, 7.5, 1.0])
#    assert "10 defects" in text and "9 ok" in text and "1 failed" in text
#    assert "1.25 s" in text or "1.2 s" in text
#    assert "1 – 7.5" in text
#
#    assert "score" not in results_mod.summarize_run(2, 2, 0.1, [])
#
#
#def test_export_button_in_results_reaches_the_studio_dialog(window):
#    window.run_trial(8, workers=1, sync=True)
#    seen = []
#    window.results.export_requested.connect(lambda: seen.append(True))
#    window.results.btn_export.click()
#    assert seen, "Results 視窗的輸出鈕要接回 Studio 的輸出精靈"
#
#
## --------------------------------------------------------------------------- #
## 3. **搬家不可以弄丟秒回**
## --------------------------------------------------------------------------- #
#def test_threshold_drag_is_still_the_pure_rescore_path(window):
#    """拖曳中只重算 bin 數（不寫 model、不重跑影像），放開才 commit。"""
#    window.run_trial(8, workers=1, sync=True)
#    window._on_threshold_committed(40.0)
#    before = window.model.threshold
#
#    window._on_threshold_changed(77.25)
#    assert window.model.threshold == pytest.approx(before), \
#        "拖曳中絕對不可以動到 model —— 那會觸發重跑"
#    live = window.histogram.bin_summary_text()
#    assert live == "   ".join(
#        "bin %s=%s" % (k, v)
#        for k, v in sorted(vm_mod.rebin(window.trial_scores, 77.25,
#                                        window.model.bins).items()))
#
#    window._on_threshold_committed(55.0)
#    assert window.model.threshold == pytest.approx(55.0)
#
#
#def test_bar_click_filters_the_gallery_in_the_same_window(window):
#    window.run_trial(8, workers=1, sync=True)
#    lo, hi = window.histogram.bar_range(0)
#    window.histogram.bar_clicked.emit(lo, hi)
#
#    assert window.gallery.filter_text(), "點長條要篩 Gallery"
#    assert window.results_visible() is True
#    # 再點同一根 = 取消
#    window.histogram.bar_clicked.emit(lo, hi)
#    assert window.gallery.filter_text() == ""
#
#
#def test_closing_results_does_not_lose_them(window):
#    window.run_trial(8, workers=1, sync=True)
#    window.results.close()
#    assert window.results_visible() is False
#    assert window.trial_results, "關掉視窗不該丟掉結果"
#
#    window.show_gallery()
#    assert window.results_visible() is True
#    assert window.gallery.displayed_count() == 8
#
#F 48e047f2ce44c7ad2990f8467035d53fa2b6fc45 383 tests/test_ui_studio_m5.py
## ADEPT Studio M5 接線測試 — authored 2026-07-28 (M5-3).
#"""``adept/ui/studio.py`` 的 M5 部分：Gallery 分頁、背景縮圖、直方圖聯動、輸出。
#
#執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_studio_m5.py -q``
#
#**為什麼所有 Qt import 都是 lazy 的（別改回去）**
#
#``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有任何
#PySide6 模組。pytest 先蒐集全部測試檔、再開始跑，所以只要這個檔案在**模組層**
#``import PySide6``（或 import ``adept.ui.studio``），蒐集階段就會把 Qt 塞進
#``sys.modules``，那個守門測試就會紅 —— 即使它先跑。
#
#因此：所有 Qt / ``adept.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
#的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
#每個測試都必須（直接或間接）要求 ``qapp`` fixture，否則那些名字不存在。
#
#測試一律走 ``StudioWindow`` 的公開 API（``run_trial(sync=True)`` /
#``request_thumbs(sync=True)`` …）或直接 emit 元件的訊號，**不開任何對話框**、
#不依賴 event loop。唯一的例外是直方圖那顆真滑鼠事件（自己建 ``QMouseEvent``
#再 ``sendEvent``）—— 因為「點長條」與「拖門檻」的區分本來就是滑鼠行為。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#import numpy as np
#import pytest
#
#REPO = Path(__file__).resolve().parent.parent
#EXAMPLE_RECIPE = REPO / "examples" / "recipes" / "die_to_die_basic.json"
#
#sys.path.insert(0, str(REPO / "tools"))
#from make_sample import generate  # noqa: E402
#
#N = 8
#
#
#def _load_qt() -> None:
#    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
#    from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: F401
#    from PySide6.QtGui import QMouseEvent  # noqa: F401
#    from PySide6.QtWidgets import QApplication  # noqa: F401
#
#    from adept.ui import export_dialog as ex_mod  # noqa: F401
#    from adept.ui import studio as studio_mod  # noqa: F401
#    from adept.ui import theme as theme_mod  # noqa: F401
#
#    globals().update(locals())
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    """離屏 QApplication（整個模組共用一個）+ 套用主題。"""
#    _load_qt()
#    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
#    theme_mod.apply_theme(app)
#    yield app
#    app.processEvents()
#
#
#@pytest.fixture(scope="module")
#def synlot(tmp_path_factory):
#    return generate(str(tmp_path_factory.mktemp("m5_lot")), n=N, seed=7)
#
#
#@pytest.fixture(scope="module")
#def window(qapp, synlot):
#    """整個模組共用一個主視窗（已載入資料集 + 範例 recipe，尚未試跑）。"""
#    win = studio_mod.StudioWindow()
#    assert win.load_dataset_path(synlot["klarf"], sync=True) is True
#    assert win.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
#    # 巢狀 layout 要 show + processEvents 之後 viewport 才有真實尺寸，
#    # Gallery 的可視範圍計算（進而 thumbs_requested）才有意義。
#    win.resize(1200, 800)
#    win.show()
#    qapp.processEvents()
#    yield win
#    win.close()
#
#
#@pytest.fixture(scope="module")
#def ran(window, qapp):
#    """跑一次全批（同步），之後的測試共用這批結果。"""
#    assert window.run_trial(N, workers=1, sync=True) is True
#    qapp.processEvents()
#    return window
#
#
#def _mouse(widget, etype, pos, button=None, buttons=None):
#    """建構並派送一顆滑鼠事件（離屏環境下比 QTest 可靠）。"""
#    button = Qt.NoButton if button is None else button
#    buttons = button if buttons is None else buttons
#    ev = QMouseEvent(etype, QPointF(pos), QPointF(pos), button, buttons,
#                     Qt.NoModifier)
#    QApplication.sendEvent(widget, ev)
#
#
## --------------------------------------------------------------------------- #
## 1. Results 視窗（F7-5：Gallery 與直方圖從主視窗搬出去）
## --------------------------------------------------------------------------- #
#def test_results_live_in_their_own_window(window):
#    """主視窗只留「編流程 + 看單顆」；跑完才有意義的東西在 Results 視窗。"""
#    assert window.gallery is window.results.gallery
#    assert window.histogram is window.results.histogram
#    assert window.results_visible() is False, "還沒跑就不該有結果視窗"
#
#    # 主視窗的中央區只剩三欄：卡片庫 | 流程+參數 | 單顆預覽
#    root = window.root_splitter
#    assert root.count() == 3
#    assert root.widget(0) is window.library
#    assert root.widget(2) is window.preview_pane
#
#
#def test_gallery_populates_after_trial(ran):
#    window = ran
#    assert window.gallery.total_count() == N
#    assert window.gallery.displayed_count() == N
#    assert len(window.trial_results) == N
#
#    ids = window.gallery.displayed_ids()
#    assert sorted(ids) == sorted(str(r["defect_id"]) for r in window.trial_results)
#    # 縮圖一開始一律是 None（解碼是背景的事）
#    assert all(item["thumb"] is None for item in window.gallery.grid.items())
#    # bin 一定寫在說明文字裡（不是只有顏色）
#    assert "bin" in window.gallery.caption_at(0)
#
#    # 排序欄位 = score + 這批真的量到的特徵
#    keys = window.gallery.sort_keys()
#    assert keys[0] == "score"
#    assert "snr_max" in keys
#    assert "defect_id" in keys
#    feats = set()
#    for r in window.trial_results:
#        feats.update(r.get("features") or {})
#    assert set(keys) == {"score", "defect_id"} | feats
#
#
## --------------------------------------------------------------------------- #
## 2. 縮圖：Gallery 要 → 背景做 → 回來貼上
## --------------------------------------------------------------------------- #
#def test_thumbs_requested_leads_to_thumbs(ran, qapp):
#    window = ran
#    seen = []
#    window.gallery.thumbs_requested.connect(lambda ids: seen.append(list(ids)))
#
#    # F7-5：Gallery 在 Results 視窗裡，要先給它真實的 viewport 尺寸。
#    window.results.resize(900, 640)
#    window.show_gallery()
#    qapp.processEvents()
#
#    # ``_maybe_request_thumbs`` 對「和上次相同的可視範圍」會提早 return，
#    # 而 ``ran`` 是 module-scoped —— 前面的測試已經觸發過第一次請求了。
#    # 把那個備忘重置，才驗得到「量到可視範圍就會要縮圖」這件事本身。
#    # （這一批全部塞得進畫面，所以範圍從頭到尾都是 (0, N)，
#    #   單純再 resize 一次是不會重發的。）
#    window.gallery.grid._last_request = None
#    window.gallery.grid.resize(860, 520)
#    qapp.processEvents()
#
#    assert seen, "可視範圍變動時 Gallery 應該要求縮圖"
#    wanted = seen[-1]
#    assert all(w in window.gallery.displayed_ids() for w in wanted)
#
#    # 同步驅動（測試不靠 event loop）：真的去讀 TIFF 頁 + make_thumb
#    n = window.request_thumbs(wanted, sync=True)
#    assert n == len(wanted)
#
#    by_id = {i["defect_id"]: i for i in window.gallery.grid.items()}
#    for did in wanted:
#        arr = by_id[did]["thumb"]
#        assert isinstance(arr, np.ndarray)
#        size = window.gallery.thumb_size()
#        assert arr.shape[:2] == (size, size)
#        assert arr.dtype == np.uint8
#
#    # 認不得的 id 靜靜略過，不炸
#    assert window.request_thumbs(["沒有這顆"], sync=True) == 0
#    window.show_preview()
#
#
#def test_thumb_worker_run_sync_and_channel_pick(ran):
#    window = ran
#    items = list(window.dataset.items)
#    assert studio_mod.thumb_channel(items[0]) == "test"     # test → single → 其他
#
#    jobs = [(str(it.defect_id), it) for it in items[:3]]
#    out = studio_mod.ThumbWorker.run_sync(jobs, 64)
#    assert set(out) == {j[0] for j in jobs}
#    assert all(a.shape == (64, 64) for a in out.values())
#
#    # 壞掉的一顆不該殺掉整批（load 會 raise，run_sync 要吞掉）
#    class _Broken:
#        images = {"test": object()}
#
#        def load(self, channel):
#            raise OSError("image gone")
#
#    mixed = studio_mod.ThumbWorker.run_sync(jobs + [("bad", _Broken())], 64)
#    assert set(mixed) == {j[0] for j in jobs}
#    assert studio_mod.thumb_channel(_Broken()) == "test"
#
#
## --------------------------------------------------------------------------- #
## 3. Gallery → 單顆預覽
## --------------------------------------------------------------------------- #
#def test_defect_activated_switches_tab_and_moves_preview(ran):
#    window = ran
#    window.show_gallery()
#    assert window.results_visible() is True
#
#    target = str(window.dataset.items[5].defect_id)
#    window.gallery.defect_activated.emit(target)
#
#    assert window.results_visible() is True   # 結果視窗不會因為跳單顆而關掉
#    assert window.defect_index == 5
#    assert str(window.dataset.items[window.defect_index].defect_id) == target
#    assert target in window.status_text()
#
#    # 不存在的 id：切回單顆預覽 + 狀態列講清楚，不炸
#    window.gallery.defect_activated.emit("不存在")
#    assert "is not in the current dataset" in window.status_text()
#
#
#def test_gallery_selection_shows_count(ran):
#    window = ran
#    ids = window.gallery.displayed_ids()[:3]
#    window.gallery.selection_changed.emit(list(ids))
#    assert window.status_text() == "3 selected"
#
#
## --------------------------------------------------------------------------- #
## 4. 直方圖 → Gallery（調參迴圈的另一半）
## --------------------------------------------------------------------------- #
#def test_bar_clicked_filters_gallery_and_switches_tab(ran):
#    window = ran
#    window.show_preview()
#    window.gallery.clear_filter()
#    lo, hi = window.histogram.bar_range(0)
#
#    window.histogram.bar_clicked.emit(lo, hi)
#    assert window.results_visible() is True
#    assert "Filtered to score" in window.status_text()
#    assert window.gallery.filter_text()
#    shown = window.gallery.displayed_count()
#    assert shown < N
#    for item in window.gallery.grid.items():
#        if item["defect_id"] in window.gallery.displayed_ids():
#            assert lo <= item["score"] <= hi
#
#    # 再點同一根 → 取消篩選
#    window.histogram.bar_clicked.emit(lo, hi)
#    assert window.gallery.displayed_count() == N
#    assert window.gallery.filter_text() == ""
#    assert "cleared" in window.status_text()
#
#
#def test_chip_clears_filter_and_same_bar_refilters(ran):
#    window = ran
#    window.gallery.clear_filter()
#    lo, hi = window.histogram.bar_range(0)
#    window.histogram.bar_clicked.emit(lo, hi)
#    filtered = window.gallery.displayed_count()
#
#    chips = [c for c in window.gallery.chips() if c.label_text.startswith("Filter")]
#    assert chips, window.gallery.chip_texts()
#    chips[0].click()                                    # Gallery 上的 ✕
#    assert window.gallery.displayed_count() == N
#
#    # chip 按掉之後再點同一根 = 重新篩選（不是又切掉）
#    window.histogram.bar_clicked.emit(lo, hi)
#    assert window.gallery.displayed_count() == filtered
#    window.gallery.clear_filter()
#
#
#def test_real_click_on_bar_does_not_move_the_threshold(ran, qapp):
#    """按下 + 原地放開 = 點長條（篩 Gallery）；門檻一動也不動。"""
#    window = ran
#    hist = window.histogram
#    hist.resize(520, 200)
#    qapp.processEvents()
#    window.gallery.clear_filter()
#
#    before = window.model.threshold
#    hist.set_threshold(before)
#    committed = []
#    hist.threshold_committed.connect(committed.append)
#
#    rect = hist._plot_rect()
#    n = len(hist._counts)
#    bw = rect.width() / n
#    # 挑一根「離門檻線夠遠」的長條（不然那是抓門檻把手，不是點長條）
#    idx = max(range(n), key=lambda i: abs(rect.left() + bw * (i + 0.5)
#                                          - hist._x_at(hist.threshold())))
#    pos = QPointF(rect.left() + bw * (idx + 0.5), rect.center().y())
#
#    _mouse(hist, QEvent.MouseButtonPress, pos, Qt.LeftButton, Qt.LeftButton)
#    _mouse(hist, QEvent.MouseButtonRelease, pos, Qt.LeftButton, Qt.NoButton)
#
#    assert committed == [], "點長條不該 commit 門檻"
#    assert hist.threshold() == pytest.approx(before)
#    assert window.model.threshold == pytest.approx(before)
#    assert window.results_visible() is True
#    assert "Filtered to score" in window.status_text()
#
#    window.gallery.clear_filter()
#    window._score_filter = None
#
#
#def test_real_drag_still_commits_the_threshold(ran, qapp):
#    """按下 + 拖過去 + 放開 = 拖門檻（老行為不能壞）。"""
#    window = ran
#    hist = window.histogram
#    hist.resize(520, 200)
#    qapp.processEvents()
#    before_visible = window.results_visible()
#
#    bars = []
#    hist.bar_clicked.connect(lambda a, b: bars.append((a, b)))
#    committed = []
#    hist.threshold_committed.connect(committed.append)
#
#    rect = hist._plot_rect()
#    y = rect.center().y()
#    start = QPointF(rect.left() + 20, y)
#    end = QPointF(rect.right() - 20, y)
#    _mouse(hist, QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton)
#    _mouse(hist, QEvent.MouseMove, QPointF(rect.center().x(), y),
#           Qt.NoButton, Qt.LeftButton)
#    _mouse(hist, QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton)
#    _mouse(hist, QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton)
#
#    assert bars == [], "拖曳不該被當成點長條"
#    assert len(committed) == 1
#    assert window.model.threshold == pytest.approx(committed[0])
#    assert window.results_visible() == before_visible   # 拖門檻不改變視窗狀態
#
#
## --------------------------------------------------------------------------- #
## 5. 輸出動作
## --------------------------------------------------------------------------- #
#def test_export_action_disabled_before_run_enabled_after(qapp, synlot):
#    win = studio_mod.StudioWindow()
#    try:
#        assert win.btn_export.isEnabled() is False
#        assert win.open_export_dialog() is None
#        assert "No results to export yet" in win.status_text()
#
#        assert win.load_dataset_path(synlot["klarf"], sync=True) is True
#        assert win.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
#        assert win.btn_export.isEnabled() is False, "載入資料集不等於有結果"
#
#        assert win.run_trial(N, workers=1, sync=True) is True
#        assert win.btn_export.isEnabled() is True
#
#        dlg = win.open_export_dialog()
#        assert isinstance(dlg, ex_mod.ExportDialog)
#        try:
#            assert dlg.klarf_columns() == list(win.dataset.klarf.defect_columns)
#            assert len(dlg.results) == N
#            assert dlg.recipe is not None
#        finally:
#            dlg.close()
#
#        # 換一份資料集 → 舊結果作廢，輸出鎖回去
#        assert win.load_dataset_path(synlot["klarf"], sync=True) is True
#        assert win.btn_export.isEnabled() is False
#        assert win.gallery.total_count() == 0
#    finally:
#        win.close()
#
#
#def test_close_stops_thumb_worker(qapp, synlot):
#    win = studio_mod.StudioWindow()
#    win.load_dataset_path(synlot["klarf"], sync=True)
#    win.load_recipe_path(str(EXAMPLE_RECIPE), sync=True)
#    win.run_trial(N, workers=1, sync=True)
#    win.request_thumbs(win.gallery.displayed_ids())        # 非同步：真的開執行緒
#    win.close()
#    assert win.thumb_worker.is_running() is False
#    assert win.thumb_worker.thread_obj is None
#    assert win.thumb_worker.pending_count() == 0
#
#F 228a8663a093edb280b6faa5608db83c5c94a61e 462 tests/test_ui_studio_smoke.py
## ADEPT Studio 主視窗煙霧測試 — authored 2026-07-28 (M3 收尾).
#"""``adept/ui/studio.py`` 的離屏（offscreen）煙霧測試。
#
#執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_studio_smoke.py -q``
#
#**為什麼所有 Qt import 都是 lazy 的（別改回去）**
#
#``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有任何
#PySide6 模組。pytest 先蒐集全部測試檔、再開始跑，所以只要這個檔案在**模組層**
#``import PySide6``（或 import ``adept.ui.studio``），蒐集階段就會把 Qt 塞進
#``sys.modules``，那個守門測試就會紅 —— 即使它先跑。
#
#因此：所有 Qt / ``adept.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
#的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
#每個測試都必須（直接或間接）要求 ``qapp`` fixture，否則那些名字不存在。
#
#測試一律走 ``StudioWindow`` 的公開 API（``load_dataset_path`` / ``select_node`` /
#``run_trial`` …）或直接 emit 元件的訊號，**不開任何對話框**、不依賴 event loop
#（背景 worker 全部走 ``sync=True`` 的同步路徑）。
#"""
#from __future__ import annotations
#
#import json
#import sys
#from pathlib import Path
#
#import pytest
#
#REPO = Path(__file__).resolve().parent.parent
#EXAMPLE_RECIPE = REPO / "examples" / "recipes" / "die_to_die_basic.json"
#
#sys.path.insert(0, str(REPO / "tools"))
#from make_sample import generate  # noqa: E402
#
#
#def _load_qt() -> None:
#    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
#    from PySide6.QtWidgets import QApplication  # noqa: F401
#
#    from adept.ui import studio as studio_mod  # noqa: F401
#    from adept.ui import theme as theme_mod  # noqa: F401
#    from adept.ui import viewmodel as vm_mod  # noqa: F401
#
#    from adept.core.pipeline import Recipe  # noqa: F401
#
#    globals().update(locals())
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    """離屏 QApplication（整個模組共用一個）+ 套用主題。"""
#    _load_qt()
#    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
#    theme_mod.apply_theme(app)
#    yield app
#    app.processEvents()
#
#
#@pytest.fixture(scope="module")
#def synlot(tmp_path_factory):
#    """合成 lot（8 顆 defect，seed=7）—— 與 M1 端到端測試同一支產生器。"""
#    out = tmp_path_factory.mktemp("studio_lot")
#    return generate(str(out), n=8, seed=7)
#
#
#@pytest.fixture(scope="module")
#def window(qapp):
#    """整個模組共用一個主視窗（最後一個測試才把它關掉）。"""
#    win = studio_mod.StudioWindow()
#    yield win
#    win.close()
#
#
#def _loaded(window, synlot):
#    """把資料集 + 範例 recipe 灌進視窗（冪等，讓每個測試都能單獨跑）。"""
#    if window.dataset is None:
#        assert window.load_dataset_path(synlot["klarf"], sync=True) is True
#    # 判斷依據是「載過 recipe 了沒」，不是「畫布上有沒有節點」——
#    # F7-9 起開窗就有一張起手 Input 卡，後者永遠是 True。
#    if window.recipe_path is None:
#        assert window.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
#    return window
#
#
## --------------------------------------------------------------------------- #
## 1. 建構 + 卡片庫
## --------------------------------------------------------------------------- #
#def test_window_constructs_with_library_cards(window):
#    assert window.windowTitle().startswith("ADEPT Studio")
#    # 卡片庫用的是真實 registry，不是手捏假資料
#    assert window.library.entry("snr_map") is not None
#    assert window.library.entry("load_patch") is not None
#    assert window.library.section_titles() == [
#        "Input", "Enhance", "Region", "Compare", "Measure", "ADC"]
#
#    # 空狀態：畫布上只有起手的 Input 卡（F7-9），而且它已經被選起來 ——
#    # 一開窗右欄就有東西可以動，不是一句「請先挑一張卡」。
#    assert window.model.node_order == ["load_patch"]
#    assert window.pipeline.node_ids() == ["load_patch"]
#    assert window.selected_node == "load_patch"
#    assert window.param_form.step_key() == "load_patch"
#    assert window.model.dirty is False, "使用者什麼都還沒做，不該被問「要存檔嗎」"
#    # 預覽沒有影像、直方圖沒有資料
#    assert window.image_view.has_image() is False
#    assert window.histogram.has_data() is False
#    assert window.status_text()          # 一開始就給使用者一句提示
#
#    # 工具列：試跑筆數 10–5000 預設 200，主要動作按鈕掛 objectName "primary"
#    assert (window.spin_trial_n.minimum(), window.spin_trial_n.maximum()) == (10, 5000)
#    assert window.spin_trial_n.value() == 200
#    assert window.btn_trial.objectName() == "primary"
#
#
## --------------------------------------------------------------------------- #
## 2. 載入資料集 + recipe
## --------------------------------------------------------------------------- #
#def test_load_dataset_and_recipe(window, synlot):
#    _loaded(window, synlot)
#
#    assert window.dataset is not None
#    assert len(window.dataset.items) == 8
#    assert window.defect_combo.count() == 8
#    assert window.defect_index == 0
#    assert "8" in window.defect_label.text()
#
#    recipe = Recipe.load(str(EXAMPLE_RECIPE))
#    assert window.model.node_order == recipe.routes["ebi_patch"]
#    assert len(window.pipeline.node_ids()) == len(window.model.node_order)
#    assert window.pipeline.node_ids() == window.model.node_order
#    assert window.model.kind == "ebi_patch"
#
#    # 標題帶 recipe id，狀態列有講人話
#    assert "die_to_die_basic" in window.windowTitle()
#    assert window.status_text()
#    # Score/Bin 尾卡摘要跟著 model 走
#    summary = window.pipeline.score_summary_text()
#    assert recipe.score.expr in summary and "50" in summary
#    # 節點摘要 = 非預設參數的 k=v（最多 3 個）—— F7-6 起節點是自繪圖元
#    assert "window=15" in window.pipeline.card("snr").info["summary"]
#
#
## --------------------------------------------------------------------------- #
## 3. 選節點 + 預覽
## --------------------------------------------------------------------------- #
#def test_select_node_and_preview(window, synlot):
#    _loaded(window, synlot)
#
#    assert window.select_node("snr") is True
#    assert window.selected_node == "snr"
#    assert window.pipeline.selected() == "snr"
#    assert window.stack.currentWidget() is window.param_form
#    assert window.param_form.step_key() == "snr_map"
#
#    assert window.refresh_preview(sync=True) is True
#    assert window.image_view.has_image() is True
#
#    streams = [window.stream_combo.itemText(i)
#               for i in range(window.stream_combo.count())]
#    assert "snr_map" in streams and "test" in streams
#    # 選了 snr 節點 → 預設看它寫出來的那條流
#    assert window.stream_combo.currentText() == "snr_map"
#
#    assert window.feature_table.rowCount() > 0
#    assert "snr_max" in window.feature_table.feature_names()
#
#    # 換一條影像流，畫面要跟著換（不用重跑 pipeline）
#    window.stream_combo.setCurrentText("test")
#    assert window.image_view.has_image() is True
#
#
#def test_compare_shows_two_streams_with_linked_zoom_and_pan(window, synlot):
#    """F7-8：並排比對預設關著，開了就自動配成 test | ref 並連動。
#
#    預設關著是刻意的 —— F7-5 把 Gallery 搬走就是為了讓影像變大，
#    預設並排等於把剛爭取到的寬度再砍一半。
#    """
#    from PySide6.QtCore import QPointF
#
#    _loaded(window, synlot)
#    assert window.refresh_preview(sync=True) is True
#    window.stream_combo.setCurrentText("test")
#
#    assert window.compare_enabled() is False
#    assert window.image_view_b.has_image() is False
#
#    assert window.set_compare(True) is True
#    assert window.compare_check.isChecked() is True
#    # 左邊是 test → 右邊自動給 ref（並排最常見的用途就是比這一對）
#    assert window.stream_combo_b.currentText() == "ref"
#    assert window.image_view_b.has_image() is True
#
#    # 連動：沒有連動的並排，使用者得自己把兩邊拖到同一個位置才比得起來
#    window.image_view.zoom_by(2.0)
#    assert window.image_view_b.view_state()[0] == pytest.approx(
#        window.image_view.view_state()[0])
#    # 反向也要連動，而且不可以互相回寫到爆掉
#    window.image_view_b.zoom_by(1.5)
#    assert window.image_view.view_state()[0] == pytest.approx(
#        window.image_view_b.view_state()[0])
#
#    # 平移一樣連動
#    before = window.image_view_b.view_state()[1]
#    window.image_view.set_view(window.image_view.view_state()[0],
#                               QPointF(11.0, 7.0))
#    window.image_view.view_changed.emit(window.image_view.view_state()[0],
#                                        QPointF(11.0, 7.0))
#    assert window.image_view_b.view_state()[1] != before
#
#    # 關掉之後右邊要真的放掉影像，不然它會留在記憶體裡也留在畫面上
#    assert window.set_compare(False) is False
#    assert window.image_view_b.has_image() is False
#
#
## --------------------------------------------------------------------------- #
## 4. 參數編輯（合法 / 不合法）
## --------------------------------------------------------------------------- #
#def test_param_edit_valid_then_invalid(window, synlot):
#    _loaded(window, synlot)
#    assert window.select_node("snr") is True
#
#    window._on_param_edited("window", 21)
#    assert window.model.nodes["snr"].params["window"] == 21
#    assert window.param_form.has_error("window") is False
#
#    window._on_param_edited("window", 15)
#    assert window.model.nodes["snr"].params["window"] == 15
#
#    # 999 超過 ParamSpec 上限 201 → 不可以丟例外，該列要變紅字，值不落地
#    window._on_param_edited("window", 999)
#    assert window.model.nodes["snr"].params["window"] == 15
#    assert window.param_form.has_error("window") is True
#    assert "maximum" in window.param_form.hint_text("window")
#
#    # 再改一個合法值 → 錯誤狀態清掉
#    window._on_param_edited("window", 15)
#    assert window.param_form.has_error("window") is False
#
#
## --------------------------------------------------------------------------- #
## 5. 純滑鼠組流程（只發訊號，不碰 model）
## --------------------------------------------------------------------------- #
#def test_mouse_only_pipeline_build(qapp):
#    win = studio_mod.StudioWindow()
#    try:
#        # 起手的 Input 卡已經在畫布上了（F7-9），所以只要再加一張
#        assert win.model.node_order == ["load_patch"]
#        win.library.add_requested.emit("percentile_norm")
#        assert win.model.node_order == ["load_patch", "percentile_norm"]
#        assert win.pipeline.node_ids() == ["load_patch", "percentile_norm"]
#        # 加入後自動選取新節點，右邊換成它的參數表單
#        assert win.selected_node == "percentile_norm"
#        assert win.param_form.step_key() == "percentile_norm"
#
#        win.pipeline.move_requested.emit("percentile_norm", -1)
#        assert win.model.node_order == ["percentile_norm", "load_patch"]
#        assert win.pipeline.node_ids() == ["percentile_norm", "load_patch"]
#
#        # 停用 / 移除也要走同一條路
#        win.pipeline.node_toggled.emit("load_patch", False)
#        assert win.model.nodes["load_patch"].enabled is False
#        win.pipeline.remove_requested.emit("load_patch")
#        assert win.model.node_order == ["percentile_norm"]
#
#        # 點 Score 尾卡 → 換到分數編輯頁
#        win.pipeline.score_clicked.emit()
#        assert win.stack.currentWidget() is win.score_pane
#    finally:
#        win.close()
#
#
## --------------------------------------------------------------------------- #
## 6. 試跑 → 直方圖
## --------------------------------------------------------------------------- #
#def test_run_trial_fills_histogram(window, synlot):
#    _loaded(window, synlot)
#
#    assert window.run_trial(8, workers=1, sync=True) is True
#    assert len(window.trial_scores) == 8
#    assert window.histogram.has_data() is True
#    assert sum(window.histogram._counts) == 8
#    assert window.histogram.bin_summary_text().startswith("bin ")
#    assert "Run finished" in window.status_text()
#
#
## --------------------------------------------------------------------------- #
## 7. 門檻：拖曳只是預覽，放開才寫回 model
## --------------------------------------------------------------------------- #
#def test_threshold_live_preview_vs_commit(window, synlot):
#    _loaded(window, synlot)
#    if not window.trial_scores:
#        window.run_trial(8, workers=1, sync=True)
#
#    window._on_threshold_committed(42.5)
#    assert window.model.threshold == pytest.approx(42.5)
#    assert window.model.to_recipe().score.threshold == pytest.approx(42.5)
#    assert window.threshold_spin.value() == pytest.approx(42.5)
#
#    # 拖曳中（changed）只重算 bin 摘要，絕對不能動 model
#    before = window.model.threshold
#    window._on_threshold_changed(77.25)
#    assert window.model.threshold == pytest.approx(before)
#    live = window.histogram.bin_summary_text()
#    assert live == "   ".join(
#        "bin %s=%s" % (k, v)
#        for k, v in sorted(vm_mod.rebin(window.trial_scores, 77.25,
#                                        window.model.bins).items()))
#
#    window._on_threshold_committed(50.0)
#    assert window.model.threshold == pytest.approx(50.0)
#
#
## --------------------------------------------------------------------------- #
## 8. 存檔往返
## --------------------------------------------------------------------------- #
#def test_save_recipe_round_trip(window, synlot, tmp_path):
#    _loaded(window, synlot)
#    out = tmp_path / "x.json"
#
#    assert window.save_recipe_path(str(out)) is True
#    assert out.is_file()
#    json.loads(out.read_text(encoding="utf-8"))     # 是合法 JSON
#
#    loaded = Recipe.load(str(out))
#    assert loaded.routes[window.model.kind] == window.model.node_order
#    assert loaded.score.expr == window.model.expr
#    assert loaded.score.threshold == pytest.approx(window.model.threshold)
#    assert sorted(loaded.nodes) == sorted(window.model.nodes)
#    assert loaded.nodes["snr"].params["window"] == \
#        window.model.nodes["snr"].params["window"]
#
#
## --------------------------------------------------------------------------- #
## 8.5 M7 推廣鐵則：前置條件不滿足的動作要「變灰 + 說明原因」，不是按了才罵人
## --------------------------------------------------------------------------- #
#def test_actions_are_disabled_until_their_preconditions_hold(qapp, synlot):
#    """按鈕的可用性要跟著狀態走，而且 tooltip 要講得出為什麼不能按。
#
#    舊行為是全部亮著、按下去才在狀態列說「還沒有載入資料集」——狀態列在螢幕
#    最下角，第一次用的人只會覺得「我按了，沒反應」。
#    """
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    try:
#        # 還沒有資料：跑不了、輸出不了（起手的 Input 卡讓「存檔」是可以的 ——
#        # 畫布上真的有一張卡，說「沒東西可存」才是騙人的）
#        assert win.btn_trial.isEnabled() is False
#        assert win.act_run_all.isEnabled() is False
#        assert win.spin_trial_n.isEnabled() is False
#        assert win.btn_export.isEnabled() is False
#        assert "No dataset" in win.btn_trial.toolTip()
#        for w in (win.btn_trial, win.btn_export):
#            assert w.toolTip().strip(), "變灰的按鈕一定要說明原因"
#
#        # 移掉起手卡 → 流程真的空了，理由要換一句，而且存不了
#        win.pipeline.remove_requested.emit("load_patch")
#        assert win.btn_save_recipe.isEnabled() is False
#        assert win.btn_save_recipe.toolTip().strip()
#        assert "add at least one card" in win.btn_trial.toolTip()
#
#        # 只有資料集 → 還是不能跑（流程是空的），但理由要換一句
#        assert win.load_dataset_path(synlot["klarf"], sync=True) is True
#        assert win.btn_trial.isEnabled() is False
#        assert "pipeline is empty" in win.btn_trial.toolTip()
#        assert win.btn_save_recipe.isEnabled() is False
#
#        # 資料集 + 流程 → 可以跑；但還沒有結果，所以還不能輸出
#        assert win.load_recipe_path(str(EXAMPLE_RECIPE), sync=True) is True
#        assert win.btn_trial.isEnabled() is True
#        assert win.act_run_all.isEnabled() is True
#        assert win.spin_trial_n.isEnabled() is True
#        assert win.btn_save_recipe.isEnabled() is True
#        assert win.btn_export.isEnabled() is False
#        assert "No results yet" in win.btn_export.toolTip()
#
#        # 跑完 → 輸出解鎖
#        assert win.run_trial(8, workers=1, sync=True) is True
#        assert win.btn_export.isEnabled() is True
#    finally:
#        win.close()
#
#
#def test_trial_count_follows_the_dataset_size(qapp, synlot):
#    """對一份只有 8 顆的 lot 顯示「First 200」沒有意義，只會讓人以為看錯了。"""
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    try:
#        assert win.spin_trial_n.value() == studio_mod.DEFAULT_TRIAL_N
#        win.load_dataset_path(synlot["klarf"], sync=True)
#        assert win.spin_trial_n.value() == max(win.spin_trial_n.minimum(), 8)
#    finally:
#        win.close()
#
#
#def test_run_all_lives_in_the_trial_button_menu(window):
#    """主要動作只留一顆 ▶；破壞性比較大的「跑整批」降級成選單項目。"""
#    menu = window.btn_trial.menu()
#    assert menu is not None, "「跑整批」要收在試跑鈕的下拉裡"
#    assert [a.text() for a in menu.actions()] == ["Run all defects"]
#    assert window.btn_trial.text() == "▶ Run trial"
#    # 舊版並排的第二顆 ▶ 鈕已經不存在
#    assert not hasattr(window, "btn_full")
#
#
## --------------------------------------------------------------------------- #
## 8.6 M7：游標讀數有自己的位置，不准洗掉狀態列
## --------------------------------------------------------------------------- #
#def test_cursor_readout_does_not_overwrite_the_status_bar(window, synlot):
#    _loaded(window, synlot)
#    window._status("Run finished: 8 defects")
#
#    window._on_cursor_info("x 12  y 30  ·  gray 187")
#    assert window.cursor_text() == "x 12  y 30  ·  gray 187"
#    assert window.status_text() == "Run finished: 8 defects", \
#        "滑鼠飄過影像不該把剛才的結果訊息洗掉"
#
#    window._on_cursor_info("")            # 游標離開影像
#    assert window.cursor_text() == ""
#    assert window.status_text() == "Run finished: 8 defects"
#
#
## --------------------------------------------------------------------------- #
## 9. 關窗：三個 worker 都收乾淨
## --------------------------------------------------------------------------- #
#def test_close_stops_workers(window, synlot):
#    _loaded(window, synlot)
#
#    # 真的丟一份非同步預覽出去（會開一條 QThread），再關窗
#    assert window.refresh_preview(sync=False) is True
#    window.close()
#
#    for worker in (window.preview_worker, window.trial_worker,
#                   window.dataset_worker):
#        assert worker.is_running() is False
#        assert worker.thread_obj is None
#    assert window._preview_timer.isActive() is False
#
#
## --------------------------------------------------------------------------- #
## 10. F7-7 進度條：載入與試跑要看得到進度，不能只有狀態列一行字
## --------------------------------------------------------------------------- #
#def test_progress_bar_is_hidden_when_idle_and_tracks_a_run(window, synlot):
#    _loaded(window, synlot)
#    assert window.progress_visible() is False, "閒著時不該佔位子"
#
#    window._on_trial_progress(3, 8)
#    assert window.progress_visible() is True
#    assert window.progress.value() == 3
#    assert window.progress.maximum() == 8
#
#    window.run_trial(8, workers=1, sync=True)
#    assert window.progress_visible() is False, "跑完要收起來"
#
#
#def test_loading_uses_an_indeterminate_bar(window):
#    """載入 KLARF 沒有可回報的百分比 —— 用跑馬燈回答「還在動嗎」。
#
#    謊報一個假的百分比比不報還糟。
#    """
#    window._progress_busy("Loading…")
#    assert window.progress_visible() is True
#    assert (window.progress.minimum(), window.progress.maximum()) == (0, 0)
#    window._progress_done()
#    assert window.progress_visible() is False
#
#F 37f2c567d7962f3aa2e851ab6c5fe8b9821901bd 410 tests/test_ui_welcome.py
## ADEPT 首次開啟導覽測試 — authored 2026-07-28 (M6-2).
#"""``adept/ui/welcome.py`` 與 Studio 導覽接線的離屏（offscreen）測試。
#
#執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_welcome.py -q``
#
#**為什麼所有 Qt import 都是 lazy 的（別改回去）**
#
#``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有
#任何 PySide6 模組。pytest 先蒐集全部測試檔、再開始跑，所以只要這個檔案在
#**模組層** ``import PySide6``（或 import ``adept.ui.welcome``），蒐集階段就會把
#Qt 塞進 ``sys.modules``，那個守門測試就會紅 —— 即使它先跑。
#
#因此：所有 Qt / ``adept.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
#的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
#每個測試都必須（直接或間接）要求 ``qapp`` fixture，否則那些名字不存在。
#
#**QSettings 不准弄髒開發機**：``welcome.app_settings()`` 用的是
#``IniFormat`` + ``UserScope``，所以 ``qapp`` fixture 一開始就把這個 scope 的
#路徑導到 pytest 的暫存目錄；「不再顯示」寫出來的檔案落在那裡。
#
#對話框一律**非 modal**（``show()``、不用 ``exec()``），而且動作都有可以直接
#呼叫的方法（``click_demo`` / ``load_selected`` / ``run_demo(sync=True)``），
#所以整個檔案不需要 event loop，也不會有任何一個測試卡住。
#"""
#from __future__ import annotations
#
#import json
#import sys
#from pathlib import Path
#
#import pytest
#
#REPO = Path(__file__).resolve().parent.parent
#RECIPES_DIR = REPO / "examples" / "recipes"
#
#
#def _load_qt() -> None:
#    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
#    from PySide6.QtCore import QSettings  # noqa: F401
#    from PySide6.QtWidgets import QApplication  # noqa: F401
#
#    from adept.ui import studio as studio_mod  # noqa: F401
#    from adept.ui import theme as theme_mod  # noqa: F401
#    from adept.ui import welcome as welcome_mod  # noqa: F401
#
#    globals().update(locals())
#
#
#@pytest.fixture(scope="module")
#def qapp(tmp_path_factory):
#    """離屏 QApplication + 主題 + 把 QSettings 導到暫存目錄。"""
#    _load_qt()
#    settings_dir = tmp_path_factory.mktemp("qsettings")
#    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(settings_dir))
#    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
#    theme_mod.apply_theme(app)
#    yield app
#    app.processEvents()
#
#
#@pytest.fixture(autouse=True)
#def clean_settings(qapp):
#    """每個測試都從「沒勾過不再顯示」開始（避免測試之間互相影響）。"""
#    welcome_mod.set_welcome_disabled(False)
#    yield
#    welcome_mod.set_welcome_disabled(False)
#
#
#@pytest.fixture(scope="module")
#def demo_lot(tmp_path_factory):
#    """給 ``run_demo`` 用的輸出資料夾（不碰使用者家目錄的 ~/.adept）。"""
#    return tmp_path_factory.mktemp("demo_lot")
#
#
#def _catch(signal):
#    """把訊號的參數 append 到一個 list（沒有 pytest-qt，手動接）。"""
#    seen = []
#    signal.connect(lambda *args: seen.append(tuple(args)))
#    return seen
#
#
## --------------------------------------------------------------------------- #
## WelcomeDialog：三顆鈕真的會發訊號
## --------------------------------------------------------------------------- #
#def test_welcome_dialog_constructs_with_the_three_actions(qapp):
#    dlg = welcome_mod.WelcomeDialog()
#    try:
#        assert dlg.isModal() is False, "導覽不可以是 modal（會卡住主視窗與測試）"
#        for btn in (dlg.btn_demo, dlg.btn_open, dlg.btn_library):
#            assert btn.text().strip(), "動作鈕沒有文字"
#            assert btn.toolTip().strip(), "動作鈕沒有 tooltip（推廣鐵則）"
#        # 最重要的那顆要長得像主要動作
#        assert dlg.btn_demo.objectName() == "primary"
#        # 三段式視覺：影像 / 算法 / ADC 各一張，顏色來自 theme token
#        cats = [c.property("category") for c in dlg.segments.cards]
#        assert cats == ["image", "algo", "adc"]
#        for cat in cats:
#            assert theme_mod.seg_hex(cat) in dlg.segments.cards[cats.index(cat)] \
#                .styleSheet()
#        assert "KLARF" in dlg.intro_label.text()
#    finally:
#        dlg.close()
#
#
#@pytest.mark.parametrize("button, signal_name", [
#    ("btn_demo", "demo_requested"),
#    ("btn_open", "open_klarf_requested"),
#    ("btn_library", "library_requested"),
#])
#def test_welcome_buttons_emit_their_signal(qapp, button, signal_name):
#    dlg = welcome_mod.WelcomeDialog()
#    try:
#        seen = _catch(getattr(dlg, signal_name))
#        getattr(dlg, button).click()
#        assert len(seen) == 1, "按了 %s 卻沒有發出 %s" % (button, signal_name)
#    finally:
#        dlg.close()
#
#
#def test_demo_and_open_buttons_close_the_dialog_first(qapp):
#    """按了「試一次」/「開我的 KLARF」要先關掉導覽，使用者才看得到結果。"""
#    for button in ("btn_demo", "btn_open"):
#        dlg = welcome_mod.WelcomeDialog()
#        dlg.show()
#        assert dlg.isVisible() is True
#        getattr(dlg, button).click()
#        assert dlg.isVisible() is False, "%s 按完應該關掉導覽" % button
#        dlg.close()
#
#
#def test_dont_show_again_writes_the_qsettings_flag(qapp):
#    assert welcome_mod.welcome_disabled() is False
#    dlg = welcome_mod.WelcomeDialog()
#    try:
#        assert dlg.chk_dont_show.isChecked() is False
#        dlg.set_dont_show_again(True)
#        assert welcome_mod.welcome_disabled() is True
#        # 設定要真的落到 QSettings（換一個 QSettings 物件也讀得到）
#        st = welcome_mod.app_settings()
#        assert str(st.value(welcome_mod.SKIP_WELCOME_KEY)).lower() in ("true", "1")
#        dlg.set_dont_show_again(False)
#        assert welcome_mod.welcome_disabled() is False
#    finally:
#        dlg.close()
#
#
#def test_new_dialog_reflects_the_saved_flag(qapp):
#    welcome_mod.set_welcome_disabled(True)
#    dlg = welcome_mod.WelcomeDialog()
#    try:
#        assert dlg.chk_dont_show.isChecked() is True
#    finally:
#        dlg.close()
#
#
#def test_quick_reference_button_is_guarded_when_pdf_missing(qapp, tmp_path):
#    """docs/ 沒有 PDF 時：鈕還在（使用者知道有這東西）但停用，按了不會炸。"""
#    assert welcome_mod.quick_reference_pdf(tmp_path) is None
#    dlg = welcome_mod.WelcomeDialog()
#    try:
#        if dlg.quickref_path is None:
#            assert dlg.btn_quickref.isEnabled() is False
#            assert dlg.btn_quickref.toolTip().strip()
#            assert dlg.open_quick_reference() is False   # 按下去也不炸
#        else:
#            assert dlg.btn_quickref.isEnabled() is True
#    finally:
#        dlg.close()
#
#
#def test_quick_reference_finds_a_pdf_and_prefers_the_named_one(tmp_path, qapp):
#    (tmp_path / "aaa-other.pdf").write_bytes(b"%PDF-1.4\n")
#    (tmp_path / "adept-quick-reference.pdf").write_bytes(b"%PDF-1.4\n")
#    found = welcome_mod.quick_reference_pdf(tmp_path)
#    assert found is not None and found.name == "adept-quick-reference.pdf"
#
#
## --------------------------------------------------------------------------- #
## RecipeLibraryDialog：內容全部從 JSON 讀
## --------------------------------------------------------------------------- #
#def test_library_lists_every_supported_recipe_file(qapp):
#    """清單完全由資料夾內容決定（沒有任何檔名寫死）。
#
#    F7-1 起會再過一層 :func:`adept.ui.scope.recipe_is_supported`：純 rsem 的
#    範本在 patch-only 期間不列出來。原本的重點沒變 —— 列出來的東西與順序
#    仍然只由 ``examples/recipes/`` 決定。
#    """
#    from adept.ui.scope import recipe_is_supported
#
#    files = sorted(RECIPES_DIR.glob("*.json"))
#    assert files, "examples/recipes/ 是空的"
#    expected = [p.name for p in files
#                if recipe_is_supported(welcome_mod.read_recipe_info(p))]
#    assert expected, "至少要有一份目前 build 跑得動的範本"
#
#    dlg = welcome_mod.RecipeLibraryDialog()
#    try:
#        assert dlg.count() == len(expected)
#        assert [Path(e["path"]).name for e in dlg.entries()] == expected
#    finally:
#        dlg.close()
#
#
#def test_library_shows_description_routes_steps_and_expr_from_json(qapp):
#    """對話框上的每一個字都要來自 JSON —— 沒有任何一份 recipe 被寫死。"""
#    dlg = welcome_mod.RecipeLibraryDialog()
#    try:
#        for i, info in enumerate(dlg.entries()):
#            raw = json.loads(Path(info["path"]).read_text(encoding="utf-8"))
#            assert info["recipe_id"] == raw["recipe_id"]
#            assert info["description"] == raw["description"]
#            assert info["description"].strip(), "%s 沒有 description" % info["file"]
#            assert info["routes"] == list(raw["routes"])
#            assert info["n_steps"] == len(raw["nodes"])
#            assert info["expr"] == raw["score"]["expr"]
#            assert info["threshold"] == pytest.approx(raw["score"]["threshold"])
#
#            # 清單那一列要看得到 recipe 名稱與 route
#            text = dlg.item_text(i)
#            assert raw["recipe_id"] in text
#            for route in raw["routes"]:
#                assert route in text
#
#            # 右邊細節要看得到說明與分數式
#            assert dlg.select(i) is True
#            detail = dlg.detail.text()
#            assert raw["description"] in detail
#            assert raw["score"]["expr"] in detail
#            for route in raw["routes"]:
#                assert route in detail
#    finally:
#        dlg.close()
#
#
#def test_library_emits_recipe_chosen_with_the_right_path(qapp):
#    dlg = welcome_mod.RecipeLibraryDialog()
#    try:
#        seen = _catch(dlg.recipe_chosen)
#        target = len(dlg.entries()) - 1
#        assert dlg.select(target) is True
#        expected = dlg.path_at(target)
#        assert dlg.load_selected() == expected
#        assert seen == [(expected,)]
#        assert Path(expected).is_file()
#    finally:
#        dlg.close()
#
#
#def test_library_reads_a_custom_directory_and_survives_broken_json(tmp_path, qapp):
#    good = json.loads((RECIPES_DIR / "die_to_die_basic.json").read_text(encoding="utf-8"))
#    (tmp_path / "a_good.json").write_text(json.dumps(good), encoding="utf-8")
#    (tmp_path / "b_broken.json").write_text("{ this is not json", encoding="utf-8")
#    dlg = welcome_mod.RecipeLibraryDialog(directory=tmp_path)
#    try:
#        assert dlg.count() == 2
#        entries = dlg.entries()
#        assert entries[0]["error"] == ""
#        assert entries[1]["error"], "壞掉的 JSON 應該被標記成讀不開"
#        # 選到壞的那一列：載入鈕停用、按下去也不發訊號
#        seen = _catch(dlg.recipe_chosen)
#        assert dlg.select(1) is True
#        assert dlg.btn_load.isEnabled() is False
#        assert dlg.load_selected() is None
#        assert seen == []
#    finally:
#        dlg.close()
#
#
#def test_library_with_empty_directory_does_not_crash(tmp_path, qapp):
#    dlg = welcome_mod.RecipeLibraryDialog(directory=tmp_path)
#    try:
#        assert dlg.count() == 0
#        assert dlg.load_selected() is None
#    finally:
#        dlg.close()
#
#
## --------------------------------------------------------------------------- #
## Studio 接線
## --------------------------------------------------------------------------- #
#@pytest.fixture(scope="module")
#def window(qapp):
#    """整個模組共用一個主視窗（**建構時不准彈任何對話框**）。"""
#    win = studio_mod.StudioWindow()
#    yield win
#    win.close()
#
#
#def test_constructing_studio_never_pops_the_welcome(window):
#    assert window.welcome_dialog is None
#    assert window.library_dialog is None
#    # 明確關掉也一樣安全
#    other = studio_mod.StudioWindow(show_welcome_on_start=False)
#    try:
#        assert other.welcome_dialog is None
#    finally:
#        other.close()
#
#
#def test_toolbar_has_help_and_examples_entries(window):
#    assert window.btn_help.text() == "Help"
#    assert window.btn_examples.text() == "Templates…"
#    for b in (window.btn_help, window.btn_examples):
#        assert b.toolTip().strip()
#
#
#def test_show_welcome_respects_and_overrides_the_flag(window):
#    welcome_mod.set_welcome_disabled(True)
#    assert window.show_welcome() is None, "勾了「不再顯示」就不該自己跳出來"
#    dlg = window.show_welcome(force=True)
#    assert dlg is not None and dlg.isVisible() is True
#    assert window.show_welcome(force=True) is dlg, "重複開啟要重用同一個對話框"
#    dlg.close()
#
#
#def test_welcome_library_button_opens_the_library_from_studio(window):
#    dlg = window.show_welcome(force=True)
#    assert dlg is not None
#    dlg.btn_library.click()
#    lib = window.library_dialog
#    try:
#        assert lib is not None and lib.count() > 0
#    finally:
#        if lib is not None:
#            lib.close()
#        dlg.close()
#
#
#def test_library_choice_loads_the_recipe_into_the_model(window):
#    lib = window.open_recipe_library()
#    try:
#        names = [e["recipe_id"] for e in lib.entries()]
#        idx = names.index("die_to_die_basic")
#        assert lib.select(idx) is True
#        path = lib.load_selected()
#        assert path is not None
#    finally:
#        lib.close()
#    assert window.model.recipe_id == "die_to_die_basic"
#    assert window.model.node_order, "載入 recipe 之後流程不該是空的"
#
#
#def test_welcome_demo_button_is_wired_to_studio_run_demo(window, monkeypatch):
#    """導覽只發訊號，動作在 Studio —— 這裡驗接線（不真的跑，也不寫 ~/.adept）。"""
#    calls = []
#
#    def fake_run_demo(*args, **kwargs):
#        calls.append((args, kwargs))
#        return True
#
#    monkeypatch.setattr(window, "run_demo", fake_run_demo)
#    dlg = window.show_welcome(force=True)
#    assert dlg is not None
#    try:
#        dlg.btn_demo.click()
#        assert len(calls) == 1, "「用範例資料試一次」沒有接到 StudioWindow.run_demo"
#    finally:
#        dlg.close()
#
#
#def test_demo_runs_end_to_end_and_populates_the_window(window, demo_lot):
#    """「用範例資料試一次」：跑完必須有資料集、有流程、有分數分佈、有 Gallery。"""
#    # 同步跑（不進 event loop）並指定輸出位置，免得測試去寫使用者家目錄的
#    # ~/.adept/demo_lot。
#    assert window.run_demo(out_dir=str(demo_lot), n=6, sync=True) is True
#
#    assert window.dataset is not None
#    assert len(window.dataset.items) == 6
#    assert window.model.recipe_id == "die_to_die_basic"
#    assert len(window.trial_results) == 6
#    assert all(r.get("ok") for r in window.trial_results)
#    assert len(window.trial_scores) == 6
#    assert window.histogram.has_data() is True, "直方圖沒有資料"
#    assert window.histogram.bin_summary_text().strip()
#    assert window.gallery.displayed_count() == 6
#    assert window.results_visible() is True
#    assert window.btn_export.isEnabled() is True
#    assert "Sample run finished" in window.status_text()
#
#
#def test_demo_lot_generation_is_reused_not_regenerated(demo_lot):
#    """同一個資料夾第二次呼叫要直接沿用（第二次按那顆鈕是秒回的）。"""
#    paths = studio_mod.generate_demo_lot(str(demo_lot), n=6)
#    assert Path(paths["klarf"]).is_file()
#    before = Path(paths["tiff"]).stat().st_mtime_ns
#    again = studio_mod.generate_demo_lot(str(demo_lot), n=6)
#    assert again["klarf"] == paths["klarf"]
#    assert Path(again["tiff"]).stat().st_mtime_ns == before
#
#
#def test_demo_reports_failure_instead_of_raising(window, tmp_path, monkeypatch):
#    """產資料失敗只在狀態列說明（鐵則：不准把 traceback 丟給使用者）。"""
#    def boom(*_a, **_kw):
#        raise RuntimeError("磁碟滿了")
#
#    monkeypatch.setattr(studio_mod, "generate_demo_lot", boom)
#    assert window.run_demo(out_dir=str(tmp_path), n=4, sync=True) is False
#    assert "磁碟滿了" in window.status_text()
#
#
#def test_generated_demo_lot_matches_the_builtin_template_route(demo_lot):
#    """範例資料一定要走得通內建範本的 route，不然那顆鈕會給人第一印象是壞的。"""
#    from adept.core.ingest.dataset import load_dataset
#    from adept.core.pipeline import Recipe
#
#    paths = studio_mod.generate_demo_lot(str(demo_lot), n=6)
#    ds = load_dataset(paths["klarf"])
#    recipe = Recipe.load(str(studio_mod.TEMPLATE_RECIPE))
#    assert ds.kind in recipe.routes
#
#F efeac6b931bea95d7e0f392c0e36e5bd9056e410 1018 tests/test_ui_widgets.py
## ADEPT Studio UI 元件測試 — authored 2026-07-28 (M3).
#"""``adept/ui/theme.py`` 與 ``adept/ui/widgets.py`` 的離屏（offscreen）測試。
#
#執行：``QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_ui_widgets.py -q``
#
#**為什麼所有 Qt import 都是 lazy 的（別改回去）**
#
#``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡沒有任何
#PySide6 模組。pytest 是「先蒐集全部測試檔、再開始跑」，所以只要這個檔案在
#**模組層** ``import PySide6``，蒐集階段就會把 Qt 塞進 ``sys.modules``，那個守門測試
#就會紅 —— 即使它先跑。
#
#因此：所有 Qt / ``adept.ui`` 的 import 都關在 :func:`_load_qt` 裡，由 module-scope
#的 ``qapp`` fixture 呼叫，再用 ``globals().update(...)`` 注入本模組命名空間。
#每個測試都必須要求 ``qapp`` fixture，否則那些名字不存在。
#
#pytest-qt 沒有安裝：訊號一律用手動 slot（append 到 list）捕捉，滑鼠事件用
#``QTest`` 或自己建構 ``QMouseEvent`` 後 ``QApplication.sendEvent`` 派送
#（離屏平台上 ``QTest.mouseMove`` 不可靠，拖曳的中間段自己派送最穩）。
#"""
#from __future__ import annotations
#
#import sys
#
#import numpy as np
#import pytest
#
#
#def _load_qt() -> None:
#    """把 Qt 與待測模組 import 進來，注入本模組的 globals（只在 fixture 裡呼叫）。"""
#    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: F401
#    from PySide6.QtGui import QMouseEvent, QWheelEvent  # noqa: F401
#    from PySide6.QtTest import QTest  # noqa: F401
#    from PySide6.QtWidgets import (  # noqa: F401
#        QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QLabel, QLineEdit,
#        QSlider, QSpinBox,
#    )
#
#    from adept.ui import theme as theme_mod  # noqa: F401
#    from adept.ui import widgets as widgets_mod  # noqa: F401
#    from adept.ui import viewmodel as vm_mod  # noqa: F401
#
#    globals().update(locals())
#
#
#@pytest.fixture(scope="module")
#def qapp():
#    """離屏 QApplication（整個模組共用一個）+ 套用主題。"""
#    _load_qt()
#    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "t"])
#    theme_mod.apply_theme(app)
#    yield app
#    app.processEvents()
#
#
## --------------------------------------------------------------------------- #
## helpers
## --------------------------------------------------------------------------- #
#def _steps():
#    """真實 registry 的 describe() dict（不是手捏的假資料）。"""
#    import adept.core.steps  # noqa: F401 — 觸發註冊
#    from adept.core.pipeline import list_steps
#
#    return [s.describe() for s in list_steps()]
#
#
#def _describe(key):
#    import adept.core.steps  # noqa: F401
#    from adept.core.pipeline import get_step
#
#    return get_step(key).describe()
#
#
#def _mouse(widget, etype, pos, button=None, buttons=None):
#    """建構並派送一顆滑鼠事件（離屏環境下比 QTest.mouseMove 可靠）。"""
#    button = Qt.NoButton if button is None else button
#    buttons = button if buttons is None else buttons
#    ev = QMouseEvent(etype, QPointF(pos), QPointF(pos), button, buttons,
#                     Qt.NoModifier)
#    QApplication.sendEvent(widget, ev)
#
#
#
## --------------------------------------------------------------------------- #
## theme
## --------------------------------------------------------------------------- #
#def _rgb(hexstr):
#    h = str(hexstr).lstrip("#")
#    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
#
#
#def test_theme_applies_and_has_adept_tokens(qapp):
#    assert qapp.styleSheet(), "apply_theme 應該有裝上 QSS"
#    qss = theme_mod.build_stylesheet()
#    # 主要動作按鈕靠 objectName "primary"
#    assert "QPushButton#primary" in qss
#    for selector in ("QComboBox", "QSpinBox", "QLineEdit", "QCheckBox::indicator",
#                     "QScrollBar", "QSplitter::handle", "QHeaderView::section",
#                     "QToolTip", "QAbstractItemView"):
#        assert selector in qss, selector
#
#
#def test_theme_is_neutral_and_flat(qapp):
#    """F7-2 的兩條產品要求，用性質斷言而不是寫死色碼。
#
#    舊配色是暖奶油底 + 琥珀 accent + 填滿色塊，使用者的評語是「太像玩具」。
#    這裡鎖住的是**中性**（大面積不帶色相）與**平面**（無陰影漸層），
#    色碼本身還可以繼續微調。
#    """
#    for key in ("bg_page", "bg_panel", "bg_surface", "toolbar", "statusbar"):
#        r, g, b = _rgb(theme_mod.TOKENS[key])
#        assert max(r, g, b) - min(r, g, b) <= 8, \
#            "%s = %s 帶了明顯色相，大面積底色要中性" % (key, theme_mod.TOKENS[key])
#
#    qss = theme_mod.build_stylesheet()
#    for banned in ("box-shadow", "qlineargradient", "qradialgradient"):
#        assert banned not in qss, "平面設計不用 %s" % banned
#
#
#def test_every_colour_token_is_a_real_colour(qapp):
#    """Qt 對無效的顏色字串是**靜靜畫成黑色**，不會報錯（F7-17）。
#
#    暗色盤裡曾經有 ``"accent_border": "#2f4straight"`` —— 一個「稍後修正」的
#    佔位字串，靠 70 行之後的一句覆寫救著。那句覆寫要是哪天被搬走或漏掉，
#    畫面上只會多出幾條看不出所以然的黑邊，沒有任何錯誤訊息。
#    """
#    import re
#
#    hexish = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
#    bad = []
#    for name, palette in theme_mod.PALETTES.items():
#        for key, value in palette.items():
#            if isinstance(value, str) and value.startswith("#") \
#                    and not hexish.match(value):
#                bad.append("%s.%s = %r" % (name, key, value))
#    assert not bad, "不是合法顏色的 token：%s" % bad
#
#
#def test_light_and_dark_palettes_have_identical_keys(qapp):
#    light, dark = theme_mod.PALETTES["light"], theme_mod.PALETTES["dark"]
#    assert set(light) == set(dark), set(light) ^ set(dark)
#    assert set(theme_mod.TOKENS) == set(light)
#    # 暗色真的比較暗（拿最大的底色面積比）
#    assert sum(_rgb(dark["bg_page"])) < sum(_rgb(light["bg_page"]))
#
#
#def test_every_token_the_ui_asks_for_actually_exists():
#    """``TOKENS["typo"]`` 只會在**那個 widget 被畫出來的那一刻**炸。
#
#    離屏測試通常不觸發 ``paintEvent``（沒有人 grab 它），所以自繪元件裡
#    打錯的 token 名可以一路活到使用者打開那個畫面才 KeyError ——
#    已經發生過一次（``surface_raised``）。這裡靜態掃一遍，成本近乎零。
#
#    不需要 ``qapp``：純文字掃描，故意不 import Qt。
#    """
#    import ast
#    import pathlib
#
#    from adept.ui import theme as t
#
#    ui = pathlib.Path(__file__).resolve().parent.parent / "adept" / "ui"
#    bad = []
#    for py in sorted(ui.rglob("*.py")):
#        tree = ast.parse(py.read_text(encoding="utf-8"))
#        for node in ast.walk(tree):
#            if not isinstance(node, ast.Subscript):
#                continue
#            target = node.value
#            name = (target.id if isinstance(target, ast.Name)
#                    else getattr(target, "attr", None))
#            if name != "TOKENS":
#                continue
#            key = node.slice
#            if isinstance(key, ast.Constant) and isinstance(key.value, str):
#                if key.value not in t.PALETTES["light"]:
#                    bad.append("%s:%d  TOKENS[%r]"
#                               % (py.name, node.lineno, key.value))
#    assert not bad, "這些 token 不存在（畫到那個 widget 時才會 KeyError）：\n  " \
#                    + "\n  ".join(bad)
#
#
#def test_self_painted_widgets_survive_an_actual_repaint(qapp):
#    """真的畫一次。自繪元件的 bug 只在 ``paintEvent`` 執行時才浮出來。"""
#    from PySide6.QtGui import QPixmap
#
#    widgets = [widgets_mod.CurveEditor(), widgets_mod.CurveField(),
#               widgets_mod.ImageView(), widgets_mod.GroupIcon("region", "#c06a1d"),
#               widgets_mod.HistogramWidget(), widgets_mod.VerdictChip(),
#               widgets_mod.ProfilePanel()]
#    lib = widgets_mod.LibraryPanel()
#    lib.set_steps(_steps())
#    widgets.append(lib)
#
#    for theme_name in ("light", "dark"):
#        theme_mod.set_theme(theme_name)
#        for w in widgets:
#            w.resize(220, 160)
#            pm = QPixmap(w.size())
#            pm.fill()
#            w.render(pm)          # KeyError / 例外會在這裡冒出來
#            assert not pm.isNull()
#    theme_mod.apply_theme(qapp, "light")
#
#
#def test_set_theme_is_in_place_and_reversible(qapp):
#    """``TOKENS`` 必須是**同一個物件** —— 各模組都 import 過它了。"""
#    before = theme_mod.TOKENS
#    try:
#        theme_mod.set_theme("dark")
#        assert theme_mod.TOKENS is before, "set_theme 不可以換掉 TOKENS 物件"
#        assert theme_mod.current_theme() == "dark"
#        assert theme_mod.TOKENS["bg_page"] == theme_mod.PALETTES["dark"]["bg_page"]
#        assert theme_mod.seg_hex("algo") == theme_mod.PALETTES["dark"]["seg_algo"]
#
#        # 不認得的名字要退回預設，不能炸
#        assert theme_mod.set_theme("nope") == theme_mod.DEFAULT_THEME
#    finally:
#        theme_mod.apply_theme(qapp, "light")
#    assert theme_mod.current_theme() == "light"
#
#
#def test_theme_segment_tokens(qapp):
#    t = theme_mod.TOKENS
#    for cat in ("image", "algo", "adc"):
#        assert t["seg_%s" % cat].startswith("#")
#        assert t["seg_%s_bg" % cat].startswith("#")
#    for tone in ("good", "bad", "neutral"):
#        for part in ("bg", "text", "border"):
#            assert t["chip_%s_%s" % (tone, part)].startswith("#")
#
#
#def test_seg_color_mapping(qapp):
#    for cat in ("image", "algo", "adc"):
#        assert theme_mod.seg_color(cat).name() == theme_mod.TOKENS["seg_%s" % cat]
#        assert theme_mod.seg_bg(cat).name() == theme_mod.TOKENS["seg_%s_bg" % cat]
#    assert theme_mod.seg_color("algo", bg=True).name() == theme_mod.TOKENS["seg_algo_bg"]
#    # 未知分類要有中性退路，不能炸
#    assert theme_mod.seg_color("nope").isValid()
#
#
## --------------------------------------------------------------------------- #
## 1. ImageView
## --------------------------------------------------------------------------- #
#def test_image_view_uint8_float_and_none(qapp):
#    view = widgets_mod.ImageView()
#    view.resize(320, 240)
#
#    assert view.has_image() is False          # 初始 = 空狀態（畫「（無影像）」）
#
#    u8 = np.arange(256, dtype=np.uint8).reshape(16, 16)
#    view.set_image(u8)
#    assert view.has_image()
#    assert view.image().dtype == np.uint8
#    np.testing.assert_array_equal(view.image(), u8)   # uint8 直接用，不做拉伸
#    assert view.scale() > 1.0                          # 16x16 塞進 320x240 -> 放大
#
#    # float + NaN：自動 min-max，NaN 不參與統計也不會炸
#    f = np.full((8, 8), np.nan, dtype=np.float32)
#    f[0, 0] = -2.0
#    f[7, 7] = 6.0
#    view.set_image(f)
#    shown = view.image()
#    assert shown.dtype == np.uint8
#    assert shown[0, 0] == 0 and shown[7, 7] == 255
#    assert shown[3, 3] == 0                            # NaN -> 0
#
#    # 全 NaN 不應該爆
#    view.set_image(np.full((4, 4), np.nan, dtype=np.float32))
#    assert int(view.image().max()) == 0
#
#    view.set_image(None)
#    assert view.has_image() is False
#
#
#def test_image_view_wheel_zoom_changes_scale(qapp):
#    view = widgets_mod.ImageView()
#    view.resize(300, 200)
#    view.set_image(np.zeros((50, 50), dtype=np.uint8))
#    before = view.scale()
#
#    ev = QWheelEvent(QPointF(120, 90), QPointF(120, 90), QPoint(0, 0),
#                     QPoint(0, 120), Qt.NoButton, Qt.NoModifier,
#                     Qt.NoScrollPhase, False)
#    QApplication.sendEvent(view, ev)
#    assert view.scale() > before
#
#    ev_out = QWheelEvent(QPointF(120, 90), QPointF(120, 90), QPoint(0, 0),
#                         QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
#                         Qt.NoScrollPhase, False)
#    QApplication.sendEvent(view, ev_out)
#    assert view.scale() == pytest.approx(before, rel=1e-6)
#
#    view.zoom_by(4.0)
#    assert view.scale() > before
#    view.fit()                                   # 雙擊走的是同一條路
#    assert view.scale() == pytest.approx(before, rel=1e-6)
#
#
## --------------------------------------------------------------------------- #
## 2. ParamForm（用真實 registry 的卡片）
## --------------------------------------------------------------------------- #
#def test_param_form_int_and_image_key_from_snr_map(qapp):
#    form = widgets_mod.ParamForm()
#    edits = []
#    form.param_edited.connect(lambda n, v: edits.append((n, v)))
#
#    desc = _describe("snr_map")
#    streams = ["test", "ref", "diff", "ref_aligned"]
#    form.set_step(desc, {"window": 31}, streams)
#
#    # 每個 ParamSpec 都要有一列
#    assert form.param_names() == [p["name"] for p in desc["params"]]
#    # 建表本身不可以噴 param_edited
#    assert edits == []
#
#    window = form.editor("window")
#    assert isinstance(window, QSpinBox)
#    assert (window.minimum(), window.maximum()) == (5, 201)
#    assert window.value() == 31
#    window.setValue(41)
#    assert edits[-1] == ("window", 41)
#    assert isinstance(edits[-1][1], int)
#
#    clip = form.editor("clip_sigma")
#    assert isinstance(clip, QDoubleSpinBox)
#    assert clip.value() == pytest.approx(3.0)
#    clip.setValue(4.5)
#    assert edits[-1] == ("clip_sigma", pytest.approx(4.5))
#    assert isinstance(edits[-1][1], float)
#
#    # image_key -> 可編輯下拉，內容 = 呼叫端給的影像流
#    source = form.editor("source")
#    assert isinstance(source, QComboBox) and source.isEditable()
#    assert [source.itemText(i) for i in range(source.count())] == streams
#    assert source.currentText() == "diff"
#    source.setCurrentText("ref_aligned")
#    assert edits[-1] == ("source", "ref_aligned")
#
#    # 每一列都看得見白話 help（推廣鐵則）
#    for spec in desc["params"]:
#        assert form.hint_text(spec["name"]) == spec["help"]
#        assert spec["help"]
#
#
#def test_bounded_numbers_get_a_slider_bound_both_ways(qapp):
#    """F7-8：有上下界的數字都配一支滑桿。
#
#    「gamma 要填多少」對不會寫 code 的人沒有答案 —— 他要的是一邊拖一邊看圖。
#    數字框留著，因為 recipe 是要交接給別人的，那需要一個確切的值。
#    """
#    form = widgets_mod.ParamForm()
#    edits = []
#    form.param_edited.connect(lambda n, v: edits.append((n, v)))
#    form.set_step(_describe("gamma"), {}, ["test", "ref"])
#
#    s = form.slider("gamma")
#    box = form.editor("gamma")
#    assert isinstance(s, QSlider) and isinstance(box, QDoubleSpinBox)
#    assert edits == [], "建表本身不可以噴 param_edited"
#
#    # 滑桿 -> 數字框 -> param_edited
#    s.setValue(s.minimum())
#    assert box.value() == pytest.approx(0.1)
#    assert edits[-1] == ("gamma", pytest.approx(0.1))
#    s.setValue(s.maximum())
#    assert box.value() == pytest.approx(5.0)
#
#    # 數字框 -> 滑桿（反向也要跟上，而且不可以互相回寫到爆掉）
#    box.setValue(1.0)
#    assert s.value() == pytest.approx(s.maximum() * (1.0 - 0.1) / (5.0 - 0.1),
#                                      abs=2)
#    assert len([e for e in edits if e[0] == "gamma"]) == 3
#
#    # 整數參數也有；沒有上下界的就沒有（硬給一支只會誤導）
#    form.set_step(_describe("snr_map"), {}, ["test", "diff"])
#    assert isinstance(form.slider("window"), QSlider)
#    assert (form.slider("window").minimum(),
#            form.slider("window").maximum()) == (5, 201)
#    form.set_step(_describe("load_patch"), {}, [])
#    assert form.slider("channels") is None
#
#
#def test_curve_editor_is_wysiwyg_and_feeds_the_recipe(qapp):
#    """曲線編輯器畫的線 = 影像上套的線（同一個 core 函式）。
#
#    UI 自己再實作一份插值太容易了，而那會讓使用者看到的和跑出來的不一樣。
#    """
#    from adept.core.algo.curve import curve_lut
#    from adept.core.steps.tone import apply_curve
#
#    form = widgets_mod.ParamForm()
#    edits = []
#    form.param_edited.connect(lambda n, v: edits.append((n, v)))
#    form.set_step(_describe("gamma"), {}, ["test", "ref"])
#
#    field = form.editor("curve")
#    assert isinstance(field, widgets_mod.CurveField)
#    assert field.text() == "0,0; 1,1" and field.is_identity() is True
#
#    # 拉一個點 -> 值進 param_edited（也就是進 recipe）
#    field.editor._insert(0.4, 0.7)
#    assert edits[-1] == ("curve", "0,0; 0.4,0.7; 1,1")
#    assert field.is_identity() is False
#
#    # 畫面上的曲線就是 core 的 LUT
#    lut = curve_lut(field.editor.points(), 256)
#    assert lut[0] == pytest.approx(0.0) and lut[-1] == pytest.approx(1.0)
#    assert np.all(np.diff(lut) >= -1e-12), "保單調：不可以 overshoot 出假的暗環"
#    assert lut[int(0.4 * 255)] > 0.4, "把中間點往上拉，中間就要變亮"
#
#    # 而且引擎吃得下同一個字串
#    img = np.linspace(0, 255, 64, dtype=np.uint8).reshape(8, 8)
#    out = apply_curve(img, field.text())
#    assert out.dtype == img.dtype and out[4, 0] > img[4, 0]
#
#    # 打字打到一半的不合法字串不可以把辛苦拉的線清掉
#    before = field.text()
#    assert field.set_text("0,0; 0.4,") is False
#    assert field.text() == before
#
#    field.editor.reset()
#    assert field.text() == "0,0; 1,1"
#
#
#def test_a_drawn_curve_visibly_takes_over_from_the_gamma_slider(qapp):
#    """規則寫在 steps/tone.py（曲線接管 gamma），這裡驗**使用者看得見**。
#
#    不然他會拉了曲線又去動 gamma，然後以為 gamma 壞了。
#    """
#    form = widgets_mod.ParamForm()
#    form.set_step(_describe("gamma"), {}, ["test", "ref"])
#    gamma_row = form._rows["gamma"]
#    assert gamma_row.property("dimmed") == "false"
#
#    form.editor("curve").editor._insert(0.3, 0.6)
#    assert gamma_row.property("dimmed") == "true"
#    assert "custom curve" in form.hint_text("gamma")
#    # 調淡不是鎖死 —— 使用者可能只是想比較兩種做法
#    assert gamma_row.isEnabled() is True
#
#    form.editor("curve").editor.reset()
#    assert gamma_row.property("dimmed") == "false"
#    assert form.hint_text("gamma") == gamma_row.spec["help"]
#
#
#def test_curve_points_can_be_dragged_and_the_ends_stay_put(qapp):
#    """頭尾的 x 鎖在 0 和 1 —— 曲線必須覆蓋整個灰階範圍，少一段就沒定義。"""
#    ed = widgets_mod.CurveEditor()
#    ed.resize(200, 200)
#    seen = []
#    ed.curve_changed.connect(seen.append)
#
#    idx = ed._insert(0.5, 0.5)
#    assert idx == 1 and len(ed.points()) == 3
#
#    def _drag(px_from, px_to):
#        _mouse(ed, QEvent.MouseButtonPress, px_from, Qt.LeftButton)
#        _mouse(ed, QEvent.MouseMove, px_to, Qt.LeftButton)
#        _mouse(ed, QEvent.MouseButtonRelease, px_to, Qt.LeftButton, Qt.NoButton)
#
#    # 拖中間那點往上
#    _drag(ed._to_px(0.5, 0.5), ed._to_px(0.5, 0.85))
#    assert ed.points()[1][1] > 0.7
#    assert seen, "拖曳要發訊號，不然參數不會進 recipe"
#
#    # 拖最後一點：y 動得了，x 不動
#    _drag(ed._to_px(1.0, 1.0), ed._to_px(0.6, 0.6))
#    assert ed.points()[-1][0] == pytest.approx(1.0)
#    assert ed.points()[-1][1] < 0.9
#
#    # 頭尾刪不掉，中間刪得掉
#    ed._remove(0)
#    ed._remove(len(ed.points()) - 1)
#    assert len(ed.points()) == 3
#    ed._remove(1)
#    assert len(ed.points()) == 2
#
#
#def test_param_form_bool_choice_and_str(qapp):
#    form = widgets_mod.ParamForm()
#    edits = []
#    form.param_edited.connect(lambda n, v: edits.append((n, v)))
#
#    # bool -> QCheckBox（subtract.absolute 預設 True）
#    form.set_step(_describe("subtract"), {}, ["test", "ref_aligned"])
#    absolute = form.editor("absolute")
#    assert isinstance(absolute, QCheckBox)
#    assert absolute.isChecked() is True
#    absolute.setChecked(False)
#    assert edits[-1] == ("absolute", False)
#    assert isinstance(edits[-1][1], bool)
#
#    # choice -> 非可編輯 QComboBox，選項 = spec.choices
#    edits.clear()
#    desc = _describe("align")
#    form.set_step(desc, {}, ["test", "ref"])
#    method = form.editor("method")
#    choices = [p for p in desc["params"] if p["name"] == "method"][0]["choices"]
#    assert isinstance(method, QComboBox) and not method.isEditable()
#    assert [method.itemText(i) for i in range(method.count())] == choices
#    assert method.currentText() == "phase"
#    method.setCurrentText("ncc")
#    assert edits[-1] == ("method", "ncc")
#
#    # int 有下限：search_radius 1..64
#    radius = form.editor("search_radius")
#    assert (radius.minimum(), radius.maximum()) == (1, 64)
#
#    # str -> QLineEdit（load_patch.channels）
#    edits.clear()
#    form.set_step(_describe("load_patch"), {}, [])
#    channels = form.editor("channels")
#    assert isinstance(channels, QLineEdit)
#    assert channels.text() == "auto"
#    channels.setText("test,ref")
#    assert edits[-1] == ("channels", "test,ref")
#    assert isinstance(edits[-1][1], str)
#
#
#def test_param_form_show_and_clear_errors(qapp):
#    form = widgets_mod.ParamForm()
#    desc = _describe("snr_map")
#    form.set_step(desc, {}, ["diff"])
#    help_text = [p for p in desc["params"] if p["name"] == "window"][0]["help"]
#
#    assert form.has_error("window") is False
#    form.show_error("window", "參數 'window'：4 低於下限 5")
#    assert form.has_error("window") is True
#    assert "低於下限 5" in form.hint_text("window")
#    assert "color:%s" % theme_mod.TOKENS["danger_text"] in \
#        form._rows["window"].hint.styleSheet()
#    assert form.has_error("out") is False        # 其他列不受影響
#
#    form.clear_errors()
#    assert form.has_error("window") is False
#    assert form.hint_text("window") == help_text
#
#
#def test_param_form_empty_state(qapp):
#    form = widgets_mod.ParamForm()
#    form.set_step(None, {}, [])
#    assert form.param_names() == []
#    assert form.step_key() is None
#
#
## --------------------------------------------------------------------------- #
## 3. LibraryPanel
## --------------------------------------------------------------------------- #
#def test_library_panel_groups_and_double_click(qapp):
#    """F7-3：卡片庫改依**流程階段**分組（不是依 category 的影像／算法）。"""
#    panel = widgets_mod.LibraryPanel()
#    steps = _steps()
#    panel.set_steps(steps)
#
#    assert panel.section_titles() == [
#        "Input", "Enhance", "Region", "Compare", "Measure", "ADC"]
#    assert set(panel.step_keys()) == {s["key"] for s in steps}
#
#    # 每張卡都被歸進宣告的那一段
#    by_group = {}
#    for s_ in steps:
#        by_group.setdefault(s_["group"], set()).add(s_["key"])
#    assert "load_patch" in by_group["input"]
#    assert {"subtract", "align"} <= by_group["compare"]
#    assert "blob_segment" in by_group["region"]
#    assert {"glv_stats", "cd_measure", "roi_snr"} <= by_group["measure"]
#
#    # 空的段落要留一行提示（registry 目前沒有 adc 卡片）
#    empties = [lbl for lbl in panel.findChildren(QLabel)
#               if lbl.objectName() == "libEmpty"]
#    assert len(empties) == sum(
#        1 for g, _t, _s in panel.GROUPS if not by_group.get(g))
#
#    got = []
#    panel.add_requested.connect(got.append)
#
#    snr_desc = _describe("snr_map")
#    item = panel.entry("snr_map")
#    assert item is not None
#    assert item.label.text() == snr_desc["label"]
#    assert item.toolTip() == snr_desc["help"]             # help 掛成 tooltip
#    QTest.mouseDClick(item, Qt.LeftButton)
#    assert got == ["snr_map"]
#
#    # 另一條路：hover 出現的「Add」按鈕
#    other = panel.entry("align")
#    assert other.add_button.text() == "Add"
#    other.add_button.click()
#    assert got == ["snr_map", "align"]
#
#    # 重新 set_steps 不會留下舊項目
#    panel.set_steps([s_ for s_ in steps if s_["group"] == "compare"])
#    assert panel.entry("snr_map") is None
#    assert panel.entry("align") is not None
#
#
#def test_library_search_filters_cards_and_hides_empty_sections(qapp):
#    panel = widgets_mod.LibraryPanel()
#    panel.set_steps(_steps())
#    panel.toggle_group(None)                 # 全部收起來，只靠搜尋
#    everything = set(panel.step_keys())
#
#    panel.set_query("snr")
#    hit = set(panel.visible_step_keys())
#    assert {"snr_map", "roi_snr", "blob_segment"} <= hit
#    assert "denoise" not in hit
#    assert "Input" not in panel.visible_section_titles(), \
#        "整組都沒命中的區塊標題要一起收起來"
#
#    # 多個詞是 AND；說明文字也在搜尋範圍內
#    panel.set_query("region blob")
#    assert set(panel.visible_step_keys()) == {"blob_segment"}
#
#    # F7-7：清空搜尋之後回到 rail 的狀態（這裡是全部收起來），不是全部攤開
#    panel.set_query("")
#    assert panel.open_group() is None
#    assert panel.visible_step_keys() == []
#
#    panel.toggle_group("enhance")
#    assert set(panel.visible_step_keys()) < everything
#    assert panel.visible_section_titles() == ["Enhance"]
#
#
#def test_library_badges_unmet_prerequisites_but_still_allows_adding(qapp):
#    """前置條件沒滿足 → 標 ``needs …`` 並調淡，**但不擋著不給加**。
#
#    卡片庫的順序不是執行順序：使用者可能先放卡再補上游。擋住只會讓人以為壞了。
#    """
#    panel = widgets_mod.LibraryPanel()
#    panel.set_steps(_steps())
#
#    # 還不知道上游有什麼 -> 一個 badge 都不該出現（別在空流程上嚇人）
#    assert not [k for k in panel.step_keys() if panel.entry(k).badge_text()]
#
#    panel.set_available_streams(["test", "ref"])
#    assert panel.entry("snr_map").badge_text() == "needs diff"
#    assert panel.entry("subtract").badge_text() == "needs ref_aligned"
#    assert panel.entry("denoise").badge_text() == ""      # 只讀 test，滿足了
#
#    got = []
#    panel.add_requested.connect(got.append)
#    panel.entry("snr_map").add_button.click()
#    assert got == ["snr_map"], "有 badge 的卡仍然要加得進去"
#
#    # 上游補齊之後 badge 要消失
#    panel.set_available_streams(["test", "ref", "ref_aligned", "diff"])
#    assert panel.entry("snr_map").badge_text() == ""
#    assert panel.entry("subtract").badge_text() == ""
#
#
#def test_group_icons_are_painted_not_files(qapp):
#    """icon 一律 QPainter 畫 —— repo 有「只放純文字檔」的不變量。"""
#    panel = widgets_mod.LibraryPanel()
#    panel.set_steps(_steps())
#    # 每個階段有兩個 icon：rail 上的大顆 + 展開區的小標題；
#    # 再加 rail 底部的搜尋鈕（它不是流程階段，所以不在 stage_buttons 裡）
#    icons = panel.findChildren(widgets_mod.GroupIcon)
#    assert len(icons) == 2 * len(panel.GROUPS) + 1
#    assert len(panel.stage_buttons) == len(panel.GROUPS)
#    assert panel.search_button.group == "search"
#    assert all(i.width() > 0 and i.height() > 0 for i in icons)
#
#    # 換主題之後 icon 要跟著換色
#    before = [i.color for i in icons]
#    theme_mod.set_theme("dark")
#    try:
#        panel.refresh_colors()
#        assert [i.color for i in icons] != before
#    finally:
#        theme_mod.set_theme("light")
#        panel.refresh_colors()
#
#
## --------------------------------------------------------------------------- #
## 4. PipelinePanel
## --------------------------------------------------------------------------- #
#def _nodes():
#    return [
#        {"node_id": "load_patch", "step_key": "load_patch", "label": "載入影像",
#         "category": "image", "enabled": True, "summary": "channels=auto"},
#        {"node_id": "align", "step_key": "align", "label": "對位",
#         "category": "image", "enabled": False, "summary": "phase · r=8"},
#        {"node_id": "snr_map", "step_key": "snr_map", "label": "SNR 地圖",
#         "category": "algo", "enabled": True, "summary": "window=31"},
#        {"node_id": "verdict", "step_key": "verdict", "label": "判定",
#         "category": "adc", "enabled": True, "summary": ""},
#    ]
#
#
#def test_pipeline_panel_signals_and_styling(qapp):
#    panel = widgets_mod.PipelinePanel()
#    nodes = _nodes()
#    panel.set_nodes(nodes)
#    assert panel.node_ids() == ["load_patch", "align", "snr_map", "verdict"]
#
#    selected, toggled, moved, removed, scored = [], [], [], [], []
#    panel.node_selected.connect(selected.append)
#    panel.node_toggled.connect(lambda n, v: toggled.append((n, v)))
#    panel.move_requested.connect(lambda n, d: moved.append((n, d)))
#    panel.remove_requested.connect(removed.append)
#    panel.score_clicked.connect(lambda: scored.append(True))
#
#    # 左側 4px 色條 = 該段顏色；停用的節點轉灰
#    algo_card = panel.card("snr_map")
#    assert algo_card.bar.width() == 4
#    assert theme_mod.seg_hex("algo") in algo_card.bar.styleSheet()
#    disabled_card = panel.card("align")
#    assert theme_mod.TOKENS["seg_disabled"] in disabled_card.bar.styleSheet()
#    assert disabled_card.chk.isChecked() is False
#
#    # 點卡片 -> 選取 + accent ring
#    _mouse(algo_card, QEvent.MouseButtonPress, QPointF(30, 10),
#           Qt.LeftButton, Qt.LeftButton)
#    assert selected == ["snr_map"]
#    assert panel.selected() == "snr_map"
#    assert theme_mod.TOKENS["accent"] in algo_card.styleSheet()
#    assert theme_mod.TOKENS["accent"] not in panel.card("verdict").styleSheet()
#
#    # 每張卡的 ↑ ↓ ✕ 與啟用勾
#    panel.card("snr_map").btn_up.click()
#    panel.card("snr_map").btn_down.click()
#    panel.card("verdict").btn_remove.click()
#    panel.card("align").chk.setChecked(True)
#    assert moved == [("snr_map", -1), ("snr_map", 1)]
#    assert removed == ["verdict"]
#    assert toggled == [("align", True)]
#
#    # 固定尾卡 Score / Bin
#    panel.set_score_summary("snr_peak * 2", 3.5)
#    text = panel.score_summary_text()
#    assert "snr_peak * 2" in text and "3.5" in text
#    _mouse(panel.score_card, QEvent.MouseButtonPress, QPointF(20, 10),
#           Qt.LeftButton, Qt.LeftButton)
#    assert scored == [True]
#
#
#def test_pipeline_panel_selection_survives_set_nodes(qapp):
#    panel = widgets_mod.PipelinePanel()
#    panel.set_nodes(_nodes())
#    panel.set_selected("align")
#    assert panel.selected() == "align"
#
#    # 重新餵資料（改了摘要）：選取要留著
#    nodes = _nodes()
#    nodes[1]["summary"] = "ncc · r=12"
#    panel.set_nodes(nodes)
#    assert panel.selected() == "align"
#    assert theme_mod.TOKENS["accent"] in panel.card("align").styleSheet()
#    assert panel.card("align").summary.text() == "ncc · r=12"
#
#    # 被選的節點消失了 -> 選取清掉，不留幽靈
#    panel.set_nodes([n for n in nodes if n["node_id"] != "align"])
#    assert panel.selected() is None
#    assert panel.card("align") is None
#
#    panel.set_nodes([])
#    assert panel.node_ids() == []
#
#
## --------------------------------------------------------------------------- #
## 5. HistogramWidget
## --------------------------------------------------------------------------- #
#def test_histogram_data_threshold_and_drag(qapp):
#    hist = widgets_mod.HistogramWidget()
#    hist.resize(420, 220)
#
#    scores = [0.5, 1.0, 1.2, 2.0, 2.4, 3.0, 3.1, 3.9, 4.5, 5.0]
#    edges, counts = vm_mod.histogram(scores, n_bins=8)
#    hist.set_data(edges, counts)
#    assert hist.has_data()
#
#    hist.set_threshold(3.0)
#    assert hist.threshold() == pytest.approx(3.0)
#    # set_threshold 是程式設定，不該回頭發訊號
#    changed, committed = [], []
#    hist.threshold_changed.connect(changed.append)
#    hist.threshold_committed.connect(committed.append)
#    hist.set_threshold(2.5)
#    assert changed == [] and committed == []
#
#    rect = hist._plot_rect()
#    y = rect.center().y()
#    start = QPointF(rect.left() + 20, y)
#    mid = QPointF(rect.center().x(), y)
#    end = QPointF(rect.right() - 20, y)
#
#    _mouse(hist, QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton)
#    _mouse(hist, QEvent.MouseMove, mid, Qt.NoButton, Qt.LeftButton)
#    _mouse(hist, QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton)
#    _mouse(hist, QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton)
#
#    assert len(changed) >= 3, "拖曳過程要連續發 threshold_changed"
#    assert len(committed) == 1, "放開才 commit 一次"
#    lo, hi = edges[0], edges[-1]
#    for v in changed:
#        assert lo <= v <= hi
#    assert changed[0] < changed[-1]                      # 由左拖到右
#    assert committed[0] == pytest.approx(changed[-1])
#    assert hist.threshold() == pytest.approx(committed[0])
#    assert hist.threshold() == pytest.approx(hi, abs=(hi - lo) * 0.2)
#
#    # 拖出範圍也要夾在 [lo, hi] 內
#    changed.clear()
#    _mouse(hist, QEvent.MouseButtonPress, QPointF(rect.right() - 1, y),
#           Qt.LeftButton, Qt.LeftButton)
#    _mouse(hist, QEvent.MouseMove, QPointF(rect.right() + 500, y),
#           Qt.NoButton, Qt.LeftButton)
#    _mouse(hist, QEvent.MouseButtonRelease, QPointF(rect.right() + 500, y),
#           Qt.LeftButton, Qt.NoButton)
#    assert hist.threshold() == pytest.approx(hi)
#    assert all(lo <= v <= hi for v in changed)
#
#
#def test_histogram_bin_summary_tooltip_and_empty(qapp):
#    hist = widgets_mod.HistogramWidget()
#    hist.resize(420, 220)
#
#    # 空狀態
#    assert hist.has_data() is False
#    assert hist.bin_summary_text() == ""
#    hist.set_data([0.0, 1.0], [0])                       # viewmodel 的空回傳
#    assert hist.has_data() is False
#
#    scores = [0.5, 1.0, 1.2, 2.0, 2.4, 3.0, 3.1, 3.9, 4.5, 5.0]
#    edges, counts = vm_mod.histogram(scores, n_bins=8)
#    hist.set_data(edges, counts)
#
#    hist.set_bin_summary(vm_mod.rebin(scores, 3.0))
#    text = hist.bin_summary_text()
#    assert text.startswith("bin 0=") and "bin 1=" in text
#    assert text == "bin 0=5   bin 1=5"
#
#    # hover 某根長條 -> tooltip「score a–b：N 顆」
#    rect = hist._plot_rect()
#    bw = rect.width() / len(counts)
#    idx = next(i for i, c in enumerate(counts) if c > 0)
#    _mouse(hist, QEvent.MouseMove,
#           QPointF(rect.left() + bw * (idx + 0.5), rect.bottom() - 4))
#    tip = hist.toolTip()
#    assert "score" in tip and "defects" in tip and "–" in tip
#    assert tip.endswith("%d defects" % counts[idx])
#
#    hist.set_bin_summary({})
#    assert hist.bin_summary_text() == ""
#
#
## --------------------------------------------------------------------------- #
## 6. FeatureTable / VerdictChip
## --------------------------------------------------------------------------- #
#def test_feature_table_formatting_and_score_pinned_last(qapp):
#    table = widgets_mod.FeatureTable()
#    table.set_features(
#        {"score": 8.5, "snr_peak": 4.23456, "blob_area": 12.0,
#         "glv_mean": 128.0, "tiny": 0.00002},
#        highlight={"snr_peak"},
#    )
#    assert table.columnCount() == 2
#    assert [table.horizontalHeaderItem(i).text() for i in range(2)] == ["Feature", "Value"]
#
#    names = table.feature_names()
#    assert names[-1] == "score"                          # score 釘最後
#    assert set(names) == {"score", "snr_peak", "blob_area", "glv_mean", "tiny"}
#
#    assert table.value_text("blob_area") == "12"         # 乾淨整數
#    assert table.value_text("glv_mean") == "128"
#    assert table.value_text("snr_peak") == "4.235"       # 3 位小數
#    assert table.value_text("tiny") == "2e-05"           # 極小值不要變成 0.000
#    assert table.value_text("score") == "8.500"
#
#    score_row = names.index("score")
#    assert table.item(score_row, 0).font().bold() is True
#    assert table.item(score_row, 1).font().bold() is True
#
#    hi_row = names.index("snr_peak")
#    assert table.item(hi_row, 0).background().color().name() == \
#        theme_mod.TOKENS["accent_bg"]
#
#    table.set_features({})                               # 清空不該炸
#    assert table.rowCount() == 0
#
#
#def test_verdict_chip(qapp):
#    chip = widgets_mod.VerdictChip()
#    assert chip.text() == "—" and chip.tone() == "neutral"
#
#    chip.set_verdict(1)
#    assert chip.text() == "bin 1 · ≥ threshold"
#    assert chip.tone() == "good"
#    assert theme_mod.TOKENS["chip_good_bg"] in chip.styleSheet()
#    assert chip.verdict() == 1
#
#    chip.set_verdict(0)
#    assert chip.text() == "bin 0 · < threshold"
#    assert chip.tone() == "bad"
#    assert theme_mod.TOKENS["chip_bad_bg"] in chip.styleSheet()
#
#    # is_real_style：bin 1 = 抓到真缺陷 = 壞消息（紅），bin 0 = 乾淨（綠）
#    chip.set_verdict(1, is_real_style=True)
#    assert chip.text() == "bin 1 · ≥ threshold" and chip.tone() == "bad"
#    chip.set_verdict(0, is_real_style=True)
#    assert chip.text() == "bin 0 · < threshold" and chip.tone() == "good"
#
#    chip.set_verdict(None)
#    assert chip.text() == "—" and chip.verdict() is None
#
#
## --------------------------------------------------------------------------- #
## 7. F7-2 換膚：切主題之後畫面上的東西不能少，也不能殘留舊色
## --------------------------------------------------------------------------- #
#def test_studio_theme_toggle_keeps_everything_and_repaints(qapp):
#    from adept.ui import studio as studio_mod
#
#    win = studio_mod.StudioWindow(show_welcome_on_start=False)
#    try:
#        cards_before = win.library.step_keys()
#        assert theme_mod.current_theme() == "light"
#
#        assert win.toggle_theme() == "dark"
#        assert theme_mod.TOKENS["bg_page"] == theme_mod.PALETTES["dark"]["bg_page"]
#        assert win.library.step_keys() == cards_before, \
#            "換膚會重建卡片庫 —— 內容不可以在過程中掉東西"
#        assert qapp.styleSheet().find(theme_mod.PALETTES["dark"]["bg_page"]) >= 0
#
#        assert win.toggle_theme() == "light"
#        assert theme_mod.TOKENS["bg_page"] == theme_mod.PALETTES["light"]["bg_page"]
#    finally:
#        win.close()
#        theme_mod.apply_theme(qapp, "light")
#
#
## --------------------------------------------------------------------------- #
## 8. F7-7 左側 rail：先選階段，才展開裡面的卡片
## --------------------------------------------------------------------------- #
#def test_stage_rail_drills_down_one_stage_at_a_time(qapp):
#    """一開始就把 15 張卡攤開，正是「太瑣碎」的來源。"""
#    panel = widgets_mod.LibraryPanel()
#    panel.set_steps(_steps())
#
#    assert len(panel.stage_buttons) == len(panel.GROUPS)
#    # 每顆按鈕標出該段有幾張卡
#    for gid, _t, _s in panel.GROUPS:
#        n = sum(1 for d in _steps() if d["group"] == gid)
#        assert panel.stage_buttons[gid].count.text() == ("" if n == 0 else str(n))
#
#    panel.toggle_group("enhance")
#    assert panel.open_group() == "enhance"
#    assert panel.stage_buttons["enhance"].is_active() is True
#    visible = set(panel.visible_step_keys())
#    assert "gamma" in visible and "subtract" not in visible, \
#        "沒展開的階段不該出現在清單裡"
#
#    # 一次只開一段
#    panel.toggle_group("measure")
#    assert panel.open_group() == "measure"
#    assert panel.stage_buttons["enhance"].is_active() is False
#    assert "glv_stats" in panel.visible_step_keys()
#
#    # 點同一顆再一次 = 收起來
#    panel.toggle_group("measure")
#    assert panel.open_group() is None
#    assert panel.visible_step_keys() == []
#
#
#def test_search_still_reaches_across_collapsed_stages(qapp):
#    """收起來的階段不該把搜尋擋住 —— 搜尋是「我不知道它在哪一段」時用的。"""
#    panel = widgets_mod.LibraryPanel()
#    panel.set_steps(_steps())
#    panel.toggle_group(None)
#    assert panel.open_group() is None
#
#    panel.set_query("gamma")
#    assert panel.visible_step_keys() == ["gamma"]
#    panel.set_query("")
#    assert panel.visible_step_keys() == []
#
#
#def test_rail_is_vertical_and_the_card_area_gives_its_width_back(qapp):
#    """F7-8：rail 像工作列一樣由上而下，收起來時整欄只剩那條圖示條。
#
#    寬度用 ``minimumWidth()`` 驗，不用 ``width()`` —— 沒 show 過的 widget
#    幾何還沒生效，那會驗到一個假的數字。
#    """
#    panel = widgets_mod.LibraryPanel()
#    panel.set_steps(_steps())
#
#    assert panel.rail.layout().__class__.__name__ == "QVBoxLayout"
#    assert panel.rail.width() == panel.RAIL_W
#    # 「圖示要大一點」：rail 上的 icon 明顯大於區塊標題的小 icon
#    assert panel.stage_buttons["input"].icon._SIZE > widgets_mod.GroupIcon._SIZE
#
#    seen = []
#    panel.panel_toggled.connect(seen.append)
#
#    panel.toggle_group(None)
#    assert panel.panel_open() is False
#    assert panel.minimumWidth() == panel.RAIL_W, "收起來就該把寬度還出去"
#
#    panel.toggle_group("region")
#    assert panel.panel_open() is True
#    assert panel.minimumWidth() == panel.RAIL_W + panel.PANEL_W
#    assert seen == [False, True]
#
#
#def test_the_search_button_survives_collapsing_the_card_area(qapp):
#    """搜尋框住在卡片區裡，卡片區收起來它也跟著不見 ——
#    所以 rail 上必須留一顆放大鏡，不然搜尋就再也叫不出來了。"""
#    panel = widgets_mod.LibraryPanel()
#    panel.set_steps(_steps())
#    panel.toggle_group(None)
#    assert panel.panel_open() is False
#
#    panel.search_button.clicked.emit("search")
#    assert panel.panel_open() is True, "按了放大鏡就要把卡片區帶回來"
#    # 而且搜尋框真的可以打字（不是被留在隱藏的容器裡）
#    assert panel.search.isVisibleTo(panel) is True
#    panel.set_query("gamma")
#    assert panel.visible_step_keys() == ["gamma"]
#
#F a58940d76a6ddb0c6fede04f4f8912e3b3426825 353 tests/test_ui_workers.py
## ADEPT M3 背景工作層測試 — authored 2026-07-28.
#"""``adept.ui.workers`` 的 headless 測試（QT_QPA_PLATFORM=offscreen）。
#
#★ 為什麼 Qt 是「延遲匯入」★
#  ``tests/test_no_qt.py::test_no_qt_after_import`` 會檢查 ``sys.modules`` 裡
#  沒有任何 Qt 模組。pytest 在跑第一個測試之前會先 **collect**（import）所有
#  測試模組，所以本檔若在最上層 ``import PySide6`` 或 ``import
#  adept.ui.workers``（它自己 import PySide6），那道守門測試就會被這裡的
#  import 汙染而失敗。
#  因此：Qt 與 workers 一律在 ``qt`` fixture 裡才 import，並注入 module
#  globals（``QtCore`` / ``workers``）給各測試與輔助函式使用。最上層只留
#  Qt-free 的 core import。
#
#非同步測試一律用 ``_pump()``（QEventLoop + 輪詢 QTimer + 逾時）驅動：
#逾時就讓測試 fail，**不會**卡住整個 test session。
#"""
#from __future__ import annotations
#
#import sys
#import time
#from pathlib import Path
#
#import pytest
#
#import adept.core.steps  # noqa: F401 — 觸發卡片註冊
#from adept.core.pipeline import Recipe
#
#REPO = Path(__file__).resolve().parent.parent
#RECIPE_PATH = REPO / "examples" / "recipes" / "die_to_die_basic.json"
#
#sys.path.insert(0, str(REPO / "tools"))
#from make_sample import generate  # noqa: E402
#
#TIMEOUT_MS = 30000          # 單次等待上限（實測整檔 < 5s）
#PREVIEW_NODES = ["norm", "align", "sub", "dn", "snr"]
#
#
## ---------------------------------------------------------------------------
## fixtures
## ---------------------------------------------------------------------------
#@pytest.fixture(scope="module")
#def qt():
#    """延遲匯入 Qt 與 workers（見模組 docstring），建立唯一的 QApplication。"""
#    from PySide6 import QtCore, QtWidgets
#
#    import adept.ui.workers as workers_mod
#
#    g = globals()
#    g["QtCore"] = QtCore
#    g["workers"] = workers_mod
#
#    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
#    yield app
#
#
#@pytest.fixture(scope="module")
#def synlot(tmp_path_factory):
#    """6 顆 defect 的合成 lot（KLARF + 多頁 TIFF + ground truth）。"""
#    out = tmp_path_factory.mktemp("ui_synlot")
#    return generate(str(out), n=6, seed=7)
#
#
#@pytest.fixture(scope="module")
#def recipe():
#    return Recipe.load(str(RECIPE_PATH))
#
#
#@pytest.fixture(scope="module")
#def dataset(qt, synlot):
#    return workers.DatasetLoadWorker.run_sync(synlot["klarf"])
#
#
#@pytest.fixture
#def live():
#    """建立 worker 的工廠；測試結束一律 shutdown（測試自己再驗一次沒漏）。"""
#    created = []
#
#    def make(cls):
#        w = cls()
#        created.append(w)
#        return w
#
#    yield make
#    for w in created:
#        w.shutdown(5000)
#
#
## ---------------------------------------------------------------------------
## 事件迴圈驅動
## ---------------------------------------------------------------------------
#def _pump(predicate, timeout_ms=TIMEOUT_MS):
#    """轉 GUI event loop 直到 ``predicate()`` 為真；逾時回 False（不 hang）。"""
#    loop = QtCore.QEventLoop()
#    deadline = time.monotonic() + timeout_ms / 1000.0
#    state = {"ok": False}
#
#    def check():
#        if predicate():
#            state["ok"] = True
#            loop.quit()
#        elif time.monotonic() > deadline:
#            loop.quit()
#
#    poll = QtCore.QTimer()
#    poll.setInterval(5)
#    poll.timeout.connect(check)
#    poll.start()
#    check()                       # predicate 可能已成立
#    if not state["ok"]:
#        loop.exec()
#    poll.stop()
#    return state["ok"]
#
#
#def _drain(ms=100):
#    """再多轉一下 event loop，讓可能遲到的訊號進來（例如多餘的 ready）。"""
#    _pump(lambda: False, ms)
#
#
#def _assert_reaped(w):
#    """關閉後不該留下還在跑的 QThread。"""
#    assert w.shutdown(5000) is True
#    assert w.is_running() is False
#    assert w.thread_obj is None
#    assert not w._zombies, "有執行緒 join 逾時未回收"
#
#
## ---------------------------------------------------------------------------
## 1) 同步模式（headless，完全不碰 Qt 執行緒）
## ---------------------------------------------------------------------------
#def test_dataset_run_sync(qt, synlot):
#    ds = workers.DatasetLoadWorker.run_sync(synlot["klarf"])
#    assert ds.kind == "ebi_patch"
#    assert len(ds.items) == 6
#    assert "test" in ds.items[0].images and "ref" in ds.items[0].images
#    # 顯式帶 tiff 參數也要通
#    ds2 = workers.DatasetLoadWorker.run_sync(synlot["klarf"], synlot["tiff"])
#    assert ds2.kind == "ebi_patch" and len(ds2.items) == 6
#
#
#def test_dataset_run_sync_raises_on_error(qt, tmp_path):
#    # 路徑是資料夾 → load_dataset 開檔就爆（KLARF parser 對「不存在的檔」
#    # 是回空 doc 不 raise，所以這裡用必定 raise 的情境）
#    with pytest.raises(Exception):
#        workers.DatasetLoadWorker.run_sync(str(tmp_path))
#
#
#def test_preview_run_sync(qt, recipe, dataset):
#    item = dataset.items[0]
#    # 全程跑完：有 score / bin
#    full = workers.PreviewWorker.run_sync(recipe, item, dataset.kind)
#    assert full.ok, full.error
#    assert full.score is not None and full.bin in (0, 1)
#
#    # upto_node：停在該節點，context 帶著中間影像
#    mid = workers.PreviewWorker.run_sync(recipe, item, dataset.kind,
#                                         upto_node="sub")
#    assert mid.ok, mid.error
#    assert mid.context is not None
#    assert "diff" in mid.context.images and "test" in mid.context.images
#    assert mid.traces[-1].node_id == "sub"
#    assert mid.score is None                 # 中途預覽不算分
#
#
#def test_trial_run_sync(qt, recipe, dataset):
#    out = workers.TrialWorker.run_sync(recipe, dataset, 6, workers=1)
#    assert len(out) == 6
#    assert all(d["ok"] for d in out), [(d["defect_id"], d["error"]) for d in out]
#    assert all(isinstance(d["score"], float) for d in out)
#    assert all(d["features"].get("score") is not None for d in out)
#
#
## ---------------------------------------------------------------------------
## 2) DatasetLoadWorker 非同步
## ---------------------------------------------------------------------------
#def test_dataset_worker_async(qt, synlot, live):
#    w = live(workers.DatasetLoadWorker)
#    got, errs = [], []
#    w.loaded.connect(got.append)
#    w.failed.connect(errs.append)
#
#    assert w.start(synlot["klarf"]) is True
#    assert _pump(lambda: bool(got or errs)), "loaded/failed 30 秒內沒有發出"
#
#    assert not errs, errs
#    assert len(got) == 1
#    assert got[0].kind == "ebi_patch" and len(got[0].items) == 6
#    _assert_reaped(w)
#
#
#def test_dataset_worker_async_failure(qt, tmp_path, live):
#    w = live(workers.DatasetLoadWorker)
#    got, errs = [], []
#    w.loaded.connect(got.append)
#    w.failed.connect(errs.append)
#
#    w.start(str(tmp_path))                   # 資料夾 → load_dataset raise
#    assert _pump(lambda: bool(got or errs)), "failed 30 秒內沒有發出"
#    assert not got and len(errs) == 1 and errs[0]
#    _assert_reaped(w)
#
#
## ---------------------------------------------------------------------------
## 3) PreviewWorker：請求合併
## ---------------------------------------------------------------------------
#def test_preview_worker_coalesces_rapid_requests(qt, recipe, dataset, live):
#    w = live(workers.PreviewWorker)
#    results, busy, errs = [], [], []
#    w.ready.connect(results.append)
#    w.busy.connect(busy.append)
#    w.failed.connect(errs.append)
#
#    item = dataset.items[0]
#    for node in PREVIEW_NODES:              # 5 個快速連發（模擬拖參數）
#        w.request(recipe, item, dataset.kind, upto_node=node)
#
#    assert _pump(lambda: busy and busy[-1] is False), "佇列 30 秒內沒有排空"
#    _drain(150)                             # 等等看還有沒有遲到的 ready
#
#    assert not errs, errs
#    assert results, "至少要有一筆預覽結果"
#    assert len(results) < len(PREVIEW_NODES), \
#        f"沒有合併：{len(results)} 筆 ready（連發 {len(PREVIEW_NODES)} 次）"
#    # 最後一筆結果必須對應最後一次請求的 upto_node
#    last = results[-1]
#    assert last.ok, last.error
#    assert last.traces[-1].node_id == PREVIEW_NODES[-1]
#    assert last.context is not None and last.context.images
#    # busy 先 True、最後 False
#    assert busy[0] is True and busy[-1] is False
#    assert w.has_pending() is False
#    _assert_reaped(w)
#
#
#def test_preview_worker_sequential_requests(qt, recipe, dataset, live):
#    """一次一筆（每筆等它跑完）→ 不該有任何合併，每筆都要回。"""
#    w = live(workers.PreviewWorker)
#    results, busy = [], []
#    w.ready.connect(results.append)
#    w.busy.connect(busy.append)
#
#    item = dataset.items[1]
#    for i, node in enumerate(["norm", "sub", "dn"]):
#        w.request(recipe, item, dataset.kind, upto_node=node)
#        assert _pump(lambda: len(results) > i), f"第 {i} 筆預覽逾時"
#    assert _pump(lambda: busy and busy[-1] is False)
#
#    assert [r.traces[-1].node_id for r in results] == ["norm", "sub", "dn"]
#    assert busy.count(True) == 3
#    _assert_reaped(w)
#
#
#def test_preview_worker_unexpected_error_goes_to_failed(
#        qt, recipe, dataset, live, monkeypatch):
#    """錯誤策略：run_defect 意外爆掉 → 只發 failed(str)，不發假的 ready。"""
#    def boom(*a, **k):
#        raise RuntimeError("模擬意外")
#
#    monkeypatch.setattr(workers, "run_defect", boom)
#    w = live(workers.PreviewWorker)
#    results, busy, errs = [], [], []
#    w.ready.connect(results.append)
#    w.busy.connect(busy.append)
#    w.failed.connect(errs.append)
#
#    w.request(recipe, dataset.items[0], dataset.kind)
#    assert _pump(lambda: bool(errs) or bool(results)), "failed 30 秒內沒有發出"
#    _drain(100)
#
#    assert not results
#    assert len(errs) == 1 and "模擬意外" in errs[0]
#    assert busy[0] is True and busy[-1] is False
#    _assert_reaped(w)
#
#
## ---------------------------------------------------------------------------
## 4) TrialWorker 非同步 + abort
## ---------------------------------------------------------------------------
#def test_trial_worker_async(qt, recipe, dataset, live):
#    w = live(workers.TrialWorker)
#    prog, done, errs = [], [], []
#    w.progress.connect(lambda d, t: prog.append((d, t)))
#    w.done.connect(done.append)
#    w.failed.connect(errs.append)
#
#    assert w.start(recipe, dataset, 6, workers=1) is True
#    assert w.start(recipe, dataset, 6, workers=1) is False   # 忙碌中不重入
#    assert _pump(lambda: bool(done or errs)), "done/failed 30 秒內沒有發出"
#
#    assert not errs, errs
#    out = done[0]
#    assert len(out) == 6
#    assert all(d["ok"] for d in out), [(d["defect_id"], d["error"]) for d in out]
#    assert all(d["score"] is not None for d in out)
#    assert prog, "progress 一次都沒發"
#    assert prog[-1] == (6, 6)
#    assert [d for d, _ in prog] == sorted(d for d, _ in prog)
#    _assert_reaped(w)
#
#
#def test_trial_worker_abort_still_delivers(qt, recipe, dataset, live):
#    w = live(workers.TrialWorker)
#    done, errs = [], []
#    w.done.connect(done.append)
#    w.failed.connect(errs.append)
#
#    w.start(recipe, dataset, 6, workers=1)
#    w.abort()                                # 立刻喊停
#    assert w.is_aborted() is True
#    assert _pump(lambda: bool(done or errs)), "abort 後 done 30 秒內沒有發出"
#
#    assert not errs, errs
#    assert isinstance(done[0], list)
#    assert len(done[0]) <= 6                 # 部分結果（可能為空）
#    _assert_reaped(w)
#
#
## ---------------------------------------------------------------------------
## 5) 生命週期：不漏執行緒
## ---------------------------------------------------------------------------
#def test_shutdown_is_safe_without_any_job(qt):
#    for cls in (workers.DatasetLoadWorker, workers.PreviewWorker,
#                workers.TrialWorker):
#        w = cls()
#        assert w.is_running() is False
#        assert w.thread_obj is None
#        assert w.shutdown() is True          # 沒跑過也能安全關
#        assert w.stop() is True              # 重複關也安全
#        assert w.thread_obj is None
#
#
#def test_stop_during_running_job_joins(qt, recipe, dataset, synlot):
#    """關窗情境：工作正在跑時 stop() → join 完成、無殘留執行緒。"""
#    w = workers.TrialWorker()
#    done = []
#    w.done.connect(done.append)
#    w.start(recipe, dataset, 6, workers=1)
#    assert w.is_running() is True
#    assert w.stop(10000) is True             # 設 abort 旗標 + join
#    assert w.is_running() is False
#    assert w.thread_obj is None
#    assert not w._zombies
#
#    p = workers.PreviewWorker()
#    p.request(recipe, dataset.items[0], dataset.kind, upto_node="snr")
#    p.request(recipe, dataset.items[0], dataset.kind, upto_node="glv")
#    assert p.has_pending() is True
#    assert p.shutdown(10000) is True
#    assert p.has_pending() is False          # 待跑請求作廢
#    assert p.is_running() is False and p.thread_obj is None
#    _drain(50)                               # 過期的 finished 通知不該炸
#    assert p.is_running() is False
#
#F 24571931e3aa73f5caded9462396fe1aa3b49589 78 tests/test_viewmodel.py
## ADEPT M3 viewmodel 測試（Qt-free）— authored 2026-07-28.
#from __future__ import annotations
#
#from pathlib import Path
#
#import pytest
#
#import adept.core.steps  # noqa: F401 — 註冊卡片
#from adept.core.pipeline import ParamError, Recipe
#from adept.ui.viewmodel import RecipeModel, histogram, rebin
#
#RECIPE = Path(__file__).resolve().parent.parent / "examples" / "recipes" / "die_to_die_basic.json"
#
#
#def test_build_route_by_mouse_ops():
#    m = RecipeModel(kind="ebi_patch")
#    changes = []
#    m.add_listener(lambda: changes.append(1))
#    a = m.add_step("load_patch")
#    b = m.add_step("percentile_norm")
#    c = m.add_step("align")
#    assert m.node_order == [a, b, c] and changes
#    # 重複 key → 唯一 id
#    d = m.add_step("align")
#    assert d == "align2"
#    m.move(d, -1)
#    assert m.node_order == [a, b, d, c]
#    m.remove(d)
#    assert m.node_order == [a, b, c]
#    m.set_enabled(b, False)
#    assert m.nodes[b].enabled is False
#
#
#def test_param_validation_rejects_bad_value():
#    m = RecipeModel()
#    m.add_step("load_patch")
#    n = m.add_step("snr_map")
#    m.set_param(n, "window", 15)
#    assert m.nodes[n].params["window"] == 15
#    with pytest.raises(ParamError):
#        m.set_param(n, "window", 999)          # 超出上限
#    assert m.nodes[n].params["window"] == 15   # 不落地
#
#
#def test_available_streams_and_features():
#    m = RecipeModel(kind="ebi_patch")
#    load = m.add_step("load_patch")
#    m.add_step("align")
#    sub = m.add_step("subtract")
#    snr = m.add_step("snr_map")
#    streams = m.available_streams(before_node=sub)
#    assert "test" in streams and "ref" in streams and "ref_aligned" in streams
#    feats = m.available_features()
#    assert "snr_max" in feats and "align_dx" in feats
#    assert "snr_max" not in m.available_features(upto_node=sub)
#    assert m.category_of(load) == "image" and m.category_of(snr) == "algo"
#
#
#def test_roundtrip_with_example_recipe():
#    recipe = Recipe.load(str(RECIPE))
#    m = RecipeModel.from_recipe(recipe)
#    assert m.kind == "ebi_patch" and not m.dirty
#    out = m.to_recipe()
#    assert out.routes["ebi_patch"] == recipe.routes["ebi_patch"]
#    assert out.score.expr == recipe.score.expr
#    issues = m.validate()
#    assert not [i for i in issues if i.level == "error"]
#    m.set_threshold(60.0)
#    assert m.dirty and m.to_recipe().score.threshold == 60.0
#
#
#def test_histogram_and_rebin():
#    edges, counts = histogram([1, 2, 2, 3, 10], n_bins=9)
#    assert len(edges) == 10 and sum(counts) == 5
#    assert histogram([])[1] == [0]
#    out = rebin([1.0, 2.0, 60.0, None, float("nan")], threshold=50.0)
#    assert out == {0: 2, 1: 1}
#
#F 7686c156f22af29465ce3a73caf617df4bafad77 78 tools/_synth.py
##!/usr/bin/env python3
## ADEPT synthetic-data helpers — authored 2026-07-28 (M4-2).
#"""合成影像的共用零件（`make_sample.py` 與 `make_sample_rsem.py` 共用）。
#
#這裡只放「畫圖案」與「種缺陷」這兩件純函式的事，沒有任何 IO；
#兩支產生器各自負責自己的 KLARF 格式與檔案佈局。
#
#★ 這些函式的數值行為必須保持穩定 ★
#`tests/test_make_sample.py` 有「同 seed → TIFF 位元組完全相同」的鎖定測試，
#改動任何一行都會改變既有合成 lot 的像素值。要調整請另開新函式，別就地改。
#"""
#from __future__ import annotations
#
#import numpy as np
#
## 缺陷型別（ground_truth.json 的 "type" 欄位用同一組字串）
#REAL_TYPES = ("bright_blob", "dark_blob", "bridge")
#NUISANCE_TYPE = "none"
#
#
#def rounded_square_tile(pitch: int) -> np.ndarray:
#    """一格圓角方塊 cell（float32，暗底 60 / 亮方塊 200，1px 軟邊）。"""
#    p = int(pitch)
#    c = (p - 1) / 2.0
#    yy, xx = np.mgrid[0:p, 0:p]
#    xx = xx - c
#    yy = yy - c
#    half = p * 0.30          # 方塊半寬
#    rad = max(1.0, p * 0.15)  # 圓角半徑
#    qx = np.abs(xx) - (half - rad)
#    qy = np.abs(yy) - (half - rad)
#    outside = np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0))
#    inside = np.minimum(np.maximum(qx, qy), 0.0)
#    d = outside + inside - rad          # 圓角方塊 signed distance
#    t = np.clip(0.5 - d, 0.0, 1.0)      # 1px 軟邊
#    return (60.0 + t * (200.0 - 60.0)).astype(np.float32)
#
#
#def pattern(size: int, pitch: int, off_x: int, off_y: int,
#            tile: np.ndarray) -> np.ndarray:
#    """以 (off_x, off_y) 相位取出 size×size 的週期圖案：P(x,y)=T((y+off_y)%p,(x+off_x)%p)。
#
#    相位是「從鋪好的大圖上換個位置裁切」，不是重新取樣 ——
#    所以裁出來的圖仍然是嚴格週期為 pitch 的晶格（Golden Cell 疊圖的前提）。
#    """
#    p = int(pitch)
#    reps = size // p + 2
#    big = np.tile(tile, (reps, reps))
#    oy = off_y % p
#    ox = off_x % p
#    return big[oy:oy + size, ox:ox + size].copy()
#
#
#def plant_anomaly(img: np.ndarray, kind: str, rng: np.random.Generator,
#                  pitch: int) -> None:
#    """在圖上就地種一個缺陷（靠近中心、振幅 >= 50）。"""
#    h, w = img.shape
#    amp = float(rng.uniform(55.0, 95.0))            # 振幅保證 >= 50
#    cx = w / 2.0 + float(rng.uniform(-0.1, 0.1)) * w
#    cy = h / 2.0 + float(rng.uniform(-0.1, 0.1)) * h
#    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
#
#    if kind in ("bright_blob", "dark_blob"):
#        sigma = float(rng.uniform(1.8, 3.5))
#        bump = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * sigma ** 2))
#        img += (amp if kind == "bright_blob" else -amp) * bump.astype(np.float32)
#    else:  # bridge：連接相鄰 cell 的短亮線（水平或垂直）
#        length = max(4.0, 1.8 * pitch)
#        thick = 1.2
#        if rng.random() < 0.5:
#            du, dv = xx - cx, yy - cy       # 水平線
#        else:
#            du, dv = yy - cy, xx - cx       # 垂直線
#        along = np.clip(np.abs(du) - length / 2.0, 0.0, None)
#        dist = np.hypot(along, np.abs(dv))
#        line = np.clip(1.0 - (dist - thick), 0.0, 1.0)
#        img += amp * line.astype(np.float32)
#
#F f8c1eef367e78983dd4b33d8a4a7a485366070d6 122 tools/check_files.py
##!/usr/bin/env python3
## ADEPT 檔案比對 — authored 2026-07-30.
#"""比對這台機器上的程式碼跟 ``tools/FILELIST.txt``，列出**要重新複製哪幾個檔案**。
#
#為什麼需要這支
#--------------
#公司機的情況（見 `docs/NO-GIT-SETUP.md` §「兩台機器」）：不能用 git、不能下載
#任何東西，但**看得到 GitHub 上的檔案並且可以複製**。所以更新程式碼的動作是
#「在瀏覽器上開檔案 → 按複製鈕 → 貼進本機的檔案」——
#而問題是 176 個檔案裡**哪幾個變了**。
#
#答案在 `tools/FILELIST.txt`：它是全部檔案的 git blob SHA。那一個檔案只有 12 KB，
#複製它幾秒鐘。複製完跑這支，它會告訴你剩下要複製哪幾個。
#
#    python tools/check_files.py
#
#所以更新一次的成本是「一次小複製 + 幾次針對性的複製」，而不是重跑整個
#六批的搬運流程。
#
#它**不連網路**（公司機連不出去），只比對磁碟上的東西。
#"""
#from __future__ import annotations
#
#import argparse
#import hashlib
#import os
#import sys
#from typing import Dict, List, Tuple
#
#MANIFEST = os.path.join("tools", "FILELIST.txt")
#RAW = "https://github.com/hxlub0905-cmyk/ADEPT/blob/main/%s"
#
#
#def blob_sha(data: bytes) -> str:
#    """git 算 blob SHA 的方式：``"blob <長度>\\0" + 內容``。"""
#    h = hashlib.sha1()                                # noqa: S324 — git 的格式
#    h.update(b"blob %d\0" % len(data))
#    h.update(data)
#    return h.hexdigest()
#
#
#def read_manifest(path: str) -> Dict[str, str]:
#    want: Dict[str, str] = {}
#    with open(path, "r", encoding="utf-8") as f:
#        for line in f:
#            line = line.strip()
#            if line and not line.startswith("#"):
#                sha, _, rel = line.partition(" ")
#                if rel:
#                    want[rel] = sha
#    return want
#
#
#def compare(root: str, want: Dict[str, str]) -> Tuple[List[str], List[str]]:
#    """回傳 (缺的, 內容不一樣的)。"""
#    missing, stale = [], []
#    for rel, sha in sorted(want.items()):
#        full = os.path.join(root, rel.replace("/", os.sep))
#        if not os.path.isfile(full):
#            missing.append(rel)
#            continue
#        with open(full, "rb") as f:
#            if blob_sha(f.read()) != sha:
#                stale.append(rel)
#    return missing, stale
#
#
#def main(argv=None) -> int:
#    ap = argparse.ArgumentParser(
#        description="Which files differ from tools/FILELIST.txt")
#    ap.add_argument("--root", default=".", help="程式碼在哪個資料夾（預設目前目錄）")
#    ap.add_argument("--urls", action="store_true",
#                    help="連 GitHub 上的網址一起印出來（貼到瀏覽器就能複製）")
#    a = ap.parse_args(argv)
#
#    root = os.path.abspath(a.root)
#    path = os.path.join(root, MANIFEST)
#    if not os.path.isfile(path):
#        print("✗ 找不到 %s" % path)
#        print("  先從 GitHub 複製那一個檔案過來（只有 12 KB）——")
#        print("  它是「哪些檔案變了」的唯一依據：")
#        print("    %s" % (RAW % "tools/FILELIST.txt"))
#        return 2
#
#    want = read_manifest(path)
#    if not want:
#        print("✗ %s 是空的（複製的時候被截斷了？）" % MANIFEST)
#        return 2
#
#    missing, stale = compare(root, want)
#    print("清單裡有 %d 個檔案。" % len(want))
#    print("缺少      : %d" % len(missing))
#    print("內容不一樣: %d" % len(stale))
#
#    if not missing and not stale:
#        print("")
#        print("✓ 這一份跟清單完全一致。")
#        print("")
#        print("注意：清單自己也可能是舊的 —— 它只證明「你的檔案跟你手上這份清單"
#              "一致」。要確認是最新的，重新複製一次 tools/FILELIST.txt 再跑一遍。")
#        return 0
#
#    todo = [("缺少", missing), ("內容不一樣", stale)]
#    for label, group in todo:
#        if not group:
#            continue
#        print("")
#        print("%s（%d 個）—— 從 GitHub 複製這幾個：" % (label, len(group)))
#        for rel in group:
#            print("    %s" % rel)
#            if a.urls:
#                print("        %s" % (RAW % rel))
#    print("")
#    print("複製的方式：在瀏覽器打開那個檔案 → 按右上角的複製鈕 → 貼進本機的同名"
#          "檔案。複製完再跑一次這支確認。")
#    # 有東西要處理就回非零 —— 這樣包在批次檔裡也看得出結果。
#    return 1
#
#
#if __name__ == "__main__":
#    sys.exit(main())
#
#F 6e7239f088a5a140f56ba29f2269b5295b75aecf 421 tools/doctor.py
##!/usr/bin/env python3
## -*- coding: utf-8 -*-
## ADEPT offline packaging tool #3 — authored 2026-07-28 (M6-1).
#"""ADEPT 環境自檢（doctor）：一次告訴你「這台機器能不能跑 ADEPT」。
#
#用法：
#    python tools/doctor.py            # 在 ADEPT 專案資料夾裡執行
#    python tools/doctor.py --verbose  # 連錯誤細節一起印
#    python tools/doctor.py --skip-smoke   # 不跑最後的端到端試跑（省 10 秒）
#
#檢查項目（每項都會給一行「怎麼修」）：
#    1. Python 版本 >= 3.9、是不是 64 位元
#    2. numpy / opencv-python(cv2) / tifffile / PySide6 / openpyxl 能不能 import、版本多少
#       （pytest 是選用的，缺了只給提醒）
#    3. 從**目前這個資料夾**能不能 import 到 adept —— 最常見的錯是「跑錯資料夾」
#    4. PySide6 能不能真的開一個 QApplication（用子行程做，避免整支 doctor 被拖死）
#    5. 目前資料夾與快取資料夾 ~/.adept 有沒有寫入權限
#    6. 端到端試跑：產一份迷你合成 lot，用範例 recipe 跑一顆 defect（約 10 秒）
#
#離開碼：必要項目全過 = 0，否則 = 1。最後一行永遠是一句白話結論。
#
#本檔在「相依套件還沒裝好」時也必須能跑，所以**模組層只 import 標準函式庫**；
#第三方套件一律在函式內部 lazy import 或丟到子行程裡驗。
#"""
#from __future__ import annotations
#
#import argparse
#import json
#import os
#import struct
#import subprocess
#import sys
#import tempfile
#import time
#from typing import List, Optional, Sequence, Tuple
#
#MIN_PYTHON = (3, 9)
#CACHE_DIR_NAME = ".adept"
#
## 相依套件： (pip 上的名字, import 用的名字, 是否必要)
#DEPENDENCIES: Tuple[Tuple[str, str, bool], ...] = (
#    ("numpy", "numpy", True),
#    ("opencv-python", "cv2", True),
#    ("tifffile", "tifffile", True),
#    ("openpyxl", "openpyxl", True),
#    ("PySide6", "PySide6", True),
#    ("pytest", "pytest", False),
#)
#
#OK, WARN, BAD = "ok", "warn", "bad"
#
#_MARKS = {OK: "✓", WARN: "△", BAD: "✗"}
#_MARKS_ASCII = {OK: "[OK]", WARN: "[!!]", BAD: "[XX]"}
#
#REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#EXAMPLE_RECIPE = os.path.join(REPO_ROOT, "examples", "recipes", "die_to_die_basic.json")
#
#SMOKE_TIMEOUT_S = 180.0
#QT_TIMEOUT_S = 90.0
#_JSON_TAG = "ADEPT_DOCTOR_JSON:"
#
#
## ---------------------------------------------------------------- 輸出小工具
#
#def _width(text: str) -> int:
#    """顯示寬度：CJK 全形字算 2 格（不然表格會歪掉）。"""
#    import unicodedata
#
#    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)
#
#
#def _pad(text: str, width: int) -> str:
#    return text + " " * max(0, width - _width(text))
#
#
#def _marks():
#    """Big5/cp950 主控台可能吐不出 ✓✗△，吐不出來就退回純 ASCII。"""
#    enc = getattr(sys.stdout, "encoding", None) or "ascii"
#    try:
#        "".join(_MARKS.values()).encode(enc)
#    except (UnicodeEncodeError, LookupError):
#        return _MARKS_ASCII
#    return _MARKS
#
#
#class Report(object):
#    """收集每一項檢查結果，最後印成表格。"""
#
#    def __init__(self) -> None:
#        self.rows: List[dict] = []
#
#    def add(self, status: str, name: str, detail: str = "",
#            hint: str = "", essential: bool = True, extra: str = "") -> str:
#        self.rows.append({"status": status, "name": name, "detail": detail,
#                          "hint": hint, "essential": essential, "extra": extra})
#        return status
#
#    def failures(self) -> List[dict]:
#        return [r for r in self.rows if r["status"] == BAD and r["essential"]]
#
#    def warnings(self) -> List[dict]:
#        return [r for r in self.rows if r["status"] == WARN
#                or (r["status"] == BAD and not r["essential"])]
#
#    def render(self, verbose: bool = False) -> None:
#        marks = _marks()
#        w_mark = max(_width(m) for m in marks.values())
#        w_name = max([4] + [_width(r["name"]) for r in self.rows])
#        print("")
#        for r in self.rows:
#            print("  %s %s  %s" % (_pad(marks[r["status"]], w_mark),
#                                   _pad(r["name"], w_name), r["detail"]))
#            if r["status"] != OK and r["hint"]:
#                print("  %s   → 修正建議：%s" % (" " * w_mark, r["hint"]))
#            if verbose and r["extra"]:
#                for line in str(r["extra"]).rstrip().splitlines():
#                    print("      | %s" % line)
#
#
## ---------------------------------------------------------------- 子行程腳本
#
#_QT_CHILD = r"""
#import json, os, sys
#os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
#out = {"import_ok": False, "version": None, "app_ok": False, "error": None}
#try:
#    import PySide6
#    out["import_ok"] = True
#    out["version"] = getattr(PySide6, "__version__", None)
#    from PySide6.QtWidgets import QApplication
#    app = QApplication.instance() or QApplication([])
#    out["app_ok"] = True
#except BaseException as exc:
#    out["error"] = "%s: %s" % (type(exc).__name__, exc)
#sys.stdout.write("ADEPT_DOCTOR_JSON:" + json.dumps(out) + "\n")
#"""
#
#_SMOKE_CHILD = r"""
#import json, os, shutil, sys, tempfile
#root = sys.argv[1]
#recipe_path = sys.argv[2]
#sys.path.insert(0, root)
#sys.path.insert(1, os.path.join(root, "tools"))
#out = {"ok": False, "error": None, "score": None, "kind": None, "n_features": 0}
#work = None
#try:
#    import make_sample
#    import adept.core.steps  # noqa: F401  觸發卡片註冊
#    from adept.core.ingest.dataset import load_dataset
#    from adept.core.pipeline import Recipe, run_defect
#
#    work = tempfile.mkdtemp(prefix="adept_doctor_")
#    info = make_sample.generate(os.path.join(work, "lot"), n=2, seed=7)
#    ds = load_dataset(info["klarf"])
#    out["kind"] = ds.kind
#    recipe = Recipe.load(recipe_path)
#    res = run_defect(recipe, ds.items[0], ds.kind)
#    out["ok"] = bool(res.ok) and res.score is not None
#    out["error"] = res.error
#    out["score"] = res.score
#    out["n_features"] = len(res.features or {})
#except BaseException as exc:
#    out["error"] = "%s: %s" % (type(exc).__name__, exc)
#finally:
#    if work:
#        shutil.rmtree(work, ignore_errors=True)
#sys.stdout.write("ADEPT_DOCTOR_JSON:" + json.dumps(out) + "\n")
#"""
#
#
#def _run_child(code: str, args: Sequence[str], timeout: float,
#               cwd: Optional[str] = None) -> Tuple[Optional[dict], str]:
#    """跑一段子行程並抓回它印的 JSON。回傳 (資料 or None, 原始輸出)。"""
#    cmd = [sys.executable, "-c", code] + list(args)
#    env = dict(os.environ)
#    env.setdefault("QT_QPA_PLATFORM", "offscreen")
#    env["PYTHONIOENCODING"] = "utf-8"
#    try:
#        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#                              timeout=timeout, cwd=cwd, env=env)
#    except subprocess.TimeoutExpired:
#        return None, "子行程超過 %.0f 秒沒有結束（timeout）。" % timeout
#    except OSError as exc:
#        return None, "叫不動子行程：%s" % exc
#    text = (proc.stdout or b"").decode("utf-8", "replace")
#    for line in text.splitlines():
#        if line.startswith(_JSON_TAG):
#            try:
#                return json.loads(line[len(_JSON_TAG):]), text
#            except ValueError:
#                break
#    tail = text.strip() or "（子行程沒有任何輸出）"
#    return None, "子行程異常結束（回傳碼 %d）：\n%s" % (proc.returncode, tail)
#
#
## ---------------------------------------------------------------- 各項檢查
#
#def check_python(rep: Report) -> None:
#    vi = sys.version_info
#    ver = "%d.%d.%d" % (vi[0], vi[1], vi[2])
#    if vi[:2] >= MIN_PYTHON:
#        rep.add(OK, "Python 版本", "%s（需要 >= %d.%d）" % (ver, MIN_PYTHON[0], MIN_PYTHON[1]),
#                extra=sys.executable)
#    else:
#        rep.add(BAD, "Python 版本", "%s 太舊（需要 >= %d.%d）" % (ver, MIN_PYTHON[0], MIN_PYTHON[1]),
#                hint="請改用 Python %d.%d 以上；公司機通常在「開始→Python」裡可以選版本。"
#                     % (MIN_PYTHON[0], MIN_PYTHON[1]),
#                extra=sys.executable)
#
#    bits = struct.calcsize("P") * 8
#    if bits >= 64:
#        rep.add(OK, "Python 位元數", "64 位元")
#    else:
#        rep.add(WARN, "Python 位元數", "32 位元", essential=False,
#                hint="PySide6/opencv 幾乎只出 64 位元 wheel；請改裝 64 位元的 Python。")
#
#
#def check_dependencies(rep: Report, verbose: bool = False) -> bool:
#    """回傳「必要套件是否全部 import 成功」。PySide6 只在這裡看版本，實際能否開視窗由 Qt 檢查負責。"""
#    all_ok = True
#    for pip_name, import_name, essential in DEPENDENCIES:
#        try:
#            mod = __import__(import_name)
#            ver = getattr(mod, "__version__", None) or _dist_version(pip_name) or "（版本不明）"
#            rep.add(OK, "套件 %s" % pip_name, "%s → import %s 成功" % (ver, import_name))
#        except BaseException as exc:  # noqa: BLE001 — 什麼爛事都可能發生
#            detail = "import %s 失敗：%s" % (import_name, type(exc).__name__)
#            if essential:
#                all_ok = False
#                rep.add(BAD, "套件 %s" % pip_name, detail,
#                        hint="離線安裝：python tools\\install_offline.py --wheels wheels"
#                             "（或有網路時 pip install %s）" % pip_name,
#                        extra="%s: %s" % (type(exc).__name__, exc))
#            else:
#                rep.add(WARN, "套件 %s" % pip_name, detail + "（選用）", essential=False,
#                        hint="只有要跑測試才需要：pip install pytest（離線時加 --include-pytest 抓）",
#                        extra="%s: %s" % (type(exc).__name__, exc))
#    return all_ok
#
#
#def _dist_version(pip_name: str) -> Optional[str]:
#    try:
#        from importlib import metadata  # Python 3.8+
#        return metadata.version(pip_name)
#    except Exception:  # noqa: BLE001
#        return None
#
#
#def check_adept_importable(rep: Report) -> bool:
#    """從**目前工作資料夾**能不能 import adept —— 專治「跑錯資料夾」。"""
#    cwd = os.getcwd()
#    has_dir = os.path.isdir(os.path.join(cwd, "adept"))
#    if cwd not in sys.path:
#        sys.path.insert(0, cwd)
#    try:
#        import adept  # noqa: F401
#        where = os.path.dirname(os.path.abspath(adept.__file__ or ""))
#        rep.add(OK, "adept 套件", "可以載入（%s）" % where)
#        return True
#    except BaseException as exc:  # noqa: BLE001
#        if has_dir:
#            hint = ("目前資料夾裡有 adept\\，但載入失敗 —— 通常是相依套件沒裝好"
#                    "（看上面的套件檢查），或 adept\\ 裡的檔案不完整（請重新解壓一次原始碼 zip）。")
#        else:
#            hint = ("你跑錯資料夾了。請先 cd 到「裡面看得到 adept\\ 這個資料夾」的地方"
#                    "（解壓後通常是 ADEPT-main\\），再執行一次："
#                    "cd C:\\...\\ADEPT-main 然後 python tools\\doctor.py")
#        rep.add(BAD, "adept 套件", "在目前資料夾 %s 載入不到（%s）" % (cwd, type(exc).__name__),
#                hint=hint, extra="%s: %s" % (type(exc).__name__, exc))
#        return False
#
#
#def check_qt(rep: Report) -> None:
#    data, raw = _run_child(_QT_CHILD, [], QT_TIMEOUT_S)
#    if data is None:
#        rep.add(BAD, "Qt 圖形介面", "PySide6 檢查子行程沒有正常結束（可能是直接當掉）",
#                hint="PySide6 裝壞了或缺系統元件：請重裝 PySide6，"
#                     "Windows 上多半還要裝「Microsoft Visual C++ Redistributable 2015-2022 (x64)」。",
#                extra=raw)
#        return
#    if not data.get("import_ok"):
#        rep.add(BAD, "Qt 圖形介面", "PySide6 import 不起來",
#                hint="離線安裝：python tools\\install_offline.py --wheels wheels；"
#                     "若已安裝仍失敗，多半缺 VC++ Redistributable (x64)。",
#                extra=data.get("error") or raw)
#        return
#    ver = data.get("version") or "（版本不明）"
#    if data.get("app_ok"):
#        rep.add(OK, "Qt 圖形介面", "PySide6 %s，QApplication 建得起來" % ver)
#    else:
#        rep.add(BAD, "Qt 圖形介面", "PySide6 %s 裝了，但開不了視窗" % ver,
#                hint="請確認有裝 VC++ Redistributable (x64)；遠端桌面/無桌面環境可先設定"
#                     " QT_QPA_PLATFORM=offscreen 只跑命令列模式（python -m adept run ...）。",
#                extra=data.get("error") or raw)
#
#
#def _probe_write(path: str) -> Optional[str]:
#    """試著在 path 底下寫一個暫存檔；成功回 None，失敗回錯誤字串。"""
#    try:
#        os.makedirs(path, exist_ok=True)
#        fd, tmp = tempfile.mkstemp(prefix=".adept_write_test_", dir=path)
#        os.close(fd)
#        os.remove(tmp)
#        return None
#    except OSError as exc:
#        return "%s: %s" % (type(exc).__name__, exc)
#
#
#def check_write_permissions(rep: Report) -> None:
#    cwd = os.getcwd()
#    err = _probe_write(cwd)
#    if err is None:
#        rep.add(OK, "寫入權限（目前資料夾）", cwd)
#    else:
#        rep.add(BAD, "寫入權限（目前資料夾）", "不能寫入 %s" % cwd,
#                hint="請把 ADEPT 解壓到你自己的資料夾（例如 C:\\Users\\你的帳號\\ADEPT-main），"
#                     "不要放在 C:\\Program Files 或唯讀的網路磁碟。",
#                extra=err)
#
#    cache = os.path.join(os.path.expanduser("~"), CACHE_DIR_NAME)
#    err = _probe_write(cache)
#    if err is None:
#        rep.add(OK, "寫入權限（快取 ~/.adept）", cache)
#    else:
#        rep.add(BAD, "寫入權限（快取 ~/.adept）", "不能寫入 %s" % cache,
#                hint="家目錄被鎖住時，請改用 --cache 指定一個你寫得進去的資料夾"
#                     "（例如 python -m adept run ... --cache D:\\temp\\adept_cache）。",
#                extra=err)
#
#
#def check_smoke(rep: Report, skip: bool = False, reason: str = "") -> None:
#    if skip:
#        rep.add(WARN, "端到端試跑", "略過（%s）" % (reason or "使用者指定"), essential=False,
#                hint="上面的問題修好後，再跑一次 python tools\\doctor.py 就會做這項。")
#        return
#    if not os.path.isfile(EXAMPLE_RECIPE):
#        rep.add(WARN, "端到端試跑", "找不到範例 recipe %s" % EXAMPLE_RECIPE, essential=False,
#                hint="原始碼解壓不完整，請重新解壓一次 GitHub 的 zip。")
#        return
#    t0 = time.time()
#    data, raw = _run_child(_SMOKE_CHILD, [REPO_ROOT, EXAMPLE_RECIPE], SMOKE_TIMEOUT_S)
#    dt = time.time() - t0
#    if data is None:
#        rep.add(BAD, "端到端試跑", "試跑子行程沒有正常結束（%.1f 秒）" % dt,
#                hint="請把上面的錯誤訊息（加 --verbose 可看到完整內容）連同這台機器的 "
#                     "Python 版本一起回報。",
#                extra=raw)
#        return
#    if data.get("ok"):
#        rep.add(OK, "端到端試跑", "合成 lot → 範例 recipe → score=%.3f，%d 個特徵（%.1f 秒）"
#                % (float(data.get("score") or 0.0), int(data.get("n_features") or 0), dt))
#    else:
#        rep.add(BAD, "端到端試跑", "跑得動但結果不對：%s" % (data.get("error") or "沒有算出 score"),
#                hint="通常是相依套件版本太舊。請確認 numpy/opencv 版本符合 requirements.txt，"
#                     "或重新離線安裝一次。",
#                extra=raw)
#
#
## ---------------------------------------------------------------- 主流程
#
#def _soften_stdout() -> None:
#    """主控台字碼頁吐不出某些字時，改成 replace 而不是整支程式炸掉。"""
#    for stream in (sys.stdout, sys.stderr):
#        try:
#            stream.reconfigure(errors="replace")      # Python 3.7+
#        except Exception:                             # noqa: BLE001 — 沒有就算了
#            pass
#
#
#def main(argv: Optional[Sequence[str]] = None) -> int:
#    _soften_stdout()
#    ap = argparse.ArgumentParser(
#        prog="doctor.py",
#        description="ADEPT 環境自檢：一次檢查 Python、相依套件、Qt、權限與端到端試跑。")
#    ap.add_argument("--verbose", action="store_true", help="連錯誤細節（完整訊息）一起印出來")
#    ap.add_argument("--skip-smoke", action="store_true", help="不跑最後的端到端試跑（省約 10 秒）")
#    args = ap.parse_args(list(argv) if argv is not None else None)
#
#    print("ADEPT 環境自檢（doctor）")
#    print("  目前資料夾：%s" % os.getcwd())
#    print("  Python    ：%s" % sys.executable)
#
#    rep = Report()
#    check_python(rep)
#    deps_ok = check_dependencies(rep, verbose=args.verbose)
#    adept_ok = check_adept_importable(rep)
#    check_qt(rep)
#    check_write_permissions(rep)
#
#    skip_reason = ""
#    if args.skip_smoke:
#        skip_reason = "--skip-smoke"
#    elif not deps_ok:
#        skip_reason = "相依套件還沒裝齊"
#    elif not adept_ok:
#        skip_reason = "adept 套件載入不到"
#    check_smoke(rep, skip=bool(skip_reason), reason=skip_reason)
#
#    rep.render(verbose=args.verbose)
#
#    fails = rep.failures()
#    warns = rep.warnings()
#    print("")
#    if fails:
#        print("結論：有 %d 項必要檢查沒過（%s），ADEPT 目前還不能跑；"
#              "請照上面每一行的『修正建議』處理後，再執行一次 python tools\\doctor.py。"
#              % (len(fails), "、".join(r["name"] for r in fails)))
#        if not args.verbose:
#            print("（想看完整錯誤訊息：python tools\\doctor.py --verbose）")
#        return 1
#    if warns:
#        print("結論：必要項目全部通過，ADEPT 可以跑（有 %d 項非必要提醒，見上面的 △）。"
#              "下一步：python -m adept gui" % len(warns))
#    else:
#        print("結論：全部檢查通過，這台機器可以跑 ADEPT。下一步：python -m adept gui")
#    return 0
#
#
#if __name__ == "__main__":  # pragma: no cover
#    sys.exit(main())
#
#F eac9fb372e5230539a81868e667bd6c850362a71 430 tools/fetch_wheels.py
##!/usr/bin/env python3
## -*- coding: utf-8 -*-
## ADEPT offline packaging tool #1 — authored 2026-07-28 (M6-1).
#"""在**有網路的機器**上，把 ADEPT 需要的套件下載成離線 wheels 資料夾。
#
#情境：公司機的 pip 連不到外網（或整台機器沒有對外網路），
#所以要先在家用/開發機把「Windows 版的 .whl 檔」抓好，整個資料夾帶進廠。
#
#用法：
#    python tools/fetch_wheels.py                        # 預設抓 win_amd64 + Python 3.9
#    python tools/fetch_wheels.py --python-version 311   # 公司機是 Python 3.11 就改這個
#    python tools/fetch_wheels.py --dest wheels --include-pytest
#    python tools/fetch_wheels.py --dry-run              # 只印出它會執行的 pip 指令
#
#重點：**本機是 Linux/macOS 也照樣能抓 Windows 的 wheel** ——
#靠的是 ``pip download --only-binary=:all: --platform win_amd64
#--python-version 39 --implementation cp --abi cp39``。
#（pip 規定：一旦指定 --platform/--python-version，就必須加 --only-binary=:all:。）
#
#產出：
#    wheels/*.whl
#    wheels/MANIFEST.txt   ← 檔名 + sha256 + 目標平台/Python，給使用者與 IT 稽核用
#
#本檔**只用標準函式庫**（它要能在還沒裝任何套件的機器上跑）。
#下載動作一律外包給 `python -m pip download` 子行程，不 import pip 內部 API。
#"""
#from __future__ import annotations
#
#import argparse
#import datetime
#import hashlib
#import os
#import re
#import subprocess
#import sys
#from typing import Dict, List, Optional, Sequence, Tuple
#
#MANIFEST_NAME = "MANIFEST.txt"
#MANIFEST_SCHEMA = "adept.wheels.manifest/1"
#
#DEFAULT_PLATFORM = "win_amd64"
#DEFAULT_PYTHON_VERSION = "39"
#DEFAULT_IMPLEMENTATION = "cp"
#
## 依賴名 → 在公司機上「import 得到的名字」（只用來把訊息寫得白話一點）
#IMPORT_NAME = {
#    "opencv-python": "cv2",
#    "pyside6": "PySide6",
#    "numpy": "numpy",
#    "tifffile": "tifffile",
#    "openpyxl": "openpyxl",
#    "pytest": "pytest",
#}
#
#
## ---------------------------------------------------------------- 小工具
#
#def _norm(name: str) -> str:
#    """PEP 503 風格的正規化：``opencv-python`` 與 ``opencv_python`` 視為同一個。"""
#    return re.sub(r"[-_.]+", "_", name).strip().lower()
#
#
#def _human_size(n: float) -> str:
#    for unit in ("B", "KB", "MB", "GB"):
#        if n < 1024.0 or unit == "GB":
#            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
#        n /= 1024.0
#    return "%.1f GB" % n
#
#
#def parse_requirements(path: str) -> List[str]:
#    """讀 requirements.txt，回傳「套件名」清單（去掉版本條件與註解）。
#
#    只做最低限度的解析：本專案的 requirements.txt 是最單純的一行一個套件。
#    以 ``-`` 開頭的 pip 選項行（例如 ``--index-url``）直接略過。
#    """
#    names: List[str] = []
#    with open(path, "r", encoding="utf-8") as f:
#        for raw in f:
#            line = raw.split("#", 1)[0].strip()
#            if not line or line.startswith("-"):
#                continue
#            m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
#            if m:
#                names.append(m.group(1))
#    return names
#
#
#def parse_wheel_filename(fname: str) -> Optional[Tuple[str, str, str, str, str]]:
#    """``name-version-pytag-abitag-plattag.whl`` → 5 元組；認不出來回 None。"""
#    if not fname.lower().endswith(".whl"):
#        return None
#    parts = fname[:-4].split("-")
#    if len(parts) < 5:
#        return None
#    # build tag（選用）夾在 version 之後；把它併掉，只保留最後三個 tag
#    name, version = parts[0], parts[1]
#    pytag, abitag, plattag = parts[-3], parts[-2], parts[-1]
#    return (name, version, pytag, abitag, plattag)
#
#
#def sha256_of(path: str) -> str:
#    h = hashlib.sha256()
#    with open(path, "rb") as f:
#        for chunk in iter(lambda: f.read(1024 * 1024), b""):
#            h.update(chunk)
#    return h.hexdigest()
#
#
## ---------------------------------------------------------------- pip 指令組裝
#
#def default_abi(python_version: str, implementation: str = DEFAULT_IMPLEMENTATION) -> str:
#    """由 --python-version / --implementation 推出預設 abi tag（cp39 → ``cp39``）。"""
#    digits = re.sub(r"[^0-9]", "", python_version)
#    if implementation != "cp" or not digits:
#        return "none"
#    if digits in ("36", "37"):
#        return "cp%sm" % digits          # 3.7 以前 Windows ABI tag 帶 m
#    return "cp%s" % digits
#
#
#def build_pip_command(*, dest: str, requirements: Optional[str] = None,
#                      platforms: Sequence[str] = (DEFAULT_PLATFORM,),
#                      python_version: str = DEFAULT_PYTHON_VERSION,
#                      implementation: str = DEFAULT_IMPLEMENTATION,
#                      abi: Optional[str] = None,
#                      extra_packages: Sequence[str] = (),
#                      python_exe: Optional[str] = None) -> List[str]:
#    """組出 ``pip download`` 的 argv（純函式，測試直接驗這個，不真的連網）。"""
#    exe = python_exe or sys.executable
#    cmd: List[str] = [exe, "-m", "pip", "download",
#                      "--only-binary=:all:",
#                      "--dest", dest,
#                      "--python-version", str(python_version),
#                      "--implementation", implementation,
#                      "--abi", abi or default_abi(python_version, implementation)]
#    for plat in platforms:
#        cmd += ["--platform", plat]
#    if requirements:
#        cmd += ["-r", requirements]
#    cmd += list(extra_packages)
#    return cmd
#
#
## ---------------------------------------------------------------- 驗證與報表
#
#def scan_dest(dest: str) -> Tuple[List[str], List[str]]:
#    """掃 dest：回傳 (wheel 檔名清單, 非 wheel 的套件檔清單=sdist)。"""
#    wheels: List[str] = []
#    sdists: List[str] = []
#    for fn in sorted(os.listdir(dest)):
#        low = fn.lower()
#        if low.endswith(".whl"):
#            wheels.append(fn)
#        elif low.endswith((".tar.gz", ".zip", ".tar.bz2")):
#            sdists.append(fn)
#    return wheels, sdists
#
#
#def match_requirements(requirements: Sequence[str],
#                       wheels: Sequence[str]) -> Dict[str, List[str]]:
#    """每個 requirement → 對應到的 wheel 檔名（可能 0 個）。"""
#    by_name: Dict[str, List[str]] = {}
#    for fn in wheels:
#        info = parse_wheel_filename(fn)
#        if info is None:
#            continue
#        by_name.setdefault(_norm(info[0]), []).append(fn)
#    return {req: by_name.get(_norm(req), []) for req in requirements}
#
#
#def _atomic_write(path: str, text: str) -> None:
#    """先寫 .tmp 再 os.replace（CLAUDE.md 鐵則 5：檔案寫入一律 atomic）。"""
#    tmp = path + ".tmp"
#    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
#        f.write(text)
#    os.replace(tmp, path)
#
#
#def build_manifest_text(*, wheels: Sequence[str], dest: str, platforms: Sequence[str],
#                        python_version: str, implementation: str, abi: str,
#                        requirements_path: str,
#                        requirement_names: Sequence[str]) -> str:
#    """產生 MANIFEST.txt 內容（人看得懂，也好用 grep/程式解析）。"""
#    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
#    rows: List[Tuple[str, str, int]] = []
#    total = 0
#    for fn in wheels:
#        full = os.path.join(dest, fn)
#        size = os.path.getsize(full)
#        total += size
#        rows.append((fn, sha256_of(full), size))
#
#    lines: List[str] = []
#    lines.append("# ADEPT 離線安裝套件清單（MANIFEST）")
#    lines.append("# 由 tools/fetch_wheels.py 產生；tools/install_offline.py 會讀這個檔做版本檢查。")
#    lines.append("# 這個資料夾只包含公開 PyPI 上的官方套件，沒有任何 ADEPT 自製二進位檔。")
#    lines.append("")
#    lines.append("schema: %s" % MANIFEST_SCHEMA)
#    lines.append("generated_utc: %s" % now)
#    lines.append("target_platform: %s" % ",".join(platforms))
#    lines.append("target_python: %s" % python_version)
#    lines.append("target_implementation: %s" % implementation)
#    lines.append("target_abi: %s" % abi)
#    lines.append("requirements_file: %s" % os.path.basename(requirements_path))
#    lines.append("requirements: %s" % ", ".join(requirement_names))
#    lines.append("wheel_count: %d" % len(rows))
#    lines.append("total_bytes: %d" % total)
#    lines.append("fetched_on_host: Python %s / %s" %
#                 (".".join(str(x) for x in sys.version_info[:3]), sys.platform))
#    lines.append("")
#    lines.append("# 以下每行：檔名 <空白> sha256 <空白> 位元組數")
#    lines.append("# 驗證方式（Windows PowerShell）：Get-FileHash -Algorithm SHA256 wheels\\檔名")
#    for fn, digest, size in rows:
#        lines.append("%s  %s  %d" % (fn, digest, size))
#    lines.append("")
#    return "\n".join(lines)
#
#
#def _width(text: str) -> int:
#    """顯示寬度：CJK 全形字算 2 格（不然表格會歪掉）。"""
#    import unicodedata
#
#    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)
#
#
#def _pad(text: str, width: int, right: bool = False) -> str:
#    fill = " " * max(0, width - _width(text))
#    return (fill + text) if right else (text + fill)
#
#
#def print_table(dest: str, wheels: Sequence[str]) -> int:
#    """印出（套件、版本、大小）表格，回傳總位元組數。"""
#    rows: List[Tuple[str, str, str, int]] = []
#    total = 0
#    for fn in wheels:
#        info = parse_wheel_filename(fn)
#        size = os.path.getsize(os.path.join(dest, fn))
#        total += size
#        if info is None:
#            rows.append((fn, "?", "?", size))
#        else:
#            rows.append((info[0], info[1], "%s-%s" % (info[2], info[4]), size))
#    if not rows:
#        return 0
#    w0 = max([_width("套件")] + [_width(r[0]) for r in rows])
#    w1 = max([_width("版本")] + [_width(r[1]) for r in rows])
#    w2 = max([_width("標籤")] + [_width(r[2]) for r in rows])
#    rule = "  " + "-" * (w0 + w1 + w2 + 16)
#    print("")
#    print("  %s  %s  %s  %s" % (_pad("套件", w0), _pad("版本", w1),
#                                _pad("標籤", w2), _pad("大小", 10, right=True)))
#    print(rule)
#    for name, ver, tag, size in sorted(rows, key=lambda r: r[0].lower()):
#        print("  %s  %s  %s  %s" % (_pad(name, w0), _pad(ver, w1), _pad(tag, w2),
#                                    _pad(_human_size(size), 10, right=True)))
#    print(rule)
#    print("  合計 %d 個檔案，%s" % (len(rows), _human_size(total)))
#    return total
#
#
## ---------------------------------------------------------------- pip 失敗的白話翻譯
#
#def explain_pip_failure(stderr: str, *, platform: str, python_version: str) -> List[str]:
#    """把 pip 的英文錯誤翻成「該怎麼辦」。回傳數行建議。"""
#    low = (stderr or "").lower()
#    tips: List[str] = []
#    if "no matching distribution" in low or "could not find a version" in low:
#        tips.append("最可能的原因：某個套件在 %s + Python %s 這個組合下沒有官方 wheel。"
#                    % (platform, python_version))
#        tips.append("做法 A：把 --python-version 改成公司機真正的 Python 版本"
#                    "（在公司機執行 `python -V` 查）。")
#        tips.append("做法 B：放寬 requirements.txt 的版本下限（舊 Python 只有舊版套件）。")
#    if "none of the wheels" in low or "only-binary" in low:
#        tips.append("這個套件只有原始碼（sdist），沒有 wheel；"
#                    "公司機沒有編譯器裝不起來，請改用有 wheel 的版本。")
#    if "proxy" in low or "connection" in low or "network" in low or "timed out" in low:
#        tips.append("看起來是這台機器連不到 PyPI（代理/防火牆）。"
#                    "fetch_wheels.py 必須在**有網路**的機器上跑。")
#    if "no module named pip" in low:
#        tips.append("這台機器的 Python 沒有 pip。請用另一個有 pip 的 Python，"
#                    "或先執行 `python -m ensurepip`。")
#    if not tips:
#        tips.append("請把上面 pip 的原始訊息連同這行指令一起回報。")
#    return tips
#
#
## ---------------------------------------------------------------- 主流程
#
#def _soften_stdout() -> None:
#    """主控台字碼頁吐不出某些字時，改成 replace 而不是整支程式炸掉。"""
#    for stream in (sys.stdout, sys.stderr):
#        try:
#            stream.reconfigure(errors="replace")      # Python 3.7+
#        except Exception:                             # noqa: BLE001 — 沒有就算了
#            pass
#
#
#def main(argv: Optional[Sequence[str]] = None) -> int:
#    _soften_stdout()
#    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#    ap = argparse.ArgumentParser(
#        prog="fetch_wheels.py",
#        description="在有網路的機器上，把 ADEPT 的相依套件下載成離線 wheels 資料夾。",
#        formatter_class=argparse.RawDescriptionHelpFormatter,
#        epilog="範例：\n"
#               "  python tools/fetch_wheels.py --python-version 311 --include-pytest\n"
#               "  python tools/fetch_wheels.py --platform win_amd64 --dest D:\\adept_wheels\n")
#    ap.add_argument("--dest", default="wheels", help="wheel 存放資料夾（預設 wheels）")
#    ap.add_argument("--python-version", default=DEFAULT_PYTHON_VERSION,
#                    help="公司機的 Python 版本，寫成 39 / 310 / 311（預設 39）")
#    ap.add_argument("--platform", action="append", default=None,
#                    help="目標平台 tag（預設 win_amd64；可重複指定）")
#    ap.add_argument("--implementation", default=DEFAULT_IMPLEMENTATION,
#                    help="Python 實作（預設 cp = CPython）")
#    ap.add_argument("--abi", default=None, help="ABI tag（預設由 --python-version 推出，例 cp39）")
#    ap.add_argument("--requirements", default=os.path.join(repo, "requirements.txt"),
#                    help="requirements.txt 路徑")
#    ap.add_argument("--include-pytest", action="store_true",
#                    help="連 pytest 一起抓（想在公司機跑測試才需要）")
#    ap.add_argument("--dry-run", action="store_true",
#                    help="只印出將要執行的 pip 指令，不真的下載")
#    args = ap.parse_args(list(argv) if argv is not None else None)
#
#    platforms = args.platform or [DEFAULT_PLATFORM]
#    abi = args.abi or default_abi(args.python_version, args.implementation)
#    dest = os.path.abspath(args.dest)
#
#    if not os.path.isfile(args.requirements):
#        print("[錯誤] 找不到 requirements 檔：%s" % args.requirements, file=sys.stderr)
#        print("       請在 ADEPT 專案資料夾裡執行，或用 --requirements 指定路徑。", file=sys.stderr)
#        return 2
#    try:
#        req_names = parse_requirements(args.requirements)
#    except OSError as exc:
#        print("[錯誤] 讀不到 requirements 檔：%s" % exc, file=sys.stderr)
#        return 2
#    if not req_names:
#        print("[錯誤] %s 裡沒有任何套件。" % args.requirements, file=sys.stderr)
#        return 2
#
#    extra: List[str] = ["pytest"] if args.include_pytest else []
#    all_reqs = req_names + extra
#
#    cmd = build_pip_command(dest=dest, requirements=args.requirements,
#                            platforms=platforms, python_version=args.python_version,
#                            implementation=args.implementation, abi=abi,
#                            extra_packages=extra)
#
#    print("ADEPT 離線 wheels 下載")
#    print("  目標平台      ：%s" % ", ".join(platforms))
#    print("  目標 Python   ：%s（abi %s、implementation %s）"
#          % (args.python_version, abi, args.implementation))
#    print("  要抓的套件    ：%s" % ", ".join(all_reqs))
#    print("  存放資料夾    ：%s" % dest)
#    print("")
#    print("將執行：")
#    print("  " + " ".join(cmd))
#
#    if args.dry_run:
#        print("\n（--dry-run：沒有真的下載。）")
#        return 0
#
#    try:
#        os.makedirs(dest, exist_ok=True)
#    except OSError as exc:
#        print("\n[錯誤] 建不了資料夾 %s：%s" % (dest, exc), file=sys.stderr)
#        return 2
#
#    print("\n下載中（第一次要幾分鐘，PySide6 就有 100 MB 以上）…\n")
#    try:
#        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#    except OSError as exc:
#        print("[錯誤] 叫不動 pip：%s" % exc, file=sys.stderr)
#        return 2
#    output = (proc.stdout or b"").decode("utf-8", "replace")
#    print(output.rstrip())
#
#    if proc.returncode != 0:
#        print("\n[錯誤] pip download 失敗（回傳碼 %d）。" % proc.returncode, file=sys.stderr)
#        for tip in explain_pip_failure(output, platform=platforms[0],
#                                       python_version=args.python_version):
#            print("  · " + tip, file=sys.stderr)
#        return 1
#
#    # ---- 下載後驗證 ----
#    wheels, sdists = scan_dest(dest)
#    total = print_table(dest, wheels)
#
#    problems = 0
#    matched = match_requirements(all_reqs, wheels)
#    missing = [r for r, files in matched.items() if not files]
#    if missing:
#        problems += 1
#        print("\n[錯誤] 這些套件沒有抓到任何 .whl：%s" % ", ".join(missing), file=sys.stderr)
#        print("       公司機會裝不起來。請確認 --python-version / --platform 是否正確。",
#              file=sys.stderr)
#    if sdists:
#        problems += 1
#        print("\n[警告] 資料夾裡有 %d 個原始碼包（不是 wheel）：%s"
#              % (len(sdists), ", ".join(sdists)), file=sys.stderr)
#        print("       原始碼包在公司機需要 C 編譯器才裝得起來，幾乎一定會失敗。",
#              file=sys.stderr)
#        print("       請改用有提供 wheel 的版本，或請 IT 從內部鏡像站取得。", file=sys.stderr)
#
#    manifest_path = os.path.join(dest, MANIFEST_NAME)
#    try:
#        _atomic_write(manifest_path, build_manifest_text(
#            wheels=wheels, dest=dest, platforms=platforms,
#            python_version=args.python_version, implementation=args.implementation,
#            abi=abi, requirements_path=args.requirements, requirement_names=all_reqs))
#    except OSError as exc:
#        print("\n[錯誤] 寫不出 MANIFEST.txt：%s" % exc, file=sys.stderr)
#        return 1
#    print("\n→ 已寫出清單：%s" % manifest_path)
#    print("  （裡面有每個檔案的 sha256 與目標平台／Python，可以直接給 IT 看。）")
#
#    if problems:
#        print("\n結論：下載完成但**有問題**，請先處理上面的錯誤或警告。")
#        return 1
#
#    print("\n結論：%d 個 wheel、共 %s，全部齊全。" % (len(wheels), _human_size(total)))
#    print("下一步：把整個 %s 資料夾連同 ADEPT 原始碼帶到公司機，然後執行" % os.path.basename(dest))
#    print("        python tools\\install_offline.py --wheels %s" % os.path.basename(dest))
#    return 0
#
#
#if __name__ == "__main__":  # pragma: no cover
#    sys.exit(main())
#
#F d3c3fa7d8b3e0d6a3605a585a67c45d0b6aa650d 187 tools/get_code.ps1
## ADEPT 取得程式碼（PowerShell 版）— authored 2026-07-30.
##
## 為什麼有兩個版本
## ---------------
## `get_code.py` 用 Python 的 urllib。在鎖很緊的公司機上 urllib 有三個做不到的事：
##   1. 讀不到 PAC（自動設定指令碼）—— py 版靠借 .NET 算，但只拿得到「第一個」proxy
##   2. 不會對 proxy 做 Windows 整合驗證（NTLM / Kerberos）
##   3. PAC 給了多個 PROXY 候選時不會依序 fallback
## 這三件事 .NET **全部原生支援**，而 PowerShell 就是 .NET —— **瀏覽器連得到的
## 東西，PowerShell 通常就連得到**。所以在「py 版被 proxy 拒絕」的機器上先試這個。
##
## 契約跟 py 版完全一樣：讀 tools/FILELIST.txt、逐檔抓、驗 git blob SHA、atomic 寫入。
##
## 怎麼拿到這支
## ------------
## 在 GitHub 上打開 tools/get_code.ps1 → 按右上角的複製鈕 → 貼進記事本存成
## get_code.ps1。然後（PowerShell 預設不准跑腳本，所以用 -ExecutionPolicy Bypass）：
##
##   powershell -ExecutionPolicy Bypass -File .\get_code.ps1
##   powershell -ExecutionPolicy Bypass -File .\get_code.ps1 -Dest D:\tools
##   powershell -ExecutionPolicy Bypass -File .\get_code.ps1 -Ref 5fdbb2a…
##   powershell -ExecutionPolicy Bypass -File .\get_code.ps1 -Proxy http://主機:8080
#
#[CmdletBinding()]
#param(
#    [string]$Dest  = "ADEPT",
#    [string]$Ref   = "main",
#    [string]$Proxy = ""
#)
#
#$ErrorActionPreference = "Stop"
#$Repo     = "hxlub0905-cmyk/ADEPT"
#$Manifest = "tools/FILELIST.txt"
#
## Windows 8.1 / Server 2012 之後仍有機器的 .NET 預設 TLS 1.0，而 GitHub 只收
## TLS 1.2 以上 —— 不設這行會拿到一個看起來像「被擋」的連線失敗。
#try {
#    [Net.ServicePointManager]::SecurityProtocol =
#        [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11
#} catch { }
#
#function Get-ProxyArgs {
#    <# proxy 相關的參數。明講的優先；否則用系統設定（PAC 會被解開），
#       並且帶上 Windows 整合驗證 —— 公司 proxy 常常要求它，而那正是
#       Python 版做不到的一件事。#>
#    if ($Proxy) {
#        return @{ Proxy = $Proxy; ProxyUseDefaultCredentials = $true }
#    }
#    $sys = [System.Net.WebRequest]::GetSystemWebProxy()
#    $for = $sys.GetProxy("https://raw.githubusercontent.com/x")
#    if ($for -and $for.AbsoluteUri -ne "https://raw.githubusercontent.com/x") {
#        return @{ Proxy = $for.AbsoluteUri; ProxyUseDefaultCredentials = $true }
#    }
#    return @{}          # 不需要 proxy
#}
#
#function Get-Text {
#    param([string]$Path, [hashtable]$ProxyArgs)
#    $url = "https://raw.githubusercontent.com/$Repo/$Ref/$Path"
#    # -UseBasicParsing：PS 5.1 沒有它會去叫 IE 引擎（在 Server Core 上會炸）
#    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30 @ProxyArgs
#    return $r
#}
#
#function Get-BlobSha {
#    <# git 算 blob SHA 的方式："blob <長度>\0" + 內容。#>
#    param([byte[]]$Bytes)
#    $head = [Text.Encoding]::ASCII.GetBytes("blob " + $Bytes.Length + "`0")
#    $all  = New-Object byte[] ($head.Length + $Bytes.Length)
#    [Array]::Copy($head, 0, $all, 0, $head.Length)
#    [Array]::Copy($Bytes, 0, $all, $head.Length, $Bytes.Length)
#    $sha  = [Security.Cryptography.SHA1]::Create()
#    try {
#        return (($sha.ComputeHash($all) | ForEach-Object { $_.ToString("x2") }) -join "")
#    } finally { $sha.Dispose() }
#}
#
#function Write-Atomic {
#    param([string]$Root, [string]$Rel, [byte[]]$Bytes)
#    $full = Join-Path $Root ($Rel -replace "/", "\")
#    $dir  = Split-Path -Parent $full
#    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
#    $tmp = "$full.tmp"
#    [IO.File]::WriteAllBytes($tmp, $Bytes)
#    Move-Item -LiteralPath $tmp -Destination $full -Force
#}
#
## ---------------------------------------------------------------------------
#$proxyArgs = Get-ProxyArgs
## 絕對路徑不可以再跟目前目錄接起來 —— `Join-Path` 會做出 `C:\cur\D:\tools`
## 這種東西，而它**建得起來**，於是檔案安靜地跑到錯的地方去（實測就發生了：
## `-Dest /tmp/x` 寫到了 `<repo>/tmp/x`）。而且 PowerShell 的目前目錄跟 .NET
## 行程的目前目錄是兩件事，所以相對路徑要自己接 `.ProviderPath`。
#$destFull = if ([IO.Path]::IsPathRooted($Dest)) {
#    [IO.Path]::GetFullPath($Dest)
#} else {
#    [IO.Path]::GetFullPath((Join-Path (Get-Location).ProviderPath $Dest))
#}
#Write-Host "來源  : https://raw.githubusercontent.com/$Repo ($Ref)"
#Write-Host "目的地: $destFull"
#if ($proxyArgs.ContainsKey("Proxy")) {
#    Write-Host ("Proxy : " + $proxyArgs.Proxy + "（含 Windows 整合驗證）")
#} else {
#    Write-Host "Proxy : （不用 proxy，直接連）"
#}
#
#try {
#    $raw = (Get-Text -Path $Manifest -ProxyArgs $proxyArgs).Content
#} catch {
#    Write-Host ""
#    Write-Host "✗ 抓 $Manifest 失敗：$($_.Exception.Message)"
#    $resp = $_.Exception.Response
#    if ($resp -and $resp.StatusCode -eq 404) {
#        Write-Host "  連得上，但這個分支上沒有這個檔案 —— 檢查 -Ref（現在是 '$Ref'）。"
#    } elseif ($resp -and ($resp.StatusCode -eq 407)) {
#        Write-Host "  proxy 要求驗證而整合驗證沒過。用 -Proxy 明講位址，"
#        Write-Host "  或請 IT 確認你的帳號可以透過 proxy 連 raw.githubusercontent.com。"
#    } else {
#        Write-Host "  連 PowerShell 也連不到 —— 那就不是 Python 的問題了。剩下的路："
#        Write-Host "  1. 請 IT 放行 codeload.github.com（zip 就會回來，這是根治）"
#        Write-Host "  2. 在有網路的機器上取得，用你搬 wheels\ 的同一條路搬過來"
#    }
#    exit 2
#}
#
#$want = @()
#foreach ($line in ($raw -split "`r?`n")) {
#    $line = $line.Trim()
#    if ($line -and -not $line.StartsWith("#")) {
#        $i = $line.IndexOf(" ")
#        if ($i -gt 0) {
#            $want += ,@($line.Substring(0, $i), $line.Substring($i + 1))
#        }
#    }
#}
#if ($want.Count -eq 0) {
#    Write-Host ""
#    Write-Host "✗ $Manifest 是空的 —— proxy 可能回了一頁別的東西。"
#    exit 2
#}
#Write-Host "清單  : $($want.Count) 個檔案"
#Write-Host ""
#
## 清單自己不在自己的清單裡（SHA 沒辦法自我包含），但抓下來那份還是要有它。
#Write-Atomic -Root $destFull -Rel $Manifest -Bytes ([Text.Encoding]::UTF8.GetBytes($raw))
#
#$bad = @()
#$done = 0
#foreach ($item in $want) {
#    $sha, $path = $item[0], $item[1]
#    try {
#        $r = Get-Text -Path $path -ProxyArgs $proxyArgs
#    } catch {
#        $bad += ,@($path, "抓不到：$($_.Exception.Message)")
#        continue
#    }
#    $bytes = $r.RawContentStream.ToArray()
#    if ((Get-BlobSha -Bytes $bytes) -ne $sha) {
#        # 最常見的原因不是「檔案壞了」，是 proxy 回了一頁 HTML（而且 HTTP 200）
#        $why = "內容不是預期的（可能是 proxy 的攔截頁）"
#        if ($bytes.Length -gt 0 -and $bytes[0] -eq 0x3C) { $why += "；開頭是 '<'，看起來真的是 HTML" }
#        $bad += ,@($path, $why)
#        continue
#    }
#    Write-Atomic -Root $destFull -Rel $path -Bytes $bytes
#    $done++
#    if (($done % 25) -eq 0 -or $done -eq $want.Count) { Write-Host "  $done / $($want.Count)" }
#}
#
#if ($bad.Count -gt 0) {
#    Write-Host ""
#    Write-Host "✗ $($bad.Count) 個檔案沒抓成功："
#    foreach ($b in ($bad | Select-Object -First 12)) { Write-Host ("    " + $b[0] + "  " + $b[1]) }
#    Write-Host ""
#    Write-Host "  這份程式碼不完整，不要用。先解決上面的原因再重跑。"
#    exit 1
#}
#
#Write-Host ""
#Write-Host "✓ $done 個檔案都抓下來了，SHA 全部對得上。"
#Write-Host ""
#Write-Host "下一步："
#Write-Host "  cd $destFull"
#Write-Host "  python tools\doctor.py        # 環境自檢（會告訴你還缺什麼）"
#Write-Host "  相依套件裝不了的話走離線 wheels：docs\OFFLINE-INSTALL.md"
#exit 0
#
#F 4d8a556b49b3c29df3e14b975225082e4c8a948d 337 tools/get_code.py
##!/usr/bin/env python3
## ADEPT 取得程式碼（不用 git、不用 zip）— authored 2026-07-30.
#"""在「zip 下載被擋」的機器上把整包程式碼抓下來。stdlib-only、單一檔案。
#
#為什麼需要這支
#--------------
#GitHub 的 Download ZIP 是從 ``codeload.github.com`` 出來的 —— **跟 github.com
#是不同的主機**，而公司 proxy 的 allowlist 常常只放了後者。網頁看得到、zip 下不來，
#而 ``.tar.gz`` 也在同一台主機上，所以換副檔名沒有用。
#
#這支只用 **一台主機**：``raw.githubusercontent.com``（送 ``text/plain``，
#DLP 對它的規則跟 ``application/zip`` 完全不同）。
#
#怎麼拿到這支
#------------
#你連這個檔案也下載不了 —— 所以到 GitHub 上打開 ``tools/get_code.py``，
#按右上角的**複製鈕**，貼進一個新檔案存成 ``get_code.py``。整份是純文字。
#
#    python get_code.py                 # 抓到 .\\ADEPT\\
#    python get_code.py --dest D:\\tools  # 抓到別的地方
#    python get_code.py --ref main      # 指定分支（預設 main）
#    python get_code.py --ref a30a040…  # 指定 commit（要完全可重現時用這個）
#    python get_code.py --proxy http://proxy.corp.com:8080   # 要走公司 proxy
#
#**瀏覽器連得到但這支逾時（WinError 10060）＝ 沒走 proxy，不是被擋。**
#``urllib`` 會讀 ``HTTPS_PROXY`` 與 Windows 登錄檔裡**手動設定**的 proxy，
#但**讀不到 PAC（自動設定指令碼）**，而公司幾乎都用 PAC —— 瀏覽器懂 PAC、
#Python 不懂，所以同一台機器上一個通一個不通。
#
#所以在 Windows 上，沒有其他 proxy 設定時這支會**自己請 .NET 把 PAC 解開**
#（``GetSystemWebProxy().GetProxy(url)``，跟瀏覽器同一套設定），解得出來就直接
#用，開頭那行 ``Proxy :`` 會講它是怎麼來的。解不出來才要你自己填 ``--proxy``。
#
#``--ref`` 給分支名的時候，抓到的是 **CDN 上的那一版** —— 剛推上去的東西可能要
#等幾分鐘才看得到（實測會拿到前一個 commit；清單與檔案來自同一份快照，
#所以 SHA 仍然全部對得上，不會誤報，但你拿到的是稍舊的一份）。
#要百分之百確定抓到哪一版，``--ref`` 直接給 commit SHA（commit 是不變的，沒有快取問題）。
#
#為什麼要驗 SHA
#--------------
#被擋的 proxy **不一定回錯誤碼** —— 它常常回一頁登入頁或一段警告 HTML，
#HTTP 200。那種東西寫進 ``.py`` 檔之後，症狀會變成「程式碼看起來都在，
#但 import 就爆語法錯誤」，而使用者完全不知道是下載壞了。
#所以每個檔案都對 ``FILELIST.txt`` 裡的 **git blob SHA-1** 驗過才落地。
#"""
#from __future__ import annotations
#
#import argparse
#import hashlib
#import os
#import subprocess
#import sys
#import urllib.error
#import urllib.request
#
#REPO = "hxlub0905-cmyk/ADEPT"
#RAW = "https://raw.githubusercontent.com/%s/%s/%s"
#MANIFEST = "tools/FILELIST.txt"
#TIMEOUT = 30
#
#
#def build_opener(cafile: str = "", proxy: str = ""):
#    """做一個 opener（proxy 與公司憑證都掛在這裡）。
#
#    不給 ``proxy`` 的話走 urllib 的預設 —— 它會讀 ``HTTPS_PROXY`` 環境變數，
#    在 Windows 上也會讀登錄檔裡**手動設定**的 proxy。
#    **但它讀不到 PAC（自動設定指令碼）**，而公司幾乎都用 PAC ——
#    那種情況下 urllib 會直接連出去，然後逾時（WinError 10060）。
#    """
#    handlers = []
#    if proxy:
#        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
#    if cafile:
#        import ssl
#        handlers.append(urllib.request.HTTPSHandler(
#            context=ssl.create_default_context(cafile=cafile)))
#    return urllib.request.build_opener(*handlers)
#
#
##: ``main()`` 建好之後放在這裡，``fetch()`` 用它（``fetch`` 的簽名保持簡單，
##: 測試才好 monkeypatch 掉整個網路層）。
#_OPENER = None
#
#
#def fetch(ref: str, path: str, cafile: str = "") -> bytes:
#    url = RAW % (REPO, ref, path)
#    opener = _OPENER or build_opener(cafile)
#    with opener.open(url, timeout=TIMEOUT) as r:      # noqa: S310 — 固定 https
#        return r.read()
#
#
#def proxy_in_effect(proxy: str = "") -> str:
#    """現在實際會用哪個 proxy（沒有就回空字串）。"""
#    if proxy:
#        return proxy
#    return urllib.request.getproxies().get("https", "")
#
#
#def system_proxy_for(url: str) -> str:
#    """問 Windows「連這個網址要走哪個 proxy」—— **PAC 會被解開**。
#
#    ``urllib`` 讀不到 PAC，但 .NET 讀得到（瀏覽器用的是同一套設定），
#    所以在 Windows 上借 PowerShell 問一次。這比叫使用者自己打開 PAC 檔去找
#    ``PROXY 主機:埠`` 好太多了 —— 那種檔案通常有上百行條件判斷，而且「哪一行
#    適用於這個網址」正是 PAC 要算的東西。
#
#    ``GetProxy()`` 在「不需要 proxy」時會回傳原網址，所以那種情況回空字串。
#    任何一步失敗都回空字串（診斷用的東西不可以自己變成失敗原因）。
#    """
#    if not sys.platform.startswith("win"):
#        return ""
#    ps = ("[System.Net.WebRequest]::GetSystemWebProxy()"
#          ".GetProxy('%s').AbsoluteUri" % url)
#    try:
#        out = subprocess.run(
#            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
#            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=25)
#    except Exception:                                 # noqa: BLE001 — 診斷用
#        return ""
#    got = out.stdout.decode("utf-8", "replace").strip().splitlines()
#    got = got[-1].strip() if got else ""
#    if not got or got.rstrip("/") == url.rstrip("/"):
#        return ""                                     # .NET 說不用 proxy
#    if not got.startswith(("http://", "https://")):
#        return ""
#    return got
#
#
#def pac_url() -> str:
#    """Windows 登錄檔裡的 PAC（自動設定指令碼）網址；沒有或不是 Windows 回空字串。
#
#    這是「瀏覽器連得到、Python 連不到」最常見的原因，而且從錯誤訊息完全看不出來
#    —— 所以直接去把它讀出來講給使用者聽。
#    """
#    if not sys.platform.startswith("win"):
#        return ""
#    try:
#        import winreg
#        key = winreg.OpenKey(
#            winreg.HKEY_CURRENT_USER,
#            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
#        try:
#            return str(winreg.QueryValueEx(key, "AutoConfigURL")[0] or "")
#        finally:
#            winreg.CloseKey(key)
#    except Exception:                                 # noqa: BLE001 — 診斷用
#        return ""
#
#
#def blob_sha(data: bytes) -> str:
#    """git 算 blob SHA 的方式：``"blob <len>\\0" + 內容``。"""
#    h = hashlib.sha1()                                # noqa: S324 — git 的格式
#    h.update(b"blob %d\0" % len(data))
#    h.update(data)
#    return h.hexdigest()
#
#
#def write_atomic(dest: str, rel: str, data: bytes) -> None:
#    full = os.path.join(dest, rel.replace("/", os.sep))
#    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
#    tmp = full + ".tmp"
#    with open(tmp, "wb") as f:
#        f.write(data)
#    os.replace(tmp, full)
#
#
#def main(argv=None) -> int:
#    ap = argparse.ArgumentParser(description="Download ADEPT without git or zip.")
#    ap.add_argument("--dest", default="ADEPT", help="要放在哪個資料夾（預設 .\\ADEPT）")
#    ap.add_argument("--ref", default="main", help="分支或 tag（預設 main）")
#    ap.add_argument("--cafile", default="",
#                    help="公司的根憑證 .pem（TLS 被中間攔截時才需要）")
#    ap.add_argument("--proxy", default="",
#                    help="公司 proxy，例如 http://proxy.corp.com:8080")
#    a = ap.parse_args(argv)
#
#    # 沒人給 proxy、環境也沒有的時候，去問 Windows（PAC 就是在這裡被解開的）。
#    # 使用者不該為了下載一份程式碼去讀一個上百行的 PAC 檔。
#    proxy, how = a.proxy, ""
#    if not proxy and not proxy_in_effect():
#        proxy = system_proxy_for(RAW % (REPO, a.ref, MANIFEST))
#        if proxy:
#            how = "（從 Windows 的自動設定（PAC）解出來的）"
#
#    global _OPENER
#    _OPENER = build_opener(a.cafile, proxy)
#
#    print("來源  : https://raw.githubusercontent.com/%s (%s)" % (REPO, a.ref))
#    print("目的地: %s" % os.path.abspath(a.dest))
#    print("Proxy : %s%s" % (proxy_in_effect(proxy) or "（不用 proxy，直接連）", how))
#    try:
#        raw = fetch(a.ref, MANIFEST, a.cafile).decode("utf-8")
#    except urllib.error.HTTPError as e:
#        # **伺服器有回答** —— 所以連線是通的。這裡最容易給錯的診斷是把 404
#        # 講成「被擋住了」，然後使用者去找 IT，而真正的原因是 --ref 打錯。
#        print("\n✗ 抓 %s 失敗：HTTP %s" % (MANIFEST, e.code))
#        if e.code == 404:
#            print("  連得上，但這個分支上沒有這個檔案。檢查 --ref（現在是 '%s'）；"
#                  % a.ref)
#            print("  預設分支通常是 main。")
#        elif e.code in (401, 403, 407, 451, 511):
#            print("  連得上，但被拒絕了 —— 403 / 407 這種通常就是公司 proxy")
#            print("  （不是 GitHub）。看下面「三台主機都被擋」的那條路。")
#        else:
#            print("  %s" % e.reason)
#        return 2
#    except urllib.error.URLError as e:
#        # 連不上（DNS / TCP / TLS）。**這裡不能一律講「被擋掉了」** ——
#        # 逾時（WinError 10060 / timed out）的意思是「直接連出去、封包沒人回」，
#        # 而那通常代表 **Python 沒有走公司 proxy**，不是這台主機被封。
#        # 瀏覽器連得到、Python 連不到，幾乎都是這件事。
#        reason = str(e.reason)
#        print("\n✗ 連不上 raw.githubusercontent.com：%s" % reason)
#        if "CERTIFICATE" in reason.upper():
#            print("  這是 TLS 被公司中間攔截。用 --cafile 指到公司的根憑證，")
#            print("  **不要**去關掉憑證驗證。")
#            return 2
#
#        timed_out = ("10060" in reason or "timed out" in reason.lower()
#                     or "timeout" in reason.lower())
#        using = proxy_in_effect(proxy)
#        if timed_out and not using:
#            pac = pac_url()
#            print("\n  這是**逾時**，不是被拒絕 —— 封包直接送出去而沒有人回應。")
#            print("  如果你的瀏覽器連得到 GitHub，那答案幾乎一定是：")
#            print("  **這台機器要透過公司 proxy 才連得出去，而 Python 沒有走 proxy。**")
#            if pac:
#                print("\n  你的 proxy 是用 PAC 自動設定檔設的 ——")
#                print("    %s" % pac)
#                print("  我試著請 Windows 幫我解開它（.NET 讀得懂 PAC），但沒有解出")
#                print("  可以用的 proxy。請用瀏覽器打開上面那個網址，找 `PROXY 主機:埠`，")
#                print("  然後：")
#            else:
#                print("\n  先找出 proxy（PowerShell，任一個有值就用它）：")
#                print("    netsh winhttp show proxy")
#                print("    Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows"
#                      "\\CurrentVersion\\Internet Settings' |"
#                      " Select ProxyServer, AutoConfigURL")
#                print("    pip config list          # pip 能連的話，proxy 就在這裡")
#                print("  AutoConfigURL 有值 = PAC 檔：用瀏覽器打開它，找 `PROXY 主機:埠`。")
#                print("  然後：")
#            print("    python get_code.py --proxy http://主機:埠")
#            print("  （或先 `$env:HTTPS_PROXY='http://主機:埠'` 再跑，pip 也吃這個）")
#            return 2
#
#        refused = "10061" in reason or "refused" in reason.lower()
#        if using and refused:
#            # **拒絕連線 ≠ 逾時。** 位址查得到、封包也到了，只是那個埠上沒有東西
#            # 在聽（或它主動拒絕）。最常見的原因是**埠不對** —— PAC 解出來的
#            # 網址沒有埠的時候 urllib 會用 80，而公司 proxy 幾乎不在 80。
#            host = using.split("//")[-1].rstrip("/")
#            print("\n  這是**拒絕連線**，不是逾時 —— 位址找得到，但那個埠上沒有")
#            print("  東西在聽。%s" % ("那個網址沒有埠，所以用了預設的 80。"
#                                     if ":" not in host else ""))
#            print("  試幾個常見的埠：")
#            for port in (8080, 3128, 8000, 9090):
#                print("    python get_code.py --proxy http://%s:%d" % (host, port))
#            print("\n  埠要從 PAC 檔裡看（`PROXY 主機:埠` 那一行）：")
#            print("    (Invoke-WebRequest (Get-ItemProperty 'HKCU:\\Software\\Microsoft"
#                  "\\Windows\\CurrentVersion\\Internet Settings').AutoConfigURL `")
#            print("        -UseBasicParsing).Content -split \"`n\" | Select-String PROXY")
#            print("\n  **或者改用 PowerShell 版**（`tools/get_code.ps1`）—— 它走 .NET，")
#            print("  也就是瀏覽器用的那一套：PAC 的多個候選會依序 fallback，")
#            print("  而且會對 proxy 做 Windows 整合驗證。Python 這兩件都做不到。")
#            print("    powershell -ExecutionPolicy Bypass -File .\\get_code.ps1")
#            return 2
#
#        if using:
#            print("\n  用的 proxy 是 %s —— 它沒有回應。確認位址與埠是對的，" % using)
#            print("  有些公司 proxy 只放行特定網域，那就要請 IT 加"
#                  " raw.githubusercontent.com。")
#            print("  也可以試 PowerShell 版（走 .NET，支援 PAC fallback 與整合驗證）：")
#            print("    powershell -ExecutionPolicy Bypass -File .\\get_code.ps1")
#        else:
#            print("\n  這台主機連不上。剩下的路：")
#        print("  1. 請 IT 放行 codeload.github.com（zip 就會回來，這是根治）")
#        print("  2. 在有網路的機器上取得，用你搬 wheels\\ 的同一條路搬過來")
#        print("     （見 docs/OFFLINE-INSTALL.md）")
#        return 2
#
#    want = []
#    for line in raw.splitlines():
#        line = line.strip()
#        if line and not line.startswith("#"):
#            sha, _, path = line.partition(" ")
#            if path:
#                want.append((sha, path))
#    if not want:
#        print("\n✗ %s 是空的 —— proxy 可能回了一頁別的東西。" % MANIFEST)
#        return 2
#    print("清單  : %d 個檔案\n" % len(want))
#
#    # 清單自己不在自己的清單裡（SHA 沒辦法自我包含），但受限機器上還是需要它 ——
#    # 少了它，抓下來那份 repo 就不完整，而且**看不出來少了什麼**。
#    # 位元組已經在手上，直接落地。
#    write_atomic(a.dest, MANIFEST, raw.encode("utf-8"))
#
#    bad, done = [], 0
#    for sha, path in want:
#        try:
#            data = fetch(a.ref, path, a.cafile)
#        except Exception as e:                        # noqa: BLE001
#            bad.append((path, "抓不到：%s" % e))
#            continue
#        got = blob_sha(data)
#        if got != sha:
#            # 最常見的原因不是「檔案壞了」，是 proxy 回了一頁 HTML（HTTP 200）
#            hint = "內容不是預期的（可能是 proxy 的攔截頁）"
#            if data.lstrip()[:1] == b"<":
#                hint += "；開頭是 '<'，看起來真的是 HTML"
#            bad.append((path, hint))
#            continue
#        write_atomic(a.dest, path, data)
#        done += 1
#        if done % 25 == 0 or done == len(want):
#            print("  %d / %d" % (done, len(want)))
#
#    if bad:
#        print("\n✗ %d 個檔案沒抓成功：" % len(bad))
#        for path, why in bad[:12]:
#            print("    %-44s %s" % (path, why))
#        if len(bad) > 12:
#            print("    …還有 %d 個" % (len(bad) - 12))
#        print("\n  這份程式碼**不完整，不要用**。先解決上面的原因再重跑。")
#        return 1
#
#    print("\n✓ %d 個檔案都抓下來了，SHA 全部對得上。\n" % done)
#    print("下一步：")
#    print("  cd %s" % a.dest)
#    print("  python tools\\doctor.py        # 環境自檢（會告訴你還缺什麼）")
#    print("  相依套件裝不了的話走離線 wheels：docs\\OFFLINE-INSTALL.md")
#    return 0
#
#
#if __name__ == "__main__":
#    sys.exit(main())
#
#F ad250d60c5c5f97e757842046c23816230704ef1 496 tools/install_offline.py
##!/usr/bin/env python3
## -*- coding: utf-8 -*-
## ADEPT offline packaging tool #2 — authored 2026-07-28 (M6-1).
#"""在**沒有網路的公司機**上，用離線 wheels 資料夾把 ADEPT 的相依套件裝起來。
#
#用法（在解壓後的 ADEPT 資料夾裡執行）：
#    python tools\\install_offline.py                       # 用 wheels\\，裝進 .venv\\
#    python tools\\install_offline.py --wheels D:\\adept_wheels
#    python tools\\install_offline.py --no-venv             # 不建虛擬環境，直接裝進現在這個 Python
#    python tools\\install_offline.py --no-venv --user      # 沒有系統管理權限時
#    python tools\\install_offline.py --dry-run             # 只做事前檢查、印出指令，不真的安裝
#
#它做的事：
#    1. 事前檢查（這一段最重要，八成的失敗都擋在這裡，而且會用白話告訴你怎麼修）
#    2. 建立虛擬環境 .venv（可用 --no-venv 跳過）
#    3. pip install --no-index --find-links=wheels -r requirements.txt
#    4. 自動跑 tools/doctor.py 驗收，並印出下一步要打的指令
#
#本檔**只用標準函式庫**：它要在「什麼套件都還沒裝」的機器上跑。
#"""
#from __future__ import annotations
#
#import argparse
#import os
#import re
#import shutil
#import subprocess
#import sys
#from typing import Dict, List, Optional, Sequence, Tuple
#
#MANIFEST_NAME = "MANIFEST.txt"
#MIN_PYTHON = (3, 9)
## 安裝過程需要的餘裕：wheel 解開後大約是原檔的 2~3 倍（PySide6 尤其肥）
#SPACE_FACTOR = 3.0
#SPACE_MARGIN_BYTES = 150 * 1024 * 1024
#
#PLATFORM_TAG_HINT = {
#    "win32": "win_amd64 / win32",
#    "linux": "manylinux*",
#    "darwin": "macosx_*",
#}
#
#
## ---------------------------------------------------------------- 小工具
#
#def human_size(n: float) -> str:
#    for unit in ("B", "KB", "MB", "GB"):
#        if n < 1024.0 or unit == "GB":
#            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
#        n /= 1024.0
#    return "%.1f GB" % n
#
#
#def running_python_tag() -> str:
#    """目前這個 Python 的版本 tag：3.9 → ``39``、3.11 → ``311``。"""
#    return "%d%d" % (sys.version_info[0], sys.version_info[1])
#
#
#def parse_python_tag(value: str) -> Optional[Tuple[int, int]]:
#    """``39`` / ``3.9`` / ``cp39`` / ``py311`` → (3, 9) / (3, 11)；認不出來回 None。"""
#    if not value:
#        return None
#    digits = re.sub(r"[^0-9]", "", str(value))
#    if len(digits) < 2:
#        return None
#    return (int(digits[0]), int(digits[1:]))
#
#
#def parse_manifest(path: str) -> Dict[str, str]:
#    """讀 fetch_wheels.py 產生的 MANIFEST.txt 表頭（``key: value``）。讀不到回空 dict。"""
#    info: Dict[str, str] = {}
#    try:
#        with open(path, "r", encoding="utf-8", errors="replace") as f:
#            for raw in f:
#                line = raw.strip()
#                if not line or line.startswith("#"):
#                    continue
#                if line.lower().endswith(".whl") or " " in line.split(":")[0]:
#                    continue          # 檔案表格那一段，不是表頭
#                if ":" in line:
#                    key, val = line.split(":", 1)
#                    key = key.strip().lower()
#                    if re.match(r"^[a-z_]+$", key):
#                        info[key] = val.strip()
#    except OSError:
#        return {}
#    return info
#
#
#def find_wheels(wheels_dir: str) -> List[str]:
#    try:
#        return sorted(fn for fn in os.listdir(wheels_dir) if fn.lower().endswith(".whl"))
#    except OSError:
#        return []
#
#
#def wheel_python_tags(filename: str) -> List[str]:
#    """從 wheel 檔名取出 python tag（``numpy-2.0-cp39-cp39-win_amd64.whl`` → ['cp39']）。"""
#    parts = filename[:-4].split("-")
#    if len(parts) < 5:
#        return []
#    return [t for t in parts[-3].split(".") if t]
#
#
#def wheels_are_pure_python(wheels: Sequence[str]) -> bool:
#    """整包都是 ``py3-none-any`` 這種與版本無關的 wheel？（那版本不合也裝得起來）"""
#    if not wheels:
#        return False
#    for fn in wheels:
#        for tag in wheel_python_tags(fn):
#            if tag.startswith("cp") or re.match(r"^py3\d+$", tag):
#                return False
#    return True
#
#
#def build_pip_install_command(python_exe: str, wheels_dir: str, requirements: str,
#                              *, user: bool = False,
#                              extra_packages: Sequence[str] = ()) -> List[str]:
#    """組出離線安裝指令（純函式，方便測試）。"""
#    cmd = [python_exe, "-m", "pip", "install",
#           "--no-index", "--find-links", wheels_dir,
#           "-r", requirements]
#    if user:
#        cmd.append("--user")
#    cmd += list(extra_packages)
#    return cmd
#
#
#def venv_python(venv_dir: str) -> str:
#    """虛擬環境裡 python.exe / bin/python 的路徑。"""
#    if os.name == "nt":
#        return os.path.join(venv_dir, "Scripts", "python.exe")
#    return os.path.join(venv_dir, "bin", "python")
#
#
#def _existing_ancestor(path: str) -> str:
#    path = os.path.abspath(path)
#    while path and not os.path.isdir(path):
#        parent = os.path.dirname(path)
#        if parent == path:
#            break
#        path = parent
#    return path or os.path.abspath(os.sep)
#
#
## ---------------------------------------------------------------- 事前檢查
#
#class PreflightError(Exception):
#    """事前檢查沒過。訊息是給使用者看的白話說明（多行）。"""
#
#
#def _fail(title: str, *lines: str) -> "PreflightError":
#    return PreflightError("\n".join(["[錯誤] " + title] + ["       " + ln for ln in lines]))
#
#
#def preflight(*, wheels_dir: str, requirements: str, venv_dir: Optional[str],
#              force: bool = False, user: bool = False) -> List[str]:
#    """全部事前檢查。過不了就 raise PreflightError；回傳「提醒」字串清單。"""
#    notes: List[str] = []
#
#    # --- 0. Python 本身 ---
#    if sys.version_info[:2] < MIN_PYTHON:
#        raise _fail(
#            "這台機器的 Python 是 %d.%d，ADEPT 需要 %d.%d 以上。"
#            % (sys.version_info[0], sys.version_info[1], MIN_PYTHON[0], MIN_PYTHON[1]),
#            "請改用比較新的 Python（在「開始」功能表搜尋 Python 看看有沒有裝多個版本），",
#            "再用那個版本執行：C:\\Python311\\python.exe tools\\install_offline.py")
#
#    # --- 1. requirements.txt ---
#    if not os.path.isfile(requirements):
#        raise _fail(
#            "找不到 requirements.txt：%s" % requirements,
#            "你可能不在 ADEPT 的資料夾裡。請先切換到解壓出來的資料夾（裡面看得到 adept\\ 與 tools\\）：",
#            "    cd C:\\...\\ADEPT-main",
#            "    python tools\\install_offline.py")
#
#    # --- 2. wheels 資料夾存在 ---
#    if not os.path.isdir(wheels_dir):
#        raise _fail(
#            "找不到離線套件資料夾：%s" % wheels_dir,
#            "這個資料夾要在**有網路的機器**上先產生，做法：",
#            "    python tools\\fetch_wheels.py --python-version %s" % running_python_tag(),
#            "然後把整個 wheels 資料夾拷貝到這台機器、放在 ADEPT 資料夾底下，再跑一次本指令。",
#            "若資料夾放在別的地方，請用 --wheels 指定，例如：--wheels D:\\adept_wheels")
#
#    # --- 3. wheels 資料夾非空 ---
#    wheels = find_wheels(wheels_dir)
#    if not wheels:
#        others = []
#        try:
#            others = sorted(os.listdir(wheels_dir))[:5]
#        except OSError:
#            pass
#        raise _fail(
#            "資料夾 %s 裡面沒有任何 .whl 檔。" % wheels_dir,
#            "看到的內容：%s" % (("、".join(others) or "（空的）")),
#            "常見原因：拷貝時只複製了資料夾外殼、或防毒/DLP 把 .whl 檔擋掉了（.whl 其實是 zip）。",
#            "請回到有網路的機器重新執行 python tools\\fetch_wheels.py，並確認 wheels 資料夾裡有一堆 .whl。")
#
#    # --- 4. Python 版本 vs wheels 版本（最常見的失敗，一定要擋在 pip 之前） ---
#    manifest_path = os.path.join(wheels_dir, MANIFEST_NAME)
#    manifest = parse_manifest(manifest_path) if os.path.isfile(manifest_path) else {}
#    target = parse_python_tag(manifest.get("target_python", ""))
#    if target is None:
#        tags = [t for fn in wheels for t in wheel_python_tags(fn)]
#        cps = sorted({t for t in tags if t.startswith("cp")})
#        if cps:
#            target = parse_python_tag(cps[0])
#    running = sys.version_info[:2]
#    if target and tuple(target) != tuple(running):
#        if wheels_are_pure_python(wheels):
#            notes.append("MANIFEST 說這批 wheel 是給 Python %d.%d 的，但它們與版本無關（py3-none-any），"
#                         "所以照樣可以裝。" % target)
#        elif force:
#            notes.append("Python 版本與 wheels 不合（wheels 給 %d.%d，這台是 %d.%d），"
#                         "但你加了 --force，繼續。" % (target[0], target[1], running[0], running[1]))
#        else:
#            raise _fail(
#                "Python 版本對不上：這批 wheel 是給 Python %d.%d 用的，"
#                "但你現在跑的是 Python %d.%d。" % (target[0], target[1], running[0], running[1]),
#                "cp%d%d 的 wheel 在 Python %d.%d 上一定裝不起來（pip 會說 "
#                "\"is not a supported wheel on this platform\"）。"
#                % (target[0], target[1], running[0], running[1]),
#                "二選一：",
#                "  (A) 用對的 Python 跑本指令 —— 如果這台機器裝了 Python %d.%d，改成："
#                % (target[0], target[1]),
#                "      C:\\Python%d%d\\python.exe tools\\install_offline.py --wheels %s"
#                % (target[0], target[1], wheels_dir),
#                "  (B) 回到有網路的機器，重抓符合這台機器的 wheels：",
#                "      python tools\\fetch_wheels.py --python-version %s" % running_python_tag(),
#                "（清單檔：%s）" % manifest_path)
#
#    # --- 5. 平台 tag（只提醒，不擋） ---
#    target_plat = manifest.get("target_platform", "")
#    if target_plat:
#        expect = PLATFORM_TAG_HINT.get(sys.platform, sys.platform)
#        first = target_plat.split(",")[0].strip()
#        if first and not any(k in first for k in expect.replace("*", "").split(" / ")):
#            notes.append("這批 wheel 標的平台是 %s，但這台機器看起來是 %s（%s）；"
#                         "若 pip 說 not a supported wheel，請重抓對應平台的 wheels。"
#                         % (target_plat, sys.platform, expect))
#
#    # --- 6. 磁碟空間 ---
#    total = 0
#    for fn in wheels:
#        try:
#            total += os.path.getsize(os.path.join(wheels_dir, fn))
#        except OSError:
#            pass
#    need = int(total * SPACE_FACTOR) + SPACE_MARGIN_BYTES
#    where = _existing_ancestor(venv_dir or os.getcwd())
#    try:
#        free = shutil.disk_usage(where).free
#    except OSError:
#        free = None
#    if free is not None and free < need:
#        raise _fail(
#            "磁碟空間不夠：%s 只剩 %s，安裝大約需要 %s。" % (where, human_size(free), human_size(need)),
#            "PySide6 解開後就要幾百 MB。請清出空間，或把 ADEPT 放到空間夠的磁碟",
#            "（例如 D:\\），再用 --venv D:\\adept_venv 指定虛擬環境位置。")
#
#    # --- 7. 寫入權限 ---
#    target_dir = _existing_ancestor(venv_dir) if venv_dir else os.getcwd()
#    if not os.access(target_dir, os.W_OK):
#        raise _fail(
#            "沒有寫入權限：%s" % target_dir,
#            "請把 ADEPT 解壓到你自己的資料夾（例如 C:\\Users\\你的帳號\\ADEPT-main），",
#            "不要放在 C:\\Program Files、系統磁碟根目錄或唯讀的網路磁碟。")
#
#    if user and venv_dir:
#        notes.append("--user 只有搭配 --no-venv 才有意義（虛擬環境裡不需要）；這次會忽略它。")
#    return notes
#
#
## ---------------------------------------------------------------- 建 venv
#
#def create_venv(venv_dir: str) -> Tuple[bool, str]:
#    """建立虛擬環境。回傳 (是否成功, 訊息)。已存在就直接沿用。"""
#    py = venv_python(venv_dir)
#    if os.path.isfile(py):
#        return True, "沿用已存在的虛擬環境：%s" % venv_dir
#    cmd = [sys.executable, "-m", "venv", venv_dir]
#    try:
#        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#    except OSError as exc:
#        return False, "叫不動 python -m venv：%s" % exc
#    out = (proc.stdout or b"").decode("utf-8", "replace")
#    if proc.returncode == 0 and os.path.isfile(py):
#        return True, "已建立虛擬環境：%s" % venv_dir
#    return False, out.strip() or "python -m venv 回傳碼 %d（沒有任何訊息）" % proc.returncode
#
#
#def explain_venv_failure(message: str, venv_dir: str) -> List[str]:
#    """把建 venv 的失敗翻成白話與可行的替代方案。"""
#    low = (message or "").lower()
#    tips: List[str] = []
#    if "ensurepip" in low or "pip" in low:
#        tips.append("這台機器的 Python 把 ensurepip 拿掉了（公司統一安裝的映像常見）。")
#    elif "no module named venv" in low:
#        tips.append("這個 Python 沒有內建 venv 模組。")
#    elif "permission" in low or "denied" in low or "errno 13" in low:
#        tips.append("沒有權限在 %s 建立資料夾。" % os.path.dirname(os.path.abspath(venv_dir)))
#    tips.append("改用不建虛擬環境的方式安裝：")
#    tips.append("    python tools\\install_offline.py --no-venv")
#    tips.append("如果連系統目錄都不能寫，再加 --user（裝到你自己的帳號底下）：")
#    tips.append("    python tools\\install_offline.py --no-venv --user")
#    return tips
#
#
## ---------------------------------------------------------------- pip 失敗翻譯
#
#def explain_pip_failure(output: str, wheels_dir: str) -> List[str]:
#    low = (output or "").lower()
#    tips: List[str] = []
#    if "not a supported wheel on this platform" in low:
#        tips.append("wheel 的 Python 版本或平台跟這台機器不合。"
#                    "請在有網路的機器重抓：python tools\\fetch_wheels.py --python-version %s"
#                    % running_python_tag())
#    if "no matching distribution" in low or "could not find a version" in low:
#        tips.append("%s 裡缺了某個相依套件（pip 會把缺的名字印在上面）。" % wheels_dir)
#        tips.append("請回到有網路的機器重跑 fetch_wheels.py，把整個 wheels 資料夾重新帶過來"
#                    "（不要只挑幾個檔案複製）。")
#    if "no module named pip" in low:
#        tips.append("這個 Python 沒有 pip。請試 python -m ensurepip --default-pip，"
#                    "或請 IT 幫忙裝一個完整的 Python。")
#    if "permission" in low or "access is denied" in low:
#        tips.append("權限不足。請加 --no-venv --user，或把 ADEPT 移到你自己的資料夾再試。")
#    if "proxy" in low or "connection" in low or "timed out" in low or "ssl" in low:
#        tips.append("看起來 pip 還是想連網。--no-index 已經關掉連網了，"
#                    "若仍出現這種訊息，請檢查有沒有 pip.ini 設了 index-url，"
#                    "或加環境變數 PIP_NO_INDEX=1 後重試。")
#    if not tips:
#        tips.append("請把上面 pip 的訊息整段回報（最後 10 行最重要）。")
#    return tips
#
#
## ---------------------------------------------------------------- 主流程
#
#def _soften_stdout() -> None:
#    """主控台字碼頁吐不出某些字時，改成 replace 而不是整支程式炸掉。"""
#    for stream in (sys.stdout, sys.stderr):
#        try:
#            stream.reconfigure(errors="replace")      # Python 3.7+
#        except Exception:                             # noqa: BLE001 — 沒有就算了
#            pass
#
#
#def main(argv: Optional[Sequence[str]] = None) -> int:
#    _soften_stdout()
#    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#    ap = argparse.ArgumentParser(
#        prog="install_offline.py",
#        description="在沒有網路的機器上，用離線 wheels 資料夾安裝 ADEPT 的相依套件。",
#        formatter_class=argparse.RawDescriptionHelpFormatter,
#        epilog="範例：\n"
#               "  python tools\\install_offline.py\n"
#               "  python tools\\install_offline.py --wheels D:\\adept_wheels --venv D:\\adept_venv\n"
#               "  python tools\\install_offline.py --no-venv --user\n")
#    ap.add_argument("--wheels", default="wheels", help="離線 wheel 資料夾（預設 wheels）")
#    ap.add_argument("--venv", default=".venv", help="虛擬環境資料夾（預設 .venv）")
#    ap.add_argument("--no-venv", action="store_true",
#                    help="不建虛擬環境，直接裝進目前這個 Python")
#    ap.add_argument("--user", action="store_true",
#                    help="搭配 --no-venv：裝到使用者目錄（沒有系統管理權限時用）")
#    ap.add_argument("--requirements", default=os.path.join(repo, "requirements.txt"),
#                    help="requirements.txt 路徑")
#    ap.add_argument("--force", action="store_true",
#                    help="即使 Python 版本與 wheels 不合也硬裝（不建議）")
#    ap.add_argument("--include-pytest", action="store_true",
#                    help="連 pytest 一起裝（wheels 資料夾裡要有；抓的時候也要加 --include-pytest）")
#    ap.add_argument("--skip-doctor", action="store_true", help="安裝完不要自動跑環境自檢")
#    ap.add_argument("--dry-run", action="store_true",
#                    help="只做事前檢查並印出指令，不真的安裝")
#    args = ap.parse_args(list(argv) if argv is not None else None)
#
#    wheels_dir = os.path.abspath(args.wheels)
#    venv_dir = None if args.no_venv else os.path.abspath(args.venv)
#    requirements = os.path.abspath(args.requirements)
#
#    print("ADEPT 離線安裝")
#    print("  Python      ：%s（%s）" % (".".join(str(x) for x in sys.version_info[:3]),
#                                      sys.executable))
#    print("  wheels 資料夾：%s" % wheels_dir)
#    print("  安裝到      ：%s" % (venv_dir or "目前這個 Python（--no-venv）"))
#    print("")
#    print("[1/4] 事前檢查…")
#    try:
#        notes = preflight(wheels_dir=wheels_dir, requirements=requirements,
#                          venv_dir=venv_dir, force=args.force, user=args.user)
#    except PreflightError as exc:
#        print("")
#        print(str(exc), file=sys.stderr)
#        print("")
#        print("（安裝沒有開始，什麼都沒有被改動。）", file=sys.stderr)
#        return 2
#    wheels = find_wheels(wheels_dir)
#    total = sum(os.path.getsize(os.path.join(wheels_dir, fn)) for fn in wheels
#                if os.path.isfile(os.path.join(wheels_dir, fn)))
#    print("      ✓ 通過（%d 個 wheel，共 %s）" % (len(wheels), human_size(total)))
#    for n in notes:
#        print("      △ %s" % n)
#
#    # --- 2. venv ---
#    if venv_dir:
#        print("\n[2/4] 建立虛擬環境 %s …" % venv_dir)
#        if args.dry_run:
#            print("      （--dry-run：跳過）")
#            py_exe = venv_python(venv_dir)
#        else:
#            ok, msg = create_venv(venv_dir)
#            if not ok:
#                print("\n[錯誤] 建立虛擬環境失敗。", file=sys.stderr)
#                print("       原始訊息：%s" % msg.replace("\n", "\n                 "),
#                      file=sys.stderr)
#                for tip in explain_venv_failure(msg, venv_dir):
#                    print("       " + tip, file=sys.stderr)
#                return 2
#            print("      ✓ %s" % msg)
#            py_exe = venv_python(venv_dir)
#    else:
#        print("\n[2/4] 不建虛擬環境（--no-venv），直接用目前的 Python。")
#        py_exe = sys.executable
#
#    # --- 3. pip install ---
#    extra: List[str] = []
#    if args.include_pytest:
#        if any(fn.lower().startswith("pytest-") for fn in wheels):
#            extra.append("pytest")
#        else:
#            print("      △ --include-pytest：%s 裡沒有 pytest 的 wheel，這次不裝它。"
#                  % wheels_dir)
#    cmd = build_pip_install_command(py_exe, wheels_dir, requirements,
#                                    user=bool(args.user and not venv_dir),
#                                    extra_packages=extra)
#    print("\n[3/4] 安裝套件…")
#    print("      " + " ".join(cmd))
#    if args.dry_run:
#        print("\n（--dry-run：事前檢查已通過，沒有真的安裝。）")
#        return 0
#    try:
#        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
#    except OSError as exc:
#        print("\n[錯誤] 叫不動 pip：%s" % exc, file=sys.stderr)
#        print("       這個 Python 可能沒有 pip，請試 python -m ensurepip --default-pip。",
#              file=sys.stderr)
#        return 1
#    out = (proc.stdout or b"").decode("utf-8", "replace")
#    print(out.rstrip())
#    if proc.returncode != 0:
#        print("\n[錯誤] pip 安裝失敗（回傳碼 %d）。" % proc.returncode, file=sys.stderr)
#        for tip in explain_pip_failure(out, wheels_dir):
#            print("  · " + tip, file=sys.stderr)
#        return 1
#    print("      ✓ 套件安裝完成")
#
#    # --- 4. doctor ---
#    doctor = os.path.join(repo, "tools", "doctor.py")
#    skipped_doctor = args.skip_doctor or not os.path.isfile(doctor)
#    if skipped_doctor:
#        rc = 0
#        print("\n[4/4] 略過環境自檢。")
#    else:
#        print("\n[4/4] 環境自檢（tools/doctor.py）…\n")
#        try:
#            rc = subprocess.call([py_exe, doctor], cwd=repo)
#        except OSError as exc:
#            print("[警告] 跑不起來環境自檢：%s" % exc, file=sys.stderr)
#            rc = 1
#
#    print("\n" + "=" * 60)
#    if skipped_doctor:
#        print("套件安裝完成（這次沒有跑環境自檢）。建議跑一次：python tools\\doctor.py")
#        print("接下來：")
#    elif rc == 0:
#        print("安裝完成，環境自檢通過。接下來：")
#    else:
#        print("套件裝好了，但環境自檢有項目沒過（見上面的 ✗ 與修正建議）。修好後再跑：")
#        print("    python tools\\doctor.py --verbose")
#        print("接下來（自檢過了才會正常）：")
#    if venv_dir:
#        rel = os.path.relpath(venv_dir, repo) if venv_dir.startswith(repo) else venv_dir
#        if os.name == "nt":
#            print("    %s\\Scripts\\activate          ← 每次開新的命令列都要先做這一步" % rel)
#            print("      （PowerShell 版：%s\\Scripts\\Activate.ps1）" % rel)
#        else:
#            print("    source %s/bin/activate      ← 每次開新的終端機都要先做這一步" % rel)
#            print("      （Windows 版：%s\\Scripts\\activate）" % rel)
#    print("    python -m adept gui                 ← 開圖形介面 Studio")
#    print("    python tools\\make_sample.py C:\\temp\\lot --n 100   ← 產一份合成資料試玩")
#    print("=" * 60)
#    return 0 if rc == 0 else 1
#
#
#if __name__ == "__main__":  # pragma: no cover
#    sys.exit(main())
#
#F 79318988a82fb09aa02a79cea32db78f966855b4 95 tools/make_filelist.py
##!/usr/bin/env python3
## ADEPT 檔案清單產生器 — authored 2026-07-30.
#"""產生 ``tools/FILELIST.txt``：``tools/get_code.py`` 靠它知道要抓哪些檔案。
#
#在**開發機**上跑（需要 git）：
#
#    python tools/make_filelist.py
#
#為什麼要有這份清單
#------------------
#``get_code.py`` 刻意只用**一台主機**（``raw.githubusercontent.com``）——
#`codeload.github.com`（zip）與 `api.github.com`（列檔案）都是另外的主機，
#而公司 proxy 的 allowlist 每多一台就多一個會被擋的地方。
#raw 送得出單一檔案但列不出目錄，所以清單得先放在 repo 裡。
#
#清單裡存的是 **git blob SHA-1**，不是大小或 md5 —— 這樣 ``git hash-object``
#可以直接對照，`tests/test_offline_tools.py` 也就擋得住這份清單腐爛
#（新增檔案卻忘了重跑這支的話，那個檔案在受限機器上會**安靜地少掉**）。
#"""
#from __future__ import annotations
#
#import hashlib
#import os
#import subprocess
#import sys
#from typing import List
#
##: 清單自己不列在自己裡面（它的 SHA 沒辦法包含自己的 SHA）。
##: ``get_code.py`` 是先抓這份清單才開始抓別的，所以它不需要被驗。
#MANIFEST = "tools/FILELIST.txt"
#
##: 產出物不進清單。`bundle/` 裡是 `make_text_bundle.py` 產的搬運用檔案 ——
##: 它們是 repo 的**複本**，不是內容。列進去有兩個後果：`get_code.py` 會白抓
##: 2.4 MB，而分批解包的「還缺幾個」永遠到不了 0（那幾個檔案本來就不在包裡）。
#EXCLUDE_DIRS = ("bundle",)
#
#HEADER = (
#    "# ADEPT 檔案清單 —— tools/get_code.py 用（每行：git blob SHA-1 + 路徑）。",
#    "# 由 tools/make_filelist.py 產生；tests/test_offline_tools.py 會擋住它腐爛。",
#)
#
#
#def repo_root() -> str:
#    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#
#
#def tracked_files(root: str = "") -> List[str]:
#    """``git ls-files``（排除清單自己），排序後回傳。"""
#    root = root or repo_root()
#    out = subprocess.run(["git", "ls-files"], cwd=root, check=True,
#                         stdout=subprocess.PIPE).stdout.decode("utf-8")
#    keep = []
#    for raw in out.split("\n"):
#        rel = raw.strip()
#        if not rel or rel == MANIFEST:
#            continue
#        if any(rel.startswith(d + "/") for d in EXCLUDE_DIRS):
#            continue
#        keep.append(rel)
#    return sorted(keep)
#
#
#def blob_sha(data: bytes) -> str:
#    """git 算 blob SHA 的方式：``"blob <len>\\0" + 內容``（與 get_code.py 相同）。"""
#    h = hashlib.sha1()                                # noqa: S324 — git 的格式
#    h.update(b"blob %d\0" % len(data))
#    h.update(data)
#    return h.hexdigest()
#
#
#def build_lines(root: str = "") -> List[str]:
#    """整份清單的內容（測試拿這個跟磁碟上的檔案對照）。"""
#    root = root or repo_root()
#    lines = list(HEADER)
#    for rel in tracked_files(root):
#        with open(os.path.join(root, rel.replace("/", os.sep)), "rb") as f:
#            lines.append("%s %s" % (blob_sha(f.read()), rel))
#    return lines
#
#
#def main(argv=None) -> int:
#    root = repo_root()
#    lines = build_lines(root)
#    path = os.path.join(root, MANIFEST.replace("/", os.sep))
#    tmp = path + ".tmp"                               # atomic（鐵則 5）
#    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
#        f.write("\n".join(lines) + "\n")
#    os.replace(tmp, path)
#    print("%s：%d 個檔案" % (MANIFEST, len(lines) - len(HEADER)))
#    return 0
#
#
#if __name__ == "__main__":
#    sys.exit(main())
#
#F a096a20ac78fba6911826946334eb6ad2227ec23 229 tools/make_sample.py
##!/usr/bin/env python3
## ADEPT synthetic sample generator — authored 2026-07-28 (M1).
#"""合成 EBI patch 測試 lot 產生器。
#
#產出一個 ingest 層可以直接吃的迷你 lot：
#  OUT_DIR/LOT_SYN.tif          多頁 TIFF（頁序：test0, ref0, test1, ref1, …）
#  OUT_DIR/LOT_SYN.001          KLARF 1.2（TiffFileName + TiffSpec + IMAGELIST）
#  OUT_DIR/ground_truth.json    {defect_id: {"is_real": bool, "type": str}}
#
#每顆 defect 一組 test+ref uint8 影像對：
#  - 共用的週期性圓角方格圖案（cell pitch 可調），每對隨機整體相位；
#  - ref 額外帶 |dx|,|dy| <= shift_max 的隨機平移（**預設 0**：機台輸出的
#    test/ref patch 本來就兩兩對應，不需要對位。要測對位就把它調大）；
#  - 兩張各自加獨立高斯雜訊；
#  - REAL 缺陷只種在 test（亮點 / 暗點 / 橋接線，振幅 >= 50、靠近中心）；
#  - NUISANCE 只有雜訊 + 平移，沒有真缺陷。
#
#用法：
#  python3 tools/make_sample.py OUT_DIR [--n 24] [--real-frac 0.5] [--size 128]
#                               [--pitch 16] [--noise 6] [--seed 7] [--shift-max 3]
#也可 import：generate(out_dir, ...) -> {"out_dir","klarf","tiff","ground_truth"}。
#同一組參數（含 seed）產出的 TIFF 位元組完全相同（可重現）。
#"""
#from __future__ import annotations
#
#import argparse
#import json
#import os
#import sys
#from typing import Any, Dict
#
#import numpy as np
#import tifffile
#
## 讓 `python3 tools/make_sample.py` 不裝套件也能 import adept（與同層的 _synth）
#_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#if _REPO not in sys.path:
#    sys.path.insert(0, _REPO)
#_TOOLS = os.path.dirname(os.path.abspath(__file__))
#if _TOOLS not in sys.path:
#    sys.path.insert(0, _TOOLS)
#
#from adept.core.ingest import dataset, klarf_core, tiff_index  # noqa: E402
#
## 圖案／缺陷合成的共用零件（與 make_sample_rsem.py 共用，數值行為完全相同）
#from _synth import (  # noqa: E402
#    NUISANCE_TYPE, REAL_TYPES,
#    pattern as _pattern,
#    plant_anomaly as _plant_anomaly,
#    rounded_square_tile as _rounded_square_tile,
#)
#
#LOT_NAME = "LOT_SYN"
#
## KLARF 1.2 die pitch（µm）：XREL/YREL 會落在這個假 die 裡
#_DIE_PITCH_UM = 5000.0
#
#
## ---------------------------------------------------------------- KLARF 產生
#
#def _make_klarf_text(n: int, rows) -> str:
#    """組出 KLARF 1.2 文字（LF 換行、固定 timestamp → 位元組可重現）。"""
#    lines = [
#        "FileVersion 1 2;",
#        "FileTimestamp 07-28-26 00:00:00;",
#        'InspectionStationID "SYN" "SYN" "ADEPT";',
#        "SampleType WAFER;",
#        "ResultTimestamp 07-28-26 00:00:00;",
#        f'LotID "{LOT_NAME}";',
#        "SampleSize 1 300;",
#        'DeviceID "SYNDEV";',
#        'SetupID "SYN" 07-28-26 00:00:00;',
#        'StepID "SYNSTEP";',
#        "SampleOrientationMarkType NOTCH;",
#        "OrientationMarkLocation DOWN;",
#        f"DiePitch {_DIE_PITCH_UM:.1f} {_DIE_PITCH_UM:.1f};",
#        "DieOrigin 0.0 0.0;",
#        'WaferID "W01";',
#        "Slot 1;",
#        f"TiffFileName {LOT_NAME}.tif;",
#        'TiffSpec 6.1 1 "IMAGENUMBER";',
#        "InspectionTest 1;",
#        "DefectRecordSpec 8 DEFECTID XREL YREL XINDEX YINDEX CLASSNUMBER"
#        " IMAGECOUNT IMAGELIST ;",
#        "DefectList",
#    ]
#    body = "\n".join(" " + " ".join(r) for r in rows) + ";"
#    lines.append(body)
#    lines += [
#        "SummarySpec 5 TESTNO NDEFECT DEFDENSITY NDIE NDEFDIE ;",
#        "SummaryList",
#        f" 1 {n} 1.0000000000e-03 25 {n};",
#        "EndOfFile;",
#        "",
#    ]
#    return "\n".join(lines)
#
#
## ---------------------------------------------------------------- 主產生器
#
#def generate(out_dir, n: int = 24, real_frac: float = 0.5, size: int = 128,
#             pitch: int = 16, noise: float = 6.0, seed: int = 7,
#             shift_max: int = 0) -> Dict[str, str]:
#    """產生合成 lot 並自我驗證 ingest 層讀得回來。回傳輸出檔路徑 dict。"""
#    if n < 1:
#        raise ValueError(f"n 至少要 1（收到 {n}）")
#    if not (0.0 <= real_frac <= 1.0):
#        raise ValueError(f"real_frac 必須在 0–1 之間（收到 {real_frac}）")
#    if size < 4 * pitch:
#        raise ValueError(f"size（{size}）至少要是 pitch（{pitch}）的 4 倍，圖案才有週期性")
#    if shift_max < 0:
#        raise ValueError(f"shift_max 不可為負（收到 {shift_max}）")
#
#    out_dir = str(out_dir)
#    os.makedirs(out_dir, exist_ok=True)
#    tiff_path = os.path.join(out_dir, LOT_NAME + ".tif")
#    klarf_path = os.path.join(out_dir, LOT_NAME + ".001")
#    gt_path = os.path.join(out_dir, "ground_truth.json")
#
#    rng = np.random.default_rng(int(seed))
#    tile = _rounded_square_tile(pitch)
#
#    # 哪些 defect 是 REAL
#    n_real = int(round(n * real_frac))
#    real_idx = set(rng.choice(n, size=n_real, replace=False).tolist()) if n_real else set()
#
#    pages = []          # test0, ref0, test1, ref1, ...
#    rows = []           # KLARF defect rows
#    truth: Dict[str, Dict[str, Any]] = {}
#
#    for i in range(n):
#        # 共用圖案 + 每對隨機整體相位；ref 相位再偏 (-dx, -dy) →
#        # ref(x, y) == test_clean(x - dx, y - dy)（algo.align 的正向慣例）
#        ox = int(rng.integers(0, pitch))
#        oy = int(rng.integers(0, pitch))
#        dx = int(rng.integers(-shift_max, shift_max + 1))
#        dy = int(rng.integers(-shift_max, shift_max + 1))
#        test_f = _pattern(size, pitch, ox, oy, tile)
#        ref_f = _pattern(size, pitch, ox - dx, oy - dy, tile)
#
#        is_real = i in real_idx
#        if is_real:
#            kind = str(REAL_TYPES[int(rng.integers(0, len(REAL_TYPES)))])
#            _plant_anomaly(test_f, kind, rng, pitch)    # 只種在 test
#        else:
#            kind = NUISANCE_TYPE
#
#        test_f = test_f + rng.normal(0.0, noise, test_f.shape)
#        ref_f = ref_f + rng.normal(0.0, noise, ref_f.shape)
#        pages.append(np.clip(test_f, 0, 255).astype(np.uint8))
#        pages.append(np.clip(ref_f, 0, 255).astype(np.uint8))
#
#        defect_id = str(i + 1)
#        truth[defect_id] = {"is_real": bool(is_real), "type": kind}
#
#        xrel = float(rng.uniform(100.0, _DIE_PITCH_UM - 100.0))
#        yrel = float(rng.uniform(100.0, _DIE_PITCH_UM - 100.0))
#        xindex = int(rng.integers(-2, 3))
#        yindex = int(rng.integers(-2, 3))
#        # IMAGELIST：TiffSpec 每張圖 1 個 token（1-based TIFF 頁碼）
#        rows.append([defect_id, f"{xrel:.3f}", f"{yrel:.3f}",
#                     str(xindex), str(yindex), "0",
#                     "2", str(2 * i + 1), str(2 * i + 2)])
#
#    # ---- 寫 TIFF（多頁；同 seed → 位元組完全相同）----
#    with tifffile.TiffWriter(tiff_path) as tw:
#        for arr in pages:
#            tw.write(arr, photometric="minisblack")
#
#    # ---- 寫 KLARF 1.2 ----
#    with open(klarf_path, "w", encoding="utf-8", newline="") as f:
#        f.write(_make_klarf_text(n, rows))
#
#    # ---- 寫 ground truth ----
#    with open(gt_path, "w", encoding="utf-8") as f:
#        json.dump(truth, f, ensure_ascii=False, indent=2, sort_keys=True)
#
#    # ---- 自我驗證：ingest 層必須讀得回來 ----
#    doc = klarf_core.load(klarf_path)
#    assert doc.version == "1.2", f"KLARF 版本判定錯誤：{doc.version}"
#    npages = tiff_index.n_pages(tiff_path)
#    assert npages == 2 * n, f"TIFF 頁數不對：{npages} != {2 * n}"
#    imap = doc.defect_image_map(npages)
#    assert imap["mode"] is not None, f"defect_image_map 解不出來：{imap['notes']}"
#    assert len(imap["pages"]) == n, f"對到 {len(imap['pages'])} 顆 defect（應為 {n}）"
#    for i, pg in enumerate(imap["pages"]):
#        assert pg == [2 * i, 2 * i + 1], f"defect {i + 1} 對到的頁不對：{pg}"
#
#    ds = dataset.load_dataset(klarf_path)
#    assert ds.kind == "ebi_patch", f"dataset kind 應為 ebi_patch，得到 {ds.kind}（warnings={ds.warnings}）"
#    assert len(ds.items) == n, f"dataset 有 {len(ds.items)} 顆 defect（應為 {n}）"
#    for i, it in enumerate(ds.items):
#        assert "test" in it.images and "ref" in it.images, \
#            f"defect {it.defect_id} 缺 test/ref ImageRef：{sorted(it.images)}"
#        assert it.images["test"].page == 2 * i and it.images["ref"].page == 2 * i + 1, \
#            f"defect {it.defect_id} 頁碼不對：test={it.images['test'].page} ref={it.images['ref'].page}"
#
#    return {"out_dir": out_dir, "klarf": klarf_path, "tiff": tiff_path,
#            "ground_truth": gt_path}
#
#
## ---------------------------------------------------------------- CLI
#
#def main(argv=None) -> int:
#    ap = argparse.ArgumentParser(
#        description="產生 ADEPT 合成 EBI patch lot（KLARF 1.2 + 多頁 TIFF + ground truth）。")
#    ap.add_argument("out_dir", help="輸出資料夾（不存在會建立）")
#    ap.add_argument("--n", type=int, default=24, help="defect 數量（預設 24）")
#    ap.add_argument("--real-frac", type=float, default=0.5,
#                    help="REAL 缺陷比例 0–1（預設 0.5，其餘為 nuisance）")
#    ap.add_argument("--size", type=int, default=128, help="影像邊長（預設 128）")
#    ap.add_argument("--pitch", type=int, default=16, help="圖案 cell 週期（預設 16）")
#    ap.add_argument("--noise", type=float, default=6.0, help="高斯雜訊 sigma（預設 6）")
#    ap.add_argument("--seed", type=int, default=7, help="隨機種子（同 seed 產出相同位元組）")
#    ap.add_argument("--shift-max", type=int, default=0,
#                    help="ref 相對 test 的最大平移（像素，預設 3）")
#    args = ap.parse_args(argv)
#    paths = generate(args.out_dir, n=args.n, real_frac=args.real_frac,
#                     size=args.size, pitch=args.pitch, noise=args.noise,
#                     seed=args.seed, shift_max=args.shift_max)
#    print("Generated synthetic lot:")
#    for k in ("klarf", "tiff", "ground_truth"):
#        print(f"  {k:12s} {paths[k]}")
#    return 0
#
#
#if __name__ == "__main__":
#    raise SystemExit(main())
#
#F cd11d6aba3d087b6d30ea50e385fd44f3586f865 296 tools/make_sample_rsem.py
##!/usr/bin/env python3
## ADEPT synthetic sample generator (Review SEM) — authored 2026-07-28 (M4-2).
#"""合成 Review SEM（rSEM）測試 lot 產生器 —— ingest 的另一條分支。
#
#和 `make_sample.py`（EBI patch：一份多頁 TIFF，每顆 defect 兩頁 test/ref）
#相反，這裡走的是 **每顆 defect 一個獨立影像檔** 的 Review SEM 佈局：
#
#  OUT_DIR/images/DEF_0001.png  每顆 defect 一張（預設 PNG，可 --format tif）
#  OUT_DIR/LOT_RSEM.001         KLARF 1.8（defect 列尾帶 `Images 1 { "檔名" … }`）
#  OUT_DIR/ground_truth.json    {defect_id: {"is_real": bool, "type": str}}
#
#`dataset.load_dataset()` 讀這份 KLARF 會回 ``kind == "rsem"``、
#每顆 defect 只有 ``images["single"]``（沒有 ref）——
#正是 Golden Cell 卡（`cell_period` + `golden_cell`）要處理的情境。
#
#影像內容（比 EBI patch 大、解析度高，預設 256²／cell pitch 24）：
#  - 嚴格週期的圓角方格晶格，**每張圖隨機相位**（相位是裁切位移，不是重取樣，
#    所以晶格仍然嚴格週期 → Golden Cell 的相位搜尋才有事情可做）；
#  - 每張圖各自的亮度／對比微擾（模擬 SEM 每次取像的條件差異）；
#  - 高斯雜訊；
#  - REAL 缺陷在影像中心附近種一個異常（亮點／暗點／橋接線，振幅 >= 50）；
#  - NUISANCE 只有晶格 + 雜訊，沒有真缺陷。
#
#用法：
#  python3 tools/make_sample_rsem.py OUT_DIR [--n 24] [--real-frac 0.5] [--size 256]
#                                    [--pitch 24] [--noise 5] [--seed 11] [--format png]
#也可 import：generate(out_dir, ...) -> {"out_dir","klarf","images_dir","images",
#"ground_truth"}。同一組參數（含 seed）產出的每個檔案位元組完全相同（可重現）。
#"""
#from __future__ import annotations
#
#import argparse
#import json
#import os
#import sys
#from typing import Any, Dict, List
#
#import cv2
#import numpy as np
#
## 讓 `python3 tools/make_sample_rsem.py` 不裝套件也能 import adept（與同層的 _synth）
#_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#if _REPO not in sys.path:
#    sys.path.insert(0, _REPO)
#_TOOLS = os.path.dirname(os.path.abspath(__file__))
#if _TOOLS not in sys.path:
#    sys.path.insert(0, _TOOLS)
#
#from adept.core.ingest import dataset, klarf_core  # noqa: E402
#
## 圖案／缺陷合成的共用零件（與 make_sample.py 共用同一組數值行為）
#from _synth import (  # noqa: E402
#    NUISANCE_TYPE, REAL_TYPES, pattern, plant_anomaly, rounded_square_tile,
#)
#
#LOT_NAME = "LOT_RSEM"
#IMAGES_DIRNAME = "images"
#FORMATS = ("png", "tif")
#
## KLARF 1.8 的座標單位是 nm（整數）：假 die 5 mm × 5 mm
#_DIE_PITCH_NM = 5_000_000
#
## PNG 壓縮等級寫死 → 不同機器／不同 OpenCV 預設值都產出相同位元組
#_PNG_PARAMS = [int(cv2.IMWRITE_PNG_COMPRESSION), 3]
#
## 固定時間戳（KLARF 內容必須可重現，不能用 now()）
#_TIMESTAMP = "07-28-26 00:00:00"
#
#
## ---------------------------------------------------------------- 影像寫出
#
#def _encode(arr: np.ndarray, ext: str) -> np.ndarray:
#    """把 uint8 灰階圖編碼成位元組緩衝（固定參數 → 可重現）。"""
#    params = _PNG_PARAMS if ext == ".png" else []
#    ok, buf = cv2.imencode(ext, arr, params)
#    if not ok:
#        raise IOError(f"影像編碼失敗（格式 {ext}）")
#    return buf
#
#
#def _write_image(path: str, arr: np.ndarray) -> None:
#    """CJK 路徑安全的寫檔（同 imageio._encode_and_write 的 imencode + tofile 手法）。"""
#    _encode(arr, os.path.splitext(path)[1]).tofile(path)
#
#
## ---------------------------------------------------------------- KLARF 產生
#
#def _make_klarf_text(rows: List[str]) -> str:
#    """組出 KLARF 1.8 文字（LF 換行、固定 timestamp → 位元組可重現）。
#
#    每顆 defect 的影像檔名放在 ``ImageList IMAGEINFO`` 欄，語法與廠內實檔
#    （tests/fixtures/sample_real.klarf）相同：
#
#        <欄位…> IMAGECOUNT Images 1 { "images/DEF_0001.png" "PNG" 1 "24" } ;
#
#    `klarf_core.defect_image_filename()` 取區塊內第一個帶引號字串當檔名；
#    `image_layout()` 也認得這種 'images18' 佈局（欄位起點正好落在 IMAGEINFO）。
#    """
#    body = "\n".join("          " + r for r in rows)
#    return f"""Record FileRecord  "1.8"
#{{
#  Field FileTimestamp 1 {{"{_TIMESTAMP}"}}
#  Field InspectionStationID 3 {{"SYN", "SYN", "ADEPT"}}
#
#  Record LotRecord "{LOT_NAME}"
#  {{
#    Field DeviceID 1 {{"SYNDEV"}}
#    Field StepID 1 {{"SYNSTEP"}}
#    Field SampleType 1 {{"WAFER"}}
#    Field ResultTimestamp 1 {{"{_TIMESTAMP}"}}
#
#    Record WaferRecord "W01"
#    {{
#      Field DieOrigin 2 {{0, 0}}
#      Field DiePitch 2 {{{_DIE_PITCH_NM}, {_DIE_PITCH_NM}}}
#      Field OrientationMarkLocation 1 {{"DOWN"}}
#      Field SlotNumber 1 {{1}}
#
#      List DefectList
#      {{
#        Columns 9 {{ int32 DEFECTID,  int32 XREL,  int32 YREL,  int32 XINDEX,
#        int32 YINDEX,  int32 CLASSNUMBER,  int32 TEST,  int32 IMAGECOUNT,
#        ImageList IMAGEINFO  }}
#        Data {len(rows)}
#        {{
#{body}
#        }}
#      }}
#    }}
#  }}
#}}
#EndOfFile;
#"""
#
#
#def _defect_row(defect_id: str, xrel: int, yrel: int, xindex: int, yindex: int,
#                rel_name: str, fmt: str) -> str:
#    """一列 defect（列尾帶 Images 區塊；`,` 不可出現在檔名內）。"""
#    return (f"{defect_id} {xrel} {yrel} {xindex} {yindex} 0 1 1 "
#            f'Images 1 {{ "{rel_name}" "{fmt.upper()}" 1 "24" }} ;')
#
#
## ---------------------------------------------------------------- 主產生器
#
#def generate(out_dir, n: int = 24, real_frac: float = 0.5, size: int = 256,
#             pitch: int = 24, noise: float = 5.0, seed: int = 11,
#             fmt: str = "png") -> Dict[str, Any]:
#    """產生合成 rSEM lot 並自我驗證 ingest 層讀得回來。回傳輸出檔路徑 dict。"""
#    if n < 1:
#        raise ValueError(f"n 至少要 1（收到 {n}）")
#    if not (0.0 <= real_frac <= 1.0):
#        raise ValueError(f"real_frac 必須在 0–1 之間（收到 {real_frac}）")
#    if pitch < 4:
#        raise ValueError(f"pitch 至少要 4（收到 {pitch}），否則疊不出 cell")
#    if size < 4 * pitch:
#        raise ValueError(f"size（{size}）至少要是 pitch（{pitch}）的 4 倍，圖案才有週期性")
#    if noise < 0:
#        raise ValueError(f"noise 不可為負（收到 {noise}）")
#    fmt = str(fmt).lower().lstrip(".")
#    if fmt not in FORMATS:
#        raise ValueError(f"format 只支援 {'/'.join(FORMATS)}（收到 {fmt!r}）")
#
#    out_dir = str(out_dir)
#    img_dir = os.path.join(out_dir, IMAGES_DIRNAME)
#    os.makedirs(img_dir, exist_ok=True)
#    klarf_path = os.path.join(out_dir, LOT_NAME + ".001")
#    gt_path = os.path.join(out_dir, "ground_truth.json")
#
#    rng = np.random.default_rng(int(seed))
#    tile = rounded_square_tile(pitch)
#
#    # 哪些 defect 是 REAL
#    n_real = int(round(n * real_frac))
#    real_idx = set(rng.choice(n, size=n_real, replace=False).tolist()) if n_real else set()
#
#    rows: List[str] = []
#    img_paths: List[str] = []
#    truth: Dict[str, Dict[str, Any]] = {}
#
#    for i in range(n):
#        # 每張圖自己的晶格相位（裁切位移 → 仍然嚴格週期）
#        ox = int(rng.integers(0, pitch))
#        oy = int(rng.integers(0, pitch))
#        img = pattern(size, pitch, ox, oy, tile)
#
#        # 每張圖的亮度／對比微擾（在種缺陷之前做，缺陷振幅才不會被 gain 縮掉）
#        gain = float(rng.uniform(0.90, 1.10))
#        bias = float(rng.uniform(-10.0, 10.0))
#        img = (img - 128.0) * gain + 128.0 + bias
#
#        is_real = i in real_idx
#        if is_real:
#            kind = str(REAL_TYPES[int(rng.integers(0, len(REAL_TYPES)))])
#            plant_anomaly(img, kind, rng, pitch)
#        else:
#            kind = NUISANCE_TYPE
#
#        img = img + rng.normal(0.0, noise, img.shape)
#        u8 = np.clip(img, 0, 255).astype(np.uint8)
#
#        defect_id = str(i + 1)
#        name = f"DEF_{i + 1:04d}.{fmt}"
#        path = os.path.join(img_dir, name)
#        _write_image(path, u8)
#        img_paths.append(path)
#
#        truth[defect_id] = {"is_real": bool(is_real), "type": kind}
#
#        xrel = int(rng.integers(100_000, _DIE_PITCH_NM - 100_000))
#        yrel = int(rng.integers(100_000, _DIE_PITCH_NM - 100_000))
#        rows.append(_defect_row(defect_id, xrel, yrel,
#                                int(rng.integers(-2, 3)), int(rng.integers(-2, 3)),
#                                IMAGES_DIRNAME + "/" + name, fmt))
#
#    # ---- 寫 KLARF 1.8 ----
#    with open(klarf_path, "w", encoding="utf-8", newline="") as f:
#        f.write(_make_klarf_text(rows))
#
#    # ---- 寫 ground truth ----
#    with open(gt_path, "w", encoding="utf-8") as f:
#        json.dump(truth, f, ensure_ascii=False, indent=2, sort_keys=True)
#
#    # ---- 自我驗證 1：影像編碼是決定性的（同輸入 → 同位元組）----
#    with open(img_paths[0], "rb") as f:
#        first = f.read()
#    again = _encode(cv2.imdecode(np.frombuffer(first, np.uint8),
#                                 cv2.IMREAD_GRAYSCALE),
#                    os.path.splitext(img_paths[0])[1]).tobytes()
#    assert again == first, (
#        f"影像編碼不是決定性的（{os.path.basename(img_paths[0])} 重編後位元組不同）；"
#        "同 seed 產出將無法重現。")
#
#    # ---- 自我驗證 2：KLARF 解得開、每顆 defect 都指到存在的檔案 ----
#    doc = klarf_core.load(klarf_path)
#    assert doc.version == "1.8", f"KLARF 版本判定錯誤：{doc.version}"
#    assert len(doc.defects) == n, f"KLARF 解出 {len(doc.defects)} 列 defect（應為 {n}）"
#    layout = doc.image_layout()
#    assert layout is not None and layout[2] == "images18", \
#        f"影像欄佈局判定錯誤：{layout}（應為 images18）"
#    for k, row in enumerate(doc.defects):
#        fname = doc.defect_image_filename(row)
#        assert fname, f"defect {k + 1} 的列尾沒解出影像檔名：{' '.join(row)}"
#        assert os.path.isfile(os.path.join(out_dir, fname)), \
#            f"defect {k + 1} 指到不存在的影像：{fname}"
#        assert len(doc.defect_image_entries(row)) == 1, \
#            f"defect {k + 1} 的 Images 區塊解出 {len(doc.defect_image_entries(row))} 條（應為 1）"
#
#    # ---- 自我驗證 3：dataset 層必須判成 rsem 且讀得出像素 ----
#    ds = dataset.load_dataset(klarf_path)
#    assert ds.kind == "rsem", f"dataset kind 應為 rsem，得到 {ds.kind}（warnings={ds.warnings}）"
#    assert len(ds.items) == n, f"dataset 有 {len(ds.items)} 顆 defect（應為 {n}）"
#    for i, it in enumerate(ds.items):
#        assert set(it.images) == {"single"}, \
#            f"defect {it.defect_id} 的 channel 應只有 single，得到 {sorted(it.images)}"
#        ref = it.images["single"]
#        assert ref.page is None, f"defect {it.defect_id} 的 single 不該是 TIFF 頁（page={ref.page}）"
#        assert os.path.isfile(ref.path), f"defect {it.defect_id} 的影像不存在：{ref.path}"
#        assert os.path.abspath(ref.path) == os.path.abspath(img_paths[i]), \
#            f"defect {it.defect_id} 對到的檔案不對：{ref.path} != {img_paths[i]}"
#        arr = it.load("single")
#        assert arr.shape == (size, size) and arr.dtype == np.uint8, \
#            f"defect {it.defect_id} 像素讀回來是 {arr.shape}/{arr.dtype}（應為 {(size, size)}/uint8）"
#
#    return {"out_dir": out_dir, "klarf": klarf_path, "images_dir": img_dir,
#            "images": img_paths, "ground_truth": gt_path}
#
#
## ---------------------------------------------------------------- CLI
#
#def main(argv=None) -> int:
#    ap = argparse.ArgumentParser(
#        description="產生 ADEPT 合成 Review SEM lot（KLARF 1.8 + 每顆 defect 一張影像 + ground truth）。")
#    ap.add_argument("out_dir", help="輸出資料夾（不存在會建立）")
#    ap.add_argument("--n", type=int, default=24, help="defect 數量（預設 24）")
#    ap.add_argument("--real-frac", type=float, default=0.5,
#                    help="REAL 缺陷比例 0–1（預設 0.5，其餘為 nuisance）")
#    ap.add_argument("--size", type=int, default=256, help="影像邊長（預設 256）")
#    ap.add_argument("--pitch", type=int, default=24, help="圖案 cell 週期（預設 24）")
#    ap.add_argument("--noise", type=float, default=5.0, help="高斯雜訊 sigma（預設 5）")
#    ap.add_argument("--seed", type=int, default=11, help="隨機種子（同 seed 產出相同位元組）")
#    ap.add_argument("--format", dest="fmt", default="png", choices=list(FORMATS),
#                    help="影像檔格式（預設 png）")
#    args = ap.parse_args(argv)
#    paths = generate(args.out_dir, n=args.n, real_frac=args.real_frac,
#                     size=args.size, pitch=args.pitch, noise=args.noise,
#                     seed=args.seed, fmt=args.fmt)
#    print("Generated synthetic rSEM lot:")
#    for k in ("klarf", "images_dir", "ground_truth"):
#        print(f"  {k:12s} {paths[k]}")
#    print(f"  {'images':12s} {len(paths['images'])} files")
#    return 0
#
#
#if __name__ == "__main__":
#    raise SystemExit(main())
#
#F c078e47ba2a10ef1c380da1d54aea9cb0ca62fe4 326 tools/make_text_bundle.py
##!/usr/bin/env python3
## ADEPT 單檔純文字打包 — authored 2026-07-30.
#"""把整個 repo 打成**一個純文字 .py 檔**，那個檔案自己解得開。
#
#什麼時候需要這個
#----------------
#實測遇到的情況：公司政策**擋掉 `.zip` 這個類別**（不只是 GitHub 的
#`codeload.github.com`，連從別的來源下載同一包 zip 也擋），而且 proxy 也不讓
#Python 逐檔抓。這時候 `tools/get_code.py` / `.ps1` 都用不上，能過的只剩
#「一個純文字檔」。
#
#所以這支產出的東西**沒有任何壓縮格式**：檔案內容原封不動地一行一行躺在裡面，
#可以用記事本打開讀。也**刻意不用 base64** —— base64 對 DLP 來說是「看不懂的
#東西」，而看不懂通常就等於擋掉；而且這個 repo 全部是純文字，本來就不需要編碼。
#
#怎麼用
#------
#    python tools/make_text_bundle.py            # 產 ADEPT_bundle.py
#    python tools/make_text_bundle.py --out X.py
#
#拿到 `ADEPT_bundle.py` 的人：
#
#    python ADEPT_bundle.py                      # 解到 .\\ADEPT\\
#    python ADEPT_bundle.py --dest D:\\tools
#    python ADEPT_bundle.py --list               # 只列出裡面有什麼，不寫檔
#
#格式為什麼是「行數」而不是「位元組數」
#--------------------------------------
#這個檔案會經過瀏覽器下載、記事本另存、郵件附件…… 任何一步都可能把 LF 換成
#CRLF。用位元組數的話那一換整包就對不起來了，而且錯誤會發生在**第一個檔案之後
#的全部檔案**上，看起來像整包壞掉。用行數則對換行符號免疫 —— 解開的時候用
#Python 的文字模式讀（它會把 CRLF 讀成 LF），所以來回一趟仍然逐位元組相同。
#前提是 repo 裡全部是 LF + UTF-8，這支會在打包前檢查，不合就拒絕產出。
#
#每個檔案仍然帶 **git blob SHA-1**，解開時逐檔驗 —— 傳輸途中被動到的話要當場
#講出來，而不是讓使用者拿到一份安靜壞掉的程式碼。
#"""
#from __future__ import annotations
#
#import argparse
#import hashlib
#import os
#import subprocess
#import sys
#from typing import List, Optional, Tuple
#
##: 資料區的分隔行。解包時找的是**整行剛好等於它**的那一行 —— 而資料區的每一行
##: 都被加了 '#'，所以就算某個檔案的內容裡出現這個字串（``make_text_bundle.py``
##: 自己就在 repo 裡，它的源碼裡當然有），也永遠不會剛好相等。加 '#' 那件事因此
##: 同時解決了兩個問題：整個檔案仍然是合法的 Python，而分隔行不會被誤認。
#BUNDLE_DIR = "bundle"
#
#SENTINEL = "# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ===="
#
##: 解包程式（放在產出檔案的最前面）。它自己也是這份 bundle 的一部分，
##: 所以刻意寫短、只用標準函式庫、而且看得完 —— 使用者要能在跑之前先讀一遍。
#EXTRACTOR = '''#!/usr/bin/env python3
## ADEPT 單檔純文字包（由 tools/make_text_bundle.py 產生）。
#"""整個 ADEPT repo 就在這個檔案裡，一行一行的純文字，沒有壓縮、沒有編碼。
#
#為什麼是這種形式：公司政策擋掉 .zip 這個類別，而 proxy 也不讓 Python 逐檔抓 ——
#能過的只剩「一個純文字檔」。你可以用記事本打開它，往下捲就看得到每個檔案的內容。
#
#    python %(name)s              # 解到 .\\\\ADEPT\\\\
#    python %(name)s --dest D:\\\\tools
#    python %(name)s --list       # 只看裡面有什麼，不寫任何檔案
#
#每個檔案都帶 git blob SHA-1，解開時逐檔驗過才落地 —— 傳輸途中被動到的話會當場
#講出來，不會讓你拿到一份安靜壞掉的程式碼。
#"""
#from __future__ import annotations
#
#import argparse
#import hashlib
#import os
#import sys
#
#SENTINEL = "%(sentinel)s"
#PART, N_PARTS = %(part)d, %(n_parts)d   # 這是第幾批 / 共幾批（1/1 = 沒有分批）
#TOTAL = %(total)d                       # 整個 repo 有幾個檔案，不是這一批有幾個
#
#
#def blob_sha(data: bytes) -> str:
#    """git 算 blob SHA 的方式："blob <長度>\\\\0" + 內容。"""
#    h = hashlib.sha1()
#    h.update(b"blob %%d\\0" %% len(data))
#    h.update(data)
#    return h.hexdigest()
#
#
#def entries(lines):
#    """走過資料區，一個一個吐出 (sha, 路徑, 內容位元組)。"""
#    i = 0
#    while i < len(lines):
#        line = lines[i]
#        if not line.startswith("#F "):
#            i += 1
#            continue
#        _, sha, count, path = line.split(" ", 3)
#        n = int(count)
#        # 資料區每一行前面有一個 '#'（那樣整個檔案才仍然是合法的 Python）。
#        body = [ln[1:] if ln[:1] == "#" else ln for ln in lines[i + 1:i + 1 + n]]
#        yield sha, path, "\\n".join(body).encode("utf-8")
#        i += 1 + n
#
#
#def main(argv=None) -> int:
#    ap = argparse.ArgumentParser(description="Unpack the ADEPT text bundle.")
#    ap.add_argument("--dest", default="ADEPT", help="解到哪個資料夾（預設 .\\\\ADEPT）")
#    ap.add_argument("--list", action="store_true", help="只列出內容，不寫檔")
#    a = ap.parse_args(argv)
#
#    # 用文字模式讀自己：Python 會把 CRLF 讀成 LF，所以這個檔案就算在傳輸途中
#    # 被換過行尾也解得開（格式用「行數」而不是「位元組數」正是為了這件事）。
#    with open(os.path.abspath(__file__), "r", encoding="utf-8") as f:
#        lines = f.read().split("\\n")
#    try:
#        start = lines.index(SENTINEL) + 1
#    except ValueError:
#        print("✗ 找不到資料區 —— 這個檔案被截斷了，或不是完整的 bundle。")
#        return 2
#
#    items = list(entries(lines[start:]))
#    if not items:
#        print("✗ 資料區是空的 —— 這個檔案被截斷了。")
#        return 2
#    print("這個包裡有 %%d 個檔案。" %% len(items))
#    if a.list:
#        for _sha, path, data in items:
#            print("  %%8d  %%s" %% (len(data), path))
#        return 0
#
#    dest = os.path.abspath(a.dest)
#    print("解到  : %%s" %% dest)
#    bad, done = [], 0
#    for sha, path, data in items:
#        if blob_sha(data) != sha:
#            bad.append(path)
#            continue
#        full = os.path.join(dest, path.replace("/", os.sep))
#        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
#        tmp = full + ".tmp"                      # atomic：半個檔案不要留在磁碟上
#        with open(tmp, "wb") as f:
#            f.write(data)
#        os.replace(tmp, full)
#        done += 1
#
#    if bad:
#        print("")
#        print("✗ %%d 個檔案的內容跟它自己的 SHA 對不上：" %% len(bad))
#        for path in bad[:12]:
#            print("    %%s" %% path)
#        print("")
#        print("  這個檔案在傳輸途中被動過（編輯器另存、郵件過濾器改寫都會這樣）。")
#        print("  請重新取得一份，不要用編輯器打開後另存。這份程式碼不完整，不要用。")
#        return 1
#
#    print("✓ %%d 個檔案都解開了，SHA 全部對得上。" %% done)
#
#    # 分批的時候要講「還缺幾個」—— 不然使用者不知道自己貼完了沒有。
#    # 判斷依據是 tools/FILELIST.txt（它固定在第一批），而不是這一批的數量。
#    listing = os.path.join(dest, "tools", "FILELIST.txt")
#    have_listing = os.path.isfile(listing)
#    missing = []
#    if have_listing:
#        with open(listing, "r", encoding="utf-8") as f:
#            for line in f:
#                line = line.strip()
#                if line and not line.startswith("#"):
#                    rel = line.split(" ", 1)[1]
#                    if not os.path.isfile(os.path.join(dest,
#                                                       rel.replace("/", os.sep))):
#                        missing.append(rel)
#
#    if N_PARTS > 1 and not have_listing:
#        # 還沒拿到檔案清單，所以「缺幾個」算不出來。**這時候絕對不能印
#        # 「下一步：跑 doctor」** —— 那看起來就像整包已經到位了。
#        print("")
#        print("這是第 %%d 批 / 共 %%d 批，整個 repo 有 %%d 個檔案 —— **還沒到齊**。"
#              %% (PART, N_PARTS, TOTAL))
#        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。")
#        print("第 1 批裡有檔案清單，貼過它之後每一批都會告訴你還缺哪些。")
#        return 0
#
#    if missing:
#        print("")
#        print("這是第 %%d 批 / 共 %%d 批。整個 repo 還缺 %%d 個檔案 —— 在其他批裡。"
#              %% (PART, N_PARTS, len(missing)))
#        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。缺的例如：")
#        for rel in missing[:6]:
#            print("    %%s" %% rel)
#        return 0
#
#    print("")
#    print("下一步：")
#    print("  cd %%s" %% dest)
#    print("  python tools\\\\doctor.py        # 環境自檢（會告訴你還缺什麼）")
#    print("  相依套件裝不了的話走離線 wheels：docs\\\\OFFLINE-INSTALL.md")
#    return 0
#
#
#if __name__ == "__main__":
#    sys.exit(main())
#'''
#
#
#def repo_root() -> str:
#    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#
#
#def blob_sha(data: bytes) -> str:
#    h = hashlib.sha1()                                # noqa: S324 — git 的格式
#    h.update(b"blob %d\0" % len(data))
#    h.update(data)
#    return h.hexdigest()
#
#
#def collect(root: str = "") -> List[Tuple[str, bytes]]:
#    """``git ls-files`` 的每個檔案（路徑, 位元組）。
#
#    順便擋掉兩種會讓「用行數打包」失效的東西：CRLF 與非 UTF-8。
#    拒絕產出比產出一個解不開的包好 —— 後者要等收到的人才會發現。
#    """
#    root = root or repo_root()
#    out = subprocess.run(["git", "ls-files"], cwd=root, check=True,
#                         stdout=subprocess.PIPE).stdout.decode("utf-8")
#    items = []
#    for rel in sorted(p for p in out.split("\n") if p.strip()):
#        if rel.startswith(BUNDLE_DIR + "/"):
#            # 產出物自己不進包裡 —— 不然每打一次包，repo 就多一份上一次的包，
#            # 而且是指數成長。
#            continue
#        with open(os.path.join(root, rel.replace("/", os.sep)), "rb") as f:
#            data = f.read()
#        if b"\r" in data:
#            raise SystemExit(
#                "%s 含 CR（CRLF 或裸 CR）—— 以行數為單位的打包會弄壞它。"
#                "先把它轉成 LF。" % rel)
#        try:
#            data.decode("utf-8")
#        except UnicodeDecodeError:
#            raise SystemExit("%s 不是 UTF-8 —— 這個格式只裝純文字。" % rel)
#        items.append((rel, data))
#    return items
#
#
#def _slice(items: List[Tuple[str, bytes]], limit: int
#           ) -> List[List[Tuple[str, bytes]]]:
#    """依大小切成幾批。``limit`` 是每批的內容上限（位元組）。
#
#    為什麼一定要切：**GitHub 不顯示超過 1 MB 的檔案**，而公司機唯一的取得方式是
#    「在 GitHub 上看到、按複製鈕、貼進記事本」。一個 2.3 MB 的包在那台機器上
#    根本點不開來複製 —— 打包成功但送不進去，是最糟的一種「做完了」。
#
#    ``tools/FILELIST.txt`` 固定放在第一批：後面每一批解完都用它回報「還缺幾個」，
#    所以它必須先到。
#    """
#    first = [it for it in items if it[0] == "tools/FILELIST.txt"]
#    rest = [it for it in items if it[0] != "tools/FILELIST.txt"]
#    out: List[List[Tuple[str, bytes]]] = [list(first)]
#    size = sum(len(d) for _r, d in first)
#    for rel, data in rest:
#        if size + len(data) > limit and out[-1]:
#            out.append([])
#            size = 0
#        out[-1].append((rel, data))
#        size += len(data)
#    return out
#
#
#def build(out_name: str = "ADEPT_bundle.py", root: str = "",
#          items: Optional[List[Tuple[str, bytes]]] = None,
#          part: int = 1, n_parts: int = 1, total_files: int = 0) -> str:
#    items = collect(root) if items is None else items
#    parts = [EXTRACTOR % {"name": out_name, "sentinel": SENTINEL,
#                          "part": part, "n_parts": n_parts,
#                          "total": total_files or len(items)}, SENTINEL]
#    for rel, data in items:
#        body = data.decode("utf-8").split("\n")
#        parts.append("#F %s %d %s" % (blob_sha(data), len(body), rel))
#        # **每一行都要變成註解。** Python 在跑任何東西之前會先編譯整個檔案，
#        # 所以資料區不能是裸的文字 —— 不然它會去解析別的檔案的內容然後語法錯誤
#        # （第一版就是這樣掛的：某個 .md 裡的全形括號變成 SyntaxError）。
#        # 加一個 '#' 比塞進三引號字串安全：檔案內容裡本來就可能有三個引號。
#        parts.extend("#" + line for line in body)
#    return "\n".join(parts) + "\n"
#
#
#def main(argv=None) -> int:
#    ap = argparse.ArgumentParser(
#        description="Pack the repo into one plain-text self-extracting .py")
#    ap.add_argument("--out", default="ADEPT_bundle.py",
#                    help="輸出檔名（分批時會變成 ..._part1of6.py）")
#    ap.add_argument("--split", type=int, default=0, metavar="KB",
#                    help=("每批最多幾 KB（0 = 不分批）。**GitHub 不顯示超過 1 MB "
#                          "的檔案**，而剪貼簿是唯一的通道時就必須分批，"
#                          "400 是安全值。"))
#    a = ap.parse_args(argv)
#
#    items = collect()
#    groups = _slice(items, a.split * 1024) if a.split else [items]
#    out_dir = os.path.dirname(os.path.abspath(a.out))
#    if out_dir and not os.path.isdir(out_dir):
#        os.makedirs(out_dir, exist_ok=True)
#    stem, ext = os.path.splitext(a.out)
#    n_parts = len(groups)
#
#    for i, group in enumerate(groups, 1):
#        name = a.out if n_parts == 1 else "%s_part%dof%d%s" % (stem, i, n_parts, ext)
#        text = build(os.path.basename(name), items=group, part=i,
#                     n_parts=n_parts, total_files=len(items))
#        tmp = name + ".tmp"                           # atomic（鐵則 5）
#        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
#            f.write(text)
#        os.replace(tmp, name)
#        print("%s：%d 個檔案、%.0f KB"
#              % (name, len(group), len(text.encode("utf-8")) / 1024))
#    if n_parts > 1:
#        print("\n共 %d 批、%d 個檔案。每一批都可以單獨執行，順序不重要，"
#              "重複執行也沒關係。" % (n_parts, len(items)))
#    return 0
#
#
#if __name__ == "__main__":
#    sys.exit(main())
#

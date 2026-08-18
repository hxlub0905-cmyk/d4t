# F11 Region-3 第 2 步：GLAS 匯出掛成一條影像流。
"""這一份鎖住的是**配對與快取**，不是「檔案讀得進來」。

三件會安靜出錯的事：

1. **配對用 manifest 的 ``label_png`` 欄位，不是自己拼檔名。** GLAS 的
   ``_safe_name`` 會把非 ``[A-Za-z0-9-_.]`` 的字元換成底線 —— 自己拼的話
   乾淨的 id 會過、髒的會**安靜地**對不上。
2. **附加檔不准混進 ``DefectItem.images``。** ``load_single`` 的契約建立在
   「一顆幾張」上，混進去的話每一顆 RSEM defect 都會突然變成兩張而載不進來。
3. **換一份匯出，快取要失效。** 有 KLARF 的時候 lot token 只看 KLARF 的 stat，
   而換 mask 目錄不會動到 KLARF —— 那會讓影像段快取把**上一份匯出算出來的框**
   餵回來（鐵則 9 講的正是這個形狀）。
"""
from __future__ import annotations

import json
import os
import re
import struct
import sys
import zlib
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import adept.core.steps  # noqa: F401,E402 — 觸發卡片註冊
from adept.core.ingest import glas_export  # noqa: E402
from adept.core.ingest.dataset import Dataset, DefectItem, ImageRef  # noqa: E402
from adept.core.pipeline import get_step  # noqa: E402
from adept.core.pipeline.batch import _dataset_token_for  # noqa: E402
from adept.core.pipeline.context import Context  # noqa: E402
from adept.core.pipeline.step import StepError  # noqa: E402


def _png(path, rows, color_type=0):
    """最小 PNG 寫出器（測試不靠 OpenCV）。"""
    per = {0: 1, 2: 3}[color_type]
    raw = b"".join(b"\x00" + bytes(r) for r in rows)

    def chunk(kind, data):
        c = kind + data
        return (struct.pack(">I", len(data)) + c
                + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", len(rows[0]) // per, len(rows), 8,
                       color_type, 0, 0, 0)
    Path(path).write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _label(w=8, h=6):
    rows = [[0] * w for _ in range(h)]
    for y in range(1, 3):
        for x in range(1, 4):
            rows[y][x] = 1
    for y in range(3, 5):
        for x in range(4, 7):
            rows[y][x] = 2
    return rows


def _export(tmp_path, rows, layers=("L17/D0", "L21/D0"), name="export"):
    """``rows`` 是 ``[(image_id, 檔名 or "" or None), …]``。
    ``None`` = manifest 寫了檔名但檔案不存在。"""
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    images = []
    for image_id, fname in rows:
        # ``None`` = manifest 寫了檔名、檔案卻不在（跟 ``""`` = 被分數門檻擋掉
        # 是**兩種不同的情況**，處置也不同）。
        declared = "%s_label.png" % image_id if fname is None else fname
        if fname:
            _png(d / fname, _label())
        images.append({"image_id": image_id, "label_png": declared,
                       "status": "ok", "id_source": "klarf-defectid",
                       "width_px": 8, "height_px": 6})
    doc = {"schema": "mmh-gds-overlay-v4",
           "columns": ["image_id", "label_png", "status", "id_source",
                       "width_px", "height_px"],
           "images": images}
    if layers:
        doc["label_map"] = [{"id": i + 1, "layer": n, "fg_glv": 200}
                            for i, n in enumerate(layers)]
    (d / "overlay_manifest.json").write_text(json.dumps(doc), encoding="utf-8")
    return str(d)


def _lot(tmp_path, ids, klarf=True):
    """一個最小的 Dataset（不必真的有影像 —— 這一份測的是配對與 token）。"""
    img = tmp_path / "img.png"
    if not img.exists():
        _png(img, [[7] * 4 for _ in range(4)])
    items = [DefectItem(defect_id=str(i), die=None, xrel_nm=None,
                        yrel_nm=None,
                        images={"single": ImageRef(str(img), None, "single")})
             for i in ids]
    doc = None
    if klarf:
        src = tmp_path / "LOT_SYN.001"
        src.write_text("x", encoding="utf-8")

        class _Doc:                       # 只需要 source_path
            source_path = str(src)
        doc = _Doc()
    return Dataset(kind="rsem", klarf=doc, items=items)


# --------------------------------------------------------------------------- #
# 1. 配對
# --------------------------------------------------------------------------- #
def test_it_pairs_on_the_defect_id(tmp_path):
    ds = _lot(tmp_path, ["1", "2", "3"])
    rep = glas_export.attach(
        ds, _export(tmp_path, [("1", "1_label.png"), ("2", "2_label.png"),
                               ("3", "3_label.png")]))
    assert rep.matched == 3 and rep.ok
    assert all("layout_label" in i.sidecars for i in ds.items)
    assert [n for _i, n in rep.layers] == ["L17/D0", "L21/D0"]


def test_the_filename_comes_from_the_manifest_not_from_the_id(tmp_path):
    """GLAS 的 ``_safe_name`` 把 ``a/b`` 寫成 ``a_b_label.png``。

    自己拼 ``<id>_label.png`` 的話，乾淨的 id 會過、髒的會**安靜地**對不上 ——
    那種 bug 的症狀是「有些 defect 沒有區域」，而沒有任何訊息說得出為什麼。
    """
    ds = _lot(tmp_path, ["a/b"])
    rep = glas_export.attach(ds, _export(tmp_path, [("a/b", "a_b_label.png")]))
    assert rep.matched == 1
    assert ds.items[0].sidecars["layout_label"].path.endswith("a_b_label.png")


def test_a_row_with_no_label_is_counted_not_an_error(tmp_path):
    """GLAS 的分數門檻本來就會擋掉一些 —— 那是正常的，不是壞掉。"""
    ds = _lot(tmp_path, ["1", "2"])
    rep = glas_export.attach(ds, _export(tmp_path, [("1", "1_label.png"),
                                                    ("2", "")]))
    assert (rep.matched, rep.gated) == (1, 1)
    assert "layout_label" not in ds.items[1].sidecars
    assert "gated" in rep.summary()


def test_a_named_file_that_is_not_there_is_counted(tmp_path):
    ds = _lot(tmp_path, ["1", "2"])
    rep = glas_export.attach(ds, _export(tmp_path, [("1", "1_label.png"),
                                                    ("2", None)]))
    assert rep.matched == 1 and rep.missing_file == 1 and rep.gated == 0
    assert "not there" in rep.summary()


def test_both_directions_of_mismatch_are_reported(tmp_path):
    ds = _lot(tmp_path, ["1", "2"])
    rep = glas_export.attach(ds, _export(tmp_path, [("1", "1_label.png"),
                                                    ("9", "9_label.png")]))
    assert rep.defects_without_row == 1     # lot 有 2，匯出裡沒有
    assert rep.rows_without_defect == 1     # 匯出有 9，lot 裡沒有


def test_matching_nothing_at_all_says_the_join_key(tmp_path):
    """一顆都沒對上，八成是挑錯資料夾 —— 那句話要講得出去查什麼。"""
    ds = _lot(tmp_path, ["1"])
    rep = glas_export.attach(ds, _export(tmp_path, [("9", "9_label.png")]))
    assert not rep.ok
    assert any("DEFECTID" in w for w in rep.warnings)


# --------------------------------------------------------------------------- #
# 2. 挑錯資料夾要**當場**知道
# --------------------------------------------------------------------------- #
def test_a_folder_with_no_manifest_is_refused_up_front(tmp_path):
    d = tmp_path / "nope"
    d.mkdir()
    with pytest.raises(glas_export.GlasExportError) as e:
        glas_export.attach(_lot(tmp_path, ["1"]), str(d))
    assert "_label.png" in str(e.value), "要講得出該挑哪一個資料夾"


def test_a_manifest_with_the_wrong_schema_is_refused(tmp_path):
    d = tmp_path / "other"
    d.mkdir()
    (d / "overlay_manifest.json").write_text(
        json.dumps({"schema": "something-else", "images": []}),
        encoding="utf-8")
    with pytest.raises(glas_export.GlasExportError) as e:
        glas_export.attach(_lot(tmp_path, ["1"]), str(d))
    assert "right folder" in str(e.value)


def test_no_label_map_is_a_warning_with_what_to_do(tmp_path):
    """少了它，label 圖裡的 1、2、3 就沒有名字可以對。"""
    ds = _lot(tmp_path, ["1"])
    rep = glas_export.attach(ds, _export(tmp_path, [("1", "1_label.png")],
                                         layers=()))
    assert rep.matched == 1 and rep.layers == []
    assert any("export ROI label map" in w for w in rep.warnings)


# --------------------------------------------------------------------------- #
# 3. 附加檔不准混進 images
# --------------------------------------------------------------------------- #
def test_the_sidecar_does_not_become_one_of_the_defect_images(tmp_path):
    """``load_single`` 在一顆有兩張時會拒絕載入，而那個拒絕是對的。
    label 混進 ``images`` 的話，每一顆 RSEM defect 都會突然載不進來 ——
    而錯誤訊息會說謊（「這顆有 2 張影像」）。"""
    ds = _lot(tmp_path, ["1"])
    glas_export.attach(ds, _export(tmp_path, [("1", "1_label.png")]))
    item = ds.items[0]
    assert list(item.images) == ["single"]
    assert list(item.sidecars) == ["layout_label"]


# --------------------------------------------------------------------------- #
# 4. 換一份匯出，快取要失效（鐵則 9）
# --------------------------------------------------------------------------- #
def test_swapping_the_export_changes_the_lot_token(tmp_path):
    """**有 KLARF 的時候 token 只看 KLARF 的 stat**，而換 mask 目錄不會動到
    KLARF。少了這一段，影像段快取會把上一份匯出算出來的框餵回來 ——
    跑得完、有數字、而且是錯的。"""
    a = _export(tmp_path, [("1", "1_label.png")], name="a")
    b = _export(tmp_path, [("1", "1_label.png")], name="b")

    ds_a = _lot(tmp_path, ["1"])
    glas_export.attach(ds_a, a)
    ds_b = _lot(tmp_path, ["1"])
    glas_export.attach(ds_b, b)
    assert _dataset_token_for(ds_a) != _dataset_token_for(ds_b)


def test_a_lot_with_no_export_keeps_exactly_the_old_token(tmp_path):
    """沒有 sidecar 時 token 要**逐字元不變** —— 既有的快取目錄與黃金值
    不能因為多了這個機制而全部失效。"""
    from adept.core.pipeline.cache import dataset_token

    ds = _lot(tmp_path, ["1", "2"])
    assert _dataset_token_for(ds) == dataset_token(ds.klarf.source_path)


def test_the_token_moves_when_the_label_file_itself_changes(tmp_path):
    d = _export(tmp_path, [("1", "1_label.png")])
    ds = _lot(tmp_path, ["1"])
    glas_export.attach(ds, d)
    before = _dataset_token_for(ds)
    rows = _label()
    rows[0][0] = 2                                  # 改一個像素
    _png(os.path.join(d, "1_label.png"), rows)
    assert _dataset_token_for(ds) != before


def test_a_lot_without_a_klarf_also_folds_the_sidecar_in(tmp_path):
    """folder 模式走的是另一條路（各 item 影像來源的 sha1）——
    兩條路都要接上，不然只有一半的資料集受保護。"""
    a, b = (_export(tmp_path, [("1", "1_label.png")], name=n) for n in "ab")
    ds_a, ds_b = _lot(tmp_path, ["1"], klarf=False), _lot(tmp_path, ["1"],
                                                          klarf=False)
    glas_export.attach(ds_a, a)
    glas_export.attach(ds_b, b)
    assert _dataset_token_for(ds_a) != _dataset_token_for(ds_b)


# --------------------------------------------------------------------------- #
# 5. 卡片
# --------------------------------------------------------------------------- #
def _ctx_with(tmp_path, rows=None, color_type=0):
    ds = _lot(tmp_path, ["1"])
    d = _export(tmp_path, [("1", "1_label.png")])
    if rows is not None:
        _png(os.path.join(d, "1_label.png"), rows, color_type=color_type)
    glas_export.attach(ds, d)
    ctx = Context(images={})
    ctx.meta["_defect_item"] = ds.items[0]
    return ctx


def test_the_card_writes_the_stream_and_touches_nothing(tmp_path):
    """label 的像素值**是** id。任何拉伸／正規化／通道平均都會把 1、2、3 混成
    不存在的值，**而且不會報錯**。"""
    ctx = _ctx_with(tmp_path)
    get_step("load_sidecar")().run(ctx, {"out": "layout_label"})
    arr = ctx.images["layout_label"]
    assert arr.dtype == np.uint8
    assert sorted(np.unique(arr).tolist()) == [0, 1, 2]
    assert arr.shape == (6, 8)


def test_the_card_declares_the_name_the_user_typed(tmp_path):
    card = get_step("load_sidecar")
    assert card.resolve_writes({"out": "gds"}) == ["gds"]
    ctx = _ctx_with(tmp_path)
    card().run(ctx, {"out": "gds"})
    assert "gds" in ctx.images and "layout_label" not in ctx.images


def test_a_defect_with_no_label_says_both_possible_reasons(tmp_path):
    """「沒掛匯出」跟「這一顆被 GLAS 擋掉了」的下一步完全不同。"""
    ds = _lot(tmp_path, ["1"])
    ctx = Context(images={})
    ctx.meta["_defect_item"] = ds.items[0]
    with pytest.raises(StepError) as e:
        get_step("load_sidecar")().run(ctx, {"out": "layout_label"})
    text = str(e.value)
    assert "no GLAS export is attached" in text and "score" in text
    assert "rest of the batch" in text


def test_a_three_channel_label_names_the_file_it_probably_is(tmp_path):
    """3 通道的多半是 ``*_label_view.png``（GLAS 給人看的上色版）——
    載進去的話 id 會被混掉，而且不會報錯。"""
    rows = [[v for value in r for v in (value, value, value)]
            for r in _label()]
    ctx = _ctx_with(tmp_path, rows=rows, color_type=2)
    with pytest.raises(StepError) as e:
        get_step("load_sidecar")().run(ctx, {"out": "layout_label"})
    assert "_label_view.png" in str(e.value)


def test_the_panel_gets_what_it_needs_to_show_which_layers_landed(tmp_path):
    """「某一層是 0 個像素」跟「沒有那一層」在畫面上長得一樣 —— 要分得出來。"""
    ctx = _ctx_with(tmp_path)
    get_step("load_sidecar")().run(ctx, {"out": "layout_label"})
    rec = ctx.meta["layout_label"]["layout_label"]
    assert rec["ids"] == [0, 1, 2]
    assert rec["shape"] == [6, 8]
    assert rec["share"][1] == pytest.approx(6 / 48.0)


def test_the_card_is_an_input_card_with_no_inputs(tmp_path):
    """畫布上它是一個**來源**：沒有輸入埠，一個輸出埠。"""
    from adept.core.pipeline.step import GROUP_INPUT

    card = get_step("load_sidecar")
    assert card.group == GROUP_INPUT
    assert card.resolve_reads({}) == []

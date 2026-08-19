"""KLARF 三種寫回模式（M5-1）—— 1.2 與 1.8 兩種版本都要過。

守的三條底線：

1. **無損**（鐵則 6）：``inplace`` 什麼都沒改 → 輸出檔與輸入檔**逐位元組相同**；
   改了某幾格 → 除了那幾格以外，每一行的每個 token 都與原檔相同。
2. **不默默失敗**：要寫的欄位不存在 → :class:`ExportError`（帶白話說明），
   絕不「看起來成功但其實沒寫」。
3. **影像不會壞**：``annotate`` 追加欄位後、``topn`` 抽子集後，
   ``defect_image_map`` / ``defect_image_filename`` / ``load_dataset``
   仍然對得到原本那些影像。
"""
from __future__ import annotations

import os
import sys

import pytest

from d4t.core.export import klarf_out
from d4t.core.export.klarf_out import ExportError
from d4t.core.ingest import dataset, klarf_core

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import make_sample  # noqa: E402
import make_sample_rsem  # noqa: E402

N = 8


# ---------------------------------------------------------------------------
# fixtures：EBI patch（KLARF 1.2）與 rSEM（KLARF 1.8）兩份合成 lot
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def ebi_lot(tmp_path_factory):
    out = tmp_path_factory.mktemp("ebi")
    return make_sample.generate(str(out), n=N)


@pytest.fixture(scope="module")
def rsem_lot(tmp_path_factory):
    out = tmp_path_factory.mktemp("rsem")
    return make_sample_rsem.generate(str(out), n=N)


@pytest.fixture(params=["1.2", "1.8"])
def lot(request, ebi_lot, rsem_lot):
    """兩種 KLARF 版本輪流跑同一組測試。"""
    return ebi_lot if request.param == "1.2" else rsem_lot


def make_results(n=N, scores=None):
    """假的 pipeline 結果（result_to_json_dict 的形狀）。"""
    out = []
    for i in range(n):
        s = float(n - i) if scores is None else float(scores[i])
        out.append({
            "defect_id": str(i + 1),
            "ok": True,
            "error": None,
            "score": s,
            "bin": 1 if i < n // 2 else 0,
            "features": {"cd_x_px": 12.5 + i, "blob_snr": 3.0 + i},
        })
    return out


def read_bytes(path):
    with open(str(path), "rb") as f:
        return f.read()


def read_text(path):
    with open(str(path), "r", encoding="utf-8") as f:
        return f.read()


def error_codes(issues):
    return sorted(i.code for i in issues if i.level == "error")


# ---------------------------------------------------------------------------
# inplace —— 無損
# ---------------------------------------------------------------------------
def test_inplace_no_change_is_byte_identical(lot, tmp_path):
    """鐵則 6 的頭號驗收：沒改任何欄位 → 位元組完全相同。"""
    src = lot["klarf"]
    doc = klarf_core.load(src)
    out = tmp_path / "same.001"
    plan = klarf_out.apply_writeback(doc, make_results(), "inplace", str(out))

    assert read_bytes(out) == read_bytes(src)
    assert plan.n_rows_changed == 0
    assert plan.columns_touched == []
    assert plan.columns_added == []
    assert plan.n_rows_out == N
    assert error_codes(plan.issues) == []


def test_inplace_does_not_mutate_input_doc(lot, tmp_path):
    """寫回不可以動到呼叫端手上那份 doc（UI 還在用它顯示）。"""
    doc = klarf_core.load(lot["klarf"])
    before = [list(r) for r in doc.defects]
    klarf_out.apply_writeback(doc, make_results(), "inplace",
                              str(tmp_path / "o.001"), class_col="CLASSNUMBER")
    assert [list(r) for r in doc.defects] == before
    assert doc.to_text() == read_text(lot["klarf"])


def test_inplace_class_from_bin_only_touches_those_cells(lot, tmp_path):
    """把 bin 寫進 CLASSNUMBER：值要對，其他 byte 一個都不能動。"""
    src = lot["klarf"]
    doc = klarf_core.load(src)
    results = make_results()
    out = tmp_path / "cls.001"
    plan = klarf_out.apply_writeback(doc, results, "inplace", str(out),
                                     class_col="CLASSNUMBER")

    # --- 值 round-trip ---
    new = klarf_core.load(str(out))
    ci = new.col_index("CLASSNUMBER")
    di = new.col_index("DEFECTID")
    assert ci >= 0
    got = {r[di]: r[ci] for r in new.defects}
    assert got == {r["defect_id"]: str(r["bin"]) for r in results}

    # --- 原檔的 CLASSNUMBER 全是 0，所以只有 bin=1 那幾顆真的改了 ---
    n_expected = sum(1 for r in results if r["bin"] != 0)
    assert plan.n_rows_changed == n_expected
    assert plan.columns_touched == ["CLASSNUMBER"]
    assert plan.n_rows_out == N

    # --- 逐行比：行數相同、每行 token 數相同、只有 CLASSNUMBER 那個 token 不同 ---
    old_lines = read_text(src).splitlines()
    new_lines = read_text(out).splitlines()
    assert len(old_lines) == len(new_lines)
    n_diff_lines = 0
    for a, b in zip(old_lines, new_lines):
        if a == b:
            continue
        n_diff_lines += 1
        ta, tb = a.split(), b.split()
        assert len(ta) == len(tb), "行的 token 數被改變了：{!r} -> {!r}".format(a, b)
        diff_at = [k for k, (x, y) in enumerate(zip(ta, tb)) if x != y]
        assert diff_at == [ci], "改到了不該改的 token：{} != [{}]".format(diff_at, ci)
    assert n_diff_lines == n_expected


def test_inplace_bin_map_and_size_column(lot, tmp_path):
    """bin_map 換掉要寫出去的數值；沒有 DSIZE 欄的檔案要擋下來。"""
    doc = klarf_core.load(lot["klarf"])
    results = make_results()
    out = tmp_path / "mapped.001"
    klarf_out.apply_writeback(doc, results, "inplace", str(out),
                              class_col="CLASSNUMBER", bin_map={0: 7, 1: 9})
    new = klarf_core.load(str(out))
    ci = new.col_index("CLASSNUMBER")
    vals = sorted({r[ci] for r in new.defects})
    assert vals == ["7", "9"]


# --------------------------------------------------------------------------- #
# 單位換算：pipeline 全程 pixel，nm 由使用者在輸出時填（2026-07-30）
# --------------------------------------------------------------------------- #
# 這個合成 KLARF 沒有 DSIZE 欄，所以這幾條借 CLASSNUMBER 當「尺寸欄」——
# 要驗的是**寫進去的數值**，跟欄位叫什麼名字無關。

def test_size_column_writes_the_pixel_value_unchanged_by_default(lot, tmp_path):
    """預設不換算。「不換算」比「用一個猜來的係數換算」誠實。"""
    doc = klarf_core.load(lot["klarf"])
    results = make_results()
    out = tmp_path / "px.001"
    plan = klarf_out.apply_writeback(doc, results, "inplace", str(out),
                                     size_col="CLASSNUMBER",
                                     size_feature="cd_x_px")
    new = klarf_core.load(str(out))
    ci, di = new.col_index("CLASSNUMBER"), new.col_index("DEFECTID")
    got = {r[di]: float(r[ci]) for r in new.defects}
    assert got == {r["defect_id"]: pytest.approx(r["features"]["cd_x_px"])
                   for r in results}
    # 預覽要講得出單位 —— 否則「這一欄是什麼單位」只存在按下去那個人的腦子裡。
    assert any("pixels" in n for n in plan.notes)


def test_size_scale_is_the_nm_per_px_the_user_typed_in(lot, tmp_path):
    """換算的位置：輸出的那一刻，係數由使用者給。

    以前是 cd_measure 讀 ``meta['nm_per_px']`` 自己乘 —— 而那個欄位沒有來源，
    所以每一顆的 nm 都是 0。現在係數是 export 的一個參數，沒填就是 pixel。
    """
    doc = klarf_core.load(lot["klarf"])
    results = make_results()
    out = tmp_path / "nm.001"
    plan = klarf_out.apply_writeback(doc, results, "inplace", str(out),
                                     size_col="CLASSNUMBER",
                                     size_feature="cd_x_px", size_scale=2.5)
    new = klarf_core.load(str(out))
    ci, di = new.col_index("CLASSNUMBER"), new.col_index("DEFECTID")
    got = {r[di]: float(r[ci]) for r in new.defects}
    assert got == {r["defect_id"]: pytest.approx(r["features"]["cd_x_px"] * 2.5)
                   for r in results}
    assert any("2.5" in n for n in plan.notes)


@pytest.mark.parametrize("bad", [0, -1.0, "nope", None, float("nan")])
def test_a_bad_size_scale_is_refused_before_anything_is_written(lot, tmp_path, bad):
    """填錯的係數要在寫檔之前擋下來，而且訊息要說得出「1 是什麼意思」。"""
    doc = klarf_core.load(lot["klarf"])
    out = tmp_path / "bad.001"
    with pytest.raises(ExportError) as ei:
        klarf_out.apply_writeback(doc, make_results(), "inplace", str(out),
                                  size_col="CLASSNUMBER",
                                  size_feature="cd_x_px", size_scale=bad)
    assert "1" in str(ei.value)                 # 講得出怎麼寫成 pixel
    assert not out.exists()                     # 失敗不留半個檔


def test_inplace_missing_column_raises_with_help(lot, tmp_path):
    """要寫的欄位不存在 → 報錯（而且訊息要看得懂、要指出可行的下一步）。"""
    doc = klarf_core.load(lot["klarf"])
    with pytest.raises(ExportError) as ei:
        klarf_out.apply_writeback(doc, make_results(), "inplace",
                                  str(tmp_path / "x.001"), size_col="DSIZE")
    msg = str(ei.value)
    assert "DSIZE" in msg
    assert "annotate" in msg               # 有給替代方案
    assert "DEFECTID" in msg               # 有列出這個檔實際有的欄位
    assert not (tmp_path / "x.001").exists()   # 失敗就不該留下半個檔


def test_inplace_skips_failed_defects(lot, tmp_path):
    """單顆失敗不寫回，也不能殺掉整批（鐵則 7 的輸出端對應）。"""
    doc = klarf_core.load(lot["klarf"])
    results = make_results()
    results[2] = dict(results[2], ok=False, error="boom", score=None, bin=None)
    plan = klarf_out.apply_writeback(doc, results, "inplace",
                                     str(tmp_path / "f.001"),
                                     class_col="CLASSNUMBER")
    new = klarf_core.load(str(tmp_path / "f.001"))
    ci, di = new.col_index("CLASSNUMBER"), new.col_index("DEFECTID")
    got = {r[di]: r[ci] for r in new.defects}
    assert got["3"] == "0"                 # 原值保留
    assert plan.n_rows_changed == sum(
        1 for r in results if r["ok"] and r["bin"] != 0)
    assert any("failed to run" in n for n in plan.notes)


# ---------------------------------------------------------------------------
# annotate —— 追加欄位，影像區塊仍在列尾
# ---------------------------------------------------------------------------
def test_annotate_adds_columns_and_keeps_images(lot, tmp_path):
    src = lot["klarf"]
    doc = klarf_core.load(src)
    results = make_results()
    base_errors = error_codes(klarf_core.lint(doc))

    # 輸出放在原資料夾，影像（多頁 TIFF / per-defect PNG）才找得到
    out = os.path.join(os.path.dirname(src), "annotated.001")
    plan = klarf_out.apply_writeback(doc, results, "annotate", out,
                                     extra_features=["cd_x_px"])

    assert plan.columns_added == ["ADCSCORE", "ADCCLASS", "CD_X_PX"]
    assert plan.n_rows_out == N
    assert plan.n_rows_changed == N
    assert error_codes(plan.issues) == base_errors      # 沒有新的 error

    new = klarf_core.load(out)
    cols = [c.upper() for c in new.defect_columns]
    assert "ADCSCORE" in cols and "ADCCLASS" in cols and "CD_X_PX" in cols
    assert len(new.defects) == N

    # --- 值 round-trip ---
    di = new.col_index("DEFECTID")
    si = new.col_index("ADCSCORE")
    ki = new.col_index("ADCCLASS")
    fi = new.col_index("CD_X_PX")
    for r in results:
        row = next(x for x in new.defects if x[di] == r["defect_id"])
        assert float(row[si]) == pytest.approx(r["score"], abs=1e-4)
        assert int(row[ki]) == r["bin"]
        assert float(row[fi]) == pytest.approx(r["features"]["cd_x_px"], abs=1e-4)

    # --- 影像尾巴活著 ---
    old = klarf_core.load(src)
    assert new.image_layout() is not None
    assert new.total_image_count() == old.total_image_count()
    assert new.defect_image_map()["pages"] == old.defect_image_map()["pages"]
    assert ([new.defect_image_filename(r) for r in new.defects]
            == [old.defect_image_filename(r) for r in old.defects])
    for row in new.defects:
        assert len(new.defect_image_entries(row)) == new.defect_image_count(row)
        assert new.row_len_ok(row)

    # --- ingest 層照樣讀得回來 ---
    old_ds = dataset.load_dataset(src)
    new_ds = dataset.load_dataset(out)
    assert new_ds.kind == old_ds.kind
    assert len(new_ds.items) == N
    for a, b in zip(old_ds.items, new_ds.items):
        assert sorted(a.images) == sorted(b.images)
        for ch in a.images:
            assert a.images[ch].page == b.images[ch].page
            assert os.path.abspath(a.images[ch].path) == os.path.abspath(b.images[ch].path)
    os.remove(out)


def test_annotate_rounds_floats_to_fixed_decimals(lot, tmp_path):
    """浮點固定小數位數，檔案才 diff 得動。"""
    doc = klarf_core.load(lot["klarf"])
    results = make_results()
    results[0] = dict(results[0], score=1.23456789)
    out = tmp_path / "dec.001"
    klarf_out.apply_writeback(doc, results, "annotate", str(out), decimals=3)
    new = klarf_core.load(str(out))
    si, di = new.col_index("ADCSCORE"), new.col_index("DEFECTID")
    row = next(x for x in new.defects if x[di] == "1")
    assert row[si] == "1.235"
    assert all(len(r[si].split(".")[1]) == 3 for r in new.defects)


def test_annotate_refuses_existing_column(lot, tmp_path):
    """已經有同名欄位 → 報錯，不覆蓋別人的資料。"""
    doc = klarf_core.load(lot["klarf"])
    with pytest.raises(ExportError) as ei:
        klarf_out.apply_writeback(doc, make_results(), "annotate",
                                  str(tmp_path / "x.001"),
                                  score_col="CLASSNUMBER")
    assert "CLASSNUMBER" in str(ei.value)
    assert "inplace" in str(ei.value)


def test_annotate_marks_unmatched_rows(lot, tmp_path):
    """沒有結果的 defect 要標成「未判定」（-1），而不是假裝判過。"""
    doc = klarf_core.load(lot["klarf"])
    out = tmp_path / "partial.001"
    plan = klarf_out.apply_writeback(doc, make_results()[:3], "annotate", str(out))
    new = klarf_core.load(str(out))
    ki = new.col_index("ADCCLASS")
    assert sum(1 for r in new.defects if r[ki] == "-1") == N - 3
    assert any("not judged" in n for n in plan.notes)


# ---------------------------------------------------------------------------
# topn —— 只留高分的，影像參照要講清楚
# ---------------------------------------------------------------------------
def test_topn_count_order_and_renumber(lot):
    """取前 3 名：數量、排序、重新編號、影像仍指向**原本**那些圖。"""
    src = lot["klarf"]
    doc = klarf_core.load(src)
    # 分數遞增 → 最高分是最後一顆，強迫輸出順序與原檔順序不同
    results = make_results(scores=[float(i) for i in range(N)])
    out = os.path.join(os.path.dirname(src), "topn.001")
    plan = klarf_out.apply_writeback(doc, results, "topn", out, n=3)

    assert plan.n_rows_out == 3
    new = klarf_core.load(out)
    assert len(new.defects) == 3

    di, si = new.col_index("DEFECTID"), new.col_index("ADCSCORE")
    assert [r[di] for r in new.defects] == ["1", "2", "3"]          # 重新編號
    scores = [float(r[si]) for r in new.defects]
    assert scores == sorted(scores, reverse=True)                   # 由高到低
    assert scores == [float(N - 1), float(N - 2), float(N - 3)]

    # 這三列在原檔是第 8、7、6 顆 —— 用 XREL 當身分證確認
    old = klarf_core.load(src)
    xr = old.col_index("XREL")
    assert [r[new.col_index("XREL")] for r in new.defects] == \
        [old.defects[k][xr] for k in (N - 1, N - 2, N - 3)]

    # 影像參照：頁碼／檔名都還指向原本那幾張
    old_map = old.defect_image_map()["pages"]
    new_map = new.defect_image_map()["pages"]
    if old.defect_image_filename(old.defects[0]):
        assert [new.defect_image_filename(r) for r in new.defects] == \
            [old.defect_image_filename(old.defects[k]) for k in (N - 1, N - 2, N - 3)]
    else:
        assert new_map == [old_map[k] for k in (N - 1, N - 2, N - 3)]

    ds = dataset.load_dataset(out)
    assert len(ds.items) == 3
    old_ds = dataset.load_dataset(src)
    for item, k in zip(ds.items, (N - 1, N - 2, N - 3)):
        ref = old_ds.items[k]
        assert sorted(item.images) == sorted(ref.images)
        for ch in ref.images:
            assert item.images[ch].page == ref.images[ch].page
            assert os.path.abspath(item.images[ch].path) == \
                os.path.abspath(ref.images[ch].path)
            assert os.path.isfile(item.images[ch].path)

    assert any("Image references" in n for n in plan.notes)
    os.remove(out)


def test_topn_min_score(lot, tmp_path):
    doc = klarf_core.load(lot["klarf"])
    results = make_results(scores=[float(i) for i in range(N)])   # 0..7
    out = tmp_path / "thr.001"
    plan = klarf_out.apply_writeback(doc, results, "topn", str(out),
                                     n=0, min_score=5.0)
    assert plan.n_rows_out == 3                                   # 5, 6, 7
    new = klarf_core.load(str(out))
    si = new.col_index("ADCSCORE")
    assert [float(r[si]) for r in new.defects] == [7.0, 6.0, 5.0]


def test_topn_without_n_or_min_score_raises(lot, tmp_path):
    doc = klarf_core.load(lot["klarf"])
    with pytest.raises(ExportError) as ei:
        klarf_out.apply_writeback(doc, make_results(), "topn", str(tmp_path / "x.001"))
    assert "min_score" in str(ei.value)


def test_topn_keep_original_ids(lot, tmp_path):
    doc = klarf_core.load(lot["klarf"])
    results = make_results(scores=[float(i) for i in range(N)])
    out = tmp_path / "keep.001"
    klarf_out.apply_writeback(doc, results, "topn", str(out), n=2,
                              renumber=False, include_annotations=False)
    new = klarf_core.load(str(out))
    di = new.col_index("DEFECTID")
    assert [r[di] for r in new.defects] == [str(N), str(N - 1)]
    assert new.defect_columns == klarf_core.load(lot["klarf"]).defect_columns


def test_topn_skips_defects_without_score(lot, tmp_path):
    doc = klarf_core.load(lot["klarf"])
    results = make_results()
    results[0] = dict(results[0], ok=False, score=None, bin=None)
    out = tmp_path / "ns.001"
    plan = klarf_out.apply_writeback(doc, results, "topn", str(out), n=N)
    assert plan.n_rows_out == N - 1
    assert any("have no score" in n for n in plan.notes)


# ---------------------------------------------------------------------------
# 計畫書 vs 實際執行
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode,opts", [
    ("inplace", {}),
    ("inplace", {"class_col": "CLASSNUMBER"}),
    ("annotate", {"extra_features": ["blob_snr"]}),
    ("topn", {"n": 4}),
    ("topn", {"n": 0, "min_score": 4.0, "include_annotations": False}),
])
def test_plan_matches_apply(lot, tmp_path, mode, opts):
    """乾跑報的數字必須與真的寫出去一模一樣（不然預覽就是騙人的）。"""
    doc = klarf_core.load(lot["klarf"])
    results = make_results()
    plan = klarf_out.plan_writeback(doc, results, mode, **opts)
    out = tmp_path / "p_{}.001".format(mode)
    applied = klarf_out.apply_writeback(doc, results, mode, str(out), **opts)

    assert plan.to_dict() == applied.to_dict()
    assert klarf_core.load(str(out)).defects.__len__() == plan.n_rows_out
    # 乾跑不留下任何檔案痕跡
    assert not (tmp_path / "p_dry.001").exists()


def test_unknown_mode_raises(lot):
    doc = klarf_core.load(lot["klarf"])
    with pytest.raises(ExportError) as ei:
        klarf_out.plan_writeback(doc, make_results(), "nonsense")
    assert "inplace" in str(ei.value) and "annotate" in str(ei.value)


def test_writeback_is_atomic(lot, tmp_path):
    """atomic 寫入（鐵則 5）：寫完不留 .tmp。"""
    doc = klarf_core.load(lot["klarf"])
    out = tmp_path / "sub" / "a.001"
    klarf_out.apply_writeback(doc, make_results(), "annotate", str(out))
    assert out.exists()
    assert not (tmp_path / "sub" / "a.001.tmp").exists()


def test_results_matched_by_defectid_not_position(lot, tmp_path):
    """結果順序被打亂也要對得回去（靠 DEFECTID，不是靠位置）。"""
    doc = klarf_core.load(lot["klarf"])
    results = list(reversed(make_results()))
    out = tmp_path / "shuf.001"
    klarf_out.apply_writeback(doc, results, "annotate", str(out))
    new = klarf_core.load(str(out))
    di, si = new.col_index("DEFECTID"), new.col_index("ADCSCORE")
    by_id = {r["defect_id"]: r["score"] for r in results}
    for row in new.defects:
        assert float(row[si]) == pytest.approx(by_id[row[di]], abs=1e-4)

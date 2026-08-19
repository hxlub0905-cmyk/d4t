# KLARF variant D 迴歸測試 — authored 2026-07-28 (M5).
"""真實 1.8 KLARF 變體：影像欄是 ImageList 型別（IMAGEINFO）、**不在最後一欄**，
且整份檔案沒有 IMAGECOUNT 欄。

這個變體是 `fab_probe/probe_klarf.py` 在 `tests/fixtures/sample_real.klarf`
（唯一一份真實來源的 KLARF）上發現的：`row_len_ok` 原本用原始 token 數比對欄數，
把 `Images 1 { "a.jpg" "JPG" 1 "24" }` 這個佔 8 個 token 的子區塊當成 8 欄，
於是**每一列都被判定違法**，`lint()` 對一份完全正常的檔案報 rowlen error。

對使用者的影響：Export 精靈在寫回前跑健檢，會對真實檔案跳出嚇人的紅字。

**這份 fixture 的識別碼是遮蔽過的**（Lot／Wafer／機台／device／recipe 名稱／
廠區代號／缺陷分類名稱一律換成合成值，等長替換）。下面每一條斷言看的都是
**結構** —— 版本、欄位佈局、ImageList 在第幾欄、round-trip 逐位元組相同 ——
沒有一條看值，所以遮蔽不影響這支測試想守的東西。
守門的測試在 `tests/test_no_real_fab_data.py`（鐵則 8）。
"""
from __future__ import annotations

from pathlib import Path

from d4t.core.ingest import klarf_core as K

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_real.klarf"


def _doc():
    return K.load(str(FIXTURE))


def test_variant_d_shape():
    """先確認這份 fixture 真的是 variant D（測試前提，變了要知道）。"""
    doc = _doc()
    assert doc.version == "1.8"
    ic, il = doc.image_col_index()
    assert ic < 0, "variant D 的前提：沒有 IMAGECOUNT 欄"
    assert il >= 0, "但有 ImageList 型別的欄（IMAGEINFO）"
    assert il < len(doc.defect_columns) - 1, "而且它不在最後一欄"
    assert doc.image_layout() is None, "image_layout 對這個變體回 None（維持現狀）"


def test_image_block_span_and_effective_len():
    doc = _doc()
    row = doc.defects[0]
    span = doc.image_block_span(row)
    assert span is not None
    start, ntok = span
    assert row[start] in ("Image", "Images")
    assert row[start + ntok - 1] == "}"
    assert ntok > 1
    # 折算後應正好等於欄數
    assert doc.effective_row_len(row) == len(doc.defect_columns)


def test_row_len_ok_no_longer_false_positives():
    doc = _doc()
    bad = [i for i, r in enumerate(doc.defects) if not doc.row_len_ok(r)]
    assert bad == [], f"這些列被誤判為違法：{bad}"


def test_lint_is_clean_on_real_file():
    """整份真實檔案不該有任何 error 等級的健檢問題。"""
    doc = _doc()
    errors = [i for i in K.lint(doc) if i.level == "error"]
    assert not errors, [(i.code, i.title, i.count) for i in errors]


def test_still_lossless():
    doc = _doc()
    original = FIXTURE.read_bytes()
    assert doc.to_text().encode("utf-8", errors="replace") == original or \
        doc.to_text() == original.decode("utf-8", errors="replace"), \
        "未編輯的檔案 to_text() 必須逐位元組還原"


def test_per_defect_image_filename_still_resolves():
    doc = _doc()
    names = [doc.defect_image_filename(r) for r in doc.defects]
    assert all(n for n in names), names
    assert all(n.lower().endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff"))
               for n in names), names


def test_no_regression_on_normal_variants(tmp_path):
    """一般變體（有 IMAGECOUNT、影像欄在最後）的判定不受影響。"""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from make_sample import generate as gen_ebi
    from make_sample_rsem import generate as gen_rsem

    for gen, sub in ((gen_ebi, "ebi"), (gen_rsem, "rsem")):
        paths = gen(str(tmp_path / sub), n=6, seed=3)
        doc = K.load(paths["klarf"])
        bad = [i for i, r in enumerate(doc.defects) if not doc.row_len_ok(r)]
        assert bad == [], f"{sub}: {bad}"
        assert not [i for i in K.lint(doc) if i.level == "error"]

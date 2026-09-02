"""報表匯出（M5-1）：CSV / Excel / summarize。

重點在 :func:`summarize` 的算術 —— 抓漏率與誤殺率是製程工程師拿來決定
「這個 recipe 敢不敢上線」的數字，算錯比不算還糟，所以用手算的
ground truth 明著驗一次。
"""
from __future__ import annotations

import csv

import pytest

from d4t.core.export import report
from d4t.core.export.report import BASE_COLUMNS, UNBINNED_KEY


# ---------------------------------------------------------------------------
# 手工資料：10 顆，前 5 顆是真缺陷、後 5 顆是 nuisance
#   判定（bin 1 = 真缺陷、0 = nuisance）：
#     id 1-4  真缺陷 → 判真   TP = 4
#     id 5    真缺陷 → 判假   FN = 1   （抓漏）
#     id 6,7  nuisance → 判真 FP = 2   （誤殺）
#     id 8-10 nuisance → 判假 TN = 3
#   抓漏率 = 1/5 = 0.2   誤殺率 = 2/5 = 0.4   正確率 = 7/10 = 0.7
# ---------------------------------------------------------------------------
_BINS = {1: 1, 2: 1, 3: 1, 4: 1, 5: 0, 6: 1, 7: 1, 8: 0, 9: 0, 10: 0}
_TRUTH = {i: (i <= 5) for i in range(1, 11)}


def hand_results():
    out = []
    for i in range(1, 11):
        out.append({
            "defect_id": str(i),
            "ok": True,
            "error": None,
            "score": float(i),
            "bin": _BINS[i],
            "features": {"blob_snr": float(i), "cd_x_px": float(i) * 2.0},
        })
    return out


def hand_ground_truth():
    """make_sample.py 的 ground_truth.json 形狀：{id: {"is_real": bool, ...}}。"""
    return {str(i): {"is_real": _TRUTH[i], "type": "syn"} for i in range(1, 11)}


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------
def test_summarize_basic_counts():
    s = report.summarize(hand_results())
    assert s["n_total"] == 10
    assert s["n_ok"] == 10
    assert s["n_fail"] == 0
    assert s["n_scored"] == 10
    assert s["bin_counts"] == {"1": 6, "0": 4}
    assert s["score_min"] == 1.0
    assert s["score_median"] == 5.5
    assert s["score_max"] == 10.0
    assert s["ground_truth"] is None


def test_summarize_feature_stats():
    s = report.summarize(hand_results())
    assert sorted(s["features"]) == ["blob_snr", "cd_x_px"]
    st = s["features"]["blob_snr"]
    assert st["n"] == 10
    assert st["min"] == 1.0
    assert st["median"] == 5.5
    assert st["max"] == 10.0
    assert st["std"] == pytest.approx(2.8722813, abs=1e-6)   # 母體標準差
    assert s["features"]["cd_x_px"]["max"] == 20.0


def test_summarize_handles_failures_and_nan():
    res = hand_results()
    res[0] = dict(res[0], ok=False, error="boom", score=None, bin=None, features={})
    res[1] = dict(res[1], score=float("nan"), features={"blob_snr": float("inf")})
    s = report.summarize(res)
    assert s["n_ok"] == 9 and s["n_fail"] == 1
    assert s["n_scored"] == 8                       # None 與 nan 都不算
    assert s["bin_counts"][UNBINNED_KEY] == 1
    assert s["features"]["blob_snr"]["n"] == 8      # inf 與缺的都不算


def test_summarize_confusion_matrix_arithmetic():
    """抓漏 / 誤殺 的算術明著驗一次。"""
    s = report.summarize(hand_results(), ground_truth=hand_ground_truth())
    gt = s["ground_truth"]

    assert (gt["tp"], gt["fn"], gt["fp"], gt["tn"]) == (4, 1, 2, 3)
    assert gt["n_labelled"] == 10
    assert gt["n_evaluated"] == 10
    assert gt["n_real"] == 5 and gt["n_nuisance"] == 5

    # 抓漏率 = 漏掉的真缺陷 / 真缺陷總數 = 1/5
    assert gt["miss_rate"] == pytest.approx(1.0 / 5.0)
    # 誤殺率 = 被判成真缺陷的 nuisance / nuisance 總數 = 2/5
    assert gt["false_alarm_rate"] == pytest.approx(2.0 / 5.0)
    # 正確率 = (TP + TN) / 有判定的顆數 = 7/10
    assert gt["accuracy"] == pytest.approx(7.0 / 10.0)
    assert gt["tp"] + gt["fn"] + gt["fp"] + gt["tn"] == gt["n_evaluated"]


def test_summarize_accepts_plain_bool_ground_truth():
    """ground_truth 也可以直接是 {id: True/False}。"""
    plain = {str(i): _TRUTH[i] for i in range(1, 11)}
    a = report.summarize(hand_results(), ground_truth=plain)["ground_truth"]
    b = report.summarize(hand_results(),
                         ground_truth=hand_ground_truth())["ground_truth"]
    assert a == b


def test_summarize_positive_bins_override():
    """把 bin 0 當成「真缺陷」→ 混淆矩陣整個反過來。"""
    gt = report.summarize(hand_results(), ground_truth=hand_ground_truth(),
                          positive_bins=[0])["ground_truth"]
    assert (gt["tp"], gt["fn"], gt["fp"], gt["tn"]) == (1, 4, 3, 2)
    assert gt["miss_rate"] == pytest.approx(4.0 / 5.0)


def test_summarize_unlabelled_and_unbinned_excluded():
    res = hand_results()
    res[9] = dict(res[9], bin=None)                     # 有標註但沒判定
    truth = hand_ground_truth()
    del truth["9"]                                      # 有判定但沒標註
    gt = report.summarize(res, ground_truth=truth)["ground_truth"]
    assert gt["n_labelled"] == 9
    assert gt["n_unlabelled"] == 1
    assert gt["n_unbinned"] == 1
    assert gt["n_evaluated"] == 8
    assert (gt["tp"], gt["fn"], gt["fp"], gt["tn"]) == (4, 1, 2, 1)


def test_summarize_empty_results():
    s = report.summarize([])
    assert s["n_total"] == 0 and s["score_median"] is None
    assert s["features"] == {} and s["bin_counts"] == {}


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def test_write_csv_header_rows_and_bom(tmp_path):
    path = tmp_path / "r.csv"
    out = report.write_csv(hand_results(), str(path))
    assert out == str(path)

    with open(out, "rb") as f:
        raw = f.read()
    assert raw.startswith(b"\xef\xbb\xbf")             # utf-8-sig，Excel 直開不亂碼
    assert not (tmp_path / "r.csv.tmp").exists()       # atomic：不留 .tmp

    with open(out, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == list(BASE_COLUMNS) + ["blob_snr", "cd_x_px"]
    assert len(rows) == 11
    assert rows[1] == ["1", "1", "", "1.0", "1", "1.0", "2.0"]
    assert rows[10][0] == "10"


def test_write_csv_feature_union_and_gaps(tmp_path):
    res = [
        {"defect_id": "1", "ok": True, "error": None, "score": 1.0, "bin": 0,
         "features": {"a": 1.0}},
        {"defect_id": "2", "ok": True, "error": None, "score": 2.0, "bin": 1,
         "features": {"b": 2.0}},
    ]
    path = tmp_path / "u.csv"
    report.write_csv(res, str(path))
    with open(str(path), "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == list(BASE_COLUMNS) + ["a", "b"]
    assert rows[1][-2:] == ["1.0", ""]                 # 缺的留空
    assert rows[2][-2:] == ["", "2.0"]


def test_write_csv_without_features(tmp_path):
    path = tmp_path / "n.csv"
    report.write_csv(hand_results(), str(path), include_features=False)
    with open(str(path), "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == list(BASE_COLUMNS)
    assert len(rows[1]) == len(BASE_COLUMNS)


def test_write_csv_failed_defect_row(tmp_path):
    res = hand_results()
    res[0] = dict(res[0], ok=False, error="炸了", score=None, bin=None, features={})
    path = tmp_path / "f.csv"
    report.write_csv(res, str(path))
    with open(str(path), "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1][:5] == ["1", "0", "炸了", "", ""]


def test_write_csv_creates_parent_dir(tmp_path):
    path = tmp_path / "deep" / "sub" / "r.csv"
    report.write_csv(hand_results(), str(path))
    assert path.exists()


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def test_write_excel_has_three_sheets(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "r.xlsx"
    recipe = {"recipe_id": "demo", "description": "測試用",
              "score": {"expr": "blob_snr * 2", "threshold": 6.0,
                        "bins": {"below": 0, "above": 1}},
              "nodes": [{"id": "a"}, {"id": "b"}]}
    out = report.write_excel(hand_results(), str(path),
                             ground_truth=hand_ground_truth(), recipe=recipe)
    assert out == str(path)
    assert not (tmp_path / "r.xlsx.tmp").exists()      # atomic

    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames == ["Summary", "Details", "Feature stats"]

    # --- 明細：標題 + 每顆一列、凍結標題、自動篩選 ---
    ws = wb["Details"]
    header = [c.value for c in ws[1]]
    assert header == list(BASE_COLUMNS) + ["blob_snr", "cd_x_px"]
    assert ws.max_row == 11
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref is not None
    assert [ws.cell(row=r, column=1).value for r in range(2, 12)] == \
        [str(i) for i in range(1, 11)]

    # --- 特徵統計：每個特徵一列 ---
    ws = wb["Feature stats"]
    assert [c.value for c in ws[1]] == ["Feature", "Count", "Minimum", "Median", "Maximum", "Std dev"]
    assert [ws.cell(row=r, column=1).value for r in (2, 3)] == ["blob_snr", "cd_x_px"]
    assert ws.cell(row=2, column=3).value == 1.0
    assert ws.cell(row=2, column=5).value == 10.0

    # --- 摘要：抓漏率 / 誤殺率 / 正確率 + 混淆矩陣都在裡面 ---
    ws = wb["Summary"]
    cells = {}
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=2):
        if row[0].value is not None:
            cells[str(row[0].value)] = row[1].value
    assert cells["Total defects"] == 10
    assert cells["Recipe name"] == "demo"
    assert cells["Score expression"] == "blob_snr * 2"
    assert cells["Threshold"] == 6.0
    hit = [k for k in cells if k.startswith("Miss rate")]
    kill = [k for k in cells if k.startswith("False alarm rate")]
    assert hit and kill
    assert cells[hit[0]] == pytest.approx(0.2)
    assert cells[kill[0]] == pytest.approx(0.4)
    assert cells["Accuracy"] == pytest.approx(0.7)
    assert cells["Actual: real defect"] == 4                   # TP
    assert cells["Actual: nuisance"] == 2                 # FP
    texts = [str(c.value) for row in ws.iter_rows() for c in row if c.value]
    assert "Confusion matrix" in texts


def test_write_excel_without_ground_truth(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "b.xlsx"
    report.write_excel(hand_results(), str(path))
    wb = openpyxl.load_workbook(str(path))
    assert wb.sheetnames == ["Summary", "Details", "Feature stats"]
    texts = [str(c.value) for row in wb["Summary"].iter_rows() for c in row if c.value]
    assert not any(t.startswith("Miss rate") for t in texts)


def test_write_excel_empty_results(tmp_path):
    """一顆都沒有也不能炸（使用者篩到空集合是常態）。"""
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "e.xlsx"
    report.write_excel([], str(path))
    wb = openpyxl.load_workbook(str(path))
    assert wb["Details"].max_row == 1
    assert wb["Summary"].cell(row=3, column=2).value == 0


# ---------------------------------------------------------------------------
# 分母是 0 的那三個比率（CLI 印它們的時候炸過）
# ---------------------------------------------------------------------------
def test_rates_are_none_when_there_is_nothing_to_divide_by():
    """一批裡一顆假點都沒有 → 誤殺率**沒有定義**，回 None 不是 0。

    這不是挑剔：`d4t run` 以前寫 ``g.get('false_alarm_rate', 0):.1%``，而那個鍵
    **存在**、值是 None，所以預設值救不了 —— 整個 run 在印摘要的時候炸掉，
    而「一批全是真缺陷」一點都不罕見。
    """
    all_real = {str(i): {"is_real": True} for i in range(1, 11)}
    g = report.summarize(hand_results(), ground_truth=all_real)["ground_truth"]
    assert g["n_nuisance"] == 0
    assert g["false_alarm_rate"] is None
    assert g["miss_rate"] is not None          # 真缺陷有，所以這個算得出來

    all_fake = {str(i): {"is_real": False} for i in range(1, 11)}
    g = report.summarize(hand_results(), ground_truth=all_fake)["ground_truth"]
    assert g["n_real"] == 0
    assert g["miss_rate"] is None
    assert g["false_alarm_rate"] is not None


def test_the_cli_prints_a_dash_instead_of_crashing_on_those():
    """CLI 那一行要印得出來，而且印 `—` 比印 `0.0%` 誠實。"""
    from d4t.__main__ import _pct

    assert _pct(None) == "—"
    assert _pct(0.25) == "25.0%"
    assert _pct(0.0) == "0.0%"        # 真的是 0 跟沒有定義是兩件事


# --------------------------------------------------------------------------- #
# 打開來不卡（2026-09-01，使用者：「html 打開來瀏覽時很卡」）
# --------------------------------------------------------------------------- #
def _many(n, feats=6):
    keys = ["f%d" % i for i in range(feats)]
    rows = [{"defect_id": str(i), "ok": i % 50 != 0, "score": float(i),
             "bin": i % 4, "error": "" if i % 50 else "boom",
             "features": {k: float(i) for k in keys}} for i in range(n)]
    return rows, keys


def test_a_big_report_does_not_put_every_row_in_the_dom():
    """**這一條是那個卡本身。**

    兩萬顆全部寫成 ``<tr>`` 是 36 萬個 DOM 節點，實測 Chromium 從打開到可用
    要 6.2 秒；只寫前 `FIRST_ROWS` 列、其餘走 JSON 之後是 0.42 秒。

    ⚠ 便宜的做法量過都沒有用：`table-layout:fixed` 更慢、
    `content-visibility:auto` 對 table-row 不生效。成本在**節點本身**。
    """
    from d4t.core.export.html import FIRST_ROWS, build_report

    rows, keys = _many(2000)
    page = build_report(rows, "T", keys, None,
                        {str(i): "images/%d.jpg" % i for i in range(2000)})
    # 一列一個 ``<td class='id'>`` —— 數 ``<tr`` 會連 JS 裡的字串一起數到
    assert page.count("<td class='id'>") == FIRST_ROWS, "只寫前 N 列，不是兩千列"
    assert "id='rows'" in page, "其餘的要帶在頁面裡（資料一顆都不能少）"


def test_every_row_is_still_in_the_file():
    """**沒有一顆被丟掉** —— 少寫的是節點，不是資料。"""
    import json

    from d4t.core.export.html import FIRST_ROWS, build_report

    rows, keys = _many(FIRST_ROWS + 25)
    page = build_report(rows, "T", keys, None, {})
    blob = page.split("id='rows' type='application/json'>", 1)[1].split("</script>", 1)[0]
    rest = json.loads(blob)
    assert len(rest) == 25
    assert rest[0][0][0] == str(FIRST_ROWS)          # 第 301 顆接在後面
    assert rest[-1][0][0] == str(FIRST_ROWS + 24)


def test_a_small_report_carries_no_javascript_payload():
    """三百列以內的報表**一個位元組都不變** —— 那是絕大多數的情況。"""
    from d4t.core.export.html import build_report

    rows, keys = _many(12)
    page = build_report(rows, "T", keys, None, {})
    assert "id='rows'" not in page and "Show all" not in page
    assert page.count("<td class='id'>") == 12


def test_the_two_ways_of_drawing_a_row_agree():
    """HTML 那條路與 JSON 那條路吃**同一份** `_row_parts`。

    分成兩份的那天，前 300 列與第 301 列會長得不一樣，而畫面上看起來只是
    「後面那些怪怪的」。
    """
    from d4t.core.export.html import _row_html, _row_parts

    r = {"defect_id": "7", "ok": False, "score": 1.5, "bin": 2,
         "error": "bad <thing>", "features": {"a": 3.25}}
    parts = _row_parts(r, ["a"], {"7": "images/7.jpg"})
    html = _row_html(*parts)
    assert "class='bad'" in html                      # 跑不起來的那一列
    assert 'data-img="images/7.jpg"' in html
    assert "&lt;thing&gt;" in html                    # 跳脫過了
    assert parts[0][0] == "7" and parts[0][-1] == "bad &lt;thing&gt;"


def test_the_json_payload_cannot_close_the_script_tag():
    """一列裡有 ``</script>`` 就會把那個 script 提早關掉，後面整段 JSON
    會被當成 HTML 印出來 —— 而那是使用者打的字（error 欄）。"""
    from d4t.core.export.html import FIRST_ROWS, build_report

    rows, keys = _many(FIRST_ROWS + 2)
    rows[-1]["error"] = "</script><b>oops</b>"
    page = build_report(rows, "T", keys, None, {})
    blob = page.split("id='rows' type='application/json'>", 1)[1].split("</script>", 1)[0]
    assert "oops" in blob, "那一列要留在 JSON 裡（不是被切掉）"
    assert "<" not in blob, "JSON 裡不准有裸的 <"

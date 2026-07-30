#!/usr/bin/env python3
# ADEPT 單檔純文字包（由 tools/make_text_bundle.py 產生）。
"""整個 ADEPT repo 就在這個檔案裡，一行一行的純文字，沒有壓縮、沒有編碼。

為什麼是這種形式：公司政策擋掉 .zip 這個類別，而 proxy 也不讓 Python 逐檔抓 ——
能過的只剩「一個純文字檔」。你可以用記事本打開它，往下捲就看得到每個檔案的內容。

    python ADEPT_part2of6.py              # 解到 .\\ADEPT\\
    python ADEPT_part2of6.py --dest D:\\tools
    python ADEPT_part2of6.py --list       # 只看裡面有什麼，不寫任何檔案

每個檔案都帶 git blob SHA-1，解開時逐檔驗過才落地 —— 傳輸途中被動到的話會當場
講出來，不會讓你拿到一份安靜壞掉的程式碼。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

SENTINEL = "# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ===="
PART, N_PARTS = 2, 6   # 這是第幾批 / 共幾批（1/1 = 沒有分批）
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
#F 2befd3e81601f75aada73c3dc59e2c962f1e64d1 497 adept/core/export/report.py
## ADEPT report export — authored 2026-07-28 (M5-1).
#"""批次結果報表：CSV（feature vector）＋ Excel（給人看的三頁報告）。
#
#三個對外函式：
#
#- :func:`summarize`   純資料統計 —— Excel 的兩頁與 CLI 都吃它，唯一的真相來源。
#- :func:`write_csv`   utf-8-sig CSV（Excel 直接雙擊不亂碼），欄位與
#  :meth:`adept.core.store.RunStore.export_csv` 相同，方便兩邊互換。
#- :func:`write_excel` openpyxl 活頁簿，三張工作表：
#
#  ============  ==========================================================
#  「摘要」       總數 / bin 分佈 / 分數統計 / recipe 資訊；有 ground truth
#                時再加 **抓漏率、誤殺率、正確率** 與 2×2 混淆矩陣。
#  「明細」       CSV 那張表，凍結標題列 + 自動篩選。
#  「特徵統計」   每個特徵在整個 lot 的 最小 / 中位數 / 最大 / 標準差。
#  ============  ==========================================================
#
#名詞（半導體 ADC 的講法，別搞混）::
#
#    抓漏 (miss)        真缺陷被判成 nuisance —— 漏掉了，最嚴重
#    誤殺 (false alarm) nuisance 被判成真缺陷 —— 白花人力去 review
#
#    抓漏率 = 抓漏數 / 真缺陷總數
#    誤殺率 = 誤殺數 / nuisance 總數
#    正確率 = 判對的顆數 / 有標註且有判定的顆數
#
#``results`` 一律是 :func:`adept.core.pipeline.result_to_json_dict` 形狀的
#dict list（``defect_id`` / ``ok`` / ``error`` / ``score`` / ``bin`` /
#``features``）。檔案寫入一律 atomic（``.tmp`` + :func:`os.replace`）。
#"""
#from __future__ import annotations
#
#import csv
#import math
#import os
#import statistics
#from typing import Any, Dict, Iterable, List, Optional, Sequence, Set
#
#from .klarf_out import ExportError
#
#__all__ = ["summarize", "write_csv", "write_excel",
#           "feature_keys", "BASE_COLUMNS"]
#
##: 明細表最前面的固定欄位（其後接排序過的特徵欄）。
#BASE_COLUMNS = ("defect_id", "ok", "error", "score", "bin")
#
##: bin 為 None（沒判定）時在 bin 分佈裡使用的 key。
#UNBINNED_KEY = "unbinned"
#
#
## ---------------------------------------------------------------------------
## 小工具
## ---------------------------------------------------------------------------
#def _finite(v: Any) -> Optional[float]:
#    """float 化；None / nan / inf / 不可轉 → None。"""
#    if v is None or isinstance(v, bool):
#        return None if v is None else float(v)
#    try:
#        f = float(v)
#    except (TypeError, ValueError):
#        return None
#    if math.isnan(f) or math.isinf(f):
#        return None
#    return f
#
#
#def _atomic_replace(tmp: str, path: str) -> str:
#    os.replace(tmp, path)
#    return path
#
#
#def _ensure_parent(path: str) -> None:
#    parent = os.path.dirname(os.path.abspath(str(path)))
#    if parent:
#        os.makedirs(parent, exist_ok=True)
#
#
#def feature_keys(results: Sequence[Dict[str, Any]]) -> List[str]:
#    """所有結果的特徵 key 聯集（排序）—— 明細表與特徵統計的欄位順序。"""
#    keys: Set[str] = set()
#    for r in results or ():
#        keys.update((r.get("features") or {}).keys())
#    return sorted(keys)
#
#
#def _gt_is_real(value: Any) -> Optional[bool]:
#    """ground truth 的一筆 → 是不是真缺陷。
#
#    接受三種寫法：``True`` / ``{"is_real": True, ...}``（``make_sample`` 的
#    ``ground_truth.json``）/ 字串（``"1"`` ``"true"`` ``"real"`` …）。
#    看不懂就回 None（該顆不列入統計，而不是猜）。
#    """
#    if isinstance(value, dict):
#        for k in ("is_real", "real", "label", "truth"):
#            if k in value:
#                return _gt_is_real(value[k])
#        return None
#    if isinstance(value, bool):
#        return value
#    if isinstance(value, (int, float)):
#        return bool(value)
#    if isinstance(value, str):
#        s = value.strip().lower()
#        if s in ("1", "true", "yes", "y", "t", "real", "defect"):
#            return True
#        if s in ("0", "false", "no", "n", "f", "nuisance"):
#            return False
#    return None
#
#
#def _lookup_gt(ground_truth: Dict[Any, Any], defect_id: Any) -> Optional[bool]:
#    if defect_id in ground_truth:
#        return _gt_is_real(ground_truth[defect_id])
#    sid = str(defect_id)
#    if sid in ground_truth:
#        return _gt_is_real(ground_truth[sid])
#    try:
#        nid = str(int(sid))
#    except (TypeError, ValueError):
#        return None
#    if nid in ground_truth:
#        return _gt_is_real(ground_truth[nid])
#    return None
#
#
#def _stats(vals: Sequence[float]) -> Dict[str, Optional[float]]:
#    if not vals:
#        return {"n": 0, "min": None, "median": None, "max": None, "std": None}
#    return {
#        "n": len(vals),
#        "min": float(min(vals)),
#        "median": float(statistics.median(vals)),
#        "max": float(max(vals)),
#        "std": float(statistics.pstdev(vals)) if len(vals) > 1 else 0.0,
#    }
#
#
## ---------------------------------------------------------------------------
## summarize —— 兩張工作表與 CLI 共用的純資料函式
## ---------------------------------------------------------------------------
#def summarize(results: Sequence[Dict[str, Any]], *,
#              ground_truth: Optional[Dict[Any, Any]] = None,
#              positive_bins: Optional[Iterable[int]] = None) -> Dict[str, Any]:
#    """把一批結果整理成報表要的所有數字（純資料，不碰檔案）。
#
#    ``positive_bins``：哪些 bin 代表「判定為真缺陷」。預設 ``None`` =
#    「bin != 0」（引擎的慣例是 below→0、above→1）。
#
#    回傳::
#
#        {
#          "n_total", "n_ok", "n_fail", "n_scored",
#          "bin_counts": {"0": 4, "1": 3, "未判定": 1},   # key 是字串
#          "score_min", "score_median", "score_max",
#          "features": {特徵名: {"n","min","median","max","std"}},
#          "ground_truth": None 或 {
#              "n_labelled", "n_evaluated", "tp", "fp", "tn", "fn",
#              "miss_rate", "false_alarm_rate", "accuracy",
#              "positive_bins"},
#        }
#    """
#    results = list(results or [])
#    n_total = len(results)
#    n_ok = sum(1 for r in results if r.get("ok"))
#
#    scores: List[float] = []
#    bin_counts: Dict[str, int] = {}
#    for r in results:
#        s = _finite(r.get("score"))
#        if s is not None:
#            scores.append(s)
#        b = r.get("bin")
#        key = UNBINNED_KEY if b is None else str(int(b))
#        bin_counts[key] = bin_counts.get(key, 0) + 1
#
#    feats: Dict[str, List[float]] = {k: [] for k in feature_keys(results)}
#    for r in results:
#        for k, v in (r.get("features") or {}).items():
#            f = _finite(v)
#            if f is not None:
#                feats[k].append(f)
#
#    out: Dict[str, Any] = {
#        "n_total": n_total,
#        "n_ok": n_ok,
#        "n_fail": n_total - n_ok,
#        "n_scored": len(scores),
#        "bin_counts": bin_counts,
#        "score_min": min(scores) if scores else None,
#        "score_median": statistics.median(scores) if scores else None,
#        "score_max": max(scores) if scores else None,
#        "features": {k: _stats(v) for k, v in sorted(feats.items())},
#        "ground_truth": None,
#    }
#    if ground_truth:
#        out["ground_truth"] = _confusion(results, ground_truth, positive_bins)
#    return out
#
#
#def _confusion(results: Sequence[Dict[str, Any]], ground_truth: Dict[Any, Any],
#               positive_bins: Optional[Iterable[int]]) -> Dict[str, Any]:
#    """抓漏 / 誤殺 / 正確率 + 2×2 混淆矩陣。
#
#    判定為真缺陷 = ``bin in positive_bins``（預設 ``bin != 0``）。
#    bin 是 None（沒判定）或 ground truth 沒標註的顆數不列入矩陣，
#    另外記在 ``n_unbinned`` / ``n_unlabelled``。
#    """
#    pos: Optional[Set[int]] = (None if positive_bins is None
#                               else {int(b) for b in positive_bins})
#    tp = fp = tn = fn = 0
#    n_labelled = 0
#    n_unbinned = 0
#    for r in results:
#        truth = _lookup_gt(ground_truth, r.get("defect_id"))
#        if truth is None:
#            continue
#        n_labelled += 1
#        b = r.get("bin")
#        if b is None:
#            n_unbinned += 1
#            continue
#        b = int(b)
#        pred = (b != 0) if pos is None else (b in pos)
#        if truth and pred:
#            tp += 1
#        elif truth and not pred:
#            fn += 1
#        elif (not truth) and pred:
#            fp += 1
#        else:
#            tn += 1
#
#    n_eval = tp + fp + tn + fn
#    n_real = tp + fn
#    n_nuis = fp + tn
#    return {
#        "n_labelled": n_labelled,
#        "n_unlabelled": len(results) - n_labelled,
#        "n_unbinned": n_unbinned,
#        "n_evaluated": n_eval,
#        "n_real": n_real,
#        "n_nuisance": n_nuis,
#        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
#        # 抓漏率：真缺陷被判成 nuisance 的比例
#        "miss_rate": (fn / n_real) if n_real else None,
#        # 誤殺率：nuisance 被判成真缺陷的比例
#        "false_alarm_rate": (fp / n_nuis) if n_nuis else None,
#        "accuracy": ((tp + tn) / n_eval) if n_eval else None,
#        "positive_bins": (None if pos is None else sorted(pos)),
#    }
#
#
## ---------------------------------------------------------------------------
## CSV
## ---------------------------------------------------------------------------
#def _detail_rows(results: Sequence[Dict[str, Any]], keys: Sequence[str]
#                 ) -> List[List[Any]]:
#    rows: List[List[Any]] = []
#    for r in results:
#        feats = r.get("features") or {}
#        row: List[Any] = [
#            r.get("defect_id", ""),
#            1 if r.get("ok") else 0,
#            "" if r.get("error") is None else r.get("error"),
#            "" if _finite(r.get("score")) is None else _finite(r.get("score")),
#            "" if r.get("bin") is None else int(r.get("bin")),
#        ]
#        for k in keys:
#            v = _finite(feats.get(k))
#            row.append("" if v is None else v)
#        rows.append(row)
#    return rows
#
#
#def write_csv(results: Sequence[Dict[str, Any]], path: str, *,
#              include_features: bool = True) -> str:
#    """匯出明細 CSV（**utf-8-sig**，Excel 雙擊直接開不亂碼），atomic 寫入。
#
#    欄位：``defect_id, ok, error, score, bin`` 後面接**排序過的特徵 key
#    聯集**（某顆沒有的特徵留空）—— 這張表就是 feature vector，可直接餵 ML。
#    ``include_features=False`` 只輸出前五欄。
#    """
#    results = list(results or [])
#    path = str(path)
#    _ensure_parent(path)
#    keys = feature_keys(results) if include_features else []
#    tmp = path + ".tmp"
#    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
#        w = csv.writer(f)
#        w.writerow(list(BASE_COLUMNS) + list(keys))
#        for row in _detail_rows(results, keys):
#            w.writerow(row)
#    return _atomic_replace(tmp, path)
#
#
## ---------------------------------------------------------------------------
## Excel
## ---------------------------------------------------------------------------
#_SHEET_SUMMARY = "Summary"
#_SHEET_DETAIL = "Details"
#_SHEET_FEATURES = "Feature stats"
#
#_NUM_FMT = "0.0000"
#_PCT_FMT = "0.00%"
#
#
#def _recipe_info(recipe: Any) -> List[Sequence[Any]]:
#    """Recipe 物件 / recipe JSON dict → 摘要頁要顯示的幾列。"""
#    if recipe is None:
#        return []
#    if hasattr(recipe, "to_json_dict"):
#        rd = recipe.to_json_dict()
#    elif isinstance(recipe, dict):
#        rd = recipe
#    else:
#        return [("recipe", str(recipe))]
#    score = rd.get("score") or {}
#    rows: List[Sequence[Any]] = [("Recipe name", rd.get("recipe_id", ""))]
#    if rd.get("description"):
#        rows.append(("Description", rd.get("description")))
#    if score.get("expr") is not None:
#        rows.append(("Score expression", str(score.get("expr"))))
#    if score.get("threshold") is not None:
#        rows.append(("Threshold", _finite(score.get("threshold"))))
#    if score.get("bins"):
#        rows.append(("Bin mapping", ", ".join(
#            "{}={}".format(k, v) for k, v in sorted(score["bins"].items()))))
#    if rd.get("nodes") is not None:
#        try:
#            rows.append(("Step count", len(rd["nodes"])))
#        except TypeError:
#            pass
#    return rows
#
#
#def _autosize(ws, widths: Sequence[int]) -> None:
#    from openpyxl.utils import get_column_letter
#    for i, w in enumerate(widths, 1):
#        ws.column_dimensions[get_column_letter(i)].width = max(8, min(60, w))
#
#
#def _text_width(rows: Iterable[Sequence[Any]], n_cols: int) -> List[int]:
#    widths = [10] * n_cols
#    for row in rows:
#        for i, v in enumerate(row[:n_cols]):
#            widths[i] = max(widths[i], len(str("" if v is None else v)) + 2)
#    return widths
#
#
#def write_excel(results: Sequence[Dict[str, Any]], path: str, *,
#                ground_truth: Optional[Dict[Any, Any]] = None,
#                recipe: Any = None,
#                positive_bins: Optional[Iterable[int]] = None) -> str:
#    """匯出 Excel 報表（三張工作表），atomic 寫入。回傳寫入路徑。
#
#    - 「摘要」：總數、bin 分佈、分數統計、recipe 資訊；給了 ``ground_truth``
#      再加抓漏率 / 誤殺率 / 正確率與 2×2 混淆矩陣。
#    - 「明細」：與 :func:`write_csv` 相同的表，凍結標題列 + 自動篩選。
#    - 「特徵統計」：每個特徵的 筆數 / 最小 / 中位數 / 最大 / 標準差。
#
#    ``ground_truth`` 可用 ``{defect_id: True}`` 或
#    ``{defect_id: {"is_real": True, "type": "..."}}``（後者就是
#    ``tools/make_sample.py`` 產出的 ``ground_truth.json``）。
#    """
#    try:
#        from openpyxl import Workbook
#        from openpyxl.styles import Alignment, Font, PatternFill
#    except ImportError as e:      # pragma: no cover — requirements 已含 openpyxl
#        raise ExportError(
#            "Exporting to Excel needs the openpyxl package, which is not "
#            "installed on this machine ({}).\nRun: pip install openpyxl, or "
#            "export to CSV instead.".format(e)) from None
#
#    results = list(results or [])
#    path = str(path)
#    _ensure_parent(path)
#    s = summarize(results, ground_truth=ground_truth, positive_bins=positive_bins)
#    keys = feature_keys(results)
#
#    bold = Font(bold=True)
#    head_fill = PatternFill("solid", fgColor="EDEFF2")
#
#    wb = Workbook()
#
#    # ---------------- 摘要 ----------------
#    ws = wb.active
#    ws.title = _SHEET_SUMMARY
#    rows: List[Sequence[Any]] = [("Item", "Value"), ("__section__", "Overall")]
#    rows += [
#        ("Total defects", s["n_total"]),
#        ("Succeeded", s["n_ok"]),
#        ("Failed", s["n_fail"]),
#        ("Scored", s["n_scored"]),
#    ]
#    rows.append(("__section__", "Bin distribution"))
#    for k in sorted(s["bin_counts"], key=lambda x: (x == UNBINNED_KEY, x)):
#        rows.append(("bin {}".format(k), s["bin_counts"][k]))
#    rows.append(("__section__", "Score"))
#    rows += [
#        ("Minimum", s["score_min"]),
#        ("Median", s["score_median"]),
#        ("Maximum", s["score_max"]),
#    ]
#    rinfo = _recipe_info(recipe)
#    if rinfo:
#        rows.append(("__section__", "recipe"))
#        rows += rinfo
#    gt = s["ground_truth"]
#    if gt:
#        rows.append(("__section__", "Against ground truth"))
#        rows += [
#            ("Labelled defects", gt["n_labelled"]),
#            ("Actually evaluated", gt["n_evaluated"]),
#            ("Miss rate (real defect called nuisance)", gt["miss_rate"]),
#            ("False alarm rate (nuisance called real defect)", gt["false_alarm_rate"]),
#            ("Accuracy", gt["accuracy"]),
#            ("__section__", "Confusion matrix"),
#            ("", "Called: real defect", "Called: nuisance"),
#            ("Actual: real defect", gt["tp"], gt["fn"]),
#            ("Actual: nuisance", gt["fp"], gt["tn"]),
#        ]
#
#    r_i = 0
#    pct_rows = set()
#    for row in rows:
#        r_i += 1
#        if row[0] == "__section__":
#            ws.cell(row=r_i, column=1, value=str(row[1])).font = bold
#            ws.cell(row=r_i, column=1).fill = head_fill
#            continue
#        for c_i, v in enumerate(row, 1):
#            cell = ws.cell(row=r_i, column=c_i, value=v)
#            if r_i == 1 or (c_i == 1 and isinstance(v, str)
#                            and v.startswith("Actual:")):
#                cell.font = bold
#        label = str(row[0])
#        if label.startswith(("Miss rate", "False alarm rate", "Accuracy")):
#            pct_rows.add(r_i)
#    for r in pct_rows:
#        ws.cell(row=r, column=2).number_format = _PCT_FMT
#    for label in ("Minimum", "Median", "Maximum", "Threshold"):
#        for r in range(1, r_i + 1):
#            if ws.cell(row=r, column=1).value == label:
#                ws.cell(row=r, column=2).number_format = _NUM_FMT
#    ws.cell(row=1, column=1).fill = head_fill
#    ws.cell(row=1, column=2).fill = head_fill
#    _autosize(ws, _text_width(rows, 3))
#    ws.freeze_panes = "A2"
#
#    # ---------------- 明細 ----------------
#    ws = wb.create_sheet(_SHEET_DETAIL)
#    header = list(BASE_COLUMNS) + list(keys)
#    ws.append(header)
#    for c_i in range(1, len(header) + 1):
#        c = ws.cell(row=1, column=c_i)
#        c.font = bold
#        c.fill = head_fill
#        c.alignment = Alignment(horizontal="center")
#    detail = _detail_rows(results, keys)
#    for row in detail:
#        ws.append(["" if v is None else v for v in row])
#    n_rows = len(detail) + 1
#    for c_i in range(4, len(header) + 1):        # score 之後全是數值欄
#        if c_i == 5:                             # bin 是整數
#            continue
#        for r_i in range(2, n_rows + 1):
#            ws.cell(row=r_i, column=c_i).number_format = _NUM_FMT
#    ws.freeze_panes = "A2"
#    if n_rows >= 1:
#        from openpyxl.utils import get_column_letter
#        ws.auto_filter.ref = "A1:{}{}".format(
#            get_column_letter(len(header)), max(n_rows, 1))
#    _autosize(ws, _text_width([header] + detail, len(header)))
#
#    # ---------------- 特徵統計 ----------------
#    ws = wb.create_sheet(_SHEET_FEATURES)
#    fheader = ["Feature", "Count", "Minimum", "Median", "Maximum", "Std dev"]
#    ws.append(fheader)
#    for c_i in range(1, len(fheader) + 1):
#        c = ws.cell(row=1, column=c_i)
#        c.font = bold
#        c.fill = head_fill
#    frows: List[Sequence[Any]] = []
#    for name, st in s["features"].items():
#        frows.append((name, st["n"], st["min"], st["median"], st["max"], st["std"]))
#    for row in frows:
#        ws.append(list(row))
#    for r_i in range(2, len(frows) + 2):
#        for c_i in range(3, 7):
#            ws.cell(row=r_i, column=c_i).number_format = _NUM_FMT
#    ws.freeze_panes = "A2"
#    _autosize(ws, _text_width([fheader] + frows, len(fheader)))
#
#    tmp = path + ".tmp"
#    wb.save(tmp)
#    return _atomic_replace(tmp, path)
#
#F cf4a1ad803592ee09a5fc9c205da267f7de1a3f9 32 adept/core/ingest/__init__.py
## ADEPT ingest package — created 2026-07-27.
## Re-exports the main names of the vendored ingest modules
## (KLIP klarf_core / klarf_tif_probe, GLAS sem_loader patterns, PEAR image IO).
#"""adept.core.ingest — KLARF / TIFF / 影像檔的載入層。"""
#from __future__ import annotations
#
#from .klarf_core import (
#    KlarfDoc,
#    Issue,
#    autofix,
#    compare,
#    detect_version,
#    lint,
#    load,
#)
#from .tiff_index import n_pages, read_page, read_tiff_pages
#from .imageio import load_gray, save_gray, save_rgb
#from .dataset import (
#    Dataset,
#    DefectItem,
#    ImageRef,
#    load_dataset,
#    load_folder,
#)
#
#__all__ = [
#    "KlarfDoc", "Issue", "autofix", "compare", "detect_version", "lint", "load",
#    "n_pages", "read_page", "read_tiff_pages",
#    "load_gray", "save_gray", "save_rgb",
#    "Dataset", "DefectItem", "ImageRef", "load_dataset", "load_folder",
#]
#
#F cd9359f8846e353aad0a7aec2f567dd2c554231b 236 adept/core/ingest/dataset.py
## Vendored/adapted into ADEPT on 2026-07-27.
## Source project: GLAS — file: glas/app/sem_loader.py (SemImage / load_klarf /
## load_folder patterns: per-defect image resolution relative to the KLARF dir,
## XREL/YREL surfacing, non-recursive folder scan). Detection and page->channel
## mapping are built on KLIP klarf_core (vendored as .klarf_core) and
## klarf_tif_probe (vendored as .tiff_index).
## Adaptations:
##   - added `from __future__ import annotations` (ADEPT convention)
##   - GLAS SemImage generalized to ImageRef / DefectItem / Dataset dataclasses
##     per the ADEPT ingest spec (multi-channel images per defect)
##   - KLARF ingest routed through klarf_core.KlarfDoc instead of GLAS
##     KlarfParser; per-defect filenames come from
##     KlarfDoc.defect_image_filename (ported GLAS concept)
##   - XREL/YREL converted to nm via doc.unit_info() (1.2 um -> x1000, 1.8 nm)
#"""Dataset 組裝：KLARF (+ patch TIFF) 或資料夾 → 統一的 DefectItem 清單。
#
#偵測邏輯（load_dataset）：
#  1. 找得到 patch TIFF（呼叫端指定或 doc.tiff_path()）且
#     doc.defect_image_map() 能對出 page → kind="ebi_patch"。
#  2. 否則 defect 列帶 per-defect 檔名（defect_image_filename）
#     → kind="rsem"，images={"single": ...}，路徑相對 KLARF 所在資料夾解析。
#  3. 兩者皆無 → 仍回 kind="rsem"（僅 defect 中繼資料，無影像）並加 warning。
#
#★ EBI patch 的 channel 指派假設（重要）★
#  每個 defect 的 TIFF pages 依「出現順序」對應 channel_order：
#  第 1 頁 = channel_order[0]（預設 "test"），第 2 頁 = channel_order[1]
#  （預設 "ref"），多出來的頁依序命名 "img3", "img4", …。
#  這是暫定慣例——真實 TiffSpec 欄位語意（哪頁是 test / ref）待進廠
#  以實際檔案驗證後再修正。
#"""
#from __future__ import annotations
#
#import os
#from dataclasses import dataclass, field
#from typing import Dict, List, Optional, Tuple
#
#import numpy as np
#
#from . import imageio, tiff_index
#from . import klarf_core
#from .klarf_core import KlarfDoc
#
#_IMAGE_EXTS = {".png", ".tif", ".tiff", ".jpg", ".jpeg", ".bmp"}
#
#
#@dataclass
#class ImageRef:
#    """一張影像的來源：多頁 TIFF 的某一頁（page 給 0-based 索引），
#    或獨立影像檔（page=None）。channel 例："test" / "ref" / "single"。"""
#    path: str
#    page: Optional[int]
#    channel: str
#
#
#@dataclass
#class DefectItem:
#    """一顆 defect + 它的影像們。座標一律已換算為 nm（die 內相對座標）。"""
#    defect_id: str
#    die: Optional[Tuple[int, int]]          # (xindex, yindex)；folder 模式為 None
#    xrel_nm: Optional[float]
#    yrel_nm: Optional[float]
#    images: Dict[str, ImageRef] = field(default_factory=dict)
#    nm_per_px: Optional[float] = None       # 目前無來源可推得；留待 in-fab 校正
#    klarf_row: int = -1                     # doc.defects 的列索引；folder 模式為 -1
#    tags: Dict[str, str] = field(default_factory=dict)
#
#    def load(self, channel: str) -> np.ndarray:
#        """讀出該 channel 的像素：TIFF 頁走 tiff_index.read_page，
#        獨立影像檔走 imageio.load_gray（CJK 路徑安全）。"""
#        if channel not in self.images:
#            raise KeyError(
#                f"defect {self.defect_id} has no channel {channel!r} "
#                f"(available: {sorted(self.images)})")
#        ref = self.images[channel]
#        if ref.page is not None:
#            return tiff_index.read_page(ref.path, ref.page)
#        return imageio.load_gray(ref.path)
#
#
#@dataclass
#class Dataset:
#    kind: str                               # "ebi_patch" | "rsem" | "folder"
#    klarf: Optional[KlarfDoc]
#    items: List[DefectItem] = field(default_factory=list)
#    warnings: List[str] = field(default_factory=list)
#
#
#def _to_float(v) -> Optional[float]:
#    try:
#        return float(v)
#    except (TypeError, ValueError):
#        return None
#
#
#def _to_int(v) -> Optional[int]:
#    try:
#        return int(v)
#    except (TypeError, ValueError):
#        return None
#
#
#def _resolve_relative(base_dir: str, fname: str) -> str:
#    """把 KLARF 內的影像檔名解析成路徑（相對 KLARF 所在資料夾；
#    Windows 反斜線先正規化，絕對路徑原樣保留）。"""
#    name = fname.replace("\\", "/")
#    if os.path.isabs(name):
#        return os.path.normpath(name)
#    return os.path.normpath(os.path.join(base_dir, name))
#
#
#def _channel_name(j: int, channel_order: Tuple[str, ...]) -> str:
#    """第 j（0-based）頁的 channel 名：channel_order 用完後接 "img3", "img4"…"""
#    if j < len(channel_order):
#        return channel_order[j]
#    return f"img{j + 1}"
#
#
#def _base_item(doc: KlarfDoc, row_idx: int, row: List[str],
#               to_nm: float) -> DefectItem:
#    di = doc.col_index("DEFECTID")
#    xi, yi = doc.col_index("XINDEX"), doc.col_index("YINDEX")
#    xr, yr = doc.col_index("XREL"), doc.col_index("YREL")
#    ci, ti = doc.col_index("CLASSNUMBER"), doc.col_index("TEST")
#
#    defect_id = row[di] if 0 <= di < len(row) else str(row_idx + 1)
#    die = None
#    if 0 <= xi < len(row) and 0 <= yi < len(row):
#        dx, dy = _to_int(row[xi]), _to_int(row[yi])
#        if dx is not None and dy is not None:
#            die = (dx, dy)
#    x = _to_float(row[xr]) if 0 <= xr < len(row) else None
#    y = _to_float(row[yr]) if 0 <= yr < len(row) else None
#    tags: Dict[str, str] = {}
#    if 0 <= ci < len(row):
#        tags["classnumber"] = row[ci]
#    if 0 <= ti < len(row):
#        tags["test"] = row[ti]
#    return DefectItem(
#        defect_id=str(defect_id),
#        die=die,
#        xrel_nm=(x * to_nm) if x is not None else None,
#        yrel_nm=(y * to_nm) if y is not None else None,
#        klarf_row=row_idx,
#        tags=tags,
#    )
#
#
#def load_dataset(klarf_path, tiff_path=None,
#                 channel_order: Tuple[str, ...] = ("test", "ref")) -> Dataset:
#    """載入 KLARF（可帶 patch TIFF）成 Dataset。偵測邏輯見模組 docstring。
#
#    channel_order：EBI patch 模式下，每個 defect 的 TIFF 頁依出現順序
#    指派到這些 channel（預設第 1 頁 = "test"、第 2 頁 = "ref"；多出的頁
#    命名 "img3", "img4", …）。此為暫定假設，真實 TiffSpec 語意待 in-fab 驗證。
#    """
#    klarf_path = str(klarf_path)
#    doc = klarf_core.load(klarf_path)
#    warnings: List[str] = list(doc.warnings)
#    base_dir = os.path.dirname(os.path.abspath(klarf_path))
#    to_nm = float(doc.unit_info()["to_nm"])
#
#    # ---- patch TIFF 偵測 ----
#    tiff = str(tiff_path) if tiff_path is not None else doc.tiff_path()
#    if tiff is not None and not os.path.isfile(tiff):
#        warnings.append(f"Patch TIFF not found: {tiff}")
#        tiff = None
#
#    imap = None
#    if tiff is not None:
#        try:
#            npages = tiff_index.n_pages(tiff)
#        except (OSError, ValueError) as e:
#            warnings.append(f"Could not index TIFF {tiff}: {e}")
#            tiff = None
#        else:
#            imap = doc.defect_image_map(npages)
#            if imap["mode"] is None:
#                warnings.extend(imap["notes"])
#                imap = None
#
#    items: List[DefectItem] = []
#
#    if imap is not None:
#        # ---- kind="ebi_patch"：多頁 TIFF，defect → pages → channels ----
#        kind = "ebi_patch"
#        warnings.extend(imap["notes"])
#        assert tiff is not None
#        for k, (row, pages) in enumerate(zip(doc.defects, imap["pages"])):
#            item = _base_item(doc, k, row, to_nm)
#            for j, pg in enumerate(pages):
#                ch = _channel_name(j, tuple(channel_order))
#                item.images[ch] = ImageRef(path=tiff, page=int(pg), channel=ch)
#            items.append(item)
#        return Dataset(kind=kind, klarf=doc, items=items, warnings=warnings)
#
#    # ---- kind="rsem"：per-defect 檔名（Image/Images {...} 區塊）----
#    n_named = 0
#    for k, row in enumerate(doc.defects):
#        item = _base_item(doc, k, row, to_nm)
#        fname = doc.defect_image_filename(row)
#        if fname:
#            n_named += 1
#            item.images["single"] = ImageRef(
#                path=_resolve_relative(base_dir, fname), page=None,
#                channel="single")
#        items.append(item)
#    if n_named == 0:
#        warnings.append(
#            "No patch TIFF and no per-defect image filenames; "
#            "dataset carries defect metadata only.")
#    return Dataset(kind="rsem", klarf=doc, items=items, warnings=warnings)
#
#
#def load_folder(folder) -> Dataset:
#    """掃描資料夾（不遞迴）成 Dataset(kind="folder")。
#    無座標資訊（GLAS load_folder 模式）：每個影像檔一個 DefectItem，
#    defect_id = 檔名主幹，images={"single": ...}。"""
#    d = str(folder)
#    items: List[DefectItem] = []
#    warnings: List[str] = []
#    if not os.path.isdir(d):
#        return Dataset(kind="folder", klarf=None, items=[],
#                       warnings=[f"Not a directory: {d}"])
#    for name in sorted(os.listdir(d)):
#        path = os.path.join(d, name)
#        stem, ext = os.path.splitext(name)
#        if os.path.isfile(path) and ext.lower() in _IMAGE_EXTS:
#            items.append(DefectItem(
#                defect_id=stem, die=None, xrel_nm=None, yrel_nm=None,
#                images={"single": ImageRef(path=path, page=None,
#                                           channel="single")},
#            ))
#    if not items:
#        warnings.append(f"No image files found in folder: {d}")
#    return Dataset(kind="folder", klarf=None, items=items, warnings=warnings)
#
#F ddb8939ebee5ba56237cce56d0c53397695982bb 75 adept/core/ingest/imageio.py
## Vendored into ADEPT on 2026-07-27.
## Source project: PEAR — file: pear/core/analysis.py (function `load_image`,
## the CJK-path-safe np.fromfile + cv2.imdecode grayscale loader).
## Adaptations:
##   - added `from __future__ import annotations` (ADEPT convention)
##   - renamed load_image -> load_gray (algorithm/behavior unchanged:
##     BGRA/BGR -> gray, non-uint8 (e.g. uint16) -> MINMAX-normalized uint8)
##   - added save_gray() / save_rgb() counterparts via cv2.imencode +
##     ndarray.tofile so writing is CJK-path safe too (cv2.imwrite is not).
#"""影像 IO（CJK 路徑安全）。
#
#cv2.imread / cv2.imwrite 在 Windows 上吃不到含中日韓字元的路徑；
#一律改走 np.fromfile + cv2.imdecode（讀）與 cv2.imencode + tofile（寫）。
#"""
#from __future__ import annotations
#
#import os
#
#import cv2
#import numpy as np
#
#
## --------------------------------------------------------------------------- #
## Image IO (CJK-path safe)
## --------------------------------------------------------------------------- #
#def load_gray(path: str) -> np.ndarray:
#    """Load an image as 8-bit single-channel grayscale (CJK-path safe)."""
#    data = np.fromfile(path, dtype=np.uint8)
#    if data.size == 0:
#        raise IOError(f"could not read file: {path}")
#    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
#    if img is None:
#        raise IOError(f"could not decode image: {path}")
#    if img.ndim == 3:
#        if img.shape[2] == 4:
#            img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
#        else:
#            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
#    if img.dtype != np.uint8:
#        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
#    return img
#
#
#def _encode_and_write(path: str, arr: np.ndarray) -> None:
#    """cv2.imencode + ndarray.tofile：CJK 路徑安全的寫檔（副檔名決定格式）。"""
#    ext = os.path.splitext(path)[1]
#    if not ext:
#        raise ValueError(f"cannot infer image format (no extension): {path}")
#    ok, buf = cv2.imencode(ext, arr)
#    if not ok:
#        raise IOError(f"could not encode image for: {path}")
#    buf.tofile(path)
#
#
#def save_gray(path: str, arr: np.ndarray) -> None:
#    """Save a single-channel (grayscale) image (CJK-path safe)."""
#    a = np.asarray(arr)
#    if a.ndim == 3 and a.shape[2] == 1:
#        a = a[:, :, 0]
#    if a.ndim != 2:
#        raise ValueError(f"save_gray expects a 2-D array, got shape {a.shape}")
#    _encode_and_write(path, a)
#
#
#def save_rgb(path: str, arr: np.ndarray) -> None:
#    """Save an RGB (H, W, 3) image (CJK-path safe).
#
#    Input is RGB channel order; cv2 encodes BGR, so the channels are
#    swapped before encoding.
#    """
#    a = np.asarray(arr)
#    if a.ndim != 3 or a.shape[2] != 3:
#        raise ValueError(f"save_rgb expects an (H, W, 3) array, got shape {a.shape}")
#    _encode_and_write(path, cv2.cvtColor(a, cv2.COLOR_RGB2BGR))
#
#F 7c83441689fc980b2a4d7e3f46375653ae305054 1958 adept/core/ingest/klarf_core.py
## Vendored into ADEPT on 2026-07-27.
## Source project: KLIP — file: klarf_core.py (KLARF 1.2/1.8 lossless engine).
## Adaptations:
##   - added `from __future__ import annotations` (ADEPT convention)
##   - added ONE additive method KlarfDoc.defect_image_filename(row): returns
##     the per-defect image filename for rows whose image tail carries an
##     `Image/Images N { "file" ... }` block (concept ported from GLAS
##     glas/core/klarf_parser.py `_map_row_tokens` / `_image_filename`,
##     re-expressed on klarf_core's raw-token row representation)
##   - no other changes; parse / lossless round-trip behavior is identical
##     to upstream (Chinese docstrings/comments kept verbatim).
#"""
#klarf_core.py
#KLARF 1.2 / 1.8 讀取 + 就地編輯引擎（UI 與檔案格式之間的那一層）
#
#核心原則：span-splice 無損寫回
#  - 沒被使用者改到的部分，to_text() 寫回時與原檔「逐位元組相同」。
#  - 只有被編輯的區塊（某個 header 欄位、DefectList）才重新產生。
#  - 需要的 count（1.8 的 Data N）自動重算；不確定意義的 count（1.2 的
#    ClassLookup 數字）一律原樣保留，絕不亂算。
#
#單位備忘：
#  - 1.2：座標/尺寸為「微米 µm 浮點」
#  - 1.8：座標/尺寸為「奈米 nm 整數」（= µm × 1000）
#  引擎內部一律以「原始字串 token」保存 defect 表，不做數值換算，
#  單位換算/顯示交給 UI 層處理，避免任何精度漂移。
#"""
#from __future__ import annotations
#
#import os
#import re
#
#
## ---------------------------------------------------------------- 小工具
#
#def _find_matching_brace(text, open_idx):
#    """從 text[open_idx] 的 '{' 找出成對的 '}' 索引；找不到回 -1。"""
#    depth = 0
#    for i in range(open_idx, len(text)):
#        if text[i] == '{':
#            depth += 1
#        elif text[i] == '}':
#            depth -= 1
#            if depth == 0:
#                return i
#    return -1
#
#
#def detect_version(text):
#    """回傳 '1.8' / '1.2'（或 FileVersion 指定的字串）。"""
#    if re.search(r'Record\s+FileRecord', text):
#        return '1.8'
#    m = re.search(r'FileVersion\s+(\d+)\s+(\d+)', text)
#    if m:
#        return f"{m.group(1)}.{m.group(2)}"
#    if re.search(r'\bList\s+\w+\s*\{', text):
#        return '1.8'
#    return '1.2'
#
#
## 1.8 的記錄名稱 → 對應到 1.2 的 header 欄位名
#REC_FIELD = {
#    'LotRecord': 'LotID',
#    'WaferRecord': 'WaferID',
#    'DeviceRecord': 'DeviceID',
#    'StepRecord': 'StepID',
#    'SetupRecord': 'SetupID',
#    'FileRecord': 'FileVersion',
#}
#
#UNIT_INFO = {
#    '1.2': {'coord_unit': 'µm', 'coord_type': 'float', 'to_nm': 1000.0},
#    '1.8': {'coord_unit': 'nm', 'coord_type': 'int',   'to_nm': 1.0},
#}
#
#
## ---------------------------------------------------------------- 主類別
#
#class KlarfDoc:
#    """一份 KLARF 檔的可編輯模型。UI 對 1.2 / 1.8 用同一組介面操作。"""
#
#    # 1.2 常見的單行 header 欄位（可編輯）；未列出的欄位會被原樣保留
#    FIELDS_12 = [
#        "FileVersion", "FileTimestamp", "InspectionStationID", "SampleType",
#        "ResultTimestamp", "LotID", "SampleSize", "DeviceID", "SetupID",
#        "StepID", "SampleOrientationMarkType", "OrientationMarkLocation",
#        "DiePitch", "DieOrigin", "WaferID", "Slot", "ScribeID",
#        "SampleCenterLocation",
#    ]
#
#    def __init__(self, text, source_path=None):
#        self._text = text
#        self.source_path = source_path
#        self.version = detect_version(text)
#        self._is18 = (self.version == '1.8')
#        self.warnings = []
#        self.summary_stale = False
#        self.auto_recompute_summary = False  # 決策：SummaryList 一律維持原樣，不自動重算
#                                             #（DefectList 常是子集、summary 是全量，重算會洗掉真數字）
#
#        # summary（目前 1.2 支援自動重算；1.8 待真檔）
#        self._summary_columns = []
#        self._summary_rows = []
#        self._summary_orig = None
#
#        # 可編輯元素
#        self._header = {}            # name -> {"orig":原字串, "value":現值, "dirty":bool}
#        self.class_lookup = {}       # code(int) -> name(str)
#        self._classlookup_orig = None
#        self._classlookup_dirty = False
#        self.defect_columns = []     # 欄位名 list
#        self.defects = []            # list[list[str]]，原始 token
#        self._defect_dirty = False
#        self._defect_orig = None     # 原始 DefectList / Data 區塊字串（供 replace-once）
#
#        # patch 影像（帶圖 KLARF）：TiffFileName 指到多頁 TIFF，
#        # TiffSpec 宣告 IMAGELIST 每張圖佔幾個 token
#        self.tiff_file_name = None   # 原始字串（可能含 Windows 路徑）
#        self.tiff_spec = None        # {"version": str, "nfields": int|None, "fields": [str]}
#        self._img_layout = 'unset'   # 快取：(start_col, nfields, how) 或 None
#        self._il18 = None            # 1.8：型別為 ImageList 的欄位索引（名稱不限）
#
#        if self._is18:
#            self._parse_18()
#        else:
#            self._parse_12()
#        self._parse_tiff_fields()
#
#    # ---------- 對外唯讀資訊 ----------
#
#    def unit_info(self):
#        return UNIT_INFO.get(self.version, UNIT_INFO['1.2'])
#
#    def header_items(self):
#        """回傳 [(name, value_str), ...] 給 UI 顯示/編輯。"""
#        return [(n, h["value"]) for n, h in self._header.items()]
#
#    def col_index(self, name):
#        up = [c.upper() for c in self.defect_columns]
#        return up.index(name.upper()) if name.upper() in up else -1
#
#    # ---------- 解析 1.2 ----------
#
#    def _parse_12(self):
#        t = self._text
#        for name in self.FIELDS_12:
#            m = re.search(rf'(?m)^[ \t]*{name}\b[ \t]+([^;]*);', t)
#            if m:
#                self._header[name] = {"orig": m.group(0),
#                                      "value": m.group(1).strip(),
#                                      "dirty": False}
#        # ClassLookup：保留原本那個數字（它常是 class 檔總數，不是列數）
#        m = re.search(r'(?m)^[ \t]*ClassLookup\b[ \t]+\d+[ \t]*\r?\n([\s\S]*?);', t)
#        if m:
#            self._classlookup_orig = m.group(0)
#            for line in m.group(1).splitlines():
#                cm = re.match(r'\s*(\d+)\s+"([^"]*)"', line)
#                if cm:
#                    self.class_lookup[int(cm.group(1))] = cm.group(2)
#
#        m = re.search(r'DefectRecordSpec\s+\d+\s+([^;]+);', t)
#        if m:
#            self.defect_columns = m.group(1).split()
#
#        matches = list(re.finditer(r'(?m)^[ \t]*DefectList\b[ \t]*\r?\n([\s\S]*?);', t))
#        if len(matches) > 1:
#            self.warnings.append(
#                f"Detected {len(matches)} DefectLists (multi-test); only the first is editable.")
#        if matches:
#            self._defect_orig = matches[0].group(0)
#            for line in matches[0].group(1).splitlines():
#                line = line.strip()
#                if line and not line.startswith(';'):
#                    self.defects.append(line.split())
#
#        # SummarySpec / SummaryList
#        m = re.search(r'SummarySpec\s+\d+\s+([^;]+);', t)
#        if m:
#            self._summary_columns = m.group(1).split()
#        m = re.search(r'(?m)^[ \t]*SummaryList\b[ \t]*\r?\n([\s\S]*?);', t)
#        if m:
#            self._summary_orig = m.group(0)
#            for line in m.group(1).splitlines():
#                line = line.strip()
#                if line and not line.startswith(';'):
#                    self._summary_rows.append(line.split())
#
#    # ---------- 解析 1.8 ----------
#
#    def _parse_18(self):
#        t = self._text
#        for m in re.finditer(r'Field\s+(\w+)\s+\d+\s*\{[^}]*\}', t):
#            name = m.group(1)
#            if name not in self._header:
#                inner = m.group(0)[m.group(0).index('{') + 1:-1].strip()
#                self._header[name] = {"orig": m.group(0), "value": inner, "dirty": False}
#
#        # 1.8 把 LotID / WaferID 等放在 Record 的名稱上（例：Record LotRecord "N9S641.06"），
#        # 不是 Field，所以另外抓出來，讓 Header 頁能和 1.2 一樣檢視／編輯。
#        for m in re.finditer(r'Record\s+(\w+Record)\s+("(?:[^"\\]|\\.)*")', t):
#            rec = m.group(1)
#            name = REC_FIELD.get(rec)
#            if name and name not in self._header:
#                self._header[name] = {"orig": m.group(0), "value": m.group(2),
#                                      "dirty": False, "rec": True}
#
#        cl = re.search(r'List\s+ClassLookupList\s*\{', t)
#        if cl:
#            b0 = t.index('{', cl.start())
#            b1 = _find_matching_brace(t, b0)
#            body = t[b0 + 1:b1]
#            dm = re.search(r'Data\s+\d+\s*\{', body)
#            if dm:
#                db0 = body.index('{', dm.start())
#                db1 = _find_matching_brace(body, db0)
#                for row in body[db0 + 1:db1].split(';'):
#                    cm = re.match(r'\s*(\d+)\s+"([^"]*)"', row)
#                    if cm:
#                        self.class_lookup[int(cm.group(1))] = cm.group(2)
#
#        dls = list(re.finditer(r'List\s+DefectList\s*\{', t))
#        if len(dls) > 1:
#            self.warnings.append(
#                f"Detected {len(dls)} DefectLists; only the first is editable.")
#        if dls:
#            b0 = t.index('{', dls[0].start())
#            b1 = _find_matching_brace(t, b0)
#            block = t[b0:b1 + 1]
#            cm = re.search(r'Columns\s+\d+\s*\{([^}]*)\}', block)
#            if cm:
#                cols = []
#                for c in cm.group(1).split(','):
#                    parts = c.strip().split()
#                    cols.append(parts[-1] if parts else c.strip())
#                    # 影像欄常不叫 IMAGELIST（例：ImageList ImageInfo），記型別位置
#                    if len(parts) >= 2 and parts[0].lower() == 'imagelist':
#                        self._il18 = len(cols) - 1
#                self.defect_columns = cols
#            dm = re.search(r'Data\s+\d+\s*\{', block)
#            if dm:
#                db0 = block.index('{', dm.start())
#                db1 = _find_matching_brace(block, db0)
#                self._defect_orig = block[dm.start():db1 + 1]   # 'Data N { ... }'
#                for row in block[db0 + 1:db1].split(';'):
#                    row = row.strip()
#                    if row:
#                        self.defects.append(re.findall(r'[^"\s]+|"[^"]*"', row))
#
#    # ---------- 解析 TIFF patch 影像欄位 ----------
#
#    def _parse_tiff_fields(self):
#        t = self._text
#        # 1.2：TiffFileName xxx; / TiffSpec 6.1 2 "IMAGEVERSION" "IMAGEXYPOS";
#        m = re.search(r'(?m)^[ \t]*TiffFileName\b[ \t]+([^;]*);', t)
#        if m:
#            self.tiff_file_name = m.group(1).strip().strip('"')
#        elif 'TiffFileName' in self._header:      # 1.8 放在 Field 裡
#            self.tiff_file_name = self._header['TiffFileName']["value"].strip().strip('"')
#        elif 'ImageFileName' in self._header:     # 1.8：Field ImageFileName {"x.tif", "TIF"}
#            q = re.findall(r'"([^"]*)"', self._header['ImageFileName']["value"])
#            if q:
#                self.tiff_file_name = q[0]
#        m = re.search(r'(?m)^[ \t]*TiffSpec\b[ \t]+([\d.]+)[ \t]+(\d+)[ \t]*([^;]*);', t)
#        if m:
#            fields = re.findall(r'"([^"]*)"', m.group(3)) or m.group(3).split()
#            n = int(m.group(2))
#            if fields and len(fields) != n:
#                self.warnings.append(
#                    f"TiffSpec declares {n} fields but lists {len(fields)}; using {len(fields)}.")
#                n = len(fields)
#            if n > 0:
#                self.tiff_spec = {"version": m.group(1), "nfields": n, "fields": fields}
#        elif 'TiffSpec' in self._header:          # 1.8：Field TiffSpec {"6.0", "G", "R"}
#            vals = re.findall(r'"([^"]*)"', self._header['TiffSpec']["value"])
#            if vals:
#                # 這裡的欄位是「影像類型」（例：G/R），不是每張圖的 token 數
#                self.tiff_spec = {"version": vals[0], "nfields": None, "fields": vals[1:]}
#
#    # ---------- TIFF patch 影像對應 ----------
#
#    def image_col_index(self):
#        """回傳 (IMAGECOUNT 欄索引, 影像清單欄索引)；沒有為 -1。
#           影像清單欄優先找名為 IMAGELIST 的欄，其次是 1.8 型別為
#           ImageList 的欄（名稱不限，例：ImageInfo）。"""
#        il = self.col_index('IMAGELIST')
#        if il < 0 and self._il18 is not None:
#            il = self._il18
#        return self.col_index('IMAGECOUNT'), il
#
#    def defect_image_count(self, row):
#        ic, _ = self.image_col_index()
#        if ic < 0 or ic >= len(row):
#            return 0
#        try:
#            return max(0, int(row[ic]))
#        except ValueError:
#            return 0
#
#    def image_layout(self):
#        """影像條目在列中的排列：(start_col, nfields, how)；沒有帶圖資訊回 None。
#           how = 'declared'（IMAGELIST 欄 + TiffSpec）或 'inferred'（從資料推斷）。
#
#           有些 1.8 檔沒有 TiffSpec、影像欄也不叫 IMAGELIST（甚至掛在宣告欄位
#           之後）；此時從所有帶圖列推斷：candidate 起點取「宣告欄位之後」與
#           「IMAGECOUNT 的下一欄（若它是最後一欄）」，要求每列多出的 token 數
#           都能被自己的 IMAGECOUNT 整除、且每張圖的 token 數全檔一致。"""
#        if self._img_layout != 'unset':
#            return self._img_layout
#        ic, il = self.image_col_index()
#        layout = None
#        if ic >= 0:
#            layout = self._detect_images18(ic, il)
#            if layout is None:
#                if il >= 0 and self.tiff_spec and self.tiff_spec.get("nfields"):
#                    layout = (il, self.tiff_spec["nfields"], 'declared')
#                else:
#                    layout = self._infer_image_layout(ic, il)
#        self._img_layout = layout
#        return layout
#
#    def _detect_images18(self, ic, il):
#        """1.8 結構化影像欄：儲存格是 'Images N {id "type" ,id "type" …}' 子區塊。
#           以第一筆帶圖列判定；回 (start_col, None, 'images18') 或 None。"""
#        s = il if il >= 0 else ic + 1
#        for r in self.defects:
#            if self.defect_image_count(r) > 0:
#                return (s, None, 'images18') if s < len(r) and r[s] == 'Images' else None
#        return None
#
#    def _infer_image_layout(self, ic, il):
#        n = len(self.defect_columns)
#        # 候選起點：影像清單欄本身、宣告欄位之後、IMAGECOUNT 的下一欄（若是最後一欄）
#        starts = []
#        for s in ([il] if il >= 0 else []) + [n] + ([n - 1] if ic == n - 2 else []):
#            if s not in starts:
#                starts.append(s)
#        cands = []
#        for s in starts:
#            # 多數決：每張圖的 token 數取眾數，容忍少數壞列（health 會另外抓）
#            tally, total = {}, 0
#            for r in self.defects:
#                cnt = self.defect_image_count(r)
#                if cnt <= 0:
#                    continue
#                total += 1
#                extra = len(r) - s
#                if extra > 0 and extra % cnt == 0:
#                    k = extra // cnt
#                    tally[k] = tally.get(k, 0) + 1
#            if not tally:
#                continue
#            nf, votes = max(tally.items(), key=lambda kv: kv[1])
#            if nf >= 1 and votes >= total - max(1, total // 10):
#                cands.append((s, nf, 'inferred'))   # 容忍最多 ~10%（至少 1 列）壞列
#        if len(cands) <= 1:
#            return cands[0] if cands else None
#        # 多個一致解：優先挑「第一個欄位像 page 編號（全整數且不重複）」的
#        for s, nf, how in cands:
#            ids, good = [], True
#            for r in self.defects:
#                cnt = self.defect_image_count(r)
#                toks = r[s:]
#                if len(toks) < cnt * nf:
#                    continue        # 壞列不參與判斷
#                for k in range(cnt):
#                    v = toks[k * nf]
#                    if not v.lstrip('-').isdigit():
#                        good = False
#                        break
#                    ids.append(int(v))
#                if not good:
#                    break
#            if good and ids and len(set(ids)) == len(ids):
#                return (s, nf, how)
#        return cands[0]
#
#    def defect_image_entries(self, row):
#        """該列的影像條目 [[tok, ...], ...]，每張圖一條；解不出來回 []。"""
#        cnt = self.defect_image_count(row)
#        layout = self.image_layout()
#        if cnt <= 0 or layout is None:
#            return []
#        s, nf, how = layout
#        if how == 'images18':
#            m = re.match(r'Images\s+\d+\s*\{(.*)\}\s*$', ' '.join(row[s:]))
#            if not m:
#                return []
#            entries = [e.split() for e in m.group(1).split(',') if e.strip()]
#            return entries if len(entries) == cnt else []
#        toks = row[s:]
#        if len(toks) < cnt * nf:
#            return []
#        return [toks[k * nf:(k + 1) * nf] for k in range(cnt)]
#
#    def defect_image_filename(self, row) -> "Optional[str]":
#        """回傳該列的 per-defect 影像檔名；沒有則回 None（ADEPT 增補）。
#
#        1.8（rSEM 類）KLARF 的列尾常帶
#        `Image N { "file.jpg" "JPG" ... }` 或 `Images N { ... }` 子區塊；
#        取區塊內第一個帶引號的字串當檔名（概念移植自 GLAS klarf_parser 的
#        _map_row_tokens / _image_filename，改寫在 raw-token 列表示上）。
#        純唯讀查詢，不影響既有解析與無損寫回。"""
#        for k, tok in enumerate(row):
#            if tok in ('Image', 'Images'):
#                tail = ' '.join(row[k:])
#                b0 = tail.find('{')
#                if b0 < 0:
#                    return None
#                b1 = _find_matching_brace(tail, b0)
#                block = tail[b0 + 1:b1] if b1 > b0 else tail[b0 + 1:]
#                m = re.search(r'"([^"]*)"', block)
#                return m.group(1) if m else None
#        return None
#
#    def total_image_count(self):
#        return sum(self.defect_image_count(r) for r in self.defects)
#
#    def defect_image_map(self, n_pages=None):
#        """建立 defect → TIFF page（0-based）的對應。
#
#        回傳 {"mode": 'imagelist' | 'sequential' | None,
#              "base": 0 | 1 | None,       # imagelist 模式時 id 的起算基準
#              "pages": [ [page, ...] 依 self.defects 順序 ],
#              "notes": [str]}
#
#        mode 判定：
#          - IMAGELIST 每條目的第一個欄位若全是整數且不重複，視為 TIFF 的
#            page 編號（KLA 慣例，通常 1-based）→ 'imagelist'
#          - 否則退回「依 defect 出現順序連續配頁」→ 'sequential'
#        """
#        notes = []
#        ic, il = self.image_col_index()
#        if ic < 0:
#            return {"mode": None, "base": None,
#                    "pages": [[] for _ in self.defects],
#                    "notes": ["No IMAGECOUNT column; this KLARF carries no patch info."]}
#        counts = [self.defect_image_count(r) for r in self.defects]
#        total = sum(counts)
#        if total == 0:
#            return {"mode": None, "base": None,
#                    "pages": [[] for _ in self.defects],
#                    "notes": ["IMAGECOUNT is 0 for every defect."]}
#
#        # 嘗試 imagelist 模式：第一欄全為整數且完整
#        ids_per_row, usable = [], (self.image_layout() is not None)
#        if usable:
#            for r, cnt in zip(self.defects, counts):
#                entries = self.defect_image_entries(r)
#                if len(entries) != cnt or not all(
#                        e and e[0].lstrip('-').isdigit() for e in entries):
#                    usable = False
#                    break
#                ids_per_row.append([int(e[0]) for e in entries])
#        layout = self.image_layout()
#        if usable and layout and layout[2] == 'images18' and all(
#                ids == list(range(1, len(ids) + 1)) for ids in ids_per_row):
#            # 1.8 結構化格式：id 是「defect 內的圖序號」，不是全域 page 編號
#            usable = False
#            notes.append("ImageList ids are per-defect ordinals (1..IMAGECOUNT); "
#                         "mapping pages sequentially in defect order.")
#        if usable:
#            flat = [i for ids in ids_per_row for i in ids]
#            if len(set(flat)) != len(flat):
#                usable = False
#                notes.append("IMAGELIST ids contain duplicates; "
#                             "falling back to sequential mapping.")
#        if usable:
#            lo, hi = min(flat), max(flat)
#            if n_pages is not None:
#                if lo >= 1 and hi <= n_pages and not (lo == 0):
#                    base = 1
#                elif lo >= 0 and hi <= n_pages - 1:
#                    base = 0
#                else:
#                    usable = False
#                    notes.append(
#                        f"IMAGELIST ids [{lo}..{hi}] do not fit in {n_pages} TIFF pages; "
#                        "falling back to sequential mapping.")
#            else:
#                base = 0 if lo == 0 else 1
#        if usable:
#            if base == 1:
#                notes.append("IMAGELIST first field treated as 1-based TIFF page number.")
#            else:
#                notes.append("IMAGELIST first field treated as 0-based TIFF page index.")
#            return {"mode": "imagelist", "base": base,
#                    "pages": [[i - base for i in ids] for ids in ids_per_row],
#                    "notes": notes}
#
#        # sequential：依出現順序連續分配
#        pages, cum = [], 0
#        for cnt in counts:
#            pages.append(list(range(cum, cum + cnt)))
#            cum += cnt
#        if n_pages is not None and total != n_pages:
#            notes.append(f"Sum of IMAGECOUNT ({total}) != TIFF page count ({n_pages}); "
#                         "sequential mapping may be off.")
#        notes.append("Pages assigned sequentially in defect order.")
#        return {"mode": "sequential", "base": None, "pages": pages, "notes": notes}
#
#    def tiff_path(self):
#        """猜出對應的 TIFF 檔路徑（存在才回傳）。
#           依序嘗試：TiffFileName（含只取檔名放同資料夾）、KLARF 同名 .tif/.tiff。"""
#        cands = []
#        base_dir = os.path.dirname(self.source_path) if self.source_path else None
#        if self.tiff_file_name:
#            name = self.tiff_file_name.replace('\\', '/')
#            cands.append(name)                          # 絕對或相對於 cwd
#            if base_dir is not None:
#                cands.append(os.path.join(base_dir, os.path.basename(name)))
#        if self.source_path:
#            stem = os.path.splitext(self.source_path)[0]
#            for p in (stem, self.source_path):
#                for ext in ('.tif', '.tiff', '.TIF', '.TIFF'):
#                    cands.append(p + ext)
#        seen = set()
#        for c in cands:
#            if c and c not in seen:
#                seen.add(c)
#                if os.path.isfile(c):
#                    return c
#        return None
#
#    def image_block_span(self, row):
#        """回傳列中 ``Image(s) N { … }`` 子區塊的 (起始索引, token 數)；沒有回 None。
#
#        ADEPT 增補（M5）。有一種真實 1.8 變體（fab_probe 稱 variant D）：
#        影像欄是 ``ImageList`` 型別（例：IMAGEINFO）且**不在最後一欄**，
#        同時整份檔案沒有 IMAGECOUNT 欄。這種列裡 ``Images 1 { "a.jpg" … }``
#        佔多個 token 但只算一欄，若直接用 token 數比對欄數會全列誤判違法。
#        """
#        for k, tok in enumerate(row):
#            if tok not in ('Image', 'Images'):
#                continue
#            depth = 0
#            for j in range(k, len(row)):
#                depth += row[j].count('{') - row[j].count('}')
#                if '{' in row[j] or '}' in row[j]:
#                    if depth <= 0:
#                        return (k, j - k + 1)
#            return (k, len(row) - k)
#        return None
#
#    def effective_row_len(self, row):
#        """把影像子區塊算成一欄之後的等效欄數（ADEPT 增補，M5）。"""
#        span = self.image_block_span(row)
#        return len(row) if span is None else len(row) - (span[1] - 1)
#
#    def row_len_ok(self, row):
#        """該列 token 數是否合法。影像欄是變動長度：每張圖佔 image_layout()
#           的 nfields 個 token，IMAGECOUNT=0 時可整欄省略。"""
#        n = len(self.defect_columns)
#        ic, il = self.image_col_index()
#        if ic < 0:
#            # 沒有 IMAGECOUNT 欄。若列裡帶 Image(s){…} 子區塊（variant D），
#            # 把整個區塊折算成一欄再比對；否則維持原本的嚴格比對。
#            return self.effective_row_len(row) == n
#        cnt = self.defect_image_count(row)
#        layout = self.image_layout()
#        if layout is not None:
#            s, nf, how = layout
#            if how == 'images18':
#                if cnt <= 0:
#                    tail = ' '.join(row[s:]).strip()
#                    return (len(row) in ({s, n} if s < n else {n})
#                            or bool(re.fullmatch(r'Images\s+0\s*\{\s*\}', tail)))
#                return len(self.defect_image_entries(row)) == cnt
#            if cnt <= 0:
#                return len(row) in ({s, n} if s < n else {n})
#            return len(row) == s + cnt * nf
#        # 排列推斷不出來：退回保守判斷
#        base = n - (1 if il >= 0 else 0)
#        if cnt <= 0:
#            return len(row) in (base, n)
#        if il >= 0:
#            return len(row) >= base + cnt
#        return len(row) == n
#
#    # ---------- 編輯操作 ----------
#
#    def set_header(self, name, value):
#        if name not in self._header:
#            raise ValueError(f"header 沒有可編輯欄位 {name}")
#        self._header[name]["value"] = value
#        self._header[name]["dirty"] = True
#
#    def batch_reclass(self, from_class, to_class):
#        """把某 class 的所有 defect 改成另一個 class；回傳筆數。"""
#        i = self.col_index('CLASSNUMBER')
#        if i < 0:
#            raise ValueError("找不到 CLASSNUMBER 欄位")
#        n = 0
#        for r in self.defects:
#            if r[i] == str(from_class):
#                r[i] = str(to_class)
#                n += 1
#        self._defect_dirty = True
#        return n
#
#    def batch_set(self, match_col, match_val, set_col, set_val):
#        """把「match_col == match_val」的所有 defect 之 set_col 設為 set_val；回傳筆數。
#           match_col / set_col 可以是任意欄位（例：where ROUGHBINNUMBER=3 → set FINEBINNUMBER=4）。"""
#        mi = self.col_index(match_col)
#        si = self.col_index(set_col)
#        if mi < 0:
#            raise ValueError(f"找不到欄位 {match_col}")
#        if si < 0:
#            raise ValueError(f"找不到欄位 {set_col}")
#        mv, sv = str(match_val), str(set_val)
#        n = 0
#        for r in self.defects:
#            if mi < len(r) and r[mi] == mv and si < len(r):
#                r[si] = sv
#                n += 1
#        if n:
#            self._defect_dirty = True
#        return n
#
#    def die_stack(self, class_number, target_xindex, target_yindex):
#        """把某 class 的 defect 全部歸到同一個 die（只改 XINDEX/YINDEX，
#        保留 die 內相對座標 XREL/YREL）。回傳筆數。"""
#        ci = self.col_index('CLASSNUMBER')
#        xi = self.col_index('XINDEX')
#        yi = self.col_index('YINDEX')
#        if min(ci, xi, yi) < 0:
#            raise ValueError("die stack 需要 CLASSNUMBER / XINDEX / YINDEX 欄位")
#        n = 0
#        for r in self.defects:
#            if r[ci] == str(class_number):
#                r[xi] = str(int(target_xindex))
#                r[yi] = str(int(target_yindex))
#                n += 1
#        self._defect_dirty = True
#        self.summary_stale = True    # 疊 die 會改變 NDEFDIE
#        return n
#
#    def set_cell(self, row_idx, col_name, value):
#        j = self.col_index(col_name)
#        if j < 0:
#            raise ValueError(f"找不到欄位 {col_name}")
#        self.defects[row_idx][j] = str(value)
#        self._defect_dirty = True
#
#    def delete_defects(self, row_indices):
#        for idx in sorted(set(row_indices), reverse=True):
#            del self.defects[idx]
#        self._defect_dirty = True
#        self.summary_stale = True
#
#    def add_defect(self, row_tokens):
#        row = [str(x) for x in row_tokens]
#        if not self.row_len_ok(row):
#            raise ValueError(
#                f"欄位數不符：需要 {len(self.defect_columns)} 個，給了 {len(row_tokens)}")
#        self.defects.append(row)
#        self._defect_dirty = True
#        self.summary_stale = True
#
#    # ---------- 寫回（無損拼接） ----------
#
#    def _any_dirty(self):
#        return (self._defect_dirty or self._classlookup_dirty or self.summary_stale
#                or any(h["dirty"] for h in self._header.values()))
#
#    def _render_header(self, name, h):
#        if self._is18:
#            if h.get("rec"):     # Record XxxRecord "值"
#                return re.sub(r'"(?:[^"\\]|\\.)*"', lambda _m: h["value"], h["orig"], count=1)
#            return re.sub(r'\{[^}]*\}', '{' + h["value"] + '}', h["orig"], count=1)
#        return re.sub(
#            r'(\b' + re.escape(name) + r'\b[ \t]+)[^;]*(;)',
#            lambda m: m.group(1) + h["value"] + m.group(2),
#            h["orig"], count=1)
#
#    def _eol(self):
#        """沿用原檔的換行字元，避免產出檔 CRLF/LF 混用（Klarity 等工具會吃不到）。"""
#        return '\r\n' if '\r\n' in self._text else '\n'
#
#    def _render_defects(self):
#        nl = self._eol()
#        if self._is18:
#            rows = nl.join('          ' + ' '.join(r) + ' ;' for r in self.defects)
#            return f'Data {len(self.defects)}{nl}        {{{nl}{rows}{nl}        }}'
#        rows = nl.join(' ' + ' '.join(r) for r in self.defects)
#        return 'DefectList' + nl + rows + ';'
#
#    def _recompute_summary_12(self):
#        """依目前 defect 重算 summary：
#           NDEFECT/NDEFDIE 直接算；DEFDENSITY 等比縮放；NDIE 保留原值。"""
#        if not self._summary_rows:
#            return
#        sc = [c.upper() for c in self._summary_columns]
#        def sidx(n): return sc.index(n) if n in sc else -1
#        i_test, i_nd, i_ndd, i_dens = (sidx('TESTNO'), sidx('NDEFECT'),
#                                       sidx('NDEFDIE'), sidx('DEFDENSITY'))
#        ti = self.col_index('TEST')
#        xi, yi = self.col_index('XINDEX'), self.col_index('YINDEX')
#        single = (ti < 0 and len(self._summary_rows) == 1)
#        for row in self._summary_rows:
#            if i_test >= 0 and ti >= 0:
#                ds = [d for d in self.defects if d[ti] == row[i_test]]
#            elif single:
#                ds = self.defects
#            else:
#                self.warnings.append(
#                    "SummaryList has multiple rows but defects have no TEST column; summary not recomputed.")
#                return
#            new_nd = len(ds)
#            old_nd = None
#            if i_nd >= 0:
#                try:
#                    old_nd = int(row[i_nd])
#                except ValueError:
#                    old_nd = None
#                row[i_nd] = str(new_nd)
#            if i_ndd >= 0 and xi >= 0 and yi >= 0:
#                row[i_ndd] = str(len({(d[xi], d[yi]) for d in ds}))
#            if i_dens >= 0 and old_nd:
#                try:
#                    row[i_dens] = f"{float(row[i_dens]) * new_nd / old_nd:.10e}"
#                except (ValueError, ZeroDivisionError):
#                    pass
#
#    def _render_summary_12(self):
#        nl = self._eol()
#        rows = nl.join('  ' + ' '.join(r) for r in self._summary_rows)
#        return 'SummaryList' + nl + rows + ';'
#
#    def to_text(self):
#        """產生寫回檔案的內容。沒改動時回傳與原檔完全相同的字串。"""
#        if not self._any_dirty():
#            return self._text
#        t = self._text
#        for name, h in self._header.items():
#            if h["dirty"]:
#                t = t.replace(h["orig"], self._render_header(name, h), 1)
#        if self._defect_dirty and self._defect_orig is not None:
#            t = t.replace(self._defect_orig, self._render_defects(), 1)
#        if (self.summary_stale and self.auto_recompute_summary
#                and self._summary_orig is not None):
#            if self._is18:
#                self.warnings.append("1.8 summary auto-recompute is not implemented; kept unchanged.")
#            else:
#                self._recompute_summary_12()
#                t = t.replace(self._summary_orig, self._render_summary_12(), 1)
#        return t
#
#    def save(self, path):
#        with open(path, 'w', encoding='utf-8', newline='') as f:
#            f.write(self.to_text())
#
#    # ---------- API KLARF：用固定 FOV 網格鋪滿一或多塊區域 ----------
#    def _grid_centers(self, rects, fov_x, fov_y, overlap):
#        """回傳所有矩形合併後的網格中心點 [(cx, cy, cls_or_None), ...]。
#           rects 的元素可為 (x0,y0,x1,y1) 或 (x0,y0,x1,y1,class)。"""
#        import math
#        sx = max(1e-9, fov_x * (1 - overlap))
#        sy = max(1e-9, fov_y * (1 - overlap))
#        centers = []
#        for rect in rects:
#            cls = rect[4] if len(rect) > 4 else None
#            x0, y0, x1, y1 = rect[0], rect[1], rect[2], rect[3]
#            if x1 < x0:
#                x0, x1 = x1, x0
#            if y1 < y0:
#                y0, y1 = y1, y0
#            nx = max(1, math.ceil((x1 - x0) / sx))
#            ny = max(1, math.ceil((y1 - y0) / sy))
#            for j in range(ny):
#                for i in range(nx):
#                    centers.append((x0 + fov_x/2 + i*sx, y0 + fov_y/2 + j*sy, cls))
#        return centers
#
#    def make_api_rows(self, rects, fov_x, fov_y, overlap, dies, class_num, did_start=1,
#                      dies_by_class=None):
#        """在 die 內相對座標的一或多個矩形內鋪 FOV 網格點，複製到指定的 die。
#           rects 可為單一 (x0,y0,x1,y1) 或其 list，元素可帶第 5 個值當 class。
#           dies_by_class 可為 {class: [(xi,yi), ...]}，讓每個 class 的選區套用到
#           自己的一組 die；沒指定的 class 則退回共用的 dies。
#           回傳 (rows, per_die, n_regions)。
#           未指定的欄位（TEST/XSIZE/DEFECTAREA…）沿用原檔第一筆 defect 的值，
#           避免產出 TEST=0、尺寸全 0 這種下游工具（如 Klarity）吃不到的列。"""
#        if rects and isinstance(rects[0], (int, float)):
#            rects = [rects]
#        cols = self.defect_columns
#        pos = {c.upper(): k for k, c in enumerate(cols)}
#        # 範本列：優先沿用原檔第一筆 defect，其餘欄位才補 0
#        # （帶圖的列比欄位數長，截到欄位數即可；IMAGECOUNT 歸 0）
#        if self.defects and len(self.defects[0]) >= len(cols) - 1 \
#                and self.row_len_ok(self.defects[0]):
#            template = (list(self.defects[0]) + ["0"])[:len(cols)]
#        else:
#            template = ["0"] * len(cols)
#        if 'IMAGECOUNT' in pos:
#            template[pos['IMAGECOUNT']] = "0"
#        if 'IMAGELIST' in pos:
#            template[pos['IMAGELIST']] = "0"
#
#        def fmt(v):
#            return f"{v:.3f}" if self.version == '1.2' else str(int(round(v)))
#
#        rows = []
#        did = did_start
#        per_die = 0
#        for rect in rects:
#            cls_v = str(rect[4]) if len(rect) > 4 and rect[4] is not None else str(class_num)
#            centers = self._grid_centers([rect], fov_x, fov_y, overlap)
#            per_die += len(centers)
#            rdies = None
#            if dies_by_class:
#                rdies = dies_by_class.get(cls_v)
#            if not rdies:
#                rdies = dies
#            for (dxi, dyi) in rdies:
#                for (cx, cy, _c) in centers:
#                    row = list(template)
#                    for name, val in (('DEFECTID', str(did)), ('XREL', fmt(cx)),
#                                      ('YREL', fmt(cy)), ('XINDEX', str(int(dxi))),
#                                      ('YINDEX', str(int(dyi))), ('CLASSNUMBER', cls_v)):
#                        if name in pos:
#                            row[pos[name]] = val
#                    rows.append(row)
#                    did += 1
#        return rows, per_die, len(rects)
#
#    def api_text(self, rects, fov_x, fov_y, overlap, dies, class_num, did_start=1,
#                 keep_classes=None, dies_by_class=None):
#        """產生全新的 API KLARF 內容（沿用本檔 header 為範本，換掉 defect list）。
#           keep_classes 指定「要保留的原始 defect 之 CLASSNUMBER 集合」，會併入網格點，
#           並把所有輸出列的 DEFECTID 從 did_start 起重新排列。
#           回傳 (text, per_die, n_regions, total, kept, warnings)。"""
#        rows, per_die, n_reg = self.make_api_rows(rects, fov_x, fov_y, overlap,
#                                                  dies, class_num, did_start,
#                                                  dies_by_class)
#        kept = 0
#        ci = self.col_index('CLASSNUMBER')
#        if keep_classes and ci >= 0:
#            ks = {str(c) for c in keep_classes}
#            for r in self.defects:
#                if ci < len(r) and r[ci] in ks:
#                    rows.append(list(r)); kept += 1
#        # 重新排列 DEFECTID（網格 + 保留的原始 defect 一起連號）
#        di = self.col_index('DEFECTID')
#        if di >= 0:
#            for k, r in enumerate(rows):
#                if di < len(r):
#                    r[di] = str(did_start + k)
#        clone = load(self._text)
#        clone.defects = rows
#        clone._defect_dirty = True
#        text = clone.to_text()
#        warns = []
#        total, ndie = len(rows), len(dies)
#        if clone._summary_orig and clone._summary_columns and clone._summary_rows:
#            # 以原檔第一列為底，只改能安全推算的欄位；其餘（NDIE 等）原值保留，
#            # 避免寫出 DEFDENSITY 0 / NDIE 1 這種下游工具會拒收的值。
#            row = list(clone._summary_rows[0])
#            sc = [c.upper() for c in clone._summary_columns]
#            def sidx(n): return sc.index(n) if n in sc else -1
#            i_nd, i_ndd, i_dens = sidx('NDEFECT'), sidx('NDEFDIE'), sidx('DEFDENSITY')
#            old_nd = None
#            if i_nd >= 0:
#                try:
#                    old_nd = int(row[i_nd])
#                except ValueError:
#                    old_nd = None
#                row[i_nd] = str(total)
#            if i_ndd >= 0:
#                row[i_ndd] = str(ndie)
#            if i_dens >= 0 and old_nd:
#                try:
#                    row[i_dens] = f"{float(row[i_dens]) * total / old_nd:.10e}"
#                except (ValueError, ZeroDivisionError):
#                    pass
#            nl = clone._eol()
#            block = 'SummaryList' + nl + '  ' + ' '.join(row) + ';'
#            text = text.replace(clone._summary_orig, block, 1)
#        elif self.version == '1.8':
#            warns.append("1.8：defect 網格已產生，但 SummaryList 未重算（1.8 summary 尚未支援）。")
#        return text, per_die, n_reg, total, kept, warns
#
#
#def load(src):
#    """src 可為檔案路徑或 KLARF 文字內容。"""
#    if isinstance(src, str) and ('\n' not in src) and os.path.exists(src):
#        with open(src, 'r', encoding='utf-8', errors='replace') as f:
#            return KlarfDoc(f.read(), source_path=src)
#    return KlarfDoc(src)
#
#
## ================================================================ 格式健檢
## 規則多半來自實戰：Klarity 等下游工具吃不到檔案時，最常見的就是這幾類問題。
#
#class Issue:
#    """一條健檢結果。fix_code 有值代表可一鍵修正。"""
#    def __init__(self, code, level, title, detail, count=0, fixable=False):
#        self.code = code          # 規則代號
#        self.level = level        # 'error' / 'warn' / 'info'
#        self.title = title
#        self.detail = detail
#        self.count = count        # 受影響的筆數（0=不適用）
#        self.fixable = fixable
#
#
#def _nums(seq):
#    out = []
#    for v in seq:
#        try:
#            out.append(float(v))
#        except (TypeError, ValueError):
#            pass
#    return out
#
#
#def _valid_tests(doc):
#    """檔案裡合法的 test 編號：InspectionTest 宣告 + SummaryList 的 TESTNO。"""
#    ts = {m.group(1) for m in re.finditer(r'(?m)^[ \t]*InspectionTest[ \t]+(\d+)[ \t]*;', doc._text)}
#    sc = [c.upper() for c in (doc._summary_columns or [])]
#    if 'TESTNO' in sc:
#        j = sc.index('TESTNO')
#        for r in doc._summary_rows:
#            if j < len(r):
#                ts.add(r[j])
#    return ts
#
#
#SIZE_COLS = ('XSIZE', 'YSIZE', 'DEFECTAREA', 'DSIZE')
#REQUIRED_12 = ('FileVersion', 'LotID', 'WaferID', 'DiePitch', 'SampleSize',
#               'DeviceID', 'StepID', 'InspectionStationID', 'SampleType',
#               'OrientationMarkLocation')
#
#
#def lint(doc):
#    """檢查一份 KLARF，回傳 [Issue]。"""
#    out = []
#    t = doc._text
#    cols = doc.defect_columns
#    n = len(doc.defects)
#
#    # --- 結構層 ---
#    crlf = t.count('\r\n'); lf = t.count('\n') - crlf
#    if crlf and lf:
#        out.append(Issue('eol', 'error', 'Mixed line endings (CRLF + LF)',
#                         f'The file mixes {crlf} CRLF and {lf} LF line breaks. '
#                         'Strict parsers (Klarity among them) may fail to read it at all.',
#                         fixable=True))
#    if not t.rstrip().endswith('EndOfFile;'):
#        out.append(Issue('eof', 'error', 'Missing EndOfFile; terminator',
#                         'A KLARF must end with EndOfFile; or it is treated as truncated.',
#                         fixable=True))
#    if not cols:
#        out.append(Issue('nospec', 'error', 'No defect column definition found',
#                         'DefectRecordSpec / Columns could not be read, so the remaining checks were skipped.'))
#        return out
#
#    if not doc._is18:
#        m = re.search(r'DefectRecordSpec\s+(\d+)\s+([^;]+);', t)
#        if m and int(m.group(1)) != len(cols):
#            out.append(Issue('speccount', 'error', 'DefectRecordSpec column count mismatch',
#                             f'Declares {m.group(1)} columns but lists {len(cols)}.',
#                             fixable=True))
#
#    # IMAGELIST 是變動長度欄（每張圖 TiffSpec.nfields 個 token），用 row_len_ok 判定
#    bad_len = sum(1 for r in doc.defects if not doc.row_len_ok(r))
#    if bad_len:
#        out.append(Issue('rowlen', 'error', 'Defect rows do not match the column definition',
#                         f'{bad_len} defect rows do not match the {len(cols)}-column definition '
#                         '(IMAGELIST rows are allowed their declared extra image tokens). '
#                         'The fix pads with 0 or truncates; rows carrying images are only padded.',
#                         bad_len, fixable=True))
#
#    # --- DEFECTID ---
#    di = doc.col_index('DEFECTID')
#    if di >= 0:
#        ids = [r[di] for r in doc.defects if di < len(r)]
#        dup = len(ids) - len(set(ids))
#        if dup:
#            out.append(Issue('dupid', 'error', 'Duplicate DEFECTID',
#                             f'{dup} duplicated DEFECTID values. Downstream tools may keep only one of each.',
#                             dup, fixable=True))
#
#    # --- TEST 欄與 InspectionTest 對應 ---
#    ti = doc.col_index('TEST')
#    if ti >= 0 and not doc._is18:
#        valid = _valid_tests(doc)
#        if valid:
#            bad = sum(1 for r in doc.defects if ti < len(r) and r[ti] not in valid)
#            if bad:
#                out.append(Issue('test', 'error', 'Defect TEST does not match any inspection test',
#                                 f'{bad} defects have a TEST value outside {sorted(valid)} '
#                                 '(generated files often leave it as 0). Review tools cannot '
#                                 'match these defects to an inspection, so they are skipped.',
#                                 bad, fixable=True))
#
#    # --- 尺寸欄全 0 ---
#    size_idx = [(c, doc.col_index(c)) for c in SIZE_COLS]
#    size_idx = [(c, i) for c, i in size_idx if i >= 0]
#    if size_idx and n:
#        zero = 0
#        for r in doc.defects:
#            vals = [r[i] for _c, i in size_idx if i < len(r)]
#            if vals and all(_isz(v) for v in vals):
#                zero += 1
#        if zero:
#            can = any(any(not _isz(r[i]) for r in doc.defects if i < len(r))
#                      for _c, i in size_idx)
#            out.append(Issue('zerosize', 'warn', 'Defect size columns are all zero',
#                             f'{zero} defects have {"/".join(c for c, _ in size_idx)} all set to 0. '
#                             'Many tools discard zero-sized defects or treat them as invalid.'
#                             + ('' if can else ' No non-zero values exist in this file, '
#                                'so it cannot be fixed automatically.'),
#                             zero, fixable=can))
#
#    # --- 座標型別 ---
#    xr, yr = doc.col_index('XREL'), doc.col_index('YREL')
#    if doc._is18 and xr >= 0:
#        frac = sum(1 for r in doc.defects if xr < len(r) and '.' in r[xr])
#        if frac:
#            out.append(Issue('coordint', 'warn', '1.8 coordinates should be integer nm',
#                             f'{frac} XREL values contain a decimal point. KLARF 1.8 stores coordinates as integer nanometres.',
#                             frac, fixable=True))
#    if (not doc._is18) and xr >= 0 and doc.defects:
#        xs = _nums(r[xr] for r in doc.defects if xr < len(r))
#        if xs and all(abs(v) > 1e6 for v in xs):
#            out.append(Issue('coordunit', 'warn', '1.2 coordinates look like nanometre values',
#                             'KLARF 1.2 stores coordinates in micrometres, but every XREL '
#                             'exceeds 1e6 — this looks like nanometre values written into a 1.2 '
#                             'file. This is not fixed automatically; please check the source.'))
#
#    # --- 座標是否落在 die 內 ---
#    try:
#        _dp = doc._header.get('DiePitch') or {}
#        pit = _nums(re.split(r'[\s,]+', str(_dp.get('value', '')).strip()))
#    except Exception:
#        pit = []
#    if len(pit) >= 2 and pit[0] > 0 and xr >= 0 and yr >= 0:
#        tol = 0.02
#        oob = 0
#        for r in doc.defects:
#            try:
#                x, y = float(r[xr]), float(r[yr])
#            except (ValueError, IndexError):
#                continue
#            if not (-pit[0]*tol <= x <= pit[0]*(1+tol) and -pit[1]*tol <= y <= pit[1]*(1+tol)):
#                oob += 1
#        if oob:
#            out.append(Issue('oob', 'info', 'Defect coordinates fall outside the die',
#                             f'{oob} defects have XREL/YREL outside the die pitch '
#                             f'({pit[0]:g} × {pit[1]:g}). This is expected if the file uses '
#                             'absolute coordinates or a shifted DieOrigin.',
#                             oob))
#
#    # --- ClassLookup ---
#    ci = doc.col_index('CLASSNUMBER')
#    if ci >= 0 and doc.class_lookup:
#        known = {str(k) for k in (doc.class_lookup or {})}
#        miss = sorted({r[ci] for r in doc.defects if ci < len(r) and r[ci] not in known})
#        if miss:
#            out.append(Issue('class', 'warn', 'Defects use classes that are not defined',
#                             'ClassLookup does not define: ' + ", ".join(miss[:12])
#                             + ('…' if len(miss) > 12 else ''),
#                             len(miss)))
#
#    # --- SummaryList ---
#    if doc._summary_rows and doc._summary_columns:
#        sc = [c.upper() for c in (doc._summary_columns or [])]
#        if 'NDEFECT' in sc:
#            j = sc.index('NDEFECT')
#            declared = sum(int(r[j]) for r in doc._summary_rows
#                           if j < len(r) and r[j].lstrip('-').isdigit())
#            if declared != n:
#                out.append(Issue('summary', 'warn', 'SummaryList defect count does not match the DefectList',
#                                 f'The summary declares {declared} defects but the DefectList '
#                                 f'has {n}. Note: this difference is normal for files that only '
#                                 'contain a sampled review subset.',
#                                 abs(declared - n), fixable=True))
#        if 'DEFDENSITY' in sc:
#            j = sc.index('DEFDENSITY')
#            if any(j < len(r) and _isz(r[j]) for r in doc._summary_rows):
#                out.append(Issue('density', 'warn', 'DEFDENSITY is zero',
#                                 'A zero defect density usually means the summary was rebuilt without recomputing it.'))
#
#    # --- 必要 header ---
#    if not doc._is18:
#        miss = [f for f in REQUIRED_12 if f not in doc._header]
#        if miss:
#            out.append(Issue('header', 'warn', 'Common header fields are missing',
#                             'Not found: ' + ', '.join(miss) +
#                             '. Some tools require these before they will load a file. '
#                             'Values cannot be invented, so this is not auto-fixable.',
#                             len(miss)))
#    return out
#
#
#def _isz(v):
#    try:
#        return float(v) == 0.0
#    except (TypeError, ValueError):
#        return False
#
#
#def _median(vals):
#    s = sorted(vals)
#    return s[len(s)//2] if s else None
#
#
#def autofix(doc, codes):
#    """套用選定的修正，回傳 (新的 KLARF 文字, [說明訊息])。原 doc 不動。"""
#    d = load(doc.to_text())
#    msgs = []
#    cols = d.defect_columns
#    codes = set(codes)
#
#    if 'rowlen' in codes and cols:
#        k = 0
#        for r in d.defects:
#            if d.row_len_ok(r):
#                continue
#            k += 1
#            cnt = d.defect_image_count(r)
#            if cnt <= 0:
#                while len(r) < len(cols):
#                    r.append('0')
#                del r[len(cols):]
#            else:
#                # 有 patch 影像的列只補不砍，避免破壞影像條目
#                target = len(cols)
#                layout = d.image_layout()
#                if layout is not None and layout[1]:   # images18 無固定寬度，不硬補
#                    target = layout[0] + cnt * layout[1]
#                while len(r) < target:
#                    r.append('0')
#        if k:
#            d._defect_dirty = True; msgs.append(f'補齊/截斷 {k} 筆欄數不符的 defect')
#
#    if 'zerosize' in codes:
#        idx = [(c, d.col_index(c)) for c in SIZE_COLS]
#        idx = [(c, i) for c, i in idx if i >= 0]
#        fill = {}
#        for c, i in idx:
#            vals = [float(r[i]) for r in d.defects
#                    if i < len(r) and not _isz(r[i]) and _isnum_s(r[i])]
#            if vals:
#                fill[i] = (c, _median(vals), r'{:g}'.format(_median(vals)))
#        if fill:
#            k = 0
#            for r in d.defects:
#                vals = [r[i] for _c, i in idx if i < len(r)]
#                if vals and all(_isz(v) for v in vals):
#                    for i, (_c, _v, txt) in fill.items():
#                        if i < len(r):
#                            r[i] = txt
#                    k += 1
#            if k:
#                d._defect_dirty = True
#                msgs.append(f'用檔內的中位數尺寸填補 {k} 筆零尺寸 defect')
#
#    if 'test' in codes:
#        ti = d.col_index('TEST')
#        valid = _valid_tests(d)
#        if ti >= 0 and valid:
#            good = sorted(valid, key=lambda s: (0, int(s)) if s.isdigit() else (1, s))[0]
#            k = 0
#            for r in d.defects:
#                if ti < len(r) and r[ti] not in valid:
#                    r[ti] = good; k += 1
#            if k:
#                d._defect_dirty = True; msgs.append(f'把 {k} 筆 defect 的 TEST 改成 {good}')
#
#    if 'coordint' in codes and d._is18:
#        k = 0
#        for name in ('XREL', 'YREL'):
#            i = d.col_index(name)
#            if i < 0:
#                continue
#            for r in d.defects:
#                if i < len(r) and '.' in r[i] and _isnum_s(r[i]):
#                    r[i] = str(int(round(float(r[i])))); k += 1
#        if k:
#            d._defect_dirty = True; msgs.append(f'把 {k} 個含小數的座標改為整數 nm')
#
#    if 'dupid' in codes:
#        di = d.col_index('DEFECTID')
#        if di >= 0:
#            for k, r in enumerate(d.defects, 1):
#                if di < len(r):
#                    r[di] = str(k)
#            d._defect_dirty = True
#            msgs.append(f'把 DEFECTID 重新編號為 1..{len(d.defects)}')
#
#    if 'summary' in codes:
#        d.auto_recompute_summary = True
#        d.summary_stale = True
#        d._defect_dirty = True
#        msgs.append('依實際 defect 重算 SummaryList（NDIE 保留原值）')
#
#    text = d.to_text()
#
#    if 'speccount' in codes and not d._is18:
#        def _fix(m):
#            return f'DefectRecordSpec {len(cols)} {m.group(2)};'
#        text2 = re.sub(r'DefectRecordSpec\s+(\d+)\s+([^;]+);', _fix, text, count=1)
#        if text2 != text:
#            text = text2; msgs.append(f'把 DefectRecordSpec 的欄數改成 {len(cols)}')
#
#    if 'eol' in codes:
#        crlf = text.count('\r\n'); lf = text.count('\n') - crlf
#        nl = '\r\n' if crlf >= lf else '\n'
#        text = text.replace('\r\n', '\n')
#        if nl == '\r\n':
#            text = text.replace('\n', '\r\n')
#        msgs.append('把換行統一為 ' + ('CRLF' if nl == '\r\n' else 'LF'))
#
#    if 'eof' in codes and not text.rstrip().endswith('EndOfFile;'):
#        nl = '\r\n' if '\r\n' in text else '\n'
#        text = text.rstrip() + nl + 'EndOfFile;' + nl
#        msgs.append('補上結尾的 EndOfFile;')
#
#    return text, msgs
#
#
#def _isnum_s(v):
#    try:
#        float(v); return True
#    except (TypeError, ValueError):
#        return False
#
#
## ================================================================ KLARF 比對
#
## 這幾欄已由 added/removed/reclass/moved 表達，不再列入「其他欄位變化」
#_SKIP_FIELDS = {'DEFECTID', 'XREL', 'YREL', 'XINDEX', 'YINDEX', 'CLASSNUMBER'}
#
#
#def _pts_for_compare(doc):
#    """把 defect 轉成統一單位(nm)的比對用結構。"""
#    f = doc.unit_info()['to_nm']
#    xi, yi = doc.col_index('XINDEX'), doc.col_index('YINDEX')
#    xr, yr = doc.col_index('XREL'), doc.col_index('YREL')
#    ci, di = doc.col_index('CLASSNUMBER'), doc.col_index('DEFECTID')
#    out = []
#    for k, r in enumerate(doc.defects):
#        try:
#            die = (int(r[xi]), int(r[yi])) if xi >= 0 and yi >= 0 else (0, 0)
#            x = float(r[xr]) * f if xr >= 0 else 0.0
#            y = float(r[yr]) * f if yr >= 0 else 0.0
#        except (ValueError, IndexError):
#            continue
#        out.append({'i': k, 'id': r[di] if 0 <= di < len(r) else str(k),
#                    'die': die, 'x': x, 'y': y,
#                    'cls': r[ci] if 0 <= ci < len(r) else '0', 'row': r})
#    return out
#
#
#def _same_number(a, b):
#    """0.03 與 0.030、1e3 與 1000 視為相同，避免格式差異被當成變化。"""
#    try:
#        return float(a) == float(b)
#    except (TypeError, ValueError):
#        return False
#
#
#def compare(doc_a, doc_b, tol_nm=500.0, mode='position'):
#    """比對兩份 KLARF。mode='position' 依 die+座標配對（容差 tol_nm），
#       mode='id' 依 DEFECTID 配對。回傳結果 dict。"""
#    A, B = _pts_for_compare(doc_a), _pts_for_compare(doc_b)
#    matched = []          # (a, b)
#    used_b = set()
#
#    if mode == 'id':
#        idx = {}
#        for p in B:
#            idx.setdefault(p['id'], []).append(p)
#        for pa in A:
#            cand = idx.get(pa['id'])
#            if cand:
#                pb = cand.pop(0)
#                matched.append((pa, pb)); used_b.add(pb['i'])
#    else:
#        # 以 die 分桶，桶內再用網格雜湊找容差內最近的點
#        buckets = {}
#        for p in B:
#            cell = (p['die'], int(p['x']//max(tol_nm, 1)), int(p['y']//max(tol_nm, 1)))
#            buckets.setdefault(cell, []).append(p)
#        for pa in A:
#            cx, cy = int(pa['x']//max(tol_nm, 1)), int(pa['y']//max(tol_nm, 1))
#            best, bestd = None, None
#            for dx in (-1, 0, 1):
#                for dy in (-1, 0, 1):
#                    for pb in buckets.get((pa['die'], cx+dx, cy+dy), ()):
#                        if pb['i'] in used_b:
#                            continue
#                        d = ((pa['x']-pb['x'])**2 + (pa['y']-pb['y'])**2) ** 0.5
#                        if d <= tol_nm and (bestd is None or d < bestd):
#                            best, bestd = pb, d
#            if best is not None:
#                matched.append((pa, best)); used_b.add(best['i'])
#
#    a_matched = {pa['i'] for pa, _ in matched}
#    removed = [p for p in A if p['i'] not in a_matched]
#    added = [p for p in B if p['i'] not in used_b]
#    reclass = [(pa, pb) for pa, pb in matched if pa['cls'] != pb['cls']]
#    moved = [(pa, pb) for pa, pb in matched
#             if abs(pa['x']-pb['x']) > 1e-6 or abs(pa['y']-pb['y']) > 1e-6]
#
#    # 其他欄位的變化（DSIZE、ROUGHBINNUMBER…）：只比兩邊都有的欄位
#    ca = {c.upper(): i for i, c in enumerate(doc_a.defect_columns)}
#    cb = {c.upper(): i for i, c in enumerate(doc_b.defect_columns)}
#    shared = [c for c in ca if c in cb and c not in _SKIP_FIELDS]
#    changed = []
#    for pa, pb in matched:
#        ra, rb = pa['row'], pb['row']
#        diffs = []
#        for c in shared:
#            ia, ib = ca[c], cb[c]
#            va = ra[ia] if ia < len(ra) else ''
#            vb = rb[ib] if ib < len(rb) else ''
#            if va != vb and not _same_number(va, vb):
#                diffs.append((c, va, vb))
#        if diffs:
#            changed.append((pa, pb, diffs))
#    same = len(matched) - len({id(x) for x in reclass} | {id(x) for x in moved})
#
#    # header 差異
#    ha = dict(doc_a.header_items()); hb = dict(doc_b.header_items())
#    hdr = []
#    for k in sorted(set(ha) | set(hb)):
#        va, vb = ha.get(k), hb.get(k)
#        if va != vb:
#            hdr.append((k, va, vb))
#
#    # class 分佈
#    def dist(pts):
#        d = {}
#        for p in pts:
#            d[p['cls']] = d.get(p['cls'], 0) + 1
#        return d
#    da, db = dist(A), dist(B)
#    classes = sorted(set(da) | set(db),
#                     key=lambda s: (0, int(s)) if s.lstrip('-').isdigit() else (1, s))
#    cls_rows = [(c, da.get(c, 0), db.get(c, 0),
#                 doc_a.class_lookup.get(int(c)) if c.lstrip('-').isdigit() else None)
#                for c in classes]
#
#    # die 分佈（給 wafer 圖用）
#    def dies(pts):
#        d = {}
#        for p in pts:
#            d[p['die']] = d.get(p['die'], 0) + 1
#        return d
#
#    return {
#        'mode': mode, 'tol_nm': tol_nm,
#        'a': {'name': os.path.basename(doc_a.source_path or 'A'),
#              'version': doc_a.version, 'unit': doc_a.unit_info()['coord_unit'],
#              'n': len(A), 'dies': dies(A)},
#        'b': {'name': os.path.basename(doc_b.source_path or 'B'),
#              'version': doc_b.version, 'unit': doc_b.unit_info()['coord_unit'],
#              'n': len(B), 'dies': dies(B)},
#        'matched': len(matched), 'same': same,
#        'added': added, 'removed': removed, 'reclass': reclass, 'moved': moved,
#        'changed': changed, 'shared_fields': shared,
#        'header': hdr, 'classes': cls_rows,
#        'summary_a': [list(r) for r in doc_a._summary_rows],
#        'summary_b': [list(r) for r in doc_b._summary_rows],
#        'summary_cols': doc_a._summary_columns or doc_b._summary_columns,
#        'geom': _wafer_geom(doc_a) or _wafer_geom(doc_b),
#    }
#
#
#def _wafer_geom(doc):
#    """從 header 推出晶圓幾何（與 App 的 wafer map 同一套近似）。
#       回傳 {'rx','ry','ar','notch'}；rx/ry = 晶圓半徑（單位: die 數），
#       ar = pitchY/pitchX（die 真實長寬比）。推不出來時回傳 None。"""
#    def fval(name):
#        for n, v in doc.header_items():
#            if n == name:
#                return [float(x) for x in
#                        re.findall(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', v)]
#        return []
#    try:
#        pit = fval('DiePitch')
#        ss = fval('SampleSize')
#        if len(pit) < 2 or pit[0] <= 0 or pit[1] <= 0 or not ss:
#            return None
#        mm = max(ss)
#        if mm < 10:           # SampleSize 不是 mm 口徑（如 wafer 型號碼）就放棄
#            return None
#        dia = mm * (1000.0 if doc.unit_info()['coord_unit'] == 'µm' else 1e6)
#        rx, ry = (dia / 2) / pit[0], (dia / 2) / pit[1]
#        if not (1 <= rx <= 80 and 1 <= ry <= 80):
#            return None
#        notch = None
#        for n, v in doc.header_items():
#            if n == 'OrientationMarkLocation':
#                notch = v.strip().strip('"').upper() or None
#        return {'rx': rx, 'ry': ry, 'ar': pit[1] / pit[0], 'notch': notch}
#    except (ValueError, ZeroDivisionError):
#        return None
#
#
#
#def diff_rows(res):
#    """把比對結果整理成並排差異列：(狀態集合, A點或None, B點或None, 有變化的欄位)。
#       同一顆 defect 若同時改分類又位移，會合併成一列。"""
#    merged = {}
#    order = []
#    def put(status, pa, pb, fields):
#        key = (id(pa) if pa is not None else None, id(pb) if pb is not None else None)
#        if key in merged:
#            merged[key][0].add(status); merged[key][3].update(fields)
#        else:
#            merged[key] = [{status}, pa, pb, set(fields)]
#            order.append(key)
#    for p in res['removed']:
#        put('removed', p, None, set())
#    for p in res['added']:
#        put('added', None, p, set())
#    for pa, pb in res['reclass']:
#        put('reclass', pa, pb, {'cls'})
#    for pa, pb in res['moved']:
#        f = set()
#        if abs(pa['x']-pb['x']) > 1e-6:
#            f.add('x')
#        if abs(pa['y']-pb['y']) > 1e-6:
#            f.add('y')
#        put('moved', pa, pb, f)
#    detail = {}
#    for pa, pb, diffs in res.get('changed', ()):
#        put('changed', pa, pb, {'other'})
#        detail[(id(pa), id(pb))] = diffs
#    rows = []
#    for key in order:
#        st, pa, pb, fields = merged[key]
#        ref = pa if pa is not None else pb
#        rows.append((st, pa, pb, fields, ref['die'], detail.get(key, [])))
#    rows.sort(key=lambda r: (-r[4][1], r[4][0]))      # 依 die 排，方便一片片看
#    return [(st, pa, pb, f, d) for st, pa, pb, f, _die, d in rows]
#
#
#STATUS_TXT = {'added': '新增', 'removed': '消失', 'reclass': '分類不同',
#              'moved': '座標位移', 'changed': '欄位變更'}
#STATUS_ORDER = ['removed', 'added', 'reclass', 'moved', 'changed']
#
#
#def _esc(s):
#    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
#            .replace('>', '&gt;').replace('"', '&quot;'))
#
#
#HEAT_ZERO = (255, 255, 255)                              # 0
#HEAT_LO1, HEAT_LO2 = (255, 229, 229), (255, 170, 170)    # 低值段
#HEAT_MD1 = (255, 102, 102)                               # 中值段起點
#HEAT_FULL = (255, 0, 0)                                  # >= 上限：正紅
#WAFER_DISC_C = "#565b63"     # 晶圓本體：中灰
#OUTSIDE_C = "#ffffff"        # 晶圓外：純白
#CENTER_DIE_C = "#00ff00"     # 基準晶粒：螢光綠
#
#
#def _mix(c1, c2, t):
#    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
#
#
#def heat_rgb(v, cap):
#    """0=純白 → 淡粉 → 珊瑚粉 → 洋紅 → 正紅(>=cap 截斷)。與 App 同一套。"""
#    if v <= 0:
#        c = HEAT_ZERO
#    else:
#        t = v / max(cap, 1)
#        if t >= 1.0:
#            c = HEAT_FULL
#        elif t <= 0.4:
#            c = _mix(HEAT_LO1, HEAT_LO2, t / 0.4)
#        else:
#            c = _mix(HEAT_MD1, HEAT_FULL, (t - 0.4) / 0.6)
#    return 'rgb(%d,%d,%d)' % c
#
#
#
#def _svg_wafer(dies_a, dies_b, kind, size=26, cap=10, geom=None):
#    """畫一張 die 熱力圖 SVG（與 App 的 Workspace wafer map 同一套視覺）：
#       暗灰圓盤 + 白→正紅漸層（超過 cap 截斷）+ 細黑格線 + 格內數字 +
#       中心 die 綠框 + 右側色階條 + 缺口標記。
#       geom（來自 _wafer_geom）給的話，會像 App 一樣畫出以 die (0,0) 為中心的
#       近似完整晶圓 die 網格（含真實 die 長寬比與 header 指定的缺口方位）。
#       kind='a'/'b' 顯示各自數量；kind='diff' 顯示 B−A（紅=B多 藍=A多）。"""
#    keys = set(dies_a) | set(dies_b)
#    if not keys:
#        return '<p class="muted">no die data</p>'
#    xs = [k[0] for k in keys]; ys = [k[1] for k in keys]
#    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
#
#    # ---- 與 App 相同的近似完整晶圓網格：中心固定在 die (0,0) ----
#    cells = None
#    ar = 1.0
#    notch_pos = 'DOWN'
#    if geom:
#        ar = max(0.25, min(4.0, geom.get('ar') or 1.0))
#        rx, ry = geom['rx'], geom['ry']
#        # 真的有 die 落在推算圓外（座標系不同或 SampleSize 有誤）就撐大半徑
#        need = max(abs(bx0), abs(bx1)) + 0.5
#        if need > rx:
#            rx = need
#        need = max(abs(by0), abs(by1)) + 0.5
#        if need > ry:
#            ry = need
#        cs = set()
#        for i in range(int(-rx) - 1, int(rx) + 2):
#            for j in range(int(-ry) - 1, int(ry) + 2):
#                if (i / rx) ** 2 + (j / ry) ** 2 <= 1.0:
#                    cs.add((i, j))
#        cs |= keys
#        if len(cs) <= 5000:          # 太大就退回只畫有 defect 的 die
#            cells = cs
#        if geom.get('notch') in ('DOWN', 'UP', 'LEFT', 'RIGHT'):
#            notch_pos = geom['notch']
#    if cells is None:
#        cells = set(keys)
#    xs2 = [c[0] for c in cells]; ys2 = [c[1] for c in cells]
#    x0, x1, y0, y1 = min(xs2), max(xs2), min(ys2), max(ys2)
#    ncol, nrow = x1 - x0 + 1, y1 - y0 + 1
#
#    # 格子尺寸自適應：完整晶圓格數多時自動縮小，避免圖爆版
#    size = max(9.0, min(float(size), 720.0 / ncol, 720.0 / (nrow * ar)))
#    sizex, sizey = size, size * ar
#    show_num = min(sizex, sizey) >= 13     # 格子太小就不塞數字（同 App 的行為）
#
#    barw = 46
#    gw, gh = ncol * sizex, nrow * sizey
#    rad = max(gw, gh) / 2 * 1.04           # 與 App 相同的 4% 邊距
#    notch_r = max(4.0, min(sizex, sizey) * 0.30)
#    margin = max(8.0, size * 0.5)
#    # 畫布同時裝得下 die 網格與晶圓圓盤（含四個方位的缺口圓）——不會被裁切
#    half_w = max(gw / 2, rad + notch_r) + margin
#    half_h = max(gh / 2, rad + notch_r) + margin
#    W, H = half_w * 2 + barw, half_h * 2
#    # 圓盤中心 = die (0,0) 的格子中心（KLARF 索引以原點 die 為基準，同 App）
#    ox, oy = half_w - gw / 2, half_h - gh / 2
#    if geom and (x0 <= 0 <= x1) and (y0 <= 0 <= y1):
#        cx = ox + (0 - x0 + 0.5) * sizex
#        cy = oy + (y1 - 0 + 0.5) * sizey
#    else:
#        cx, cy = half_w, half_h
#    # 中心若偏離畫布中心（原點 die 不在網格正中），畫布向外擴到涵蓋整個圓盤
#    ex_l = max(0.0, rad + notch_r + margin - cx)
#    ex_r = max(0.0, cx + rad + notch_r + margin - (W - barw))
#    ex_t = max(0.0, rad + notch_r + margin - cy)
#    ex_b = max(0.0, cy + rad + notch_r + margin - H)
#    ox += ex_l; cx += ex_l
#    oy += ex_t; cy += ex_t
#    W += ex_l + ex_r
#    H += ex_t + ex_b
#    src = dies_a if kind == 'a' else dies_b
#    if kind == 'diff':
#        mx = max([abs(dies_b.get(k, 0)-dies_a.get(k, 0)) for k in keys] or [1])
#    else:
#        mx = cap
#
#    def diverge(d):
#        if d == 0:
#            return '#ffffff'
#        t = min(1.0, abs(d)/max(mx, 1))
#        base = (255, 0, 0) if d > 0 else (20, 55, 150)
#        return 'rgb(%d,%d,%d)' % _mix((255, 255, 255), base, t)
#
#    o = [f'<svg viewBox="0 0 {W:.1f} {H:.1f}" class="wafer">']
#    o.append(f'<rect x="0" y="0" width="{W:.1f}" height="{H:.1f}" fill="{OUTSIDE_C}"/>')
#    o.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rad:.1f}" fill="{WAFER_DISC_C}" '
#             f'stroke="#000000" stroke-width="1"/>')
#    # 方位缺口：依 header 的 OrientationMarkLocation 放在對應邊（同 App）
#    nx, ny = {'DOWN': (cx, cy + rad), 'UP': (cx, cy - rad),
#              'LEFT': (cx - rad, cy), 'RIGHT': (cx + rad, cy)}[notch_pos]
#    o.append(f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="{notch_r:.1f}" '
#             f'fill="#ffffff" stroke="#000000" stroke-width="1"/>')
#    fs = max(6.5, min(sizex, sizey) * 0.36)
#    for (dx, dy) in sorted(cells):
#        px = ox + (dx - x0) * sizex; py = oy + (y1 - dy) * sizey
#        if kind == 'diff':
#            v = dies_b.get((dx, dy), 0) - dies_a.get((dx, dy), 0)
#            fill = diverge(v)
#            txt = ('%+d' % v) if v else '0'
#            dark = abs(v) >= mx*0.55
#        else:
#            v = src.get((dx, dy), 0)
#            fill = heat_rgb(v, mx)
#            txt = str(v)
#            dark = False          # 數字一律純黑
#        tip = f'die ({dx},{dy})  A:{dies_a.get((dx,dy),0)}  B:{dies_b.get((dx,dy),0)}'
#        o.append(f'<rect x="{px:.1f}" y="{py:.1f}" width="{sizex:.1f}" height="{sizey:.1f}" '
#                 f'fill="{fill}" stroke="#000000" stroke-width="1">'
#                 f'<title>{_esc(tip)}</title></rect>')
#        if show_num:
#            o.append(f'<text x="{px+sizex/2:.1f}" y="{py+sizey/2+fs*0.36:.1f}" font-size="{fs:.1f}" '
#                     f'text-anchor="middle" fill="{"#ffffff" if dark else "#000000"}" '
#                     f'font-family="Segoe UI,system-ui,sans-serif">{txt}</text>')
#        if (dx, dy) == (0, 0):
#            o.append(f'<rect x="{px+1:.1f}" y="{py+1:.1f}" width="{sizex-2:.1f}" height="{sizey-2:.1f}" '
#                     f'fill="none" stroke="{CENTER_DIE_C}" stroke-width="2"/>')
#    # 右側色階條（cy 可能偏離畫布中心，夾住避免超出畫布）
#    bx = W - barw + 8; bh = min(gh, rad*1.6); bw = 13
#    by = max(6.0, min(H - bh - 6.0, cy - bh/2))
#    gid = 'g_' + kind
#    if kind == 'diff':
#        stops = ('<stop offset="0%" stop-color="rgb(255,0,0)"/>'
#                 '<stop offset="50%" stop-color="#ffffff"/>'
#                 '<stop offset="100%" stop-color="rgb(20,55,150)"/>')
#        labs = [(by, '+%d' % mx), (by+bh/2, '0'), (by+bh, '-%d' % mx)]
#    else:
#        # 分段漸層：上=cap(正紅) → 洋紅 → 珊瑚粉 → 下=0(白)
#        stops = ('<stop offset="0%" stop-color="rgb(255,0,0)"/>'
#                 '<stop offset="60%" stop-color="rgb(255,102,102)"/>'
#                 '<stop offset="60%" stop-color="rgb(255,170,170)"/>'
#                 '<stop offset="100%" stop-color="#ffffff"/>')
#        labs = [(by, '%d+' % mx), (by+bh/2, '%g' % (mx/2)), (by+bh, '0')]
#    o.append(f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">{stops}'
#             f'</linearGradient></defs>')
#    o.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="url(#{gid})" '
#             f'stroke="#000000" stroke-width="0.8"/>')
#    for ly, lab in labs:
#        o.append(f'<text x="{bx+bw+3}" y="{ly+3.5:.1f}" font-size="9" fill="#1f2733" '
#                 f'font-family="Segoe UI,system-ui,sans-serif">{lab}</text>')
#    o.append('</svg>')
#    return ''.join(o)
#
#
#_HTML_CSS = """
#:root{--ink:#1f2733;--sub:#5b6672;--line:#e6e8ec;--bg:#f6f7f9;--acc:#2f6feb;--dan:#e0533d;--ok:#12a150}
#*{box-sizing:border-box}
#body{margin:0;padding:28px;background:var(--bg);color:var(--ink);
# font:14px/1.55 "Segoe UI",system-ui,-apple-system,"Noto Sans TC",sans-serif}
#h1{font-size:21px;margin:0 0 4px} h2{font-size:15px;margin:26px 0 10px}
#.muted{color:var(--sub);font-size:12.5px}
#.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:14px}
#.files{display:flex;gap:14px;flex-wrap:wrap}
#.files div{flex:1;min-width:230px}
#.tag{display:inline-block;padding:1px 7px;border-radius:9px;background:#eef2f8;color:var(--sub);font-size:11.5px}
#.kpis{display:flex;gap:10px;flex-wrap:wrap;margin:2px 0 4px}
#.kpi{flex:1;min-width:120px;background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px 14px}
#.kpi .n{font-size:23px;font-weight:700;line-height:1.1}
#.kpi .l{font-size:12px;color:var(--sub);margin-top:2px}
#.kpi .n{color:var(--ink)}
#table{border-collapse:collapse;width:100%;font-size:13px}
#th,td{border-bottom:1px solid var(--line);padding:6px 9px;text-align:left;white-space:nowrap}
#th{background:#fafbfc;color:var(--sub);font-weight:600;position:sticky;top:0}
#td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
#.pos{color:var(--ok)} .neg{color:var(--dan)}
#.maps{display:flex;gap:18px;flex-wrap:wrap}
#.maps figure{margin:0;text-align:center}
#.maps figcaption{font-size:12px;color:var(--sub);margin-top:6px}
#.wafer{width:340px;height:auto;background:#fff;border:1px solid var(--line);border-radius:8px}
#.scroll{max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:8px}
#.legend{font-size:12px;color:var(--sub);margin-top:8px}
#.scroll.big{max-height:620px}
##dt th.ha,#dt th.hb{background:#f1f3f6;color:var(--ink);text-align:center;
# font-weight:700;letter-spacing:.02em}
##dt td.sep,#dt th.sep{border-left:2px solid #cfd6e0;padding:0;width:2px;background:#f4f6f9}
##dt td.empty{color:#c3cad4}
##dt td.oth,#dt th.oth{text-align:left;font-size:12px;color:var(--sub);white-space:normal;
# max-width:190px}
##dt td.chg{font-weight:700;text-decoration:underline;text-underline-offset:3px;
# text-decoration-thickness:1.5px;text-decoration-color:#9aa4b2}
##dt tbody tr:nth-child(even){background:#fcfcfd}
##dt tbody tr:hover{background:#f4f6f9}
#.pill{display:inline-block;padding:0 7px;border:1px solid #c8cfd9;border-radius:3px;
# font-size:11px;font-weight:600;color:var(--sub);background:#fff;margin-right:3px;white-space:nowrap}
#.filters{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
#.fb{border:1px solid var(--line);background:#fff;border-radius:16px;padding:5px 12px;
# font:inherit;font-size:12.5px;color:var(--sub);cursor:pointer}
#.fb:hover{background:#f2f5f9}
#.fb.on{background:var(--acc);border-color:var(--acc);color:#fff;font-weight:600}
##q{border:1px solid var(--line);border-radius:16px;padding:5px 12px;
# font:inherit;font-size:12.5px;min-width:200px}
#.filters select{border:1px solid var(--line);border-radius:16px;padding:5px 10px;
# font:inherit;font-size:12.5px;background:#fff;color:var(--sub);max-width:170px}
#.cnt{margin-left:auto;font-size:12.5px;color:var(--sub);white-space:nowrap}
#.pager{display:flex;gap:6px;align-items:center;margin-top:10px;font-size:12.5px;color:var(--sub)}
#.pager button{border:1px solid var(--line);background:#fff;border-radius:14px;
# padding:4px 12px;font:inherit;font-size:12.5px;color:var(--ink);cursor:pointer}
#.pager button:hover:not(:disabled){background:#f2f5f9}
#.pager button:disabled{color:#c3cad4;cursor:default}
#.pager select{border:1px solid var(--line);border-radius:14px;padding:4px 8px;
# font:inherit;font-size:12.5px;margin-left:auto}
##pinfo{padding:0 8px}
#.sw{display:inline-block;width:11px;height:11px;border-radius:3px;vertical-align:-1px;margin:0 4px 0 12px}
#"""
#
#
#
#_HTML_JS = """<script>
#(function(){
#  var DATA = JSON.parse(document.getElementById('diffdata').textContent);
#  var TXT  = {added:'新增', removed:'消失', reclass:'分類不同',
#              moved:'座標位移', changed:'欄位變更'};
#  var tb    = document.getElementById('tb');
#  var q     = document.getElementById('q');
#  var cnt   = document.getElementById('cnt');
#  var fcls  = document.getElementById('fcls');
#  var fdie  = document.getElementById('fdie');
#  var ffld  = document.getElementById('ffld');
#  var pinfo = document.getElementById('pinfo');
#  var psize = document.getElementById('psize');
#  var cur = 'all', page = 0, size = 200, view = [], timer = null;
#
#  // 每列先算好搜尋字串，之後打字就不用重組
#  DATA.forEach(function(d){
#    d.q = ((d.a ? d.a[0] : '') + ' ' + (d.b ? d.b[0] : '') + ' ' +
#           d.d + ' ' + d.c.join(' ') + ' ' + d.f.join(' ')).toLowerCase();
#  });
#
#  function esc(v){
#    return String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
#  }
#  var KEYS = ['id','xi','yi','x','y','cls'];
#  function cells(arr, marks){
#    if (!arr) return '<td class="num empty">—</td>'.repeat(6) + '<td class="oth"></td>';
#    var out = '';
#    for (var i = 0; i < 6; i++){
#      out += '<td class="num' + (marks.indexOf(KEYS[i]) >= 0 ? ' chg' : '') + '">'
#           + esc(arr[i]) + '</td>';
#    }
#    return out + '<td class="oth' + (arr[6] ? ' chg' : '') + '">' + esc(arr[6]) + '</td>';
#  }
#  function render(){
#    var lo = size ? page * size : 0;
#    var hi = size ? Math.min(lo + size, view.length) : view.length;
#    var html = [];
#    for (var i = lo; i < hi; i++){
#      var d = view[i];
#      var pill = d.s.map(function(x){
#        return '<span class="pill ' + x + '">' + TXT[x] + '</span>'; }).join(' ');
#      html.push('<tr class="' + d.s[0] + '"><td>' + pill + '</td>'
#                + cells(d.a, d.m) + '<td class="sep"></td>' + cells(d.b, d.m) + '</tr>');
#    }
#    tb.innerHTML = html.join('') ||
#      '<tr><td colspan="16" class="muted">沒有符合條件的差異。</td></tr>';
#    var pages = size ? Math.max(1, Math.ceil(view.length / size)) : 1;
#    if (pinfo) pinfo.textContent = size
#      ? ('第 ' + (view.length ? page + 1 : 0) + ' / ' + pages + ' 頁'
#         + '（第 ' + (view.length ? lo + 1 : 0) + '–' + hi + ' 列）')
#      : ('全部 ' + view.length + ' 列');
#    ['pfirst','pprev'].forEach(function(id){
#      document.getElementById(id).disabled = (page <= 0 || !size); });
#    ['pnext','plast'].forEach(function(id){
#      document.getElementById(id).disabled = (page >= pages - 1 || !size); });
#  }
#  function apply(reset){
#    var t  = (q.value || '').trim().toLowerCase();
#    var vc = fcls ? fcls.value : '';
#    var vd = fdie ? fdie.value : '';
#    var vf = ffld ? ffld.value : '';
#    view = DATA.filter(function(d){
#      return (cur === 'all' || d.s.indexOf(cur) >= 0)
#          && (!vc || d.c.indexOf(vc) >= 0)
#          && (!vd || d.d === vd)
#          && (!vf || d.f.indexOf(vf) >= 0)
#          && (!t  || d.q.indexOf(t) >= 0);
#    });
#    if (reset !== false) page = 0;
#    if (cnt) cnt.textContent = '顯示 ' + view.length + ' / ' + DATA.length + ' 列';
#    render();
#  }
#
#  document.querySelectorAll('.fb').forEach(function(b){
#    b.onclick = function(){
#      document.querySelectorAll('.fb').forEach(function(x){ x.classList.remove('on'); });
#      b.classList.add('on'); cur = b.getAttribute('data-f'); apply();
#    };
#  });
#  [fcls, fdie, ffld].forEach(function(s){ if (s) s.onchange = function(){ apply(); }; });
#  q.addEventListener('input', function(){
#    clearTimeout(timer); timer = setTimeout(apply, 120);
#  });
#  psize.onchange = function(){ size = parseInt(psize.value, 10) || 0; page = 0; render(); };
#  document.getElementById('pfirst').onclick = function(){ page = 0; render(); };
#  document.getElementById('pprev').onclick  = function(){ if (page > 0) { page--; render(); } };
#  document.getElementById('pnext').onclick  = function(){
#    var pages = size ? Math.ceil(view.length / size) : 1;
#    if (page < pages - 1) { page++; render(); } };
#  document.getElementById('plast').onclick  = function(){
#    page = size ? Math.max(0, Math.ceil(view.length / size) - 1) : 0; render(); };
#  apply();
#})();
#</script>"""
#
#
#def _rows_table(rows, cols, unit, limit=800):
#    if not rows:
#        return '<p class="muted">（無）</p>'
#    head = ''.join(f'<th class="num">{_esc(c)}</th>' for c in cols)
#    body = []
#    for r in rows[:limit]:
#        body.append('<tr>' + ''.join(f'<td class="num">{_esc(v)}</td>' for v in r) + '</tr>')
#    more = ('' if len(rows) <= limit else
#            f'<p class="muted">僅顯示前 {limit} 筆，共 {len(rows)} 筆。</p>')
#    return (f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
#            f'<tbody>{"".join(body)}</tbody></table></div>{more}')
#
#
#def compare_html(res):
#    """把 compare() 的結果產生成一份自包含的 HTML 報告。"""
#    import datetime
#    a, b = res['a'], res['b']
#    fu = 1000.0 if a['unit'] == 'µm' else 1.0     # nm → 顯示單位
#    du = a['unit']
#
#    def fmt(v):
#        return f"{v/fu:.3f}" if du == 'µm' else f"{v:.0f}"
#
#    kpi = f"""<div class="kpis">
#      <div class="kpi"><div class="n">{res['matched']}</div><div class="l">配對成功</div></div>
#      <div class="kpi add"><div class="n">+{len(res['added'])}</div><div class="l">只在 B（新增）</div></div>
#      <div class="kpi rem"><div class="n">-{len(res['removed'])}</div><div class="l">只在 A（消失）</div></div>
#      <div class="kpi rc"><div class="n">{len(res['reclass'])}</div><div class="l">分類不同</div></div>
#      <div class="kpi"><div class="n">{len(res['moved'])}</div><div class="l">座標位移</div></div>
#      <div class="kpi"><div class="n">{len(res.get('changed', ()))}</div><div class="l">其他欄位變更</div></div>
#    </div>"""
#
#    hdr = '<p class="muted">兩份檔案的 header 欄位完全相同。</p>'
#    if res['header']:
#        rows = ''.join(
#            f'<tr><td>{_esc(k)}</td><td>{_esc(va if va is not None else "—")}</td>'
#            f'<td>{_esc(vb if vb is not None else "—")}</td></tr>'
#            for k, va, vb in res['header'])
#        hdr = (f'<table><thead><tr><th>欄位</th><th>A</th><th>B</th></tr></thead>'
#               f'<tbody>{rows}</tbody></table>')
#
#    crows = []
#    for c, na, nb, name in res['classes']:
#        d = nb - na
#        cls = 'pos' if d > 0 else ('neg' if d < 0 else 'muted')
#        crows.append(f'<tr><td>{_esc(c)}</td><td>{_esc(name or "")}</td>'
#                     f'<td class="num">{na}</td><td class="num">{nb}</td>'
#                     f'<td class="num {cls}">{d:+d}</td></tr>')
#    cls_tbl = (f'<table><thead><tr><th>Class</th><th>名稱</th><th class="num">A</th>'
#               f'<th class="num">B</th><th class="num">Δ</th></tr></thead>'
#               f'<tbody>{"".join(crows)}</tbody></table>')
#
#    # ---- 並排差異表：資料存成 JSON，由瀏覽器只渲染當前頁 ----
#    # （整份差異都在檔案裡，不做任何截斷；但一次只把一頁放進 DOM，
#    #   否則數萬列的表格光是解析就要十幾秒）
#    import json as _json
#    drows = diff_rows(res)
#    data = []
#    for st, pa, pb, fields, chg in drows:
#        sts = sorted(st, key=STATUS_ORDER.index)
#        ref = pa if pa is not None else pb
#
#        def side(p, which):
#            if p is None:
#                return None
#            oth = ('  '.join('%s %s' % (c, (va if which == 0 else vb))
#                             for c, va, vb in chg)) if chg else ''
#            return [p['id'], str(p['die'][0]), str(p['die'][1]),
#                    fmt(p['x']), fmt(p['y']), p['cls'], oth]
#
#        data.append({
#            's': sts,
#            'a': side(pa, 0), 'b': side(pb, 1),
#            'm': sorted(fields),
#            'd': '%d,%d' % ref['die'],
#            'c': sorted({p['cls'] for p in (pa, pb) if p is not None}),
#            'f': sorted({c for c, _x, _y in chg}),
#        })
#    payload = _json.dumps(data, separators=(',', ':'), ensure_ascii=False) \
#                   .replace('</', '<\\/')
#
#    colhead = (''.join('<th class="num">%s</th>' % c for c in
#                       ('DEFECTID', 'XINDEX', 'YINDEX', 'XREL (%s)' % du,
#                        'YREL (%s)' % du, 'CLASS'))
#               + '<th class="oth">其他欄位</th>')
#    head = ('<tr><th rowspan="2">狀態</th>'
#            '<th colspan="7" class="ha">A — %s</th>' % _esc(a['name']) +
#            '<th rowspan="2" class="sep"></th>'
#            '<th colspan="7" class="hb">B — %s</th></tr>' % _esc(b['name']) +
#            '<tr>' + colhead + colhead + '</tr>')
#
#    fbtn = ('<button class="fb on" data-f="all">全部 (%d)</button>' % len(drows) +
#            ''.join('<button class="fb" data-f="%s">%s (%d)</button>'
#                    % (k, STATUS_TXT[k], len(res.get(k, ())))
#                    for k in ('added', 'removed', 'reclass', 'moved', 'changed')))
#
#    all_cls = sorted({c for d in data for c in d['c']},
#                     key=lambda v: (0, int(v)) if v.lstrip('-').isdigit() else (1, v))
#    all_die = sorted({d['d'] for d in data},
#                     key=lambda t: (int(t.split(',')[1]), int(t.split(',')[0])))
#    all_fld = sorted({f for d in data for f in d['f']})
#
#    def sel(sid, label, opts):
#        o = ''.join('<option value="%s">%s</option>' % (_esc(v), _esc(v)) for v in opts)
#        return ('<select id="%s"><option value="">%s</option>%s</select>'
#                % (sid, _esc(label), o))
#
#    drops = sel('fcls', '所有 class', all_cls) + sel('fdie', '所有 die', all_die)
#    if all_fld:
#        drops += sel('ffld', '所有變更欄位', all_fld)
#
#    pager = ('<div class="pager"><button id="pfirst">&laquo;</button>'
#             '<button id="pprev">上一頁</button><span id="pinfo"></span>'
#             '<button id="pnext">下一頁</button><button id="plast">&raquo;</button>'
#             '<select id="psize"><option>200</option><option>500</option>'
#             '<option>1000</option><option value="0">全部顯示</option></select></div>')
#
#    diff_tbl = ('<div class="filters">' + fbtn + drops +
#                '<input id="q" placeholder="搜尋 DEFECTID / die / class…">'
#                '<span id="cnt" class="cnt"></span></div>'
#                '<div class="scroll big"><table id="dt"><thead>' + head +
#                '</thead><tbody id="tb"></tbody></table></div>' + pager +
#                '<script id="diffdata" type="application/json">' + payload + '</script>')
#
#    srows = ''
#    if res['summary_cols']:
#        head = ''.join(f'<th class="num">{_esc(c)}</th>' for c in res['summary_cols'])
#        def blk(tag, rs):
#            return ''.join('<tr><td>' + tag + '</td>' +
#                           ''.join(f'<td class="num">{_esc(v)}</td>' for v in r) + '</tr>'
#                           for r in rs)
#        srows = (f'<table><thead><tr><th>檔案</th>{head}</tr></thead><tbody>'
#                 f'{blk("A", res["summary_a"])}{blk("B", res["summary_b"])}</tbody></table>')
#
#    mode_txt = ('依 DEFECTID 配對' if res['mode'] == 'id'
#                else f'依 die + 座標配對（容差 {res["tol_nm"]/fu:g} {du}）')
#    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
#    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
#<title>KLARF Compare — {_esc(a['name'])} vs {_esc(b['name'])}</title>
#<style>{_HTML_CSS}</style></head><body>
#<h1>KLARF 比對報告</h1>
#<p class="muted">{_esc(mode_txt)} · 產生於 {ts} · KLIP</p>
#
#<div class="card"><div class="files">
#  <div><span class="tag">A</span> <b>{_esc(a['name'])}</b><br>
#    <span class="muted">KLARF {_esc(a['version'])} · 座標 {_esc(a['unit'])} · {a['n']} 筆 defect</span></div>
#  <div><span class="tag">B</span> <b>{_esc(b['name'])}</b><br>
#    <span class="muted">KLARF {_esc(b['version'])} · 座標 {_esc(b['unit'])} · {b['n']} 筆 defect</span></div>
#</div></div>
#
#{kpi}
#
#<div class="card"><h2 style="margin-top:0">Wafer 分佈</h2><div class="maps">
#  <figure>{_svg_wafer(a['dies'], b['dies'], 'a', geom=res.get('geom'))}<figcaption>A：{a['n']} 筆</figcaption></figure>
#  <figure>{_svg_wafer(a['dies'], b['dies'], 'b', geom=res.get('geom'))}<figcaption>B：{b['n']} 筆</figcaption></figure>
#  <figure>{_svg_wafer(a['dies'], b['dies'], 'diff', geom=res.get('geom'))}<figcaption>差異（B − A）</figcaption></figure>
#</div>
#<div class="legend">A / B 圖採白→深紅漸層，色階上限 10（≥10 一律最深紅，避免極端值壓縮低值的解析度）；
#  格內數字為該 die 的 defect 數，<span class="sw" style="background:#12b83a"></span>綠框為中心 die (0,0)。
#  差異圖：<span class="sw" style="background:#8f0f06"></span>B 較多
#  <span class="sw" style="background:#143796"></span>A 較多
#  <span class="sw" style="background:#ffffff;border:1px solid #ccc"></span>相同。</div>
#</div>
#
#<div class="card"><h2 style="margin-top:0">逐筆差異　（左 = A　｜　右 = B）</h2>{diff_tbl}</div>
#
#<div class="card"><h2 style="margin-top:0">Header 差異</h2>{hdr}</div>
#<div class="card"><h2 style="margin-top:0">Class 分佈</h2>{cls_tbl}</div>
#<div class="card"><h2 style="margin-top:0">SummaryList</h2>{srows or '<p class="muted">（無）</p>'}</div>
#
#{_HTML_JS}
#</body></html>"""
#
#F 48bc252f2f4e778f53ebccfd524869e8253b7a6a 168 adept/core/ingest/tiff_index.py
## Vendored into ADEPT on 2026-07-27.
## Source project: KLIP — file: klarf_tif_probe.py (dependency-free TIFF IFD
## walker; only the pure-struct structural reader is vendored, not the CLI /
## probe / report code).
## Adaptations:
##   - added `from __future__ import annotations` (ADEPT convention)
##   - extracted read_tiff_pages() + helpers (TYPE_SIZE / COMPRESSION /
##     PHOTOMETRIC / TAGS / _read_values / _page_geom) verbatim
##   - added n_pages(path) built on read_tiff_pages (still dependency-free)
##   - added read_page(path, page_index) -> np.ndarray via LAZY
##     `import tifffile` inside the function (pixel decode only there)
##   - Chinese comments kept verbatim.
#"""TIFF 結構索引：只讀 IFD（不解碼像素），純標準函式庫。
#
#支援 classic TIFF 與 BigTIFF、兩種 byte order。像素解碼（read_page）
#另以 lazy import 的 tifffile 完成。
#"""
#from __future__ import annotations
#
#import os
#import struct
#
#
## ---------------------------------------------------------------- TIFF 走訪
## 只讀 IFD 結構（不解碼像素），純標準函式庫。支援 classic TIFF 與 BigTIFF、
## 兩種 byte order。
#
#TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4,
#             10: 8, 11: 4, 12: 8, 13: 4, 16: 8, 17: 8, 18: 8}
#
#COMPRESSION = {1: "none", 2: "CCITT-RLE", 3: "CCITT-G3", 4: "CCITT-G4",
#               5: "LZW", 6: "old-JPEG", 7: "JPEG", 8: "deflate",
#               32773: "PackBits", 32946: "deflate"}
#
#PHOTOMETRIC = {0: "white-is-zero", 1: "black-is-zero", 2: "RGB",
#               3: "palette", 4: "mask", 5: "CMYK", 6: "YCbCr"}
#
#TAGS = {254: "subfile", 256: "width", 257: "height", 258: "bits",
#        259: "compression", 262: "photometric", 270: "description",
#        273: "strip_offsets", 277: "spp", 279: "strip_bytes",
#        297: "page_number", 305: "software", 306: "datetime",
#        322: "tile_w", 323: "tile_h", 324: "tile_offsets", 325: "tile_bytes"}
#
#
#def _read_values(f, en, vtype, count, raw, big):
#    """把 IFD entry 的 value/offset 解成 python 值 list。"""
#    size = TYPE_SIZE.get(vtype)
#    if size is None:
#        return None
#    total = size * count
#    inline = 8 if big else 4
#    if total <= inline:
#        data = raw[:total]
#    else:
#        off = struct.unpack(en + ('Q' if big else 'I'), raw)[0]
#        pos = f.tell()
#        f.seek(off)
#        data = f.read(total)
#        f.seek(pos)
#        if len(data) < total:
#            return None
#    if vtype == 2:                        # ASCII
#        return [data.split(b'\x00')[0].decode('latin-1', 'replace')]
#    fmt = {1: 'B', 3: 'H', 4: 'I', 6: 'b', 7: 'B', 8: 'h', 9: 'i',
#           11: 'f', 12: 'd', 13: 'I', 16: 'Q', 17: 'q'}.get(vtype)
#    if fmt is None:
#        if vtype in (5, 10):              # rational
#            f2 = 'I' if vtype == 5 else 'i'
#            vals = struct.unpack(en + f2 * (count * 2), data)
#            return [vals[i] / vals[i + 1] if vals[i + 1] else 0.0
#                    for i in range(0, count * 2, 2)]
#        return None
#    return list(struct.unpack(en + fmt * count, data))
#
#
#def read_tiff_pages(path):
#    """回傳 (pages, info)。pages = [dict,...]（每頁一筆），info = 檔案層資訊。"""
#    pages = []
#    with open(path, 'rb') as f:
#        head = f.read(8)
#        if len(head) < 8:
#            raise ValueError("File too short to be a TIFF.")
#        if head[:2] == b'II':
#            en = '<'
#        elif head[:2] == b'MM':
#            en = '>'
#        else:
#            raise ValueError("Not a TIFF (missing II/MM byte-order mark).")
#        magic = struct.unpack(en + 'H', head[2:4])[0]
#        big = (magic == 43)
#        if magic == 42:
#            next_ifd = struct.unpack(en + 'I', head[4:8])[0]
#        elif big:
#            off_size, zero = struct.unpack(en + 'HH', head[4:8])
#            if off_size != 8 or zero != 0:
#                raise ValueError("Malformed BigTIFF header.")
#            next_ifd = struct.unpack(en + 'Q', f.read(8))[0]
#        else:
#            raise ValueError(f"Unknown TIFF magic {magic} (expected 42 or 43).")
#
#        seen = set()
#        while next_ifd:
#            if next_ifd in seen or len(pages) > 100000:
#                raise ValueError("IFD chain loops — corrupt TIFF.")
#            seen.add(next_ifd)
#            f.seek(next_ifd)
#            n = struct.unpack(en + ('Q' if big else 'H'),
#                              f.read(8 if big else 2))[0]
#            page = {"index": len(pages), "ifd_offset": next_ifd}
#            esize = 20 if big else 12
#            entries = f.read(esize * n)
#            for k in range(n):
#                e = entries[k * esize:(k + 1) * esize]
#                tag, vtype = struct.unpack(en + 'HH', e[:4])
#                if big:
#                    count = struct.unpack(en + 'Q', e[4:12])[0]
#                    raw = e[12:20]
#                else:
#                    count = struct.unpack(en + 'I', e[4:8])[0]
#                    raw = e[8:12]
#                name = TAGS.get(tag)
#                if name is None:
#                    continue
#                vals = _read_values(f, en, vtype, count, raw, big)
#                if vals is None:
#                    continue
#                page[name] = vals[0] if len(vals) == 1 else vals
#            b = page.get("strip_bytes", page.get("tile_bytes", 0))
#            page["data_bytes"] = sum(b) if isinstance(b, list) else b
#            pages.append(page)
#            next_ifd = struct.unpack(en + ('Q' if big else 'I'),
#                                     f.read(8 if big else 4))[0]
#
#    info = {"byte_order": "little-endian (II)" if en == '<' else "big-endian (MM)",
#            "bigtiff": big, "n_pages": len(pages),
#            "file_bytes": os.path.getsize(path)}
#    return pages, info
#
#
#def _page_geom(p):
#    bits = p.get("bits", "?")
#    if isinstance(bits, list):
#        bits = "/".join(str(b) for b in bits)
#    return (f'{p.get("width", "?")}x{p.get("height", "?")} '
#            f'{bits}-bit {COMPRESSION.get(p.get("compression", 1), "compression?")} '
#            f'{PHOTOMETRIC.get(p.get("photometric", -1), "")}'.strip())
#
#
## ------------------------------------------------------- ADEPT additions
#
#def n_pages(path) -> int:
#    """回傳多頁 TIFF 的頁數（純 IFD 走訪，不解碼像素、不需第三方套件）。"""
#    _pages, info = read_tiff_pages(path)
#    return info["n_pages"]
#
#
#def read_page(path, page_index):
#    """解碼並回傳第 page_index（0-based）頁的像素 (np.ndarray)。
#
#    像素解碼交給 tifffile（lazy import：只有真的要讀像素才需要它）。
#    """
#    import tifffile  # lazy: pixel decode only; structural code above stays pure-stdlib
#    with tifffile.TiffFile(path) as tf:
#        if page_index < 0 or page_index >= len(tf.pages):
#            raise IndexError(
#                f"TIFF page {page_index} out of range (0..{len(tf.pages) - 1})")
#        return tf.pages[page_index].asarray()
#
#F d138a400e6717b57b9b19187af462d55b6a95100 62 adept/core/pipeline/__init__.py
## ADEPT pipeline engine — authored 2026-07-28 (M1).
#"""adept.core.pipeline — Context / Step / Recipe / 表達式 / 執行引擎。
#
#單一匯入點：steps、UI、CLI 一律 ``from adept.core.pipeline import ...``。
#"""
#from __future__ import annotations
#
#from .context import Context, ContextError
#from .step import (
#    CATEGORY_ADC,
#    CATEGORY_ALGO,
#    CATEGORY_IMAGE,
#    ParamError,
#    ParamSpec,
#    REGISTRY,
#    Step,
#    StepError,
#    get_step,
#    list_steps,
#    register_step,
#)
#from .expression import Expression, ExpressionError, parse_expression
#from .recipe import (
#    Issue,
#    Recipe,
#    RecipeError,
#    RecipeNode,
#    ScoreSpec,
#    execution_order,
#    validate,
#)
#from .engine import (
#    DefectResult,
#    StepTrace,
#    image_segment_signature,
#    result_to_json_dict,
#    run_dataset,
#    run_defect,
#    run_defect_cached,
#)
#from .cache import StageCache
#from .batch import run_batch
#
#__all__ = [
#    # context
#    "Context", "ContextError",
#    # step
#    "Step", "ParamSpec", "ParamError", "StepError",
#    "register_step", "get_step", "list_steps", "REGISTRY",
#    "CATEGORY_IMAGE", "CATEGORY_ALGO", "CATEGORY_ADC",
#    # recipe
#    "Recipe", "RecipeNode", "ScoreSpec", "Issue",
#    "validate", "execution_order", "RecipeError",
#    # expression
#    "parse_expression", "Expression", "ExpressionError",
#    # engine
#    "run_defect", "run_dataset", "DefectResult", "StepTrace",
#    "result_to_json_dict",
#    # M2：checkpoint 快取與平行批次
#    "run_defect_cached", "image_segment_signature", "StageCache", "run_batch",
#]
#
#F f277b6b3e5e65ce8027da01648a0d42d44a64905 220 adept/core/pipeline/batch.py
## ADEPT parallel batch engine — authored 2026-07-28 (M2).
#"""ProcessPool 平行批次（MMH 模式）：整個 lot 多進程跑完。
#
#設計要點：
#- worker 初始化（:func:`_init_worker`，TOP-LEVEL、picklable）只做一次：
#  import 卡片庫（registry 註冊）、由 JSON dict 重建 Recipe、建 StageCache，
#  存進模組全域 ``_WORKER`` —— 之後每顆 defect 只傳 DefectItem（純 dataclass，
#  pickle 乾淨；不帶 KlarfDoc）。
#- 單顆爆 = 該顆 FAIL dict，不殺整批（run_defect / run_defect_cached 永不
#  raise；worker 層再包一層 try/except 保險）。
#- 結果一律回「原始 item 順序」（as_completed 亂序 → index map 排回）。
#- ``workers <= 1`` → 同進程循序跑（無 pool；語意與平行路徑相同，
#  cache_dir 有給就照用）。
#"""
#from __future__ import annotations
#
#import hashlib
#import multiprocessing as _mp
#import os
#import sys
#import threading
#from concurrent.futures import ProcessPoolExecutor, as_completed
#from typing import Any, Callable, Dict, List, Optional
#
#from .cache import StageCache, dataset_token
#from .engine import result_to_json_dict, run_defect, run_defect_cached
#from .recipe import Recipe
#
#__all__ = ["run_batch", "pin_cv2_deterministic"]
#
## adept/core/pipeline/batch.py → 上四層 = repo root（spawn 模式 sys.path 保險）
#_REPO_ROOT = os.path.abspath(
#    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
#
## worker 進程的全域狀態（initializer 填入；每個 worker 各自一份）
#_WORKER: Dict[str, Any] = {}
#
#
#def pin_cv2_deterministic() -> None:
#    """把 cv2 調成 bit-reproducible 模式（worker 一律套用；parent 想跟
#    worker 位元級一致時也可呼叫）。
#
#    - ``setNumThreads(1)``：N workers × cv2 threads 會超額訂閱，pool 內
#      本來就該單執行緒。
#    - ``ipp.setUseIPP(False)``：Intel IPP 的 Sobel / filter kernel 會依
#      buffer 位址（對齊）選不同 SIMD 路徑，同一張圖兩次重算可能差在
#      1e-8 級 —— 關掉 IPP 後同輸入必同輸出（「快取重放 = 全程重算」
#      的位元級驗收靠這個）。
#    """
#    try:
#        import cv2
#    except Exception:  # pragma: no cover — repo 必裝 cv2；防禦性而已
#        return
#    try:
#        cv2.setNumThreads(1)
#    except Exception:
#        pass
#    try:
#        cv2.ipp.setUseIPP(False)
#    except Exception:
#        pass
#
#
#def _init_worker(recipe_json: Dict[str, Any], kind: str,
#                 cache_dir: Optional[str], token: str,
#                 repo_root: Optional[str] = None) -> None:
#    """ProcessPool worker 初始化（TOP-LEVEL：spawn/fork 皆可 pickle）。"""
#    if repo_root and repo_root not in sys.path:
#        sys.path.insert(0, repo_root)  # spawn 模式下確保 adept 找得到
#    pin_cv2_deterministic()
#    import adept.core.steps  # noqa: F401 — 觸發卡片註冊（fork 模式重複 import 無害）
#    _WORKER["recipe"] = Recipe.from_json_dict(recipe_json)
#    _WORKER["kind"] = str(kind)
#    _WORKER["cache"] = StageCache(str(cache_dir)) if cache_dir else None
#    _WORKER["token"] = str(token)
#
#
#def _run_one(item: Any) -> Dict[str, Any]:
#    """worker 執行一顆 defect（TOP-LEVEL picklable）→ JSON-safe dict。"""
#    recipe: Recipe = _WORKER["recipe"]
#    kind: str = _WORKER["kind"]
#    cache: Optional[StageCache] = _WORKER["cache"]
#    if cache is not None:
#        r = run_defect_cached(recipe, item, kind, cache, _WORKER["token"])
#    else:
#        r = run_defect(recipe, item, kind)
#    return result_to_json_dict(r)
#
#
#def _fail_dict(item: Any, err: BaseException) -> Dict[str, Any]:
#    """worker 層意外（pickle 失敗、worker 被殺…）→ 單顆 FAIL dict。"""
#    return {
#        "defect_id": str(getattr(item, "defect_id", "")),
#        "ok": False,
#        "error": f"{type(err).__name__}: {err}",
#        "features": {},
#        "score": None,
#        "bin": None,
#        "traces": [],
#    }
#
#
#def _dataset_token_for(dataset: Any) -> str:
#    """由 Dataset 推 lot token：有 KLARF 就用檔案 stat（重產 lot 自動失效）；
#    folder / 無 KLARF 模式退化為各 item 影像來源（路徑+mtime+size）的 sha1。"""
#    doc = getattr(dataset, "klarf", None)
#    src = getattr(doc, "source_path", None) if doc is not None else None
#    if src and os.path.exists(str(src)):
#        return dataset_token(src)
#    h = hashlib.sha1()
#    h.update(str(getattr(dataset, "kind", "")).encode("utf-8"))
#    for item in getattr(dataset, "items", []) or []:
#        images = getattr(item, "images", {}) or {}
#        for ch in sorted(images):
#            ref = images[ch]
#            h.update(f"|{getattr(item, 'defect_id', '')}|{ch}"
#                     f"|{ref.path}|{ref.page}".encode("utf-8"))
#            try:
#                st = os.stat(ref.path)
#                h.update(f"|{st.st_mtime_ns}|{st.st_size}".encode("utf-8"))
#            except OSError:
#                pass
#    return "items:" + h.hexdigest()
#
#
#def _pool_context():
#    """挑選 multiprocessing 啟動方式：主執行緒用 fork、非主執行緒用 spawn。
#
#    為什麼要分：
#    - **fork**（Linux 預設）快、且呼叫端腳本不需要 ``if __name__ == "__main__"``
#      保護 —— CLI 與一般 script 都在主執行緒，維持這個便利性。
#    - 但 fork 若從**非主執行緒**（例如 Studio 的 QThread）呼叫，子行程會繼承
#      其他執行緒持有的鎖，實測 100% 死鎖（M3 Studio「試跑」按鈕）。這種情況
#      改用 **spawn**：每個 worker 多約 0.3 s 啟動成本，但不會卡死。
#      GUI/CLI 進入點都有 ``if __name__ == "__main__"`` 保護，spawn 安全。
#    - Windows 沒有 fork，一律 spawn（本函式自動退回）。
#    """
#    on_main = threading.current_thread() is threading.main_thread()
#    methods = _mp.get_all_start_methods()
#    if on_main and "fork" in methods:
#        return _mp.get_context("fork")
#    return _mp.get_context("spawn")
#
#
#def run_batch(recipe: Recipe, dataset: Any, *,
#              workers: Optional[int] = None,
#              cache_dir: Optional[str] = None,
#              progress: Optional[Callable[[int, int, Dict[str, Any]], Any]] = None,
#              abort_check: Optional[Callable[[], Any]] = None,
#              limit: Optional[int] = None) -> List[Dict[str, Any]]:
#    """平行（或循序）跑整個 dataset，回傳 JSON-safe result dict 清單。
#
#    - ``workers``：None → ``os.cpu_count()``；``<= 1`` → 同進程循序（無 pool）。
#    - ``cache_dir``：有給 → 走 :func:`run_defect_cached`（影像段快取）。
#    - ``progress(done_count, total, result_dict)``：每顆完成呼叫一次
#      （done_count 從 1 起算；平行模式為完成順序，非 item 順序）。
#    - ``abort_check()`` 回 truthy → 取消尚未開跑的顆、回傳已完成的部分結果。
#    - ``limit``：只跑前 N 顆。
#    - 回傳順序 = 原始 item 順序（被 abort 略過的顆不在清單裡）。
#    - 單顆失敗（含 worker 層意外）→ 該顆 ``ok=False`` dict，不殺整批。
#    """
#    items = list(dataset.items) if limit is None else list(dataset.items)[:limit]
#    n = len(items)
#    kind = str(getattr(dataset, "kind", ""))
#    token = _dataset_token_for(dataset) if cache_dir else ""
#
#    if workers is None:
#        workers = os.cpu_count() or 1
#    workers = int(workers)
#
#    # ---- 循序路徑（無 pool；語意同平行路徑）----
#    if workers <= 1 or n <= 1:
#        cache = StageCache(str(cache_dir)) if cache_dir else None
#        out: List[Dict[str, Any]] = []
#        done = 0
#        for item in items:
#            if abort_check is not None and abort_check():
#                break
#            try:
#                if cache is not None:
#                    r = run_defect_cached(recipe, item, kind, cache, token)
#                else:
#                    r = run_defect(recipe, item, kind)
#                d = result_to_json_dict(r)
#            except Exception as e:  # pragma: no cover — run_defect 永不 raise 的保險
#                d = _fail_dict(item, e)
#            out.append(d)
#            done += 1
#            if progress is not None:
#                progress(done, n, d)
#        return out
#
#    # ---- 平行路徑：ProcessPoolExecutor ----
#    results: Dict[int, Dict[str, Any]] = {}
#    recipe_json = recipe.to_json_dict()
#    with ProcessPoolExecutor(
#            max_workers=workers,
#            mp_context=_pool_context(),
#            initializer=_init_worker,
#            initargs=(recipe_json, kind, cache_dir, token, _REPO_ROOT)) as ex:
#        fut_to_idx = {ex.submit(_run_one, item): i
#                      for i, item in enumerate(items)}
#        done = 0
#        for fut in as_completed(fut_to_idx):
#            i = fut_to_idx[fut]
#            try:
#                d = fut.result()
#            except Exception as e:  # 單顆 worker 意外 → FAIL dict，不殺整批
#                d = _fail_dict(items[i], e)
#            results[i] = d
#            done += 1
#            if progress is not None:
#                progress(done, n, d)
#            if abort_check is not None and abort_check():
#                for f in fut_to_idx:
#                    f.cancel()  # 尚未開跑的顆取消；跑一半的顆等它結束但不收
#                break
#
#    return [results[i] for i in sorted(results)]
#
#F 73f0fec00bdfb78cbd32387e4d890b196e5ce1fb 193 adept/core/pipeline/cache.py
## ADEPT stage cache — authored 2026-07-28 (M2).
#"""StageCache — 影像段（checkpoint）快取。
#
#調參迴圈的關鍵加速：影像段（load→norm→align→sub→dn…）佔一顆 defect
#絕大多數運算量，但調的多半是算法段/判定段參數。把影像段結束時的
#Context 快照（images + features + meta 子集）存成 npz，之後同一顆、
#同一影像段簽章、同一 lot 直接續跑算法段。
#
#儲存格式：``dir/<key[:2]>/<key>.npz``
#  - ``img__<name>``：各影像流 ndarray（savez_compressed，無損）
#  - ``__labels__``：ROI label map（若有）
#  - ``__payload__``：0 維字串陣列，內容是 JSON
#    ``{"version": N, "image_names": [...], "features": {...}, "meta": {...},
#       "rois": [[name, nx, ny, nw, nh], ...], "dtypes": {...}, "shapes": {...}}``
#寫入走 atomic（先寫 ``.tmp`` 再 ``os.replace``）；讀到壞檔 → 盡力刪掉、
#回 None（呼叫端退回重算，永不 crash）。
#
#**快照必須涵蓋 Context 的每一個欄位。**（F7-9 修）v1 只存了
#images/features/meta，漏了 ``rois`` 與 ``labels``。checkpoint 是執行順序上的
#**位置**（最後一張影像段卡的下一格），不是「所有影像段的卡」—— 所以放在中間
#的 Region 卡（``roi_define`` / ``blob_segment``，都是 algo）會落在快取段裡。
#於是：第一次跑（miss）正常，**第二次跑（hit）ROI 不見了**，量測卡報
#「region 'main' is not defined」。第一次對、第二次錯是最難查的一種 bug，
#所以 ``FORMAT_VERSION`` 存進 payload，版本對不上一律當 miss 重算 ——
#既有的快取目錄不會把舊的殘缺快照餵回來。
#"""
#from __future__ import annotations
#
#import hashlib
#import json
#import os
#from typing import Any, Dict, Optional
#
#import numpy as np
#
#__all__ = ["StageCache", "dataset_token"]
#
#
#def dataset_token(klarf_path: Any) -> str:
#    """由 KLARF 路徑造出 lot 識別 token：abspath + mtime_ns + size。
#
#    重新產生（覆寫）同名 lot → mtime/size 變 → token 變 → 舊快取自動失效。
#    檔案 stat 不到（少見）→ 退化成只有 abspath。
#    """
#    p = os.path.abspath(str(klarf_path))
#    try:
#        st = os.stat(p)
#    except OSError:
#        return p
#    return f"{p}|{st.st_mtime_ns}|{st.st_size}"
#
#
#class StageCache:
#    """影像段快取（磁碟 npz；single-writer-per-key、多進程安全的 atomic 寫入）。
#
#    ``hits`` / ``misses`` 計數器在 :meth:`get` 內累加（本 instance 的統計；
#    平行批次時各 worker 有自己的 instance 與計數）。
#    """
#
#    #: 快照格式版本。**欄位有增減就要 +1** —— 版本對不上的舊快照一律當 miss，
#    #: 不然使用者既有的快取目錄會繼續餵回缺欄位的快照。
#    FORMAT_VERSION = 2
#
#    def __init__(self, dir: str) -> None:
#        self.dir = str(dir)
#        os.makedirs(self.dir, exist_ok=True)
#        self.hits = 0
#        self.misses = 0
#
#    # ---- key ---------------------------------------------------------------
#    @staticmethod
#    def make_key(dataset_token: str, defect_id: str, signature: str) -> str:
#        """(lot token, defect_id, 影像段簽章) → sha1 hex（deterministic）。"""
#        payload = json.dumps(
#            [str(dataset_token), str(defect_id), str(signature)],
#            ensure_ascii=False, separators=(",", ":"))
#        return hashlib.sha1(payload.encode("utf-8")).hexdigest()
#
#    # 讓呼叫端也能用 StageCache.dataset_token(...)（同模組函式）
#    dataset_token = staticmethod(dataset_token)
#
#    def _path(self, key: str) -> str:
#        key = str(key)
#        return os.path.join(self.dir, key[:2], key + ".npz")
#
#    # ---- get / put ---------------------------------------------------------
#    def get(self, key: str) -> Optional[Dict[str, Any]]:
#        """回 ``{"images", "features", "meta", "rois", "labels"}``
#        或 None（不存在 / 壞檔 / 舊格式；壞檔會盡力刪掉）。"""
#        path = self._path(key)
#        if not os.path.isfile(path):
#            self.misses += 1
#            return None
#        try:
#            with np.load(path, allow_pickle=False) as z:
#                payload = json.loads(str(z["__payload__"][()]))
#                if int(payload.get("version", 1)) != self.FORMAT_VERSION:
#                    # 舊格式（缺欄位）—— 當作沒有，讓呼叫端重算並覆寫
#                    self.misses += 1
#                    return None
#                images = {str(n): z["img__" + str(n)]
#                          for n in payload["image_names"]}
#                features = {str(k): float(v)
#                            for k, v in dict(payload.get("features") or {}).items()}
#                meta = dict(payload.get("meta") or {})
#                rois = [(str(r[0]), tuple(float(v) for v in r[1:5]))
#                        for r in (payload.get("rois") or [])]
#                labels = z["__labels__"] if "__labels__" in z.files else None
#        except Exception:
#            try:
#                os.remove(path)  # 壞檔：盡力清掉，下次直接 miss
#            except OSError:
#                pass
#            self.misses += 1
#            return None
#        self.hits += 1
#        return {"images": images, "features": features, "meta": meta,
#                "rois": rois, "labels": labels}
#
#    def put(self, key: str, images: Dict[str, np.ndarray],
#            features: Dict[str, float], meta: Dict[str, Any],
#            rois: Any = None, labels: Any = None) -> None:
#        """寫入一筆快照（atomic：先 ``.tmp`` 再 ``os.replace``）。
#
#        失敗會 raise（磁碟滿、唯讀…）—— 呼叫端（run_defect_cached）自行
#        try/except 退回無快取路徑。
#        """
#        path = self._path(key)
#        os.makedirs(os.path.dirname(path), exist_ok=True)
#
#        imgs = {str(n): np.asarray(a) for n, a in dict(images or {}).items()}
#        payload = {
#            "version": self.FORMAT_VERSION,
#            "image_names": sorted(imgs),
#            "features": {str(k): float(v)
#                         for k, v in dict(features or {}).items()},
#            "meta": dict(meta or {}),
#            # 具名 ROI（正規化座標，跟 Context.set_roi 同一個格式）
#            "rois": [[str(name)] + [float(v) for v in rect]
#                     for name, rect in (rois or [])],
#            # dtype / shape 註記（除錯、日後版本檢查用；載入以 npz 內容為準）
#            "dtypes": {n: str(a.dtype) for n, a in imgs.items()},
#            "shapes": {n: list(a.shape) for n, a in imgs.items()},
#        }
#        arrays: Dict[str, np.ndarray] = {"img__" + n: a for n, a in imgs.items()}
#        if labels is not None:
#            arrays["__labels__"] = np.asarray(labels)
#        arrays["__payload__"] = np.array(
#            json.dumps(payload, ensure_ascii=False, sort_keys=True))
#
#        tmp = f"{path}.{os.getpid()}.tmp"  # 含 pid：多 worker 同 dir 不互踩
#        try:
#            with open(tmp, "wb") as f:
#                np.savez_compressed(f, **arrays)
#            os.replace(tmp, path)
#        finally:
#            if os.path.exists(tmp):
#                try:
#                    os.remove(tmp)
#                except OSError:
#                    pass
#
#    # ---- 管理 --------------------------------------------------------------
#    def stats(self) -> Dict[str, int]:
#        """快取目錄現況：``{"n_files": 檔數, "bytes": 總大小}``。"""
#        n = 0
#        total = 0
#        for root, _dirs, files in os.walk(self.dir):
#            for fn in files:
#                if not fn.endswith(".npz"):
#                    continue
#                try:
#                    st = os.stat(os.path.join(root, fn))
#                except OSError:
#                    continue
#                n += 1
#                total += int(st.st_size)
#        return {"n_files": n, "bytes": total}
#
#    def clear(self) -> None:
#        """清空快取目錄（保留根目錄本身；計數器不歸零）。"""
#        for root, dirs, files in os.walk(self.dir, topdown=False):
#            for fn in files:
#                try:
#                    os.remove(os.path.join(root, fn))
#                except OSError:
#                    pass
#            for dn in dirs:
#                try:
#                    os.rmdir(os.path.join(root, dn))
#                except OSError:
#                    pass
#
#F eaea0e601b87670141d579df99ef562c37f8ae65 207 adept/core/pipeline/context.py
## ADEPT pipeline contract — authored 2026-07-27 (M1).
#"""Context — pipeline 步驟間傳遞的執行狀態。
#
#設計原則（見 docs/plans/F0-master-plan.md §3.2）：
#- ``images``   命名影像流（"test"、"ref"、"ref_aligned"、"diff"、"snr_map"…）。
#- ``rois``     MultiROISet（正規化座標；M3 起由 ROI 卡填入）。
#- ``labels``   整數 ROI label map（0=背景, 1..N；GLAS 契約 gray[labels==k]）。
#- ``features`` 扁平特徵區 —— **score 表達式的唯一變數空間**。
#  任何卡塞進來的數字（CD、SNR、GLV、focus…）一視同仁。
#- ``meta``     診斷與雜項（nm_per_px、對位 dx/dy、fallback_reason、blob 清單…）。
#
#慣例：
#- Step 對同名影像流做 in-place 覆寫（linear 鏈的預設行為）；要保留舊圖就寫新 key。
#- feature 覆寫允許，但會記錄在 ``meta["feature_overwrites"]`` 供 lint/UI 提示。
#- 引擎在執行前會把當前 DefectItem 放進 ``meta["_defect_item"]``、Dataset kind 放進
#  ``meta["_dataset_kind"]``（Load 卡讀這兩個 key）。
#"""
#from __future__ import annotations
#
#from dataclasses import dataclass, field
#from typing import Any, Dict, List, Optional
#
#import numpy as np
#
#
#class ContextError(RuntimeError):
#    """步驟向 Context 要不存在的資源時拋出（訊息需列出現有 keys）。"""
#
#
#@dataclass
#class Context:
#    images: Dict[str, np.ndarray] = field(default_factory=dict)
#    rois: Optional[Any] = None            # adept.core.algo.roi.MultiROISet
#    labels: Optional[np.ndarray] = None
#    features: Dict[str, float] = field(default_factory=dict)
#    meta: Dict[str, Any] = field(default_factory=dict)
#    #: 記錄「這一步把某條影像流改成什麼樣」（F7-17，**預設關閉**）。
#    #:
#    #: Enhance 卡是就地改寫同一條流的（``test → test``），所以跑完之後「之前
#    #: 長什麼樣」就沒了 —— 而那正是使用者最需要看的：對比拉大之後背景被壓成
#    #: 全黑、缺陷的邊界也一起被吃掉，畫面上只會覺得「變乾淨了」。
#    #:
#    #: 只在**預覽**（單顆）打開。批次跑一萬顆時每一次 set_image 都算兩個直方圖
#    #: 是白花的力氣 —— 那份資料沒有人看。
#    track_changes: bool = False
#
#    # ---- images -----------------------------------------------------------
#    def require_image(self, key: str) -> np.ndarray:
#        try:
#            return self.images[key]
#        except KeyError:
#            raise ContextError(
#                f"image stream '{key}' does not exist; available: "
#                f"{sorted(self.images)}"
#            ) from None
#
#    def set_image(self, key: str, arr: np.ndarray) -> None:
#        if not isinstance(arr, np.ndarray):
#            raise ContextError(f"set_image('{key}') needs a numpy array, got "
#                               f"{type(arr).__name__}")
#        if self.track_changes and key in self.images:
#            # 覆寫既有的流 = 有人在改它。記下改之前與改之後的樣子。
#            self._record_change(key, self.images[key], arr)
#        self.images[key] = arr
#
#    #: 記錄用的直方圖分幾格。夠看出「壓平了」「削掉了」，又不會讓 meta 變肥。
#    HIST_BINS = 48
#
#    def _record_change(self, key: str, before: np.ndarray,
#                       after: np.ndarray) -> None:
#        """把一次覆寫壓成兩個直方圖 + 削平計數，放進 ``meta['stream_change']``。
#
#        存的是**摘要不是影像** —— 存兩張圖會讓每顆 defect 的 meta 變成幾百 KB，
#        而使用者要回答的問題（「我把資訊弄掉了嗎」）用直方圖就答得出來。
#        """
#        try:
#            rec = {
#                "before": _hist(before, self.HIST_BINS),
#                "after": _hist(after, self.HIST_BINS),
#                "clipped_low": _clipped(after, low=True),
#                "clipped_high": _clipped(after, low=False),
#                "was_clipped_low": _clipped(before, low=True),
#                "was_clipped_high": _clipped(before, low=False),
#            }
#        except Exception:               # noqa: BLE001 — 記錄失敗不准影響執行
#            return
#        self.meta.setdefault("stream_change", {})[str(key)] = rec
#
#    # ---- ROI（F7-4）--------------------------------------------------------
#    #
#    # ``rois`` 是 ``algo.roi.MultiROISet``（vendoring 自 Fusi³，正規化座標）。
#    # 那個類別是為「ROI 編輯器」設計的（有 id / target / reference / 顏色），
#    # ADEPT 要的其實只是「用**名字**取一個框」，所以在這裡包一層以名字為鍵的
#    # API，底層仍然用 MultiROISet 的 ``label`` 當名字 —— 不另外發明資料結構。
#    #
#    # 座標一律是正規化的 (nx, ny, nw, nh)，理由見 docs/plans/F7 §4：
#    # patch 是以 defect 為中心裁切的，同一份 recipe 換一個 patch 尺寸時，
#    # 用比例定義的框才會落在同一個地方（像素值會失效）。
#
#    def set_roi(self, name: str, norm_rect: Any) -> None:
#        """以名字寫入一個 ROI（同名覆寫）。``norm_rect`` = (nx, ny, nw, nh)。"""
#        from ..algo.roi import MultiROISet
#
#        name = str(name)
#        rect = tuple(float(v) for v in norm_rect)
#        if len(rect) != 4:
#            raise ContextError(
#                f"set_roi('{name}') needs (nx, ny, nw, nh), got {norm_rect!r}")
#        if self.rois is None:
#            self.rois = MultiROISet()
#        for roi in list(self.rois.rois):
#            if roi.label == name:
#                self.rois.remove_roi(roi.id)
#        self.rois.add_roi(rect, label=name)
#
#    def roi_names(self) -> List[str]:
#        """目前定義了哪些 ROI 名字（依加入順序）。"""
#        if self.rois is None:
#            return []
#        return [r.label for r in self.rois.rois]
#
#    def require_roi(self, name: str) -> Any:
#        """以名字取一個 ``NamedROI``；不存在時拋帶說明的 ContextError。"""
#        name = str(name)
#        for roi in (self.rois.rois if self.rois is not None else ()):
#            if roi.label == name:
#                return roi
#        raise ContextError(
#            f"ROI '{name}' is not defined; available: {self.roi_names()}. "
#            f"Add a Region card upstream, or leave the roi parameter empty "
#            f"to use the whole image.")
#
#    def roi_rect(self, name: str, shape: Any) -> Any:
#        """以名字取像素矩形 ``(x, y, w, h)``，套用到 ``shape``=(H, W) 的影像。"""
#        return self.require_roi(name).to_pixel_rect(tuple(shape)[:2])
#
#    # ---- features ---------------------------------------------------------
#    def add_feature(self, name: str, value: Any) -> None:
#        """寫入一個特徵值（強制轉 float；NaN/inf 允許，由表達式層做安全處理）。"""
#        v = float(value)
#        if name in self.features:
#            self.meta.setdefault("feature_overwrites", []).append(name)
#        self.features[name] = v
#
#    def add_features(self, mapping: Dict[str, Any]) -> None:
#        for k, v in mapping.items():
#            self.add_feature(k, v)
#
#    # ---- misc -------------------------------------------------------------
#    @property
#    def nm_per_px(self) -> Optional[float]:
#        return self.meta.get("nm_per_px")
#
#    def warn(self, msg: str) -> None:
#        self.meta.setdefault("warnings", []).append(str(msg))
#
#    def summary(self) -> Dict[str, Any]:
#        """輕量摘要（不含像素資料），供 trace / debug 輸出。"""
#        return {
#            "images": {k: tuple(v.shape) for k, v in self.images.items()},
#            "features": dict(self.features),
#            "warnings": list(self.meta.get("warnings", [])),
#        }
#
#
## --------------------------------------------------------------------------- #
## 影像流變動的摘要（F7-17）—— 純函式，UI 與測試都可以直接用
## --------------------------------------------------------------------------- #
#def _finite(arr: "np.ndarray") -> "np.ndarray":
#    a = np.asarray(arr)
#    if a.dtype.kind == "f":
#        a = a[np.isfinite(a)]
#    return a.reshape(-1)
#
#
#def _hist(arr: "np.ndarray", bins: int) -> List[int]:
#    """灰階分布。**固定用 0–255 的刻度**，不用每張圖自己的 min–max ——
#    比較 before / after 的前提是兩者在同一把尺上，各自拉伸就沒得比了。
#
#    float 影像（diff / snr_map 這類）本來就不在 0–255，那時候退回兩者的
#    共同範圍；退回的判斷放在呼叫端之外，這裡只負責照給定範圍分格。
#    """
#    a = _finite(arr)
#    if a.size == 0:
#        return [0] * int(bins)
#    lo, hi = 0.0, 255.0
#    if a.dtype.kind == "f" and (float(a.min()) < -1.0 or float(a.max()) > 256.0):
#        lo, hi = float(a.min()), float(a.max())
#        if hi <= lo:
#            hi = lo + 1.0
#    idx = np.clip(((a.astype(np.float64) - lo) / (hi - lo) * bins).astype(int),
#                  0, int(bins) - 1)
#    return np.bincount(idx, minlength=int(bins)).astype(int).tolist()
#
#
#def _clipped(arr: "np.ndarray", low: bool) -> float:
#    """貼在 0（或 255）的畫素佔多少比例。
#
#    削平是 Enhance **唯一**會安靜毀掉資訊的方式：那些畫素的差異永遠回不來了，
#    而畫面上只會覺得「對比變好了」。
#    """
#    a = _finite(arr)
#    if a.size == 0:
#        return 0.0
#    hit = (a <= 0.5) if low else (a >= 254.5)
#    return float(np.count_nonzero(hit)) / float(a.size)
#
#F 8a8f906147c0b06defc52096716ecfd917b0b94e 117 adept/core/pipeline/curve.py
## ADEPT pipeline contract — authored 2026-07-29 (F7-8).
#"""Tone-curve 控制點的字串編碼（parse / format）。
#
#為什麼是字串
#------------
#recipe 是給人看、也給 git diff 看的 JSON。控制點如果存成巢狀陣列，
#diff 會變成一整片括號；存成 ``"0,0; 0.35,0.55; 1,1"`` 一眼就看得出使用者
#把暗部拉起來了。而且 ``ParamSpec`` 的值一律是純量 —— 一個參數一個值，
#UI 表單、rescore、CLI ``--set`` 都靠這條規則，不想為了曲線破例。
#
#為什麼放在 ``pipeline/`` 而不是 ``algo/``
#-----------------------------------------
#``ParamSpec.validate`` 要用它（推廣鐵則：填爆的值要擋在表單，不能跑到演算法
#裡才炸），而 ``pipeline`` 不該把整個 ``algo`` 套件（連帶 cv2）拉進 import 圖。
#所以**編碼**在這裡、純 stdlib；**求值**（LUT、套用到影像）在
#``algo/curve.py``，那邊才用 numpy。
#"""
#from __future__ import annotations
#
#from typing import List, Sequence, Tuple
#
#__all__ = ["IDENTITY", "parse_curve", "format_curve", "is_identity",
#           "CurveError"]
#
#Point = Tuple[float, float]
#
##: 預設曲線 = ``y = x``（什麼都不做）。UI 的曲線編輯器一開也是這條線。
#IDENTITY = "0,0; 1,1"
#
##: 兩個 x 太靠近就視為同一點（避免除以 0，也避免使用者拖出肉眼看不出的重疊點）。
#_MIN_DX = 1e-4
#
#
#class CurveError(ValueError):
#    """曲線字串不合法。訊息是白話的 —— 會直接顯示在參數列下面。"""
#
#
#def parse_curve(text: object) -> List[Point]:
#    """``"0,0; 0.4,0.6; 1,1"`` → ``[(0.0, 0.0), (0.4, 0.6), (1.0, 1.0)]``。
#
#    規則（每一條都會回一句白話錯誤）：
#
#    * 至少兩點；
#    * x 與 y 都在 0–1；
#    * 依 x 排序後 x 必須嚴格遞增（曲線不能往回折）；
#    * 頭尾的 x 必須是 0 與 1 —— 曲線要覆蓋整個灰階範圍，
#      少了就會有一段灰階沒有定義。
#
#    空字串（或 ``None``）視為 :data:`IDENTITY`，這樣舊 recipe 沒有這個參數
#    也讀得動。
#    """
#    s = "" if text is None else str(text).strip()
#    if not s:
#        return parse_curve(IDENTITY)
#
#    pts: List[Point] = []
#    for chunk in s.replace("\n", ";").split(";"):
#        chunk = chunk.strip()
#        if not chunk:
#            continue
#        bits = [b.strip() for b in chunk.split(",")]
#        if len(bits) != 2:
#            raise CurveError(
#                "curve point '%s' should look like 'x,y' (two numbers between "
#                "0 and 1, separated by a comma)" % chunk)
#        try:
#            x, y = float(bits[0]), float(bits[1])
#        except ValueError:
#            raise CurveError(
#                "curve point '%s' is not a pair of numbers" % chunk) from None
#        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
#            raise CurveError(
#                "curve point '%s' is outside 0–1 (x is the input gray level, "
#                "y is the output, both normalised)" % chunk)
#        pts.append((x, y))
#
#    if len(pts) < 2:
#        raise CurveError("a curve needs at least two points (start and end)")
#
#    pts.sort(key=lambda p: p[0])
#    for a, b in zip(pts, pts[1:]):
#        if b[0] - a[0] < _MIN_DX:
#            raise CurveError(
#                "two curve points share the same input level (x=%.4f); "
#                "a curve can only go left to right" % a[0])
#    if pts[0][0] > 0.0 or pts[-1][0] < 1.0:
#        raise CurveError(
#            "a curve must start at x=0 and end at x=1, otherwise part of the "
#            "gray range has no output defined")
#    return pts
#
#
#def format_curve(points: Sequence[Point]) -> str:
#    """控制點 → 標準字串。四位小數 —— 再細也不是使用者拉得出來的精度。"""
#    out = []
#    for x, y in points:
#        out.append("%s,%s" % (_num(x), _num(y)))
#    return "; ".join(out)
#
#
#def is_identity(points: Sequence[Point], tol: float = 1e-6) -> bool:
#    """這條曲線等於 ``y = x`` 嗎（也就是「使用者其實沒畫」）。
#
#    卡片用這個判斷要不要理會曲線 —— 沒畫就走 gamma 滑桿。
#    """
#    pts = list(points)
#    if len(pts) != 2:
#        return all(abs(y - x) <= tol for x, y in pts)
#    return all(abs(y - x) <= tol for x, y in pts)
#
#
#def _num(v: float) -> str:
#    """去掉沒有意義的尾數零：``0.5000`` → ``0.5``、``1.0000`` → ``1``。"""
#    s = "%.4f" % float(v)
#    s = s.rstrip("0").rstrip(".")
#    return s or "0"
#
#F fa5da5800962d9f5372360e914f440f9601d784d 448 adept/core/pipeline/engine.py
## ADEPT pipeline engine — authored 2026-07-28 (M1; M2 加入 checkpoint 快取).
#"""單顆執行引擎：對一顆 defect 依 recipe 跑完整 pipeline。
#
#M1：單進程、循序。M2：內部重構成可重用片段（種 Context → 跑節點區間 →
#算分），讓 :func:`run_defect_cached` 能從「影像段結束」的 checkpoint 續跑
#（影像段快取見 :mod:`.cache`，平行批次見 :mod:`.batch`）。
#
#鐵則：**單顆爆 = 該顆 FAIL，不殺整批** —— :func:`run_defect` 與
#:func:`run_defect_cached` 永不 raise，所有錯誤（StepError / ContextError /
#RecipeError / 快取讀寫失敗 / 其他）都收進 :class:`DefectResult` 或
#自動退回全程重算。
#"""
#from __future__ import annotations
#
#import json
#import math
#import time
#from dataclasses import dataclass
#from typing import Any, Callable, Dict, List, Optional, Tuple, Type
#
#from .context import Context
#from .expression import parse_expression
#from .recipe import Recipe, RecipeError, execution_order
#from .step import CATEGORY_IMAGE, REGISTRY, Step, StepError
#
#__all__ = ["StepTrace", "DefectResult", "run_defect", "run_defect_cached",
#           "run_dataset", "image_segment_signature", "result_to_json_dict"]
#
#
#@dataclass
#class StepTrace:
#    """一個節點的執行紀錄（供 Studio 單顆預覽與 debug）。"""
#    node_id: str
#    step_key: str
#    ok: bool
#    ms: float
#    error: Optional[str]
#    features_added: Dict[str, float]   # 該步驟新增或改值的特徵
#    images_after: List[str]            # 該步驟結束後的影像流 key（排序）
#
#
#@dataclass
#class DefectResult:
#    """一顆 defect 的完整執行結果。"""
#    defect_id: str
#    ok: bool
#    error: Optional[str]
#    features: Dict[str, float]
#    score: Optional[float]
#    bin: Optional[int]
#    traces: List[StepTrace]
#    context: Optional[Context]         # keep_context=True 才附上（不進 JSON）
#
#
## ---------------------------------------------------------------------------
## 可重用片段（M2 重構；run_defect 的行為與 M1 完全相同）
## ---------------------------------------------------------------------------
#def _seed_context(item: Any, kind: str, defect_id: str) -> Context:
#    """建立新 Context 並種入引擎慣例的 meta key（Load 卡讀這些）。"""
#    ctx = Context()
#    ctx.meta["_defect_item"] = item
#    ctx.meta["_dataset_kind"] = kind
#    ctx.meta["_defect_id"] = defect_id
#    ctx.meta["nm_per_px"] = getattr(item, "nm_per_px", None)
#    return ctx
#
#
#def _finish(defect_id: str, ctx: Context, traces: List[StepTrace],
#            keep_context: bool, ok: bool, error: Optional[str],
#            score: Optional[float] = None,
#            bin_: Optional[int] = None) -> DefectResult:
#    return DefectResult(
#        defect_id=defect_id, ok=ok, error=error,
#        features=dict(ctx.features), score=score, bin=bin_,
#        traces=traces, context=(ctx if keep_context else None))
#
#
#def _run_nodes(recipe: Recipe, order: List[str], start: int, stop: int,
#               ctx: Context, traces: List[StepTrace],
#               registry: Dict[str, Type[Step]],
#               upto_node: Optional[str]) -> Tuple[Context, Optional[str]]:
#    """執行 ``order[start:stop]`` 的節點；trace 逐一 append。
#
#    回傳 ``(ctx, error)``：error 為 None 表成功（或在 upto_node 停下）；
#    否則為 "[node_id] 訊息" 字串（呼叫端包成失敗結果）。
#    """
#    for nid in order[start:stop]:
#        node = recipe.nodes.get(nid)
#        if node is None:
#            traces.append(StepTrace(
#                node_id=nid, step_key="?", ok=False, ms=0.0,
#                error=f"step '{nid}' is not in recipe.nodes", features_added={},
#                images_after=sorted(ctx.images)))
#            return ctx, f"[{nid}] step '{nid}' is not in recipe.nodes"
#        if not node.enabled:
#            if nid == upto_node:
#                break  # 目標節點被停用：停在它這裡、不執行它
#            continue
#
#        t0 = time.perf_counter()
#        feats_before = dict(ctx.features)
#        try:
#            step_cls = registry.get(node.step)
#            if step_cls is None:
#                raise StepError(
#                    node.step,
#                    f"unknown step '{node.step}'; registered: {sorted(registry)}")
#            params = step_cls.validate_params(node.params)
#            ret = step_cls().run(ctx, params)
#            if isinstance(ret, Context):
#                ctx = ret
#        except Exception as e:  # StepError / ContextError / ParamError / 其他
#            ms = (time.perf_counter() - t0) * 1000.0
#            traces.append(StepTrace(
#                node_id=nid, step_key=node.step, ok=False, ms=ms,
#                error=str(e), features_added={},
#                images_after=sorted(ctx.images)))
#            return ctx, f"[{nid}] {e}"
#
#        ms = (time.perf_counter() - t0) * 1000.0
#        added = {
#            k: v for k, v in ctx.features.items()
#            if k not in feats_before or feats_before[k] != v
#        }
#        traces.append(StepTrace(
#            node_id=nid, step_key=node.step, ok=True, ms=ms,
#            error=None, features_added=added,
#            images_after=sorted(ctx.images)))
#        if nid == upto_node:
#            break
#    return ctx, None
#
#
#def _eval_score(recipe: Recipe, ctx: Context) -> Tuple[float, int]:
#    """ADC 判定：score = expr(features) → bin。失敗會 raise（呼叫端攔截）。"""
#    expr = parse_expression(recipe.score.expr)
#    score = expr.eval(ctx.features)
#    ctx.features["score"] = score
#    if score < float(recipe.score.threshold):
#        b = int(recipe.score.bins["below"])
#    else:
#        b = int(recipe.score.bins["above"])
#    return score, b
#
#
#def run_defect(recipe: Recipe, item: Any, kind: str, *,
#               keep_context: bool = False,
#               upto_node: Optional[str] = None,
#               track_changes: bool = False,
#               registry: Optional[Dict[str, Type[Step]]] = None) -> DefectResult:
#    """對單顆 defect 執行 ``kind`` 這條 route；**永不 raise**。
#
#    - Context.meta 先種入 ``_defect_item`` / ``_dataset_kind`` / ``_defect_id`` /
#      ``nm_per_px``（Load 卡讀這些 key）。
#    - 停用（enabled=False）節點跳過。
#    - ``track_changes``：把「每一次覆寫既有影像流的前後樣貌」記進
#      ``ctx.meta['stream_change']``（F7-17 的 Enhance 儀表要的）。**預設關**——
#      批次跑一萬顆時那份資料沒有人看，不值得每次 set_image 都算兩個直方圖。
#    - ``upto_node``：跑到該節點**之後**就停（Studio 點卡看中間輸出用）；
#      強制 keep_context=True，score/bin 不算（None）；若該節點被停用則
#      停在它前面、不執行它；不在 route 上 → ok=False（不 raise）。
#    - 步驟全過後：score = expr(features)、features["score"] = score、
#      bin = bins["below"]（score < threshold）否則 bins["above"]。
#    """
#    if registry is None:
#        registry = REGISTRY
#    if upto_node is not None:
#        keep_context = True  # 中間輸出就是要看 context
#
#    defect_id = str(getattr(item, "defect_id", ""))
#    ctx = _seed_context(item, kind, defect_id)
#    ctx.track_changes = bool(track_changes)
#    traces: List[StepTrace] = []
#
#    try:
#        order = execution_order(recipe, kind)
#    except RecipeError as e:
#        return _finish(defect_id, ctx, traces, keep_context, False, str(e))
#
#    if upto_node is not None and upto_node not in order:
#        return _finish(
#            defect_id, ctx, traces, keep_context, False,
#            f"upto_node '{upto_node}' is not in the execution order {order} "
#            f"of route '{kind}'")
#
#    ctx, err = _run_nodes(recipe, order, 0, len(order), ctx, traces,
#                          registry, upto_node)
#    if err is not None:
#        return _finish(defect_id, ctx, traces, keep_context, False, err)
#
#    if upto_node is not None:
#        return _finish(defect_id, ctx, traces, keep_context, True, None)
#
#    # ---- ADC 判定：score → bin ----
#    try:
#        score, b = _eval_score(recipe, ctx)
#    except Exception as e:
#        return _finish(defect_id, ctx, traces, keep_context, False, f"[score] {e}")
#    return _finish(defect_id, ctx, traces, keep_context, True, None,
#                   score=score, bin_=b)
#
#
## ---------------------------------------------------------------------------
## M2：影像段 checkpoint（signature）與快取續跑
## ---------------------------------------------------------------------------
#def image_segment_signature(recipe: Recipe, kind: str,
#                            registry: Optional[Dict[str, Type[Step]]] = None
#                            ) -> Tuple[str, int]:
#    """算出 ``kind`` route 的影像段簽章與 checkpoint 索引。
#
#    checkpoint 索引 = 執行順序中「最後一個 enabled 且 category==image 的節點」
#    的下一個位置；沒有影像段節點 → 0（快取沒意義）。
#    簽章 = checkpoint 前所有 enabled 節點的
#    ``[(node_id, step_key, sorted-param-items), ...]`` + kind 的穩定 JSON 字串
#    （params 先過 ``validate_params`` 正規化：帶預設值、coerce 型別，
#    讓「寫不寫預設值」不影響簽章）。deterministic。
#
#    注意：未知 route / 循環會 raise :class:`RecipeError`
#    （:func:`run_defect_cached` 會攔截並退回 :func:`run_defect`）。
#    """
#    if registry is None:
#        registry = REGISTRY
#    order = execution_order(recipe, kind)
#
#    ckpt = 0
#    for i, nid in enumerate(order):
#        node = recipe.nodes.get(nid)
#        if node is None or not node.enabled:
#            continue
#        step_cls = registry.get(node.step)
#        if step_cls is not None and step_cls.category == CATEGORY_IMAGE:
#            ckpt = i + 1
#
#    sig_nodes: List[List[Any]] = []
#    for nid in order[:ckpt]:
#        node = recipe.nodes.get(nid)
#        if node is None or not node.enabled:
#            continue  # 停用節點不影響執行，也不進簽章
#        params: Dict[str, Any] = dict(node.params)
#        step_cls = registry.get(node.step)
#        if step_cls is not None:
#            try:
#                params = step_cls.validate_params(node.params)
#            except Exception:
#                params = dict(node.params)  # 壞參數：用原樣（執行時會爆，簽章仍穩定）
#        items = sorted((str(k), v) for k, v in params.items())
#        sig_nodes.append([nid, node.step, [list(kv) for kv in items]])
#
#    sig = json.dumps({"kind": kind, "nodes": sig_nodes},
#                     ensure_ascii=False, sort_keys=True, default=str,
#                     separators=(",", ":"))
#    return sig, ckpt
#
#
#def _json_safe(v: Any) -> bool:
#    try:
#        json.dumps(v)
#        return True
#    except (TypeError, ValueError):
#        return False
#
#
#def _meta_snapshot(meta: Dict[str, Any]) -> Dict[str, Any]:
#    """meta 的可快取子集：去掉私有 key（``_`` 開頭，引擎每次重新種入）、
#    去掉 JSON 序列化不了的值（例如 ndarray、物件）。
#    涵蓋 warnings / notes / nm_per_px / align_dx / align_dy /
#    feature_overwrites … 等後段卡片可能讀到的一般值。"""
#    out: Dict[str, Any] = {}
#    for k, v in meta.items():
#        if str(k).startswith("_"):
#            continue
#        if _json_safe(v):
#            out[k] = v
#    return out
#
#
#def _roi_snapshot(ctx: Context) -> List[Any]:
#    """具名 ROI → ``[(name, (nx, ny, nw, nh)), ...]``（可 JSON 化）。"""
#    out: List[Any] = []
#    for roi in (ctx.rois.rois if ctx.rois is not None else ()):
#        try:
#            rect = tuple(float(v) for v in roi.norm_rect)
#        except Exception:              # noqa: BLE001 — 快取是盡力而為
#            continue
#        out.append((str(roi.label), rect))
#    return out
#
#
#def _restore_context(item: Any, kind: str, defect_id: str,
#                     snap: Dict[str, Any]) -> Context:
#    """由快取快照重建 Context。
#
#    **Context 的每一個欄位都要回來**，不只 images/features/meta。checkpoint 是
#    執行順序上的位置，不是「所有影像段的卡」，所以夾在中間的 Region 卡
#    （algo）會落在快取段裡 —— 漏掉 ``rois`` 的話會變成「第一次跑對、第二次跑
#    錯」。見 :mod:`.cache` 的模組說明。
#    """
#    ctx = _seed_context(item, kind, defect_id)
#    for name, arr in dict(snap.get("images") or {}).items():
#        ctx.images[str(name)] = arr
#    for name, val in dict(snap.get("features") or {}).items():
#        ctx.features[str(name)] = float(val)
#    for k, v in dict(snap.get("meta") or {}).items():
#        ctx.meta[str(k)] = v  # 快照不含 ``_`` 開頭 key，不會蓋掉剛種的
#    for name, rect in (snap.get("rois") or []):
#        ctx.set_roi(str(name), rect)
#    labels = snap.get("labels")
#    if labels is not None:
#        ctx.labels = labels
#    return ctx
#
#
#def run_defect_cached(recipe: Recipe, item: Any, kind: str,
#                      cache: Any, dataset_token: str, *,
#                      keep_context: bool = False,
#                      registry: Optional[Dict[str, Type[Step]]] = None
#                      ) -> DefectResult:
#    """帶影像段快取的單顆執行；**永不 raise**，結果與 :func:`run_defect`
#    位元級一致（features / score / bin）。
#
#    - 影像段（到 checkpoint 為止）命中快取 → 直接重建 Context 續跑算法段；
#      未命中 → 跑影像段、寫入快取（:class:`.cache.StageCache`）、續跑。
#    - checkpoint == 0（沒有影像段節點）或快取讀/寫失敗 → 退回全程重算，
#      不會 crash。
#    - 快取命中時 ``traces`` 只含 checkpoint 之後的節點（影像段沒真的跑）。
#    """
#    if registry is None:
#        registry = REGISTRY
#
#    try:
#        sig, ckpt = image_segment_signature(recipe, kind, registry=registry)
#    except Exception:
#        return run_defect(recipe, item, kind,
#                          keep_context=keep_context, registry=registry)
#    if cache is None or ckpt <= 0:
#        return run_defect(recipe, item, kind,
#                          keep_context=keep_context, registry=registry)
#
#    defect_id = str(getattr(item, "defect_id", ""))
#    key: Optional[str] = None
#    snap: Optional[Dict[str, Any]] = None
#    try:
#        key = cache.make_key(str(dataset_token), defect_id, sig)
#        snap = cache.get(key)
#    except Exception:
#        snap = None  # 快取層出包 → 當作 miss
#
#    order = execution_order(recipe, kind)  # signature 已驗證過，不會再 raise
#    traces: List[StepTrace] = []
#    ctx: Optional[Context] = None
#
#    if snap is not None:
#        try:
#            ctx = _restore_context(item, kind, defect_id, snap)
#        except Exception:
#            ctx = None  # 快照壞掉 → 退回重算影像段
#
#    if ctx is None:
#        # miss：跑影像段（order[:ckpt]），成功才寫快取
#        ctx = _seed_context(item, kind, defect_id)
#        ctx, err = _run_nodes(recipe, order, 0, ckpt, ctx, traces,
#                              registry, None)
#        if err is not None:
#            return _finish(defect_id, ctx, traces, keep_context, False, err)
#        if key is not None:
#            try:
#                cache.put(key, dict(ctx.images), dict(ctx.features),
#                          _meta_snapshot(ctx.meta),
#                          rois=_roi_snapshot(ctx), labels=ctx.labels)
#            except Exception:
#                pass  # 快取寫入失敗 → 不影響本次結果
#
#    # 續跑算法段 + ADC 判定
#    ctx, err = _run_nodes(recipe, order, ckpt, len(order), ctx, traces,
#                          registry, None)
#    if err is not None:
#        return _finish(defect_id, ctx, traces, keep_context, False, err)
#    try:
#        score, b = _eval_score(recipe, ctx)
#    except Exception as e:
#        return _finish(defect_id, ctx, traces, keep_context, False, f"[score] {e}")
#    return _finish(defect_id, ctx, traces, keep_context, True, None,
#                   score=score, bin_=b)
#
#
#def run_dataset(recipe: Recipe, dataset: Any, *,
#                progress: Optional[Callable[[int, int, DefectResult], Any]] = None,
#                limit: Optional[int] = None) -> List[DefectResult]:
#    """循序跑整個 dataset（M1 單進程；平行批次見 :func:`.batch.run_batch`）。
#
#    - ``limit``：只跑前 N 顆（調參試跑用）。
#    - ``progress(i, n, result)``：每顆跑完呼叫一次（i 為 0 起算的索引）。
#    - 單顆失敗不影響其他顆（run_defect 永不 raise）。
#    """
#    items = list(dataset.items) if limit is None else list(dataset.items)[:limit]
#    n = len(items)
#    results: List[DefectResult] = []
#    for i, item in enumerate(items):
#        r = run_defect(recipe, item, dataset.kind)
#        results.append(r)
#        if progress is not None:
#            progress(i, n, r)
#    return results
#
#
## ---------------------------------------------------------------------------
## JSON 匯出（CLI `adept run` 輸出 features JSON 用）
## ---------------------------------------------------------------------------
#def _safe_num(v: Any) -> Optional[float]:
#    """float 化；nan/inf/ndarray/不可轉 → None（JSON 安全）。"""
#    if v is None:
#        return None
#    try:
#        f = float(v)
#    except (TypeError, ValueError):
#        return None
#    if math.isnan(f) or math.isinf(f):
#        return None
#    return f
#
#
#def result_to_json_dict(r: DefectResult) -> Dict[str, Any]:
#    """DefectResult → 可直接 ``json.dumps`` 的 dict。
#
#    不含 ndarray、不含 context；nan/inf → None；ms 取 3 位小數。
#    """
#    return {
#        "defect_id": r.defect_id,
#        "ok": bool(r.ok),
#        "error": r.error,
#        "features": {k: _safe_num(v) for k, v in r.features.items()},
#        "score": _safe_num(r.score),
#        "bin": None if r.bin is None else int(r.bin),
#        "traces": [
#            {
#                "node_id": t.node_id,
#                "step_key": t.step_key,
#                "ok": bool(t.ok),
#                "ms": round(float(t.ms), 3),
#                "error": t.error,
#                "features_added": {k: _safe_num(v)
#                                   for k, v in t.features_added.items()},
#                "images_after": [str(x) for x in t.images_after],
#            }
#            for t in r.traces
#        ],
#    }
#
#F e8903f84ee1104d66e67f528d0e4ea2951204dea 488 adept/core/pipeline/expression.py
## ADEPT pipeline engine — authored 2026-07-28 (M1).
#"""Score 表達式引擎：手寫 tokenizer → 遞迴下降 parser → AST → evaluator。
#
#設計（見 docs/plans/F0-master-plan.md §4）：
#- 變數 = Context.features 的 key（snr_max、cd_x_nm、glv_mean_roi1…）。
#- 運算元：``+ - * / **``、比較 ``> < >= <= == !=``、布林 ``and or not``、
#  函數 ``sqrt log abs exp``（1 個參數）與 ``min max``（至少 1 個參數）。
#- 比較採**左結合折疊**：``a < b < c`` 解讀為 ``(a < b) < c``，
#  **不是** Python 的鏈式比較（v1 刻意如此，語意單純）。
#- ``**`` 右結合、優先度高於一元負號（``-2**2 == -4``、``2**-1`` 合法）。
#
#SAFE 語意（inline 調參不炸批次的鐵則）：
#- 除以 0 → 0.0；log(≤0) → 0.0；sqrt(<0) → 0.0；
#  0 的負次方 → 0.0；負數的非整數次方 → 0.0。
#- 最終結果為 nan/inf → 0.0。
#- 例外：**變數不存在**與**變數值不是數字**會 raise ExpressionError
#  （這是 recipe 寫錯，不是資料髒 —— 要讓使用者看到）。
#
#錯誤訊息以繁體中文白話呈現，附 caret（^）指出出錯位置，
#非工程師同事也能看懂哪裡打錯了。
#"""
#from __future__ import annotations
#
#import math
#from typing import Any, FrozenSet, List, Mapping, Set, Tuple
#
#__all__ = ["ExpressionError", "Expression", "parse_expression"]
#
## 訊息中表達式行的縮排（測試依賴此常數對 caret 位置做驗證）
#_INDENT = "    "
#
## 固定參數個數的函數；min/max 為至少 1 個參數
#_FIXED_ARITY = {"sqrt": 1, "log": 1, "abs": 1, "exp": 1}
#_VARIADIC = ("min", "max")
#_KEYWORDS = ("and", "or", "not")
#_CMP_OPS = (">", "<", ">=", "<=", "==", "!=")
#_TWO_CHAR_OPS = ("**", ">=", "<=", "==", "!=")
#
#
#class ExpressionError(ValueError):
#    """表達式錯誤：``.pos`` 為出錯的字元位置（0 起算），
#    訊息共三行 —— 白話說明、原始表達式、caret（^）指位。"""
#
#    def __init__(self, desc: str, text: str = "", pos: int = 0):
#        self.desc = desc
#        self.text = text
#        self.pos = max(0, int(pos))
#        msg = (
#            f"Problem in the score expression (near character "
#            f"{self.pos + 1}): {desc}\n"
#            f"{_INDENT}{text}\n"
#            f"{_INDENT}{' ' * self.pos}^"
#        )
#        super().__init__(msg)
#
#
## ---------------------------------------------------------------------------
## Tokenizer
## ---------------------------------------------------------------------------
## token = (kind, value, pos)；kind ∈ {"num","name","op","lparen","rparen","comma","end"}
#_Token = Tuple[str, Any, int]
#
#
#def _tokenize(text: str) -> List[_Token]:
#    toks: List[_Token] = []
#    i, n = 0, len(text)
#    while i < n:
#        c = text[i]
#        if c in " \t\r\n":
#            i += 1
#            continue
#        # ---- 數字（int/float，支援 1.5、.5、2.、1e3、1.2e-3）----
#        if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
#            start = i
#            while i < n and text[i].isdigit():
#                i += 1
#            if i < n and text[i] == ".":
#                i += 1
#                while i < n and text[i].isdigit():
#                    i += 1
#            if i < n and text[i] in "eE":
#                j = i + 1
#                if j < n and text[j] in "+-":
#                    j += 1
#                if j < n and text[j].isdigit():
#                    i = j
#                    while i < n and text[i].isdigit():
#                        i += 1
#                else:
#                    raise ExpressionError(
#                        "scientific notation (e) must be followed by digits, "
#                        "e.g. 1e3", text, i)
#            toks.append(("num", float(text[start:i]), start))
#            continue
#        # ---- 識別字 / 關鍵字 ----
#        if c.isalpha() or c == "_":
#            start = i
#            while i < n and (text[i].isalnum() or text[i] == "_"):
#                i += 1
#            toks.append(("name", text[start:i], start))
#            continue
#        # ---- 雙字元運算子優先 ----
#        two = text[i:i + 2]
#        if two in _TWO_CHAR_OPS:
#            toks.append(("op", two, i))
#            i += 2
#            continue
#        if c in "+-*/><":
#            toks.append(("op", c, i))
#            i += 1
#            continue
#        if c == "(":
#            toks.append(("lparen", c, i))
#            i += 1
#            continue
#        if c == ")":
#            toks.append(("rparen", c, i))
#            i += 1
#            continue
#        if c == ",":
#            toks.append(("comma", c, i))
#            i += 1
#            continue
#        if c == "=":
#            raise ExpressionError(
#                "a single '=' cannot be used to compare; write 'equals' as "
#                "'=='", text, i)
#        if c == "!":
#            raise ExpressionError(
#                "'!' cannot be used on its own; write 'not equal' as '!='",
#                text, i)
#        raise ExpressionError(f"unrecognised character '{c}'", text, i)
#    toks.append(("end", "", n))
#    return toks
#
#
## ---------------------------------------------------------------------------
## Parser（遞迴下降；AST 用 tuple 表示，可 pickle）
##
## 文法（低優先度 → 高優先度）：
##   expr    := or
##   or      := and ("or" and)*
##   and     := not ("and" not)*
##   not     := "not" not | cmp
##   cmp     := arith (CMPOP arith)*          ← 左結合折疊，非鏈式
##   arith   := term (("+"|"-") term)*
##   term    := unary (("*"|"/") unary)*
##   unary   := "-" unary | power
##   power   := atom ("**" unary)?            ← 右結合；-2**2 == -(2**2)
##   atom    := NUM | NAME | NAME "(" args ")" | "(" expr ")"
## ---------------------------------------------------------------------------
#class _Parser:
#    def __init__(self, text: str):
#        self.text = text
#        self.toks = _tokenize(text)
#        self.i = 0
#
#    def _peek(self) -> _Token:
#        return self.toks[self.i]
#
#    def _next(self) -> _Token:
#        t = self.toks[self.i]
#        self.i += 1
#        return t
#
#    def _is_name(self, word: str) -> bool:
#        kind, val, _ = self._peek()
#        return kind == "name" and val == word
#
#    # ---- 進入點 -----------------------------------------------------------
#    def parse(self) -> tuple:
#        kind, _, pos = self._peek()
#        if kind == "end":
#            raise ExpressionError(
#                "the expression is empty — enter a formula such as "
#                "snr_max * 2", self.text, pos)
#        node = self.parse_or()
#        kind, _, pos = self._peek()
#        if kind != "end":
#            raise ExpressionError(
#                "the expression should have ended here; there is extra content "
#                "after it", self.text, pos)
#        return node
#
#    # ---- 各優先度層 -------------------------------------------------------
#    def parse_or(self) -> tuple:
#        node = self.parse_and()
#        while self._is_name("or"):
#            self._next()
#            node = ("bool", "or", node, self.parse_and())
#        return node
#
#    def parse_and(self) -> tuple:
#        node = self.parse_not()
#        while self._is_name("and"):
#            self._next()
#            node = ("bool", "and", node, self.parse_not())
#        return node
#
#    def parse_not(self) -> tuple:
#        if self._is_name("not"):
#            self._next()
#            return ("not", self.parse_not())
#        return self.parse_cmp()
#
#    def parse_cmp(self) -> tuple:
#        node = self.parse_arith()
#        while True:
#            kind, val, _ = self._peek()
#            if kind == "op" and val in _CMP_OPS:
#                self._next()
#                node = ("cmp", val, node, self.parse_arith())  # 左結合折疊
#            else:
#                return node
#
#    def parse_arith(self) -> tuple:
#        node = self.parse_term()
#        while True:
#            kind, val, _ = self._peek()
#            if kind == "op" and val in ("+", "-"):
#                self._next()
#                node = ("bin", val, node, self.parse_term())
#            else:
#                return node
#
#    def parse_term(self) -> tuple:
#        node = self.parse_unary()
#        while True:
#            kind, val, _ = self._peek()
#            if kind == "op" and val in ("*", "/"):
#                self._next()
#                node = ("bin", val, node, self.parse_unary())
#            else:
#                return node
#
#    def parse_unary(self) -> tuple:
#        kind, val, _ = self._peek()
#        if kind == "op" and val == "-":
#            self._next()
#            return ("neg", self.parse_unary())
#        return self.parse_power()
#
#    def parse_power(self) -> tuple:
#        base = self.parse_atom()
#        kind, val, _ = self._peek()
#        if kind == "op" and val == "**":
#            self._next()
#            # 指數走 unary → 右結合，且 2**-1 合法
#            return ("bin", "**", base, self.parse_unary())
#        return base
#
#    def parse_atom(self) -> tuple:
#        kind, val, pos = self._next()
#        if kind == "num":
#            return ("num", float(val))
#        if kind == "name" and val not in _KEYWORDS:
#            k2, _, _ = self._peek()
#            if k2 == "lparen":
#                return self.parse_call(str(val), pos)
#            return ("var", str(val), pos)
#        if kind == "lparen":
#            node = self.parse_or()
#            k2, _, p2 = self._peek()
#            if k2 != "rparen":
#                raise ExpressionError("missing a closing bracket ')'", self.text, p2)
#            self._next()
#            return node
#        raise ExpressionError(
#            "a number, a variable or an opening bracket is expected here",
#            self.text, pos)
#
#    def parse_call(self, name: str, name_pos: int) -> tuple:
#        if name not in _FIXED_ARITY and name not in _VARIADIC:
#            raise ExpressionError(
#                f"'{name}' is not a supported function "
#                f"(supported: abs, exp, log, max, min, sqrt)",
#                self.text, name_pos)
#        self._next()  # 吃掉 '('
#        args: List[tuple] = []
#        kind, _, _ = self._peek()
#        if kind == "rparen":
#            self._next()
#        else:
#            while True:
#                args.append(self.parse_or())
#                kind, _, pos = self._peek()
#                if kind == "comma":
#                    self._next()
#                    continue
#                if kind == "rparen":
#                    self._next()
#                    break
#                raise ExpressionError(
#                    "function arguments must be separated by commas and end "
#                    "with a closing bracket ')'", self.text, pos)
#        # ---- 參數個數在「解析期」就檢查，不等執行才爆 ----
#        if name in _FIXED_ARITY and len(args) != _FIXED_ARITY[name]:
#            raise ExpressionError(
#                f"function {name}() takes 1 argument, but {len(args)} were "
#                f"given",
#                self.text, name_pos)
#        if name in _VARIADIC and len(args) < 1:
#            raise ExpressionError(
#                f"function {name}() needs at least 1 argument", self.text,
#                name_pos)
#        return ("call", name, tuple(args))
#
#
## ---------------------------------------------------------------------------
## Evaluator（SAFE 語意）
## ---------------------------------------------------------------------------
#def _truthy(v: float) -> bool:
#    return v != 0.0
#
#
#def _safe_pow(a: float, b: float) -> float:
#    """SAFE 次方：0 的負次方 → 0.0；負底非整數次方 → 0.0；溢位 → inf。"""
#    if a == 0.0 and b < 0.0:
#        return 0.0
#    if a < 0.0 and math.isfinite(b) and b != math.floor(b):
#        return 0.0
#    try:
#        return float(a ** b)
#    except OverflowError:
#        # 結果太大：以 inf 代表，最終結果層會安全歸零
#        neg = a < 0.0 and math.isfinite(b) and (math.floor(b) % 2 == 1)
#        return -math.inf if neg else math.inf
#
#
#def _safe_call(name: str, args: List[float]) -> float:
#    if name == "sqrt":
#        x = args[0]
#        return math.sqrt(x) if x >= 0.0 else 0.0
#    if name == "log":
#        x = args[0]
#        return math.log(x) if x > 0.0 else 0.0
#    if name == "abs":
#        return abs(args[0])
#    if name == "exp":
#        try:
#            return math.exp(args[0])
#        except OverflowError:
#            return math.inf
#    if name == "min":
#        return float(min(args))
#    if name == "max":
#        return float(max(args))
#    raise ExpressionError(f"'{name}' is not a supported function")  # pragma: no cover — parser 已擋
#
#
#def _lookup_var(name: str, pos: int, variables: Mapping[str, Any], text: str) -> float:
#    try:
#        v = variables[name]
#    except (KeyError, TypeError):
#        avail = (", ".join(sorted(variables)) if variables
#             else "(no variables are available yet)")
#        raise ExpressionError(
#            f"variable '{name}' not found; available variables: {avail}",
#            text, pos) from None
#    if isinstance(v, bool):
#        return 1.0 if v else 0.0
#    if v is None or isinstance(v, (str, bytes)):
#        raise ExpressionError(
#            f"variable '{name}' is not a number (got {type(v).__name__}: "
#            f"{v!r}) — check that the upstream card really produces this "
#            f"feature", text, pos)
#    try:
#        return float(v)
#    except (TypeError, ValueError):
#        raise ExpressionError(
#            f"variable '{name}' is not a number (got {type(v).__name__}) — "
#            f"check that the upstream card really produces this feature",
#            text, pos) from None
#
#
#def _eval(node: tuple, variables: Mapping[str, Any], text: str) -> float:
#    tag = node[0]
#    if tag == "num":
#        return float(node[1])
#    if tag == "var":
#        return _lookup_var(node[1], node[2], variables, text)
#    if tag == "neg":
#        return -_eval(node[1], variables, text)
#    if tag == "not":
#        return 0.0 if _truthy(_eval(node[1], variables, text)) else 1.0
#    if tag == "bool":
#        op, lhs, rhs = node[1], node[2], node[3]
#        lv = _truthy(_eval(lhs, variables, text))
#        rv = _truthy(_eval(rhs, variables, text))
#        if op == "and":
#            return 1.0 if (lv and rv) else 0.0
#        return 1.0 if (lv or rv) else 0.0
#    if tag == "cmp":
#        op, lhs, rhs = node[1], node[2], node[3]
#        lv = _eval(lhs, variables, text)
#        rv = _eval(rhs, variables, text)
#        if op == ">":
#            ok = lv > rv
#        elif op == "<":
#            ok = lv < rv
#        elif op == ">=":
#            ok = lv >= rv
#        elif op == "<=":
#            ok = lv <= rv
#        elif op == "==":
#            ok = lv == rv
#        else:  # "!="
#            ok = lv != rv
#        return 1.0 if ok else 0.0
#    if tag == "bin":
#        op, lhs, rhs = node[1], node[2], node[3]
#        lv = _eval(lhs, variables, text)
#        rv = _eval(rhs, variables, text)
#        if op == "+":
#            return lv + rv
#        if op == "-":
#            return lv - rv
#        if op == "*":
#            return lv * rv
#        if op == "/":
#            return lv / rv if rv != 0.0 else 0.0  # SAFE：除以 0 → 0.0
#        if op == "**":
#            return _safe_pow(lv, rv)
#    if tag == "call":
#        args = [_eval(a, variables, text) for a in node[2]]
#        return _safe_call(node[1], args)
#    raise ExpressionError(f"internal error: unknown AST node {tag!r}")  # pragma: no cover
#
#
#def _collect_vars(node: tuple, out: Set[str]) -> None:
#    tag = node[0]
#    if tag == "var":
#        out.add(node[1])
#    elif tag in ("neg", "not"):
#        _collect_vars(node[1], out)
#    elif tag in ("bool", "cmp", "bin"):
#        _collect_vars(node[2], out)
#        _collect_vars(node[3], out)
#    elif tag == "call":
#        for a in node[2]:
#            _collect_vars(a, out)
#
#
## ---------------------------------------------------------------------------
## 公開 API
## ---------------------------------------------------------------------------
#class Expression:
#    """已解析的表達式：``variables`` 列出用到的變數、``eval`` 求值。"""
#
#    __slots__ = ("text", "_ast", "_vars")
#
#    def __init__(self, text: str, ast: tuple, variables: Set[str]):
#        self.text = text
#        self._ast = ast
#        self._vars: FrozenSet[str] = frozenset(variables)
#
#    @property
#    def variables(self) -> FrozenSet[str]:
#        """表達式中用到的所有變數名（不含函數名）。"""
#        return self._vars
#
#    def eval(self, vars: Mapping[str, Any]) -> float:
#        """以 ``vars``（通常是 Context.features）求值。
#
#        比較與布林運算回傳 1.0/0.0；最終結果為 nan/inf 一律歸 0.0。
#        變數不存在或值不是數字會 raise :class:`ExpressionError`。
#        """
#        result = float(_eval(self._ast, vars if vars is not None else {}, self.text))
#        if math.isnan(result) or math.isinf(result):
#            return 0.0
#        return result
#
#    def __repr__(self) -> str:  # pragma: no cover
#        return f"Expression({self.text!r})"
#
#
#def parse_expression(text: str) -> Expression:
#    """解析表達式文字；語法錯誤 raise :class:`ExpressionError`（含 caret 指位）。"""
#    if not isinstance(text, str):
#        raise ExpressionError(
#            f"the expression must be text, got {type(text).__name__}",
#            str(text), 0)
#    parser = _Parser(text)
#    ast = parser.parse()
#    names: Set[str] = set()
#    _collect_vars(ast, names)
#    return Expression(text, ast, names)
#
#F c75cc58347ed6cb834a0bfab4c4cedc070c96dab 532 adept/core/pipeline/recipe.py
## ADEPT pipeline engine — authored 2026-07-28 (M1).
#"""Recipe 模型：DAG JSON serde、執行順序（拓撲排序）、lint 式驗證。
#
#Recipe JSON 形狀（見 docs/plans/F0-master-plan.md §3.4）：
#
#.. code-block:: json
#
#    {
#      "recipe_id": "M1_EBI_bridge", "version": 3, "author": "HX",
#      "description": "...",
#      "routes": {"ebi_patch": ["load","align","subtract","snr"],
#                 "rsem":      ["load","golden","subtract","snr"]},
#      "nodes": {"align": {"step": "align", "params": {"method": "phase"},
#                          "enabled": true}},
#      "edges": [["subtract","snr"]],
#      "score": {"expr": "snr_max * sqrt(blob_area)", "threshold": 3.0,
#                "bins": {"below": 0, "above": 1}}
#    }
#
#- v1 每條 route 是線性鏈；``edges`` 是額外的 DAG 邊（v2 自由畫布備用）。
#  執行順序 = route 相鄰對邊 ∪ edges（限制在該 route 內）的 Kahn 拓撲排序，
#  平手時依 route 位置決定（deterministic）。
#- 驗證走 lint 模式（KLIP ``Issue`` 結構）：一次列出**所有**問題，
#  不是碰到第一個就停。
#"""
#from __future__ import annotations
#
#import heapq
#import json
#import os
#from dataclasses import dataclass, field
#from typing import Any, Dict, List, Optional, Set, Type
#
#from .expression import ExpressionError, parse_expression
#from .step import ParamError, Step, REGISTRY
#
#__all__ = [
#    "RecipeError", "RecipeNode", "ScoreSpec", "Recipe",
#    "Issue", "execution_order", "validate",
#]
#
#
#class RecipeError(ValueError):
#    """Recipe 結構性錯誤（循環、未知 route、JSON 缺欄位…）。"""
#
#
## ---------------------------------------------------------------------------
## 資料模型
## ---------------------------------------------------------------------------
#@dataclass
#class RecipeNode:
#    """pipeline 上的一張卡：``id`` 節點名、``step`` 卡片 key、``params`` 參數。"""
#    id: str
#    step: str
#    params: Dict[str, Any]
#    enabled: bool = True
#
#
#@dataclass
#class ScoreSpec:
#    """ADC 判定段：score 表達式 + 門檻 + bin 對應（{"below": 0, "above": 1}）。"""
#    expr: str
#    threshold: float
#    bins: Dict[str, int]
#
#
## ---------------------------------------------------------------------------
## 舊 recipe 相容遷移（F7-18）：``also_apply`` → 一張卡一條流
## ---------------------------------------------------------------------------
##: 哪些卡片以前有 ``also_apply``，以及它們的主要影像流參數叫什麼。
#_ALSO_APPLY_CARDS: Dict[str, str] = {
#    "percentile_norm": "source",
#    "glv_mask_norm": "source",
#    "denoise": "target",
#    "flatten": "target",
#    "local_contrast": "target",
#    "brightness_contrast": "target",
#    "gamma": "target",
#}
#
##: 這兩張卡另外還有 ``anchor``：``source`` = 其他流借主流量出來的拉伸範圍。
##: 那個能力現在叫 ``range_from``（一條影像流的名字），所以遷移得動兩個參數。
#_ANCHOR_CARDS = ("percentile_norm", "glv_mask_norm")
#
#
#def _fresh_id(taken: Dict[str, Any], base: str) -> str:
#    nid = base
#    i = 2
#    while nid in taken:
#        nid = "%s_%d" % (base, i)
#        i += 1
#    return nid
#
#
#def _migrate_also_apply(nodes: Dict[str, "RecipeNode"],
#                        routes: Dict[str, List[str]]) -> None:
#    """把 ``also_apply`` 展開成一張卡一條流（就地改寫 nodes 與 routes）。
#
#    為什麼要遷移而不是直接不認得
#    ----------------------------
#    ``also_apply`` 是使用者存在磁碟上的 recipe 裡的字，而 recipe 是拿來交接的
#    東西。認不得它會讓一份跑得好好的檔案在升級之後變成 ``unknown parameters``
#    —— 對不會寫 code 的人那就是「工具壞了」。
#
#    為什麼順序看 ``anchor``
#    -----------------------
#    ``anchor="source"`` 的語意是「ref 用 **test 原本的** 灰階範圍」。拆成兩張卡
#    之後，如果 test 那張先跑，它會把 test 拉成 0–255，ref 那張再去借就借到
#    「拉伸後」的範圍 —— 數字不一樣，而畫面上兩者都是一張看起來正常的圖。
#    所以 ``anchor="source"`` 時把借範圍的那幾張排在**前面**，此時主流還沒被改過，
#    輸出與舊版逐位元組相同。``anchor="self"`` 沒有這個相依，維持原順序。
#    """
#    extra: Dict[str, tuple] = {}          # 原節點 id -> (新節點 ids, 要不要排前面)
#    for nid, node in list(nodes.items()):
#        primary_name = _ALSO_APPLY_CARDS.get(node.step)
#        if primary_name is None:
#            continue
#        params = dict(node.params)
#        if "also_apply" not in params and "anchor" not in params:
#            continue
#        also_raw = params.pop("also_apply", "")
#        anchor = params.pop("anchor", None)
#        primary = str(params.get(primary_name, "") or "")
#        also: List[str] = []
#        for tok in str(also_raw or "").split(","):
#            tok = tok.strip()
#            if tok and tok != primary and tok not in also:
#                also.append(tok)
#        borrow = node.step in _ANCHOR_CARDS and str(anchor or "source") == "source"
#        if node.step in _ANCHOR_CARDS:
#            params.setdefault("range_from", "")
#        node.params = params
#
#        made: List[str] = []
#        for stream in also:
#            new_id = _fresh_id(nodes, "%s_%s" % (nid, stream))
#            p = dict(params)
#            p[primary_name] = stream
#            if node.step in _ANCHOR_CARDS:
#                p["range_from"] = primary if borrow else ""
#            nodes[new_id] = RecipeNode(id=new_id, step=node.step, params=p,
#                                       enabled=node.enabled)
#            made.append(new_id)
#        if made:
#            extra[nid] = (made, borrow)
#
#    if not extra:
#        return
#    for k, route in list(routes.items()):
#        out: List[str] = []
#        for nid in route:
#            made, first = extra.get(nid, ([], False))
#            if first:
#                out.extend(made)
#                out.append(nid)
#            else:
#                out.append(nid)
#                out.extend(made)
#        routes[k] = out
#
#
#@dataclass
#class Recipe:
#    """一份完整 recipe（單一 JSON 檔可互傳）。"""
#    recipe_id: str
#    routes: Dict[str, List[str]]      # dataset kind → 依序的節點 id（v1 線性）
#    nodes: Dict[str, RecipeNode]
#    score: ScoreSpec
#    version: int = 1
#    author: str = ""
#    description: str = ""
#    edges: List[List[str]] = field(default_factory=list)  # 額外 DAG 邊
#
#    # ---- JSON serde -------------------------------------------------------
#    def to_json_dict(self) -> Dict[str, Any]:
#        return {
#            "recipe_id": self.recipe_id,
#            "version": int(self.version),
#            "author": self.author,
#            "description": self.description,
#            "routes": {k: list(v) for k, v in self.routes.items()},
#            "nodes": {
#                nid: {
#                    "step": n.step,
#                    "params": dict(n.params),
#                    "enabled": bool(n.enabled),
#                }
#                for nid, n in self.nodes.items()
#            },
#            "edges": [list(e) for e in self.edges],
#            "score": {
#                "expr": self.score.expr,
#                "threshold": float(self.score.threshold),
#                "bins": dict(self.score.bins),
#            },
#        }
#
#    @classmethod
#    def from_json_dict(cls, d: Dict[str, Any]) -> "Recipe":
#        if not isinstance(d, dict):
#            raise RecipeError(f"the top level of a recipe JSON must be an object "
#                              f"(dict), got {type(d).__name__}")
#        missing = [k for k in ("recipe_id", "routes", "nodes", "score") if k not in d]
#        if missing:
#            raise RecipeError(f"recipe JSON is missing required fields: {missing}")
#
#        nodes: Dict[str, RecipeNode] = {}
#        for nid, nd in dict(d["nodes"]).items():
#            if not isinstance(nd, dict) or "step" not in nd:
#                raise RecipeError(f"step '{nid}' has no 'step' field")
#            nodes[str(nid)] = RecipeNode(
#                id=str(nid),
#                step=str(nd["step"]),
#                params=dict(nd.get("params") or {}),
#                enabled=bool(nd.get("enabled", True)),
#            )
#
#        sd = d["score"]
#        if not isinstance(sd, dict) or "expr" not in sd:
#            raise RecipeError(
#                "the score block must be an object containing 'expr'")
#        score = ScoreSpec(
#            expr=str(sd["expr"]),
#            threshold=float(sd.get("threshold", 0.0)),
#            bins={str(k): int(v) for k, v in dict(sd.get("bins") or {}).items()},
#        )
#
#        routes = {str(k): [str(x) for x in v] for k, v in dict(d["routes"]).items()}
#
#        edges: List[List[str]] = []
#        for e in (d.get("edges") or []):
#            e = list(e)
#            if len(e) != 2:
#                raise RecipeError(f"an edge must be [from, to] — two step ids; got: {e}")
#            edges.append([str(e[0]), str(e[1])])
#
#        # 舊 recipe（F7-18 之前）的 also_apply / anchor：展開成一張卡一條流。
#        # 做在這裡而不是各張卡的 validate_params 裡，因為它會**增加節點**——
#        # 那是 recipe 層級的事，一張卡看不到自己以外的東西。
#        _migrate_also_apply(nodes, routes)
#
#        return cls(
#            recipe_id=str(d["recipe_id"]),
#            routes=routes,
#            nodes=nodes,
#            score=score,
#            version=int(d.get("version", 1)),
#            author=str(d.get("author", "")),
#            description=str(d.get("description", "")),
#            edges=edges,
#        )
#
#    def save(self, path: Any) -> None:
#        """寫入 JSON 檔（utf-8、indent=2、atomic ``.tmp`` + ``os.replace``）。"""
#        path = str(path)
#        tmp = path + ".tmp"
#        with open(tmp, "w", encoding="utf-8") as f:
#            json.dump(self.to_json_dict(), f, ensure_ascii=False, indent=2)
#            f.write("\n")
#        os.replace(tmp, path)
#
#    @classmethod
#    def load(cls, path: Any) -> "Recipe":
#        with open(str(path), "r", encoding="utf-8") as f:
#            d = json.load(f)
#        return cls.from_json_dict(d)
#
#
## ---------------------------------------------------------------------------
## 執行順序（Kahn 拓撲排序，平手依 route 位置 → deterministic）
## ---------------------------------------------------------------------------
#def execution_order(recipe: Recipe, kind: str) -> List[str]:
#    """回傳 ``kind`` 這條 route 的節點執行順序。
#
#    邊 = route 相鄰對（load→norm→align…）∪ 顯式 ``edges``（兩端都在該
#    route 內才算）。循環或未知 kind → :class:`RecipeError`。
#    """
#    if kind not in recipe.routes:
#        raise RecipeError(
#            f"unknown input-type route '{kind}'; this recipe only defines: "
#            f"{sorted(recipe.routes)}")
#    route = list(recipe.routes[kind])
#    if not route:
#        return []
#    pos = {nid: i for i, nid in enumerate(route)}
#    node_set = set(route)
#
#    pair_edges: Set[tuple] = set()
#    for a, b in zip(route, route[1:]):
#        pair_edges.add((a, b))
#    for e in recipe.edges:
#        if len(e) == 2 and e[0] in node_set and e[1] in node_set:
#            pair_edges.add((e[0], e[1]))  # 自迴圈也收進來 → Kahn 會偵測為循環
#
#    indeg = {n: 0 for n in route}
#    adj: Dict[str, List[str]] = {n: [] for n in route}
#    for a, b in pair_edges:
#        adj[a].append(b)
#        indeg[b] += 1
#
#    heap = [pos[n] for n in route if indeg[n] == 0]
#    heapq.heapify(heap)
#    out: List[str] = []
#    while heap:
#        n = route[heapq.heappop(heap)]
#        out.append(n)
#        for m in sorted(adj[n], key=lambda x: pos[x]):
#            indeg[m] -= 1
#            if indeg[m] == 0:
#                heapq.heappush(heap, pos[m])
#    if len(out) != len(route):
#        stuck = [n for n in route if n not in out]
#        raise RecipeError(
#            f"route '{kind}' has a cycle in its step connections, so no "
#            f"execution order can be determined; stuck steps: {stuck}")
#    return out
#
#
## ---------------------------------------------------------------------------
## lint 式驗證（KLIP Issue 風格：一次列出所有問題）
## ---------------------------------------------------------------------------
#@dataclass
#class Issue:
#    """一條驗證發現：``level`` 為 "error" 或 "warning"。"""
#    code: str
#    level: str
#    node_id: Optional[str]
#    title: str
#    detail: str
#
#
#def _clean_params_for(step_cls: Type[Step], raw: Dict[str, Any],
#                      issues: List[Issue], nid: str) -> Dict[str, Any]:
#    """驗證參數；壞參數記 Issue 並改用預設值，讓後續模擬檢查照常進行。"""
#    try:
#        return step_cls.validate_params(raw)
#    except ParamError as e:
#        issues.append(Issue(
#            code="bad-param", level="error", node_id=nid,
#            title="Invalid parameter", detail=str(e)))
#        try:
#            return step_cls.validate_params(None)  # 全預設值
#        except ParamError:  # pragma: no cover — 預設值本身壞掉屬程式錯誤
#            return {}
#
#
#def validate(recipe: Recipe, kind: Optional[str] = None,
#             registry: Optional[Dict[str, Type[Step]]] = None) -> List[Issue]:
#    """lint 式驗證：收集**所有**問題後一次回傳（不會 raise）。
#
#    檢查項（code）：unknown-step / bad-param / not-configured / unknown-node /
#    unknown-route / cycle / missing-image / unknown-region / requires-ref /
#    score-expr / unknown-feature（warning）/ feature-collision（warning）/
#    bad-bins。
#    """
#    if registry is None:
#        registry = REGISTRY
#    issues: List[Issue] = []
#
#    # ---- bins 必須含 below / above ----
#    bins = recipe.score.bins or {}
#    for key in ("below", "above"):
#        if key not in bins:
#            issues.append(Issue(
#                code="bad-bins", level="error", node_id=None,
#                title="Incomplete bin settings",
#                detail=f"score.bins has no '{key}' (both below and above bin "
#                       f"values are required); it currently has: "
#                       f"{sorted(bins)}"))
#
#    # ---- 要檢查哪些 route ----
#    if kind is not None:
#        if kind not in recipe.routes:
#            issues.append(Issue(
#                code="unknown-route", level="error", node_id=None,
#                title=f"Unknown input-type route '{kind}'",
#                detail=f"this recipe only defines routes: "
#                       f"{sorted(recipe.routes)}"))
#            kinds: List[str] = []
#        else:
#            kinds = [kind]
#    else:
#        kinds = list(recipe.routes)
#
#    # ---- 每個節點：step 存在？參數合法？----
#    clean_params: Dict[str, Dict[str, Any]] = {}
#    for nid, node in recipe.nodes.items():
#        step_cls = registry.get(node.step)
#        if step_cls is None:
#            issues.append(Issue(
#                code="unknown-step", level="error", node_id=nid,
#                title=f"Unknown card '{node.step}'",
#                detail=f"step '{nid}' uses '{node.step}', which is not in the "
#                       f"card library; available cards: {sorted(registry)}"))
#            continue
#        clean_params[nid] = _clean_params_for(step_cls, node.params, issues, nid)
#
#        # 參數全部合法，卡片還是可能**沒設定完**（F7-13）。空字串的模板是完全
#        # 合法的 str —— 但那張卡跑起來每一顆都會失敗，而以前要跑過一次才知道。
#        try:
#            unset = list(step_cls.configuration_issues(clean_params[nid]))
#        except Exception:                       # noqa: BLE001 — 卡片自己的程式
#            unset = []
#        for msg in unset:
#            issues.append(Issue(
#                code="not-configured", level="error", node_id=nid,
#                title=f"{step_cls.label} is not set up yet", detail=str(msg)))
#
#    # ---- score 表達式解析 ----
#    expr = None
#    try:
#        expr = parse_expression(recipe.score.expr)
#    except ExpressionError as e:
#        issues.append(Issue(
#            code="score-expr", level="error", node_id=None,
#            title="Score expression failed to parse", detail=str(e)))
#
#    # ---- 每條 route：unknown-node / cycle / reads 模擬 / requires_ref ----
#    for k in kinds:
#        route = recipe.routes[k]
#        for nid in route:
#            if nid not in recipe.nodes:
#                issues.append(Issue(
#                    code="unknown-node", level="error", node_id=nid,
#                    title=f"route '{k}' refers to a step that does not exist: "
#                          f"'{nid}'",
#                    detail=f"nodes has no '{nid}'; defined steps: "
#                           f"{sorted(recipe.nodes)}"))
#        try:
#            order = execution_order(recipe, k)
#        except RecipeError as e:
#            issues.append(Issue(
#                code="cycle", level="error", node_id=None,
#                title=f"route '{k}' has a cycle in its step connections",
#                detail=str(e)))
#            continue
#
#        # reads-satisfaction 模擬：seed = 第一張啟用卡（load 卡）的 writes；
#        # 之後每張卡 reads 必須 ⊆ 累積 writes。停用節點跳過（與 runtime 一致）。
#        avail: Set[str] = set()
#        feats: Set[str] = {"score"}
#        regions: Set[str] = set()
#        #: feature 名 -> 第一個產出它的節點。特徵是**扁平的全域命名空間**，
#        #: 所以兩張同型別的量測卡（例如量兩個 ROI 的 glv_stats）會寫同一組名字，
#        #: 後面那張安靜地蓋掉前面那張 —— 跑得完、有數字、少一半。
#        feat_owner: Dict[str, str] = {}
#        first = True
#        for nid in order:
#            node = recipe.nodes.get(nid)
#            if node is None or not node.enabled:
#                continue
#            step_cls = registry.get(node.step)
#            if step_cls is None:
#                continue  # 已記 unknown-step
#            p = clean_params.get(nid, {})
#            if first:
#                # 第一張卡（load）：reads / requires_ref 不檢查；
#                # writes 用 kind-aware 宣告（load 卡依資料型別決定會有哪些流）
#                avail |= set(step_cls.resolve_writes_for_kind(p, k))
#                for f in step_cls.resolve_features(p):
#                    feat_owner.setdefault(f, nid)
#                feats |= set(step_cls.resolve_features(p))
#                regions |= set(step_cls.resolve_regions_out(p))
#                first = False
#                continue
#            missing = [x for x in step_cls.resolve_reads(p) if x not in avail]
#            if missing:
#                issues.append(Issue(
#                    code="missing-image", level="error", node_id=nid,
#                    title=f"step '{nid}' is missing an upstream image",
#                    detail=f"route '{k}': it needs image streams {missing}, but "
#                           f"upstream only provides {sorted(avail)}"))
#            if k == "rsem" and getattr(step_cls, "requires_ref", False) \
#                    and "ref" not in avail:
#                issues.append(Issue(
#                    code="requires-ref", level="error", node_id=nid,
#                    title=f"step '{nid}' needs a reference image",
#                    detail=f"'{node.step}' needs ref, but a single-image rsem "
#                           f"input has none and no upstream card produces "
#                           f"'ref' (currently provided: {sorted(avail)})"))
#            # 具名區域走跟影像流一樣的檢查（F7-9）。沒有這一段的話，
#            # 「量測卡指到沒人定義的區域」在跑之前是看不出來的 ——
#            # 名字打錯要等執行期 StepError，而預設的 'blob' 少了上游的
#            # Blob 卡更慘：它會安靜地退回量整張圖，跑得完、有數字、且是錯的。
#            missing_roi = [x for x in step_cls.resolve_regions_in(p)
#                           if x not in regions]
#            if missing_roi:
#                issues.append(Issue(
#                    code="unknown-region", level="error", node_id=nid,
#                    title=f"step '{nid}' uses a region nobody defines",
#                    detail=f"route '{k}': it measures region(s) {missing_roi}, "
#                           f"but no upstream card defines them (currently "
#                           f"defined: {sorted(regions)}). Add a Region card "
#                           f"upstream, or clear the roi parameter to measure "
#                           f"the whole image."))
#
#            # 特徵撞名：後面的卡會安靜地蓋掉前面的（Context.add_feature 允許
#            # 覆寫，只在 meta 留紀錄）。最典型的踩法是「量兩個 ROI」——
#            # 兩張 glv_stats 都寫 glv_mean，跑完只剩後面那張的值，而分數表達式
#            # 完全沒有辦法指到前面那一個。這是**警告**不是 error：同名覆寫有時
#            # 是刻意的（例如重跑一次 normalize），但它必須看得見。
#            for f in step_cls.resolve_features(p):
#                owner = feat_owner.get(f)
#                if owner is not None and owner != nid:
#                    issues.append(Issue(
#                        code="feature-collision", level="warning", node_id=nid,
#                        title=f"step '{nid}' overwrites the feature '{f}'",
#                        detail=f"route '{k}': '{f}' is already produced by "
#                               f"'{owner}'; the later value wins and the earlier "
#                               f"one cannot be referenced from the score "
#                               f"expression at all. Give one of the two cards a "
#                               f"different output name if you need both."))
#                else:
#                    feat_owner.setdefault(f, nid)
#
#            avail |= set(step_cls.resolve_writes(p))
#            feats |= set(step_cls.resolve_features(p))
#            regions |= set(step_cls.resolve_regions_out(p))
#
#        # score 變數 ⊆ 此 route 會產出的特徵 ∪ {"score"}（僅警告）
#        if expr is not None:
#            unknown = sorted(expr.variables - feats)
#            if unknown:
#                issues.append(Issue(
#                    code="unknown-feature", level="warning", node_id=None,
#                    title="Score expression uses unknown features",
#                    detail=f"route '{k}': the variables {unknown} are not among "
#                           f"the features this route produces ({sorted(feats)}), "
#                           f"so the score may not be computable at run time"))
#
#    return issues
#
#F 40461568b5d9317c6d90baf8b02c6bdbfbbb328c 362 adept/core/pipeline/step.py
## ADEPT pipeline contract — authored 2026-07-27 (M1).
#"""Step 介面 + ParamSpec + registry。
#
#一張「卡片」= 一個 Step 子類別：
#- 宣告 ``params``（每個參數都要有白話 ``help`` 與合理 ``default`` —— 推廣鐵則）
#- 宣告 reads / writes（影像流 key）與 features_out（會產出的特徵名）
#- 實作 ``run(ctx, params)``（純函數風格：吃 Context、回 Context）
#
#新算法 = 新 class + ``@register_step``，UI 與引擎零修改。
#
#分類（三段式，見 master plan §5）：
#- ``CATEGORY_IMAGE``  影像段（把圖變乾淨；寫 images）
#- ``CATEGORY_ALGO``   算法段（從圖量出數字；寫 features）
#- ``CATEGORY_ADC``    判定段（score / bin / 輸出）
#"""
#from __future__ import annotations
#
#import re
#from abc import ABC, abstractmethod
#from dataclasses import dataclass
#from typing import Any, ClassVar, Dict, List, Optional, Type
#
#from .context import Context
#from .curve import CurveError, format_curve, parse_curve
#
#CATEGORY_IMAGE = "image"
#CATEGORY_ALGO = "algo"
#CATEGORY_ADC = "adc"
#
## --------------------------------------------------------------------------- #
## 流程階段（F7-3）—— 卡片庫的分組依據
## --------------------------------------------------------------------------- #
##: ``category`` 分的是「這張卡吐什麼型別」（引擎用：快取切點、驗證順序）；
##: ``group`` 分的是「這張卡在解決什麼問題」（**使用者用**：卡片庫的分組）。
##:
##: 兩者是**獨立**的軸。舊 UI 直接拿 category 當分類，於是使用者看到的是
##: 「影像／算法」—— 那描述的是輸出型別，不是意圖，所以被評為「太武斷」。
##:
##: 每一段的規則是機械可判定的（吃什麼、吐什麼），新卡片放哪不需要討論：
##:
##: =============  =========================  ==============================
##: group          規則                       例
##: =============  =========================  ==============================
##: input          （固定頭節點）              load_patch
##: enhance        影像 → 影像                normalize / gamma / denoise
##: region         找出「要看哪裡」            snr_map / blob_segment / roi_define
##: compare        影像＋影像 → 影像           align / subtract
##: measure        影像＋區域 → 數字           glv_stats / cd_measure
##: adc            數字 → score → bin         （固定尾節點）
##: =============  =========================  ==============================
##:
##: **型別規則是預設的裁決方式，但不是唯一的。** ``snr_map`` 是影像進影像出，
##: 照型別會落在 enhance —— 但它的**唯一**消費者是 ``blob_segment``
##: （每一份範例 recipe 都是 snr → blob），而且它必須跑在 Compare 之後，
##: 放在讀起來排第二的 Enhance 裡永遠用不到。所以規則補一條：
##: **一張卡如果只為了餵另一段而存在，就跟著那一段走。**
#GROUP_INPUT = "input"
#GROUP_ENHANCE = "enhance"
#GROUP_REGION = "region"
#GROUP_COMPARE = "compare"
#GROUP_MEASURE = "measure"
#GROUP_ADC = "adc"
#
##: 卡片庫的顯示順序（讀起來是一句話：
##: Input → Enhance → Region → Compare → Measure → ADC）。
#GROUP_ORDER = (GROUP_INPUT, GROUP_ENHANCE, GROUP_REGION,
#               GROUP_COMPARE, GROUP_MEASURE, GROUP_ADC)
#_GROUPS = GROUP_ORDER
#_CATEGORIES = (CATEGORY_IMAGE, CATEGORY_ALGO, CATEGORY_ADC)
#
##: ``curve`` 是一個「值是控制點字串」的參數（見 ``pipeline/curve.py``）——
##: 跟 ``image_key`` 一樣，型別上就是 str，但 UI 認得它、會給專用編輯器。
##:
##: ``image_keys``（F7-9）是「一串影像流名」，值仍然是逗號分隔字串 ——
##: **recipe JSON 的格式沒有變**，舊檔照樣讀得進來。差別在 UI：它拿到的是
##: 上游每一條流的一個勾選框，而不是一個要自己打字、打錯只會靜靜警告的輸入框。
##: ``template``（F7-13）是一個「值是一整份資料、不是一句話」的參數 ——
##: 型別上仍是 str，但那個字串有六千多個字元，而且**沒有人能用打的**。
##: 一個放不下、也編輯不了的值配一個文字框，等於邀請使用者去改它。
##: UI 認得這個型別：它給的是「建一個」的按鈕加一行摘要，欄位本身唯讀。
#PARAM_TYPES = ("int", "float", "bool", "str", "choice", "image_key",
#               "image_keys", "curve", "template")
#
#
#class ParamError(ValueError):
#    """參數不合法（含參數名與原因，UI 直接顯示）。"""
#
#
#class StepError(RuntimeError):
#    """步驟執行失敗；engine 會攔截並記入該 defect 的結果，不會殺整批。"""
#
#    def __init__(self, step_key: str, msg: str):
#        super().__init__(f"[{step_key}] {msg}")
#        self.step_key = step_key
#
#
#@dataclass
#class ParamSpec:
#    """一個參數的完整描述 —— UI 表單由此自動生成。
#
#    ``help`` 必填：一行白話說明（不會寫 code 的人要能看懂）。
#    ``type=="choice"`` 需附 ``choices``；``type=="image_key"`` 表示值是影像流名稱，
#    UI 會提供下拉（目前 pipeline 上游的 writes 聯集）。
#
#    ``label``（F7-9，選填）是**顯示名**。``name`` 是 recipe JSON 的鍵，改不得；
#    但 ``also_apply`` 這種名字對製程工程師來說不是一句話。有 label 就顯示 label，
#    沒有就顯示 name —— 既有卡片一張都不用動。
#    """
#
#    name: str
#    type: str
#    default: Any
#    help: str
#    min: Optional[float] = None
#    max: Optional[float] = None
#    choices: Optional[List[str]] = None
#    unit: str = ""
#    label: str = ""
#    #: 文字參數的合法格式（正規表達式）。填了就在 ``validate_params`` 擋下來，
#    #: 而不是讓壞值跑到演算法裡（鐵則 4）。用在「這個字會變成特徵名的一部分」
#    #: 這種地方 —— 打了空白或減號，分數表達式就再也指不到那個特徵。
#    pattern: Optional[str] = None
#    #: ``pattern`` 不合時給使用者看的白話說明（不要讓他看到正規表達式）。
#    pattern_help: str = ""
#
#    def __post_init__(self) -> None:
#        if self.type not in PARAM_TYPES:
#            raise ParamError(f"parameter '{self.name}': unknown type '{self.type}' "
#                             f"(allowed: {PARAM_TYPES})")
#        if not str(self.help).strip():
#            raise ParamError(f"parameter '{self.name}': help (a plain-language "
#                             f"description) must not be empty")
#        if self.type == "choice" and not self.choices:
#            raise ParamError(f"parameter '{self.name}': type 'choice' requires choices")
#
#    def validate(self, value: Any) -> Any:
#        """coerce + 檢查範圍；失敗拋 ParamError（訊息含參數名）。"""
#        try:
#            if self.type == "int":
#                v: Any = int(value)
#            elif self.type == "float":
#                v = float(value)
#            elif self.type == "bool":
#                if isinstance(value, str):
#                    v = value.strip().lower() in ("1", "true", "yes", "on")
#                else:
#                    v = bool(value)
#            elif self.type in ("str", "image_key", "template"):
#                v = str(value)
#            elif self.type == "image_keys":
#                # 正規化：去空白、去空項、去重複但保留順序。
#                # 手打的 "ref, ref ,, test" 與 UI 勾出來的 "ref,test" 等價，
#                # 存進 recipe 的字串才不會因為輸入方式不同而長得不一樣。
#                seen: List[str] = []
#                for tok in str(value).split(","):
#                    tok = tok.strip()
#                    if tok and tok not in seen:
#                        seen.append(tok)
#                v = ",".join(seen)
#            elif self.type == "curve":
#                # 擋在這裡而不是等 run() 才炸（鐵則 4）。順便正規化：
#                # 排序、去空白、統一小數位 —— 手打的字串與 UI 拉出來的一樣。
#                v = format_curve(parse_curve(value))
#            elif self.type == "choice":
#                v = str(value)
#                if v not in (self.choices or []):
#                    raise ParamError(
#                        f"parameter '{self.name}': '{v}' is not one of {self.choices}"
#                    )
#            else:  # pragma: no cover — 擋在 __post_init__
#                raise ParamError(f"parameter '{self.name}': unknown type")
#        except ParamError:
#            raise
#        except CurveError as exc:
#            # CurveError 的訊息已經是白話的，別被下面的通用訊息蓋掉
#            raise ParamError(f"parameter '{self.name}': {exc}") from None
#        except (TypeError, ValueError):
#            raise ParamError(
#                f"parameter '{self.name}': '{value}' cannot be converted "
#                f"to {self.type}"
#            ) from None
#        if self.pattern and isinstance(v, str) and not re.match(self.pattern, v):
#            raise ParamError(
#                "parameter '%s': '%s' is not allowed here%s"
#                % (self.name, v,
#                   (" - " + self.pattern_help) if self.pattern_help else ""))
#        if self.type in ("int", "float"):
#            if self.min is not None and v < self.min:
#                raise ParamError(f"parameter '{self.name}': {v} is below the "
#                                 f"minimum of {self.min}")
#            if self.max is not None and v > self.max:
#                raise ParamError(f"parameter '{self.name}': {v} is above the "
#                                 f"maximum of {self.max}")
#        return v
#
#
#class Step(ABC):
#    """所有卡片的基底。子類別必須設定 key/label/category 並實作 run()。"""
#
#    key: ClassVar[str] = ""
#    label: ClassVar[str] = ""            # UI 顯示名
#    category: ClassVar[str] = ""
#    #: 流程階段（卡片庫分組用）。空字串 = 依 category 推一個保守的預設，
#    #: 所以舊卡片不宣告也不會壞（見 :meth:`resolve_group`）。
#    group: ClassVar[str] = ""
#    help: ClassVar[str] = ""             # 一行白話：這張卡做什麼
#    params: ClassVar[List[ParamSpec]] = []
#    reads: ClassVar[List[str]] = []      # 預設宣告；param 相依時覆寫 resolve_reads
#    writes: ClassVar[List[str]] = []
#    features_out: ClassVar[List[str]] = []
#    requires_ref: ClassVar[bool] = False  # True → rsem 單張資料流不可用（除非上游造出 ref）
#
#    # ---- 參數 -------------------------------------------------------------
#    @classmethod
#    def validate_params(cls, raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
#        """未知參數 → 錯；缺參數 → 帶預設；逐一 coerce/範圍檢查。回傳乾淨 dict。"""
#        raw = dict(raw or {})
#        spec_by_name = {p.name: p for p in cls.params}
#        unknown = sorted(set(raw) - set(spec_by_name))
#        if unknown:
#            raise ParamError(f"[{cls.key}] unknown parameters: {unknown} "
#                             f"(allowed: {sorted(spec_by_name)})")
#        out: Dict[str, Any] = {}
#        for name, spec in spec_by_name.items():
#            out[name] = spec.validate(raw.get(name, spec.default))
#        return out
#
#    # ---- I/O 宣告（param 相依的卡片覆寫這三個 classmethod）------------------
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return list(cls.reads)
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return list(cls.writes)
#
#    @classmethod
#    def resolve_writes_for_kind(cls, params: Dict[str, Any], kind: str) -> List[str]:
#        """資料型別相依的 writes 宣告（validate 對 route 首卡使用）。
#
#        預設同 ``resolve_writes``；像 load 卡這種「寫什麼取決於資料型別」的卡
#        覆寫此方法（例：ebi_patch → test+ref，rsem → single+test）。
#        """
#        return cls.resolve_writes(params)
#
#    @classmethod
#    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
#        return list(cls.features_out)
#
#    # ---- 具名區域（F7-9）---------------------------------------------------
#    #: 影像流有 reads/writes 可以在 validate 裡模擬，**具名 ROI 以前沒有**。
#    #: 於是「量測卡指到一個沒人定義的區域」只有兩種下場：名字打錯 → 每顆
#    #: defect 執行到一半才 StepError；名字剛好是保留字 ``blob`` 而上游又沒有
#    #: Blob 卡 → **安靜地改量整張圖**，跑得完、有數字、而且是錯的。
#    #: 後者是最糟的一種：使用者看不出哪裡不對。所以區域也宣告成契約，
#    #: 跟影像流走同一條檢查路徑（``recipe.validate`` 的 unknown-region）。
#    @classmethod
#    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
#        """這張卡會定義哪些具名區域。"""
#        return []
#
#    @classmethod
#    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
#        """這張卡需要哪些具名區域（空字串 = 整張影像，不算需求）。"""
#        return []
#
#    # ---- 「還沒設定完」（F7-13）--------------------------------------------
#    #: **參數合法 ≠ 設定完成。** ``roi_template`` 的 template 空字串是完全合法的
#    #: str，所以 ``validate_params`` 沒話說，lint 也沒話說 —— 但那張卡跑起來
#    #: 每一顆都會失敗。以前使用者要跑過一次才知道，而且是在跑完 200 顆之後。
#    #:
#    #: 這個方法讓卡片自己講「我還缺什麼」，而且是用**這張卡的話**講（模板要去
#    #: 按哪顆鈕），不是一句通用的「參數是必填的」。回傳的每一句都會變成一個
#    #: lint error，畫布上那張卡也會因此掛上警示標記。
#    @classmethod
#    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
#        """這張卡還缺哪些設定才跑得起來（空 list = 沒問題）。"""
#        return []
#
#    # ---- 執行 -------------------------------------------------------------
#    @abstractmethod
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        """執行本步驟。可就地修改 ctx 並回傳它。失敗請 raise StepError。"""
#
#    # ---- UI 描述 ----------------------------------------------------------
#    @classmethod
#    def resolve_group(cls) -> str:
#        """這張卡屬於哪個流程階段。
#
#        沒宣告 ``group`` 的卡片依 ``category`` 給一個保守預設 ——
#        影像段當 enhance、算法段當 measure、判定段當 adc。
#        這樣**新增 group 這個概念不會弄壞任何既有卡片**，
#        外掛或還沒遷移的卡照樣列得出來。
#        """
#        if cls.group:
#            return str(cls.group)
#        if cls.category == CATEGORY_ALGO:
#            return GROUP_MEASURE
#        if cls.category == CATEGORY_ADC:
#            return GROUP_ADC
#        return GROUP_ENHANCE
#
#    @classmethod
#    def describe(cls) -> Dict[str, Any]:
#        """給 UI / CLI 列表用的完整卡片描述。"""
#        return {
#            "key": cls.key,
#            "label": cls.label,
#            "category": cls.category,
#            "group": cls.resolve_group(),
#            "help": cls.help,
#            "requires_ref": cls.requires_ref,
#            "params": [
#                {
#                    "name": p.name, "type": p.type, "default": p.default,
#                    "help": p.help, "min": p.min, "max": p.max,
#                    "choices": p.choices, "unit": p.unit,
#                    "label": p.label or p.name,
#                    "pattern": p.pattern,
#                }
#                for p in cls.params
#            ],
#            "reads": list(cls.reads),
#            "writes": list(cls.writes),
#            "features_out": list(cls.features_out),
#        }
#
#
## ---------------------------------------------------------------------------
## Registry
## ---------------------------------------------------------------------------
#REGISTRY: Dict[str, Type[Step]] = {}
#
#
#def register_step(cls: Type[Step]) -> Type[Step]:
#    """類別裝飾器：把卡片註冊進全域 registry（key 重複 = 程式錯誤，立刻爆）。"""
#    if not cls.key:
#        raise ValueError(f"{cls.__name__}: key must not be empty")
#    if cls.category not in _CATEGORIES:
#        raise ValueError(f"{cls.__name__}: category must be one of {_CATEGORIES}, "
#                         f"got '{cls.category}'")
#    if not str(cls.help).strip():
#        raise ValueError(f"{cls.__name__}: help (a one-line plain-language "
#                         f"description) must not be empty")
#    if cls.key in REGISTRY:
#        raise ValueError(f"step key '{cls.key}' is already registered by "
#                         f"{REGISTRY[cls.key].__name__}")
#    REGISTRY[cls.key] = cls
#    return cls
#
#
#def get_step(key: str) -> Type[Step]:
#    try:
#        return REGISTRY[key]
#    except KeyError:
#        raise KeyError(f"unknown step '{key}'; registered: {sorted(REGISTRY)}") from None
#
#
#def list_steps(category: Optional[str] = None) -> List[Type[Step]]:
#    steps = [s for s in REGISTRY.values() if category is None or s.category == category]
#    return sorted(steps, key=lambda s: (_CATEGORIES.index(s.category), s.key))
#
#F fb69a86de270065254eb8c179aebef56f0994ed3 40 adept/core/steps/__init__.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""步驟卡片庫：import 本套件即完成所有卡片的 registry 註冊。
#
#每個子模組是一到多張卡（@register_step 的 Step 子類別）；
#引擎與 UI 只需 ``import adept.core.steps`` 再從
#``adept.core.pipeline.step.REGISTRY`` / ``list_steps()`` 取卡。
#
#已註冊的 key（影像段 → 算法段）：
#  load_patch, percentile_norm, glv_mask_norm, hist_match, denoise,
#  align, subtract, invert, golden_cell,
#  snr_map, blob_segment, cd_measure, roi_snr, focus_quality, glv_stats,
#  cell_period
#"""
#from __future__ import annotations
#
#from . import _util          # 共用小工具（非卡片）
#from . import load           # load_patch
#from . import normalize      # percentile_norm / glv_mask_norm / hist_match
#from . import denoise        # denoise
#from . import tone           # brightness_contrast / gamma
#from . import flatten        # flatten / local_contrast
#from . import align          # align
#from . import arith          # subtract / invert
#from . import snr_map        # snr_map
#from . import blob           # blob_segment
#from . import region         # roi_define
#from . import roi_profile    # roi_profile
#from . import roi_template   # roi_template
#from . import cd             # cd_measure
#from . import roi_snr        # roi_snr
#from . import quality        # focus_quality
#from . import glv_stats      # glv_stats
#from . import golden         # cell_period / golden_cell
#
#__all__ = [
#    "load", "normalize", "denoise", "tone", "flatten", "align", "arith",
#    "region", "roi_profile", "roi_template", "snr_map", "blob", "cd", "roi_snr", "quality", "glv_stats",
#    "golden",
#]
#
#F 1b6789a92ff01ea44b919be6f91cf07cd6c3391b 167 adept/core/steps/_util.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""步驟卡片共用的小工具（非卡片；不註冊任何 step）。
#
#- ``require_image``  向 Context 要影像，缺流時轉成白話 StepError。
#- ``to_uint8``       把任何灰階陣列安全轉成 uint8 0–255（[0,1] 浮點自動 ×255）。
#- ``parse_key_list`` 逗號字串 → 影像流 key 清單（去空白、忽略空項）。
#- ``ensure_gray``    彩色（3 通道）輸入自動轉灰階。
#- ``output_prefix_spec`` / ``prefix_*``  量測卡的輸出名前綴（見下方說明）。
#"""
#from __future__ import annotations
#
#from typing import Dict, List
#
#import cv2
#import numpy as np
#
#from ..pipeline.context import Context, ContextError
#from ..pipeline.step import ParamSpec, StepError
#
## --------------------------------------------------------------------------- #
## 輸出名前綴（F7-11）—— 讓同一張量測卡可以用在好幾個區域上
## --------------------------------------------------------------------------- #
##: 特徵名是**扁平的全域命名空間**，而且是分數表達式的變數名。所以前綴只能用
##: 「可以當變數名」的字：開頭是字母或底線，後面接字母／數字／底線。
##: 打了空白或減號的話，`glv mean` 這種名字在表達式裡是指不到的 —— 擋在這裡，
##: 而不是等使用者寫完表達式才發現（鐵則 4）。
#FEATURE_PREFIX_PATTERN = r"^$|^[A-Za-z_][A-Za-z0-9_]*$"
#
#
## --------------------------------------------------------------------------- #
## 一張卡做一條流（F7-18）
## --------------------------------------------------------------------------- #
##: Enhance 卡的主要參數共用的說明。
##:
##: 以前每張卡是「``target`` + ``also_apply``」兩個參數：主流一個、附帶的一串。
##: 那個形狀把 ``test`` 講成主角、``ref`` 講成附帶 —— 但它們就是兩張不同的
##: 輸入影像，兩張都該可以獨立處理。而「要對哪幾張做」是**畫布上的事**
##: （哪條線接進來），不是控制列上的一組勾選框。
##:
##: 所以現在一張卡就是一條流：要對 ref 也做同一件事，就再放一張卡接到 ref。
##: 畫布上因此看得到兩條各自的處理鏈，而不是一張卡偷偷動了兩條流。
#ONE_STREAM_HELP = (
#    "Which image stream this card works on; the result is written back to "
#    "that same stream. Streams are the named lines on the canvas - test is "
#    "the defect image, ref is the reference image. One card works on one "
#    "stream: connect a stream to this card on the canvas (or pick it here), "
#    "and add a second card if the other image needs the same treatment.")
#
#
#def output_prefix_spec(example: str = "center") -> ParamSpec:
#    """量測卡共用的 ``output_prefix`` 參數（每張卡的說明只差一個例子）。"""
#    return ParamSpec(
#        name="output_prefix", type="str", default="",
#        label="Name these results",
#        pattern=FEATURE_PREFIX_PATTERN,
#        pattern_help=("use letters, digits and underscores only, and do not "
#                      "start with a digit"),
#        help=("Put a name in front of every number this card produces, so two "
#              "of these cards measuring two different regions do not overwrite "
#              "each other. For example '%s' turns glv_mean into %s_glv_mean. "
#              "Leave it empty if this is the only card of its kind."
#              % (example, example)),
#    )
#
#
#def prefix_names(prefix: str, names: List[str]) -> List[str]:
#    """把前綴套到一串特徵名上（前綴為空 = 原樣回傳）。"""
#    p = str(prefix or "").strip()
#    return [f"{p}_{n}" for n in names] if p else list(names)
#
#
#def prefix_features(prefix: str, feats: Dict[str, float]) -> Dict[str, float]:
#    """把前綴套到一組特徵值上（前綴為空 = 原樣回傳）。"""
#    p = str(prefix or "").strip()
#    return {f"{p}_{k}": v for k, v in feats.items()} if p else dict(feats)
#
#
#def require_image(ctx: Context, step_key: str, key: str) -> np.ndarray:
#    """取出影像流；不存在時拋白話 StepError（不讓 ContextError 直接外洩）。"""
#    try:
#        return ctx.require_image(key)
#    except ContextError as e:
#        raise StepError(step_key, f"missing image stream '{key}' ({e})") from None
#
#
#def roi_rect_or_none(ctx, step_key: str, image, roi_name):
#    """把 ``roi`` 參數解成像素矩形 ``(x, y, w, h)``；空字串 = 整張影像。
#
#    ``'blob'`` 是保留名：優先找同名 ROI（``blob_segment`` 會寫），
#    找不到才退回 ``meta['blobs']`` 的主 blob —— 這樣舊 recipe 與新 Region 段
#    可以並存，而且 ``blob_segment`` 之後也還是同一個名字。
#    找不到任何東西時回 ``None``（呼叫端決定要警告還是當成整張圖）。
#    """
#    import numpy as _np
#
#    name = str(roi_name or "").strip()
#    shape = None if image is None else _np.asarray(image).shape[:2]
#    if not name:
#        # 整張影像 —— 需要知道尺寸
#        return None if shape is None else (0, 0, int(shape[1]), int(shape[0]))
#    if name in ctx.roi_names():
#        # 具名 ROI 存的是正規化座標，一樣需要尺寸才展得開
#        return None if shape is None else ctx.roi_rect(name, shape)
#    if name == "blob":
#        # blob 的矩形已經是像素座標，**不需要影像**（影像流可能已被下游覆寫掉）
#        blobs = ctx.meta.get("blobs") or []
#        if blobs:
#            b = blobs[0]        # 主 blob = SNR 最強者（segment 已降冪排序）
#            return (int(b["x"]), int(b["y"]), int(b["w"]), int(b["h"]))
#        # 退回整張圖是刻意的（Blob 卡跑了但這顆沒找到東西是正常的），但
#        # **一定要說出來**：不講的話使用者拿到的是一組看起來很正常、實際上
#        # 量的是整張圖的數字，而那是最難發現的一種錯。
#        ctx.warn(f"[{step_key}] no blob was found on this defect, so region "
#                 f"'blob' falls back to the whole image; the numbers from this "
#                 f"card describe the whole patch, not a defect.")
#        return None
#    # 具名 ROI 打錯字要講清楚，不要安靜地量整張圖
#    raise StepError(step_key,
#                    "region '%s' is not defined; available: %s. Add a Define "
#                    "region card upstream, or leave roi empty for the whole "
#                    "image." % (name, ctx.roi_names()))
#
#
#def crop_to_roi(ctx, step_key: str, image, roi_name):
#    """依 ``roi`` 參數裁出要量測的像素（找不到 blob 時退回整張圖）。"""
#    rect = roi_rect_or_none(ctx, step_key, image, roi_name)
#    if rect is None:
#        return image
#    x, y, w, h = rect
#    return image[y:y + h, x:x + w]
#
#
#def ensure_gray(arr: np.ndarray) -> np.ndarray:
#    """彩色影像轉單通道灰階；灰階原樣回傳。"""
#    a = np.asarray(arr)
#    if a.ndim == 3:
#        if a.shape[2] == 4:
#            return cv2.cvtColor(a, cv2.COLOR_BGRA2GRAY)
#        return cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
#    return a
#
#
#def to_uint8(arr: np.ndarray) -> np.ndarray:
#    """任何灰階陣列 → uint8 0–255。
#
#    - uint8 原樣回傳。
#    - 浮點且值域看起來是 [0, 1] → ×255。
#    - 其他（float 0–255、uint16 已是 0–255 值域…）→ clip 到 0–255 後轉型。
#    """
#    a = np.asarray(arr)
#    if a.dtype == np.uint8:
#        return a
#    f = a.astype(np.float32)
#    if f.size > 0:
#        fmax = float(f.max())
#        fmin = float(f.min())
#        if 0.0 <= fmin and fmax <= 1.5:
#            f = f * 255.0
#    return np.clip(f, 0, 255).astype(np.uint8)
#
#
#def parse_key_list(raw: str) -> List[str]:
#    """逗號分隔字串 → key 清單；空白與空項自動忽略。"""
#    if not raw:
#        return []
#    return [tok.strip() for tok in str(raw).split(",") if tok.strip()]
#
#F 55a5a0bcc01184359f6a4f5bf5aca5c6c99c37d9 98 adept/core/steps/align.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""align — 對位卡：估計 moving 相對 fixed 的平移並回正。
#
#符號慣例（沿用 algo.align）：moving 內容若在 fixed 的右下方 (dx, dy) 像素，
#則回報正的 (dx, dy)，並把 moving 平移 (-dx, -dy) 寫到 out 流。
#平坦影像或對位失敗時：警告 + 零位移（原圖照寫到 out），絕不讓整批掛掉。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#from ..algo import align as algo_align
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_IMAGE, ParamSpec, Step, register_step, GROUP_COMPARE,
#)
#from ._util import require_image
#
#
#@register_step
#class AlignStep(Step):
#    """平移對位：phase/hybrid/ncc/ecc/template 後端擇一。"""
#
#    key = "align"
#    label = "Align"
#    category = CATEGORY_IMAGE
#    group = GROUP_COMPARE
#    help = ("Estimate how far ref is shifted from test and move ref back into "
#            "alignment, so the later subtraction is not full of false signal.")
#    requires_ref = True
#    params = [
#        ParamSpec(name="moving", type="image_key", default="ref",
#                  help="Image stream to be moved into alignment (usually ref)."),
#        ParamSpec(name="fixed", type="image_key", default="test",
#                  help="Reference stream that stays put (usually test)."),
#        ParamSpec(name="method", type="choice", default="phase",
#                  choices=["phase", "hybrid", "ncc", "ecc", "template"],
#                  help=("Alignment backend: phase = fast and robust (default); "
#                        "ncc = exhaustive correlation; ecc = iterative refinement; "
#                        "template = central template match; hybrid behaves like phase.")),
#        ParamSpec(name="search_radius", type="int", default=8, min=1, max=64,
#                  help=("Search radius in pixels: the largest shift you expect. "
#                        "Too small and it will not find the shift, too large "
#                        "and it gets slow.")),
#        ParamSpec(name="out", type="image_key", default="ref_aligned",
#                  help="Name of the image stream the aligned result is written to."),
#    ]
#    reads = ["test", "ref"]
#    writes = ["ref_aligned"]
#    features_out = ["align_dx", "align_dy", "align_score"]
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("fixed", "test"), params.get("moving", "ref")]
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("out", "ref_aligned")]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        fixed = require_image(ctx, self.key, p["fixed"])
#        moving = require_image(ctx, self.key, p["moving"])
#        if fixed.shape[:2] != moving.shape[:2]:
#            # 尺寸不合時無法對位：警告 + 零位移，不殺整批
#            ctx.warn(f"[{self.key}] '{p['fixed']}' and '{p['moving']}' differ in "
#                     f"size ({fixed.shape[:2]} vs {moving.shape[:2]}); "
#                     f"using zero shift.")
#            res = None
#        else:
#            try:
#                res = algo_align.calculate_alignment(
#                    fixed, moving, method=p["method"],
#                    search_radius=int(p["search_radius"]))
#            except Exception as e:   # 對位絕不讓整批掛掉
#                ctx.warn(f"[{self.key}] alignment failed ({e}); using zero shift.")
#                res = None
#
#        if res is None or res.status == "fail":
#            if res is not None:
#                ctx.warn(f"[{self.key}] alignment did not converge "
#                         f"(score={res.final_score:.1f}); using zero shift.")
#            dx, dy, score = 0.0, 0.0, (res.final_score if res is not None else 0.0)
#            aligned = moving.copy()
#        else:
#            if res.status == "warn":
#                ctx.warn(f"[{self.key}] low alignment quality "
#                         f"(score={res.final_score:.1f}); treat results with care.")
#            dx, dy = float(res.dx_subpixel), float(res.dy_subpixel)
#            score = float(res.final_score)
#            aligned = algo_align.apply_alignment(moving, dx, dy)
#
#        ctx.set_image(p["out"], aligned)
#        ctx.add_features({"align_dx": dx, "align_dy": dy, "align_score": score})
#        ctx.meta["align_dx"] = dx
#        ctx.meta["align_dy"] = dy
#        return ctx
#
#F cd0970fe460695f92bd15316a4a5be96f0f5776b 146 adept/core/steps/arith.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""影像算術卡：subtract / invert。
#
#注意：subtract 產出的 diff 流是 **float32**（可能含負值，取決於 absolute），
#下游卡（snr_map / blob_segment / roi_snr…）都吃得下 float32。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#import numpy as np
#
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_COMPARE, GROUP_ENHANCE,
#)
#from ._util import require_image
#
#
#@register_step
#class SubtractStep(Step):
#    """影像相減：out = a - b（float32；absolute=True 時取絕對值）。"""
#
#    key = "subtract"
#    label = "Compare two streams"
#    category = CATEGORY_IMAGE
#    group = GROUP_COMPARE
#    help = ("Combine two image streams into one - normally test minus the "
#            "aligned ref, which is what makes defects stand out. The result "
#            "stream is float32.")
#    requires_ref = True
#    params = [
#        ParamSpec(name="a", type="image_key", default="test",
#                  label="First stream",
#                  help="The image being judged (usually test)."),
#        ParamSpec(name="b", type="image_key", default="ref_aligned",
#                  label="Second stream",
#                  help=("What to compare it against (usually the aligned "
#                        "ref_aligned - add an Align card to produce that "
#                        "stream, or point this at ref to skip alignment).")),
#        # op 是 F7-10 加的。差分之外的四種組合以前得靠外部工具做，但它們跟
#        # 相減是同一個問題的不同答案（「這兩張哪裡不一樣」），所以是同一張卡的
#        # 一個下拉 —— 不是四張新卡片。
#        ParamSpec(
#            name="op", type="choice", default="subtract",
#            choices=["subtract", "ratio", "max", "min", "mean"],
#            label="How to combine",
#            help=("subtract = a minus b, the normal die-to-die difference; "
#                  "ratio = a divided by b, which stays meaningful when the "
#                  "two images have different overall brightness; max / min = "
#                  "take the brighter or darker pixel of the two; mean = "
#                  "average them (useful for building a cleaner reference)."),
#        ),
#        ParamSpec(name="absolute", type="bool", default=True,
#                  label="Ignore the sign",
#                  help=("True = absolute value (bright and dark defects both become "
#                        "positive signal); False = keep the sign so bright and dark "
#                        "defects stay distinguishable. Only used by subtract.")),
#        ParamSpec(name="out", type="image_key", default="diff",
#                  label="Write result to",
#                  help="Name of the image stream the result is written to (float32)."),
#    ]
#    reads = ["test", "ref_aligned"]
#    writes = ["diff"]
#    features_out: List[str] = []
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("a", "test"), params.get("b", "ref_aligned")]
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("out", "diff")]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        a = require_image(ctx, self.key, p["a"])
#        b = require_image(ctx, self.key, p["b"])
#        if a.shape != b.shape:
#            raise StepError(self.key, f"'{p['a']}' and '{p['b']}' differ in size "
#                            f"({a.shape} vs {b.shape}); cannot subtract.")
#        fa, fb = a.astype(np.float32), b.astype(np.float32)
#        op = str(p["op"])
#        if op == "ratio":
#            # 0 除法：分母補一個極小值而不是讓它變 inf —— inf 會一路帶到
#            # 特徵與分數，最後變成一顆「分數是 nan」的 defect，而使用者
#            # 完全看不出是哪一步造成的。
#            out = fa / np.maximum(np.abs(fb), 1e-6) * np.sign(np.where(fb == 0, 1.0, fb))
#        elif op == "max":
#            out = np.maximum(fa, fb)
#        elif op == "min":
#            out = np.minimum(fa, fb)
#        elif op == "mean":
#            out = (fa + fb) * 0.5
#        else:
#            out = fa - fb
#            if p["absolute"]:
#                out = np.abs(out)
#        ctx.set_image(p["out"], out.astype(np.float32))
#        return ctx
#
#
#@register_step
#class InvertStep(Step):
#    """影像反相：亮暗顛倒（uint8：255-x；[0,1] 浮點：1-x）。"""
#
#    key = "invert"
#    label = "Invert"
#    category = CATEGORY_IMAGE
#    group = GROUP_ENHANCE
#    help = ("Flip bright and dark, so dark defects become bright signal for "
#            "the steps that follow.")
#    params = [
#        ParamSpec(name="target", type="image_key", default="test",
#                  label="Apply to",
#                  help=("Which image stream to invert; the result is written "
#                        "back to that same stream. Streams are the named lines "
#                        "on the canvas - test is the defect image, ref is the "
#                        "reference image.")),
#    ]
#    reads = ["test"]
#    writes = ["test"]
#    features_out: List[str] = []
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("target", "test")]
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("target", "test")]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        img = require_image(ctx, self.key, p["target"])
#        if img.dtype == np.uint8:
#            out = (255 - img).astype(np.uint8)
#        else:
#            f = img.astype(np.float32)
#            if f.size > 0 and float(f.min()) >= 0.0 and float(f.max()) <= 1.5:
#                out = (1.0 - np.clip(f, 0.0, 1.0)).astype(np.float32)
#            else:
#                out = (255.0 - np.clip(f, 0.0, 255.0)).astype(np.float32)
#        ctx.set_image(p["target"], out)
#        return ctx
#
#F 4e08651dd3cc6c6ca9ebe5c8f8d65cb455f333da 108 adept/core/steps/blob.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""blob_segment — Blob 分割卡。
#
#在 SNR 地圖上做門檻 + 連通元件分割，找出候選缺陷區塊：
#- meta["blobs"]：全部區塊（plain dict 清單，可序列化）。
#- features：blob_count 與「主 blob」（SNR 最強者）的 blob_area /
#  blob_aspect / blob_dist_center / blob_snr；一顆都沒有時全部為 0（不算錯誤）。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#from ..algo import blob as algo_blob
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_REGION,
#)
#from ._util import require_image
#
#
#def _roi_to_dict(r: "algo_blob.DefectROI") -> Dict[str, Any]:
#    return {
#        "x": int(r.x), "y": int(r.y), "w": int(r.w), "h": int(r.h),
#        "cx": float(r.cx), "cy": float(r.cy),
#        "area": int(r.area),
#        "mean_signal": float(r.mean_signal),
#        "snr_value": float(r.snr_value),
#        "aspect_ratio": float(r.aspect_ratio),
#        "dist_to_center": float(r.dist_to_center),
#    }
#
#
#@register_step
#class BlobSegmentStep(Step):
#    """Blob 分割：SNR 地圖 → 門檻 → 連通元件 → 候選缺陷清單。"""
#
#    key = "blob_segment"
#    label = "Blob segment"
#    category = CATEGORY_ALGO
#    group = GROUP_REGION
#    help = ("Cut candidate defect blobs out of the SNR map and record the main "
#            "blob's area, aspect ratio, distance from centre and SNR.")
#    params = [
#        ParamSpec(name="source", type="image_key", default="snr_map",
#                  help="Input SNR map image stream."),
#        ParamSpec(name="diff_source", type="image_key", default="diff",
#                  help=("Matching difference image stream, used to measure each "
#                        "blob's mean signal.")),
#        ParamSpec(name="min_area", type="int", default=4, min=1, max=10000,
#                  help=("Minimum area in pixels: anything smaller is treated as "
#                        "noise and dropped.")),
#        ParamSpec(name="roi_out", type="str", default="blob",
#                  help=("Name given to the main blob's region, so Measure "
#                        "cards can point at it (leave as 'blob' unless you "
#                        "run two Blob segment cards).")),
#        ParamSpec(name="snr_threshold", type="float", default=0.0, min=0.0, max=255.0,
#                  help=("Segmentation threshold on the 0-255 map scale; "
#                        "0 = decide automatically by Otsu (recommended).")),
#    ]
#    reads = ["snr_map", "diff"]
#    writes: List[str] = []
#    features_out = ["blob_count", "blob_area", "blob_aspect",
#                    "blob_dist_center", "blob_snr"]
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("source", "snr_map"), params.get("diff_source", "diff")]
#
#    @classmethod
#    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
#        name = str(params.get("roi_out", "blob") or "").strip()
#        return [name] if name else []
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        snr_img = require_image(ctx, self.key, p["source"])
#        diff_img = require_image(ctx, self.key, p["diff_source"])
#        if snr_img.shape[:2] != diff_img.shape[:2]:
#            raise StepError(self.key, f"'{p['source']}' and '{p['diff_source']}' differ in "
#                                      f"size ({snr_img.shape[:2]} vs "
#                                      f"{diff_img.shape[:2]}); cannot segment.")
#        thr = None if float(p["snr_threshold"]) <= 0.0 else float(p["snr_threshold"])
#        rois = algo_blob.segment_defects(
#            snr_img, diff_img, min_area=int(p["min_area"]), snr_threshold=thr)
#
#        ctx.meta["blobs"] = [_roi_to_dict(r) for r in rois]
#        # F7-4：主 blob 也寫成具名 ROI，讓它跟使用者畫的框走同一條路。
#        # meta["blobs"] 保留（overlay 與舊 recipe 還在讀）。
#        name = str(p["roi_out"]).strip()
#        if name and rois:
#            big0 = rois[0]
#            h0, w0 = snr_img.shape[:2]
#            ctx.set_roi(name, (big0.x / w0, big0.y / h0,
#                               max(1, big0.w) / w0, max(1, big0.h) / h0))
#        feats = {"blob_count": float(len(rois)),
#                 "blob_area": 0.0, "blob_aspect": 0.0,
#                 "blob_dist_center": 0.0, "blob_snr": 0.0}
#        if rois:
#            big = rois[0]     # 主 blob = SNR 最強者（segment_defects 已按 snr 降冪排序）
#            feats.update({
#                "blob_area": float(big.area),
#                "blob_aspect": float(big.aspect_ratio),
#                "blob_dist_center": float(big.dist_to_center),
#                "blob_snr": float(big.snr_value),
#            })
#        ctx.add_features(feats)
#        return ctx
#
#F 1d82ef94ad92b93b4e9e023f4a8334fa8394c24c 140 adept/core/steps/cd.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""cd_measure — CD 量測卡（M1 簡化版）。
#
#★ M1 簡化說明 ★
#v1 的 CD 定義是「最大 blob 的 bounding box 寬 / 高」：
#  cd_x_px = bbox 寬、cd_y_px = bbox 高。
#這是缺陷尺寸的粗估，不是產線 CD-SEM 等級的線寬量測（真正的
#edge-pair / 多取樣線寬量測留待後續 milestone）。refine="subpixel"
#時只精修 bbox 的上下邊（Y 方向）成次像素，X 方向仍是 bbox 寬。
#
#meta["nm_per_px"] 存在時同步輸出 nm 尺寸（cd_x_nm / cd_y_nm / area_nm2），
#否則這三個 feature 為 0 並記警告。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#import numpy as np
#
#from ..algo import subpixel as algo_subpixel
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_ALGO, ParamSpec, Step, register_step, GROUP_MEASURE,
#)
#from ._util import (
#    output_prefix_spec, prefix_features, prefix_names, roi_rect_or_none,
#)
#
#_ZERO = {"cd_x_px": 0.0, "cd_y_px": 0.0,
#         "cd_x_nm": 0.0, "cd_y_nm": 0.0, "area_nm2": 0.0}
#
#
#@register_step
#class CdMeasureStep(Step):
#    """CD 量測（M1：最大 blob 的 bbox 尺寸；可選次像素上下邊精修）。"""
#
#    key = "cd_measure"
#    label = "CD measure"
#    category = CATEGORY_ALGO
#    group = GROUP_MEASURE
#    help = ("Measure the width and height of the main defect blob in pixels "
#            "(also in nm when nm_per_px is known). Currently a bounding-box "
#            "estimate.")
#    params = [
#        ParamSpec(name="source", type="image_key", default="diff",
#                  help="Image stream sampled when refining edges (usually diff)."),
#        ParamSpec(name="roi", type="str", default="blob",
#                  help=("Which region to measure — the name given by a Blob "
#                        "segment or Define region card upstream.")),
#        ParamSpec(name="refine", type="choice", default="none",
#                  choices=["none", "subpixel"],
#                  help=("none = use the bounding box as is; subpixel = refine the "
#                        "top and bottom edges to sub-pixel precision (falls back "
#                        "to the bounding box on failure).")),
#        output_prefix_spec("blob"),
#    ]
#    reads = ["diff"]
#    writes: List[str] = []
#    features_out = ["cd_x_px", "cd_y_px", "cd_x_nm", "cd_y_nm", "area_nm2"]
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("source", "diff")]
#
#    @classmethod
#    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
#        return prefix_names(params.get("output_prefix", ""), cls.features_out)
#
#    @classmethod
#    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
#        name = str(params.get("roi", "blob") or "").strip()
#        return [name] if name else []
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        # 尺寸來源：優先用參數指定的流，否則任何一張都可以。可能一張都沒有 ——
#        # roi="blob" 不需要影像（矩形已是像素座標），所以這裡不能提早 return。
#        shape_src = ctx.images.get(p["source"])
#        if shape_src is None:
#            shape_src = next(iter(ctx.images.values()), None)
#
#        rect = roi_rect_or_none(ctx, self.key, shape_src, p["roi"])
#        if rect is None:
#            ctx.warn(f"[{self.key}] no blob found (run Blob segment first, or "
#                     f"point roi at a Define region card); all CD features "
#                     f"recorded as 0.")
#            ctx.add_features(prefix_features(p["output_prefix"], _ZERO))
#            return ctx
#
#        bx, by = float(rect[0]), float(rect[1])
#        bw, bh = float(rect[2]), float(rect[3])
#        cx = bx + bw / 2.0
#
#        # 面積：blob 有真實的像素面積（不是 bbox 面積），使用者畫的框則是 w*h。
#        blobs = ctx.meta.get("blobs") or []
#        area_px = (float(blobs[0].get("area", bw * bh))
#                   if (blobs and str(p["roi"]).strip() == "blob") else bw * bh)
#
#        cd_x_px = bw
#        cd_y_px = bh
#
#        if p["refine"] == "subpixel":
#            img = ctx.images.get(p["source"])
#            if img is None:
#                ctx.warn(f"[{self.key}] image stream '{p['source']}' does not "
#                          f"exist; cannot refine to sub-pixel, using the "
#                          f"bounding box.")
#            else:
#                try:
#                    top = algo_subpixel.refine_yedge_subpixel(
#                        np.asarray(img), x_center=cx, y_guess=by)
#                    bot = algo_subpixel.refine_yedge_subpixel(
#                        np.asarray(img), x_center=cx, y_guess=by + bh)
#                    if (top.fallback_reason == "" and bot.fallback_reason == ""
#                            and bot.y_refined > top.y_refined):
#                        cd_y_px = float(bot.y_refined - top.y_refined)
#                    else:
#                        reason = (top.fallback_reason or bot.fallback_reason
#                                  or "edges came out in the wrong order")
#                        ctx.warn(f"[{self.key}] sub-pixel refinement did not "
#                                     f"succeed ({reason}); using the bounding-box "
#                                     f"height.")
#                except Exception as e:   # 精修絕不讓量測掛掉
#                    ctx.warn(f"[{self.key}] sub-pixel refinement errored "
#                             f"({e}); using the bounding-box height.")
#
#        feats = {"cd_x_px": float(cd_x_px), "cd_y_px": float(cd_y_px),
#                 "cd_x_nm": 0.0, "cd_y_nm": 0.0, "area_nm2": 0.0}
#        npp = ctx.nm_per_px
#        if npp is not None and float(npp) > 0:
#            npp = float(npp)
#            feats["cd_x_nm"] = cd_x_px * npp
#            feats["cd_y_nm"] = cd_y_px * npp
#            feats["area_nm2"] = area_px * npp * npp
#        else:
#            ctx.warn(f"[{self.key}] meta['nm_per_px'] is not set; nm sizes "
#                     f"recorded as 0 (pixel values only).")
#        ctx.add_features(prefix_features(p["output_prefix"], feats))
#        return ctx
#
#F 2079c270453bebec9f45d2ee524c68afc0a96fb9 101 adept/core/steps/denoise.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""denoise — 去雜訊卡（median / gaussian / bilateral / nlm）。"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#import cv2
#import numpy as np
#
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_ENHANCE,
#)
#from ..algo import enhance as algo_enhance
#from ._util import ONE_STREAM_HELP, require_image
#
#
#def _denoise_one(step_key: str, img: np.ndarray, method: str, ksize: int,
#                 strength: float = 1.0) -> np.ndarray:
#    """四種去雜訊法共用的入口。
#
#    ``bilateral`` / ``nlm`` 是 F7-10 加的**邊緣保留**法。加進這張卡而不是
#    另開一張，是因為使用者的問題自始至終是同一個（「這張圖太雜」），
#    差別只在願意付多少代價換多少邊緣 —— 那是一個下拉，不是兩張卡。
#    它們回傳 float32（見 ``algo/enhance.py`` 的 dtype 慣例）。
#    """
#    if ksize == 1:
#        return img.copy()          # ksize=1 等於不濾波
#    if method == "median":
#        # cv2.medianBlur：float32 只支援 ksize<=5；uint8 支援到大核
#        if img.dtype != np.uint8 and ksize > 5:
#            raise StepError(step_key, f"median filtering of float images supports ksize 1/3/5 only "
#                        f"(got {ksize}); use a smaller ksize or convert to uint8 first.")
#        src = img if img.dtype in (np.uint8, np.float32) else img.astype(np.float32)
#        return cv2.medianBlur(src, ksize)
#    if method == "bilateral":
#        return algo_enhance.bilateral(img, ksize, strength)
#    if method == "nlm":
#        return algo_enhance.nlm(img, ksize, strength)
#    # gaussian
#    return cv2.GaussianBlur(img, (ksize, ksize), 0)
#
#
#@register_step
#class DenoiseStep(Step):
#    """去雜訊：median / gaussian（全平滑）與 bilateral / nlm（保留邊緣）。"""
#
#    key = "denoise"
#    label = "Denoise"
#    category = CATEGORY_IMAGE
#    group = GROUP_ENHANCE
#    help = ("Suppress image noise so the measurements that follow are "
#            "steadier - either smoothing everything, or smoothing only the "
#            "flat areas and leaving edges (and small defects) intact.")
#    params = [
#        ParamSpec(name="target", type="image_key", default="test",
#                  label="Image stream", help=ONE_STREAM_HELP),
#        ParamSpec(name="method", type="choice", default="median",
#                  choices=["median", "gaussian", "bilateral", "nlm"],
#                  help=("median = suppress isolated bright/dark specks (common "
#                        "for SEM); gaussian = soften everything; bilateral = "
#                        "smooth noise but keep edges, so small defects are not "
#                        "wiped out with the noise; nlm = the same idea but "
#                        "gentler on repeating patterns, and much slower.")),
#        ParamSpec(name="ksize", type="int", default=3, min=1, max=15,
#                  label="Filter size",
#                  help=("Filter kernel size (odd, 1-15; 1 = no filtering, "
#                        "larger is smoother).")),
#        ParamSpec(name="strength", type="float", default=1.0, min=0.1, max=5.0,
#                  label="Smoothing strength",
#                  help=("How aggressively bilateral / nlm smooth, measured "
#                        "against this image's own noise level - so 1 means "
#                        "the same thing on a quiet lot and a noisy one. "
#                        "Above about 2, small defects start disappearing "
#                        "along with the noise. Not used by median or "
#                        "gaussian.")),
#    ]
#    reads = ["test"]
#    writes = ["test"]
#    features_out: List[str] = []
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [str(params.get("target", "test"))]
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return cls.resolve_reads(params)
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        ksize = int(p["ksize"])
#        if ksize % 2 == 0:
#            raise StepError(self.key, f"ksize must be odd (got {ksize}); an even kernel has no "
#                        f"centre pixel — use {ksize - 1} or {ksize + 1}.")
#        strength = float(p["strength"])
#        tgt = require_image(ctx, self.key, p["target"])
#        ctx.set_image(p["target"],
#                      _denoise_one(self.key, tgt, p["method"], ksize, strength))
#        return ctx
#
#F afd4fbe9c41c4fdbbee73b53a89626555a1e4dd2 168 adept/core/steps/flatten.py
## ADEPT step-card library — authored 2026-07-29 (F7-10).
#"""flatten / local_contrast —— 處理**空間性**假訊號的兩張 Enhance 卡。
#
#為什麼是兩張卡而不是六張
#------------------------
#「背景平坦化」「去掃描線條紋」「top-hat」「black-hat」看起來是四種不同的東西，
#但它們的結構完全一樣：**估一個大尺度的成分，然後把它減掉**。差別只在怎麼估
#（高斯模糊／逐列中位數／形態學開閉運算）。所以它們是同一張卡的 ``method``，
#不是四張卡 —— 卡片庫多四列，使用者要多讀四段說明才能知道該用哪一個；
#一張卡的一個下拉，他只要讀一次。
#
#CLAHE 分開放，是因為它不是「減掉什麼」而是「局部重新拉伸」，
#而且它跟既有的三張 Normalize 卡是同一個家族（都是把灰階重新映射），
#所以命名跟著那個家族走（``Normalize · Local contrast``）。
#
#輸出 dtype
#----------
#兩張卡都輸出 float32。既有的 Enhance 卡多半維持 uint8，但這幾種運算會產生
#負值（背景移除）或需要小數精度（CLAHE 後再做別的），硬轉回 uint8 會在
#量測之前就先截掉資訊。下游的量測卡與 ``subtract`` 都吃得下 float32
#（``diff`` 流本來就是 float32）。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#import numpy as np
#
#from ..algo import enhance as algo_enhance
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_IMAGE, GROUP_ENHANCE, ParamSpec, Step, register_step,
#)
#from ._util import ONE_STREAM_HELP, require_image
#
#
#class _StreamStep(Step):
#    """共用：一張卡做一條影像流（同 tone / normalize 卡的慣例，見 F7-18）。"""
#
#    category = CATEGORY_IMAGE
#    group = GROUP_ENHANCE
#    reads = ["test"]
#    writes = ["test"]
#    features_out: List[str] = []
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [str(params.get("target", "test"))]
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return cls.resolve_reads(params)
#
#    def _apply(self, ctx: Context, params: Dict[str, Any], fn) -> Context:
#        key = str(params.get("target", "test"))
#        img = require_image(ctx, self.key, key)
#        ctx.set_image(key, np.asarray(fn(img), dtype=np.float32))
#        return ctx
#
#
#@register_step
#class FlattenStep(_StreamStep):
#    """移除大尺度的假訊號：亮度梯度、掃描線條紋、不平的背景。"""
#
#    key = "flatten"
#    label = "Remove background / stripes"
#    help = ("Remove large-scale artifacts that are not defects - charging "
#            "brightness gradients, scan-line stripes, or an uneven background "
#            "- so they stop showing up in the difference image.")
#    params = [
#        ParamSpec(name="target", type="image_key", default="test",
#                  label="Image stream", help=ONE_STREAM_HELP),
#        ParamSpec(
#            name="method", type="choice", default="background",
#            choices=["background", "stripes_h", "stripes_v",
#                     "bright_spots", "dark_spots"],
#            label="Remove",
#            help=("background = a smooth brightness gradient (charging); "
#                  "stripes_h / stripes_v = scan-line stripes running across "
#                  "or down the image; bright_spots / dark_spots = keep only "
#                  "features smaller than the size below and drop everything "
#                  "larger, whatever shape the background is."),
#        ),
#        ParamSpec(
#            name="size", type="int", default=31, min=3, max=999, unit="px",
#            label="Scale to remove",
#            help=("How large the artifact is, in pixels. It must be clearly "
#                  "BIGGER than your defects - anything smaller than this "
#                  "survives, anything larger is removed. A quarter to a half "
#                  "of the patch width is a good starting point. "
#                  "(Not used for the stripe methods.)"),
#        ),
#        ParamSpec(
#            name="strength", type="float", default=1.0, min=0.0, max=1.0,
#            label="Strength",
#            help=("How much of the estimated artifact to take out; 1 = all of "
#                  "it. Only used by the stripe methods - real stripes are not "
#                  "always purely additive, so full correction can overshoot."),
#        ),
#        ParamSpec(
#            name="keep_level", type="bool", default=True,
#            label="Keep original brightness",
#            help=("Add the original average brightness back, so the image "
#                  "stays in the gray range it started in and the thresholds "
#                  "downstream still mean the same thing."),
#        ),
#    ]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        method = str(p["method"])
#        size = int(p["size"])
#        strength = float(p["strength"])
#        keep = bool(p["keep_level"])
#
#        def fn(img: Any) -> np.ndarray:
#            if method == "background":
#                return algo_enhance.remove_background(img, size, keep_level=keep)
#            if method in ("stripes_h", "stripes_v"):
#                return algo_enhance.remove_stripes(
#                    img, axis=0 if method == "stripes_h" else 1,
#                    strength=strength)
#            out = algo_enhance.morph_residual(
#                img, size, dark=(method == "dark_spots"))
#            if keep:
#                # top-hat / black-hat 的輸出以 0 為基準；把原本的亮度加回去，
#                # 讓「輸出仍落在原本的灰階區間」這件事對五種方法都成立。
#                out = out + float(np.nanmean(np.asarray(img, dtype=np.float32)))
#            return out
#
#        return self._apply(ctx, p, fn)
#
#
#@register_step
#class LocalContrastStep(_StreamStep):
#    """CLAHE：分格子做直方圖等化，暗區裡的小缺陷也拉得起來。"""
#
#    key = "local_contrast"
#    label = "Normalize · Local contrast"
#    help = ("Stretch contrast tile by tile (CLAHE) instead of over the whole "
#            "image, so a faint defect sitting in a dark area becomes visible "
#            "- a global stretch can never do that.")
#    params = [
#        ParamSpec(name="target", type="image_key", default="test",
#                  label="Image stream", help=ONE_STREAM_HELP),
#        ParamSpec(
#            name="clip_limit", type="float", default=2.0, min=0.1, max=40.0,
#            label="Contrast limit",
#            help=("Ceiling on how much contrast one tile may gain. Raise it "
#                  "for more punch; too high and flat areas amplify their own "
#                  "noise until it looks like signal."),
#        ),
#        ParamSpec(
#            name="tiles", type="int", default=8, min=1, max=32,
#            label="Tiles per side",
#            help=("The image is divided into this many tiles across and down. "
#                  "More tiles follow local brightness more closely, but a "
#                  "defect larger than one tile starts being treated as "
#                  "background and fades out - lower this if that happens."),
#        ),
#    ]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        clip, tiles = float(p["clip_limit"]), int(p["tiles"])
#        return self._apply(
#            ctx, p, lambda img: algo_enhance.clahe(img, clip, tiles))
#
#F 4a209da9d5cab056640d43b23e440a353893b807 110 adept/core/steps/glv_stats.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""glv_stats — 灰階（GLV）統計卡。
#
#metrics 參數是逗號清單，每個 id 產生一個同名 feature：
#- 固定集：glv_mean / glv_median / glv_std / glv_min / glv_max / glv_q25 / glv_q75
#- 動態分位數：glv_q<NN>（例 glv_q90）
#- 別名：glv_p50 = glv_median；glv_p<NN> = glv_q<NN>
#feature 名稱「照使用者列的寫」（別名不改名），數值一致。
#"""
#from __future__ import annotations
#
#import re
#from typing import Any, Dict, List
#
#import numpy as np
#
#from ..algo import glv as algo_glv
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_MEASURE,
#)
#from ._util import (
#    crop_to_roi, output_prefix_spec, parse_key_list, prefix_features,
#    prefix_names, require_image,
#)
#
#_P_ALIAS = re.compile(r"^glv_p(\d+)$")
#_Q_FORM = re.compile(r"^glv_q(\d+)$")
#
#
#def _canonical(mid: str) -> str:
#    """把使用者寫的 metric id 轉成 algo.glv 認得的 id；不認得回傳空字串。"""
#    if mid in algo_glv.GLV_STATS:
#        return mid
#    if mid == "glv_p50":
#        return "glv_median"          # 慣用別名：P50 = 中位數
#    m = _P_ALIAS.match(mid)
#    if m and 0 <= int(m.group(1)) <= 100:
#        return f"glv_q{m.group(1)}"  # glv_pNN → glv_qNN
#    m = _Q_FORM.match(mid)
#    if m and 0 <= int(m.group(1)) <= 100:
#        return mid
#    return ""
#
#
#@register_step
#class GlvStatsStep(Step):
#    """GLV 統計：整張或中央方框的灰階統計量。"""
#
#    key = "glv_stats"
#    label = "Gray-level stats"
#    category = CATEGORY_ALGO
#    group = GROUP_MEASURE
#    help = ("Compute gray-level statistics (mean, standard deviation, "
#            "percentiles…) inside a region, and write each one out as a "
#            "feature.")
#    params = [
#        ParamSpec(name="source", type="image_key", default="test",
#                  help="Image stream to compute statistics on."),
#        ParamSpec(name="roi", type="str", default="",
#                  help=("Which region to measure in — the name given by a "
#                        "Define region card upstream. Leave empty for the "
#                        "whole image.")),
#        ParamSpec(name="metrics", type="str", default="glv_mean,glv_std,glv_p50",
#                  help=("Statistics to output (comma separated): glv_mean / "
#                        "glv_std / glv_median / glv_min / glv_max / glv_q25 / "
#                        "glv_q75. Percentiles can be written glv_q90 or glv_p90 "
#                        "(glv_p50 = median).")),
#        output_prefix_spec("center"),
#    ]
#    reads = ["test"]
#    writes: List[str] = []
#    features_out = ["glv_mean", "glv_std", "glv_p50"]
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("source", "test")]
#
#    @classmethod
#    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
#        name = str(params.get("roi", "") or "").strip()
#        return [name] if name else []
#
#    @classmethod
#    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
#        mids = parse_key_list(params.get("metrics", "glv_mean,glv_std,glv_p50"))
#        return prefix_names(params.get("output_prefix", ""),
#                            mids or list(cls.features_out))
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        img = require_image(ctx, self.key, p["source"])
#        mids = parse_key_list(p["metrics"])
#        if not mids:
#            raise StepError(self.key, "metrics is empty; list at least one statistic (e.g. glv_mean).")
#
#        patch = np.asarray(crop_to_roi(ctx, self.key, img, p["roi"]))
#
#        feats: Dict[str, float] = {}
#        for mid in mids:
#            canon = _canonical(mid)
#            if not canon:
#                raise StepError(
#                    self.key,
#                    f"unknown statistic '{mid}'; available: "
#                    f"{sorted(algo_glv.GLV_STATS)} or glv_q<0-100> / glv_p<0-100>.")
#            feats[mid] = algo_glv.glv_value(patch, canon)   # feature 名照使用者列的寫
#        ctx.add_features(prefix_features(p["output_prefix"], feats))
#        return ctx
#
#F 49a75b01392bbf66e936c2606f7b439b68f9dab9 272 adept/core/steps/golden.py
## ADEPT step-card library — authored 2026-07-28 (M4-1).
#"""Golden Cell 兩張卡：cell_period（週期估測）+ golden_cell（參考圖合成）。
#
#用途：Review SEM 這類**只有一張圖、沒有 ref**的資料，靠「圖上的 cell 會重複」
#這件事自己造一張參考圖 —— 把所有 cell 疊起來，缺陷只出現在其中一格，
#疊完就被平均/中位數洗掉，剩下乾淨的「標準 cell」。再把它鋪回原尺寸，
#就得到一張可以直接拿去 subtract 的 ref。
#
#兩張卡分開的原因：週期只跟「這一站的版圖」有關，一個 lot 內不會變，
#量一次（cell_period）寫進 ``ctx.meta["cell_period"]``，golden_cell 直接拿來用，
#不必每顆 defect 重算 FFT。單獨使用 golden_cell 也可以（它會自己估）。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List, Optional, Tuple
#
#import numpy as np
#
#from ..algo import golden as algo_golden
#from ..algo import period as algo_period
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_ALGO, CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_COMPARE, GROUP_MEASURE,
#)
#from ._util import ensure_gray, require_image, to_uint8
#
## 週期參數的共用上限：超過這個值的 cell 在 patch 影像上根本疊不出幾格。
#_MAX_PERIOD = 512
#
#
#def _opt(value: Any) -> Optional[int]:
#    """參數的 0 = 「自動」→ None；其餘轉 int。"""
#    v = int(value)
#    return v if v > 0 else None
#
#
#@register_step
#class CellPeriodStep(Step):
#    """量出圖上重複 cell 的 X/Y 週期（像素）。"""
#
#    key = "cell_period"
#    label = "Cell period"
#    category = CATEGORY_ALGO
#    group = GROUP_MEASURE
#    help = ("Measure the X/Y period of the repeating cells in the image (in "
#            "pixels) for the Golden Cell card, and report how trustworthy that "
#            "period is.")
#    params = [
#        ParamSpec(name="source", type="image_key", default="test",
#                  help="Image stream to measure the period on (usually test)."),
#        ParamSpec(name="min_period", type="int", default=0, min=0, max=_MAX_PERIOD,
#                  unit="px",
#                  help=("Minimum period in pixels; 0 = automatic. Set it when you "
#                        "know how small a cell can be, to avoid locking onto a "
#                        "small noise period.")),
#        ParamSpec(name="max_period", type="int", default=0, min=0, max=_MAX_PERIOD,
#                  unit="px",
#                  help=("Maximum period in pixels; 0 = automatic (half the image). "
#                        "Set it when you know how large a cell can be.")),
#        ParamSpec(name="refine", type="bool", default=True,
#                  help=("Whether to run a +/-2 pixel refinement search, picking the "
#                        "period that actually stacks sharpest. More accurate, "
#                        "slightly slower.")),
#    ]
#    reads = ["test"]
#    writes: List[str] = []
#    features_out = ["cell_px", "cell_py", "cell_conf_x", "cell_conf_y"]
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("source", "test")]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        lo, hi = _opt(p["min_period"]), _opt(p["max_period"])
#        if lo is not None and hi is not None and hi < lo:
#            raise StepError(self.key,
#                            f"max_period ({hi}) cannot be smaller than min_period "
#                            f"({lo}); swap the two values or set them to 0 (automatic).")
#        img = to_uint8(ensure_gray(require_image(ctx, self.key, p["source"])))
#
#        res = algo_period.estimate_period(img, min_period=lo, max_period=hi)
#        px, py = res.px, res.py
#
#        # 微調：用實際疊出來的清晰度在 ±2 像素內挑最好的週期（兩軸都有值才做）。
#        if p["refine"] and px is not None and py is not None:
#            px, py, _ = algo_golden.refine_period(img, px, py, search=2)
#
#        if px is None or py is None:
#            if px is None and py is None:
#                why = ("this image shows no periodic structure (no repeating "
#                       "cell found on either the X or the Y axis)")
#            else:
#                axis = "X" if px is not None else "Y"
#                other = "Y" if px is not None else "X"
#                why = (f"this image is periodic along {axis} only, with nothing "
#                       f"measurable along {other} (it may be a one-directional "
#                       f"layout such as line/space)")
#            ctx.warn(f"[{self.key}] {why}, so a full cell period cannot be "
#                     "measured. The Golden Cell route may not suit this layer — "
#                     "consider a comparison route that has a real ref image.")
#        ctx.meta["cell_period"] = {"px": int(px or 0), "py": int(py or 0)}
#        ctx.add_features({
#            "cell_px": float(px or 0),
#            "cell_py": float(py or 0),
#            "cell_conf_x": float(res.confidence_x),   # PeriodResult.confidence_x（0–100）
#            "cell_conf_y": float(res.confidence_y),   # PeriodResult.confidence_y（0–100）
#        })
#        return ctx
#
#
#@register_step
#class GoldenCellStep(Step):
#    """Golden Cell：把重複的 cell 疊成一張乾淨參考圖，再鋪回原尺寸。
#
#    輸出影像與 ``source`` **同尺寸、同 dtype**（下游 subtract 要求兩張圖
#    shape 完全相同）；彩色輸入會先轉灰階再複製回同樣的通道數。
#    """
#
#    key = "golden_cell"
#    label = "Golden Cell reference"
#    category = CATEGORY_IMAGE
#    group = GROUP_COMPARE
#    help = ("Stack the repeating cells into one clean reference image — use it "
#            "as the comparison baseline when there is no ref image (a single "
#            "Review SEM frame, for instance).")
#    requires_ref = False          # 這張卡是「製造 ref」的人，自己不需要 ref
#    params = [
#        ParamSpec(name="source", type="image_key", default="test",
#                  help="Image stream whose cells are stacked (usually test)."),
#        ParamSpec(name="out", type="image_key", default="ref",
#                  help=("Name of the image stream the synthetic reference goes "
#                        "to. Leave it at 'ref' and the align/subtract cards "
#                        "downstream need no changes at all.")),
#        ParamSpec(name="method", type="choice", default="median",
#                  choices=["mean", "median"],
#                  help=("Stacking method: median resists contamination by defects "
#                        "and is recommended; mean is faster and smoother.")),
#        ParamSpec(name="px", type="int", default=0, min=0, max=_MAX_PERIOD, unit="px",
#                  help=("Cell period along X in pixels; 0 = automatic (uses the "
#                        "cell_period card's result, or estimates its own).")),
#        ParamSpec(name="py", type="int", default=0, min=0, max=_MAX_PERIOD, unit="px",
#                  help=("Cell period along Y in pixels; 0 = automatic (uses the "
#                        "cell_period card's result, or estimates its own).")),
#        ParamSpec(name="phase_search", type="bool", default=True,
#                  help=("Find the lattice phase automatically (where to start "
#                        "cutting cells) so the stack does not come out blurred. "
#                        "Leave it on unless you are in a hurry.")),
#        ParamSpec(name="ghost_warn", type="float", default=0.0, min=0.0, max=100.0,
#                  help=("Warn when stack quality (golden_ghost, 0-100, higher is "
#                        "sharper) falls below this value; 0 = do not check.")),
#    ]
#    reads = ["test"]
#    writes = ["ref"]
#    features_out = ["golden_ghost", "golden_px", "golden_py"]
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("source", "test")]
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("out", "ref")]
#
#    # ---- 週期來源：參數 → cell_period 卡的 meta → 自己估 ----------------------
#    def _resolve_period(self, ctx: Context, p: Dict[str, Any],
#                        img: np.ndarray) -> Tuple[int, int]:
#        px, py = int(p["px"]), int(p["py"])
#        if px > 1 and py > 1:
#            return px, py
#
#        cached = ctx.meta.get("cell_period") or {}
#        if isinstance(cached, dict):
#            cx, cy = int(cached.get("px", 0) or 0), int(cached.get("py", 0) or 0)
#            if cx > 1 and cy > 1:
#                return (px if px > 1 else cx), (py if py > 1 else cy)
#
#        res = algo_period.estimate_period(img)
#        ex, ey = res.px, res.py
#        if px > 1:
#            ex = px
#        if py > 1:
#            ey = py
#        if ex is None or ey is None:
#            raise StepError(
#                self.key,
#                "no repeating cell structure found (at least one axis has no "
#                "measurable period), so a Golden Cell reference cannot be built. "
#                "This layer may simply not be a periodic layout — use a comparison "
#                "route with a real ref image (die-to-die / cell-to-cell), or enter "
#                "the known px / py in the parameters.")
#        return int(ex), int(ey)
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        src = require_image(ctx, self.key, p["source"])
#        gray = to_uint8(ensure_gray(src))
#        h, w = gray.shape[:2]
#
#        px, py = self._resolve_period(ctx, p, gray)
#        if px > w or py > h:
#            raise StepError(
#                self.key,
#                f"the cell period ({px}x{py} px) is larger than the image "
#                f"({w}x{h} px), so not a single cell can be stacked. Check the "
#                f"period parameters, or use a comparison route with a real ref "
#                f"image.")
#
#        origin = (0, 0)
#        if p["phase_search"]:
#            origin = algo_period.choose_origin(gray.shape, px, py, image=gray)
#
#        n_cells = len(algo_golden.tile_coords(gray.shape, px, py, origin))
#        if n_cells < 2:
#            raise StepError(
#                self.key,
#                f"the image fits only {n_cells} complete cell(s) (period "
#                f"{px}x{py} px), which is not enough for a meaningful reference. "
#                f"The image may be too small or not a periodic layout — use a "
#                f"comparison route with a real ref image.")
#
#        stacked = algo_golden.stack_cells(gray, px, py, method=p["method"],
#                                          origin=origin)
#        if stacked.shape[:2] != (py, px):   # 理論上不會發生；防呆
#            raise StepError(self.key, f"stacking failed (got {stacked.shape} instead of {(py, px)}).")
#
#        score, lap_var, edge_contrast = algo_golden.ghosting_score(stacked)
#
#        # 鋪回原尺寸：out[y, x] = stacked[(y - oy) % py, (x - ox) % px]
#        # → 與 source 同尺寸，且鋪出來的晶格與 source 同相位，可直接相減。
#        ox, oy = origin
#        xi = (np.arange(w) - ox) % px
#        yi = (np.arange(h) - oy) % py
#        tiled = stacked[np.ix_(yi, xi)]
#        ctx.set_image(p["out"], _match_source(tiled, src))
#
#        warn_at = float(p["ghost_warn"])
#        if warn_at > 0 and score < warn_at:
#            ctx.warn(f"[{self.key}] the stacked reference looks blurred "
#                     f"(golden_ghost={score:.1f} < {warn_at:g}): the period or "
#                     f"phase may be wrong, so treat the comparison with care.")
#
#        ctx.meta["golden_cell"] = {
#            "px": int(px), "py": int(py), "ox": int(ox), "oy": int(oy),
#            "method": str(p["method"]), "n_cells": int(n_cells),
#            "lap_var": float(lap_var), "edge_contrast": float(edge_contrast),
#        }
#        ctx.add_features({
#            "golden_ghost": float(score),   # 0–100，越高越清晰（ghosting 越少）
#            "golden_px": float(px),
#            "golden_py": float(py),
#        })
#        return ctx
#
#
#def _match_source(tiled: np.ndarray, src: np.ndarray) -> np.ndarray:
#    """把 uint8 的鋪圖還原成與 ``src`` 相同的 dtype／值域／通道數。
#
#    疊圖一律在 uint8 0–255 的值域做（週期分析的前提），但上游可能餵進
#    float32 0–1 的影像流；直接輸出 uint8 會讓下游 subtract 兩張圖差一個
#    255 倍。這裡照 ``_util.to_uint8`` 的相反規則還原。
#    """
#    out = tiled
#    if src.ndim == 3:
#        out = np.repeat(out[:, :, None], src.shape[2], axis=2)
#    if src.dtype == np.uint8:
#        return out.astype(np.uint8)
#    f = np.asarray(src, dtype=np.float32)
#    if f.size > 0 and float(f.min()) >= 0.0 and float(f.max()) <= 1.5:
#        return (out.astype(np.float32) / 255.0)
#    return out.astype(np.float32)
#
#F ee3627d1f9b02d3159009077e9b1b2cfc23272c3 142 adept/core/steps/load.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""load_patch — 載入影像卡。
#
#從 ``ctx.meta["_defect_item"]``（ingest 層的 DefectItem，由引擎放入）讀出
#這顆 defect 的各 channel 像素並寫進 ``ctx.images``。
#
#writes 說明：類別層級靜態宣告 ``writes=["test"]`` 只是保守下限——實際會寫哪些
#影像流取決於 ``channels`` 參數與資料本身（ebi_patch 通常是 test+ref；rsem 單張
#會寫 single 並同時鏡射一份到 test），由 ``resolve_writes`` 在拿到參數後盡力
#解析，"auto" 模式下仍以執行期為準。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_INPUT,
#)
#from ._util import ensure_gray, to_uint8
#
## "auto" 模式下 channel 的優先順序（其餘 channel 依名稱排序附加在後）
#_PREFERRED_ORDER = ("test", "ref", "single")
#
#
#@register_step
#class LoadPatchStep(Step):
#    """把 DefectItem 的影像載入成 Context 影像流（一律轉成 uint8 灰階）。"""
#
#    key = "load_patch"
#    label = "Load images"
#    category = CATEGORY_IMAGE
#    group = GROUP_INPUT
#    help = ("Load this defect's images (test/ref, or a single image) into the "
#            "pipeline, always converted to 8-bit grayscale.")
#    params = [
#        ParamSpec(
#            name="channels", type="str", default="auto",
#            help=("Which images to load: auto = whatever is available "
#                  "(a single RSEM image is also exposed as test); or a comma "
#                  "separated list such as test,ref."),
#        ),
#    ]
#    reads: List[str] = []
#    writes = ["test"]            # 保守靜態宣告；實際流以執行期解析為準（見模組 docstring）
#    features_out = ["n_channels"]
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        raw = str(params.get("channels", "auto")).strip()
#        if raw.lower() == "auto":
#            return list(cls.writes)     # auto：靜態下限，實際以執行期為準
#        return [tok.strip() for tok in raw.split(",") if tok.strip()] or list(cls.writes)
#
#    @classmethod
#    def resolve_writes_for_kind(cls, params: Dict[str, Any], kind: str) -> List[str]:
#        """validate 用的 kind-aware 宣告：ebi_patch → test+ref；rsem → single+test。"""
#        raw = str(params.get("channels", "auto")).strip()
#        if raw.lower() != "auto":
#            return cls.resolve_writes(params)
#        if kind == "ebi_patch":
#            return ["test", "ref"]
#        if kind == "rsem":
#            return ["single", "test"]   # single 會鏡射為 test（見 run()）
#        return list(cls.writes)
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        item = ctx.meta.get("_defect_item")
#        kind = ctx.meta.get("_dataset_kind")
#        if item is None:
#            raise StepError(self.key, "no defect data in the Context (meta['_defect_item']); this "
#                            "card must be run by the engine after a dataset is loaded.")
#        images = getattr(item, "images", None)
#        if not images:
#            raise StepError(self.key, f"defect {getattr(item, 'defect_id', '?')} has no images to load.")
#
#        raw = str(p["channels"]).strip()
#        if raw.lower() == "auto":
#            avail = list(images.keys())
#            wanted = [c for c in _PREFERRED_ORDER if c in avail]
#            wanted += sorted(c for c in avail if c not in wanted)
#        else:
#            wanted = [tok.strip() for tok in raw.split(",") if tok.strip()]
#            if not wanted:
#                raise StepError(self.key, "the channels parameter is empty; use auto or a comma "
#                                "separated list (e.g. test,ref).")
#
#        loaded: List[str] = []
#        for ch in wanted:
#            if ch not in images:
#                raise StepError(
#                    self.key,
#                    f"defect {getattr(item, 'defect_id', '?')} has no channel "
#                    f"'{ch}' (available: {sorted(images)}).")
#            try:
#                arr = item.load(ch)
#            except Exception as e:  # 檔案毀損 / 頁碼超界等
#                raise StepError(self.key, f"could not read channel '{ch}': {e}") from e
#            arr_u8 = to_uint8(ensure_gray(arr))
#            ctx.set_image(ch, arr_u8)
#            loaded.append(ch)
#
#        # rsem / folder 單張資料流：把 single 同時鏡射為 test，讓下游卡片
#        # 用預設參數（source="test"）就能直接吃到影像。
#        if "single" in loaded and "test" not in ctx.images:
#            ctx.set_image("test", ctx.images["single"])
#            note = (f"single-image input (kind={kind}): 'single' is also "
#                    f"exposed as 'test' for downstream cards.")
#            ctx.meta.setdefault("notes", []).append(note)
#
#        # 面板用（F7-17）：**每條影像流是從哪一頁來的、載進來長什麼樣**。
#        #
#        # 這不是裝飾。「每顆 defect 第一張是 test、第二張是 ref」是全專案第一條
#        # 待廠內驗證的假設（CLAUDE.md §8），而目前唯一的驗證方式是另外跑
#        # fab_probe 腳本。把配對與每一頁的平均灰階直接攤在畫面上，使用者載入
#        # 第一份真資料的當下就會看到「咦，第二張比較亮」—— 那就是順序反了的證據。
#        pages = []
#        for ch in loaded:
#            ref = images.get(ch)
#            arr = ctx.images.get(ch)
#            pages.append({
#                "channel": ch,
#                "page": None if ref is None else getattr(ref, "page", None),
#                "file": "" if ref is None else str(getattr(ref, "path", "")),
#                "shape": None if arr is None else [int(v) for v in arr.shape[:2]],
#                "mean": None if arr is None else float(arr.mean()),
#            })
#        ctx.meta["input"] = {
#            "kind": str(kind or ""),
#            "defect_id": str(getattr(item, "defect_id", "")),
#            "die": list(getattr(item, "die", None) or []),
#            "xrel_nm": getattr(item, "xrel_nm", None),
#            "yrel_nm": getattr(item, "yrel_nm", None),
#            "klarf_row": int(getattr(item, "klarf_row", -1)),
#            "nm_per_px": getattr(item, "nm_per_px", None),
#            "pages": pages,
#        }
#
#        ctx.add_feature("n_channels", float(len(loaded)))
#        return ctx
#
#F 4ef457b2fd7ce6725fce2e2edaea7d83316e8c40 207 adept/core/steps/normalize.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""亮度正規化卡片：percentile_norm / glv_mask_norm / hist_match。
#
#三張卡都是「把圖的亮度拉到可以互相比較」的影像段工具：
#- percentile_norm：百分位拉伸（P2–P98 → 0–255）。
#- glv_mask_norm  ：只用指定灰階帶（GLV band）內的像素估計拉伸範圍。
#- hist_match     ：把 moving 影像的直方圖對齊到 reference 影像。
#
#輸出一律 uint8 0–255。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#import numpy as np
#
#from ..algo import histmatch as algo_histmatch
#from ..algo import normalize as algo_normalize
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_IMAGE, ParamSpec, Step, StepError, register_step, GROUP_ENHANCE,
#)
#from ._util import ONE_STREAM_HELP, require_image, to_uint8
#
#
#def _norm_to_u8(img: np.ndarray, lo: float, hi: float) -> np.ndarray:
#    """套用範圍正規化並轉 uint8 0–255。"""
#    out01 = algo_normalize.normalize_image_with_range(img.astype(np.float32), lo, hi)
#    return (np.clip(out01, 0.0, 1.0) * 255.0).astype(np.uint8)
#
#
##: ``range_from`` 的說明（``source`` 用共用的 :data:`ONE_STREAM_HELP`）。
##:
##: 這兩張卡以前是「主流 + also_apply 清單 + anchor」三個參數擠在控制列上，
##: 而使用者在畫布上想的是節點：**一張卡做一條流**，要對 ref 也做就再放一張卡。
##: 唯一會掉的能力是 ``anchor="source"``（ref 借 test 量出來的範圍，這是
##: 「兩張圖還比得起來」的關鍵），所以那件事升成一個看得見的參數 ``range_from``
##: —— 它是**一條影像流的名字**，在畫布上就是接進這張卡的第二條線。
#_RANGE_FROM_HELP = (
#    "Leave empty and the stretch range is measured on this card's own stream. "
#    "Name another stream to reuse that stream's range instead - that is what "
#    "keeps test and ref comparable when each one is normalized by its own "
#    "card. Put this card BEFORE the card that normalizes the stream you are "
#    "borrowing from, so the range is measured on the original image.")
#
#
#def _stream_reads(params: Dict[str, Any]) -> List[str]:
#    """這張卡讀哪幾條流：自己那條，加上（有填的話）借範圍的那條。"""
#    keys = [str(params.get("source", "test"))]
#    borrow = str(params.get("range_from", "") or "").strip()
#    if borrow and borrow not in keys:
#        keys.append(borrow)
#    return keys
#
#
#def _range_basis(ctx: Context, step_key: str, params: Dict[str, Any],
#                 src: np.ndarray) -> np.ndarray:
#    """量拉伸範圍要看哪一張圖：預設是自己，填了 ``range_from`` 就是那一條。
#
#    借不到（那條流不存在）就**報錯**，不靜靜改用自己的範圍 —— 兩者的輸出都
#    是一張看起來很正常的圖，差別只在數字，而那正是使用者看不出來的那種錯。
#    """
#    borrow = str(params.get("range_from", "") or "").strip()
#    if not borrow or borrow == str(params.get("source", "")):
#        return src
#    return require_image(ctx, step_key, borrow)
#
#
#@register_step
#class PercentileNormStep(Step):
#    """百分位正規化：P_low–P_high 拉伸到 0–255。"""
#
#    key = "percentile_norm"
#    label = "Normalize · Percentile"
#    category = CATEGORY_IMAGE
#    group = GROUP_ENHANCE
#    help = ("Stretch image brightness over a percentile range (P2-P98 by "
#            "default) to 0-255, removing brightness drift.")
#    params = [
#        ParamSpec(name="source", type="image_key", default="test",
#                  label="Image stream", help=ONE_STREAM_HELP),
#        ParamSpec(name="range_from", type="image_key", default="",
#                  label="Borrow range from", help=_RANGE_FROM_HELP),
#        ParamSpec(name="p_low", type="float", default=2.0, min=0.0, max=50.0,
#                  help=("Lower percentile (0-50): pixels below it are clipped "
#                        "to 0.")),
#        ParamSpec(name="p_high", type="float", default=98.0, min=50.0, max=100.0,
#                  help=("Upper percentile (50-100): pixels above it are clipped "
#                        "to 255.")),
#    ]
#    reads = ["test"]
#    writes = ["test"]
#    features_out: List[str] = []
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return _stream_reads(params)
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return [str(params.get("source", "test"))]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        if p["p_low"] >= p["p_high"]:
#            raise StepError(self.key, f"p_low ({p['p_low']}) must be smaller than p_high "
#                            f"({p['p_high']}).")
#        src = require_image(ctx, self.key, p["source"])
#        basis = _range_basis(ctx, self.key, p, src)
#        lo, hi = algo_normalize.percentile_range(basis, p["p_low"], p["p_high"])
#        ctx.set_image(p["source"], _norm_to_u8(src, lo, hi))
#        return ctx
#
#
#@register_step
#class GlvMaskNormStep(Step):
#    """GLV 帶正規化：只用指定灰階範圍內的像素估計拉伸範圍。"""
#
#    key = "glv_mask_norm"
#    label = "Normalize · GLV band"
#    category = CATEGORY_IMAGE
#    group = GROUP_ENHANCE
#    help = ("Estimate the brightness range from pixels inside a chosen gray "
#            "band only, then stretch to 0-255 — this locks onto the brightness "
#            "of one particular pattern.")
#    params = [
#        ParamSpec(name="source", type="image_key", default="test",
#                  label="Image stream", help=ONE_STREAM_HELP),
#        ParamSpec(name="range_from", type="image_key", default="",
#                  label="Borrow range from", help=_RANGE_FROM_HELP),
#        ParamSpec(name="glv_low", type="int", default=0, min=0, max=255,
#                  help=("Lower edge of the gray band (0-255): only pixels inside "
#                        "the band take part in the range estimate.")),
#        ParamSpec(name="glv_high", type="int", default=255, min=0, max=255,
#                  help=("Upper edge of the gray band (0-255); must be greater "
#                        "than or equal to glv_low.")),
#    ]
#    reads = ["test"]
#    writes = ["test"]
#    features_out: List[str] = []
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return _stream_reads(params)
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return [str(params.get("source", "test"))]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        if p["glv_low"] > p["glv_high"]:
#            raise StepError(self.key, f"glv_low ({p['glv_low']}) cannot be greater than "
#                            f"glv_high ({p['glv_high']}).")
#        src = require_image(ctx, self.key, p["source"])
#        basis = _range_basis(ctx, self.key, p, src)
#        lo, hi = algo_normalize.percentile_range_glv_masked(
#            basis.astype(np.float32), p["glv_low"], p["glv_high"])
#        ctx.set_image(p["source"], _norm_to_u8(src, lo, hi))
#        return ctx
#
#
#@register_step
#class HistMatchStep(Step):
#    """直方圖匹配：把 moving 的亮度分布對齊到 reference。"""
#
#    key = "hist_match"
#    label = "Normalize · Histogram match"
#    category = CATEGORY_IMAGE
#    group = GROUP_ENHANCE
#    help = ("Match the moving image's brightness distribution to the reference "
#            "image so the two can be subtracted directly.")
#    requires_ref = True
#    params = [
#        ParamSpec(name="moving", type="image_key", default="test",
#                  label="Adjust this stream",
#                  help=("Image stream whose brightness is adjusted (the result "
#                        "overwrites the same stream).")),
#        ParamSpec(name="reference", type="image_key", default="ref",
#                  label="Match it to",
#                  help="Brightness reference stream (never modified)."),
#        ParamSpec(name="method", type="choice", default="linear",
#                  choices=["exact", "linear", "percentile"],
#                  help=("Matching method: linear = align mean/standard deviation "
#                        "(most natural); exact = identical histograms; "
#                        "percentile = align P2-P98 (robust to outliers).")),
#    ]
#    reads = ["test", "ref"]
#    writes = ["test"]
#    features_out: List[str] = []
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("moving", "test"), params.get("reference", "ref")]
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("moving", "test")]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        mov = to_uint8(require_image(ctx, self.key, p["moving"]))
#        ref = to_uint8(require_image(ctx, self.key, p["reference"]))
#        fn = algo_histmatch.MATCH_FN[p["method"]]
#        ctx.set_image(p["moving"], fn(mov, ref))
#        return ctx
#
#F 6e906a1610e0dfc2de6ecfee1773cd78652035a2 56 adept/core/steps/quality.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""focus_quality — 影像品質（對焦）量測卡。"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#from ..algo import quality as algo_quality
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_MEASURE,
#)
#from ._util import (
#    output_prefix_spec, prefix_features, prefix_names, require_image,
#)
#
#
#@register_step
#class FocusQualityStep(Step):
#    """對焦品質：Laplacian 變異數 / Tenengrad / FFT 高頻比。"""
#
#    key = "focus_quality"
#    label = "Focus quality"
#    category = CATEGORY_ALGO
#    group = GROUP_MEASURE
#    help = ("Measure image sharpness with three metrics — higher is sharper. "
#            "Useful for screening out defocused images.")
#    params = [
#        ParamSpec(name="source", type="image_key", default="test",
#                  help="Image stream to measure sharpness on."),
#        output_prefix_spec("test"),
#    ]
#    reads = ["test"]
#    writes: List[str] = []
#    features_out = ["focus_lapvar", "focus_tenengrad", "focus_fft"]
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("source", "test")]
#
#    @classmethod
#    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
#        return prefix_names(params.get("output_prefix", ""), cls.features_out)
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        img = require_image(ctx, self.key, p["source"])
#        q = algo_quality.compute_quality(img)
#        if q.get("error"):
#            raise StepError(self.key, f"image quality computation failed: {q['error']}")
#        ctx.add_features(prefix_features(p["output_prefix"], {
#            "focus_lapvar": q["laplacian_var"],
#            "focus_tenengrad": q["tenengrad"],
#            "focus_fft": q["fft_hf_ratio"],
#        }))
#        return ctx
#
#F 6d7694b11ba4a9a7466b8d9233bcff10db8c5c12 126 adept/core/steps/region.py
## ADEPT step-card library — authored 2026-07-28 (F7-4).
#"""region — Region 段：決定「要看哪裡」。
#
#為什麼 ROI 值得升成一級概念
#---------------------------
#在 F7-4 之前，ROI 是**藏在每張量測卡裡的參數**（``glv_stats`` 有
#``region`` / ``box_size``、``roi_snr`` 有 ``mode`` / ``box_size``）。同一個
#「要看哪裡」被複製在好幾張卡上，各自有自己的幾何參數 —— 這正是
#``CLAUDE.md`` §7 記載的坑：同一組中心框參數在 128² patch 上準、
#換成 256² 就漏抓。
#
#現在改成：Region 卡把 ROI 寫進 ``ctx.rois``（具名），量測卡只說「我要量
#哪一個 ROI」。改一次框，所有量測跟著動。
#
#patch 的兩個座標系（重要）
#--------------------------
#機台的裁切是「**以 defect 座標為正中心，裁 x×x 像素**」，於是：
#
#* **defect frame** —— 原點在 patch 正中心。缺陷永遠在這裡（裁切方式保證的），
#  所以中心框、整張圖這類 ROI **跨 defect 穩定**。本卡只做這個座標系。
#* **pattern frame** —— 原點在版圖晶格。裁切中心是 defect 而不是晶格，
#  所以晶格相位逐顆不同，「量線寬內部」這種 ROI 得先認出晶格在哪。
#  那要靠 ``algo/period.py`` 的 ``estimate_period`` / ``choose_origin``，
#  **尚未實作**（見 ``docs/plans/F7-canvas-and-taxonomy.md`` §4）。
#
#尺寸單位可以選 ``percent``
#--------------------------
#``size_unit="percent"`` 時框的大小是**影像邊長的百分比**，所以同一份 recipe
#換 patch 尺寸不會失效 —— 那是上面那個坑的正解。預設仍是 ``px``，
#因為使用者腦中想的通常是像素。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_ALGO, GROUP_REGION, ParamSpec, Step, StepError, register_step,
#)
#from ._util import require_image
#
#__all__ = ["RegionDefineStep", "center_norm_rect"]
#
#
#def center_norm_rect(shape: Any, size: float, unit: str = "px") -> tuple:
#    """置中方框的正規化矩形 ``(nx, ny, nw, nh)``。
#
#    ``unit="px"`` -> ``size`` 是像素邊長；``unit="percent"`` -> 影像邊長的百分比。
#    邊長會夾在 1 像素與整張影像之間，所以參數填爆也不會產生無效的框。
#    """
#    h, w = int(shape[0]), int(shape[1])
#    if str(unit) == "percent":
#        pw = w * float(size) / 100.0
#        ph = h * float(size) / 100.0
#    else:
#        pw = ph = float(size)
#    pw = max(1.0, min(pw, float(w)))
#    ph = max(1.0, min(ph, float(h)))
#    nx = max(0.0, (w - pw) / 2.0 / w)
#    ny = max(0.0, (h - ph) / 2.0 / h)
#    return (nx, ny, pw / w, ph / h)
#
#
#@register_step
#class RegionDefineStep(Step):
#    """定義一個具名 ROI（defect 座標系）。"""
#
#    key = "roi_define"
#    label = "Define region"
#    category = CATEGORY_ALGO
#    group = GROUP_REGION
#    help = ("Mark the part of the image that later Measure cards should look "
#            "at, and give it a name.")
#    params = [
#        ParamSpec(name="name", type="str", default="main",
#                  help=("Name for this region. Measure cards refer to it by "
#                        "this name.")),
#        ParamSpec(name="shape", type="choice", default="center",
#                  choices=["center", "whole"],
#                  help=("center = a box in the middle of the patch, which is "
#                        "where the tool put the defect; whole = the entire "
#                        "image.")),
#        ParamSpec(name="size", type="float", default=32.0, min=1.0, max=100000.0,
#                  help="Side length of the centre box (ignored when shape = whole)."),
#        ParamSpec(name="size_unit", type="choice", default="px",
#                  choices=["px", "percent"],
#                  help=("px = size is in pixels; percent = size is a "
#                        "percentage of the image side, so the same recipe "
#                        "still works when the patch size changes.")),
#        ParamSpec(name="source", type="image_key", default="test",
#                  help=("Which image stream sets the geometry. Any stream of "
#                        "the same size will do; this only decides the size.")),
#    ]
#    reads = ["test"]
#    writes: List[str] = []
#    features_out: List[str] = []
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [str(params.get("source", "test"))]
#
#    @classmethod
#    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
#        name = str(params.get("name", "") or "").strip()
#        return [name] if name else []
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        name = str(p["name"]).strip()
#        if not name:
#            raise StepError(self.key, "the region name must not be empty.")
#
#        img = require_image(ctx, self.key, p["source"])
#        shape = img.shape[:2]
#        if str(p["shape"]) == "whole":
#            rect = (0.0, 0.0, 1.0, 1.0)
#        else:
#            rect = center_norm_rect(shape, float(p["size"]), str(p["size_unit"]))
#
#        ctx.set_roi(name, rect)
#        x, y, w, h = ctx.roi_rect(name, shape)
#        ctx.meta.setdefault("regions", {})[name] = {
#            "shape": str(p["shape"]), "rect_px": [int(x), int(y), int(w), int(h)],
#        }
#        return ctx
#
#F 91d3b4da2de3313df2fadb2ac2015ca5ffa81449 237 adept/core/steps/roi_profile.py
## ADEPT step-card library — authored 2026-07-29 (F7-11).
#"""roi_profile —— 用一維投影找出結構，再從結構上切出具名區域。
#
#這張卡在解什麼問題
#------------------
#patch 是機台**以缺陷為正中心**裁出來的，所以缺陷永遠在中央 —— 但缺陷**周圍**
#的東西每張都不一樣：同一批裡有的缺陷落在結構正中間，有的靠邊，有的旁邊就是
#另一種材質。於是「中心固定框」只對缺陷本身成立；只要框大過缺陷，它就可能在
#某些 patch 上吃進別種材質，量出來的數字忽高忽低，而**變動的原因不是缺陷**。
#
#所以要先找到結構在哪，再把框放在**結構的**某個位置上，而不是畫面的某個位置。
#
#做法與取捨都寫在 ``algo/profile.py`` 的模組說明裡（為什麼找轉折而不是分材質、
#為什麼在 ref 上做、什麼時候一定會失敗）。這裡只負責把它接成一張卡。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#from ..algo import profile as algo_profile
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_ALGO, GROUP_REGION, ParamSpec, Step, StepError, register_step,
#)
#from ._util import (
#    FEATURE_PREFIX_PATTERN, output_prefix_spec, prefix_features, prefix_names,
#    require_image,
#)
#
#
#def _band_rect(band, length: int, axis: str):
#    """一段（沿投影方向的 [start, end)）→ 正規化矩形 (nx, ny, nw, nh)。
#
#    另一個方向取滿：投影只知道「沿著這條軸的哪一段」，對另一個方向一無所知，
#    硬給一個高度等於憑空捏造資訊。
#    """
#    a, b = int(band[0]), int(band[1])
#    n = max(1, int(length))
#    lo, span = a / n, max(1, b - a) / n
#    if str(axis) == algo_profile.AXIS_X:
#        return (lo, 0.0, span, 1.0)
#    return (0.0, lo, 1.0, span)
#
#
#@register_step
#class RoiProfileStep(Step):
#    """投影定位：把影像壓成曲線、找轉折、挑一段當作具名區域。"""
#
#    key = "roi_profile"
#    label = "Locate region by profile"
#    category = CATEGORY_ALGO
#    group = GROUP_REGION
#    help = ("Find the structure in the image by flattening it into a curve and "
#            "looking for the places where it changes, then use one of those "
#            "sections as the region to measure - so the region follows the "
#            "pattern instead of sitting at a fixed spot on the screen.")
#    params = [
#        ParamSpec(
#            name="source", type="image_key", default="ref",
#            label="Find the structure in",
#            help=("Which image stream to look for the structure in. Use ref: "
#                  "it has no defect on it, so nothing is interfering with the "
#                  "search, and the pair is already aligned so the answer "
#                  "applies to test as well."),
#        ),
#        ParamSpec(
#            name="axis", type="choice", default="x", choices=["x", "y"],
#            label="Scan direction",
#            help=("x = flatten each column into one value, which finds "
#                  "structure boundaries running up and down; y = the other way "
#                  "round, for boundaries running left to right."),
#        ),
#        ParamSpec(
#            name="sensitivity", type="float", default=0.35, min=0.0, max=1.0,
#            label="Edge sensitivity",
#            help=("How steep a change counts as a boundary, compared with the "
#                  "steepest change in this image. Lower finds more boundaries, "
#                  "higher finds only the strongest. Watch the curve panel and "
#                  "drag until the lines land where you expect."),
#        ),
#        ParamSpec(
#            name="smooth", type="int", default=3, min=1, max=99, unit="px",
#            label="Curve smoothing",
#            help=("Smooth the curve before looking for boundaries. Too little "
#                  "and image noise becomes false boundaries; too much and real "
#                  "boundaries get rounded away."),
#        ),
#        ParamSpec(
#            name="min_gap", type="int", default=4, min=1, max=500, unit="px",
#            label="Minimum spacing",
#            help=("How far apart two boundaries must be. One real boundary "
#                  "spans several pixels, so without this it gets counted "
#                  "several times."),
#        ),
#        ParamSpec(
#            name="rule", type="choice", default="center",
#            choices=list(algo_profile.PICK_RULES),
#            label="Which section",
#            help=("center = the section the defect sits in (the defect is "
#                  "always at the middle of the patch, so this is the usual "
#                  "choice); widest / darkest / brightest = pick by that "
#                  "property; index = count sections from the left."),
#        ),
#        ParamSpec(
#            name="index", type="int", default=0, min=-99, max=99,
#            label="Section number",
#            help=("Only used when the rule above is 'index'. 0 is the leftmost "
#                  "section; negative counts from the right."),
#        ),
#        ParamSpec(
#            name="roi_out", type="str", default="band",
#            label="Name this region", pattern=FEATURE_PREFIX_PATTERN,
#            pattern_help=("use letters, digits and underscores only, and do "
#                          "not start with a digit"),
#            help=("Name for the section that was picked. Measure cards refer "
#                  "to it by this name."),
#        ),
#        ParamSpec(
#            name="also_neighbours", type="bool", default=False,
#            label="Also name the sections either side",
#            help=("Also produce <name>_before and <name>_after for the "
#                  "sections next to the chosen one. Measuring a defect against "
#                  "the neighbouring material is usually more meaningful than "
#                  "measuring it against a fixed box that may contain anything."),
#        ),
#        ParamSpec(
#            name="min_confidence", type="float", default=5.0, min=0.0, max=200.0,
#            label="Give up below",
#            help=("How much of the curve must be real signal rather than "
#                  "noise. Some patches sit entirely inside one material and "
#                  "have nothing to lock onto - those cannot be located by any "
#                  "method, so this card falls back to the whole image and "
#                  "marks the defect instead of guessing. A featureless patch "
#                  "scores about 1; anything with structure scores 20 or more."),
#        ),
#        output_prefix_spec("band"),
#    ]
#    reads = ["ref"]
#    writes: List[str] = []
#    features_out = ["band_center_px", "band_width_px", "band_dist_px",
#                    "band_count", "locate_conf", "locate_ok"]
#
#    # ---- 宣告（給 lint / UI）------------------------------------------------
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [str(params.get("source", "ref"))]
#
#    @classmethod
#    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
#        name = str(params.get("roi_out", "band") or "").strip()
#        if not name:
#            return []
#        out = [name]
#        if bool(params.get("also_neighbours", False)):
#            out += [f"{name}_before", f"{name}_after"]
#        return out
#
#    @classmethod
#    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
#        return prefix_names(params.get("output_prefix", ""), cls.features_out)
#
#    # ---- 執行 ---------------------------------------------------------------
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        name = str(p["roi_out"]).strip()
#        if not name:
#            raise StepError(self.key, "the region name must not be empty.")
#
#        img = require_image(ctx, self.key, p["source"])
#        res = algo_profile.locate(
#            img, axis=str(p["axis"]), sensitivity=float(p["sensitivity"]),
#            smooth=int(p["smooth"]), min_gap=int(p["min_gap"]),
#            rule=str(p["rule"]), index=int(p["index"]))
#
#        # panel 用的原始資料。**UI 畫的就是引擎算的這一份** —— UI 自己再算一次
#        # 很容易變成「畫面上的框」與「真的量下去的框」不一樣，那種 bug 極難發現。
#        ctx.meta.setdefault("profiles", {})[name] = {
#            "axis": res.axis,
#            "profile": [float(v) for v in res.profile],
#            "raw": [float(v) for v in res.raw],
#            "transitions": [int(t) for t in res.transitions],
#            "bands": [[int(a), int(b)] for a, b in res.bands],
#            "picked": None if res.picked is None else [int(res.picked[0]),
#                                                      int(res.picked[1])],
#            "confidence": float(res.confidence),
#        }
#
#        located = (res.picked is not None
#                   and res.confidence >= float(p["min_confidence"]))
#        length = res.length
#
#        if not located:
#            # 定位不出來就退回整張圖，**而且說出來**。整張都是同一種材質的 patch
#            # 本來就不需要定位（整張量是對的），但那跟「有結構卻沒找到」是兩件事，
#            # 使用者必須分得出來自己拿到的是哪一種。
#            ctx.warn(f"[{self.key}] no clear boundary in '{p['source']}' "
#                     f"(confidence {res.confidence:.1f} < "
#                     f"{float(p['min_confidence']):.1f}); region '{name}' falls "
#                     f"back to the whole image and this defect is marked "
#                     f"locate_ok = 0.")
#            ctx.set_roi(name, (0.0, 0.0, 1.0, 1.0))
#            if bool(p["also_neighbours"]):
#                ctx.set_roi(f"{name}_before", (0.0, 0.0, 1.0, 1.0))
#                ctx.set_roi(f"{name}_after", (0.0, 0.0, 1.0, 1.0))
#            ctx.add_features(prefix_features(p["output_prefix"], {
#                "band_center_px": length / 2.0,
#                "band_width_px": float(length),
#                "band_dist_px": -1.0,
#                "band_count": float(len(res.bands)),
#                "locate_conf": float(res.confidence),
#                "locate_ok": 0.0,
#            }))
#            return ctx
#
#        a, b = res.picked
#        ctx.set_roi(name, _band_rect((a, b), length, res.axis))
#
#        if bool(p["also_neighbours"]):
#            i = res.bands.index(res.picked)
#            before = res.bands[i - 1] if i > 0 else res.picked
#            after = res.bands[i + 1] if i + 1 < len(res.bands) else res.picked
#            ctx.set_roi(f"{name}_before", _band_rect(before, length, res.axis))
#            ctx.set_roi(f"{name}_after", _band_rect(after, length, res.axis))
#
#        dist = algo_profile.distance_to_nearest_transition(res)
#        ctx.add_features(prefix_features(p["output_prefix"], {
#            "band_center_px": (a + b) / 2.0,
#            "band_width_px": float(b - a),
#            # 缺陷離最近一條邊界多遠 —— 落在結構正中間跟落在交界上，
#            # 通常不是同一回事，所以這本身就是一個可以拿去打分的數字。
#            "band_dist_px": -1.0 if dist == float("inf") else float(dist),
#            "band_count": float(len(res.bands)),
#            "locate_conf": float(res.confidence),
#            "locate_ok": 1.0,
#        }))
#        return ctx
#
#F f620810659b803d1d9efba0b4ccf6f1c53a92ea1 95 adept/core/steps/roi_snr.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""roi_snr — ROI SNR 量測卡。
#
#在指定影像流上對一個 ROI（最大 blob 的 bbox，或影像中央固定方框）量
#訊噪比與相關統計。roi_snr_signed 沿用 e-beam 正負號慣例：比背景暗的
#缺陷是負值。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#from ..algo import snr as algo_snr
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_ALGO, ParamSpec, Step, register_step, GROUP_MEASURE,
#)
#from ._util import (
#    output_prefix_spec, prefix_features, prefix_names, require_image,
#    roi_rect_or_none,
#)
#
#_ZERO = {"roi_snr_signed": 0.0, "roi_snr_abs": 0.0, "roi_contrast": 0.0,
#         "roi_edge_sharpness": 0.0, "roi_dvi": 0.0}
#
#
#@register_step
#class RoiSnrStep(Step):
#    """ROI SNR：缺陷區對周邊背景的訊噪比與對比統計。"""
#
#    key = "roi_snr"
#    label = "ROI SNR"
#    category = CATEGORY_ALGO
#    group = GROUP_MEASURE
#    help = ("Measure the defect region's signal-to-noise against the "
#            "surrounding background (signed — dark defects are negative), "
#            "plus contrast and edge sharpness.")
#    params = [
#        ParamSpec(name="source", type="image_key", default="diff",
#                  help=("Image stream to measure on (usually diff; leave diff "
#                        "unsigned to keep bright/dark direction visible).")),
#        ParamSpec(name="roi", type="str", default="blob",
#                  help=("Which region to measure in — the name given by a "
#                        "Define region card, or 'blob' for the main blob found "
#                        "by Blob segment. Leave empty for the whole image.")),
#        ParamSpec(name="background_margin", type="int", default=20, min=1, max=200,
#                  help=("Background sampling width in pixels: the ring outside the "
#                        "ROI used for background statistics.")),
#        output_prefix_spec("blob"),
#    ]
#    reads = ["diff"]
#    writes: List[str] = []
#    features_out = ["roi_snr_signed", "roi_snr_abs", "roi_contrast",
#                    "roi_edge_sharpness", "roi_dvi"]
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("source", "diff")]
#
#    @classmethod
#    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
#        return prefix_names(params.get("output_prefix", ""), cls.features_out)
#
#    @classmethod
#    def resolve_regions_in(cls, params: Dict[str, Any]) -> List[str]:
#        name = str(params.get("roi", "blob") or "").strip()
#        return [name] if name else []
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        img = require_image(ctx, self.key, p["source"])
#
#        rect = roi_rect_or_none(ctx, self.key, img, p["roi"])
#        if rect is None:
#            ctx.warn(f"[{self.key}] no blob found (run Blob segment first, or "
#                     f"point roi at a Define region card); all ROI SNR "
#                     f"features recorded as 0.")
#            ctx.add_features(prefix_features(p["output_prefix"], _ZERO))
#            return ctx
#
#        res = algo_snr.roi_snr(img, rect, background_margin=int(p["background_margin"]))
#        if res is None:
#            ctx.warn(f"[{self.key}] ROI {rect} is outside the image or invalid; "
#                     f"all ROI SNR features recorded as 0.")
#            ctx.add_features(prefix_features(p["output_prefix"], _ZERO))
#            return ctx
#
#        ctx.add_features(prefix_features(p["output_prefix"], {
#            "roi_snr_signed": res.snr_signed,
#            "roi_snr_abs": res.snr_abs,
#            "roi_contrast": res.contrast,
#            "roi_edge_sharpness": res.edge_sharpness,
#            "roi_dvi": res.dvi,
#        }))
#        return ctx
#
#F 8dcba6fbbf0c970249fc83b0b8e6ac925c07ba74 246 adept/core/steps/roi_template.py
## ADEPT step-card library — authored 2026-07-29 (F7-12).
#"""roi_template —— 用 Golden Cell 模板把每張 patch 對回版圖的相位，再放框。
#
#跟投影定位（``roi_profile``）的分工
#-----------------------------------
#兩張卡解的是同一個問題（結構在每張 patch 裡的位置不一樣），差別在**資訊從哪來**：
#
#* **投影定位**只看 patch 自己。便宜、不需要任何額外檔案，但只有在 patch 裡看得到
#  地標時才定得出來。
#* **模板定位**（這張）用大圖疊出來的一個完整週期當模板。patch 比週期小也沒關係
#  —— 是把小 patch 滑進大模板，不是把小片互相對位。
#
#模板長什麼樣、為什麼原點要錨在地標上、信心值為什麼看的是「峰有多突出」而不是
#分數本身 —— 全部寫在 ``algo/template.py`` 的模組說明裡。
#
#模板存在 recipe 裡（不是存路徑）
#--------------------------------
#``template`` 參數存的是**模板本身**（base64 純文字）。存路徑的話，圖被搬走、
#被換掉、下個月有人用了另一張大圖，結果會安靜地變 —— 而 recipe 是要交接給別人的
#東西，它必須自己就是完整的。
#
#跨 lot 共用是刻意的：同一支 inspection recipe 掃同一塊 scan area，圖案是一樣的。
#換一批資料要不要重算模板，是 Studio 在設定時提供的健檢，不是每一顆的執行期行為。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#import numpy as np
#
#from ..algo import template as algo_template
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_ALGO, GROUP_REGION, ParamSpec, Step, StepError, register_step,
#)
#from ._util import (
#    FEATURE_PREFIX_PATTERN, output_prefix_spec, prefix_features, prefix_names,
#    require_image,
#)
#
##: ``locate_axis`` -> 哪幾軸要做定位。一維的 layout（垂直條紋）只有 X 有相位，
##: 硬要在另一軸上搜尋只會把峰的突出程度稀釋掉，把「定得出來」誤判成「定不出來」。
#_AXES = {"x": (True, False), "y": (False, True), "both": (True, True)}
#
#
#@register_step
#class RoiTemplateStep(Step):
#    """模板定位：把 patch 對回 Golden Cell 的相位，再把標好的框搬過來。"""
#
#    key = "roi_template"
#    label = "Locate region by template"
#    category = CATEGORY_ALGO
#    group = GROUP_REGION
#    help = ("Match each patch against one repeating cell of the layout, so a "
#            "region marked once on that cell lands in the right place on every "
#            "patch - even when the patch is smaller than one cell.")
#    params = [
#        ParamSpec(
#            name="source", type="image_key", default="ref",
#            label="Match on",
#            help=("Which image stream to match against the template. Use ref: "
#                  "it has no defect on it, so nothing is interfering with the "
#                  "match, and the pair is already aligned so the answer applies "
#                  "to test as well."),
#        ),
#        ParamSpec(
#            name="template", type="template", default="",
#            label="Template",
#            help=("The repeating cell this card matches against, stored inside "
#                  "the recipe as text so the recipe stays a single file you can "
#                  "hand to someone else. Build it from a full-size image in "
#                  "Studio - there is nothing useful to type here by hand."),
#        ),
#        ParamSpec(
#            name="locate_axis", type="choice", default="x",
#            choices=["x", "y", "both"],
#            label="Locate across",
#            help=("Which direction the layout repeats in. x = vertical stripes "
#                  "(the usual case); y = horizontal stripes; both = a cell that "
#                  "repeats in two directions. Searching a direction that does "
#                  "not repeat only makes the match less certain."),
#        ),
#        ParamSpec(name="roi_x", type="float", default=0.0, min=0.0, max=1.0,
#                  label="Region left",
#                  help="Left edge of the region on the cell, 0 = the cell's left edge."),
#        ParamSpec(name="roi_y", type="float", default=0.0, min=0.0, max=1.0,
#                  label="Region top",
#                  help="Top edge of the region on the cell."),
#        ParamSpec(name="roi_w", type="float", default=1.0, min=0.01, max=1.0,
#                  label="Region width",
#                  help="Width of the region as a fraction of one cell."),
#        ParamSpec(name="roi_h", type="float", default=1.0, min=0.01, max=1.0,
#                  label="Region height",
#                  help="Height of the region as a fraction of one cell."),
#        ParamSpec(
#            name="roi_out", type="str", default="cell",
#            label="Name this region", pattern=FEATURE_PREFIX_PATTERN,
#            pattern_help=("use letters, digits and underscores only, and do "
#                          "not start with a digit"),
#            help="Name for the region. Measure cards refer to it by this name.",
#        ),
#        ParamSpec(
#            name="min_score", type="float", default=0.3, min=-1.0, max=1.0,
#            label="Minimum match",
#            help=("How well the patch must match the template at all. This is "
#                  "brightness-independent, so it does not need retuning when "
#                  "the gain changes."),
#        ),
#        ParamSpec(
#            name="min_margin", type="float", default=0.05, min=0.0, max=2.0,
#            label="Minimum certainty",
#            help=("How much better the best position must be than the next "
#                  "best one. A patch with nothing distinctive on it matches "
#                  "every position equally well - that scores near 0 here, and "
#                  "is the signal that this defect cannot be located."),
#        ),
#        ParamSpec(
#            name="min_structure", type="float", default=5.0, min=0.0, max=200.0,
#            label="Give up below",
#            help=("How much structure the patch itself must have. A patch that "
#                  "sits entirely inside one material has nothing to match, and "
#                  "no threshold on the match score can tell that apart from "
#                  "luck - pure noise scores surprisingly well against any "
#                  "template. Measured: a featureless patch scores about 1, "
#                  "anything with structure scores 20 or more."),
#        ),
#        output_prefix_spec("cell"),
#    ]
#    reads = ["ref"]
#    writes: List[str] = []
#    features_out = ["match_score", "match_margin", "match_structure",
#                    "phase_x", "phase_y", "locate_ok"]
#
#    # ---- 宣告 ---------------------------------------------------------------
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [str(params.get("source", "ref"))]
#
#    @classmethod
#    def resolve_regions_out(cls, params: Dict[str, Any]) -> List[str]:
#        name = str(params.get("roi_out", "cell") or "").strip()
#        return [name] if name else []
#
#    @classmethod
#    def resolve_features(cls, params: Dict[str, Any]) -> List[str]:
#        return prefix_names(params.get("output_prefix", ""), cls.features_out)
#
#    @classmethod
#    def configuration_issues(cls, params: Dict[str, Any]) -> List[str]:
#        """沒有模板 = 還沒設定完，而不是「參數填錯」。
#
#        空字串是完全合法的 str，所以參數檢查沒話說 —— 但這張卡跑起來**每一顆**
#        都會失敗。使用者以前要跑過一次才知道，而且那時已經等完 200 顆了。
#        """
#        if str(params.get("template", "") or "").strip():
#            return []
#        return ["This card has no template yet. Select it and use “Build "
#                "template from a full-size image…” — a template is an image, "
#                "it cannot be typed in."]
#
#    # ---- 執行 ---------------------------------------------------------------
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        name = str(p["roi_out"]).strip()
#        if not name:
#            raise StepError(self.key, "the region name must not be empty.")
#
#        cell = algo_template.decode_cell(str(p["template"]))
#        if cell is None or cell.size == 0:
#            # 沒有模板不是「跑不出好結果」，是**還沒設定完**。講清楚要去哪裡設，
#            # 不要讓使用者對著一個空白參數猜。
#            raise StepError(
#                self.key,
#                "no template yet. Select this card in Studio and use “Build "
#                "template from a full-size image…” — the template cannot be "
#                "typed in by hand.")
#
#        img = require_image(ctx, self.key, p["source"])
#        axes = _AXES[str(p["locate_axis"])]
#        match = algo_template.match_patch(
#            cell, img, min_score=float(p["min_score"]),
#            min_margin=float(p["min_margin"]),
#            min_structure=float(p["min_structure"]), periodic=axes)
#
#        norm = (float(p["roi_x"]), float(p["roi_y"]),
#                float(p["roi_w"]), float(p["roi_h"]))
#        shape = np.asarray(img).shape[:2]
#
#        # panel 用（跟 roi_profile 同一個慣例）：UI 畫的就是引擎算的這一份
#        ctx.meta.setdefault("templates", {})[name] = {
#            "cell_w": int(cell.shape[1]), "cell_h": int(cell.shape[0]),
#            "phase_x": int(match.phase_x), "phase_y": int(match.phase_y),
#            "score": float(match.score), "margin": float(match.margin),
#            "structure": float(match.structure),
#            "ok": bool(match.ok), "norm": [float(v) for v in norm],
#            "axis": str(p["locate_axis"]),
#        }
#
#        if not match.ok:
#            ctx.warn(
#                f"[{self.key}] could not place '{name}' on this defect "
#                f"(match {match.score:.2f}, certainty {match.margin:.2f}); "
#                f"the region falls back to the whole image and this defect is "
#                f"marked locate_ok = 0.")
#            ctx.set_roi(name, (0.0, 0.0, 1.0, 1.0))
#            ctx.add_features(prefix_features(p["output_prefix"], {
#                "match_score": float(match.score),
#                "match_margin": float(match.margin),
#                "match_structure": float(match.structure),
#                "phase_x": float(match.phase_x), "phase_y": float(match.phase_y),
#                "locate_ok": 0.0,
#            }))
#            return ctx
#
#        x, y, w, h = algo_template.roi_in_patch(
#            norm, match, cell.shape, shape, periodic=axes)
#
#        # 落在 patch 外面的部分裁掉。一個 cell 可能有一半在框外 —— 那是正常的
#        # （缺陷靠邊時本來就會這樣），但剩下的必須還有東西可以量。
#        ph, pw = int(shape[0]), int(shape[1])
#        x0, y0 = max(0, int(x)), max(0, int(y))
#        x1, y1 = min(pw, int(x) + int(w)), min(ph, int(y) + int(h))
#        if x1 <= x0 or y1 <= y0:
#            ctx.warn(f"[{self.key}] region '{name}' lands completely outside "
#                     f"this patch; falling back to the whole image "
#                     f"(locate_ok = 0).")
#            ctx.set_roi(name, (0.0, 0.0, 1.0, 1.0))
#            ctx.add_features(prefix_features(p["output_prefix"], {
#                "match_score": float(match.score),
#                "match_margin": float(match.margin),
#                "match_structure": float(match.structure),
#                "phase_x": float(match.phase_x), "phase_y": float(match.phase_y),
#                "locate_ok": 0.0,
#            }))
#            return ctx
#
#        ctx.set_roi(name, (x0 / pw, y0 / ph, (x1 - x0) / pw, (y1 - y0) / ph))
#        ctx.add_features(prefix_features(p["output_prefix"], {
#            "match_score": float(match.score),
#            "match_margin": float(match.margin),
#            "match_structure": float(match.structure),
#            "phase_x": float(match.phase_x), "phase_y": float(match.phase_y),
#            "locate_ok": 1.0,
#        }))
#        return ctx
#
#F 9fa9304bcfc700c529e7d9e2f9035120b1e1bc91 83 adept/core/steps/snr_map.py
## ADEPT step-card library — authored 2026-07-28 (M1).
#"""snr_map — 區域 SNR 地圖卡。
#
#把 diff 圖轉成「每個位置的訊號有多突出（幾個 sigma）」的地圖：
#影像流 out 存正規化後的 float32 地圖（0–1），feature ``snr_max`` 存
#正規化前的原始 SNR 峰值（sigma 單位），可直接拿去打分。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#from ..algo import snr as algo_snr
#from ..pipeline.context import Context
#from ..pipeline.step import (
#    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_REGION,
#)
#from ._util import require_image
#
#
#@register_step
#class SnrMapStep(Step):
#    """區域 SNR 地圖：局部平均對局部標準差的突出程度。"""
#
#    key = "snr_map"
#    label = "SNR map"
#    category = CATEGORY_ALGO
#    group = GROUP_REGION
#    help = ("Turn the difference image into a map of how much the signal "
#            "stands out at each position (SNR), and report the peak as "
#            "snr_max.")
#    params = [
#        ParamSpec(name="source", type="image_key", default="diff",
#                  help=("Input difference image stream (usually the diff "
#                        "produced by subtract).")),
#        ParamSpec(name="window", type="int", default=31, min=5, max=201,
#                  help=("Local statistics window size (odd, 5-201): roughly "
#                        "2-4x the defect size you expect.")),
#        ParamSpec(name="clip_sigma", type="float", default=3.0, min=0.5, max=20.0,
#                  help=("SNR ceiling in sigma: the saturation value for the "
#                        "map; anything above is clamped here.")),
#        ParamSpec(name="clip_percentile", type="float", default=99.5, min=50.0, max=100.0,
#                  help=("Normalisation percentile: the value at this "
#                        "percentile becomes 1.0 on the map.")),
#        ParamSpec(name="exclude_border", type="int", default=16, min=0, max=100,
#                  help=("Border exclusion width in pixels: edge statistics are "
#                        "unreliable, so they are zeroed to avoid false peaks.")),
#        ParamSpec(name="out", type="image_key", default="snr_map",
#                  help="Name of the image stream the SNR map is written to (float32, 0-1)."),
#    ]
#    reads = ["diff"]
#    writes = ["snr_map"]
#    features_out = ["snr_max"]
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("source", "diff")]
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return [params.get("out", "snr_map")]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        window = int(p["window"])
#        if window % 2 == 0:
#            raise StepError(self.key, f"window must be odd (got {window}); use {window - 1} or "
#                        f"{window + 1}.")
#        src = require_image(ctx, self.key, p["source"])
#        h, w = src.shape[:2]
#        if 2 * int(p["exclude_border"]) >= min(h, w):
#            raise StepError(self.key, f"exclude_border ({p['exclude_border']}) is too large — it "
#                        f"would blank the whole {w}x{h} image; use a smaller value.")
#        res = algo_snr.compute_snr_map(
#            src,
#            window_size=window,
#            clip_sigma=float(p["clip_sigma"]),
#            clip_percentile=float(p["clip_percentile"]),
#            exclude_border=int(p["exclude_border"]),
#        )
#        ctx.set_image(p["out"], res.map_float)
#        ctx.add_feature("snr_max", res.snr_max)
#        return ctx
#
#F cd57244a5b92565fc110ceee0cccfc6004db10c1 198 adept/core/steps/tone.py
## ADEPT step-card library — authored 2026-07-29 (F7-7).
#"""tone — 亮度／對比／gamma 調整卡（Enhance 段）。
#
#跟 ``normalize.py`` 的差別（很重要，不要混用）
#---------------------------------------------
#* ``percentile_norm`` / ``glv_mask_norm`` 是**自動**的：從影像自己算出範圍再拉伸，
#  目的是「把兩張圖變成可以比」。
#* 這一檔是**手動**的：使用者直接指定要加多少亮度、拉多少對比、套什麼 gamma。
#  目的是「讓我看得清楚 / 讓後面的量測落在好用的數值範圍」。
#
#兩者都可以用，順序也隨意 —— 但如果流程裡已經有正規化卡，通常手動調整要放在
#它**之後**，否則正規化會把你剛調的東西再拉回去。
#
#為什麼 gamma 值得一張卡
#-----------------------
#SEM 的暗部細節常常擠在低灰階區。gamma < 1 會把暗部拉開、gamma > 1 壓暗部拉亮部，
#這是線性的亮度／對比做不到的 —— 它對灰階是**非線性**重分佈。
#
#運算一律在 float 上做、最後夾回原本的數值範圍：uint8 進 uint8 出，float 進 float 出
#（下游的 diff 是 float32，這條規則讓這張卡插在哪裡都不會偷偷改變型別）。
#"""
#from __future__ import annotations
#
#from typing import Any, Dict, List
#
#import numpy as np
#
#from ..algo.curve import apply_curve_01
#from ..pipeline.context import Context
#from ..pipeline.curve import IDENTITY, is_identity, parse_curve
#from ..pipeline.step import (
#    CATEGORY_IMAGE, GROUP_ENHANCE, ParamSpec, Step, register_step,
#)
#from ._util import ONE_STREAM_HELP, require_image
#
#__all__ = ["BrightnessContrastStep", "GammaStep", "apply_brightness_contrast",
#           "apply_gamma", "apply_curve"]
#
#
#def _value_range(arr: np.ndarray) -> tuple:
#    """這個陣列該被夾在什麼範圍：uint8 -> (0,255)，float -> 依實際內容。
#
#    float 影像（例如 diff）可能有負值，硬夾成 0–255 會把資訊剪掉，
#    所以浮點一律保留原本的動態範圍。
#    """
#    if arr.dtype == np.uint8:
#        return 0.0, 255.0
#    lo = float(np.nanmin(arr)) if arr.size else 0.0
#    hi = float(np.nanmax(arr)) if arr.size else 1.0
#    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
#        return 0.0, 1.0
#    return lo, hi
#
#
#def apply_brightness_contrast(img: np.ndarray, brightness: float,
#                              contrast: float) -> np.ndarray:
#    """``out = (img - mid) * contrast + mid + brightness``，繞著中灰旋轉。
#
#    對比以**影像自己的中間值**為支點，不是以 0 為支點 —— 以 0 為支點的話
#    拉對比會同時把整張圖變亮，使用者得再回頭調亮度，很難用。
#    ``brightness`` 的單位是「原始灰階」（uint8 就是 0–255 的刻度）。
#    """
#    out = img.astype(np.float64, copy=False)
#    lo, hi = _value_range(img)
#    mid = (lo + hi) / 2.0
#    out = (out - mid) * float(contrast) + mid + float(brightness)
#    out = np.clip(out, lo, hi)
#    return out.astype(img.dtype, copy=False)
#
#
#def apply_gamma(img: np.ndarray, gamma: float) -> np.ndarray:
#    """先正規化到 0–1、套 ``x ** (1/gamma)``、再映射回原範圍。
#
#    習慣用法：``gamma < 1`` 壓亮部、拉開暗部細節（SEM 常用）；
#    ``gamma > 1`` 相反。``gamma == 1`` 原樣回傳。
#    """
#    g = float(gamma)
#    if g <= 0 or g == 1.0:
#        return img
#    lo, hi = _value_range(img)
#    span = hi - lo
#    if span <= 0:
#        return img
#    x = (img.astype(np.float64, copy=False) - lo) / span
#    x = np.clip(x, 0.0, 1.0) ** (1.0 / g)
#    return (x * span + lo).astype(img.dtype, copy=False)
#
#
#def apply_curve(img: np.ndarray, curve) -> np.ndarray:
#    """套用自訂色調曲線（控制點字串或 ``[(x, y), …]``）。
#
#    跟 :func:`apply_gamma` 走完全相同的正規化 / 反正規化流程 ——
#    差別只在中間那條轉移函數是使用者自己拉的，而不是 ``x ** (1/gamma)``。
#    所以兩者可以互換，換過去不會連帶改變亮度基準或數值型別。
#    """
#    pts = parse_curve(curve) if isinstance(curve, str) else list(curve)
#    if is_identity(pts):
#        return img
#    lo, hi = _value_range(img)
#    span = hi - lo
#    if span <= 0:
#        return img
#    x = (img.astype(np.float64, copy=False) - lo) / span
#    return (apply_curve_01(x, pts) * span + lo).astype(img.dtype, copy=False)
#
#
#class _ToneStep(Step):
#    """共用：一張卡做一條影像流（同 normalize / flatten 卡的慣例，見 F7-18）。"""
#
#    category = CATEGORY_IMAGE
#    group = GROUP_ENHANCE
#    reads = ["test"]
#    writes = ["test"]
#    features_out: List[str] = []
#
#    @classmethod
#    def resolve_reads(cls, params: Dict[str, Any]) -> List[str]:
#        return [str(params.get("target", "test"))]
#
#    @classmethod
#    def resolve_writes(cls, params: Dict[str, Any]) -> List[str]:
#        return cls.resolve_reads(params)
#
#    def _apply(self, ctx: Context, params: Dict[str, Any], fn) -> Context:
#        key = str(params.get("target", "test"))
#        img = require_image(ctx, self.key, key)
#        ctx.set_image(key, fn(img))
#        return ctx
#
#
#@register_step
#class BrightnessContrastStep(_ToneStep):
#    """手動亮度 / 對比。"""
#
#    key = "brightness_contrast"
#    label = "Brightness / Contrast"
#    help = ("Manually shift brightness and stretch contrast, so faint defects "
#            "become easier to see and to measure.")
#    params = [
#        ParamSpec(name="target", type="image_key", default="test",
#                  label="Image stream", help=ONE_STREAM_HELP),
#        ParamSpec(name="brightness", type="float", default=0.0,
#                  min=-255.0, max=255.0,
#                  help=("Added to every pixel, in gray levels. Positive "
#                        "brightens, negative darkens; 0 leaves it alone.")),
#        ParamSpec(name="contrast", type="float", default=1.0,
#                  min=0.0, max=10.0,
#                  help=("Contrast multiplier around mid gray. 1 = unchanged, "
#                        "2 = twice the spread, 0.5 = half.")),
#    ]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        b, c = float(p["brightness"]), float(p["contrast"])
#        return self._apply(
#            ctx, p, lambda im: apply_brightness_contrast(im, b, c))
#
#
#@register_step
#class GammaStep(_ToneStep):
#    """Gamma 校正 + 自訂色調曲線（非線性重分佈灰階）。
#
#    兩個旋鈕、一個結果
#    ------------------
#    ``gamma`` 是滑桿，一個數字就講完；``curve`` 是使用者自己拉的線，
#    想做「只提暗部、亮部原封不動」這種 gamma 做不到的事時用。
#
#    **曲線一旦不是 y=x 就完全接手，gamma 被忽略。** 選「兩個都套」會很難
#    debug：使用者把曲線拉平了卻還是暗，因為 gamma 還壓在那裡。
#    這條規則寫在 ``curve`` 的 help 裡，UI 也會在曲線生效時把 gamma 那列調淡。
#    """
#
#    key = "gamma"
#    label = "Gamma / Curve"
#    help = ("Redistribute gray levels non-linearly: below 1 opens up dark "
#            "detail, above 1 pushes it down. Linear brightness and contrast "
#            "cannot do this. Draw your own curve for full control.")
#    params = [
#        ParamSpec(name="target", type="image_key", default="test",
#                  label="Image stream", help=ONE_STREAM_HELP),
#        ParamSpec(name="gamma", type="float", default=1.0, min=0.1, max=5.0,
#                  help=("Below 1 brings out detail in the dark areas (common "
#                        "for SEM); above 1 does the opposite. 1 = unchanged.")),
#        ParamSpec(name="curve", type="curve", default=IDENTITY,
#                  help=("Custom tone curve: input gray level across, output "
#                        "up. Drag a point to bend it. While it is a straight "
#                        "y = x line the gamma slider above is used instead; "
#                        "as soon as you bend it, the curve takes over.")),
#    ]
#
#    def run(self, ctx: Context, params: Dict[str, Any]) -> Context:
#        p = self.validate_params(params)
#        pts = parse_curve(p["curve"])
#        if not is_identity(pts):
#            return self._apply(ctx, p, lambda im: apply_curve(im, pts))
#        g = float(p["gamma"])
#        return self._apply(ctx, p, lambda im: apply_gamma(im, g))
#
#F 0e7d37674a365b4c5292ba728f7da61b0aba6b08 11 adept/core/store/__init__.py
## ADEPT result store — authored 2026-07-28 (M2).
#"""adept.core.store — 批次結果持久化（SQLite）與 rescore。
#
#單一匯入點：``from adept.core.store import RunStore, rescore``。
#"""
#from __future__ import annotations
#
#from .results import SCHEMA_VERSION, RunStore, rescore
#
#__all__ = ["RunStore", "rescore", "SCHEMA_VERSION"]
#
#F 9a939964c13156bd41a7eb72b27134921827fb08 386 adept/core/store/results.py
## ADEPT result store — authored 2026-07-28 (M2).
#"""批次結果儲存（SQLite）＋ rescore：MMH ``batch_run_store`` 模式的一般化。
#
#角色（見 docs/plans/F0-master-plan.md §6）：
#
#- **RunStore**：每次批次執行存成一個 run —— ``runs`` 一列（recipe 快照、
#  KLARF 路徑、ok/fail 統計）＋ ``results`` 每顆一列（score/bin/features）。
#  直方圖、gallery、報表、feature vector 匯出全吃這張表。
#- **rescore**：改表達式/門檻**不重跑影像** —— 從既有 run 的 features 直接
#  重算 score/bin（「拖門檻線 → bin 數即時變」的 headless 基礎）。
#  10k 顆 rescore 遠低於 5 秒（純 python dict 迴圈 + executemany）。
#
#設計慣例：
#
#- WAL journal、foreign_keys ON、``ON DELETE CASCADE``（刪 run 連 results 一起掉）。
#- schema_version 記在 ``meta`` 表（v1）；未來升版走 migration。
#- 資料庫路徑由呼叫端決定（CLI 層預設 ``~/.adept/runs.db``），這裡不寫死。
#- results 列 = :func:`adept.core.pipeline.result_to_json_dict` 的 dict
#  （traces 不入庫；features 中 nan/inf 一律存成 None，JSON 安全）。
#"""
#from __future__ import annotations
#
#import csv
#import json
#import math
#import os
#import statistics
#import time
#import uuid
#from datetime import datetime, timezone
#from typing import Any, Dict, Iterator, List, Optional, Tuple, Union
#
#import sqlite3
#
#from adept.core.pipeline.expression import parse_expression
#
#__all__ = ["RunStore", "rescore", "SCHEMA_VERSION"]
#
#SCHEMA_VERSION = 1
#
#_SCHEMA = """
#CREATE TABLE IF NOT EXISTS meta(
#    key   TEXT PRIMARY KEY,
#    value TEXT NOT NULL
#);
#CREATE TABLE IF NOT EXISTS runs(
#    run_id       TEXT PRIMARY KEY,
#    created_utc  TEXT NOT NULL,
#    recipe_id    TEXT NOT NULL DEFAULT '',
#    recipe_json  TEXT NOT NULL DEFAULT '',
#    klarf_path   TEXT NOT NULL DEFAULT '',
#    dataset_kind TEXT NOT NULL DEFAULT '',
#    n_total      INTEGER NOT NULL DEFAULT 0,
#    n_ok         INTEGER NOT NULL DEFAULT 0,
#    n_fail       INTEGER NOT NULL DEFAULT 0,
#    notes        TEXT NOT NULL DEFAULT ''
#);
#CREATE TABLE IF NOT EXISTS results(
#    run_id        TEXT NOT NULL,
#    defect_id     TEXT NOT NULL,
#    ok            INTEGER NOT NULL,
#    error         TEXT,
#    score         REAL,
#    bin           INTEGER,
#    features_json TEXT NOT NULL DEFAULT '{}',
#    PRIMARY KEY(run_id, defect_id),
#    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
#);
#"""
#
#_RUN_COLS = ("run_id", "created_utc", "recipe_id", "klarf_path",
#             "dataset_kind", "n_total", "n_ok", "n_fail", "notes")
#
#
## ---------------------------------------------------------------------------
## 小工具
## ---------------------------------------------------------------------------
#def _safe_num(v: Any) -> Optional[float]:
#    """float 化；None/nan/inf/不可轉 → None（與 engine._safe_num 同語意）。"""
#    if v is None:
#        return None
#    try:
#        f = float(v)
#    except (TypeError, ValueError):
#        return None
#    if math.isnan(f) or math.isinf(f):
#        return None
#    return f
#
#
#def _now_utc_iso() -> str:
#    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
#
#
#def _auto_run_id() -> str:
#    """自動 run_id：UTC 時間戳（到分）＋短 uuid，例 ``20260728T0102-ab12cd``。"""
#    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")
#    return "{}-{}".format(stamp, uuid.uuid4().hex[:6])
#
#
#def _recipe_to_dict(recipe: Any) -> Dict[str, Any]:
#    """Recipe dataclass 或 recipe JSON dict → dict（duck typing，不硬綁類別）。"""
#    if hasattr(recipe, "to_json_dict"):
#        return recipe.to_json_dict()
#    if isinstance(recipe, dict):
#        return dict(recipe)
#    raise TypeError(
#        "recipe must be a Recipe object (with to_json_dict) or a recipe JSON "
#        "dict, got {}".format(type(recipe).__name__))
#
#
## ---------------------------------------------------------------------------
## RunStore
## ---------------------------------------------------------------------------
#class RunStore:
#    """批次歷史 SQLite 儲存；一個實例 = 一條連線。支援 context manager。
#
#    .. code-block:: python
#
#        with RunStore(str(db_path)) as store:
#            run_id = store.save_run(recipe, [result_to_json_dict(r) for r in rs])
#            summary = rescore(store, run_id, threshold=2.5)
#    """
#
#    def __init__(self, db_path: str):
#        self.db_path = str(db_path)
#        parent = os.path.dirname(self.db_path)
#        if parent and self.db_path != ":memory:":
#            os.makedirs(parent, exist_ok=True)
#        self._conn = sqlite3.connect(self.db_path)
#        self._conn.row_factory = sqlite3.Row
#        self._conn.execute("PRAGMA journal_mode=WAL")
#        self._conn.execute("PRAGMA foreign_keys=ON")
#        with self._conn:
#            self._conn.executescript(_SCHEMA)
#            self._conn.execute(
#                "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
#                (str(SCHEMA_VERSION),))
#
#    # ---- 生命週期 ---------------------------------------------------------
#    def close(self) -> None:
#        if self._conn is not None:
#            self._conn.close()
#            self._conn = None  # type: ignore[assignment]
#
#    def __enter__(self) -> "RunStore":
#        return self
#
#    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
#        self.close()
#
#    # ---- 寫入 -------------------------------------------------------------
#    def save_run(self, recipe: Any, results: List[Dict[str, Any]], *,
#                 klarf_path: str = "", dataset_kind: str = "",
#                 notes: str = "", run_id: Optional[str] = None) -> str:
#        """存一個 run（單一交易、``executemany``），回傳 run_id。
#
#        ``results`` 為 :func:`result_to_json_dict` 形狀的 dict list
#        （traces 不入庫）；features 中 nan/inf → None。
#        ``run_id=None`` 自動產生（時間戳＋短 uuid，撞號自動重抽）。
#        """
#        rdict = _recipe_to_dict(recipe)
#        recipe_id = str(rdict.get("recipe_id", ""))
#        recipe_json = json.dumps(rdict, ensure_ascii=False)
#
#        if run_id is None:
#            run_id = _auto_run_id()
#            while self._run_exists(run_id):  # pragma: no cover — uuid 撞號極罕見
#                run_id = _auto_run_id()
#        else:
#            run_id = str(run_id)
#
#        rows = []
#        n_ok = 0
#        for r in results:
#            ok = bool(r.get("ok"))
#            n_ok += 1 if ok else 0
#            feats = {k: _safe_num(v) for k, v in (r.get("features") or {}).items()}
#            b = r.get("bin")
#            rows.append((
#                run_id,
#                str(r.get("defect_id", "")),
#                1 if ok else 0,
#                r.get("error"),
#                _safe_num(r.get("score")),
#                None if b is None else int(b),
#                json.dumps(feats, ensure_ascii=False),
#            ))
#
#        with self._conn:  # 單一交易：runs + results 同進同出
#            self._conn.execute(
#                "INSERT INTO runs(run_id, created_utc, recipe_id, recipe_json, "
#                "klarf_path, dataset_kind, n_total, n_ok, n_fail, notes) "
#                "VALUES(?,?,?,?,?,?,?,?,?,?)",
#                (run_id, _now_utc_iso(), recipe_id, recipe_json,
#                 str(klarf_path), str(dataset_kind),
#                 len(rows), n_ok, len(rows) - n_ok, str(notes)))
#            self._conn.executemany(
#                "INSERT INTO results(run_id, defect_id, ok, error, score, bin, "
#                "features_json) VALUES(?,?,?,?,?,?,?)", rows)
#        return run_id
#
#    def delete_run(self, run_id: str) -> None:
#        """刪 run；results 由 ``ON DELETE CASCADE`` 一併清掉。不存在則靜默。"""
#        with self._conn:
#            self._conn.execute("DELETE FROM runs WHERE run_id=?", (str(run_id),))
#
#    # ---- 讀取 -------------------------------------------------------------
#    def _run_exists(self, run_id: str) -> bool:
#        cur = self._conn.execute(
#            "SELECT 1 FROM runs WHERE run_id=?", (str(run_id),))
#        return cur.fetchone() is not None
#
#    def list_runs(self) -> List[Dict[str, Any]]:
#        """全部 run 摘要（**不含** recipe_json），新的在前。"""
#        cur = self._conn.execute(
#            "SELECT {} FROM runs ORDER BY created_utc DESC, rowid DESC".format(
#                ", ".join(_RUN_COLS)))
#        return [dict(row) for row in cur.fetchall()]
#
#    def get_run(self, run_id: str) -> Dict[str, Any]:
#        """單一 run 完整列（**含** recipe_json）；不存在 → :class:`KeyError`。"""
#        cur = self._conn.execute(
#            "SELECT * FROM runs WHERE run_id=?", (str(run_id),))
#        row = cur.fetchone()
#        if row is None:
#            raise KeyError("run '{}' not found (database: {})".format(run_id, self.db_path))
#        return dict(row)
#
#    def iter_results(self, run_id: str) -> Iterator[Dict[str, Any]]:
#        """逐顆 yield 結果 dict（features 已從 JSON 解析回 dict），依存入順序。"""
#        if not self._run_exists(run_id):
#            raise KeyError("run '{}' not found (database: {})".format(run_id, self.db_path))
#        cur = self._conn.execute(
#            "SELECT defect_id, ok, error, score, bin, features_json "
#            "FROM results WHERE run_id=? ORDER BY rowid", (str(run_id),))
#        for row in cur:
#            yield {
#                "defect_id": row["defect_id"],
#                "ok": bool(row["ok"]),
#                "error": row["error"],
#                "score": row["score"],
#                "bin": row["bin"],
#                "features": json.loads(row["features_json"]),
#            }
#
#    def get_features_table(self, run_id: str) -> Tuple[List[str], List[Dict[str, Any]]]:
#        """``(defect_ids, feature_dicts)`` 兩平行 list —— feature vector / ML 備料。"""
#        ids: List[str] = []
#        feats: List[Dict[str, Any]] = []
#        for r in self.iter_results(run_id):
#            ids.append(r["defect_id"])
#            feats.append(r["features"])
#        return ids, feats
#
#    # ---- 匯出 -------------------------------------------------------------
#    def export_csv(self, run_id: str, path: str) -> str:
#        """匯出一個 run 為 CSV（utf-8-sig，Excel 直開不亂碼）。
#
#        欄位：defect_id, ok, error, score, bin，之後接**排序後的
#        feature key 聯集**（缺的留空）—— feature vector 匯出 = ML 備料。
#        atomic 寫入（``.tmp`` + ``os.replace``）。回傳寫入路徑。
#        """
#        path = str(path)
#        rows = list(self.iter_results(run_id))
#        keys: List[str] = sorted(set().union(*(r["features"].keys() for r in rows))) \
#            if rows else []
#        tmp = path + ".tmp"
#        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
#            w = csv.writer(f)
#            w.writerow(["defect_id", "ok", "error", "score", "bin"] + keys)
#            for r in rows:
#                feats = r["features"]
#                w.writerow(
#                    [r["defect_id"],
#                     1 if r["ok"] else 0,
#                     "" if r["error"] is None else r["error"],
#                     "" if r["score"] is None else r["score"],
#                     "" if r["bin"] is None else r["bin"]]
#                    + [("" if feats.get(k) is None else feats.get(k)) for k in keys])
#        os.replace(tmp, path)
#        return path
#
#
## ---------------------------------------------------------------------------
## rescore：改表達式/門檻不重跑影像
## ---------------------------------------------------------------------------
#def rescore(store: RunStore, run_id: str, *,
#            expr: Optional[str] = None,
#            threshold: Optional[float] = None,
#            bins: Optional[Dict[str, int]] = None,
#            save_as: Optional[Union[str, bool]] = None,
#            notes: str = "") -> Dict[str, Any]:
#    """用既有 run 的 features 重算 score/bin（**不重跑影像**）。
#
#    - ``expr`` / ``threshold`` / ``bins``：None → 沿用該 run recipe 的設定。
#    - 每顆的變數 = 存下來的 features **排除 "score"**（避免舊分數污染新式）。
#    - 判定與 engine 相同：``score < threshold → bins["below"]``，否則
#      ``bins["above"]``。
#    - 某顆 features 缺變數（或值是 None，例如原本是 nan）→ 該顆
#      score=None、bin=None、記入 ``n_errors``，**絕不炸整批**。
#    - ``save_as``：字串 → 以該 id 存成**新 run**；True → 自動 id；
#      新 run 帶更新後的 recipe_json、原 run 的 klarf_path/dataset_kind、
#      ``notes``；新 id 放在回傳的 ``saved_run_id``。
#
#    回傳 summary::
#
#        {run_id, n, n_errors, bin_counts, score_min, score_median,
#         score_max, elapsed_s, saved_run_id}
#    """
#    t0 = time.perf_counter()
#    run = store.get_run(run_id)
#
#    # ---- 組出「更新後的 score spec」（None → 沿用）----
#    try:
#        rdict: Dict[str, Any] = json.loads(run["recipe_json"]) or {}
#    except (ValueError, TypeError):
#        rdict = {}
#    spec = dict(rdict.get("score") or {})
#    if expr is not None:
#        spec["expr"] = str(expr)
#    if threshold is not None:
#        spec["threshold"] = float(threshold)
#    if bins is not None:
#        spec["bins"] = {str(k): int(v) for k, v in bins.items()}
#    if "expr" not in spec:
#        raise ValueError(
#            "the recipe of run '{}' has no score.expr; rescore needs an expression via expr="
#            .format(run_id))
#    rdict["score"] = spec
#
#    expression = parse_expression(str(spec["expr"]))  # 語法錯誤 → 直接 raise（recipe 寫錯要讓人看到）
#    thr = float(spec.get("threshold", 0.0))
#    bins_used = dict(spec.get("bins") or {})
#    b_below = int(bins_used.get("below", 0))
#    b_above = int(bins_used.get("above", 1))
#
#    # ---- 純 python dict 迴圈重算（10k 顆遠低於 5 s）----
#    n = 0
#    n_errors = 0
#    scores: List[float] = []
#    bin_counts: Dict[int, int] = {}
#    new_rows: List[Dict[str, Any]] = []
#    for r in store.iter_results(run_id):
#        n += 1
#        feats = r["features"]
#        variables = {k: v for k, v in feats.items() if k != "score"}
#        try:
#            s = expression.eval(variables)
#            b = b_below if s < thr else b_above
#        except Exception as e:  # 缺變數 / 值不是數字 → 該顆記錯，不殺整批
#            n_errors += 1
#            feats["score"] = None
#            new_rows.append({
#                "defect_id": r["defect_id"], "ok": False, "error": str(e),
#                "features": feats, "score": None, "bin": None})
#            continue
#        scores.append(s)
#        bin_counts[b] = bin_counts.get(b, 0) + 1
#        feats["score"] = s
#        new_rows.append({
#            "defect_id": r["defect_id"], "ok": True, "error": None,
#            "features": feats, "score": s, "bin": b})
#
#    # ---- 存成新 run（選配）----
#    saved_run_id: Optional[str] = None
#    if save_as:
#        saved_run_id = store.save_run(
#            rdict, new_rows,
#            klarf_path=run.get("klarf_path", ""),
#            dataset_kind=run.get("dataset_kind", ""),
#            notes=notes,
#            run_id=(None if save_as is True else str(save_as)))
#
#    return {
#        "run_id": run_id,
#        "n": n,
#        "n_errors": n_errors,
#        "bin_counts": bin_counts,
#        "score_min": min(scores) if scores else None,
#        "score_median": statistics.median(scores) if scores else None,
#        "score_max": max(scores) if scores else None,
#        "elapsed_s": time.perf_counter() - t0,
#        "saved_run_id": saved_run_id,
#    }
#
#F e69de29bb2d1d6434b8b29ae775ad8c2e48c5391 1 adept/ui/__init__.py
#
#F 1ce158e532ca3e12af81e66ee60dfc77e8d8b081 41 adept/ui/app.py
## ADEPT Studio 進入點 — authored 2026-07-28 (M3).
#"""``python -m adept.ui.app`` —— 開一個 ADEPT Studio 視窗。
#
#薄薄一層：建 QApplication → 套主題 → 開主視窗 → 進 event loop。
#所有邏輯都在 :mod:`adept.ui.studio`，這裡刻意什麼都不做，
#方便未來換成別的殼（嵌進廠內既有 app）時只改這一個檔。
#"""
#from __future__ import annotations
#
#import sys
#from typing import List, Optional, Sequence
#
#from PySide6.QtWidgets import QApplication
#
#from . import theme
#from .studio import StudioWindow
#from .welcome import saved_theme
#
#__all__ = ["main"]
#
#
#def main(argv: Optional[Sequence[str]] = None) -> int:
#    """開視窗並跑到使用者關掉為止；回傳 process exit code。"""
#    args: List[str] = list(sys.argv if argv is None else argv)
#    if not args:
#        args = ["adept-studio"]
#
#    app = QApplication.instance()
#    if app is None:
#        app = QApplication(args)
#    theme.apply_theme(app, saved_theme(theme.DEFAULT_THEME))
#
#    win = StudioWindow()
#    win.resize(1440, 900)
#    win.show()
#    return int(app.exec())
#
#
#if __name__ == "__main__":
#    raise SystemExit(main())
#

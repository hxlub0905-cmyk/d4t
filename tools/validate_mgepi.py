#!/usr/bin/env python3
# d4t mgepi lot separability check — authored 2026-08-14.
"""`make_mgepi_real.py` 產出 lot 的可分性驗證（也是量測邏輯的參考實作）。

驗收條件（這批資料存在的理由）：
  - 整張圖 max：real 與 nuisance **重疊**（不定 ROI 就淹掉）
  - spacer ROI 內的兩個指標：real 最小值 > nuisance 最大值（零重疊）

量測邏輯 —— 每一條都是被反例逼出來的，接 d4t pipeline 時照著對：
1. **先選帶、再壓剖面。** 整欄平均會把 spacer 的凹陷跟行間的 STI 混在
   一起（行間比 spacer 谷還暗，找谷會找錯地方）。先挑 EPI 列
   （row-mean > 145），只在這些列上壓欄剖面。
2. **用幾何找谷，不要用 GLV band mask。** 缺陷把 spacer「亮出範圍」之後
   它就不再像 spacer —— GLV band mask 會把缺陷自己剔除掉。
3. **在 ref 上定位、在 test/diff 上量。** 缺陷會把 test 的谷推亮、把定位
   帶偏（實測會讓 diff 指標從分得開變成分不開）。
4. **ROI 取整段谷底，不是谷點 ±1。** 谷底是 ~4 px 的平底，缺陷可能停在
   另一端。
5. **避開 patch 邊界（≥4 px）。** 被截斷的 spacer 找谷會挑到 MG 側壁半坡
   欄（看起來像 200+ 的「spacer」）；谷不夠深也跳過（那裡沒有 spacer）。
6. **max 前先 3×3 均值（匹配濾波）。** 缺陷是 ~3 px 的塊，單像素 max 在
   這種紋理下太脆（snr_map 卡就是這個邏輯）。
7. **diff 用 (test − ref) 只取正的。** Hf 缺陷一律正向亮起；LER 造成的
   test/ref 邊緣不合是雙向的，取正這一刀直接殺掉一半 nuisance。

用法：
  python3 tools/validate_mgepi.py LOT_DIR
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import cv2  # noqa: E402
import tifffile  # noqa: E402

MARGIN = 4               # patch 邊界淨空（px）
EPI_ROW_MIN = 145.0      # row-mean 高於這個才算 EPI 列
MG_COL_MIN = 190.0       # EPI 列剖面高於這個才算 MG 欄
DIP_MAX = 168.0          # 谷底高於這個 = 這裡其實沒有 spacer
VALLEY_TOL = 5.0         # 「還在谷底附近」的容忍度（GLV）
VALLEY_ABS = 161.0       # 谷擴張的絕對上限（EPI 下限 163 之下）


def spacer_mask(img):
    """幾何式 spacer 定位：EPI 列剖面 → MG 緣 → 外側找谷 → 收整段谷底。"""
    rowmean = img.mean(axis=1)
    epi_rows = rowmean > EPI_ROW_MIN
    if not epi_rows.any():
        return np.zeros(img.shape, bool)
    colmean = img[epi_rows, :].mean(axis=0)
    mg = colmean > MG_COL_MIN

    edges = []
    prev = False
    for x, v in enumerate(mg):
        if v and not prev:
            edges.append((x, -1))      # 左緣，spacer 在左邊
        if prev and not v:
            edges.append((x - 1, +1))  # 右緣，spacer 在右邊
        prev = v

    mask = np.zeros(img.shape, bool)
    for ex, sign in edges:
        cand = [ex + sign * d for d in range(1, 8)]
        # 谷的搜尋窗被 patch 邊界截掉就整個緣跳過（Keep clear of the edge）
        if any(c < MARGIN or c >= img.shape[1] - MARGIN for c in cand):
            continue
        dip = min(cand, key=lambda c: colmean[c])
        if colmean[dip] > DIP_MAX:
            continue
        lo_c = hi_c = dip
        floor = min(colmean[dip] + VALLEY_TOL, VALLEY_ABS)
        while lo_c - 1 >= MARGIN and colmean[lo_c - 1] <= floor and hi_c - lo_c < 4:
            lo_c -= 1
        while hi_c + 1 < img.shape[1] - MARGIN and colmean[hi_c + 1] <= floor and hi_c - lo_c < 4:
            hi_c += 1
        for c in range(lo_c, hi_c + 1):
            mask[:, c] |= epi_rows
    return mask


def metrics(test, ref):
    t3 = cv2.blur(test.astype(np.float32), (3, 3))
    sd = np.clip(test.astype(np.float32) - ref.astype(np.float32), 0, None)
    p3 = cv2.blur(sd, (3, 3))
    m = spacer_mask(ref)      # 在 ref 上定位（見檔頭第 3 條）
    return {
        "whole_max": float(test.max()),
        "sp_t3_max": float(t3[m].max()) if m.any() else 0.0,
        "sp_p3_max": float(p3[m].max()) if m.any() else 0.0,
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print(__doc__.splitlines()[0])
        print("usage: python3 tools/validate_mgepi.py LOT_DIR")
        return 2
    lot = argv[0]

    with open(os.path.join(lot, "ground_truth.json"), encoding="utf-8") as f:
        truth = json.load(f)
    tf = tifffile.TiffFile(os.path.join(lot, "LOT_SYN.tif"))

    rows = {"real": [], "nuis": []}
    for i in range(len(truth)):
        did = str(i + 1)
        test = tf.pages[2 * i].asarray().astype(np.float64)
        ref = tf.pages[2 * i + 1].asarray().astype(np.float64)
        rows["real" if truth[did]["is_real"] else "nuis"].append(metrics(test, ref))

    ok = True
    for name, label, want_sep in [
            ("whole_max", "whole-image max      ", False),
            ("sp_t3_max", "spacer 3x3 test max  ", True),
            ("sp_p3_max", "spacer 3x3 (t-r)+ max", True)]:
        r = np.array([m[name] for m in rows["real"]])
        u = np.array([m[name] for m in rows["nuis"]])
        gap = r.min() - u.max()
        sep = gap > 0
        mark = "ok" if sep == want_sep else "UNEXPECTED"
        ok = ok and (sep == want_sep)
        print("%s  real %6.1f+-%4.1f  nuis %6.1f+-%4.1f  gap=%+6.1f  "
              "separable=%-5s  %s" % (label, r.mean(), r.std(),
                                      u.mean(), u.std(), gap, sep, mark))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

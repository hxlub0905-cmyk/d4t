#!/usr/bin/env python3
# ADEPT realistic BSE synthetic lot — authored 2026-08-14 (with the user, five rounds).
"""擬真 BSE MG×EPI×inner-spacer 合成 lot 產生器。

`make_sample.py` 產的是「引擎吃得動」的抽象圖案；這一支產的是「看起來像
真的 SEM、而且**逼你用 ROI**」的驗證資料 —— 缺陷亮起後的絕對 GLV 與
MG+bloom 的亮部完全重疊，整張圖的 max/percentile 挑不出它，只有「量
spacer 裡面」看得到（可分性數字見 `validate_mgepi.py`）。

規格（1.5 nm/px、patch 81×81，使用者 2026-08-14 五輪迭代收斂）：
  - MG：直線，GLV 200–220，pitch 42 nm（28 px）、線寬 14 nm（9.3 px）
  - EPI：橫帶（SiGe，BSE 下亮、Ge 濃度不均 → 帶內大尺度濃度渦），
    GLV 160–180，pitch 39/35 nm 交錯、線寬 12 nm（8 px）
  - inner spacer：貼著每根 MG 左右緣、寬 6 nm（4 px）、只長在 EPI 上，
    GLV 138–150 —— 上限壓在 EPI 下限之下 ≥13 GLV：EPI 抽到暗端的 die
    也要保得住「spacer 是谷」（rev3 抓到一顆 EPI≈154 的 die，spacer 158
    跟它齊平，剖面整段平掉、找谷變成亂挑）
  - STI 暗區 ~72（也有顆粒與低頻斑駁 —— 暗帶不是平灰）
  - 缺陷（Hf，原子序高 → BSE 下比 SiGe/MG 都亮）：一律出現在 inner
    spacer 中間亮起，~3 px 尺度
  - 質感：LER 邊緣抖動（沿線相關）、MG 側壁 2–4 px 梯度、SE/BSE 邊緣
    增亮（spacer 凹縫壓到 25%）、束斑模糊、shot noise、掃描列雜訊、
    輕微照度梯度

實作：**3× 超取樣**（243²）再箱型縮回 81² —— 3× 之下所有幾何都是整數
（MG 84/28、EPI 78/70/24），非整數線寬與次像素邊緣自然出現。
線寬是 **FWHM** 定義：覆蓋率斜坡跨在名義邊緣上（邊緣處 = 0.5）。
斜坡往帶內吃的寫法會讓 soft 越大線越細（rev3 被使用者抓到：MG/EPI
都變細）—— 見 `_band_cov`。

用法：
  python3 tools/make_mgepi_real.py OUT_DIR [--n 48] [--seed 11]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
_TOOLS = os.path.dirname(os.path.abspath(__file__))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import cv2  # noqa: E402
import tifffile  # noqa: E402
from make_sample import _DIE_PITCH_UM, _make_klarf_text  # noqa: E402
from adept.core.ingest import dataset, klarf_core, tiff_index  # noqa: E402

S = 3                    # 超取樣倍率
SIZE = 81                # patch 邊長（px）
HS = SIZE * S            # 243
MG_PITCH, MG_W = 28.0 * S, 9.33 * S          # 84, 28
EPI_PITCHES = (26.0 * S, 23.33 * S)          # 78, 70（交錯）
EPI_W = 8.0 * S                              # 24

GLV_STI = 72.0
# inner spacer（EPI 與 MG 交界、位在 EPI 上）。上限壓在 EPI 下限（163）
# 之下 ≥13 GLV —— 理由見檔頭。
GLV_SPACER = (138.0, 150.0)
GLV_MG = (203.0, 217.0)      # 每根線的均值範圍（規格 200–220）
GLV_EPI = (163.0, 177.0)     # 每條帶的均值範圍（規格 160–180）
EDGE_BLOOM = 4.0             # SE/BSE 邊緣增亮
LER_AMP = 0.8 * S            # 邊緣抖動振幅（≈1 px）
LER_CORR = 12 * S            # 抖動的沿線相關長度
MG_SOFT = 9.0                # MG 側壁梯度（3x 座標 ≈ 2.3 px 實際）
EPI_SOFT = 4.0
SPACER_SOFT = 3.0

SPACER_W = 4.0 * S           # inner spacer 寬（6 nm = 4 px）
REAL_TYPES = ("spacer_bright",)   # 缺陷一律：spacer 中間亮起


def _smooth1d(rng, n, corr, amp):
    """沿線相關的邊緣抖動：白雜訊 → 盒平滑 → 縮到振幅。"""
    raw = rng.normal(0.0, 1.0, n + corr)
    k = np.ones(corr) / corr
    sm = np.convolve(raw, k, mode="valid")[:n]
    sm = sm / (np.abs(sm).max() + 1e-9)
    return sm * amp


def _band_cov(centerpos, width, edge_jitter_lo, edge_jitter_hi, axis_len, soft):
    """一條帶的**軟覆蓋率**（0–1，trapezoid 剖面）。

    SEM 的線邊不是刀切的：側壁在影像上是一段梯度。``soft`` 是那段斜坡的
    寬度（3x 座標）；覆蓋率 >0.5 視為「屬於這個材質」（top label 用）。

    斜坡**跨在名義邊緣上**（邊緣處 = 0.5 覆蓋率）→ FWHM = 名義線寬。
    往帶內吃的寫法（``(x-lo)/soft`` 不加 0.5）soft 越大線越細。
    """
    lo = centerpos - width / 2.0 + edge_jitter_lo
    hi = centerpos + width / 2.0 + edge_jitter_hi
    coords = np.arange(axis_len)[:, None].astype(np.float64)
    up = np.clip((coords - lo[None, :]) / soft + 0.5, 0.0, 1.0)
    dn = np.clip((hi[None, :] - coords) / soft + 0.5, 0.0, 1.0)
    return up * dn


def _mottle(rng, hs, cells, amp):
    """低頻斑駁紋理（每個材質自己一份 —— 暗帶也不准是平灰）。"""
    g = rng.normal(0.0, 1.0, (cells, cells))
    g = np.kron(g, np.ones((hs // cells + 1, hs // cells + 1)))[:hs, :hs]
    g = cv2.GaussianBlur(g.astype(np.float32), (0, 0), hs / cells / 3.0)
    g = g / (np.abs(g).std() + 1e-9)
    return g.astype(np.float64) * amp


def render_die(rng_geom, rng_die, defect=None):
    """畫一顆 die 的 81×81 SEM 圖。

    ``rng_geom``：**test/ref 共用**的幾何（相位、每線均值的基準）——
    同一個 die 位置在相鄰 die 上圖形名義相同。
    ``rng_die``：這一片 die 自己的（LER、亮度小偏移、雜訊）——
    die-to-die 邊緣粗糙度與亮度本來就獨立。
    """
    img = np.full((HS, HS), GLV_STI, np.float64)
    img += rng_die.normal(0.0, 3.2, img.shape)          # STI 細顆粒
    img += _mottle(rng_die, HS, 10, 4.5)                # STI 低頻斑駁
    img += _mottle(rng_die, HS, 28, 2.0)                # 中頻紋理

    top = np.zeros((HS, HS), np.uint8)                  # 0=STI 1=EPI 2=MG 3=spacer
    epi_cov = np.zeros((HS, HS), np.float64)

    # ---- EPI 橫帶（兩種 pitch 交錯）----
    y = -float(rng_geom.uniform(0, sum(EPI_PITCHES)))   # 相位（幾何共用）
    k = int(rng_geom.integers(0, 2))                    # 先 39 還是先 35
    epi_rows = []
    while y < HS + EPI_PITCHES[0]:
        epi_rows.append(y)
        y += EPI_PITCHES[k % 2]
        k += 1
    for cy in epi_rows:
        base = float(rng_geom.uniform(*GLV_EPI))        # 名義亮度（幾何共用）
        base += float(rng_die.normal(0.0, 1.5))         # die-to-die 小偏移
        j_lo = _smooth1d(rng_die, HS, LER_CORR, LER_AMP)
        j_hi = _smooth1d(rng_die, HS, LER_CORR, LER_AMP)
        cov = _band_cov(cy, EPI_W, j_lo, j_hi, HS, EPI_SOFT)   # 列座標 × 欄
        # 沿線慢變化 + 帶內 2D 斑駁（SiGe 濃度渦：大尺度、平滑）
        along = _smooth1d(rng_die, HS, LER_CORR * 3, 8.0)[None, :]
        tex = _mottle(rng_die, HS, 7, 7.0)
        val = base + along + tex + rng_die.normal(0, 2.2, img.shape)
        img = img * (1 - cov) + val * cov
        top = np.where(cov > 0.5, np.uint8(1), top)
        epi_cov = np.maximum(epi_cov, cov)

    # ---- MG 直線（固定 pitch，畫在 EPI 之上）----
    x = -float(rng_geom.uniform(0, MG_PITCH))
    mg_cols = []
    while x < HS + MG_PITCH:
        mg_cols.append(x)
        x += MG_PITCH
    for cx in mg_cols:
        base = float(rng_geom.uniform(*GLV_MG))
        base += float(rng_die.normal(0.0, 1.5))
        j_lo = _smooth1d(rng_die, HS, LER_CORR, LER_AMP)
        j_hi = _smooth1d(rng_die, HS, LER_CORR, LER_AMP)
        cov = _band_cov(cx, MG_W, j_lo, j_hi, HS, MG_SOFT).T   # 轉置成欄座標
        along = _smooth1d(rng_die, HS, LER_CORR * 3, 3.0)[:, None]
        tex = _mottle(rng_die, HS, 20, 2.2)
        val = base + along + tex + rng_die.normal(0, 1.8, img.shape)
        img = img * (1 - cov) + val * cov
        top = np.where(cov > 0.5, np.uint8(2), top)

    # ---- inner spacer：EPI 與 MG 的交界、位在 EPI 上（比兩者都暗）----
    # 貼著每根 MG 的左右緣、寬 SPACER_W，只長在 EPI 的列上。
    for cx in mg_cols:
        for sign in (-1, +1):
            edge = cx + sign * (MG_W / 2.0)
            x0 = edge if sign > 0 else edge - SPACER_W
            x1 = x0 + SPACER_W
            j = _smooth1d(rng_die, HS, LER_CORR, LER_AMP * 0.7)
            center = (x0 + x1) / 2.0 + j
            cov = _band_cov(center, SPACER_W, np.zeros(HS), np.zeros(HS),
                            HS, SPACER_SOFT).T
            cov = cov * np.clip(epi_cov / 0.3, 0, 1) * (top != 2)   # 鋪滿整段 EPI（含邊緣過渡列）
            base = float(rng_geom.uniform(*GLV_SPACER))
            base += float(rng_die.normal(0.0, 1.2))
            along = _smooth1d(rng_die, HS, LER_CORR * 2, 3.5)[:, None]
            val = base + along + rng_die.normal(0, 2.2, img.shape)
            img = img * (1 - cov) + val * cov
            top = np.where(cov > 0.5, np.uint8(3), top)

    # ---- 缺陷（只有 test 有）：spacer 中間亮起 ----
    # Hf 亮到 ~200–235 —— **絕對 GLV 跟 MG+bloom 的亮部重疊**，
    # 所以整張圖的 max/percentile 挑不出它；只有「量 spacer 裡面」看得到。
    if defect is not None:
        kind, (dy, dx) = defect
        cy = HS // 2 + dy * S
        cx0 = HS // 2 + dx * S
        # 離指定點最近的 spacer 條中心（MG 邊緣 ± spacer 一半）
        cand = []
        for cxm in mg_cols:
            cand.append(cxm - MG_W / 2.0 - SPACER_W / 2.0)
            cand.append(cxm + MG_W / 2.0 + SPACER_W / 2.0)
        cx = min(cand, key=lambda c: abs(c - cx0))
        # 也要落在 EPI 帶上（挑離 cy 最近的 EPI 帶中心）
        cyb = min(epi_rows, key=lambda c: abs(c - cy))
        yy, xx = np.mgrid[0:HS, 0:HS]
        r = 3.0 * S
        g = np.exp(-(((yy - cyb) ** 2 + (xx - cx) ** 2) / (2 * (r / 1.8) ** 2)))
        img += 104.0 * g * (top == 3)         # Hf 在 BSE 下比 SiGe/MG 都亮
        img += 28.0 * g * (top != 3)          # 邊上一點暈開，比較像真的

    # ---- SE/BSE 邊緣增亮：頂層材質的邊界亮一圈 ----
    edge = np.zeros_like(img, bool)
    edge[1:, :] |= top[1:, :] != top[:-1, :]
    edge[:, 1:] |= top[:, 1:] != top[:, :-1]
    grow = edge.copy()
    grow[1:, :] |= edge[:-1, :]
    grow[:, 1:] |= edge[:, :-1]
    bloom = EDGE_BLOOM * (0.6 + 0.4 * (top > 0))
    # spacer 是凹陷的窄縫：二次電子出得來的少，邊緣增亮明顯弱 ——
    # 不壓的話 spacer 兩側會有亮縫，深度直接被吃掉一半。
    near_sp = (top == 3)
    near_sp[1:, :] |= (top[:-1, :] == 3); near_sp[:-1, :] |= (top[1:, :] == 3)
    near_sp[:, 1:] |= (top[:, :-1] == 3); near_sp[:, :-1] |= (top[:, 1:] == 3)
    bloom = np.where(near_sp, bloom * 0.25, bloom)
    img += grow * bloom

    # ---- 縮回 81² + 束斑模糊 + 照度 + 雜訊 ----
    small = img.reshape(SIZE, S, SIZE, S).mean(axis=(1, 3))
    small = cv2.GaussianBlur(small.astype(np.float32), (0, 0), 0.9)
    gx = np.linspace(-1, 1, SIZE)
    small = small + 3.5 * float(rng_die.normal(0, 1)) * gx[None, :]
    small = small + rng_die.normal(0.0, 4.5, small.shape)          # shot noise
    small = small + rng_die.normal(0.0, 1.2, (SIZE, 1))            # 掃描列雜訊
    return np.clip(small, 0, 255)


def generate(out_dir, n=48, seed=11):
    os.makedirs(out_dir, exist_ok=True)
    tiff_path = os.path.join(out_dir, "LOT_SYN.tif")
    klarf_path = os.path.join(out_dir, "LOT_SYN.001")
    gt_path = os.path.join(out_dir, "ground_truth.json")

    master = np.random.default_rng(seed)
    real_idx = set(master.choice(n, size=n // 2, replace=False).tolist())

    pages, rows, truth = [], [], {}
    for i in range(n):
        geom_seed = int(master.integers(0, 2 ** 31))
        is_real = i in real_idx
        kind = str(REAL_TYPES[int(master.integers(0, len(REAL_TYPES)))]) if is_real else "none"
        pos = (int(master.integers(-8, 9)), int(master.integers(-8, 9)))
        defect = (kind, pos) if is_real else None

        test = render_die(np.random.default_rng(geom_seed),
                          np.random.default_rng(int(master.integers(0, 2 ** 31))),
                          defect)
        ref = render_die(np.random.default_rng(geom_seed),
                         np.random.default_rng(int(master.integers(0, 2 ** 31))),
                         None)
        pages += [test.astype(np.uint8), ref.astype(np.uint8)]

        did = str(i + 1)
        truth[did] = {"is_real": bool(is_real), "type": kind}
        xrel = float(master.uniform(100.0, _DIE_PITCH_UM - 100.0))
        yrel = float(master.uniform(100.0, _DIE_PITCH_UM - 100.0))
        rows.append([did, "%.3f" % xrel, "%.3f" % yrel,
                     str(int(master.integers(-2, 3))), str(int(master.integers(-2, 3))),
                     "0", "2", str(2 * i + 1), str(2 * i + 2)])

    with tifffile.TiffWriter(tiff_path) as tw:
        for arr in pages:
            tw.write(arr, photometric="minisblack")
    with open(klarf_path, "w", encoding="utf-8", newline="") as f:
        f.write(_make_klarf_text(n, rows))
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(truth, f, ensure_ascii=False, indent=2, sort_keys=True)

    # 自我驗證（同 make_sample）
    doc = klarf_core.load(klarf_path)
    assert doc.version == "1.2"
    assert tiff_index.n_pages(tiff_path) == 2 * n
    ds = dataset.load_dataset(klarf_path)
    assert ds.kind == "ebi_patch" and len(ds.items) == n
    return {"out_dir": out_dir, "klarf": klarf_path, "tiff": tiff_path,
            "ground_truth": gt_path}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out_dir")
    ap.add_argument("--n", type=int, default=48)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args(argv)
    out = generate(args.out_dir, n=args.n, seed=args.seed)
    print("ok:", out["klarf"], out["tiff"], out["ground_truth"])


if __name__ == "__main__":
    main()

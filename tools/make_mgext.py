#!/usr/bin/env python3
# d4t MG-extrusion synthetic lot — authored 2026-08-22.
"""MG extrusion 合成 lot —— 缺陷是 **MG 材質從側壁竄出**，凸出長度已知。

跟 `mgepi_real3` 的差別只有缺陷本身，其餘物理設定逐項沿用（1.5 nm/px、
81×81 patch、MG pitch 42 nm / 線寬 14 nm、EPI pitch 39/35 nm 交錯 / 帶寬 12 nm、
inner spacer 6 nm、BSE 對比、LER、束斑模糊、shot noise）：

    mgepi_real3   缺陷 = inner spacer **中間**冒出一顆 Hf（比 MG 還亮的異材）
    這一份        缺陷 = **MG 自己**從側壁長出去一段（同材質、同亮度）

為什麼要另外做一組
------------------
`mgepi_real3` 只答得出「分不分得開」，答不出「**量得準不準**」——
那一顆 Hf 沒有一個叫做「凸出量」的真值可以對。這一份每一顆都帶著

    extrusion_px  = 從 MG 的**名義邊緣**往外算，凸出了幾個 pixel

而且它是**設計出來的**（不是量出來的），所以量測結果可以直接跟它回歸，
得到斜率／截距／殘差 —— 那才是 CD 準確度的證據。

缺陷幾何
--------
貼著某一根 MG 的左緣或右緣、落在某一條 EPI 帶上，往外伸出 `L` px、
沿 MG 方向高 `H` px，末端是圓的（不是方頭），側壁軟硬度與 MG 相同。
**它蓋掉那一段 inner spacer**（凸出去的是 MG 材質，spacer 被擠掉了）——
這正是 extrusion 在製程上會做的事，也是它跟「spacer 裡冒出一顆東西」
在影像上真正的差別。

缺陷位置**不隨機灑**（跟 mgepi_real3 相反）：一律放在離 patch 正中心最近
的那一根 MG × 最近的那一條 EPI 帶上。理由是這一份要問的是「量得準不準」，
把「框有沒有放對」這個變因拿掉，兩件事才分得開。要驗定位能力請用
`mgepi_real3`，那一份是特地灑開的。

實作：**3× 超取樣**（243²）再箱型縮回 81²，所以非整數線寬與次像素邊緣
自然出現。KLARF 沿用 `tools/make_sample.py` 的 `_make_klarf_text`。

產出的資料**不進版控**（`0822test/` 在 .gitignore 裡）—— 它是 2 MB 的 TIFF，
而且用這一支隨時重產得出來，逐位元組相同（種子固定、不用 `Date.now` 那類東西）。

用法
----
    python tools/make_mgext.py <輸出目錄> [顆數] [seed]

預設 60 顆、seed 23 —— 那正是 `docs/plans/F20-pick-defect-box.md` 與
2026-08-22 那份校正報告用的那一批。
"""
from __future__ import annotations

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

import cv2                                                        # noqa: E402
import tifffile                                                   # noqa: E402
from make_sample import _DIE_PITCH_UM, _make_klarf_text           # noqa: E402
from d4t.core.ingest import dataset, klarf_core, tiff_index       # noqa: E402

# --------------------------------------------------------------------------- #
# 幾何與材質（與 mgepi_real3 逐項相同）
# --------------------------------------------------------------------------- #
S = 3                                        # 超取樣倍率
SIZE = 81                                    # patch 邊長（px）
HS = SIZE * S                                # 243
NM_PER_PX = 1.5

MG_PITCH, MG_W = 28.0 * S, 9.33 * S          # 84, 28
EPI_PITCHES = (26.0 * S, 23.33 * S)          # 78, 70（交錯）
EPI_W = 8.0 * S                              # 24
SPACER_W = 4.0 * S                           # inner spacer 寬（6 nm = 4 px）

GLV_STI = 72.0
GLV_SPACER = (138.0, 150.0)
GLV_MG = (203.0, 217.0)
GLV_EPI = (163.0, 177.0)
EDGE_BLOOM = 4.0
LER_AMP = 0.8 * S
LER_CORR = 12 * S
MG_SOFT = 9.0                                # MG 側壁梯度（3x 座標 ≈ 2.3 px）
EPI_SOFT = 4.0
SPACER_SOFT = 3.0

# --------------------------------------------------------------------------- #
# 缺陷（這一份唯一新增的東西）
# --------------------------------------------------------------------------- #
#: 凸出長度的抽樣範圍（px，從 MG 名義邊緣往外算）。下限刻意壓在 spacer 寬
#: （4 px）之下、上限跨過它 —— 這樣同一批裡同時有「還沒碰到 EPI」與
#: 「整條 spacer 被吃掉、MG 與 EPI 連起來」兩種，回歸線才有兩端。
EXT_RANGE_PX = (1.0, 8.0)

#: 凸出物沿 MG 方向的高度（px）。太矮的話量測線不夠，`cd_n` 會少到沒有意義。
EXT_HEIGHT_PX = (3.0, 6.0)

#: 凸出物的亮度相對於它長出來的那根 MG。1.0 = 同材質同亮度（預設，
#: 也就是「MG 自己長出去」）。想做成異材（像 mgepi_real3 的 Hf）就調高。
EXT_GLV_SCALE = 1.0


def _smooth1d(rng, n, corr, amp):
    """沿線相關的邊緣抖動：白雜訊 → 盒平滑 → 縮到振幅。"""
    raw = rng.normal(0.0, 1.0, n + corr)
    k = np.ones(corr) / corr
    sm = np.convolve(raw, k, mode="valid")[:n]
    sm = sm / (np.abs(sm).max() + 1e-9)
    return sm * amp


def _band_cov(centerpos, width, edge_jitter_lo, edge_jitter_hi, axis_len, soft):
    """一條帶的軟覆蓋率（0–1）。斜坡**跨在名義邊緣上** → FWHM = 名義線寬。"""
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


def _soft_step(coords, lo, hi, soft):
    """一維軟方波（同 `_band_cov` 的斜坡定義，但直接給上下界）。"""
    up = np.clip((coords - lo) / soft + 0.5, 0.0, 1.0)
    dn = np.clip((hi - coords) / soft + 0.5, 0.0, 1.0)
    return up * dn


def _extrusion_cov(cx_mg, side, cy, length_3x, height_3x):
    """凸出物的覆蓋率（3x 座標）——貼著 MG 側壁、末端是圓的。

    `cx_mg` 是那根 MG 的中心、`side` 是 -1（左）或 +1（右）。
    從 MG 的**名義邊緣** ``cx_mg + side*MG_W/2`` 往外伸 `length_3x`。

    末端做成圓的而不是方的：方頭在剖面上會多一條完全垂直的邊，
    量出來的次像素位置會漂亮得不像真的，而那會讓這批資料變成一個
    比實際容易的題目。
    """
    yy, xx = np.mgrid[0:HS, 0:HS].astype(np.float64)
    edge = cx_mg + side * (MG_W / 2.0)
    tip = edge + side * length_3x
    lo, hi = (min(edge, tip), max(edge, tip))

    # 主體：X 方向從 MG 邊緣到末端、Y 方向是高度
    body = (_soft_step(xx, lo, hi, MG_SOFT)
            * _soft_step(yy, cy - height_3x / 2.0, cy + height_3x / 2.0, MG_SOFT))

    # 末端的圓角：半徑 = 高度的一半，圓心退回 length 一半的地方
    r = height_3x / 2.0
    cap_c = tip - side * r
    dist = np.hypot(xx - cap_c, yy - cy)
    cap = np.clip((r - dist) / MG_SOFT + 0.5, 0.0, 1.0)
    # 圓角只負責末端外側那一段，內側交給 body
    outer = ((xx - cap_c) * side) > 0
    return np.clip(np.where(outer, np.maximum(body, cap), body), 0.0, 1.0)


def render_die(rng_geom, rng_die, defect=None):
    """畫一顆 die 的 81×81 SEM 圖。

    `rng_geom` 是 test/ref **共用**的幾何（相位、每條線的名義亮度）；
    `rng_die` 是這一片 die 自己的（LER、亮度小偏移、雜訊）。

    `defect` 是 ``None`` 或 ``(side, length_3x, height_3x)``；
    真正放在哪一根 MG／哪一條 EPI 帶由這支函式決定（離中心最近的那一組），
    並且透過 `render_die.last_defect` 回報實際座標，讓 ground truth 記得下來。
    """
    img = np.full((HS, HS), GLV_STI, np.float64)
    img += rng_die.normal(0.0, 3.2, img.shape)
    img += _mottle(rng_die, HS, 10, 4.5)
    img += _mottle(rng_die, HS, 28, 2.0)

    top = np.zeros((HS, HS), np.uint8)          # 0=STI 1=EPI 2=MG 3=spacer
    epi_cov = np.zeros((HS, HS), np.float64)

    # ---- EPI 橫帶（兩種 pitch 交錯）----
    y = -float(rng_geom.uniform(0, sum(EPI_PITCHES)))
    k = int(rng_geom.integers(0, 2))
    epi_rows = []
    while y < HS + EPI_PITCHES[0]:
        epi_rows.append(y)
        y += EPI_PITCHES[k % 2]
        k += 1
    for cy in epi_rows:
        base = float(rng_geom.uniform(*GLV_EPI)) + float(rng_die.normal(0.0, 1.5))
        j_lo = _smooth1d(rng_die, HS, LER_CORR, LER_AMP)
        j_hi = _smooth1d(rng_die, HS, LER_CORR, LER_AMP)
        cov = _band_cov(cy, EPI_W, j_lo, j_hi, HS, EPI_SOFT)
        along = _smooth1d(rng_die, HS, LER_CORR * 3, 8.0)[None, :]
        tex = _mottle(rng_die, HS, 7, 7.0)
        val = base + along + tex + rng_die.normal(0, 2.2, img.shape)
        img = img * (1 - cov) + val * cov
        top = np.where(cov > 0.5, np.uint8(1), top)
        epi_cov = np.maximum(epi_cov, cov)

    # ---- MG 直線 ----
    x = -float(rng_geom.uniform(0, MG_PITCH))
    mg_cols = []
    while x < HS + MG_PITCH:
        mg_cols.append(x)
        x += MG_PITCH
    mg_level = {}
    for cx in mg_cols:
        base = float(rng_geom.uniform(*GLV_MG)) + float(rng_die.normal(0.0, 1.5))
        mg_level[cx] = base
        j_lo = _smooth1d(rng_die, HS, LER_CORR, LER_AMP)
        j_hi = _smooth1d(rng_die, HS, LER_CORR, LER_AMP)
        cov = _band_cov(cx, MG_W, j_lo, j_hi, HS, MG_SOFT).T
        along = _smooth1d(rng_die, HS, LER_CORR * 3, 3.0)[:, None]
        tex = _mottle(rng_die, HS, 20, 2.2)
        val = base + along + tex + rng_die.normal(0, 1.8, img.shape)
        img = img * (1 - cov) + val * cov
        top = np.where(cov > 0.5, np.uint8(2), top)

    # ---- inner spacer（貼著每根 MG 的左右緣、只長在 EPI 上）----
    for cx in mg_cols:
        for sign in (-1, +1):
            edge = cx + sign * (MG_W / 2.0)
            x0 = edge if sign > 0 else edge - SPACER_W
            j = _smooth1d(rng_die, HS, LER_CORR, LER_AMP * 0.7)
            center = (x0 + x0 + SPACER_W) / 2.0 + j
            cov = _band_cov(center, SPACER_W, np.zeros(HS), np.zeros(HS),
                            HS, SPACER_SOFT).T
            cov = cov * np.clip(epi_cov / 0.3, 0, 1) * (top != 2)
            base = float(rng_geom.uniform(*GLV_SPACER)) + float(rng_die.normal(0.0, 1.2))
            along = _smooth1d(rng_die, HS, LER_CORR * 2, 3.5)[:, None]
            val = base + along + rng_die.normal(0, 2.2, img.shape)
            img = img * (1 - cov) + val * cov
            top = np.where(cov > 0.5, np.uint8(3), top)

    # ---- 缺陷：MG 從側壁竄出去一段（只有 test 有）----
    render_die.last_defect = None
    if defect is not None:
        side, length_3x, height_3x = defect
        cx = min(mg_cols, key=lambda c: abs(c - HS / 2.0))       # 離中心最近的 MG
        cy = min(epi_rows, key=lambda c: abs(c - HS / 2.0))      # 離中心最近的 EPI 帶
        cov = _extrusion_cov(cx, side, cy, length_3x, height_3x)
        base = mg_level[cx] * EXT_GLV_SCALE
        val = base + _mottle(rng_die, HS, 20, 2.2) + rng_die.normal(0, 1.8, img.shape)
        img = img * (1 - cov) + val * cov
        top = np.where(cov > 0.5, np.uint8(2), top)              # 它就是 MG
        render_die.last_defect = {
            "mg_center_px": round(cx / S, 3),
            "mg_edge_px": round((cx + side * MG_W / 2.0) / S, 3),
            "tip_px": round((cx + side * (MG_W / 2.0 + length_3x)) / S, 3),
            "row_px": round(cy / S, 3),
            "side": "right" if side > 0 else "left",
        }

    # ---- SE 邊緣增亮 ----
    edge = np.zeros_like(img, bool)
    edge[1:, :] |= top[1:, :] != top[:-1, :]
    edge[:, 1:] |= top[:, 1:] != top[:, :-1]
    grow = edge.copy()
    grow[1:, :] |= edge[:-1, :]
    grow[:, 1:] |= edge[:, :-1]
    bloom = EDGE_BLOOM * (0.6 + 0.4 * (top > 0))
    near_sp = (top == 3)
    near_sp[1:, :] |= (top[:-1, :] == 3); near_sp[:-1, :] |= (top[1:, :] == 3)
    near_sp[:, 1:] |= (top[:, :-1] == 3); near_sp[:, :-1] |= (top[:, 1:] == 3)
    bloom = np.where(near_sp, bloom * 0.25, bloom)
    img += grow * bloom

    # ---- 縮回 81² + 束斑模糊 + 照度 + 雜訊 ----
    small = img.reshape(SIZE, S, SIZE, S).mean(axis=(1, 3))
    small = cv2.GaussianBlur(small.astype(np.float32), (0, 0), 0.9)
    gx = np.linspace(-1, 1, SIZE)
    small = small + 3.5 * np.outer(rng_die.normal(0, 1), np.ones(SIZE))[0] * gx[None, :]
    small = small + rng_die.normal(0.0, 4.5, small.shape)        # shot noise
    small = small + rng_die.normal(0.0, 1.2, (SIZE, 1))          # 掃描列雜訊
    return np.clip(small, 0, 255)


def generate(out_dir, n=60, seed=23, n_clean=None):
    """產生一組 lot。`n_clean` 顆沒有缺陷，其餘的凸出量掃過 `EXT_RANGE_PX`。

    凸出量用**等距**取樣而不是亂數：同樣的顆數之下，等距在回歸線上鋪得比較
    均勻，斜率的信賴區間窄得多。哪一顆是哪個長度仍然被 `seed` 打散，
    所以它跟座標、亮度、雜訊之間沒有相關。
    """
    os.makedirs(out_dir, exist_ok=True)
    tiff_path = os.path.join(out_dir, "LOT_SYN.tif")
    klarf_path = os.path.join(out_dir, "LOT_SYN.001")
    gt_path = os.path.join(out_dir, "ground_truth.json")

    if n_clean is None:
        n_clean = n // 3
    n_def = n - n_clean
    master = np.random.default_rng(seed)

    lengths = np.linspace(EXT_RANGE_PX[0], EXT_RANGE_PX[1], n_def)
    order = master.permutation(n)
    is_def = np.zeros(n, bool)
    is_def[order[:n_def]] = True
    len_iter = iter(lengths[master.permutation(n_def)])

    pages, rows, truth = [], [], {}
    for i in range(n):
        geom_seed = int(master.integers(0, 2 ** 31))
        if is_def[i]:
            L = float(next(len_iter))
            H = float(master.uniform(*EXT_HEIGHT_PX))
            side = int(master.choice((-1, 1)))
            defect = (side, L * S, H * S)
        else:
            L = H = 0.0
            side = 0
            defect = None

        test = render_die(np.random.default_rng(geom_seed),
                          np.random.default_rng(int(master.integers(0, 2 ** 31))),
                          defect)
        where = render_die.last_defect
        ref = render_die(np.random.default_rng(geom_seed),
                         np.random.default_rng(int(master.integers(0, 2 ** 31))),
                         None)
        pages += [test.astype(np.uint8), ref.astype(np.uint8)]

        did = str(i + 1)
        truth[did] = {
            "is_real": bool(is_def[i]),
            "type": "mg_extrusion" if is_def[i] else "none",
            # 這一份的重點：從 MG 名義邊緣往外算的真實凸出量
            "extrusion_px": round(L, 4),
            "extrusion_nm": round(L * NM_PER_PX, 4),
            "height_px": round(H, 4),
            # 量測線量到的「MG＋凸出物」在最寬那一列的名義寬度
            "widest_px": round(9.33 + L, 4) if is_def[i] else 9.33,
        }
        if where:
            truth[did].update(where)

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

    # ---- 自我驗證（同 make_sample）----
    doc = klarf_core.load(klarf_path)
    assert doc.version == "1.2", doc.version
    assert tiff_index.n_pages(tiff_path) == 2 * n
    ds = dataset.load_dataset(klarf_path)
    assert ds.kind == "ebi_patch" and len(ds.items) == n, (ds.kind, len(ds.items))
    have = sorted(v["extrusion_px"] for v in truth.values() if v["is_real"])
    # 回傳的形狀跟 `make_sample` / `make_mgepi_real` 一字不差 —— 三支產生器
    # 的呼叫端（CLI 與測試）因此只要學一次。
    return {"klarf": klarf_path, "tiff": tiff_path, "ground_truth": gt_path,
            "n": n, "n_defects": len(have),
            "extrusion_px": (have[0], have[-1]) if have else (0.0, 0.0)}


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="MG extrusion 合成 lot 產生器")
    ap.add_argument("out_dir", help="輸出目錄（會建立）")
    ap.add_argument("--n", type=int, default=60, help="幾顆 defect")
    ap.add_argument("--clean", type=int, default=None,
                    help="其中幾顆沒有缺陷（預設 n/3）")
    ap.add_argument("--seed", type=int, default=23)
    args = ap.parse_args(argv)
    out = generate(args.out_dir, n=args.n, seed=args.seed, n_clean=args.clean)
    lo, hi = out["extrusion_px"]
    print("ok:", out["klarf"], out["tiff"], out["ground_truth"])
    print("    %d 顆：%d 顆有 extrusion（%.2f – %.2f px ＝ %.1f – %.1f nm）、%d 顆乾淨"
          % (out["n"], out["n_defects"], lo, hi,
             lo * NM_PER_PX, hi * NM_PER_PX, out["n"] - out["n_defects"]))
    return out


if __name__ == "__main__":
    main()

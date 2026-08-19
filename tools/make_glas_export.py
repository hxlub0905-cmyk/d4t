#!/usr/bin/env python3
# d4t synthetic GLAS export — authored 2026-08-18 (F11 Region-3 第 1 步).
"""合成一份 **GLAS 匯出**（`<id>_label.png` + v4 manifest），給家用機開發用。

為什麼需要這支
--------------
Region-3（GDS mode）吃的是 GLAS 匯出的東西，而 **GLAS 的輸出只在公司機上**
（`AGENTS.md` §1：新功能只能用真實資料驗證的話，它在家用機上就等於不能驗證）。
所以先有一份形狀一模一樣的合成品，`roi_from_mask` 才有東西可以對著寫。

它不是 GLAS 的替代品，是**格式與幾何的替身**：欄位名、檔名慣例、label 的整數
語意、三種 PNG 的通道數，全部照真實匯出（見
[`docs/GLAS-INTERFACE.md`](../docs/GLAS-INTERFACE.md) §3.4，2026-08-18 實測 399 顆）。

用法
----
```
python tools/make_sample_rsem.py /tmp/lot --n 12          # 先有一個 RSEM lot
python tools/make_glas_export.py /tmp/lot /tmp/gds        # 再產它的 sidecar
python tools/check_glas_export.py /tmp/gds --samples 2    # 健檢應該全過
```

第一個參數是 **RSEM lot 的資料夾**（裡面有 KLARF）—— defect id 與影像尺寸都從
那份 KLARF 讀，所以兩邊天然對得上，跟真實情況一樣（GLAS 也是讀同一份 KLARF）。

同一組參數（含 `--seed`）產出的每個檔案**位元組完全相同**。

刻意做進去的四件事
------------------
每一件都對應一個 d4t 會安靜出錯的地方，所以測試資料裡一定要有：

1. **圖案是非週期的。** GDS 的使用時機就在非週期區域（使用者 2026-08-18），
   而只用條紋測的話，偷偷跑進去的週期假設永遠不會被抓到。這裡的形狀是亂數
   放的矩形與 **L 形**，不是等距的條紋。
2. **有 L 形。** 它的 bounding box 會框到別的材質 —— 「取 bbox」與「精確拆成
   矩形」的差別只有這種形狀看得出來。
3. **後面的層蓋掉前面的層**（`lbl[m > 0] = id`，跟 GLAS 一樣），而且 `--eaten`
   會刻意讓某一顆的某一層被蓋光 —— 名字還在 `label_map` 裡，區域卻是空的。
4. **有壞的樣本**：`--miss` 幾顆沒有 label 檔（manifest 那一列的 `label_png`
   是空的，就像 GLAS 被分數門檻擋掉那樣）、`--wrong-size` 幾顆的 label 跟影像
   不一樣大。健檢與卡片都要對得出來。

label 的幾何**不對應 SEM 影像的像素**
--------------------------------------
lot 的影像是 `make_sample_rsem.py` 的週期方格，而這裡的 layout 刻意非週期 ——
兩者對不起來。這對 `roi_from_mask` 沒有影響（它只讀 label 那條流，從不看 SEM），
但**用這份資料量出來的 GLV 沒有意義**，所以測試要斷言幾何與計數，不要斷言灰階。

要看得對得起來的話，用同時產出的 **`<id>_gray.png`** 當影像（它是同一份 layout
的 SEM-like renderer，跟 label 逐像素對齊）—— 那也正是 GLAS 的 gray 的用途。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

# 讓 `python tools/make_glas_export.py` 不裝套件也能 import d4t（同 make_sample_rsem）
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from d4t.core.ingest import klarf_core  # noqa: E402

#: manifest 的 schema 與欄位順序 —— 照 2026-08-18 實測的那一份（v4）。
SCHEMA = "mmh-gds-overlay-v4"
COLUMNS = ["image_id", "raw_png", "overlay_png", "fine_dx_nm", "fine_dy_nm",
           "score", "status", "gray_png", "label_png", "id_source", "page",
           "width_px", "height_px", "nm_per_px", "label_view_png"]

#: alignment 檔的 schema 與欄位（`gds_align_tool.ALIGNMENT_COLUMNS`）。
ALIGN_SCHEMA = "mmh-gds-alignment-v1"
ALIGN_COLUMNS = ["image_id", "klarf_path", "gds_path", "poi_layer",
                 "coarse_dx_nm", "coarse_dy_nm", "fine_dx_nm", "fine_dy_nm",
                 "score", "nm_per_px"]

#: 層的名字**刻意長成 GLAS 的形狀**（`NAME (L17/D0)` / 裸的 `L17/D0`）——
#: 那個形狀裡的 `/` 與空白是 d4t 的區域名規則不收的字元，而「怎麼改寫」
#: 是 `roi_from_mask` 一定要處理的事。用乾淨的名字產測試資料等於把那題藏起來。
LAYER_NAMES = ("L17/D0", "L21/D0", "L33/D0", "L44/D2", "L51/D0", "L60/D0")

#: 每層畫成什麼灰階（gray 圖用）。跟 GLAS 一樣是「每層一個 fg_glv」。
LAYER_GLV = (220, 200, 100, 160, 130, 80)

#: gray 圖的背景與模糊 —— GLAS 的預設（`overlay_export` 的 `bg_glv` / `blur_sigma_px`）。
#: **label 不模糊**，那正是 label 存在的理由。
BG_GLV = 80
BLUR_SIGMA = 1.0

#: PNG 壓縮等級寫死 → 不同機器產出相同位元組（同 `make_sample_rsem`）。
_PNG_PARAMS = [int(cv2.IMWRITE_PNG_COMPRESSION), 3]

#: `label_view.png` 每層的顏色（RGB）。只是給人看的，d4t 不吃。
VIEW_COLORS = ((0, 200, 120), (240, 180, 40), (120, 160, 255),
               (240, 120, 170), (150, 210, 70), (200, 140, 240))


def safe_name(s: str) -> str:
    """``glas/core/overlay_export.py::_safe_name`` —— 檔名的來源。

    跟 `check_glas_export.safe_name` 是同一段（兩支各留一份是刻意的：檢查那支
    必須能在只有它自己的機器上跑）。改一邊就要改另一邊，`tests/` 有一條測試
    綁著兩者相等。
    """
    out = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in str(s))
    return out or "image"


def _write_png(path: str, arr: np.ndarray) -> None:
    """CJK 路徑安全 + 位元組可重現（同 `make_sample_rsem._write_image`）。"""
    ok, buf = cv2.imencode(".png", arr, _PNG_PARAMS)
    if not ok:
        raise IOError("PNG 編碼失敗：%s" % path)
    buf.tofile(path)


# --------------------------------------------------------------------------- #
# 非週期的 layout
# --------------------------------------------------------------------------- #
def layer_shapes(rng, width: int, height: int, index: int
                 ) -> List[Tuple[int, int, int, int]]:
    """一層的形狀 —— 一串矩形（**L 形就是兩個重疊的矩形**）。

    為什麼是亂數而不是等距：GDS 的使用時機在非週期區域，而等距的測試資料會讓
    「偷偷假設有週期」的程式碼一路綠燈跑到廠內才爆。所以位置與大小都由 ``rng``
    決定，只有**數量**跟著層號變（外層的層畫得大、後面的層畫得小，這樣後面的
    層才會在前面的層上切出洞來 —— 那正是要重現的那個行為）。
    """
    n = max(2, 7 - index)
    big = max(8, min(width, height) // (3 + index))
    out: List[Tuple[int, int, int, int]] = []
    for k in range(n):
        w = int(rng.integers(big // 2, big + 1))
        h = int(rng.integers(big // 2, big + 1))
        x = int(rng.integers(-w // 3, width - w // 2))      # 有的會被切到邊
        y = int(rng.integers(-h // 3, height - h // 2))
        out.append((x, y, w, h))
        # 每層的第一塊做成 **L 形**：多一個貼著它、只蓋住一半的矩形。
        # 這個形狀的 bounding box 會框到別的材質 —— 「取 bbox」與「精確拆成
        # 矩形」的差別只有它看得出來。
        if k == 0:
            out.append((x, y + h, w // 2, h))
    return out


def paint(shapes, width: int, height: int, value: int, canvas: np.ndarray
          ) -> None:
    """把一層畫上去。**後面的層蓋掉前面的層** —— 跟 GLAS 一樣。"""
    for x, y, w, h in shapes:
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(width, x + w), min(height, y + h)
        if x1 > x0 and y1 > y0:
            canvas[y0:y1, x0:x1] = value


#: 「吃掉」的時候，最後一層要比受害層大多少（像素）。夠蓋滿就好 ——
#: 蓋得越大，剩下的層與背景就越少，而那會把這張圖變成一個沒有代表性的樣本。
_EAT_MARGIN = 3


def render(rng, width: int, height: int, layers: int, eaten: bool
           ) -> Tuple[np.ndarray, np.ndarray]:
    """一顆的 ``(label, gray)``。兩張**逐像素對齊**（同一組幾何畫兩次）。

    ``eaten``：最後一層改成畫在**倒數第二層的形狀**上（各邊放大幾個像素），
    於是那一層被吃得一個像素都不剩 —— 重現「名字還在 ``label_map`` 裡、
    區域卻是空的」那個安靜的情況。

    ⚠ 第一版是「最後一層蓋滿整張圖」，結果那張圖 100% 都是同一個 id：
    其他層**跟背景**一起沒了，於是它同時不是一個像樣的 label 圖，也量不出
    「一層拆成幾個矩形」。**要吃掉的是一層，不是整張圖。**
    """
    label = np.zeros((height, width), np.uint8)
    gray = np.full((height, width), np.uint8(BG_GLV), np.uint8)
    victim: List[Tuple[int, int, int, int]] = []
    for i in range(layers):
        shapes = layer_shapes(rng, width, height, i)
        if eaten and layers >= 2 and i == layers - 1 and victim:
            m = _EAT_MARGIN
            shapes = [(x - m, y - m, w + 2 * m, h + 2 * m)
                      for x, y, w, h in victim]
        if i == layers - 2:
            victim = list(shapes)
        paint(shapes, width, height, i + 1, label)
        paint(shapes, width, height, LAYER_GLV[i % len(LAYER_GLV)], gray)
    if BLUR_SIGMA > 0:
        k = int(max(1, round(BLUR_SIGMA * 3))) * 2 + 1
        gray = cv2.GaussianBlur(gray, (k, k), float(BLUR_SIGMA))
    return label, gray


def colorize(label: np.ndarray, layers: int) -> np.ndarray:
    """`label_view.png`：**3 通道**的上色預覽。

    它存在的意義有一半是當**陷阱**：真實匯出裡它就在 label 旁邊，而指錯檔案的
    話 d4t 會把通道平均掉、把 label id 混成不存在的值，**而且不會報錯**。
    測試資料裡有它，那條路才驗得到。
    """
    view = np.zeros(label.shape + (3,), np.uint8)
    for i in range(layers):
        r, g, b = VIEW_COLORS[i % len(VIEW_COLORS)]
        view[label == i + 1] = (b, g, r)                 # cv2 寫的是 BGR
    return view


# --------------------------------------------------------------------------- #
# lot 那一邊
# --------------------------------------------------------------------------- #
def read_lot(lot_dir: str) -> Tuple[str, List[str], Dict[str, str]]:
    """從 RSEM lot 讀 ``(KLARF 路徑, DEFECTID 清單, {id: 影像檔名})``。

    **id 從 KLARF 來，不是自己編的** —— GLAS 也是這樣拿的，所以合成品跟真實
    匯出踩到的是同一條配對路徑（包含 id 長什麼樣、要不要 `_safe_name`）。
    """
    klarf = ""
    for name in sorted(os.listdir(lot_dir)):
        if os.path.splitext(name)[1].lower() in (".001", ".klarf", ".txt"):
            klarf = os.path.join(lot_dir, name)
            break
    if not klarf:
        raise SystemExit("在 %s 裡找不到 KLARF（.001 / .klarf / .txt）—— "
                         "先跑 python tools/make_sample_rsem.py <這個資料夾>"
                         % lot_dir)
    doc = klarf_core.load(klarf)
    cols = [str(c).upper() for c in doc.defect_columns]
    if "DEFECTID" not in cols:
        raise SystemExit("這份 KLARF 沒有 DEFECTID 欄位：%s" % klarf)
    col = cols.index("DEFECTID")
    ids: List[str] = []
    files: Dict[str, str] = {}
    for row in doc.defects:
        if len(row) <= col:
            continue
        did = str(row[col])
        ids.append(did)
        name = doc.defect_image_filename(row)
        if name:
            files[did] = str(name)
    return klarf, ids, files


def image_size(lot_dir: str, name: str) -> Optional[Tuple[int, int]]:
    """lot 裡那張影像多大（``(寬, 高)``）。找不到回 ``None``。"""
    for root, _dirs, names in os.walk(lot_dir):
        if name in names:
            arr = cv2.imread(os.path.join(root, name), cv2.IMREAD_UNCHANGED)
            if arr is not None:
                return int(arr.shape[1]), int(arr.shape[0])
    return None


# --------------------------------------------------------------------------- #
# 產生
# --------------------------------------------------------------------------- #
def generate(lot_dir: str, out_dir: str, layers: int = 3, seed: int = 5,
             miss: int = 1, wrong_size: int = 1, eaten: int = 1,
             size: Optional[int] = None,
             alignment: bool = True) -> Dict[str, Any]:
    """產出整份匯出。回傳 ``{"out_dir", "manifest", "rows", "label_map"}``。

    ``miss`` / ``wrong_size`` / ``eaten`` 是**刻意的壞樣本各幾顆**。它們預設不是
    0：一份「全部都對」的測試資料驗不到任何一條錯誤路徑，而那幾條路徑正是
    Region-3 最容易安靜出錯的地方。
    """
    klarf, ids, files = read_lot(lot_dir)
    if not ids:
        raise SystemExit("那份 KLARF 裡一顆 defect 都沒有：%s" % klarf)
    layers = max(1, min(int(layers), len(LAYER_NAMES)))
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    label_map = [{"id": i + 1, "layer": LAYER_NAMES[i],
                  "fg_glv": int(LAYER_GLV[i])} for i in range(layers)]
    rng = np.random.default_rng(int(seed))
    rows: List[Dict[str, Any]] = []

    # **壞樣本一律排在最後面**，順序固定：… 好的 …, eaten, miss, wrong_size。
    # 理由：健檢與開發時都是抽前幾顆看（`--samples 2`），前面就放壞的話，
    # 每一次看到的都是特例 —— 而且「一層拆成幾個矩形」那個量測會量到一張
    # 沒有代表性的圖（第一版就是這樣，第一顆 100% 都是同一個 id）。
    n_ids = len(ids)
    take = lambda k: max(0, min(int(k), n_ids))          # noqa: E731
    end = n_ids
    bad_size_at = set(range(end - take(wrong_size), end))
    end -= take(wrong_size)
    miss_at = set(range(end - take(miss), end))
    end -= take(miss)
    eaten_at = set(range(end - take(eaten), end))

    for n, did in enumerate(ids):
        base = safe_name(did)
        wh = None if size else image_size(lot_dir, files.get(did, ""))
        w, h = (int(size), int(size)) if size else (wh or (256, 256))
        bad_size = n in bad_size_at
        no_file = n in miss_at
        is_eaten = n in eaten_at

        row = {c: "" for c in COLUMNS}
        row.update({
            "image_id": did,
            # `id_source` 是 v4 才有的那一格，而它是 d4t 唯一不必猜 join key
            # 的來源（`GLAS-INTERFACE.md` §3.4）。
            "id_source": "klarf-defectid",
            "page": "",                      # RSEM 一顆一個檔，沒有頁
            "width_px": w, "height_px": h, "nm_per_px": 1,
            "fine_dx_nm": round(float(rng.normal(0, 40)), 3),
            "fine_dy_nm": round(float(rng.normal(0, 40)), 3),
            "score": round(float(rng.uniform(0.78, 0.92)), 6),
            "status": "ok",
        })
        if no_file:
            # GLAS 被分數門檻擋掉時就長這樣：**那一列在，PNG 不在**。
            rows.append(row)
            continue

        lw, lh = (w + 8, h) if bad_size else (w, h)
        label, gray = render(rng, lw, lh, layers, eaten=is_eaten)
        _write_png(os.path.join(out_dir, "%s_label.png" % base), label)
        _write_png(os.path.join(out_dir, "%s_gray.png" % base), gray)
        _write_png(os.path.join(out_dir, "%s_label_view.png" % base),
                   colorize(label, layers))
        row["label_png"] = "%s_label.png" % base
        row["gray_png"] = "%s_gray.png" % base
        row["label_view_png"] = "%s_label_view.png" % base
        rows.append(row)

    manifest = os.path.join(out_dir, "overlay_manifest.json")
    doc = {"schema": SCHEMA, "columns": COLUMNS, "images": rows,
           "label_map": label_map}
    with open(manifest, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    # CSV 那一份也產（真實匯出兩份都有）。**d4t 不讀它** —— GLAS 是用平台
    # 預設編碼寫的，非 ASCII 會壞；這裡明寫 utf-8，但 d4t 仍然只讀 JSON。
    with open(os.path.join(out_dir, "overlay_manifest.csv"), "w",
              encoding="utf-8", newline="") as f:
        w_ = csv.DictWriter(f, fieldnames=COLUMNS)
        w_.writeheader()
        for r in rows:
            w_.writerow(r)

    if alignment:
        _write_alignment(out_dir, klarf, rows, label_map)
    return {"out_dir": out_dir, "manifest": manifest, "rows": rows,
            "label_map": label_map}


def _write_alignment(out_dir: str, klarf: str, rows, label_map) -> None:
    """alignment JSON。d4t **擺框不需要它**（mask 已經對位完了），
    但真實匯出裡有，所以合成品也要有 —— 不然那條路永遠沒被走過。"""
    poi = "; ".join(e["layer"] for e in label_map)
    out = []
    for r in rows:
        out.append({
            "image_id": r["image_id"], "klarf_path": klarf,
            "gds_path": os.path.join(os.path.dirname(klarf), "SYNTH.oas"),
            "poi_layer": poi,
            "coarse_dx_nm": 3_940_000.0, "coarse_dy_nm": 1_670_000.0,
            "fine_dx_nm": r["fine_dx_nm"], "fine_dy_nm": r["fine_dy_nm"],
            "score": r["score"], "nm_per_px": 1,
        })
    with open(os.path.join(out_dir, "alignment.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump({"schema": ALIGN_SCHEMA, "columns": ALIGN_COLUMNS,
                   "alignments": out, "synthetic_layers": []}, f, indent=2)
        f.write("\n")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="合成一份 GLAS 匯出（label PNG + v4 manifest），"
                    "給家用機開發 Region-3 用。")
    ap.add_argument("lot_dir", help="RSEM lot 的資料夾（裡面有 KLARF）")
    ap.add_argument("out_dir", help="匯出要放哪（不存在會建立）")
    ap.add_argument("--layers", type=int, default=3,
                    help="幾層 POI（預設 3，最多 %d）" % len(LAYER_NAMES))
    ap.add_argument("--seed", type=int, default=5,
                    help="亂數種子（同 seed 產出相同位元組）")
    ap.add_argument("--miss", type=int, default=1,
                    help="幾顆**沒有** label 檔（manifest 那一列在，PNG 不在 "
                         "—— GLAS 被分數門檻擋掉時就長這樣）")
    ap.add_argument("--wrong-size", type=int, default=1, dest="wrong_size",
                    help="幾顆的 label 跟影像**不一樣大**")
    ap.add_argument("--eaten", type=int, default=1,
                    help="幾顆刻意讓最後一層蓋光中間那一層（名字還在 "
                         "label_map 裡、區域卻是空的）")
    ap.add_argument("--size", type=int, default=0,
                    help="強制影像邊長（預設 0 = 照 lot 裡那張圖的大小）")
    ap.add_argument("--no-alignment", action="store_true",
                    help="不要產 alignment.json")
    args = ap.parse_args(argv)

    res = generate(args.lot_dir, args.out_dir, layers=args.layers,
                   seed=args.seed, miss=args.miss,
                   wrong_size=args.wrong_size, eaten=args.eaten,
                   size=args.size or None, alignment=not args.no_alignment)
    got = sum(1 for r in res["rows"] if r["label_png"])
    print("%s：%d 顆，其中 %d 顆有 label；%d 層（%s）"
          % (res["out_dir"], len(res["rows"]), got, len(res["label_map"]),
             ", ".join(e["layer"] for e in res["label_map"])))
    bad = args.miss + args.wrong_size + args.eaten
    if bad:
        print("其中**刻意**放了壞樣本（最後 %d 顆）：%d 顆沒有 label 檔、"
              "%d 顆尺寸不符、%d 顆有一層被蓋光 —— 所以健檢會有紅字，"
              "那是對的。" % (bad, args.miss, args.wrong_size, args.eaten))
    print("驗一下：python tools/check_glas_export.py %s --samples 2"
          % res["out_dir"])
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())

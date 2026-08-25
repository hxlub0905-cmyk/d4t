#!/usr/bin/env python3
# d4t 配對健檢 — authored 2026-08-20（F15 拿真實資料驗收）.
"""拿**真的兩份 lot** 跑一次配對＋對圖，印出一份可以安心貼出來的報告。

為什麼需要這支
--------------
F15 那條鏈（配對 → 對圖 → 帶欄位）有四個數字是**猜不出來的**，而它們全都
要拿真實資料才問得到答案：

1. **容差**（`tol_nm`）—— 兩台機台報的座標差多少才算同一顆？
2. **尺度**（`nm/px`）—— 兩邊的像素大小比例對不對？填錯的話 NCC 會整批垮掉，
   而垮掉的樣子跟「配錯顆」一模一樣。
3. **stage offset** —— defect 偏離圖中心多少？**中位數的正負號**同時回答了
   「KLARF 的 y 軸與影像的列方向誰正誰負」那個問題。
4. **搜尋框夠不夠**（`search_within`）—— 使用者估 FOV 的 15%，真的嗎？

一顆一顆看是看不出這四件事的：它們是**分布**，不是單一數值。所以這支跑一批、
印分布、然後**直接講出建議值**。

跟 `check_glas_export.py` / `load_probe.py` 同一條路：**不連網路、不寫檔案**
（除非你自己加 `--csv`），預設**不印任何廠內識別碼**（lot／wafer／device 名、
路徑、DEFECTID 一律不印，只印結構、統計與秒數）。要看真名自己加 `--reveal`
（那一份不要貼出來）。

    python tools/pair_probe.py 主.001 第二份.001 --n 200
    python tools/pair_probe.py 主.001 第二份.001 --nm-per-px 1.0 --second-nm-per-px 2.5
    python tools/pair_probe.py 主.001 第二份.001 --within 0        # 先不要限制搜尋框
"""
from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

#: 分布用這幾個百分位講話 —— 平均值會被幾顆離群值拖走，而這裡最想看的正是
#: 「大部分長什麼樣」與「尾巴有多長」。
PCTS = (10, 50, 90, 100)


def _pct(values, p):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if p >= 100:
        return vals[-1]
    k = (len(vals) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - lo + int(k) - k) * 0 + (vals[hi] - vals[lo]) * (k - int(k))


def _row(label, values, unit="", width=26):
    """一行分布：p10 / 中位數 / p90 / 最大。"""
    import unicodedata

    vals = [v for v in values if v is not None]
    cols = len(label) + sum(1 for ch in label
                            if unicodedata.east_asian_width(ch) in ("W", "F"))
    pad = " " * max(0, width - cols)
    if not vals:
        return "%s%s（沒有數字）" % (label, pad)
    got = [_pct(vals, p) for p in PCTS]
    return ("%s%s p10 %9.3f │ 中位數 %9.3f │ p90 %9.3f │ 最大 %9.3f  %s"
            % (label, pad, got[0], got[1], got[2], got[3], unit))


def _recipe(args):
    from d4t.core.pipeline import Recipe, RecipeNode, ScoreSpec

    nodes = {
        "load": RecipeNode("load", "load_patch",
                           {"nm_per_px": float(args.nm_per_px)}),
        "pair": RecipeNode("pair", "pair_source",
                           {"source": "second", "match": "position",
                            "tol_nm": float(args.tol_nm),
                            "candidates": int(args.candidates),
                            "carry": str(args.carry or ""),
                            "channel": str(args.second_channel or ""),
                            "nm_per_px": float(args.second_nm_per_px)}),
        "align": RecipeNode("align", "align_to",
                            {"template": str(args.channel),
                             "search": "paired",
                             "search_within": float(args.within),
                             "min_score": -1.0,     # **不要擋**：這裡要看分布
                             "out": "aligned"}),
    }
    return Recipe(recipe_id="pair-probe",
                  routes={"ebi_patch": list(nodes), "rsem": list(nodes)},
                  nodes=nodes,
                  score=ScoreSpec(expr="pair_found", threshold=0.5,
                                  bins={"below": 0, "above": 1}))


def probe(args):
    from d4t.core.ingest import pair_source as pair_ingest
    from d4t.core.ingest.dataset import load_dataset
    from d4t.core.pipeline import run_batch
    import d4t.core.steps  # noqa: F401 — 觸發卡片註冊

    out = []
    say = out.append

    t0 = time.time()
    main = load_dataset(str(args.main))
    second = load_dataset(str(args.second))
    say("主 lot   : kind=%s · %d 顆" % (main.kind, len(main.items)))
    say("第二份   : kind=%s · %d 顆" % (second.kind, len(second.items)))
    if args.reveal:
        say("           %s / %s" % (args.main, args.second))

    cols = [c.strip().upper() for c in str(args.carry or "").split(",") if c.strip()]
    rep = pair_ingest.attach(main, second, "second", columns=cols)
    missing = pair_ingest.missing_columns(second, cols)
    if missing:
        say("⚠ 這一份沒有 %s 這幾欄（它有：%s）"
            % (", ".join(missing), ", ".join(pair_ingest.columns_of(second))))
        return "\n".join(out)
    say("掛上去   : %s" % rep.summary())
    say("載入耗時 : %.1f s" % (time.time() - t0))
    say("")

    n = int(args.n)
    say("跑 %d 顆（配對容差 %g nm · 搜尋框 %g%% FOV · 候選 %d）…"
        % (n, args.tol_nm, args.within, args.candidates))
    t0 = time.time()
    results = run_batch(_recipe(args), main, workers=int(args.workers), limit=n)
    say("耗時     : %.1f s（%.0f ms/顆）"
        % (time.time() - t0, 1000.0 * (time.time() - t0) / max(1, len(results))))
    say("")

    def col(name):
        return [r.get("features", {}).get(name) for r in results]

    ok = [r for r in results if r.get("ok")]
    paired = [v for v in col("pair_found") if v is not None]
    n_paired = sum(1 for v in paired if v > 0)
    say("配對     : %d / %d 顆配到（%.0f%%）"
        % (n_paired, len(results), 100.0 * n_paired / max(1, len(results))))
    say("成功跑完 : %d / %d 顆" % (len(ok), len(results)))

    # 失敗的理由**歸類**再印 —— 一行一顆的話，幾百顆的報告沒有人讀得完，
    # 而且訊息裡可能有 defect id。
    why = {}
    for r in results:
        if r.get("ok"):
            continue
        msg = str(r.get("error") or "")
        key = msg.split(" - ")[0].split(".")[0][:90]
        why[key] = why.get(key, 0) + 1
    for key, cnt in sorted(why.items(), key=lambda kv: -kv[1])[:5]:
        say("   ✗ %d 顆：%s" % (cnt, key))
    say("")

    say("分布")
    say("-" * 100)
    say(_row("配對距離 match_dist_nm", col("match_dist_nm"), "nm"))
    say(_row("對圖分數 ncc_score", col("ncc_score")))
    say(_row("第一名比第二名 peak_ratio", col("align_peak_ratio")))
    say(_row("偏離中心 X align_off_x_px", col("align_off_x_px"), "px"))
    say(_row("偏離中心 Y align_off_y_px", col("align_off_y_px"), "px"))
    scales = [v for v in col("align_scale") if v is not None]
    if scales:
        say("用的尺度 align_scale        %.4f（小圖的 nm/px ÷ 大圖的）" % scales[0])
    for c in cols:
        say(_row("帶過來的 pair_%s" % c, col("pair_%s" % c)))
    say("")

    say("結論與建議")
    say("-" * 100)
    for line in _verdicts(args, results, col):
        say("  %s" % line)

    if args.csv:
        from d4t.core.export.report import write_csv

        write_csv(results, str(args.csv))
        say("")
        say("→ 逐顆的數字：%s（**這一份有 defect id，不要貼出來**）" % args.csv)
    return "\n".join(out)


def _verdicts(args, results, col):
    """把四個猜不出來的數字，變成四句「該填多少」。"""
    out = []
    dist = [v for v in col("match_dist_nm") if v is not None and v == v]
    ncc = [v for v in col("ncc_score") if v is not None]
    ratio = [v for v in col("align_peak_ratio") if v is not None]
    offx = [v for v in col("align_off_x_px") if v is not None]
    offy = [v for v in col("align_off_y_px") if v is not None]
    n_paired = sum(1 for v in col("pair_found") if v)

    # ① 容差
    if n_paired < 0.5 * len(results):
        out.append("① 一半以上配不到 → 容差 %g nm 太小，或兩份 KLARF 的座標系"
                   "根本不同（先把 --tol-nm 開大 10 倍看配對率會不會跳上來）。"
                   % args.tol_nm)
    elif dist:
        p90 = _pct(dist, 90)
        out.append("① 容差：90%% 的配對距離在 %.0f nm 以內 → `tol_nm` 設 %.0f "
                   "就夠（現在 %g）。" % (p90, max(50.0, p90 * 1.5), args.tol_nm))

    # ② 尺度
    if ncc:
        p50 = _pct(ncc, 50)
        if p50 < 0.3:
            out.append("② 尺度：對圖分數中位數只有 %.2f —— **整批都對不上**，"
                       "那通常不是「配錯顆」而是**兩邊的 nm/px 比例錯了**。"
                       "先確認 --nm-per-px / --second-nm-per-px，或直接試 "
                       "--within 0 看是不是被搜尋框排除掉。" % p50)
        elif p50 < 0.6:
            out.append("② 尺度：對圖分數中位數 %.2f，普通。可以試著把 nm/px "
                       "微調 ±5%% 看分數會不會整批往上走。" % p50)
        else:
            out.append("② 尺度：對圖分數中位數 %.2f —— 尺度是對的。" % p50)

    # ③ stage offset（**中位數的正負號就是那個問題的答案**）
    if offx and offy:
        mx, my = _pct(offx, 50), _pct(offy, 50)
        sx = [abs(v - mx) for v in offx]
        sy = [abs(v - my) for v in offy]
        out.append("③ stage offset：中位數 (%.1f, %.1f) px。把它填進 "
                   "`expect_dx_px` / `expect_dy_px`，搜尋框就可以縮小。"
                   % (mx, my))
        out.append("   （這兩個數字的**正負號**同時回答了「KLARF 的 y 軸與影像"
                   "的列方向誰正誰負」——之後要用座標算預期位置就靠它。）")
        out.append("④ 搜尋框：扣掉系統性的那一份之後，90%% 的顆散布在 "
                   "±(%.0f, %.0f) px 以內。" % (_pct(sx, 90), _pct(sy, 90)))

    # ⑤ 週期性結構
    if ratio:
        bad = sum(1 for v in ratio if v > 0.9)
        out.append("⑤ 可信度：%d / %d 顆的第一名與第二名差不到 10%%（peak_ratio "
                   "> 0.9）—— 那幾顆的位置是**猜的**（週期性結構）。"
                   % (bad, len(ratio)))
        if bad > 0.2 * len(ratio):
            out.append("   超過兩成 → 建議把 patch 開大一點（帶到更多不重複的"
                       "結構），或把 peak_ratio 寫進分數表達式當門檻。")
    if not out:
        out.append("（沒有足夠的數字下結論 —— 先看上面的失敗理由。）")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="拿真的兩份 lot 跑一次配對＋對圖（輸出預設已遮蔽，可以貼出來）")
    ap.add_argument("main", help="主 lot 的 KLARF（批次跑的是它的每一顆）")
    ap.add_argument("second", help="拿來對照的那一份 KLARF")
    ap.add_argument("--n", type=int, default=200, help="跑幾顆（預設 200）")
    ap.add_argument("--workers", type=int, default=1, help="平行度（預設 1）")
    ap.add_argument("--tol-nm", type=float, default=500.0, dest="tol_nm",
                    help="配對容差 nm（預設 500）")
    ap.add_argument("--within", type=float, default=15.0,
                    help="搜尋框 = FOV 的百分之幾（預設 15；0 = 整張圖）")
    ap.add_argument("--candidates", type=int, default=1,
                    help="座標最近的幾顆都留著讓 NCC 挑（預設 1）")
    ap.add_argument("--channel", default="test",
                    help="主 lot 拿哪一條流當小圖（預設 test）")
    ap.add_argument("--second-channel", default="", dest="second_channel",
                    help="第二份的哪一張圖（預設留空 = 第一張）")
    ap.add_argument("--nm-per-px", type=float, default=0.0, dest="nm_per_px",
                    help="主 lot 的像素大小 nm/px（不填 = 不知道）")
    ap.add_argument("--second-nm-per-px", type=float, default=0.0,
                    dest="second_nm_per_px", help="第二份的像素大小 nm/px")
    ap.add_argument("--carry", default="",
                    help="要帶過來的 KLARF 欄位（逗號分隔）")
    ap.add_argument("--csv", default="", help="逐顆的數字寫到這個檔（不要貼出來）")
    ap.add_argument("--reveal", action="store_true",
                    help="印出真實路徑（**這一份不要貼出來**）")
    args = ap.parse_args(argv)

    for path in (args.main, args.second):
        if not os.path.isfile(path):
            print("找不到這個檔：%s" % path, file=sys.stderr)
            return 2
    try:
        print(probe(args))
    except ImportError as e:
        print("載入不到 d4t（%s）—— 這支要在裝好 d4t 的那台機器上、"
              "在 repo 根目錄底下跑。" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

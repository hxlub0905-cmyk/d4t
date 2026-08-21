# d4t step-card library — authored 2026-07-28 (M1); rebuilt 2026-08-21 (F19).
"""cd_measure — **CD**：在哪量 × 沿哪個方向 × 邊界怎麼定義 × 怎麼收。

四個彼此正交的問題，跟 F18 拆 Gray level 是同一套辦法：

======================  ====================================================
① 在哪量？              ``source``（流）× ``roi``（區域）—— 畫布上的線
② 沿哪個方向？          ``axis`` × ``target`` —— 問的是**樣品**長什麼樣
③ 邊界怎麼定義？        ``criterion`` —— **數字實際上從這裡來**
④ 一串距離怎麼收？      ``report`` 膠囊 ＋ ``target_cd``
======================  ====================================================

**刻意不是「四個 method 四選一」。** 那種選項每一個都同時綁死②③④，使用者改一件
事實際上動了三件，而畫面上只有一個下拉在動。判準只有一句話：**這個參數問的是
使用者的樣品，還是問軟體**——「這條線是亮的還是暗的」問樣品，「用 profile 還是
contour」問軟體，後者不該出現在卡片上。

原子單位是「一條量測線」，不是「一個區域」
------------------------------------------
重做之前這張卡量的是區域的 bounding box，而 bbox 是**極值統計量**：邊界上任何
一顆離群像素 100% 傳進答案，圖再大也不會變準。換成「一條線量一個寬度、N 條線
收成一個分布」之後，平均是 CD、**σ 就是 LWR**、min 是頸縮、max 是橋接——
粗糙度不是另外加的功能，是同一趟的副產品。數學全部在 `d4t.core.algo.edge`。

三條寫死、不給選的規矩
----------------------
1. **沒有「要不要次像素」的開關。** 1 px 的量化誤差打在 10 px 的線上是 10%，
   不存在「有時候想要比較差的答案」那種時候。
2. **絕不把畫面或框的邊界當成一條邊。** patch 是以缺陷為中心裁的，結構被切掉
   一半是常態；那時候正確的行為是拒絕並講出來（``open_edge``），不是吐出一個
   等於區域寬度的數字——重做之前那張卡正是如此，於是它在既有的三份黃金值上
   **每一顆都是 128 / 128 / 16384**，一個沒有鑑別力的常數欄。
3. **量不到就不寫那一格**（不是 0、也不是 NaN）。0 進得了分數表達式、寫得進
   DSIZE，一路安靜到最後。

單位
----
一律 pixel。填了 nm/px（Load 卡上那一格）就**多配一份 nm 的**，不是換掉——
名字帶著單位就永遠不必回頭查「那份資料當初填了沒」（見 `_util.nm_twins`）。
哪些名字算長度住在 `_util.LENGTH_FEATURES`。

⚠ **舊的 ``cd_x_px`` / ``cd_y_px`` / ``area_px`` 已經沒有了**（F19，使用者
2026-08-21：「就得完全刪掉 以新的為主」）。舊 recipe 的分數表達式引用它們會拿到
``unknown-feature`` warning 指名那個變數——**那正是要看到的**：舊值是 bbox，
跟新值不是同一種量測，安靜地改寫等於換掉那條表達式的意思。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from ..algo import edge as algo_edge
from ..pipeline.context import Context
from ..pipeline.step import (
    CATEGORY_ALGO, ParamSpec, Step, StepError, register_step, GROUP_MEASURE,
)
from ._util import (
    MultiSourceStep, ensure_gray, output_prefix_spec, parse_key_list,
    roi_rect_or_none,
)

#: ``report`` 膠囊列得出來的東西。分三群（UI 那邊登記在
#: ``widgets.METRIC_GROUPS``）—— 分群不是排版偏好：粗糙度那一群只有在
#: **量測線夠多**的時候才有意義，而那件事在一排攤平的膠囊上看不出來。
REPORT_CHOICES = (
    # Width —— 這條結構有多寬
    "cd_median", "cd_mean", "cd_min", "cd_max", "cd_range",
    # Roughness —— 它有多不齊
    "cd_std", "ler_a_std", "ler_b_std",
    # Vs target —— 跟規格差多少（要填 target_cd）
    "cd_dev", "cd_dev_frac",
)

#: 預設勾這幾顆。中位數而不是平均（一條線量歪了不該把答案帶走）、σ 是 LWR、
#: min/max 是頸縮與橋接——**殺死良率的是最窄的那一段，不是平均**。
DEFAULT_REPORT = "cd_median,cd_std,cd_min,cd_max"

#: 要填 ``target_cd`` 才算得出來的那兩顆。
_NEEDS_TARGET = ("cd_dev", "cd_dev_frac")

#: 這張卡**一律**吐的五個（不在膠囊裡）。
#:
#: 前兩個是「量得準不準」（同 F18 的 ``glv_pixels``），後兩個是**卡片自己做的
#: 決定**。規矩一句話：**卡片自動做的每一個決定，都要變成一個使用者畫得出分布的
#: 數字**——方向若在整批裡逐顆翻轉，那一欄 CSV 混著兩種不同的量測，而除了
#: ``cd_axis_deg`` 之外沒有任何線索透露這件事。
#:
#: ``cd_bright``（1 = 量了亮的那條、0 = 暗的那條）是**實跑合成 lot 才發現要有
#: 的**：``target="auto"`` 在同一批裡逐顆挑了不同的極性，於是 ``cd_median``
#: 那一欄同時裝著「線寬 6.5」與「溝寬 9.4」兩群 —— 每一顆都吐得出正常數字，
#: 而 CSV 上沒有任何東西透露它們量的不是同一種東西。
ALWAYS = ("cd_n", "cd_lines", "cd_axis_deg", "cd_bright", "cd_edge_score")


@register_step
class CdMeasureStep(MultiSourceStep):
    """CD：沿一堆量測線找出把區域中心那個結構包起來的兩條邊，收成分布。"""

    key = "cd_measure"
    label = "CD"
    category = CATEGORY_ALGO
    group = GROUP_MEASURE
    help = ("Measure how wide a line or a gap is, in pixels. It lays a row of "
            "measurement lines across the region you point it at, finds the "
            "two edges on each one, and reports the spread as well as the "
            "width - so roughness comes for free. Convert to nm by filling in "
            "the pixel size on the card that loaded the images.")
    params = [
        # ① 在哪量 ------------------------------------------------------------
        ParamSpec(name="source", type="image_keys", direction="in",
                  default="test",
                  help=("Which image stream to find the edges on. Usually the "
                        "test image - a difference image has the structure "
                        "subtracted out of it, so there are no edges left to "
                        "measure.")),
        ParamSpec(name="roi", type="region_keys", direction="in", default="",
                  label="Region",
                  help=("Which region(s) to measure in - drag a line from the "
                        "Region card that defines each one. Two regions here "
                        "means the same measurement in both, and every number "
                        "gets its region's name in front of it. No line means "
                        "the whole image.")),
        # ② 沿哪個方向 --------------------------------------------------------
        ParamSpec(name="axis", type="icon_choice", default="auto",
                  label="Direction",
                  choices=["auto", "x", "y"],
                  icons=["dir_both", "dir_upright", "dir_flat"],
                  choice_help={
                      "auto": "Let the card pick whichever direction the edges "
                              "run across. It writes down what it picked in "
                              "cd_axis_deg.",
                      "x": "Measure left-to-right (for up-and-down lines).",
                      "y": "Measure top-to-bottom (for flat lines).",
                  },
                  help=("Which way to measure across the structure. Pick it "
                        "yourself if the whole lot looks the same - then every "
                        "defect is measured the same way.")),
        ParamSpec(name="target", type="icon_choice", default="auto",
                  label="Measure the",
                  choices=["auto", "bright", "dark"],
                  icons=["target_auto", "target_bright", "target_dark"],
                  choice_help={
                      "auto": "Whichever of the two sits at the middle of the "
                              "region.",
                      "bright": "The bright band (a line).",
                      "dark": "The dark band (a gap or a trench).",
                  },
                  help=("Is the thing you want to measure the bright band or "
                        "the dark one? This is a question about your sample, "
                        "not about the software.")),
        # ③ 邊界怎麼定義 ------------------------------------------------------
        ParamSpec(name="criterion", type="choice", default="threshold",
                  section="Where the edge is",
                  label="Edge is at",
                  choices=list(algo_edge.CRITERIA),
                  choice_help={
                      "threshold": "Where the brightness crosses a set height "
                                   "between the two sides. Steadiest number "
                                   "of the three.",
                      "gradient": "Where the brightness changes fastest. Least "
                                  "affected by blur and smoothing, so use it "
                                  "when you compare absolute CD across lots.",
                      "fit": "Fits an S-curve to the whole slope. Also "
                             "reports how blurred the edge is.",
                  },
                  help=("There is no single correct edge - CD is defined by "
                        "how you measure it. All three are steady; they just "
                        "differ in what they are steadiest against.")),
        ParamSpec(name="threshold_pct", type="int", default=50, min=1, max=99,
                  unit="%", section="Where the edge is",
                  label="…at this height",
                  show_when=("criterion", ("threshold",)),
                  help=("How far up the step counts as the edge. 50% of the "
                        "local contrast is the usual choice.")),
        ParamSpec(name="window", type="int", default=9, min=3, max=64,
                  unit="px", section="Where the edge is", extent=True,
                  label="Look this far around each edge",
                  help=("How much of each side to use when working out the "
                        "two levels the edge sits between. Too small and there "
                        "is no flat part to measure; too large and the "
                        "neighbouring structure gets counted in. The card "
                        "never lets this reach past the next edge.")),
        # ④ 怎麼收 ------------------------------------------------------------
        ParamSpec(name="report", type="metric_chips", default=DEFAULT_REPORT,
                  section="Report", label="Report",
                  choices=list(REPORT_CHOICES),
                  help=("Which numbers to write out. The width ones describe "
                        "the structure; the roughness ones are the spread "
                        "across the measurement lines - cd_std is LWR (the "
                        "usual 3-sigma LWR is three times it), and ler_a / "
                        "ler_b are the two edges wandering on their own.")),
        ParamSpec(name="target_cd", type="float", default=0.0, min=0.0,
                  max=1e6, unit="px", section="Report",
                  label="Target CD",
                  help=("What this structure is supposed to measure, from your "
                        "process spec. Fill it in and you also get how far off "
                        "this defect is - which is usually the number worth "
                        "binning on. Leave it at 0 to skip.")),
        # 進階 ----------------------------------------------------------------
        ParamSpec(name="line_step", type="int", default=1, min=1, max=64,
                  unit="px", advanced=True,
                  label="One line every",
                  help=("Measure only every Nth line. Leave it at 1 unless the "
                        "region is very tall and you want it faster.")),
        ParamSpec(name="line_bin", type="int", default=1, min=1, max=64,
                  unit="px", advanced=True,
                  label="Average this many lines together",
                  help=("Averaging neighbouring lines makes each width less "
                        "noisy, but it also smooths the roughness away - the "
                        "wobble you are trying to measure is exactly what gets "
                        "averaged out. Leave it at 1 to measure roughness.")),
        ParamSpec(name="min_lines", type="int", default=3, min=1, max=999,
                  advanced=True,
                  label="Need at least this many lines",
                  help=("If fewer measurement lines than this succeed, no "
                        "width is written for this defect at all - a mean of "
                        "two lines is not a measurement. The counts are still "
                        "written so you can see what happened.")),
        ParamSpec(name="min_edge", type="float",
                  default=algo_edge.MIN_QUALITY, min=0.0, max=0.95,
                  advanced=True,
                  label="Ignore edges weaker than",
                  help=("How much an edge has to stand out from the noise on "
                        "its own line before it counts, from 0 (anything) to "
                        "0.95 (only very clean edges). The default 0.5 means "
                        "the step has to be about four times the noise. Turn "
                        "it down only if the card is missing edges you can see "
                        "- turning it to 0 lets it measure the noise itself, "
                        "which produces a perfectly normal-looking width for "
                        "every defect.")),
        ParamSpec(name="smooth", type="float", default=1.0, min=0.0, max=5.0,
                  unit="px", advanced=True,
                  label="Smooth each line by",
                  help=("Smooths each measurement line before looking for "
                        "edges, which is what makes edge finding survive "
                        "noise. Turning it up a long way pushes the threshold "
                        "and S-curve edges outward (measured); the gradient "
                        "one does not move.")),
        output_prefix_spec("cd"),
    ]
    reads = ["test"]
    writes: List[str] = []
    features_out = list(ALWAYS) + list(REPORT_CHOICES)

    #: 這張卡一定要影像 —— 它量的是像素上的邊，不是框的尺寸。
    #: （重做之前是 ``False``，因為 bbox 不必看圖，而那正是問題所在。）
    REQUIRE_IMAGE = True

    #: ``ctx.meta`` 上放掃描線幾何的鍵（面板與影像疊圖都讀它）。
    META_KEY = "cd"

    # ---- 影像上的標記（見 Step.overlay_marks）------------------------------ #
    @classmethod
    def overlay_marks(cls, ctx: Any, params: Dict[str, Any]) -> Any:
        """把 ``ctx.meta["cd"]`` 裡的掃描線與邊點交出去。

        線太多會糊成一片，所以最多畫 :data:`MAX_DRAWN_LINES` 條（等距抽樣）——
        但**代表那一條一定在裡面**，它是面板上那張剖面圖畫的同一條。
        """
        notes = (getattr(ctx, "meta", None) or {}).get(cls.META_KEY) or {}
        lines: List[Any] = []
        points: List[Any] = []
        focus = -1
        for prefix in sorted(notes):
            note = notes[prefix] or {}
            segs = list(note.get("scan_lines") or [])
            edges = list(note.get("edges") or [])
            if len(segs) != len(edges):
                continue                   # 對不齊就整組不畫（同 set_overlay）
            pick = int(note.get("median_index", -1))
            for i in _thin_out(len(segs), MAX_DRAWN_LINES, pick):
                if i == pick and focus < 0:
                    focus = len(lines)
                lines.append([tuple(pt) for pt in segs[i]])
                points.append([tuple(pt) for pt in edges[i]])
        return lines, points, focus

    # ---- 宣告 ------------------------------------------------------------- #
    @classmethod
    def feature_names(cls, params: Dict[str, object]) -> List[str]:
        """這組參數下會產出哪幾個基本名（不含任何前綴）。

        ``cd_dev`` 那兩顆**只在填了 ``target_cd`` 時才宣告** —— 這張卡看得到那
        一格，所以它答得出來，而少宣告等於 CSV 少兩個永遠是空的欄。
        """
        want = [m for m in parse_key_list(str(params.get("report", "")))
                if m in REPORT_CHOICES]
        if _target_cd(params) <= 0.0:
            want = [m for m in want if m not in _NEEDS_TARGET]
        return list(ALWAYS) + want

    # ---- 量一個區域 -------------------------------------------------------- #
    def measure(self, ctx: Context, img, p: Dict[str, Any]):
        gray = ensure_gray(np.asarray(img))
        rect = roi_rect_or_none(ctx, self.key, gray, p["roi"])
        x, y, w, h = (int(v) for v in rect)
        block = gray[y:y + h, x:x + w]
        if block.size == 0 or min(block.shape[:2]) < 3:
            ctx.warn("[%s] region '%s' is only %d×%d px on this defect - too "
                     "small to lay a measurement line across. Nothing "
                     "measured for it."
                     % (self.key, p["roi"] or "the image",
                        block.shape[1] if block.ndim > 1 else 0,
                        block.shape[0] if block.ndim > 0 else 0))
            return None

        axis = str(p["axis"])
        if axis == "auto":
            axis, _sx, _sy = algo_edge.choose_axis(block, smooth=p["smooth"])

        res = algo_edge.scan(
            block, axis=axis, criterion=str(p["criterion"]),
            target=str(p["target"]),
            threshold_frac=float(p["threshold_pct"]) / 100.0,
            window=int(p["window"]), smooth=float(p["smooth"]),
            line_step=int(p["line_step"]), line_bin=int(p["line_bin"]),
            min_quality=float(p["min_edge"]))

        used = _target_used(res)
        self._note(ctx, gray, (x, y, w, h), res, p, used)
        self._complain(ctx, res, p)

        n_ok = int(res.widths.size)
        feats: Dict[str, float] = {
            "cd_n": float(n_ok),
            "cd_lines": float(len(res.lines)),
            # 0 = 沿 X 量、90 = 沿 Y 量。**自動選的方向一定要吐出來**（見 ALWAYS）。
            "cd_axis_deg": 0.0 if res.axis == algo_edge.AXIS_X else 90.0,
        }
        if used:
            feats["cd_bright"] = 1.0 if used == "bright" else 0.0
        if n_ok < max(1, int(p["min_lines"])):
            return feats                   # 量不出來的那幾格**不寫**
        feats["cd_edge_score"] = float(np.median(
            [ln.quality for ln in res.lines if not ln.reason]))
        feats.update(self._report(res, p))
        return feats

    # ---- ④ 一串距離收成數字 ------------------------------------------------ #
    def _report(self, res: "algo_edge.ScanResult",
                p: Dict[str, Any]) -> Dict[str, float]:
        widths = res.widths
        table = {
            "cd_median": lambda: float(np.median(widths)),
            "cd_mean": lambda: float(np.mean(widths)),
            "cd_min": lambda: float(np.min(widths)),
            "cd_max": lambda: float(np.max(widths)),
            "cd_range": lambda: float(np.max(widths) - np.min(widths)),
            # **一律報 σ，不報 3σ。** LWR 的業界慣例是 3σ，但同一個名字在不同
            # 地方算出不同的東西是這個 repo 最怕的錯 —— 所以名字說 σ，
            # 「LWR = 3 × 它」寫在 help 裡。
            "cd_std": lambda: float(np.std(widths)),
            # 兩條邊**各自**的 σ。兩邊一起晃 = LER 有、LWR 沒有（載台或對位在
            # 漂）；各自晃才是結構本身粗糙。兩個不同的製程故障，而 bbox 那條路
            # 連問都問不出來。
            "ler_a_std": lambda: float(np.std(res.a_positions)),
            "ler_b_std": lambda: float(np.std(res.b_positions)),
        }
        want = [m for m in parse_key_list(str(p.get("report", "")))
                if m in REPORT_CHOICES]
        out: Dict[str, float] = {}
        for name in want:
            fn = table.get(name)
            if fn is not None:
                out[name] = fn()

        target = _target_cd(p)
        if target > 0:
            here = float(np.median(widths))
            if "cd_dev" in want:
                out["cd_dev"] = here - target
            if "cd_dev_frac" in want:
                out["cd_dev_frac"] = (here - target) / target
        return out

    # ---- 講出哪裡不對 ------------------------------------------------------ #
    def _complain(self, ctx: Context, res: "algo_edge.ScanResult",
                  p: Dict[str, Any]) -> None:
        total = max(1, len(res.lines))
        n_ok = int(res.widths.size)
        where = str(p.get("roi") or "the whole image")
        open_edge = int(res.reasons.get("open_edge", 0))
        if open_edge > total // 2:
            ctx.warn(
                "[%s] the structure runs past the edge of %s on %d of %d "
                "measurement lines, so those lines were not measured (a frame "
                "is not an edge). Widen the region, or point the card at a "
                "region that contains the whole structure."
                % (self.key, where, open_edge, total))
        if int(res.reasons.get("too_many", 0)):
            ctx.warn("[%s] only the first %d measurement lines were used in "
                     "%s; raise 'One line every' to spread them out instead."
                     % (self.key, total, where))
        if n_ok < max(1, int(p["min_lines"])):
            ctx.warn(
                "[%s] only %d of %d measurement lines found a pair of edges in "
                "%s (the card asks for at least %d), so no width is written "
                "for this defect. Most common reasons here: %s. The rest of "
                "the batch is unaffected."
                % (self.key, n_ok, total, where, int(p["min_lines"]),
                   reasons_in_words(res.reasons) or "none recorded"))

    # ---- 給面板與影像疊圖的那一份 ----------------------------------------- #
    def _note(self, ctx: Context, image, rect, res: "algo_edge.ScanResult",
              p: Dict[str, Any], used: str = "") -> None:
        """把「畫得出來所需要的一切」放進 ``ctx.meta["cd"][前綴]``。

        座標**正規化**（跟 `ImageView.set_overlay` 同一套慣例），所以縮放平移與
        換一顆 patch 都不必重算。剖面只存**代表那一條**：每一條都存的話，每顆
        defect 的 meta 會變成幾百 KB（同 `Context._record_change` 只存摘要）。
        """
        h, w = np.asarray(image).shape[:2]
        if not (h and w):
            return
        rx, ry, rw, rh = rect
        along_y = res.axis == algo_edge.AXIS_Y

        def point(along: float, across: float):
            """(沿量測軸, 沿堆疊軸) → 正規化的 (x, y)。"""
            px, py = ((rx + across, ry + along) if along_y
                      else (rx + along, ry + across))
            return round(float(px) / w, 6), round(float(py) / h, 6)

        span = float(rh if along_y else rw)
        lines, marks = [], []
        # ``median_index`` 是代表那一條在**這兩份清單裡**的位置（不是 `res.lines`
        # 裡的）—— 兩份清單只裝量得到的那些，而畫圖的人只拿得到這兩份。
        # 記索引而不是讓下游去比對座標：座標是四捨五入過的。
        median_index = -1
        for ln in res.lines:
            if ln.reason:
                continue
            if ln.index == res.median_line:
                median_index = len(lines)
            lines.append([point(0.0, ln.offset), point(span, ln.offset)])
            marks.append([point(ln.a, ln.offset), point(ln.b, ln.offset)])
        prefix = str(p.get(self.CURRENT_PREFIX, "") or "")
        note: Dict[str, Any] = {
            "axis": res.axis, "criterion": str(p["criterion"]),
            "target": res.target, "target_used": used,
            "region": str(p.get("roi") or ""),
            "stream": str(p.get(self.CURRENT_STREAM, "") or ""),
            "n": int(res.widths.size), "lines": len(res.lines),
            "reasons": dict(res.reasons), "fallbacks": int(res.fallbacks),
            "scan_lines": lines, "edges": marks,
            "median_index": median_index,
            "widths": [round(float(v), 4) for v in res.widths],
            "offsets": [round(float(v), 4) for v in res.offsets],
        }
        if res.median_line >= 0 and res.profile is not None:
            pick = res.lines[res.median_line]
            note["profile"] = {
                "values": [round(float(v), 3) for v in res.profile],
                "a": round(float(pick.a), 4), "b": round(float(pick.b), 4),
                "level": (None if res.level is None
                          else round(float(res.level), 3)),
                "offset": round(float(pick.offset), 4),
            }
        ctx.meta.setdefault(self.META_KEY, {})[prefix] = note


#: 一次最多畫幾條掃描線。128 條疊在一張 128 px 的 patch 上是一片實心的網。
MAX_DRAWN_LINES = 24


def _thin_out(n: int, limit: int, keep: int) -> List[int]:
    """從 ``n`` 條裡等距挑 ``limit`` 條，而且**一定包含 ``keep``**。

    代表那一條非留不可：面板上那張剖面圖畫的就是它，兩邊對不起來的話，使用者
    在影像上找不到剖面圖在講哪一條。
    """
    if n <= 0:
        return []
    if n <= limit:
        return list(range(n))
    step = n / float(limit)
    picked = sorted({min(n - 1, int(i * step)) for i in range(limit)})
    if 0 <= keep < n and keep not in picked:
        picked[len(picked) // 2] = keep
        picked = sorted(set(picked))
    return picked


def _target_used(res: "algo_edge.ScanResult") -> str:
    """整批線裡**多數**量到的是哪一種極性（``""`` = 一條都沒量到）。

    逐條線各自決定極性（``auto`` 時），所以這裡取多數 —— 而少數那些通常是
    量歪的線。這個字最後變成 ``cd_bright``，見 :data:`ALWAYS`。
    """
    votes = {}
    for ln in res.lines:
        if ln.reason:
            continue
        votes[ln.target] = votes.get(ln.target, 0) + 1
    if not votes:
        return ""
    return max(sorted(votes), key=lambda k: votes[k])


def _target_cd(params: Dict[str, object]) -> float:
    try:
        return max(0.0, float(params.get("target_cd", 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0


#: 失敗碼 → 給使用者看的一句話。**每一句都要講得出下一步**。
#:
#: 面板也吃這張表（`ui.inspectors.CdInspector`）—— **只有一份**，不然畫面上
#: 講的原因跟警告訊息裡講的會是兩套說法。
_REASON_WORDS = {
    "open_edge": "the structure ran past the edge of the region",
    "no_pair": "no pair of edges around the middle of the region",
    "flat_profile": "nothing with enough contrast to be an edge",
    "fit_failed": "the edge could not be pinned down",
}


def reasons_in_words(reasons: Dict[str, int]) -> str:
    got = [(n, code) for code, n in (reasons or {}).items()
           if code in _REASON_WORDS]
    got.sort(reverse=True)
    return ", ".join("%s (%d lines)" % (_REASON_WORDS[code], n)
                     for n, code in got[:2])

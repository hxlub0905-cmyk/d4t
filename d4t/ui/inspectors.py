# d4t Studio — 每張卡自己的儀表 (F7-17).
"""選一張卡，右下角就換成**那張卡的儀表**。

為什麼不是一塊通用面板
----------------------
右下角本來是一張「特徵 / 數值」表：`glv_snr 11.170`、`glv_max 255`。
問題不是它佔位子，是**那些數字沒有辦法判讀** —— 11.17 是大還是小？255 是不是
飽和了？一個數字單獨存在，回答不了使用者真正在問的問題。

而使用者在問的問題**每張卡都不一樣**：調 Align 的時候他要知道「搜尋半徑夠不夠
大」，調 Denoise 的時候他要知道「我有沒有把訊號一起磨掉」。同一塊面板放同一種
東西，對兩者都答非所問。

挑選原則
--------
面板不高（約 200 px），所以每張卡**只放一件事**。挑的標準是：

    這張卡最常見的失敗模式是什麼，而那個失敗**在單顆畫面上看不出來**。

看得出來的（影像整個黑掉）不需要面板；看不出來的才需要。Align 就是典型：
每一顆都「有對到啊」，只有把整批的位移畫在一起，才看得出來一半的點貼在搜尋框
的邊上 —— 那些顆根本沒對準，只是被半徑截斷了。

三條約定
--------
1. **依 ``Step.key`` 註冊**（``INSPECTORS``）。沒註冊的卡就用原本的特徵表，
   所以加一張新卡不必動這個檔案 —— 維持「import 就出現」那條規則。
2. **畫的是引擎算出來的那一份**。要嘛來自 ``ctx.meta``（step 卡自己放進去的，
   同 ``roi_profile``），要嘛來自 ``trial_results``（跑完的整批結果）。
   UI 不自己重算一次 —— 不然畫面上的東西跟真的跑出來的有機會不一樣。
3. **沒有資料時說得出「為什麼沒有」**，而不是一片空白。最常見的原因是
   「還沒跑過」，那句話要直接寫在面板上。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF,
)
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..core.steps.align import shift_feature_names as _align_shift_names
from .numbers import format_feature_value
from . import theme
from .theme import TOKENS
# ⚠ 2026-09-24：基底、GLV、CD、Enhance 四塊搬出去了（各自一支 `inspector_*.py`）。
# 這裡把它們轉出口：註冊表要它們，而測試與 `studio` 照舊從 `inspectors` 拿。
from .inspector_base import (  # noqa: F401  轉出口（測試用 inspectors._fmt 等）
    HEADER_GAP, Inspector, _fmt, _short_number, header_boxes, note_header,
    paint_note_header, row_labels,
)
from .inspector_cd import CdInspector
from .inspector_enhance import EnhanceInspector
from .inspector_glv import GlvInspector

__all__ = ["Inspector", "AlignInspector", "EnhanceInspector",
           "H2HInspector",
           "MeasureInspector", "GlvInspector", "InputInspector",
           "CrossInspector", "TemplateInspector",
           "INSPECTORS", "inspector_for"]


class AlignInspector(Inspector):
    """Align：**整批的位移散佈圖**，加上搜尋半徑的方框。

    為什麼是這一張圖
    ----------------
    對位失敗在單顆上看不出來 —— 每一顆都「有對到啊」，因為演算法一定會回一個
    位移。真正的失敗是**位移被搜尋半徑截斷**：真實偏移 12 px、半徑設 8，
    那顆回報 8，而 8 是一個看起來完全正常的數字。

    把整批畫在一起，這件事變成一眼可見：**點貼在方框的邊上**。而且它是可以照做
    的 —— 把 Search radius 調大再跑一次就好。

    資料來自 ``trial_results`` 的 ``align_dx`` / ``align_dy``（引擎算的），
    方框來自這張卡的 ``search_radius`` 參數。UI 不自己算對位。

    ⚠ **三條以上的流時特徵名帶著流名前綴**（F109，DOE 一次餵 N 個 condition
    進來）。要畫哪幾組由**卡片自己**說（``shift_feature_names``），不是 UI 拼
    出來的 —— 拼的那一份會在下一次改前綴規則時安靜地畫出一張空圖，而空圖上
    寫的是「跑一次試跑就看得到」，那句話是假的。
    """

    title = "Alignment"

    #: 距離邊界多近算「貼在邊上」（像素）。次像素對位會落在 7.9 這種值上，
    #: 用嚴格相等會什麼都抓不到。
    _EDGE_TOL = 0.75

    def radius(self) -> float:
        try:
            return float(self.params.get("search_radius", 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def points(self) -> List[Tuple[float, float]]:
        out: List[Tuple[float, float]] = []
        for dx_name, dy_name in _align_shift_names(dict(self.params)):
            xs = self.feature_values(dx_name)
            ys = self.feature_values(dy_name)
            n = min(len(xs), len(ys))
            out.extend(zip(xs[:n], ys[:n]))
        return out

    def at_the_limit(self) -> int:
        """有幾顆的位移貼在搜尋框的邊上（= 很可能根本沒對準）。"""
        r = self.radius()
        if r <= 0:
            return 0
        edge = r - self._EDGE_TOL
        return sum(1 for x, y in self.points()
                   if abs(x) >= edge or abs(y) >= edge)

    def has_data(self) -> bool:
        return bool(self.points())

    def empty_reason(self) -> str:
        return ("Run a trial to see how far every defect had to move to line "
                "up. One defect cannot tell you whether the search radius is "
                "big enough — the whole batch can.")

    def summary(self) -> str:
        pts = self.points()
        if not pts:
            return ""
        r = self.radius()
        far = max(max(abs(x), abs(y)) for x, y in pts)
        text = ("%d defects · largest shift %.1f px · search radius %.0f px"
                % (len(pts), far, r))
        stuck = self.at_the_limit()
        if stuck:
            text += ("  ⚠ %d of them sit on the search limit — those did not "
                     "really line up, they ran out of room. Raise “Search "
                     "radius” and run again." % stuck)
        return text

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        pts = self.points()
        r = max(self.radius(), max((max(abs(x), abs(y)) for x, y in pts),
                                   default=1.0), 1.0)
        span = r * 1.15
        # 正方形，而且**置中** —— dx 與 dy 必須同一個尺度（不然圓形的散佈看起來
        # 像橢圓，使用者會以為某一軸偏得比較多），但靠左擺會讓十字跑到面板左邊。
        side = min(rect.width(), rect.height())
        plot = QRectF(rect.left() + (rect.width() - side) / 2.0,
                      rect.top() + (rect.height() - side) / 2.0, side, side)
        cx, cy = plot.center().x(), plot.center().y()
        scale = (side / 2.0) / span

        def to_px(dx: float, dy: float) -> QPointF:
            # 螢幕的 y 往下為正，位移的 y 往上為正 —— 不翻的話整張圖上下顛倒，
            # 而使用者是拿它跟影像對照的。
            return QPointF(cx + dx * scale, cy - dy * scale)

        # 十字與搜尋框
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0, Qt.DashLine))
        p.drawLine(QPointF(plot.left(), cy), QPointF(plot.right(), cy))
        p.drawLine(QPointF(cx, plot.top()), QPointF(cx, plot.bottom()))

        rad = self.radius()
        if rad > 0:
            box = QRectF(to_px(-rad, rad), to_px(rad, -rad))
            stuck = self.at_the_limit()
            p.setPen(QPen(QColor(TOKENS["danger_text"] if stuck
                                 else TOKENS["accent"]), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawRect(box)
            # 說明放在方框**下面**：上面那條帶子已經有 dy 的軸標，
            # 兩個東西擠在同一列會疊字（實測疊成一團看不懂）。
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(box.left(), box.bottom() + 1, box.width(), 14),
                       Qt.AlignRight | Qt.AlignVCenter,
                       "search radius %.0f px" % rad)

        # 每一顆一個點；貼在邊上的用警示色（那些才是要看的）
        edge = rad - self._EDGE_TOL if rad > 0 else float("inf")
        normal = QColor(TOKENS["accent"])
        normal.setAlpha(150)
        bad = QColor(TOKENS["danger_text"])
        p.setPen(Qt.NoPen)
        for x, y in pts:
            p.setBrush(QBrush(bad if (abs(x) >= edge or abs(y) >= edge)
                              else normal))
            p.drawEllipse(to_px(x, y), 2.6, 2.6)

        # 目前這一顆：空心大圈，看得出「我在哪」
        tx, ty = self.this_value("align_dx"), self.this_value("align_dy")
        if tx is not None and ty is not None:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.6))
            p.drawEllipse(to_px(tx, ty), 5.0, 5.0)

        # 座標軸要標 —— 不標的話這是一張幾何圖形，不是量測結果。
        # 兩個字都畫水平的：旋轉過的字連箭頭一起轉，「dy ↑」會變成「dy ←」。
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(plot.right() - 60, cy + 2, 58, 13),
                   Qt.AlignRight | Qt.AlignVCenter, "dx (px)")
        p.drawText(QRectF(cx + 4, plot.top(), 60, 13),
                   Qt.AlignLeft | Qt.AlignVCenter, "dy (px)")


class CrossInspector(Inspector):
    """`roi_cross`：兩個方向各一條曲線，加上一行「這一顆到底拿到了什麼」。

    為什麼要兩條曲線
    ----------------
    交會處是兩組條紋**共同**定義的，所以失敗也有兩種，而且處置完全不同：
    直的那組沒抓到、還是橫的那組沒抓到。只給一條曲線（或只給一個信心值）的話，
    使用者只知道「失敗了」，卻不知道該去調哪一半 —— 而這張卡有兩組
    sensitivity / pitch。

    畫的資料來自引擎那一次計算（``ctx.meta["crossings"]``），UI 不自己再算。
    """

    title = "Crossings"

    #: 量測尺（F8）：轉發兩條曲線各自的訊號，讓主視窗在影像上標同一段。
    #: 這裡不做判斷，只轉發 —— 儀表不該知道影像檢視器存不存在。
    measure_changed = Signal(str, float, float)
    measure_ended = Signal()
    #: 「用這一種材質」（點了曲線上的一根條紋）→ 主視窗做 ``model.set_param``。
    select_requested = Signal(str, str)
    #: 「把量到的間距填進參數格」→ 主視窗做 ``model.set_param``。
    #: 儀表不碰模型（它連 recipe 長什麼樣都不知道），只說出請求。
    param_requested = Signal(str, object)
    #: 「用**整批** patch 量一次，把結果填進參數」（F8 第七輪的一鍵校正）。
    #: 儀表發不動這件事 —— 它沒有 dataset 也沒有 recipe，只有主視窗有。
    calibrate_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        from .widgets import ProfilePanel, small_button

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # 一鍵校正。放在兩條曲線的上面：它做的事是「把這兩條曲線在整批上
        # 各量一次」，而按鈕要貼著它講的東西。
        self.calibrate_btn = small_button(
            "Measure pitch && width from this lot", shape="wide",
            tip=("Measure the stripe spacing and width on every loaded "
                 "defect and fill the answers into this card. One patch "
                 "measures with a little noise and a small patch often "
                 "cannot even tell that the spacing alternates - the whole "
                 "lot can. Uses the card's current material settings "
                 "(which stripes, how many kinds), so set those first."),
            parent=self)
        self.calibrate_btn.clicked.connect(self.calibrate_requested)
        head = QVBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        # 共用 header（PR-2 2f）：這個面板是 widget 容器（paintEvent 是
        # no-op，兩張 ProfilePanel 自己畫），所以標題是一個 QLabel ——
        # 字照樣走 `note_header`，跟其他面板同一份。
        self.header = QLabel("", self)
        self.header.setObjectName("inspectorHeader")
        head.addWidget(self.header, 0)
        head.addWidget(self.calibrate_btn, 0, Qt.AlignLeft)
        lay.addLayout(head)

        self.across = ProfilePanel(self)
        self.down = ProfilePanel(self)
        for panel in (self.across, self.down):
            panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            panel.measure_changed.connect(self.measure_changed)
            panel.measure_ended.connect(self.measure_ended)
            panel.pitch_requested.connect(self._on_pitch_requested)
            panel.select_requested.connect(self.select_requested)
            lay.addWidget(panel)

    def _on_pitch_requested(self, axis: str, pitch: float,
                            pitch_2: float) -> None:
        """曲線的軸 → 這張卡的參數名。

        ``axis="x"`` 是沿 X 走的曲線，找到的是**直的**條紋 → ``vertical_*``。
        這一步每次都要在腦裡轉一次，所以它只寫在這裡一個地方。
        """
        side = "vertical" if str(axis) == "x" else "horizontal"
        self.param_requested.emit("%s_pitch" % side, float(pitch))
        # 第二格一定要跟著送 —— 只送第一格的話，上一次留下來的交錯值會跟
        # 新量到的單一 pitch 湊成一組沒有人量過的組合。
        self.param_requested.emit("%s_pitch_2" % side, float(pitch_2))

    def region(self) -> str:
        return str(self.params.get("roi_out") or "")

    def record(self) -> Dict[str, Any]:
        crossings = dict(self.meta.get("crossings") or {})
        name = self.region()
        return dict(crossings.get(name) or (
            list(crossings.values())[0] if len(crossings) == 1 else {}))

    def set_context(self, *a, **kw) -> None:
        super().set_context(*a, **kw)
        rec = self.record()
        left, right = note_header(
            {"stream": str(self.params.get("source", "") or ""),
             "n": len(rec.get("boxes") or [])},
            self.region(), unit="box(es)")
        self.header.setText("%s    %s" % (left, right) if rec else "")
        self.header.setVisible(bool(rec))
        self.across.set_data("upright stripes", rec.get("x"))
        self.down.set_data("flat stripes", rec.get("y"))
        # **沒在看的方向不畫。**（F11 Region-2c）那個方向的曲線是一條平的線，
        # 而平的線在這張面板上的意思一直都是「這裡沒東西、去調敏感度」——
        # 完全相反的意思。留著它等於給一個錯的提示，而且佔掉在看的那條
        # 曲線一半的高度。
        from d4t.core.algo.grid import directions_used

        want_x, want_y = directions_used(
            rec.get("directions") or self.params.get("directions") or "both")
        self.across.setVisible(bool(want_x))
        self.down.setVisible(bool(want_y))

    def has_data(self) -> bool:
        return bool(self.record())

    def empty_reason(self) -> str:
        return "Run a trial to see the two curves this card locks onto."

    def summary(self) -> str:
        rec = self.record()
        if not rec:
            return ""
        if not rec.get("ok"):
            # 失敗的時候 reason 就是全部的資訊 —— 它已經講了是哪個方向。
            return "not located — %s" % (rec.get("reason") or "unknown")
        from d4t.core.algo.grid import directions_used

        want = dict(zip(("x", "y"), directions_used(rec.get("directions")
                                                    or "both")))
        bits = ["%d boxes" % len(rec.get("boxes") or [])]
        for tag, key in (("upright", "x"), ("flat", "y")):
            if not want[key]:
                continue          # 沒在看的方向沒有 pitch 可以報
            s = dict(rec.get(key) or {})
            bits.append("%s pitch %.1f px" % (tag, float(s.get("pitch_used", 0.0))))
        filled = sum(int((rec.get(k) or {}).get("filled", 0))
                     for k in ("x", "y") if want[k])
        if filled:
            bits.append("%d stripe(s) filled in from the pitch you gave" % filled)
        if rec.get("reason"):
            bits.append(str(rec["reason"]))
        return " · ".join(bits)

    def paintEvent(self, _e) -> None:  # 內容由子元件畫
        pass


class TemplateInspector(Inspector):
    """`roi_template`：三道閘門各自過了沒，以及這張 patch 對到哪個相位。

    為什麼是這三根柱子
    ------------------
    定位失敗的時候，卡片只講「定不出來，退回整張圖」。但那有三個完全不同的
    原因，而**處置完全不同**：

    * **match 太低** —— 模板不對（或這批圖跟建模板那張差太多）；
    * **certainty 太低** —— 對得上的位置不只一個（週期性太強或門檻太緊）；
    * **structure 太低** —— **這張 patch 上根本沒有東西可比**。這個不是要調
      參數，是本來就該退回整張圖。

    分不出來的話，使用者會一直去調前兩個門檻，而問題其實在第三個。

    整批的那一行（F11 Region-1）
    ----------------------------
    這一顆過不過只是一顆。``roi_template`` 的檔頭一直承諾「換一批資料要不要重算
    模板，是 Studio 在設定時提供的健檢」—— 而那個健檢本來不存在（F10 那個形狀：
    文字說得出來、引擎做不到）。它現在就在這裡，而且**不必再跑一次比對**：
    每一顆都已經吐了 ``match_score`` / ``match_margin`` / ``match_structure``，
    整批的判讀是那三串數字的函式（``algo/template.judge_template``）。
    """

    title = "Match"

    _GATES = (("match", "score", "min_score", 1.0),
              ("certainty", "margin", "min_margin", 1.0),
              ("structure", "structure", "min_structure", 40.0))

    def record(self) -> Dict[str, Any]:
        """這張卡的比對結果（三道閘門的值對每個區域都一樣，取第一個就好）。

        一張卡現在可以標好幾個區域（F11 Region-1），而**比對是一張卡一次**——
        分數、確定度、結構都是 patch 對模板的性質，跟哪個區域無關。所以這裡取
        這張卡自己的第一個區域，不是「唯一那個」。
        """
        from d4t.core.pipeline.cellrois import region_names

        templates = dict(self.meta.get("templates") or {})
        for name in region_names(self.params.get("regions", "")):
            if name in templates:
                return dict(templates[name])
        return dict(list(templates.values())[0] if len(templates) == 1 else {})

    def has_data(self) -> bool:
        return bool(self.record())

    def empty_reason(self) -> str:
        if not str(self.params.get("template") or "").strip():
            return ("No template yet — build one from a full-size image, then "
                    "this panel shows why each defect did or did not match.")
        if not str(self.params.get("regions") or "").strip():
            return ("No regions drawn on the cell yet — open “Edit template & "
                    "regions…” and draw at least one.")
        return "Select a defect to see how well it matched the template."

    def gates(self) -> List[Tuple[str, float, float, bool]]:
        """``(名稱, 量到的值, 門檻, 過了沒)``。"""
        rec = self.record()
        out = []
        for label, key, param, _full in self._GATES:
            got = float(rec.get(key, 0.0) or 0.0)
            need = float(self.params.get(param, 0.0) or 0.0)
            out.append((label, got, need, got >= need))
        return out

    def failing(self) -> List[str]:
        return [g[0] for g in self.gates() if not g[3]]

    def health(self):
        """整批的判讀 —— 「這個模板還能不能用」（``algo.template.judge_template``）。"""
        from d4t.core.algo.template import judge_template

        def vals(name: str) -> List[float]:
            return self.feature_values(self.prefixed(name))

        return judge_template(
            vals("match_score"), vals("match_margin"), vals("match_structure"),
            float(self.params.get("min_score", 0.0) or 0.0),
            float(self.params.get("min_margin", 0.0) or 0.0),
            float(self.params.get("min_structure", 0.0) or 0.0))

    def prefixed(self, name: str) -> str:
        """特徵名加上這張卡的 ``output_prefix``（沒有就原樣）。"""
        pre = str(self.params.get("output_prefix", "") or "").strip()
        return "%s_%s" % (pre, name) if pre else name

    def summary(self) -> str:
        rec = self.record()
        if not rec:
            return ""
        batch = self.health()
        tail = ("  ·  %s" % batch.message) if batch.checked > 1 else ""
        if rec.get("ok"):
            return ("matched at phase %d,%d · %s%s"
                    % (int(rec.get("phase_x", 0)), int(rec.get("phase_y", 0)),
                       " · ".join("%s %.2f" % (g[0], g[1])
                                  for g in self.gates()), tail))
        bad = self.failing()
        why = {
            "structure": ("this patch has nothing to match — it sits inside "
                          "one material. That is not a setting to fix; the "
                          "region falls back to the whole image, which is the "
                          "right answer here."),
            "certainty": ("more than one position fits equally well. Lower "
                          "“Minimum certainty” only if you can live with a "
                          "coin flip."),
            "match": ("the patch does not look like the template. Check the "
                      "template was built from this layer."),
        }
        first = bad[0] if bad else "match"
        return ("could not place the region — %s: %s%s"
                % (first, why[first], tail))

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        gates = self.gates()
        row_h = min(30.0, rect.height() / (len(gates) + 1))
        for i, ((label, got, need, ok), (_l, _k, _p, full)) in enumerate(
                zip(gates, self._GATES)):
            band = QRectF(rect.left(), rect.top() + i * row_h,
                          rect.width(), row_h - 4)
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(band.left(), band.top(), 76, band.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, label)

            bar = QRectF(band.left() + 80, band.top() + band.height() / 2 - 5,
                         max(20.0, band.width() - 150), 10)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(TOKENS["hover_warm_strong"])))
            p.drawRoundedRect(bar, 3, 3)
            frac = max(0.0, min(1.0, got / full if full else 0.0))
            p.setBrush(QBrush(QColor(TOKENS["success"] if ok
                                     else TOKENS["danger_text"])))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(),
                                     max(2.0, bar.width() * frac),
                                     bar.height()), 3, 3)
            # 門檻線：沒有它，柱子的長度沒有意義（多長才算夠？）
            nx = bar.left() + bar.width() * max(0.0, min(1.0, need / full
                                                         if full else 0.0))
            p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.4))
            p.drawLine(QPointF(nx, bar.top() - 3), QPointF(nx, bar.bottom() + 3))

            p.setPen(QColor(TOKENS["text_primary"]))
            p.drawText(QRectF(bar.right() + 8, band.top(), 62, band.height()),
                       Qt.AlignRight | Qt.AlignVCenter, "%.2f" % got)

        rec = self.record()
        batch = self.health()
        foot = ("cell %d × %d px · phase %d,%d · line = the threshold"
                % (int(rec.get("cell_w", 0)), int(rec.get("cell_h", 0)),
                   int(rec.get("phase_x", 0)), int(rec.get("phase_y", 0))))
        sw, sh = int(rec.get("self_w", 0)), int(rec.get("self_h", 0))
        cw, ch = int(rec.get("cell_w", 0)), int(rec.get("cell_h", 0))
        if sw and sh and (sw, sh) != (cw, ch):
            foot += " · repeats every %d × %d px inside the cell" % (sw, sh)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(rect.left(), rect.bottom() - 14, rect.width(), 14),
                   Qt.AlignLeft | Qt.AlignVCenter, foot)

        if batch.checked > 1:
            # 整批的成績自己一行，而且**顏色講出處置**：模板要重建是紅的，
            # 「這批 patch 本來就沒結構」不是錯，用一般的灰。
            col = {"ok": TOKENS["success"], "stale": TOKENS["danger_text"],
                   "too-tight": TOKENS["warning"]}.get(
                       batch.verdict, TOKENS["text_secondary"])
            p.setPen(QColor(col))
            p.drawText(QRectF(rect.left(), rect.bottom() - 28, rect.width(), 14),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "%d / %d located · %s" % (batch.located, batch.checked,
                                                 batch.verdict))


class MeasureInspector(Inspector):
    """量測卡共用：**這張卡自己產出的每個數字，整批長什麼樣、這一顆站在哪。**

    為什麼是這一張圖
    ----------------
    `glv_snr 11.170` 單獨存在回答不了任何問題。而調一張量測卡的時候，
    要問的其實是：**我把參數設成這樣，量出來的東西分不分得開？**

    分布回答得了：擠成一根柱子 = 這個特徵對這批資料沒有鑑別力（不管門檻設哪裡
    都一樣）；分成兩坨 = 有東西可以分。而「這一顆在哪裡」讓使用者把畫面上看到
    的缺陷跟數字連起來 —— 那是他唯一能校準自己直覺的方式。

    只列**這張卡的**特徵（`Step.resolve_features`，含 output_prefix），
    不是整份 feature 表 —— 那是 ADC 的事，不是這張卡的事。
    """

    title = "Spread"

    #: 一次畫幾條。面板不高，六條以上每一條就只剩幾個畫素高。
    MAX_ROWS = 5
    BINS = 28

    def rows(self) -> List[str]:
        names = [n for n in self.feature_names if self.feature_values(n)]
        return names[:self.MAX_ROWS]

    def has_data(self) -> bool:
        return bool(self.rows())

    def empty_reason(self) -> str:
        return ("Run a trial to see how this card's numbers are spread across "
                "the batch. One value on its own cannot tell you whether it "
                "separates anything.")

    def percentile_of(self, name: str) -> Optional[float]:
        """這一顆在整批裡的百分位（0–100）。"""
        vals = self.feature_values(name)
        here = self.this_value(name)
        if not vals or here is None:
            return None
        below = sum(1 for v in vals if v < here)
        return 100.0 * below / float(len(vals))

    def summary(self) -> str:
        names = self.rows()
        if not names:
            return ""
        flat = [n for n in names if self._is_flat(n)]
        text = "%d values over %d defects" % (len(names),
                                              len(self.feature_values(names[0])))
        here = [n for n in names if self.percentile_of(n) is not None
                and self.percentile_of(n) >= 95.0]
        if here:
            text += ("  ·  this defect is in the top 5%% for %s"
                     % ", ".join(here))
        if flat:
            text += ("  ⚠ %s barely varies across the batch — no threshold on "
                     "it will separate anything." % ", ".join(flat))
        return text

    def _is_flat(self, name: str) -> bool:
        """整批幾乎同一個值 = 這個特徵對這批資料沒有鑑別力。"""
        vals = self.feature_values(name)
        if len(vals) < 4:
            return False
        lo, hi = min(vals), max(vals)
        if hi - lo <= 0:
            return True
        mid = (abs(lo) + abs(hi)) / 2.0 or 1.0
        return (hi - lo) / mid < 0.01

    #: 圖例那一條的高度；放不下就不畫（面板可以很矮）。
    LEGEND_H = 15
    #: 一排要有這麼高，兩端的刻度才擠得下。
    AXIS_MIN_ROW_H = 34
    AXIS_H = 12

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        names = self.rows()
        if not names:
            # 子類可能因為**別的理由**說「有資料」（`PairInspector` 手上有配對
            # 資訊，但整批的數字要跑一批才有）。那時候這裡一列都畫不出來，而
            # 底下那一行除法會是 ZeroDivisionError —— 2026-08-20 使用者遇到的
            # 就是它，而症狀是「圖載不出來」。
            self._say_empty(p, rect)
            return
        # 共用 header（PR-2 2f）：來源流 · n（這裡的 n 是整批的顆數 ——
        # Spread 的資料本來就是 batch）。
        src = str(self.params.get("source", "") or "").split(",")[0].strip()
        head_h = paint_note_header(
            p, rect, {"stream": src,
                      "n": len(self.feature_values(names[0]))},
            colour=QColor(TOKENS["text_primary"]), unit="defect(s)")
        rect = QRectF(rect.left(), rect.top() + head_h + 1, rect.width(),
                      rect.height() - head_h - 1)
        # 圖例畫一次就好（每一排都畫是噪音），而且**放得下才畫** ——
        # 面板可以被拖到很矮，那時候長條本身比圖例重要。
        body = rect
        with_legend = rect.height() >= len(names) * 26 + self.LEGEND_H
        if with_legend:
            body = QRectF(rect.left(), rect.top(), rect.width(),
                          rect.height() - self.LEGEND_H)
            self._paint_legend(p, QRectF(rect.left(), body.bottom(),
                                         rect.width(), self.LEGEND_H))

        row_h = body.height() / float(len(names))
        for i, name in enumerate(names):
            band = QRectF(body.left(), body.top() + i * row_h,
                          body.width(), row_h - 2)
            self._paint_row(p, band, name)

    def _paint_legend(self, p: QPainter, box: QRectF) -> None:
        """紅線是什麼、藍柱是什麼 —— **畫**出來，不要只用名詞描述。

        跟 :class:`EnhanceInspector` 的圖例同一種語言（F7-21）。以前這個面板
        什麼都沒有：三排長條、右邊一個數字、中間一條紅線，而畫面上沒有一個地方
        說得出橫軸是什麼、紅線是什麼、右邊那個數字又是誰的。
        """
        y = box.center().y()
        x = box.left()
        p.setPen(QPen(QColor(TOKENS["danger_text"]), 1.6))
        p.drawLine(QPointF(x, y - 5), QPointF(x, y + 5))
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(x + 7, box.top(), 150, box.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, "this defect")
        x += 84
        col = QColor(TOKENS["accent"])
        col.setAlpha(150)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        p.drawRect(QRectF(x, y - 4, 11, 8))
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(x + 15, box.top(), 200, box.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, "the batch")
        # 右邊那一欄的數字是**這一顆的值**，不是整批的最大值 —— 那是看這個面板
        # 的人第一個會猜錯的東西。窄的時候不畫：疊在「the batch」上面比不寫更糟。
        if box.width() > 340:
            p.drawText(box, Qt.AlignRight | Qt.AlignVCenter,
                       "value = this defect")

    def _paint_row(self, p: QPainter, band: QRectF, name: str) -> None:
        vals = self.feature_values(name)
        lo, hi = min(vals), max(vals)
        if hi <= lo:
            hi = lo + 1.0

        label = QRectF(band.left(), band.top(), 116, band.height())
        p.setPen(QColor(TOKENS["text_secondary"]))
        fm = p.fontMetrics()
        p.drawText(label, Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(name, Qt.ElideRight, int(label.width()) - 4))

        value = QRectF(band.right() - 74, band.top(), 74, band.height())
        here = self.this_value(name)
        p.setPen(QColor(TOKENS["text_primary"]))
        p.drawText(value, Qt.AlignRight | Qt.AlignVCenter,
                   "—" if here is None else _fmt(here))

        # 橫軸的兩端。**每一排的單位都不一樣**（``glv_mean`` 與 ``area_px`` 不是
        # 同一把尺），所以刻度要跟著那一排走，不能像 Enhance 那樣共用一句
        # 「0 → 255」。沒有這兩個數字，長條的位置只說得出「比較左邊」，
        # 說不出「比較左邊是多少」。
        with_axis = band.height() >= self.AXIS_MIN_ROW_H
        axis_h = self.AXIS_H if with_axis else 0.0
        plot = QRectF(label.right() + 4, band.top() + 2,
                      value.left() - label.right() - 10,
                      max(6.0, band.height() - 6 - axis_h))
        if plot.width() < 20:
            return
        if with_axis:
            axis = QRectF(plot.left(), plot.bottom() + 1, plot.width(), axis_h)
            p.setPen(QColor(TOKENS["text_hint"]))
            p.drawText(axis, Qt.AlignLeft | Qt.AlignVCenter, _fmt(lo))
            p.drawText(axis, Qt.AlignRight | Qt.AlignVCenter, _fmt(hi))

        counts = [0] * self.BINS
        for v in vals:
            k = int((v - lo) / (hi - lo) * (self.BINS - 1))
            counts[max(0, min(self.BINS - 1, k))] += 1
        top = max(counts) or 1
        bw = plot.width() / float(self.BINS)
        col = QColor(TOKENS["accent"])
        col.setAlpha(150)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        for k, c in enumerate(counts):
            h = (c / float(top)) * plot.height()
            p.drawRect(QRectF(plot.left() + k * bw, plot.bottom() - h,
                              max(1.0, bw - 0.5), h))

        # 這一顆在哪裡 —— 沒有這條線，分布只是一張統計圖，跟眼前這顆缺陷無關。
        #
        # 會落在範圍外是**正常的**：改了參數之後預覽會立刻重算，而整批還是上一次
        # 跑的。那時候把線畫到圖外（會蓋到旁邊的文字）比不畫更糟，所以夾回邊界
        # 並且畫成箭頭 —— 「在這個方向的外面」也是一個答案。
        if here is not None:
            frac = (here - lo) / (hi - lo)
            outside = frac < 0.0 or frac > 1.0
            x = plot.left() + min(1.0, max(0.0, frac)) * plot.width()
            p.setPen(QPen(QColor(TOKENS["danger_text"]), 1.6))
            p.drawLine(QPointF(x, plot.top() - 2), QPointF(x, plot.bottom() + 2))
            if outside:
                p.setBrush(QBrush(QColor(TOKENS["danger_text"])))
                p.setPen(Qt.NoPen)
                tip = -5.0 if frac < 0.0 else 5.0
                mid = (plot.top() + plot.bottom()) / 2.0
                # QPolygonF，不是三個散的 QPointF —— 後者在 PySide6 綁到別的
                # overload，直接 segfault（不是例外，是整個行程掛掉）。
                p.drawPolygon(QPolygonF([QPointF(x + tip, mid),
                                         QPointF(x, mid - 4.0),
                                         QPointF(x, mid + 4.0)]))


class InputInspector(Inspector):
    """Patch：**哪一頁變成哪一條流**，以及每一頁載進來長什麼樣。

    頁序已經確認（2026-07-30）
    --------------------------
    「每顆 defect 的第一張是 test、第二張是 ref」曾經是這個專案第一條待廠內
    驗證的假設；使用者已經確認就是這個順序，所以它現在是**約定**，不是猜測。

    面板留著，因為約定成立不代表每一份檔案都照著走 —— 三頁以上、單頁、或
    ``channel_order`` 被改過的資料集，配對關係仍然只有這裡看得到。而它要回答的
    問題也換了一個：**這兩張圖比得起來嗎**（整體亮度差很多就得先正規化）。

    資料來自 Load 卡放進 ``ctx.meta['input']`` 的那一份 —— 也就是引擎**實際載
    進來的東西**，不是 UI 從檔名猜的。
    """

    title = "Input"

    def info(self) -> Dict[str, Any]:
        return dict(self.meta.get("input") or {})

    def pages(self) -> List[Dict[str, Any]]:
        return [dict(d) for d in (self.info().get("pages") or [])]

    def has_data(self) -> bool:
        return bool(self.pages())

    def empty_reason(self) -> str:
        return ("Select a defect to see which page of the TIFF became which "
                "image stream.")

    def summary(self) -> str:
        pages = self.pages()
        if not pages:
            return ""
        info = self.info()
        bits = ["defect %s" % (info.get("defect_id") or "?")]
        die = info.get("die") or []
        if len(die) == 2:
            bits.append("die %d,%d" % (int(die[0]), int(die[1])))
        if info.get("nm_per_px"):
            bits.append("%.2f nm/px" % float(info["nm_per_px"]))
        else:
            # 量測一律 pixel；換算是 Export 那一刻的事，而且由使用者填。
            # （以前這裡說「CD 的 nm 值會是 0」—— 那個 0 已經不存在了。）
            bits.append("measured in pixels — set nm/px when you export")
        return " · ".join(bits)

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        pages = self.pages()
        head = QRectF(rect.left(), rect.top(), rect.width(), 15)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(head, Qt.AlignLeft | Qt.AlignVCenter,
                   "page → stream        size        mean grey")

        row_h = min(20.0, max(14.0, (rect.height() - 18) / max(1, len(pages))))
        means = [d.get("mean") for d in pages if d.get("mean") is not None]
        spread = (max(means) - min(means)) if len(means) > 1 else 0.0
        for i, d in enumerate(pages):
            y = rect.top() + 18 + i * row_h
            band = QRectF(rect.left(), y, rect.width(), row_h)
            page = d.get("page")
            p.setPen(QColor(TOKENS["text_primary"]))
            p.drawText(QRectF(band.left(), band.top(), 150, band.height()),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "%s → %s" % ("page %d" % page if page is not None
                                    else "file", d.get("channel", "?")))
            shape = d.get("shape") or []
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(band.left() + 150, band.top(), 90, band.height()),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "%d × %d" % (shape[1], shape[0]) if len(shape) == 2 else "—")
            mean = d.get("mean")
            p.drawText(QRectF(band.left() + 240, band.top(), 70, band.height()),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "—" if mean is None else "%.1f" % mean)

        if spread >= 8.0:
            # 兩張本來就該長得幾乎一樣（同一個位置、同一次掃描）。差很多不會讓
            # 對位掛掉，但會讓相減的殘差整片偏掉 —— 而那看起來像訊號。
            # 頁序已經確認，所以這裡講的是處置（先正規化），不是叫人去懷疑配對。
            p.setPen(QColor(TOKENS["warning"]))
            p.drawText(QRectF(rect.left(), rect.bottom() - 14, rect.width(), 14),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "mean grey differs by %.0f between pages — normalise "
                       "before comparing" % spread)


#: step key -> 儀表。沒列在這裡的卡用原本的特徵表（見模組說明的約定 1）。
#:
#: Enhance 的卡共用同一個儀表：它們做的事不同，但**要回答的問題是同一個**
#: （我把資訊弄掉了嗎）。F7-20 把九張併成四張，所以這裡只剩四個 key ——
#: 少的那五個不是被拿掉，是變成 ``normalize`` / ``tone`` 的一個下拉選項。
class GdsInspector(Inspector):
    """`roi_reference`（``layout layers`` 那一支）：**這一顆對到了哪幾層**、各幾塊、多大。

    為什麼是一張表而不是「label map 的上色預覽」
    ------------------------------------------
    第一版打算畫一張上色的 label（label map 的像素值是 1、2、3，在一般檢視器裡
    **幾乎全黑** —— 那正是 GLAS 另外產一張 ``_label_view.png`` 的原因）。
    但**形狀已經看得到了**：這張卡吐的每一層都是一個具名區域，而預覽影像上的
    疊框本來就一個區域一個顏色、還帶圖例（2026-08-18 的疊框分色）——
    而且是畫在**真的那張 SEM 影像**上，比另外看一張示意圖有用。

    所以這裡回答的是那張圖答不出來的三件事：**哪一層根本沒落在這一顆上**
    （框看不到 = 可能是沒有，也可能是被別的層蓋掉）、**各幾塊幾個框**
    （切碎的程度）、以及**有沒有砍到上限**。

    顏色跟疊框、模板編輯器**同一組**（`theme.REGION_COLORS`），而且順序一樣 ——
    表上第二列的顏色就是畫面上第二個區域的顏色。

    畫的是**引擎算的那一份**（`ctx.meta["gds_layers"]`），UI 不自己再拆一次 ——
    不然「畫面上的層」與「真的量下去的層」會不一樣，而那種 bug 極難發現。
    """

    title = "Layout layers"

    def record(self) -> Dict[str, Any]:
        by_source = dict(self.meta.get("gds_layers") or {})
        key = str(self.params.get("source") or "")
        if key in by_source:
            return dict(by_source[key])
        return dict(list(by_source.values())[0] if len(by_source) == 1 else {})

    def has_data(self) -> bool:
        return bool(self.record())

    def empty_reason(self) -> str:
        return ("Run a trial to see which layers landed on this defect. No "
                "layout labels? Use “Open GDS export…”.")

    def summary(self) -> str:
        rec = self.record()
        if not rec:
            return ""
        got = [e for e in rec.get("layers") or () if e.get("boxes")]
        bits = ["%d of %d layer(s) on this defect"
                % (len(got), len(rec.get("layers") or ()))]
        total = sum(int(e.get("boxes") or 0) for e in rec.get("layers") or ())
        bits.append("%d boxes" % total)
        if any(e.get("clipped") for e in rec.get("layers") or ()):
            bits.append("hit the box limit — some boxes were left out")
        # **在圖裡、但沒有名字的 id** —— 那是「匯出多了一層而 recipe 沒跟上」，
        # 而它安靜地少一個區域。
        named = {int(e.get("id")) for e in rec.get("layers") or ()}
        extra = [i for i in rec.get("ids_in_image") or () if int(i) not in named]
        if extra:
            bits.append("layer(s) %s are in the label map but have no name"
                        % ", ".join(str(i) for i in extra))
        return " · ".join(bits)

    def paintEvent(self, _e) -> None:  # Qt hook
        from .theme import region_hex

        rec = self.record()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(TOKENS["bg_panel"]))
        entries = list(rec.get("layers") or ())
        if not entries:
            p.end()
            return

        f = QFont(p.font())
        f.setPixelSize(theme.font_px("font_body"))
        p.setFont(f)
        fm = QFontMetricsF(f)
        line = fm.height() + 6.0
        pad, sw = 8.0, 10.0
        cols = ("layer", "boxes", "pieces", "area px")
        y = 4.0
        p.setPen(QColor(TOKENS["text_secondary"]))
        for i, head in enumerate(cols):
            p.drawText(QRectF(pad + (0 if not i else 150 + (i - 1) * 62), y,
                              150 if not i else 60, line),
                       Qt.AlignLeft | Qt.AlignVCenter, head)
        y += line
        for i, e in enumerate(entries):
            colour = QColor(region_hex(i))
            got = int(e.get("boxes") or 0)
            if not got:
                colour.setAlpha(90)
            p.setPen(Qt.NoPen)
            p.setBrush(colour)
            p.drawRect(QRectF(pad, y + line / 2 - sw / 2, sw, sw))
            p.setPen(QColor(TOKENS["text_primary"] if got
                            else TOKENS["text_disabled"]))
            p.drawText(QRectF(pad + sw + 6, y, 132, line),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       "%s  (id %s)" % (e.get("name"), e.get("id")))
            for k, value in enumerate((got, int(e.get("pieces") or 0),
                                       int(e.get("area_px") or 0))):
                p.drawText(QRectF(150 + k * 62, y, 60, line),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           "—" if not got else str(value))
            if e.get("clipped"):
                p.setPen(QColor(TOKENS["danger_text"]))
                p.drawText(QRectF(150 + 3 * 62, y, 90, line),
                           Qt.AlignLeft | Qt.AlignVCenter, "clipped")
            y += line
        p.end()


class PairInspector(MeasureInspector):
    """`pair_source`：**這一顆對到了第二份裡的哪一顆**，以及整批配得怎麼樣。

    為什麼不是只有分布
    ------------------
    分布（`pair_found` / `match_dist_nm` 整批長什麼樣）是 `MeasureInspector` 已經在
    畫的東西，而它正是調容差要看的圖 —— 距離擠在左邊一坨 = 容差可以收；拖出一
    條長尾 = 那條尾巴配到的是鄰居。

    但有兩件事分布答不出來，而它們正是這張卡存在的理由：

    * **對到的是哪一顆**（第二份裡的 DEFECTID）—— 使用者要拿它回去翻原始資料；
    * **帶過來的字串欄位**（`meta["pair_fields"]`）—— 那些欄位**不在特徵表裡**
      （feature 是數字的地盤），沒有這裡的話它們哪裡都看不到。
    """

    title = "Match"

    def match(self) -> Dict[str, Any]:
        return dict(self.meta.get("pair_match") or {})

    def empty_reason(self) -> str:
        # **配到了**跟**還沒配到**是兩句不同的話。這一格在只跑過一顆（預覽）的
        # 時候是常態：配對資訊有了，整批的分布還沒有。
        if self.match():
            return ("Paired — run a trial to see how the match distance and "
                    "the score are spread across the batch. One value on its "
                    "own cannot tell you whether the tolerance is right.")
        return ("Run a trial to see which defect this one pairs with. No "
                "second lot yet? Use “Open data…” on this card.")

    def summary(self) -> str:
        rec = self.match()
        bits: List[str] = []
        if rec:
            if int(rec.get("index", -1)) >= 0:
                bits.append("paired with %s in '%s'"
                            % (rec.get("defect_id") or "?", rec.get("source")))
                dist = rec.get("dist_nm")
                if dist is not None and not math.isnan(float(dist)):
                    bits.append("%.0f nm away" % float(dist))
            else:
                bits.append("no match in '%s' — recorded as pair_found = 0"
                            % rec.get("source"))
        carried = dict(self.meta.get("pair_fields") or {})
        if carried:
            bits.append(", ".join("%s=%s" % (k, carried[k])
                                  for k in sorted(carried)))
        spread = super().summary()
        if spread:
            bits.append(spread)
        return "  ·  ".join(bits)

    def has_data(self) -> bool:
        return bool(self.match()) or super().has_data()



class WriteBackInspector(Inspector):
    """Write KLARF：**這一次寫下去會改到什麼**（F16 Stage 5c）。

    M5 那條規則是硬性的：**寫回前一定先預覽變更**。Export 精靈的做法是把
    「寫出」鈕鎖住，直到使用者按過「預覽變更」。精靈拿掉之後那條規則不能跟著
    消失 —— 而它其實不需要一顆鈕：機制本來就在 core
    （``klarf_out.plan_writeback`` 的**乾跑**，一個位元組都不寫），
    所以它可以是**這張卡的儀表**。

    這樣比精靈**更早**：選到那張卡就看得到，不必等按下 Export。

    ⚠ **只有 `inplace` 會動到原檔**，而那是唯一不可逆的一種。面板上那句話因此
    分三種寫（`annotate` / `topn` 寫的是新檔）—— 把三種都講成「危險」的話，
    使用者很快就不讀它了。

    數字從哪來：``trial_results``（上一次跑的那一批）。**還沒跑過就講那句話**，
    不要畫一個看起來像答案的空面板。
    """

    title = "Write-back"

    def mode(self) -> str:
        return str(self.params.get("mode", "annotate") or "annotate").strip()

    def path(self) -> str:
        return str(self.params.get("path", "") or "").strip()

    def has_data(self) -> bool:
        return bool(self.batch)

    def empty_reason(self) -> str:
        if not self.path():
            return ("Put the full path of the KLARF file into “Write to”, "
                    "then run the batch to see what would change.")
        return ("Run the batch to see how many rows this would change "
                "before anything is written.")

    def plan(self) -> Dict[str, Any]:
        """乾跑一次（**不寫任何東西**），回 ``{changed, out, note}``。

        算不出來就回空的 —— 這是一句提示，不准擋路（同 `paintEvent` 的鐵則）。
        """
        rows = [dict(r) for r in (self.batch or [])]
        if not rows:
            return {}
        doc = self.meta.get("_klarf_doc")
        if doc is None:
            # 儀表拿不到 KlarfDoc（它不該自己去讀檔）。退而求其次：講得出
            # 「有幾顆會被寫」，那已經是使用者要的量級。
            ok = sum(1 for r in rows if r.get("ok"))
            return {"changed": ok, "out": len(rows), "note": "estimated"}
        try:
            from d4t.core.export.klarf_out import plan_writeback

            plan = plan_writeback(doc, rows, self.mode())
            return {"changed": int(getattr(plan, "n_rows_changed", 0)),
                    "out": int(getattr(plan, "n_rows_out", 0)), "note": ""}
        except Exception:  # 提示不准擋路
            ok = sum(1 for r in rows if r.get("ok"))
            return {"changed": ok, "out": len(rows), "note": "estimated"}

    def summary(self) -> str:
        info = self.plan()
        if not info:
            return ""
        mode = self.mode()
        what = ("edits the original file" if mode == "inplace"
                else "writes a new file")
        return ("%s — %s; %d of %d row(s) would change%s"
                % (mode, what, info.get("changed", 0), info.get("out", 0),
                   " (estimated)" if info.get("note") else ""))

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        info = self.plan()
        mode = self.mode()
        lines = [("Mode", mode)]
        if mode == "inplace":
            lines.append(("Original file",
                          "EDITED IN PLACE - cannot be undone"))
        else:
            lines.append(("Original", "untouched (a new file is written)"))
        lines.append(("Rows changed",
                      "%d of %d%s" % (info.get("changed", 0),
                                      info.get("out", 0),
                                      " (estimated)" if info.get("note") else "")))
        lines.append(("Write to", self.path() or "(not set yet)"))

        row_h = max(16.0, rect.height() / max(1, len(lines) + 1))
        y = rect.top()
        for label, value in lines:
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(rect.left(), y, rect.width() * 0.32, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, label)
            danger = (label == "Original file")
            p.setPen(QColor(TOKENS["danger_text"] if danger
                            else TOKENS["text_primary"]))
            p.drawText(QRectF(rect.left() + rect.width() * 0.34, y,
                              rect.width() * 0.66, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, str(value))
            y += row_h


class H2HInspector(MeasureInspector):
    """`align_to`（H2H）：**對到哪、歪了多少、這個位置可不可信**。

    為什麼不只是分布（F33，2026-08-26）
    -----------------------------------
    分布（`MeasureInspector` 已經在畫的那五條）是調參數要看的東西 —— 但這張卡
    的產物是一個**位置**，而位置的三個問題分布答不出來：

    * **對到哪** —— 大圖上的座標，使用者要拿它跟畫面上的框對起來；
    * **歪了多少** —— `align_off_*`，也就是這一顆的 stage 偏移。整批取中位數
      填回 `expect_dx_px` 就能把搜尋框縮小（F15 §14.3 的調校迴圈）；
    * **可不可信** —— `align_peak_ratio`。⚠ **`ncc_score` 一個不夠**：陣列區
      裡實測 NCC 0.98 而位置每一顆都錯，因為第二名跟第一名一樣好
      （`docs/history/plans/F33-ebi-characterization.md` §8.5）。所以這一行**兩個數字
      一起講**，不讓使用者只看到漂亮的那一個。

    影像上的框與十字走的是另一條路（`AlignToStep.overlay_marks`）——
    **文字說多少、圖上指哪裡**，兩邊是同一組數字的兩種說法。
    """

    title = "Match"

    def note(self) -> Dict[str, Any]:
        return dict(self.meta.get("align_to") or {})

    def empty_reason(self) -> str:
        # **對到了**跟**還沒跑**是兩句不同的話（同 `PairInspector`）。
        if self.note():
            return ("Matched - run a trial to see how the match score and the "
                    "stage offset are spread across the batch. One value on "
                    "its own cannot tell you whether it is a good match.")
        return ("Run a trial to see where the small image sits inside the big "
                "one. Nothing here yet? Check that both streams are wired up.")

    def summary(self) -> str:
        note = self.note()
        bits: List[str] = []
        if note:
            try:
                bits.append("matched at (%d, %d)"
                            % (int(round(float(note["x"]))),
                               int(round(float(note["y"])))))
            except (KeyError, TypeError, ValueError):
                pass
        ox = self.this_value("align_off_x_px")
        oy = self.this_value("align_off_y_px")
        if ox is not None and oy is not None:
            # 「歪了多少」是這張卡最實用的一個數字：整批的中位數就填回
            # `expect_dx_px`，搜尋框因此縮得下來。
            bits.append("off by (%+.0f, %+.0f) px" % (ox, oy))
        score = self.this_value("ncc_score")
        ratio = self.this_value("align_peak_ratio")
        if score is not None:
            # **兩個一起講**：陣列區裡 NCC 漂亮而位置是猜的（見類別說明）。
            if ratio is not None and ratio >= 0.9:
                bits.append("score %.2f but the runner-up scores %.0f%% as "
                            "well - this position is a guess (repeating "
                            "pattern)" % (score, 100.0 * ratio))
            elif ratio is not None:
                bits.append("score %.2f (runner-up %.0f%%)"
                            % (score, 100.0 * ratio))
            else:
                bits.append("score %.2f" % score)
        spread = super().summary()
        if spread:
            bits.append(spread)
        return "  ·  ".join(bits)




class SubtractInspector(Inspector):
    """Compare：**差影像是什麼做的**（PR-2 2d）。

    `diff` 是 D2D 的心臟，而它以前一格儀表都沒有。三樣東西，全部來自卡片
    自己 note 的那一份（`arith._note_diagnostics`，預覽就有 —— 跟 Enhance
    的 `stream_change` 同一個生命週期）：

    * **有號直方圖**（0 置中）—— 差影像的中心是 0 不是 128；
    * **殘留數字**：median / MAD / 超出 ±3×MAD 的比例；
    * **行/列平均曲線** —— 抓半像素對位殘留的主角：條紋在預覽上肉眼看不出，
      行列平均一眼看出方向與強度。
    """

    title = "Difference"

    def record(self) -> Dict[str, Any]:
        out = str(self.params.get("out", "diff") or "diff")
        return dict((self.meta.get("subtract") or {}).get(out) or {})

    def has_data(self) -> bool:
        return bool(self.record().get("bins"))

    def empty_reason(self) -> str:
        return ("Select a defect and this panel shows what the difference "
                "image is made of - the signed histogram around zero, the "
                "residual level, and the row/column means that reveal "
                "alignment stripes the preview cannot show.")

    def summary(self) -> str:
        r = self.record()
        if not r:
            return ""
        op = {"subtract": "−", "ratio": "÷", "max": "max", "min": "min",
              "mean": "mean"}.get(str(r.get("op") or ""), str(r.get("op")))
        return ("%s = %s %s %s · median %+.2f · MAD %.2f · %.1f%% beyond "
                "±3×MAD · %.1f%% clipped"
                % (self.params.get("out", "diff"), r.get("a", "?"), op,
                   r.get("b", "?"), float(r.get("median") or 0.0),
                   float(r.get("mad") or 0.0),
                   100.0 * float(r.get("beyond3") or 0.0),
                   100.0 * float(r.get("clipped") or 0.0)))

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        r = self.record()
        if not r.get("bins"):
            self._say_empty(p, rect)
            return
        op = {"subtract": "−", "ratio": "÷"}.get(str(r.get("op") or ""),
                                                 str(r.get("op") or ""))
        note = {"stream": str(self.params.get("out", "diff") or "diff"),
                "n": int(r.get("n") or 0)}
        head_h = paint_note_header(
            p, rect, note, colour=QColor(TOKENS["text_primary"]),
            tail="  = %s %s %s" % (r.get("a", "?"), op, r.get("b", "?")),
            trust="%.1f%% clipped" % (100.0 * float(r.get("clipped") or 0.0)))
        body = QRectF(rect.left(), rect.top() + head_h + 2, rect.width(),
                      rect.height() - head_h - 2)
        if body.height() < 20:
            return
        left = QRectF(body.left(), body.top(), body.width() * 0.54,
                      body.height())
        right = QRectF(left.right() + 8, body.top(),
                       body.right() - left.right() - 8, body.height())
        self._paint_signed_hist(p, left, r)
        self._paint_curves(p, right, r)

    def _paint_signed_hist(self, p: QPainter, rect: QRectF,
                           r: Dict[str, Any]) -> None:
        counts = [max(0, int(c)) for c in (r.get("bins") or [])]
        if not counts:
            return
        cap = QRectF(rect.left(), rect.bottom() - 11, rect.width(), 11)
        plot = QRectF(rect.left(), rect.top(), rect.width(),
                      max(8.0, rect.height() - 12))
        top = max(counts) or 1
        bw = plot.width() / float(len(counts))
        fill = QColor(TOKENS["accent"])
        fill.setAlpha(90)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(fill))
        for k, c in enumerate(counts):
            h = (c / float(top)) * plot.height()
            p.drawRect(QRectF(plot.left() + k * bw, plot.bottom() - h,
                              max(1.0, bw - 0.4), h))
        # 0 的中線 —— 這張圖的主角刻度（有號分布對稱於它）。
        p.setPen(QPen(QColor(TOKENS["text_secondary"]), 1.0, Qt.DashLine))
        mid = plot.left() + plot.width() / 2.0
        p.drawLine(QPointF(mid, plot.top()), QPointF(mid, plot.bottom()))
        p.setPen(QColor(TOKENS["border_default"]))
        p.drawLine(QPointF(plot.left(), plot.bottom()),
                   QPointF(plot.right(), plot.bottom()))
        hi = float(r.get("hi") or 0.0)
        p.setPen(QColor(TOKENS["text_hint"]))
        p.drawText(cap, Qt.AlignLeft | Qt.AlignVCenter, "%+.3g" % -hi)
        p.drawText(cap, Qt.AlignHCenter | Qt.AlignVCenter, "0")
        p.drawText(cap, Qt.AlignRight | Qt.AlignVCenter, "%+.3g" % hi)

    def _paint_curves(self, p: QPainter, rect: QRectF,
                      r: Dict[str, Any]) -> None:
        """行/列平均（各 ≤128 點，引擎抽稀過）—— 各自縮放、各配一條中線。"""
        halves = ((QRectF(rect.left(), rect.top(), rect.width(),
                          rect.height() / 2 - 2), "row means",
                   [float(v) for v in (r.get("rows") or [])]),
                  (QRectF(rect.left(), rect.center().y() + 2, rect.width(),
                          rect.height() / 2 - 2), "column means",
                   [float(v) for v in (r.get("cols") or [])]))
        for box, name, vals in halves:
            if len(vals) < 2 or box.height() < 14:
                continue
            p.setPen(QColor(TOKENS["text_hint"]))
            f = p.font()
            f.setPixelSize(theme.font_px("font_small"))
            p.setFont(f)
            p.drawText(box, Qt.AlignLeft | Qt.AlignTop, name)
            plot = QRectF(box.left(), box.top() + 11, box.width(),
                          max(6.0, box.height() - 12))
            lo, hi = min(vals), max(vals)
            span = (hi - lo) or 1.0
            mid_y = plot.top() + (hi - (lo + hi) / 2.0) / span * plot.height()
            p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0, Qt.DashLine))
            p.drawLine(QPointF(plot.left(), mid_y),
                       QPointF(plot.right(), mid_y))
            step = plot.width() / float(len(vals) - 1)
            pts = [QPointF(plot.left() + i * step,
                           plot.top() + (hi - v) / span * plot.height())
                   for i, v in enumerate(vals)]
            p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawPolyline(QPolygonF(pts))


class OutputPreviewInspector(Inspector):
    """輸出卡共用：**按下 Run 會寫出哪幾個檔**（PR-2 2e）。

    援引 Write KLARF 的那條硬規則（寫出前一定先預覽）：計畫來自 core 的
    `planned_files`（**跟 `run_batch` 同一張表**，各寫一份會漂），這裡只
    列出來 —— 不真的寫、**不猜檔案大小**。選到卡就有（未跑就看得到），
    勾選一變清單跟著變。
    """

    STEP_KEY = ""
    title = "Will write"

    def plan(self) -> List[Dict[str, str]]:
        try:
            from ..core.pipeline.step import get_step
            return list(get_step(self.STEP_KEY).planned_files(self.params))
        except Exception:  # 提示不准擋路
            return []

    def path(self) -> str:
        return str(self.params.get("folder", "") or "").strip()

    def has_data(self) -> bool:
        return bool(self.params)

    def empty_reason(self) -> str:
        return ("Select this card to see which files it would write - "
                "nothing is written until you run the whole batch.")

    def _count_line(self) -> str:
        if self.batch:
            return "%d defect(s) from the last run" % len(self.batch)
        return "run a trial to count the defects"

    def summary(self) -> str:
        plan = self.plan()
        return "%d file kind(s) into %s" % (
            len(plan), self.path() or "(folder not set yet)")

    def _lines(self) -> List[Tuple[str, str]]:
        lines = [("Writes into", self.path() or "(not set yet)")]
        for f in self.plan():
            lines.append((f.get("name", "?"), f.get("what", "")))
        if not self.plan():
            lines.append(("(nothing ticked)", "the folder would be empty"))
        lines.append(("Defects", self._count_line()))
        return lines

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        lines = self._lines()
        row_h = max(15.0, min(20.0, rect.height() / max(1, len(lines))))
        y = rect.top()
        for label, value in lines:
            p.setPen(QColor(TOKENS["text_secondary"]))
            p.drawText(QRectF(rect.left(), y, rect.width() * 0.42, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, label)
            p.setPen(QColor(TOKENS["text_primary"]))
            p.drawText(QRectF(rect.left() + rect.width() * 0.44, y,
                              rect.width() * 0.56, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, str(value))
            y += row_h
            if y > rect.bottom():
                break


class ReportPreviewInspector(OutputPreviewInspector):
    STEP_KEY = "output_report"
    title = "Report folder"

    def frame(self) -> Any:
        """**一列一顆 defect** 的長表（F89-4）—— 跨整批那張圖的選單吃它。

        ⚠ 跟 `UniformityPreviewInspector.frame()` 是**兩張不同的表**：那一張
        是「一顆之內、一列一格框」，這一張是「一列一顆」。兩個 `frame()` 同名
        是刻意的 —— `ParamForm.set_chart_frame` 問的就是這一句，而**哪一張表
        是這張卡的表，由那張卡自己答**。

        ⚠ 座標（`die_x` / `x_um`）**不在結果那幾列裡** —— 它們住在
        `Dataset.items`，由主視窗經 `meta["_items"]` 遞過來（同 `_klarf_doc`
        的理由：儀表不自己去讀檔）。沒有 KLARF 的兩種輸入那幾欄整欄是空的，
        而**空的欄跟「座標是 0」是兩件事**。
        """
        from ..core.export import chart_frame

        return chart_frame.build_lot_frame(
            self.batch, self.meta.get("_items") or [])


class CharPreviewInspector(OutputPreviewInspector):
    STEP_KEY = "output_char"
    title = "Comparison folder"

    def _lines(self) -> List[Tuple[str, str]]:
        lines = super()._lines()
        cols = [c for c in str(self.params.get("columns", "") or "").split(",")
                if c.strip()]
        lines.append(("Columns", "%d ticked" % len(cols) if cols
                      else "(none - just id, class and the pictures)"))
        return lines


class UniformityPreviewInspector(OutputPreviewInspector):
    """F85：`Write charts` 會寫哪幾個檔 —— **而且這一顆量出來是多少**。

    為什麼圖不在這裡（F87，使用者 2026-09-07：「右側 Uniformity folder 直接
    把預覽的圖放上來好像也很奇怪」）
    ----------------------------------------------------------------------
    同意。四張圖塞進這個窄面板，每張只剩約 250×180 —— 讀不動；而且那一排
    Output 儀表本來的節奏是**一份乾淨的「按下去會寫哪幾個檔」清單**，
    塞四張圖進去是把圖放在「UI 裡沒有別的家」的地方，不是設計。

    圖搬去 `ui/uniformity_window.UniformityWindow`（一顆 `Preview charts…`
    開它），這裡留下**讀得動的那一半**：會寫哪幾個檔 ＋ 這一顆每個區域的
    CV／斜率。那張小表跟報告頁上那一張是**同一支** `summary_rows` ——
    各算一份的話，面板上與報告裡會出現兩個 CV%，而沒有人看得出哪個對。

    ⚠ 數字**從 features 來，不在這裡重算**（`summary_rows` 的規矩）：
    算不出來的那一格印 ``-``，不印一個算出來的替身。
    """

    STEP_KEY = "output_uniformity"
    title = "Charts folder"

    #: 按了要開圖的視窗 —— 這一份不開視窗（儀表不認識主視窗），只說出請求，
    #: 跟 `CrossInspector.param_requested` 同一條界線。
    charts_requested = Signal()

    #: 下半那張小表最多佔幾成 —— 上半的檔案清單是硬規則（寫出前先預覽）。
    TABLE_SHARE = 0.55
    #: 按鈕那一條的高度（含上下留白）。
    BUTTON_H = 30.0

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        from .widgets import small_button

        self.btn_charts = small_button(
            "Preview charts\u2026", shape="wide",
            tip=("Open the four charts in their own window, big enough to "
                 "read - and change how they look."),
            parent=self)
        self.btn_charts.clicked.connect(self.charts_requested)
        self.btn_charts.hide()

    def charts(self) -> List[str]:
        """勾了哪幾張（照 `CHARTS` 的順序，不照使用者打字的順序）。"""
        from ..core.export import uniformity_charts as uc

        got = {c.strip() for c in
               str(self.params.get("charts", "") or "").split(",")}
        return [k for k in uc.CHARTS if k in got]

    def series(self) -> Dict[str, Any]:
        """這一顆的資料 —— **跟寫出去的走同一支** `chart_series`。"""
        from ..core.export import uniformity_charts as uc

        notes = self.meta.get("glv_hist")
        if not isinstance(notes, list):
            return {"groups": [], "metric": "", "metrics": []}
        return uc.chart_series(notes, metric=str(
            self.params.get("metric", "") or "").strip())

    def frame(self) -> Any:
        """一列一格框的長表 —— **跟 `boxes.csv` 走同一支** `build_frame`。

        散佈圖吃的是這一份，不是 `series`（兩條軸是使用者自己挑的欄，而
        `series` 只裝得下「一個統計量 ＋ 位置」）。UI 不自己再攤一次：畫面上
        那張圖跟寫出去的 CSV 對不起來的話，沒有人看得出哪一份是對的。
        """
        from ..core.export import chart_frame

        notes = self.meta.get("glv_hist")
        if not isinstance(notes, list):
            return chart_frame.build_frame([])
        return chart_frame.build_frame(notes)

    def rows(self) -> List[Dict[str, Any]]:
        """小表的列 —— **報告頁上那一張表的同一支**。"""
        from ..core.export import uniformity_charts as uc

        return uc.summary_rows(self.series(),
                               self.result.get("features") or {})

    def _lines(self) -> List[Tuple[str, str]]:
        lines = super()._lines()
        kinds = self.charts()
        lines.append(("Charts", "%d ticked" % len(kinds) if kinds
                      else "(none - this card would write empty pages)"))
        return lines

    def summary(self) -> str:
        base = super().summary()
        groups = self.series().get("groups") or []
        if not groups:
            return base
        boxes = sum(len(g.get("values") or ()) for g in groups)
        return "%s  \u00b7  %d region(s), %d box(es)" % (
            base, len(groups), boxes)

    # -- 那顆鈕 -------------------------------------------------------------
    def can_preview(self) -> bool:
        """有東西可看嗎（**沒東西的鈕不該按得下去** —— 推廣鐵則）。"""
        return bool(self.charts()) and bool(self.series().get("groups"))

    def _place_button(self) -> None:
        show = self.can_preview()
        self.btn_charts.setVisible(show)
        if not show:
            return
        size = self.btn_charts.sizeHint()
        w = max(126, size.width())
        h = max(22, size.height())
        self.btn_charts.setGeometry(
            int(self.width() - w - 14), int(self.height() - h - 12),
            int(w), int(h))

    def set_context(self, *a, **kw) -> None:
        super().set_context(*a, **kw)
        self._place_button()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_button()

    # -- 畫 -----------------------------------------------------------------
    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        series = self.series()
        if not series.get("groups"):
            super().paint_body(p, rect)
            self._say_no_boxes(p, rect)
            return
        room = max(0.0, rect.height() - self.BUTTON_H)
        rows = self.rows()
        table_h = min(room * self.TABLE_SHARE, 19.0 + 17.0 * len(rows))
        super().paint_body(p, QRectF(rect.left(), rect.top(), rect.width(),
                                     max(0.0, room - table_h - 6.0)))
        area = QRectF(rect.left(), rect.top() + room - table_h,
                      rect.width(), table_h)
        self._paint_table(p, area, rows, str(series.get("metric") or ""))

    def _say_no_boxes(self, p: QPainter, rect: QRectF) -> None:
        """為什麼沒有圖 —— **原因通常是上游那張卡，不是這一張**。"""
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(rect.left(), rect.bottom() - 30.0,
                          rect.width(), 28.0),
                   int(Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap),
                   "No box-by-box numbers yet: set the Gray level card to "
                   "\u201ceach box\u201d and tick something under \u201cHow "
                   "even are the boxes\u201d.")

    def _paint_table(self, p: QPainter, area: QRectF,
                     rows: List[Dict[str, Any]], metric: str) -> None:
        """一個區域一列：``epi · 24 boxes   CV 1.8 %   L→R 0.42 /100 px``。"""
        from ..core.export import uniformity_charts as uc

        if area.height() < 20.0:
            return
        # 一列 16 px：底線（``glv_mean`` 的 ``_``）住在基線下面，14 px 的框會
        # 把它切掉 —— 而切掉之後那個名字讀起來是 ``glv mean``，也就是一個
        # 不存在的特徵。
        fm = p.fontMetrics()
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(area.left(), area.top(), area.width(), 16.0),
                   int(Qt.AlignLeft | Qt.AlignVCenter),
                   "This defect%s" % (" \u00b7 %s" % metric if metric else ""))
        y = area.top() + 17.0
        for i, row in enumerate(rows):
            if y + 16.0 > area.bottom():
                p.setPen(QColor(TOKENS["text_hint"]))
                p.drawText(QRectF(area.left(), y, area.width(), 16.0),
                           int(Qt.AlignLeft | Qt.AlignVCenter),
                           "\u2026 %d more" % (len(rows) - i))
                break
            cells = row.get("cells") or {}
            bits = ["%s \u00b7 %d box(es)"
                    % (row.get("name") or "region", int(row.get("boxes") or 0))]
            for key, head, unit in uc.UNIF_COLUMNS:
                if key in cells:
                    # **面板走完整版**（`numbers` 那一支的邊界：短版只給畫在
                    # 影像上的標記）。這裡是一張表，而表上的數字是使用者真的
                    # 要讀的那一個 —— 少一位有效數字省不到什麼寬度，卻會讓
                    # 面板上的 CV 跟 CSV 上的對不起來。
                    bits.append("%s %s %s"
                                % (head, format_feature_value(cells[key]),
                                   unit))
            p.setPen(QColor(TOKENS["text_primary"] if i == 0
                            else TOKENS["text_secondary"]))
            # **放不下就 elide，不要讓它自己被邊界切掉**：切掉的那一刀落在
            # 數字中間時，畫面上會出現一個看起來完整而且是錯的值
            # （``1.29`` 切成 ``1.2``）。`…` 說得出「還有」。
            p.drawText(QRectF(area.left(), y, area.width(), 16.0),
                       int(Qt.AlignLeft | Qt.AlignVCenter),
                       fm.elidedText("    ".join(bits), Qt.ElideRight,
                                     int(area.width())))
            y += 17.0



class FocusInspector(MeasureInspector):
    """Focus index：**這一顆的三個銳利度值，選到就有**（PR-2 2e）。

    以前它掛在泛用的 Spread 上 —— 跑完一批才有東西。可是這張卡逐顆量、
    數字早就在（`quality.measure` note 進 meta 的那一份），單顆該立即
    顯示；整批的分布照舊由下半（繼承 `MeasureInspector`）補。
    """

    title = "Focus"

    #: 顯示用的一句話（dtype 檢查歸值域/dtype 那張 bug 單，這裡只講）。
    HINT = "sharpness only means anything on an 8-bit stream"

    def notes(self) -> List[Dict[str, Any]]:
        return [n for n in (self.meta.get("focus") or [])
                if isinstance(n, dict)]

    def has_data(self) -> bool:
        return bool(self.notes()) or bool(self.rows())

    def empty_reason(self) -> str:
        return ("Select a defect to see its three sharpness numbers; run a "
                "trial to see how they spread across the batch.")

    def summary(self) -> str:
        notes = self.notes()
        if not notes:
            return super().summary()
        n = notes[0]
        return ("lapvar %.4g · tenengrad %.4g · fft %.4g — higher is sharper"
                % (float(n.get("lapvar") or 0.0),
                   float(n.get("tenengrad") or 0.0),
                   float(n.get("fft") or 0.0)))

    #: 單顆那一段的高度：一列 header + 一列數字 + 一列提示。
    NOTE_H = 46.0

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        notes = self.notes()
        if not notes:
            super().paint_body(p, rect)
            return
        note = notes[0]
        head_h = paint_note_header(
            p, rect, {"stream": note.get("stream", ""),
                      "n": len(self.batch or [])},
            colour=QColor(TOKENS["text_primary"]),
            label="this defect", unit="defect(s) run")
        line = QRectF(rect.left(), rect.top() + head_h + 1, rect.width(), 15)
        p.setPen(QColor(TOKENS["text_primary"]))
        p.drawText(line, Qt.AlignLeft | Qt.AlignVCenter,
                   "lapvar %.4g    tenengrad %.4g    fft %.4g"
                   % (float(note.get("lapvar") or 0.0),
                      float(note.get("tenengrad") or 0.0),
                      float(note.get("fft") or 0.0)))
        hint = QRectF(rect.left(), line.bottom() + 1, rect.width(), 13)
        p.setPen(QColor(TOKENS["text_hint"]))
        p.drawText(hint, Qt.AlignLeft | Qt.AlignVCenter, self.HINT)
        rest = QRectF(rect.left(), hint.bottom() + 4, rect.width(),
                      rect.bottom() - hint.bottom() - 4)
        # 批次的分布（繼承的下半）：跑過才有；沒跑不畫（單顆那三行就是答案，
        # 再畫一句「跑一批」是把主角擠掉）。
        if self.rows() and rest.height() >= 40:
            super().paint_body(p, rest)


INSPECTORS: Dict[str, type] = {
    "load_patch": InputInspector,
    # 同一個面板：它讀的是 meta["input"]，兩張 Input 卡都會寫（F11 Input-4）。
    "load_single": InputInspector,
    "roi_cross": CrossInspector,
    "roi_template": TemplateInspector,
    "align": AlignInspector,
    "tone": EnhanceInspector,
    "normalize": EnhanceInspector,
    "denoise": EnhanceInspector,
    "flatten": EnhanceInspector,
    # F18 第 2 步：Gray level 換成「這一顆的分布」（Spread 搬去 Results）。
    # 其餘量測卡暫時留在 Spread —— 它們還沒有自己的面板，而**沒有面板比
    # 「跑完才有東西的面板」更糟**。CD 那張本來就要整張重做（F19）。
    "glv_stats": GlvInspector,
    # F19：CD 有自己的面板了（剖面圖是它唯一講得清楚自己的方式）。
    "cd_measure": CdInspector,
    # PR-2：單顆的三個銳利度值選到就有，批次分布（繼承 Spread）跑完再補。
    "focus_quality": FocusInspector,
    # PR-2：diff 是 D2D 的心臟 —— 有號直方圖、殘留數字、行列平均曲線。
    "subtract": SubtractInspector,
    # PR-2：輸出卡援引 Write KLARF 的硬規則（寫出前一定先預覽）——
    # 選到卡就列出會寫哪幾個檔，跟 `run_batch` 讀同一張 `planned_files` 表。
    "output_report": ReportPreviewInspector,
    "output_char": CharPreviewInspector,
    # F85：跟另外兩張走同一支 —— 寫出前一定先預覽（M5 的硬性規則）。
    "output_uniformity": UniformityPreviewInspector,
    # ⚠ ``roi_reference`` **一個 key、三種面板**（F30）—— 見 :data:`BY_METHOD`。
    # 這裡放的是「沒有 method 可看時的那一個」。
    "roi_reference": GdsInspector,
    "pair_source": PairInspector,
    # 對圖的分數只有**跟整批比**才讀得懂（0.62 是高是低要看其他顆長什麼樣），
    # 所以分布留著 —— 但 F33 之後上面多一行講「對到哪、歪多少、可不可信」。
    "align_to": H2HInspector,
    # 寫回前一定先預覽變更（M5 的硬性規則，F16 Stage 5c 搬過來的）。
    "output_klarf": WriteBackInspector,
}


#: 一個 step key 有好幾種面板時，由**哪一個參數**決定，以及各對應哪一個
#: （F30：四張 Region 卡收成 ``roi_reference`` 的四個 ``method``）。
#:
#: 為什麼不是「一張卡一個面板」就好：面板講的是**這一支怎麼算的**（Profile 的
#: 兩條投影曲線、Template 的三道閘門、GDS 的層清單），而那三件事沒有一個共同的
#: 畫法。硬湊一個的話，使用者看到的是一塊「有時候是空的」的面板。
BY_METHOD: Dict[str, Dict[str, Optional[type]]] = {
    "roi_reference": {
        "stripes in the image": CrossInspector,
        "a cell I mark myself": TemplateInspector,
        "layout layers": GdsInspector,
    },
}


def inspector_for(step_key: str,
                  params: Optional[Dict[str, Any]] = None) -> Optional[type]:
    """這張卡的儀表。``params`` 給了的話，同一個 key 可以有好幾種（見
    :data:`BY_METHOD`）。"""
    key = str(step_key or "")
    table = BY_METHOD.get(key)
    if table is not None and params is not None:
        method = str((params or {}).get("method", ""))
        if method in table:
            return table[method]
        # method 認不得（舊檔、打字錯）→ 落回 INSPECTORS 那一個，不要當機。
    return INSPECTORS.get(key)

# d4t Studio — 每張卡自己的儀表 (F7-17).
"""選一張卡，右下角就換成**那張卡的儀表**。

為什麼不是一塊通用面板
----------------------
右下角本來是一張「特徵 / 數值」表：`roi_snr_signed 11.170`、`glv_max 255`。
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
import traceback
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from ..core.algo import glv as algo_glv
from ..core.steps._util import CLIP_FRAC, PAIR_FEATURES
from ..core.steps.denoise import HOT_FRAC, REMOVED_OVER_NOISE
from . import theme
from .theme import TOKENS, region_hex

__all__ = ["Inspector", "AlignInspector", "EnhanceInspector",
           "MeasureInspector", "GlvInspector", "InputInspector",
           "CrossInspector", "TemplateInspector",
           "INSPECTORS", "inspector_for"]


class Inspector(QWidget):
    """卡片儀表的共同介面。

    ``set_context()`` 一次餵齊三種來源：這張卡的參數、**這一顆**的結果、
    以及**整批**的結果。子類自己決定要用哪些 —— 但不准自己去跑 pipeline。
    """

    #: 面板標題（顯示在切換列上）。
    title = "Card"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.params: Dict[str, Any] = {}
        self.result: Dict[str, Any] = {}
        self.batch: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = {}
        self.feature_names: List[str] = []
        self.shown_streams: List[str] = []
        self.node_id = ""
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_context(self, node_id: str, params: Optional[Dict[str, Any]] = None,
                    result: Optional[Dict[str, Any]] = None,
                    batch: Optional[Sequence[Dict[str, Any]]] = None,
                    meta: Optional[Dict[str, Any]] = None,
                    feature_names: Optional[Sequence[str]] = None,
                    shown_streams: Optional[Sequence[str]] = None) -> None:
        self.node_id = str(node_id or "")
        self.params = dict(params or {})
        self.result = dict(result or {})
        self.batch = [dict(r) for r in (batch or [])]
        self.meta = dict(meta or {})
        #: 預覽區**現在正在看**哪幾條流（並排比對打開時是左右那兩條）。
        #: 儀表要跟著畫面走：畫面上兩張圖，底下就該是兩張直方圖。
        self.shown_streams = [str(s) for s in (shown_streams or []) if s]
        #: 這張卡**自己**產出哪些特徵（含 output_prefix）。解析要用卡片庫，
        #: 那是 Studio 的事 —— 儀表只負責畫。
        self.feature_names = [str(f) for f in (feature_names or [])]
        self.update()

    # -- 子類覆寫 -----------------------------------------------------------
    def tab_title(self) -> str:
        """分頁鈕上的字。**預設是類別的 `title`，但子類可以按狀態改**。

        以前這一格讀的是**類別屬性**，所以不管畫面上是什麼，它永遠寫著
        「Gray level」——「這一塊在講什麼」得自己從圖裡推。使用者 2026-08-21：
        「他的 title 要更詳細一點（顯示的是什麼、誰跟誰比之類的）」。
        """
        return str(getattr(self, "title", "Card"))

    def tab_tooltip(self) -> str:
        """分頁鈕的 tooltip —— 標題放不下的那半句話。"""
        return ""

    def summary(self) -> str:
        """一行文字摘要。**測試與狀態列讀這個**，不去讀畫素。"""
        return ""

    def has_data(self) -> bool:
        return False

    def empty_reason(self) -> str:
        """沒有資料時要說的話 —— 空白面板本身不是訊息。"""
        return "Run a trial to fill this in."

    # -- 共用小工具 ---------------------------------------------------------
    def feature_values(self, name: str) -> List[float]:
        """整批裡某個特徵的值（跳過失敗與缺值的顆）。"""
        out: List[float] = []
        for r in self.batch:
            v = (r.get("features") or {}).get(name)
            if v is None:
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if not (math.isnan(f) or math.isinf(f)):
                out.append(f)
        return out

    def this_value(self, name: str) -> Optional[float]:
        v = (self.result.get("features") or {}).get(name)
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return None if (math.isnan(f) or math.isinf(f)) else f

    def _frame(self, p: QPainter) -> QRectF:
        rect = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(QRectF(self.rect()), QColor(TOKENS["bg_surface"]))
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
        p.drawRoundedRect(rect, 4, 4)
        return rect.adjusted(8, 8, -8, -8)

    def _say_empty(self, p: QPainter, rect: QRectF) -> None:
        p.setPen(QColor(TOKENS["text_disabled"]))
        p.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap, self.empty_reason())

    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
        """**畫不出來不得毀掉整個畫面**（2026-08-20）——鐵則 7 的 UI 版。

        Qt 的 ``paintEvent`` 一丟例外就留下一個沒收尾的 painter
        （``QBackingStore::endPaint() called with active painter``），而接下來
        每一次重繪都會再失敗一次 —— 使用者看到的是**別的地方**壞掉：實際發生
        的那次是「配對卡的圖載不出來」，而真正的錯在儀表的一行除法。

        所以：例外照樣印到終端機（不要藏），但畫面上只變成這個面板的一行字，
        而且 painter 一定收尾。
        """
        p = QPainter(self)
        try:
            rect = self._frame(p)
            if not self.has_data():
                self._say_empty(p, rect)
            else:
                self.paint_body(p, rect)
        except Exception:                  # noqa: BLE001 — 見 docstring
            traceback.print_exc()
            try:
                p.setPen(QColor(TOKENS["danger_text"]))
                p.drawText(QRectF(self.rect()).adjusted(10, 10, -10, -10),
                           Qt.AlignCenter | Qt.TextWordWrap,
                           "This panel could not be drawn (see the terminal). "
                           "Everything else still works.")
            except Exception:              # noqa: BLE001 — 連錯誤都畫不出來
                pass
        finally:
            p.end()

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        """子類畫這裡（``rect`` 已經扣掉外框與留白）。"""


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
        xs = self.feature_values("align_dx")
        ys = self.feature_values("align_dy")
        n = min(len(xs), len(ys))
        return list(zip(xs[:n], ys[:n]))

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

    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
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


class EnhanceInspector(Inspector):
    """Enhance 九張卡共用：**同一條流的 before / after 直方圖 + 削平計數**。

    為什麼是這一張圖
    ----------------
    Enhance 的失敗是安靜的。對比拉大之後「看起來變乾淨了」，但背景被壓成全黑、
    缺陷的邊界也一起被吃掉 —— 而**後面每一張量測卡都吃這個結果**。

    削平（畫素貼在 0 或 255）是唯一能量化「我毀掉了多少」的東西：那些畫素之間的
    差異永遠回不來了。所以這裡除了兩條分布，還直接把「多少 % 被壓到底 / 頂」
    講成一句話。

    資料來自引擎（``ctx.meta['stream_change']``，預覽時才記）—— UI 不自己再套
    一次那些演算法，不然畫面上的曲線跟真的算出來的有機會不一樣。
    """

    title = "Before / after"

    #: 削平多少才值得警告。**不是 0** —— 原圖本來就可能有幾顆全黑的畫素，
    #: 而每次都喊狼來了跟不喊一樣沒有用。實測 1% 以下肉眼看不出差別。
    WARN_CLIP = 0.01

    def stream(self) -> str:
        """這張卡的主要輸出流（也就是要比 before/after 的那一條）。

        F7-20 起 Enhance 卡的參數是 ``streams``（一串，逗號分隔），所以這裡取
        第一條。``target`` / ``source`` 留著是為了舊 recipe 與非 Enhance 的卡。

        ⚠ 一張卡吃兩條流的時候，這個面板目前只畫得出第一條 —— 兩條各一組
        before/after 是 F7-19 畫布那一半的事（計畫書 §23.7）。
        """
        raw = str(self.params.get("streams") or self.params.get("target")
                  or self.params.get("source") or "test")
        first = raw.split(",")[0].strip()
        return first or "test"

    def streams(self) -> List[str]:
        """這張卡處理的每一條流（``streams`` 是逗號分隔的一串）。"""
        raw = str(self.params.get("streams") or self.params.get("target")
                  or self.params.get("source") or "test")
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        return keys or ["test"]

    def panes(self) -> List[str]:
        """要畫幾張直方圖、各是哪一條流。

        **跟著預覽畫面走**：並排比對打開時畫面上是兩張圖，底下就該是兩張
        直方圖，而且左右順序一樣 —— 使用者是拿它們互相對照的，順序對不上就
        每次都要重新認一次哪張配哪張。

        只取這張卡真的動過的流：並排的右邊可能是 ``diff``（這張 Enhance 卡沒
        碰過它），那畫一張空的圖只是佔位子。都沒有的話退回這張卡的第一條流。
        """
        changes = dict(self.meta.get("stream_change") or {})
        mine = self.streams()
        if self.shown_streams:
            picked = [s for s in self.shown_streams if s in changes]
            if picked:
                return picked
        return [s for s in mine if s in changes] or mine[:1]

    def record(self, key: Optional[str] = None) -> Dict[str, Any]:
        changes = dict(self.meta.get("stream_change") or {})
        return dict(changes.get(key or self.stream()) or {})

    def has_data(self) -> bool:
        return any(bool(self.record(k).get("before"))
                   and bool(self.record(k).get("after"))
                   for k in self.panes())

    def empty_reason(self) -> str:
        return ("Select a defect to see what this card does to “%s” — the "
                "grey levels before it ran and after." % self.stream())

    def clipped(self, key: Optional[str] = None) -> Tuple[float, float]:
        rec = self.record(key)
        return (float(rec.get("clipped_low", 0.0)),
                float(rec.get("clipped_high", 0.0)))

    def added_clipping(self, key: Optional[str] = None) -> Tuple[float, float]:
        """**這張卡自己**新增的削平（原圖本來就黑掉的部分不算它的帳）。"""
        rec = self.record(key)
        lo = float(rec.get("clipped_low", 0.0)) - float(rec.get("was_clipped_low", 0.0))
        hi = float(rec.get("clipped_high", 0.0)) - float(rec.get("was_clipped_high", 0.0))
        return (max(0.0, lo), max(0.0, hi))

    def stream_feature_name(self, key: Optional[str], name: str) -> str:
        """這一條流的某個診斷特徵**叫什麼**（多流才有前綴，F10-3）。"""
        k = key or self.stream()
        return ("%s_%s" % (k, name)) if len(self.streams()) > 1 else name

    def stream_feature(self, key: Optional[str], name: str) -> Optional[float]:
        """這一條流的某個診斷特徵值（**兩條以上才有流名前綴**，F10-3）。

        前綴規則在引擎那邊（`MultiStreamStep.run`）與這裡各寫了一次，而寫錯的
        那一半是安靜的（面板就只是不印那一行）—— 所以有一支測試從真實預覽走完
        整條路，不是只餵假資料。
        """
        return self.this_value(self.stream_feature_name(key, name))

    def pushed_out(self, key: Optional[str] = None) -> Optional[float]:
        """引擎量到的「算出來超出 0–255、被壓回來」的比例（F11 Enhance-1）。

        **跟 :meth:`clipped` 是兩件事**，所以講法也不一樣：

        - ``clipped``：輸出裡有多少畫素**坐在** 0 或 255。原圖本來就有的黑也算
          進來，而且直方圖上看得到（兩端那根染色的柱子）。
        - ``pushed_out``：這張卡**算出了值域以外的值**（實測 ``stripes_h`` 會
          到 261.5）。那些資訊在存進影像流之前就被壓掉了，所以直方圖上**看不到**
          —— 兩端的柱子只長高一點點，看起來跟原本就有的黑沒兩樣。

        數字來自引擎（``clip_frac`` 特徵，`MultiStreamStep.run` 寫的），UI 不自己
        再量一次。多流時特徵名帶流名前綴 —— 跟量測卡同一條規則（F10-3）。
        """
        return self.stream_feature(key, CLIP_FRAC)

    def replaced(self, key: Optional[str] = None) -> Optional[float]:
        """``denoise`` 的 hot_pixels 換掉了多少比例（F11 Enhance-2）。

        **這是使用者調 `threshold` 時唯一看得到的回饋**：門檻壓低到開始吃真的缺陷
        時，影像上看不出來（少了幾顆亮點而已），但這個數字會跳。
        """
        return self.stream_feature(key, HOT_FRAC)

    def sigma(self, key: Optional[str] = None) -> Optional[float]:
        """這一條流的雜訊 σ（只有 Denoise 卡量，F11 Enhance-1）。

        為什麼要露出來：``strength`` 的單位就是它（「濾掉幾個 σ 的擾動」），
        而在這之前使用者是在調一個「以某個他看不到的數字為單位」的旋鈕。
        來自 ``ctx.meta['noise_sigma']``（`denoise.note_stream` 寫的）。
        """
        table = self.meta.get("noise_sigma") or {}
        try:
            v = float(table[str(key or self.stream())])
        except (KeyError, TypeError, ValueError):
            return None
        return None if (math.isnan(v) or math.isinf(v)) else v

    def removed_over_noise(self, key: Optional[str] = None) -> Optional[float]:
        """磨掉的東西有幾個 σ（`denoise` 的平滑法，F11 Enhance-UI-E）。

        ≈1 = 磨掉的量級就是雜訊（想要的）；≫1 = 連結構一起磨掉了。這是
        ``strength`` / ``ksize`` 那兩個旋鈕唯一的問題，而**兩種結果在單顆畫面上
        都「看起來乾淨了」** —— 那正是它需要一個數字的理由。
        """
        return self.stream_feature(key, REMOVED_OVER_NOISE)

    #: 兩條流差多少就算「還不能比」。**經驗值，不是定理** —— 面板同時把實際數字
    #: 印出來，使用者自己看得到它離這條線多遠。
    #: 5 個灰階的整片偏移在 diff 上是看得見的一塊；起伏差 1.5 倍表示同一個門檻
    #: 在兩張圖上抓到的東西不一樣多。
    PAIR_LEVEL_OK = 5.0
    PAIR_RATIO_OK = 1.5

    def pair(self) -> Optional[Tuple[float, float]]:
        """這張卡處理的前兩條流**還有多像**（F11 Enhance-UI-B）。

        回 ``(背景差幾個灰階, 起伏差幾倍)``，只有一條流時回 None。
        可比性是 `subtract` 的前提，而「不可比」在畫面上長得像「兩張圖本來就不
        一樣」—— 一張比較亮的 ref 減出來的 diff 整片偏移，看起來就像一個大面積
        的缺陷。
        """
        if len(self.streams()) < 2:
            return None
        delta = self.this_value(PAIR_FEATURES[0])
        ratio = self.this_value(PAIR_FEATURES[1])
        if delta is None or ratio is None:
            return None
        return (delta, ratio)

    def batch_pushed_out(self, key: Optional[str] = None) -> List[float]:
        """**整批**每一顆被壓回值域的比例（F11 Enhance-UI-H）。

        為什麼一定要有整批的那一版
        --------------------------
        這是 `AlignInspector` 教過的那一課：Enhance 的失敗是**「某幾顆」**的事。
        調參數的人看的是第 1 顆，而出問題的是第 57 顆 —— 單顆的數字永遠只回答
        那一顆，不管它多準。

        資料來自 ``trial_results``（引擎跑出來的整批），所以不必再跑一次。
        """
        return self.feature_values(self.stream_feature_name(key, CLIP_FRAC))

    def batch_over_limit(self, key: Optional[str] = None) -> Tuple[int, int]:
        """整批裡**有幾顆**壓掉超過 1%（回 ``(超過的, 總共)``）。"""
        vals = self.batch_pushed_out(key)
        return (sum(1 for v in vals if v > self.WARN_CLIP), len(vals))

    def summary(self) -> str:
        if not self.has_data():
            return ""
        panes = self.panes()
        bits = []
        worst = 0.0
        for key in panes:
            lo, hi = self.clipped(key)
            bits.append("“%s” %.1f%% at black, %.1f%% at white"
                        % (key, lo * 100.0, hi * 100.0))
            # 直方圖看不到的兩個數字，就寫在它旁邊（σ 是旋鈕的單位；
            # pushed_out 是「這張卡把資訊推到值域外」而那在圖上看不出來）。
            extra = []
            sig = self.sigma(key)
            if sig is not None:
                extra.append("noise σ ≈ %.1f" % sig)
            hot = self.replaced(key)
            if hot is not None:
                extra.append("%.2f%% replaced as hot/dead pixels"
                             % (hot * 100.0))
            rem = self.removed_over_noise(key)
            if rem is not None:
                extra.append("removed %.1f× the noise" % rem)
            out = self.pushed_out(key)
            if out is not None and out >= 0.0005:
                extra.append("%.1f%% computed outside 0–255 and clipped back"
                             % (out * 100.0))
            if extra:
                bits[-1] += " (%s)" % ", ".join(extra)
            alo, ahi = self.added_clipping(key)
            worst = max(worst, alo, ahi)
        text = " · ".join(bits)
        alo = ahi = worst
        if max(alo, ahi) >= self.WARN_CLIP:
            text += ("  ⚠ this card flattened %.1f%% of the patch onto the "
                     "ends of the scale — those pixels no longer differ from "
                     "each other, and every measure card downstream reads "
                     "them as identical." % (max(alo, ahi) * 100.0))
        pair = self.pair()
        if pair is not None:
            keys = self.streams()
            delta, ratio = pair
            text += ("  ·  “%s” vs “%s” now: %.1f gray levels apart, spread "
                     "%.2f×" % (keys[0], keys[1], delta, ratio))
            if delta > self.PAIR_LEVEL_OK or ratio > self.PAIR_RATIO_OK:
                text += (" — still not comparable, so the difference image "
                         "will show that gap as if it were a defect")
        over, total = self.batch_over_limit(panes[0] if panes else None)
        if over:
            # **這一句講的是別的顆**，所以它要講「幾顆之中的幾顆」而不是一個比例
            # —— 使用者接下來要做的事是去看那幾顆。
            text += ("  ⚠ %d of the %d defects in the last trial lost more "
                     "than 1%% this way — the one on screen is not the worst "
                     "case." % (over, total))
        return text

    #: 整批那條走勢圖的高度（含標籤）。面板只有 ~200px，所以它必須很薄 ——
    #: 它回答的是一個是非題（「有沒有別的顆更糟」），不是一張要細看的圖。
    _STRIP_H = 22.0

    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
        panes = self.panes()
        if not panes:
            return
        # 整批的走勢圖佔底下一條，**只有真的有整批資料時才佔位子**（跑過一次
        # trial 之前它是空的，而一條空的軸線只是雜訊）。
        body = rect
        strip = None
        if self.batch_pushed_out(panes[0]):
            body = QRectF(rect.left(), rect.top(), rect.width(),
                          max(40.0, rect.height() - self._STRIP_H))
            strip = QRectF(rect.left(), body.bottom(), rect.width(),
                           self._STRIP_H)
        # 並排比對打開時畫兩張 —— 左右的順序跟畫面上兩張圖一樣。
        gap = 14.0
        w = (body.width() - gap * (len(panes) - 1)) / float(len(panes))
        for i, key in enumerate(panes):
            box = QRectF(body.left() + i * (w + gap), body.top(), w, body.height())
            self._paint_one(p, box, key, with_axis_title=(i == 0))
        if strip is not None:
            self._paint_batch_strip(p, strip, panes[0])

    def _paint_batch_strip(self, p: QPainter, rect: QRectF, key: str) -> None:
        """整批的 ``clip_frac``：一顆一根，超過 1% 的那幾根染警示色。

        為什麼是逐顆一根、而不是一個分布直方圖
        --------------------------------------
        使用者接下來要做的事是**去看那幾顆**，所以橫軸要是「第幾顆」——
        分布圖答得出「有幾顆很糟」，但答不出「是哪幾顆」。
        """
        vals = self.batch_pushed_out(key)
        if not vals:
            return
        label = "clip across %d defects" % len(vals)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(rect.left(), rect.top(), rect.width(), 12),
                   Qt.AlignLeft | Qt.AlignVCenter, label)
        over = sum(1 for v in vals if v > self.WARN_CLIP)
        if over:
            p.setPen(QColor(TOKENS["danger_text"]))
            p.drawText(QRectF(rect.left(), rect.top(), rect.width(), 12),
                       Qt.AlignRight | Qt.AlignVCenter,
                       "%d over 1%%" % over)
        plot = QRectF(rect.left(), rect.top() + 12, rect.width(),
                      max(4.0, rect.height() - 13))
        # 刻度固定從 0 起、上界是 max 與 1% 的較大者 —— 全部都很小的時候不要把
        # 0.01% 放大成滿格（那看起來像是出了事）。
        top = max(max(vals), self.WARN_CLIP)
        bw = plot.width() / float(len(vals))
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
        p.drawLine(QPointF(plot.left(), plot.bottom()),
                   QPointF(plot.right(), plot.bottom()))
        p.setPen(Qt.NoPen)
        warn = QColor(TOKENS["danger_text"])
        ok = QColor(TOKENS["accent"])
        ok.setAlpha(150)
        for i, v in enumerate(vals):
            h = (v / top) * plot.height() if top > 0 else 0.0
            if v <= 0.0:
                continue
            p.setBrush(QBrush(warn if v > self.WARN_CLIP else ok))
            p.drawRect(QRectF(plot.left() + i * bw, plot.bottom() - h,
                              max(1.0, bw - 0.5), max(1.0, h)))

    def _paint_one(self, p: QPainter, rect: QRectF, key: str,
                   with_axis_title: bool) -> None:
        """一條流的 before/after 直方圖。

        軸要講得出自己是什麼
        --------------------
        使用者原話：「histogram 我有點看不太懂，橫軸是 GLV 縱軸是 pixel counts？
        細線是什麼？」—— 三個問題，三個都是**畫面上沒寫**。以前只有兩端的
        ``black`` / ``white`` 跟一句 ``outline = before · filled = after``，
        而那句話要先知道 outline 指的是那條細線才讀得懂。

        現在：橫軸寫 ``gray level  0 → 255``、縱軸寫 ``pixels``，圖例直接**畫**
        一小段細線與一小塊實心方塊配上字，不要求使用者把名詞對應到圖形。
        """
        rec = self.record(key)
        head = QRectF(rect.left(), rect.top(), rect.width(), 13)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(head, Qt.AlignLeft | Qt.AlignVCenter, "“%s”" % key)
        if with_axis_title:
            p.drawText(head, Qt.AlignRight | Qt.AlignVCenter, "pixels ↑")

        before = [float(v) for v in rec.get("before") or []]
        after = [float(v) for v in rec.get("after") or []]
        if not before and not after:
            p.drawText(rect, Qt.AlignCenter, "no record for this stream")
            return
        n = max(len(before), len(after))
        # **高度用平方根。** 削平會在兩端堆出兩根極高的柱子（六成的畫素都在那裡），
        # 線性刻度下其餘的分布會被壓成一條貼著底的線 —— 而那正是要比較的形狀。
        # 平方根保住高低順序，又讓中間看得見。
        before = [math.sqrt(v) for v in before]
        after = [math.sqrt(v) for v in after]
        top = max(max(before or [1.0]), max(after or [1.0]), 1.0)

        plot = QRectF(rect.left(), rect.top() + 20,
                      rect.width(), max(20.0, rect.height() - 52))
        bw = plot.width() / float(n)

        def bars(vals: List[float], col: QColor, filled: bool) -> None:
            p.setPen(Qt.NoPen if filled else QPen(col, 1.4))
            p.setBrush(QBrush(col) if filled else Qt.NoBrush)
            path_pts = []
            for i, v in enumerate(vals):
                h = (v / top) * plot.height()
                x = plot.left() + i * bw
                if filled:
                    p.drawRect(QRectF(x, plot.bottom() - h, max(1.0, bw - 0.6), h))
                else:
                    path_pts.append(QPointF(x + bw / 2.0, plot.bottom() - h))
            if not filled and len(path_pts) > 1:
                for a, b in zip(path_pts, path_pts[1:]):
                    p.drawLine(a, b)

        # after 是實心的（那是現在的樣子），before 只畫輪廓 —— 兩個都實心會
        # 疊成一團看不出誰是誰。
        faint = QColor(TOKENS["text_disabled"])
        bar = QColor(TOKENS["accent"])
        bar.setAlpha(170)
        bars(before, faint, False)
        bars(after, bar, True)

        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
        p.drawLine(QPointF(plot.left(), plot.bottom()),
                   QPointF(plot.right(), plot.bottom()))

        # 兩端的削平：把貼在 0 / 255 的那一格**整根柱子**染成警示色。
        #
        # 以前是在圖的正上方畫一小塊色塊。那個位置離它在講的那根柱子有半張圖那麼
        # 遠，於是它看起來像是一個獨立的裝飾 —— 使用者看得到它，但看不出來它在指
        # 什麼。標記要長在被標記的東西上面。
        lo, hi = self.clipped(key)
        alo, ahi = self.added_clipping(key)
        for frac, added, at_left in ((lo, alo, True), (hi, ahi, False)):
            if frac <= 0.0005:
                continue
            col = QColor(TOKENS["danger_text"] if added >= self.WARN_CLIP
                         else TOKENS["warning"])
            idx = 0 if at_left else (len(after) - 1)
            h = ((after[idx] / top) * plot.height()) if 0 <= idx < len(after) else 0.0
            x = plot.left() if at_left else plot.right() - bw
            w = max(1.0, bw - 0.6)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(col))
            if h > 0:
                p.drawRect(QRectF(x, plot.bottom() - h, w, h))
            # 柱子再矮也要看得見，所以柱頂再壓一小塊（柱高 0 時它就是全部）。
            cap = QRectF(x, plot.bottom() - max(h, 3.0) - 3.0, max(3.0, w), 3.0)
            p.drawRect(cap)

        # 橫軸：兩端的 0 / 255 加上中間那句「這是什麼軸」。
        axis = QRectF(rect.left(), plot.bottom() + 1, rect.width(), 13)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(axis, Qt.AlignLeft | Qt.AlignVCenter, "0 black")
        p.drawText(axis, Qt.AlignRight | Qt.AlignVCenter, "white 255")
        p.drawText(axis, Qt.AlignCenter, "gray level")

        # 圖例：**畫**一段細線與一塊實心方塊，不要只寫「outline / filled」——
        # 那要求使用者先把名詞對回圖形，而那正是他卡住的地方。
        self._paint_legend(p, QRectF(rect.left(), axis.bottom() + 1,
                                     rect.width(), 14), faint, bar)

    @staticmethod
    def _paint_legend(p: QPainter, box: QRectF, line_col: QColor,
                      fill_col: QColor) -> None:
        y = box.center().y()
        x = box.left()
        p.setPen(QPen(line_col, 1.4))
        p.drawLine(QPointF(x, y), QPointF(x + 12, y))
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(x + 16, box.top(), 60, box.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, "before")
        x += 74
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(fill_col))
        p.drawRect(QRectF(x, y - 4, 12, 8))
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(x + 16, box.top(), 60, box.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, "after")


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

    def set_context(self, *a, **kw) -> None:   # noqa: D102
        super().set_context(*a, **kw)
        rec = self.record()
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

    def paintEvent(self, _e) -> None:          # noqa: D102 - 內容由子元件畫
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

    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
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
    `roi_snr_signed 11.170` 單獨存在回答不了任何問題。而調一張量測卡的時候，
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

    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
        names = self.rows()
        if not names:
            # 子類可能因為**別的理由**說「有資料」（`PairInspector` 手上有配對
            # 資訊，但整批的數字要跑一批才有）。那時候這裡一列都畫不出來，而
            # 底下那一行除法會是 ZeroDivisionError —— 2026-08-20 使用者遇到的
            # 就是它，而症狀是「圖載不出來」。
            self._say_empty(p, rect)
            return
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


def _fmt(v: float) -> str:
    a = abs(v)
    if a >= 1000 or (a and a < 0.01):
        return "%.3g" % v
    return "%.3f" % v if a < 100 else "%.1f" % v


class GlvInspector(Inspector):
    """Gray level：**這一顆量到的分布**，勾選的統計量標在上面（F18 第 2 步）。

    為什麼換掉 Spread（使用者 2026-08-21）
    -------------------------------------
    原話：「我不太喜歡要跑完才有 Spread 的設計，他是很重要，但他不應該被放在
    這邊，因為他在 run 之前都是空的。」而那句話有程式碼上的證據：

    ==============================  ====================  ================
    儀表                            資料從哪來            什麼時候有東西
    ==============================  ====================  ================
    `EnhanceInspector`              ``ctx.meta``          **預覽就有**
    `MeasureInspector`（Spread）    ``trial_results``     跑完一批才有
    ==============================  ====================  ================

    同一塊面板、同一個位置、兩種資料生命週期。這一張走的是前者：引擎在
    ``ctx.meta["glv_hist"]`` 留了每一塊的直方圖，所以**選到卡片的那一刻就有東西**。

    整批的資訊沒有消失，它縮成底下一條 8 px 的帶子（這一顆落在整批的哪裡），
    而「這個特徵分不分得開」那個問題搬去 Results —— 那裡本來就是「跑完才看」
    的地方，而且門檻拉得動（見 `ui/results.py`）。

    畫什麼
    ------
    * 一塊區域一條直方圖（最多 :data:`MAX_ROWS` 條，多的收成一句話）
    * 勾選到的統計量畫成刻度：**中心那一類畫實線，其餘畫短刻度** ——
      十個標記全畫成一樣的線的話，圖上會是一排看不出誰是誰的柵欄
    * 標題右邊是 ``n=… px · …% saturated`` —— 「這塊還能不能信」的兩個數字，
      而 patch 的 ROI 常常只有幾百個像素
    """

    title = "Gray level"

    #: 一次畫幾條分布。面板不高，四條以上每一條就只剩幾個畫素。
    MAX_ROWS = 3
    #: 底下那條「這一顆在整批的哪裡」的帶子有多高（跑過才畫）。
    BAND_H = 14.0
    #: 一個**位置**、畫整條實線的那幾個。
    CENTRE_MARKS = ("glv_median", "glv_p50", "glv_mean", "glv_trim")
    #: 一個**位置**、畫貼著底的短刻度的那幾個。
    POSITION_MARKS = ("glv_min", "glv_max", "glv_q")
    #: 一個**寬度**（不是位置）—— 畫成中心兩側的一段淡帶，見 :meth:`_paint_marks`。
    WIDTH_MARKS = ("glv_mad", "glv_std", "glv_iqr")

    # -- 資料 ---------------------------------------------------------------
    def rows(self) -> List[Dict[str, Any]]:
        """引擎留下的每一塊（`glv_stats._note_distribution` 寫的）。"""
        raw = self.meta.get("glv_hist")
        return [dict(r) for r in raw][:self.MAX_ROWS] if isinstance(raw, list) else []

    def has_data(self) -> bool:
        return bool(self.rows())

    def empty_reason(self) -> str:
        return ("Wire an image into this card and it will show the gray levels "
                "it measured, with the statistics you ticked marked on them.")

    def summary(self) -> str:
        rows = self.rows()
        if not rows:
            return ""
        bits = []
        for r in rows:
            where = r.get("region") or r.get("stream") or "whole image"
            bits.append("%s: %d px" % (where, int(r.get("n") or 0)))
        text = "  ·  ".join(bits)
        gated = [r for r in rows if r.get("thin")]
        if gated:
            # 使用者自己設了「至少要幾個像素」，而這一顆沒過 —— 那不是警告，
            # 是這張卡在照他說的做，所以講法是陳述句。
            text += ("  ·  under the minimum you set, so this defect's gray "
                     "levels are blank")
        thin = [r for r in rows if int(r.get("n") or 0) < self.THIN_PX
                and not r.get("thin")]
        if thin:
            # **樣本數太少的時候要講出來。** patch 的 ROI 常常只有幾百個像素，
            # 而在那個數量下離散度本身沒有意義 —— 而畫面上以前沒有任何地方
            # 說得出這件事。
            text += ("  ⚠ %s under %d pixels — spread statistics are not "
                     "reliable that thin."
                     % (", ".join(str(r.get("region") or r.get("stream") or "it")
                                  for r in thin), self.THIN_PX))
        hot = [r for r in rows if float(r.get("sat") or 0.0) > self.SAT_WARN]
        if hot:
            text += ("  ⚠ %.0f%% of the pixels sit at 0 or 255 — whatever was "
                     "in them is already gone."
                     % (100.0 * max(float(r.get("sat") or 0.0) for r in hot)))
        return text

    #: 少於這麼多像素就講一句話（見 :meth:`summary`）。
    THIN_PX = 400
    #: 貼在 0/255 的比例超過這個就講一句話。
    SAT_WARN = 0.02

    # -- 標題（使用者 2026-08-21：「要更詳細一點」）--------------------------
    def _pairs(self) -> Dict[str, str]:
        """區域名 -> 它跟誰比（引擎在 ``ctx.meta["compares"]`` 留的那一份）。"""
        out: Dict[str, str] = {}
        for rec in (self.meta.get("compares") or {}).values():
            if isinstance(rec, dict):
                out[str(rec.get("target") or "")] = str(rec.get("reference") or "")
        return out

    def tab_title(self) -> str:                # noqa: D102
        rows = self.rows()
        if not rows:
            return self.title
        pairs = self._pairs()
        first = rows[0]
        who = str(first.get("region") or "the image")
        if len(rows) > 1:
            return "%s · %d regions" % (self.title, len(rows))
        versus = pairs.get(who)
        if versus:
            # 「誰跟誰比」比「在哪條流上」重要 —— 兩個都塞得下的話字會太長，
            # 而流名在比較的那一邊已經寫出來了（`epi_others @ ref`）。
            return "%s · %s vs %s" % (self.title, who, versus)
        return "%s · %s on %s" % (self.title, who,
                                  str(first.get("stream") or "?"))

    def tab_tooltip(self) -> str:              # noqa: D102
        rows = self.rows()
        if not rows:
            return self.empty_reason()
        pairs = self._pairs()
        bits = []
        for r in rows:
            who = str(r.get("region") or "the whole image")
            line = "%s on %s" % (who, r.get("stream") or "?")
            if pairs.get(who):
                line += "  compared against %s" % pairs[who]
            if int(r.get("boxes") or 0) > 1:
                line += "  (%d boxes, one at a time)" % int(r.get("boxes") or 0)
            bits.append(line)
        marks = sorted((rows[0].get("marks") or {}))
        if marks:
            bits.append("showing: " + ", ".join(marks))
        return "\n".join(bits)

    # -- 畫 -----------------------------------------------------------------
    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
        rows = self.rows()
        if not rows:
            self._say_empty(p, rect)
            return
        body = rect
        band = None
        if self._batch_marks(rows[0]):
            body = QRectF(rect.left(), rect.top(), rect.width(),
                          rect.height() - self.BAND_H - 4)
            band = QRectF(rect.left(), body.bottom() + 4, rect.width(),
                          self.BAND_H)
        row_h = body.height() / float(len(rows))
        for i, r in enumerate(rows):
            self._paint_row(p, QRectF(body.left(), body.top() + i * row_h,
                                      body.width(), row_h - 3), r, i)
        if band is not None:
            self._paint_batch_band(p, band, rows[0])

    def _colour(self, index: int) -> QColor:
        """一塊區域一個顏色 —— **跟影像上的疊框、模板編輯器同一組**。

        不同一組的話，使用者在畫面上認得的那個綠色 ROI1，到了這裡是別的顏色，
        而沒有任何東西說得出它們是同一個。
        """
        return QColor(region_hex(index))

    def _paint_row(self, p: QPainter, band: QRectF, row: Dict[str, Any],
                   index: int) -> None:
        counts = [max(0, int(c)) for c in (row.get("bins") or [])]
        if not counts or band.height() < 12:
            return
        colour = self._colour(index)

        label = str(row.get("region") or row.get("stream") or "whole image")
        versus = self._pairs().get(str(row.get("region") or ""))
        if versus:
            label += "  vs  " + versus
        if int(row.get("boxes") or 0) > 1:
            # 一格一格量的時候畫的是**典型那一格**，而畫面必須說出這件事 ——
            # 不說的話這條分布看起來像整個區域的，那是兩個不同的東西。
            label += "  ·  typical box #%d of %d" % (int(row.get("box") or 0),
                                                     int(row.get("boxes") or 0))
        head = QRectF(band.left(), band.top(), band.width(), 13)
        p.setPen(colour)
        p.drawText(head, Qt.AlignLeft | Qt.AlignVCenter, label)
        p.setPen(QColor(TOKENS["text_hint"]))
        # 三個旋鈕丟掉了像素的時候要講出來（F18 第 4 步）：畫面上這條分布是
        # **留下來的那些**，而使用者需要知道那不是整塊。
        n, n_raw = int(row.get("n") or 0), int(row.get("n_raw") or 0)
        count = ("n=%d of %d px" % (n, n_raw)) if n_raw and n_raw != n \
            else ("n=%d px" % n)
        p.drawText(head, Qt.AlignRight | Qt.AlignVCenter,
                   "%s · %.1f%% saturated"
                   % (count, 100.0 * float(row.get("sat") or 0.0)))

        plot = QRectF(band.left(), head.bottom() + 1, band.width(),
                      max(8.0, band.bottom() - head.bottom() - 12))
        top = max(counts) or 1
        bw = plot.width() / float(len(counts))
        fill = QColor(colour)
        fill.setAlpha(90)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(fill))
        for k, c in enumerate(counts):
            h = (c / float(top)) * plot.height()
            p.drawRect(QRectF(plot.left() + k * bw, plot.bottom() - h,
                              max(1.0, bw - 0.4), h))
        p.setPen(QColor(TOKENS["border_default"]))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(plot.left(), plot.bottom()),
                   QPointF(plot.right(), plot.bottom()))

        # 0 與 255 —— 橫軸是灰階，而**每一條的尺都一樣**（不像 Spread 那邊
        # 每一排各有各的單位），所以刻度寫兩端就夠。
        axis = QRectF(plot.left(), plot.bottom() + 1, plot.width(), 11)
        p.setPen(QColor(TOKENS["text_hint"]))
        p.drawText(axis, Qt.AlignLeft | Qt.AlignVCenter, "0")
        p.drawText(axis, Qt.AlignRight | Qt.AlignVCenter, "255")

        self._paint_marks(p, plot, row, colour)

    def _paint_marks(self, p: QPainter, plot: QRectF, row: Dict[str, Any],
                     colour: QColor) -> None:
        """把勾選到的統計量標在這條分布上 —— **用它自己的形狀**。

        這是整塊面板最容易說謊的地方。三種統計量在灰階軸上的意思完全不同：

        ==========================  ==========================================
        中位數 / 平均 / 修剪平均     一個**位置** → 整條實線
        最小 / 最大 / 分位數         一個**位置** → 貼著底的短刻度
        MAD / 標準差 / IQR           一個**寬度** → 中心兩側的一段淡帶
        ==========================  ==========================================

        第三種畫成一條線的話（第一版就是），`glv_mad = 65` 會在灰階 65 的地方
        畫一條線 —— 那裡什麼都沒有，而畫面上沒有任何東西說得出那條線是假的。
        寬度沒有中心可以掛的時候（只勾了 MAD、沒勾中位數）就**不畫** ——
        「這個數字沒有畫得出來的位置」是一個誠實的答案。

        剩下那幾個（偏度、峰度、熵、雙峰、飽和比例、亮度佔比）的單位根本不是
        灰階，一律不畫；它們的值在特徵表上。唯一的例外是 ``glv_above<NN>``：
        畫的是**那個門檻**（虛線），不是它的值 —— 門檻真的在灰階軸上。
        """
        marks = {str(k): v for k, v in (row.get("marks") or {}).items()}
        ink = QColor(theme.readable_on(colour.name(), TOKENS["bg_surface"]))

        def as_gray(mid):
            try:
                v = float(marks[mid])
            except (KeyError, TypeError, ValueError):
                return None
            return v if 0.0 <= v <= 255.0 else None

        def x_at(v):
            return plot.left() + (v / 255.0) * plot.width()

        centre = next((as_gray(m) for m in sorted(marks)
                       if m.startswith(self.CENTRE_MARKS)
                       and as_gray(m) is not None), None)

        # 先畫寬度（淡帶），線才不會被蓋掉。
        for mid in sorted(marks):
            if not mid.startswith(self.WIDTH_MARKS) or centre is None:
                continue
            w = as_gray(mid)
            if w is None or w <= 0:
                continue
            lo, hi = max(0.0, centre - w), min(255.0, centre + w)
            wash = QColor(ink)
            wash.setAlpha(46)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(wash))
            p.drawRect(QRectF(x_at(lo), plot.top() + plot.height() * 0.30,
                              x_at(hi) - x_at(lo), plot.height() * 0.70))
            p.setBrush(Qt.NoBrush)

        for mid in sorted(marks):
            if mid.startswith(self.CENTRE_MARKS):
                v = as_gray(mid)
                if v is None:
                    continue
                p.setPen(QPen(ink, 1.6))
                p.drawLine(QPointF(x_at(v), plot.top()),
                           QPointF(x_at(v), plot.bottom()))
            elif mid.startswith(self.POSITION_MARKS):
                v = as_gray(mid)
                if v is None:
                    continue
                p.setPen(QPen(ink, 1.1))
                p.drawLine(QPointF(x_at(v), plot.bottom() - plot.height() * 0.34),
                           QPointF(x_at(v), plot.bottom()))
            else:
                thr = algo_glv.above_of(mid)      # glv_above<NN>：畫門檻不畫值
                if thr is None:
                    continue
                p.setPen(QPen(ink, 1.1, Qt.DashLine))
                p.drawLine(QPointF(x_at(float(thr)), plot.top()),
                           QPointF(x_at(float(thr)), plot.bottom()))
        p.setPen(Qt.NoPen)

    # -- 整批那一條帶子 -----------------------------------------------------
    def _batch_marks(self, row: Dict[str, Any]) -> Optional[Tuple[str, float, float]]:
        """(特徵名, 這一顆的值, 百分位) —— 沒跑過整批就回 None。"""
        prefix = str(row.get("prefix") or "")
        for mid in sorted((row.get("marks") or {})):
            name = "%s_%s" % (prefix, mid) if prefix else mid
            vals = self.feature_values(name)
            here = self.this_value(name)
            if len(vals) >= 2 and here is not None:
                below = sum(1 for v in vals if v < here)
                return (name, here, 100.0 * below / float(len(vals)))
        return None

    def _paint_batch_band(self, p: QPainter, box: QRectF,
                          row: Dict[str, Any]) -> None:
        """整批的資訊縮成一條帶子：**這一顆落在整批的哪裡**。

        它跑完才有，所以它不能是這塊面板的主體 —— 那正是 Spread 搬家的理由。
        一條帶子放得下的東西剛好就是它真正回答得了的問題。
        """
        got = self._batch_marks(row)
        if not got:
            return
        name, here, pct = got
        p.setPen(QColor(TOKENS["text_hint"]))
        text = "%s = %s · top %d%% of the batch" % (
            name, _fmt(here), int(round(100.0 - pct)))
        left = QRectF(box.left(), box.top(), box.width() * 0.62, box.height())
        p.drawText(left, Qt.AlignLeft | Qt.AlignVCenter, text)

        track = QRectF(box.right() - box.width() * 0.34, box.center().y() - 3,
                       box.width() * 0.34, 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(TOKENS["border_default"])))
        p.drawRoundedRect(track, 3, 3)
        x = track.left() + (pct / 100.0) * track.width()
        p.setBrush(QBrush(QColor(TOKENS["danger_text"])))
        p.drawEllipse(QRectF(x - 3.5, track.center().y() - 3.5, 7, 7))
        p.setBrush(Qt.NoBrush)


class InputInspector(Inspector):
    """Load images：**哪一頁變成哪一條流**，以及每一頁載進來長什麼樣。

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

    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
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
    """`roi_from_mask`：**這一顆對到了哪幾層**、各幾塊、多大。

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

    title = "GDS layers"

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

    def paintEvent(self, _e) -> None:          # noqa: D102 - Qt hook
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
        f.setPointSizeF(max(7.5, f.pointSizeF() - 0.5))
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
    分布（`paired` / `match_dist_nm` 整批長什麼樣）是 `MeasureInspector` 已經在
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
                bits.append("no match in '%s' — recorded as paired = 0"
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
        except Exception:                  # noqa: BLE001 — 提示不准擋路
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

    def paint_body(self, p: QPainter, rect: QRectF) -> None:   # noqa: D102
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
    "cd_measure": MeasureInspector,
    "focus_quality": MeasureInspector,
    "roi_snr": MeasureInspector,
    "roi_from_mask": GdsInspector,
    "pair_source": PairInspector,
    # 對圖的分數只有**跟整批比**才讀得懂：0.62 是高是低要看其他顆長什麼樣。
    "align_to": MeasureInspector,
    # 寫回前一定先預覽變更（M5 的硬性規則，F16 Stage 5c 搬過來的）。
    "output_klarf": WriteBackInspector,
}


def inspector_for(step_key: str) -> Optional[type]:
    return INSPECTORS.get(str(step_key or ""))

# d4t Studio — 儀表的共用底座（2026-09-24 從 inspectors.py 拆出）.
"""每張卡的儀表共用的那一層：:class:`Inspector` 基底、數字格式、共用 header。

為什麼拆出來：`inspectors.py` 長到 3,669 行、19 個類別，最大的兩個面板
（GLV、CD）各六百行。拆的時候它們都要這一層，而把基底留在 `inspectors.py`
會變成互相 import。註冊表（`INSPECTORS`／`BY_METHOD`／`inspector_for`）仍然
住在 `inspectors.py`，那是唯一的入口。
"""
from __future__ import annotations

import math
import traceback
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetricsF,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from d4t.core.log import swallowed

from .numbers import format_feature_value, format_feature_value_short
from .theme import TOKENS


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
        """沒有資料時要說的話 —— 空白面板本身不是訊息。

        這一句是**退路**，不是家：每個註冊過的面板都要自己講（有 registry
        全掃的測試守著）—— 泛用的一句話答不出「所以我現在該做什麼」
        （推廣鐵則）。
        """
        return ("Nothing to show for this card yet - select a defect, or "
                "run a trial.")

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

    def _label_rows(self) -> List[Dict[str, Any]]:
        """這張面板一列一份的那組記錄 —— 只給 :meth:`_row_label` 用。

        預設空的：沒有覆寫的面板不是多列的，標題本來就不必分辨誰是誰。
        """
        return []

    def _row_label(self, note: Dict[str, Any]) -> str:
        """這一列的標題 —— 只說出真正把它跟別列分開的那件事（見 `row_labels`）。"""
        rows = self._label_rows() or [note]
        labels = row_labels(rows)
        key = (str(note.get("region") or ""), str(note.get("stream") or ""))
        for row, label in zip(rows, labels):
            if row is note or (str(row.get("region") or ""),
                               str(row.get("stream") or "")) == key:
                return label
        return str(note.get("region") or note.get("stream") or "whole image")

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

    def paintEvent(self, _e) -> None:  # Qt hook
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
        except Exception:  # 見 docstring
            traceback.print_exc()
            try:
                p.setPen(QColor(TOKENS["danger_text"]))
                p.drawText(QRectF(self.rect()).adjusted(10, 10, -10, -10),
                           Qt.AlignCenter | Qt.TextWordWrap,
                           "This panel could not be drawn (see the terminal). "
                           "Everything else still works.")
            except Exception:  # 連錯誤都畫不出來
                swallowed("inspectors.paintEvent")
        finally:
            p.end()

    def paint_body(self, p: QPainter, rect: QRectF) -> None:
        """子類畫這裡（``rect`` 已經扣掉外框與留白）。"""


def _short_number(v: float, signed: bool = False) -> str:
    """畫**在影像上**的短數字：`26.1` / `66` / `0.06`。

    ⚠ **F52 起它是 `numbers.format_feature_value_short` 的別名**，而那一支
    修好了一個 bug：舊版把 ``0.000312`` 印成 ``0.00`` —— 讀起來是**零**，
    而這個標記畫在影像上，正是使用者盯著看的地方。

    圖上的字只有 10 px 高，`SNR 66` 比 `SNR 66.116` 好讀 —— 所以短版是**刻意
    的例外**，而例外的邊界寫在那一支上：只有畫在影像上的標記用它。
    """
    return format_feature_value_short(v, signed=signed)


def _fmt(v: float) -> str:
    """儀表面板上的數字。

    ⚠ **F52 起它是 `numbers.format_feature_value` 的別名。** 以前是自己一份
    （``%.3g`` / ``%.3f`` / ``%.1f`` 三段），於是同一顆的同一個數字在儀表上
    與在結果表上不一樣。
    """
    return format_feature_value(v)


def row_labels(notes: Sequence[Dict[str, Any]]) -> List[str]:
    """一組 note → 每一列的標題：**只說出真正把它們分開的那件事**。

    量測卡的面板一列一份記錄，而「一份」可以是一個區域，也可以是同一個區域的
    另一條影像流（`source` 是複數型別，接第二條線就多一份 —— 見
    ``docs/USING-CD.md`` §2）。列標題原本一律寫區域名，於是
    **同一個區域接了 test 與 ref 兩條流時，兩列標的是同一個名字**，
    而且顏色也一樣（顏色照區域給）—— 畫面上沒有任何東西說得出哪一列是哪一條。
    2026-08-22 在 `0822test/mgext` 的 recipe 上實際看到：兩列都寫 ``mg_center``，
    一列 9.17 px、一列 8.50 px，而使用者要相減的正是這兩個數字。

    規則就一句：**把不變的那一半省掉。**

    * 區域都一樣、流不一樣 → 只寫流名
    * 流都一樣、區域不一樣 → 只寫區域名（＝ 原本的行為，多區域是常態）
    * 兩個都不一樣 → 兩個都寫

    ⚠ **顏色不動。** 顏色的意思是「影像上那個框」（`GlvInspector._colour` 立下
    的規矩），兩條流量的是同一個框 —— 給它們兩個顏色的話，面板上的顏色就不再
    對得回影像上的框，那比標題重複糟得多。分辨兩條流是**標題**的工作。
    """
    rows = list(notes)
    if not rows:
        return []
    regions = [str(n.get("region") or "") for n in rows]
    streams = [str(n.get("stream") or "") for n in rows]
    many_regions = len(set(regions)) > 1
    many_streams = len(set(streams)) > 1
    out = []
    for region, stream in zip(regions, streams):
        who = region or "whole image"
        if many_streams and not many_regions:
            out.append(stream or who)
        elif many_streams and many_regions:
            out.append("%s @ %s" % (who, stream) if stream else who)
        else:
            out.append(who)
    return out


def note_header(note: Dict[str, Any], label: str = "",
                unit: str = "px") -> Tuple[str, str]:
    """共用 header 的兩半（PR-2 2f）：``(左, 右)``。

    左＝**來源流永遠在**（`row_labels` 只在流是分辨軸時印它，而共用 header
    的約定是「每個面板都講得出來源流」）＋ 分辨用的那一半（``label``，仍由
    `row_labels` / `_row_label` 產 —— 分辨邏輯只有那一份）。已含流名就不
    重複。右＝ ``n=… px``（旋鈕丟過像素時 ``n=… of … px``）。
    """
    stream = str(note.get("stream") or "")
    label = str(label or "")
    if stream and stream not in label:
        left = "%s · %s" % (stream, label) if label else stream
    else:
        left = label or "the image"
    n = int(note.get("n") or 0)
    n_raw = int(note.get("n_raw") or 0)
    right = ("n=%d of %d %s" % (n, n_raw, unit)) if n_raw and n_raw != n \
        else ("n=%d %s" % (n, unit))
    return left, right


def paint_note_header(p: QPainter, band: QRectF, note: Dict[str, Any], *,
                      colour: QColor, label: str = "", tail: str = "",
                      tail_colour: Optional[QColor] = None,
                      trust: str = "", unit: str = "px") -> float:
    """畫共用 header 一列，回它的高度。

    「來源流 · 區域（有才顯示）· n · 可信度旗標」：左半 `note_header`、
    ``tail``（GLV 的「vs 參照」那一段）接在左半後面用自己的顏色、右半 =
    n ＋（有的話）``trust``（GLV 傳 sat%、Subtract 傳 clipped%）。
    高度是 ``max(13, 字高)`` —— 13 是老的寫死值，字高不夠時 ``band_a_center``
    的底線會被切掉（CD 那邊踩過，教訓收進這裡一次）。
    """
    left, right = note_header(note, label, unit)
    fm = QFontMetricsF(p.font())
    head_h = max(13.0, fm.height())
    head = QRectF(band.left(), band.top(), band.width(), head_h)
    right_text = "%s · %s" % (right, trust) if trust else right
    left_box, tail_box, right_box = header_boxes(
        head, fm.horizontalAdvance(left), fm.horizontalAdvance(tail) if tail
        else 0.0, fm.horizontalAdvance(right_text))
    p.setPen(colour)
    p.drawText(left_box, Qt.AlignLeft | Qt.AlignVCenter,
               fm.elidedText(left, Qt.ElideRight, left_box.width()))
    if tail and tail_box.width() > 0:
        p.setPen(tail_colour if tail_colour is not None
                 else QColor(TOKENS["text_secondary"]))
        p.drawText(tail_box, Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(tail, Qt.ElideRight, tail_box.width()))
    p.setPen(QColor(TOKENS["text_hint"]))
    p.drawText(right_box, Qt.AlignRight | Qt.AlignVCenter,
               fm.elidedText(right_text, Qt.ElideLeft, right_box.width()))
    return head_h


#: 共用 header 左右兩段之間至少留這麼寬（px）—— 兩段字貼在一起讀起來像一句。
HEADER_GAP = 8.0


def header_boxes(head: QRectF, left_w: float, tail_w: float,
                 right_w: float) -> Tuple[QRectF, QRectF, QRectF]:
    """把 header 那一列切成**互不重疊**的三塊：左、尾、右（F99 P0-2）。

    以前左右兩段各自畫進同一個矩形（一個靠左、一個靠右），而沒有一方讓出
    寬度 —— 面板窄到 200 px 的時候「single · on_pattern」跟
    「n=81 px · 0.0% saturated」直接疊在一起，三張直方圖每一張都是。那是
    2026-09-08 外部評審在預設版面上一眼看到的第一個 bug，而它待在調參數時
    視線停留最久的地方。

    規則：**右段（n、可信度）先拿它要的寬度**（那兩個數字是「這塊還能不能
    信」，比左邊的名字更不能少），但最多拿一半；左段拿剩下的，尾段（GLV 的
    「vs 參照」）只在左段講完之後還有位子才畫。每一塊都可能比字短 —— 那時候
    呼叫端用 ``elidedText`` 縮，而不是讓字溢出到隔壁那一塊。
    純幾何、不碰 QPainter，所以測試不用開視窗就能量。
    """
    width = max(0.0, float(head.width()))
    right_take = min(float(right_w), width * 0.5)
    left_room = max(0.0, width - right_take - (HEADER_GAP if right_take else 0.0))
    left_take = min(float(left_w), left_room)
    tail_take = min(float(tail_w), max(0.0, left_room - left_take))
    left_box = QRectF(head.left(), head.top(), left_take, head.height())
    tail_box = QRectF(head.left() + left_take, head.top(), tail_take,
                      head.height())
    right_box = QRectF(head.right() - right_take, head.top(), right_take,
                       head.height())
    return left_box, tail_box, right_box

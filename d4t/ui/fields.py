# 參數表單上那一列一列的編輯器 — 從 widgets.py 搬出來 2026-09-08 (U7).
"""一格參數長什麼樣：那一列（`_ParamRow`）、滑桿、以及各種專用編輯器。

**每個參數的白話 `help` 一定要看得到** —— 推廣鐵則，而它的執行機構就在
`_ParamRow`。**把 `min`/`max` 填好，滑桿是免費的**（F7-8）：使用者是一邊拖
一邊看影像決定值的，「先想好一個數字再輸入」那個順序是反的。

住在這裡的專用編輯器：影像流／區域的接線格（唯讀 —— 來源只在畫布上拉線
決定）、`channel_map` 的表、模板、`cell_rois`、色調曲線、圖表樣式與規格。

U7 那一刀。這一份是**純搬移**：每一行都是原封搬過來的，一個字都沒有改。
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFontMetricsF, QIcon, QPainter, QPainterPath, QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from . import fit_screen
from . import region_words
from . import strings
from . import theme
from .buttons import small_button
from .icons import draw_glyph_icon
from .theme import TOKENS, region_hex

__all__ = [
    "ChannelMapField", "TemplateField", "CellRoisField", "CurveField",
    "CurveEditor", "CurveDialog", "ChartStyleField", "ChartSpecField",
    "StreamPicker", "MultiChoicePicker", "ProfilePanel",
    "glyph_icon", "region_dot_icon",
]

# --------------------------------------------------------------------------- #
#: 浮點滑桿的內部刻度數。滑桿只吃 int，所以 min..max 一律映射到 0..這個數。
#: 1000 格對 gamma（0.1–5）約是 0.005 一格 —— 拖起來連續，又不會抖到看不出。
_SLIDER_TICKS = 1000

#: 整數參數的滑桿上限跨度。超過這個跨度就不給滑桿（一格好幾十，拖了也沒用），
#: 留純數字框比較誠實。
_SLIDER_MAX_INT_SPAN = 5000



#: 整數參數的滑桿上限跨度。超過這個跨度就不給滑桿（一格好幾十，拖了也沒用），
#: 留純數字框比較誠實。
_SLIDER_MAX_INT_SPAN = 5000


class _HintLabel(QLabel):
    """列面上那句「非讀不可」的字（錯誤／不生效註記）。

    歷史：F7-15 它是常駐的參數說明（一行、hover 攤開），2026-08-14 說明整段
    搬進 tooltip —— hover 攤開/收合跟著滑鼠此起彼落地閃，比一面牆更亂。
    現在這個 label 平常是隱藏的，只在「有一句話必須讀完」時出現，而且出現
    就是整段（``set_expanded(True)``）。收合模式留著給還需要它的呼叫端；
    收合時切字自己算（``elidedText``），不交給 Qt 裁 —— Qt 會硬切在字的
    中間，看起來像畫面壞掉（同 canvas 的 ``_draw_elided``）。
    """

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("paramHint")
        self._full = str(text)
        self._expanded = False
        self.setWordWrap(False)
        self._sync()

    def full_text(self) -> str:
        return self._full

    def set_full_text(self, text: str) -> None:
        # 翻譯層擺在共用的那一支（U14）：**每一句參數說明都流過這裡**
        # （`ParamSpec.help` 那一句、卡片自己的一行說明、「不生效」註記），
        # 所以包這一次就涵蓋整個設定區，而呼叫端一個字都不用改。
        #
        # 組出來的句子（`"⚠ " + msg`）在 catalog 裡查不到 → 回原句，
        # 那正是要的行為：漏翻的代價是「那句話沒有被翻譯」。
        self._full = strings.tr(str(text))
        self._sync()

    def set_expanded(self, expanded: bool) -> None:
        if bool(expanded) != self._expanded:
            self._expanded = bool(expanded)
            self._sync()

    def is_expanded(self) -> bool:
        return self._expanded

    def resizeEvent(self, e) -> None:  # Qt hook
        super().resizeEvent(e)
        if not self._expanded:
            self._sync()

    def _sync(self) -> None:
        if self._expanded:
            self.setWordWrap(True)
            super().setText(self._full)
            return
        self.setWordWrap(False)
        w = max(40, self.width())
        super().setText(self.fontMetrics().elidedText(
            self._full, Qt.ElideRight, w))


#: 這幾種編輯器是**一整塊**，不是一行 —— 它們那一列的名字要對齊到最上面。
#:
#: 為什麼要列出來而不是量 widget 的高度：``sizeHint`` 在建構的當下還沒定案
#: （膠囊要排版完才知道會不會換行），量到的會是一個還沒長好的數字。
_BLOCK_EDITORS = ("metric_chips", "metric_choice", "multi_choice",
                  "chip_choice", "curve", "template",
                  "channel_map", "cell_rois")


class _ParamRow(QFrame):
    """一個參數 = 一列（名稱 + 滑桿 + 數字框）。說明住在 tooltip 裡。

    為什麼有上下界的數字都配一支滑桿（F7-8）
    ----------------------------------------
    「gamma 要填多少」對不會寫 code 的人是個沒有答案的問題 —— 他要的是
    **一邊拖一邊看圖**。數字框逼人先想好一個數字再輸入，那個順序是反的。

    數字框沒有被拿掉，是刻意的：滑桿負責找到大概的位置，數字框負責記錄與
    重現（recipe 是要交接給別人的）。兩邊雙向綁定，改哪一邊另一邊都會跟上。

    說明文字為什麼不畫在列的下面（2026-08-14，取代 F7-15 的 hover 攤開）
    ------------------------------------------------------------------
    F7-15 把說明收成一行、hover 才攤開 —— 但攤開/收合跟著滑鼠此起彼落，
    使用者的形容是「移過去會顯示、移走又消失，很亂」。說明整段搬進
    tooltip（整列都感應，停上去就看得到全文），列面上只留兩種**非讀不可**
    的字：紅色錯誤（驗證擋下來的原因）與「這一格現在不生效」的調淡註記。
    那兩種不是說明，是狀態 —— 出現就攤開整段，不玩收合。
    """

    def __init__(self, spec: Dict[str, Any], editor: QWidget,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.spec = spec
        self.editor = editor
        self.slider: Optional[QSlider] = None
        self._dim_note = ""
        self.setObjectName("paramRow")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 6)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        # 顯示名優先用 ``label``（F7-9）。``name`` 是 recipe JSON 的鍵，
        # 對使用者來說 ``range_from`` 不是一句話，"Borrow range from" 才是。
        self.name_label = QLabel(str(spec.get("label") or spec.get("name", "")))
        self.name_label.setObjectName("paramLabel")
        self.name_label.setMinimumWidth(104)
        # **重複自己的小標題的那個名字要拿掉。** CD 的膠囊那一格 `label` 與
        # `section` 都是 "Report"，於是畫面上同一個字出現兩次 —— 而下面那條
        # 對齊的規矩會讓它落在群組區塊的**中間那一列**旁邊，讀起來像是一個叫
        # 「Report」的群（截圖出來才看到：Size 的第二排看起來屬於它）。
        # 比對前先剝掉小標題的編號（"3 · Compare with" → "Compare with"，
        # F32）：編號是段落的座標不是名字，留著比的話「段標題正下方再寫一次
        # 同名列標籤」這種重複只有沒編號的段抓得到。
        label_txt = str(spec.get("label") or "").strip()
        section_txt = re.sub(r"^\d+\s*·\s*", "",
                             str(spec.get("section") or "").strip())
        self._label_is_echo = bool(label_txt and label_txt == section_txt)
        if self._label_is_echo:
            self.name_label.hide()
        else:
            top.addWidget(self.name_label)
        # **一整塊的編輯器，名字要對齊到最上面。** 垂直置中的話那個名字會落在
        # 區塊中間的某一列上，而那一列有它自己的意思（群名、第幾條曲線…）。
        if str(spec.get("type") or "") in _BLOCK_EDITORS:
            top.setAlignment(self.name_label, Qt.AlignTop)
            self.name_label.setContentsMargins(0, 6, 0, 0)
        if str(spec.get("type") or "") == "chip_choice":
            # **長的列名要換行，不要把膠囊擠扁**（F68 第二輪）。
            # 「Take the up-and-down stripes that are」把那一列的名字撐到
            # 三百多 px，剩給七顆膠囊的寬度不到一半 —— 它們於是排成五排
            # 參差不齊的東西（render 出來才看到）。名字是一欄，膠囊是一塊。
            self.name_label.setWordWrap(True)
            self.name_label.setMaximumWidth(152)

        self.slider = _make_slider(spec, editor)
        if self.slider is not None:
            top.addWidget(self.slider, 1)
            editor.setMaximumWidth(96)
            top.addWidget(editor, 0)
        else:
            top.addWidget(editor, 1)
        lay.addLayout(top)

        self.hint = _HintLabel(strings.tr(str(spec.get("help", ""))), self)
        self.hint.setProperty("error", "false")
        # 出現的時候一定是「必須讀完的一句話」（錯誤／不生效註記），
        # 所以永遠整段攤開；平常整列收起來只有一行高。
        self.hint.set_expanded(True)
        self.hint.hide()
        lay.addWidget(self.hint)

        # 說明全文住在 tooltip：整列（含名稱與空白處）都感應得到。
        tip = strings.tr(str(spec.get("help", "")))
        if tip:
            self.setToolTip(tip)
            self.name_label.setToolTip(tip)

    def set_error(self, msg: Optional[str]) -> None:
        if msg:
            self.hint.set_full_text("⚠ " + str(msg))
            self.hint.setProperty("error", "true")
            self.hint.setStyleSheet(
                "color:%s; font-size:%s; font-weight:600;"
                % (TOKENS["danger_text"], TOKENS["font_small"]))
            self.hint.show()
        else:
            self.hint.setProperty("error", "false")
            self._show_dim_note_or_hide()
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)

    def has_error(self) -> bool:
        return self.hint.property("error") == "true"

    def hint_visible(self) -> bool:
        """列面上現在有沒有一句攤開的字（**明確狀態**，不問 ``isVisible()``）。"""
        return not self.hint.isHidden()

    def set_dimmed(self, dimmed: bool, why: str = "") -> None:
        """把整列調淡（值還在、還能改，只是現在不生效）。

        用在「另一個參數接管了這一個」的情況 —— 例如畫了曲線之後 gamma
        就不再被用到。不 disable 是刻意的：使用者可能只是想比較兩種做法，
        把它鎖死會逼他先把曲線拉平才改得動 gamma。
        """
        self.setProperty("dimmed", "true" if dimmed else "false")
        self.setEnabled(True)
        self.name_label.setStyleSheet(
            "color:%s;" % (TOKENS["text_disabled"] if dimmed
                           else TOKENS["text_primary"]))
        self._dim_note = str(why) if (dimmed and why) else ""
        if not self.has_error():
            self._show_dim_note_or_hide()

    def _show_dim_note_or_hide(self) -> None:
        """沒有錯誤的時候，列面上唯一可能出現的字是「不生效」註記。"""
        if self._dim_note:
            self.hint.set_full_text("· " + self._dim_note)
            self.hint.setStyleSheet(
                "color:%s; font-size:%s; font-style:italic;"
                % (TOKENS["text_disabled"], TOKENS["font_small"]))
            self.hint.show()
        else:
            self.hint.set_full_text(str(self.spec.get("help", "")))
            self.hint.setStyleSheet("color:%s; font-size:%s;"
                                    % (TOKENS["text_hint"], TOKENS["font_small"]))
            self.hint.hide()


def _make_slider(spec: Dict[str, Any], editor: QWidget) -> Optional[QSlider]:
    """有上下界的 int / float 參數 → 一支跟數字框雙向綁定的滑桿。

    回 ``None`` 表示這個參數不適合滑桿（沒界、跨度是 0、或整數跨度大到
    一格好幾十）。這樣新卡片只要把 min/max 填好就自動有滑桿，
    不必逐張卡去 UI 這邊登記。
    """
    ptype = str(spec.get("type", ""))
    lo, hi = spec.get("min"), spec.get("max")
    if ptype not in ("int", "float") or lo is None or hi is None:
        return None
    lo, hi = float(lo), float(hi)
    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
        return None

    s = QSlider(Qt.Horizontal)
    s.setObjectName("paramSlider")
    s.setToolTip(str(spec.get("help", "")))
    guard = {"busy": False}

    if ptype == "int":
        if hi - lo > _SLIDER_MAX_INT_SPAN:
            return None
        s.setRange(int(lo), int(hi))
        s.setValue(int(editor.value()))

        def from_slider(v: int) -> None:
            if guard["busy"]:
                return
            guard["busy"] = True
            editor.setValue(int(v))
            guard["busy"] = False

        def from_box(v: int) -> None:
            if guard["busy"]:
                return
            guard["busy"] = True
            s.setValue(int(v))
            guard["busy"] = False
    else:
        s.setRange(0, _SLIDER_TICKS)
        span = hi - lo

        def to_tick(v: float) -> int:
            return int(round((float(v) - lo) / span * _SLIDER_TICKS))

        s.setValue(to_tick(editor.value()))

        def from_slider(v: int) -> None:  # 兩型別各一份
            if guard["busy"]:
                return
            guard["busy"] = True
            editor.setValue(lo + (float(v) / _SLIDER_TICKS) * span)
            guard["busy"] = False

        def from_box(v: float) -> None:
            if guard["busy"]:
                return
            guard["busy"] = True
            s.setValue(to_tick(v))
            guard["busy"] = False

    # 兩邊互相回寫會無限來回（float 還會因為取整而每次都差一點點），
    # 所以用 guard 擋住「因我而起的那一次回呼」。
    s.valueChanged.connect(from_slider)
    editor.valueChanged.connect(from_box)
    return s


class ProfilePanel(QWidget):
    """投影定位的曲線面板（F7-11）：曲線、轉折線、選中的那一段、中心線。

    為什麼這張卡沒有這個面板就不成立
    --------------------------------
    「敏感度要調多少」對不會寫 code 的人是一個沒有答案的問題 —— 除非他看得到
    曲線、看得到目前抓到幾條線、看得到抓到的線是不是落在他預期的地方。
    沒有這個面板，這張卡就只是另一個要盲填的數字。

    **畫的資料來自引擎那一次計算**（step 卡把它放進 ``ctx.meta["profiles"]``），
    UI 不自己再算一次。不然「畫面上的框」跟「真的量下去的框」會不一樣，
    而那種 bug 幾乎不可能靠肉眼發現。
    """

    #: 量測尺按著時，這一段量到哪裡（axis, 起, 迄；單位是**影像像素**）。
    #: 上面那張影像靠它同步標出同一段 —— 見 :meth:`ImageView.set_measure`。
    measure_changed = Signal(str, float, float)
    #: 放開了。標記要跟著消失，它是「現在正在量」的回饋不是註記。
    measure_ended = Signal()
    #: 「把量到的間距填進參數格」（axis, pitch, 第二個 pitch）。
    #: 使用者原話：「有辦法自動 measure 填入左側數值嗎」。曲線本來就知道答案，
    #: 而要他看著面板上的數字再手動打一次，是在製造一個可以打錯的機會。
    pitch_requested = Signal(str, float, float)
    #: 「用這一種材質」（axis, select 的值）—— 使用者**點了曲線上的一根條紋**。
    #:
    #: 為什麼這件事要能用點的（F11 Region-2b）：使用者的話是「能用圖就用圖」，
    #: 而 ``second_brightest`` 這個詞本身不告訴他任何事 —— 「哪一組是第二亮的」
    #: 是一個只有看圖才答得出來的問題，而圖就在這裡。分群由引擎給
    #: （``algo/grid.band_groups``），面板不自己分。
    select_requested = Signal(str, str)

    _EMPTY = "(select a Profile card to see its curve)"

    #: 每一群的底色（依群號輪流）。用**顏色**而不是深淺：深淺會跟曲線下面的
    #: 灰階混在一起，而這裡要講的是「這幾根是同一種東西」。
    #: ⚠ 寫的是 **token 名**，畫的時候才取值（F99 P2-2）。以前這裡是五個
    #: 寫死的 hex —— 它們是 accent／warning／seg_adc／success／danger 的
    #: **複本**，而複本不跟主題走：暗色主題下這幾根柱子穿的還是亮色的衣服。
    GROUP_COLORS = ("accent", "warning", "seg_adc", "success", "danger")

    #: 拖多少個取樣點以內算「點一下」而不是「拖了一段」。
    CLICK_SLOP = 1.5

    #: 底部那條分群色帶有多高（畫面像素）。
    GROUP_BAR = 5.0

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._data: Dict[str, Any] = {}
        self._name = ""
        self._ruler: Optional[Tuple[float, float]] = None
        self._pressed_at: Optional[float] = None
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip(
            "Gray level projected along the scan direction.\n\n"
            "The thin upright lines are the edges found in this image. The "
            "shaded blocks are the stripes the card will actually use - which "
            "is not the same thing: the edges are refined to sub-pixel, and if "
            "you filled in a pitch the stripes are then snapped onto that "
            "regular grid. So the blocks can sit a pixel or two off the lines, "
            "and the summary says how far.\n\n"
            "The dashed line marked 'defect' is the middle of the patch, which "
            "is where the tool put the defect - a marker, not a setting.\n\n"
            "Click a stripe to use that material — the colours are the groups "
            "the card found, and the solid one is the group it is using now.\n\n"
            "Press and drag across the curve to measure: the green band shows "
            "the same stretch on the image above, and the readout gives the "
            "distance in pixels - and the pitch, if you dragged across more "
            "than one stripe. Let go to clear it.")

        # 「量給我填」。浮在面板上（同 kind="icon" 那幾顆的理由：這裡沒有卡片
        # 當底色）。只有在**它會改變什麼**的時候才出現 —— 見 _sync_button。
        # ⚠ shape 一定要 "wide"：square 的 QSS 是 max-width 22px，文字按鈕
        # 放進去只剩「Use 4…」—— 使用者回報「只看得到一半的數字」就是它。
        self._fill_btn = small_button("", shape="wide", kind="icon",
                                      parent=self)
        self._fill_btn.setVisible(False)
        self._fill_btn.clicked.connect(self._request_pitch)

    # -- public ------------------------------------------------------------
    def set_data(self, name: str, data: Optional[Dict[str, Any]]) -> None:
        self._name = str(name or "")
        self._data = dict(data or {})
        self._sync_button()
        self._end_ruler()
        self.setCursor(Qt.CrossCursor if self.has_data() else Qt.ArrowCursor)
        self.update()

    def has_data(self) -> bool:
        return bool(self._data.get("profile"))

    # -- 「量給我填」 ------------------------------------------------------
    def measured_pitches(self) -> Tuple[float, float]:
        """這條曲線量到的間距（第二個是 0 代表不交錯）。"""
        return (float(self._data.get("pitch_measured") or 0.0),
                float(self._data.get("pitch_measured_2") or 0.0))

    def fill_button_text(self) -> str:
        """按鈕上的字（空字串 = 這時候不該有按鈕）。"""
        a, b = self.measured_pitches()
        if a < 2.0:
            return ""
        used = [float(v) for v in (self._data.get("pitches_used") or [])]
        want = [round(v, 1) for v in ((a, b) if b >= 2.0 else (a,))]
        if [round(v, 1) for v in used] == want:
            return ""            # 已經是這個值了 —— 按了什麼都不會變
        return ("Use %s px" % " / ".join("%.1f" % v for v in want))

    def _request_pitch(self) -> None:
        a, b = self.measured_pitches()
        if a >= 2.0:
            self.pitch_requested.emit(self.axis(), a, b if b >= 2.0 else 0.0)

    def _sync_button(self) -> None:
        text = self.fill_button_text()
        self._fill_btn.setText(text)
        self._fill_btn.setVisible(bool(text))
        self._fill_btn.setToolTip(
            "Put the spacing measured on this curve into the pitch box for "
            "this direction. Use it when you do not know the pitch from the "
            "layout - once it is filled in, the card can check what it finds, "
            "fill in stripes that were too faint, and lock on from a single "
            "stripe." if text else "")
        if text:
            self._fill_btn.adjustSize()
            self._place_button()

    def _place_button(self) -> None:
        b = self._fill_btn
        b.move(max(2, self.width() - b.width() - 10), 4)

    def resizeEvent(self, e) -> None:  # Qt hook
        super().resizeEvent(e)
        self._place_button()

    # -- ruler (F8) --------------------------------------------------------
    def axis(self) -> str:
        """這條曲線是哪一軸的投影（``"x"`` 直的條紋／``"y"`` 橫的）。"""
        return str(self._data.get("axis") or "")

    def ruler_span(self) -> Optional[Tuple[float, float]]:
        """量測尺現在夾住的那一段（起 ≤ 迄，影像像素）；沒在量就 None。"""
        if self._ruler is None:
            return None
        a, b = self._ruler
        return (min(a, b), max(a, b))

    def ruler_text(self) -> str:
        """量測尺的讀數。

        為什麼不只講「幾個像素」
        ----------------------
        使用者拉這一把的目的多半是**問出 pitch**（他不知道 pitch 是多少，
        所以才要量）。而「量一個週期」是所有量法裡最不準的一種 —— 兩端各差
        一個像素，pitch 就差兩個。橫跨好幾根條紋再除以根數，誤差就被根數除掉。
        所以只要這一段裡有兩根以上抓到的條紋，就順便把 pitch 算給他。
        """
        span = self.ruler_span()
        if span is None:
            return ""
        a, b = span
        bits = ["%.1f px" % (b - a)]
        mids = self._centers_in(a, b)
        if len(mids) >= 2:
            bits.append("%d stripes" % len(mids))
            bits.append("pitch %.1f px" % ((mids[-1] - mids[0]) / (len(mids) - 1)))
        return " · ".join(bits)

    def groups(self) -> List[int]:
        """每一段屬於第幾群（引擎算的，見 ``algo/grid.band_groups``）。"""
        return [int(g) for g in (self._data.get("groups") or [])]

    def group_rules(self) -> Dict[int, str]:
        """群號 → 要填進 ``select`` 的值。"""
        return {int(k): str(v)
                for k, v in (self._data.get("group_rules") or {}).items()}

    def group_at(self, index: float) -> Optional[int]:
        """曲線上第 ``index`` 個取樣點落在哪一群（不在任何段裡回 ``None``）。"""
        bands = self._data.get("bands") or []
        groups = self.groups()
        if len(groups) != len(bands):
            return None
        for (a, b), g in zip(bands, groups):
            if float(a) <= float(index) <= float(b):
                return int(g)
        return None

    def rule_at(self, index: float) -> str:
        """點在這裡的話，``select`` 要填什麼（沒有答案就空字串）。"""
        g = self.group_at(index)
        return self.group_rules().get(g, "") if g is not None else ""

    def _centers_in(self, a: float, b: float) -> List[float]:
        """這一段裡有幾根條紋的**中心**（用中心不用邊，邊有升有降會多算一倍）。"""
        bands = self._data.get("selected") or self._data.get("bands") or []
        out = []
        for band in bands:
            try:
                mid = (float(band[0]) + float(band[1])) / 2.0
            except (TypeError, IndexError, ValueError):
                continue
            if a <= mid <= b:
                out.append(mid)
        return sorted(out)

    def _plot_rect(self) -> QRectF:
        """曲線畫在哪一塊。

        **繪製與命中判定共用這一個** —— 兩邊各自算一次的話，量測尺會跟曲線
        差幾個像素，而那種偏差肉眼看不出來卻會讓讀數一直是錯的。
        """
        return QRectF(self.rect()).adjusted(6, 6, -6, -6).adjusted(4, 16, -4, -4)

    def _index_at(self, x: float) -> float:
        """widget 的 x 座標 → 曲線上的取樣點（= 影像像素）。"""
        n = len(self._data.get("profile") or [])
        plot = self._plot_rect()
        if n < 2 or plot.width() <= 0:
            return 0.0
        t = (float(x) - plot.left()) / plot.width()
        return max(0.0, min(float(n - 1), t * (n - 1)))

    def _end_ruler(self) -> None:
        if self._ruler is not None:
            self._ruler = None
            self.measure_ended.emit()
            self.update()

    def _emit_ruler(self) -> None:
        span = self.ruler_span()
        if span is not None:
            self.measure_changed.emit(self.axis(), span[0], span[1])

    def mousePressEvent(self, e) -> None:  # Qt hook
        if e.button() != Qt.LeftButton or not self.has_data():
            return
        i = self._index_at(e.position().x())
        self._ruler = (i, i)
        self._pressed_at = i          # 放開時用來分辨「點一下」與「拖了一段」
        self._emit_ruler()
        self.update()
        e.accept()

    def mouseMoveEvent(self, e) -> None:  # Qt hook
        if self._ruler is None:
            return
        self._ruler = (self._ruler[0], self._index_at(e.position().x()))
        self._emit_ruler()
        self.update()
        e.accept()

    def mouseReleaseEvent(self, e) -> None:  # Qt hook
        if e.button() != Qt.LeftButton or self._ruler is None:
            return
        span = abs(self._ruler[1] - self._ruler[0])
        at = self._pressed_at
        self._end_ruler()
        # **點一下 = 選這一種材質；拖一段 = 量尺。** 同一個手勢兩種意思會很糟，
        # 所以用「有沒有移動」分開 —— 那是使用者本來就分得出來的兩件事，
        # 而尺本來就要拖過一段才有意義（0 寬的尺量不出東西）。
        if span <= self.CLICK_SLOP and at is not None:
            rule = self.rule_at(at)
            if rule:
                self.select_requested.emit(self.axis(), rule)
        e.accept()

    def summary(self) -> str:
        """一行文字摘要（測試與狀態列都用這個，不用去讀畫素）。"""
        if not self.has_data():
            return ""
        d = self._data
        if d.get("selected"):
            # 交會定位：講的是「這個方向抓到幾根條紋、間距多少」——
            # 而不是「挑了哪一段」，因為它一整排都要。
            bits = ["%s · %d stripes" % (self._name, len(d["selected"]))]
            pitch = float(d.get("pitch_used") or 0.0)
            if pitch > 0:
                bits.append("pitch %.1f px" % pitch)
            if d.get("width_fixed"):
                # 只有**給定**的線寬才講。量到的線寬畫面上已經看得到（就是塗
                # 起來的那幾段有多寬），而給定的那個是使用者填進去的假設 ——
                # 假設要看得到才驗得了。
                bits.append("width %.1f px (given)"
                            % float(d.get("width_used") or 0.0))
            filled = int(d.get("filled") or 0)
            if filled:
                # 這幾根影像上看不到，是靠已知 pitch 推出來的。框仍然對，
                # 但「憑什麼對」換了一個依據 —— 使用者有權知道。
                bits.append("%d filled in" % filled)
            shift = float(d.get("snap_shift") or 0.0)
            if shift >= 0.5:
                # 使用者原話：「藍框跟線有時候會 shift」。它是刻意的（次像素
                # 精修 + 對齊到你給的 pitch），但沒講出來就只是「怪」，
                # 而「怪」的下一步通常是去亂調敏感度。
                bits.append("snapped %.1f px" % shift)
            if d.get("pitch_disagrees"):
                # 最重要的一句 —— 它是「這一顆能不能信」的答案。放在
                # confidence 前面，因為那個數字在這種失敗上反而更高。
                bits.append("⚠ measured %.0f%% of the pitch you gave"
                            % (float(d.get("pitch_ratio") or 0.0) * 100.0))
            trust = str(d.get("trust_note") or "")
            if trust:
                # 最重要的一句：這個方向的定位不能信，而且**為什麼**。
                # 它排在最前面 —— 後面那些數字在這種失敗上全都看起來正常。
                bits = [bits[0], "⚠ " + trust]
            note = str(d.get("pitch_note") or "")
            if note:
                # 給了 pitch 卻沒有用 —— 這件事一定要講。使用者會以為那格
                # 生效了，然後拿一份其實是「照影像自己量」的結果去跑整批。
                bits.append("pitch not used: %s" % note)
            blocked = len(d.get("blocked") or ())
            if blocked:
                # 「這一格我故意不放」跟「這一格我沒找到」在畫面上長得一模一樣。
                # 少了這句，使用者會以為那裡定位失敗，然後去調敏感度。
                bits.append("%d left out" % blocked)
            bits.append("confidence %.1f" % float(d.get("confidence", 0.0)))
            return " · ".join(bits)
        picked = d.get("picked")
        where = ("none" if not picked
                 else "%d-%d px" % (int(picked[0]), int(picked[1])))
        return ("%s · %d boundaries · %d sections · picked %s · confidence %.1f"
                % (self._name, len(d.get("transitions") or []),
                   len(d.get("bands") or []), where,
                   float(d.get("confidence", 0.0))))

    # -- paint -------------------------------------------------------------
    def paintEvent(self, _e) -> None:  # Qt hook
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        p.fillRect(QRectF(self.rect()), QColor(TOKENS["bg_surface"]))
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
        p.drawRoundedRect(rect, 4, 4)

        prof = [float(v) for v in (self._data.get("profile") or [])]
        if len(prof) < 2:
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(rect, Qt.AlignCenter, self._EMPTY)
            p.end()
            return

        n = len(prof)
        raw = [float(v) for v in (self._data.get("raw") or [])]
        lo = min(min(prof), min(raw) if raw else min(prof))
        hi = max(max(prof), max(raw) if raw else max(prof))
        span = max(hi - lo, 1e-6)
        plot = self._plot_rect()

        def to_x(i: float) -> float:
            return plot.left() + plot.width() * (float(i) / max(1, n - 1))

        def to_y(v: float) -> float:
            return plot.bottom() - plot.height() * ((v - lo) / span)

        # 選中的段：先畫底色，曲線才會壓在上面。
        # ``picked`` 是一段（投影定位），``selected`` 是**好幾段**（交會定位
        # 的那一組條紋）—— 兩者都畫得出來，因為只畫其中一段的話，面板就會
        # 少講「這張卡其實用到了這一整排」。
        shaded = self._data.get("selected")
        if not shaded:
            one = self._data.get("picked")
            shaded = [one] if one else []
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(TOKENS["accent_bg"]))
        for band in shaded:
            x0, x1 = to_x(int(band[0])), to_x(int(band[1]))
            p.drawRect(QRectF(x0, plot.top(), max(1.0, x1 - x0), plot.height()))

        # **底部的一條色帶：每一群一個顏色**（F11 Region-2b）。
        #
        # 「哪一組是第二亮的」是一個只有看圖才答得出來的問題，而
        # ``second_brightest`` 這個詞本身不告訴使用者任何事 —— 所以把分群畫出來。
        # 分群是引擎算的（``algo/grid.band_groups``），面板不自己分。
        #
        # 為什麼是**底部一條細帶**而不是整段上色：整段上色會把「現在用的是哪
        # 一組」那個既有的塗色淹掉（實測：塗滿之後兩者只剩 alpha 的差別），
        # 而且畫面會變得很吵。色帶回答「有幾種、哪一種是哪一種」，塗色回答
        # 「現在用的是哪一種」—— 兩個問題，兩個位置。
        bands = self._data.get("bands") or []
        groups = self.groups()
        if len(groups) == len(bands) and bands:
            picked_group = self._data.get("group_picked")
            p.setPen(Qt.NoPen)
            for band, g in zip(bands, groups):
                on = (g == picked_group)
                col = QColor(TOKENS[self.GROUP_COLORS[int(g) % len(self.GROUP_COLORS)]])
                # 沒被選中的那幾群要**很淡**：空隙那一群通常最寬，照一樣的濃度
                # 畫會把整條色帶佔滿，而真正要看的「現在用哪一組」反而變成幾根
                # 小點（render 出來確認過）。
                col.setAlpha(255 if on else 70)
                p.setBrush(col)
                x0, x1 = to_x(float(band[0])), to_x(float(band[1]))
                th = self.GROUP_BAR if on else self.GROUP_BAR * 0.45
                p.drawRect(QRectF(x0, plot.bottom() - th,
                                  max(1.0, x1 - x0), th))

        # 晶格上**故意不用**的那幾格（那裡是別的材質）。畫成斜線而不是另一種
        # 底色：它跟選中的段是同一排上的東西，差別在「用不用」，而兩塊實心色
        # 只說得出「這是兩種東西」。
        blocked = self._data.get("blocked") or []
        if blocked:
            hatch = QColor(TOKENS["text_secondary"])
            hatch.setAlpha(90)
            p.setPen(QPen(hatch, 1.0))
            for band in blocked:
                x0, x1 = to_x(float(band[0])), to_x(float(band[1]))
                r = QRectF(x0, plot.top(), max(1.0, x1 - x0), plot.height())
                p.save()
                p.setClipRect(r)
                x = r.left() - r.height()
                while x < r.right():
                    p.drawLine(QPointF(x, r.bottom()),
                               QPointF(x + r.height(), r.top()))
                    x += 4.0
                p.restore()

        # 平滑前的曲線畫在後面當對照 —— 使用者才看得出平滑吃掉了多少
        if len(raw) == n:
            p.setPen(QPen(QColor(TOKENS["border_input"]), 1.0))
            p.setBrush(Qt.NoBrush)
            path = QPainterPath(QPointF(to_x(0), to_y(raw[0])))
            for i in range(1, n):
                path.lineTo(QPointF(to_x(i), to_y(raw[i])))
            p.drawPath(path)

        p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.6))
        path = QPainterPath(QPointF(to_x(0), to_y(prof[0])))
        for i in range(1, n):
            path.lineTo(QPointF(to_x(i), to_y(prof[i])))
        p.drawPath(path)

        # 中心線 = 缺陷的位置（patch 是以缺陷為中心裁的）。
        # **標上字**：它是一條參考線不是一個控制項，而使用者問過「這條線我是
        # 可以做操作的嗎」—— 一條沒有說明的虛線看起來就像可以拖的東西。
        p.setPen(QPen(QColor(TOKENS["text_secondary"]), 1.0, Qt.DashLine))
        cx = to_x((n - 1) / 2.0)
        p.drawLine(QPointF(cx, plot.top()), QPointF(cx, plot.bottom()))
        f = p.font()
        f.setPixelSize(theme.font_px("font_tiny"))
        p.setFont(f)
        p.setPen(QColor(TOKENS["text_secondary"]))
        p.drawText(QRectF(cx + 3, plot.bottom() - 12, 64, 11),
                   Qt.AlignLeft | Qt.AlignVCenter, "defect")

        p.setPen(QPen(QColor(TOKENS["accent"]), 1.4))
        for t in (self._data.get("transitions") or []):
            # **不要 int()**：轉折位置是次像素的，而條紋的幾何用的就是它。
            # 在這裡捨掉等於畫面上的線跟塗色的方塊差半格，而那半格沒有任何
            # 解釋 —— 使用者會以為是定位歪了。
            x = to_x(float(t))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

        self._paint_ruler(p, plot, to_x)

        p.setPen(QColor(TOKENS["text_secondary"]))
        f = p.font()
        f.setPixelSize(theme.font_px("font_small"))
        p.setFont(f)
        strip = QRectF(rect.left() + 6, rect.top() + 2, rect.width() - 12, 14)
        p.drawText(strip, Qt.AlignVCenter | Qt.AlignLeft, self.summary())
        # 斜線的圖例（PR-2）：畫在同一條 14px 摘要帶的**右側**（那裡是空的，
        # 零幾何改動）。畫一小塊真的斜線 —— 「▨」那種字元在不同字型上長不
        # 一樣，而畫的這一塊跟圖上的斜線是**同一支筆**。會撞到左邊的摘要字
        # 就整組不畫（圖例是輔助，摘要是主角）。
        if self._data.get("blocked"):
            legend = region_words.LEFT_OUT_LEGEND
            fm = QFontMetricsF(p.font())
            need = 12.0 + 4.0 + fm.horizontalAdvance(legend)
            used = fm.horizontalAdvance(self.summary())
            if used + 12.0 + need <= strip.width():
                sw = QRectF(strip.right() - need, strip.top() + 3.0, 12.0, 8.0)
                hatch = QColor(TOKENS["text_secondary"])
                hatch.setAlpha(90)
                p.save()
                p.setPen(QPen(hatch, 1.0))
                p.setClipRect(sw)
                x = sw.left() - sw.height()
                while x < sw.right():
                    p.drawLine(QPointF(x, sw.bottom()),
                               QPointF(x + sw.height(), sw.top()))
                    x += 4.0
                p.restore()
                p.setPen(QColor(TOKENS["text_secondary"]))
                p.drawText(
                    QRectF(sw.right() + 4.0, strip.top(),
                           strip.right() - sw.right() - 4.0, strip.height()),
                    Qt.AlignVCenter | Qt.AlignLeft, legend)
        p.end()

    def _paint_ruler(self, p: QPainter, plot: QRectF, to_x) -> None:
        """量測尺：兩條綠線、中間一層淡綠、加上讀數。

        綠色是刻意跟畫面上其他東西**換一個色相**的：曲線是墨色、轉折線是
        accent、選中的段是 accent 的淡底 —— 量測尺再從那一家挑一個色階的話，
        「哪一條是我剛剛拉的」就只剩深淺可分，而深淺會被主題與縮放吃掉。
        """
        rul = self.ruler_span()
        if rul is None:
            return
        x0, x1 = to_x(rul[0]), to_x(rul[1])
        green = QColor(TOKENS["success"])
        if x1 - x0 >= 1.0:
            fill = QColor(green)
            fill.setAlpha(40)
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRect(QRectF(x0, plot.top(), x1 - x0, plot.height()))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(green, 1.4))
        for x in (x0, x1):
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))

        text = self.ruler_text()
        if not text:
            return
        f = p.font()
        f.setPixelSize(theme.font_px("font_small"))
        p.setFont(f)
        w = QFontMetricsF(f).horizontalAdvance(text) + 8.0
        # 讀數貼著自己量的那一段（不要放到面板角落 —— 兩條曲線各有一把尺，
        # 放在固定位置的話讀數就得先對回是哪一把）；但不准跑出畫面外。
        left = min(max(plot.left(), min(x0, x1) + 3.0), plot.right() - w)
        p.setPen(green)
        p.drawText(QRectF(left, plot.top() + 1, w, 12),
                   Qt.AlignLeft | Qt.AlignVCenter, text)


class StreamPicker(QWidget):
    """``image_keys`` 參數的編輯器：上游每一條影像流一個勾選框（F7-9）。

    為什麼不是一個輸入框
    --------------------
    「一串影像流」如果是自由文字，三個問題一次到齊 —— 使用者不知道**可以填
    什麼**（流名從來沒有列出來過）、不知道**填了會怎樣**、打錯了也不會被擋。
    勾選框把這三件事一次解掉：能填的就是列出來的那幾個。

    F7-18 之後沒有內建卡片用這個型別
    --------------------------------
    唯一用它的是 Enhance 卡的 ``also_apply``，而那件事已經拆成節點了：
    **一張卡一條流**，要對 ref 也做就再放一張卡接到 ref。留著這個編輯器是因為
    「一串影像流」仍然是 ``ParamSpec`` 的合法型別（見 ``step.PARAM_TYPES``），
    自訂卡片用得到；拿掉它等於要求下一張這種卡自己刻一個表單元件。

    值的格式是逗號分隔字串；recipe 裡指到「現在的 pipeline 沒有這條流」的名字
    也會列出來並勾著，不會因為看不到就被靜靜刪掉。
    """

    changed = Signal(str)

    _EMPTY_TEXT = "(no upstream stream yet — add an Input card first)"

    def __init__(self, streams: Sequence[str], value: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._boxes: List[QCheckBox] = []
        self._emitting = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        picked = [t.strip() for t in str(value or "").split(",") if t.strip()]
        names: List[str] = []
        for name in list(streams) + picked:      # 上游的在前，recipe 帶來的在後
            name = str(name)
            if name and name not in names:
                names.append(name)

        for name in names:
            box = QCheckBox(name, self)
            box.setChecked(name in picked)
            box.toggled.connect(self._on_toggled)
            lay.addWidget(box)
            self._boxes.append(box)
        if not names:
            hint = QLabel(self._EMPTY_TEXT, self)
            hint.setObjectName("paramHint")
            lay.addWidget(hint)
        lay.addStretch(1)

    def text(self) -> str:
        """目前的值（逗號分隔，順序同勾選框）。"""
        return ",".join(b.text() for b in self._boxes if b.isChecked())

    def set_text(self, value: str) -> None:
        picked = {t.strip() for t in str(value or "").split(",") if t.strip()}
        self._emitting = True
        try:
            for box in self._boxes:
                box.setChecked(box.text() in picked)
        finally:
            self._emitting = False

    def stream_names(self) -> List[str]:
        return [b.text() for b in self._boxes]

    def _on_toggled(self, _checked: bool) -> None:
        if not self._emitting:
            self.changed.emit(self.text())


class MultiChoicePicker(QWidget):
    """``multi_choice`` 參數的編輯器：固定選項的勾選網格（2026-08-14）。

    使用者的原話：「支援的量測數值希望是選的而不是用打的。」自由文字的三個
    問題跟 ``StreamPicker`` 那邊一模一樣 —— 不知道能填什麼、不知道填了會怎樣、
    打錯不會被擋。差別只在選項是**卡片宣告的**（``ParamSpec.choices``），
    不是上游流。排成一欄三格的網格 —— 九個統計量排成一橫列會把表單撐爆。

    recipe 帶進來、不在清單上的值（手寫的 ``glv_q37``）照樣列出來並勾著 ——
    看不到就被靜靜刪掉，是最糟的一種「幫忙」。

    ⚠ **格子上寫的字與存進 recipe 的值是兩件事**（F117 B2）：``labels`` 給了
    就顯示那個字，而勾起來寫回去的永遠是**鍵**（``cv_pct``）。值跟著每一顆
    box 上的 ``choice`` 屬性走，**不跟著 `box.text()` 走** —— 讀字的那一版會
    把白話名字存進 recipe，而那是一個跑得完、存得下、下次開起來全錯的形狀。

    沒給 label 的選項顯示鍵本身：手寫 recipe 帶進來的那種本來就沒有人給得出
    白話名字，而顯示鍵至少跟他打的字對得起來。
    """

    changed = Signal(str)
    _PER_ROW = 3

    def __init__(self, choices: Sequence[str], value: str = "",
                 parent: Optional[QWidget] = None, empty_hint: str = "",
                 labels: Optional[Dict[str, str]] = None):
        super().__init__(parent)
        self._boxes: List[QCheckBox] = []
        self._emitting = False
        self._labels: Dict[str, str] = dict(labels or {})

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)

        picked = [t.strip() for t in str(value or "").split(",") if t.strip()]
        names: List[str] = []
        for name in list(choices) + picked:      # 卡片宣告的在前，recipe 的在後
            name = str(name)
            if name and name not in names:
                names.append(name)
        for i, name in enumerate(names):
            grid.addWidget(self._make_box(name, name in picked),
                           i // self._PER_ROW, i % self._PER_ROW)
        # **一個都沒有的時候要講話**（F15-2）。選項是執行期來的（那一份 KLARF
        # 有哪些欄），所以「還沒掛第二份」是一個正常狀態 —— 而它畫出來是一塊
        # 空白，讀起來像壞掉。
        if not self._boxes and empty_hint:
            hint = QLabel(str(empty_hint), self)
            hint.setEnabled(False)
            hint.setWordWrap(True)
            grid.addWidget(hint, 0, 0, 1, self._PER_ROW)

    def text(self) -> str:
        """目前的值（逗號分隔，順序同勾選框）。"""
        return ",".join(self._value_of(b) for b in self._boxes
                        if b.isChecked())

    def set_text(self, value: str) -> None:
        picked = {t.strip() for t in str(value or "").split(",") if t.strip()}
        self._emitting = True
        try:
            for box in self._boxes:
                box.setChecked(self._value_of(box) in picked)
        finally:
            self._emitting = False

    def set_choices(self, choices: Sequence[str],
                    value: Optional[str] = None) -> None:
        """換一批選項（F15-2）。``value=None`` = 保留目前勾的。

        為什麼是「換內容」而不是「重建整張表單」：使用者剛在隔壁那一格打字，
        整張重建會把游標搶走。
        """
        keep = self.text() if value is None else str(value)
        grid = self.layout()
        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._boxes = []
        picked = [t.strip() for t in keep.split(",") if t.strip()]
        names: List[str] = []
        for name in list(choices) + picked:
            name = str(name)
            if name and name not in names:
                names.append(name)
        self._emitting = True
        try:
            for i, name in enumerate(names):
                grid.addWidget(self._make_box(name, name in picked),
                               i // self._PER_ROW, i % self._PER_ROW)
        finally:
            self._emitting = False

    def _make_box(self, name: str, checked: bool) -> QCheckBox:
        """一顆勾選框：**字是給人看的，屬性是存進 recipe 的**（F117 B2）。"""
        box = QCheckBox(self._labels.get(name, name), self)
        box.setProperty("choice", name)
        box.setChecked(bool(checked))
        box.toggled.connect(self._on_toggled)
        self._boxes.append(box)
        return box

    @staticmethod
    def _value_of(box: QCheckBox) -> str:
        """這一顆代表的**值**（不是它畫出來的字）。"""
        return str(box.property("choice") or box.text())

    def choice_names(self) -> List[str]:
        """畫面上列得出來的每一顆的**值**（不是 label）。"""
        return [self._value_of(b) for b in self._boxes]

    def _on_toggled(self, _checked: bool) -> None:
        if not self._emitting:
            self.changed.emit(self.text())


class ChannelMapField(QWidget):
    """``channel_map`` 參數的編輯器：一張「第幾張圖 → 叫什麼」的小表（F11 Input-1）。

    為什麼不是文字框
    ----------------
    值長這樣：``1:se1, 2:bse, 3:se2, 4:se3, 5:se4``。五列以上的時候，一行逗號
    字串**數不清位置** —— 而「哪一張是 BSE」正是這個參數唯一要回答的問題
    （使用者的資料是 1 BSE + 4 SE，BSE 固定在第 2 張）。數錯一格的後果不是
    語法錯誤，是 BSE 的數字被寫在 SE 的名字上：跑得完、有數字、而且是錯的。

    所以排成一列一張圖：**左邊是位置（程式寫的，不能打錯）、右邊是名字**。
    空著的那一列就是「這一張不命名」，而 placeholder 就寫出它不命名時會叫什麼
    （``test`` / ``ref`` / ``img3``…）—— 那是現行行為，使用者看得到自己在改什麼。
    """

    changed = Signal(str)

    #: 沒有命名時 ingest 會給的名字（``ingest/dataset.py::_channel_name``）。
    #: 這裡只是**顯示**用的 placeholder，真正的命名規則仍然只有 ingest 那一份。
    _DEFAULTS = ("test", "ref")

    #: 一列代表什麼 —— **三句話而已，資料形狀完全一樣**（整數 → 名字，空的就是
    #: 不要）。所以是一個旗標而不是第二個 widget：抄第二份出來的那份一定會漂移。
    _WORDS = {
        "images": ("Image %d", "Add another image",
                   "Add a row for one more image. A defect with five images "
                   "(one BSE plus four SE, say) needs five rows."),
        "labels": ("Layer %d", "Add another layer",
                   "Add a row for one more layout layer. The rows normally "
                   "come from the GLAS export — use this only if a layer is "
                   "missing from it."),
    }

    def __init__(self, value: str = "", parent: Optional[QWidget] = None,
                 min_rows: int = 0, row_kind: str = "images"):
        super().__init__(parent)
        self._edits: List[QLineEdit] = []
        self._emitting = False
        self._row_kind = str(row_kind)
        self._words = self._WORDS.get(self._row_kind, self._WORDS["images"])
        #: 這批資料**一顆有幾張圖**（0 = 還不知道）。列數至少排到這個數 ——
        #: 使用者要回答「哪一張是 BSE」的時候，唯一需要的事實就是「有幾張」，
        #: 而那個數字在資料載進來的那一刻就知道了（F11 Input-1 的尾巴）。
        self._min_rows = max(0, int(min_rows))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(2)
        outer.addLayout(self._grid)

        self._add_btn = QPushButton(self._words[1], self)
        self._add_btn.setProperty("variant", "secondary")
        self._add_btn.setToolTip(self._words[2])
        self._add_btn.clicked.connect(lambda: self._add_row(emit=True))
        outer.addWidget(self._add_btn, 0, Qt.AlignLeft)

        self.set_text(value)

    # -- 值 ------------------------------------------------------------------
    def text(self) -> str:
        """目前的值。**空白的列直接跳過** —— 那一張就是「不命名」。"""
        out = []
        for i, edit in enumerate(self._edits):
            name = edit.text().strip()
            if name:
                out.append("%d:%s" % (i + 1, name))
        return ", ".join(out)

    def set_text(self, value: str) -> None:
        pairs = {}
        for chunk in str(value or "").replace(";", ",").split(","):
            item = chunk.strip()
            if ":" in item:
                left, right = item.split(":", 1)
                try:
                    pairs[int(left.strip())] = right.strip()
                except ValueError:          # 壞值由 core 的 parse 負責報錯
                    continue
        floor = 0 if self._row_kind == "labels" else len(self._DEFAULTS)
        rows = max(floor, max(pairs) if pairs else 0, self._min_rows)
        self._emitting = True
        try:
            while len(self._edits) < rows:
                self._add_row(emit=False)
            for i, edit in enumerate(self._edits):
                edit.setText(pairs.get(i + 1, ""))
        finally:
            self._emitting = False

    def row_count(self) -> int:
        return len(self._edits)

    def row_kind(self) -> str:
        """一列代表什麼（``"images"`` / ``"labels"``）。"""
        return self._row_kind

    def set_min_rows(self, n: int) -> None:
        """這批資料一顆有幾張圖 —— 列數至少排到這麼多（不動已經填的名字）。"""
        self._min_rows = max(0, int(n))
        self.set_text(self.text())

    # -- 內部 ----------------------------------------------------------------
    def _default_name(self, index: int) -> str:
        if self._row_kind == "labels":
            # 空著 = **這一層不要**（不是「用預設名」）—— 兩者差很多，
            # 所以 placeholder 要講的是後果，不是一個假的名字。
            return "(no region for this layer)"
        if index < len(self._DEFAULTS):
            return self._DEFAULTS[index]
        return "img%d" % (index + 1)

    def _add_row(self, emit: bool = True) -> None:
        i = len(self._edits)
        label = QLabel(self._words[0] % (i + 1), self)
        label.setObjectName("paramHint")
        edit = QLineEdit(self)
        edit.setPlaceholderText(self._default_name(i))
        edit.textChanged.connect(self._on_edited)
        self._grid.addWidget(label, i, 0)
        self._grid.addWidget(edit, i, 1)
        self._edits.append(edit)
        if emit and not self._emitting:
            self._on_edited("")

    def _on_edited(self, _text: str) -> None:
        if not self._emitting:
            self.changed.emit(self.text())


class TemplateField(QWidget):
    """``template`` 參數的編輯器：一顆「建一個」的按鈕 + 一行摘要（F7-13）。

    為什麼不是文字框
    ----------------
    模板的值有六千多個字元，而且**沒有人能用打的**（它是一張影像的內容）。
    給它一個文字框有三個後果：空的時候看起來像「還沒填的欄位」，而真正的入口
    在半個螢幕外的另一塊面板上；填了之後那個框變成一整片 base64；而且它是
    可編輯的 —— 一個放不下、也編輯不了的值配一個文字框，等於邀請使用者去改它。

    這裡改成：**按鈕就在這一列**（它是這個參數的值從哪來，不是預覽的動作），
    欄位本身只回答「現在有沒有模板、是什麼樣的模板」。
    """

    build_requested = Signal()

    _EMPTY = "No template yet — this card cannot run until you build one."

    def __init__(self, value: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        # ``&&`` 見 `set_text`（Qt 會把單一個 ``&`` 當助憶鍵吃掉）。
        self.button = QPushButton("Edit template && regions…", self)
        self.button.setProperty("variant", "secondary")
        self.button.setToolTip(
            "Measure the repeating cell from one full-size image, then draw "
            "the regions on that cell. Both are stored inside this recipe — "
            "the image is only needed here, so the recipe stays a single "
            "file you can hand to someone else.")
        self.button.clicked.connect(self.build_requested.emit)
        lay.addWidget(self.button, 0, Qt.AlignLeft)

        self.summary = QLabel("", self)
        self.summary.setObjectName("paramHint")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

        self._value = ""
        self.set_text(value)

    def text(self) -> str:
        return self._value

    def set_text(self, value: str) -> None:
        self._value = str(value or "")
        self.summary.setText(self.describe())
        # 「還沒有模板」不是說明文字，是**這張卡現在跑不了**。用同一種灰字講，
        # 它就沉進下面那段說明裡了。
        self.summary.setStyleSheet(
            "color:%s; font-size:%s;%s"
            % (TOKENS["text_hint"] if self.has_template() else TOKENS["danger_text"],
               TOKENS["font_small"],
               "" if self.has_template() else " font-weight:600;"))
        # ⚠ ``&&`` 不是筆誤：Qt 把單一個 ``&`` 當成助憶鍵的記號吃掉，畫出來
        # 少一個 ``&`` 又多一條底線（``Build template _regions…``）。
        # 同一個坑 2026-08-24 在「Run all & write」上被使用者指出來，
        # `tests/test_ui_button_labels.py` 現在會掃出所有的。
        self.button.setText("Build template && regions…" if not self._value
                            else "Edit template && regions…")

    def has_template(self) -> bool:
        return bool(self._value.strip())

    def describe(self) -> str:
        """一行白話：現在存的是什麼。**摘要是解出來的，不是記在旁邊的**——
        記在旁邊的欄位會跟真正的值走散，而走散時畫面上看起來完全正常。"""
        if not self.has_template():
            return self._EMPTY
        try:
            from ..core.algo.template import decode_cell

            cell = decode_cell(self._value)
        except Exception:  # 顯示用
            cell = None
        if cell is None or getattr(cell, "size", 0) == 0:
            return ("A template is stored, but it cannot be read back. "
                    "Build it again.")
        h, w = cell.shape[:2]
        return ("Stored in this recipe: one cell of %d × %d px (%.1f kB of "
                "text). The regions below are drawn on it."
                % (w, h, len(self._value) / 1024.0))


def glyph_icon(name: str, size: int = 16, color: str = "") -> QIcon:
    """自繪圖示 → 一個 `QIcon`（給 `QComboBox` 的每一項用，2026-09-01）。

    為什麼下拉的項目要圖而不是換成一排膠囊（使用者：「ADC 的設定頁面是不是也
    加入一些 icon 會比較好」）：判定樹那一列是 ``[數字 ▾][運算子 ▾][值]``，
    而那一欄的寬度是使用者拖的（實測預設 437 px）。六顆比較運算子的膠囊擠不
    進去 —— 但**收起來的下拉照樣看得到現在選的那一顆的圖**，這是下拉唯一比
    膠囊強的地方。

    顏色預設吃主題的主要文字色；面板重建時會重畫，所以換主題跟得上。
    """
    px = QPixmap(int(size), int(size))
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    try:
        draw_glyph_icon(p, str(name), float(size),
                        str(color or TOKENS["text_primary"]))
    finally:
        p.end()
    return QIcon(px)


def region_dot_icon(index: int, size: int = 12) -> QIcon:
    """第 ``index`` 個具名區域的**顏色點**（下拉的每一項前面那一顆）。

    同一個顏色在三個畫面上講同一件事：影像上那個框、Feature 表名字的上標、
    判定段下拉的這一點。各自從自己那邊挑顏色的話，同一塊區域在三個地方是三
    個顏色 —— 而顏色指錯區域比沒有顏色糟得多（`_util.CURRENT_REGION_INDEX`
    的註解寫過同一句）。
    """
    px = QPixmap(int(size), int(size))
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(region_hex(int(index))))
    r = size * 0.34
    p.drawEllipse(QPointF(size / 2.0, size / 2.0), r, r)
    p.end()
    return QIcon(px)



class CellRoisField(QWidget):
    """``cell_rois`` 參數的編輯器：一顆按鈕 + 現在標了什麼（F11 Region-1）。

    為什麼是**唯讀**的摘要而不是文字框
    ----------------------------------
    同 ``image_key`` 那條（F9-6，使用者定調「他會很亂連」）：框的來源只有一個
    —— 畫在 cell 上。給它一個文字框的話同一件事有兩個入口，而兩邊很容易對不
    起來；更糟的是那串字的座標**相對於一格 cell**，離開那張圖就沒有意義，
    所以打得進去的自由文字正是最容易打出「跑得完、有數字、而且是錯的」的地方。

    唯讀不等於藏起來：這一格仍然要看得到現在標了哪些區域、各幾塊。
    """

    edit_requested = Signal()

    _EMPTY = "No regions yet — this card cannot run until you draw one."

    def __init__(self, value: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        self.button = QPushButton("Draw regions on the cell…", self)
        self.button.setProperty("variant", "secondary")
        self.button.setToolTip(
            "The boxes are drawn on the repeating cell, not on a patch: they "
            "have to hold for the whole batch, and a patch is a different crop "
            "for every defect.")
        self.button.clicked.connect(self.edit_requested.emit)
        lay.addWidget(self.button, 0, Qt.AlignLeft)

        self.summary = QLabel("", self)
        self.summary.setObjectName("paramHint")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

        self._value = ""
        self.set_text(value)

    def text(self) -> str:
        return self._value

    def set_text(self, value: str) -> None:
        self._value = str(value or "")
        self.summary.setText(self.describe())
        self.summary.setStyleSheet(
            "color:%s; font-size:%s;%s"
            % (TOKENS["text_hint"] if self.has_regions() else TOKENS["danger_text"],
               TOKENS["font_small"],
               "" if self.has_regions() else " font-weight:600;"))

    def has_regions(self) -> bool:
        return bool(self._value.strip())

    def describe(self) -> str:
        """**摘要是解出來的，不是記在旁邊的** —— 記在旁邊的會跟真正的值走散。"""
        if not self.has_regions():
            return self._EMPTY
        from ..core.pipeline.cellrois import CellRoiError, parse_cell_rois

        try:
            regions = parse_cell_rois(self._value)
        except CellRoiError as e:
            return "These regions cannot be read back: %s" % e
        return "  ·  ".join(
            "%s (%d rectangle%s)" % (n, len(b), "" if len(b) == 1 else "s")
            for n, b in regions)

# --------------------------------------------------------------------------- #
# 2b. CurveEditor —— 自己拉的色調曲線（F7-8）
# --------------------------------------------------------------------------- #
def _float_decimals(lo: Any, span: Optional[float], value: Any) -> int:
    """一個浮點欄位要顯示幾位小數（F68）。

    以前一律 3 位，於是「超過幾 σ」印成 ``0.000 σ``、「靠邊幾 px」印成
    ``0.000 px`` —— 三位小數在那些欄位上不是精度，是雜訊（而且讓人以為
    那一格需要那麼細）。

    規矩跟**已經存在的** step 一樣看範圍（`setSingleStep` 那一行）：

    * 下界是一個**小於 1 的正數** → 3 位。那種欄位本來就在細部
      （``nm_per_px`` 的 0.01、``gamma`` 的 0.1），砍掉小數位會讓它填不進去。
    * 範圍 ≤ 2 → 3 位（``min_score`` 的 −1…1 那種）。
    * 其餘 → 1 位（px、%、σ、灰階）。

    ⚠ **但顯示不准比 recipe 裡的值粗**：手寫 recipe 填了 ``2.55`` 的話，
    位數要夠寫得出它 —— 不然畫面上是 ``2.6``，而那是一個安靜的謊
    （QDoubleSpinBox 會把值捨進它的位數）。
    """
    if lo is not None and 0.0 < abs(float(lo)) < 1.0:
        want = 3
    elif span is not None and span <= 2.0:
        want = 3
    else:
        want = 1
    try:
        text = ("%.6f" % float(value)).rstrip("0")
        have = len(text.split(".")[1]) if "." in text else 0
    except (TypeError, ValueError):
        have = 0
    return max(want, min(have, 6))


def _wiring_display(text: str) -> QWidget:      # pragma: no cover - F68 之後沒人叫
    """「這條流從哪來」的**唯讀**顯示（F9-6）。

    為什麼是唯讀：來源改成**只在畫布上決定**。以前參數表單也能改，於是同一件事
    有兩個入口，而兩邊很容易對不起來 —— 使用者的原話是「他會很亂連」。

    唯讀不等於藏起來：這一格仍然要**看得到現在接的是什麼**，否則使用者得回畫布
    上一條一條線去數。空的時候講出「還沒接」而不是留白 —— 留白讀起來像壞掉。
    """
    w = QLineEdit()
    w.setText(str(text) if str(text).strip() else "")
    w.setPlaceholderText("not wired yet — drag a line on the canvas")
    w.setReadOnly(True)
    w.setToolTip("Set by the lines on the canvas. Drag from an output port to "
                 "change what this card works on.")
    w.setObjectName("wiringDisplay")
    w.setCursor(Qt.ArrowCursor)
    return w


class CurveEditor(QWidget):
    """可拖曳的色調曲線編輯器。橫軸 = 輸入灰階，縱軸 = 輸出灰階，兩軸都 0–1。

    操作（右下角就寫著，不用先看說明）
    ----------------------------------
    * 拖控制點 = 改曲線；
    * 在空白處按左鍵 = 加一個控制點；
    * 對控制點右鍵（或雙擊）= 刪掉它。頭尾兩點刪不掉，
      因為曲線必須覆蓋整個灰階範圍。

    **畫出來的線就是影像上套的線** —— 這裡呼叫的是 core 的
    ``algo.curve.curve_lut``，跟 ``gamma`` 卡執行時用的是同一個函式。
    UI 自己再實作一份插值是很容易發生的事，那會讓使用者看到的和跑出來的不一樣。
    這是本檔唯一一處 import ``d4t.core``，理由就是這個 —— 而且它是純運算、
    不碰引擎，沒有違反「元件不跑 pipeline」的約束。
    """

    curve_changed = Signal(str)

    _PAD = 10.0                 # 邊界留白（點拖到角落時還抓得到）
    _HIT = 9.0                  # 控制點的點擊半徑（螢幕像素）
    _DOT = 4.0

    def __init__(self, parent: Optional[QWidget] = None, compact: bool = True):
        super().__init__(parent)
        from ..core.pipeline.curve import IDENTITY, parse_curve

        self._parse = parse_curve
        self._points: List[Tuple[float, float]] = list(parse_curve(IDENTITY))
        self._drag: Optional[int] = None
        self._compact = bool(compact)
        #: 墊在曲線後面的直方圖（引擎算的那一份，見 :meth:`set_histogram`）。
        self._hist: List[float] = []
        self.setMinimumSize(QSize(150, 130 if compact else 300))
        if not compact:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setToolTip("Drag to bend · click to add a point · "
                        "right-click a point to remove it")

    # -- public API --------------------------------------------------------
    def text(self) -> str:
        from ..core.pipeline.curve import format_curve
        return format_curve(self._points)

    def points(self) -> List[Tuple[float, float]]:
        return list(self._points)

    def set_text(self, text: str, emit: bool = False) -> bool:
        """從控制點字串載入。字串壞掉時**保持原樣並回 False**。

        參數表單是「打字即生效」的，使用者打到一半必然出現不合法的中間狀態；
        那時候把曲線清成 y=x 會讓他辛苦拉的線消失。
        """
        try:
            pts = self._parse(text)
        except ValueError:
            return False
        self._points = list(pts)
        self.update()
        if emit:
            self.curve_changed.emit(self.text())
        return True

    def reset(self) -> None:
        from ..core.pipeline.curve import IDENTITY
        self.set_text(IDENTITY, emit=True)

    def is_identity(self) -> bool:
        from ..core.pipeline.curve import is_identity
        return is_identity(self._points)

    def set_histogram(self, counts: Optional[Sequence[float]]) -> None:
        """把**這張圖進來時**的灰階分布墊在曲線後面（F11 Enhance-UI-C）。

        為什麼要墊
        ----------
        曲線的橫軸是「輸入灰階」，而使用者不知道哪一段灰階**真的有畫素**。
        於是常見的兩種白工：在一個空的區間上把線拉得很陡（畫面完全沒變化），
        或者反過來，把所有畫素都在的那一小段壓平（一動就整片糊掉）。
        Photoshop 的 Curves 就是這個形狀，所以對「不會寫 code 但會修圖」的
        使用者是零學習成本。

        資料是**引擎算的那一份**（``ctx.meta['stream_change'][流]['before']``），
        UI 不自己再壓一次直方圖 —— 不然畫面上的分布跟真的跑出來的有機會不一樣。
        ``None`` / 空 = 沒有東西可墊（還沒跑過預覽），那就只畫格線。
        """
        vals = [float(v) for v in (counts or [])
                if float(v) == float(v) and float(v) >= 0.0]
        self._hist = vals
        self.update()

    def histogram(self) -> List[float]:
        """現在墊著的那一份（測試讀這個，不去讀畫素）。"""
        return list(self._hist)

    # -- 座標轉換 ----------------------------------------------------------
    def _plot_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(self._PAD, self._PAD,
                                            -self._PAD, -self._PAD)

    def _to_px(self, x: float, y: float) -> QPointF:
        r = self._plot_rect()
        return QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())

    def _to_unit(self, p: QPointF) -> Tuple[float, float]:
        r = self._plot_rect()
        w = max(1.0, r.width())
        h = max(1.0, r.height())
        return (float(np.clip((p.x() - r.left()) / w, 0.0, 1.0)),
                float(np.clip((r.bottom() - p.y()) / h, 0.0, 1.0)))

    def _hit(self, p: QPointF) -> Optional[int]:
        for i, (x, y) in enumerate(self._points):
            if (self._to_px(x, y) - p).manhattanLength() <= self._HIT * 1.6:
                return i
        return None

    # -- painting ----------------------------------------------------------
    def _paint_histogram(self, p: QPainter, plot: QRectF) -> None:
        """墊在曲線後面的分布：很淡的實心柱，高度用平方根。

        平方根跟 Enhance 儀表用的是同一個理由：兩端的削平會堆出極高的柱子，
        線性刻度下其餘的分布會被壓成一條貼著底的線 —— 而那正是要看的形狀。
        """
        vals = self._hist
        if not vals:
            return
        top = max(vals)
        if top <= 0:
            return
        h = [math.sqrt(v / top) for v in vals]
        bw = plot.width() / float(len(h))
        col = QColor(TOKENS["text_disabled"])
        col.setAlpha(70)               # 背景就是背景：看得到形狀，不搶曲線
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(col))
        for i, v in enumerate(h):
            bar = v * plot.height()
            if bar <= 0.0:
                continue
            p.drawRect(QRectF(plot.left() + i * bw, plot.bottom() - bar,
                              max(1.0, bw), bar))

    def paintEvent(self, _e) -> None:  # Qt hook
        from ..core.algo.curve import curve_lut

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
        p.setBrush(QColor(TOKENS["image_backdrop"]))
        p.drawRoundedRect(r, 5, 5)

        plot = self._plot_rect()
        # 直方圖先畫 —— 它是**背景**。畫在曲線之後的話它會蓋住曲線，
        # 而曲線才是使用者在操作的東西。
        self._paint_histogram(p, plot)
        grid = QColor(TOKENS["border_default"])
        grid.setAlpha(120)
        p.setPen(QPen(grid, 1))
        for i in range(1, 4):
            f = i / 4.0
            p.drawLine(self._to_px(f, 0.0), self._to_px(f, 1.0))
            p.drawLine(self._to_px(0.0, f), self._to_px(1.0, f))

        # y = x 參考線（虛線）—— 使用者隨時看得出自己偏離了多少
        ref = QPen(QColor(TOKENS["text_disabled"]), 1, Qt.DashLine)
        p.setPen(ref)
        p.drawLine(self._to_px(0.0, 0.0), self._to_px(1.0, 1.0))

        accent = QColor(theme.seg_hex("image"))
        n = max(24, int(plot.width()))
        lut = curve_lut(self._points, n)
        p.setPen(QPen(accent, 2.0))
        prev = self._to_px(0.0, float(lut[0]))
        for i in range(1, n):
            cur = self._to_px(i / (n - 1.0), float(lut[i]))
            p.drawLine(prev, cur)
            prev = cur

        p.setPen(QPen(QColor(TOKENS["bg_surface"]), 1.5))
        p.setBrush(accent)
        for x, y in self._points:
            c = self._to_px(x, y)
            p.drawEllipse(c, self._DOT, self._DOT)
        p.end()

    # -- interaction -------------------------------------------------------
    def mousePressEvent(self, e) -> None:  # Qt hook
        pos = QPointF(e.position())
        idx = self._hit(pos)
        if e.button() == Qt.RightButton:
            if idx is not None:
                self._remove(idx)
            return
        if e.button() != Qt.LeftButton:
            return
        if idx is None:
            idx = self._insert(*self._to_unit(pos))
            if idx is None:
                return
        self._drag = idx
        self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:  # Qt hook
        if self._drag is None:
            return
        x, y = self._to_unit(QPointF(e.position()))
        i = self._drag
        if i == 0:
            x = 0.0                       # 頭尾的 x 鎖住：曲線必須從 0 到 1
        elif i == len(self._points) - 1:
            x = 1.0
        else:
            # 不准越過鄰居 —— 越過去就不是函數了（同一個輸入兩個輸出）
            x = float(np.clip(x, self._points[i - 1][0] + 0.01,
                              self._points[i + 1][0] - 0.01))
        self._points[i] = (x, y)
        self.update()
        self.curve_changed.emit(self.text())

    def mouseReleaseEvent(self, _e) -> None:  # Qt hook
        if self._drag is not None:
            self._drag = None
            self.setCursor(Qt.CrossCursor)

    def mouseDoubleClickEvent(self, e) -> None:  # Qt hook
        idx = self._hit(QPointF(e.position()))
        if idx is not None:
            self._remove(idx)

    def _insert(self, x: float, y: float) -> Optional[int]:
        """在 x 的位置插一個控制點；太靠近既有點就不插（會變成不合法的曲線）。"""
        if any(abs(px - x) < 0.02 for px, _py in self._points):
            return None
        self._points.append((x, y))
        self._points.sort(key=lambda pt: pt[0])
        self.update()
        self.curve_changed.emit(self.text())
        return self._points.index((x, y))

    def _remove(self, idx: int) -> None:
        if idx <= 0 or idx >= len(self._points) - 1:
            return                       # 頭尾刪不掉
        del self._points[idx]
        self.update()
        self.curve_changed.emit(self.text())


class CurveField(QWidget):
    """參數表單裡的曲線欄位：小張的編輯器 + ``Reset`` / ``Enlarge…``。

    小張的可以直接拉（常見的微調不用開視窗），要做細活再按 ``Enlarge…``
    開一張大的。兩邊改的是同一組控制點。
    """

    curve_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        self.editor = CurveEditor(self)
        self.editor.curve_changed.connect(self._on_changed)
        lay.addWidget(self.editor)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(5)
        self.reset_button = QPushButton("Reset to y = x", self)
        self.reset_button.setToolTip("Put the curve back to a straight line "
                                     "(the gamma slider takes over again)")
        self.reset_button.clicked.connect(self.editor.reset)
        self.enlarge_button = QPushButton("Enlarge…", self)
        self.enlarge_button.setToolTip("Open a big curve canvas")
        self.enlarge_button.clicked.connect(self.open_dialog)
        bar.addWidget(self.reset_button)
        bar.addWidget(self.enlarge_button)
        bar.addStretch(1)
        lay.addLayout(bar)

    def text(self) -> str:
        return self.editor.text()

    def set_text(self, text: str, emit: bool = False) -> bool:
        return self.editor.set_text(text, emit=emit)

    def is_identity(self) -> bool:
        return self.editor.is_identity()

    def set_histogram(self, counts: Optional[Sequence[float]]) -> None:
        """把這張圖的灰階分布墊在曲線後面（見 `CurveEditor.set_histogram`）。"""
        self._hist = list(counts or [])
        self.editor.set_histogram(counts)
        dlg = getattr(self, "_dialog", None)
        if dlg is not None and dlg.isVisible():
            dlg.editor.set_histogram(counts)

    def histogram(self) -> List[float]:
        return self.editor.histogram()

    def open_dialog(self) -> "CurveDialog":
        dlg = CurveDialog(self.editor.text(), self)
        # 放大的那一張也要墊 —— 「做細活」正是最需要知道哪一段有畫素的時候。
        dlg.editor.set_histogram(getattr(self, "_hist", []))
        dlg.curve_changed.connect(self._adopt)
        dlg.show()
        self._dialog = dlg          # 保住參照，不然 show() 之後會被 GC
        return dlg

    def _adopt(self, text: str) -> None:
        if self.editor.set_text(text):
            self.curve_changed.emit(self.editor.text())

    def _on_changed(self, text: str) -> None:
        self.curve_changed.emit(text)


class ChartStyleField(QWidget):
    """`chart_style` 那一格：**一句摘要 ＋ 一顆 `Chart settings…`**。

    為什麼那一格不能是一個文字框（F87 第六刀，使用者 2026-09-07：
    「Chart look 是什麼? 我沒看到 Chart setting 沒看到編輯器」）
    ------------------------------------------------------------------
    `chart_style` 的值是一串 JSON（``{"tick_size":14,"box.title":"…"}``）。
    沒有這一支的時候它掉進表單的預設分支 —— 一個**可以打字的文字框，裡面是
    生 JSON**。目標使用者是不會寫 code 的製程工程師（推廣鐵則），而那一格
    等於在要他手寫設定檔；更糟的是編輯器**存在**，只是掛在別的地方
    （圖的彈出視窗），所以畫面上那一格看起來就是「這個功能沒做」。

    `tone` 的 ``type="curve"`` 早就立了規矩：**一個複雜的值裝在一格參數裡，
    配一個專屬編輯器**。我寫下了那句話卻只把編輯器接到視窗上 —— 這一支是把
    它接回它本來就該在的地方。兩個入口改的是同一格參數，開的是同一個對話框。
    """

    style_changed = Signal(str)

    def __init__(self, kinds: Optional[Sequence[str]] = None,
                 parent: Optional[QWidget] = None, words: bool = True):
        super().__init__(parent)
        self._text = ""
        self._kinds = [str(k) for k in (kinds or [])]
        self._words = bool(words)
        self._series: Dict[str, Any] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.summary = QLabel("", self)
        self.summary.setObjectName("paramHint")
        self.button = small_button(
            "Chart settings\u2026", shape="wide",
            tip=("Titles, axis names, tick counts, text size and colour, "
                 "marker and line width - and whether the value scale is "
                 "locked. It travels with the recipe."),
            parent=self)
        self.button.clicked.connect(self.open_dialog)
        lay.addWidget(self.button, 0)
        lay.addWidget(self.summary, 1)

    def text(self) -> str:
        return self._text

    def set_text(self, text: str) -> None:
        from ..core.pipeline import chart_style

        self._text = str(text or "")
        try:
            said = chart_style.describe(self._text)
        except Exception:  # 壞掉的值也要顯示
            said = "not readable - press the button to start over"
        self.summary.setText(said)

    def set_series(self, series: Optional[Dict[str, Any]]) -> None:
        """編輯器裡的預覽要畫哪一顆（Studio 餵目前選著的那一顆）。

        沒有的時候編輯器會退到樣本資料 —— 調外觀不必先跑完一批，但**用自己
        的資料看**是最有用的那一種，所以有就給。
        """
        self._series = dict(series or {})
        dlg = getattr(self, "_dialog", None)
        if dlg is not None and dlg.isVisible():
            dlg.set_series(self._series)

    def set_charts(self, kinds: Optional[Sequence[str]]) -> None:
        """對話框右半要開哪幾個分頁 —— **就是這張卡勾了哪幾張圖**。

        沒勾的那幾張的覆寫不會被清掉（`ChartSettingsDialog` 原封不動帶回去）。
        """
        self._kinds = [str(k) for k in (kinds or [])]

    def open_dialog(self) -> None:
        from .chart_settings import ChartSettingsDialog

        dlg = ChartSettingsDialog(self._text, self._kinds or None, self,
                                  series=self._series, words=self._words)
        self._dialog = dlg
        try:
            if dlg.exec():
                got = dlg.value()
                if got != self._text:
                    self.set_text(got)
                    self.style_changed.emit(got)
        finally:
            self._dialog = None


class ChartSpecField(QWidget):
    """`chart_spec` 那一格：**一句摘要 ＋ 一顆 `Chart\u2026`**（同 `ChartStyleField`）。

    為什麼一樣不能是文字框：那一格的值是 ``{"mark":"point","x":"glv_mean",
    "y":"glv_std"}``。目標使用者是不會寫 code 的製程工程師（推廣鐵則）。

    ⚠ **選單要從資料長出來**，所以這一支要拿得到那一顆的長表
    （:meth:`set_frame`）。沒有的時候按鈕照開 —— 選單是空的，而對話框上那
    一句話說得出為什麼（總比一顆按不下去的按鈕好）。
    """

    spec_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._text = ""
        self._frame: Any = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.summary = QLabel("", self)
        self.summary.setObjectName("paramHint")
        self.button = small_button(
            "Chart\u2026", shape="wide",
            tip=("Pick which measured number runs across the bottom, which "
                 "one runs up the side, and what the colour and marker size "
                 "mean."),
            parent=self)
        self.button.clicked.connect(self.open_dialog)
        lay.addWidget(self.button, 0)
        lay.addWidget(self.summary, 1)

    def text(self) -> str:
        return self._text

    def set_text(self, text: str) -> None:
        from ..core.pipeline import chart_spec

        self._text = str(text or "")
        try:
            said = chart_spec.describe(self._text)
        except Exception:  # 壞掉的值也要顯示
            said = "not readable - press the button to start over"
        self.summary.setText(said)

    def set_frame(self, frame: Any) -> None:
        """選單要從哪一份資料長出來（Studio 餵目前選著的那一顆）。"""
        self._frame = frame

    def open_dialog(self) -> None:
        from .graph_builder import GraphBuilderDialog

        dlg = GraphBuilderDialog(self._text, self._frame, self)
        if dlg.exec():
            got = dlg.value()
            if got != self._text:
                self.set_text(got)
                self.spec_changed.emit(got)


class CurveDialog(QDialog):
    """放大版的曲線畫布。非模態 —— 一邊拉曲線一邊看主視窗的預覽更新。"""

    curve_changed = Signal(str)

    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Tone curve")
        self.setModal(False)
        fit_screen.fit(self, 420, 460)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        head = QLabel("Input gray level across, output up. Drag a point to "
                      "bend the curve; click an empty spot to add one; "
                      "right-click a point to remove it.", self)
        head.setWordWrap(True)
        head.setObjectName("paramHint")
        lay.addWidget(head)

        self.editor = CurveEditor(self, compact=False)
        self.editor.set_text(text)
        self.editor.curve_changed.connect(self.curve_changed)
        lay.addWidget(self.editor, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        reset = QPushButton("Reset to y = x", self)
        reset.clicked.connect(self.editor.reset)
        buttons.addButton(reset, QDialogButtonBox.ResetRole)
        buttons.rejected.connect(self.close)
        lay.addWidget(buttons)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return default if (math.isnan(f) or math.isinf(f)) else f

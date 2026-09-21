# 設定區的膠囊 — 從 widgets.py 搬出來 2026-09-08 (U7).
"""一排可勾可選的膠囊（圖 + 字）：統計量、`chip_choice` 的那一排。

**一格選項＝一排膠囊，不是下拉**（F68 第二輪，使用者定調）。圖是掃視時的
錨點、字才是意思 —— 所以兩個都要有，而 `test_ui_widgets` 那條
「任何一張卡都不准只剩一個裸下拉」守著它。

U7 那一刀。這一份是**純搬移**：每一行都是原封搬過來的，一個字都沒有改。

⚠ **`METRIC_GROUPS` 是「引擎說有哪些，UI 說長什麼樣」的那張表**，而登記過
的與沒登記過的都要答得出來（`metric_face`）—— 手寫 recipe 的 ``glv_q37``
不能因為沒人登記就從畫面上消失（「看不到就被靜靜刪掉」是最糟的一種幫忙）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QPainter,
                           QPen)
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QInputDialog, QLabel, QSizePolicy, QVBoxLayout,
    QWidget,
)

from ..core.algo import glv as algo_glv
from . import theme
from .icons import draw_glyph_icon, draw_metric_glyph
from .theme import TOKENS

__all__ = [
    "METRIC_GROUPS", "metric_face", "MetricChips", "MetricPick", "ChoiceChips",
    # `ParamForm` 的 GLV「你的第一個問題」那一排（`_intent_btns`）直接用它
    # 造 chip —— 那是同一種膠囊的第三個用法，不是一個新的類別。
    "_ChoiceChip",
]

def _spell(value: str) -> str:
    """``beside_vertical`` → ``Beside vertical``（沒有指定顯示名時的拼法）。

    ⚠ **只動第一個字母**，不要用 ``str.capitalize()`` —— 它會把**其餘的字全部
    轉小寫**，於是 ``a cell I mark myself`` 在畫面上變成「a cell **i** mark
    myself」。那是使用者自己寫的一句話，被一支拼字函式改掉了。

    拼不對的那幾個（``zscore`` / ``nlm`` / ``topn``…）走 `ParamSpec.choice_labels`
    —— 那張表**只放例外**，不是把整排值再抄一份。
    """
    text = str(value).replace("_", " ").strip()
    return text[:1].upper() + text[1:]



#: metric id -> (分群, 短標籤, 小圖)。**引擎說有哪些，UI 說長什麼樣**：
#: 「有哪些統計量」的唯一出處是 ``ParamSpec.choices``（卡片宣告的），這裡只
#: 補上分群與怎麼畫。兩份漂開會被 `tests/test_ui_widgets.py` 擋下來。
#:
#: 分群的順序＝畫面上的順序，而它是一句話：**中心 → 離散 → 端點 → 形狀 →
#: 計數**。十四顆平鋪是一面牆；分群之後使用者只要先決定「我要問的是中心還是
#: 離散」，而那個問題他答得出來。
METRIC_GROUPS: Dict[str, Tuple[str, str, str]] = {
    "glv_median": ("Center", "Median", "median"),
    "glv_mean": ("Center", "Mean", "mean"),
    "glv_p50": ("Center", "Median (P50)", "median"),
    "glv_trim10": ("Center", "Trimmed mean", "trimmed"),
    "glv_mad": ("Spread", "MAD", "mad"),
    "glv_std": ("Spread", "Std dev", "std"),
    "glv_iqr": ("Spread", "IQR", "iqr"),
    "glv_min": ("Ends", "Min", "min"),
    "glv_max": ("Ends", "Max", "max"),
    "glv_skew": ("Shape", "Skew", "skew"),
    "glv_kurt": ("Shape", "Kurtosis", "kurtosis"),
    "glv_entropy": ("Shape", "Entropy", "entropy"),
    "glv_bimodality": ("Shape", "Bimodality", "bimodality"),
    "glv_above128": ("Counts", "Above 128", "above"),
    "glv_sat_frac": ("Counts", "Saturated %", "saturated"),
    # 「跟誰比」那一排 —— 同一個 widget、同一種膠囊（F18 補課，2026-08-21）。
    # 使用者：「Compare 跟 absolute 一樣重要，而且它的 Metric 面板 UI 也沒有
    # Statistics 那麼漂亮，我覺得可以改成切換式」。
    #
    # **分成三群不是分成一群**（F18 補課第二輪，使用者：「我覺得 Report 要有
    # 更多統計量可以量」）：九顆膠囊排成一列的時候，「哪幾個需要參照的格子」
    # 這件事在畫面上看不出來 —— 而它正是「為什麼我的 snr 是空的」的答案。
    "delta": ("Difference", "Difference", "delta"),
    "abs_delta": ("Difference", "|Difference|", "abs_delta"),
    "ratio": ("Difference", "Ratio", "ratio"),
    "percent": ("Difference", "Percent", "percent"),
    "contrast": ("Difference", "Contrast", "contrast"),
    # ⚠ **自己一群，不是掛在「Vs boxes」底下**（F110）：那個群名講的正是
    # `snr` 的分母（格與格之間），而 `snr_px` 的分母是參照自己的像素 ——
    # 把它擺進那一群，畫面上就會說它是 by-box 的，而那是這兩個數字**唯一**
    # 的差別。同一格膠囊列旁邊放兩個不同的分母，群名是使用者唯一看得到的線索。
    "snr_px": ("Vs pixels", "SNR px", "snr"),
    "snr": ("Vs boxes", "SNR", "snr"),
    "tstat": ("Vs boxes", "t-stat", "tstat"),
    "pct_rank": ("Vs boxes", "Rank %", "pct_rank"),
    "overlap": ("Distributions", "Overlap", "overlap"),
    "spread_ratio": ("Distributions", "Spread ratio", "spread_ratio"),
    # CD 的 Report（F19）。**分三群不是分成一群**，理由跟上面那一段一字不差：
    # Roughness 那一群只有在量測線夠多的時候才有意義，而那件事在一排攤平的
    # 膠囊上看不出來 —— 它正是「為什麼我的 LER 是 0」的答案。
    # Focus index 那張卡（F77，2026-09-02）。**沿用既有的圖示**，不畫新的 ——
    # 這一族講的是「銳不銳利」，而分布那套語言對它剛好成立（能量／變異數）。
    "focus_lapvar": ("Sharpness", "Laplacian var", "std"),
    "focus_tenengrad": ("Sharpness", "Gradient energy", "delta"),
    "focus_fft": ("Sharpness", "High-freq share", "percent"),
    "focus_iqi": ("Sharpness", "IQI (OP-301)", "range"),
    "cd_median": ("Width", "Median", "median"),
    "cd_mean": ("Width", "Mean", "mean"),
    "cd_min": ("Width", "Narrowest", "min"),
    "cd_max": ("Width", "Widest", "max"),
    "cd_range": ("Width", "Widest - narrowest", "range"),
    "cd_std": ("Roughness", "LWR (sigma)", "std"),
    "ler_a_std": ("Roughness", "LER one side", "ler_a"),
    "ler_b_std": ("Roughness", "LER other side", "ler_b"),
    "cd_dev": ("Vs target", "Off target", "delta"),
    "cd_dev_frac": ("Vs target", "Off target %", "percent"),
    # CD 的無方向那一支（F19 第二批）。群名用 ``Size`` / ``Outline`` ——
    # **不要用 ``Shape``**，那個字在上面已經是 GLV 的偏度那一群了。
    "cd_area_px": ("Size", "Area", "area"),
    "cd_deq": ("Size", "Equivalent diameter", "deq"),
    "cd_feret_max": ("Size", "Widest across", "feret_max"),
    "cd_feret_min": ("Size", "Narrowest across", "feret_min"),
    # ``aspect`` 重用 ``ratio``：它**本來就是**一個比值，而多畫一顆長得像
    # 「兩個 Feret」的圖示只會跟上面那兩顆撞在一起。
    "cd_aspect": ("Outline", "Long / short", "ratio"),
    "cd_roundness": ("Outline", "Roundness", "roundness"),
}

#: 分群的顯示順序。不在 :data:`METRIC_GROUPS` 裡的 id（手寫 recipe 的
#: ``glv_q37``、``glv_trim05``…）落在最後一群 —— **列出來並且勾著**，因為
#: 「看不到就被靜靜刪掉」是最糟的一種幫忙（同 `MultiChoicePicker` 的老規矩）。
#: ⚠ **`METRIC_GROUPS` 裡出現的每一個群名都要在這張表上。**
#: `MetricChips._build` 是照這張表逐群畫的，所以漏一個群 = 那一群的膠囊
#: **一顆都不會出現**，而畫面上寫的是「nothing picked yet · 0 picked」——
#: 同時引擎照樣拿 `validate_params` 補出來的預設值在算。實際發生過
#: （2026-09-02，F77 加 Focus 那一族時漏了 "Sharpness"）：設定區說一個都沒選，
#: 底下的特徵表列出三個值。守著它的是
#: `tests/test_ui_widgets.py::test_every_metric_group_can_actually_be_drawn`。
#: ⚠ **一個群名沒加進這裡，那一群的膠囊就安靜地不畫**（F77 真的踩過）。
METRIC_GROUP_ORDER = ("Center", "Spread", "Ends", "Shape", "Counts",
                      "Difference", "Vs pixels", "Vs boxes", "Distributions",
                      "Width", "Roughness", "Vs target",
                      "Size", "Outline", "Sharpness", "Other")


def metric_face(mid: str) -> Tuple[str, str, str]:
    """一個 metric id 的（分群, 短標籤, 小圖）—— 沒登記過的也答得出來。"""
    known = METRIC_GROUPS.get(mid)
    if known:
        return known
    q = algo_glv.quantile_of(mid)
    if q is not None:
        return ("Ends", "P%d" % q, "percentile")
    t = algo_glv.trim_of(mid)
    if t is not None:
        return ("Center", "Trimmed %d%%" % t, "trimmed")
    a = algo_glv.above_of(mid)
    if a is not None:
        return ("Counts", "Above %d" % a, "above")
    return ("Other", mid, "percentile")


class _ChipBase(QFrame):
    """一顆膠囊：小圖 + 短標籤，點一下切換選/不選。

    為什麼是自繪而不是 QCheckBox + QSS：選中的狀態要用**階段色**（量測段的
    橙），而那個顏色是算出來的（`theme.group_hex` / `readable_on`），不是主題
    的一個 token —— 走 QSS 的話每換一次主題都要重寫一次樣式表字串。

    這個基底只認得**一顆膠囊長什麼樣**（尺寸、字級、選中的畫法）。「小圖是
    哪一張、字寫什麼、tooltip 講什麼」由子類決定：統計量那一族
    （:class:`_MetricChip`）畫的是分布上的一筆，設定區那一族
    （:class:`_ChoiceChip`）畫的是按鈕圖示。**兩族共用同一個外觀是刻意的**
    —— 使用者 2026-09-01：「我希望設定欄這邊也是能像下方一樣膠囊 icon 配文字，
    這樣 user 比較會有感覺。」抄第二份出來的那份會漂移（這個 repo 記過三次），
    所以外觀只有這一份。
    """

    toggled = Signal(str, bool)

    #: ⚠ **這個數字跟按鈕是同一個節奏**（`theme` 的 QSS：1px 邊框 ＋ 7px
    #: padding ＋ 18px min-height = 34）。膠囊跟按鈕、輸入框常常排在同一欄裡，
    #: 只改一邊那一欄就會參差 —— 而那正是 theme 裡那段「one vertical rhythm」
    #: 的註解寫下來要防的事。
    #: 30 → 34（F120，2026-09-21，跟按鈕一起）。
    H = 34
    GLYPH = 19
    #: ⚠ **字級要用 px 並且同時寫進 stylesheet**：QSS 的 ``* { font-size: 13px }``
    #: 會蓋掉 ``setFont``，於是「量寬度用的字」與「畫出來的字」不是同一個 ——
    #: 症狀是膠囊右邊被切掉（第一版的 “Trimmed mean” 少了半個 n）。
    FONT_PX = 11

    #: 虛線框（「這裡還沒有東西」）—— 只有「再加一顆」那種膠囊會打開。
    dashed = False

    #: **按了不自己改狀態**：發出訊號，勾不勾由呼叫端下一次重畫時決定。
    #: 用在 preset 那一排（「照這個意思把線接好」）—— 那一排再按一次不該把它
    #: 取消（取消要回到哪個狀態？沒有答案），而套不上的時候畫面要停在真實
    #: 狀態上，不是停在使用者按下去的那一顆。
    momentary = False

    def __init__(self, mid: str, label: str, colour: str,
                 checked: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.mid = str(mid)
        self.label = str(label)
        self.colour = str(colour)
        self._checked = bool(checked)
        self._hover = False
        self.setObjectName("metricChip")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(self.H)
        f = QFont(self.font())
        f.setPixelSize(self.FONT_PX)
        self.setFont(f)
        self.setStyleSheet("font-size: %dpx;" % self.FONT_PX)
        self.setFixedWidth(int(11 + self.GLYPH + 7
                               + QFontMetricsF(f).horizontalAdvance(self.label)
                               + 15))
        self.setAccessibleName(self.label)

    def draw_glyph(self, p: QPainter, ink: QColor, dim: QColor) -> None:
        """畫這一顆的小圖（子類實作）。"""
        raise NotImplementedError

    # -- 狀態 ---------------------------------------------------------------
    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, on: bool) -> None:
        self._checked = bool(on)
        self.update()

    def set_colour(self, colour: str) -> None:
        self.colour = str(colour)
        self.update()

    # -- Qt hooks -----------------------------------------------------------
    def enterEvent(self, _e) -> None:  # Qt hook
        self._hover = True
        self.update()

    def leaveEvent(self, _e) -> None:  # Qt hook
        self._hover = False
        self.update()

    def mousePressEvent(self, e) -> None:  # Qt hook
        if e.button() == Qt.LeftButton:
            self.click()

    def click(self) -> None:
        """切換這一顆（測試直接呼叫這支，不模擬滑鼠）。

        **灰掉的時候什麼都不做。** Qt 只擋得住滑鼠事件；直接呼叫這支的路
        （測試、鍵盤）擋不到，而「按了灰的鈕居然生效」是最難查的那種。
        """
        if not self.isEnabled():
            return
        if self.momentary:
            self.toggled.emit(self.mid, True)
            return
        self._checked = not self._checked
        self.update()
        self.toggled.emit(self.mid, self._checked)

    def changeEvent(self, e) -> None:  # Qt hook
        if e.type() == QEvent.EnabledChange:
            self.setCursor(Qt.PointingHandCursor if self.isEnabled()
                           else Qt.ArrowCursor)
            self.update()
        super().changeEvent(e)

    def paintEvent(self, _e) -> None:  # Qt hook
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad = r.height() / 2.0
        if not self.isEnabled():
            # 灰掉 = **這一格現在還不能答**（例：roi 那條線還沒接）。
            # 選中的那一顆**照樣看得出是選中的**（它是現在的狀態，不是一個
            # 待選項）—— 只是整顆退色。
            bg = QColor(self.colour if self._checked else TOKENS["bg_surface"])
            if self._checked:
                bg.setAlpha(16)
            border = QColor(self.colour if self._checked
                            else TOKENS["border_default"])
            if self._checked:
                border.setAlpha(110)
            ink = QColor(TOKENS["text_disabled"])
            dim = QColor(ink)
            dim.setAlpha(90)
        elif self._checked:
            bg = QColor(self.colour)
            bg.setAlpha(42 if self._hover else 30)
            border = QColor(self.colour)
            border.setAlpha(200)
            ink = QColor(theme.readable_on(self.colour, TOKENS["bg_surface"]))
            dim = QColor(ink)
            dim.setAlpha(85)
        else:
            bg = QColor(TOKENS["hover_warm"] if self._hover
                        else TOKENS["bg_surface"])
            border = QColor(TOKENS["border_default"])
            ink = QColor(TOKENS["text_secondary"])
            dim = QColor(TOKENS["text_hint"])
            dim.setAlpha(110)
        pen = QPen(border, 1.4 if (self._checked and self.isEnabled()) else 1.0)
        if self.dashed:
            pen.setStyle(Qt.DashLine)     # 虛線 = 這裡還沒有東西，按了才長出來
        p.setBrush(QBrush(bg))
        p.setPen(pen)
        p.drawRoundedRect(r, rad, rad)
        p.save()
        p.translate(11, (self.height() - self.GLYPH) / 2.0)
        self.draw_glyph(p, ink, dim)
        p.restore()
        p.setPen(ink)
        p.drawText(QRectF(11 + self.GLYPH + 7, 0, self.width(), self.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, self.label)
        p.end()


class _MetricChip(_ChipBase):
    """統計量那一族的膠囊：小圖是**這個統計量標在分布上的哪一筆**。"""

    #: 「再加一顆」的那種膠囊被按了（``adder_label`` 有值時才會發）。
    add_clicked = Signal(str)

    def __init__(self, mid: str, colour: str, checked: bool = False,
                 parent: Optional[QWidget] = None,
                 adder_label: str = ""):
        if adder_label:
            # 這一顆是**動作**不是統計量：虛線框、永遠不是「選中」。
            group, label, glyph = "", str(adder_label), "plus"
        else:
            group, label, glyph = metric_face(str(mid))
        super().__init__(mid, label, colour, checked, parent)
        self.group, self.glyph = group, glyph
        self.adder = self.dashed = bool(adder_label)
        # tooltip = 這個統計量到底算什麼（引擎那一份公式，不要再寫第二份）。
        self.setToolTip("Add one and pick the number" if self.adder else
                        "%s — %s" % (algo_glv.metric_label(self.mid),
                                     algo_glv.metric_formula(self.mid)))

    def click(self) -> None:  # 見基底
        if self.adder:
            self.add_clicked.emit(self.mid)
            return
        super().click()

    def draw_glyph(self, p: QPainter, ink: QColor, dim: QColor) -> None:
        draw_metric_glyph(p, self.glyph, float(self.GLYPH), ink.name(),
                          dim.name())


class _ChoiceChip(_ChipBase):
    """設定區那一族的膠囊：小圖是**這個選項在做什麼**（`GLYPH_ICONS`）。

    值就是 ``mid``（recipe 裡那個字），字是 :func:`_spell` 拼出來的 ——
    所以加一個選項不必再維護第二張「值 → 顯示名」的表。
    """

    def __init__(self, value: str, icon: str, colour: str,
                 checked: bool = False, parent: Optional[QWidget] = None,
                 tip: str = "", label: str = ""):
        super().__init__(value, str(label or "") or _spell(value), colour,
                         checked, parent)
        self.icon = str(icon)
        self.setToolTip(str(tip or ""))

    def draw_glyph(self, p: QPainter, ink: QColor, dim: QColor) -> None:
        draw_glyph_icon(p, self.icon, float(self.GLYPH), ink.name())


class _ChipFlow(QWidget):
    """一群膠囊，寬度不夠就換行（QLayout 排不出「換行」，所以自己排）。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        #: 膠囊**與**「+ Percentile」那種鈕都排在這裡 —— 它們在同一列上，
        #: 分開排的話換行的位置會兩邊各算各的。
        self._items: List[QWidget] = []
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def add(self, item: QWidget) -> None:
        item.setParent(self)
        item.show()
        self._items.append(item)
        self._relayout()

    def remove(self, item: QWidget) -> None:
        """拿掉一顆（呼叫端自己 `deleteLater`）。"""
        if item in self._items:
            self._items.remove(item)
            item.setParent(None)
            self._relayout()

    def chips(self) -> List["_ChipBase"]:
        return [c for c in self._items if isinstance(c, _ChipBase)]

    def _relayout(self, width: Optional[int] = None) -> None:
        w = int(width or self.width() or 320)
        x = y = 0
        for c in self._items:
            if x and x + c.width() > w:
                x = 0
                y += _ChipBase.H + 5
            c.move(x, y)
            x += c.width() + 5
        self.setFixedHeight(y + _ChipBase.H if self._items else 0)

    def resizeEvent(self, e) -> None:  # Qt hook
        self._relayout(e.size().width())
        super().resizeEvent(e)

    #: ⚠ **要自己講寬度。** 這一族的高度是排完版才知道的，所以 `_relayout`
    #: 只設了 `setFixedHeight` —— 而寬度沒有人講的話 `sizeHint` 是 0，
    #: 於是放進一個沒有 stretch 的 layout（判定面板那一列）時整塊被壓成 0 px
    #: 寬：膠囊都在、也都 `isVisible()`，但畫面上什麼都沒有（2026-09-01
    #: render 出來才看到）。ParamForm 那邊看不出來，因為它是 `addWidget(w, 1)`。
    def sizeHint(self) -> QSize:  # Qt hook
        return QSize(max([c.width() for c in self._items] or [0]) or 120,
                     max(self.height(), _ChipBase.H))

    def minimumSizeHint(self) -> QSize:  # Qt hook
        return QSize(max([c.width() for c in self._items] or [0]),
                     _ChipBase.H)


class MetricChips(QWidget):
    """``metric_chips`` 參數的編輯器：分群的膠囊 + 「會變成哪幾個 feature」。

    值的格式跟 :class:`MultiChoicePicker` **一字不差**（逗號分隔的 id），所以
    recipe JSON 沒有變 —— 換掉的只有長相。為什麼要換（F18，使用者：「metric
    部分的 UI 我希望更漂亮一點」）：

    * **分群**讓十四顆不再是一面牆；
    * **小圖**給了掃視時的錨點，而且它教了一件事（見 :func:`draw_metric_glyph`）；
    * **底下那一行**把勾選變成 feature 名講出來 —— 那些名字會被打進分數表達式，
      所以它們不能只活在文件裡。

    ``+ Percentile`` 與 ``+ Above`` 是**動作**不是統計量：按下去問一個數字，
    長出一顆 ``glv_q<NN>`` / ``glv_above<NN>``。以前要在自由文字裡自己打
    ``glv_q37``，而打錯只會安靜地少一個 feature。
    """

    changed = Signal(str)

    #: 「再加一顆」的兩個動作：(按鈕字, 問句, 下限, 上限, id 模板)。
    _ADDERS = (
        ("Percentile", "Which percentile? (0-100)", 0, 100, "glv_q%d", 90),
        ("Above", "Count pixels brighter than? (0-255)", 0, 255,
         "glv_above%d", 200),
    )

    def __init__(self, choices: Sequence[str], value: str = "",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._choices = [str(c) for c in (choices or [])]
        self._chips: List[_MetricChip] = []
        self._flows: Dict[str, _ChipFlow] = {}
        self._emitting = False

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(9)
        self._grid.setVerticalSpacing(6)
        self._grid.setColumnStretch(1, 1)

        self.count = QLabel("", self)
        self.count.setObjectName("paramHint")
        self.count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._grid.addWidget(self.count, 0, 1)

        self.out = QLabel("", self)
        self.out.setObjectName("paramHint")
        self.out.setWordWrap(True)

        self._build(value)

    # -- public API ---------------------------------------------------------
    def text(self) -> str:
        """目前的值（逗號分隔）。**順序＝畫面上的順序**，不是點選的順序 ——
        同一組勾選每次都要產生同一個字串，不然一份 recipe 會因為使用者點的
        先後而長得不一樣（而它進得了快取簽章）。"""
        return ",".join(c.mid for c in self._chips if c.is_checked())

    def set_text(self, value: str) -> None:
        picked = {t.strip() for t in str(value or "").split(",") if t.strip()}
        unknown = [m for m in picked
                   if m not in [c.mid for c in self._chips]]
        if unknown:                       # recipe 帶進來的手寫 id
            self._build(str(value or ""))
            return
        self._emitting = True
        try:
            for c in self._chips:
                c.set_checked(c.mid in picked)
        finally:
            self._emitting = False
        self._sync_labels()

    def chip(self, mid: str) -> Optional["_MetricChip"]:
        """某一顆膠囊（測試點它、Studio 高亮它用）。"""
        for c in self._chips:
            if c.mid == str(mid):
                return c
        return None

    def picked(self) -> List[str]:
        return [c.mid for c in self._chips if c.is_checked()]

    def choice_names(self) -> List[str]:
        """畫面上列得出來的每一顆（同 :meth:`MultiChoicePicker.choice_names`）。

        **不含**「+ Percentile…」那種膠囊 —— 它們是動作，不是可以勾的統計量。
        """
        return [c.mid for c in self._chips]

    def refresh_colour(self) -> None:
        colour = theme.group_hex("measure")
        for c in self._chips:
            c.set_colour(colour)

    # -- internals ----------------------------------------------------------
    def _build(self, value: str) -> None:
        while self._grid.count() > 1:
            item = self._grid.takeAt(1)
            w = item.widget()
            if w is not None and w is not self.count and w is not self.out:
                w.setParent(None)
                w.deleteLater()
        self._chips = []
        self._flows = {}

        picked = [t.strip() for t in str(value or "").split(",") if t.strip()]
        # 卡片宣告的在前、recipe 帶來的在後（同 MultiChoicePicker 的規矩）。
        ids: List[str] = []
        for mid in list(self._choices) + picked:
            if mid and mid not in ids:
                ids.append(mid)

        colour = theme.group_hex("measure")
        by_group: Dict[str, List[str]] = {}
        for mid in ids:
            by_group.setdefault(metric_face(mid)[0], []).append(mid)
        # 「再加一顆」是 GLV 統計量專屬的（分位數、亮度門檻）。這個 widget 也
        # 服務「跟誰比」那一格，而在那裡長出一顆 `+ Percentile…` 只會是一顆
        # 按了會加出一個那張表不認得的值的鈕。
        adders = any(str(m).startswith("glv_") for m in ids)

        # 群名那一欄有多寬**由最長的那個群名決定**，不是一個寫死的數字。
        # 以前是 46 px，剛好裝得下 Statistics 的五個群（Center…Counts）——
        # 而 Report 分成三群之後，「Difference」與「Distributions」在畫面上
        # 是「ifference」與「ributions」。同一種 QSS 的字級也要進度量
        # （`* { font-size: 13px }` 會蓋掉 `setFont`，那是膠囊那邊踩過的坑）。
        gf = QFont(self.font())
        gf.setPixelSize(10)
        gm = QFontMetricsF(gf)
        shown = [g for g in METRIC_GROUP_ORDER
                 if (by_group.get(g) or (adders and g == "Ends"))]
        label_w = (max([46] + [int(gm.horizontalAdvance(g)) + 4 for g in shown])
                   if len(by_group) > 1 else 46)

        row = 1
        for group in METRIC_GROUP_ORDER:
            members = by_group.get(group) or []
            if not members and not (adders and group == "Ends"):
                continue
            # 只有一群的時候不印群名（「跟誰比」那一格就是這種）—— 那一列的
            # 標籤已經寫了「Report」，旁邊再擺一個「Compare」只是一個沒有在
            # 分辨任何東西的字。
            lbl = QLabel(group if len(by_group) > 1 else "", self)
            lbl.setObjectName("metricGroup")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignTop)
            # 字級**兩邊都設**（QFont 與 QSS）：`* { font-size: 13px }` 會蓋掉
            # `setFont`，所以只設 QFont 的話畫出來是 13 px；只設 QSS 的話
            # `lbl.fontMetrics()` 量的是 13 px 而畫出來是 10 px —— 兩種都會讓
            # 「這個字裝得下嗎」的答案跟畫面不一致（膠囊那邊踩過同一個坑）。
            lbl.setFont(gf)
            lbl.setFixedWidth(label_w)
            lbl.setStyleSheet("color:%s; font-size:%s; padding-top:8px;"
                              % (TOKENS["text_hint"], TOKENS["font_tiny"]))
            flow = _ChipFlow(self)
            for mid in members:
                c = _MetricChip(mid, colour, mid in picked, flow)
                c.toggled.connect(self._on_toggled)
                flow.add(c)
                self._chips.append(c)
            # 「再加一顆」的膠囊跟著它產生的東西放：分位數在 Ends、亮度在
            # Counts。做成**同一種膠囊**（虛線框）而不是一顆按鈕 —— 那一列上
            # 混一顆長得不一樣的鈕，讀起來像是它跟旁邊那些不是同一件事。
            for text, question, lo, hi, tmpl, start in self._ADDERS:
                if not adders or metric_face(tmpl % start)[0] != group:
                    continue
                b = _MetricChip("+" + tmpl, colour, False, flow,
                                adder_label=text + "…")
                b.add_clicked.connect(
                    lambda _m="", q=question, a=lo, z=hi, t=tmpl, s=start:
                    self._add_number(q, a, z, t, s))
                flow.add(b)
            self._grid.addWidget(lbl, row, 0)
            self._grid.addWidget(flow, row, 1)
            self._flows[group] = flow
            row += 1

        self._grid.addWidget(self.out, row, 1)
        self._sync_labels()

    def _add_number(self, question: str, lo: int, hi: int, tmpl: str,
                    start: int) -> None:
        n, ok = QInputDialog.getInt(self, "Add a statistic", question,
                                    start, lo, hi, 1)
        if not ok:
            return
        mid = tmpl % int(n)
        existing = self.chip(mid)
        if existing is not None:              # 已經有了 -> 勾起來就好
            existing.set_checked(True)
        else:
            self._build(",".join(self.picked() + [mid]))
        self._emit()

    def _on_toggled(self, _mid: str, _on: bool) -> None:
        if not self._emitting:
            self._emit()

    def _emit(self) -> None:
        self._sync_labels()
        self.changed.emit(self.text())

    def _sync_labels(self) -> None:
        names = self.picked()
        self.count.setText("%d picked" % len(names))
        # **這一行是「會變成哪幾個 feature」**，不是「你勾了什麼」的複述：
        # 接了區域的時候引擎會加上區域名前綴（`epi_glv_median`），而那件事
        # 這裡不知道 —— 所以只講字尾，並且由 help 說明前綴。
        self.out.setText("→  " + (", ".join(names) if names
                                  else "nothing picked yet"))


class MetricPick(MetricChips):
    """``metric_choice`` 參數的編輯器：**單選**版膠囊（F32）。

    跟 :class:`MetricChips` 同一種膠囊、同一個「+ Percentile…」——
    差別只有三件：值是**一個** id、點一顆會把其他的關掉、恆有一顆選著
    （取消最後一顆等於留下一個空值，而空值會在 validate 被換回預設 ——
    看起來像「取消沒有生效」，不如一開始就不准）。

    為什麼不是下拉：GLV 的統計量在這張卡的其他格都是帶小圖的膠囊，
    同一個東西在同一張卡上兩種長相，使用者要學兩次（F18 的理由原封不動）。
    """

    def text(self) -> str:
        picked = [c.mid for c in self._chips if c.is_checked()]
        return picked[0] if picked else ""

    def _on_toggled(self, mid: str, on: bool) -> None:
        if self._emitting:
            return
        if on:
            self._emitting = True
            try:
                for c in self._chips:
                    if c.mid != mid:
                        c.set_checked(False)
            finally:
                self._emitting = False
        elif not any(c.is_checked() for c in self._chips):
            # 恆有一顆選著：把它勾回來、值沒變、不 emit。
            self._emitting = True
            try:
                got = self.chip(mid)
                if got is not None:
                    got.set_checked(True)
            finally:
                self._emitting = False
            return
        self._emit()

    def _add_number(self, question: str, lo: int, hi: int, tmpl: str,
                    start: int) -> None:
        n, ok = QInputDialog.getInt(self, "Add a statistic", question,
                                    start, lo, hi, 1)
        if not ok:
            return
        mid = tmpl % int(n)
        if self.chip(mid) is None:
            self._build(mid)          # 重建：宣告的照列，而只有這一顆選著
        else:
            self._emitting = True
            try:
                for c in self._chips:
                    c.set_checked(c.mid == mid)
            finally:
                self._emitting = False
        self._emit()

    def _sync_labels(self) -> None:
        got = self.text()
        self.count.setText("")        # 單選沒有「N picked」好講
        self.out.setText("→  the odd box is judged by %s"
                         % (got or "nothing yet"))


class ChoiceChips(QWidget):
    """``chip_choice`` 參數的編輯器：**一排膠囊，選一顆**（F68 第二輪）。

    使用者 2026-09-01：「我希望設定欄這邊也是能像下方一樣膠囊 icon 配文字，
    這樣 user 比較會有感覺。」

    為什麼不是下拉選單（跟 :class:`MetricChips` 同一個理由，只是換一格）
    ------------------------------------------------------------------
    下拉選單把選項**藏起來**：使用者要先按開才知道有幾個、分別是什麼，而這
    幾格問的是「這張卡要怎麼找缺陷」—— 那是他每一次調參數都要重看一遍的事。
    攤成一排膠囊之後，選項本身就是畫面，而選中的那一顆帶著階段色。

    為什麼不是「只有圖、名字退到 tooltip」（F11 Region-2 的 ``IconChoice``，
    2026-09-01 拿掉）
    ------------------------------------------------------------------
    那一族的理由是「那個詞講的就是一個畫得出來的形狀」（``beside_vertical``、
    CD 的一條線／一團東西）—— 圖給完了，字是多的。而使用者看了整個設定區之後
    的判斷相反：「**我認為設定區都要變成這樣 icon 膠囊 + 文字，並且視覺模型
    可能要接近會比較好**」。同一個面板上兩種長相，使用者要學兩次；
    **圖是掃視時的錨點，字才是意思**。所以現在只有這一種。

    值的格式跟 ``choice`` **一字不差**（就是那個字），所以 recipe JSON 沒有變。
    """

    changed = Signal(str)

    def __init__(self, choices: Sequence[str], icons: Sequence[str],
                 value: str = "", helps: Optional[Dict[str, str]] = None,
                 parent: Optional[QWidget] = None,
                 labels: Optional[Dict[str, str]] = None):
        super().__init__(parent)
        helps = dict(helps or {})
        labels = dict(labels or {})
        colour = theme.group_hex("measure")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._flow = _ChipFlow(self)
        lay.addWidget(self._flow)

        self._chips: List[_ChoiceChip] = []
        self._value = str(value or "")
        for name, icon in zip([str(c) for c in choices],
                              [str(i) for i in icons]):
            c = _ChoiceChip(name, icon, colour, name == self._value,
                            self._flow, tip=helps.get(name) or "",
                            label=labels.get(name) or "")
            c.toggled.connect(self._on_toggled)
            self._flow.add(c)
            self._chips.append(c)

    # -- ParamForm 那一側看到的介面（跟其他編輯器一樣是 text/set_text）------
    def text(self) -> str:
        return self._value

    def set_text(self, value: str) -> None:
        # 認不得的值（手寫 recipe）**不要偷偷改掉**：一顆都不亮，比亮錯一顆
        # 誠實（這一條是從 `IconChoice` 帶過來的，那個 widget 已經不在了）。
        self._value = str(value or "")
        for c in self._chips:
            c.set_checked(c.mid == self._value)

    def chip(self, value: str) -> Optional[_ChoiceChip]:
        """某一顆膠囊（測試點它用）。"""
        for c in self._chips:
            if c.mid == str(value):
                return c
        return None

    def _on_toggled(self, mid: str, on: bool) -> None:
        """**恆有一顆選著**：再點選中的那一顆不會把它關掉。

        取消最後一顆等於留下一個空值，而空值在 ``validate_params`` 會被換回
        預設 —— 看起來像「我點了但沒有反應」（同 :class:`MetricPick`）。
        """
        if not on:
            got = self.chip(mid)
            if got is not None:
                got.set_checked(True)
            return
        self.set_text(mid)
        self.changed.emit(self._value)

# d4t helper：問一張圖的 pitch — authored 2026-09-21 (F120).
"""**Pitch helper —— 丟一張圖進去，回答它的 cell period。**

使用者 2026-09-21：「主要是算 Golden cell（應該在 ROI 內那張卡），命名就叫
pitch helper，主要功能就是丟一張圖進去，算 repeating pattern 的 cell period
（可支援 pixels & X(nm)）。」

這個能力今天**只存在於一條很長的路的中間**：Studio → `roi_reference`
（`method="template"`）→ `TemplateDialog` → 匯入大圖 → 疊模板。週期是那條路的
副產品，而使用者常常只想要那個數字本身。為了一個數字先開 Studio、先有一份
recipe、先加一張卡、先接好線 —— 那不是「功能不存在」，是**入口不存在**。
所以這一支**不新增任何演算法**，它只是一個入口。

⚠ **原功能一個字都沒動。** `roi_reference` / `roi_template` / `TemplateDialog`
照舊，recipe 照舊，黃金值照舊。

量週期不抄第二份
----------------
唯一出處是 `algo/template.measure_period`（三票制：投影法 ＋ 二維自相關 ＋
半週期檢查，F104／F105 的實測全長在它身上）。它本來是私有的
（``_measure_period``），F120 改成公開 —— 第二個呼叫者出現時，選擇只有
「開放那一支」與「抄一份三票制出去」，而後者一定會漂（`CLAUDE.md` §0）。

「怎麼證明它是對的」—— 疊起來看（使用者 2026-09-21 指定的做法）
----------------------------------------------------------------
> 「仿照所謂的 AMAT 的 golden cell：將 period 週期用格線切完後，將所有的每個
>  cell 放在一起，如果取的 period 是完美的，他會有疊加 Frame 的效果，GC 影像
>  會很漂亮；如果 period 錯，格線切的差，疊起來就會糊糊的。」

所以畫面上是**兩張圖**，而不是一堆分數：

1. **原圖 ＋ 切點格線** —— 格子有沒有跟著同一種結構走（F103 那一套）；
2. **疊起來的那一格**（`golden.stack_cells`，走 `build_golden_cell` 本人）——
   清楚 ＝ 週期對，糊掉／出現兩層 ＝ 週期錯。**一眼的事，不需要懂任何分數。**

⚠ **旁邊那個數字是 `agreement`，不是 sharpness** —— 而那個選擇是量出來的
（F40，2026-08-26）。使用者的直覺（「或是算 sharpness 這樣評估」）是自然的，
但 `ghosting_score` 只看疊完的那一張圖，**看不到疊進去的那幾格**，所以分不出
「因為對齊了所以銳利」與「因為兩個鬼影各帶一組邊所以銳利」—— 相位錯掉的 stack
實測拿到 **76.1**，而正確的只有 **68.4**；純雜訊在 σ=60 拿 **99.4**。
`golden.stack_agreement` 問的是那幾格**彼此**對得多齊（`var(mean(cells)) /
mean(var(cell))`，扣掉 `1/n` 的地板），無量綱、跨影像可比，所以它才是那個可以
配固定門檻的數字。**人眼看那張圖 ＋ 這個數字，兩個一起才完整。**

單位：px 是答案，nm 是換算
--------------------------
`docs/FAB-VALIDATION.md` 假設 #2 已經定調：``nm_per_px`` 在 KLARF 裡沒有來源，
所以**單位一律 pixel、換算搬到輸出那一刻**。這裡照抄卡片那一套
（`steps/_util.nm_per_px_spec`）：**0 ＝ 不知道，那一欄就不出現**。
顯示一個 `0 nm` 比不顯示糟得多 —— 它看起來像一個量出來的答案。

版面：一分鐘之內要答得完（使用者 2026-09-21）
---------------------------------------------
> 「user 進來是要 1 min 內解決問題，而不是找按鍵還要看一堆文字。」

所以是**一條細工具列 ＋ 左圖右答案**，而右邊由上而下就是使用者的問題順序：

    pitch 是多少 → 哪個方向 → 不對的話我自己改 → 憑什麼相信它

第一版是四個編號方塊由上而下、每一塊都帶一段說明，讀完才知道要按哪裡。
三條換掉它的規則寫在 :class:`PitchHelperWindow` 的 docstring 裡。

刻意不放進 Studio 的工具列
--------------------------
同 `gc_generator` 的理由，逐字適用：那條工具列已經滿到把「Results」擠進 Qt 的
overflow 過一次（F48）。這是一個**問一個數字**的工具，不是分析流程的一步。
開法：``python -m d4t pitch``。
"""
from __future__ import annotations

import os
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import (
    QColor, QGuiApplication, QImage, QKeySequence, QPainter, QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QCheckBox, QDoubleSpinBox, QFileDialog,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from pitchapp.core.algo import period as algo_period
from pitchapp.core.algo import period2d as algo_period2d
from pitchapp.core.algo import template as algo_template
from pitchapp.core.log import swallowed

from . import branding, fit_screen, theme
from .chips import ChoiceChips
from .crop_dialog import CropDialog, crop_array, describe_crop
from .icons import GlyphButton
from .splitters import HairlineSplitter
from .image_view import ImageView
from .lattice_dialog import lattice_boxes
from .theme import TOKENS
# ⚠ **直接 import 真正的家，不走 `widgets` 那道轉出口。**
# `widgets.py` 把整個 UI 層轉出去 —— 為了這兩個名字走它，卡片庫、參數表單、
# 圖表設定全被拉進來：實測相依從 **27 支模組漲成 78 支**（16,589 → 48,495 行）。
# 而這兩個名字本來就住在下面這兩支，而且這個檔案本來就已經 import 它們了。
from .icons import apply_button_cursors
from .image_view import to_uint8

__all__ = [
    "PitchHelperWindow", "Bar", "AXES", "AXIS_X", "AXIS_Y",
    "AXIS_BOTH", "axis_flags", "lattice_periods", "px_text", "nm_text",
    "pitch_rows", "effective_period", "conf_tone", "agree_tone", "Override",
    "PITCH_UNSET", "PITCH_NOT_USED", "WINDOW_TITLE", "PHASE_PENDING",
    "BLURRED_BELOW",
    "VERDICT_OK", "VERDICT_BLURRED", "VERDICT_NONE", "VERDICT_TYPED",
    "VERDICT_CHECK", "VERDICT_BUSY_PERIOD", "VERDICT_BUSY_STACK",
    "CONF_TYPED", "TONE_GOOD", "TONE_WARN",
    "TONE_BAD", "CONF_GOOD_FROM", "AGREE_GOOD_FROM", "CELL_BOX",
    "BAR_W", "BAR_H", "candidate_periods", "candidate_label",
    "detail_rows", "trust_note", "MIN_CELLS_TO_TRUST",
    "MAX_CANDIDATES", "cells_along", "trim_to_inner", "NEXT_STEP",
    "MIN_CELLS_AFTER_TRIM", "run",
]

# ⚠ **不碰 widget 的那一半住在 `pitch_core`**（2026-09-22 拆的，F120 第十七
# 輪）：常數、判準、數字 → 字。兩個理由，而第二個比較重要 ——（1）這一支
# 2,199 行而上限 2,200；（2）**那一半是獨立出去的那個 app 要帶走的東西**
# （`docs/plans/F120-pitch-helper.md` §28）。
#
# ⚠ 這是一道**轉出口**：`ph.axis_flags` / `ph.PITCH_UNSET` 這些名字在測試與
# 其他模組裡到處都有人叫，而搬家不該連名字一起換 —— 那會把一次版面調整變成
# 一次全域改名。`__all__` 裡有它們，所以 ruff 認得這是轉出口，不必 noqa。
from .pitch_core import (
    AGREE_GOOD_FROM, AXES, AXIS_BOTH, AXIS_HELP, AXIS_ICONS, AXIS_LABELS,
    AXIS_X, AXIS_Y, BLURRED_BELOW, CONF_GOOD_FROM, CONF_TYPED,
    GRID_HEX, MAX_CANDIDATES, MIN_CELLS_AFTER_TRIM, MIN_CELLS_TO_TRUST,
    MIN_PERIOD_PX, NEXT_STEP, Override, PHASE_PENDING, PITCH_NOT_USED,
    PITCH_UNSET,
    TONE_BAD, TONE_GOOD, TONE_WARN, VERDICT_BLURRED, VERDICT_BUSY_PERIOD,
    VERDICT_BUSY_STACK, VERDICT_CHECK, VERDICT_NONE, VERDICT_OK,
    VERDICT_TYPED, WINDOW_TITLE, agree_tone, axis_flags, candidate_label,
    candidate_periods, cells_along, conf_tone, detail_rows, effective_period,
    lattice_periods, nm_text, pitch_rows, px_text, trim_to_inner, trust_note,
)


#: 那條長條的軌道有多長／多高（像素）。**長度是可讀性，不是裝飾**：
#: 92 px 的時候 92 分與 100 分在畫面上分不出來（見 :class:`Bar`）。
BAR_W = 150
BAR_H = 11


class Bar(QWidget):
    """一條 **0–100 的橫向長條**：填到那個分數的比例，顏色按分數綠／黃／紅。

    使用者 2026-09-21：「有一個橫向的長條（示意 0–100），然後裡面可能 80 分
    是綠的（填滿到 80%），60 分黃的（填滿到 60 分）。」

    ⚠ **軌道要夠長，不然「填到幾成」讀不出來。** 第一版 92 px 寬、8 px 高：
    92 分填出來是 85 px，跟填滿的 100 分**在畫面上分不出來** —— 而那個差別
    正是這條長條存在的理由。現在 :data:`BAR_W` / :data:`BAR_H`。

    ⚠ **顏色不是唯一的通道。** 數字一直都在（紅綠色覺缺陷者看不出顏色差別，
    而這一條是「這個答案可不可信」唯一的一眼答案）。這是 F117 U13 定下來的
    規矩：底色是第二個通道，不是唯一的。
    """

    def __init__(self, parent: Optional[QWidget] = None, width: int = 0):
        super().__init__(parent)
        self._frac = 0.0
        self._tone = TONE_WARN
        self._text = ""
        self._track = True
        self._w = int(width) or BAR_W
        self.setMinimumSize(self._w + 46, BAR_H + 8)

    def set_value(self, frac: float, tone: str, text: str) -> None:
        self._frac = float(np.clip(float(frac or 0.0), 0.0, 1.0))
        self._tone = str(tone)
        self._text = str(text)
        self._track = True
        self.update()

    def set_text_only(self, text: str) -> None:
        """**沒有分數可言的時候不要畫那條軌道。**

        使用者自己打的週期就是這一種：畫一條空軌道等於說「這個數字拿了 0 分」，
        而實情是「這個數字根本沒有被評分過」—— 兩件事在畫面上長得一樣就是說謊。
        """
        self._frac, self._tone, self._text = 0.0, TONE_WARN, str(text)
        self._track = False
        self.update()

    def value_text(self) -> str:
        """測試讀這個（不必去解析畫出來的像素）。"""
        return self._text

    def tone(self) -> str:
        return self._tone

    def paintEvent(self, e) -> None:  # Qt hook
        # ⚠ `paintEvent` 不准把例外往外丟：一個沒收尾的 painter 會讓**之後
        # 每一次重繪**都失敗，而壞掉的地方跟看到的地方不一樣
        # （`docs/PITFALLS.md` 第一列）。
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.Antialiasing, True)
            h = BAR_H
            y = (self.height() - h) // 2
            p.setPen(Qt.NoPen)
            if self._track:
                p.setBrush(QColor(TOKENS["border_default"]))
                p.drawRoundedRect(0, y, self._w, h, h / 2.0, h / 2.0)
                # ⚠ **0 分也要畫**（一顆紅點，寬度 = 高度）。這裡原本是
                # `if self._frac > 0`，於是 0 分畫出來是一條**空軌道** —— 跟
                # `set_text_only` 那個「沒有被評分過」長得一模一樣。而 0 分
                # 是這個視窗最需要講清楚的一格：使用者打了一個週期，圖在那個
                # 週期上完全不重複（實測打 45 對一張 60 的圖就是 0.0）。
                p.setBrush(QColor(_TONE_HEX[self._tone]))
                p.drawRoundedRect(0, y, max(h, int(self._w * self._frac)), h,
                                  h / 2.0, h / 2.0)
            x0 = (self._w + 8) if self._track else 0
            p.setPen(QColor(TOKENS["text_primary"] if self._track
                            else TOKENS["text_hint"]))
            p.drawText(x0, 0, self.width() - x0, self.height(),
                       int(Qt.AlignVCenter | Qt.AlignLeft), self._text)
        except Exception:
            swallowed("ui.pitch_helper.Bar.paintEvent")
        finally:
            p.end()


_TONE_HEX = {
    TONE_GOOD: TOKENS["chip_good_text"],
    TONE_WARN: TOKENS["warning"],
    TONE_BAD: TOKENS["danger"],
}


# --------------------------------------------------------------------------- #
# 背景執行緒
# --------------------------------------------------------------------------- #
class _PitchWorker(QThread):
    """量週期 → 疊 Golden Cell。**不在 GUI 執行緒跑** —— 4096² 要十幾秒。

    ⚠ **疊圖走 `build_golden_cell` 本人**（F120 第三版）。第一版只叫
    `choose_origin` 自己畫格線，而那繞過了整條路最有說服力的那一步：
    **把每一格疊起來**。使用者 2026-09-21 講的就是它 ——「仿照 AMAT 的
    golden cell，period 完美的話疊起來會很漂亮，period 錯的話疊起來糊糊的」。
    那條路已經在 repo 裡而且有測試，繞過它等於抄第二份。

    兩軸的週期**明講給它**（``px=``／``py=``），所以它不會再量一次
    （`build_golden_cell` 的 ``given`` 分支）—— 量已經在這裡做過，
    而且使用者可能自己打了一個。
    """

    stage = Signal(str)
    #: **週期量完了，證據還沒。** 急著要數字的人等的是這一刻，不是 `done`。
    #: 實測 4096² 上：量週期 2.14 s，而疊圖找相位還要 2.67 s —— 多等的那一半
    #: 等的是**證據**，不是答案。
    answer = Signal(object)              # MeasuredPeriod
    done = Signal(object, object, str)   # (MeasuredPeriod, GoldenCell, 錯誤)

    def __init__(self, image: np.ndarray, axis: str,
                 measured: Optional[Any] = None,
                 override: Override = (None, None), method: str = "mean",
                 skip_edges: bool = True, parent=None):
        super().__init__(parent)
        self._image = image
        self._axis = str(axis)
        self._measured = measured        # 有就不重量（只重疊）
        self._override = override
        self._method = str(method)       # mean / median（median 免疫稀疏缺陷）
        self._skip_edges = bool(skip_edges)
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:  # Qt hook
        try:
            m = self._measured
            if m is None:
                self.stage.emit("Measuring the period…")
                m = algo_template.measure_period(self._image)
                if not self._stop:
                    # ⚠ **先把答案送出去。** 底下的疊圖／相位搜尋是為了「憑什麼
                    # 相信它」，而那一段在 4096² 上要 2.67 s —— 讓一個已經算好
                    # 的數字在背景多躺兩秒半，是這個視窗最貴的一件事。
                    self.answer.emit(m)
            if self._stop:
                self.done.emit(None, None, "")
                return
            ex, ey = effective_period(m, self._override)
            flags = axis_flags(self._axis, ex, ey,
                               100.0 if self._override[0] else m.conf_x,
                               100.0 if self._override[1] else m.conf_y)
            gc = None
            if flags[0] or flags[1]:
                ux, uy = lattice_periods(self._image.shape[:2], ex, ey, flags)
                gc = algo_template.build_golden_cell(
                    self._image, px=ux, py=uy, method=self._method,
                    progress=self._tick)
                if self._skip_edges and gc is not None and gc.cell.size:
                    gc = self._without_edges(gc, ux, uy, flags)
        except Exception as e:           # 講出來，不要吞掉（鐵則 7 的 UI 版）
            self.done.emit(None, None, "Could not measure this image: %s" % e)
        else:
            if self._stop:
                # ⚠ **被停掉的那一份不准出去。** 上面那道 `_stop` 只擋在量週期
                # 之後、疊圖之前；`build_golden_cell` 吃的 `progress=self._tick`
                # 也回 `not self._stop`，所以停在疊圖中途的時候它會回一份
                # **只疊了一半、n_cells = 0** 的 GoldenCell —— 而那一份走到畫面
                # 上長得就是「Cells agree 空白、0 cells」，也就是「這個週期不
                # 成立」。實際踩法：4096² 疊十幾秒，中途改一個設定就換掉了。
                #
                # 這是 repo 既有的那條規矩（鐵則 11「被停掉的部分結果拒寫並講
                # 出來」）在這個視窗的版本。`_on_done` 收到 `m is None` 會直接
                # 忽略，畫面因此停在上一個**完整**的答案上。
                self.done.emit(None, None, "")
                return
            self.done.emit(m, gc, "")

    def _without_edges(self, gc: Any, ux: float, uy: float,
                       flags: Tuple[bool, bool]) -> Any:
        """把最外一圈格子拿掉，**只重疊一次，不重跑相位搜尋**。

        相位已經知道了（`gc.origin`），而切掉的那一圈是沿著格線切的 —— 新的
        左上角就落在一條格線上，所以在那一塊裡原點是 (0, 0)。因此這裡叫的是
        `golden.stack_cells` / `stack_agreement` **本人**（`build_golden_cell`
        內部叫的也是這兩支），不是再跑一次整支 —— 相位搜尋在 4096² 要 5 秒，
        而它的答案不會因為少了一圈格子而改變。
        """
        from pitchapp.core.algo import golden as algo_golden
        box = trim_to_inner(self._image.shape[:2], ux, uy, gc.origin, flags)
        if box is None:
            return gc                       # 格子太少，拿掉不划算（見 `trim_to_inner`）
        x0, y0, x1, y1 = box
        inner = self._image[y0:y1, x0:x1]
        ix, iy = int(round(ux)), int(round(uy))
        before = gc                         # 剪完不划算的話要回得去（見下面）
        cell = algo_golden.stack_cells(inner, ix, iy, method=self._method)
        agree = algo_golden.stack_agreement(inner, ix, iy)
        n = len(algo_golden.tile_coords(inner.shape, ix, iy))
        if n < MIN_CELLS_AFTER_TRIM:
            # ⚠ **剪完什麼都不剩的話，要回到沒剪的那一份，不是報一個 0。**
            # `trim_to_inner` 已經擋掉格數太少的情形，但它算的是「沿著哪一軸
            # 剪幾格」，答不出「剪完那一塊裝不裝得下一個 cell」。而 0 格疊出來
            # 的 `agreement` 是 0.00，畫面上長得跟「這個週期是錯的」一模一樣
            # —— **一個算不出來的答案不准假裝成一個否定的答案**（同卡片那條
            # 「算不出來的那一格不寫」）。
            return before
        gc.cell, gc.agreement = cell, agree
        gc.ghosting, gc.lap_var, _e = algo_golden.ghosting_score(cell)
        gc.n_cells = n
        gc.trimmed = True                   # 畫面上要講出來（少了幾格是事實）
        return gc

    def _tick(self, stage: str, done: int = 0, total: int = 0) -> bool:
        """進度講到哪一步 **而且講到第幾格** —— 7680² 要十幾秒，一條跑不完的
        進度條答不出「它還在動嗎」。"""
        self.stage.emit("%s  %d/%d" % (stage, done, total) if total > 1
                        else str(stage))
        return not self._stop


# --------------------------------------------------------------------------- #
# 主視窗
# --------------------------------------------------------------------------- #
#: 疊出來那張 cell 顯示成多大（放大到這麼多像素見方，保持長寬比）。
#: 一格常常只有 40–80 px，原尺寸在螢幕上小到看不出糊不糊 —— 而「看得出糊不糊」
#: 正是它存在的唯一理由。150 是「放大得夠看出邊緣」與「右欄還排得下一致性
#: 那一格」之間量出來的那個值。
#: ⚠ **150 → 175**（第十輪）。把證據搬到答案底下之後，面板短了，底下多出
#: 122 px 的留白 —— 而這張圖是**唯一一個「多幾個像素就是多一點證據」**的東西
#: （使用者要從它判斷邊緣是清楚還是糊的）。
#: ⚠ **165 是量出來的，不是挑的。** 右欄那一條 Bar 要 118 ＋ 46 的數字欄 =
#: 164，而 Qt 在空間不夠時**就是會重疊，不會報錯**（這個面板第一版踩過）。
#: 實測：175 的時候圖片右緣 x=984、右欄從 x=987 開始 —— **只剩 3 px**，
#: 換一個字型或 DPI 就疊了。165 留 13 px。
CELL_BOX = 165


class PitchHelperWindow(QMainWindow):
    """一張圖 → 它的 cell period，以及兩個看得出對不對的畫面。

    版面（使用者 2026-09-21：「user 進來是要 1 min 內解決問題，而不是找按鍵
    還要看一堆文字」）
    ------------------------------------------------------------------------
    第一版是四個編號方塊由上而下，每一塊都帶著一段說明 —— 讀完才知道要按哪裡。
    現在是**一條細工具列 ＋ 左圖右答案**，而右邊由上而下就是使用者的問題順序：

        pitch 是多少 → 哪個方向 → 不對的話我自己改 → 憑什麼相信它

    三條規則：

    * **畫面上不放使用者不必讀的字。** 說明退到 tooltip（同 `template_dialog`
      「第一版把每支工具寫成一句話擺在畫面上，使用者回報介面文字太多」）。
    * **警告只在有事的時候出現。** 第一版有一塊常駐的「What it decided」，
      而最常見的情形是它空著 —— 使用者 2026-09-21 的原話是「這我不知道可以
      幹嘛？」。沒有話要說的時候整條不佔位置。
    * **每一個分數都配一條橫條**（綠／黃／紅），數字照樣在（U13：顏色不是
      唯一的通道）。
    """

    #: 量完一次：(MeasuredPeriod, GoldenCell 或 None)。
    measured = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # ⚠ **就叫 `Pitch helper`，後面不掛 d4t**（使用者 2026-09-22 指定）。
        # Studio 的標題帶著主程式的名字是因為它**是**主程式；這一個不是 ——
        # 它的下一步是完全獨立成自己的應用程式（`docs/plans/F120-…` §28），
        # 那一天標題裡的 `d4t` 會變成一句假話。現在就不要先寫上去。
        self.setWindowTitle(WINDOW_TITLE)
        # **自己的圖示**（F120）：工作列上要分得出這不是 Studio。
        self.setWindowIcon(branding.pitch_icon())

        self._full: Optional[np.ndarray] = None      # 載進來的原圖
        self._work: Optional[np.ndarray] = None      # 裁過的（量的就是它）
        self._crop: Optional[Tuple[int, int, int, int]] = None
        self._name = ""
        self._m: Optional[Any] = None                # 上一次的 MeasuredPeriod
        self._gc: Optional[Any] = None               # 上一次疊出來的 Golden Cell
        self._worker: Optional[_PitchWorker] = None
        #: 量尺量到的 ``(axis, 長度 px)``；沒量就 None。
        self._measured: Optional[Tuple[str, float]] = None
        #: `_fill_warning` 這一輪有沒有話要說 —— 狀態行的判準（見 `verdict`）。
        self._has_warning = False

        root = QWidget(self)
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(8)
        outer.addLayout(self._toolbar())

        # ⚠ **左右由使用者拉，不是我挑一個數字。** 右欄本來寫死 380，而那個
        # 數字是在「四顆膠囊排得下」量出來的 —— 它答不出「這張圖有多寬」。
        # 一張 4096² 的 patch 跟一張 900×700 的 SEM 要的比例不一樣，而只有
        # 坐在那裡的人知道他現在在看哪一種。
        # 380 因此從**固定寬**變成**最小寬**（那個量測仍然成立：低於它膠囊
        # 會擠成兩排、疊圖那一格會跟旁邊的說明重疊）。
        # `HairlineSplitter` 是這個 repo 唯一准用的分隔器（CLAUDE.md §4：
        # `d4t/ui` 裡不准直接用 Qt 那一個，有測試數像素）。
        # ⚠ 這一句本來把那個被禁的呼叫**逐字寫出來**當說明，而
        # `test_ui_splitters` 是**逐行 grep 原始碼**的 —— 於是一句解釋規矩的
        # 註解自己違反了那條規矩。守門的東西不分辨程式碼跟散文，那是它保守的
        # 地方，不是它的 bug。
        split = HairlineSplitter(Qt.Horizontal, root)
        split.addWidget(self._image_side())
        split.addWidget(self._answer_side())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setCollapsible(0, False)     # 圖收掉的話量尺就沒地方拉了
        split.setCollapsible(1, False)     # 答案收掉的話這個視窗就沒有輸出了
        self.split = split
        outer.addWidget(split, 1)

        self.warn = QLabel("", root)
        self.warn.setObjectName("paramHint")
        self.warn.setWordWrap(True)
        self.warn.setVisible(False)
        outer.addWidget(self.warn)

        self.setAcceptDrops(True)
        self._bind_keys()
        fit_screen.fit(self, 1180, 780)
        apply_button_cursors(self)
        self._refresh()

    # -- 鍵盤 ---------------------------------------------------------------
    #: 快捷鍵 → 做什麼。**改這裡就好** —— 綁定、提示文字、守門的測試都讀它，
    #: 所以一個鍵不會出現「綁了但沒人講」或「講了但沒綁」。
    SHORTCUTS = (
        ("Ctrl+O", "open_image"),
        ("Ctrl+V", "paste_image"),
        # ⚠ Ctrl+C 走 `copy_focused_or_answer`，不直接接 X 那一顆 —— 見那一支。
        ("Ctrl+C", "copy_focused_or_answer"),
        ("Ctrl+Shift+C", "copy_y"),
    )

    def _bind_keys(self) -> None:
        """把 :data:`SHORTCUTS` 綁上去。

        為什麼是 `QShortcut` 而不是 `keyPressEvent`
        ------------------------------------------------------------------
        `keyPressEvent` 只在**沒有子元件吃掉那顆鍵**的時候才會跑到，而這個
        視窗上半部全是輸入框與按鈕 —— 使用者剛剛打完 pixel size，焦點就在
        spin box 裡，那一刻 Ctrl+C 永遠到不了視窗。`QShortcut`（預設
        ``WindowShortcut``）比 key event **先**處理，所以「我看到數字了，
        Ctrl+C」在畫面任何地方都成立。

        ⚠ 這也是為什麼 Ctrl+C 不能直接接 Copy X：見
        :meth:`copy_focused_or_answer`。
        """
        self._shortcuts: List[QShortcut] = []
        for seq, name in self.SHORTCUTS:
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(getattr(self, name))
            self._shortcuts.append(sc)

    @classmethod
    def key_for(cls, action: str) -> str:
        """那個動作綁在哪一顆鍵上。**提示文字讀這個，不自己抄一份字** ——
        抄出來的那一份哪天沒跟上，畫面會教使用者按一顆沒有綁的鍵。"""
        for seq, name in cls.SHORTCUTS:
            if name == action:
                return seq
        return ""

    def copy_y(self) -> None:
        """Ctrl+Shift+C。**是一支方法不是 lambda** —— :data:`SHORTCUTS` 要能
        被測試逐條走過去，而一個名字查得到、一個 lambda 查不到。"""
        self.copy_axis(1)

    def copy_focused_or_answer(self) -> None:
        """Ctrl+C：**輸入框裡選著字的時候複製那段字**，其餘時間複製答案。

        ⚠ 少了這道分支，Ctrl+C 就從輸入框手上被搶走了：`QShortcut` 比
        `QLineEdit` 自己的標準鍵動作先處理，所以使用者在 pixel size 那一格裡
        選了 `45` 按 Ctrl+C，剪貼簿上會是**週期**。一個到處都能用的快捷鍵
        不該偷走一個更小、更明確的動作。
        """
        w = QApplication.focusWidget()
        le = w.lineEdit() if isinstance(w, QAbstractSpinBox) else (
            w if isinstance(w, QLineEdit) else None)
        if le is not None and le.hasSelectedText():
            le.copy()
            return
        self.copy_axis(0)

    # -- 版面 ---------------------------------------------------------------
    def _toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        # ⚠ 圖示走 `icons.GlyphButton`（自繪），**不是字元**：廠內是 Windows，
        # 而 Segoe UI 蓋不到那些符號 —— 退字型之後同一排每顆的大小與 baseline
        # 都不一樣，最壞是豆腐框，而我們在開發機上看不到
        # （`draw_glyph_icon` 的檔頭逐字說明了這件事）。
        self.btn_open = GlyphButton(
            "image", "Open image…",
            "Open an image file (%s)." % PitchHelperWindow.key_for("open_image"),
            self)
        self.btn_open.clicked.connect(self.open_image)
        self.btn_paste = GlyphButton(
            "paste", "Paste",
            "Paste an image from the clipboard (%s)."
            % PitchHelperWindow.key_for("paste_image"), self)
        self.btn_paste.clicked.connect(self.paste_image)
        # ⚠ **就叫 `Crop`，沒有刪節號**（使用者 2026-09-22 指定）。
        # 這個 app 其他會開對話框的鈕都帶 `…`（`Open image…`、`Templates…`、
        # `Browse…`）—— 那是一個慣例，而使用者在這一顆上把它關掉了。
        # 留這段註解是為了不要有人「順手修回來」。
        self.btn_crop = GlyphButton(
            "crop", "Crop",
            "Measure from one part only — leave out the defect, scribe lines "
            "and the scale bar. They are not the repeating layout.", self)
        self.btn_crop.clicked.connect(self.ask_crop)
        # **入口要長得像入口。** 三顆一樣灰的鈕，使用者第一眼不知道該按哪一個
        # —— 而這個視窗只有一個起點。
        self.btn_open.setObjectName("primary")   # 藍的那一顆（見 theme 的 #primary）
        for b in (self.btn_paste, self.btn_crop):
            b.setProperty("variant", "secondary")
        for b in (self.btn_open, self.btn_paste, self.btn_crop):
            row.addWidget(b)
        # ⚠ **空的時候就空著。** 這裡本來也寫「Drop an image here, open one, or
        # paste one.」—— 而畫布正中間現在講的是同一句話。同一則訊息出現兩次，
        # 使用者會先花一秒確認那是不是兩件事。它的工作是載入之後講檔名與尺寸。
        self.lab_source = QLabel("", self)
        self.lab_source.setObjectName("paramHint")
        row.addWidget(self.lab_source, 1)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(150)
        self.progress.setVisible(False)
        row.addWidget(self.progress)
        return row

    def _image_side(self) -> QWidget:
        box = QWidget(self)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.view = ImageView(box)
        lay.addWidget(self.view, 1)
        # ⚠ **格線走兩色線**（深色襯底 ＋ 亮芯）。理由是量出來的，不是美感：
        # 目前這條 accent 藍在中灰上的 WCAG 對比是 **1.04** —— 等於不存在，
        # 而一條在某些地方看不見的格線，比沒有格線更糟（使用者會以為那裡沒有
        # 被切到）。完整的數字在 `ImageView.set_overlay_look`。
        self.view.set_overlay_look(GRID_HEX, cased=True)
        # **要做的那件事，寫在要用到的那塊空間裡。** 預設的 `(no image)` 只
        # 描述現況；而這個視窗空著的時候，唯一要做的事本來寫在工具列 11px 的
        # 灰字裡 —— 700×700 的畫布上卻只有一句「沒有影像」。
        self.view.set_empty_text(
            "Drop an image here\n\nor use Open image… / Paste (Ctrl+V)")
        self.view.measured.connect(self._on_measured)
        row = QHBoxLayout()
        self.chk_grid = QCheckBox("Cut lines", box)
        self.chk_grid.setChecked(True)
        self.chk_grid.setToolTip("Draw the cell boundaries on the image.")
        # ⚠ **這一顆的方塊就是色標。** 它旁邊寫著 "Cut lines"，而那些線是青色
        # 的 —— 勾選框卻是 app 的 accent 藍，於是那個方塊被讀成「線是藍的」。
        # 另外兩顆勾選框（Ignore defects／Skip edge cells）維持 accent：
        # 它們開關的是行為，不是畫面上某個有顏色的東西。
        self.chk_grid.setStyleSheet(
            "QCheckBox::indicator:checked{background:%s;border-color:%s;}"
            % (GRID_HEX, GRID_HEX))
        self.chk_grid.toggled.connect(lambda _on: self._draw())
        row.addWidget(self.chk_grid)

        # ---- 量尺（F120 第九輪，使用者：「畫布上也添加量尺功能」）----------
        # ⚠ **它不是「再算一次 period」，它是「我自己量一段」。** 兩者在畫面上
        # 要分得出來：量尺是綠的（`ImageView._paint_measure` 本人），格線是藍的。
        self.btn_ruler = GlyphButton("ruler", "Ruler", parent=box)
        self.btn_ruler.setCheckable(True)
        self.btn_ruler.setProperty("variant", "secondary")
        self.btn_ruler.setToolTip(
            "Drag on the image to measure a distance. Turn it on and the "
            "left button measures instead of panning.")
        self.btn_ruler.toggled.connect(self._on_ruler)
        row.addWidget(self.btn_ruler)
        # **量到的數字要用得掉。** 只印一個長度的尺，使用者還是得自己把它打進
        # 週期欄 —— 而那一格就在旁邊，中間隔著一次手抄。
        self.btn_use_ruler = QPushButton("Use as period", box)
        self.btn_use_ruler.setProperty("variant", "secondary")
        self.btn_use_ruler.setToolTip(
            "Put what you just measured into the period box for that axis.")
        self.btn_use_ruler.clicked.connect(self.use_measured)
        self.btn_use_ruler.setVisible(False)
        row.addWidget(self.btn_use_ruler)

        self.caption = QLabel("", box)
        self.caption.setObjectName("paramHint")
        row.addWidget(self.caption, 1)
        lay.addLayout(row)
        return box

    # -- 量尺 ---------------------------------------------------------------
    def _on_ruler(self, on: bool) -> None:
        self.view.set_measure_mode(bool(on))
        if not on:
            self._measured = None
            self.btn_use_ruler.setVisible(False)
            self._draw()                      # 帶子沒了，說明也要跟著回去
        else:
            self._say("Drag across the image to measure. "
                      "Release and the reading stays.")

    def _on_measured(self, axis: str, a: float, b: float) -> None:
        span = abs(float(b) - float(a))
        self._measured = (str(axis), span)
        self.btn_use_ruler.setVisible(span >= MIN_PERIOD_PX)
        self.btn_use_ruler.setText(
            "Use as %s period" % ("X" if axis == "x" else "Y"))
        self._say_caption("")          # 內容由 `_say_caption` 自己從 `_measured` 生

    def measured_span(self) -> Optional[Tuple[str, float]]:
        """量尺現在量到的 ``(axis, 長度 px)``（沒量就 None）。測試讀這個。"""
        return self._measured

    def use_measured(self) -> None:
        """把量到的那一段**填進對應那一軸的週期欄**。

        ⚠ 填的是 `spin_px`／`spin_py`，走的是既有的「使用者自己打一個週期」
        那條路（`_on_override`）—— **不是第三條算週期的路**。所以格線、疊圖、
        信心（`confidence_at`）全部跟著重算，而且跟手打的完全一樣。
        """
        if self._measured is None:
            return
        axis, span = self._measured
        if span < MIN_PERIOD_PX:
            return
        (self.spin_px if axis == "x" else self.spin_py).setValue(float(span))
        # **用掉之後就收起來。** 那個數字現在住在週期欄裡，畫面上不需要兩份；
        # 而留著一顆「Use as period」會讓人以為還沒生效。
        self._clear_ruler()
        self.btn_ruler.setChecked(False)

    def _answer_side(self) -> QWidget:
        """右欄：**一條 header ＋ 三張卡**（F120 第十七輪）。

        順序是使用者定的：「理想上應該要先有圖（因為你要確認 GC 跟 pitch 是不是
        正確的），然後中間才是答案」。所以

            header  圖示＋名字  |  現在的狀態
            卡 1    這看起來像一個 cell 嗎     ← 疊出來的那一格＋它的分數
            卡 2    The period                ← 答案
            卡 3    不是這個 cell？            ← 軸向、覆寫、怎麼疊、細節

        ⚠ **一欄只有一種對齊。** 上一版是上半置中、下半靠左，而「排版很奇怪」
        量出來就是這件事：y=0…158 置中、y=164 以下靠左，眼睛找不到一條穩定的
        垂直線。現在每張卡內部一律靠左，**只有那個大數字置中** —— 它是結論，
        該獨佔中軸。

        ⚠ **設定不准住在證據裡。** `Ignore defects` / `Skip edge cells` 本來擠在
        證據卡的右下角，而它們改的是「下一次怎麼疊」不是「這次疊得怎麼樣」。

        高度是量出來的：這個排法 664 px，而 1366×768 的筆電上右欄約 700。
        圖獨佔一塊的原版是 742（會被切），並排版是 595。
        """
        box = QWidget(self)
        # ⚠ **這個寬度是量出來的，不是挑的。** 340 的時候：四顆膠囊擠成兩排、
        # 疊出來那一格跟旁邊的說明**畫在一起**（Qt 在空間不夠時就是會重疊，
        # 不會報錯 —— 那是版面 bug 最常見的長相）。380 是膠囊排得下、cell ＋
        # 一致性那一欄也排得下的寬度，現在是**最小**寬不是固定寬。
        box.setMinimumWidth(380)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self._header_row(box))
        lay.addWidget(self._proof_card(box))
        lay.addWidget(self._period_card(box))
        lay.addWidget(self._fix_card(box))
        lay.addStretch(1)
        return box

    def _header_row(self, parent: QWidget) -> QWidget:
        """圖示＋名字 ｜ 現在的狀態。

        ⚠ **右邊那半不是裝飾。** 畫面上有三條 bar、一張圖、一堆數字，卻沒有
        任何一個地方用一句話說「所以這次到底成不成立」—— 那就是這一行。而它
        也是「答案先到、疊圖後到」那兩秒半唯一有話說的地方。

        ⚠ 文字 ＋ 色調**兩個通道**（F117 U13）：顏色是第二個通道，不是唯一的。
        """
        row = QWidget(parent)
        h = QHBoxLayout(row)
        h.setContentsMargins(2, 0, 2, 0)
        h.setSpacing(8)
        icon = QLabel(row)
        icon.setPixmap(branding.pitch_icon().pixmap(20, 20))
        self.lab_name = QLabel(WINDOW_TITLE, row)
        self.lab_name.setObjectName("pitchName")
        h.addWidget(icon)
        h.addWidget(self.lab_name)
        h.addStretch(1)
        self.lab_state_mark = QLabel("", row)
        self.lab_state = QLabel("", row)
        for w in (self.lab_state_mark, self.lab_state):
            w.setObjectName("pitchState")
            h.addWidget(w)
        return row

    def _proof_card(self, parent: QWidget) -> QWidget:
        """**疊起來的那一格** —— 這個視窗最有說服力的一塊，而它在最上面。

        使用者 2026-09-21：「仿照 AMAT 的 golden cell，將 period 週期用格線切完
        後，將所有的每個 cell 放在一起，如果取的 period 是完美的，他會有疊加
        Frame 的效果，GC 影像會很漂亮；如果 period 錯，格線切的差，疊起來就會
        糊糊的。」2026-09-22：「理想上應該要先有圖。」

        ⚠ **旁邊那個數字是 `agreement` 不是 sharpness**，而那個選擇是量出來的
        （F40）：`ghosting_score`（銳利度）只看疊完那一張圖，**看不到疊進去的
        那幾格**，所以分不出「因為對齊了所以銳利」與「因為兩個鬼影各帶一組邊
        所以銳利」—— 相位錯掉的 stack 會拿到**更高**的分數（實測：錯的 76.1
        比正確的 68.4 高），而純雜訊在 σ=60 拿 99.4。`stack_agreement` 問的是
        那幾格**彼此**對得多齊，無量綱、跨影像可比，所以它才是那個可以配門檻
        的數字。**人眼看那張圖 ＋ 這個數字**，兩個一起才完整。
        """
        card = QGroupBox("Does this look like one cell?", parent)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(12)
        self.cell_view = QLabel(card)
        self.cell_view.setFixedSize(CELL_BOX, CELL_BOX)
        self.cell_view.setAlignment(Qt.AlignCenter)
        # ⚠ 線粗與圓角**吃 token**（`hairline` / `radius_sm`），不寫 1px / 4px
        # —— 同 U12 那條「字級、線粗、圓角只有一個家」（`tests/test_ui_design_
        # tokens.py` 會擋）。螢幕變了要一起改，而「一起」的前提是只有一個地方。
        self.cell_view.setStyleSheet(
            "background:%s;border:%s solid %s;border-radius:%s;color:%s;"
            % (TOKENS["bg_page"], TOKENS["hairline"], TOKENS["border_default"],
               TOKENS["radius_sm"], TOKENS["text_hint"]))
        self.cell_view.setText(PITCH_UNSET)
        self.cell_view.setToolTip(
            "Every cell the grid cut, averaged on top of each other. Crisp "
            "means they landed on each other, so the period is right. Blurred "
            "or doubled means it is not. Click to see it bigger.")
        self.cell_view.setCursor(Qt.PointingHandCursor)
        self.cell_view.mouseReleaseEvent = lambda _e: self.show_cell_big()
        lay.addWidget(self.cell_view, 0, Qt.AlignTop)
        side = QVBoxLayout()
        side.setSpacing(2)
        cap = QLabel("Cells agree", card)
        cap.setObjectName("paramHint")
        side.addWidget(cap)
        self.bar_agree = Bar(card, width=118)
        side.addWidget(self.bar_agree)
        self.lab_stack = QLabel("", card)
        self.lab_stack.setObjectName("paramHint")
        self.lab_stack.setWordWrap(True)
        side.addWidget(self.lab_stack)
        side.addStretch(1)
        lay.addLayout(side, 1)
        return card

    def _period_card(self, parent: QWidget) -> QWidget:
        """答案本人。

        ⚠ 字級走 **QSS 的 objectName**（`pitchAnswer`），不是 `setFont()`
        —— theme 的 ``* { font-size }`` 會蓋掉 per-widget 的 QFont，而 Qt
        不會抱怨。F120 連三輪「把答案放大」就是這樣安靜地沒有生效
        （量出來一直是 13px，跟旁邊的說明一樣大）。
        """
        card = QGroupBox("The period", parent)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)
        self._cells: List[List[QLabel]] = []
        self._bars: List[Bar] = []
        self._tags: List[QLabel] = []
        self.lab_big = QLabel(PITCH_UNSET, card)
        self.lab_big.setObjectName("pitchAnswer")
        self.lab_big.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        lay.addWidget(self.lab_big)
        self.lab_um = QLabel("", card)
        self.lab_um.setObjectName("pitchAnswerSub")
        self.lab_um.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        lay.addWidget(self.lab_um)
        # 兩軸的信心**跟著數字**，而一致性跟著上面那張圖 —— 每一條 bar 跟它
        # 評的東西在一起。上一版三條擠在證據卡裡，於是「數字的信心」看起來
        # 像是在評那張圖。
        self.grid_answer = QGridLayout()
        self.grid_answer.setHorizontalSpacing(8)
        self.grid_answer.setVerticalSpacing(2)
        for i, nm in enumerate(("Repeat along X", "Repeat along Y")):
            # 那個軸向標籤本人就是這一行標題：`_fill_answer` 靠
            # `self._tags[i]` 的顯示／隱藏決定「這一軸算不算數」（X only 時
            # Y 整列要消失）。另外做一個的話那個邏輯只管到一半，而沒被加進
            # 任何 layout 的那一個會浮在 (0,0) —— 實拍就是一個 `x` 飄在最大
            # 的那個答案旁邊。
            tag = QLabel(nm, card)
            tag.setObjectName("paramHint")
            tag.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            bar = Bar(card, width=100)
            self._tags.append(tag)
            self._bars.append(bar)
            self._cells.append([QLabel(card), QLabel(card)])   # 舊介面的殘留
            self.grid_answer.addWidget(tag, i, 0)
            self.grid_answer.addWidget(bar, i, 1)
        self.grid_answer.setColumnStretch(1, 1)
        lay.addLayout(self.grid_answer)
        # ---- pixel size ＋ 把答案帶走 ---------------------------------------
        # ⚠ pixel size **緊貼著它換算出來的那一行**。它本來有自己的 `Units`
        # 區段，排在整個面板的最下面 —— 而它產生的 `0.150 µm` 在最上面。
        # 量出來是 **552 px**：一個輸入跟它的效果能隔多遠就隔多遠。
        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.spin_nm = QDoubleSpinBox(card)
        self.spin_nm.setRange(0.0, 1e6)
        self.spin_nm.setDecimals(3)
        self.spin_nm.setSingleStep(0.1)
        self.spin_nm.setSuffix(" nm/px")
        # ⚠ **這句話要塞得進那個框。** 原本寫 `pixel size not known`（132 px），
        # 而框裡真正留給字的只有 112 px —— 畫面上長出來的是
        # **`el size not known`**，一句看不懂又有點嚇人的話。
        self.spin_nm.setSpecialValueText("set pixel size")
        self.spin_nm.setKeyboardTracking(False)   # 打字中途不重算
        self.spin_nm.setToolTip(
            "How many nanometres one pixel is, from the tool's settings. Fill "
            "it in and the pitch also comes out in micrometres.")
        # ⚠ **不要跟 Copy 一樣重。** 它是答案的一個附註（「這是用什麼換算的」），
        # 不是一個動作。
        self.spin_nm.setObjectName("pitchPixelSize")
        self.spin_nm.setMaximumWidth(170)
        self.spin_nm.valueChanged.connect(lambda _v: self._fill_answer())
        tools.addWidget(self.spin_nm)
        tools.addStretch(1)
        # ⚠ **一軸一顆，而且複製的是光禿禿的數字**（使用者 2026-09-21：
        # 「複製應該要能直接複製數字（不包含單位），X 跟 Y 都要有複製鍵」）。
        # 那一句指出了一件很具體的事：這個數字的去處是 `Cell W` / `Cell H`
        # **兩個各自的輸入框**，而原本那顆 Copy 給的是
        # `X 60 px (0.150 µm)  Y 44 px (0.110 µm)` —— **一個貼進任何一格都會
        # 被拒絕的字串**。能帶走答案跟能用答案是兩回事。
        self._copy_buttons: List[QPushButton] = []
        for i, axis_name in enumerate(("X", "Y")):
            b = GlyphButton("copy", "Copy %s" % axis_name, parent=card)
            b.setProperty("variant", "secondary")
            b.setMaximumWidth(108)
            b.clicked.connect(lambda _c=False, k=i: self.copy_axis(k))
            tools.addWidget(b)
            self._copy_buttons.append(b)
        lay.addLayout(tools)
        # 舊名字留著（測試與 `_fill_answer` 讀它），指向 X 那一顆。
        self.btn_copy = self._copy_buttons[0]
        # **「然後呢」要有人講。** 這個視窗的產出是一個**要拿去別處用**的數字，
        # 而畫面上本來沒有任何一句說它要貼到哪。名字是**真的那個名字**：
        # `template_dialog` 的視窗標題是 "Template & regions"，那兩格叫
        # `Cell W` / `Cell H` —— 見 `NEXT_STEP` 的說明（我第一版寫錯過）。
        self.lab_next = QLabel(NEXT_STEP, card)
        self.lab_next.setObjectName("paramHint")
        self.lab_next.setWordWrap(True)
        self.lab_next.setVisible(False)
        lay.addWidget(self.lab_next)
        return card

    def _fix_card(self, parent: QWidget) -> QWidget:
        """不對的話怎麼改 —— 軸向、覆寫、候選，以及**怎麼疊**。

        ⚠ `Ignore defects` / `Skip edge cells` 住在這裡而不是證據卡裡：它們改
        的是「下一次怎麼疊」，是設定不是證據。它們本來擠在證據卡的右下角，
        而那讓那張卡左右兩半高度對不起來。
        """
        card = QGroupBox("Not the cell you want?", parent)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)
        self.chips_axis = ChoiceChips(AXES, AXIS_ICONS, AXIS_BOTH,
                                      helps=AXIS_HELP, labels=AXIS_LABELS,
                                      parent=card)
        self.chips_axis.changed.connect(self._on_axis)
        lay.addWidget(self.chips_axis)

        fix = QHBoxLayout()
        fix.setSpacing(4)
        self.spin_px = self._period_spin(card, "across")
        self.spin_py = self._period_spin(card, "down")
        fix.addWidget(self.spin_px)
        fix.addWidget(QLabel("×", card))
        fix.addWidget(self.spin_py)
        self.btn_double = QPushButton("×2", card)
        self.btn_double.setToolTip(
            "Double both — for when one cell of yours is two of the repeats it "
            "measured (two MG lines making the unit you compare).")
        self.btn_double.clicked.connect(self._on_double)
        self.btn_reset = GlyphButton("undo", "Reset", parent=card)
        self.btn_reset.setToolTip("Back to the measured period.")
        self.btn_reset.clicked.connect(self._on_reset)
        fix.addStretch(1)      # 兩格週期靠左成一對，×2／Reset 靠右
        for b, cap in ((self.btn_double, 46), (self.btn_reset, 86)):
            b.setProperty("variant", "secondary")
            # ⚠ Reset 現在左邊多了一個圖示格，64 會把字切成 "Res…"。
            # 寬度跟著內容走，不是兩顆抄同一個數字。
            b.setMaximumWidth(cap)
            fix.addWidget(b)
        lay.addLayout(fix)

        # ---- 取錯了怎麼辦：諧波上的其他可能，點一下就套用 -------------------
        self.row_try = QHBoxLayout()
        self.row_try.setSpacing(4)
        self.lab_try = QLabel("Or try", card)
        self.lab_try.setObjectName("paramHint")
        self.row_try.addWidget(self.lab_try)
        self._try_buttons: List[QPushButton] = []
        self.row_try.addStretch(1)
        lay.addLayout(self.row_try)

        # ---- 怎麼疊 ＋ 細節：同一排（那一排本來各佔一行，花掉 40 px）-------
        last = QHBoxLayout()
        last.setSpacing(14)
        # **大圖中間常常就是缺陷本體，而 mean 會把它抹進 GC。** median 對稀疏
        # 缺陷免疫（`golden.stack_cells` 的 `method`），所以那是一個勾選，
        # 不是一個要去別的地方改的設定。
        self.chk_median = QCheckBox("Ignore defects", card)
        self.chk_median.setToolTip(
            "Stack with the median instead of the mean. A defect sitting in "
            "one cell then does not smear into the stacked picture.")
        self.chk_median.toggled.connect(lambda _on: self.remeasure(reuse=True))
        # 邊界那一圈：**量出來的**（帶掃描邊緣效應的合成圖 0.872 → 0.980，
        # 乾淨影像 0.980 → 0.980），而使用者也說「不太想放」。所以預設打開。
        self.chk_edges = QCheckBox("Skip edge cells", card)
        self.chk_edges.setChecked(True)
        self.chk_edges.setToolTip(
            "Leave out the ring of cells touching the image border. The scan "
            "edge is often brighter, darker or noisier than the rest, and "
            "those cells drag the stacked picture down. Costs nothing on a "
            "clean image.")
        self.chk_edges.toggled.connect(lambda _on: self.remeasure(reuse=True))
        last.addWidget(self.chk_median)
        last.addWidget(self.chk_edges)
        last.addStretch(1)
        # ---- 細節：**預設收起來** -------------------------------------------
        # 使用者要得到「每個方法的分數」，但同一輪也說了「不要看一堆文字」。
        # 兩件事只有一種解法：**要查的那天它在，平常不佔畫面。**
        self.btn_details = QPushButton("▸  Details", card)
        self.btn_details.setProperty("variant", "secondary")
        # ⚠ **不要橫跨整欄。** 量出來它本來是 411 × 30 = **13.7 : 1** ——
        # 而一個又寬又扁的盒子會讓裡面的字**看起來被拉長**（實際上沒有：
        # 量過字型的 stretch 是 1.0000，QSS 裡也沒有 font-stretch）。
        # 使用者回報「按鈕有點扁、文字有點被拉長」，病根是這個長寬比。
        self.btn_details.setMaximumWidth(124)
        self.btn_details.setCheckable(True)
        self.btn_details.setStyleSheet("text-align:left;")
        self.btn_details.toggled.connect(self._on_details)
        last.addWidget(self.btn_details)
        lay.addLayout(last)
        self.details = QLabel("", card)
        self.details.setObjectName("paramHint")
        self.details.setTextFormat(Qt.RichText)
        # ⚠ 沒有這一行的話那段說明會被右邊界切掉（"the number ir…"）。
        self.details.setWordWrap(True)
        self.details.setVisible(False)
        lay.addWidget(self.details)
        return card

    def _period_spin(self, box: QWidget, axis: str) -> QDoubleSpinBox:
        """一格「我自己來」的週期。**0 ＝ 沒打，用量到的那個。**

        ⚠ 小數要收得下（`setDecimals(1)`）：F105 之後週期可以是 79.5，而
        79.5 對 79 在 4000 px 上差 25 px。
        """
        sp = QDoubleSpinBox(box)
        sp.setRange(0.0, 8192.0)
        sp.setDecimals(1)
        sp.setSingleStep(1.0)
        # ⚠ 84 的時候 ``specialValueText`` 被切成 "easured" —— 一個**看起來像
        # 壞掉**的畫面，而它其實只是少了 14 px。
        sp.setMinimumWidth(104)
        # ⚠ **也要有上限。** 右欄現在拉得寬（第十一輪的 splitter），而沒有上限
        # 的話這兩格會各自撐到一半，中間那個 `×` 落在兩格之間的空地上 ——
        # 一對東西看起來就不再是一對。實拍在 538 px 寬的時候就是那樣。
        sp.setMaximumWidth(132)
        sp.setSpecialValueText("measured")
        # ⚠ **打字的中途不算。** 預設 Qt 每敲一個鍵就發 `valueChanged`，於是
        # 要打 45 的人會先看到整個視窗用 4 重算一次（使用者 2026-09-21：
        # 「我要輸入 45，但當我輸入到 4，就會強制 trigger 算 4」）—— 一次
        # 疊格子是幾百毫秒，中途那一次是純粹的浪費，而且畫面會閃一個錯的答案。
        # 關掉之後只有 **Enter／離開焦點／按上下鍵** 才算。
        sp.setKeyboardTracking(False)
        sp.setToolTip(
            "Type the cell size %s if the measured one is not the unit you "
            "want — the grid and the stacked cell redraw so you can see "
            "whether yours is right." % axis)
        sp.valueChanged.connect(lambda _v: self._on_override())
        return sp

    # -- 進來的圖 -----------------------------------------------------------
    def open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open an image of the repeating layout", "",
            "Images (*.tif *.tiff *.png *.jpg *.jpeg *.bmp);;All files (*)")
        if path:
            self._load_path(str(path))

    def _load_path(self, path: str) -> None:
        from pitchapp.core.ingest import imageio as ingest_imageio
        try:
            arr = ingest_imageio.load_gray(path)
        except Exception as e:
            self._say("Could not open that image: %s" % e)
            return
        self.set_image(arr, os.path.basename(path), ask_crop=True)

    def paste_image(self) -> None:
        cb = QGuiApplication.clipboard()
        arr = _qimage_to_gray(cb.image() if cb is not None else None)
        if arr is None:
            self._say("There is no image on the clipboard.")
            return
        self.set_image(arr, "pasted image", ask_crop=True)

    def set_image(self, arr: Any, name: str = "", ask_crop: bool = False) -> None:
        """換一張圖：清掉上一次的答案，量一次新的。

        ⚠ **舊答案要先清掉**再開始量。留著的話，新圖載進來的那幾秒畫面上寫的
        是上一張圖的 pitch，而那是這個視窗唯一的輸出。
        """
        a = np.asarray(arr)
        if a.ndim < 2 or a.size == 0:
            self._say("That is not an image.")
            return
        self._full = to_uint8(a)
        self._crop = None
        self._name = str(name or "")
        self._m = self._gc = None
        self._apply_crop()
        if ask_crop and not self.ask_crop():
            self.remeasure()

    def ask_crop(self) -> bool:
        """問「只看這一塊」。回 True 表示它已經自己重量過了。

        用的是 `crop_dialog.CropDialog` **本人** —— 「框怎麼變成像素」只能有
        一個家（見 `crop_array` 的說明）。
        """
        if self._full is None:
            return False
        dlg = CropDialog(self._full, self._name, self._crop, self,
                         ok_text="Measure from this box")
        if not dlg.exec():
            return False
        self._crop = dlg.box()
        self._apply_crop()
        self.remeasure()
        return True

    def _apply_crop(self) -> None:
        if self._full is None:
            return
        self._work = crop_array(self._full, self._crop)
        self._m = self._gc = None
        # ⚠ **底下的像素換了，剛剛量的那一段就不算了。** 留著的話那條綠帶會
        # 落在一張它從來沒有被拉過的圖上，而畫面不會說那是舊的。
        self._clear_ruler()
        h, w = self._work.shape[:2]
        bits = ["%s%d × %d px" % ((self._name + " · ") if self._name else "", w, h)]
        crop = describe_crop(self._crop)
        if crop:
            bits.append(crop)
        self.lab_source.setText(" · ".join(bits))
        self.view.set_image(self._work)

    # -- 量 -----------------------------------------------------------------
    def remeasure(self, reuse: bool = False) -> None:
        """量一次。``reuse=True`` 只重疊（軸向或週期改了，影像沒變）。"""
        if self._work is None or self._worker is not None:
            return
        self._worker = _PitchWorker(self._work, self.axis(),
                                    self._m if reuse else None,
                                    self.override(), self.stack_method(),
                                    self.skip_edges(), self)
        self._worker.stage.connect(self._say)
        self._worker.answer.connect(self._on_answer)
        self._worker.done.connect(self._on_done)
        self._worker.finished.connect(self._on_finished)
        self.progress.setVisible(True)
        self._busy(True)
        self._worker.start()

    def _on_answer(self, m: Any) -> None:
        """週期量完了 —— **先把數字放上去**，證據等疊完再補。

        ⚠ 這一刻**還不能畫格線**：格子的位置要等相位搜尋（`choose_origin`）
        回來才知道。畫在相位 0 上再跳掉是最糟的一種 —— 使用者盯著的正是那張
        圖，而它會先給一個錯的位置。所以 `_draw` 遇到「有週期、還沒有相位」
        就只說一句「正在找位置」。
        """
        if m is None:
            return
        self._m, self._gc = m, None
        self._refresh()

    def _on_done(self, m: Any, gc: Any, err: str) -> None:
        if err:
            self._say(err)
            return
        if m is None:
            return
        self._m, self._gc = m, gc
        self._refresh()
        self.measured.emit(m, gc)

    def _on_finished(self) -> None:
        self._worker = None
        self.progress.setVisible(False)
        self._busy(False)

    def _clear_ruler(self) -> None:
        """量尺歸零（模式留著 —— 使用者按的那一顆鈕不會自己彈回去）。"""
        self._measured = None
        self.view.clear_measure()
        self.btn_use_ruler.setVisible(False)

    #: 沒有影像就沒有意義的那些控制項（見 `_sync_enabled`）。
    #: ⚠ `spin_nm`（pixel size）**不在裡面**：先填好機台的 nm/px 再開圖是合理的
    #: 用法，而它填的值撐得過換圖。
    def _needs_image(self):
        return (self.btn_crop, self.chips_axis, self.spin_px, self.spin_py,
                self.btn_double, self.btn_reset, self.chk_median,
                self.chk_edges, self.chk_grid, self.btn_ruler,
                self.btn_details)

    def _sync_enabled(self) -> None:
        """**沒有圖的時候，按不出結果的東西要看起來按不出結果。**

        空狀態下這些控制項全部是「按得動」的，而按下去：`Crop` 回 False
        **狀態列一個字都沒有**（按了像壞掉）；`Ruler` 真的打開量尺模式、還說
        「Drag across the image」—— 而沒有 image；週期欄收下 60、答案仍然是
        `—`；`×2` 靜靜地沒反應。

        這是鐵則 7「不 raise 不等於不記」的 UI 版：**一顆按了什麼都不會發生、
        也不說為什麼的按鈕**。變灰是那句「為什麼」最便宜的講法。
        """
        has = self._work is not None and bool(np.asarray(self._work).size)
        for w in self._needs_image():
            w.setEnabled(has)
        if not has:                      # 關掉的模式不要留著
            self.btn_ruler.setChecked(False)

    def _busy(self, on: bool) -> None:
        for w in (self.btn_open, self.btn_paste, self.btn_use_ruler) \
                + self._needs_image():
            w.setEnabled(not on)
        for b in self._try_buttons:
            b.setEnabled(not on)
        if not on:
            # ⚠ 跑完不是「全部打開」，是「回到該有的樣子」—— 不然沒有圖的那條
            # 路會被這裡一口氣全部啟用。
            self._sync_enabled()

    def _on_axis(self, _value: str) -> None:
        """軸向改了 —— **週期不重量**，但格線與疊圖都要重來。

        ⚠ **格線要當場重畫，不能等 worker 回來。** 第一版沒有這一行，症狀是
        按下「X only」之後表格立刻寫 `not used`，而圖上的**橫線還在**，一等
        好幾秒 —— 畫面同時在說兩件相反的事，而使用者會相信圖。
        """
        if self._m is None:
            return
        self._refresh()
        self.remeasure(reuse=True)

    def _on_override(self) -> None:
        """使用者自己打了一個週期 —— 同 `_on_axis`：**當場重畫，不等疊圖**。"""
        if self._m is None:
            self._fill_answer()
            return
        self._refresh()
        self.remeasure(reuse=True)

    def _on_double(self) -> None:
        """兩格一起 ×2（沒打過就從量到的那個翻倍）。"""
        if self._m is None:
            return
        ex, ey = effective_period(self._m, self.override())
        self._set_override(min(8192.0, ex * 2.0), min(8192.0, ey * 2.0))

    def _on_reset(self) -> None:
        self._set_override(0.0, 0.0)

    def _set_override(self, px: float, py: float) -> None:
        """兩格一起換，**只重畫一次**（各自 `setValue` 會跑兩趟 worker）。"""
        for sp in (self.spin_px, self.spin_py):
            sp.blockSignals(True)
        self.spin_px.setValue(float(px))
        self.spin_py.setValue(float(py))
        for sp in (self.spin_px, self.spin_py):
            sp.blockSignals(False)
        self._on_override()

    # -- 畫面 ---------------------------------------------------------------
    def axis(self) -> str:
        return self.chips_axis.text() or AXIS_BOTH

    def nm_per_px(self) -> float:
        return float(self.spin_nm.value())

    def skip_edges(self) -> bool:
        return bool(self.chk_edges.isChecked())

    def stack_method(self) -> str:
        """``"median"`` ＝ 忽略缺陷（`golden.stack_cells` 的那個參數）。"""
        return "median" if self.chk_median.isChecked() else "mean"

    def override(self) -> Override:
        """使用者自己打的那一組（``None`` ＝ 那一軸用量到的）。"""
        px, py = float(self.spin_px.value()), float(self.spin_py.value())
        return (px if px >= MIN_PERIOD_PX else None,
                py if py >= MIN_PERIOD_PX else None)

    def _flags(self) -> Tuple[bool, bool]:
        """哪幾軸算數 —— **答案、格線、疊圖三個地方問的是同一支**。

        各自算一次的話，畫面上會出現「答案說 Y 沒在用、格線卻切了橫線」——
        這個視窗已經被那種形狀咬過兩次（`_on_axis` 與 `_draw` 的回歸測試）。
        """
        if self._m is None:
            return (False, False)
        ov = self.override()
        ex, ey = effective_period(self._m, ov)
        return axis_flags(self.axis(), ex, ey,
                          100.0 if ov[0] else self._m.conf_x,
                          100.0 if ov[1] else self._m.conf_y)

    def typed_conf(self) -> Override:
        """使用者打進去的那一組週期，**在這張圖上**拿幾分。

        ⚠ 量的是 `self._work`（裁過、正在看的那一張），不是原圖 —— 畫面上
        那些格線切的就是它，分數跟它們講的必須是同一件事。
        每一軸沒打就是 ``None``（沒有分數要算），不是 0。

        便宜得可以每次 refresh 都算：一條投影 ＋ 一次自相關，不是一次疊格子。
        """
        ox, oy = self.override()
        work = self._work
        if work is None or not np.asarray(work).size:
            return (None, None)
        return (algo_period.confidence_at(work, float(ox), "x") if ox else None,
                algo_period.confidence_at(work, float(oy), "y") if oy else None)

    def rows(self) -> List[Tuple[str, str, str, str]]:
        """畫面上那兩列（測試讀這個，不必去挖 QLabel）。"""
        if self._m is None:
            return [(lab, PITCH_UNSET, "", PITCH_UNSET)
                    for lab in ("Across (X)", "Down (Y)")]
        return pitch_rows(self._m, self.axis(), self.nm_per_px(),
                          self.override(), self.typed_conf())

    def _refresh(self) -> None:
        """一次把畫面對齊到目前的狀態 —— **只有這一支**（少呼叫一半就是說謊）。"""
        self._sync_enabled()
        self._fill_answer()
        self._draw()
        self._fill_stack()
        self._fill_try()
        self._fill_details()
        self._fill_warning()

    def _fill_answer(self) -> None:
        """答案那兩列。**沒在用的那一軸整列不顯示**（使用者 2026-09-21 定的）。

        ⚠ 這一條**推翻了第一版的決定**，而理由是使用者的：第一版寫 `not used`，
        想法是「藏起來他會以為量不到」。但**選 X only 的人是自己按的那顆鈕**
        —— 他知道 Y 還在，那一列對他只是噪音。原本的顧慮只在 Auto 自己丟掉
        一軸時才成立，而那一種 Auto 本來就不會把它列出來（`flags` 是 False），
        所以改由**警告條**去講（「這一軸信心不足」），不是留一列半殘的資料。
        """
        rows = self.rows()
        ov = self.override()
        flags = self._flags()
        tc = self.typed_conf()
        confs = (float(getattr(self._m, "conf_x", 0.0) or 0.0) if self._m else 0.0,
                 float(getattr(self._m, "conf_y", 0.0) or 0.0) if self._m else 0.0)
        used = [i for i in range(2) if (flags[i] if self._m is not None else True)]
        self.lab_big.setText(
            " × ".join(rows[i][1] for i in used) + " px" if used and
            rows[used[0]][1] != PITCH_UNSET else PITCH_UNSET)
        ums = [rows[i][2] for i in used if rows[i][2]]
        self.lab_um.setText(" × ".join(ums).replace(" µm ×", " ×") if ums else "")
        # 沒填 pixel size 就沒有這一行 —— 一個空著的標籤照樣佔一行高，而那一行
        # 在大數字底下看起來像「這裡本來該有東西」。
        self.lab_um.setVisible(bool(ums))
        # **按鈕自己講它會複製什麼** —— 「copy 是 copy 誰？」的另一半答案。
        what = self.answer_text()
        self.lab_next.setVisible(bool(what))
        # **沒在用的那一軸連複製鍵都不出現**（同那一列數字的規矩），
        # 而沒有答案的時候剩下的那顆是灰的：一顆按下去只會說「還沒量到東西」
        # 的按鈕，在畫面上是一個問題，不是一個功能。
        for i, b in enumerate(self._copy_buttons):
            num = self.axis_number(i)
            b.setVisible(flags[i] if self._m is not None else True)
            b.setEnabled(bool(num))
            b.setToolTip(("Puts %s on the clipboard — just the number, "
                          "ready for Cell %s.  (%s)"
                          % (num, "W" if i == 0 else "H",
                             self.key_for("copy_focused_or_answer" if i == 0
                                          else "copy_y")))
                         if num else "Nothing measured yet.")
        for i, (bar, tag) in enumerate(zip(self._bars, self._tags)):
            show = flags[i] if self._m is not None else True
            for w in (tag, bar):
                w.setVisible(show)
            if not show:
                continue
            if self._m is None:
                # ⚠ **還沒量過就不畫軌道**（同 `bar_agree` 那一條）。
                # 這裡本來是 `set_value(0.0, …)`，於是還沒載圖的時候這兩條各畫
                # 一顆琥珀色的點（=「被評分過，拿了 0 分」），而正下方的
                # `Cells agree` 什麼都沒畫（=「還沒有東西可評」）——
                # **同一張卡、三條、兩種意思**。
                # 第十二輪修的是那一條，而我寫的測試也只斷言了那一條：
                # 三條裡守了一條，另外兩條就大搖大擺地漏過去。
                bar.set_text_only("")
            elif ov[i] and tc[i] is None:
                # 打進去了，但這張圖打不出分數（還沒載圖／lag 大過半張圖）。
                bar.set_text_only(CONF_TYPED)
            else:
                # 打進去的那一軸看的是**它自己的**分數（`confidence_at`），
                # 不是量出來那個數字的分數 —— 兩個同尺度，可以直接比。
                c = float(tc[i]) if ov[i] else confs[i]
                bar.set_value(c / 100.0, conf_tone(c), "%.0f" % c)

    def _fill_try(self) -> None:
        """候選那一排 —— **點一下就套用**（見 `candidate_periods` 的說明）。"""
        for b in self._try_buttons:
            self.row_try.removeWidget(b)
            # ⚠ `removeWidget` **不會讓它從畫面上消失** —— 它只是不再由
            # layout 擺位，於是它留在父視窗上最後一次被擺的地方，而
            # `deleteLater` 要等事件迴圈才真的刪。實拍到的樣子是一顆舊的
            # 「60 × 22」候選鈕**疊在最大的那個答案上**。`setParent(None)`
            # 才是「現在就不要再畫它」。
            b.setParent(None)
            b.deleteLater()
        self._try_buttons = []
        flags = self._flags()
        cands = (candidate_periods(self._m, flags,
                                   effective_period(self._m, self.override()))
                 if self._m is not None else [])
        self.lab_try.setVisible(bool(cands))
        for px, py in cands:
            b = QPushButton(candidate_label(px, py, flags), self.lab_try.parentWidget())
            # ⚠ **候選是備案，不是動作。** 這裡本來是 `secondary`（藍框），
            # 而右欄那時有 8 顆可見按鈕**全部同一個 variant** —— 藍色在這個
            # app 是 accent（「這是動作」），全部 accent 等於沒有 accent。
            # 而這四顆是畫面上最不重要的東西（「萬一取錯了」），卻是最吵的
            # 一叢。`ghost` 讓它們退回背景，點得到但不搶戲。
            # ⚠ `ghost` 是次要文字色 —— 實拍出來那四顆跟旁邊的 "Or try" 一樣
            # 灰，看起來像**死掉的文字**，而它們是點得下去的。保留 accent 的
            # **字色**（那一句才是「可以點」），只拿掉框。
            b.setProperty("variant", "ghost")
            b.setProperty("clickableText", "true")
            # 一排四顆要塞進 380 px：留白收掉，字才不會被切成 "L20 × 44"。
            b.setStyleSheet("padding-left:6px;padding-right:6px;")
            b.setToolTip(
                "Try this instead — it is one of the harmonics of what was "
                "measured, and a wrong period is almost always one of these. "
                "The grid and the stacked cell redraw so you can compare.")
            b.clicked.connect(lambda _c=False, a=px, bb=py: self._set_override(a, bb))
            self.row_try.insertWidget(self.row_try.count() - 1, b)
            self._try_buttons.append(b)

    def _fill_details(self) -> None:
        """三票各自的答案（折在 ``▸ Details`` 後面）。"""
        if self._m is None:
            self.details.setText("")
            return
        rows = detail_rows(self._m, self._flags())
        cells = "".join(
            "<tr><td style='padding-right:12px'>%s</td>"
            "<td style='padding-right:12px'>%s</td><td>%s</td></tr>"
            % r for r in rows)
        self.details.setText(
            "<table><tr><td></td><td><b>X</b></td><td><b>Y</b></td></tr>%s</table>"
            "<br>Each row is one of the three ways it looks for a repeat; the "
            "number in brackets is that method's own confidence. They are "
            "allowed to disagree — that is a fact about the layout, not a "
            "fault." % cells)

    def _on_details(self, on: bool) -> None:
        self.btn_details.setText(("▾  Details" if on else "▸  Details"))
        self.details.setVisible(bool(on))

    def show_cell_big(self) -> None:
        """疊出來那一格點一下 → 放大看。

        150 px 對細 pattern 不夠判斷糊不糊，而**看得出糊不糊是它存在的唯一
        理由**。走 `lattice_dialog` 用的那個 `ImageView`（滾輪縮放、拖曳平移）。
        """
        cell = getattr(self._gc, "cell", None) if self._gc is not None else None
        if cell is None or np.asarray(cell).size == 0:
            return
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Stacked cell")
        fit_screen.fit(dlg, 620, 620)
        lay = QVBoxLayout(dlg)
        view = ImageView(dlg)
        view.set_image(np.asarray(cell))
        lay.addWidget(view, 1)
        hint = QLabel("Crisp edges mean the cells landed on each other. "
                      "Blurred or doubled means the period is off. "
                      "Wheel zooms, drag pans.", dlg)
        hint.setObjectName("paramHint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Close, Qt.Horizontal, dlg)
        bb.rejected.connect(dlg.reject)
        bb.clicked.connect(lambda _b: dlg.reject())
        lay.addWidget(bb)
        apply_button_cursors(dlg)
        dlg.exec()

    def answer_text(self) -> str:
        """Copy 出去的那一段字（測試讀這個）。"""
        rows = self.rows()
        flags = self._flags()
        bits = []
        for i, name in enumerate(("X", "Y")):
            if not flags[i]:
                continue
            piece = "%s %s px" % (name, rows[i][1])
            if rows[i][2]:
                piece += " (%s)" % rows[i][2]
            bits.append(piece)
        return "  ".join(bits)

    def axis_number(self, i: int) -> str:
        """那一軸**光禿禿的數字**（沒有單位、沒有軸名）—— Copy 放上剪貼簿的。

        ⚠ 走的是 `rows()`，也就是畫面上那個數字**本人** —— 不是再算一次。
        使用者打進去的週期、×2、候選一鍵套用，複製到的都會是他看到的那一個。
        """
        rows = self.rows()
        flags = self._flags()
        if not (0 <= int(i) < 2) or not flags[int(i)]:
            return ""
        val = rows[int(i)][1]
        return "" if val == PITCH_UNSET else str(val)

    def copy_axis(self, i: int) -> None:
        """把那一軸的數字放上剪貼簿。"""
        text = self.axis_number(int(i))
        if not text:
            self._say("Nothing measured yet.")
            return
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(text)
        self._say("Copied %s" % text)

    def copy_answer(self) -> None:
        """X 那一軸（舊的進入點 —— 測試與鍵盤走這裡）。"""
        self.copy_axis(0)

    def _fill_stack(self) -> None:
        """疊出來那一格 ＋ 一致性 —— 這是「憑什麼相信它」那一塊。"""
        gc = self._gc
        cell = getattr(gc, "cell", None) if gc is not None else None
        if cell is None or np.asarray(cell).size == 0:
            self.cell_view.setPixmap(QPixmap())
            self.cell_view.setFixedSize(CELL_BOX, CELL_BOX)
            self.cell_view.setText(PITCH_UNSET)
            # ⚠ **還沒疊過的時候不畫那條軌道**（`set_text_only`）。
            # 這一行本來是 `set_value(0.0, …)`，而自從 0 分改成畫一顆點之後，
            # 「沒有東西可疊」就跟「疊了，而它们完全對不起來」畫成同一個樣子 ——
            # 而那正是那個改動要消掉的歧義。
            self.bar_agree.set_text_only("")
            self.lab_stack.setText("")
            return
        # ⚠ **格子照 cell 的長寬比，不硬塞正方形。** 60×44 放進一個正方形，
        # 上下各留一條白邊 —— 而那條白邊會被讀成「cell 比實際高」，也就是說謊。
        #
        # ⚠ **而那個比例要收在一個 `CELL_BOX` 見方的框裡，不是只縮寬度。**
        # 純 X 的 layout（直條）一格是 48 × 480 —— 只算高度的話那一格會長到
        # 1650 px，把整張卡撐爛，而圖根本畫不出來。這是 `_pixmap` 裡
        # `KeepAspectRatio` 已經在做的同一件事，這裡只是讓**框**跟上它。
        arr = np.asarray(cell)
        h, w = arr.shape[:2]
        scale = float(CELL_BOX) / float(max(h, w) or 1)
        self.cell_view.setFixedSize(max(24, int(round(w * scale))),
                                    max(24, int(round(h * scale))))
        self.cell_view.setPixmap(_pixmap(arr, CELL_BOX))
        agree = float(getattr(gc, "agreement", 0.0) or 0.0)
        self.bar_agree.set_value(agree, agree_tone(agree), "%.2f" % agree)
        n = int(getattr(gc, "n_cells", 0) or 0)
        tone = agree_tone(agree)
        # ⚠ **一句話，不是三句。** 第一版是「144 cells. Edge cells left out.
        # The cells landed on each other — this period is right.」—— 而那個
        # 結論旁邊就是一條綠色的長條寫著 0.98，字只是在重複顏色已經講完的事。
        # 使用者 2026-09-21：「UI 內字太多」。長的那一段留在 tooltip 裡。
        if tone == TONE_GOOD:
            word = "landed on each other."
        elif tone == TONE_WARN:
            word = "look blurred? try ×2."
        else:
            word = "did not agree — this period is wrong."
        edge = ", edges left out" if getattr(gc, "trimmed", False) else ""
        self.lab_stack.setText("%d cells%s — %s" % (n, edge, word))

    def _fill_warning(self) -> None:
        """⚠ **只在有事的時候出現。** 第一版有一塊常駐的「What it decided」，
        而最常見的情形是它空著 —— 使用者 2026-09-21：「這我不知道可以幹嘛？」
        一塊永遠在那裡、內容通常是空的面板，教會使用者不要看它。"""
        lines: List[str] = []
        if self._m is not None:
            nothing = self._flags() == (False, False)
            if nothing:
                # ⚠ **一句話講一次。** 引擎的 note 裡已經有一句
                # "no periodic structure detected"，而它是寫給開發者看的
                # （F118：使用者面的字不准講開發者的話）。兩句並排出現的時候
                # 使用者會去找「它們是不是在講兩件事」—— 而那是找不到答案的。
                lines.append("No repeating period could be measured in this "
                             "image. Try Crop to leave out anything that is "
                             "not the repeating layout.")
            else:
                lines.extend(getattr(self._m, "notes", None) or [])
            note = ""
            if self._gc is not None and not nothing and self._work is not None:
                ex, ey = effective_period(self._m, self.override())
                note = trust_note(cells_along(self._work.shape[:2], ex, ey,
                                              self._flags()))
            if note:
                lines.append(note)
            # ⚠ **低信心的那一軸現在用講的，不是默默丟掉。**
            # 那是 `Auto` 留下來的唯一一件有用的事（見 :data:`AXES`）——
            # 使用者 2026-09-21 把 `Auto` 拿掉之後，這一句就是它的去處。
            # 打進去的那一軸不算（使用者明講的數字不需要引擎背書）。
            flags_now = self._flags()
            weak = [name for i, (name, conf) in enumerate(
                (("X", float(getattr(self._m, "conf_x", 0.0) or 0.0)),
                 ("Y", float(getattr(self._m, "conf_y", 0.0) or 0.0))))
                if flags_now[i] and not self.override()[i]
                and conf < algo_template.MIN_PERIOD_CONFIDENCE]
            if weak:
                lines.append(
                    "%s barely repeats (confidence under %d) — the number is "
                    "there, but check the stacked cell before you trust it."
                    % (" and ".join(weak),
                       int(algo_template.MIN_PERIOD_CONFIDENCE)))
            ox, oy = self.override()
            if ox or oy:
                got = ", ".join(
                    "%s: yours %s vs measured %s"
                    % (name, algo_period2d.fmt_px(typed),
                       algo_period2d.fmt_px(m) if m >= MIN_PERIOD_PX else "none")
                    for name, typed, m in (
                        ("X", ox, float(self._m.px or 0)),
                        ("Y", oy, float(self._m.py or 0))) if typed)
                lines.append("Not the measured size — %s. “Reset” puts it back."
                             % got)
        text = "  ·  ".join(str(s) for s in lines if str(s).strip())
        self.warn.setText(("⚠  " + text) if text else "")
        self.warn.setVisible(bool(text))
        # ⚠ **狀態行讀的就是這一份，不另外算第二份。** 這個 repo 為「同一件事
        # 有兩個算法」付過太多次錢了；而且這一份剛好就是對的判準 —— 見
        # `VERDICT_CHECK` 的說明（半週期疊起來照樣很齊）。
        self._has_warning = bool(text)
        self._fill_state()

    def verdict(self) -> Tuple[str, str]:
        """(色調, 那句話) —— **這一行說的是「所以這次到底成不成立」**。

        ⚠ `good` 的條件是「**一個警告都沒有**」，不是「分數夠高」：一個錯的
        週期（真正週期的一半）每一格都是半個 cell，彼此照樣對得很齊，
        `Cells agree` 會很高。那一刻給綠勾等於替一個可能錯的答案背書。
        """
        if self._work is None:
            return "", ""
        if self._m is None:
            return TONE_WARN if self._worker is None else "busy", (
                "" if self._worker is None else VERDICT_BUSY_PERIOD)
        if self._flags() == (False, False):
            return TONE_BAD, VERDICT_NONE
        if self._gc is None:
            return "busy", VERDICT_BUSY_STACK
        # ⚠ **疊不起來的時候先說疊不起來，就算那個數字是使用者自己打的。**
        # 「Using your period」是真的，但它是一句中性的話 —— 實拍過：使用者
        # 打了 37，`Cells agree` 紅成 0.44，而最上面那一行還是灰色的「在用你
        # 的週期」。那一行的工作是**一眼的結論**，它不能在證據已經紅了的時候
        # 說一句不表態的話。
        agree = float(getattr(self._gc, "agreement", 0.0) or 0.0)
        tone = agree_tone(agree)
        if tone != TONE_GOOD:
            return tone, VERDICT_BLURRED
        if any(self.override()):
            return "busy", VERDICT_TYPED
        return (TONE_WARN, VERDICT_CHECK) if self._has_warning \
            else (TONE_GOOD, VERDICT_OK)

    #: 狀態行的符號。**文字 ＋ 色調是兩個通道**（F117 U13）—— 顏色是第二個，
    #: 不是唯一的，所以這個符號也不能是唯一的差別。
    STATE_MARKS = {TONE_GOOD: "✓", TONE_WARN: "⚠", TONE_BAD: "⚠", "busy": "◐"}

    def _fill_state(self) -> None:
        tone, text = self.verdict()
        self.lab_state.setText(text)
        self.lab_state_mark.setText(self.STATE_MARKS.get(tone, "") if text
                                    else "")
        hexs = {TONE_GOOD: TOKENS["success_text"],
                TONE_WARN: TOKENS["warning"],
                TONE_BAD: TOKENS["danger_text"]}.get(tone,
                                                     TOKENS["text_secondary"])
        for w in (self.lab_state, self.lab_state_mark):
            w.setStyleSheet("color:%s;" % hexs)
            w.setVisible(bool(text))

    def _say_caption(self, text: str) -> None:
        """圖底下那一行字 —— **只有這一支寫它**。

        ⚠ 量尺的讀數跟格線的說明搶同一行，而它們由不同的事件觸發（拖曳 vs
        重算完）。少了這道收口，worker 回來的那一刻會把使用者剛量到的數字
        蓋掉 —— 這個視窗這一輪已經為了「同一件事有兩個算法」付過四次錢了。
        **量尺在量的時候它說了算**，其餘時間交給格線。
        """
        if self._measured is not None:
            axis, span = self._measured
            um = nm_text(span, True, self.nm_per_px())
            self.caption.setText(
                "Ruler: %s px%s along %s"
                % (algo_period2d.fmt_px(span), ("  ·  " + um) if um else "",
                   "X" if axis == "x" else "Y"))
            return
        self.caption.setText(str(text))

    def _draw(self) -> None:
        """格線鋪回原圖 —— **`lattice_boxes` 本人**，不自己再算一次格子。"""
        if self._work is None or self._m is None or not self.chk_grid.isChecked():
            self.view.set_overlay(None)
            self._say_caption("")
            return
        if self._gc is None:
            # 有週期、還沒有相位（答案已經在上面了，疊圖還在跑）。
            self.view.set_overlay(None)
            self._say_caption(PHASE_PENDING)
            return
        flags = self._flags()
        if not flags[0] and not flags[1]:
            self.view.set_overlay(None)
            self._say_caption("No period to draw.")
            return
        shape = self._work.shape[:2]
        # ⚠ 畫的是**真的在用的那一組**，不是量到的那一組 —— 少了這一行，
        # 使用者打了 120、答案寫 120，而格線還是照 60 畫。
        ex, ey = effective_period(self._m, self.override())
        ux, uy = lattice_periods(shape, ex, ey, flags)
        origin = tuple(getattr(self._gc, "origin", None) or (0.0, 0.0))
        boxes, total = lattice_boxes(shape, ux, uy, origin, flags)
        # ⚠ **畫的格子要跟疊進去的那些是同一批。** 少了這一段，邊界那一圈明明
        # 沒有被疊進去，畫面上卻還框著它 —— 而使用者盯著的正是那張圖。
        # 這是這一輪第三次踩到同一種形狀（`_on_axis`、`_draw` 的週期、這裡），
        # 病根都是「同一件事在畫面上有兩個算法」。
        if getattr(self._gc, "trimmed", False):
            box = trim_to_inner(shape, ux, uy, origin, flags)
            if box is not None:
                h, w = shape
                x0, y0, x1, y1 = (box[0] / w, box[1] / h, box[2] / w, box[3] / h)
                boxes = [b for b in boxes
                         if b[0] >= x0 - 1e-6 and b[1] >= y0 - 1e-6
                         and b[0] + b[2] <= x1 + 1e-6 and b[1] + b[3] <= y1 + 1e-6]
                total = len(boxes)
        self.view.set_overlay(boxes)
        text = "%s px · %d cells" % (algo_template.period_text(ux, uy), total)
        if len(boxes) < total:
            text += " (%d drawn)" % len(boxes)
        self._say_caption(text)

    def _say(self, text: str) -> None:
        self.statusBar().showMessage(str(text), 8000)

    # -- 手勢 ---------------------------------------------------------------
    def dragEnterEvent(self, e) -> None:  # Qt hook
        if e.mimeData() is not None and e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # Qt hook
        urls = list(e.mimeData().urls()) if e.mimeData() is not None else []
        path = urls[0].toLocalFile() if urls else ""
        if not path:
            return
        e.acceptProposedAction()
        self._load_path(str(path))

    def closeEvent(self, e) -> None:  # Qt hook
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(3000)
        super().closeEvent(e)


def _pixmap(arr: np.ndarray, box: int) -> QPixmap:
    """uint8 2D → 放大到 ``box`` 見方的 QPixmap（保持長寬比）。

    ⚠ **放大用 nearest-neighbour**：一格常常只有 40–80 px，而使用者要判斷的
    正是「邊緣是清楚的還是糊的」。平滑取樣會把答案本身抹掉。
    """
    a = np.ascontiguousarray(to_uint8(arr))
    h, w = a.shape[:2]
    img = QImage(a.data, w, h, w, QImage.Format_Grayscale8).copy()
    return QPixmap.fromImage(img).scaled(box, box, Qt.KeepAspectRatio,
                                         Qt.FastTransformation)


def _qimage_to_gray(img: Optional[QImage]) -> Optional[np.ndarray]:
    """剪貼簿的 QImage → uint8 灰階 2D。空的或壞的回 ``None``。

    ⚠ **一定要先轉成 ``Format_Grayscale8``**：截圖多半是 ARGB32，它的 `bits()`
    是 BGRA 四個 byte 一組，直接 reshape 會拿到「寬度四倍、內容是交錯通道」的
    東西 —— 而那**看起來仍然像一張圖**（條紋狀），只是每一個數字都不對。
    """
    if img is None or img.isNull():
        return None
    g = img.convertToFormat(QImage.Format_Grayscale8)
    h, w = g.height(), g.width()
    if h < 4 or w < 4:
        return None
    buf = np.frombuffer(bytes(g.constBits()), dtype=np.uint8)
    stride = g.bytesPerLine()
    return buf[:h * stride].reshape(h, stride)[:, :w].copy()


def run(argv: Optional[Sequence[str]] = None) -> int:
    """``python main.py`` 的進入點。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(list(argv or []))
    theme.apply_theme(app)
    # 這條路是**獨立**的入口（`python -m d4t pitch`），所以整個 app 的圖示
    # 就是 helper 的，不是 Studio 的。
    app.setWindowIcon(branding.pitch_icon())
    win = PitchHelperWindow()
    win.show()
    return int(app.exec())

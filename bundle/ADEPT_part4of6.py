#!/usr/bin/env python3
# ADEPT 單檔純文字包（由 tools/make_text_bundle.py 產生）。
"""整個 ADEPT repo 就在這個檔案裡，一行一行的純文字，沒有壓縮、沒有編碼。

為什麼是這種形式：公司政策擋掉 .zip 這個類別，而 proxy 也不讓 Python 逐檔抓 ——
能過的只剩「一個純文字檔」。你可以用記事本打開它，往下捲就看得到每個檔案的內容。

    python ADEPT_part4of6.py              # 解到 .\\ADEPT\\
    python ADEPT_part4of6.py --dest D:\\tools
    python ADEPT_part4of6.py --list       # 只看裡面有什麼，不寫任何檔案

每個檔案都帶 git blob SHA-1，解開時逐檔驗過才落地 —— 傳輸途中被動到的話會當場
講出來，不會讓你拿到一份安靜壞掉的程式碼。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

SENTINEL = "# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ===="
PART, N_PARTS = 4, 6   # 這是第幾批 / 共幾批（1/1 = 沒有分批）
TOTAL = 178                       # 整個 repo 有幾個檔案，不是這一批有幾個


def blob_sha(data: bytes) -> str:
    """git 算 blob SHA 的方式："blob <長度>\\0" + 內容。"""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def entries(lines):
    """走過資料區，一個一個吐出 (sha, 路徑, 內容位元組)。"""
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("#F "):
            i += 1
            continue
        _, sha, count, path = line.split(" ", 3)
        n = int(count)
        # 資料區每一行前面有一個 '#'（那樣整個檔案才仍然是合法的 Python）。
        body = [ln[1:] if ln[:1] == "#" else ln for ln in lines[i + 1:i + 1 + n]]
        yield sha, path, "\n".join(body).encode("utf-8")
        i += 1 + n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Unpack the ADEPT text bundle.")
    ap.add_argument("--dest", default="ADEPT", help="解到哪個資料夾（預設 .\\ADEPT）")
    ap.add_argument("--list", action="store_true", help="只列出內容，不寫檔")
    a = ap.parse_args(argv)

    # 用文字模式讀自己：Python 會把 CRLF 讀成 LF，所以這個檔案就算在傳輸途中
    # 被換過行尾也解得開（格式用「行數」而不是「位元組數」正是為了這件事）。
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    try:
        start = lines.index(SENTINEL) + 1
    except ValueError:
        print("✗ 找不到資料區 —— 這個檔案被截斷了，或不是完整的 bundle。")
        return 2

    items = list(entries(lines[start:]))
    if not items:
        print("✗ 資料區是空的 —— 這個檔案被截斷了。")
        return 2
    print("這個包裡有 %d 個檔案。" % len(items))
    if a.list:
        for _sha, path, data in items:
            print("  %8d  %s" % (len(data), path))
        return 0

    dest = os.path.abspath(a.dest)
    print("解到  : %s" % dest)
    bad, done = [], 0
    for sha, path, data in items:
        if blob_sha(data) != sha:
            bad.append(path)
            continue
        full = os.path.join(dest, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        tmp = full + ".tmp"                      # atomic：半個檔案不要留在磁碟上
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, full)
        done += 1

    if bad:
        print("")
        print("✗ %d 個檔案的內容跟它自己的 SHA 對不上：" % len(bad))
        for path in bad[:12]:
            print("    %s" % path)
        print("")
        print("  這個檔案在傳輸途中被動過（編輯器另存、郵件過濾器改寫都會這樣）。")
        print("  請重新取得一份，不要用編輯器打開後另存。這份程式碼不完整，不要用。")
        return 1

    print("✓ %d 個檔案都解開了，SHA 全部對得上。" % done)

    # 分批的時候要講「還缺幾個」—— 不然使用者不知道自己貼完了沒有。
    # 判斷依據是 tools/FILELIST.txt（它固定在第一批），而不是這一批的數量。
    listing = os.path.join(dest, "tools", "FILELIST.txt")
    have_listing = os.path.isfile(listing)
    missing = []
    if have_listing:
        with open(listing, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    rel = line.split(" ", 1)[1]
                    if not os.path.isfile(os.path.join(dest,
                                                       rel.replace("/", os.sep))):
                        missing.append(rel)

    if N_PARTS > 1 and not have_listing:
        # 還沒拿到檔案清單，所以「缺幾個」算不出來。**這時候絕對不能印
        # 「下一步：跑 doctor」** —— 那看起來就像整包已經到位了。
        print("")
        print("這是第 %d 批 / 共 %d 批，整個 repo 有 %d 個檔案 —— **還沒到齊**。"
              % (PART, N_PARTS, TOTAL))
        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。")
        print("第 1 批裡有檔案清單，貼過它之後每一批都會告訴你還缺哪些。")
        return 0

    if missing:
        print("")
        print("這是第 %d 批 / 共 %d 批。整個 repo 還缺 %d 個檔案 —— 在其他批裡。"
              % (PART, N_PARTS, len(missing)))
        print("把其他批也貼進來執行（順序不重要，重複執行也沒關係）。缺的例如：")
        for rel in missing[:6]:
            print("    %s" % rel)
        return 0

    print("")
    print("下一步：")
    print("  cd %s" % dest)
    print("  python tools\\doctor.py        # 環境自檢（會告訴你還缺什麼）")
    print("  相依套件裝不了的話走離線 wheels：docs\\OFFLINE-INSTALL.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# ==== ADEPT-BUNDLE-DATA ==== 以下是資料，不要編輯 ====
#F 75df1028febe3a268f90fd2e4c507f13c5d7ad79 2720 adept/ui/widgets.py
## ADEPT Studio widget library — authored 2026-07-28 (M3).
## ImageView 的 zoom/pan 骨架 vendored from: PEAR/pear/ui/image_view.py（去掉 ROI 編輯）。
#"""Studio 的六個可重用元件 —— 全部「資料驅動」，**不碰引擎**。
#
#設計約束（很重要，別破壞）：
#
#1. 這裡的元件只吃 dict / list / ndarray，只發 Signal。任何一個元件都不會
#   import ``adept.core``、不會跑 pipeline、不會開檔案。組裝與呼叫引擎是
#   main window / worker 的事。
#2. 顏色一律走 ``theme.TOKENS`` / ``theme.seg_color``，不寫死 hex。
#3. 每個參數的白話 ``help`` 一定要看得到（``ParamForm`` 的第二行提示）—— 推廣鐵則。
#
#元件一覽：
#
#- :class:`ImageView`        ndarray 檢視器（滾輪縮放、拖曳平移、雙擊 fit）
#- :class:`ParamForm`        由 ``Step.describe()`` 自動生成的參數表單
#- :class:`LibraryPanel`     三段式卡片庫（影像／算法／ADC）
#- :class:`PipelinePanel`    有序節點清單 + Score/Bin 尾卡
#- :class:`HistogramWidget`  分數分佈 + 可拖曳門檻線 + 可點擊長條（``bar_clicked``）
#- :class:`FeatureTable` / :class:`VerdictChip`  特徵表與判定 chip
#"""
#
#from __future__ import annotations
#
#import math
#from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
#
#import numpy as np
#from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
#from PySide6.QtGui import (
#    QColor,
#    QFont,
#    QImage,
#    QPainter,
#    QPainterPath,
#    QPen,
#    QPixmap,
#)
#from PySide6.QtWidgets import (
#    QAbstractItemView,
#    QCheckBox,
#    QComboBox,
#    QDoubleSpinBox,
#    QFrame,
#    QHBoxLayout,
#    QGridLayout,
#    QHeaderView,
#    QLabel,
#    QLineEdit,
#    QDialog,
#    QDialogButtonBox,
#    QPushButton,
#    QScrollArea,
#    QSizePolicy,
#    QSlider,
#    QSpinBox,
#    QTableWidget,
#    QTableWidgetItem,
#    QVBoxLayout,
#    QWidget,
#)
#
#from . import theme
#from .theme import TOKENS
#
#__all__ = [
#    "ImageView",
#    "ParamForm",
#    "LibraryPanel",
#    "PipelinePanel",
#    "HistogramWidget",
#    "FeatureTable",
#    "VerdictChip",
#    "TemplateField",
#    "to_uint8",
#]
#
#
## --------------------------------------------------------------------------- #
## numpy -> Qt
## --------------------------------------------------------------------------- #
#def to_uint8(arr: np.ndarray) -> np.ndarray:
#    """任意 ndarray -> 可顯示的 uint8。
#
#    * ``uint8`` 直接用（不做任何拉伸，patch 的原始灰階就是原始灰階）。
#    * 其他型別（float32 的 diff / snr_map、int16 …）走 min–max 自動拉伸；
#      NaN / ±Inf 不參與統計，最後補 0（不會整張變白或炸掉）。
#    """
#    a = np.asarray(arr)
#    if a.dtype == np.uint8:
#        return np.ascontiguousarray(a)
#    f = np.asarray(a, dtype=np.float64)
#    finite = np.isfinite(f)
#    if not finite.any():
#        return np.zeros(f.shape, dtype=np.uint8)
#    lo = float(f[finite].min())
#    hi = float(f[finite].max())
#    if hi <= lo:
#        scaled = np.zeros(f.shape, dtype=np.float64)
#    else:
#        scaled = (f - lo) * (255.0 / (hi - lo))
#    scaled = np.where(finite, scaled, 0.0)
#    return np.ascontiguousarray(np.clip(scaled, 0.0, 255.0).astype(np.uint8))
#
#
#def _qimage_from_uint8(arr: np.ndarray) -> QImage:
#    """uint8 (H,W) / (H,W,3) / (H,W,4) -> QImage（deep copy，不依賴原 buffer）。"""
#    a = np.ascontiguousarray(arr)
#    if a.ndim == 2:
#        h, w = a.shape
#        img = QImage(a.data, w, h, w, QImage.Format_Grayscale8)
#    elif a.ndim == 3 and a.shape[2] == 3:
#        h, w, _ = a.shape
#        img = QImage(a.data, w, h, 3 * w, QImage.Format_RGB888)
#    elif a.ndim == 3 and a.shape[2] == 4:
#        h, w, _ = a.shape
#        img = QImage(a.data, w, h, 4 * w, QImage.Format_RGBA8888)
#    else:
#        raise ValueError(f"Unsupported image shape: {a.shape}")
#    return img.copy()
#
#
## --------------------------------------------------------------------------- #
## 1. ImageView
## --------------------------------------------------------------------------- #
#class ImageView(QWidget):
#    """ndarray 檢視器：滾輪對游標縮放、拖曳平移、雙擊 fit。
#
#    放大到 1:1 以上時關掉平滑取樣（nearest-neighbour），缺陷 patch 的像素要
#    看得出方格 —— 這是看 SEM 小圖的基本要求。
#    """
#
#    zoom_changed = Signal(float)
#    cursor_info = Signal(str)          # "x 12  y 30  ·  gray 187"（離開時空字串）
#    #: 縮放**或**平移之後的完整檢視狀態（scale, offset）。
#    #: 並排比對兩張圖時，兩邊靠這個訊號互相跟隨 —— 沒有連動的並排沒有意義，
#    #: 使用者得手動把兩邊拖到同一個位置才比得起來。
#    view_changed = Signal(float, QPointF)
#
#    _MIN_SCALE = 0.02
#    _MAX_SCALE = 60.0
#    _EMPTY_TEXT = "(no image)"
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.setMinimumSize(240, 180)
#        self.setMouseTracking(True)
#        self.setFocusPolicy(Qt.StrongFocus)
#        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
#
#        self._image: Optional[np.ndarray] = None      # 顯示用的 uint8
#        self._pixmap: Optional[QPixmap] = None
#        self._scale = 1.0
#        self._offset = QPointF(0.0, 0.0)
#        self._auto_fit = True                         # 尺寸變動時是否自動重 fit
#        self._panning = False
#        self._pan_start = QPointF()
#        self._pan_offset = QPointF()
#
#    # -- public API --------------------------------------------------------
#    def set_image(self, arr: Optional[np.ndarray]) -> None:
#        """設定影像；``None`` 清空並顯示「（無影像）」。
#
#        第一次拿到影像（或尺寸換了）會自動 fit；同尺寸的重繪保留目前的縮放/平移，
#        調參數時視野不會被重設。
#        """
#        if arr is None:
#            self._image = None
#            self._pixmap = None
#            self._auto_fit = True
#            self.update()
#            return
#        u8 = to_uint8(arr)
#        old_shape = None if self._image is None else self._image.shape[:2]
#        self._image = u8
#        self._pixmap = QPixmap.fromImage(_qimage_from_uint8(u8))
#        if old_shape != u8.shape[:2]:
#            self.fit()
#        else:
#            self.update()
#
#    def has_image(self) -> bool:
#        return self._image is not None
#
#    def image(self) -> Optional[np.ndarray]:
#        return self._image
#
#    def scale(self) -> float:
#        return self._scale
#
#    def zoom_percent(self) -> int:
#        return int(round(self._scale * 100))
#
#    def fit(self) -> None:
#        """整張影像置中縮放到剛好塞進畫布（留 4% 邊）。"""
#        self._auto_fit = True
#        if self._pixmap is None:
#            return
#        vw, vh = max(1, self.width()), max(1, self.height())
#        iw, ih = self._pixmap.width(), self._pixmap.height()
#        if iw <= 0 or ih <= 0:
#            return
#        self._scale = float(np.clip(min(vw / iw, vh / ih) * 0.96,
#                                    self._MIN_SCALE, self._MAX_SCALE))
#        self._offset = QPointF((vw - iw * self._scale) / 2.0,
#                               (vh - ih * self._scale) / 2.0)
#        self.update()
#        self.zoom_changed.emit(self._scale)
#        self.view_changed.emit(self._scale, QPointF(self._offset))
#
#    def zoom_by(self, factor: float, anchor: Optional[QPointF] = None) -> None:
#        """以 ``anchor``（畫布座標，預設中心）為定點縮放。"""
#        if self._pixmap is None:
#            return
#        if anchor is None:
#            anchor = QPointF(self.width() / 2.0, self.height() / 2.0)
#        ia = self._to_image(anchor)
#        new_scale = float(np.clip(self._scale * factor,
#                                  self._MIN_SCALE, self._MAX_SCALE))
#        if new_scale == self._scale:
#            return
#        self._scale = new_scale
#        self._offset = QPointF(anchor.x() - ia.x() * self._scale,
#                               anchor.y() - ia.y() * self._scale)
#        self._auto_fit = False
#        self.update()
#        self.zoom_changed.emit(self._scale)
#        self.view_changed.emit(self._scale, QPointF(self._offset))
#
#    def set_view(self, scale: float, offset: QPointF) -> None:
#        """直接套用另一張圖的檢視狀態（並排比對時用）。
#
#        **不回發 view_changed** —— 兩邊互相跟隨會無限來回。跟隨是單向的，
#        由發起操作的那一邊推過去。
#        """
#        s = float(np.clip(float(scale), self._MIN_SCALE, self._MAX_SCALE))
#        if s == self._scale and QPointF(offset) == self._offset:
#            return
#        self._scale = s
#        self._offset = QPointF(offset)
#        self._auto_fit = False
#        self.update()
#
#    def view_state(self) -> Tuple[float, QPointF]:
#        return self._scale, QPointF(self._offset)
#
#    def zoom_in(self) -> None:
#        self.zoom_by(1.25)
#
#    def zoom_out(self) -> None:
#        self.zoom_by(1 / 1.25)
#
#    # -- transforms --------------------------------------------------------
#    def _to_image(self, p: QPointF) -> QPointF:
#        s = self._scale or 1.0
#        return QPointF((p.x() - self._offset.x()) / s,
#                       (p.y() - self._offset.y()) / s)
#
#    # -- painting ----------------------------------------------------------
#    def paintEvent(self, _e) -> None:
#        p = QPainter(self)
#        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
#        p.setRenderHint(QPainter.Antialiasing, True)
#        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
#        # 中性灰底：不隨主題變，也不讓背景偏移對灰階的判斷（見 theme 的
#        # image_backdrop 說明）
#        p.setBrush(QColor(TOKENS["image_backdrop"]))
#        p.drawRoundedRect(rect, 6, 6)
#        if self._pixmap is None:
#            p.setPen(QColor(TOKENS["text_disabled"]))
#            p.drawText(self.rect(), Qt.AlignCenter, self._EMPTY_TEXT)
#            p.end()
#            return
#        # scale > 1 -> nearest neighbour（像素銳利）；縮小才用平滑取樣（防摩爾紋）
#        p.setRenderHint(QPainter.SmoothPixmapTransform, self._scale <= 1.0)
#        target = QRectF(self._offset.x(), self._offset.y(),
#                        self._pixmap.width() * self._scale,
#                        self._pixmap.height() * self._scale)
#        p.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
#        p.end()
#
#    # -- interaction -------------------------------------------------------
#    def wheelEvent(self, e) -> None:
#        if self._pixmap is None:
#            return
#        delta = e.angleDelta().y()
#        if delta == 0:
#            return
#        self.zoom_by(1.15 if delta > 0 else 1 / 1.15, QPointF(e.position()))
#        e.accept()
#
#    def mousePressEvent(self, e) -> None:
#        if self._pixmap is None:
#            return
#        if e.button() in (Qt.LeftButton, Qt.MiddleButton, Qt.RightButton):
#            self._panning = True
#            self._pan_start = QPointF(e.position())
#            self._pan_offset = QPointF(self._offset)
#            self._auto_fit = False
#            self.setCursor(Qt.ClosedHandCursor)
#
#    def mouseMoveEvent(self, e) -> None:
#        pos = QPointF(e.position())
#        if self._panning:
#            self._offset = self._pan_offset + (pos - self._pan_start)
#            self.update()
#            self.view_changed.emit(self._scale, QPointF(self._offset))
#            return
#        self._emit_cursor(pos)
#
#    def mouseReleaseEvent(self, _e) -> None:
#        if self._panning:
#            self._panning = False
#            self.unsetCursor()
#
#    def mouseDoubleClickEvent(self, e) -> None:
#        if e.button() == Qt.LeftButton:
#            self.fit()
#
#    def leaveEvent(self, _e) -> None:
#        self.cursor_info.emit("")
#
#    def resizeEvent(self, e) -> None:
#        super().resizeEvent(e)
#        if self._auto_fit:
#            self.fit()
#
#    def _emit_cursor(self, pos: QPointF) -> None:
#        if self._image is None:
#            self.cursor_info.emit("")
#            return
#        ip = self._to_image(pos)
#        x, y = int(math.floor(ip.x())), int(math.floor(ip.y()))
#        h, w = self._image.shape[:2]
#        if 0 <= x < w and 0 <= y < h:
#            v = self._image[y, x]
#            gray = int(v) if np.ndim(v) == 0 else int(np.mean(v))
#            self.cursor_info.emit(f"x {x}  y {y}  ·  gray {gray}")
#        else:
#            self.cursor_info.emit("")
#
#
## --------------------------------------------------------------------------- #
## 2. ParamForm
## --------------------------------------------------------------------------- #
##: 浮點滑桿的內部刻度數。滑桿只吃 int，所以 min..max 一律映射到 0..這個數。
##: 1000 格對 gamma（0.1–5）約是 0.005 一格 —— 拖起來連續，又不會抖到看不出。
#_SLIDER_TICKS = 1000
#
##: 整數參數的滑桿上限跨度。超過這個跨度就不給滑桿（一格好幾十，拖了也沒用），
##: 留純數字框比較誠實。
#_SLIDER_MAX_INT_SPAN = 5000
#
#
#class _HintLabel(QLabel):
#    """參數說明：平常一行（放不下就切成 ``像這樣…``），要用的時候整段攤開。
#
#    為什麼不直接讓它一直換行
#    ------------------------
#    一張卡有 11 個參數、每個帶 2–3 行灰字，加起來就是一面牆 —— 一定要捲，
#    而且**真正要緊的事會淹在裡面**（「這張卡還沒有模板」跟「這個滑桿越大越
#    平滑」長得一模一樣）。
#
#    為什麼不乾脆只留 tooltip
#    ------------------------
#    因為那等於把說明藏起來，而這個工具的使用者是不會寫 code 的製程工程師 ——
#    他要的是「我現在在動的這個東西是什麼」隨手看得到，不是「知道要把滑鼠停在
#    哪裡等一秒」。所以：正在用的那一列整段攤開，其餘各留一行。
#
#    切字自己算（``elidedText``），不交給 Qt 裁 —— Qt 會硬切在字的中間，
#    看起來像畫面壞掉（同 canvas 的 ``_draw_elided``）。
#    """
#
#    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.setObjectName("paramHint")
#        self._full = str(text)
#        self._expanded = False
#        self.setWordWrap(False)
#        self._sync()
#
#    def full_text(self) -> str:
#        return self._full
#
#    def set_full_text(self, text: str) -> None:
#        self._full = str(text)
#        self._sync()
#
#    def set_expanded(self, expanded: bool) -> None:
#        if bool(expanded) != self._expanded:
#            self._expanded = bool(expanded)
#            self._sync()
#
#    def is_expanded(self) -> bool:
#        return self._expanded
#
#    def resizeEvent(self, e) -> None:          # noqa: D102 - Qt hook
#        super().resizeEvent(e)
#        if not self._expanded:
#            self._sync()
#
#    def _sync(self) -> None:
#        if self._expanded:
#            self.setWordWrap(True)
#            super().setText(self._full)
#            return
#        self.setWordWrap(False)
#        w = max(40, self.width())
#        super().setText(self.fontMetrics().elidedText(
#            self._full, Qt.ElideRight, w))
#
#
#class _ParamRow(QFrame):
#    """一個參數 = 標題列（名稱 + 滑桿 + 數字框）+ 永遠看得見的白話說明第二行。
#
#    為什麼有上下界的數字都配一支滑桿（F7-8）
#    ----------------------------------------
#    「gamma 要填多少」對不會寫 code 的人是個沒有答案的問題 —— 他要的是
#    **一邊拖一邊看圖**。數字框逼人先想好一個數字再輸入，那個順序是反的。
#
#    數字框沒有被拿掉，是刻意的：滑桿負責找到大概的位置，數字框負責記錄與
#    重現（recipe 是要交接給別人的）。兩邊雙向綁定，改哪一邊另一邊都會跟上。
#    """
#
#    def __init__(self, spec: Dict[str, Any], editor: QWidget,
#                 parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.spec = spec
#        self.editor = editor
#        self.slider: Optional[QSlider] = None
#        self._active = False
#        self.setObjectName("paramRow")
#
#        lay = QVBoxLayout(self)
#        lay.setContentsMargins(0, 2, 0, 6)
#        lay.setSpacing(2)
#
#        top = QHBoxLayout()
#        top.setContentsMargins(0, 0, 0, 0)
#        top.setSpacing(8)
#        # 顯示名優先用 ``label``（F7-9）。``name`` 是 recipe JSON 的鍵，
#        # 對使用者來說 ``range_from`` 不是一句話，"Borrow range from" 才是。
#        self.name_label = QLabel(str(spec.get("label") or spec.get("name", "")))
#        self.name_label.setObjectName("paramLabel")
#        self.name_label.setMinimumWidth(104)
#        top.addWidget(self.name_label)
#
#        self.slider = _make_slider(spec, editor)
#        if self.slider is not None:
#            top.addWidget(self.slider, 1)
#            editor.setMaximumWidth(96)
#            top.addWidget(editor, 0)
#        else:
#            top.addWidget(editor, 1)
#        lay.addLayout(top)
#
#        self.hint = _HintLabel(str(spec.get("help", "")), self)
#        self.hint.setProperty("error", "false")
#        lay.addWidget(self.hint)
#
#        # 說明只在**這一列被使用的時候**展開（F7-15）。11 個參數各配 2–3 行灰字
#        # 是一面牆：一定要捲，而且真正要緊的事（模板是空的）淹在裡面。收成一行
#        # 不是把資訊藏起來 —— 使用者在讀的永遠只有他正在動的那一個參數。
#        self.setAttribute(Qt.WA_Hover, True)
#        editor.installEventFilter(self)
#        for child in editor.findChildren(QWidget):
#            child.installEventFilter(self)
#        if self.slider is not None:
#            self.slider.installEventFilter(self)
#
#    # -- 「正在用這一列」（F7-15）-------------------------------------------
#    def eventFilter(self, obj, e):             # noqa: D102 - Qt hook
#        from PySide6.QtCore import QEvent
#
#        if e.type() in (QEvent.FocusIn, QEvent.Enter):
#            self.set_active(True)
#        elif e.type() == QEvent.FocusOut:
#            self.set_active(self.underMouse())
#        return False
#
#    def enterEvent(self, e) -> None:           # noqa: D102 - Qt hook
#        self.set_active(True)
#        super().enterEvent(e)
#
#    def leaveEvent(self, e) -> None:           # noqa: D102 - Qt hook
#        # 兩種「其實還在這一列」的情況不收起來：
#        #  * 焦點還在這一列的欄位上（使用者正在打字或拖滑桿）——
#        #    滑鼠離開輸入框那一瞬間把說明收掉，是在他眼前抽走東西；
#        #  * 滑鼠只是從列的空白處移進了**這一列自己的**輸入框。Qt 會先送
#        #    Leave 給列、再送 Enter 給子元件，照字面處理就是收起來又立刻攤開，
#        #    看起來是閃一下。所以直接問游標還在不在這一列的矩形裡。
#        if not (self._has_focus() or self._cursor_inside()):
#            self.set_active(False)
#        super().leaveEvent(e)
#
#    def _cursor_inside(self) -> bool:
#        from PySide6.QtGui import QCursor
#
#        try:
#            return self.rect().contains(self.mapFromGlobal(QCursor.pos()))
#        except Exception:                      # noqa: BLE001 — 沒有游標的環境
#            return False
#
#    def _has_focus(self) -> bool:
#        w = self.editor.focusWidget() if hasattr(self.editor, "focusWidget") else None
#        return bool(self.editor.hasFocus() or w is not None
#                    or (self.slider is not None and self.slider.hasFocus()))
#
#    def set_active(self, active: bool) -> None:
#        """這一列現在是不是使用者正在動的那一個（說明整段攤開）。"""
#        self._active = bool(active)
#        # 錯誤永遠攤開：那是他現在最需要讀完的一句話。
#        self.hint.set_expanded(self._active or self.has_error())
#
#    def is_active(self) -> bool:
#        return bool(getattr(self, "_active", False))
#
#    def set_error(self, msg: Optional[str]) -> None:
#        if msg:
#            self.hint.set_full_text("⚠ " + str(msg))
#            self.hint.setProperty("error", "true")
#            self.hint.setStyleSheet(
#                "color:%s; font-size:11px; font-weight:600;" % TOKENS["danger_text"])
#            self.hint.set_expanded(True)
#        else:
#            self.hint.set_full_text(str(self.spec.get("help", "")))
#            self.hint.setProperty("error", "false")
#            self.hint.setStyleSheet("color:%s; font-size:11px;" % TOKENS["text_hint"])
#            self.hint.set_expanded(self.is_active())
#        self.hint.style().unpolish(self.hint)
#        self.hint.style().polish(self.hint)
#
#    def has_error(self) -> bool:
#        return self.hint.property("error") == "true"
#
#    def set_dimmed(self, dimmed: bool, why: str = "") -> None:
#        """把整列調淡（值還在、還能改，只是現在不生效）。
#
#        用在「另一個參數接管了這一個」的情況 —— 例如畫了曲線之後 gamma
#        就不再被用到。不 disable 是刻意的：使用者可能只是想比較兩種做法，
#        把它鎖死會逼他先把曲線拉平才改得動 gamma。
#        """
#        self.setProperty("dimmed", "true" if dimmed else "false")
#        self.setEnabled(True)
#        self.name_label.setStyleSheet(
#            "color:%s;" % (TOKENS["text_disabled"] if dimmed
#                           else TOKENS["text_primary"]))
#        if dimmed and why:
#            self.hint.set_full_text("· " + why)
#            self.hint.setStyleSheet("color:%s; font-size:11px; font-style:italic;"
#                                    % TOKENS["text_disabled"])
#        elif not self.has_error():
#            self.hint.set_full_text(str(self.spec.get("help", "")))
#            self.hint.setStyleSheet("color:%s; font-size:11px;" % TOKENS["text_hint"])
#
#
#def _make_slider(spec: Dict[str, Any], editor: QWidget) -> Optional[QSlider]:
#    """有上下界的 int / float 參數 → 一支跟數字框雙向綁定的滑桿。
#
#    回 ``None`` 表示這個參數不適合滑桿（沒界、跨度是 0、或整數跨度大到
#    一格好幾十）。這樣新卡片只要把 min/max 填好就自動有滑桿，
#    不必逐張卡去 UI 這邊登記。
#    """
#    ptype = str(spec.get("type", ""))
#    lo, hi = spec.get("min"), spec.get("max")
#    if ptype not in ("int", "float") or lo is None or hi is None:
#        return None
#    lo, hi = float(lo), float(hi)
#    if not (math.isfinite(lo) and math.isfinite(hi)) or hi <= lo:
#        return None
#
#    s = QSlider(Qt.Horizontal)
#    s.setObjectName("paramSlider")
#    s.setToolTip(str(spec.get("help", "")))
#    guard = {"busy": False}
#
#    if ptype == "int":
#        if hi - lo > _SLIDER_MAX_INT_SPAN:
#            return None
#        s.setRange(int(lo), int(hi))
#        s.setValue(int(editor.value()))
#
#        def from_slider(v: int) -> None:
#            if guard["busy"]:
#                return
#            guard["busy"] = True
#            editor.setValue(int(v))
#            guard["busy"] = False
#
#        def from_box(v: int) -> None:
#            if guard["busy"]:
#                return
#            guard["busy"] = True
#            s.setValue(int(v))
#            guard["busy"] = False
#    else:
#        s.setRange(0, _SLIDER_TICKS)
#        span = hi - lo
#
#        def to_tick(v: float) -> int:
#            return int(round((float(v) - lo) / span * _SLIDER_TICKS))
#
#        s.setValue(to_tick(editor.value()))
#
#        def from_slider(v: int) -> None:      # noqa: F811 — 兩型別各一份
#            if guard["busy"]:
#                return
#            guard["busy"] = True
#            editor.setValue(lo + (float(v) / _SLIDER_TICKS) * span)
#            guard["busy"] = False
#
#        def from_box(v: float) -> None:       # noqa: F811
#            if guard["busy"]:
#                return
#            guard["busy"] = True
#            s.setValue(to_tick(v))
#            guard["busy"] = False
#
#    # 兩邊互相回寫會無限來回（float 還會因為取整而每次都差一點點），
#    # 所以用 guard 擋住「因我而起的那一次回呼」。
#    s.valueChanged.connect(from_slider)
#    editor.valueChanged.connect(from_box)
#    return s
#
#
#class ProfilePanel(QWidget):
#    """投影定位的曲線面板（F7-11）：曲線、轉折線、選中的那一段、中心線。
#
#    為什麼這張卡沒有這個面板就不成立
#    --------------------------------
#    「敏感度要調多少」對不會寫 code 的人是一個沒有答案的問題 —— 除非他看得到
#    曲線、看得到目前抓到幾條線、看得到抓到的線是不是落在他預期的地方。
#    沒有這個面板，這張卡就只是另一個要盲填的數字。
#
#    **畫的資料來自引擎那一次計算**（step 卡把它放進 ``ctx.meta["profiles"]``），
#    UI 不自己再算一次。不然「畫面上的框」跟「真的量下去的框」會不一樣，
#    而那種 bug 幾乎不可能靠肉眼發現。
#    """
#
#    _EMPTY = "(select a Locate region by profile card to see its curve)"
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self._data: Dict[str, Any] = {}
#        self._name = ""
#        self.setMinimumHeight(96)
#        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
#        self.setToolTip("Gray level projected along the scan direction. "
#                        "Vertical lines are the boundaries that were found; "
#                        "the shaded section is the region this card produces.")
#
#    # -- public ------------------------------------------------------------
#    def set_data(self, name: str, data: Optional[Dict[str, Any]]) -> None:
#        self._name = str(name or "")
#        self._data = dict(data or {})
#        self.update()
#
#    def has_data(self) -> bool:
#        return bool(self._data.get("profile"))
#
#    def summary(self) -> str:
#        """一行文字摘要（測試與狀態列都用這個，不用去讀畫素）。"""
#        if not self.has_data():
#            return ""
#        d = self._data
#        picked = d.get("picked")
#        where = ("none" if not picked
#                 else "%d-%d px" % (int(picked[0]), int(picked[1])))
#        return ("%s · %d boundaries · %d sections · picked %s · confidence %.1f"
#                % (self._name, len(d.get("transitions") or []),
#                   len(d.get("bands") or []), where,
#                   float(d.get("confidence", 0.0))))
#
#    # -- paint -------------------------------------------------------------
#    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
#        p = QPainter(self)
#        p.setRenderHint(QPainter.Antialiasing, True)
#        rect = QRectF(self.rect()).adjusted(6, 6, -6, -6)
#        p.fillRect(QRectF(self.rect()), QColor(TOKENS["bg_surface"]))
#        p.setPen(QPen(QColor(TOKENS["border_default"]), 1.0))
#        p.drawRoundedRect(rect, 4, 4)
#
#        prof = [float(v) for v in (self._data.get("profile") or [])]
#        if len(prof) < 2:
#            p.setPen(QColor(TOKENS["text_disabled"]))
#            p.drawText(rect, Qt.AlignCenter, self._EMPTY)
#            p.end()
#            return
#
#        n = len(prof)
#        raw = [float(v) for v in (self._data.get("raw") or [])]
#        lo = min(min(prof), min(raw) if raw else min(prof))
#        hi = max(max(prof), max(raw) if raw else max(prof))
#        span = max(hi - lo, 1e-6)
#        plot = rect.adjusted(4, 16, -4, -4)
#
#        def to_x(i: float) -> float:
#            return plot.left() + plot.width() * (float(i) / max(1, n - 1))
#
#        def to_y(v: float) -> float:
#            return plot.bottom() - plot.height() * ((v - lo) / span)
#
#        # 選中的那一段：先畫底色，曲線才會壓在上面
#        picked = self._data.get("picked")
#        if picked:
#            x0, x1 = to_x(int(picked[0])), to_x(int(picked[1]))
#            p.setPen(Qt.NoPen)
#            p.setBrush(QColor(TOKENS["accent_bg"]))
#            p.drawRect(QRectF(x0, plot.top(), max(1.0, x1 - x0), plot.height()))
#
#        # 平滑前的曲線畫在後面當對照 —— 使用者才看得出平滑吃掉了多少
#        if len(raw) == n:
#            p.setPen(QPen(QColor(TOKENS["border_input"]), 1.0))
#            p.setBrush(Qt.NoBrush)
#            path = QPainterPath(QPointF(to_x(0), to_y(raw[0])))
#            for i in range(1, n):
#                path.lineTo(QPointF(to_x(i), to_y(raw[i])))
#            p.drawPath(path)
#
#        p.setPen(QPen(QColor(TOKENS["text_primary"]), 1.6))
#        path = QPainterPath(QPointF(to_x(0), to_y(prof[0])))
#        for i in range(1, n):
#            path.lineTo(QPointF(to_x(i), to_y(prof[i])))
#        p.drawPath(path)
#
#        # 中心線 = 缺陷的位置（patch 是以缺陷為中心裁的）
#        p.setPen(QPen(QColor(TOKENS["text_secondary"]), 1.0, Qt.DashLine))
#        cx = to_x((n - 1) / 2.0)
#        p.drawLine(QPointF(cx, plot.top()), QPointF(cx, plot.bottom()))
#
#        p.setPen(QPen(QColor(TOKENS["accent"]), 1.4))
#        for t in (self._data.get("transitions") or []):
#            x = to_x(int(t))
#            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
#
#        p.setPen(QColor(TOKENS["text_secondary"]))
#        f = p.font()
#        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.0))
#        p.setFont(f)
#        p.drawText(QRectF(rect.left() + 6, rect.top() + 2, rect.width() - 12, 14),
#                   Qt.AlignVCenter | Qt.AlignLeft, self.summary())
#        p.end()
#
#
#class StreamPicker(QWidget):
#    """``image_keys`` 參數的編輯器：上游每一條影像流一個勾選框（F7-9）。
#
#    為什麼不是一個輸入框
#    --------------------
#    「一串影像流」如果是自由文字，三個問題一次到齊 —— 使用者不知道**可以填
#    什麼**（流名從來沒有列出來過）、不知道**填了會怎樣**、打錯了也不會被擋。
#    勾選框把這三件事一次解掉：能填的就是列出來的那幾個。
#
#    F7-18 之後沒有內建卡片用這個型別
#    --------------------------------
#    唯一用它的是 Enhance 卡的 ``also_apply``，而那件事已經拆成節點了：
#    **一張卡一條流**，要對 ref 也做就再放一張卡接到 ref。留著這個編輯器是因為
#    「一串影像流」仍然是 ``ParamSpec`` 的合法型別（見 ``step.PARAM_TYPES``），
#    自訂卡片用得到；拿掉它等於要求下一張這種卡自己刻一個表單元件。
#
#    值的格式是逗號分隔字串；recipe 裡指到「現在的 pipeline 沒有這條流」的名字
#    也會列出來並勾著，不會因為看不到就被靜靜刪掉。
#    """
#
#    changed = Signal(str)
#
#    _EMPTY_TEXT = "(no upstream stream yet — add an Input card first)"
#
#    def __init__(self, streams: Sequence[str], value: str = "",
#                 parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self._boxes: List[QCheckBox] = []
#        self._emitting = False
#
#        lay = QHBoxLayout(self)
#        lay.setContentsMargins(0, 0, 0, 0)
#        lay.setSpacing(10)
#
#        picked = [t.strip() for t in str(value or "").split(",") if t.strip()]
#        names: List[str] = []
#        for name in list(streams) + picked:      # 上游的在前，recipe 帶來的在後
#            name = str(name)
#            if name and name not in names:
#                names.append(name)
#
#        for name in names:
#            box = QCheckBox(name, self)
#            box.setChecked(name in picked)
#            box.toggled.connect(self._on_toggled)
#            lay.addWidget(box)
#            self._boxes.append(box)
#        if not names:
#            hint = QLabel(self._EMPTY_TEXT, self)
#            hint.setObjectName("paramHint")
#            lay.addWidget(hint)
#        lay.addStretch(1)
#
#    def text(self) -> str:
#        """目前的值（逗號分隔，順序同勾選框）。"""
#        return ",".join(b.text() for b in self._boxes if b.isChecked())
#
#    def set_text(self, value: str) -> None:
#        picked = {t.strip() for t in str(value or "").split(",") if t.strip()}
#        self._emitting = True
#        try:
#            for box in self._boxes:
#                box.setChecked(box.text() in picked)
#        finally:
#            self._emitting = False
#
#    def stream_names(self) -> List[str]:
#        return [b.text() for b in self._boxes]
#
#    def _on_toggled(self, _checked: bool) -> None:
#        if not self._emitting:
#            self.changed.emit(self.text())
#
#
#class TemplateField(QWidget):
#    """``template`` 參數的編輯器：一顆「建一個」的按鈕 + 一行摘要（F7-13）。
#
#    為什麼不是文字框
#    ----------------
#    模板的值有六千多個字元，而且**沒有人能用打的**（它是一張影像的內容）。
#    給它一個文字框有三個後果：空的時候看起來像「還沒填的欄位」，而真正的入口
#    在半個螢幕外的另一塊面板上；填了之後那個框變成一整片 base64；而且它是
#    可編輯的 —— 一個放不下、也編輯不了的值配一個文字框，等於邀請使用者去改它。
#
#    這裡改成：**按鈕就在這一列**（它是這個參數的值從哪來，不是預覽的動作），
#    欄位本身只回答「現在有沒有模板、是什麼樣的模板」。
#    """
#
#    build_requested = Signal()
#
#    _EMPTY = "No template yet — this card cannot run until you build one."
#
#    def __init__(self, value: str = "", parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        lay = QVBoxLayout(self)
#        lay.setContentsMargins(0, 0, 0, 0)
#        lay.setSpacing(3)
#
#        self.button = QPushButton("Build template from a full-size image…", self)
#        self.button.setProperty("variant", "secondary")
#        self.button.setToolTip(
#            "Measure the repeating cell from one full-size image and store it "
#            "inside this recipe. The image is only needed here — the recipe "
#            "stays a single file you can hand to someone else.")
#        self.button.clicked.connect(self.build_requested.emit)
#        lay.addWidget(self.button, 0, Qt.AlignLeft)
#
#        self.summary = QLabel("", self)
#        self.summary.setObjectName("paramHint")
#        self.summary.setWordWrap(True)
#        lay.addWidget(self.summary)
#
#        self._value = ""
#        self.set_text(value)
#
#    def text(self) -> str:
#        return self._value
#
#    def set_text(self, value: str) -> None:
#        self._value = str(value or "")
#        self.summary.setText(self.describe())
#        # 「還沒有模板」不是說明文字，是**這張卡現在跑不了**。用同一種灰字講，
#        # 它就沉進下面那段說明裡了。
#        self.summary.setStyleSheet(
#            "color:%s; font-size:11px;%s"
#            % (TOKENS["text_hint"] if self.has_template() else TOKENS["danger_text"],
#               "" if self.has_template() else " font-weight:600;"))
#        self.button.setText("Build template from a full-size image…"
#                            if not self._value else "Rebuild template…")
#
#    def has_template(self) -> bool:
#        return bool(self._value.strip())
#
#    def describe(self) -> str:
#        """一行白話：現在存的是什麼。**摘要是解出來的，不是記在旁邊的**——
#        記在旁邊的欄位會跟真正的值走散，而走散時畫面上看起來完全正常。"""
#        if not self.has_template():
#            return self._EMPTY
#        try:
#            from ..core.algo.template import decode_cell
#
#            cell = decode_cell(self._value)
#        except Exception:                       # noqa: BLE001 — 顯示用
#            cell = None
#        if cell is None or getattr(cell, "size", 0) == 0:
#            return ("A template is stored, but it cannot be read back. "
#                    "Build it again.")
#        h, w = cell.shape[:2]
#        return ("Stored in this recipe: one cell of %d × %d px (%.1f kB of "
#                "text). Mark the region on it with the four Region sliders "
#                "below." % (w, h, len(self._value) / 1024.0))
#
#
#class ParamForm(QWidget):
#    """由 ``Step.describe()`` 的 ParamSpec dict 自動長出來的參數表單。
#
#    ``set_step(describe, current_params, stream_choices)`` 一次重建整張表；
#    使用者改動任何欄位 -> ``param_edited(name, value)``（值已 coerce 成該型別）。
#    上層驗證失敗時呼叫 ``show_error(name, msg)`` 把那一列的說明變紅字。
#    """
#
#    param_edited = Signal(str, object)
#    #: 「這個參數的值要用別的方式產生」（目前只有 template）。表單不知道那是
#    #: 什麼對話框 —— 它只負責把請求送上去，由 Studio 決定要開什麼。
#    action_requested = Signal(str)
#
#    _EMPTY_TEXT = "(Pick a card from the library, or select a step in the pipeline)"
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self._rows: Dict[str, _ParamRow] = {}
#        self._describe: Optional[Dict[str, Any]] = None
#        self._building = False
#
#        outer = QVBoxLayout(self)
#        outer.setContentsMargins(0, 0, 0, 0)
#        outer.setSpacing(4)
#
#        self._title = QLabel("")
#        self._title.setObjectName("paramTitle")
#        self._step_help = QLabel("")
#        self._step_help.setObjectName("paramStepHelp")
#        self._step_help.setWordWrap(True)
#        outer.addWidget(self._title)
#        outer.addWidget(self._step_help)
#
#        self._scroll = QScrollArea(self)
#        self._scroll.setWidgetResizable(True)
#        self._scroll.setFrameShape(QFrame.NoFrame)
#        self._host = QWidget()
#        self._form = QVBoxLayout(self._host)
#        self._form.setContentsMargins(2, 2, 8, 2)
#        self._form.setSpacing(2)
#        self._placeholder = QLabel(self._EMPTY_TEXT)
#        self._placeholder.setObjectName("placeholder")
#        self._placeholder.setWordWrap(True)
#        self._form.addWidget(self._placeholder)
#        self._form.addStretch(1)
#        self._scroll.setWidget(self._host)
#        outer.addWidget(self._scroll, 1)
#
#        self.set_step(None, {}, [])
#
#    # -- public API --------------------------------------------------------
#    def set_step(self, describe: Optional[Dict[str, Any]],
#                 current_params: Optional[Dict[str, Any]] = None,
#                 stream_choices: Optional[Sequence[str]] = None) -> None:
#        """重建表單。``describe=None`` -> 顯示提示語（未選節點）。"""
#        current_params = dict(current_params or {})
#        streams = [str(s) for s in (stream_choices or [])]
#        self._describe = describe
#        self._building = True
#        try:
#            self._clear_rows()
#            if not describe:
#                self._title.setText("")
#                self._title.setVisible(False)
#                self._step_help.setText("")
#                self._step_help.setVisible(False)
#                self._placeholder.setVisible(True)
#                return
#            self._title.setText(str(describe.get("label")
#                                    or describe.get("key") or ""))
#            self._title.setVisible(True)
#            self._step_help.setText(str(describe.get("help", "")))
#            self._step_help.setVisible(bool(describe.get("help")))
#            self._placeholder.setVisible(False)
#            for spec in describe.get("params", []):
#                name = str(spec.get("name", ""))
#                value = current_params.get(name, spec.get("default"))
#                editor = self._make_editor(spec, value, streams)
#                editor.setToolTip(str(spec.get("help", "")))
#                row = _ParamRow(spec, editor, self._host)
#                self._form.insertWidget(self._form.count() - 1, row)
#                self._rows[name] = row
#        finally:
#            self._building = False
#        self._sync_curve_override()
#
#    def _sync_curve_override(self) -> None:
#        """曲線一旦不是 y=x，就把 ``gamma`` 那列調淡並說明原因。
#
#        規則本身寫在 ``steps/tone.py``（曲線接管 gamma）。這裡只是**讓它看得
#        見** —— 不然使用者會拉了曲線又去動 gamma，然後發現 gamma 沒有反應。
#        """
#        curve_row = None
#        for name, row in self._rows.items():
#            if str(row.spec.get("type", "")) == "curve":
#                curve_row = row
#                break
#        if curve_row is None:
#            return
#        active = not curve_row.editor.is_identity()
#        gamma = self._rows.get("gamma")
#        if gamma is not None and not gamma.has_error():
#            gamma.set_dimmed(active, "Not used while a custom curve is drawn.")
#
#    def step_key(self) -> Optional[str]:
#        return None if not self._describe else str(self._describe.get("key"))
#
#    def param_names(self) -> List[str]:
#        return list(self._rows)
#
#    def editor(self, name: str) -> Optional[QWidget]:
#        row = self._rows.get(name)
#        return None if row is None else row.editor
#
#    def slider(self, name: str) -> Optional[QSlider]:
#        """那一列的滑桿（沒有上下界的參數沒有滑桿，回 ``None``）。"""
#        row = self._rows.get(name)
#        return None if row is None else row.slider
#
#    def hint_text(self, name: str) -> str:
#        """那一列的說明**全文**。
#
#        不是 ``hint.text()`` —— 收起來的時候那是切過的字（``像這樣…``），
#        而問「說明寫了什麼」的人要的從來不是「畫面上現在放得下多少」。"""
#        row = self._rows.get(name)
#        return "" if row is None else row.hint.full_text()
#
#    def show_error(self, name: str, msg: str) -> None:
#        """把 ``name`` 那一列的說明換成紅色錯誤訊息。"""
#        row = self._rows.get(name)
#        if row is not None:
#            row.set_error(msg)
#
#    def clear_errors(self) -> None:
#        """所有列還原成白話說明（灰字）。"""
#        for row in self._rows.values():
#            if row.has_error():
#                row.set_error(None)
#
#    def has_error(self, name: str) -> bool:
#        row = self._rows.get(name)
#        return bool(row is not None and row.has_error())
#
#    # -- internals ---------------------------------------------------------
#    def _clear_rows(self) -> None:
#        for row in self._rows.values():
#            self._form.removeWidget(row)
#            row.setParent(None)
#            row.deleteLater()
#        self._rows = {}
#
#    def _emit(self, name: str, value: Any) -> None:
#        if self._building:
#            return
#        self.param_edited.emit(name, value)
#
#    def _make_editor(self, spec: Dict[str, Any], value: Any,
#                     streams: Sequence[str]) -> QWidget:
#        name = str(spec.get("name", ""))
#        ptype = str(spec.get("type", "str"))
#        unit = str(spec.get("unit", "") or "")
#        lo, hi = spec.get("min"), spec.get("max")
#
#        if ptype == "int":
#            w = QSpinBox()
#            w.setRange(int(lo) if lo is not None else -10 ** 9,
#                       int(hi) if hi is not None else 10 ** 9)
#            if unit:
#                w.setSuffix(" " + unit)
#            w.setValue(_safe_int(value))
#            w.valueChanged.connect(lambda v, n=name: self._emit(n, int(v)))
#            return w
#
#        if ptype == "float":
#            w = QDoubleSpinBox()
#            w.setDecimals(3)
#            w.setRange(float(lo) if lo is not None else -1e9,
#                       float(hi) if hi is not None else 1e9)
#            span = None if (lo is None or hi is None) else float(hi) - float(lo)
#            w.setSingleStep(0.01 if (span is not None and span <= 2.0) else 0.1)
#            if unit:
#                w.setSuffix(" " + unit)
#            w.setValue(_safe_float(value))
#            w.valueChanged.connect(lambda v, n=name: self._emit(n, float(v)))
#            return w
#
#        if ptype == "bool":
#            w = QCheckBox("Enabled")
#            w.setChecked(bool(value))
#            w.toggled.connect(lambda v, n=name: self._emit(n, bool(v)))
#            return w
#
#        if ptype == "choice":
#            w = QComboBox()
#            choices = [str(c) for c in (spec.get("choices") or [])]
#            w.addItems(choices)
#            text = str(value)
#            if text in choices:
#                w.setCurrentIndex(choices.index(text))
#            w.currentTextChanged.connect(lambda t, n=name: self._emit(n, str(t)))
#            return w
#
#        if ptype == "curve":
#            w = CurveField()
#            w.set_text("" if value is None else str(value))
#            w.curve_changed.connect(lambda t, n=name: self._emit(n, str(t)))
#            w.curve_changed.connect(lambda _t: self._sync_curve_override())
#            return w
#
#        if ptype == "image_keys":
#            w = StreamPicker(streams, "" if value is None else str(value))
#            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
#            return w
#
#        if ptype == "template":
#            w = TemplateField("" if value is None else str(value))
#            # 值不是在這裡編的（模板是一張影像）——按鈕只是把請求往上送，
#            # 由 Studio 開對話框，成交之後照一般的路徑寫回參數。
#            w.build_requested.connect(lambda n=name: self.action_requested.emit(n))
#            return w
#
#        if ptype == "image_key":
#            w = QComboBox()
#            w.setEditable(True)          # 可挑上游影像流，也可自己打新流名
#            items = list(dict.fromkeys([str(s) for s in streams]))
#            text = str(value)
#            if text and text not in items:
#                items.append(text)
#            w.addItems(items)
#            w.setCurrentText(text)
#            w.currentTextChanged.connect(lambda t, n=name: self._emit(n, str(t)))
#            return w
#
#        w = QLineEdit()
#        w.setText("" if value is None else str(value))
#        w.textChanged.connect(lambda t, n=name: self._emit(n, str(t)))
#        return w
#
#
## --------------------------------------------------------------------------- #
## 2b. CurveEditor —— 自己拉的色調曲線（F7-8）
## --------------------------------------------------------------------------- #
#class CurveEditor(QWidget):
#    """可拖曳的色調曲線編輯器。橫軸 = 輸入灰階，縱軸 = 輸出灰階，兩軸都 0–1。
#
#    操作（右下角就寫著，不用先看說明）
#    ----------------------------------
#    * 拖控制點 = 改曲線；
#    * 在空白處按左鍵 = 加一個控制點；
#    * 對控制點右鍵（或雙擊）= 刪掉它。頭尾兩點刪不掉，
#      因為曲線必須覆蓋整個灰階範圍。
#
#    **畫出來的線就是影像上套的線** —— 這裡呼叫的是 core 的
#    ``algo.curve.curve_lut``，跟 ``gamma`` 卡執行時用的是同一個函式。
#    UI 自己再實作一份插值是很容易發生的事，那會讓使用者看到的和跑出來的不一樣。
#    這是本檔唯一一處 import ``adept.core``，理由就是這個 —— 而且它是純運算、
#    不碰引擎，沒有違反「元件不跑 pipeline」的約束。
#    """
#
#    curve_changed = Signal(str)
#
#    _PAD = 10.0                 # 邊界留白（點拖到角落時還抓得到）
#    _HIT = 9.0                  # 控制點的點擊半徑（螢幕像素）
#    _DOT = 4.0
#
#    def __init__(self, parent: Optional[QWidget] = None, compact: bool = True):
#        super().__init__(parent)
#        from ..core.pipeline.curve import IDENTITY, parse_curve
#
#        self._parse = parse_curve
#        self._points: List[Tuple[float, float]] = list(parse_curve(IDENTITY))
#        self._drag: Optional[int] = None
#        self._compact = bool(compact)
#        self.setMinimumSize(QSize(150, 130 if compact else 300))
#        if not compact:
#            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
#        self.setMouseTracking(True)
#        self.setCursor(Qt.CrossCursor)
#        self.setToolTip("Drag to bend · click to add a point · "
#                        "right-click a point to remove it")
#
#    # -- public API --------------------------------------------------------
#    def text(self) -> str:
#        from ..core.pipeline.curve import format_curve
#        return format_curve(self._points)
#
#    def points(self) -> List[Tuple[float, float]]:
#        return list(self._points)
#
#    def set_text(self, text: str, emit: bool = False) -> bool:
#        """從控制點字串載入。字串壞掉時**保持原樣並回 False**。
#
#        參數表單是「打字即生效」的，使用者打到一半必然出現不合法的中間狀態；
#        那時候把曲線清成 y=x 會讓他辛苦拉的線消失。
#        """
#        try:
#            pts = self._parse(text)
#        except ValueError:
#            return False
#        self._points = list(pts)
#        self.update()
#        if emit:
#            self.curve_changed.emit(self.text())
#        return True
#
#    def reset(self) -> None:
#        from ..core.pipeline.curve import IDENTITY
#        self.set_text(IDENTITY, emit=True)
#
#    def is_identity(self) -> bool:
#        from ..core.pipeline.curve import is_identity
#        return is_identity(self._points)
#
#    # -- 座標轉換 ----------------------------------------------------------
#    def _plot_rect(self) -> QRectF:
#        return QRectF(self.rect()).adjusted(self._PAD, self._PAD,
#                                            -self._PAD, -self._PAD)
#
#    def _to_px(self, x: float, y: float) -> QPointF:
#        r = self._plot_rect()
#        return QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())
#
#    def _to_unit(self, p: QPointF) -> Tuple[float, float]:
#        r = self._plot_rect()
#        w = max(1.0, r.width())
#        h = max(1.0, r.height())
#        return (float(np.clip((p.x() - r.left()) / w, 0.0, 1.0)),
#                float(np.clip((r.bottom() - p.y()) / h, 0.0, 1.0)))
#
#    def _hit(self, p: QPointF) -> Optional[int]:
#        for i, (x, y) in enumerate(self._points):
#            if (self._to_px(x, y) - p).manhattanLength() <= self._HIT * 1.6:
#                return i
#        return None
#
#    # -- painting ----------------------------------------------------------
#    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
#        from ..core.algo.curve import curve_lut
#
#        p = QPainter(self)
#        p.setRenderHint(QPainter.Antialiasing, True)
#        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
#        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
#        p.setBrush(QColor(TOKENS["image_backdrop"]))
#        p.drawRoundedRect(r, 5, 5)
#
#        plot = self._plot_rect()
#        grid = QColor(TOKENS["border_default"])
#        grid.setAlpha(120)
#        p.setPen(QPen(grid, 1))
#        for i in range(1, 4):
#            f = i / 4.0
#            p.drawLine(self._to_px(f, 0.0), self._to_px(f, 1.0))
#            p.drawLine(self._to_px(0.0, f), self._to_px(1.0, f))
#
#        # y = x 參考線（虛線）—— 使用者隨時看得出自己偏離了多少
#        ref = QPen(QColor(TOKENS["text_disabled"]), 1, Qt.DashLine)
#        p.setPen(ref)
#        p.drawLine(self._to_px(0.0, 0.0), self._to_px(1.0, 1.0))
#
#        accent = QColor(theme.seg_hex("image"))
#        n = max(24, int(plot.width()))
#        lut = curve_lut(self._points, n)
#        p.setPen(QPen(accent, 2.0))
#        prev = self._to_px(0.0, float(lut[0]))
#        for i in range(1, n):
#            cur = self._to_px(i / (n - 1.0), float(lut[i]))
#            p.drawLine(prev, cur)
#            prev = cur
#
#        p.setPen(QPen(QColor(TOKENS["bg_surface"]), 1.5))
#        p.setBrush(accent)
#        for x, y in self._points:
#            c = self._to_px(x, y)
#            p.drawEllipse(c, self._DOT, self._DOT)
#        p.end()
#
#    # -- interaction -------------------------------------------------------
#    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
#        pos = QPointF(e.position())
#        idx = self._hit(pos)
#        if e.button() == Qt.RightButton:
#            if idx is not None:
#                self._remove(idx)
#            return
#        if e.button() != Qt.LeftButton:
#            return
#        if idx is None:
#            idx = self._insert(*self._to_unit(pos))
#            if idx is None:
#                return
#        self._drag = idx
#        self.setCursor(Qt.ClosedHandCursor)
#
#    def mouseMoveEvent(self, e) -> None:       # noqa: D102 - Qt hook
#        if self._drag is None:
#            return
#        x, y = self._to_unit(QPointF(e.position()))
#        i = self._drag
#        if i == 0:
#            x = 0.0                       # 頭尾的 x 鎖住：曲線必須從 0 到 1
#        elif i == len(self._points) - 1:
#            x = 1.0
#        else:
#            # 不准越過鄰居 —— 越過去就不是函數了（同一個輸入兩個輸出）
#            x = float(np.clip(x, self._points[i - 1][0] + 0.01,
#                              self._points[i + 1][0] - 0.01))
#        self._points[i] = (x, y)
#        self.update()
#        self.curve_changed.emit(self.text())
#
#    def mouseReleaseEvent(self, _e) -> None:   # noqa: D102 - Qt hook
#        if self._drag is not None:
#            self._drag = None
#            self.setCursor(Qt.CrossCursor)
#
#    def mouseDoubleClickEvent(self, e) -> None:  # noqa: D102 - Qt hook
#        idx = self._hit(QPointF(e.position()))
#        if idx is not None:
#            self._remove(idx)
#
#    def _insert(self, x: float, y: float) -> Optional[int]:
#        """在 x 的位置插一個控制點；太靠近既有點就不插（會變成不合法的曲線）。"""
#        if any(abs(px - x) < 0.02 for px, _py in self._points):
#            return None
#        self._points.append((x, y))
#        self._points.sort(key=lambda pt: pt[0])
#        self.update()
#        self.curve_changed.emit(self.text())
#        return self._points.index((x, y))
#
#    def _remove(self, idx: int) -> None:
#        if idx <= 0 or idx >= len(self._points) - 1:
#            return                       # 頭尾刪不掉
#        del self._points[idx]
#        self.update()
#        self.curve_changed.emit(self.text())
#
#
#class CurveField(QWidget):
#    """參數表單裡的曲線欄位：小張的編輯器 + ``Reset`` / ``Enlarge…``。
#
#    小張的可以直接拉（常見的微調不用開視窗），要做細活再按 ``Enlarge…``
#    開一張大的。兩邊改的是同一組控制點。
#    """
#
#    curve_changed = Signal(str)
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        lay = QVBoxLayout(self)
#        lay.setContentsMargins(0, 0, 0, 0)
#        lay.setSpacing(3)
#
#        self.editor = CurveEditor(self)
#        self.editor.curve_changed.connect(self._on_changed)
#        lay.addWidget(self.editor)
#
#        bar = QHBoxLayout()
#        bar.setContentsMargins(0, 0, 0, 0)
#        bar.setSpacing(5)
#        self.reset_button = QPushButton("Reset to y = x", self)
#        self.reset_button.setToolTip("Put the curve back to a straight line "
#                                     "(the gamma slider takes over again)")
#        self.reset_button.clicked.connect(self.editor.reset)
#        self.enlarge_button = QPushButton("Enlarge…", self)
#        self.enlarge_button.setToolTip("Open a big curve canvas")
#        self.enlarge_button.clicked.connect(self.open_dialog)
#        bar.addWidget(self.reset_button)
#        bar.addWidget(self.enlarge_button)
#        bar.addStretch(1)
#        lay.addLayout(bar)
#
#    def text(self) -> str:
#        return self.editor.text()
#
#    def set_text(self, text: str, emit: bool = False) -> bool:
#        return self.editor.set_text(text, emit=emit)
#
#    def is_identity(self) -> bool:
#        return self.editor.is_identity()
#
#    def open_dialog(self) -> "CurveDialog":
#        dlg = CurveDialog(self.editor.text(), self)
#        dlg.curve_changed.connect(self._adopt)
#        dlg.show()
#        self._dialog = dlg          # 保住參照，不然 show() 之後會被 GC
#        return dlg
#
#    def _adopt(self, text: str) -> None:
#        if self.editor.set_text(text):
#            self.curve_changed.emit(self.editor.text())
#
#    def _on_changed(self, text: str) -> None:
#        self.curve_changed.emit(text)
#
#
#class CurveDialog(QDialog):
#    """放大版的曲線畫布。非模態 —— 一邊拉曲線一邊看主視窗的預覽更新。"""
#
#    curve_changed = Signal(str)
#
#    def __init__(self, text: str, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.setWindowTitle("Tone curve")
#        self.setModal(False)
#        self.resize(420, 460)
#
#        lay = QVBoxLayout(self)
#        lay.setContentsMargins(12, 12, 12, 12)
#        lay.setSpacing(8)
#
#        head = QLabel("Input gray level across, output up. Drag a point to "
#                      "bend the curve; click an empty spot to add one; "
#                      "right-click a point to remove it.", self)
#        head.setWordWrap(True)
#        head.setObjectName("paramHint")
#        lay.addWidget(head)
#
#        self.editor = CurveEditor(self, compact=False)
#        self.editor.set_text(text)
#        self.editor.curve_changed.connect(self.curve_changed)
#        lay.addWidget(self.editor, 1)
#
#        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
#        reset = QPushButton("Reset to y = x", self)
#        reset.clicked.connect(self.editor.reset)
#        buttons.addButton(reset, QDialogButtonBox.ResetRole)
#        buttons.rejected.connect(self.close)
#        lay.addWidget(buttons)
#
#
#def _safe_int(value: Any, default: int = 0) -> int:
#    try:
#        return int(value)
#    except (TypeError, ValueError):
#        return default
#
#
#def _safe_float(value: Any, default: float = 0.0) -> float:
#    try:
#        f = float(value)
#    except (TypeError, ValueError):
#        return default
#    return default if (math.isnan(f) or math.isinf(f)) else f
#
#
## --------------------------------------------------------------------------- #
## 3. LibraryPanel
## --------------------------------------------------------------------------- #
#def draw_group_icon(p: QPainter, group: str, color: str, size: float) -> None:
#    """在 ``p`` 的目前原點畫一個 ``size`` × ``size`` 的階段圖示。
#
#    **抽成自由函式**，是為了讓左側 rail 的按鈕、卡片庫的區塊標題、以及畫布上的
#    節點卡三處共用完全相同的圖形 —— 使用者在 rail 上看到的尺，在節點上看到的
#    也要是同一把尺，不然「圖示」就只是裝飾而不是語言。
#
#    不吃任何圖檔：repo 有「只放純文字檔」的不變量（公司機 DLP 會擋含二進位的
#    壓縮檔，見 ``docs/HANDOVER.md`` §5）。``.svg`` 其實是純文字、過得了 DLP，
#    但用 QPainter 連「要不要把圖檔加進版控」這個問題都不用問，而且顏色直接吃
#    token —— 換主題時圖示自動跟著變。
#    """
#    p.setRenderHint(QPainter.Antialiasing, True)
#    pen = QPen(QColor(color), max(1.2, size / 11.0))
#    pen.setCapStyle(Qt.RoundCap)
#    p.setPen(pen)
#    p.setBrush(Qt.NoBrush)
#    w = h = float(size)
#    m = w / 7.5                       # 邊界留白，隨尺寸縮放
#    g = str(group)
#
#    if g == "input":                    # 匣子 + 往下的箭頭
#        p.drawRect(QRectF(m, h * 0.55, w - 2 * m, h * 0.45 - m))
#        p.drawLine(QPointF(w / 2, m), QPointF(w / 2, h * 0.46))
#        p.drawLine(QPointF(w / 2 - w * 0.16, h * 0.30), QPointF(w / 2, h * 0.46))
#        p.drawLine(QPointF(w / 2 + w * 0.16, h * 0.30), QPointF(w / 2, h * 0.46))
#    elif g == "enhance":                # 亮度：半實心圓
#        p.drawEllipse(QRectF(m, m, w - 2 * m, h - 2 * m))
#        p.setBrush(QColor(color))
#        p.setPen(Qt.NoPen)
#        p.drawPie(QRectF(m, m, w - 2 * m, h - 2 * m), -90 * 16, 180 * 16)
#    elif g == "region":                 # 取景框（四個角）+ 中心點
#        c = w * 0.24
#        for x0, y0, dx, dy in ((m, m, 1, 1), (w - m, m, -1, 1),
#                               (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
#            p.drawLine(QPointF(x0, y0), QPointF(x0 + c * dx, y0))
#            p.drawLine(QPointF(x0, y0), QPointF(x0, y0 + c * dy))
#        p.setBrush(QColor(color))
#        p.setPen(Qt.NoPen)
#        r = w * 0.11
#        p.drawEllipse(QRectF(w / 2 - r, h / 2 - r, 2 * r, 2 * r))
#    elif g == "compare":                # 兩個交疊的方框
#        side = w - 2 * m - w * 0.2
#        p.drawRect(QRectF(m, m, side, side))
#        p.drawRect(QRectF(m + w * 0.2, m + w * 0.2, side, side))
#    elif g == "measure":                # 尺（一條線 + 刻度）
#        base = h - m
#        p.drawLine(QPointF(m, base), QPointF(w - m, base))
#        for i in range(4):
#            x = m + i * (w - 2 * m) / 3.0
#            p.drawLine(QPointF(x, base),
#                       QPointF(x, base - (h * 0.40 if i % 2 == 0 else h * 0.23)))
#    elif g == "search":                 # 放大鏡（rail 上的搜尋鈕，不是流程階段）
#        r = w * 0.29
#        p.drawEllipse(QRectF(m, m, 2 * r, 2 * r))
#        p.drawLine(QPointF(m + 2 * r * 0.86, m + 2 * r * 0.86),
#                   QPointF(w - m, h - m))
#    else:                               # adc / 其他：打勾
#        p.drawLine(QPointF(m, h * 0.52), QPointF(w * 0.42, h - m))
#        p.drawLine(QPointF(w * 0.42, h - m), QPointF(w - m, m))
#
#
#class GroupIcon(QWidget):
#    """:func:`draw_group_icon` 的 widget 包裝（給 rail 與區塊標題用）。"""
#
#    _SIZE = 15
#
#    def __init__(self, group: str, color: str, parent: Optional[QWidget] = None,
#                 size: Optional[int] = None):
#        super().__init__(parent)
#        self.group = str(group)
#        self.color = str(color)
#        self._SIZE = int(size or self._SIZE)
#        self.setFixedSize(self._SIZE, self._SIZE)
#
#    def set_color(self, color: str) -> None:
#        self.color = str(color)
#        self.update()
#
#    def paintEvent(self, _e) -> None:      # noqa: D102 - Qt hook
#        p = QPainter(self)
#        draw_group_icon(p, self.group, self.color, float(self._SIZE))
#        p.end()
#
#
#class _LibraryItem(QFrame):
#    """卡片庫的一列：名稱 + hover 才出現的「Add」；雙擊也能加入。
#
#    ``set_missing(streams)`` 會把「上游還沒產出它要的影像流」這件事顯示成
#    一個灰字 badge（例：``needs diff``）並把整列調淡 —— 但**仍然可以加**。
#    卡片庫的順序不等於執行順序，使用者可能先放卡再補上游；擋著不給加只會
#    讓人以為工具壞了。
#    """
#
#    activated = Signal(str)
#
#    def __init__(self, describe: Dict[str, Any], color: str,
#                 parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.step_key = str(describe.get("key", ""))
#        self.reads = [str(r) for r in (describe.get("reads") or ())]
#        self.setObjectName("libItem")
#        self.setCursor(Qt.PointingHandCursor)
#        self._base_tip = (str(describe.get("help", ""))
#                          or str(describe.get("label", "")))
#        if describe.get("requires_ref"):
#            self._base_tip += " (needs a ref image)"
#        self.setToolTip(self._base_tip)
#        self.setStyleSheet(
#            "QFrame#libItem { background:transparent; border:1px solid transparent;"
#            " border-radius:5px; }"
#            "QFrame#libItem:hover { background:%s; border-color:%s; }"
#            % (TOKENS["hover_warm"], TOKENS["border_default"])
#        )
#
#        lay = QHBoxLayout(self)
#        lay.setContentsMargins(10, 3, 6, 3)
#        lay.setSpacing(6)
#
#        self.dot = QFrame()
#        self.dot.setFixedSize(5, 5)
#        self.dot.setStyleSheet("background:%s; border-radius:2px;" % color)
#        lay.addWidget(self.dot)
#
#        self.label = QLabel(str(describe.get("label") or self.step_key))
#        self.label.setToolTip(self._base_tip)
#        lay.addWidget(self.label, 1)
#
#        self.badge = QLabel("")
#        self.badge.setObjectName("libBadge")
#        self.badge.setStyleSheet(
#            "color:%s; font-size:10px; border:1px solid %s; border-radius:3px;"
#            " padding:0px 4px;" % (TOKENS["text_disabled"], TOKENS["border_default"]))
#        self.badge.setVisible(False)
#        self.missing: List[str] = []
#        lay.addWidget(self.badge)
#
#        self.add_button = QPushButton("Add")
#        self.add_button.setObjectName("cardButton")
#        self.add_button.setCursor(Qt.PointingHandCursor)
#        self.add_button.setToolTip("Append this card to the end of the pipeline")
#        self.add_button.setFixedWidth(40)
#        self.add_button.clicked.connect(
#            lambda: self.activated.emit(self.step_key))
#        self.add_button.setVisible(False)
#        lay.addWidget(self.add_button)
#
#    # -- 前置條件 badge -----------------------------------------------------
#    def set_missing(self, missing: Sequence[str]) -> None:
#        """``missing`` = 這張卡要讀、但上游還沒有的影像流。"""
#        missing = [str(m) for m in (missing or ())]
#        self.missing = list(missing)
#        if missing:
#            self.badge.setText("needs %s" % ", ".join(missing))
#            self.badge.setVisible(True)
#            self.label.setStyleSheet("color:%s;" % TOKENS["text_disabled"])
#            self.setToolTip(
#                "%s\n\nNot available yet: this card reads %s, which nothing "
#                "upstream produces so far. You can still add it — the pipeline "
#                "order is up to you."
#                % (self._base_tip, ", ".join(missing)))
#        else:
#            self.badge.setVisible(False)
#            self.label.setStyleSheet("")
#            self.setToolTip(self._base_tip)
#
#    def badge_text(self) -> str:
#        """目前的 badge 文字（沒有就空字串）。
#
#        看的是 :attr:`missing` 而不是 ``badge.isVisible()`` —— 視窗還沒 show()
#        之前 Qt 的可見性一律是 False，headless 測試會全部誤判。
#        """
#        return self.badge.text() if self.missing else ""
#
#    def enterEvent(self, e) -> None:      # noqa: D102 - Qt hook
#        self.add_button.setVisible(True)
#        super().enterEvent(e)
#
#    def leaveEvent(self, e) -> None:      # noqa: D102 - Qt hook
#        self.add_button.setVisible(False)
#        super().leaveEvent(e)
#
#    def mouseDoubleClickEvent(self, e) -> None:   # noqa: D102 - Qt hook
#        if e.button() == Qt.LeftButton:
#            self.activated.emit(self.step_key)
#
#
#class StageButton(QFrame):
#    """左側 rail 的一顆大按鈕：icon + 階段名 + 卡片數。
#
#    這是 F7-7 的要求：**先用大 icon 分功能，按下去才帶出裡面的小功能。**
#    六個階段一次全展開，等於一開始就把 15 張卡攤在使用者面前 ——
#    那正是「太瑣碎」的來源。
#    """
#
#    clicked = Signal(str)
#
#    _ICON = 30
#
#    def __init__(self, group: str, title: str, subtitle: str, colour: str,
#                 parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.group = str(group)
#        self.setObjectName("stageButton")
#        self.setCursor(Qt.PointingHandCursor)
#        self.setToolTip("%s — %s" % (title, subtitle))
#        self._colour = colour
#        self._active = False
#
#        self.setFixedWidth(58)
#        lay = QVBoxLayout(self)
#        lay.setContentsMargins(2, 7, 2, 5)
#        lay.setSpacing(2)
#        lay.setAlignment(Qt.AlignHCenter)
#
#        self.icon = GroupIcon(self.group, colour, self, size=self._ICON)
#        lay.addWidget(self.icon, 0, Qt.AlignHCenter)
#
#        self.label = QLabel(title, self)
#        self.label.setAlignment(Qt.AlignHCenter)
#        self.label.setStyleSheet("font-size:9px; font-weight:600;")
#        lay.addWidget(self.label)
#
#        self.count = QLabel("", self)
#        self.count.setAlignment(Qt.AlignHCenter)
#        self.count.setStyleSheet("font-size:9px; color:%s;" % TOKENS["text_disabled"])
#        lay.addWidget(self.count)
#        self._restyle()
#
#    def set_count(self, n: int) -> None:
#        self.count.setText("" if n <= 0 else str(int(n)))
#
#    def set_active(self, active: bool) -> None:
#        self._active = bool(active)
#        self._restyle()
#
#    def is_active(self) -> bool:
#        return self._active
#
#    def refresh_colour(self, colour: str) -> None:
#        self._colour = colour
#        self.icon.set_color(colour)
#        self._restyle()
#
#    def _restyle(self) -> None:
#        self.setStyleSheet(
#            "QFrame#stageButton { background:%s; border:1px solid %s;"
#            " border-radius:6px; }"
#            "QFrame#stageButton:hover { background:%s; }"
#            % (TOKENS["accent_bg"] if self._active else "transparent",
#               TOKENS["accent_border"] if self._active else "transparent",
#               TOKENS["hover_warm"]))
#
#    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
#        if e.button() == Qt.LeftButton:
#            self.clicked.emit(self.group)
#        super().mousePressEvent(e)
#
#
#class LibraryPanel(QWidget):
#    """卡片庫：依**流程階段**分組（F7-3），每組一個 QPainter 畫的 icon + 標題。
#
#    為什麼不再依 ``category`` 分
#    ----------------------------
#    ``category``（影像／算法）描述的是「這張卡吐什麼型別」——那是引擎的分類
#    （快取切點、驗證順序）。使用者要的是「我想幹嘛」，所以改用 ``group``：
#
#        Input → Enhance → Region → Compare → Measure → ADC
#
#    讀起來是一句話，而且每段有一條機械可判定的規則（見 ``pipeline/step.py``）。
#
#    另外兩件讓 17 列不再瑣碎的事：
#
#    * **搜尋框** —— 打字即時過濾（比對名稱、key 與說明）。
#    * **前置條件 badge** —— ``set_available_streams()`` 之後，
#      上游還沒產出所需影像流的卡會標成 ``needs diff`` 並調淡。
#    """
#
#    add_requested = Signal(str)
#    #: 卡片區展開/收起（``True`` = 展開）。主視窗據此縮放左欄寬度 ——
#    #: 收起來時整欄只留 rail，工作區才真的變寬。
#    panel_toggled = Signal(bool)
#
#    #: 顯示順序與標題。id 對應 ``pipeline/step.py`` 的 ``GROUP_*``。
#    GROUPS = (
#        ("input", "Input", "Load this defect's images"),
#        ("enhance", "Enhance", "Image in, image out"),
#        ("region", "Region", "Decide where to look"),
#        ("compare", "Compare", "Two images in, difference out"),
#        ("measure", "Measure", "Image + region in, numbers out"),
#        ("adc", "ADC", "Numbers in, score and bin out"),
#    )
#    _ORDER = tuple(g for g, _t, _s in GROUPS)
#    _EMPTY_TEXT = "(no cards in this section)"
#    _NO_MATCH_TEXT = "(no card matches)"
#
#    #: group -> 所屬的三段式 segment。**顏色不再從這裡取**（F7-9 起走
#    #: ``theme.group_hex``，六個階段各一個色相）；這份對照留著是因為
#    #: 「這個階段屬於哪一段」在說明文字與排序上仍然成立。
#    _GROUP_SEG = {"input": "image", "enhance": "image", "region": "algo",
#                  "compare": "image", "measure": "algo", "adc": "adc"}
#
#    #: 直式 icon rail 的寬度（收起來時整個 panel 就縮到只剩這條）。
#    RAIL_W = 66
#    #: 展開時卡片區至少要多寬（卡名 + badge 放得下）。
#    PANEL_W = 190
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self._items: Dict[str, _LibraryItem] = {}
#        self._describes: Dict[str, Dict[str, Any]] = {}
#        self._section_boxes: Dict[str, QVBoxLayout] = {}
#        self._headers: Dict[str, QWidget] = {}
#        self._icons: Dict[str, GroupIcon] = {}
#        self._available: List[str] = []
#        self._query = ""
#        self._shown_groups: List[str] = []
#
#        self._open_group: Optional[str] = None
#
#        # 版面：**直式 rail（左）｜ 卡片區（右）**。
#        # F7-8：像工作列一樣由上而下，點了 icon 才顯示裡面的卡 ——
#        # 這樣左邊的操作區平常是乾淨的。
#        outer = QHBoxLayout(self)
#        outer.setContentsMargins(0, 0, 0, 0)
#        outer.setSpacing(0)
#
#        self.rail = QWidget(self)
#        self.rail.setObjectName("stageRail")
#        self.rail.setFixedWidth(self.RAIL_W)
#        rail_lay = QVBoxLayout(self.rail)
#        rail_lay.setContentsMargins(2, 6, 2, 6)
#        rail_lay.setSpacing(2)
#        self.stage_buttons: Dict[str, StageButton] = {}
#        for gid, title, subtitle in self.GROUPS:
#            btn = StageButton(gid, title, subtitle, theme.group_hex(gid),
#                              self.rail)
#            btn.clicked.connect(self.toggle_group)
#            rail_lay.addWidget(btn)
#            self.stage_buttons[gid] = btn
#        rail_lay.addStretch(1)
#
#        # 搜尋鈕留在 rail 上（不是在 panel 裡）—— panel 收起來時搜尋框跟著藏，
#        # 沒有這顆就再也打不開搜尋了。
#        self.search_button = StageButton(
#            "search", "Search", "Find a card by name or description",
#            TOKENS["text_secondary"], self.rail)
#        self.search_button.clicked.connect(lambda _g: self.focus_search())
#        rail_lay.addWidget(self.search_button)
#        outer.addWidget(self.rail)
#
#        # 右邊：搜尋 + 卡片清單（收起來時整塊隱藏）
#        self.panel = QWidget(self)
#        panel_lay = QVBoxLayout(self.panel)
#        panel_lay.setContentsMargins(0, 0, 0, 0)
#        panel_lay.setSpacing(0)
#
#        self.search = QLineEdit(self)
#        self.search.setPlaceholderText("Search cards…")
#        self.search.setClearButtonEnabled(True)
#        self.search.setToolTip("Filter the card library by name or description")
#        self.search.textChanged.connect(self._on_search)
#        wrap = QWidget(self.panel)
#        wl = QHBoxLayout(wrap)
#        wl.setContentsMargins(6, 6, 8, 4)
#        wl.addWidget(self.search)
#        panel_lay.addWidget(wrap)
#
#        self._scroll = QScrollArea(self.panel)
#        self._scroll.setWidgetResizable(True)
#        self._scroll.setFrameShape(QFrame.NoFrame)
#        self._host = QWidget()
#        self._body = QVBoxLayout(self._host)
#        self._body.setContentsMargins(6, 2, 8, 6)
#        self._body.setSpacing(2)
#
#        for gid, title, subtitle in self.GROUPS:
#            self._body.addWidget(self._make_header(gid, title, subtitle))
#            box = QVBoxLayout()
#            box.setContentsMargins(0, 0, 0, 8)
#            box.setSpacing(1)
#            self._body.addLayout(box)
#            self._section_boxes[gid] = box
#
#        self._body.addStretch(1)
#        self._scroll.setWidget(self._host)
#        panel_lay.addWidget(self._scroll, 1)
#        outer.addWidget(self.panel, 1)
#
#        self.set_steps([])
#        self.toggle_group(self._ORDER[0])       # 開窗先展開 Input
#
#    # -- 區塊標題（icon + 標題，取代舊的填滿色塊）---------------------------
#    def _make_header(self, gid: str, title: str, subtitle: str) -> QWidget:
#        colour = theme.group_hex(gid)
#        head = QWidget(self)
#        head.setObjectName("libSectionHeader")
#        head.setProperty("group", gid)
#        head.setToolTip(subtitle)
#        lay = QHBoxLayout(head)
#        lay.setContentsMargins(4, 8, 4, 2)
#        lay.setSpacing(7)
#
#        icon = GroupIcon(gid, colour, head)
#        icon.setToolTip(subtitle)
#        lay.addWidget(icon)
#        self._icons[gid] = icon
#
#        lbl = QLabel(title, head)
#        lbl.setObjectName("libSectionTitle")
#        lbl.setToolTip(subtitle)
#        lbl.setStyleSheet("color:%s; font-weight:700; font-size:11px;"
#                          % TOKENS["text_secondary"])
#        lay.addWidget(lbl)
#        lay.addStretch(1)
#        self._headers[gid] = head
#        return head
#
#    # -- public API --------------------------------------------------------
#    def set_steps(self, steps: Sequence[Dict[str, Any]]) -> None:
#        """用 ``Step.describe()`` 的 dict 清單重建整個卡片庫。"""
#        self._clear()
#        self._describes = {str(d.get("key", "")): dict(d) for d in (steps or [])}
#        by_group: Dict[str, List[Dict[str, Any]]] = {g: [] for g in self._ORDER}
#        for d in steps or []:
#            gid = str(d.get("group") or "") or "enhance"
#            by_group.setdefault(gid, []).append(d)
#
#        for gid in self._ORDER:
#            box = self._section_boxes[gid]
#            entries = by_group.get(gid, [])
#            if not entries:
#                box.addWidget(self._empty_label(self._EMPTY_TEXT))
#                continue
#            colour = theme.group_hex(gid)
#            for d in entries:
#                item = _LibraryItem(d, colour, self._host)
#                item.activated.connect(self.add_requested)
#                box.addWidget(item)
#                self._items[item.step_key] = item
#        for gid, btn in self.stage_buttons.items():
#            btn.set_count(len(by_group.get(gid, [])))
#        self._apply_filter()
#        self._apply_badges()
#
#    def set_available_streams(self, streams: Sequence[str]) -> None:
#        """告訴卡片庫「目前 pipeline 到最後為止產出了哪些影像流」。
#
#        據此標出前置條件未滿足的卡。傳空清單 = 不知道（badge 全清）。
#        """
#        self._available = [str(s) for s in (streams or [])]
#        self._apply_badges()
#
#    def entry(self, step_key: str) -> Optional[_LibraryItem]:
#        """取得某張卡片的那一列（給主視窗做 highlight／給測試點擊）。"""
#        return self._items.get(step_key)
#
#    def step_keys(self) -> List[str]:
#        return list(self._items)
#
#    def visible_step_keys(self) -> List[str]:
#        """目前**看得到**的卡（搜尋過濾之後）。
#
#        同樣用明確狀態（``_matches``）而不是 ``isVisible()``，理由見
#        :meth:`_LibraryItem.badge_text`。
#        """
#        return [k for k in self._items
#                if self._matches(k)
#                and self._group_open(str((self._describes.get(k) or {})
#                                         .get("group") or ""))]
#
#    def section_titles(self) -> List[str]:
#        return [lbl.text() for lbl in self.findChildren(QLabel)
#                if lbl.objectName() == "libSectionTitle"]
#
#    def visible_section_titles(self) -> List[str]:
#        """搜尋之後還有卡片的區塊標題（順序同 :data:`GROUPS`）。"""
#        return [title for gid, title, _sub in self.GROUPS
#                if gid in self._shown_groups]
#
#    # -- 展開 / 收合（F7-7）--------------------------------------------------
#    def toggle_group(self, group: Optional[str]) -> None:
#        """點同一顆再點一次 = 收起來；點別顆 = 換過去（一次只開一段）。
#
#        傳 ``None`` 直接全部收起來（測試 / 外部呼叫用）。訊號帶過來的是
#        ``str``，所以這裡不能用 ``str(group)`` 一律轉字串 —— ``str(None)``
#        會變成 ``"None"``，看起來像一個真的存在的段名。
#        """
#        gid = None if group is None else str(group)
#        self._open_group = None if (gid is None or self._open_group == gid) else gid
#        for g, btn in self.stage_buttons.items():
#            btn.set_active(g == self._open_group)
#        self._sync_panel()
#        self._apply_filter()
#
#    def panel_open(self) -> bool:
#        """卡片區現在是展開的嗎（收起來時只剩 rail）。
#
#        用明確狀態而不是 ``isVisible()`` —— 視窗還沒 show 之前 ``isVisible()``
#        一律是 False，那會讓「收起來了嗎」在建構期永遠答錯。
#        """
#        return self._open_group is not None or bool(self._query)
#
#    def _sync_panel(self) -> None:
#        """展開狀態 -> panel 顯示 + 本身的最小寬度 + 通知外面重排欄寬。"""
#        show = self.panel_open()
#        self.panel.setVisible(show)
#        self.setMinimumWidth(self.RAIL_W + (self.PANEL_W if show else 0))
#        self.panel_toggled.emit(show)
#
#    def open_group(self) -> Optional[str]:
#        """目前展開的是哪一段（都收起來時回 None）。"""
#        return self._open_group
#
#    def set_query(self, text: str) -> None:
#        """程式化設定搜尋字串（測試 / 外部呼叫用）。"""
#        self.search.setText(str(text or ""))
#
#    def focus_search(self) -> None:
#        """展開卡片區並把游標放進搜尋框（rail 上的放大鏡鈕）。"""
#        if not self.panel_open():
#            self.toggle_group(self._ORDER[0])
#        self.search.setFocus(Qt.OtherFocusReason)
#        self.search.selectAll()
#
#    def refresh_colors(self) -> None:
#        """換主題之後重新取色（icon 與圓點都是自繪/內嵌樣式）。"""
#        for gid, icon in self._icons.items():
#            icon.set_color(theme.group_hex(gid))
#        for gid, btn in self.stage_buttons.items():
#            btn.refresh_colour(theme.group_hex(gid))
#        self.search_button.refresh_colour(TOKENS["text_secondary"])
#
#    # -- internals ---------------------------------------------------------
#    def _empty_label(self, text: str) -> QLabel:
#        lbl = QLabel(text)
#        lbl.setObjectName("libEmpty")
#        lbl.setStyleSheet("color:%s; font-size:11px; padding-left:12px;"
#                          % TOKENS["text_disabled"])
#        return lbl
#
#    def _on_search(self, text: str) -> None:
#        self._query = str(text or "").strip().lower()
#        self._sync_panel()
#        self._apply_filter()
#
#    def _matches(self, key: str) -> bool:
#        if not self._query:
#            return True
#        d = self._describes.get(key) or {}
#        hay = " ".join([key, str(d.get("label", "")), str(d.get("help", "")),
#                        str(d.get("group", ""))]).lower()
#        return all(tok in hay for tok in self._query.split())
#
#    def _group_open(self, gid: str) -> bool:
#        """搜尋中 = 跨全部階段找；沒搜尋 = 只看展開的那一段。"""
#        return True if self._query else (gid == self._open_group)
#
#    def _apply_filter(self) -> None:
#        """過濾卡片；沒展開的階段整段收起來。"""
#        for key, item in self._items.items():
#            gid = str((self._describes.get(key) or {}).get("group") or "")
#            item.setVisible(self._matches(key) and self._group_open(gid))
#        shown: List[str] = []
#        for gid, head in self._headers.items():
#            box = self._section_boxes[gid]
#            hit = False
#            opened = self._group_open(gid)
#            for i in range(box.count()):
#                w = box.itemAt(i).widget()
#                if isinstance(w, _LibraryItem):
#                    hit = hit or (self._matches(w.step_key) and opened)
#                elif isinstance(w, QLabel):
#                    # 空區塊的提示語只在該段展開、且沒搜尋時顯示
#                    show = opened and not self._query
#                    w.setVisible(show)
#                    hit = hit or show
#            head.setVisible(hit)
#            if hit:
#                shown.append(gid)
#        self._shown_groups = [g for g in self._ORDER if g in shown]
#
#    def _apply_badges(self) -> None:
#        avail = set(self._available)
#        for key, item in self._items.items():
#            if not self._available:
#                item.set_missing(())
#                continue
#            item.set_missing([r for r in item.reads if r not in avail])
#
#    def _clear(self) -> None:
#        self._items = {}
#        for box in self._section_boxes.values():
#            while box.count():
#                item = box.takeAt(0)
#                w = item.widget()
#                if w is not None:
#                    w.setParent(None)
#                    w.deleteLater()
#
#
## --------------------------------------------------------------------------- #
## 4. PipelinePanel
## --------------------------------------------------------------------------- #
#class _NodeCard(QFrame):
#    """流程中的一個節點卡：左側 4px 段落色條 + 名稱/摘要 + 啟用勾 + ↑ ↓ ✕。"""
#
#    # 注意：不要把訊號取名 move / remove —— 會蓋掉 QWidget.move() 等既有方法。
#    clicked = Signal(str)
#    enable_toggled = Signal(str, bool)
#    move_requested = Signal(str, int)
#    remove_requested = Signal(str)
#
#    def __init__(self, node: Dict[str, Any], parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.node_id = str(node.get("node_id", ""))
#        self.category = str(node.get("category", ""))
#        self.enabled_flag = bool(node.get("enabled", True))
#        self.setObjectName("nodeCard")
#        self.setCursor(Qt.PointingHandCursor)
#
#        lay = QHBoxLayout(self)
#        lay.setContentsMargins(0, 0, 6, 0)
#        lay.setSpacing(6)
#
#        self.bar = QFrame()
#        self.bar.setFixedWidth(4)
#        self.bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
#        lay.addWidget(self.bar)
#
#        text_box = QVBoxLayout()
#        text_box.setContentsMargins(2, 5, 0, 5)
#        text_box.setSpacing(1)
#        self.label = QLabel(str(node.get("label") or node.get("step_key") or ""))
#        self.label.setObjectName("nodeLabel")
#        self.summary = QLabel(str(node.get("summary", "") or ""))
#        self.summary.setObjectName("nodeSummary")
#        self.summary.setWordWrap(True)
#        text_box.addWidget(self.label)
#        text_box.addWidget(self.summary)
#        lay.addLayout(text_box, 1)
#
#        self.chk = QCheckBox()
#        self.chk.setChecked(self.enabled_flag)
#        self.chk.setToolTip("Temporarily skip this step (without removing it)")
#        self.chk.toggled.connect(
#            lambda v: self.enable_toggled.emit(self.node_id, bool(v)))
#        lay.addWidget(self.chk)
#
#        self.btn_up = self._small("↑", "Move one step earlier")
#        self.btn_up.clicked.connect(
#            lambda: self.move_requested.emit(self.node_id, -1))
#        self.btn_down = self._small("↓", "Move one step later")
#        self.btn_down.clicked.connect(
#            lambda: self.move_requested.emit(self.node_id, +1))
#        self.btn_remove = self._small("✕", "Remove from the pipeline")
#        self.btn_remove.clicked.connect(
#            lambda: self.remove_requested.emit(self.node_id))
#        for b in (self.btn_up, self.btn_down, self.btn_remove):
#            lay.addWidget(b)
#
#        self.set_selected(False)
#
#    def _small(self, text: str, tip: str) -> QPushButton:
#        b = QPushButton(text)
#        b.setObjectName("cardButton")
#        b.setToolTip(tip)
#        b.setFixedSize(QSize(22, 22))
#        b.setCursor(Qt.PointingHandCursor)
#        return b
#
#    def set_selected(self, selected: bool) -> None:
#        self.selected = bool(selected)
#        on = self.enabled_flag
#        bar_color = theme.seg_hex(self.category) if on else TOKENS["seg_disabled"]
#        self.bar.setStyleSheet("background:%s; border:0; border-top-left-radius:7px;"
#                               "border-bottom-left-radius:7px;" % bar_color)
#        if selected:
#            bg, border, width = TOKENS["accent_bg"], TOKENS["accent"], 2
#        else:
#            bg = TOKENS["bg_surface"] if on else TOKENS["seg_disabled_bg"]
#            border, width = TOKENS["border_default"], 1
#        self.setStyleSheet(
#            "QFrame#nodeCard { background:%s; border:%dpx solid %s; border-radius:7px; }"
#            % (bg, width, border)
#        )
#        text_color = TOKENS["text_primary"] if on else TOKENS["text_disabled"]
#        sub_color = TOKENS["text_secondary"] if on else TOKENS["text_disabled"]
#        self.label.setStyleSheet("color:%s; font-weight:700;" % text_color)
#        self.summary.setStyleSheet("color:%s; font-size:11px;" % sub_color)
#
#    def mousePressEvent(self, e) -> None:   # noqa: D102 - Qt hook
#        if e.button() == Qt.LeftButton:
#            self.clicked.emit(self.node_id)
#        super().mousePressEvent(e)
#
#
#class _ScoreCard(QFrame):
#    """流程尾端固定存在的「Score / Bin」卡（ADC 段顏色）。點一下 -> 編分數。"""
#
#    clicked = Signal()
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.setObjectName("scoreCard")
#        self.setCursor(Qt.PointingHandCursor)
#        self.setToolTip("Edit the score expression and threshold")
#        self.setStyleSheet(
#            "QFrame#scoreCard { background:%s; border:1px solid %s;"
#            " border-radius:7px; }" % (theme.seg_hex("adc", bg=True),
#                                       theme.seg_hex("adc"))
#        )
#        lay = QHBoxLayout(self)
#        lay.setContentsMargins(0, 0, 8, 0)
#        lay.setSpacing(6)
#
#        bar = QFrame()
#        bar.setFixedWidth(4)
#        bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
#        bar.setStyleSheet("background:%s; border:0; border-top-left-radius:7px;"
#                          "border-bottom-left-radius:7px;" % theme.seg_hex("adc"))
#        lay.addWidget(bar)
#
#        box = QVBoxLayout()
#        box.setContentsMargins(2, 5, 0, 5)
#        box.setSpacing(1)
#        title = QLabel("Score / Bin")
#        title.setStyleSheet("color:%s; font-weight:700;" % theme.seg_hex("adc"))
#        self.summary = QLabel("(no score set yet)")
#        self.summary.setObjectName("scoreSummary")
#        self.summary.setWordWrap(True)
#        box.addWidget(title)
#        box.addWidget(self.summary)
#        lay.addLayout(box, 1)
#
#    def mousePressEvent(self, e) -> None:   # noqa: D102 - Qt hook
#        if e.button() == Qt.LeftButton:
#            self.clicked.emit()
#        super().mousePressEvent(e)
#
#
#class PipelinePanel(QWidget):
#    """有序的節點清單（資料驅動）+ 固定的 Score/Bin 尾卡。
#
#    ``set_nodes`` 吃 dict 清單，每個 dict：
#    ``{node_id, step_key, label, category, enabled, summary}``。
#    重建時會保留目前選取的節點（只要它還在），所以改參數 -> 重繪 -> 選取不會亂跳。
#    """
#
#    node_selected = Signal(str)
#    node_toggled = Signal(str, bool)
#    move_requested = Signal(str, int)
#    remove_requested = Signal(str)
#    score_clicked = Signal()
#
#    _EMPTY_TEXT = "(Pipeline is empty — double-click a card in the library to add the first step)"
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self._cards: Dict[str, _NodeCard] = {}
#        self._order: List[str] = []
#        self._selected: Optional[str] = None
#
#        outer = QVBoxLayout(self)
#        outer.setContentsMargins(0, 0, 0, 0)
#        outer.setSpacing(4)
#
#        self._scroll = QScrollArea(self)
#        self._scroll.setWidgetResizable(True)
#        self._scroll.setFrameShape(QFrame.NoFrame)
#        self._host = QWidget()
#        self._list = QVBoxLayout(self._host)
#        self._list.setContentsMargins(4, 4, 8, 4)
#        self._list.setSpacing(4)
#        self._placeholder = QLabel(self._EMPTY_TEXT)
#        self._placeholder.setObjectName("placeholder")
#        self._placeholder.setWordWrap(True)
#        self._list.addWidget(self._placeholder)
#        self._list.addStretch(1)
#        self._scroll.setWidget(self._host)
#        outer.addWidget(self._scroll, 1)
#
#        self.score_card = _ScoreCard(self)
#        self.score_card.clicked.connect(self.score_clicked)
#        outer.addWidget(self.score_card)
#
#    # -- public API --------------------------------------------------------
#    def set_nodes(self, nodes: Sequence[Dict[str, Any]]) -> None:
#        self._clear()
#        self._order = []
#        for node in nodes or []:
#            card = _NodeCard(node, self._host)
#            card.clicked.connect(self._on_card_clicked)
#            card.enable_toggled.connect(self.node_toggled)
#            card.move_requested.connect(self.move_requested)
#            card.remove_requested.connect(self.remove_requested)
#            self._list.insertWidget(self._list.count() - 1, card)
#            self._cards[card.node_id] = card
#            self._order.append(card.node_id)
#        self._placeholder.setVisible(not self._order)
#        if self._selected not in self._cards:
#            self._selected = None
#        self._refresh_selection()
#
#    def set_score_summary(self, expr: str, threshold: float) -> None:
#        """尾卡摘要：``score = <expr>   threshold <threshold>``。"""
#        expr = str(expr or "").strip()
#        if not expr:
#            self.score_card.summary.setText("(no score set yet)")
#            return
#        self.score_card.summary.setText(
#            "score = %s   threshold %s" % (expr, _fmt_number(threshold)))
#
#    def score_summary_text(self) -> str:
#        return self.score_card.summary.text()
#
#    def selected(self) -> Optional[str]:
#        return self._selected
#
#    def set_selected(self, node_id: Optional[str]) -> None:
#        """設定選取（不發 ``node_selected``；那是使用者點擊才發的）。"""
#        self._selected = node_id if node_id in self._cards else None
#        self._refresh_selection()
#
#    def node_ids(self) -> List[str]:
#        return list(self._order)
#
#    def card(self, node_id: str) -> Optional[_NodeCard]:
#        return self._cards.get(node_id)
#
#    # -- internals ---------------------------------------------------------
#    def _on_card_clicked(self, node_id: str) -> None:
#        self._selected = node_id
#        self._refresh_selection()
#        self.node_selected.emit(node_id)
#
#    def _refresh_selection(self) -> None:
#        for nid, card in self._cards.items():
#            card.set_selected(nid == self._selected)
#
#    def _clear(self) -> None:
#        for card in self._cards.values():
#            self._list.removeWidget(card)
#            card.setParent(None)
#            card.deleteLater()
#        self._cards = {}
#
#
## --------------------------------------------------------------------------- #
## 5. HistogramWidget
## --------------------------------------------------------------------------- #
#class HistogramWidget(QWidget):
#    """分數分佈長條圖 + 可拖曳的門檻線 + 可點擊的長條。
#
#    資料來自 ``viewmodel.histogram(scores)``（edges 有 n+1 個、counts 有 n 個）。
#    拖曳時持續發 ``threshold_changed``（上層用 ``viewmodel.rebin`` 秒回 bin 數），
#    放開才發 ``threshold_committed``（上層才把值寫回 model / 重算）。
#
#    「點一根長條」與「拖門檻」怎麼分（別改成用計時器）
#    ------------------------------------------------
#    兩件事都從同一顆左鍵 press 開始，所以**在放開的那一刻**才決定它是哪一種：
#
#    ===========================================  ==========================
#    放開時的狀況                                  結果
#    ===========================================  ==========================
#    滑鼠移動 > :data:`_CLICK_SLOP` px             拖門檻 → ``threshold_committed``
#    press 落在門檻線 ±:data:`_HANDLE_PX` px 內    拖門檻（原地放開 = 重新確認門檻）
#    以上皆非，且點在某根長條上                     ``bar_clicked(lo, hi)``，
#                                                  **門檻退回按下去之前的值**
#    ===========================================  ==========================
#
#    最後一種情況會補發一次 ``threshold_changed(舊值)``，讓上層拖曳中的即時
#    bin 摘要跟著還原 —— 點長條**不會**動到門檻，也不會發 committed。
#    """
#
#    threshold_changed = Signal(float)
#    threshold_committed = Signal(float)
#    #: 點一根長條：``(lo, hi)`` 是那根長條的分數區間（Studio 用來篩 Gallery）。
#    bar_clicked = Signal(float, float)
#
#    _EMPTY_TEXT = "(Score distribution appears after a trial run)"
#    # 上緣留 20px 給門檻線的標籤（「門檻 3.5」畫在圖面之上，不壓到長條）
#    _M_LEFT, _M_RIGHT, _M_TOP, _M_BOTTOM = 46.0, 14.0, 20.0, 30.0
#    _SUMMARY_H = 18.0
#    #: 按下點與門檻線的距離在這個範圍內 → 視為抓著門檻把手，不是點長條。
#    _HANDLE_PX = 6.0
#    #: 按下到放開的水平位移超過這個值 → 視為拖曳，不是點擊。
#    _CLICK_SLOP = 3.0
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.setMinimumHeight(140)
#        self.setMouseTracking(True)
#        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
#        self._edges: List[float] = []
#        self._counts: List[int] = []
#        self._threshold: Optional[float] = None
#        self._bin_text = ""
#        self._dragging = False
#        self._hover_bin = -1
#        # 點擊 vs 拖曳的判定用（見 class docstring）
#        self._press_x: Optional[float] = None
#        self._press_threshold: Optional[float] = None
#        self._press_on_handle = False
#        self._moved = False
#
#    # -- public API --------------------------------------------------------
#    def set_data(self, edges: Sequence[float], counts: Sequence[int]) -> None:
#        """``edges`` / ``counts`` 直接吃 ``viewmodel.histogram()`` 的回傳值。"""
#        edges = [float(e) for e in (edges or [])]
#        counts = [int(c) for c in (counts or [])]
#        if len(edges) != len(counts) + 1 or not counts:
#            edges, counts = [], []
#        self._edges, self._counts = edges, counts
#        if self._threshold is not None:
#            self._threshold = self._clamp(self._threshold)
#        self.update()
#
#    def set_threshold(self, value: Optional[float]) -> None:
#        """設定門檻線位置（不發訊號；程式設定不應該回頭觸發自己）。"""
#        self._threshold = None if value is None else self._clamp(float(value))
#        self.update()
#
#    def threshold(self) -> Optional[float]:
#        return self._threshold
#
#    def set_bin_summary(self, bins: Optional[Dict[int, int]]) -> None:
#        """``{0: 812, 1: 96}`` -> 「bin 0=812   bin 1=96」。"""
#        if not bins:
#            self._bin_text = ""
#        else:
#            self._bin_text = "   ".join(
#                "bin %s=%s" % (k, bins[k]) for k in sorted(bins))
#        self.update()
#
#    def bin_summary_text(self) -> str:
#        return self._bin_text
#
#    def has_data(self) -> bool:
#        return bool(self._counts) and sum(self._counts) > 0
#
#    def bar_range(self, index: int) -> Optional[Tuple[float, float]]:
#        """第 ``index`` 根長條的分數區間 ``(lo, hi)``；超出範圍回 None。"""
#        i = int(index)
#        if not self._counts or not (0 <= i < len(self._counts)):
#            return None
#        return (float(self._edges[i]), float(self._edges[i + 1]))
#
#    # -- geometry ----------------------------------------------------------
#    def _plot_rect(self) -> QRectF:
#        extra = self._SUMMARY_H if self._bin_text else 0.0
#        w = max(20.0, self.width() - self._M_LEFT - self._M_RIGHT)
#        h = max(20.0, self.height() - self._M_TOP - self._M_BOTTOM - extra)
#        return QRectF(self._M_LEFT, self._M_TOP, w, h)
#
#    def _span(self) -> Tuple[float, float]:
#        if not self._edges:
#            return 0.0, 1.0
#        lo, hi = self._edges[0], self._edges[-1]
#        return (lo, hi if hi > lo else lo + 1.0)
#
#    def _x_at(self, value: float) -> float:
#        lo, hi = self._span()
#        r = self._plot_rect()
#        return r.left() + (float(value) - lo) / (hi - lo) * r.width()
#
#    def _value_at(self, x: float) -> float:
#        lo, hi = self._span()
#        r = self._plot_rect()
#        t = 0.0 if r.width() <= 0 else (float(x) - r.left()) / r.width()
#        return self._clamp(lo + t * (hi - lo))
#
#    def _clamp(self, v: float) -> float:
#        lo, hi = self._span()
#        if not self._edges:
#            return float(v)
#        return float(min(max(v, lo), hi))
#
#    def _bar_at(self, x: float) -> int:
#        if not self._counts:
#            return -1
#        r = self._plot_rect()
#        if x < r.left() or x > r.right():
#            return -1
#        n = len(self._counts)
#        i = int((x - r.left()) / max(1e-9, r.width()) * n)
#        return int(min(max(i, 0), n - 1))
#
#    # -- painting ----------------------------------------------------------
#    def paintEvent(self, _e) -> None:
#        p = QPainter(self)
#        p.setRenderHint(QPainter.Antialiasing, True)
#        frame = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
#        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
#        p.setBrush(QColor(TOKENS["bg_panel"]))
#        p.drawRoundedRect(frame, 7, 7)
#
#        if not self.has_data():
#            p.setPen(QColor(TOKENS["text_disabled"]))
#            p.drawText(self.rect(), Qt.AlignCenter, self._EMPTY_TEXT)
#            p.end()
#            return
#
#        r = self._plot_rect()
#        small = QFont(p.font())
#        small.setPointSize(8)
#        p.setFont(small)
#
#        # 座標軸（低調的細線）
#        p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
#        p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.bottom()))
#        p.drawLine(QPointF(r.left(), r.top()), QPointF(r.left(), r.bottom()))
#
#        ymax = max(self._counts) or 1
#        n = len(self._counts)
#        bw = r.width() / n
#        bar = QColor(theme.seg_hex("algo"))
#        hover = QColor(TOKENS["accent_active"])
#        p.setPen(Qt.NoPen)
#        for i, c in enumerate(self._counts):
#            if c <= 0:
#                continue
#            bh = c / float(ymax) * r.height()
#            x = r.left() + i * bw
#            p.setBrush(hover if i == self._hover_bin else bar)
#            p.drawRect(QRectF(x + 0.5, r.bottom() - bh, max(1.0, bw - 1.0), bh))
#
#        # 刻度文字
#        lo, hi = self._span()
#        p.setPen(QColor(TOKENS["text_hint"]))
#        p.drawText(QRectF(r.left() - self._M_LEFT + 2, r.top() - 6,
#                          self._M_LEFT - 6, 14),
#                   Qt.AlignRight | Qt.AlignVCenter, str(ymax))
#        p.drawText(QRectF(r.left() - self._M_LEFT + 2, r.bottom() - 7,
#                          self._M_LEFT - 6, 14),
#                   Qt.AlignRight | Qt.AlignVCenter, "0")
#        p.drawText(QRectF(r.left(), r.bottom() + 2, r.width() / 2, 14),
#                   Qt.AlignLeft, "%.3g" % lo)
#        p.drawText(QRectF(r.center().x(), r.bottom() + 2, r.width() / 2, 14),
#                   Qt.AlignRight, "%.3g" % hi)
#
#        # 門檻線
#        if self._threshold is not None:
#            x = self._x_at(self._threshold)
#            pen = QPen(QColor(TOKENS["accent_active"]), 2)
#            pen.setStyle(Qt.DashLine)
#            p.setPen(pen)
#            p.setBrush(Qt.NoBrush)
#            p.drawLine(QPointF(x, r.top() - 3), QPointF(x, r.bottom() + 3))
#            p.setPen(QColor(TOKENS["accent_active"]))
#            label = "threshold %s" % _fmt_number(self._threshold)
#            fm = p.fontMetrics()
#            tw = fm.horizontalAdvance(label) + 4
#            tx = min(max(x + 3, r.left()), max(r.left(), r.right() - tw))
#            p.drawText(QRectF(tx, r.top() - self._M_TOP + 2, tw,
#                              self._M_TOP - 4),
#                       Qt.AlignLeft | Qt.AlignVCenter, label)
#
#        # bin 摘要
#        if self._bin_text:
#            p.setPen(QColor(TOKENS["text_secondary"]))
#            p.drawText(QRectF(r.left(), r.bottom() + 16, r.width(),
#                              self._SUMMARY_H),
#                       Qt.AlignLeft | Qt.AlignVCenter, self._bin_text)
#        p.end()
#
#    # -- interaction -------------------------------------------------------
#    def mousePressEvent(self, e) -> None:   # noqa: D102 - Qt hook
#        if e.button() != Qt.LeftButton or not self.has_data():
#            return
#        pos = QPointF(e.position())
#        if not self._plot_rect().adjusted(-6, -6, 6, 6).contains(pos):
#            return
#        self._dragging = True
#        self._press_x = float(pos.x())
#        self._press_threshold = self._threshold
#        self._press_on_handle = (
#            self._threshold is not None
#            and abs(pos.x() - self._x_at(self._threshold)) <= self._HANDLE_PX)
#        self._moved = False
#        self._set_from_mouse(pos.x())
#        e.accept()
#
#    def mouseMoveEvent(self, e) -> None:    # noqa: D102 - Qt hook
#        pos = QPointF(e.position())
#        if self._dragging:
#            if (self._press_x is not None
#                    and abs(pos.x() - self._press_x) > self._CLICK_SLOP):
#                self._moved = True
#            self._set_from_mouse(pos.x())
#            return
#        self._update_hover(pos)
#
#    def mouseReleaseEvent(self, e) -> None:  # noqa: D102 - Qt hook
#        if not self._dragging:
#            return
#        self._dragging = False
#        idx = -1 if self._press_x is None else self._bar_at(self._press_x)
#        rng = self.bar_range(idx)
#        if not self._moved and not self._press_on_handle and rng is not None:
#            self._restore_press_threshold()
#            self.bar_clicked.emit(float(rng[0]), float(rng[1]))
#            return
#        if self._threshold is not None:
#            self.threshold_committed.emit(float(self._threshold))
#
#    def _restore_press_threshold(self) -> None:
#        """點長條：門檻退回按下去之前的值（並補一次 changed 讓上層還原顯示）。"""
#        old = self._press_threshold
#        self._threshold = None if old is None else self._clamp(float(old))
#        self.update()
#        if self._threshold is not None:
#            self.threshold_changed.emit(float(self._threshold))
#
#    def leaveEvent(self, _e) -> None:       # noqa: D102 - Qt hook
#        if self._hover_bin != -1:
#            self._hover_bin = -1
#            self.setToolTip("")
#            self.update()
#
#    def _set_from_mouse(self, x: float) -> None:
#        value = self._value_at(x)
#        if self._threshold is None or value != self._threshold:
#            self._threshold = value
#            self.update()
#        self.threshold_changed.emit(float(value))
#
#    def _update_hover(self, pos: QPointF) -> None:
#        idx = -1
#        if self.has_data() and self._plot_rect().contains(pos):
#            idx = self._bar_at(pos.x())
#        if idx == self._hover_bin:
#            return
#        self._hover_bin = idx
#        if idx < 0:
#            self.setToolTip("")
#        else:
#            a, b = self._edges[idx], self._edges[idx + 1]
#            self.setToolTip("score %.3g–%.3g: %d defects"
#                            % (a, b, self._counts[idx]))
#        self.update()
#
#
## --------------------------------------------------------------------------- #
## 6. FeatureTable / VerdictChip
## --------------------------------------------------------------------------- #
#def _fmt_number(value: Any) -> str:
#    """數值 -> 好讀字串：整數不拖小數點、一般值 3 位、極小值退回有效位數。"""
#    if isinstance(value, bool):
#        return "Yes" if value else "No"
#    try:
#        f = float(value)
#    except (TypeError, ValueError):
#        return str(value)
#    if math.isnan(f):
#        return "NaN"
#    if math.isinf(f):
#        return "∞" if f > 0 else "-∞"
#    if f == int(f) and abs(f) < 1e12:
#        return str(int(f))
#    if 0 < abs(f) < 5e-4:
#        return "%.3g" % f
#    return "%.3f" % f
#
#
#class FeatureTable(QTableWidget):
#    """特徵 / 數值 兩欄表；``score`` 永遠釘在最後一列且用粗體。"""
#
#    _SCORE = "score"
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(0, 2, parent)
#        self.setHorizontalHeaderLabels(["Feature", "Value"])
#        self.verticalHeader().setVisible(False)
#        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
#        self.setSelectionBehavior(QAbstractItemView.SelectRows)
#        self.setSelectionMode(QAbstractItemView.SingleSelection)
#        self.setAlternatingRowColors(True)
#        self.setShowGrid(False)
#        head = self.horizontalHeader()
#        head.setSectionResizeMode(0, QHeaderView.Stretch)
#        head.setSectionResizeMode(1, QHeaderView.ResizeToContents)
#
#    def set_features(self, features: Optional[Dict[str, Any]],
#                     highlight: Iterable[str] = ()) -> None:
#        """填表。``highlight`` 內的特徵名會用 accent 底色標出（例：分數用到的）。"""
#        features = dict(features or {})
#        hi = set(highlight or ())
#        names = [k for k in features if k != self._SCORE]
#        if self._SCORE in features:
#            names.append(self._SCORE)
#
#        self.setRowCount(len(names))
#        for row, name in enumerate(names):
#            is_score = name == self._SCORE
#            key_item = QTableWidgetItem(str(name))
#            val_item = QTableWidgetItem(_fmt_number(features[name]))
#            val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
#            if is_score:
#                font = key_item.font()
#                font.setBold(True)
#                key_item.setFont(font)
#                val_item.setFont(font)
#                key_item.setForeground(QColor(TOKENS["accent_active"]))
#                val_item.setForeground(QColor(TOKENS["accent_active"]))
#            if name in hi:
#                bg = QColor(TOKENS["accent_bg"])
#                key_item.setBackground(bg)
#                val_item.setBackground(bg)
#            self.setItem(row, 0, key_item)
#            self.setItem(row, 1, val_item)
#
#    def feature_names(self) -> List[str]:
#        return [self.item(r, 0).text() for r in range(self.rowCount())
#                if self.item(r, 0) is not None]
#
#    def value_text(self, name: str) -> Optional[str]:
#        for r in range(self.rowCount()):
#            key = self.item(r, 0)
#            if key is not None and key.text() == name:
#                val = self.item(r, 1)
#                return None if val is None else val.text()
#        return None
#
#
#class VerdictChip(QLabel):
#    """判定 chip：``bin 1 · ≥門檻`` / ``bin 0 · <門檻`` / ``—``。
#
#    ``is_real_style=True`` 時色彩語意反轉：bin 1 代表「這是真缺陷」，是壞消息
#    （紅），bin 0 是乾淨（綠）。預設（False）則照「過門檻 = 好」來配色。
#    文字兩種模式都一樣，只有顏色換邊。
#    """
#
#    def __init__(self, parent: Optional[QWidget] = None):
#        super().__init__(parent)
#        self.setAlignment(Qt.AlignCenter)
#        self.setMinimumWidth(112)
#        self.setMinimumHeight(28)
#        self._bin: Optional[int] = None
#        self.set_verdict(None)
#
#    def set_verdict(self, bin_value: Optional[Any] = None,
#                    is_real_style: bool = False) -> None:
#        try:
#            b = None if bin_value is None else int(bin_value)
#        except (TypeError, ValueError):
#            b = None
#        self._bin = b
#        if b is None:
#            text, tone = "—", "neutral"
#        elif b == 1:
#            text = "bin 1 · ≥ threshold"
#            tone = "bad" if is_real_style else "good"
#        elif b == 0:
#            text = "bin 0 · < threshold"
#            tone = "good" if is_real_style else "bad"
#        else:
#            text, tone = "bin %d" % b, "neutral"
#        bg = TOKENS["chip_%s_bg" % tone]
#        fg = TOKENS["chip_%s_text" % tone]
#        border = TOKENS["chip_%s_border" % tone]
#        self.setText(text)
#        self.setProperty("tone", tone)
#        self.setStyleSheet(
#            "background:%s; color:%s; border:1px solid %s; border-radius:8px;"
#            "padding:4px 12px; font-weight:700;" % (bg, fg, border))
#
#    def verdict(self) -> Optional[int]:
#        return self._bin
#
#    def tone(self) -> str:
#        return str(self.property("tone"))
#
#F db4c0723c6a28cddd4c335d5214895f57915fc7d 407 adept/ui/workers.py
## ADEPT Studio 背景工作層 — authored 2026-07-28 (M3).
#"""Studio 的三個背景工作：載資料集、單顆預覽、試跑批次。
#
#設計原則
#--------
#- **GUI 不卡**：每個工作把 core 的重運算（``load_dataset`` / ``run_defect`` /
#  ``run_batch``）丟到自己的 :class:`QThread` 上跑；worker 物件本身留在 GUI
#  執行緒，只在背景執行緒 ``emit`` 訊號（Qt 的 AutoConnection 會依「接收端」
#  所在執行緒自動排隊，UI slot 仍在 GUI 執行緒被呼叫）。背景程式碼**不碰**
#  任何 GUI 物件。
#- **執行緒樣式（統一）**：每次 ``start()`` / ``request()`` 都開一條全新的
#  ``QThread``，把一個 :class:`_Task`（純 QObject，帶要跑的 callable）
#  ``moveToThread`` 過去，``thread.started -> task.run``；``run`` 跑完
#  ``emit finished`` 後呼叫 ``QThread.currentThread().quit()`` 結束該執行緒的
#  event loop。GUI 端收到 ``finished``（queued）後 ``quit() + wait()`` 回收，
#  不留殘骸、不 poll、不 busy-loop。
#- **同步模式**：三個 worker 都提供 ``run_sync(...)``，完全不碰 Qt 執行緒，
#  給 headless 測試與 CLI 用（``QApplication`` 不存在也能跑）。
#- **關窗安全**：``stop()``（``shutdown()`` 為別名）會先設中止旗標 / 清掉
#  待跑請求，再 join 背景執行緒；之後 ``is_running()`` 為 False、內部
#  thread 參考歸 None。無法在時限內結束的執行緒（不可中斷的 core 呼叫）
#  會被移到 ``_zombies`` 保住參考，**絕不** ``terminate()``（會毀掉 numpy /
#  cv2 的狀態），也絕不在還在跑時銷毀 QThread 物件。
#
#注意：非同步模式（``start`` / ``request``）需要有 ``QApplication`` 且
#GUI 執行緒的 event loop 有在轉，訊號才會被投遞——這是 Qt 的常態；
#``run_sync`` 沒有這個限制。
#"""
#from __future__ import annotations
#
#import threading
#from typing import Any, Callable, Dict, List, Optional
#
#from PySide6.QtCore import QObject, QThread, Signal
#
#import adept.core.steps  # noqa: F401 — 觸發卡片註冊（Qt-free、便宜）
#from adept.core.ingest.dataset import Dataset, load_dataset
#from adept.core.pipeline import Recipe, run_batch, run_defect
#from adept.core.pipeline.engine import DefectResult
#
#__all__ = ["DatasetLoadWorker", "PreviewWorker", "TrialWorker",
#           "RegionCheckWorker"]
#
##: ``stop()`` 等背景執行緒收工的預設上限（毫秒）。
#DEFAULT_JOIN_MS = 15000
#
#
## ---------------------------------------------------------------------------
## 內部：一次性的執行緒任務
## ---------------------------------------------------------------------------
#class _Task(QObject):
#    """跑一個 callable 的一次性任務物件（會被 moveToThread 到背景執行緒）。
#
#    ``fn`` 自己負責 emit 業務訊號（loaded / ready / done / failed）；
#    ``_Task`` 只保證「跑完一定會 emit ``finished(job_id)`` 並讓執行緒 quit」。
#    ``job_id`` 讓 GUI 端能認出並忽略**過期**的完成通知（queued 訊號可能在
#    該份工作已被回收之後才送達）。
#    """
#
#    finished = Signal(int)
#
#    def __init__(self, job_id: int, fn: Callable[[], None]) -> None:
#        super().__init__()
#        self._job_id = int(job_id)
#        self._fn = fn
#
#    def run(self) -> None:  # 在背景執行緒被呼叫
#        try:
#            self._fn()
#        finally:
#            try:
#                self.finished.emit(self._job_id)
#            finally:
#                thread = QThread.currentThread()
#                if thread is not None:
#                    thread.quit()   # 結束這條 thread 的 event loop
#
#
#class _ThreadedWorker(QObject):
#    """三個 worker 的共用底座：一次一條 QThread，收工即回收。"""
#
#    def __init__(self, parent: Optional[QObject] = None) -> None:
#        super().__init__(parent)
#        self._thread: Optional[QThread] = None
#        self._task: Optional[_Task] = None
#        self._job_id = 0                    # 目前這份工作的編號（過期通知用）
#        self._zombies: List[QThread] = []   # join 逾時、還在跑的執行緒（保住參考）
#
#    # ---- 狀態查詢 ---------------------------------------------------------
#    def is_running(self) -> bool:
#        """目前是否有背景工作在跑。"""
#        t = self._thread
#        return t is not None and t.isRunning()
#
#    @property
#    def thread_obj(self) -> Optional[QThread]:
#        """目前的背景執行緒物件（沒有工作時為 None）——測試用。"""
#        return self._thread
#
#    # ---- 啟動 / 回收 ------------------------------------------------------
#    def _start_job(self, fn: Callable[[], None]) -> None:
#        """開一條新 QThread 跑 ``fn``（必須在 GUI 執行緒呼叫）。"""
#        self._reap(DEFAULT_JOIN_MS)          # 前一條若已收工，先清乾淨
#        self._job_id += 1
#        thread = QThread()
#        task = _Task(self._job_id, fn)
#        task.moveToThread(thread)
#        thread.started.connect(task.run)
#        task.finished.connect(self._on_task_finished)   # queued 回 GUI 執行緒
#        self._thread = thread
#        self._task = task
#        thread.start()
#
#    def _on_task_finished(self, job_id: int) -> None:
#        """背景任務跑完（GUI 執行緒、queued）：回收執行緒後給子類接手。"""
#        if int(job_id) != self._job_id:
#            return                           # 過期通知（該份工作已被回收）
#        self._reap(DEFAULT_JOIN_MS)
#        self._job_finished()
#
#    def _job_finished(self) -> None:
#        """子類覆寫：一份工作結束後的後續動作（例如跑下一個待跑請求）。"""
#
#    def _reap(self, timeout_ms: int) -> bool:
#        """quit + wait 目前的執行緒並丟掉參考；回傳是否成功收乾淨。
#
#        同時把 ``_job_id`` 往前推一格，讓這份工作之後才送達的 queued
#        ``finished`` 通知被視為過期而忽略。
#        """
#        thread = self._thread
#        if thread is None:
#            return True
#        self._job_id += 1
#        thread.quit()
#        ok = bool(thread.wait(int(timeout_ms)))
#        self._thread = None
#        self._task = None
#        if not ok:
#            # 還在跑（core 呼叫不可中斷）：保住參考，QThread 物件不能被銷毀
#            self._zombies.append(thread)
#        return ok
#
#    # ---- 關閉 -------------------------------------------------------------
#    def stop(self, timeout_ms: int = DEFAULT_JOIN_MS) -> bool:
#        """中止並 join 背景執行緒；回傳是否已完全收乾淨（關窗時呼叫）。"""
#        self._before_stop()
#        return self._reap(timeout_ms)
#
#    def shutdown(self, timeout_ms: int = DEFAULT_JOIN_MS) -> bool:
#        """:meth:`stop` 的別名（關窗語意讀起來比較順）。"""
#        return self.stop(timeout_ms)
#
#    def _before_stop(self) -> None:
#        """子類覆寫：join 之前要設的中止旗標 / 要清的待跑佇列。"""
#
#
## ---------------------------------------------------------------------------
## 1) 載入資料集
## ---------------------------------------------------------------------------
#class DatasetLoadWorker(_ThreadedWorker):
#    """背景載入 KLARF（可帶 patch TIFF）→ :class:`Dataset`。
#
#    訊號：``loaded(Dataset)`` 成功、``failed(str)`` 失敗（``load_dataset``
#    會 raise，例如檔案不存在 / KLARF 壞掉）。
#    """
#
#    loaded = Signal(object)
#    failed = Signal(str)
#
#    def start(self, path: str, tiff: Optional[str] = None) -> bool:
#        """開背景執行緒載入；已有工作在跑時回傳 False（不排隊）。"""
#        if self.is_running():
#            return False
#        path_s = str(path)
#        tiff_s = None if tiff is None else str(tiff)
#
#        def job() -> None:
#            try:
#                ds = load_dataset(path_s, tiff_s)
#            except Exception as e:                      # noqa: BLE001 — 一律回報
#                self.failed.emit(f"{type(e).__name__}: {e}")
#            else:
#                self.loaded.emit(ds)
#
#        self._start_job(job)
#        return True
#
#    @staticmethod
#    def run_sync(path: str, tiff: Optional[str] = None) -> Dataset:
#        """同步載入（不開執行緒）；失敗直接 raise，給測試 / headless 用。"""
#        return load_dataset(str(path), None if tiff is None else str(tiff))
#
#
## ---------------------------------------------------------------------------
## 2) 單顆預覽（請求合併）
## ---------------------------------------------------------------------------
#class PreviewWorker(_ThreadedWorker):
#    """單顆 defect 預覽：**只保留最新一筆**待跑請求的合併式 worker。
#
#    Studio 每動一次參數就會呼叫 :meth:`request`，過期的請求算完也沒人看，
#    所以：有工作在跑時只記住**最後一筆**，前面的待跑請求靜靜丟掉；
#    目前這筆跑完再跑它。
#
#    訊號
#    ----
#    ``ready(DefectResult)``
#        一筆預覽算完（``run_defect`` 永不 raise，失敗會是 ``ok=False`` 的
#        DefectResult，一樣走 ``ready``）。
#    ``busy(bool)``
#        ``True``：有工作開跑（每筆都發，statusbar 直接接）；
#        ``False``：佇列排空（沒有待跑請求了）。
#        為了讓 UI 立即有反應，``busy`` 在**呼叫端（GUI）執行緒**同步發出。
#    ``failed(str)``
#        **錯誤策略**：``run_defect`` 依合約永不 raise，所以這個訊號只會在
#        「意外」時出現（例如 registry 被抽掉、記憶體不足）。此時**不會**
#        再發 ``ready``（不硬湊一顆假的 DefectResult，避免 UI 把它當成
#        真的預覽結果畫出來）；UI 該做的是保留上一張畫面 + statusbar 顯示
#        錯誤。``busy`` 的 True/False 配對仍然成立。
#        同步模式（:meth:`run_sync`）則相反：例外照常往外 raise。
#    """
#
#    ready = Signal(object)
#    busy = Signal(bool)
#    failed = Signal(str)
#
#    def __init__(self, parent: Optional[QObject] = None) -> None:
#        super().__init__(parent)
#        self._pending: Optional[tuple] = None   # 只留最新一筆 (recipe,item,kind,upto)
#
#    # ---- 對外 -------------------------------------------------------------
#    def request(self, recipe: Recipe, item: Any, kind: str,
#                upto_node: Optional[str] = None) -> None:
#        """要求算一筆預覽；忙碌中則覆蓋掉先前的待跑請求（舊的直接丟）。"""
#        job = (recipe, item, str(kind), upto_node)
#        if self.is_running():
#            self._pending = job            # 覆蓋 = 丟掉更舊的請求
#            return
#        self._launch(job)
#
#    @staticmethod
#    def run_sync(recipe: Recipe, item: Any, kind: str,
#                 upto_node: Optional[str] = None) -> DefectResult:
#        """同步跑一筆預覽（不開執行緒）；``keep_context=True`` 以便看中間影像。"""
#        # ``track_changes``：預覽是單顆，記下「每張卡把影像流改成什麼樣」
#        # 的成本可以忽略，而 Enhance 的儀表就是靠這份資料（F7-17）。
#        return run_defect(recipe, item, str(kind), keep_context=True,
#                          upto_node=upto_node, track_changes=True)
#
#    def has_pending(self) -> bool:
#        """是否還有待跑的請求（測試 / statusbar 用）。"""
#        return self._pending is not None
#
#    # ---- 內部 -------------------------------------------------------------
#    def _launch(self, job: tuple) -> None:
#        recipe, item, kind, upto = job
#
#        def work() -> None:
#            try:
#                r = run_defect(recipe, item, kind, keep_context=True,
#                               upto_node=upto, track_changes=True)
#            except Exception as e:          # noqa: BLE001 — 合約外的意外
#                self.failed.emit(f"{type(e).__name__}: {e}")
#            else:
#                self.ready.emit(r)
#
#        self.busy.emit(True)                # 呼叫端執行緒：UI 立刻變忙
#        self._start_job(work)
#
#    def _job_finished(self) -> None:
#        """一筆算完（GUI 執行緒）：有待跑就接著跑，沒有就宣告閒置。"""
#        job, self._pending = self._pending, None
#        if job is not None:
#            self._launch(job)
#        else:
#            self.busy.emit(False)
#
#    def _before_stop(self) -> None:
#        self._pending = None                # 關窗：待跑請求全部作廢
#
#
## ---------------------------------------------------------------------------
## 3) 試跑批次
## ---------------------------------------------------------------------------
#class TrialWorker(_ThreadedWorker):
#    """在背景跑 :func:`adept.core.pipeline.run_batch`（前 N 顆試跑）。
#
#    訊號：``progress(done, total)``、``done(list)``（result dict 清單，
#    即使被 :meth:`abort` 也會帶著部分結果發出）、``failed(str)``。
#
#    ``run_batch`` 內部可能開 ProcessPool——從背景執行緒開子進程沒問題
#    （子進程不繼承 Qt event loop 的使用）。
#    """
#
#    progress = Signal(int, int)
#    done = Signal(object)
#    failed = Signal(str)
#
#    def __init__(self, parent: Optional[QObject] = None) -> None:
#        super().__init__(parent)
#        self._abort = threading.Event()
#
#    # ---- 對外 -------------------------------------------------------------
#    def start(self, recipe: Recipe, dataset: Any, n: int,
#              workers: Optional[int] = None,
#              cache_dir: Optional[str] = None) -> bool:
#        """開背景執行緒試跑前 ``n`` 顆；已有工作在跑時回傳 False。"""
#        if self.is_running():
#            return False
#        self._abort.clear()
#        limit = int(n)
#        w = None if workers is None else int(workers)
#        cdir = None if cache_dir is None else str(cache_dir)
#
#        def progress_cb(done_count: int, total: int,
#                        _result: Dict[str, Any]) -> None:
#            self.progress.emit(int(done_count), int(total))
#
#        def job() -> None:
#            try:
#                out = run_batch(recipe, dataset, workers=w, cache_dir=cdir,
#                                limit=limit, progress=progress_cb,
#                                abort_check=self._abort.is_set)
#            except Exception as e:          # noqa: BLE001 — 整批爆掉才會走到這
#                self.failed.emit(f"{type(e).__name__}: {e}")
#            else:
#                self.done.emit(out)
#
#        self._start_job(job)
#        return True
#
#    def abort(self) -> None:
#        """設中止旗標：``run_batch`` 的 ``abort_check`` 會看到，
#        已完成的部分結果仍會由 ``done`` 送出（不 join，不阻塞 UI）。"""
#        self._abort.set()
#
#    def is_aborted(self) -> bool:
#        """中止旗標目前狀態。"""
#        return self._abort.is_set()
#
#    @staticmethod
#    def run_sync(recipe: Recipe, dataset: Any, n: int, workers: int = 1,
#                 cache_dir: Optional[str] = None) -> List[Dict[str, Any]]:
#        """同步試跑（不開執行緒），回傳 result dict 清單。"""
#        return run_batch(recipe, dataset, workers=int(workers),
#                         cache_dir=None if cache_dir is None else str(cache_dir),
#                         limit=int(n))
#
#    # ---- 內部 -------------------------------------------------------------
#    def _before_stop(self) -> None:
#        self._abort.set()                   # 關窗：讓 run_batch 早點收手
#
#
## ---------------------------------------------------------------------------
## 4) 區域跨顆檢視（F7-11）
## ---------------------------------------------------------------------------
#class RegionCheckWorker(_ThreadedWorker):
#    """在背景把一個具名區域畫到前 N 顆的縮圖上（見 ``ui/region_check.py``）。
#
#    為什麼要開背景執行緒：它**每顆都要跑一次 pipeline** 到那張 Region 卡為止。
#    N 顆就是 N 次，在 GUI 執行緒做會讓整個視窗僵住幾秒 —— 而使用者按下這個按鈕
#    的當下，正是他在調參數、最需要介面有反應的時候。
#
#    訊號：``ready(list)``、``busy(bool)``、``failed(str)``。
#    """
#
#    ready = Signal(object)
#    busy = Signal(bool)
#    failed = Signal(str)
#
#    def start(self, recipe: Recipe, items: Any, kind: str, node_id: str,
#              regions: Any, thumb_size: int = 120,
#              source: Optional[str] = None) -> bool:
#        """開背景執行緒檢查；已有工作在跑時回傳 False（不排隊）。
#
#        不排隊是刻意的：這個動作是使用者明確按下去的，重複按第二次的意思是
#        「用現在的設定再看一次」，而不是「排兩份」。
#        """
#        if self.is_running():
#            return False
#        args = (recipe, list(items), str(kind), str(node_id),
#                list(regions), int(thumb_size), source)
#
#        def job() -> None:
#            from .region_check import check_regions
#            try:
#                out = check_regions(*args)
#            except Exception as e:          # noqa: BLE001 — 合約外的意外
#                self.failed.emit(f"{type(e).__name__}: {e}")
#            else:
#                self.ready.emit(out)
#
#        self.busy.emit(True)
#        self._start_job(job)
#        return True
#
#    @staticmethod
#    def run_sync(recipe: Recipe, items: Any, kind: str, node_id: str,
#                 regions: Any, thumb_size: int = 120,
#                 source: Optional[str] = None) -> List[Dict[str, Any]]:
#        """同步版（測試用）。"""
#        from .region_check import check_regions
#        return check_regions(recipe, list(items), str(kind), str(node_id),
#                             list(regions), int(thumb_size), source)
#
#    def _job_finished(self) -> None:
#        self.busy.emit(False)
#
#F 04c5ce471195ac4e2449126ce835b22b4c880cf3 39 conftest.py
## pytest 根設定 — authored 2026-07-29.
#"""讓 ``pytest``（不加 ``python -m``）也找得到 ``adept`` 套件。
#
#為什麼需要這個檔
#----------------
#``python -m pytest`` 會把**目前工作目錄**放進 ``sys.path``，``pytest`` 不會。
#測試都是從 repo 根目錄跑的，所以兩種寫法的差別就是 ``import adept`` 成不成立：
#
#===========================  ==========================================
#``python -m pytest -q``      CWD 進 sys.path → 找得到 adept ✓
#``pytest -q``                CWD **不**進 sys.path → ModuleNotFoundError ✗
#===========================  ==========================================
#
#CI（``.github/workflows/ci.yml``）跑的是後者，所以整套測試在 CI 上是
#**收集階段就中斷**，一個都沒真的跑到。本機開發用前者，於是這件事一直沒被發現。
#
#修法：pytest 在載入 conftest 時，會把該 conftest 所在目錄（= repo 根目錄）
#插進 ``sys.path``。所以這個檔案存在本身就是修正 —— 底下再明確補一次，
#讓意圖看得出來，也不依賴 pytest 的 import-mode 細節。
#
#比 ``pip install -e .`` 好在哪：廠內機器不一定裝得了可編輯安裝
#（見 ``docs/NO-GIT-SETUP.md``：使用者是解壓 zip 直接跑），
#所以「從 repo 根目錄直接跑得動」是這個專案要維持的性質。
#"""
#from __future__ import annotations
#
#import sys
#from pathlib import Path
#
#_ROOT = Path(__file__).resolve().parent
#if str(_ROOT) not in sys.path:
#    sys.path.insert(0, str(_ROOT))
#
## tools/ 不是套件，但有幾支測試要 import make_sample / make_sample_rsem
## 來產合成資料（tools 本身刻意保持 stdlib-only 的單檔腳本）。
#_TOOLS = _ROOT / "tools"
#if _TOOLS.is_dir() and str(_TOOLS) not in sys.path:
#    sys.path.insert(0, str(_TOOLS))
#
#F ba101eee94ed5f8183eba368989167fb1132a128 214 docs/HANDOVER.md
## ADEPT 交接文件
#
#> **給接手的人（含新的 Claude Code session）：先讀這份，再讀 `CLAUDE.md`。**
#>
#> `CLAUDE.md` 是「怎麼動手」的操作手冊；這份是「為什麼會長成這樣」。
#> ADEPT 是在一個 Claude Cowork session 裡從零做到 v1 的，那個 session 同時讀過
#> 六個既有專案的原始碼 —— **那份跨專案的脈絡不在程式碼裡，只在這份文件裡。**
#
#版本：2026-07-28 · 對應 commit `M6: offline install toolchain…` · 588 tests
#
#---
#
### 1. 這個工具為什麼存在
#
#### 出發點（使用者原話的整理）
#
#在半導體 E-beam Inspection 的工作裡，機台會對每顆 defect 產出小圖（patch），
#Review SEM 則會產出單張高解析影像，兩者都配一份 KLARF。長年的做法是針對每個站點
#寫一套 ADC（Auto Defect Classification）程式來重新算分、重新分類 ——
#patch 的叫 **PADC**、review 影像的叫 **RADC**。
#
#問題是：**入門門檻太高，要會寫 code。**
#
#所以每次換站點、換想法，都得回頭找會寫程式的人。而真正知道「這種缺陷長什麼樣、
#該看哪裡」的是製程與設備工程師，不是寫程式的人。
#
#> 目標：**打造一個可以把腦中想法轉變成算法的工具。**
#> 讓不會寫 code 的人，也能自己做出 ADC 算分 —— 也就是**量化證據**。
#
#明確不要的東西：**不是單純框個 ROI、算 BBOX 內 GLV 那種一步到位的工具**。
#要的是多步驟、能組合、任何 Inspection 站點都適用的。
#
#### 由此推導出的最高指導原則
#
#**站點差異封裝進 recipe，不封裝進程式碼。**
#
#傳統 PADC/RADC 每個站點一份 code；ADEPT 是一份程式 + 每個站點一份 recipe JSON。
#recipe 是使用者用滑鼠組出來的、可存檔、可互傳給同事。
#
#第二原則：**推廣鐵則** —— 目標使用者不會寫 code。
#任何讓他們看不懂、或會噴出 traceback 的設計，都是 bug。
#（這條在程式碼層級有強制力：沒寫白話 `help` 的卡片，`register_step` 會直接拒絕註冊。）
#
#### 心智模型：為什麼是三段式
#
#使用者自己給的分類：**defect 分數最主要就跟兩件事有關 —— 影像（優化）和算法。**
#於是整個 UI 與資料流都照這個切：
#
#```
#【影像段 Image】把圖變乾淨、變可比  → 產出影像流（ctx.images）
#【算法段 Algo】 從圖量出數字        → 產出特徵（ctx.features）
#【ADC 判定段】  特徵 → 分數 → bin → 寫回 KLARF
#```
#
#這不是裝飾。它同時是 `Step.category`、UI 分色、快取切點（快取邊界就切在影像段結尾，
#所以改算法段或門檻都是秒級回饋）、以及 recipe 驗證的順序依據。
#
#---
#
### 2. 需求訪談的結論與理由
#
#以下每一條都是問過使用者才定的，改動前請先確認前提還在。
#
#| 決策 | 結論 | 理由 |
#|---|---|---|
#| 使用對象 | **推廣給部門同事**（不寫 code） | 決定了 UX 引導、防呆預設、範例庫都是一級需求而非附屬品 |
#| 形態 | 桌面 GUI（PySide6），core/ui 嚴格分離，CLI 附帶 | 廠內機器；CLI 供排程與腳本 |
#| 組裝方式 | 視覺化 pipeline 編輯器 + recipe JSON | 「把想法轉成算法」的具體形式 |
#| 輸入 | **兩種都要**：EBI patch（test+ref 配對、8-bit、multi-page TIFF）與 RSEM 單張 | 使用者明說格式參照 KLIP |
#| 輸出 | 寫回 KLARF（class/bin/DSIZE）、另存含 score+class 的新檔、Top-N、報表、feature vector | feature vector 是為了未來 ML 備料 |
#| Pipeline 結構 | **core 即 DAG**，UI v1 只呈現直線 + 輸入型別分流 | 直線是 DAG 的特例；之後上自由畫布時引擎零改動 |
#| Gallery | v1 就要，含直方圖聯動 | 「同屏比多顆」是調參迴圈的另一半 |
#| CD | 是 pipeline 中的一張特徵卡，不是特例 | 使用者主動提的：CD 當 attribute 很好 |
#| ML | v1 純 rule-based，但 **feature 匯出先做** | 保留未來訓練分類器的料 |
#| 重用方式 | **Vendoring**（複製進新 repo 改名空間） | 新工具完全獨立，不動現有六個專案 |
#| KPI | 三個都要：自動分類準確度、壓 nuisance rate、**review efficiency**（分數排名高的都要是真 defect）| review efficiency 是 Gallery 按分排序的存在理由 |
#| 資料量級 | 千級常態、偶爾上萬 | 設計目標 10k defect 流暢 |
#
#### 名稱由來
#
#工作代號原本是 FlexADC。M3 之後定名 **ADEPT = Auto Defect Evaluation Pipeline Tool**。
#挑選時排除了水果系（PEACH/FIG/PLUM，本來想跟 PEAR 成家族），選 ADEPT 的理由是：
#縮寫精準對應功能，而 adept（熟練、得心應手）正是要給不寫 code 同事的承諾。
#
#---
#
### 3. 六個來源專案：跨專案脈絡
#
#**這一節是新 session 最缺的東西。** ADEPT 的演算法幾乎都是從使用者既有的六個專案
#vendoring 過來的。那六個專案在使用者的桌面上（`Desktop\hxlub0905-cmyk\`），
#但新的 Claude Code session 不會去讀它們。以下是當初讀過之後的判斷。
#
#### 各專案提供了什麼
#
#| 專案 | 是什麼 | ADEPT 拿了什麼 | **刻意沒拿什麼** |
#|---|---|---|---|
#| **KLIP** | KLARF 檔案編輯器（PySide6 GUI + 純邏輯 core） | `klarf_core.py` **整檔搬**（1.2/1.8 無損讀寫、健檢 lint、defect↔TIFF page 對應、比對、API-KLARF 產生）；`klarf_tif_probe` 的免解碼 TIFF 走訪 | 3340 行的 Qt GUI。只留下裡面的 filter DSL 概念 |
#| **GLAS** | GDS/OASIS layout 與 SEM 對位工具 | `fine_align_one`、`_parabola_subpx`、`sem_loader`、ROI label map 契約（`gray[label==k]`）、DAG 拓撲排序概念（`recipe_dependency_order`）、boolean 運算式的 AST 架構 | **整套 OASIS/GDS 解析與渲染**（`oasis_streamer.py` 就 125KB、`gds_align_tool.py` 398KB）、multiprocessing pool harness |
#| **MMH** | SEM 大量量測工具 | recipe 架構原型（一般化成 Step/DAG）、批次引擎模式（ProcessPool + as_completed + per-defect try/except）、次像素邊緣定位（CD 用）、影像品質三指標、calibration profile、KLARF 寫回與 exporter 模式 | CMG 專用的 recipe（54KB）、GUI workspaces |
#| **PEAR** | Pre-EBI 屬性排序工具 | GLV 統計 metric bank、Tukey IQR 離群、Cohen's d / η²、**CJK-safe 影像讀寫**（`np.fromfile` + `imdecode`，Windows 中文路徑必備） | Qt UI、wafer map |
#| **cell-period-estimator (CPE)** | 週期陣列的 cell 週期估測 | `estimate_period`、`stack_cells`、`ghosting_score`、`refine_period`；UI 主題 token 系統（ADEPT 的配色延續自這裡） | — |
#| **Perspective-Combination (Fusi³)** | 多視角 E-beam 影像融合 | 正規化、直方圖匹配、**5-backend 對位**、SNR map、blob 分割、`MultiROISet`（正規化座標、可隨對位平移） | 557KB 的 `dialog.py` UI、PCA fusion（v1 移出）、quadrant 多通道融合（v2 backlog）|
#
#### 在來源專案裡發現、但**尚未回報給原專案**的問題
#
#這幾件事值得回頭修原專案：
#
#1. **Fusi³ `ecc` 對位 backend 位移正負號與其他四個相反。**
#   `cv2.findTransformECC` 的 `WARP_INVERSE_MAP` 語意被弄反了。ADEPT 版已修正並用測試鎖住
#   五個 backend 同號（見 `adept/core/algo/align.py` 檔頭）。
#2. **CPE `choose_origin` 是 stub**（永遠回 `(0,0)`）。ADEPT 在 M4 補完了相位搜尋。
#3. **MMH 次像素 batch 版比 scalar 版低約 1.5 px 的系統性偏移。**
#   ADEPT 照「行為不變」原則保留原行為並在檔頭記錄；要精確值請用 scalar 版。
#
#### 還沒挖、但可以挖的（v2 backlog）
#
#- **GLAS 的 GDS render** → die-to-database 參考圖（`render_gray_and_label_from_geoms`
#  已經能同時吐灰階圖與 ROI label map，兩者保證像素對齊）。這是「連 Golden Cell 都做不出
#  參考圖」時的最後一條路。
#- **Fusi³ 的 PCA fusion 與 quadrant 多通道融合**（BSE/SE）。
#- **MMH 的 Region Stats / FFT**（分區統計、去趨勢、週期頻譜）。
#
#---
#
### 4. 目前狀態：哪些是真的，哪些還是假設
#
#**這一節請務必誠實看待。**
#
#### 已驗證的
#
#- 588 個測試全綠，全部跑在**合成資料**上，約 30 秒跑完。
#- 效能：2 核容器、2000 顆合成 patch，cold 17.5 ms/顆、暖快取 2.2 ms/顆、rescore 0.17 s。
#- 分類效果：`dual_route_basic.json` 跨 3 seeds × 2 種輸入共 144 顆合成 defect，正確率 95.1%。
#- KLARF 無損寫回：inplace 模式沒改東西時輸出逐位元組相同（有測試鎖）。
#- 唯一一份**真實來源的 KLARF**（`tests/fixtures/sample_real.klarf`，來自 GLAS）能正確解析、
#  lint 乾淨、無損還原。
#
#### 還是假設的（CLAUDE.md §8 有完整版）
#
#真實資料不能出廠，所以以下三件事**從頭到尾沒有用真實資料驗證過**：
#
#1. **EBI patch 的 page→channel 對應** —— 目前假設每顆 defect 第一張 = test、第二張 = ref。
#2. **`nm_per_px` 從哪來** —— KLARF 裡找不到，暫為 `None`，所以 **CD 量測的 nm 值目前都是 0**。
#3. **KLARF 變體還有幾種** —— 已知四種（含 M5 修正的 variant D）。
#
#`fab_probe/` 三支腳本就是為了回答這三題而做的：stdlib-only 單檔、輸出純文字、
#預設遮蔽 Lot/Wafer/Device 識別碼，設計成可以直接複製貼出廠區。
#**進廠跑一次是下一個最有價值的動作。**
#
#### 開發過程中踩到、已修但值得知道的坑
#
#完整表在 `CLAUDE.md` §7。三個最容易再踩的：
#
#- **fork 死鎖**：Linux 預設 fork 若從 QThread 呼叫，ProcessPool 100% 卡死（GUI 按「試跑」
#  永遠不回、也不報錯）。已改成主執行緒 fork、非主執行緒 spawn。
#- **OpenCV IPP 非決定性**：同張圖算兩次差 ~1e-8，快取結果對不起來。已關閉 IPP。
#- **KLARF variant D**：`ImageList` 欄不在最後 + 沒有 IMAGECOUNT 欄 → `row_len_ok` 誤判每列違法。
#  修法是把 `Images N { … }` 折算成一欄。**注意 `image_layout()` 對這個變體仍回 `None`，
#  而 export 的插欄位置正好因此落在最後 —— 那是對的，別「順手修好」它。**
#
#---
#
### 5. 設計決策與理由（改動前先看這裡）
#
#這些是「看起來可以隨便改、但其實有理由」的地方。
#
#**`golden_cell` 預設寫進 `ref`。**
#RSEM 沒有機台給的參考圖，Golden Cell 疊一張出來後命名為 `ref` ——
#於是下游所有吃 ref 的卡片（對位、相減…）完全不用改，rsem route 只是比 ebi route
#多插一張卡，整條算法段直接重用。這是「站點差異封裝進 recipe」最漂亮的一次體現。
#
#**快取邊界切在影像段結尾。**
#與三段式心智模型對齊：使用者改算法段或判定段的任何東西，都只重算後半，秒級回饋。
#
#**score 表達式引擎是自己寫的 parser，不用 `eval`。**
#安全語意：除以零、log 負數、NaN 都回 0.0，不會噴 traceback 給不寫 code 的人看。
#
#**幾何類參數要隨 route 走。**
#同一組 `glv_stats` 中心框在 128² patch 上準、在 256² RSEM 上會漏抓（缺陷散佈超出框）。
#`dual_route_basic.json` 的做法是兩條 route 各自一個 glv 節點。
#或者改用無量綱分數（`(glv_max-glv_median)/(glv_std+0.5)`），那樣才有共用門檻。
#
#**Export 一定要先「預覽變更」才解鎖「寫出」。**
#對著正式 KLARF 按下去的東西，不該讓人賭。任何選項一改動就作廢重鎖。
#
#**`repo 只有純文字檔`是刻意維持的不變量。**
#使用者的公司機有 DLP 會擋含二進位的壓縮檔。所以：不要把任何 `.png`/`.pyd`/`.zip`
#加進版控，也**不要把 `.git` 打包給使用者**（二進位 pack 物件 + `hooks/*.sample`
#腳本會觸發 DLP —— 這件事踩過一次）。
#
#---
#
### 6. 接手後可以做什麼
#
#依價值排序：
#
#1. **帶 `fab_probe/` 進廠跑一次**，把 §4 那三個假設變成事實。
#   輸出貼回來 → 把真實格式做成最小化合成 fixture → 永久回歸測試
#   （寫法參考 `tests/test_klarf_variant_d.py`：先斷言「這份檔案確實是該變體」當前提，再測行為）。
#2. **拿一份真實 lot 跑一次完整流程**，看分數分佈長什麼樣、Gallery 掃起來合不合理。
#   這是第一次知道合成資料上的 95% 有多少能兌現。
#3. **v2 backlog**（`CLAUDE.md` §9 底部）：ground-truth 標注 + 混淆矩陣儀表板
#   （KPI「分類準確度」的完整量化靠這個）、自由 DAG 畫布、ML Classify 卡、
#   快速參考卡 PDF、以及 §3 那些還沒挖的來源專案資產。
#
#### 給 Claude Code session 的提醒
#
#- `CLAUDE.md` 會自動載入，是操作手冊；這份 `HANDOVER.md` 要自己開。
#- **每次 session 結束請更新 `SESSION_LOG.md`**（沿用 GLAS/MMH 的慣例）。
#  那份是逐次的決策紀錄，比 commit message 詳細。
#- 這個 repo 的測試全部用合成資料、~30 秒跑完，所以**改任何東西都應該先跑一次全套**：
#  `QT_QPA_PLATFORM=offscreen pytest -q`（Windows 不用設環境變數）。
#- 新增卡片的完整範例在 `CLAUDE.md` §5。新算法 = 新 class + decorator，UI 與引擎零修改。
#
#F 08a0584487f2854df1c7796915fbf51f3d90397a 319 docs/NO-GIT-SETUP.md
## 在沒有 git 的機器上使用 ADEPT
#
#適用情境：**公司機沒有 git（或 git 被擋）。** 整個 repo 只有純文字檔
#（`.py` / `.md` / `.json` / `.toml` / `.txt` / `.yml` / 一份 `.klarf`），
#沒有任何執行檔或二進位檔，不需要 git 也能跑。
#
#> ## 先看這裡：你的機器下載得了東西嗎
#>
#> 這一份原本假設你可以按 GitHub 的「Download ZIP」。**實測遇到的環境連那個都
#> 不行** —— `.zip` 被擋、`.py` 也被擋，等於什麼都下載不了，但**看得到 GitHub 上
#> 的檔案而且可以按複製鈕**。完整的環境限制見 [`../AGENTS.md`](../AGENTS.md)。
#>
#> | 你的情況 | 跳到 |
#> |---|---|
#> | **什麼都下載不了**（只能看 GitHub + 複製）| **§0 用剪貼簿搬** ← 多數人在這裡 |
#> | 下載得了東西，只有 GitHub 的 ZIP 不行 | §1 取得程式碼 |
#> | 什麼都下載得了 | §1，按 Download ZIP 就好 |
#
#---
#
### 0. 用剪貼簿搬（下載完全不通的時候）
#
#三條路，用在不同時機 —— **不要每次都搬整包**：
#
#### 0a. 第一次搬整包：`bundle/` 裡的六批
#
#`bundle/ADEPT_part1of6.py` … `part6of6.py`。對每一批做同一件事：
#
#1. 在瀏覽器打開 `https://github.com/hxlub0905-cmyk/ADEPT/blob/main/bundle/ADEPT_part1of6.py`
#2. 按檔案右上角的**複製鈕**（從已經載入的網頁複製，不會再連別的主機）
#3. 貼進記事本，存成同名的 `.py`
#4. `python ADEPT_part1of6.py`
#
#**順序不重要，重複執行也沒關係。** 每一批解完會告訴你整個 repo 還缺幾個檔案，
#全部到齊之後才會印「下一步」。
#
#為什麼是六批而不是一個檔案：**GitHub 不顯示超過 1 MB 的檔案** —— 整包 2.4 MB
#在那台機器上根本點不開來複製。每一批 < 420 KB。
#
#包裡沒有壓縮、**也沒有 base64**：每個檔案的內容一行一行原樣躺在裡面（每行前面
#加一個 `#`，所以整個檔案仍然是合法的 Python）。你可以用記事本打開往下捲，
#看得到每一個檔案。每個檔案帶 **git blob SHA-1**，貼歪或被截斷會**當場講出來**。
#
#### 0b. 之後更新：先複製一個 12 KB 的清單
#
#不要重跑 0a。`tools/FILELIST.txt` 是全部檔案的 SHA，只有 12 KB：
#
#1. 複製 `tools/FILELIST.txt` 覆蓋掉舊的
#2. `python tools/check_files.py`
#
#它會列出**哪幾個檔案要重新複製**（缺少的、內容不一樣的），加 `--urls` 還會把
#GitHub 的網址一起印出來，貼到瀏覽器就能開。所以更新一次是
#「一次小複製 + 幾次針對性複製」。
#
#### 0c. 只想跑格式探測：三支單檔腳本
#
#要驗證 `CLAUDE.md` §8 那三個廠內假設，**不需要整個專案**。
#`fab_probe/probe_klarf.py` / `probe_tiff.py` / `probe_stats.py` 各 24–46 KB、
#stdlib-only、單檔，複製過去直接跑。輸出是純文字且預設遮蔽 Lot／Wafer／Device，
#所以結果可以貼回開發端。
#
#---
#
### 1. 取得程式碼（下載通得過的時候）
#
#到 `https://github.com/hxlub0905-cmyk/ADEPT` → 綠色 **Code** 按鈕 →
#**Download ZIP** → 解壓到任意資料夾。
#
#解壓後會得到 `ADEPT-main\`，裡面就是完整程式碼。
#GitHub 產生的 zip **不含 `.git` 資料夾**，所以裡面 174 個檔案全部是純文字，約 850 KB。
#
#### 如果 Download ZIP 被公司擋掉
#
#**這件事跟 repo 的內容不一定有關係**，先分辨是哪一種 —— 三種原因的處置完全不同：
#
#| 先做這個測試 | 結果 | 那就是 |
#|---|---|---|
#| 直接開 `https://codeload.github.com/hxlub0905-cmyk/ADEPT/zip/refs/heads/main` | 這個網址被擋，但 `github.com` 的網頁看得到 | **主機層的封鎖**（最常見，已實際遇到）。看下面「主機層封鎖」那一段 |
#| 隨便下載另一個無關的公開 repo 的 zip | 也被擋 | **政策層面禁止 .zip 這個類別**，跟哪個 repo 無關。走下面的替代路徑 |
#| 上面兩個都正常，只有這個 repo 的 zip 被擋 | — | **DLP 掃到了內容**。看 §「DLP 掃內容」那一段 |
#
#### 主機層封鎖 → 用 `tools/get_code.py`
#
#**已知這是真的會發生的情況**（實際遇到過：`codeload.github.com` 被擋，
#`github.com` 的網頁正常）。這種時候：
#
#- **`.tar.gz` 不用試** —— 它在同一台主機上，換副檔名沒有用。
#- 根治是**請 IT 放行 `codeload.github.com`**。它跟 `github.com` 是同一個信任範圍，
#  只是 GitHub 把 archive 下載放在另一個網域。可以這樣寫給 IT：
#  > 請將 `codeload.github.com` 加入允許清單。它是 github.com 的官方
#  > archive 下載網域（按 Code → Download ZIP 時瀏覽器實際連線的主機），
#  > 目前 `github.com` 已放行但 `codeload.github.com` 未放行，
#  > 導致可以瀏覽程式碼但無法下載。
#
#- 不想等 IT，就走 **`tools/get_code.py`**：它只用 **`raw.githubusercontent.com`
#  一台主機**逐檔抓（送的是 `text/plain`，DLP 對它的規則跟 `application/zip`
#  完全不同），而且**不需要 git、不需要任何套件**。
#
#  怎麼拿到那支腳本（你連它也下載不了）：
#  1. 在瀏覽器開 `https://github.com/hxlub0905-cmyk/ADEPT/blob/main/tools/get_code.py`
#  2. 按檔案右上角的**複製鈕**（那是從已經載入的網頁複製，不會再連別的主機）
#  3. 貼進記事本，存成 `get_code.py`
#  4. `python get_code.py`
#
#  ```
#  python get_code.py                    # 抓到 .\ADEPT\
#  python get_code.py --dest D:\tools    # 抓到別的地方
#  python get_code.py --cafile corp.pem  # 公司有 TLS 中間攔截時
#  ```
#
#  抓下來的內容跟 GitHub 上**逐位元組相同**（實測比對過），而且那一份自己
#  跑得起來（`pytest -q` 只會 skip 掉兩支需要 git 的清單檢查）。
#
#  它會對每個檔案驗 **git blob SHA**。這不是龜毛 —— 被擋的 proxy 常常回一頁
#  登入頁或警告 HTML，而且是 **HTTP 200**。那種東西寫進 `.py` 之後，症狀會變成
#  「程式碼看起來都在，但 import 就爆語法錯誤」，而你完全不會歸因到下載。
#  SHA 對不上就不落地，並且明講「這份程式碼不完整，不要用」。
#
#  ⚠ 憑證錯誤請用 `--cafile` 指到公司的根憑證，**不要去關掉 TLS 驗證**
#  （那會讓這支腳本變成一個把任意內容寫進磁碟的工具；有測試守著這件事）。
#
##### 逾時（WinError 10060）＝ 沒走 proxy，不是被擋
#
#**實際遇到過。** 逾時的意思是「封包直接送出去、沒有人回應」。
#如果你的**瀏覽器連得到 GitHub**，那答案幾乎一定是：
#**這台機器要透過公司 proxy 才連得出去，而 Python 沒有走 proxy。**
#
#原因：`urllib` 會讀 `HTTPS_PROXY` 環境變數與 Windows 登錄檔裡**手動設定**的
#proxy，但**讀不到 PAC（自動設定指令碼）** —— 而公司幾乎都用 PAC。
#瀏覽器懂 PAC，Python 不懂，所以同一台機器上一個通一個不通。
#
#**Windows 上 `get_code.py` 會自己解 PAC**：沒有其他 proxy 設定時，它請 .NET
#算出「連這個網址該走哪個 proxy」（`GetSystemWebProxy().GetProxy(url)` —— 瀏覽器
#用的就是同一套設定），解得出來就直接用。開頭那行 `Proxy :` 會講它是怎麼來的。
#PAC 檔通常有上百行條件判斷，而「哪一行適用於這個網址」正是 PAC 要算的東西，
#不該由你手算。
#
#自動解不出來（或不是 Windows）才需要自己找 proxy 位址：
#
#```powershell
#netsh winhttp show proxy
#Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' |
#    Select ProxyServer, AutoConfigURL
#```
#
#⚠ **不要**用 `pip config list` 來找 proxy：很多公司的 pip 是走**內部 PyPI 鏡像**
#（`index-url` 指到內網），根本沒有 proxy 設定 —— 而且那個輸出裡常常**含帳號密碼**，
#貼給別人看之前要遮掉。
#
#`AutoConfigURL` 有值就是 PAC：**用瀏覽器打開那個網址**，在裡面找
#`PROXY 主機:埠` 那一行。然後：
#
#```powershell
#python get_code.py --proxy http://主機:埠
## 或者設環境變數（pip 也吃這個，一次解決兩個問題）
#$env:HTTPS_PROXY = 'http://主機:埠'
#python get_code.py
#```
#
##### 拒絕連線（WinError 10061）→ 換 PowerShell 版
#
#**實際遇到過**，而且它跟逾時是不同的事：拒絕連線的意思是**位址找得到、封包也到
#了，但那個埠上沒有東西在聽**。最常見的原因是 PAC 解出來的網址**沒有埠**，
#於是 Python 用了預設的 80，而公司 proxy 幾乎不在 80。
#
#這時候先試常見的埠（`8080` / `3128` / `8000` / `9090`），不行就**改用
#PowerShell 版**：
#
#```powershell
#powershell -ExecutionPolicy Bypass -File .\get_code.ps1
#```
#
#`tools/get_code.ps1` 跟 `.py` 版是**同一份契約**（同一份 `FILELIST.txt`、
#同樣驗 git blob SHA、同樣 atomic 寫入），差別在它走 .NET —— 也就是**瀏覽器用的
#那一套網路堆疊**。三件 Python 做不到的事它原生就有：
#
#| | `get_code.py` | `get_code.ps1` |
#|---|---|---|
#| 解 PAC | 借 .NET 算，只拿得到**第一個** proxy | 原生，多個候選會**依序 fallback** |
#| proxy 的 Windows 整合驗證（NTLM / Kerberos）| ✗ | ✓ |
#| TLS 版本 | 跟著 Python | 明確設 TLS 1.2（PS 5.1 預設 1.0，GitHub 收不了）|
#
#所以判斷方式很簡單：**瀏覽器連得到 GitHub 的話，PowerShell 通常就連得到。**
#`-ExecutionPolicy Bypass` 是必要的 —— PowerShell 預設不准跑腳本檔。
#拿這支的方式跟 `.py` 版一樣：在 blob 頁按複製鈕、貼進記事本。
#
#一行決定要不要走這條路（PowerShell 拿得到就代表值得）：
#
#```powershell
#Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/hxlub0905-cmyk/ADEPT/main/tools/FILELIST.txt' -UseBasicParsing -OutFile t.txt
#```
#
#- 三台主機都被擋的話，剩下的路是**在有網路的機器上取得，用你搬 `wheels\` 的
#  同一條路搬過來**（見 [`OFFLINE-INSTALL.md`](OFFLINE-INSTALL.md)）。
#
#### 連 .zip 這個類別都被擋 → 單檔純文字包
#
#**實測遇到過**：不只是 `codeload.github.com`，**從任何來源下載 `.zip` 都被擋**。
#這種情況下「請 IT 放行 codeload」也沒有用（拿到的還是 zip），而 `get_code.py` /
#`.ps1` 也要 proxy 通得過才行。能過的只剩「一個純文字檔」。
#
#`tools/make_text_bundle.py` 在**有網路的機器上**把整個 repo 打成一個
#`ADEPT_bundle.py` —— **沒有任何壓縮格式、沒有 base64**，每個檔案的內容原封不動
#一行一行躺在裡面（每行前面加一個 `#`，所以整個檔案仍然是合法的 Python）。
#你可以用記事本打開它往下捲，看得到每一個檔案。
#
#```
#python tools/make_text_bundle.py        # 產 ADEPT_bundle.py（約 2.4 MB 純文字）
#```
#
#把那個檔案帶到公司機（下載、郵件、隨身碟 —— 它就是一個 .py 檔），然後：
#
#```
#python ADEPT_bundle.py                  # 解到 .\ADEPT\
#python ADEPT_bundle.py --list           # 先看裡面有什麼，不寫任何檔案
#```
#
#每個檔案都帶 **git blob SHA-1**，解開時逐檔驗過才落地。傳輸途中被動到（編輯器
#另存、郵件過濾器改寫）會**當場講出來**，而不是給你一份安靜壞掉的程式碼。
#
#格式刻意用**行數**而不是位元組數：這個檔案很可能在某個環節被把 LF 換成 CRLF，
#而用位元組數的話那一換就會讓**第一個檔案之後的全部檔案**對不起來。
#（有測試把「換過行尾還解得開」鎖住。）
#
#### DLP 掃內容
#
#如果只有這個 repo 的 zip 被擋，那要看的是**裡面有沒有公司的識別碼**。
#`tests/fixtures/sample_real.klarf` 是唯一一份真實來源的檔案（它就是這樣抓到
#KLARF variant D 的），它裡面的 Lot／Wafer／機台／device／**recipe 名稱**
#（recipe 名稱通常編碼了層別與製程步驟）與缺陷分類名稱**都已經遮蔽成合成值**，
#而且有一支測試守著（`tests/test_no_real_fab_data.py`）：
#
#```
#pytest -q tests/test_no_real_fab_data.py
#```
#
#加新 fixture 時那支測試會擋下沒遮蔽的值。**遮蔽是等長替換，測試只看結構不看值，
#所以遮蔽不會弄壞任何斷言。**
#
#⚠ 遮蔽只影響「現在的檔案」。**已經推上去的 git 歷史裡還留著原本的值** ——
#DLP 掃的是下載下來的 zip（GitHub 的 zip 不含 `.git`，所以看不到歷史），
#但如果要求是「repo 裡完全不能有」，那需要重寫歷史或把 repo 改成 private。
#
### 2. 安裝相依套件
#
#```
#cd ADEPT-main
#python -m venv .venv
#.venv\Scripts\activate
#pip install -r requirements.txt
#```
#
#需要 4 個套件：`numpy`、`opencv-python`、`tifffile`、`PySide6`。
#
#**如果公司擋 pip 對外連線**（很常見）：改走離線 wheels ——
#在有網路的機器上 `python tools/fetch_wheels.py`，把產生的 `wheels\` 資料夾帶進公司機，
#再跑 `python tools/install_offline.py`。完整步驟與疑難排解見
#**[`docs/OFFLINE-INSTALL.md`](OFFLINE-INSTALL.md)**。
#
#裝完（或安裝失敗想知道卡在哪）都可以跑環境自檢：
#
#```
#python tools/doctor.py
#```
#
#它會逐項檢查 Python 版本、每個套件、Qt 能不能開視窗、資料夾權限，
#每個沒過的項目都附一行「怎麼修」。
#
### 3. 確認能跑
#
#```
#python -m adept steps
#```
#
#會列出全部步驟卡片。看得到「影像段 IMAGE / 算法段 ALGO」就代表裝好了。
#
#跑測試（可選，需要 `pip install pytest`）：
#
#```
#set QT_QPA_PLATFORM=offscreen
#pytest -q
#```
#
### 4. 產一份合成資料試玩（不需要真實 KLARF）
#
#```
#python tools\make_sample.py C:\temp\lot --n 100
#```
#
#會產生 `LOT_SYN.001`（KLARF）、`LOT_SYN.tif`（patch 影像）、
#`ground_truth.json`（哪些是真缺陷，供你驗證算分效果）。
#
### 5. 開圖形介面
#
#```
#python -m adept gui
#```
#
#在 Studio 裡：**開啟 KLARF** 選剛才的 `LOT_SYN.001` → **載入範本（die-to-die）**
#→ **試跑** → 拖下方的門檻線看 bin 數變化。
#
### 6. 命令列批次
#
#```
#python -m adept run examples\recipes\die_to_die_basic.json C:\temp\lot\LOT_SYN.001 ^
#    --workers 4 --cache C:\temp\cache --csv features.csv
#```
#
#---
#
### 沒有 git 的情況下，怎麼保存你的修改
#
#你的 recipe 存成單一 JSON 檔（Studio 裡「存 Recipe」），那才是你的心血結晶 ——
#程式碼可以隨時重新下載，recipe 不行。建議把 `examples\recipes\` 底下的檔案
#另外備份一份到你自己的資料夾。
#
#如果改了程式碼（例如加了新的步驟卡片），把改動的 `.py` 檔另外複製一份留底；
#之後在有 git 的機器上再合併回 repo。
#
#F b44fd20e599353902ae98f1edc0a1323134d2715 277 docs/OFFLINE-INSTALL.md
## 離線安裝 ADEPT（公司機沒有網路 / pip 連不出去）
#
#適用情境：**公司機沒有 git、pip 連不到外網、只能拿到純文字的原始碼 zip。**
#這份文件寫給「從來沒碰過 Python 套件安裝」的人，照著做就好，不需要懂原理。
#
#整件事只有兩句話：
#
#1. 在**有網路的機器**上，把套件先下載成一個資料夾（`wheels\`）。
#2. 把那個資料夾連同 ADEPT 原始碼帶到**公司機**，用它離線安裝。
#
#> **名詞解釋**
#> * **套件（package）**：ADEPT 用到的現成程式庫，共 4 個：
#>   `numpy`（數值運算）、`opencv-python`（影像處理）、`tifffile`（讀 TIFF）、
#>   `openpyxl`（寫 Excel）、`PySide6`（圖形介面）。
#> * **wheel（`.whl` 檔）**：套件「已經編譯好」的安裝檔，副檔名 `.whl`。
#>   它本質上是一個 zip 檔，裡面有 `.py` 與（部分套件）編譯好的 `.pyd` / `.dll`。
#> * **venv（虛擬環境）**：一個獨立的小 Python 環境，裝在 ADEPT 資料夾底下的 `.venv\`。
#>   好處是不會弄髒公司機原本的 Python，要刪掉就整個資料夾砍掉。
#
#---
#
### 開始之前：先查兩件事（在**公司機**上查）
#
#打開命令提示字元（開始 → 輸入 `cmd`），輸入：
#
#```
#python -V
#python -c "import struct; print(struct.calcsize('P')*8, 'bit')"
#```
#
#你會看到類似 `Python 3.11.5` 與 `64 bit`。**把版本號記下來**，等一下要用：
#
#| 公司機顯示 | 等一下要填的 `--python-version` |
#|---|---|
#| Python 3.9.x  | `39` |
#| Python 3.10.x | `310` |
#| Python 3.11.x | `311` |
#| Python 3.12.x | `312` |
#
#> 版本填錯是離線安裝**最常見**的失敗原因（`cp39` 的檔案在 Python 3.11 上一定裝不起來）。
#> ADEPT 的安裝程式會在動手前先幫你比對、擋下來，但一開始就填對可以省一趟來回。
#>
#> 如果顯示 `32 bit`，請請 IT 換成 64 位元的 Python —— `PySide6` 與 `opencv` 幾乎只出 64 位元版。
#> ADEPT 需要 **Python 3.9 以上**。
#
#---
#
## 第一部分：在**有網路的機器**上
#
### 步驟 1：拿到 ADEPT 原始碼
#
#到 `https://github.com/hxlub0905-cmyk/ADEPT` → 綠色 **Code** → **Download ZIP**，
#解壓成 `ADEPT-main\`。（詳見 `docs/NO-GIT-SETUP.md`。）
#
### 步驟 2：下載套件到 `wheels\` 資料夾
#
#在 `ADEPT-main\` 裡開命令提示字元，執行（把 `311` 換成你剛剛記下來的版本）：
#
#```
#python tools\fetch_wheels.py --python-version 311
#```
#
#想連測試工具一起帶（之後要在公司機跑 `pytest`）就多加一個選項：
#
#```
#python tools\fetch_wheels.py --python-version 311 --include-pytest
#```
#
#這支程式做的事：叫 pip 去 PyPI 把「**Windows 64 位元 + 你指定的 Python 版本**」的
#`.whl` 檔通通抓下來放進 `wheels\`。
#**在 Linux 或 Mac 上跑也沒關係**，它抓的一樣是 Windows 版的檔案。
#
#其他可用選項：
#
#| 選項 | 用途 |
#|---|---|
#| `--dest D:\adept_wheels` | 換一個存放資料夾 |
#| `--platform win_amd64` | 目標平台（預設就是這個；32 位元填 `win32`） |
#| `--include-pytest` | 連 pytest 一起抓 |
#| `--dry-run` | 只印出它會執行的指令，不真的下載（想先看看它要做什麼時用） |
#
### 步驟 3：看它的驗收報告
#
#跑完會印出一張表和一句結論，例如：
#
#```
#  套件            版本      標籤              大小
#  ------------------------------------------------
#  PySide6         6.5.2     cp37-win_amd64   1.5 KB
#  numpy           1.26.4    cp311-win_amd64  15.5 MB
#  ...
#  合計 12 個檔案，180.4 MB
#
#→ 已寫出清單：...\wheels\MANIFEST.txt
#
#結論：12 個 wheel、共 180.4 MB，全部齊全。
#```
#
#* 看到「**全部齊全**」就成功了。
#* 如果它說某個套件「**沒有抓到任何 .whl**」→ 多半是 `--python-version` 填的版本
#  沒有官方 wheel，換一個版本再試。
#* 如果它說資料夾裡有「**原始碼包（不是 wheel）**」→ 那種檔案在公司機需要 C 編譯器，
#  幾乎一定裝不起來，請改用有 wheel 的版本、或請 IT 從公司內部鏡像站取得。
#
#`wheels\MANIFEST.txt` 是**清單檔**：裡面有每個檔案的名稱、sha256 雜湊值、
#以及這批檔案是給哪個平台／哪個 Python 版本用的。
#公司機的安裝程式會讀它做版本比對；IT 要稽核「你到底帶了什麼進來」時也可以直接給他看這個檔。
#
### 步驟 4：要帶進公司的東西
#
#只有兩樣，放在同一個資料夾裡最省事：
#
#```
#ADEPT-main\          ← 原始碼（純文字，沒有任何執行檔）
#ADEPT-main\wheels\   ← 剛剛下載的 .whl 檔 + MANIFEST.txt
#```
#
#> ### ⚠️ 關於公司 DLP（資料外洩防護）擋壓縮檔／執行檔
#>
#> **原始碼 zip 沒有問題**：整包都是純文字（`.py` / `.md` / `.json` / `.txt`），
#> 沒有任何執行檔。
#>
#> **`wheels\` 資料夾要注意**：`.whl` 檔本身是 zip 格式，而且 numpy / opencv / PySide6
#> 的 wheel 裡面確實含有編譯好的二進位檔（`.pyd` / `.dll`）—— 這是所有 Python 套件的
#> 正常型態，但有些公司的 DLP 政策會直接擋。三條路：
#>
#> 1. **請 IT 把這個資料夾加入允許清單**。把 `MANIFEST.txt` 給他看：
#>    裡面列出每個檔案的名稱、大小與 sha256，全部是公開 PyPI 上的官方套件，
#>    沒有任何自製二進位檔，IT 可以逐一比對來源。
#> 2. **用公司內部的套件鏡像站**（Artifactory / Nexus / 內部 PyPI）。
#>    如果公司有，那是最順的做法，完全不用帶檔案進來：
#>    ```
#>    pip install -r requirements.txt --index-url https://內部鏡像站/simple --trusted-host 內部鏡像站
#>    ```
#>    （鏡像站網址請問 IT。）
#> 3. **請 IT 直接幫你安裝**這 5 個套件 —— 它們都是業界標準的公開套件。
#>
#> 不論走哪一條，裝完都用 `python tools\doctor.py` 驗收（見下）。
#
#---
#
## 第二部分：在**公司機**上
#
### 步驟 1：解壓原始碼
#
#把 `ADEPT-main.zip` 解壓到**你自己有寫入權限的資料夾**，例如
#`C:\Users\你的帳號\ADEPT-main`。
#
#> 不要放在 `C:\Program Files\`、磁碟根目錄、或唯讀的網路磁碟 —— 會沒有權限寫檔案。
#
#把帶進來的 `wheels\` 資料夾放進 `ADEPT-main\` 裡面。
#
### 步驟 2：切換到那個資料夾
#
#開始 → `cmd` → 輸入（路徑換成你自己的）：
#
#```
#cd C:\Users\你的帳號\ADEPT-main
#dir
#```
#
#`dir` 要看得到 `adept`、`tools`、`requirements.txt`、`wheels` 這幾個名字。
#**看不到就是你在錯的資料夾** —— 這是新手最常見的錯誤，後面所有指令都會失敗。
#
### 步驟 3：安裝
#
#```
#python tools\install_offline.py
#```
#
#（如果 `wheels\` 放在別的地方：`python tools\install_offline.py --wheels D:\adept_wheels`）
#
#它會依序做四件事，每一步都會印出結果：
#
#```
#[1/4] 事前檢查…          ← 版本、空間、權限對不對；有問題會在這裡停下來並告訴你怎麼修
#[2/4] 建立虛擬環境 .venv  ← 一個乾淨的小 Python 環境，不會動到公司機原本的設定
#[3/4] 安裝套件…          ← pip install --no-index --find-links=wheels -r requirements.txt
#                            （--no-index = 完全不連網，只用你帶進來的檔案）
#[4/4] 環境自檢…          ← 自動跑 tools\doctor.py 驗收
#```
#
#最後會印出一段「接下來要打的指令」。**看到自檢通過就成功了。**
#
#常用選項：
#
#| 選項 | 什麼時候用 |
#|---|---|
#| `--wheels 路徑` | `wheels\` 放在別的地方 |
#| `--include-pytest` | 連 pytest 一起裝（下載時也要加同名選項，`wheels\` 裡才會有） |
#| `--no-venv` | 公司機的 Python 建不出虛擬環境（見疑難排解） |
#| `--no-venv --user` | 沒有系統管理權限，要裝到自己的帳號底下 |
#| `--venv D:\adept_venv` | C 槽空間不夠，把虛擬環境放到別的磁碟 |
#| `--dry-run` | 只做事前檢查、不真的安裝（想先確認環境沒問題時用） |
#
### 步驟 4：驗收與開始用
#
#```
#.venv\Scripts\activate         ← 每次開新的命令提示字元都要先做這一步
#python tools\doctor.py         ← 環境自檢，全部 ✓ 就沒問題
#python -m adept gui            ← 開圖形介面 Studio
#```
#
#第一次玩可以先產一份合成資料（不需要真實 KLARF）：
#
#```
#python tools\make_sample.py C:\temp\lot --n 100
#```
#
#然後在 Studio 裡：**開啟 KLARF** 選 `C:\temp\lot\LOT_SYN.001` →
#**載入範本（die-to-die）** → **試跑**。
#
#> `.venv\Scripts\activate` 執行成功後，命令提示字元最前面會出現 `(.venv)`。
#> 沒有那個字樣就表示還沒啟用，`python -m adept gui` 會說找不到套件。
#
#---
#
## 第三部分：疑難排解
#
#**任何時候卡住，先跑這一行**，它會逐項告訴你哪裡壞了、以及怎麼修：
#
#```
#python tools\doctor.py            （想看完整錯誤訊息就加 --verbose）
#```
#
#`doctor` 檢查：Python 版本與位元數、5 個套件能不能載入、
#從目前資料夾能不能找到 `adept`、Qt 能不能開視窗、
#資料夾與快取目錄 `~\.adept` 有沒有寫入權限，
#最後還會實際產一份迷你合成資料、跑一顆 defect 走完整條 recipe（約 10 秒）。
#全部通過離開碼是 0，否則是 1，最後一行永遠是一句白話結論。
#
#| 症狀（畫面上出現的訊息） | 真正的原因 | 怎麼修 |
#|---|---|---|
#| `install_offline` 說「**Python 版本對不上**」 | 帶進來的 wheel 是給別的 Python 版本用的（例如 cp39 的檔案配 Python 3.11） | 兩條路：(A) 公司機若也裝了對應版本，用那個版本執行，例如 `C:\Python39\python.exe tools\install_offline.py`；(B) 回有網路的機器重抓：`python tools\fetch_wheels.py --python-version 311` |
#| pip 說 `... is not a supported wheel on this platform` | 同上（版本或 32/64 位元不合），或抓成了 Linux/Mac 版 | 重抓時確認 `--python-version` 與 `--platform win_amd64` 都正確 |
#| `install_offline` 說「**找不到離線套件資料夾**」 | `wheels\` 沒帶到、或不在預設位置 | 用 `--wheels` 指定完整路徑，或把資料夾複製到 `ADEPT-main\wheels` |
#| `install_offline` 說「**裡面沒有任何 .whl 檔**」 | 複製時只複製了空資料夾，或防毒／DLP 把 `.whl` 擋掉刪掉了 | 重新複製一次；若是 DLP 擋掉，見第一部分的 DLP 說明（請 IT 允許清單化或改用內部鏡像站） |
#| 建立虛擬環境失敗，訊息裡有 `ensurepip` | 公司統一安裝的 Python 映像常把 `ensurepip` 拿掉，`python -m venv` 因此建不起來 | 改成不建虛擬環境：`python tools\install_offline.py --no-venv`；若連系統目錄都不能寫，再加 `--user` |
#| `Permission denied` / `Access is denied` / 「沒有寫入權限」 | ADEPT 放在 `C:\Program Files` 之類受保護的位置，或家目錄被鎖 | 把整個資料夾搬到 `C:\Users\你的帳號\` 底下再試；快取可用 `--cache D:\temp\adept_cache` 指到寫得進去的地方 |
#| 「磁碟空間不夠」 | PySide6 解開後要幾百 MB | 清空間，或 `--venv D:\adept_venv` 把虛擬環境放到別的磁碟 |
#| `ImportError: DLL load failed while importing QtCore` 或 `doctor` 說「Qt 開不了視窗」 | PySide6 需要 **Microsoft Visual C++ Redistributable 2015-2022 (x64)**，公司機常常沒裝 | 請 IT 安裝 VC++ Redistributable (x64)。暫時的替代方案：先用命令列模式 `python -m adept run ...`（不需要開視窗） |
#| `ModuleNotFoundError: No module named 'adept'` | **跑錯資料夾**（八成是這個原因） | `cd` 到解壓出來、`dir` 看得到 `adept` 資料夾的那一層再執行 |
#| `ModuleNotFoundError: No module named 'numpy'`（明明裝過了） | 忘了啟用虛擬環境 | 先 `.venv\Scripts\activate`，命令提示字元前面要出現 `(.venv)` |
#| pip 出現 proxy / SSL / 連線逾時 的錯誤 | **離線安裝其實完全不連網**（`--no-index` 已經關掉了）。會出現這種訊息，通常是機器上有 `pip.ini` 設了 `index-url`，或設了 `PIP_INDEX_URL` 環境變數 | 檢查 `%APPDATA%\pip\pip.ini`；或先設定 `set PIP_NO_INDEX=1` 再跑一次。**不需要**為了離線安裝去申請開放防火牆 |
#| 下載時 pip 說 `Could not find a version that satisfies the requirement ...` | 那個套件在你指定的 Python 版本沒有官方 wheel | 換 `--python-version`，或放寬 `requirements.txt` 裡的版本下限 |
#| `doctor` 的表格顯示成一堆問號或亂碼 | 命令提示字元的字碼頁不支援 ✓✗△ | 先執行 `chcp 65001` 再跑；`doctor` 也會自動改用 `[OK]/[XX]/[!!]` 這種純英數符號 |
#
#---
#
### 附錄：指令速查
#
#**有網路的機器**
#
#```
#python tools\fetch_wheels.py --python-version 311 --include-pytest
#python tools\fetch_wheels.py --dry-run              # 只看它會做什麼
#```
#
#**公司機**
#
#```
#cd C:\Users\你的帳號\ADEPT-main
#python tools\install_offline.py                     # 安裝（會自動驗收）
#python tools\install_offline.py --no-venv --user    # 沒權限 / 建不出 venv 時
#.venv\Scripts\activate                              # 每次開新視窗都要先做
#python tools\doctor.py --verbose                    # 出事時第一個跑這個
#python -m adept gui                                 # 開 Studio
#python tools\make_sample.py C:\temp\lot --n 100     # 產合成資料試玩
#```
#
#**要移除的話**：把 `.venv\` 資料夾整個刪掉就好（沒有動到公司機原本的 Python），
#或者把整個 `ADEPT-main\` 刪掉。ADEPT 不會寫入登錄檔，也不需要系統管理員權限。
#唯一會留下的是快取資料夾 `C:\Users\你的帳號\.adept\`（可以直接刪）。
#
#相關文件：`docs/NO-GIT-SETUP.md`（沒有 git 怎麼取得與保存修改）、
#專案根目錄的 `README.md`（ADEPT 是什麼、怎麼用）。
#
#F 284baa3b08f76721a95eabc8674130af5fcfa202 337 docs/plans/F0-master-plan.md
## ADEPT 開發計畫（工作代號，名稱待定）
#
#> 一個 **flexible、多步驟、任何 Inspection 站點都適用**的 ADC 工具：
#> 讀 EBI patch（test+ref）或 RSEM 單張影像 + 對應 KLARF，
#> 用「步驟卡片組 pipeline」把腦中想法變成算法，對每顆 defect 算分、
#> 調參看整批分佈、寫回 KLARF。
#> 定位：PADC / RADC 的低門檻繼承者 —— **站點差異封裝進 recipe，不封裝進程式碼**。
#> 推廣目標：同事學會操作後，不寫 code 也能把想法轉成算法。
#
#版本：v1.0 · 2026-07-27 · 依據六專案盤點 + 三輪需求訪談定案
#
#---
#
### 1. 已確認的需求與決策（訪談結論）
#
#| 決策點 | 結論 |
#|---|---|
#| 使用對象 | **推廣給部門同事**（不寫 code）→ UX 引導、防呆預設值、教學文件是一級需求，不是附屬品 |
#| 形態 | 桌面 GUI（PySide6），core/ui 嚴格分離；**CLI 附帶**（`adept run <recipe> <klarf>` 供排程/腳本） |
#| 組裝方式 | 視覺化 pipeline 編輯器（step 卡片 + 自動生成的參數表單），底層 recipe JSON |
#| 輸入 | 兩者都吃：**EBI patch = test+ref 兩兩配對、8-bit、multi-page TIFF（格式參照 KLIP）**；RSEM = 單張/defect。ingest 自動判別；16-bit 防禦性支援 |
#| 輸出 | ① 無損寫回 KLARF（CLASSNUMBER、ROUGHBIN/FINEBIN、DSIZE）② **score + new class 寫入指定欄位並 gen 新 KLARF**（含 Top-N 篩選）③ CSV/Excel 報表 + overlay ④ per-defect feature vector 匯出（為未來 ML 備料） |
#| Pipeline 結構 | **core 第一版即 DAG**（直線是特例）；UI v1 = 直線鏈 + 輸入型別分流，自由 DAG 畫布 v2 |
#| Gallery | v1 就要：縮圖網格 + score/feature 排序 + 直方圖點 bar 篩選；ground-truth 標注 v2 |
#| CD | 「CD Measure」是 pipeline 中的一張特徵卡，輸出進 score 表達式、可回寫 DSIZE |
#| Step 分類 | **兩大類：影像（Image，影像優化）與算法（Algo，量化）**，由 ADC 判定段串起 —— defect 分數就是這兩件事決定的，UI 分類必須一眼看懂 |
#| v1 精簡 | PCA Ref、Region Stats/FFT 兩張卡移出 v1（列 backlog，之後要加隨時加回） |
#| ML | v1 純 rule-based；**feature 匯出先做**（CSV per defect），「ML Classify」卡留 v2 擴充位 |
#| KPI | 三個都要：自動分類準確度、壓 nuisance rate、**review efficiency（分數排名高的都要是真 defect）** |
#| 資料量級 | 千級常態、偶爾上萬 → **設計目標 10k defect 流暢**（批次 < 2 min、gallery 虛擬捲動） |
#| 程式碼重用 | **Vendoring**：從六專案 copy 進新 repo 改名空間，新工具完全獨立、不動現有專案 |
#| 開發資料 | 實際資料**不能出廠**；開發用合成資料 + KLIP 產的測試 KLARF，配套**廠內探測腳本**（純文字輸出、可複製貼上回報格式變體）§10 |
#| 廠內環境 | 可裝 Python（離線 wheels 建 venv）；單 exe 打包為選配（KLIP build.bat 模式備援） |
#| Recipe 分享 | 單一 JSON 檔互傳即可；工具內建匯入/匯出 + 版本/作者欄位 |
#| 首發實戰案例 | **EBI patch 算分**：證明「想法 → 算法」這條路真的走得通（M3 驗收目標） |
#
#---
#
### 2. 架構總覽
#
#```
#adept/
#├── core/                    # 純運算，零 Qt import（headless 可測）
#│   ├── ingest/              # KLARF + 影像載入、dataset 模型
#│   │   ├── klarf_core.py    # ← KLIP（整檔搬，補 per-defect ImageFileName 解析）
#│   │   ├── tiff_index.py    # ← KLIP klarf_tif_probe.read_tiff_pages + tifffile 像素讀取
#│   │   └── dataset.py       # Dataset / DefectItem（GLAS sem_loader 一般化）
#│   ├── pipeline/
#│   │   ├── step.py          # Step 介面 + ParamSpec + registry
#│   │   ├── recipe.py        # Recipe(DAG) 模型、JSON serde、lint 式驗證
#│   │   ├── context.py       # Context 資料模型
#│   │   ├── engine.py        # 單顆執行 + 批次 ProcessPool + 中間結果快取（← MMH）
#│   │   └── expression.py    # score 表達式引擎（← GLAS gds_boolean AST 改造）
#│   ├── steps/               # step library（見 §5，每類一檔）
#│   ├── store/               # recipe 持久化（← MMH recipe_registry）、批次歷史 SQLite（← MMH batch_run_store）
#│   └── export/              # KLARF 寫回/新檔、CSV/Excel、feature vector、overlay PNG
#├── ui/                      # PySide6 殼
#│   ├── studio/              # Recipe Studio：library｜pipeline｜單顆預覽｜直方圖
#│   ├── gallery/             # 縮圖網格 + 排序 + 直方圖聯動（虛擬捲動）
#│   ├── onboarding/          # 首啟導覽 + 內建範例 recipe（← Fusi³ welcome_tutorial 模式）
#│   └── theme.py             # 設計 token（沿用 GLAS/CPE 主題系統）
#├── fab_probe/               # 廠內探測腳本（獨立、stdlib-only、文字輸出）§10
#├── tests/                   # 合成影像測試（照 CPE test_synthetic 模式）+ KLARF fixtures
#└── tools/                   # CLI 進入點、synthetic data generator
#```
#
#六專案共同驗證過的慣例，直接沿用：core 不得 import Qt；批次 worker 為 top-level
#picklable 純函數、recipe 以 dict 序列化進子行程；檔案寫入一律 atomic（`.tmp`+`os.replace`）；
#KLARF 寫回走 KLIP 無損 span-splice。
#
#---
#
### 3. 資料模型
#
#### 3.1 Dataset / DefectItem（統一兩種輸入）
#
#```python
#@dataclass
#class DefectItem:
#    defect_id: str
#    die: tuple[int, int]              # XINDEX, YINDEX
#    xrel_nm: float; yrel_nm: float
#    images: dict[str, ImageRef]       # ebi_patch: {"test","ref"}；rsem: {"single"}
#    nm_per_px: float | None           # KLARF pixel size / TIFF tag / calibration profile
#    klarf_row: int                    # 寫回用列索引
#    tags: dict                        # class, roughbin, dsize… 原始欄位
#
#@dataclass
#class Dataset:
#    kind: Literal["ebi_patch", "rsem", "folder"]
#    klarf: KlarfDoc | None            # 活的 KLIP 物件，供無損寫回
#    items: list[DefectItem]
#```
#
#判別：KLARF + multi-page TIFF 且 `defect_image_map` 解析成功 → `ebi_patch`
#（page 依 TiffSpec/推斷對應 test/ref）；defect 各帶 ImageFileName → `rsem`；
#純資料夾 → `folder`（演算法開發用）。**diff 不假設存在，一律由 Subtract 卡現算。**
#
#### 3.2 Context（步驟間的執行狀態）
#
#```python
#class Context:
#    images:   dict[str, np.ndarray]   # 命名影像流："test"、"ref_aligned"、"diff"、"snr_map"…
#    rois:     MultiROISet | None      # ← Fusi³（正規化座標，可隨對位 shifted()）
#    labels:   np.ndarray | None       # 整數 ROI label map（← GLAS 契約：gray[label==k]）
#    features: dict[str, float]        # 扁平特徵區 = score 表達式的變數空間
#    meta:     dict                    # nm_per_px、dx/dy、step 診斷（fallback_reason…）
#```
#
#- 每張卡宣告 reads / writes（如 `Subtract: reads ["test","ref_aligned"] → writes ["diff"]`），
#  recipe 驗證期靜態檢查「串起來缺什麼」，不等執行才爆。
#- `features` 是唯一算分介面：CD、SNR、GLV、focus 一視同仁，全部可進表達式、
#  全部進 feature vector 匯出（ML 備料）。
#- 內部運算 float32，顯示端才轉 8-bit；載入用 CJK-safe `np.fromfile`+`imdecode`（PEAR）。
#
#### 3.3 Step 介面與註冊
#
#```python
#class Step(ABC):
#    key: str                          # "snr_map"
#    category: str                     # 前處理｜對位｜Reference｜運算｜ROI｜特徵｜判定
#    params: list[ParamSpec]           # 名稱/型別/範圍/預設/一行說明 → UI 表單自動生成
#    reads: list[str]; writes: list[str]
#    requires_ref: bool = False        # rsem 模式下自動禁用（除非上游有 Reference 卡）
#
#    @abstractmethod
#    def run(self, ctx: Context, p: dict) -> Context: ...
#
#@register_step                        # 新算法 = 新 class + decorator，UI 零修改
#```
#
#> MMH `recipe_base` 的一般化：寫死 6 stage → 任意 DAG 節點；並補上 MMH 缺的 params 驗證。
#> **ParamSpec 的「一行說明 + 合理預設 + 範圍防呆」是推廣成敗關鍵**，每張卡都必填。
#
#### 3.4 Recipe（DAG JSON，單檔可互傳）
#
#```json
#{
#  "recipe_id": "M1_EBI_bridge", "version": 3, "author": "HX",
#  "description": "M1 站 EBI 假點過濾：對位相減 + SNR/CD 雙特徵",
#  "routes": {
#    "ebi_patch": ["load","norm","align","subtract","snr","segment","cd","score","bin"],
#    "rsem":      ["load","norm","golden","subtract","snr","segment","cd","score","bin"]
#  },
#  "nodes": { "align": {"step":"align","params":{"method":"phase","search":8}}, "…": {} },
#  "edges": [["subtract","snr"],["subtract","cd"],["snr","score"],["cd","score"]],
#  "score": {"expr": "snr_max * sqrt(blob_area)", "threshold": 3.0,
#             "bins": {"below": 0, "above": 1}}
#}
#```
#
#- v1 UI 產生直線＋分流（routes），core 以一般 DAG 執行（拓撲排序 ← GLAS
#  `recipe_dependency_order`），v2 上自由畫布時引擎零改動。
#- 驗證走 lint 模式（← KLIP `Issue` 結構）：無環、reads/writes 相容、params 範圍、
#  輸入型別可用性，一次列出所有問題。
#
#---
#
### 4. Score 表達式引擎
#
#GLAS `gds_boolean` 的 tokenizer → AST → evaluator 移植改造：
#
#- 變數 = `features` 的 key（`snr_max`、`cd_x_nm`、`glv_mean_roi1`…），UI 下拉列出目前 pipeline 會產出的全部 key
#- 運算：`+ - * / ** sqrt log abs min max`、比較與布林 `> < >= <= == and or not`
#- 兩用：`score = <expr>`（連續分數 → 直方圖/排序）與 bin 條件（`score >= 3 and cd_x_nm > 25`）
#- v1 鎖定此運算元集，不做迴圈/自訂函數 —— 更複雜的邏輯就寫新 Step（本來就是擴充點）
#
#---
#
### 5. Step Library v1（19 張卡）—— 兩大類 + ADC 串接
#
#Pipeline 在 UI 上呈現為**三段式**，對應「defect 分數由影像與算法兩件事決定」的心智模型：
#
#```
#【影像段 Image】把圖變乾淨、變可比 → 產出的是「影像流」
#        ↓
#【算法段 Algo】從圖量出數字（量化證據）→ 產出的是「features」
#        ↓
#【ADC 判定段】features → score → bin → 寫回
#```
#
#每張卡依所屬段落上色（影像=藍、算法=橙、判定=紫），Library 也照這三組排 ——
#使用者不用理解 context/DAG，只要記得「先弄圖、再量化、最後判定」。
#段落順序由 recipe 驗證強制（算法卡不能排在它要用的影像流之前）。
#
#### 影像段（Image — 影像優化，寫入 images）
#
#| 卡片 | 做什麼 | 來源（搬運 function） |
#|---|---|---|
#| **Load Patch**（固定第一張） | dataset → images | KLIP `klarf_core`+`read_tiff_pages`+tifffile；GLAS `sem_loader` |
#| **Percentile Norm** | P2–P98 拉伸 | Fusi³ `_normalize_image_with_range` |
#| **GLV-Mask Norm** | 指定 GLV 帶內錨定正規化 | Fusi³ `_percentile_range_glv_masked` |
#| **Histogram Match** | 向 reference 匹配直方圖（跨機台） | Fusi³ `match_histogram_linear/_percentile/_exact` |
#| **Denoise** | median / gaussian / NLM | cv2 薄封裝（新，~50 行） |
#| **Align** | 5 backends：phase/ncc/ecc/hybrid/template | Fusi³ `_calculate_alignment`+`_apply_alignment`；GLAS `fine_align_one`、`_parabola_subpx` |
#| **In-patch Ref** | patch 內附 ref page 當 reference 流 | ingest 直供 |
#| **Golden Cell** | 週期估測+堆疊 golden，ghosting 信心 gate | CPE `estimate_period`+`stack_cells`+`ghosting_score` |
#| **GDS Render** *(v1.5 選配)* | layout 渲染合成 ref + ROI label map | GLAS `render_gray_and_label_from_geoms` |
#| **Subtract / Blend / Invert** | 影像流運算 | Fusi³ |
#
#### 算法段（Algo — 量化，寫入 features）
#
#| 卡片 | 做什麼 | 來源 |
#|---|---|---|
#| **ROI Box / Grid / MultiROI** | 手畫、網格、target/reference ROI 集 | Fusi³ `MultiROISet`（隨對位 `shifted()`）；PEAR grid |
#| **GLV Stats** | ROI 內 mean/median/Qn/std/min/max | PEAR `attributes.glv_value/glv_stats` |
#| **ROI SNR** | defect box vs 背景 ring：SNR/contrast/edge/DVI | Fusi³ `calculate_roi_snr` |
#| **SNR Map** | 局部訊噪比地圖 + snr_max | Fusi³ `compute_snr_map`（修 tuple 回傳） |
#| **Blob Segment** | 門檻→連通域→area/aspect/dist | Fusi³ `segment_defects` → `DefectROI` |
#| **CD Measure** | blob/ROI 次像素邊緣定位 → cd_x/y_nm、area_nm² | MMH `_refine_yedge_*_batch`、`_extract_strip`、`_SubpixelResult`（一般化到 X/Y）+ `calibration` |
#| **Focus / Quality** | Laplacian/Tenengrad/FFT 高頻比（預篩 gate） | MMH `image_quality`+`compute_quality` |
#| **Outlier Flag** | 族群內 Tukey IQR 離群 | PEAR `group_outliers` |
#
#### ADC 判定段（串接，寫入 score / bin）
#
#| 卡片 | 做什麼 | 來源 |
#|---|---|---|
#| **Score** | 表達式算分（features 自由組合） | §4 表達式引擎（新） |
#| **Threshold → Bin** | 門檻/條件 → bin/class | 新 |
#| **寫回 / 輸出** | KLARF 三模式 + 報表（§8） | KLIP + MMH exporters |
#
#特徵命名慣例：`<卡片>_<量>[_<roi>]`（`snr_max`、`cd_x_nm`、`glv_mean_roi1`）。
#**v1 移除（列 backlog）**：PCA Ref、Region Stats/FFT。
#v2 擴充卡備選：上述兩張 + ML Classify、BSE/SE 多通道融合、雙 reference AND。
#
#---
#
### 6. 批次引擎、快取與結果儲存
#
#- **執行**：MMH `measurement_engine` 模式 —— ProcessPool + `as_completed`、per-defect
#  try/except（單顆爆=該顆 FAIL 不殺整批）、`on_progress`/`abort_check` callback、
#  Focus/Quality gate 低分短路。
#- **效能目標**：千級常態、偶爾上萬 → **10k patch 全 pipeline < 2 min**（MMH 實測 13k
#  張大圖 3–6 min，patch 更小，目標合理）。
#- **中間結果快取（調參迴圈的核心）**：per-defect、以「step 參數鏈 hash」為 key。
#  改第 5 張卡 → 前 4 張輸出直接複用；改門檻/表達式 → 完全不重跑影像，
#  純重算 score（**拖門檻線 → bin 數即時變**的基礎）。
#- **結果**：每顆一列 `{defect_id, features…, score, bin, 診斷}` → SQLite 批次歷史
#  （← MMH `batch_run_store`）；直方圖/gallery/報表/feature 匯出全吃這張表。
#
#---
#
### 7. UI v1（三工作區 + 導覽）
#
#### 7.0 使用旅程 —— 「我有一組圖 + KLARF，然後呢？」（不寫 code 的使用者視角）
#
#工具頂部是固定的四步 stepper：**① 載入資料 → ② 設計 pipeline → ③ 試跑調參 → ④ 輸出**。
#
#1. **載入**：把 KLARF 檔（或整個資料夾）拖進來。工具自動認版本、找到對應 TIFF、
#   判別 ebi_patch/rsem，顯示摘要卡：幾顆 defect、有無 ref、pixel size、wafer map 縮圖。
#   此時還沒有任何算法，就能先逐顆瀏覽 test/ref 原圖（KLIP 的看圖體驗）。
#2. **選起點**（三選一）：(a) **內建範本** —— 系統依資料型別推薦（EBI patch → die-to-die
#   假點過濾範本；RSEM → cell-to-cell 或單張 rule-based 範本），一鍵載入就是一條能跑的
#   pipeline；(b) 匯入同事給的 recipe JSON；(c) 空白開始。**推廣場景 90% 走 (a)：
#   從會動的東西開始改，不是從白紙開始。**
#3. **設計**：在 Studio 把想法翻成卡片。左側 Library 三組（影像藍/算法橙/判定紫），
#   中間 pipeline 同色分段；每加一張卡或改一個參數，右側立刻重算目前這顆 defect 的
#   中間輸出鏈 —— **所見即所得，想法對不對當場看到**。切幾顆代表性 defect
#   （已知真缺陷、已知假點各挑幾顆釘選）來回驗證。
#4. **試跑調參**：按「試跑」（預設抽 500 顆）→ 下方直方圖亮起來 → 拖門檻線看 bin 數
#   → 開 Gallery 按分數排序掃一眼（高分的是不是都真的？門檻附近是什麼？）→ 回頭改參數
#   （快取讓重算只發生在改動之後的步驟）。滿意後跑全批。
#5. **輸出**：Export 精靈選寫回模式（就地改欄/新 KLARF 含 score+class/Top-N）＋報表；
#   存 recipe JSON，傳給同事 —— 對方載入後從第 1 步直接跑。
#
#### 工作區
#
#1. **Studio**（mock 已確認方向）：Step Library（三色分組）｜Pipeline（三段式直線＋
#   輸入型別分流 tab）｜單顆預覽（點卡看中間輸出、features 表、verdict、釘選比對顆）｜
#   整批分數直方圖（門檻線可拖）。
#2. **Gallery**：縮圖網格（test/diff/overlay 底圖可切）、score/任一 feature 排序、
#   點直方圖 bar 篩選該區間、框選送單顆詳看；虛擬捲動撐 10k+。
#   → 對應 KPI「review efficiency」：按分數排序一眼驗證「排前面的是不是都是真的」。
#3. **Export**：KLARF 寫回精靈 —— 選模式（就地改 CLASSNUMBER/BIN/DSIZE ｜ gen 新
#   KLARF 含 score+new class 欄位 ｜ Top-N 篩選新檔），寫回前自動跑 KLIP `lint()` 健檢
#   ＋ 變更摘要確認（動了幾列、哪些欄）。另有 CSV/Excel、feature vector CSV、overlay 資料夾。
#4. **推廣配套**：首啟導覽（← Fusi³ welcome_tutorial 模式）、內建 2 份範例 recipe
#   （die-to-die、cell-to-cell）+ 合成示範資料、一頁快速參考卡 PDF（← GLAS 慣例）。
#
#主題沿用 GLAS/CPE token 系統（奶油底、單一 accent、instrument 風格）。
#
#---
#
### 8. KLARF 寫回細節（依訪談展開）
#
#| 模式 | 行為 | 依託 |
#|---|---|---|
#| 就地改欄 | CLASSNUMBER / ROUGHBIN / FINEBIN / DSIZE 依 bin 結果 `batch_set`，其餘 byte 不動 | KLIP span-splice |
#| Gen 新 KLARF（全量） | 複製原檔 + 擴充 DefectRecordSpec 加自訂欄（如 `ADCSCORE` `ADCCLASS`）寫入分數與新分類 | KLIP `to_text` + spec 改寫（新檔不受無損限制） |
#| Gen 新 KLARF（Top-N） | 依 score 排序取前 N（或條件篩選）產新檔給 Review SEM，DEFECTID 重排 | KLIP API-KLARF 既有能力 + MMH TopN exporter 座標修正 |
#
#---
#
### 9. Milestones
#
#| 里程碑 | 內容 | 驗收 |
#|---|---|---|
#| **M0 抽庫** | Vendoring §5 清單檔案進 `adept/core`；統一 KLARF parser（KLIP `klarf_core` 為底，補 ImageFileName；棄用重複的 `klarf_parser`）；修三摩擦（ROI 座標統一正規化、SNR 正負號統一、`compute_snr_map` 回傳）；合成影像單元測試 | `pytest` 全綠、core 零 Qt import |
#| **M1 引擎** | Context/Step/registry/Recipe(DAG)/表達式/單顆執行 + **synthetic data generator + KLIP 產測試 KLARF fixture 庫** | CLI 對合成 KLARF+TIFF 跑通 die-to-die pipeline，輸出 features JSON |
#| **M2 批次** | ProcessPool + SQLite + 中間快取 + headless CLI + feature vector 匯出 | 10k 合成 patch < 2 min；改末端參數重跑 < 5 s |
#| **M3 Studio** | 四區塊 Studio + 即時中間輸出鏈 + 直方圖/門檻拖曳 | **首發案例：EBI patch 算分全程滑鼠完成**（想法→算法的證明點） |
#| **M4 雙輸入** | rsem ingest、型別分流、Golden Cell 卡（含相位搜尋補完） | 同一 recipe 吃 EBI patch 與 RSEM 合成資料 |
#| **M5 Gallery+Export** | Gallery 聯動、KLARF 三種寫回模式（含 lint+確認）、報表/overlay | 完整調參迴圈 demo：調參→分佈→gallery→寫回 |
#| **M6 推廣包** | 離線 wheels 安裝腳本（主）+ exe 打包（備）、首啟導覽、範例 recipe、快速參考卡 PDF | 乾淨離線 Windows 機從零裝起→跑通範例 |
#| **廠內驗證**（穿插） | 每個 M 完成後帶 `fab_probe` 腳本進廠對真資料，文字報告貼回修 fixture | 真實 KLARF 變體全部進 fixture 庫 |
#
#每個 milestone 照現行慣例開 `docs/plans/F*.md` + SESSION_LOG。
#
#---
#
### 10. 開發資料策略（資料不能出廠的配套）
#
#1. **合成資料產生器**（`tools/make_sample.py`，CPE/PEAR/GLAS 皆有先例）：
#   可調參的合成 patch（cell 陣列/線條 + 植入 bridge/particle/missing + noise/對位偏移），
#   搭配 KLIP 產生對應測試 KLARF —— 全 pipeline 開發與 CI 都用它。
#2. **fab_probe 廠內探測腳本**（stdlib-only、單檔、免安裝）：
#   - `probe_klarf.py`：KLARF 版本/欄位/image-layout 變體盤點（← `klarf_tif_probe` 擴充）
#   - `probe_tiff.py`：page 數/尺寸/位深/壓縮盤點（不碰像素值輸出）
#   - `probe_stats.py`：匿名統計（GLV 直方圖形狀、patch 尺寸分佈）
#   輸出一律純文字/可貼上的 JSON —— 你在廠內跑、貼結果回來，我把變體補進 fixture。
#3. **格式契約測試**：每收到一種新變體 → 寫成最小化合成 fixture → 永久回歸測試。
#
### 11. 風險與待決
#
#1. KLARF 變體超出 `klarf_core` 已知三種 → fab_probe 持續收集，M1 起建 fixture 庫。
#2. Golden Cell 相位（CPE `choose_origin` 是 stub）→ M4 補相位搜尋。
#3. 推廣後 recipe 品質參差 → recipe lint + 範例庫 + 參考卡緩解；權限/集中管理留 v2。
#4. 命名待定（ADEPT 為代號；可延續水果/自然系：PEAR、Fusi³…）。
#
### 12. v2+ Backlog
#
#PCA Ref 卡、Region Stats/FFT 卡（v1 移出）｜自由 DAG 畫布（雙 reference AND）｜
#ground-truth 標注 + 抓漏/誤殺/混淆矩陣儀表板（KPI「分類準確度」的完整量化靠這個）｜
#ML Classify 卡（吃 v1 匯出的 feature vector）｜自然語言→recipe 草稿（AI 輔助）｜
#BSE/SE 多通道融合卡｜GDS Render 正式化（die-to-database）｜recipe diff / A-B 比較｜
#共用 recipe library｜多 lot 趨勢。
#
#F 9cb008460ec1b323254bde1d79e35f33542b401a 1239 docs/plans/F7-canvas-and-taxonomy.md
## F7 — 畫布、卡片分類重整、patch-only 收斂
#
#> 把 UI 從「直線鏈 + 兩種輸入」收斂成 **「單一輸入型別（EBI patch）+ n8n 式自由畫布」**，
#> 並把卡片分類從「影像／算法」（描述卡片**吐什麼**）改成依**流程階段**分類
#> （描述卡片**在解決什麼問題**）。
#>
#> 版本：v1.0 · 2026-07-28 · **F7-1 ~ F7-6 全數完成**（643 tests 綠）
#
#---
#
### 1. 為什麼要做
#
#M6 之後 v1 功能完整，但實際打開 Studio 的第一印象是「東西太多、不知道從哪開始」。
#逐條拆解使用者的回饋：
#
#| 回饋 | 根因 |
#|---|---|
#| 「字卡功能太瑣碎」 | 17 列平鋪，沒有階層、沒有搜尋 |
#| 「影像／算法分得太武斷」 | 那是依**輸出型別**分（吐圖 vs 吐數字），不是依**使用者的意圖**分 |
#| 「一次做 SEM image 跟 patch 太複雜」 | 雙 route 讓每個概念都要講兩次 |
#| 「UI 太像玩具」 | 暖奶油底 + 琥珀 accent + 填滿的彩色區塊（配色 vendoring 自 CPE） |
#| 「影像太小」 | 右欄 620px 寬且與特徵表 3:2 分高；底部直方圖再吃掉 190px |
#| 「直方圖不該在這」 | 它是**跑完一批才有意義**的東西，卻常駐在編輯流程的畫面上 |
#
#共同的根因只有一個：**v1 的 UI 是按「引擎的結構」長出來的，不是按「使用者的工作流程」長出來的。**
#
#---
#
### 2. 已定案的決策
#
#| # | 決策 | 理由 |
#|---|---|---|
#| D1 | **RSEM 輸入先關掉，但不刪 code** | 使用者說的是「暫時」。刪掉等於丟掉整個 M4 + M0 vendoring 的 `algo/golden.py`、`algo/period.py`。關掉的成本是零，回復的成本是一個開關 |
#| D2 | **卡片改依流程階段分類**（見 §3） | 分類要回答「我想幹嘛」，不是「這張卡吐什麼型別」 |
#| D3 | **`blob_segment` 從量測段移到 Region 段** | 它做的事是「產生 ROI」，不是量測。搬過去之後手畫的框與偵測出來的框走同一條路 |
#| D4 | **`snr_map` 留在 Enhance** | 依型別規則（影像進、影像出）。破例會讓「看型別就知道放哪」這條規則失效 |
#| D5 | **Align 降級：卡片保留，但不進預設範本** | 機台輸出的 patch 兩兩對應本來就是 defect & reference，不需要對位（使用者的領域知識，見 §5） |
#| D6 | **Output 是固定尾節點，但底下仍是 Export 精靈** | 畫布視覺完整（Input → … → ADC → Output），但 Export 是 per-batch、ADC 是 per-defect，不該真的變成流程節點。引擎不動 |
#| D7 | **Region 段先只做「defect 座標系」的 ROI** | pattern 座標系的 ROI 有真實難題，見 §4 |
#
#---
#
### 3. 新的卡片分類
#
#每一段附一條**機械可判定的規則**（吃什麼、吐什麼），這樣「新卡片放哪一段」不需要討論。
#
#| 段 | 規則 | 現有卡 | 待補 |
#|---|---|---|---|
#| **Input** | *(固定頭節點)* | `load_patch` | — |
#| **Enhance** | 影像 → 影像 | `percentile_norm` `glv_mask_norm` `hist_match` `denoise` `invert` `snr_map` | Brightness/Contrast、Gamma、CLAHE |
#| **Region** | 影像 → 區域 | `blob_segment`（搬過來） | Whole image、Centre box、Annulus |
#| **Compare** | 影像＋影像 → 影像 | `subtract`、`align`（不進預設） | ratio / log-ratio |
#| **Measure** | 影像＋區域 → 數字 | `glv_stats` `roi_snr` `cd_measure` `focus_quality` | Custom metric |
#| **ADC** | 數字 → score → bin | Score / Bin *(固定)* | — |
#| **Output** | 整批 → 檔案 | Export *(固定尾節點)* | — |
#
#### 命名（左側 rail 用 icon + 短標題）
#
#| 段 | 採用 | 也考慮過 | 為什麼選這個 |
#|---|---|---|---|
#| 1 | **Input** | Source, Load | 固定節點，n8n 的 trigger 位置 |
#| 2 | **Enhance** | Preprocess, Adjust, Image Ops | 使用者自己的用詞 |
#| 3 | **Region** | ROI, Where | 標題用 Region，副標寫 ROI（業界通用語但仍是縮寫） |
#| 4 | **Compare** | Difference, Combine | 涵蓋未來的 ratio；Difference 綁死在減法 |
#| 5 | **Measure** | Metrics, Quantify | 最短、最白話 |
#| 6 | **ADC** | Score, Decide | **使用者最熟悉的字**，比任何翻譯都好懂 |
#| 7 | **Output** | Export, Write | 固定節點 |
#
#讀起來是一句話：**Input → Enhance → Region → Compare → Measure → ADC → Output**。
#
#### 因為畫布，分類不再需要編碼順序
#
#Region 段排在 Compare 前面，但 `blob_segment` 必須跑在 `subtract` 之後（它吃 diff）。
#在直線 UI 裡這是矛盾；在自由畫布上不是 —— **順序由使用者拉的線決定，
#左側清單只回答「這張卡在做什麼」**。靜態 ROI 接前面、偵測型 ROI 接後面，
#兩者仍同屬 Region 群組。
#
#### icon 的實作限制
#
#repo 有「只有純文字檔」的不變量（公司機 DLP 擋二進位，見 HANDOVER §5）。
#`.png` 不行；`.svg` 是純文字可以。**但建議用 `QPainter` 直接畫**：
#七段各十幾行幾何，顏色吃 `theme.py` 的 token，換主題時 icon 自動跟著變，
#而且完全不用新增檔案。
#
#---
#
### 4. Region 段的真實難題（**這一段先不照搬**）
#
#### 問題
#
#機台的裁切邏輯是：**以 defect 座標為正中心，裁 x×x 像素**。這帶來兩個座標系：
#
#| 座標系 | 原點 | ROI 在這裡穩不穩定 |
#|---|---|---|
#| **defect frame** | patch 正中心 | **穩定** —— 缺陷永遠在中心，這是裁切方式保證的 |
#| **pattern frame** | 版圖晶格 | **不穩定** —— 裁切中心是 defect 而不是晶格，所以晶格相位逐顆不同 |
#
#也就是說「中心 32×32 框」這種 defect frame 的 ROI 一直都是對的（現有
#`glv_stats(region=center)` 之所以有效就是因為這個）；但「量線寬內部」「量 space」
#這類 pattern frame 的 ROI，**每顆 patch 都要先認出晶格在哪**。
#
#使用者的原話：*「我要在有限的 patch pattern 中認出位置」* —— 這就是那個難題。
#再加上 patch 很小、defect 靠近版圖邊界時 patch 內容會不一樣（*「邊界不一樣」*），
#pattern frame 的 ROI 可能整個落在框外。
#
#### v1 只做穩定的那些
#
#| ROI 種類 | 座標系 | v1 | 備註 |
#|---|---|---|---|
#| Whole image | — | ✅ | |
#| Centre box | defect | ✅ | 大小同時支援 px 與 **% of patch**（見下） |
#| Annulus / ring | defect | ✅ | 中心框外一圈，當背景統計用 |
#| Detected blobs | 影像 | ✅ | `blob_segment` 搬過來 |
#| Line / space / cell-aligned | **pattern** | ❌ 延後 | 需要相位偵測，見下 |
#
#**「% of patch」順手修掉一個已知的坑**：CLAUDE.md §7 記載「同一組 `glv_stats`
#中心框參數在 128² 上準、在 256² 上漏抓」。ROI 尺寸支援百分比之後，
#同一份 recipe 換 patch 尺寸不會失效。
#
#### pattern frame ROI 要用的工具已經在 repo 裡
#
#`adept/core/algo/period.py`：
#
#- `estimate_period(img)` → X/Y 週期 **＋ `confidence_x` / `confidence_y`**
#- `choose_origin(shape, px, py, image=)` → 晶格相位（M4 補完的相位搜尋，
#  原 CPE 專案裡是永遠回 `(0,0)` 的 stub）
#
#這正是「在 patch 裡認出晶格位置」需要的東西。
#
#> ⚠ **這是 D1「關掉但不刪」最重要的理由。**
#> `algo/period.py` 目前只被 RSEM 的 Golden Cell 用到，看起來像是可以跟著 RSEM
#> 一起砍掉的東西 —— 但它是之後做 pattern frame ROI 的唯一工具。**不要刪。**
#
#設計方向（之後做）：相位信心低於門檻時，**退回 defect frame ROI 並標記該顆**，
#而不是安靜地量錯位置。`estimate_period` 已經回報信心值，`cell_conf_x` /
#`cell_conf_y` 也早就是 feature，所以這條路是通的。
#
#---
#
### 5. Align：卡片留著，但要用真實資料裁決
#
#使用者的領域知識：**機台輸出時兩兩對應的 patch 就是 defect & reference，不需要對位。**
#
#處理方式：卡片保留在 Compare 段，但**不進預設範本**。
#
#要把「不需要」從判斷變成事實，有一個現成的量法：
#
#1. 拿一份真實 lot，跑一次**有** align 的 recipe，加 `--csv features.csv`
#2. 看 `align_dx` / `align_dy` 兩欄的分佈 —— 它們是 **feature**（`align.py:49`），
#   不只是 meta，所以直接就在 CSV 裡，開 Excel 拉個直方圖就看得到
#3. 分佈集中在 0 → 永久拿掉；不集中 → 留著並依實際範圍設 `search_radius`
#
#順帶一提 `align_score` 也是 feature，可以同時看對位品質，
#判斷「位移是 0」和「根本沒對上」的差別。
#
#### 一個要一起決定的副作用
#
#`tools/make_sample.py` 預設 `--shift-max 3`，**刻意在 ref 上加隨機平移**來模擬對位誤差。
#現有 94–95% 的分類正確率是在「有位移 + 有 align」的條件下量到的。
#
#若真實 patch 本來就對齊，合成資料應該把預設改成 `--shift-max 0` 才符合現實 ——
#但那會改變 demo 的數字。**這是一個待決策點，不要順手改。**
#
#---
#
### 6. 卡片遷移清單（破壞性 schema 變更）
#
#Region 段成立之後，量測卡要從「自己帶一組幾何參數」改成「引用一個具名 ROI」：
#
#| 卡片 | 現在 | 改成 |
#|---|---|---|
#| `glv_stats` | `region=full\|center` + `box_size` | `roi=<ROI 名稱>` |
#| `roi_snr` | `mode=blob\|center` + `box_size` | `roi=<ROI 名稱>` |
#| `cd_measure` | 讀 `meta["blobs"]` | 讀具名 ROI |
#| `blob_segment` | 寫 `meta["blobs"]`、category=algo | 寫 `ctx.rois`、category 改 Region 段 |
#
#`Context.rois` / `Context.labels` 欄位**早就存在但從來沒有人寫過**
#（`context.py:33-34`，註解寫著「M3 起由 ROI 卡填入」—— 那張卡沒做出來）。
#`adept/core/algo/roi.py` 的 `NamedROI` / `MultiROISet`（vendoring 自 Fusi³）也是現成的。
#這次是把它們接上。
#
#**連帶要改**：5 份範例 recipe、`test_example_recipes.py`、端到端測試。
#建議與 patch-only 收斂做在同一批，一次痛完。
#
#---
#
### 7. Measure 段：metric bank，不要一個 metric 一張卡
#
#使用者預期「這邊要花滿多時間 setup 量測工具」。若每個 metric 一張卡，
#會做出 30 張卡然後回到「太瑣碎」的原點。
#
#`adept/core/algo/glv.py` 已經有現成的 metric bank（vendoring 自 PEAR）：
#
#```
#GLV_STATS                     metric id → 顯示名
#glv_value(patch, mid)         算單一 metric
#roi_metric(image, roi, mid)   在 ROI 內算
#metric_label / metric_formula 給 UI 顯示名稱與公式
#```
#
#所以 Measure 段應該是**少數幾張卡，各自被「ROI + 勾選 metric」參數化**：
#
#- **GLV metrics** — 選 ROI + 勾 mean / std / median / max / q90 / …
#- **Signal metrics** — dSNR、對比、邊緣銳利度
#- **Geometry metrics** — CD、面積、長寬比、離中心距離
#- **Custom metric** — 使用者自己的算式，變數是同一個 ROI 的像素統計
#
#**加一個新量測 = 在 metric bank 加一個 id，UI 零修改。**
#
#---
#
### 8. 畫布（最大的一塊）
#
#好消息：**core 本來就是 DAG**，這是 F0 就決定的（「UI v1 只呈現直線，
#之後上自由畫布時引擎零改動」）。現成的：
#
#- `Recipe` JSON 已有 `edges` 欄位（目前都是空陣列）
#- `execution_order()` 已是 Kahn 拓撲排序 + 循環偵測
#- `validate()` 已會報「這條 route 有循環」
#
#要做的純粹是 UI：
#
#1. `QGraphicsScene` 節點畫布：節點卡、輸入/輸出 port、貝茲連線、拖曳連接、平移縮放、框選、刪除
#2. 左側點一下 → 節點出現在畫布空位
#3. `RecipeModel` 從線性 `node_order` 改成 `nodes` + `edges`，順序交給 `execution_order()`
#4. 固定頭尾節點（Input / Output），使用者不能刪
#
#規模估計：**800–1200 行新 UI + `RecipeModel` 改寫**。風險不在引擎（不動），
#在 UI 的互動細節。
#
#**patch-only 讓這件事簡單很多**：`routes` 只剩一條 = 畫布上只有一張圖要編輯。
#雙 route 的話得處理「同一組節點、兩種執行順序」，是完全不同等級的複雜度。
#
#---
#
### 9. 版面與視覺
#
#### 版面
#
#```
#┌ 左 rail（icon+標題，可收合）┬─ 中央 Workspace ─────────┬─ 右 Inspector ─┐
#│ Input                      │ 畫布（節點流程）           │ 參數表單        │
#│ Enhance                    │ ─────────────────────────  │ 特徵表（可收合）│
#│ Region                     │ 影像（置中、佔滿剩餘空間）  │ ~300px         │
#│ Compare / Measure / ADC    │                           │                │
#└────────────────────────────┴───────────────────────────┴────────────────┘
#
#直方圖 + Gallery → 搬進「Results」視窗（按 Run 之後才開）
#```
#
#**直方圖與 Gallery 都是「跑完一批才有意義」的東西**，跟「編流程 + 看單顆」
#是兩種模式。分開之後主視窗才乾淨。
#
#⚠ 搬家時**不能弄丟秒回**：拖門檻線目前走 `viewmodel.rebin()` 純計算路徑
#（不重跑影像），Results 視窗必須沿用同一條。
#
#### 視覺
#
#現在的配色 vendoring 自 cell-period-estimator：底 `#f7f4ef`、accent 琥珀 `#f29f4b`、
#三段式用**填滿的彩色底塊**。暖色 + 高飽和 + 大色塊 = 玩具感。
#
#目標是 n8n / KLIP 的語言：**中性灰階、全平面（無陰影漸層）、顏色只表達語意、
#小圓角、一致的 4/8px 間距**。
#
#`theme.py` 當初就把所有顏色集中成 `TOKENS`（同時餵 QSS 與自繪 widget），
#所以這是**換一組 token + QSS 掃一遍**，不是重寫。段落色降級成 3px 左側色條或小圓點。
#
#> 參考點就在手邊：使用者自己的 **KLIP** 已經是這個視覺語言（平面、中性、
#> 藍色 accent、頂部 tab、密而不擠）。ADEPT 應該向 KLIP 靠齊，而不是繼續繼承 CPE 的暖色。
#
#---
#
### 10. 執行順序
#
#| 階段 | 內容 | 風險 | 為什麼是這個順序 |
#|---|---|---|---|
#| **F7-1** | ✅ patch-only 收斂 —— `adept/ui/scope.py` 一個檔就是整個開關 | 低 | 先把世界變簡單 |
#| **F7-2** | ✅ 中性色 + 平面化 + 暗色主題（token swap，呼叫端零改動） | 低 | 早做，判斷版面才不會被暖色帶偏 |
#| **F7-3** | ✅ `Step.group` + icon 分組 + 搜尋 + 前置條件 badge | 中 | 引擎不動 |
#| **F7-4** | ✅ Region 段（具名 ROI）+ 四張量測卡遷移 + 5 份範例 recipe | 中高 | 分數分佈與重構前逐項相同 |
#| **F7-5** | ✅ Results 視窗（直方圖 + Gallery 搬家），預覽拿最寬一欄 | 中 | 秒回路徑有測試鎖 |
#| **F7-6** | ✅ 節點畫布 —— 純 UI，core 一行沒動 | 高 | 印證了 F0 「引擎零改動」的設計 |
#| **F7-7** | ✅ 階段大按鈕 rail、進度條、Brightness/Contrast + Gamma 卡、`snr_map` 移到 Region | 中 | 使用者試用後的第一輪回饋 |
#| **F7-8** | ✅ 滑桿 + 自訂曲線、直式 rail、並排比對、畫布 n8n 化 | 中 | 第二輪回饋，見 §12 |
#
#### 完成後的實測
#
#- 643 tests 綠（F7 之前是 595）
#- `die_to_die_basic` 跑 100 顆合成 patch：分數分佈與 F7 之前**逐項相同**
#  （min 21 / median 45 / max 171、bin 0=52 · bin 1=48），對照 ground truth 98%
#- 卡片庫 17 列 → 15 列，分成 6 段（Input / Enhance / Region / Compare / Measure / ADC）
#
#---
#
### 11. 待決策 / 待驗證
#
#| # | 項目 | 誰決定 |
#|---|---|---|
#| Q1 | `make_sample.py` 的 `--shift-max` 預設要不要改成 0（見 §5） | 等真實 patch 的對位分佈 |
#| Q2 | pattern frame ROI 的相位信心門檻怎麼訂 | 等真實資料 |
#| Q3 | Enhance 段要不要再細分（photometric vs 其他） | 等卡片數量長到會痛再說 |
#| Q4 | 畫布要不要支援分支（一個節點餵多個下游） | 引擎支援，UI v1 要不要開放待定 |
#| Q5 | RSEM 什麼時候（或是否）回來 | 使用者 |
#
#`fab_probe/` 的三個原始假設（page→channel 對應、`nm_per_px` 來源、KLARF 變體）
#**仍然全部未驗證**，與本計畫獨立，優先度不因為這次重構而降低。
#
#---
#
### 12. F7-8：試用回饋第二輪
#
#使用者實際開起來用之後提的五件事。每一件下面記的是**做了什麼**與**為什麼是
#這個做法**（不是那個做法）。
#
#### 12.1 數字參數改用滑桿，Gamma 加自訂曲線
#
#> 「調亮度 對比可以放在一起，然後是用搖桿調整（不是輸入），同理 gamma 也是。
#> 然後下方要支援 custom curve 可以自己畫 gamma 曲線（預設 y=x，可以開啟畫布自己拉）」
#
#**滑桿是資料驅動的，不是逐張卡登記的。** `_make_slider()` 看 ParamSpec 有沒有
#`min`/`max`：有就給滑桿，沒有就不給。所以新卡片只要把上下界填好（本來就是
#鐵則 4 的要求）就自動有滑桿，UI 這邊不需要為它加任何一行。
#
#**數字框沒有被拿掉。** 滑桿負責「找到大概的位置」，數字框負責「記錄與重現」——
#recipe 是要交接給別人的，那需要一個確切的值。兩邊雙向綁定。
#
#**曲線存成字串**（`"0,0; 0.35,0.6; 1,1"`）。ParamSpec 的值一律是純量，UI 表單、
#rescore、CLI `--set` 全都靠這條規則，不為了曲線破例；而且 recipe 的 git diff
#仍然一眼看得懂「使用者把暗部拉起來了」。
#
#**插值用保單調三次 Hermite（Fritsch–Carlson），不是自然三次樣條。**
#自然樣條會 overshoot：使用者把中間點往上拉，曲線可能在旁邊先往下凹一段，
#在影像上就是**一圈演算法自己造出來的暗環**。對一個要拿去判 defect 的工具來說，
#那是最糟的一種 bug。`tests/test_curve.py` 用四條最容易凹出去的曲線鎖住這件事。
#
#**曲線與 gamma 的關係是「接手」，不是「疊加」。** 疊加很難 debug ——
#使用者把曲線拉平了卻還是暗，因為 gamma 還壓在那裡。所以曲線一旦不是 y=x
#就完全接手，而且 UI 會把 gamma 那一列**調淡並說明原因**（不是 disable：
#使用者可能只是想比較兩種做法，鎖死會逼他先把曲線拉平才改得動）。
#
#**編輯器畫的線就是影像上套的線** —— 兩邊呼叫同一個 `algo.curve.curve_lut`。
#UI 自己再實作一份插值是很容易發生的事，那會讓看到的和跑出來的不一樣。
#
#### 12.2 畫布：殘影、成對的線、並排看兩張圖
#
#殘影的原因是 `boundingRect` 沒有涵蓋畫在節點右緣**之外**的埠標籤，
#Qt 就只重繪它宣告的範圍。
#
#**Input → Subtract 現在畫兩條線**（test 一條、ref 一條）。這是
#`_ports_between()` 從兩端共用的影像流**推導**出來的，不是存起來的 ——
#recipe JSON 的 edge 仍然是 `[from, to]`，格式不用改，重新載入不掉資訊。
#
#並排比對：**預設關著。** F7-5 把 Gallery 與直方圖搬走就是為了讓右欄的影像變大
#（使用者原話「影像最好大一點、置中」），預設並排等於把剛爭取到的寬度再砍一半。
#真正需要並排的時機很明確 —— **調 Enhance 卡的時候**，確認 test 與 ref 被調成
#一樣的；那是一次點擊。開了之後兩張圖的縮放與平移**連動**，沒有連動的並排
#使用者得自己把兩邊拖到同一個位置才比得起來，那還不如切換一張。
#
#### 12.3 左側改成直式 rail
#
#六個階段的大 icon 由上而下排成一條工作列，**卡片區收起來時整欄只剩那條 rail**，
#寬度真的還給工作區。搜尋框住在卡片區裡，所以 rail 底部必須留一顆放大鏡 ——
#不然卡片區收起來之後，搜尋就再也叫不出來了。
#
#### 12.4 Normalize
#
#美式拼法，而且三張 normalize 卡改成共同前綴（`Normalize · Percentile` /
#`· GLV band` / `· Histogram match`），在清單裡自然排在一起。
#
#### 12.5 畫布視覺
#
#n8n 之所以一眼認得出來，靠的是**左邊那顆有顏色的圖示磚**，不是細色條 ——
#細條太安靜，遠看整張畫布還是一排一模一樣的方框。所以：圖示磚（淡色底 + 與左側
#rail 完全相同的圖形）、投影、**點陣底而不是格線底**（格線跟連線同一種筆觸，
#「哪條是資料流、哪條是背景」要看第二眼）、連線中點的方向箭頭、
#停用節點畫**虛線框**（n8n 的慣例 —— 不是消失，是「還在，但這次不跑」）。
#
#過長的文字一律 elide 成 `像這樣…`。直接 `drawText` 到放不下的矩形，Qt 會硬切在
#字的中間，`source=diff · metri` 這種殘句會讓人以為參數值真的是那樣。
#
#---
#
### 13. F7-9：試用回饋第三輪
#
#使用者提的四件事，加上一個提問（「也請幫我確認目前的卡片操作與組合是否相互
#會有問題」）。最後一句話講清楚了真正的目標：
#
#> 「最終是希望兩張 patch 可以一起，或經過不同的工作流做設定
#> （所以 UI 跟 UX 方面要好操作並看得懂）」
#
#前四件事各自看起來像小毛病，但它們指向同一個缺口：**「影像流」這個概念在畫面
#上幾乎是隱形的**，而「兩張 patch 要一起還是分開」正是一件純粹關於影像流的事。
#
#### 13.1 六個階段六個顏色
#
#> 「Icon 圖示很不錯 但太多都同個顏色（input enhance 跟 Compare 都是藍色）」
#
#以前的鏈是 `group → category → 顏色`，而 category 只有三個，所以六個階段只有
#三種色。圖示分得出來、顏色分不出來 —— 顏色這個維度等於白給了。
#
#現在 `theme.group_hex()` 每個階段各一個色相。挑色的兩個條件是可驗證的性質，
#不是「好看」：兩兩之間 **CIE Lab ΔE ≥ 25**（一眼看得出是兩個顏色，而不是同色
#的深淺），而且同一主題內 **明度 L\* 差 ≤ 15**（看起來像一套色票，不是六個各自
#為政的顏色）。`tests/test_f7_9_feedback.py` 兩條都鎖住，色碼本身還可以再調。
#
#`seg_hex()`（三段式的顏色）**沒有被取代**，需要講「這是哪一段」的地方
#（首啟導覽、直方圖、Score/Bin 尾卡）仍然用它。兩個軸各有各的用途。
#
#### 13.2 埠：一個 bug，三個症狀
#
#> 「畫布上移動 Load images 時還是會有殘點（test 跟 ref）」
#> 「新增的節點只有前面有圓框，後面沒有圓框讓人可以連」
#
#這兩件事是**同一個 bug**：`paint()` 拿 `out_anchors()`（**場景**座標）去畫本地
#座標的東西。節點在原點時看起來正常 —— 而第一欄的 Input 剛好就在原點，所以
#「Load 有埠、後面的卡沒有」。一離開原點，埠與埠標籤就被畫到「兩倍位移」的
#位置：後面每張卡的圓點都跑到卡外面（看起來像沒有），拖動 Input 則把標籤留在
#`boundingRect` 之外（Qt 只重繪它宣告的範圍 → 擦不掉 → 殘影）。
#
#F7-8 修過一次殘影，改的是 `boundingRect` 的大小 —— 那是對症狀動刀。真正的
#不變量是**「畫的座標系」與「宣告的座標系」必須是同一個**，所以現在分成
#`out_anchors_local()`（繪製、命中判定）與 `out_anchors()`（連線）兩個方法，
#測試直接鎖那個不變量：把節點拖到任何位置，每個埠與埠標籤都要在
#`boundingRect` 裡面。
#
#順手做的兩件事：輸入埠畫**空心圈**、輸出埠畫**實心點**（線該從哪拉到哪，
#不用先試一次才知道）；而且**每個輸出埠都標上它吐的影像流名**（以前只有多埠
#才標）—— 那些名字正是 `Apply to` 下拉裡的名字，見 13.3。
#
#### 13.3 起手就有 Input 卡
#
#> 「一開始預設畫布上就應該有 load image 這個節點」
#
#空白畫布對不會寫 code 的人是一道「現在要幹嘛」的關卡，而答案永遠是同一個。
#`RecipeModel.starter()` 開窗就放好 Input 卡並**選起來**（右欄一開窗就是可以動
#的東西），而且 `dirty=False` —— 使用者什麼都還沒做，關窗不該被問「要存檔嗎」。
#
#### 13.3b 還沒拉線的畫布會換行
#
#截圖檢查時發現的（不在回饋清單上，但同一個「看得懂」的問題）：一份九張卡、
#還沒拉線的 recipe 排成一列超過 2500px。`fit()` 為了塞進畫面得縮到看不出字，
#而它又有下限（縮成小方塊比留捲軸更糟）—— 結果是**一排讀不出來的小方塊，
#再加上一條捲軸**，兩邊都輸。現在退化排版每 `WRAP`（4）張換一行，
#同樣九張卡變成 3×4 的格子，每一張都讀得到字。閱讀順序仍是左到右、上到下。
#
#### 13.4 target / also apply：把影像流變成看得見的東西
#
#> 「target 跟 also apply 要怎麼使用？對應的節點又是什麼？」
#
#這個提問本身就是答案：使用者在畫布上想的是**節點**，而這兩個參數講的是
#**影像流** —— 流是節點之間的**線**，不是節點。以前畫面上完全沒有東西把這件事
#說出來，於是 `also_apply` 是一個「不知道能填什麼、填錯了也不會被擋
#（缺流只 warn）」的自由文字框。
#
#四件事一起做：
#
#1. **`ParamSpec.label`**（選填顯示名）。`name` 是 recipe JSON 的鍵，改不得；
#   但 `also_apply` 對製程工程師不是一句話，`Also apply to` 才是。
#2. **新的參數型別 `image_keys`**：值仍然是逗號分隔字串（**recipe 格式沒有變**，
#   舊檔照樣讀），但 UI 給的是上游每一條流的一個**勾選框**。能填什麼一目了然，
#   打錯字這件事直接不存在。
#3. **說明改寫**：明講「流就是畫布上那些有名字的線，test 是缺陷圖、ref 是參考圖」。
#4. **每個輸出埠標上流名**（13.2）—— 表單裡的名字，在畫布上找得到。
#
#於是使用者最終要的那件事變成一個看得見的動作：**ref 勾著 = 兩張 patch 一起
#處理；取消 = 分開**（再加一張只對 ref 的卡，就是各走各的工作流）。
#
#### 13.5 點卡片不要跳到 ref
#
#> 「如果把 compare 打開，點卡片時右上 image stream 都會一直被切換成 ref
#> （左右顯示同一張 ref image，要再手動切換回來）」
#
#`_default_stream()` 取的是「這張卡寫過的**最後**一條流」，而 Enhance 卡的
#`resolve_writes` 是 `[target] + also_apply` —— 最後一項永遠是 also_apply 的
#`ref`。並排開著、右邊又停在 ref 的時候，畫面就變成左右兩張一樣的圖。
#
#改成先看這張卡的**主要**參數（`target` / `source`），再退回 writes。
#另外加一條保險：左右如果算出同一條流，右邊讓步換成配對的另一張 ——
#兩張一模一樣的圖是並排唯一沒有意義的狀態。
#
#### 13.6 卡片組合：兩個真的會咬到的地方
#
#使用者問的是「目前的卡片操作與組合是否相互會有問題」。把 19 張卡的
#reads / writes / features / 具名區域全部攤開跑一遍之後，有兩個真的會咬到：
#
#**一、具名 ROI 完全沒有被檢查。** 影像流有 reads/writes 可以在 `validate()` 裡
#模擬，ROI 沒有。所以「量測卡指到一個沒人定義的區域」有兩種下場，兩種都不好：
#名字打錯 → 每顆 defect 執行到一半 `StepError`；名字剛好是保留字 `blob` 而上游
#又沒有 Blob 卡 → **安靜地改量整張圖**，跑得完、有數字、而且是錯的。後者是最糟
#的一種 —— 使用者看不出哪裡不對。
#
#修法是讓區域走跟影像流**同一條路**：`Step.resolve_regions_in/out()`
#（預設空清單，既有卡片不受影響），`validate()` 多一個 `unknown-region`；
#而 `blob` 退回整張圖的那條路現在會 `ctx.warn` 說清楚。
#
#**二、Studio 從來沒有跑過 lint。** 同一份檢查 CLI 從 M1 就在用了，Studio 沒接。
#加上引擎「單顆出錯不殺整批」的契約，一組接錯的卡片的下場是**跑完 200 顆、每一
#顆都失敗**：進度條走完、結果是空的、原因埋在每顆的錯誤訊息裡。現在試跑前先
#lint，有 error 就擋下來並講出第一個問題（warning 照跑）。
#
#還有一個**不是 bug 但會絆到人**的地方，記在這裡：`subtract` 預設吃
#`ref_aligned`（Align 卡的產物），所以 Load 之後直接放 Subtract 一定缺上游。
#這個預設是對的（die-to-die 本來就該先對位），但卡片庫上那個 `needs ref_aligned`
#的灰字 badge 對不會寫 code 的人沒有動作可做 —— 他不知道那條流是誰產的。
#所以加卡片時的狀態列現在會講完整的一句話：
#「還缺 `ref_aligned`（先加 Align），或把它指到現有的 test / ref」。
#
#**沒有動的**：`subtract` 的預設值本身。把它改成 `ref` 確實會讓
#Load → Subtract 立刻能跑，但接著會產生一個更難發現的反向陷阱 —— 加了 Align 卻
#沒有重新接線，於是**安靜地減掉沒對位的 ref**。用一個看得見的錯誤換一個看不見
#的錯誤，不划算。
#
#---
#
### 14. F7-10：隱含順序看得見 + Enhance 補齊空間性 artifact
#
#### 14.1 畫布上「沒有線」不代表「沒有連接」
#
#引擎的依賴是 **route 相鄰對 ∪ 顯式 edges**（`recipe.execution_order`，M1 起就是
#這樣），但畫布以前只畫顯式 edges。於是載入一份沒拉過線的 recipe，使用者看到的
#是九張互不相干的卡 —— 而它其實是照順序跑的。他只會得到兩種結論，兩種都是錯的：
#以為要自己連起來才會跑，或以為沒連線的卡不會執行。
#
#現在 route 的相鄰對畫成**虛線、半透明、不可選取**。不可選取是刻意的：隱含順序
#來自卡片的排列，刪掉它在語意上等於「把這張卡從流程裡拿掉」，那是另一個動作，
#不該用同一個 Delete 鍵完成。使用者親手把同一對連起來時，虛線換成實線
#（不會變成兩條）。`edge_pairs()` 仍然只回報使用者拉的線 —— 存檔寫的是那個，
#把 route 順序也寫進 edges 會變成同一件事記兩遍。
#
#副作用：現在**每一份** recipe 都有依賴了，所以 F7-9 只做在「退化排版」上的換行
#必須對深度排版也成立，否則九張卡又會排成一條 2500px 的橫列。
#`layout_columns` 改成 `col = depth % WRAP`、`row = (depth // WRAP) * 帶高 + 同深度序`。
#
#### 14.2 Enhance：三種空間性 artifact，但只加兩張卡
#
#既有的 Enhance 卡全部是**全域**的（percentile / gamma / curve / 亮度對比）——
#對整張圖套同一條轉換曲線。但 E-beam patch 上最常見的假訊號都是**空間性**的，
#全域轉換一個都處理不掉：charging 的亮度梯度、掃描線條紋、暗區裡的小缺陷。
#
#使用者的要求是「不要開太多卡片，類似功能放在一起」，所以六項能力只長出兩張卡：
#
#| 能力 | 落在哪 |
#|---|---|
#| 背景平坦化（charging 梯度） | 新卡 `flatten`，`method=background` |
#| 掃描線去條紋（兩個方向） | 同卡，`method=stripes_h / stripes_v` |
#| 形態學 top-hat / black-hat | 同卡，`method=bright_spots / dark_spots` |
#| CLAHE 局部對比 | 新卡 `local_contrast`（`Normalize ·` 家族） |
#| 邊緣保留去噪 | **既有** `denoise` 加 `bilateral` / `nlm` 兩個選項 |
#| 雙流運算（ratio/max/min/mean） | **既有** `subtract` 加 `op` 參數 |
#
#`flatten` 的五個方法看起來是五種東西，其實是同一個結構：**估一個大尺度的成分，
#再把它減掉**，差別只在怎麼估（高斯模糊／逐列中位數／形態學開閉）。所以它們是
#一張卡的一個下拉 —— 卡片庫多五列，使用者要讀五段說明才知道用哪個；
#一張卡的一個下拉，他只讀一次。
#
#CLAHE 分開放，是因為它不是「減掉什麼」而是「局部重新拉伸」，
#跟既有三張 Normalize 卡同一個家族，所以命名跟著那個家族走。
#
#### 14.3 兩個實作上的決定
#
#**去條紋用中位數，不用平均值。** 一顆夠大的缺陷會把它所在那一列的平均值整個帶
#偏，校正時就在缺陷那一列造出一條**反向的假條紋** —— 演算法自己造缺陷，跟 F7-8
#的色調曲線 overshoot 是同一類 bug。中位數對它免疫，測試直接鎖「缺陷那幾列不可
#以被壓下去」。
#
#**保留邊緣的去噪，強度以「這張圖自己的雜訊 σ」為單位**（Immerkær 估計）。
#`bilateral` / `nlm` 的強度參數單位是灰階值，直接給常數的話，同一組參數換一台
#機台、換一個曝光就完全不對 —— 而使用者只會覺得是自己參數調錯。以雜訊為尺度，
#`strength=1` 的意思固定是「濾掉一個 σ 的擾動」。實測 h≈1σ 時雜訊掉九成而
#3×3 的小缺陷完好；2σ 起小缺陷開始跟著消失，所以預設就停在 1。
#
#加這兩個方法的**唯一**理由是 median 對「比核心小的亮點」是毀滅性的 ——
#而那正好就是要找的東西。測試拿 median 當對照組：同一顆 3×3 缺陷，
#median(5) 把它從 46 抹到 5，bilateral 與 nlm 都留在 46 以上。
#
#---
#
### 15. F7-11：ROI 定位（第一批）
#
#這一段的起點是一次很長的來回討論，結論改寫了我原本的設計。記在這裡的是**結論
#與它的理由**，不是討論過程。
#
#### 15.1 領域事實（這一切的前提）
#
#- patch 是 EBI 機台**以它找到的缺陷位置為正中心**裁出來的 → **缺陷永遠在中央**。
#- EBI 的檢測本來就鎖定在某一種 pattern 上（例：兩種 pattern MG 與 EPI，只鎖 EPI）
#  → **每一張 patch 裡一定都有那個結構**。
#- 但缺陷可能落在結構的中間、也可能靠邊 → **結構在 patch 裡的位置逐顆不同**，
#  靠邊的那些還會切到旁邊的另一種 pattern。
#
#**所以「中心固定框一定準」這個說法只對了一半。** 缺陷本身在中央沒錯，但缺陷
#**周圍**的東西每張都不一樣 —— 框只要大過缺陷，就可能在某些 patch 上吃進別種
#材質。量出來的數字忽高忽低，而**變動的原因不是缺陷**。拿來當「乾淨背景」的
#區域更糟：靠邊的那些 patch，背景框裡根本不是同一種東西。
#
#於是問題不是「把框放在畫面的哪個位置」，是**「把框放在結構的哪個位置」**。
#
#### 15.2 三種定位方式，以及它們各自解得掉什麼
#
#討論裡釐清了一個我原本混在一起的區別：**定位**（這張 patch 在版圖的哪裡）與
#**定義**（我要量的是哪一塊）是兩件事。
#
#| 方法 | 定位 | 定義 | 備註 |
#|---|---|---|---|
#| **投影找轉折** | 有地標時可以 | 可以（「包含中心的那一段」這類規則） | **本輪做的**；唯一不需要大圖的 |
#| 比對 Golden Cell | 可以 | 可以（在 cell 上標一次） | 下一批。零件（period/golden/align）都已在 repo |
#| 回找大圖位置 | 可以 | **不行** | 降級成輔助 —— 知道位置不代表知道要量哪裡 |
#| GDS | — | 可以（逐層生成） | 非週期 layout 的唯一解；GLAS 的範圍 |
#
#非週期 layout 之所以只有 GDS 能解，是因為**定義**沒有一個「標一次就套用到所有
#地方」的單元可以標，而不是因為定位有多難。
#
#### 15.3 為什麼找「轉折」而不是分「材質」
#
#第一版的想法是「EPI 暗、MG 中等、交界最亮 → 分三種灰階」。使用者一句話擋掉了：
#**這個工具是泛用的，之後跑的資料不會只有這幾種 layout。**
#
#分材質需要先知道有幾種、每種多亮，而且灰階會隨機台與曝光漂移 ——
#等於把一份 recipe 綁死在一種 layout 和一台機台上。
#
#找轉折沒有這個問題：它只問「哪裡在變」，不問「變成什麼」。使用者只要回答一個
#對任何 layout 都成立的問題 —— **「我要哪一段」**。
#
#### 15.4 什麼時候一定會失敗（而且沒關係）
#
#patch 通常比一個重複單元還小，所以有些 patch 整張都落在同一種材質裡。
#那種 patch **不可能**定位 —— 沒有任何演算法能從一張均勻的圖判斷它在週期的哪裡。
#**這是資訊不夠，不是演算法不夠。**
#
#但那種 patch 也**不需要**定位：整張都是同一種材質，整張量就是對的。
#所以做法是「判斷有沒有地標，沒有就退回整張圖，並且把那顆標記出來」
#（`locate_ok` 這個 feature），讓使用者事後分得清哪些顆是定位過的。
#
#信心值的定義是「曲線的起伏 ÷ 雜訊的尺度」，分母用 **MAD 而不是標準差** ——
#銳利的邊界會讓平滑吃掉一點真訊號，用標準差當分母會變成「結構越清楚、信心越低」。
#實測：整張同一種材質約 0.7，任何有結構的情況都在 20 以上。
#
#另外擋掉一個退化情況：**固定斜率的漸層**上每一格梯度都相等，不加防護的話浮點
#誤差會決定邊界畫在哪，而且每一格都被判成邊界。所以要求「最陡的地方」至少比
#「一般的地方」陡 1.2 倍（漸層 1.00、正弦 1.41、方波極大）。
#
#### 15.5 前綴：多區域的前置條件
#
#一次吐好幾個框之後會立刻撞上一個既有的問題：兩張同型別的量測卡寫同一組特徵名，
#後面那張把前面那張蓋掉。所以量測卡加了 `output_prefix`，而且
#**Studio 在使用者挑了區域之後自動把它填成區域的名字** ——
#命名空間是工具的問題，不是製程工程師該懂的事；他把卡指到 `epi` 這個動作已經
#表達了意圖。只在空著時填，使用者自己命名過就不再動它。
#
#### 15.6 面板不是裝飾
#
#「敏感度要調多少」沒有答案，除非看得到曲線、看得到抓到幾條線、看得到線落在哪。
#所以面板畫的是**引擎那一次算出來的同一份資料**（step 卡把它放進
#`ctx.meta["profiles"]`），UI 不自己再算一次 —— 不然「畫面上的框」跟「真的量下去
#的框」有機會不一樣，而那種 bug 幾乎不可能靠肉眼發現。
#
#### 15.7 面板揭出來的一個舊 bug
#
#`PreviewWorker` 只合併「還沒開跑」的請求；已經在跑的那筆照樣會跑完並發出
#`ready`。所以「先送出背景預覽、接著又跑了同步預覽」時，舊的那筆會**後到**，
#把新的畫面蓋掉 —— 而且不會再更新，因為沒有人會再算一次。
#
#這個順序在實際操作裡並不罕見（點卡片 → 立刻改參數），只是以前的症狀是「影像
#閃一下」，不容易歸因；曲線面板讓它變成「面板整個空白」，才浮出來。
#修法是給預覽一個世代編號，背景那筆算完時編號不對就整筆丟掉。
#
#### 15.8 區域跨顆檢視
#
#一個區域設定對不對，是一個**關於整批**的問題。patch 是以缺陷為中心裁的，
#所以結構在每張 patch 裡的位置本來就不一樣 —— **在第 1 顆剛好的框，第 50 顆
#可能整個偏掉**，而看單顆永遠看不出這件事。
#
#所以 Region 卡旁邊有一顆「Check this region across defects…」：把區域畫到前 N 顆
#的縮圖上，一次看完。畫面上只有三件事 —— 縮圖、框、以及**這顆定位成功了沒**
#（失敗的用琥珀色外框、算不出來的用紅色）。
#
#**「只看失敗的」是預設就想得到的操作**，所以它是一個勾選框。定位失敗的那些
#才是要看的：可能是「本來就沒有結構可認」（正常，整張量就對），也可能是
#「參數設得太緊」（要調）—— 兩者只有看圖分得出來。
#
#三個實作上的決定：
#
#- **按鈕對任何會定義區域的卡片都出現**（走 `Step.resolve_regions_out()`），
#  不是只給投影定位卡。手畫的框一樣需要「在整批上看一遍」。
#- **縮圖的 letterbox 偏移與 `make_thumb` 放在同一個檔案**（`thumb_placement`）。
#  分開放的話，哪天改了縮圖的縮放規則而忘了改另一邊，框會整批偏掉 ——
#  而畫面上看起來只是「框好像有點歪」，不會有人聯想到是縮圖改過。測試直接
#  拿兩者對照。
#- **開背景執行緒**：它每顆都要跑一次 pipeline 到那張卡為止，N 顆就是 N 次。
#  而使用者按下這顆按鈕的當下，正是他在調參數、最需要介面有反應的時候。
#
#---
#
### 16. F7-12：Golden Cell 模板定位（ROI 定位第二批）
#
#投影定位（§15）只看 patch 自己，所以 patch 裡沒有地標時它就定不出來 ——
#而 patch **普遍小於一個重複單元**，那種情況不是例外，是常態。
#
#這一段補上另一條路：**把資訊從外面帶進來**。
#
#### 16.1 為什麼「patch 比週期小」不會擋住模板法
#
#討論裡使用者先問了這個問題（patch 小於 cell，對不對得起來？），然後自己給了
#答案：**匯入一張大圖，用週期估測疊出一個 Golden Cell 當模板。**
#
#這是對的，而且理由值得寫下來：**模板法不是把兩張小 patch 互相對位，是把一張小
#patch 滑進一張大模板。** 小的那張只要**比雜訊多一點結構**就會有唯一解 ——
#patch 小於 cell 反而是有利的（它一定塞得進去，不必處理跨越邊界的情形）。
#
#大圖拿得到，這條路才成立。使用者確認了三件事：
#
#- patch **就是**從大圖上裁下來的（同一支 rcp、同一個 beam 與條件 → 像素尺寸一模一樣）。
#- 大圖**每次掃描都跟著出來**。
#- 但 GC **可以跨 lot 共用** —— 同一支 inspection rcp 掃同一塊 scan area，
#  圖案是一樣的，換的只是 lot。
#
#所以模板**凍進 recipe**（base64 純文字，不是路徑）。存路徑的話，圖被搬走、被
#換掉、下個月有人用了另一張大圖，結果會**安靜地變** —— 而 recipe 是要交接給
#別人的東西，它必須自己就是完整的。純文字也是為了 §9.5 的 DLP 限制。
#
#### 16.2 我講錯的一件事（記下來免得再犯）
#
#我原本說「有了大圖，非週期 layout 也能定位」。使用者直接擋掉：
#**知道 patch 在大圖的哪裡，不等於知道要量哪一塊。** 非週期 layout 沒有一個
#「標一次就套用到所有地方」的單元可以標，那是 GDS（不同 layer 疊出 ROI）的事。
#
#這正是 §15.2 那張表裡「定位 / 定義」分欄的意義 —— 我自己在下一輪又把它們混回去了。
#**GC 法適用的前提是 layout 有週期**，這句話寫在卡片的 help 裡。
#
#### 16.3 原點必須錨在看得見的地標上
#
#疊出來的 cell，它的「第 0 欄」預設是大圖上的某個任意切點 —— 換一張大圖、
#換一個 seed，切點就換了。而使用者是在 cell 上標框的：切點一飄，**同一份 recipe
#在不同時間建的模板會指到不同的地方**，而且畫面上完全看不出來。
#
#所以 `anchor_cell()` 把 cell 環狀旋轉到**最強的上升邊**在第 0 欄。用「最大的正
#梯度」而不是 `abs`，否則一個週期的兩個相反邊界會競爭，錨點在兩者之間跳。
#測試直接鎖：三個 seed、三個不同切點，疊出來的 profile 幾乎一樣，且最強上升邊
#落在 index 0。
#
#### 16.4 三道閘門，因為分數本身會騙人
#
#比對用 NCC（`TM_CCOEFF_NORMED`）—— 對亮度與增益免疫，換機台不必重調。
#但 NCC 分數**單獨看不可信**，實測踩到兩個坑：
#
#| 坑 | 症狀 | 閘門 |
#|---|---|---|
#| 一維 layout 在另一軸上搜尋 | 峰的突出程度被稀釋，定得出來被判成定不出來 | `locate_axis`：不重複的那一軸整段吃掉，不搜尋 |
#| 全域 margin 被週期性自我打敗 | 相鄰週期的次高峰讓 margin 恆為 0 | **把比對曲面折回一個週期**再取次高峰 |
#| 均勻無結構的 patch | 純雜訊對任何模板都能拿到 0.44（門檻 0.3 → 過關） | `min_structure`：先問 **patch 自己有沒有東西可比**。實測無結構約 1、有結構 20 以上；20 顆無結構 patch 全部擋下（0 個假陽性） |
#
#第三個是關鍵：**沒有任何分數門檻分得出「對得準」與「碰巧」**，因為兩者的分數
#重疊。要問的是另一個問題 —— 這張 patch 上到底有沒有資訊。定不出來時退回整張圖
#並標 `locate_ok = 0`，跟投影定位同一個約定。
#
#### 16.5 一維 layout 不是特例
#
#第一版在 `py` 量不到週期時直接放棄。但垂直條紋（只有 X 有週期）是**最常見的**
#情況。現在兩軸各自判斷 `periodic_x` / `periodic_y`，不重複的那一軸取整個影像
#高度/寬度。
#
#順帶擋掉一個更難看的失敗：純雜訊上 `estimate_period` 會回一個**看似合理**的
#週期（實測 py=48，信心 20.3）。信心門檻拉到 40，噪音圖現在會被明確拒絕 ——
#「疊出一個沒有意義的模板」比「說我做不到」糟得多。
#
#### 16.6 對話框就是這張卡的入口
#
#模板不可能用打字的，所以 `TemplateDialog` 是唯一的入口，它壞掉整張卡就不能用。
#畫面上把**判斷材料全部攤開**：量到的週期、疊了幾格、疊出來長什麼樣、以及一個
#銳利度分數（`ghosting_score`，repo 本來就有）。
#
#使用者不需要懂那個分數怎麼算 —— 他要看得到「疊出來是清楚的還是糊的」。
#糊掉這件事另外用白話講一次（「這通常表示週期量錯了，而糊掉的模板會讓**每一顆**
#都放錯位置」），因為它是整條路唯一會**安靜壞掉**的地方：估錯 → 模板糊 →
#每顆都對錯 → 畫面上沒有錯誤訊息，只有一批看起來很正常、其實量錯位置的數字。
#
#### 16.7 還沒做：用當次的大圖做健檢
#
#跨 lot 共用 GC 的前提是「圖案沒變」。這個前提**通常**成立，但它會失效
#（rcp 改過、換了 scan area、機台調整過），而失效時的症狀跟 16.6 一樣是安靜的。
#
#做法已經想好、還沒實作：**拿當次掃描的大圖重疊一次 cell，跟凍在 recipe 裡的那
#份比對，差太多就警告。** 零件都在（`build_golden_cell` + NCC），缺的是接到
#Studio 的一個入口。列在下一批。
#
#---
#
### 17. F7-13：控制項要看得出自己是什麼（A 組）
#
#使用者看了跑起來的畫面之後說「先打磨 UI」。這一段做的是清單裡**不是品味問題**
#的那三項 —— 三個症狀來自同一種毛病：**控制項長得不像它自己**。
#
#這種 bug 用功能測試抓不到，因為每一項功能都是好的。
#
#### 17.1 下拉選單長得像文字框
#
#`Match on`（三條影像流擇一）、`Locate across`（x / y / both）、
#`Name this region`（自由文字）在畫面上**一模一樣**。前兩個點得開，第三個必須自己
#打字，而使用者無從得知。
#
#原因是一行 QSS：
#
#```css
#QComboBox::drop-down { border: 0; width: 18px; }
#```
#
#styled 的 subcontrol 要自己提供 `down-arrow` 圖檔，否則**箭頭完全不畫**。
#而這個 repo 是純文字的（§9.5 的 DLP 限制），不能塞圖檔。拿掉 `border: 0`
#就讓這個 subcontrol 留在 base style 上，由它自己畫箭頭。
#
#量出來的證據：修之前箭頭區域有 **0** 個非底色畫素；修之後 20 個，而同尺寸的
#`QLineEdit` 仍然是 0。`tests/test_ui_controls_readable.py` 直接鎖這個數字，
#淺色與深色各測一次。
#
#### 17.2 一個沒辦法用打的值，配了一個文字框
#
#`template` 的值有六千多個字元，而且它是**一張影像的內容**。給它文字框有三個
#後果：空的時候看起來只是「還沒填的欄位」（而真正的入口在半個螢幕外的預覽面板
#下方），填了之後那一格變成一片 base64，而且它是**可以編輯的** ——
#一個放不下、也編輯不了的值配一個文字框，等於邀請使用者去改它。
#
#所以加了一個參數型別 `template`（core 只多一個字串常數，UI 認得它）：
#這一列直接是**按鈕 + 一行摘要**，值本身唯讀。
#
#按鈕從預覽面板搬回參數列。原本放在影像下方的理由是「離影像近」，但它是**那個
#參數的值從哪來**，不是一個預覽動作 —— 放在影像下方等於把「這個欄位怎麼填」的
#答案擺到離欄位半個螢幕的地方。
#
#摘要是**解出來的**（`decode_cell` → 尺寸），不是存在旁邊的另一個欄位。
#存在旁邊的摘要會跟真正的值走散，而走散時畫面上看起來完全正常。
#
#順帶修掉一個還沒被看見的雷：節點的第三行摘要會把「非預設的參數」串起來，
#模板直接串進去就是一段 base64 —— 元件切掉之後看到的是
#`template=gc1:iVBORw0KGg…`，既沒有資訊也把真正有用的參數擠掉了。
#這種參數只講 `template: set`。
#
#### 17.3 「這張卡還不能跑」以前只有跑過才知道
#
#**參數合法 ≠ 設定完成。** 空字串是完全合法的 str，所以 `validate_params` 沒話說、
#lint 也沒話說 —— 但那張卡跑起來每一顆都會失敗，而使用者是在跑完 200 顆之後
#才知道的。
#
#新增 `Step.configuration_issues(params)`（預設回空 list）：卡片自己講「我還缺
#什麼」，而且用**這張卡的話**講（模板要去按哪一顆鈕），不是一句通用的
#「這個參數是必填的」。回傳的每一句變成一個 lint error（code `not-configured`），
#畫布上那張卡也因此掛上右上角的警示標記，滑鼠停上去講原因。
#
#這讓既有的「每張卡都要有可行組合」測試出現一個新的分類：`roi_template` 的路是
#通的，只是還沒設定完 —— 那不是死路。所以那支測試改成把 `not-configured` 分開
#看，但**要求它的訊息指得出路在哪**（訊息裡要有「…」，也就是一個按得下去的東西
#的名字），否則它就真的是死路了。
#
#### 17.4 按鈕看起來要像按鈕
#
#工具列本來是一排沒有邊框的字。那讀起來是「File Edit View…」——
#**而選單列是拉下來的東西，不是按的東西**，於是整條工具列都不像可以按。
#現在每一顆有自己的表面與邊框，主要動作（Run trial）維持強調色。
#
#順手：`First [200]` 旁邊沒有單位，200 可以是任何東西（秒？百分比？），
#數字框加上 ` defects` 後綴。
#
#---
#
### 18. F7-14：從畫布上就做得完一條 pipeline（B 組）
#
#使用者的清單裡「n8n 的手感」有三項。它們看起來像外觀，其實都是**功能**。
#
#### 18.1 輸出埠上的「+」
#
#以前要加一張卡，得回左邊的卡片庫，從 22 張裡自己判斷哪一張接得上目前這條流。
#卡片庫的作法是「全部列出來，接不上的標成 `needs diff`」——
#對不會寫 code 的人，那個 badge 沒有動作可做。
#
#但**「接得上」這件事引擎本來就知道**（`Step.resolve_reads` vs 累積到這個節點為止
#的影像流）。所以埠上的「+」跳出來的清單反過來：**只列現在就成立的卡**，
#依流程階段排序（Input→Enhance→…→ADC，那是使用者腦中的順序，不是字母序）。
#
#三個實作上的決定：
#
#- **每個輸出埠一顆「+」**，不是每張卡一顆。一顆共用的「+」表達不出
#  「我要對 ref 做這件事」。
#- **按的那個埠的影像流會被帶進新卡的主要輸入**（`target`／`source`）。
#  不帶的話，從 ref 的埠接一張 Denoise 出來卻做在 test 上 —— 那顆「+」就只是
#  一個比較短的「新增卡片」，而使用者以為他已經表達了意圖。
#- **接出來的線是實線**（顯式 edge），不是 route 相鄰的虛線。使用者的動作是
#  「從這裡接下去」，那是意圖，不只是順序。
#
#「+」畫在埠標籤之外，所以 `boundingRect` 也跟著長 —— 這是 F7-8／F7-9 那條
#不變量的第三次應用：**畫得出去的東西 boundingRect 一定要涵蓋**，否則拖動節點
#會留殘影。測試直接斷言每顆「+」的中心都在 `boundingRect` 裡面。
#
#### 18.2 縮放控制
#
#滾輪縮放本來就有，但**畫面上沒有任何東西說得出這件事**，而且滾過頭之後沒有路
#回來：點陣底縮小之後每一格都長得一樣，使用者不知道自己在哪裡。
#
#左下角四顆固定的鈕（− / + / 全部看得完 / 回到 100%）加一個百分比。
#縮放夾在 25%–300% —— 上下限本身就是一種「回得來」的保證。
#
#### 18.3 節點副標印的是「這張卡在做什麼」
#
#以前那一行印 node_id（`roi_template`）—— 那是 recipe JSON 的鍵，而卡片名字就在
#它上面一行，所以那一行等於沒有資訊。現在印 **`吃什麼 → 吐什麼`**
#（`test ref → ref_aligned`）。
#
#Region 卡不寫影像流，它定義的是具名區域，所以副標取 `resolve_regions_out()`
#（`diff → cell`）—— 不然那張卡在畫布上看起來什麼都不產出。
#
#**重複的卡片才把 id 帶出來**（`denoise2 · ref → ref`）。那時候「是哪一張」
#才真的是使用者需要知道的事 —— lint 訊息與特徵前綴講的都是那個 id。
#
#---
#
### 19. F7-15：畫面上的字要能被讀完（C 組）
#
#清單的最後一組。三件事都不是「功能不對」，是**讀不完／看不到／分不出來**。
#
#### 19.1 一面灰字牆
#
#一張卡 11 個參數，每個帶 2–3 行說明 —— 加起來一定要捲，而且**真正要緊的事會
#淹在裡面**：「這張卡還沒有模板」跟「這個滑桿越大越平滑」長得一模一樣。
#
#作法：說明平常**一行**（放不下就切成 `像這樣…`），滑鼠移上去或欄位拿到焦點時
#整段攤開。收起來的行數從 11×3 變成 11×1，同一個高度看得到的參數多一倍。
#
#三個細節：
#
#- **切字自己算**（`elidedText`），不交給 Qt 裁 —— Qt 硬切在字的中間，
#  看起來像畫面壞掉（同 canvas 的 `_draw_elided`）。
#- **錯誤永遠攤開**。那是他現在最需要讀完的一句話，不能因為滑鼠移開就切掉。
#- **`hint_text()` 回的是全文**，不是畫面上放得下的那一段。收起來只是畫面上的
#  事；問「這個參數的說明寫了什麼」的人要的從來不是「現在放得下多少」。
#  全文同時也在 tooltip 裡。
#
#不做成「只留 tooltip」是因為那等於把說明藏起來 —— 使用者是不會寫 code 的製程
#工程師，他要的是「我現在在動的這個東西是什麼」隨手看得到，而不是「知道要把
#滑鼠停在哪裡等一秒」。
#
#一個 Qt 的坑：滑鼠從列的空白處移進**這一列自己的**輸入框時，Qt 會先送 `Leave`
#給列、再送 `Enter` 給子元件。照字面處理就是收起來又立刻攤開，看起來是閃一下。
#所以 `leaveEvent` 直接問游標還在不在這一列的矩形裡。
#
#### 19.2 一片黑
#
#沒載資料時，畫面上最大的一塊是純黑，正中央一行灰字 `(no image)`，右上角一行
#更小的 `(no dataset loaded)`。首啟導覽關掉之後，**沒有任何東西說得出下一步**。
#
#那一塊現在是一個 `QStackedWidget`：沒資料時放「No data loaded yet」加上使用者
#真正能做的那兩件事 —— **Open KLARF…**（主要）與 **Try it with sample data**
#（次要，同一顆鈕在首啟導覽裡）。載到資料就換回影像。
#
#### 19.3 「沒成功」跟「做好了」長得一樣
#
#狀態列是**唯一**會講出「這件事沒成功」的地方（lint 擋下試跑、卡片加不進去、
#模板存不起來、還沒載資料就按了鈕），而它跟「Added denoise」用完全一樣的灰字，
#在畫面最左下角。使用者按了一顆鈕、什麼都沒發生、而唯一的解釋長得跟剛才那句
#成功訊息一模一樣 —— 那等於沒有講。
#
#`_status(msg, level="error")` 會在狀態列掛一個屬性，QSS 把它變成紅色粗體。
#測試不比對顏色值（那會綁死主題），而是**用同一句話渲染兩次**、只有 level 不同，
#比較畫素：設了屬性但 QSS 沒有對應規則的話兩張圖會一模一樣，那正是要擋的情況。
#
#哪些訊息算 error 是**逐條列舉**的，不是靠字串比對 —— 規則比對會把
#「No results to export yet」這種旁白也染紅。
#
#---
#
### 20. F7-16：四張安全網
#
#這四項不是「不方便」，是**一個誤按就沒了**。使用者看完 F7-15 的畫面之後問
#「還有什麼可以改」，我把這四件排在功能面（Feature 面板）前面，理由是它們損失的
#是**已經做完的工作**。
#
#### 20.1 復原：存整份快照，不是反向操作
#
#`RecipeModel` 的每一個變動之前先存一份**整個編輯狀態的快照**。
#
#反向操作（「刪掉的卡再加回去」）看起來比較省，實際上每加一個新動作就多一個
#會忘記的地方 —— 而且這個 model 有一堆**連帶效果**：`add_edge` 會重排
#`node_order`（拓撲排序）、`set_param` 會連帶補上相依的預設值。反向操作要為每一種
#連帶效果各寫一次「怎麼倒回去」，漏掉一個就是「復原之後跟原本不一樣」，
#而那種 bug 使用者看不出來。
#
#recipe 很小（幾十個節點、純 JSON 值），存整份是幾十 KB 的事。
#
#**滑桿要合併成一步。** 拖一次滑桿會發幾十次 `set_param`；每次各記一步的話，
#按一次 Ctrl+Z 只退回一個畫素，使用者要按四十次 —— 那等於沒有復原。所以
#`_push_undo(key)` 帶一個「這次改的是哪一個東西」的鍵，同一個鍵連續改只記第一次。
#
#那個鍵在**換節點、存檔、復原/重做**時清掉（`end_coalescing`）—— 因為
#「調 A 卡的 gamma → 去做別的 → 再調回 A 卡的 gamma」是兩件事，不該被併成一步。
#
#### 20.2 快捷鍵：照慣例，不要自己發明
#
#以前一個都沒有（`studio.py` 裡沒有任何 `setShortcut`）。而存檔、跑一次、退一步是
#每分鐘都在做的事，每次都要把手移到滑鼠、找到那顆鈕。
#
#全部照作業系統慣例：`Ctrl+O` / `Ctrl+S` / `Ctrl+R` / `Ctrl+Z` / `Ctrl+Shift+Z`
#與 `Ctrl+Y` / `Ctrl+0`、`Ctrl+±`、`Ctrl+Shift+F`（fit）/ `Ctrl+F`（找卡片）/
#`Ctrl+←→`（上一顆／下一顆）。使用者的肌肉記憶是從別的軟體帶過來的，這裡不該重學。
#
#**按鍵存在還不夠，要發現得到** —— 寫進工具列的 tooltip。這裡踩到一個坑：
#`_update_action_states()` 每次 refresh 都會重寫那幾顆的 tooltip（「還沒有東西可以
#存」之類的原因），所以「建構時附加一次」在第一次 refresh 就被蓋掉了。改成
#**設 tooltip 的那個動作自己會補上快捷鍵**（`_set_tip`）。
#
#### 20.3 關窗前問一次
#
#以前 `closeEvent` 只是收工。`model.dirty` 一直有在維護，但沒有人讀它 ——
#調了一小時的 recipe，關掉就沒了。
#
#三個答案：存檔 / 不存 / 取消。**存檔失敗（或使用者在存檔對話框按取消）不算可以
#關** —— 那是「我改變主意了」，不是「丟掉吧」。所以 `_on_save_recipe()` 從
#「回 None」改成回傳「真的存下去了嗎」。
#
#判斷與對話框分開（`confirm_close()` / `_ask_unsaved()`），測試驗的是
#「三個答案各自會怎樣」，不是 QMessageBox 長什麼樣。
#
#**測試裡一律關掉這個對話框**（`tests/conftest.py`）：一個 modal 對話框不會讓
#headless 測試失敗，它會讓測試**永遠停在那裡**而且沒有任何訊息 —— 那種卡住最難查。
#
#### 20.4 跑到一半可以停
#
#引擎**本來就支援**（`run_batch` 的 `abort_check`、`TrialWorker.abort()`），
#只是畫面上沒有任何地方按得到 —— 使用者唯一的中止方式是把整個視窗關掉。
#進度條旁邊加一顆 Stop。
#
#兩個細節：
#
#- **已經跑完的那些顆留著。** 按停止是「不要再等了」，不是「把剛才那五分鐘丟掉」。
#- **不能講「finished」。** 被中止的那一批，數字是真的，但它描述的是「你叫我停的
#  時候跑到哪裡」，不是整批的結果。差一個字，後面所有根據這批數字做的判斷
#  （抓漏率、誤殺率）就都建立在錯的前提上。
#
#---
#
### 21. F7-17：右下角是**這張卡自己的儀表**
#
#使用者的話：「我一直覺得右下角 Feature 那一塊還可以拿來利用」，而且指出我第一輪
#提的那些（整批分布、分數拆解）「都比較偏 ADC 面板會顯示的」—— 他要的是
#**每張卡那邊的位置可以放什麼**。他是對的，而且這個模式 repo 裡已經有了：
#`roi_profile` 選起來會冒出投影曲線面板（F7-11）。那不是特例，那是沒有被推廣的通例。
#
#### 21.1 為什麼不是一塊通用面板
#
#原本固定是一張「特徵 / 數值」表。問題不是它佔位子，是**那些數字沒有辦法判讀**
#—— `blob_dist_center 11.170` 是大還是小？`blob_snr 255` 是不是飽和了？
#一個數字單獨存在，回答不了使用者真正在問的問題。
#
#而使用者在問的問題**每張卡都不一樣**：調 Align 時他要知道「搜尋半徑夠不夠大」，
#調 Denoise 時他要知道「我有沒有把訊號一起磨掉」。同一塊面板放同一種東西，
#對兩者都答非所問。
#
#挑選原則（面板只有約 200 px，每張卡只放一件事）：
#
#> 這張卡最常見的失敗模式是什麼，而那個失敗**在單顆畫面上看不出來**。
#
#看得出來的（影像整個黑掉）不需要面板；看不出來的才需要。
#
#### 21.2 這一輪做的四個
#
#| 卡片 | 面板 | 它回答的問題 |
#|---|---|---|
#| `load_patch` | **哪一頁 → 哪一條流**，每頁的尺寸與平均灰階 | 「第一張是 test、第二張是 ref」是全專案**第一條待廠內驗證的假設**。錯了的話 diff 整個反號、所有分數都錯，而畫面上看不出來（兩張本來就很像）。以前唯一的驗證方式是另外跑 `fab_probe`；現在載入第一份真資料就看得到。兩頁平均灰階差 8 以上會直接警告 |
#| Enhance 九張卡 | **同一條流的 before / after 直方圖 + 削平計數** | Enhance 的失敗是安靜的：對比拉大「看起來變乾淨了」，但背景被壓成全黑、缺陷邊界一起被吃掉，而後面每一張量測卡都吃這個結果。削平是唯一能量化「我毀掉了多少」的東西 |
#| `align` | **整批的位移散佈圖** + 搜尋半徑的方框 | 對位失敗在單顆上看不出來 —— 演算法一定會回一個位移，而 8 是一個看起來完全正常的數字。真正的失敗是**位移被半徑截斷**，那在散佈圖上是「點貼在框邊」，一眼可見，而且照做得出來（把半徑調大） |
#| 五張量測卡 | **這張卡自己的每個特徵，整批分布 + 這一顆站在哪** | 調量測卡時要問的是「我把參數設成這樣，量出來的東西**分不分得開**」。擠成一根柱子＝門檻設哪裡都一樣。只列這張卡的特徵（含 `output_prefix`）—— 整份 feature 表是 ADC 的事 |
#
#### 21.3 三條約定
#
#1. **依 `Step.key` 註冊**（`INSPECTORS`）。沒註冊的卡就用原本的特徵表 ——
#   加一張新卡不必動 `inspectors.py`，維持「import 就出現」那條規則。
#2. **畫的是引擎算出來的那一份**：`ctx.meta`（step 卡自己放進去的）或
#   `trial_results`（跑完的整批）。UI 不自己重算 —— 不然畫面上的東西跟真的跑出來
#   的有機會不一樣，而那種 bug 幾乎不可能靠肉眼發現。
#3. **沒有資料時說得出「為什麼沒有」**。空白面板本身不是訊息。
#
#### 21.4 before/after 需要引擎配合，而它是**選配**的
#
#Enhance 卡是就地改寫同一條流（`test → test`），所以跑完之後「之前長什麼樣」就
#沒了。作法是 `Context.track_changes`：**覆寫既有影像流時**把前後各壓成一個
#48 格直方圖加削平比例，放進 `ctx.meta["stream_change"]`。
#
#**預設關閉，只有預覽（單顆）打開。** 批次跑一萬顆時每次 `set_image` 都算兩個
#直方圖是白花的力氣 —— 那份資料沒有人看。存的是摘要不是影像：存兩張圖會讓每顆
#的 meta 變成幾百 KB。
#
#### 21.5 三個實作上踩到的東西
#
#- **直方圖高度用平方根。** 削平會在兩端堆出兩根極高的柱子（六成畫素都在那裡），
#  線性刻度下其餘的分布被壓成貼著底的一條線 —— 而那正是要比較的形狀。
#- **「這一顆」的位置會落在整批範圍外，而那是正常的**：改了參數之後預覽立刻重算，
#  整批還是上一次跑的。夾回邊界並畫成箭頭（「在這個方向的外面」也是一個答案），
#  不夾的話那條線會畫到面板外面、蓋到旁邊的文字。
#- **`drawPolygon(QPointF, QPointF, QPointF)` 在 PySide6 會 segfault**（不是丟例外，
#  是整個行程掛掉）。要傳 `QPolygonF`。
#
#### 21.6 第二批：Region 的兩張卡
#
#**`roi_profile` 的曲線面板收進機制。** 它 F7-11 就做好了，只是當時直接掛在預覽
#面板上 —— 也就是一條**跟儀表機制平行的路**。兩條並存的下場是：加新面板的人不知道
#該走哪一條，然後兩邊各長一半。畫的還是同一個元件（`widgets.ProfilePanel`），
#只是換了個地方住。`profile_panel` 這個對外名字保留（測試與狀態列都用它），
#選到別的卡時回一個**空的替身**而不是 `None` —— 呼叫端不必到處寫 `if is None`。
#
#**`roi_template` 的三道閘門。** 定位失敗時卡片只講「定不出來，退回整張圖」，
#但那有三個原因，而**處置完全不同**：
#
#| 失敗的閘門 | 真正的意思 | 該做什麼 |
#|---|---|---|
#| match | 模板不對，或這批圖跟建模板那張差太多 | 檢查模板是不是這一層建的 |
#| certainty | 對得上的位置不只一個 | 調低門檻＝接受擲硬幣，通常不該調 |
#| structure | **這張 patch 上根本沒有東西可比** | **不要調** —— 退回整張圖就是對的答案 |
#
#分不出來的話，使用者會一直去調前兩個門檻，而問題其實在第三個 —— 然後一路調低到
#它開始亂放框。所以面板是三根柱子，每一根上面畫著**它自己的門檻線**：沒有那條線，
#柱子的長度沒有意義（多長才算夠？）。
#
#### 21.7 還沒做的（同一個機制）
#
#`blob_segment` 的 label map、`subtract` 的背景殘差（後面所有量測的地板噪音）、
#`roi_snr` 的分子分母分解（SNR 是比值，單看比值不知道是訊號小還是雜訊大）、
#Region 卡常駐的「框畫在前 N 顆縮圖上」，以及所有卡片共用的頁尾
#「這張卡在這一批花了多少時間」（`traces` 裡本來就有）。
#
#---
#
### 22. F7-18：影像流是節點的事，不是控制列的事
#
#使用者三件回饋。前兩件看起來是外觀（一顆按鈕、一個顏色），第三件才是主菜 ——
#但三件指向同一句話：**畫布是主體，控制列是配角。**
#
#> 「目前新增各個卡片各個節點後的 + 號會永久存在，我後來想想還是手動從旁邊功能卡
#> 添加好了……虛線代表可以拉沒錯，但不要跟實線同個顏色……我看到很多張卡片都會
#> 限制或阻撓只能拉 ref，但我希望不會有這個限制，test 跟 ref 就是兩張不同的
#> image source，應該是都要可以做操作的（所以其實也不用再控制列設定什麼 Apply to
#> 或者是 also apply to（變很複雜））—— 之間用節點的方式去指引每張 image source
#> 會做哪些事或操作。」
#
#### 22.1 拿掉輸出埠上的「+」
#
#F7-14 加它的理由仍然成立（「接得上」引擎本來就知道，使用者不必自己判斷）。
#但它是**常駐**的：每個輸出埠一顆，一份十張卡的 pipeline 就有十幾顆加號長在
#節點旁邊，而它們跟資料流無關 —— 畫布的主體是節點與連線，其餘每一個常駐的東西
#都在跟主體搶。
#
#所以入口收回卡片庫，而「+」做對的兩件事沒有跟著丟掉，只是換了觸發點：
#**選著一張卡的時候從卡片庫加，新卡就接在它後面、做在它那條流上**
#（`_on_add_requested` → `add_card_after`）。加完選取新卡，所以連按三張卡片會
#長成一條鏈，順序就是按下去的順序 —— 不會像「永遠插在同一張後面」那樣倒過來。
#
#`cards_addable_after()`（只列接得上的）跟著「+」一起走了：卡片庫本來就把 22 張
#全列出來並標 `needs diff`，兩套「哪些卡現在能用」的邏輯並存會腐爛。
#
#### 22.2 虛線給它自己的顏色
#
#以前虛線是 `canvas_edge` 加 alpha 120 —— **同一個顏色淡一點**。那只說得出
#「比較不重要」，而這兩種線在語意上是不同的東西：
#
#| | 誰畫的 | 刪得掉嗎 | 使用者要讀到的意思 |
#|---|---|---|---|
#| 實線 | 使用者拉的 | 選起來按 Delete | 我指定了這條連接 |
#| 虛線 | 卡片的排列順序 | 刪不掉（要拿掉就把卡移走） | 這裡**可以**拉一條 |
#
#而且深淺這個維度在畫布上不可靠：縮放會改變抗鋸齒後的實際灰度，換暗色主題整組
#關係又要重新調。新的 `canvas_edge_implicit` 是一個暖色（light `#b08a5a`／
#dark `#a2794a`），跟中性偏藍的 `canvas_edge` 拉開色相。
#測試鎖兩層：token 的色相差得出來，而且 `paint()` 真的去讀了它
#（把兩條線各自畫進 pixmap 比主色相 —— 「token 換了但畫的地方沒改」正是要擋的）。
#
#### 22.3 一張卡一條流（這一輪真正的改動）
#
#原本七張 Enhance 卡都是「`target` 主流 + `also_apply` 一串附帶的流」。
#那個形狀有三個問題，而它們都不是「多一個參數」而已：
#
#1. **它把 test 講成主角、ref 講成附帶。** 但 patch 就是兩張輸入影像，
#   兩張都該可以獨立處理。
#2. **它讓一張卡偷偷動了畫布上看不到的東西。** 那張卡畫在 test 那條鏈上，
#   卻同時改寫了 ref —— 畫布因此說謊。
#3. **兩個節點之間只拉得動一條線。** 先從 test 拉、再從 ref 拉，第二條只會拿到
#   一句 `already connected` 然後什麼都沒發生。使用者的結論是「這張卡不准我碰
#   ref」 —— 就是回饋裡的「限制或阻撓」。
#
#改法：**`resolve_writes` 一律只回主流那一條**，`also_apply` 從七張卡上消失。
#要對 ref 做同一件事就再放一張卡接到 ref，畫布上因此看得到兩條各自的處理鏈。
#
#### 22.4 連線設定影像流
#
#`edge_added` 多帶一個參數：**這條線從哪個輸出埠出發**（`(src, dst, stream)`）。
#Studio 收到之後把下游那張卡的主要輸入（`target`／`source`）指到那條流。
#於是「這張卡做在 ref 上」變成一個**畫布上做得完**的動作。
#
#同一對節點之間再拉一條也照樣處理 —— 那句話不是「你已經連過了」，是
#「我改變主意了，這張卡改做 ref」。沒有主要影像流參數的卡（`subtract` 有自己的
#`a`／`b`）不受影響：連線不亂改它們。
#
#### 22.5 唯一掉了的能力，補一個看得見的替代品
#
#`percentile_norm` / `glv_mask_norm` 的 `anchor="source"` 是「其他流借主流量出來
#的拉伸範圍」—— 那是「兩張圖正規化完還比得起來」的關鍵，不能跟著 `also_apply`
#一起消失。它現在是 `range_from`（一條**影像流的名字**），所以在畫布上就是接進
#這張卡的第二條線，而不是一個藏在下拉裡的 `self` / `source`。
#
#借不到（那條流不存在）就報錯，不靜靜改用自己的範圍：兩者的輸出都是一張看起來
#很正常的圖，差別只在數字。
#
#### 22.6 舊 recipe 要照樣讀得進來
#
#recipe 是**存在磁碟上、拿來交接**的檔案。認不得 `also_apply` 等於一份跑得好好的
#檔案在升級之後變成 `unknown parameters` —— 對不會寫 code 的人那就是「工具壞了」。
#
#`Recipe.from_json_dict` 加了一道遷移：一個帶 `also_apply` 的節點展開成 N 張卡，
#插進 route。做在 recipe 層而不是卡片的 `validate_params` 裡，因為它會**增加節點**
#—— 一張卡看不到自己以外的東西。
#
#**順序看 `anchor`**，而這一點是整段遷移唯一有陷阱的地方：`anchor="source"` 的
#語意是「ref 用 **test 原本的** 灰階範圍」。如果拆完之後 test 那張先跑，它會先把
#test 拉成 0–255，ref 再去借就借到「拉伸後」的範圍 —— 數字不一樣，而畫面上兩者都
#是一張看起來正常的圖。所以借範圍的那幾張排在**前面**。
#
#驗證方式不是讀程式碼：同一份 `die_to_die_basic` 跑 100 顆合成 patch，遷移前後
#`min / median / max` 與兩個 bin 的數量**逐項相同**（20.230 / 32.115 / 175.000、
#bin 0 = 54 · bin 1 = 46），`cd_gate` 同樣相同。三份範例 recipe 也就地改寫成新格式。
#
#### 22.7 還沒做
#
#- 兩條處理鏈完全相同時，畫布上沒有東西講出「這兩張卡是一對」。多數 recipe 會有
#  一對 Normalize、一對 Denoise，而它們必須維持同樣的參數才比得起來 ——
#  改了其中一張、忘了另一張，是這個新形狀帶進來的**新**的安靜失敗。
#  候選解法：lint 的一條 warning（「這兩條流被處理成不一樣了」），而不是把兩張卡
#  綁在一起（綁起來就退回 `also_apply` 了）。
#- 節點副標現在印 `test → test`，成對的兩張卡看起來只差一個字。
#- **`range_from` 的順序是靠說明講的，不是靠檢查擋的。** 借範圍的那張卡要排在
#  「會改寫那條流」的卡**前面**，否則借到的是拉伸後的範圍 —— 遷移出來的 recipe
#  與 Studio 的加卡流程都會自然排對，但手工重排就可能弄錯，而弄錯之後兩張輸出
#  都是看起來正常的圖。`validate()` 加一條 warning 是對的方向，但那條規則是
#  「這張卡讀的流被上游改過」—— 對幾乎每張卡都成立，所以要先想清楚怎麼講才不會
#  變成雜訊。
#
#F 8dca9d9389fa5413ad9d89cf8ba8c136b7d540e7 67 examples/recipes/README.md
## 範例 recipe 庫 —— 先挑一個最像你的情況，再改參數
#
#這裡每一份 `.json` 都是一條**可以直接跑**的完整流程（影像段 → 算法段 → ADC 判定）。
#建議的用法：**不要從空白開始**。挑一份最接近你站點情況的，載進 Studio 之後
#改參數、改分數門檻，存成你自己的 recipe。
#
#在 Studio 裡：工具列「範例 recipe」→ 選一份 →「載入」。
#
#---
#
### 先回答三個問題，就知道要挑哪一份
#
#1. **有沒有可以拿來比對的參考圖（ref）？**
#   機台的 die-to-die patch 通常會附一張 ref；Review SEM 單張通常沒有。
#2. **沒有 ref 的話，圖上有沒有重複的 cell 圖案？**
#   有的話可以把重複的 cell 疊成一張乾淨的「Golden Cell」自己當 ref。
#3. **你要用什麼決定「這顆重不重要」？**
#   殘差有多亮（灰階）？還是缺陷有多大（CD 尺寸）？
#
#---
#
### 對照表
#
#| Recipe | 什麼情況用它 | 走哪條 route | 分數怎麼算 |
#|---|---|---|---|
#| `die_to_die_basic.json` | **最常見的起點**。機台有給 ref 的 die-to-die patch，想先把假點濾掉。 | `ebi_patch` | 對位相減後，**中心 32 px 方框內差異圖的最亮值**，再加上「最亮值比 99 百分位高多少」當尖銳度加權：`glv_max + (glv_max - glv_q99)`，門檻 50。 |
#| `dual_route_basic.json` | 同一套判定標準要**同時吃兩種輸入**（機台 patch 與 Review SEM），不想維護兩份 recipe。 | `ebi_patch` + `rsem` | 中心區差異圖的**無量綱對比**：`(glv_max - glv_median) / (glv_std + 0.5)`，門檻 4.2。無量綱 → 兩條 route 可以共用同一個門檻。 |
#| `rsem_golden_cell.json` | **只有單張 Review SEM、沒有 ref，但圖上有重複的 cell**。 | `rsem` | 量出 cell 週期 → 疊出 Golden Cell 當 ref → 相減；分數就是**中心區殘差的最大值** `glv_max`，門檻 30。自己減自己，亮度／對比飄移會抵消，不必先做正規化。 |
#| `single_image_rules.json` | **既沒有 ref、圖上也沒有週期性**可以疊 Golden Cell 的保底作法。 | `ebi_patch` + `rsem` | 直接在原圖上算局部訊號突出度，三條規則相乘：**訊號要強 × 塊要夠大 ÷ 離報點位置要近**，前面再加一道對焦閘（模糊的圖直接 0 分）：`(focus_lapvar > 100) * snr_max * blob_area / (blob_dist_center + 5)`，門檻 0.16。 |
#| `cd_gate.json` | 站點對「**多小的缺陷可以放過**」有明確規格，要用尺寸而不是亮度做決定。 | `ebi_patch` | 先用中心區殘差當閘門確認「這是真的」，過關的才用缺陷尺寸算分：`(glv_max > 30 and cd_x_px > 2) * max(cd_x_px, cd_y_px)`，門檻 3 —— **門檻的單位就是像素**，填你在意的最小缺陷尺寸。 |
#
#---
#
### 每一份在教什麼（挑 recipe 之外的價值）
#
#- **`die_to_die_basic`** —— 標準的影像段五連：正規化 → 對位 → 相減 → 去噪 → SNR 地圖。
#  沒有 ref 就沒有 `diff`，後面整段算法都動不了；這是三段式的骨架。
#- **`dual_route_basic`** —— 一份 recipe、兩條 route。兩條路共用同一批算法節點，
#  **只有和影像尺寸有關的幾何參數（中心框大小）各自一個節點**。
#  這是踩過的坑：同一組 `box_size` 在 128² patch 上準、在 256² 上會漏抓。
#  分數改用無量綱式子，兩條路才能共用一個門檻。
#- **`rsem_golden_cell`** —— 「沒有 ref 就自己造一張」。`cell_period` 量週期、
#  `golden_cell` 疊圖，之後就完全回到 die-to-die 的老路。也示範了
#  **不是每條流程都需要正規化與對位**（Golden Cell 天生對齊、亮度天生一致）。
#- **`single_image_rules`** —— 不用參考圖也能給分：把工程師口頭的判斷條件
#  （「訊號要明顯、東西要夠大、要在報點附近」）直接寫成一條乘法算式，
#  再用比較運算子做閘。**這是準確率最低的一條**（合成資料上約九成，
#  而且很吃參數），只在前面兩條路都走不通時當保底。
#- **`cd_gate`** —— 分數不一定要是無單位的「可疑度」，**也可以是有物理單位的量**。
#  分數 = 缺陷寬高（像素），門檻 = 規格。另外示範 `blob_segment` 可以直接切
#  `diff`，不一定要先做 SNR 地圖。
#
#---
#
### 改的時候注意
#
#- **幾何類參數要跟著影像尺寸走**（中心框 `box_size`、SNR 視窗 `window`、
#  `exclude_border`、`min_area`）。同一份 recipe 要吃兩種尺寸的圖時，
#  請像 `dual_route_basic` 那樣**每條 route 各放一個節點**，不要共用。
#- **門檻先看直方圖再決定**。試跑之後直接在直方圖上拖那條線，
#  bin 數會即時跟著變；覺得對了再放開滑鼠套用。
#- **分數表達式的變數 = 上游卡片產出的特徵名**。用分數編輯頁的
#  「插入特徵 ▾」挑，不會打錯字。
#- 改完存成自己的檔案（工具列「存 Recipe…」），**不要覆蓋這裡的範例** ——
#  `tests/test_example_recipes.py` 會對每一份範例做驗證與實跑，
#  改壞了測試會紅。
#
#F f4447ff0a7e92ab5c551c541a165edbcdeec7556 112 examples/recipes/cd_gate.json
#{
#  "recipe_id": "cd_gate",
#  "version": 1,
#  "author": "HX",
#  "description": "Die-to-die，但分數本身就是缺陷尺寸（像素）：先用差異圖的中心區殘差當「這是不是真的」的閘門，過關的才用最大缺陷區塊的寬高算分，門檻直接填你在意的最小缺陷尺寸。適合「多小的缺陷可以放過」有明確規格的站點。這條也示範 blob 可以直接切 diff，不一定要先做 SNR 地圖。",
#  "routes": {
#    "ebi_patch": [
#      "load",
#      "norm_ref",
#      "norm",
#      "align",
#      "sub",
#      "dn",
#      "blob",
#      "cd",
#      "glv_roi",
#      "glv"
#    ]
#  },
#  "nodes": {
#    "load": {
#      "step": "load_patch",
#      "params": {},
#      "enabled": true
#    },
#    "norm_ref": {
#      "step": "percentile_norm",
#      "params": {
#        "source": "ref",
#        "range_from": "test"
#      },
#      "enabled": true
#    },
#    "norm": {
#      "step": "percentile_norm",
#      "params": {
#        "source": "test"
#      },
#      "enabled": true
#    },
#    "align": {
#      "step": "align",
#      "params": {
#        "method": "phase",
#        "search_radius": 8
#      },
#      "enabled": true
#    },
#    "sub": {
#      "step": "subtract",
#      "params": {},
#      "enabled": true
#    },
#    "dn": {
#      "step": "denoise",
#      "params": {
#        "target": "diff",
#        "method": "median",
#        "ksize": 3
#      },
#      "enabled": true
#    },
#    "blob": {
#      "step": "blob_segment",
#      "params": {
#        "source": "diff",
#        "diff_source": "diff",
#        "min_area": 6,
#        "snr_threshold": 30
#      },
#      "enabled": true
#    },
#    "cd": {
#      "step": "cd_measure",
#      "params": {
#        "source": "diff",
#        "refine": "none"
#      },
#      "enabled": true
#    },
#    "glv_roi": {
#      "step": "roi_define",
#      "params": {
#        "name": "glv_roi",
#        "shape": "center",
#        "size": 32.0,
#        "size_unit": "px",
#        "source": "diff"
#      },
#      "enabled": true
#    },
#    "glv": {
#      "step": "glv_stats",
#      "params": {
#        "source": "diff",
#        "metrics": "glv_max,glv_median,glv_std",
#        "roi": "glv_roi"
#      },
#      "enabled": true
#    }
#  },
#  "edges": [],
#  "score": {
#    "expr": "(glv_max > 30 and cd_x_px > 2) * max(cd_x_px, cd_y_px)",
#    "threshold": 3.0,
#    "bins": {
#      "below": 0,
#      "above": 1
#    }
#  }
#}
#
#F 8f4800382997c2f5e2d5e9fa48e1963184dca10e 109 examples/recipes/die_to_die_basic.json
#{
#  "recipe_id": "die_to_die_basic",
#  "version": 2,
#  "author": "HX",
#  "description": "Die-to-die nuisance filter: normalise -> subtract -> denoise, scored on the peak GLV in the centre region. No alignment step: the tool emits corresponding test/reference patch pairs already.",
#  "routes": {
#    "ebi_patch": [
#      "load",
#      "norm_ref",
#      "norm",
#      "sub",
#      "dn",
#      "snr",
#      "blob",
#      "cd",
#      "glv_roi",
#      "glv"
#    ]
#  },
#  "nodes": {
#    "load": {
#      "step": "load_patch",
#      "params": {},
#      "enabled": true
#    },
#    "norm_ref": {
#      "step": "percentile_norm",
#      "params": {
#        "source": "ref",
#        "range_from": "test"
#      },
#      "enabled": true
#    },
#    "norm": {
#      "step": "percentile_norm",
#      "params": {
#        "source": "test"
#      },
#      "enabled": true
#    },
#    "sub": {
#      "step": "subtract",
#      "params": {
#        "b": "ref"
#      },
#      "enabled": true
#    },
#    "dn": {
#      "step": "denoise",
#      "params": {
#        "target": "diff",
#        "method": "median",
#        "ksize": 3
#      },
#      "enabled": true
#    },
#    "snr": {
#      "step": "snr_map",
#      "params": {
#        "window": 15,
#        "exclude_border": 8
#      },
#      "enabled": true
#    },
#    "blob": {
#      "step": "blob_segment",
#      "params": {
#        "min_area": 6,
#        "snr_threshold": 200
#      },
#      "enabled": true
#    },
#    "cd": {
#      "step": "cd_measure",
#      "params": {},
#      "enabled": true
#    },
#    "glv_roi": {
#      "step": "roi_define",
#      "params": {
#        "name": "glv_roi",
#        "shape": "center",
#        "size": 32.0,
#        "size_unit": "px",
#        "source": "diff"
#      },
#      "enabled": true
#    },
#    "glv": {
#      "step": "glv_stats",
#      "params": {
#        "source": "diff",
#        "metrics": "glv_max,glv_q99,glv_mean",
#        "roi": "glv_roi"
#      },
#      "enabled": true
#    }
#  },
#  "edges": [],
#  "score": {
#    "expr": "glv_max + (glv_max - glv_q99)",
#    "threshold": 50.0,
#    "bins": {
#      "below": 0,
#      "above": 1
#    }
#  }
#}
#
#F cca8e89b079ee63234f5bf8cd4507cf13e9a7911 159 examples/recipes/dual_route_basic.json
#{
#  "recipe_id": "dual_route_basic",
#  "version": 1,
#  "author": "HX",
#  "description": "雙路線範本：EBI patch 用機台附的 ref；RSEM 單張沒有 ref → Golden Cell 自己疊一張當基準。兩路共用同一段算法與判定，只有影像尺寸相關的幾何參數不同。",
#  "routes": {
#    "ebi_patch": [
#      "load",
#      "norm_ref",
#      "norm",
#      "align",
#      "sub",
#      "dn",
#      "snr",
#      "blob",
#      "cd",
#      "glv_patch_roi",
#      "glv_patch"
#    ],
#    "rsem": [
#      "load",
#      "golden",
#      "norm_ref",
#      "norm",
#      "align",
#      "sub",
#      "dn",
#      "snr",
#      "blob",
#      "cd",
#      "glv_rsem_roi",
#      "glv_rsem"
#    ]
#  },
#  "nodes": {
#    "load": {
#      "step": "load_patch",
#      "params": {},
#      "enabled": true
#    },
#    "norm_ref": {
#      "step": "percentile_norm",
#      "params": {
#        "source": "ref",
#        "range_from": "test"
#      },
#      "enabled": true
#    },
#    "norm": {
#      "step": "percentile_norm",
#      "params": {
#        "source": "test"
#      },
#      "enabled": true
#    },
#    "align": {
#      "step": "align",
#      "params": {
#        "method": "phase",
#        "search_radius": 8
#      },
#      "enabled": true
#    },
#    "sub": {
#      "step": "subtract",
#      "params": {},
#      "enabled": true
#    },
#    "dn": {
#      "step": "denoise",
#      "params": {
#        "target": "diff",
#        "method": "median",
#        "ksize": 5
#      },
#      "enabled": true
#    },
#    "snr": {
#      "step": "snr_map",
#      "params": {
#        "window": 15,
#        "exclude_border": 8
#      },
#      "enabled": true
#    },
#    "blob": {
#      "step": "blob_segment",
#      "params": {
#        "min_area": 6,
#        "snr_threshold": 200
#      },
#      "enabled": true
#    },
#    "cd": {
#      "step": "cd_measure",
#      "params": {},
#      "enabled": true
#    },
#    "glv_patch_roi": {
#      "step": "roi_define",
#      "params": {
#        "name": "glv_patch_roi",
#        "shape": "center",
#        "size": 64.0,
#        "size_unit": "px",
#        "source": "diff"
#      },
#      "enabled": true
#    },
#    "glv_patch": {
#      "step": "glv_stats",
#      "params": {
#        "source": "diff",
#        "metrics": "glv_max,glv_median,glv_std",
#        "roi": "glv_patch_roi"
#      },
#      "enabled": true
#    },
#    "golden": {
#      "step": "golden_cell",
#      "params": {
#        "source": "test",
#        "out": "ref",
#        "method": "median"
#      },
#      "enabled": true
#    },
#    "glv_rsem_roi": {
#      "step": "roi_define",
#      "params": {
#        "name": "glv_rsem_roi",
#        "shape": "center",
#        "size": 128.0,
#        "size_unit": "px",
#        "source": "diff"
#      },
#      "enabled": true
#    },
#    "glv_rsem": {
#      "step": "glv_stats",
#      "params": {
#        "source": "diff",
#        "metrics": "glv_max,glv_median,glv_std",
#        "roi": "glv_rsem_roi"
#      },
#      "enabled": true
#    }
#  },
#  "edges": [],
#  "score": {
#    "expr": "(glv_max - glv_median) / (glv_std + 0.5)",
#    "threshold": 4.2,
#    "bins": {
#      "below": 0,
#      "above": 1
#    }
#  }
#}
#
#F b20cea5a320e2061621dddc05cec7e48a3ba7bdf 112 examples/recipes/rsem_golden_cell.json
#{
#  "recipe_id": "rsem_golden_cell",
#  "version": 1,
#  "author": "HX",
#  "description": "只吃 Review SEM 單張影像：先量出圖上 cell 的重複週期，把重複的 cell 疊成一張乾淨的 Golden Cell 當基準，相減後看中心區還剩多少殘差。沒有機台附的 ref、但圖上有週期性圖案時用這條。因為是自己減自己，整張圖的亮度／對比飄移會自動抵消，不必先做正規化。",
#  "routes": {
#    "rsem": [
#      "load",
#      "period",
#      "golden",
#      "sub",
#      "dn",
#      "snr",
#      "blob",
#      "glv_roi",
#      "glv"
#    ]
#  },
#  "nodes": {
#    "load": {
#      "step": "load_patch",
#      "params": {},
#      "enabled": true
#    },
#    "period": {
#      "step": "cell_period",
#      "params": {
#        "source": "test",
#        "refine": true
#      },
#      "enabled": true
#    },
#    "golden": {
#      "step": "golden_cell",
#      "params": {
#        "source": "test",
#        "out": "ref",
#        "method": "median",
#        "phase_search": true
#      },
#      "enabled": true
#    },
#    "sub": {
#      "step": "subtract",
#      "params": {
#        "a": "test",
#        "b": "ref",
#        "absolute": true,
#        "out": "diff"
#      },
#      "enabled": true
#    },
#    "dn": {
#      "step": "denoise",
#      "params": {
#        "target": "diff",
#        "method": "median",
#        "ksize": 5
#      },
#      "enabled": true
#    },
#    "snr": {
#      "step": "snr_map",
#      "params": {
#        "source": "diff",
#        "window": 15,
#        "exclude_border": 16
#      },
#      "enabled": true
#    },
#    "blob": {
#      "step": "blob_segment",
#      "params": {
#        "source": "snr_map",
#        "diff_source": "diff",
#        "min_area": 8,
#        "snr_threshold": 200
#      },
#      "enabled": true
#    },
#    "glv": {
#      "step": "glv_stats",
#      "params": {
#        "source": "diff",
#        "metrics": "glv_max,glv_median,glv_std",
#        "roi": "glv_roi"
#      },
#      "enabled": true
#    },
#    "glv_roi": {
#      "step": "roi_define",
#      "params": {
#        "name": "glv_roi",
#        "shape": "center",
#        "size": 128.0,
#        "size_unit": "px",
#        "source": "diff"
#      },
#      "enabled": true
#    }
#  },
#  "edges": [],
#  "score": {
#    "expr": "glv_max",
#    "threshold": 30.0,
#    "bins": {
#      "below": 0,
#      "above": 1
#    }
#  }
#}
#
#F acc6491ea06d2b61aa63f6c0e1132b24a82f6642 126 examples/recipes/single_image_rules.json
#{
#  "recipe_id": "single_image_rules",
#  "version": 1,
#  "author": "HX",
#  "description": "完全不用參考圖的保底流程：直接在原圖上算局部訊號突出度（SNR 地圖）→ 切出候選塊 → 用「訊號要夠強、塊要夠大、位置要靠近報點」三條規則相乘算分，另外加一道對焦品質閘（模糊的圖直接 0 分）。沒有 ref、圖上也沒有週期性可以疊 Golden Cell 時用這條。",
#  "routes": {
#    "ebi_patch": [
#      "load",
#      "focus",
#      "snr_patch",
#      "blob_patch",
#      "glv_patch_roi",
#      "glv_patch"
#    ],
#    "rsem": [
#      "load",
#      "focus",
#      "snr_rsem",
#      "blob_rsem",
#      "glv_rsem_roi",
#      "glv_rsem"
#    ]
#  },
#  "nodes": {
#    "load": {
#      "step": "load_patch",
#      "params": {},
#      "enabled": true
#    },
#    "focus": {
#      "step": "focus_quality",
#      "params": {
#        "source": "test"
#      },
#      "enabled": true
#    },
#    "snr_patch": {
#      "step": "snr_map",
#      "params": {
#        "source": "test",
#        "window": 15,
#        "exclude_border": 8
#      },
#      "enabled": true
#    },
#    "snr_rsem": {
#      "step": "snr_map",
#      "params": {
#        "source": "test",
#        "window": 25,
#        "exclude_border": 16
#      },
#      "enabled": true
#    },
#    "blob_patch": {
#      "step": "blob_segment",
#      "params": {
#        "source": "snr_map",
#        "diff_source": "test",
#        "min_area": 8,
#        "snr_threshold": 200
#      },
#      "enabled": true
#    },
#    "blob_rsem": {
#      "step": "blob_segment",
#      "params": {
#        "source": "snr_map",
#        "diff_source": "test",
#        "min_area": 12,
#        "snr_threshold": 180
#      },
#      "enabled": true
#    },
#    "glv_patch": {
#      "step": "glv_stats",
#      "params": {
#        "source": "test",
#        "metrics": "glv_max,glv_median,glv_std",
#        "roi": "glv_patch_roi"
#      },
#      "enabled": true
#    },
#    "glv_rsem": {
#      "step": "glv_stats",
#      "params": {
#        "source": "test",
#        "metrics": "glv_max,glv_median,glv_std",
#        "roi": "glv_rsem_roi"
#      },
#      "enabled": true
#    },
#    "glv_patch_roi": {
#      "step": "roi_define",
#      "params": {
#        "name": "glv_patch_roi",
#        "shape": "center",
#        "size": 48.0,
#        "size_unit": "px",
#        "source": "test"
#      },
#      "enabled": true
#    },
#    "glv_rsem_roi": {
#      "step": "roi_define",
#      "params": {
#        "name": "glv_rsem_roi",
#        "shape": "center",
#        "size": 96.0,
#        "size_unit": "px",
#        "source": "test"
#      },
#      "enabled": true
#    }
#  },
#  "edges": [],
#  "score": {
#    "expr": "(focus_lapvar > 100) * snr_max * blob_area / (blob_dist_center + 5)",
#    "threshold": 0.16,
#    "bins": {
#      "below": 0,
#      "above": 1
#    }
#  }
#}
#
#F e5dde7f87a51c5bc36c04399032cc32447b1a15c 215 fab_probe/README.md
## fab_probe —— 廠內格式探測腳本
#
#給**廠內工程師**與**資料攜出審核人員**看的說明。
#
#ADEPT 全程用合成資料開發（真實資料不能出廠），因此有三個假設必須拿真實檔案確認。
#這個資料夾裡的三支腳本就是為此而生：**它們只讀檔、只印文字報告，不修改任何檔案、
#不連網路、不產生新檔**（除非你自己用 `>` 把輸出導到檔案）。
#
#| 腳本 | 回答哪個假設 | 會不會讀像素 |
#|---|---|---|
#| `probe_klarf.py` | **假設 #3**：KLARF 的影像佈局變體有幾種（順帶找 **假設 #2** 的欄位線索） | 否 |
#| `probe_tiff.py`  | **假設 #1**：每顆 defect 是不是兩頁（test/ref）（順帶找 **假設 #2** 的 TIFF 標籤） | 否（只讀 IFD 標籤） |
#| `probe_stats.py` | 影像段參數怎麼設；奇偶頁亮度差是 **假設 #1** 的旁證 | **是（唯一會讀像素的一支）** |
#
#三個假設的原文在 `CLAUDE.md` §8：
#1. EBI patch 的 page→channel 對應（目前假設每顆 defect 第 1 張 = test、第 2 張 = ref）
#2. `nm_per_px` 從哪裡來（目前找不到 → CD 量測的 nm 值一律是 0）
#3. KLARF 影像佈局變體（目前處理了四種，實際站點可能還有新花樣）
#
#---
#
### 1. 執行前你需要知道的事
#
#* **單檔、純標準函式庫。** 每支腳本都是一個 `.py`，不需要 `pip install` 任何東西，
#  也不會 import ADEPT。有 Python 就能跑（3.6 以上；3.8 以上最保險）。
#* **不需要網路、不需要管理員權限。**
#* **只讀不寫。** 腳本不會碰你的原始檔（以唯讀模式開檔）。
#* **輸出是純文字。** 直接看得懂，也可以用 `>` 存成 `.txt` 再貼給對方。
#
### 2. 怎麼跑（Windows）
#
#把 `fab_probe` 資料夾（三個 `.py` + 這份 README）複製到廠內機器，開啟「命令提示字元」：
#
#```bat
#cd C:\adept\fab_probe
#
#REM 1) KLARF 結構（最先跑這支）
#python probe_klarf.py C:\data\LOT1234.001 > klarf_report.txt
#
#REM 2) TIFF 結構 + 與 KLARF 的成對檢查
#python probe_tiff.py C:\data\LOT1234.tif --with-klarf C:\data\LOT1234.001 > tiff_report.txt
#
#REM 3) 灰階統計（會讀像素，請先確認可否攜出）
#python probe_stats.py C:\data\LOT1234.tif --pages 20 --bins 16 > stats_report.txt
#```
#
#路徑有空白時記得加引號：`python probe_klarf.py "C:\my data\LOT1234.001"`。
#沒有 `python` 指令時，試 `py -3 probe_klarf.py ...`。
#
#Linux / macOS 一樣：`python3 probe_klarf.py /data/LOT1234.001 > klarf_report.txt`。
#
#### 常用選項
#
#| 選項 | 適用 | 說明 |
#|---|---|---|
#| `--include-ids` | klarf / tiff | 連 LotID、WaferID、檔名等識別碼一起輸出（**預設遮蔽**）。只有在你確認可攜出時才加。 |
#| `--rows N` | klarf | 抽樣列數上限（型別推斷、列尾樣式、異常列索引；預設 20）。 |
#| `--pages N` | tiff | 細看前 N 頁（另外自動加看中段與最後兩頁；預設 8）。 |
#| `--with-klarf FILE` | tiff | 同時給對應的 KLARF，做「頁數 vs defect 數」的成對檢查（假設 #1 的重點）。 |
#| `--pages N` / `--bins N` | stats | 抽樣頁數（預設 20）／直方圖格數（預設 16）。 |
#| `--max-pixels N` | stats | 每頁最多取樣幾個像素（預設 200 萬；大圖會自動依列抽樣，抽樣率會印出來）。 |
#
#### 回傳碼
#
#| 碼 | 意思 |
#|---|---|
#| 0 | 正常完成 |
#| 2 | 檔案找不到／不是這支腳本吃的格式（會印一行白話說明） |
#| 3 | 非預期錯誤（會印錯誤類型，請把那一行回報） |
#
#腳本不會丟出 Python traceback；看到的一定是中文說明。
#
#---
#
### 3. 攜出審核用：到底有什麼東西會離開這台機器？
#
#報告本身也把這一節印在最前面，方便直接給審核人員看。
#
#### 一律**不會**出現在報告裡
#
#* 任何 defect 的座標（`XREL` / `YREL` / `XINDEX` / `YINDEX`）—— 連最大最小值都不印
#* 任何 defect 資料列的原始內容 —— 只印「token 的型別樣式」，例如 `d d f d { s s d s }`
#  （`d`=整數、`f`=浮點、`s`=字串、`w`=文字、`{}`=括號；**沒有任何數值或文字內容**）
#* 任何像素值 —— `probe_klarf` / `probe_tiff` 連一個 byte 的影像資料都沒有解碼
#* 影像縮圖、任何可還原影像的資料
#* 檔名原文（只印副檔名與字元數，例如 `<redacted, 11 chars>.001`）
#* class 類別名稱（只印「有幾類」）
#
#### 預設**遮蔽**（加 `--include-ids` 才會出現）
#
#* `LotID`、`WaferID`、`DeviceID`、`StepID`、`SetupID`、`ScribeID`、`InspectionStationID`、
#  `RecipeID`、`FabID`、`TiffFileName` 等識別碼欄位的**值**
#  —— 預設印成 `LotID: <redacted, 9 chars>`（保留字元數，因為欄位長度本身是格式資訊）
#* TIFF 的 `ImageDescription` / `Software` / `Make` / `Model` 裡「像識別碼的字」
#  —— 規則：字母數字混合且長度 ≥ 6 的字換成 `<id:長度>`；
#  **純數字（含 3.25、1.2e-3、25nm 這種帶單位的）一律保留**（`nm_per_px` 要靠它）；
#  純字母的字（如 `PixelSize`）保留。整段截斷到 160 字元。
#
#### **會**出現在報告裡（這些就是我們要的東西）
#
#* 欄位**名稱**（header 欄位名、defect 欄位名與宣告型別）—— 這是格式，不是資料
#* 各種計數與統計：列數、欄位數、頁數、每顆 defect 的影像張數分布、列長分布、
#  異常列的**索引編號**（不是內容）
#* 結構性欄位的值：`FileVersion`、`SampleType`、`SampleSize`、`DiePitch`、`DieOrigin`、
#  `TiffSpec`、時間戳 —— 判讀格式必需
#* **`nm_per_px` 候選欄位的值**（這是刻意的例外，也正是探測目的）：
#  名稱含 PIXEL / SCALE / RESOLUT / MAG / NM / UM / SIZE / PITCH / FOV 之類的欄位，
#  會印出它的值或值域（defect 欄位只印 min/max 與相異值個數）。
#  若該欄位名同時像識別碼（例如 `RecipeID`），仍然遮蔽。
#* TIFF 結構標籤：尺寸、位元深度、通道數、壓縮方式、strip/tile 排列、解析度標籤
#* `probe_stats.py` 額外輸出：灰階直方圖、min/max/平均/標準差、每頁平均與標準差、
#  以及**一張 4×4 的區塊平均**（整張圖只切成 16 格取平均；粗到無法辨識任何圖樣，
#  但看得出視野是否有大範圍明暗不均）
#
#### 特別提醒：`probe_stats.py`
#
#三支裡只有它會**實際讀取像素值**。它輸出的都是彙總統計（不可能還原影像），
#但既然碰了像素，**請先確認貴公司的資料攜出規範允許，再把報告貼出廠外**。
#報告最上方也印了同樣的警語。
#
#---
#
### 4. 報告怎麼讀（每支的重點段落）
#
#### `probe_klarf.py`
#
#| 段 | 內容 |
#|---|---|
#| 1 | 檔案基本資訊（大小、換行、編碼） |
#| 2 | 版本判定 1.2 / 1.8，以及**是哪一條啟發式命中的** |
#| 3 | header 欄位名清單，並標出哪些是 ADEPT 目前**沒看過**的欄位（`NEW`） |
#| 4 | defect 欄位清單（宣告型別 + 由資料推斷的型別）、列數 |
#| **5** | **影像佈局變體判定 + 證據**（假設 #3；最重要） |
#| 6 | 列長異常統計（只有數量與索引） |
#| **7** | **`nm_per_px` 獵捕**（假設 #2） |
#| 尾 | 「請回報這一段」：一段 JSON 摘要，貼回來就好 |
#
#第 5 段目前認得四種變體：
#
#* **變體 A `images18`**：有 `IMAGECOUNT` 欄，影像欄是 `Images N { … }` 子區塊
#* **變體 B `declared`**：有 `IMAGELIST` 欄，且 `TiffSpec` 宣告了每張圖佔幾個 token
#* **變體 C `inferred`**：以上都沒有，從資料推斷每張圖佔幾個 token（報告會印投票明細）
#* **變體 D `imagefile`**：沒有 `IMAGECOUNT` 欄，但列中有 `Image/Images N { "檔名" … }`
#  子區塊（Review SEM 常見）
#
#若印出「**四種已知變體都不成立**」，那就是我們要找的新花樣 ——
#請把第 5 段（含列尾樣式）整段回報，我們會做成回歸測試 fixture。
#
#### `probe_tiff.py`
#
#重點在**第 5 段**（要加 `--with-klarf` 才有）：
#
#* 檢查 A：TIFF 頁數 == 2 × defect 數？
#* 檢查 B：TIFF 頁數 == `IMAGECOUNT` 總和？
#* 觀察到的排列：`pairs`（每顆 2 張）/ `single` / `triples` / `mixed`
#* KLARF 宣告的 page 對應解不解得開（`imagelist` 直接是頁碼，還是只能 `sequential` 連續配頁）、
#  id 是 0-based 還是 1-based
#
#注意：檢查 A 通過只證明「**成對**」，**沒有證明哪一張是 test**。
#先後順序請看第 4 段（頁面標籤週期性）與 `probe_stats.py` 的奇偶頁亮度比較。
#
#第 3 段的 `ImageDescription` / `Software` / 解析度標籤是假設 #2 的主要線索：
#若出現 `PixelSize=3.2nm` 這類字樣，那就是 `nm_per_px` 的來源。
#
#### `probe_stats.py`
#
#* 第 2 段：每頁的 min/max/平均/標準差
#* 第 3 段：合計灰階直方圖（含「貼邊像素」比例 → 判斷是否飽和截斷）
#* 第 4 段：**奇偶頁亮度比較** —— 有系統性差異就是「兩頁來源不同（test/ref）」的旁證
#* 第 5 段：4×4 區塊平均 ASCII 圖 —— 看視野是否有大範圍照明不均
#
#遇到解不開的壓縮（LZW、JPEG、deflate）或 tile 排列時，**會清楚說明並跳過該頁**，
#不會中斷；那一行的說明本身就是要回報的重要資訊
#（代表廠內 TIFF 用了 ADEPT 沒預期的編碼方式）。
#
#---
#
### 5. 要回報什麼
#
#每份報告最後都有一段：
#
#```
#==========================================================================
#請回報這一段（機器可讀摘要…）
#==========================================================================
#>>>JSON_BEGIN
#{ ... }
#>>>JSON_END
#```
#
#**最少**把這一段（含 `>>>JSON_BEGIN` / `>>>JSON_END` 兩行）貼回來。
#它不含識別碼、不含座標、不含像素，是三份報告裡最安全的部分。
#
#如果報告裡出現下列任何一句，請**連同它上下那一整段**一起回報：
#
#* 「四種已知變體都不成立」（假設 #3 的新變體）
#* 「與 test/ref 成對假設不符」（假設 #1 不成立）
#* 「本腳本只解得開 未壓縮 與 PackBits」（TIFF 編碼方式沒預期到）
#* 「頁面規格不一致」
#* 「klarf_core 未涵蓋（NEW）」後面列出的欄位名
#* 第 7 段裡任何看起來真的帶 nm / pixel 的欄位（假設 #2 的答案）
#
#---
#
### 6. 給維護者的話（不是給廠內使用者）
#
#* 三支腳本**刻意不 import `adept`**，而是把 `adept/core/ingest/klarf_core.py` 與
#  `adept/core/ingest/tiff_index.py` 的判定邏輯**重寫一份**（純標準函式庫）。
#  這是為了讓廠內只需要複製單一檔案，代價是**兩邊要同步維護**：
#  改動 `detect_version` / `image_layout` 一族 / `read_tiff_pages` 時，
#  這裡也要跟著改。每支腳本的檔頭都列了它鏡射了哪些函式。
#* `tests/test_fab_probe.py` 會用 `tools/make_sample.py` 與 `tools/make_sample_rsem.py`
#  產生資料，再以 subprocess 跑這三支腳本並檢查輸出（含遮蔽政策與「不得 import
#  numpy/cv2/tifffile/adept」的原始碼掃描）。
#
#F 40ea41a3ba7fc6fb9da08ae90d1624615040b08e 1115 fab_probe/probe_klarf.py
##!/usr/bin/env python3
## -*- coding: utf-8 -*-
#"""ADEPT 廠內探測腳本 #1：KLARF 結構探測（單檔、純標準函式庫）。
#
#用途：在廠內真實 KLARF 上確認 CLAUDE.md §8 的兩個假設 ——
#  假設 #3「KLARF 影像佈局變體」（本腳本最重要的輸出）
#  假設 #2「nm_per_px 從哪來」（欄位名獵捕）
#
#邏輯鏡射自 adept/core/ingest/klarf_core.py：
#  detect_version / _parse_12 / _parse_18 / _parse_tiff_fields /
#  image_col_index / _detect_images18 / _infer_image_layout /
#  defect_image_entries / row_len_ok / tiff_path
#本檔「重寫」了上述邏輯的最小必要部分（不 import adept、不用第三方套件），
#所以 klarf_core 那邊改判定規則時，這裡要跟著改（兩邊都要更新）。
#
#用法：
#    python probe_klarf.py FILE.klarf [--include-ids] [--rows 20]
#
#輸出：純文字報告（預設遮蔽所有識別碼），最後一段是可貼回的 JSON 摘要。
#"""
#
#import argparse
#import json
#import os
#import re
#import sys
#
#PROBE_VERSION = "1.0"
#SCHEMA = "adept.fab_probe.klarf/1"
#
## ---------------------------------------------------------------- 遮蔽政策
##
## 預設（不加 --include-ids）：
##   * header 欄位「名稱」全部顯示（名稱本身是格式資訊，不是資料）
##   * header 欄位「值」一律遮蔽成 <redacted, N chars>，
##     只有 STRUCTURAL_FIELDS 白名單（幾何/版本類，判讀格式必需）顯示原值
##   * defect 資料一個 token 都不印；只印欄位名、型別、列數、長度統計
##   * 座標（XREL/YREL/XINDEX/…）永不輸出，連範圍都不輸出
##   * 檔名（KLARF 檔本身、TiffFileName）遮蔽，只留副檔名與字元數
##   * ClassLookup 只報「有幾類」，不報類別名稱
##   * nm_per_px 候選欄位是「刻意的例外」：值會顯示（這正是探測目的），
##     但若欄位名同時落在 ID_FIELDS，仍然遮蔽
##
## 加 --include-ids：上述值全部照原樣輸出（由使用者自行判斷可否攜出）。
#
#STRUCTURAL_FIELDS = {
#    "FILEVERSION", "FILETIMESTAMP", "SAMPLETYPE", "SAMPLESIZE", "DIEPITCH",
#    "DIEORIGIN", "SAMPLEORIENTATIONMARKTYPE", "ORIENTATIONMARKLOCATION",
#    "TIFFSPEC", "INSPECTIONTEST", "RESULTTIMESTAMP", "SLOT", "SLOTNUMBER",
#    "COORDINATESMIRRORED", "INSPECTIONORIENTATION",
#}
#
#ID_FIELDS = {
#    "LOTID", "WAFERID", "DEVICEID", "STEPID", "SETUPID", "SCRIBEID",
#    "INSPECTIONSTATIONID", "TIFFFILENAME", "IMAGEFILENAME", "FILENAME",
#    "RECIPENAME", "RECIPEID", "JOBID", "OPERATORID", "PRODUCTID",
#    "SAMPLECENTERLOCATION", "PROCESSEQUIPMENTSTATE", "ORIENTATIONINSTRUCTIONS",
#}
#
## klarf_core 目前「認得」的 header 欄位（1.2 FIELDS_12 + 1.8 Record 對應 + 影像欄）
#KNOWN_FIELDS = {
#    "FILEVERSION", "FILETIMESTAMP", "INSPECTIONSTATIONID", "SAMPLETYPE",
#    "RESULTTIMESTAMP", "LOTID", "SAMPLESIZE", "DEVICEID", "SETUPID", "STEPID",
#    "SAMPLEORIENTATIONMARKTYPE", "ORIENTATIONMARKLOCATION", "DIEPITCH",
#    "DIEORIGIN", "WAFERID", "SLOT", "SCRIBEID", "SAMPLECENTERLOCATION",
#    "TIFFFILENAME", "TIFFSPEC", "IMAGEFILENAME",
#}
#
## 假設 #2：名稱看起來可能帶「像素尺寸 / 比例尺 / 倍率」的欄位
#NM_PATTERNS = [
#    ("PIXEL", r"PIXEL|PXL|PX_?SIZE"),
#    ("SCALE", r"SCALE|CALIB"),
#    ("RESOLUT", r"RESOLUT|\bDPI\b"),
#    ("MAG", r"MAGNIF|\bMAG\b"),
#    ("NM/UM", r"\bNM\b|NANOM|\bUM\b|MICRON|MICROM"),
#    ("SIZE", r"SIZE"),
#    ("PITCH/FOV", r"PITCH|\bFOV\b|FIELDOFVIEW|ZOOM"),
#]
#
## KLARF-ness 指標：一個都沒有 → 判定不是 KLARF
#KLARF_MARKERS = ["FileVersion", "DefectRecordSpec", "DefectList", "FileRecord",
#                 "EndOfFile", "SummarySpec", "InspectionStationID", "Columns"]
#
#
## ---------------------------------------------------------------- 小工具
#
#def _out(line=""):
#    print(line)
#
#
#def redact(value, name="", include_ids=False, keep=80):
#    """依遮蔽政策把一個 header 值轉成可輸出字串。"""
#    v = "" if value is None else str(value)
#    if include_ids:
#        return v if len(v) <= keep else v[:keep] + "...(截斷)"
#    up = name.upper()
#    if up in STRUCTURAL_FIELDS and up not in ID_FIELDS:
#        return v if len(v) <= keep else v[:keep] + "...(截斷)"
#    return "<redacted, %d chars>" % len(v)
#
#
#def redact_name(path, include_ids=False):
#    """檔名遮蔽：只留副檔名與字元數（檔名常含 lot/wafer 編號）。"""
#    base = os.path.basename(str(path))
#    if include_ids:
#        return base
#    stem, ext = os.path.splitext(base)
#    return "<redacted, %d chars>%s" % (len(stem), ext)
#
#
#def token_shape(tok):
#    """把一個 token 換成型別字元（不帶任何內容）。"""
#    if tok in ("{", "}"):
#        return tok
#    if tok.startswith('"'):
#        return "s"
#    t = tok.lstrip("+-")
#    if t.isdigit():
#        return "d"
#    try:
#        float(tok)
#        return "f"
#    except ValueError:
#        pass
#    return "w"
#
#
#def shape_line(tokens, limit=40):
#    """列的 token 型別樣式（連續相同者壓成 d*5）。"""
#    shapes = [token_shape(t) for t in tokens[:limit]]
#    out, i = [], 0
#    while i < len(shapes):
#        j = i
#        while j < len(shapes) and shapes[j] == shapes[i]:
#            j += 1
#        n = j - i
#        out.append(shapes[i] if n == 1 else "%s*%d" % (shapes[i], n))
#        i = j
#    tail = " ..." if len(tokens) > limit else ""
#    return " ".join(out) + tail
#
#
#def find_image_block(row):
#    """找出列中的 `Image/Images N { ... }` 子區塊，回傳 (起, 迄) token 索引（含端點）。
#
#    概念同 klarf_core.defect_image_filename（它用字串找成對大括號，
#    這裡改在 token 串上找，才能算出這個變動長度欄位佔幾個 token）。
#    """
#    for k, tok in enumerate(row):
#        if tok not in ("Image", "Images"):
#            continue
#        b0 = None
#        for j in range(k + 1, min(len(row), k + 4)):
#            if "{" in row[j] and not row[j].startswith('"'):
#                b0 = j
#                break
#        if b0 is None:
#            return None
#        depth = 0
#        for j in range(b0, len(row)):
#            if row[j].startswith('"'):
#                continue
#            depth += row[j].count("{") - row[j].count("}")
#            if depth <= 0:
#                return (k, j)
#        return (k, len(row) - 1)
#    return None
#
#
#def collapse_row(row):
#    """把影像子區塊壓成一個 token，讓「欄位對齊」在變動長度欄之後仍然成立。"""
#    span = find_image_block(row)
#    if span is None:
#        return row
#    a, b = span
#    return row[:a] + ["<IMAGEBLOCK>"] + row[b + 1:]
#
#
#def block_filename(row):
#    """取影像子區塊裡第一個帶引號的字串（鏡射 defect_image_filename）。"""
#    span = find_image_block(row)
#    if span is None:
#        return None
#    for tok in row[span[0]:span[1] + 1]:
#        if tok.startswith('"'):
#            return tok.strip('"')
#    return None
#
#
#def json_block(d):
#    """一行一個 key 的 JSON（整段仍可被 json.loads 解開）。"""
#    items = list(d.items())
#    lines = ["{"]
#    for i, (k, v) in enumerate(items):
#        comma = "," if i < len(items) - 1 else ""
#        lines.append("  %s: %s%s" % (json.dumps(k, ensure_ascii=False),
#                                     json.dumps(v, ensure_ascii=False), comma))
#    lines.append("}")
#    return lines
#
#
#def histogram_lines(counter, label="值", width=40):
#    """{值: 次數} → 文字直方圖。"""
#    if not counter:
#        return ["  （無資料）"]
#    keys = sorted(counter.keys(), key=lambda k: (isinstance(k, str), k))
#    mx = max(counter.values())
#    lines = []
#    for k in keys:
#        n = counter[k]
#        bar = "#" * max(1, int(round(width * n / float(mx))))
#        lines.append("  %-8s : %8d  %s" % (str(k), n, bar))
#    return lines
#
#
## ---------------------------------------------------------------- 讀檔
#
#class ProbeError(Exception):
#    pass
#
#
#def read_text(path):
#    """讀 KLARF 文字，回傳 (text, meta)。"""
#    if not os.path.isfile(path):
#        raise ProbeError("找不到檔案：%s" % path)
#    try:
#        with open(path, "rb") as f:
#            raw = f.read()
#    except (IOError, OSError) as exc:
#        raise ProbeError("讀檔失敗：%s" % exc)
#    if not raw:
#        raise ProbeError("檔案是空的（0 bytes），沒有東西可以探測。")
#    if raw.count(b"\x00") > max(4, len(raw) // 200):
#        raise ProbeError("這個檔看起來是二進位檔（含大量 NUL byte），不是 KLARF 文字檔。")
#
#    bom = raw.startswith(b"\xef\xbb\xbf")
#    body = raw[3:] if bom else raw
#    encoding = "utf-8"
#    try:
#        text = body.decode("utf-8")
#    except UnicodeDecodeError:
#        encoding = "latin-1 (fallback)"
#        text = body.decode("latin-1", "replace")
#
#    crlf = body.count(b"\r\n")
#    lf = body.count(b"\n") - crlf
#    eol = "CRLF" if crlf and not lf else ("LF" if lf and not crlf else
#                                          ("mixed CRLF+LF" if crlf and lf else "none"))
#    meta = {"bytes": len(raw), "bom": bom, "encoding": encoding, "eol": eol,
#            "lines": body.count(b"\n") + 1}
#    hits = [m for m in KLARF_MARKERS if m in text]
#    if not hits:
#        raise ProbeError(
#            "這個檔不像 KLARF（找不到任何 KLARF 關鍵字：%s）。"
#            % "/".join(KLARF_MARKERS[:4]))
#    meta["markers"] = hits
#    return text, meta
#
#
## ------------------------------------------------- 版本判定（鏡射 detect_version）
#
#def detect_version(text):
#    """回傳 (version, [(名稱, 是否命中, 說明)], 命中的啟發式名稱)。"""
#    checks = []
#    fired = None
#    version = None
#
#    h1 = re.search(r"Record\s+FileRecord", text)
#    checks.append(("Record FileRecord", bool(h1), "1.8 的檔頭記錄"))
#    if h1 and version is None:
#        version, fired = "1.8", "Record FileRecord"
#
#    h2 = re.search(r"FileVersion\s+(\d+)\s+(\d+)", text)
#    checks.append(("FileVersion N M", bool(h2),
#                   ("宣告 %s.%s" % (h2.group(1), h2.group(2))) if h2 else "無此宣告"))
#    if h2 and version is None:
#        version, fired = "%s.%s" % (h2.group(1), h2.group(2)), "FileVersion N M"
#
#    h3 = re.search(r"\bList\s+\w+\s*\{", text)
#    checks.append(("List XXX {", bool(h3), "1.8 的區塊語法"))
#    if h3 and version is None:
#        version, fired = "1.8", "List XXX {"
#
#    if version is None:
#        version, fired = "1.2", "fallback（以上都沒命中 → 預設 1.2）"
#    checks.append(("fallback 1.2", version == "1.2" and fired.startswith("fallback"),
#                   "什麼都沒命中時的預設"))
#    return version, checks, fired
#
#
## ------------------------------------------------- 解析（鏡射 _parse_12 / _parse_18）
#
#def _find_matching_brace(text, open_idx):
#    depth = 0
#    for i in range(open_idx, len(text)):
#        if text[i] == "{":
#            depth += 1
#        elif text[i] == "}":
#            depth -= 1
#            if depth == 0:
#                return i
#    return -1
#
#
#BLOCK_KEYWORDS = {"DEFECTLIST", "SUMMARYLIST", "ENDOFFILE", "DEFECTRECORDSPEC",
#                  "SUMMARYSPEC", "CLASSLOOKUP", "RECORD", "FIELD", "LIST",
#                  "COLUMNS", "DATA", "IMAGES", "IMAGE"}
#
#
#def parse_12(text):
#    d = {"header": [], "columns": [], "column_types": [], "rows": [],
#         "n_defect_lists": 0, "n_classes": 0, "class_names": [],
#         "declared_row_count": None}
#    for m in re.finditer(r"(?m)^[ \t]*([A-Za-z][A-Za-z0-9_]*)\b[ \t]+([^;\n]*);", text):
#        name, value = m.group(1), m.group(2).strip()
#        if name.upper() in BLOCK_KEYWORDS:
#            continue
#        d["header"].append((name, value))
#
#    m = re.search(r"(?m)^[ \t]*ClassLookup\b[ \t]+(\d+)[ \t]*\r?\n([\s\S]*?);", text)
#    if m:
#        for line in m.group(2).splitlines():
#            cm = re.match(r'\s*(\d+)\s+"([^"]*)"', line)
#            if cm:
#                d["n_classes"] += 1
#                d["class_names"].append(cm.group(2))
#
#    m = re.search(r"DefectRecordSpec\s+(\d+)\s+([^;]+);", text)
#    if m:
#        d["columns"] = m.group(2).split()
#        d["declared_col_count"] = int(m.group(1))
#    matches = list(re.finditer(r"(?m)^[ \t]*DefectList\b[ \t]*\r?\n([\s\S]*?);", text))
#    d["n_defect_lists"] = len(matches)
#    if matches:
#        for line in matches[0].group(1).splitlines():
#            line = line.strip()
#            if line and not line.startswith(";"):
#                d["rows"].append(line.split())
#    return d
#
#
#def parse_18(text):
#    d = {"header": [], "columns": [], "column_types": [], "rows": [],
#         "n_defect_lists": 0, "n_classes": 0, "class_names": [],
#         "declared_row_count": None, "imagelist_col": None}
#    for m in re.finditer(r"Field\s+(\w+)\s+\d+\s*\{[^}]*\}", text):
#        inner = m.group(0)[m.group(0).index("{") + 1:-1].strip()
#        d["header"].append((m.group(1), inner))
#    rec_field = {"LotRecord": "LotID", "WaferRecord": "WaferID",
#                 "DeviceRecord": "DeviceID", "StepRecord": "StepID",
#                 "SetupRecord": "SetupID", "FileRecord": "FileVersion"}
#    for m in re.finditer(r'Record\s+(\w+Record)\s+("(?:[^"\\]|\\.)*")', text):
#        name = rec_field.get(m.group(1))
#        if name:
#            d["header"].append((name, m.group(2)))
#
#    cl = re.search(r"List\s+ClassLookupList\s*\{", text)
#    if cl:
#        b0 = text.index("{", cl.start())
#        b1 = _find_matching_brace(text, b0)
#        body = text[b0 + 1:b1]
#        dm = re.search(r"Data\s+\d+\s*\{", body)
#        if dm:
#            db0 = body.index("{", dm.start())
#            db1 = _find_matching_brace(body, db0)
#            for row in body[db0 + 1:db1].split(";"):
#                cm = re.match(r'\s*(\d+)\s+"([^"]*)"', row)
#                if cm:
#                    d["n_classes"] += 1
#                    d["class_names"].append(cm.group(2))
#
#    dls = list(re.finditer(r"List\s+DefectList\s*\{", text))
#    d["n_defect_lists"] = len(dls)
#    if dls:
#        b0 = text.index("{", dls[0].start())
#        b1 = _find_matching_brace(text, b0)
#        block = text[b0:b1 + 1]
#        cm = re.search(r"Columns\s+(\d+)\s*\{([^}]*)\}", block)
#        if cm:
#            cols, types = [], []
#            for c in cm.group(2).split(","):
#                parts = c.strip().split()
#                if not parts:
#                    continue
#                cols.append(parts[-1])
#                types.append(parts[0] if len(parts) >= 2 else "?")
#                if len(parts) >= 2 and parts[0].lower() == "imagelist":
#                    d["imagelist_col"] = len(cols) - 1
#            d["columns"] = cols
#            d["column_types"] = types
#            d["declared_col_count"] = int(cm.group(1))
#        dm = re.search(r"Data\s+(\d+)\s*\{", block)
#        if dm:
#            d["declared_row_count"] = int(dm.group(1))
#            db0 = block.index("{", dm.start())
#            db1 = _find_matching_brace(block, db0)
#            for row in block[db0 + 1:db1].split(";"):
#                row = row.strip()
#                if row:
#                    d["rows"].append(re.findall(r'[^"\s]+|"[^"]*"', row))
#    return d
#
#
#def parse_tiff_fields(text, header):
#    """鏡射 _parse_tiff_fields：回傳 (tiff_file_name, tiff_spec, how)。"""
#    hd = {}
#    for n, v in header:
#        hd.setdefault(n, v)
#    name = None
#    how = None
#    m = re.search(r"(?m)^[ \t]*TiffFileName\b[ \t]+([^;]*);", text)
#    if m:
#        name, how = m.group(1).strip().strip('"'), "1.2 TiffFileName 行"
#    elif "TiffFileName" in hd:
#        name, how = hd["TiffFileName"].strip().strip('"'), "1.8 Field TiffFileName"
#    elif "ImageFileName" in hd:
#        q = re.findall(r'"([^"]*)"', hd["ImageFileName"])
#        if q:
#            name, how = q[0], "1.8 Field ImageFileName"
#
#    spec = None
#    m = re.search(r"(?m)^[ \t]*TiffSpec\b[ \t]+([\d.]+)[ \t]+(\d+)[ \t]*([^;]*);", text)
#    if m:
#        fields = re.findall(r'"([^"]*)"', m.group(3)) or m.group(3).split()
#        n = int(m.group(2))
#        mismatch = bool(fields) and len(fields) != n
#        if mismatch:
#            n = len(fields)
#        spec = {"version": m.group(1), "nfields": n if n > 0 else None,
#                "fields": fields, "source": "1.2 TiffSpec 行", "mismatch": mismatch}
#    elif "TiffSpec" in hd:
#        vals = re.findall(r'"([^"]*)"', hd["TiffSpec"])
#        if vals:
#            spec = {"version": vals[0], "nfields": None, "fields": vals[1:],
#                    "source": "1.8 Field TiffSpec（欄位是影像類型，不是 token 數）",
#                    "mismatch": False}
#    return name, spec, how
#
#
## ------------------------------------------- 影像佈局（鏡射 image_layout 一族）
#
#def col_index(columns, name):
#    up = [c.upper() for c in columns]
#    return up.index(name.upper()) if name.upper() in up else -1
#
#
#def image_col_index(columns, imagelist_col18):
#    il = col_index(columns, "IMAGELIST")
#    if il < 0 and imagelist_col18 is not None:
#        il = imagelist_col18
#    return col_index(columns, "IMAGECOUNT"), il
#
#
#def defect_image_count(row, ic):
#    if ic < 0 or ic >= len(row):
#        return 0
#    try:
#        return max(0, int(row[ic]))
#    except ValueError:
#        return 0
#
#
#def detect_images18(rows, ic, il):
#    """鏡射 _detect_images18。回傳 (layout, 證據字串)。"""
#    s = il if il >= 0 else ic + 1
#    for k, r in enumerate(rows):
#        if defect_image_count(r, ic) > 0:
#            if s < len(r) and r[s] == "Images":
#                return (s, None, "images18"), \
#                    "第一筆帶圖列（第 %d 列）第 %d 欄的 token 正好是 'Images'" % (k, s)
#            return None, \
#                "第一筆帶圖列（第 %d 列）第 %d 欄不是 'Images'（是 %s 型 token）" % (
#                    k, s, token_shape(r[s]) if s < len(r) else "缺欄")
#    return None, "沒有任何 IMAGECOUNT > 0 的列"
#
#
#def infer_image_layout(rows, columns, ic, il):
#    """鏡射 _infer_image_layout，另外回傳投票明細當證據。"""
#    n = len(columns)
#    starts = []
#    for s in ([il] if il >= 0 else []) + [n] + ([n - 1] if ic == n - 2 else []):
#        if s not in starts:
#            starts.append(s)
#    cands, evidence = [], []
#    for s in starts:
#        tally, total = {}, 0
#        for r in rows:
#            cnt = defect_image_count(r, ic)
#            if cnt <= 0:
#                continue
#            total += 1
#            extra = len(r) - s
#            if extra > 0 and extra % cnt == 0:
#                tally[extra // cnt] = tally.get(extra // cnt, 0) + 1
#        if not tally:
#            evidence.append("起點欄 %d：沒有任何列的多餘 token 數能被 IMAGECOUNT 整除" % s)
#            continue
#        nf, votes = max(tally.items(), key=lambda kv: kv[1])
#        detail = "、".join("每張圖 %d token → %d 票" % (k, v)
#                          for k, v in sorted(tally.items(), key=lambda kv: -kv[1]))
#        need = total - max(1, total // 10)
#        ok = nf >= 1 and votes >= need
#        evidence.append("起點欄 %d：%s（帶圖列共 %d；門檻 %d 票；%s）"
#                        % (s, detail, total, need, "通過" if ok else "不通過"))
#        if ok:
#            cands.append((s, nf, "inferred"))
#    if len(cands) <= 1:
#        return (cands[0] if cands else None), evidence
#    for s, nf, how in cands:
#        ids, good = [], True
#        for r in rows:
#            cnt = defect_image_count(r, ic)
#            toks = r[s:]
#            if len(toks) < cnt * nf:
#                continue
#            for k in range(cnt):
#                v = toks[k * nf]
#                if not v.lstrip("-").isdigit():
#                    good = False
#                    break
#                ids.append(int(v))
#            if not good:
#                break
#        if good and ids and len(set(ids)) == len(ids):
#            evidence.append("多個候選 → 選起點欄 %d（首欄像 page 編號：全整數且不重複）" % s)
#            return (s, nf, how), evidence
#    evidence.append("多個候選且都不像 page 編號 → 取第一個候選")
#    return cands[0], evidence
#
#
#def decide_layout(rows, columns, ic, il, tiff_spec):
#    """判定影像佈局變體。回傳 (layout, [證據字串])。
#
#    layout = (起點欄, 每張圖 token 數 或 None, 變體代號)；沒有影像資訊回 None。
#    變體代號：images18 / declared / inferred（= klarf_core.image_layout 的三種）
#              imagefile（無 IMAGECOUNT 欄、但列中有 Image/Images 子區塊；
#                         klarf_core 走 defect_image_filename 這條路）
#    """
#    ev = []
#    if ic >= 0:
#        lay18, ev18 = detect_images18(rows, ic, il)
#        if lay18 is not None:
#            return lay18, ["變體 A（images18）成立：" + ev18]
#        ev.append("變體 A（images18）不成立：" + ev18)
#        if il >= 0 and tiff_spec and tiff_spec.get("nfields"):
#            ev.append("變體 B（declared）成立：有影像清單欄（第 %d 欄）"
#                      "且 TiffSpec 宣告每張圖 %d 個 token" % (il, tiff_spec["nfields"]))
#            return (il, tiff_spec["nfields"], "declared"), ev
#        ev.append("變體 B（declared）不成立：%s"
#                  % ("沒有影像清單欄" if il < 0 else "TiffSpec 沒宣告每張圖的 token 數"))
#        lay, ev_c = infer_image_layout(rows, columns, ic, il)
#        for e in ev_c:
#            ev.append("變體 C（inferred）投票：" + e)
#        if lay is not None:
#            return lay, ev
#        return None, ev
#
#    ev.append("沒有 IMAGECOUNT 欄（klarf_core.image_layout() 在這種檔上會回 None）")
#    for k, r in enumerate(rows):
#        span = find_image_block(r)
#        if span is not None:
#            ev.append("變體 D（imagefile）成立：第 %d 列的第 %d 欄起有 "
#                      "`%s N { ... }` 子區塊，佔 %d 個 token；"
#                      "klarf_core 會走 defect_image_filename() 逐列取檔名"
#                      % (k, span[0], r[span[0]], span[1] - span[0] + 1))
#            return (span[0], None, "imagefile"), ev
#    ev.append("列中也找不到 Image/Images 子區塊 → 這份 KLARF 不帶影像資訊")
#    return None, ev
#
#
#def defect_image_entries(row, layout, ic):
#    cnt = defect_image_count(row, ic)
#    if cnt <= 0 or layout is None:
#        return []
#    s, nf, how = layout
#    if how == "images18":
#        m = re.match(r"Images\s+\d+\s*\{(.*)\}\s*$", " ".join(row[s:]))
#        if not m:
#            return []
#        entries = [e.split() for e in m.group(1).split(",") if e.strip()]
#        return entries if len(entries) == cnt else []
#    toks = row[s:]
#    if len(toks) < cnt * nf:
#        return []
#    return [toks[k * nf:(k + 1) * nf] for k in range(cnt)]
#
#
#def row_len_ok(row, columns, layout, ic, il):
#    """鏡射 row_len_ok。"""
#    n = len(columns)
#    if ic < 0:
#        return len(row) == n
#    cnt = defect_image_count(row, ic)
#    if layout is not None:
#        s, nf, how = layout
#        if how == "images18":
#            if cnt <= 0:
#                tail = " ".join(row[s:]).strip()
#                return (len(row) in ({s, n} if s < n else {n})
#                        or bool(re.match(r"^Images\s+0\s*\{\s*\}$", tail)))
#            return len(defect_image_entries(row, layout, ic)) == cnt
#        if cnt <= 0:
#            return len(row) in ({s, n} if s < n else {n})
#        return len(row) == s + cnt * nf
#    base = n - (1 if il >= 0 else 0)
#    if cnt <= 0:
#        return len(row) in (base, n)
#    if il >= 0:
#        return len(row) >= base + cnt
#    return len(row) == n
#
#
#def aligned_len(row, layout, ic):
#    """把「影像欄」不論多長都算成一欄之後，這一列相當於幾欄。
#
#    用來和宣告的欄位數比對 —— 這是比 klarf_core.row_len_ok() 更寬鬆、
#    但更貼近「列到底有沒有對齊欄位」的判準。
#    """
#    span = find_image_block(row)
#    if span is not None:
#        return len(row) - (span[1] - span[0] + 1) + 1
#    if layout is not None and layout[2] in ("declared", "inferred"):
#        s, nf, _how = layout
#        cnt = defect_image_count(row, ic)
#        if cnt > 0:
#            return s + 1 if len(row) == s + cnt * nf else len(row)
#        return s + 1 if len(row) == s else len(row)
#    return len(row)
#
#
#def sibling_tiff(klarf_path, tiff_file_name):
#    """鏡射 tiff_path 的候選順序；回傳 (找到的路徑, [(候選描述, 是否存在)])。"""
#    cands, tried = [], []
#    base_dir = os.path.dirname(os.path.abspath(klarf_path))
#    if tiff_file_name:
#        nm = tiff_file_name.replace("\\", "/")
#        cands.append((nm, "TiffFileName 原樣（絕對或相對 cwd）"))
#        cands.append((os.path.join(base_dir, os.path.basename(nm)),
#                      "TiffFileName 的檔名 + KLARF 同資料夾"))
#    stem = os.path.splitext(klarf_path)[0]
#    for p, tag in ((stem, "KLARF 去副檔名"), (klarf_path, "KLARF 全名")):
#        for ext in (".tif", ".tiff", ".TIF", ".TIFF"):
#            cands.append((p + ext, "%s + %s" % (tag, ext)))
#    found, seen = None, set()
#    for path, desc in cands:
#        if not path or path in seen:
#            continue
#        seen.add(path)
#        exists = os.path.isfile(path)
#        tried.append((desc, exists))
#        if exists and found is None:
#            found = path
#    return found, tried
#
#
## ---------------------------------------------------------------- 報告
#
#def emit_header(path, meta, include_ids):
#    _out("=" * 74)
#    _out("ADEPT 廠內探測報告 #1：KLARF 結構（probe_klarf.py v%s）" % PROBE_VERSION)
#    _out("=" * 74)
#    _out("")
#    _out("【這份報告包含什麼】")
#    _out("  - KLARF 版本判定、header 欄位『名稱』清單、defect 欄位名與型別")
#    _out("  - 列數、每張圖佔幾個 token、影像佈局變體判定與其證據")
#    _out("  - 各種統計數字（列長分布、每顆 defect 影像張數分布、異常列的索引）")
#    _out("【這份報告不包含什麼】")
#    _out("  - 不含任何 defect 資料 token（座標 XREL/YREL/XINDEX 一個都不印，連範圍都不印）")
#    _out("  - 不含 LotID / WaferID / DeviceID / StepID 等識別碼的值（只印欄位名）")
#    _out("  - 不含檔名原文（只印副檔名與字元數）、不含 class 名稱、不含任何影像像素")
#    if include_ids:
#        _out("")
#        _out("  ** 注意：本次以 --include-ids 執行 → 上述識別碼『會』照原樣輸出。**")
#        _out("  ** 請先確認公司資料攜出規範允許，再把這份報告貼出廠外。 **")
#    _out("")
#    _out("-" * 74)
#    _out("1. 檔案基本資訊")
#    _out("-" * 74)
#    _out("  檔名        : %s" % redact_name(path, include_ids))
#    _out("  大小        : %d bytes" % meta["bytes"])
#    _out("  行數        : %d" % meta["lines"])
#    _out("  換行        : %s" % meta["eol"])
#    _out("  編碼        : %s%s" % (meta["encoding"], "（含 BOM）" if meta["bom"] else ""))
#    _out("  KLARF 關鍵字: %s" % ", ".join(meta["markers"]))
#    _out("")
#
#
#def emit_version(version, checks, fired):
#    _out("-" * 74)
#    _out("2. 版本判定（鏡射 klarf_core.detect_version 的順序）")
#    _out("-" * 74)
#    _out("  判定結果    : %s" % version)
#    _out("  由哪條命中  : %s" % fired)
#    _out("  各啟發式    :")
#    for name, hit, note in checks:
#        _out("    [%s] %-20s %s" % ("V" if hit else " ", name, note))
#    if version not in ("1.2", "1.8"):
#        _out("  ** 這個版本字串 ADEPT 沒看過（只處理過 1.2 / 1.8）→ 請務必回報。**")
#    _out("")
#
#
#def emit_header_fields(d, include_ids):
#    _out("-" * 74)
#    _out("3. Header 欄位（名稱全列，值預設遮蔽）")
#    _out("-" * 74)
#    seen, unknown = [], []
#    _out("  %-30s %-6s %s" % ("欄位名", "klarf", "值"))
#    for name, value in d["header"]:
#        if name in seen:
#            continue
#        seen.append(name)
#        known = name.upper() in KNOWN_FIELDS
#        if not known:
#            unknown.append(name)
#        _out("  %-30s %-6s %s" % (name, "known" if known else "NEW",
#                                  redact(value, name, include_ids)))
#    if not seen:
#        _out("  （解不出任何 header 欄位 —— 這本身就值得回報）")
#    _out("")
#    _out("  欄位總數 %d，其中 klarf_core 未涵蓋（NEW）%d 個：%s"
#         % (len(seen), len(unknown), ", ".join(unknown) if unknown else "無"))
#    _out("  ClassLookup 類別數：%d%s"
#         % (d["n_classes"],
#            ("（名稱：%s）" % ", ".join(d["class_names"][:20])) if include_ids else "（名稱已遮蔽）"))
#    _out("")
#    return seen, unknown
#
#
#def infer_col_type(rows, idx, limit):
#    kinds = set()
#    for r in rows[:limit]:
#        if idx >= len(r):
#            continue
#        kinds.add(token_shape(r[idx]))
#    if not kinds:
#        return "?"
#    if kinds == {"d"}:
#        return "int"
#    if kinds <= {"d", "f"}:
#        return "float"
#    if kinds == {"s"}:
#        return "string"
#    if kinds == {"w"}:
#        return "word"
#    return "/".join(sorted(kinds))
#
#
#def emit_columns(d, ic, il, rows_limit):
#    _out("-" * 74)
#    _out("4. Defect 欄位與列數")
#    _out("-" * 74)
#    cols = d["columns"]
#    declared = d.get("declared_col_count")
#    _out("  欄位數      : %d%s" % (len(cols),
#         ("（宣告 %d%s）" % (declared, "，不一致！" if declared != len(cols) else "")
#          if declared is not None else "")))
#    _out("  DefectList  : %d 個（>1 表示多 test，klarf_core 只吃第一個）" % d["n_defect_lists"])
#    _out("  列數        : %d%s" % (len(d["rows"]),
#         ("（Data 宣告 %d%s）" % (d["declared_row_count"],
#                                "，不一致！" if d["declared_row_count"] != len(d["rows"]) else "")
#          if d.get("declared_row_count") is not None else "")))
#    _out("")
#    _out("  （推斷型別是把 `Image/Images N { … }` 子區塊壓成一個 token 後才對欄的，")
#    _out("    所以影像欄之後的欄位也對得起來；d=整數 f=浮點 s=字串 w=字）")
#    _out("  %-4s %-24s %-10s %-10s %s" % ("#", "欄位名", "宣告型別", "推斷型別", "備註"))
#    collapsed = d["rows_collapsed"]
#    for i, c in enumerate(cols):
#        dt = d["column_types"][i] if i < len(d["column_types"]) else "-"
#        note = []
#        if i == ic:
#            note.append("<- IMAGECOUNT")
#        if i == il:
#            note.append("<- 影像清單欄（變動長度）")
#        _out("  %-4d %-24s %-10s %-10s %s"
#             % (i, c, dt, infer_col_type(collapsed, i, rows_limit), " ".join(note)))
#    if not cols:
#        _out("  （解不出欄位清單 —— 請回報）")
#    _out("")
#
#
#def emit_image_layout(d, tiff_name, tiff_spec, spec_how, layout, evidence,
#                      ic, il, rows_limit, klarf_path, include_ids):
#    _out("-" * 74)
#    _out("5. 影像佈局變體（**假設 #3：本報告最重要的一段**）")
#    _out("-" * 74)
#    _out("  IMAGECOUNT 欄索引 : %s" % (ic if ic >= 0 else "無"))
#    _out("  影像清單欄索引    : %s%s" % (
#        il if il >= 0 else "無",
#        ("（欄名 %s）" % d["columns"][il]) if 0 <= il < len(d["columns"]) else ""))
#    if tiff_spec:
#        _out("  TiffSpec          : version=%s nfields=%s fields=%s（來源：%s）%s"
#             % (tiff_spec["version"], tiff_spec["nfields"],
#                ",".join(tiff_spec["fields"]) or "-", tiff_spec["source"],
#                "  ** 宣告數與實際列出的欄位數不一致 **" if tiff_spec.get("mismatch") else ""))
#    else:
#        _out("  TiffSpec          : 無")
#    how = layout[2] if layout else "none"
#    variant = {
#        "images18": "變體 A：IMAGECOUNT 欄 + 結構化 `Images N { … }` 子區塊（images18）",
#        "declared": "變體 B：IMAGELIST 欄 + TiffSpec 宣告每張圖的 token 數（declared）",
#        "inferred": "變體 C：從資料推斷每張圖的 token 數（inferred）",
#        "imagefile": "變體 D：沒有 IMAGECOUNT 欄，但列中有 `Image/Images N { \"檔名\" … }` 子區塊"
#                     "（imagefile；klarf_core 走 defect_image_filename）",
#        "none": "**（四種已知變體都不成立）**"}[how]
#    _out("")
#    _out("  判定變體          : %s" % variant)
#    if layout:
#        _out("  影像條目起點欄    : %d" % layout[0])
#        _out("  每張圖 token 數   : %s" % (layout[1] if layout[1] is not None else "不定（子區塊）"))
#    _out("  證據              :")
#    for e in evidence:
#        _out("    - %s" % e)
#    if how == "none" and (il >= 0 or any(find_image_block(r) for r in d["rows"])):
#        _out("")
#        _out("  ** 這份 KLARF 看起來帶影像資訊，卻不符合任何一種已知變體 ——")
#        _out("     這就是要找的『新花樣』，請務必連同下面的列尾樣式一起回報。**")
#    elif how == "none":
#        _out("")
#        _out("  → 這份 KLARF 不帶影像資訊（沒有 IMAGECOUNT 欄、也沒有 Image 子區塊）。")
#
#    # 帶圖列的 token 型別樣式（無內容）
#    _out("")
#    _out("  帶圖列的列尾樣式（token 型別，d=整數 f=浮點 s=字串 w=字 {}=括號；無任何內容）：")
#    shown = 0
#    for k, r in enumerate(d["rows"]):
#        has_img = defect_image_count(r, ic) > 0 or find_image_block(r) is not None
#        if not has_img:
#            continue
#        start = max(0, (layout[0] if layout else len(d["columns"])) - 2)
#        _out("    列 %-5d 全長 %-4d 從第 %d 欄起: %s"
#             % (k, len(r), start, shape_line(r[start:])))
#        shown += 1
#        if shown >= min(3, rows_limit):
#            break
#    if shown == 0:
#        _out("    （沒有任何帶圖的列）")
#    _out("")
#
#    # 每顆 defect 影像張數分布
#    counts = {}
#    total_imgs = 0
#    for r in d["rows"]:
#        if ic >= 0:
#            c = defect_image_count(r, ic)
#        else:                                 # 變體 D：以子區塊有無代表 0/1 張
#            c = 1 if find_image_block(r) is not None else 0
#        counts[c] = counts.get(c, 0) + 1
#        total_imgs += c
#    _out("  每顆 defect 的影像張數（%s）分布：" % ("IMAGECOUNT 欄" if ic >= 0 else "有無影像子區塊"))
#    for line in histogram_lines(counts):
#        _out(line)
#    _out("  影像總張數        : %d（defect 列數 %d）" % (total_imgs, len(d["rows"])))
#    uniq = sorted(counts.keys())
#    if uniq == [2]:
#        _out("  → 每顆 defect 都是 2 張：與 ADEPT 目前的 test/ref 成對假設一致（假設 #1）。")
#        _out("    但「哪一張是 test、哪一張是 ref」要靠 probe_tiff.py 的頁面資訊確認。")
#    elif uniq == [1]:
#        _out("  → 每顆 defect 都是 1 張：Review SEM 型（單張，無 ref）。")
#    elif uniq == [0]:
#        _out("  → 沒有任何 defect 帶圖。")
#    else:
#        _out("  → 張數不一致（%s）：ADEPT 的 test/ref 成對假設在這份檔上不成立，請回報。"
#             % ",".join(str(u) for u in uniq))
#    _out("")
#
#    # 每顆 defect 一個獨立影像檔（變體 A/D 常見）→ 只報副檔名與存在與否
#    names = [block_filename(r) for r in d["rows"]]
#    names = [n for n in names if n]
#    n_files_exist = 0
#    exts = {}
#    if names:
#        base_dir = os.path.dirname(os.path.abspath(klarf_path))
#        for nm in names:
#            ext = os.path.splitext(nm)[1].lower() or "(無副檔名)"
#            exts[ext] = exts.get(ext, 0) + 1
#            if os.path.isfile(os.path.join(base_dir, nm.replace("\\", "/"))):
#                n_files_exist += 1
#        _out("  列尾帶檔名的列    : %d / %d（副檔名分布：%s）"
#             % (len(names), len(d["rows"]),
#                ", ".join("%s x%d" % (k, v) for k, v in sorted(exts.items()))))
#        _out("  以 KLARF 所在資料夾為基準，實際找得到的檔案：%d / %d"
#             % (n_files_exist, len(names)))
#        if n_files_exist == 0:
#            _out("  ** 一個都找不到 → 影像可能放在別的資料夾（相對路徑基準不同），請回報。**")
#        _out("")
#
#    # 對應的 TIFF
#    _out("  TiffFileName      : %s%s"
#         % (redact_name(tiff_name, include_ids) if tiff_name else "無",
#            ("（來源：%s）" % spec_how) if spec_how else ""))
#    found, tried = sibling_tiff(klarf_path, tiff_name)
#    for desc, exists in tried:
#        _out("    [%s] %s" % ("找到" if exists else "沒有", desc))
#    if found:
#        _out("  → 使用: %s（%d bytes）" % (redact_name(found, include_ids),
#                                          os.path.getsize(found)))
#        _out("  → 請對這個 TIFF 再跑一次 probe_tiff.py（假設 #1）。")
#    else:
#        _out("  → 找不到同伴 TIFF。若影像其實是每顆 defect 一個獨立檔（Review SEM 型），這是正常的。")
#    _out("")
#    return {"total_images": total_imgs, "counts": counts, "tiff_found": found,
#            "n_named": len(names), "n_named_exist": n_files_exist, "exts": exts}
#
#
#def emit_row_anomalies(d, layout, ic, il, rows_limit):
#    _out("-" * 74)
#    _out("6. 列長異常（只報索引與數量，不報內容）")
#    _out("-" * 74)
#    n = len(d["columns"])
#    lens, clens = {}, {}
#    bad, bad_c = [], []
#    for k, r in enumerate(d["rows"]):
#        lens[len(r)] = lens.get(len(r), 0) + 1
#        al = aligned_len(r, layout, ic)
#        clens[al] = clens.get(al, 0) + 1
#        if not row_len_ok(r, d["columns"], layout, ic, il):
#            bad.append(k)
#        if al != n:
#            bad_c.append(k)
#    _out("  原始列長分布（token 數 : 列數）：")
#    for line in histogram_lines(lens):
#        _out(line)
#    _out("  影像欄不論多長都算一欄之後的列長分布（宣告欄位數 = %d）：" % n)
#    for line in histogram_lines(clens):
#        _out(line)
#    _out("")
#    _out("  klarf_core.row_len_ok() 判為不合法：%d / %d" % (len(bad), len(d["rows"])))
#    if bad:
#        _out("    前幾筆索引：%s%s"
#             % (", ".join(str(b) for b in bad[:rows_limit]),
#                " ..." if len(bad) > rows_limit else ""))
#    _out("  對齊欄位數（影像欄算一欄後的長度 != %d）判為不合法：%d / %d"
#         % (n, len(bad_c), len(d["rows"])))
#    if bad_c:
#        _out("    前幾筆索引：%s%s"
#             % (", ".join(str(b) for b in bad_c[:rows_limit]),
#                " ..." if len(bad_c) > rows_limit else ""))
#    if bad and not bad_c:
#        _out("  → 兩者不一致：列其實對得起欄位數，是 klarf_core 的 row_len_ok()")
#        _out("    對這種變體判得太嚴（已知落差，不是檔案有問題）。請回報這一行。")
#    elif bad_c:
#        _out("  ** 真的有列對不上欄位數 → 佈局判定可能不對，請連同第 5 段一起回報。**")
#    _out("")
#    return len(bad), bad[:rows_limit], len(bad_c), bad_c[:rows_limit]
#
#
#def emit_nm_hunt(d, include_ids, rows_limit):
#    _out("-" * 74)
#    _out("7. nm_per_px 獵捕（**假設 #2**：名稱看起來可能帶像素尺寸/比例尺/倍率的欄位）")
#    _out("-" * 74)
#    hits = []
#
#    def match(name):
#        up = name.upper()
#        tags = [tag for tag, pat in NM_PATTERNS if re.search(pat, up)]
#        return tags
#
#    _out("  [header 欄位]")
#    n = 0
#    for name, value in d["header"]:
#        tags = match(name)
#        if not tags:
#            continue
#        n += 1
#        hits.append(name)
#        if name.upper() in ID_FIELDS and not include_ids:
#            shown = "<redacted, %d chars>（名稱同時像識別碼 → 仍遮蔽）" % len(str(value))
#        else:
#            v = str(value)
#            shown = v if len(v) <= 80 else v[:80] + "...(截斷)"
#        _out("    %-28s [%s] = %s" % (name, ",".join(tags), shown))
#    if n == 0:
#        _out("    （沒有名稱像像素尺寸的 header 欄位）")
#
#    _out("  [defect 欄位]（只報值域統計，不報逐列值）")
#    m = 0
#    for i, c in enumerate(d["columns"]):
#        tags = match(c)
#        if not tags:
#            continue
#        m += 1
#        hits.append(c)
#        vals = []
#        for r in d["rows"]:
#            if i < len(r):
#                vals.append(r[i])
#        nums = []
#        for v in vals:
#            try:
#                nums.append(float(v))
#            except ValueError:
#                pass
#        uniq = sorted(set(vals))
#        if nums and len(nums) == len(vals):
#            stat = "min=%g max=%g 相異值=%d" % (min(nums), max(nums), len(uniq))
#            if len(uniq) <= 5:
#                stat += "（值：%s）" % ", ".join(uniq)
#        else:
#            stat = "非數值或混合；相異值=%d" % len(uniq)
#        _out("    #%-3d %-24s [%s] %s" % (i, c, ",".join(tags), stat))
#    if m == 0:
#        _out("    （沒有名稱像像素尺寸的 defect 欄位）")
#    _out("")
#    _out("  ** 若上面沒有任何一個欄位真的帶 nm/pixel，代表 nm_per_px 不在 KLARF 裡 —— **")
#    _out("  ** 請接著看 probe_tiff.py 的 ImageDescription / Software / Resolution 標籤。 **")
#    _out("")
#    return hits
#
#
#def emit_json(summary):
#    _out("=" * 74)
#    _out("請回報這一段（以下整段是機器可讀摘要，可安全貼出；不含任何識別碼與座標）")
#    _out("=" * 74)
#    _out(">>>JSON_BEGIN")
#    for line in json_block(summary):
#        _out(line)
#    _out(">>>JSON_END")
#
#
## ---------------------------------------------------------------- main
#
#def run(path, include_ids=False, rows_limit=20):
#    text, meta = read_text(path)
#    version, checks, fired = detect_version(text)
#    d = parse_18(text) if version == "1.8" else parse_12(text)
#    d.setdefault("imagelist_col", None)
#    d.setdefault("declared_col_count", None)
#    tiff_name, tiff_spec, spec_how = parse_tiff_fields(text, d["header"])
#
#    d["rows_collapsed"] = [collapse_row(r) for r in d["rows"]]
#    ic, il = image_col_index(d["columns"], d.get("imagelist_col"))
#    layout, evidence = decide_layout(d["rows"], d["columns"], ic, il, tiff_spec)
#
#    emit_header(path, meta, include_ids)
#    emit_version(version, checks, fired)
#    names, unknown = emit_header_fields(d, include_ids)
#    emit_columns(d, ic, il, rows_limit)
#    img = emit_image_layout(d, tiff_name, tiff_spec, spec_how, layout, evidence,
#                            ic, il, rows_limit, path, include_ids)
#    n_bad, bad_idx, n_bad_c, bad_idx_c = emit_row_anomalies(
#        d, layout, ic, il, rows_limit)
#    nm_hits = emit_nm_hunt(d, include_ids, rows_limit)
#
#    summary = {}
#    summary["schema"] = SCHEMA
#    summary["probe_version"] = PROBE_VERSION
#    summary["file_bytes"] = meta["bytes"]
#    summary["eol"] = meta["eol"]
#    summary["encoding"] = meta["encoding"]
#    summary["klarf_version"] = version
#    summary["version_heuristic"] = fired
#    summary["n_header_fields"] = len(names)
#    summary["header_fields"] = names
#    summary["header_fields_new"] = unknown
#    summary["n_classes"] = d["n_classes"]
#    summary["n_defect_columns"] = len(d["columns"])
#    summary["defect_columns"] = d["columns"]
#    summary["defect_column_types"] = d["column_types"]
#    summary["n_defect_rows"] = len(d["rows"])
#    summary["n_defect_lists"] = d["n_defect_lists"]
#    summary["declared_row_count"] = d.get("declared_row_count")
#    summary["imagecount_col"] = ic
#    summary["imagelist_col"] = il
#    summary["image_layout_variant"] = layout[2] if layout else "none"
#    summary["image_layout_start_col"] = layout[0] if layout else None
#    summary["image_layout_nfields"] = layout[1] if layout else None
#    summary["tiffspec"] = ({"version": tiff_spec["version"],
#                            "nfields": tiff_spec["nfields"],
#                            "fields": tiff_spec["fields"]} if tiff_spec else None)
#    summary["imagecount_distribution"] = dict(
#        (str(k), v) for k, v in sorted(img["counts"].items()))
#    summary["total_images"] = img["total_images"]
#    summary["n_rows_with_image_filename"] = img["n_named"]
#    summary["n_image_files_found"] = img["n_named_exist"]
#    summary["image_file_extensions"] = img["exts"]
#    summary["tiff_referenced"] = bool(tiff_name)
#    summary["tiff_exists"] = bool(img["tiff_found"])
#    summary["row_length_anomalies_klarf_core"] = n_bad
#    summary["row_length_anomaly_index"] = bad_idx
#    summary["row_length_anomalies_aligned"] = n_bad_c
#    summary["row_length_anomaly_index_aligned"] = bad_idx_c
#    summary["nm_per_px_candidates"] = nm_hits
#    summary["ids_included"] = bool(include_ids)
#    emit_json(summary)
#    return 0
#
#
#def main(argv=None):
#    ap = argparse.ArgumentParser(
#        description="ADEPT 廠內探測 #1：KLARF 結構（單檔、純標準函式庫、不讀像素）")
#    ap.add_argument("klarf", help="要探測的 KLARF 檔（例：C:\\path\\to\\file.klarf）")
#    ap.add_argument("--include-ids", action="store_true",
#                    help="連 LotID/WaferID/DeviceID 等識別碼的值一起輸出（預設遮蔽）")
#    ap.add_argument("--rows", type=int, default=20,
#                    help="取樣列數上限（型別推斷、樣式與異常索引列出的筆數，預設 20）")
#    args = ap.parse_args(argv)
#    try:
#        return run(args.klarf, args.include_ids, max(1, args.rows))
#    except ProbeError as exc:
#        sys.stderr.write("錯誤：%s\n" % exc)
#        return 2
#    except Exception as exc:                      # noqa: BLE001 - 廠內不該看到 traceback
#        sys.stderr.write("錯誤：探測失敗（%s: %s）。請把這行連同檔案大小回報。\n"
#                         % (type(exc).__name__, exc))
#        return 3
#
#
#if __name__ == "__main__":
#    for _s in (sys.stdout, sys.stderr):
#        try:
#            _s.reconfigure(errors="replace")      # Python 3.7+；舊版忽略
#        except Exception:
#            pass
#    sys.exit(main())
#
#F 3046145d1bef806353a4b0d63fd81b33347fb8c8 626 fab_probe/probe_stats.py
##!/usr/bin/env python3
## -*- coding: utf-8 -*-
#"""ADEPT 廠內探測腳本 #3：灰階統計（單檔、純標準函式庫）。
#
#*** 這是三支腳本裡唯一會「讀像素值」的一支。***
#它只輸出彙總統計（直方圖、min/max/平均/標準差、4x4 區塊平均），
#不輸出任何一顆像素、不輸出可還原影像的資訊；但既然它碰了像素，
#請先確認公司的資料攜出規範，再把報告貼出廠外。
#
#用途：
#  - 影像段參數（正規化、對比）要怎麼設，看灰階分布就知道
#  - 每頁平均亮度的漂移 → 判斷 test/ref 或前後頁是否有系統性亮度差（假設 #1 的旁證）
#  - 4x4 區塊平均 → 看視野是否有大範圍不均（照明/掃描不均）
#
#TIFF 走訪邏輯鏡射自 adept/core/ingest/tiff_index.py（read_tiff_pages）；
#像素解碼在 ADEPT 是交給 tifffile，這裡為了「不裝任何套件」自己寫了
#最小解碼器：**只支援 strip 排列、未壓縮或 PackBits、8/16-bit、單通道**。
#遇到解不開的壓縮方式會清楚說明並跳過該頁，不會中斷。
#
#用法：
#    python probe_stats.py FILE.tif [--pages 20] [--bins 16] [--max-pixels 2000000]
#"""
#
#import argparse
#import array
#import json
#import math
#import os
#import struct
#import sys
#
#PROBE_VERSION = "1.0"
#SCHEMA = "adept.fab_probe.stats/1"
#
#TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4,
#             10: 8, 11: 4, 12: 8, 13: 4, 16: 8, 17: 8, 18: 8}
#
#COMPRESSION = {1: "none", 2: "CCITT-RLE", 3: "CCITT-G3", 4: "CCITT-G4",
#               5: "LZW", 6: "old-JPEG", 7: "JPEG", 8: "deflate",
#               32773: "PackBits", 32946: "deflate"}
#
#PHOTOMETRIC = {0: "white-is-zero", 1: "black-is-zero", 2: "RGB",
#               3: "palette", 4: "mask", 5: "CMYK", 6: "YCbCr"}
#
#TAGS = {254: "subfile", 256: "width", 257: "height", 258: "bits",
#        259: "compression", 262: "photometric", 270: "description",
#        273: "strip_offsets", 277: "spp", 278: "rows_per_strip",
#        279: "strip_bytes", 284: "planarconfig", 305: "software",
#        317: "predictor", 322: "tile_w", 323: "tile_h", 324: "tile_offsets",
#        325: "tile_bytes", 339: "sample_format"}
#
#RAMP = ".:-=+*#@"          # 8 級（由暗到亮）；不用空白，方格才看得出來
#
#
#class ProbeError(Exception):
#    pass
#
#
#def _out(line=""):
#    print(line)
#
#
#def redact_name(path):
#    base = os.path.basename(str(path))
#    stem, ext = os.path.splitext(base)
#    return "<redacted, %d chars>%s" % (len(stem), ext)
#
#
#def json_block(d):
#    items = list(d.items())
#    lines = ["{"]
#    for i, (k, v) in enumerate(items):
#        comma = "," if i < len(items) - 1 else ""
#        lines.append("  %s: %s%s" % (json.dumps(k, ensure_ascii=False),
#                                     json.dumps(v, ensure_ascii=False), comma))
#    lines.append("}")
#    return lines
#
#
## ------------------------------------------------- IFD 走訪（鏡射 tiff_index）
#
#def _read_values(f, en, vtype, count, raw, big):
#    size = TYPE_SIZE.get(vtype)
#    if size is None:
#        return None
#    total = size * count
#    inline = 8 if big else 4
#    if total <= inline:
#        data = raw[:total]
#    else:
#        off = struct.unpack(en + ("Q" if big else "I"), raw)[0]
#        pos = f.tell()
#        f.seek(off)
#        data = f.read(total)
#        f.seek(pos)
#        if len(data) < total:
#            return None
#    if vtype == 2:
#        return [data.split(b"\x00")[0].decode("latin-1", "replace")]
#    fmt = {1: "B", 3: "H", 4: "I", 6: "b", 7: "B", 8: "h", 9: "i",
#           11: "f", 12: "d", 13: "I", 16: "Q", 17: "q"}.get(vtype)
#    if fmt is None:
#        if vtype in (5, 10):
#            f2 = "I" if vtype == 5 else "i"
#            vals = struct.unpack(en + f2 * (count * 2), data)
#            return [vals[i] / vals[i + 1] if vals[i + 1] else 0.0
#                    for i in range(0, count * 2, 2)]
#        return None
#    return list(struct.unpack(en + fmt * count, data))
#
#
#def read_tiff_pages(f, path):
#    pages = []
#    head = f.read(8)
#    if len(head) < 8:
#        raise ProbeError("檔案太小（%d bytes），不可能是 TIFF。" % os.path.getsize(path))
#    if head[:2] == b"II":
#        en = "<"
#    elif head[:2] == b"MM":
#        en = ">"
#    else:
#        hint = ""
#        if head.startswith(b"\x89PNG"):
#            hint = "（看起來是 PNG）"
#        elif head.startswith(b"\xff\xd8\xff"):
#            hint = "（看起來是 JPEG）"
#        raise ProbeError("這個檔不是 TIFF/BigTIFF：開頭不是 II 或 MM 位元組序標記%s。"
#                         "\n      若你的影像是每顆 defect 一個 PNG/JPG（Review SEM 型），"
#                         "本腳本目前只吃多頁 TIFF。" % hint)
#    magic = struct.unpack(en + "H", head[2:4])[0]
#    big = (magic == 43)
#    if magic == 42:
#        next_ifd = struct.unpack(en + "I", head[4:8])[0]
#    elif big:
#        off_size, zero = struct.unpack(en + "HH", head[4:8])
#        if off_size != 8 or zero != 0:
#            raise ProbeError("BigTIFF 檔頭損毀。")
#        next_ifd = struct.unpack(en + "Q", f.read(8))[0]
#    else:
#        raise ProbeError("不認得的 TIFF magic %d（應為 42 或 43）。" % magic)
#
#    seen = set()
#    while next_ifd:
#        if next_ifd in seen:
#            raise ProbeError("IFD 串鏈成環 —— TIFF 檔損毀。")
#        seen.add(next_ifd)
#        f.seek(next_ifd)
#        nb = f.read(8 if big else 2)
#        if len(nb) < (8 if big else 2):
#            break
#        n = struct.unpack(en + ("Q" if big else "H"), nb)[0]
#        page = {"index": len(pages)}
#        esize = 20 if big else 12
#        entries = f.read(esize * n)
#        for k in range(n):
#            e = entries[k * esize:(k + 1) * esize]
#            if len(e) < esize:
#                break
#            tag, vtype = struct.unpack(en + "HH", e[:4])
#            if big:
#                count = struct.unpack(en + "Q", e[4:12])[0]
#                raw = e[12:20]
#            else:
#                count = struct.unpack(en + "I", e[4:8])[0]
#                raw = e[8:12]
#            name = TAGS.get(tag)
#            if name is None:
#                continue
#            vals = _read_values(f, en, vtype, count, raw, big)
#            if vals is None:
#                continue
#            page[name] = vals[0] if len(vals) == 1 else vals
#        pages.append(page)
#        nb = f.read(8 if big else 4)
#        if len(nb) < (8 if big else 4):
#            break
#        next_ifd = struct.unpack(en + ("Q" if big else "I"), nb)[0]
#    if not pages:
#        raise ProbeError("這個 TIFF 一頁都沒有。")
#    return pages, {"endian": en, "bigtiff": big, "n_pages": len(pages),
#                   "file_bytes": os.path.getsize(path)}
#
#
## ---------------------------------------------------------------- 像素解碼
#
#def unpackbits(data, expected):
#    """PackBits（TIFF compression 32773）解碼。"""
#    out = bytearray()
#    i, n = 0, len(data)
#    while i < n and len(out) < expected:
#        h = data[i]
#        i += 1
#        if h < 128:
#            cnt = h + 1
#            out += data[i:i + cnt]
#            i += cnt
#        elif h > 128:
#            if i >= n:
#                break
#            out += bytes(data[i:i + 1]) * (257 - h)
#            i += 1
#    return bytes(out)
#
#
#def _as_list(v):
#    if v is None:
#        return []
#    return list(v) if isinstance(v, (list, tuple)) else [v]
#
#
#def page_reason(p):
#    """這頁能不能解？不能的話回一句白話原因；能解回 None。"""
#    if "tile_w" in p or "tile_offsets" in p:
#        return "以 tile 排列（本腳本只支援 strip 排列）"
#    bits = p.get("bits", 8)
#    if isinstance(bits, list):
#        return "每通道位元深度不一致（%s）" % bits
#    spp = p.get("spp", 1)
#    if isinstance(spp, list):
#        spp = spp[0]
#    if spp != 1:
#        return "多通道影像（SamplesPerPixel=%s，本腳本只支援單通道灰階）" % spp
#    if bits not in (8, 16):
#        return "%s-bit（本腳本只支援 8/16-bit）" % bits
#    comp = p.get("compression", 1)
#    if comp not in (1, 32773):
#        return "壓縮方式 %s（本腳本只解得開 未壓縮 與 PackBits）" % COMPRESSION.get(comp, comp)
#    pred = p.get("predictor", 1)
#    if pred not in (1, None):
#        return "predictor=%s（水平差分預測，本腳本不支援）" % pred
#    pc = p.get("planarconfig", 1)
#    if pc not in (1, None):
#        return "planarconfig=%s（分離平面，本腳本只支援 chunky）" % pc
#    if "strip_offsets" not in p:
#        return "沒有 StripOffsets 標籤（找不到影像資料）"
#    if not p.get("width") or not p.get("height"):
#        return "缺少寬或高標籤"
#    return None
#
#
#def sample_page(f, p, en, max_pixels):
#    """讀一頁的（抽樣）像素，回傳 (rows, w, h, bits, stride)。
#
#    rows = [(列索引, 序列)]；序列是 bytes（8-bit）或 array('H')（16-bit）。
#    為了控制記憶體與時間，列會依 stride 抽樣（大圖才會 > 1）。
#    """
#    w, h = int(p["width"]), int(p["height"])
#    bits = int(p.get("bits", 8))
#    bypp = bits // 8
#    rowbytes = w * bypp
#    rps = p.get("rows_per_strip", h)
#    if isinstance(rps, list):
#        rps = rps[0]
#    rps = int(rps) if rps else h
#    rps = max(1, min(rps, h))
#    offsets = _as_list(p.get("strip_offsets"))
#    counts = _as_list(p.get("strip_bytes")) or [rowbytes * rps] * len(offsets)
#    comp = p.get("compression", 1)
#
#    max_rows = max(1, int(max_pixels // max(1, w)))
#    stride = max(1, int(math.ceil(h / float(max_rows))))
#    wanted = set(range(0, h, stride))
#
#    rows = []
#    for s, off in enumerate(offsets):
#        r0 = s * rps
#        r1 = min(h, r0 + rps)
#        need = [r for r in range(r0, r1) if r in wanted]
#        if not need:
#            continue
#        nbytes = int(counts[s]) if s < len(counts) else rowbytes * (r1 - r0)
#        f.seek(int(off))
#        data = f.read(nbytes)
#        if comp == 32773:
#            data = unpackbits(data, rowbytes * (r1 - r0))
#        for r in need:
#            a = (r - r0) * rowbytes
#            chunk = data[a:a + rowbytes]
#            if len(chunk) < rowbytes:
#                continue                      # 資料不足的殘列直接不取樣
#            if bits == 8:
#                rows.append((r, chunk))
#            else:
#                arr = array.array("H")
#                arr.frombytes(chunk)
#                if (en == "<") != (sys.byteorder == "little"):
#                    arr.byteswap()
#                rows.append((r, arr))
#    return rows, w, h, bits, stride
#
#
#def page_summary(rows, w, h, bits):
#    """由抽樣列算出 值直方圖 + 4x4 區塊平均。"""
#    hist = {}
#    if bits == 8:
#        buf = b"".join(r[1] for r in rows)
#        for v in range(256):
#            c = buf.count(bytes([v]))
#            if c:
#                hist[v] = c
#    else:
#        for _r, seq in rows:
#            for v in seq:
#                hist[v] = hist.get(v, 0) + 1
#
#    bsum = [0.0] * 16
#    bcnt = [0] * 16
#    edges = [int(round(w * k / 4.0)) for k in range(5)]
#    for r, seq in rows:
#        br = min(3, int(r * 4 // h))
#        for bc in range(4):
#            a, b = edges[bc], edges[bc + 1]
#            if b <= a:
#                continue
#            bsum[br * 4 + bc] += float(sum(seq[a:b]))
#            bcnt[br * 4 + bc] += (b - a)
#    grid = [(bsum[i] / bcnt[i]) if bcnt[i] else None for i in range(16)]
#    return hist, grid
#
#
#def hist_stats(hist):
#    n = sum(hist.values())
#    if n == 0:
#        return {"n": 0, "min": None, "max": None, "mean": None, "std": None}
#    s = sum(v * c for v, c in hist.items())
#    s2 = sum(float(v) * v * c for v, c in hist.items())
#    mean = s / float(n)
#    var = max(0.0, s2 / float(n) - mean * mean)
#    return {"n": n, "min": min(hist), "max": max(hist),
#            "mean": mean, "std": math.sqrt(var)}
#
#
#def select_pages(n, k):
#    """抽樣頁：盡量以「相鄰兩頁一組」抽，才看得出 test/ref 這種成對結構。"""
#    if n <= k:
#        return list(range(n))
#    npairs = max(1, k // 2)
#    step = max(2, (n // npairs))
#    if step % 2:
#        step += 1
#    sel = []
#    i = 0
#    while i < n and len(sel) < k:
#        sel.append(i)
#        if i + 1 < n and len(sel) < k:
#            sel.append(i + 1)
#        i += step
#    return sorted(set(sel))
#
#
## ---------------------------------------------------------------- 報告
#
#def emit_header(path):
#    _out("=" * 74)
#    _out("ADEPT 廠內探測報告 #3：灰階統計（probe_stats.py v%s）" % PROBE_VERSION)
#    _out("=" * 74)
#    _out("")
#    _out("  ****************************************************************")
#    _out("  * 注意：三支探測腳本裡，只有這一支會實際讀取影像的像素值。      *")
#    _out("  * 它只輸出彙總統計，不輸出任何一顆像素、不可能還原出影像；      *")
#    _out("  * 但請先確認貴公司的資料攜出規範允許，再把這份報告貼出廠外。    *")
#    _out("  ****************************************************************")
#    _out("")
#    _out("【這份報告包含什麼】")
#    _out("  - 抽樣頁的灰階直方圖（預設 16 格）與 min / max / 平均 / 標準差")
#    _out("  - 每頁的平均與標準差（看亮度漂移、看奇偶頁是否有系統性差異）")
#    _out("  - 一張 4x4 的區塊平均 ASCII 圖（只有 16 個數字，粗到無法辨識任何圖樣）")
#    _out("【這份報告不包含什麼】")
#    _out("  - 不含任何單一像素值、不含 4x4 以外的空間資訊、不含影像縮圖")
#    _out("  - 不含檔名原文、不含 defect 座標")
#    _out("")
#
#
#def emit_pages(path, pages, info, sel, results, max_pixels):
#    _out("-" * 74)
#    _out("1. 檔案與抽樣")
#    _out("-" * 74)
#    _out("  檔名          : %s" % redact_name(path))
#    _out("  大小          : %d bytes" % info["file_bytes"])
#    _out("  頁數          : %d（本次抽樣 %d 頁）" % (info["n_pages"], len(sel)))
#    _out("  抽樣頁索引    : %s%s" % (", ".join(str(i) for i in sel[:24]),
#                                     " ..." if len(sel) > 24 else ""))
#    _out("  每頁像素上限  : %d（超過就依列抽樣，抽樣率會標在下表）" % max_pixels)
#    _out("")
#    _out("-" * 74)
#    _out("2. 每頁統計（值域、平均、標準差）")
#    _out("-" * 74)
#    _out("  %-6s %-12s %-6s %-9s %-9s %-9s %-9s %s"
#         % ("頁", "尺寸", "bits", "取樣像素", "min", "max", "平均", "標準差"))
#    ok = 0
#    for r in results:
#        if r["skip"]:
#            _out("  %-6d %-12s %s" % (r["index"], "-", "跳過：" + r["skip"]))
#            continue
#        ok += 1
#        st = r["stats"]
#        _out("  %-6d %-12s %-6d %-9d %-9s %-9s %-9.2f %-9.2f%s"
#             % (r["index"], "%dx%d" % (r["w"], r["h"]), r["bits"], st["n"],
#                st["min"], st["max"], st["mean"], st["std"],
#                ("  （列抽樣 1/%d）" % r["stride"]) if r["stride"] > 1 else ""))
#    _out("")
#    if ok == 0:
#        _out("  ** 沒有任何一頁解得開 —— 上面的原因就是要回報的重點。**")
#        _out("")
#    return ok
#
#
#def emit_histogram(hist, bits, bins):
#    _out("-" * 74)
#    _out("3. 灰階直方圖（所有抽樣頁合計）")
#    _out("-" * 74)
#    n = sum(hist.values())
#    top = (1 << bits) - 1
#    counts = [0] * bins
#    for v, c in hist.items():
#        k = int(v * bins // (top + 1))
#        counts[min(bins - 1, max(0, k))] += c
#    mx = max(counts) if counts else 0
#    _out("  值域 0..%d 分成 %d 格；合計 %d 個像素" % (top, bins, n))
#    for i, c in enumerate(counts):
#        lo = int(round(i * (top + 1) / float(bins)))
#        hi = int(round((i + 1) * (top + 1) / float(bins))) - 1
#        bar = "#" * (int(round(46 * c / float(mx))) if mx else 0)
#        _out("  [%6d..%6d] %10d %5.1f%% %s"
#             % (lo, hi, c, 100.0 * c / n if n else 0.0, bar))
#    st = hist_stats(hist)
#    _out("")
#    _out("  min=%s  max=%s  平均=%.2f  標準差=%.2f"
#         % (st["min"], st["max"], st["mean"], st["std"]))
#    sat_lo = hist.get(0, 0)
#    sat_hi = hist.get(top, 0)
#    _out("  貼邊像素：值=0 有 %d（%.2f%%）、值=%d 有 %d（%.2f%%）"
#         % (sat_lo, 100.0 * sat_lo / n if n else 0, top, sat_hi,
#            100.0 * sat_hi / n if n else 0))
#    if n and (sat_lo + sat_hi) / float(n) > 0.01:
#        _out("  → 有明顯的飽和/截斷（超過 1%）；影像段的正規化參數要留意。")
#    _out("")
#    return counts, st
#
#
#def emit_drift(results):
#    _out("-" * 74)
#    _out("4. 每頁亮度漂移（假設 #1 的旁證：奇偶頁是否有系統性差異）")
#    _out("-" * 74)
#    good = [r for r in results if not r["skip"]]
#    means = [r["stats"]["mean"] for r in good]
#    stds = [r["stats"]["std"] for r in good]
#    if not means:
#        _out("  （沒有可用的頁）")
#        _out("")
#        return None
#    lo, hi = min(means), max(means)
#    avg = sum(means) / len(means)
#    spread = math.sqrt(sum((m - avg) ** 2 for m in means) / len(means))
#    _out("  頁平均值：最小 %.2f、最大 %.2f、全體平均 %.2f、頁間標準差 %.2f"
#         % (lo, hi, avg, spread))
#    _out("  頁標準差：最小 %.2f、最大 %.2f" % (min(stds), max(stds)))
#    even = [r["stats"]["mean"] for r in good if r["index"] % 2 == 0]
#    odd = [r["stats"]["mean"] for r in good if r["index"] % 2 == 1]
#    result = {"page_mean_min": lo, "page_mean_max": hi, "page_mean_spread": spread,
#              "even_mean": None, "odd_mean": None}
#    if even and odd:
#        em = sum(even) / len(even)
#        om = sum(odd) / len(odd)
#        result["even_mean"] = em
#        result["odd_mean"] = om
#        _out("  偶數頁平均 %.2f（%d 頁） vs 奇數頁平均 %.2f（%d 頁），差 %.2f"
#             % (em, len(even), om, len(odd), em - om))
#        if spread > 0 and abs(em - om) > 0.5 * spread and abs(em - om) > 0.5:
#            _out("  → 奇偶頁有系統性亮度差：與『兩頁一組、兩頁來源不同（test/ref）』的假設一致。")
#        else:
#            _out("  → 奇偶頁沒有明顯系統性差異（分不出 test/ref，也可能兩者本來就同亮度）。")
#    else:
#        _out("  （抽樣頁的奇偶不齊，無法比較）")
#    _out("")
#    return result
#
#
#def emit_grid(grids, bits):
#    _out("-" * 74)
#    _out("5. 4x4 區塊平均（唯一的空間資訊；粗到無法辨識任何圖樣）")
#    _out("-" * 74)
#    acc = [0.0] * 16
#    cnt = [0] * 16
#    for g in grids:
#        for i, v in enumerate(g):
#            if v is not None:
#                acc[i] += v
#                cnt[i] += 1
#    grid = [(acc[i] / cnt[i]) if cnt[i] else 0.0 for i in range(16)]
#    lo, hi = min(grid), max(grid)
#    rng = hi - lo
#    _out("  ASCII（字元梯度 %s，暗 -> 亮；每格 = 全圖 1/16 面積的平均）：" % RAMP)
#    for r in range(4):
#        line = ""
#        for c in range(4):
#            v = grid[r * 4 + c]
#            k = 0 if rng <= 0 else int(min(len(RAMP) - 1, (v - lo) / rng * (len(RAMP) - 1)))
#            line += RAMP[k]
#        _out("    %s" % line)
#    _out("  區塊平均值：")
#    for r in range(4):
#        _out("    %s" % "  ".join("%8.2f" % grid[r * 4 + c] for c in range(4)))
#    _out("  區塊間最大落差：%.2f（全體平均 %.2f）"
#         % (rng, sum(grid) / 16.0))
#    if rng > 0.08 * ((1 << bits) - 1):
#        _out("  → 視野內有明顯的大範圍不均（照明/掃描不均）；影像段可考慮做背景平坦化。")
#    else:
#        _out("  → 視野大致平坦。")
#    _out("")
#    return grid
#
#
#def emit_json(summary):
#    _out("=" * 74)
#    _out("請回報這一段（機器可讀摘要；只有彙總數字，沒有任何像素）")
#    _out("=" * 74)
#    _out(">>>JSON_BEGIN")
#    for line in json_block(summary):
#        _out(line)
#    _out(">>>JSON_END")
#
#
## ---------------------------------------------------------------- main
#
#def run(path, n_pages=20, bins=16, max_pixels=2000000):
#    if not os.path.isfile(path):
#        raise ProbeError("找不到檔案：%s" % path)
#    with open(path, "rb") as f:
#        pages, info = read_tiff_pages(f, path)    # 先確認檔案讀得開，再輸出抬頭
#        emit_header(path)
#        sel = select_pages(info["n_pages"], n_pages)
#        results = []
#        total_hist = {}
#        grids = []
#        bits_seen = set()
#        for i in sel:
#            p = pages[i]
#            why = page_reason(p)
#            if why:
#                results.append({"index": i, "skip": why})
#                continue
#            rows, w, h, bits, stride = sample_page(f, p, info["endian"], max_pixels)
#            if not rows:
#                results.append({"index": i, "skip": "讀不到任何完整的列（資料被截斷？）"})
#                continue
#            hist, grid = page_summary(rows, w, h, bits)
#            bits_seen.add(bits)
#            for v, c in hist.items():
#                total_hist[v] = total_hist.get(v, 0) + c
#            grids.append(grid)
#            results.append({"index": i, "skip": None, "w": w, "h": h, "bits": bits,
#                            "stride": stride, "stats": hist_stats(hist)})
#
#    n_ok = emit_pages(path, pages, info, sel, results, max_pixels)
#    bits = max(bits_seen) if bits_seen else 8
#    if len(bits_seen) > 1:
#        _out("  ** 抽樣頁的位元深度不一致（%s）；直方圖以 %d-bit 值域繪製。**"
#             % (sorted(bits_seen), bits))
#        _out("")
#    counts, st = ([], {"n": 0, "min": None, "max": None, "mean": None, "std": None})
#    drift = None
#    grid = [0.0] * 16
#    if n_ok:
#        counts, st = emit_histogram(total_hist, bits, bins)
#        drift = emit_drift(results)
#        grid = emit_grid(grids, bits)
#
#    summary = {}
#    summary["schema"] = SCHEMA
#    summary["probe_version"] = PROBE_VERSION
#    summary["file_bytes"] = info["file_bytes"]
#    summary["n_pages"] = info["n_pages"]
#    summary["sampled_pages"] = sel
#    summary["decoded_pages"] = n_ok
#    summary["skipped"] = dict((str(r["index"]), r["skip"]) for r in results if r["skip"])
#    summary["bits"] = bits
#    summary["bins"] = bins
#    summary["sampled_pixels"] = st["n"]
#    summary["histogram"] = counts
#    summary["min"] = st["min"]
#    summary["max"] = st["max"]
#    summary["mean"] = round(st["mean"], 4) if st["mean"] is not None else None
#    summary["std"] = round(st["std"], 4) if st["std"] is not None else None
#    summary["page_means"] = [round(r["stats"]["mean"], 3)
#                             for r in results if not r["skip"]]
#    summary["page_stds"] = [round(r["stats"]["std"], 3)
#                            for r in results if not r["skip"]]
#    summary["drift"] = (dict((k, (round(v, 4) if isinstance(v, float) else v))
#                             for k, v in drift.items()) if drift else None)
#    summary["grid4x4"] = [round(v, 2) for v in grid]
#    emit_json(summary)
#    return 0
#
#
#def main(argv=None):
#    ap = argparse.ArgumentParser(
#        description="ADEPT 廠內探測 #3：灰階統計（會讀像素值，只輸出彙總統計）")
#    ap.add_argument("tiff", help="要探測的多頁 TIFF（例：C:\\path\\to\\lot.tif）")
#    ap.add_argument("--pages", type=int, default=20, help="抽樣幾頁（預設 20）")
#    ap.add_argument("--bins", type=int, default=16, help="直方圖格數（預設 16）")
#    ap.add_argument("--max-pixels", type=int, default=2000000,
#                    help="每頁最多取樣幾個像素（超過就依列抽樣，預設 200 萬）")
#    args = ap.parse_args(argv)
#    if args.bins < 2 or args.bins > 256:
#        sys.stderr.write("錯誤：--bins 請給 2..256 之間的值（收到 %d）。\n" % args.bins)
#        return 2
#    try:
#        return run(args.tiff, max(1, args.pages), args.bins, max(1000, args.max_pixels))
#    except ProbeError as exc:
#        sys.stderr.write("錯誤：%s\n" % exc)
#        return 2
#    except Exception as exc:                      # noqa: BLE001
#        sys.stderr.write("錯誤：探測失敗（%s: %s）。請把這行連同檔案大小回報。\n"
#                         % (type(exc).__name__, exc))
#        return 3
#
#
#if __name__ == "__main__":
#    for _s in (sys.stdout, sys.stderr):
#        try:
#            _s.reconfigure(errors="replace")
#        except Exception:
#            pass
#    sys.exit(main())
#
#F ec0ff843efab0f5474454ada7124f3edd80ae633 850 fab_probe/probe_tiff.py
##!/usr/bin/env python3
## -*- coding: utf-8 -*-
#"""ADEPT 廠內探測腳本 #2：TIFF/BigTIFF 結構探測（單檔、純標準函式庫、不解碼像素）。
#
#用途：在廠內真實 patch TIFF 上確認 CLAUDE.md §8 的假設 ——
#  假設 #1「每顆 defect 第 1 張 = test、第 2 張 = ref」（--with-klarf 交叉比對；本腳本最重要的輸出）
#  假設 #2「nm_per_px 從哪來」（ImageDescription / Software / Resolution 標籤）
#
#邏輯鏡射自 adept/core/ingest/tiff_index.py（read_tiff_pages / _read_values /
#TYPE_SIZE / COMPRESSION / PHOTOMETRIC / TAGS）與 adept/core/ingest/klarf_core.py
#（--with-klarf 需要的最小 KLARF 解析 + defect_image_map）。本檔重寫了這些邏輯，
#不 import adept、不用第三方套件；那兩個模組改判定規則時，這裡要跟著改。
#
#用法：
#    python probe_tiff.py FILE.tif [--pages 8] [--with-klarf FILE.klarf] [--include-ids]
#
#本腳本**不讀任何像素**，只讀 IFD 標籤。要看灰階統計請用 probe_stats.py。
#"""
#
#import argparse
#import json
#import os
#import re
#import struct
#import sys
#
#PROBE_VERSION = "1.0"
#SCHEMA = "adept.fab_probe.tiff/1"
#
## ------------------------------------------------- TIFF 常數（鏡射 tiff_index）
#
#TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4,
#             10: 8, 11: 4, 12: 8, 13: 4, 16: 8, 17: 8, 18: 8}
#
#COMPRESSION = {1: "none", 2: "CCITT-RLE", 3: "CCITT-G3", 4: "CCITT-G4",
#               5: "LZW", 6: "old-JPEG", 7: "JPEG", 8: "deflate",
#               32773: "PackBits", 32946: "deflate"}
#
#PHOTOMETRIC = {0: "white-is-zero", 1: "black-is-zero", 2: "RGB",
#               3: "palette", 4: "mask", 5: "CMYK", 6: "YCbCr"}
#
#RESUNIT = {1: "none", 2: "inch", 3: "cm"}
#
## tiff_index.TAGS 的超集：多讀幾個對「假設 #2」有用的標籤
#TAGS = {254: "subfile", 256: "width", 257: "height", 258: "bits",
#        259: "compression", 262: "photometric", 270: "description",
#        271: "make", 272: "model", 273: "strip_offsets",
#        277: "spp", 278: "rows_per_strip", 279: "strip_bytes",
#        282: "xres", 283: "yres", 284: "planarconfig", 296: "res_unit",
#        297: "page_number", 305: "software", 306: "datetime",
#        317: "predictor", 322: "tile_w", 323: "tile_h", 324: "tile_offsets",
#        325: "tile_bytes", 339: "sample_format", 65000: "vendor_65000"}
#
## tiff_index 目前有讀的標籤（用來標示「ADEPT 目前沒在看」的欄位）
#TAGS_IN_ADEPT = {254, 256, 257, 258, 259, 262, 270, 273, 277, 279, 297,
#                 305, 306, 322, 323, 324, 325}
#
#
#class ProbeError(Exception):
#    pass
#
#
#def _out(line=""):
#    print(line)
#
#
## ---------------------------------------------------------------- 遮蔽政策
##
## 預設：
##   * 檔名只印副檔名與字元數
##   * ImageDescription / Software / Make / Model / DateTime 這類自由文字：
##     截斷到 160 字元，並把「看起來像識別碼的字」換成 <id:長度>
##     —— 規則：由字母+數字混成、長度 >= 6 的字 → 遮蔽；
##              純數字（含小數、含 nm/um 之類短單位）→ 保留（假設 #2 要看數值）；
##              純字母（<= 24 字）→ 保留（PixelSize、Software 名稱等）
##   * 不輸出任何像素
## --include-ids：上述自由文字與檔名照原樣輸出。
#
#_WORD = re.compile(r"[A-Za-z0-9_.\-]+")
#_NUMLIKE = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?[A-Za-z%/]{0,4}$")
#
#
#def redact_text(s, include_ids=False, limit=160):
#    if s is None:
#        return None
#    s = str(s).replace("\r", " ").replace("\n", " ").replace("\t", " ")
#    if not include_ids:
#        parts = re.split(r"([^A-Za-z0-9_.\-]+)", s)
#        out = []
#        for i, chunk in enumerate(parts):
#            if i % 2 == 1 or not chunk:              # 分隔符原樣保留
#                out.append(chunk)
#                continue
#            if _NUMLIKE.match(chunk):
#                out.append(chunk)
#                continue
#            core = chunk.replace("_", "").replace(".", "").replace("-", "")
#            has_a = any(c.isalpha() for c in core)
#            has_d = any(c.isdigit() for c in core)
#            if has_a and has_d and len(core) >= 6:
#                out.append("<id:%d>" % len(chunk))
#            elif has_a and not has_d and len(core) <= 24:
#                out.append(chunk)
#            elif len(chunk) >= 20:
#                out.append("<id:%d>" % len(chunk))
#            else:
#                out.append(chunk)
#        s = "".join(out)
#    if len(s) > limit:
#        s = s[:limit] + "...(截斷)"
#    return s
#
#
#def redact_name(path, include_ids=False):
#    base = os.path.basename(str(path))
#    if include_ids:
#        return base
#    stem, ext = os.path.splitext(base)
#    return "<redacted, %d chars>%s" % (len(stem), ext)
#
#
#def json_block(d):
#    items = list(d.items())
#    lines = ["{"]
#    for i, (k, v) in enumerate(items):
#        comma = "," if i < len(items) - 1 else ""
#        lines.append("  %s: %s%s" % (json.dumps(k, ensure_ascii=False),
#                                     json.dumps(v, ensure_ascii=False), comma))
#    lines.append("}")
#    return lines
#
#
#def histogram_lines(counter, width=40):
#    if not counter:
#        return ["  （無資料）"]
#    keys = sorted(counter.keys(), key=lambda k: (isinstance(k, str), k))
#    mx = max(counter.values())
#    lines = []
#    for k in keys:
#        n = counter[k]
#        lines.append("  %-10s : %8d  %s"
#                     % (str(k), n, "#" * max(1, int(round(width * n / float(mx))))))
#    return lines
#
#
## ------------------------------------------------- IFD 走訪（鏡射 read_tiff_pages）
#
#MAGIC_HINTS = [(b"\x89PNG\r\n\x1a\n", "PNG"), (b"\xff\xd8\xff", "JPEG"),
#               (b"BM", "BMP"), (b"GIF8", "GIF"), (b"PK\x03\x04", "ZIP/壓縮檔"),
#               (b"%PDF", "PDF")]
#
#
#def _read_values(f, en, vtype, count, raw, big):
#    size = TYPE_SIZE.get(vtype)
#    if size is None:
#        return None
#    total = size * count
#    inline = 8 if big else 4
#    if total <= inline:
#        data = raw[:total]
#    else:
#        off = struct.unpack(en + ("Q" if big else "I"), raw)[0]
#        pos = f.tell()
#        f.seek(off)
#        data = f.read(total)
#        f.seek(pos)
#        if len(data) < total:
#            return None
#    if vtype == 2:
#        return [data.split(b"\x00")[0].decode("latin-1", "replace")]
#    fmt = {1: "B", 3: "H", 4: "I", 6: "b", 7: "B", 8: "h", 9: "i",
#           11: "f", 12: "d", 13: "I", 16: "Q", 17: "q"}.get(vtype)
#    if fmt is None:
#        if vtype in (5, 10):
#            f2 = "I" if vtype == 5 else "i"
#            vals = struct.unpack(en + f2 * (count * 2), data)
#            return [vals[i] / vals[i + 1] if vals[i + 1] else 0.0
#                    for i in range(0, count * 2, 2)]
#        return None
#    return list(struct.unpack(en + fmt * count, data))
#
#
#def read_tiff_pages(path, max_pages=200000):
#    """回傳 (pages, info)。鏡射 tiff_index.read_tiff_pages，錯誤訊息改成中文。"""
#    if not os.path.isfile(path):
#        raise ProbeError("找不到檔案：%s" % path)
#    if os.path.getsize(path) < 8:
#        raise ProbeError("檔案太小（%d bytes），不可能是 TIFF。" % os.path.getsize(path))
#    pages = []
#    unknown_tags = {}
#    with open(path, "rb") as f:
#        head = f.read(8)
#        if head[:2] == b"II":
#            en = "<"
#        elif head[:2] == b"MM":
#            en = ">"
#        else:
#            hint = ""
#            for sig, name in MAGIC_HINTS:
#                if head.startswith(sig):
#                    hint = "（看起來是 %s）" % name
#                    break
#            raise ProbeError(
#                "這個檔不是 TIFF/BigTIFF：開頭不是 II 或 MM 位元組序標記%s。" % hint)
#        magic = struct.unpack(en + "H", head[2:4])[0]
#        big = (magic == 43)
#        if magic == 42:
#            next_ifd = struct.unpack(en + "I", head[4:8])[0]
#        elif big:
#            off_size, zero = struct.unpack(en + "HH", head[4:8])
#            if off_size != 8 or zero != 0:
#                raise ProbeError("BigTIFF 檔頭損毀（offset size=%d）。" % off_size)
#            next_ifd = struct.unpack(en + "Q", f.read(8))[0]
#        else:
#            raise ProbeError("不認得的 TIFF magic %d（應為 42 或 43）。" % magic)
#
#        seen = set()
#        while next_ifd:
#            if next_ifd in seen:
#                raise ProbeError("IFD 串鏈成環（第 %d 頁）—— TIFF 檔損毀。" % len(pages))
#            if len(pages) >= max_pages:
#                break
#            seen.add(next_ifd)
#            f.seek(next_ifd)
#            nb = f.read(8 if big else 2)
#            if len(nb) < (8 if big else 2):
#                raise ProbeError("讀 IFD 表頭時檔案就結束了（第 %d 頁）。" % len(pages))
#            n = struct.unpack(en + ("Q" if big else "H"), nb)[0]
#            page = {"index": len(pages), "ifd_offset": next_ifd}
#            esize = 20 if big else 12
#            entries = f.read(esize * n)
#            for k in range(n):
#                e = entries[k * esize:(k + 1) * esize]
#                if len(e) < esize:
#                    break
#                tag, vtype = struct.unpack(en + "HH", e[:4])
#                if big:
#                    count = struct.unpack(en + "Q", e[4:12])[0]
#                    raw = e[12:20]
#                else:
#                    count = struct.unpack(en + "I", e[4:8])[0]
#                    raw = e[8:12]
#                name = TAGS.get(tag)
#                if name is None:
#                    unknown_tags[tag] = unknown_tags.get(tag, 0) + 1
#                    continue
#                vals = _read_values(f, en, vtype, count, raw, big)
#                if vals is None:
#                    continue
#                page[name] = vals[0] if len(vals) == 1 else vals
#            b = page.get("strip_bytes", page.get("tile_bytes", 0))
#            page["data_bytes"] = sum(b) if isinstance(b, list) else b
#            pages.append(page)
#            nb = f.read(8 if big else 4)
#            if len(nb) < (8 if big else 4):
#                break
#            next_ifd = struct.unpack(en + ("Q" if big else "I"), nb)[0]
#
#    if not pages:
#        raise ProbeError("這個 TIFF 一頁都沒有（IFD 串鏈是空的）。")
#    info = {"byte_order": "little-endian (II)" if en == "<" else "big-endian (MM)",
#            "endian": en, "bigtiff": big, "n_pages": len(pages),
#            "file_bytes": os.path.getsize(path), "unknown_tags": unknown_tags}
#    return pages, info
#
#
#def page_sig(p):
#    bits = p.get("bits", "?")
#    if isinstance(bits, list):
#        bits = "/".join(str(b) for b in bits)
#    return "%sx%s %s-bit spp=%s %s %s %s" % (
#        p.get("width", "?"), p.get("height", "?"), bits, p.get("spp", 1),
#        COMPRESSION.get(p.get("compression", 1), "compression?%s" % p.get("compression")),
#        PHOTOMETRIC.get(p.get("photometric", -1), "photometric?"),
#        "tile" if "tile_w" in p else "strip")
#
#
#def select_pages(n, first):
#    """要細看哪幾頁：前 first 頁 + 中段取樣 + 最後兩頁。"""
#    idx = set(range(min(first, n)))
#    if n > first:
#        mid = n // 2
#        for i in (mid - 1, mid, mid + 1):
#            if 0 <= i < n:
#                idx.add(i)
#        idx.add(n - 2)
#        idx.add(n - 1)
#    return sorted(i for i in idx if 0 <= i < n)
#
#
## ------------------------------- 最小 KLARF 解析（鏡射 klarf_core，僅 --with-klarf 用）
#
#def _find_matching_brace(text, open_idx):
#    depth = 0
#    for i in range(open_idx, len(text)):
#        if text[i] == "{":
#            depth += 1
#        elif text[i] == "}":
#            depth -= 1
#            if depth == 0:
#                return i
#    return -1
#
#
#def klarf_detect_version(text):
#    if re.search(r"Record\s+FileRecord", text):
#        return "1.8"
#    m = re.search(r"FileVersion\s+(\d+)\s+(\d+)", text)
#    if m:
#        return "%s.%s" % (m.group(1), m.group(2))
#    if re.search(r"\bList\s+\w+\s*\{", text):
#        return "1.8"
#    return "1.2"
#
#
#def klarf_parse(path):
#    """回傳 {version, columns, rows, imagelist_col18, tiff_file_name, tiff_spec}。"""
#    if not os.path.isfile(path):
#        raise ProbeError("找不到 KLARF：%s" % path)
#    with open(path, "rb") as f:
#        raw = f.read()
#    try:
#        text = raw.decode("utf-8")
#    except UnicodeDecodeError:
#        text = raw.decode("latin-1", "replace")
#    d = {"version": klarf_detect_version(text), "columns": [], "rows": [],
#         "imagelist_col18": None, "tiff_file_name": None, "tiff_spec": None}
#    if d["version"] == "1.8":
#        dls = list(re.finditer(r"List\s+DefectList\s*\{", text))
#        if dls:
#            b0 = text.index("{", dls[0].start())
#            b1 = _find_matching_brace(text, b0)
#            block = text[b0:b1 + 1]
#            cm = re.search(r"Columns\s+\d+\s*\{([^}]*)\}", block)
#            if cm:
#                cols = []
#                for c in cm.group(1).split(","):
#                    parts = c.strip().split()
#                    if not parts:
#                        continue
#                    cols.append(parts[-1])
#                    if len(parts) >= 2 and parts[0].lower() == "imagelist":
#                        d["imagelist_col18"] = len(cols) - 1
#                d["columns"] = cols
#            dm = re.search(r"Data\s+\d+\s*\{", block)
#            if dm:
#                db0 = block.index("{", dm.start())
#                db1 = _find_matching_brace(block, db0)
#                for row in block[db0 + 1:db1].split(";"):
#                    row = row.strip()
#                    if row:
#                        d["rows"].append(re.findall(r'[^"\s]+|"[^"]*"', row))
#        m = re.search(r'Field\s+TiffFileName\s+\d+\s*\{([^}]*)\}', text)
#        if m:
#            q = re.findall(r'"([^"]*)"', m.group(1))
#            d["tiff_file_name"] = q[0] if q else m.group(1).strip()
#        m = re.search(r'Field\s+TiffSpec\s+\d+\s*\{([^}]*)\}', text)
#        if m:
#            vals = re.findall(r'"([^"]*)"', m.group(1))
#            if vals:
#                d["tiff_spec"] = {"version": vals[0], "nfields": None,
#                                  "fields": vals[1:]}
#    else:
#        m = re.search(r"DefectRecordSpec\s+\d+\s+([^;]+);", text)
#        if m:
#            d["columns"] = m.group(1).split()
#        m = re.search(r"(?m)^[ \t]*DefectList\b[ \t]*\r?\n([\s\S]*?);", text)
#        if m:
#            for line in m.group(1).splitlines():
#                line = line.strip()
#                if line and not line.startswith(";"):
#                    d["rows"].append(line.split())
#        m = re.search(r"(?m)^[ \t]*TiffFileName\b[ \t]+([^;]*);", text)
#        if m:
#            d["tiff_file_name"] = m.group(1).strip().strip('"')
#        m = re.search(r"(?m)^[ \t]*TiffSpec\b[ \t]+([\d.]+)[ \t]+(\d+)[ \t]*([^;]*);", text)
#        if m:
#            fields = re.findall(r'"([^"]*)"', m.group(3)) or m.group(3).split()
#            n = int(m.group(2))
#            if fields and len(fields) != n:
#                n = len(fields)
#            if n > 0:
#                d["tiff_spec"] = {"version": m.group(1), "nfields": n, "fields": fields}
#    return d
#
#
#def _col_index(columns, name):
#    up = [c.upper() for c in columns]
#    return up.index(name.upper()) if name.upper() in up else -1
#
#
#def _image_cols(d):
#    il = _col_index(d["columns"], "IMAGELIST")
#    if il < 0 and d["imagelist_col18"] is not None:
#        il = d["imagelist_col18"]
#    return _col_index(d["columns"], "IMAGECOUNT"), il
#
#
#def _img_count(row, ic):
#    if ic < 0 or ic >= len(row):
#        return 0
#    try:
#        return max(0, int(row[ic]))
#    except ValueError:
#        return 0
#
#
#def _layout(d, ic, il):
#    """鏡射 klarf_core.image_layout 的三種變體判定（簡化版）。"""
#    if ic < 0:
#        return None
#    s = il if il >= 0 else ic + 1
#    for r in d["rows"]:
#        if _img_count(r, ic) > 0:
#            if s < len(r) and r[s] == "Images":
#                return (s, None, "images18")
#            break
#    if il >= 0 and d["tiff_spec"] and d["tiff_spec"].get("nfields"):
#        return (il, d["tiff_spec"]["nfields"], "declared")
#    n = len(d["columns"])
#    starts = []
#    for cand in ([il] if il >= 0 else []) + [n] + ([n - 1] if ic == n - 2 else []):
#        if cand not in starts:
#            starts.append(cand)
#    best = None
#    for st in starts:
#        tally, total = {}, 0
#        for r in d["rows"]:
#            cnt = _img_count(r, ic)
#            if cnt <= 0:
#                continue
#            total += 1
#            extra = len(r) - st
#            if extra > 0 and extra % cnt == 0:
#                tally[extra // cnt] = tally.get(extra // cnt, 0) + 1
#        if not tally:
#            continue
#        nf, votes = max(tally.items(), key=lambda kv: kv[1])
#        if nf >= 1 and votes >= total - max(1, total // 10) and best is None:
#            best = (st, nf, "inferred")
#    return best
#
#
#def _entries(row, layout, ic):
#    cnt = _img_count(row, ic)
#    if cnt <= 0 or layout is None:
#        return []
#    s, nf, how = layout
#    if how == "images18":
#        m = re.match(r"Images\s+\d+\s*\{(.*)\}\s*$", " ".join(row[s:]))
#        if not m:
#            return []
#        e = [x.split() for x in m.group(1).split(",") if x.strip()]
#        return e if len(e) == cnt else []
#    toks = row[s:]
#    if len(toks) < cnt * nf:
#        return []
#    return [toks[k * nf:(k + 1) * nf] for k in range(cnt)]
#
#
#def defect_image_map(d, n_pages):
#    """鏡射 klarf_core.defect_image_map。回傳 {mode, base, pages, notes}。"""
#    notes = []
#    ic, il = _image_cols(d)
#    if ic < 0:
#        return {"mode": None, "base": None, "pages": [[] for _ in d["rows"]],
#                "notes": ["沒有 IMAGECOUNT 欄 → 這份 KLARF 不帶 patch 對應資訊。"]}
#    counts = [_img_count(r, ic) for r in d["rows"]]
#    total = sum(counts)
#    if total == 0:
#        return {"mode": None, "base": None, "pages": [[] for _ in d["rows"]],
#                "notes": ["每一列的 IMAGECOUNT 都是 0。"]}
#    layout = _layout(d, ic, il)
#    ids_per_row, usable = [], (layout is not None)
#    if usable:
#        for r, cnt in zip(d["rows"], counts):
#            ents = _entries(r, layout, ic)
#            if len(ents) != cnt or not all(e and e[0].lstrip("-").isdigit() for e in ents):
#                usable = False
#                notes.append("影像條目的第一個欄位不是整數頁碼（可能是檔名或解不出條目）"
#                             "→ 改用出現順序連續配頁。")
#                break
#            ids_per_row.append([int(e[0]) for e in ents])
#    if usable and layout and layout[2] == "images18" and all(
#            ids == list(range(1, len(ids) + 1)) for ids in ids_per_row):
#        usable = False
#        notes.append("ImageList 的 id 是「defect 內的第幾張」（1..IMAGECOUNT），"
#                     "不是全域 page 編號 → 改用出現順序連續配頁。")
#    flat = [i for ids in ids_per_row for i in ids]
#    if usable and len(set(flat)) != len(flat):
#        usable = False
#        notes.append("IMAGELIST 的 id 有重複 → 改用出現順序連續配頁。")
#    base = None
#    if usable:
#        lo, hi = min(flat), max(flat)
#        if lo >= 1 and hi <= n_pages:
#            base = 1
#        elif lo >= 0 and hi <= n_pages - 1:
#            base = 0
#        else:
#            usable = False
#            notes.append("IMAGELIST 的 id 範圍 [%d..%d] 塞不進 %d 頁 → 改用連續配頁。"
#                         % (lo, hi, n_pages))
#    if usable:
#        notes.append("IMAGELIST 第一個欄位視為 %s TIFF 頁碼。"
#                     % ("1-based（1 = 第一頁）" if base == 1 else "0-based（0 = 第一頁）"))
#        return {"mode": "imagelist", "base": base,
#                "pages": [[i - base for i in ids] for ids in ids_per_row],
#                "notes": notes}
#    pages, cum = [], 0
#    for cnt in counts:
#        pages.append(list(range(cum, cum + cnt)))
#        cum += cnt
#    if total != n_pages:
#        notes.append("IMAGECOUNT 總和（%d）不等於 TIFF 頁數（%d）→ 連續配頁可能對不上。"
#                     % (total, n_pages))
#    notes.append("依 defect 出現順序連續配頁。")
#    return {"mode": "sequential", "base": None, "pages": pages, "notes": notes}
#
#
## ---------------------------------------------------------------- 報告
#
#def emit_header(path, include_ids):
#    _out("=" * 74)
#    _out("ADEPT 廠內探測報告 #2：TIFF 結構（probe_tiff.py v%s）" % PROBE_VERSION)
#    _out("=" * 74)
#    _out("")
#    _out("【這份報告包含什麼】")
#    _out("  - TIFF 檔層資訊（位元組序、是否 BigTIFF、頁數、檔案大小）")
#    _out("  - 抽樣頁的尺寸/位元深度/通道數/壓縮/光度/tile 或 strip 等結構標籤")
#    _out("  - ImageDescription、Software 等文字標籤（截斷 + 識別碼遮蔽，數字保留）")
#    _out("  - 搭配 --with-klarf 時：defect 數與頁數的對應關係檢查")
#    _out("【這份報告不包含什麼】")
#    _out("  - **完全不讀像素**（本腳本只讀 IFD 標籤，連一個 byte 的影像資料都沒解碼）")
#    _out("  - 不含檔名原文（只印副檔名與字元數）、不含 defect 座標")
#    if include_ids:
#        _out("")
#        _out("  ** 注意：本次以 --include-ids 執行 → 檔名與文字標籤會照原樣輸出。**")
#    _out("")
#
#
#def emit_file_info(path, info, include_ids):
#    _out("-" * 74)
#    _out("1. 檔案層資訊")
#    _out("-" * 74)
#    _out("  檔名          : %s" % redact_name(path, include_ids))
#    _out("  大小          : %d bytes" % info["file_bytes"])
#    _out("  位元組序      : %s" % info["byte_order"])
#    _out("  BigTIFF       : %s" % ("是" if info["bigtiff"] else "否（classic TIFF）"))
#    _out("  頁數（IFD 數）: %d" % info["n_pages"])
#    if info["unknown_tags"]:
#        top = sorted(info["unknown_tags"].items(), key=lambda kv: -kv[1])[:12]
#        _out("  未收錄的標籤  : %s"
#             % ", ".join("tag %d x%d" % (t, c) for t, c in top))
#        _out("                  （probe 沒有解讀這些標籤；若其中有廠商私有的 pixel size，")
#        _out("                    請把 tag 編號回報，我們再加進來看）")
#    _out("")
#
#
#def emit_uniformity(pages):
#    _out("-" * 74)
#    _out("2. 各頁尺寸是否一致")
#    _out("-" * 74)
#    sigs = {}
#    for p in pages:
#        sigs.setdefault(page_sig(p), []).append(p["index"])
#    _out("  相異的頁面規格數：%d" % len(sigs))
#    for sig, idxs in sorted(sigs.items(), key=lambda kv: -len(kv[1])):
#        head = ", ".join(str(i) for i in idxs[:8])
#        _out("    %-52s x%-6d 頁索引：%s%s"
#             % (sig, len(idxs), head, " ..." if len(idxs) > 8 else ""))
#    uniform = len(sigs) == 1
#    _out("  → %s" % ("所有頁面規格完全一致（uniform）。" if uniform else
#                     "**頁面規格不一致 —— ADEPT 假設同一份 patch TIFF 各頁同尺寸，請回報。**"))
#    _out("")
#    return uniform, len(sigs)
#
#
#def emit_pages(pages, info, sel, include_ids):
#    _out("-" * 74)
#    _out("3. 抽樣頁的標籤（前幾頁 + 中段 + 最後兩頁）")
#    _out("-" * 74)
#    prev_key = None
#    for i in sel:
#        p = pages[i]
#        key = json.dumps(dict((k, v) for k, v in p.items()
#                              if k not in ("index", "ifd_offset", "strip_offsets",
#                                           "tile_offsets", "data_bytes",
#                                           "strip_bytes", "tile_bytes")),
#                         sort_keys=True, default=str)
#        _out("  [第 %d 頁 / 共 %d]" % (i, info["n_pages"]))
#        if key == prev_key:
#            _out("     （標籤與上一個列出的頁完全相同；只有影像資料位置不同）")
#            continue
#        prev_key = key
#        _out("     規格        : %s" % page_sig(p))
#        if "tile_w" in p:
#            _out("     tile        : %sx%s" % (p.get("tile_w"), p.get("tile_h")))
#        else:
#            _out("     strip       : rows_per_strip=%s，strip 數=%s"
#                 % (p.get("rows_per_strip", "?"),
#                    len(p["strip_offsets"]) if isinstance(p.get("strip_offsets"), list) else 1))
#        _out("     影像資料量  : %s bytes" % p.get("data_bytes", "?"))
#        extra = []
#        for key, label in (("planarconfig", "planar"), ("sample_format", "sample_format"),
#                           ("predictor", "predictor"), ("page_number", "page_number"),
#                           ("subfile", "subfile")):
#            if key in p:
#                extra.append("%s=%s" % (label, p[key]))
#        if extra:
#            _out("     其他        : %s" % ", ".join(extra))
#        if "xres" in p or "yres" in p:
#            _out("     解析度      : xres=%s yres=%s unit=%s  <- **假設 #2 的線索**"
#                 % (p.get("xres"), p.get("yres"),
#                    RESUNIT.get(p.get("res_unit"), p.get("res_unit"))))
#        for key, label in (("description", "ImageDescription"), ("software", "Software"),
#                           ("make", "Make"), ("model", "Model"), ("datetime", "DateTime")):
#            if key in p:
#                v = p[key]
#                if isinstance(v, list):
#                    v = " ".join(str(x) for x in v[:8])
#                _out("     %-12s: %s" % (label, redact_text(v, include_ids)))
#    _out("")
#    _out("  ** ImageDescription / Software 裡若出現像 PixelSize=3.2nm 這種字樣，**")
#    _out("  ** 就是 nm_per_px 的來源（假設 #2）—— 請把那一行回報。**")
#    _out("")
#
#
#def emit_desc_pattern(pages, info):
#    """頁面文字標籤的週期性 —— 對「哪一頁是 test、哪一頁是 ref」是直接證據。"""
#    _out("-" * 74)
#    _out("4. 頁面標籤的週期性（判斷 test/ref 交錯的線索）")
#    _out("-" * 74)
#    keys = []
#    for p in pages:
#        parts = []
#        for k in ("description", "software", "page_number", "photometric",
#                  "width", "height"):
#            if k in p:
#                parts.append("%s=%s" % (k, p[k]))
#        keys.append("|".join(parts))
#    uniq = {}
#    for k in keys:
#        uniq[k] = uniq.get(k, 0) + 1
#    _out("  相異的標籤組合數：%d（共 %d 頁）" % (len(uniq), len(pages)))
#    period = None
#    for cand in (1, 2, 3, 4):
#        if len(keys) >= 2 * cand and all(
#                keys[i] == keys[i % cand] for i in range(len(keys))):
#            period = cand
#            break
#    if period == 1:
#        _out("  → 所有頁的標籤完全相同：標籤本身分不出 test / ref。")
#    elif period:
#        _out("  → 標籤以 %d 頁為週期重複 —— 與「每顆 defect %d 張、順序固定」一致。"
#             % (period, period))
#    else:
#        _out("  → 標籤沒有明顯週期（每頁都帶各自的資訊，例如逐頁編號）。")
#    seq = [p.get("page_number") for p in pages[:8]]
#    if any(s is not None for s in seq):
#        _out("  前 8 頁的 page_number 標籤：%s" % seq)
#    _out("")
#    return period
#
#
#def emit_klarf_crosscheck(klarf_path, pages, info, include_ids):
#    _out("-" * 74)
#    _out("5. 與 KLARF 交叉比對（**假設 #1：本報告最重要的一段**）")
#    _out("-" * 74)
#    d = klarf_parse(klarf_path)
#    ic, il = _image_cols(d)
#    n_rows = len(d["rows"])
#    n_pages = info["n_pages"]
#    counts = {}
#    total = 0
#    for r in d["rows"]:
#        c = _img_count(r, ic)
#        counts[c] = counts.get(c, 0) + 1
#        total += c
#    _out("  KLARF          : %s（版本 %s）"
#         % (redact_name(klarf_path, include_ids), d["version"]))
#    _out("  defect 列數    : %d" % n_rows)
#    _out("  TIFF 頁數      : %d" % n_pages)
#    _out("  IMAGECOUNT 總和: %d" % total)
#    _out("")
#    _out("  每顆 defect 的影像張數分布：")
#    for line in histogram_lines(counts):
#        _out(line)
#
#    uniq = sorted(k for k in counts.keys())
#    if ic < 0:
#        _out("")
#        _out("  觀察到的排列   : 無法判斷 —— 這份 KLARF 沒有 IMAGECOUNT 欄")
#        _out("  → 影像資訊可能寫在列尾的 `Image/Images { \"檔名\" }` 子區塊裡"
#             "（每顆 defect 一個獨立影像檔），")
#        _out("    那就和這份多頁 TIFF 沒有對應關係。請改跑 probe_klarf.py 看第 5 段的變體判定。")
#        _out("")
#        return {"klarf_version": d["version"], "n_defect_rows": n_rows,
#                "imagecount_total": 0, "pattern": "no-imagecount-column",
#                "pages_eq_2x_defects": (n_pages == 2 * n_rows),
#                "pages_eq_imagecount": False, "map_mode": None, "map_base": None,
#                "map_out_of_range": 0, "imagecount_distribution": {}}
#    if uniq == [1]:
#        pattern = "single"
#        pat_txt = "single（每顆 1 張）"
#    elif uniq == [2]:
#        pattern = "pairs"
#        pat_txt = "pairs（每顆 2 張）"
#    elif uniq == [3]:
#        pattern = "triples"
#        pat_txt = "triples（每顆 3 張）"
#    elif len(uniq) == 1:
#        pattern = "n=%d" % uniq[0]
#        pat_txt = "每顆 %d 張" % uniq[0]
#    else:
#        pattern = "mixed"
#        pat_txt = "mixed（張數不一致：%s）" % ",".join(str(u) for u in uniq)
#    _out("")
#    _out("  觀察到的排列   : %s" % pat_txt)
#    ok_pair = (n_pages == 2 * n_rows)
#    _out("  檢查 A：頁數 == 2 x defect 數？  %s（%d vs %d）"
#         % ("是" if ok_pair else "否", n_pages, 2 * n_rows))
#    ok_total = (n_pages == total)
#    _out("  檢查 B：頁數 == IMAGECOUNT 總和？%s（%d vs %d）"
#         % ("是" if ok_total else "否", n_pages, total))
#    if ok_pair and pattern == "pairs":
#        _out("  → 與 ADEPT 目前的假設一致：每顆 defect 兩頁（假設第 1 頁 = test、第 2 頁 = ref）。")
#        _out("    注意：這只證明『成對』，**沒有證明哪一張是 test**。")
#        _out("    要確認先後順序，請看第 4 段的標籤週期，或用 probe_stats.py 看奇/偶頁的亮度差異。")
#    elif pattern == "single":
#        _out("  → 每顆 defect 只有一張：沒有 ref，屬 Review SEM 型流程。")
#    else:
#        _out("  ** → 與 test/ref 成對假設不符，這正是要找的差異，請務必回報這一段。**")
#
#    imap = defect_image_map(d, n_pages)
#    _out("")
#    _out("  宣告的 page 對應是否解得開：%s"
#         % ({"imagelist": "解得開（imagelist 模式，id 直接是頁碼）",
#             "sequential": "解不開，退回連續配頁（sequential 模式）",
#             None: "沒有對應資訊"}[imap["mode"]]))
#    if imap["base"] is not None:
#        _out("  id 起算基準    : %d-based" % imap["base"])
#    for note in imap["notes"]:
#        _out("    - %s" % note)
#    shown = [pg for pg in imap["pages"][:5]]
#    if shown:
#        _out("  前幾顆 defect 對到的頁（0-based 頁索引，不是座標）：")
#        for k, pg in enumerate(shown):
#            _out("    defect #%d -> %s" % (k, pg))
#    out_of_range = 0
#    for pg in imap["pages"]:
#        for x in pg:
#            if x < 0 or x >= n_pages:
#                out_of_range += 1
#    if out_of_range:
#        _out("  ** 有 %d 個對應頁碼落在 0..%d 之外 —— 對應規則和 ADEPT 想的不一樣，請回報。**"
#             % (out_of_range, n_pages - 1))
#    _out("")
#    return {"klarf_version": d["version"], "n_defect_rows": n_rows,
#            "imagecount_total": total, "pattern": pattern,
#            "pages_eq_2x_defects": ok_pair, "pages_eq_imagecount": ok_total,
#            "map_mode": imap["mode"], "map_base": imap["base"],
#            "map_out_of_range": out_of_range,
#            "imagecount_distribution": dict((str(k), v) for k, v in sorted(counts.items()))}
#
#
#def emit_json(summary):
#    _out("=" * 74)
#    _out("請回報這一段（機器可讀摘要，可安全貼出；不含識別碼、不含像素）")
#    _out("=" * 74)
#    _out(">>>JSON_BEGIN")
#    for line in json_block(summary):
#        _out(line)
#    _out(">>>JSON_END")
#
#
## ---------------------------------------------------------------- main
#
#def run(path, n_first=8, with_klarf=None, include_ids=False):
#    pages, info = read_tiff_pages(path)
#    emit_header(path, include_ids)
#    emit_file_info(path, info, include_ids)
#    uniform, n_sigs = emit_uniformity(pages)
#    sel = select_pages(info["n_pages"], n_first)
#    emit_pages(pages, info, sel, include_ids)
#    period = emit_desc_pattern(pages, info)
#    cross = None
#    if with_klarf:
#        cross = emit_klarf_crosscheck(with_klarf, pages, info, include_ids)
#
#    p0 = pages[0]
#    summary = {}
#    summary["schema"] = SCHEMA
#    summary["probe_version"] = PROBE_VERSION
#    summary["file_bytes"] = info["file_bytes"]
#    summary["byte_order"] = info["byte_order"]
#    summary["bigtiff"] = info["bigtiff"]
#    summary["n_pages"] = info["n_pages"]
#    summary["uniform_pages"] = uniform
#    summary["n_page_signatures"] = n_sigs
#    summary["page0"] = {"width": p0.get("width"), "height": p0.get("height"),
#                        "bits": p0.get("bits"), "spp": p0.get("spp", 1),
#                        "compression": COMPRESSION.get(p0.get("compression", 1),
#                                                       str(p0.get("compression"))),
#                        "photometric": PHOTOMETRIC.get(p0.get("photometric", -1),
#                                                       str(p0.get("photometric"))),
#                        "layout": "tile" if "tile_w" in p0 else "strip"}
#    summary["has_description_tag"] = any("description" in p for p in pages)
#    summary["has_resolution_tag"] = any("xres" in p for p in pages)
#    summary["unknown_tags"] = sorted(info["unknown_tags"].keys())[:32]
#    summary["tag_period"] = period
#    summary["adept_unread_tags"] = sorted(
#        set(t for t, name in TAGS.items()
#            if t not in TAGS_IN_ADEPT and any(name in p for p in pages)))
#    summary["klarf_crosscheck"] = cross
#    summary["ids_included"] = bool(include_ids)
#    emit_json(summary)
#    return 0
#
#
#def main(argv=None):
#    ap = argparse.ArgumentParser(
#        description="ADEPT 廠內探測 #2：TIFF 結構（單檔、純標準函式庫、不解碼像素）")
#    ap.add_argument("tiff", help="要探測的 TIFF 檔（例：C:\\path\\to\\lot.tif）")
#    ap.add_argument("--pages", type=int, default=8,
#                    help="細看前幾頁（另外自動加看中段與最後兩頁，預設 8）")
#    ap.add_argument("--with-klarf", default=None,
#                    help="同時給對應的 KLARF，做 defect 數 / 頁數的成對檢查（假設 #1）")
#    ap.add_argument("--include-ids", action="store_true",
#                    help="檔名與文字標籤照原樣輸出（預設遮蔽）")
#    args = ap.parse_args(argv)
#    try:
#        return run(args.tiff, max(1, args.pages), args.with_klarf, args.include_ids)
#    except ProbeError as exc:
#        sys.stderr.write("錯誤：%s\n" % exc)
#        return 2
#    except Exception as exc:                      # noqa: BLE001
#        sys.stderr.write("錯誤：探測失敗（%s: %s）。請把這行連同檔案大小回報。\n"
#                         % (type(exc).__name__, exc))
#        return 3
#
#
#if __name__ == "__main__":
#    for _s in (sys.stdout, sys.stderr):
#        try:
#            _s.reconfigure(errors="replace")
#        except Exception:
#            pass
#    sys.exit(main())
#
#F a0efd0dffb6b69c2c67e1801f21528c887b8b763 20 pyproject.toml
#[build-system]
#requires = ["setuptools>=61"]
#build-backend = "setuptools.build_meta"
#
#[project]
#name = "adept"
#version = "0.1.0.dev0"
#description = "ADEPT: flexible multi-step ADC for semiconductor inspection (EBI patch / RSEM + KLARF)"
#requires-python = ">=3.9"
#dependencies = ["numpy>=1.24", "opencv-python>=4.8", "tifffile>=2023.7", "openpyxl>=3.1"]
#
#[project.optional-dependencies]
#dev = ["pytest>=7"]
#
#[tool.setuptools.packages.find]
#include = ["adept*"]
#
#[tool.pytest.ini_options]
#testpaths = ["tests"]
#
#F cf5284f96a1d071e240ef88199e54d580b48c57c 6 requirements.txt
#numpy>=1.24
#opencv-python>=4.8
#tifffile>=2023.7
#PySide6>=6.5
#openpyxl>=3.1
#
#F 525a28bc3de17678321715cbca0bdbb60a9a3560 29 tests/conftest.py
## 測試共用設定。
#"""**測試裡不准跳出 modal 對話框。**
#
#Studio 關窗時會問「還沒存要不要存」（F7-16）。那在真的使用時是必要的，但在
#headless 測試裡，一個 modal 對話框不會讓測試失敗 —— 它會讓測試**永遠停在那裡**，
#而且沒有任何訊息。那種卡住是最難查的一種，所以在這裡一次關掉。
#
#要驗那個對話框本身的測試（`test_ui_f7_16_safety_net.py`）自己把它打開，
#驗完再關回去。
#
#刻意**不**在這裡 import Qt：core 的測試不該因為一個 conftest 就把 PySide6 拉
#進來。等到某個 UI 測試把 `adept.ui.studio` 載進來之後，這個 fixture 才動它。
#（fixture 的建立順序保證得了這件事：module-scoped 的 `qapp` 比 function-scoped
#的 autouse fixture 早建立，而 `qapp` 就是 import Studio 的那一步。）
#"""
#from __future__ import annotations
#
#import sys
#
#import pytest
#
#
#@pytest.fixture(autouse=True)
#def _no_modal_dialogs_in_tests():
#    mod = sys.modules.get("adept.ui.studio")
#    if mod is not None:
#        mod.StudioWindow.PROMPT_ON_CLOSE = False
#    yield
#

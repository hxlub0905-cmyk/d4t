# ADEPT Studio Gallery — authored 2026-07-28 (M5-2).
# 虛擬捲動的骨架（單一自繪畫布 + 手算可視範圍）是本檔自寫；視覺語言、
# token 用法與 test-accessor 慣例沿用 adept/ui/widgets.py。
"""同屏比多顆 —— 縮圖網格（Gallery）。

為什麼要有這一頁：單顆預覽一次只能看一顆，但調參的真正問題是「**整群**看起來
對不對」——排前面的是不是都是真缺陷？門檻附近坐著什麼？所以把整批 defect 攤成
縮圖牆，用眼睛一次掃過一整批。它跟直方圖是同一個調參迴圈的兩半：
直方圖點一根 bar → :meth:`GalleryPanel.filter_by_score_range` → 這裡只剩那一區間。

設計約束（跟 ``widgets.py`` 同一套，別破壞）
--------------------------------------------

1. **純資料驅動**：只吃 dict / ndarray，只發 Signal。這個元件**不碰引擎、不開檔案**。
   縮圖由呼叫端（背景執行緒用 :func:`make_thumb` 產生）餵進來；``thumb=None``
   會畫「載入中…」的佔位磚，之後用 :meth:`GalleryPanel.set_thumb` 逐張補上。
2. **顏色一律走 ``theme.TOKENS``**，不寫死 hex。
3. **顏色不是唯一通道**：bin 除了色條，也一定寫在說明文字裡（「bin 1」），
   色盲 / 投影機 / 列印都讀得到 —— 推廣鐵則。
4. **虛擬捲動是硬需求**：目標 10k defect 順順跑。作法是「一塊自繪畫布」——
   整個網格只有 **一個** widget（:class:`_GridView` 的 viewport），tile 是畫上去的
   不是 widget，所以 10k 顆不會產生 10k 個 QWidget。每次重繪只走
   :meth:`_GridView._visible_range` 算出來的可視索引區間（外加 1 列 overscan），
   QPixmap 轉換結果放在上限 :data:`CACHE_CAP` 的 LRU 快取裡（key 含縮圖尺寸）。
"""

from __future__ import annotations

import math
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import TOKENS
from .widgets import apply_button_cursors, to_uint8

__all__ = ["GalleryPanel", "make_thumb", "THUMB_SIZES", "CACHE_CAP"]

#: 縮圖大小選項（顯示名稱, 邊長 px）—— 小 / 中 / 大。
THUMB_SIZES: Tuple[Tuple[str, int], ...] = (("S", 64), ("M", 96), ("L", 144))

#: QPixmap LRU 快取上限（筆數）。key = (defect_id, 縮圖邊長)。
CACHE_CAP = 512

#: 可視範圍上下各多算幾列（捲動時不會看到白邊）。
OVERSCAN_ROWS = 1


# --------------------------------------------------------------------------- #
# 縮圖產生（Qt-free —— 呼叫端可以在背景執行緒跑）
# --------------------------------------------------------------------------- #
def make_thumb(arr: np.ndarray, size: int = 96) -> np.ndarray:
    """任意 ndarray → ``size`` × ``size`` 的方形 uint8 縮圖。

    * 正規化規則與 :func:`widgets.to_uint8` **完全一致**：``uint8`` 原樣使用
      （patch 的原始灰階就是原始灰階），float / int16 等走 min–max 自動拉伸，
      NaN/Inf 不參與統計。同一顆 defect 在單顆預覽與 gallery 裡看起來一樣。
    * 非方形輸入採 **letterbox**（等比縮到塞得下，四周補黑）而不是裁切 ——
      缺陷可能就長在邊緣，裁掉會讓人看不到證據。
    * 縮小用 ``cv2.INTER_AREA``（防摩爾紋），放大用 ``INTER_NEAREST``
      （SEM 小圖要看得出方格，跟 ImageView 放大時關平滑取樣同一個理由）。

    這個函式**不碰 Qt**，所以可以丟到背景執行緒批次產生縮圖。
    """
    s = int(max(8, min(512, int(size))))
    a = np.asarray(arr)
    if a.ndim == 3:
        if a.shape[2] == 4:
            a = a[:, :, :3]
        elif a.shape[2] == 1:
            a = a[:, :, 0]
        elif a.shape[2] != 3:
            a = a[:, :, 0]
    if a.ndim not in (2, 3):
        raise ValueError("make_thumb accepts (H,W) or (H,W,3/4) images only, got %r"
                         % (a.shape,))

    colour = a.ndim == 3
    out_shape = (s, s, 3) if colour else (s, s)
    h, w = a.shape[:2]
    if h <= 0 or w <= 0:
        return np.zeros(out_shape, dtype=np.uint8)

    u8 = to_uint8(a)
    scale = min(s / float(w), s / float(h))
    tw = int(max(1, min(s, round(w * scale))))
    th = int(max(1, min(s, round(h * scale))))
    if (tw, th) != (w, h):
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_NEAREST
        small = cv2.resize(u8, (tw, th), interpolation=interp)
    else:
        small = u8
    if colour and small.ndim == 2:            # cv2 可能把單通道壓成 2-D
        small = np.repeat(small[:, :, None], 3, axis=2)

    out = np.zeros(out_shape, dtype=np.uint8)
    y0, x0 = (s - th) // 2, (s - tw) // 2
    out[y0:y0 + th, x0:x0 + tw] = small
    return out


def thumb_placement(shape: Any, size: int = 96) -> Tuple[int, int, int, int]:
    """縮圖裡「影像實際落在哪」：``(x0, y0, w, h)``。

    :func:`make_thumb` 用的是**置中的 letterbox**（等比縮放後四周補黑），
    所以要把一個正規化座標的框畫到縮圖上，就得知道那個偏移與縮放。

    **它與 make_thumb 是同一份算式，所以放在一起** —— 分開放的話，
    哪天改了縮圖的縮放規則而忘了改這裡，框就會整批偏掉，
    而且畫面上看起來只是「框好像有點歪」，不會有人聯想到是縮圖改過。
    """
    s = int(max(8, min(512, int(size))))
    h, w = (int(shape[0]), int(shape[1])) if len(shape) >= 2 else (0, 0)
    if h <= 0 or w <= 0:
        return (0, 0, s, s)
    scale = min(s / float(w), s / float(h))
    tw = int(max(1, min(s, round(w * scale))))
    th = int(max(1, min(s, round(h * scale))))
    return ((s - tw) // 2, (s - th) // 2, tw, th)


def _qimage_from_uint8(arr: np.ndarray) -> QImage:
    """uint8 (H,W) / (H,W,3) → QImage（deep copy，不依賴原 buffer）。

    規則與 ``widgets._qimage_from_uint8`` 相同；gallery 只會拿到縮圖，
    所以只支援灰階與 RGB 兩種。
    """
    a = np.ascontiguousarray(arr)
    if a.ndim == 2:
        h, w = a.shape
        img = QImage(a.data, w, h, w, QImage.Format_Grayscale8)
    elif a.ndim == 3 and a.shape[2] == 3:
        h, w, _ = a.shape
        img = QImage(a.data, w, h, 3 * w, QImage.Format_RGB888)
    elif a.ndim == 3 and a.shape[2] == 4:
        h, w, _ = a.shape
        img = QImage(a.data, w, h, 4 * w, QImage.Format_RGBA8888)
    else:
        raise ValueError("Unsupported thumbnail shape: %r" % (a.shape,))
    return img.copy()


def _fmt_score(value: Any) -> str:
    """分數 → 說明文字用的短字串（3 位有效數字，整數不拖小數）。"""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(f):
        return "NaN"
    if math.isinf(f):
        return "∞" if f > 0 else "-∞"
    if f == int(f) and abs(f) < 1e12:
        return str(int(f))
    return "%.3g" % f


# --------------------------------------------------------------------------- #
# 排序 / 篩選（Qt-free 的純邏輯，方便單獨測）
# --------------------------------------------------------------------------- #
def _value_of(item: Dict[str, Any], key: str) -> Any:
    """取排序值：``score`` / ``bin`` / ``defect_id`` 是固定欄位，其餘查 features。"""
    if key == "score":
        return item.get("score")
    if key == "bin":
        return item.get("bin")
    if key == "defect_id":
        return item.get("defect_id")
    return (item.get("features") or {}).get(key)


def _sort_key(value: Any, none_rank: int) -> Tuple[int, float, str]:
    """把任意值壓成可比較的三元組；``None``/NaN 一律排到最後（不管升冪降冪）。"""
    if value is None:
        return (none_rank, 0.0, "")
    if isinstance(value, bool):
        return (0, float(value), "")
    if isinstance(value, (int, float, np.integer, np.floating)):
        f = float(value)
        return (none_rank, 0.0, "") if math.isnan(f) else (0, f, "")
    text = str(value)
    try:                                   # KLARF 的 DEFECTID 常是純數字字串
        return (0, float(text), "")
    except ValueError:
        return (1, 0.0, text)


def make_filter(spec: Any) -> Tuple[Optional[Callable[[Dict[str, Any]], bool]], str]:
    """篩選條件 → ``(predicate, 中文說明)``；``predicate=None`` 代表「全部」。

    支援的 ``spec``：

    ============================================  ================================
    spec                                          意思
    ============================================  ================================
    ``None`` / ``"all"`` / ``{"mode": "all"}``    全部顯示
    ``{"mode": "bin", "bin": 1}``                 只看某個 bin
    ``{"mode": "score_range", "lo":a, "hi":b}``   分數落在 [a, b]（直方圖點 bar 用）
    ``"failed"`` / ``{"mode": "failed"}``         只看跑失敗的（``ok=False``）
    可呼叫物件 ``fn(item) -> bool``               自訂條件
    ============================================  ================================
    """
    if spec is None:
        return None, ""
    if callable(spec):
        return (lambda it: bool(spec(it))), "custom filter"
    if isinstance(spec, str):
        spec = {"mode": spec}
    if not isinstance(spec, dict):
        raise TypeError("Unrecognised filter spec: %r" % (spec,))

    mode = str(spec.get("mode", "all"))
    if mode == "all":
        return None, ""
    if mode == "failed":
        return (lambda it: not bool(it.get("ok", True))), "failed only"
    if mode == "bin":
        want = spec.get("bin")
        want = None if want is None else int(want)
        return ((lambda it: it.get("bin") == want),
                "bin %s only" % ("—" if want is None else want))
    if mode == "score_range":
        lo = spec.get("lo")
        hi = spec.get("hi")
        lo_f = -float("inf") if lo is None else float(lo)
        hi_f = float("inf") if hi is None else float(hi)
        if lo_f > hi_f:
            lo_f, hi_f = hi_f, lo_f

        def _in_range(it: Dict[str, Any]) -> bool:
            s = it.get("score")
            if s is None:
                return False
            f = float(s)
            return not math.isnan(f) and lo_f <= f <= hi_f

        return _in_range, "score %s ~ %s" % (_fmt_score(lo_f), _fmt_score(hi_f))
    raise ValueError("Unknown filter mode: %r" % (mode,))


# --------------------------------------------------------------------------- #
# 條件 chip（可移除）
# --------------------------------------------------------------------------- #
class _Chip(QPushButton):
    """標頭上的一顆條件 chip：``排序：score ↓  ✕``。點一下就把該條件拿掉。"""

    def __init__(self, text: str, tip: str, parent: Optional[QWidget] = None):
        super().__init__("%s  ✕" % text, parent)
        self.setObjectName("galleryChip")
        self.label_text = text
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tip)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.refresh_style()

    def refresh_style(self) -> None:
        """（重新）套用 token 顏色 —— 換主題時由 GalleryPanel 呼叫。"""
        self.setStyleSheet(
            "QPushButton#galleryChip { background:%s; color:%s;"
            " border:1px solid %s; border-radius:9px; padding:2px 9px;"
            " font-size:11px; font-weight:500; min-height:16px; }"
            "QPushButton#galleryChip:hover { background:%s; }"
            % (TOKENS["accent_bg"], TOKENS["accent_active"],
               TOKENS["accent_border"], TOKENS["hover_warm_strong"])
        )


# --------------------------------------------------------------------------- #
# 網格本體（虛擬捲動的自繪畫布）
# --------------------------------------------------------------------------- #
class _GridView(QAbstractScrollArea):
    """縮圖網格畫布 —— **整個網格只有一個 widget**（viewport），tile 是畫的。

    捲動位置 + viewport 高度 → :meth:`_visible_range` 算出「這一瞬間該畫哪幾格」，
    ``paintEvent`` 只跑那個區間。所以 10 顆與 10,000 顆的每幀成本一樣。
    """

    selection_changed = Signal(object)      # list[str]
    defect_activated = Signal(str)
    thumbs_requested = Signal(object)       # list[str]：可視範圍內還沒有縮圖的

    _EMPTY_TEXT = "(Thumbnails for every defect appear here after a trial run)"
    _NO_MATCH_TEXT = "(No defect matches the current filter — try removing a chip above)"

    _MARGIN = 10
    _GAP = 8
    _PAD = 6
    _BAR_H = 4                              # bin 色條
    _CAPTION_H = 17

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.StrongFocus)
        self.viewport().setMouseTracking(True)
        self.setMinimumSize(220, 140)

        self._items: List[Dict[str, Any]] = []
        self._pos_of: Dict[str, int] = {}
        self._view: List[int] = []            # 顯示順序 -> _items 索引
        self._selected: List[str] = []
        self._anchor = -1

        self._sort_key: Optional[str] = None
        self._sort_desc = True
        self._filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None
        self._filter_text = ""

        self._thumb = int(THUMB_SIZES[1][1])
        self._cache: "OrderedDict[Tuple[str, int], QPixmap]" = OrderedDict()
        self._last_request: Tuple[int, int] = (-1, -1)

    # -- 資料 ---------------------------------------------------------------
    def set_items(self, items: Sequence[Dict[str, Any]]) -> None:
        norm: List[Dict[str, Any]] = []
        pos: Dict[str, int] = {}
        for raw in items or []:
            d = {
                "defect_id": str(raw.get("defect_id", "")),
                "score": _opt_float(raw.get("score")),
                "bin": _opt_int(raw.get("bin")),
                "ok": bool(raw.get("ok", True)),
                "features": dict(raw.get("features") or {}),
                "thumb": raw.get("thumb"),
            }
            pos[d["defect_id"]] = len(norm)
            norm.append(d)
        # 先把顯示清單清空再換資料：setValue(0) 會同步觸發 scrollContentsBy，
        # 那時若 _view 還指著舊清單的索引就會讀到已經不存在的項目。
        self._view = []
        self._last_request = (-1, -1)
        self._items = norm
        self._pos_of = pos
        self._cache.clear()
        self._selected = [i for i in self._selected if i in pos]
        self._anchor = -1
        self.verticalScrollBar().setValue(0)
        self.refresh()

    def set_thumb(self, defect_id: str, arr: Optional[np.ndarray]) -> bool:
        """補上（或換掉）某顆的縮圖；``defect_id`` 不在清單裡回傳 False。"""
        i = self._pos_of.get(str(defect_id))
        if i is None:
            return False
        self._items[i]["thumb"] = arr
        for key in [k for k in self._cache if k[0] == str(defect_id)]:
            del self._cache[key]
        self.viewport().update()
        return True

    def items(self) -> List[Dict[str, Any]]:
        return list(self._items)

    def total_count(self) -> int:
        return len(self._items)

    def displayed_count(self) -> int:
        return len(self._view)

    def displayed_ids(self) -> List[str]:
        return [self._items[i]["defect_id"] for i in self._view]

    def item_at(self, index: int) -> Optional[Dict[str, Any]]:
        if 0 <= index < len(self._view):
            return self._items[self._view[index]]
        return None

    # -- 排序 / 篩選 ---------------------------------------------------------
    def set_sort(self, key: Optional[str], descending: bool = True) -> None:
        self._sort_key = None if key in (None, "") else str(key)
        self._sort_desc = bool(descending)
        self.refresh()

    def sort_key(self) -> Optional[str]:
        return self._sort_key

    def sort_descending(self) -> bool:
        return self._sort_desc

    def set_filter(self, spec: Any) -> None:
        self._filter_fn, self._filter_text = make_filter(spec)
        self.verticalScrollBar().setValue(0)
        self.refresh()

    def filter_text(self) -> str:
        return self._filter_text

    def refresh(self) -> None:
        """重算顯示順序（篩選 → 排序）並重畫。"""
        idx = list(range(len(self._items)))
        if self._filter_fn is not None:
            fn = self._filter_fn
            keep = []
            for i in idx:
                try:
                    if fn(self._items[i]):
                        keep.append(i)
                except Exception:            # noqa: BLE001 — 自訂條件炸掉不該殺 UI
                    continue
            idx = keep
        if self._sort_key:
            key = self._sort_key
            none_rank = -1 if self._sort_desc else 2
            idx.sort(key=lambda i: _sort_key(_value_of(self._items[i], key),
                                             none_rank),
                     reverse=self._sort_desc)
        self._view = idx
        self._update_scrollbar()
        self.viewport().update()
        self._maybe_request_thumbs()

    # -- 選取 ---------------------------------------------------------------
    def selected_ids(self) -> List[str]:
        return list(self._selected)

    def set_selected(self, ids: Sequence[str], emit: bool = False) -> None:
        wanted = [str(i) for i in (ids or []) if str(i) in self._pos_of]
        changed = wanted != self._selected
        self._selected = wanted
        self.viewport().update()
        if changed and emit:
            self.selection_changed.emit(list(self._selected))

    # -- 縮圖大小 -----------------------------------------------------------
    def set_thumb_size(self, px: int) -> None:
        px = int(max(32, min(320, int(px))))
        if px == self._thumb:
            return
        self._thumb = px
        self._update_scrollbar()
        self.viewport().update()
        self._maybe_request_thumbs()

    def thumb_size(self) -> int:
        return self._thumb

    # -- 幾何 ---------------------------------------------------------------
    def _tile_w(self) -> int:
        return self._thumb + 2 * self._PAD

    def _tile_h(self) -> int:
        return (self._BAR_H + self._PAD + self._thumb + 3
                + self._CAPTION_H + self._PAD)

    def _cell_w(self) -> int:
        return self._tile_w() + self._GAP

    def _cell_h(self) -> int:
        return self._tile_h() + self._GAP

    def _viewport_size(self) -> Tuple[int, int]:
        vp = self.viewport()
        w = vp.width() or self.width() or 1
        h = vp.height() or self.height() or 1
        return int(w), int(h)

    def columns(self) -> int:
        w, _ = self._viewport_size()
        usable = max(1, w - 2 * self._MARGIN + self._GAP)
        return max(1, usable // self._cell_w())

    def _row_count(self) -> int:
        n = len(self._view)
        return 0 if n == 0 else int(math.ceil(n / float(self.columns())))

    def content_height(self) -> int:
        rows = self._row_count()
        return 0 if rows == 0 else 2 * self._MARGIN + rows * self._cell_h() - self._GAP

    def _update_scrollbar(self) -> None:
        _, vh = self._viewport_size()
        bar = self.verticalScrollBar()
        bar.setSingleStep(max(8, self._cell_h() // 3))
        bar.setPageStep(max(1, vh))
        bar.setRange(0, max(0, self.content_height() - vh))

    def _visible_range(self) -> Tuple[int, int]:
        """目前該畫（含 overscan）的顯示索引區間 ``[lo, hi)``。"""
        n = len(self._view)
        if n == 0:
            return (0, 0)
        cols = self.columns()
        cell_h = self._cell_h()
        _, vh = self._viewport_size()
        top = int(self.verticalScrollBar().value())
        first = (top - self._MARGIN) // cell_h - OVERSCAN_ROWS
        last = (top + vh - self._MARGIN) // cell_h + OVERSCAN_ROWS
        lo = max(0, min(n, int(first) * cols))
        hi = max(lo, min(n, (int(last) + 1) * cols))
        return (lo, hi)

    def visible_indices(self) -> List[int]:
        lo, hi = self._visible_range()
        return list(range(lo, hi))

    def tile_rect(self, index: int) -> QRect:
        """顯示索引 → viewport 座標的方框（給 hit-test / 測試點擊用）。"""
        cols = self.columns()
        row, col = divmod(int(index), cols)
        x = self._MARGIN + col * self._cell_w()
        y = self._MARGIN + row * self._cell_h() - int(self.verticalScrollBar().value())
        return QRect(int(x), int(y), self._tile_w(), self._tile_h())

    def index_at(self, pos: QPoint) -> Optional[int]:
        if not self._view:
            return None
        x = int(pos.x()) - self._MARGIN
        y = int(pos.y()) + int(self.verticalScrollBar().value()) - self._MARGIN
        if x < 0 or y < 0:
            return None
        cols = self.columns()
        col, in_x = divmod(x, self._cell_w())
        row, in_y = divmod(y, self._cell_h())
        if col >= cols or in_x >= self._tile_w() or in_y >= self._tile_h():
            return None                       # 點在格與格之間的空隙
        i = int(row) * cols + int(col)
        return i if 0 <= i < len(self._view) else None

    # -- 縮圖 LRU -----------------------------------------------------------
    def cache_size(self) -> int:
        return len(self._cache)

    def _pixmap_for(self, item: Dict[str, Any]) -> Optional[QPixmap]:
        arr = item.get("thumb")
        if arr is None:
            return None
        key = (item["defect_id"], self._thumb)
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        try:
            u8 = to_uint8(np.asarray(arr))
            if u8.ndim == 3 and u8.shape[2] not in (3, 4):
                u8 = u8[:, :, 0]
            pm = QPixmap.fromImage(_qimage_from_uint8(u8))
        except Exception:                     # noqa: BLE001 — 壞縮圖不該殺掉整頁
            return None
        s = self._thumb
        if pm.width() != s or pm.height() != s:
            mode = (Qt.SmoothTransformation if max(pm.width(), pm.height()) > s
                    else Qt.FastTransformation)
            pm = pm.scaled(QSize(s, s), Qt.KeepAspectRatio, mode)
        self._cache[key] = pm
        self._cache.move_to_end(key)
        while len(self._cache) > CACHE_CAP:
            self._cache.popitem(last=False)   # 丟最久沒用到的
        return pm

    def _maybe_request_thumbs(self) -> None:
        rng = self._visible_range()
        if rng == self._last_request:
            return
        self._last_request = rng
        missing = [self._items[self._view[i]]["defect_id"]
                   for i in range(rng[0], rng[1])
                   if self._items[self._view[i]].get("thumb") is None]
        if missing:
            self.thumbs_requested.emit(missing)

    # -- 說明文字 -----------------------------------------------------------
    def caption_at(self, index: int) -> str:
        item = self.item_at(index)
        return "" if item is None else caption_of(item)

    def placeholder_text(self) -> str:
        if not self._items:
            return self._EMPTY_TEXT
        if not self._view:
            return self._NO_MATCH_TEXT
        return ""

    # -- 繪圖 ---------------------------------------------------------------
    def paintEvent(self, _e) -> None:          # noqa: D102 - Qt hook
        p = QPainter(self.viewport())
        # 縮圖牆也用中性灰 —— 這裡是用眼睛掃整批的地方，背景偏差影響最大
        p.fillRect(self.viewport().rect(), QColor(TOKENS["image_backdrop"]))
        if not self._view:
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(self.viewport().rect(), Qt.AlignCenter,
                       self.placeholder_text())
            p.end()
            return
        small = QFont(p.font())
        small.setPointSize(8)
        p.setFont(small)
        lo, hi = self._visible_range()
        for i in range(lo, hi):
            self._paint_tile(p, i)
        p.end()

    def _paint_tile(self, p: QPainter, index: int) -> None:
        item = self.item_at(index)
        if item is None:
            return
        rect = self.tile_rect(index)
        selected = item["defect_id"] in self._selected

        p.setRenderHint(QPainter.Antialiasing, True)
        if selected:
            p.setPen(QPen(QColor(TOKENS["accent"]), 2))
            p.setBrush(QColor(TOKENS["accent_bg"]))
        else:
            p.setPen(QPen(QColor(TOKENS["border_default"]), 1))
            p.setBrush(QColor(TOKENS["bg_surface"]))
        p.drawRoundedRect(QRect(rect).adjusted(1, 1, -1, -1), 6, 6)

        # bin 色條（顏色只是輔助，bin 數字一定也寫在說明文字裡）
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(bin_hex(item)))
        p.drawRect(QRect(rect.left() + 5, rect.top() + 4,
                         rect.width() - 10, self._BAR_H))

        img_top = rect.top() + self._BAR_H + self._PAD
        img_rect = QRect(rect.left() + self._PAD, img_top, self._thumb, self._thumb)
        pm = self._pixmap_for(item)
        if pm is None:
            p.setPen(QPen(QColor(TOKENS["border_default"]), 1, Qt.DashLine))
            p.setBrush(QColor(TOKENS["bg_elevated"]))
            p.drawRect(img_rect)
            p.setPen(QColor(TOKENS["text_disabled"]))
            p.drawText(img_rect, Qt.AlignCenter, "loading…")
        else:
            p.setRenderHint(QPainter.SmoothPixmapTransform, False)
            x = img_rect.left() + (img_rect.width() - pm.width()) // 2
            y = img_rect.top() + (img_rect.height() - pm.height()) // 2
            p.drawPixmap(QPoint(x, y), pm)

        cap_rect = QRect(rect.left() + self._PAD, img_rect.bottom() + 3,
                         self._thumb, self._CAPTION_H)
        p.setPen(QColor(TOKENS["text_secondary"] if item["ok"]
                        else TOKENS["danger_text"]))
        text = p.fontMetrics().elidedText(caption_of(item), Qt.ElideMiddle,
                                          cap_rect.width())
        p.drawText(cap_rect, Qt.AlignLeft | Qt.AlignVCenter, text)

    # -- 互動 ---------------------------------------------------------------
    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.button() != Qt.LeftButton:
            return
        idx = self.index_at(e.position().toPoint())
        mods = e.modifiers()
        before = list(self._selected)
        if idx is None:
            self._selected = []
        elif mods & Qt.ShiftModifier and self._anchor >= 0:
            lo, hi = sorted((self._anchor, idx))
            self._selected = [self._items[self._view[i]]["defect_id"]
                              for i in range(lo, min(hi + 1, len(self._view)))]
        elif mods & (Qt.ControlModifier | Qt.MetaModifier):
            did = self._items[self._view[idx]]["defect_id"]
            if did in self._selected:
                self._selected = [i for i in self._selected if i != did]
            else:
                self._selected = self._selected + [did]
            self._anchor = idx
        else:
            self._selected = [self._items[self._view[idx]]["defect_id"]]
            self._anchor = idx
        self.viewport().update()
        if self._selected != before:
            self.selection_changed.emit(list(self._selected))
        e.accept()

    def mouseDoubleClickEvent(self, e) -> None:   # noqa: D102 - Qt hook
        if e.button() != Qt.LeftButton:
            return
        idx = self.index_at(e.position().toPoint())
        if idx is None:
            return
        item = self.item_at(idx)
        if item is None:
            return
        if self._selected != [item["defect_id"]]:
            self._selected = [item["defect_id"]]
            self._anchor = idx
            self.viewport().update()
            self.selection_changed.emit(list(self._selected))
        self.defect_activated.emit(item["defect_id"])
        e.accept()

    def scrollContentsBy(self, dx: int, dy: int) -> None:   # noqa: D102 - Qt hook
        self.viewport().update()
        self._maybe_request_thumbs()

    def resizeEvent(self, e) -> None:          # noqa: D102 - Qt hook
        super().resizeEvent(e)
        self._update_scrollbar()
        self._maybe_request_thumbs()


def bin_hex(item: Dict[str, Any]) -> str:
    """tile 色條顏色：失敗=紅、bin 1=綠、bin 0=灰、未判定=中性。"""
    if not item.get("ok", True):
        return TOKENS["danger"]
    b = item.get("bin")
    if b is None:
        return TOKENS["chip_neutral_border"]
    if int(b) == 0:
        return TOKENS["seg_disabled"]
    return TOKENS["success"]


def caption_of(item: Dict[str, Any]) -> str:
    """一行說明：``#id · bin 1 · 3.21``。

    **bin 一定寫成文字**，色條只是輔助 —— 色盲、投影機、黑白列印都要讀得到。
    """
    parts = ["#%s" % item.get("defect_id", "")]
    if not item.get("ok", True):
        parts.append("FAILED")
        return " · ".join(parts)
    b = item.get("bin")
    parts.append("bin %d" % int(b) if b is not None else "bin —")
    s = item.get("score")
    if s is not None:
        parts.append(_fmt_score(s))
    return " · ".join(parts)


def _opt_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _opt_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# 對外的面板（標頭 + 網格）
# --------------------------------------------------------------------------- #
class GalleryPanel(QWidget):
    """同屏比多顆：標頭（顯示筆數 + 排序 + 縮圖大小 + 條件 chip）+ 縮圖網格。

    主視窗這樣用：

    ``set_sort_keys([...])`` 一次（有哪些欄可排）→ 試跑完 ``set_items([...])``
    （每筆 = ``result_to_json_dict`` 的 dict 再加一個 ``thumb`` 鍵）→ 縮圖用
    :func:`make_thumb` 在背景產生後 ``set_thumb(defect_id, arr)`` 逐張補。
    直方圖點一根 bar → :meth:`filter_by_score_range`。
    使用者雙擊某顆 → ``defect_activated(defect_id)``，主視窗把單顆預覽跳過去。
    """

    selection_changed = Signal(object)      # list[str]
    defect_activated = Signal(str)
    thumbs_requested = Signal(object)       # list[str]

    _ORDER_DESC = "↓ High to low"
    _ORDER_ASC = "↑ Low to high"
    #: 排序下拉的第一項 = 不排序（維持 set_items 給的原始順序）。
    NO_SORT = "(original order)"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # ---- 標頭第一列：筆數 + 排序 + 縮圖大小 ----------------------------
        head = QHBoxLayout()
        head.setContentsMargins(2, 0, 2, 0)
        head.setSpacing(6)

        self.count_label = QLabel("")
        self.count_label.setObjectName("galleryCount")
        self.count_label.setToolTip("Defects shown after filtering / total in this batch")
        self.count_label.setStyleSheet("color:%s; font-weight:700;"
                                       % TOKENS["text_primary"])
        head.addWidget(self.count_label)
        head.addSpacing(6)

        sort_label = QLabel("Sort by")
        sort_label.setToolTip("Sort by a field: score, any feature, or defect id")
        head.addWidget(sort_label)

        self.sort_combo = QComboBox()
        self.sort_combo.setToolTip("Sort by a field: score, any feature, or defect id")
        self.sort_combo.setMinimumWidth(120)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        head.addWidget(self.sort_combo)

        self.order_button = QPushButton(self._ORDER_DESC)
        self.order_button.setToolTip("Toggle descending / ascending")
        self.order_button.setProperty("variant", "ghost")
        self.order_button.clicked.connect(self._toggle_order)
        head.addWidget(self.order_button)

        head.addStretch(1)

        zoom_label = QLabel("Thumbnail")
        zoom_label.setToolTip("Thumbnail size: smaller shows more, larger shows more detail")
        head.addWidget(zoom_label)

        self.zoom_combo = QComboBox()
        self.zoom_combo.setToolTip("Thumbnail size: smaller shows more, larger shows more detail")
        for name, px in THUMB_SIZES:
            self.zoom_combo.addItem(name, px)
        self.zoom_combo.setCurrentIndex(1)
        self.zoom_combo.currentIndexChanged.connect(self._on_zoom_changed)
        head.addWidget(self.zoom_combo)
        outer.addLayout(head)

        # ---- 標頭第二列：條件 chip -----------------------------------------
        self._chip_row = QHBoxLayout()
        self._chip_row.setContentsMargins(2, 0, 2, 0)
        self._chip_row.setSpacing(5)
        self._chip_row.addStretch(1)
        self._chips: List[_Chip] = []
        outer.addLayout(self._chip_row)

        # ---- 網格 ------------------------------------------------------------
        self.grid = _GridView(self)
        self.grid.selection_changed.connect(self.selection_changed)
        self.grid.defect_activated.connect(self.defect_activated)
        self.grid.thumbs_requested.connect(self.thumbs_requested)
        outer.addWidget(self.grid, 1)

        self._sort_keys: List[str] = []
        self.set_sort_keys(["score"])
        self.grid.set_thumb_size(int(THUMB_SIZES[1][1]))
        self._refresh_header()
        apply_button_cursors(self)

    # -- 資料（主視窗呼叫）---------------------------------------------------
    def set_items(self, items: Sequence[Dict[str, Any]]) -> None:
        """餵資料。每筆：``{defect_id, score, bin, ok, features, thumb}``。

        ``thumb`` 可以是 ``None``（先畫「載入中…」佔位磚，之後用
        :meth:`set_thumb` 補）。這裡**不會**去讀檔或跑引擎。
        """
        self.grid.set_items(items)
        self._refresh_header()

    def set_thumb(self, defect_id: str, arr: Optional[np.ndarray]) -> bool:
        """補上單顆的縮圖（背景執行緒算好後回主執行緒呼叫）。"""
        return self.grid.set_thumb(defect_id, arr)

    def set_thumbs(self, mapping: Dict[str, Optional[np.ndarray]]) -> int:
        """一次補一批縮圖；回傳成功貼上的張數。"""
        return sum(1 for k, v in (mapping or {}).items() if self.grid.set_thumb(k, v))

    # -- 排序 ---------------------------------------------------------------
    def set_sort_keys(self, keys: Sequence[str]) -> None:
        """設定排序下拉的可選欄位（``defect_id`` 一定會補在最後）。

        下拉的第一項固定是 :data:`NO_SORT`（原始順序）；目前的排序欄位若還在
        新清單裡會保留，否則預設挑 ``score``（調參最常看的欄）。
        """
        keys = [str(k) for k in (keys or [])]
        if "defect_id" not in keys:
            keys = keys + ["defect_id"]
        seen: List[str] = []
        for k in keys:
            if k and k not in seen:
                seen.append(k)
        self._sort_keys = seen

        current = self.grid.sort_key()
        if current not in seen:
            current = "score" if "score" in seen else None
        block = self.sort_combo.blockSignals(True)
        self.sort_combo.clear()
        self.sort_combo.addItem(self.NO_SORT)
        self.sort_combo.addItems(seen)
        self.sort_combo.setCurrentIndex(seen.index(current) + 1 if current else 0)
        self.sort_combo.blockSignals(block)
        self.grid.set_sort(current, self.grid.sort_descending())
        self._refresh_header()

    def sort_keys(self) -> List[str]:
        return list(self._sort_keys)

    def set_sort(self, key: Optional[str], descending: bool = True) -> None:
        """排序。``key`` 可以是 ``"score"`` / 任一特徵名 / ``"defect_id"``；
        認不得的 key（或該欄全都沒值）→ 維持原本順序，不會炸。"""
        self.grid.set_sort(key, descending)
        block = self.sort_combo.blockSignals(True)
        if key and key in self._sort_keys:
            self.sort_combo.setCurrentIndex(self._sort_keys.index(key) + 1)
        elif not key:
            self.sort_combo.setCurrentIndex(0)
        self.sort_combo.blockSignals(block)
        self.order_button.setText(self._ORDER_DESC if descending
                                  else self._ORDER_ASC)
        self._refresh_header()

    def sort_key(self) -> Optional[str]:
        return self.grid.sort_key()

    def sort_descending(self) -> bool:
        return self.grid.sort_descending()

    # -- 篩選 ---------------------------------------------------------------
    def set_filter(self, spec: Any) -> None:
        """設定篩選條件（見 :func:`make_filter` 支援的寫法）。"""
        self.grid.set_filter(spec)
        self._refresh_header()

    def filter_by_score_range(self, lo: Optional[float],
                              hi: Optional[float]) -> None:
        """只顯示分數落在 ``[lo, hi]`` 的 defect —— 直方圖點一根 bar 就呼叫這個。"""
        self.set_filter({"mode": "score_range", "lo": lo, "hi": hi})

    def filter_by_bin(self, bin_value: Optional[int]) -> None:
        """只顯示某個 bin。"""
        self.set_filter({"mode": "bin", "bin": bin_value})

    def show_failed_only(self) -> None:
        """只顯示跑失敗的 defect（``ok=False``）。"""
        self.set_filter({"mode": "failed"})

    def clear_filter(self) -> None:
        """清掉篩選，回到全部。"""
        self.set_filter(None)

    def filter_text(self) -> str:
        return self.grid.filter_text()

    # -- 縮圖大小 -----------------------------------------------------------
    def set_thumb_size(self, px: int) -> None:
        """設定縮圖邊長（會對齊到最接近的 小/中/大 選項）。"""
        px = int(px)
        best = min(THUMB_SIZES, key=lambda kv: abs(kv[1] - px))
        block = self.zoom_combo.blockSignals(True)
        self.zoom_combo.setCurrentIndex([s[1] for s in THUMB_SIZES].index(best[1]))
        self.zoom_combo.blockSignals(block)
        self.grid.set_thumb_size(best[1])

    def thumb_size(self) -> int:
        return self.grid.thumb_size()

    # -- 選取 ---------------------------------------------------------------
    def selected_ids(self) -> List[str]:
        return self.grid.selected_ids()

    def set_selected(self, ids: Sequence[str]) -> None:
        """程式設定選取（不發 ``selection_changed`` —— 那是使用者點擊才發的）。"""
        self.grid.set_selected(ids, emit=False)

    # -- 查詢（測試 / 主視窗都用得到）---------------------------------------
    def displayed_ids(self) -> List[str]:
        """目前依序顯示的 defect_id（已套用篩選與排序）。"""
        return self.grid.displayed_ids()

    def displayed_count(self) -> int:
        return self.grid.displayed_count()

    def total_count(self) -> int:
        return self.grid.total_count()

    def visible_indices(self) -> List[int]:
        """**這一瞬間真的會被畫出來**的顯示索引（含 1 列 overscan）。

        虛擬捲動的證據：不管清單有 20 顆還是 10,000 顆，這個清單長度只跟
        viewport 大小有關。
        """
        return self.grid.visible_indices()

    def caption_at(self, index: int) -> str:
        return self.grid.caption_at(index)

    def caption_of(self, defect_id: str) -> str:
        for i, did in enumerate(self.displayed_ids()):
            if did == str(defect_id):
                return self.grid.caption_at(i)
        return ""

    def bin_color(self, defect_id: str) -> str:
        for item in self.grid.items():
            if item["defect_id"] == str(defect_id):
                return bin_hex(item)
        return ""

    def cache_size(self) -> int:
        return self.grid.cache_size()

    def header_text(self) -> str:
        return self.count_label.text()

    def empty_text(self) -> str:
        """目前顯示的空狀態文字（有 tile 時為空字串）。"""
        return self.grid.placeholder_text()

    def chips(self) -> List[_Chip]:
        """標頭上的條件 chip（第一顆是排序、之後是篩選）。"""
        return list(self._chips)

    def chip_texts(self) -> List[str]:
        return [c.label_text for c in self._chips]

    def refresh_styles(self) -> None:
        """換主題之後重新取色（chip 與網格都是自繪/內嵌樣式）。"""
        for chip in self._chips:
            chip.refresh_style()
        self.grid.viewport().update()
        self.update()

    # -- 內部 ---------------------------------------------------------------
    def _on_sort_changed(self, idx: int) -> None:
        key = None if idx <= 0 else self.sort_combo.currentText()
        self.grid.set_sort(key, self.grid.sort_descending())
        self._refresh_header()

    def _toggle_order(self) -> None:
        self.set_sort(self.grid.sort_key(), not self.grid.sort_descending())

    def _on_zoom_changed(self, _idx: int) -> None:
        px = self.zoom_combo.currentData()
        if px is not None:
            self.grid.set_thumb_size(int(px))

    def _clear_chips(self) -> None:
        for chip in self._chips:
            self._chip_row.removeWidget(chip)
            chip.setParent(None)
            chip.deleteLater()
        self._chips = []

    def _add_chip(self, text: str, tip: str, on_remove: Callable[[], None]) -> None:
        chip = _Chip(text, tip, self)
        chip.clicked.connect(lambda: on_remove())
        self._chip_row.insertWidget(len(self._chips), chip)
        self._chips.append(chip)

    def _refresh_header(self) -> None:
        self.count_label.setText("Showing %d / %d defects"
                                 % (self.grid.displayed_count(),
                                    self.grid.total_count()))
        self.order_button.setText(self._ORDER_DESC if self.grid.sort_descending()
                                  else self._ORDER_ASC)
        self._clear_chips()
        key = self.grid.sort_key()
        if key:
            arrow = "↓" if self.grid.sort_descending() else "↑"
            self._add_chip("Sort: %s %s" % (key, arrow),
                           "Click to clear sorting and return to the original order",
                           lambda: self.set_sort(None, self.grid.sort_descending()))
        ftext = self.grid.filter_text()
        if ftext:
            self._add_chip("Filter: %s" % ftext, "Click to remove this filter",
                           self.clear_filter)

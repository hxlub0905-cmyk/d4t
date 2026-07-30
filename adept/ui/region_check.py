# ADEPT Studio — 區域跨顆檢視 (F7-11 第三批).
"""把具名區域畫在**很多顆** defect 的縮圖上，一次看完。

為什麼一張圖不夠
----------------
調一個區域的設定時，看單顆是不夠的：**在第 1 顆剛好的設定，第 50 顆可能整個
偏掉。** 而這正是這一整段的前提 —— patch 是以缺陷為中心裁的，所以結構在每張
patch 裡的位置本來就不一樣。設定對不對，是一個**關於整批**的問題，
不是關於這一張圖的問題。

所以這個視窗只回答一個問題：**這個區域設定，在整批上普遍成立嗎？**
畫面上因此只有三件事：每顆的縮圖、框、以及「這顆定位成功了沒」。

「只看失敗的」是預設就想得到的操作
----------------------------------
定位失敗的那些才是要看的。它們可能是「本來就沒有結構可認」（正常，整張量就對），
也可能是「參數設得太緊」（要調）。兩者只有看圖分得出來，所以要能一鍵只看它們。

本模組的 :func:`check_regions` 不碰 Qt，可以 headless 測試；
Qt 的部分只負責把它算出來的東西畫出來。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from adept.core.pipeline import get_step
from adept.core.pipeline.engine import run_defect

from .gallery import make_thumb, thumb_placement
from .theme import TOKENS
from .widgets import _qimage_from_uint8

__all__ = ["check_regions", "regions_of_node", "RegionThumb", "RegionCheckWindow"]

#: 一次最多檢查幾顆（再多也看不完，而且每顆都要跑一次 pipeline）。
MAX_CHECK = 200


def regions_of_node(node: Any) -> List[str]:
    """一個節點會定義哪些具名區域（不是 Region 卡就是空清單）。"""
    try:
        step_cls = get_step(node.step)
        return [str(r) for r in step_cls.resolve_regions_out(node.params)]
    except Exception:                       # noqa: BLE001 — 顯示用
        return []


def check_regions(recipe: Any, items: Sequence[Any], kind: str, node_id: str,
                  regions: Sequence[str], thumb_size: int = 120,
                  source: Optional[str] = None) -> List[Dict[str, Any]]:
    """對每一顆跑到 ``node_id`` 為止，取出縮圖與該節點定義的區域框。

    回傳每顆一個 dict：``defect_id`` / ``thumb``（uint8 方形縮圖）/
    ``boxes``（``[(區域名, (x, y, w, h)), …]``，座標已經是**縮圖上的像素**）/
    ``located``（這顆定位成功了沒）/ ``error``。

    **永不 raise** —— 單顆出錯只會變成一顆 ``error`` 不為 None 的格子，
    跟引擎「單顆爆不殺整批」的契約一致。
    """
    out: List[Dict[str, Any]] = []
    wanted = [str(r) for r in regions]

    for item in list(items)[:MAX_CHECK]:
        defect_id = str(getattr(item, "defect_id", ""))
        entry: Dict[str, Any] = {"defect_id": defect_id, "thumb": None,
                                 "boxes": [], "located": True, "error": None}
        try:
            res = run_defect(recipe, item, kind, keep_context=True,
                             upto_node=node_id)
        except Exception as e:              # noqa: BLE001 — 合約外的意外
            entry["error"] = "%s: %s" % (type(e).__name__, e)
            out.append(entry)
            continue

        ctx = getattr(res, "context", None)
        images = dict(getattr(ctx, "images", {}) or {}) if ctx is not None else {}
        if not res.ok:
            entry["error"] = res.error
        img = images.get(str(source)) if source else None
        if img is None:
            for key in ("ref", "test"):      # 定位是在 ref 上做的，優先顯示它
                if key in images:
                    img = images[key]
                    break
        if img is None and images:
            img = next(iter(images.values()))
        if img is None:
            entry["error"] = entry["error"] or "no image to show"
            out.append(entry)
            continue

        arr = np.asarray(img)
        entry["thumb"] = make_thumb(arr, thumb_size)
        x0, y0, tw, th = thumb_placement(arr.shape, thumb_size)

        names = set(ctx.roi_names() if ctx is not None else [])
        for name in wanted:
            if name not in names:
                continue
            nx, ny, nw, nh = ctx.require_roi(name).norm_rect
            entry["boxes"].append((name, (
                x0 + nx * tw, y0 + ny * th, max(1.0, nw * tw), max(1.0, nh * th))))

        # ``locate_ok`` 是投影定位卡吐的旗標；沒有這個特徵的 Region 卡
        # （例如手畫的框）一律當成定位成功 —— 它本來就不需要定位。
        feats = dict(getattr(res, "features", {}) or {})
        flags = [v for k, v in feats.items() if k.endswith("locate_ok")]
        entry["located"] = all(float(v) > 0.5 for v in flags) if flags else True
        out.append(entry)

    return out


def summarize(results: Sequence[Dict[str, Any]]) -> str:
    """一行摘要（測試與標題列共用；不用去讀畫素）。"""
    total = len(results)
    failed = sum(1 for r in results if not r.get("located", True))
    errors = sum(1 for r in results if r.get("error"))
    parts = ["%d defects" % total,
             "%d located" % (total - failed),
             "%d fell back to the whole image" % failed]
    if errors:
        parts.append("%d could not be computed" % errors)
    return " · ".join(parts)


class RegionThumb(QFrame):
    """一格：縮圖 + 區域框 + defect id；定位失敗的用邊框標出來。"""

    clicked = Signal(str)

    def __init__(self, entry: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.entry = dict(entry)
        self.defect_id = str(entry.get("defect_id", ""))
        self.setCursor(Qt.PointingHandCursor)
        thumb = entry.get("thumb")
        self._size = int(thumb.shape[0]) if thumb is not None else 120
        self.setFixedSize(self._size + 8, self._size + 24)
        tip = self.defect_id
        if entry.get("error"):
            tip += "\n%s" % entry["error"]
        elif not entry.get("located", True):
            tip += "\nno structure found - measured the whole image"
        self.setToolTip(tip)

    def located(self) -> bool:
        return bool(self.entry.get("located", True))

    def mousePressEvent(self, e) -> None:      # noqa: D102 - Qt hook
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.defect_id)
        super().mousePressEvent(e)

    def paintEvent(self, _e) -> None:          # noqa: D102 - Qt hook
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        thumb = self.entry.get("thumb")
        s = self._size

        if thumb is not None:
            p.drawPixmap(4, 4, QPixmap.fromImage(_qimage_from_uint8(thumb)))
        else:
            p.fillRect(QRectF(4, 4, s, s), QColor(TOKENS["disabled_bg"]))

        # 第一個框是**使用者命名的那個區域**，其餘是它的鄰段。用實線 vs 虛線
        # 分開 —— 三個一樣的藍框排在一起，看不出哪個是主角。
        for i, (_name, (x, y, w, h)) in enumerate(self.entry.get("boxes") or []):
            pen = QPen(QColor(TOKENS["accent"]), 1.8)
            if i:
                pen.setWidthF(1.2)
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(4 + x, 4 + y, w, h))

        # 定位失敗 / 算不出來的用外框標出來 —— 這是這個視窗最重要的一個訊號
        if self.entry.get("error"):
            edge = QColor(TOKENS["danger"])
        elif not self.located():
            edge = QColor(TOKENS["warning"])
        else:
            edge = QColor(TOKENS["border_default"])
        p.setPen(QPen(edge, 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(3, 3, s + 2, s + 2))

        p.setPen(QColor(TOKENS["text_secondary"]))
        f = p.font()
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1.0))
        p.setFont(f)
        p.drawText(QRectF(4, s + 6, s, 14), Qt.AlignHCenter | Qt.AlignVCenter,
                   self.defect_id)
        p.end()


class RegionCheckWindow(QDialog):
    """區域跨顆檢視。非 modal —— 使用者要能一邊看它、一邊在主視窗調參數。"""

    defect_activated = Signal(str)

    _COLUMNS = 6

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Check region across defects")
        self.setModal(False)
        self.resize(880, 620)
        self._results: List[Dict[str, Any]] = []
        self._cells: List[RegionThumb] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        head = QHBoxLayout()
        self.title = QLabel("", self)
        self.title.setObjectName("paramTitle")
        head.addWidget(self.title, 1)
        self.only_failed = QCheckBox("Only the ones that fell back", self)
        self.only_failed.setToolTip(
            "Show only the defects where no structure could be found. Those are "
            "either patches with nothing to lock onto - which is fine, the whole "
            "image is the right thing to measure there - or a sign the settings "
            "are too tight. Looking at them is the only way to tell.")
        self.only_failed.toggled.connect(lambda _v: self._relayout())
        head.addWidget(self.only_failed)
        outer.addLayout(head)

        self.summary = QLabel("", self)
        self.summary.setObjectName("paramHint")
        self.summary.setWordWrap(True)
        outer.addWidget(self.summary)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._host = QWidget()
        self._grid = QGridLayout(self._host)
        self._grid.setContentsMargins(2, 2, 2, 2)
        self._grid.setSpacing(6)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)

    # ---- 對外 -------------------------------------------------------------
    def set_results(self, regions: Sequence[str],
                    results: Sequence[Dict[str, Any]]) -> None:
        self._results = list(results or [])
        names = ", ".join(str(r) for r in regions) or "(no region)"
        self.title.setText("Region: %s" % names)
        self.summary.setText(summarize(self._results))
        self._relayout()

    def summary_text(self) -> str:
        return self.summary.text()

    def visible_ids(self) -> List[str]:
        """目前排在畫面上的 defect id（測試用；不必去讀畫素）。"""
        return [c.defect_id for c in self._cells]

    def failed_ids(self) -> List[str]:
        return [str(r.get("defect_id", "")) for r in self._results
                if not r.get("located", True) or r.get("error")]

    # ---- 內部 -------------------------------------------------------------
    def _relayout(self) -> None:
        for cell in self._cells:
            self._grid.removeWidget(cell)
            cell.setParent(None)
            cell.deleteLater()
        self._cells = []

        shown = self._results
        if self.only_failed.isChecked():
            shown = [r for r in shown
                     if not r.get("located", True) or r.get("error")]

        for i, entry in enumerate(shown):
            cell = RegionThumb(entry, self._host)
            cell.clicked.connect(self.defect_activated)
            self._grid.addWidget(cell, i // self._COLUMNS, i % self._COLUMNS)
            self._cells.append(cell)

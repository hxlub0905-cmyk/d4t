# d4t Studio — authored 2026-09-17 (F103).
"""lattice_dialog —— **把 cell 鋪回原圖**看：格線有沒有落在同一種結構上。

使用者問「假設算不對我該怎麼知道」。對話框上已經有四個數字（一致性、銳利度、
k× 提示、諧波修正），但數字回答的是「疊得齊不齊」，不是「週期是不是**你要的**
那一個」—— 半週期的格子彼此真的蠻像的，一致性 0.93 是誠實的回答（`template_dialog`
的 `BLURRED_BELOW` 說明）。分得開這件事的只有一種看法：把格線鋪回原圖，
**每一格框住的東西都一樣**就是對的；格線在圖的另一頭漂到別的結構上，就是錯的。
那是一眼的事，不需要懂任何分數。

畫的是**引擎真的用的那組格子**：`GoldenCell.origin`（已含錨定的捲動）起、每
`px`／`py` 一格，跟 `golden.tile_coords` 同一條規則 —— UI 自己再算一次很容易
變成「畫面上的格線」跟「疊進去的格子」差一個錨定量，那種 bug 極難發現。

用既有的 `ImageView`（滾輪縮放、拖曳平移、雙擊 fit）—— 7680² 的圖鋪 40 px 的
格線要放大到 1:1 才看得出漂不漂，而那三個手勢它本來就有。格子超過
:data:`MAX_BOXES` 只畫離中心最近的那些並講出來（`set_overlay` 畫幾萬個框會卡）。
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget,
)

from pitchapp.core.algo import golden as algo_golden
from pitchapp.core.algo import period2d as algo_period2d

from . import fit_screen
from .image_view import ImageView
from .icons import apply_button_cursors   # 不走 `widgets` 轉出口（見 pitch_helper）

__all__ = ["LatticeDialog", "lattice_boxes", "MAX_BOXES"]

#: 最多畫幾格（離影像中心最近的優先）。1000×1000、40 px 是 625 格；7680² 是
#: 36,864 格 —— 畫得出來但每一次平移都要重畫幾萬個矩形。
MAX_BOXES = 4000


def lattice_boxes(shape: Tuple[int, int], px: float, py: float,
                  origin: Tuple[float, float], periodic: Tuple[bool, bool],
                  cap: int = MAX_BOXES) -> Tuple[List[Tuple[float, float, float, float]], int]:
    """格子的**正規化**矩形 ``(nx, ny, nw, nh)`` 與總格數（畫的可能比總數少）。

    沒有週期的那一軸一格就是整張影像 —— 那一軸不切，跟 `build_golden_cell`
    把 ``px`` 設成整張寬的做法一致。

    週期與原點可以是小數（F105，`GoldenCell.period_x`／`origin`）：第 k 格在
    ``origin + k·period``，不是整數步進 —— 79.5 對 79 在 4000 px 上差 25 px，
    格線就是這樣「靠邊會滑」的。整數參數時跟 `tile_coords` 畫的一模一樣。
    """
    h, w = int(shape[0]), int(shape[1])
    if h < 1 or w < 1:
        return [], 0
    px = float(px) if periodic[0] and float(px) >= 1 else float(w)
    py = float(py) if periodic[1] and float(py) >= 1 else float(h)
    ox = float(origin[0]) if periodic[0] else 0.0
    oy = float(origin[1]) if periodic[1] else 0.0
    coords = algo_golden.cell_origins((h, w), px, py, (ox, oy))
    total = len(coords)
    if total > cap:
        cx, cy = w / 2.0, h / 2.0
        coords.sort(key=lambda t: (t[0] + px / 2.0 - cx) ** 2 + (t[1] + py / 2.0 - cy) ** 2)
        coords = coords[:cap]
    boxes = [(x / float(w), y / float(h), px / float(w), py / float(h))
             for x, y in coords]
    return boxes, total


class LatticeDialog(QDialog):
    """一張圖、一組格線、一句話。非 modal —— 開著它回去改 cell 尺寸再看。

    它是模板對話框上那顆「Grid」開關的另一半（2026-09-17 使用者：「改成類似格線
    的開關按鈕，可以開啟顯示或關閉顯示」）：開＝這個視窗出現，關＝收起來。使用者
    直接把視窗關掉時要讓開關跟著彈回來，所以關閉會發 :attr:`closed`。
    """

    #: 使用者關掉了這個視窗（按 Close、按 ✕、按 Esc）。
    closed = Signal()

    def __init__(self, image: Any, px: int, py: int,
                 origin: Tuple[int, int], periodic: Tuple[bool, bool],
                 name: str = "", parent: Optional[QWidget] = None,
                 marks: Optional[Sequence[Tuple[int, int]]] = None):
        super().__init__(parent)
        self.setWindowTitle("Cell grid on the image")
        fit_screen.fit(self, 1000, 760)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self.view = ImageView(self)
        lay.addWidget(self.view, 1)
        self.caption = QLabel("", self)
        self.caption.setObjectName("paramHint")
        self.caption.setWordWrap(True)
        lay.addWidget(self.caption)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Close, Qt.Horizontal, self)
        self.buttons.rejected.connect(self.reject)
        self.buttons.clicked.connect(lambda _b: self.reject())
        lay.addWidget(self.buttons)
        self.rejected.connect(self.closed.emit)

        self._name = str(name or "")
        self.set_lattice(image, px, py, origin, periodic, marks)
        apply_button_cursors(self)

    def closeEvent(self, e) -> None:  # Qt hook
        super().closeEvent(e)
        self.closed.emit()

    def set_lattice(self, image: Any, px: float, py: float,
                    origin: Tuple[float, float], periodic: Tuple[bool, bool],
                    marks: Optional[Sequence[Tuple[int, int]]] = None) -> None:
        arr = np.asarray(image)
        if arr.size == 0 or arr.ndim < 2:
            self.view.set_image(None)
            self.caption.setText("(no image)")
            return
        self.view.set_image(arr)
        boxes, total = lattice_boxes(arr.shape[:2], px, py, origin, periodic)
        self.view.set_overlay(boxes)
        self.shown, self.total = len(boxes), total
        fx, fy = algo_period2d.fmt_px(px), algo_period2d.fmt_px(py)
        axis = {(True, True): "%s x %s px" % (fx, fy),
                (True, False): "%s px across (no period down)" % fx,
                (False, True): "%s px down (no period across)" % fy,
                (False, False): "no period"}[(bool(periodic[0]), bool(periodic[1]))]
        text = ("Every box is one cell as the template sees it: %s, %d cells"
                % (axis, total))
        if len(boxes) < total:
            text += " (the %d nearest the centre are drawn)" % len(boxes)
        text += (". If the boxes frame the same structure everywhere, the "
                 "period and phase are right; if they drift onto something "
                 "else towards one side, the period is off by a little. "
                 "Wheel zooms, drag pans, double-click fits.")
        self.caption.setText(text)

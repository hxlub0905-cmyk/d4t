# 調參迴圈的記憶 —— authored 2026-09-08 (X1).
"""**「剛才那個改動讓它變好還是變壞」** —— 這個工具以前答不出來的那一句。

缺口長什麼樣
------------
引擎那一端該有的都有：`runs.db` 存得下每一次跑、CLI 有 ``runs`` / ``rescore``、
`viewmodel.accuracy_at` 算得出這個門檻下的正確率。可是 ``d4t/ui/`` **一處都
沒有碰過那個 db** —— Studio 每按一次 Run trial 就把上一次的結果整個蓋掉。

於是使用者答得出「現在準不準」（78%），答不出「**剛才那一下**讓它從幾變成
幾」。而調參的本質正好就是一連串「改一點、看差多少」：一個只講絕對值的畫面，
等於要求使用者自己記住上一個數字 —— 而他一輪要改十幾格。

這一份補的不是「算」，是「**留住上一次**」
------------------------------------------
所以這裡沒有任何新的統計：正確率仍然走
:func:`~d4t.ui.viewmodel.accuracy_at`（＝ `core.export.summarize`，跟 CLI 與
Excel 報表同一份邏輯，不另寫一份會漂的）。這一份只做三件事：

1. 把一次跑**壓成一小塊 JSON**（:func:`snapshot`）；
2. 兩塊 JSON 相減成一行字（:func:`diff_line`）；
3. 把釘住的那一塊存進 QSettings（:class:`BaselineStore`），
   **關窗重開還在**。

為什麼是 QSettings 而不是 `runs.db`
-----------------------------------
釘住的 baseline 是**這台機器上這個人**的工作狀態（跟主題、欄寬、上次的版面
同一類），不是那一批資料的一部分。寫進 `runs.db` 的話，把 lot 資料夾複製給
同事等於連他的 baseline 一起送過去，而那個數字對他沒有意義。

⚠ **算的那兩支不碰 Qt**（:func:`snapshot` / :func:`diff_line` 是純函式，
測起來不用開視窗），畫的那一塊（:class:`BaselineBar`）才碰 —— 這一份是那條
橫條的家，`CLAUDE.md` §4「一塊新面板一個新模組」的直接套用。
"""
from __future__ import annotations
from d4t.core.log import swallowed

import json
import time
from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

__all__ = [
    "snapshot", "diff_line", "headline", "BaselineStore", "default_store",
    "BaselineBar", "SETTINGS_KEY",
]

#: 釘住的那一塊住在 QSettings 的哪一格（跟 ``ui/columns`` 同一組設定）。
SETTINGS_KEY = "ui/baseline_run"


def _finite(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f or f in (float("inf"), float("-inf")) else f


def snapshot(results: Sequence[Dict[str, Any]],
             ground_truth: Optional[Dict[Any, Any]] = None,
             bins: Optional[Dict[str, int]] = None,
             threshold: Optional[float] = None,
             label: str = "",
             decide: Any = None) -> Dict[str, Any]:
    """一次跑 → 一小塊可以存進 JSON 的東西。

    ``threshold`` 有給就照它重算 bin（等同拖門檻線的那條路，
    :func:`~d4t.ui.viewmodel.accuracy_at`）；沒給就用結果裡引擎判的 bin。

    **沒有 ground truth 也要回一塊東西**，只是 ``accuracy`` 那三格是 ``None``：
    「這一輪比上一輪多抓了 5 顆」在沒有答案卷的時候仍然是使用者要看的 ——
    他自己知道那 5 顆是不是他要的。回 ``None`` 的話畫面上就什麼都不剩。
    """
    from d4t.core.pipeline.decide_tree import called_real, positive_bins

    rows = list(results or [])
    # 「判成真的」看每一類標的好消息／壞消息（F122 期 3；沒標的照舊 bin != 0）
    # —— 跟正確率那一行、Results 表上紅著的格子同一條規矩。
    outcomes = decide.bin_outcomes() if decide is not None else {}
    flagged = sum(1 for r in rows if called_real(r.get("bin"), outcomes))

    out: Dict[str, Any] = {
        "at": float(time.time()),
        "label": str(label or ""),
        "n": len(rows),
        "n_ok": sum(1 for r in rows if r.get("ok")),
        "flagged": flagged,
        "accuracy": None,
        "missed": None,
        "false_alarm": None,
        "n_evaluated": 0,
    }
    if not ground_truth or not rows:
        return out

    # 走跟拖門檻線一模一樣的那條路 —— 這裡刻意不自己數 tp/fp。
    from .viewmodel import accuracy_at
    if threshold is None:
        from d4t.core.export import summarize
        g = summarize(rows, ground_truth=ground_truth,
                      positive_bins=positive_bins(decide, rows)
                      ).get("ground_truth")
    else:
        g = accuracy_at(rows, float(threshold), bins, ground_truth)
    if not g:
        return out
    out["accuracy"] = _finite(g.get("accuracy"))
    out["missed"] = int(g.get("fn") or 0)
    out["false_alarm"] = int(g.get("fp") or 0)
    out["n_evaluated"] = int(g.get("n_evaluated") or 0)
    return out


def _signed(delta: float, digits: int = 0) -> str:
    """``+6`` / ``-2`` / ``+0``。

    **零也要寫出來**，而且寫成 ``+0`` 不是留白：一格空的差值分不出
    「沒有變」與「上一輪沒有這個數字」，而那兩件事對調參的人意思相反。
    """
    fmt = "%%+.%df" % int(digits)
    text = fmt % float(delta)
    return "+0" if text in ("-0", "+0", "-0.0", "+0.0") and not digits else text


def headline(snap: Optional[Dict[str, Any]]) -> str:
    """一塊 snapshot → 沒有比較對象時的那一行（絕對值）。"""
    if not snap:
        return ""
    parts: List[str] = []
    acc = _finite(snap.get("accuracy"))
    if acc is not None and int(snap.get("n_evaluated") or 0):
        parts.append("accuracy %.0f%%" % (100.0 * acc))
        parts.append("missed %d" % int(snap.get("missed") or 0))
        parts.append("false alarm %d" % int(snap.get("false_alarm") or 0))
    else:
        parts.append("%d defects" % int(snap.get("n") or 0))
        parts.append("flagged %d" % int(snap.get("flagged") or 0))
    return " · ".join(parts)


def diff_line(now: Optional[Dict[str, Any]],
              base: Optional[Dict[str, Any]]) -> str:
    """兩塊 snapshot → ``accuracy 78% (+6) · missed 3 (-2) · false alarm 11 (+4)``。

    規則有兩條，兩條都是「不要說謊」的直接後果：

    * **只有兩邊都有的數字才給括號**。baseline 是在沒有答案卷的時候釘的、
      現在才標了 20 顆 —— 那一格顯示絕對值，不顯示一個拿 0 當基準算出來的
      ``(+78)``。
    * **顆數不一樣的時候要講**。First 50 跟 First 200 的正確率放在一起比，
      差值有數字而且完全沒有意義；所以最後接一句 ``(50 → 200 defects)``。
    """
    if not now:
        return ""
    if not base:
        return headline(now)

    parts: List[str] = []
    acc, base_acc = _finite(now.get("accuracy")), _finite(base.get("accuracy"))
    scored = int(now.get("n_evaluated") or 0)
    if acc is not None and scored:
        text = "accuracy %.0f%%" % (100.0 * acc)
        if base_acc is not None and int(base.get("n_evaluated") or 0):
            text += " (%s)" % _signed(100.0 * (acc - base_acc))
        parts.append(text)
        for key, word in (("missed", "missed"), ("false_alarm", "false alarm")):
            value = int(now.get(key) or 0)
            text = "%s %d" % (word, value)
            if base.get(key) is not None and base_acc is not None:
                text += " (%s)" % _signed(value - int(base.get(key) or 0))
            parts.append(text)
    else:
        # 沒有答案卷：能講的是顆數與「判進非 0 bin 的有幾顆」。
        flagged = int(now.get("flagged") or 0)
        parts.append("%d defects" % int(now.get("n") or 0))
        parts.append("flagged %d (%s)"
                     % (flagged, _signed(flagged - int(base.get("flagged") or 0))))

    n_now, n_base = int(now.get("n") or 0), int(base.get("n") or 0)
    if n_now != n_base:
        parts.append("%d → %d defects, so the numbers are not the same batch"
                     % (n_base, n_now))
    return " · ".join(parts)


class BaselineStore:
    """釘住的那一塊住哪裡。

    是一個**類別而不是四支模組函式**，因為測試要餵一個自己的 ``QSettings``
    （寫進真的使用者設定的測試會讓「上一次手動跑 GUI 釘過什麼」漏進下一次的
    斷言 —— `studio._load_sizes` 那一段記著同一個教訓）。
    """

    def __init__(self, settings: Any = None, key: str = SETTINGS_KEY) -> None:
        self._settings = settings
        self._key = str(key)
        #: 沒有 QSettings（測試、或設定讀不動）時的退路。
        self._memory: Optional[str] = None

    def _store(self) -> Any:
        if self._settings is None:
            try:
                from .welcome import app_settings
                self._settings = app_settings()
            except Exception:  # 設定讀不到不准擋路
                self._settings = False     # 記住失敗，不要每次都重試
        return self._settings or None

    def save(self, snap: Optional[Dict[str, Any]]) -> None:
        raw = json.dumps(dict(snap)) if snap else ""
        self._memory = raw or None
        st = self._store()
        if st is None:
            return
        try:
            st.setValue(self._key, raw)
            st.sync()
        except Exception:  # 存不進去不准擋路
            swallowed("baseline.save")

    def load(self) -> Optional[Dict[str, Any]]:
        raw = self._memory
        st = self._store()
        if st is not None:
            try:
                raw = str(st.value(self._key, "") or "") or raw
            except Exception:
                swallowed("baseline.load")
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) and data else None

    def clear(self) -> None:
        self.save(None)


def _running_under_pytest() -> bool:
    """現在是不是在跑測試。

    ⚠ 這是 `studio._running_under_pytest` 的第二份，而那**不是**抄漏了：
    這個模組不能 import `studio`（`studio` import 它）。兩行、判準一樣，
    改一份要記得改另一份 —— 而症狀是「測試又開始碰使用者真正的設定」。
    """
    import os
    import sys
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules


def default_store() -> BaselineStore:
    """Studio 用的那一個（讀 `welcome.app_settings`，第一次用到才建）。

    **測試裡它只活在記憶體。** 開一個 `ResultsWindow` 就去讀開發者真正的
    QSettings 的話，他上一次手動跑 GUI 釘過的那一批數字會漏進斷言裡 ——
    `studio._load_sizes` 對欄寬記著的是同一個教訓。要驗持久化的測試自己
    餵一個 `QSettings`（`BaselineStore(QSettings(路徑, IniFormat))`）。
    """
    return BaselineStore(settings=False if _running_under_pytest() else None)


# --------------------------------------------------------------------------- #
# 畫出來（一條細長的橫條，住在 Results 視窗判定段的下面）
# --------------------------------------------------------------------------- #
class BaselineBar(QWidget):
    """``[ accuracy 78% (+6) · missed 3 (-2) ]   [ Pin as baseline ]``

    **一條橫條而不是一個對話框**：它要回答的是「剛才那一下」，而那個問題在
    使用者按下 Run 的一秒後就過期了 —— 一個要點開的東西答不到它。

    這個 widget 自己不算任何數字（:func:`diff_line` 才算），也不自己存
    （:class:`BaselineStore` 才存）。它只有兩顆訊號，宿主接了決定要不要做。
    """

    pin_requested = Signal()
    unpin_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._run: Optional[Dict[str, Any]] = None
        self._base: Optional[Dict[str, Any]] = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 2, 10, 4)
        lay.setSpacing(8)
        self.label = QLabel("", self)
        self.label.setObjectName("paramHint")
        self.label.setWordWrap(False)
        self.label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.label, 1)

        self.btn_pin = QToolButton(self)
        self.btn_pin.setText("Pin as baseline")
        self.btn_pin.setCursor(Qt.PointingHandCursor)
        self.btn_pin.clicked.connect(self._on_pin)
        lay.addWidget(self.btn_pin)

        self.btn_clear = QToolButton(self)
        self.btn_clear.setText("Unpin")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.clicked.connect(self.unpin_requested)
        lay.addWidget(self.btn_clear)
        self.refresh()

    # ---- 對外 -------------------------------------------------------------
    def set_run(self, snap: Optional[Dict[str, Any]]) -> None:
        """這一次跑出來的那一塊（``None`` = 還沒跑過）。"""
        self._run = dict(snap) if snap else None
        self.refresh()

    def set_baseline(self, snap: Optional[Dict[str, Any]]) -> None:
        self._base = dict(snap) if snap else None
        self.refresh()

    def run(self) -> Optional[Dict[str, Any]]:
        """現在畫面上這一次跑的那一塊（``None`` = 還沒跑過）。"""
        return dict(self._run) if self._run else None

    def baseline(self) -> Optional[Dict[str, Any]]:
        return dict(self._base) if self._base else None

    def text(self) -> str:
        return self.label.text()

    def refresh(self) -> None:
        """三種狀態，三句不同的話（**沒有一種是空白**）。"""
        pinned = bool(self._base)
        self.btn_clear.setVisible(pinned)
        self.btn_pin.setEnabled(bool(self._run))
        self.btn_pin.setText("Pin this run instead" if pinned
                             else "Pin as baseline")
        self.btn_pin.setToolTip(
            "Remember this run's numbers, so the next run can say how much "
            "each change moved them."
            if self._run else "Run a trial first - there is nothing to pin yet.")
        if not self._run:
            self.label.setText(
                "Baseline: %s" % (headline(self._base) if pinned
                                  else "nothing pinned yet"))
            return
        if not pinned:
            self.label.setText(
                "%s — pin it and the next run says how much it moved."
                % headline(self._run))
            return
        # **三樣東西一起在畫面上**：這一次、差值、以及基準那一次的絕對值。
        # 只給差值的話，使用者知道「好了 6 個百分點」卻不知道「從幾變成幾」——
        # 而他下一個動作（要不要收手）取決於後者。
        self.label.setText("%s      ← baseline: %s"
                           % (diff_line(self._run, self._base),
                              headline(self._base)))

    def _on_pin(self) -> None:
        if self._run:
            self.pin_requested.emit()

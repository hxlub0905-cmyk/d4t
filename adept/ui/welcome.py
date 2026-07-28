# ADEPT Studio 首次開啟導覽 — authored 2026-07-28 (M6-2).
"""``WelcomeDialog`` 與 ``RecipeLibraryDialog`` —— 產品的「上車處」。

為什麼要有這個檔（推廣鐵則）
----------------------------
ADEPT 的存在意義是讓**不會寫 code 的製程／設備工程師**把一個想法變成評分
演算法。可是第一次打開 Studio 看到的是一條空流程 —— 東西全都在，就是沒有
入口。這支對話框的唯一任務：**讓一個從沒用過的人，在大約一分鐘內看到一批
真的算出分數的結果**。

所以它不是一面文字牆，而是三顆「按下去真的會發生事情」的按鈕：

1. **用範例資料試一次** —— 產一批合成資料 → 載入 → 載入 die-to-die 範本 →
   試跑，最後畫面上是有分數分佈的直方圖與一整牆縮圖。**全產品最重要的一顆鈕。**
2. **開啟我自己的 KLARF** —— 關掉自己，交給 Studio 的「開啟 KLARF…」。
3. **看範例 recipe** —— 打開 :class:`RecipeLibraryDialog`（範例 recipe 庫）。

**對話框不自己驅動 app**：三顆鈕都只 emit 訊號，真正的動作由
:class:`~adept.ui.studio.StudioWindow` 執行。這樣對話框可以單獨測，
Studio 也可以在沒有對話框的情況下跑同一段流程（``run_demo``）。

「不再顯示」寫進 ``QSettings``（org ``ADEPT`` / app ``Studio``，鍵
``welcome/skip``）。刻意用 ``IniFormat`` + ``UserScope``：測試只要呼叫
``QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmpdir)``
就能把整組設定導到暫存目錄，不會弄髒開發機。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import SEG_LABELS, TOKENS, seg_hex

__all__ = [
    "WelcomeDialog", "RecipeLibraryDialog",
    "SETTINGS_ORG", "SETTINGS_APP", "SKIP_WELCOME_KEY",
    "app_settings", "welcome_disabled", "set_welcome_disabled",
    "RECIPES_DIR", "DOCS_DIR", "list_recipe_files", "read_recipe_info",
    "quick_reference_pdf",
]

#: repo 根目錄（本檔在 ``<repo>/adept/ui/welcome.py``）。
_REPO = Path(__file__).resolve().parents[2]

#: 範例 recipe 庫的位置（``RecipeLibraryDialog`` 的預設來源）。
RECIPES_DIR = _REPO / "examples" / "recipes"

#: 快速參考卡 PDF 找這個資料夾。
DOCS_DIR = _REPO / "docs"

#: QSettings 座標（三處共用：本檔、Studio、測試）。
SETTINGS_ORG = "ADEPT"
SETTINGS_APP = "Studio"
SKIP_WELCOME_KEY = "welcome/skip"

#: 三段式的一句話說明（和 CLAUDE.md §2 的心智模型逐字對應）。
_SEG_LINES = (
    ("image", "把圖變乾淨、變可比"),
    ("algo", "從圖量出數字（量化證據）"),
    ("adc", "分數 → bin → 寫回 KLARF"),
)

_INTRO = (
    "ADEPT 讀進機台的 patch／Review SEM 影像與 KLARF，讓你用一張張「步驟卡片」"
    "組成一條流程：對每一顆 defect 算出一個分數、用門檻分 bin，再把結果寫回 KLARF。"
    "\n不用寫程式 —— 你只要決定「什麼樣子叫做真缺陷」，流程負責把它算出來。"
)

_FOOTER_HINT = "第一次用？直接按左邊那顆 —— 大約一分鐘就會看到一批算好分數的結果。"


# --------------------------------------------------------------------------- #
# QSettings 小工具
# --------------------------------------------------------------------------- #
def app_settings() -> QSettings:
    """Studio 的 ``QSettings``（org ``ADEPT`` / app ``Studio``、INI 格式）。"""
    return QSettings(QSettings.IniFormat, QSettings.UserScope,
                     SETTINGS_ORG, SETTINGS_APP)


def welcome_disabled() -> bool:
    """使用者是否勾過「不再顯示」。讀不到／格式怪 → 一律回 False（照樣顯示）。"""
    value = app_settings().value(SKIP_WELCOME_KEY, False)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def set_welcome_disabled(disabled: bool) -> None:
    """寫入「不再顯示」旗標（立刻 sync，關窗當掉也不會掉設定）。"""
    st = app_settings()
    st.setValue(SKIP_WELCOME_KEY, bool(disabled))
    st.sync()


# --------------------------------------------------------------------------- #
# recipe 庫的讀取（全部從 JSON 讀，一個字都不寫死）
# --------------------------------------------------------------------------- #
def list_recipe_files(directory: Any = None) -> List[Path]:
    """``examples/recipes/*.json`` 依檔名排序（資料夾不在就回空清單）。"""
    d = Path(str(directory)) if directory is not None else RECIPES_DIR
    if not d.is_dir():
        return []
    return sorted(d.glob("*.json"))


def read_recipe_info(path: Any) -> Dict[str, Any]:
    """讀一份 recipe JSON → 給庫對話框顯示用的摘要（**不做驗證、不炸**）。

    壞掉的檔案不會讓整個庫開不起來：回傳的 dict 會帶 ``error``，
    對話框把它顯示成一列紅字，其他 recipe 照常可用（鐵則 7 的精神）。
    """
    p = Path(str(path))
    info: Dict[str, Any] = {
        "path": str(p), "file": p.name, "recipe_id": p.stem,
        "description": "", "routes": [], "route_steps": {},
        "n_steps": 0, "expr": "", "threshold": None, "author": "",
        "version": None, "error": "",
    }
    try:
        with open(str(p), "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("最外層不是一個 JSON 物件")
    except Exception as e:                       # noqa: BLE001 — UI 邊界
        info["error"] = "%s: %s" % (type(e).__name__, e)
        return info

    info["recipe_id"] = str(d.get("recipe_id") or p.stem)
    info["description"] = str(d.get("description") or "")
    info["author"] = str(d.get("author") or "")
    info["version"] = d.get("version")

    routes = d.get("routes") or {}
    if isinstance(routes, dict):
        info["routes"] = [str(k) for k in routes]
        info["route_steps"] = {str(k): len(list(v or [])) for k, v in routes.items()}
    info["n_steps"] = len(dict(d.get("nodes") or {}))

    score = d.get("score") or {}
    if isinstance(score, dict):
        info["expr"] = str(score.get("expr") or "")
        try:
            info["threshold"] = float(score.get("threshold"))
        except (TypeError, ValueError):
            info["threshold"] = None
    return info


def quick_reference_pdf(directory: Any = None) -> Optional[Path]:
    """``docs/`` 裡的快速參考卡 PDF；找不到回 ``None``（呼叫端必須擋）。

    名字含 quick / reference / 參考 / 卡 的排前面，其餘的 PDF 也接受
    （廠內可能自己換檔名）。
    """
    d = Path(str(directory)) if directory is not None else DOCS_DIR
    if not d.is_dir():
        return None
    pdfs = sorted(d.glob("*.pdf"))
    if not pdfs:
        return None
    for p in pdfs:
        low = p.name.lower()
        if any(k in low for k in ("quick", "reference", "參考", "卡")):
            return p
    return pdfs[0]


# --------------------------------------------------------------------------- #
# 三段式視覺（影像 → 算法 → ADC 判定）
# --------------------------------------------------------------------------- #
class _SegmentStrip(QWidget):
    """一條「影像 → 算法 → ADC 判定」的彩色說明帶（不用任何圖檔）。

    顏色直接取 :func:`~adept.ui.theme.seg_hex`，和卡片庫區塊標題、Pipeline
    卡片左側色條是同一組 token —— 使用者在導覽看到的橙色，等一下在畫面上
    看到的也是同一個橙色。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.cards: List[QFrame] = []
        for i, (cat, line) in enumerate(_SEG_LINES):
            if i:
                arrow = QLabel("▶", self)
                arrow.setStyleSheet("color:%s; font-size:15px;"
                                    % TOKENS["text_hint"])
                lay.addWidget(arrow, 0)
            lay.addWidget(self._card(cat, line), 1)

    def _card(self, category: str, line: str) -> QFrame:
        fg, bg = seg_hex(category), seg_hex(category, bg=True)
        card = QFrame(self)
        card.setObjectName("segCard")
        card.setStyleSheet(
            "QFrame#segCard { background:%s; border:1px solid %s;"
            " border-radius:8px; }" % (bg, fg))
        card.setProperty("category", category)
        card.setMinimumHeight(58)
        box = QVBoxLayout(card)
        box.setContentsMargins(10, 7, 10, 7)
        box.setSpacing(2)

        title = QLabel(SEG_LABELS[category], card)
        title.setStyleSheet("color:%s; font-weight:700; font-size:12px;" % fg)
        body = QLabel(line, card)
        body.setWordWrap(True)
        body.setStyleSheet("color:%s; font-size:11px;" % TOKENS["text_secondary"])
        box.addWidget(title)
        box.addWidget(body)
        self.cards.append(card)
        return card


# --------------------------------------------------------------------------- #
# 首次開啟導覽
# --------------------------------------------------------------------------- #
class WelcomeDialog(QDialog):
    """首次開啟（與工具列「說明」）看到的導覽。

    三顆動作鈕**只發訊號**，實際動作由 Studio 做：

    - ``demo_requested()``       → ``StudioWindow.run_demo()``
    - ``open_klarf_requested()`` → 「開啟 KLARF…」
    - ``library_requested()``    → :class:`RecipeLibraryDialog`
    - ``quickref_requested(str)``→ 已開啟的 PDF 路徑（沒有 PDF 時鈕是停用的）

    測試友善：:meth:`click_demo` / :meth:`click_open` / :meth:`click_library` /
    :meth:`set_dont_show_again` 都不需要真的滑鼠事件。
    """

    demo_requested = Signal()
    open_klarf_requested = Signal()
    library_requested = Signal()
    quickref_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("歡迎使用 ADEPT")
        self.setModal(False)          # 永遠不擋住主視窗（測試也才不會卡住）
        self.setMinimumWidth(620)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        title = QLabel("ADEPT —— 用卡片組出你自己的缺陷判定流程", self)
        title.setObjectName("paramTitle")
        root.addWidget(title)

        intro = QLabel(_INTRO, self)
        intro.setWordWrap(True)
        intro.setStyleSheet("color:%s;" % TOKENS["text_secondary"])
        self.intro_label = intro
        root.addWidget(intro)

        self.segments = _SegmentStrip(self)
        root.addWidget(self.segments)

        root.addWidget(self._separator())

        # ---- 三顆真的會做事的鈕 ------------------------------------------
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_demo = QPushButton("用範例資料試一次", self)
        self.btn_demo.setObjectName("primary")
        self.btn_demo.setCursor(Qt.PointingHandCursor)
        self.btn_demo.setToolTip(
            "產一批合成資料 → 載入 → 套用 die-to-die 範本 → 試跑，"
            "直接看到分數分佈與縮圖牆（不會動到你的任何檔案）")
        self.btn_demo.setMinimumHeight(34)
        self.btn_demo.clicked.connect(self.click_demo)

        self.btn_open = QPushButton("開啟我自己的 KLARF", self)
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.setToolTip("關掉這個視窗，直接去選一份 KLARF 檔")
        self.btn_open.setMinimumHeight(34)
        self.btn_open.clicked.connect(self.click_open)

        self.btn_library = QPushButton("看範例 recipe", self)
        self.btn_library.setCursor(Qt.PointingHandCursor)
        self.btn_library.setToolTip("打開範例 recipe 庫：每一份都是可以直接跑的完整流程")
        self.btn_library.setMinimumHeight(34)
        self.btn_library.clicked.connect(self.click_library)

        for b in (self.btn_demo, self.btn_open, self.btn_library):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            row.addWidget(b, 1)
        root.addLayout(row)

        hint = QLabel(_FOOTER_HINT, self)
        hint.setObjectName("paramHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addWidget(self._separator())

        # ---- 底列：不再顯示 / 快速參考卡 / 關閉 ----------------------------
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.chk_dont_show = QCheckBox("不再顯示", self)
        self.chk_dont_show.setToolTip(
            "之後開啟就不會再跳出這個視窗；隨時可以從工具列的「說明」再打開")
        self.chk_dont_show.setChecked(welcome_disabled())
        self.chk_dont_show.toggled.connect(self._on_dont_show_toggled)
        bottom.addWidget(self.chk_dont_show)
        bottom.addStretch(1)

        self.quickref_path = quick_reference_pdf()
        self.btn_quickref = QPushButton("快速參考卡", self)
        self.btn_quickref.setProperty("variant", "ghost")
        self.btn_quickref.setCursor(Qt.PointingHandCursor)
        self.btn_quickref.setStyleSheet(
            "QPushButton { background:transparent; border:0; color:%s;"
            " text-decoration:underline; padding:4px 8px; }"
            "QPushButton:disabled { color:%s; text-decoration:none; }"
            % (TOKENS["accent_active"], TOKENS["text_disabled"]))
        if self.quickref_path is None:
            self.btn_quickref.setEnabled(False)
            self.btn_quickref.setToolTip(
                "docs/ 裡還沒有快速參考卡 PDF —— 這一版的離線安裝包會附上。")
        else:
            self.btn_quickref.setToolTip("用系統預設的 PDF 閱讀器開啟：%s"
                                         % self.quickref_path.name)
        self.btn_quickref.clicked.connect(self.open_quick_reference)
        bottom.addWidget(self.btn_quickref)

        self.btn_close = QPushButton("先自己看看", self)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setToolTip("關掉導覽，直接進 Studio")
        self.btn_close.clicked.connect(self.close)
        bottom.addWidget(self.btn_close)
        root.addLayout(bottom)

    # ---- 小零件 ----------------------------------------------------------
    def _separator(self) -> QFrame:
        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet("background:%s; border:0;" % TOKENS["border_default"])
        return line

    # ---- 動作（每一顆都可以在測試裡直接呼叫）------------------------------
    def click_demo(self) -> None:
        """「用範例資料試一次」：先關掉自己，讓使用者看得到結果。"""
        self.close()
        self.demo_requested.emit()

    def click_open(self) -> None:
        """「開啟我自己的 KLARF」：關掉自己，交給 Studio 的開檔動作。"""
        self.close()
        self.open_klarf_requested.emit()

    def click_library(self) -> None:
        """「看範例 recipe」：打開 recipe 庫（導覽留著，方便再按別的鈕）。"""
        self.library_requested.emit()

    def set_dont_show_again(self, checked: bool) -> None:
        """程式化地勾／取消「不再顯示」（會寫進 QSettings）。"""
        self.chk_dont_show.setChecked(bool(checked))

    def _on_dont_show_toggled(self, checked: bool) -> None:
        set_welcome_disabled(bool(checked))

    def open_quick_reference(self) -> bool:
        """開啟快速參考卡 PDF；檔案不在就什麼都不做並回 ``False``。"""
        path = self.quickref_path
        if path is None or not os.path.isfile(str(path)):
            return False
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.quickref_requested.emit(str(path))
        return True


# --------------------------------------------------------------------------- #
# 範例 recipe 庫
# --------------------------------------------------------------------------- #
class RecipeLibraryDialog(QDialog):
    """範例 recipe 庫：左邊列清單、右邊看細節，雙擊或按「載入」就套用。

    清單上顯示的每一個字（名稱、說明、route、步驟數、分數表達式）**都是從
    JSON 讀出來的**，沒有任何一份 recipe 被寫死在程式裡 —— 之後往
    ``examples/recipes/`` 丟一份新的 JSON，這裡就會自己多一列。

    訊號：``recipe_chosen(path)``（雙擊或按「載入」）。
    """

    recipe_chosen = Signal(str)

    def __init__(self, directory: Any = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("範例 recipe 庫")
        self.setModal(False)
        self.setMinimumSize(720, 420)
        self.directory = Path(str(directory)) if directory is not None else RECIPES_DIR

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        head = QLabel("挑一份最接近你站點情況的，載進來再改參數 —— "
                      "不要從空白的流程開始。", self)
        head.setWordWrap(True)
        head.setStyleSheet("color:%s;" % TOKENS["text_secondary"])
        root.addWidget(head)

        body = QHBoxLayout()
        body.setSpacing(10)

        self.list = QListWidget(self)
        self.list.setMinimumWidth(280)
        self.list.setAlternatingRowColors(True)
        self.list.currentRowChanged.connect(self._on_row_changed)
        self.list.itemDoubleClicked.connect(lambda *_: self.load_selected())
        body.addWidget(self.list, 2)

        self.detail = QLabel("", self)
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail.setStyleSheet(
            "background:%s; border:1px solid %s; border-radius:8px; padding:10px;"
            % (TOKENS["bg_surface"], TOKENS["border_default"]))
        body.addWidget(self.detail, 3)
        root.addLayout(body, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.path_label = QLabel("", self)
        self.path_label.setObjectName("paramHint")
        bottom.addWidget(self.path_label, 1)
        self.btn_load = QPushButton("載入", self)
        self.btn_load.setObjectName("primary")
        self.btn_load.setCursor(Qt.PointingHandCursor)
        self.btn_load.setToolTip("把這份 recipe 載進 Studio 的流程面板")
        self.btn_load.clicked.connect(self.load_selected)
        bottom.addWidget(self.btn_load)
        self.btn_close = QPushButton("關閉", self)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        bottom.addWidget(self.btn_close)
        root.addLayout(bottom)

        self._entries: List[Dict[str, Any]] = []
        self.reload()

    # ---- 資料 -------------------------------------------------------------
    def reload(self) -> int:
        """重讀資料夾並重建清單；回傳有幾份 recipe。"""
        self._entries = [read_recipe_info(p) for p in list_recipe_files(self.directory)]
        self.list.clear()
        for info in self._entries:
            item = QListWidgetItem(self._item_text(info))
            item.setData(Qt.UserRole, info["path"])
            item.setToolTip(info["description"] or info["error"] or info["file"])
            if info["error"]:
                item.setToolTip("這份檔案讀不開：%s" % info["error"])
            self.list.addItem(item)
        if self._entries:
            self.list.setCurrentRow(0)
        else:
            self.detail.setText("`examples/recipes/` 裡還沒有任何 recipe JSON。")
            self.btn_load.setEnabled(False)
        return len(self._entries)

    def entries(self) -> List[Dict[str, Any]]:
        """目前列出的 recipe 摘要（測試用；順序與清單一致）。"""
        return list(self._entries)

    def count(self) -> int:
        return self.list.count()

    def item_text(self, index: int) -> str:
        item = self.list.item(int(index))
        return "" if item is None else str(item.text())

    def path_at(self, index: int) -> str:
        item = self.list.item(int(index))
        return "" if item is None else str(item.data(Qt.UserRole))

    def select(self, index: int) -> bool:
        """選第 ``index`` 列（超出範圍回 False）。"""
        if not (0 <= int(index) < self.list.count()):
            return False
        self.list.setCurrentRow(int(index))
        return True

    def selected_path(self) -> Optional[str]:
        row = int(self.list.currentRow())
        if row < 0:
            return None
        return self.path_at(row) or None

    # ---- 顯示 -------------------------------------------------------------
    @staticmethod
    def _item_text(info: Dict[str, Any]) -> str:
        if info["error"]:
            return "%s\n（讀不開：%s）" % (info["file"], info["error"])
        routes = "、".join(info["routes"]) or "（沒有 route）"
        return "%s\nroute：%s · %d 個步驟" % (
            info["recipe_id"], routes, int(info["n_steps"]))

    def _on_row_changed(self, row: int) -> None:
        if not (0 <= int(row) < len(self._entries)):
            self.detail.setText("")
            self.path_label.setText("")
            self.btn_load.setEnabled(False)
            return
        info = self._entries[int(row)]
        self.btn_load.setEnabled(not info["error"])
        self.path_label.setText(info["path"])
        self.detail.setText(self._detail_text(info))

    @staticmethod
    def _detail_text(info: Dict[str, Any]) -> str:
        if info["error"]:
            return "這份檔案讀不開：\n%s" % info["error"]
        lines = [info["description"] or "（這份 recipe 沒有寫說明）", ""]
        for route in info["routes"]:
            lines.append("• route %s：%d 個步驟"
                         % (route, int(info["route_steps"].get(route, 0))))
        lines.append("")
        lines.append("分數 = %s" % (info["expr"] or "（沒有寫分數表達式）"))
        if info["threshold"] is not None:
            lines.append("門檻 = %g（分數 ≥ 門檻 → bin 1）" % float(info["threshold"]))
        if info["author"]:
            lines.append("作者：%s" % info["author"])
        return "\n".join(lines)

    # ---- 動作 -------------------------------------------------------------
    def load_selected(self) -> Optional[str]:
        """發出 ``recipe_chosen(path)`` 並關窗；沒選到／檔案壞掉回 ``None``。"""
        row = self.list.currentRow()
        if not (0 <= row < len(self._entries)):
            return None
        info = self._entries[row]
        if info["error"]:
            return None
        path = str(info["path"])
        self.recipe_chosen.emit(path)
        self.close()
        return path

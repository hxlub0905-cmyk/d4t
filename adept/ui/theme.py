# ADEPT Studio theme — authored 2026-07-28 (M3), repainted 2026-07-28 (F7-2).
# Originally vendored from cell-period-estimator/…/ui/theme.py（GLAS 暖色 token
# 系統 + apply_theme QSS）。F7-2 換掉了整組**顏色值**，但 token 的**鍵名一個都沒改**
#   —— QSS 與所有自繪 widget 都是照鍵名取色，所以換膚不需要動任何呼叫端。
"""ADEPT Studio 佈景主題 —— 設計 token 的唯一真相來源。

``TOKENS`` 同時餵給 QSS（標準 widget）與自繪 widget（直方圖、節點卡、色條），
顏色永遠不會兩邊走鐘。

F7-2：為什麼整組換掉
--------------------
舊配色是暖奶油底（``#f7f4ef``）+ 琥珀 accent（``#f29f4b``），而且三段式用
**填滿的彩色底塊**當區塊標題。暖色 + 高飽和 + 大色塊三個加起來，使用者的
評語是「太像玩具」。

新的目標是 n8n / KLIP 的語言：

* **中性灰階** —— 大面積不帶色相，眼睛不會被背景搶走
* **全平面** —— 沒有陰影、沒有漸層（n8n 2.0 也是刻意拿掉 3D 陰影的）
* **顏色只表達語意** —— 段落色、狀態色、accent；裝飾一律不用色
* **小圓角、細邊框、一致的 4/8px 間距**

亮色與暗色
----------
``PALETTES`` 有 ``"light"`` / ``"dark"`` 兩組，鍵名完全相同。
:func:`set_theme` 就地更新 ``TOKENS``（**不是換掉物件**）——
因為各模組都是 ``from .theme import TOKENS`` 之後在建構式裡取值，
就地更新才能讓已經 import 過的模組跟著變。

三段式 segment 色（master plan §5）：

===========  ==========  ==========  ==========================================
段           前景 token  底色 token  用在哪
===========  ==========  ==========  ==========================================
影像 image   seg_image   seg_image_bg  Library 區塊圓點、Pipeline 卡片左側色條
算法 algo    seg_algo    seg_algo_bg   同上 + 直方圖長條
ADC  adc     seg_adc     seg_adc_bg    同上 + Score/Bin 尾卡
===========  ==========  ==========  ==========================================

Qt-QSS 限制備忘：QSS 沒有 ``text-transform`` / ``letter-spacing``；區塊標題
一律在程式碼裡處理大小寫，顏色與字重才交給 QSS。

本模組不在 import 時碰 Qt（``TOKENS`` 可被 headless 測試直接讀），
``QColor`` 一律在函式內 lazy import。
"""

from __future__ import annotations

from string import Template
from typing import Any, Dict

__all__ = [
    "TOKENS", "PALETTES", "THEMES", "DEFAULT_THEME", "current_theme",
    "set_theme", "SEG_LABELS", "seg_hex", "seg_color", "seg_bg",
    "build_stylesheet", "apply_theme",
]

# --------------------------------------------------------------------------- #
# Design tokens
# --------------------------------------------------------------------------- #
#: 亮色（預設）。中性灰階 + 一個克制的藍當 accent。
_LIGHT: Dict[str, Any] = {
    # -- backgrounds (low -> high elevation) -------------------------------
    "bg_page": "#f4f5f7",
    "bg_panel": "#fafbfc",
    "bg_surface": "#ffffff",
    "bg_elevated": "#f7f8fa",
    "bg_input": "#ffffff",
    "side_panel": "#fafbfc",
    "toolbar": "#ffffff",
    "statusbar": "#f7f8fa",
    # -- borders ------------------------------------------------------------
    "border_default": "#e3e6eb",
    "border_input": "#cbd1d9",
    "border_hover": "#9aa3ae",
    "border_focus": "#3574d6",
    # -- text ---------------------------------------------------------------
    "text_primary": "#1f2430",
    "text_secondary": "#5b6472",
    "text_hint": "#79828f",
    "text_disabled": "#aeb5bf",
    # -- accent (restrained blue; KLIP 的視覺語言) ---------------------------
    "accent": "#3574d6",
    "accent_hover": "#4a86e2",
    "accent_active": "#2b5eb0",
    "accent_bg": "#eaf1fc",
    "accent_border": "#c2d6f2",
    # -- selection / hover --------------------------------------------------
    "selection": "#d5e3f8",
    "hover_warm": "#f0f2f5",          # 鍵名保留（歷史），已不是暖色
    "hover_warm_strong": "#e6eaf0",
    "focus_bg": "#ffffff",
    # -- semantic -----------------------------------------------------------
    "success": "#3f9d6b",
    "success_bg": "#eaf6f0",
    "success_border": "#b6ddc7",
    "success_text": "#2f7a52",
    "danger": "#d05a4c",
    "danger_bg": "#fdeeeb",
    "danger_border": "#f0bdb5",
    "danger_text": "#a83f33",
    "warning": "#c2871f",
    "min_accent": "#c2731f",
    "min_accent_bg": "#fdf3e6",
    "min_accent_border": "#eed3ad",
    "min_accent_text": "#8f5615",
    "max_accent": "#3574d6",
    "max_accent_bg": "#eaf1fc",
    "max_accent_border": "#c2d6f2",
    "max_accent_text": "#2b5eb0",
    # -- ADEPT 三段式 segment 色（去飽和，只當色條/圓點用）-------------------
    "seg_image": "#4a7ba7",
    "seg_algo": "#b0722f",
    "seg_adc": "#7a68a6",
    "seg_image_bg": "#eaf0f6",
    "seg_algo_bg": "#f8f0e5",
    "seg_adc_bg": "#f0edf6",
    "seg_disabled": "#c2c7ce",
    "seg_disabled_bg": "#f0f1f3",
    # -- 判定 chip（good / bad / neutral）------------------------------------
    "chip_good_bg": "#eaf6f0",
    "chip_good_text": "#2f7a52",
    "chip_good_border": "#b6ddc7",
    "chip_bad_bg": "#fdeeeb",
    "chip_bad_text": "#a83f33",
    "chip_bad_border": "#f0bdb5",
    "chip_neutral_bg": "#f0f2f5",
    "chip_neutral_text": "#5b6472",
    "chip_neutral_border": "#e3e6eb",
    # -- tooltip (inverted) -------------------------------------------------
    "tooltip_bg": "#2b303b",
    "tooltip_text": "#f4f5f7",
    "tooltip_border": "#1f2430",
    # -- lists / scrollbars / disabled --------------------------------------
    "list_bg": "#ffffff",
    "row_alt": "#fafbfc",
    "scroll_track": "transparent",
    "scroll_thumb": "#cbd1d9",
    "scroll_thumb_hover": "#aeb5bf",
    "disabled_bg": "#f4f5f7",
    "disabled_text": "#aeb5bf",
    "tab_inactive": "transparent",
    # -- section header tiers ------------------------------------------------
    "tier1_bg": "transparent",
    "tier1_text": "#79828f",
    # -- canvas (F7-6 節點畫布) ----------------------------------------------
    "canvas_bg": "#f0f1f4",
    "canvas_grid": "#e0e3e8",
    "canvas_edge": "#9aa3ae",
    "canvas_edge_active": "#3574d6",
    # -- typography ----------------------------------------------------------
    "font_stack": ("'Segoe UI','PingFang TC','Microsoft JhengHei',"
                   "'Helvetica Neue',Arial,sans-serif"),
    "mono_stack": "'Consolas','Courier New',monospace",
}

#: 暗色。n8n 的畫布是深中性色，不是純黑（純黑對比太硬，看久了刺眼）。
_DARK: Dict[str, Any] = dict(_LIGHT, **{
    "bg_page": "#191b20",
    "bg_panel": "#1e2127",
    "bg_surface": "#23262d",
    "bg_elevated": "#2a2e36",
    "bg_input": "#1b1e24",
    "side_panel": "#1e2127",
    "toolbar": "#1e2127",
    "statusbar": "#1b1e24",

    "border_default": "#333842",
    "border_input": "#3d434f",
    "border_hover": "#5c6474",
    "border_focus": "#4b8bf5",

    "text_primary": "#e3e6ec",
    "text_secondary": "#a3abb8",
    "text_hint": "#8b93a1",
    "text_disabled": "#5c6474",

    "accent": "#4b8bf5",
    "accent_hover": "#639cf8",
    "accent_active": "#3a76d8",
    "accent_bg": "#1d2a3f",
    "accent_border": "#2f4straight",   # placeholder, fixed below
    "selection": "#2b3d5c",
    "hover_warm": "#282c34",
    "hover_warm_strong": "#30353f",
    "focus_bg": "#1b1e24",

    "success": "#54b382",
    "success_bg": "#1b2b23",
    "success_border": "#2f5a45",
    "success_text": "#6ec79a",
    "danger": "#e07568",
    "danger_bg": "#2e1e1c",
    "danger_border": "#5c3630",
    "danger_text": "#f0958a",
    "warning": "#d8a145",
    "min_accent": "#d8934a",
    "min_accent_bg": "#2b2219",
    "min_accent_border": "#5a4630",
    "min_accent_text": "#e0a86a",
    "max_accent": "#4b8bf5",
    "max_accent_bg": "#1d2a3f",
    "max_accent_border": "#33507d",
    "max_accent_text": "#7aaaf8",

    "seg_image": "#6f9fc8",
    "seg_algo": "#d1994f",
    "seg_adc": "#9e8bc8",
    "seg_image_bg": "#1e2833",
    "seg_algo_bg": "#2c2519",
    "seg_adc_bg": "#26222f",
    "seg_disabled": "#4a505c",
    "seg_disabled_bg": "#22252b",

    "chip_good_bg": "#1b2b23",
    "chip_good_text": "#6ec79a",
    "chip_good_border": "#2f5a45",
    "chip_bad_bg": "#2e1e1c",
    "chip_bad_text": "#f0958a",
    "chip_bad_border": "#5c3630",
    "chip_neutral_bg": "#282c34",
    "chip_neutral_text": "#a3abb8",
    "chip_neutral_border": "#333842",

    "tooltip_bg": "#f4f5f7",
    "tooltip_text": "#1f2430",
    "tooltip_border": "#cbd1d9",

    "list_bg": "#1b1e24",
    "row_alt": "#1f2229",
    "scroll_track": "transparent",
    "scroll_thumb": "#3d434f",
    "scroll_thumb_hover": "#5c6474",
    "disabled_bg": "#22252b",
    "disabled_text": "#5c6474",
    "tab_inactive": "transparent",

    "tier1_bg": "transparent",
    "tier1_text": "#8b93a1",

    "canvas_bg": "#16181d",
    "canvas_grid": "#232730",
    "canvas_edge": "#5c6474",
    "canvas_edge_active": "#4b8bf5",
})
_DARK["accent_border"] = "#33507d"

#: 兩組色盤，鍵名完全一致（測試會逐鍵比對）。
PALETTES: Dict[str, Dict[str, Any]] = {"light": _LIGHT, "dark": _DARK}
THEMES = tuple(PALETTES)
DEFAULT_THEME = "light"

#: **活的** token 字典。``set_theme`` 就地更新它（見模組 docstring）。
TOKENS: Dict[str, Any] = dict(_LIGHT)

_CURRENT = {"name": DEFAULT_THEME}


def current_theme() -> str:
    """目前套用的主題名稱。"""
    return _CURRENT["name"]


def set_theme(name: str) -> str:
    """切換色盤（**就地**更新 ``TOKENS``），回傳實際套用的名稱。

    不認得的名字退回 :data:`DEFAULT_THEME`，不丟例外 —— 主題壞掉不該讓
    使用者連視窗都開不起來（鐵則 7 的精神）。
    """
    key = str(name or "").strip().lower()
    if key not in PALETTES:
        key = DEFAULT_THEME
    TOKENS.clear()
    TOKENS.update(PALETTES[key])
    _CURRENT["name"] = key
    return key


# 分類 -> (前景 token, 底色 token)。未知分類退回中性色。
_SEG_TOKENS = {
    "image": ("seg_image", "seg_image_bg"),
    "algo": ("seg_algo", "seg_algo_bg"),
    "adc": ("seg_adc", "seg_adc_bg"),
}

SEG_LABELS = {
    "image": "Image",
    "algo": "Algorithm",
    "adc": "ADC Decision",
}


def seg_hex(category: str, bg: bool = False) -> str:
    """回傳 segment 顏色的 hex 字串（``bg=True`` 取柔和底色）。純字串、免 Qt。"""
    fg_key, bg_key = _SEG_TOKENS.get(str(category), ("text_secondary", "bg_panel"))
    return TOKENS[bg_key if bg else fg_key]


def seg_color(category: str, bg: bool = False):
    """``"image"``/``"algo"``/``"adc"`` -> ``QColor``（``bg=True`` 取柔和底色）。"""
    from PySide6.QtGui import QColor

    return QColor(seg_hex(category, bg=bg))


def seg_bg(category: str):
    """``seg_color(category, bg=True)`` 的別名（可讀性糖）。"""
    return seg_color(category, bg=True)


# --------------------------------------------------------------------------- #
# QSS
# --------------------------------------------------------------------------- #
_QSS = Template(r"""
* {
    font-family: $font_stack;
    font-size: 13px;
    color: $text_primary;
}

QMainWindow, QWidget, QDialog { background: $bg_page; color: $text_primary; }

/* -- toolbar ---------------------------------------------------------- */
QToolBar {
    background: $toolbar;
    border: 0;
    border-bottom: 1px solid $border_default;
    spacing: 6px;
    padding: 4px 6px;
}
QToolBar QToolButton {
    background: transparent;
    color: $text_secondary;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 6px 12px;
    font-weight: 500;
}
QToolBar QToolButton:hover { background: $hover_warm; color: $text_primary; }
QToolBar QToolButton:pressed { background: $hover_warm_strong; }
QToolBar QToolButton:checked {
    background: $accent_bg; color: $accent_active; border: 1px solid $accent_border;
}
QToolBar QToolButton#primary {
    background: $accent; color: #ffffff; border: 1px solid $accent;
    padding: 6px 16px; font-weight: 600;
}
QToolBar QToolButton#primary:hover { background: $accent_hover; }
QToolBar QToolButton#primary:pressed { background: $accent_active; }
QToolBar QToolButton#primary:disabled {
    background: $disabled_bg; color: $disabled_text; border: 1px solid $border_default;
}
QToolBar::separator { background: $border_default; width: 1px; margin: 5px 6px; }

/* -- status bar ------------------------------------------------------- */
QStatusBar { background: $statusbar; color: $text_secondary;
             border-top: 1px solid $border_default; }
QStatusBar::item { border: 0; }

/* -- group boxes (section cards) -------------------------------------- */
QGroupBox {
    background: $bg_surface;
    border: 1px solid $border_default;
    border-radius: 6px;
    margin-top: 16px;
    padding: 12px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 2px;
    top: 1px;
    padding: 0px 4px;
    background: transparent;
    border: 0;
    color: $tier1_text;
    font-size: 11px;
    font-weight: 700;
}

/* -- push buttons ------------------------------------------------------ */
QPushButton {
    background: $bg_input;
    color: $text_primary;
    border: 1px solid $border_input;
    border-radius: 6px;
    padding: 5px 12px;
    min-height: 18px;
    font-weight: 500;
}
QPushButton:hover { border-color: $border_hover; background: $hover_warm; }
QPushButton:pressed { background: $hover_warm_strong; }
QPushButton:focus { border: 1px solid $border_focus; }
QPushButton:disabled { background: $disabled_bg; color: $disabled_text;
                       border-color: $border_default; }
/* primary action (Run trial / Run all): objectName = "primary" */
QPushButton#primary {
    background: $accent; color: #ffffff; border: 1px solid $accent;
    padding: 6px 18px; font-weight: 600;
}
QPushButton#primary:hover { background: $accent_hover; }
QPushButton#primary:pressed { background: $accent_active; }
QPushButton#primary:disabled {
    background: $disabled_bg; color: $disabled_text; border: 1px solid $border_default;
}
QPushButton[variant="secondary"] {
    background: $bg_input; color: $accent_active; border: 1px solid $accent;
}
QPushButton[variant="secondary"]:hover { background: $accent_bg; }
QPushButton[variant="ghost"] {
    background: transparent; color: $text_secondary; border: 1px solid transparent;
}
QPushButton[variant="ghost"]:hover { background: $hover_warm; color: $text_primary; }
QPushButton[variant="danger"] {
    background: $danger_bg; color: $danger_text; border: 1px solid $danger_border;
}
/* small square buttons on cards (up / down / remove / add) */
QPushButton#cardButton {
    background: transparent; color: $text_secondary;
    border: 1px solid transparent; border-radius: 5px;
    padding: 0px; font-weight: 700; min-height: 20px;
}
QPushButton#cardButton:hover { background: $hover_warm_strong; color: $accent_active;
                               border: 1px solid $accent_border; }
QPushButton#cardButton:disabled { color: $disabled_text; background: transparent; }

/* -- inputs ------------------------------------------------------------ */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: $bg_input;
    color: $text_primary;
    border: 1px solid $border_input;
    border-radius: 5px;
    padding: 2px 6px;
    min-height: 22px;
    selection-background-color: $selection;
    selection-color: $text_primary;
}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {
    border-color: $border_hover;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid $border_focus; background: $focus_bg;
}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
    background: $disabled_bg; color: $disabled_text; border-color: $border_default;
}
QComboBox::drop-down { border: 0; width: 18px; }
QComboBox QAbstractItemView {
    background: $bg_input; border: 1px solid $border_default;
    selection-background-color: $selection; selection-color: $text_primary;
    outline: 0;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 16px; background: $bg_elevated; border-left: 1px solid $border_default;
}

/* -- check boxes ------------------------------------------------------- */
QCheckBox { background: transparent; spacing: 6px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid $border_input; border-radius: 3px; background: $bg_input;
}
QCheckBox::indicator:hover { border-color: $border_hover; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent_active; }
QCheckBox::indicator:disabled { background: $disabled_bg; border-color: $border_default; }
QCheckBox:disabled { color: $disabled_text; }

/* -- labels ------------------------------------------------------------ */
QLabel { background: transparent; color: $text_primary; }
QLabel:disabled { color: $text_disabled; }

/* -- views / lists / tables -------------------------------------------- */
QAbstractItemView {
    background: $list_bg; alternate-background-color: $row_alt;
    border: 1px solid $border_default; border-radius: 6px;
    selection-background-color: $selection; selection-color: $text_primary;
    outline: 0;
}
QListView::item, QTreeView::item { padding: 3px 4px; border-radius: 4px; }
QListView::item:hover, QTreeView::item:hover { background: $hover_warm; }
QTableView { gridline-color: $border_default; }
QTableView::item { padding: 2px 6px; }
QHeaderView { background: $list_bg; }
QHeaderView::section {
    background: $bg_elevated; color: $text_secondary; border: 0;
    border-bottom: 1px solid $border_default; padding: 5px 8px; font-weight: 600;
}

/* -- scroll area ------------------------------------------------------- */
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* -- splitter ---------------------------------------------------------- */
QSplitter { background: $bg_page; }
QSplitter::handle { background: $border_default; }
QSplitter::handle:hover { background: $border_hover; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }

/* -- scrollbars -------------------------------------------------------- */
QScrollBar:vertical { background: $scroll_track; width: 11px; margin: 0; border: 0; }
QScrollBar::handle:vertical { background: $scroll_thumb; border-radius: 5px;
                              min-height: 24px; }
QScrollBar::handle:vertical:hover { background: $scroll_thumb_hover; }
QScrollBar:horizontal { background: $scroll_track; height: 11px; margin: 0; border: 0; }
QScrollBar::handle:horizontal { background: $scroll_thumb; border-radius: 5px;
                                min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: $scroll_thumb_hover; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* -- progress bar ------------------------------------------------------ */
QProgressBar {
    background: $bg_elevated; border: 1px solid $border_default;
    border-radius: 5px; text-align: center; min-height: 14px; color: $text_secondary;
}
QProgressBar::chunk { background: $accent; border-radius: 5px; }

/* -- tabs -------------------------------------------------------------- */
QTabWidget::pane { border: 1px solid $border_default; border-radius: 6px;
                   background: $bg_surface; }
QTabBar::tab { background: $tab_inactive; color: $text_secondary;
               padding: 5px 14px; margin-right: 2px;
               border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: $bg_surface; color: $accent_active;
                        font-weight: 700; }

/* -- menus / tooltips -------------------------------------------------- */
QMenu { background: $bg_surface; border: 1px solid $border_default; padding: 4px; }
QMenu::item { padding: 4px 18px; border-radius: 4px; }
QMenu::item:selected { background: $selection; color: $text_primary; }
QToolTip {
    background: $tooltip_bg; color: $tooltip_text; border: 1px solid $tooltip_border;
    padding: 4px 6px;
}

/* -- Studio-specific object names -------------------------------------- */
QLabel#paramTitle { color: $text_primary; font-size: 14px; font-weight: 700; }
QLabel#paramStepHelp { color: $text_secondary; font-size: 11px; }
QLabel#paramLabel { color: $text_primary; font-weight: 600; }
QLabel#paramHint { color: $text_hint; font-size: 11px; }
QLabel#paramHint[error="true"] { color: $danger_text; font-size: 11px; font-weight: 600; }
QLabel#placeholder { color: $text_disabled; font-size: 12px; }
QLabel#libEmpty { color: $text_disabled; font-size: 11px; }
QLabel#nodeLabel { color: $text_primary; font-weight: 700; }
QLabel#nodeSummary { color: $text_secondary; font-size: 11px; }
QLabel#scoreSummary { color: $text_secondary; font-size: 11px; }
""")


def build_stylesheet() -> str:
    """回傳完整 QSS（token 已代入）。"""
    return _QSS.substitute(TOKENS)


def apply_theme(app, theme: str = None) -> str:
    """把主題（palette + stylesheet）套到 QApplication 上，回傳套用的主題名。

    ``theme=None`` 沿用目前的（預設 light）。傳 ``"dark"`` 就整個介面轉暗 ——
    因為所有顏色都走 ``TOKENS``，換膚不需要動任何 widget。
    """
    from PySide6.QtGui import QColor, QFont, QPalette

    name = set_theme(theme if theme is not None else current_theme())
    app.setStyle("Fusion")  # 跨平台一致的 QSS 底座

    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(TOKENS["bg_page"]))
    pal.setColor(QPalette.Base, QColor(TOKENS["bg_input"]))
    pal.setColor(QPalette.AlternateBase, QColor(TOKENS["row_alt"]))
    pal.setColor(QPalette.Text, QColor(TOKENS["text_primary"]))
    pal.setColor(QPalette.WindowText, QColor(TOKENS["text_primary"]))
    pal.setColor(QPalette.ButtonText, QColor(TOKENS["text_primary"]))
    pal.setColor(QPalette.Button, QColor(TOKENS["bg_input"]))
    pal.setColor(QPalette.Highlight, QColor(TOKENS["selection"]))
    pal.setColor(QPalette.HighlightedText, QColor(TOKENS["text_primary"]))
    pal.setColor(QPalette.ToolTipBase, QColor(TOKENS["tooltip_bg"]))
    pal.setColor(QPalette.ToolTipText, QColor(TOKENS["tooltip_text"]))
    app.setPalette(pal)

    font = QFont()
    font.setPointSize(10)
    app.setFont(font)

    app.setStyleSheet(build_stylesheet())
    return name

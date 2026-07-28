# FlexADC Studio theme — authored 2026-07-28 (M3).
# Vendored from: cell-period-estimator/cell_period_estimator/ui/theme.py
#   （GLAS 暖色淺色 token 系統 + apply_theme QSS）— 視覺語言延續自 CPE，
#   FlexADC 只「加」不「改」：新增三段式 segment 色（image / algo / adc）與
#   good / bad 判定 chip 色，暖奶油底 + 琥珀 accent 原封不動。
"""FlexADC Studio 佈景主題 —— 設計 token 的唯一真相來源。

``TOKENS`` 同時餵給 QSS（標準 widget）與自繪 widget（直方圖、節點卡、色條），
顏色永遠不會兩邊走鐘。

三段式 segment 色（master plan §5）：

===========  ==========  ==========  ==========================================
段           前景 token  底色 token  用在哪
===========  ==========  ==========  ==========================================
影像 image   seg_image   seg_image_bg  Library 區塊標題、Pipeline 卡片左側色條
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

# --------------------------------------------------------------------------- #
# Design tokens
# --------------------------------------------------------------------------- #
TOKENS: Dict[str, Any] = {
    # -- backgrounds (low -> high elevation) -------------------------------
    "bg_page": "#f7f4ef",
    "bg_panel": "#faf7f3",
    "bg_surface": "#fff8f2",
    "bg_elevated": "#fff4e8",
    "bg_input": "#ffffff",
    "side_panel": "#fff7ee",
    "toolbar": "#f2ece4",
    "statusbar": "#f0e9e0",
    # -- borders ------------------------------------------------------------
    "border_default": "#e8d8c8",
    "border_input": "#c8b8a8",
    "border_hover": "#8a7060",
    "border_focus": "#f29f4b",
    # -- text ---------------------------------------------------------------
    "text_primary": "#3f3428",
    "text_secondary": "#7a6a5a",
    "text_hint": "#8a7660",
    "text_disabled": "#b0a090",
    # -- accent (amber) -----------------------------------------------------
    "accent": "#f29f4b",
    "accent_hover": "#f6b56b",
    "accent_active": "#d97d1e",
    "accent_bg": "#fff4e6",
    "accent_border": "#efd8b8",
    # -- selection / hover --------------------------------------------------
    "selection": "#f6c38c",
    "hover_warm": "#f6efe6",
    "hover_warm_strong": "#fff4e8",
    "focus_bg": "#fffef9",
    # -- semantic -----------------------------------------------------------
    "success": "#7abf9a",
    "success_bg": "#ebf7f0",
    "success_border": "#9ec9ad",
    "success_text": "#3e7f5d",
    "danger": "#cc7b6c",
    "danger_bg": "#feeee8",
    "danger_border": "#e0a89e",
    "danger_text": "#a8453a",
    "warning": "#d9a24f",
    "min_accent": "#d8894f",
    "min_accent_bg": "#fff8f0",
    "min_accent_border": "#f0c8a8",
    "min_accent_text": "#9a5a2a",
    "max_accent": "#6ea8cf",
    "max_accent_bg": "#f0f7fc",
    "max_accent_border": "#a8c8e0",
    "max_accent_text": "#3a6a8a",
    # -- FlexADC 三段式 segment 色 ------------------------------------------
    "seg_image": "#6f93b5",       # 影像段（把圖變乾淨）
    "seg_algo": "#c06a1d",        # 算法段（從圖量出數字）
    "seg_adc": "#8a6fb5",         # 判定段（score / bin / 輸出）
    "seg_image_bg": "#e8eef5",
    "seg_algo_bg": "#f9ecd9",
    "seg_adc_bg": "#ece6f4",
    "seg_disabled": "#cdc2b4",    # 停用節點的左側色條
    "seg_disabled_bg": "#f1ece5",
    # -- 判定 chip（good / bad / neutral）------------------------------------
    "chip_good_bg": "#e9f6ee",
    "chip_good_text": "#2f7a52",
    "chip_good_border": "#9ec9ad",
    "chip_bad_bg": "#fdece8",
    "chip_bad_text": "#a8453a",
    "chip_bad_border": "#e0a89e",
    "chip_neutral_bg": "#f2ece4",
    "chip_neutral_text": "#8a7660",
    "chip_neutral_border": "#e8d8c8",
    # -- tooltip (inverted) -------------------------------------------------
    "tooltip_bg": "#3f3428",
    "tooltip_text": "#faf7f3",
    "tooltip_border": "#2c2418",
    # -- lists / scrollbars / disabled --------------------------------------
    "list_bg": "#f2ece4",
    "row_alt": "#faf5ee",
    "scroll_track": "#faf5ee",
    "scroll_thumb": "#d8c8b6",
    "scroll_thumb_hover": "#b8a898",
    "disabled_bg": "#faf6f0",
    "disabled_text": "#c8b89e",
    "tab_inactive": "#efe8de",
    # -- section header tiers ------------------------------------------------
    "tier1_bg": "#fff4e8",
    "tier1_text": "#c97028",
    # -- typography ----------------------------------------------------------
    "font_stack": ("'Segoe UI','PingFang TC','Microsoft JhengHei',"
                   "'Helvetica Neue',Arial,sans-serif"),
    "mono_stack": "'Consolas','Courier New',monospace",
}

# 分類 -> (前景 token, 底色 token)。未知分類退回中性色。
_SEG_TOKENS = {
    "image": ("seg_image", "seg_image_bg"),
    "algo": ("seg_algo", "seg_algo_bg"),
    "adc": ("seg_adc", "seg_adc_bg"),
}

SEG_LABELS = {
    "image": "影像 Image",
    "algo": "算法 Algo",
    "adc": "ADC 判定",
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
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 600;
}
QToolBar QToolButton:hover { background: $hover_warm; color: $text_primary; }
QToolBar QToolButton:pressed { background: $hover_warm_strong; }
QToolBar QToolButton:checked {
    background: $accent_bg; color: $accent_active; border: 1px solid $accent_border;
}
QToolBar QToolButton#primary {
    background: $accent; color: #ffffff; border: 1px solid $accent_active;
    padding: 6px 18px; font-weight: 700;
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
    border-radius: 9px;
    margin-top: 16px;
    padding: 12px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    top: 2px;
    padding: 2px 8px;
    background: $tier1_bg;
    border: 1px solid $accent_border;
    border-radius: 5px;
    color: $tier1_text;
    font-size: 10px;
    font-weight: 700;
}

/* -- push buttons ------------------------------------------------------ */
QPushButton {
    background: $bg_input;
    color: $text_primary;
    border: 1px solid $border_input;
    border-radius: 6px;
    padding: 5px 13px;
    min-height: 18px;
    font-weight: 600;
}
QPushButton:hover { border-color: $border_hover; background: $hover_warm; }
QPushButton:pressed { background: $hover_warm_strong; }
QPushButton:focus { border: 1.5px solid $border_focus; }
QPushButton:disabled { background: $disabled_bg; color: $disabled_text;
                       border-color: $border_default; }
/* 主要動作（「試跑」「跑整批」）：objectName = "primary" */
QPushButton#primary {
    background: $accent; color: #ffffff; border: 1px solid $accent_active;
    padding: 6px 20px; font-weight: 700;
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
/* 卡片上的小方鈕（↑ ↓ ✕ / 加入 ▸） */
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
    border: 1.5px solid $border_input;
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
    border: 1.5px solid $border_focus; background: $focus_bg;
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
    border: 1.5px solid $border_input; border-radius: 3px; background: $bg_input;
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
    background: $list_bg; color: $accent_active; border: 0;
    border-bottom: 1px solid $border_default; padding: 4px 8px; font-weight: 700;
}

/* -- scroll area ------------------------------------------------------- */
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* -- splitter ---------------------------------------------------------- */
QSplitter { background: $bg_page; }
QSplitter::handle { background: $border_default; }
QSplitter::handle:hover { background: $accent; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical { height: 3px; }

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
QTabWidget::pane { border: 1px solid $border_default; border-radius: 7px;
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

/* -- Studio 專用 object names ------------------------------------------ */
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


def apply_theme(app) -> None:
    """把 GLAS 暖色主題（palette + stylesheet）套到 QApplication 上。"""
    from PySide6.QtGui import QColor, QFont, QPalette

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

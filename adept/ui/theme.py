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
    "group_hex", "group_color", "build_stylesheet", "apply_theme",
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
    #: 工具列的底**不能跟按鈕同色**（F7-24）。原本兩邊都是 ``#ffffff``，
    #: 於是那一排按鈕只靠一條 1px 的淺灰邊框跟背景分開 —— 使用者的評語是
    #: 「有點單調」，而單調的來源不是缺顏色，是**缺層次**：七顆白鈕貼在白條上。
    #: 暗色盤本來就沒有這個問題（toolbar 比 bg_surface 暗一階），所以只有
    #: 亮色要改。
    "toolbar": "#f7f8fa",
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
    #: 焦點框畫在**按鈕的填色上面**（Qt 的 ``outline`` 對按鈕不生效，見 QSS 裡
    #: 的說明），所以環的顏色要跟那顆按鈕自己的底對比 —— 淡底用 accent
    #: （``border_focus``），accent 底用這個。**light / dark 刻意同值**：
    #: 兩個主題的 primary 底都是藍的，白環在兩邊都對比得出來。
    "focus_ring_inverse": "#ffffff",
    # -- selection / hover --------------------------------------------------
    "selection": "#d5e3f8",
    "hover_warm": "#f0f2f5",          # 鍵名保留（歷史），已不是暖色
    "hover_warm_strong": "#e6eaf0",
    #: 按下去的那一階（F7-23 第三輪）。以前 ``:pressed`` 用的是
    #: ``hover_warm_strong`` —— 跟 hover 只差 ΔL≈3.5，而按住的時間大約 100ms，
    #: 在 24px 的小鈕上等於沒有回饋。全平面設計不能用陰影表達「壓下去」，
    #: 那底色就得真的跳一階。
    "pressed_bg": "#d9dee6",
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
    # -- 流程階段色（F7-9）：六個階段各一個色相（見 group_hex 的說明）--------
    "stage_input": "#2f8f80",
    "stage_enhance": "#3f7fbf",
    "stage_region": "#5f8f3f",
    "stage_compare": "#b0507f",
    "stage_measure": "#bf7030",
    "stage_adc": "#8a5fbf",
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
    # -- 影像背景（F7-7）------------------------------------------------------
    #: **light / dark 兩組刻意填同一個值。**
    #:
    #: 這個工具的核心工作是判斷 8-bit 灰階 patch 上的細微差異，而周圍的亮度
    #: 會偏移人對灰階的感知（同時對比效應）。原本影像底用的是 ``bg_panel``
    #: （淡色主題下近乎純白），那是最糟的組合：patch 會顯得比實際暗、
    #: 感知對比被壓縮。影像評估的慣例是中性灰（Photoshop/Lightroom 的深灰、
    #: 醫療影像 viewer 的黑底），理由就是不要讓背景去偏移判斷。
    #:
    #: 所以：**chrome 跟著主題走，影像區不跟。** 換主題時同一張 patch
    #: 看起來要一樣。
    "image_backdrop": "#3f4247",

    # -- canvas (F7-6 節點畫布) ----------------------------------------------
    "canvas_bg": "#f0f1f4",
    #: F7-8：背景從格線改成點陣之後這個值調深了一階。線鋪滿整片，太深會吵；
    #: 點只有交會處那一顆，用原本的淺色就直接看不見了。
    "canvas_grid": "#ced4de",
    "canvas_edge": "#9aa3ae",
    "canvas_edge_active": "#3574d6",
    #: 隱含順序的虛線（F7-18）。以前它是 ``canvas_edge`` 加透明度 —— 同一個
    #: 顏色淡一點，於是「這條線是我拉的」跟「這條線是排列順序帶來的」看起來
    #: 只差在深淺，而深淺在畫布上還會被縮放與背景影響。兩者在語意上是兩種
    #: 東西（一條刪得掉、一條刪不掉），所以給它自己的色相。
    "canvas_edge_implicit": "#b08a5a",
    # -- typography ----------------------------------------------------------
    "font_stack": ("'Segoe UI','PingFang TC','Microsoft JhengHei',"
                   "'Helvetica Neue',Arial,sans-serif"),
    "mono_stack": "'Consolas','Courier New',monospace",
    # -- geometry（F7-23）-----------------------------------------------------
    #: 圓角也是設計語言的一部分，不是每個呼叫端各填一個數字。F7-23 之前 QSS 裡
    #: 有六個值（3 / 4 / 5 / 6 / 7 / 9 px）散在各處，而它們之間沒有任何規則 ——
    #: 一顆按鈕與它旁邊的輸入框差 1px，看得出來但說不出為什麼。
    #:
    #: 三個尺度就夠了：``sm`` 給指示器與清單列（14–20px 高的東西），
    #: ``md`` 給所有「一塊面」（按鈕、輸入框、卡片、頁籤、面板），
    #: ``pill`` 給 chip。**light / dark 同值** —— 換膚換的是顏色，不是形狀。
    #:
    #: ⚠ ``pill`` 是**真的半高**（11px = chip 的 22px 高的一半），不是 CSS 那個
    #: ``999px`` 慣用寫法。**Qt 不會把超出範圍的圓角夾回去** —— 實測 999px 畫出來
    #: 的是**方角**（左緣輪廓量到一整排 0），而且不報錯。名字叫 pill、畫出來是
    #: 方的，是最難發現的一種。chip 的高度改了，這個值要跟著改。
    "radius_sm": "4px",
    "radius_md": "6px",
    "radius_pill": "11px",
    #: 小按鈕（畫布縮放列、卡片上的 ↑↓✕、換 defect 的 ◀▶、Card/Features）的邊長。
    #: F7-23 第二輪之前這是六個各自寫死的尺寸（22×22、24×22、30×22、寬 28、
    #: 寬 40、高 20）—— 同一種視覺語言，但沒有兩顆是一樣大的。
    "control_sm": "24px",
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
    "accent_border": "#33507d",
    "selection": "#2b3d5c",
    "hover_warm": "#282c34",
    "hover_warm_strong": "#30353f",
    "pressed_bg": "#3d434f",
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
    # -- 流程階段色（F7-9）---------------------------------------------------
    "stage_input": "#5cbfae",
    "stage_enhance": "#6fa6e0",
    "stage_region": "#93c46a",
    "stage_compare": "#dd7fac",
    "stage_measure": "#e0a05c",
    "stage_adc": "#b48fe0",
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

    "image_backdrop": "#3f4247",     # 與 light 相同 —— 見上面的說明
    "canvas_bg": "#16181d",
    "canvas_grid": "#2f3540",
    "canvas_edge": "#5c6474",
    "canvas_edge_active": "#4b8bf5",
    "canvas_edge_implicit": "#a2794a",
})

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


# 流程階段 -> 色彩 token（F7-9）。順序同 ``pipeline/step.py`` 的 ``GROUP_ORDER``。
_STAGE_TOKENS = {
    "input": "stage_input",
    "enhance": "stage_enhance",
    "region": "stage_region",
    "compare": "stage_compare",
    "measure": "stage_measure",
    "adc": "stage_adc",
}


def group_hex(group: str) -> str:
    """流程階段 -> 顏色 hex。純字串、免 Qt。

    為什麼階段色不再從 ``seg_hex`` 借（F7-9）
    ----------------------------------------
    F7-3 之前這裡是 ``group -> category -> 顏色``，於是六個階段只有三種色：
    Input／Enhance／Compare 全是藍的。試用回饋原話是「圖示很不錯，但太多都同
    個顏色」—— 圖示分得出來、顏色分不出來，等於顏色這個維度白給了。

    現在每個階段各有一個色相，但**冷暖仍然對得上三段式**：
    影像段（Input 藍綠／Enhance 藍／Compare 靛）走冷色、
    算法段（Region 綠／Measure 橙）與 ADC（紫）維持原本的識別。
    相鄰的兩階段永遠不同色系，所以在直式 rail 上由上而下掃過去分得開。

    ``seg_hex`` 沒有被取代 —— 需要講「這是哪一段」的地方（首啟導覽的三段說明、
    直方圖、Score/Bin 尾卡）仍然用它。兩個軸各有各的用途，見 CLAUDE.md §2。
    """
    return TOKENS[_STAGE_TOKENS.get(str(group), "stage_enhance")]


def group_color(group: str):
    """:func:`group_hex` 的 ``QColor`` 版。"""
    from PySide6.QtGui import QColor

    return QColor(group_hex(group))


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
/* Toolbar buttons look like buttons, not like a menu bar. Borderless text in
 * a row reads as “File Edit View…”, and a menu bar is something you pull down,
 * not something you press — so the whole strip stopped looking clickable. */
/* One vertical rhythm for every button in the app (F7-23 round 2):
 * 1px border + 5px padding + 18px min-height = 30px, full stop. Importance is
 * expressed horizontally - primary is wider, never taller. It used to be
 * taller too, so in the empty state "Open KLARF..." stood 2px above the
 * "Try it with sample data" next to it, and the toolbar had no min-height at
 * all, which left its row depending on the font's text height. */
QToolBar QToolButton {
    background: $bg_surface;
    color: $text_primary;
    border: 1px solid $border_input;
    border-radius: $radius_md;
    padding: 5px 12px;
    min-height: 18px;
    font-weight: 500;
}
QToolBar QToolButton:hover { background: $hover_warm; color: $text_primary;
                             border-color: $border_hover; }
QToolBar QToolButton:pressed { background: $pressed_bg;
                               border-color: $border_hover; }
QToolBar QToolButton:disabled { color: $text_disabled; border-color: $border_default; }
/* One hairline between groups: seven equal-weight buttons in a row read as a
 * single run, so you have to read all of them to find the one you want.
 *
 * This rule used to be written twice, with different margins, and the copy that
 * won was the one 20 lines below with no comment on it - so the explanation and
 * the behaviour lived in different places. Values here are the ones that were
 * actually in effect. */
QToolBar::separator {
    background: $border_default;
    width: 1px;
    margin: 5px 6px;
}
/* The stretcher between the left and right halves must not look like a control. */
QWidget#toolbarSpacer { background: transparent; border: 0; }
QToolBar QToolButton:checked {
    background: $accent_bg; color: $accent_active; border: 1px solid $accent_border;
}
QToolBar QToolButton#primary {
    background: $accent; color: #ffffff; border: 1px solid $accent;
    padding: 5px 16px; font-weight: 600;
}
/* Icon-only buttons carry no label, so the horizontal padding that sizes a
 * text button would leave them enormous; and a button that draws its own glyph
 * next to a label has to be told to leave room for it (F7-23 round 4). */
QToolBar QToolButton[glyph="true"] { padding: 5px 8px; }
QToolBar QToolButton[hasGlyph="true"] { padding-left: 26px; }
QToolBar QToolButton#primary[hasGlyph="true"] { padding-left: 30px; }
QToolBar QToolButton#primary[hasGlyph="true"]:focus { padding-left: 29px; }
/* The second-most important action on the bar (Export) gets the accent as an
 * outline, not a fill - the fill belongs to Run trial. Two coloured buttons on
 * the whole bar, and they are the two the user actually came to press. */
QToolBar QToolButton[variant="secondary"] {
    background: $bg_surface; color: $accent_active; border: 1px solid $accent;
    font-weight: 600;
}
QToolBar QToolButton[variant="secondary"]:hover { background: $accent_bg; }
QToolBar QToolButton[variant="secondary"]:pressed { background: $accent_bg;
                                                    border-color: $accent_active; }
QToolBar QToolButton[variant="secondary"]:focus {
    border: 2px solid $border_focus; padding: 4px 11px;
}
QToolBar QToolButton[variant="secondary"]:disabled {
    background: $disabled_bg; color: $disabled_text; border: 1px solid $border_default;
}
/* Run trial and its ▾ are one control with two halves, so the corners that
 * face each other are square and the 1px between them shows the bar through.
 * Sitting apart with the toolbar's usual 6px gap, they read as two unrelated
 * buttons - and the arrow is not another feature, it is this button's other
 * way of running. */
QToolBar QToolButton#primary[seg="left"] {
    border-top-right-radius: 0; border-bottom-right-radius: 0;
}
QToolBar QToolButton#primary[seg="right"] {
    border-top-left-radius: 0; border-bottom-left-radius: 0;
    padding-left: 7px; padding-right: 7px;
}
QToolBar QToolButton#primary[seg="right"]:focus { padding-left: 6px; padding-right: 6px; }
QWidget#toolbarGroup { background: transparent; border: 0; }
QToolBar QToolButton#primary:hover { background: $accent_hover; }
QToolBar QToolButton#primary:pressed { background: $accent_active; }
/* Disabled, but still recognisably the main action (F7-23).
 *
 * This used to be the same grey-on-grey as every other disabled button, so with
 * no dataset open the whole toolbar was one flat strip and "where is the thing
 * I am supposed to press" had no answer - which is exactly the moment a new
 * user needs one. Keeping the pale accent plate says "this is the main action,
 * it just isn't available yet"; the muted text still says "not now". */
QToolBar QToolButton#primary:disabled {
    background: $accent_bg; color: $text_disabled; border: 1px solid $accent_border;
}

/* -- status bar ------------------------------------------------------- */
QStatusBar { background: $statusbar; color: $text_secondary;
             border-top: 1px solid $border_default; }
/* A refusal must not look like a confirmation (F7-15). The status bar is the
 * only place that says a trial was blocked by lint, or a card could not be
 * added - in the same grey as "Added denoise", that reads as nothing said. */
QStatusBar[level="error"] { color: $danger_text; font-weight: 600; }
QStatusBar::item { border: 0; }

/* -- group boxes (section cards) -------------------------------------- */
QGroupBox {
    background: $bg_surface;
    border: 1px solid $border_default;
    border-radius: $radius_md;
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
    border-radius: $radius_md;
    padding: 5px 12px;
    min-height: 18px;
    font-weight: 500;
}
QPushButton:hover { border-color: $border_hover; background: $hover_warm; }
/* Pressed has to be a real step, not a shade (F7-23 round 3). It used to reuse
 * the hover colour one notch darker - about 3.5 in L* - and a press lasts
 * roughly 100ms, so on a 24px button that read as nothing happening. A flat
 * design has no shadow to fall back on, so the fill itself has to move. */
QPushButton:pressed { background: $pressed_bg; border-color: $border_hover; }
/* A checkable QPushButton had no checked rule at all; only #cardButton did.
 * The next checkable button anyone adds would have looked unchecked forever. */
QPushButton:checked {
    background: $accent_bg; color: $accent_active; border-color: $accent_border;
}
QPushButton:disabled { background: $disabled_bg; color: $disabled_text;
                       border-color: $border_default; }
/* primary action (Run trial / Run all): objectName = "primary" */
QPushButton#primary {
    background: $accent; color: #ffffff; border: 1px solid $accent;
    padding: 5px 18px; font-weight: 600;
}
QPushButton#primary:hover { background: $accent_hover; }
QPushButton#primary:pressed { background: $accent_active; }
/* See the toolbar copy above for why disabled-primary keeps the accent plate. */
QPushButton#primary:disabled {
    background: $accent_bg; color: $text_disabled; border: 1px solid $accent_border;
}
QPushButton[variant="secondary"] {
    background: $bg_input; color: $accent_active; border: 1px solid $accent;
    font-weight: 600;
}
QPushButton[variant="secondary"]:hover { background: $accent_bg; }
QPushButton[variant="secondary"]:pressed { background: $accent_bg;
                                           border: 1px solid $accent_active; }
QPushButton[variant="secondary"]:disabled {
    background: $disabled_bg; color: $disabled_text; border: 1px solid $border_default;
}
QPushButton[variant="ghost"] {
    background: transparent; color: $text_secondary; border: 1px solid transparent;
}
QPushButton[variant="ghost"]:hover { background: $hover_warm; color: $text_primary; }
QPushButton[variant="danger"] {
    background: $danger_bg; color: $danger_text; border: 1px solid $danger_border;
    font-weight: 600;
}
QPushButton[variant="danger"]:hover { border-color: $danger_text; }
/* Stop stays visible after it is pressed, disabled, so that "I already asked
 * it to stop" is on screen while the current defects finish. */
QPushButton[variant="danger"]:disabled {
    background: $disabled_bg; color: $disabled_text; border-color: $border_default;
}
/* Small buttons: card controls, the canvas zoom bar, defect nav, the
 * Card/Features switch.
 *
 * #cardButton says what KIND of button it is; [shape] says how big it is; and
 * [kind="icon"] gives it a surface of its own. Six call sites used to hard-code
 * six sizes for what is visually one button - 22x22, 24x22, 30x22, w28, w40,
 * h20 - so no two of them lined up. Geometry is the sheet's business now; the
 * call site only says which of the two shapes it wants.
 *
 * Note #cardButton deliberately declares no padding or height any more: an id
 * selector outranks [shape], so leaving them here would silently win. */
QPushButton#cardButton {
    background: transparent; color: $text_secondary;
    border: 1px solid transparent; border-radius: $radius_sm;
    font-weight: 700;
}
QPushButton[shape="square"] {
    min-width: $control_sm; max-width: $control_sm;
    min-height: $control_sm; max-height: $control_sm; padding: 0px;
}
QPushButton[shape="wide"] {
    min-height: $control_sm; max-height: $control_sm; padding: 0px 8px;
}
/* Buttons that float over the canvas or over an image need a surface, or they
 * are invisible until you happen to hover the right patch of background -
 * which is the same reason F7-13 gave the toolbar buttons a border. The ones
 * that live inside a card stay transparent: there the card is the surface. */
QPushButton#cardButton[kind="icon"] {
    background: $bg_surface; border: 1px solid $border_default;
}
QPushButton#cardButton[kind="icon"]:hover {
    background: $hover_warm; border-color: $border_hover; color: $accent_active;
}
/* Hover moves two things here, same as every other button. It used to move
 * three - fill, border AND text colour - so the smallest, least important
 * button in the app had the loudest reaction of any of them. Accent text is
 * kept for :checked, where it means something. */
QPushButton#cardButton:hover { background: $hover_warm_strong;
                               border: 1px solid $border_default; }
QPushButton#cardButton:pressed { background: $pressed_bg;
                                 border: 1px solid $border_hover; }
QPushButton#cardButton:disabled { color: $disabled_text; background: transparent; }
/* The card / features switch under the image: the selected one has to look
 * selected, or the pair reads as two labels rather than a choice (F7-17). */
QPushButton#cardButton:checked {
    background: $accent_bg; color: $accent_active;
    border: 1px solid $accent_border; font-weight: 600;
}

/* -- keyboard focus (F7-23) --------------------------------------------- *
 * Focus has to be visible on EVERY button, and until F7-23 it was visible on
 * exactly one kind: a plain QPushButton. Two separate things were hiding it.
 *
 * 1. Specificity. `QPushButton#primary` is an id selector, so it outranks
 *    `QPushButton:focus` and its own `border` wins; `[variant="..."]` ties
 *    with `:focus` and wins by being written later in this sheet. So Run
 *    trial, Stop, and Try it with sample data had no focus state at all - and
 *    no toolbar button ever had one, because there was no QToolButton:focus
 *    rule to begin with. Every variant therefore needs its own :focus rule;
 *    a single blanket one is silently outranked.
 *
 * 2. `outline` does nothing here. Qt accepts the property and paints nothing
 *    for buttons under Fusion - measured, with and without outline-offset -
 *    so the ring has to be a border, drawn inside the button.
 *
 * Being inside costs a pixel, so each rule pays it back out of its own
 * padding: the label must not move when you tab onto it. And the ring colour
 * is whatever contrasts with THAT button's fill - accent on the pale fills,
 * white on the accent fill. The small transparent buttons keep a 1px ring
 * because they have no padding to give back, but transparent -> accent is a
 * big enough change on its own.
 *
 * This is the other half of F7-16: shortcuts made the keyboard path work,
 * this makes it visible. */
QPushButton:focus, QPushButton[variant="secondary"]:focus,
QPushButton[variant="danger"]:focus {
    border: 2px solid $border_focus; padding: 4px 11px;
}
QToolBar QToolButton:focus { border: 2px solid $border_focus; padding: 4px 11px; }
QPushButton#primary:focus {
    border: 2px solid $focus_ring_inverse; padding: 4px 17px;
}
QToolBar QToolButton#primary:focus {
    border: 2px solid $focus_ring_inverse; padding: 4px 15px;
}
/* These two already have a 1px border (transparent), so the ring costs them
 * nothing - but they must restate their padding, or the blanket rule's
 * 1px-compensation above applies to them and the label shifts anyway. */
QPushButton[variant="ghost"]:focus {
    border: 1px solid $border_focus; padding: 5px 12px;
}
QPushButton#cardButton:focus {
    border: 1px solid $border_focus; background: $accent_bg; color: $accent_active;
}

/* -- library rows, stage rail, gallery chips (F7-23 round 3) ------------ *
 * These three used to carry a stylesheet string each, built in their own
 * constructor from TOKENS. That made theme.py's promise - one source of truth,
 * the colours never drift apart - false for exactly the widgets a user looks at
 * most, and it only held together because someone remembered to call
 * refresh_style()/_restyle() on every theme switch. One of them wasn't called:
 * a library row with a "needs diff" badge kept the old theme's grey.
 *
 * What genuinely varies per instance stays in the widget: the stage colour of
 * the rail icon and the category dot are computed from the step, not the theme.
 */
QFrame#libItem { background: transparent; border: 1px solid transparent;
                 border-radius: $radius_sm; }
QFrame#libItem:hover { background: $hover_warm; border-color: $border_default; }
/* A card whose inputs are not on the canvas yet is dimmed, badge and all. */
QFrame#libItem[missing="true"] QLabel { color: $text_disabled; }
QLabel#libBadge { color: $text_disabled; font-size: 10px;
                  border: 1px solid $border_default; border-radius: $radius_sm;
                  padding: 0px 4px; }

QFrame#stageButton { background: transparent; border: 1px solid transparent;
                     border-radius: $radius_md; }
QFrame#stageButton:hover { background: $hover_warm; }
QFrame#stageButton[active="true"] { background: $accent_bg;
                                    border-color: $accent_border; }
QLabel#stageCount { font-size: 9px; color: $text_disabled; }

QPushButton#galleryChip {
    background: $accent_bg; color: $accent_active;
    border: 1px solid $accent_border; border-radius: $radius_pill;
    padding: 2px 9px; font-size: 11px; font-weight: 500; min-height: 16px;
}
QPushButton#galleryChip:hover { background: $hover_warm_strong; }
QPushButton#galleryChip:pressed { background: $pressed_bg; }
QPushButton#galleryChip:focus { border: 1px solid $border_focus; }

/* -- inputs ------------------------------------------------------------ */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: $bg_input;
    color: $text_primary;
    border: 1px solid $border_input;
    border-radius: $radius_md;
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
/* A dropdown must not be pixel-identical to a free-text field.
 *
 * `border: 0` here used to hide the arrow completely: styling this subcontrol
 * hands it to the stylesheet, and a styled drop-down draws no arrow unless the
 * rule also supplies a `down-arrow` image — which this repo cannot ship,
 * because it is text-only (see CLAUDE.md §9.5). Leaving the border unset keeps
 * the subcontrol on the base style, which paints the arrow itself.
 *
 * The visible consequence was that "Match on" (three fixed streams) and "Name
 * this region" (free text) looked exactly the same, so there was no way to
 * tell which fields could be opened and which had to be typed.
 * tests/test_ui_controls_readable.py locks this. */
QComboBox::drop-down { width: 20px; subcontrol-origin: padding;
                       subcontrol-position: center right; }
QComboBox QAbstractItemView {
    background: $bg_input; border: 1px solid $border_default;
    selection-background-color: $selection; selection-color: $text_primary;
    outline: 0;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 16px; background: $bg_elevated; border-left: 1px solid $border_default;
}

/* -- sliders (F7-8) ----------------------------------------------------- *
 * One per bounded parameter. The handle is deliberately larger than Qt's
 * default: the whole point is dragging it while watching the image, and a
 * handle you keep missing is the same as no slider at all.                */
QSlider { background: transparent; min-height: 22px; }
QSlider::groove:horizontal {
    height: 4px; border-radius: 2px;
    background: $border_default;
}
QSlider::sub-page:horizontal {
    height: 4px; border-radius: 2px; background: $accent;
}
QSlider::handle:horizontal {
    width: 12px; height: 12px; margin: -5px 0; border-radius: 6px;
    background: $bg_elevated; border: 2px solid $accent;
}
QSlider::handle:horizontal:hover { border-color: $accent_active; }
QSlider::handle:horizontal:pressed { background: $accent; }
QSlider:disabled::sub-page:horizontal { background: $border_default; }
QSlider:disabled::handle:horizontal { border-color: $border_default; }

/* -- check boxes ------------------------------------------------------- */
QCheckBox { background: transparent; spacing: 6px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid $border_input; border-radius: $radius_sm; background: $bg_input;
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
    border: 1px solid $border_default; border-radius: $radius_md;
    selection-background-color: $selection; selection-color: $text_primary;
    outline: 0;
}
QListView::item, QTreeView::item { padding: 3px 4px; border-radius: $radius_sm; }
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

/* -- scrollbars -------------------------------------------------------- *
 * The 5px here is deliberately NOT $radius_sm: an 11px-wide bar with a 5px
 * radius is a capsule, and it should stay a capsule if the token ever moves. */
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
    border-radius: $radius_md; text-align: center; min-height: 14px;
    color: $text_secondary;
}
QProgressBar::chunk { background: $accent; border-radius: $radius_md; }

/* -- tabs -------------------------------------------------------------- */
QTabWidget::pane { border: 1px solid $border_default; border-radius: $radius_md;
                   background: $bg_surface; }
QTabBar::tab { background: $tab_inactive; color: $text_secondary;
               padding: 5px 14px; margin-right: 2px;
               border-top-left-radius: $radius_md;
               border-top-right-radius: $radius_md; }
QTabBar::tab:selected { background: $bg_surface; color: $accent_active;
                        font-weight: 700; }

/* -- menus / tooltips -------------------------------------------------- */
QMenu { background: $bg_surface; border: 1px solid $border_default; padding: 4px; }
QMenu::item { padding: 4px 18px; border-radius: $radius_sm; }
QMenu::item:selected { background: $selection; color: $text_primary; }
QToolTip {
    background: $tooltip_bg; color: $tooltip_text; border: 1px solid $tooltip_border;
    padding: 4px 6px;
}

/* -- Studio-specific object names -------------------------------------- */
QLabel#paramTitle { color: $text_primary; font-size: 14px; font-weight: 700; }
QLabel#paramStepHelp { color: $text_secondary; font-size: 11px; }
/* Section heading in the parameter form. A signpost, not content: it has to
   read as a heading (weight, colour, space above) without competing with the
   parameters themselves. */
QLabel#paramSection {
    color: $text_secondary; font-size: 10px; font-weight: 600;
    padding: 10px 0 2px 2px; border-bottom: 1px solid $border_default;
}
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

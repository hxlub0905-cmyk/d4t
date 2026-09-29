# d4t Studio 首次開啟導覽 — authored 2026-07-28 (M6-2).
"""``WelcomeDialog`` 與 ``RecipeLibraryDialog`` —— 產品的「上車處」。

為什麼要有這個檔（推廣鐵則）
----------------------------
d4t 的存在意義是讓**不會寫 code 的製程／設備工程師**把一個想法變成評分
演算法。可是第一次打開 Studio 看到的是一條空流程 —— 東西全都在，就是沒有
入口。這支對話框的唯一任務：**讓一個從沒用過的人，在大約一分鐘內看到一批
真的算出分數的結果**。

所以它不是一面文字牆，而是三顆「按下去真的會發生事情」的按鈕：

1. **用範例資料試一次** —— 產一批合成資料 → 載入 → 載入範本 → 試跑，最後畫面上
   是有分數分佈的直方圖與一整牆縮圖。**全產品最重要的一顆鈕。**
2. **開啟我自己的 KLARF** —— 關掉自己，交給 Studio 的「開啟 KLARF…」。
3. **看範例 recipe** —— 打開 :class:`RecipeLibraryDialog`（範例 recipe 庫）。

**第 1 顆 2026-09-09 回來了**（``scope.SHOW_SAMPLE_DATA``）：它以前產得出
一批合成資料，但**不載 pipeline** —— `studio.TEMPLATE_RECIPE` 指著一個刪掉的
路徑。現在指 `recipes/ebi-die-to-die.json`，整條路通到 Gallery。

**第 3 顆 2026-09-08 回來了**（F91 X4，``scope.SHOW_TEMPLATE_LIBRARY``）：
`recipes/` 有出貨的 recipe 了，而且逐份有測試跑過。兩顆從此看**兩個**旗標
—— 它們是兩件事，而混在一個旗標裡會讓打開其中一個順手把另一個也放回畫面上。

**對話框不自己驅動 app**：三顆鈕都只 emit 訊號，真正的動作由
:class:`~d4t.ui.studio.StudioWindow` 執行。這樣對話框可以單獨測，
Studio 也可以在沒有對話框的情況下跑同一段流程（``run_demo``）。

「不再顯示」寫進 ``QSettings``（org ``d4t`` / app ``Studio``，鍵
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

from . import fit_screen
# ⚠ **旗標要透過模組讀，不要 `from .scope import SHOW_…`**（U10）：
# `scope.use_profile()` 改的是 scope 模組上的那幾個名字，而 import 進來的
# 是一份**當時的複本** —— 換了 profile 而這裡停在舊值，症狀是「設定說
# 關著、畫面上還在」。`tests/test_ui_scope_profiles.py` 擋著。
from . import scope
from . import wording
from . import strings
from .scope import recipe_is_supported
from .theme import SEG_LABELS, TOKENS, seg_hex
from .widgets import apply_button_cursors

__all__ = [
    "WelcomeDialog", "RecipeLibraryDialog",
    "SETTINGS_ORG", "SETTINGS_APP", "SKIP_WELCOME_KEY",
    "app_settings", "welcome_disabled", "set_welcome_disabled",
    "THEME_KEY", "saved_theme", "save_theme",
    "RECIPES_DIR", "DOCS_DIR", "list_recipe_files", "read_recipe_info",
    "quick_reference_pdf",
]

#: repo 根目錄（本檔在 ``<repo>/d4t/ui/welcome.py``）。
_REPO = Path(__file__).resolve().parents[2]

#: 範本庫的位置（``RecipeLibraryDialog`` 的預設來源）。
#:
#: **2026-09-08（F91 X4）：``examples/recipes`` → ``recipes``。** 前者
#: 2026-08-16 就整個刪掉了，所以在這之前這個常數指著一個**不存在的資料夾**
#: —— 那正是「範本庫開起來是空的」那句話的機制。現在指的是出貨的那一份，
#: 而 `tests/test_shipped_recipes.py` 逐份真的跑一次。
#:
#: ⚠ 資料夾不在的時候 `list_recipe_files` 回空清單（pip 裝出來的 d4t 沒有
#: `recipes/` —— 它不在 `packages.find` 裡）。跟 `DOCS_DIR` 同一個約定。
RECIPES_DIR = _REPO / "recipes"

#: 快速參考卡 PDF 找這個資料夾。
DOCS_DIR = _REPO / "docs"

#: QSettings 座標（三處共用：本檔、Studio、測試）。
SETTINGS_ORG = "d4t"
SETTINGS_APP = "Studio"
SKIP_WELCOME_KEY = "welcome/skip"

#: 主題偏好（F7-2）。與導覽旗標共用同一組 QSettings。
THEME_KEY = "ui/theme"

#: 三段式的一句話說明（和 docs/ARCHITECTURE.md 的心智模型逐字對應）。
_SEG_LINES = (
    ("image", "Make images clean and comparable"),
    ("algo", "Measure numbers from images (quantified evidence)"),
    ("adc", "Score → bin → write back to KLARF"),
)

#: 三段（引擎）與卡片庫七群（使用者）的關係 —— **第一次見面唯一會問的那句**
#: （F117 G2）。⚠ 群數不寫死：`step.GROUPS` 加一群的那天，這句話會變成一句
#: 安靜的假話（`_axes_note` 去數）。
AXES_NOTE = ("Those three are what the engine does. The card library on the "
             "left is sorted a different way - by what you are looking for "
             "(%d groups, from Input to Output). Same cards, two ways in.")

def axes_note() -> str:
    """那句話 —— **群數是數出來的**（同 `_intro_text` 的規矩）。

    寫死一個 7 的話，`step.GROUPS` 加一群的那天它會變成一句安靜的假話：
    畫面上寫七群、卡片庫裡是八群，而沒有任何測試會紅。
    """
    from d4t.core.pipeline.step import GROUPS

    return strings.tr(AXES_NOTE) % len(GROUPS)


#: 判定那一段的四個字（F117 D4；F122 期 3 收掉第五個「verdict」—— 它講的就是
#: 一顆 defect 的 class，現在畫面上那一格也叫 Class）。**順序是使用者遇到它們的
#: 順序**，不是字母序 —— 這張表要讀起來像一句話：分數 → 問題 → 類別 → 編號。
#:
#: 為什麼需要它
#: ------------
#: 走查記的是「Decision / Verdict / bin / class / score 多種叫法」。掃過整個
#: 畫面之後**沒有亂用的同義詞**（`grade`／`bucket`／`category` 一個都沒有）
#: —— 五個字各自都用得很一致。缺的是**沒有任何地方告訴使用者它們怎麼串起來**，
#: 而它們在同一個畫面上同時出現。
#:
#: ⚠ **每一句都講「它在畫面上是哪一個東西」**，不是給一個定義。一個不寫 code
#: 的製程工程師要的是「我看到的那一格叫什麼」，而不是一段名詞解釋。
GLOSSARY = (
    ("score", "One number per defect, worked out from what the cards "
              "measured. You write the expression."),
    ("decision", "The tree on the canvas. Each step asks the score (or any "
                 "other number) a question."),
    ("class", "Where a defect ends up on that tree - you name it yourself "
              "(“a spot stands out”). The chip beside the preview shows the "
              "class one defect got, with its bin."),
    ("bin", "The number that class writes into the KLARF. One class, one "
            "bin."),
)


def open_title() -> str:
    """那顆「開自己的資料」鈕在 Studio 上叫什麼（F121 期 4：入口只有一顆）。

    **從表上讀，不寫死**（F117 G1 那一課：這一頁的數字與名字寫死過兩次，兩次
    都漂了）。以前這裡是 ``ways_in()`` —— 「開 KLARF 以外還有幾條路」—— 而入口
    合成一顆之後那個數字只剩附加檔，句子也就不該再數了。
    """
    return scope.INPUT_SOURCES[0].title if scope.INPUT_SOURCES else ""


def _intro_text() -> str:
    """導覽最上面那一段。

    ⚠ **它刻意不列出有哪幾種資料** —— 那張清單只有一個家
    （`scope.INPUT_SOURCES`），而 `InputSource` 自己的說明就寫著它為什麼存在：
    「在這張表出現之前，同一組入口被抄在三個地方：工具列三顆鈕的 tooltip、
    空白狀態上的那一句話、導覽對話框上的那顆鈕。三份會漂 —— 而且已經漂了」。

    **這一段就是那第三份，而它一直沒有被改成從表上長出來**，所以它漂了
    （F117 G1）。改法不是「也從表上長一句」—— 那樣長出來的句子讀起來像清單，
    而這裡要的是一句歡迎詞；改法是**不要在這裡列**，把「有哪幾種」留給真的
    一種一列的地方（關掉這扇窗就看得到的空白狀態，那一列本來就是從表長的）。
    """
    return (
        "d4t reads the tool's patch / Review SEM images — with or without a "
        "KLARF — and lets you build a pipeline out of step cards: it scores "
        "every defect, sorts them into bins with a decision tree, and writes the "
        "result back to KLARF."
        "\nNo programming needed — you decide what a real defect looks like, "
        "and the pipeline works it out.")

def _footer_hint() -> str:
    """導覽底下那句提示。**它必須描述畫面上真的看得到的鈕。**

    三種狀態三句話（範例資料那顆收著的時候，「按左邊那顆，一分鐘就看得到
    分數」指的會是「開啟我自己的資料」，而那顆給不出那個結果）。

    ⚠ **是函式不是常數**（F117 G1）。兩個理由，而第二個是 bug：

    1. 最後那一句以前寫著「the four kinds of data it reads」—— 而
       `scope.INPUT_SOURCES` 那時是**三**條（F114 拿掉 stack 之後）。寫死的
       數字會漂，所以它改成數出來的；F121 期 4 入口合成一顆之後不再數，改成
       講那顆鈕的名字（也是從表上讀的，:func:`open_title`）。
    2. 常數是在 **import 的那一刻**算的，於是 `scope.use_profile()` 換過
       profile 之後這一句還停在舊的分支 —— 那正是 U10 那條「旗標要透過模組
       讀」在講的事，而這一行剛好是漏網的那個。
    """
    if scope.SHOW_SAMPLE_DATA:
        return ("First time here? Press the button on the left — you will be "
                "looking at scored results in about a minute.")
    if scope.SHOW_TEMPLATE_LIBRARY:
        return ("Open your own data, then press “Templates…” — do not start "
                "from an empty pipeline; every template is a complete, "
                "runnable one.")
    return ("Close this window, open your data with “%s”, then build the "
            "pipeline card by card from the library on the left."
            % open_title())


# --------------------------------------------------------------------------- #
# QSettings 小工具
# --------------------------------------------------------------------------- #
def app_settings() -> QSettings:
    """Studio 的 ``QSettings``（org ``d4t`` / app ``Studio``、INI 格式）。"""
    return QSettings(QSettings.IniFormat, QSettings.UserScope,
                     SETTINGS_ORG, SETTINGS_APP)


def welcome_disabled() -> bool:
    """使用者是否勾過「不再顯示」。讀不到／格式怪 → 一律回 False（照樣顯示）。"""
    value = app_settings().value(SKIP_WELCOME_KEY, False)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def saved_theme(default: str = "light") -> str:
    """使用者上次選的主題（讀不到就回 ``default``）。"""
    try:
        return str(app_settings().value(THEME_KEY, default) or default)
    except Exception:  # 設定讀不到不該擋開窗
        return default


def save_theme(name: str) -> None:
    """記住主題偏好（立刻 sync）。"""
    st = app_settings()
    st.setValue(THEME_KEY, str(name))
    st.sync()


def set_welcome_disabled(disabled: bool) -> None:
    """寫入「不再顯示」旗標（立刻 sync，關窗當掉也不會掉設定）。"""
    st = app_settings()
    st.setValue(SKIP_WELCOME_KEY, bool(disabled))
    st.sync()


# --------------------------------------------------------------------------- #
# recipe 庫的讀取（全部從 JSON 讀，一個字都不寫死）
# --------------------------------------------------------------------------- #
def list_recipe_files(directory: Any = None) -> List[Path]:
    """``recipes/*.json`` 依檔名排序（資料夾不在就回空清單）。"""
    d = Path(str(directory)) if directory is not None else RECIPES_DIR
    if not d.is_dir():
        return []
    return sorted(d.glob("*.json"))


#: 清單上那一行摘要最多幾個字（F117 G3）。出貨那三份的第一句有 150～400 個
#: 字 —— 整句放進清單就變成一面牆，而使用者在那個清單上要做的是「掃過去挑
#: 一份」。完整的一段在右邊那一塊。
#: 轉出口 —— **本體住 `ui/wording.py`**（F117 H3 起兩個地方共用）。
#: 既有的測試 import 的是這兩個名字，所以它們留在這裡。
HEADLINE_MAX = wording.HEADLINE_MAX
_headline = wording.headline


def _count_classes(decide: Dict[str, Any]) -> int:
    """判定樹上有幾個類別（葉子）—— 給庫上那一行「分成幾類」用。

    ⚠ 讀的是**生的 JSON**，不是 `DecideSpec`：這一支的規矩是「不驗證、不炸」
    （壞掉的檔案要變成一列紅字，不是讓整個庫開不起來）。
    """
    seen = set()

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if "bin" in node:
            seen.add(node.get("bin"))
            return
        walk(node.get("yes"))
        walk(node.get("no"))

    walk(decide.get("tree"))
    for rule in (decide.get("rules") or []):
        if isinstance(rule, dict):
            seen.add(rule.get("bin"))
    if decide.get("rules"):
        seen.add((decide.get("otherwise") or {}).get("bin"))
    return len(seen)


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
        # **有沒有判定樹**（F117 G3）：沒有這一格的時候，一份走判定樹的
        # recipe 在庫上寫著 `score = (no score expression)` —— 讀起來像
        # 「這一份不會判定」，而它其實是**用另一種方式**判定的。
        "has_tree": False, "n_classes": 0,
        "version": None, "error": "",
    }
    try:
        with open(str(p), "r", encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            raise ValueError("top level is not a JSON object")
    except Exception as e:  # UI 邊界
        info["error"] = wording.exception_text(e)
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

    decide = d.get("decide") or {}
    if isinstance(decide, dict):
        info["has_tree"] = decide.get("tree") is not None or bool(
            decide.get("rules"))
        info["n_classes"] = _count_classes(decide)

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
        if any(k in low for k in ("quick", "reference", "quickref", "card")):
            return p
    return pdfs[0]


# --------------------------------------------------------------------------- #
# 三段式視覺（影像 → 算法 → ADC 判定）
# --------------------------------------------------------------------------- #
class _SegmentStrip(QWidget):
    """一條「影像 → 算法 → ADC 判定」的彩色說明帶（不用任何圖檔）。

    顏色直接取 :func:`~d4t.ui.theme.seg_hex`，和卡片庫區塊標題、Pipeline
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
                arrow.setStyleSheet("color:%s; font-size:%s;"
                                    % (TOKENS["text_hint"], TOKENS["font_title"]))
                lay.addWidget(arrow, 0)
            lay.addWidget(self._card(cat, line), 1)

    def _card(self, category: str, line: str) -> QFrame:
        fg, bg = seg_hex(category), seg_hex(category, bg=True)
        card = QFrame(self)
        card.setObjectName("segCard")
        card.setStyleSheet(
            "QFrame#segCard { background:%s; border:%s solid %s;"
            " border-radius:%s; }"
            % (bg, TOKENS["hairline"], fg, TOKENS["radius_md"]))
        card.setProperty("category", category)
        card.setMinimumHeight(58)
        box = QVBoxLayout(card)
        box.setContentsMargins(10, 7, 10, 7)
        box.setSpacing(2)

        title = QLabel(SEG_LABELS[category], card)
        title.setStyleSheet("color:%s; font-weight:700; font-size:%s;"
                            % (fg, TOKENS["font_body"]))
        body = QLabel(line, card)
        body.setWordWrap(True)
        body.setStyleSheet("color:%s; font-size:%s;"
                           % (TOKENS["text_secondary"], TOKENS["font_small"]))
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
        self.setWindowTitle(strings.tr("Welcome to d4t"))
        self.setModal(False)          # 永遠不擋住主視窗（測試也才不會卡住）
        self.setMinimumWidth(620)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        title = QLabel(strings.tr("d4t — build your own defect decision pipeline from cards"), self)
        title.setObjectName("paramTitle")
        root.addWidget(title)

        intro = QLabel(_intro_text(), self)
        intro.setWordWrap(True)
        intro.setStyleSheet("color:%s;" % TOKENS["text_secondary"])
        self.intro_label = intro
        root.addWidget(intro)

        self.segments = _SegmentStrip(self)
        root.addWidget(self.segments)

        # **兩種分段是刻意並存的，而第一次見面沒有人講過**（F117 G2）。
        # 上面那三段是**引擎在做什麼**（影像 → 數字 → 判定），而卡片庫分成
        # 七群是**使用者要找什麼**（我現在要載入、要挑區域、還是要量）。
        # 走查記的是「兩邊的段數對不上」—— 對不上是對的，它們回答的是兩個
        # 不同的問題；缺的只是一句話。
        self.axes = QLabel(axes_note(), self)
        self.axes.setWordWrap(True)
        self.axes.setStyleSheet("color:%s; font-size:%s;"
                                % (TOKENS["text_hint"], TOKENS["font_small"]))
        root.addWidget(self.axes)

        # **五個字怎麼串起來**（F117 D4）。它們在同一個畫面上同時出現，而在
        # 這一段之前沒有任何地方講過它們的關係 —— 而那正是第一次見面的人會
        # 卡住的地方。放在三段之後：先知道這個工具在做什麼，再學它的詞。
        self.glossary = QLabel(
            "  ·  ".join("<b>%s</b> %s" % (name, line)
                         for name, line in GLOSSARY), self)
        self.glossary.setWordWrap(True)
        self.glossary.setTextFormat(Qt.RichText)
        self.glossary.setStyleSheet("color:%s; font-size:%s;"
                                    % (TOKENS["text_secondary"],
                                       TOKENS["font_small"]))
        root.addWidget(self.glossary)

        root.addWidget(self._separator())

        # ---- 三顆真的會做事的鈕 ------------------------------------------
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_demo = QPushButton(strings.tr("Try it with sample data"), self)
        self.btn_demo.setObjectName("primary")
        self.btn_demo.setCursor(Qt.PointingHandCursor)
        self.btn_demo.setToolTip(
            "Generate synthetic data, load it, apply the die-to-die template and "
            "trial-run it — you land straight on a score histogram and a wall of "
            "thumbnails (none of your own files are touched)")
        self.btn_demo.setMinimumHeight(34)
        self.btn_demo.clicked.connect(self.click_demo)

        # 「我自己的**資料**」不是「我自己的 KLARF」（F11 Input-5）：四種輸入
        # 裡有兩種根本沒有 KLARF，而這顆鈕是第一次開 d4t 的人看到的第一條路。
        # 它仍然直接開 KLARF 那個對話框（最常見的那一種），另外三條在關掉這個
        # 視窗之後的空白狀態上一列一個。
        self.btn_open = QPushButton(strings.tr("Open my own data"), self)
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.setToolTip(
            "Close this window and pick your data - a KLARF, a folder of "
            "images, or one image; d4t works out which (Studio's “%s”)."
            % open_title())
        self.btn_open.setMinimumHeight(34)
        self.btn_open.clicked.connect(self.click_open)

        self.btn_library = QPushButton(strings.tr("Browse templates"), self)
        self.btn_library.setCursor(Qt.PointingHandCursor)
        self.btn_library.setToolTip("Open the template library — every entry is a complete, runnable pipeline")
        self.btn_library.setMinimumHeight(34)
        self.btn_library.clicked.connect(self.click_library)

        for b in (self.btn_demo, self.btn_open, self.btn_library):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            row.addWidget(b, 1)
        # 導覽是**第一次用的人看到的第一個畫面**，上面不能有按了撞牆的鈕。
        # 兩顆各看自己的旗標（F91 X4 拆開的 —— 它們的死法不一樣，見
        # `scope.SHOW_SAMPLE_DATA` 的說明）：範本庫 2026-09-08 回來了，
        # 範例資料 2026-09-09 跟著回來（`recipes/ebi-die-to-die.json`）。
        # 收起來的是入口不是能力 —— ``click_demo`` / ``click_library`` 與訊號
        # 一行都沒動，測試照樣直接呼叫得到。
        self.btn_demo.setVisible(bool(scope.SHOW_SAMPLE_DATA))
        self.btn_library.setVisible(bool(scope.SHOW_TEMPLATE_LIBRARY))
        if not (scope.SHOW_SAMPLE_DATA and scope.SHOW_TEMPLATE_LIBRARY):
            # 少了幾顆之後，「開自己的資料」就是主要動作。
            self.btn_open.setObjectName("primary")
        root.addLayout(row)

        hint = QLabel(_footer_hint(), self)
        hint.setObjectName("paramHint")
        hint.setWordWrap(True)
        self.footer_hint = hint          # 這句話要跟看得到的鈕一致（有測試）
        root.addWidget(hint)

        root.addWidget(self._separator())

        # ---- 底列：不再顯示 / 快速參考卡 / 關閉 ----------------------------
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.chk_dont_show = QCheckBox(strings.tr("Do not show again"), self)
        self.chk_dont_show.setToolTip(
            "This window will not open on start-up any more; Help on the toolbar "
            "always brings it back")
        self.chk_dont_show.setChecked(welcome_disabled())
        self.chk_dont_show.toggled.connect(self._on_dont_show_toggled)
        bottom.addWidget(self.chk_dont_show)
        bottom.addStretch(1)

        self.quickref_path = quick_reference_pdf()
        self.btn_quickref = QPushButton(strings.tr("Quick reference card"), self)
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
                "No quick-reference PDF in docs/ yet — it ships with the "
                "offline installer.")
        else:
            self.btn_quickref.setToolTip("Open with the system PDF viewer: %s"
                                         % self.quickref_path.name)
        self.btn_quickref.clicked.connect(self.open_quick_reference)
        bottom.addWidget(self.btn_quickref)

        self.btn_close = QPushButton(strings.tr("Explore on my own"), self)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setToolTip("Close the tour and go straight to Studio")
        self.btn_close.clicked.connect(self.close)
        bottom.addWidget(self.btn_close)
        root.addLayout(bottom)
        apply_button_cursors(self)

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
    ``recipes/`` 丟一份新的 JSON，這裡就會自己多一列。

    ⚠ 「這份在做什麼」那一句就是 recipe JSON 的 ``description`` 欄位
    （`read_recipe_info` 讀它）。加一份新的 recipe 而沒有寫那一欄的話，
    使用者在這裡看到的是一個檔名 —— 而他要決定的正是「哪一份最接近我的層」。

    訊號：``recipe_chosen(path)``（雙擊或按「載入」）。

    大小與位置記得（F117 I16）：挑 recipe 的時候使用者常把它拉寬去讀右邊
    那段說明，而每次回到預設等於每次重做一遍。
    """

    #: 大小與位置存在 QSettings 的哪一格（F117 I16）。
    GEOMETRY_KEY = "recipe_library"

    def done(self, result: int) -> None:   # Qt hook
        """關掉時記住大小（F117 I16）。

        ⚠ **`done` 而不是 `closeEvent`**：`accept` / `reject` 兩條路都走這
        裡，而按 Esc 關掉的對話框不一定收得到 `closeEvent`。掛錯地方的症狀
        是「用滑鼠關掉會記得，按 Esc 關掉不會」—— 那種不一致使用者只會覺得
        它壞了。

        ⚠ **函式內 import**：`geometry` 讀這裡的 `app_settings`，兩邊在模組
        層互相 import 會炸。
        """
        from . import geometry

        geometry.remember(self, self.GEOMETRY_KEY)
        super().done(int(result))

    recipe_chosen = Signal(str)

    def __init__(self, directory: Any = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(strings.tr("Template library"))
        self.setModal(False)
        self.setMinimumSize(720, 420)
        fit_screen.relax_minimum(self)
        self.directory = Path(str(directory)) if directory is not None else RECIPES_DIR

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        head = QLabel("Pick the one closest to your layer, load it, then tune the "
                      "parameters — do not start from an empty pipeline.", self)
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
            "background:%s; border:%s solid %s; border-radius:%s;"
            " padding:10px;"
            % (TOKENS["bg_surface"], TOKENS["hairline"],
               TOKENS["border_default"], TOKENS["radius_md"]))
        body.addWidget(self.detail, 3)
        root.addLayout(body, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.path_label = QLabel("", self)
        self.path_label.setObjectName("paramHint")
        bottom.addWidget(self.path_label, 1)
        self.btn_load = QPushButton(strings.tr("Load"), self)
        self.btn_load.setObjectName("primary")
        self.btn_load.setCursor(Qt.PointingHandCursor)
        self.btn_load.setToolTip("Load this recipe into the Studio pipeline panel")
        self.btn_load.clicked.connect(self.load_selected)
        bottom.addWidget(self.btn_load)
        self.btn_close = QPushButton(strings.tr("Close"), self)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        bottom.addWidget(self.btn_close)
        root.addLayout(bottom)

        self._entries: List[Dict[str, Any]] = []
        self.reload()
        apply_button_cursors(self)

    # ---- 資料 -------------------------------------------------------------
    def reload(self) -> int:
        """重讀資料夾並重建清單；回傳有幾份 recipe。"""
        # F7-1：只列至少有一條「這個 build 跑得動」的 route 的 recipe
        # （純 rsem 的範本會被濾掉；雙 route 的照列，載進來會走 ebi_patch）。
        self._entries = [info for info in
                         (read_recipe_info(p)
                          for p in list_recipe_files(self.directory))
                         if recipe_is_supported(info)]
        self.list.clear()
        for info in self._entries:
            item = QListWidgetItem(self._item_text(info))
            item.setData(Qt.UserRole, info["path"])
            item.setToolTip(info["description"] or info["error"] or info["file"])
            if info["error"]:
                item.setToolTip("This file could not be read: %s" % info["error"])
            self.list.addItem(item)
        if self._entries:
            self.list.setCurrentRow(0)
        else:
            # **講出找過哪裡**：一句「沒有範本」答不出「那我要把檔案放哪」。
            self.detail.setText(
                "No recipe JSON in %s yet.\n\nDrop one in there (or use "
                "“Save recipe…” on a pipeline you like) and it shows up here."
                % self.directory)
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
        """清單上一列：**一句摘要在上、資料型別與步驟數在下**（F117 G3）。

        以前第一行是 ``recipe_id``（`ebi_die_to_die`）、第二行是
        ``route: ebi_patch`` —— 兩個都是 recipe JSON 的鍵，而使用者要決定的
        是「哪一份最接近我的層」。描述是他自己寫的那一句，所以它排第一。

        沒有描述的那一份退回檔名（**不是 `recipe_id`**）：他在檔案總管裡看到
        的就是那個字。
        """
        if info["error"]:
            return "%s\n(unreadable: %s)" % (info["file"], info["error"])
        head = _headline(info.get("description"))
        kinds = ", ".join(scope.kind_word(r) for r in info["routes"]) \
            or "(no route)"
        return "%s\n%s · %d steps" % (head or info["file"], kinds,
                                      int(info["n_steps"]))

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
            return "This file could not be read:\n%s" % info["error"]
        lines = [info["description"] or "(this recipe has no description)", ""]
        for route in info["routes"]:
            lines.append("• %s: %d steps"
                         % (scope.kind_word(route),
                            int(info["route_steps"].get(route, 0))))
        lines.append("")
        # ⚠ **走判定樹的 recipe 沒有分數表達式，而那不是「沒有判定」**
        # （F117 G3）。以前這裡寫 `score = (no score expression)`，讀起來像
        # 這一份不會判定 —— 而它是用另一種方式判定的。
        if info.get("has_tree"):
            n = int(info.get("n_classes") or 0)
            lines.append("Sorts with a decision tree on the canvas%s"
                         % (" (%d classes)" % n if n else ""))
        else:
            lines.append("score = %s"
                         % (info["expr"] or "(no score expression)"))
        # 門檻跟著 score 走 —— 走判定樹的那一份印它一樣會讓人以為判定是
        # 「跟一個數字比大小」（同上面那一行的理由）。
        if info["threshold"] is not None and not info.get("has_tree"):
            lines.append("threshold = %g (score >= threshold → bin 1)"
                         % float(info["threshold"]))
        if info["author"]:
            lines.append("Author: %s" % info["author"])
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

# 一個特徵名怎麼變成人看得懂的字 — 從 widgets.py 搬出來 2026-09-08 (U7).
"""特徵名 → 它是什麼、單位是什麼、畫出來長什麼樣；以及判定 chip。

``glv_median`` 這種名字是**分數表達式的變數名**（也是 CSV 的欄名），所以它
不能為了好看而改。這一份做的是另一件事：在畫面上**旁邊多說一句**，而原始
欄名永遠還在（`feature_html` 的第一行、懸停的第一行）。

U7 那一刀。這一份是**純搬移**：每一行都是原封搬過來的，一個字都沒有改。

⚠ `VerdictChip` 的意思走**三個通道**（U13／X7 2026-09-08，F119 2026-09-20）：
判定的名字（recipe 自己取的）排第一、``bin N`` 退成後面的補充，好壞那個詞
接在最後，顏色與框線樣式是另外兩條 —— 三條吃同一個 `outcome`，而那是**寫
recipe 的人自己標的**（以前是看 bin 的號碼猜，三份出貨的 recipe 全反了）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from ..core.algo import glv as algo_glv
from . import strings, theme
from .chips import metric_face
from .numbers import format_feature_value
from .theme import TOKENS

__all__ = [
    "feature_gloss", "feature_unit", "feature_html", "VerdictChip",
    "VARIANT_GLOSS", "_fmt_number",
]




# --------------------------------------------------------------------------- #
# 6. 特徵名／說明／單位 ＋ VerdictChip
# --------------------------------------------------------------------------- #
def _fmt_number(value: Any) -> str:
    """數值 → 好讀字串。

    ⚠ **F52 起它只是 `numbers.format_feature_value` 的別名。** 以前這裡是
    自己一份（整數捷徑 ＋ ``%.3f`` ＋極小值 ``%.3g``），而
    `gallery._fmt_score` 是**同一份抄第二次然後漂開的**。實測的下場：
    ``99.995`` 在結果表上是 ``100``、在這張單顆特徵表上是 ``99.995`` ——
    使用者在 Results 看到一顆是 100，點進去變成 99.995，會以為自己點錯顆。

    名字留著是因為這個檔案裡有好幾個呼叫端（門檻標籤、特徵表）。
    """
    return format_feature_value(value)

#: 絕對量 / 相對量 —— :func:`feature_gloss` 回的第一個值。
FEATURE_ABSOLUTE = "absolute"
FEATURE_RELATIVE = "relative"


def feature_gloss(name: str, about: Optional[Dict[str, str]] = None,
                  spec: Optional[Any] = None) -> Tuple[str, str]:
    """一個特徵名 →（絕對量／相對量／空的, 一句話說它是什麼）。

    F18 補課第三輪（使用者 2026-08-21）：「我認為 feature 中絕對量的跟相對量
    的還是要分類好（不然不清楚命名規則會很痛苦），或者 Feature 的功能 UI
    顯示需要再優化」。

    PR-3 起吃 ``spec``（`FeatureSpec` —— 名字誕生處宣告的身分）：相對／絕對
    看 ``family``、統計量是 ``metric``、cmp 比的是哪個統計量在 ``stat``。
    **沒有 spec 就留白，不猜** —— 以前這裡拆 ``cmp_``/``glv_`` 字串用最長
    比對把 metric 猜回來，而那正是「拆特徵字串猜語意」禁令要清掉的一處。

    說明的內容不是在這裡發明的：絕對量走 `algo.glv.metric_formula`（公式的
    家），相對量走 :data:`METRIC_GROUPS` 的短標籤（膠囊的家）。抄第二份出來
    的那一份一定會漂（`CLAUDE.md` §0）。

    ``about`` 是「跟誰比」——名字裡沒有那件事（``epi_cmp_delta_median`` 不講
    mg），所以由呼叫端從引擎的 ``meta["compares"]`` 帶進來。
    """
    if spec is None:
        return "", ""
    text = str(name or "")
    ref = str((about or {}).get(text, "") or "")
    family = str(getattr(spec, "family", "") or "")
    if family == "cmp":
        label = metric_face(spec.metric)[1] if spec.metric \
            else (spec.base or text)
        body = label if not spec.stat else "%s of %s" % (label, spec.stat)
        return FEATURE_RELATIVE, _with_variant(
            spec, body + " vs %s" % (ref or "the reference"))
    if family == "glv":
        mid = str(spec.metric or spec.base or "")
        # **先問卡片**（F76）：`metric_formula` 只認得統計量，而這一族裡有
        # 一整批不是統計量（`glv_worst_*` / `glv_boxes*`）—— 它們以前落到
        # 最後那個 `metric_face`，印出來就是自己的 id。
        body = _card_says(spec) or algo_glv.metric_formula(mid)
        if body == "—":
            body = metric_face(mid)[1]
        return FEATURE_ABSOLUTE, _with_variant(spec, body)
    # 其餘的一句話**由卡片自己說**（`Step.FEATURE_HELP`，2026-09-01）。
    # 在這裡補一張表是最快的做法，也是最錯的：那句話會跟卡片本人的說明漂開，
    # 而漂開的時候畫面上看起來完全正常（`CLAUDE.md` §0）。
    said = _card_says(spec)
    return (FEATURE_ABSOLUTE, _with_variant(spec, said)) if said else ("", "")


#: 變體怎麼**改寫**那個量的說明（F76，2026-09-02）。``%s`` 是那個量自己的
#: 那一句（`metric_formula` 或卡片的 `FEATURE_HELP`）。
#:
#: 為什麼一定要有這一層：`feature_gloss` 以前只讀 `spec.metric`，於是
#: ``glv_median_typical`` / ``_outlier`` / ``_outlier_box`` / ``_worst``
#: 四列的說明**一字不差**（都寫 ``median(gray)``）—— 而 ``_outlier_box``
#: 的值根本不是灰階，它是一個框號。實測：出貨的 `rsem-worst-box` 上有 97 個
#: 特徵的說明跟別的特徵完全相同。
#:
#: ⚠ **`_outlier` 跟 `_worst` 常常不是同一格**（實測 24 顆：judge 那個量
#: 24/24 相同，其他量只有 2–5/24）。使用者 2026-09-02 的原話是「反而這樣會
#: 誤導別人以為他是最 worst 的」—— 所以這兩句話要**明講它們在挑哪一格**，
#: 那是名字上唯一沒有的資訊。
VARIANT_GLOSS = {
    "typical": "%s - the middle one across all the boxes",
    "outlier": "%s - on the box furthest out on this statistic alone, "
               "which is often not the one the judge picked",
    "outlier_box": "which box was furthest out on this statistic alone "
                   "(%s)",
    "worst": "%s - on the box the judge picked as the odd one out",
    "nm": "%s, in nanometres",
    "nm2": "%s, in square nanometres",
    "raw": "%s, before it was scaled against the batch",
    "rescued": "%s - kept under this name because a later card wrote over it",
    # ---- 均勻度（F85）：這一群框「之間」的量 ----------------------------
    # ⚠ 這五句話都要明講**它們講的是整群，不是某一格** —— 名字上唯一沒有的
    # 資訊正是那個（`glv_median_cv_pct` 讀起來很像又一個灰階值）。
    # 兩個斜率**必須把 100 說出來**：數字被換成每 px 的版本時，它不會變成
    # 錯的，它會變成 0.00x —— 而那讀起來是「很平」。
    "range": "%s - the gap between the brightest box and the darkest one",
    "range_pct": "%s - that same gap, as a percentage of the average",
    "cv_pct": "%s - how spread out the boxes are, as a percentage of the "
              "average; 0 means every box reads the same",
    "slope_x": "%s - how much it changes from left to right, per 100 pixels; "
               "0 means no tilt",
    "slope_y": "%s - how much it changes from top to bottom, per 100 pixels; "
               "0 means no tilt",
}


def _with_variant(spec: Any, body: str) -> str:
    """把變體那句話套上去（沒有變體、或不認得的變體就原樣回）。"""
    pattern = VARIANT_GLOSS.get(str(getattr(spec, "variant", "") or ""))
    return (pattern % body) if (pattern and body) else body


def feature_unit(spec: Any) -> str:
    """這個數字的單位 —— **問卡片，不猜**（F76，2026-09-02）。

    先看變體（`step.VARIANT_UNITS`：``_outlier_box`` 的值是框號，不是那個
    量），再看那張卡的 `Step.feature_units`。查不到就**留白** —— 一個猜錯的
    單位比沒有單位糟得多（同 `feature_gloss` 的退化原則）。
    """
    if spec is None:
        return ""
    from ..core.pipeline.step import VARIANT_UNITS

    var = str(getattr(spec, "variant", "") or "")
    if var in VARIANT_UNITS:
        return VARIANT_UNITS[var]
    try:
        from ..core.pipeline import get_step

        table = get_step(str(getattr(spec, "card", "") or "")).feature_units()
    except Exception:  # 顯示用，不能擋畫面
        return ""
    for key in (getattr(spec, "metric", ""), getattr(spec, "base", ""),
                getattr(spec, "name", "")):
        got = str(table.get(str(key or ""), "") or "")
        if got:
            return got
    return ""


def _card_says(spec: Any) -> str:
    """``spec`` 的那張卡怎麼形容這個數字（查不到就空字串）。"""
    try:
        from ..core.pipeline import get_step

        table = get_step(str(getattr(spec, "card", "") or "")).feature_help()
    except Exception:  # 顯示用，不能擋畫面
        return ""
    for key in (getattr(spec, "base", ""), getattr(spec, "metric", ""),
                getattr(spec, "name", "")):
        got = str(table.get(str(key or ""), "") or "")
        if got:
            return got
    return ""


#: ⚠ 這裡以前有一張 `_ABS_GLOSS`（`glv_pixels` / `glv_ok` 兩條）。
#: **F76 刪掉了** —— 那兩句話現在住在 GLV 卡的 `FEATURE_HELP` 上，跟同一族
#: 其他十二句在一起。留兩份的話它們會漂，而漂開的時候畫面上看起來完全正常。


#: 一個特徵名拆好之後，畫在畫面上要用哪些角色（F37 A4，2026-08-26）。
#:
#: 使用者 2026-08-26：「值可否用上下標　更清楚　配合顏色」。
#:
#: 三個角色，而**每一個都對應名字裡真的存在的一段**（拆解由卡片給，見
#: `Step.feature_parts`）：
#:
#: =========  =========  ==================================================
#: 主體       正常大小   ``glv_median`` —— 家族 tag ＋ 統計量
#: 區域       **上標**   ``epi`` —— 顏色取自 `theme.region_hex`
#: 影像流     **下標**   ``test``
#: =========  =========  ==================================================
#:
#: 為什麼區域是上標而不是下標：一份 recipe 常常只有一條流、卻有好幾個區域，
#: 所以區域是**比較常出現、也比較需要一眼分辨**的那一個，而上標的位置比下標
#: 顯眼。挑一個然後從此不變 —— 兩種都成立，會出錯的是兩邊各挑一個。
#:
#: ⚠ **顏色不是在這裡發明的。** `theme.region_hex(index)` 同時是影像上那個
#: ROI 框的顏色與畫布上區域埠的顏色（`MultiSourceStep.CURRENT_REGION_INDEX`
#: 用同一個序）—— 三個地方同一個顏色，而來源只有一份。各自挑一份的話，
#: "top,bot" 在一邊是 0/1、在另一邊是 1/0，而**顏色指錯區域比沒有顏色糟得多**。
FEATURE_SUP = "region"
FEATURE_SUB = "stream"


def feature_html(name: str, parts: Optional[Dict[str, Any]] = None) -> str:
    """一個特徵名 → 要畫的那一小段 HTML（拆不出來就是原樣的純文字）。

    純函式，沒有 Qt —— 所以「畫成什麼樣」測得起來，不必開一個視窗。
    """
    text = _escape(str(name or ""))
    got = dict(parts or {})
    base = str(got.get("base", "") or "")
    if not base:
        return text
    out = [_escape(base)]
    region = str(got.get(FEATURE_SUP, "") or "")
    if region:
        colour = theme.region_hex(int(got.get("region_index", 0) or 0))
        out.append('<sup style="color:%s"><b>%s</b></sup>'
                   % (colour, _escape(region)))
    stream = str(got.get(FEATURE_SUB, "") or "")
    if stream:
        out.append('<sub style="color:%s">%s</sub>'
                   % (TOKENS["text_hint"], _escape(stream)))
    own = str(got.get("own", "") or "")
    if own:
        # 使用者自己取的名字**不縮小也不上下標**：它是他打的字，不是軟體
        # 推出來的一段 —— 兩者在畫面上要分得出來。
        out.append(' <span style="color:%s">%s</span>'
                   % (TOKENS["text_secondary"], _escape(own)))
    return "".join(out)


def _escape(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


# ⚠ **`_FeatureNameDelegate` 與 `FeatureTable` 2026-09-02 刪掉了**（F76）。
#
# 那張「特徵 / 它是什麼 / 數值」三欄表被 `ui/feature_panel.FeaturePanel` 取代
# （四胞胎橫過來、卡 › 區域 分段），而它自 F76 刀 4 起就沒有任何呼叫端。
# 使用者 2026-09-02 定調刪掉 —— `CLAUDE.md` §5 那張價目表的「刪掉」那一格，
# 而這一次代價量過：零個生產呼叫端、零份 recipe、零個黃金值。
#
# **留下來的是它身上真正有價值的那幾支**，它們現在服務新面板：
#
#   `feature_html` ＋ `FEATURE_SUP` / `FEATURE_SUB` —— 名字的上下標與區域色
#       （F37 A4，使用者「值可否用上下標　更清楚　配合顏色」）。新面板的
#       flat 列直接把它餵進 QLabel 的 rich text，delegate 因此不必跟著搬。
#   `feature_gloss` / `feature_unit` —— 「它是什麼」與單位。
#   `_fmt_number` —— 門檻標籤還在用。
#
# 那張表帶著的四條不變量搬到 `tests/test_ui_feature_panel.py`：標題不是特徵、
# 收合只收自己那一組、結論永遠看得到（score 現在跟 bin 同一行）、
# **沒人認領的特徵仍然要出現**（最後這一條在搬的過程裡救回一個真的 bug）。


#: tone → 框線的樣式。**顏色以外的第二個通道**（U13）。
#:
#: 紅綠對約 8% 的男性是不可分辨的，而這張 chip 以前把「好消息／壞消息」整個
#: 押在色相上。字是主要的通道（見 :meth:`VerdictChip.set_verdict`），這一張表
#: 是給掃視用的第二個：**實線 = 有結論、虛線 = 還沒有**，而壞消息的框更粗。
#:
#: ⚠ 為什麼不用一個圖示字元（`●` / `○`）：那兩個在 Geometric Shapes 區，廠內
#: 那台 Windows 的 Segoe UI 要退到 Segoe UI Symbol 才畫得出來
#: （`tests/test_ui_f7_23_buttons.py` 那條規則的同一個理由）—— 退字型的下場是
#: 大小與 baseline 都不一樣，最壞是豆腐框。框線是 QSS 畫的，跟字型無關。
_TONE_BORDER = {
    "good": ("solid", 1),
    "bad": ("solid", 3),
    "neutral": ("dashed", 1),
}

#: 好壞在**字**上叫什麼（U13 的第二個通道）。中性與「還沒說」不加字 ——
#: 它們本來就沒有主張，硬塞一個詞會讓使用者以為系統說了什麼。
#:
#: 為什麼是 ``review`` 而不是 ``bad``：廠內對「這一顆要人看一眼」講的就是
#: review（review SEM、人工複判），而 ``bad`` 讀起來像在罵那片晶圓。
_TONE_WORD = {"good": "good", "bad": "review"}


def verdict_words(decide: Any, bin_value: Any) -> Tuple[str, str]:
    """``decide`` ＋ bin → ``(名字, 好壞)``。**兩張表在同一個地方查。**

    `bin_labels()` 與 `bin_outcomes()` 是同一條路的兩半（那一行字，與那一行
    字的顏色），分開查的那天它們會來自不同的葉子 —— 而畫面上看不出來。

    ``decide`` 是 None（走舊的 `score` 路）就兩個都空。
    """
    if decide is None or bin_value is None:
        return ("", "")
    try:
        key = int(bin_value)
    except (TypeError, ValueError):
        return ("", "")
    return (str(decide.bin_labels().get(key, "") or ""),
            str(decide.bin_outcomes().get(key, "") or ""))


class VerdictChip(QLabel):
    """判定 chip：**這一顆被判成什麼** —— 名字排第一，``bin N`` 是補充。

    為什麼名字要排第一（X7，2026-09-08）
    ------------------------------------
    廠內講的是 real / nuisance 或某個 class name，不是 ``bin 1``。而那些名字
    **本來就存得下來**（`Rule.label` / `TreeLeaf.label` / `otherwise_label`
    從 F21-D／F24 起就在），只是沒有人拿去畫。所以這不是新功能，是把一條已經
    鋪好的路接上。

    為什麼顏色不能是唯一的通道（U13，2026-09-08）
    ---------------------------------------------
    紅綠對色覺缺陷者不可分辨（男性約 8%），所以「好消息還是壞消息」走**三個
    通道**：顏色、**字**（:data:`_TONE_WORD`）、框線樣式
    （:data:`_TONE_BORDER`）。三個吃同一個來源，所以不會各說各話。

    顏色從哪裡來（F119，2026-09-20）
    --------------------------------
    ⚠ **以前是看 bin 的號碼**（``bin 1`` 綠、``bin 0`` 紅），而號碼本身沒有
    意義 —— 意義是寫 recipe 的人給的。量出來的下場：三份出貨的 recipe
    **全部反了**（``nothing stands out`` 是紅的、``a spot stands out`` 是
    綠的）。現在顏色來自 `DecideSpec.bin_outcomes()`，也就是**寫 recipe 的
    人自己標的**（F117 D2）。

    ⚠ **沒標就是中性灰，不猜。** 一個很有把握的錯顏色比沒有顏色糟得多 ——
    使用者會相信它。

    ⚠ 這一輪拿掉了 `is_real_style`（U13 當初那個紅綠對調的旗標）：它**從來
    沒有呼叫端**，而它要解的「同一個綠色在兩份 recipe 裡意思相反」在
    `outcome` 之後從根上不存在了 —— 綠色現在永遠是「寫這份 recipe 的人說
    這是好消息」。三個通道一個都沒有少。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(112)
        self.setMinimumHeight(28)
        self._bin: Optional[int] = None
        self.set_verdict(None)

    @staticmethod
    def _wording(b: Optional[int], label: str, outcome: str = "") -> str:
        """chip 上那一行字：``<名字> · bin N`` ＋ 好壞那個詞（有標才加）。

        名字排第一是 X7：recipe 取了名字就用那個名字（使用者自己的字彙），
        沒取名才退回門檻關係 —— 那時候 ``≥ threshold`` 是**真的**唯一知道的
        事，不該假裝知道更多。

        ⚠ **好壞那個詞是 U13 的第二個通道，所以它跟著 `outcome` 走而不是跟著
        名字走**：``a spot stands out`` 這個名字本身沒有說那是好事還是壞事，
        而顏色說了 —— 顏色說了什麼，字就要說得出同一件事，不然色覺缺陷者手上
        只剩一條看不見的通道。中性與「還沒說」不加字（它們本來就沒有主張）。
        """
        if b is None:
            return "—"
        named = str(label or "").strip()
        if named:
            head = "%s · bin %d" % (named, b)
        elif b == 1:
            head = "bin 1 · ≥ threshold"
        elif b == 0:
            head = "bin 0 · < threshold"
        else:
            head = "bin %d" % b
        word = _TONE_WORD.get(str(outcome or ""), "")
        return "%s · %s" % (head, strings.tr(word)) if word else head

    def set_verdict(self, bin_value: Optional[Any] = None,
                    label: str = "", outcome: str = "") -> None:
        """``outcome`` 來自 `DecideSpec.bin_outcomes()` —— **沒標就是中性**。

        ⚠ 認不得的值也是中性：這一格不猜（同 `bin_outcomes` 丟掉打錯的值）。
        """
        try:
            b = None if bin_value is None else int(bin_value)
        except (TypeError, ValueError):
            b = None
        self._bin = b
        tone = str(outcome or "")
        if b is None or tone not in _TONE_BORDER:
            tone = "neutral"
        text = self._wording(b, label, outcome)
        bg = TOKENS["chip_%s_bg" % tone]
        fg = TOKENS["chip_%s_text" % tone]
        border = TOKENS["chip_%s_border" % tone]
        style, width = _TONE_BORDER[tone]
        self.setText(text)
        self.setProperty("tone", tone)
        self.setToolTip(text)
        self.setAccessibleName("Verdict: %s" % text)
        # **這一格不准被擠到把名字截掉**（F99 P0-4）。`setMinimumWidth(112)`
        # 的意思是「版面可以把我縮到 112」——於是「more than one box is off」
        # 在窄的那一列被從左邊切成「:han one box is off」，而那是整份判定裡
        # 最該一眼看到的一句。最小寬度跟著字走；擠不下的是旁邊那條路徑
        # （它有 tooltip 與省略號），不是這一格。
        self.setMinimumWidth(max(
            112, self.fontMetrics().horizontalAdvance(text) + 2 * 12 + 2 * 2))
        self.setStyleSheet(
            "background:%s; color:%s; border:%dpx %s %s;"
            " border-radius:%s; padding:4px 12px; font-weight:700;"
            % (bg, fg, width, style, border, TOKENS["radius_md"]))

    def verdict(self) -> Optional[int]:
        return self._bin

    def tone(self) -> str:
        return str(self.property("tone"))

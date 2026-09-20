# 參數表單 — 從 widgets.py 搬出來 2026-09-08 (U7).
"""``ParamForm`` —— 由 ``Step.describe()`` **自動生成**的參數表單。

這是整個專案賣點的執行機構：**加一張卡，UI 與引擎零修改**。卡片宣告
`ParamSpec`（型別、`min`/`max`、`help`、`show_when`），這裡把它變成一列一列
可以動的東西 —— 而卡片庫、畫布、引擎一行都不用改。

由此而來的幾條規矩（改這一支之前先讀）：

* **每個參數的白話 `help` 一定要看得到**（推廣鐵則）。
* **把 `min`/`max` 填好，滑桿是免費的**（F7-8）。
* **`image_key` / `region_key` 那幾格是唯讀的**（F9-6 / F12）：來源只在畫布上
  拉線決定，這裡只顯示現在接的是什麼。
* **`show_when` 是顯示規則不是驗證規則**：藏起來的參數照樣有預設值，卡片自己
  要保證用不到的參數不影響結果（`test_card_invariants` 的 I9 守著）。

一列一列的編輯器住在 `ui/fields.py`，膠囊住在 `ui/chips.py` —— 這一支只負責
**排它們**。U7 那一刀。

這一份是**純搬移**：每一行都是原封搬過來的，一個字都沒有改。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QPushButton, QSlider, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from . import strings
from . import theme
from .chips import ChoiceChips, MetricChips, MetricPick, _ChipFlow, _ChoiceChip
from .fields import (
    CellRoisField, ChannelMapField, ChartSpecField, ChartStyleField,
    CurveField, MultiChoicePicker, TemplateField, _HintLabel, _ParamRow,
    _float_decimals, _safe_float, _safe_int,
)
from .icons import apply_button_cursors

__all__ = ["ParamForm", "split_labelled", "FEATURE_LABEL_SEP"]



#: 「數字 → 誰算的」那份清單的分隔（跟 `viewmodel.ViewModel.FEATURE_LABEL_SEP`
#: 是同一個字）。**拆開的規矩只有這一份** —— 抄第二份出來的那份會漂。
FEATURE_LABEL_SEP = "\t"


def split_labelled(item: Any) -> "tuple":
    """``"cd_median\tCD"`` → ``("cd_median", "CD")``；沒有標籤就回空字串。

    前半是**要插進算式的字**，後半只是給人看的 —— 插錯半邊的話，使用者會得到
    一個永遠指不到的變數名，而錯誤要等跑起來才出現。
    """
    text = str(item or "")
    name, _sep, label = text.partition(FEATURE_LABEL_SEP)
    return name.strip(), label.strip()


class ParamForm(QWidget):
    """由 ``Step.describe()`` 的 ParamSpec dict 自動長出來的參數表單。

    ``set_step(describe, current_params, stream_choices)`` 一次重建整張表；
    使用者改動任何欄位 -> ``param_edited(name, value)``（值已 coerce 成該型別）。
    上層驗證失敗時呼叫 ``show_error(name, msg)`` 把那一列的說明變紅字。
    """

    param_edited = Signal(str, object)
    #: 「這個參數的值要用別的方式產生」（目前只有 template）。表單不知道那是
    #: 什麼對話框 —— 它只負責把請求送上去，由 Studio 決定要開什麼。
    action_requested = Signal(str)
    #: 使用者在一格接線插槽上挑了一個上游的區域／影像流：``(參數名, 名字)``。
    #: **這裡不改任何東西** —— `StudioWindow` 接到之後走跟畫布拉線同一條路
    #: （F68；線仍然是唯一的儲存）。
    wire_requested = Signal(str, str)
    #: 「在畫布上指給我看」：``(參數名,)``。
    wire_show_requested = Signal(str)
    #: **入口卡的「資料從哪來」**（F14-1）：按下去要開檔案對話框。
    #: 同樣地，表單不知道那是哪一種來源 —— 它送出去，Studio 決定開什麼。
    source_requested = Signal()
    #: 「我要量什麼」三選（PR-2 2a）：使用者按了哪個 preset 的 id。
    #: 表單不知道 preset 會動什麼 —— 動線動格的腦袋在 model。
    intent_chosen = Signal(str)

    _EMPTY_TEXT = "(Pick a card from the library, or select a step in the pipeline)"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._rows: Dict[str, _ParamRow] = {}
        #: 目前這批資料**一顆有幾張圖**（0 = 沒有資料）。只有 `channel_map` 的
        #: 編輯器用得到它 —— 但它是「資料的事實」而不是「這張卡的參數」，
        #: 所以放在表單上（一份資料一次）而不是塞進 `set_step` 的簽章。
        self._image_count = 0
        #: 目前掛上的 GLAS 匯出**有幾層**（0 = 沒掛）。`channel_map` 的
        #: `row_kind="labels"` 靠它排列數 —— 使用者打開那一格時，第一個要知道
        #: 的是「這份匯出有哪幾層」，而那在掛上去的那一刻就知道了。
        self._label_count = 0
        #: 這張卡吃進來的那條流的灰階分布（墊在曲線後面，見 `set_histogram`）。
        self._hist: List[float] = []
        #: 小標題：``section 名 -> [QLabel]`` 與 ``參數名 -> section 名``。
        #: 整組都被 ``show_when`` 藏起來時，標題也要跟著不見 —— 一個底下什麼
        #: 都沒有的標題比沒有標題更讓人以為畫面壞了。
        self._sections: Dict[str, List[QWidget]] = {}
        self._section_of: Dict[str, str] = {}
        #: 標了 ``advanced`` 的那幾列（預設收起來）。
        self._advanced: set = set()
        #: 目前這張卡每個參數的值 —— ``show_when`` 要靠它判斷哪幾列該在。
        self._values: Dict[str, Any] = {}
        #: 執行期才知道的選單（F15-2）：``{RUNTIME_CHOICES 的鍵: [選項]}``。
        self._dynamic: Dict[str, List[str]] = {}
        #: 上游定義了哪些具名區域（F11 Region-1）。
        self._regions: List[str] = []
        #: 插槽選單的內容（F68）：``{"region": [...], "image": [...]}``。
        self._wiring: Dict[str, List[str]] = {}
        self._describe: Optional[Dict[str, Any]] = None
        self._building = False
        #: 進階參數收起來了嗎（**追明確狀態**，不問 widget —— docs/PITFALLS.md）。
        #: 換一張卡就收回去：上一張卡展開過不代表這一張也要。
        self._advanced_open = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)          # 8px 節奏（F8-UI）

        self._title = QLabel("")
        self._title.setObjectName("paramTitle")
        # 卡片自己的一句話。收成一行（放不下就 ``像這樣…``）、全文住 tooltip
        # —— 跟參數列同一個決定（2026-08-14）：說明是查閱用的，不佔版面。
        # **兩行**（F117 B3）：一行放不下一句卡片說明是常態，而一行的省略號
        # 看不出後面還有多少。全文照舊在 tooltip（說明是查閱用的，不佔版面）。
        self._step_help = _HintLabel("", max_lines=2)
        self._step_help.setObjectName("paramStepHelp")
        outer.addWidget(self._title)
        outer.addWidget(self._step_help)

        # 「這張卡的資料從哪來」（F14-1，使用者定調：工具列那幾顆 Open
        # 「會混淆」）。入口長在**讀那份資料的那張卡上** —— 以前它在工具列，
        # 而畫布上那張 Load 卡完全不會說它讀的是哪個檔案：同一件事兩個地方，
        # 而畫布是說謊的那一個。
        self._source_row = QWidget(self)
        self._source_row.setObjectName("sourceRow")
        srow = QHBoxLayout(self._source_row)
        srow.setContentsMargins(2, 0, 8, 0)
        srow.setSpacing(8)
        self._source_btn = QPushButton("", self._source_row)
        self._source_btn.setObjectName("primary")
        self._source_btn.setCursor(Qt.PointingHandCursor)
        self._source_btn.clicked.connect(self.source_requested.emit)
        self._source_note = QLabel("", self._source_row)
        self._source_note.setObjectName("paramHint")
        self._source_note.setWordWrap(True)
        srow.addWidget(self._source_btn)
        srow.addWidget(self._source_note, 1)
        self._source_shown = False
        self._source_row.setVisible(False)
        outer.addWidget(self._source_row)

        # 「我要量什麼」三選（PR-2 2a；目前只有 GLV 用）。跟 `_source_row`
        # 同一個位置學（scroll 區上方 —— 意圖在參數之前）。**preset 不是
        # 參數**：這裡只畫鈕、發 id，動線動格的腦袋在 `RecipeModel
        # .apply_glv_intent`。表單保持不認識 model。
        self._intent_row = QWidget(self)
        self._intent_row.setObjectName("intentRow")
        irow = QVBoxLayout(self._intent_row)
        # 上緣留白：卡片那句說明的下緣與這一排的標題（14px/700）之間原本只有
        # 版面的 8px，兩行字擠在一起（F68 截圖上看得到）。
        irow.setContentsMargins(2, 6, 8, 4)
        irow.setSpacing(2)
        self._intent_title = QLabel("", self._intent_row)
        self._intent_title.setObjectName("paramTitle")
        irow.addWidget(self._intent_title)
        # **會換行的一排**（F100 v2）。以前是 QHBoxLayout：三顆固定寬度的膠囊
        # 把設定區的最小寬度撐到 376 px，而那正是 1366 上視窗裝不下的最後一根
        # 稻草（設定區、儀表、影像三欄的最小寬度加起來 1,395）。`_ChipFlow`
        # 的最小寬度是最寬的那一顆，塞不下就折到下一行 —— 跟 `metric_chips`
        # 那一排同一個元件。
        self._intent_btns: Dict[str, "_ChoiceChip"] = {}
        self._intent_flow = _ChipFlow(self._intent_row)
        irow.addWidget(self._intent_flow)
        self._intent_note = QLabel("", self._intent_row)
        self._intent_note.setObjectName("paramHint")
        self._intent_note.setWordWrap(True)
        irow.addWidget(self._intent_note)
        self._intent_shown = False           # 追明確狀態（PITFALLS：isVisible
        self._intent_row.setVisible(False)   # 在視窗 show 之前恆為 False）
        outer.addWidget(self._intent_row)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._host = QWidget()
        self._form = QVBoxLayout(self._host)
        self._form.setContentsMargins(2, 2, 8, 2)
        self._form.setSpacing(2)
        self._placeholder = QLabel(self._EMPTY_TEXT)
        self._placeholder.setObjectName("placeholder")
        self._placeholder.setWordWrap(True)
        self._form.addWidget(self._placeholder)
        # 「還有幾格」的入口。放在**進階那幾列的上面**（插在它們之前），
        # 這樣按下去展開的東西就在按鈕底下 —— 不必回頭找。
        self._advanced_btn = QPushButton("", self._host)
        self._advanced_btn.setObjectName("advancedToggle")
        self._advanced_btn.setCursor(Qt.PointingHandCursor)
        self._advanced_btn.setVisible(False)
        self._advanced_btn.clicked.connect(self.toggle_advanced)
        self._form.addWidget(self._advanced_btn)
        self._form.addStretch(1)
        self._scroll.setWidget(self._host)
        outer.addWidget(self._scroll, 1)

        self.set_step(None, {}, [])

    # -- public API --------------------------------------------------------
    def set_source_action(self, label: str = "", note: str = "",
                          tooltip: str = "") -> None:
        """入口卡上那一排「資料從哪來」。``label=""`` = 這張卡沒有這一排。

        note 講的是**現在載的是什麼**（`LOT_SYN.001 · 12 defects`）——
        鈕本身只說得出「可以換一份」，而使用者第一個要確認的是「我現在看的
        是哪一份」。
        """
        label = str(label or "")
        self._source_btn.setText(label)
        self._source_btn.setToolTip(str(tooltip or ""))
        self._source_note.setText(str(note or ""))
        # **追明確狀態**：`isVisible()` 在視窗 show 之前恆為 False，
        # 那個坑這個 repo 踩過（見 docs/PITFALLS.md）。
        self._source_shown = bool(label)
        self._source_row.setVisible(self._source_shown)

    def has_source_action(self) -> bool:
        """這張卡有沒有那一排「資料從哪來」。"""
        return bool(getattr(self, "_source_shown", False))

    def set_intent_row(self, title: str = "",
                       options: Sequence[Tuple[str, str, str]] = (),
                       current_id: str = "", note: str = "",
                       enabled: bool = True) -> None:
        """卡最上面的「我要量什麼」三選（PR-2 2a）。``title=""`` = 沒有這排。

        ``options`` 是 ``(id, 顯示字, 一句話, 圖示名)``；``current_id`` 對不上
        任何 id（例 ``"custom"``）就一顆都不勾 —— **不強制改**，自訂是一個合法
        的狀態。``enabled=False``（roi 還沒接線）時整排灰掉，note 講原因。

        **長相跟設定區的膠囊一模一樣**（F68 第三輪，使用者：「最上方的
        What do I want to measure 也是」）。它問的是同一種問題（幾個答案挑
        一個），長成另一種東西只會讓人以為那是別的機制 —— 而它其實正是底下
        那幾格的捷徑：三顆膠囊的圖就是它們會設成的那幾格的圖。
        """
        title = str(title or "")
        # 重建（選項是呼叫端給的，張數可能變）。
        #
        # ⚠ **`deleteLater()` 不夠，要先 `setParent(None)`。** 延遲刪除要等
        # 事件圈的 DeferredDelete 那一趟，而在那之前那幾顆**還在畫面上**，
        # 停在上一次版面給它們的位置 —— 這一排是有 stretch 的，面板一換寬度
        # 位置就變，於是舊的那幾顆變成疊在標題與新膠囊上的鬼影
        # （F68 第三輪 render 出來才看到；以前是 QPushButton 時同一個 bug，
        # 只是每次寬度都一樣所以完美重疊，看不出來）。
        for btn in self._intent_btns.values():
            self._intent_flow.remove(btn)
            btn.deleteLater()
        self._intent_btns = {}
        self._intent_title.setText(title)
        colour = theme.group_hex("measure")
        if title:
            for iid, label, help_line, icon in options:
                chip = _ChoiceChip(str(iid), str(icon), colour,
                                   str(iid) == str(current_id),
                                   self._intent_row, tip=str(help_line),
                                   label=str(label))
                chip.momentary = True          # 見 `_ChipBase.momentary`
                chip.setEnabled(bool(enabled))
                # **不是 toggle**：這一排是 preset，按下去等於「照這個意思
                # 把線接好」，而**再按一次不該把它取消**（取消要回到哪個狀態？
                # 沒有答案）。所以只接「按了」，勾不勾由 `current_id` 決定。
                chip.toggled.connect(
                    lambda _v, _on, i=str(iid): self.intent_chosen.emit(i))
                self._intent_flow.add(chip)
                self._intent_btns[str(iid)] = chip
        self._intent_note.setText(str(note or ""))
        self._intent_note.setVisible(bool(note))
        self._intent_shown = bool(title)
        self._intent_row.setVisible(self._intent_shown)

    def has_intent_row(self) -> bool:
        return bool(getattr(self, "_intent_shown", False))

    def intent_buttons(self) -> Dict[str, "_ChoiceChip"]:
        """測試 API：id → 那一顆膠囊。"""
        return dict(self._intent_btns)

    def source_button(self) -> QPushButton:
        """那顆鈕本身（訊息裡引到的名字要跟它一字不差 —— 有測試在擋）。"""
        return self._source_btn

    def set_image_count(self, n: int) -> None:
        """告訴表單「這批資料一顆有幾張圖」（F11）。

        `channel_map` 的表格會照它排列數 —— 使用者打開那一格時，第一個要知道的
        事實就是「有幾張」，而那個數字在資料載進來的那一刻就知道了。
        """
        n = max(0, int(n))
        if n == self._image_count:
            return
        self._image_count = n
        for row in self._rows.values():
            if isinstance(row.editor, ChannelMapField) \
                    and row.editor.row_kind() == "images":
                row.editor.set_min_rows(n)

    def set_label_count(self, n: int) -> None:
        """告訴表單「掛上的 GLAS 匯出有幾層」（F11 Region-3）。

        跟 :meth:`set_image_count` 同一個形狀，而且**兩者不可以互相蓋掉** ——
        一張 recipe 上可能同時有 `load_patch`（一列一張圖）與 `roi_reference`
        （一列一層）兩個 `channel_map`，用同一個數字去排兩者的列數，其中一邊
        一定是錯的。
        """
        n = max(0, int(n))
        if n == self._label_count:
            return
        self._label_count = n
        for row in self._rows.values():
            if isinstance(row.editor, ChannelMapField) \
                    and row.editor.row_kind() == "labels":
                row.editor.set_min_rows(n)

    def set_histogram(self, counts: Optional[Sequence[float]]) -> None:
        """這張卡吃進來的那條流長什麼樣（F11 Enhance-UI-C）。

        只有曲線欄位用得到它。跟 :meth:`set_image_count` 同一個形狀：這是
        **資料的事實**而不是這張卡的參數，所以放在表單上，不塞進 `set_step`
        的簽章（那會讓每一個呼叫端都得知道有這回事）。

        重建表單時會被清掉，所以上層在 `set_step` 之後要再餵一次 —— 那是
        Studio 的 `_refresh_curve_backdrop`。
        """
        self._hist = list(counts or [])
        for row in self._rows.values():
            if isinstance(row.editor, CurveField):
                row.editor.set_histogram(self._hist)

    def histogram(self) -> List[float]:
        return list(self._hist)

    def set_step(self, describe: Optional[Dict[str, Any]],
                 current_params: Optional[Dict[str, Any]] = None,
                 stream_choices: Optional[Sequence[str]] = None,
                 region_choices: Optional[Sequence[str]] = None,
                 dynamic_choices: Optional[Dict[str, Sequence[str]]] = None
                 ) -> None:
        """重建表單。``describe=None`` -> 顯示提示語（未選節點）。

        ``region_choices`` 是**上游定義了哪些具名區域**（F11 Region-1）。
        跟 ``stream_choices`` 同一個理由：那些名字程式知道，就不該讓使用者用打的。

        ``dynamic_choices`` 是**執行期才知道的選單**（F15-2），
        ``{RUNTIME_CHOICES 的鍵: [選項]}`` —— 現在掛了哪幾份第二 source、
        那一份的一顆有哪幾張圖、那一份的 KLARF 有哪些欄。同一個理由的第三次：
        程式知道的名字不該讓使用者用打的。Studio 是唯一知道答案的人，所以答案
        從這裡傳進來，而不是讓元件自己去問（`widgets` 不認得 `Dataset`）。
        """
        current_params = dict(current_params or {})
        # 換卡先把「我要量什麼」那排清掉（同 `set_source_action` 的規矩：
        # 這排是**這張卡**的，別張卡不出現）—— 要顯示的話 Studio 在
        # `set_step` 之後自己 set 回來。
        self.set_intent_row("")
        # **沒填的那幾格用預設值補上**（F30）。`show_when` 問的是「另外那一格
        # 現在是什麼」，而引擎那一邊看到的永遠是 `validate_params` 補完的一份
        # —— 這裡不補的話，一張剛加進來、參數還是空的卡，它的 `method` 在
        # 面板眼裡是空字串，於是**每一格都被判定為不該顯示**，整張卡看起來
        # 是空的。實測就是這樣發現的（四張 Region 卡收成一張之後）。
        for spec in (describe or {}).get("params") or []:
            current_params.setdefault(str(spec.get("name")), spec.get("default"))
        streams = [str(s) for s in (stream_choices or [])]
        self._regions = [str(r) for r in (region_choices or [])]
        self._dynamic = {str(k): [str(v) for v in (vals or [])]
                         for k, vals in dict(dynamic_choices or {}).items()}
        self._describe = describe
        self._building = True
        try:
            self._clear_rows()
            if not describe:
                self._title.setText("")
                self._title.setVisible(False)
                self._step_help.set_full_text("")
                self._step_help.setVisible(False)
                self._placeholder.setVisible(True)
                return
            self._title.setText(str(describe.get("label")
                                    or describe.get("key") or ""))
            self._title.setVisible(True)
            step_help = str(describe.get("help", ""))
            self._step_help.set_full_text(step_help)
            self._step_help.setToolTip(strings.tr(step_help))
            self._step_help.setVisible(bool(step_help))
            self._placeholder.setVisible(False)
            self._values = {}
            self._advanced = set()
            self._advanced_open = False
            section = None
            for spec in describe.get("params", []):
                name = str(spec.get("name", ""))
                # 小標題：換組的時候插一行（F8 第三輪）。參數清單的**順序**就是
                # 分組，所以卡片作者不必額外宣告什麼 —— 把同一組的排在一起就好。
                want = str(spec.get("section", "") or "")
                if want != section:
                    section = want
                    if want:
                        head = QLabel(want, self._host)
                        head.setObjectName("paramSection")
                        self._form.insertWidget(self._form.count() - 1, head)
                        self._sections.setdefault(want, []).append(head)
                value = current_params.get(name, spec.get("default"))
                self._values[name] = value
                editor = self._make_editor(spec, value, streams)
                editor.setToolTip(strings.tr(str(spec.get("help", ""))))
                row = _ParamRow(spec, editor, self._host)
                self._form.insertWidget(self._form.count() - 1, row)
                self._rows[name] = row
                if want:
                    self._section_of[name] = want
                if bool(spec.get("advanced")):
                    self._advanced.add(name)
        finally:
            self._building = False
        self._sync_visible_rows()
        self._sync_curve_override()
        # 參數列是**選到哪張卡才長出來的**，所以視窗建好時掃的那一次抓不到
        # 它們（模板鈕、曲線的兩顆…）。每次重建之後再掃一次。
        apply_button_cursors(self)

    def _sync_curve_override(self) -> None:
        """曲線一旦不是 y=x，就把 ``gamma`` 那列調淡並說明原因。

        規則本身寫在 ``steps/tone.py``（曲線接管 gamma）。這裡只是**讓它看得
        見** —— 不然使用者會拉了曲線又去動 gamma，然後發現 gamma 沒有反應。
        """
        curve_row = None
        for _name, row in self._rows.items():
            if str(row.spec.get("type", "")) == "curve":
                curve_row = row
                break
        if curve_row is None:
            return
        active = not curve_row.editor.is_identity()
        gamma = self._rows.get("gamma")
        if gamma is not None and not gamma.has_error():
            gamma.set_dimmed(active, "Not used while a custom curve is drawn.")

    def set_chart_series(self, series: Optional[Dict[str, Any]]) -> None:
        """把目前這一顆的均勻度資料交給 `chart_style` 那一列（F87 第七刀）。

        先例是 :meth:`set_histogram` —— 曲線欄位後面墊的那條分布也是這樣從
        引擎那一份餵過來的。**UI 不自己再算一份**：畫面上的預覽跟真的跑出來
        的不一樣，比沒有那個預覽更糟。
        """
        for row in self._rows.values():
            if isinstance(row.editor, ChartStyleField):
                row.editor.set_series(series)

    def set_chart_frame(self, frame: Any) -> None:
        """把這一顆的**長表**交給 `chart_spec` 那一列（散佈圖的選單）。

        同 :meth:`set_chart_series` 的理由：UI 不自己再攤一次 —— 畫面上那張
        圖跟寫出去的 `boxes.csv` 對不起來的話，沒有人看得出哪一份是對的。
        """
        for row in self._rows.values():
            if isinstance(row.editor, ChartSpecField):
                row.editor.set_frame(frame)

    def _chart_kinds(self) -> List[str]:
        """`chart_style` 的編輯器要開哪幾個分頁 —— **那張卡說的**。

        `Step.chart_kinds`（`Write charts` 是勾了哪幾張、`Write report`
        只有盒鬚圖）。卡片沒說就給全部：一個空的分頁區讀起來是「壞了」。
        沒勾的那幾張的覆寫不會因此消失（`ChartSettingsDialog` 原封不動帶回）。
        """
        from ..core.export.uniformity_charts import CHARTS
        from ..core.pipeline import get_step

        want: List[str] = []
        key = self.step_key()
        if key:
            try:
                want = [str(k) for k in
                        get_step(key).chart_kinds(dict(self._values))]
            except Exception:  # 顯示用，不能擋畫面
                want = []
        return [k for k in CHARTS if k in want] or list(CHARTS)

    def _chart_words(self) -> bool:
        """編輯器右半要不要「每張圖自己的字」—— 也是**那張卡說的**
        （`Step.chart_words`）。"""
        from ..core.pipeline import get_step

        key = self.step_key()
        if not key:
            return True
        try:
            return bool(getattr(get_step(key), "chart_words", True))
        except Exception:  # 顯示用，不能擋畫面
            return True

    def step_key(self) -> Optional[str]:
        return None if not self._describe else str(self._describe.get("key"))

    def advanced_open(self) -> bool:
        """進階那幾列現在攤開了嗎（**明確狀態**，不問 widget）。"""
        return bool(self._advanced_open)

    def advanced_names(self) -> List[str]:
        """這張卡有哪幾列是進階的。"""
        return [n for n in self._rows if n in self._advanced]

    def toggle_advanced(self) -> None:
        self.set_advanced_open(not self._advanced_open)

    def set_advanced_open(self, open_: bool) -> None:
        self._advanced_open = bool(open_)
        self._sync_visible_rows()

    def section_names(self) -> List[str]:
        """這張卡分了哪幾組小標題（依出現順序）。"""
        return list(self._sections)

    def section_visible(self, name: str) -> bool:
        """某一組的標題現在看不看得到（**追明確狀態**，不問 ``isVisible()`` ——
        視窗還沒 show 之前那個恆為 False，見 docs/PITFALLS.md）。"""
        heads = self._sections.get(str(name)) or []
        return bool(heads) and all(not h.isHidden() for h in heads)

    def param_names(self) -> List[str]:
        return list(self._rows)

    def row_visible(self, name: str) -> bool:
        """那一列現在看不看得到（**明確狀態**，不問 ``isVisible()``）。"""
        row = self._rows.get(str(name))
        return bool(row is not None and not row.isHidden())

    def values(self) -> Dict[str, Any]:
        """目前表單上每一格的值（收起來的那幾格照樣在 —— 這是顯示規則）。"""
        return dict(self._values)

    def advanced_button_text(self) -> str:
        return str(self._advanced_btn.text())

    def advanced_button_visible(self) -> bool:
        return bool(self._advanced_names_now())

    def _advanced_names_now(self) -> List[str]:
        """按下去會出現的那幾格 —— 被 ``show_when`` 排除的不算。"""
        return [n for n in self._rows
                if n in self._advanced and self._shown_by_rules(n)]

    def editor(self, name: str) -> Optional[QWidget]:
        row = self._rows.get(name)
        return None if row is None else row.editor

    def slider(self, name: str) -> Optional[QSlider]:
        """那一列的滑桿（沒有上下界的參數沒有滑桿，回 ``None``）。"""
        row = self._rows.get(name)
        return None if row is None else row.slider

    def hint_text(self, name: str) -> str:
        """那一列的說明**全文**。

        不是 ``hint.text()`` —— 收起來的時候那是切過的字（``像這樣…``），
        而問「說明寫了什麼」的人要的從來不是「畫面上現在放得下多少」。"""
        row = self._rows.get(name)
        return "" if row is None else row.hint.full_text()

    def show_error(self, name: str, msg: str) -> None:
        """把 ``name`` 那一列的說明換成紅色錯誤訊息。"""
        row = self._rows.get(name)
        if row is not None:
            row.set_error(msg)

    def clear_errors(self) -> None:
        """所有列還原成白話說明（灰字）。"""
        for row in self._rows.values():
            if row.has_error():
                row.set_error(None)

    def has_error(self, name: str) -> bool:
        row = self._rows.get(name)
        return bool(row is not None and row.has_error())

    # -- internals ---------------------------------------------------------
    def _clear_rows(self) -> None:
        for row in self._rows.values():
            self._form.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = {}
        for heads in self._sections.values():
            for head in heads:
                self._form.removeWidget(head)
                head.setParent(None)
                head.deleteLater()
        self._sections, self._section_of = {}, {}
        self._advanced = set()

    def _emit(self, name: str, value: Any) -> None:
        if self._building:
            return
        self._values[name] = value
        # 改了控制別人的那一格（例如 Normalize 的 method）→ 立刻重算哪幾列該在。
        self._sync_visible_rows()
        self.param_edited.emit(name, value)

    def _sync_visible_rows(self) -> None:
        """依 ``show_when`` 顯示／隱藏各列（F7-20）。

        為什麼是隱藏而不是變淡：``_sync_curve_override`` 的「變淡」講的是
        「這一格還在，只是現在沒有作用」—— 使用者可能想把曲線拉直再用 gamma。
        ``show_when`` 講的是**完全不同的另一件事**：選了 CLAHE 的時候
        ``p_low`` 根本不是這張卡的一部分，留在畫面上只會讓人問「那它算不算數」。
        """
        for name, row in self._rows.items():
            # **規則住在 core**（`step.param_visible`）—— 這裡以前自己又寫了
            # 一次同樣的判斷，而兩份會漂：漂掉的症狀是「設定區看得到某一格，
            # 但引擎當它不存在」，使用者填了一個沒有作用的值而畫面上不會說。
            from ..core.pipeline.step import param_visible
            shown = param_visible(row.spec.get("show_when"), self._values)
            # 兩個規則是 **and**：進階的那一列被 show_when 排除掉的時候，
            # 展開進階也不該把它變出來（那一列在這個方法下根本不算數）。
            if name in self._advanced and not self._advanced_open:
                shown = False
            row.setVisible(shown)

        n = len(self._advanced_names_now())
        self._advanced_btn.setVisible(n > 0)
        # 講**幾格**，不要只講「進階」：使用者要判斷的是「我漏看了什麼」，
        # 而一個沒有數字的標籤答不出那個問題。
        self._advanced_btn.setText(
            "Hide %d more settings" % n if self._advanced_open
            else "Show %d more settings" % n)

        # 整組都藏起來時標題也要不見 —— 一個底下什麼都沒有的標題，
        # 比沒有標題更讓人以為畫面壞了。
        alive = {}
        for name, row in self._rows.items():
            sec = self._section_of.get(name)
            if sec:
                alive[sec] = alive.get(sec, False) or row.isVisibleTo(self)
        for sec, heads in self._sections.items():
            for head in heads:
                head.setVisible(alive.get(sec, True))

    #: 「插入數字 ▾」每一項的 tooltip 與區域顏色從哪來（2026-09-09）。表單
    #: 自己沒有 model，所以 Studio 建表單時裝一支 provider 進來 —— 回
    #: ``(tips, regions)`` 兩張表（`number_picker.number_tips` /
    #: `RecipeModel.feature_regions`）。沒裝就是沒有 tooltip、沒有顏色點，
    #: 那一格照樣完全可用（測試、別的宿主）。
    number_info_provider: Any = None

    def _feature_tips(self) -> Dict[str, str]:
        try:
            got = self.number_info_provider() if self.number_info_provider else None
        except Exception:  # 說明而已，不能擋畫面
            return {}
        return dict((got or ({}, {}))[0])

    def _region_colors(self) -> Dict[str, int]:
        try:
            got = self.number_info_provider() if self.number_info_provider else None
        except Exception:  # 上色而已，不能擋畫面
            return {}
        return dict((got or ({}, {}))[1])

    def set_dynamic_choices(self,
                            dynamic: Optional[Dict[str, Sequence[str]]]) -> None:
        """換一批執行期選單（F15-2），**不重建表單**。

        重建會把游標搶走 —— 而這件事最常發生的時機正是「使用者剛在
        “Source name” 那一格打字」。所以這裡只換那幾格的**內容**，而且
        **跳過現在有游標的那一格**（它的內容就是使用者正在打的字）。
        """
        self._dynamic = {str(k): [str(v) for v in (vals or [])]
                         for k, vals in dict(dynamic or {}).items()}
        for _name, row in self._rows.items():
            choices = self._runtime_choices(row.spec)
            if choices is None:
                continue
            w = row.editor
            if w is None or w.hasFocus():
                continue
            if isinstance(w, MultiChoicePicker):
                w.set_choices(choices)
            elif isinstance(w, QComboBox):
                line = w.lineEdit()
                if line is not None and line.hasFocus():
                    continue
                text = w.currentText()
                w.blockSignals(True)
                try:
                    w.clear()
                    w.addItems(choices)
                    w.setCurrentText(text)
                finally:
                    w.blockSignals(False)

    def _shown_by_rules(self, name: str) -> bool:
        """撇開「進階收起來了」這件事，這一列本身算不算數（``show_when``）。"""
        from ..core.pipeline.step import param_visible
        row = self._rows.get(name)
        if row is None:
            return False
        # **同一支規則**（`step.param_visible`）—— 這裡是第二個自己寫一份的
        # 地方，而兩份會漂：漂掉的症狀是同一列在兩個問句下有兩個答案。
        return param_visible(row.spec.get("show_when"), self._values)

    #: `choices_from` 的鍵 → 空清單時那一格要說的話。**空清單是正常狀態**
    #: （還沒掛第二份），而它畫出來是一塊空白 —— 留白讀起來像壞掉。
    _EMPTY_HINTS = {
        "sources": "No second lot open yet — use the button above.",
        "source_images": "Open the second lot to see its images.",
        "source_columns": "Open the second lot to see its KLARF columns.",
    }

    def _wiring_slot(self, name: str, spec: Dict[str, Any],
                     value: Any) -> QWidget:
        """一格接線（F68）—— 見 `d4t/ui/wiring_slot.py`。

        「非接不可」看的是 `ParamSpec.required_input` 的同一個判準（預設值指得
        出一條流的就是主要輸入）—— 這裡拿 describe 過的 dict，所以自己算一次
        同一句話：**有預設值的影像輸入**才是紅字的那一種。
        """
        from .wiring_slot import IMAGE, REGION, WiringSlot

        ptype = str(spec.get("type", ""))
        kind = REGION if ptype in ("region_key", "region_keys") else IMAGE
        required = (kind == IMAGE
                    and bool(str(spec.get("default", "") or "").strip()))
        w = WiringSlot(kind, "" if value is None else str(value),
                       is_reference=str(spec.get("role", "")) == "reference",
                       required=required)
        w.set_choices(self._wiring_choices(kind))
        w.wire_requested.connect(
            lambda picked, n=name: self.wire_requested.emit(n, picked))
        w.show_requested.connect(
            lambda n=name: self.wire_show_requested.emit(n))
        return w

    def _wiring_choices(self, kind: str) -> List[str]:
        """插槽選單裡有哪些（Studio 用 :meth:`set_wiring_choices` 餵）。"""
        return list(self._wiring.get(str(kind), ()))

    def set_wiring_choices(self, regions: Sequence[str] = (),
                           streams: Sequence[str] = ()) -> None:
        """告訴表單「**到這張卡為止**上游產得出哪些區域／影像流」（F68）。

        跟 `set_dynamic_choices` 一樣，這是**執行期才知道**的東西，所以由
        Studio 餵；差別是它不必等使用者打字，換一張卡就算一次。
        """
        from .wiring_slot import IMAGE, REGION

        self._wiring = {REGION: [str(r) for r in regions],
                        IMAGE: [str(x) for x in streams]}
        for row in self._rows.values():
            w = row.editor
            if hasattr(w, "set_choices") and hasattr(w, "wire_requested"):
                ptype = str(row.spec.get("type", ""))
                w.set_choices(self._wiring[
                    REGION if ptype in ("region_key", "region_keys") else IMAGE])

    def _runtime_choices(self, spec: Dict[str, Any]) -> Optional[List[str]]:
        """這一格的選項是**執行期來的**嗎（F15-2）。不是就回 None。

        認得旗標但拿不到清單（Studio 還沒實作那一個鍵）→ 回**空 list**，
        不是 None：那一格仍然是選單，只是現在是空的 —— 而空的會講出為什麼。
        """
        key = str(spec.get("choices_from", "") or "")
        if not key:
            return None
        return list(self._dynamic.get(key, ()))

    def _make_expr_editor(self, name: str, value: Any,
                          kind: str = "expr") -> QWidget:
        """算式那一格：一個文字框 ＋ 一支「插入數字 ▾」（F21-B）。

        清單來自 ``dynamic_choices["features"]``，項目是
        ``"名字\t誰算的"``（見 `split_labelled`）。拿不到清單的時候它仍然是
        一個**完全可用的文字框** —— 那正是 Studio 以外的地方（測試、將來的
        別的宿主）會遇到的情況，而少一支下拉不該讓那一格不能填。
        """
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        edit = QLineEdit()
        edit.setText("" if value is None else str(value))
        edit.setPlaceholderText(
            "e.g. glv_max - glv_median" if kind == "expr"
            else "e.g. cd_median, cd_min" if kind == "feature_keys"
            else "e.g. glv_worst_score")
        edit.textEdited.connect(lambda t, n=name: self._emit(n, str(t)))
        lay.addWidget(edit)

        items = list(self._dynamic.get("features", ()))
        combo = QComboBox()
        # 一張卡一組、組名點不到、每一項帶一句它是什麼 —— 跟判定面板那支
        # **同一支**（`number_picker`，2026-09-09）。以前這裡是第三份各自寫的
        # 平清單。lazy import：`number_picker` import 本模組的 `split_labelled`。
        from .number_picker import fill_number_picker

        fill_number_picker(combo, items, self._region_colors(),
                           "Insert a number…" if items
                           else "No numbers upstream yet",
                           self._feature_tips())
        combo.setEnabled(bool(items))
        combo.setToolTip("Pick one of the numbers the cards above work out - "
                         "it is put in at the cursor.")
        combo.activated.connect(
            lambda i, c=combo, e=edit, n=name, k=kind:
            self._insert_feature(i, c, e, n, k))
        lay.addWidget(combo)
        return box

    def _insert_feature(self, index: int, combo: QComboBox,
                        edit: QLineEdit, name: str,
                        kind: str = "expr") -> None:
        """把選到的數字送進那一格，然後把下拉撥回標題那一列。

        ``expr`` 插在**游標的位置**（式子中間常常要補一個名字）；
        ``feature_keys`` **接在後面**並補一個逗號（那一格是一串名字，插在中間
        會把別人的名字剖成兩半）。同一支下拉、兩種送進去的方式 —— 差別由那一格
        的型別決定，不由使用者記得。
        """
        if int(index) <= 0:
            return
        token = str(combo.itemData(int(index)) or "")
        combo.setCurrentIndex(0)
        if not token:
            return
        text = edit.text()
        if kind == "feature_keys":
            have = [x.strip() for x in text.split(",") if x.strip()]
            if token in have:            # 已經在裡面就不重複加
                return
            new_text = ", ".join(have + [token])
            pos = len(new_text)
        elif kind == "feature_key":
            # 一格**一個**名字（`rank_by` / `size_feature`）：挑了就是換掉，
            # 插在游標處會變成 `glv_medianglv_max` 那種永遠指不到的東西。
            new_text = token
            pos = len(new_text)
        else:
            pos = max(0, min(edit.cursorPosition(), len(text)))
            new_text = text[:pos] + token + text[pos:]
            pos = pos + len(token)
        edit.setText(new_text)
        edit.setCursorPosition(pos)
        self._emit(name, new_text)

    def _make_editor(self, spec: Dict[str, Any], value: Any,
                     streams: Sequence[str]) -> QWidget:
        name = str(spec.get("name", ""))
        ptype = str(spec.get("type", "str"))
        unit = str(spec.get("unit", "") or "")
        lo, hi = spec.get("min"), spec.get("max")
        runtime = self._runtime_choices(spec)

        if runtime is not None and ptype == "str":
            # **可編輯的**下拉（F15-2）：清單是現在載了什麼，但值仍然可以是一個
            # 還沒載進來的名字 —— recipe 是在資料掛上來**之前**讀進來的，鎖死
            # 選單等於「開一份寫好的 recipe 會把那一格清空」。
            w = QComboBox()
            w.setEditable(True)
            w.addItems(runtime)
            w.setCurrentText("" if value is None else str(value))
            hint = self._EMPTY_HINTS.get(str(spec.get("choices_from") or ""), "")
            if not runtime and hint and w.lineEdit() is not None:
                w.lineEdit().setPlaceholderText(hint)
            w.currentTextChanged.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype in ("expr", "feature_key", "feature_keys"):
            # 算式／一串數字名 ＋ 一支「插入數字 ▾」（F21-B）。**不是**可編輯
            # 的下拉：使用者要打的是一個式子（或一串名字），不是從清單裡挑一個
            # 值 —— 下拉只負責把名字送進去，省掉「記得拼對」這件事。
            # ⚠ `feature_key`（單一個名字）2026-09-09 才進這一行：在這之前它
            # 掉到最底下那個純文字框，於是 Output 卡的 `rank_by` 從來沒有過
            # 下拉 —— 而 `output.py` 的 spec 上寫著「UI 會給這一格一支」。
            return self._make_expr_editor(name, value, kind=ptype)

        if ptype == "int":
            w = QSpinBox()
            w.setRange(int(lo) if lo is not None else -10 ** 9,
                       int(hi) if hi is not None else 10 ** 9)
            if unit:
                w.setSuffix(" " + unit)
            w.setValue(_safe_int(value))
            w.valueChanged.connect(lambda v, n=name: self._emit(n, int(v)))
            return w

        if ptype == "float":
            w = QDoubleSpinBox()
            span = None if (lo is None or hi is None) else float(hi) - float(lo)
            w.setDecimals(_float_decimals(lo, span, value))
            w.setRange(float(lo) if lo is not None else -1e9,
                       float(hi) if hi is not None else 1e9)
            w.setSingleStep(0.01 if (span is not None and span <= 2.0) else 0.1)
            if unit:
                w.setSuffix(" " + unit)
            w.setValue(_safe_float(value))
            w.valueChanged.connect(lambda v, n=name: self._emit(n, float(v)))
            return w

        if ptype == "bool":
            w = QCheckBox("Enabled")
            w.setChecked(bool(value))
            w.toggled.connect(lambda v, n=name: self._emit(n, bool(v)))
            return w

        if ptype == "choice":
            # ⚠ **現在沒有任何一張卡走這一支**（F68 第二輪把每一格選項都換成
            # `chip_choice`，使用者：「設定區都要變成這樣 icon 膠囊 + 文字」）。
            # 型別留著，因為「這一排的選項畫不出圖」是有可能的 —— 那時候硬畫
            # 一張圖是裝飾，而裝飾會讓使用者以為那裡有意思可以讀。
            # 真的要用的人會先撞到 `test_no_card_anywhere_still_shows_a_bare_dropdown`，
            # 那正是停下來想一下的地方。
            w = QComboBox()
            choices = [str(c) for c in (spec.get("choices") or [])]
            w.addItems(choices)
            text = str(value)
            if text in choices:
                w.setCurrentIndex(choices.index(text))
            w.currentTextChanged.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "chart_spec":
            # 一格參數 ＋ 專屬編輯器（同 `chart_style` / `curve`）。
            w = ChartSpecField()
            w.set_text("" if value is None else str(value))
            w.spec_changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "chart_style":
            # 一格參數 ＋ 專屬編輯器（同 `curve`）—— 見 `ChartStyleField`。
            w = ChartStyleField(self._chart_kinds(),
                                words=self._chart_words())
            w.set_text("" if value is None else str(value))
            w.style_changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "curve":
            w = CurveField()
            w.set_text("" if value is None else str(value))
            w.curve_changed.connect(lambda t, n=name: self._emit(n, str(t)))
            w.curve_changed.connect(lambda _t: self._sync_curve_override())
            return w

        if ptype == "image_keys" and spec.get("direction") != "out":
            # F9-6：**來源只在畫布上決定**（使用者定調）。以前這裡是一排勾選框，
            # 於是同一件事有兩個入口 —— 拉線會改它、勾選框也會改它 —— 而畫布上
            # 那條線與這裡的勾選很容易對不起來（使用者的原話是「他會很亂連」）。
            # F68：那一格從「假的輸入框」變成**插槽**——同一顆埠的形狀、
            # 沒接線時講後果、而且可以直接挑一個上游的流（挑了之後由 Studio
            # 走跟拉線同一條路，線仍然是唯一的儲存）。
            return self._wiring_slot(name, spec, value)

        if ptype in ("region_key", "region_keys"):
            # F12：**區域的來源也只在畫布上決定**，跟影像流一模一樣。
            #
            # 以前這裡是下拉／勾選框（F11 Region-1）—— 那已經解掉「打錯字要跑
            # 一次 lint 才知道」的問題，但它留下第二個入口：畫布上沒有任何線
            # 表示這張卡用了上游的區域，而拿掉那張 Region 卡，量測卡會**安靜地
            # 改量整張圖**。使用者的話是「但我還是這樣怪怪的」。
            #
            # 現在區域在畫布上是一顆菱形埠 + 一條虛線，這一格只顯示接的是什麼。
            # 理由與 F9-6 對 image_keys 做的事逐字相同（「他會很亂連」）。
            # F68：改成插槽（見上面那一格的說明）。
            return self._wiring_slot(name, spec, value)

        if ptype == "multi_choice":
            choices = (runtime if runtime is not None
                       else [str(c) for c in (spec.get("choices") or [])])
            w = MultiChoicePicker(
                choices, "" if value is None else str(value),
                empty_hint=self._EMPTY_HINTS.get(
                    str(spec.get("choices_from") or ""), ""),
                labels=spec.get("choice_labels") or {})
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "metric_chips":
            # `multi_choice` 的第二種長相（F18）—— **值的格式一字不差**。
            w = MetricChips([str(c) for c in (spec.get("choices") or [])],
                            "" if value is None else str(value))
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "metric_choice":
            # 單選版（F32）—— 值是一個 id，膠囊長相跟上面同一套。
            w = MetricPick([str(c) for c in (spec.get("choices") or [])],
                           "" if value is None else str(value))
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "channel_map":
            kind = str(spec.get("row_kind") or "images")
            w = ChannelMapField(
                "" if value is None else str(value),
                min_rows=(self._label_count if kind == "labels"
                          else self._image_count),
                row_kind=kind)
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "chip_choice":
            # `choice` 的第二種長相（F68 第二輪）—— **值的格式一字不差**，
            # 換掉的只有長相（同 metric_chips 對 multi_choice 做的事）。
            w = ChoiceChips([str(c) for c in (spec.get("choices") or [])],
                            [str(i) for i in (spec.get("icons") or [])],
                            "" if value is None else str(value),
                            spec.get("choice_help") or {},
                            labels=spec.get("choice_labels") or {})
            w.changed.connect(lambda t, n=name: self._emit(n, str(t)))
            return w

        if ptype == "cell_rois":
            w = CellRoisField("" if value is None else str(value))
            # 值不是在這裡編的（框畫在 cell 上）——按鈕只是把請求往上送。
            w.edit_requested.connect(lambda n=name: self.action_requested.emit(n))
            return w

        if ptype == "template":
            w = TemplateField("" if value is None else str(value))
            # 值不是在這裡編的（模板是一張影像）——按鈕只是把請求往上送，
            # 由 Studio 開對話框，成交之後照一般的路徑寫回參數。
            w.build_requested.connect(lambda n=name: self.action_requested.emit(n))
            return w

        if ptype == "image_key" and spec.get("direction") != "out":
            # F68：同上（單一角色的影像埠，例如「Ref image」）。
            # 同上（F9-6）：來源是接線的結果，不是這裡填的。
            #
            # ⚠ **只有輸入是唯讀的**（F10-7）。`write result to`（`out`）型別
            # 一樣是 image_key，但它是這張卡**吐出去**的那條流的名字 —— 那是
            # 使用者自己取的名字，不是接線的結果，唯讀等於「不給改」。
            # F9-6 那時候還沒有 `direction`，所以只能連輸出一起鎖住；使用者
            # 回報「Write result to 沒辦法改名（不給輸入）」就是這個。
            return self._wiring_slot(name, spec, value)

        w = QLineEdit()
        w.setText("" if value is None else str(value))
        w.textChanged.connect(lambda t, n=name: self._emit(n, str(t)))
        return w

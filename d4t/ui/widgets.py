# d4t Studio widget library — authored 2026-07-28 (M3)；2026-09-08 拆開 (U7)。
"""**這一支現在是一道門，不是一個房間。**

它曾經是 7,140 行、24 個不相干的類別擠在一起 —— 影像檢視器、參數表單、卡片
庫、直方圖、自繪圖示、膠囊、特徵名的排版，全部住同一個檔案。F90 那把規模的
尺 2026-09-08 把它凍住，而 `CLAUDE.md` §4 早就指名它「最好拆、風險最低」。

U7 那一刀把它拆成八支，一支一個主題：

===================  ==========================================================
`ui/buttons.py`      最底層：`small_button`、`FilterChip`、「停放不銷毀」
`ui/icons.py`        **按鈕上**那些自繪的圖（膠囊上的在 `ui/glyphs.py`）
`ui/image_view.py`   `ImageView` ＋ 記號的角色 → 顏色
`ui/fields.py`       參數表單上一列一列的編輯器
`ui/param_form.py`   `ParamForm` —— 把 `Step.describe()` 排成一張表
`ui/chips.py`        設定區的膠囊（統計量、`chip_choice`）
`ui/library.py`      三段式卡片庫
`ui/histogram.py`    分數分佈 ＋ 可拖曳的門檻線
`ui/feature_text.py` 特徵名怎麼變成人看得懂的字 ＋ `VerdictChip`
===================  ==========================================================

**為什麼留一道門，而不是把 import 全部改掉**
--------------------------------------------
四十幾個模組與上百條測試寫的是 ``from .widgets import ImageView``，而那句話
描述的是「我要一個元件」，不是「那個元件住在哪一支檔案」。改掉它們會讓這一刀
從「純搬移」變成一個橫跨半個 repo 的 diff —— 而**這一刀的驗收條件正是
「無任何邏輯 diff」**。

所以搬家的成本留在這裡：一層轉出口。新的程式碼請直接 import 上面那幾支
（意思比較準），而舊的一個字都不用改。

⚠ **拆之前這裡有 141 個頂層名字，拆之後一個都不能少。** 那不是靠人記得 ——
`tests/test_ui_widgets.py::test_the_split_did_not_drop_a_single_name` 拿 git
裡拆之前的那一份當清單問一次。會漏的正是**屬性存取**那種
（``widgets_mod.METRIC_GROUP_ORDER``），掃 import 看不到它。

而**「頂層名字」包含它 import 進來的東西** —— 那一條是踩出來的：第一版的清單
只數了這裡 `class` 與 `def` 出來的 81 個，於是 `TOKENS`（從 `ui/theme` import
進來、再被 `test_ui_f8_ruler` 用 `widgets_mod.TOKENS` 讀走的那一個）安靜地漏掉
了，測試照樣綠 —— 直到那支測試自己壞掉才看得見。

只有一類刻意不轉出：**stdlib 與 Qt 自己的名字**（`math` / `re` / `np` /
`QColor` / `Qt` …）。`widgets.QColor` 從來不是這道門要給的東西，而轉出它等於
說「從這裡拿 Qt 也可以」。那張豁免表寫在那支測試裡，配著一支反向的 —— 表上列
著的名字要是哪天真的被人透過這裡讀了，測試會叫。
"""
from __future__ import annotations

# ⚠ **這一段是轉出口，不是「這裡用得到」**（U7，2026-09-08）。
#
# `widgets.py` 曾經是 7,140 行、24 個不相干的類別擠在一支。拆開的時候
# **一個呼叫端都不改**：四十幾個模組與上百條測試寫的是
# `from .widgets import ImageView`，而那些 import 描述的是「我要一個元件」，
# 不是「那個元件住在哪一支檔案」。所以這裡留一層轉出口。
#
# 底下那行要豁免 F401：那條規則問的是「這個檔案有沒有用到」，答不出
# 「別人有沒有**透過**這個檔案用到」（`CLAUDE.md` §4 那條 `pair_ingest`
# 的教訓 —— 一個轉出口被 `--fix` 順手刪掉，而兩個呼叫端當場壞掉）。
from .feature_text import (   # noqa: F401
    FEATURE_ABSOLUTE, FEATURE_RELATIVE, FEATURE_SUB, FEATURE_SUP,
    VARIANT_GLOSS, VerdictChip, _card_says, _escape, _fmt_number,
    _with_variant, feature_gloss, feature_html, feature_unit, verdict_words,
)
from .histogram import (
    HistogramWidget,
)
from .fields import (         # noqa: F401
    CellRoisField, ChannelMapField, ChartSpecField, ChartStyleField,
    CurveDialog, CurveEditor, CurveField, MultiChoicePicker, ProfilePanel,
    StreamPicker, TemplateField, _BLOCK_EDITORS, _HintLabel, _ParamRow,
    _SLIDER_MAX_INT_SPAN, _SLIDER_TICKS, _float_decimals, _make_slider,
    _safe_float, _safe_int, _wiring_display, glyph_icon, region_dot_icon,
)
from .param_form import (     # noqa: F401
    FEATURE_LABEL_SEP, ParamForm, split_labelled,
)
from .chips import (          # noqa: F401
    METRIC_GROUPS, METRIC_GROUP_ORDER, ChoiceChips, MetricChips, MetricPick,
    _ChipBase, _ChipFlow, _ChoiceChip, _MetricChip, _spell, metric_face,
)
from .buttons import (        # noqa: F401
    FilterChip, clear_layout_parked, small_button,
)
from .library import (        # noqa: F401
    CARD_MIME, GroupIcon, LibraryPanel, StageButton, _LibraryItem,
    column_header, draw_group_icon,
)
from .image_view import (     # noqa: F401
    MARK_ROLE_TOKENS, MARK_ROLE_WEIGHTS, ImageView, _focus_set,
    _qimage_from_uint8, to_uint8,
)
from ..core.algo import glv as algo_glv          # noqa: F401
from ..core.export.uniformity_charts import heat_hex as uc_heat_hex  # noqa: F401
from . import fit_screen                         # noqa: F401
from . import glyphs                             # noqa: F401
from . import region_words                       # noqa: F401
from . import theme                              # noqa: F401
from .numbers import (       # noqa: F401
    format_feature_value, format_feature_value_short,
)
from .theme import (         # noqa: F401
    TOKENS, region_hex,
)
from .icons import (          # noqa: F401
    GLYPH_ICONS, METRIC_GLYPHS, IconButton, _GlyphMixin, _blob_outline,
    _dist_curve, _draw_profile_glyph, _extreme_pair, _paint_glyph, _poly_area,
    apply_button_cursors, draw_glyph_icon, draw_metric_glyph, restyle,
)


__all__ = [
    "ImageView",
    "ParamForm",
    "LibraryPanel",
    "HistogramWidget",
    "feature_html",
    "VerdictChip", "verdict_words",
    "TemplateField",
    "to_uint8",
    "small_button",
    "apply_button_cursors",
    "restyle",
    "IconButton",
    "GLYPH_ICONS",
    "draw_glyph_icon",
    "draw_metric_glyph",
    "METRIC_GLYPHS",
    "METRIC_GROUPS",
    "MetricChips",
    "FilterChip",
    "metric_face",
    "feature_unit",
    "VARIANT_GLOSS",
    "TOKENS",
]



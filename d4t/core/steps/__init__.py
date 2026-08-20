# d4t step-card library — authored 2026-07-28 (M1).
"""步驟卡片庫：import 本套件即完成所有卡片的 registry 註冊。

每個子模組是一到多張卡（@register_step 的 Step 子類別）；
引擎與 UI 只需 ``import d4t.core.steps`` 再從
``d4t.core.pipeline.step.REGISTRY`` / ``list_steps()`` 取卡。

已註冊的 key（影像段 → 算法段）：
  load_patch, load_single, load_sidecar, normalize, tone, denoise, flatten,
  align, subtract, align_to, pair_source,
  roi_cross, roi_template, roi_from_mask, roi_mask,
  snr_map, cd_measure, roi_snr, focus_quality, glv_stats,
  feature_math, output_csv

**2026-08-20（F16）：``pattern_ref`` 刪掉了。** 使用者：「Compare 中
pattern_ref 這項功能完全沒用，請直接拿掉」。

它的代價量過而且**真的付了**：rsem 那條 route 靠它從單張影像的重複 pattern
疊一張 ref 出來，才有 ``diff`` 可以量 —— 分類正確率 24/24。沒有它，同一條
route 只剩「直接量單張影像」，而那條路量過是 12/24（＝猜銅板）。所以
``tests/fixtures/recipes/dual_route_basic.json`` 的 rsem route 重做了，
而 ``tests/test_e2e_dual_route.py`` 的 rsem 斷言從**準確率**改成**跑得完、
算得出分數** —— 那個準確率證據跟著這張卡一起消失了，假裝它還在比沒有更糟。

**2026-08-18：``golden`` 那一支拆成兩件事**（前情）：``cell_period``
（Cell period）刪掉 —— 使用者：「不需要這功能」；``golden_cell`` 先刪、同一天
要回來並改名成 ``pattern_ref`` —— 也就是這一輪拿掉的那一張。

刪掉與 `scope.HIDDEN_STEPS` 收起來是兩件事，差別在使用者說的是哪一句話：
`align` 是「之後真需要我再回來」→ 收起來；`cell_period` / `pattern_ref` 是
「不需要」「完全沒用」→ 刪掉。

⚠ ``d4t/core/algo/golden.py`` 與 ``d4t/core/algo/period.py`` **仍然不要刪** ——
`pattern_ref` 走了之後它們的呼叫者只剩一個（``algo/template.py`` 疊 Golden Cell
模板時要 ``stack_cells`` 與 ``estimate_period`` / ``choose_origin``）。
只剩一個呼叫者的模組正是最容易被當成死碼順手清掉的那一種。
"""
from __future__ import annotations

from . import _util          # 共用小工具（非卡片）
from . import load           # load_patch / load_single
from . import load_sidecar  # load_sidecar（GLAS 的 label map）
from . import normalize      # normalize（percentile / glv_band / match / local）
from . import denoise        # denoise
from . import tone           # tone（亮度/對比/gamma/曲線/反相）
from . import flatten        # flatten
from . import align          # align
from . import arith          # subtract / invert
from . import snr_map        # snr_map
from . import roi_cross      # roi_cross
from . import align_to       # 小圖在大圖裡的位置（F15-C）
from . import pair_source    # 另一份資料的對應那一顆（F15）
from . import roi_from_mask  # GDS label map -> 具名區域
from . import roi_mask       # roi_mask（區域 → 0/255 mask 影像流，F8c）
from . import roi_template   # roi_template
from . import cd             # cd_measure
from . import roi_snr        # roi_snr
from . import quality        # focus_quality
from . import glv_stats      # glv_stats（Gray level：stats / compare）
from . import feature_math   # feature_math（Algo 段：數字 → 數字）
from . import output_csv     # output_csv（Output 段：整批 → 一份 CSV）

__all__ = [
    "load", "load_sidecar", "normalize", "denoise", "tone", "flatten", "align", "arith",
    "align_to", "pair_source", "roi_cross", "roi_from_mask", "roi_mask", "roi_template", "snr_map", "cd", "roi_snr",
    "quality", "glv_stats", "feature_math", "output_csv",
]

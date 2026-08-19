# d4t step-card library — authored 2026-07-28 (M1).
"""步驟卡片庫：import 本套件即完成所有卡片的 registry 註冊。

每個子模組是一到多張卡（@register_step 的 Step 子類別）；
引擎與 UI 只需 ``import d4t.core.steps`` 再從
``d4t.core.pipeline.step.REGISTRY`` / ``list_steps()`` 取卡。

已註冊的 key（影像段 → 算法段）：
  load_patch, load_single, load_sidecar, normalize, tone, denoise, flatten,
  align, subtract, invert, pattern_ref,
  roi_cross, roi_template, roi_from_mask, roi_mask,
  snr_map, cd_measure, roi_snr, roi_compare, focus_quality, glv_stats

**2026-08-18：``golden`` 那一支拆成兩件事。**

* ``cell_period``（Cell period）**刪掉**了 —— 使用者：「不需要這功能」。
  週期的來源因此只剩「參數填死」與「疊圖的那張卡自己估」兩條。
* ``golden_cell``（Golden Cell reference）先刪、同一天要回來，並且**改名**成
  ``pattern_ref``「Reference from pattern」（`steps/pattern_ref.py`）
  —— 使用者：「那可能要拿回來 不過要改名字 不然會誤會」。誤會的來源是
  Template 卡的對話框裡也在疊 golden cell。舊 recipe 由
  `recipe._migrate_renamed_cards` 接住（連分數表達式裡的 feature 名一起換）。

刪掉與 `scope.HIDDEN_STEPS` 收起來是兩件事，差別在使用者說的是哪一句話：
`align` 是「之後真需要我再回來」→ 收起來；`cell_period` 是「不需要」→ 刪掉。
`d4t/core/algo/golden.py` 與 `d4t/core/algo/period.py` 一直都留著。
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
from . import roi_compare    # 比較兩個區域（T/R 住在這張卡上）
from . import roi_cross      # roi_cross
from . import roi_from_mask  # GDS label map -> 具名區域
from . import roi_mask       # roi_mask（區域 → 0/255 mask 影像流，F8c）
from . import roi_template   # roi_template
from . import cd             # cd_measure
from . import roi_snr        # roi_snr
from . import quality        # focus_quality
from . import glv_stats      # glv_stats
from . import pattern_ref    # pattern_ref（從重複 pattern 疊出 ref）

__all__ = [
    "load", "load_sidecar", "normalize", "denoise", "tone", "flatten", "align", "arith",
    "roi_compare", "roi_cross", "roi_from_mask", "roi_mask", "roi_template", "snr_map", "cd", "roi_snr",
    "quality", "glv_stats", "pattern_ref",
]

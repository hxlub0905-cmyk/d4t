# ADEPT step-card library — authored 2026-07-28 (M1).
"""步驟卡片庫：import 本套件即完成所有卡片的 registry 註冊。

每個子模組是一到多張卡（@register_step 的 Step 子類別）；
引擎與 UI 只需 ``import adept.core.steps`` 再從
``adept.core.pipeline.step.REGISTRY`` / ``list_steps()`` 取卡。

已註冊的 key（影像段 → 算法段）：
  load_patch, normalize, tone, denoise, flatten,
  align, subtract, golden_cell, cell_period,
  snr_map, roi_cross, roi_mask, roi_template,
  cd_measure, roi_snr, focus_quality, glv_stats

這份清單是給人讀的，會過期。真正的來源是 ``REGISTRY``：
``python -m adept steps`` 列的是實際註冊到的那些。
"""
from __future__ import annotations

from . import _util          # 共用小工具（非卡片）
from . import load           # load_patch
from . import normalize      # normalize（percentile / glv_band / match / local）
from . import denoise        # denoise
from . import tone           # tone（亮度/對比/gamma/曲線/反相）
from . import flatten        # flatten
from . import align          # align
from . import arith          # subtract
from . import snr_map        # snr_map
from . import roi_cross      # roi_cross
from . import roi_mask       # roi_mask（區域 → 0/255 mask 影像流，F8c）
from . import roi_template   # roi_template
from . import cd             # cd_measure
from . import roi_snr        # roi_snr
from . import quality        # focus_quality
from . import glv_stats      # glv_stats
from . import golden         # cell_period / golden_cell

__all__ = [
    "load", "normalize", "denoise", "tone", "flatten", "align", "arith",
    "roi_cross", "roi_mask", "roi_template", "snr_map", "cd", "roi_snr",
    "quality", "glv_stats", "golden",
]

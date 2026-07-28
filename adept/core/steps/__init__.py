# ADEPT step-card library — authored 2026-07-28 (M1).
"""步驟卡片庫：import 本套件即完成所有卡片的 registry 註冊。

每個子模組是一到多張卡（@register_step 的 Step 子類別）；
引擎與 UI 只需 ``import adept.core.steps`` 再從
``adept.core.pipeline.step.REGISTRY`` / ``list_steps()`` 取卡。

已註冊的 key（影像段 → 算法段）：
  load_patch, percentile_norm, glv_mask_norm, hist_match, denoise,
  align, subtract, invert, golden_cell,
  snr_map, blob_segment, cd_measure, roi_snr, focus_quality, glv_stats,
  cell_period
"""
from __future__ import annotations

from . import _util          # 共用小工具（非卡片）
from . import load           # load_patch
from . import normalize      # percentile_norm / glv_mask_norm / hist_match
from . import denoise        # denoise
from . import align          # align
from . import arith          # subtract / invert
from . import snr_map        # snr_map
from . import blob           # blob_segment
from . import cd             # cd_measure
from . import roi_snr        # roi_snr
from . import quality        # focus_quality
from . import glv_stats      # glv_stats
from . import golden         # cell_period / golden_cell

__all__ = [
    "load", "normalize", "denoise", "align", "arith",
    "snr_map", "blob", "cd", "roi_snr", "quality", "glv_stats", "golden",
]

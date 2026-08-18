# ADEPT step-card library — authored 2026-07-28 (M1).
"""步驟卡片庫：import 本套件即完成所有卡片的 registry 註冊。

每個子模組是一到多張卡（@register_step 的 Step 子類別）；
引擎與 UI 只需 ``import adept.core.steps`` 再從
``adept.core.pipeline.step.REGISTRY`` / ``list_steps()`` 取卡。

已註冊的 key（影像段 → 算法段）：
  load_patch, load_single, load_sidecar, normalize, tone, denoise, flatten,
  align, subtract, invert,
  roi_cross, roi_template, roi_from_mask, roi_mask,
  snr_map, cd_measure, roi_snr, roi_compare, focus_quality, glv_stats

**2026-08-18：``golden`` 那一支（``cell_period`` + ``golden_cell``）刪掉了。**
使用者定調「Compare 內的 Golden Cell reference 功能幫我完整移除（他就是
template）」、「Measure 中的 Cell period 幫我移除（不需要這功能）」。

這一次是**刪掉**不是 `scope.HIDDEN_STEPS`（`align` 走的是後者）—— 差別在使用者
說的是哪一句話：align 是「之後真需要我再回來」，這兩張是「完整移除」。
`adept/core/algo/golden.py` 與 `adept/core/algo/period.py` **都留著**：
`algo/template.py`（Template 卡的 golden cell）在用前者，而後者是之後做
pattern-frame ROI 的唯一工具（見 CLAUDE.md §5 的 ⚠）。
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

__all__ = [
    "load", "load_sidecar", "normalize", "denoise", "tone", "flatten", "align", "arith",
    "roi_compare", "roi_cross", "roi_from_mask", "roi_mask", "roi_template", "snr_map", "cd", "roi_snr",
    "quality", "glv_stats",
]

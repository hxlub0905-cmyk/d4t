# F9 Phase 3d：影像流一進 Context 就凍起來（2026-08-15）。
"""**一張卡不准就地改寫別人的影像流。**

為什麼這件事非鎖不可
--------------------
圖執行器在分岔的時候是 copy-on-fork，而複製**不含像素**（`Packet.fork` 只複製
那本字典）。兩條分支因此指著同一塊記憶體 —— 一張卡若就地改寫，另一條分支拿到
的是被改過的圖，**而且不會有任何錯誤訊息**：跑得完、有數字、而且是錯的。
那是這個專案最在意的一種 bug（同 `cd_x_nm` 恆為 0、同快取只存了一半的 Context）。

計畫書 §5b.1 把它記成「不可變性從型別保證降級成慣例」，並要求在 Phase 3 用
型別或掃描重新鎖上。這一支就是那個鎖：`Context.set_image` 把陣列標成唯讀，
就地改寫當場丟 `ValueError`，指著犯規的那一行。

**掃描原始碼做不到這件事。** `arr += 1` 掃得出來，但 `cv2.blur(src, dst=arr)`
掃不出來 —— 而它們的後果一模一樣。
"""
from __future__ import annotations

import numpy as np
import pytest

# 卡片註冊是 import 的副作用（CLAUDE.md §7）。
import adept.core.steps  # noqa: F401

from adept.core.pipeline import Context, REGISTRY
from adept.core.pipeline.context import freeze
from adept.core.pipeline.graph import Packet


# --------------------------------------------------------------------------- #
# 1. 護欄本身
# --------------------------------------------------------------------------- #
def test_a_stream_is_read_only_once_it_is_in_the_context():
    ctx = Context()
    arr = np.zeros((4, 4), np.uint8)
    ctx.set_image("test", arr)
    with pytest.raises(ValueError):
        ctx.images["test"][0, 0] = 9
    # 同一個物件，不是複本 —— 這道護欄不准偷偷多花一次記憶體
    assert ctx.images["test"] is arr


def test_the_normal_way_to_write_a_card_still_works():
    """「算一張新的、set_image 回去」不受影響；要就地改就先 ``.copy()``。"""
    ctx = Context()
    ctx.set_image("test", np.zeros((4, 4), np.uint8))

    out = ctx.require_image("test").copy()      # 新的一份是可寫的
    out += 3
    ctx.set_image("test", out)
    assert int(ctx.images["test"][0, 0]) == 3


def test_freeze_leaves_things_it_cannot_freeze_alone():
    """這是一道護欄，不是驗證 —— 凍不起來的東西原樣回傳，不准拋例外。"""
    sentinel = object()
    assert freeze(sentinel) is sentinel


# --------------------------------------------------------------------------- #
# 2. 它擋住的正是那個安靜的錯
# --------------------------------------------------------------------------- #
def test_a_card_that_writes_in_place_is_caught_instead_of_poisoning_the_fork():
    """沒有這道護欄的話，第二條分支會拿到被第一條改過的圖，而且沒有人會發現。"""
    ctx = Context()
    ctx.set_image("test", np.zeros((4, 4), np.uint8))
    a, b = Packet(ctx), Packet(ctx).fork()

    # 分岔之後兩包指著同一塊記憶體 —— 這正是要防的那件事
    assert a.ctx.images["test"] is b.ctx.images["test"]
    with pytest.raises(ValueError):
        a.ctx.images["test"] += 1               # 犯規的卡片會長這樣
    assert int(b.ctx.images["test"].max()) == 0, "另一條分支被汙染了"


# --------------------------------------------------------------------------- #
# 3. 掃過整個卡片庫
# --------------------------------------------------------------------------- #
def _seeded_context() -> Context:
    """一個「大部分卡片都跑得動」的 Context：四條流 + 一個具名區域 + 幾個特徵。"""
    rng = np.random.default_rng(7)
    ctx = Context()
    for name in ("test", "ref", "ref_aligned", "diff", "single"):
        ctx.set_image(name, rng.integers(0, 255, (32, 32), dtype=np.uint8))
    ctx.set_roi("main", (0.25, 0.25, 0.5, 0.5))
    ctx.set_roi("cross", (0.3, 0.3, 0.4, 0.4))
    ctx.add_features({"glv_mean": 1.0, "snr_max": 2.0, "peak": 3.0})
    ctx.meta["_dataset_kind"] = "ebi_patch"
    ctx.meta["_defect_id"] = "d1"
    return ctx


def _is_readonly_complaint(e: BaseException) -> bool:
    """numpy 對「寫進唯讀陣列」的抱怨（訊息在不同版本間有小差異）。"""
    text = str(e).lower().replace("-", "")
    return "readonly" in text or "read only" in text


@pytest.mark.parametrize("key", sorted(REGISTRY))
def test_no_card_in_the_library_writes_into_its_input(key):
    """每一張卡用預設參數跑一遍，**不准**碰到唯讀的輸入。

    卡片自己因為別的原因失敗（缺上游、還沒設定完、要一份另外匯入的模板、
    要引擎先把 DefectItem 種進 meta）是**允許**的 —— 這一條問的只有一件事：
    有沒有人在改別人的圖。所以它掃得到整個 registry，而且加新卡片不必來改
    這份清單。
    """
    ctx = _seeded_context()
    try:
        REGISTRY[key]().run(ctx, {})
    except Exception as e:                       # noqa: BLE001 — 見 docstring
        assert not _is_readonly_complaint(e), (
            "卡片 '%s' 就地改寫了輸入的影像流 —— 分岔的時候另一條分支會拿到"
            "被改過的圖，而且不會有任何錯誤訊息。請先 .copy() 再改。（%s）"
            % (key, e))


def test_the_scan_would_actually_catch_a_card_that_breaks_the_rule():
    """守門的測試自己要先證明它抓得到 —— 不然它只是一句永遠成立的話。"""
    from adept.core.pipeline.step import CATEGORY_IMAGE, Step

    class Offender(Step):
        key = "t_inplace_offender"
        label = "x"
        category = CATEGORY_IMAGE
        help = "測試用：故意就地改寫輸入"

        def run(self, ctx, params):
            ctx.require_image("test")[0, 0] = 1   # 犯規
            return ctx

    ctx = _seeded_context()
    with pytest.raises(ValueError) as e:
        Offender().run(ctx, {})
    assert _is_readonly_complaint(e.value)

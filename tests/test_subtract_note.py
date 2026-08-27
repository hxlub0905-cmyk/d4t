# PR-2（2d）：Subtract 卡的診斷 note —— `diff` 是 D2D 的心臟，面板要有料。
"""`diff` 是**新**流，`set_image` 的 `stream_change` 只在覆寫時記
（`test_ui_inspectors.py` 鎖著「第一次寫入不是改」），所以這張卡自己 note。
生命週期跟 Enhance 面板一字不差：`track_changes`（預覽）才記，批次零成本。
"""
from __future__ import annotations

import json

import numpy as np

import d4t.core.steps  # noqa: F401 - 註冊卡片
from d4t.core.pipeline import get_step
from d4t.core.pipeline.context import Context


def _ctx(a, b, track=True):
    ctx = Context(images={"test": np.asarray(a, np.float32),
                          "ref": np.asarray(b, np.float32)})
    ctx.track_changes = bool(track)
    return ctx


def _run(ctx, **over):
    p = {"a": "test", "b": "ref", "op": "subtract", "absolute": False,
         "out": "diff"}
    p.update(over)
    get_step("subtract")().run(ctx, p)
    return ctx


def test_the_note_is_there_in_preview_and_absent_in_batch():
    rng = np.random.default_rng(3)
    a = rng.normal(100, 5, (64, 64))
    b = rng.normal(100, 5, (64, 64))
    on = _run(_ctx(a, b, track=True))
    note = on.meta["subtract"]["diff"]
    for key in ("a", "b", "op", "absolute", "bins", "hi", "clipped", "n",
                "median", "mad", "beyond3", "rows", "cols", "rows_n",
                "cols_n"):
        assert key in note, key
    off = _run(_ctx(a, b, track=False))
    assert "subtract" not in off.meta, "批次（track_changes=False）零成本"


def test_the_numbers_are_the_engines_not_the_panels():
    """median / MAD / beyond3 用同一份 diff 重算要對得起來 —— 面板畫的就是
    引擎算的這一份，測試扮演那個「自己重算一次」的懷疑者。"""
    rng = np.random.default_rng(9)
    a = rng.normal(120, 8, (80, 60))
    b = rng.normal(100, 8, (80, 60))
    note = _run(_ctx(a, b)).meta["subtract"]["diff"]
    # 跟引擎同一條路：兩張圖先各自 cast float32 再相減（順序不同結果就差
    # 一個捨入 —— 這條測試要的是逐位元組）。
    d = (np.asarray(a, np.float32) - np.asarray(b, np.float32)) \
        .astype(np.float64).ravel()
    med = float(np.median(d))
    mad = float(np.median(np.abs(d - med)))
    assert note["median"] == med
    assert note["mad"] == mad
    assert note["beyond3"] == float((np.abs(d - med) > 3.0 * mad).mean())
    assert note["n"] == d.size
    assert sum(note["bins"]) == d.size, "超界收編最外側 bin，一顆都不丟"


def test_row_means_catch_a_stripe_the_histogram_hides():
    """「行列平均是抓對位殘留的主角」不是一句口號 —— 造一條直方圖看不出、
    rows 曲線一眼看出的橫向條紋。"""
    rng = np.random.default_rng(5)
    a = rng.normal(100, 5, (64, 64))
    b = a.copy()
    b[30, :] -= 2.0                       # 一列 +2 的殘留（半像素對位的形狀）
    note = _run(_ctx(a, b)).meta["subtract"]["diff"]
    rows = np.asarray(note["rows"])
    # 直方圖端：那 64 顆像素混在 4096 顆裡，形狀幾乎不動（沒有超界）。
    assert note["clipped"] == 0.0
    # 曲線端：第 30 列的平均整整高出 2，別列在 0 附近 —— 一眼可辨。
    assert rows.max() > 1.5
    assert np.median(np.abs(rows)) < 0.5
    assert len(note["rows"]) <= 128 and len(note["cols"]) <= 128


def test_curves_are_thinned_to_at_most_128_points():
    a = np.zeros((400, 300), np.float32)
    note = _run(_ctx(a, a)).meta["subtract"]["diff"]
    assert len(note["rows"]) <= 128 and len(note["cols"]) <= 128
    assert note["rows_n"] == 400 and note["cols_n"] == 300, \
        "抽稀了要講原長 —— 「128 點」不是「128 列」"


def test_the_note_is_json_serializable():
    rng = np.random.default_rng(1)
    ctx = _run(_ctx(rng.normal(0, 1, (32, 32)), np.zeros((32, 32))))
    json.dumps(ctx.meta["subtract"])   # numpy 標量混進來這裡會炸


def test_recording_never_breaks_the_run(monkeypatch):
    """記錄壞了只會少一份儀表資料，不准弄壞跑（鐵則 7 的精神）。"""
    from d4t.core.steps import arith

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(arith.SubtractStep, "_note_diagnostics", boom)
    ctx = _run(_ctx(np.ones((8, 8)), np.zeros((8, 8))))
    assert "diff" in ctx.images, "note 炸掉，影像照樣要寫出來"

# d4t tests — F16：畫布上的段落
"""段落的順序只有一個真相。

`GROUP_ORDER`（`core/pipeline/step.py`）與 `LibraryPanel.GROUPS`（`ui/widgets.py`）
是同一件事的兩半：前者是引擎認得的 id 與順序，後者多帶給人看的標題與副標。
**兩份漂開的話，卡片庫的順序會跟引擎講的不一樣**，而那件事在畫面上看不出來 ——
使用者只會覺得「這個 app 的段落順序有點怪」。

這個 repo 記過好幾次同一個形狀（同一件事有兩個地方存，抄第二份出來的那份會漂）。
所以這裡不是「檢查一下」，是把兩份綁在一起。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from d4t.core.pipeline.step import (      # noqa: E402 — Qt-free
    GROUP_ALGO, GROUP_ORDER, GROUP_OUTPUT, REGISTRY,
)
import d4t.core.steps  # noqa: F401,E402 — 觸發卡片註冊


def _import_qt(g):
    from PySide6.QtWidgets import QApplication
    from d4t.ui import widgets as widgets_mod
    g["QApplication"] = QApplication
    g["widgets_mod"] = widgets_mod


@pytest.fixture(scope="module")
def qapp():
    _import_qt(globals())
    app = QApplication.instance() or QApplication([])
    yield app


def test_the_library_and_the_engine_agree_on_the_order(qapp):
    """兩份表逐項相同 —— id 與順序都要對得起來。"""
    lib = tuple(gid for gid, _title, _sub in widgets_mod.LibraryPanel.GROUPS)
    assert lib == tuple(GROUP_ORDER), (
        "卡片庫的段落順序跟 GROUP_ORDER 不一樣：\n"
        "  widgets.LibraryPanel.GROUPS = %s\n"
        "  step.GROUP_ORDER            = %s" % (list(lib), list(GROUP_ORDER)))


def test_every_stage_has_a_title_and_a_subtitle(qapp):
    """新加一段的人最容易漏掉副標，而 rail 上只剩一個看不懂的字。"""
    for gid, title, sub in widgets_mod.LibraryPanel.GROUPS:
        assert title.strip(), "段落 %r 沒有標題" % gid
        assert sub.strip(), "段落 %r 沒有副標（rail 上會只剩一個字）" % gid


def test_the_stages_are_in_the_order(qapp):
    """段落照使用者定的順序（而且是**七段**）。

    F16（2026-08-20）定的是八段；F24 §5 把 Algo 段解散進判定（算式住進
    working numbers、補值變成「missing ⇒」、跨顆換算變成「跟整批比」），
    而「動段落要使用者再點一次頭」那條規矩履行過了（2026-08-24：
    「那三件事接著做」）。
    """
    order = list(GROUP_ORDER)
    assert GROUP_ALGO not in order and GROUP_OUTPUT in order
    assert order == ["input", "enhance", "region", "measure",
                     "compare", "adc", "output"], order


def test_the_absorbed_algo_cards_never_read_an_image_stream():
    """Algo 與 Measure 的界線（使用者定調）：

    > measure 是量出數值來，但 Algo 是拿這些 feature 去做更 custom 的處理

    Algo 段解散之後這條界線仍然成立 —— 被吸收的那兩張卡（收在
    `HIDDEN_STEPS`，只服務舊 recipe）不吃影像流；`GROUP_ALGO` 留給外掛
    相容，掛在那上面的卡也一樣。
    """
    for key, cls in sorted(REGISTRY.items()):
        if key not in ("feature_math", "feature_fill") \
                and cls.resolve_group() != GROUP_ALGO:
            continue
        params = {p.name: p.default for p in cls.params}
        reads = cls.resolve_reads(params)
        assert not reads, (
            "卡片 %r 只吃數字，卻要讀影像流 %s。"
            "吃影像的卡屬於 Measure（影像＋區域 → 數字）。" % (key, reads))


def test_output_cards_are_the_end_of_the_line():
    """Output 段的卡是 end point：不吐影像流、也不吐特徵。

    使用者：「他就是個 end point」。這一條讓「Output 卡順手多吐一個數字」
    這種便利功能停在加卡的那一刻 —— 一旦它吐了東西，下游就接得上它，
    而「這一段是最後一段」這句話就不再成立。
    """
    for key, cls in sorted(REGISTRY.items()):
        if cls.resolve_group() != GROUP_OUTPUT:
            continue
        params = {p.name: p.default for p in cls.params}
        assert not cls.resolve_writes(params), \
            "Output 卡 %r 吐了影像流：%s" % (key, cls.resolve_writes(params))
        assert not cls.resolve_features(params), \
            "Output 卡 %r 吐了特徵：%s" % (key, cls.resolve_features(params))

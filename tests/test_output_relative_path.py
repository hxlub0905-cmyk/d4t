# 相對的「Write to」接在資料旁邊，不接在行程的工作目錄（2026-09-24）。
from __future__ import annotations

import os
from types import SimpleNamespace

from d4t.core.steps.output import _anchor


class _DS:
    def __init__(self, src):
        self._src = src

    def source_label(self):
        return self._src


def test_relative_goes_beside_the_klarf(tmp_path):
    klarf = tmp_path / "lot" / "A.001"
    klarf.parent.mkdir()
    klarf.write_text("x")
    got = _anchor("ebi_report", SimpleNamespace(dataset=_DS(str(klarf))))
    assert got == os.path.join(str(klarf.parent), "ebi_report")


def test_relative_goes_inside_the_image_folder(tmp_path):
    got = _anchor("out", SimpleNamespace(dataset=_DS(str(tmp_path))))
    assert got == os.path.join(str(tmp_path), "out")


def test_absolute_and_unknown_are_left_alone(tmp_path):
    ab = str(tmp_path / "abs")
    assert _anchor(ab, SimpleNamespace(dataset=_DS(str(tmp_path)))) == ab
    assert _anchor("rel", SimpleNamespace(dataset=_DS(""))) == "rel"
    assert _anchor("rel", None) == "rel"

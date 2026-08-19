# F11 Input-1 驗收 — authored 2026-08-17.
"""**這一顆的第幾張圖叫什麼，由 recipe 說。**

在這之前，名字是位置決定的、而且**recipe 摸不到**（`channel_order` 只有測試
傳過）：第 1 張 = `test`、第 2 張 = `ref`、之後接 `img3`…。使用者的資料是
**1 張 BSE + 4 張 SE，BSE 固定在第 2 張**，所以：

    第1張 → test    第2張 → ref  ← 其實是 BSE    第3–5張 → img3, img4, img5

而 `subtract` 拿 `test − ref` **一句話都不會說**，比的是 SE 減 BSE。
那是這個 repo 最在意的一種錯：跑得完、有數字、而且是錯的。

對照表放在 **recipe** 裡（使用者定調 2026-08-17），代價是「同一份 recipe 換一台
頁序不同的機台」——所以這一支同時鎖住那道**防呆**：宣告與資料不符要擋下來，
不准照順序硬套。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import d4t.core.steps                                          # noqa: F401,E402
from d4t.core.ingest.dataset import DefectItem, ImageRef        # noqa: E402
from d4t.core.pipeline import Context, ParamError               # noqa: E402
from d4t.core.pipeline.channels import (                        # noqa: E402
    ChannelMapError, format_channel_map, highest_image_number, mapped_names,
    parse_channel_map,
)
from d4t.core.pipeline.step import REGISTRY                     # noqa: E402

LOAD = REGISTRY["load_patch"]


# ---------------------------------------------------------------------------
# 對照表本身
# ---------------------------------------------------------------------------
def test_parse_sorts_and_normalises():
    assert parse_channel_map("2:bse ,1:se1") == [(1, "se1"), (2, "bse")]
    assert format_channel_map([(2, "bse"), (1, "se1")]) == "1:se1, 2:bse"
    assert mapped_names([(2, "bse"), (1, "se1")]) == ["se1", "bse"]
    assert highest_image_number([(2, "bse"), (5, "se4")]) == 5


def test_empty_means_use_the_default_names():
    """空的就是**現行行為** —— 所以舊 recipe 不需要遷移。"""
    assert parse_channel_map("") == []
    assert parse_channel_map(None) == []
    assert highest_image_number([]) == 0


@pytest.mark.parametrize("bad, says", [
    ("bse", "no ':'"),                      # 忘了寫第幾張
    ("x:bse", "not an image number"),
    ("0:bse", "start at 1"),                # 0-based 的直覺要被擋掉
    ("1:", "has no name"),
    ("1:my stream", "cannot be used as a stream name"),
    ("1:2nd", "cannot be used as a stream name"),
    ("1:se1, 1:bse", "listed twice"),
    ("1:bse, 2:bse", "same name"),          # 後面那張會蓋掉前面那張
])
def test_every_bad_row_says_something_a_person_can_act_on(bad, says):
    with pytest.raises(ChannelMapError) as e:
        parse_channel_map(bad)
    assert says in str(e.value), str(e.value)


def test_the_card_rejects_a_bad_map_when_it_is_typed_not_when_it_runs():
    """鐵則 4：壞值擋在 `validate_params`，不准跑到演算法裡。"""
    with pytest.raises(ParamError) as e:
        LOAD.validate_params({"channel_map": "1:my stream"})
    assert "channel_map" in str(e.value)
    # 而且正規化過的值存回 recipe（round-trip 才是 identity）
    assert LOAD.validate_params(
        {"channel_map": "2:bse ,1:se1"})["channel_map"] == "1:se1, 2:bse"


# ---------------------------------------------------------------------------
# 畫布看得到的東西：宣告出來的流
# ---------------------------------------------------------------------------
def test_the_declared_streams_follow_the_map():
    """畫布上的輸出埠照對照表長 —— 名字與數量都要對。"""
    p = LOAD.validate_params({"channel_map": "1:se1, 2:bse, 3:se2"})
    assert LOAD.resolve_writes(p) == ["se1", "bse", "se2"]
    assert LOAD.resolve_writes_for_kind(p, "ebi_patch") == ["se1", "bse", "se2"]


def test_the_declaration_never_depends_on_the_dataset_kind():
    """**宣告只看使用者看得到的值**（F11 Input-4）。

    這一條以前斷言的是相反的事：沒填對照表時 `resolve_writes_for_kind` 會依資料
    型別給 `["test","ref"]`（patch）或 `["single","test"]`（rsem）。那個「一張卡對
    不同資料型別宣告不同東西」的機制，就是使用者回報的「畫布跟實際對不起來」的
    來源 —— 拆成兩張卡之後它整個消失了。
    """
    p = LOAD.validate_params({})
    assert LOAD.resolve_writes(p) == ["test", "ref"]      # ＝ 預設對照表的名字
    for kind in ("ebi_patch", "rsem", "folder", "tiff_stack", "whatever"):
        assert LOAD.resolve_writes_for_kind(p, kind) == ["test", "ref"], kind


# ---------------------------------------------------------------------------
# 執行：五張圖的資料
# ---------------------------------------------------------------------------
class _FiveChannelItem:
    """一顆五張圖的假 DefectItem（1 BSE + 4 SE，BSE 在第 2 張）。

    ingest 會照位置命名成 test / ref / img3 / img4 / img5，而**第 2 張是 BSE**。
    每張圖的灰階值刻意等於它的張號 ×10，所以「哪一條流拿到哪一張圖」一眼看得出來。
    """
    defect_id = "d5"
    die = None
    xrel_nm = None
    yrel_nm = None
    klarf_row = 0
    nm_per_px = None

    def __init__(self, n: int = 5):
        names = ["test", "ref"] + ["img%d" % i for i in range(3, n + 1)]
        self.images = {name: ImageRef(path="fake.tif", page=j, channel=name)
                       for j, name in enumerate(names)}

    def load(self, channel: str):
        page = self.images[channel].page
        return np.full((8, 8), 10 * (page + 1), np.uint8)


def _run(params, item=None):
    ctx = Context()
    ctx.meta["_defect_item"] = item if item is not None else _FiveChannelItem()
    ctx.meta["_dataset_kind"] = "ebi_patch"
    return LOAD().run(ctx, params)


def test_the_bse_page_gets_the_bse_name():
    """**這一輪要換來的東西。** 第 2 張是 BSE，那條流就叫 bse。"""
    ctx = _run({"channel_map": "1:se1, 2:bse, 3:se2, 4:se3, 5:se4"})
    assert sorted(ctx.images) == ["bse", "se1", "se2", "se3", "se4"]
    # 第 2 張的灰階是 20 —— 拿到它的是 bse，不是 ref
    assert ctx.images["bse"].mean() == 20.0
    assert ctx.images["se1"].mean() == 10.0
    assert "ref" not in ctx.images


def test_the_default_map_is_the_old_patch_convention():
    """預設對照表 = `1:test, 2:ref` —— EBI patch 的老規矩，所以黃金值不動。

    五張圖的資料用預設值只會載到前兩張**並講一句**（第 3–5 張沒有名字）。
    以前是安靜地多載三條 `img3`/`img4`/`img5` —— 那三條在畫布上有埠、
    在特徵表裡有前綴，而使用者從來沒有替它們取名字。
    """
    ctx = _run({})
    assert sorted(ctx.images) == ["ref", "test"]
    assert ctx.images["test"].mean() == 10.0 and ctx.images["ref"].mean() == 20.0
    warns = " ".join(ctx.meta.get("warnings", []))
    assert "has 5 images but only 2 are named" in warns
    assert "img3" in warns


def test_declaring_more_images_than_the_data_has_is_refused():
    """宣告五張、資料只有兩張 → **擋下來**，不准照順序硬套。

    這是「對照表放 recipe」的代價的解藥：同一份 recipe 拿到頁序不同的資料時，
    使用者會看到一句可以照做的話，而不是一組安靜地錯位的數字。
    """
    from d4t.core.pipeline.step import StepError
    with pytest.raises(StepError) as e:
        _run({"channel_map": "1:se1, 2:bse, 3:se2, 4:se3, 5:se4"},
             item=_FiveChannelItem(n=2))
    msg = str(e.value)
    assert "at least 5 images" in msg and "has 2" in msg
    assert "Name the images" in msg          # 講得出去哪裡改


def test_naming_fewer_images_than_the_data_has_warns_and_does_not_load_the_rest():
    """只命名前兩張 → 只載那兩張，但**要講一句**（資料比 recipe 預期的多）。"""
    ctx = _run({"channel_map": "1:se1, 2:bse"})
    assert sorted(ctx.images) == ["bse", "se1"]
    warns = " ".join(ctx.meta.get("warnings", []))
    assert "has 5 images but only 2 are named" in warns
    assert "img3" in warns                   # 講出沒載入的是哪幾張


def test_the_inspector_panel_still_shows_which_page_each_stream_came_from():
    """F7-17 的面板資料要跟著改名 —— 那是唯一看得到配對關係的地方。"""
    ctx = _run({"channel_map": "1:se1, 2:bse"})
    pages = {row["channel"]: row["page"] for row in ctx.meta["input"]["pages"]}
    assert pages == {"se1": 0, "bse": 1}
    assert ctx.features["n_channels"] == 2.0


def test_channels_can_still_pick_a_subset_by_the_new_names():
    """`channels` 挑的是**改名後**的名字（兩個參數不打架）。"""
    ctx = _run({"channel_map": "1:se1, 2:bse, 3:se2, 4:se3, 5:se4",
                "channels": "bse,se1"})
    assert sorted(ctx.images) == ["bse", "se1"]


# ---------------------------------------------------------------------------
# 端到端：真的 KLARF + 真的多頁 TIFF（一顆五張）
# ---------------------------------------------------------------------------
#: 一顆 defect 五張圖（`IMAGECOUNT` 5，`IMAGELIST` 給絕對頁號）。
#: 這是使用者的資料形式：1 張 BSE + 4 張 SE，**BSE 在第 2 張**。
_KLARF_FIVE = """FileVersion 1 2;
FileTimestamp 03-14-26 08:00:00;
LotID "LOT_SYN";
SampleSize 1 300;
DeviceID "DEV01";
StepID "STEP01";
DiePitch 1000.0 1200.0;
WaferID "W01";
TiffFileName LOT_SYN.tif;
TiffSpec 6.1 2 "IMAGEVERSION" "IMAGEXYPOS";
InspectionTest 1;
DefectRecordSpec 10 DEFECTID XREL YREL XINDEX YINDEX XSIZE YSIZE CLASSNUMBER IMAGECOUNT IMAGELIST ;
DefectList
 1 100.500 200.500 1 2 0.5 0.5 1 5 1 0 2 0 3 0 4 0 5 0
 2 300.000 400.000 2 3 0.6 0.6 4 5 6 0 7 0 8 0 9 0 10 0;
EndOfFile;
"""


@pytest.fixture()
def five_channel_lot(tmp_path):
    """真的 ingest 走一遍：兩顆 defect × 五張圖，灰階值 = 絕對頁號 ×10。"""
    import tifffile
    from d4t.core.ingest import dataset as ds_mod

    pages = [np.full((16, 16), 10 * (i + 1), np.uint8) for i in range(10)]
    with tifffile.TiffWriter(str(tmp_path / "LOT_SYN.tif")) as tw:
        for arr in pages:
            tw.write(arr, photometric="minisblack")
    kpath = tmp_path / "LOT_SYN.klarf"
    kpath.write_text(_KLARF_FIVE, encoding="utf-8")
    return ds_mod.load_dataset(str(kpath))


def test_the_dataset_layer_already_gives_five_images_per_defect(five_channel_lot):
    """引擎層本來就吃得下五張（頁數是每顆的 IMAGECOUNT，不是寫死 2）——
    缺的只有名字，那正是這一輪做的事。"""
    assert five_channel_lot.kind == "ebi_patch"
    assert len(five_channel_lot.items) == 2
    first = five_channel_lot.items[0]
    assert len(first.images) == 5
    # 沒有對照表的時候，第 2 張叫 ref —— 而它其實是 BSE
    assert sorted(first.images) == ["img3", "img4", "img5", "ref", "test"]


def test_end_to_end_the_second_image_becomes_bse_for_every_defect(five_channel_lot):
    """**這一輪的驗收**：一份 recipe + 真的資料 → 五條各自命名的流。

    第二顆的五張是 TIFF 的第 6–10 頁，所以「第幾張」是**這一顆的**第幾張，
    不是絕對頁號 —— 兩顆都要拿到同一組名字，值才比得起來。
    """
    params = {"channel_map": "1:se1, 2:bse, 3:se2, 4:se3, 5:se4"}
    means = []
    for item in five_channel_lot.items:
        ctx = Context()
        ctx.meta["_defect_item"] = item
        ctx.meta["_dataset_kind"] = five_channel_lot.kind
        out = LOAD().run(ctx, params)
        assert sorted(out.images) == ["bse", "se1", "se2", "se3", "se4"]
        means.append({k: float(v.mean()) for k, v in out.images.items()})
        assert not out.meta.get("warnings"), out.meta["warnings"]

    # 第一顆：第 1–5 頁 → 10..50；第二顆：第 6–10 頁 → 60..100。
    # 兩顆的 bse 都是「自己的第 2 張」。
    assert means[0]["se1"] == 10.0 and means[0]["bse"] == 20.0
    assert means[1]["se1"] == 60.0 and means[1]["bse"] == 70.0

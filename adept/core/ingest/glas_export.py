# ADEPT ingest — authored 2026-08-18 (F11 Region-3 第 2 步).
"""把一份 **GLAS 匯出**掛到已經載好的 lot 上（`<id>_label.png` → 一條影像流）。

分工：**layout 的解析與對位在 GLAS，ADEPT 只吃它匯出的東西**
（`docs/GLAS-INTERFACE.md`，使用者 2026-08-17 定調）。ADEPT 裡不會有
OASIS/GDS parser，也**不做任何對位** —— GLAS 產的 mask 已經是對位完的。

為什麼配對在 ingest 層，不在卡片裡
----------------------------------
影像段快取的簽章與 ``ProcessPool`` 的 worker 都是照「``DefectItem`` 帶著哪些
來源」在算的。卡片自己偷偷讀檔的話，**換了 mask 目錄而簽章看不見** —— 那正是
鐵則 9 擋的那類安靜錯誤。所以：這裡負責「哪個檔對哪一顆」，卡片只吃流。

（`batch._dataset_token_for` 因此也要看得到 sidecar —— 有 KLARF 的時候那個
token 本來只看 KLARF 的 stat，換一份匯出它不會變。那一段跟這個檔一起改的。）

檔案長什麼樣（2026-08-18 對一份真實匯出實測 399 顆）
----------------------------------------------------
* ``overlay_manifest.json``：``{"schema": "mmh-gds-overlay-v4", "columns": [...],
  "images": [每顆一列], "label_map": [{"id", "layer", "fg_glv"}]}``
* 每一列的 ``label_png`` 是**裸檔名**（不是路徑），而且**可能是空的** ——
  GLAS 的分數門檻擋掉的那幾顆就長那樣，那是正常的。
* ``image_id`` 是 KLARF 的 ``DEFECTID``（v4 的 ``id_source`` 直接講）。
* 檔名是 ``_safe_name(image_id)`` 轉過的，所以**不要自己拼**——
  一律用那一列的 ``label_png`` 欄位。

只讀 JSON 不讀 CSV：GLAS 的 CSV 是用平台預設編碼寫的（Windows 上 cp950），
非 ASCII 的 layer 名會壞；JSON 那一份是 ``ensure_ascii=True``，安全。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .dataset import Dataset, ImageRef

__all__ = ["MANIFEST_NAME", "SIDECAR_LABEL", "AttachReport", "read_manifest",
           "label_map", "region_name_for", "default_layer_map",
           "layer_map_default", "attach"]

#: manifest 的固定檔名（`gds_align_tool._write_manifest`）。
MANIFEST_NAME = "overlay_manifest.json"

#: 掛上去的那條流叫什麼。**一個常數，不是各處各寫一份字串。**
SIDECAR_LABEL = "layout_label"

#: 認得的 schema 前綴。v3 / v4 都吃 —— 差別只在 v4 多幾個欄位，而那幾個欄位
#: 我們是「有就用」（見 `attach`）。
_SCHEMA_PREFIX = "mmh-gds-overlay-"


class GlasExportError(Exception):
    """匯出資料夾有問題，而且**在載入的當下**就講得出來。

    不是每顆的執行期錯誤 —— 挑錯資料夾要當場知道，不是跑完 400 顆才發現
    每一顆都定不出來（那跟「這批圖沒有結構」看起來一模一樣）。
    """


@dataclass
class AttachReport:
    """掛完之後的實況。**每個數字都是使用者要看到的**。"""

    #: 幾顆 defect 真的拿到了 label。
    matched: int = 0
    #: manifest 有那一列、但 ``label_png`` 是空的（GLAS 的分數門檻擋掉的）。
    gated: int = 0
    #: manifest 有那一列、檔案卻不在磁碟上。
    missing_file: int = 0
    #: lot 裡有、manifest 裡沒有的 defect。
    defects_without_row: int = 0
    #: manifest 裡有、lot 裡沒有的列。
    rows_without_defect: int = 0
    #: ``label_map``：``[(id, layer 名), …]``（順序就是 id 順序）。
    layers: List[Tuple[int, str]] = field(default_factory=list)
    #: 要講給使用者聽的話（載入當下就顯示，不是等跑完）。
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """至少有一顆掛上了 —— 一顆都沒有的話，八成是挑錯資料夾。"""
        return self.matched > 0

    def summary(self) -> str:
        bits = ["%d defect(s) got a layout label" % self.matched]
        if self.gated:
            bits.append("%d had none in the export (gated by GLAS's score "
                        "threshold)" % self.gated)
        if self.missing_file:
            bits.append("%d named a file that is not there" % self.missing_file)
        if self.defects_without_row:
            bits.append("%d are not in the manifest at all"
                        % self.defects_without_row)
        if self.rows_without_defect:
            bits.append("%d manifest row(s) match no defect in this lot"
                        % self.rows_without_defect)
        if self.layers:
            bits.append("layers: %s" % ", ".join(n for _i, n in self.layers))
        return " · ".join(bits)


def read_manifest(export_dir: Any) -> Dict[str, Any]:
    """讀 ``overlay_manifest.json``。壞了就**當場**拋 :class:`GlasExportError`。"""
    path = os.path.join(str(export_dir), MANIFEST_NAME)
    if not os.path.isfile(path):
        raise GlasExportError(
            "there is no %s in %s. Point at the folder GLAS exported into "
            "(the one with the *_label.png files in it)."
            % (MANIFEST_NAME, export_dir))
    try:
        with open(path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8-sig" if raw[:3] == b"\xef\xbb\xbf" else "utf-8")
        doc = json.loads(text)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        raise GlasExportError("could not read %s: %s" % (path, e)) from None
    if not isinstance(doc, dict):
        raise GlasExportError("%s is not a JSON object." % path)
    schema = str(doc.get("schema", ""))
    if not schema.startswith(_SCHEMA_PREFIX):
        raise GlasExportError(
            "%s says schema %r; ADEPT reads GLAS overlay manifests (%s*). "
            "Is this the right folder?" % (path, schema, _SCHEMA_PREFIX))
    return doc


def label_map(doc: Dict[str, Any]) -> List[Tuple[int, str]]:
    """``[(label id, layer 名), …]``，依 id 排序。

    **沒有 ``label_map`` 是一個要講出來的狀況，不是空清單**：GLAS 只有在匯出時
    勾了 label 才寫它，而少了它，label 圖裡的 1、2、3 就沒有名字可以對 ——
    區域會變成 ``region_1`` 那種沒有意義的名字。呼叫端自己決定要不要擋。
    """
    out: List[Tuple[int, str]] = []
    for entry in doc.get("label_map") or ():
        try:
            out.append((int(entry["id"]), str(entry["layer"])))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out)


def region_name_for(layer: str, taken: Any = ()) -> str:
    """GLAS 的 layer 名 → **ADEPT 的區域名**（`L17/D0` → `L17_D0`）。

    為什麼要有這一支（2026-08-18 對真實匯出實測到的）
    ------------------------------------------------
    真實匯出的三個 layer 名全都含有 ADEPT 區域名規則不收的字元 —— 那個名字會
    變成特徵的前綴（`L17_D0_glv_mean`），所以它必須是一個**變數名**。

    規則刻意很笨，因為它必須**每次都一樣**：不是變數字元的一律換成 `_`、
    頭尾的 `_` 去掉、開頭是數字就補一個 `L`、空的就叫 `layer`。
    ``taken`` 裡已經有的名字會補 `_2`、`_3`… —— 兩層撞名的話後面那層會蓋掉
    前面那層，而畫面上只看得到一個區域。

    這只是**預設值**：使用者可以在卡片上改名（`epi` 比 `L17_D0` 好用太多，
    而寫分數表達式的是他）。跟 F11 Input 的通道命名同一個原則 ——
    程式給預設，名字是使用者的。
    """
    out = "".join(ch if (ch.isalnum() and ord(ch) < 128) or ch == "_" else "_"
                  for ch in str(layer)).strip("_")
    while "__" in out:
        out = out.replace("__", "_")
    if not out:
        out = "layer"
    if out[0].isdigit():
        out = "L" + out
    used = {str(t) for t in (taken or ())}
    if out not in used:
        return out
    n = 2
    while "%s_%d" % (out, n) in used:
        n += 1
    return "%s_%d" % (out, n)


def layer_map_default(layers: Any) -> str:
    """``[(id, layer 名), …]`` → 卡片 ``layers`` 參數的預設值。

    格式跟 ``load_patch`` 的 ``channel_map`` 一模一樣（``"1:epi, 2:mg"``）——
    **重用而不是發明第二個** ：兩者都是「整數 → 名字」，而那一份的驗證規則
    （整數要 ≥1、不能重複、名字要能當變數）正好就是這裡要的。

    吃的是**已經讀出來的清單**而不是整份 manifest，因為 Studio 手上留著的正是
    那份清單（``AttachReport.layers``）—— 讓它為了填一張卡再讀一次 JSON，就是
    多開一條會漂的路。
    """
    names: List[str] = []
    parts: List[str] = []
    for lid, layer in (layers or ()):
        name = region_name_for(layer, names)
        names.append(name)
        parts.append("%d:%s" % (int(lid), name))
    return ", ".join(parts)


def default_layer_map(doc: Dict[str, Any]) -> str:
    """同上，但從整份 manifest 讀。"""
    return layer_map_default(label_map(doc))


def attach(dataset: Dataset, export_dir: Any,
           stream: str = SIDECAR_LABEL) -> AttachReport:
    """把匯出掛到 ``dataset`` 的每一顆上（**就地修改 items**）。

    配對用 manifest 的 ``image_id`` ↔ ``DefectItem.defect_id``，檔名一律取那一列
    的 ``label_png`` 欄位 —— **不要自己拼**：GLAS 的 ``_safe_name`` 會把非
    ``[A-Za-z0-9-_.]`` 的字元換成底線，自己拼的話乾淨的 id 會過、髒的會安靜地
    對不上。

    掛不上的那幾顆**不是錯誤**（GLAS 的分數門檻本來就會擋掉一些），它們只是沒有
    那條流；跑到 Region 卡時那一顆會失敗並講出原因，而整批照跑（鐵則 7）。
    """
    doc = read_manifest(export_dir)
    rows = {str(r.get("image_id", "")): r for r in (doc.get("images") or [])
            if str(r.get("image_id", ""))}
    rep = AttachReport(layers=label_map(doc))
    if not rep.layers:
        rep.warnings.append(
            "this export has no label_map, so the label ids have no layer "
            "names. Re-export from GLAS with “export ROI label map” ticked.")

    seen = set()
    for item in getattr(dataset, "items", []) or []:
        row = rows.get(str(item.defect_id))
        if row is None:
            rep.defects_without_row += 1
            continue
        seen.add(str(item.defect_id))
        name = str(row.get("label_png", "") or "").strip()
        if not name:
            rep.gated += 1
            continue
        path = os.path.join(str(export_dir), name)
        if not os.path.isfile(path):
            rep.missing_file += 1
            continue
        item.sidecars[str(stream)] = ImageRef(path=path, page=None,
                                              channel=str(stream))
        rep.matched += 1
    rep.rows_without_defect = len(set(rows) - seen)

    if not rep.ok:
        rep.warnings.append(
            "not one defect in this lot matched a row in the export. The join "
            "key is the KLARF DEFECTID — check this export was made from this "
            "lot.")
    return rep


def expected_size(doc: Dict[str, Any], defect_id: Any
                  ) -> Optional[Tuple[int, int]]:
    """manifest 說這一顆的影像多大（``(寬, 高)``）—— v4 才有，v3 回 ``None``。

    留這一支是因為「label 圖跟 SEM 影像不一樣大」是唯一會讓框**整片錯位**的
    東西，而 v4 的 manifest 自己就答得出來（不必再去讀另一個檔案）。
    """
    for row in doc.get("images") or ():
        if str(row.get("image_id", "")) == str(defect_id):
            try:
                return int(row["width_px"]), int(row["height_px"])
            except (KeyError, TypeError, ValueError):
                return None
    return None

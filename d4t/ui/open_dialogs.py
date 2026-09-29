# d4t UI — authored 2026-09-18 (F110).
"""Open 鈕各自的**檔案對話框**。

為什麼自己一個模組（`CLAUDE.md` §4：新的面板一律開新模組，`studio.py` 留給
接線）：這幾支裡面有**內容**，不是接線 —— 副檔名過濾字串、「一顆幾張」那個
問句與它的預設值。`studio.py` 那一格天花板**只准往下**，而 F110 要加第五顆
（DOE 的 `Open conditions…`，F121 期 0 又拿掉了）；照規矩要先從它手上搬走等量
的東西，於是這一族整個搬過來，`studio.py` 只留一行轉呼叫。

**2026-09-18（F114-2）：五顆併成三顆**（見 :data:`OPENABLE` 的說明）；
**2026-09-24（F121 期 0）：三顆剩兩顆**（DOE 那顆拿掉）；
**2026-09-29（F121 期 4）：兩顆剩一顆**「Open data…」。它吃「一個檔案**或**一個
資料夾」，而**是哪一種由那條路徑自己回答** —— 判斷住在 core
（`ingest.dataset.plan_open`），CLI 的 `d4t.__main__._open_input` 叫同一支。

⚠ **每一支都回「使用者選了什麼」，不自己去載。** 載入是 `StudioWindow` 的事
（它要管 `_pending_dataset_name`、進度列、worker 忙不忙）—— 這裡只問問題。
問完使用者取消的話回 ``None``，而**呼叫端一律要處理 None**：那是最常見的路徑。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog

from . import wording

if TYPE_CHECKING:                  # 只給型別看：這一支不 import studio
    from .studio import StudioWindow

#: 「一顆幾張」問不到頁數時滑桿的上限。
_UNKNOWN_PAGE_CAP = 999

IMAGE_FILTER = ("Images (*.png *.tif *.tiff *.I01 *.jpg *.jpeg *.bmp);;"
                "All files (*)")
KLARF_FILTER = "KLARF (*.001 *.klarf *.txt);;All files (*)"
RAW_FILTER = "Raw images (*.raw)"
#: 「Open data…」的第一條過濾：上面三種的聯集（一顆鈕吃得下的每一種）。
DATA_FILTER = ("Data - KLARF, images, raw (*.001 *.klarf *.txt *.png *.tif "
               "*.tiff *.I01 *.jpg *.jpeg *.bmp *.raw)")

#: 「以上都不是，我自己填」那一項的字。
OTHER_LAYOUT = "Something else - let me type it in"

#: :func:`open_source` 認得的 key。**`scope.INPUT_SOURCES` 上的每一個 key 都要
#: 在這裡**，不然那顆鈕按下去只會講一句「還沒有辦法開」——
#: `tests/test_ui_input_kinds.py` 兩個方向都守。
#: **2026-09-18（F114-2）：五顆併成三顆。** 使用者：「目前的 input 入口搞得我
#: 很亂（user 可能會被嚇掉）… 可否整合?」→「入口整合成 3 顆」。併掉的是
#: ``folder`` / ``image`` / ``raw`` —— 那幾件事**看一眼那條路徑就知道**。
#: **2026-09-24（F121 期 0）**：DOE 的 `Open conditions…` 拿掉（設計錯了）。
#: **2026-09-29（F121 期 4）**：`Open KLARF…` 與 `Open images…` 併成一顆
#: ``data``（使用者：「我想把入口簡單化」）。F114-2 那時 KLARF 沒併的理由是
#: 「看不出來」—— 而那是錯的：一個檔案是不是 KLARF 讀檔頭就知道
#: （`ingest.dataset.looks_like_klarf`），是 patch 還是一顆一張由 KLARF 自己講。
OPENABLE = ("data",)


def ask_data(parent: Any) -> Optional[str]:
    """「Open data…」—— **一個檔案（KLARF 或一張影像）或一個資料夾**。

    對話框用的是 ``FileMode.Directory`` **加上 `ShowDirsOnly` 關掉** —— 那組合
    底下檔案看得到也選得到，所以「選一個資料夾」與「選一個檔案」**同一顆鈕就
    夠了**，而回來的是一條路徑。要分哪一種交給 :func:`open_path`（→
    `plan_open`），使用者不必先回答一個他還沒看到資料就答不出來的問題。

    ⚠ **非原生對話框**（`DontUseNativeDialog`）：原生的目錄選擇器在每個平台上
    都只給目錄，那正是這一顆要擺脫的限制。
    """
    d = QFileDialog(parent, "Open data - a KLARF, a folder of images, or "
                            "one image")
    d.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    d.setFileMode(QFileDialog.FileMode.Directory)
    d.setOption(QFileDialog.Option.ShowDirsOnly, False)
    d.setNameFilters([DATA_FILTER, KLARF_FILTER.split(";;")[0],
                      IMAGE_FILTER.split(";;")[0], RAW_FILTER, "All files (*)"])
    if not d.exec():
        return None
    got = d.selectedFiles()
    return got[0] if got else None


def ask_raw_layout(parent: Any, probe: str) -> Optional[Any]:
    """`.raw` 要**怎麼讀** —— 寬高、檔頭、位元深度。

    `.raw` 裡沒有任何一個 byte 在講寬高或位元深度，所以非問不可。但先
    **從檔案大小推**（:func:`rawfile.guess_layouts`）：正方形的解通常只有一個，
    而那時候使用者要做的只是確認，不是量。

    ⚠ 推不出來就**老實問**，不預設一個「常見尺寸」—— 猜錯的話每一個像素都錯，
    而且不會報錯（圖會變成一條斜線，不是一個錯誤訊息）。

    ``probe`` 是拿來量大小的那個檔案。回 ``None`` = 使用者取消。
    """
    import os

    from d4t.core.ingest.rawfile import guess_layouts

    size = os.path.getsize(probe)
    # ⚠ **要把檔案本身交出去**，不是只交大小（F115）：有一種 `.raw` 的檔頭裡
    # 就寫著寬高，而那個答案不必猜。只給 size 的話那條路永遠走不到。
    picks = guess_layouts(size, path=probe)
    if picks:
        labels = [s.describe() for s in picks] + [OTHER_LAYOUT]
        choice, ok = QInputDialog.getItem(
            parent, "How is this .raw laid out?",
            "%s is %d bytes.\n\nThese layouts fit exactly:"
            % (os.path.basename(probe), size), labels, 0, False)
        if not ok:
            return None
        if choice != OTHER_LAYOUT:
            return picks[labels.index(choice)]

    # 推不出來、或推出來的都不對 → **一張表單四格一起填**，底下即時講對不對得
    # 上檔案大小、並畫出照這組設定讀出來的樣子（以前是連跳四個小對話框，填錯
    # 一格就從頭來 —— 2026-09-24 使用者要求改）。
    from .raw_dialog import RawLayoutDialog

    dlg = RawLayoutDialog(probe, initial=picks[0] if picks else None,
                          parent=parent)
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.spec()


def open_source(window: Any, key: str) -> None:
    """`INPUT_SOURCES` 裡那一顆按鈕按下去 —— **入口共用這一支**（F110）。

    以前一種入口一支 ``StudioWindow._on_open_<key>``，而 `CLAUDE.md` §5 那句
    「**加／改一個入口＝改 `INPUT_SOURCES`，不要動 UI**」其實做不到：加一列就得
    同時在 `studio.py` 上長一支方法出來，不然那顆鈕按下去是 `AttributeError`。
    現在那句話是真的 —— 這一支照 key 分岔，而 `studio.py` 只留 `partial(...)`。

    問完之後**載入交回給 window**：它要管 `_pending_dataset_name`、進度列、
    worker 忙不忙 —— 那些是它的狀態，不是對話框的。

    ⚠ 認不得的 key **不當機**：那是產品範圍的旋鈕，不是輸入驗證的地方
    （同 `scope.use_profile` 的理由）。講一句話就好。
    """
    if key == "data":
        path = ask_data(window)
        if path:
            open_path(window, path)
    else:
        window._status("No way to open \u201c%s\u201d yet." % key, "error")


def open_path(window: Any, path: str) -> None:
    """選完之後：**看那條路徑決定走哪一條 ingest**（F121 期 4：一顆 Open）。

    使用者不必先回答「這是 KLARF、一疊影像、一張、還是 raw」—— 那幾件事從路徑
    上看得出來（`ingest.dataset.plan_open`，CLI 也叫它），而**看得出來的事就不該
    拿去問人**（推廣鐵則）。只有 `.raw` 要多問一句版面：它的檔案裡沒有任何一個
    byte 在講寬高。
    """
    import os

    from d4t.core.ingest.dataset import plan_open
    from d4t.core.ingest.rawfile import RAW_EXTS

    plan = plan_open(path)
    if plan.what == "raw":
        probe = path if os.path.isfile(path) else None
        if probe is None:
            names = sorted(n for n in os.listdir(plan.path)
                           if os.path.splitext(n)[1].lower() in RAW_EXTS)
            probe = os.path.join(plan.path, names[0])
        spec = ask_raw_layout(window, probe)
        if spec is not None:
            _load_raw(window, plan.path, spec)
    elif plan.what == "folder":
        window.load_folder_path(plan.path)
    elif plan.what == "image":
        window.load_image_path(plan.path)
    else:
        window.load_dataset_path(plan.path)


def _load_raw(window: Any, folder: str, spec: Any) -> bool:
    """讀一個資料夾的 `.raw` 並交給視窗。

    ⚠ **住在這裡而不是 `StudioWindow` 上**：`studio.py` 的三格天花板只准往下
    （`CLAUDE.md` §4），而這一段本來就是「那顆鈕按下去要做什麼」。視窗要的只有
    最後那一個 `Dataset`。
    """
    import os

    from d4t.core.ingest.dataset import load_raw_folder
    from d4t.core.ingest.rawfile import RawSpec

    d = str(folder)
    window._pending_dataset_name = os.path.basename(d.rstrip("/\\"))
    try:
        ds = load_raw_folder(d, spec or RawSpec(width=1, height=1))
    except Exception as e:                  # UI 邊界，一律回報
        window._status("Could not read the raw images: %s"
                       % wording.failure("open.raw", e), "error")
        return False
    return bool(window._on_dataset_loaded(ds))


# --------------------------------------------------------------------------- #
# Recipe 的開與存（F116 第 4 步）
# --------------------------------------------------------------------------- #
# 跟上面那幾顆 Open 是**同一個契約**：只問路徑，做事交給 `window` 上那兩支
# （`load_recipe_path` / `save_recipe_path`）。搬過來是因為它們本來就是這個
# 形狀 —— 留在 `studio.py` 只是歷史。

def open_recipe(window: "StudioWindow") -> None:
    path, _ = QFileDialog.getOpenFileName(
        window, "Open Recipe", "", "Recipe JSON (*.json);;All files (*)")
    if not path:
        return
    window.load_recipe_path(path)


#: 「另存」對話框的副檔名 —— 這一個常數是為了**下面那句 endswith**
#: 而存在的，不是為了整齊：Windows 的另存對話框在使用者自己打了一個
#: 沒有副檔名的名字時**不會**幫他補（`docs/NO-GIT-SETUP.md` 記過記事本
#: 那個反例），而一份叫 `char` 的檔案下次打開時在「Recipe JSON」這個
#: 篩選底下**看不見**。
RECIPE_SUFFIX = ".json"


def save_recipe(window: "StudioWindow") -> bool:
    """`Ctrl+S` 與工具列那顆鈕：**存回原檔**，沒有原檔才問路徑。

    回傳「真的存下去了嗎」—— 關窗前的確認要靠這個答案（F7-16）：
    使用者在另存對話框按取消，意思是「先別關」，不是「丟掉」。
    """
    if window.recipe_path:
        return bool(window.save_recipe_path(window.recipe_path))
    return save_recipe_as(window)


def save_recipe_as(window: "StudioWindow") -> bool:
    """`Ctrl+Shift+S`：**一定問路徑**。"""
    start = window.recipe_path or ("%s%s" % (
        str(getattr(window.model, "recipe_id", "") or "recipe").strip()
        or "recipe", RECIPE_SUFFIX))
    path, _ = QFileDialog.getSaveFileName(
        window, "Save Recipe", start,
        "Recipe JSON (*%s);;All files (*)" % RECIPE_SUFFIX)
    if not path:
        return False
    if not str(path).lower().endswith(RECIPE_SUFFIX):
        path = "%s%s" % (path, RECIPE_SUFFIX)
    return bool(window.save_recipe_path(path))

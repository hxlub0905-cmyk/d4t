# d4t UI — authored 2026-09-18 (F110).
"""Open 鈕各自的**檔案對話框**。

為什麼自己一個模組（`CLAUDE.md` §4：新的面板一律開新模組，`studio.py` 留給
接線）：這幾支裡面有**內容**，不是接線 —— 副檔名過濾字串、「一顆幾張」那個
問句與它的預設值。`studio.py` 那一格天花板**只准往下**，而 F110 要加第五顆
（DOE 的 `Open conditions…`，F121 期 0 又拿掉了）；照規矩要先從它手上搬走等量
的東西，於是這一族整個搬過來，`studio.py` 只留一行轉呼叫。

**2026-09-18（F114-2）：五顆併成三顆**（見 :data:`OPENABLE` 的說明）；
**2026-09-24（F121 期 0）：三顆剩兩顆**（DOE 那顆拿掉）；
**2026-09-29（F121 期 4）：兩顆剩一顆**「Open data…」，**是哪一種由那條路徑自己
回答** —— 判斷住在 core（`ingest.dataset.plan_open`），CLI 的
`d4t.__main__._open_input` 叫同一支。
**2026-10-02：那一顆改回原生檔案對話框**（:func:`ask_data` 的說明有整個故事）：
挑一個檔案；「整個資料夾」是挑裡面任何一張影像之後被問出來的
（:func:`widen_to_folder`），不再是對話框裡選目錄。

⚠ **每一支都回「使用者選了什麼」，不自己去載。** 載入是 `StudioWindow` 的事
（它要管 `_pending_dataset_name`、進度列、worker 忙不忙）—— 這裡只問問題。
問完使用者取消的話回 ``None``，而**呼叫端一律要處理 None**：那是最常見的路徑。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Optional

from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from . import strings, wording

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


#: 挑了一張影像、而它旁邊還有別的影像時，問「只開這一張還是整批」
#: （:func:`widen_to_folder`）。測試關掉（`tests/conftest.py`）＝只開挑的那一張；
#: 要驗那個問句的測試用 :data:`CHOOSE` 換掉使用者的選擇（同 `link_drop` 的形狀）。
ASK = True
#: ``CHOOSE(image_path, folder, n_images) -> image_path | folder | None``。
CHOOSE: Optional[Callable[[str, str, int], Optional[str]]] = None

#: 問句上那兩顆鈕的字（`tests/test_ui_one_open.py` 用它們認鈕）。
THIS_IMAGE = "Just this image"
WHOLE_FOLDER = "All %d images in the folder"


def ask_data(parent: Any) -> Optional[str]:
    """「Open data…」—— **原生**檔案對話框，挑**一個檔案**：KLARF、一張影像、或 `.raw`。

    2026-09-29 ～ 10-02 這裡是 Qt 自己畫的對話框（`DontUseNativeDialog`），設成
    `FileMode.Directory` 再把 `ShowDirsOnly` 關掉，前提是「這樣檔案與資料夾都選得到，
    一顆鈕就夠」。看得到是真的，**選得到是假的**：那個模式下 Qt 的 accept 只收目錄，
    點一個 KLARF 按 Choose **什麼都不會發生**（按鈕灰掉、視窗不關）—— 於是三種資料
    一種都開不了（使用者 2026-10-02 回報「目前 input 都無法載入檔案」）。而且非原生
    對話框在 Windows 上列磁碟走的是 Qt 的檔案系統模型，不是檔案總管：斷線的網路
    磁碟機看起來像壞的、沒有「快速存取」，使用者的話是「瀏覽資料夾視窗變得很奇怪」。
    測試當時全部把這一支換成假的直接餵路徑，所以沒有人看到。
    `tests/test_ui_one_open.py` 現在反向守著那兩個選項不准再出現在這裡。

    「整個資料夾」那條路改成：挑資料夾裡**任何一張影像**，旁邊還有別的影像時
    :func:`widen_to_folder` 會問「只開這張還是整批」。lot 資料夾不必問 ——
    挑 KLARF 就是整批（`plan_open`）。回 ``None`` = 使用者取消。
    """
    path, _ = QFileDialog.getOpenFileName(
        parent, "Open data - pick a KLARF, an image, or a .raw file", "",
        ";;".join([DATA_FILTER, KLARF_FILTER.split(";;")[0],
                   IMAGE_FILTER.split(";;")[0], RAW_FILTER, "All files (*)"]))
    return path or None


def widen_to_folder(parent: Any, path: str) -> Optional[str]:
    """挑了一張影像、旁邊還有別的影像 → 問要開這一張還是整批。

    回要開的那條路徑（那張影像、或它的資料夾）；``None`` = 取消。不是影像、或
    資料夾裡只有它一張，原路回去**不問**（看得出來的事不拿去問人）。數影像用
    `ingest.dataset.image_files` —— 跟 `load_folder` 同一份清單，問句上的數字才會
    等於載進來的顆數。
    """
    import os

    from d4t.core.ingest.dataset import image_files, plan_open

    if plan_open(path).what != "image":
        return path
    folder = os.path.dirname(os.path.abspath(path))
    n = len(image_files(folder))
    if n <= 1:
        return path
    if CHOOSE is not None:
        return CHOOSE(path, folder, n)
    if not ASK:
        return path
    picked = _ask_box(
        parent, strings.tr("Open data"),
        strings.tr("This folder has other images next to the one you picked.")
        + "\n" + strings.tr("Open just this image, or every image in the folder?"),
        [strings.tr(THIS_IMAGE), strings.tr(WHOLE_FOLDER) % n])
    if picked is None:
        return None
    return folder if picked == 1 else path


def _ask_box(parent: Any, title: str, text: str, labels: Any) -> Optional[int]:
    """一題多顆鈕的小問句：回被按的那顆的序號，取消回 ``None``。

    拆成一支是為了測試換得掉（`QMessageBox.clickedButton` 換不掉）。
    """
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    buttons = [box.addButton(label, QMessageBox.AcceptRole) for label in labels]
    box.addButton(QMessageBox.Cancel)
    box.exec()
    clicked = box.clickedButton()
    for i, b in enumerate(buttons):
        if clicked is b:
            return i
    return None


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
            path = widen_to_folder(window, path)
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

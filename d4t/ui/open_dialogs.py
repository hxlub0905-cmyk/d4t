# d4t UI — authored 2026-09-18 (F110).
"""五顆 Open 鈕各自的**檔案對話框**。

為什麼自己一個模組（`CLAUDE.md` §4：新的面板一律開新模組，`studio.py` 留給
接線）：這幾支裡面有**內容**，不是接線 —— 副檔名過濾字串、「一顆幾張」那個
問句與它的預設值、DOE 那顆按鈕問的是目錄不是檔案。`studio.py` 那一格天花板
**只准往下**，而 F110 要加第五顆（`Open conditions…`）；照規矩要先從它手上
搬走等量的東西，於是這一族整個搬過來，`studio.py` 只留一行轉呼叫。

⚠ **每一支都回「使用者選了什麼」，不自己去載。** 載入是 `StudioWindow` 的事
（它要管 `_pending_dataset_name`、進度列、worker 忙不忙）—— 這裡只問問題。
問完使用者取消的話回 ``None``，而**呼叫端一律要處理 None**：那是最常見的路徑。
"""
from __future__ import annotations

from typing import Any, Optional, Tuple

from PySide6.QtWidgets import QFileDialog, QInputDialog

#: 「一顆幾張」問不到頁數時滑桿的上限。
_UNKNOWN_PAGE_CAP = 999

IMAGE_FILTER = ("Images (*.png *.tif *.tiff *.I01 *.jpg *.jpeg *.bmp);;"
                "All files (*)")
STACK_FILTER = "Multi-page TIFF (*.tif *.tiff *.I01);;All files (*)"
KLARF_FILTER = "KLARF (*.001 *.klarf *.txt);;All files (*)"

#: 「以上都不是，我自己填」那一項的字。
OTHER_LAYOUT = "Something else - let me type it in"

#: 手填寬高時的上限（純粹是個滑桿上界，不是產品限制）。
_MAX_SIDE = 65536

#: :func:`open_source` 認得的 key。**`scope.INPUT_SOURCES` 上的每一個 key 都要
#: 在這裡**，不然那顆鈕按下去只會講一句「還沒有辦法開」——
#: `tests/test_ui_input_kinds.py` 兩個方向都守。
OPENABLE = ("klarf", "stack", "folder", "doe_folder", "image", "raw")


def ask_klarf(parent: Any) -> Optional[str]:
    """`Open KLARF…` —— patch 與 RSEM 都走這一顆（ingest 自動判別）。"""
    path, _ = QFileDialog.getOpenFileName(parent, "Open KLARF", "",
                                          KLARF_FILTER)
    return path or None


def ask_image(parent: Any) -> Optional[str]:
    """`Open image…` —— 一個影像檔一顆 defect。"""
    path, _ = QFileDialog.getOpenFileName(parent, "Open image", "",
                                          IMAGE_FILTER)
    return path or None


def ask_folder(parent: Any) -> Optional[str]:
    """`Open folder…` —— 一個資料夾的單張影像，每個檔案一顆 defect。"""
    return QFileDialog.getExistingDirectory(
        parent, "Open folder of images", "") or None


def ask_conditions_folder(parent: Any) -> Optional[str]:
    """`Open conditions…` —— DOE：一個**子目錄**一顆，裡面每個檔案一個 condition。

    ⚠ 標題要講得出跟上面那一顆的差別，因為兩顆都是「選一個目錄」，而選錯的
    下場是一批看起來正常的資料（`folder` 會把每個 condition 當成一顆 defect）。
    """
    return QFileDialog.getExistingDirectory(
        parent, "Open a folder of per-defect folders", "") or None


def ask_raw_folder(parent: Any) -> Optional[Tuple[str, Any]]:
    """`Open raw…` —— 一個資料夾的 headerless `.raw`，外加**它們要怎麼讀**。

    `.raw` 裡沒有任何一個 byte 在講寬高或位元深度，所以這一顆非問不可。但先
    **從檔案大小推**（:func:`rawfile.guess_layouts`）：正方形的解通常只有一個，
    而那時候使用者要做的只是確認，不是量。

    ⚠ 推不出來就**老實問**，不預設一個「常見尺寸」—— 猜錯的話每一個像素都錯，
    而且不會報錯（圖會變成一條斜線，不是一個錯誤訊息）。
    """
    import os

    from d4t.core.ingest.rawfile import RAW_EXTS, RawSpec, guess_layouts

    d = QFileDialog.getExistingDirectory(parent, "Open folder of .raw images", "")
    if not d:
        return None
    names = [n for n in sorted(os.listdir(d))
             if os.path.splitext(n)[1].lower() in RAW_EXTS
             and os.path.isfile(os.path.join(d, n))]
    if not names:
        return d, None                      # 交給 ingest 講那句話（只有一份）
    size = os.path.getsize(os.path.join(d, names[0]))

    picks = guess_layouts(size)
    labels = [s.describe() for s in picks] + [OTHER_LAYOUT]
    choice, ok = QInputDialog.getItem(
        parent, "How is this .raw laid out?",
        "%s is %d bytes.\n\nThese layouts fit exactly:" % (names[0], size),
        labels, 0, False)
    if not ok:
        return None
    if choice != OTHER_LAYOUT:
        return d, picks[labels.index(choice)]

    w, ok = QInputDialog.getInt(parent, "Width", "Pixels across:", 1024, 1,
                                _MAX_SIDE)
    if not ok:
        return None
    h, ok = QInputDialog.getInt(parent, "Height", "Pixels down:", w, 1, _MAX_SIDE)
    if not ok:
        return None
    hdr, ok = QInputDialog.getInt(
        parent, "Header", "Bytes to skip before the pixels start:", 0, 0,
        max(0, size), 1)
    if not ok:
        return None
    bits, ok = QInputDialog.getItem(parent, "Bit depth",
                                    "Bytes per pixel:", ["16-bit", "8-bit"],
                                    0, False)
    if not ok:
        return None
    return d, RawSpec(width=int(w), height=int(h), header=int(hdr),
                      bits=16 if bits.startswith("16") else 8)


def ask_stack(parent: Any) -> Optional[Tuple[str, int]]:
    """`Open stack…` —— 一個多頁 TIFF ＋「一顆幾張」。

    「一顆幾張」問一次就好，而且**預設值要是這個檔案自己的頁數線索**：問這一格
    的時候使用者手上唯一的事實是「這個檔案有幾頁」，所以先講出來。
    """
    path, _ = QFileDialog.getOpenFileName(parent, "Open image stack", "",
                                          STACK_FILTER)
    if not path:
        return None
    pages = 0
    try:
        from d4t.core.ingest import tiff_index
        pages = int(tiff_index.n_pages(path))
    except Exception:            # 只是拿來寫提示
        pages = 0
    prompt = ("How many images make up one defect?\n\n"
              "%s\nEvery N consecutive pages become one defect; enter 1 if "
              "each page is its own defect. Name them afterwards on the "
              "Load images card." % ("This file has %d page(s)." % pages
                                     if pages else ""))
    n, ok = QInputDialog.getInt(parent, "Images per defect", prompt, 1, 1,
                                max(1, pages) if pages else _UNKNOWN_PAGE_CAP)
    return (path, int(n)) if ok else None


def open_source(window: Any, key: str) -> None:
    """`INPUT_SOURCES` 裡那一顆按鈕按下去 —— **五種入口共用這一支**（F110）。

    以前一種入口一支 ``StudioWindow._on_open_<key>``，而 `CLAUDE.md` §5 那句
    「**加／改一個入口＝改 `INPUT_SOURCES`，不要動 UI**」其實做不到：加一列就得
    同時在 `studio.py` 上長一支方法出來，不然那顆鈕按下去是 `AttributeError`。
    現在那句話是真的 —— 這一支照 key 分岔，而 `studio.py` 只留 `partial(...)`。

    問完之後**載入交回給 window**：它要管 `_pending_dataset_name`、進度列、
    worker 忙不忙 —— 那些是它的狀態，不是對話框的。

    ⚠ 認不得的 key **不當機**：那是產品範圍的旋鈕，不是輸入驗證的地方
    （同 `scope.use_profile` 的理由）。講一句話就好。
    """
    if key == "klarf":
        path = ask_klarf(window)
        if path:
            window.load_dataset_path(path)
    elif key == "stack":
        got = ask_stack(window)
        if got:
            window.load_stack_path(got[0], got[1])
    elif key in ("folder", "doe_folder"):
        doe = key == "doe_folder"
        d = ask_conditions_folder(window) if doe else ask_folder(window)
        if d:
            window.load_folder_path(d, doe=doe)
    elif key == "image":
        path = ask_image(window)
        if path:
            window.load_image_path(path)
    elif key == "raw":
        got = ask_raw_folder(window)
        if got:
            _load_raw(window, got[0], got[1])
    else:
        window._status("No way to open \u201c%s\u201d yet." % key, "error")


def _load_raw(window: Any, folder: str, spec: Any) -> bool:
    """讀一個資料夾的 `.raw` 並交給視窗。

    ⚠ **住在這裡而不是 `StudioWindow` 上**：`studio.py` 的三格天花板只准往下
    （`CLAUDE.md` §4），而這一段本來就是「那顆鈕按下去要做什麼」—— 跟隔壁四顆
    同一族。視窗要的只有最後那一個 `Dataset`。
    """
    import os

    from d4t.core.ingest.dataset import load_raw_folder
    from d4t.core.ingest.rawfile import RawSpec

    d = str(folder)
    window._pending_dataset_name = os.path.basename(d.rstrip("/\\"))
    try:
        ds = load_raw_folder(d, spec or RawSpec(width=1, height=1))
    except Exception as e:                  # UI 邊界，一律回報
        window._status("Could not read the raw images: %s: %s"
                       % (type(e).__name__, e), "error")
        return False
    return bool(window._on_dataset_loaded(ds))

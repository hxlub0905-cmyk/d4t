# d4t UI — authored 2026-09-18 (F110).
"""三顆 Open 鈕各自的**檔案對話框**。

為什麼自己一個模組（`CLAUDE.md` §4：新的面板一律開新模組，`studio.py` 留給
接線）：這幾支裡面有**內容**，不是接線 —— 副檔名過濾字串、「一顆幾張」那個
問句與它的預設值、DOE 那顆按鈕問的是目錄不是檔案。`studio.py` 那一格天花板
**只准往下**，而 F110 要加第五顆（`Open conditions…`）；照規矩要先從它手上
搬走等量的東西，於是這一族整個搬過來，`studio.py` 只留一行轉呼叫。

**2026-09-18（F114-2）：五顆併成三顆**（見 :data:`OPENABLE` 的說明）。
`Open images…` 這一顆吃「一個資料夾**或**一個檔案」，而**是哪一種由那條路徑
自己回答** —— 那個判斷跟 CLI 的 `d4t.__main__._open_input` 是同一套規則，
`tests/test_ui_input_kinds.py` 有一條釘住兩邊不准漂。

⚠ **每一支都回「使用者選了什麼」，不自己去載。** 載入是 `StudioWindow` 的事
（它要管 `_pending_dataset_name`、進度列、worker 忙不忙）—— 這裡只問問題。
問完使用者取消的話回 ``None``，而**呼叫端一律要處理 None**：那是最常見的路徑。
"""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtWidgets import QFileDialog, QInputDialog

#: 「一顆幾張」問不到頁數時滑桿的上限。
_UNKNOWN_PAGE_CAP = 999

IMAGE_FILTER = ("Images (*.png *.tif *.tiff *.I01 *.jpg *.jpeg *.bmp);;"
                "All files (*)")
KLARF_FILTER = "KLARF (*.001 *.klarf *.txt);;All files (*)"
RAW_FILTER = "Raw images (*.raw)"

#: 「以上都不是，我自己填」那一項的字。
OTHER_LAYOUT = "Something else - let me type it in"

#: 手填寬高時的上限（純粹是個滑桿上界，不是產品限制）。
_MAX_SIDE = 65536

#: :func:`open_source` 認得的 key。**`scope.INPUT_SOURCES` 上的每一個 key 都要
#: 在這裡**，不然那顆鈕按下去只會講一句「還沒有辦法開」——
#: `tests/test_ui_input_kinds.py` 兩個方向都守。
#: **2026-09-18（F114-2）：五顆併成三顆。** 使用者：「目前的 input 入口搞得我
#: 很亂（user 可能會被嚇掉）… 可否整合?」→「入口整合成 3 顆」。
#: 併掉的是 ``folder`` / ``image`` / ``raw`` —— 它們**本來就是同一種 kind**
#: （``folder``），只差在「一個檔還是一疊檔」與「byte 要怎麼變成像素」，
#: 而那兩件事**看一眼那條路徑就知道**（CLI 的 `_open_input` 早就是這樣做的）。
#: 沒併的兩顆是因為它們**看不出來**：KLARF 的形狀由 KLARF 自己講，而
#: 「資料夾裡還有資料夾」與「一個資料夾的圖」選錯會安靜地得到一批看起來
#: 正常的錯資料。
OPENABLE = ("klarf", "images", "doe_folder")


def ask_klarf(parent: Any) -> Optional[str]:
    """`Open KLARF…` —— patch 與 RSEM 都走這一顆（ingest 自動判別）。"""
    path, _ = QFileDialog.getOpenFileName(parent, "Open KLARF", "",
                                          KLARF_FILTER)
    return path or None


def ask_images(parent: Any) -> Optional[str]:
    """`Open images…` —— **一個資料夾，或單獨一個影像檔**。

    這一顆是 F114-2 把三顆併起來的那一顆（`folder` / `image` / `raw`）。
    對話框用的是 ``FileMode.Directory`` **加上 `ShowDirsOnly` 關掉** ——
    那組合底下檔案看得到也選得到，所以「選一個資料夾」與「選一個檔案」
    **同一顆鈕就夠了**，而回來的是一條路徑。要分哪一種，交給
    :func:`open_source` 看那條路徑（`.raw`？目錄？），使用者不必先回答
    一個他還沒看到資料就答不出來的問題。

    ⚠ **非原生對話框**（`DontUseNativeDialog`）：原生的目錄選擇器在每個平台上
    都只給目錄，那正是這一顆要擺脫的限制。
    """
    d = QFileDialog(parent, "Open images - a folder, or one image file")
    d.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    d.setFileMode(QFileDialog.FileMode.Directory)
    d.setOption(QFileDialog.Option.ShowDirsOnly, False)
    d.setNameFilters([IMAGE_FILTER.split(";;")[0], RAW_FILTER, "All files (*)"])
    if not d.exec():
        return None
    got = d.selectedFiles()
    return got[0] if got else None


def ask_conditions_folder(parent: Any) -> Optional[str]:
    """`Open conditions…` —— DOE：一個**子目錄**一顆，裡面每個檔案一個 condition。

    ⚠ 標題要講得出跟上面那一顆的差別，因為兩顆都是「選一個目錄」，而選錯的
    下場是一批看起來正常的資料（`folder` 會把每個 condition 當成一顆 defect）。
    """
    return QFileDialog.getExistingDirectory(
        parent, "Open a folder of per-defect folders", "") or None


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

    from d4t.core.ingest.rawfile import RawSpec, guess_layouts

    size = os.path.getsize(probe)
    # ⚠ **要把檔案本身交出去**，不是只交大小（F115）：有一種 `.raw` 的檔頭裡
    # 就寫著寬高，而那個答案不必猜。只給 size 的話那條路永遠走不到。
    picks = guess_layouts(size, path=probe)
    labels = [s.describe() for s in picks] + [OTHER_LAYOUT]
    choice, ok = QInputDialog.getItem(
        parent, "How is this .raw laid out?",
        "%s is %d bytes.\n\nThese layouts fit exactly:"
        % (os.path.basename(probe), size), labels, 0, False)
    if not ok:
        return None
    if choice != OTHER_LAYOUT:
        return picks[labels.index(choice)]

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
    return RawSpec(width=int(w), height=int(h), header=int(hdr),
                   bits=16 if bits.startswith("16") else 8)


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
    elif key == "images":
        path = ask_images(window)
        if path:
            _open_picked(window, path)
    elif key == "doe_folder":
        d = ask_conditions_folder(window)
        if d:
            window.load_folder_path(d, doe=True)
    else:
        window._status("No way to open \u201c%s\u201d yet." % key, "error")


def raw_folder_for(path: str) -> Optional[str]:
    """這條路徑是不是 `.raw` 那條路？是的話回**要當成一個 lot 的資料夾**。

    **這就是「一顆鈕吃兩種形狀」的全部邏輯**，而它跟 CLI 的
    `d4t.__main__._open_input` 是同一條規則：`.raw` 解不開，所以
    ``dataset._IMAGE_EXTS`` 裡沒有它 —— 兩邊都得自己問一次。

    * 指到一個 `.raw` **檔** → 它所在的**資料夾**（`.raw` 的位元位移是**整批
      共用**的，見 `ingest/rawfile.py`；一個檔案的資料夾就是一顆的 lot）。
    * 指到一個**資料夾**且裡面有 `.raw` → 那個資料夾。
    * 其他 → ``None``（不是 raw 那條路）。
    """
    import os

    p = str(path)
    if os.path.isfile(p):
        return (os.path.dirname(p) or ".") if _is_raw(p) else None
    if os.path.isdir(p):
        return p if any(_is_raw(n) for n in os.listdir(p)) else None
    return None


def _is_raw(name: str) -> bool:
    import os

    from d4t.core.ingest.rawfile import RAW_EXTS

    return os.path.splitext(str(name))[1].lower() in RAW_EXTS


def _open_picked(window: Any, path: str) -> None:
    """`Open images…` 選完之後：**看那條路徑決定走哪一條 ingest**。

    使用者不必先回答「這是一個檔還是一疊檔、是不是 raw」—— 那三件事從路徑上
    看得出來，而**看得出來的事就不該拿去問人**（推廣鐵則）。
    """
    import os

    raw_dir = raw_folder_for(path)
    if raw_dir is not None:
        probe = path if os.path.isfile(path) else None
        if probe is None:
            names = sorted(n for n in os.listdir(raw_dir) if _is_raw(n))
            probe = os.path.join(raw_dir, names[0])
        spec = ask_raw_layout(window, probe)
        if spec is not None:
            _load_raw(window, raw_dir, spec)
        return
    if os.path.isdir(path):
        window.load_folder_path(path, doe=False)
    else:
        window.load_image_path(path)


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

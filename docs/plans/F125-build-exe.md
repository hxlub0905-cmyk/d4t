# F125 — 把 d4t 包成 exe（資料夾版／單檔版）

狀態：**做完（2026-10-02）—— Linux 容器兩種模式都建過且冒煙全過；等 `exe.yml` 在 Windows runner 上第一次綠、使用者在家用機上建過一次，再搬進 `docs/history/plans/`。**
使用手冊：[`../BUILD-EXE.md`](../BUILD-EXE.md)。工具：`tools/build_exe.py`、`tools/exe/`。

---

## 1. 使用者定調（2026-10-02）

「請幫忙製作一件打包 exe 程式（可選擇單檔 exe 或資料夾）」。三個問題三個答案：

| 問 | 答 |
|---|---|
| exe 裡放什麼 | **Studio + 命令列**：`d4t-studio.exe`（windowed）＋ `d4t.exe`（console）。資料夾版共用一份 `_internal\`，單檔版各一個 exe |
| 要不要 CI | **要**：`.github/workflows/exe.yml`，windows-latest，兩種模式各一份 artifact |
| 範本／手冊／範例資料產生器 | **全部包進去** |

## 2. 為什麼長這樣

* **清單只有一份**：`tools/build_exe.py` 最上面的 `DATAS` / `HIDDEN_IMPORTS` / `EXCLUDES` /
  `EXE_NAMES`。spec 從它 import；`tests/test_build_exe.py` 逐條驗檔案存在，也驗 spec 裡沒有
  再抄一份字面值。
* **datas 的目的地鏡射 repo 版面，所以 core／UI 一行找檔案的程式都不用改**：PyInstaller 6
  把 `__file__` 放在 `<_MEIPASS>/d4t/ui/x.pyc`，`parents[2]` 就是 `_MEIPASS`。範本庫、
  「用範例資料試一次」、手冊、build id、圖示、翻譯檔全部靠這件事。證據：exe 的
  `--version` 印出真的 build id（冒煙一定看它）。
* **`multiprocessing.freeze_support()` 是承重的**：Windows 的 spawn 是重跑 exe，少了它
  `--workers N` 開出 N 個 Studio。放在兩支 launcher 的第一句與兩個進入點的 `__main__`
  守衛，ast 測試守位置。
* **`language._relaunch_command` 加 frozen 分支**：frozen 下 `sys.executable` 就是 exe，
  沒有 `-m d4t` 這回事。
* **spec 進版控、模式走環境變數**（`D4T_EXE_MODE`）：`pyinstaller x.spec` 會忽略 `--onefile`。
  兩個 exe 同一個 spec 一次跑完；資料夾版兩個 `EXE(exclude_binaries=True)` 丟同一個
  `COLLECT`（Qt 只一份）；不用 `MERGE`。
* **圖示現做**（`tools/exe/make_icon.py`）：repo 只有 SVG（純文字鐵則），打包時用 Qt 畫成
  16/32/48 的 DIB ＋ 256 的 PNG 包成 `.ico`，寫檔只用 stdlib。失敗不擋打包。
  ⚠ 踩到兩個 segfault：`QGuiApplication` 沒抓著參照、`QBuffer(QByteArray())` 的暫時物件。
* **工具本身 stdlib-only**（`tools/` 的規矩），PyInstaller 用子行程叫；`pyinstaller>=6` 放
  `dev` extra（只在建置機跑，LICENSE carve-out 不動，LICENSING §4 多一列）。
* **兩個 exe 都帶 Qt**：`_cmd_gui` 靜態 import `d4t.ui.app`，排掉會讓 `d4t.exe gui` 印錯誤提示。

## 3. 容器裡量到的（Linux，2026-10-02）

| | 資料夾版 | 單檔版 |
|---|---|---|
| 建置 | 過；`--version` 印 build id、`steps` 列卡片、Studio offscreen 活到 timeout、`run --workers 2` 跑完 12 顆 CSV 正確 | 過；`--version` 印 build id、`steps` 列卡片 |
| 體積 | 約 578 MB（PySide6 119 MB、opencv-headless 的 .libs 81 MB＋cv2 71 MB、numpy 42 MB、libicudata 31 MB） | 兩個 exe 各約 142 MB（壓縮過；啟動時解開的大小接近資料夾版） |

體積的下一刀（沒做，記在這裡）：`EXCLUDES` 排的是 Python 模組，PySide6 的 hook 仍因為
plugin 相依收了 `libQt6Quick`／`Qml`／`Pdf`（約 20 MB）；要再省得在 COLLECT 之後刪
`imageformats/libqpdf` 這類 plugin。Windows 的 wheel 比 Linux 的小，數字要在 CI 的
artifact 上重量。

## 4. 風險（已知、未解）

* 單檔版 = 兩個各自帶 Qt+numpy+cv2 的 exe；冷啟動解壓到 `%TEMP%`；防毒誤判較多。預設建議資料夾版。
* 未簽章 → SmartScreen 攔；簽章不在範圍。
* Linux 上 `run` 走 fork，spawn 在 frozen 下真正被驗是在 Windows CI（與使用者的家用機）。
* LGPL：exe 把 PySide6 包進去了（原始碼那條路沒有）。單檔版「使用者能換掉 Qt」比資料夾版弱。
  記在 `docs/LICENSING.md`，給法務，不在這裡解。

## 5. 驗收

* [x] `ruff check` 綠。
* [x] `tests/test_build_exe.py` 與文件守門（tree／links／registry／licensing／plans／offline_tools）綠。
* [x] Linux 資料夾版：建、`--version`、`steps`、Studio offscreen、2 worker 批次。
* [x] Linux 單檔版：建、`--version`、`steps`。
* [ ] `exe.yml` 在 windows-latest 綠（第一次推上 main 或手動觸發）。
* [ ] 使用者在家用機上建一次、帶進公司機開得起來。

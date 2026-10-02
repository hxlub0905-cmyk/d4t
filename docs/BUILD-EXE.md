# 把 d4t 包成 Windows 執行檔（exe）

適用情境：**要讓一台沒裝 Python 的機器直接開 Studio**，或是不想再跟同事解釋
「先 activate 虛擬環境」。這份寫給沒碰過打包工具的人，照著做就好。

> 這條路**不取代**原始碼那條路（[`NO-GIT-SETUP.md`](NO-GIT-SETUP.md)、
> [`OFFLINE-INSTALL.md`](OFFLINE-INSTALL.md)）：exe 是**二進位**，不能走剪貼簿、
> 不進 repo。它是「做好一包、帶進去、雙擊就開」的另一種搬運品 ——
> 跟 `wheels\` 同一個性質、同一條搬運路、同一個 DLP 窗口（[`../AGENTS.md`](../AGENTS.md)）。

---

## 0. 會得到什麼

**兩個執行檔**，不管選哪一種模式都是這兩個：

| 檔名 | 做什麼 | 有沒有黑色命令列視窗 |
|---|---|---|
| `d4t-studio.exe` | **雙擊開 Studio**（＝ `python -m d4t gui`） | 沒有 |
| `d4t.exe` | 命令列：`d4t.exe run RECIPE.json LOT.001 --csv out.csv`、`d4t.exe steps`、`d4t.exe --version` | 有 |

兩種模式差在**怎麼放**：

| | 資料夾版（`--onedir`，**建議**）| 單檔版（`--onefile`）|
|---|---|---|
| 長什麼樣 | `dist\d4t\` 一個資料夾：兩個 exe ＋ `_internal\`（程式庫） | `dist\d4t.exe` 與 `dist\d4t-studio.exe` 兩個檔案，各自獨立 |
| 體積 | 程式庫**一份**，兩個 exe 共用 | 程式庫**兩份**（每個 exe 各帶一份 Qt＋numpy＋OpenCV） |
| 啟動 | 直接跑 | **每次冷啟動先把自己解壓到 `%TEMP%`**，慢幾秒到幾十秒 |
| 搬運 | 要**整個資料夾**一起搬（少了 `_internal\` 就開不起來）| 複製一個檔案 |
| 防毒 | 一般 | 這種「自解壓 exe」較常被誤判，要先跟 IT 說 |

不確定就選資料夾版。

## 1. 在**有網路的機器**上（家用機）

1. 照 [`../CLAUDE.md`](../CLAUDE.md) §4 把開發環境裝起來（`pip install -r requirements.txt`）。
2. 多裝打包工具：

   ```
   pip install pyinstaller
   ```

   公司機走內部鏡像站的話：`pip install --index-url https://內部鏡像站/simple pyinstaller`
   （網址問 IT）。它只是建置工具，不會進到任何一條搬運路徑。
3. 在 d4t 的 repo 根目錄（`dir` 看得到 `d4t`、`tools`、`recipes`）跑：

   ```
   python tools\build_exe.py
   ```

   它會問你 **1 = 資料夾、2 = 單檔**。不想被問就直接給旗標：

   ```
   python tools\build_exe.py --onedir      # 資料夾版
   python tools\build_exe.py --onefile     # 單檔版
   python tools\build_exe.py --dry-run     # 只看它會做什麼，不建任何東西
   ```

4. 等幾分鐘。它會先檢查環境（少了什麼會用一句話告訴你怎麼裝）、印出
   「打包的是：d4t 版本 (build ○○○)」、叫 PyInstaller、建完**真的跑一次**
   `d4t.exe --version` 與 `d4t.exe steps` 驗證，最後印一段摘要：東西在哪、多大、怎麼跑。

   看到 `完成：…` 就成功了。看到 `✗` 就照那一行說的修。

> ⚠ **在哪一台做，exe 就只能在那一種系統上跑。** 在 Linux／Mac 上跑這支會做出
> Linux／Mac 的執行檔（它會印一行 △ 提醒）。給廠內 Windows 用的 exe 要在 Windows 上做
> —— 或讓 GitHub Actions 做（§4）。

## 2. 帶進公司機

跟 `wheels\` 一條路（[`OFFLINE-INSTALL.md`](OFFLINE-INSTALL.md) 第一部分的 DLP 那一段）：

* 資料夾版：把**整個 `dist\d4t\`** 複製過去，放在自己有寫入權限的地方
  （`C:\Users\你的帳號\d4t\`），**不要**放 `C:\Program Files\`。
* 單檔版：複製那兩個 exe。
* 公司 DLP 擋 exe 的話，給 IT 看的說法：裡面是 d4t 的原始碼加上 PyPI 上**未修改的官方套件**
  （numpy / OpenCV / tifffile / openpyxl / PySide6），由 PyInstaller 打包；
  `_internal\LICENSE` 與 `_internal\docs\LICENSING.md` 跟在包裡。

## 3. 第一次執行

* **Windows SmartScreen 會攔**（這個 exe 沒有數位簽章）：點「其他資訊」→「仍要執行」。
  只會問一次。
* `d4t.exe --version` 印出 `d4t 0.x (build ○○○)` —— 那個 build 就是
  `python -m d4t --version` 與 `bundle/d4t_bundle.py` 檔頭的同一個數，回報問題時附上它。
* Studio 裡 Templates…、「用範例資料試一次」、卡片上的手冊連結都在：範本 recipe、
  `docs/USING-*.md`、範例資料產生器都包在裡面了。
* 出問題：當機紀錄在 `%LOCALAPPDATA%\d4t\log\`（跟原始碼版同一個地方）。
* **沒有東西需要「安裝」**。要移除就把資料夾刪掉；recipe 與快取在 `~\.d4t\`，不在 exe 旁邊。

## 4. 讓 GitHub Actions 做

`.github/workflows/exe.yml` 在推上 `main` 或手動觸發（Actions → exe → Run workflow）時，
在 Windows runner 上兩種模式各建一次，掛成 artifact `d4t-onedir-windows` 與
`d4t-onefile-windows`。這是 spec **在真的 Windows 上能不能過**的證明（開發用的
Linux 容器建不出 Windows 的 exe）。⚠ 公司機下載不了 artifact —— 先下載到家用機，再走 §2。

## 5. 想改打包的內容

* 要包哪些檔案、哪些 import PyInstaller 看不到、不帶哪些 Qt 模組：**全部在
  `tools/build_exe.py` 最上面那幾張表**（唯一出處）。`tools/exe/d4t.spec` 只負責
  PyInstaller 自己的三步，從那一支 import 清單。
* 清單裡每一個檔案都有測試驗「真的在 repo 裡」（`tests/test_build_exe.py`）；
  搬走或改名一份 USING 文件，測試會當場紅。
* 兩支啟動腳本（`tools/exe/launch_*.py`）第一句一定是 `multiprocessing.freeze_support()`：
  少了它 exe 裡 `--workers 4` 會開出四個 Studio。有測試守，不要搬動。
* 為什麼不用改任何「找檔案」的程式碼：PyInstaller 把模組的 `__file__` 放在
  `<_internal>\d4t\ui\…`，所以程式裡 `Path(__file__).parents[2] / "recipes"` 在 exe 裡
  指到 `<_internal>\recipes` —— 清單把 `recipes\` 放在那裡就好。打包時目的地**鏡射 repo
  的版面**是這件事成立的條件（測試也守著）。
* 授權：exe 把 PySide6（LGPL）**包進去了**，這跟原始碼那條路不一樣 ——
  見 [`LICENSING.md`](LICENSING.md) §4「PySide6 的 LGPL」。目前只在組織內部用。

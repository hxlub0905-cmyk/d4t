# 離線安裝 d4t（公司機沒有網路 / pip 連不出去）

適用情境：**公司機沒有 git、pip 連不到外網、只能拿到純文字的原始碼 zip。**
這份文件寫給「從來沒碰過 Python 套件安裝」的人，照著做就好，不需要懂原理。

整件事只有兩句話：

1. 在**有網路的機器**上，把套件先下載成一個資料夾（`wheels\`）。
2. 把那個資料夾連同 d4t 原始碼帶到**公司機**，用它離線安裝。

> **名詞解釋**
> * **套件（package）**：d4t 用到的現成程式庫，共 4 個：
>   `numpy`（數值運算）、`opencv-python`（影像處理）、`tifffile`（讀 TIFF）、
>   `openpyxl`（寫 Excel）、`PySide6`（圖形介面）。
> * **wheel（`.whl` 檔）**：套件「已經編譯好」的安裝檔，副檔名 `.whl`。
>   它本質上是一個 zip 檔，裡面有 `.py` 與（部分套件）編譯好的 `.pyd` / `.dll`。
> * **venv（虛擬環境）**：一個獨立的小 Python 環境，裝在 d4t 資料夾底下的 `.venv\`。
>   好處是不會弄髒公司機原本的 Python，要刪掉就整個資料夾砍掉。

---

## 開始之前：先查兩件事（在**公司機**上查）

打開命令提示字元（開始 → 輸入 `cmd`），輸入：

```
python -V
python -c "import struct; print(struct.calcsize('P')*8, 'bit')"
```

你會看到類似 `Python 3.11.5` 與 `64 bit`。**把版本號記下來**，等一下要用：

| 公司機顯示 | 等一下要填的 `--python-version` |
|---|---|
| Python 3.9.x  | `39` |
| Python 3.10.x | `310` |
| Python 3.11.x | `311` |
| Python 3.12.x | `312` |

> 版本填錯是離線安裝**最常見**的失敗原因（`cp39` 的檔案在 Python 3.11 上一定裝不起來）。
> d4t 的安裝程式會在動手前先幫你比對、擋下來，但一開始就填對可以省一趟來回。
>
> 如果顯示 `32 bit`，請請 IT 換成 64 位元的 Python —— `PySide6` 與 `opencv` 幾乎只出 64 位元版。
> d4t 需要 **Python 3.9 以上**。

---

# 第一部分：在**有網路的機器**上

## 步驟 1：拿到 d4t 原始碼

到 `https://github.com/hxlub0905-cmyk/d4t` → 綠色 **Code** → **Download ZIP**，
解壓成 `d4t-main\`。（詳見 `docs/NO-GIT-SETUP.md`。）

## 步驟 2：下載套件到 `wheels\` 資料夾

在 `d4t-main\` 裡開命令提示字元，執行（把 `311` 換成你剛剛記下來的版本）：

```
python tools\fetch_wheels.py --python-version 311
```

想連測試工具一起帶（之後要在公司機跑 `pytest`）就多加一個選項：

```
python tools\fetch_wheels.py --python-version 311 --include-pytest
```

這支程式做的事：叫 pip 去 PyPI 把「**Windows 64 位元 + 你指定的 Python 版本**」的
`.whl` 檔通通抓下來放進 `wheels\`。
**在 Linux 或 Mac 上跑也沒關係**，它抓的一樣是 Windows 版的檔案。

其他可用選項：

| 選項 | 用途 |
|---|---|
| `--dest D:\d4t_wheels` | 換一個存放資料夾 |
| `--platform win_amd64` | 目標平台（預設就是這個；32 位元填 `win32`） |
| `--include-pytest` | 連 pytest 一起抓 |
| `--dry-run` | 只印出它會執行的指令，不真的下載（想先看看它要做什麼時用） |

## 步驟 3：看它的驗收報告

跑完會印出一張表和一句結論，例如：

```
  套件            版本      標籤              大小
  ------------------------------------------------
  PySide6         6.5.2     cp37-win_amd64   1.5 KB
  numpy           1.26.4    cp311-win_amd64  15.5 MB
  ...
  合計 12 個檔案，180.4 MB

→ 已寫出清單：...\wheels\MANIFEST.txt

結論：12 個 wheel、共 180.4 MB，全部齊全。
```

* 看到「**全部齊全**」就成功了。
* 如果它說某個套件「**沒有抓到任何 .whl**」→ 多半是 `--python-version` 填的版本
  沒有官方 wheel，換一個版本再試。
* 如果它說資料夾裡有「**原始碼包（不是 wheel）**」→ 那種檔案在公司機需要 C 編譯器，
  幾乎一定裝不起來，請改用有 wheel 的版本、或請 IT 從公司內部鏡像站取得。

`wheels\MANIFEST.txt` 是**清單檔**：裡面有每個檔案的名稱、sha256 雜湊值、
以及這批檔案是給哪個平台／哪個 Python 版本用的。
公司機的安裝程式會讀它做版本比對；IT 要稽核「你到底帶了什麼進來」時也可以直接給他看這個檔。

## 步驟 4：要帶進公司的東西

只有兩樣，放在同一個資料夾裡最省事：

```
d4t-main\          ← 原始碼（純文字，沒有任何執行檔）
d4t-main\wheels\   ← 剛剛下載的 .whl 檔 + MANIFEST.txt
```

> ### ⚠️ 關於公司 DLP（資料外洩防護）擋壓縮檔／執行檔
>
> **原始碼 zip 沒有問題**：整包都是純文字（`.py` / `.md` / `.json` / `.txt`），
> 沒有任何執行檔。
>
> **`wheels\` 資料夾要注意**：`.whl` 檔本身是 zip 格式，而且 numpy / opencv / PySide6
> 的 wheel 裡面確實含有編譯好的二進位檔（`.pyd` / `.dll`）—— 這是所有 Python 套件的
> 正常型態，但有些公司的 DLP 政策會直接擋。三條路：
>
> 1. **請 IT 把這個資料夾加入允許清單**。把 `MANIFEST.txt` 給他看：
>    裡面列出每個檔案的名稱、大小與 sha256，全部是公開 PyPI 上的官方套件，
>    沒有任何自製二進位檔，IT 可以逐一比對來源。
> 2. **用公司內部的套件鏡像站**（Artifactory / Nexus / 內部 PyPI）。
>    如果公司有，那是最順的做法，完全不用帶檔案進來：
>    ```
>    pip install -r requirements.txt --index-url https://內部鏡像站/simple --trusted-host 內部鏡像站
>    ```
>    （鏡像站網址請問 IT。）
> 3. **請 IT 直接幫你安裝**這 5 個套件 —— 它們都是業界標準的公開套件。
>
> 不論走哪一條，裝完都用 `python tools\doctor.py` 驗收（見下）。

---

# 第二部分：在**公司機**上

## 步驟 1：解壓原始碼

把 `d4t-main.zip` 解壓到**你自己有寫入權限的資料夾**，例如
`C:\Users\你的帳號\d4t-main`。

> 不要放在 `C:\Program Files\`、磁碟根目錄、或唯讀的網路磁碟 —— 會沒有權限寫檔案。

把帶進來的 `wheels\` 資料夾放進 `d4t-main\` 裡面。

## 步驟 2：切換到那個資料夾

開始 → `cmd` → 輸入（路徑換成你自己的）：

```
cd C:\Users\你的帳號\d4t-main
dir
```

`dir` 要看得到 `d4t`、`tools`、`requirements.txt`、`wheels` 這幾個名字。
**看不到就是你在錯的資料夾** —— 這是新手最常見的錯誤，後面所有指令都會失敗。

## 步驟 3：安裝

```
python tools\install_offline.py
```

（如果 `wheels\` 放在別的地方：`python tools\install_offline.py --wheels D:\d4t_wheels`）

它會依序做四件事，每一步都會印出結果：

```
[1/4] 事前檢查…          ← 版本、空間、權限對不對；有問題會在這裡停下來並告訴你怎麼修
[2/4] 建立虛擬環境 .venv  ← 一個乾淨的小 Python 環境，不會動到公司機原本的設定
[3/4] 安裝套件…          ← pip install --no-index --find-links=wheels -r requirements.txt
                            （--no-index = 完全不連網，只用你帶進來的檔案）
[4/4] 環境自檢…          ← 自動跑 tools\doctor.py 驗收
```

最後會印出一段「接下來要打的指令」。**看到自檢通過就成功了。**

常用選項：

| 選項 | 什麼時候用 |
|---|---|
| `--wheels 路徑` | `wheels\` 放在別的地方 |
| `--include-pytest` | 連 pytest 一起裝（下載時也要加同名選項，`wheels\` 裡才會有） |
| `--no-venv` | 公司機的 Python 建不出虛擬環境（見疑難排解） |
| `--no-venv --user` | 沒有系統管理權限，要裝到自己的帳號底下 |
| `--venv D:\d4t_venv` | C 槽空間不夠，把虛擬環境放到別的磁碟 |
| `--dry-run` | 只做事前檢查、不真的安裝（想先確認環境沒問題時用） |

## 步驟 4：驗收與開始用

```
.venv\Scripts\activate         ← 每次開新的命令提示字元都要先做這一步
python tools\doctor.py         ← 環境自檢，全部 ✓ 就沒問題
python -m d4t gui            ← 開圖形介面 Studio
```

第一次玩可以先產一份合成資料（不需要真實 KLARF）：

```
python tools\make_sample.py C:\temp\lot --n 100
```

然後在 Studio 裡：**開啟 KLARF** 選 `C:\temp\lot\LOT_SYN.001` →
**載入範本（die-to-die）** → **試跑**。

> `.venv\Scripts\activate` 執行成功後，命令提示字元最前面會出現 `(.venv)`。
> 沒有那個字樣就表示還沒啟用，`python -m d4t gui` 會說找不到套件。

---

# 第三部分：疑難排解

**任何時候卡住，先跑這一行**，它會逐項告訴你哪裡壞了、以及怎麼修：

```
python tools\doctor.py            （想看完整錯誤訊息就加 --verbose）
```

`doctor` 檢查：Python 版本與位元數、5 個套件能不能載入、
從目前資料夾能不能找到 `d4t`、Qt 能不能開視窗、
資料夾與快取目錄 `~\.d4t` 有沒有寫入權限，
最後還會實際產一份迷你合成資料、跑一顆 defect 走完整條 recipe（約 10 秒）。
全部通過離開碼是 0，否則是 1，最後一行永遠是一句白話結論。

| 症狀（畫面上出現的訊息） | 真正的原因 | 怎麼修 |
|---|---|---|
| `install_offline` 說「**Python 版本對不上**」 | 帶進來的 wheel 是給別的 Python 版本用的（例如 cp39 的檔案配 Python 3.11） | 兩條路：(A) 公司機若也裝了對應版本，用那個版本執行，例如 `C:\Python39\python.exe tools\install_offline.py`；(B) 回有網路的機器重抓：`python tools\fetch_wheels.py --python-version 311` |
| pip 說 `... is not a supported wheel on this platform` | 同上（版本或 32/64 位元不合），或抓成了 Linux/Mac 版 | 重抓時確認 `--python-version` 與 `--platform win_amd64` 都正確 |
| `install_offline` 說「**找不到離線套件資料夾**」 | `wheels\` 沒帶到、或不在預設位置 | 用 `--wheels` 指定完整路徑，或把資料夾複製到 `d4t-main\wheels` |
| `install_offline` 說「**裡面沒有任何 .whl 檔**」 | 複製時只複製了空資料夾，或防毒／DLP 把 `.whl` 擋掉刪掉了 | 重新複製一次；若是 DLP 擋掉，見第一部分的 DLP 說明（請 IT 允許清單化或改用內部鏡像站） |
| 建立虛擬環境失敗，訊息裡有 `ensurepip` | 公司統一安裝的 Python 映像常把 `ensurepip` 拿掉，`python -m venv` 因此建不起來 | 改成不建虛擬環境：`python tools\install_offline.py --no-venv`；若連系統目錄都不能寫，再加 `--user` |
| `Permission denied` / `Access is denied` / 「沒有寫入權限」 | d4t 放在 `C:\Program Files` 之類受保護的位置，或家目錄被鎖 | 把整個資料夾搬到 `C:\Users\你的帳號\` 底下再試；快取可用 `--cache D:\temp\d4t_cache` 指到寫得進去的地方 |
| 「磁碟空間不夠」 | PySide6 解開後要幾百 MB | 清空間，或 `--venv D:\d4t_venv` 把虛擬環境放到別的磁碟 |
| `ImportError: DLL load failed while importing QtCore` 或 `doctor` 說「Qt 開不了視窗」 | PySide6 需要 **Microsoft Visual C++ Redistributable 2015-2022 (x64)**，公司機常常沒裝 | 請 IT 安裝 VC++ Redistributable (x64)。暫時的替代方案：先用命令列模式 `python -m d4t run ...`（不需要開視窗） |
| `ModuleNotFoundError: No module named 'd4t'` | **跑錯資料夾**（八成是這個原因） | `cd` 到解壓出來、`dir` 看得到 `d4t` 資料夾的那一層再執行 |
| `ModuleNotFoundError: No module named 'numpy'`（明明裝過了） | 忘了啟用虛擬環境 | 先 `.venv\Scripts\activate`，命令提示字元前面要出現 `(.venv)` |
| pip 出現 proxy / SSL / 連線逾時 的錯誤 | **離線安裝其實完全不連網**（`--no-index` 已經關掉了）。會出現這種訊息，通常是機器上有 `pip.ini` 設了 `index-url`，或設了 `PIP_INDEX_URL` 環境變數 | 檢查 `%APPDATA%\pip\pip.ini`；或先設定 `set PIP_NO_INDEX=1` 再跑一次。**不需要**為了離線安裝去申請開放防火牆 |
| 下載時 pip 說 `Could not find a version that satisfies the requirement ...` | 那個套件在你指定的 Python 版本沒有官方 wheel | 換 `--python-version`，或放寬 `requirements.txt` 裡的版本下限 |
| `doctor` 的表格顯示成一堆問號或亂碼 | 命令提示字元的字碼頁不支援 ✓✗△ | 先執行 `chcp 65001` 再跑；`doctor` 也會自動改用 `[OK]/[XX]/[!!]` 這種純英數符號 |

---

## 附錄：指令速查

**有網路的機器**

```
python tools\fetch_wheels.py --python-version 311 --include-pytest
python tools\fetch_wheels.py --dry-run              # 只看它會做什麼
```

**公司機**

```
cd C:\Users\你的帳號\d4t-main
python tools\install_offline.py                     # 安裝（會自動驗收）
python tools\install_offline.py --no-venv --user    # 沒權限 / 建不出 venv 時
.venv\Scripts\activate                              # 每次開新視窗都要先做
python tools\doctor.py --verbose                    # 出事時第一個跑這個
python -m d4t gui                                 # 開 Studio
python tools\make_sample.py C:\temp\lot --n 100     # 產合成資料試玩
```

**要移除的話**：把 `.venv\` 資料夾整個刪掉就好（沒有動到公司機原本的 Python），
或者把整個 `d4t-main\` 刪掉。d4t 不會寫入登錄檔，也不需要系統管理員權限。
唯一會留下的是快取資料夾 `C:\Users\你的帳號\.d4t\`（可以直接刪）。

相關文件：`docs/NO-GIT-SETUP.md`（沒有 git 怎麼取得與保存修改）、
專案根目錄的 `README.md`（d4t 是什麼、怎麼用）。

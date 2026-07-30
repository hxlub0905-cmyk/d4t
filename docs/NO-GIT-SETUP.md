# 在沒有 git 的機器上使用 ADEPT

適用情境：**公司機沒有 git（或 git 被擋）。** 整個 repo 只有純文字檔
（`.py` / `.md` / `.json` / `.toml` / `.txt` / `.yml` / 一份 `.klarf`），
沒有任何執行檔或二進位檔，不需要 git 也能跑。

> ## 先看這裡：你的機器下載得了東西嗎
>
> 這一份原本假設你可以按 GitHub 的「Download ZIP」。**實測遇到的環境連那個都
> 不行** —— `.zip` 被擋、`.py` 也被擋，等於什麼都下載不了，但**看得到 GitHub 上
> 的檔案而且可以按複製鈕**。完整的環境限制見 [`../AGENTS.md`](../AGENTS.md)。
>
> | 你的情況 | 跳到 |
> |---|---|
> | **什麼都下載不了**（只能看 GitHub + 複製）| **§0 用剪貼簿搬** ← 多數人在這裡 |
> | 下載得了東西，只有 GitHub 的 ZIP 不行 | §1 取得程式碼 |
> | 什麼都下載得了 | §1，按 Download ZIP 就好 |

---

## 0. 用剪貼簿搬（下載完全不通的時候）

三條路，用在不同時機 —— **不要每次都搬整包**：

### 0a. 第一次搬整包：一個檔案（推薦）

`bundle/ADEPT_bundle.py` —— **735 KB，一次複製就搬完整個 repo**。

1. 在瀏覽器打開 `https://github.com/hxlub0905-cmyk/ADEPT/blob/main/bundle/ADEPT_bundle.py`
2. 按檔案右上角的**複製鈕**
3. 貼進記事本，存成 `ADEPT_bundle.py`
4. `python ADEPT_bundle.py --list`  ← 先看它會寫哪些檔案，**不寫任何東西**
5. `python ADEPT_bundle.py`

它用 `lzma` + base64 壓過（stdlib，不需要裝東西）。為什麼是 lzma 而不是 gzip：
gzip 壓完 base64 是 991 KB，太貼近 GitHub 那個 1 MB 的顯示上限；lzma 是 735 KB。

**代價**：內容是 base64，記事本打開看不懂。**解包程式本身仍然是可讀的 Python**
（檔案最前面約 90 行），而 `--list` 讓你在它寫任何檔案之前就看得到清單。
想逐字讀過全部內容的話用下面那個純文字版。

### 0a-2. 同一件事的純文字版：六批

`bundle/ADEPT_part1of6.py` … `part6of6.py`：**沒有壓縮、沒有 base64**，
每個檔案的內容一行一行原樣躺在裡面（每行前面加一個 `#`，所以整份仍是合法的
Python），記事本打開往下捲就看得到。代價是 6 次複製。

對每一批做同一件事：

1. 在瀏覽器打開 `https://github.com/hxlub0905-cmyk/ADEPT/blob/main/bundle/ADEPT_part1of6.py`
2. 按檔案右上角的**複製鈕**（從已經載入的網頁複製，不會再連別的主機）
3. 貼進記事本，存成同名的 `.py`
4. `python ADEPT_part1of6.py`

**順序不重要，重複執行也沒關係。** 每一批解完會告訴你整個 repo 還缺幾個檔案，
全部到齊之後才會印「下一步」。

為什麼純文字版要分六批：**GitHub 不顯示超過 1 MB 的檔案**，而純文字整包是
2.4 MB —— 在那台機器上根本點不開來複製。每一批 < 420 KB。

兩種版本的每個檔案都帶 **git blob SHA-1**，貼歪或被截斷會**當場講出來**，
而且一個檔案都不會落地。

### 0b. 之後更新：先複製一個 12 KB 的清單

不要重跑 0a。`tools/FILELIST.txt` 是全部檔案的 SHA，只有 12 KB：

1. 複製 `tools/FILELIST.txt` 覆蓋掉舊的
2. `python tools/check_files.py`

它會列出**哪幾個檔案要重新複製**（缺少的、內容不一樣的），加 `--urls` 還會把
GitHub 的網址一起印出來，貼到瀏覽器就能開。所以更新一次是
「一次小複製 + 幾次針對性複製」。

### 0c. 只想跑格式探測：三支單檔腳本

要驗證 `CLAUDE.md` §8 那三個廠內假設，**不需要整個專案**。
`fab_probe/probe_klarf.py` / `probe_tiff.py` / `probe_stats.py` 各 24–46 KB、
stdlib-only、單檔，複製過去直接跑。輸出是純文字且預設遮蔽 Lot／Wafer／Device，
所以結果可以貼回開發端。

---

## 1. 取得程式碼（下載通得過的時候）

到 `https://github.com/hxlub0905-cmyk/ADEPT` → 綠色 **Code** 按鈕 →
**Download ZIP** → 解壓到任意資料夾。

解壓後會得到 `ADEPT-main\`，裡面就是完整程式碼。
GitHub 產生的 zip **不含 `.git` 資料夾**，所以裡面 174 個檔案全部是純文字，約 850 KB。

### 如果 Download ZIP 被公司擋掉

**這件事跟 repo 的內容不一定有關係**，先分辨是哪一種 —— 三種原因的處置完全不同：

| 先做這個測試 | 結果 | 那就是 |
|---|---|---|
| 直接開 `https://codeload.github.com/hxlub0905-cmyk/ADEPT/zip/refs/heads/main` | 這個網址被擋，但 `github.com` 的網頁看得到 | **主機層的封鎖**（最常見，已實際遇到）。看下面「主機層封鎖」那一段 |
| 隨便下載另一個無關的公開 repo 的 zip | 也被擋 | **政策層面禁止 .zip 這個類別**，跟哪個 repo 無關。走下面的替代路徑 |
| 上面兩個都正常，只有這個 repo 的 zip 被擋 | — | **DLP 掃到了內容**。看 §「DLP 掃內容」那一段 |

### 主機層封鎖 → 用 `tools/get_code.py`

**已知這是真的會發生的情況**（實際遇到過：`codeload.github.com` 被擋，
`github.com` 的網頁正常）。這種時候：

- **`.tar.gz` 不用試** —— 它在同一台主機上，換副檔名沒有用。
- 根治是**請 IT 放行 `codeload.github.com`**。它跟 `github.com` 是同一個信任範圍，
  只是 GitHub 把 archive 下載放在另一個網域。可以這樣寫給 IT：
  > 請將 `codeload.github.com` 加入允許清單。它是 github.com 的官方
  > archive 下載網域（按 Code → Download ZIP 時瀏覽器實際連線的主機），
  > 目前 `github.com` 已放行但 `codeload.github.com` 未放行，
  > 導致可以瀏覽程式碼但無法下載。

- 不想等 IT，就走 **`tools/get_code.py`**：它只用 **`raw.githubusercontent.com`
  一台主機**逐檔抓（送的是 `text/plain`，DLP 對它的規則跟 `application/zip`
  完全不同），而且**不需要 git、不需要任何套件**。

  怎麼拿到那支腳本（你連它也下載不了）：
  1. 在瀏覽器開 `https://github.com/hxlub0905-cmyk/ADEPT/blob/main/tools/get_code.py`
  2. 按檔案右上角的**複製鈕**（那是從已經載入的網頁複製，不會再連別的主機）
  3. 貼進記事本，存成 `get_code.py`
  4. `python get_code.py`

  ```
  python get_code.py                    # 抓到 .\ADEPT\
  python get_code.py --dest D:\tools    # 抓到別的地方
  python get_code.py --cafile corp.pem  # 公司有 TLS 中間攔截時
  ```

  抓下來的內容跟 GitHub 上**逐位元組相同**（實測比對過），而且那一份自己
  跑得起來（`pytest -q` 只會 skip 掉兩支需要 git 的清單檢查）。

  它會對每個檔案驗 **git blob SHA**。這不是龜毛 —— 被擋的 proxy 常常回一頁
  登入頁或警告 HTML，而且是 **HTTP 200**。那種東西寫進 `.py` 之後，症狀會變成
  「程式碼看起來都在，但 import 就爆語法錯誤」，而你完全不會歸因到下載。
  SHA 對不上就不落地，並且明講「這份程式碼不完整，不要用」。

  ⚠ 憑證錯誤請用 `--cafile` 指到公司的根憑證，**不要去關掉 TLS 驗證**
  （那會讓這支腳本變成一個把任意內容寫進磁碟的工具；有測試守著這件事）。

#### 逾時（WinError 10060）＝ 沒走 proxy，不是被擋

**實際遇到過。** 逾時的意思是「封包直接送出去、沒有人回應」。
如果你的**瀏覽器連得到 GitHub**，那答案幾乎一定是：
**這台機器要透過公司 proxy 才連得出去，而 Python 沒有走 proxy。**

原因：`urllib` 會讀 `HTTPS_PROXY` 環境變數與 Windows 登錄檔裡**手動設定**的
proxy，但**讀不到 PAC（自動設定指令碼）** —— 而公司幾乎都用 PAC。
瀏覽器懂 PAC，Python 不懂，所以同一台機器上一個通一個不通。

**Windows 上 `get_code.py` 會自己解 PAC**：沒有其他 proxy 設定時，它請 .NET
算出「連這個網址該走哪個 proxy」（`GetSystemWebProxy().GetProxy(url)` —— 瀏覽器
用的就是同一套設定），解得出來就直接用。開頭那行 `Proxy :` 會講它是怎麼來的。
PAC 檔通常有上百行條件判斷，而「哪一行適用於這個網址」正是 PAC 要算的東西，
不該由你手算。

自動解不出來（或不是 Windows）才需要自己找 proxy 位址：

```powershell
netsh winhttp show proxy
Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' |
    Select ProxyServer, AutoConfigURL
```

⚠ **不要**用 `pip config list` 來找 proxy：很多公司的 pip 是走**內部 PyPI 鏡像**
（`index-url` 指到內網），根本沒有 proxy 設定 —— 而且那個輸出裡常常**含帳號密碼**，
貼給別人看之前要遮掉。

`AutoConfigURL` 有值就是 PAC：**用瀏覽器打開那個網址**，在裡面找
`PROXY 主機:埠` 那一行。然後：

```powershell
python get_code.py --proxy http://主機:埠
# 或者設環境變數（pip 也吃這個，一次解決兩個問題）
$env:HTTPS_PROXY = 'http://主機:埠'
python get_code.py
```

#### 拒絕連線（WinError 10061）→ 換 PowerShell 版

**實際遇到過**，而且它跟逾時是不同的事：拒絕連線的意思是**位址找得到、封包也到
了，但那個埠上沒有東西在聽**。最常見的原因是 PAC 解出來的網址**沒有埠**，
於是 Python 用了預設的 80，而公司 proxy 幾乎不在 80。

這時候先試常見的埠（`8080` / `3128` / `8000` / `9090`），不行就**改用
PowerShell 版**：

```powershell
powershell -ExecutionPolicy Bypass -File .\get_code.ps1
```

`tools/get_code.ps1` 跟 `.py` 版是**同一份契約**（同一份 `FILELIST.txt`、
同樣驗 git blob SHA、同樣 atomic 寫入），差別在它走 .NET —— 也就是**瀏覽器用的
那一套網路堆疊**。三件 Python 做不到的事它原生就有：

| | `get_code.py` | `get_code.ps1` |
|---|---|---|
| 解 PAC | 借 .NET 算，只拿得到**第一個** proxy | 原生，多個候選會**依序 fallback** |
| proxy 的 Windows 整合驗證（NTLM / Kerberos）| ✗ | ✓ |
| TLS 版本 | 跟著 Python | 明確設 TLS 1.2（PS 5.1 預設 1.0，GitHub 收不了）|

所以判斷方式很簡單：**瀏覽器連得到 GitHub 的話，PowerShell 通常就連得到。**
`-ExecutionPolicy Bypass` 是必要的 —— PowerShell 預設不准跑腳本檔。
拿這支的方式跟 `.py` 版一樣：在 blob 頁按複製鈕、貼進記事本。

一行決定要不要走這條路（PowerShell 拿得到就代表值得）：

```powershell
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/hxlub0905-cmyk/ADEPT/main/tools/FILELIST.txt' -UseBasicParsing -OutFile t.txt
```

- 三台主機都被擋的話，剩下的路是**在有網路的機器上取得，用你搬 `wheels\` 的
  同一條路搬過來**（見 [`OFFLINE-INSTALL.md`](OFFLINE-INSTALL.md)）。

### 連 .zip 這個類別都被擋 → 單檔純文字包

**實測遇到過**：不只是 `codeload.github.com`，**從任何來源下載 `.zip` 都被擋**。
這種情況下「請 IT 放行 codeload」也沒有用（拿到的還是 zip），而 `get_code.py` /
`.ps1` 也要 proxy 通得過才行。能過的只剩「一個純文字檔」。

`tools/make_text_bundle.py` 在**有網路的機器上**把整個 repo 打成一個
`ADEPT_bundle.py` —— **沒有任何壓縮格式、沒有 base64**，每個檔案的內容原封不動
一行一行躺在裡面（每行前面加一個 `#`，所以整個檔案仍然是合法的 Python）。
你可以用記事本打開它往下捲，看得到每一個檔案。

```
python tools/make_text_bundle.py        # 產 ADEPT_bundle.py（約 2.4 MB 純文字）
```

把那個檔案帶到公司機（下載、郵件、隨身碟 —— 它就是一個 .py 檔），然後：

```
python ADEPT_bundle.py                  # 解到 .\ADEPT\
python ADEPT_bundle.py --list           # 先看裡面有什麼，不寫任何檔案
```

每個檔案都帶 **git blob SHA-1**，解開時逐檔驗過才落地。傳輸途中被動到（編輯器
另存、郵件過濾器改寫）會**當場講出來**，而不是給你一份安靜壞掉的程式碼。

格式刻意用**行數**而不是位元組數：這個檔案很可能在某個環節被把 LF 換成 CRLF，
而用位元組數的話那一換就會讓**第一個檔案之後的全部檔案**對不起來。
（有測試把「換過行尾還解得開」鎖住。）

### DLP 掃內容

如果只有這個 repo 的 zip 被擋，那要看的是**裡面有沒有公司的識別碼**。
`tests/fixtures/sample_real.klarf` 是唯一一份真實來源的檔案（它就是這樣抓到
KLARF variant D 的），它裡面的 Lot／Wafer／機台／device／**recipe 名稱**
（recipe 名稱通常編碼了層別與製程步驟）與缺陷分類名稱**都已經遮蔽成合成值**，
而且有一支測試守著（`tests/test_no_real_fab_data.py`）：

```
pytest -q tests/test_no_real_fab_data.py
```

加新 fixture 時那支測試會擋下沒遮蔽的值。**遮蔽是等長替換，測試只看結構不看值，
所以遮蔽不會弄壞任何斷言。**

⚠ 遮蔽只影響「現在的檔案」。**已經推上去的 git 歷史裡還留著原本的值** ——
DLP 掃的是下載下來的 zip（GitHub 的 zip 不含 `.git`，所以看不到歷史），
但如果要求是「repo 裡完全不能有」，那需要重寫歷史或把 repo 改成 private。

## 2. 安裝相依套件

```
cd ADEPT-main
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

需要 4 個套件：`numpy`、`opencv-python`、`tifffile`、`PySide6`。

**如果公司擋 pip 對外連線**（很常見）：改走離線 wheels ——
在有網路的機器上 `python tools/fetch_wheels.py`，把產生的 `wheels\` 資料夾帶進公司機，
再跑 `python tools/install_offline.py`。完整步驟與疑難排解見
**[`docs/OFFLINE-INSTALL.md`](OFFLINE-INSTALL.md)**。

裝完（或安裝失敗想知道卡在哪）都可以跑環境自檢：

```
python tools/doctor.py
```

它會逐項檢查 Python 版本、每個套件、Qt 能不能開視窗、資料夾權限，
每個沒過的項目都附一行「怎麼修」。

## 3. 確認能跑

```
python -m adept steps
```

會列出全部步驟卡片。看得到「影像段 IMAGE / 算法段 ALGO」就代表裝好了。

跑測試（可選，需要 `pip install pytest`）：

```
set QT_QPA_PLATFORM=offscreen
pytest -q
```

## 4. 產一份合成資料試玩（不需要真實 KLARF）

```
python tools\make_sample.py C:\temp\lot --n 100
```

會產生 `LOT_SYN.001`（KLARF）、`LOT_SYN.tif`（patch 影像）、
`ground_truth.json`（哪些是真缺陷，供你驗證算分效果）。

## 5. 開圖形介面

```
python -m adept gui
```

在 Studio 裡：**開啟 KLARF** 選剛才的 `LOT_SYN.001` → **載入範本（die-to-die）**
→ **試跑** → 拖下方的門檻線看 bin 數變化。

## 6. 命令列批次

```
python -m adept run examples\recipes\die_to_die_basic.json C:\temp\lot\LOT_SYN.001 ^
    --workers 4 --cache C:\temp\cache --csv features.csv
```

---

## 沒有 git 的情況下，怎麼保存你的修改

你的 recipe 存成單一 JSON 檔（Studio 裡「存 Recipe」），那才是你的心血結晶 ——
程式碼可以隨時重新下載，recipe 不行。建議把 `examples\recipes\` 底下的檔案
另外備份一份到你自己的資料夾。

如果改了程式碼（例如加了新的步驟卡片），把改動的 `.py` 檔另外複製一份留底；
之後在有 git 的機器上再合併回 repo。

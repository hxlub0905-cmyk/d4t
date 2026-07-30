# 在沒有 git 的機器上使用 ADEPT

適用情境：**公司機沒有 git（或 git 被擋），你習慣從 GitHub 按「Download ZIP」
把整包下載下來，直接用 Python 跑。**

ADEPT 完全支援這種用法 —— 整個 repo 只有純文字檔（`.py` / `.md` / `.json` /
`.toml` / `.txt` / `.yml` / 一份 `.klarf`），沒有任何執行檔或二進位檔，
不需要 git 也能跑。

---

## 1. 取得程式碼

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

  它會對每個檔案驗 **git blob SHA**。這不是龜毛 —— 被擋的 proxy 常常回一頁
  登入頁或警告 HTML，而且是 **HTTP 200**。那種東西寫進 `.py` 之後，症狀會變成
  「程式碼看起來都在，但 import 就爆語法錯誤」，而你完全不會歸因到下載。
  SHA 對不上就不落地，並且明講「這份程式碼不完整，不要用」。

  ⚠ 憑證錯誤請用 `--cafile` 指到公司的根憑證，**不要去關掉 TLS 驗證**
  （那會讓這支腳本變成一個把任意內容寫進磁碟的工具；有測試守著這件事）。

- 三台主機都被擋的話，剩下的路是**在有網路的機器上取得，用你搬 `wheels\` 的
  同一條路搬過來**（見 [`OFFLINE-INSTALL.md`](OFFLINE-INSTALL.md)）。

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

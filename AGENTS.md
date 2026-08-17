# AGENTS.md — 開發環境與限制

給任何要在這個專案上動手的人／agent。**先讀這一份**，再讀
[`CLAUDE.md`](CLAUDE.md)（怎麼動手）與 [`docs/HANDOVER.md`](docs/HANDOVER.md)
（為什麼長成這樣）。

這一份講的是**環境**：這個專案在什麼樣的機器上開發、在什麼樣的機器上執行，
以及那些限制怎麼決定了程式碼的形狀。不知道這些的話，很多設計看起來是多餘的
（為什麼工具都是 stdlib-only？為什麼有三種取得程式碼的方式？為什麼有個
`FILELIST.txt`？），然後就會被「順手簡化」掉。

---

## 1. 兩台機器

開發與執行**不在同一台機器上**，而且兩台的限制正好互補：

| | 家用機（開發） | 公司機（執行） |
|---|---|---|
| git | ✅ | ❌ 不能裝、不能執行 git 操作 |
| 網路下載 | ✅ 什麼都能下載 | ❌ **目前什麼都下載不了**（`.zip` 被擋、`.py` 也被擋）|
| 看得到 GitHub 網頁 | ✅ | ✅ **看得到檔案內容，而且可以按複製鈕** |
| 執行 `.py` | ✅ | ✅ |
| `pip install` | ✅ | ✅ 走**公司內部 PyPI 鏡像**（不是 proxy）|
| PowerShell | ✅ | ✅ |
| **真實資料** | ❌ **沒有** | ✅ **只有這裡有** |

最後一列是關鍵：**開發的地方沒有資料，有資料的地方不能開發。**

### 這件事的後果

- **全部功能都要能用合成資料開發與驗證。** `tools/make_sample.py` /
  `make_sample_rsem.py` 不是玩具，它們是唯一的開發資料來源。
  新功能如果只能用真實資料驗證，那它在家用機上就無法驗證 —— 設計要繞開這件事。
- **真實資料的假設必須「可探測」而不是「假設對了就好」。** 這就是 `fab_probe/`
  存在的理由：三支 stdlib-only 的單檔腳本，複製到公司機上跑，輸出純文字、
  預設遮蔽識別碼，所以結果可以貼回開發端。見 `CLAUDE.md` §8 的三個待驗證假設。
- **不能有「只在公司機上才能跑的建置步驟」。** 公司機不能下載東西，所以任何
  「執行前要先抓什麼」的設計都是死路。

---

## 2. 唯一的傳輸通道是剪貼簿

公司機下載不了東西，但**看得到 GitHub 上的檔案並且可以複製**。所以程式碼進去的
方式是：**在瀏覽器打開檔案 → 按右上角的複製鈕 → 貼進記事本 → 存成檔案**。

這條通道**只有一個**硬限制，設計必須繞開：

**一次複製一個檔案。** 190 幾個檔案不可能一個一個貼，所以要有整包的形式；
但更新的時候也不該重跑整套搬運，所以要有「只有這幾個變了」的機制
（`FILELIST.txt` + `check_files.py`）。

> ### 包的大小**不是限制**（2026-08-17 使用者確認）
>
> 以前這裡寫著第二條硬限制「GitHub 不顯示超過 1 MB 的檔案」，因為檔案瀏覽頁
> 超過 1 MB 就不顯示內容，那顆複製鈕也跟著消失。
>
> **使用者的做法是直接複製 raw**：
> `https://raw.githubusercontent.com/<owner>/ADEPT/main/bundle/ADEPT_bundle.py`
> 在瀏覽器打得開，全選複製一樣搬得走 —— 跟檔案有多大無關。
>
> 所以 **1 MB 不再是任何設計的約束**：不必為了它把文件搬進 `docs/history/`、
> 不必分批、也不必在寫東西之前先想「這會不會把包撐大」。`release.py` 仍然
> 每次報一句目前大小，那是**資訊**不是警告（它從來就不擋任何事）。
>
> `docs/history/` 那個目錄還是有用 —— 它讓公司機用不到的東西不佔搬運的體積、
> 也讓 diff 乾淨 —— 只是它現在是**整理**，不是**必要**。

**壓成一個檔案仍然是預設做法**（`ADEPT_bundle.py`：lzma + base64）：一次複製
就搬完，比「一個一個檔案點過去」快得多。代價是內容變成不可讀的 base64，
但**解包程式本身仍然是可讀的 Python**，而且 `--list` 可以在寫任何檔案之前
先列出它要寫什麼。

要在跑之前逐字看過內容的時候，`--split 400` 產的純文字數批仍然在
（每批 < 420 KB、記事本打開就讀得到）—— 那是為了**可讀性**，不再是為了大小。

### 三條路，用在不同的時機

| 情況 | 用什麼 | 成本 |
|---|---|---|
| **第一次搬整包** | `bundle/ADEPT_bundle.py`（壓縮成一個檔案）| **1 次複製** |
| 同上，但想先讀過內容 | 在家用機跑 `make_text_bundle.py --split 400` 產純文字數批 | 每批一次複製 |
| **之後更新** | 複製 `tools/FILELIST.txt`（12 KB）→ `python tools/check_files.py` → 它列出要重新複製哪幾個 | 1 次小複製 + 幾次針對性複製 |
| **只想跑格式探測** | 直接複製 `fab_probe/probe_*.py`（各 24–46 KB，stdlib-only 單檔，**不需要整個 repo**） | 1–3 次複製 |

最後一條常被忽略：要驗證 `CLAUDE.md` §8 那三個假設，**不需要搬整個專案**。

### 網路真的通的時候還有兩支

如果哪天 proxy／allowlist 放寬了，`tools/get_code.py`（Python）與
`tools/get_code.ps1`（PowerShell）可以逐檔抓下來，不必手動複製。
它們目前在這個環境下**過不了 proxy**，但寫進來的診斷是有用的資產 ——
連線失敗分六種，每一種的處置都不一樣（見 `docs/NO-GIT-SETUP.md`）。

---

## 3. 這些限制決定了哪些程式碼形狀

看到下面這些東西的時候，**它們不是過度設計，是上面那些限制的直接後果**：

| 設計 | 為什麼 |
|---|---|
| `tools/` 底下每一支都是 **stdlib-only** | 它們要在「套件還沒裝好」或「根本裝不了」的機器上跑。有測試（`test_offline_tools.py`）掃 module-level import 把這條鎖住 |
| **Python 3.9 相容** | 公司機的 Python 版本不由我們決定。⚠ 本機那道 `ast.parse(feature_version=(3,9))` **只檢查語法，不檢查標準函式庫的 API**（實例：`Path.write_text(newline=…)` 是 3.10+ 才有的，本機全綠、CI 的 3.9 job 才紅）。真正驗 3.9 的是 CI |
| 整個 repo **只有純文字檔** | 剪貼簿通道只搬得動文字；而且純文字才能在 GitHub 上被看到與複製 |
| `tools/FILELIST.txt`（git blob SHA） | 「哪幾個檔案變了」的唯一依據。它腐爛的代價是**公司機上安靜地少一個檔案** |
| 每一種搬運方式都**驗 SHA** | 剪貼簿與 proxy 都可能安靜地改掉內容（截斷、換行、攔截頁）。驗不過就不落地 |
| `bundle/` 裡有產生出來的複本 | 那是搬運品，不是內容。**已刻意排除**在 `FILELIST.txt` 與打包來源之外（不然會遞迴長大） |
| **repo 裡不得有廠內識別碼**（鐵則 8）| 這是唯一的傳輸通道，而資料只能往「進公司」的方向走，不能往外。`tests/test_no_real_fab_data.py` 守著；已經進了歷史的話見 §3.5 |

### 3.5 識別碼已經進了 git 歷史怎麼辦

**遮蔽現在的檔案不會動到歷史。** 舊的 commit 裡還是原值，`git log -p` 看得到。
真的要清掉就得**改寫歷史**，而那件事的代價要先知道：

- **所有 commit 的 SHA 都會變。** 任何已經 clone 過的人都要重新 clone；
  開著的 PR 會失效（要重開）。
- **GitHub 上舊的物件不會立刻消失** —— 用完整 SHA 的網址還點得到，
  直到 GitHub 自己回收。repo 是 private 的話，那也只有有權限的人點得到。

做法（**在家用機上**，用 `git filter-repo`）：

```bash
pip install git-filter-repo

# 替換規則。⚠ 這個檔案本身含有要保護的東西 ——
# 放在 **repo 外面**，做完就刪掉，絕對不要 commit。
cat > ~/redact.txt <<'RULES'
literal:真實的LOT==>AA0000.0X
literal:真實的機台==>TOOL01
RULES

# 先在複本上試，確認只有那幾行變了
git clone --no-local . /tmp/rewrite-test
cd /tmp/rewrite-test && git filter-repo --replace-text ~/redact.txt --force

# 確認乾淨了再對真的 repo 做
git filter-repo --replace-text ~/redact.txt --force
git push --force origin main
rm ~/redact.txt
```

**替換一律等長**（`QQ1234.5Z` → `AA0000.0X` 這種長度；左邊那個是編的，<!-- FAKE-ID -->
真值不會出現在這份文件裡）。不是為了好看：`klarf_core` 是
span-splice，長度變了不會壞，但等長讓「改寫前後只有那幾個字不同」這件事
一眼驗得出來 —— 用 `diff -r` 比同一個 commit 的樹，差異行數應該正好等於
識別碼出現的行數。

**先在 `git clone --no-local` 的複本上跑過**再對真的做。filter-repo 沒有 undo。

---

## 4. 每次改動之後的固定動作（**家用機**）

```bash
# ── 家用機（有 git）───────────────────────────────────────────
git add -A && python tools/release.py && git add -A
```

**這一節從頭到尾都是家用機的事。公司機不能執行 git 操作，也不需要跑這些。**
`release.py` 在沒有 git 的機器上會直接說「你跑錯機器了」並指向那台機器該跑的東西。

一行做完兩件事，**順序不能顛倒**（包裡面含著那份清單）：

1. `tools/FILELIST.txt` —— 公司機用它判斷「哪幾個檔案要重新複製」
2. `bundle/ADEPT_bundle.py` —— 整包壓成一個 `.py`（2026-08-16 是 888 KB），
   按複製鈕就搬得走。產完會報一行水位，見上面 §2 的警告

`git add` 要在前面：兩者都是從 `git ls-files` 產的，**還沒 add 的新檔案會安靜地
不在裡面** —— 公司機上就少一個檔案。`release.py` 會擋下這種情況並叫你先 add。

**有測試守著**（`test_the_transfer_files_are_up_to_date`）：忘了跑會紅，
而錯誤訊息就是上面那一行。過期不會有任何症狀，所以不能靠記得。

純文字分批版（`--split 400`，記事本讀得懂）**不再固定產出** —— 它每次更新會動到
3 MB，diff 全是噪音。需要逐字審內容的時候再產：

```bash
python tools/make_text_bundle.py --out bundle/ADEPT.py --split 400
```

---

## 4.5 哪一支在哪一台跑

`tools/` 底下的東西**分屬兩台機器**，混起來用會得到看不懂的錯誤：

| 工具 | 哪一台 | 要 git 嗎 | 做什麼 |
|---|---|---|---|
| `release.py` | **家用機** | ✅ 要 | 重產清單 + 搬運包（每次改完都跑）|
| `make_filelist.py` / `make_text_bundle.py` | **家用機** | ✅ 要 | `release.py` 底下的兩支，通常不直接叫 |
| `fetch_wheels.py` | **家用機** | ❌ | 抓 Windows wheels，帶 `wheels\` 過去 |
| `make_mgepi_real.py` / `validate_mgepi.py` | **家用機** | ❌ | 擬真 BSE 合成 lot（MG×EPI×spacer）＋可分性驗證（要 numpy/cv2）|
| `freeze_golden.py` | **家用機** | ❌ | 把現在算出來的 feature 表凍成黃金值（重構的安全網，見 `docs/history/plans/F9-dag-streams.md`）|
| `check_files.py` | **公司機** | ❌ | 哪幾個檔案跟 GitHub 上不一樣（要先複製 `FILELIST.txt`）|
| `install_offline.py` | **公司機** | ❌ | 用 `wheels\` 裝相依套件 |
| `doctor.py` | **公司機** | ❌ | 環境自檢 |
| `fab_probe/probe_*.py` | **公司機** | ❌ | 探測真實資料的格式（單檔，不需要整個 repo）|
| `get_code.py` / `.ps1` | 公司機（**目前用不了**）| ❌ | 網路通的時候才逐檔抓 |

判準很簡單：**要 git 的都在家用機。** 公司機那幾支一律 stdlib-only 且不碰 git。

### 公司機上改的東西怎麼回來

公司機不能 push。它能做的是**把文字複製出來**（跟 `fab_probe` 的輸出同一條路）：

- **recipe**（Studio 存出來的 JSON）—— 小檔案，用記事本打開全選複製，貼回家用機
- **`fab_probe` 的輸出** —— 本來就是設計成純文字可以貼出來的
- **CSV／報表** —— 太大就先在公司機上看，把結論帶回來就好

所以「在公司機上長期改程式碼」不是這個專案支援的工作方式 ——
**程式碼在家用機改，recipe 與量測結果從公司機帶回來。**

---

## 5. 開發流程本身

見 [`CLAUDE.md`](CLAUDE.md) §6。**測試只在家用機上跑**（公司機沒有 pytest，
也不該把時間花在那裡）：

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q       # Windows 不用設那個變數
```

一個環境上的注意事項：UI 測試在**單一行程裡跑整套**會累積 Qt 記憶體而變得極慢
（容器裡實測會從 100 秒變成十幾分鐘）。分段跑就正常。這不是測試的問題。

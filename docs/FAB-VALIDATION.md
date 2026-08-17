# 待廠內驗證的假設

開發全程用合成資料（真實資料不能出廠）。原本有三條假設，**2026-07-30 使用者結掉了
前兩條**（一條確認、一條改設計繞開）；第 3 條與 **2026-08-17 新增的兩條（#4 位元深度、
#5 多於兩頁時的頁序）**要在廠內用 `fab_probe/` 探測腳本確認。
那三支腳本是 stdlib-only 單檔、輸出純文字且預設遮蔽 Lot/Wafer/Device 等識別碼，
設計成可以直接複製貼出廠區（細節與資料外流說明見 `fab_probe/README.md`）：

| 假設 | 現況 | 用哪支腳本確認 |
|---|---|---|
| ~~1. EBI patch 的 page→channel 對應~~ | ✅ **已確認（2026-07-30）**：第一張 = test、第二張 = ref。`load_dataset` 的 `channel_order` 預設就是對的。參數保留是給「一顆多於兩頁」或站點慣例不同用的，不再是「怕猜錯」 | — |
| ~~2. `nm_per_px` 來源~~ | ✅ **已用設計繞開（2026-07-30）**：不再需要這個值。見下面「單位一律 pixel」 | —（`probe_*.py` 若順手看到仍會回報，那是加分不是前提）|
| 3. KLARF 變體 | `klarf_core` 已知四種（含 M5 修正的 variant D） | `probe_klarf.py` 的 image-layout 變體判定與證據 |
| ~~4. 影像的位元深度~~ | ✅ **已確認（2026-08-17）：8-bit。** 所以下面那件事不會發生在現在的資料上 —— 但**程式不該把它當成保證**，要補一道「非 8-bit 就講一句話」的防呆（成本幾行，擋掉的是安靜算出垃圾）。原本的風險紀錄留著：兩條載入路徑都寫死 8-bit 假設：`ebi_patch` 走 `to_uint8` → 一張 12-bit 的圖 **93.8% 的像素飽和成 255**；`rsem`/`folder` 走 `imageio.load_gray` → **每張圖各自 MINMAX 拉伸**，於是亮度砍半的圖載進來平均值一模一樣（兩張圖之間不再可比，而那是 `test − ref` 的前提）。實測數字與三種修法見 [`plans/F11-phase2-features.md`](plans/F11-phase2-features.md) §3.1.8 | 待補（bit depth 在 TIFF 標頭裡，一支腳本讀得到；順手可一起回答壓縮方式與尺寸是否逐顆相同）|
| 5. 一顆多於兩頁時的頁序 | ⏸ **擱置**（2026-08-17：「我決定我暫時不做 multi channel」）——假設本身留著，因為那種資料真的送進來時還是要知道。使用者口述：**1 BSE + 4 SE，BSE 固定在第 2 頁**，SE 順序無所謂，**沒有 ref**。假設 #1 只確認過「兩頁」的情形。`channel_map`（F11 Input-1）會讓這件事變成 recipe 裡的設定，而**頁數與宣告不符時要擋下來**，不准照順序硬套 | 待補（同上那支腳本：每顆幾頁、各頁尺寸與平均灰階）|

### 單位一律 pixel，換算在輸出那一刻由使用者填（2026-07-30）

`nm_per_px` 在 KLARF 裡找不到來源，而舊做法是「找不到就吐 0」——
`cd_measure` 在沒有它的時候照樣吐 `cd_x_nm` / `cd_y_nm` / `area_nm2` 三個 **0**。
那是最糟的一種缺值：**0 是個看起來很像答案的答案**，它進得了分數表達式、
寫得進 DSIZE 欄，一路安靜到最後。而實務上它每一顆都是 0。

現在的分工：

- **pipeline 全程用 pixel。** `cd_measure` 吐 `cd_x_px` / `cd_y_px` / `area_px`
  （`area_px` 是新的 —— 以前只在算 nm 的時候用到，沒有吐出來）。
  卡片裡不做單位換算，**任何 `*_nm` 特徵都不該再出現**。
- **換算只發生在輸出。** Export 精靈的 DSIZE 那一列多一格 `× scale`
  （`klarf_out` 的 `size_scale`，CLI 是 `--size-scale`），預設 `1` = 原樣寫 pixel。
  要寫 nm 就把 nm/px 填進去 —— **那個數字只有站點自己知道**，所以它是一格輸入，
  不是一個猜出來的欄位。計畫書會把換算寫進 plan.notes，因為「這一欄是什麼單位」
  不能只存在按下去那個人的腦子裡（鐵則：寫回前一定先預覽變更）。

舊 recipe 若在分數表達式裡引用 `cd_x_nm`，`validate()` 會出 `unknown-feature`
warning 指名它 —— 那正是要看到的（它以前恆為 0，那份分數本來就是錯的）。

`core/calibration.py`（MMH 來的 nm/px profile 管理）**沒有被刪**：哪天真的量出
站點的 nm/px，它就是存那個值的地方，Export 那一格可以從 profile 帶預設值進來。

**每遇到一種新變體 → 做成最小化合成 fixture → 永久回歸測試**（見
`tests/test_klarf_variant_d.py` 的寫法：先斷言「這份檔案確實是該變體」當前提，再測行為）。

---

## 部署到受限的廠內機器

**完整的環境限制看 [`AGENTS.md`](../AGENTS.md)** —— 開發在家用機（有 git、能下載、
但**沒有真實資料**），執行在公司機（**只有那裡有資料**，但不能裝 git、
目前什麼都下載不了）。唯一的傳輸通道是**在 GitHub 上看到檔案並按複製鈕**。

三條路，用在不同時機：

| 情況 | 用什麼 |
|---|---|
| 第一次搬整包 | `bundle/ADEPT_bundle.py`（單檔，lzma + base64）—— **1 次複製**就搬完。包的大小不是限制（使用者直接複製 raw；見 [`AGENTS.md`](../AGENTS.md) §2）|
| 之後更新 | 複製 `tools/FILELIST.txt`（12 KB）→ `python tools/check_files.py` → 它列出要重新複製哪幾個 |
| 只想跑格式探測 | 直接複製 `fab_probe/probe_*.py`（stdlib-only 單檔，**不需要整個 repo**）|

網路哪天通了還有 `tools/get_code.py` / `.ps1`（逐檔抓）。其餘對應設計：

- 整個 repo **只有純文字檔**（`.py`/`.md`/`.json`/`.toml`/`.txt`/`.yml` + 一份 `.klarf`），
  所以 GitHub「Download ZIP」下載得下來（那份 zip 不含 `.git`；170 個檔案、約 830 KB）。
  **不要把 `.git` 打包給使用者** —— 二進位 pack 物件 + `hooks/*.sample` 腳本會觸發 DLP。
- **「純文字」是必要條件，不是充分條件。** DLP 也掃**內容**，而最容易破功的地方是
  測試 fixture：一份真實的 KLARF 帶著 Lot／Wafer／機台／device／**recipe 名稱**
  （通常編碼了層別與製程步驟）、缺陷分類名稱，甚至廠區代號 —— 而那些值對測試
  完全沒有用（`test_klarf_variant_d.py` 斷言的全是結構）。已全部遮蔽，
  並由 `tests/test_no_real_fab_data.py` 守著（白名單 + 合成命名規則，
  **不是列出不准出現的字** —— 那等於把要保護的東西寫進 repo）。
- Download ZIP 是從 **`codeload.github.com`** 出來的，不是 `github.com`。
  「以前下載得到、現在被擋」最常見的原因是 proxy allowlist 只放了後者，
  跟 repo 內容無關。分辨方式與替代路徑見 `docs/NO-GIT-SETUP.md`。
- **連 zip 都下載不了**（實際遇到：proxy 只放行 `github.com`，沒放 `codeload`）→
  `tools/get_code.py`：只用 `raw.githubusercontent.com` **一台主機**逐檔抓，
  每個檔案對 `tools/FILELIST.txt` 的 git blob SHA 驗過才落地。
  驗 SHA 不是龜毛：被擋的 proxy 常常回一頁 HTML 而且是 **HTTP 200**，
  那種東西寫進 `.py` 之後症狀是「程式碼都在但 import 就語法錯誤」。
  清單由 `tools/make_filelist.py` 產生，有測試擋它腐爛（見 §6）。
- 相依套件走離線 wheels：`tools/fetch_wheels.py`（有網路的機器）→ 帶 `wheels\` 過去 →
  `tools/install_offline.py`（廠內機器）。全部 stdlib-only，因為它們在套件裝好之前就要能跑。
- 裝不起來或跑不動時的第一件事：`python tools/doctor.py` —— 逐項 ✓/✗ 並附「怎麼修」。
  最常見的失敗是 **wheels 的 Python 版本與機器上的不符**（cp39 的輪子配 py3.12），
  `install_offline.py` 會在 pip 之前就攔下來並講清楚。
- 詳細步驟：`docs/OFFLINE-INSTALL.md`；不用 git 的取得方式：`docs/NO-GIT-SETUP.md`。

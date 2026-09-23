# 交接：把 Pitch helper 搬成自己的 repo

**狀態：資料夾已經抽好（`apps/pitch`），兩邊都還在。A 與 B 都還沒做。**

使用者 2026-09-23：

> 我之後帶走後 d4t 會把 pitch helper 移除，就等於 pitch helper 直接開新 repo，
> 原來 d4t 不會有殘留。

這一份是那件事的**操作手冊**。它有一個明確的壽命：**B 做完之後，連同它自己一起
刪掉**。

---

## 0. 現在是什麼狀態

| | |
|---|---|
| `apps/pitch/` | 完整、可以單獨跑的複本（27 支模組、12,786 行）。`python main.py` 就開得起來 |
| `apps/simgen/` | 同樣抽了一份（11 支模組）。⚠ **使用者沒有要求移除它** —— 它要不要走是另一個決定 |
| `d4t/ui/pitch_helper.py` 等 | **還在**，而且是目前唯一有測試守著的那一份 |
| `tools/extract_app.py` | 抽取工具（一次性） |
| 一致性 | `tests/test_measure_period_is_public.py::test_the_taken_away_copy_is_the_same_algorithm` 釘著兩份的演算法一字不差 |

**順序是 A → B，不可以反過來。** 反過來的話，萬一新 repo 少帶了什麼，來源已經
沒了。

---

## A. 開新 repo

### A.1 動手

```bash
cp -r apps/pitch ~/pitch-helper
cd ~/pitch-helper
git init && git add -A && git commit -m "Initial commit: extracted from d4t"
pip install -r requirements.txt
python main.py              # 確認開得起來
```

### A.2 ⚠ 抽取工具**不會**帶的東西，手動補

| 補什麼 | 從哪裡 | 為什麼 |
|---|---|---|
| **`docs/F120-pitch-helper.md`** | `d4t/docs/plans/F120-pitch-helper.md` | **最重要的一件**。十七輪的決策紀錄，每一條都是量出來的。沒有它，下一個人會把已經試過而且被否決的東西再做一次（例：`Auto` 軸向、常駐的「What it decided」面板、hero 版面）|
| `LICENSE` | `d4t/LICENSE` | 目前沿用專有／內部條款 |
| 測試 | `d4t/tests/test_ui_pitch_helper.py`（129 條）、`tests/test_period_confidence_at.py`（13 條）| 抽取工具只帶程式碼。這兩支要改 import（`d4t.ui.…` → `pitchapp.ui.…`）|
| `.gitignore` / CI | 自己寫 | d4t 的不一定合用 |

改 import 的最小做法：

```bash
sed -i 's/\bfrom d4t\.ui\./from pitchapp.ui./g; s/\bfrom d4t\.core\./from pitchapp.core./g;
        s/\bfrom d4t\.ui import\b/from pitchapp.ui import/g;
        s/"d4t\.ui\./"pitchapp.ui./g' tests/*.py
```

⚠ 測試裡有**字串形式**的模組名（`pytest.importorskip("d4t.ui.pitch_core")`、
`monkeypatch.setattr("d4t.ui....")`），`grep import` 找不到它們 —— 跑一次就知道。

### A.3 給 agent 的話（可以直接貼）

> 這個 repo 是從 d4t 抽出來的 pitch helper（`tools/extract_app.py` 抽的）。
> 先讀 `README.md` 跟 `pitchapp/ui/pitch_helper.py` 的檔頭。
>
> **動版面之前先讀 `docs/F120-pitch-helper.md`** —— 那是這個工具十七輪的決策
> 紀錄，裡面每一條都是量出來的不是挑的（例：`Auto` 軸向被拿掉是因為實測它的
> 門檻從來不會咬；格線是兩色線是因為沒有任何單色在灰階 SEM 上到處看得見）。
> 不讀它就會把被否決過的東西再做一次。
>
> 規矩沿用 d4t：core 不 import Qt、Python 3.9 相容語法、每個參數的 help 必填、
> 寫檔 atomic、`except` 之後不 raise 不等於不記（`core/log.swallowed`），
> 以及最重要的**同一件事只寫在一個地方**。
>
> 我要加 ⟨功能⟩。

### A.4 A 做完的判準

```bash
cd ~/pitch-helper
python -m pytest -q                       # 帶過去的測試全綠
python main.py                            # 視窗開得起來、量得出數字
grep -rn "\bd4t\b" pitchapp/ --include="*.py" | grep -v "^.*:.*#"   # 應該是空的
```

---

## B. 從 d4t 移除

**A 全綠之後才做。**

### B.1 整支刪掉

```
d4t/ui/pitch_helper.py
d4t/ui/pitch_core.py
d4t/ui/assets/pitch.svg
tests/test_ui_pitch_helper.py
tests/test_standalone_apps.py
tools/extract_app.py
# tests/test_period_confidence_at.py  ← 看 B.5 怎麼決定
apps/                                  # 整個目錄（pitch 與 simgen）
docs/HANDOVER-PITCH-SPLIT.md           # 這一份，最後刪
```

`docs/plans/F120-pitch-helper.md` **不要刪，搬到 `docs/history/plans/`**
（`tests/test_plan_docs.py` 的規矩：做完不再改的計畫書搬進歷史）。

### B.2 逐行改掉

| 檔案 | 改什麼 |
|---|---|
| `d4t/__main__.py` | `_cmd_pitch()` 整支 ＋ `sub.add_parser("pitch", …)` 那一段 |
| `d4t/ui/branding.py` | `PITCH_ICON_PATH`、`pitch_icon()`、`__all__` 裡那兩個名字 |
| `d4t/ui/theme.py` | QSS：`QLabel#pitchName` / `#pitchState` / `#pitchAnswer` / `#pitchAnswerSub` / `#pitchAnswerUnit`、`QDoubleSpinBox#pitchPixelSize`（兩條）；以及 `font_answer` 這個 token（**只有 helper 在用**）|
| `tests/test_ui_branding.py` | 六條 `test_the_pitch_icon_*` |
| `tests/test_ui_window_policy.py` | `PitchHelperWindow` 那一列（`_SIDE_BY_SIDE` 與說明表）|
| `tests/test_measure_period_is_public.py` | `test_the_taken_away_copy_is_the_same_algorithm` 整支；`test_a_one_dimensional_layout_agrees_too` 裡那段 `pitch_core` 的斷言（⚠ **前半段不要刪** —— 它驗的是 `build_golden_cell` 對一維的處置，跟 helper 無關）|
| `docs/ARCHITECTURE.md` | 視窗政策表的 `PitchHelperWindow` 那一列；目錄樹的 `pitch_helper.py`、`pitch_core.py`、`apps/` 三段 |
| `README.md` | `python -m d4t pitch` 那一行 |
| `AGENTS.md` | 機器對照表的 `extract_app.py` 那一列 |
| `CLAUDE.md` | §0 表格裡指向這一份的那一列（如果有加）|

### B.3 ⚠ 註解裡提到 `pitch_helper` 的幾處 —— 改字，**不要改行為**

這幾行是**解耦的理由**，而那些解耦 d4t 自己也受益，所以留著：

```
d4t/ui/crop_dialog.py:45      from .icons import apply_button_cursors   # 不走 widgets 轉出口（見 pitch_helper）
d4t/ui/lattice_dialog.py:34   同上
d4t/ui/gc_generator.py:50     from .image_view import to_uint8         # 同上
d4t/core/algo/golden.py:57    BLURRED_BELOW 搬家的理由裡提到 pitch_helper
d4t/core/algo/template.py:317 measure_period 為什麼公開
```

把「見 `pitch_helper`」換成「見 `docs/history/plans/F120-pitch-helper.md`」就好。

### B.4 ⚠ 三個**不要刪**

| | 為什麼 |
|---|---|
| `d4t/core/algo/period.py`、`period2d.py`、`golden.py` | **模板那條路在用**：`algo/template.py` 與 `ui/lattice_dialog.py` 都 import 它們。`template.measure_period` 也是 —— `build_golden_cell`／`template_dialog`／`roi_reference` 全走它 |
| `d4t/core/export/ramps.py` | 色階的家。它是為了抽取才拆的，但 d4t 自己也受益：`ui/image_view.py` 不再為了一個顏色函式 import 報表產生器（省 10 支模組、7,672 行）|
| 那四行 `widgets` 轉出口的解耦 | 同上，d4t 自己也受益 |

### B.5 ⚠ `confidence_at` —— 一個要自己決定的

**先更正一件事**：這一份的早期版本（以及 `apps/README.md`、
`F120-pitch-helper.md` §29.4）寫著「`algo/period.confidence_at` 不要刪，模板那條
路也在用」。**那是錯的。** 實際掃過：

```
$ grep -rn "confidence_at(" --include="*.py" d4t/ tools/ | grep -v algo/period.py
d4t/ui/pitch_helper.py:1275
d4t/ui/pitch_helper.py:1276
```

**唯一的呼叫者是 pitch helper。** 所以它跟著走是合理的，兩個選擇：

* **一起刪**（`confidence_at` ＋ `tests/test_period_confidence_at.py` 13 條）——
  乾淨，符合「d4t 不會有殘留」。⚠ 它跟 `_analyze_axis` 共用私有 helper，刪的時候
  只刪那一支公開函式，**不要動** `_analyze_axis` 那一串。
* **留著** —— 它是一支 13 條測試守著、20 行的純函式，留著的成本接近零，而「打進
  去的那個週期在這張圖上拿幾分」是個會再被問到的問題。

**建議：一起刪。** 理由是使用者說的那一句「原來 d4t 不會有殘留」—— 一支沒有人
叫的公開 API 正是殘留，而它在新 repo 裡活得好好的。

### B.6 給 agent 的話（可以直接貼）

> 把 pitch helper 從 d4t 移除 —— 它已經搬進獨立的 repo 了，
> 照 `docs/HANDOVER-PITCH-SPLIT.md` 的 B 節做。
>
> ⚠ 特別注意 B.4（三個不要刪：`algo/period`＋`period2d`＋`golden`、
> `core/export/ramps.py`、那四行 `widgets` 解耦 —— 模板那條路在用，而且 d4t
> 自己也受益）與 B.5（`confidence_at` 只有 helper 在用，建議一起刪）。
>
> 刪完跑 B.7 那一組。

### B.7 B 做完的判準

```bash
ruff check
python tools/typecheck.py                       # 上限那個數字可能要往下調
python tools/freeze_golden.py --check           # 三份要全綠 —— 刪東西不准改到數字
python -m pytest -q --ignore-glob="*test_ui_*"  # CI 跑的就是這一道
python tools/run_tests.py                       # 全套逐檔
git add -A && python tools/release.py && git add -A
```

**再掃一次殘留**（應該全部是空的）：

```bash
# ① 指向「那個工具」的識別字
grep -rn "pitch_helper\|pitch_core\|PitchHelper\|PITCH_ICON\|pitch_icon\|pitch\.svg" \
     --include="*.py" --include="*.md" d4t/ tools/ tests/ docs/ *.md
# ② QSS 的 objectName 與只有 helper 在用的 token
grep -rn "pitchAnswer\|pitchName\|pitchState\|pitchPixelSize\|font_answer" d4t/ui/theme.py
# ③ CLI 的子命令、README 的那一行、AGENTS 的工具列、CLAUDE §0 的那一列
grep -rn '"pitch"' d4t/__main__.py
grep -rn "d4t pitch\|HANDOVER-PITCH-SPLIT\|extract_app" README.md AGENTS.md CLAUDE.md
# ④ 整支該消失的
ls apps tools/extract_app.py docs/HANDOVER-PITCH-SPLIT.md \
   tests/test_standalone_apps.py docs/plans/F120-pitch-helper.md 2>&1
```

四道**全部應該是空的／找不到檔案**。①寫這一份的時候命中 18 個檔案，
B.1／B.2／B.3 把它們全部點到名了 —— 有漏的話是這份清單過期了，不是可以略過。

⚠ **`pitch` 這個字本身不是殘留** —— 它是領域術語（cell pitch），`algo/period.py`、
`tools/make_sample.py`、一堆測試裡到處都是，那些都要留。判準是「它指的是**那個
工具**，還是**那個量**」。

---

## C. 這一份自己

B.1 把它刪掉。它的工作到那時候就結束了 —— 一份講「怎麼搬家」的文件留在搬完的
房子裡，只會讓下一個人以為還有東西要搬。

# `apps/` —— 可以帶走的獨立工具

這裡每一個子資料夾都是**一個完整、可以單獨跑的程式**。整個資料夾複製到任何
地方（或 `git init` 開成一個新 repo）都跑得起來，不需要 d4t。

| 資料夾 | 是什麼 | 大小 | d4t 裡的對應 |
|---|---|---|---|
| [`pitch/`](pitch/) | **Pitch helper** —— 丟一張圖進去，回答它的 cell period | 27 支模組 | `python -m d4t pitch` |
| [`simgen/`](simgen/) | **Golden Cell generator** —— 從一張 GC 產一整批模擬資料 | 11 支模組 | `python -m d4t simgen` |

```bash
cd apps/pitch && pip install -r requirements.txt && python main.py
```

## 為什麼這裡可以有「第二份」

⚠ 這個 repo 的頭號鐵則是**同一件事只寫在一個地方**，而這裡看起來違反了它。
沒有違反，理由是使用者 2026-09-23 講的那一句：

> 我之後帶走後 d4t 會把 pitch helper 移除，就等於 pitch helper 直接開新 repo，
> 原來 d4t 不會有殘留。

也就是說這是一次**搬家的中繼狀態**，不是一個長期的雙份安排。搬完之後 d4t 這邊
的那一份會刪掉，剩下的就只有一個家。

**所以不要把 `apps/` 當成一個可以長住的地方。** 它是搬家的箱子。

## 怎麼重抽

```bash
python tools/extract_app.py --list          # 抽得出來的有哪些
python tools/extract_app.py pitch  apps/pitch
python tools/extract_app.py simgen apps/simgen
```

那一支做的是兩件手工最容易做錯的事：**相依閉包**（漏一支要等到跑到那條路才炸）
與 **import 改寫**。它另外擋兩件事：`branding.py` 名字裡寫著的資產沒被複製
（少一個不會報錯，只是安靜地沒有圖示），以及 `RENAMES` 那張表沒套用完
（來源改過了，表沒跟上 ⇒ 帶走的那份會留著一句假話）。

## 帶走的時候

1. `cp -r apps/pitch ~/pitch-helper && cd ~/pitch-helper && git init`
2. 補一份 `LICENSE`（目前沿用 d4t 的專有／內部條款）
3. 回頭把 d4t 這邊的那一份刪掉 —— 清單在
   [`docs/plans/F120-pitch-helper.md`](../docs/plans/F120-pitch-helper.md) §29

`tests/test_standalone_apps.py` 守著這幾件事：資料夾裡沒有任何 `import d4t`、
相對 import 指到的每一支都在、沒有一句話指向 d4t Studio 裡的東西、
`branding` 點名的資產都在，以及**把 `d4t` 從 import 路徑上擋掉之後視窗真的開得
起來**（這台機器裝著 d4t，不擋的話那一條永遠是綠的）。

---

## 之後怎麼跟 agent 說

兩件事分開講，因為它們**該在不同的 repo 裡做**。

### A. 在新 repo 裡繼續開發 pitch helper

在**新 repo** 的 session 裡說：

> 這個 repo 是從 d4t 抽出來的 pitch helper（`tools/extract_app.py` 抽的）。
> 先讀 `README.md` 跟 `pitchapp/ui/pitch_helper.py` 的檔頭。
> 我要加 <你要的功能>。
>
> 規矩沿用 d4t 的：`d4t/CLAUDE.md` 的鐵則 1／2／3／5／7（core 不 import Qt、
> Python 3.9 相容語法、每個參數的 help 必填、寫檔 atomic、不 raise 不等於不記），
> 以及「同一件事只寫在一個地方」。
> UI 的設計理由在 `docs/F120-pitch-helper.md`（從 d4t 帶過來的那一份）——
> **動版面之前先讀它**，裡面每一條都是量出來的，不是挑的。

⚠ **記得把 `docs/plans/F120-pitch-helper.md` 一起帶過去**（抽取工具不會帶文件）。
那一份是這個工具十七輪的決策紀錄，沒有它，下一個人會把已經試過而且被否決的東西
再做一次。

### B. 把 d4t 這邊的 pitch helper 移除

在 **d4t 的** session 裡說：

> 把 pitch helper 從 d4t 移除 —— 它已經搬進獨立的 repo 了。
> 清單在 `docs/plans/F120-pitch-helper.md` §29.4，照著做。
>
> ⚠ 三件要特別小心的：
> 1. `algo/period.confidence_at`、`algo/period2d`、`algo/golden`、
>    `algo/template.measure_period` **不要刪** —— 模板那條路（`template_dialog`、
>    `roi_reference`、`build_golden_cell`）也在用。
> 2. `core/export/ramps.py` 與那道 `widgets` 轉出口的解耦**留著** ——
>    它們是為了抽取才做的，但 d4t 自己也受益（`image_view` 不再 import 報表產生器）。
> 3. `apps/` 與 `tools/extract_app.py` 本身也要刪 —— 它們是搬家的箱子。
>
> 刪完跑：`ruff check`、`python tools/typecheck.py`、
> `python tools/freeze_golden.py --check`、`python -m pytest -q --ignore-glob="*test_ui_*"`、
> `python tools/run_tests.py`，然後 `git add -A && python tools/release.py && git add -A`。

⚠ **A 做完再做 B。** 反過來的話，萬一新 repo 少帶了什麼，來源已經沒了。

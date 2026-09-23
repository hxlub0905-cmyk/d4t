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

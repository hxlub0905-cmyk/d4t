# Pitch helper

丟一張圖進去，回答它的 cell period。

```bash
pip install -r requirements.txt
python main.py
```

## 這個資料夾是什麼

它是一個**完整、可以單獨帶走的程式** —— 整個資料夾複製到任何地方都跑得起來，
不需要 d4t。

它由 `tools/extract_app.py` 從 d4t 抽出來（2026-09-23），而那是一次性的搬家：
d4t 那邊之後會把這個工具移除，所以**這裡是唯一的家**，不會有兩份要對。

## 裡面有什麼

`pitchapp/` 底下的目錄形狀跟 d4t 一樣，所以從 d4t 帶過來的程式碼一個字都沒改
（只有 `import d4t.…` 換成 `import pitchapp.…`）：

* `pitchapp/core/` — 純運算，**不 import Qt**
* `pitchapp/ui/` — 視窗與元件

共 27 支模組、12,786 行。

## 相依

* Python 3.9+
* 見 `requirements.txt`

## 授權

跟 d4t 同一份（專有／內部）—— 見原 repo 的 `LICENSE`。

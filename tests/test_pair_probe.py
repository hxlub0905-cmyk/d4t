# F15 驗收工具的驗收 — authored 2026-08-20.
"""`tools/pair_probe.py` 是拿真實資料回答四個問題的那支工具，所以**它自己得先
是對的**：報告上寫「stage offset 中位數 (12, -7)」的時候，那必須真的是 12 與
−7，而不是一個看起來很合理的數字。

所以這一份自己造一份「RSEM 那樣的第二份」——**每一張大圖裡真的藏著主 lot 的
那一塊 patch**，位置是我們自己放的 —— 然後看報告有沒有把它讀出來。

（合成資料證明不了真實資料會怎樣；它證明的是**這支工具沒有在說謊**。真實資料
的答案要靠使用者在公司機上跑那一次。）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

import make_sample                                       # noqa: E402
import make_sample_rsem as rsem                          # noqa: E402
import pair_probe                                        # noqa: E402
from d4t.core.ingest.dataset import load_dataset         # noqa: E402
from d4t.core.ingest.imageio import save_gray            # noqa: E402

#: 我們自己放進去的 stage offset（像素）與座標抖動（nm）。
OFF_X, OFF_Y = 12, -7
JITTER_NM = 120
FOV = 384


class _Args:
    """`pair_probe.probe()` 吃的那組參數（argparse 的 Namespace 太囉唆）。"""

    def __init__(self, main, second, **over):
        self.main, self.second = str(main), str(second)
        self.n, self.workers = 8, 1
        self.tol_nm, self.within, self.candidates = 500.0, 15.0, 1
        self.channel, self.second_channel = "test", ""
        self.nm_per_px = self.second_nm_per_px = 0.0
        self.carry, self.csv, self.reveal = "", "", False
        self.__dict__.update(over)


def _second_lot(main_paths, out_dir, scale=1.0):
    """造一份「大圖」的第二份 lot：每張圖裡藏著主 lot 那一顆的 patch。

    座標跟主 lot 一樣（＋一點抖動，模擬兩台機台報的位置本來就差一點），
    而 patch 放在**圖中心 + (OFF_X, OFF_Y)** —— 那就是 stage 沒對準的那一點。
    """
    import cv2

    ds = load_dataset(main_paths["klarf"])
    img_dir = os.path.join(str(out_dir), "images")
    os.makedirs(img_dir, exist_ok=True)
    rng = np.random.default_rng(3)
    rows = []
    for k, item in enumerate(ds.items):
        patch = item.load("test")
        if scale != 1.0:
            patch = cv2.resize(patch, (int(round(patch.shape[1] / scale)),
                                       int(round(patch.shape[0] / scale))))
        ph, pw = patch.shape[:2]
        canvas = rng.integers(0, 255, (FOV, FOV)).astype(np.uint8)
        x = (FOV - pw) // 2 + OFF_X
        y = (FOV - ph) // 2 + OFF_Y
        canvas[y:y + ph, x:x + pw] = patch
        name = "DEF_%04d.png" % (k + 1)
        save_gray(os.path.join(img_dir, name), canvas)
        rows.append(rsem._defect_row(
            str(k + 1), int(item.xrel_nm) + JITTER_NM,
            int(item.yrel_nm) - JITTER_NM,
            int(item.die[0]), int(item.die[1]),
            "images/" + name, "png"))
    # 名字沿用合成產生器的那一個 —— 這個 repo 不放看起來像真的 lot 名。
    klarf = os.path.join(str(out_dir), rsem.LOT_NAME + ".001")
    with open(klarf, "w", encoding="utf-8", newline="\n") as f:
        f.write(rsem._make_klarf_text(rows))
    return klarf


@pytest.fixture(scope="module")
def lots(tmp_path_factory):
    root = tmp_path_factory.mktemp("pairprobe")
    main = make_sample.generate(str(root / "main"), n=8, seed=4)
    second = _second_lot(main, root / "second")
    return main, second


def test_the_report_reads_back_what_we_planted(lots):
    """報告上的四個數字要真的是我們放進去的那四個。"""
    main, second = lots
    text = pair_probe.probe(_Args(main["klarf"], second, carry="CLASSNUMBER"))

    assert "8 / 8 顆配到（100%）" in text
    assert "成功跑完 : 8 / 8 顆" in text
    # ① 容差：我們的抖動是 ±120 nm 兩軸 → 距離 ~170 nm
    assert "① 容差" in text
    # ② 尺度：圖是原樣貼進去的，所以應該接近滿分
    assert "尺度是對的" in text
    # ③ stage offset：**這才是重點** —— 中位數要等於我們放的 (12, -7)
    line = next(l for l in text.splitlines() if "stage offset" in l)
    assert "(%.1f, %.1f)" % (OFF_X, OFF_Y) in line, line
    # ⑤ 隨機底噪 → 第一名與第二名差很多
    assert "0 / 8 顆的第一名與第二名差不到 10%" in text


def test_a_pixel_size_mismatch_is_called_out_not_swallowed(tmp_path):
    """尺度錯的時候，報告要說「那通常不是配錯顆」——因為那句話會讓人往完全錯
    的方向查（去調容差、去看座標，而問題在 nm/px）。"""
    main = make_sample.generate(str(tmp_path / "main"), n=6, seed=6)
    second = _second_lot(main, tmp_path / "second", scale=1.6)

    blind = pair_probe.probe(_Args(main["klarf"], second, n=6))
    assert "整批都對不上" in blind or "普通" in blind

    # 第二份的 patch 被縮小了 1.6 倍 → 它的一個像素**蓋比較大一塊**
    # （128 px 的東西變成 80 px），所以第二份的 nm/px 是主 lot 的 1.6 倍。
    told = pair_probe.probe(_Args(main["klarf"], second, n=6,
                                  nm_per_px=1.0, second_nm_per_px=1.6))
    assert "尺度是對的" in told, told
    line = next(l for l in told.splitlines() if "stage offset" in l)
    assert "(%.1f, %.1f)" % (OFF_X, OFF_Y) in line, line


def test_the_report_never_prints_a_path_or_a_defect_id(lots):
    """跟 `check_glas_export.py` / `load_probe.py` 同一條路：預設可以貼出來。"""
    main, second = lots
    text = pair_probe.probe(_Args(main["klarf"], second))
    assert str(main["klarf"]) not in text and str(second) not in text
    assert "LOT_SYN" not in text and "images/" not in text
    # --reveal 那一份才印路徑（而它會自己說「不要貼出來」）
    assert str(main["klarf"]) in pair_probe.probe(
        _Args(main["klarf"], second, reveal=True))

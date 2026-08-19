# d4t stage cache — authored 2026-07-28 (M2).
"""StageCache — 影像段（checkpoint）快取。

調參迴圈的關鍵加速：影像段（load→norm→align→sub→dn…）佔一顆 defect
絕大多數運算量，但調的多半是算法段/判定段參數。把影像段結束時的
Context 快照（images + features + meta 子集）存成 npz，之後同一顆、
同一影像段簽章、同一 lot 直接續跑算法段。

儲存格式：``dir/<key[:2]>/<key>.npz``
  - ``img__<name>``：各影像流 ndarray（savez_compressed，無損）
  - ``__labels__``：ROI label map（若有）
  - ``__payload__``：0 維字串陣列，內容是 JSON
    ``{"version": N, "image_names": [...], "features": {...}, "meta": {...},
       "rois": [[name, nx, ny, nw, nh], ...], "dtypes": {...}, "shapes": {...}}``
寫入走 atomic（先寫 ``.tmp`` 再 ``os.replace``）；讀到壞檔 → 盡力刪掉、
回 None（呼叫端退回重算，永不 crash）。

**快照必須涵蓋 Context 的每一個欄位。**（F7-9 修）v1 只存了
images/features/meta，漏了 ``rois`` 與 ``labels``。checkpoint 是執行順序上的
**位置**（最後一張影像段卡的下一格），不是「所有影像段的卡」—— 所以放在中間
的 Region 卡（``roi_define`` / ``blob_segment``，都是 algo）會落在快取段裡。
於是：第一次跑（miss）正常，**第二次跑（hit）ROI 不見了**，量測卡報
「region 'main' is not defined」。第一次對、第二次錯是最難查的一種 bug，
所以 ``FORMAT_VERSION`` 存進 payload，版本對不上一律當 miss 重算 ——
既有的快取目錄不會把舊的殘缺快照餵回來。
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Optional

import numpy as np

__all__ = ["StageCache", "dataset_token"]


def dataset_token(klarf_path: Any) -> str:
    """由 KLARF 路徑造出 lot 識別 token：abspath + mtime_ns + size。

    重新產生（覆寫）同名 lot → mtime/size 變 → token 變 → 舊快取自動失效。
    檔案 stat 不到（少見）→ 退化成只有 abspath。
    """
    p = os.path.abspath(str(klarf_path))
    try:
        st = os.stat(p)
    except OSError:
        return p
    return f"{p}|{st.st_mtime_ns}|{st.st_size}"


class StageCache:
    """影像段快取（磁碟 npz；single-writer-per-key、多進程安全的 atomic 寫入）。

    ``hits`` / ``misses`` 計數器在 :meth:`get` 內累加（本 instance 的統計；
    平行批次時各 worker 有自己的 instance 與計數）。
    """

    #: 快照格式版本。**欄位有增減就要 +1** —— 版本對不上的舊快照一律當 miss，
    #: 不然使用者既有的快取目錄會繼續餵回缺欄位的快照。
    #:
    #: 3（F9-4，2026-08-16）：``meta`` 裡多了 ``feature_owner``（誰產出了哪個
    #: 特徵，F9-3）。**欄位名稱沒變，但少了它熱跑會算出跟冷跑不一樣的東西** ——
    #: 舊快照沒有這份帳，於是被蓋掉的特徵不會被救回來，熱跑比冷跑少一個特徵。
    #: 這正是「版本要 +1」要擋的情況：舊快取目錄不會安靜地餵回不完整的快照。
    #:
    #: 4（F9-10，2026-08-16）：多了 ``produced`` —— 「哪個節點的哪顆埠產出了
    #: 這張圖」。F9 之後影像流的身分是 ``(節點, 埠)``，而快照以前只存
    #: ``images``（名字 → **最後一個**寫它的人）。分支之後同一個名字有好幾張
    #: 圖，快照只留得下最後那張，於是熱跑時指向快取段內某個節點的線查不到，
    #: 退回最後寫者＝**隔壁那一支**：冷跑 3.0、熱跑 5.0，兩邊都跑得完。
    FORMAT_VERSION = 4

    def __init__(self, dir: str) -> None:
        self.dir = str(dir)
        os.makedirs(self.dir, exist_ok=True)
        self.hits = 0
        self.misses = 0

    # ---- key ---------------------------------------------------------------
    @staticmethod
    def make_key(dataset_token: str, defect_id: str, signature: str) -> str:
        """(lot token, defect_id, 影像段簽章) → sha1 hex（deterministic）。"""
        payload = json.dumps(
            [str(dataset_token), str(defect_id), str(signature)],
            ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    # 讓呼叫端也能用 StageCache.dataset_token(...)（同模組函式）
    dataset_token = staticmethod(dataset_token)

    def _path(self, key: str) -> str:
        key = str(key)
        return os.path.join(self.dir, key[:2], key + ".npz")

    # ---- get / put ---------------------------------------------------------
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """回 ``{"images", "features", "meta", "rois", "labels", "produced"}``
        或 None（不存在 / 壞檔 / 舊格式；壞檔會盡力刪掉）。

        ``produced`` 是 ``{(節點, 埠): 陣列}`` —— 只存**跨過 checkpoint 被用到
        的那幾張**（見 :func:`~.engine._streams_needed_across_checkpoint`）。
        """
        path = self._path(key)
        if not os.path.isfile(path):
            self.misses += 1
            return None
        try:
            with np.load(path, allow_pickle=False) as z:
                payload = json.loads(str(z["__payload__"][()]))
                if int(payload.get("version", 1)) != self.FORMAT_VERSION:
                    # 舊格式（缺欄位）—— 當作沒有，讓呼叫端重算並覆寫
                    self.misses += 1
                    return None
                images = {str(n): z["img__" + str(n)]
                          for n in payload["image_names"]}
                features = {str(k): float(v)
                            for k, v in dict(payload.get("features") or {}).items()}
                meta = dict(payload.get("meta") or {})
                rois = [(str(r[0]), tuple(float(v) for v in r[1:5]))
                        for r in (payload.get("rois") or [])]
                labels = z["__labels__"] if "__labels__" in z.files else None
                produced = {}
                for i, (nid, port) in enumerate(payload.get("produced") or []):
                    produced[(str(nid), str(port))] = z["prod__%d" % i]
        except Exception:
            try:
                os.remove(path)  # 壞檔：盡力清掉，下次直接 miss
            except OSError:
                pass
            self.misses += 1
            return None
        self.hits += 1
        return {"images": images, "features": features, "meta": meta,
                "rois": rois, "labels": labels, "produced": produced}

    def put(self, key: str, images: Dict[str, np.ndarray],
            features: Dict[str, float], meta: Dict[str, Any],
            rois: Any = None, labels: Any = None,
            produced: Any = None) -> None:
        """寫入一筆快照（atomic：先 ``.tmp`` 再 ``os.replace``）。

        ``produced``：``{(節點, 埠): 陣列}``。**只給跨過 checkpoint 會被用到的
        那幾張** —— 全存的話快取檔會按中間影像的張數倍增，而絕大多數中間結果
        沒有人在快取段之後還要用。

        失敗會 raise（磁碟滿、唯讀…）—— 呼叫端（run_defect_cached）自行
        try/except 退回無快取路徑。
        """
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        imgs = {str(n): np.asarray(a) for n, a in dict(images or {}).items()}
        payload = {
            "version": self.FORMAT_VERSION,
            "image_names": sorted(imgs),
            "features": {str(k): float(v)
                         for k, v in dict(features or {}).items()},
            "meta": dict(meta or {}),
            # 具名 ROI（正規化座標，跟 Context.set_roi 同一個格式）
            "rois": [[str(name)] + [float(v) for v in rect]
                     for name, rect in (rois or [])],
            # dtype / shape 註記（除錯、日後版本檢查用；載入以 npz 內容為準）
            "dtypes": {n: str(a.dtype) for n, a in imgs.items()},
            "shapes": {n: list(a.shape) for n, a in imgs.items()},
        }
        # 先照 key 排序再取值 —— 不要把陣列放進排序的 tuple 裡（key 不會重複，
        # 所以實際上比不到陣列，但那種寫法一旦重複就會拿 ndarray 去比大小）。
        prod_src = {(str(k[0]), str(k[1])): v
                    for k, v in dict(produced or {}).items()}
        prod_keys = sorted(prod_src)
        payload["produced"] = [[nid, port] for nid, port in prod_keys]

        arrays: Dict[str, np.ndarray] = {"img__" + n: a for n, a in imgs.items()}
        for i, k in enumerate(prod_keys):
            arrays["prod__%d" % i] = np.asarray(prod_src[k])
        if labels is not None:
            arrays["__labels__"] = np.asarray(labels)
        arrays["__payload__"] = np.array(
            json.dumps(payload, ensure_ascii=False, sort_keys=True))

        tmp = f"{path}.{os.getpid()}.tmp"  # 含 pid：多 worker 同 dir 不互踩
        try:
            with open(tmp, "wb") as f:
                np.savez_compressed(f, **arrays)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    # ---- 管理 --------------------------------------------------------------
    def stats(self) -> Dict[str, int]:
        """快取目錄現況：``{"n_files": 檔數, "bytes": 總大小}``。"""
        n = 0
        total = 0
        for root, _dirs, files in os.walk(self.dir):
            for fn in files:
                if not fn.endswith(".npz"):
                    continue
                try:
                    st = os.stat(os.path.join(root, fn))
                except OSError:
                    continue
                n += 1
                total += int(st.st_size)
        return {"n_files": n, "bytes": total}

    def clear(self) -> None:
        """清空快取目錄（保留根目錄本身；計數器不歸零）。"""
        for root, dirs, files in os.walk(self.dir, topdown=False):
            for fn in files:
                try:
                    os.remove(os.path.join(root, fn))
                except OSError:
                    pass
            for dn in dirs:
                try:
                    os.rmdir(os.path.join(root, dn))
                except OSError:
                    pass

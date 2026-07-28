# ADEPT stage cache — authored 2026-07-28 (M2).
"""StageCache — 影像段（checkpoint）快取。

調參迴圈的關鍵加速：影像段（load→norm→align→sub→dn…）佔一顆 defect
絕大多數運算量，但調的多半是算法段/判定段參數。把影像段結束時的
Context 快照（images + features + meta 子集）存成 npz，之後同一顆、
同一影像段簽章、同一 lot 直接續跑算法段。

儲存格式：``dir/<key[:2]>/<key>.npz``
  - ``img__<name>``：各影像流 ndarray（savez_compressed，無損）
  - ``__payload__``：0 維字串陣列，內容是 JSON
    ``{"image_names": [...], "features": {...}, "meta": {...},
       "dtypes": {...}, "shapes": {...}}``
寫入走 atomic（先寫 ``.tmp`` 再 ``os.replace``）；讀到壞檔 → 盡力刪掉、
回 None（呼叫端退回重算，永不 crash）。
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
        """回 ``{"images": {name: ndarray}, "features": {...}, "meta": {...}}``
        或 None（不存在 / 壞檔；壞檔會盡力刪掉）。"""
        path = self._path(key)
        if not os.path.isfile(path):
            self.misses += 1
            return None
        try:
            with np.load(path, allow_pickle=False) as z:
                payload = json.loads(str(z["__payload__"][()]))
                images = {str(n): z["img__" + str(n)]
                          for n in payload["image_names"]}
                features = {str(k): float(v)
                            for k, v in dict(payload.get("features") or {}).items()}
                meta = dict(payload.get("meta") or {})
        except Exception:
            try:
                os.remove(path)  # 壞檔：盡力清掉，下次直接 miss
            except OSError:
                pass
            self.misses += 1
            return None
        self.hits += 1
        return {"images": images, "features": features, "meta": meta}

    def put(self, key: str, images: Dict[str, np.ndarray],
            features: Dict[str, float], meta: Dict[str, Any]) -> None:
        """寫入一筆快照（atomic：先 ``.tmp`` 再 ``os.replace``）。

        失敗會 raise（磁碟滿、唯讀…）—— 呼叫端（run_defect_cached）自行
        try/except 退回無快取路徑。
        """
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        imgs = {str(n): np.asarray(a) for n, a in dict(images or {}).items()}
        payload = {
            "image_names": sorted(imgs),
            "features": {str(k): float(v)
                         for k, v in dict(features or {}).items()},
            "meta": dict(meta or {}),
            # dtype / shape 註記（除錯、日後版本檢查用；載入以 npz 內容為準）
            "dtypes": {n: str(a.dtype) for n, a in imgs.items()},
            "shapes": {n: list(a.shape) for n, a in imgs.items()},
        }
        arrays: Dict[str, np.ndarray] = {"img__" + n: a for n, a in imgs.items()}
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

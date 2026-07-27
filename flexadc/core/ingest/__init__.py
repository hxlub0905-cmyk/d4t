# FlexADC ingest package — created 2026-07-27.
# Re-exports the main names of the vendored ingest modules
# (KLIP klarf_core / klarf_tif_probe, GLAS sem_loader patterns, PEAR image IO).
"""flexadc.core.ingest — KLARF / TIFF / 影像檔的載入層。"""
from __future__ import annotations

from .klarf_core import (
    KlarfDoc,
    Issue,
    autofix,
    compare,
    detect_version,
    lint,
    load,
)
from .tiff_index import n_pages, read_page, read_tiff_pages
from .imageio import load_gray, save_gray, save_rgb
from .dataset import (
    Dataset,
    DefectItem,
    ImageRef,
    load_dataset,
    load_folder,
)

__all__ = [
    "KlarfDoc", "Issue", "autofix", "compare", "detect_version", "lint", "load",
    "n_pages", "read_page", "read_tiff_pages",
    "load_gray", "save_gray", "save_rgb",
    "Dataset", "DefectItem", "ImageRef", "load_dataset", "load_folder",
]

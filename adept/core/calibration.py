# Vendored into ADEPT on 2026-07-27.
# Source project: MMH — src/core/calibration.py
# Adaptations:
#   - Storage directory changed from ~/.mmh/calibrations/ to
#     ~/.adept/calibrations/.
#   - `save()` made atomic: profile JSON is written to a `.tmp` sibling
#     first and moved into place with os.replace (MMH wrote in place,
#     risking a truncated file on crash).
#   - CalibrationProfile / CalibrationManager API kept unchanged.
"""Calibration profile management.

Profiles are persisted as JSON files in ~/.adept/calibrations/.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


CALIBRATION_DIR = Path.home() / ".adept" / "calibrations"

_FALLBACK_PROFILE_ID = "default-1nm-px"


@dataclass
class CalibrationProfile:
    profile_id: str
    profile_name: str
    nm_per_pixel: float
    magnification: float = 0.0
    detector_type: str = ""
    source: str = "manual"   # "manual" | "tiff_tag" | "imported"
    version: int = 1
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_name": self.profile_name,
            "nm_per_pixel": float(self.nm_per_pixel),
            "magnification": float(self.magnification),
            "detector_type": self.detector_type,
            "source": self.source,
            "version": self.version,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(d: dict) -> "CalibrationProfile":
        return CalibrationProfile(
            profile_id=d["profile_id"],
            profile_name=d.get("profile_name", d["profile_id"]),
            nm_per_pixel=float(d.get("nm_per_pixel", 1.0)),
            magnification=float(d.get("magnification", 0.0)),
            detector_type=d.get("detector_type", ""),
            source=d.get("source", "manual"),
            version=int(d.get("version", 1)),
            notes=d.get("notes", ""),
        )


_FALLBACK = CalibrationProfile(
    profile_id=_FALLBACK_PROFILE_ID,
    profile_name="Default (1 nm/px)",
    nm_per_pixel=1.0,
    source="manual",
    notes="Built-in fallback — update with your SEM calibration value.",
)


class CalibrationManager:
    """Load, save, and list CalibrationProfile objects from disk."""

    def __init__(self, cal_dir: Optional[Path] = None):
        self._dir = cal_dir or CALIBRATION_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._profiles: Dict[str, CalibrationProfile] = {}
        self._load_all()

    def _load_all(self) -> None:
        for f in self._dir.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                p = CalibrationProfile.from_dict(d)
                self._profiles[p.profile_id] = p
            except Exception:
                pass

    def list_profiles(self) -> List[CalibrationProfile]:
        return sorted(self._profiles.values(), key=lambda p: p.profile_name)

    def get(self, profile_id: str) -> Optional[CalibrationProfile]:
        return self._profiles.get(profile_id)

    def get_default(self) -> CalibrationProfile:
        if self._profiles:
            return next(iter(self._profiles.values()))
        return _FALLBACK

    def save(self, profile: CalibrationProfile) -> None:
        """Persist *profile* atomically (.tmp sibling + os.replace)."""
        path = self._dir / f"{profile.profile_id}.json"
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(profile.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(str(tmp), str(path))
        self._profiles[profile.profile_id] = profile

    def delete(self, profile_id: str) -> bool:
        path = self._dir / f"{profile_id}.json"
        if path.exists():
            path.unlink()
            self._profiles.pop(profile_id, None)
            return True
        return False

    def create_new(
        self,
        name: str,
        nm_per_pixel: float,
        magnification: float = 0.0,
        detector_type: str = "",
        notes: str = "",
    ) -> CalibrationProfile:
        p = CalibrationProfile(
            profile_id=str(uuid.uuid4()),
            profile_name=name,
            nm_per_pixel=nm_per_pixel,
            magnification=magnification,
            detector_type=detector_type,
            notes=notes,
        )
        self.save(p)
        return p

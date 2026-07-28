"""Tests for adept.core.calibration (vendored from MMH)."""
from __future__ import annotations

import json

import pytest

import adept.core.calibration as cal
from adept.core.calibration import CalibrationManager, CalibrationProfile


@pytest.fixture()
def manager(tmp_path, monkeypatch):
    # Point the module-level default dir into the tmp sandbox so even code
    # paths that fall back to CALIBRATION_DIR never touch the real HOME.
    monkeypatch.setattr(cal, "CALIBRATION_DIR", tmp_path / "calibrations")
    return CalibrationManager(cal_dir=tmp_path / "calibrations")


def test_round_trip_save_load(manager, tmp_path):
    p = manager.create_new(
        name="SEM-A 5nm", nm_per_pixel=5.0, magnification=50000.0,
        detector_type="SE", notes="标定 round-trip")
    # persisted to disk under the tmp dir
    f = tmp_path / "calibrations" / f"{p.profile_id}.json"
    assert f.exists()
    # no stray .tmp file left behind by the atomic save
    assert list((tmp_path / "calibrations").glob("*.tmp")) == []
    # fresh manager re-reads it identically
    m2 = CalibrationManager(cal_dir=tmp_path / "calibrations")
    loaded = m2.get(p.profile_id)
    assert loaded == p
    assert loaded.nm_per_pixel == 5.0
    assert loaded.notes == "标定 round-trip"
    assert m2.list_profiles() == [p]


def test_get_default(manager, tmp_path):
    # empty store -> built-in fallback
    d = manager.get_default()
    assert d.profile_id == "default-1nm-px"
    assert d.nm_per_pixel == 1.0
    # once a profile exists, it becomes the default
    p = manager.create_new("Real cal", nm_per_pixel=2.5)
    m2 = CalibrationManager(cal_dir=tmp_path / "calibrations")
    assert m2.get_default().profile_id == p.profile_id


def test_default_dir_used_when_none(monkeypatch, tmp_path):
    monkeypatch.setattr(cal, "CALIBRATION_DIR", tmp_path / "default_loc")
    m = CalibrationManager()   # no cal_dir -> falls back to CALIBRATION_DIR
    m.create_new("via default dir", nm_per_pixel=1.5)
    assert len(list((tmp_path / "default_loc").glob("*.json"))) == 1


def test_save_overwrites_atomically(manager, tmp_path):
    p = manager.create_new("v1", nm_per_pixel=1.0)
    p2 = CalibrationProfile(
        profile_id=p.profile_id, profile_name="v2", nm_per_pixel=9.0,
        version=2)
    manager.save(p2)
    f = tmp_path / "calibrations" / f"{p.profile_id}.json"
    d = json.loads(f.read_text(encoding="utf-8"))
    assert d["profile_name"] == "v2"
    assert d["nm_per_pixel"] == 9.0
    assert d["version"] == 2
    assert manager.get(p.profile_id).profile_name == "v2"


def test_delete(manager, tmp_path):
    p = manager.create_new("victim", nm_per_pixel=3.0)
    assert manager.delete(p.profile_id) is True
    assert manager.get(p.profile_id) is None
    assert not (tmp_path / "calibrations" / f"{p.profile_id}.json").exists()
    assert manager.delete("missing-id") is False


def test_corrupt_json_skipped(tmp_path):
    d = tmp_path / "calibrations"
    d.mkdir()
    (d / "broken.json").write_text("{not json", encoding="utf-8")
    ok = CalibrationProfile("good-id", "Good", 4.0)
    m = CalibrationManager(cal_dir=d)
    m.save(ok)
    m2 = CalibrationManager(cal_dir=d)
    assert [p.profile_id for p in m2.list_profiles()] == ["good-id"]


def test_profile_dict_round_trip():
    p = CalibrationProfile("id-1", "Name", 2.0, magnification=1e4,
                           detector_type="BSE", source="imported",
                           version=3, notes="n")
    assert CalibrationProfile.from_dict(p.to_dict()) == p
    # from_dict tolerates missing optional keys
    q = CalibrationProfile.from_dict({"profile_id": "only-id"})
    assert q.profile_name == "only-id"
    assert q.nm_per_pixel == 1.0

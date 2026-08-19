"""Tests for d4t.core.algo.quality (vendored from MMH)."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from d4t.core.algo.quality import (
    DEFAULT_LAP_THRESHOLD,
    check_lap_quality,
    compute_quality,
)

_METRICS = ("laplacian_var", "tenengrad", "fft_hf_ratio")


@pytest.fixture(scope="module")
def sharp_image():
    """Noisy fine checkerboard — strong genuine high-frequency content."""
    rng = np.random.default_rng(123)
    img = np.zeros((128, 128), np.float64)
    for y in range(0, 128, 8):
        for x in range(0, 128, 8):
            img[y:y + 8, x:x + 8] = 210 if ((y // 8) + (x // 8)) % 2 == 0 else 40
    img += rng.normal(0, 8, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def blurred_image(sharp_image):
    return cv2.GaussianBlur(sharp_image, (0, 0), 4.0)


def test_sharp_beats_blurred_on_all_metrics(sharp_image, blurred_image):
    qs = compute_quality(sharp_image)
    qb = compute_quality(blurred_image)
    assert qs["error"] == "" and qb["error"] == ""
    for k in _METRICS:
        assert qs[k] > qb[k], k


def test_check_lap_quality_orders_and_threshold(sharp_image, blurred_image):
    lap_sharp = check_lap_quality(sharp_image)
    lap_blur = check_lap_quality(blurred_image)
    assert lap_sharp > lap_blur
    assert lap_sharp > DEFAULT_LAP_THRESHOLD
    assert lap_blur < DEFAULT_LAP_THRESHOLD
    # matches compute_quality's laplacian_var (same medianBlur(5) pre-filter)
    assert lap_sharp == pytest.approx(
        compute_quality(sharp_image)["laplacian_var"])


def test_ndarray_and_path_inputs_agree(sharp_image, tmp_path):
    # CJK filename: exercises the np.fromfile + cv2.imdecode path loader
    p = tmp_path / "样品_对焦.png"
    ok, buf = cv2.imencode(".png", sharp_image)
    assert ok
    buf.tofile(str(p))
    q_arr = compute_quality(sharp_image)
    q_path = compute_quality(str(p))
    assert q_path["error"] == ""
    for k in _METRICS:
        assert q_path[k] == pytest.approx(q_arr[k], abs=1e-9), k


def test_color_ndarray_accepted(sharp_image):
    bgr = cv2.cvtColor(sharp_image, cv2.COLOR_GRAY2BGR)
    q = compute_quality(bgr)
    assert q["error"] == ""
    assert q["laplacian_var"] == pytest.approx(
        compute_quality(sharp_image)["laplacian_var"])


def test_missing_path_reports_error(tmp_path):
    q = compute_quality(str(tmp_path / "does_not_exist.png"))
    assert q["error"] == "Cannot load image"
    assert q["laplacian_var"] == 0.0
    assert q["tenengrad"] == 0.0
    assert q["fft_hf_ratio"] == 0.0

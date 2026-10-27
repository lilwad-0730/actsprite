import numpy as np
import pytest

from actsprite.verify import combined_score, extract_palette, mask_iou, palette_drift, passes, silhouette_iou


def rect(h, w, box):
    m = np.zeros((h, w), bool)
    l, t, r, b = box
    m[t:b, l:r] = True
    return m


def test_mask_iou():
    a = rect(10, 10, (0, 0, 4, 10))
    b = rect(10, 10, (2, 0, 6, 10))
    assert mask_iou(a, b) == pytest.approx(20 / 60)
    assert mask_iou(a, a) == 1.0
    assert mask_iou(np.zeros((3, 3), bool), np.zeros((3, 3), bool)) == 0.0


def test_silhouette_iou_ignores_position_and_scale():
    small = rect(300, 300, (10, 10, 30, 70))
    big_elsewhere = rect(300, 300, (150, 100, 190, 220))
    assert silhouette_iou(small, big_elsewhere) > 0.95


def test_silhouette_iou_detects_pose_change():
    standing = rect(200, 200, (90, 20, 110, 180))
    lying = rect(200, 200, (20, 160, 180, 180))
    assert silhouette_iou(standing, lying) < 0.3


def test_palette_drift_zero_for_same_image_and_high_for_recolour():
    rng = np.random.default_rng(0)
    img = np.zeros((40, 40, 3), np.uint8)
    img[:20] = (200, 30, 30)
    img[20:] = (30, 30, 200)
    img = np.clip(img.astype(int) + rng.integers(-5, 6, img.shape), 0, 255).astype(np.uint8)
    mask = np.ones((40, 40), bool)
    pal = extract_palette(img, mask, colors=8)
    assert palette_drift(img, mask, pal) == 0.0
    green = img.copy()
    green[:20] = (30, 200, 30)
    assert palette_drift(green, mask, pal) == pytest.approx(0.5, abs=0.01)


def test_score_and_thresholds():
    assert combined_score(1.0, 10, 0.0) == pytest.approx(1.0)
    assert passes(0.75, 8, 0.1)
    assert not passes(0.65, 8, 0.1)
    assert not passes(0.75, 6, 0.1)
    assert not passes(0.75, 8, 0.2)

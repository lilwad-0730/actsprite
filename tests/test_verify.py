import numpy as np
import pytest

from actsprite import config
from actsprite.verify import (
    FrameScores,
    critic_parts,
    extract_palette,
    largest_component,
    mask_iou,
    palette_drift,
    silhouette_iou,
)


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


def test_silhouette_iou_ignores_specks():
    body = rect(200, 200, (90, 20, 110, 180))
    noisy = body.copy()
    noisy[2:4, 2:4] = True  # a SAM speck far above the head
    assert silhouette_iou(body, noisy) == pytest.approx(1.0)


def test_largest_component():
    m = rect(20, 20, (0, 0, 3, 3)) | rect(20, 20, (10, 10, 18, 18))
    assert largest_component(m).sum() == 64


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


def test_frame_scores():
    perfect = FrameScores(iou=1.0, pose=10, identity=10, drift=0.0)
    assert perfect.combined == pytest.approx(1.0)
    assert perfect.passed and perfect.failures() == []
    ok = FrameScores(iou=config.IOU_MIN, pose=config.POSE_MIN, identity=config.IDENTITY_MIN,
                     drift=config.PALETTE_DRIFT_MAX)
    assert ok.passed
    bad_pose = FrameScores(iou=0.8, pose=3, identity=9, drift=0.05)
    assert not bad_pose.passed
    assert bad_pose.failures() == [f"pose 3 < {config.POSE_MIN}"]


def test_critic_parts_order():
    parts = critic_parts(b"S", b"P", b"G", b"C")
    images = [p for p in parts if isinstance(p, bytes)]
    assert images == [b"S", b"P", b"G", b"C"]
    first = critic_parts(b"S", None, b"G", b"C")
    assert [p for p in first if isinstance(p, bytes)] == [b"S", b"G", b"C"]
    assert "PREVIOUS" not in " ".join(p for p in first if isinstance(p, str))

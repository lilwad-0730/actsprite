"""Sequence-level capture/align logic on a synthetic walker (no video needed)."""

import math

import numpy as np

from actsprite.align import align_sequence, mask_bbox
from actsprite.capture import find_cycle, motion_curve, select_keyframes

PERIOD = 10


def walker(t: int, h=240, w=480, travel=6, crouch=False) -> np.ndarray:
    """Body + one swinging leg; the whole figure walks right `travel` px per frame."""
    m = np.zeros((h, w), bool)
    x = 40 + travel * t
    top = 60 if crouch else 40
    m[top:150, x : x + 30] = True  # torso
    swing = int(round(25 * math.sin(2 * math.pi * t / PERIOD)))
    m[150:220, x + 10 + swing : x + 22 + swing] = True  # leg
    m[150:220, x + 8 : x + 20] = True  # standing leg
    return m


def test_align_sequence_runs_in_place_with_one_scale():
    masks = [walker(t) for t in range(PERIOD + 1)]
    aligned, _, scale = align_sequence(masks, size=128, margin=8)
    assert all(mask_bbox(a)[3] == 128 for a in aligned)  # feet on the baseline
    assert np.array_equal(aligned[0], aligned[PERIOD])  # same pose, different place -> same cell


def test_align_sequence_keeps_height_difference():
    aligned, _, _ = align_sequence([walker(0), walker(0, crouch=True)], size=128, margin=8)
    h0 = mask_bbox(aligned[0])[3] - mask_bbox(aligned[0])[1]
    h1 = mask_bbox(aligned[1])[3] - mask_bbox(aligned[1])[1]
    assert h1 < h0


def test_find_cycle_detects_period():
    aligned, _, _ = align_sequence([walker(t) for t in range(25)], size=128, margin=8)
    assert find_cycle(aligned) == PERIOD


def test_find_cycle_none_for_still_clip():
    aligned, _, _ = align_sequence([walker(0)] * 12, size=128, margin=8)
    assert find_cycle(aligned) is None


def test_select_keyframes_skips_pauses():
    # 10 frames of real motion, then 10 frames frozen: keyframes should sit in the moving part.
    masks = [walker(t) for t in range(PERIOD)] + [walker(PERIOD - 1)] * 10
    aligned, _, _ = align_sequence(masks, size=128, margin=8)
    assert motion_curve(aligned)[-1] == 0.0
    picks = select_keyframes(aligned, 6, loop=False)
    assert len(picks) == 6 and picks == sorted(set(picks))
    assert sum(p >= PERIOD for p in picks) <= 1


def test_select_keyframes_loop_excludes_end():
    aligned, _, _ = align_sequence([walker(t) for t in range(PERIOD)], size=128, margin=8)
    picks = select_keyframes(aligned, 5, loop=True)
    assert picks[0] == 0 and len(picks) == 5 and picks == sorted(set(picks))
    assert select_keyframes(aligned, 20, loop=True) == list(range(PERIOD))

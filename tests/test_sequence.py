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


def test_action_window_finds_the_burst():
    from actsprite.capture import action_window

    still = [walker(0, travel=0)] * 15
    moving = [walker(t) for t in range(1, 11)]
    aligned, _, _ = align_sequence(still + moving + [walker(10)] * 15, size=128, margin=8)
    start, end = action_window(aligned, fps=10, smooth_s=0.1, pad_s=0.0, merge_gap_s=0.2)
    assert 13 <= start <= 16 and 24 <= end <= 27


def test_pose_guide_shared_scale_keeps_crouch_short():
    from actsprite.align import pose_guide, shared_scale

    stand, crouch = walker(0), walker(0, crouch=True)
    img = np.full((*stand.shape, 3), 255, np.uint8)
    s = shared_scale([stand, crouch], 128, 8)
    _, gs = pose_guide(img, stand, size=128, margin=8, scale=s)
    _, gc = pose_guide(img, crouch, size=128, margin=8, scale=s)
    assert mask_bbox(gc)[3] == mask_bbox(gs)[3] == 128
    assert mask_bbox(gc)[1] > mask_bbox(gs)[1]


def test_best_cycle_skips_settling_in():
    from actsprite.capture import best_cycle

    settle = [walker(0, crouch=True)] * 3 + [walker(0)] * 2  # stepping into place first
    frames = settle + [walker(t) for t in range(25)]
    aligned, _, _ = align_sequence(frames, size=128, margin=8)
    start, length = best_cycle(aligned, fps=10)
    assert length == PERIOD and start >= len(settle) - 1


def test_find_cycle_small_motion_loop():
    # Subtle bob: only the arm moves a little, the body stays put.
    def bob(t):
        m = walker(0, travel=0)
        dx = int(round(6 * math.sin(2 * math.pi * t / 8)))
        m[100:150, 70 + dx : 80 + dx] = True
        return m

    aligned, _, _ = align_sequence([bob(t) for t in range(20)], size=128, margin=8)
    assert find_cycle(aligned) == 8


def two_legs(t: int, period: int = 20) -> np.ndarray:
    """Side-view walker: near leg (thicker) and far leg swing in opposite phase, so after half a
    period the silhouette nearly repeats with the legs swapped."""
    m = np.zeros((240, 480), bool)
    m[40:150, 200:300] = True  # body
    swing = int(round(30 * math.sin(2 * math.pi * t / period)))
    m[150:220, 240 + swing : 256 + swing] = True  # near leg
    m[150:220, 242 - swing : 252 - swing] = True  # far leg
    return m


def test_gait_cycle_is_two_steps():
    from actsprite.capture import best_cycle

    aligned, _, _ = align_sequence([two_legs(t) for t in range(50)], size=128, margin=8)
    assert find_cycle(aligned) == 10  # plain loop stops after one step (legs swapped)
    assert find_cycle(aligned, gait=True) == 20  # a stride is two steps
    _, length = best_cycle(aligned, fps=10, gait=True)
    assert length == 20


def test_size_drift_cancels_walking_toward_camera():
    from actsprite.align import size_drift

    def body(t):  # grows from 100 to 150 px tall over 60 frames, plus a fast 4 px bob
        m = np.zeros((300, 300), bool)
        h = int(100 + 50 * t / 59 + 4 * math.sin(2 * math.pi * t / 6))
        m[280 - h : 280, 120:180] = True
        return m

    masks = [body(t) for t in range(60)]
    rel = size_drift(masks, fps=30, window_s=1.0)
    aligned, _, _ = align_sequence(masks, size=128, margin=8, rel=rel)
    heights = [mask_bbox(a)[3] - mask_bbox(a)[1] for a in aligned[15:45]]  # away from the clip ends
    plain, _, _ = align_sequence(masks, size=128, margin=8)
    plain_h = [mask_bbox(a)[3] - mask_bbox(a)[1] for a in plain[15:45]]
    assert max(heights) - min(heights) < 0.5 * (max(plain_h) - min(plain_h))
    assert max(heights) - min(heights) >= 3  # the fast bob survives

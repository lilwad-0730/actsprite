"""One action from a tracked clip: which 8 frames to draw, and the pose guide for each."""

from __future__ import annotations

import numpy as np

from actsprite import config
from actsprite.align import align_sequence, pose_guide, shared_scale, size_drift
from actsprite.capture import SamObject, action_window, best_cycle, full_body_range, select_keyframes
from actsprite.errors import PipelineError

MODES = ("once", "loop", "gait")
# once: one burst of motion (jump, attack); loop: cleanest cycle (idle); gait: one two-step stride (walk, run).
ACTION_MODES = {"attack": "once", "jump": "once", "hit": "once", "idle": "loop", "walk": "gait", "run": "gait"}


def mode_for(action: str, mode: str | None = None) -> str:
    if mode is not None:
        if mode not in MODES:
            raise PipelineError(f"Unknown mode '{mode}'; use one of {', '.join(MODES)}.")
        return mode
    if action not in ACTION_MODES:
        raise PipelineError(f"Pass --mode for the action '{action}': once (jump, attack), loop (idle) "
                            f"or gait (walk, run).")
    return ACTION_MODES[action]


def choose_frames(masks: np.ndarray, fps: float, mode: str, edges: tuple[str, ...]) -> tuple[dict, np.ndarray]:
    """Keyframes plus a per-frame scale factor (1 unless walking/running, where it cancels the
    subject moving toward or away from the camera; idle and one-shot actions stay in place)."""
    n = len(masks)
    track = {i: SamObject(i, "0", (0, 0, 1, 1), m) for i, m in enumerate(masks) if m.any()}
    rng = full_body_range(track, n, edges=edges)
    if rng is None:
        raise PipelineError("No stretch of the clip shows the whole body. Keep head and feet inside the frame, "
                            "or let them touch the top/bottom edge with --edges left,right.")
    lo, hi = rng
    rel = np.ones(n)
    if mode == "gait":
        rel[lo:hi] = size_drift(list(masks[lo:hi]), fps)
    aligned, _, _ = align_sequence(list(masks[lo:hi]), rel=rel[lo:hi])
    if mode == "once":
        s, e = action_window(aligned, fps)
        picks = select_keyframes(aligned[s:e], config.FRAMES_PER_ACTION, loop=False)
        cycle = None
    else:
        found = best_cycle(aligned, fps, gait=mode == "gait")
        if found is None:
            raise PipelineError("No loop found in this clip: repeat the movement at least twice "
                                "(for walk/run, at least two full strides).")
        s, cycle = found
        e = s + cycle
        picks = select_keyframes(aligned[s:e], config.FRAMES_PER_ACTION, loop=True)
    keys = [lo + s + p for p in picks]
    info = {"full_body": [lo, hi], "window": [lo + s, lo + e], "cycle_frames": cycle, "keyframes": keys,
            "keyframe_seconds": [round(k / fps, 3) for k in keys],
            "keyframe_size_fix": [round(float(rel[k]), 3) for k in keys]}
    return info, rel


def make_guides(frames: dict[int, np.ndarray], masks: np.ndarray, keys: list[int],
                rel: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """(pose guide image, its mask) per keyframe, all at one scale so a crouch stays shorter.
    `frames` only needs the keyframes (RGB, indexed like `masks`)."""
    scale = shared_scale([masks[i] for i in keys], config.GUIDE_SIZE, config.CELL_MARGIN * 2, rel[keys])
    return [pose_guide(frames[i], masks[i], fill=True, head_fraction=config.GUIDE_HEAD_FRACTION,
                       scale=scale * rel[i]) for i in keys]

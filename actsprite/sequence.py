"""One action from a tracked clip: which 8 frames to draw, and the pose guide for each."""

from __future__ import annotations

import numpy as np

from actsprite import config
from actsprite.align import align_sequence, pose_guide, shared_scale, size_drift
from actsprite.capture import SamObject, action_window, best_cycle, full_body_range, select_keyframes
from actsprite.errors import PipelineError

MODES = ("once", "loop", "gait", "span")
# once: one burst of motion (jump, attack); loop: cleanest cycle (idle); gait: one two-step stride (walk, run);
# span: the whole clip (or --start/--end) at even time steps, for moves with no single burst or cycle (a dance).
LOOP_MODES = ("loop", "gait")  # actions that play in a loop
ACTION_MODES = {"attack": "once", "jump": "once", "hit": "once", "idle": "loop", "walk": "gait", "run": "gait"}


def mode_for(action: str, mode: str | None = None) -> str:
    if mode is not None:
        if mode not in MODES:
            raise PipelineError(f"Unknown mode '{mode}'; use one of {', '.join(MODES)}.")
        return mode
    if action not in ACTION_MODES:
        raise PipelineError(f"Pass --mode for the action '{action}': once (jump, attack), loop (idle), "
                            f"gait (walk, run) or span (the whole clip, e.g. a dance).")
    return ACTION_MODES[action]


def choose_frames(masks: np.ndarray, fps: float, mode: str, edges: tuple[str, ...],
                  frames: int = config.FRAMES_ACTION, start: float | None = None,
                  end: float | None = None) -> tuple[dict, np.ndarray]:
    """Keyframes plus a per-frame scale factor (1 unless walking/running, where it cancels the
    subject moving toward or away from the camera; idle and one-shot actions stay in place).
    start/end (seconds) keep only that part of the clip."""
    if not config.FRAMES_MIN <= frames <= config.FRAMES_MAX:
        raise PipelineError(f"--frames must be {config.FRAMES_MIN}-{config.FRAMES_MAX}, not {frames}.")
    n = len(masks)
    first = 0 if start is None else max(0, int(round(start * fps)))
    last = n if end is None else min(n, int(round(end * fps)))
    if last - first < 2:
        raise PipelineError(f"--start/--end leave no frames: the clip is {n / fps:.1f} s long.")
    track = {i: SamObject(i, "0", (0, 0, 1, 1), m) for i, m in enumerate(masks) if first <= i < last and m.any()}
    rng = full_body_range(track, n, edges=edges)
    if rng is None:
        raise PipelineError("No stretch of the clip shows the whole body. Keep head and feet inside the frame, "
                            "or let them touch the top/bottom edge with --edges left,right.")
    lo, hi = rng
    if mode == "span" and hi - lo < frames:
        raise PipelineError(f"Only {hi - lo} usable frames between {lo / fps:.2f} and {hi / fps:.2f} s, fewer than "
                            f"--frames {frames}: use fewer frames or a longer part of the clip.")
    rel = np.ones(n)
    if mode == "gait":
        rel[lo:hi] = size_drift(list(masks[lo:hi]), fps)
    aligned, _, _ = align_sequence(list(masks[lo:hi]), rel=rel[lo:hi])
    if mode == "span":
        s, e = 0, hi - lo
        picks = select_keyframes(aligned[s:e], frames, loop=False)
        cycle = None
    elif mode == "once":
        s, e = action_window(aligned, fps)
        picks = select_keyframes(aligned[s:e], frames, loop=False)
        cycle = None
    else:
        found = best_cycle(aligned, fps, gait=mode == "gait")
        if found is None:
            raise PipelineError("No loop found in this clip: repeat the movement at least twice "
                                "(for walk/run, at least two full strides).")
        s, cycle = found
        e = s + cycle
        picks = select_keyframes(aligned[s:e], frames, loop=True)
    keys = [lo + s + p for p in picks]
    info = {"full_body": [lo, hi], "window": [lo + s, lo + e], "cycle_frames": cycle, "keyframes": keys,
            "keyframe_sampling": "uniform_time",
            "keyframe_seconds": [round(k / fps, 3) for k in keys],
            "keyframe_size_fix": [round(float(rel[k]), 3) for k in keys]}
    return info, rel


def clip_fps(info: dict, fps: float, mode: str) -> float:
    """Playback fps at which the keyframes take as long as they did in the clip (fps = the SAM clip's)."""
    keys = info["keyframes"]
    if mode in LOOP_MODES and info.get("cycle_frames"):
        span, steps = info["cycle_frames"], len(keys)  # the last frame leads back to the first
    else:
        span, steps = keys[-1] - keys[0], len(keys) - 1
    if span <= 0 or steps <= 0:
        raise PipelineError("Cannot time a single keyframe: use --fps with a number.")
    return round(min(max(fps * steps / span, config.FPS_MIN), config.FPS_MAX), 1)


def make_guides(frames: dict[int, np.ndarray], masks: np.ndarray, keys: list[int],
                rel: np.ndarray, faces: np.ndarray | None = None) -> list[tuple[np.ndarray, np.ndarray]]:
    """(pose guide image, its mask) per keyframe, all at one scale so a crouch stays shorter.
    `frames` only needs the keyframes (RGB, indexed like `masks`); `faces` (same indexing) adds the face patch."""
    scale = shared_scale([masks[i] for i in keys], config.GUIDE_SIZE, config.CELL_MARGIN * 2, rel[keys])
    return [pose_guide(frames[i], masks[i], fill=True, head_fraction=config.GUIDE_HEAD_FRACTION,
                       scale=scale * rel[i], face=None if faces is None else faces[i]) for i in keys]

"""Capture: video frames and SAM 3.1 segmentation output -> per-frame binary masks."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from actsprite import config
from meta_sam_parser import (
    CompletedOutcome,
    InvalidSegmentationMaskError,
    decode_mask_to_raster,
    image_segmentation_format,
    video_segmentation_format,
)


@dataclass
class SamObject:
    frame_index: int
    object_id: str
    box: tuple[int, int, int, int]  # left, top, right, bottom (half-open, source pixels)
    mask: np.ndarray  # bool, full frame (H, W)

    @property
    def area(self) -> int:
        return int(self.mask.sum())


_Decoded = tuple[int, str, tuple[int, int, int, int], np.ndarray]  # frame, object id, box, crop


def _decode_chunk(text: str, video: bool) -> list[_Decoded]:
    """Parse SAM text with the official parser and decode each mask crop (runs in a worker)."""
    parser = (video_segmentation_format() if video else image_segmentation_format()).create_parser()
    parser.push(text)
    result = parser.finish(CompletedOutcome()).result
    out: list[_Decoded] = []
    for record in result.records:
        if record.kind != "mask":
            continue
        m = record.mask
        try:
            crop = np.frombuffer(decode_mask_to_raster(m), dtype=np.uint8).reshape(m.height, m.width)
        except InvalidSegmentationMaskError:
            continue  # a corrupt payload costs that frame its mask, not the whole track
        box = tuple(int(round(v)) for v in (record.bounds.left, record.bounds.top,
                                             record.bounds.right, record.bounds.bottom))
        frame_index = record.frame.frame_index if record.frame is not None else 0
        out.append((frame_index, record.object_id, box, crop))  # type: ignore[arg-type]
    return out


def _frame_chunks(text: str, count: int) -> list[str]:
    """Split video output (one line per frame) into about `count` groups of whole lines."""
    lines = text.splitlines(keepends=True)
    size = max(1, -(-len(lines) // count))
    return ["".join(lines[i : i + size]) for i in range(0, len(lines), size)]


def parse_sam_output(
    text: str, frame_size: tuple[int, int], *, video: bool, workers: int | None = None
) -> list[SamObject]:
    """Decode SAM 3.1 special-token text into full-frame masks.

    frame_size is (width, height) of the media that was sent. Each SAM mask is a
    crop covering its box, so it is pasted back at the box's top-left corner.
    The official decoder is pure Python (~1 s per 720p person mask), so video output
    is split by frame and decoded in `workers` processes (default: CPUs up to config.SAM_PARSE_WORKERS_MAX;
    1 = in-process). If a worker dies (10/30: Windows ran out of page file with 32 workers), the rest is decoded
    in this process.
    """
    width, height = frame_size
    workers = workers or min(os.cpu_count() or 1, config.SAM_PARSE_WORKERS_MAX)
    chunks = _frame_chunks(text, workers * 4) if video and workers > 1 else [text]
    if len(chunks) > 1:
        try:
            with ProcessPoolExecutor(max_workers=min(workers, len(chunks))) as pool:
                decoded = [d for part in pool.map(_decode_chunk, chunks, [video] * len(chunks)) for d in part]
        except BrokenProcessPool:
            print("[warn] SAM decode worker died; decoding in the main process (slower)", flush=True)
            decoded = [d for chunk in chunks for d in _decode_chunk(chunk, video)]
    else:
        decoded = _decode_chunk(text, video)

    objects: list[SamObject] = []
    for frame_index, object_id, (left, top, right, bottom), crop in decoded:
        box_w, box_h = right - left, bottom - top
        if (box_w, box_h) != (crop.shape[1], crop.shape[0]) and box_w > 0 and box_h > 0:
            crop = cv2.resize(crop, (box_w, box_h), interpolation=cv2.INTER_NEAREST)

        full = np.zeros((height, width), dtype=bool)
        x0, y0 = max(left, 0), max(top, 0)
        x1, y1 = min(left + crop.shape[1], width), min(top + crop.shape[0], height)
        if x1 > x0 and y1 > y0:
            full[y0:y1, x0:x1] = crop[y0 - top : y1 - top, x0 - left : x1 - left] > 0
        objects.append(SamObject(frame_index, object_id, (left, top, right, bottom), full))
    return objects


def largest_object(objects: list[SamObject]) -> SamObject | None:
    return max(objects, key=lambda o: o.area, default=None)


def main_track(objects: list[SamObject]) -> dict[int, SamObject]:
    """Pick the object id with the most total mask area; return its mask per frame."""
    if not objects:
        return {}
    totals: dict[str, int] = {}
    for o in objects:
        totals[o.object_id] = totals.get(o.object_id, 0) + o.area
    best = max(totals, key=totals.__getitem__)
    return {o.frame_index: o for o in objects if o.object_id == best}


def motion_curve(aligned: list[np.ndarray]) -> np.ndarray:
    """Shape change between consecutive in-place masks (1 - IoU), length n-1."""
    from actsprite.verify import mask_iou

    return np.array([1.0 - mask_iou(a, b) for a, b in zip(aligned, aligned[1:])], dtype=np.float64)


def select_keyframes(aligned: list[np.ndarray], count: int, *, loop: bool) -> list[int]:
    """Pick frames at even time intervals for fixed-FPS playback, preserving pauses and rhythm.

    One-shots include the first and last frame. Loops sample [0, n), leaving room for the
    closing interval. Rounding to actual source frames adds at most half a frame of timing error.
    """
    n = len(aligned)
    if n == 0:
        raise ValueError("No frames to choose from.")
    if count >= n:
        return list(range(n))
    targets = np.linspace(0, n if loop else n - 1, count, endpoint=not loop)
    return np.rint(targets).astype(int).tolist()


def action_window(
    aligned: list[np.ndarray],
    fps: float,
    *,
    smooth_s: float = config.ACTION_SMOOTH_S,
    level: float = config.ACTION_LEVEL,
    merge_gap_s: float = config.ACTION_MERGE_GAP_S,
    pad_s: float = config.ACTION_PAD_S,
) -> tuple[int, int]:
    """Frames [start, end) of the strongest burst of motion: one jump or one attack inside a
    clip that also has standing still (or several repeats). Falls back to the whole clip."""
    n = len(aligned)
    if n < 3:
        return 0, n
    motion = motion_curve(aligned)
    k = max(1, round(smooth_s * fps))
    smooth = np.convolve(motion, np.ones(k) / k, mode="same")
    base, peak = float(np.median(smooth)), float(smooth.max())
    if peak <= base:
        return 0, n
    active = smooth > base + level * (peak - base)

    # Runs of active steps, merging quiet gaps shorter than merge_gap_s.
    runs: list[list[int]] = []
    gap = round(merge_gap_s * fps)
    for i in np.flatnonzero(active):
        if runs and i - runs[-1][1] <= gap:
            runs[-1][1] = int(i)
        else:
            runs.append([int(i), int(i)])
    best = max(runs, key=lambda r: float(motion[r[0] : r[1] + 1].sum()))
    pad = round(pad_s * fps)
    # Step i is the change from frame i to i+1, so the run covers frames best[0]..best[1]+1.
    return max(0, best[0] - pad), min(n, best[1] + 2 + pad)


def find_cycle(
    aligned: list[np.ndarray],
    *,
    min_frames: int = config.CYCLE_MIN_FRAMES,
    min_similarity: float = config.CYCLE_MIN_SIMILARITY,
    max_frames: int | None = None,
    gait: bool = False,
) -> int | None:
    """Length of the first full motion cycle starting at frame 0, or None if no loop is found.

    A cycle ends at the first frame k that looks like frame 0 again (a local IoU peak) after
    the shape has first moved away. "Away" and "back" are relative to how far this clip moves
    within max_frames, so a subtle idle bob and a big walk stride both work.

    gait=True (walk/run): from the side the silhouette after one step looks like the start with
    the legs swapped, so the cycle must also contain that half-way match (two steps = one stride).
    """
    from actsprite.verify import mask_iou

    if max_frames is not None:
        aligned = aligned[: max_frames + 1]
    sim = [mask_iou(aligned[0], m) for m in aligned]
    if len(sim) < 3:
        return None
    spread = 1.0 - min(sim[1:])
    if spread < config.CYCLE_MIN_CHANGE:
        return None  # nothing moves: no loop to find
    away = 1.0 - config.CYCLE_AWAY_SHARE * spread
    back = max(min_similarity, 1.0 - config.CYCLE_RETURN_SHARE * spread)
    moved_away = False
    for k in range(1, len(sim)):
        if sim[k] < away:
            moved_away = True
            continue
        if not moved_away or k < min_frames or sim[k] < back:
            continue
        nxt = sim[k + 1] if k + 1 < len(sim) else -1.0
        if sim[k] >= sim[k - 1] and sim[k] >= nxt and (not gait or _has_mid_step(sim, k)):
            return k
    return None


def _has_mid_step(sim: list[float], k: int) -> bool:
    """True if the similarity curve climbs back up half way through the cycle (the other step)."""
    trough = min(sim[1:k])
    mid = max(sim[round(0.35 * k) : round(0.65 * k) + 1])
    return mid - trough >= config.GAIT_MID_SHARE * (sim[k] - trough)


def best_cycle(aligned: list[np.ndarray], fps: float, gait: bool = False) -> tuple[int, int] | None:
    """(start, length) of the cleanest loop in the clip: tries every start frame and keeps the
    cycle whose end matches its start best. Skips settling-in at the start (turning, stepping in).

    The match also compares the frame after start with the frame after the end, so a pose seen
    on the way out and again on the way back (same shape, opposite motion) is not a loop."""
    from actsprite.verify import mask_iou

    horizon = round(config.CYCLE_MAX_S * fps)
    best: tuple[float, int, int] | None = None
    for s in range(0, max(0, len(aligned) - config.CYCLE_MIN_FRAMES)):
        k = find_cycle(aligned[s:], max_frames=horizon, gait=gait)
        if k is None or s + k + 1 >= len(aligned):
            continue
        score = min(mask_iou(aligned[s], aligned[s + k]), mask_iou(aligned[s + 1], aligned[s + k + 1]))
        if best is None or score > best[0]:
            best = (score, s, k)
    return None if best is None else (best[1], best[2])


def edge_contact(mask: np.ndarray, edge_px: int = config.FULL_BODY_EDGE_PX) -> set[str]:
    """Which frame edges ('top', 'bottom', 'left', 'right') the mask touches (within edge_px)."""
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return set()
    touched = set()
    if ys.min() < edge_px:
        touched.add("top")
    if ys.max() >= h - edge_px:
        touched.add("bottom")
    if xs.min() < edge_px:
        touched.add("left")
    if xs.max() >= w - edge_px:
        touched.add("right")
    return touched


def full_body_range(
    track: dict[int, SamObject],
    frame_count: int,
    *,
    edge_px: int = config.FULL_BODY_EDGE_PX,
    min_frames: int = config.FULL_BODY_MIN_FRAMES,
    edges: tuple[str, ...] = config.FULL_BODY_EDGES,
) -> tuple[int, int] | None:
    """Longest run [start, end) of frames where the subject is found and touches no frame edge.

    Trims the walk to and from the phone that self-filmed clips start and end with.
    Returns None when no run is at least min_frames long.
    """
    best: tuple[int, int] | None = None
    start: int | None = None
    for i in range(frame_count + 1):
        ok = (i < frame_count and i in track and track[i].area > 0
              and not edge_contact(track[i].mask, edge_px) & set(edges))
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if best is None or i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    if best is None or best[1] - best[0] < min_frames:
        return None
    return best


@dataclass
class PreparedVideo:
    path: Path
    frame_count: int
    size: tuple[int, int]  # (width, height)
    fps: float
    source_indices: list[int]  # frame i of the prepared clip = this frame of the source


def prepare_video(
    src: Path,
    dst: Path,
    *,
    max_short_side: int = config.SAM_VIDEO_MAX_SHORT_SIDE,
    target_fps: float = config.SAM_VIDEO_FPS,
    max_seconds: float | None = None,
    start_seconds: float = 0.0,
) -> PreparedVideo:
    """Re-encode a phone clip for SAM: MPEG-4 in an MP4, short side <= max_short_side,
    every n-th frame so the rate is at most target_fps, from start_seconds and for max_seconds if given.
    Streams frames (no full clip in memory)."""
    fps, _, (w, h) = video_info(src)
    first = max(0, int(round(start_seconds * fps)))
    last = None if max_seconds is None else first + int(round(max_seconds * fps))
    stride = max(1, round(fps / target_fps))
    scale = min(1.0, max_short_side / min(w, h))
    size = (int(w * scale) // 2 * 2, int(h * scale) // 2 * 2)
    dst.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), fps / stride, size)
    cap = cv2.VideoCapture(str(src))
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
    kept: list[int] = []
    i = 0
    while True:
        ok, bgr = cap.read()
        if not ok or (last is not None and i >= last):
            break
        if i >= first and (i - first) % stride == 0:
            writer.write(cv2.resize(bgr, size, interpolation=cv2.INTER_AREA))
            kept.append(i)
        i += 1
    cap.release()
    writer.release()
    if not kept:
        raise ValueError(f"No frames could be read from {src}; re-export it as H.264 MP4/MOV.")
    return PreparedVideo(dst, len(kept), size, fps / stride, kept)


def video_info(path: Path) -> tuple[float, int, tuple[int, int]]:
    """Return (fps, frame_count, (width, height))."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video {path}; check the path and that it is MP4/MOV.")
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)  # phone display rotation must match decoded pixels and dimensions
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    cap.release()
    return fps, count, size


def read_frames_at(path: Path, indices: list[int]) -> dict[int, np.ndarray]:
    """Only the given frames (RGB), read in one pass: a whole 16 s clip would be ~600 MB in memory."""
    wanted = set(indices)
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
    frames: dict[int, np.ndarray] = {}
    i = 0
    while len(frames) < len(wanted):
        ok, bgr = cap.read()
        if not ok:
            break
        if i in wanted:
            frames[i] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        i += 1
    cap.release()
    missing = wanted - frames.keys()
    if missing:
        raise ValueError(f"{path} has no frames {sorted(missing)[:5]} (it has {i}).")
    return frames


def read_frames(path: Path) -> list[np.ndarray]:
    """All frames as RGB arrays, in source order (SAM frame indices refer to these)."""
    cap = cv2.VideoCapture(str(path))
    frames: list[np.ndarray] = []
    cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()
    return frames

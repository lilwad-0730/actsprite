"""Capture: video frames and SAM 3.1 segmentation output -> per-frame binary masks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from meta_sam_parser import (
    CompletedOutcome,
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


def parse_sam_output(text: str, frame_size: tuple[int, int], *, video: bool) -> list[SamObject]:
    """Decode SAM 3.1 special-token text into full-frame masks.

    frame_size is (width, height) of the media that was sent. Each SAM mask is a
    crop covering its box, so it is pasted back at the box's top-left corner.
    """
    width, height = frame_size
    parser = (video_segmentation_format() if video else image_segmentation_format()).create_parser()
    parser.push(text)
    result = parser.finish(CompletedOutcome()).result

    objects: list[SamObject] = []
    for record in result.records:
        if record.kind != "mask":
            continue
        m = record.mask
        crop = np.frombuffer(decode_mask_to_raster(m), dtype=np.uint8).reshape(m.height, m.width)
        left, top = int(round(record.bounds.left)), int(round(record.bounds.top))
        right, bottom = int(round(record.bounds.right)), int(round(record.bounds.bottom))
        box_w, box_h = right - left, bottom - top
        if (box_w, box_h) != (m.width, m.height) and box_w > 0 and box_h > 0:
            crop = cv2.resize(crop, (box_w, box_h), interpolation=cv2.INTER_NEAREST)

        full = np.zeros((height, width), dtype=bool)
        x0, y0 = max(left, 0), max(top, 0)
        x1, y1 = min(left + crop.shape[1], width), min(top + crop.shape[0], height)
        if x1 > x0 and y1 > y0:
            full[y0:y1, x0:x1] = crop[y0 - top : y1 - top, x0 - left : x1 - left] > 0
        frame_index = record.frame.frame_index if record.frame is not None else 0
        objects.append(SamObject(frame_index, record.object_id, (left, top, right, bottom), full))
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


def video_info(path: Path) -> tuple[float, int, tuple[int, int]]:
    """Return (fps, frame_count, (width, height))."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video {path}; check the path and that it is MP4/MOV.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    cap.release()
    return fps, count, size


def read_frames(path: Path) -> list[np.ndarray]:
    """All frames as RGB arrays, in source order (SAM frame indices refer to these)."""
    cap = cv2.VideoCapture(str(path))
    frames: list[np.ndarray] = []
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cap.release()
    return frames

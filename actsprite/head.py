"""Head direction from SAM 3.1 masks: where the face sits inside the head says which way the head turns.

Only mask shapes are used: the face mask (SAM 3.1 prompt "face") is drawn as a flat patch on the pose guide
and summed up in one sentence for Muse Image and the critic. No facial features ever leave the photo.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from actsprite import config
from actsprite.align import mask_bbox


@dataclass(frozen=True)
class HeadPose:
    face_share: float  # face area / head area (0 = no face seen: the head is turned away)
    yaw: float  # face centre offset from the head centre, -1 (image left) .. 1 (image right)

    @property
    def turned_away(self) -> bool:
        return self.face_share < config.HEAD_FACE_MIN_SHARE

    def describe(self) -> str:
        """One sentence for the redraw prompt and the critic, in image directions."""
        if self.turned_away:
            return "turned away from the viewer, the back of the head shows"
        turn = abs(self.yaw)
        if turn < config.HEAD_YAW_FRONT:
            return "facing the viewer"
        side = "left" if self.yaw < 0 else "right"
        if turn < config.HEAD_YAW_HALF:
            return f"turned slightly toward the {side} side of the image"
        if turn < config.HEAD_YAW_PROFILE:
            return f"turned toward the {side} side of the image, about half way (three-quarter view)"
        return f"turned toward the {side} side of the image, in profile"


def head_region(person: np.ndarray) -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) of the head: the top HEAD_HEIGHT_SHARE of the body below the top of the head,
    with thin limbs (raised arms) opened away first, as in align.head_band_end."""
    if not person.any():
        return None
    _, top, _, bottom = mask_bbox(person)
    k = max(3, int((bottom - top) * config.GUIDE_LIMB_OPEN)) | 1
    opened = cv2.morphologyEx(person.astype(np.uint8), cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) > 0
    body = opened if opened.any() else person
    _, head_top, _, _ = mask_bbox(body)
    head_bottom = head_top + max(1, int((bottom - head_top) * config.HEAD_HEIGHT_SHARE))
    band = body[head_top:head_bottom]
    cols = np.flatnonzero(band.any(axis=0))
    if len(cols) == 0:
        return None
    # The widest row of the band may include shoulders: take the median row width around the band's centre.
    centre = float(np.median(np.concatenate([np.flatnonzero(r) for r in band if r.any()])))
    half = float(np.median([r.sum() for r in band if r.any()])) / 2
    return int(centre - half), head_top, int(np.ceil(centre + half)), head_bottom


def head_pose(person: np.ndarray, face: np.ndarray | None) -> HeadPose | None:
    """Head direction of one frame; None when the head cannot be found."""
    box = head_region(person)
    if box is None:
        return None
    left, top, right, bottom = box
    head_area = max(1, (right - left) * (bottom - top))
    face = np.zeros_like(person) if face is None else face & cv2.dilate(
        person.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    ys, xs = np.nonzero(face)
    share = len(xs) / head_area
    if share < config.HEAD_FACE_MIN_SHARE:
        return HeadPose(share, 0.0)
    return HeadPose(share, float(np.clip((xs.mean() - (left + right) / 2) / max(1.0, (right - left) / 2), -1, 1)))

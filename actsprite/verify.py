"""Verify: per-frame checks (pose silhouette, critic identity + pose, palette drift) and the combined score."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from actsprite import config
from actsprite.align import fit_to_canvas, mask_bbox
from actsprite.restyle import BODIES


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    if union == 0:
        return 0.0
    return float(np.logical_and(a, b).sum() / union)


def largest_component(mask: np.ndarray) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    if n <= 1:
        return mask.astype(bool)
    return labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))


def _normalise(mask: np.ndarray, height: int, tolerance: int) -> np.ndarray:
    mask = largest_component(mask)
    _, top, _, bottom = mask_bbox(mask)
    placed, _, _ = fit_to_canvas(mask, height * 3, margin=0, scale=height / (bottom - top))
    if tolerance > 0:
        kernel = np.ones((2 * tolerance + 1, 2 * tolerance + 1), np.uint8)
        placed = cv2.dilate(placed.astype(np.uint8), kernel) > 0
    return placed


def silhouette_iou(
    a: np.ndarray,
    b: np.ndarray,
    height: int = config.CELL_SIZE,
    tolerance: int = config.IOU_TOLERANCE_PX,
) -> float:
    """Pose fidelity: IoU after scaling both silhouettes to the same height, feet on
    the same baseline and mask centroids aligned. Specks are dropped and both shapes
    get a small tolerance so armour/outline thickness does not dominate."""
    return mask_iou(_normalise(a, height, tolerance), _normalise(b, height, tolerance))


def leg_zone(mask: np.ndarray, height: int = 200, share: float = config.LEG_ZONE_SHARE) -> np.ndarray:
    """The legs: bottom `share` of the figure, scaled to `height`, feet on the baseline, centred."""
    placed = _normalise(mask, height, 0)
    _, top, _, bottom = mask_bbox(placed)
    placed[: bottom - int(share * (bottom - top))] = False
    return placed


def leg_motion(guide_prev: np.ndarray, guide: np.ndarray, cand_prev: np.ndarray, cand: np.ndarray) -> float | None:
    """How far the candidate's legs moved from the previous frame, relative to how far the pose
    guide's legs moved (about 1 = as much, near 0 = copied). None when the guide's legs barely move."""
    g = 1.0 - mask_iou(leg_zone(guide_prev), leg_zone(guide))
    if g < config.LEG_MOTION_GUIDE_MIN:
        return None
    return (1.0 - mask_iou(leg_zone(cand_prev), leg_zone(cand))) / g


def extract_palette(image: np.ndarray, mask: np.ndarray, colors: int = config.PALETTE_SIZE) -> np.ndarray:
    """Median-cut palette (k, 3) of the subject's pixels."""
    pixels = image[mask].reshape(-1, 1, 3).astype(np.uint8)
    if len(pixels) == 0:
        raise ValueError("Mask is empty: cannot extract a palette.")
    quant = Image.fromarray(pixels, "RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    used = sorted({int(i) for i in np.asarray(quant).ravel()})
    flat = quant.getpalette()
    assert flat is not None
    return np.array([flat[i * 3 : i * 3 + 3] for i in used], dtype=np.float32)


def nearest_palette_distance(pixels: np.ndarray, palette: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For (N, 3) pixels return (distance, index) of the nearest palette colour."""
    d = np.sqrt(((pixels[:, None, :].astype(np.float32) - palette[None, :, :]) ** 2).sum(axis=2))
    return d.min(axis=1), d.argmin(axis=1)


def palette_drift(
    image: np.ndarray,
    mask: np.ndarray,
    palette: np.ndarray,
    max_distance: float = config.PALETTE_MATCH_DISTANCE,
) -> float:
    """Share of subject pixels whose nearest palette colour is farther than max_distance."""
    pixels = image[mask].reshape(-1, 3)
    if len(pixels) == 0:
        return 1.0
    dist, _ = nearest_palette_distance(pixels, palette)
    return float((dist > max_distance).mean())


@dataclass
class FrameScores:
    iou: float
    pose: float  # critic, 1-10
    identity: float  # critic, 1-10
    drift: float
    leg_motion: float | None = None  # see leg_motion(); None = not checked (first frame, still legs)

    @property
    def frozen(self) -> bool:
        """Legs copied from the previous frame instead of following the pose guide."""
        return self.leg_motion is not None and self.leg_motion < config.LEG_MOTION_MIN

    @property
    def rank(self) -> tuple[bool, bool, float]:
        """Sort key for picking the best attempt: passed first, then legs that moved, then score."""
        return (self.passed, not self.frozen, self.combined)

    @property
    def combined(self) -> float:
        return (
            config.SCORE_WEIGHT_IOU * self.iou
            + config.SCORE_WEIGHT_POSE * self.pose / 10.0
            + config.SCORE_WEIGHT_IDENTITY * self.identity / 10.0
            + config.SCORE_WEIGHT_PALETTE * (1.0 - self.drift)
        )

    @property
    def passed(self) -> bool:
        return (
            self.iou >= config.IOU_MIN
            and self.pose >= config.POSE_MIN
            and self.identity >= config.IDENTITY_MIN
            and self.drift <= config.PALETTE_DRIFT_MAX
            and not self.frozen
        )

    def failures(self) -> list[str]:
        out = []
        if self.iou < config.IOU_MIN:
            out.append(f"silhouette IoU {self.iou:.2f} < {config.IOU_MIN}")
        if self.pose < config.POSE_MIN:
            out.append(f"pose {self.pose:.0f} < {config.POSE_MIN}")
        if self.identity < config.IDENTITY_MIN:
            out.append(f"identity {self.identity:.0f} < {config.IDENTITY_MIN}")
        if self.drift > config.PALETTE_DRIFT_MAX:
            out.append(f"palette drift {self.drift:.2f} > {config.PALETTE_DRIFT_MAX}")
        if self.frozen:
            out.append(f"the legs are copied from the previous frame (moved {self.leg_motion:.2f} of the pose guide's "
                       f"change < {config.LEG_MOTION_MIN}): put every leg and paw exactly where the pose guide has it")
        return out


CRITIC_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "identity_score": {"type": "integer", "minimum": 1, "maximum": 10},
        "pose_score": {"type": "integer", "minimum": 1, "maximum": 10},
        "issues": {"type": "array", "items": {"type": "string"}},
        "fix_instruction": {"type": "string"},
    },
    "required": ["identity_score", "pose_score", "issues", "fix_instruction"],
    "additionalProperties": False,
}

_CRITIC_RULES = (
    "identity_score (1-10): is the CANDIDATE the same character as the REFERENCE SHEET{prev_clause}? "
    "Check head and body proportions, outfit details, colors, accessories and line style. Ignore the pose here.\n"
    "pose_score (1-10): does the CANDIDATE's pose match the POSE GUIDE? Compare only the angle of each leg and "
    "knee, whether each foot is on the ground or in the air, {pose_parts}. Ignore costume, "
    "body proportions and art style here. 10 = same pose, 1 = completely different pose.\n"
    "issues: short list of problems. fix_instruction: one sentence telling the artist what to change "
    "(empty string if nothing).\n"
    "Return JSON only."
)


def critic_parts(
    sheet: bytes, prev: bytes | None, guide: bytes, candidate: bytes, body: str = "biped"
) -> list[str | bytes]:
    """Prompt parts for the one-call art-director check (identity + pose)."""
    parts: list[str | bytes] = [
        "You are a strict 2D game animation art director.",
        "REFERENCE SHEET:",
        sheet,
    ]
    if prev is not None:
        parts += ["PREVIOUS APPROVED FRAME:", prev]
    parts += [
        "POSE GUIDE (plain figure):",
        guide,
        "CANDIDATE FRAME:",
        candidate,
        _CRITIC_RULES.format(
            prev_clause=" and visually continuous with the PREVIOUS APPROVED FRAME" if prev is not None else "",
            pose_parts=BODIES[body].critic_pose_parts,
        ),
    ]
    return parts

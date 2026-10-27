"""Verify: the three per-frame checks and the combined score."""

from __future__ import annotations

import numpy as np
from PIL import Image

from actsprite import config
from actsprite.align import fit_to_canvas


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.logical_or(a, b).sum()
    if union == 0:
        return 0.0
    return float(np.logical_and(a, b).sum() / union)


def silhouette_iou(a: np.ndarray, b: np.ndarray, size: int = config.CELL_SIZE) -> float:
    """Pose fidelity: IoU after putting both silhouettes on the same canvas,
    each scaled to fit and anchored at its feet (bottom-centre)."""
    a_fit, _, _ = fit_to_canvas(a, size, margin=0)
    b_fit, _, _ = fit_to_canvas(b, size, margin=0)
    return mask_iou(a_fit, b_fit)


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


def palette_drift(
    image: np.ndarray,
    mask: np.ndarray,
    palette: np.ndarray,
    max_distance: float = config.PALETTE_MATCH_DISTANCE,
) -> float:
    """Share of subject pixels whose nearest palette colour is farther than max_distance."""
    pixels = image[mask].reshape(-1, 3).astype(np.float32)
    if len(pixels) == 0:
        return 1.0
    dist = np.sqrt(((pixels[:, None, :] - palette[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
    return float((dist > max_distance).mean())


def combined_score(iou: float, identity: float, drift: float) -> float:
    return (
        config.SCORE_WEIGHT_IOU * iou
        + config.SCORE_WEIGHT_IDENTITY * identity / 10.0
        + config.SCORE_WEIGHT_PALETTE * (1.0 - drift)
    )


def passes(iou: float, identity: float, drift: float) -> bool:
    return iou >= config.IOU_MIN and identity >= config.IDENTITY_MIN and drift <= config.PALETTE_DRIFT_MAX


CRITIC_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "identity_score": {"type": "integer", "minimum": 1, "maximum": 10},
        "issues": {"type": "array", "items": {"type": "string"}},
        "fix_instruction": {"type": "string"},
    },
    "required": ["identity_score", "issues", "fix_instruction"],
    "additionalProperties": False,
}

CRITIC_PROMPT = (
    "You are a strict 2D game animation art director.\n"
    "Image 1 is the character reference sheet. Image 2 is the previous approved frame. "
    "Image 3 is the candidate frame.\n"
    "Judge only whether image 3 is the SAME character as image 1 and visually continuous with image 2.\n"
    "Check: head and body proportions, outfit details, colors, accessories, line style.\n"
    "Ignore pose differences; pose is checked elsewhere.\n"
    'Return JSON only: {"identity_score": 1-10, "issues": ["short issue", ...], '
    '"fix_instruction": "one sentence telling the artist what to change"}'
)

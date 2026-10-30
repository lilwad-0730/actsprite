"""Align: put a subject on a fixed canvas with its feet on the baseline, and draw pose guides."""

from __future__ import annotations

import cv2
import numpy as np

from actsprite import config


def mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    """(left, top, right, bottom), half-open. Raises on an empty mask."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        raise ValueError("Mask is empty: the subject was not found in this frame.")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def fit_scale(mask: np.ndarray, size: int, margin: int) -> float:
    """Largest scale that fits the subject inside the canvas minus margins."""
    left, top, right, bottom = mask_bbox(mask)
    return min((size - margin) / (bottom - top), (size - 2 * margin) / (right - left))


def fit_to_canvas(
    mask: np.ndarray,
    size: int,
    *,
    margin: int = config.CELL_MARGIN,
    image: np.ndarray | None = None,
    scale: float | None = None,
    background: int = 255,
) -> tuple[np.ndarray, np.ndarray | None, float]:
    """Scale the subject and place it so its lowest pixel sits on the bottom row and
    its mask centroid is horizontally centred (bottom-centre pivot).

    Pass the same `scale` for every frame of an action to keep height differences.
    Returns (mask_canvas, image_canvas_or_None, scale_used).
    """
    left, top, right, bottom = mask_bbox(mask)
    if scale is None:
        scale = fit_scale(mask, size, margin)

    crop_mask = mask[top:bottom, left:right].astype(np.uint8)
    new_w = max(1, round((right - left) * scale))
    new_h = max(1, round((bottom - top) * scale))
    scaled_mask = cv2.resize(crop_mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST) > 0

    centroid_x = float(np.nonzero(scaled_mask)[1].mean()) if scaled_mask.any() else new_w / 2
    dst_x = round(size / 2 - centroid_x)
    dst_y = size - new_h

    out_mask = np.zeros((size, size), dtype=bool)
    _paste(out_mask, scaled_mask, dst_x, dst_y)

    out_image = None
    if image is not None:
        crop_img = image[top:bottom, left:right]
        scaled_img = cv2.resize(crop_img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        out_image = np.full((size, size, 3), background, dtype=np.uint8)
        region = np.zeros((size, size), dtype=bool)
        _paste(region, scaled_mask, dst_x, dst_y)
        placed = np.full((size, size, 3), background, dtype=np.uint8)
        _paste(placed, scaled_img, dst_x, dst_y)
        out_image[region] = placed[region]
    return out_mask, out_image, scale


def size_drift(masks: list[np.ndarray], fps: float, window_s: float = config.DRIFT_SMOOTH_S) -> np.ndarray:
    """Per-frame factor that cancels slow size change (the subject walking toward or away from
    the camera): 1 / height smoothed over window_s, relative to its median. Multiply the shared
    scale by it. Changes faster than the window (the bob within a step) are kept."""
    heights = np.array([mask_bbox(m)[3] - mask_bbox(m)[1] for m in masks], float)
    k = max(1, round(window_s * fps)) | 1  # odd width, centred
    smooth = np.convolve(np.pad(heights, k // 2, mode="edge"), np.ones(k) / k, mode="valid")
    return float(np.median(smooth)) / smooth


def shared_scale(
    masks: list[np.ndarray], size: int, margin: int, rel: np.ndarray | list[float] | None = None
) -> float:
    """One scale for a whole action: the largest that fits every frame, so a crouch stays shorter.
    With `rel` (from size_drift) frame i is drawn at scale * rel[i]."""
    if rel is None:
        rel = [1.0] * len(masks)
    return min(fit_scale(m, size, margin) / r for m, r in zip(masks, rel))


def align_sequence(
    masks: list[np.ndarray],
    images: list[np.ndarray] | None = None,
    *,
    size: int = config.CELL_SIZE,
    margin: int = config.CELL_MARGIN,
    rel: np.ndarray | list[float] | None = None,
) -> tuple[list[np.ndarray], list[np.ndarray] | None, float]:
    """Put every frame of one action in place on the same canvas with ONE scale
    (set by the frame that needs the most room), so height changes between frames survive
    and the subject's travel across the video is removed (run in place).
    `rel` (from size_drift) also removes the camera-distance change in walk/run clips."""
    if not masks:
        raise ValueError("align_sequence needs at least one mask.")
    if rel is None:
        rel = [1.0] * len(masks)
    scale = shared_scale(masks, size, margin, rel)
    out_masks: list[np.ndarray] = []
    out_images: list[np.ndarray] | None = [] if images is not None else None
    for i, m in enumerate(masks):
        fm, fi, _ = fit_to_canvas(m, size, margin=margin, image=None if images is None else images[i],
                                  scale=scale * rel[i])
        out_masks.append(fm)
        if out_images is not None:
            assert fi is not None
            out_images.append(fi)
    return out_masks, out_images, scale


def _paste(dst: np.ndarray, src: np.ndarray, x: int, y: int) -> None:
    h, w = src.shape[:2]
    H, W = dst.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, W), min(y + h, H)
    if x1 > x0 and y1 > y0:
        dst[y0:y1, x0:x1] = src[y0 - y : y1 - y, x0 - x : x1 - x]


def head_band_end(mask: np.ndarray, fraction: float, limb_open: float = config.GUIDE_LIMB_OPEN) -> int:
    """Row where the head band ends: `fraction` of the figure below the top of the head. The top of the head
    is the top of the figure once limbs thinner than `limb_open` of its height are opened away, so arms
    raised overhead do not push the band up above the face."""
    _, top, _, bottom = mask_bbox(mask)
    k = max(3, int((bottom - top) * limb_open)) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    opened = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, kernel)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(opened, 8)
    if n > 1:
        body = labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        top = max(top, mask_bbox(body)[1])
    return top + int((bottom - top) * fraction)


def pose_guide(
    image: np.ndarray,
    mask: np.ndarray,
    *,
    size: int = config.GUIDE_SIZE,
    margin: int = config.CELL_MARGIN * 2,
    fill: bool = False,
    head_fraction: float = 0.0,
    scale: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Black-on-white line art of the subject only (no photo pixels leave this function).

    fill: paint the silhouette light gray under the lines (stronger pose signal).
    head_fraction: drop interior lines from the top of the figure down to this share below the top of the
    head (e.g. 0.18, see head_band_end) so facial features of a real actor never reach the image model.
    scale: pass shared_scale(...) of the whole action so height changes (crouch, jump) survive.
    Returns (guide_rgb, guide_mask) on a size x size canvas, feet on the bottom row.
    """
    fitted_mask, fitted_image, _ = fit_to_canvas(mask, size, margin=margin, image=image, scale=scale)
    assert fitted_image is not None
    gray = cv2.cvtColor(fitted_image, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 40, 120) > 0
    inner = cv2.erode(fitted_mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    edges &= inner
    if head_fraction > 0:
        edges[: head_band_end(fitted_mask, head_fraction)] = False

    guide = np.full((size, size, 3), 255, dtype=np.uint8)
    if fill:
        guide[fitted_mask] = config.GUIDE_FILL_GRAY
    guide[edges] = 0
    contours, _ = cv2.findContours(fitted_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(guide, contours, -1, (0, 0, 0), thickness=3)
    return guide, fitted_mask

"""Pack: consistency post-processing (pixelate onto one palette) and, later, sprite sheet + JSON."""

from __future__ import annotations

import cv2
import numpy as np

from actsprite.verify import nearest_palette_distance


def map_to_palette(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Replace every pixel with its nearest palette colour."""
    flat = rgb.reshape(-1, 3)
    _, idx = nearest_palette_distance(flat, palette)
    return palette[idx].round().astype(np.uint8).reshape(rgb.shape)


def pixelate(rgba: np.ndarray, size: int, palette: np.ndarray | None = None) -> np.ndarray:
    """Downscale an aligned RGBA cell to size x size with hard alpha, optionally onto a shared palette.

    Colours are averaged over opaque pixels only, so the white background never bleeds
    into the edge pixels. Every frame of an action goes through the same palette, which
    is what makes small frame-to-frame colour wobble disappear.
    """
    if rgba.shape[2] != 4:
        raise ValueError("pixelate expects an RGBA image (H, W, 4).")
    alpha = rgba[..., 3:4].astype(np.float32) / 255.0
    rgb = rgba[..., :3].astype(np.float32)
    small_alpha = cv2.resize(alpha, (size, size), interpolation=cv2.INTER_AREA)
    small_alpha = small_alpha.reshape(size, size, 1)
    small_rgb = cv2.resize(rgb * alpha, (size, size), interpolation=cv2.INTER_AREA)
    small_rgb = small_rgb / np.maximum(small_alpha, 1e-6)
    opaque = small_alpha[..., 0] >= 0.5

    out_rgb = np.clip(small_rgb, 0, 255).astype(np.uint8)
    if palette is not None:
        out_rgb = map_to_palette(out_rgb, palette)
    out = np.zeros((size, size, 4), np.uint8)
    out[..., :3] = out_rgb
    out[..., 3] = opaque * 255
    out[~opaque, :3] = 0
    return out


def upscale_nearest(image: np.ndarray, factor: int) -> np.ndarray:
    """Blow up a pixel sprite for previews without blurring."""
    return cv2.resize(image, (image.shape[1] * factor, image.shape[0] * factor), interpolation=cv2.INTER_NEAREST)

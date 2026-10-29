"""Image helpers shared by the pipeline and the spikes: PNG bytes in and out, saving, tiling."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def png_bytes(rgb: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if not ok:
        raise ValueError("Could not encode the image as PNG.")
    return buf.tobytes()


def decode_rgb(data: bytes) -> np.ndarray:
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Could not decode image bytes.")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def save_rgb(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def save_rgba(path: Path, rgba: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))


def tile(images: list[np.ndarray], cols: int, cell: int | tuple[int, int] = 256) -> np.ndarray:
    """Grid of RGB images on white; cell is a square size or (height, width)."""
    ch, cw = (cell, cell) if isinstance(cell, int) else cell
    rows = (len(images) + cols - 1) // cols
    sheet = np.full((rows * ch, cols * cw, 3), 255, np.uint8)
    for i, img in enumerate(images):
        r, c = divmod(i, cols)
        resized = cv2.resize(img, (cw, ch), interpolation=cv2.INTER_AREA)
        sheet[r * ch : (r + 1) * ch, c * cw : (c + 1) * cw] = resized
    return sheet

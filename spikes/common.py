"""Small helpers shared by the Day 1 feasibility spikes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from actsprite import config
from actsprite.capture import largest_object, parse_sam_output
from actsprite.meta_client import MetaClient

OUT = config.ROOT / "spikes" / "out"

STYLES = {
    "pixel": "pixel art, crisp hard-edged pixels, limited palette, no anti-aliasing",
    "handdrawn": "hand-drawn 2D game art, clean ink outlines, flat cel shading",
}

KNIGHT = (
    "an original small knight: silver armor, blue cape, red plume on the helmet, short sword at the hip"
)

SHEET_PROMPT = (
    "Original character design for a 2D side-scrolling game: {character}. "
    "Style: {style}. Full body, side view facing right, standing neutral pose, centered, "
    "feet at the bottom. Plain solid white background, no shadow, no text, no border."
)

REDRAW_PROMPT = (
    "Redraw the character from image 1 in the exact pose shown by the line-art pose guide (the last image).\n"
    "Keep the character's design, proportions, outfit and colors identical to image 1.\n"
    "{prev_line}"
    "Full body, side view, facing right, centered, feet touching the bottom edge like the pose guide.\n"
    "Style: {style}. Plain solid white background, no shadow, no props, no text, no border.\n"
    "{fix}"
)


def redraw_parts(
    sheet: bytes, guide: bytes, prev: bytes | None, style: str, fix: str = ""
) -> list[str | bytes]:
    parts: list[str | bytes] = ["Image 1 - character reference sheet:", sheet]
    prev_line = ""
    if prev is not None:
        parts += ["Image 2 - previous animation frame:", prev]
        prev_line = "Match the previous animation frame (image 2) for line weight, shading and colors.\n"
    parts += [
        "Last image - pose guide (line art):",
        guide,
        REDRAW_PROMPT.format(prev_line=prev_line, style=STYLES[style], fix=fix),
    ]
    return parts


def png_bytes(rgb: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return buf.tobytes()


def decode_rgb(data: bytes) -> np.ndarray:
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Could not decode image bytes.")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def save_rgb(path: Path, rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def save_mask(path: Path, mask: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), mask.astype(np.uint8) * 255)


def load_mask(path: Path) -> np.ndarray:
    return cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) > 127


def sam_mask(client: MetaClient, rgb: np.ndarray, prompt: str, note: str = "") -> np.ndarray | None:
    """Largest SAM 3.1 match for `prompt` in a still image, as a full-size bool mask."""
    text, _ = client.segment(png_bytes(rgb), prompt, note=note)
    obj = largest_object(parse_sam_output(text, (rgb.shape[1], rgb.shape[0]), video=False))
    return obj.mask if obj is not None else None


def estimate(desc: str, usd: float) -> None:
    print(f"[cost] {desc}: estimated ${usd:.3f} (cached calls are free)")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def silhouette_overlay(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Red = a only, green = b only, yellow = both (inputs already on the same canvas)."""
    out = np.full((*a.shape, 3), 255, np.uint8)
    out[a & ~b] = (230, 60, 60)
    out[b & ~a] = (60, 180, 60)
    out[a & b] = (230, 200, 40)
    return out


def tile(images: list[np.ndarray], cols: int, cell: int = 256) -> np.ndarray:
    rows = (len(images) + cols - 1) // cols
    sheet = np.full((rows * cell, cols * cell, 3), 255, np.uint8)
    for i, img in enumerate(images):
        r, c = divmod(i, cols)
        resized = cv2.resize(img, (cell, cell), interpolation=cv2.INTER_AREA)
        sheet[r * cell : (r + 1) * cell, c * cell : (c + 1) * cell] = resized
    return sheet

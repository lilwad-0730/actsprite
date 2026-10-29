"""Small helpers shared by the Day 1 feasibility spikes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from actsprite import config
from actsprite.images import decode_rgb, png_bytes, save_rgb, tile  # noqa: F401 (re-exported)
from actsprite.meta_client import print_estimate as estimate  # noqa: F401 (re-exported)
from actsprite.redraw import sam_mask  # noqa: F401 (re-exported)

OUT = config.ROOT / "spikes" / "out"

STYLES = {
    "pixel": "pixel art, crisp hard-edged pixels, limited palette, no anti-aliasing",
    "handdrawn": "hand-drawn 2D game art, clean ink outlines, flat cel shading",
}

CHARACTERS = {
    "knight": "an original small knight: silver armor, blue cape, red plume on the helmet, short sword at the hip",
    # v2: no cape (it hides the pose) and normal proportions (closer to the actor's silhouette)
    "knight2": (
        "an original young knight with normal adult proportions (about 6 heads tall): fitted silver plate "
        "armor with blue cloth trim, red plume on the helmet, short sword in a scabbard on the hip, no cape"
    ),
}
KNIGHT = CHARACTERS["knight"]

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


REDRAW_PROMPT_V2 = (
    "Redraw the character from image 1 in the EXACT pose of the pose guide (the last image). "
    "The pose guide is the only source of the pose: match the angle of every limb, where each foot and knee is, "
    "the arm positions and the body lean.\n"
    "Keep the character's design, outfit and colors identical to image 1.\n"
    "{prev_line}"
    "Full body, side view, facing right, feet touching the bottom edge like the pose guide.\n"
    "Style: {style}. Plain solid white background, no shadow, no props, no text, no border.\n"
    "{fix}"
)


def redraw_parts(
    sheet: bytes, guide: bytes, prev: bytes | None, style: str, fix: str = "", version: str = "v1"
) -> list[str | bytes]:
    parts: list[str | bytes] = ["Image 1 - character reference sheet:", sheet]
    prev_line = ""
    if prev is not None:
        parts += ["Image 2 - previous animation frame:", prev]
        prev_line = (
            "Match the previous animation frame (image 2) for line weight, shading and colors.\n"
            if version == "v1"
            else "Use image 2 (the previous animation frame) ONLY for line weight, shading and colors; "
            "do NOT copy its pose.\n"
        )
    template = REDRAW_PROMPT if version == "v1" else REDRAW_PROMPT_V2
    parts += [
        "Last image - pose guide (line art):" if version == "v1" else "Last image - pose guide:",
        guide,
        template.format(prev_line=prev_line, style=STYLES[style], fix=fix),
    ]
    return parts


def save_mask(path: Path, mask: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), mask.astype(np.uint8) * 255)


def load_mask(path: Path) -> np.ndarray:
    return cv2.imread(str(path), cv2.IMREAD_GRAYSCALE) > 127


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

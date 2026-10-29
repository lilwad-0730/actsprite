"""Restyle: character sheet and per-frame redraw prompts for Muse Image, plus white-background cutout."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from actsprite import config


@dataclass(frozen=True)
class Style:
    prompt: str  # what we ask Muse Image to draw
    pixelate: bool  # pixel look is applied in post (pack.pixelate), not by the model


# Pixel art is drawn as a clean flat illustration and pixelated by us: the model's own
# "pixel art" was neither on a consistent grid nor consistent between frames (Day 1).
STYLES: dict[str, Style] = {
    "pixel": Style("clean 2D game sprite illustration, bold dark outlines, flat colors with one shade step, "
                   "limited palette, no gradients, no texture", pixelate=True),
    "handdrawn": Style("hand-drawn 2D game art, clean ink outlines, flat cel shading", pixelate=False),
    "ink": Style("black ink brush silhouette with a few white highlight strokes, sumi-e inspired, "
                 "single flat black fill", pixelate=False),
}


@dataclass(frozen=True)
class Body:
    proportions: str  # sheet rule that keeps the drawn silhouette comparable with the filmed one
    pose_parts: str  # what the redraw must match besides legs and feet
    critic_pose_parts: str  # the same, for the art-director check


# Biped strings are the Day 1 wording unchanged, so earlier knight calls stay cached.
BODIES: dict[str, Body] = {
    "biped": Body("normal body proportions about 6 heads tall",
                  "the arm positions and the body lean", "the arm positions and the torso lean"),
    "quadruped": Body("natural four-legged animal proportions with all four legs clearly visible",
                      "which front and hind legs are forward, the head and neck line and the tail",
                      "which front and hind legs are forward, the head and neck line and the tail"),
}

# Day 1: large flowing parts hide the pose and break silhouette checks; normal
# proportions keep the character's silhouette comparable with the actor's.
SHEET_RULES = "no cape, no cloak, no long scarf or other large flowing parts"

SHEET_PROMPT = (
    "Original character design for a 2D side-scrolling game: {description}, {rules}. "
    "Style: {style}. Full body, side view facing right, standing neutral pose, centered, feet at the bottom. "
    "Plain solid white background, no shadow, no text, no border."
)

REDRAW_PROMPT = (
    "Redraw the character from image 1 in the EXACT pose of the pose guide (the last image). "
    "The pose guide is the only source of the pose: match the angle of every limb, where each foot and knee is, "
    "{pose_parts}.\n"
    "Keep the character's design, outfit and colors identical to image 1.\n"
    "{prev_line}"
    "Full body, side view, facing right, feet touching the bottom edge like the pose guide.\n"
    "Style: {style}. Plain solid white background, no shadow, no props, no text, no border.\n"
    "{fix}"
)
PREV_LINE = (
    "Use image 2 (the previous animation frame) ONLY for line weight, shading and colors; do NOT copy its pose.\n"
)


def sheet_prompt(description: str, style: str, body: str = "biped") -> str:
    rules = f"{BODIES[body].proportions}, {SHEET_RULES}"
    return SHEET_PROMPT.format(description=description, rules=rules, style=STYLES[style].prompt)


def redraw_parts(
    sheet: bytes, guide: bytes, prev: bytes | None, style: str, fix: str = "", body: str = "biped"
) -> list[str | bytes]:
    """Interleaved prompt for one frame: sheet, (previous approved frame), pose guide, instructions."""
    parts: list[str | bytes] = ["Image 1 - character reference sheet:", sheet]
    if prev is not None:
        parts += ["Image 2 - previous animation frame:", prev]
    fix_line = f"Fix from the art director: {fix.strip()}\n" if fix.strip() else ""
    parts += [
        "Last image - pose guide:",
        guide,
        REDRAW_PROMPT.format(prev_line=PREV_LINE if prev is not None else "", style=STYLES[style].prompt,
                             fix=fix_line, pose_parts=BODIES[body].pose_parts),
    ]
    return parts


def white_flood_cutout(
    rgb: np.ndarray,
    tolerance: int = config.CUTOUT_WHITE_TOLERANCE,
    min_speck: float = config.CUTOUT_MIN_SPECK,
) -> np.ndarray:
    """Subject mask = everything not connected to the image border through near-white pixels.

    Keeps thin parts (swords, plumes) that a segmentation mask may drop, and keeps white
    highlights inside the character because they are not connected to the border.
    """
    h, w = rgb.shape[:2]
    near_white = (rgb.min(axis=2) > 255 - tolerance).astype(np.uint8)
    border = np.zeros((h, w), bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    n, labels = cv2.connectedComponents(near_white, connectivity=4)
    background_labels = np.unique(labels[border & (near_white == 1)])
    background = np.isin(labels, background_labels[background_labels > 0])
    subject = ~background

    n, labels, stats, _ = cv2.connectedComponentsWithStats(subject.astype(np.uint8), 8)
    keep = np.zeros((h, w), bool)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_speck * h * w:
            keep |= labels == i
    return keep

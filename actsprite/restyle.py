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
    line_gaps: float = 0.0  # unfilled line art: close outline gaps up to this share of image height before cutout


# Pixel art is drawn as a clean flat illustration and pixelated by us: the model's own
# "pixel art" was neither on a consistent grid nor consistent between frames (Day 1).
STYLES: dict[str, Style] = {
    "pixel": Style("clean 2D game sprite illustration, bold dark outlines, flat colors with one shade step, "
                   "limited palette, no gradients, no texture", pixelate=True),
    "handdrawn": Style("hand-drawn 2D game art, clean ink outlines, flat cel shading", pixelate=False),
    "ink": Style("black ink brush silhouette with a few white highlight strokes, sumi-e inspired, "
                 "single flat black fill", pixelate=False),
    # The inside of the figure is white like the background, so sketchy outlines must be closed first.
    "lineart": Style("hand-drawn line art like a pencil sketch: thin dark sketchy lines on white paper, "
                     "no color fill, no shading, same line weight as image 1", pixelate=False,
                     line_gaps=config.CUTOUT_LINE_GAP),
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
    "{view_line}"
    "Style: {style}. Plain solid white background, no shadow, no props, no text, no border.\n"
    "{fix}"
)
# How the character faces in every frame. "side" is the Day 1 wording unchanged (cached calls stay valid);
# "front" is for clips filmed facing the camera (10/30 dance clip: side-view redraws turned the dance sideways).
VIEW_LINES = {
    "side": "Full body, side view, facing right, feet touching the bottom edge like the pose guide.\n",
    "front": "Full body, front view, facing the viewer, face visible, feet touching the bottom edge like the "
             "pose guide. The pose guide shows the actor from the front: the arm on the left of the guide is the "
             "arm on the left of the drawing.\n",
}
VIEWS = tuple(VIEW_LINES)
# Front view sheet: drawn from the side-view sheet so the design stays the same character.
FRONT_SHEET_PROMPT = (
    "Draw the same character as image 1 seen from the front, facing the viewer, face visible: same design, outfit, "
    "colors, proportions and line style. Full body, standing neutral pose with the arms slightly away from the "
    "body, centered, feet at the bottom.\n"
    "Style: {style}. Plain solid white background, no shadow, no text, no border."
)
PREV_LINE = (
    "Use image 2 (the previous animation frame) ONLY for line weight, shading and colors; do NOT copy its pose.\n"
)
# Anchor mode: every frame after the first refers to the approved first frame, so frames 1-7 can run at once.
ANCHOR_LABEL = "Image 2 - approved first frame of this animation:"
ANCHOR_LINE = (
    "Use image 2 (the approved first frame of this animation) ONLY for line weight, shading and colors; "
    "do NOT copy its pose.\n"
)
# Same, with the anchor's legs painted white (hide_legs): the model copied frame 0's legs in 8 of 14 frames (10/30).
ANCHOR_NOLEGS_LABEL = "Image 2 - approved first frame of this animation, legs painted out on purpose:"
ANCHOR_NOLEGS_LINE = (
    "Use image 2 (the approved first frame of this animation, legs painted out on purpose) ONLY for line weight, "
    "shading and colors; do NOT copy its pose. Draw every leg only from the pose guide.\n"
)


def hide_legs(rgb: np.ndarray, mask: np.ndarray, share: float = config.LEG_ZONE_SHARE) -> np.ndarray:
    """Copy of `rgb` with the bottom `share` of the figure (from the mask's box) painted white, edge to edge."""
    rows = np.flatnonzero(mask.any(axis=1))
    if len(rows) == 0:
        raise ValueError("Empty mask: nothing to hide.")
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    out = rgb.copy()
    out[bottom - int(share * (bottom - top)) :] = 255
    return out


def sheet_prompt(description: str, style: str, body: str = "biped") -> str:
    rules = f"{BODIES[body].proportions}, {SHEET_RULES}"
    return SHEET_PROMPT.format(description=description, rules=rules, style=STYLES[style].prompt)


def front_sheet_parts(side_sheet: bytes, style: str) -> list[str | bytes]:
    """Prompt for the front-view sheet, drawn from the side-view sheet."""
    return ["Image 1 - character reference sheet (side view):", side_sheet,
            FRONT_SHEET_PROMPT.format(style=STYLES[style].prompt)]


def redraw_parts(
    sheet: bytes, guide: bytes, prev: bytes | None, style: str, fix: str = "", body: str = "biped",
    anchor: bool = False, legs_hidden: bool = False, view: str = "side",
) -> list[str | bytes]:
    """Interleaved prompt for one frame: sheet, (previous or, with anchor, first approved frame), pose guide,
    instructions. legs_hidden: the anchor was sent through hide_legs. view: key of VIEW_LINES."""
    if legs_hidden and not anchor:
        raise ValueError("legs_hidden only applies to the anchor (first) frame: pass anchor=True.")
    if view not in VIEW_LINES:
        raise ValueError(f"Unknown view '{view}'; use one of {VIEWS}.")
    label, ref_line = (
        (ANCHOR_NOLEGS_LABEL, ANCHOR_NOLEGS_LINE) if legs_hidden
        else (ANCHOR_LABEL, ANCHOR_LINE) if anchor
        else ("Image 2 - previous animation frame:", PREV_LINE)
    )
    parts: list[str | bytes] = ["Image 1 - character reference sheet:", sheet]
    if prev is not None:
        parts += [label, prev]
    else:
        ref_line = ""
    fix_line = f"Fix from the art director: {fix.strip()}\n" if fix.strip() else ""
    parts += [
        "Last image - pose guide:",
        guide,
        REDRAW_PROMPT.format(prev_line=ref_line, style=STYLES[style].prompt, fix=fix_line,
                             pose_parts=BODIES[body].pose_parts, view_line=VIEW_LINES[view]),
    ]
    return parts


def white_flood_cutout(
    rgb: np.ndarray,
    tolerance: int = config.CUTOUT_WHITE_TOLERANCE,
    min_speck: float = config.CUTOUT_MIN_SPECK,
    line_gaps: float = 0.0,
) -> np.ndarray:
    """Subject mask = everything not connected to the image border through near-white pixels.

    Keeps thin parts (swords, plumes) that a segmentation mask may drop, and keeps white
    highlights inside the character because they are not connected to the border.

    line_gaps > 0 (unfilled line art, white inside): the flood may not pass within
    line_gaps * height of a line, so small breaks in a sketchy outline do not let the
    background leak into the figure; the background is then grown back up to the lines.
    """
    h, w = rgb.shape[:2]
    near_white = (rgb.min(axis=2) > 255 - tolerance).astype(np.uint8)
    passable = near_white
    kernel = None
    if line_gaps > 0:
        r = max(1, round(line_gaps * h))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        passable = near_white & (cv2.dilate(1 - near_white, kernel) == 0)
    border = np.zeros((h, w), bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    n, labels = cv2.connectedComponents(passable, connectivity=4)
    background_labels = np.unique(labels[border & (passable == 1)])
    background = np.isin(labels, background_labels[background_labels > 0])
    if kernel is not None:
        background = (cv2.dilate(background.astype(np.uint8), kernel) > 0) & (near_white == 1)
    subject = ~background

    n, labels, stats, _ = cv2.connectedComponentsWithStats(subject.astype(np.uint8), 8)
    keep = np.zeros((h, w), bool)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_speck * h * w:
            keep |= labels == i
    return keep

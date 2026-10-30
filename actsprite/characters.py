"""Characters: the built-in showcase designs, or the user's own drawing, and their reference sheet."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import cv2
import numpy as np

from actsprite import config
from actsprite.errors import PipelineError
from actsprite.images import decode_rgb, png_bytes
from actsprite.meta_client import MetaClient, print_estimate
from actsprite.restyle import BODIES, STYLES, VIEWS, front_sheet_parts, sheet_prompt, white_flood_cutout
from actsprite.verify import extract_palette


@dataclass(frozen=True)
class Character:
    name: str
    description: str  # used to generate the sheet when there is no sheet_path
    body: str = "biped"  # key of restyle.BODIES
    sam_prompt: str = "person"  # noun SAM 3.1 uses to find the drawn character in a redraw
    style: str = "pixel"  # key of restyle.STYLES
    sheet_path: str | None = None  # the user's own design is the reference sheet (nothing generated)
    sheet_faces_left: bool = False  # mirror the user's sheet: every frame is drawn facing right
    view: str = "side"  # key of restyle.VIEW_LINES: side (facing right) or front (facing the viewer)

    def __post_init__(self) -> None:
        if self.body not in BODIES:
            raise PipelineError(f"Unknown body '{self.body}'; use one of {sorted(BODIES)}.")
        if self.style not in STYLES:
            raise PipelineError(f"Unknown style '{self.style}'; use one of {sorted(STYLES)}.")
        if self.view not in VIEWS:
            raise PipelineError(f"Unknown view '{self.view}'; use one of {', '.join(VIEWS)}.")


# The three showcase characters. The descriptions are part of the cached prompts: keep them unchanged.
PRESETS = {
    "knight": Character("knight", "an original young knight: fitted silver plate armor with blue cloth trim, red plume "
                        "on the helmet, short sword in a scabbard on the hip", "biped", "knight"),
    "hound": Character("hound", "an original hound companion for a knight: short sandy-gold fur, cream muzzle and "
                       "belly, dark brown ear tips, a small silver chest plate with blue cloth trim, red leather collar",
                       "quadruped", "dog"),
    # Drawn for this project (10/29): plain bald young man in a fitted suit with seam lines, pencil lines, no fill.
    "lineman": Character("lineman", "a plain young man drawn as a pencil line sketch: bald head, slim build, fitted "
                         "bodysuit with seam lines", "biped", "person", style="lineart",
                         sheet_path=str(config.ROOT / "man in line.jpg"), sheet_faces_left=True),
}
DEFAULT_SAM_PROMPT = {"biped": "person", "quadruped": "animal"}


def cutout(rgb: np.ndarray, ch: Character) -> np.ndarray:
    """The drawn character's mask on its white background."""
    return white_flood_cutout(rgb, line_gaps=STYLES[ch.style].line_gaps)


def user_sheet(ch: Character) -> np.ndarray:
    """The user's design on a square white canvas, facing right, feet near the bottom (like a generated sheet)."""
    if ch.sheet_path is None:
        raise PipelineError(f"Character '{ch.name}' has no sheet image.")
    bgr = cv2.imread(ch.sheet_path)
    if bgr is None:
        raise PipelineError(f"Character sheet not found or not an image: {ch.sheet_path} (use PNG or JPG).")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    if ch.sheet_faces_left:
        rgb = rgb[:, ::-1].copy()
    h, w = rgb.shape[:2]
    side = max(h, w)
    canvas = np.full((side, side, 3), 255, np.uint8)
    canvas[side - h :, (side - w) // 2 : (side - w) // 2 + w] = rgb
    return canvas


def make_sheet(client: MetaClient, ch: Character, note: str = "") -> tuple[bytes, np.ndarray, np.ndarray]:
    """(png bytes, rgb, palette) of the reference sheet: the user's image, or one Muse Image generation.
    Front view: one more Muse Image call draws the side-view sheet seen from the front."""
    if ch.view == "front":
        side_png, _, _ = make_sheet(client, replace(ch, view="side"), note)
        print_estimate(f"front view sheet {ch.name} (Muse Image)", config.PRICE_IMAGE)
        png, _ = client.generate_image(front_sheet_parts(side_png, ch.style), note=f"{note or ch.name} front sheet")
        rgb = decode_rgb(png)
    elif ch.sheet_path:
        rgb = user_sheet(ch)
        png = png_bytes(rgb)
    else:
        print_estimate(f"character sheet {ch.name} (Muse Image)", config.PRICE_IMAGE)
        png, _ = client.generate_image([sheet_prompt(ch.description, ch.style, ch.body)],
                                       note=note or f"sheet {ch.name}")
        rgb = decode_rgb(png)
    palette = extract_palette(rgb, cutout(rgb, ch))
    return png, rgb, palette


def custom_character(name: str, *, sheet: Path | None = None, description: str = "", body: str = "biped",
                     style: str = "pixel", faces_left: bool = False, sam_prompt: str | None = None) -> Character:
    """The user's own character: their drawing (sheet) or a text description Muse Image designs from."""
    if sheet is None and not description.strip():
        raise PipelineError("A custom character needs --sheet (your drawing) or --description (text to design from).")
    return Character(name, description.strip(), body, sam_prompt or DEFAULT_SAM_PROMPT[body], style,
                     str(sheet) if sheet else None, faces_left)

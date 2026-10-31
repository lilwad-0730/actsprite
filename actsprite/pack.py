"""Pack: consistency post-processing (pixelate onto one palette), sprite sheet, JSON for Unity, preview GIF."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from actsprite import config
from actsprite.align import fit_to_canvas
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


def _height(mask: np.ndarray) -> int:
    ys = np.nonzero(mask)[0]
    return int(ys.max() - ys.min() + 1) if len(ys) else 0


def follow_guide_height(rgbs: list[np.ndarray], cuts: list[np.ndarray],
                        guide_masks: list[np.ndarray]) -> tuple[list[np.ndarray], list[np.ndarray], list[float]]:
    """Squash each redraw vertically so the figure's height changes from frame to frame like the actor's in the
    pose guides (Muse Image draws every frame at full height). Frame 0 (the anchor, drawn at the size every other
    action uses) keeps its size; nothing is stretched past the drawn size. The canvas size stays and the freed rows
    go on top, so the feet stay where they were.
    Returns the new redraws, their cutouts and the factor used per frame."""
    gh = np.array([_height(m) for m in guide_masks], float)
    rh = np.array([_height(c) for c in cuts], float)
    if (gh == 0).any() or (rh == 0).any():
        return rgbs, cuts, [1.0] * len(rgbs)
    f = (gh / np.median(gh)) / (rh / np.median(rh))
    f = np.minimum(f / f[0], 1.0)
    new_rgbs, new_cuts = [], []
    for rgb, cut, s in zip(rgbs, cuts, f):
        h, w = cut.shape
        nh = max(1, round(h * s))
        if nh == h:
            new_rgbs.append(rgb)
            new_cuts.append(cut)
            continue
        small = cv2.resize(rgb, (w, nh), interpolation=cv2.INTER_AREA)
        small_cut = cv2.resize(cut.astype(np.uint8), (w, nh), interpolation=cv2.INTER_NEAREST) > 0
        new_rgbs.append(np.vstack([np.full((h - nh, w, 3), 255, np.uint8), small]))
        new_cuts.append(np.vstack([np.zeros((h - nh, w), bool), small_cut]))
    return new_rgbs, new_cuts, [round(float(s), 4) for s in f]


def sprite_cells(rgbs: list[np.ndarray], cuts: list[np.ndarray], palette: np.ndarray,
                 pixel_size: int | None) -> list[np.ndarray]:
    """One RGBA cell per redrawn frame: feet on the bottom row, horizontally centred, the same scale for every
    frame (the redraw canvas width maps to the cell width). pixel_size: pixelate onto the sheet palette at
    that size (pixel styles); None keeps the drawn lines at CELL_SIZE (hand-drawn styles)."""
    cells = []
    for rgb, cut in zip(rgbs, cuts):
        m, img, _ = fit_to_canvas(cut, config.CELL_SIZE, image=rgb, scale=config.CELL_SIZE / rgb.shape[1])
        assert img is not None
        rgba = np.dstack([img, m.astype(np.uint8) * 255])
        cells.append(pixelate(rgba, pixel_size, palette) if pixel_size else rgba)
    return cells


def export_cells(cells: list[np.ndarray], pixel_art: bool) -> list[np.ndarray]:
    """Cells at the contract's grid size: pixel art is drawn at SPRITE_PIXEL_SIZE and each art pixel becomes a
    square block of a CELL_PIXEL_ART cell (same look, sharper in engines); other styles stay at CELL_SIZE."""
    if not pixel_art:
        return cells
    factor = config.CELL_PIXEL_ART // cells[0].shape[0]
    return [upscale_nearest(c, factor) if factor > 1 else c for c in cells]


def sheet_from_rows(rows: list[list[np.ndarray]]) -> np.ndarray:
    """One action per row, frames left to right, fixed cells, transparent background."""
    h, w = rows[0][0].shape[:2]
    if any(c.shape[:2] != (h, w) for row in rows for c in row):
        raise ValueError("Every frame of a character must have the same cell size.")
    sheet = np.zeros((len(rows) * h, max(len(r) for r in rows) * w, 4), np.uint8)
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            sheet[r * h : (r + 1) * h, c * w : (c + 1) * w] = cell
    return sheet


def action_fps(mode: str) -> int:
    """Contract defaults: idle (loop) 8 fps, every other action 15."""
    return config.FPS_IDLE if mode == "loop" else config.FPS_ACTION


def character_meta(character: str, style: str, cell: tuple[int, int], actions: list[dict]) -> dict:
    """<name>_meta.json, the contract shared with the Unity importer (docs/02_product_spec.md 4.3):
    `actions` in sheet row order, each with name, frames, fps, loop. Pivot is fixed at the feet."""
    return {
        "character": character,
        "style": style,
        "cell": {"width": cell[0], "height": cell[1]},
        "pivot": {"x": 0.5, "y": 0.0},
        "actions": [{"name": a["name"], "row": row, "frames": a["frames"], "fps": a["fps"], "loop": a["loop"]}
                    for row, a in enumerate(actions)],
    }


def preview_gif(cells: list[np.ndarray], path: Path, fps: float, size: int = config.CELL_SIZE,
                background: tuple[int, int, int] = (235, 235, 235)) -> None:
    """Animated preview at the action's fps on a light grey background; small cells are blown up unblurred."""
    frames = []
    for cell in cells:
        if cell.shape[0] < size:
            cell = upscale_nearest(cell, max(1, size // cell.shape[0]))
        rgba = Image.fromarray(cell, "RGBA")
        frames.append(Image.alpha_composite(Image.new("RGBA", rgba.size, (*background, 255)), rgba).convert("RGB"))
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=round(1000 / fps), loop=0)

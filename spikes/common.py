"""Small helpers shared by the Day 1 feasibility spikes."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
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


_parse_pool: ProcessPoolExecutor | None = None
_parse_pool_lock = threading.Lock()


def _sam_parse_pool() -> ProcessPoolExecutor:
    global _parse_pool
    with _parse_pool_lock:
        if _parse_pool is None:
            _parse_pool = ProcessPoolExecutor(max_workers=config.REDRAW_WORKERS)
        return _parse_pool


def sam_mask(client: MetaClient, rgb: np.ndarray, prompt: str, note: str = "") -> np.ndarray | None:
    """Largest SAM 3.1 match for `prompt` in a still image, as a full-size bool mask.

    The SAM decoder is pure Python (about 9 s for a 1024 px redraw) and holds the GIL, so it runs in a
    process pool: parallel redraws (anchor mode) would otherwise wait for each other here."""
    global _parse_pool
    text, _ = client.segment(png_bytes(rgb), prompt, note=note)
    size = (rgb.shape[1], rgb.shape[0])
    pool = _sam_parse_pool()
    try:
        objects = pool.submit(parse_sam_output, text, size, video=False, workers=1).result()
    except BrokenProcessPool:
        # A worker died (10/30 knight run, cause unknown; the same SAM text decodes fine). Start a new pool for
        # the next calls and decode this one here, so one lost worker does not stop the whole action.
        with _parse_pool_lock:
            if _parse_pool is pool:
                _parse_pool = None
        print(f"[warn] SAM decode worker died ({note}); decoding in the main process", flush=True)
        objects = parse_sam_output(text, size, video=False, workers=1)
    obj = largest_object(objects)
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


def tile(images: list[np.ndarray], cols: int, cell: int | tuple[int, int] = 256) -> np.ndarray:
    """Grid of images; cell is a square size or (height, width)."""
    ch, cw = (cell, cell) if isinstance(cell, int) else cell
    rows = (len(images) + cols - 1) // cols
    sheet = np.full((rows * ch, cols * cw, 3), 255, np.uint8)
    for i, img in enumerate(images):
        r, c = divmod(i, cols)
        resized = cv2.resize(img, (cw, ch), interpolation=cv2.INTER_AREA)
        sheet[r * ch : (r + 1) * ch, c * cw : (c + 1) * cw] = resized
    return sheet

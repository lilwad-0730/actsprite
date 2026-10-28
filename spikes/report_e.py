"""Evidence image for spike E (no actor photos: guides, knight frames, pixel sprites only)."""

from __future__ import annotations

import sys

import cv2
import numpy as np
from PIL import Image

from spikes.common import OUT, save_rgb


def row(images: list[np.ndarray], h: int = 256) -> np.ndarray:
    return np.hstack([cv2.resize(i, (h, h), interpolation=cv2.INTER_NEAREST) for i in images])


def main(clip: str) -> None:
    d = OUT / "e_sequence" / clip
    n = len(list((d / "guides").glob("*.png")))
    guides = [cv2.cvtColor(cv2.imread(str(d / "guides" / f"{k}.png")), cv2.COLOR_BGR2RGB) for k in range(n)]
    knights = [cv2.cvtColor(cv2.imread(str(d / "redraw" / f"{k}.png")), cv2.COLOR_BGR2RGB) for k in range(n)]
    strip = np.asarray(Image.open(d / "sprite_strip.png").convert("RGBA"))
    cell = strip.shape[0]
    pixels = []
    for k in range(n):
        rgba = strip[:, k * cell : (k + 1) * cell]
        bg = np.full(rgba.shape[:2] + (3,), 235, np.uint8)
        a = rgba[..., 3:4] / 255.0
        pixels.append((rgba[..., :3] * a + bg * (1 - a)).astype(np.uint8))
    sheet = np.vstack([row(guides), row(knights), row(pixels)])
    save_rgb(OUT.parent / "report_img" / f"e_{clip}.png", sheet)
    print("saved", OUT.parent / "report_img" / f"e_{clip}.png")


if __name__ == "__main__":
    main(sys.argv[1])

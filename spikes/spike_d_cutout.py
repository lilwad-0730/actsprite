"""Spike D: background removal.

Muse Image always returns an opaque image (docs: `background` is always "opaque"),
so we ask for a white background and cut out with the SAM 3.1 mask saved by spike B.
Measures how many near-white pixels survive on the cutout's edge (white fringe),
with the raw mask and with the mask shrunk by 1 px.

Run after spike B: .venv\\Scripts\\python -m spikes.spike_d_cutout   (no API cost)
"""

from __future__ import annotations

import cv2
import numpy as np

from spikes.common import OUT, load_mask, tile, write_json

SRC = OUT / "b_restyle"
FRINGE_MAX = 0.05


def background_whiteness(rgb: np.ndarray, mask: np.ndarray) -> float:
    """Share of background pixels that are near-white."""
    bg = rgb[~mask]
    return float((bg.min(axis=1) > 235).mean()) if len(bg) else 0.0


def fringe_ratio(rgb: np.ndarray, mask: np.ndarray, ring_px: int = 2) -> float:
    """Share of near-white, unsaturated pixels in the inner edge ring of the mask."""
    kernel = np.ones((2 * ring_px + 1, 2 * ring_px + 1), np.uint8)
    ring = mask & ~(cv2.erode(mask.astype(np.uint8), kernel) > 0)
    px = rgb[ring].astype(int)
    if len(px) == 0:
        return 0.0
    whiteish = (px.min(axis=1) > 225) & (px.max(axis=1) - px.min(axis=1) < 20)
    return float(whiteish.mean())


def on_dark(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.full_like(rgb, 40)
    out[mask] = rgb[mask]
    return out


def main() -> None:
    rows, previews = [], []
    for mask_path in sorted(SRC.glob("*/*_mask.png")):
        img_path = mask_path.with_name(mask_path.name.replace("_mask", ""))
        rgb = cv2.cvtColor(cv2.imread(str(img_path)), cv2.COLOR_BGR2RGB)
        mask = load_mask(mask_path)
        shrunk = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        row = {
            "image": f"{img_path.parent.name}/{img_path.name}",
            "background_white_share": round(background_whiteness(rgb, mask), 3),
            "fringe_raw": round(fringe_ratio(rgb, mask), 3),
            "fringe_shrink1": round(fringe_ratio(rgb, shrunk), 3),
        }
        rows.append(row)
        previews += [on_dark(rgb, mask), on_dark(rgb, shrunk)]
        rgba = np.dstack([rgb, mask.astype(np.uint8) * 255])
        out_png = OUT / "d_cutout" / row["image"].replace("/", "_")
        out_png.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_png), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        print(row)
    if not rows:
        raise SystemExit("No masks found. Run spike B first (python -m spikes.spike_b_restyle).")
    cv2.imwrite(str(OUT / "d_cutout" / "overview.png"), cv2.cvtColor(tile(previews, cols=6), cv2.COLOR_RGB2BGR))
    summary = {
        "rows": rows,
        "pass_raw": all(r["fringe_raw"] <= FRINGE_MAX for r in rows),
        "pass_shrink1": all(r["fringe_shrink1"] <= FRINGE_MAX for r in rows),
        "note": "Also check d_cutout/overview.png by eye (left = raw mask, right = shrunk 1 px).",
    }
    write_json(OUT / "d_cutout" / "summary.json", summary)
    print({k: v for k, v in summary.items() if k != "rows"})


if __name__ == "__main__":
    main()

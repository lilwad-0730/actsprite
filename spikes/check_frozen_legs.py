"""Offline check (no API calls): did each redraw attempt move its legs as much as the pose guide did?

The Muse Image redraw sometimes copies the previous frame's legs. The whole-silhouette IoU and the
critic both miss this for thin legs (the dog clip passed 8/8 with 6 frozen frames), so compare the
change of the leg zone between consecutive frames: redraw change / guide change. Writes
spikes/out/e_sequence/<clip>/frozen_check.csv.

  .venv\\Scripts\\python -m spikes.check_frozen_legs pet jump attack
"""

from __future__ import annotations

import csv
import sys

import cv2
import numpy as np

from actsprite.align import fit_to_canvas, mask_bbox
from actsprite.restyle import white_flood_cutout
from actsprite.verify import mask_iou
from spikes.common import OUT

LEG_SHARE = 0.35  # bottom share of the figure height counted as legs
FROZEN_RATIO = 0.25  # redraw leg change below this share of the guide's change = legs copied


def leg_zone(mask: np.ndarray) -> np.ndarray:
    """Height-normalised (200 px), feet on the baseline, bottom LEG_SHARE of the figure only."""
    _, top, _, bottom = mask_bbox(mask)
    m, _, _ = fit_to_canvas(mask, 400, margin=0, scale=200 / (bottom - top))
    _, top, _, bottom = mask_bbox(m)
    m[: bottom - int(LEG_SHARE * (bottom - top))] = False
    return m


def redraw_legs(path: str) -> np.ndarray:
    rgb = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
    return leg_zone(white_flood_cutout(rgb))


def check(clip: str) -> list[dict]:
    base = OUT / "e_sequence" / clip
    guides = [leg_zone(cv2.imread(str(base / "guides" / f"{k}.png"), cv2.IMREAD_GRAYSCALE) < 250) for k in range(8)]
    chosen = [redraw_legs(str(base / "redraw" / f"{k}.png")) for k in range(8)]
    rows = []
    for r in csv.DictReader((base / "scores.csv").open(encoding="utf-8")):
        k, a = int(r["frame"]), int(r["attempt"])
        if k == 0:
            continue  # no previous frame to copy from
        g = 1 - mask_iou(guides[k], guides[k - 1])
        c = 1 - mask_iou(redraw_legs(str(base / "redraw" / f"{k}_a{a}.png")), chosen[k - 1])
        rows.append({"frame": k, "attempt": a, "guide_leg_change": round(g, 3), "redraw_leg_change": round(c, 3),
                     "ratio": round(c / g, 3), "frozen": c / g < FROZEN_RATIO, "passed": r["passed"],
                     "chosen": r.get("chosen", "")})
    with (base / "frozen_check.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return rows


def main() -> None:
    for clip in sys.argv[1:]:
        rows = check(clip)
        frozen = [r for r in rows if r["frozen"]]
        false_pass = [r for r in frozen if r["passed"] == "True"]
        print(f"{clip}: {len(frozen)}/{len(rows)} attempts frozen, {len(false_pass)} of them had passed verification")


if __name__ == "__main__":
    main()

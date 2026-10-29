"""Side by side: the same keyframes redrawn in different ways, e.g. one after another (each frame refers to
the previous one), anchor mode (frames 1-7 refer to frame 0, drawn at the same time) and anchor mode with
frame 0's legs hidden. No API calls.

  .venv\\Scripts\\python -m spikes.compare_anchor attack attack_anchor attack_nolegs

Writes spikes/out/e_sequence/<last run>/vs_<other runs>.png (guides, then one row per run) and .gif, and prints
per run: frames passed, frames passed by today's rules (legs not frozen against the frame before), the
leg motion between neighbouring frames, and how much the drawn size wanders relative to the actor.
"""

from __future__ import annotations

import csv
import json
import sys

import cv2
import numpy as np
from PIL import Image

from actsprite import config
from actsprite.align import mask_bbox
from actsprite.verify import leg_motion
from spikes.common import OUT, save_rgb, tile
from spikes.spike_e_sequence import CHARACTERS, cutout

BG = (235, 235, 235)


def load(name: str) -> dict:
    base = OUT / "e_sequence" / name
    summary = json.loads((base / "summary.json").read_text(encoding="utf-8"))
    ch = CHARACTERS[summary.get("character") or "knight"]
    n = len(summary["keyframes"])
    guides = [cv2.imread(str(base / "guides" / f"{k}.png"), cv2.IMREAD_GRAYSCALE) < 250 for k in range(n)]
    rgbs = [cv2.cvtColor(cv2.imread(str(base / "redraw" / f"{k}.png")), cv2.COLOR_BGR2RGB) for k in range(n)]
    cuts = [cutout(rgb, ch) for rgb in rgbs]
    with (base / "scores.csv").open(encoding="utf-8") as f:
        chosen = [r for r in csv.DictReader(f) if r.get("chosen") == "True"]
    passed = [r["passed"] == "True" for r in sorted(chosen, key=lambda r: int(r["frame"]))]
    adjacent = [leg_motion(guides[k - 1], guides[k], cuts[k - 1], cuts[k]) for k in range(1, n)]
    frozen = [False] + [m is not None and m < config.LEG_MOTION_MIN for m in adjacent]
    heights = []  # drawn figure height / actor height in the guide; the spread shows size wandering
    for g, c in zip(guides, cuts):
        _, gt, _, gb = mask_bbox(g)
        _, ct, _, cb = mask_bbox(c)
        heights.append((cb - ct) / (gb - gt))
    strip = np.asarray(Image.open(base / "sprite_strip.png").convert("RGBA"))
    return {"name": name, "summary": summary, "guides": base / "guides", "rgbs": rgbs, "passed": passed,
            "adjacent": adjacent, "frozen": frozen, "size_spread": max(heights) / min(heights), "strip": strip}


def on_bg(rgba: np.ndarray) -> np.ndarray:
    a = rgba[..., 3:4] / 255.0
    return (rgba[..., :3] * a + np.array(BG) * (1 - a)).astype(np.uint8)


def report(run: dict) -> dict:
    s = run["summary"].get("redraw") or {}
    return {
        "run": run["name"], "anchor": s.get("anchor", "previous"), "hide_anchor_legs": s.get("hide_anchor_legs", False),
        "passed": sum(run["passed"]),
        "passed_with_neighbour_check": sum(p and not f for p, f in zip(run["passed"], run["frozen"])),
        "neighbour_frozen": sum(run["frozen"]),
        "neighbour_leg_motion": [None if m is None else round(m, 2) for m in run["adjacent"]],
        "size_spread": round(run["size_spread"], 3),
        "attempts": s.get("attempts"), "redraw_seconds": s.get("redraw_seconds"),
    }


def main() -> None:
    names = sys.argv[1:]
    if len(names) < 2:
        raise SystemExit("Pass two or more run folders, oldest first, e.g. attack attack_anchor attack_nolegs")
    runs = [load(name) for name in names]
    n = len(runs[0]["rgbs"])
    guides = [cv2.cvtColor(cv2.imread(str(runs[-1]["guides"] / f"{k}.png")), cv2.COLOR_BGR2RGB) for k in range(n)]
    out = OUT / "e_sequence" / names[-1]
    stem = "vs_" + "_".join(names[:-1])
    save_rgb(out / f"{stem}.png", tile(guides + [img for run in runs for img in run["rgbs"]], cols=n))
    cell = config.CELL_SIZE
    frames = [Image.fromarray(np.hstack([on_bg(run["strip"][:, k * cell:(k + 1) * cell]) for run in runs]))
              for k in range(n)]
    frames[0].save(out / f"{stem}.gif", save_all=True, append_images=frames[1:], duration=110, loop=0)
    for run in runs:
        print(json.dumps(report(run), ensure_ascii=False))
    print(f"wrote {out / stem}.png (rows: pose guides / {' / '.join(names)}) and .gif "
          f"(left to right: {', '.join(names)})")


if __name__ == "__main__":
    main()

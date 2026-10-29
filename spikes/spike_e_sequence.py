"""Spike E: real clip -> one action -> 8 aligned keyframes + pose guides -> (optional) character redraw.

Uses the SAM track saved by spike A (spikes/out/a_video/<clip>/track.npz), so no SAM video cost here.
The steps themselves live in the package (actsprite.sequence, actsprite.redraw, actsprite.pack); this script
keeps the experiment outputs under spikes/out/e_sequence/<out>/ that spikes/compare_anchor.py reads.
The product command is `python -m actsprite` (see actsprite/__main__.py).

  # capture + align only (free):
  .venv\\Scripts\\python -m spikes.spike_e_sequence jump --mode once --edges left,right
  # plus Muse Image redraw with the Muse Spark + SAM check loop (~$0.02-0.07 per frame):
  .venv\\Scripts\\python -m spikes.spike_e_sequence jump --mode once --edges left,right --redraw

--mode once : strongest burst of motion (jump, attack); --mode loop : cleanest cycle (idle);
--mode gait : cleanest two-step stride (walk, run), with camera-distance size change removed.
--character knight (biped) | hound (quadruped) | lineman (line art), e.g. the pet clip:
  .venv\\Scripts\\python -m spikes.spike_e_sequence pet --mode gait --character hound --redraw
--anchor first (default): frame 0 first, then frames 1-7 all refer to frame 0 and are drawn at the same time.
  Frame 0 is sent with its legs painted white, so the model cannot copy them (--show-anchor-legs: send it whole).
--anchor previous: each frame refers to the one before, one at a time (the 10/28-10/29 runs).
"""

from __future__ import annotations

import argparse
import csv

import cv2
import numpy as np
from PIL import Image

from actsprite import config
from actsprite.align import fit_to_canvas, shared_scale
from actsprite.capture import read_frames_at
from actsprite.characters import PRESETS, cutout, make_sheet
from actsprite.meta_client import MetaClient
from actsprite.pack import sprite_cells, upscale_nearest
from actsprite.redraw import ANCHORS, redraw_action
from actsprite.restyle import STYLES
from actsprite.sequence import MODES, choose_frames, make_guides
from spikes.common import OUT, save_rgb, tile, write_json

CHARACTERS = PRESETS
SPRITE_PX = config.SPRITE_PIXEL_SIZE  # pixel-art resolution; strips and GIFs show it blown up to CELL_SIZE


def masked_actor(rgb: np.ndarray, mask: np.ndarray, scale: float) -> np.ndarray:
    _, img, _ = fit_to_canvas(mask, config.CELL_SIZE, image=rgb, scale=scale)
    assert img is not None
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", help="folder name under spikes/out/a_video, e.g. jump")
    ap.add_argument("--mode", choices=MODES, default="once",
                    help="once: jump/attack; loop: idle; gait: walk/run (a cycle = two steps)")
    ap.add_argument("--character", choices=sorted(CHARACTERS), default="knight")
    ap.add_argument("--edges", default=",".join(config.FULL_BODY_EDGES),
                    help="frame edges the subject must not touch, e.g. left,right")
    ap.add_argument("--redraw", action="store_true")
    ap.add_argument("--anchor", choices=ANCHORS, default="first",
                    help="first (default): frames 1-7 refer to frame 0 and are drawn at the same time; "
                         "previous: each frame refers to the one before (one at a time)")
    ap.add_argument("--show-anchor-legs", action="store_true",
                    help="with --anchor first: send frame 0 whole. By default its legs are painted white, so "
                         "their positions cannot be copied (the critic always sees the whole frame)")
    ap.add_argument("--out", help="output folder name under spikes/out/e_sequence (default: the clip name)")
    args = ap.parse_args()

    src = OUT / "a_video" / args.clip
    out = OUT / "e_sequence" / (args.out or args.clip)
    z = np.load(src / "track.npz")
    masks, fps = z["masks"], float(z["fps"])
    info, rel = choose_frames(masks, fps, args.mode, tuple(e for e in args.edges.split(",") if e))
    info.update({"clip": args.clip, "mode": args.mode, "character": args.character, "fps": round(fps, 2),
                 "edges": args.edges})
    print(info)

    keys = info["keyframes"]
    lo, hi = info["window"]
    every = list(range(lo, hi, max(1, (hi - lo) // 24)))  # window frames for the by-eye check
    frames = read_frames_at(src / "sam_input.mp4", sorted(set(keys) | set(every)))
    guides = make_guides(frames, masks, keys, rel)
    for k, (g, _) in enumerate(guides):
        save_rgb(out / "guides" / f"{k}.png", g)
    window_scale = shared_scale(list(masks[lo:hi]), config.CELL_SIZE, config.CELL_MARGIN, rel[lo:hi])
    actor = [masked_actor(frames[i], masks[i], window_scale * rel[i]) for i in keys]
    save_rgb(out / "keyframes_actor.png", tile(actor, cols=len(keys)))
    save_rgb(out / "keyframes_guides.png", tile([g for g, _ in guides], cols=len(keys)))
    # Every window frame, aligned, so the cut and the keyframe spacing can be checked by eye.
    save_rgb(out / "window_aligned.png",
             tile([masked_actor(frames[i], masks[i], window_scale * rel[i]) for i in every], cols=12,
                  cell=(192, 192)))

    if args.redraw:
        ch = CHARACTERS[args.character]
        client = MetaClient()
        sheet_png, sheet_rgb, palette = make_sheet(client, ch, note=f"spikeE sheet {ch.name}")
        save_rgb(OUT / "e_sequence" / ("sheet.png" if ch.name == "knight" else f"sheet_{ch.name}.png"), sheet_rgb)
        hide_legs_ = args.anchor == "first" and not args.show_anchor_legs
        rows, rgbs, timing = redraw_action(client, ch, guides, sheet_png, palette, out / "redraw",
                                           f"spikeE {args.out or args.clip}", args.anchor, hide_legs_)
        # Sprite cells: feet on the baseline, same scale for every frame. Pixel styles are pixelated onto the
        # sheet palette and blown up to CELL_SIZE for viewing; hand-drawn styles keep the full-resolution lines.
        pixel = STYLES[ch.style].pixelate
        cells = sprite_cells(rgbs, [cutout(rgb, ch) for rgb in rgbs], palette, SPRITE_PX if pixel else None)
        if pixel:
            cells = [upscale_nearest(c, config.CELL_SIZE // SPRITE_PX) for c in cells]
        Image.fromarray(np.hstack(cells), "RGBA").save(out / "sprite_strip.png")
        bg = [Image.alpha_composite(Image.new("RGBA", (c.shape[1], c.shape[0]), (235, 235, 235, 255)),
                                    Image.fromarray(c, "RGBA")).convert("RGB") for c in cells]
        bg[0].save(out / "preview.gif", save_all=True, append_images=bg[1:], duration=110, loop=0)
        with (out / "scores.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(dict.fromkeys([*rows[0].keys(), "chosen"])))
            w.writeheader()
            w.writerows(rows)
        chosen = [r for r in rows if r.get("chosen")]
        info["redraw"] = {
            "anchor": args.anchor, "hide_anchor_legs": hide_legs_, "frames": len(chosen),
            "passed": sum(r["passed"] for r in chosen), "attempts": len(rows),
            "first_try_pass": sum(r["passed"] for r in rows if r["attempt"] == 0),
            **timing, "spent_total_usd": round(client.cost_log.total(), 4),
        }
        compare = [cv2.resize(g, (256, 256)) for g, _ in guides] + rgbs
        save_rgb(out / "compare.png", tile(compare, cols=len(guides)))
        print(info["redraw"])
    write_json(out / "summary.json", info)


if __name__ == "__main__":
    main()

"""Skeleton experiment, round 2: redraw frame 0 (the anchor) on the skeleton guide too.

Round 1 (spike_skeleton.py) redrew only the bad frames on skeleton guides, still anchored on the old frame 0,
which Muse Image had drawn with a wide stride; all five got worse. Here frame 0 is redrawn first on its skeleton
guide with no reference (as the pipeline draws frame 0), then the bad frames are redrawn anchored on that new frame 0.
Scored the same way as round 1 (local cutout IoU against the gray guide, the same critic thresholds).
No SAM call. Output: out/_eval/skeleton/anchor/<case>/ (no actor pixels in compare.png).

Run: .venv/Scripts/python -B -m spikes.spike_skeleton_anchor
"""

from __future__ import annotations

import csv
import json

import numpy as np

from actsprite import config
from actsprite.characters import cutout
from actsprite.images import decode_rgb, png_bytes, save_rgb, tile
from actsprite.meta_client import MetaClient, print_estimate
from actsprite.redraw import Reference
from actsprite.restyle import hide_legs, redraw_parts
from actsprite.verify import (CRITIC_SCHEMA, FrameScores, critic_parts, largest_component, leg_drift, leg_motion,
                              palette_drift, silhouette_iou)
from spikes.spike_skeleton import FIX, OUT, critic_image, guard_client, prepare, reserve, spent

PREFIX = "spike skeleton v3 anchor"
DEST = OUT / "anchor"


def score(client: MetaClient, plan: dict, k: int, png: bytes, ref: Reference | None, label: str) -> dict:
    """Round 1's scoring: gray guide for the critic, local cutout IoU, the pipeline's thresholds."""
    ch = plan["ch"]
    guide, gm = plan["guides"][k]
    rgb = decode_rgb(png)
    cut = cutout(rgb, ch)
    iou = silhouette_iou(gm, largest_component(cut))
    parts = critic_parts(critic_image(plan["sheet"]), None if ref is None else critic_image(ref.png),
                         png_bytes(guide), critic_image(png), ch.body, anchor=ref is not None)
    verdict, _ = client.critic(parts, CRITIC_SCHEMA, note=f"{PREFIX} {plan['case']} {label} critic f{k}")
    motion = drift = None
    if ref is not None:
        if ref.legs_stay:
            drift = leg_drift(ref.guide_mask, gm, ref.cut, cut)
        else:
            motion = leg_motion(ref.guide_mask, gm, ref.cut, cut)
    s = FrameScores(iou, float(verdict["pose_score"]), float(verdict["identity_score"]),
                    palette_drift(rgb, cut, plan["palette"]), motion, "the first frame", drift)
    return dict(iou=round(iou, 3), pose=s.pose, identity=s.identity, passed=s.passed,
                failures="; ".join(s.failures()), issues=" | ".join(verdict["issues"]))


def main() -> None:
    plans = prepare()
    n_draw = sum(1 + len(p["targets"]) for p in plans)
    estimate = n_draw * config.PRICE_IMAGE + 2 * n_draw * config.CRITIC_MEAN_USD  # new + old frame scored
    print_estimate(f"skeleton anchor round: {n_draw} redraws and {2 * n_draw} critic calls, no SAM", estimate)
    reserve(spent(), estimate * 1.5)
    client = MetaClient()
    guard_client(client)
    before = spent()
    rows = []
    for plan in plans:
        ch, work, case = plan["ch"], plan["work"], plan["case"]
        dest = DEST / case
        skel = plan["dest"] / "guides"
        old_ref = plan["ref"]  # Reference built from the old frame 0
        # 1. Frame 0 on its skeleton guide, no reference: the request the pipeline sends for frame 0, plus FIX.
        png0, _ = client.generate_image(
            redraw_parts(plan["sheet"], (skel / "0.png").read_bytes(), None, ch.style,
                         FIX if plan["quality"][0]["skeleton_used"] else "", ch.body, view=ch.view),
            note=f"{PREFIX} {case} redraw f0")
        save_rgb(dest / "redraw" / "0.png", decode_rgb(png0))
        old0 = (work / "redraw" / "0.png").read_bytes()
        rows.append(dict(case=case, frame=0, **{f"old_{k}": v for k, v in score(client, plan, 0, old0, None, "old").items()},
                         **{f"new_{k}": v for k, v in score(client, plan, 0, png0, None, "new").items()}))
        print(json.dumps(rows[-1]), flush=True)
        # 2. The bad frames, anchored on the NEW frame 0 (same Reference rules as redraw_action).
        rgb0 = decode_rgb(png0)
        cut0 = cutout(rgb0, ch)
        gen_png = png_bytes(hide_legs(rgb0, cut0)) if old_ref.legs_hidden else None
        ref = Reference(png0, cut0, plan["guides"][0][1], anchor=True, gen_png=gen_png, legs_stay=old_ref.legs_stay)
        for k in plan["targets"]:
            png, _ = client.generate_image(
                redraw_parts(plan["sheet"], (skel / f"{k}.png").read_bytes(), ref.gen_png or ref.png, ch.style,
                             FIX if plan["quality"][k]["skeleton_used"] else "", ch.body, anchor=True,
                             legs_hidden=ref.legs_hidden, view=ch.view),
                note=f"{PREFIX} {case} redraw f{k}")
            save_rgb(dest / "redraw" / f"{k}.png", decode_rgb(png))
            old = (work / "redraw" / f"{k}.png").read_bytes()
            rows.append(dict(case=case, frame=k,
                             **{f"old_{n}": v for n, v in score(client, plan, k, old, old_ref, "old").items()},
                             **{f"new_{n}": v for n, v in score(client, plan, k, png, ref, "new").items()}))
            print(json.dumps(rows[-1]), flush=True)
        # Compare: pipeline gray guides / old redraws / skeleton guides / new redraws, frames 0 + targets.
        ks = [0, *plan["targets"]]
        images = ([decode_rgb((work / "guides" / f"{k}.png").read_bytes()) for k in ks]
                  + [decode_rgb((work / "redraw" / f"{k}.png").read_bytes()) for k in ks]
                  + [decode_rgb((skel / f"{k}.png").read_bytes()) for k in ks]
                  + [decode_rgb((dest / "redraw" / f"{k}.png").read_bytes()) for k in ks])
        size = min(i.shape[0] for i in images)
        import cv2
        images = [cv2.resize(i, (size, size), interpolation=cv2.INTER_AREA) for i in images]
        save_rgb(dest / "compare.png", tile(images, cols=len(ks)))
    DEST.mkdir(parents=True, exist_ok=True)
    with (DEST / "scores.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"spent this run ${spent() - before:.4f}; skeleton experiment total ${spent():.4f}")


if __name__ == "__main__":
    main()

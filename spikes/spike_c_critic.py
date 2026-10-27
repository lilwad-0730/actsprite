"""Spike C: can Muse Spark 1.3 tell a good frame from a deliberately broken one?

Uses spike B's pixel-style outputs. Good frame = the 'jump' redraw (previous = 'run').
Three broken variants of that frame:
  hue   - armor/cape colours rotated in code (no API cost)
  edit  - Muse Image edit: helmet removed, cape recoloured
  other - a different character drawn in the same pose
Pass: every broken variant scores lower than the good frame.

Run after spike B: .venv\\Scripts\\python -m spikes.spike_c_critic
Cost: 2 Muse Image + 5 Muse Spark calls ~ $0.06.
"""

from __future__ import annotations

import cv2
import numpy as np

from actsprite import config
from actsprite.meta_client import MetaClient
from actsprite.verify import CRITIC_PROMPT, CRITIC_SCHEMA
from spikes.common import OUT, STYLES, decode_rgb, estimate, load_mask, png_bytes, save_rgb, tile, write_json

import argparse

SRC = OUT / "b_restyle" / "pixel"


def hue_rotate(rgb: np.ndarray, mask: np.ndarray, shift: int = 60) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h = hsv[..., 0].astype(int)
    h[mask] = (h[mask] + shift) % 180
    hsv[..., 0] = h.astype(np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)


def main() -> None:
    global SRC
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="b_restyle", help="spike B output folder to use")
    args = ap.parse_args()
    SRC = OUT / args.src / "pixel"
    for f in ["sheet.png", "run.png", "jump.png", "idle.png", "jump_mask.png"]:
        if not (SRC / f).exists():
            raise SystemExit(f"Missing {SRC / f}. Run spike B first (python -m spikes.spike_b_restyle).")
    client = MetaClient()
    estimate("2 Muse Image + 5 Muse Spark", 2 * config.PRICE_IMAGE + 5 * 0.012)

    sheet = (SRC / "sheet.png").read_bytes()
    prev = (SRC / "run.png").read_bytes()
    good = (SRC / "jump.png").read_bytes()
    good_rgb = decode_rgb(good)
    out = OUT / f"c_critic_{args.src}"

    bad_hue = png_bytes(hue_rotate(good_rgb, load_mask(SRC / "jump_mask.png")))
    bad_edit, _ = client.generate_image(
        [good, "Edit this image: remove the helmet so the head is bare with short brown hair, "
               "and change every blue part to green. Keep the pose, art style and everything else unchanged."],
        note="spikeC bad edit",
    )
    guide = (SRC.parent / "guides" / "jump.png").read_bytes()
    bad_other, _ = client.generate_image(
        [guide, "Draw an original wizard in a purple robe and pointed hat with a wooden staff, in the exact "
                f"pose of this line-art guide. Side view facing right. Style: {STYLES['pixel']}. "
                "Plain solid white background, no shadow, no text."],
        note="spikeC bad other",
    )

    candidates = {
        "good_jump": good,
        "good_idle": (SRC / "idle.png").read_bytes(),
        "bad_hue": bad_hue,
        "bad_edit": bad_edit,
        "bad_other": bad_other,
    }
    results = {}
    for name, cand in candidates.items():
        save_rgb(out / f"{name}.png", decode_rgb(cand))
        reply, res = client.critic([CRITIC_PROMPT, sheet, prev, cand], CRITIC_SCHEMA, note=f"spikeC {name}")
        results[name] = {**reply, "cost_usd": round(res.cost_usd, 5), "latency_s": round(res.latency_s, 1),
                         "usage": res.data.get("usage")}
        print(name, reply)

    good_score = results["good_jump"]["identity_score"]
    groups = {b: results[b]["identity_score"] < good_score for b in ["bad_hue", "bad_edit", "bad_other"]}
    summary = {"results": results, "bad_scored_lower_than_good": groups, "pass": all(groups.values()),
               "spent_total_usd": round(client.cost_log.total(), 4)}
    save_rgb(out / "overview.png", tile([decode_rgb(sheet), decode_rgb(prev)] +
                                        [decode_rgb(c) for c in candidates.values()], cols=7))
    write_json(out / "summary.json", summary)
    print({k: v for k, v in summary.items() if k != "results"})


if __name__ == "__main__":
    main()

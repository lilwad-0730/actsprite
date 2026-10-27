"""Spike B: can Muse Image redraw a pose guide as the SAME character?

For each style: make a character sheet, then redraw 3 pose guides in order
(each anchored to the previous result), and measure pose IoU with SAM 3.1.

Pose sources: `--poses DIR` (frames from your own clips) or, by default,
3 generated photos of a mannequin-like person, so the spike can run before
real footage exists.

Run: .venv\\Scripts\\python -m spikes.spike_b_restyle [--poses DIR]
Cost (default): 11 Muse Image + 11 SAM images ~ $0.14.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np

from actsprite import config
from actsprite.align import fit_to_canvas, pose_guide
from actsprite.meta_client import MetaClient
from actsprite.verify import extract_palette, palette_drift, silhouette_iou
from spikes.common import (
    KNIGHT,
    OUT,
    SHEET_PROMPT,
    STYLES,
    decode_rgb,
    estimate,
    png_bytes,
    redraw_parts,
    sam_mask,
    save_mask,
    save_rgb,
    silhouette_overlay,
    tile,
    write_json,
)

POSE_PROMPTS = {
    "run": "running mid-stride, one knee raised high, arms swinging",
    "jump": "jumping in the air with both knees tucked up",
    "idle": "standing relaxed, arms at the sides",
}
POSE_PHOTO = (
    "Studio photo of an adult in plain gray sweatpants and a plain gray long-sleeve shirt, {pose}. "
    "Full body visible, exact side view facing right, plain light gray background, even lighting."
)


def load_poses(client: MetaClient, poses_dir: Path | None, out: Path) -> dict[str, np.ndarray]:
    if poses_dir is not None:
        files = sorted(p for p in poses_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"})
        return {p.stem: cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB) for p in files}
    poses = {}
    for name, desc in POSE_PROMPTS.items():
        img, _ = client.generate_image([POSE_PHOTO.format(pose=desc)], note=f"spikeB pose {name}")
        poses[name] = decode_rgb(img)
        save_rgb(out / "poses" / f"{name}.png", poses[name])
    return poses


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", type=Path, default=None, help="folder of pose source images")
    ap.add_argument("--styles", default="pixel,handdrawn")
    ap.add_argument("--subject", default="person", help="SAM prompt for the pose source")
    args = ap.parse_args()
    styles = args.styles.split(",")
    out = OUT / "b_restyle"

    client = MetaClient()
    n_pose = 3 if args.poses is None else len(list(args.poses.iterdir()))
    n_img = len(styles) + (3 if args.poses is None else 0) + len(styles) * n_pose
    n_sam = n_pose + len(styles) + len(styles) * n_pose
    estimate(f"{n_img} Muse Image + {n_sam} SAM images",
             n_img * config.PRICE_IMAGE + n_sam * config.PRICE_SAM_IMAGE)

    poses = load_poses(client, args.poses, out)
    guides: dict[str, tuple[bytes, np.ndarray]] = {}
    for name, rgb in poses.items():
        mask = sam_mask(client, rgb, args.subject, note=f"spikeB pose mask {name}")
        if mask is None:
            print(f"! SAM found no '{args.subject}' in pose {name}; skipped")
            continue
        guide, gmask = pose_guide(rgb, mask)
        save_rgb(out / "guides" / f"{name}.png", guide)
        guides[name] = (png_bytes(guide), gmask)

    rows = []
    overview: list[np.ndarray] = []
    for style in styles:
        sheet_png, _ = client.generate_image(
            [SHEET_PROMPT.format(character=KNIGHT, style=STYLES[style])], note=f"spikeB sheet {style}"
        )
        sheet = decode_rgb(sheet_png)
        save_rgb(out / style / "sheet.png", sheet)
        sheet_mask = sam_mask(client, sheet, "knight", note=f"spikeB sheet mask {style}")
        palette = extract_palette(sheet, sheet_mask) if sheet_mask is not None else None
        overview.append(sheet)

        prev: bytes | None = None
        for name, (guide_png, gmask) in guides.items():
            img_png, res = client.generate_image(
                redraw_parts(sheet_png, guide_png, prev, style), note=f"spikeB redraw {style} {name}"
            )
            img = decode_rgb(img_png)
            save_rgb(out / style / f"{name}.png", img)
            mask = sam_mask(client, img, "knight", note=f"spikeB result mask {style} {name}")
            row = {"style": style, "pose": name, "latency_s": round(res.latency_s, 1),
                   "result_size": f"{img.shape[1]}x{img.shape[0]}", "sam_found": mask is not None,
                   "iou": None, "palette_drift": None}
            overview += [decode_rgb(guide_png), img]
            if mask is not None:
                save_mask(out / style / f"{name}_mask.png", mask)
                row["iou"] = round(silhouette_iou(gmask, mask), 3)
                if palette is not None:
                    row["palette_drift"] = round(palette_drift(img, mask, palette), 3)
                a, _, _ = fit_to_canvas(gmask, config.CELL_SIZE, margin=0)
                b, _, _ = fit_to_canvas(mask, config.CELL_SIZE, margin=0)
                overview.append(silhouette_overlay(a, b))
            else:
                overview.append(np.full((256, 256, 3), 255, np.uint8))
            rows.append(row)
            print(row)
            prev = img_png

    with (out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    # Layout per style: sheet, then (guide, result, overlay) per pose.
    save_rgb(out / "overview.png", tile(overview, cols=1 + 3 * len(guides)))
    ious = [r["iou"] for r in rows if r["iou"] is not None]
    summary = {
        "rows": rows,
        "pass_rate_iou_0.70": sum(i >= config.IOU_MIN for i in ious) / max(len(rows), 1),
        "mean_iou": round(float(np.mean(ious)), 3) if ious else None,
        "spent_total_usd": round(client.cost_log.total(), 4),
    }
    write_json(out / "summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()

"""Spike B metrics: which pose-fidelity check can tell the right pose from a wrong one?

For every redraw result and every pose guide (right and wrong), compute:
  silhouette - whole-body SAM silhouette IoU (height-normalised, feet aligned, 6 px tolerance)
  legs       - IoU of SAM 'legs' masks, placed with the whole-body transform (6 px tolerance)
  judge      - Muse Spark 1.3 pose-only score 1-10, costume and proportions ignored
A metric is useful if each result scores highest against its own guide.

Run: .venv\\Scripts\\python -m spikes.spike_b_metrics b_restyle b_restyle_v2
Cost per folder: 6 SAM 'legs' + 3 pose SAM + 18 Muse Spark calls ~ $0.2.
"""

from __future__ import annotations

import argparse

import cv2
import numpy as np

from actsprite.align import mask_bbox
from actsprite.capture import parse_sam_output
from actsprite.meta_client import MetaClient
from actsprite.verify import mask_iou
from spikes.common import OUT, estimate, load_mask, png_bytes, sam_mask, write_json

POSES = ["run", "jump", "idle"]
STYLES = ["pixel", "handdrawn"]
H = 256
TOL = 6

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "pose_score": {"type": "integer", "minimum": 1, "maximum": 10},
        "mismatches": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["pose_score", "mismatches"],
    "additionalProperties": False,
}
JUDGE_PROMPT = (
    "Image 1 is a pose reference drawn as a plain human figure. Image 2 is a 2D game character.\n"
    "Ignore costume, armor, body proportions, art style and colors. Compare ONLY the pose: the angle of "
    "each leg and knee, whether the feet are on the ground or in the air, the arm positions and the torso lean.\n"
    "Score 1-10 how well image 2's pose matches image 1 (10 = same pose, 1 = completely different pose). "
    "List the main mismatches."
)


def rgb(path):
    return cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)


def all_masks(client: MetaClient, image: np.ndarray, prompt: str, note: str) -> np.ndarray:
    text, _ = client.segment(png_bytes(image), prompt, note=note)
    out = np.zeros(image.shape[:2], bool)
    for o in parse_sam_output(text, (image.shape[1], image.shape[0]), video=False):
        out |= o.mask
    return out


def place(body: np.ndarray, part: np.ndarray) -> np.ndarray:
    """Place `part` with the transform that puts `body` feet-down, height H, centroid centred."""
    l, t, r, b = mask_bbox(body)
    s = H / (b - t)
    size = (max(1, round((r - l) * s)), H)
    scaled_body = cv2.resize(body[t:b, l:r].astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0
    scaled_part = cv2.resize(part[t:b, l:r].astype(np.uint8), size, interpolation=cv2.INTER_NEAREST) > 0
    canvas = 3 * H
    dx = round(canvas / 2 - np.nonzero(scaled_body)[1].mean())
    out = np.zeros((H, canvas), bool)
    x0, x1 = max(dx, 0), min(dx + size[0], canvas)
    out[:, x0:x1] = scaled_part[:, x0 - dx : x1 - dx]
    return cv2.dilate(out.astype(np.uint8), np.ones((2 * TOL + 1,) * 2, np.uint8)) > 0


def stats(matrix: dict[str, list[float]]) -> dict:
    diag = [matrix[f"{s}/{p}"][i] for s in STYLES for i, p in enumerate(POSES)]
    off = [v for s in STYLES for i, p in enumerate(POSES) for j, v in enumerate(matrix[f"{s}/{p}"]) if j != i]
    correct = sum(int(np.argmax(matrix[f"{s}/{p}"]) == i) for s in STYLES for i, p in enumerate(POSES))
    return {"own_pose_ranked_first": f"{correct}/{len(STYLES) * len(POSES)}",
            "own_mean": round(float(np.mean(diag)), 3), "own_min": round(float(np.min(diag)), 3),
            "other_mean": round(float(np.mean(off)), 3), "other_max": round(float(np.max(off)), 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--no-judge", action="store_true")
    args = ap.parse_args()
    client = MetaClient()

    poses_dir = OUT / "b_restyle" / "poses"
    pose_body = {p: sam_mask(client, rgb(poses_dir / f"{p}.png"), "person") for p in POSES}
    pose_legs = {p: all_masks(client, rgb(poses_dir / f"{p}.png"), "legs", f"metrics legs pose {p}") for p in POSES}

    report = {}
    for folder in args.folders:
        src = OUT / folder
        estimate(f"{folder}: 6 SAM legs + {0 if args.no_judge else 18} Muse Spark judge", 6 * 0.0025 + 18 * 0.01)
        sil, legs, judge = {}, {}, {}
        for s in STYLES:
            for p in POSES:
                img = rgb(src / s / f"{p}.png")
                body = load_mask(src / s / f"{p}_mask.png")
                rlegs = all_masks(client, img, "legs", f"metrics legs {folder} {s} {p}")
                key = f"{s}/{p}"
                sil[key] = [round(mask_iou(place(pose_body[g], pose_body[g]), place(body, body)), 3) for g in POSES]
                legs[key] = [round(mask_iou(place(pose_body[g], pose_legs[g]), place(body, rlegs)), 3)
                             if rlegs.any() and pose_legs[g].any() else 0.0 for g in POSES]
                if not args.no_judge:
                    row = []
                    for g in POSES:
                        guide = (src / "guides" / f"{g}.png").read_bytes()
                        reply, _ = client.critic([JUDGE_PROMPT, guide, (src / s / f"{p}.png").read_bytes()],
                                                 JUDGE_SCHEMA, schema_name="pose_judge",
                                                 note=f"metrics judge {folder} {key} vs {g}")
                        row.append(reply["pose_score"])
                    judge[key] = row
                print(folder, key, "sil", sil[key], "legs", legs[key], "judge", judge.get(key))
        report[folder] = {"silhouette": {"matrix": sil, **stats(sil)}, "legs": {"matrix": legs, **stats(legs)}}
        if judge:
            report[folder]["judge"] = {"matrix": judge, **stats(judge)}
        for name in report[folder]:
            print(folder, name, {k: v for k, v in report[folder][name].items() if k != "matrix"})
    report["spent_total_usd"] = round(client.cost_log.total(), 4)
    write_json(OUT / "b_metrics.json", report)


if __name__ == "__main__":
    main()

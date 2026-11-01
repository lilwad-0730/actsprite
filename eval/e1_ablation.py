"""E1: does the anchor and the verification loop help? Three ways to draw the same keyframes:

  A  no anchor, one try: each frame drawn from the character sheet and its pose guide only (new calls here)
  B  anchor, one try:    the first attempt of each frame in the shipped run (frames 1+ refer to frame 0)
  C  anchor + checks:    the frame the shipped run kept after up to 2 checked redraws

The pose guides are the shipped run's saved guides (rebuilding them from the video is not exact: a re-encoded
clip gives SAM 3.1 a slightly different track). For a fair comparison all three are scored the same way here:
silhouette IoU between the guide and the drawn character's local cutout, the Muse Spark pose and identity scores
(new calls for A; B and C from the runs' scores.csv), palette drift, and "passed" = IoU, pose, identity and
palette within the pipeline's thresholds. The leg checks are left out (A has no reference frame).
The pipeline's own verdicts for B and C (with SAM IoU and leg checks) are kept in the CSV as well.

  .venv\\Scripts\\python -m eval.e1_ablation

Writes out/_eval/e1/ (A's drawings), eval/results/e1_frames.csv, e1_summary.csv and e1_chart.png.
Small development check, not a formal accuracy study.
"""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from actsprite import config
from actsprite.characters import PRESETS, cutout
from actsprite.images import decode_rgb, png_bytes, save_rgb
from actsprite.meta_client import ContentRefused, MetaClient, print_estimate
from actsprite.restyle import redraw_parts
from actsprite.verify import (CRITIC_SCHEMA, critic_parts, extract_palette, largest_component, palette_drift,
                              silhouette_iou)

ROOT = config.ROOT
WORK = ROOT / "out" / "_eval" / "e1"
RESULTS = ROOT / "eval" / "results"
# (output folder, action): every shipped action except the knight attack, whose frames were edited by hand.
CASES = [("knight", "idle"), ("knight", "run"), ("knight", "jump"),
         ("lineman", "run"), ("lineman", "attack"), ("hound", "walk")]
CONDITIONS = ("A no anchor, one try", "B anchor, one try", "C anchor + checks")
METRICS = ("iou", "pose", "identity", "drift")


def guide(work: Path, k: int) -> tuple[bytes, np.ndarray, np.ndarray]:
    png = (work / "guides" / f"{k}.png").read_bytes()
    rgb = decode_rgb(png)
    return png, rgb, rgb.min(axis=2) < 245  # silhouette fill and outline: everything that is not white paper


def local_scores(ch, rgb: np.ndarray, gmask: np.ndarray, palette: np.ndarray) -> tuple[float, float]:
    cut = cutout(rgb, ch)
    return silhouette_iou(gmask, largest_component(cut)), palette_drift(rgb, cut, palette)


def passed(iou: float, pose: float, identity: float, drift: float) -> bool:
    return (iou >= config.IOU_MIN and pose >= config.POSE_MIN and identity >= config.IDENTITY_MIN
            and drift <= config.PALETTE_DRIFT_MAX)


def main() -> None:
    jobs = []
    for folder, action in CASES:
        work = ROOT / "out" / folder / "work" / action
        with (work / "scores.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        n = 1 + max(int(r["frame"]) for r in rows)
        jobs += [(folder, action, work, rows, k) for k in range(n)]
    print_estimate(f"E1 no-anchor redraws: {len(jobs)} frames, one Muse Image try and one critic each",
                   len(jobs) * (config.PRICE_IMAGE + config.CRITIC_MEAN_USD))
    client = MetaClient()
    sheets = {}

    def sheet(folder: str, work: Path):
        if folder not in sheets:
            png = (work.parent / "sheet.png").read_bytes()
            rgb = decode_rgb(png)
            sheets[folder] = (png, extract_palette(rgb, cutout(rgb, PRESETS[folder])))
        return sheets[folder]

    for folder, action, work, *_ in jobs:
        sheet(folder, work)

    def one(job) -> list[dict]:
        folder, action, work, rows, k = job
        ch = PRESETS[folder]
        sheet_png, palette = sheet(folder, work)
        gpng, _, gmask = guide(work, k)
        out = []
        # A: the request the pipeline sends for a frame with no reference (as for frame 0), one try.
        try:
            png, _ = client.generate_image(redraw_parts(sheet_png, gpng, None, ch.style, "", ch.body, view=ch.view),
                                           note=f"eval e1 noanchor {folder} {action} f{k}")
        except ContentRefused:
            png = None
        if png is not None:
            save_rgb(WORK / f"{folder}_{action}" / f"{k}.png", decode_rgb(png))
            verdict, _ = client.critic(critic_parts(sheet_png, None, gpng, png, ch.body),
                                       CRITIC_SCHEMA, note=f"eval e1 noanchor critic {folder} {action} f{k}")
            iou, drift = local_scores(ch, decode_rgb(png), gmask, palette)
            pose, ident = float(verdict["pose_score"]), float(verdict["identity_score"])
            out.append({"condition": CONDITIONS[0], "iou": iou, "pose": pose, "identity": ident, "drift": drift,
                        "pipeline_passed": ""})
        # B and C: the shipped run's first attempt and kept frame, re-scored locally the same way.
        first = next(r for r in rows if int(r["frame"]) == k and r["attempt"] == "0")
        kept = next(r for r in rows if int(r["frame"]) == k and r.get("chosen") == "True")
        for cond, r in ((CONDITIONS[1], first), (CONDITIONS[2], kept)):
            rgb = decode_rgb((work / "redraw" / f"{k}_a{r['attempt']}.png").read_bytes())
            iou, drift = local_scores(ch, rgb, gmask, palette)
            out.append({"condition": cond, "iou": iou, "pose": float(r["pose"]), "identity": float(r["identity"]),
                        "drift": drift, "pipeline_passed": r["passed"] == "True"})
        for r in out:
            r.update({"case": f"{folder} {action}", "frame": k, "iou": round(r["iou"], 3),
                      "drift": round(r["drift"], 3), "passed": passed(r["iou"], r["pose"], r["identity"], r["drift"])})
        return out

    with ThreadPoolExecutor(max_workers=config.REDRAW_WORKERS) as pool:
        frames = [r for rs in pool.map(one, jobs) for r in rs]
    cols = ["case", "frame", "condition", *METRICS, "passed", "pipeline_passed"]
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / "e1_frames.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows({c: r[c] for c in cols} for r in frames)
    # Only frames drawn in all three conditions (a refused A drawing drops that frame everywhere).
    complete = {(r["case"], r["frame"]) for r in frames if r["condition"] == CONDITIONS[0]}
    frames = [r for r in frames if (r["case"], r["frame"]) in complete]
    summary = []
    for case in [*[f"{a} {b}" for a, b in CASES], "all"]:
        for cond in CONDITIONS:
            rs = [r for r in frames if r["condition"] == cond and case in ("all", r["case"])]
            summary.append({"case": case, "condition": cond, "frames": len(rs),
                            **{f"mean_{m}": round(float(np.mean([r[m] for r in rs])), 3) for m in METRICS},
                            "passed_share": round(sum(r["passed"] for r in rs) / len(rs), 3)})
    with (RESULTS / "e1_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    chart([s for s in summary if s["case"] == "all"])
    for s in summary:
        print(s)
    print(f"total logged spend now ${client.cost_log.total():.2f}")


def chart(rows: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = ["Silhouette IoU", "Pose (/10)", "Identity (/10)", "Frames passing"]
    keys = ["mean_iou", "mean_pose", "mean_identity", "passed_share"]
    scale = [1, 10, 10, 1]
    fig, ax = plt.subplots(figsize=(8, 4))
    width = 0.26
    colors = ["#b0b0b0", "#6fa8dc", "#2e7d32"]
    for i, r in enumerate(rows):
        vals = [r[k] / s for k, s in zip(keys, scale)]
        bars = ax.bar(np.arange(4) + (i - 1) * width, vals, width, label=r["condition"], color=colors[i])
        for b, v, k, s in zip(bars, vals, keys, scale):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{r[k]:.2f}" if s == 1 else f"{r[k]:.1f}",
                    ha="center", fontsize=8)
    ax.set_xticks(np.arange(4), labels)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("share of the maximum")
    ax.set_title(f"E1: the same {rows[0]['frames']} keyframes (6 actions) drawn three ways")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(RESULTS / "e1_chart.png", dpi=150)


if __name__ == "__main__":
    main()

"""E6: does the Muse Spark 1.3 critic catch frames that are off-model? Defect injection.

20 frames that passed every check in the shipped runs are copied once more by Muse Image with one deliberate
defect each (4 kinds x 5 frames: recolour, a missing part, wrong proportions, an extra item). Each normal frame
and its defective copy are judged by the same critic request the pipeline sends (character sheet, the action's
frame 0, the pose guide, the candidate). A frame is "rejected by the critic" when its pose or identity score is
below the pipeline's threshold (config.POSE_MIN, config.IDENTITY_MIN). The local palette-drift check is
reported too. No SAM call.

  .venv\\Scripts\\python -m eval.e6_defects

Writes eval/results/e6_frames.csv, e6_summary.md and e6_examples.png (normal above defective, a few pairs).
Small development check, not a formal accuracy study.
"""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from actsprite import config
from actsprite.characters import PRESETS, cutout
from actsprite.images import decode_rgb, png_bytes, save_rgb, tile
from actsprite.meta_client import ContentRefused, MetaClient, print_estimate
from actsprite.verify import CRITIC_SCHEMA, critic_parts, extract_palette, palette_drift

ROOT = config.ROOT
RESULTS = ROOT / "eval" / "results"
WORK = ROOT / "out" / "_eval" / "e6"
# (output folder, action, how many passed frames to take)
PICKS = [("knight", "run", 3), ("knight", "idle", 2), ("knight", "jump", 3), ("lineman", "run", 8), ("hound", "walk", 4)]
KINDS = ["recolour", "missing part", "proportions", "extra item"]
DEFECTS = {
    "knight": {"recolour": "make the armour gold instead of silver and the blue cloth bright red",
               "missing part": "remove the sword and its scabbard from the hip completely",
               "proportions": "make the head and helmet about twice as large as now",
               "extra item": "add a long flowing purple cape from the shoulders"},
    "lineman": {"recolour": "fill the whole bodysuit with solid bright red colour",
                "missing part": "remove the seam lines and draw the body as one plain outline with no inner lines",
                "proportions": "make the legs half as long and the torso longer",
                "extra item": "add a wide-brimmed hat and a backpack"},
    "hound": {"recolour": "make the fur bright blue instead of sandy gold",
              "missing part": "remove the silver chest plate and the red collar completely",
              "proportions": "make the head twice as large and the legs very short",
              "extra item": "add a leather saddle with bags on its back"},
}
EDIT = ("Edit this game character frame. Keep everything else exactly the same: the same pose, framing, size, art "
        "style, line work and plain white background. Only change this: {defect}.")


def picks() -> list[dict]:
    out = []
    for folder, action, n in PICKS:
        work = ROOT / "out" / folder / "work" / action
        with (work / "scores.csv").open(encoding="utf-8") as f:
            ok = sorted(int(r["frame"]) for r in csv.DictReader(f)
                        if r.get("chosen") == "True" and r["passed"] == "True" and r["frame"] != "0")
        step = max(1, len(ok) // n)
        out += [{"folder": folder, "action": action, "frame": k, "work": work} for k in ok[::step][:n]]
    for i, p in enumerate(out):
        p["kind"] = KINDS[i % len(KINDS)]
    return out


def judge(client: MetaClient, p: dict, png: bytes, label: str) -> dict:
    ch = PRESETS[p["folder"]]
    work = p["work"]
    sheet = (work.parent / "sheet.png").read_bytes()
    verdict, _ = client.critic(
        critic_parts(sheet, (work / "redraw" / "0.png").read_bytes(),
                     (work / "guides" / f"{p['frame']}.png").read_bytes(), png, ch.body, anchor=True),
        CRITIC_SCHEMA, note=f"eval e6 {p['folder']} {p['action']} f{p['frame']} {label}")
    sheet_rgb = decode_rgb(sheet)
    rgb = decode_rgb(png)
    drift = palette_drift(rgb, cutout(rgb, ch), extract_palette(sheet_rgb, cutout(sheet_rgb, ch)))
    pose, ident = float(verdict["pose_score"]), float(verdict["identity_score"])
    return {"pose": pose, "identity": ident, "critic_rejects": pose < config.POSE_MIN or ident < config.IDENTITY_MIN,
            "palette_drift": round(float(drift), 3), "palette_rejects": drift > config.PALETTE_DRIFT_MAX,
            "issues": " | ".join(verdict["issues"])}


def main() -> None:
    items = picks()
    print_estimate(f"E6: {len(items)} Muse Image edits and {2 * len(items)} critic calls",
                   len(items) * (config.PRICE_IMAGE + 2 * config.CRITIC_MEAN_USD))
    client = MetaClient()

    def one(p: dict) -> list[dict]:
        normal = (p["work"] / "redraw" / f"{p['frame']}.png").read_bytes()
        defect = DEFECTS[p["folder"]][p["kind"]]
        base = {"character": p["folder"], "action": p["action"], "frame": p["frame"], "defect_kind": p["kind"]}
        rows = [{**base, "image": "normal", "defect": "", **judge(client, p, normal, "normal")}]
        try:
            bad, _ = client.generate_image([normal, EDIT.format(defect=defect)],
                                           note=f"eval e6 {p['folder']} {p['action']} f{p['frame']} {p['kind']}")
        except ContentRefused:
            return rows + [{**base, "image": "defect", "defect": defect, "issues": "edit refused by content filter"}]
        path = WORK / f"{p['folder']}_{p['action']}_f{p['frame']}_{p['kind'].replace(' ', '_')}.png"
        save_rgb(path, decode_rgb(bad))
        save_rgb(path.with_name(path.stem + "_normal.png"), decode_rgb(normal))
        return rows + [{**base, "image": "defect", "defect": defect, "file": str(path.relative_to(ROOT)),
                        **judge(client, p, bad, "defect")}]

    with ThreadPoolExecutor(max_workers=config.REDRAW_WORKERS) as pool:
        rows = [r for rs in pool.map(one, items) for r in rs]
    RESULTS.mkdir(parents=True, exist_ok=True)
    with (RESULTS / "e6_frames.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)
    summary(rows)
    examples(rows)
    print(f"total logged spend now ${client.cost_log.total():.2f}")


def summary(rows: list[dict]) -> None:
    normal = [r for r in rows if r["image"] == "normal"]
    bad = [r for r in rows if r["image"] == "defect" and "pose" in r]
    caught = sum(r["critic_rejects"] for r in bad)
    either = sum(r["critic_rejects"] or r["palette_rejects"] for r in bad)
    false = sum(r["critic_rejects"] for r in normal)
    lines = ["# E6: defect injection", "",
             f"Defective frames rejected by the Muse Spark critic: **{caught}/{len(bad)}**; by the critic or the "
             f"palette check: {either}/{len(bad)}.",
             f"Normal frames (all passed in the shipped runs) rejected by the critic on a second look: "
             f"**{false}/{len(normal)}**.", "", "| Kind | Caught by critic | Caught by critic or palette |",
             "| --- | --- | --- |"]
    for kind in KINDS:
        k = [r for r in bad if r["defect_kind"] == kind]
        lines.append(f"| {kind} | {sum(r['critic_rejects'] for r in k)}/{len(k)} | "
                     f"{sum(r['critic_rejects'] or r['palette_rejects'] for r in k)}/{len(k)} |")
    refused = [r for r in rows if r["image"] == "defect" and "pose" not in r]
    if refused:
        lines += ["", f"{len(refused)} defect edit(s) were refused by the content filter and are left out."]
    lines += ["", "Rejected = pose or identity score below 7, the pipeline's threshold. Defects were made by Muse "
                  "Image, which did not always apply them fully; see e6_examples.png and the files listed in "
                  "e6_frames.csv."]
    (RESULTS / "e6_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def examples(rows: list[dict]) -> None:
    import cv2

    pairs = [r for r in rows if r.get("file")][:8]
    top, bottom = [], []
    for r in pairs:
        bad = decode_rgb((ROOT / r["file"]).read_bytes())
        normal = decode_rgb(Path(ROOT / r["file"]).with_name(Path(r["file"]).stem + "_normal.png").read_bytes())
        top.append(cv2.resize(normal, (256, 256), interpolation=cv2.INTER_AREA))
        bottom.append(cv2.resize(bad, (256, 256), interpolation=cv2.INTER_AREA))
    if pairs:
        save_rgb(RESULTS / "e6_examples.png", tile(top + bottom, cols=len(pairs)))


if __name__ == "__main__":
    main()

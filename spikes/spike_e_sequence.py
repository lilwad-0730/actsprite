"""Spike E: real clip -> one action -> 8 aligned keyframes + pose guides -> (optional) knight redraw.

Uses the SAM track saved by spike A (spikes/out/a_video/<clip>/track.npz), so no SAM video cost here.

  # capture + align only (free):
  .venv\\Scripts\\python -m spikes.spike_e_sequence jump --mode once --edges left,right
  # plus Muse Image redraw with the Muse Spark + SAM check loop (~$0.02-0.07 per frame):
  .venv\\Scripts\\python -m spikes.spike_e_sequence jump --mode once --edges left,right --redraw

--mode once : strongest burst of motion (jump, attack); --mode loop : first full cycle (walk, idle).
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from actsprite import config
from actsprite.align import align_sequence, fit_to_canvas, pose_guide, shared_scale
from actsprite.capture import SamObject, action_window, best_cycle, full_body_range, read_frames, select_keyframes
from actsprite.meta_client import MetaClient
from actsprite.pack import pixelate, upscale_nearest
from actsprite.restyle import redraw_parts, sheet_prompt, white_flood_cutout
from actsprite.verify import (
    CRITIC_SCHEMA,
    FrameScores,
    critic_parts,
    extract_palette,
    largest_component,
    palette_drift,
    silhouette_iou,
)
from spikes.common import OUT, decode_rgb, estimate, png_bytes, sam_mask, save_rgb, tile, write_json

KNIGHT = ("an original young knight: fitted silver plate armor with blue cloth trim, red plume on the helmet, "
          "short sword in a scabbard on the hip")
SPRITE_PX = 64  # pixel-art cell size after pixelate (CELL_SIZE / 4)


def masked_actor(rgb: np.ndarray, mask: np.ndarray, scale: float) -> np.ndarray:
    _, img, _ = fit_to_canvas(mask, config.CELL_SIZE, image=rgb, scale=scale)
    assert img is not None
    return img


def choose_frames(masks: np.ndarray, fps: float, mode: str, edges: tuple[str, ...]) -> dict:
    n = len(masks)
    track = {i: SamObject(i, "0", (0, 0, 1, 1), m) for i, m in enumerate(masks) if m.any()}
    rng = full_body_range(track, n, edges=edges)
    if rng is None:
        raise SystemExit("No stretch with the whole body in frame; try --edges left,right")
    lo, hi = rng
    aligned, _, _ = align_sequence(list(masks[lo:hi]))
    if mode == "once":
        s, e = action_window(aligned, fps)
        picks = select_keyframes(aligned[s:e], config.FRAMES_PER_ACTION, loop=False)
        cycle = None
    else:
        found = best_cycle(aligned, fps)
        if found is None:
            raise SystemExit("No loop found in this clip.")
        s, cycle = found
        e = s + cycle
        picks = select_keyframes(aligned[s:e], config.FRAMES_PER_ACTION, loop=True)
    keys = [lo + s + p for p in picks]
    return {"full_body": [lo, hi], "window": [lo + s, lo + e], "cycle_frames": cycle, "keyframes": keys,
            "keyframe_seconds": [round(k / fps, 3) for k in keys]}


def make_sheet(client: MetaClient, out: Path) -> tuple[bytes, np.ndarray, np.ndarray]:
    estimate("character sheet (Muse Image)", config.PRICE_IMAGE)
    png, _ = client.generate_image([sheet_prompt(KNIGHT, "pixel")], note="spikeE sheet")
    rgb = decode_rgb(png)
    save_rgb(out / "sheet.png", rgb)
    palette = extract_palette(rgb, white_flood_cutout(rgb))
    return png, rgb, palette


def redraw(client: MetaClient, out: Path, guides: list[tuple[np.ndarray, np.ndarray]], tag: str) -> list[dict]:
    sheet_png, _, palette = make_sheet(client, OUT / "e_sequence")
    per_try = config.PRICE_IMAGE + config.PRICE_SAM_IMAGE + 0.011
    estimate(f"redraw {len(guides)} frames, up to {config.MAX_REGENERATIONS + 1} tries each",
             len(guides) * per_try * (config.MAX_REGENERATIONS + 1))
    rows: list[dict] = []
    prev_png: bytes | None = None
    for k, (guide_rgb, guide_mask) in enumerate(guides):
        guide_png = png_bytes(guide_rgb)
        fix = ""
        best: tuple[float, bytes, np.ndarray, FrameScores] | None = None
        for attempt in range(config.MAX_REGENERATIONS + 1):
            png, _ = client.generate_image(redraw_parts(sheet_png, guide_png, prev_png, "pixel", fix),
                                           note=f"spikeE {tag} f{k} a{attempt}")
            rgb = decode_rgb(png)
            save_rgb(out / "redraw" / f"{k}_a{attempt}.png", rgb)
            cut = white_flood_cutout(rgb)
            cand = sam_mask(client, rgb, "knight", note=f"spikeE {tag} mask f{k} a{attempt}")
            if cand is None or not cand.any():
                cand = cut  # SAM sometimes returns nothing for a drawn figure (attack f3 a0)
            iou = silhouette_iou(guide_mask, largest_component(cand))
            verdict, _ = client.critic(critic_parts(sheet_png, prev_png, guide_png, png), CRITIC_SCHEMA,
                                       note=f"spikeE {tag} critic f{k} a{attempt}")
            scores = FrameScores(iou, float(verdict["pose_score"]), float(verdict["identity_score"]),
                                 palette_drift(rgb, cut, palette))
            rows.append({"frame": k, "attempt": attempt, "iou": round(iou, 3), "pose": scores.pose,
                         "identity": scores.identity, "drift": round(scores.drift, 3),
                         "combined": round(scores.combined, 3), "passed": scores.passed,
                         "failures": "; ".join(scores.failures()), "issues": " | ".join(verdict["issues"]),
                         "fix": verdict["fix_instruction"]})
            print(rows[-1])
            if best is None or scores.combined > best[0]:
                best = (scores.combined, png, rgb, scores)
                best_row = rows[-1]
            if scores.passed:
                break
            fix = " ".join(filter(None, [verdict["fix_instruction"], *scores.failures()]))
        assert best is not None
        _, png, rgb, scores = best
        best_row["chosen"] = True
        save_rgb(out / "redraw" / f"{k}.png", rgb)
        prev_png = png
    # Sprite cells: feet on the baseline, same scale for every frame (the canvas ratio).
    cells, pixels = [], []
    for k in range(len(guides)):
        rgb = decode_rgb((out / "redraw" / f"{k}.png").read_bytes())
        cut = white_flood_cutout(rgb)
        m, img, _ = fit_to_canvas(cut, config.CELL_SIZE, image=rgb, scale=config.CELL_SIZE / rgb.shape[1])
        assert img is not None
        rgba = np.dstack([img, m.astype(np.uint8) * 255])
        cells.append(rgba)
        pixels.append(pixelate(rgba, SPRITE_PX, palette))
    strip = np.hstack([upscale_nearest(p, 4) for p in pixels])
    Image.fromarray(strip, "RGBA").save(out / "sprite_strip.png")
    frames = [Image.fromarray(upscale_nearest(p, 4), "RGBA").convert("RGBA") for p in pixels]
    bg = [Image.alpha_composite(Image.new("RGBA", f.size, (235, 235, 235, 255)), f).convert("RGB") for f in frames]
    bg[0].save(out / "preview.gif", save_all=True, append_images=bg[1:], duration=110, loop=0)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", help="folder name under spikes/out/a_video, e.g. jump")
    ap.add_argument("--mode", choices=["once", "loop"], default="once")
    ap.add_argument("--edges", default=",".join(config.FULL_BODY_EDGES),
                    help="frame edges the subject must not touch, e.g. left,right")
    ap.add_argument("--redraw", action="store_true")
    args = ap.parse_args()

    src = OUT / "a_video" / args.clip
    out = OUT / "e_sequence" / args.clip
    z = np.load(src / "track.npz")
    masks, fps = z["masks"], float(z["fps"])
    info = choose_frames(masks, fps, args.mode, tuple(e for e in args.edges.split(",") if e))
    info.update({"clip": args.clip, "mode": args.mode, "fps": round(fps, 2), "edges": args.edges})
    print(info)

    frames = read_frames(src / "sam_input.mp4")
    keys = info["keyframes"]
    lo, hi = info["window"]
    window_scale = shared_scale(list(masks[lo:hi]), config.CELL_SIZE, config.CELL_MARGIN)
    guide_scale = shared_scale([masks[i] for i in keys], config.GUIDE_SIZE, config.CELL_MARGIN * 2)
    guides = [pose_guide(frames[i], masks[i], fill=True, head_fraction=config.GUIDE_HEAD_FRACTION,
                         scale=guide_scale) for i in keys]
    for k, (g, _) in enumerate(guides):
        save_rgb(out / "guides" / f"{k}.png", g)
    actor = [masked_actor(frames[i], masks[i], window_scale) for i in keys]
    save_rgb(out / "keyframes_actor.png", tile(actor, cols=len(keys)))
    save_rgb(out / "keyframes_guides.png", tile([g for g, _ in guides], cols=len(keys)))
    # Every window frame, aligned, so the cut and the keyframe spacing can be checked by eye.
    every = list(range(lo, hi, max(1, (hi - lo) // 24)))
    save_rgb(out / "window_aligned.png",
             tile([masked_actor(frames[i], masks[i], window_scale) for i in every], cols=12, cell=(192, 192)))

    if args.redraw:
        client = MetaClient()
        rows = redraw(client, out, guides, args.clip)
        with (out / "scores.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) + ["chosen"])
            w.writeheader()
            w.writerows(rows)
        chosen = [r for r in rows if r.get("chosen")]
        info["redraw"] = {
            "frames": len(chosen), "passed": sum(r["passed"] for r in chosen),
            "attempts": len(rows), "first_try_pass": sum(r["passed"] for r in rows if r["attempt"] == 0),
            "spent_total_usd": round(client.cost_log.total(), 4),
        }
        compare = [cv2.resize(g, (256, 256)) for g, _ in guides] + [
            decode_rgb((out / "redraw" / f"{k}.png").read_bytes()) for k in range(len(guides))]
        save_rgb(out / "compare.png", tile(compare, cols=len(guides)))
        print(info["redraw"])
    write_json(out / "summary.json", info)


if __name__ == "__main__":
    main()

"""Spike E: real clip -> one action -> 8 aligned keyframes + pose guides -> (optional) knight redraw.

Uses the SAM track saved by spike A (spikes/out/a_video/<clip>/track.npz), so no SAM video cost here.

  # capture + align only (free):
  .venv\\Scripts\\python -m spikes.spike_e_sequence jump --mode once --edges left,right
  # plus Muse Image redraw with the Muse Spark + SAM check loop (~$0.02-0.07 per frame):
  .venv\\Scripts\\python -m spikes.spike_e_sequence jump --mode once --edges left,right --redraw

--mode once : strongest burst of motion (jump, attack); --mode loop : cleanest cycle (idle);
--mode gait : cleanest two-step stride (walk, run), with camera-distance size change removed.
--character knight (biped) | hound (quadruped), e.g. the pet clip:
  .venv\\Scripts\\python -m spikes.spike_e_sequence pet --mode gait --character hound --redraw
--anchor first (default): frame 0 first, then frames 1-7 all refer to frame 0 and are drawn at the same time.
  Frame 0 is sent with its legs painted white, so the model cannot copy them (--show-anchor-legs: send it whole).
--anchor previous: each frame refers to the one before, one at a time (the 10/28-10/29 runs).
"""

from __future__ import annotations

import argparse
import csv
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from actsprite import config
from actsprite.align import align_sequence, fit_to_canvas, pose_guide, shared_scale, size_drift
from actsprite.capture import SamObject, action_window, best_cycle, full_body_range, read_frames, select_keyframes
from actsprite.meta_client import MetaClient
from actsprite.pack import pixelate, upscale_nearest
from actsprite.restyle import STYLES, hide_legs, redraw_parts, sheet_prompt, white_flood_cutout
from actsprite.verify import (
    CRITIC_SCHEMA,
    FrameScores,
    critic_parts,
    extract_palette,
    largest_component,
    leg_motion,
    palette_drift,
    silhouette_iou,
)
from spikes.common import OUT, decode_rgb, estimate, png_bytes, sam_mask, save_rgb, tile, write_json

@dataclass(frozen=True)
class Character:
    description: str
    body: str  # key of restyle.BODIES
    sam_prompt: str  # noun SAM uses to find the drawn character
    style: str = "pixel"  # key of restyle.STYLES
    sheet_path: str | None = None  # user's own design used as the reference sheet (no sheet generation)
    sheet_faces_left: bool = False  # mirror the user's sheet: every frame is drawn facing right


CHARACTERS = {
    "knight": Character("an original young knight: fitted silver plate armor with blue cloth trim, red plume on the "
                        "helmet, short sword in a scabbard on the hip", "biped", "knight"),
    "hound": Character("an original hound companion for a knight: short sandy-gold fur, cream muzzle and belly, "
                       "dark brown ear tips, a small silver chest plate with blue cloth trim, red leather collar",
                       "quadruped", "dog"),
    # User's drawing (10/29): plain bald young man in a fitted suit with seam lines, sketchy pencil lines, no fill.
    "lineman": Character("a plain young man drawn as a pencil line sketch: bald head, slim build, fitted bodysuit "
                         "with seam lines", "biped", "person", style="lineart",
                         sheet_path=str(config.ROOT / "man in line.jpg"), sheet_faces_left=True),
}
SPRITE_PX = 64  # pixel-art cell size after pixelate (CELL_SIZE / 4)


def cutout(rgb: np.ndarray, ch: Character) -> np.ndarray:
    return white_flood_cutout(rgb, line_gaps=STYLES[ch.style].line_gaps)


def user_sheet(ch: Character) -> np.ndarray:
    """The user's design on a square white canvas, facing right, feet near the bottom (like a generated sheet)."""
    assert ch.sheet_path is not None
    bgr = cv2.imread(ch.sheet_path)
    if bgr is None:
        raise SystemExit(f"Character sheet not found: {ch.sheet_path}")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    if ch.sheet_faces_left:
        rgb = rgb[:, ::-1].copy()
    h, w = rgb.shape[:2]
    side = max(h, w)
    canvas = np.full((side, side, 3), 255, np.uint8)
    canvas[side - h :, (side - w) // 2 : (side - w) // 2 + w] = rgb
    return canvas


def masked_actor(rgb: np.ndarray, mask: np.ndarray, scale: float) -> np.ndarray:
    _, img, _ = fit_to_canvas(mask, config.CELL_SIZE, image=rgb, scale=scale)
    assert img is not None
    return img


def choose_frames(masks: np.ndarray, fps: float, mode: str, edges: tuple[str, ...]) -> tuple[dict, np.ndarray]:
    """Keyframes plus a per-frame scale factor (1 unless walking/running, where it cancels the
    subject moving toward or away from the camera; idle and one-shot actions stay in place)."""
    n = len(masks)
    track = {i: SamObject(i, "0", (0, 0, 1, 1), m) for i, m in enumerate(masks) if m.any()}
    rng = full_body_range(track, n, edges=edges)
    if rng is None:
        raise SystemExit("No stretch with the whole body in frame; try --edges left,right")
    lo, hi = rng
    rel = np.ones(n)
    if mode == "gait":
        rel[lo:hi] = size_drift(list(masks[lo:hi]), fps)
    aligned, _, _ = align_sequence(list(masks[lo:hi]), rel=rel[lo:hi])
    if mode == "once":
        s, e = action_window(aligned, fps)
        picks = select_keyframes(aligned[s:e], config.FRAMES_PER_ACTION, loop=False)
        cycle = None
    else:
        found = best_cycle(aligned, fps, gait=mode == "gait")
        if found is None:
            raise SystemExit("No loop found in this clip.")
        s, cycle = found
        e = s + cycle
        picks = select_keyframes(aligned[s:e], config.FRAMES_PER_ACTION, loop=True)
    keys = [lo + s + p for p in picks]
    info = {"full_body": [lo, hi], "window": [lo + s, lo + e], "cycle_frames": cycle, "keyframes": keys,
            "keyframe_seconds": [round(k / fps, 3) for k in keys],
            "keyframe_size_fix": [round(float(rel[k]), 3) for k in keys]}
    return info, rel


def make_sheet(client: MetaClient, out: Path, name: str) -> tuple[bytes, np.ndarray, np.ndarray]:
    ch = CHARACTERS[name]
    if ch.sheet_path:  # the user's own design is the reference: nothing to generate
        rgb = user_sheet(ch)
        png = png_bytes(rgb)
    else:
        estimate(f"character sheet {name} (Muse Image)", config.PRICE_IMAGE)
        png, _ = client.generate_image([sheet_prompt(ch.description, ch.style, ch.body)],
                                       note=f"spikeE sheet {name}")
        rgb = decode_rgb(png)
    save_rgb(out / ("sheet.png" if name == "knight" else f"sheet_{name}.png"), rgb)
    palette = extract_palette(rgb, cutout(rgb, ch))
    return png, rgb, palette


@dataclass(frozen=True)
class Reference:
    """The approved frame a redraw refers to: the previous frame, or frame 0 in anchor mode."""
    png: bytes  # what the critic compares with
    cut: np.ndarray  # its cutout, for the leg-motion check
    guide_mask: np.ndarray  # the pose guide it was drawn from
    anchor: bool
    gen_png: bytes | None = None  # what Muse Image gets instead of `png` (frame 0 with its legs painted out)

    @property
    def legs_hidden(self) -> bool:
        return self.gen_png is not None


def redraw_frame(client: MetaClient, ch: Character, out: Path, tag: str, k: int,
                 guide: tuple[np.ndarray, np.ndarray], sheet_png: bytes, palette: np.ndarray,
                 ref: Reference | None) -> tuple[list[dict], bytes, np.ndarray]:
    """Draw one frame, check it, redraw up to MAX_REGENERATIONS times; returns the rows and the best attempt."""
    guide_rgb, guide_mask = guide
    guide_png = png_bytes(guide_rgb)
    anchor = ref is not None and ref.anchor
    copied_from = "the first frame" if anchor else "the previous frame"
    rows: list[dict] = []
    fix = ""
    use_ref = True  # dropped after a frozen-legs attempt: the model was copying that image
    best: tuple[tuple, bytes, np.ndarray] | None = None
    best_row: dict = {}
    for attempt in range(config.MAX_REGENERATIONS + 1):
        sent = (ref.gen_png or ref.png) if ref is not None and use_ref else None
        legs_hidden = sent is not None and ref is not None and ref.legs_hidden
        png, _ = client.generate_image(
            redraw_parts(sheet_png, guide_png, sent, ch.style, fix, ch.body, anchor, legs_hidden),
            note=f"spikeE {tag} f{k} a{attempt}")
        rgb = decode_rgb(png)
        save_rgb(out / "redraw" / f"{k}_a{attempt}.png", rgb)
        cut = cutout(rgb, ch)
        cand = sam_mask(client, rgb, ch.sam_prompt, note=f"spikeE {tag} mask f{k} a{attempt}")
        if cand is None or not cand.any():
            cand = cut  # SAM sometimes returns nothing for a drawn figure (attack f3 a0)
        iou = silhouette_iou(guide_mask, largest_component(cand))
        motion = None if ref is None else leg_motion(ref.guide_mask, guide_mask, ref.cut, cut)
        verdict, _ = client.critic(
            critic_parts(sheet_png, None if ref is None else ref.png, guide_png, png, ch.body, anchor),
            CRITIC_SCHEMA, note=f"spikeE {tag} critic f{k} a{attempt}")
        scores = FrameScores(iou, float(verdict["pose_score"]), float(verdict["identity_score"]),
                             palette_drift(rgb, cut, palette), motion, copied_from)
        rows.append({"frame": k, "attempt": attempt, "with_prev": sent is not None, "iou": round(iou, 3),
                     "pose": scores.pose, "identity": scores.identity, "drift": round(scores.drift, 3),
                     "leg_motion": "" if motion is None else round(motion, 3),
                     "combined": round(scores.combined, 3), "passed": scores.passed,
                     "failures": "; ".join(scores.failures()), "issues": " | ".join(verdict["issues"]),
                     "fix": verdict["fix_instruction"]})
        print(rows[-1], flush=True)
        if best is None or scores.rank > best[0]:
            best = (scores.rank, png, rgb)
            best_row = rows[-1]
        if scores.passed:
            break
        fix = " ".join(filter(None, [verdict["fix_instruction"], *scores.failures()]))
        if scores.frozen:
            # Drop the reference even when its legs are hidden: keeping it made the dog copy the same stride
            # again on 5 retries (10/30, spikes/REPORT.md Day 4 third round).
            use_ref = False
    assert best is not None
    best_row["chosen"] = True
    save_rgb(out / "redraw" / f"{k}.png", best[2])
    return rows, best[1], best[2]


def redraw(client: MetaClient, out: Path, guides: list[tuple[np.ndarray, np.ndarray]], tag: str,
           name: str, anchor: str = "first", hide_anchor_legs: bool = True) -> tuple[list[dict], dict]:
    """anchor="first": frame 0 first, then frames 1-7 all refer to frame 0 and are drawn at the same time
    (hide_anchor_legs: Muse Image gets frame 0 with its legs painted white).
    anchor="previous": each frame refers to the one before (one at a time); hide_anchor_legs is ignored."""
    ch = CHARACTERS[name]
    sheet_png, _, palette = make_sheet(client, OUT / "e_sequence", name)
    per_try = config.PRICE_IMAGE + config.PRICE_SAM_IMAGE + 0.011
    estimate(f"redraw {len(guides)} frames, up to {config.MAX_REGENERATIONS + 1} tries each",
             len(guides) * per_try * (config.MAX_REGENERATIONS + 1))
    draw = partial(redraw_frame, client, ch, out, tag, sheet_png=sheet_png, palette=palette)
    rows: list[dict] = []
    chosen: list[np.ndarray] = []  # the chosen frames' RGB, in order
    t0 = time.perf_counter()
    if anchor == "previous":
        ref = None
        for k, guide in enumerate(guides):
            r, png, rgb = draw(k, guide, ref=ref)
            rows += r
            chosen.append(rgb)
            ref = Reference(png, cutout(rgb, ch), guide[1], anchor=False)
        timing = {"redraw_seconds": round(time.perf_counter() - t0, 1)}
    else:
        r, png0, rgb0 = draw(0, guides[0], ref=None)
        rows += r
        t_first = time.perf_counter() - t0
        cut0 = cutout(rgb0, ch)
        gen_png = None
        if hide_anchor_legs:
            legless = hide_legs(rgb0, cut0)
            save_rgb(out / "anchor_sent.png", legless)
            gen_png = png_bytes(legless)
        ref = Reference(png0, cut0, guides[0][1], anchor=True, gen_png=gen_png)
        with ThreadPoolExecutor(max_workers=config.REDRAW_WORKERS) as pool:
            done = list(pool.map(lambda k: draw(k, guides[k], ref=ref), range(1, len(guides))))
        for r, _, _ in done:
            rows += r
        chosen = [rgb0] + [rgb for _, _, rgb in done]
        timing = {"first_frame_seconds": round(t_first, 1), "redraw_seconds": round(time.perf_counter() - t0, 1)}
    rows.sort(key=lambda r: (r["frame"], r["attempt"]))
    # Neighbouring chosen frames, the way the animation plays: legs frozen between frame k-1 and k?
    cuts = [cutout(rgb, ch) for rgb in chosen]
    adjacent = [leg_motion(guides[k - 1][1], guides[k][1], cuts[k - 1], cuts[k]) for k in range(1, len(guides))]
    timing["adjacent_leg_motion"] = [None if m is None else round(m, 3) for m in adjacent]
    timing["adjacent_frozen"] = sum(m is not None and m < config.LEG_MOTION_MIN for m in adjacent)
    # Sprite cells: feet on the baseline, same scale for every frame (the canvas ratio).
    # Pixel styles are pixelated onto the sheet palette; hand-drawn styles keep the full-resolution lines.
    cells = []
    for k in range(len(guides)):
        rgb = decode_rgb((out / "redraw" / f"{k}.png").read_bytes())
        m, img, _ = fit_to_canvas(cutout(rgb, ch), config.CELL_SIZE, image=rgb, scale=config.CELL_SIZE / rgb.shape[1])
        assert img is not None
        rgba = np.dstack([img, m.astype(np.uint8) * 255])
        if STYLES[ch.style].pixelate:
            rgba = upscale_nearest(pixelate(rgba, SPRITE_PX, palette), config.CELL_SIZE // SPRITE_PX)
        cells.append(rgba)
    strip = np.hstack(cells)
    Image.fromarray(strip, "RGBA").save(out / "sprite_strip.png")
    frames = [Image.fromarray(c, "RGBA") for c in cells]
    bg = [Image.alpha_composite(Image.new("RGBA", f.size, (235, 235, 235, 255)), f).convert("RGB") for f in frames]
    bg[0].save(out / "preview.gif", save_all=True, append_images=bg[1:], duration=110, loop=0)
    return rows, timing


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", help="folder name under spikes/out/a_video, e.g. jump")
    ap.add_argument("--mode", choices=["once", "loop", "gait"], default="once",
                    help="once: jump/attack; loop: idle; gait: walk/run (a cycle = two steps)")
    ap.add_argument("--character", choices=sorted(CHARACTERS), default="knight")
    ap.add_argument("--edges", default=",".join(config.FULL_BODY_EDGES),
                    help="frame edges the subject must not touch, e.g. left,right")
    ap.add_argument("--redraw", action="store_true")
    ap.add_argument("--anchor", choices=["first", "previous"], default="first",
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

    frames = read_frames(src / "sam_input.mp4")
    keys = info["keyframes"]
    lo, hi = info["window"]
    window_scale = shared_scale(list(masks[lo:hi]), config.CELL_SIZE, config.CELL_MARGIN, rel[lo:hi])
    guide_scale = shared_scale([masks[i] for i in keys], config.GUIDE_SIZE, config.CELL_MARGIN * 2, rel[keys])
    guides = [pose_guide(frames[i], masks[i], fill=True, head_fraction=config.GUIDE_HEAD_FRACTION,
                         scale=guide_scale * rel[i]) for i in keys]
    for k, (g, _) in enumerate(guides):
        save_rgb(out / "guides" / f"{k}.png", g)
    actor = [masked_actor(frames[i], masks[i], window_scale * rel[i]) for i in keys]
    save_rgb(out / "keyframes_actor.png", tile(actor, cols=len(keys)))
    save_rgb(out / "keyframes_guides.png", tile([g for g, _ in guides], cols=len(keys)))
    # Every window frame, aligned, so the cut and the keyframe spacing can be checked by eye.
    every = list(range(lo, hi, max(1, (hi - lo) // 24)))
    save_rgb(out / "window_aligned.png",
             tile([masked_actor(frames[i], masks[i], window_scale * rel[i]) for i in every], cols=12,
                  cell=(192, 192)))

    if args.redraw:
        client = MetaClient()
        hide_legs_ = args.anchor == "first" and not args.show_anchor_legs
        rows, timing = redraw(client, out, guides, args.out or args.clip, args.character, args.anchor, hide_legs_)
        with (out / "scores.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(dict.fromkeys([*rows[0].keys(), "chosen"])))
            w.writeheader()
            w.writerows(rows)
        chosen = [r for r in rows if r.get("chosen")]
        info["redraw"] = {
            "anchor": args.anchor, "hide_anchor_legs": hide_legs_, "frames": len(chosen), "passed": sum(r["passed"] for r in chosen),
            "attempts": len(rows), "first_try_pass": sum(r["passed"] for r in rows if r["attempt"] == 0),
            **timing, "spent_total_usd": round(client.cost_log.total(), 4),
        }
        compare = [cv2.resize(g, (256, 256)) for g, _ in guides] + [
            decode_rgb((out / "redraw" / f"{k}.png").read_bytes()) for k in range(len(guides))]
        save_rgb(out / "compare.png", tile(compare, cols=len(guides)))
        print(info["redraw"])
    write_json(out / "summary.json", info)


if __name__ == "__main__":
    main()

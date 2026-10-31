"""Redraw one action as the character and check every frame (Muse Image + SAM 3.1 + Muse Spark 1.3).

Each frame is drawn, cut out, segmented by SAM 3.1 and judged by the Muse Spark critic; frames that fail
are redrawn with the critic's fix, up to MAX_REGENERATIONS times, and the best attempt is kept.

anchor="first" (default): frame 0 is drawn first, then frames 1-7 all refer to frame 0 and are drawn at the
same time. Muse Image gets frame 0 with its legs painted white so it cannot copy their positions; the critic
and the copied-legs check still see the whole frame. anchor="previous": one frame at a time, each referring
to the frame before (the 10/28-10/29 runs).
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from actsprite import config
from actsprite.capture import largest_object, parse_sam_output
from actsprite.characters import Character, cutout
from actsprite.images import decode_rgb, png_bytes, save_rgb
from actsprite.errors import PipelineError
from actsprite.meta_client import ContentRefused, MetaClient, print_estimate
from actsprite.restyle import hide_legs, redraw_parts
from actsprite.verify import (
    CRITIC_SCHEMA,
    FrameScores,
    critic_parts,
    largest_component,
    leg_drift,
    leg_motion,
    palette_drift,
    silhouette_iou,
)

ANCHORS = ("first", "previous")
TRY_EST_USD = config.PRICE_IMAGE + config.PRICE_SAM_IMAGE + config.CRITIC_MEAN_USD

_parse_pool: ProcessPoolExecutor | None = None
_parse_pool_lock = threading.Lock()


def _sam_parse_pool() -> ProcessPoolExecutor:
    global _parse_pool
    with _parse_pool_lock:
        if _parse_pool is None:
            _parse_pool = ProcessPoolExecutor(max_workers=config.REDRAW_WORKERS)
        return _parse_pool


def sam_mask(client: MetaClient, rgb: np.ndarray, prompt: str, note: str = "") -> np.ndarray | None:
    """Largest SAM 3.1 match for `prompt` in a still image, as a full-size bool mask.

    The SAM decoder is pure Python (about 9 s for a 1024 px redraw) and holds the GIL, so it runs in a
    process pool: parallel redraws would otherwise wait for each other here."""
    global _parse_pool
    text, _ = client.segment(png_bytes(rgb), prompt, note=note)
    size = (rgb.shape[1], rgb.shape[0])
    pool = _sam_parse_pool()
    try:
        objects = pool.submit(parse_sam_output, text, size, video=False, workers=1).result()
    except BrokenProcessPool:
        # A worker died (10/30 knight run, cause unknown; the same SAM text decodes fine). Start a new pool for
        # the next calls and decode this one here, so one lost worker does not stop the whole action.
        with _parse_pool_lock:
            if _parse_pool is pool:
                _parse_pool = None
        print(f"[warn] SAM decode worker died ({note}); decoding in the main process", flush=True)
        objects = parse_sam_output(text, size, video=False, workers=1)
    obj = largest_object(objects)
    return obj.mask if obj is not None else None


@dataclass(frozen=True)
class Reference:
    """The approved frame a redraw refers to: the previous frame, or frame 0 in anchor mode."""
    png: bytes  # what the critic compares with
    cut: np.ndarray  # its cutout, for the leg-motion check
    guide_mask: np.ndarray  # the pose guide it was drawn from
    anchor: bool
    gen_png: bytes | None = None  # what Muse Image gets instead of `png` (frame 0 with its legs painted out)
    legs_stay: bool = False  # in-place loop: keep this frame's stance (check wandering legs, not copies)

    @property
    def legs_hidden(self) -> bool:
        return self.gen_png is not None


def leg_policy(mode: str, hide_anchor_legs: bool = True) -> tuple[bool, bool]:
    """(hide frame 0's legs from Muse Image, legs stay) for an action mode. Moving actions hide frame 0's
    legs and check that they were not copied. In-place loops (config.LEGS_STAY_MODES, e.g. idle) show frame 0
    whole, because its stance is the one to keep, and check instead that the legs did not wander."""
    if mode in config.LEGS_STAY_MODES:
        return False, True
    return hide_anchor_legs, False


def redraw_frame(client: MetaClient, ch: Character, out: Path, note: str, k: int,
                 guide: tuple[np.ndarray, np.ndarray], sheet_png: bytes, palette: np.ndarray,
                 ref: Reference | None, head: str = "") -> tuple[list[dict], bytes, np.ndarray]:
    """Draw one frame, check it, redraw up to MAX_REGENERATIONS times; returns the rows and the best attempt.
    Attempts are saved as out/<k>_a<n>.png and the chosen one as out/<k>.png."""
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
        try:
            png, _ = client.generate_image(
                redraw_parts(sheet_png, guide_png, sent, ch.style, fix, ch.body, anchor, legs_hidden, ch.view, head),
                note=f"{note} f{k} a{attempt}")
        except ContentRefused:
            if best is None:
                raise PipelineError(f"Muse Image refused to draw frame {k} (content filter). Try another part of "
                                    "the clip with --start/--end.") from None
            # A retry's fix text (written by the critic) can trip the filter: keep the best attempt so far.
            print(f"[warn] {note} f{k} a{attempt}: refused by the content filter; keeping attempt "
                  f"{best_row['attempt']}", flush=True)
            best_row["refused_retry"] = True
            break
        rgb = decode_rgb(png)
        save_rgb(out / f"{k}_a{attempt}.png", rgb)
        cut = cutout(rgb, ch)
        cand = sam_mask(client, rgb, ch.sam_prompt, note=f"{note} mask f{k} a{attempt}")
        if cand is None or not cand.any():
            cand = cut  # SAM sometimes returns nothing for a drawn figure (attack f3 a0)
        iou = silhouette_iou(guide_mask, largest_component(cand))
        motion = drift_legs = None
        if ref is not None and ref.legs_stay:
            drift_legs = leg_drift(ref.guide_mask, guide_mask, ref.cut, cut)
        elif ref is not None:
            motion = leg_motion(ref.guide_mask, guide_mask, ref.cut, cut)
        verdict, _ = client.critic(
            critic_parts(sheet_png, None if ref is None else ref.png, guide_png, png, ch.body, anchor, head),
            CRITIC_SCHEMA, note=f"{note} critic f{k} a{attempt}")
        scores = FrameScores(iou, float(verdict["pose_score"]), float(verdict["identity_score"]),
                             palette_drift(rgb, cut, palette), motion, copied_from, drift_legs)
        rows.append({"frame": k, "attempt": attempt, "with_prev": sent is not None, "iou": round(iou, 3),
                     "pose": scores.pose, "identity": scores.identity, "drift": round(scores.drift, 3),
                     "leg_motion": "" if motion is None else round(motion, 3),
                     "leg_drift": "" if drift_legs is None else round(drift_legs, 3),
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
    save_rgb(out / f"{k}.png", best[2])
    return rows, best[1], best[2]


def redraw_action(client: MetaClient, ch: Character, guides: list[tuple[np.ndarray, np.ndarray]],
                  sheet_png: bytes, palette: np.ndarray, out: Path, note: str, anchor: str = "first",
                  hide_anchor_legs: bool = True, legs_stay: bool = False, heads: list[str] | None = None,
                  ) -> tuple[list[dict], list[np.ndarray], dict]:
    """Redraw every keyframe. Returns (one row per attempt, the chosen frames' RGB in order, timing and the
    leg motion between neighbouring chosen frames). hide_anchor_legs only applies to anchor="first";
    legs_stay=True checks that the legs keep frame 0's stance instead of checking for copies (see leg_policy).
    heads: the actor's head direction per frame (actsprite/head.py), or None when not tracked."""
    if anchor not in ANCHORS:
        raise ValueError(f"anchor must be one of {ANCHORS}")
    print_estimate(f"redraw {len(guides)} frames, up to {config.MAX_REGENERATIONS + 1} tries each",
                   len(guides) * TRY_EST_USD * (config.MAX_REGENERATIONS + 1))

    def draw(k: int, ref: Reference | None) -> tuple[list[dict], bytes, np.ndarray]:
        return redraw_frame(client, ch, out, note, k, guides[k], sheet_png, palette, ref,
                            heads[k] if heads else "")

    rows: list[dict] = []
    chosen: list[np.ndarray] = []
    t0 = time.perf_counter()
    if anchor == "previous":
        ref = None
        for k in range(len(guides)):
            r, png, rgb = draw(k, ref)
            rows += r
            chosen.append(rgb)
            ref = Reference(png, cutout(rgb, ch), guides[k][1], anchor=False, legs_stay=legs_stay)
        timing: dict = {"redraw_seconds": round(time.perf_counter() - t0, 1)}
    else:
        r, png0, rgb0 = draw(0, None)
        rows += r
        t_first = time.perf_counter() - t0
        cut0 = cutout(rgb0, ch)
        gen_png = None
        if hide_anchor_legs:
            legless = hide_legs(rgb0, cut0)
            save_rgb(out.parent / "anchor_sent.png", legless)
            gen_png = png_bytes(legless)
        ref0 = Reference(png0, cut0, guides[0][1], anchor=True, gen_png=gen_png, legs_stay=legs_stay)
        with ThreadPoolExecutor(max_workers=config.REDRAW_WORKERS) as pool:
            done = list(pool.map(lambda k: draw(k, ref0), range(1, len(guides))))
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
    return rows, chosen, timing

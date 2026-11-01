"""Isolated MediaPipe/Muse skeleton experiment; never tracks or calls SAM.

Run with .venv/Scripts/python -B -m spikes.spike_skeleton [--prepare-only|--self-check].
MediaPipe 0.10.21: Apache-2.0, https://github.com/google-ai-edge/mediapipe
Uses the upstream Pose API and landmark convention, without copied source.
All images/measurements go to out/_eval/skeleton; normal Meta cache/cost log apply.
Pose reads every ORIGINAL RGB frame in VIDEO mode, before selecting keyframes.
SAM association and point visibility gate drawing; rejected frames keep their gray guide.
Original RGB overlays and five-column comparisons contain faces: local out/_eval only.
Old AND new images are scored against the SAME original gray guide, using local
character cutout IoU (no new SAM), the existing critic and FrameScores thresholds.
Original pipeline scores are retained separately, since their IoU used SAM.
One generation per target; this tests skeleton guidance without retry selection.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

from actsprite import config

ROOT = config.ROOT
OUT = ROOT / "out" / "_eval" / "skeleton"
os.environ.setdefault("MPLCONFIGDIR", str(OUT / "_matplotlib"))

import cv2
import numpy as np

from actsprite.align import fit_to_canvas, mask_bbox, shared_scale, size_drift
from actsprite.characters import PRESETS, cutout
from actsprite.images import decode_rgb, png_bytes, save_rgb
from actsprite.meta_client import BudgetExceeded, CacheMiss, MetaClient, print_estimate, request_key
from actsprite.redraw import Reference
from actsprite.restyle import hide_legs, redraw_parts
from actsprite.sequence import make_guides
from actsprite.verify import (CRITIC_SCHEMA, FrameScores, critic_parts, extract_palette,
                              largest_component, leg_drift, leg_motion, palette_drift,
                              silhouette_iou)

CASES = (("knight_punch3", "attack", "knight", (3, 4)),
         ("lineman_run20", "run", "lineman", (4, 5, 6)))
PREFIX = "spike skeleton v2 video"
EXPERIMENT_PREFIX = "spike skeleton "
LIMIT = 1.0
CRITIC_OUTPUT_CAP = 8192  # includes the critic's high-effort reasoning, not just its JSON
MIN_VISIBILITY = .5
MIN_INSIDE_SHARE = .6
MAX_OUTSIDE_HEIGHT_SHARE = .02
CORE = np.array([0, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32])
FIX = ("The coloured lines on the pose guide are the actor's skeleton: blue = the actor's left arm "
       "and leg, orange = the actor's right arm and leg, green = torso and head. Place the limbs "
       "on these lines, matching every elbow, knee, ankle and the body lean. Left/right mean the "
       "actor's anatomical sides, not image left/right. Overlapping legs must remain overlapping; "
       "do not invent a wider stance. The colours are guidance only; do not draw the skeleton "
       "or its colours on the final character.")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def cost_rows() -> list[dict]:
    if not config.COST_LOG.exists():
        return []
    with config.COST_LOG.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r["note"].startswith(EXPERIMENT_PREFIX)]


def spent() -> float:
    return sum(float(r["cost_usd"]) for r in cost_rows())


def reserve(used: float, amount: float) -> None:
    if used + amount > LIMIT + 1e-9:
        raise BudgetExceeded(f"Skeleton experiment ${used:.6f} + reserve ${amount:.3f} exceeds $1.00; stopped.")


def guard_client(client: MetaClient) -> None:
    """Keep MetaClient(), its cache and cost logging; bound this experiment separately."""
    original = client._call

    def guarded(payload: dict, **kwargs: Any) -> Any:
        if kwargs["operation"] == "critic":
            payload = {**payload, "max_output_tokens": CRITIC_OUTPUT_CAP}
            # Four <=512px images and a short prompt; reserve 40k input tokens.
            upper = 40000 * config.PRICE_CRITIC_INPUT_TOKEN + CRITIC_OUTPUT_CAP * config.PRICE_CRITIC_OUTPUT_TOKEN
        elif kwargs["operation"] == "generate_image":
            upper = config.PRICE_IMAGE
        else:
            raise RuntimeError("This spike permits only Muse image/critic calls; SAM is disabled.")
        cached = (client.cache_dir / f"{request_key(payload)}.json").exists()
        reserve(spent(), 0.0 if cached else upper)
        result = original(payload, **{**kwargs, "estimate_usd": max(kwargs["estimate_usd"], upper)})
        reserve(spent(), 0.0)
        return result

    client._call = guarded


def project(xy: np.ndarray, mask: np.ndarray, scale: float) -> np.ndarray:
    """The rounded resize and scaled-mask centroid used inside align.fit_to_canvas."""
    left, top, right, bottom = mask_bbox(mask)
    width = max(1, round((right - left) * scale))
    height = max(1, round((bottom - top) * scale))
    resized = cv2.resize(mask[top:bottom, left:right].astype(np.uint8), (width, height),
                         interpolation=cv2.INTER_NEAREST) > 0
    centre = float(np.nonzero(resized)[1].mean()) if resized.any() else width / 2
    offset = np.array([round(config.GUIDE_SIZE / 2 - centre), config.GUIDE_SIZE - height])
    return (xy - [left, top]) * [width / (right - left), height / (bottom - top)] + offset


def track_video(path: Path, masks: np.ndarray, keys: list[int]) -> tuple[dict, dict, dict]:
    """Feed EVERY decoded original RGB frame, in order, to one VIDEO tracker per clip."""
    import mediapipe as mp

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open SAM input video: {path}")
    frames, landmarks = {}, {}
    wanted = set(keys)
    index, detections = 0, 0
    try:
        with mp.solutions.pose.Pose(static_image_mode=False, model_complexity=1,
                                    smooth_landmarks=True, enable_segmentation=False,
                                    min_detection_confidence=.5, min_tracking_confidence=.5) as pose:
            while True:
                ok, bgr = cap.read()
                if not ok:
                    break
                if index >= len(masks) or bgr.shape[:2] != masks.shape[1:]:
                    raise RuntimeError("SAM input video frame count/dimensions differ from track.npz")
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                detected = pose.process(np.ascontiguousarray(rgb))
                points = detected.pose_landmarks
                detections += points is not None
                if index in wanted:
                    frames[index] = rgb
                    landmarks[index] = None if points is None else np.array(
                        [[p.x * rgb.shape[1], p.y * rgb.shape[0], p.z, p.visibility]
                         for p in points.landmark], dtype=float)
                index += 1
    finally:
        cap.release()
    if index != len(masks) or set(frames) != wanted:
        raise RuntimeError(f"SAM input video frame count {index} differs from track.npz {len(masks)}")
    return frames, landmarks, {"mode": "VIDEO", "input": str(path), "input_pixels": "original RGB",
                               "processed_frames": index, "detected_frames": detections,
                               "frame_size_wh": [int(masks.shape[2]), int(masks.shape[1])]}


def quality(xy: np.ndarray, visibility: np.ndarray, mask: np.ndarray) -> tuple[bool, np.ndarray, dict]:
    """Associate the detected person with SAM, then discard unreliable individual points."""
    h, w = mask.shape
    _, top, _, bottom = mask_bbox(mask)
    finite = np.isfinite(xy).all(axis=1) & np.isfinite(visibility)
    rounded = np.rint(np.where(np.isfinite(xy), xy, -1)).astype(int)
    in_image = finite & (rounded[:, 0] >= 0) & (rounded[:, 0] < w) & (rounded[:, 1] >= 0) & (rounded[:, 1] < h)
    distance = np.full(33, np.inf)
    outside = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    distance[in_image] = outside[rounded[in_image, 1], rounded[in_image, 0]]
    inside = distance == 0
    tolerance = max(1., (bottom - top) * MAX_OUTSIDE_HEIGHT_SHARE)
    valid = finite & (visibility >= MIN_VISIBILITY) & (distance <= tolerance)
    inside_share, core_share = float(inside.mean()), float(inside[CORE].mean())
    reasons = []
    if inside_share < MIN_INSIDE_SHARE or core_share < MIN_INSIDE_SHARE:
        reasons.append("most_joints_not_inside_sam")
    if int(valid[CORE].sum()) < 8:
        reasons.append("too_few_reliable_body_joints")
    if int(valid[[11, 12, 23, 24]].sum()) < 3:
        reasons.append("unreliable_torso")
    point_reasons = []
    for i in range(33):
        rejected = []
        if not finite[i]:
            rejected.append("nonfinite")
        if not finite[i] or visibility[i] < MIN_VISIBILITY:
            rejected.append("low_visibility")
        if distance[i] > tolerance:
            rejected.append("outside_mask")
        point_reasons.append(rejected)
    used = not reasons
    return used, valid if used else np.zeros(33, bool), {
        "skeleton_used": used, "fallback_reason": ";".join(reasons),
        "inside_share": inside_share, "core_inside_share": core_share,
        "valid_core_count": int(valid[CORE].sum()), "outside_tolerance_px": tolerance,
        "outside_distance_px": [float(d) if np.isfinite(d) else None for d in distance],
        "point_reasons": point_reasons}


def draw_skeleton(image: np.ndarray, points: np.ndarray, valid: np.ndarray, thickness: int) -> np.ndarray:
    """The same filtered joints on the original RGB and on the gray guide."""
    output = image.copy()
    groups = (((11, 13, 15), (23, 25, 27, 29, 31)),
              ((12, 14, 16), (24, 26, 28, 30, 32)))

    def line(a: np.ndarray, b: np.ndarray, color: tuple[int, int, int]) -> None:
        cv2.line(output, tuple(np.rint(a).astype(int)), tuple(np.rint(b).astype(int)),
                 color, thickness, cv2.LINE_AA)

    for paths, color in zip(groups, ((25, 100, 235), (245, 140, 20))):
        for path in paths:
            for a, b in zip(path, path[1:]):
                if valid[a] and valid[b]:
                    line(points[a], points[b], color)
            for a in path:
                if valid[a]:
                    cv2.circle(output, tuple(np.rint(points[a]).astype(int)), max(2, thickness // 2),
                               color, -1, cv2.LINE_AA)
    green = (20, 165, 90)
    shoulders, hips = points[[11, 12]].mean(axis=0), points[[23, 24]].mean(axis=0)
    for a, b in ((11, 12), (11, 23), (12, 24), (23, 24)):
        if valid[a] and valid[b]:
            line(points[a], points[b], green)
    if valid[[11, 12, 23, 24]].all():
        line(hips, shoulders, green)
    if valid[[0, 11, 12]].all():
        line(shoulders, points[0], green)
    if valid[0]:
        cv2.circle(output, tuple(np.rint(points[0]).astype(int)), thickness, green, 2, cv2.LINE_AA)
    return output


def skeleton(landmarks: np.ndarray | None, rgb: np.ndarray, mask: np.ndarray, guide: np.ndarray,
             scale: float) -> tuple[np.ndarray, np.ndarray, dict]:
    if landmarks is None:
        return guide.copy(), rgb.copy(), {"skeleton_used": False, "fallback_reason": "no_pose", "landmarks": []}
    xy, visibility = landmarks[:, :2], landmarks[:, 3]
    used, valid, details = quality(xy, visibility, mask)
    points = project(xy, mask, scale)
    placed, _, _ = fit_to_canvas(mask, config.GUIDE_SIZE, scale=scale)
    _, gt, _, gb = mask_bbox(placed)
    _, top, _, bottom = mask_bbox(mask)
    thickness = max(1, round((gb - gt) * .03))
    guide_out = draw_skeleton(guide, points, valid, thickness)
    source_out = draw_skeleton(rgb, xy, valid, max(1, round((bottom - top) * .03)))
    details.update({"line_width": thickness,
                    "landmarks": [{"index": i, "source_xy": xy[i].tolist(), "guide_xy": points[i].tolist(),
                                   "visibility": float(visibility[i]), "z": float(landmarks[i, 2]),
                                   "drawn": bool(valid[i] and i in CORE)} for i in range(33)],
                    "note": "Filtered VIDEO landmarks from original RGB; rejected joints are not drawn."})
    assert used or np.array_equal(guide_out, guide)
    return guide_out, source_out, details


def prepare() -> list[dict]:
    import mediapipe as mp

    assert mp.__version__ == "0.10.21", mp.__version__
    plans = []
    for case, action, character, targets in CASES:
        work = ROOT / "out" / case / "work" / action
        dest = OUT / case
        info = json.loads((work / "result.json").read_text(encoding="utf-8"))
        with np.load(work / "track.npz") as track:
            masks, fps = track["masks"], float(track["fps"])
        keys = info["keyframes"]
        frames, landmarks, tracking = track_video(work / "sam_input.mp4", masks, keys)
        rel = np.ones(len(masks))
        lo, hi = info["full_body"]
        if info["mode"] == "gait":
            rel[lo:hi] = size_drift(list(masks[lo:hi]), fps)
        guides = make_guides(frames, masks, keys, rel)
        scale = shared_scale([masks[i] for i in keys], config.GUIDE_SIZE,
                             config.CELL_MARGIN * 2, rel[keys])
        with (work / "scores.csv").open(encoding="utf-8", newline="") as f:
            previous = {int(r["frame"]): r for r in csv.DictReader(f) if r.get("chosen") == "True"}
        checks = []
        for k, (guide, gm) in enumerate(guides):
            old_guide = decode_rgb((work / "guides" / f"{k}.png").read_bytes())
            if not np.array_equal(guide, old_guide):
                raise RuntimeError(f"{case} guide {k} differs from saved guide; stop before paying.")
            skel, source, details = skeleton(landmarks[keys[k]], frames[keys[k]], masks[keys[k]],
                                             guide, scale * rel[keys[k]])
            save_rgb(dest / "guides" / f"{k}.png", skel)
            # Contains real faces. Local out/_eval only; never used in an API request.
            save_rgb(dest / "source_skeleton" / f"{k}.png", source)
            save_rgb(dest / "old_guides" / f"{k}.png", guide)
            write_json(dest / "landmarks" / f"{k}.json", {"frame": k, "source_frame": keys[k], **details})
            checks.append({"frame": k, "source_frame": keys[k], "guide_matches_saved": True,
                           "skeleton_used": details["skeleton_used"],
                           "fallback_reason": details["fallback_reason"]})
            if k in targets:
                old = (work / "redraw" / f"{k}.png").read_bytes()
                attempt = previous[k]["attempt"]
                assert old == (work / "redraw" / f"{k}_a{attempt}.png").read_bytes(), "Old selection changed"
                save_rgb(dest / "old_redraw" / f"{k}.png", decode_rgb(old))
        write_json(dest / "preparation.json", {"mediapipe": mp.__version__, "checks": checks,
                   "targets": targets, "fix": FIX, "tracking": tracking,
                   "thresholds": {"min_visibility": MIN_VISIBILITY, "min_inside_share": MIN_INSIDE_SHARE,
                                  "max_outside_height_share": MAX_OUTSIDE_HEIGHT_SHARE,
                                  "min_valid_core": 8, "min_valid_torso": 3}})
        with (dest / "skeleton_quality.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(checks[0]))
            writer.writeheader()
            writer.writerows(checks)
        sheet_png = (work.parent / "sheet.png").read_bytes()
        ch = PRESETS[character]
        sheet_rgb = decode_rgb(sheet_png)
        palette = extract_palette(sheet_rgb, cutout(sheet_rgb, ch))
        png0 = (work / "redraw" / "0.png").read_bytes()
        rgb0 = decode_rgb(png0)
        cut0 = cutout(rgb0, ch)
        gen_png = png_bytes(hide_legs(rgb0, cut0)) if info["hide_anchor_legs"] else None
        ref = Reference(png0, cut0, guides[0][1], anchor=True, gen_png=gen_png,
                        legs_stay=info["legs_stay"])
        plans.append(dict(case=case, work=work, dest=dest, targets=targets, keys=keys, guides=guides,
                          ch=ch, sheet=sheet_png, palette=palette, ref=ref, previous=previous,
                          quality={r["frame"]: r for r in checks}))
        used = sum(r["skeleton_used"] for r in checks)
        print(f"[prepare] {case}: {tracking['processed_frames']} original RGB frames tracked in VIDEO mode; "
              f"{len(keys)} identical rebuilt guides; {used} skeletons used, {len(keys)-used} fallbacks", flush=True)
    return plans


def critic_image(png: bytes) -> bytes:
    rgb = decode_rgb(png)
    h, w = rgb.shape[:2]
    if max(h, w) > 512:
        rgb = cv2.resize(rgb, (round(w * 512 / max(h, w)), round(h * 512 / max(h, w))),
                         interpolation=cv2.INTER_AREA)
    return png_bytes(rgb)


def evaluate(client: MetaClient, plan: dict, k: int, png: bytes, label: str) -> dict:
    ch, ref = plan["ch"], plan["ref"]
    guide, gm = plan["guides"][k]
    rgb = decode_rgb(png)
    cut = cutout(rgb, ch)
    iou = silhouette_iou(gm, largest_component(cut))
    # The unchanged gray guide is used for BOTH evaluations, avoiding a changed judge input.
    parts = critic_parts(critic_image(plan["sheet"]), critic_image(ref.png), png_bytes(guide),
                         critic_image(png), ch.body, anchor=True)
    verdict, _ = client.critic(parts, CRITIC_SCHEMA, note=f"{PREFIX} {plan['case']} {label} critic f{k}")
    motion = None if ref.legs_stay else leg_motion(ref.guide_mask, gm, ref.cut, cut)
    drift = leg_drift(ref.guide_mask, gm, ref.cut, cut) if ref.legs_stay else None
    score = FrameScores(iou, float(verdict["pose_score"]), float(verdict["identity_score"]),
                        palette_drift(rgb, cut, plan["palette"]), motion, "the first frame", drift)
    result = dict(iou=round(iou, 3), pose=score.pose, identity=score.identity, passed=score.passed,
                  drift=round(score.drift, 3), leg_motion=motion, leg_drift=drift,
                  failures="; ".join(score.failures()), issues=" | ".join(verdict["issues"]))
    write_json(plan["dest"] / "scores" / f"{k}_{label}.json", result)
    return result


def comparison(plan: dict, rows: list[dict]) -> None:
    cell, row_height = 384, 420
    canvas = np.full((48 + len(rows) * row_height, 5 * cell, 3), 255, np.uint8)
    for j, label in enumerate(("Original RGB + skeleton", "Old guide", "Skeleton guide", "Old selected redraw", "New redraw")):
        cv2.putText(canvas, label, (j * cell + 12, 28), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 0), 1)
    for i, row in enumerate(rows):
        k, dest = row["frame"], plan["dest"]
        images = (dest / "source_skeleton" / f"{k}.png", plan["work"] / "guides" / f"{k}.png", dest / "guides" / f"{k}.png",
                  plan["work"] / "redraw" / f"{k}.png", dest / "redraw" / f"{k}.png")
        top = 48 + i * row_height
        for j, path in enumerate(images):
            rgb = decode_rgb(path.read_bytes())
            h, w = rgb.shape[:2]
            scale = min(cell / h, cell / w)
            nh, nw = round(h * scale), round(w * scale)
            y, x = top + (cell - nh) // 2, j * cell + (cell - nw) // 2
            canvas[y:y + nh, x:x + nw] = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
            label = f"f{k} / source {row['source_frame']}"
            if j == 0 or j == 2:
                label += f" / skeleton {row['skeleton_used']}"
            if j > 2:
                prefix = "old" if j == 3 else "new"
                label = f"IoU {row[prefix+'_iou']:.3f} pose {row[prefix+'_pose']:g} id {row[prefix+'_identity']:g} pass {row[prefix+'_passed']}"
            cv2.putText(canvas, label, (j * cell + 8, top + cell + 22), cv2.FONT_HERSHEY_SIMPLEX, .47, (0, 0, 0), 1)
    save_rgb(plan["dest"] / "compare.png", canvas)


def run(plans: list[dict]) -> None:
    n = sum(len(p["targets"]) for p in plans)
    # Probe the exact old-critic requests offline before reserving any paid work.
    offline = MetaClient(offline=True)
    guard_client(offline)
    missing_old = 0
    for plan in plans:
        for k in plan["targets"]:
            try:
                evaluate(offline, plan, k, (plan["work"] / "redraw" / f"{k}.png").read_bytes(), "old")
            except CacheMiss:
                missing_old += 1
    critic_reserve = 40000 * config.PRICE_CRITIC_INPUT_TOKEN + CRITIC_OUTPUT_CAP * config.PRICE_CRITIC_OUTPUT_TOKEN
    estimate = n * config.PRICE_IMAGE + (n + missing_old) * config.CRITIC_MEAN_USD
    ceiling = n * config.PRICE_IMAGE + (n + missing_old) * critic_reserve
    print_estimate(f"VIDEO skeleton {n} redraws + {n+missing_old} uncached critics, no SAM", estimate)
    print(f"[cache] {n-missing_old}/{n} old critic responses confirmed offline", flush=True)
    print(f"[cost] conservative reservation ${ceiling:.4f}; already spent ${spent():.6f}; cap $1.00", flush=True)
    reserve(spent(), ceiling)
    client = MetaClient()
    guard_client(client)
    before = spent()
    all_rows = []
    try:
        for plan in plans:
            rows = []
            for k in plan["targets"]:
                ch, ref, dest = plan["ch"], plan["ref"], plan["dest"]
                old_png = (plan["work"] / "redraw" / f"{k}.png").read_bytes()
                old_score = evaluate(client, plan, k, old_png, "old")
                parts = redraw_parts(plan["sheet"], (dest / "guides" / f"{k}.png").read_bytes(),
                                     ref.gen_png or ref.png, ch.style, FIX if plan["quality"][k]["skeleton_used"] else "", ch.body,
                                     anchor=True, legs_hidden=ref.legs_hidden, view=ch.view)
                png, _ = client.generate_image(parts, note=f"{PREFIX} {plan['case']} redraw f{k}")
                save_rgb(dest / "redraw" / f"{k}.png", decode_rgb(png))
                new_score = evaluate(client, plan, k, png, "new")
                row = dict(case=plan["case"], frame=k, source_frame=plan["keys"][k],
                           skeleton_used=plan["quality"][k]["skeleton_used"],
                           skeleton_fallback_reason=plan["quality"][k]["fallback_reason"],
                           iou_method="local character cutout (both)", critic_guide="original gray (both)")
                for label, scores in (("old", old_score), ("new", new_score)):
                    row.update({f"{label}_{name}": value for name, value in scores.items()})
                row.update({f"original_pipeline_{key}": plan["previous"][k][key]
                            for key in ("iou", "pose", "identity", "passed")})
                rows.append(row)
                all_rows.append(row)
                with (dest / "scores.csv").open("w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(row))
                    writer.writeheader()
                    writer.writerows(rows)
                comparison(plan, rows)
                print(json.dumps(row), flush=True)
    finally:
        if all_rows:
            with (OUT / "scores.csv").open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(all_rows[0]))
                writer.writeheader()
                writer.writerows(all_rows)
        write_json(OUT / "run_summary.json", {"spent_this_run_usd": round(spent() - before, 6),
                   "experiment_total_usd": round(spent(), 6), "cost_log": str(config.COST_LOG),
                   "cost_note_prefix": PREFIX, "budget_note_prefix": EXPERIMENT_PREFIX,
                   "calls": client.calls, "completed_frames": len(all_rows),
                   "cost_rows": cost_rows(), "rows": all_rows,
                   "evaluation": "Paired re-evaluation with local cutout IoU and same original gray guide; no SAM requests."})


def self_check() -> None:
    mask = np.zeros((12, 12), bool)
    mask[2:10, 3:7] = True
    xy = project(np.array([[3., 2.], [6., 9.]]), mask, 2.)
    assert np.array_equal(xy, [[252., 496.], [258., 510.]]), xy
    reserve(.9, .1)
    try:
        reserve(.95, .06)
    except BudgetExceeded:
        pass
    else:
        raise AssertionError("Budget guard failed")
    assert "blue" in FIX and "orange" in FIX and "green" in FIX
    print("[self-check] coordinate mapping and $1 budget guard passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    self_check()
    if not args.self_check:
        plans = prepare()
        if not args.prepare_only:
            run(plans)

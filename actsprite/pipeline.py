"""The whole pipeline for one character: phone clip of each action -> SAM 3.1 track -> keyframes and pose
guides -> character redraw with the verification loop -> the output ZIP of the interface contract
(docs/02_product_spec.md 4.2):

  actsprite_<name>/
    <name>_sheet.png                  one row per action, fixed cells, transparent background
    <name>_meta.json                  the contract shared with the Unity importer
    frames/<action>/<action>_00.png   every frame as its own PNG, for touch-ups
    preview/<action>.gif              the animation without opening Unity
    report/scores.csv                 every redraw attempt with its scores; needs_review marks frames to check
    report/summary.md                 spend, time and the frames to check by hand
    reference/character_sheet.png
    reference/character_sheet_front.png   once an action was drawn in front view
    unity/ActSpriteImporter.cs        once the importer exists
  actsprite_<name>.zip                the same folder, zipped
  work/<action>/                      SAM input clip, track, pose guides, every attempt, the action's result

Each run does one action and then rebuilds the package from every action finished so far, so running
attack, then jump, then idle for the same character gives one sheet with three rows.
Nothing in the package shows the actor's photo pixels: the pose guides stay in work/ and are silhouettes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from actsprite import config
from actsprite.capture import main_track, parse_sam_output, prepare_video, read_frames_at
from actsprite.characters import Character, cutout, make_sheet
from actsprite.errors import PipelineError
from actsprite.head import head_pose
from actsprite.images import save_rgb, save_rgba, tile
from actsprite.meta_client import MetaClient, estimate_sam_video_cost, print_estimate
from actsprite.pack import action_fps, character_meta, export_cells, preview_gif, sheet_from_rows, sprite_cells
from actsprite.redraw import leg_policy, redraw_action
from actsprite.restyle import STYLES
from actsprite.sequence import LOOP_MODES, choose_frames, clip_fps, make_guides, mode_for


def track_actor(client: MetaClient, video: Path, prompt: str, work: Path, *,
                target_fps: float = config.SAM_VIDEO_FPS,
                short_side: int = config.SAM_VIDEO_MAX_SHORT_SIDE,
                name: str = "track") -> tuple[np.ndarray, float, Path]:
    """(masks per frame of the SAM clip, its fps, the SAM clip). One SAM 3.1 video call; the decoded track is
    kept in work/<name>.npz and reused while the clip and prompt stay the same."""
    if not video.exists():
        raise PipelineError(f"Video not found: {video}")
    pv = prepare_video(video, work / "sam_input.mp4", target_fps=target_fps, max_short_side=short_side)
    data = pv.path.read_bytes()
    key = hashlib.sha256(data + prompt.encode()).hexdigest()
    saved = work / f"{name}.npz"
    if saved.exists():
        z = np.load(saved)
        if str(z["key"]) == key:
            return z["masks"], float(z["fps"]), pv.path
    print_estimate(f"SAM 3.1 video track of '{prompt}' in {video.name} ({pv.frame_count} frames)",
                   estimate_sam_video_cost(pv.frame_count))
    suffix = "" if name == "track" else f" {name}"
    text, _ = client.segment(data, prompt, video_frame_count=pv.frame_count, note=f"actsprite track {video.name}{suffix}")
    track = main_track(parse_sam_output(text, pv.size, video=True))
    if not track:
        raise PipelineError(f"SAM 3.1 found no '{prompt}' in {video.name}. Check --actor (person, dog, cat ...).")
    masks = np.zeros((pv.frame_count, pv.size[1], pv.size[0]), bool)
    for i, obj in track.items():
        masks[i] = obj.mask
    np.savez_compressed(saved, masks=masks, fps=pv.fps, key=key, source_indices=np.array(pv.source_indices))
    return masks, pv.fps, pv.path


def track_faces(client: MetaClient, video: Path, work: Path, sample_fps: float) -> np.ndarray | None:
    """The actor's face per frame (SAM 3.1 prompt config.SAM_FACE_PROMPT), or None when no face is ever found."""
    try:
        faces, _, _ = track_actor(client, video, config.SAM_FACE_PROMPT, work, target_fps=sample_fps, name="face")
    except PipelineError:
        print("[warn] SAM 3.1 found no face in the clip: the head direction is left to the pose guide", flush=True)
        return None
    return faces


def playback_fps(fps: float | str | None, info: dict, sam_fps: float, mode: str) -> float:
    """None: the contract default for the mode (span: the clip's speed); "auto": the clip's speed; or a number."""
    if fps is None:
        fps = "auto" if mode == "span" else action_fps(mode)
    fps = clip_fps(info, sam_fps, mode) if fps == "auto" else float(fps)
    if not config.FPS_MIN <= fps <= config.FPS_MAX:
        raise PipelineError(f"--fps must be {config.FPS_MIN:g}-{config.FPS_MAX:g} or auto, not {fps:g}.")
    return int(fps) if fps.is_integer() else fps  # 12, not 12.0, in the meta JSON


def run_action(video: Path, root: Path, action: str, ch: Character, *, actor: str = "person",
               mode: str | None = None, edges: tuple[str, ...] = config.FULL_BODY_EDGES, anchor: str = "first",
               hide_anchor_legs: bool = True, frames: int = config.FRAMES_PER_ACTION,
               fps: float | str | None = None, start: float | None = None, end: float | None = None,
               head_turn: bool | None = None, sample_fps: float = config.SAM_VIDEO_FPS,
               client: MetaClient | None = None) -> dict:
    """Track, choose keyframes, redraw and check one action; writes work/<action>/ and returns its result.
    frames: keyframes to draw; fps: playback speed (see playback_fps); start/end: part of the clip in seconds.
    head_turn: also track the face with SAM 3.1 so the drawn head turns like the actor's (None: on in front view).
    sample_fps: frames per second of the clip sent to SAM 3.1 for tracking."""
    if not config.SAMPLE_FPS_MIN <= sample_fps <= config.SAMPLE_FPS_MAX:
        raise PipelineError(f"--sample-fps must be {config.SAMPLE_FPS_MIN:g}-{config.SAMPLE_FPS_MAX:g}, "
                            f"not {sample_fps:g}.")
    head_turn = ch.view == "front" if head_turn is None else head_turn
    mode = mode_for(action, mode)
    client = client or MetaClient()
    work = root / "work" / action
    spent_before = client.cost_log.total()
    calls_before = dict(client.calls)
    t0 = time.perf_counter()
    note = f"actsprite {ch.name} {action}"

    masks, sam_fps, sam_clip = track_actor(client, video, actor, work, target_fps=sample_fps)
    t_track = time.perf_counter() - t0
    info, rel = choose_frames(masks, sam_fps, mode, edges, frames, start, end)
    play_fps = playback_fps(fps, info, sam_fps, mode)
    keys = info["keyframes"]
    faces = track_faces(client, video, work, sample_fps) if head_turn else None
    poses = [head_pose(masks[k], None if faces is None else faces[k]) for k in keys] if faces is not None else None
    heads = [p.describe() if p else "" for p in poses] if poses else None
    guides = make_guides(read_frames_at(sam_clip, keys), masks, keys, rel, faces)
    for k, (g, _) in enumerate(guides):
        save_rgb(work / "guides" / f"{k}.png", g)

    sheet_png, sheet_rgb, palette = make_sheet(client, ch, note=f"{note} sheet")
    save_rgb(root / "work" / ("sheet_front.png" if ch.view == "front" else "sheet.png"), sheet_rgb)
    if ch.view == "front" and not (root / "work" / "sheet.png").exists():
        save_rgb(root / "work" / "sheet.png", make_sheet(client, replace(ch, view="side"))[1])  # cached
    hide_legs, legs_stay = leg_policy(mode, hide_anchor_legs)
    rows, rgbs, timing = redraw_action(client, ch, guides, sheet_png, palette, work / "redraw", note,
                                       anchor, hide_legs, legs_stay, heads)

    pixel_art = STYLES[ch.style].pixelate
    cells = sprite_cells(rgbs, [cutout(rgb, ch) for rgb in rgbs], palette,
                         config.SPRITE_PIXEL_SIZE if pixel_art else None)
    for k, cell in enumerate(export_cells(cells, pixel_art)):
        save_rgba(work / "cells" / f"{k:02d}.png", cell)
    for r in rows:
        r["needs_review"] = bool(r.get("chosen")) and not r["passed"]
    with (work / "scores.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys([*rows[0].keys(), "chosen", "needs_review"])))
        w.writeheader()
        w.writerows(rows)
    save_rgb(work / "compare.png", compare_sheet([g for g, _ in guides], rgbs))

    chosen = sorted((r for r in rows if r.get("chosen")), key=lambda r: r["frame"])
    result = {
        "name": action, "mode": mode, "frames": len(chosen), "fps": play_fps, "loop": mode in LOOP_MODES,
        "view": ch.view, "head_turn": faces is not None, "heads": heads,
        "head_yaw": [None if p is None else round(p.yaw, 3) for p in poses] if poses else None,
        "passed": [bool(r["passed"]) for r in chosen],
        "attempts": len(rows), "first_try_pass": sum(bool(r["passed"]) for r in rows if r["attempt"] == 0),
        "video": str(video), "actor": actor, "edges": list(edges), "sam_fps": round(sam_fps, 2),
        "start": start, "end": end,
        "anchor": anchor, "hide_anchor_legs": anchor == "first" and hide_legs, "legs_stay": legs_stay,
        **info, **timing,
        "track_seconds": round(t_track, 1), "seconds": round(time.perf_counter() - t0, 1),
        "spent_usd": round(client.cost_log.total() - spent_before, 4),
        "api_calls": {k: client.calls[k] - calls_before[k] for k in client.calls},  # new = sent to Meta
    }
    (work / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def compare_sheet(guides: list[np.ndarray], redraws: list[np.ndarray], cols: int = 8) -> np.ndarray:
    """Pose guides above their redraws, `cols` frames per row pair."""
    if len(guides) <= cols:
        return tile(guides + redraws, cols=len(guides))
    images: list[np.ndarray] = []
    for i in range(0, len(guides), cols):
        g, r = guides[i : i + cols], redraws[i : i + cols]
        blank = [np.full_like(guides[0], 255)] * (cols - len(g))
        images += g + blank + r + blank
    return tile(images, cols=cols)


def _action_sort_key(name: str) -> tuple[int, str]:
    order = config.ACTION_ORDER
    return (order.index(name) if name in order else len(order), name)


def build_package(root: Path, ch: Character) -> Path:
    """(Re)build actsprite_<name>/ and its ZIP from every finished action in root/work; returns the ZIP."""
    done = sorted((p.parent for p in (root / "work").glob("*/result.json")), key=lambda d: _action_sort_key(d.name))
    if not done:
        raise PipelineError(f"No finished action in {root / 'work'}: run one action first.")
    results = [json.loads((d / "result.json").read_text(encoding="utf-8")) for d in done]
    cells = [[np.asarray(Image.open(p).convert("RGBA")) for p in sorted((d / "cells").glob("*.png"))] for d in done]

    name = ch.name
    pkg = root / f"actsprite_{name}"
    if pkg.exists():
        shutil.rmtree(pkg)  # generated output only: rebuilt from work/ every time
    save_rgba(pkg / f"{name}_sheet.png", sheet_from_rows(cells))
    h, w = cells[0][0].shape[:2]
    (pkg / f"{name}_meta.json").write_text(json.dumps(character_meta(name, ch.style, (w, h), results), indent=2),
                                           encoding="utf-8")
    for res, row in zip(results, cells):
        for k, cell in enumerate(row):
            save_rgba(pkg / "frames" / res["name"] / f"{res['name']}_{k:02d}.png", cell)
        preview_gif(row, pkg / "preview" / f"{res['name']}.gif", res["fps"])
    _write_scores(pkg / "report" / "scores.csv", done)
    (pkg / "report" / "summary.md").write_text(_summary_md(name, ch.style, results), encoding="utf-8")
    (pkg / "reference").mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "work" / "sheet.png", pkg / "reference" / "character_sheet.png")
    if any(r.get("view") == "front" for r in results) and (root / "work" / "sheet_front.png").exists():
        shutil.copy2(root / "work" / "sheet_front.png", pkg / "reference" / "character_sheet_front.png")
    if config.UNITY_IMPORTER.exists():
        (pkg / "unity").mkdir(exist_ok=True)
        shutil.copy2(config.UNITY_IMPORTER, pkg / "unity" / config.UNITY_IMPORTER.name)
    return Path(shutil.make_archive(str(root / pkg.name), "zip", root_dir=root, base_dir=pkg.name))


def _write_scores(path: Path, action_dirs: list[Path]) -> None:
    rows = []
    for d in action_dirs:
        with (d / "scores.csv").open(encoding="utf-8") as f:
            rows += [{"action": d.name, **r} for r in csv.DictReader(f)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)


def _summary_md(name: str, style: str, results: list[dict]) -> str:
    lines = [f"# {name} ({style})", "",
             "| Action | Frames passed | Attempts | Frames to check by hand | Time | Spend | Meta API calls: new / cached |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    rebuilt = []
    for r in results:
        check = ", ".join(str(k) for k, ok in enumerate(r["passed"]) if not ok) or "none"
        calls = r.get("api_calls") or {}
        lines.append(f"| {r['name']} | {sum(r['passed'])}/{r['frames']} | {r['attempts']} | {check} | "
                     f"{r['seconds'] / 60:.1f} min | ${r['spent_usd']:.2f} | "
                     f"{calls.get('new', '?')} / {calls.get('cached', '?')} |")
        if calls and calls.get("new") == 0:
            rebuilt.append(r["name"])
    lines += ["", f"Total spend: ${sum(r['spent_usd'] for r in results):.2f} (cached calls are free)."]
    if rebuilt:
        lines += ["", f"Rebuilt from the API cache with no new Meta API calls: {', '.join(rebuilt)}. Their time and "
                      "spend are those of the rebuild, not of a first run (see the project README for measured runs)."]
    lines += ["",
              "A frame passes when its silhouette matches the pose guide (SAM 3.1), the Muse Spark critic scores "
              "pose and identity at least 7, its colours stay on the sheet palette and its legs moved like the "
              "actor's. A frame to check did not pass every check after the redraws; the best attempt is used.", ""]
    return "\n".join(lines)


def run(video: Path, root: Path, action: str, ch: Character, **kwargs) -> tuple[dict, Path]:
    """One action end to end, then the character's package; returns (the action's result, the ZIP)."""
    result = run_action(video, root, action, ch, **kwargs)
    return result, build_package(root, ch)

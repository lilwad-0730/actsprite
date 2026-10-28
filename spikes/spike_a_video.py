"""Spike A: SAM 3.1 video tracking on real phone clips.

Each clip is re-encoded for SAM (MPEG-4 MP4, short side <= 720 px, <= 30 fps) so the
upload stays small and our frame indices match SAM's. Then one SAM video call per clip.
Saves the main track's masks (track.npz) for the align/keyframe step.

Run: .venv\Scripts\python -m spikes.spike_a_video samples/jump.MOV:person samples/cat.mp4:cat
Cost: $0.0002 per frame sent, at least 50 frames per clip (16 s @ 30 fps ~ $0.10).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from actsprite import config
from actsprite.capture import edge_contact, full_body_range, main_track, parse_sam_output, prepare_video, read_frames
from actsprite.meta_client import MetaClient, estimate_sam_video_cost
from spikes.common import OUT, estimate, save_rgb, tile, write_json


def overlay(rgb: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    out = rgb.copy()
    if mask is not None:
        out[mask] = (0.5 * out[mask] + 0.5 * np.array([60, 200, 90])).astype(np.uint8)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", help="path:prompt, e.g. samples/jump.MOV:person")
    ap.add_argument("--fps", type=float, default=config.SAM_VIDEO_FPS)
    ap.add_argument("--short-side", type=int, default=config.SAM_VIDEO_MAX_SHORT_SIDE)
    ap.add_argument("--tag", default="", help="suffix for the output folder")
    args = ap.parse_args()
    client = MetaClient()
    summary = []
    for spec in args.clips:
        path_str, _, prompt = spec.rpartition(":")
        src = Path(path_str)
        out = OUT / "a_video" / (src.stem.lower() + args.tag)
        pv = prepare_video(src, out / "sam_input.mp4", target_fps=args.fps, max_short_side=args.short_side)
        data = pv.path.read_bytes()
        estimate(f"SAM video {src.name} ({pv.frame_count} frames, {len(data) / 1e6:.1f} MB)",
                 estimate_sam_video_cost(pv.frame_count))

        text, res = client.segment(data, prompt, video_frame_count=pv.frame_count, note=f"spikeA {src.name}")
        objs = parse_sam_output(text, pv.size, video=True)
        track = main_track(objs)
        n = pv.frame_count
        per_frame_top: list[str] = []
        for i in range(n):
            here = [o for o in objs if o.frame_index == i]
            if here:
                per_frame_top.append(max(here, key=lambda o: o.area).object_id)
        switches = sum(a != b for a, b in zip(per_frame_top, per_frame_top[1:]))
        usable = full_body_range(track, n)
        lo, hi = usable if usable else (0, n)
        edges = {e: sum(e in edge_contact(track[i].mask) for i in range(lo, hi) if i in track)
                 for e in ("top", "bottom", "left", "right")}
        near_bottom = []  # lowest mask row distance to the frame bottom, inside the usable range
        for i in range(lo, hi):
            if i in track:
                ys = np.nonzero(track[i].mask)[0]
                near_bottom.append(pv.size[1] - 1 - int(ys.max()))

        found = np.array([i in track for i in range(n)])
        masks = np.zeros((n, pv.size[1], pv.size[0]), bool)
        for i, o in track.items():
            masks[i] = o.mask
        np.savez_compressed(out / "track.npz", masks=masks, found=found, fps=pv.fps,
                            source_indices=np.array(pv.source_indices), usable=np.array(usable or (-1, -1)))

        frames = read_frames(pv.path)
        picks = np.linspace(0, n - 1, 16).astype(int)
        save_rgb(out / "contact.png",
                 tile([overlay(frames[i], track[i].mask if i in track else None) for i in picks], cols=8, cell=(320, 180)))
        if usable:
            picks = np.linspace(lo, hi - 1, 16).astype(int)
            save_rgb(out / "contact_usable.png",
                     tile([overlay(frames[i], track[i].mask) for i in picks], cols=8, cell=(320, 180)))
        row = {
            "clip": src.name, "prompt": prompt, "frames": n, "fps": round(pv.fps, 2),
            "size": f"{pv.size[0]}x{pv.size[1]}", "upload_mb": round(len(data) / 1e6, 2),
            "frames_with_any_mask": round(len({o.frame_index for o in objs}) / n, 3),
            "main_track_coverage": round(len(track) / n, 3),
            "distinct_ids": len({o.object_id for o in objs}),
            "largest_id_switches": switches,
            "usable_frames": [lo, hi] if usable else None,
            "usable_seconds": round((hi - lo) / pv.fps, 2) if usable else 0,
            "usable_edge_contacts": edges,
            "feet_to_bottom_px_min": min(near_bottom) if near_bottom else None,
            "latency_s": round(res.latency_s, 1), "cost_usd": round(res.cost_usd, 4), "cached": res.cached,
        }
        row["pass"] = usable is not None and all(i in track for i in range(lo, hi))
        summary.append(row)
        print(row)
    write_json(OUT / "a_video" / f"summary{args.tag}_{Path(args.clips[0].rpartition(':')[0]).stem.lower()}.json",
               {"clips": summary, "spent_total_usd": round(client.cost_log.total(), 4)})


if __name__ == "__main__":
    main()

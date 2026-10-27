"""Spike A: SAM 3.1 video tracking on real phone clips.

Each clip is re-encoded to MP4 (MPEG-4, short side <= 720 px, same fps) so the
upload stays small and our frame indices match SAM's. Then one SAM video call.

Run: .venv\\Scripts\\python -m spikes.spike_a_video samples/run.mp4:person samples/cat.mp4:cat
Cost: $0.0002 per frame, at least 50 frames per clip (5 s @ 30 fps ~ $0.03).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from actsprite.capture import main_track, parse_sam_output, read_frames, video_info
from actsprite.meta_client import MetaClient, estimate_sam_video_cost
from spikes.common import OUT, estimate, save_rgb, tile, write_json

MAX_SHORT_SIDE = 720


def reencode(src: Path, dst: Path) -> tuple[int, tuple[int, int], float]:
    fps, _, (w, h) = video_info(src)
    scale = min(1.0, MAX_SHORT_SIDE / min(w, h))
    size = (int(w * scale) // 2 * 2, int(h * scale) // 2 * 2)
    dst.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    n = 0
    for rgb in read_frames(src):
        writer.write(cv2.cvtColor(cv2.resize(rgb, size, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR))
        n += 1
    writer.release()
    return n, size, fps


def overlay(rgb: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    out = rgb.copy()
    if mask is not None:
        out[mask] = (0.5 * out[mask] + 0.5 * np.array([60, 200, 90])).astype(np.uint8)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+", help="path:prompt, e.g. samples/run.mp4:person")
    args = ap.parse_args()
    client = MetaClient()
    summary = []
    for spec in args.clips:
        path_str, _, prompt = spec.rpartition(":")
        src = Path(path_str)
        out = OUT / "a_video" / src.stem
        mp4 = out / f"{src.stem}_sam.mp4"
        n, size, fps = reencode(src, mp4)
        data = mp4.read_bytes()
        estimate(f"SAM video {src.name} ({n} frames)", estimate_sam_video_cost(n))

        text, res = client.segment(data, prompt, video_frame_count=n, note=f"spikeA {src.name}")
        objs = parse_sam_output(text, size, video=True)
        track = main_track(objs)
        per_frame_top: list[str] = []
        for i in range(n):
            here = [o for o in objs if o.frame_index == i]
            if here:
                per_frame_top.append(max(here, key=lambda o: o.area).object_id)
        switches = sum(a != b for a, b in zip(per_frame_top, per_frame_top[1:]))

        frames = read_frames(mp4)
        picks = np.linspace(0, len(frames) - 1, 8).astype(int)
        save_rgb(out / "contact.png",
                 tile([overlay(frames[i], track[i].mask if i in track else None) for i in picks], cols=8))
        row = {
            "clip": src.name, "prompt": prompt, "frames": n, "fps": round(fps, 2), "size": f"{size[0]}x{size[1]}",
            "upload_mb": round(len(data) / 1e6, 2),
            "frames_with_any_mask": round(len({o.frame_index for o in objs}) / n, 3),
            "main_track_coverage": round(len(track) / n, 3),
            "distinct_ids": len({o.object_id for o in objs}),
            "largest_id_switches": switches,
            "latency_s": round(res.latency_s, 1), "cost_usd": round(res.cost_usd, 4),
        }
        row["pass"] = row["main_track_coverage"] >= 0.9 and switches == 0
        summary.append(row)
        print(row)
    write_json(OUT / "a_video" / "summary.json",
               {"clips": summary, "spent_total_usd": round(client.cost_log.total(), 4)})


if __name__ == "__main__":
    main()

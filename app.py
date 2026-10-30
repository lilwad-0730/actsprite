"""ActSprite web app: the Hugging Face Space entry point.

Preview build (10/29): a showcase of finished sprites and a SAM 3.1 tracking check that also
measures how fast this machine decodes SAM masks. The full upload -> sprite sheet -> Unity
flow comes with stage 4 (11/1).

Run locally: .venv\\Scripts\\python app.py   (the tracking check needs META_API_KEY in .env)
"""

from __future__ import annotations

try:  # free Spaces run on ZeroGPU hardware; this app itself needs no GPU
    import spaces
except ImportError:  # local runs without the package
    spaces = None

import base64
import datetime as dt
import hashlib
import os
import tempfile
import threading
import time
from pathlib import Path

import cv2
import gradio as gr
import numpy as np

from actsprite import config
from actsprite.capture import main_track, parse_sam_output, prepare_video, read_frames
from actsprite.meta_client import BudgetExceeded, MetaClient, MissingApiKey

SHOWCASE = config.ROOT / "showcase"
SHOWCASE_ITEMS = [
    ("knight_attack", "Pixel knight - attack", "Phone clip of the author. 5 of 8 frames passed every check."),
    ("hound_walk", "Pixel hound - walk cycle",
     "Pexels clip by Luis Adolfo Burgos. One 22-frame stride, 10 frames at 15 fps. 4 of 10 frames passed "
     "every check."),
    ("lineman_attack", "Line-art man - attack",
     "Same attack clip, redrawn as a friend's line-art design. 10 frames at 15 fps; 6 of 10 passed."),
]
# Spaces sets CPU_CORES; os.cpu_count() can report the whole host inside a container.
WORKERS = max(1, int(os.environ.get("CPU_CORES") or os.cpu_count() or 1))

_usage_lock = threading.Lock()
_usage: dict[tuple[str, str], int] = {}


if spaces is not None:

    @spaces.GPU(duration=5)
    def _zerogpu_probe() -> str:
        """Never called. ZeroGPU expects one GPU function at startup; all real work here is CPU or remote."""
        return "ok"


def _visitor(request: gr.Request | None) -> str:
    """Salted hash of the visitor's address, used only for the daily limit (the raw address is not kept)."""
    if request is None:
        return "local"
    forwarded = request.headers.get("x-forwarded-for", "") if request.headers else ""
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    salt = os.environ.get("SPACE_SIGNING_SECRET", "actsprite")
    return hashlib.sha256((salt + ip).encode()).hexdigest()[:16]


def _take_slot(visitor: str, limit: int) -> bool:
    key = (visitor, dt.date.today().isoformat())
    with _usage_lock:
        if _usage.get(key, 0) >= limit:
            return False
        _usage[key] = _usage.get(key, 0) + 1
        return True


def _overlay_sheet(frames: list[np.ndarray], masks: dict[int, np.ndarray], count: int = 8) -> np.ndarray:
    """count evenly spaced frames with the tracked mask tinted green, 4 per row."""
    picks = np.linspace(0, len(frames) - 1, num=min(count, len(frames))).round().astype(int)
    cells = []
    for i in picks:
        rgb = frames[i].copy()
        m = masks.get(int(i))
        if m is not None:
            rgb[m] = (0.5 * rgb[m] + 0.5 * np.array([60, 200, 90])).astype(np.uint8)
        h, w = rgb.shape[:2]
        cells.append(cv2.resize(rgb, (320, round(320 * h / w)), interpolation=cv2.INTER_AREA))
    while len(cells) % 4:
        cells.append(np.full_like(cells[0], 255))
    return np.vstack([np.hstack(cells[r : r + 4]) for r in range(0, len(cells), 4)])


def track_check(video: str | None, prompt: str, request: gr.Request) -> tuple[np.ndarray, dict]:
    if not video:
        raise gr.Error("Upload a short MP4 or MOV clip first.")
    prompt = (prompt or "person").strip()[:40]
    if not _take_slot(_visitor(request), config.DEMO_SAM_CHECKS_PER_DAY):
        raise gr.Error(f"Daily limit reached ({config.DEMO_SAM_CHECKS_PER_DAY} checks per visitor). Try tomorrow.")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            # Per-request cache in the temp folder, so nothing derived from the upload outlives the check.
            # The cost log is shared, so the Space-wide spend cap holds across visitors.
            client = MetaClient(cache_dir=Path(tmp) / "cache", budget_usd=config.DEMO_SPEND_CAP_USD)
        except MissingApiKey as e:
            raise gr.Error("This Space has no META_API_KEY secret yet.") from e
        t0 = time.perf_counter()
        pv = prepare_video(Path(video), Path(tmp) / "sam_input.mp4", target_fps=config.DEMO_SAM_FPS,
                           max_seconds=config.DEMO_MAX_CLIP_S)
        frames = read_frames(pv.path)
        prep_s = time.perf_counter() - t0
        try:
            text, res = client.segment(pv.path.read_bytes(), prompt, video_frame_count=pv.frame_count,
                                       note="space tracking check")
        except BudgetExceeded as e:
            raise gr.Error("This demo has used its Meta API budget. The showcase still works.") from e
        t1 = time.perf_counter()
        objects = parse_sam_output(text, pv.size, video=True, workers=WORKERS)
        parse_s = time.perf_counter() - t1
    track = main_track(objects)
    sheet = _overlay_sheet(frames, {i: o.mask for i, o in track.items()})
    stats = {
        "frames_sent": pv.frame_count,
        "size": f"{pv.size[0]}x{pv.size[1]}",
        "fps": round(pv.fps, 2),
        "frames_with_mask": f"{len(track)}/{pv.frame_count}",
        "object_ids": len({o.object_id for o in objects}),
        "sam_api_seconds": round(res.latency_s, 1),
        "mask_decode_seconds": round(parse_s, 1),
        "decode_seconds_per_frame": round(parse_s / max(1, pv.frame_count), 2),
        "prepare_seconds": round(prep_s, 1),
        "decode_workers": WORKERS,
        "cost_usd": round(res.cost_usd, 4),
    }
    return sheet, stats


def system_info() -> dict:
    return {
        "space": os.environ.get("SPACE_ID", "local"),
        "accelerator": os.environ.get("ACCELERATOR", "n/a"),
        "cpu_cores_env": os.environ.get("CPU_CORES", "n/a"),
        "memory_env": os.environ.get("MEMORY", "n/a"),
        "os_cpu_count": os.cpu_count(),
        "decode_workers": WORKERS,
        "api_key_set": bool(os.environ.get(config.API_KEY_ENV)),
        "spend_cap_usd": config.DEMO_SPEND_CAP_USD,
    }


def showcase_html() -> str:
    def b64(path: Path) -> str:
        return base64.b64encode(path.read_bytes()).decode()

    cards = []
    for name, title, note in SHOWCASE_ITEMS:
        gif, strip = SHOWCASE / f"{name}.gif", SHOWCASE / f"{name}_strip.png"
        cards.append(
            f'<div style="margin-bottom:24px"><h3 style="margin:0 0 4px">{title}</h3>'
            f'<p style="margin:0 0 8px;opacity:.8">{note}</p>'
            f'<img src="data:image/gif;base64,{b64(gif)}" width="192" height="192" '
            f'style="image-rendering:pixelated;background:#ebebeb;border-radius:6px;margin-right:12px" alt="{title} loop">'
            f'<img src="data:image/png;base64,{b64(strip)}" style="max-width:100%;height:96px;'
            f'image-rendering:pixelated;background:#ebebeb;border-radius:6px" alt="{title} sprite strip"></div>'
        )
    return "".join(cards)


HEADER = """# ActSprite - Act it out. Play it in.
Act out a move on your phone and get a consistent, game-ready animated character for Unity.
Three Meta models: **SAM 3.1** tracks you, **Muse Image** redraws each pose as your character,
**Muse Spark 1.3** and SAM check every frame and send drifting ones back for a redraw.

*Preview build (Oct 29): showcase and a tracking check. The full upload -> sprite sheet -> Unity flow arrives Nov 1.*
Source: [github.com/lilwad-0730/actsprite](https://github.com/lilwad-0730/actsprite)"""

NOTICE = f"""Clips you upload are sent to the **Meta Model API (SAM 3.1)** for segmentation.
Only the first {config.DEMO_MAX_CLIP_S:.0f} seconds are used, at {config.DEMO_SAM_FPS} fps.
Uploads are deleted within an hour; tracking results are not stored.
Limit: {config.DEMO_SAM_CHECKS_PER_DAY} checks per visitor per day. Best results: side view, whole body in frame."""

with gr.Blocks(title="ActSprite", delete_cache=(3600, 3600)) as demo:
    gr.Markdown(HEADER)
    with gr.Tab("Showcase"):
        gr.HTML(showcase_html())
    with gr.Tab("Tracking check"):
        gr.Markdown(NOTICE)
        with gr.Row():
            with gr.Column():
                video_in = gr.Video(label="Phone clip (MP4 or MOV)", sources=["upload"])
                prompt_in = gr.Textbox(value="person", label="What to track (a short noun, e.g. person, dog)")
                run_btn = gr.Button("Track with SAM 3.1", variant="primary")
            with gr.Column():
                sheet_out = gr.Image(label="Tracked frames", type="numpy")
                stats_out = gr.JSON(label="Numbers")
        run_btn.click(track_check, [video_in, prompt_in], [sheet_out, stats_out], concurrency_limit=1)
    with gr.Tab("Space info"):
        gr.JSON(value=system_info, label="Runtime")

demo.queue(max_size=config.DEMO_QUEUE_SIZE)

if __name__ == "__main__":
    demo.launch()

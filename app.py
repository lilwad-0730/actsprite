"""ActSprite web app: the Hugging Face Space entry point.

Make a sprite in three checked steps (spec 5: three checkpoints):
  1. Track: SAM 3.1 follows the actor, the keyframes and their pose guides are chosen (one SAM call).
  2. First frame: Muse Image draws frame 0, Muse Spark and SAM check it (about one image's cost).
  3. All frames: the rest are drawn and checked, then the overview and the ZIP for Unity.
Plus the showcase of finished sprites. Settings are locked to tested defaults on the web; the command line
(`python -m actsprite --help`) has them all.

Run locally: .venv\\Scripts\\python app.py   (needs META_API_KEY in .env)
"""

from __future__ import annotations

try:  # free Spaces run on ZeroGPU hardware; this app itself needs no GPU
    import spaces
except ImportError:  # local runs without the package
    spaces = None

import base64
import datetime as dt
import hashlib
import math
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path

import gradio as gr
import numpy as np
from PIL import Image, ImageDraw

from actsprite import config
from actsprite.capture import prepare_video
from actsprite.characters import PRESETS, custom_character
from actsprite.errors import PipelineError
from actsprite.images import tile
from actsprite.meta_client import BudgetExceeded, CostLog, MetaClient, MissingApiKey
from actsprite.pipeline import ActionPlan, build_package, draw_first_frame, finish_action, plan_action
from actsprite.redraw import TRY_EST_USD
from actsprite.restyle import BODIES, STYLES

SHOWCASE = config.ROOT / "showcase"
SHOWCASE_ITEMS = [
    ("knight_run", "Pixel knight - run cycle",
     "Phone clip of the author. One stride, 8 frames at 12 fps. 7 of 8 frames passed every check."),
    ("hound_walk", "Pixel hound - walk cycle",
     "Pexels clip by Luis Adolfo Burgos. One 22-frame stride, 10 frames at 15 fps. 4 of 10 frames passed "
     "every check."),
    ("lineman_run", "Line-art man - run cycle",
     "The author's run clip, redrawn as a friend's line-art design. One stride, 20 frames at 20 fps; "
     "16 of 20 passed every check.", 2),
]  # (name, title, note[, rows in the strip image])
# Spaces sets CPU_CORES; os.cpu_count() can report the whole host inside a container.
WORKERS = max(1, int(os.environ.get("CPU_CORES") or os.cpu_count() or 1))
WEB_ROOT = Path(tempfile.gettempdir()) / "actsprite_web"  # one folder per visit, deleted after KEEP_S
KEEP_S = 3600

OWN = "My own design"
CHARACTERS = {
    "Pixel knight": replace(PRESETS["knight"], sheet_path=str(config.ROOT / "characters" / "knight.png")),
    "Line-art man": PRESETS["lineman"],
    "Hound (for dog clips)": replace(PRESETS["hound"], sheet_path=str(config.ROOT / "characters" / "hound.png")),
}
NAMES = {"Pixel knight": "knight", "Line-art man": "lineman", "Hound (for dog clips)": "hound", OWN: "mychar"}
ACTIONS = {
    "idle - stand and breathe (loops)": "idle",
    "walk - one stride (loops)": "walk",
    "run - one stride (loops)": "run",
    "jump - plays once": "jump",
    "attack - plays once": "attack",
}

_usage_lock = threading.Lock()
_usage: dict[tuple[str, str, str], int] = {}
_sessions_lock = threading.Lock()
_sessions: dict[str, dict] = {}


if spaces is not None:

    @spaces.GPU(duration=5)
    def _zerogpu_probe() -> str:
        """Never called. ZeroGPU expects one GPU function at startup; all real work here is CPU or remote."""
        return "ok"


# ------------------------------------------------------------------ limits
def _visitor(request: gr.Request | None) -> str:
    """Salted hash of the visitor's address, used only for the daily limits (the raw address is not kept)."""
    if request is None:
        return "local"
    forwarded = request.headers.get("x-forwarded-for", "") if request.headers else ""
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    salt = os.environ.get("SPACE_SIGNING_SECRET", "actsprite")
    return hashlib.sha256((salt + ip).encode()).hexdigest()[:16]


def _used(kind: str, visitor: str) -> int:
    with _usage_lock:
        return _usage.get((kind, visitor, dt.date.today().isoformat()), 0)


def _take_slot(kind: str, visitor: str, limit: int) -> bool:
    key = (kind, visitor, dt.date.today().isoformat())
    with _usage_lock:
        if _usage.get(key, 0) >= limit:
            return False
        _usage[key] = _usage.get(key, 0) + 1
        return True


def _quota(visitor: str) -> dict:
    spent = CostLog().total()
    return {
        "sprite_runs_left_today": max(0, config.DEMO_RUNS_PER_DAY - _used("run", visitor)),
        "tracking_steps_left_today": max(0, config.DEMO_SAM_CHECKS_PER_DAY - _used("track", visitor)),
        "space_budget_left_usd": round(max(0.0, config.DEMO_SPEND_CAP_USD - spent), 2),
    }


# ------------------------------------------------------------------ sessions
def _cleanup() -> None:
    """Delete visits older than KEEP_S: uploads and everything derived from them."""
    now = time.time()
    if WEB_ROOT.exists():
        for d in WEB_ROOT.iterdir():
            if d.is_dir() and now - d.stat().st_mtime > KEEP_S:
                shutil.rmtree(d, ignore_errors=True)
    with _sessions_lock:
        for sid in [s for s, v in _sessions.items() if not v["root"].exists()]:
            del _sessions[sid]


def _session(sid: str | None) -> dict:
    with _sessions_lock:
        s = _sessions.get(sid or "")
    if s is None or not s["root"].exists():
        raise gr.Error("This visit has expired (results are kept for an hour). Start again at step 1.")
    return s


def _own_character(png: str | None, style: str, body: str, faces_left: bool, root: Path):
    if not png:
        raise gr.Error("Upload your character design: one PNG or JPG, side view, whole body, plain background.")
    img = Image.open(png)
    if min(img.size) < 256:
        raise gr.Error(f"Your design is {img.size[0]}x{img.size[1]} px; use at least 256 px on each side.")
    flat = Image.new("RGB", img.size, (255, 255, 255))  # transparent PNGs: put the drawing on white
    rgba = img.convert("RGBA")
    flat.paste(rgba, mask=rgba.getchannel("A"))
    path = root / "design.png"
    flat.save(path)
    return custom_character("mine", sheet=path, body=body, style=style, faces_left=faces_left)


def _clean_name(text: str | None, default: str) -> str:
    """The name in the ZIP (actsprite_<name>.zip), its files and the Unity character: letters, digits, - and _."""
    name = re.sub(r"[^A-Za-z0-9_-]", "", (text or "").strip().replace(" ", "_"))[:32]
    return name or default


def output_style_notice(style: str) -> str:
    if STYLES[style].pixelate:
        return ("**Final output for this run: pixel art.** Uploaded designs are pixelated too; "
                "fine lines, facial features and clothing details will be reduced. The first-frame preview "
                "is shown before pixelation. For smooth artwork, choose **My own design → Output style → "
                "handdrawn** before Track; use **lineart** for a line drawing.")
    return (f"**Final output for this run: {style}, without pixelation.** "
            "The generated artwork is still resized to fit the exported sprite frames.")


# ------------------------------------------------------------------ panels
def _parameters(s: dict, visitor: str) -> dict:
    plan: ActionPlan = s["plan"]
    info, start = plan.info, s["start"]
    est = len(plan.guides) * TRY_EST_USD
    return {
        "name": s.get("name", plan.ch.name),
        "character": s["character"],
        "style": plan.ch.style,
        "action": plan.action,
        "mode (chosen from the action)": plan.mode,
        "settings_for_this_action": s["recipe"],
        "feet_planted": plan.legs_stay,
        "frames": len(plan.guides),
        "playback_fps": plan.play_fps,
        "sam_sample_fps": config.DEMO_SAM_FPS,
        "clip_part_used_seconds": [start, round(start + s["clip_seconds"], 2)],
        "edges_the_body_must_not_touch": list(plan.edges),
        "keyframes_at_seconds": [round(start + t, 2) for t in info["keyframe_seconds"]],
        "action_window_seconds": [round(start + i / plan.sam_fps, 2) for i in info["window"]],
        "checks": {
            "silhouette_iou_min": config.IOU_MIN,
            "pose_score_min": config.POSE_MIN,
            "identity_score_min": config.IDENTITY_MIN,
            "palette_drift_max": config.PALETTE_DRIFT_MAX,
            "redraws_per_frame_max": config.MAX_REGENERATIONS,
        },
        "cost_usd": {
            "estimate_all_frames": round(est, 2),
            "worst_case_all_frames": round(est * (config.MAX_REGENERATIONS + 1), 2),
            "spent_this_visit": round(plan.client.cost_log.total() - s["spent_at_start"], 4),
        },
        "quota": _quota(visitor),
    }


def _gif_html(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode()
    return (f'<img src="data:image/gif;base64,{b64}" width="256" height="256" alt="animation preview" '
            'style="image-rendering:pixelated;background:#ebebeb;border-radius:6px">')


def _frame_grid(cells: list[Path], passed: list[bool]) -> np.ndarray:
    """Every cell on light grey with a green (passed) or amber (check by hand) bar and its number."""
    out = []
    for k, (p, ok) in enumerate(zip(cells, passed)):
        cell = Image.open(p).convert("RGBA").resize((160, 160), Image.NEAREST)
        card = Image.new("RGB", (160, 176), (235, 235, 235))
        card.paste(cell, (0, 0), cell)
        d = ImageDraw.Draw(card)
        d.rectangle([0, 160, 159, 175], fill=(60, 170, 90) if ok else (230, 160, 40))
        d.text((6, 162), f"{k}  {'passed' if ok else 'check by hand'}", fill=(255, 255, 255))
        out.append(np.asarray(card))
    return tile(out, cols=4)


# ------------------------------------------------------------------ steps
def step_track(video, char_label, own_png, style, body, faces_left, action_label, actor, start, end,
               request: gr.Request):
    if not video:
        raise gr.Error("Upload a phone clip (MP4 or MOV) first.")
    try:
        start = float(start or 0)
        end = None if end in (None, "") else float(end)
    except (TypeError, ValueError) as e:
        raise gr.Error("Start at and End at must be finite numbers.") from e
    if not math.isfinite(start) or (end is not None and not math.isfinite(end)):
        raise gr.Error("Start at and End at must be finite numbers.")
    start = max(0.0, start)
    if end is not None and not start < end <= start + config.DEMO_MAX_CLIP_S:
        raise gr.Error(f"End at must be after Start at and at most {config.DEMO_MAX_CLIP_S:.0f} s later "
                       "(or empty).")
    visitor = _visitor(request)
    if not _take_slot("track", visitor, config.DEMO_SAM_CHECKS_PER_DAY):
        raise gr.Error(f"Daily limit reached ({config.DEMO_SAM_CHECKS_PER_DAY} tracking steps per visitor). "
                       "Try tomorrow, or look at the showcase.")
    _cleanup()
    sid = uuid.uuid4().hex
    root = WEB_ROOT / sid
    root.mkdir(parents=True)
    ch = _own_character(own_png, style, body, faces_left, root) if char_label == OWN else CHARACTERS[char_label]
    action = ACTIONS[action_label]
    recipe = config.DEMO_RECIPES[action]
    actor = (actor or "person").strip()[:40]
    try:
        client = MetaClient(cache_dir=root / "cache", budget_usd=config.DEMO_SPEND_CAP_USD)
    except MissingApiKey as e:
        raise gr.Error("This Space has no META_API_KEY secret yet.") from e
    spent_at_start = client.cost_log.total()
    try:
        pv = prepare_video(Path(video), root / "clip.mp4", target_fps=config.DEMO_SAM_FPS,
                           max_seconds=config.DEMO_MAX_CLIP_S if end is None else end - start,
                           start_seconds=start)
    except (ValueError, FileNotFoundError) as e:
        raise gr.Error(str(e)) from e
    whole = bool(recipe.get("span")) and end is not None  # jump/attack with an end time: the whole part
    frames = min(recipe["frames"], max(2, pv.frame_count - 1)) if whole else recipe["frames"]
    kwargs = dict(actor=actor, mode="span" if whole else None, frames=frames, fps=recipe.get("fps"),
                  feet_planted=recipe.get("feet_planted", False), sample_fps=config.DEMO_SAM_FPS, client=client)
    try:
        try:
            plan = plan_action(pv.path, root, action, ch, **kwargs)
        except PipelineError:
            # Phone clips often cut the feet or head at the frame edge, which leaves no whole-body stretch or
            # too short a one to find a loop: allow the top and bottom edges once (the track is cached).
            plan = plan_action(pv.path, root, action, ch, edges=("left", "right"), **kwargs)
    except PipelineError as e:
        raise gr.Error(str(e)) from e
    except BudgetExceeded as e:
        raise gr.Error("This demo has used its Meta API budget. The showcase still works.") from e
    s = {"plan": plan, "root": root, "character": char_label, "start": start, "first": False, "slot": False,
         "recipe": recipe, "whole": whole,
         "clip_seconds": pv.frame_count / pv.fps, "spent_at_start": spent_at_start}
    with _sessions_lock:
        _sessions[sid] = s
    guides = tile([g for g, _ in plan.guides], cols=4)
    n, info = len(plan.guides), plan.info
    note = (f"**{n} keyframes** between {start + info['keyframe_seconds'][0]:.2f} s and "
            f"{start + info['keyframe_seconds'][-1]:.2f} s of your clip, played at {plan.play_fps} fps. "
            "These grey silhouettes are all Muse Image will see of you. If the pose is wrong, change the start "
            "time or the clip and track again; otherwise draw the first frame. "
            f"Step 3 costs about ${n * TRY_EST_USD:.2f}.")
    note += "\n\n" + output_style_notice(plan.ch.style)
    if recipe.get("span") and not whole:
        note += (" **Tip:** set *End at* to where the move ends, so the whole move is used (for a jump: "
                 "from takeoff to standing again); without it the most active part is picked.")
    if action == "attack":
        note += " **Known limitation:** narrow punch stances can still be redrawn as wide lunges."
    return sid, guides, note, _parameters(s, visitor), gr.update(interactive=True), gr.update(interactive=False)


def step_first(sid, request: gr.Request):
    s = _session(sid)
    visitor = _visitor(request)
    if not s["slot"]:
        if not _take_slot("run", visitor, config.DEMO_RUNS_PER_DAY):
            raise gr.Error(f"Daily limit reached ({config.DEMO_RUNS_PER_DAY} sprites per visitor). Try tomorrow.")
        s["slot"] = True
    try:
        rows, rgb = draw_first_frame(s["plan"])
    except PipelineError as e:
        raise gr.Error(str(e)) from e
    except BudgetExceeded as e:
        raise gr.Error("This demo has used its Meta API budget. The showcase still works.") from e
    s["first"] = True
    best = next(r for r in rows if r.get("chosen"))
    verdict = "passed every check" if best["passed"] else f"did not pass: {best['failures']}"
    note = (f"Frame 0 {verdict} (silhouette match {best['iou']:.2f}, pose {best['pose']:.0f}/10, "
            f"looks like the character {best['identity']:.0f}/10, {len(rows)} attempt(s)). Every other frame is "
            "drawn to match this one. If it looks wrong, try another clip part or character; otherwise draw all.")
    note += "\n\n" + output_style_notice(s["plan"].ch.style)
    return rgb, note, _parameters(s, visitor), gr.update(interactive=True)


def _pack(s: dict, name: str | None, visitor: str) -> tuple[Path, dict]:
    """(Re)build the ZIP under the chosen name: no Meta API calls."""
    plan: ActionPlan = s["plan"]
    s["name"] = _clean_name(name, plan.ch.name)
    params = _parameters(s, visitor)
    return build_package(s["root"], replace(plan.ch, name=s["name"]), parameters=params), params


def step_finish(sid, name, request: gr.Request, progress=gr.Progress()):
    s = _session(sid)
    if not s["first"]:
        raise gr.Error("Draw the first frame (step 2) first.")
    plan: ActionPlan = s["plan"]
    progress(0.05, desc=f"Drawing and checking {len(plan.guides) - 1} more frames (about 2-4 minutes)")
    try:
        result = finish_action(plan)
    except PipelineError as e:
        raise gr.Error(str(e)) from e
    except BudgetExceeded as e:
        raise gr.Error("This demo has used its Meta API budget. The showcase still works.") from e
    progress(0.95, desc="Packing the ZIP")
    zip_path, params = _pack(s, name, _visitor(request))
    s["finished"] = True
    pkg = zip_path.with_suffix("")
    cells = sorted((plan.work / "cells").glob("*.png"))
    passed = result["passed"]
    summary = (f"**{sum(passed)} of {len(passed)} frames passed every check** "
               f"({result['attempts']} drawings in all, ${params['cost_usd']['spent_this_visit']:.2f} in Meta API "
               f"calls, {result['seconds'] / 60:.1f} min). Amber frames did not pass after "
               f"{config.MAX_REGENERATIONS} redraws; the best attempt is used, so look at them. "
               "Unity: install the importer from the repo (unity/ActSpriteImporter), then ActSprite > Import ZIP.")
    return (_gif_html(pkg / "preview" / f"{plan.action}.gif"), _frame_grid(cells, passed), summary,
            str(zip_path), params, gr.update(value=s["name"]), gr.update(interactive=True))


def rename_zip(sid, name, request: gr.Request):
    s = _session(sid)
    if not s.get("finished"):
        raise gr.Error("Finish step 3 first.")
    zip_path, params = _pack(s, name, _visitor(request))
    return str(zip_path), params, gr.update(value=s["name"])


def own_design_visible(label: str):
    own = label == OWN
    actor = "dog" if label.startswith("Hound") else "person"
    return gr.update(visible=own), gr.update(value=actor), gr.update(value=NAMES[label])


# ------------------------------------------------------------------ page
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
    for name, title, note, *rows in SHOWCASE_ITEMS:
        gif, strip = SHOWCASE / f"{name}.gif", SHOWCASE / f"{name}_strip.png"
        height = 96 * (rows[0] if rows else 1)  # every row of frames shows 96 px tall
        cards.append(
            f'<div style="margin-bottom:24px"><h3 style="margin:0 0 4px">{title}</h3>'
            f'<p style="margin:0 0 8px;opacity:.8">{note}</p>'
            f'<img src="data:image/gif;base64,{b64(gif)}" width="192" height="192" '
            f'style="image-rendering:pixelated;background:#ebebeb;border-radius:6px;margin-right:12px" alt="{title} loop">'
            f'<img src="data:image/png;base64,{b64(strip)}" style="max-width:100%;height:{height}px;'
            f'image-rendering:pixelated;background:#ebebeb;border-radius:6px" alt="{title} sprite strip"></div>'
        )
    return "".join(cards)


HEADER = """# ActSprite - Act it out. Play it in.
Act out a move on your phone and get a consistent, game-ready animated character for Unity.
Three Meta models: **SAM 3.1** tracks you, **Muse Image** redraws each pose as your character,
**Muse Spark 1.3** and SAM check every frame and send drifting ones back for a redraw.
Source and Unity importer: [github.com/lilwad-0730/actsprite](https://github.com/lilwad-0730/actsprite)"""

NOTICE = f"""**Before you upload.** Your clip and your character image are sent to the **Meta Model API**. While this
demo runs on hackathon credits, Meta may use uploads to improve its products. Muse Image only sees grey
silhouettes of you (the pose guides) and the character design, so your appearance never reaches the sprites.
Uploads and results are deleted from this Space within an hour.
**Limits:** up to {config.DEMO_MAX_CLIP_S:.0f} seconds of the clip (start to end), 8-16 frames depending on the action,
{config.DEMO_RUNS_PER_DAY} sprites and {config.DEMO_SAM_CHECKS_PER_DAY} tracking steps per visitor per day.
**Best results:** side view, the whole body in frame, a plain background, one move."""

LOCKED = """**Advanced settings: coming soon.** ActSprite is in an early stage, and this public demo runs on a limited
Meta Model API budget, so these settings are locked to tested defaults for now. Every option below already works in
the command-line version (`python -m actsprite --help`); they will open up here as the project grows."""


def _locked(component, flag: str):
    """A disabled field with its command-line flag as the tooltip line."""
    return component(interactive=False, info=f"Coming soon here. Command line: {flag}")


with gr.Blocks(title="ActSprite", delete_cache=(KEEP_S, KEEP_S)) as demo:
    gr.Markdown(HEADER)
    sid = gr.State(None)
    with gr.Tab("Make a sprite"):
        gr.Markdown(NOTICE)
        with gr.Row():
            with gr.Column(scale=1):
                video_in = gr.Video(label="Phone clip (MP4 or MOV)", sources=["upload"])
                with gr.Row():
                    start_in = gr.Number(value=0, minimum=0, label="Start at (seconds)",
                                         info=f"Up to {config.DEMO_MAX_CLIP_S:.0f} seconds from here are used.")
                    end_in = gr.Number(value=None, minimum=0, label="End at (seconds, optional)",
                                       info="Jump and attack: where the move ends. Empty for idle, walk, run.")
                action_in = gr.Dropdown(list(ACTIONS), value="run - one stride (loops)", label="Action")
                char_in = gr.Radio([*CHARACTERS, OWN], value="Pixel knight", label="Character")
                with gr.Group(visible=False) as own_box:
                    own_png = gr.Image(type="filepath", label="Your design: side view, whole body, facing right, "
                                                              "plain white background", sources=["upload"])
                    with gr.Row():
                        style_in = gr.Dropdown(sorted(STYLES), value="pixel", label="Output style",
                                               info="Applies to your uploaded design too. Default: pixel art. "
                                                    "Choose handdrawn or lineart before Track to avoid pixelation.")
                        body_in = gr.Dropdown(sorted(BODIES), value="biped", label="Body")
                    gr.Markdown("**Your design's final look:** `pixel` converts the result to pixel art and "
                                "reduces fine details. `handdrawn`, `lineart` and `ink` do not pixelate. "
                                "Choose before **1. Track**; changing this later requires tracking again.")
                    faces_left_in = gr.Checkbox(False, label="My design faces left (it will be mirrored)")
                actor_in = gr.Textbox(value="person", label="Who to track in the clip (a short noun)")
                with gr.Accordion("Advanced settings (coming soon)", open=False):
                    gr.Markdown(LOCKED)
                    _locked(lambda **k: gr.Textbox(value="idle 8, walk and run 16, jump 12, attack 10",
                                                   label="Frames", **k), "--frames 2-48")
                    _locked(lambda **k: gr.Textbox(value="idle 8, attack 15, walk/run/jump the clip's speed",
                                                   label="Playback fps", **k),
                            "--fps 1-30 or auto (the clip's own speed)")
                    _locked(lambda **k: gr.Slider(config.SAMPLE_FPS_MIN, config.SAMPLE_FPS_MAX,
                                                  value=config.DEMO_SAM_FPS, step=1, label="SAM 3.1 sample fps", **k),
                            "--sample-fps 1-60")
                    _locked(lambda **k: gr.Radio(["side", "front"], value="side", label="View", **k), "--view")
                    _locked(lambda **k: gr.Checkbox(False, label="Turn the head like the actor", **k),
                            "--head-turn")
                    _locked(lambda **k: gr.Textbox(value="off (the command line can plant them, e.g. for a punch)",
                                                   label="Feet stay planted", **k), "--feet-planted")
                    _locked(lambda **k: gr.Radio(["first", "previous"], value="first",
                                                 label="Each frame follows", **k), "--anchor")
                    _locked(lambda **k: gr.Textbox(value=f"start to end, at most {config.DEMO_MAX_CLIP_S:.0f} s",
                                                   label="Clip part", **k), "--start / --end (any part, any length)")
                track_btn = gr.Button("1. Track (SAM 3.1, about $0.02)", variant="primary")
            with gr.Column(scale=2):
                guides_out = gr.Image(label="Step 1: keyframes as pose guides", type="numpy")
                track_note = gr.Markdown()
                first_btn = gr.Button(f"2. Draw the first frame (about ${TRY_EST_USD:.2f})", interactive=False)
                with gr.Row():
                    first_out = gr.Image(label="Step 2: frame 0 (before final export processing)",
                                         type="numpy", height=280)
                    first_note = gr.Markdown()
                name_in = gr.Textbox(value="knight", max_length=32, label="Name",
                                     info="Names the ZIP (actsprite_<name>.zip), the files inside and the "
                                          "character in Unity. Letters, digits, - and _.")
                finish_btn = gr.Button("3. Draw all frames and pack the ZIP", variant="primary", interactive=False)
                with gr.Row():
                    gif_out = gr.HTML(label="Animation")
                    summary_out = gr.Markdown()
                grid_out = gr.Image(label="Step 3: every frame (green passed, amber check by hand)", type="numpy")
                with gr.Row():
                    zip_out = gr.File(label="ZIP for Unity", scale=3)
                    rename_btn = gr.Button("Rename the ZIP (free)", interactive=False, scale=1)
                params_out = gr.JSON(label="Parameters used (also in the ZIP: report/parameters.json)")
        char_in.change(own_design_visible, char_in, [own_box, actor_in, name_in])
        track_btn.click(step_track, [video_in, char_in, own_png, style_in, body_in, faces_left_in, action_in,
                                     actor_in, start_in, end_in],
                        [sid, guides_out, track_note, params_out, first_btn, finish_btn], concurrency_limit=1)
        first_btn.click(step_first, sid, [first_out, first_note, params_out, finish_btn], concurrency_limit=1)
        finish_btn.click(step_finish, [sid, name_in],
                         [gif_out, grid_out, summary_out, zip_out, params_out, name_in, rename_btn],
                         concurrency_limit=1)
        rename_btn.click(rename_zip, [sid, name_in], [zip_out, params_out, name_in])
    with gr.Tab("Showcase"):
        gr.HTML(showcase_html())
    with gr.Tab("Space info"):
        gr.JSON(value=system_info, label="Runtime")

demo.queue(max_size=config.DEMO_QUEUE_SIZE)

if __name__ == "__main__":
    demo.launch()

"""User options added 10/30: front view, frames per action, playback fps, part of the clip."""

import argparse

import numpy as np
import pytest

from actsprite import config
from actsprite.characters import PRESETS, Character, make_sheet
from actsprite.errors import PipelineError
from actsprite.images import png_bytes
from actsprite.restyle import STYLES, VIEWS, redraw_parts, sheet_prompt
from actsprite.sequence import choose_frames, clip_fps

# The Day 1 first-frame prompt, character for character: cached knight/hound/lineman calls depend on it.
DAY1_FIRST_FRAME = (
    "Redraw the character from image 1 in the EXACT pose of the pose guide (the last image). "
    "The pose guide is the only source of the pose: match the angle of every limb, where each foot and knee is, "
    "the arm positions and the body lean.\n"
    "Keep the character's design, outfit and colors identical to image 1.\n"
    "Full body, side view, facing right, feet touching the bottom edge like the pose guide.\n"
    f"Style: {STYLES['pixel'].prompt}. Plain solid white background, no shadow, no props, no text, no border.\n"
)


def test_side_view_prompt_is_unchanged():
    assert redraw_parts(b"S", b"G", None, "pixel")[-1] == DAY1_FIRST_FRAME
    assert redraw_parts(b"S", b"G", None, "pixel", view="side") == redraw_parts(b"S", b"G", None, "pixel")


def test_front_view_prompt():
    text = redraw_parts(b"S", b"G", b"P", "pixel", anchor=True, view="front")[-1]
    assert "front view, facing the viewer" in text and "side view" not in text
    with pytest.raises(ValueError):
        redraw_parts(b"S", b"G", None, "pixel", view="back")
    with pytest.raises(PipelineError):
        Character("x", "d", view="back")
    assert VIEWS == ("side", "front")


class FakeClient:
    def __init__(self):
        self.calls = []

    def generate_image(self, parts, note=""):
        self.calls.append(parts)
        img = np.full((64, 64, 3), 255, np.uint8)
        img[10:60, 25:40] = (40, 60, 200) if len(self.calls) == 1 else (200, 60, 40)
        return png_bytes(img), {}


def test_front_sheet_is_drawn_from_the_side_sheet():
    client = FakeClient()
    knight = PRESETS["knight"]
    side_png, _, _ = make_sheet(client, knight)
    assert client.calls[0] == [sheet_prompt(knight.description, knight.style, knight.body)]  # cached Day 1 call

    client = FakeClient()
    make_sheet(client, Character(**{**knight.__dict__, "view": "front"}))
    assert len(client.calls) == 2
    assert client.calls[1][1] == side_png and "seen from the front" in client.calls[1][-1]


def _standing(n=60, h=120, w=80) -> np.ndarray:
    masks = np.zeros((n, h, w), bool)
    for t in range(n):
        masks[t, 20:110, 30:50] = True
        masks[t, 30 + t % 10 : 40 + t % 10, 50:60] = True  # an arm that moves
    return masks


def test_span_takes_even_time_steps_over_the_clip_or_a_part():
    info, _ = choose_frames(_standing(), 30.0, "span", ("top", "bottom", "left", "right"), frames=6)
    assert info["keyframes"] == [0, 12, 24, 35, 47, 59]
    part, _ = choose_frames(_standing(), 30.0, "span", ("top", "bottom", "left", "right"), frames=4,
                            start=1.0, end=2.0)
    assert part["keyframes"][0] >= 30 and part["keyframes"][-1] < 60 and len(part["keyframes"]) == 4


def test_frames_and_part_are_checked():
    edges = ("top", "bottom", "left", "right")
    with pytest.raises(PipelineError):
        choose_frames(_standing(), 30.0, "span", edges, frames=config.FRAMES_MAX + 1)
    with pytest.raises(PipelineError):
        choose_frames(_standing(), 30.0, "span", edges, frames=12, start=1.0, end=1.2)  # 6 frames left
    with pytest.raises(PipelineError):
        choose_frames(_standing(), 30.0, "span", edges, start=5.0)  # after the end of the clip


def test_clip_speed():
    assert clip_fps({"keyframes": [0, 12, 24, 35, 47, 59]}, 30.0, "span") == pytest.approx(2.5)
    assert clip_fps({"keyframes": list(range(0, 20, 5)), "cycle_frames": 20}, 30.0, "loop") == 6.0
    assert clip_fps({"keyframes": [0, 1]}, 120.0, "once") == config.FPS_MAX  # clamped


def test_playback_fps_defaults_and_limits():
    from actsprite.pipeline import playback_fps

    info = {"keyframes": [0, 12, 24, 35, 47, 59]}
    assert playback_fps(None, info, 30.0, "once") == 15 and isinstance(playback_fps(None, info, 30.0, "once"), int)
    assert playback_fps(None, info, 30.0, "loop") == 8
    assert playback_fps(None, info, 30.0, "span") == pytest.approx(2.5)
    assert playback_fps("auto", info, 30.0, "once") == pytest.approx(2.5)
    assert playback_fps(7.5, info, 30.0, "once") == 7.5
    with pytest.raises(PipelineError):
        playback_fps(100.0, info, 30.0, "once")


def test_cli_options():
    from actsprite.__main__ import _fps, parse_args

    assert _fps("auto") == "auto" and _fps("7.5") == 7.5
    for bad in ("0", "fast"):
        with pytest.raises(argparse.ArgumentTypeError):
            _fps(bad)
    args = parse_args(["d.mp4", "--action", "dance", "--mode", "span", "--view", "front", "--frames", "16",
                       "--fps", "auto", "--end", "2"])
    assert (args.view, args.frames, args.fps, args.end, args.start) == ("front", 16, "auto", 2.0, None)
    assert parse_args(["a.mov", "--action", "attack"]).view == "side"


def test_compare_sheet_wraps_long_actions():
    from actsprite.pipeline import compare_sheet

    g = [np.full((32, 32, 3), 200, np.uint8)] * 16
    assert compare_sheet(g, g).shape == (4 * 256, 8 * 256, 3)  # guides/redraws row pairs, 8 per row
    assert compare_sheet(g[:8], g[:8]).shape == (2 * 256, 8 * 256, 3)  # 8 frames: as before


def test_frames_default_follows_the_action():
    from actsprite.__main__ import parse_args

    assert parse_args(["clip.mp4", "--action", "run"]).frames is None  # pipeline picks idle 8 / others 10
    assert config.FRAMES_IDLE == 8 and config.FRAMES_ACTION == 10 and config.FPS_ACTION == 15

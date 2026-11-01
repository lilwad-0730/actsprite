"""Web input and packaging checks; no Meta API calls."""
import json
import os
import zipfile
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from actsprite.sequence import ACTION_MODES

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
pytest.importorskip("gradio")
import app


@pytest.fixture
def web(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setattr(app, "WEB_ROOT", tmp_path)
    monkeypatch.setattr(app, "_sessions", {})
    monkeypatch.setattr(app, "_usage", {})
    client = SimpleNamespace(cost_log=SimpleNamespace(total=lambda: 0.0))
    monkeypatch.setattr(app, "MetaClient", lambda **kwargs: client)

    def prepare(src, dst, **kwargs):
        calls["clip"] = kwargs
        return SimpleNamespace(path=dst, fps=30.0, frame_count=60)

    def plan(video, root, action, ch, **kwargs):
        calls["plan"] = kwargs
        n = kwargs["frames"]
        return SimpleNamespace(ch=ch, client=client, action=action, legs_stay=False,
                               mode=kwargs["mode"] or ACTION_MODES[action],
                               play_fps=10 if kwargs["fps"] == "auto" else kwargs["fps"] or 8,
                               sam_fps=30, edges=("left", "right"),
                               guides=[(np.zeros((2, 2, 3), np.uint8), None)] * n,
                               info={"keyframe_seconds": [i / 30 for i in range(n)], "window": [0, 60]})

    monkeypatch.setattr(app, "prepare_video", prepare)
    monkeypatch.setattr(app, "plan_action", plan)
    return calls


@pytest.mark.parametrize("action,end,count,mode,fps", [
    ("idle", None, 8, "loop", None),
    ("run", None, 16, "gait", "auto"),
    ("walk", 3, 16, "gait", "auto"),
    ("jump", None, 12, "once", "auto"),
    ("jump", 3, 12, "span", "auto"),
    ("attack", 3, 10, "span", 15),
])
def test_web_time_range_and_action_settings(web, action, end, count, mode, fps):
    label = next(k for k, v in app.ACTIONS.items() if v == action)
    r = app.step_track("clip.mp4", "Pixel knight", None, "pixel", "biped", False,
                       label, "person", 1, end, None)
    assert web["clip"]["start_seconds"] == 1
    assert web["clip"]["max_seconds"] == (5 if end is None else 2)
    assert web["plan"]["sample_fps"] == 30
    assert web["plan"]["fps"] == fps and not web["plan"]["feet_planted"]
    assert r[3]["frames"] == count and r[3]["mode (chosen from the action)"] == mode


@pytest.mark.parametrize("start,end", [(1, 1), (1, 0), (1, 7), (float("inf"), None),
                                       (float("nan"), None), (0, float("inf")), (0, "bad")])
def test_invalid_times_do_not_use_tracking_quota_or_call_models(web, start, end):
    with pytest.raises(app.gr.Error):
        app.step_track("clip.mp4", "Pixel knight", None, "pixel", "biped", False,
                       "run - one stride (loops)", "person", start, end, None)
    assert not web and app._used("track", "local") == 0


@pytest.mark.parametrize("style", ["pixel", "handdrawn", "lineart", "ink"])
def test_uploaded_design_style_is_disclosed_before_drawing(web, tmp_path, monkeypatch, style):
    design = tmp_path / "design.png"
    Image.new("RGB", (256, 256), "white").save(design)
    r = app.step_track("clip.mp4", app.OWN, str(design), style, "biped", False,
                       "run - one stride (loops)", "person", 0, None, None)
    assert r[3]["style"] == style
    expected = "Final output for this run: pixel art" if style == "pixel" else f"{style}, without pixelation"
    assert expected in r[2]
    if style == "pixel":
        assert "Uploaded designs are pixelated too" in r[2] and "before pixelation" in r[2]
    # Repeat the style captured by Track before the batch drawing step.
    monkeypatch.setattr(app, "draw_first_frame", lambda plan: ([{
        "chosen": True, "passed": True, "iou": 1.0, "pose": 10, "identity": 10,
    }], np.zeros((2, 2, 3), np.uint8)))
    first = app.step_first(r[0], None)
    assert expected in first[1]


def test_rename_rebuilds_zip_names_and_metadata_without_model_calls(monkeypatch, tmp_path):
    from actsprite.characters import Character

    work = tmp_path / "work" / "run"
    (work / "cells").mkdir(parents=True)
    for i in range(2):
        Image.new("RGBA", (128, 128), (30, 40, 50, 255)).save(work / "cells" / f"{i:02d}.png")
    (work / "scores.csv").write_text("frame,attempt,passed,chosen\n0,0,True,True\n", encoding="utf-8")
    (work / "result.json").write_text(json.dumps({"name": "run", "frames": 2, "fps": 15, "loop": True,
        "passed": [True, True], "attempts": 2, "seconds": 1, "spent_usd": 0}), encoding="utf-8")
    Image.new("RGB", (16, 16), "white").save(tmp_path / "work" / "sheet.png")
    s = {"plan": SimpleNamespace(ch=Character("knight", "test character")), "root": tmp_path, "finished": True}
    monkeypatch.setattr(app, "_sessions", {"test": s})
    monkeypatch.setattr(app, "_parameters", lambda s, visitor: {"name": s["name"]})
    monkeypatch.setattr(app, "MetaClient", lambda **k: pytest.fail("Rename must not create a model client"))
    first, _, _ = app.rename_zip("test", "../knight renamed!", None)
    assert first.endswith("actsprite_knight_renamed.zip")
    with zipfile.ZipFile(first) as z:
        assert z.testzip() is None
        assert all(n.startswith("actsprite_knight_renamed/") for n in z.namelist())
        meta = json.loads(z.read("actsprite_knight_renamed/knight_renamed_meta.json"))
        assert meta["character"] == "knight_renamed" and meta["actions"][0]["frames"] == 2
    fallback, _, _ = app.rename_zip("test", "...", None)
    assert fallback.endswith("actsprite_knight.zip")
    assert app._clean_name("x" * 40, "knight") == "x" * 32

import json
import zipfile

import numpy as np
from PIL import Image

from actsprite.characters import Character
from actsprite.pipeline import build_package


def _fake_action(root, name, mode, frames, passed):
    work = root / "work" / name
    (work / "cells").mkdir(parents=True)
    for k in range(frames):
        cell = np.zeros((128, 128, 4), np.uint8)
        cell[40:128, 50:78] = (200, 40, 40, 255)
        Image.fromarray(cell, "RGBA").save(work / "cells" / f"{k:02d}.png")
    (work / "scores.csv").write_text("frame,attempt,passed,chosen,needs_review\n0,0,True,True,False\n",
                                     encoding="utf-8")
    result = {"name": name, "mode": mode, "frames": frames, "fps": 8 if mode == "loop" else 15,
              "loop": mode != "once", "passed": passed, "attempts": frames, "seconds": 60.0, "spent_usd": 0.5,
              "api_calls": {"new": 0 if name == "idle" else 24, "cached": 3}}
    (work / "result.json").write_text(json.dumps(result), encoding="utf-8")


def test_package_follows_the_output_contract(tmp_path):
    root = tmp_path / "knight"
    _fake_action(root, "jump", "once", 8, [True] * 7 + [False])
    _fake_action(root, "idle", "loop", 8, [True] * 8)
    Image.new("RGB", (64, 64), "white").save(root / "work" / "sheet.png")
    zip_path = build_package(root, Character("knight", "an original knight"))

    pkg = root / "actsprite_knight"
    meta = json.loads((pkg / "knight_meta.json").read_text(encoding="utf-8"))
    assert [a["name"] for a in meta["actions"]] == ["idle", "jump"]  # contract row order: idle, run, jump
    assert [a["row"] for a in meta["actions"]] == [0, 1] and meta["pivot"] == {"x": 0.5, "y": 0.0}
    assert Image.open(pkg / "knight_sheet.png").size == (8 * 128, 2 * 128)
    names = set(zipfile.ZipFile(zip_path).namelist())
    for f in ["knight_sheet.png", "knight_meta.json", "frames/jump/jump_07.png", "preview/idle.gif",
              "report/scores.csv", "report/summary.md", "reference/character_sheet.png"]:
        assert f"actsprite_knight/{f}" in names
    assert not any("/work/" in n for n in names)  # pose guides and attempts stay out of the ZIP
    summary = (pkg / "report" / "summary.md").read_text(encoding="utf-8")
    assert "| jump | 7/8 | 8 | 7 |" in summary and "| 24 / 3 |" in summary
    assert "Rebuilt from the API cache with no new Meta API calls: idle." in summary  # honest about replays
    scores = (pkg / "report" / "scores.csv").read_text(encoding="utf-8").splitlines()
    assert scores[0].startswith("action,frame") and len(scores) == 3


def test_front_view_sheet_goes_into_the_package(tmp_path):
    root = tmp_path / "knight"
    _fake_action(root, "dance", "span", 16, [True] * 16)
    result = json.loads((root / "work" / "dance" / "result.json").read_text(encoding="utf-8"))
    (root / "work" / "dance" / "result.json").write_text(json.dumps({**result, "view": "front", "fps": 7.5,
                                                                     "loop": False}), encoding="utf-8")
    Image.new("RGB", (64, 64), "white").save(root / "work" / "sheet.png")
    Image.new("RGB", (64, 64), "white").save(root / "work" / "sheet_front.png")
    zip_path = build_package(root, Character("knight", "an original knight"))
    names = set(zipfile.ZipFile(zip_path).namelist())
    assert "actsprite_knight/reference/character_sheet_front.png" in names
    meta = json.loads((root / "actsprite_knight" / "knight_meta.json").read_text(encoding="utf-8"))
    assert meta["actions"][0] == {"name": "dance", "row": 0, "frames": 16, "fps": 7.5, "loop": False}
    assert Image.open(root / "actsprite_knight" / "knight_sheet.png").size == (16 * 128, 128)

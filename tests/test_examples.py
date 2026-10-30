"""The finished examples in examples/ follow the output contract (docs/02_product_spec.md 4.2-4.3).
No API key and no network needed: this is what a judge can check in a minute."""

import csv
import io
import json
import zipfile

import pytest
from PIL import Image

from actsprite import config

EXAMPLES = sorted((config.ROOT / "examples").glob("actsprite_*.zip"))


def test_three_examples_are_bundled():
    assert [p.stem for p in EXAMPLES] == ["actsprite_hound", "actsprite_knight", "actsprite_lineman"]


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_follows_the_contract(path):
    z = zipfile.ZipFile(path)
    name = path.stem.removeprefix("actsprite_")
    top = f"actsprite_{name}/"
    names = {n for n in z.namelist() if not n.endswith("/")}  # files only (the ZIP also lists folders)
    assert all(n.startswith(top) for n in names)
    assert not any(w in n for n in names for w in ("guide", "work/", "sam_input"))  # nothing from the actor's video

    meta = json.loads(z.read(f"{top}{name}_meta.json"))
    assert set(meta) == {"character", "style", "cell", "pivot", "actions"} and meta["character"] == name
    assert meta["pivot"] == {"x": 0.5, "y": 0.0}
    w, h = meta["cell"]["width"], meta["cell"]["height"]
    assert (w, h) == ((128, 128) if meta["style"] == "pixel" else (256, 256))
    actions = meta["actions"]
    assert [a["row"] for a in actions] == list(range(len(actions)))

    sheet = Image.open(io.BytesIO(z.read(f"{top}{name}_sheet.png")))
    assert sheet.mode == "RGBA" and sheet.size == (max(a["frames"] for a in actions) * w, len(actions) * h)
    with z.open(f"{top}report/scores.csv") as f:
        scores = list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8")))
    for a in actions:
        assert set(a) == {"name", "row", "frames", "fps", "loop"} and config.FPS_MIN <= a["fps"] <= config.FPS_MAX
        frames = sorted(n for n in names if n.startswith(f"{top}frames/{a['name']}/"))
        assert len(frames) == a["frames"]
        assert all(Image.open(io.BytesIO(z.read(n))).size == (w, h) for n in frames)
        assert f"{top}preview/{a['name']}.gif" in names
        chosen = [r for r in scores if r["action"] == a["name"] and r["chosen"] == "True"]
        assert sorted(int(r["frame"]) for r in chosen) == list(range(a["frames"]))  # one chosen attempt per frame
        assert all((r["needs_review"] == "True") == (r["passed"] == "False") for r in chosen)
    for f in ("report/summary.md", "reference/character_sheet.png"):
        assert f"{top}{f}" in names

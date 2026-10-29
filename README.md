# ActSprite — Act it out. Play it in.

> Hackathon: Meta Global AI Developer Hackathon · Track: Indie Developer · Theme: **Build for Your World**

Act out a move on your phone. Get a consistent, game-ready animated character in Unity.

**Status:** work in progress. The command line runs the whole pipeline; the Unity importer and the full web flow come next.

## For judges: verify in 2 minutes (no API key)

**1. Look at finished output.** Each ZIP is exactly what the pipeline hands to Unity:

| Pixel knight, attack | Pixel hound, walk | Line-art man, attack |
| --- | --- | --- |
| ![knight](examples/previews/knight_attack.gif) | ![hound](examples/previews/hound_walk.gif) | ![line-art man](examples/previews/lineman_attack.gif) |
| [Download ZIP](https://github.com/lilwad-0730/actsprite/raw/main/examples/actsprite_knight.zip) | [Download ZIP](https://github.com/lilwad-0730/actsprite/raw/main/examples/actsprite_hound.zip) | [Download ZIP](https://github.com/lilwad-0730/actsprite/raw/main/examples/actsprite_lineman.zip) |
| 7/8 frames passed every check | 5/8 | 5/8 |
| $0.70 in Meta API calls | $0.73 | $0.67 |

Inside each ZIP: the sprite sheet, `<name>_meta.json` for the Unity importer, every frame as a PNG, a GIF
preview, and `report/scores.csv` with the scores of every redraw attempt (`needs_review` marks the frames that did
not pass every check). The spend is the sum of every paid call behind each ZIP in `logs/cost.csv`: the SAM 3.1
video track, the character sheet and every redraw and check. One action takes about 3-4.5 minutes
(measurements in `spikes/REPORT.md`, Day 4). The ZIPs were rebuilt from the API cache, so their own
`report/summary.md` shows $0 and says so.

**2. Run the tests.** No key and no network needed; `tests/test_examples.py` checks the three ZIPs against the
output contract.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest
```

## How it works

| Step | Meta model | Job |
| --- | --- | --- |
| Capture | SAM 3.1 (`sam-3.1`) | Track the actor in the clip, pixel masks per frame |
| Redraw | Muse Image (`muse-image-1.0`) | Redraw each pose as your character, anchored to the approved first frame so frames 1-7 are drawn at once |
| Verify | Muse Spark 1.3 (`muse-spark-1.3`) + SAM 3.1 | Art-director critic scores identity; SAM re-checks the pose silhouette |

## Quick start (dev)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env   # then paste your Meta Model API key into .env
.venv\Scripts\python -m pytest
```

## One command per action

```powershell
.venv\Scripts\python -m actsprite samples/attack.MOV --action attack --edges left,right             # pixel knight
.venv\Scripts\python -m actsprite samples/pet.mp4 --action walk --actor dog --character hound         # pixel hound
.venv\Scripts\python -m actsprite my_jump.mp4 --action jump --sheet my_hero.png --style lineart --name hero
```

Each run tracks the actor with SAM 3.1, picks 8 keyframes (one burst for jump/attack, one loop for idle,
one two-step stride for walk/run), draws pose guides, redraws every frame as the character with Muse Image
and checks it (SAM 3.1 silhouette, Muse Spark 1.3 critic, palette, leg motion), redrawing failed frames up to
twice. Frames 1-7 are drawn at the same time, anchored to the approved frame 0. The result is added as a row
to `out/<name>/actsprite_<name>.zip`:

```
actsprite_<name>/
  <name>_sheet.png                 one row per action, fixed cells (pixel art 128 px, other styles 256 px)
  <name>_meta.json                 cell size, feet pivot (0.5, 0), and per action: row, frames, fps, loop
  frames/<action>/<action>_00.png  every frame as its own PNG
  preview/<action>.gif
  report/scores.csv                every redraw attempt with its scores; needs_review marks frames to check
  report/summary.md
  reference/character_sheet.png
```

The estimated cost is printed before each batch of calls and every call is logged in `logs/cost.csv`
(about $0.7 per action for the three examples; identical requests are served from `cache/` for free). Set `ACTSPRITE_OFFLINE=1`
to answer only from the cache: no key needed, nothing is ever sent to the API.

## Web app

Live preview: https://huggingface.co/spaces/Andy0730huggin/actsprite (showcase + SAM 3.1 tracking check).

```powershell
.venv\Scripts\python -m pip install gradio==6.31.0 spaces huggingface_hub
.venv\Scripts\python app.py                    # local, http://localhost:7860
.venv\Scripts\hf auth login                    # once, token stays on your machine
.venv\Scripts\python scripts/deploy_space.py   # upload app.py, actsprite/, showcase/ to the Space
```

## Built during the hackathon (Oct 26 – Nov 4, 2026)

Everything in this repository was created during the hackathon period. See the git history.
The line-art character design (`man in line.jpg`) was drawn for this project on 2026-10-29 by a friend of the author.
The only outside input is the test footage listed under Credits.

## Credits and licenses

| Package | License | Use |
| --- | --- | --- |
| [openai](https://github.com/openai/openai-python) | Apache-2.0 | Client for the OpenAI-compatible Meta Model API |
| [meta-sam-parser](https://pypi.org/project/meta-sam-parser/) | SAM License (Meta) | Official parser for SAM 3.1 segmentation output |
| [opencv-python-headless](https://github.com/opencv/opencv-python) | Apache-2.0 | Frame extraction, edges, mask ops |
| [NumPy](https://numpy.org) | BSD-3-Clause | Arrays |
| [Pillow](https://python-pillow.org) | MIT-CMU | Image I/O, palette, packing |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | BSD-3-Clause | Load `.env` |
| [pytest](https://pytest.org) | MIT | Tests |
| [Gradio](https://github.com/gradio-app/gradio) | Apache-2.0 | Web app (`app.py`), installed by the Space from `sdk_version` |
| [spaces](https://pypi.org/project/spaces/) | Apache-2.0 | Hugging Face ZeroGPU hosting hook (the app runs on CPU) |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | Apache-2.0 | `scripts/deploy_space.py` uploads the app to the Space |

| Footage | Source | License | Use |
| --- | --- | --- | --- |
| `samples/pet.mp4` (not in the repo) | [Close-Up Shot of Dog Walking on the Street](https://www.pexels.com/video/close-up-shot-of-dog-walking-on-the-street-4300700/) by Luis Adolfo Burgos, Pexels | [Pexels License](https://www.pexels.com/license/) (free to use and modify) | Test input for the four-legged walk cycle. Only derived silhouettes and redrawn sprites appear in this repo; download the clip from the link to reproduce. |

## License

MIT

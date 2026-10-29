"""One command per action, from a phone clip to the character's verified sprite sheet ZIP for Unity:

  .venv\\Scripts\\python -m actsprite samples/attack.MOV --action attack --edges left,right
  .venv\\Scripts\\python -m actsprite samples/pet.mp4 --action walk --actor dog --character hound
  .venv\\Scripts\\python -m actsprite clip.mp4 --action jump --sheet my_hero.png --style lineart --name hero

Each action adds a row to out/<name>/actsprite_<name>/ and its ZIP (layout: actsprite/pipeline.py).
Costs (cached calls are free): SAM 3.1 video $0.0002 per frame sent (at least 50), then up to 24 redraw
attempts of about $0.035 each. Every call is logged in logs/cost.csv; the run stops at the budget hard stop.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from actsprite import config
from actsprite.characters import PRESETS, custom_character
from actsprite.errors import PipelineError
from actsprite.meta_client import BudgetExceeded, CacheMiss, MissingApiKey
from actsprite.pipeline import run
from actsprite.redraw import ANCHORS
from actsprite.restyle import BODIES, STYLES
from actsprite.sequence import ACTION_MODES, MODES


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m actsprite", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path, help="phone clip (MP4/MOV) of one action, side view")
    ap.add_argument("--action", required=True,
                    help=f"name of the action; {', '.join(ACTION_MODES)} pick the mode by themselves")
    ap.add_argument("--mode", choices=MODES, help="once (jump, attack), loop (idle) or gait (walk, run)")
    ap.add_argument("--actor", default="person", help="what SAM 3.1 tracks in the clip: person, dog, cat ...")
    ap.add_argument("--edges", default=",".join(config.FULL_BODY_EDGES),
                    help="frame edges the actor must not touch, e.g. left,right when the feet touch the bottom")
    ap.add_argument("--out", type=Path, help="output folder (default: out/<character>_<action>)")
    c = ap.add_argument_group("character (a built-in one, or your own)")
    c.add_argument("--character", choices=sorted(PRESETS), default="knight", help="built-in character")
    c.add_argument("--sheet", type=Path, help="your own design: full body, side view, plain white background")
    c.add_argument("--sheet-faces-left", action="store_true", help="your design faces left (it is mirrored)")
    c.add_argument("--description", default="",
                   help="design a new character from this text instead (e.g. 'an original fox ranger ...')")
    c.add_argument("--name", default="custom", help="name of your own character in the outputs")
    c.add_argument("--body", choices=sorted(BODIES), default="biped", help="your own character's body")
    c.add_argument("--style", choices=sorted(STYLES), default="pixel", help="your own character's style")
    r = ap.add_argument_group("redraw")
    r.add_argument("--anchor", choices=ANCHORS, default="first",
                   help="first: frames 1-7 refer to frame 0 and are drawn at once; previous: one at a time")
    r.add_argument("--show-anchor-legs", action="store_true",
                   help="send frame 0 whole (by default its legs are painted out so they cannot be copied)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.sheet or args.description:
            ch = custom_character(args.name, sheet=args.sheet, description=args.description, body=args.body,
                                  style=args.style, faces_left=args.sheet_faces_left)
        else:
            ch = PRESETS[args.character]
        root = args.out or config.ROOT / "out" / ch.name
        edges = tuple(e for e in args.edges.split(",") if e)
        result, zip_path = run(args.video, root, args.action, ch, actor=args.actor, mode=args.mode, edges=edges,
                               anchor=args.anchor, hide_anchor_legs=not args.show_anchor_legs)
    except (PipelineError, MissingApiKey, BudgetExceeded, CacheMiss) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    passed = sum(result["passed"])
    print(f"\n{args.action}: {passed}/{result['frames']} frames passed every check ({result['attempts']} attempts), "
          f"{result['seconds']:.0f} s, ${result['spent_usd']:.2f} this run")
    print(f"  package: {zip_path.with_suffix('')}")
    print(f"  zip:     {zip_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

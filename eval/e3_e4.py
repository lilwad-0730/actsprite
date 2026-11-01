"""E3 (unit cost) and E4 (robustness) from the records of runs already made. No API calls.

  .venv\\Scripts\\python -m eval.e3_e4

Reads out/*/work/*/result.json, scores.csv, track.npz and logs/cost.csv (all local, not in git) and writes
eval/results/e3_cost_per_action.csv, e3_cost_by_model.csv, e4_tracking.csv and e4_summary.md.
Small development check on the author's clips, not a formal accuracy study.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from actsprite import config

ROOT = config.ROOT
RESULTS = ROOT / "eval" / "results"

# The shipped sprites: the run behind each ZIP or Unity demo character (output folder, action).
SHIPPED = [("knight", "idle"), ("knight", "run"), ("knight", "jump"), ("knight", "attack"),
           ("lineman", "run"), ("lineman", "attack"), ("hound", "walk"), ("knight_dance2_whole", "dance")]
# What each clip shows, from the author's notes; "not recorded" where the notes do not say.
CLIPS = {
    "pet.mp4": ("dog", "outdoor street", "Pexels stock clip"),
    "punch.MOV": ("person", "outdoor", "author"),
    "idle (1).MOV": ("person", "outdoor", "author"),
    "jump (1).MOV": ("person", "outdoor", "author"),
    "run (1).MOV": ("person", "outdoor", "author"),
    "attack.MOV": ("person", "not recorded", "author"),
    "idle (2a).mp4": ("person", "not recorded", "author"),
    "idle (2b).mp4": ("person", "not recorded", "author"),
    "dance test.mp4": ("person", "not recorded", "friend, consent given"),
    "dance 2 test .mp4": ("person", "not recorded", "friend, consent given"),
}


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        w.writeheader()
        w.writerows(rows)


def cost_log() -> list[dict]:
    with config.COST_LOG.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def e3(log: list[dict]) -> tuple[list[dict], list[dict]]:
    per_action = []
    for folder, action in SHIPPED:
        work = ROOT / "out" / folder / "work" / action
        r = json.loads((work / "result.json").read_text(encoding="utf-8"))
        character = folder.split("_")[0]
        # Every paid call ever made for this character and action (all retries and earlier tries included).
        prefix = f"actsprite {character} {action}"
        paid = [x for x in log if x["note"].startswith(prefix) and x["cached"] in ("0", "False")]
        total = sum(float(x["cost_usd"]) for x in paid)
        calls = r.get("api_calls") or {}
        per_action.append({
            "character": character, "action": action, "frames": r["frames"], "fps": r["fps"],
            "passed": sum(r["passed"]), "attempts": r["attempts"],
            "spend_of_final_run_usd": round(r["spent_usd"], 4),
            "final_run_new_calls": calls.get("new", ""), "final_run_cached_calls": calls.get("cached", ""),
            "spend_all_tries_on_this_action_usd": round(total, 4),
            "all_tries_usd_per_frame": round(total / r["frames"], 4),
            "minutes_final_run": round(r["seconds"] / 60, 1),
        })
    by_model: dict[tuple[str, str], list[float]] = defaultdict(list)
    for x in log:
        if x["cached"] in ("0", "False"):
            by_model[(x["model"], x["operation"])].append(float(x["cost_usd"]))
    models = [{"model": m, "operation": op, "paid_calls": len(v), "total_usd": round(sum(v), 2),
               "mean_usd_per_call": round(sum(v) / len(v), 4)} for (m, op), v in sorted(by_model.items())]
    return per_action, models


def e4() -> list[dict]:
    rows, seen = [], set()
    for track in sorted((ROOT / "out").glob("*/work/*/track.npz")):
        res = track.parent / "result.json"
        if not res.exists():
            continue
        r = json.loads(res.read_text(encoding="utf-8"))
        clip = Path(r["video"].replace("\\", "/")).name
        z = np.load(track)
        masks = z["masks"]
        key = (clip, round(float(z["fps"]), 1), masks.shape[0])
        if key in seen or clip not in CLIPS:
            continue
        seen.add(key)
        present = masks.reshape(len(masks), -1).any(1)
        lo, hi = r["full_body"]
        subject, place, source = CLIPS[clip]
        rows.append({
            "clip": clip, "subject": subject, "place": place, "source": source,
            "sam_frames": len(masks), "sam_fps": round(float(z["fps"]), 2),
            "frames_with_mask": int(present.sum()), "tracked_share": round(float(present.mean()), 3),
            "edges_required": "+".join(r["edges"]),
            "usable_whole_body_frames_in_part_used": hi - lo, "usable_share": round((hi - lo) / len(masks), 3),
            "example_action_from_clip": r["name"], "example_frames_passed": f"{sum(r['passed'])}/{r['frames']}",
        })
    return rows


def main() -> None:
    log = cost_log()
    per_action, models = e3(log)
    write_csv(RESULTS / "e3_cost_per_action.csv", per_action)
    write_csv(RESULTS / "e3_cost_by_model.csv", models)
    tracking = e4()
    write_csv(RESULTS / "e4_tracking.csv", tracking)
    ok = [t for t in tracking if t["tracked_share"] >= 0.9]
    lines = ["# E4: SAM 3.1 tracking on the clips used so far", "",
             f"{len(ok)} of {len(tracking)} clips had a mask in at least 90% of the frames sent to SAM 3.1 "
             f"(subjects: {', '.join(sorted({t['subject'] for t in tracking}))}).",
             "No stop-motion figure clip was tested.", "",
             "| Clip | Subject | Place | Tracked frames | Usable whole-body frames (in the part of the clip used) | Example result |",
             "| --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {t['clip']} | {t['subject']} | {t['place']} | {t['frames_with_mask']}/{t['sam_frames']} "
              f"({t['tracked_share']:.0%}) | {t['usable_whole_body_frames_in_part_used']} ({t['usable_share']:.0%}, edges "
              f"{t['edges_required']}) | {t['example_action_from_clip']} {t['example_frames_passed']} |"
              for t in tracking]
    (RESULTS / "e4_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for name, rows in (("E3 per action", per_action), ("E3 by model", models), ("E4", tracking)):
        print(f"\n== {name}")
        for r in rows:
            print(r)


if __name__ == "__main__":
    main()

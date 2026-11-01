"""Run the web app's three steps in-process for one action (no server). The local cost log is shared with
development, so the web's $40 cap is lifted to the project's $140 hard stop for this test only."""
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
from actsprite import config



def main() -> None:
    config.DEMO_SPEND_CAP_USD = config.BUDGET_HARD_STOP_USD
    OUT = Path(sys.argv[1])
    video, action_label, start = sys.argv[2], sys.argv[3], float(sys.argv[4])
    end = float(sys.argv[5]) if len(sys.argv) > 5 else None
    OUT.mkdir(parents=True, exist_ok=True)

    t = time.time()
    r = app.step_track(video, "Pixel knight", None, "pixel", "biped", False, action_label, "person", start, end, None)
    sid = r[0]
    print(f"step 1 ({time.time() - t:.0f} s):", r[2])
    p = r[3]
    print("  frames", p["frames"], "| fps", p["playback_fps"], "| mode", p["mode (chosen from the action)"],
          "| keyframes", p["keyframes_at_seconds"])
    t = time.time()
    r = app.step_first(sid, None)
    print(f"step 2 ({time.time() - t:.0f} s):", r[1][:110])
    t = time.time()
    r = app.step_finish(sid, "knight", None, progress=lambda *a, **k: None)
    print(f"step 3 ({time.time() - t:.0f} s):", r[2][:120])
    print("  spent", r[4]["cost_usd"]["spent_this_visit"])
    s = app._sessions[sid]
    pkg = Path(r[3]).with_suffix("")
    action = s["plan"].action
    shutil.copy(pkg / "preview" / f"{action}.gif", OUT / f"web_{action}.gif")
    from PIL import Image
    Image.fromarray(r[1]).save(OUT / f"web_{action}_grid.png")


if __name__ == "__main__":
    main()

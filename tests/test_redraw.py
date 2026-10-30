from concurrent.futures.process import BrokenProcessPool

import numpy as np

from actsprite.capture import SamObject
from actsprite import redraw


class _Client:
    def segment(self, media, prompt, note=""):
        return "sam text", None


class _BrokenPool:
    def submit(self, *args, **kwargs):
        raise BrokenProcessPool("worker died")


def test_sam_mask_survives_a_dead_decode_worker(monkeypatch):
    mask = np.zeros((4, 4), bool)
    mask[1:3, 1:3] = True
    broken = _BrokenPool()
    monkeypatch.setattr(redraw, "_parse_pool", broken)
    monkeypatch.setattr(redraw, "parse_sam_output", lambda text, size, video, workers: [SamObject(0, "0", (1, 1, 3, 3), mask)])
    out = redraw.sam_mask(_Client(), np.zeros((4, 4, 3), np.uint8), "knight")
    assert out is not None and (out == mask).all()  # decoded in the main process instead
    assert redraw._parse_pool is None  # the broken pool is dropped; the next call starts a new one


def test_idle_keeps_frame_zero_legs_and_skips_the_copy_check():
    from actsprite.redraw import leg_policy

    assert leg_policy("loop") == (False, True)  # idle: frame 0 whole, legs must keep its stance
    assert leg_policy("loop", hide_anchor_legs=True) == (False, True)
    assert leg_policy("gait") == (True, False) and leg_policy("once") == (True, False)
    assert leg_policy("once", hide_anchor_legs=False) == (False, False)  # --show-anchor-legs

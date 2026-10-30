"""Head direction (10/30): SAM 3.1 face mask inside the head -> face patch on the guide and one sentence."""

import numpy as np
import pytest

from actsprite import config
from actsprite.align import pose_guide
from actsprite.head import head_pose, head_region
from actsprite.restyle import redraw_parts
from actsprite.verify import critic_parts


def _person_and_face(offset: int, face: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Front-view figure 300 px tall with a 40 px wide head; the face sits `offset` px right of the head centre."""
    person = np.zeros((360, 200), bool)
    person[30:72, 80:120] = True  # head
    person[72:330, 60:140] = True  # body and legs
    f = np.zeros_like(person)
    if face:
        f[38:70, 88 + offset : 112 + offset] = True
    return person, f & person


def test_head_region_is_the_head_not_the_shoulders():
    person, _ = _person_and_face(0)
    left, top, right, bottom = head_region(person)
    assert top == 30 and abs(left - 80) <= 1 and abs(right - 120) <= 1 and bottom > top


@pytest.mark.parametrize(("offset", "words"), [
    (0, "facing the viewer"),
    (3, "turned slightly toward the right"),
    (-6, "turned toward the left side of the image, about half way"),
    (12, "in profile"),
])
def test_face_position_gives_the_turn(offset, words):
    person, face = _person_and_face(offset)
    assert words in head_pose(person, face).describe()


def test_no_face_means_turned_away():
    person, face = _person_and_face(0, face=False)
    pose = head_pose(person, face)
    assert pose.turned_away and "back of the head" in pose.describe()
    assert head_pose(np.zeros((10, 10), bool), None) is None


def test_face_patch_on_the_guide_has_no_features():
    person, face = _person_and_face(6)
    img = np.full(person.shape + (3,), 90, np.uint8)
    img[45:50, 90:110] = 230  # "eyes": must not come through
    guide, _ = pose_guide(img, person, size=256, margin=8, fill=True, head_fraction=0.18, face=face)
    patch = guide[..., 0] == config.GUIDE_FACE_GRAY
    assert patch.any()
    ys, xs = np.nonzero(patch)
    assert xs.mean() > 128  # patch is right of centre, like the face
    plain, _ = pose_guide(img, person, size=256, margin=8, fill=True, head_fraction=0.18)
    assert not (plain[..., 0] == config.GUIDE_FACE_GRAY).any()
    assert set(np.unique(guide)) <= {0, config.GUIDE_FACE_GRAY, config.GUIDE_FILL_GRAY, 255}


def test_head_sentence_reaches_the_redraw_and_the_critic():
    plain = redraw_parts(b"S", b"G", b"P", "pixel", anchor=True, view="front")
    with_head = redraw_parts(b"S", b"G", b"P", "pixel", anchor=True, view="front", head="facing the viewer")
    assert "Head: facing the viewer." in with_head[-1] and "Head:" not in plain[-1]
    critic = critic_parts(b"S", b"P", b"G", b"C", anchor=True, head="turned away from the viewer")[-1]
    assert "the head must be turned away from the viewer" in critic
    assert "head direction" not in critic_parts(b"S", b"P", b"G", b"C", anchor=True)[-1]


def test_cli_head_and_sample_options():
    import argparse

    from actsprite.__main__ import _sample_fps, parse_args

    args = parse_args(["d.mp4", "--action", "dance", "--mode", "span", "--sample-fps", "60", "--no-head-turn"])
    assert args.sample_fps == 60 and args.head_turn is False
    assert parse_args(["d.mp4", "--action", "attack"]).head_turn is None  # decided by the view
    assert parse_args(["d.mp4", "--action", "attack"]).sample_fps == config.SAM_VIDEO_FPS
    with pytest.raises(argparse.ArgumentTypeError):
        _sample_fps("120")

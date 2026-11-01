"""Local tests for VIDEO ordering, SAM association and conservative drawing."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from spikes import spike_skeleton as spike


def test_video_reads_every_rgb_frame_before_selecting_keys(monkeypatch):
    import mediapipe as mp

    calls, modes = [], []
    bgr_frames = [np.full((8, 10, 3), [i, i + 10, i + 20], np.uint8) for i in range(4)]

    class Capture:
        index = 0

        def isOpened(self):
            return True

        def read(self):
            if self.index == len(bgr_frames):
                return False, None
            frame = bgr_frames[self.index]
            self.index += 1
            return True, frame

        def release(self):
            pass

    class Pose:
        def __init__(self, **kwargs):
            modes.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def process(self, rgb):
            calls.append(rgb[0, 0].tolist())
            points = [SimpleNamespace(x=.5, y=.5, z=0., visibility=1.) for _ in range(33)]
            return SimpleNamespace(pose_landmarks=SimpleNamespace(landmark=points))

    monkeypatch.setattr(spike.cv2, "VideoCapture", lambda path: Capture())
    monkeypatch.setattr(mp.solutions.pose, "Pose", Pose)
    frames, landmarks, info = spike.track_video(Path("unused.mp4"), np.ones((4, 8, 10), bool), [1, 3])
    assert calls == [[20, 10, 0], [21, 11, 1], [22, 12, 2], [23, 13, 3]]
    assert list(frames) == [1, 3] and list(landmarks) == [1, 3]
    assert modes[0]["static_image_mode"] is False and len(modes) == 1
    assert info["processed_frames"] == 4
    assert landmarks[1][0, :2].tolist() == [5., 4.]
    with pytest.raises(RuntimeError, match="frame count"):
        spike.track_video(Path("unused.mp4"), np.ones((5, 8, 10), bool), [1])


def test_quality_omits_occluded_and_distant_points():
    mask = np.zeros((100, 100), bool)
    mask[10:90, 30:70] = True
    xy = np.tile([50., 50.], (33, 1))
    visibility = np.ones(33)
    visibility[13] = .1
    xy[25] = [95., 50.]
    used, valid, details = spike.quality(xy, visibility, mask)
    assert used and not valid[13] and not valid[25]
    assert details["inside_share"] == pytest.approx(32 / 33)
    assert "low_visibility" in details["point_reasons"][13]
    assert "outside_mask" in details["point_reasons"][25]


def test_unrelated_person_or_missing_pose_falls_back_to_exact_guide():
    mask = np.zeros((100, 100), bool)
    mask[10:90, 30:70] = True
    rgb = np.full((100, 100, 3), 127, np.uint8)
    guide = np.full((512, 512, 3), 205, np.uint8)
    wrong = np.tile([95., 50., 0., 1.], (33, 1))
    for landmarks in (wrong, None):
        result, original, details = spike.skeleton(landmarks, rgb, mask, guide, 2.)
        assert details["skeleton_used"] is False
        assert np.array_equal(result, guide)
        assert np.array_equal(original, rgb)


def test_low_visibility_point_is_not_drawn_or_bridged():
    xy = np.zeros((33, 2))
    xy[11], xy[13], xy[15] = [10, 10], [20, 20], [30, 10]
    valid = np.zeros(33, bool)
    valid[[11, 15]] = True
    image = spike.draw_skeleton(np.full((40, 40, 3), 255, np.uint8), xy, valid, 2)
    assert image[20, 20].tolist() == [255, 255, 255]
    assert image[10, 20].tolist() == [255, 255, 255]
    assert image[10, 10].tolist() != [255, 255, 255]

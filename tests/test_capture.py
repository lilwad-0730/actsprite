import pytest
import numpy as np

from actsprite.capture import largest_object, main_track, parse_sam_output

# Two-object sample from the meta-sam-parser documentation (frame 320x334).
SAMPLE = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
    ",1<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,48,~!!!!J!0c[q=Pj_zs=*4C4(/./x#:/`S_GnD`=o3?X{emCgO$y@|>\n"
)


def test_parse_image_output_pastes_masks_inside_boxes():
    objs = parse_sam_output(SAMPLE, (320, 334), video=False)
    assert [o.object_id for o in objs] == ["0", "1"]
    for o in objs:
        assert o.mask.shape == (334, 320)
        assert o.area > 0
        left, top, right, bottom = o.box
        outside = o.mask.copy()
        outside[top:bottom, left:right] = False
        assert not outside.any()
    assert objs[0].box == (211, 228, 271, 255)


def test_parse_video_output_keeps_frame_index():
    text = SAMPLE + SAMPLE.replace("<0f>", "<3f>")
    objs = parse_sam_output(text, (320, 334), video=True)
    assert sorted({o.frame_index for o in objs}) == [0, 3]
    track = main_track(objs)
    assert sorted(track) == [0, 3]
    assert len({o.object_id for o in track.values()}) == 1


def test_empty_output_is_valid():
    assert parse_sam_output("", (10, 10), video=False) == []
    assert largest_object([]) is None
    assert main_track([]) == {}


def test_largest_object_by_area():
    objs = parse_sam_output(SAMPLE, (320, 334), video=False)
    best = largest_object(objs)
    assert best is not None
    assert best.area == max(int(np.sum(o.mask)) for o in objs)


def _obj(i: int, mask: np.ndarray) -> "SamObject":
    from actsprite.capture import SamObject

    return SamObject(i, "0", (0, 0, 1, 1), mask)


def _body(top: int, bottom: int, left: int = 20, right: int = 40, h: int = 100, w: int = 60) -> np.ndarray:
    m = np.zeros((h, w), bool)
    m[top:bottom, left:right] = True
    return m


def test_edge_contact():
    from actsprite.capture import edge_contact

    assert edge_contact(_body(10, 90)) == set()
    assert edge_contact(_body(10, 100)) == {"bottom"}
    assert edge_contact(_body(0, 50, left=0)) == {"top", "left"}
    assert edge_contact(np.zeros((5, 5), bool)) == set()


def test_full_body_range_trims_walk_in_and_out():
    from actsprite.capture import full_body_range

    # 0-2 close to the camera (cut off), 3-11 whole body, 12 missing, 13-15 whole body, 16-17 cut off.
    track = {}
    for i in range(18):
        if i == 12:
            continue
        cut = i < 3 or i >= 16
        track[i] = _obj(i, _body(0 if cut else 10, 100 if cut else 90))
    assert full_body_range(track, 18, min_frames=3) == (3, 12)
    assert full_body_range(track, 18, min_frames=10) is None


def test_prepare_video_strides_and_scales(tmp_path):
    import cv2

    from actsprite.capture import prepare_video, read_frames

    src = tmp_path / "src.mp4"
    writer = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"mp4v"), 60, (320, 180))
    for i in range(20):
        frame = np.zeros((180, 320, 3), np.uint8)
        frame[:, : 10 * (i + 1)] = 255
        writer.write(frame)
    writer.release()

    pv = prepare_video(src, tmp_path / "out.mp4", max_short_side=90, target_fps=30)
    assert pv.size == (160, 90)
    assert pv.source_indices == list(range(0, 20, 2))
    assert pv.frame_count == 10 and abs(pv.fps - 30) < 0.01
    frames = read_frames(pv.path)
    assert len(frames) == 10 and frames[0].shape == (90, 160, 3)

    short = prepare_video(src, tmp_path / "short.mp4", max_short_side=90, target_fps=30, max_seconds=0.2)
    assert short.source_indices == [0, 2, 4, 6, 8, 10]  # first 0.2 s of a 60 fps clip = 12 frames


def test_parallel_video_parse_matches_serial():
    text = "".join(SAMPLE.replace("<0f>", f"<{i}f>") for i in range(6))
    serial = parse_sam_output(text, (320, 334), video=True, workers=1)
    parallel = parse_sam_output(text, (320, 334), video=True, workers=3)
    assert [(o.frame_index, o.object_id, o.box) for o in serial] == [
        (o.frame_index, o.object_id, o.box) for o in parallel
    ]
    assert all(np.array_equal(a.mask, b.mask) for a, b in zip(serial, parallel))


def test_full_body_range_can_ignore_an_edge():
    from actsprite.capture import full_body_range

    track = {i: _obj(i, _body(10, 100)) for i in range(8)}  # feet touch the bottom in every frame
    assert full_body_range(track, 8) is None
    assert full_body_range(track, 8, edges=("left", "right", "top")) == (0, 8)


def test_read_frames_at_returns_only_the_asked_frames(tmp_path):
    import cv2

    from actsprite.capture import read_frames, read_frames_at

    src = tmp_path / "src.mp4"
    writer = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"mp4v"), 30, (64, 32))
    for i in range(12):
        writer.write(np.full((32, 64, 3), 20 * i, np.uint8))
    writer.release()
    every = read_frames(src)
    some = read_frames_at(src, [7, 2, 11])
    assert sorted(some) == [2, 7, 11]
    assert all((some[i] == every[i]).all() for i in some)
    with pytest.raises(ValueError):
        read_frames_at(src, [3, 40])


def test_video_parse_survives_a_dead_worker(monkeypatch):
    from concurrent.futures.process import BrokenProcessPool

    import actsprite.capture as capture

    class DyingPool:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def map(self, *a, **k):
            raise BrokenProcessPool("worker ran out of page file")

    text = "".join(SAMPLE.replace("<0f>", f"<{i}f>") for i in range(4))
    serial = parse_sam_output(text, (320, 334), video=True, workers=1)
    monkeypatch.setattr(capture, "ProcessPoolExecutor", DyingPool)
    rescued = parse_sam_output(text, (320, 334), video=True, workers=3)
    assert [(o.frame_index, o.box) for o in rescued] == [(o.frame_index, o.box) for o in serial]


def test_prepare_video_from_a_start_time(tmp_path):
    import cv2
    import numpy as np
    from actsprite.capture import prepare_video

    src = tmp_path / "clip.mp4"
    w = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 48))
    for i in range(30):  # 3 s at 10 fps; frame i is filled with the value 8 * i
        w.write(np.full((48, 64, 3), 8 * i, np.uint8))
    w.release()
    pv = prepare_video(src, tmp_path / "out.mp4", target_fps=10, max_seconds=1.0, start_seconds=1.5)
    assert pv.source_indices == list(range(15, 25)) and pv.frame_count == 10


def test_a_corrupt_sam_mask_is_skipped(monkeypatch):
    from meta_sam_parser import InvalidSegmentationMaskError
    from actsprite import capture

    class Rec:
        kind, object_id = "mask", "0"
        def __init__(self, i):
            self.mask = type("M", (), {"height": 2, "width": 2, "i": i})()
            self.bounds = type("B", (), {"left": 0, "top": 0, "right": 2, "bottom": 2})()
            self.frame = type("F", (), {"frame_index": i})()

    class Parser:
        def push(self, text): pass
        def finish(self, outcome): return type("R", (), {"result": type("X", (), {"records": [Rec(0), Rec(1)]})()})()

    def decode(m):
        if m.i == 1:
            raise InvalidSegmentationMaskError("Mask payload could not be decoded.")
        return bytes(4)

    monkeypatch.setattr(capture, "video_segmentation_format", lambda: type("Fm", (), {"create_parser": lambda self: Parser()})())
    monkeypatch.setattr(capture, "decode_mask_to_raster", decode)
    out = capture._decode_chunk("text", video=True)
    assert [d[0] for d in out] == [0]  # frame 1's corrupt mask is dropped, frame 0 kept


def test_phone_rotation_is_applied_to_frames_and_prepared_size(tmp_path):
    from pathlib import Path
    from actsprite.capture import prepare_video, read_frames, read_frames_at, video_info

    # Synthetic red/green/blue/yellow quadrants stored landscape with a 90-degree display rotation.
    src = Path(__file__).parent / "fixtures" / "phone_rotation90.mp4"
    fps, count, size = video_info(src)
    assert fps == 10 and count == 2 and size == (48, 64)
    frames = read_frames(src)
    assert frames[0].shape == (64, 48, 3)
    assert frames[0][8, 8, 1] > 200  # green rotates from the stored top right to the displayed top left
    assert np.array_equal(read_frames_at(src, [0])[0], frames[0])
    pv = prepare_video(src, tmp_path / "prepared.mp4", target_fps=10, max_short_side=48)
    assert pv.size == size and pv.source_indices == [0, 1]
    prepared = read_frames(pv.path)
    assert prepared[0].shape == frames[0].shape and prepared[0][8, 8, 1] > 200

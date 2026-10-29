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

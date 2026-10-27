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

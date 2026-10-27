import numpy as np
import pytest

from actsprite.align import fit_to_canvas, mask_bbox, pose_guide


def figure(h=200, w=300, box=(120, 40, 160, 180)):
    """A rectangle 'person' standing somewhere in a frame."""
    mask = np.zeros((h, w), dtype=bool)
    l, t, r, b = box
    mask[t:b, l:r] = True
    return mask


def test_bbox_and_empty():
    assert mask_bbox(figure()) == (120, 40, 160, 180)
    with pytest.raises(ValueError):
        mask_bbox(np.zeros((5, 5), bool))


def test_feet_on_bottom_row_and_centred():
    out, _, scale = fit_to_canvas(figure(), 256, margin=12)
    l, t, r, b = mask_bbox(out)
    assert b == 256  # feet touch the baseline
    assert t == 12  # tallest frame fills the height minus top margin
    assert abs((l + r) / 2 - 128) <= 1
    assert scale == pytest.approx(244 / 140)


def test_shared_scale_keeps_height_difference():
    tall, short = figure(), figure(box=(120, 110, 160, 180))
    _, _, s = fit_to_canvas(tall, 256)
    out_short, _, _ = fit_to_canvas(short, 256, scale=s)
    l, t, r, b = mask_bbox(out_short)
    assert b == 256
    assert (b - t) == pytest.approx(70 * s, abs=1)


def test_moving_subject_is_placed_in_place():
    a, _, s = fit_to_canvas(figure(box=(20, 40, 60, 180)), 256)
    b, _, _ = fit_to_canvas(figure(box=(220, 40, 260, 180)), 256, scale=s)
    assert np.array_equal(a, b)


def test_pose_guide_is_black_lines_on_white_only_inside_subject():
    img = np.full((200, 300, 3), 90, np.uint8)
    img[60:120, 125:155] = 220  # some interior detail
    mask = figure()
    guide, gmask = pose_guide(img, mask, size=128, margin=8)
    assert guide.shape == (128, 128, 3)
    assert set(np.unique(guide)) <= {0, 255}
    dark = guide[..., 0] == 0
    assert dark.any()
    grown = np.zeros_like(gmask)
    ys, xs = np.nonzero(gmask)
    grown[max(ys.min() - 3, 0) : ys.max() + 4, max(xs.min() - 3, 0) : xs.max() + 4] = True
    assert not (dark & ~grown).any()

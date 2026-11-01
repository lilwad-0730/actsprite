import numpy as np
import pytest

from actsprite.pack import map_to_palette, pixelate, upscale_nearest


@pytest.mark.parametrize("fps", [7.9, 12., 30.])
def test_preview_gif_preserves_cumulative_playback_time(tmp_path, fps):
    from PIL import Image, ImageSequence
    from actsprite.pack import preview_gif

    cells = [np.full((16, 16, 4), (20 * i, 40, 60, 255), np.uint8) for i in range(8)]
    path = tmp_path / "preview.gif"
    preview_gif(cells, path, fps, size=16)
    with Image.open(path) as gif:
        durations = [frame.info["duration"] for frame in ImageSequence.Iterator(gif)]
    assert len(durations) == len(cells)
    # GIF stores 10ms ticks: each boundary should be within half a tick, without accumulating drift.
    expected = np.arange(1, len(cells) + 1) * 1000 / fps
    assert np.max(np.abs(np.cumsum(durations) - expected)) <= 5. + 1e-9


def cell():
    """256x256 RGBA: red block on a transparent white background."""
    img = np.zeros((256, 256, 4), np.uint8)
    img[..., :3] = 255
    img[64:256, 96:160, :3] = (200, 40, 40)
    img[64:256, 96:160, 3] = 255
    return img


def test_pixelate_shape_hard_alpha_no_white_bleed():
    out = pixelate(cell(), 64)
    assert out.shape == (64, 64, 4)
    assert set(np.unique(out[..., 3])) <= {0, 255}
    opaque = out[..., 3] == 255
    assert opaque.sum() == 48 * 16
    assert (out[opaque][:, :3] == (200, 40, 40)).all()  # edge pixels not mixed with white


def test_pixelate_onto_palette():
    pal = np.array([[0, 0, 0], [210, 30, 30], [255, 255, 255]], np.float32)
    out = pixelate(cell(), 32, pal)
    opaque = out[..., 3] == 255
    assert (out[opaque][:, :3] == (210, 30, 30)).all()


def test_map_to_palette_and_upscale():
    pal = np.array([[0, 0, 0], [255, 255, 255]], np.float32)
    img = np.array([[[10, 10, 10], [240, 240, 240]]], np.uint8)
    assert map_to_palette(img, pal).tolist() == [[[0, 0, 0], [255, 255, 255]]]
    assert upscale_nearest(img, 3).shape == (3, 6, 3)


def test_pixelate_rejects_rgb():
    with pytest.raises(ValueError):
        pixelate(np.zeros((8, 8, 3), np.uint8), 4)


def test_contract_meta_rows_and_pivot():
    from actsprite.pack import action_fps, character_meta

    actions = [{"name": "idle", "frames": 8, "fps": action_fps("loop"), "loop": True},
               {"name": "jump", "frames": 8, "fps": action_fps("once"), "loop": False}]
    meta = character_meta("knight", "pixel", (128, 128), actions)
    assert meta == {
        "character": "knight", "style": "pixel", "cell": {"width": 128, "height": 128},
        "pivot": {"x": 0.5, "y": 0.0},
        "actions": [{"name": "idle", "row": 0, "frames": 8, "fps": 8, "loop": True},
                    {"name": "jump", "row": 1, "frames": 8, "fps": 15, "loop": False}],
    }


def test_sheet_rows_and_pixel_cells():
    from actsprite.pack import export_cells, sheet_from_rows

    small = [np.full((64, 64, 4), v, np.uint8) for v in (10, 20)]
    big = export_cells(small, pixel_art=True)
    assert big[0].shape == (128, 128, 4) and (big[1] == 20).all()  # each art pixel -> 2x2
    assert export_cells(small, pixel_art=False) is small
    sheet = sheet_from_rows([big, big[:1]])
    assert sheet.shape == (256, 256, 4)
    assert (sheet[128:, 128:] == 0).all()  # the shorter row leaves transparent cells
    with pytest.raises(ValueError):
        sheet_from_rows([big, small])  # one cell size per character


def test_follow_guide_height_squashes_shorter_guides_keeps_feet():
    from actsprite.pack import follow_guide_height

    def figure(top, size=100):
        m = np.zeros((size, 40), bool)
        m[top:, 10:30] = True
        return m

    cuts = [figure(5), figure(5), figure(5)]  # redraws: always full height
    rgbs = [np.where(c[..., None], 50, 255).astype(np.uint8).repeat(3, 2) for c in cuts]
    guides = [figure(10), figure(20), figure(10)]  # the actor crouches in frame 1
    new_rgbs, new_cuts, f = follow_guide_height(rgbs, cuts, guides)
    tops = [int(np.nonzero(c)[0].min()) for c in new_cuts]
    assert f[0] == 1.0 and f[2] == 1.0 and f[1] < 1.0
    assert tops[0] == 5 and tops[1] > 15  # frame 1 is shorter by about the guide's drop
    assert all(c.shape == (100, 40) and c[-1].any() for c in new_cuts)  # canvas kept, feet on the bottom row
    assert all(r.shape == (100, 40, 3) for r in new_rgbs)


def test_follow_guide_height_never_stretches_and_skips_empty():
    from actsprite.pack import follow_guide_height
    m = np.zeros((50, 20), bool)
    m[10:, 5:15] = True
    rgb = np.full((50, 20, 3), 255, np.uint8)
    _, _, f = follow_guide_height([rgb, rgb], [m, m], [m, m])
    assert f == [1.0, 1.0]
    _, cuts, f = follow_guide_height([rgb], [m], [np.zeros_like(m)])
    assert f == [1.0] and cuts[0] is m


def test_follow_guide_height_keeps_frame0_size_and_caps_taller_frames():
    from actsprite.pack import follow_guide_height
    m = np.zeros((100, 20), bool)
    m[5:, 5:15] = True
    rgb = np.full((100, 20, 3), 255, np.uint8)
    tall, short, base = np.zeros_like(m), np.zeros_like(m), np.zeros_like(m)
    base[20:] = True
    tall[0:] = True  # arms up: taller than frame 0
    short[40:] = True  # crouch
    _, _, f = follow_guide_height([rgb] * 3, [m] * 3, [base, tall, short])
    assert f[0] == 1.0 and f[1] == 1.0 and abs(f[2] - 60 / 80) < 0.01

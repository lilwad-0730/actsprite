import numpy as np
import pytest

from actsprite.pack import map_to_palette, pixelate, upscale_nearest


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

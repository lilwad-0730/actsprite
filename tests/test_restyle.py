import numpy as np

from actsprite.restyle import SHEET_RULES, STYLES, redraw_parts, sheet_prompt, white_flood_cutout


def test_sheet_prompt_has_design_rules():
    p = sheet_prompt("an original young knight", "pixel")
    assert "no cape" in p and SHEET_RULES in p
    assert STYLES["pixel"].prompt in p


def test_redraw_parts_with_and_without_previous_frame():
    first = redraw_parts(b"S", b"G", None, "handdrawn")
    assert [p for p in first if isinstance(p, bytes)] == [b"S", b"G"]
    assert "do NOT copy its pose" not in first[-1]

    later = redraw_parts(b"S", b"G", b"P", "handdrawn", fix="Make the plume red.")
    assert [p for p in later if isinstance(p, bytes)] == [b"S", b"P", b"G"]
    assert "do NOT copy its pose" in later[-1]
    assert "Fix from the art director: Make the plume red." in later[-1]


def test_flood_cutout_keeps_inner_white_and_thin_parts():
    img = np.full((100, 100, 3), 255, np.uint8)
    img[30:90, 40:60] = (90, 90, 120)  # body
    img[50:60, 45:55] = (250, 250, 250)  # white highlight inside the body
    img[20:30, 49:51] = (120, 60, 30)  # thin sword sticking out on top
    img[2:3, 2:3] = (0, 0, 0)  # 1 px speck
    mask = white_flood_cutout(img)
    assert mask[55, 50]  # inner white kept
    assert mask[25, 50]  # thin part kept
    assert not mask[2, 2]  # speck dropped
    assert not mask[5, 90]  # background removed
    assert mask.sum() == 60 * 20 + 10 * 2

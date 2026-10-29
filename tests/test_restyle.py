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


def test_anchor_mode_names_the_first_frame_and_keeps_default_wording():
    later = redraw_parts(b"S", b"G", b"P", "pixel")
    anchored = redraw_parts(b"S", b"G", b"P", "pixel", anchor=True)
    assert [p for p in anchored if isinstance(p, bytes)] == [b"S", b"P", b"G"]
    assert "approved first frame" in anchored[2] and "approved first frame" in anchored[-1]
    assert "previous animation frame" in later[2] and "first frame" not in later[-1]  # cached calls unchanged
    assert redraw_parts(b"S", b"G", None, "pixel", anchor=True) == redraw_parts(b"S", b"G", None, "pixel")


def test_hidden_legs_anchor_wording():
    import pytest

    legless = redraw_parts(b"S", b"G", b"P", "pixel", anchor=True, legs_hidden=True)
    assert "legs painted out" in legless[2] and "Draw every leg only from the pose guide" in legless[-1]
    with pytest.raises(ValueError):
        redraw_parts(b"S", b"G", b"P", "pixel", legs_hidden=True)  # only the anchor can be legless


def test_hide_legs_paints_the_bottom_of_the_figure_white():
    from actsprite.restyle import hide_legs

    rgb = np.zeros((100, 60, 3), np.uint8)
    mask = np.zeros((100, 60), bool)
    mask[20:80, 10:50] = True  # figure 60 px tall: bottom 35% = 21 rows -> rows 59..99 white
    out = hide_legs(rgb, mask, share=0.35)
    assert (out[59:] == 255).all() and (out[:59] == 0).all()
    assert (rgb == 0).all()  # input untouched


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


def test_biped_sheet_prompt_unchanged_and_quadruped_wording():
    from actsprite.restyle import REDRAW_PROMPT

    # Day 1 wording: keeps earlier knight calls cached (same prompt -> same sheet).
    assert ("normal body proportions about 6 heads tall, no cape, no cloak, no long scarf or other large "
            "flowing parts.") in sheet_prompt("x", "pixel")
    assert "four-legged" in sheet_prompt("x", "pixel", "quadruped")
    biped = redraw_parts(b"S", b"G", None, "pixel")[-1]
    assert "the arm positions and the body lean.\n" in biped
    dog = redraw_parts(b"S", b"G", None, "pixel", body="quadruped")[-1]
    assert "front and hind legs" in dog and "arm" not in dog
    assert "{" not in biped and "{" not in dog and "{pose_parts}" in REDRAW_PROMPT


def test_flood_cutout_closes_gaps_in_line_art():
    img = np.full((200, 200, 3), 255, np.uint8)
    img[40:162, 60:62] = img[40:162, 138:140] = 0  # left and right outline
    img[40:42, 60:140] = img[160:162, 60:140] = 0  # top and bottom outline
    img[100:104, 138:140] = 255  # 4 px break in the right side
    plain = white_flood_cutout(img)
    closed = white_flood_cutout(img, line_gaps=0.02)  # 4 px at 200 px
    assert not plain[100, 100]  # background leaked into the unfilled figure
    assert closed[100, 100] and closed[42:160, 62:138].all()
    assert not closed[20, 20] and not closed[100, 150]  # outside stays background up to the line

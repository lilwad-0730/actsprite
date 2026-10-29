import cv2
import numpy as np
import pytest

from actsprite.characters import custom_character, user_sheet
from actsprite.errors import PipelineError


def test_user_sheet_is_mirrored_and_padded_to_a_white_square(tmp_path):
    img = np.full((100, 40, 3), 255, np.uint8)
    img[:, :10] = 0  # dark stripe on the left
    path = tmp_path / "design.png"
    cv2.imwrite(str(path), img)
    sheet = user_sheet(custom_character("hero", sheet=path, faces_left=True))
    assert sheet.shape == (100, 100, 3)
    assert (sheet[:, 30:60] == 255).all() and (sheet[:, 60:70] == 0).all()  # stripe now on the right


def test_custom_character_needs_a_sheet_or_a_description():
    with pytest.raises(PipelineError):
        custom_character("hero")
    fox = custom_character("fox", description="an original fox ranger", body="quadruped")
    assert fox.sam_prompt == "animal" and fox.sheet_path is None
    with pytest.raises(PipelineError):
        custom_character("x", description="d", style="watercolor")

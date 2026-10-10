import pytest

from touchsight import braille as br


@pytest.mark.parametrize("text, expected", [
    ("cat", "⠉⠁⠞"),
    ("left atrium", "⠇⠑⠋⠞⠀⠁⠞⠗⠊⠥⠍"),
    ("abcdefghij", "⠁⠃⠉⠙⠑⠋⠛⠓⠊⠚"),
    ("klmnopqrst", "⠅⠇⠍⠝⠕⠏⠟⠗⠎⠞"),
    ("uvwxyz", "⠥⠧⠺⠭⠽⠵"),
    ("2026", "⠼⠃⠚⠃⠋"),
    ("3.5", "⠼⠉⠲⠑"),
])
def test_ueb_grade1(text, expected):
    assert br.to_unicode(text) == expected


def test_standalone_letter_gets_grade1_indicator():
    # without ⠰ a lone "n" reads as the contraction "not"
    assert br.to_unicode("n") == "⠰⠝"
    assert br.to_unicode("nu") == "⠝⠥"


def test_physical_width_matches_cell_pitch():
    cells = len(br.to_cells("nucleus"))
    assert br.width_mm("nucleus") == pytest.approx((cells - 1) * br.CELL_PITCH + br.DOT_GAP + 2 * br.DOT_R)


def test_dot_positions_follow_standard_spacing():
    a, b = br.dots("b", 0, 0)[-2:]  # 'b' = dots 1 and 2, below the grade-1 indicator cell
    assert b[1] - a[1] == pytest.approx(br.DOT_GAP)

"""Uncontracted English braille (UEB grade 1) with physical dot geometry.

Dimensions follow common signage/paper standards: dot diameter ~1.44 mm,
dot spacing within a cell 2.5 mm, cell-to-cell 6.2 mm, line-to-line 10 mm.
"""
from __future__ import annotations

DOT_R = 0.72      # mm
DOT_GAP = 2.5     # mm between dot centres in a cell
CELL_PITCH = 6.2  # mm between cell origins
LINE_PITCH = 10.0 # mm between braille lines
CELL_H = 2 * DOT_GAP + 2 * DOT_R   # visual height of a cell (~6.4 mm)

# dots numbered 1-3 down the left column, 4-6 down the right column
_LETTERS = {
    "a": "1", "b": "12", "c": "14", "d": "145", "e": "15", "f": "124", "g": "1245",
    "h": "125", "i": "24", "j": "245", "k": "13", "l": "123", "m": "134", "n": "1345",
    "o": "135", "p": "1234", "q": "12345", "r": "1235", "s": "234", "t": "2345",
    "u": "136", "v": "1236", "w": "2456", "x": "1346", "y": "13456", "z": "1356",
}
_PUNCT = {",": "2", ";": "23", ":": "25", ".": "256", "!": "235", "?": "236",
          "'": "3", "-": "36", "(": "2356", ")": "2356", "/": "34", "&": "12346"}
NUMBER_SIGN = "3456"
GRADE1_INDICATOR = "56"  # a standalone letter could be read as a contraction ("n" = "not") without it
_DIGITS = {"1": "a", "2": "b", "3": "c", "4": "d", "5": "e", "6": "f", "7": "g", "8": "h", "9": "i", "0": "j"}


def to_cells(text: str) -> list[str]:
    """Translate text to a list of cells, each a string of dot numbers ('' = blank)."""
    cells: list[str] = []
    if len(text.strip()) == 1 and text.strip().lower() in _LETTERS:
        cells.append(GRADE1_INDICATOR)
    in_number = False
    for ch in text.lower():
        if ch.isdigit():
            if not in_number:
                cells.append(NUMBER_SIGN)
                in_number = True
            cells.append(_LETTERS[_DIGITS[ch]])
            continue
        if ch != ".":
            in_number = False
        if ch in _LETTERS:
            cells.append(_LETTERS[ch])
        elif ch == " ":
            cells.append("")
        elif ch in _PUNCT:
            cells.append(_PUNCT[ch])
    return cells


def to_unicode(text: str) -> str:
    out = []
    for c in to_cells(text):
        code = 0x2800
        for d in c:
            code |= 1 << (int(d) - 1)
        out.append(chr(code))
    return "".join(out)


def width_mm(text: str) -> float:
    n = len(to_cells(text))
    return 0 if n == 0 else (n - 1) * CELL_PITCH + DOT_GAP + 2 * DOT_R


_OFFS = {"1": (0, 0), "2": (0, 1), "3": (0, 2), "4": (1, 0), "5": (1, 1), "6": (1, 2)}


def dots(text: str, x: float, y: float) -> list[tuple[float, float]]:
    """Dot centres (mm) for text whose top-left cell corner is at (x, y)."""
    pts = []
    for i, c in enumerate(to_cells(text)):
        cx = x + DOT_R + i * CELL_PITCH
        for d in c:
            col, row = _OFFS[d]
            pts.append((cx + col * DOT_GAP, y + DOT_R + row * DOT_GAP))
    return pts

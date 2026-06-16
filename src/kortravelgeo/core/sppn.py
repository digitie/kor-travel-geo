"""National point number parsing helpers.

The supported public form is two Korean 100 km grid letters followed by
four easting and four northing digits, for example ``다사 6925 4045``.
The returned EPSG:5179 coordinate is the center of the 10 m grid cell.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from kortravelgeo.dto.common import Point

GRID_LETTERS = "가나다라마바사아자차카타파하"
GRID_SIZE_M = 100_000
CELL_SIZE_M = 10
X_ORIGIN_5179 = 700_000
Y_ORIGIN_5179 = 1_300_000
KOREA_GRID_MIN_X_5179 = 700_000
KOREA_GRID_MAX_X_5179 = 1_400_000
KOREA_GRID_MIN_Y_5179 = 1_450_000
KOREA_GRID_MAX_Y_5179 = 2_100_000

_SPPN_RE = re.compile(
    rf"(?P<x_letter>[{GRID_LETTERS}])\s*(?P<y_letter>[{GRID_LETTERS}])"
    r"[\s-]*(?P<x_digits>\d{4})[\s-]*(?P<y_digits>\d{4})"
)


@dataclass(frozen=True, slots=True)
class NationalPointNumber:
    text: str
    compact: str
    x_letter: str
    y_letter: str
    x_digits: str
    y_digits: str
    point_5179: Point


def parse_national_point_number(value: str) -> NationalPointNumber | None:
    """Parse a national point number and return its EPSG:5179 cell center.

    The formula follows the 100 km Korean-letter grid and 10 m numeric cell
    convention used by national point numbers. Inputs that contain additional
    address text are rejected so normal 주소 geocoding is not hijacked by a
    coincidental two-letter/four-digit pattern.
    """

    stripped = value.strip()
    match = _SPPN_RE.fullmatch(stripped)
    if match is None:
        return None

    x_letter = match.group("x_letter")
    y_letter = match.group("y_letter")
    x_digits = match.group("x_digits")
    y_digits = match.group("y_digits")
    x_index = GRID_LETTERS.index(x_letter)
    y_index = GRID_LETTERS.index(y_letter)
    x = X_ORIGIN_5179 + x_index * GRID_SIZE_M + int(x_digits) * CELL_SIZE_M + 5
    y = Y_ORIGIN_5179 + y_index * GRID_SIZE_M + int(y_digits) * CELL_SIZE_M + 5
    point_5179 = Point(x=x, y=y)
    if not is_in_korea_grid_envelope(point_5179):
        return None
    compact = f"{x_letter}{y_letter}{x_digits}{y_digits}"
    text = f"{x_letter}{y_letter} {x_digits} {y_digits}"
    return NationalPointNumber(
        text=text,
        compact=compact,
        x_letter=x_letter,
        y_letter=y_letter,
        x_digits=x_digits,
        y_digits=y_digits,
        point_5179=point_5179,
    )


def format_national_point_number_from_5179(point: Point) -> NationalPointNumber | None:
    """Format an EPSG:5179 point as the containing 10 m national grid cell."""

    if not is_in_korea_grid_envelope(point):
        return None
    x_cell = _cell_index(point.x, X_ORIGIN_5179)
    y_cell = _cell_index(point.y, Y_ORIGIN_5179)
    if x_cell is None or y_cell is None:
        return None

    x_letter, x_digits = x_cell
    y_letter, y_digits = y_cell
    return parse_national_point_number(
        f"{x_letter}{y_letter} {x_digits:04d} {y_digits:04d}"
    )


def is_in_korea_grid_envelope(point: Point) -> bool:
    """Return whether a 5179 point is inside the supported Korea SPPN envelope."""

    return (
        KOREA_GRID_MIN_X_5179 <= point.x < KOREA_GRID_MAX_X_5179
        and KOREA_GRID_MIN_Y_5179 <= point.y < KOREA_GRID_MAX_Y_5179
    )


def _cell_index(value: float, origin: int) -> tuple[str, int] | None:
    offset = value - origin
    if offset < 0:
        return None
    grid_index = int(offset // GRID_SIZE_M)
    if grid_index >= len(GRID_LETTERS):
        return None
    grid_offset = offset - grid_index * GRID_SIZE_M
    digit = int(grid_offset // CELL_SIZE_M)
    if digit >= 10_000:
        return None
    return (GRID_LETTERS[grid_index], digit)

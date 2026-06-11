"""Units for quantity reporting.

All geometric quantities are in raw drawing units unless a scale is detected
or configured. Reports must always state the assumed unit.
"""

from enum import StrEnum


class Unit(StrEnum):
    COUNT = "count"
    DRAWING_UNITS = "drawing_units"
    DRAWING_UNITS_SQUARED = "drawing_units^2"


UNKNOWN_UNIT_ASSUMPTION = (
    "Lengths and areas are in raw drawing units; no scale or unit was detected"
)

from __future__ import annotations

from enum import Enum


class DistrictState(str, Enum):
    CLEAR = "clear"
    WARM = "warm"
    FRAYED = "frayed"
    HUNTING = "hunting"
    SEIZED = "seized"


def pressure_to_district_state(pressure: float) -> DistrictState:
    """Interpret persistent pressure as a district-scale condition.

    These thresholds are separate from the player survival banding.
    They describe how the district itself is doing.
    """
    if pressure < 0.50:
        return DistrictState.CLEAR
    if pressure < 1.25:
        return DistrictState.WARM
    if pressure < 2.25:
        return DistrictState.FRAYED
    if pressure < 3.50:
        return DistrictState.HUNTING
    return DistrictState.SEIZED

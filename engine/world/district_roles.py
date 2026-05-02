from __future__ import annotations

from typing import Tuple

ChunkCoord = Tuple[int, int]

ROLE_HUB = "hub"
ROLE_CORRIDOR = "corridor"
ROLE_SHELTER = "shelter"
ROLE_RELAY = "relay"
ROLE_INDUSTRIAL = "industrial"
ROLE_QUARANTINE = "quarantine"
ROLE_NEST = "nest"
ROLE_CIVIC = "civic"
ROLE_WILD = "wild"


def assign_district_role(coord: ChunkCoord, archetype: str) -> str:
    x, y = coord

    if coord == (0, 0):
        return ROLE_HUB

    # Explicit signature districts near hub.
    if coord == (1, 0):
        return ROLE_RELAY
    if coord == (0, -1):
        return ROLE_CIVIC
    if coord == (-1, 0):
        return ROLE_SHELTER
    if coord == (0, 1):
        return ROLE_CORRIDOR

    # Archetype-driven fallback roles.
    if archetype == "lane":
        return ROLE_CORRIDOR

    if archetype == "plaza":
        return ROLE_CIVIC

    if archetype == "dense":
        if x <= -2:
            return ROLE_QUARANTINE
        if y <= -2:
            return ROLE_INDUSTRIAL
        return ROLE_NEST

    if archetype == "room":
        if y < 0:
            return ROLE_SHELTER
        return ROLE_WILD

    return ROLE_WILD

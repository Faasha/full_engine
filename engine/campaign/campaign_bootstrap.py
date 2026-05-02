from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from engine.core.world_chunk import WorldChunk
from engine.world.district_state import pressure_to_district_state

ChunkCoord = Tuple[int, int]


@dataclass(slots=True)
class BootstrapSummary:
    profile: str
    changed_coords: List[ChunkCoord]
    notes: List[str]

    def to_dict(self) -> dict:
        return {
            "profile": self.profile,
            "changed_coords": [list(c) for c in self.changed_coords],
            "notes": self.notes[:],
        }


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _set_chunk(
    chunk: WorldChunk,
    *,
    pressure: float | None = None,
    civilians: float | None = None,
    hostiles: float | None = None,
    activation_count: int | None = None,
) -> None:
    baseline_civ = float(chunk.population.channels.civilians)
    baseline_host = float(chunk.population.channels.hostiles)

    if pressure is not None:
        chunk.state.pressure = _clamp(float(pressure), 0.0, 8.0)

    if civilians is not None:
        civ_cap = max(0.0, baseline_civ + 4.0)
        chunk.state.current_channels.civilians = _clamp(float(civilians), 0.0, civ_cap)

    if hostiles is not None:
        host_cap = max(0.0, baseline_host + 4.0)
        chunk.state.current_channels.hostiles = _clamp(float(hostiles), 0.0, host_cap)

    if activation_count is not None:
        chunk.state.activation_count = max(0, int(activation_count))


def apply_opening_crisis(chunks: Dict[ChunkCoord, WorldChunk]) -> BootstrapSummary:
    """
    Moderate opening:
    - city is stressed, not already lost
    - one clean early anchor target
    - one relay problem
    - one shelter pressure point
    - one industrial cooling problem
    - one nest-side future threat
    """
    for chunk in chunks.values():
        chunk.reset_persistent_state()
        chunk.state.anchor_strength = 0.0
        chunk.state.anchor_certified = False

    changed: list[ChunkCoord] = []

    def apply(coord: ChunkCoord, **kwargs) -> None:
        chunk = chunks.get(coord)
        if chunk is None:
            return
        _set_chunk(chunk, **kwargs)
        changed.append(coord)

    # Hub: stable and meaningful, not doomed.
    apply((0, 0), pressure=0.12, civilians=8.8, hostiles=0.0, activation_count=1)

    # Near-hub lines: these should create the first real choices.
    apply((0, -1), pressure=1.12, civilians=4.4, hostiles=0.9, activation_count=1)  # civic
    apply((1, 0), pressure=1.34, civilians=4.0, hostiles=1.4, activation_count=1)   # relay
    apply((-1, 0), pressure=1.22, civilians=5.3, hostiles=1.1, activation_count=1)  # shelter
    apply((0, 1), pressure=1.08, civilians=3.5, hostiles=1.3, activation_count=1)   # corridor

    # Industrial belt: the first real cooling target.
    apply((0, -2), pressure=1.86, civilians=1.8, hostiles=4.4, activation_count=2)
    apply((1, -2), pressure=1.62, civilians=1.9, hostiles=3.9, activation_count=2)
    apply((-1, -2), pressure=1.44, civilians=2.0, hostiles=3.5, activation_count=2)

    # West quarantine: dangerous but not campaign-ending.
    apply((-2, 0), pressure=1.58, civilians=1.9, hostiles=3.8, activation_count=2)
    apply((-2, -1), pressure=1.36, civilians=1.8, hostiles=3.3, activation_count=2)

    # Nest side: future threat, not immediate collapse.
    apply((2, 0), pressure=1.74, civilians=1.2, hostiles=4.1, activation_count=2)
    apply((2, -1), pressure=1.48, civilians=1.3, hostiles=3.7, activation_count=2)
    apply((0, 2), pressure=1.42, civilians=1.5, hostiles=3.5, activation_count=2)

    # Light wear in nearby rooms so the city reads as stressed.
    apply((-1, -1), pressure=0.82, civilians=3.0, hostiles=1.3, activation_count=1)
    apply((1, -1), pressure=0.84, civilians=3.0, hostiles=1.3, activation_count=1)
    apply((-1, 1), pressure=0.64, civilians=2.8, hostiles=1.1, activation_count=1)
    apply((1, 1), pressure=0.68, civilians=2.8, hostiles=1.1, activation_count=1)

    for chunk in chunks.values():
        chunk.district_state = pressure_to_district_state(chunk.state.pressure).value

    return BootstrapSummary(
        profile="opening_crisis_v2",
        changed_coords=sorted(set(changed)),
        notes=[
            "civic line is the cleanest early anchor",
            "relay line is pressured and strategically important",
            "shelter side carries civilians and rewards relief",
            "industrial belt is the first serious cooling target",
            "nest side is a future threat, not instant campaign failure",
        ],
    )

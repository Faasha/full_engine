from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple

from engine.core.world_chunk import WorldChunk

ChunkCoord = Tuple[int, int]


class MissionType(str, Enum):
    RELAY_RUN = "relay_run"
    RELIEF_RUN = "relief_run"
    RECOVERY_RUN = "recovery_run"
    EXTRACTION_RUN = "extraction_run"


class CargoType(str, Enum):
    RELAY_HEART = "relay_heart"
    MED_DISPERSAL = "med_dispersal"
    DAMPER_UNIT = "damper_unit"
    COOLANT_SPINE = "coolant_spine"
    EVAC_CIVILIAN = "evac_civilian"


@dataclass(slots=True)
class Mission:
    mission_type: MissionType
    cargo_type: CargoType
    source: ChunkCoord
    target: ChunkCoord
    picked_up: bool = False
    delivered: bool = False
    completed: bool = False
    failed: bool = False
    failure_reason: str = ""
    label: str = ""

    @property
    def phase(self) -> str:
        if self.failed:
            return "failed"
        if self.completed:
            return "complete"
        if self.delivered:
            return "delivered"
        if self.picked_up:
            return "to_target"
        return "to_source"

    def observe(self, player_chunk: ChunkCoord | None, *, overloaded: bool) -> None:
        if self.failed or self.completed:
            return

        if overloaded:
            self.failed = True
            self.failure_reason = "overloaded"
            return

        if player_chunk is None:
            return

        if not self.picked_up and player_chunk == self.source:
            self.picked_up = True
        elif self.picked_up and not self.delivered and player_chunk == self.target:
            self.delivered = True

    def finalize(self, *, overloaded: bool) -> None:
        if self.completed:
            return

        if overloaded:
            self.failed = True
            if not self.failure_reason:
                self.failure_reason = "overloaded"
            return

        if self.delivered:
            self.completed = True
            self.failed = False
            self.failure_reason = ""
        else:
            self.failed = True
            if not self.failure_reason:
                self.failure_reason = "incomplete"


def build_default_mission(chunks: Dict[ChunkCoord, WorldChunk]) -> Mission:
    missions = build_spindle_missions(chunks)
    return missions[0]


def build_spindle_missions(chunks: Dict[ChunkCoord, WorldChunk]) -> List[Mission]:
    """Build a small deterministic mission set that fits the current route grammar."""

    def pick(*coords: ChunkCoord) -> ChunkCoord:
        for coord in coords:
            if coord in chunks:
                return coord
        return next(iter(chunks.keys()))

    def hottest_non_hub(hub_coord: ChunkCoord) -> ChunkCoord:
        state_weight = {"clear": 0, "warm": 1, "frayed": 2, "hunting": 3, "seized": 4}
        candidates = [coord for coord in chunks.keys() if coord != hub_coord]
        if not candidates:
            return hub_coord

        def score(coord: ChunkCoord) -> tuple[float, float, float]:
            chunk = chunks[coord]
            return (
                float(state_weight.get(chunk.district_state, 0)),
                float(chunk.state.pressure),
                1.0 if chunk.archetype == "dense" else 0.0,
            )

        return max(candidates, key=score)

    hub = pick((0, 0))
    east_line = pick((1, 0), hub)
    south_line = pick((0, -1), east_line, hub)
    deep_dense = pick((1, -2), (0, -2), (2, -2), south_line, hub)
    far_dense = pick((2, -2), (1, -2), (0, -2), hub)
    hot_zone = hottest_non_hub(hub)

    missions: List[Mission] = [
        Mission(
            mission_type=MissionType.RELAY_RUN,
            cargo_type=CargoType.RELAY_HEART,
            source=east_line,
            target=deep_dense,
            label="relay run // reopen line",
        ),
        Mission(
            mission_type=MissionType.RELIEF_RUN,
            cargo_type=CargoType.MED_DISPERSAL,
            source=hub,
            target=south_line,
            label="relief run // stabilize district",
        ),
        Mission(
            mission_type=MissionType.RECOVERY_RUN,
            cargo_type=CargoType.DAMPER_UNIT,
            source=east_line,
            target=far_dense,
            label="damper run // cool hot route",
        ),
        Mission(
            mission_type=MissionType.EXTRACTION_RUN,
            cargo_type=CargoType.EVAC_CIVILIAN,
            source=hot_zone,
            target=hub,
            label="extraction run // pull civilian out",
        ),
    ]

    return missions

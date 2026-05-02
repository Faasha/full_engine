from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple

from engine.core.world_chunk import WorldChunk

ChunkCoord = Tuple[int, int]


class MissionType(str, Enum):
    RELAY_RUN = "relay_run"
    RELIEF_RUN = "relief_run"
    RECOVERY_RUN = "recovery_run"
    EXTRACTION_RUN = "extraction_run"
    STABILIZATION_RUN = "stabilization_run"


class CargoType(str, Enum):
    RELAY_HEART = "relay_heart"
    MED_DISPERSAL = "med_dispersal"
    DAMPER_UNIT = "damper_unit"
    COOLANT_SPINE = "coolant_spine"
    EVAC_CIVILIAN = "evac_civilian"
    STABILITY_LATTICE = "stability_lattice"


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _neighbors(coord: ChunkCoord, chunks: Dict[ChunkCoord, WorldChunk]) -> list[ChunkCoord]:
    x, y = coord
    out: list[ChunkCoord] = []
    for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if nxt in chunks:
            out.append(nxt)
    return out


def _route_chunks(
    source: ChunkCoord,
    target: ChunkCoord,
    chunks: Dict[ChunkCoord, WorldChunk],
) -> list[ChunkCoord]:
    if source not in chunks and target not in chunks:
        return []
    if source == target:
        return [source] if source in chunks else []
    if source not in chunks:
        return [target] if target in chunks else []
    if target not in chunks:
        return [source]

    frontier: list[ChunkCoord] = [source]
    came_from: dict[ChunkCoord, ChunkCoord | None] = {source: None}
    head = 0

    while head < len(frontier):
        coord = frontier[head]
        head += 1

        if coord == target:
            break

        for nxt in _neighbors(coord, chunks):
            if nxt not in came_from:
                came_from[nxt] = coord
                frontier.append(nxt)

    if target not in came_from:
        return [source, target]

    path: list[ChunkCoord] = []
    cursor: ChunkCoord | None = target
    while cursor is not None:
        path.append(cursor)
        cursor = came_from[cursor]
    path.reverse()
    return path


def _radius_chunks(
    center: ChunkCoord,
    chunks: Dict[ChunkCoord, WorldChunk],
    radius: int = 1,
) -> list[ChunkCoord]:
    out: list[ChunkCoord] = []
    cx, cy = center
    for coord in chunks:
        dx = abs(coord[0] - cx)
        dy = abs(coord[1] - cy)
        if dx + dy <= radius:
            out.append(coord)
    out.sort()
    return out


def _apply_chunk_delta(
    chunk: WorldChunk,
    *,
    pressure_delta: float = 0.0,
    civilian_delta: float = 0.0,
    hostile_delta: float = 0.0,
    civilian_cap_bonus: float = 0.0,
    hostile_cap_bonus: float = 0.0,
) -> dict[str, float]:
    before_pressure = float(chunk.state.pressure)
    before_civ = float(chunk.state.current_channels.civilians)
    before_host = float(chunk.state.current_channels.hostiles)

    baseline_civ = float(chunk.population.channels.civilians)
    baseline_host = float(chunk.population.channels.hostiles)

    chunk.state.pressure = _clamp(before_pressure + pressure_delta, 0.0, 8.0)

    civ_cap = max(0.0, baseline_civ + civilian_cap_bonus)
    host_cap = max(0.0, baseline_host + hostile_cap_bonus)

    chunk.state.current_channels.civilians = _clamp(before_civ + civilian_delta, 0.0, civ_cap)
    chunk.state.current_channels.hostiles = _clamp(before_host + hostile_delta, 0.0, host_cap)

    return {
        "pressure": round(chunk.state.pressure - before_pressure, 6),
        "civilians": round(chunk.state.current_channels.civilians - before_civ, 6),
        "hostiles": round(chunk.state.current_channels.hostiles - before_host, 6),
    }


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
    hold_seconds: float = 0.0
    progress_seconds: float = 0.0
    aftermath: dict[str, object] = field(default_factory=dict)

    @property
    def phase(self) -> str:
        if self.failed:
            return "failed"
        if self.completed:
            return "complete"
        if self.mission_type == MissionType.STABILIZATION_RUN:
            if self.delivered:
                return "stabilized"
            if self.picked_up and self.progress_seconds > 0.0:
                return "stabilizing"
        if self.delivered:
            return "delivered"
        if self.picked_up:
            return "to_target"
        return "to_source"

    def observe(
        self,
        player_chunk: ChunkCoord | None,
        *,
        overloaded: bool,
        dt: float = 0.0,
        chunks: Dict[ChunkCoord, WorldChunk] | None = None,
    ) -> None:
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
            self.progress_seconds = 0.0
            return

        if self.mission_type == MissionType.STABILIZATION_RUN:
            if not self.picked_up:
                return

            target_chunk = chunks.get(self.target) if chunks is not None else None

            if player_chunk == self.target:
                self.progress_seconds = min(
                    max(1.0, self.hold_seconds),
                    self.progress_seconds + dt,
                )
                if target_chunk is not None:
                    target_chunk.state.pressure = max(
                        0.0,
                        target_chunk.state.pressure - 0.60 * dt,
                    )

                target_stable = True
                if target_chunk is not None:
                    target_stable = (
                        target_chunk.state.pressure <= 1.25
                        or target_chunk.district_state in {"clear", "warm"}
                    )

                if self.progress_seconds >= max(1.0, self.hold_seconds) and target_stable:
                    if target_chunk is not None:
                        target_chunk.state.anchor_strength = max(target_chunk.state.anchor_strength, 1.0)
                        target_chunk.state.anchor_certified = True
                    self.delivered = True
            else:
                self.progress_seconds = max(0.0, self.progress_seconds - dt * 1.5)
            return

        if self.picked_up and not self.delivered and player_chunk == self.target:
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

    def apply_aftermath(self, chunks: Dict[ChunkCoord, WorldChunk]) -> dict[str, object]:
        if self.aftermath:
            return self.aftermath

        summary: dict[str, object] = {
            "applied": False,
            "mission_type": self.mission_type.value,
            "cargo_type": self.cargo_type.value,
            "affected_chunks": [],
            "pressure_delta_total": 0.0,
            "civilians_delta_total": 0.0,
            "hostiles_delta_total": 0.0,
            "notes": [],
        }

        if not self.completed or self.failed or not chunks:
            self.aftermath = summary
            return summary

        affected: list[dict[str, object]] = []

        def record(
            coord: ChunkCoord,
            *,
            pressure_delta: float = 0.0,
            civilian_delta: float = 0.0,
            hostile_delta: float = 0.0,
            civilian_cap_bonus: float = 0.0,
            hostile_cap_bonus: float = 0.0,
            note: str = "",
        ) -> None:
            chunk = chunks.get(coord)
            if chunk is None:
                return
            delta = _apply_chunk_delta(
                chunk,
                pressure_delta=pressure_delta,
                civilian_delta=civilian_delta,
                hostile_delta=hostile_delta,
                civilian_cap_bonus=civilian_cap_bonus,
                hostile_cap_bonus=hostile_cap_bonus,
            )
            if (
                delta["pressure"] != 0.0
                or delta["civilians"] != 0.0
                or delta["hostiles"] != 0.0
            ):
                affected.append(
                    {
                        "coord": [coord[0], coord[1]],
                        "archetype": chunk.archetype,
                        "note": note,
                        "delta": delta,
                    }
                )

        if self.mission_type == MissionType.RELAY_RUN:
            route = _route_chunks(self.source, self.target, chunks)
            for i, coord in enumerate(route):
                endpoint = i == 0 or i == len(route) - 1
                chunk = chunks[coord]
                record(
                    coord,
                    pressure_delta=-0.75 if endpoint else -0.55,
                    civilian_delta=0.25 if chunk.archetype in {"lane", "plaza"} else 0.10,
                    hostile_delta=-0.70 if chunk.archetype == "dense" else -0.45,
                    civilian_cap_bonus=1.25,
                    note="relay corridor reopened",
                )
            summary["notes"] = [
                "pressure reduced along the relay corridor",
                "hostile concentration cooled on the reopened line",
            ]

        elif self.mission_type == MissionType.RELIEF_RUN:
            for coord in _radius_chunks(self.target, chunks, radius=1):
                center = coord == self.target
                record(
                    coord,
                    pressure_delta=-0.85 if center else -0.35,
                    civilian_delta=1.25 if center else 0.40,
                    hostile_delta=-0.75 if center else -0.20,
                    civilian_cap_bonus=2.00 if center else 0.75,
                    note="relief dispersal restored civic activity",
                )
            summary["notes"] = [
                "target district received civilian recovery",
                "local hostile pressure was pushed down",
            ]

        elif self.mission_type == MissionType.STABILIZATION_RUN:
            for coord in _radius_chunks(self.target, chunks, radius=1):
                chunk = chunks[coord]
                if chunk.archetype not in {"lane", "room", "plaza"}:
                    continue
                center = coord == self.target
                record(
                    coord,
                    pressure_delta=-0.65 if center else -0.25,
                    civilian_delta=0.60 if center else 0.20,
                    hostile_delta=-0.45 if center else -0.15,
                    civilian_cap_bonus=1.25,
                    note="stability lattice hardened the civic line",
                )
            summary["notes"] = [
                "civic line hardened after hold completion",
                "district pressure was left in a cooler state",
            ]

        elif self.mission_type == MissionType.RECOVERY_RUN:
            for coord in _radius_chunks(self.target, chunks, radius=1):
                chunk = chunks[coord]
                center = coord == self.target
                dense_bias = chunk.archetype == "dense"
                record(
                    coord,
                    pressure_delta=-1.00 if center else (-0.50 if dense_bias else -0.25),
                    hostile_delta=-1.20 if center else (-0.60 if dense_bias else -0.25),
                    civilian_delta=0.20 if center and not dense_bias else 0.0,
                    civilian_cap_bonus=0.60,
                    note="damper field cooled the hot route",
                )
            summary["notes"] = [
                "dense-route escalation was suppressed",
                "future hostile rematerialization pressure should be lower nearby",
            ]

        elif self.mission_type == MissionType.EXTRACTION_RUN:
            route = _route_chunks(self.source, self.target, chunks)
            if route:
                record(
                    route[0],
                    pressure_delta=-0.55,
                    civilian_delta=-1.00,
                    hostile_delta=-0.60,
                    note="civilian extracted from hot zone",
                )
                for coord in route[1:-1]:
                    record(
                        coord,
                        pressure_delta=-0.20,
                        hostile_delta=-0.10,
                        note="extraction corridor stabilized",
                    )
                record(
                    route[-1],
                    pressure_delta=-0.35,
                    civilian_delta=1.00,
                    civilian_cap_bonus=3.00,
                    note="evacuee delivered to hub",
                )
            summary["notes"] = [
                "one civilian was pulled out of the hot zone",
                "hub stability improved after delivery",
            ]

        pressure_total = 0.0
        civilians_total = 0.0
        hostiles_total = 0.0
        for item in affected:
            delta = item["delta"]
            pressure_total += float(delta["pressure"])
            civilians_total += float(delta["civilians"])
            hostiles_total += float(delta["hostiles"])

        summary["applied"] = bool(affected)
        summary["affected_chunks"] = affected
        summary["pressure_delta_total"] = round(pressure_total, 6)
        summary["civilians_delta_total"] = round(civilians_total, 6)
        summary["hostiles_delta_total"] = round(hostiles_total, 6)

        self.aftermath = summary
        return summary


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

    def civic_fray_target(hub_coord: ChunkCoord) -> ChunkCoord:
        state_weight = {"clear": 0, "warm": 1, "frayed": 2, "hunting": 3, "seized": 4}
        candidates = [
            coord
            for coord, chunk in chunks.items()
            if coord != hub_coord and chunk.archetype in {"lane", "room", "plaza"}
        ]
        if not candidates:
            candidates = [coord for coord in chunks.keys() if coord != hub_coord]
        if not candidates:
            return hub_coord

        def score(coord: ChunkCoord) -> tuple[float, float, float]:
            chunk = chunks[coord]
            civic_bias = 1.0 if chunk.archetype == "lane" else 0.5 if chunk.archetype == "plaza" else 0.0
            return (
                float(state_weight.get(chunk.district_state, 0)),
                float(chunk.state.pressure),
                civic_bias,
            )

        return max(candidates, key=score)

    hub = pick((0, 0))
    east_line = pick((1, 0), hub)
    south_line = pick((0, -1), east_line, hub)
    deep_dense = pick((1, -2), (0, -2), (2, -2), south_line, hub)
    far_dense = pick((2, -2), (1, -2), (0, -2), hub)
    hot_zone = hottest_non_hub(hub)
    civic_line = civic_fray_target(hub)

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
            mission_type=MissionType.STABILIZATION_RUN,
            cargo_type=CargoType.STABILITY_LATTICE,
            source=hub,
            target=civic_line,
            label="stabilization run // hold district line",
            hold_seconds=8.0,
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

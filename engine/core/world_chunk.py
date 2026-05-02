"""Chunk data model for the world runtime.

Pressure-escalation tuning pass:
- chunk archetype
- multi-channel population
- persistent mutable state
- cheap background drift influenced by pressure
- activation leaves a regional fingerprint
- pressure influences future rematerialization
- stronger but bounded hostile escalation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from engine.systems.simple_collision_system import RectObstacle


ChunkCoord = Tuple[int, int]


@dataclass(slots=True)
class PopulationChannels:
    civilians: float = 0.0
    hostiles: float = 0.0

    def total(self) -> float:
        return self.civilians + self.hostiles

    def copy(self) -> "PopulationChannels":
        return PopulationChannels(
            civilians=self.civilians,
            hostiles=self.hostiles,
        )


@dataclass(slots=True)
class PopulationAnchor:
    channels: PopulationChannels = field(default_factory=PopulationChannels)
    seed: int = 0


@dataclass(slots=True)
class PersistentChunkState:
    current_channels: PopulationChannels = field(default_factory=PopulationChannels)
    pressure: float = 0.0
    last_active_tick: int = -1
    activation_count: int = 0
    anchor_strength: float = 0.0
    anchor_certified: bool = False

    def total(self) -> float:
        return self.current_channels.total()


@dataclass(slots=True)
class WorldChunk:
    coord: ChunkCoord
    archetype: str = "wild"
    district_state: str = "clear"
    district_role: str = "wild"
    obstacles: List[RectObstacle] = field(default_factory=list)
    population: PopulationAnchor = field(default_factory=PopulationAnchor)
    state: PersistentChunkState = field(default_factory=PersistentChunkState)
    tag: str = "wild"
    door_mask: str = ""

    def has_obstacles(self) -> bool:
        return bool(self.obstacles)

    def obstacle_tuples(self) -> list[tuple[float, float, float, float]]:
        return [(o.x, o.y, o.w, o.h) for o in self.obstacles]

    def civilian_count_hint(self) -> int:
        return max(0, int(round(self.state.current_channels.civilians)))

    def hostile_count_hint(self) -> int:
        return max(0, int(round(self.state.current_channels.hostiles)))

    def total_count_hint(self) -> int:
        return self.civilian_count_hint() + self.hostile_count_hint()

    def reset_persistent_state(self) -> None:
        self.state = PersistentChunkState(
            current_channels=self.population.channels.copy(),
            pressure=0.0,
            last_active_tick=-1,
            activation_count=0,
            anchor_strength=0.0,
            anchor_certified=False,
        )

    def on_activate(self, tick: int) -> None:
        self.state.last_active_tick = tick
        self.state.activation_count += 1

        pressure_gain = 0.25
        if self.archetype == "dense":
            pressure_gain = 0.34
        elif self.archetype == "lane":
            pressure_gain = 0.28
        elif self.archetype == "plaza":
            pressure_gain = 0.18

        self.state.pressure += pressure_gain
        if self.state.pressure > 8.0:
            self.state.pressure = 8.0

    def on_deactivate(self) -> None:
        cooldown = 0.96
        if self.archetype == "plaza":
            cooldown = 0.94
        elif self.archetype == "dense":
            cooldown = 0.975

        self.state.pressure *= cooldown
        if self.state.pressure < 0.0:
            self.state.pressure = 0.0

    def note_population_materialized(self, civilians: int, hostiles: int) -> None:
        self.state.current_channels.civilians -= civilians
        self.state.current_channels.hostiles -= hostiles

        if self.state.current_channels.civilians < 0.0:
            self.state.current_channels.civilians = 0.0
        if self.state.current_channels.hostiles < 0.0:
            self.state.current_channels.hostiles = 0.0

    def note_population_returned(self, civilians: int, hostiles: int) -> None:
        self.state.current_channels.civilians += civilians
        self.state.current_channels.hostiles += hostiles

        if self.state.current_channels.civilians < 0.0:
            self.state.current_channels.civilians = 0.0
        if self.state.current_channels.hostiles < 0.0:
            self.state.current_channels.hostiles = 0.0

    def apply_passive_drift(self) -> None:
        """Cheap background state evolution with stronger but bounded escalation."""
        pressure_decay = 0.995
        if self.archetype == "dense":
            pressure_decay = 0.997
        elif self.archetype == "plaza":
            pressure_decay = 0.992

        self.state.pressure *= pressure_decay
        if self.state.pressure < 0.0:
            self.state.pressure = 0.0

        baseline_civ = self.population.channels.civilians
        baseline_host = self.population.channels.hostiles
        p = self.state.pressure

        civ = self.state.current_channels.civilians
        host = self.state.current_channels.hostiles

        if self.archetype == "plaza":
            civ_recover = 0.0060
            host_growth = 0.0004
            civ_loss = 0.0010
            host_cool = 0.0030
        elif self.archetype == "lane":
            civ_recover = 0.0025
            host_growth = 0.0022
            civ_loss = 0.0020
            host_cool = 0.0010
        elif self.archetype == "dense":
            civ_recover = 0.0008
            host_growth = 0.0050
            civ_loss = 0.0030
            host_cool = 0.0004
        else:  # room
            civ_recover = 0.0018
            host_growth = 0.0020
            civ_loss = 0.0018
            host_cool = 0.0012

        civ -= civ_loss * p
        host += host_growth * p

        if p < 1.25:
            if civ < baseline_civ:
                civ += civ_recover
            if host > baseline_host:
                host -= host_cool

        civ_cap = baseline_civ + 1.5
        host_cap = baseline_host + (3.0 if self.archetype == "dense" else 2.0)

        if civ > civ_cap:
            civ = civ_cap
        if host > host_cap:
            host = host_cap

        if civ < 0.0:
            civ = 0.0
        if host < 0.0:
            host = 0.0

        self.state.current_channels.civilians = civ
        self.state.current_channels.hostiles = host

    def projected_materialization(self) -> tuple[int, int]:
        """Return the explicit population that should materialize now."""
        civ = self.state.current_channels.civilians
        host = self.state.current_channels.hostiles
        p = self.state.pressure

        civ_scale = 1.0
        host_scale = 1.0

        civ_scale -= min(0.45, p * 0.10)
        host_scale += min(0.85, p * 0.18)

        if self.archetype == "plaza":
            civ_scale += 0.12
            host_scale -= 0.14
        elif self.archetype == "lane":
            host_scale += 0.08
        elif self.archetype == "dense":
            civ_scale -= 0.08
            host_scale += 0.22

        if civ_scale < 0.20:
            civ_scale = 0.20
        if host_scale < 0.20:
            host_scale = 0.20

        materialized_civ = max(0, int(round(civ * civ_scale)))
        materialized_host = max(0, int(round(host * host_scale)))

        return materialized_civ, materialized_host


def _door_span(width: float, height: float) -> float:
    return min(width, height) * 0.28


def _build_outer_walls(
    *,
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    wall_thickness: float,
    door_mask: str,
) -> list[RectObstacle]:
    doors = set(door_mask.upper())
    obstacles: list[RectObstacle] = []

    door_span = _door_span(width, height)

    if "N" in doors:
        left_w = (width - door_span) * 0.5
        if left_w > 0:
            obstacles.append(RectObstacle(origin_x, origin_y + height - wall_thickness, left_w, wall_thickness))
            obstacles.append(RectObstacle(origin_x + left_w + door_span, origin_y + height - wall_thickness, left_w, wall_thickness))
    else:
        obstacles.append(RectObstacle(origin_x, origin_y + height - wall_thickness, width, wall_thickness))

    if "S" in doors:
        left_w = (width - door_span) * 0.5
        if left_w > 0:
            obstacles.append(RectObstacle(origin_x, origin_y, left_w, wall_thickness))
            obstacles.append(RectObstacle(origin_x + left_w + door_span, origin_y, left_w, wall_thickness))
    else:
        obstacles.append(RectObstacle(origin_x, origin_y, width, wall_thickness))

    if "W" in doors:
        low_h = (height - door_span) * 0.5
        if low_h > 0:
            obstacles.append(RectObstacle(origin_x, origin_y, wall_thickness, low_h))
            obstacles.append(RectObstacle(origin_x, origin_y + low_h + door_span, wall_thickness, low_h))
    else:
        obstacles.append(RectObstacle(origin_x, origin_y, wall_thickness, height))

    if "E" in doors:
        low_h = (height - door_span) * 0.5
        if low_h > 0:
            obstacles.append(RectObstacle(origin_x + width - wall_thickness, origin_y, wall_thickness, low_h))
            obstacles.append(RectObstacle(origin_x + width - wall_thickness, origin_y + low_h + door_span, wall_thickness, low_h))
    else:
        obstacles.append(RectObstacle(origin_x + width - wall_thickness, origin_y, wall_thickness, height))

    return obstacles


def _add_lane_interior(
    obstacles: list[RectObstacle],
    *,
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    wall_thickness: float,
) -> None:
    bar_w = wall_thickness
    bar_h = height * 0.32
    x = origin_x + width * 0.5 - bar_w * 0.5
    y = origin_y + height * 0.5 - bar_h * 0.5
    obstacles.append(RectObstacle(x, y, bar_w, bar_h))


def _add_dense_interior(
    obstacles: list[RectObstacle],
    *,
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    wall_thickness: float,
) -> None:
    block_w = width * 0.16
    block_h = height * 0.16
    obstacles.append(RectObstacle(origin_x + width * 0.22, origin_y + height * 0.22, block_w, block_h))
    obstacles.append(RectObstacle(origin_x + width * 0.62, origin_y + height * 0.58, block_w, block_h))


def _add_plaza_interior(
    obstacles: list[RectObstacle],
    *,
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    wall_thickness: float,
) -> None:
    size = min(width, height) * 0.10
    obstacles.append(RectObstacle(origin_x + width * 0.18, origin_y + height * 0.18, size, size))
    obstacles.append(RectObstacle(origin_x + width * 0.72, origin_y + height * 0.18, size, size))
    obstacles.append(RectObstacle(origin_x + width * 0.18, origin_y + height * 0.72, size, size))
    obstacles.append(RectObstacle(origin_x + width * 0.72, origin_y + height * 0.72, size, size))


def make_room_chunk(
    coord: ChunkCoord,
    *,
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
    wall_thickness: float = 24.0,
    door_mask: str = "",
    civilians: float = 0.0,
    hostiles: float = 0.0,
    seed: int = 0,
    tag: str = "room",
    archetype: str = "room",
    district_role: str = "wild",
) -> WorldChunk:
    obstacles = _build_outer_walls(
        origin_x=origin_x,
        origin_y=origin_y,
        width=width,
        height=height,
        wall_thickness=wall_thickness,
        door_mask=door_mask,
    )

    if archetype == "lane":
        _add_lane_interior(obstacles, origin_x=origin_x, origin_y=origin_y, width=width, height=height, wall_thickness=wall_thickness)
    elif archetype == "dense":
        _add_dense_interior(obstacles, origin_x=origin_x, origin_y=origin_y, width=width, height=height, wall_thickness=wall_thickness)
    elif archetype == "plaza":
        _add_plaza_interior(obstacles, origin_x=origin_x, origin_y=origin_y, width=width, height=height, wall_thickness=wall_thickness)

    channels = PopulationChannels(civilians=civilians, hostiles=hostiles)

    return WorldChunk(
        coord=coord,
        archetype=archetype,
        district_role=district_role,
        obstacles=obstacles,
        population=PopulationAnchor(channels=channels.copy(), seed=seed),
        state=PersistentChunkState(
            current_channels=channels.copy(),
            pressure=0.0,
            last_active_tick=-1,
            activation_count=0,
            anchor_strength=0.0,
            anchor_certified=False,
        ),
        tag=tag,
        door_mask=door_mask,
    )

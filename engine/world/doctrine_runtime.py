from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from engine.components.agent_state import AgentState
from engine.core.world_chunk import WorldChunk
from engine.core.world_grid import ChunkCoord, WorldGrid
from engine.world.district_state import pressure_to_district_state

EntityID = Tuple[int, int]


@dataclass(slots=True)
class ChunkTelemetry:
    baseline_civ: float
    baseline_host: float
    final_civ: float
    final_host: float
    final_pressure: float
    activation_count: int
    archetype: str


def apply_background_drift(
    chunks: Dict[ChunkCoord, WorldChunk],
    warm_chunks: set[ChunkCoord],
) -> None:
    for coord, chunk in chunks.items():
        if coord not in warm_chunks:
            chunk.apply_passive_drift()


def update_district_states(chunks: Dict[ChunkCoord, WorldChunk]) -> list[str]:
    changes: list[str] = []

    for coord, chunk in chunks.items():
        prev = chunk.district_state
        curr = pressure_to_district_state(chunk.state.pressure).value

        if curr != prev:
            changes.append(f"{coord}:{prev}->{curr}")

        chunk.district_state = curr

    return changes


def count_explicit_population(world, ecs, player_id: EntityID) -> tuple[int, int]:
    civilians = 0
    hostiles = 0

    for entity_id in world.index_to_entity:
        if entity_id == player_id:
            continue

        agent_state = ecs.get_component(entity_id, AgentState)
        if agent_state is None:
            continue

        if agent_state.kind == "hostile":
            hostiles += 1
        else:
            civilians += 1

    return civilians, hostiles


def count_active_abstract_population(
    chunks: Dict[ChunkCoord, WorldChunk],
    active_chunks: set[ChunkCoord],
) -> tuple[int, int]:
    civilians = 0
    hostiles = 0

    for coord in active_chunks:
        chunk = chunks.get(coord)
        if chunk is None:
            continue

        civilians += chunk.civilian_count_hint()
        hostiles += chunk.hostile_count_hint()

    return civilians, hostiles


def average_live_speeds(world, ecs, player_id: EntityID) -> tuple[float, float]:
    civ_total = 0.0
    civ_count = 0
    host_total = 0.0
    host_count = 0

    for entity_id in world.index_to_entity:
        if entity_id == player_id:
            continue

        agent_state = ecs.get_component(entity_id, AgentState)
        if agent_state is None:
            continue

        idx = world.entity_to_index[entity_id]
        vx = world.vel_x[idx]
        vy = world.vel_y[idx]
        speed = (vx * vx + vy * vy) ** 0.5

        if agent_state.kind == "hostile":
            host_total += speed
            host_count += 1
        else:
            civ_total += speed
            civ_count += 1

    return (
        civ_total / civ_count if civ_count else 0.0,
        host_total / host_count if host_count else 0.0,
    )


def build_chunk_overlay(
    chunks: Dict[ChunkCoord, WorldChunk],
    grid: WorldGrid,
    active_chunks: set[ChunkCoord],
) -> list[dict[str, object]]:
    overlay: list[dict[str, object]] = []

    for coord, chunk in chunks.items():
        x0, y0, x1, y1 = grid.chunk_bounds(coord)
        overlay.append(
            {
                "coord": coord,
                "x": x0,
                "y": y0,
                "w": x1 - x0,
                "h": y1 - y0,
                "pressure": float(chunk.state.pressure),
                "active": coord in active_chunks,
                "archetype": chunk.archetype,
                "district_state": chunk.district_state,
            }
        )

    return overlay


def active_pressure_summary(
    chunks: Dict[ChunkCoord, WorldChunk],
    active_chunks: set[ChunkCoord],
) -> tuple[float, Dict[str, int]]:
    pressure = 0.0
    archetypes: Dict[str, int] = {}

    for coord in active_chunks:
        chunk = chunks.get(coord)
        if chunk is None:
            continue

        pressure += chunk.state.pressure
        archetypes[chunk.archetype] = archetypes.get(chunk.archetype, 0) + 1

    return pressure, archetypes


def build_state_counts(chunks: Dict[ChunkCoord, WorldChunk]) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for chunk in chunks.values():
        counts[chunk.district_state] = counts.get(chunk.district_state, 0) + 1

    return counts


def rehydrate_active_chunk_population(
    chunks: Dict[ChunkCoord, WorldChunk],
    chunk_entities: Dict[ChunkCoord, List[EntityID]],
    ecs,
) -> None:
    for coord, entity_ids in chunk_entities.items():
        chunk = chunks.get(coord)
        if chunk is None:
            continue

        returned_civ = 0
        returned_host = 0

        for entity_id in entity_ids:
            agent_state = ecs.get_component(entity_id, AgentState)
            if agent_state is None:
                continue

            if agent_state.kind == "hostile":
                returned_host += 1
            else:
                returned_civ += 1

        if returned_civ or returned_host:
            chunk.note_population_returned(returned_civ, returned_host)


def build_chunk_telemetry(
    chunks: Dict[ChunkCoord, WorldChunk],
    baseline: Dict[ChunkCoord, tuple[float, float]],
) -> Dict[ChunkCoord, ChunkTelemetry]:
    telemetry: Dict[ChunkCoord, ChunkTelemetry] = {}

    for coord, chunk in chunks.items():
        baseline_civ, baseline_host = baseline[coord]
        telemetry[coord] = ChunkTelemetry(
            baseline_civ=baseline_civ,
            baseline_host=baseline_host,
            final_civ=chunk.state.current_channels.civilians,
            final_host=chunk.state.current_channels.hostiles,
            final_pressure=chunk.state.pressure,
            activation_count=chunk.state.activation_count,
            archetype=chunk.archetype,
        )

    return telemetry


def top_pressure_chunks(
    telemetry: Dict[ChunkCoord, ChunkTelemetry],
) -> list[tuple[ChunkCoord, ChunkTelemetry]]:
    return sorted(telemetry.items(), key=lambda item: item[1].final_pressure, reverse=True)[:5]


def top_hostile_growth(
    telemetry: Dict[ChunkCoord, ChunkTelemetry],
) -> list[tuple[ChunkCoord, ChunkTelemetry]]:
    return sorted(
        telemetry.items(),
        key=lambda item: item[1].final_host - item[1].baseline_host,
        reverse=True,
    )[:5]


def top_civilian_loss(
    telemetry: Dict[ChunkCoord, ChunkTelemetry],
) -> list[tuple[ChunkCoord, ChunkTelemetry]]:
    return sorted(
        telemetry.items(),
        key=lambda item: item[1].baseline_civ - item[1].final_civ,
        reverse=True,
    )[:5]


def most_activated_chunks(
    telemetry: Dict[ChunkCoord, ChunkTelemetry],
) -> list[tuple[ChunkCoord, ChunkTelemetry]]:
    return sorted(telemetry.items(), key=lambda item: item[1].activation_count, reverse=True)[:5]


def build_doctrine_snapshot(
    *,
    chunks,
    active_chunks,
    chunk_telemetry_start,
):
    active_pressure, active_archetypes = active_pressure_summary(chunks, active_chunks)
    district_state_counts = build_state_counts(chunks)
    telemetry = build_chunk_telemetry(chunks, chunk_telemetry_start)

    return {
        "world_pressure_total": sum(chunk.state.pressure for chunk in chunks.values()),
        "active_pressure": active_pressure,
        "active_archetypes": active_archetypes,
        "district_state_counts": district_state_counts,
        "top_pressure_chunks": top_pressure_chunks(telemetry),
        "top_hostile_growth": top_hostile_growth(telemetry),
        "top_civilian_loss": top_civilian_loss(telemetry),
        "most_activated_chunks": most_activated_chunks(telemetry),
    }

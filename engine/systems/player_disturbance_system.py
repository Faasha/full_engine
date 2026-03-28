from __future__ import annotations

from typing import Dict

from engine.components.player_state import PlayerState
from engine.components.player_tag import PlayerTag
from engine.components.transform import Transform
from engine.core.ecs import ECS
from engine.core.world_chunk import WorldChunk
from engine.core.world_grid import ChunkCoord, WorldGrid


def pressure_band(value: float) -> str:
    if value < 1.00:
        return "calm"
    if value < 2.40:
        return "tense"
    return "hostile"


def update_player_disturbance(
    ecs: ECS,
    chunks: Dict[ChunkCoord, WorldChunk],
    grid: WorldGrid,
    *,
    dt: float,
) -> dict[str, object]:
    player_entity = None
    for entity_id, (_tag,) in ecs.iter_entities(PlayerTag):
        player_entity = entity_id
        break

    if player_entity is None:
        return {
            "chunk": None,
            "pressure": 0.0,
            "band": "calm",
            "strain": 0.0,
            "archetype": "none",
            "overloaded": False,
            "survival_state": "stable",
        }

    transform = ecs.get_component(player_entity, Transform)
    player_state = ecs.get_component(player_entity, PlayerState)
    if transform is None or player_state is None:
        return {
            "chunk": None,
            "pressure": 0.0,
            "band": "calm",
            "strain": 0.0,
            "archetype": "none",
            "overloaded": False,
            "survival_state": "stable",
        }

    px, py = transform.position
    coord = grid.world_to_chunk(px, py)
    chunk = chunks.get(coord)

    if chunk is None:
        overloaded = player_state.strain >= player_state.max_strain
        return {
            "chunk": coord,
            "pressure": 0.0,
            "band": "calm",
            "strain": player_state.strain,
            "archetype": "void",
            "overloaded": overloaded,
            "survival_state": "overloaded" if overloaded else "stable",
        }

    # Softer local heating. The world should tighten, not instantly cook the player.
    pressure_gain = 0.05 * dt
    if chunk.archetype == "dense":
        pressure_gain = 0.12 * dt
    elif chunk.archetype == "lane":
        pressure_gain = 0.08 * dt
    elif chunk.archetype == "plaza":
        pressure_gain = 0.01 * dt

    chunk.state.pressure += pressure_gain
    if chunk.state.pressure > 8.0:
        chunk.state.pressure = 8.0

    band = pressure_band(chunk.state.pressure)

    # Survival curve:
    # - plaza should recover strain
    # - tense should be pressure, not automatic death
    # - hostile dense should hurt, but still allow a route if the player moves
    if chunk.archetype == "plaza":
        if band == "hostile":
            strain_delta = -2.0 * dt
        elif band == "tense":
            strain_delta = -6.0 * dt
        else:
            strain_delta = -10.0 * dt
    elif chunk.archetype == "lane":
        if band == "calm":
            strain_delta = -1.5 * dt
        elif band == "tense":
            strain_delta = 1.5 * dt
        else:
            strain_delta = 3.5 * dt
    elif chunk.archetype == "dense":
        if band == "calm":
            strain_delta = 0.5 * dt
        elif band == "tense":
            strain_delta = 2.5 * dt
        else:
            strain_delta = 5.0 * dt
    else:  # room
        if band == "calm":
            strain_delta = -0.5 * dt
        elif band == "tense":
            strain_delta = 2.0 * dt
        else:
            strain_delta = 4.0 * dt

    player_state.strain += strain_delta

    if player_state.strain < 0.0:
        player_state.strain = 0.0
    if player_state.strain > player_state.max_strain:
        player_state.strain = player_state.max_strain

    overloaded = player_state.strain >= player_state.max_strain

    if overloaded:
        survival_state = "overloaded"
    elif player_state.strain >= player_state.max_strain * 0.80:
        survival_state = "critical"
    elif player_state.strain >= player_state.max_strain * 0.45:
        survival_state = "strained"
    else:
        survival_state = "stable"

    return {
        "chunk": coord,
        "pressure": chunk.state.pressure,
        "band": band,
        "strain": player_state.strain,
        "archetype": chunk.archetype,
        "overloaded": overloaded,
        "survival_state": survival_state,
    }

"""System to dissolve distant entities into the behavioural field.

This version updates OccupancyMap incrementally so we do not have to
rebuild local active-cell counts from scratch every tick.
"""

from __future__ import annotations

from engine.core.ecs import ECS
from engine.core.flat_world import FlatWorld
from engine.core.occupancy_map import OccupancyMap
from engine.components.transform import Transform
from engine.components.velocity import Velocity
from .field_system import FieldSystem


def dissolve_distant_entities(
    ecs: ECS,
    field: FieldSystem,
    *,
    occupancy: OccupancyMap,
    world: FlatWorld | None = None,
    radius: float = 400.0,
    cell_size: float = 50.0,
) -> int:
    """Dissolve entities that are further than ``radius`` from the origin.

    Entities outside the active simulation radius are removed from the ECS and
    their influence is added to the behavioural field. Each entity contributes
    a unit weight of 1.0 to conserve mass.

    If ``world`` is provided, the entity is also removed from FlatWorld.
    Occupancy is decremented for the entity's local cell.
    """
    to_dissolve: list[tuple[tuple[int, int], float, float, float]] = []
    w = field.width
    h = field.height
    half_w = w // 2
    half_h = h // 2
    radius_sq = radius * radius

    if world is not None:
        for idx, entity_id in enumerate(world.index_to_entity):
            x = world.pos_x[idx]
            y = world.pos_y[idx]
            if x * x + y * y > radius_sq:
                to_dissolve.append((entity_id, x, y, 1.0))
    else:
        for entity_id, (transform, velocity) in ecs.iter_entities(Transform, Velocity):
            x, y = transform.position
            if x * x + y * y > radius_sq:
                to_dissolve.append((entity_id, x, y, 1.0))

    count = 0
    for entity_id, x, y, weight in to_dissolve:
        # Local occupancy cell relative to origin
        local_cx, local_cy = occupancy.world_to_cell(x, y)
        occupancy.decrement(local_cx, local_cy, 1)

        # Field cell relative to field centre
        cx = int(x / cell_size) + half_w
        cy = int(y / cell_size) + half_h

        if cx < 0:
            cx = 0
        elif cx >= w:
            cx = w - 1

        if cy < 0:
            cy = 0
        elif cy >= h:
            cy = h - 1

        field.dissolve(cx, cy, weight)

        if world is not None and world.has(entity_id):
            world.remove(entity_id)

        ecs.destroy_entity(entity_id)
        count += 1

    return count

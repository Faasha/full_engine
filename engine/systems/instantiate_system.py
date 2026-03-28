"""System to instantiate entities from the behavioural field.

This version uses OccupancyMap so we do not rebuild per-cell active
counts from scratch every tick.

Key improvements:
- only scans active field cells within spawn radius
- uses a persistent occupancy map instead of rebuilding counts
- preserves mass exactly by returning all unconsumed mass
- inserts spawned entities into FlatWorld when provided
"""

from __future__ import annotations

import random

from engine.core.ecs import ECS
from engine.core.flat_world import FlatWorld
from engine.core.occupancy_map import OccupancyMap
from engine.components.transform import Transform
from engine.components.velocity import Velocity
from engine.components.renderable import Renderable
from engine.assets.asset_manager import AssetManager
from .field_system import FieldSystem


def instantiate_from_field(
    ecs: ECS,
    field: FieldSystem,
    assets: AssetManager,
    *,
    occupancy: OccupancyMap,
    world: FlatWorld | None = None,
    spawn_radius: float = 300.0,
    cell_size: float = 50.0,
    threshold: float = 10.0,
    max_entities_per_cell: int = 1,
    mesh_handle: int | None = None,
    material_handle: int | None = None,
) -> int:
    """Instantiate entities near the origin based on field density.

    Only active field cells inside the spawn radius are considered.

    If a cell's field value exceeds ``threshold`` and there are fewer than
    ``max_entities_per_cell`` active entities already occupying that local
    cell, one or more entities may be spawned.

    Any unconsumed mass is returned to the field so total mass remains
    conserved.

    Parameters
    ----------
    ecs:
        Authoritative entity-lifecycle store.
    field:
        Behavioural field containing distant aggregate mass.
    assets:
        Asset manager used when handles are not provided.
    occupancy:
        Persistent occupancy tracker for local active cells.
    world:
        Authoritative hot-state storage. When provided, spawned entities are
        inserted into FlatWorld immediately.
    """
    width, height = field.width, field.height
    half_w = width // 2
    half_h = height // 2
    max_cell = int(spawn_radius / cell_size)
    spawned_total = 0

    if mesh_handle is None:
        mesh_handle = assets.create_asset("agent_mesh")
    if material_handle is None:
        material_handle = assets.create_asset("agent_material")

    # Only inspect active cells inside the spawn radius.
    candidate_cells = field.active_cells_within_radius(max_cell)

    for x_idx, y_idx in candidate_cells:
        # Cheap prefilter: do not consume/restore cells below threshold.
        peek = field.get(x_idx, y_idx)
        if peek <= threshold:
            continue

        value = field.instantiate(x_idx, y_idx)

        # Safety fallback if value changed between peek and consume.
        if value <= threshold:
            if value > 0.0:
                field.dissolve(x_idx, y_idx, value)
            continue

        # Convert grid coordinates to local cell coordinates relative to origin.
        cx = x_idx - half_w
        cy = y_idx - half_h

        current = occupancy.get(cx, cy)
        if current >= max_entities_per_cell:
            field.dissolve(x_idx, y_idx, value)
            continue

        available = max_entities_per_cell - current

        desired = int(value)
        if desired < 1:
            desired = 1

        count = min(desired, available)
        if count <= 0:
            field.dissolve(x_idx, y_idx, value)
            continue

        leftover = value - count
        if leftover > 0.0:
            field.dissolve(x_idx, y_idx, leftover)

        world_x = (cx + 0.5) * cell_size
        world_y = (cy + 0.5) * cell_size

        for _ in range(count):
            vx = random.uniform(-20.0, 20.0)
            vy = random.uniform(-20.0, 20.0)

            entity_id = ecs.create_entity(
                {
                    Transform: Transform(position=(world_x, world_y)),
                    Velocity: Velocity(value=(vx, vy)),
                    Renderable: Renderable(
                        mesh_handle=mesh_handle,
                        material_handle=material_handle,
                    ),
                }
            )

            if world is not None:
                world.add(
                    entity_id,
                    world_x,
                    world_y,
                    vx,
                    vy,
                    mesh_handle,
                    material_handle,
                )

            occupancy.increment(cx, cy, 1)
            spawned_total += 1

    return spawned_total

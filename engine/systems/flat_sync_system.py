"""Sync helpers between ECS and FlatWorld.

These helpers let the runtime bridge from the older ECS-centered layout
to the newer flat hot-path layout. The ECS remains useful for entity
identity, cold state, and structural bookkeeping, while FlatWorld is
used for high-frequency movement and render extraction.
"""

from __future__ import annotations

from engine.core.ecs import ECS
from engine.core.flat_world import FlatWorld
from engine.components.transform import Transform
from engine.components.velocity import Velocity
from engine.components.renderable import Renderable


def build_flat_world_from_ecs(ecs: ECS, world: FlatWorld) -> None:
    """Rebuild FlatWorld entirely from ECS state."""
    world.clear()

    for entity_id, (transform, velocity, renderable) in ecs.iter_entities(
        Transform, Velocity, Renderable
    ):
        x, y = transform.position
        vx, vy = velocity.value
        world.add(
            entity_id,
            x,
            y,
            vx,
            vy,
            renderable.mesh_handle,
            renderable.material_handle,
        )


def add_entity_to_flat_world(ecs: ECS, world: FlatWorld, entity_id: tuple[int, int]) -> None:
    """Add one ECS entity into FlatWorld if it has the required hot components."""
    transform = ecs.get_component(entity_id, Transform)
    velocity = ecs.get_component(entity_id, Velocity)
    renderable = ecs.get_component(entity_id, Renderable)

    if transform is None or velocity is None or renderable is None:
        return

    x, y = transform.position
    vx, vy = velocity.value
    world.add(
        entity_id,
        x,
        y,
        vx,
        vy,
        renderable.mesh_handle,
        renderable.material_handle,
    )


def remove_entity_from_flat_world(world: FlatWorld, entity_id: tuple[int, int]) -> None:
    """Remove one entity from FlatWorld if present."""
    if world.has(entity_id):
        world.remove(entity_id)


def write_flat_positions_back_to_ecs(ecs: ECS, world: FlatWorld) -> None:
    """Write FlatWorld positions back into ECS Transform components.

    This should not be done every tick in the hot path. It is mainly for:
    - final snapshots
    - debugging
    - compatibility with slower ECS-based systems
    """
    transforms = ecs.get_component_array(Transform)

    for idx, entity_id in enumerate(world.index_to_entity):
        row = ecs.entity_row(entity_id)
        transform = transforms[row]
        if transform is not None:
            transform.position = (world.pos_x[idx], world.pos_y[idx])

"""Movement system.

Integrates velocity into position for entities possessing both
``Transform`` and ``Velocity`` components.  The system is designed to
operate on dense arrays stored in the ECS; it performs no per‑entity
allocations and avoids hidden overhead.
"""

from __future__ import annotations

from typing import Tuple

from engine.core.ecs import ECS
from engine.components.transform import Transform
from engine.components.velocity import Velocity


def update_movement(ecs: ECS, dt: float) -> None:
    """Integrate velocity into position for all entities with both Transform and Velocity.

    This implementation retrieves the raw component arrays from the ECS and
    iterates over rows directly.  It avoids per-entity tuple packing and
    repeated dictionary lookups, significantly reducing overhead in hot
    paths.
    """
    transforms = ecs.get_component_array(Transform)
    velocities = ecs.get_component_array(Velocity)
    row_count = ecs.rows()
    for row in range(row_count):
        transform = transforms[row]
        velocity = velocities[row]
        if transform is None or velocity is None:
            continue
        x, y = transform.position
        vx, vy = velocity.value
        transform.position = (x + vx * dt, y + vy * dt)
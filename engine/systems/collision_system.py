"""Simple collision system for bounding boxes.

This system handles collisions between dynamic entities (those with
``Transform``, ``Velocity`` and ``Collider`` components) and static
world boundaries or obstacles.  When a moving entity's bounding
box intersects a world boundary or obstacle, its velocity is
reflected along the axis of collision.  The system also prevents
entities from passing through the boundaries by clamping their
positions to the valid range.

The system does not handle collisions between moving entities (no
entity–entity collision); it only resolves collisions against
immovable obstacles and the world extents.  Obstacles are provided
as a list of axis‑aligned bounding boxes defined by (x, y, w, h).
"""

from __future__ import annotations

from typing import Iterable, List, Tuple

from engine.core.ecs import ECS
from engine.components.transform import Transform
from engine.components.velocity import Velocity
from engine.components.collider import Collider


def handle_collisions(
    ecs: ECS,
    world_bounds: Tuple[float, float, float, float],
    obstacles: Iterable[Tuple[float, float, float, float]],
) -> None:
    """Resolve collisions against boundaries and static obstacles.

    Parameters
    ----------
    ecs:
        The entity–component system managing entity state.
    world_bounds:
        A tuple ``(min_x, min_y, max_x, max_y)`` defining the
        rectangular area in which entities are allowed to move.  If an
        entity exceeds these bounds, its velocity is reflected and
        position clamped.
    obstacles:
        An iterable of axis‑aligned rectangles ``(x, y, w, h)``
        representing static obstacles.  The coordinates define the
        centre of the rectangle; ``w`` and ``h`` are the width and
        height.  Collisions are resolved by reflecting the velocity
        component along the axis of overlap.
    """
    # Unpack world boundaries for clarity
    min_x, min_y, max_x, max_y = world_bounds
    transforms = ecs.get_component_array(Transform)
    velocities = ecs.get_component_array(Velocity)
    colliders = ecs.get_component_array(Collider)
    row_count = ecs.rows()

    # Preprocess obstacles into half‑extents
    proc_obstacles: List[Tuple[float, float, float, float]] = []
    for ox, oy, ow, oh in obstacles:
        hx = ow / 2.0
        hy = oh / 2.0
        proc_obstacles.append((ox, oy, hx, hy))

    for row in range(row_count):
        transform = transforms[row]
        velocity = velocities[row]
        collider = colliders[row]

        if transform is None or velocity is None or collider is None:
            continue

        x, y = transform.position
        vx, vy = velocity.value
        half_w, half_h = collider.size[0] / 2.0, collider.size[1] / 2.0

        # Check world boundaries along X
        if x - half_w < min_x:
            x = min_x + half_w
            vx = abs(vx)  # bounce to the right
        elif x + half_w > max_x:
            x = max_x - half_w
            vx = -abs(vx)  # bounce to the left

        # Check world boundaries along Y
        if y - half_h < min_y:
            y = min_y + half_h
            vy = abs(vy)  # bounce downwards (upwards in screen coords)
        elif y + half_h > max_y:
            y = max_y - half_h
            vy = -abs(vy)

        # Check collisions with each obstacle
        for (ox, oy, ohx, ohy) in proc_obstacles:
            # Compute overlap along x and y
            dx = x - ox
            px = ohx + half_w - abs(dx)
            if px <= 0:
                # No overlap along x; skip check for this obstacle
                continue
            dy = y - oy
            py = ohy + half_h - abs(dy)
            if py <= 0:
                # No overlap along y; skip
                continue
            # Collision detected.  Reflect along the axis of minimum
            # penetration depth.  Adjust position to resolve interpenetration.
            if px < py:
                # Resolve along X axis
                if dx > 0:
                    x = ox + ohx + half_w
                    vx = abs(vx)
                else:
                    x = ox - ohx - half_w
                    vx = -abs(vx)
            else:
                # Resolve along Y axis
                if dy > 0:
                    y = oy + ohy + half_h
                    vy = abs(vy)
                else:
                    y = oy - ohy - half_h
                    vy = -abs(vy)

        # Write back the resolved position and velocity
        transform.position = (x, y)
        velocity.value = (vx, vy)
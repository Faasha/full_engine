"""Simple collision system for the first playable slice.

Optimized version:
- world bounds
- static axis-aligned rectangle obstacles
- circle-vs-AABB resolution for movers
- cheap broad-phase rejection per obstacle

Still intentionally narrow:
- no physics engine
- no impulses
- no restitution
- no swept collision
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class RectObstacle:
    """Axis-aligned obstacle rectangle."""
    x: float
    y: float
    w: float
    h: float


@dataclass(slots=True)
class WorldBounds:
    """Simple rectangular world bounds."""
    min_x: float
    min_y: float
    max_x: float
    max_y: float


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _circle_aabb_maybe_overlap(px: float, py: float, radius: float, rect: RectObstacle) -> bool:
    """Cheap broad-phase rejection for circle vs AABB."""
    if px + radius < rect.x:
        return False
    if px - radius > rect.x + rect.w:
        return False
    if py + radius < rect.y:
        return False
    if py - radius > rect.y + rect.h:
        return False
    return True


def _resolve_circle_vs_aabb(
    px: float,
    py: float,
    radius: float,
    rect: RectObstacle,
) -> tuple[float, float, bool]:
    """Resolve overlap between a circle center and an AABB.

    Returns:
        (new_x, new_y, collided)
    """
    nearest_x = _clamp(px, rect.x, rect.x + rect.w)
    nearest_y = _clamp(py, rect.y, rect.y + rect.h)

    dx = px - nearest_x
    dy = py - nearest_y
    dist_sq = dx * dx + dy * dy
    radius_sq = radius * radius

    if dist_sq >= radius_sq:
        return px, py, False

    # Center exactly on the nearest point / embedded case
    if dist_sq <= 1e-12:
        left_pen = abs(px - rect.x)
        right_pen = abs((rect.x + rect.w) - px)
        bottom_pen = abs(py - rect.y)
        top_pen = abs((rect.y + rect.h) - py)

        min_pen = min(left_pen, right_pen, bottom_pen, top_pen)
        if min_pen == left_pen:
            return rect.x - radius, py, True
        if min_pen == right_pen:
            return rect.x + rect.w + radius, py, True
        if min_pen == bottom_pen:
            return px, rect.y - radius, True
        return px, rect.y + rect.h + radius, True

    dist = dist_sq ** 0.5
    push = radius - dist
    nx = dx / dist
    ny = dy / dist

    return px + nx * push, py + ny * push, True


def resolve_world_bounds(
    world,
    *,
    radius: float,
    bounds: WorldBounds,
) -> int:
    """Clamp all movers inside world bounds.

    Returns number of axis adjustments applied.
    """
    count = 0
    n = len(world.pos_x)

    min_x = bounds.min_x + radius
    max_x = bounds.max_x - radius
    min_y = bounds.min_y + radius
    max_y = bounds.max_y - radius

    for i in range(n):
        x = world.pos_x[i]
        y = world.pos_y[i]

        nx = _clamp(x, min_x, max_x)
        ny = _clamp(y, min_y, max_y)

        if nx != x:
            world.pos_x[i] = nx
            world.vel_x[i] = 0.0
            count += 1
        if ny != y:
            world.pos_y[i] = ny
            world.vel_y[i] = 0.0
            count += 1

    return count


def resolve_static_obstacles(
    world,
    *,
    radius: float,
    obstacles: Iterable[RectObstacle],
) -> int:
    """Resolve circle-vs-rectangle overlaps for all movers.

    Uses a cheap broad-phase test before detailed resolution.

    Returns number of entities that required any obstacle adjustment.
    """
    obstacle_list = list(obstacles)
    if not obstacle_list:
        return 0

    count = 0
    n = len(world.pos_x)

    for i in range(n):
        x = world.pos_x[i]
        y = world.pos_y[i]
        collided_any = False

        for rect in obstacle_list:
            if not _circle_aabb_maybe_overlap(x, y, radius, rect):
                continue

            x, y, collided = _resolve_circle_vs_aabb(x, y, radius, rect)
            if collided:
                collided_any = True

        if collided_any:
            world.pos_x[i] = x
            world.pos_y[i] = y
            world.vel_x[i] = 0.0
            world.vel_y[i] = 0.0
            count += 1

    return count

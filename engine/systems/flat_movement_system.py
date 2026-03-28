"""Flat-array movement system."""

from __future__ import annotations

from engine.core.flat_world import FlatWorld


def update_flat_movement(world: FlatWorld, dt: float) -> None:
    """Integrate velocity into position using flat arrays."""
    px = world.pos_x
    py = world.pos_y
    vx = world.vel_x
    vy = world.vel_y

    for i in range(len(px)):
        px[i] += vx[i] * dt
        py[i] += vy[i] * dt

"""Cell occupancy tracking for active entities.

This module provides a small helper that tracks how many active entities
currently occupy each local simulation cell.

Why it exists:
- rebuilding occupancy from scratch every tick is expensive
- instantiate logic only needs per-cell counts
- dissolve / instantiate can update occupancy incrementally
- later, movement can update occupancy when entities cross cell boundaries

Cell coordinates here are *local* cell coordinates relative to the
simulation origin, not field-grid coordinates.
"""

from __future__ import annotations

from typing import Dict, Tuple

from engine.core.ecs import ECS
from engine.core.flat_world import FlatWorld
from engine.components.transform import Transform


Cell = Tuple[int, int]


class OccupancyMap:
    """Track active-entity counts per local cell."""

    def __init__(self, cell_size: float = 50.0) -> None:
        self.cell_size = cell_size
        self.counts: Dict[Cell, int] = {}

    def clear(self) -> None:
        """Clear all occupancy state."""
        self.counts.clear()

    def world_to_cell(self, x: float, y: float) -> Cell:
        """Convert world position to local cell coordinates."""
        return (int(x / self.cell_size), int(y / self.cell_size))

    def get(self, cx: int, cy: int) -> int:
        """Return occupancy for a cell."""
        return self.counts.get((cx, cy), 0)

    def increment(self, cx: int, cy: int, amount: int = 1) -> None:
        """Increase occupancy for a cell."""
        key = (cx, cy)
        self.counts[key] = self.counts.get(key, 0) + amount

    def decrement(self, cx: int, cy: int, amount: int = 1) -> None:
        """Decrease occupancy for a cell and remove empty entries."""
        key = (cx, cy)
        new_value = self.counts.get(key, 0) - amount
        if new_value > 0:
            self.counts[key] = new_value
        else:
            self.counts.pop(key, None)

    def set_count(self, cx: int, cy: int, value: int) -> None:
        """Set occupancy explicitly."""
        key = (cx, cy)
        if value > 0:
            self.counts[key] = value
        else:
            self.counts.pop(key, None)

    def move(self, old_cx: int, old_cy: int, new_cx: int, new_cy: int) -> None:
        """Move one entity from one cell to another."""
        if old_cx == new_cx and old_cy == new_cy:
            return
        self.decrement(old_cx, old_cy, 1)
        self.increment(new_cx, new_cy, 1)

    def rebuild_from_flat_world(self, world: FlatWorld) -> None:
        """Rebuild occupancy from authoritative FlatWorld hot state."""
        self.clear()
        for i in range(len(world.pos_x)):
            cx, cy = self.world_to_cell(world.pos_x[i], world.pos_y[i])
            self.increment(cx, cy, 1)

    def rebuild_from_ecs(self, ecs: ECS) -> None:
        """Fallback rebuild from ECS Transform data."""
        self.clear()
        transforms = ecs.get_component_array(Transform)
        row_count = ecs.rows()
        for row in range(row_count):
            transform = transforms[row]
            if transform is None:
                continue
            cx, cy = self.world_to_cell(transform.position[0], transform.position[1])
            self.increment(cx, cy, 1)

    def snapshot(self) -> Dict[Cell, int]:
        """Return a shallow copy for debugging."""
        return dict(self.counts)

    def __len__(self) -> int:
        return len(self.counts)

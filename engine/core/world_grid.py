"""World-space grid utilities for chunked world simulation.

This is the first real world substrate layer.

Responsibilities:
- define chunk size
- map world position to chunk coordinates
- map chunk coordinates to world-space origins/centers
- provide neighborhood iteration for activation logic

This file should stay dumb and exact.
It is geometry and indexing, not gameplay.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Tuple


ChunkCoord = Tuple[int, int]


@dataclass(slots=True, frozen=True)
class WorldGrid:
    """Defines the chunk lattice for the world."""

    chunk_width: float = 256.0
    chunk_height: float = 256.0

    def world_to_chunk(self, x: float, y: float) -> ChunkCoord:
        """Return the chunk coordinate containing a world-space point."""
        cx = int(x // self.chunk_width)
        cy = int(y // self.chunk_height)
        return (cx, cy)

    def chunk_to_world_origin(self, coord: ChunkCoord) -> tuple[float, float]:
        """Return the world-space minimum corner of a chunk."""
        cx, cy = coord
        return (cx * self.chunk_width, cy * self.chunk_height)

    def chunk_to_world_center(self, coord: ChunkCoord) -> tuple[float, float]:
        """Return the world-space center of a chunk."""
        ox, oy = self.chunk_to_world_origin(coord)
        return (ox + self.chunk_width * 0.5, oy + self.chunk_height * 0.5)

    def chunk_bounds(self, coord: ChunkCoord) -> tuple[float, float, float, float]:
        """Return (min_x, min_y, max_x, max_y) for a chunk."""
        ox, oy = self.chunk_to_world_origin(coord)
        return (ox, oy, ox + self.chunk_width, oy + self.chunk_height)

    def chunk_distance_sq(self, a: ChunkCoord, b: ChunkCoord) -> int:
        """Return squared chunk-grid distance."""
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return dx * dx + dy * dy

    def iter_square(self, center: ChunkCoord, radius: int) -> Iterator[ChunkCoord]:
        """Iterate chunk coords in a square around center."""
        cx, cy = center
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                yield (x, y)

    def iter_disc(self, center: ChunkCoord, radius: int) -> Iterator[ChunkCoord]:
        """Iterate chunk coords within a disc radius around center."""
        cx, cy = center
        radius_sq = radius * radius
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                dx = x - cx
                dy = y - cy
                if dx * dx + dy * dy <= radius_sq:
                    yield (x, y)

    def local_offset_in_chunk(self, x: float, y: float) -> tuple[float, float]:
        """Return local coordinates inside the containing chunk."""
        cx, cy = self.world_to_chunk(x, y)
        ox, oy = self.chunk_to_world_origin((cx, cy))
        return (x - ox, y - oy)

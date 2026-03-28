"""Player-relative activation logic for the first world slice.

This system defines the first real active/distant boundary in the engine.

Responsibilities:
- identify which chunks are active around the player
- identify which chunks are warm or distant
- compute enter/exit sets as the player moves
- provide a stable activation policy the scene can use

This file does not instantiate entities itself.
It tells the rest of the runtime what should be active.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set, Tuple

from engine.core.world_grid import ChunkCoord, WorldGrid


@dataclass(slots=True)
class ActivationState:
    """Tracks current chunk activation around the player."""

    center_chunk: ChunkCoord = (0, 0)
    active_chunks: Set[ChunkCoord] = field(default_factory=set)
    warm_chunks: Set[ChunkCoord] = field(default_factory=set)

    entered_active: Set[ChunkCoord] = field(default_factory=set)
    exited_active: Set[ChunkCoord] = field(default_factory=set)

    entered_warm: Set[ChunkCoord] = field(default_factory=set)
    exited_warm: Set[ChunkCoord] = field(default_factory=set)


def compute_chunk_rings(
    grid: WorldGrid,
    center: ChunkCoord,
    *,
    active_radius: int,
    warm_radius: int,
) -> tuple[Set[ChunkCoord], Set[ChunkCoord]]:
    """Return (active_chunks, warm_chunks) around a center chunk.

    warm_chunks includes the active ring and an outer shell up to warm_radius.
    """
    if warm_radius < active_radius:
        warm_radius = active_radius

    active = set(grid.iter_disc(center, active_radius))
    warm = set(grid.iter_disc(center, warm_radius))
    return active, warm


def update_activation_state(
    state: ActivationState,
    grid: WorldGrid,
    player_x: float,
    player_y: float,
    *,
    active_radius: int = 1,
    warm_radius: int = 2,
) -> ActivationState:
    """Update activation state from the player's world position.

    Sets:
    - center_chunk
    - active_chunks
    - warm_chunks
    - entered/exited delta sets
    """
    new_center = grid.world_to_chunk(player_x, player_y)
    new_active, new_warm = compute_chunk_rings(
        grid,
        new_center,
        active_radius=active_radius,
        warm_radius=warm_radius,
    )

    old_active = state.active_chunks
    old_warm = state.warm_chunks

    state.center_chunk = new_center

    state.entered_active = new_active - old_active
    state.exited_active = old_active - new_active

    state.entered_warm = new_warm - old_warm
    state.exited_warm = old_warm - new_warm

    state.active_chunks = new_active
    state.warm_chunks = new_warm
    return state


def chunk_sets_debug_dict(state: ActivationState) -> Dict[str, object]:
    """Return lightweight debug data for logging or HUD use."""
    return {
        "center_chunk": state.center_chunk,
        "active_count": len(state.active_chunks),
        "warm_count": len(state.warm_chunks),
        "entered_active": len(state.entered_active),
        "exited_active": len(state.exited_active),
        "entered_warm": len(state.entered_warm),
        "exited_warm": len(state.exited_warm),
    }

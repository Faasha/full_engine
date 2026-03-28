"""Simple player input system.

This first version is deliberately boring:
- poll keyboard state
- convert to a velocity
- write directly to the player velocity component

No acceleration curves.
No event buffering.
No input abstraction maze.
"""

from __future__ import annotations

from typing import Optional

from engine.core.ecs import ECS
from engine.components.player_tag import PlayerTag
from engine.components.velocity import Velocity


def _resolve_input_vector(keys: dict[str, bool]) -> tuple[float, float]:
    """Convert simple directional input into a normalized 2D vector."""
    x = 0.0
    y = 0.0

    if keys.get("left", False):
        x -= 1.0
    if keys.get("right", False):
        x += 1.0
    if keys.get("up", False):
        y += 1.0
    if keys.get("down", False):
        y -= 1.0

    # Normalize diagonals so speed stays consistent
    if x != 0.0 and y != 0.0:
        inv = 2 ** -0.5
        x *= inv
        y *= inv

    return x, y


def find_player_entity(ecs: ECS) -> Optional[tuple[int, int]]:
    """Return the first entity marked as the player."""
    for entity_id, (tag,) in ecs.iter_entities(PlayerTag):
        if tag.enabled:
            return entity_id
    return None


def apply_player_input(
    ecs: ECS,
    keys: dict[str, bool],
    speed: float = 120.0,
) -> Optional[tuple[int, int]]:
    """Apply input to the player velocity.

    Returns the player entity ID if found, else None.
    """
    player_id = find_player_entity(ecs)
    if player_id is None:
        return None

    velocity = ecs.get_component(player_id, Velocity)
    if velocity is None:
        return player_id

    ix, iy = _resolve_input_vector(keys)
    velocity.value = (ix * speed, iy * speed)
    return player_id

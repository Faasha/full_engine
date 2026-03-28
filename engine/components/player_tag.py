"""Marker component for the player entity."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PlayerTag:
    """Marks an entity as the player."""
    enabled: bool = True

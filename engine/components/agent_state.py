"""Lightweight behavior identity for active agents."""

from __future__ import annotations

from dataclasses import dataclass

ChunkCoord = tuple[int, int]


@dataclass(slots=True)
class AgentState:
    """Minimal active-agent behavior descriptor."""

    kind: str = "civilian"
    home_archetype: str = "room"
    pressure_bias: float = 0.0
    home_chunk: ChunkCoord | None = None
    response_mode: str = "ambient"
    response_strength: float = 0.0

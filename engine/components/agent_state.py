"""Lightweight behavior identity for active agents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AgentState:
    """Minimal active-agent behavior descriptor."""

    kind: str = "civilian"
    home_archetype: str = "room"
    pressure_bias: float = 0.0

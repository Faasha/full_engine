from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PlayerState:
    strain: float = 0.0
    max_strain: float = 100.0

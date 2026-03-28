"""Transform component.

Stores an entity's position, rotation and scale.  All values are floats,
suitable for simple 2D simulation.  No methods are defined on the
component; systems operate on its fields directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class Transform:
    position: Tuple[float, float]
    rotation: float = 0.0
    scale: Tuple[float, float] = (1.0, 1.0)
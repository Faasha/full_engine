"""Velocity component.

Represents an entity's linear velocity in two dimensions.  Units are
abstract; systems are responsible for interpreting the velocity relative
to the timestep.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class Velocity:
    value: Tuple[float, float]
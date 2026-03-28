"""Collider component for basic collision detection.

This component defines an axis‑aligned bounding box (AABB) for an
entity.  The collider is specified by a ``size`` tuple representing
the width and height of the bounding box.  Collision detection uses
the entity's ``Transform`` position as the centre of the box and
expands it by half of ``size`` in each direction.  Only entities
that possess both ``Transform`` and ``Collider`` components are
considered collidable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class Collider:
    """Simple axis‑aligned bounding box collider.

    The ``size`` attribute defines the width and height of the box.
    Collision detection treats this collider as centred at the
    entity's position (from ``Transform.position``) and uses half of
    ``size`` as the extents.
    """

    size: Tuple[float, float]
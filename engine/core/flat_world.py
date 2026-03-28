"""Flat hot-state storage for the runtime.

This version uses plain Python lists for the hot arrays. Even though the
array-backed experiment looked promising for future native integration,
the current Python-heavy movement and extract paths run faster on list
storage, so this is the correct live runtime version for now.

Hot arrays:
- pos_x, pos_y
- vel_x, vel_y
- mesh, material

Structural mappings remain:
- entity_to_index
- index_to_entity
"""

from __future__ import annotations

from typing import Dict, List, Tuple


EntityID = Tuple[int, int]


class FlatWorld:
    """Dense hot-state store using Python lists."""

    def __init__(self) -> None:
        self.entity_to_index: Dict[EntityID, int] = {}
        self.index_to_entity: List[EntityID] = []

        self.pos_x: List[float] = []
        self.pos_y: List[float] = []
        self.vel_x: List[float] = []
        self.vel_y: List[float] = []

        self.mesh: List[int] = []
        self.material: List[int] = []

    def clear(self) -> None:
        """Clear all world state."""
        self.entity_to_index.clear()
        self.index_to_entity.clear()

        self.pos_x.clear()
        self.pos_y.clear()
        self.vel_x.clear()
        self.vel_y.clear()

        self.mesh.clear()
        self.material.clear()

    def rows(self) -> int:
        """Return the number of active hot rows."""
        return len(self.index_to_entity)

    def has(self, entity_id: EntityID) -> bool:
        """Return True if the entity exists in FlatWorld."""
        return entity_id in self.entity_to_index

    def add(
        self,
        entity_id: EntityID,
        x: float,
        y: float,
        vx: float,
        vy: float,
        mesh_handle: int,
        material_handle: int,
    ) -> None:
        """Append one entity to the dense hot arrays."""
        if entity_id in self.entity_to_index:
            raise KeyError(f"Entity already exists in FlatWorld: {entity_id}")

        idx = len(self.index_to_entity)
        self.entity_to_index[entity_id] = idx
        self.index_to_entity.append(entity_id)

        self.pos_x.append(float(x))
        self.pos_y.append(float(y))
        self.vel_x.append(float(vx))
        self.vel_y.append(float(vy))
        self.mesh.append(int(mesh_handle))
        self.material.append(int(material_handle))

    def remove(self, entity_id: EntityID) -> None:
        """Remove one entity using swap-remove.

        This keeps the hot arrays dense and updates the entity/index mapping.
        """
        if entity_id not in self.entity_to_index:
            raise KeyError(f"Entity not found in FlatWorld: {entity_id}")

        idx = self.entity_to_index.pop(entity_id)
        last = len(self.index_to_entity) - 1

        if idx != last:
            last_entity = self.index_to_entity[last]

            self.index_to_entity[idx] = last_entity
            self.entity_to_index[last_entity] = idx

            self.pos_x[idx] = self.pos_x[last]
            self.pos_y[idx] = self.pos_y[last]
            self.vel_x[idx] = self.vel_x[last]
            self.vel_y[idx] = self.vel_y[last]
            self.mesh[idx] = self.mesh[last]
            self.material[idx] = self.material[last]

        self.index_to_entity.pop()
        self.pos_x.pop()
        self.pos_y.pop()
        self.vel_x.pop()
        self.vel_y.pop()
        self.mesh.pop()
        self.material.pop()

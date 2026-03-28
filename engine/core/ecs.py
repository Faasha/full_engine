"""Entity–component storage.

This module provides a minimal entity component system (ECS) storage
layer using a dense table layout.  It is intentionally simple and
focused on deterministic simulation for a low-waste runtime.

Hot components (those updated every tick) are stored in parallel arrays
(structure of arrays) keyed by component type.  Cold or optional data
can be stored separately.  The ECS ensures that rows stay dense by
swapping removed entities with the last row when an entity is
destroyed.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple, Type, TypeVar

from .id_allocator import IDAllocator


EntityID = Tuple[int, int]
ComponentT = TypeVar("ComponentT")


class ECS:
    """Store and manage entities and their components.

    The ECS uses a table (structure-of-arrays) layout for hot components,
    maintaining a dense row for each active entity.  When an entity is
    destroyed, its row is swapped with the last row to keep iteration
    contiguous.  Components are stored in per-type arrays; missing components
    are represented by ``None`` in the corresponding slot.  Hot-loop systems
    may retrieve raw component arrays directly via :meth:`get_component_array`
    for maximum efficiency.
    """

    def __init__(self, id_allocator: IDAllocator) -> None:
        self.id_allocator = id_allocator
        # Map from entity ID to row index
        self._entity_to_row: Dict[EntityID, int] = {}
        # List of entity IDs by row index
        self._rows_to_entity: List[EntityID] = []
        # Component arrays keyed by component type
        self._components: Dict[Type[Any], List[Optional[Any]]] = {}

    def _ensure_component(self, comp_type: Type[Any]) -> None:
        """Ensure a component array exists for the given type."""
        if comp_type not in self._components:
            self._components[comp_type] = [None] * len(self._rows_to_entity)

    def _grow_component_arrays(self) -> None:
        """Append a None slot to every component array for a new entity."""
        for array in self._components.values():
            array.append(None)

    def create_entity(self, components: Optional[Dict[Type[Any], Any]] = None) -> EntityID:
        """Create a new entity with the given components.

        ``components`` is a mapping from component types to instances. Types
        not present in the mapping will remain ``None`` for the new entity.
        Returns the assigned entity ID.
        """
        components = components or {}
        entity_id = self.id_allocator.allocate()
        row = len(self._rows_to_entity)

        self._rows_to_entity.append(entity_id)
        self._entity_to_row[entity_id] = row

        for comp_type in components.keys():
            self._ensure_component(comp_type)

        self._grow_component_arrays()

        for comp_type, value in components.items():
            self._components[comp_type][row] = value

        return entity_id

    def destroy_entity(self, entity_id: EntityID) -> None:
        """Destroy an entity and recycle its ID.

        Raises KeyError if the entity is not alive.
        """
        if entity_id not in self._entity_to_row:
            raise KeyError(f"Entity {entity_id} not found")

        row = self._entity_to_row.pop(entity_id)
        last_row = len(self._rows_to_entity) - 1

        # Swap with last row to maintain density
        if row != last_row:
            last_entity = self._rows_to_entity[last_row]
            self._rows_to_entity[row] = last_entity
            self._entity_to_row[last_entity] = row

            for array in self._components.values():
                array[row] = array[last_row]

        # Remove last row
        self._rows_to_entity.pop()
        for array in self._components.values():
            array.pop()

        self.id_allocator.release(entity_id)

    def add_component(self, entity_id: EntityID, comp_type: Type[ComponentT], value: ComponentT) -> None:
        """Attach a component to an entity."""
        row = self._entity_to_row[entity_id]
        self._ensure_component(comp_type)
        array = self._components[comp_type]

        if len(array) < len(self._rows_to_entity):
            array.extend([None] * (len(self._rows_to_entity) - len(array)))

        array[row] = value

    def remove_component(self, entity_id: EntityID, comp_type: Type[Any]) -> None:
        """Remove a component from an entity."""
        row = self._entity_to_row[entity_id]
        array = self._components.get(comp_type)
        if array is not None and row < len(array):
            array[row] = None

    def get_component(self, entity_id: EntityID, comp_type: Type[ComponentT]) -> Optional[ComponentT]:
        """Retrieve a component instance from an entity."""
        row = self._entity_to_row[entity_id]
        array = self._components.get(comp_type)
        if array is None or row >= len(array):
            return None
        return array[row]  # type: ignore[return-value]

    def get_component_array(self, comp_type: Type[ComponentT]) -> List[Optional[ComponentT]]:
        """Return the raw component array for the given type.

        If the type has not been used yet, an array of ``None`` values is
        created and returned. Systems can use this to access components
        directly by row without the overhead of :meth:`iter_entities`.
        """
        self._ensure_component(comp_type)
        return self._components[comp_type]  # type: ignore[return-value]

    def entity_row(self, entity_id: EntityID) -> int:
        """Return the dense row index for an active entity."""
        return self._entity_to_row[entity_id]

    def rows(self) -> int:
        """Return the number of active rows (entities)."""
        return len(self._rows_to_entity)

    def iter_entities(self, *component_types: Type[Any]) -> Iterator[Tuple[EntityID, Tuple[Any, ...]]]:
        """Yield entities and their components for the given types.

        Only entities that have non-``None`` values for all specified
        component types are yielded. The components are returned in the
        same order as ``component_types``.
        """
        arrays = [self._components.get(ct, []) for ct in component_types]

        for row, entity_id in enumerate(self._rows_to_entity):
            comps: List[Any] = []
            match = True

            for array in arrays:
                if row >= len(array):
                    match = False
                    break

                value = array[row]
                if value is None:
                    match = False
                    break

                comps.append(value)

            if match:
                yield (entity_id, tuple(comps))

    def snapshot_positions(self) -> Dict[EntityID, Tuple[float, float]]:
        """Return a dict of entity positions for debugging or tests."""
        from engine.components.transform import Transform

        positions: Dict[EntityID, Tuple[float, float]] = {}
        transform_array = self._components.get(Transform)
        if transform_array is None:
            return positions

        for row, entity_id in enumerate(self._rows_to_entity):
            if row < len(transform_array):
                transform = transform_array[row]
                if transform is not None:
                    positions[entity_id] = transform.position

        return positions

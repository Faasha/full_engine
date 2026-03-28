"""Generational ID allocator for engine entities.

This module implements a simple generational ID system.  Each entity ID is a
tuple of ``(index, generation)``.  When an entity is destroyed its
generation counter is incremented, preventing stale references from being
mistakenly reused.
"""

from __future__ import annotations

from typing import List, Tuple


class IDAllocator:
    """Allocate and recycle generational entity IDs."""

    def __init__(self) -> None:
        self._generations: List[int] = []
        self._free_indices: List[int] = []

    def allocate(self) -> Tuple[int, int]:
        """Allocate a new ID.

        Returns a 2‑tuple (index, generation).  Reuses indices from the
        free list if available, otherwise appends a new slot.
        """
        if self._free_indices:
            index = self._free_indices.pop()
            generation = self._generations[index]
        else:
            index = len(self._generations)
            generation = 0
            self._generations.append(0)
        return (index, generation)

    def release(self, identifier: Tuple[int, int]) -> None:
        """Release an ID and increment its generation.

        Raises ``ValueError`` if the ID is invalid or its generation does not
        match the current generation for its slot.
        """
        index, generation = identifier
        try:
            current = self._generations[index]
        except IndexError as exc:
            raise ValueError(f"Invalid ID {identifier}: index out of range") from exc
        if current != generation:
            raise ValueError(
                f"Invalid ID {identifier}: generation mismatch (expected {current})"
            )
        self._generations[index] = current + 1
        self._free_indices.append(index)

    def is_alive(self, identifier: Tuple[int, int]) -> bool:
        """Return True if the given ID has not been released."""
        index, generation = identifier
        return 0 <= index < len(self._generations) and self._generations[index] == generation
"""Per‑frame transient memory arena.

Allocates lists of a requested length for temporary data used within a
single simulation frame.  At the end of each frame the arena can be
cleared, discarding all allocations.  This helps avoid hidden per‑frame
allocations that accumulate over time.
"""

from __future__ import annotations

from typing import Any, List, MutableSequence, Type


class FrameArena:
    """A scratch allocator for per‑frame temporary storage.

    The arena allocates transient lists that are automatically discarded
    at the end of each frame.  Systems may also register existing
    objects with :meth:`keep` so that they are cleared alongside
    arena allocations.
    """

    def __init__(self) -> None:
        # Internal list of objects to clear at the end of the frame
        self._allocations: List[Any] = []

    def alloc_array(self, length: int, dtype: Type[Any] = object) -> List[Any]:
        """Allocate a new list of the specified length.

        All allocated lists are recorded so that they can be cleared
        automatically when :meth:`clear` is called.
        """
        arr: List[Any] = [None] * length
        self._allocations.append(arr)
        return arr

    def keep(self, obj: Any) -> Any:
        """Track an existing temporary object for this frame.

        Systems that build lists or other containers outside of
        :meth:`alloc_array` should register them with ``keep`` so that
        they are discarded automatically at the end of the frame.
        Returns the object to enable fluent use.
        """
        self._allocations.append(obj)
        return obj

    def clear(self) -> None:
        """Discard all transient allocations.

        After calling clear all objects tracked by the arena will be
        eligible for garbage collection if no other references remain.
        """
        self._allocations.clear()
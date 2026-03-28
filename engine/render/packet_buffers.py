"""Reusable structured packet buffers for simulation/render handoff.

The goal is to avoid per-frame packet snapshot copying.

Ownership model:
- simulation acquires an empty packet from the pool
- simulation fills it and hands it to the renderer queue
- renderer consumes it
- renderer returns the packet to the pool

Packet format:
    {
        "mesh": list[int],
        "material": list[int],
        "x": list[float],
        "y": list[float],
        "count": int,
    }
"""

from __future__ import annotations

import queue
from typing import Any, Dict


Packet = Dict[str, Any]


def _new_packet() -> Packet:
    """Create a fresh structured packet buffer."""
    return {
        "mesh": [],
        "material": [],
        "x": [],
        "y": [],
        "count": 0,
    }


class PacketBufferPool:
    """Pool of reusable structured packet buffers."""

    def __init__(self, count: int = 3) -> None:
        self._free: "queue.SimpleQueue[Packet]" = queue.SimpleQueue()
        for _ in range(count):
            self._free.put(_new_packet())

    def acquire(self) -> Packet:
        """Acquire a reusable packet buffer.

        Falls back to allocating a new packet if the pool is temporarily empty.
        """
        try:
            packet = self._free.get_nowait()
        except Exception:
            packet = _new_packet()

        # Reset logical size only. Lists stay allocated for reuse.
        packet["count"] = 0
        return packet

    def release(self, packet: Packet) -> None:
        """Return a packet buffer to the pool."""
        packet["count"] = 0
        self._free.put(packet)

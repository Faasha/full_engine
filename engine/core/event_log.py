"""Append‑only event log for external influence.

External inputs and structural changes enter the simulation as events.  The
event log stores a sequence of events with timestamps (or tick indices) so
that they can be consumed in order by the simulation.  For the first
milestone, the structure of events is deliberately simple.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Iterator, List, Tuple


@dataclass
class Event:
    """Generic event record."""
    tick: int
    kind: str
    payload: Any


class EventLog:
    """Simple append‑only log of events."""

    def __init__(self) -> None:
        self._events: List[Event] = []

    def append(self, tick: int, kind: str, payload: Any) -> None:
        """Append an event for the given tick."""
        self._events.append(Event(tick, kind, payload))

    def extend(self, events: Iterable[Tuple[int, str, Any]]) -> None:
        """Append multiple events in order."""
        for tick, kind, payload in events:
            self._events.append(Event(tick, kind, payload))

    def events_since(self, tick: int) -> Iterator[Event]:
        """Iterate over events occurring at or after the given tick."""
        for event in self._events:
            if event.tick >= tick:
                yield event

    def __len__(self) -> int:  # pragma: no cover
        return len(self._events)
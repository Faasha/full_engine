"""Tests for the event log."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from engine.core.event_log import EventLog


def test_append_and_replay() -> None:
    log = EventLog()
    # Append events out of order ticks
    log.append(5, "Spawn", {"id": 1})
    log.append(2, "Input", {"key": "W"})
    log.append(5, "Destroy", {"id": 2})
    assert len(log) == 3
    # Replay events since tick 3
    events = list(log.events_since(3))
    assert len(events) == 2
    assert all(ev.tick >= 3 for ev in events)
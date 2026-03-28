"""Timing utilities for profiling and debugging.

Provides a simple context manager for measuring code block durations.  This
is intended for ad‑hoc profiling and debugging rather than production
telemetry.  For detailed metrics consider integrating a more complete
profiling system later.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def Timer(name: str) -> Iterator[None]:
    """Context manager that prints the elapsed time of a code block.

    Usage::
        with Timer("movement"):
            update_movement()
    When the block exits a line is printed with the duration in
    milliseconds.
    """
    start = time.perf_counter()
    try:
        yield None
    finally:
        end = time.perf_counter()
        ms = (end - start) * 1000.0
        print(f"[{name}] {ms:.3f} ms")
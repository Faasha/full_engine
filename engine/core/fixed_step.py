"""Fixed‑step simulation loop.

Runs a simulation update function at a constant timestep, accumulating
floating‑point residuals so that the simulation stays in sync with real
time.  Optionally stops after a specified duration.
"""

from __future__ import annotations

import time
from typing import Callable, Optional


def run_fixed_step(
    target_fps: float,
    update_fn: Callable[[int, float], None],
    duration: Optional[float] = None,
) -> None:
    """Run a fixed‑timestep loop.

    Parameters
    ----------
    target_fps:
        Number of simulation steps per second.
    update_fn:
        Function called for each simulation step.  It receives the tick
        index and the timestep ``dt``.
    duration:
        Optional time limit in seconds.  If provided, the loop stops when
        the accumulated time exceeds this value.
    """
    dt = 1.0 / float(target_fps)
    accumulator = 0.0
    previous_time = time.perf_counter()
    tick = 0
    elapsed = 0.0
    while True:
        now = time.perf_counter()
        frame_time = now - previous_time
        previous_time = now
        accumulator += frame_time
        # Catch up simulation steps if behind
        max_steps = 5
        steps = 0
        while accumulator >= dt and steps < max_steps:
            update_fn(tick, dt)
            tick += 1
            accumulator -= dt
            elapsed += dt
            steps += 1
            if duration is not None and elapsed >= duration:
                return
        # Sleep until next tick to yield CPU
        sleep_time = dt - accumulator
        if sleep_time > 0:
            time.sleep(sleep_time)
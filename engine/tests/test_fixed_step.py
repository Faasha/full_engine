"""Tests for the fixed step loop."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from engine.core.fixed_step import run_fixed_step


def test_run_fixed_steps() -> None:
    # Count ticks and record dt values
    ticks = []
    dts = []
    def update_fn(tick: int, dt: float) -> None:
        ticks.append(tick)
        dts.append(dt)
    run_fixed_step(60.0, update_fn, duration=0.2)
    # Expect roughly 12 steps (0.2 * 60 = 12)
    assert 10 <= len(ticks) <= 14
    # All dt values should be approximately 1/60
    for dt in dts:
        assert abs(dt - (1.0 / 60.0)) < 0.01
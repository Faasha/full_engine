"""Integration test for the stress‑null scene."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from engine.scenes.stress_null import run_stress_scene


def test_stress_null_deterministic() -> None:
    # Run twice with same seed and parameters; results should match
    positions1 = run_stress_scene(num_entities=100, duration=0.5, seed=123, fps=60.0, use_graphics=False)
    positions2 = run_stress_scene(num_entities=100, duration=0.5, seed=123, fps=60.0, use_graphics=False)
    assert positions1 == positions2
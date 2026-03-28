"""Probe and validator for the native field diffusion kernel.

This compares the Python field update against the native diffusion step
for correctness and basic timing.

Usage examples:
    python3 -m engine.native.field_native_probe --ticks 120
    python3 -m engine.native.field_native_probe --ticks 120 --inject 32,32,100
    python3 -m engine.native.field_native_probe --ticks 120 --inject 0,0,100
"""

from __future__ import annotations

import argparse
import time
from typing import List, Set, Tuple

from engine.native.field_native import diffuse_step_native
from engine.systems.field_system import FieldSystem


def parse_injection(text: str) -> Tuple[int, int, float]:
    parts = text.split(",")
    if len(parts) != 3:
        raise ValueError(f"Invalid inject value: {text!r}")
    x = int(parts[0])
    y = int(parts[1])
    mass = float(parts[2])
    return x, y, mass


def python_step(
    grid: List[float],
    width: int,
    height: int,
    diffuse_rate: float,
    dt: float,
    epsilon: float,
    active_indices: Set[int],
) -> Tuple[List[float], Set[int]]:
    field = FieldSystem(
        width=width,
        height=height,
        diffuse_rate=diffuse_rate,
        epsilon=epsilon,
    )
    field.grid = grid[:]
    field.active_indices = set(active_indices)
    field.update(dt)
    return field.grid[:], set(field.active_indices)


def max_abs_diff(a: List[float], b: List[float]) -> float:
    if len(a) != len(b):
        raise ValueError("List length mismatch")
    m = 0.0
    for x, y in zip(a, b):
        d = abs(x - y)
        if d > m:
            m = d
    return m


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument("--diffuse-rate", type=float, default=0.1)
    parser.add_argument("--dt", type=float, default=1.0 / 60.0)
    parser.add_argument("--epsilon", type=float, default=1e-6)
    parser.add_argument(
        "--inject",
        action="append",
        default=[],
        help="Injection in x,y,mass form. Can be repeated.",
    )
    args = parser.parse_args()

    width = args.width
    height = args.height
    cell_count = width * height

    if args.inject:
        injections = [parse_injection(text) for text in args.inject]
    else:
        injections = [(width // 2, height // 2, 100.0)]

    base_grid = [0.0] * cell_count
    base_active: Set[int] = set()

    for x, y, mass in injections:
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(f"Injection out of bounds: {(x, y)}")
        idx = y * width + x
        base_grid[idx] += mass
        if abs(base_grid[idx]) > args.epsilon:
            base_active.add(idx)

    print("=== Native Field Probe Start ===")
    print(f"grid: {width}x{height}")
    print(f"diffuse_rate: {args.diffuse_rate}")
    print(f"ticks: {args.ticks}")
    print(f"dt: {args.dt}")
    print(f"baseline mass: {sum(base_grid):.6f}")
    print(f"injections: {injections}")

    py_grid = base_grid[:]
    py_active = set(base_active)

    native_grid = base_grid[:]
    native_active = set(base_active)

    py_total = 0.0
    native_total = 0.0

    worst_grid_diff = 0.0
    worst_active_diff = 0

    for tick in range(args.ticks):
        py_start = time.perf_counter()
        py_grid, py_active = python_step(
            grid=py_grid,
            width=width,
            height=height,
            diffuse_rate=args.diffuse_rate,
            dt=args.dt,
            epsilon=args.epsilon,
            active_indices=py_active,
        )
        py_total += time.perf_counter() - py_start

        native_start = time.perf_counter()
        native_grid, native_active = diffuse_step_native(
            grid=native_grid,
            width=width,
            height=height,
            diffuse_rate=args.diffuse_rate,
            dt=args.dt,
            epsilon=args.epsilon,
            active_indices=native_active,
        )
        native_total += time.perf_counter() - native_start

        grid_diff = max_abs_diff(py_grid, native_grid)
        active_diff = abs(len(py_active) - len(native_active))

        if grid_diff > worst_grid_diff:
            worst_grid_diff = grid_diff
        if active_diff > worst_active_diff:
            worst_active_diff = active_diff

        print(
            f"tick {tick:03d} | "
            f"py_mass={sum(py_grid):.6f} | "
            f"native_mass={sum(native_grid):.6f} | "
            f"grid_diff={grid_diff:.12f} | "
            f"py_active={len(py_active)} | "
            f"native_active={len(native_active)}"
        )

    print()
    print("=== Native Field Probe Summary ===")
    print(f"python total: {py_total * 1000.0:.4f} ms")
    print(f"native total: {native_total * 1000.0:.4f} ms")
    if args.ticks > 0:
        print(f"python avg: {(py_total / args.ticks) * 1000.0:.4f} ms")
        print(f"native avg: {(native_total / args.ticks) * 1000.0:.4f} ms")
    print(f"worst grid diff: {worst_grid_diff:.12f}")
    print(f"worst active count diff: {worst_active_diff}")
    print(f"final python mass: {sum(py_grid):.6f}")
    print(f"final native mass: {sum(native_grid):.6f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

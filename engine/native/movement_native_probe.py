"""Probe and validator for the native flat movement kernel.

This compares the Python movement step against the native movement step
for correctness and basic timing.

Usage examples:
    python3 -m engine.native.movement_native_probe --entities 1000 --ticks 300
    python3 -m engine.native.movement_native_probe --entities 5000 --ticks 300
    python3 -m engine.native.movement_native_probe --entities 10000 --ticks 300
"""

from __future__ import annotations

import argparse
import random
import time
from typing import List, Tuple

from engine.native.movement_native import update_movement_native


def python_step(
    pos_x: List[float],
    pos_y: List[float],
    vel_x: List[float],
    vel_y: List[float],
    dt: float,
) -> Tuple[List[float], List[float]]:
    count = len(pos_x)
    out_x = pos_x[:]
    out_y = pos_y[:]
    for i in range(count):
        out_x[i] += vel_x[i] * dt
        out_y[i] += vel_y[i] * dt
    return out_x, out_y


def max_abs_diff(a: List[float], b: List[float]) -> float:
    if len(a) != len(b):
        raise ValueError("List length mismatch")
    m = 0.0
    for x, y in zip(a, b):
        d = abs(x - y)
        if d > m:
            m = d
    return m


def make_data(entities: int, seed: int) -> tuple[List[float], List[float], List[float], List[float]]:
    random.seed(seed)
    pos_x = [random.uniform(-500.0, 500.0) for _ in range(entities)]
    pos_y = [random.uniform(-500.0, 500.0) for _ in range(entities)]
    vel_x = [random.uniform(-50.0, 50.0) for _ in range(entities)]
    vel_y = [random.uniform(-50.0, 50.0) for _ in range(entities)]
    return pos_x, pos_y, vel_x, vel_y


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entities", type=int, default=1000)
    parser.add_argument("--ticks", type=int, default=300)
    parser.add_argument("--dt", type=float, default=1.0 / 60.0)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    base_px, base_py, vx, vy = make_data(args.entities, args.seed)

    py_px = base_px[:]
    py_py = base_py[:]

    native_px = base_px[:]
    native_py = base_py[:]

    py_total = 0.0
    native_total = 0.0
    worst_x_diff = 0.0
    worst_y_diff = 0.0

    for _ in range(args.ticks):
        py_start = time.perf_counter()
        py_px, py_py = python_step(py_px, py_py, vx, vy, args.dt)
        py_total += time.perf_counter() - py_start

        native_start = time.perf_counter()
        native_px, native_py = update_movement_native(
            native_px, native_py, vx, vy, args.dt
        )
        native_total += time.perf_counter() - native_start

        x_diff = max_abs_diff(py_px, native_px)
        y_diff = max_abs_diff(py_py, native_py)

        if x_diff > worst_x_diff:
            worst_x_diff = x_diff
        if y_diff > worst_y_diff:
            worst_y_diff = y_diff

    print("=== Native Movement Probe Summary ===")
    print(f"entities: {args.entities}")
    print(f"ticks: {args.ticks}")
    print(f"python total: {py_total * 1000.0:.4f} ms")
    print(f"native total: {native_total * 1000.0:.4f} ms")
    if args.ticks > 0:
        print(f"python avg: {(py_total / args.ticks) * 1000.0:.4f} ms")
        print(f"native avg: {(native_total / args.ticks) * 1000.0:.4f} ms")
    print(f"worst x diff: {worst_x_diff:.12f}")
    print(f"worst y diff: {worst_y_diff:.12f}")
    if args.entities > 0:
        print(f"sample pos: ({native_px[0]:.4f}, {native_py[0]:.4f})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Flat runtime probe.

Purpose:
- run the real fixed-step loop on flat storage
- measure movement + extract together in engine-like conditions
"""

from __future__ import annotations

import argparse
import random
import time

from engine.core.flat_world import FlatWorld
from engine.systems.flat_movement_system import update_flat_movement
from engine.systems.flat_render_extract_system import extract_flat_render_packet


def run_probe(
    entities: int = 1000,
    ticks: int = 300,
    dt: float = 1.0 / 60.0,
    seed: int = 0,
) -> None:
    random.seed(seed)
    world = FlatWorld()

    for _ in range(entities):
        x = random.uniform(-400.0, 400.0)
        y = random.uniform(-300.0, 300.0)
        vx = random.uniform(-50.0, 50.0)
        vy = random.uniform(-50.0, 50.0)
        world.add(x, y, vx, vy, 1, 2)

    packet: list = []

    move_total = 0.0
    extract_total = 0.0
    tick_total = 0.0
    tick_max = 0.0

    for _ in range(ticks):
        tick_start = time.perf_counter()

        move_start = time.perf_counter()
        update_flat_movement(world, dt)
        move_total += time.perf_counter() - move_start

        extract_start = time.perf_counter()
        extract_flat_render_packet(world, packet)
        extract_total += time.perf_counter() - extract_start

        tick_elapsed = time.perf_counter() - tick_start
        tick_total += tick_elapsed
        if tick_elapsed > tick_max:
            tick_max = tick_elapsed

    print("=== Flat Runtime Probe ===")
    print(f"entities: {entities}")
    print(f"ticks: {ticks}")
    print(f"avg tick: {(tick_total / ticks) * 1000.0:.4f} ms")
    print(f"max tick: {tick_max * 1000.0:.4f} ms")
    print(f"avg movement: {(move_total / ticks) * 1000.0:.4f} ms")
    print(f"avg extract: {(extract_total / ticks) * 1000.0:.4f} ms")
    print(f"packet size: {len(packet)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entities", type=int, default=1000)
    parser.add_argument("--ticks", type=int, default=300)
    parser.add_argument("--dt", type=float, default=1.0 / 60.0)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    run_probe(args.entities, args.ticks, args.dt, args.seed)


if __name__ == "__main__":
    main()

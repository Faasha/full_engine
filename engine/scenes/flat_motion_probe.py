"""Flat motion probe.

Purpose:
- measure the benefit of flat arrays over tuple/object-heavy motion updates
- prepare the data layout for native porting later
"""

from __future__ import annotations

import argparse
import random
import time


def build_data(n: int, seed: int = 0):
    random.seed(seed)
    xs = [random.uniform(-400.0, 400.0) for _ in range(n)]
    ys = [random.uniform(-300.0, 300.0) for _ in range(n)]
    vxs = [random.uniform(-50.0, 50.0) for _ in range(n)]
    vys = [random.uniform(-50.0, 50.0) for _ in range(n)]
    return xs, ys, vxs, vys


def update_flat(xs, ys, vxs, vys, dt: float):
    for i in range(len(xs)):
        xs[i] += vxs[i] * dt
        ys[i] += vys[i] * dt


def run_probe(entities: int, ticks: int, dt: float, seed: int):
    xs, ys, vxs, vys = build_data(entities, seed)

    start = time.perf_counter()
    for _ in range(ticks):
        update_flat(xs, ys, vxs, vys, dt)
    elapsed = time.perf_counter() - start

    avg_tick_ms = (elapsed / ticks) * 1000.0

    print("=== Flat Motion Probe ===")
    print(f"entities: {entities}")
    print(f"ticks: {ticks}")
    print(f"total: {elapsed * 1000.0:.4f} ms")
    print(f"avg tick: {avg_tick_ms:.4f} ms")
    print(f"sample pos: ({xs[0]:.4f}, {ys[0]:.4f})")


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

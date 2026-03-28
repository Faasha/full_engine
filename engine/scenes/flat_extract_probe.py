"""Flat render extract probe."""

from __future__ import annotations

import argparse
import random
import time


def build_data(n: int, seed: int = 0):
    random.seed(seed)
    xs = [random.uniform(-400.0, 400.0) for _ in range(n)]
    ys = [random.uniform(-300.0, 300.0) for _ in range(n)]
    mesh = [1 for _ in range(n)]
    material = [2 for _ in range(n)]
    return xs, ys, mesh, material


def extract_flat(xs, ys, mesh, material, packet):
    packet.clear()
    for i in range(len(xs)):
        packet.append((mesh[i], material[i], xs[i], ys[i]))


def run_probe(entities: int, ticks: int, seed: int):
    xs, ys, mesh, material = build_data(entities, seed)
    packet = []

    start = time.perf_counter()
    for _ in range(ticks):
        extract_flat(xs, ys, mesh, material, packet)
    elapsed = time.perf_counter() - start

    avg_tick_ms = (elapsed / ticks) * 1000.0

    print("=== Flat Extract Probe ===")
    print(f"entities: {entities}")
    print(f"ticks: {ticks}")
    print(f"total: {elapsed * 1000.0:.4f} ms")
    print(f"avg tick: {avg_tick_ms:.4f} ms")
    print(f"packet size: {len(packet)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entities", type=int, default=1000)
    parser.add_argument("--ticks", type=int, default=300)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    run_probe(args.entities, args.ticks, args.seed)


if __name__ == "__main__":
    main()

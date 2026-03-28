"""Field probe.

Purpose:
- isolate the behavioural field from the rest of the engine
- verify diffusion conserves mass
- verify dissolve/instantiate accounting
- expose threshold loss and edge loss directly

Run examples:
    python3 -m engine.scenes.field_probe --ticks 120
    python3 -m engine.scenes.field_probe --ticks 120 --inject 32,32,100
    python3 -m engine.scenes.field_probe --ticks 120 --inject 0,0,100
    python3 -m engine.scenes.field_probe --ticks 120 --inject 63,63,100
"""

from __future__ import annotations

import argparse
from typing import List, Tuple

from engine.systems.field_system import FieldSystem


def parse_injections(values: List[str]) -> List[Tuple[int, int, float]]:
    out: List[Tuple[int, int, float]] = []
    for v in values:
        x, y, w = v.split(",")
        out.append((int(x), int(y), float(w)))
    return out


def run_probe(
    *,
    width: int = 64,
    height: int = 64,
    diffuse_rate: float = 0.1,
    ticks: int = 120,
    dt: float = 1.0 / 60.0,
    injections: List[Tuple[int, int, float]] | None = None,
) -> None:
    field = FieldSystem(width=width, height=height, diffuse_rate=diffuse_rate)

    if not injections:
        injections = [(width // 2, height // 2, 100.0)]

    for x, y, w in injections:
        field.dissolve(x, y, w)

    baseline = field.total_mass()
    print("=== Field Probe Start ===")
    print(f"grid: {width}x{height}")
    print(f"diffuse_rate: {diffuse_rate}")
    print(f"ticks: {ticks}")
    print(f"dt: {dt}")
    print(f"baseline mass: {baseline:.6f}")
    print(f"injections: {injections}")
    print()

    for tick in range(ticks):
        pre = field.total_mass()
        field.update(dt)
        post = field.total_mass()
        delta = post - pre
        print(
            f"tick {tick:03d} | pre={pre:.6f} | post={post:.6f} | delta={delta:+.6f}"
        )

    final = field.total_mass()
    loss = baseline - final

    print()
    print("=== Field Probe Summary ===")
    print(f"baseline mass: {baseline:.6f}")
    print(f"final mass:    {final:.6f}")
    print(f"mass loss:     {loss:.6f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe field conservation.")
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--diffuse-rate", type=float, default=0.1)
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument("--dt", type=float, default=1.0 / 60.0)
    parser.add_argument(
        "--inject",
        action="append",
        default=[],
        help="Injection as x,y,weight . Can be repeated.",
    )
    args = parser.parse_args()

    injections = parse_injections(args.inject)
    run_probe(
        width=args.width,
        height=args.height,
        diffuse_rate=args.diffuse_rate,
        ticks=args.ticks,
        dt=args.dt,
        injections=injections,
    )


if __name__ == "__main__":
    main()

"""Entry point for the runtime."""

from __future__ import annotations

import argparse
import sys

from engine.scenes.playable_slice import run_playable_slice
from engine.scenes.stress_null import run_stress_scene
from engine.scenes.world_slice import run_world_slice


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        choices=("stress", "playable", "world"),
        default="stress",
        help="Which scene mode to run.",
    )
    parser.add_argument("--entities", type=int, default=1000)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--fps", type=float, default=60.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--field", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--graphics", action="store_true")

    parser.add_argument("--field-width", type=int, default=64)
    parser.add_argument("--field-height", type=int, default=64)
    parser.add_argument("--diffuse-rate", type=float, default=0.1)
    parser.add_argument("--dissolve-radius", type=float, default=400.0)
    parser.add_argument("--spawn-radius", type=float, default=300.0)
    parser.add_argument("--cell-size", type=float, default=50.0)
    parser.add_argument("--threshold", type=float, default=10.0)
    parser.add_argument("--max-per-cell", type=int, default=1)

    parser.add_argument("--chunk-width", type=float, default=256.0)
    parser.add_argument("--chunk-height", type=float, default=256.0)
    parser.add_argument("--active-radius", type=int, default=1)
    parser.add_argument("--warm-radius", type=int, default=2)

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.mode == "playable":
        run_playable_slice(
            duration=args.duration,
            seed=args.seed,
            fps=args.fps,
            use_graphics=args.graphics,
            num_agents=min(args.entities, 128),
            use_field=args.field,
            field_width=min(args.field_width, 32) if args.field else 32,
            field_height=min(args.field_height, 32) if args.field else 32,
            diffuse_rate=min(args.diffuse_rate, 0.05) if args.field else 0.05,
            dissolve_radius=args.dissolve_radius,
            spawn_radius=min(args.spawn_radius, 220.0),
            cell_size=max(args.cell_size, 60.0),
            threshold=max(args.threshold, 18.0),
            max_entities_per_cell=args.max_per_cell,
        )
        return 0

    if args.mode == "world":
        run_world_slice(
            duration=args.duration,
            seed=args.seed,
            fps=args.fps,
            use_graphics=args.graphics,
            player_speed=150.0,
            chunk_width=args.chunk_width,
            chunk_height=args.chunk_height,
            active_radius=args.active_radius,
            debug_level="full",
            warm_radius=args.warm_radius,
        )
        return 0

    run_stress_scene(
        num_entities=args.entities,
        duration=args.duration,
        seed=args.seed,
        fps=args.fps,
        use_graphics=args.graphics,
        verbose=args.verbose,
        field_width=args.field_width,
        field_height=args.field_height,
        diffuse_rate=args.diffuse_rate,
        dissolve_radius=args.dissolve_radius,
        spawn_radius=args.spawn_radius,
        cell_size=args.cell_size,
        threshold=args.threshold,
        max_entities_per_cell=args.max_per_cell,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Demo scene showcasing a simple world with obstacles and moving agents.

This script demonstrates how the deterministic runtime can be used to
simulate a small interactive world.  It spawns a configurable number
of agents in a bounded area with static rectangular obstacles.  Each
agent has a position, velocity, renderable and collider.  The
``movement_system`` integrates velocities, the ``collision_system``
reflects velocities off world boundaries and obstacles, and the
render extract system builds a packet for the renderer.  The
behavioural field can optionally be enabled to test dissolution and
instantiation alongside obstacles.

At the end of the run, the script prints a timing summary, hitch
counts, memory usage, the final number of active entities and the
total field mass.

Usage::

    python3 -m engine.scenes.demo_scene --entities 50 --duration 10 \
        --width 800 --height 600 --fps 60 --field

Static obstacles can be defined via the ``--obstacle`` flag multiple
times as ``x,y,w,h`` coordinates.  Coordinates and sizes are in the
same world units as entity positions.  The origin is at the centre
of the world.
"""

from __future__ import annotations

import argparse
import random
import queue
import resource
import threading
import time
from typing import Dict, Iterable, List, Tuple

from engine.core.id_allocator import IDAllocator
from engine.core.ecs import ECS
from engine.core.frame_arena import FrameArena
from engine.core.fixed_step import run_fixed_step
from engine.core.event_log import EventLog
from engine.components.transform import Transform
from engine.components.velocity import Velocity
from engine.components.renderable import Renderable
from engine.components.collider import Collider
from engine.assets.asset_manager import AssetManager
from engine.systems.movement_system import update_movement
from engine.systems.collision_system import handle_collisions
from engine.systems.field_system import FieldSystem
from engine.systems.dissolve_system import dissolve_distant_entities
from engine.systems.instantiate_system import instantiate_from_field
from engine.systems.render_extract_system import extract_render_packet
from engine.render.renderer import Renderer


def run_demo_scene(
    num_entities: int = 50,
    duration: float = 10.0,
    seed: int = 0,
    fps: float = 60.0,
    width: float = 800.0,
    height: float = 600.0,
    obstacles: Iterable[Tuple[float, float, float, float]] = (),
    use_field: bool = False,
    max_entities_per_cell: int = 4,
    verbose: bool = False,
) -> Dict[Tuple[int, int], Tuple[float, float]]:
    """Run the demo scene.

    Parameters
    ----------
    num_entities:
        Number of moving agents to spawn at the start of the simulation.
    duration:
        Duration of the simulation in seconds.
    seed:
        Random seed for reproducibility.
    fps:
        Fixed simulation rate (ticks per second).
    width, height:
        Size of the world rectangle.  The world extends from
        ``-width/2`` to ``width/2`` along X and ``-height/2`` to
        ``height/2`` along Y.  Obstacles and entities are placed
        relative to this coordinate system.
    obstacles:
        A list of static obstacles defined as ``(x, y, w, h)`` in
        world coordinates.  Each obstacle is centred at ``(x, y)`` and
        extends ``w`` and ``h`` units along X and Y.
    use_field:
        Whether to enable the behavioural field.  If False, all
        entities remain in the ECS; if True, distant entities will
        dissolve into the field and reappear as the player returns.
    max_entities_per_cell:
        Maximum number of entities that can be spawned from any
        single field cell per tick.  This controls the rate of
        instantiation when the field is enabled.
    verbose:
        If True, log when render packets are dropped.
    """
    random.seed(seed)
    # Core systems
    id_alloc = IDAllocator()
    ecs = ECS(id_alloc)
    arena = FrameArena()
    event_log = EventLog()
    field = FieldSystem(width=64, height=64)
    assets = AssetManager()

    # Determine world boundaries
    half_w = width / 2.0
    half_h = height / 2.0
    world_bounds = (-half_w, -half_h, half_w, half_h)

    # Create obstacles: convert to internal list
    obstacle_list: List[Tuple[float, float, float, float]] = list(obstacles)

    # Dummy asset handles for all entities
    mesh = assets.create_asset("default_mesh")
    material = assets.create_asset("default_material")

    # Spawn moving agents
    for _ in range(num_entities):
        pos = (
            random.uniform(-half_w * 0.75, half_w * 0.75),
            random.uniform(-half_h * 0.75, half_h * 0.75),
        )
        vel = (
            random.uniform(-100.0, 100.0),
            random.uniform(-100.0, 100.0),
        )
        size = (20.0, 20.0)  # All agents have the same collider size
        ecs.create_entity(
            {
                Transform: Transform(position=pos),
                Velocity: Velocity(value=vel),
                Renderable: Renderable(mesh_handle=mesh, material_handle=material),
                Collider: Collider(size=size),
            }
        )

    # Optionally spawn a player at the centre with slower velocity
    player_pos = (0.0, 0.0)
    player_vel = (0.0, 0.0)
    player_size = (25.0, 25.0)
    ecs.create_entity(
        {
            Transform: Transform(position=player_pos),
            Velocity: Velocity(value=player_vel),
            Renderable: Renderable(mesh_handle=mesh, material_handle=material),
            Collider: Collider(size=player_size),
        }
    )

    # Renderer setup
    packet_queue: queue.Queue = queue.Queue(maxsize=3)
    stop_event = threading.Event()
    renderer = Renderer()
    renderer.start(packet_queue, stop_event, use_graphics=False)

    # Instrumentation accumulators
    tick_count = 0
    tick_total = 0.0
    tick_max = 0.0
    move_total = 0.0
    move_max = 0.0
    extract_total = 0.0
    extract_max = 0.0
    hitch_16 = 0
    hitch_20 = 0
    hitch_33 = 0
    budget_ms = 1000.0 / fps

    # Main update function
    def update_fn(tick: int, dt: float) -> None:
        nonlocal tick_count, tick_total, tick_max
        nonlocal move_total, move_max
        nonlocal extract_total, extract_max
        nonlocal hitch_16, hitch_20, hitch_33

        start = time.perf_counter()
        # Field update and boundary events
        if use_field:
            # Update the field diffusion
            field.update(dt)
        # Resolve collisions against boundaries and obstacles
        handle_collisions(ecs, world_bounds, obstacle_list)
        # Movement integration
        move_start = time.perf_counter()
        update_movement(ecs, dt)
        move_elapsed = time.perf_counter() - move_start
        move_total += move_elapsed
        move_max = max(move_max, move_elapsed)
        # Behavioural field dissolve and instantiate if enabled
        if use_field:
            dissolve_distant_entities(ecs, field)
            instantiate_from_field(
                ecs, field, assets, max_entities_per_cell=max_entities_per_cell
            )
        # Render packet extraction
        extract_start = time.perf_counter()
        packet = extract_render_packet(ecs, arena)
        extract_elapsed = time.perf_counter() - extract_start
        extract_total += extract_elapsed
        extract_max = max(extract_max, extract_elapsed)
        # Enqueue packet to renderer
        try:
            packet_queue.put_nowait(packet)
        except queue.Full:
            if verbose:
                print(f"[Simulation] Packet dropped at tick {tick}")
        # Clear transient allocations
        arena.clear()
        # Tick timing end
        elapsed = time.perf_counter() - start
        tick_total += elapsed
        tick_max = max(tick_max, elapsed)
        # Hitch counting
        ms = elapsed * 1000.0
        if ms > budget_ms:
            hitch_16 += 1
        if ms > 20.0:
            hitch_20 += 1
        if ms > 33.33:
            hitch_33 += 1
        tick_count += 1

    # Run simulation
    run_fixed_step(fps, update_fn, duration=duration)
    # Stop renderer
    stop_event.set()
    renderer.stop()
    # Instrumentation summary
    if tick_count > 0:
        avg_tick_ms = tick_total / tick_count * 1000.0
        avg_move_ms = move_total / tick_count * 1000.0
        avg_extract_ms = extract_total / tick_count * 1000.0
        print("=== Timing Summary ===")
        print(f"ticks: {tick_count}")
        print(f"avg tick: {avg_tick_ms:.4f} ms")
        print(f"max tick: {tick_max * 1000.0:.4f} ms")
        print(f"avg movement: {avg_move_ms:.4f} ms")
        print(f"max movement: {move_max * 1000.0:.4f} ms")
        print(f"avg extract: {avg_extract_ms:.4f} ms")
        print(f"max extract: {extract_max * 1000.0:.4f} ms")
        print("=== Hitch Summary ===")
        print(f">{budget_ms:.2f} ms: {hitch_16}")
        print(f">20.00 ms: {hitch_20}")
        print(f">33.33 ms: {hitch_33}")
        # Memory usage
        usage = resource.getrusage(resource.RUSAGE_SELF)
        max_rss_kb = usage.ru_maxrss
        print("=== Memory Usage ===")
        print(f"max RSS: {max_rss_kb} KB")
        # Mass accounting if field enabled
        if use_field:
            active_entities = 0
            transforms = ecs.get_component_array(Transform)
            for row in range(ecs.rows()):
                if transforms[row] is not None:
                    active_entities += 1
            print("=== Mass Summary ===")
            print(f"active entities: {active_entities}")
            print(f"field mass: {field.total_mass():.2f}")
    return ecs.snapshot_positions()


def _parse_obstacles(values: List[str]) -> List[Tuple[float, float, float, float]]:
    result: List[Tuple[float, float, float, float]] = []
    for v in values:
        parts = v.split(",")
        if len(parts) != 4:
            raise argparse.ArgumentTypeError(
                f"Invalid obstacle specification '{v}'. Must be x,y,w,h."
            )
        try:
            x, y, w, h = map(float, parts)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Invalid obstacle specification '{v}'. Must be x,y,w,h."
            )
        result.append((x, y, w, h))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the demo scene.")
    parser.add_argument(
        "--entities",
        type=int,
        default=50,
        help="Number of moving agents to spawn (default: 50).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Simulation duration in seconds (default: 10).",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=60.0,
        help="Fixed simulation rate (default: 60).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for reproducibility (default: 0).",
    )
    parser.add_argument(
        "--width",
        type=float,
        default=800.0,
        help="World width (default: 800).",
    )
    parser.add_argument(
        "--height",
        type=float,
        default=600.0,
        help="World height (default: 600).",
    )
    parser.add_argument(
        "--obstacle",
        action="append",
        default=[],
        metavar="X,Y,W,H",
        help=(
            "Add a static obstacle defined by its centre coordinates and size."
        ),
    )
    parser.add_argument(
        "--field",
        action="store_true",
        help="Enable the behavioural field (distant simulation).",
    )
    parser.add_argument(
        "--max-per-cell",
        type=int,
        default=4,
        help="Max entities spawned per field cell per tick (default: 4).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print debug messages when packets are dropped.",
    )
    args = parser.parse_args()
    obstacles = _parse_obstacles(args.obstacle)
    run_demo_scene(
        num_entities=args.entities,
        duration=args.duration,
        seed=args.seed,
        fps=args.fps,
        width=args.width,
        height=args.height,
        obstacles=obstacles,
        use_field=args.field,
        max_entities_per_cell=args.max_per_cell,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
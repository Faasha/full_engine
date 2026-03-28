"""Stress-null scene setup and simulation runner.

This scene exists to expose the core runtime truth:
- deterministic fixed-step simulation
- behavioural field diffusion
- dissolve / instantiate accounting
- flat hot-path movement
- flat render extraction
- timing and hitch visibility

It intentionally avoids gameplay complexity so the runtime costs stay visible.
"""

from __future__ import annotations

import queue
import random
import threading
import time
from typing import Dict, Tuple

from engine.core.id_allocator import IDAllocator
from engine.core.ecs import ECS
from engine.core.flat_world import FlatWorld
from engine.core.occupancy_map import OccupancyMap
from engine.core.frame_arena import FrameArena
from engine.core.fixed_step import run_fixed_step
from engine.core.event_log import EventLog
from engine.components.transform import Transform
from engine.components.velocity import Velocity
from engine.components.renderable import Renderable
from engine.assets.asset_manager import AssetManager
from engine.systems.field_system import FieldSystem
from engine.systems.instantiate_system import instantiate_from_field
from engine.systems.flat_movement_system import update_flat_movement
from engine.systems.flat_render_extract_system import extract_flat_render_packet
from engine.systems.flat_sync_system import (
    build_flat_world_from_ecs,
    write_flat_positions_back_to_ecs,
)
from engine.render.renderer import Renderer
from engine.render.packet_buffers import PacketBufferPool


def run_stress_scene(
    num_entities: int = 1000,
    duration: float = 5.0,
    seed: int = 0,
    fps: float = 60.0,
    use_graphics: bool = False,
    verbose: bool = False,
    *,
    field_width: int = 64,
    field_height: int = 64,
    diffuse_rate: float = 0.1,
    dissolve_radius: float = 400.0,
    spawn_radius: float = 300.0,
    cell_size: float = 50.0,
    threshold: float = 10.0,
    max_entities_per_cell: int = 1,
    dissolve_budget: int = 32,
    dissolve_scan_budget: int = 128,
) -> Dict[Tuple[int, int], Tuple[float, float]]:
    """Run the stress-null scene and return final positions."""
    random.seed(seed)

    id_alloc = IDAllocator()
    ecs = ECS(id_alloc)
    arena = FrameArena()
    event_log = EventLog()
    field = FieldSystem(width=field_width, height=field_height, diffuse_rate=diffuse_rate)
    assets = AssetManager()

    default_mesh = assets.create_asset("default_mesh")
    default_material = assets.create_asset("default_material")
    agent_mesh = assets.create_asset("agent_mesh")
    agent_material = assets.create_asset("agent_material")

    for _ in range(num_entities):
        pos = (
            random.uniform(-dissolve_radius, dissolve_radius),
            random.uniform(-dissolve_radius * 0.75, dissolve_radius * 0.75),
        )
        vel = (
            random.uniform(-50.0, 50.0),
            random.uniform(-50.0, 50.0),
        )
        ecs.create_entity(
            {
                Transform: Transform(position=pos),
                Velocity: Velocity(value=vel),
                Renderable: Renderable(
                    mesh_handle=default_mesh,
                    material_handle=default_material,
                ),
            }
        )

    world = FlatWorld()
    build_flat_world_from_ecs(ecs, world)

    occupancy = OccupancyMap(cell_size=cell_size)
    occupancy.rebuild_from_flat_world(world)

    packet_queue: queue.Queue = queue.Queue(maxsize=3)
    stop_event = threading.Event()
    packet_pool = PacketBufferPool(count=3)

    renderer = Renderer()
    renderer.start(
        packet_queue,
        stop_event,
        use_graphics=use_graphics,
        packet_pool=packet_pool,
    )

    tick_count = 0
    tick_total = 0.0
    tick_max = 0.0

    movement_total = 0.0
    movement_max = 0.0

    extract_total = 0.0
    extract_max = 0.0

    field_total = 0.0
    field_max = 0.0

    dissolve_total = 0.0
    dissolve_max = 0.0

    instantiate_total = 0.0
    instantiate_max = 0.0

    enqueue_total = 0.0
    enqueue_max = 0.0

    budget_ms = 1000.0 / fps
    hitch_16 = 0
    hitch_20 = 0
    hitch_33 = 0

    dissolved_total = 0
    instantiated_total = 0
    mass_delta_total = 0.0
    active_delta_total = 0

    baseline_total = ecs.rows() + field.total_mass()

    pending_dissolves: list[tuple[tuple[int, int], float, float]] = []
    pending_dissolve_ids: set[tuple[int, int]] = set()
    dissolve_scan_cursor = 0

    def scan_for_dissolves(limit: int) -> int:
        """Incrementally scan FlatWorld and enqueue distant dissolve candidates.

        This avoids the old full-world refill spike. We scan only a slice of the
        active world each tick, starting from a rolling cursor.
        """
        nonlocal dissolve_scan_cursor

        world_len = len(world.index_to_entity)
        if world_len == 0:
            dissolve_scan_cursor = 0
            return 0

        radius_sq = dissolve_radius * dissolve_radius
        scanned = min(limit, world_len)

        for _ in range(scanned):
            if dissolve_scan_cursor >= world_len:
                dissolve_scan_cursor = 0
                world_len = len(world.index_to_entity)
                if world_len == 0:
                    break

            entity_id = world.index_to_entity[dissolve_scan_cursor]

            # Skip entities already queued or removed.
            if entity_id in pending_dissolve_ids or not world.has(entity_id):
                dissolve_scan_cursor += 1
                continue

            idx = world.entity_to_index[entity_id]
            x = world.pos_x[idx]
            y = world.pos_y[idx]

            if x * x + y * y > radius_sq:
                pending_dissolves.append((entity_id, x, y))
                pending_dissolve_ids.add(entity_id)

            dissolve_scan_cursor += 1

        return scanned

    def process_dissolves(limit: int) -> int:
        """Process up to `limit` pending dissolves."""
        count = 0
        half_w = field.width // 2
        half_h = field.height // 2

        n = min(limit, len(pending_dissolves))
        for _ in range(n):
            entity_id, x, y = pending_dissolves.pop(0)
            pending_dissolve_ids.discard(entity_id)

            if not world.has(entity_id):
                continue

            local_cx, local_cy = occupancy.world_to_cell(x, y)
            occupancy.decrement(local_cx, local_cy, 1)

            cx = int(x / cell_size) + half_w
            cy = int(y / cell_size) + half_h

            if cx < 0:
                cx = 0
            elif cx >= field.width:
                cx = field.width - 1

            if cy < 0:
                cy = 0
            elif cy >= field.height:
                cy = field.height - 1

            field.dissolve(cx, cy, 1.0)
            world.remove(entity_id)
            ecs.destroy_entity(entity_id)
            count += 1

        return count

    def update_fn(tick: int, dt: float) -> None:
        nonlocal tick_count, tick_total, tick_max
        nonlocal movement_total, movement_max
        nonlocal extract_total, extract_max
        nonlocal field_total, field_max
        nonlocal dissolve_total, dissolve_max
        nonlocal instantiate_total, instantiate_max
        nonlocal enqueue_total, enqueue_max
        nonlocal hitch_16, hitch_20, hitch_33
        nonlocal dissolved_total, instantiated_total
        nonlocal mass_delta_total, active_delta_total

        tick_start = time.perf_counter()

        pre_active = ecs.rows()
        pre_mass = field.total_mass()

        field_start = time.perf_counter()
        field.update(dt)
        field_elapsed = time.perf_counter() - field_start
        field_total += field_elapsed
        if field_elapsed > field_max:
            field_max = field_elapsed

        dissolve_start = time.perf_counter()
        scan_for_dissolves(dissolve_scan_budget)
        dissolved = process_dissolves(dissolve_budget)
        dissolve_elapsed = time.perf_counter() - dissolve_start
        dissolve_total += dissolve_elapsed
        if dissolve_elapsed > dissolve_max:
            dissolve_max = dissolve_elapsed

        instantiate_start = time.perf_counter()
        spawned = instantiate_from_field(
            ecs,
            field,
            assets,
            occupancy=occupancy,
            world=world,
            spawn_radius=spawn_radius,
            cell_size=cell_size,
            threshold=threshold,
            max_entities_per_cell=max_entities_per_cell,
            mesh_handle=agent_mesh,
            material_handle=agent_material,
        )
        instantiate_elapsed = time.perf_counter() - instantiate_start
        instantiate_total += instantiate_elapsed
        if instantiate_elapsed > instantiate_max:
            instantiate_max = instantiate_elapsed

        post_active = ecs.rows()
        post_mass = field.total_mass()
        active_delta = post_active - pre_active
        mass_delta = post_mass - pre_mass

        dissolved_total += dissolved
        instantiated_total += spawned
        mass_delta_total += mass_delta
        active_delta_total += active_delta

        if verbose:
            total_mass = post_active + post_mass
            print(
                f"Tick {tick}: pre-diff {pre_mass:.2f}, post-diff {post_mass:.2f}, "
                f"dissolved {dissolved}, instantiated {spawned}, total mass {total_mass:.2f}"
            )

        move_start = time.perf_counter()
        update_flat_movement(world, dt)
        move_elapsed = time.perf_counter() - move_start
        movement_total += move_elapsed
        if move_elapsed > movement_max:
            movement_max = move_elapsed

        packet = packet_pool.acquire()
        extract_start = time.perf_counter()
        packet = extract_flat_render_packet(world, packet)
        extract_elapsed = time.perf_counter() - extract_start
        extract_total += extract_elapsed
        if extract_elapsed > extract_max:
            extract_max = extract_elapsed

        enqueue_start = time.perf_counter()
        try:
            packet_queue.put_nowait(packet)
        except queue.Full:
            packet_pool.release(packet)
            if verbose:
                print(f"[Simulation] Packet dropped at tick {tick}")
        enqueue_elapsed = time.perf_counter() - enqueue_start
        enqueue_total += enqueue_elapsed
        if enqueue_elapsed > enqueue_max:
            enqueue_max = enqueue_elapsed

        arena.clear()

        tick_elapsed = time.perf_counter() - tick_start
        tick_total += tick_elapsed
        if tick_elapsed > tick_max:
            tick_max = tick_elapsed

        tick_ms = tick_elapsed * 1000.0
        if tick_ms > budget_ms:
            print(
                f"[HITCH] tick {tick} | total={tick_ms:.2f} ms | "
                f"field={field_elapsed * 1000.0:.2f} | "
                f"dissolve={dissolve_elapsed * 1000.0:.2f} | "
                f"instantiate={instantiate_elapsed * 1000.0:.2f} | "
                f"move={move_elapsed * 1000.0:.2f} | "
                f"extract={extract_elapsed * 1000.0:.2f} | "
                f"enqueue={enqueue_elapsed * 1000.0:.2f} | "
                f"active={post_active} | "
                f"field_cells={len(field.active_indices)} | "
                f"dissolved={dissolved} | spawned={spawned} | "
                f"pending_dissolves={len(pending_dissolves)}"
            )
            hitch_16 += 1
        if tick_ms > 20.0:
            hitch_20 += 1
        if tick_ms > 33.33:
            hitch_33 += 1

        tick_count += 1

    run_fixed_step(fps, update_fn, duration=duration)

    stop_event.set()
    renderer.stop()

    write_flat_positions_back_to_ecs(ecs, world)

    if tick_count > 0:
        avg_tick_ms = (tick_total / tick_count) * 1000.0
        avg_move_ms = (movement_total / tick_count) * 1000.0
        avg_extract_ms = (extract_total / tick_count) * 1000.0
        avg_field_ms = (field_total / tick_count) * 1000.0
        avg_dissolve_ms = (dissolve_total / tick_count) * 1000.0
        avg_instantiate_ms = (instantiate_total / tick_count) * 1000.0
        avg_enqueue_ms = (enqueue_total / tick_count) * 1000.0

        print("=== Timing Summary ===")
        print(f"ticks: {tick_count}")
        print(f"avg tick: {avg_tick_ms:.4f} ms")
        print(f"max tick: {tick_max * 1000.0:.4f} ms")
        print(f"avg movement: {avg_move_ms:.4f} ms")
        print(f"max movement: {movement_max * 1000.0:.4f} ms")
        print(f"avg extract: {avg_extract_ms:.4f} ms")
        print(f"max extract: {extract_max * 1000.0:.4f} ms")
        print(f"avg field: {avg_field_ms:.4f} ms")
        print(f"max field: {field_max * 1000.0:.4f} ms")
        print(f"avg dissolve: {avg_dissolve_ms:.4f} ms")
        print(f"max dissolve: {dissolve_max * 1000.0:.4f} ms")
        print(f"avg instantiate: {avg_instantiate_ms:.4f} ms")
        print(f"max instantiate: {instantiate_max * 1000.0:.4f} ms")
        print(f"avg enqueue: {avg_enqueue_ms:.4f} ms")
        print(f"max enqueue: {enqueue_max * 1000.0:.4f} ms")

        print("=== Hitch Summary ===")
        print(f">{budget_ms:.2f} ms: {hitch_16}")
        print(f">20.00 ms: {hitch_20}")
        print(f">33.33 ms: {hitch_33}")

        active_count = ecs.rows()
        field_mass = field.total_mass()
        final_total = active_count + field_mass

        print("=== Mass Summary ===")
        print(f"initial active: {num_entities}")
        print("initial field mass: 0.00")
        print(f"final active: {active_count}")
        print(f"final field mass: {field_mass:.2f}")
        print(f"total dissolved: {dissolved_total}")
        print(f"total instantiated: {instantiated_total}")
        print(f"active delta: {active_delta_total}")
        print(f"field mass delta: {mass_delta_total:.2f}")
        print(f"baseline total mass: {baseline_total:.2f}")
        print(f"final total mass: {final_total:.2f}")
        print(f"estimated mass loss: {baseline_total - final_total:.2f}")

        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            print("=== Memory Usage ===")
            print(f"max RSS: {usage.ru_maxrss} KB")
        except Exception:
            pass

    return ecs.snapshot_positions()

"""First ugly playable slice.

Optimized playable-mode version:
- lighter field workload
- optional no-field toggle
- static obstacles
- cheap nearby wander behavior
- obstacle-aware agent steering
- upgraded render metadata for readable camera-centered view

This is the current live path:
the no-field slice is the real playable core,
while field-enabled mode remains experimental.
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
from engine.components.transform import Transform
from engine.components.velocity import Velocity
from engine.components.renderable import Renderable
from engine.components.player_tag import PlayerTag
from engine.assets.asset_manager import AssetManager
from engine.systems.field_system import FieldSystem
from engine.systems.instantiate_system import instantiate_from_field
from engine.systems.player_input_system import apply_player_input
from engine.systems.agent_wander_system import build_wander_state, update_agent_wander
from engine.systems.simple_collision_system import (
    RectObstacle,
    WorldBounds,
    resolve_static_obstacles,
    resolve_world_bounds,
)
from engine.systems.flat_movement_system import update_flat_movement
from engine.systems.flat_render_extract_system import extract_flat_render_packet
from engine.systems.flat_sync_system import (
    build_flat_world_from_ecs,
    write_flat_positions_back_to_ecs,
)
from engine.render.renderer import Renderer
from engine.render.packet_buffers import PacketBufferPool


def _poll_keys_pygame() -> dict[str, bool]:
    try:
        import pygame
    except Exception:
        return {"left": False, "right": False, "up": False, "down": False}

    pygame.event.pump()
    pressed = pygame.key.get_pressed()

    return {
        "left": bool(pressed[pygame.K_LEFT] or pressed[pygame.K_a]),
        "right": bool(pressed[pygame.K_RIGHT] or pressed[pygame.K_d]),
        "up": bool(pressed[pygame.K_UP] or pressed[pygame.K_w]),
        "down": bool(pressed[pygame.K_DOWN] or pressed[pygame.K_s]),
    }


def run_playable_slice(
    duration: float = 10.0,
    seed: int = 0,
    fps: float = 60.0,
    use_graphics: bool = True,
    num_agents: int = 32,
    player_speed: float = 140.0,
    *,
    use_field: bool = True,
    field_width: int = 32,
    field_height: int = 32,
    diffuse_rate: float = 0.05,
    dissolve_radius: float = 450.0,
    spawn_radius: float = 220.0,
    cell_size: float = 60.0,
    threshold: float = 18.0,
    max_entities_per_cell: int = 1,
    dissolve_budget: int = 16,
    dissolve_scan_budget: int = 96,
    initial_field_pockets: int = 24,
) -> Dict[Tuple[int, int], Tuple[float, float]]:
    random.seed(seed)

    id_alloc = IDAllocator()
    ecs = ECS(id_alloc)
    arena = FrameArena()
    assets = AssetManager()

    field = FieldSystem(
        width=field_width,
        height=field_height,
        diffuse_rate=diffuse_rate,
    )

    player_mesh = assets.create_asset("player_mesh")
    player_material = assets.create_asset("player_material")
    agent_mesh = assets.create_asset("agent_mesh")
    agent_material = assets.create_asset("agent_material")

    actor_radius = 8.0

    bounds = WorldBounds(
        min_x=-420.0,
        min_y=-320.0,
        max_x=420.0,
        max_y=320.0,
    )

    obstacles = [
        RectObstacle(x=-60.0, y=-220.0, w=120.0, h=40.0),
        RectObstacle(x=-220.0, y=-40.0, w=80.0, h=160.0),
        RectObstacle(x=140.0, y=-20.0, w=120.0, h=40.0),
        RectObstacle(x=-40.0, y=120.0, w=220.0, h=40.0),
        RectObstacle(x=240.0, y=120.0, w=40.0, h=120.0),
    ]
    obstacle_tuples = [(o.x, o.y, o.w, o.h) for o in obstacles]

    player_id = ecs.create_entity(
        {
            Transform: Transform(position=(0.0, 0.0)),
            Velocity: Velocity(value=(0.0, 0.0)),
            Renderable: Renderable(
                mesh_handle=player_mesh,
                material_handle=player_material,
            ),
            PlayerTag: PlayerTag(),
        }
    )

    for _ in range(num_agents):
        x = 0.0
        y = 0.0
        for _attempt in range(16):
            x = random.uniform(-260.0, 260.0)
            y = random.uniform(-180.0, 180.0)

            blocked = False
            for rect in obstacles:
                if (
                    rect.x - 16.0 <= x <= rect.x + rect.w + 16.0
                    and rect.y - 16.0 <= y <= rect.y + rect.h + 16.0
                ):
                    blocked = True
                    break

            if not blocked:
                break

        vx = random.uniform(-25.0, 25.0)
        vy = random.uniform(-25.0, 25.0)
        ecs.create_entity(
            {
                Transform: Transform(position=(x, y)),
                Velocity: Velocity(value=(vx, vy)),
                Renderable: Renderable(
                    mesh_handle=agent_mesh,
                    material_handle=agent_material,
                ),
            }
        )

    if use_field:
        half_w = field.width // 2
        half_h = field.height // 2
        for _ in range(initial_field_pockets):
            cx = random.randint(0, field.width - 1)
            cy = random.randint(0, field.height - 1)
            if abs(cx - half_w) < 3 and abs(cy - half_h) < 3:
                continue
            field.dissolve(cx, cy, random.uniform(6.0, 12.0))

    world = FlatWorld()
    build_flat_world_from_ecs(ecs, world)
    wander_state = build_wander_state(world)

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

    input_total = 0.0
    input_max = 0.0

    wander_total = 0.0
    wander_max = 0.0

    movement_total = 0.0
    movement_max = 0.0

    collision_total = 0.0
    collision_max = 0.0

    field_total = 0.0
    field_max = 0.0

    instantiate_total = 0.0
    instantiate_max = 0.0

    extract_total = 0.0
    extract_max = 0.0

    enqueue_total = 0.0
    enqueue_max = 0.0

    budget_ms = 1000.0 / fps
    hitch_16 = 0
    hitch_20 = 0
    hitch_33 = 0

    pending_dissolves: list[tuple[tuple[int, int], float, float]] = []
    pending_dissolve_ids: set[tuple[int, int]] = set()
    dissolve_scan_cursor = 0
    dissolved_total = 0
    instantiated_total = 0
    collisions_total = 0

    def scan_for_dissolves(limit: int, center_x: float, center_y: float) -> int:
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

            if entity_id in pending_dissolve_ids or not world.has(entity_id):
                dissolve_scan_cursor += 1
                continue

            if entity_id == player_id:
                dissolve_scan_cursor += 1
                continue

            idx = world.entity_to_index[entity_id]
            dx = world.pos_x[idx] - center_x
            dy = world.pos_y[idx] - center_y

            if dx * dx + dy * dy > radius_sq:
                pending_dissolves.append((entity_id, world.pos_x[idx], world.pos_y[idx]))
                pending_dissolve_ids.add(entity_id)

            dissolve_scan_cursor += 1

        return scanned

    def process_dissolves(limit: int) -> int:
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
        nonlocal input_total, input_max
        nonlocal wander_total, wander_max
        nonlocal movement_total, movement_max
        nonlocal collision_total, collision_max
        nonlocal field_total, field_max
        nonlocal instantiate_total, instantiate_max
        nonlocal extract_total, extract_max
        nonlocal enqueue_total, enqueue_max
        nonlocal hitch_16, hitch_20, hitch_33
        nonlocal dissolved_total, instantiated_total, collisions_total

        tick_start = time.perf_counter()

        input_start = time.perf_counter()
        keys = _poll_keys_pygame() if use_graphics else {
            "left": False,
            "right": False,
            "up": False,
            "down": False,
        }
        apply_player_input(ecs, keys, speed=player_speed)
        input_elapsed = time.perf_counter() - input_start
        input_total += input_elapsed
        if input_elapsed > input_max:
            input_max = input_elapsed

        if world.has(player_id):
            idx = world.entity_to_index[player_id]
            player_vel = ecs.get_component(player_id, Velocity)
            if player_vel is not None:
                world.vel_x[idx] = player_vel.value[0]
                world.vel_y[idx] = player_vel.value[1]

        wander_start = time.perf_counter()
        update_agent_wander(
            ecs,
            world,
            wander_state,
            dt,
            obstacles=obstacles,
            bounds=bounds,
        )
        wander_elapsed = time.perf_counter() - wander_start
        wander_total += wander_elapsed
        if wander_elapsed > wander_max:
            wander_max = wander_elapsed

        player_idx = world.entity_to_index[player_id]
        player_x = world.pos_x[player_idx]
        player_y = world.pos_y[player_idx]

        field_elapsed = 0.0
        instantiate_elapsed = 0.0

        if use_field:
            field_start = time.perf_counter()
            field.update(dt)
            field_elapsed = time.perf_counter() - field_start
            field_total += field_elapsed
            if field_elapsed > field_max:
                field_max = field_elapsed

            scan_for_dissolves(dissolve_scan_budget, player_x, player_y)
            dissolved_total += process_dissolves(dissolve_budget)

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
            instantiated_total += spawned

        move_start = time.perf_counter()
        update_flat_movement(world, dt)
        move_elapsed = time.perf_counter() - move_start
        movement_total += move_elapsed
        if move_elapsed > movement_max:
            movement_max = move_elapsed

        collision_start = time.perf_counter()
        c1 = resolve_world_bounds(world, radius=actor_radius, bounds=bounds)
        c2 = resolve_static_obstacles(world, radius=actor_radius, obstacles=obstacles)
        collisions_total += c1 + c2
        collision_elapsed = time.perf_counter() - collision_start
        collision_total += collision_elapsed
        if collision_elapsed > collision_max:
            collision_max = collision_elapsed

        if world.has(player_id):
            idx = world.entity_to_index[player_id]
            player_transform = ecs.get_component(player_id, Transform)
            if player_transform is not None:
                player_transform.position = (world.pos_x[idx], world.pos_y[idx])

        packet = packet_pool.acquire()
        extract_start = time.perf_counter()
        packet = extract_flat_render_packet(world, packet)
        packet["camera_x"] = player_x
        packet["camera_y"] = player_y
        packet["obstacles"] = obstacle_tuples
        packet["player_mesh"] = player_mesh
        packet["agent_mesh"] = agent_mesh
        packet["bounds"] = (bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y)
        packet["debug_player_rings"] = use_field
        packet["dissolve_radius"] = dissolve_radius
        packet["spawn_radius"] = spawn_radius
        extract_elapsed = time.perf_counter() - extract_start
        extract_total += extract_elapsed
        if extract_elapsed > extract_max:
            extract_max = extract_elapsed

        enqueue_start = time.perf_counter()
        try:
            packet_queue.put_nowait(packet)
        except queue.Full:
            packet_pool.release(packet)
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
        print("=== Playable Slice Timing Summary ===")
        print(f"ticks: {tick_count}")
        print(f"avg tick: {(tick_total / tick_count) * 1000.0:.4f} ms")
        print(f"max tick: {tick_max * 1000.0:.4f} ms")
        print(f"avg input: {(input_total / tick_count) * 1000.0:.4f} ms")
        print(f"max input: {input_max * 1000.0:.4f} ms")
        print(f"avg wander: {(wander_total / tick_count) * 1000.0:.4f} ms")
        print(f"max wander: {wander_max * 1000.0:.4f} ms")
        print(f"avg movement: {(movement_total / tick_count) * 1000.0:.4f} ms")
        print(f"max movement: {movement_max * 1000.0:.4f} ms")
        print(f"avg collision: {(collision_total / tick_count) * 1000.0:.4f} ms")
        print(f"max collision: {collision_max * 1000.0:.4f} ms")
        print(f"avg field: {(field_total / tick_count) * 1000.0:.4f} ms")
        print(f"max field: {field_max * 1000.0:.4f} ms")
        print(f"avg instantiate: {(instantiate_total / tick_count) * 1000.0:.4f} ms")
        print(f"max instantiate: {instantiate_max * 1000.0:.4f} ms")
        print(f"avg extract: {(extract_total / tick_count) * 1000.0:.4f} ms")
        print(f"max extract: {extract_max * 1000.0:.4f} ms")
        print(f"avg enqueue: {(enqueue_total / tick_count) * 1000.0:.4f} ms")
        print(f"max enqueue: {enqueue_max * 1000.0:.4f} ms")

        print("=== Playable Slice Hitch Summary ===")
        print(f">{budget_ms:.2f} ms: {hitch_16}")
        print(f">20.00 ms: {hitch_20}")
        print(f">33.33 ms: {hitch_33}")

        active_count = ecs.rows()
        field_mass = field.total_mass() if use_field else 0.0
        print("=== Playable Slice World Summary ===")
        print(f"active entities: {active_count}")
        print(f"field mass: {field_mass:.2f}")
        print(f"total dissolved: {dissolved_total}")
        print(f"total instantiated: {instantiated_total}")
        print(f"total collision adjustments: {collisions_total}")
        print(f"field enabled: {use_field}")

    return ecs.snapshot_positions()

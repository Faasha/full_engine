"""Cheap wander behavior for nearby active agents.

Pressure-aware version:
- excludes the player
- keeps timer-based headings
- uses cheap bounds and obstacle steering
- behavior is affected by kind, archetype, and pressure bias
- hostiles can enter district-driven response modes
"""

from __future__ import annotations

import random
from typing import Dict, Iterable, Tuple

from engine.components.agent_state import AgentState
from engine.components.player_tag import PlayerTag
from engine.core.ecs import ECS
from engine.core.flat_world import FlatWorld
from engine.systems.simple_collision_system import RectObstacle, WorldBounds


EntityID = Tuple[int, int]

KIND_CIVILIAN = 0
KIND_HOSTILE = 1

ARCH_ROOM = 0
ARCH_PLAZA = 1
ARCH_LANE = 2
ARCH_DENSE = 3


def _normalize(x: float, y: float) -> tuple[float, float]:
    mag_sq = x * x + y * y
    if mag_sq <= 1e-12:
        return 1.0, 0.0
    mag = mag_sq ** 0.5
    return x / mag, y / mag


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _kind_code(kind: str) -> int:
    return KIND_HOSTILE if kind == "hostile" else KIND_CIVILIAN


def _arch_code(archetype: str) -> int:
    if archetype == "plaza":
        return ARCH_PLAZA
    if archetype == "lane":
        return ARCH_LANE
    if archetype == "dense":
        return ARCH_DENSE
    return ARCH_ROOM


def _compute_bounds_push(
    x: float,
    y: float,
    bounds: WorldBounds,
    margin: float,
) -> tuple[float, float]:
    ax = 0.0
    ay = 0.0

    if x < bounds.min_x + margin:
        ax += 1.0
    elif x > bounds.max_x - margin:
        ax -= 1.0

    if y < bounds.min_y + margin:
        ay += 1.0
    elif y > bounds.max_y - margin:
        ay -= 1.0

    return ax, ay


def _near_obstacle(
    x: float,
    y: float,
    rect: RectObstacle,
    margin: float,
) -> bool:
    if x < rect.x - margin or x > rect.x + rect.w + margin:
        return False
    if y < rect.y - margin or y > rect.y + rect.h + margin:
        return False
    return True


def _obstacle_escape_dir(
    x: float,
    y: float,
    rect: RectObstacle,
) -> tuple[float, float]:
    nearest_x = _clamp(x, rect.x, rect.x + rect.w)
    nearest_y = _clamp(y, rect.y, rect.y + rect.h)

    dx = x - nearest_x
    dy = y - nearest_y

    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        cx = rect.x + rect.w * 0.5
        cy = rect.y + rect.h * 0.5
        dx = x - cx
        dy = y - cy
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            dx = 1.0
            dy = 0.0

    return _normalize(dx, dy)


def _behavior_profile_codes(
    kind_code: int,
    arch_code: int,
    pressure_bias: float,
) -> tuple[float, float, float, float, float]:
    """Return:
    (speed, jitter, avoid_margin, obstacle_push, bounds_push)
    """
    speed = 30.0
    jitter = 0.35
    avoid_margin = 36.0
    obstacle_push = 1.35
    bounds_push = 1.15

    if kind_code == KIND_CIVILIAN:
        speed = 24.0
        jitter = 0.30
        obstacle_push = 1.20
    else:
        speed = 33.0
        jitter = 0.20
        obstacle_push = 1.45

    if arch_code == ARCH_PLAZA:
        speed *= 0.85
        jitter *= 1.10
        avoid_margin = 28.0
    elif arch_code == ARCH_LANE:
        speed *= 1.02
        jitter *= 0.82
        avoid_margin = 32.0
    elif arch_code == ARCH_DENSE:
        speed *= 0.90
        jitter *= 0.72
        avoid_margin = 42.0
        obstacle_push *= 1.05
        bounds_push *= 1.05

    p = pressure_bias
    if kind_code == KIND_CIVILIAN:
        speed *= max(0.72, 1.0 - 0.10 * p)
        jitter *= min(1.35, 1.0 + 0.10 * p)
        obstacle_push *= min(1.20, 1.0 + 0.05 * p)
    else:
        speed *= min(1.35, 1.0 + 0.12 * p)
        jitter *= max(0.75, 1.0 - 0.08 * p)
        obstacle_push *= min(1.35, 1.0 + 0.10 * p)
        bounds_push *= min(1.20, 1.0 + 0.05 * p)

    return speed, jitter, avoid_margin, obstacle_push, bounds_push


def build_wander_state(world: FlatWorld, ecs: ECS) -> Dict[EntityID, dict[str, float | int | str]]:
    state: Dict[EntityID, dict[str, float | int | str]] = {}

    for entity_id in world.index_to_entity:
        agent_state = ecs.get_component(entity_id, AgentState)
        kind_code = KIND_CIVILIAN
        arch_code = ARCH_ROOM
        pressure_bias = 0.0
        response_mode = "ambient"
        response_strength = 0.0

        if agent_state is not None:
            kind_code = _kind_code(agent_state.kind)
            arch_code = _arch_code(agent_state.home_archetype)
            pressure_bias = agent_state.pressure_bias
            response_mode = agent_state.response_mode
            response_strength = agent_state.response_strength

        state[entity_id] = {
            "timer": random.uniform(0.2, 1.0),
            "dir_x": random.uniform(-1.0, 1.0),
            "dir_y": random.uniform(-1.0, 1.0),
            "kind_code": kind_code,
            "arch_code": arch_code,
            "pressure_bias": pressure_bias,
            "response_mode": response_mode,
            "response_strength": response_strength,
        }

    return state


def update_agent_wander(
    ecs: ECS,
    world: FlatWorld,
    wander_state: Dict[EntityID, dict[str, float | int | str]],
    dt: float,
    *,
    turn_interval_min: float = 0.4,
    turn_interval_max: float = 1.8,
    obstacles: Iterable[RectObstacle] = (),
    bounds: WorldBounds | None = None,
    player_pos: tuple[float, float] | None = None,
) -> None:
    player_ids: set[EntityID] = set()
    for entity_id, (_tag,) in ecs.iter_entities(PlayerTag):
        player_ids.add(entity_id)

    for entity_id in world.index_to_entity:
        if entity_id not in wander_state:
            agent_state = ecs.get_component(entity_id, AgentState)
            kind_code = KIND_CIVILIAN
            arch_code = ARCH_ROOM
            pressure_bias = 0.0
            response_mode = "ambient"
            response_strength = 0.0
            if agent_state is not None:
                kind_code = _kind_code(agent_state.kind)
                arch_code = _arch_code(agent_state.home_archetype)
                pressure_bias = agent_state.pressure_bias
                response_mode = agent_state.response_mode
                response_strength = agent_state.response_strength

            wander_state[entity_id] = {
                "timer": random.uniform(turn_interval_min, turn_interval_max),
                "dir_x": random.uniform(-1.0, 1.0),
                "dir_y": random.uniform(-1.0, 1.0),
                "kind_code": kind_code,
                "arch_code": arch_code,
                "pressure_bias": pressure_bias,
                "response_mode": response_mode,
                "response_strength": response_strength,
            }

    stale = [entity_id for entity_id in wander_state if not world.has(entity_id)]
    for entity_id in stale:
        del wander_state[entity_id]

    obstacle_list = list(obstacles)

    for entity_id in world.index_to_entity:
        if entity_id in player_ids:
            continue

        idx = world.entity_to_index[entity_id]
        state = wander_state[entity_id]
        agent_state = ecs.get_component(entity_id, AgentState)

        if agent_state is not None:
            state["kind_code"] = _kind_code(agent_state.kind)
            state["arch_code"] = _arch_code(agent_state.home_archetype)
            state["pressure_bias"] = agent_state.pressure_bias
            state["response_mode"] = agent_state.response_mode
            state["response_strength"] = agent_state.response_strength

        kind_code = int(state["kind_code"])
        arch_code = int(state["arch_code"])
        pressure_bias = float(state["pressure_bias"])
        response_mode = str(state.get("response_mode", "ambient"))
        response_strength = float(state.get("response_strength", 0.0))

        speed, jitter, avoid_margin, obstacle_push, bounds_push = _behavior_profile_codes(
            kind_code,
            arch_code,
            pressure_bias,
        )

        if kind_code == KIND_HOSTILE and response_mode != "ambient":
            speed *= 1.0 + 0.25 * response_strength

        timer = float(state["timer"]) - dt
        dx = float(state["dir_x"])
        dy = float(state["dir_y"])

        if timer <= 0.0:
            dx += random.uniform(-jitter, jitter)
            dy += random.uniform(-jitter, jitter)
            dx, dy = _normalize(dx, dy)
            timer = random.uniform(turn_interval_min, turn_interval_max)

        px = world.pos_x[idx]
        py = world.pos_y[idx]

        if bounds is not None:
            bx, by = _compute_bounds_push(px, py, bounds, avoid_margin)
            if bx != 0.0 or by != 0.0:
                dx += bx * bounds_push
                dy += by * bounds_push

        for rect in obstacle_list:
            if not _near_obstacle(px, py, rect, avoid_margin):
                continue

            ox, oy = _obstacle_escape_dir(px, py, rect)
            dx += ox * obstacle_push
            dy += oy * obstacle_push

            timer = min(timer, 0.10)
            dx += random.uniform(-0.05, 0.05)
            dy += random.uniform(-0.05, 0.05)
            break

        if player_pos is not None and kind_code == KIND_HOSTILE and response_mode != "ambient":
            tx = player_pos[0] - px
            ty = player_pos[1] - py
            hx, hy = _normalize(tx, ty)
            bias = 1.8 * response_strength
            if response_mode == "seized_response":
                bias *= 1.20
            dx += hx * bias
            dy += hy * bias
            timer = min(timer, 0.12)

        dx, dy = _normalize(dx, dy)

        state["timer"] = timer
        state["dir_x"] = dx
        state["dir_y"] = dy

        world.vel_x[idx] = dx * speed
        world.vel_y[idx] = dy * speed

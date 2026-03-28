from __future__ import annotations

from typing import Dict, List, Tuple

from engine.core.world_chunk import WorldChunk
from engine.core.world_grid import ChunkCoord, WorldGrid
from engine.missions.mission import Mission, build_spindle_missions
from engine.scenes.world_slice import _make_world_chunks
from engine.world.district_state import pressure_to_district_state
from engine.world.save_manager import load_chunk_state_into


def _state_color(state: str) -> tuple[int, int, int]:
    if state == "clear":
        return (42, 64, 54)
    if state == "warm":
        return (120, 98, 52)
    if state == "frayed":
        return (164, 92, 56)
    if state == "hunting":
        return (170, 58, 58)
    if state == "seized":
        return (96, 24, 36)
    return (60, 60, 60)


def _state_counts(chunks: Dict[ChunkCoord, WorldChunk]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for chunk in chunks.values():
        counts[chunk.district_state] = counts.get(chunk.district_state, 0) + 1
    return counts


def _world_pressure_total(chunks: Dict[ChunkCoord, WorldChunk]) -> float:
    return sum(chunk.state.pressure for chunk in chunks.values())


def _build_world(
    *,
    save_path: str,
    chunk_width: float,
    chunk_height: float,
) -> tuple[WorldGrid, Dict[ChunkCoord, WorldChunk], int, List[Mission]]:
    grid = WorldGrid(chunk_width=chunk_width, chunk_height=chunk_height)
    chunks = _make_world_chunks(grid)
    for chunk in chunks.values():
        chunk.district_state = pressure_to_district_state(chunk.state.pressure).value

    loaded_chunk_count = load_chunk_state_into(chunks, save_path)
    for chunk in chunks.values():
        chunk.district_state = pressure_to_district_state(chunk.state.pressure).value

    missions = build_spindle_missions(chunks)
    return grid, chunks, loaded_chunk_count, missions


def _chunk_rect(
    coord: ChunkCoord,
    *,
    min_x: int,
    max_y: int,
    cell: int,
    map_left: int,
    map_top: int,
):
    import pygame

    cx, cy = coord
    sx = map_left + (cx - min_x) * cell
    sy = map_top + (max_y - cy) * cell
    return pygame.Rect(sx, sy, cell, cell)


def _state_symbol(state: str) -> str:
    if state == "clear":
        return "C"
    if state == "warm":
        return "W"
    if state == "frayed":
        return "F"
    if state == "hunting":
        return "H"
    if state == "seized":
        return "S"
    return "?"


def _run_spindle_scene_text(
    chunks: Dict[ChunkCoord, WorldChunk],
    loaded_chunk_count: int,
    missions: List[Mission],
) -> Mission | None:
    counts = _state_counts(chunks)
    world_pressure = _world_pressure_total(chunks)

    coords = sorted(chunks.keys())
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    print("\nSPINDLE // PRESSURE-CONTROL CHAMBER")
    print("=" * 44)
    print(f"loaded chunks: {loaded_chunk_count}")
    print(f"world pressure total: {world_pressure:.2f}")
    print(
        "district states:",
        {
            "clear": counts.get("clear", 0),
            "warm": counts.get("warm", 0),
            "frayed": counts.get("frayed", 0),
            "hunting": counts.get("hunting", 0),
            "seized": counts.get("seized", 0),
        },
    )
    print()

    print("CITY MACRO MAP")
    print("symbol legend: C=clear W=warm F=frayed H=hunting S=seized")
    print()

    for cy in range(max_y, min_y - 1, -1):
        row_parts = []
        for cx in range(min_x, max_x + 1):
            coord = (cx, cy)
            chunk = chunks.get(coord)
            if chunk is None:
                row_parts.append("   .   ")
                continue
            sym = _state_symbol(chunk.district_state)
            row_parts.append(f"{coord!s}:{sym}")
        print(" | ".join(row_parts))
    print()

    print("AVAILABLE RUNS")
    for i, mission in enumerate(missions, start=1):
        print(
            f"{i}. {mission.label} | cargo={mission.cargo_type.value} | "
            f"source={mission.source} | target={mission.target}"
        )
    print("0. cancel")
    print()

    while True:
        raw = input("Select run number: ").strip()
        if raw == "0":
            return None
        try:
            idx = int(raw) - 1
        except ValueError:
            print("Enter a valid number.")
            continue
        if 0 <= idx < len(missions):
            mission = missions[idx]
            print(
                f"launching: {mission.label} | cargo={mission.cargo_type.value} | "
                f"{mission.source} -> {mission.target}"
            )
            return mission
        print("Selection out of range.")


def _run_spindle_scene_pygame(
    chunks: Dict[ChunkCoord, WorldChunk],
    loaded_chunk_count: int,
    missions: List[Mission],
) -> Mission | None:
    import pygame

    screen = pygame.display.set_mode((1120, 720))
    pygame.display.set_caption("SPINDLE // pressure-control chamber")
    clock = pygame.time.Clock()

    selected_index = 0

    coords = sorted(chunks.keys())
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    cell = 88
    map_left = 56
    map_top = 88

    title_font = pygame.font.SysFont(None, 40)
    section_font = pygame.font.SysFont(None, 28)
    body_font = pygame.font.SysFont(None, 24)
    small_font = pygame.font.SysFont(None, 20)

    running = True
    selected: Mission | None = None

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                selected = None

            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                    selected = None

                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected_index = (selected_index + 1) % len(missions)

                elif event.key in (pygame.K_UP, pygame.K_w):
                    selected_index = (selected_index - 1) % len(missions)

                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    selected = missions[selected_index]
                    running = False

        screen.fill((11, 14, 18))

        selected_mission = missions[selected_index]
        counts = _state_counts(chunks)
        world_pressure = _world_pressure_total(chunks)

        title = title_font.render("SPINDLE // PRESSURE-CONTROL CHAMBER", True, (236, 236, 236))
        screen.blit(title, (36, 24))

        pygame.draw.rect(screen, (18, 22, 28), (32, 72, 560, 612), border_radius=12)
        pygame.draw.rect(screen, (52, 58, 66), (32, 72, 560, 612), 2, border_radius=12)

        section = section_font.render("CITY MACRO MAP", True, (230, 230, 230))
        screen.blit(section, (52, 88))

        src_rect = _chunk_rect(
            selected_mission.source, min_x=min_x, max_y=max_y, cell=cell, map_left=map_left, map_top=map_top
        )
        tgt_rect = _chunk_rect(
            selected_mission.target, min_x=min_x, max_y=max_y, cell=cell, map_left=map_left, map_top=map_top
        )
        pygame.draw.line(screen, (120, 220, 255), src_rect.center, tgt_rect.center, 3)

        for coord, chunk in chunks.items():
            rect = _chunk_rect(coord, min_x=min_x, max_y=max_y, cell=cell, map_left=map_left, map_top=map_top)
            color = _state_color(chunk.district_state)
            pygame.draw.rect(screen, color, rect, border_radius=8)

            border = (96, 100, 108)
            if coord == selected_mission.source:
                border = (110, 220, 255)
            if coord == selected_mission.target:
                border = (255, 220, 110)

            pygame.draw.rect(screen, border, rect, 3, border_radius=8)

            coord_text = small_font.render(f"{coord[0]},{coord[1]}", True, (240, 240, 240))
            screen.blit(coord_text, (rect.x + 8, rect.y + 8))

            state_text = small_font.render(chunk.district_state.upper(), True, (235, 235, 235))
            screen.blit(state_text, (rect.x + 8, rect.y + 30))

            pressure_text = small_font.render(f"p={chunk.state.pressure:.2f}", True, (235, 235, 235))
            screen.blit(pressure_text, (rect.x + 8, rect.y + 52))

        pygame.draw.rect(screen, (18, 22, 28), (620, 72, 468, 612), border_radius=12)
        pygame.draw.rect(screen, (52, 58, 66), (620, 72, 468, 612), 2, border_radius=12)

        section = section_font.render("DISPATCH", True, (230, 230, 230))
        screen.blit(section, (640, 88))

        stats_y = 124
        stats = [
            f"loaded chunks: {loaded_chunk_count}",
            f"world pressure total: {world_pressure:.2f}",
            f"clear: {counts.get('clear', 0)}",
            f"warm: {counts.get('warm', 0)}",
            f"frayed: {counts.get('frayed', 0)}",
            f"hunting: {counts.get('hunting', 0)}",
            f"seized: {counts.get('seized', 0)}",
        ]
        for line in stats:
            surf = body_font.render(line, True, (230, 230, 230))
            screen.blit(surf, (640, stats_y))
            stats_y += 24

        mission_header = section_font.render("AVAILABLE RUNS", True, (230, 230, 230))
        screen.blit(mission_header, (640, 320))

        card_y = 356
        for idx, mission in enumerate(missions):
            rect = pygame.Rect(640, card_y, 420, 88)
            fill = (28, 34, 42)
            border = (70, 78, 88)
            if idx == selected_index:
                fill = (42, 50, 60)
                border = (255, 220, 110)

            pygame.draw.rect(screen, fill, rect, border_radius=10)
            pygame.draw.rect(screen, border, rect, 2, border_radius=10)

            line1 = body_font.render(mission.label.upper(), True, (240, 240, 240))
            line2 = small_font.render(
                f"cargo={mission.cargo_type.value}  source={mission.source}  target={mission.target}",
                True,
                (220, 220, 220),
            )
            screen.blit(line1, (rect.x + 12, rect.y + 12))
            screen.blit(line2, (rect.x + 12, rect.y + 44))
            card_y += 102

        selected_title = section_font.render("SELECTED RUN", True, (230, 230, 230))
        screen.blit(selected_title, (640, 670 - 120))

        detail_lines = [
            f"mission: {selected_mission.mission_type.value}",
            f"cargo: {selected_mission.cargo_type.value}",
            f"pickup at: {selected_mission.source}",
            f"deliver to: {selected_mission.target}",
            "controls: W/S or Up/Down to cycle, Enter to launch, Esc to cancel",
        ]
        dy = 670 - 92
        for line in detail_lines:
            surf = small_font.render(line, True, (235, 235, 235))
            screen.blit(surf, (640, dy))
            dy += 20

        pygame.display.flip()
        clock.tick(60)

    return selected


def run_spindle_scene(
    *,
    save_path: str = "runtime/world_state.json",
    chunk_width: float = 256.0,
    chunk_height: float = 256.0,
) -> Mission | None:
    grid, chunks, loaded_chunk_count, missions = _build_world(
        save_path=save_path,
        chunk_width=chunk_width,
        chunk_height=chunk_height,
    )

    try:
        import pygame  # noqa: F401
    except Exception:
        return _run_spindle_scene_text(chunks, loaded_chunk_count, missions)

    import pygame
    pygame.init()
    try:
        return _run_spindle_scene_pygame(chunks, loaded_chunk_count, missions)
    finally:
        pygame.quit()


if __name__ == "__main__":
    mission = run_spindle_scene()
    if mission is None:
        print("spindle: no mission selected")
    else:
        print(
            "spindle mission:",
            mission.label,
            mission.cargo_type.value,
            mission.source,
            mission.target,
        )

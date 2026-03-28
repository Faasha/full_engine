"""Renderer for engine packets.

World-state overlay upgrade:
- still works headless
- still supports simple entity rendering
- draws chunk grid
- draws chunk pressure tint
- outlines active chunks
- shows player-centered camera
- colors district state transitions clearly
- now includes a real in-world HUD
"""

from __future__ import annotations

import queue
import threading
from typing import Any


class Renderer:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._packet_queue: queue.Queue | None = None
        self._use_graphics = False
        self._packet_pool = None

    def start(
        self,
        packet_queue: queue.Queue,
        stop_event: threading.Event,
        *,
        use_graphics: bool = True,
        packet_pool=None,
    ) -> None:
        self._packet_queue = packet_queue
        self._stop_event = stop_event
        self._use_graphics = use_graphics
        self._packet_pool = packet_pool

        self._thread = threading.Thread(
            target=self._run,
            name="renderer",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self) -> None:
        if not self._use_graphics:
            while self._stop_event is not None and not self._stop_event.is_set():
                try:
                    packet = self._packet_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                if self._packet_pool is not None:
                    self._packet_pool.release(packet)
            return

        try:
            import pygame
        except Exception:
            while self._stop_event is not None and not self._stop_event.is_set():
                try:
                    packet = self._packet_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                if self._packet_pool is not None:
                    self._packet_pool.release(packet)
            return

        pygame.init()
        screen = pygame.display.set_mode((960, 640))
        pygame.display.set_caption("Full Engine")
        clock = pygame.time.Clock()

        latest_packet: dict[str, Any] | None = None

        try:
            while self._stop_event is not None and not self._stop_event.is_set():
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        if self._stop_event is not None:
                            self._stop_event.set()

                try:
                    while True:
                        packet = self._packet_queue.get_nowait()
                        if latest_packet is not None and self._packet_pool is not None:
                            self._packet_pool.release(latest_packet)
                        latest_packet = packet
                except queue.Empty:
                    pass

                screen.fill((10, 12, 16))

                if latest_packet is not None:
                    self._draw_packet(screen, latest_packet)

                pygame.display.flip()
                clock.tick(60)
        finally:
            if latest_packet is not None and self._packet_pool is not None:
                self._packet_pool.release(latest_packet)
            pygame.quit()

    def _draw_packet(self, screen, packet: dict[str, Any]) -> None:
        import pygame

        width = screen.get_width()
        height = screen.get_height()

        camera_x = float(packet.get("camera_x", 0.0))
        camera_y = float(packet.get("camera_y", 0.0))

        def world_to_screen(x: float, y: float) -> tuple[int, int]:
            sx = int((x - camera_x) + width * 0.5)
            sy = int(height * 0.5 - (y - camera_y))
            return sx, sy

        def rect_world_to_screen(x: float, y: float, w: float, h: float) -> pygame.Rect:
            sx0, sy_top = world_to_screen(x, y + h)
            sx1, sy_bot = world_to_screen(x + w, y)
            left = min(sx0, sx1)
            top = min(sy_top, sy_bot)
            rect_w = abs(sx1 - sx0)
            rect_h = abs(sy_bot - sy_top)
            return pygame.Rect(left, top, rect_w, rect_h)

        hud = packet.get("hud", {})
        hud_source = tuple(hud.get("source")) if hud.get("source") is not None else None
        hud_target = tuple(hud.get("target")) if hud.get("target") is not None else None
        hud_player_chunk = tuple(hud.get("player_chunk")) if hud.get("player_chunk") is not None else None

        chunk_overlay = packet.get("chunk_overlay", [])
        for item in chunk_overlay:
            rect = rect_world_to_screen(
                item["x"],
                item["y"],
                item["w"],
                item["h"],
            )

            pressure = float(item.get("pressure", 0.0))
            is_active = bool(item.get("active", False))
            archetype = str(item.get("archetype", "room"))
            district_state = str(item.get("district_state", "clear"))
            coord = tuple(item.get("coord", (None, None)))

            pressure_level = max(0.0, min(1.0, pressure / 4.0))

            if archetype == "plaza":
                base = (40, 70, 48)
            elif archetype == "lane":
                base = (52, 52, 74)
            elif archetype == "dense":
                base = (74, 48, 48)
            else:
                base = (50, 50, 50)

            tint = (
                min(255, int(base[0] + 110 * pressure_level)),
                min(255, int(base[1] + 30 * pressure_level)),
                min(255, int(base[2] + 30 * pressure_level)),
            )

            if district_state == "seized":
                tint = (100, 25, 35)
            elif district_state == "hunting":
                tint = (
                    min(255, tint[0] + 30),
                    max(0, tint[1] - 10),
                    max(0, tint[2] - 10),
                )

            pygame.draw.rect(screen, tint, rect, 0)

            border = (110, 110, 110)
            if district_state == "warm":
                border = (220, 180, 80)
            elif district_state == "frayed":
                border = (240, 140, 70)
            elif district_state == "hunting":
                border = (230, 80, 80)
            elif district_state == "seized":
                border = (180, 40, 60)

            if is_active:
                border = (240, 220, 90)

            pygame.draw.rect(screen, border, rect, 2 if is_active else 1)

            if coord == hud_source:
                pygame.draw.rect(screen, (90, 210, 255), rect.inflate(-10, -10), 2)

            if coord == hud_target:
                pygame.draw.rect(screen, (255, 215, 90), rect.inflate(-18, -18), 3)

            if coord == hud_player_chunk:
                pygame.draw.rect(screen, (255, 255, 255), rect.inflate(-30, -30), 2)

        obstacles = packet.get("obstacles", [])
        for ox, oy, ow, oh in obstacles:
            rect = rect_world_to_screen(ox, oy, ow, oh)
            pygame.draw.rect(screen, (180, 180, 180), rect)

        positions_x = packet.get("positions_x", [])
        positions_y = packet.get("positions_y", [])
        mesh_handles = packet.get("mesh_handles", [])

        player_mesh = packet.get("player_mesh", None)
        hostile_mesh = packet.get("hostile_mesh", None)

        for i in range(len(positions_x)):
            x = float(positions_x[i])
            y = float(positions_y[i])
            mesh = mesh_handles[i] if i < len(mesh_handles) else None
            sx, sy = world_to_screen(x, y)

            color = (120, 200, 240)
            radius = 5

            if mesh == player_mesh:
                color = (255, 240, 120)
                radius = 7
            elif hostile_mesh is not None and mesh == hostile_mesh:
                color = (230, 90, 90)
                radius = 5

            pygame.draw.circle(screen, color, (sx, sy), radius)

        self._draw_hud(screen, hud)

        font = pygame.font.SysFont(None, 20)
        lines = packet.get("overlay_lines", [])
        y = 10
        for line in lines[:10]:
            surf = font.render(str(line), True, (235, 235, 235))
            screen.blit(surf, (10, y))
            y += 18

    def _draw_hud(self, screen, hud: dict[str, Any]) -> None:
        import pygame

        width = screen.get_width()
        height = screen.get_height()

        title_font = pygame.font.SysFont(None, 28)
        body_font = pygame.font.SysFont(None, 22)
        small_font = pygame.font.SysFont(None, 20)

        objective = str(hud.get("objective", "--"))
        mission_label = str(hud.get("mission_label", "--"))
        mission_phase = str(hud.get("mission_phase", "--"))
        cargo = str(hud.get("cargo", "--"))
        player_chunk = hud.get("player_chunk")
        zone_archetype = str(hud.get("zone_archetype", "--"))
        zone_band = str(hud.get("zone_band", "--"))
        local_pressure = float(hud.get("local_pressure", 0.0))
        strain = float(hud.get("strain", 0.0))
        survival_state = str(hud.get("survival_state", "--"))
        overloaded = bool(hud.get("overloaded", False))
        source = hud.get("source")
        target = hud.get("target")

        panel = pygame.Surface((380, 185), pygame.SRCALPHA)
        panel.fill((8, 10, 14, 192))
        screen.blit(panel, (12, height - 197))
        pygame.draw.rect(screen, (80, 90, 110), pygame.Rect(12, height - 197, 380, 185), 1)

        title = title_font.render("RUN HUD", True, (245, 245, 245))
        screen.blit(title, (24, height - 188))

        objective_color = (255, 215, 90) if not overloaded else (255, 120, 120)
        objective_surf = body_font.render(objective, True, objective_color)
        screen.blit(objective_surf, (24, height - 160))

        lines = [
            f"Run: {mission_label}",
            f"Phase: {mission_phase}    Cargo: {cargo}",
            f"Chunk: {player_chunk}    Route: {source} -> {target}",
            f"Zone: {zone_archetype} / {zone_band}",
            f"Pressure: {local_pressure:.2f}    State: {survival_state}",
        ]

        y = height - 132
        for line in lines:
            surf = small_font.render(line, True, (228, 228, 228))
            screen.blit(surf, (24, y))
            y += 22

        bar_x = 24
        bar_y = height - 34
        bar_w = 320
        bar_h = 16

        pygame.draw.rect(screen, (40, 44, 54), pygame.Rect(bar_x, bar_y, bar_w, bar_h))
        fill_w = int(max(0.0, min(1.0, strain / 100.0)) * bar_w)

        if strain < 40.0:
            bar_color = (90, 210, 120)
        elif strain < 75.0:
            bar_color = (240, 190, 80)
        else:
            bar_color = (240, 90, 90)

        pygame.draw.rect(screen, bar_color, pygame.Rect(bar_x, bar_y, fill_w, bar_h))
        pygame.draw.rect(screen, (200, 200, 200), pygame.Rect(bar_x, bar_y, bar_w, bar_h), 1)

        strain_text = small_font.render(f"STRAIN {strain:0.1f}", True, (245, 245, 245))
        screen.blit(strain_text, (bar_x + bar_w + 10, bar_y - 1))

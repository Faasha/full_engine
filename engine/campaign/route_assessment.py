from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Tuple

from engine.core.world_chunk import WorldChunk
from engine.campaign.campaign_state import CampaignSnapshot
from engine.campaign.operation_generator import OperationOffer

ChunkCoord = Tuple[int, int]


@dataclass(slots=True)
class RouteAssessment:
    path: List[ChunkCoord]
    path_length: int
    route_pressure_total: float
    max_route_pressure: float
    route_hostile_total: float
    certified_anchors_on_route: List[ChunkCoord]
    exposed_anchors_on_route: List[ChunkCoord]
    compromised_anchors_on_route: List[ChunkCoord]
    failure_risk: float
    reasons: List[str]

    def to_dict(self) -> dict:
        return {
            "path": [list(c) for c in self.path],
            "path_length": self.path_length,
            "route_pressure_total": round(self.route_pressure_total, 6),
            "max_route_pressure": round(self.max_route_pressure, 6),
            "route_hostile_total": round(self.route_hostile_total, 6),
            "certified_anchors_on_route": [list(c) for c in self.certified_anchors_on_route],
            "exposed_anchors_on_route": [list(c) for c in self.exposed_anchors_on_route],
            "compromised_anchors_on_route": [list(c) for c in self.compromised_anchors_on_route],
            "failure_risk": round(self.failure_risk, 6),
            "reasons": self.reasons[:],
        }


def _neighbors(coord: ChunkCoord) -> list[ChunkCoord]:
    x, y = coord
    return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]


def _shortest_path(
    chunks: Dict[ChunkCoord, WorldChunk],
    start: ChunkCoord,
    target: ChunkCoord,
) -> list[ChunkCoord]:
    if start == target:
        return [start]

    frontier: deque[ChunkCoord] = deque([start])
    came_from: dict[ChunkCoord, ChunkCoord | None] = {start: None}

    while frontier:
        current = frontier.popleft()
        for nxt in _neighbors(current):
            if nxt not in chunks or nxt in came_from:
                continue
            came_from[nxt] = current
            if nxt == target:
                frontier.clear()
                break
            frontier.append(nxt)

    if target not in came_from:
        return [start, target]

    path: list[ChunkCoord] = []
    cursor: ChunkCoord | None = target
    while cursor is not None:
        path.append(cursor)
        cursor = came_from[cursor]
    path.reverse()
    return path


def _merge_paths(parts: list[list[ChunkCoord]]) -> list[ChunkCoord]:
    out: list[ChunkCoord] = []
    for part in parts:
        for coord in part:
            if out and out[-1] == coord:
                continue
            out.append(coord)
    return out


def assess_operation_route(
    chunks: Dict[ChunkCoord, WorldChunk],
    offer: OperationOffer,
    snapshot: CampaignSnapshot,
) -> RouteAssessment:
    hub = tuple(snapshot.hub_coord)

    # Real mission travel starts at hub.
    # Extraction goes hub -> hot source -> hub.
    # Normal missions go hub -> target -> hub.
    parts: list[list[ChunkCoord]] = []

    if tuple(offer.source) != hub:
        parts.append(_shortest_path(chunks, hub, tuple(offer.source)))

    parts.append(_shortest_path(chunks, tuple(offer.source), tuple(offer.target)))

    if tuple(offer.target) != hub:
        parts.append(_shortest_path(chunks, tuple(offer.target), hub))

    path = _merge_paths(parts)

    route_pressure_total = 0.0
    max_route_pressure = 0.0
    route_hostile_total = 0.0

    certified: list[ChunkCoord] = []
    exposed: list[ChunkCoord] = []
    compromised: list[ChunkCoord] = []
    reasons: list[str] = []

    seen: set[ChunkCoord] = set()

    for coord in path:
        chunk = chunks.get(coord)
        if chunk is None:
            continue

        pressure = float(chunk.state.pressure)
        hostiles = float(chunk.state.current_channels.hostiles)
        civilians = float(chunk.state.current_channels.civilians)

        route_pressure_total += pressure
        max_route_pressure = max(max_route_pressure, pressure)
        route_hostile_total += hostiles

        if coord in seen:
            continue
        seen.add(coord)

        is_anchor = (
            bool(getattr(chunk.state, "anchor_certified", False))
            and float(getattr(chunk.state, "anchor_strength", 0.0)) >= 1.0
        )

        if not is_anchor:
            continue

        certified.append(coord)

        if chunk.district_state in {"warm", "frayed"} or pressure >= 0.75:
            exposed.append(coord)

        if chunk.district_state in {"hunting", "seized"} or pressure >= 2.25 or hostiles > civilians + 2.5:
            compromised.append(coord)

    path_length = max(0, len(path) - 1)

    failure_risk = 0.0
    failure_risk += path_length * 0.05
    failure_risk += route_pressure_total * 0.08
    failure_risk += max_route_pressure * 0.15
    failure_risk += route_hostile_total * 0.015
    failure_risk += len(exposed) * 0.25
    failure_risk += len(compromised) * 0.55

    if path_length >= 5:
        reasons.append("long_route")
    if max_route_pressure >= 1.8:
        reasons.append("hot_route")
    if exposed:
        reasons.append("anchor_exposure")
    if compromised:
        reasons.append("compromised_anchor_on_route")
    if route_hostile_total >= 20.0:
        reasons.append("hostile_route")

    return RouteAssessment(
        path=path,
        path_length=path_length,
        route_pressure_total=route_pressure_total,
        max_route_pressure=max_route_pressure,
        route_hostile_total=route_hostile_total,
        certified_anchors_on_route=certified,
        exposed_anchors_on_route=exposed,
        compromised_anchors_on_route=compromised,
        failure_risk=failure_risk,
        reasons=reasons,
    )


def assess_operation_routes(
    chunks: Dict[ChunkCoord, WorldChunk],
    offers: list[OperationOffer],
    snapshot: CampaignSnapshot,
) -> dict[int, RouteAssessment]:
    return {
        i: assess_operation_route(chunks, offer, snapshot)
        for i, offer in enumerate(offers)
    }

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple

from engine.core.world_chunk import WorldChunk

ChunkCoord = Tuple[int, int]


class CampaignPhase(str, Enum):
    ONGOING = "ongoing"
    WON = "won"
    LOST = "lost"


@dataclass(slots=True, frozen=True)
class CampaignConfig:
    operation_limit: int = 12
    required_anchor_districts: int = 6
    max_seized_districts: int = 4
    fracture_limit: float = 30.0
    min_total_civilians: float = 28.0
    critical_hub_pressure: float = 2.75
    win_fracture_ratio: float = 0.70
    hub_coord: ChunkCoord = (0, 0)


@dataclass(slots=True)
class CampaignSnapshot:
    phase: CampaignPhase
    operation_index: int
    operations_remaining: int
    operation_limit: int

    required_anchor_districts: int
    anchor_districts: int
    anchor_coords: List[ChunkCoord]

    max_seized_districts: int
    seized_districts: int
    seized_coords: List[ChunkCoord]

    critical_coords: List[ChunkCoord]

    fracture_score: float
    fracture_limit: float

    total_civilians: float
    min_total_civilians: float
    total_hostiles: float

    hub_coord: ChunkCoord
    hub_state: str
    hub_pressure: float
    hub_compromised: bool

    win_ready: bool
    loss_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "operation_index": self.operation_index,
            "operations_remaining": self.operations_remaining,
            "operation_limit": self.operation_limit,
            "required_anchor_districts": self.required_anchor_districts,
            "anchor_districts": self.anchor_districts,
            "anchor_coords": [list(c) for c in self.anchor_coords],
            "max_seized_districts": self.max_seized_districts,
            "seized_districts": self.seized_districts,
            "seized_coords": [list(c) for c in self.seized_coords],
            "critical_coords": [list(c) for c in self.critical_coords],
            "fracture_score": round(self.fracture_score, 6),
            "fracture_limit": self.fracture_limit,
            "total_civilians": round(self.total_civilians, 6),
            "min_total_civilians": self.min_total_civilians,
            "total_hostiles": round(self.total_hostiles, 6),
            "hub_coord": list(self.hub_coord),
            "hub_state": self.hub_state,
            "hub_pressure": round(self.hub_pressure, 6),
            "hub_compromised": self.hub_compromised,
            "win_ready": self.win_ready,
            "loss_reason": self.loss_reason,
        }


def _is_anchor_district(
    coord: ChunkCoord,
    chunk: WorldChunk,
    *,
    hub_coord: ChunkCoord,
) -> bool:
    if coord == hub_coord:
        return False

    # Anchor certification is persistent campaign progress.
    # A stressed anchor can be contested, but it should not stop counting
    # just because it briefly becomes warm/frayed during a later operation.
    if not getattr(chunk.state, "anchor_certified", False):
        return False

    if float(getattr(chunk.state, "anchor_strength", 0.0)) < 1.0:
        return False

    if chunk.archetype not in {"lane", "room", "plaza"}:
        return False

    # True compromise removes the anchor from objective count.
    if chunk.district_state in {"hunting", "seized"}:
        return False

    pressure = float(chunk.state.pressure)
    civ = float(chunk.state.current_channels.civilians)
    host = float(chunk.state.current_channels.hostiles)

    if pressure >= 2.25:
        return False

    if host > civ + 2.5:
        return False

    return True


def _fracture_contribution(
    coord: ChunkCoord,
    chunk: WorldChunk,
    *,
    hub_coord: ChunkCoord,
) -> float:
    pressure = float(chunk.state.pressure)
    civ = float(chunk.state.current_channels.civilians)
    host = float(chunk.state.current_channels.hostiles)

    # Fracture should measure irreversible strain, not any visible stress.
    # Calm or merely warm districts should not dominate the whole-city score.
    if chunk.district_state == "clear" and pressure < 1.00:
        return 0.0
    if chunk.district_state == "warm" and pressure < 1.10 and host <= civ:
        return 0.0

    state_bonus = {
        "clear": 0.0,
        "warm": 0.75,
        "frayed": 1.75,
        "hunting": 3.50,
        "seized": 5.50,
    }.get(chunk.district_state, 0.0)

    # Only count pressure above the operational comfort floor.
    excess_pressure = max(0.0, pressure - 1.00)

    archetype_mult = {
        "plaza": 0.80,
        "room": 0.90,
        "lane": 1.00,
        "dense": 1.15,
    }.get(chunk.archetype, 1.0)

    # Hostiles only matter here when they exceed the civilian body present.
    hostile_edge = max(0.0, host - civ) * 0.18

    hub_bonus = 0.0
    if coord == hub_coord:
        if chunk.district_state in {"frayed", "hunting", "seized"}:
            hub_bonus += 2.0
        elif pressure >= 1.25:
            hub_bonus += 0.75

    return excess_pressure * archetype_mult + state_bonus + hostile_edge + hub_bonus

def build_campaign_snapshot(
    chunks: Dict[ChunkCoord, WorldChunk],
    *,
    operation_index: int,
    config: CampaignConfig | None = None,
) -> CampaignSnapshot:
    cfg = config or CampaignConfig()

    anchor_coords = sorted(
        coord
        for coord, chunk in chunks.items()
        if _is_anchor_district(coord, chunk, hub_coord=cfg.hub_coord)
    )

    seized_coords = sorted(
        coord
        for coord, chunk in chunks.items()
        if chunk.district_state == "seized"
    )

    critical_coords = sorted(
        coord
        for coord, chunk in chunks.items()
        if chunk.district_state in {"hunting", "seized"}
    )

    total_civilians = sum(float(chunk.state.current_channels.civilians) for chunk in chunks.values())
    total_hostiles = sum(float(chunk.state.current_channels.hostiles) for chunk in chunks.values())

    fracture_score = sum(
        _fracture_contribution(coord, chunk, hub_coord=cfg.hub_coord)
        for coord, chunk in chunks.items()
    )

    hub = chunks.get(cfg.hub_coord)
    if hub is None:
        hub_state = "missing"
        hub_pressure = 999.0
        hub_compromised = True
    else:
        hub_state = hub.district_state
        hub_pressure = float(hub.state.pressure)
        hub_compromised = (
            hub_state in {"hunting", "seized"}
            or hub_pressure >= cfg.critical_hub_pressure
        )

    win_ready = (
        len(anchor_coords) >= cfg.required_anchor_districts
        and len(seized_coords) <= cfg.max_seized_districts
        and fracture_score <= cfg.fracture_limit * cfg.win_fracture_ratio
        and total_civilians >= cfg.min_total_civilians
        and not hub_compromised
    )

    phase = CampaignPhase.ONGOING
    loss_reason = ""

    if hub_compromised:
        phase = CampaignPhase.LOST
        loss_reason = "hub_compromised"
    elif len(seized_coords) > cfg.max_seized_districts:
        phase = CampaignPhase.LOST
        loss_reason = "too_many_seized_districts"
    elif total_civilians < cfg.min_total_civilians:
        phase = CampaignPhase.LOST
        loss_reason = "civilian_collapse"
    elif fracture_score > cfg.fracture_limit:
        phase = CampaignPhase.LOST
        loss_reason = "system_fracture"
    elif operation_index >= cfg.operation_limit:
        if win_ready:
            phase = CampaignPhase.WON
        else:
            phase = CampaignPhase.LOST
            loss_reason = "deadline_expired"

    return CampaignSnapshot(
        phase=phase,
        operation_index=operation_index,
        operations_remaining=max(0, cfg.operation_limit - operation_index),
        operation_limit=cfg.operation_limit,
        required_anchor_districts=cfg.required_anchor_districts,
        anchor_districts=len(anchor_coords),
        anchor_coords=anchor_coords,
        max_seized_districts=cfg.max_seized_districts,
        seized_districts=len(seized_coords),
        seized_coords=seized_coords,
        critical_coords=critical_coords,
        fracture_score=fracture_score,
        fracture_limit=cfg.fracture_limit,
        total_civilians=total_civilians,
        min_total_civilians=cfg.min_total_civilians,
        total_hostiles=total_hostiles,
        hub_coord=cfg.hub_coord,
        hub_state=hub_state,
        hub_pressure=hub_pressure,
        hub_compromised=hub_compromised,
        win_ready=win_ready,
        loss_reason=loss_reason,
    )


def objective_status_lines(snapshot: CampaignSnapshot) -> list[str]:
    lines = [
        (
            f"campaign={snapshot.phase.value} "
            f"op={snapshot.operation_index}/{snapshot.operation_limit} "
            f"ops_left={snapshot.operations_remaining}"
        ),
        (
            f"anchors={snapshot.anchor_districts}/{snapshot.required_anchor_districts} "
            f"seized={snapshot.seized_districts}/{snapshot.max_seized_districts}"
        ),
        (
            f"fracture={snapshot.fracture_score:.2f}/{snapshot.fracture_limit:.2f} "
            f"civilians={snapshot.total_civilians:.2f}/{snapshot.min_total_civilians:.2f}"
        ),
        (
            f"hub={snapshot.hub_state} "
            f"hub_pressure={snapshot.hub_pressure:.2f} "
            f"hub_compromised={snapshot.hub_compromised}"
        ),
        (
            f"win_ready={snapshot.win_ready} "
            f"critical={len(snapshot.critical_coords)}"
        ),
    ]
    if snapshot.loss_reason:
        lines.append(f"loss_reason={snapshot.loss_reason}")
    return lines

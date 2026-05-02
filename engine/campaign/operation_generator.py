from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from engine.core.world_chunk import WorldChunk
from engine.missions.mission import CargoType, MissionType
from engine.campaign.campaign_state import CampaignSnapshot

ChunkCoord = Tuple[int, int]


@dataclass(slots=True)
class OperationOffer:
    mission_type: MissionType
    cargo_type: CargoType
    label: str
    source: ChunkCoord
    target: ChunkCoord
    priority: float
    rationale: List[str]
    target_role: str
    target_state: str
    target_pressure: float

    def to_dict(self) -> dict:
        return {
            "mission_type": self.mission_type.value,
            "cargo_type": self.cargo_type.value,
            "label": self.label,
            "source": list(self.source),
            "target": list(self.target),
            "priority": round(self.priority, 6),
            "rationale": self.rationale[:],
            "target_role": self.target_role,
            "target_state": self.target_state,
            "target_pressure": round(self.target_pressure, 6),
        }


def _role_weight(role: str) -> float:
    return {
        "hub": 10.0,
        "relay": 8.0,
        "civic": 7.0,
        "shelter": 7.0,
        "corridor": 6.0,
        "industrial": 5.0,
        "quarantine": 5.0,
        "nest": 6.5,
        "wild": 3.0,
    }.get(role, 3.0)


def _state_weight(state: str) -> float:
    return {
        "clear": 0.0,
        "warm": 1.5,
        "frayed": 3.5,
        "hunting": 6.0,
        "seized": 9.0,
    }.get(state, 0.0)


def _pick_hub(chunks: Dict[ChunkCoord, WorldChunk]) -> ChunkCoord:
    return (0, 0) if (0, 0) in chunks else next(iter(chunks.keys()))


def _candidate_chunks(
    chunks: Dict[ChunkCoord, WorldChunk],
    *,
    exclude_hub: bool = True,
) -> list[tuple[ChunkCoord, WorldChunk]]:
    hub = _pick_hub(chunks)
    out = []
    for coord, chunk in chunks.items():
        if exclude_hub and coord == hub:
            continue
        out.append((coord, chunk))
    return out


def _priority_stabilization(coord: ChunkCoord, chunk: WorldChunk, snapshot: CampaignSnapshot) -> tuple[float, list[str]]:
    reasons: list[str] = []
    p = float(chunk.state.pressure)
    civ = float(chunk.state.current_channels.civilians)
    host = float(chunk.state.current_channels.hostiles)

    score = 0.0
    if chunk.district_role in {"civic", "shelter", "corridor", "relay"}:
        score += 4.0
        reasons.append(f"role={chunk.district_role}")

    if chunk.district_state in {"warm", "frayed"}:
        score += 3.0
        reasons.append(f"state={chunk.district_state}")

    if getattr(chunk.state, "anchor_certified", False):
        return -999.0, ["already_anchor"]

    if p <= 1.6:
        score += 2.5
        reasons.append("pressure_stabilizable")
    elif p <= 2.4:
        score += 1.0
        reasons.append("pressure_borderline")
    else:
        score -= 3.0
        reasons.append("pressure_too_hot")

    if civ >= host:
        score += 1.0
        reasons.append("civilian_viable")
    else:
        score -= 2.0
        reasons.append("hostile_heavier")

    # If campaign still lacks anchors, heavily bias anchor creation.
    anchors_missing = max(0, snapshot.required_anchor_districts - snapshot.anchor_districts)
    score += anchors_missing * 0.75

    return score, reasons


def _priority_relay(coord: ChunkCoord, chunk: WorldChunk) -> tuple[float, list[str]]:
    reasons: list[str] = []
    p = float(chunk.state.pressure)

    score = 0.0
    if chunk.district_role in {"relay", "corridor"}:
        score += 5.0
        reasons.append(f"role={chunk.district_role}")

    score += _state_weight(chunk.district_state) * 0.8
    if chunk.district_state != "clear":
        reasons.append(f"state={chunk.district_state}")

    score += min(3.0, p * 1.2)
    reasons.append(f"pressure={p:.2f}")

    return score, reasons


def _priority_relief(coord: ChunkCoord, chunk: WorldChunk) -> tuple[float, list[str]]:
    reasons: list[str] = []
    p = float(chunk.state.pressure)
    civ = float(chunk.state.current_channels.civilians)
    host = float(chunk.state.current_channels.hostiles)

    score = 0.0
    if chunk.district_role in {"shelter", "civic"}:
        score += 5.0
        reasons.append(f"role={chunk.district_role}")

    if civ > 0.0:
        score += min(4.0, civ * 0.35)
        reasons.append("civilians_present")

    score += min(3.0, p * 1.1)
    if host > civ:
        score += 1.0
        reasons.append("population_under_pressure")

    return score, reasons


def _priority_damper(coord: ChunkCoord, chunk: WorldChunk) -> tuple[float, list[str]]:
    reasons: list[str] = []
    p = float(chunk.state.pressure)
    host = float(chunk.state.current_channels.hostiles)

    # Damper is a threat-suppression operation.
    # It should not be offered against civic/shelter/relay/corridor anchors.
    if chunk.district_role not in {"industrial", "nest", "quarantine"}:
        return -999.0, ["not_damper_role"]

    score = 4.5
    reasons.append(f"role={chunk.district_role}")

    score += _state_weight(chunk.district_state)
    if chunk.district_state != "clear":
        reasons.append(f"state={chunk.district_state}")

    score += min(5.0, p * 1.4)
    score += min(4.0, host * 0.35)

    if p >= 1.5:
        score += 1.5
        reasons.append("pressure_source")

    if host >= 5.0:
        score += 1.5
        reasons.append("hostile_source")

    reasons.append(f"pressure={p:.2f}")
    reasons.append(f"hostiles={host:.2f}")

    return score, reasons



def _priority_extraction(coord: ChunkCoord, chunk: WorldChunk) -> tuple[float, list[str]]:
    reasons: list[str] = []
    p = float(chunk.state.pressure)
    civ = float(chunk.state.current_channels.civilians)

    score = 0.0
    if chunk.district_role in {"quarantine", "nest", "industrial"}:
        score += 3.0
        reasons.append(f"role={chunk.district_role}")

    if chunk.district_state in {"hunting", "seized", "frayed"}:
        score += 4.0
        reasons.append(f"state={chunk.district_state}")

    if civ > 0.0:
        score += min(4.0, civ * 0.30)
        reasons.append("civilians_to_save")
    else:
        score -= 3.0
        reasons.append("no_civilians")

    score += min(4.0, p * 1.0)
    reasons.append(f"pressure={p:.2f}")

    return score, reasons


def _best_offer(
    chunks: Dict[ChunkCoord, WorldChunk],
    *,
    mission_type: MissionType,
    cargo_type: CargoType,
    label: str,
    snapshot: CampaignSnapshot,
) -> OperationOffer | None:
    hub = snapshot.hub_coord
    candidates = _candidate_chunks(chunks)

    best: OperationOffer | None = None

    for coord, chunk in candidates:
        if mission_type == MissionType.STABILIZATION_RUN:
            priority, rationale = _priority_stabilization(coord, chunk, snapshot)
            source, target = hub, coord
        elif mission_type == MissionType.RELAY_RUN:
            priority, rationale = _priority_relay(coord, chunk)
            source, target = hub, coord
        elif mission_type == MissionType.RELIEF_RUN:
            priority, rationale = _priority_relief(coord, chunk)
            source, target = hub, coord
        elif mission_type == MissionType.RECOVERY_RUN:
            priority, rationale = _priority_damper(coord, chunk)
            source, target = hub, coord
        elif mission_type == MissionType.EXTRACTION_RUN:
            priority, rationale = _priority_extraction(coord, chunk)
            source, target = coord, hub
        else:
            continue

        if priority < 0.0:
            continue

        priority += _role_weight(chunk.district_role) * 0.15

        offer = OperationOffer(
            mission_type=mission_type,
            cargo_type=cargo_type,
            label=label,
            source=source,
            target=target,
            priority=priority,
            rationale=rationale,
            target_role=chunk.district_role,
            target_state=chunk.district_state,
            target_pressure=float(chunk.state.pressure),
        )

        if best is None or offer.priority > best.priority:
            best = offer

    return best


def generate_operation_offers(
    chunks: Dict[ChunkCoord, WorldChunk],
    snapshot: CampaignSnapshot,
) -> list[OperationOffer]:
    offers: list[OperationOffer] = []

    offer_specs = [
        (
            MissionType.STABILIZATION_RUN,
            CargoType.STABILITY_LATTICE,
            "stabilization run // certify anchor",
        ),
        (
            MissionType.RELAY_RUN,
            CargoType.RELAY_HEART,
            "relay run // reopen route",
        ),
        (
            MissionType.RELIEF_RUN,
            CargoType.MED_DISPERSAL,
            "relief run // protect civilians",
        ),
        (
            MissionType.RECOVERY_RUN,
            CargoType.DAMPER_UNIT,
            "damper run // cool hot district",
        ),
        (
            MissionType.EXTRACTION_RUN,
            CargoType.EVAC_CIVILIAN,
            "extraction run // pull value out",
        ),
    ]

    for mission_type, cargo_type, label in offer_specs:
        best = _best_offer(
            chunks,
            mission_type=mission_type,
            cargo_type=cargo_type,
            label=label,
            snapshot=snapshot,
        )
        if best is not None:
            offers.append(best)

    offers.sort(key=lambda o: o.priority, reverse=True)
    return offers

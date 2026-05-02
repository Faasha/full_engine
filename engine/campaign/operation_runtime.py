from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from engine.campaign.campaign_policy import choose_operation_index
from engine.campaign.operation_generator import OperationOffer
from engine.campaign.route_assessment import RouteAssessment
from engine.core.world_chunk import WorldChunk
from engine.missions.mission import CargoType, Mission, MissionType

ChunkCoord = Tuple[int, int]


@dataclass(slots=True)
class OperationSelection:
    operation_index: int
    offer: OperationOffer
    mission: Mission
    policy_reason: str
    route_assessment: RouteAssessment | None = None

    def to_dict(self) -> dict:
        return {
            "operation_index": self.operation_index,
            "policy_reason": self.policy_reason,
            "route_assessment": (
                self.route_assessment.to_dict()
                if self.route_assessment is not None
                else None
            ),
            "offer": self.offer.to_dict(),
            "mission": {
                "mission_type": self.mission.mission_type.value,
                "cargo_type": self.mission.cargo_type.value,
                "label": self.mission.label,
                "source": list(self.mission.source),
                "target": list(self.mission.target),
                "hold_seconds": self.mission.hold_seconds,
            },
        }


def hold_seconds_for_mission_type(mission_type: MissionType) -> float:
    if mission_type == MissionType.STABILIZATION_RUN:
        return 8.0
    return 0.0


def offer_to_mission(offer: OperationOffer) -> Mission:
    return Mission(
        mission_type=offer.mission_type,
        cargo_type=offer.cargo_type,
        source=offer.source,
        target=offer.target,
        label=offer.label,
        hold_seconds=hold_seconds_for_mission_type(offer.mission_type),
    )


def select_primary_operation(
    offers: List[OperationOffer],
    *,
    operation_index: int,
    snapshot,
    chunks: Dict[ChunkCoord, WorldChunk] | None = None,
) -> OperationSelection:
    if not offers:
        raise ValueError("no operation offers available")

    decision = choose_operation_index(offers, snapshot, chunks=chunks)
    best = offers[decision.selected_index]
    mission = offer_to_mission(best)

    return OperationSelection(
        operation_index=operation_index,
        offer=best,
        mission=mission,
        policy_reason=decision.reason,
        route_assessment=decision.route_assessment,
    )

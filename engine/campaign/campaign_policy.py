from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from engine.campaign.campaign_state import CampaignSnapshot
from engine.campaign.operation_generator import OperationOffer
from engine.campaign.route_assessment import RouteAssessment, assess_operation_routes
from engine.core.world_chunk import WorldChunk
from engine.missions.mission import MissionType

ChunkCoord = tuple[int, int]


@dataclass(slots=True)
class PolicyDecision:
    selected_index: int
    reason: str
    route_assessment: RouteAssessment | None = None


def _find_first(offers: List[OperationOffer], mission_type: MissionType) -> tuple[int, OperationOffer] | None:
    for i, offer in enumerate(offers):
        if offer.mission_type == mission_type:
            return i, offer
    return None


def _find_relay_for_anchor(
    offers: List[OperationOffer],
    anchor_coords: list[ChunkCoord],
) -> tuple[int, OperationOffer] | None:
    anchor_set = set(anchor_coords)
    for i, offer in enumerate(offers):
        if offer.mission_type != MissionType.RELAY_RUN:
            continue
        if tuple(offer.target) in anchor_set:
            return i, offer
    return None


def choose_operation_index(
    offers: List[OperationOffer],
    snapshot: CampaignSnapshot,
    *,
    chunks: Dict[ChunkCoord, WorldChunk] | None = None,
) -> PolicyDecision:
    if not offers:
        raise ValueError("no offers available")

    route_assessments: dict[int, RouteAssessment] = {}
    if chunks is not None:
        route_assessments = assess_operation_routes(chunks, offers, snapshot)

    def assessment_for(index: int) -> RouteAssessment | None:
        return route_assessments.get(index)

    def finish(index: int, reason: str) -> PolicyDecision:
        return PolicyDecision(index, reason, assessment_for(index))

    anchors_missing = max(0, snapshot.required_anchor_districts - snapshot.anchor_districts)
    anchor_coords = set(tuple(c) for c in snapshot.anchor_coords)

    stab = _find_first(offers, MissionType.STABILIZATION_RUN)
    damper = _find_first(offers, MissionType.RECOVERY_RUN)
    extract = _find_first(offers, MissionType.EXTRACTION_RUN)
    relay = _find_first(offers, MissionType.RELAY_RUN)
    relief = _find_first(offers, MissionType.RELIEF_RUN)

    # 1. True emergency cooling first.
    if damper is not None:
        i, offer = damper
        route = assessment_for(i)
        route_too_dangerous = route is not None and route.failure_risk >= 1.35
        if (offer.target_pressure >= 2.4 or offer.target_state in {"hunting", "seized"}) and not route_too_dangerous:
            return finish(i, "emergency_cooling")

    # 2. Deadline pressure: if there are barely enough turns left to build required anchors,
    # stop spending turns on route/relief/cooling unless there is a true emergency.
    if anchors_missing > 0 and stab is not None:
        i, offer = stab
        route = assessment_for(i)
        target_is_new_anchor = tuple(offer.target) not in anchor_coords
        # Deadline anchor turns may accept moderate route risk.
        # They are blocked only by genuinely compromised anchor routes.
        route_ok = (
            route is None
            or (
                route.failure_risk < 1.50
                and not route.compromised_anchors_on_route
            )
        )

        must_build_now = anchors_missing >= max(1, snapshot.operations_remaining - 2)

        if (
            must_build_now
            and target_is_new_anchor
            and route_ok
            and offer.target_pressure <= 1.8
            and offer.target_state not in {"hunting", "seized"}
        ):
            return finish(i, "deadline_anchor_pressure")

    # 3. If damper route exposes an anchor badly, repair that anchor first.
    if damper is not None:
        i, offer = damper
        route = assessment_for(i)
        if route is not None and route.exposed_anchors_on_route and route.failure_risk >= 0.85:
            relay_for_anchor = _find_relay_for_anchor(offers, route.exposed_anchors_on_route)
            if relay_for_anchor is not None:
                ri, _ = relay_for_anchor
                return finish(ri, "route_precondition")

    # 4. Normal anchor building: only stressed or tactically warm districts.
    if anchors_missing > 0 and stab is not None:
        i, offer = stab
        target_is_new_anchor = tuple(offer.target) not in anchor_coords
        anchor_candidate = (
            offer.target_state in {"warm", "frayed"}
            or offer.target_pressure >= 0.75
        )
        route = assessment_for(i)
        route_ok = route is None or route.failure_risk < 1.2
        if target_is_new_anchor and anchor_candidate and offer.target_pressure <= 1.8 and route_ok:
            return finish(i, "anchor_deficit")

    # 5. Severe civilian rescue only.
    if extract is not None:
        i, offer = extract
        route = assessment_for(i)
        route_ok = route is None or route.failure_risk < 1.2
        severe_extraction = (
            offer.target_state in {"hunting", "seized"}
            or offer.target_pressure >= 2.35
        )
        if severe_extraction and route_ok:
            return finish(i, "civilian_extraction_window")

    # 6. Fracture management.
    if damper is not None:
        i, offer = damper
        route = assessment_for(i)
        fracture_hot = snapshot.fracture_score >= snapshot.fracture_limit * 0.33
        viable_cooling = (
            offer.target_state in {"warm", "frayed", "hunting", "seized"}
            or offer.target_pressure >= 0.75
            or offer.priority >= 9.0
        )
        route_ok = route is None or route.failure_risk < 0.95
        if fracture_hot and viable_cooling and route_ok:
            return finish(i, "fracture_management")

    # 7. Route repair only when serious and not stealing a deadline anchor turn.
    if relay is not None:
        i, offer = relay
        serious_route_problem = (
            offer.target_state in {"hunting", "seized"}
            or offer.target_pressure >= 1.65
        )
        if offer.target_role in {"relay", "corridor"} and serious_route_problem:
            return finish(i, "route_integrity")

    # 8. Civilian protection.
    if relief is not None:
        i, offer = relief
        if offer.target_role in {"shelter", "civic"} and offer.target_pressure >= 1.2:
            return finish(i, "civilian_protection")

    return finish(0, "highest_priority_fallback")

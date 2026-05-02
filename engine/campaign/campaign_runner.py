from __future__ import annotations

import argparse
import contextlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.core.world_grid import WorldGrid
from engine.scenes.world_slice import _make_world_chunks, run_world_slice
from engine.world.save_manager import save_chunk_state, load_chunk_state_into
from engine.campaign.campaign_bootstrap import apply_opening_crisis
from engine.campaign.campaign_state import (
    CampaignSnapshot,
    build_campaign_snapshot,
    objective_status_lines,
)
from engine.campaign.operation_generator import OperationOffer, generate_operation_offers
from engine.campaign.operation_runtime import OperationSelection, select_primary_operation


@dataclass(slots=True)
class CampaignDayResult:
    operation_index: int
    state_in: str
    state_out: str
    mission_report_path: str
    bootstrapped: bool
    snapshot_before: CampaignSnapshot
    offers_before: list[OperationOffer]
    selection: OperationSelection
    snapshot_after: CampaignSnapshot
    offers_after: list[OperationOffer]
    objective_status_after: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_index": self.operation_index,
            "state_in": self.state_in,
            "state_out": self.state_out,
            "mission_report_path": self.mission_report_path,
            "bootstrapped": self.bootstrapped,
            "snapshot_before": self.snapshot_before.to_dict(),
            "offers_before": [offer.to_dict() for offer in self.offers_before],
            "selection": self.selection.to_dict(),
            "snapshot_after": self.snapshot_after.to_dict(),
            "offers_after": [offer.to_dict() for offer in self.offers_after],
            "objective_status_after": self.objective_status_after[:],
        }


def _load_chunks_from_state(
    state_path: Path,
    *,
    bootstrap_if_missing: bool,
) -> tuple[dict, bool]:
    grid = WorldGrid(chunk_width=256.0, chunk_height=256.0)
    chunks = _make_world_chunks(grid)

    bootstrapped = False

    if state_path.exists():
        loaded = load_chunk_state_into(chunks, state_path)
        if loaded <= 0:
            raise RuntimeError(f"state file existed but loaded no chunks: {state_path}")
    else:
        if not bootstrap_if_missing:
            raise FileNotFoundError(f"missing campaign state: {state_path}")
        apply_opening_crisis(chunks)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        save_chunk_state(chunks, state_path)
        bootstrapped = True

    return chunks, bootstrapped


def run_campaign_day(
    *,
    operation_index: int,
    state_in: str | Path,
    state_out: str | Path,
    report_path: str | Path,
    bootstrap_if_missing: bool = False,
    duration: float = 20.0,
    fps: float = 60.0,
    debug_level: str = "full",
    quiet_world: bool = False,
) -> CampaignDayResult:
    state_in_path = Path(state_in)
    state_out_path = Path(state_out)
    report_path = Path(report_path)
    mission_report_path = report_path.with_name(report_path.stem + "_mission.json")

    chunks, bootstrapped = _load_chunks_from_state(
        state_in_path,
        bootstrap_if_missing=bootstrap_if_missing,
    )

    snapshot_before = build_campaign_snapshot(chunks, operation_index=operation_index)
    offers_before = generate_operation_offers(chunks, snapshot_before)
    selection = select_primary_operation(
        offers_before,
        operation_index=operation_index,
        snapshot=snapshot_before,
        chunks=chunks,
    )

    def run_selected_mission() -> None:
        run_world_slice(
            duration=duration,
            fps=fps,
            use_graphics=False,
            use_autopilot=True,
            debug_level=debug_level,
            load_path=str(state_in_path),
            save_path=str(state_out_path),
            report_path=str(mission_report_path),
            live_state_path=None,
            mission=selection.mission,
        )

    if quiet_world:
        with contextlib.redirect_stdout(io.StringIO()):
            run_selected_mission()
    else:
        run_selected_mission()

    grid = WorldGrid(chunk_width=256.0, chunk_height=256.0)
    chunks_after = _make_world_chunks(grid)
    loaded_after = load_chunk_state_into(chunks_after, state_out_path)
    if loaded_after <= 0:
        raise RuntimeError(f"mission produced no loadable next-state chunks: {state_out_path}")

    snapshot_after = build_campaign_snapshot(
        chunks_after,
        operation_index=operation_index + 1,
    )
    offers_after = generate_operation_offers(chunks_after, snapshot_after)
    status_after = objective_status_lines(snapshot_after)

    result = CampaignDayResult(
        operation_index=operation_index,
        state_in=str(state_in_path),
        state_out=str(state_out_path),
        mission_report_path=str(mission_report_path),
        bootstrapped=bootstrapped,
        snapshot_before=snapshot_before,
        offers_before=offers_before,
        selection=selection,
        snapshot_after=snapshot_after,
        offers_after=offers_after,
        objective_status_after=status_after,
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    return result


def print_campaign_day_result(result: CampaignDayResult, *, compact: bool = False) -> None:
    if compact:
        before = result.snapshot_before.to_dict()
        after = result.snapshot_after.to_dict()
        sel = result.selection.to_dict()
        mission = sel["mission"]

        print("=== CAMPAIGN DAY COMPACT ===")
        print(
            f"op={result.operation_index} "
            f"selected={mission['mission_type']} "
            f"reason={sel['policy_reason']} "
            f"target={mission['target']}"
        )
        print(
            f"before: anchors={before['anchor_districts']}/{before['required_anchor_districts']} "
            f"fracture={before['fracture_score']}/{before['fracture_limit']} "
            f"hub={before['hub_state']}:{before['hub_pressure']}"
        )
        print(
            f"after:  anchors={after['anchor_districts']}/{after['required_anchor_districts']} "
            f"fracture={after['fracture_score']}/{after['fracture_limit']} "
            f"hub={after['hub_state']}:{after['hub_pressure']} "
            f"critical={len(after['critical_coords'])} "
            f"phase={after['phase']}"
        )
        return

    print("=== CAMPAIGN DAY RUN ===")
    print(f"operation_index: {result.operation_index}")
    print(f"state_in: {result.state_in}")
    print(f"state_out: {result.state_out}")
    print(f"bootstrapped: {result.bootstrapped}")

    print("=== SNAPSHOT BEFORE ===")
    print(json.dumps(result.snapshot_before.to_dict(), indent=2))

    print("=== OFFERS BEFORE ===")
    for offer in result.offers_before:
        print(json.dumps(offer.to_dict(), indent=2))

    print("=== SELECTED OPERATION ===")
    print(json.dumps(result.selection.to_dict(), indent=2))

    print("=== SNAPSHOT AFTER ===")
    print(json.dumps(result.snapshot_after.to_dict(), indent=2))

    print("=== OFFERS AFTER ===")
    for offer in result.offers_after:
        print(json.dumps(offer.to_dict(), indent=2))

    print("=== OBJECTIVE STATUS AFTER ===")
    for line in result.objective_status_after:
        print(line)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one campaign operation day.")
    parser.add_argument("--operation-index", type=int, required=True)
    parser.add_argument("--state-in", required=True)
    parser.add_argument("--state-out", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--bootstrap-if-missing", action="store_true")
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--fps", type=float, default=60.0)
    parser.add_argument("--debug-level", default="full", choices=["off", "basic", "full"])
    parser.add_argument("--quiet-world", action="store_true")
    parser.add_argument("--compact", action="store_true")

    args = parser.parse_args()

    result = run_campaign_day(
        operation_index=args.operation_index,
        state_in=args.state_in,
        state_out=args.state_out,
        report_path=args.report,
        bootstrap_if_missing=args.bootstrap_if_missing,
        duration=args.duration,
        fps=args.fps,
        debug_level=args.debug_level,
        quiet_world=args.quiet_world,
    )
    print_campaign_day_result(result, compact=args.compact)


if __name__ == "__main__":
    main()

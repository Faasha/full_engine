from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

from engine.core.world_chunk import WorldChunk

ChunkCoord = Tuple[int, int]


SAVE_VERSION = 1


def _coord_key(coord: ChunkCoord) -> str:
    return f"{coord[0]},{coord[1]}"


def _parse_coord_key(key: str) -> ChunkCoord:
    xs, ys = key.split(",", 1)
    return int(xs), int(ys)


def save_chunk_state(
    chunks: Dict[ChunkCoord, WorldChunk],
    path: str | Path,
) -> None:
    """Persist only abstract chunk state, never live ECS entities."""
    out = {
        "version": SAVE_VERSION,
        "chunks": {},
    }

    for coord, chunk in chunks.items():
        out["chunks"][_coord_key(coord)] = {
            "pressure": float(chunk.state.pressure),
            "district_state": str(chunk.district_state),
            "activation_count": int(chunk.state.activation_count),
            "last_active_tick": int(chunk.state.last_active_tick),
            "current_civilians": float(chunk.state.current_channels.civilians),
            "current_hostiles": float(chunk.state.current_channels.hostiles),
        }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")


def load_chunk_state_into(
    chunks: Dict[ChunkCoord, WorldChunk],
    path: str | Path,
) -> int:
    """Load saved abstract state into an existing chunk layout.

    Returns number of chunks restored.
    """
    path = Path(path)
    if not path.exists():
        return 0

    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != SAVE_VERSION:
        return 0

    restored = 0
    raw_chunks = data.get("chunks", {})
    for key, payload in raw_chunks.items():
        try:
            coord = _parse_coord_key(key)
        except Exception:
            continue

        chunk = chunks.get(coord)
        if chunk is None:
            continue

        chunk.state.pressure = max(0.0, float(payload.get("pressure", 0.0)))
        chunk.district_state = str(payload.get("district_state", "clear"))
        chunk.state.activation_count = max(0, int(payload.get("activation_count", 0)))
        chunk.state.last_active_tick = int(payload.get("last_active_tick", -1))
        chunk.state.current_channels.civilians = max(
            0.0, float(payload.get("current_civilians", 0.0))
        )
        chunk.state.current_channels.hostiles = max(
            0.0, float(payload.get("current_hostiles", 0.0))
        )
        restored += 1

    return restored

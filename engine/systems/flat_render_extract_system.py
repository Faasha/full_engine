"""Flat-array render extraction system.

This version avoids per-entity tuple construction by writing into
parallel packet arrays instead of appending `(mesh, material, x, y)`
tuples for every entity every frame.

The packet format is a dict with these keys:
- "mesh": list[int]
- "material": list[int]
- "x": list[float]
- "y": list[float]
- "count": int

This keeps extraction closer to the engine's flat-data doctrine and
reduces Python object churn on large frames.
"""

from __future__ import annotations

from engine.core.flat_world import FlatWorld


def _ensure_capacity(arr: list, size: int, fill_value) -> None:
    """Grow a list to at least `size` elements."""
    missing = size - len(arr)
    if missing > 0:
        arr.extend([fill_value] * missing)


def acquire_packet_buffer(packet: dict | None = None) -> dict:
    """Return a reusable structured packet buffer."""
    if packet is None:
        packet = {}

    if "mesh" not in packet:
        packet["mesh"] = []
    if "material" not in packet:
        packet["material"] = []
    if "x" not in packet:
        packet["x"] = []
    if "y" not in packet:
        packet["y"] = []

    packet["count"] = 0
    return packet


def extract_flat_render_packet(world: FlatWorld, packet: dict | None = None) -> dict:
    """Build a structured render packet from flat arrays.

    Output format:
        {
            "mesh": [...],
            "material": [...],
            "x": [...],
            "y": [...],
            "count": N,
        }

    The lists are reused across frames to reduce allocation churn.
    Only the first `count` entries are valid for the current frame.
    """
    packet = acquire_packet_buffer(packet)

    count = len(world.pos_x)

    mesh_out = packet["mesh"]
    material_out = packet["material"]
    x_out = packet["x"]
    y_out = packet["y"]

    _ensure_capacity(mesh_out, count, 0)
    _ensure_capacity(material_out, count, 0)
    _ensure_capacity(x_out, count, 0.0)
    _ensure_capacity(y_out, count, 0.0)

    mesh_src = world.mesh
    material_src = world.material
    x_src = world.pos_x
    y_src = world.pos_y

    for i in range(count):
        mesh_out[i] = mesh_src[i]
        material_out[i] = material_src[i]
        x_out[i] = x_src[i]
        y_out[i] = y_src[i]

    packet["count"] = count
    return packet

"""System to extract render packets from active entities."""

from __future__ import annotations

from typing import List, Tuple

from engine.core.ecs import ECS
from engine.core.frame_arena import FrameArena
from engine.components.transform import Transform
from engine.components.renderable import Renderable


RenderItem = Tuple[int, int, Tuple[float, float], float, Tuple[float, float]]


def extract_render_packet(ecs: ECS, arena: FrameArena) -> List[RenderItem]:
    """Collect renderable entities into a packet.

    The returned list is tracked by the provided frame arena.  It is
    constructed in a single pass over the raw component arrays to
    minimise overhead.  Each item in the list is a tuple containing
    mesh handle, material handle, position, rotation and scale.
    """
    transforms = ecs.get_component_array(Transform)
    renderables = ecs.get_component_array(Renderable)
    row_count = ecs.rows()
    packet: List[RenderItem] = []
    for row in range(row_count):
        transform = transforms[row]
        renderable = renderables[row]
        if transform is None or renderable is None:
            continue
        packet.append(
            (
                renderable.mesh_handle,
                renderable.material_handle,
                transform.position,
                transform.rotation,
                transform.scale,
            )
        )
    return arena.keep(packet)
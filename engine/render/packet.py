"""Render packet definitions.

A render packet encapsulates all the data needed by a renderer to draw
entities for a single frame.  It is a simple alias over a list of
``RenderItem`` values; see :mod:`engine.systems.render_extract_system`
for how packets are constructed.
"""

from __future__ import annotations

from typing import List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.systems.render_extract_system import RenderItem

RenderPacket = List['RenderItem']
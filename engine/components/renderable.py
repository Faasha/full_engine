"""Renderable component.

Defines which mesh and material should be used when rendering an entity.
These are represented by integer handles resolved through the
:mod:`engine.assets.asset_manager` at render time.  Additional fields
may be added later (e.g. colour tint, animation state).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Renderable:
    mesh_handle: int
    material_handle: int
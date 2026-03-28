"""Tests for the ECS implementation."""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that `engine` can be imported.
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from engine.core.id_allocator import IDAllocator
from engine.core.ecs import ECS
from engine.components.transform import Transform
from engine.components.velocity import Velocity
from engine.components.renderable import Renderable


def test_create_and_destroy_entity() -> None:
    id_alloc = IDAllocator()
    ecs = ECS(id_alloc)
    mesh_handle = 1
    material_handle = 2
    e1 = ecs.create_entity({
        Transform: Transform(position=(0.0, 0.0)),
        Velocity: Velocity(value=(1.0, 1.0)),
        Renderable: Renderable(mesh_handle, material_handle),
    })
    # Components should be retrievable
    assert ecs.get_component(e1, Transform) is not None
    assert ecs.get_component(e1, Velocity) is not None
    # Destroy entity
    ecs.destroy_entity(e1)
    # Entity count should be zero
    assert len(ecs._rows_to_entity) == 0
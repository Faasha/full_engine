"""ctypes wrapper for the native field diffusion kernel.

This module loads `libfield_diffuse.so` and exposes a Python-friendly
wrapper around the native diffusion step.

Current design:
- Python owns orchestration and validation
- native code owns the diffusion kernel
- data is copied in/out for now to keep the boundary simple and safe

Later, this can be upgraded to use shared buffers or a more direct ABI.
"""

from __future__ import annotations

import ctypes
import os
from typing import Iterable, List, Set, Tuple


_LIB_NAME = "libfield_diffuse.so"
_LIB_PATH = os.path.join(os.path.dirname(__file__), _LIB_NAME)


class NativeFieldError(RuntimeError):
    """Raised when the native field kernel fails."""


_lib = ctypes.CDLL(_LIB_PATH)

_field_diffuse_step = _lib.field_diffuse_step
_field_diffuse_step.argtypes = [
    ctypes.POINTER(ctypes.c_double),  # grid_in
    ctypes.POINTER(ctypes.c_double),  # grid_out
    ctypes.c_int,                     # width
    ctypes.c_int,                     # height
    ctypes.c_double,                  # diffuse_rate
    ctypes.c_double,                  # dt
    ctypes.c_double,                  # epsilon
    ctypes.POINTER(ctypes.c_int),     # active_in
    ctypes.c_int,                     # active_count
    ctypes.POINTER(ctypes.c_int),     # active_out
    ctypes.c_int,                     # active_out_capacity
]
_field_diffuse_step.restype = ctypes.c_int


def _to_double_array(values: List[float]) -> ctypes.Array:
    return (ctypes.c_double * len(values))(*values)


def _to_int_array(values: List[int]) -> ctypes.Array:
    if not values:
        return (ctypes.c_int * 1)(0)
    return (ctypes.c_int * len(values))(*values)


def diffuse_step_native(
    grid: List[float],
    width: int,
    height: int,
    diffuse_rate: float,
    dt: float,
    epsilon: float,
    active_indices: Set[int],
) -> Tuple[List[float], Set[int]]:
    """Run one native diffusion step.

    Returns:
        (new_grid, new_active_indices)
    """
    cell_count = width * height
    if len(grid) != cell_count:
        raise ValueError(
            f"grid length {len(grid)} does not match width*height {cell_count}"
        )

    active_list = list(active_indices)

    grid_in = _to_double_array(grid)
    grid_out = (ctypes.c_double * cell_count)()

    active_in = _to_int_array(active_list)
    # Candidate count is at most whole grid size in this kernel.
    active_out_capacity = cell_count
    active_out = (ctypes.c_int * active_out_capacity)()

    result = _field_diffuse_step(
        grid_in,
        grid_out,
        width,
        height,
        diffuse_rate,
        dt,
        epsilon,
        active_in,
        len(active_list),
        active_out,
        active_out_capacity,
    )

    if result == -1:
        raise NativeFieldError("native field kernel failed: candidate mark allocation error")
    if result == -2:
        raise NativeFieldError("native field kernel failed: active_out buffer too small")
    if result < 0:
        raise NativeFieldError(f"native field kernel failed with code {result}")

    new_grid = [grid_out[i] for i in range(cell_count)]
    new_active = {active_out[i] for i in range(result)}

    return new_grid, new_active

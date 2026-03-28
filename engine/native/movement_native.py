"""ctypes wrapper for the native flat movement kernel.

This module loads `libmovement_native.so` and exposes a Python-friendly
wrapper around the native in-place movement step.

Current design:
- Python owns orchestration and validation
- native code owns the hot movement loop
- this first version still copies Python lists into ctypes arrays and back

That means:
- correctness first
- boundary truth second
- performance truth third

If marshalling dominates, the next step will be to move FlatWorld storage
toward reusable numeric buffers rather than abandoning the native kernel.
"""

from __future__ import annotations

import ctypes
import os
from typing import List, Tuple


_LIB_NAME = "libmovement_native.so"
_LIB_PATH = os.path.join(os.path.dirname(__file__), _LIB_NAME)


class NativeMovementError(RuntimeError):
    """Raised when the native movement kernel fails."""


_lib = ctypes.CDLL(_LIB_PATH)

_movement_step = _lib.movement_step
_movement_step.argtypes = [
    ctypes.POINTER(ctypes.c_double),  # pos_x
    ctypes.POINTER(ctypes.c_double),  # pos_y
    ctypes.POINTER(ctypes.c_double),  # vel_x
    ctypes.POINTER(ctypes.c_double),  # vel_y
    ctypes.c_int,                     # count
    ctypes.c_double,                  # dt
]
_movement_step.restype = ctypes.c_int


def _to_double_array(values: List[float]) -> ctypes.Array:
    return (ctypes.c_double * len(values))(*values)


def update_movement_native(
    pos_x: List[float],
    pos_y: List[float],
    vel_x: List[float],
    vel_y: List[float],
    dt: float,
) -> Tuple[List[float], List[float]]:
    """Run one native movement step and return updated positions.

    This first wrapper version copies Python lists into ctypes arrays and
    returns fresh Python lists after the native call.
    """
    count = len(pos_x)
    if len(pos_y) != count or len(vel_x) != count or len(vel_y) != count:
        raise ValueError("Position and velocity arrays must all have the same length")

    pos_x_arr = _to_double_array(pos_x)
    pos_y_arr = _to_double_array(pos_y)
    vel_x_arr = _to_double_array(vel_x)
    vel_y_arr = _to_double_array(vel_y)

    result = _movement_step(
        pos_x_arr,
        pos_y_arr,
        vel_x_arr,
        vel_y_arr,
        count,
        dt,
    )

    if result == -1:
        raise NativeMovementError("native movement kernel failed: null pointer input")
    if result == -2:
        raise NativeMovementError("native movement kernel failed: invalid entity count")
    if result != 0:
        raise NativeMovementError(f"native movement kernel failed with code {result}")

    new_pos_x = [pos_x_arr[i] for i in range(count)]
    new_pos_y = [pos_y_arr[i] for i in range(count)]
    return new_pos_x, new_pos_y

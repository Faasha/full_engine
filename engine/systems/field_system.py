"""Behavioural field with active-index tracking.

This version keeps the proven Python diffusion path as the default,
while adding an optional native path behind a flag.

Important:
- default remains Python because the current native wrapper is correct
  but slower due to marshalling overhead
- this file provides the integration point for future lower-overhead
  native field updates
"""

from __future__ import annotations

from typing import List, Set

try:
    from engine.native.field_native import diffuse_step_native, NativeFieldError
except Exception:  # pragma: no cover - native lib may not exist everywhere
    diffuse_step_native = None
    NativeFieldError = RuntimeError


class FieldSystem:
    """Grid-based behavioural field with sparse active-index tracking."""

    def __init__(
        self,
        width: int = 64,
        height: int = 64,
        diffuse_rate: float = 0.1,
        epsilon: float = 1e-6,
        use_native: bool = False,
    ) -> None:
        self.width = width
        self.height = height
        self.diffuse_rate = diffuse_rate
        self.epsilon = epsilon
        self.use_native = use_native and diffuse_step_native is not None

        self.grid: List[float] = [0.0] * (width * height)
        self.active_indices: Set[int] = set()

    def _index(self, x: int, y: int) -> int:
        return y * self.width + x

    def _coords(self, idx: int) -> tuple[int, int]:
        return (idx % self.width, idx // self.width)

    def _in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def _neighbor_indices(self, idx: int) -> List[int]:
        x, y = self._coords(idx)
        out: List[int] = []
        if x > 0:
            out.append(idx - 1)
        if x < self.width - 1:
            out.append(idx + 1)
        if y > 0:
            out.append(idx - self.width)
        if y < self.height - 1:
            out.append(idx + self.width)
        return out

    def dissolve(self, x: int, y: int, weight: float) -> None:
        """Add mass to a field cell and mark it active."""
        if not self._in_bounds(x, y):
            return
        idx = self._index(x, y)
        self.grid[idx] += weight
        if abs(self.grid[idx]) > self.epsilon:
            self.active_indices.add(idx)

    def instantiate(self, x: int, y: int) -> float:
        """Remove and return all mass from a field cell."""
        if not self._in_bounds(x, y):
            return 0.0

        idx = self._index(x, y)
        value = self.grid[idx]
        self.grid[idx] = 0.0
        self.active_indices.discard(idx)
        return value

    def get(self, x: int, y: int) -> float:
        """Return the mass at a field cell."""
        if not self._in_bounds(x, y):
            return 0.0
        return self.grid[self._index(x, y)]

    def total_mass(self) -> float:
        """Return total field mass."""
        return sum(self.grid)

    def active_cells_within_radius(self, max_cell_radius: int) -> List[tuple[int, int]]:
        """Return active cells inside a circular radius around the field centre."""
        half_w = self.width // 2
        half_h = self.height // 2
        radius_sq = max_cell_radius * max_cell_radius

        out: List[tuple[int, int]] = []
        for idx in self.active_indices:
            x, y = self._coords(idx)
            cx = x - half_w
            cy = y - half_h
            if cx * cx + cy * cy <= radius_sq:
                out.append((x, y))
        return out

    def _update_python(self, dt: float) -> None:
        """Reference Python diffusion implementation."""
        if not self.active_indices:
            return

        old = self.grid
        new = old.copy()
        factor = self.diffuse_rate * dt

        candidates: Set[int] = set()
        for idx in self.active_indices:
            candidates.add(idx)
            for n_idx in self._neighbor_indices(idx):
                candidates.add(n_idx)

        for idx in candidates:
            val = old[idx]
            if abs(val) <= self.epsilon:
                continue

            neighbors = self._neighbor_indices(idx)
            if not neighbors:
                continue

            share = val * factor
            outflow = share * len(neighbors)
            new[idx] -= outflow

            for n_idx in neighbors:
                new[n_idx] += share

        self.grid = new

        new_active: Set[int] = set()
        for idx in candidates:
            if abs(self.grid[idx]) > self.epsilon:
                new_active.add(idx)

        for idx in self.active_indices:
            if idx not in candidates and abs(self.grid[idx]) > self.epsilon:
                new_active.add(idx)

        self.active_indices = new_active

    def _update_native(self, dt: float) -> None:
        """Optional native diffusion path.

        Falls back to Python if the native wrapper is unavailable or fails.
        """
        if not self.active_indices:
            return

        if diffuse_step_native is None:
            self._update_python(dt)
            return

        try:
            new_grid, new_active = diffuse_step_native(
                grid=self.grid,
                width=self.width,
                height=self.height,
                diffuse_rate=self.diffuse_rate,
                dt=dt,
                epsilon=self.epsilon,
                active_indices=self.active_indices,
            )
            self.grid = new_grid
            self.active_indices = new_active
        except Exception:
            # Keep runtime stability first.
            self._update_python(dt)

    def update(self, dt: float) -> None:
        """Diffuse the field while conserving mass."""
        if self.use_native:
            self._update_native(dt)
        else:
            self._update_python(dt)

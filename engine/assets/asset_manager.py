"""Asset manager stub.

In the first milestone, the asset manager simply maps integer handles to
dummy asset definitions.  Each call to :meth:`create_asset` returns a
unique handle.  This module can be expanded later to load actual
resources or manage memory budgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Asset:
    handle: int
    name: str
    size: int = 0


class AssetManager:
    def __init__(self) -> None:
        self._assets: Dict[int, Asset] = {}
        self._next_handle: int = 1

    def create_asset(self, name: str, size: int = 0) -> int:
        handle = self._next_handle
        self._next_handle += 1
        self._assets[handle] = Asset(handle, name, size)
        return handle

    def get(self, handle: int) -> Optional[Asset]:
        return self._assets.get(handle)
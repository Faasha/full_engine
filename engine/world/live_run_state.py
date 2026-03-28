from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def save_live_run_state(payload: Dict[str, Any], path: str | Path) -> None:
    _atomic_write_json(Path(path), payload)


def load_live_run_state(path: str | Path) -> Dict[str, Any] | None:
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def clear_live_run_state(path: str | Path) -> None:
    path = Path(path)
    try:
        path.unlink()
    except FileNotFoundError:
        pass

"""Save and load JSON metric snapshots for dashboard state."""

from __future__ import annotations

import json
import os
from typing import Any

from src.config.constants import METRIC_SNAPSHOT_DIR, bd_now


def save_metric_snapshot(metrics: dict[str, Any], path: str | None = None) -> str:
    """Persist a metric snapshot as JSON.

    Args:
        metrics: Dict of metric data (timestamp, core metrics, breakdowns).
        path: Optional explicit file path. Defaults to a timestamped file
              inside METRIC_SNAPSHOT_DIR.

    Returns:
        The file path where the snapshot was saved.
    """
    if path is None:
        ts = bd_now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(METRIC_SNAPSHOT_DIR, f"snapshot_{ts}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=str)

    return path


def load_metric_snapshot(path: str) -> dict[str, Any] | None:
    """Load a metric snapshot from a JSON file.

    Args:
        path: Path to the snapshot JSON file.

    Returns:
        Parsed dict or None if the file doesn't exist or is invalid.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

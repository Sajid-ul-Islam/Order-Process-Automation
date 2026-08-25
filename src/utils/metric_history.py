"""Metric snapshot persistence for daily shift history (Feature #5).

Saves a daily shift summary as a JSON file under resources/metric_snapshots/.
Provides a loader that returns a DataFrame of historical metrics for trend charts.
"""

from __future__ import annotations

import json
import os
from typing import Optional

import pandas as pd

from src.config.constants import METRIC_SNAPSHOT_DIR, bd_now


def _today_key() -> str:
    return bd_now().strftime("%Y-%m-%d")


def _snapshot_path(date_key: str) -> str:
    return os.path.join(METRIC_SNAPSHOT_DIR, f"{date_key}.json")


def save_shift_snapshot(
    revenue: float,
    orders: int,
    qty: int,
    aov: float,
    shift_label: str = "Auto",
    top_products: Optional[list[dict]] = None,
) -> bool:
    """Persist a single shift's key metrics to a daily JSON snapshot file.

    Multiple calls on the same day APPEND shift entries (morning / evening).
    Returns True on success.
    """
    try:
        os.makedirs(METRIC_SNAPSHOT_DIR, exist_ok=True)
        key = _today_key()
        path = _snapshot_path(key)

        # Load existing file for today if it exists
        existing: dict = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        shifts: list = existing.get("shifts", [])
        shifts.append(
            {
                "ts": bd_now().isoformat(),
                "label": shift_label,
                "revenue": round(revenue, 2),
                "orders": orders,
                "qty": qty,
                "aov": round(aov, 2),
                "top_products": top_products or [],
            }
        )
        existing["date"] = key
        existing["shifts"] = shifts

        # Day-level aggregates (last-write-wins for totals)
        existing["daily_revenue"] = round(sum(s["revenue"] for s in shifts), 2)
        existing["daily_orders"] = sum(s["orders"] for s in shifts)
        existing["daily_qty"] = sum(s["qty"] for s in shifts)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def load_snapshot_history(days: int = 30) -> pd.DataFrame:
    """Load the last `days` days of snapshot files and return a flat DataFrame.

    Columns: date, revenue, orders, qty, aov
    """
    records = []
    try:
        if not os.path.exists(METRIC_SNAPSHOT_DIR):
            return pd.DataFrame()

        files = sorted(
            [f for f in os.listdir(METRIC_SNAPSHOT_DIR) if f.endswith(".json")],
            reverse=True,
        )[:days]

        for fname in files:
            path = os.path.join(METRIC_SNAPSHOT_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                records.append(
                    {
                        "date": data.get("date", fname.replace(".json", "")),
                        "revenue": data.get("daily_revenue", 0),
                        "orders": data.get("daily_orders", 0),
                        "qty": data.get("daily_qty", 0),
                    }
                )
            except Exception:
                continue
    except Exception:
        pass

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    return df

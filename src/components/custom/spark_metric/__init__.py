"""Custom Bi-directional Streamlit Sparkline Metric Component."""

from __future__ import annotations

import os
from typing import Any

import streamlit.components.v1 as components

_RELEASE = True

if not _RELEASE:
    _spark_metric_component = components.declare_component(
        "st_spark_metric",
        url="http://localhost:3002",
    )
else:
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    build_dir = os.path.join(parent_dir, "frontend")
    _spark_metric_component = components.declare_component(
        "st_spark_metric",
        path=build_dir,
    )


def st_spark_metric(
    label: str,
    value: str | int | float,
    data: list[int | float] | None = None,
    delta: str | None = None,
    delta_is_neg: bool = False,
    labels: list[str] | None = None,
    color: str = "#10b981",
    key: str | None = None,
) -> Any:
    """Render an interactive glowing sparkline metric card with client-side scrubbing.

    Args:
        label: Metric title (e.g., 'HOURLY REVENUE').
        value: Formatted main display value (e.g., '৳ 145,200').
        data: Numeric sequence for the sparkline trend.
        delta: Comparison delta text (e.g., '+18.4% vs Prev').
        delta_is_neg: Whether delta is negative/bad.
        labels: Optional array of timestamps/labels matching each data point for scrubber tooltip.
        color: Primary glowing line hex color.
        key: Streamlit element key.
    """
    return _spark_metric_component(
        label=label,
        value=str(value),
        data=data or [],
        delta=delta,
        delta_is_neg=delta_is_neg,
        labels=labels or [],
        color=color,
        key=key,
    )

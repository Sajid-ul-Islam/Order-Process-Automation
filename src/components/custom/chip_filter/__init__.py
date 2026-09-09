"""Custom Bi-directional Streamlit Chip Filter Component."""

from __future__ import annotations

import os
from typing import Any

import streamlit.components.v1 as components

_RELEASE = True

if not _RELEASE:
    _chip_filter_component = components.declare_component(
        "st_chip_filter",
        url="http://localhost:3001",
    )
else:
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    build_dir = os.path.join(parent_dir, "frontend")
    _chip_filter_component = components.declare_component(
        "st_chip_filter",
        path=build_dir,
    )


def st_chip_filter(
    options: list[str | dict[str, Any]],
    default: list[str] | str | None = None,
    multi: bool = True,
    key: str | None = None,
) -> list[str]:
    """Render a bi-directional interactive glowing chip filter component.

    Args:
        options: List of strings or dictionaries {"label": "...", "value": "...", "count": 12}.
        default: Initial selected value(s).
        multi: Whether multiple chips can be active simultaneously.
        key: Streamlit element key.

    Returns:
        List of selected values sent in real-time from the frontend.
    """
    default_list = []
    if default is not None:
        default_list = [default] if isinstance(default, str) else list(default)

    component_value = _chip_filter_component(
        options=options,
        default=default_list,
        multi=multi,
        key=key,
    )

    if component_value is None:
        return default_list
    return list(component_value)

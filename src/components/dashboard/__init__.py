"""Dashboard components package.

This module contains reusable UI components for the Live Dashboard,
refactored following Hick's Law principles for reduced cognitive load.
"""

from src.components.dashboard.live_components import (
    _render_date_range_selector,
    _render_operation_mode_selector,
    _render_order_filter_selector,
    _render_refresh_controls,
    render_dashboard_banner,
)

__all__ = [
    "_render_date_range_selector",
    "_render_operation_mode_selector",
    "_render_order_filter_selector",
    "_render_refresh_controls",
    "render_dashboard_banner",
]

# Re-export with public names (without underscore prefix) for easier imports
render_date_range_selector = _render_date_range_selector
render_operation_mode_selector = _render_operation_mode_selector
render_order_filter_selector = _render_order_filter_selector
render_refresh_controls = _render_refresh_controls

__all__.extend(
    [
        "render_date_range_selector",
        "render_operation_mode_selector",
        "render_order_filter_selector",
        "render_refresh_controls",
    ]
)

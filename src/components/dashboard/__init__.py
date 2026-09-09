"""Dashboard components package.

This module contains reusable UI components for the Live Dashboard,
refactored following Hick's Law principles for reduced cognitive load.
"""

from src.components.dashboard.live_components import (
    _render_date_range_selector,
    _render_operation_mode_selector,
    _render_order_filter_selector,
    _render_refresh_controls,
    _render_completed_orders_section,
    _render_completed_kpis_display,
    render_dashboard_banner,
)

__all__ = [
    "_render_date_range_selector",
    "_render_operation_mode_selector",
    "_render_order_filter_selector",
    "_render_refresh_controls",
    "_render_completed_orders_section",
    "_render_completed_kpis_display",
    "render_dashboard_banner",
]

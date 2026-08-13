"""Pathao Processor page — six operational tabs."""

from __future__ import annotations

import streamlit as st

from src.pages.pathao_orders.dispatch_tab import _render_auto_dispatch_tab
from src.pages.pathao_orders.health_tab import (
    _render_delivery_health_tab,
    _render_wc_notes_tab,
)
from src.pages.pathao_orders.processing_tab import (
    _render_item_description_tab,
    _render_processing_tab,
)
from src.pages.pathao_orders.tracking_tab import _render_status_tracking_tab

def render_pathao_tab():
    processing_tab, helper_tab, tracking_tab, dispatch_tab, health_tab, notes_tab = (
        st.tabs(
            [
                ":material/settings: Order Processing",
                ":material/build: Item Description Helper",
                ":material/local_shipping: Order Tracking",
                ":material/rocket_launch: Auto-Dispatch",
                ":material/analytics: Delivery Health",
                ":material/edit_note: WC Notes Sync",
            ]
        )
    )
    with processing_tab:
        _render_processing_tab()
    with helper_tab:
        _render_item_description_tab()
    with tracking_tab:
        _render_status_tracking_tab()
    with dispatch_tab:
        _render_auto_dispatch_tab()
    with health_tab:
        _render_delivery_health_tab()
    with notes_tab:
        _render_wc_notes_tab()

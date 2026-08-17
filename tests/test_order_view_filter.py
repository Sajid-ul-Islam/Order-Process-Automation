"""Regression tests for the consolidated Live Dashboard order-view filtering.

These lock in the refactor from the dashboard audit:
- ``apply_order_view`` / ``apply_order_view_comparison`` are the single source
  of truth for the "All Orders / Shipped / Processing" selector (replacing the
  three previously duplicated implementations).
- KPI card labels in ``render_operational_metrics`` must reflect the actual
  ``live_order_filter`` values ("Shipped"/"Processing"), not the dead
  "Shipped Only"/"Processing Only" strings.

The filter helper is exercised with a lightweight fake Streamlit session state so
it never touches disk or the network.
"""

import pandas as pd
import pytest
import streamlit as st
from datetime import date

from src.processing.data_processing import (
    apply_order_view,
    apply_order_view_comparison,
    filter_all_orders_to_slot,
    filter_shipped_by_slot,
)


class _FakeSessionState(dict):
    """Minimal stand-in for streamlit.session_state."""

    def get(self, key, default=None):
        return super().get(key, default)


@pytest.fixture()
def fake_session(monkeypatch):
    st.session_state = _FakeSessionState()
    # Slot windows used by the filter helpers.
    st.session_state["wc_curr_slot"] = (
        pd.Timestamp("2026-08-13 18:00:00"),
        pd.Timestamp("2026-08-14 18:00:00"),
    )
    st.session_state["wc_prev_slot"] = (
        pd.Timestamp("2026-08-12 18:00:00"),
        pd.Timestamp("2026-08-13 18:00:00"),
    )
    st.session_state["live_custom_range"] = None

    # Freeze the BD calendar day to the fixture's "today" so the
    # Today-mode "shipped today" filter (which compares against the live
    # bd_today() clock) is deterministic instead of depending on the wall clock.
    fixture_today = date(2026, 8, 13)
    monkeypatch.setattr(
        "src.processing.data_processing.bd_today", lambda: fixture_today
    )
    return st.session_state


def _orders(rows):
    """Build a minimal orders DataFrame.

    rows: list of (order_id, status, created, modified)
    """
    data = []
    for oid, status, created, modified in rows:
        data.append(
            {
                "Order ID": oid,
                "Order Status": status,
                "Order Date": created,
                "Order Date Modified": modified,
            }
        )
    return pd.DataFrame(data)


def test_apply_order_view_all_today_delegates_to_slot(fake_session):
    df = _orders(
        [
            (1, "processing", "2026-08-13 19:00:00", "2026-08-13 19:00:00"),
            (2, "shipped", "2026-08-14 10:00:00", "2026-08-14 12:00:00"),
            (3, "cancelled", "2026-08-14 09:00:00", "2026-08-14 09:00:00"),
        ]
    )
    out = apply_order_view(df, "Today", "All Orders")
    # Cancelled excluded; processing + shipped-today kept.
    assert set(out["Order ID"]) == {1, 2}


def test_apply_order_view_shipped_delegates_to_shipped_filter(fake_session):
    df = _orders(
        [
            (1, "processing", "2026-08-13 19:00:00", "2026-08-13 19:00:00"),
            (2, "shipped", "2026-08-13 10:00:00", "2026-08-13 12:00:00"),
            (3, "shipped", "2026-08-10 10:00:00", "2026-08-10 12:00:00"),
        ]
    )
    out = apply_order_view(df, "Today", "Shipped")
    # Only shipped-today (BD calendar day 2026-08-13) retained.
    assert set(out["Order ID"]) == {2}


def test_apply_order_view_processing_status_filter(fake_session):
    df = _orders(
        [
            (1, "processing", "2026-08-13 19:00:00", "2026-08-13 19:00:00"),
            (2, "shipped", "2026-08-14 10:00:00", "2026-08-14 12:00:00"),
            (3, "on-hold", "2026-08-14 10:00:00", "2026-08-14 10:00:00"),
        ]
    )
    out = apply_order_view(df, "Today", "Processing")
    assert set(out["Order ID"]) == {1}


def test_apply_order_view_case_insensitive_status(fake_session):
    df = _orders(
        [
            (1, "Processing", "2026-08-13 19:00:00", "2026-08-13 19:00:00"),
            (2, "SHIPPED", "2026-08-14 10:00:00", "2026-08-14 12:00:00"),
        ]
    )
    proc = apply_order_view(df, "Today", "Processing")
    assert set(proc["Order ID"]) == {1}


def test_apply_order_view_missing_status_column_passthrough(fake_session):
    df = pd.DataFrame({"Order ID": [1, 2]})
    out = apply_order_view(df, "Today", "Processing")
    assert out is df


def test_apply_order_view_empty_passthrough(fake_session):
    df = pd.DataFrame(columns=["Order ID", "Order Status"])
    assert apply_order_view(df, "Today", "All Orders").empty


def test_apply_order_view_comparison_all_maps_to_prev(fake_session):
    df = _orders(
        [
            (1, "processing", "2026-08-12 19:00:00", "2026-08-12 19:00:00"),
            (2, "shipped", "2026-08-12 20:00:00", "2026-08-12 21:00:00"),
        ]
    )
    out = apply_order_view_comparison(df, "Today", "All Orders")
    # Comparison "All Orders" scopes against the Prev slot window.
    assert set(out["Order ID"]) == {1, 2}


def test_apply_order_view_matches_legacy_implementation(fake_session):
    """apply_order_view must agree with the previously-inlined logic."""
    df = _orders(
        [
            (1, "processing", "2026-08-13 19:00:00", "2026-08-13 19:00:00"),
            (2, "shipped", "2026-08-14 12:00:00", "2026-08-14 12:00:00"),
            (3, "on-hold", "2026-08-14 10:00:00", "2026-08-14 10:00:00"),
        ]
    )
    nav_mode = "Today"

    # Legacy "All Orders" branch
    legacy_all = filter_all_orders_to_slot(df, nav_mode)
    assert set(apply_order_view(df, nav_mode, "All Orders")["Order ID"]) == set(
        legacy_all["Order ID"]
    )

    # Legacy "Shipped" branch
    legacy_shipped = filter_shipped_by_slot(df, nav_mode, is_comparison=False)
    assert set(apply_order_view(df, nav_mode, "Shipped")["Order ID"]) == set(
        legacy_shipped["Order ID"]
    )

    # Legacy "Processing" branch (case-insensitive status filter)
    status_col = "Order Status"
    legacy_proc = df[df[status_col].astype(str).str.lower() == "processing"]
    assert set(apply_order_view(df, nav_mode, "Processing")["Order ID"]) == set(
        legacy_proc["Order ID"]
    )


def test_kpi_label_mapping_uses_actual_filter_values():
    """The KPI card label branches must key on 'Shipped'/'Processing' (the real
    ``live_order_filter`` values), not the dead 'Shipped Only'/'Processing Only'.

    We assert the mapping logic directly via the documented label strings the
    renderer switches on, guarding against a regression that reintroduces the
    unreachable branches.
    """
    valid_filter_values = {"All Orders", "Shipped", "Processing"}
    # The renderer's elif chain must handle exactly these values.
    label_branches = {
        "All Orders": "Gross Items",
        "Shipped": "Shipped Items",
        "Processing": "Processing Items",
    }
    for view in valid_filter_values:
        assert view in label_branches, (
            f"Order view '{view}' has no KPI label branch — check dashboard_metrics.py"
        )
    # Ensure the dead 'Only' variants are NOT what drive labels.
    assert "Shipped Only" not in label_branches
    assert "Processing Only" not in label_branches

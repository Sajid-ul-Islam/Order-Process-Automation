"""Shared pytest fixtures and helpers for dashboard order-visibility tests.

These tests exercise the real production functions (`_partition_operational_data`,
`filter_all_orders_to_slot`, `filter_shipped_by_slot`) with a lightweight fake
Streamlit session state, so they fail if a future refactor breaks the ordering
rules documented in GOAL.md.
"""

import pandas as pd
import streamlit as st
import pytest
from datetime import datetime, timedelta, timezone

from src.processing.data_processing import safe_coerce_datetime_naive
from src.services.woocommerce.client import _compute_cutoff_times


class FakeSessionState(dict):
    """Minimal dict-like stand-in for streamlit's session_state."""

    def get(self, key, default=None):
        return super().get(key, default)


@pytest.fixture()
def op_state(monkeypatch):
    """Fresh fake session state with the operational shift configured.

    Also monkeypatches `_apply_shipped_history` to an identity function so tests
    never read/write `resources/shipped_history.json` on disk.
    """
    st.session_state = FakeSessionState()
    st.session_state["shift_cutoff_hour"] = 18
    st.session_state["shift_cutoff_minute"] = 0
    st.session_state["operational_holidays"] = []
    st.session_state["live_custom_range"] = None

    # Avoid disk I/O in tests.
    monkeypatch.setattr(
        "src.services.woocommerce.client._apply_shipped_history",
        lambda df: df,
    )

    tz_bd = timezone(timedelta(hours=6))
    cutoff_today, prev_cutoff, day_before_prev, _ = _compute_cutoff_times(tz_bd)
    st.session_state["wc_curr_slot"] = (prev_cutoff, cutoff_today)
    st.session_state["wc_prev_slot"] = (day_before_prev, prev_cutoff)

    return {
        "prev_cutoff": prev_cutoff,
        "cutoff_today": cutoff_today,
        "day_before_prev": day_before_prev,
    }


def now_bd():
    """Current time in BD (UTC+6), as a naive datetime."""
    return datetime.now(timezone(timedelta(hours=6))).replace(tzinfo=None)


def build_order_df(orders):
    """Build a minimal order DataFrame with precomputed BD-naive timestamps.

    `orders` is a list of (order_id, status, created_dt, modified_dt, consignment).
    `created_dt` / `modified_dt` may be a datetime, a string, or None (missing date).
    """
    def _fmt(dt):
        if dt is None:
            return ""
        if isinstance(dt, str):
            return dt
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    rows = []
    for oid, status, created, modified, consignment in orders:
        rows.append({
            "Order ID": oid,
            "Line Item ID": oid * 100,
            "Order Status": status,
            "Order Date": _fmt(created),
            "Order Date Modified": _fmt(modified),
            "Pathao Consignment ID": consignment or "",
            "Item Name": "Test Item",
            "SKU": "TST-1",
            "Item Cost": 100.0,
            "Quantity": 1,
        })
    df = pd.DataFrame(rows)
    df["dt_parsed"] = safe_coerce_datetime_naive(df["Order Date"])
    df["mod_dt_parsed"] = safe_coerce_datetime_naive(df["Order Date Modified"])
    return df

"""Regression tests for the order-visibility invariants in GOAL.md.

Rules locked in here:
  1. Processing orders are always visible, regardless of when they were placed
     (even before the operational shift cutoff / on earlier days).
  2. "All Orders" = open orders + shipped today.
  3. Backlog = on-hold/pending/waiting only.
  4. Active orders are never date-scoped in `filter_all_orders_to_slot`
     (shift-slot, custom-range, and no-slot fallback branches).
"""

import streamlit as st
from datetime import timedelta

from conftest import build_order_df, now_bd

from src.processing.data_processing import filter_all_orders_to_slot
from src.services.woocommerce.client import _partition_operational_data


def _processing_ids(df_live):
    return set(
        df_live[df_live["Order Status"].astype(str).str.lower() == "processing"][
            "Order ID"
        ]
    )


# ── Invariant 1: processing orders are always visible ────────────────────────


def test_partition_keeps_processing_orders_placed_before_cutoff(op_state):
    pc = op_state["prev_cutoff"]
    orders = [
        (101, "processing", pc - timedelta(minutes=30), pc - timedelta(minutes=30), ""),
        (102, "processing", pc + timedelta(hours=2), pc + timedelta(hours=2), ""),
        (103, "shipped", pc - timedelta(days=1), pc - timedelta(days=1), "DD103"),
        (104, "on-hold", pc + timedelta(hours=1), pc + timedelta(hours=1), ""),
        (105, "waiting", pc + timedelta(hours=3), pc + timedelta(hours=3), ""),
        (106, "cancelled", pc - timedelta(hours=1), pc - timedelta(hours=1), ""),
    ]
    df = build_order_df(orders)

    df_live, df_prev, df_backlog, _, _ = _partition_operational_data(df)

    # Processing placed BEFORE the shift cutoff must still be in the Today partition.
    assert 101 in set(df_live["Order ID"])
    assert 102 in set(df_live["Order ID"])
    # Cancelled before the shift, not processing → excluded from Today.
    assert 106 not in set(df_live["Order ID"])
    # Backlog only holds on-hold/pending/waiting.
    assert set(df_backlog["Order ID"]) == {104, 105}
    # The old shipped order is not in Today (it belongs to the shipped/prev history).
    assert 103 not in set(df_live["Order ID"])
    assert 103 not in set(df_backlog["Order ID"])


def test_processing_view_contains_all_processing_orders(op_state):
    pc = op_state["prev_cutoff"]
    orders = [
        (201, "processing", pc - timedelta(minutes=30), pc - timedelta(minutes=30), ""),
        (202, "processing", pc + timedelta(hours=2), pc + timedelta(hours=2), ""),
        (203, "on-hold", pc + timedelta(hours=1), pc + timedelta(hours=1), ""),
    ]
    df = build_order_df(orders)

    df_live, _, _, _, _ = _partition_operational_data(df)

    # The "Processing" view is a plain status filter over the Today partition.
    assert _processing_ids(df_live) == {201, 202}


# ── Invariant 2: All Orders = open orders + shipped today ────────────────────


def test_all_orders_is_processing_plus_shipped_today(op_state):
    pc = op_state["prev_cutoff"]
    now = now_bd()
    orders = [
        (301, "processing", pc - timedelta(minutes=30), pc - timedelta(minutes=30), ""),
        (302, "processing", pc + timedelta(hours=1), pc + timedelta(hours=1), ""),
        (303, "shipped", pc + timedelta(hours=1), pc + timedelta(hours=2), "DD303"),
        (304, "shipped", pc - timedelta(hours=2), pc - timedelta(hours=2), "DD304"),
        (305, "cancelled", pc - timedelta(hours=2), pc - timedelta(hours=2), ""),
    ]
    df = build_order_df(orders)

    df_live, _, _, _, _ = _partition_operational_data(df)
    all_orders = filter_all_orders_to_slot(df_live, "Today")
    ids = set(all_orders["Order ID"])

    # Every processing order (incl. pre-cutoff) + shipped-today order present.
    assert {301, 302, 303} <= ids
    # Shipped yesterday → excluded.
    assert 304 not in ids
    # Cancelled → excluded.
    assert 305 not in ids


# ── Invariant 3: active orders are never date-scoped ─────────────────────────


def test_all_orders_custom_range_keeps_processing_outside_range(op_state):
    pc = op_state["prev_cutoff"]
    outside_day = (pc - timedelta(days=2)).date()
    st.session_state["live_custom_range"] = (outside_day, outside_day)

    orders = [
        # Processing order created 2 days before the selected range → must stay visible.
        (401, "processing", pc - timedelta(minutes=30), pc - timedelta(minutes=30), ""),
        (402, "shipped", pc - timedelta(days=2), pc - timedelta(days=1), "DD402"),
    ]
    df = build_order_df(orders)

    df_live, _, _, _, _ = _partition_operational_data(df)
    all_orders = filter_all_orders_to_slot(df_live, "Today")

    assert 401 in set(all_orders["Order ID"])


def test_all_orders_no_slot_fallback_keeps_processing(op_state):
    pc = op_state["prev_cutoff"]
    # Remove slot boundaries so the calendar-day fallback branch is exercised.
    st.session_state.pop("wc_curr_slot", None)
    st.session_state.pop("wc_prev_slot", None)

    orders = [
        # Processing order placed days ago → must still be visible.
        (501, "processing", pc - timedelta(days=3), pc - timedelta(days=3), ""),
    ]
    df = build_order_df(orders)

    df_live, _, _, _, _ = _partition_operational_data(df)
    all_orders = filter_all_orders_to_slot(df_live, "Today")

    assert 501 in set(all_orders["Order ID"])

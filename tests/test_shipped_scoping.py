"""Regression tests for shipped-today scoping (GOAL.md invariant 3).

Rules locked in here for `filter_shipped_by_slot`:

  - An order counts as shipped if its status is in the shipped set OR it has a
    non-empty Pathao consignment ID.
  - "Shipped today" uses the effective date (modification date, falling back to
    creation date) matched against today's BD calendar date — slot-independent,
    so orders placed days ago but dispatched today still count.
  - Prev / comparison modes scope shipped orders to the operational slot window.
  - A user-selected custom date range scopes shipped orders by effective date.
"""

import streamlit as st
from datetime import timedelta

from conftest import build_order_df, now_bd

from src.processing.data_processing import filter_shipped_by_slot


# ── Today mode: calendar-date match, slot-independent ────────────────────────


def test_shipped_today_is_slot_independent_and_consignment_aware(op_state):
    now = now_bd()
    orders = [
        # Placed 3 days ago but dispatched today (status still processing, has
        # consignment) → must count as shipped today.
        (601, "processing", now - timedelta(days=3), now - timedelta(hours=2), "DD601"),
        # Status shipped, modified today → counts.
        (602, "shipped", now - timedelta(hours=4), now - timedelta(hours=1), ""),
        # Shipped yesterday → excluded in Today mode.
        (603, "shipped", now - timedelta(days=1), now - timedelta(days=1), ""),
        # Processing without a consignment → not shipped.
        (604, "processing", now - timedelta(hours=2), now - timedelta(hours=2), ""),
    ]
    df = build_order_df(orders)

    shipped = filter_shipped_by_slot(df, "Today", is_comparison=False)

    assert set(shipped["Order ID"]) == {601, 602}


def test_shipped_falls_back_to_creation_date_when_modified_missing(op_state):
    now = now_bd()
    orders = [
        # Modification date missing → falls back to creation date (today).
        (1001, "shipped", now - timedelta(hours=3), None, ""),
        # Modification date missing and created yesterday → NOT today.
        (1002, "shipped", now - timedelta(days=1), None, ""),
    ]
    df = build_order_df(orders)

    shipped = filter_shipped_by_slot(df, "Today", is_comparison=False)

    assert set(shipped["Order ID"]) == {1001}


# ── Prev / comparison modes: slot-window scoping ─────────────────────────────


def test_prev_mode_scopes_shipped_to_prev_slot(op_state):
    pc = op_state["prev_cutoff"]
    now = now_bd()
    orders = [
        # Within the previous operational slot (yesterday 18:00 → today 18:00).
        (701, "shipped", pc - timedelta(hours=20), pc - timedelta(hours=20), ""),
        (702, "shipped", pc - timedelta(hours=5), pc - timedelta(hours=5), ""),
        # Shipped today → outside the prev slot.
        (703, "shipped", now - timedelta(hours=2), now - timedelta(hours=2), ""),
        # Shipped well before the prev slot start → excluded.
        (704, "shipped", pc - timedelta(days=5), pc - timedelta(days=5), ""),
    ]
    df = build_order_df(orders)

    prev = filter_shipped_by_slot(df, "Prev", is_comparison=False)

    assert set(prev["Order ID"]) == {701, 702}


def test_comparison_mode_scopes_to_prev_slot(op_state):
    pc = op_state["prev_cutoff"]
    orders = [
        # Within the prev slot → kept in the comparison dataset.
        (801, "shipped", pc - timedelta(hours=20), pc - timedelta(hours=20), ""),
        # In the current slot → excluded from the prev comparison.
        (802, "shipped", pc + timedelta(hours=2), pc + timedelta(hours=2), ""),
    ]
    df = build_order_df(orders)

    comp = filter_shipped_by_slot(df, "Today", is_comparison=True)

    assert set(comp["Order ID"]) == {801}


# ── Custom range: effective-date scoping ─────────────────────────────────────


def test_custom_range_scopes_shipped_by_effective_date(op_state):
    now = now_bd()
    range_day = (now - timedelta(days=1)).date()
    st.session_state["live_custom_range"] = (range_day, range_day)

    orders = [
        # Effective (modified) date inside the range → kept.
        (901, "shipped", now - timedelta(days=1), now - timedelta(days=1), ""),
        # Effective date outside the range → excluded.
        (902, "shipped", now - timedelta(days=3), now - timedelta(days=3), ""),
    ]
    df = build_order_df(orders)

    scoped = filter_shipped_by_slot(df, "Today", is_comparison=False)

    assert set(scoped["Order ID"]) == {901}

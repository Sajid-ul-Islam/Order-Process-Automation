"""Operational metrics rendering: KPI cards, deltas, status breakdown, and goal tracking."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import pandas as pd
import streamlit as st

from src.components.dashboard.svg import _generate_sparkline_svg
from src.processing.column_detection import (
    EMAIL_COL_CANDIDATES,
    ORDER_ID_COL_CANDIDATES,
    PHONE_COL_CANDIDATES,
    pick_column,
)
from src.processing.data_processing import (
    aggregate_data,
    prepare_granular_data,
    safe_coerce_datetime_naive,
)
from src.utils.customer_registry import (
    compute_new_vs_returning_counts,
    get_customer_first_order_date,
    load_customer_registry,
    normalize_phone_key,
)
from src.utils.logging import log_system_event
from src.utils.metric_history import save_shift_snapshot


def render_operational_metrics(
    m_df,
    c_df,
    nav_mode: str,
    dummy_mapping: dict,
    wc_raw_mapping: dict,
    forecast_val: float = 0,
    avg_proc_time: float = 0,
):
    """Render the operational KPI cards and return updated aggregates."""
    if m_df is None:
        m_df = pd.DataFrame()
    if (
        "Category" not in m_df.columns
        or "Product Name" not in m_df.columns
        or "Clean_Product" not in m_df.columns
    ):
        m_df, _ = prepare_granular_data(m_df, wc_raw_mapping)
    if c_df is not None and not c_df.empty:
        if (
            "Category" not in c_df.columns
            or "Product Name" not in c_df.columns
            or "Clean_Product" not in c_df.columns
        ):
            c_df, _ = prepare_granular_data(c_df, wc_raw_mapping)
    else:
        c_df = None

    active_df = m_df
    drill, summ, top, basket = aggregate_data(m_df, dummy_mapping)

    m_qty = m_df["Quantity"].sum() if "Quantity" in m_df.columns else 0
    m_ord = basket["total_orders"] if basket else 0
    m_item_rev = (
        (m_df["Quantity"] * m_df["Item Cost"]).sum()
        if "Quantity" in m_df.columns and "Item Cost" in m_df.columns
        else 0.0
    )

    # ── Robust Gross Revenue, Cashback, and Net Revenue Calculation ──
    # ``prepare_granular_data`` (called above) guarantees ``Cashback Discount``,
    # ``Gross Amount`` and ``Total Amount`` columns already exist on ``m_df`` and
    # ``c_df``, so these are the single source of truth (no secondary derivation).
    m_cashback_disc = (
        float(m_df["Cashback Discount"].sum())
        if "Cashback Discount" in m_df.columns
        else 0.0
    )
    m_gross_rev = (
        float(m_df["Gross Amount"].sum())
        if "Gross Amount" in m_df.columns
        else m_item_rev
    )

    # Net Revenue = Gross Revenue - Cashback/Discount Fees
    m_net_rev = max(0.0, m_gross_rev - m_cashback_disc)

    m_loss_pct = (m_cashback_disc / m_gross_rev * 100) if m_gross_rev > 0 else 0.0
    m_gross_bv = (m_gross_rev / m_ord) if m_ord > 0 else 0.0
    m_net_bv = (m_net_rev / m_ord) if m_ord > 0 else 0.0
    m_cb_per_basket = (m_cashback_disc / m_ord) if m_ord > 0 else 0.0
    m_bv = m_net_bv

    dq_str, dr_str, do_str, db_str = None, None, None, None
    pct_q, pct_r, pct_o, pct_b = None, None, None, None
    prev_q_str, prev_r_str, prev_o_str, prev_b_str = None, None, None, None

    if c_df is not None and not c_df.empty:
        co_q = c_df["Quantity"].sum() if "Quantity" in c_df.columns else 0
        co_item_r = (
            (c_df["Quantity"] * c_df["Item Cost"]).sum()
            if "Quantity" in c_df.columns and "Item Cost" in c_df.columns
            else 0.0
        )
        _, _, _, co_basket = aggregate_data(c_df, dummy_mapping)
        co_o = co_basket["total_orders"] if co_basket else 0

        co_cb = (
            float(c_df["Cashback Discount"].sum())
            if "Cashback Discount" in c_df.columns
            else 0.0
        )
        co_gross = (
            float(c_df["Gross Amount"].sum())
            if "Gross Amount" in c_df.columns
            else co_item_r
        )
        co_net_r = max(0.0, co_gross - co_cb)
        co_b = (co_net_r / co_o) if co_o > 0 else 0.0

        prefix = "Today " if nav_mode == "Prev" else ""
        suffix = "" if nav_mode == "Prev" else " vs Prev"

        dq = m_qty - co_q
        dr = m_net_rev - co_net_r
        d_o = m_ord - co_o
        db = m_net_bv - co_b
        if nav_mode == "Prev":
            dq = co_q - m_qty
            dr = co_net_r - m_net_rev
            d_o = co_o - m_ord
            db = co_b - m_net_bv

        pct_q = ((dq / co_q) * 100) if co_q > 0 else (100.0 if dq > 0 else 0.0 if dq == 0 else -100.0)
        pct_r = ((dr / co_net_r) * 100) if co_net_r > 0 else (100.0 if dr > 0 else 0.0 if dr == 0 else -100.0)
        pct_o = ((d_o / co_o) * 100) if co_o > 0 else (100.0 if d_o > 0 else 0.0 if d_o == 0 else -100.0)
        pct_b = ((db / co_b) * 100) if co_b > 0 else (100.0 if db > 0 else 0.0 if db == 0 else -100.0)

        dq_str = f"{prefix}{dq:+,.0f}{suffix}"
        dr_str = f"{prefix}{'+' if dr >= 0 else '-'}TK {abs(dr):,.0f}{suffix}"
        do_str = f"{prefix}{d_o:+,.0f}{suffix}"
        db_str = f"{prefix}{'+' if db >= 0 else '-'}TK {abs(db):,.0f}{suffix}"

        prev_q_str = f"{co_q:,.0f}"
        prev_r_str = f"TK {co_net_r:,.0f}"
        prev_o_str = f"{co_o:,.0f}"
        prev_b_str = f"TK {int(co_b):,}"

    def format_delta(delta_str, prev_val_str=None, pct_val=None):
        if not delta_str:
            return ""
        is_up = "+" in delta_str
        cls = "delta-up" if is_up else "delta-down"
        arrow = "▲" if is_up else "▼"
        pct_snippet = (
            f" ({pct_val:+.1f}%)"
            if pct_val is not None and not pd.isna(pct_val)
            else ""
        )
        prev_snippet = (
            f' <span class="delta-prev">(Prev: {prev_val_str})</span>'
            if prev_val_str
            else ""
        )
        return f'<div class="metric-delta {cls}">{arrow} {delta_str}{pct_snippet}{prev_snippet}</div>'

    v_qty = f"{m_qty:,.0f}"
    v_rev = f"TK {m_net_rev:,.0f}"
    v_ord = f"{m_ord:,.0f}"
    v_bv = f"TK {int(m_net_bv):,}"

    html_dq = format_delta(dq_str, prev_val_str=prev_q_str, pct_val=pct_q)
    html_dr = format_delta(dr_str, prev_val_str=prev_r_str, pct_val=pct_r)
    html_do = format_delta(do_str, prev_val_str=prev_o_str, pct_val=pct_o)
    html_db = format_delta(db_str, prev_val_str=prev_b_str, pct_val=pct_b)

    # ── "Last Day" Comparison Badges ─────────────────────────────────────
    # Prominent badges showing the previous period's absolute values,
    # placed between the main value and the delta on each KPI card.
    def _last_day_badge(prev_str, color="#64748b"):
        if not prev_str:
            return ""
        return (
            f'<div style="font-size:0.68rem;font-weight:600;color:{color};'
            f'background:rgba(100,116,139,0.08);padding:2px 7px;'
            f'border-radius:4px;margin-top:5px;display:inline-block;'
            f'letter-spacing:0.02em;">'
            f'📅 Last Day: {prev_str}</div>'
        )

    badge_qty = _last_day_badge(prev_q_str)
    badge_rev = _last_day_badge(prev_r_str)
    badge_ord = _last_day_badge(prev_o_str)
    badge_bv = _last_day_badge(prev_b_str)

    extra_metric_label = "Basket Size"
    extra_metric_value = v_bv
    extra_metric_delta = html_db
    extra_metric_icon = "🛍️"

    if nav_mode == "Backlog" and not m_df.empty:
        try:
            m_df["dt_temp"] = pd.to_datetime(
                m_df[wc_raw_mapping["date"]], errors="coerce"
            ).dt.tz_localize(None)
            oldest_t = m_df["dt_temp"].min()
            if oldest_t:
                diff = datetime.now() - oldest_t
                hours = int(diff.total_seconds() / 3600)
                mins = int((diff.total_seconds() % 3600) / 60)
                color = "#ef4444" if hours >= 12 else "#3b82f6"

                extra_metric_label = "Oldest Order"
                extra_metric_value = f"{hours}h {mins}m"
                extra_metric_delta = (
                    '<div class="metric-delta" '
                    f'style="background: rgba(239, 68, 68, 0.1); color: {color};">'
                    "AGING IN QUEUE</div>"
                )
                extra_metric_icon = "⏳"
        except Exception:
            pass

    # ── Last 7-Days KPI Sparkline Extraction ──
    # Initialize all sparkline and customer mix variables to safe defaults
    m_new_cnt, m_ret_cnt = 0, 0
    s_cust, d_cust = "", ""
    s_qty, s_rev, s_ord, s_bv = "", "", "", ""
    d_qty, d_rev, d_ord, d_bv, d_cust = "", "", "", "", ""
    if not m_df.empty and nav_mode != "Backlog":
        try:
            # 1. Fetch the multi-day source DataFrame from session state if available, fallback to m_df
            full_df = (
                st.session_state.get("wc_full_df")
                if st.session_state.get("wc_full_df") is not None
                and not st.session_state.get("wc_full_df").empty
                else (
                    st.session_state.get("granular_df")
                    if st.session_state.get("granular_df") is not None
                    and not st.session_state.get("granular_df").empty
                    else (
                        st.session_state.get("raw_df")
                        if st.session_state.get("raw_df") is not None
                        and not st.session_state.get("raw_df").empty
                        else m_df
                    )
                )
            )

            date_col = (
                "Date"
                if "Date" in full_df.columns
                else wc_raw_mapping.get("date", "Order Date")
            )
            if date_col not in full_df.columns:
                date_col = next(
                    (
                        c
                        for c in ["Order Date", "Date", "Created Date"]
                        if c in full_df.columns
                    ),
                    full_df.columns[0],
                )

            src_df = full_df.copy()
            src_df["_dt"] = safe_coerce_datetime_naive(src_df[date_col])
            src_df = src_df.dropna(subset=["_dt"])

            order_id_col = wc_raw_mapping.get("order_id", "Order ID")
            if order_id_col not in src_df.columns:
                order_id_col = next(
                    (c for c in ["Order ID", "Order Number"] if c in src_df.columns),
                    src_df.columns[0],
                )

            if "Total Amount" in src_df.columns:
                src_df["_rev"] = src_df["Total Amount"]
            elif "Gross Amount" in src_df.columns:
                src_df["_rev"] = src_df["Gross Amount"]
            else:
                src_df["_rev"] = src_df["Quantity"] * src_df["Item Cost"]

            # ── 36-hour hourly sparkline series (orders & products sold per hour) ──
            src_df["_hr"] = src_df["_dt"].dt.floor("h")

            hour_map_qty = {}
            hour_map_rev = {}
            hour_map_ord = {}

            if not src_df.empty:
                for h_key, grp in src_df.groupby("_hr"):
                    hour_map_qty[h_key] = float(grp["Quantity"].sum())
                    hour_map_rev[h_key] = float(grp["_rev"].sum())
                    hour_map_ord[h_key] = float(grp[order_id_col].nunique())

            # Window end = latest data hour (falls back to now), 36h span.
            end_hr = (
                src_df["_hr"].max()
                if not src_df.empty
                else pd.Timestamp.now().floor("h")
            )
            all_36h = pd.date_range(end=end_hr, periods=36, freq="h")

            t_qty_vals = [hour_map_qty.get(h, 0.0) for h in all_36h]
            t_rev_vals = [hour_map_rev.get(h, 0.0) for h in all_36h]
            t_ord_vals = [hour_map_ord.get(h, 0.0) for h in all_36h]
            t_bv_vals = [
                (r / o if o > 0 else 0)
                for r, o in zip(t_rev_vals, t_ord_vals, strict=True)
            ]

            # Trim leading zeros (data collection started recently).
            def _trim_leading_zeros(vals: list[float]) -> list[float]:
                first_nz = next((i for i, v in enumerate(vals) if v > 0), None)
                if first_nz is not None:
                    nz_count = sum(1 for v in vals if v > 0)
                    if nz_count < 2:
                        return []
                    trimmed = vals[first_nz:]
                    if len(trimmed) >= 2:
                        return trimmed
                return []

            t_qty_vals = _trim_leading_zeros(t_qty_vals)
            t_rev_vals = _trim_leading_zeros(t_rev_vals)
            t_ord_vals = _trim_leading_zeros(t_ord_vals)
            t_bv_vals = _trim_leading_zeros(t_bv_vals)

            from src.config.ui_config import CHART_THEMES

            theme_name = st.session_state.get("chart_theme", "✨ Emerald Cyberpunk")
            theme_cfg = CHART_THEMES.get(
                theme_name, CHART_THEMES["✨ Emerald Cyberpunk"]
            )

            s_qty, d_qty = _generate_sparkline_svg(
                t_qty_vals,
                theme_cfg.get("spark_qty", "#06b6d4"),
                prefix="",
                suffix="",
                title="36-hour trend",
            )
            s_rev, d_rev = _generate_sparkline_svg(
                t_rev_vals,
                theme_cfg.get("spark_rev", "#10b981"),
                prefix="৳",
                suffix="",
                title="36-hour trend",
            )
            s_ord, d_ord = _generate_sparkline_svg(
                t_ord_vals,
                theme_cfg.get("spark_ord", "#3b82f6"),
                prefix="",
                suffix="",
                title="36-hour trend",
            )
            s_bv, d_bv = _generate_sparkline_svg(
                t_bv_vals,
                theme_cfg.get("spark_bv", "#f59e0b"),
                prefix="৳",
                suffix="",
                title="36-hour trend",
            )

            # ── New vs Returning Customer Calculation (Lifetime Registry Integrated) ──
            try:
                # NOTE: the authoritative counts come from
                # compute_new_vs_returning_counts() below, which already refreshes
                # BOTH the full 3-bucket registry and the legacy flat registry
                # from full_df. Do NOT call update_customer_registry() here as
                # well — it duplicated the same disk I/O on every render.
                phone_col = pick_column(m_df, PHONE_COL_CANDIDATES)
                email_col = pick_column(m_df, EMAIL_COL_CANDIDATES)
                cust_col = phone_col or email_col

                if cust_col and not full_df.empty:
                    full_dt_col = (
                        "Date"
                        if "Date" in full_df.columns
                        else wc_raw_mapping.get("date", "Order Date")
                    )
                    if full_dt_col not in full_df.columns:
                        full_dt_col = next(
                            (c for c in ["Order Date", "Date"] if c in full_df.columns),
                            full_df.columns[0],
                        )

                    f_df = full_df.copy()
                    f_df["_dt"] = safe_coerce_datetime_naive(f_df[full_dt_col])
                    f_df["_norm_cust"] = f_df[cust_col].apply(normalize_phone_key)
                    f_df = f_df.dropna(subset=["_dt"])
                    f_df = f_df[f_df["_norm_cust"] != ""]

                    if not m_df.empty and cust_col in m_df.columns:
                        # first_order_map is still needed by the 7-day sparkline below.
                        active_dt_col = (
                            "Date"
                            if "Date" in m_df.columns
                            else wc_raw_mapping.get("date", "Order Date")
                        )
                        t_act = m_df.copy()
                        t_act["_dt"] = safe_coerce_datetime_naive(t_act[active_dt_col])
                        t_act["_norm_cust"] = t_act[cust_col].apply(normalize_phone_key)
                        order_id_col = wc_raw_mapping.get("order_id", "Order ID")
                        if order_id_col not in t_act.columns:
                            order_id_col = pick_column(
                                t_act, ORDER_ID_COL_CANDIDATES, t_act.columns[0]
                            )
                        first_order_map = (
                            t_act.dropna(subset=["_dt"])
                            .query("_norm_cust != ''")
                            .groupby("_norm_cust")["_dt"]
                            .min()
                            .to_dict()
                        )

                        # Authoritative new vs returning using the full 3-bucket
                        # registry (email -> phone -> name/city). This is the same
                        # source the Customer Insights panels use, and it correctly
                        # detects returning customers whose earlier order was keyed
                        # by a different identity (e.g. email) than the current one.
                        # The legacy flat-registry + session-window loop below
                        # under-counted returning customers (it only saw phone keys
                        # within the cached window).
                        m_new_cnt, m_ret_cnt = compute_new_vs_returning_counts(
                            m_df, full_df, wc_raw_mapping
                        )

                    # 7-Day % New Customers Sparkline
                    if not f_df.empty:
                        f_df["_day"] = f_df["_dt"].dt.floor("d")
                        order_id_col = wc_raw_mapping.get("order_id", "Order ID")
                        if order_id_col not in f_df.columns:
                            order_id_col = next(
                                (
                                    c
                                    for c in ["Order ID", "Order Number"]
                                    if c in f_df.columns
                                ),
                                f_df.columns[0],
                            )

                        # Read-only lifetime lookup for the 7-day sparkline
                        # (registry refresh itself is owned by
                        # compute_new_vs_returning_counts() above).
                        lifetime_registry = load_customer_registry()

                        day_map_total = defaultdict(int)
                        day_map_new = defaultdict(int)

                        for d_key, d_grp in f_df.groupby("_day"):
                            d_uniq = d_grp.drop_duplicates(subset=[order_id_col])
                            day_map_total[d_key] = len(d_uniq)

                            for _, drow in d_uniq.iterrows():
                                c_id = drow.get("_norm_cust")
                                d_dt = drow.get("_dt")
                                first_dt = first_order_map.get(c_id, d_dt)
                                reg_dt = get_customer_first_order_date(
                                    c_id, lifetime_registry
                                )
                                if reg_dt and (pd.isna(first_dt) or reg_dt < first_dt):
                                    first_dt = reg_dt

                                if pd.isna(first_dt) or first_dt.floor("d") == d_key:
                                    day_map_new[d_key] += 1

                        today_dt = f_df["_day"].max()
                        all_7days = pd.date_range(end=today_dt, periods=7, freq="d")

                        t_new_vals = []
                        t_ret_vals = []
                        for d in all_7days:
                            d_tot = day_map_total.get(d, 0)
                            d_new = day_map_new.get(d, 0)

                            if d == today_dt and (m_new_cnt + m_ret_cnt) > 0:
                                d_tot = m_new_cnt + m_ret_cnt
                                d_new = m_new_cnt

                            d_ret = max(0, d_tot - d_new)

                            pct_new = (d_new / d_tot * 100.0) if d_tot > 0 else 0.0
                            pct_ret = (d_ret / d_tot * 100.0) if d_tot > 0 else 0.0

                            t_new_vals.append(pct_new)
                            t_ret_vals.append(pct_ret)

                        t_new_vals = _trim_leading_zeros(t_new_vals)
                        t_ret_vals = _trim_leading_zeros(t_ret_vals)
                        # Pure-gradient sparkline of the 7-day new-customer trend
                        # (matches the other metric cards' minimal visual style).
                        s_cust, _ = _generate_sparkline_svg(
                            t_new_vals,
                            color="#a855f7",
                            prefix="",
                            suffix="%",
                            title="7-day trend",
                        )
                        d_cust = ""
            except Exception as e:
                log_system_event(
                    "CUSTOMER_MIX_ERROR", f"Failed to compute customer mix: {e}"
                )
        except Exception as e:
            log_system_event("SPARKLINE_ERROR", f"Failed to generate sparklines: {e}")

    # % of unique orders with cashback
    _ord_id_col = next(
        (c for c in ["Order ID", "Order Number"] if c in m_df.columns), None
    )
    if _ord_id_col and m_cashback_disc > 0 and "Cashback Discount" in m_df.columns:
        _uniq = m_df.drop_duplicates(subset=[_ord_id_col])
        _cb_ord_cnt = int((_uniq["Cashback Discount"] > 0).sum())
        _total_ord = max(1, len(_uniq))
    else:
        _cb_ord_cnt = 0
        _total_ord = max(1, int(m_ord))
    m_cb_orders_pct = (_cb_ord_cnt / _total_ord * 100) if _cb_ord_cnt > 0 else 0.0

    order_view_mode = (
        st.session_state.get("live_order_filter", "All Orders")
        if nav_mode == "Today"
        else "All Orders"
    )

    if nav_mode == "Backlog":
        l1 = "Backlog Items"
        l2 = "Backlog Rev"
        l3 = "Backlog Orders"
        icon_l3 = "🛒"
    elif order_view_mode == "Shipped":
        l1 = "Shipped Items"
        l2 = "Shipped Net Revenue"
        l3 = "Shipped Orders"
        icon_l3 = "🚚"
    elif order_view_mode == "Processing":
        l1 = "Processing Items"
        l2 = "Processing Rev"
        l3 = "Processing Orders"
        icon_l3 = "⚙️"
    else:
        l1 = "Gross Items"
        l2 = "Net Realized Revenue"
        l3 = "Orders"
        icon_l3 = "🛒"

    gross_items_card = (
        f'<div class="metric-card"><div class="metric-content"><div class="metric-label">{l1}</div>'
        f'<div class="metric-value">{v_qty}</div>{badge_qty}{html_dq}{s_qty}{d_qty}</div>'
        '<div class="metric-icon">📦</div></div>'
    )

    # Override Basket Size card value with net basket value
    if extra_metric_label == "Basket Size" and m_cashback_disc > 0:
        extra_metric_value = f"TK {int(m_net_bv):,}"

    # One consolidated cashback badge on the Revenue card only (was three
    # separate amber badges spread across cards).
    cb_badge = (
        f'<div style="font-size:0.72rem;color:#f59e0b;font-weight:600;'
        f"background:rgba(245,158,11,0.10);padding:3px 8px;border-radius:4px;"
        f'margin-top:4px;display:inline-block;">'
        f"Gross ৳{int(m_gross_rev):,} · Cashback −৳{int(m_cashback_disc):,} "
        f"({m_cb_orders_pct:.0f}% of orders)</div>"
        if m_cashback_disc > 0
        else ""
    )
    cb_basket_badge = ""
    cb_orders_badge = ""

    tot_cust = m_new_cnt + m_ret_cnt
    pct_new = (m_new_cnt / tot_cust * 100) if tot_cust > 0 else 0
    pct_ret = (m_ret_cnt / tot_cust * 100) if tot_cust > 0 else 0

    v_cust = f"{m_new_cnt} New / {m_ret_cnt} Ret" if tot_cust > 0 else "0 New / 0 Ret"
    cust_badge = (
        f'<div style="font-size:0.75rem;color:#a855f7;font-weight:700;background:rgba(168,85,247,0.12);padding:3px 8px;border-radius:4px;margin-top:4px;display:inline-block;">🆕 {pct_new:.0f}% New || 🔄 {pct_ret:.0f}% Returning</div>'
        if tot_cust > 0
        else ""
    )

    # Previous slot comparison for Customer Mix
    html_dcust = ""
    if c_df is not None and not c_df.empty:
        try:
            full_ref = (
                full_df
                if "full_df" in locals() and full_df is not None and not full_df.empty
                else m_df
            )
            co_new_cnt, co_ret_cnt = compute_new_vs_returning_counts(
                c_df, full_ref, wc_raw_mapping
            )
            co_tot = co_new_cnt + co_ret_cnt
            if co_tot > 0:
                d_new = m_new_cnt - co_new_cnt
                pct_new_change = (
                    ((m_new_cnt - co_new_cnt) / co_new_cnt * 100)
                    if co_new_cnt > 0
                    else (100.0 if m_new_cnt > 0 else 0.0)
                )
                html_dcust = format_delta(
                    f"{d_new:+d} New vs Prev",
                    prev_val_str=f"{co_new_cnt}N / {co_ret_cnt}R",
                    pct_val=pct_new_change,
                )
        except Exception:
            pass

    customer_mix_card = (
        f'<div class="metric-card"><div class="metric-content"><div class="metric-label">Customer Mix</div>'
        f'<div class="metric-value" style="font-size:1.3rem;">{v_cust}</div>{cust_badge}{html_dcust}{s_cust}{d_cust}</div>'
        '<div class="metric-icon">👥</div></div>'
    )

    card_html = (
        '<div class="metric-container metric-container-5">'
        f"{gross_items_card}"
        f'<div class="metric-card"><div class="metric-content"><div class="metric-label">{l2}</div>'
        f'<div class="metric-value">{v_rev}</div>{badge_rev}{cb_badge}{html_dr}{s_rev}{d_rev}</div><div class="metric-icon">৳</div></div>'
        f'<div class="metric-card"><div class="metric-content"><div class="metric-label">{l3}</div>'
        f'<div class="metric-value">{v_ord}</div>{badge_ord}{cb_orders_badge}{html_do}{s_ord}{d_ord}</div><div class="metric-icon">{icon_l3}</div></div>'
        f'<div class="metric-card"><div class="metric-content"><div class="metric-label">{extra_metric_label}</div>'
        f'<div class="metric-value">{extra_metric_value}</div>{badge_bv}{cb_basket_badge}{extra_metric_delta}'
        f"{(s_bv + d_bv) if nav_mode != 'Backlog' else ''}</div>"
        f'<div class="metric-icon">{extra_metric_icon}</div></div>'
        f"{customer_mix_card}"
        "</div>"
    )

    st.markdown(card_html, unsafe_allow_html=True)

    # ── Feature #3: Goal Threshold Alerts ──────────────────────────────────────
    goals = st.session_state.get("shift_goals", {})
    rev_goal = goals.get("revenue", 0)
    ord_goal = goals.get("orders", 0)

    if rev_goal > 0 or ord_goal > 0:
        st.markdown("###### 🎯 Shift Goal Progress")
        g1, g2 = st.columns(2)
        with g1:
            if rev_goal > 0:
                pct = min(m_net_rev / rev_goal, 1.0)
                color = (
                    "#10b981" if pct >= 1.0 else "#f59e0b" if pct >= 0.7 else "#ef4444"
                )
                label = (
                    "✅ Goal Reached!"
                    if pct >= 1.0
                    else f"৳{m_net_rev:,.0f} / ৳{rev_goal:,.0f}"
                )
                st.markdown(
                    f'<div style="margin-bottom:8px;">'
                    f'<span style="font-size:0.72rem;font-weight:700;color:{color};letter-spacing:0.05em;">'
                    f"💰 REVENUE — {label}</span>"
                    f'<div style="background:rgba(255,255,255,0.08);border-radius:6px;height:8px;margin-top:4px;overflow:hidden;">'
                    f'<div style="background:{color};width:{pct * 100:.1f}%;height:100%;border-radius:6px;'
                    f'transition:width 0.6s ease;"></div></div></div>',
                    unsafe_allow_html=True,
                )
        with g2:
            if ord_goal > 0:
                pct_o = min(m_ord / ord_goal, 1.0)
                color_o = (
                    "#10b981"
                    if pct_o >= 1.0
                    else "#f59e0b" if pct_o >= 0.7 else "#ef4444"
                )
                label_o = (
                    "✅ Goal Reached!"
                    if pct_o >= 1.0
                    else f"{m_ord} / {ord_goal} orders"
                )
                st.markdown(
                    f'<div style="margin-bottom:8px;">'
                    f'<span style="font-size:0.72rem;font-weight:700;color:{color_o};letter-spacing:0.05em;">'
                    f"🛒 ORDERS — {label_o}</span>"
                    f'<div style="background:rgba(255,255,255,0.08);border-radius:6px;height:8px;margin-top:4px;overflow:hidden;">'
                    f'<div style="background:{color_o};width:{pct_o * 100:.1f}%;height:100%;border-radius:6px;'
                    f'transition:width 0.6s ease;"></div></div></div>',
                    unsafe_allow_html=True,
                )

    # ── Feature #5: Auto-Save Shift Snapshot ───────────────────────────────────
    # Only save once per render cycle, silently — keyed by data fingerprint
    snap_key = f"{m_net_rev:.0f}_{m_ord}_{m_qty}"
    if st.session_state.get("_last_snap_key") != snap_key and m_ord > 0:
        top_list = []
        if top is not None and not top.empty:
            name_col = (
                "Product Name" if "Product Name" in top.columns else top.columns[0]
            )
            amt_col = "Total Amount" if "Total Amount" in top.columns else None
            for _, row in (
                top.sort_values(amt_col, ascending=False).head(5).iterrows()
                if amt_col
                else []
            ):
                top_list.append(
                    {
                        "name": str(row.get(name_col, "")),
                        "revenue": float(row.get(amt_col, 0)),
                    }
                )
        save_shift_snapshot(
            revenue=float(m_net_rev),
            orders=int(m_ord),
            qty=int(m_qty),
            aov=float(m_bv),
            shift_label=nav_mode,
            top_products=top_list,
        )
        st.session_state["_last_snap_key"] = snap_key

    # Publish Hero Metrics as the single source of truth for downstream widgets
    st.session_state["hero_metrics"] = {
        "gross_rev": float(m_gross_rev),
        "cashback_disc": float(m_cashback_disc),
        "net_rev": float(m_net_rev),
        "orders": int(m_ord),
        "qty": int(m_qty),
        "net_aov": float(m_net_bv),
        "gross_aov": float(m_gross_bv),
        "cb_per_basket": float(m_cb_per_basket),
        "loss_pct": float(m_loss_pct),
        "new_customers": int(m_new_cnt),
        "returning_customers": int(m_ret_cnt),
    }

    return drill, summ, top, basket, active_df


EXCLUDED_STATUSES = [
    "pending",
    "pending payment",
    "cancelled",
    "failed",
    "refunded",
    "trash",
]


def render_revenue_cashback_comparison_section(
    m_df: pd.DataFrame, raw_df: pd.DataFrame | None = None
) -> None:
    """Render a dedicated metric & breakdown section comparing Total Revenue & Basket Size with Cashback / Discounted Fee.

    Args:
        m_df:   The analytics-ready (filtered) DataFrame.
        raw_df: The raw pre-filter DataFrame (before excluded statuses are dropped).
                When provided, excluded order counts and revenue are shown in the comparison.
    """
    if m_df is None or m_df.empty:
        st.info("No active order data for cashback/fee comparison.")
        return

    # Source of truth: reuse the Hero Metrics published by render_operational_metrics
    # so this analysis can never diverge from the KPI cards. Fall back to the granular
    # DataFrame ONLY if the hero metrics are not yet available (e.g. standalone call).
    hero = st.session_state.get("hero_metrics", {}) or {}

    if {"gross_rev", "cashback_disc", "net_rev", "orders"} <= set(hero.keys()):
        gross_rev = float(hero["gross_rev"])
        total_cashback = float(hero["cashback_disc"])
        net_rev = float(hero["net_rev"])
        tot_orders = int(hero["orders"])
    else:
        gross_rev = (
            float(m_df["Gross Amount"].sum())
            if "Gross Amount" in m_df.columns
            else float((m_df["Quantity"] * m_df["Item Cost"]).sum())
        )
        total_cashback = (
            float(m_df["Cashback Discount"].sum())
            if "Cashback Discount" in m_df.columns
            else 0.0
        )
        net_rev = (
            float(m_df["Total Amount"].sum())
            if "Total Amount" in m_df.columns
            else (gross_rev - total_cashback)
        )
        id_col = (
            "Order ID"
            if "Order ID" in m_df.columns
            else "Order Number" if "Order Number" in m_df.columns else None
        )
        tot_orders = len(m_df.drop_duplicates(subset=[id_col])) if id_col else len(m_df)

    pct_rev_lost = (total_cashback / gross_rev * 100) if gross_rev > 0 else 0.0

    # Basket level metrics (per-order values, consistent with KPI "Basket Size")
    net_basket = (net_rev / tot_orders) if tot_orders > 0 else 0.0
    cb_per_basket = (total_cashback / tot_orders) if tot_orders > 0 else 0.0

    # Per-order cashback distribution (used by tier/filler/cashback-orders logic below).
    # Independent of the hero-metrics branch above — always derived from the granular frame.
    cb_orders_mask = (
        (m_df["Cashback Discount"] > 0)
        if "Cashback Discount" in m_df.columns
        else pd.Series(False, index=m_df.index)
    )
    id_col = (
        "Order ID"
        if "Order ID" in m_df.columns
        else "Order Number" if "Order Number" in m_df.columns else None
    )
    if id_col:
        unique_df = m_df.drop_duplicates(subset=[id_col])
        cb_orders_cnt = (
            unique_df[unique_df[id_col].isin(m_df[cb_orders_mask][id_col])][
                id_col
            ].nunique()
            if cb_orders_mask.any()
            else 0
        )
    else:
        cb_orders_cnt = int(cb_orders_mask.sum())

    # ── Excluded Orders (raw_df-based) ───────────────────────────────────────
    excl_orders_cnt = 0
    excl_gross_rev = 0.0
    excl_statuses_found: list[str] = []
    if raw_df is not None and not raw_df.empty:
        raw_status_col = (
            "Order Status"
            if "Order Status" in raw_df.columns
            else "Status" if "Status" in raw_df.columns else None
        )
        if raw_status_col:
            excl_mask = (
                raw_df[raw_status_col].astype(str).str.lower().isin(EXCLUDED_STATUSES)
            )
            excl_df = raw_df[excl_mask]
            raw_id_col = (
                "Order ID"
                if "Order ID" in excl_df.columns
                else "Order Number" if "Order Number" in excl_df.columns else None
            )
            if raw_id_col:
                excl_orders_cnt = excl_df[raw_id_col].nunique()
            else:
                excl_orders_cnt = len(excl_df)
            # Gross revenue of excluded rows (use Gross Amount if available, else Item Cost * Quantity)
            if "Gross Amount" in excl_df.columns:
                excl_gross_rev = float(excl_df["Gross Amount"].sum())
            elif "Item Cost" in excl_df.columns and "Quantity" in excl_df.columns:
                excl_gross_rev = float(
                    (excl_df["Item Cost"] * excl_df["Quantity"]).sum()
                )
            elif "Total Amount" in excl_df.columns:
                excl_gross_rev = float(excl_df["Total Amount"].sum())
            excl_statuses_found = sorted(
                excl_df[raw_status_col].astype(str).str.lower().unique().tolist()
            )

    st.markdown("### ⚖️ Revenue & Basket Size Cashback Impact Analysis")
    st.info(
        f"💡 **Revenue Equation:** Gross Revenue (**TK {gross_rev:,.0f}**) - Cashback/Discount Fees (**TK {total_cashback:,.0f}**) = **Actual Net Revenue (TK {net_rev:,.0f})**"
    )

    # Show excluded orders banner when raw data is provided
    if excl_orders_cnt > 0:
        status_label = ", ".join(f"`{s}`" for s in excl_statuses_found)
        st.warning(
            f"🚫 **Excluded from Analytics:** **{excl_orders_cnt:,} order(s)** · "
            f"Gross Value: **TK {excl_gross_rev:,.0f}** · "
            f"Status: {status_label} — these are intentionally excluded from revenue figures above."
        )

    # Compact summary: the revenue equation box above already carries
    # gross/cashback/net and the hero KPIs carry basket values — the two old
    # 4-column st.metric grids duplicated those numbers eight times.
    c1, c2 = st.columns(2)
    with c1:
        st.metric(
            "🛍️ Net Basket Value",
            f"TK {net_basket:,.0f}",
            delta=f"-TK {cb_per_basket:,.0f} cashback/order",
            delta_color="inverse",
        )
    with c2:
        st.metric(
            "📉 Revenue Lost to Cashback",
            f"{pct_rev_lost:.1f}%",
            delta=f"-TK {total_cashback:,.0f}",
            delta_color="inverse",
        )

    # ── Category Repetition & Cashback Tier Metrics ───────────────────────────
    HIGH_VAL_CODES = {"101", "106", "108", "110"}
    MID_VAL_CODES = {"102"}
    LOW_VAL_CODES = {"105", "107", "109", "TB"}

    def _classify_row_cat(r):
        s = str(r.get("SKU", ""))
        code = s.split("-")[0] if "-" in s else ""
        if code in HIGH_VAL_CODES:
            return "High"
        if code in MID_VAL_CODES:
            return "Mid"
        if code in LOW_VAL_CODES:
            return "Low"
        comb = f"{str(r.get('Item Name', ''))} {str(r.get('Category', ''))}".lower()
        if any(
            kw in comb for kw in ["jeans", "panjabi", "sweatshirt", "trouser", "cargo"]
        ):
            return "High"
        if "shirt" in comb and "t-shirt" not in comb:
            return "Mid"
        return "Low"

    cnt_500_tier = 0
    cnt_700_tier = 0
    high_rep_cnt = 0
    mid_rep_cnt = 0
    low_rep_cnt = 0
    filler_orders_cnt = 0
    filler_dict = defaultdict(lambda: {"count": 0, "costs": [], "cat_type": ""})

    if id_col and cb_orders_cnt > 0:
        cb_df_all = m_df[cb_orders_mask] if cb_orders_mask.any() else m_df.copy()
        for _, grp in cb_df_all.groupby(id_col):
            # Order-level cashback: sum across the order's line items (the store
            # applies cashback as an order-level fee, split per line item by the
            # flattener). Using iloc[0] would only see one item's split and
            # undercount multi-item cashback orders.
            order_cb_amt = 0.0
            if "Cashback Discount" in grp.columns:
                order_cb_amt = float(grp["Cashback Discount"].sum())
            if (
                order_cb_amt == 0
                and "Gross Amount" in grp.columns
                and "Total Amount" in grp.columns
            ):
                order_cb_amt = float(
                    grp["Gross Amount"].sum() - grp["Total Amount"].sum()
                )

            gross_sum = (
                float(grp["Gross Amount"].sum())
                if "Gross Amount" in grp.columns
                else 0.0
            )
            if 400 <= order_cb_amt < 650 or (
                order_cb_amt == 0
                and "Gross Amount" in grp.columns
                and 2300 <= gross_sum < 2900
            ):
                cnt_500_tier += 1
            elif order_cb_amt >= 650 or (
                order_cb_amt == 0
                and "Gross Amount" in grp.columns
                and gross_sum >= 2900
            ):
                cnt_700_tier += 1

            cat_counts = {"High": 0, "Mid": 0, "Low": 0}
            grp_items = []
            for _, row in grp.iterrows():
                c_type = _classify_row_cat(row)
                q = int(row.get("Quantity", 1)) if pd.notna(row.get("Quantity")) else 1
                c_cost = (
                    float(row.get("Item Cost", 0))
                    if pd.notna(row.get("Item Cost"))
                    else 0.0
                )
                p_name = str(row.get("Item Name", row.get("Clean_Product", "")))
                cat_counts[c_type] += q
                grp_items.append(
                    {"name": p_name, "cost": c_cost, "qty": q, "cat_type": c_type}
                )

            if cat_counts["High"] > 1:
                high_rep_cnt += 1
            if cat_counts["Mid"] > 1:
                mid_rep_cnt += 1
            if cat_counts["Low"] > 1:
                low_rep_cnt += 1

            # Detect Filler Item
            tot_grp_cost = sum(it["cost"] * it["qty"] for it in grp_items)
            threshold_val = 2500 if order_cb_amt < 650 else 3000
            sorted_grp = sorted(grp_items, key=lambda x: x["cost"])
            cheapest_it = sorted_grp[0] if sorted_grp else None
            rest_grp_cost = (
                tot_grp_cost - (cheapest_it["cost"] * cheapest_it["qty"])
                if cheapest_it
                else 0
            )

            if (
                cheapest_it
                and rest_grp_cost < threshold_val
                and tot_grp_cost >= threshold_val
            ):
                filler_orders_cnt += 1
                base_name = cheapest_it["name"].split(" - ")[0]
                filler_dict[base_name]["count"] += 1
                filler_dict[base_name]["costs"].append(cheapest_it["cost"])
                filler_dict[base_name]["cat_type"] = cheapest_it["cat_type"]

    pct_500 = (cnt_500_tier / cb_orders_cnt * 100) if cb_orders_cnt > 0 else 0.0
    pct_700 = (cnt_700_tier / cb_orders_cnt * 100) if cb_orders_cnt > 0 else 0.0
    pct_high_rep = (high_rep_cnt / cb_orders_cnt * 100) if cb_orders_cnt > 0 else 0.0
    pct_mid_rep = (mid_rep_cnt / cb_orders_cnt * 100) if cb_orders_cnt > 0 else 0.0
    pct_low_rep = (low_rep_cnt / cb_orders_cnt * 100) if cb_orders_cnt > 0 else 0.0

    st.markdown("##### 🎯 Cashback Tier & Category Repetition Breakdown")
    t1, t2, t3, t4, t5 = st.columns(5)
    with t1:
        st.metric(
            "💰 500 Cashback Tier",
            f"{cnt_500_tier} orders",
            delta=f"{pct_500:.1f}% of cashback orders",
        )
    with t2:
        st.metric(
            "💜 700 Cashback Tier",
            f"{cnt_700_tier} orders",
            delta=f"{pct_700:.1f}% of cashback orders",
        )
    with t3:
        st.metric(
            "👖 High Value Repeat %",
            f"{pct_high_rep:.1f}%",
            delta=f"{high_rep_cnt} orders (Jeans/Panjabi)",
        )
    with t4:
        st.metric(
            "👔 Mid Value Repeat %",
            f"{pct_mid_rep:.1f}%",
            delta=f"{mid_rep_cnt} orders (Shirts)",
        )
    with t5:
        st.metric(
            "👕 Low Value Repeat %",
            f"{pct_low_rep:.1f}%",
            delta=f"{low_rep_cnt} orders (T-Shirts/Acc)",
        )

    # Top Filler Products Breakdown Table
    if filler_dict and cb_orders_cnt > 0:
        pct_filler_total = (
            (filler_orders_cnt / cb_orders_cnt * 100) if cb_orders_cnt > 0 else 0
        )
        st.markdown(
            f"##### 🛒 Top Filler Products Added to Avail Cashback Threshold "
            f"(found in **{filler_orders_cnt}** orders · **{pct_filler_total:.1f}%** of cashback orders)"
        )
        filler_rows = []
        for fname, fdata in sorted(filler_dict.items(), key=lambda x: -x[1]["count"]):
            cnt = fdata["count"]
            pct_f = (cnt / cb_orders_cnt) * 100
            avg_cost = (
                sum(fdata["costs"]) / len(fdata["costs"]) if fdata["costs"] else 0
            )
            filler_rows.append(
                {
                    "Product Base Name": fname,
                    "Category Value": fdata["cat_type"],
                    "Filler Orders Count": cnt,
                    "% of Cashback Orders": f"{pct_f:.1f}%",
                    "Avg Unit Price": f"TK {avg_cost:,.0f}",
                }
            )
        filler_df = pd.DataFrame(filler_rows)
        st.dataframe(filler_df.head(15), use_container_width=True, hide_index=True)

    from src.components.dashboard.dashboard_charts import (
        render_revenue_cashback_comparison_chart,
    )

    render_revenue_cashback_comparison_chart(m_df)

    # Show filtered Cashback / Discount Orders Table
    if cb_orders_cnt > 0:
        with st.expander(
            f"📋 View Orders with Cashback / Discount Applied ({cb_orders_cnt} orders)",
            expanded=False,
        ):
            cb_df = m_df[cb_orders_mask].copy() if cb_orders_mask.any() else m_df.copy()
            show_cols = [
                c
                for c in [
                    "Order ID",
                    "Order Status",
                    "Item Name",
                    "SKU",
                    "Subtotal Cost",
                    "Item Cost",
                    "Cashback Discount",
                    "Gross Amount",
                    "Total Amount",
                    "Coupons",
                ]
                if c in cb_df.columns
            ]
            st.dataframe(cb_df[show_cols].head(100), use_container_width=True)

    # Show excluded orders detail table
    if excl_orders_cnt > 0 and raw_df is not None and not raw_df.empty:
        raw_status_col = (
            "Order Status"
            if "Order Status" in raw_df.columns
            else "Status" if "Status" in raw_df.columns else None
        )
        if raw_status_col:
            excl_mask = (
                raw_df[raw_status_col].astype(str).str.lower().isin(EXCLUDED_STATUSES)
            )
            excl_detail_df = raw_df[excl_mask].copy()
            with st.expander(
                f"🚫 View Excluded Orders ({excl_orders_cnt} orders · TK {excl_gross_rev:,.0f} gross)",
                expanded=False,
            ):
                show_excl_cols = [
                    c
                    for c in [
                        "Order ID",
                        "Order Status",
                        "Item Name",
                        "SKU",
                        "Item Cost",
                        "Quantity",
                        "Gross Amount",
                        "Total Amount",
                        "Cashback Discount",
                    ]
                    if c in excl_detail_df.columns
                ]
                st.caption(
                    "These orders are excluded from all analytics due to their status (pending, cancelled, failed, refunded, etc.)"
                )
                st.dataframe(
                    excl_detail_df[show_excl_cols].head(200), use_container_width=True
                )

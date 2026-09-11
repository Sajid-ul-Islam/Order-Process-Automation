# Live Operational Dashboard - Refactored for Hick's Law Compliance
"""
Phase 2 Refactoring: Breaking down render_live_tab() into focused components.
Follows Hick's Law principles:
1. Single Primary Action per screen
2. Visual Hierarchy with button types
3. Progressive Disclosure for advanced options
4. Contextual Relevance
"""

import pandas as pd
import streamlit as st

from src.components.dashboard.dashboard_metrics import render_operational_metrics
from src.components.dashboard.dashboard_output import render_dashboard_output
from src.components.dashboard.live_components import (
    render_dashboard_banner,
)
from src.components.ui.widgets import render_reset_confirm
from src.config.constants import bd_now, bd_today
from src.processing.column_detection import find_columns
from src.processing.data_processing import (
    aggregate_data,
    apply_order_view,
    apply_order_view_comparison,
    filter_live_dashboard_view,
    filter_shipped_by_slot,
    prepare_granular_data,
)
from src.services.woocommerce.client import load_live_source
from src.utils.logging import log_system_event
from src.utils.safe_ops import safe_render


# KPI cards are rendered once per page run. The data-sync fragment triggers a
# page rerun only when the underlying order fingerprint changes.
def _refresh_core_metrics():
    """Render KPI cards from the latest synchronized dashboard frames.

    Reuses the already-filtered, granular ``live_df_standard`` /
    ``live_cmp_standard`` stashed by ``render_live_tab`` so the cards always
    show the exact same data as the charts beneath them (no second, divergent
    filtering pass). Falls back to recomputing only when the stash is missing.
    """
    nav_mode = st.session_state.get("wc_nav_mode", "Today")
    selected_view = st.session_state.get("live_dashboard_view", "All Orders")
    order_view_mode = st.session_state.get("live_order_filter", "All Orders")

    m_df = st.session_state.get("live_df_standard")
    c_df = st.session_state.get("live_cmp_standard")

    if m_df is None or m_df.empty:
        # Fallback: nothing stashed yet (e.g. very first render before the
        # main pipeline ran) — recompute from session state via the shared helper.
        if nav_mode == "Today":
            raw = st.session_state.get("wc_curr_df")
        elif nav_mode == "Backlog":
            raw = st.session_state.get("wc_backlog_df")
        else:
            raw = st.session_state.get("wc_prev_df")
        if raw is None:
            st.caption("⏳ Waiting for data...")
            return
        m_df = apply_order_view(raw, nav_mode, order_view_mode)
        if m_df is None:
            m_df = pd.DataFrame()
        m_df, _ = prepare_granular_data(
            m_df, find_columns(m_df) if not m_df.empty else {}
        )

    if selected_view not in {"Today", "Today Shipped"}:
        c_df = None
    elif c_df is None or c_df.empty:
        if nav_mode == "Today" and order_view_mode == "Shipped":
            _cmp_raw = _get_day_comparison_source()
        else:
            _cmp_raw = (
                st.session_state.get("wc_prev_df")
                if nav_mode == "Today"
                else st.session_state.get("wc_curr_df")
                if nav_mode in ["Backlog", "Prev"]
                else None
            )
        if (_cmp_raw is None or _cmp_raw.empty) and nav_mode == "Today":
            full_raw = st.session_state.get("wc_full_df")
            if full_raw is not None and not full_raw.empty:
                try:
                    from src.services.woocommerce.client import (
                        _partition_operational_data,
                    )

                    _, df_prev_ext, _, _, _ = _partition_operational_data(full_raw)
                    _cmp_raw = df_prev_ext
                except Exception:
                    pass
        if _cmp_raw is not None and not _cmp_raw.empty:
            _cmp_f = apply_order_view_comparison(_cmp_raw, nav_mode, order_view_mode)
            if _cmp_f is not None and not _cmp_f.empty:
                c_df, _ = prepare_granular_data(
                    _cmp_f, find_columns(_cmp_f) if not _cmp_f.empty else {}
                )

    dummy_mapping = {
        "name": "Product Name",
        "cost": "Item Cost",
        "qty": "Quantity",
        "date": "Date",
        "order_id": "Order ID",
        "phone": "Phone",
        "sku": "SKU",
    }
    wc_raw_mapping = {
        "name": "Item Name",
        "cost": "Item Cost",
        "qty": "Quantity",
        "date": "Order Date",
        "order_id": "Order ID",
        "phone": "Phone (Billing)",
        "sku": "SKU",
    }

    render_operational_metrics(
        m_df,
        c_df,
        nav_mode,
        dummy_mapping,
        wc_raw_mapping,
        forecast_val=0,
        avg_proc_time=0,
    )


def _get_day_comparison_source():
    """Combine live and prior partitions so yesterday covers 00:00–23:59 BD."""
    frames = [
        frame
        for frame in (
            st.session_state.get("wc_curr_df"),
            st.session_state.get("wc_prev_df"),
        )
        if frame is not None and not frame.empty
    ]
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True).drop_duplicates()


def _get_dashboard_source(fallback=None):
    """Combine dashboard partitions so view rules operate on one source."""
    frames = [
        frame
        for frame in (
            st.session_state.get("wc_curr_df"),
            st.session_state.get("wc_prev_df"),
            st.session_state.get("wc_backlog_df"),
        )
        if frame is not None and not frame.empty
    ]
    if not frames:
        return fallback
    return pd.concat(frames, ignore_index=True).drop_duplicates()


# ── Staleness Monitor ────────────────────────────────────────────────────────
# Graphs how often the store's REST API serves cached/older order data by
# charting WC_STALE_DATA detection events (and their retry outcomes) from
# data/feedback/system_logs.json over time.

STALE_EVENT_TYPES = frozenset(
    {
        "WC_STALE_DATA",
        "WC_STALE_RETRY",  # legacy detection event (pre-cache-buster naming)
        "WC_STALE_RETRY_RECOVERED",
        "WC_STALE_RETRY_UNRESOLVED",
        "WC_STALE_RETRY_FAILED",
        "WC_STALE_RENDER",
    }
)


def _load_stale_events():
    """Load staleness events from the system log file into a DataFrame."""
    import json
    import os

    import pandas as pd

    from src.config.constants import FEEDBACK_DIR

    empty_df = pd.DataFrame(columns=["ts", "type", "details"])
    log_path = os.path.join(FEEDBACK_DIR, "system_logs.json")
    if not os.path.exists(log_path):
        return empty_df
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            logs = json.load(f)
        if not isinstance(logs, list):
            return empty_df
    except Exception:
        return empty_df

    rows = [
        {
            "ts": entry.get("timestamp", ""),
            "type": entry.get("type", ""),
            "details": str(entry.get("details", "")),
        }
        for entry in logs
        if isinstance(entry, dict) and entry.get("type") in STALE_EVENT_TYPES
    ]
    if not rows:
        return empty_df

    df = pd.DataFrame(rows)
    from src.processing.data_processing import safe_coerce_datetime_naive

    if "ts" in df.columns:
        df["ts"] = safe_coerce_datetime_naive(df["ts"])
        return df.dropna(subset=["ts"])
    return empty_df


def render_staleness_monitor():
    """Diagnostic panel: how often WooCommerce serves stale order data over time."""
    import pandas as pd
    import plotly.express as px

    df = _load_stale_events()
    # Promoted from a collapsed expander: staleness is the app's primary defense
    # against silently bad WooCommerce data, so it renders as a first-class
    # section with a compact summary header.
    recent = (
        df[df["ts"] >= pd.Timestamp.now().normalize() - pd.Timedelta(days=1)]
        if not df.empty
        else df
    )
    stale_24h = (
        int(recent[recent["type"].isin(["WC_STALE_DATA", "WC_STALE_RETRY"])].shape[0])
        if not recent.empty
        else 0
    )

    st.markdown("#### 🩺 Data Staleness Monitor")
    if stale_24h > 0:
        st.warning(
            f"⚠️ **{stale_24h} stale sync(es) in the last 24h** — order data may have been served "
            "from cache. Check the site's cache/CDN."
        )
    else:
        st.caption("✅ No stale syncs in the last 24 hours.")
    with st.expander("Staleness details & history", expanded=stale_24h > 0):
        st.caption(
            "Tracks when the store's REST API serves cached/stale order data — syncs whose newest order "
            "modification was older than 45 minutes at fetch time. Clear the site's cache/CDN to stop "
            "these windows."
        )
        if df.empty:
            st.info(
                "No staleness events recorded yet. Events appear automatically when a sync returns stale "
                "data (see the 'Possibly stale WooCommerce data' banner)."
            )
            return

        now = pd.Timestamp.now().normalize()
        last7 = df[df["ts"] >= now - pd.Timedelta(days=6)]
        detections = last7[last7["type"].isin(["WC_STALE_DATA", "WC_STALE_RETRY"])]
        recovered = last7[last7["type"] == "WC_STALE_RETRY_RECOVERED"]

        c1, c2, c3 = st.columns(3)
        c1.metric("Stale syncs (7d)", len(detections))
        c2.metric("Recovered via retry (7d)", len(recovered))
        c3.metric(
            "Recovery rate (7d)",
            (
                f"{100 * len(recovered) / len(detections):.0f}%"
                if len(detections)
                else "—"
            ),
        )

        last14 = df[df["ts"] >= now - pd.Timedelta(days=13)]
        detect14 = last14[
            last14["type"].isin(["WC_STALE_DATA", "WC_STALE_RETRY"])
        ].copy()
        if not detect14.empty:
            detect14["date"] = detect14["ts"].dt.date
            daily = detect14.groupby("date").size().reset_index(name="Stale syncs")
            fig = px.bar(
                daily,
                x="date",
                y="Stale syncs",
                title="Stale-data detections per day (last 14 days)",
                labels={"date": "Date", "Stale syncs": "Syncs"},
            )
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(
                fig, use_container_width=True, config={"displayModeBar": False}
            )

        outcomes = last14[
            last14["type"].isin(
                [
                    "WC_STALE_RETRY_RECOVERED",
                    "WC_STALE_RETRY_UNRESOLVED",
                    "WC_STALE_RETRY_FAILED",
                ]
            )
        ].copy()
        if not outcomes.empty:
            outcomes["date"] = outcomes["ts"].dt.date
            outcomes["Outcome"] = outcomes["type"].map(
                {
                    "WC_STALE_RETRY_RECOVERED": "Recovered (cache-buster)",
                    "WC_STALE_RETRY_UNRESOLVED": "Still stale",
                    "WC_STALE_RETRY_FAILED": "Retry failed",
                }
            )
            out_daily = (
                outcomes.groupby(["date", "Outcome"]).size().reset_index(name="Count")
            )
            fig2 = px.bar(
                out_daily,
                x="date",
                y="Count",
                color="Outcome",
                title="Retry outcomes per day (last 14 days)",
                labels={"date": "Date", "Count": "Events"},
                barmode="stack",
            )
            fig2.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
            st.plotly_chart(
                fig2, use_container_width=True, config={"displayModeBar": False}
            )

        st.caption(
            f"Latest event: {df.iloc[-1]['ts']:%Y-%m-%d %H:%M} · {df.iloc[-1]['type']}"
        )


def _render_order_pipeline_summary(df):
    """Show the non-cancelled workload without mixing it into sales KPIs."""
    if df is None or df.empty:
        return

    status_col = (
        "Order Status"
        if "Order Status" in df.columns
        else "Status"
        if "Status" in df.columns
        else None
    )
    if status_col is None:
        return

    order_col = "Order ID" if "Order ID" in df.columns else None
    statuses = df[status_col].astype(str).str.lower().str.strip()

    def count_orders(mask):
        subset = df[mask]
        return int(subset[order_col].nunique()) if order_col else len(subset)

    sales_mask = statuses.isin({"shipped", "completed", "wc-shipped", "wc-completed"})
    processing_mask = statuses.isin({"processing", "process", "wc-processing"})
    held_mask = statuses.isin(
        {
            "on-hold",
            "hold",
            "pending",
            "waiting",
            "wc-on-hold",
            "wc-hold",
            "wc-pending",
            "wc-waiting",
        }
    )
    other_mask = ~(sales_mask | processing_mask | held_mask)

    summary_parts = [
        f"🚚 Actual sales **{count_orders(sales_mask)}**",
        f"⚙️ Processing **{count_orders(processing_mask)}**",
    ]
    held_count = count_orders(held_mask)
    if held_count > 0:
        summary_parts.append(f"⏸ Hold / waiting **{held_count}**")
    other_count = count_orders(other_mask)
    if other_count > 0:
        summary_parts.append(f"Other **{other_count}**")

    st.caption("Operational workload · " + " · ".join(summary_parts))

    with st.expander("View operational orders", expanded=False):
        visible_columns = [
            column
            for column in (
                "Order ID",
                status_col,
                "Full Name (Billing)",
                "Order Date",
                "Order Date Modified",
                "Order Total Amount",
            )
            if column in df.columns
        ]
        workload = df[visible_columns]
        if order_col and order_col in workload.columns:
            workload = workload.drop_duplicates(subset=[order_col])
        st.dataframe(workload, width="stretch", hide_index=True)


def _render_empty_sales_kpis(selected_view="All Orders"):
    """Keep the selected sales headline visible when its result is zero."""
    if selected_view in {"Last Day Shipped", "Last Day"}:
        st.metric("Actual Sales · Last Day", "0 orders")
        st.caption("Actual sale = WooCommerce status `shipped` or `completed` only.")
        return

    previous_df = _get_day_comparison_source()
    previous_df = filter_shipped_by_slot(previous_df, "Today", is_comparison=True)
    if previous_df is None or previous_df.empty:
        previous_orders = 0
    elif "Order ID" in previous_df.columns:
        previous_orders = int(previous_df["Order ID"].nunique())
    else:
        previous_orders = len(previous_df)

    today_col, previous_col = st.columns(2)
    today_col.metric(
        "Actual Sales · Today",
        "0 orders",
        delta=f"{-previous_orders:+d} vs previous day",
    )
    previous_col.metric("Actual Sales · Previous Day", f"{previous_orders:,} orders")
    st.caption("Actual sale = WooCommerce status `shipped` or `completed` only.")


def render_live_tab():
    def _reset_live_state():
        st.session_state.wc_curr_df = None
        st.session_state.wc_prev_df = None
        st.session_state.live_sync_time = None
        st.session_state.wc_view_historical = False
        st.session_state.wc_sync_mode = "Operational Cycle"
        st.session_state.live_dashboard_view = "All Orders"
        st.session_state.wc_nav_mode = "Today"
        st.session_state.live_order_filter = "All Orders"

    render_reset_confirm("Live Dashboard", "live", _reset_live_state)
    st.session_state.manual_tab_active = False

    if "live_dashboard_view" not in st.session_state:
        st.session_state.live_dashboard_view = "All Orders"

    view_state = {
        "All Orders": ("Today", "All Orders"),
        "Today Shipped": ("Today", "Shipped"),
        "Last Day Shipped": ("Prev", "Shipped"),
        "Queue": ("Backlog", "Queue"),
        # Backward-compatible aliases:
        "Today": ("Today", "Shipped"),
        "Last Day": ("Prev", "Shipped"),
    }
    selected_view = st.session_state.get("live_dashboard_view", "All Orders")
    nav_state, order_state = view_state.get(selected_view, view_state["All Orders"])
    st.session_state.wc_nav_mode = nav_state
    st.session_state.live_order_filter = order_state
    today = bd_today()
    st.session_state["live_custom_range"] = (today, today)

    if "wc_nav_mode" not in st.session_state:
        st.session_state.wc_nav_mode = "Today"

    if "live_order_filter" not in st.session_state:
        st.session_state.live_order_filter = "Shipped"

    # Force Operational Cycle in live dashboard
    st.session_state["wc_sync_mode"] = "Operational Cycle"

    # Initialize session state for controls if they don't exist
    if "perf_outlook_view" not in st.session_state:
        st.session_state.perf_outlook_view = "Sub-Category"

    # ── Data Loading & Preparation (Moved to top for early access) ───────────
    try:
        live_res = load_live_source()
        if isinstance(live_res, dict):
            df_live = live_res.get("df_to_return")
            source_name = live_res.get("sync_desc", "WooCommerce_API")
            modified_at = live_res.get("modified_at", "")
        elif isinstance(live_res, (list, tuple)) and len(live_res) == 3:
            df_live, source_name, modified_at = live_res
        else:
            df_live = live_res
            source_name = "WooCommerce_API"
            modified_at = ""

        if source_name == "LOCAL_SNAPSHOT_FALLBACK" or modified_at == "API_OFFLINE":
            st.warning(
                "⚠️ **WooCommerce REST API is currently offline or not responding.** Displaying the last saved sales snapshot. Live updates will resume once connection is restored."
            )

        # ── Stale Data Warning ──────────────────────────────────────────────
        # The store's REST API has been observed serving cached/older order data
        # intermittently (the same query returns different states minutes apart).
        # When the newest order modification in a live sync is much older than
        # now, the dashboard is likely showing a stale snapshot — e.g. missing
        # today's shipped orders — so surface it instead of silently hiding data.
        try:
            import pandas as _pd

            mod_col = (
                "mod_dt_parsed"
                if "mod_dt_parsed" in df_live.columns
                else (
                    "Order Date Modified"
                    if "Order Date Modified" in df_live.columns
                    else None
                )
            )
            if df_live is not None and not df_live.empty and mod_col:
                mods = _pd.to_datetime(
                    df_live[mod_col].astype(str).str.replace("Z", "", regex=False),
                    errors="coerce",
                )
                newest = mods.max()
                if _pd.notnull(newest):
                    now_bd = bd_now().replace(tzinfo=None)
                    age_min = (now_bd - newest).total_seconds() / 60
                    # Only alert during active daytime business hours (> 120m without any order modification)
                    if age_min > 120 and 11 <= now_bd.hour <= 22:
                        st.info(
                            f"ℹ️ **WooCommerce REST API Active:** Last store modification was at **{newest:%Y-%m-%d %H:%M}** ({age_min:.0f} min ago)."
                        )
                        log_system_event(
                            "WC_MOD_INFO",
                            f"newest_mod={newest} age_min={age_min:.0f}",
                        )
        except Exception:
            pass

        # ── New Order Notification Toast ──────────────────────────────────────
        new_cnt = st.session_state.pop("wc_new_order_count", 0)
        if new_cnt > 0:
            tot_today = (
                len(df_live["Order ID"].unique())
                if "Order ID" in df_live.columns
                else len(df_live)
            )
            st.toast(
                f"⚡ **{new_cnt} new WooCommerce order{'s' if new_cnt > 1 else ''} synced** from REST API (Total: {tot_today} orders)",
                icon="🔔",
            )
    except Exception as api_err:
        log_system_event(
            "LIVE_API_ERROR", f"Live sync failed, attempting fallback: {api_err}"
        )
        from src.utils.snapshots import load_sales_snapshot

        df_snap = load_sales_snapshot()

        if df_snap is not None and not df_snap.empty:
            st.warning(
                "⚠️ **WooCommerce REST API is currently offline or not responding.** Displaying the last saved sales snapshot. Live updates will resume once connection is restored."
            )
            df_live = df_snap
            source_name = "LOCAL_SNAPSHOT_FALLBACK"
            modified_at = "OFFLINE_MODE"
            st.session_state.wc_nav_mode = "Offline"
        else:
            log_system_event("LIVE_FILE_ERROR", str(api_err))
            err_str = str(api_err).lower()
            if any(
                kw in err_str
                for kw in ["connection", "timeout", "502", "503", "500", "resolve"]
            ):
                st.error(
                    "🌐 **Connection Error:** Cannot reach WooCommerce. Check your network or server status."
                )
            else:
                st.error(f"⚠️ **Sync Error:** {api_err}")
            st.info(
                "💡 Use **Sales Data Ingestion** to upload a local CSV/Excel export as a fallback."
            )
            return

    # ── Multi-Mode Shift Navigation & Filtering ───────────────────────────────
    nav_mode = st.session_state.get("wc_nav_mode", "Today")
    if nav_mode == "Offline":
        pass
    elif nav_mode == "Prev" and "wc_prev_df" in st.session_state:
        df_live = st.session_state.wc_prev_df
    elif nav_mode == "Backlog" and "wc_backlog_df" in st.session_state:
        df_live = st.session_state.wc_backlog_df
    elif nav_mode == "Today" and "wc_curr_df" in st.session_state:
        df_live = st.session_state.wc_curr_df

    # Prepare granular data early
    df_standard, timeframe = prepare_granular_data(
        df_live, find_columns(df_live) if df_live is not None else {}
    )

    # ── Header: Refactored with Hick's Law Compliance ───────────────────────
    # Single responsibility: delegate to component module
    render_dashboard_banner(load_live_source)

    st.markdown("---")

    selected_view = st.session_state.get("live_dashboard_view", "All Orders")
    nav_mode, order_view_mode = view_state.get(selected_view, view_state["All Orders"])
    df_live = filter_live_dashboard_view(
        _get_dashboard_source(fallback=df_live), selected_view
    )

    if df_live is None or df_live.empty:
        st.warning(f"No data found for the **{nav_mode}** slot.")
        if nav_mode != "Today" and nav_mode != "Offline":
            st.session_state.wc_nav_mode = "Today"
            st.rerun()
        return

    status_col = (
        "Order Status"
        if "Order Status" in df_live.columns
        else "Status"
        if "Status" in df_live.columns
        else None
    )
    if status_col is None and order_view_mode != "All Orders":
        st.warning("⚠️ 'Order Status' column not found — cannot apply filter.")
        return

    if df_live is None or df_live.empty:
        if selected_view in {
            "Today Shipped",
            "Today",
            "Last Day Shipped",
            "Last Day",
        }:
            _render_empty_sales_kpis(selected_view)
        elif selected_view == "Queue":
            st.info("📋 No hold or waiting orders in the queue.")
        else:
            st.info(f"📦 No active orders found in the **{nav_mode}** slot.")
        return

    # ── Column Detection ──────────────────────────────────────────────────────
    auto_cols = find_columns(df_live) if df_live is not None else {}
    live_mapping = {
        "name": auto_cols.get("name"),
        "cost": auto_cols.get("cost"),
        "qty": auto_cols.get("qty"),
        "date": auto_cols.get("date"),
        "order_id": auto_cols.get("order_id"),
        "phone": auto_cols.get("phone"),
    }
    # Re-assign df_standard with the finally filtered df_live
    df_standard, timeframe = prepare_granular_data(df_live, live_mapping)

    # Stash the granular frames so the auto-refresh KPI fragment renders the
    # exact same data as the charts below (no second, divergent filtering pass).
    st.session_state["live_df_standard"] = df_standard
    _cmp_standard = None
    if selected_view in {"Today Shipped", "Today"}:
        _cmp_f = filter_live_dashboard_view(
            _get_dashboard_source(), "Last Day Shipped"
        )
        if _cmp_f is not None and not _cmp_f.empty:
            _cmp_standard, _ = prepare_granular_data(
                _cmp_f, find_columns(_cmp_f) if not _cmp_f.empty else live_mapping
            )
    st.session_state["live_cmp_standard"] = _cmp_standard

    if df_standard.empty:
        st.warning("Data preparation returned empty results.")
        st.dataframe(df_live.head(20), use_container_width=True)
        return

    drill, summ, top, basket = aggregate_data(df_standard, live_mapping)
    if drill is None or summ is None:
        st.warning("Data aggregation failed.")
        st.dataframe(df_standard.head(20), use_container_width=True)
        return

    # ── KPI Cards (30s auto-refresh) ─────────────────────────────────────────
    _refresh_core_metrics()

    # ── Operational Pipeline Summary (for All Orders view) ────────────────────
    if selected_view == "All Orders":
        _render_order_pipeline_summary(df_live)

    # A conditional view selector avoids executing hidden tab content on every
    # Streamlit rerun.
    if hasattr(st, "segmented_control"):
        dashboard_view = st.segmented_control(
            "Dashboard detail",
            ["📋 Today", "🔍 Analysis"],
            default="📋 Today",
            key="live_dashboard_detail_view",
            label_visibility="collapsed",
        )
    else:
        dashboard_view = st.radio(
            "Dashboard detail",
            ["📋 Today", "🔍 Analysis"],
            horizontal=True,
            key="live_dashboard_detail_view_radio",
            label_visibility="collapsed",
        )

    if dashboard_view == "📋 Today":
        # ── Dashboard Output (charts, tables, AI briefing, export) ───────────
        safe_render(
            lambda: render_dashboard_output(
                drill,
                summ,
                top,
                str(timeframe) if timeframe is not None else None,
                basket,
                str(source_name) if source_name is not None else None,
                str(modified_at) if modified_at is not None else None,
                granular_df=df_standard,
                show_core_metrics=False,
            ),
            fallback_msg="Dashboard rendering encountered an error.",
        )

        # ── Dispatch Export (Shipped Only mode only) ─────────────────────────
        if selected_view == "Today":
            _render_dispatch_export()
    else:
        # ── Market Basket & Cross-Selling Intelligence ───────────────────────
        from src.components.dashboard.market_basket_view import (
            render_market_basket_analysis_section,
        )

        render_market_basket_analysis_section(df_standard, raw_df=df_live)

    # ── Staleness monitor stays visible below both tabs ──────────────────────
    render_staleness_monitor()


def _render_dispatch_export():
    """Render today's full dispatch export: shipped + confirmed + waiting orders."""
    import pandas as pd

    raw_df = st.session_state.get("wc_curr_df")
    if raw_df is None or raw_df.empty:
        return

    raw_df = raw_df.copy()

    # Apply Online Only filter if toggle is on
    if st.session_state.get("shipped_online_only", False):
        from src.processing.completed_analytics import (
            classify_order_source,
            detect_source_column,
        )

        source_col = detect_source_column(raw_df)
        raw_df["_order_source"] = raw_df.apply(
            lambda row: classify_order_source(row, source_col), axis=1
        )
        raw_df = raw_df[raw_df["_order_source"] == "Online"]

    from src.processing.data_processing import safe_coerce_datetime_naive

    if "mod_dt_parsed" in raw_df.columns:
        raw_df["mod_dt_parsed"] = safe_coerce_datetime_naive(raw_df["mod_dt_parsed"])
    if "dt_parsed" in raw_df.columns:
        raw_df["dt_parsed"] = safe_coerce_datetime_naive(raw_df["dt_parsed"])

    today_bd = bd_today()

    status_col = (
        "Order Status"
        if "Order Status" in raw_df.columns
        else "Status"
        if "Status" in raw_df.columns
        else None
    )
    if status_col is None:
        return

    from src.processing.data_processing import filter_shipped_by_slot

    shipped_today = filter_shipped_by_slot(
        raw_df, nav_mode="Today", is_comparison=False
    )

    if shipped_today is None or shipped_today.empty:
        return

    keep_cols = [
        c
        for c in [
            "Order ID",
            "Full Name (Billing)",
            "Phone (Billing)",
            status_col,
            "Pathao Consignment ID",
            "mod_dt_parsed",
            "dt_parsed",
            "Shipping Address 1",
            "Shipping City",
        ]
        if c in raw_df.columns
    ]

    def _dedup(df, label):
        if df.empty:
            return pd.DataFrame()
        d = df[keep_cols].drop_duplicates(subset=["Order ID"]).copy()
        d["Export Tag"] = label
        return d

    shipped_dedup = _dedup(shipped_today, "✅ Shipped Today")

    if shipped_dedup.empty:
        return

    export_df = shipped_dedup.copy()

    # Sort chronologically by modification date (most recent dispatches first)
    sort_cols = [c for c in ["mod_dt_parsed", "dt_parsed"] if c in export_df.columns]
    if sort_cols:
        export_df = export_df.sort_values(
            by=sort_cols, ascending=False, na_position="last"
        ).reset_index(drop=True)

    rename_map = {
        "Full Name (Billing)": "Customer",
        "Phone (Billing)": "Phone",
        status_col: "Status",
        "mod_dt_parsed": "Last Modified",
        "dt_parsed": "Order Date",
    }
    export_df = export_df.rename(
        columns={k: v for k, v in rename_map.items() if k in export_df.columns}
    )

    col_order = [
        "Export Tag",
        "Order ID",
        "Customer",
        "Phone",
        "Status",
        "Pathao Consignment ID",
        "Last Modified",
        "Order Date",
        "Shipping Address 1",
        "Shipping City",
    ]
    export_df = export_df[[c for c in col_order if c in export_df.columns]]

    for dt_col in ["Last Modified", "Order Date"]:
        if dt_col in export_df.columns:
            export_df[dt_col] = safe_coerce_datetime_naive(
                export_df[dt_col]
            ).dt.strftime("%Y-%m-%d %I:%M %p")

    st.divider()
    with st.expander(
        f"📋 Dispatch Export — {len(export_df)} Shipped Orders",
        expanded=True,
    ):
        st.caption("Orders shipped during today's shift · one row per Order ID.")

        search_q = st.text_input(
            "🔍 Search by Order ID, Name, or Phone", key="dispatch_export_search"
        ).strip()
        display_df = export_df.copy()
        if search_q:
            mask = (
                display_df["Order ID"]
                .astype(str)
                .str.contains(search_q, case=False, na=False)
                | display_df.get("Customer", pd.Series(dtype=str))
                .astype(str)
                .str.contains(search_q, case=False, na=False)
                | display_df.get("Phone", pd.Series(dtype=str))
                .astype(str)
                .str.contains(search_q, case=False, na=False)
            )
            display_df = display_df[mask]

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Export Tag": st.column_config.TextColumn("Tag", width="small"),
                "Order ID": st.column_config.NumberColumn("Order ID", format="%d"),
                "Customer": st.column_config.TextColumn("Customer"),
                "Phone": st.column_config.TextColumn("Phone"),
                "Status": st.column_config.TextColumn("Status"),
                "Pathao Consignment ID": st.column_config.TextColumn("Consignment ID"),
                "Last Modified": st.column_config.TextColumn("Shipped/Modified At"),
                "Order Date": st.column_config.TextColumn("Order Placed"),
            },
        )

        now_str = bd_now().strftime("%Y%m%d_%H%M")
        st.download_button(
            label=f"⬇️ Download Dispatch List ({len(export_df)} orders) — CSV",
            data=export_df.to_csv(index=False).encode("utf-8"),
            file_name=f"DEEN_Dispatch_{today_bd.strftime('%Y%m%d')}_{now_str}.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
            key="dispatch_export_download",
        )

# Live Operational Dashboard
import pandas as pd
import streamlit as st

from src.components.dashboard.dashboard_metrics import render_operational_metrics
from src.components.dashboard.dashboard_output import render_dashboard_output
from src.components.ui.widgets import render_reset_confirm
from src.config.constants import bd_now, bd_today
from src.processing.column_detection import find_columns
from src.processing.data_processing import (
    aggregate_data,
    apply_order_view,
    apply_order_view_comparison,
    prepare_granular_data,
)
from src.services.woocommerce.client import load_live_source
from src.utils.logging import log_system_event
from src.utils.safe_ops import safe_render

# ── Auto-Sync Fragments ───────────────────────────────────────────────────────
# Two stable module-level fragments — Streamlit keys fragment identity by the
# function object, so they must NOT be created inside a factory per render.
# _sync_60s  → Active + Shipped Only (high-frequency, catches new dispatches) — every 30s
# _sync_180s → All other modes (light background refresh) — every 60s


def _compute_live_data_fingerprint(df):
    """Compute deterministic MD5 fingerprint across Order IDs, Order Statuses, and Modified Dates."""
    if df is None or df.empty:
        return ""
    import hashlib

    status_col = (
        "Order Status"
        if "Order Status" in df.columns
        else "Status" if "Status" in df.columns else None
    )
    mod_col = (
        "mod_dt_parsed"
        if "mod_dt_parsed" in df.columns
        else "Order Date Modified" if "Order Date Modified" in df.columns else None
    )
    oid_col = "Order ID" if "Order ID" in df.columns else None

    cols = [c for c in [oid_col, status_col, mod_col] if c and c in df.columns]
    if cols:
        summary_str = f"{len(df)}_" + df[cols].astype(str).to_string()
        return hashlib.md5(summary_str.encode("utf-8")).hexdigest()
    return str(len(df))


def _check_and_trigger_ui_rerun():
    df_curr = st.session_state.get("wc_curr_df")
    if df_curr is not None and not df_curr.empty:
        new_fp = _compute_live_data_fingerprint(df_curr)
        old_fp = st.session_state.get("_live_dash_data_fingerprint", "")
        st.session_state["_live_dash_data_fingerprint"] = new_fp
        if old_fp and new_fp != old_fp:
            st.rerun()


@st.fragment(run_every=30)
def _sync_60s():
    """30-second background sync used in Shipped-Only / Active mode."""
    try:
        load_live_source(force_refresh=True)
        _check_and_trigger_ui_rerun()
    except Exception:
        pass


@st.fragment(run_every=60)
def _sync_180s():
    """60-second background sync used for all other dashboard modes."""
    try:
        load_live_source(force_refresh=True)
        _check_and_trigger_ui_rerun()
    except Exception:
        pass


# ── Live KPI Fragment (20s auto-refresh) ────────────────────────────────────
@st.fragment(run_every=20)
def _refresh_core_metrics():
    """20-second auto-refresh of KPI cards.

    Reuses the already-filtered, granular ``live_df_standard`` /
    ``live_cmp_standard`` stashed by ``render_live_tab`` so the cards always
    show the exact same data as the charts beneath them (no second, divergent
    filtering pass). Falls back to recomputing only when the stash is missing.
    """
    nav_mode = st.session_state.get("wc_nav_mode", "Today")
    order_view_mode = (
        st.session_state.get("live_order_filter", "All Orders")
        if nav_mode == "Today"
        else "All Orders"
    )

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

    log_path = os.path.join(FEEDBACK_DIR, "system_logs.json")
    if not os.path.exists(log_path):
        return pd.DataFrame(columns=["ts", "type", "details"])
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except Exception:
        return pd.DataFrame(columns=["ts", "type", "details"])

    rows = [
        {
            "ts": entry.get("timestamp", ""),
            "type": entry.get("type", ""),
            "details": str(entry.get("details", "")),
        }
        for entry in logs
        if entry.get("type") in STALE_EVENT_TYPES
    ]
    df = pd.DataFrame(rows)
    from src.processing.data_processing import safe_coerce_datetime_naive

    df["ts"] = safe_coerce_datetime_naive(df["ts"])
    return df.dropna(subset=["ts"])


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


def render_live_tab():
    def _reset_live_state():
        st.session_state.wc_curr_df = None
        st.session_state.wc_prev_df = None
        st.session_state.live_sync_time = None
        st.session_state.wc_view_historical = False
        st.session_state.wc_sync_mode = "Operational Cycle"
        st.session_state.wc_nav_mode = "Today"
        st.session_state.live_order_filter = "All Orders"

    render_reset_confirm("Live Dashboard", "live", _reset_live_state)
    st.session_state.manual_tab_active = False

    if "wc_nav_mode" not in st.session_state:
        st.session_state.wc_nav_mode = "Today"

    if "live_order_filter" not in st.session_state:
        st.session_state.live_order_filter = "All Orders"

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
                    if age_min > 45:
                        st.warning(
                            f"⚠️ **Possibly stale WooCommerce data.** The newest order modification in this sync is "
                            f"**{newest:%Y-%m-%d %H:%M}** ({age_min:.0f} min ago). The store's REST API appears to be "
                            f"serving cached data — orders shipped recently may not show here. Clear the WordPress "
                            f"cache (caching plugin / CDN) for `/wp-json/wc/v3/orders`, or wait for the next sync."
                        )
                        log_system_event(
                            "WC_STALE_RENDER",
                            f"newest_mod={newest} age_min={age_min:.0f}",
                        )
        except Exception:
            pass

        # ── New Order Notification Toast ──────────────────────────────────────
        new_cnt = st.session_state.pop("wc_new_order_count", 0)
        if new_cnt > 0:
            st.toast(
                f"🆕 **{new_cnt} new order{'s' if new_cnt > 1 else ''} detected** since last sync!",
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

    # ── Header: Auto-Sync, Date Range, Refresh button ─────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns([1.1, 2.1, 2.1, 0.7, 1.0, 0.5])

    # Column 2: Date Range Picker
    with c1:
        today_bd = bd_today()
        curr_range = st.session_state.get("live_custom_range", (today_bd, today_bd))

        sel_dates = st.date_input(
            "📅 Date Range",
            value=curr_range,
            max_value=today_bd,
            key="live_date_picker_widget",
            label_visibility="collapsed",
            help="Select custom start and end date range to filter orders.",
        )

        if isinstance(sel_dates, (list, tuple)) and len(sel_dates) == 2:
            new_r = (sel_dates[0], sel_dates[1])
            if st.session_state.get("live_custom_range") != new_r:
                st.session_state["live_custom_range"] = new_r
                st.session_state["wc_sync_start_date"] = sel_dates[0]
                st.session_state["wc_sync_end_date"] = sel_dates[1]
                st.rerun()
        elif isinstance(sel_dates, (list, tuple)) and len(sel_dates) == 1:
            new_r = (sel_dates[0], sel_dates[0])
            if st.session_state.get("live_custom_range") != new_r:
                st.session_state["live_custom_range"] = new_r
                st.session_state["wc_sync_start_date"] = sel_dates[0]
                st.session_state["wc_sync_end_date"] = sel_dates[0]
                st.rerun()

        if curr_range and (curr_range[0] != today_bd or curr_range[1] != today_bd):
            if st.button(
                "❌ Clear Range",
                key="btn_clear_custom_range",
                type="secondary",
                use_container_width=True,
            ):
                st.session_state["live_custom_range"] = (today_bd, today_bd)
                if "wc_sync_start_date" in st.session_state:
                    del st.session_state["wc_sync_start_date"]
                if "wc_sync_end_date" in st.session_state:
                    del st.session_state["wc_sync_end_date"]
                st.rerun()

    # Column 3: (was Cashback toggle — removed; full breakdown lives on the
    # permanent "Analysis" tab now)
    with c4:
        st.empty()

    # Column 4 & 5: Main Dashboard Filters (Op Mode, View, Chart Type)
    with c2:
        st.markdown('<div style="height: 5px;"></div>', unsafe_allow_html=True)
        mode_options = ["Last Day", "Active", "Queue"]
        mode_icons = {"Last Day": "⏳", "Active": "⚡", "Queue": "📥"}
        mode_to_state = {"Last Day": "Prev", "Active": "Today", "Queue": "Backlog"}
        state_to_mode = {v: k for k, v in mode_to_state.items()}
        current_idx = mode_options.index(state_to_mode.get(nav_mode, "Active"))

        if hasattr(st, "pills"):
            selected_mode = st.pills(
                "Op Mode",
                mode_options,
                default=mode_options[current_idx],
                format_func=lambda x: f"{mode_icons.get(x, '')} {x}".strip(),
                key="banner_op_mode_pills",
                label_visibility="collapsed",
            )
            if not selected_mode:
                selected_mode = mode_options[current_idx]
        else:  # Fallback for older Streamlit versions
            selected_mode = st.radio(
                "Op Mode",
                mode_options,
                index=current_idx,
                horizontal=True,
                format_func=lambda x: f"{mode_icons.get(x, '')} {x}".strip(),
                key="banner_op_mode_radio",
                label_visibility="collapsed",
            )

        new_nav = mode_to_state[selected_mode]
        if new_nav != nav_mode:
            st.session_state.wc_nav_mode = new_nav
            st.rerun()

    with c3:
        st.markdown('<div style="height: 5px;"></div>', unsafe_allow_html=True)
        if nav_mode == "Today":
            opts_filter = ["All Orders", "Shipped", "Processing"]
            filter_icons = {"All Orders": "📦", "Shipped": "🚚", "Processing": "⚙️"}
            curr_filter = st.session_state.get("live_order_filter", "All Orders")
            if curr_filter not in opts_filter:
                curr_filter = "All Orders"

            if hasattr(st, "pills"):
                sel_filter = st.pills(
                    "Shift View",
                    opts_filter,
                    default=curr_filter,
                    format_func=lambda x: f"{filter_icons.get(x, '')} {x}".strip(),
                    key="live_order_filter_pills",
                    label_visibility="collapsed",
                )
            else:
                sel_filter = st.radio(
                    "Shift View",
                    opts_filter,
                    index=opts_filter.index(curr_filter),
                    horizontal=True,
                    format_func=lambda x: f"{filter_icons.get(x, '')} {x}".strip(),
                    key="live_order_filter_radio",
                    label_visibility="collapsed",
                )

            if sel_filter and sel_filter != curr_filter:
                st.session_state.live_order_filter = sel_filter
                st.rerun()
        else:
            # Placeholder to maintain layout when not in "Today" mode
            st.markdown('<div style="height: 38px;"></div>', unsafe_allow_html=True)

    # Column 5: Auto-Sync Label
    with c5:
        st.markdown(
            '<div style="height: 5px;"></div>', unsafe_allow_html=True
        )  # Vertical alignment helper
        order_view_mode = (
            st.session_state.get("live_order_filter", "All Orders")
            if nav_mode == "Today"
            else "All Orders"
        )
        if nav_mode == "Today" and order_view_mode == "Shipped":
            _sync_60s()
        else:
            _sync_180s()

    # Column 6: Manual Refresh Button
    with c6:
        st.markdown(
            '<div style="height: 5px;"></div>', unsafe_allow_html=True
        )  # Vertical alignment helper
        if st.button(
            "🔄",
            use_container_width=True,
            key="btn_refresh_newly_shipped",
            type="secondary",
            help="Force a manual data refresh",
        ):
            load_live_source(force_refresh=True)
            st.toast("⚡ Data refreshed!")
            st.rerun()

    # ── Final Data Filtering & Sanity Checks ──────────────────────────────────
    order_view_mode = (
        st.session_state.get("live_order_filter", "All Orders")
        if nav_mode == "Today"
        else "All Orders"
    )

    if df_live is None or df_live.empty:
        st.warning(f"No data found for the **{nav_mode}** slot.")
        if nav_mode != "Today" and nav_mode != "Offline":
            st.session_state.wc_nav_mode = "Today"
            st.rerun()
        return

    # ── Apply Order View Filter (single shared helper) ──────────────────────────
    status_col = (
        "Order Status"
        if "Order Status" in df_live.columns
        else "Status" if "Status" in df_live.columns else None
    )
    if status_col is None and order_view_mode != "All Orders":
        st.warning("⚠️ 'Order Status' column not found — cannot apply filter.")
        return

    df_live = apply_order_view(df_live, nav_mode, order_view_mode)
    if df_live is None or df_live.empty:
        if order_view_mode == "Shipped":
            st.info(f"📦 No shipped orders found in the **{nav_mode}** slot.")
        elif order_view_mode == "Processing":
            st.info(f"📋 No processing orders found in the **{nav_mode}** slot.")
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
    _cmp_raw = (
        st.session_state.get("wc_prev_df")
        if nav_mode == "Today"
        else st.session_state.get("wc_curr_df") if nav_mode == "Backlog" else None
    )
    _cmp_standard = None
    if _cmp_raw is not None and not _cmp_raw.empty:
        _cmp_f = apply_order_view_comparison(_cmp_raw, nav_mode, order_view_mode)
        if _cmp_f is not None and not _cmp_f.empty:
            _cmp_standard, _ = prepare_granular_data(_cmp_f, live_mapping)
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

    # ── Top-level split: shift-speed "Today" vs deep-dive "Analysis" ──────────
    tab_today, tab_analysis = st.tabs(["📋 Today", "🔍 Analysis"])

    with tab_today:
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
        if nav_mode == "Today" and order_view_mode == "Shipped":
            _render_dispatch_export()

    with tab_analysis:
        # ── Revenue vs. Cashback Impact Analysis (always available here) ─────
        from src.components.dashboard.dashboard_metrics import (
            render_revenue_cashback_comparison_section,
        )

        render_revenue_cashback_comparison_section(df_standard, raw_df=df_live)

    # ── Staleness monitor stays visible below both tabs ──────────────────────
    render_staleness_monitor()


def _render_dispatch_export():
    """Render today's full dispatch export: shipped + confirmed + waiting orders."""
    import pandas as pd

    raw_df = st.session_state.get("wc_curr_df")
    if raw_df is None or raw_df.empty:
        return

    raw_df = raw_df.copy()

    from src.processing.data_processing import safe_coerce_datetime_naive

    if "mod_dt_parsed" in raw_df.columns:
        raw_df["mod_dt_parsed"] = safe_coerce_datetime_naive(raw_df["mod_dt_parsed"])
    if "dt_parsed" in raw_df.columns:
        raw_df["dt_parsed"] = safe_coerce_datetime_naive(raw_df["dt_parsed"])

    today_bd = bd_today()

    status_col = (
        "Order Status"
        if "Order Status" in raw_df.columns
        else "Status" if "Status" in raw_df.columns else None
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

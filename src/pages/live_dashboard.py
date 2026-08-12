# Live Operational Dashboard
import streamlit as st
from datetime import datetime, timedelta, timezone

from src.components.ui.widgets import render_reset_confirm
from src.config.constants import SHIPPED_STATUSES
from src.processing.column_detection import find_columns
from src.processing.data_processing import prepare_granular_data, aggregate_data, filter_shipped_by_slot, filter_all_orders_to_slot
from src.components.dashboard.dashboard_output import render_dashboard_output
from src.components.dashboard.dashboard_metrics import render_operational_metrics
from src.services.woocommerce.client import load_live_source
from src.utils.logging import log_system_event
from src.utils.safe_ops import safe_render, safe_filter

# ── Auto-Sync Fragments ───────────────────────────────────────────────────────
# Two stable module-level fragments — Streamlit keys fragment identity by the
# function object, so they must NOT be created inside a factory per render.
# _sync_60s  → Active + Shipped Only (high-frequency, catches new dispatches)
# _sync_180s → All other modes (light background refresh)

def _compute_live_data_fingerprint(df):
    """Compute deterministic MD5 fingerprint across Order IDs, Order Statuses, and Modified Dates."""
    if df is None or df.empty:
        return ""
    import hashlib
    status_col = "Order Status" if "Order Status" in df.columns else "Status" if "Status" in df.columns else None
    mod_col = "mod_dt_parsed" if "mod_dt_parsed" in df.columns else "Order Date Modified" if "Order Date Modified" in df.columns else None
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


@st.fragment(run_every=60)
def _sync_60s():
    """60-second background sync used in Shipped-Only / Active mode."""
    try:
        load_live_source(force_refresh=True)
        _check_and_trigger_ui_rerun()
    except Exception:
        pass
    sync_time = st.session_state.get("live_sync_time")
    if sync_time:
        elapsed = int((datetime.now() - sync_time).total_seconds())
        next_in = max(0, 60 - elapsed)
        st.caption(f"🔄 Auto-sync · 1m · next in **{next_in}s**")


@st.fragment(run_every=180)
def _sync_180s():
    """3-minute background sync used for all other dashboard modes."""
    try:
        load_live_source(force_refresh=True)
        _check_and_trigger_ui_rerun()
    except Exception:
        pass
    sync_time = st.session_state.get("live_sync_time")
    if sync_time:
        elapsed = int((datetime.now() - sync_time).total_seconds())
        next_in = max(0, 180 - elapsed)
        mins, secs = divmod(next_in, 60)
        label = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
        st.caption(f"🔄 Auto-sync · 3m · next in **{label}**")


# ── Live KPI Fragment (30s auto-refresh) ────────────────────────────────────
@st.fragment(run_every=30)
def _refresh_core_metrics():
    """30-second auto-refresh of KPI cards — reads latest from session state."""
    nav_mode = st.session_state.get("wc_nav_mode", "Today")

    if nav_mode == "Today":
        m_df = st.session_state.get("wc_curr_df")
    elif nav_mode == "Backlog":
        m_df = st.session_state.get("wc_backlog_df")
    else:
        m_df = st.session_state.get("wc_prev_df")

    c_df = st.session_state.get("wc_prev_df" if nav_mode == "Today" else "wc_curr_df") if nav_mode != "Backlog" else None

    order_view_mode = st.session_state.get("live_order_filter", "All Orders") if nav_mode == "Today" else "All Orders"
    if order_view_mode == "All Orders" and nav_mode == "Today":
        m_df = filter_all_orders_to_slot(m_df, nav_mode)
        if c_df is not None and not c_df.empty:
            c_df = filter_all_orders_to_slot(c_df, "Prev")
    elif order_view_mode == "Shipped Only":
        from src.processing.data_processing import filter_shipped_by_slot
        m_df = filter_shipped_by_slot(m_df, nav_mode, is_comparison=False)
        if c_df is not None and not c_df.empty:
            c_df = filter_shipped_by_slot(c_df, nav_mode, is_comparison=True)
    elif order_view_mode == "Processing Only":
        if m_df is not None and not m_df.empty:
            status_col_m = "Order Status" if "Order Status" in m_df.columns else "Status" if "Status" in m_df.columns else None
            if status_col_m:
                m_df = m_df[m_df[status_col_m].astype(str).str.lower() == "processing"]
        if c_df is not None and not c_df.empty:
            status_col_c = "Order Status" if "Order Status" in c_df.columns else "Status" if "Status" in c_df.columns else None
            if status_col_c:
                c_df = c_df[c_df[status_col_c].astype(str).str.lower() == "processing"]

    if m_df is None or m_df.empty:
        st.caption("⏳ Waiting for data...")
        return

    dummy_mapping = {"name":"Product Name", "cost":"Item Cost", "qty":"Quantity", "date":"Date", "order_id":"Order ID", "phone":"Phone", "sku":"SKU"}
    wc_raw_mapping = {"name":"Item Name", "cost":"Item Cost", "qty":"Quantity", "date":"Order Date", "order_id":"Order ID", "phone":"Phone (Billing)", "sku":"SKU"}

    render_operational_metrics(
        m_df, c_df, nav_mode, dummy_mapping, wc_raw_mapping,
        forecast_val=0, avg_proc_time=0
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
            st.warning("⚠️ **WooCommerce REST API is currently offline or not responding.** Displaying the last saved sales snapshot. Live updates will resume once connection is restored.")

        # ── New Order Notification Toast ──────────────────────────────────────
        new_cnt = st.session_state.pop("wc_new_order_count", 0)
        if new_cnt > 0:
            st.toast(f"🆕 **{new_cnt} new order{'s' if new_cnt > 1 else ''} detected** since last sync!", icon="🔔")
    except Exception as api_err:
        log_system_event("LIVE_API_ERROR", f"Live sync failed, attempting fallback: {api_err}")
        from src.utils.snapshots import load_sales_snapshot
        df_snap = load_sales_snapshot()

        if df_snap is not None and not df_snap.empty:
            st.warning("⚠️ **WooCommerce REST API is currently offline or not responding.** Displaying the last saved sales snapshot. Live updates will resume once connection is restored.")
            df_live = df_snap
            source_name = "LOCAL_SNAPSHOT_FALLBACK"
            modified_at = "OFFLINE_MODE"
            st.session_state.wc_nav_mode = "Offline"
        else:
            log_system_event("LIVE_FILE_ERROR", str(api_err))
            err_str = str(api_err).lower()
            if any(kw in err_str for kw in ["connection", "timeout", "502", "503", "500", "resolve"]):
                st.error("🌐 **Connection Error:** Cannot reach WooCommerce. Check your network or server status.")
            else:
                st.error(f"⚠️ **Sync Error:** {api_err}")
            st.info("💡 Use **Sales Data Ingestion** to upload a local CSV/Excel export as a fallback.")
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

    # Prepare granular data early to check for cashback
    df_standard, timeframe = prepare_granular_data(df_live, find_columns(df_live) if df_live is not None else {})
    has_cashback = "Cashback Discount" in df_standard.columns and (df_standard["Cashback Discount"] > 0).any()

    # ── Header: Auto-Sync, Date Range, Cashback Toggle, Refresh button ───────
    c1, c2, c3, c4, c5, c6 = st.columns([1.5, 1.8, 1.5, 1.5, 1.5, 0.5])

    # Column 1: Auto-Sync Label & Custom Range Indicator
    with c1:
        # Auto-sync fragment (renders compact caption inline)
        order_view_mode = st.session_state.get("live_order_filter", "All Orders") if nav_mode == "Today" else "All Orders"
        if nav_mode == "Today" and order_view_mode == "Shipped Only":
            _sync_60s()
        else:
            _sync_180s()

        curr_r = st.session_state.get("live_custom_range")
        tz_bd = timezone(timedelta(hours=6))
        today_bd = datetime.now(tz_bd).date()
        if curr_r and (curr_r[0] != today_bd or curr_r[1] != today_bd):
            st.caption(f"🗓️ Custom Range: **{curr_r[0].strftime('%b %d')} – {curr_r[1].strftime('%b %d')}**")
            if st.button("❌ Clear Range", key="btn_clear_custom_range", type="secondary"):
                st.session_state["live_custom_range"] = (today_bd, today_bd)
                if "wc_sync_start_date" in st.session_state:
                    del st.session_state["wc_sync_start_date"]
                if "wc_sync_end_date" in st.session_state:
                    del st.session_state["wc_sync_end_date"]
                st.rerun()

    # Column 2: Date Range Picker
    with c2:
        tz_bd = timezone(timedelta(hours=6))
        today_bd = datetime.now(tz_bd).date()
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

    # Column 3: Operational Mode & Cashback Toggle
    with c3:
        if has_cashback:
            st.markdown('<div style="height: 5px;"></div>', unsafe_allow_html=True) # Vertical alignment helper
            st.toggle(
                "⚖️ Cashback View",
                value=st.session_state.get("live_compare_cashback", False),
                key="live_compare_cashback",
                help="Toggle the Revenue vs Cashback/Fee breakdown section at the bottom of the page."
            )

    # Column 4 & 5: Main Dashboard Filters (Op Mode, View, Chart Type)
    with c4:
        st.markdown('<div style="height: 5px;"></div>', unsafe_allow_html=True)
        mode_options = ["Last Day", "Active", "Queue"]
        mode_icons = {"Last Day": "⏳", "Active": "⚡", "Queue": "📥"}
        mode_to_state = {"Last Day": "Prev", "Active": "Today", "Queue": "Backlog"}
        state_to_mode = {v: k for k, v in mode_to_state.items()}
        current_idx = mode_options.index(state_to_mode.get(nav_mode, "Active"))

        if hasattr(st, "pills"):
            selected_mode = st.pills(
                "Op Mode", mode_options, default=mode_options[current_idx],
                format_func=lambda x: f"{mode_icons.get(x, '')} {x}".strip(),
                key="banner_op_mode_pills", label_visibility="collapsed"
            )
            if not selected_mode: selected_mode = mode_options[current_idx]
        else: # Fallback for older Streamlit versions
            selected_mode = st.radio(
                "Op Mode", mode_options, index=current_idx, horizontal=True,
                format_func=lambda x: f"{mode_icons.get(x, '')} {x}".strip(),
                key="banner_op_mode_radio", label_visibility="collapsed"
            )

        new_nav = mode_to_state[selected_mode]
        if new_nav != nav_mode:
            st.session_state.wc_nav_mode = new_nav
            st.rerun()

    with c5:
        st.markdown('<div style="height: 5px;"></div>', unsafe_allow_html=True)
        if nav_mode == "Today":
            opts_filter = ["All Orders", "Shipped Only", "Processing Only"]
            filter_icons = {"All Orders": "📦", "Shipped Only": "🚚", "Processing Only": "⚙️"}
            curr_filter = st.session_state.get("live_order_filter", "All Orders")
            if curr_filter not in opts_filter: curr_filter = "All Orders"

            if hasattr(st, "pills"):
                sel_filter = st.pills(
                    "Shift View", opts_filter, default=curr_filter,
                    format_func=lambda x: f"{filter_icons.get(x, '')} {x}".strip(),
                    key="live_order_filter_pills", label_visibility="collapsed"
                )
            else:
                sel_filter = st.radio("Shift View", opts_filter, index=opts_filter.index(curr_filter), horizontal=True, format_func=lambda x: f"{filter_icons.get(x, '')} {x}".strip(), key="live_order_filter_radio", label_visibility="collapsed")

            if sel_filter and sel_filter != curr_filter:
                st.session_state.live_order_filter = sel_filter
                st.rerun()
        else:
            # Placeholder to maintain layout when not in "Today" mode
            st.markdown('<div style="height: 38px;"></div>', unsafe_allow_html=True)

    # Column 6: Refresh Button
    with c6:
        st.markdown('<div style="height: 5px;"></div>', unsafe_allow_html=True) # Vertical alignment helper
        if st.button("🔄", use_container_width=True, key="btn_refresh_newly_shipped", type="secondary", help="Force a manual data refresh"):
            load_live_source(force_refresh=True)
            st.toast("⚡ Data refreshed!")
            st.rerun()

    # ── Final Data Filtering & Sanity Checks ──────────────────────────────────
    order_view_mode = st.session_state.get("live_order_filter", "All Orders") if nav_mode == "Today" else "All Orders"

    if df_live is None or df_live.empty:
        st.warning(f"No data found for the **{nav_mode}** slot.")
        if nav_mode != "Today" and nav_mode != "Offline":
            st.session_state.wc_nav_mode = "Today"
            st.rerun()
        return

    # ── Apply Order View Filter ───────────────────────────────────────────────
    status_col = "Order Status" if "Order Status" in df_live.columns else "Status" if "Status" in df_live.columns else None

    if status_col:
        if order_view_mode == "All Orders" and nav_mode == "Today":
            df_live = filter_all_orders_to_slot(df_live, nav_mode)
            if df_live is None or df_live.empty:
                st.info(f"📦 No active orders found in the **{nav_mode}** slot.")
                return
        elif order_view_mode == "Shipped Only":
            df_live = filter_shipped_by_slot(df_live, nav_mode, is_comparison=False)
            if df_live is None or df_live.empty:
                st.info(f"📦 No shipped orders found in the **{nav_mode}** slot.")
                return
        elif order_view_mode == "Processing Only":
            df_live = df_live[df_live[status_col].astype(str).str.lower() == "processing"]
            if df_live is None or df_live.empty:
                st.info(f"📋 No processing orders found in the **{nav_mode}** slot.")
                return
    elif order_view_mode != "All Orders":
        st.warning("⚠️ 'Order Status' column not found — cannot apply filter.")

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

    # ── Dashboard Output (charts, tables, AI briefing, export) ───────────────
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
            show_core_metrics=False
        ),
        fallback_msg="Dashboard rendering encountered an error.",
    )

    # ── Revenue vs. Cashback Impact Analysis ─────────────────────────────────
    if has_cashback and st.session_state.get("live_compare_cashback", False):
        st.divider()
        from src.components.dashboard.dashboard_metrics import render_revenue_cashback_comparison_section
        render_revenue_cashback_comparison_section(df_standard, raw_df=df_live)

    # ── Dispatch Export (Shipped Only mode only) ──────────────────────────────
    if nav_mode == "Today" and order_view_mode == "Shipped Only":
        _render_dispatch_export()


def _render_dispatch_export():
    """Render today's full dispatch export: shipped + confirmed + waiting orders."""
    import pandas as pd
    from datetime import datetime, timedelta, timezone

    raw_df = st.session_state.get("wc_curr_df")
    if raw_df is None or raw_df.empty:
        return

    raw_df = raw_df.copy()

    from src.processing.data_processing import safe_coerce_datetime_naive
    if "mod_dt_parsed" in raw_df.columns:
        raw_df["mod_dt_parsed"] = safe_coerce_datetime_naive(raw_df["mod_dt_parsed"])
    if "dt_parsed" in raw_df.columns:
        raw_df["dt_parsed"] = safe_coerce_datetime_naive(raw_df["dt_parsed"])

    tz_bd = timezone(timedelta(hours=6))
    today_bd = datetime.now(tz_bd).date()

    status_col = "Order Status" if "Order Status" in raw_df.columns else "Status" if "Status" in raw_df.columns else None
    if status_col is None:
        return

    from src.processing.data_processing import filter_shipped_by_slot
    shipped_today = filter_shipped_by_slot(raw_df, nav_mode="Today", is_comparison=False)

    if shipped_today is None or shipped_today.empty:
        return

    keep_cols = [
        c for c in [
            "Order ID", "Full Name (Billing)", "Phone (Billing)",
            status_col, "Pathao Consignment ID", "mod_dt_parsed", "dt_parsed",
            "Shipping Address 1", "Shipping City",
        ] if c in raw_df.columns
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
        export_df = export_df.sort_values(by=sort_cols, ascending=False, na_position="last").reset_index(drop=True)

    rename_map = {
        "Full Name (Billing)": "Customer",
        "Phone (Billing)": "Phone",
        status_col: "Status",
        "mod_dt_parsed": "Last Modified",
        "dt_parsed": "Order Date",
    }
    export_df = export_df.rename(columns={k: v for k, v in rename_map.items() if k in export_df.columns})

    col_order = ["Export Tag", "Order ID", "Customer", "Phone", "Status",
                 "Pathao Consignment ID", "Last Modified", "Order Date",
                 "Shipping Address 1", "Shipping City"]
    export_df = export_df[[c for c in col_order if c in export_df.columns]]

    for dt_col in ["Last Modified", "Order Date"]:
        if dt_col in export_df.columns:
            export_df[dt_col] = safe_coerce_datetime_naive(export_df[dt_col]).dt.strftime("%Y-%m-%d %I:%M %p")

    st.divider()
    with st.expander(
        f"📋 Dispatch Export — {len(export_df)} Shipped Orders",
        expanded=True,
    ):
        st.caption("Orders shipped during today's shift · one row per Order ID.")

        search_q = st.text_input("🔍 Search by Order ID, Name, or Phone", key="dispatch_export_search").strip()
        display_df = export_df.copy()
        if search_q:
            mask = (
                display_df["Order ID"].astype(str).str.contains(search_q, case=False, na=False)
                | display_df.get("Customer", pd.Series(dtype=str)).astype(str).str.contains(search_q, case=False, na=False)
                | display_df.get("Phone", pd.Series(dtype=str)).astype(str).str.contains(search_q, case=False, na=False)
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

        now_str = datetime.now(tz_bd).strftime("%Y%m%d_%H%M")
        st.download_button(
            label=f"⬇️ Download Dispatch List ({len(export_df)} orders) — CSV",
            data=export_df.to_csv(index=False).encode("utf-8"),
            file_name=f"DEEN_Dispatch_{today_bd.strftime('%Y%m%d')}_{now_str}.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
            key="dispatch_export_download",
        )

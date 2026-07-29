import streamlit as st
from datetime import datetime, timedelta, timezone

from src.components.ui.widgets import render_reset_confirm
from src.processing.column_detection import find_columns
from src.processing.data_processing import prepare_granular_data, aggregate_data, filter_shipped_by_slot
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

@st.fragment(run_every=60)
def _sync_60s():
    """60-second background sync used in Shipped-Only / Active mode."""
    try:
        load_live_source(force_refresh=True)
    except Exception:
        pass
    sync_time = st.session_state.get("live_sync_time")
    if sync_time:
        elapsed = int((datetime.now() - sync_time).total_seconds())
        next_in = max(0, 60 - elapsed)
        secs_label = f"{next_in}s"
        st.caption(f"🔄 **Auto-Sync** · every 1m · next in **{secs_label}**")


@st.fragment(run_every=180)
def _sync_180s():
    """3-minute background sync used for all other dashboard modes."""
    try:
        load_live_source()
    except Exception:
        pass
    sync_time = st.session_state.get("live_sync_time")
    if sync_time:
        elapsed = int((datetime.now() - sync_time).total_seconds())
        next_in = max(0, 180 - elapsed)
        mins, secs = divmod(next_in, 60)
        label = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
        st.caption(f"🔄 **Auto-Sync** · every 3m · next in **{label}**")


# ── Live KPI Fragment (30s auto-refresh) ────────────────────────────────────
# Renders the full core metric cards with sparklines, deltas, and goal progress.
# Reads the latest data directly from session state, so it stays fresh even when
# the sync fragments (60s/180s) update the data underneath.

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

    if m_df is None or m_df.empty:
        st.caption("⏳ Waiting for data...")
        return

    dummy_mapping = {"name":"Product Name", "cost":"Item Cost", "qty":"Quantity", "date":"Date", "order_id":"Order ID", "phone":"Phone", "sku":"SKU"}
    wc_raw_mapping = {"name":"Item Name", "cost":"Item Cost", "qty":"Quantity", "date":"Order Date", "order_id":"Order ID", "phone":"Phone (Billing)", "sku":"SKU"}

    st.subheader("Core Metrics")
    render_operational_metrics(
        m_df, c_df, nav_mode, dummy_mapping, wc_raw_mapping,
        forecast_val=0, avg_proc_time=0
    )


def _render_status_summary_strip(df_live, nav_mode):
    """Render a visual metric card bar summarizing current shift status counts."""
    if df_live is None or df_live.empty:
        return

    status_col = "Order Status" if "Order Status" in df_live.columns else "Status" if "Status" in df_live.columns else None
    if not status_col:
        return

    from src.config.constants import SHIPPED_STATUSES

    id_col = "Order ID" if "Order ID" in df_live.columns else None
    if id_col:
        unique_df = df_live.drop_duplicates(subset=[id_col])
        s_lower_uniq = unique_df[status_col].astype(str).str.lower()
        total_orders = len(unique_df)
    else:
        s_lower_uniq = df_live[status_col].astype(str).str.lower()
        total_orders = len(df_live)

    shipped_cnt = s_lower_uniq.isin(SHIPPED_STATUSES).sum()
    processing_cnt = (s_lower_uniq == "processing").sum()
    confirmed_cnt = (s_lower_uniq == "confirmed").sum()
    hold_waiting_cnt = s_lower_uniq.isin(["on-hold", "pending", "waiting"]).sum()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📦 Shift Total Orders", f"{total_orders:,}")
    with col2:
        st.metric("🔵 Processing Queue", f"{processing_cnt:,}")
    with col3:
        st.metric("🟢 Shipped / In-Transit", f"{shipped_cnt + confirmed_cnt:,}", delta=f"{shipped_cnt} shipped" if shipped_cnt else None)
    with col4:
        st.metric("🟡 On-Hold / Pending", f"{hold_waiting_cnt:,}")


def render_live_tab():
    def _reset_live_state():
        st.session_state.wc_curr_df = None
        st.session_state.wc_prev_df = None
        st.session_state.live_sync_time = None
        st.session_state.wc_view_historical = False
        st.session_state.wc_sync_mode = "Operational Cycle"

    render_reset_confirm("Live Dashboard", "live", _reset_live_state)
    st.session_state.manual_tab_active = False # v11.3 Flag Reset

    # Today's active slot remains open through the night shift until 6 AM
    if "live_order_filter" not in st.session_state:
        st.session_state.live_order_filter = "All Orders"

    # Use global imports
    # Force Operational Cycle in live dashboard
    st.session_state["wc_sync_mode"] = "Operational Cycle"

    nav_mode = st.session_state.get("wc_nav_mode", "Today")
    order_view_mode = st.session_state.get("live_order_filter", "All Orders") if nav_mode == "Today" else "All Orders"

    # ── Operational Shift & Auto-Sync Header ──────────────────────────────────
    shift_h = st.session_state.get("shift_cutoff_hour", 18)
    col_hdr1, col_hdr2 = st.columns([3, 1])
    with col_hdr1:
        st.caption(f"🕒 **Operational Shift Cutoff:** {shift_h:02d}:00 BD Time (UTC+6) · **Active Slot:** `{nav_mode}`")
    with col_hdr2:
        if st.button("🔄 Refresh Newly Shipped", use_container_width=True, key="btn_refresh_newly_shipped", type="secondary"):
            load_live_source(force_refresh=True)
            st.toast("⚡ Live WooCommerce data refreshed! Fetched newly shipped orders.")
            st.rerun()

    # ── Auto-Sync: pick the right interval fragment ───────────────────────────
    if nav_mode == "Today" and order_view_mode == "Shipped Only":
        _sync_60s()   # 60s — stays current with newly dispatched orders
    else:
        _sync_180s()  # 3m — lighter refresh for other modes

    # ── Live Data Sync with status progress ──────────────────────────────
    try:
        with st.status("📡 Syncing WooCommerce data...", expanded=True) as sync_status:
            sync_status.write("🔌 Connecting to WooCommerce API...")
            df_live, source_name, modified_at = load_live_source()
            sync_status.write("✅ Data fetched and processed")
            sync_status.update(label="Sync complete", state="complete", expanded=False)
    except Exception as api_err:
        log_system_event("LIVE_API_ERROR", f"Live sync failed, attempting fallback: {api_err}")
        from src.utils.snapshots import load_sales_snapshot
        df_snap = load_sales_snapshot()
        
        if df_snap is not None and not df_snap.empty:
            st.error("📡 **WooCommerce API Unreachable**")
            st.warning("⚠️ **Offline Mode:** Operating on the last locally saved snapshot. Data will not reflect live changes.")
            df_live = df_snap
            source_name = "LOCAL_SNAPSHOT_FALLBACK"
            modified_at = "OFFLINE_MODE"
            st.session_state.wc_nav_mode = "Offline"
        else:
            log_system_event("LIVE_FILE_ERROR", str(api_err))
            err_str = str(api_err).lower()
            if any(kw in err_str for kw in ["connection", "timeout", "502", "503", "500", "resolve"]):
                st.error("🌐 **Connection Error:** Failed to reach WooCommerce. The server is currently unreachable or experiencing high traffic.")
            else:
                st.error(f"⚠️ **Live Sync Error:** {api_err}")
            st.info("💡 **Fallback Mode:** Use the '📥 Sales Data Ingestion' tab to upload a local CSV/Excel export until the live connection is restored.")
            return

    # Handle v9.5 Multi-Mode Shift Navigation
    nav_mode = st.session_state.get("wc_nav_mode", "Today")
    if nav_mode == "Offline":
        pass # Bypass slot navigation, just use the fallback snapshot df
    elif nav_mode == "Prev" and "wc_prev_df" in st.session_state:
        df_live = st.session_state.wc_prev_df
        p_s, p_e = st.session_state.get("wc_prev_slot", (datetime.now(), datetime.now()))
        source_name = f"PREV_SLOT_{p_s.strftime('%a_%d%b')}"
        modified_at = "HISTORICAL_SNAPSHOT"
    elif nav_mode == "Backlog" and "wc_backlog_df" in st.session_state:
        df_live = st.session_state.wc_backlog_df
        b_s, b_e = st.session_state.get("wc_backlog_slot", (datetime.now(), datetime.now()))
        source_name = f"INCOMING_BATCH_{b_s.strftime('%H:%M')}"
        modified_at = "BACKLOG_QUEUE"
    elif nav_mode == "Today" and "wc_curr_df" in st.session_state:
        df_live = st.session_state.wc_curr_df
        # default df_live from load_live_source is already the current one

    if df_live is None or df_live.empty:
        st.warning(f"No data found for the {nav_mode} slot.")
        # Fallback to Today if we were in another mode
        if nav_mode != "Today" and nav_mode != "Offline":
            st.session_state.wc_nav_mode = "Today"
            st.rerun()
        return

    # Apply Workspace Sub-Filters
    status_col = "Order Status" if "Order Status" in df_live.columns else "Status" if "Status" in df_live.columns else None

    # ── Debug Diagnostics Expander ───────────────────────────────────────────
    with st.expander("🔍 Debug: Live Data Diagnostics", expanded=False):
        import pandas as pd
        from src.config.constants import SHIPPED_STATUSES
        st.write(f"**Nav mode:** `{nav_mode}` | **View mode:** `{order_view_mode}` | **Total rows:** `{len(df_live)}`")
        if status_col and not df_live.empty:
            status_counts = df_live[status_col].astype(str).value_counts()
            st.write("**Order Status counts in current data:**")
            st.dataframe(status_counts.reset_index().rename(columns={"index": "Status", "count": "Count"}))
            shipped_mask = df_live[status_col].astype(str).str.lower().isin(SHIPPED_STATUSES)
            st.write(f"**Shipped rows (case-insensitive):** `{shipped_mask.sum()}`")
            st.write(f"**SHIPPED_STATUSES list:** `{SHIPPED_STATUSES}`")
            if "mod_dt_parsed" in df_live.columns:
                mod_col = pd.to_datetime(df_live["mod_dt_parsed"], errors="coerce")
                st.write(f"**mod_dt_parsed range:** `{mod_col.min()}` → `{mod_col.max()}` (NaT: `{mod_col.isna().sum()}`)")
            if "dt_parsed" in df_live.columns:
                dt_col = pd.to_datetime(df_live["dt_parsed"], errors="coerce")
                st.write(f"**dt_parsed range:** `{dt_col.min()}` → `{dt_col.max()}`")
            st.write(f"**wc_curr_slot:** `{st.session_state.get('wc_curr_slot')}` | **wc_prev_slot:** `{st.session_state.get('wc_prev_slot')}`")
        else:
            st.warning("df_live is empty or has no status column.")
    # ── End Debug ────────────────────────────────────────────────────────────

    if status_col:
        if order_view_mode == "Shipped Only":
            df_live = filter_shipped_by_slot(df_live, nav_mode, is_comparison=False)
            if df_live is None or df_live.empty:
                st.info(f"📦 No shipped orders found in the {nav_mode} slot.")
                return
        elif order_view_mode == "Processing Only":
            df_live = df_live[df_live[status_col].astype(str).str.lower() == "processing"]
            if df_live is None or df_live.empty:
                st.info(f"📋 No processing orders found in the {nav_mode} slot.")
                return
    elif order_view_mode != "All Orders":
        st.warning("⚠️ 'Order Status' column not found in data. Cannot apply filter.")

    try:
        auto_cols = find_columns(df_live)
    except Exception as col_err:
        log_system_event("LIVE_COLUMN_DETECT_ERROR", str(col_err))
        st.error(f"Column detection failed: {col_err}")
        st.dataframe(df_live.head(20), use_container_width=True)
        return

    missing_required = [k for k in ["name", "cost", "qty"] if k not in auto_cols]
    if missing_required:
        st.error(f"Cannot auto-map required columns: {', '.join(missing_required)}")
        st.dataframe(df_live.head(20), use_container_width=True)
        return

    live_mapping = {
        "name": auto_cols.get("name"),
        "cost": auto_cols.get("cost"),
        "qty": auto_cols.get("qty"),
        "date": auto_cols.get("date"),
        "order_id": auto_cols.get("order_id"),
        "phone": auto_cols.get("phone"),
    }

    df_standard, timeframe = prepare_granular_data(df_live, live_mapping)
    if df_standard.empty:
        st.warning("Data preparation returned empty results. Raw data shown below.")
        st.dataframe(df_live.head(20), use_container_width=True)
        return

    drill, summ, top, basket = aggregate_data(df_standard, live_mapping)
    if drill is None or summ is None:
        st.warning("Data aggregation failed. Raw data shown below.")
        st.dataframe(df_standard.head(20), use_container_width=True)
        return

    # ── Auto-refreshing Core Metrics (30s) ──────────────────────────────────
    _refresh_core_metrics()

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

    # ── Dispatch Export (Shipped Only / Active mode only) ─────────────────────
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

    # Ensure mod_dt_parsed is datetime
    if "mod_dt_parsed" in raw_df.columns:
        raw_df["mod_dt_parsed"] = pd.to_datetime(raw_df["mod_dt_parsed"], errors="coerce")
    if "dt_parsed" in raw_df.columns:
        raw_df["dt_parsed"] = pd.to_datetime(raw_df["dt_parsed"], errors="coerce")

    tz_bd = timezone(timedelta(hours=6))
    today_bd = datetime.now(tz_bd).date()

    status_col = "Order Status" if "Order Status" in raw_df.columns else "Status" if "Status" in raw_df.columns else None
    if status_col is None:
        return

    from src.config.constants import SHIPPED_STATUSES

    # ── 1. Shipped today (mod_dt_parsed date == today) ───────────────────────
    is_shipped = raw_df[status_col].astype(str).str.lower().isin(SHIPPED_STATUSES)
    shipped_today = raw_df[
        is_shipped & (raw_df["mod_dt_parsed"].dt.date == today_bd)
    ]

    # ── 2. Confirmed orders (in-transit / ready for dispatch) ────────────────
    confirmed_df = raw_df[raw_df[status_col].astype(str).str.lower() == "confirmed"]

    # ── 3. Waiting orders placed today ───────────────────────────────────────
    waiting_df = raw_df[
        (raw_df[status_col].astype(str).str.lower() == "waiting") &
        (raw_df["dt_parsed"].dt.date == today_bd)
    ]

    # ── Build unified export table (one row per Order ID) ────────────────────
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
        d = df[keep_cols].drop_duplicates(subset=["Order ID"])
        d = d.copy()
        d["Export Tag"] = label
        return d

    parts = []
    shipped_dedup = _dedup(shipped_today, "✅ Shipped Today")
    confirmed_dedup = _dedup(confirmed_df, "🚚 Confirmed")
    waiting_dedup = _dedup(waiting_df, "⏳ Waiting (today)")

    if not shipped_dedup.empty:
        parts.append(shipped_dedup)
    if not confirmed_dedup.empty:
        # Exclude orders already captured as shipped
        confirmed_dedup = confirmed_dedup[~confirmed_dedup["Order ID"].isin(shipped_dedup["Order ID"])]
        if not confirmed_dedup.empty:
            parts.append(confirmed_dedup)
    if not waiting_dedup.empty:
        already_seen = set()
        if not shipped_dedup.empty:
            already_seen |= set(shipped_dedup["Order ID"])
        if not confirmed_dedup.empty:
            already_seen |= set(confirmed_dedup["Order ID"])
        waiting_dedup = waiting_dedup[~waiting_dedup["Order ID"].isin(already_seen)]
        if not waiting_dedup.empty:
            parts.append(waiting_dedup)

    if not parts:
        return

    export_df = pd.concat(parts, ignore_index=True)

    # Rename for readability
    rename_map = {
        "Full Name (Billing)": "Customer",
        "Phone (Billing)": "Phone",
        status_col: "Status",
        "mod_dt_parsed": "Last Modified",
        "dt_parsed": "Order Date",
    }
    export_df = export_df.rename(columns={k: v for k, v in rename_map.items() if k in export_df.columns})

    # Reorder: Export Tag first, then Order ID, then rest
    col_order = ["Export Tag", "Order ID", "Customer", "Phone", "Status",
                 "Pathao Consignment ID", "Last Modified", "Order Date",
                 "Shipping Address 1", "Shipping City"]
    export_df = export_df[[c for c in col_order if c in export_df.columns]]

    # Format datetimes for display
    for dt_col in ["Last Modified", "Order Date"]:
        if dt_col in export_df.columns:
            export_df[dt_col] = pd.to_datetime(export_df[dt_col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M")

    # ── Render ────────────────────────────────────────────────────────────────
    st.divider()
    with st.expander(
        f"📋 Dispatch Export — {len(export_df)} Orders "
        f"({len(shipped_dedup)} shipped · {len(confirmed_dedup) if not confirmed_dedup.empty else 0} confirmed · "
        f"{len(waiting_dedup) if not waiting_dedup.empty else 0} waiting)",
        expanded=True,
    ):
        st.caption(
            "All orders shipped today + confirmed (in-transit) + today's waiting orders. "
            "One row per Order ID — deduplicated."
        )

        # Search filter
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

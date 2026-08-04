import os
import base64
import streamlit as st


from datetime import datetime, timedelta
from src.components.ui.clock import get_clock_html


def render_header(right_slot_callback=None):
    """Modern command-center header with exact user-requested styling."""
    st.markdown(
        f"""
        <div style="display: flex; align-items: baseline; gap: 12px; margin-bottom: 0px; justify-content: space-between; width: 100%;">
            <h1 class="hub-title" id="deen-ops-terminal-v10-0" aria-labelledby=":r9:" style="margin: 0px;">
                <span id=":r9:">DEEN OPS Terminal <span style="color: rgb(29, 78, 216);">v10.0</span></span>
            </h1>
        </div>
        <p style="color: var(--text-muted); margin-bottom: -10px; font-size: 1rem;">Operational Command & Business Intelligence Center</p>
        """,
        unsafe_allow_html=True
    )
    if right_slot_callback:
        with st.container():
            right_slot_callback()


def render_app_banner():
    """Renders a premium visual banner for the application with integrated clock, title, and sync status."""
    banner_path = os.path.join("assets", "app_banner.png")
    clock_html = get_clock_html()
    
    sync_label = "Checking status..."
    if st.session_state.get("live_sync_time"):
        diff = datetime.now() - st.session_state.live_sync_time
        mins = int(diff.total_seconds() / 60)
        sync_label = "Synced: Just now" if mins < 1 else f"Synced: {mins}m ago"
    elif st.session_state.get("wc_sync_mode") == "Operational Cycle":
         sync_label = "Syncing with WooCommerce..."

    # v15.0: Dynamic Holiday Awareness Logic
    holiday_banner_html = ""
    is_holiday_merge = False
    
    # Check if we are in Operational Cycle and if a merge is active
    if st.session_state.get("wc_sync_mode") == "Operational Cycle":
        curr_slot = st.session_state.get("wc_curr_slot")
        if curr_slot and len(curr_slot) == 2:
            start, end = curr_slot
            # If the duration is more than 28 hours, it's likely a holiday merge (normal shift is ~24h)
            if (end - start).total_seconds() > 100800: # 28 hours
                is_holiday_merge = True
                merge_date = (start + timedelta(hours=12)).strftime("%a, %d %b")
                holiday_banner_html = f"""
                    <div style="position: absolute; top: 15px; left: 40px; z-index: 10; display: flex; align-items: center; gap: 8px; background: rgba(59, 130, 246, 0.2); backdrop-filter: blur(10px); padding: 6px 14px; border-radius: 20px; border: 1px solid rgba(59, 130, 246, 0.4); animation: pulse 2s infinite;">
                        <span style="font-size: 0.9rem;">🌙</span>
                        <span style="color: #60a5fa; font-size: 0.75rem; font-weight: 800; letter-spacing: 0.05em; text-transform: uppercase;">Holiday Merge Active</span>
                        <span style="color: white; font-size: 0.7rem; font-weight: 600;">(Incl. {merge_date})</span>
                    </div>
                """

    from src.config.ui_config import get_active_theme_config
    theme_cfg = get_active_theme_config()
    p_color = theme_cfg.get("primary", "#10b981")
    s_color = theme_cfg.get("secondary", "#06b6d4")

    img_html = ""
    if os.path.exists(banner_path):
        try:
            with open(banner_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
                img_html = f'<img src="data:image/png;base64,{b64}" class="app-banner-img" style="width: 100%; height: 100%; object-fit: cover; position: absolute; top: 0; left: 0; z-index: 1; opacity: 0.35;">'
        except Exception:
            pass

    st.markdown(
        f"""
        <div class="app-banner-wrapper" style="
            position: relative;
            width: 100%;
            height: 110px;
            border-radius: 16px;
            overflow: hidden;
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.9) 100%);
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 12px 32px -8px rgba(0, 0, 0, 0.5), inset 0 1px 1px rgba(255, 255, 255, 0.1);
            margin-bottom: 16px;
        ">
            {img_html}
            <div style="position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, {p_color}, {s_color}); z-index: 5;"></div>
            {holiday_banner_html}
            <div class="app-banner-overlay" style="
                position: relative;
                z-index: 3;
                display: flex;
                align-items: center;
                justify-content: space-between;
                height: 100%;
                padding: 0 28px;
                background: radial-gradient(circle at 10% 50%, rgba(16, 185, 129, 0.08) 0%, transparent 60%);
            ">
                <div class="app-banner-title-area">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-size: 1.55rem; font-weight: 900; letter-spacing: 0.08em; background: linear-gradient(90deg, #ffffff 0%, {p_color} 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">DEEN-OPS Terminal</span>
                        <span style="background: rgba(16, 185, 129, 0.15); color: {p_color}; font-size: 0.65rem; font-weight: 800; padding: 2px 8px; border-radius: 12px; border: 1px solid rgba(16, 185, 129, 0.3); text-transform: uppercase; letter-spacing: 0.05em;">v10.0 LIVE</span>
                    </div>
                    <div style="color: rgba(226, 232, 240, 0.75); font-size: 0.85rem; font-weight: 500; margin-top: 4px; letter-spacing: 0.02em;">Advanced Operational Command & Strategic Business Intelligence</div>
                </div>
                <div class="app-banner-clock-area" style="text-align: right;">
                    {clock_html}
                    <div style="margin-top: 4px; color: {p_color}; font-size: 0.72rem; font-family: monospace; letter-spacing: 0.08em; font-weight: 700;">🟢 {sync_label.upper()}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_banner_mode_controls():
    """Renders operational mode segmented controls at the bottom-left of the banner area."""
    nav_mode = st.session_state.get("wc_nav_mode", "Today")
    mode_options = ["Last Day", "Active", "Queue"]
    mode_icons = {"Last Day": "⏳", "Active": "⚡", "Queue": "📥"}
    mode_to_state = {"Last Day": "Prev", "Active": "Today", "Queue": "Backlog"}
    state_to_mode = {v: k for k, v in mode_to_state.items()}
    current_idx = mode_options.index(state_to_mode.get(nav_mode, "Active"))

    # Use native segmented controls if available (Streamlit 1.36+), fallback to radio
    has_segmented = hasattr(st, "segmented_control")

    with st.container():
        st.markdown('<div class="banner-controls-margin"></div>', unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns([1, 1.5, 1])
        with c1:
            st.markdown('<span class="align-left-helper"></span>', unsafe_allow_html=True)
            if has_segmented:
                selected_mode = st.segmented_control(
                    "Op Mode",
                    mode_options,
                    default=mode_options[current_idx],
                    format_func=lambda x: f"{mode_icons.get(x, '')} {x}".strip(),
                    key="banner_op_mode_seg",
                    label_visibility="collapsed"
                )
                if not selected_mode:
                    selected_mode = mode_options[current_idx]
            else:
                selected_mode = st.radio(
                    "Op Mode",
                    mode_options,
                    index=current_idx,
                    horizontal=True,
                    format_func=lambda x: f"{mode_icons.get(x, '')} {x}".strip(),
                    key="banner_op_mode_radio",
                    label_visibility="collapsed"
                )
        
        with c2:
            st.markdown('<span class="align-center-helper"></span>', unsafe_allow_html=True)
            if nav_mode == "Today":
                opts_filter = ["All Orders", "Shipped Only", "Processing Only"]
                filter_icons = {"All Orders": "📦", "Shipped Only": "🚚", "Processing Only": "⚙️"}
                curr_filter = st.session_state.get("live_order_filter", "All Orders")
                if curr_filter not in opts_filter: curr_filter = "All Orders"
                    
                if has_segmented:
                    sel_filter = st.segmented_control(
                        "Shift View", opts_filter, default=curr_filter,
                        format_func=lambda x: f"{filter_icons.get(x, '')} {x}".strip(),
                        key="live_order_filter_seg", label_visibility="collapsed"
                    )
                else:
                    sel_filter = st.radio("Shift View", opts_filter, index=opts_filter.index(curr_filter), horizontal=True, format_func=lambda x: f"{filter_icons.get(x, '')} {x}".strip(), key="live_order_filter_radio", label_visibility="collapsed")

                if sel_filter and sel_filter != curr_filter:
                    st.session_state.live_order_filter = sel_filter
                    st.rerun()
                
        with c3:
            st.markdown('<span class="align-right-helper"></span>', unsafe_allow_html=True)
            opts_view = ["Category", "Sub-Category"]
            view_icons = {"Category": "🏷️", "Sub-Category": "📑"}
            curr_view = st.session_state.get("perf_outlook_view", "Sub-Category")
            if curr_view not in opts_view: curr_view = "Sub-Category"
                
            if has_segmented:
                sel_view = st.segmented_control(
                    "Chart View", opts_view, default=curr_view,
                    format_func=lambda x: f"{view_icons.get(x, '')} {x}".strip(),
                    key="perf_outlook_view_seg", label_visibility="collapsed"
                )
            else:
                sel_view = st.radio("Chart View", opts_view, index=opts_view.index(curr_view), horizontal=True, format_func=lambda x: f"{view_icons.get(x, '')} {x}".strip(), key="perf_outlook_view_radio", label_visibility="collapsed")

            if sel_view and sel_view != curr_view:
                st.session_state.perf_outlook_view = sel_view
                st.rerun()

    new_nav = mode_to_state[selected_mode]
    if new_nav != nav_mode:
        st.session_state.wc_nav_mode = new_nav
        st.rerun()

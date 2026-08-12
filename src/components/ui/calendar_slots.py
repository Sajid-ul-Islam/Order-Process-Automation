import streamlit as st
from datetime import datetime, date, time, timedelta
from src.state.persistence import save_state
from src.services.woocommerce.client import _is_off_day

# Default shift cutoff: 18:00 (6:00 PM Bangladesh time)
DEFAULT_SHIFT_HOUR = 18
DEFAULT_SHIFT_MINUTE = 0


def get_shift_cutoff_time() -> time:
    """Returns the user-configured shift cutoff time, falling back to 18:00."""
    h = st.session_state.get("shift_cutoff_hour", DEFAULT_SHIFT_HOUR)
    m = st.session_state.get("shift_cutoff_minute", DEFAULT_SHIFT_MINUTE)
    return time(h, m)


def render_operational_slots_calendar():
    """
    Shift Cutoff + Operational Holiday Manager.

    - Friday is permanently off (built-in rule).
    - Manual holidays can be added/removed via date range picker.
    - The slot calculator in client.py automatically walks backwards past
      consecutive off days so reports always compare working day vs working day.
    """
    if "operational_holidays" not in st.session_state:
        st.session_state.operational_holidays = []

    hols: list[str] = st.session_state.operational_holidays
    holiday_set: set[str] = set(hols)

    # ── Shift Cutoff ─────────────────────────────────────────────────────────
    st.markdown("#### ⏰ Shift Cutoff Time")
    st.caption("Orders after this time roll into the NEXT operational shift (BD time).")

    current_hour = st.session_state.get("shift_cutoff_hour", DEFAULT_SHIFT_HOUR)
    current_minute = st.session_state.get("shift_cutoff_minute", DEFAULT_SHIFT_MINUTE)

    col_h, col_m, col_apply = st.columns([2, 2, 2])
    with col_h:
        new_hour = st.number_input(
            "Hour (0–23)",
            min_value=0,
            max_value=23,
            value=current_hour,
            step=1,
            key="shift_cutoff_hour_input",
            label_visibility="collapsed",
            help="Hour in 24h format (BD time)",
        )
        st.caption(f"Hour: **{new_hour:02d}**")
    with col_m:
        new_minute = st.selectbox(
            "Minute",
            options=[0, 15, 30, 45],
            index=[0, 15, 30, 45].index(current_minute) if current_minute in [0, 15, 30, 45] else 0,
            key="shift_cutoff_minute_input",
            label_visibility="collapsed",
            format_func=lambda x: f":{x:02d}",
        )
        st.caption(f"Min: **:{new_minute:02d}**")
    with col_apply:
        st.markdown("<div style='margin-top:4px;'></div>", unsafe_allow_html=True)
        if st.button("✅ Apply", use_container_width=True, key="apply_shift_cutoff"):
            changed = new_hour != current_hour or new_minute != current_minute
            st.session_state.shift_cutoff_hour = new_hour
            st.session_state.shift_cutoff_minute = new_minute
            if changed:
                st.session_state.wc_curr_df = None
                st.session_state.wc_prev_df = None
                save_state()
                st.toast(
                    f"✅ Shift cutoff set to {new_hour:02d}:{new_minute:02d} BD time.",
                    icon="⏰",
                )
                st.rerun()

    active_cutoff = get_shift_cutoff_time()
    st.info(f"Active cutoff: **{active_cutoff.strftime('%I:%M %p')}** BD time")

    st.divider()

    # ── Off-Day Rules ────────────────────────────────────────────────────────
    st.markdown("#### 📅 Off-Day Rules")
    st.markdown(
        "- 🟥 **Friday** — permanent weekly off (built-in, no action needed)\n"
        "- 🟧 **Manual holidays** — mark specific dates below (Eid, public holidays, etc.)\n"
        "\nThe report engine automatically skips consecutive off days when comparing shifts."
    )

    st.divider()

    # ── Manual Holiday Date Range Picker ─────────────────────────────────────
    st.markdown("**Mark / Clear Holiday Dates**")

    selected_range = st.date_input(
        "Select date or range",
        value=(),
        label_visibility="collapsed",
        help="Pick a single date or click start & end to mark a range",
    )

    c1, c2 = st.columns(2)

    def _dates_in_range(start: date, end: date) -> list[str]:
        result, curr = [], start
        while curr <= end:
            result.append(curr.strftime("%Y-%m-%d"))
            curr += timedelta(days=1)
        return result

    if len(selected_range) in (1, 2):
        start = selected_range[0]
        end = selected_range[-1]  # same as start for single pick
        dates_in_sel = _dates_in_range(start, end)

        with c1:
            if st.button("🛑 Mark Holiday", use_container_width=True, type="primary"):
                added = [d for d in dates_in_sel if d not in holiday_set]
                if added:
                    hols.extend(added)
                    st.session_state.operational_holidays = sorted(set(hols))
                    save_state()
                    st.session_state.wc_curr_df = None
                    st.session_state.wc_prev_df = None
                    st.toast(f"✅ Marked {len(added)} day(s) as holiday!")
                    st.rerun()
                else:
                    st.toast("All selected dates are already marked.")

        with c2:
            if st.button("⚪ Clear Holiday", use_container_width=True):
                removed = [d for d in dates_in_sel if d in holiday_set]
                if removed:
                    for d in removed:
                        hols.remove(d)
                    st.session_state.operational_holidays = sorted(hols)
                    save_state()
                    st.session_state.wc_curr_df = None
                    st.session_state.wc_prev_df = None
                    st.toast(f"✅ Cleared {len(removed)} day(s) from holidays!")
                    st.rerun()
                else:
                    st.toast("None of the selected dates were marked as holiday.")
    else:
        with c1:
            st.button("🛑 Mark Holiday", use_container_width=True, type="primary", disabled=True)
        with c2:
            st.button("⚪ Clear Holiday", use_container_width=True, disabled=True)
        st.caption("Pick a date or range above.")

    st.divider()

    # ── Current Holiday List Preview ─────────────────────────────────────────
    today = datetime.now().date()
    upcoming = [h for h in sorted(hols) if datetime.strptime(h, "%Y-%m-%d").date() >= today]
    past = [h for h in sorted(hols, reverse=True) if datetime.strptime(h, "%Y-%m-%d").date() < today]

    if upcoming:
        st.markdown(f"**📌 Upcoming Holidays ({len(upcoming)})**")
        for h in upcoming:
            h_date = datetime.strptime(h, "%Y-%m-%d").date()
            col_d, col_del = st.columns([4, 1])
            with col_d:
                st.markdown(f"🟧 **{h_date.strftime('%a, %d %b %Y')}**")
            with col_del:
                if st.button("✕", key=f"del_{h}", help=f"Remove {h}"):
                    hols.remove(h)
                    st.session_state.operational_holidays = sorted(hols)
                    save_state()
                    st.session_state.wc_curr_df = None
                    st.session_state.wc_prev_df = None
                    st.toast(f"Removed {h}")
                    st.rerun()

    if past:
        with st.expander(f"🗂️ Past Holidays ({len(past)})", expanded=False):
            for h in past:
                h_date = datetime.strptime(h, "%Y-%m-%d").date()
                col_d, col_del = st.columns([4, 1])
                with col_d:
                    st.markdown(f"⬜ {h_date.strftime('%a, %d %b %Y')}")
                with col_del:
                    if st.button("✕", key=f"del_past_{h}", help=f"Remove {h}"):
                        hols.remove(h)
                        st.session_state.operational_holidays = sorted(hols)
                        save_state()
                        st.rerun()

    if not hols:
        st.caption("No manual holidays added yet. Only Fridays are off by default.")

    st.divider()

    st.markdown("**📦 Order Fetch Limit**")
    order_limit_opt = st.selectbox(
        "Fetch Limit",
        ["Last 10", "Last 20", "Custom Order"],
        key="operational_slot_order_limit",
    )
    if order_limit_opt == "Custom Order":
        st.number_input("Custom Order Count", min_value=1, value=50, key="operational_slot_custom_order_count")

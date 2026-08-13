"""Order Processing and Item Description Helper tabs."""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from src.components.ui.dataframe_search import render_dataframe_search
from src.components.ui.status import render_status_toggle
from src.components.ui.widgets import (
    render_file_summary,
    render_reset_confirm,
    render_sticky_action_bar,
    section_card,
)
from src.processing.order_processor import (
    normalize_manual_item_input,
    process_orders_dataframe,
)
from src.services.exports.excel_exporter import export_to_styled_excel
from src.state.persistence import save_state
from src.utils.file_io import read_uploaded
from src.utils.logging import log_error

from src.pages.pathao_orders.shared import (
    REQUIRED_COLUMNS,
    SOURCE_UPLOAD,
    SOURCE_WOOCOM,
    _highlight_split_orders,
    _load_processing_orders_from_woocommerce,
    _reset_pathao_state,
    _sync_pathao_map,
)

def _render_processing_tab():
    render_reset_confirm("Pathao Processor", "pathao", _reset_pathao_state)

    with st.expander("Pathao API & Sync Settings", expanded=False):
        st.markdown("### Location Database Sync")

        pathao_map_path = "resources/pathao_map.json"
        if os.path.exists(pathao_map_path):
            from datetime import datetime

            modified_at = os.path.getmtime(pathao_map_path)
            updated_str = datetime.fromtimestamp(modified_at).strftime("%Y-%m-%d %H:%M")
            render_status_toggle(
                "Local DB Loaded", "success", f"Last updated: {updated_str}"
            )
        else:
            render_status_toggle(
                "No Local Data",
                "warning",
                "Sync required for smart zone matching.",
            )

        st.info(
            "Sync the local database with Pathao city, zone, and area data for more accurate matching."
        )

        if st.button("Sync Available Locations from Pathao", use_container_width=True):
            _sync_pathao_map()

    section_card(
        "Order Source",
        "Choose whether to pull active processing orders from WooCommerce or process a user-supplied file.",
    )

    if hasattr(st, "pills"):
        source_mode = st.pills(
            "Select input source",
            [SOURCE_WOOCOM, SOURCE_UPLOAD],
            default=SOURCE_WOOCOM,
            selection_mode="single",
            key="pathao_source_mode_pills",
            label_visibility="collapsed",
        )
        if not source_mode:
            source_mode = SOURCE_WOOCOM
    else:
        source_mode = st.radio(
            "Select input source",
            [SOURCE_WOOCOM, SOURCE_UPLOAD],
            horizontal=True,
            key="pathao_source_mode_radio",
            label_visibility="collapsed",
        )

    if st.session_state.get("pathao_source_mode_last") != source_mode:
        st.session_state.pathao_source_mode_last = source_mode
        st.session_state.pathao_preview_df = None
        st.session_state.pathao_preview_source = None
        st.session_state.pathao_res_df = None
        st.session_state.pathao_vlink_df = None
        st.session_state.show_vlink_gen = False
        st.session_state.pathao_auto_process = False

    preview_df = None
    valid_file = False
    uploaded_file = None
    fetch_live_clicked = False

    if source_mode == SOURCE_WOOCOM:
        c_pull, c_hint = st.columns([1, 1])
        with c_pull:
            fetch_live_clicked = st.button(
                "Pull Processing Orders",
                type="secondary",
                use_container_width=True,
                key="pathao_live",
            )
        with c_hint:
            st.info("Only WooCommerce rows with status `processing` will be used.")
    else:
        uploaded_file = st.file_uploader("", type=["xlsx", "csv"], key="pathao_up")
        c_upload, c_url = st.columns(2)
        with c_upload:
            st.caption("Upload an Excel or CSV export.")
        with c_url:
            url_input = st.text_input(
                "Paste public CSV/XLSX URL",
                key="pathao_url_input",
                label_visibility="collapsed",
                placeholder="Paste public CSV/XLSX URL...",
            )
            if url_input and st.button(
                "Fetch URL",
                use_container_width=True,
                type="secondary",
                key="pathao_url_fetch",
            ):
                try:
                    from src.utils.url_fetch import fetch_dataframe_from_url

                    with st.spinner("Fetching from URL..."):
                        df_res = fetch_dataframe_from_url(url_input)
                        st.session_state.pathao_preview_df = df_res
                        st.session_state.pathao_preview_source = source_mode
                        st.session_state.pathao_auto_process = True
                        st.rerun()
                except Exception as exc:
                    st.error(f"URL fetch failed: {exc}")

    if fetch_live_clicked:
        try:
            preview_df, used_status_filter = _load_processing_orders_from_woocommerce()
            st.session_state.pathao_preview_df = preview_df
            st.session_state.pathao_preview_source = source_mode
            st.session_state.pathao_auto_process = True

            missing = [c for c in REQUIRED_COLUMNS if c not in preview_df.columns]
            valid_file = len(missing) == 0

            if preview_df.empty and used_status_filter:
                st.warning("No WooCommerce rows are currently in `processing` status.")
            else:
                st.toast(f"📥 Successfully pulled {len(preview_df)} processing rows.")
        except Exception as exc:
            log_error(exc, context="Pathao WooCommerce Pull")
            st.error(f"Failed to fetch data: {exc}")
    elif uploaded_file:
        try:
            preview_df = read_uploaded(uploaded_file)
            st.session_state.pathao_preview_df = preview_df
            st.session_state.pathao_preview_source = source_mode
            valid_file = render_file_summary(
                uploaded_file, preview_df, REQUIRED_COLUMNS
            )
        except Exception as exc:
            log_error(exc, context="Pathao Upload")
            st.error("Failed to read uploaded file.")
    elif (
        st.session_state.get("pathao_preview_df") is not None
        and st.session_state.get("pathao_preview_source") == source_mode
    ):
        preview_df = st.session_state.pathao_preview_df
        missing = [c for c in REQUIRED_COLUMNS if c not in preview_df.columns]
        valid_file = len(missing) == 0

    if preview_df is not None:
        with st.expander("Preview source data", expanded=False):
            preview_search = render_dataframe_search(
                preview_df, "pathao_preview", height=400
            )
            st.dataframe(preview_search.head(50), use_container_width=True)

    run_clicked, clear_clicked = render_sticky_action_bar(
        primary_label="Process orders",
        primary_key="pathao_process_btn",
        secondary_label="Clear source data",
        secondary_key="pathao_clear_btn",
    )

    if st.session_state.get("pathao_auto_process"):
        run_clicked = True
        st.session_state.pathao_auto_process = False

    if clear_clicked:
        _reset_pathao_state()
        st.rerun()

    if run_clicked:
        if preview_df is None or not valid_file:
            st.warning("Load a valid source before processing orders.")
        else:
            try:
                with st.status("Processing orders...", expanded=True) as status:
                    st.write(
                        "Applying cleanup, district resolution, and address normalization..."
                    )
                    result_df = process_orders_dataframe(preview_df.copy())
                    st.session_state.pathao_res_df = result_df
                    save_state()
                    status.update(
                        label="Processing complete", state="complete", expanded=False
                    )
                st.toast(f"✅ Processed {len(result_df)} grouped orders.")
            except Exception as exc:
                log_error(exc, context="Pathao Processor")
                st.error("Pathao processing failed. Check System Logs for details.")

    result_df = st.session_state.get("pathao_res_df")
    if result_df is not None:
        with st.expander("Preview output", expanded=True):
            result_search = render_dataframe_search(
                result_df, "pathao_result", height=400
            )
            st.dataframe(
                result_search.style.apply(_highlight_split_orders, axis=1),
                use_container_width=True,
            )

        c1, c2 = st.columns(2)
        with c1:
            pathao_excel_bytes = export_to_styled_excel(
                {"Pathao": result_df}, group_by_col="Order ID"
            )

            st.download_button(
                "Download repaired file",
                pathao_excel_bytes,
                "Pathao_Final.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )

        with c2:
            if st.button(
                "Generate Verification Links",
                type="secondary",
                use_container_width=True,
            ):
                st.session_state.show_vlink_gen = True

        if st.session_state.get("show_vlink_gen"):
            with st.status("Generating links...", expanded=True):
                import random

                df_v = result_df.copy()
                domain = "https://deencommerce.com/v"
                links = []
                for _, row in df_v.iterrows():
                    token = f"{random.getrandbits(32):08x}"
                    order_id = str(row.get("Order ID", "VERIFY"))
                    links.append(f"{domain}/verify?id={order_id}&token={token}")
                df_v["Verification Link"] = links
                st.session_state.pathao_vlink_df = df_v
                st.toast("✅ Verification links generated.")

            vlink_df = st.session_state.get("pathao_vlink_df")
            if vlink_df is not None:
                vlink_excel_bytes = export_to_styled_excel(
                    {"Verification": vlink_df}, group_by_col="Order ID"
                )

                st.download_button(
                    "Download Verification Report",
                    vlink_excel_bytes,
                    "Deliveries_Verification.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )


def _render_item_description_tab():
    section_card(
        "Item Description Helper",
        "Paste one item per line to normalize, sort, and generate the same ItemDesc style used by the bulk order processor.",
    )
    st.caption(
        "Supported formats: `2x Item Name`, `Item Name x2`, `Item Name (2 pcs)`, or `Item Name | SKU123`."
    )

    raw_items = st.text_area(
        "Manual item input",
        key="pathao_manual_items",
        height=220,
        placeholder="2x Oxford Shirt - Navy | SKU123\nPolo Shirt x1\nJeans (2 pcs)",
    )

    if st.button(
        "Normalize and sort items",
        type="primary",
        use_container_width=True,
        key="pathao_manual_normalize",
    ):
        if not raw_items.strip():
            st.warning("Enter at least one item line.")
        else:
            normalized_items, description = normalize_manual_item_input(raw_items)
            st.session_state.pathao_manual_items_df = pd.DataFrame(normalized_items)
            st.session_state.pathao_manual_desc = description

    normalized_df = st.session_state.get("pathao_manual_items_df")
    manual_desc = st.session_state.get("pathao_manual_desc")

    if normalized_df is not None and not normalized_df.empty:
        display_df = normalized_df.rename(
            columns={"category": "Category", "label": "Normalized Item", "qty": "Qty"}
        )
        with st.expander("Normalized items", expanded=True):
            st.dataframe(display_df, use_container_width=True, hide_index=True)

    if manual_desc:
        from src.components.ui.clipboard import render_copy_button

        c1, c2 = st.columns([4, 1])
        with c1:
            st.markdown("#### Generated Item Description")
        with c2:
            render_copy_button(manual_desc, label="Copy ItemDesc")
        st.code(manual_desc)

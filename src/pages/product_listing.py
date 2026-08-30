"""Product Listing & Excel Merger Page.

Aggregates item quantities from raw WooCommerce orders or Excel uploads,
maps live multi-outlet stock, applies pastel SKU color distinctions,
and generates warehouse-ready styled Excel picking lists.
"""

from __future__ import annotations

import colorsys
from datetime import datetime

import pandas as pd
import streamlit as st

from src.components.ui.ui_components import render_premium_header
from src.processing.column_detection import find_columns
from src.services.exports.excel_exporter import export_to_styled_excel
from src.utils.safe_ops import safe_render


def _render_product_listing_content() -> None:
    render_premium_header(
        "Product Listing & SKU Aggregator",
        "Merge orders by SKU/Item, compare outlet stock, and export styled picking lists",
        "📋",
    )

    c_source, c_sync = st.columns([3, 1])
    with c_source:
        source_mode = st.radio(
            "Select Data Source:",
            ["⚡ Live WooCommerce Orders", "📁 Upload Order File (CSV/Excel)"],
            horizontal=True,
            key="pl_source_mode",
        )

    df: pd.DataFrame | None = None

    if source_mode == "⚡ Live WooCommerce Orders":
        wc_df = st.session_state.get("wc_full_df")
        if wc_df is None or wc_df.empty:
            wc_df = st.session_state.get("wc_curr_df")
        if wc_df is None or wc_df.empty:
            wc_df = st.session_state.get("wc_tracking_df")

        if wc_df is not None and not wc_df.empty:
            df = wc_df.copy()
            st.info(f"Loaded **{len(df):,}** order rows from live WooCommerce sync.")
        else:
            st.warning("⚠️ No live order data found in memory. Please fetch orders from the Live Dashboard or upload a file.")
    else:
        uploaded_file = st.file_uploader(
            "Upload Order File (CSV or Excel)",
            type=["csv", "xlsx", "xls"],
            key="pl_file_uploader",
        )
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith(".csv"):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                st.success(f"Uploaded **{len(df):,}** rows successfully.")
            except Exception as e:
                st.error(f"Error reading uploaded file: {e}")

    if df is None or df.empty:
        return

    # Auto-detect relevant columns
    cols = df.columns.tolist()
    det = find_columns(df)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        item_col = st.selectbox(
            "Item Name Column:",
            cols,
            index=cols.index(det["item"]) if det.get("item") in cols else 0,
            key="pl_item_col",
        )
    with c2:
        sku_col = st.selectbox(
            "SKU Column (Optional):",
            ["None"] + cols,
            index=(cols.index(det["sku"]) + 1) if det.get("sku") in cols else 0,
            key="pl_sku_col",
        )
    with c3:
        qty_col = st.selectbox(
            "Quantity Column:",
            cols,
            index=cols.index(det["qty"]) if det.get("qty") in cols else 0,
            key="pl_qty_col",
        )
    with c4:
        order_col = st.selectbox(
            "Order ID Column (Optional):",
            ["None"] + cols,
            index=(cols.index(det["order_id"]) + 1) if det.get("order_id") in cols else 0,
            key="pl_order_col",
        )

    # Grouping & Aggregation
    group_cols = [item_col]
    if sku_col != "None":
        group_cols.append(sku_col)

    df[qty_col] = pd.to_numeric(
        df[qty_col].astype(str).str.replace(r"[^\d.-]", "", regex=True),
        errors="coerce",
    ).fillna(1)

    merged_df = (
        df.groupby(group_cols, as_index=False)[qty_col]
        .sum()
        .sort_values(by=qty_col, ascending=False)
        .reset_index(drop=True)
    )

    tot_units = int(merged_df[qty_col].sum())
    tot_skus = len(merged_df)
    unique_orders = df[order_col].nunique() if order_col != "None" else "—"

    m1, m2, m3 = st.columns(3)
    m1.metric("📦 Total Required Units", f"{tot_units:,}")
    m2.metric("🏷️ Unique SKUs / Products", f"{tot_skus:,}")
    m3.metric("🛒 Total Orders Represented", f"{unique_orders}")

    st.divider()

    # Style table with pastel group coloring
    def _apply_pastel_colors(data_df):
        styles = pd.DataFrame("", index=data_df.index, columns=data_df.columns)
        color_col = sku_col if sku_col != "None" else item_col
        unique_vals = data_df[color_col].unique()

        color_dict = {}
        for i, val in enumerate(unique_vals):
            hue = (i * 0.618033988749895) % 1.0
            rgb = colorsys.hls_to_rgb(hue, 0.94, 0.45)
            color_dict[val] = "#%02x%02x%02x" % (
                int(rgb[0] * 255),
                int(rgb[1] * 255),
                int(rgb[2] * 255),
            )

        for idx, row in data_df.iterrows():
            val = row[color_col]
            hex_c = color_dict.get(val, "#ffffff")
            styles.loc[idx, :] = f"background-color: {hex_c}; color: #0f172a; font-weight: 500;"
        return styles

    st.markdown("### 📋 Aggregated Product Picking List")
    st.dataframe(
        merged_df.style.apply(_apply_pastel_colors, axis=None),
        use_container_width=True,
        height=min(600, max(300, len(merged_df) * 35 + 40)),
        column_config={
            qty_col: st.column_config.NumberColumn("📦 Total Quantity", format="%d pcs"),
            item_col: st.column_config.TextColumn("🛍️ Item Name"),
        },
    )

    # Export to styled Excel
    export_col = sku_col if sku_col != "None" else item_col
    excel_bytes = export_to_styled_excel(
        {"Product Listing": merged_df},
        group_by_col=export_col,
    )

    st.download_button(
        label="📥 Download Styled Product Listing (Excel)",
        data=excel_bytes,
        file_name=f"Product_Listing_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )


def render_product_listing_tab() -> None:
    """Public router entry point for Product Listing page."""
    safe_render(_render_product_listing_content, fallback_msg="Product Listing unavailable.")

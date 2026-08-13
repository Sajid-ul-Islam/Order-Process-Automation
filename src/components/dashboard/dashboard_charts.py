"""Chart rendering for the dashboard — pie, bar, spotlight, and copy buttons."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.utils.display import truncate_label


def get_short_category_label(name: str) -> str:
    """Return concise short descriptor (e.g. 'Denim', 'Flannel', 'Corduroy', 'Cuban') instead of long prefixes."""
    if not isinstance(name, str) or not name:
        return ""
    name_str = name.strip()
    lower_n = name_str.lower()

    if "denim" in lower_n:
        return "Denim"
    if "flannel" in lower_n:
        return "Flannel"
    if "casual" in lower_n:
        return "Casual"
    if "corduroy" in lower_n:
        return "Corduroy"
    if "cuban" in lower_n:
        return "Cuban"
    if "formal shirt" in lower_n:
        return "Formal"
    if "panjabi" in lower_n:
        return "Panjabi"
    if "sweatshirt" in lower_n or "sweat shirt" in lower_n:
        return "Sweatshirt"
    if "jeans" in lower_n:
        return "Jeans"
    if "pajama" in lower_n or "payjama" in lower_n:
        return "Pajama"
    if "polo" in lower_n:
        return "Polo"
    if "cargo" in lower_n:
        return "Cargo"

    for prefix in [
        "FS Shirt - ",
        "HS Shirt - ",
        "FS T-Shirt - ",
        "HS T-Shirt - ",
        "FS Shirt ",
        "HS Shirt ",
        "FS ",
        "HS ",
    ]:
        if name_str.startswith(prefix):
            short_ver = name_str[len(prefix) :].strip()
            if short_ver:
                return short_ver

    return name_str


def render_category_charts(
    summ: pd.DataFrame,
    display_col: str,
    color_map: dict[str, str],
    metrics_summary: dict | None = None,
    total_revenue: float | None = None,
) -> None:
    """Render the Revenue Share pie and Volume bar charts with truncated labels.

    Args:
        summ: Summary DataFrame with 'Total Amount', 'Total Qty', etc.
        display_col: Column name to use for chart grouping ('Category' or 'Sub-Category').
        color_map: Mapping of category values to hex colours.
        metrics_summary: Optional dictionary containing top revenue/volume metrics.
        total_revenue: Optional Net Realized Revenue override for exact center donut alignment.
    """
    summ_display = summ.copy()
    summ_display["Display_Label"] = summ_display[display_col].apply(
        lambda x: truncate_label(get_short_category_label(x), max_len=15)
    )

    v1, v2 = st.columns(2)
    with v1:
        pie_display = summ_display.copy()
        pie_display["Pie_Name"] = pie_display[display_col].apply(
            get_short_category_label
        )

        tot_rev = pie_display["Total Amount"].sum()
        if (
            display_col == "Sub-Category"
            and "Category" in pie_display.columns
            and tot_rev > 0
        ):

            def resolve_low_share_name(row):
                sub_raw = str(row.get(display_col, ""))
                cat_raw = str(row.get("Category", ""))
                sub_short = get_short_category_label(sub_raw)
                cat_short = get_short_category_label(cat_raw)

                # If share is low (< 5%), choose whichever label is shorter between Sub-Category and Category
                if float(row.get("Total Amount", 0)) < (0.05 * tot_rev):
                    if len(sub_short) > 0 and len(sub_short) <= len(cat_short):
                        return sub_short
                    return cat_short if len(cat_short) > 0 else sub_short
                return sub_short if len(sub_short) > 0 else cat_short

            pie_display["Pie_Name"] = pie_display.apply(resolve_low_share_name, axis=1)

        # Consolidate duplicate Pie_Name rows cleanly before calculating top slices and Others
        agg_dict = {"Total Amount": "sum", "Total Qty": "sum"}
        if display_col in pie_display.columns:
            agg_dict[display_col] = "first"
        if "Category" in pie_display.columns:
            agg_dict["Category"] = "first"
        pie_display = pie_display.groupby("Pie_Name", as_index=False).agg(agg_dict)

        # Scale category amounts to match Net Realized Revenue if provided
        gross_tot = float(pie_display["Total Amount"].sum())
        if (
            total_revenue is not None
            and total_revenue > 0
            and gross_tot > 0
            and abs(gross_tot - total_revenue) > 0.01
        ):
            scale_factor = total_revenue / gross_tot
            pie_display["Total Amount"] = pie_display["Total Amount"] * scale_factor

        name_totals = (
            pie_display.groupby("Pie_Name")["Total Amount"]
            .sum()
            .sort_values(ascending=False)
        )
        total_amt = (
            float(total_revenue)
            if (total_revenue is not None and total_revenue > 0)
            else float(name_totals.sum())
        )

        top_p = name_totals[name_totals >= 0.02 * total_amt].index.tolist()

        max_pie = 12
        if len(top_p) > max_pie - 1:
            top_p = top_p[: max_pie - 1]

        if len(top_p) < len(name_totals):
            others_mask = ~pie_display["Pie_Name"].isin(top_p)
            others_rev = pie_display.loc[others_mask, "Total Amount"].sum()
            others_qty = pie_display.loc[others_mask, "Total Qty"].sum()

            others_row = pd.DataFrame(
                [
                    {
                        "Pie_Name": "Others",
                        display_col: "Others",
                        "Total Amount": others_rev,
                        "Total Qty": others_qty,
                    }
                ]
            )
            pie_display = pd.concat(
                [pie_display[~others_mask], others_row], ignore_index=True
            )

            if "Others" not in color_map:
                color_map = color_map.copy()
                color_map["Others"] = "#94a3b8"

            name_totals = (
                pie_display.groupby("Pie_Name")["Total Amount"]
                .sum()
                .sort_values(ascending=False)
            )

        pie_display["_Name_Total"] = pie_display["Pie_Name"].map(name_totals)
        pie_display = pie_display.sort_values(
            ["_Name_Total", "Total Amount"], ascending=[False, False]
        )
        pie_display["Display_Label"] = pie_display["Pie_Name"].apply(
            lambda x: truncate_label(x, max_len=15)
        )

        pie_display["Avg_Price"] = pie_display.apply(
            lambda r: (r["Total Amount"] / r["Total Qty"]) if r["Total Qty"] > 0 else 0,
            axis=1,
        )

        fig_pie = px.pie(
            pie_display,
            values="Total Amount",
            names="Pie_Name",
            color=display_col,
            hole=0.55,
            title="<b>💰 Revenue Share (TK)</b>",
            color_discrete_map=color_map,
        )
        # Explicit customdata in a fixed, version-independent order so the
        # texttemplate and hovertemplate indices always match:
        # [0]=Total Qty  [1]=Display_Label  [2]=Pie_Name  [3]=Avg_Price
        fig_pie.update_traces(
            customdata=pie_display[
                ["Total Qty", "Display_Label", "Pie_Name", "Avg_Price"]
            ].values
        )

        center_annotation_text = (
            f"<span style='font-size:18px;'><b>৳ {total_amt:,.0f}</b></span><br>"
            f"<span style='font-size:10px;opacity:0.75;letter-spacing:0.5px;'>TOTAL REVENUE</span>"
        )
        fig_pie.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=40, b=30, l=20, r=20),
            height=440,
            showlegend=False,
            hoverlabel=dict(
                bgcolor="#0f172a",
                font_size=12,
                font_family="Inter, sans-serif",
                font_color="#ffffff",
                bordercolor="#a855f7",
            ),
            annotations=[
                dict(
                    text=center_annotation_text,
                    x=0.5,
                    y=0.5,
                    font=dict(family="Inter, sans-serif"),
                    showarrow=False,
                    align="center",
                )
            ],
        )
        # Determine background gap color so slices do NOT join:
        # Light mode page -> #ffffff (creates a 4.5px white gap separating slices)
        # Dark mode page  -> #0f172a (creates a 4.5px dark gap separating slices)
        is_dark = (
            st.session_state.get("dark_mode", False)
            or "dark" in str(st.session_state.get("theme_mode", "")).lower()
        )
        gap_color = "#0f172a" if is_dark else "#ffffff"

        fig_pie.update_traces(
            sort=False,
            textposition="inside",
            texttemplate="%{customdata[1]}<br>%{percent:.0%}",
            textfont_size=11,
            marker=dict(line=dict(color=gap_color, width=4.5)),
            hovertemplate=(
                "<b>%{customdata[2]}</b><br>"
                "💰 Net Revenue: <b>৳ %{value:,.0f}</b> (%{percent:.1%})<br>"
                "📦 Volume Sold: <b>%{customdata[0]:,.0f} Units</b><br>"
                "🏷️ Avg Item Price: <b>৳ %{customdata[3]:,.0f} / unit</b>"
                "<extra></extra>"
            ),
        )
        st.plotly_chart(
            fig_pie, use_container_width=True, config={"displayModeBar": False}
        )

        # Executive Category Leaderboard Pills with Rank Medals
        pill_htmls = []
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]
        for idx, p_row in pie_display.head(6).reset_index(drop=True).iterrows():
            c_name = str(p_row.get(display_col, p_row.get("Pie_Name", "")))
            c_rev = float(p_row.get("Total Amount", 0))
            c_color = color_map.get(c_name, "#a855f7")
            c_pct = (c_rev / total_amt * 100) if total_amt > 0 else 0
            medal = medals[idx] if idx < len(medals) else f"#{idx + 1}"

            pill_htmls.append(
                f"<div style='background: var(--card-bg, rgba(255,255,255,0.04)); border: 1px solid var(--border-color, rgba(255,255,255,0.08)); border-radius: 8px; padding: 4px 10px; font-size: 11px; display: inline-flex; align-items: center; gap: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.12);'>"
                f"<span style='font-size:12px;'>{medal}</span> "
                f"<b>{truncate_label(c_name, 12)}</b>: "
                f"<span style='color:{c_color}; font-weight:bold;'>৳{c_rev:,.0f}</span> "
                f"<span style='opacity:0.75; font-size:10px;'>({c_pct:.1f}%)</span>"
                f"</div>"
            )
        if pill_htmls:
            st.markdown(
                f"<div style='display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; margin-bottom:8px;'>{''.join(pill_htmls)}</div>",
                unsafe_allow_html=True,
            )

    with v2:
        bar_axis = "Sub-Category" if "Sub-Category" in summ.columns else display_col
        bar_display = summ_display.copy()

        bar_display["Bar_X"] = bar_display[bar_axis].apply(get_short_category_label)

        if (
            display_col == "Sub-Category"
            and len(bar_display) > 12
            and "Category" in bar_display.columns
        ):
            jeans_mask = bar_display["Category"] == "Jeans"
            bar_display.loc[jeans_mask, "Bar_X"] = "Jeans"

        x_totals = (
            bar_display.groupby("Bar_X")["Total Qty"].sum().sort_values(ascending=False)
        )

        max_bars = 12
        if len(x_totals) > max_bars:
            top_x = x_totals.index[: max_bars - 1].tolist()
            bar_display.loc[~bar_display["Bar_X"].isin(top_x), "Bar_X"] = "Others"

            x_totals = (
                bar_display.groupby("Bar_X")["Total Qty"]
                .sum()
                .sort_values(ascending=False)
            )
            sorted_bars = [x for x in x_totals.index if x != "Others"] + ["Others"]
        else:
            sorted_bars = x_totals.index.tolist()

        bar_display = bar_display.sort_values("Total Qty", ascending=False)
        bar_display["Avg_Unit_Price"] = bar_display.apply(
            lambda r: (r["Total Amount"] / r["Total Qty"]) if r["Total Qty"] > 0 else 0,
            axis=1,
        )

        unique_bars = pd.DataFrame({"Bar_X": sorted_bars})
        unique_bars["Bar_Label"] = unique_bars["Bar_X"].apply(
            lambda x: truncate_label(get_short_category_label(x), max_len=15)
        )

        fig_bar = px.bar(
            bar_display,
            x="Bar_X",
            y="Total Qty",
            color=display_col,
            title="<b>📦 Sales Volume by Category</b>",
            text_auto=".0f",
            color_discrete_map=color_map,
            category_orders={"Bar_X": sorted_bars},
        )
        # Explicit customdata in a fixed order so the hovertemplate indices are
        # version-independent: [0]=Bar_X  [1]=Total Amount  [2]=Avg_Unit_Price
        fig_bar.update_traces(
            customdata=bar_display[["Bar_X", "Total Amount", "Avg_Unit_Price"]].values
        )

        avg_vol = bar_display["Total Qty"].mean() if not bar_display.empty else 0
        if avg_vol > 0:
            fig_bar.add_hline(
                y=avg_vol,
                line_dash="dash",
                line_color="rgba(255,255,255,0.4)",
                annotation_text=f"Avg: {avg_vol:.1f} units",
                annotation_position="top right",
                annotation_font=dict(size=10, color="rgba(255,255,255,0.7)"),
            )

        fig_bar.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=40, b=30, l=20, r=20),
            height=440,
            xaxis_title="",
            yaxis_title="Units Sold",
            showlegend=False,
            hoverlabel=dict(
                bgcolor="#0f172a",
                font_size=12,
                font_family="Inter, sans-serif",
                font_color="#ffffff",
                bordercolor="#3b82f6",
            ),
        )
        fig_bar.update_xaxes(
            showgrid=False,
            automargin=True,
            tickmode="array",
            tickvals=unique_bars["Bar_X"],
            ticktext=unique_bars["Bar_Label"],
            tickangle=-45,
        )
        fig_bar.update_yaxes(
            showgrid=True,
            gridwidth=1,
            gridcolor="rgba(255,255,255,0.06)",
            zeroline=False,
            automargin=True,
        )
        fig_bar.update_traces(
            cliponaxis=False,
            marker=dict(line=dict(color="rgba(255,255,255,0.2)", width=1)),
            hovertemplate="<b>%{x}</b><br>📦 Volume: %{y:,.0f} Units<br>💰 Net Revenue: ৳ %{customdata[1]:,.0f}<br>🏷️ Avg Price: ৳ %{customdata[2]:,.0f}/unit",
        )
        st.plotly_chart(
            fig_bar, use_container_width=True, config={"displayModeBar": False}
        )


def render_spotlight(
    top: pd.DataFrame, color_map: dict[str, str], prev_top: pd.DataFrame | None = None
) -> None:
    """Render the Products Spotlight bar chart with velocity arrows and stock alerts.

    Args:
        top: Top-items DataFrame with 'Product Name', 'SKU', 'Category', 'Total Qty', 'Total Amount'.
        color_map: Mapping of category values to hex colours.
        prev_top: Optional previous-period top-items for velocity calculation.
    """
    if top is None or top.empty:
        return

    # Apply size-agnostic grouping (aggregate by Clean_Product)
    top = top.copy()
    if "Clean_Product" in top.columns:
        group_cols = ["Clean_Product"]
        if "SKU" in top.columns:
            group_cols.append("SKU")

        agg_dict = {"Total Qty": "sum", "Total Amount": "sum", "Category": "first"}
        if "Sub-Category" in top.columns:
            agg_dict["Sub-Category"] = "first"

        top = top.groupby(group_cols, as_index=False).agg(agg_dict)
        top.rename(columns={"Clean_Product": "Product Name"}, inplace=True)

        if (
            prev_top is not None
            and not prev_top.empty
            and "Clean_Product" in prev_top.columns
        ):
            prev_group_cols = ["Clean_Product"]
            if "SKU" in prev_top.columns:
                prev_group_cols.append("SKU")
            prev_top = prev_top.groupby(prev_group_cols, as_index=False).agg(agg_dict)
            prev_top.rename(columns={"Clean_Product": "Product Name"}, inplace=True)

    st.subheader("🔥 Products Spotlight")
    sc1, sc2 = st.columns([1, 1])
    with sc1:
        strat_opts = [
            "Top 10",
            "Top 20",
            "Last 10",
            "Last 20",
            "Underperformers",
            "Custom Range",
            "Custom Order",
        ]
        if hasattr(st, "pills"):
            strategy = st.pills(
                "Spotlight Strategy",
                strat_opts,
                default="Top 10",
                key="spotlight_strat_pills",
                selection_mode="single",
            )
            if not strategy:
                strategy = "Top 10"
        else:
            strategy = st.radio(
                "Spotlight Strategy",
                strat_opts,
                index=0,
                key="spotlight_strat_radio",
                horizontal=True,
            )

    limit = 10
    ascending = False
    if strategy == "Top 10":
        limit = 10
        ascending = False
    elif strategy == "Top 20":
        limit = 20
        ascending = False
    elif strategy in ["Last 10", "Underperformers"]:
        limit = 10
        ascending = True
    elif strategy == "Last 20":
        limit = 20
        ascending = True

    # Ensure top is sorted descending by amount so custom range and limits slice correctly
    top = top.sort_values("Total Amount", ascending=False).reset_index(drop=True)

    if strategy in ["Custom Range", "Custom Order"] and not top.empty:
        with sc2:
            c_range = st.slider(
                "Select Rank Range", 1, len(top), (1, min(10, len(top)))
            )
            spotlight = top.iloc[c_range[0] - 1 : c_range[1]].sort_values(
                "Total Amount", ascending=True
            )
    else:
        spotlight = (
            top.sort_values("Total Amount", ascending=ascending)
            .head(limit)
            .sort_values("Total Amount", ascending=True)
        )

    spotlight = spotlight.copy()

    # v15.0: Calculate Velocity and Stock Intelligence
    stock_df = st.session_state.get("wc_stock_df")

    def get_velocity_and_stock_label(row):
        has_sku = (
            "SKU" in row
            and pd.notna(row["SKU"])
            and str(row["SKU"]).strip() not in ["", "N/A", "nan"]
        )
        product_name = str(row["Product Name"])
        label = f"{product_name} [{row['SKU']}]" if has_sku else f"{product_name}"

        # 🟢 Velocity Logic
        if prev_top is not None and not prev_top.empty:
            if has_sku and "SKU" in prev_top.columns:
                prev_row = prev_top[prev_top["SKU"] == row["SKU"]]
            elif "Product Name" in prev_top.columns:
                prev_row = prev_top[prev_top["Product Name"] == row["Product Name"]]
            else:
                prev_row = pd.DataFrame()

            if not prev_row.empty:
                curr_q = row["Total Qty"]
                prev_q = prev_row.iloc[0]["Total Qty"]
                if curr_q > prev_q:
                    label = f"<span style='color:#10b981'>🔼</span> {label}"
                elif curr_q < prev_q:
                    label = f"<span style='color:#ef4444'>🔽</span> {label}"

        # 🔴 Safety Stock Logic
        if stock_df is not None and not stock_df.empty:
            sku_stock = pd.DataFrame()
            if has_sku and "SKU" in stock_df.columns:
                sku_stock = stock_df[stock_df["SKU"] == row["SKU"]]
            elif "Clean_Product" in stock_df.columns:
                sku_stock = stock_df[stock_df["Clean_Product"] == row["Product Name"]]
            elif "Product" in stock_df.columns:
                sku_stock = stock_df[stock_df["Product"] == row["Product Name"]]

            if not sku_stock.empty:
                stock_qty = sku_stock["Stock"].sum()
                # Trigger earlier: if stock is under absolute minimum (10) OR less than 3x current shift sales
                if stock_qty <= 10 or stock_qty <= (row["Total Qty"] * 3.0):
                    label = f"<span style='color:#f59e0b'>⚠️</span> {label}"

        return label

    spotlight["Label"] = spotlight.apply(get_velocity_and_stock_label, axis=1)

    hover_data_dict = {
        "Label": False,
        "Product Name": True,
        "Sub-Category": True if "Sub-Category" in spotlight.columns else False,
        "Total Qty": ":.0f",
        "Total Amount": ":,.0f",
    }
    if "SKU" in spotlight.columns:
        hover_data_dict["SKU"] = True

    fig_top = px.bar(
        spotlight,
        x="Total Amount",
        y="Label",
        orientation="h",
        color="Category",
        title=f"Spotlight: {strategy}",
        text_auto=".2s",
        color_discrete_map=color_map,
        hover_data=hover_data_dict,
    )
    fig_top.update_layout(
        margin=dict(t=50, b=20, l=10, r=20),
        yaxis_title="",
        xaxis_title="Revenue (TK)",
        showlegend=False,
    )
    fig_top.update_yaxes(automargin=True)
    fig_top.update_xaxes(automargin=True)
    st.plotly_chart(fig_top, use_container_width=True, config={"displayModeBar": False})


def render_revenue_cashback_comparison_chart(m_df: pd.DataFrame) -> None:
    """Render a visual side-by-side comparison chart for Gross Revenue vs Net Revenue vs Cashback Fee."""
    if m_df is None or m_df.empty:
        st.info("No data available for revenue comparison.")
        return

    status_col = (
        "Order Status"
        if "Order Status" in m_df.columns
        else "Status" if "Status" in m_df.columns else None
    )

    # Calculate overall metrics
    gross_rev = (
        m_df["Gross Amount"].sum()
        if "Gross Amount" in m_df.columns
        else m_df["Total Amount"].sum()
    )
    net_rev = m_df["Total Amount"].sum() if "Total Amount" in m_df.columns else 0
    cashback_disc = (
        m_df["Cashback Discount"].sum()
        if "Cashback Discount" in m_df.columns
        else max(0.0, gross_rev - net_rev)
    )

    from src.config.ui_config import get_active_theme_config

    theme_cfg = get_active_theme_config()

    # 1. Overview Bar Chart
    comp_df = pd.DataFrame(
        [
            {
                "Metric": "Gross Revenue (Pre-Discount)",
                "Amount (TK)": gross_rev,
                "Category": "Gross Revenue",
            },
            {
                "Metric": "Net Revenue (Post-Cashback)",
                "Amount (TK)": net_rev,
                "Category": "Net Revenue",
            },
            {
                "Metric": "Cashback / Discount Fee",
                "Amount (TK)": cashback_disc,
                "Category": "Discount / Cashback",
            },
        ]
    )

    fig_overview = px.bar(
        comp_df,
        x="Metric",
        y="Amount (TK)",
        color="Category",
        text="Amount (TK)",
        color_discrete_map={
            "Gross Revenue": theme_cfg.get("primary", "#10b981"),
            "Net Revenue": theme_cfg.get("secondary", "#06b6d4"),
            "Discount / Cashback": theme_cfg.get("spark_bv", "#f59e0b"),
        },
        title="Overall Revenue Stream Comparison",
    )
    fig_overview.update_traces(texttemplate="TK %{text:,.0f}", textposition="outside")
    fig_overview.update_layout(
        margin=dict(t=40, b=20, l=10, r=10),
        showlegend=False,
        yaxis_title="Amount (TK)",
        xaxis_title="",
    )

    # 2. Status Breakdown if status_col exists
    if status_col:
        status_grp = (
            m_df.groupby(status_col)
            .agg(
                {
                    "Gross Amount": (
                        "sum" if "Gross Amount" in m_df.columns else "count"
                    ),
                    "Total Amount": (
                        "sum" if "Total Amount" in m_df.columns else "count"
                    ),
                    "Cashback Discount": (
                        "sum" if "Cashback Discount" in m_df.columns else "count"
                    ),
                }
            )
            .reset_index()
        )

        status_melt = status_grp.melt(
            id_vars=[status_col],
            value_vars=["Gross Amount", "Total Amount", "Cashback Discount"],
            var_name="Revenue Type",
            value_name="Amount (TK)",
        )
        status_melt["Revenue Type"] = status_melt["Revenue Type"].map(
            {
                "Gross Amount": "Gross Revenue",
                "Total Amount": "Net Revenue",
                "Cashback Discount": "Cashback / Fee",
            }
        )

        fig_status = px.bar(
            status_melt,
            x=status_col,
            y="Amount (TK)",
            color="Revenue Type",
            barmode="group",
            title="Revenue & Cashback Breakdown by Status",
            color_discrete_map={
                "Gross Revenue": "#3b82f6",
                "Net Revenue": "#10b981",
                "Cashback / Fee": "#f59e0b",
            },
        )
        fig_status.update_layout(
            margin=dict(t=40, b=20, l=10, r=10),
            xaxis_title="Order Status",
            yaxis_title="TK",
        )

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.plotly_chart(fig_overview, use_container_width=True)
        with col_c2:
            st.plotly_chart(fig_status, use_container_width=True)
    else:
        st.plotly_chart(fig_overview, use_container_width=True)

    # ── Pie Charts: Order Share & Revenue Impact ──────────────────────────────
    id_col = (
        "Order ID"
        if "Order ID" in m_df.columns
        else "Order Number" if "Order Number" in m_df.columns else None
    )
    cb_mask = (
        (m_df["Cashback Discount"] > 0)
        if "Cashback Discount" in m_df.columns
        else pd.Series(False, index=m_df.index)
    )

    if cb_mask.any():
        st.markdown("##### 🥧 Cashback Order Share & Revenue Contribution")
        pie_c1, pie_c2 = st.columns(2)

        # — Pie 1: % of orders with vs without cashback —
        if id_col:
            unique_df = m_df.drop_duplicates(subset=[id_col])
            cb_ord_ids = m_df.loc[cb_mask, id_col].unique()
            cb_orders = unique_df[id_col].isin(cb_ord_ids).sum()
            clean_orders = len(unique_df) - cb_orders
        else:
            cb_orders = int(cb_mask.sum())
            clean_orders = len(m_df) - cb_orders

        pie_orders_df = pd.DataFrame(
            {
                "Segment": ["With Cashback", "No Cashback"],
                "Orders": [cb_orders, clean_orders],
            }
        )

        fig_pie_orders = px.pie(
            pie_orders_df,
            names="Segment",
            values="Orders",
            title="Orders: Cashback vs No-Cashback",
            color="Segment",
            color_discrete_map={
                "With Cashback": "#f59e0b",
                "No Cashback": "#10b981",
            },
            hole=0.45,
        )
        fig_pie_orders.update_traces(
            textinfo="percent+label",
            hovertemplate="%{label}<br>%{value:,} orders (%{percent})<extra></extra>",
        )
        fig_pie_orders.update_layout(
            margin=dict(t=50, b=20, l=10, r=10),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.25),
        )

        # — Pie 2: Gross revenue of cashback'd orders vs clean orders —
        gross_col = (
            "Gross Amount"
            if "Gross Amount" in m_df.columns
            else "Total Amount" if "Total Amount" in m_df.columns else None
        )
        if gross_col:
            cb_gross = float(m_df.loc[cb_mask, gross_col].sum())
            clean_gross = float(m_df.loc[~cb_mask, gross_col].sum())
        else:
            cb_gross = (
                float(
                    (
                        m_df.loc[cb_mask, "Quantity"] * m_df.loc[cb_mask, "Item Cost"]
                    ).sum()
                )
                if "Quantity" in m_df.columns
                else 0.0
            )
            clean_gross = float(gross_rev) - cb_gross

        pie_rev_df = pd.DataFrame(
            {
                "Segment": ["Cashback Orders Revenue", "Non-Cashback Orders Revenue"],
                "Revenue (TK)": [cb_gross, max(0.0, clean_gross)],
            }
        )

        fig_pie_rev = px.pie(
            pie_rev_df,
            names="Segment",
            values="Revenue (TK)",
            title="Gross Revenue: Cashback'd vs Clean Orders",
            color="Segment",
            color_discrete_map={
                "Cashback Orders Revenue": "#f59e0b",
                "Non-Cashback Orders Revenue": "#3b82f6",
            },
            hole=0.45,
        )
        fig_pie_rev.update_traces(
            textinfo="percent+label",
            hovertemplate="%{label}<br>TK %{value:,.0f} (%{percent})<extra></extra>",
        )
        fig_pie_rev.update_layout(
            margin=dict(t=50, b=20, l=10, r=10),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.25),
        )

        with pie_c1:
            st.plotly_chart(fig_pie_orders, use_container_width=True)
        with pie_c2:
            st.plotly_chart(fig_pie_rev, use_container_width=True)

"""Market Basket & Cross-Selling Analysis view component.

Renders association rules, frequent itemsets, co-purchase rates, basket size distributions,
and interactive product bundle recommendations for DEEN-OPS Terminal.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.processing.market_basket import (
    compute_basket_summary_metrics,
    compute_category_associations,
    detect_id_and_item_cols,
    get_product_cross_sells,
    mine_association_rules,
)

EXCLUDED_STATUSES = [
    "failed",
    "cancelled",
    "pending",
    "on-hold",
    "refunded",
    "trash",
]


def render_market_basket_analysis_section(
    m_df: pd.DataFrame,
    raw_df: pd.DataFrame | None = None,
) -> None:
    """Render the full Market Basket Analysis dashboard section.

    Args:
        m_df: Granular filtered/standardized DataFrame.
        raw_df: Optional pre-filter DataFrame to account for excluded orders.
    """
    if m_df is None or m_df.empty:
        st.info("No order line data available for Market Basket Analysis.")
        return

    # Defensively initialize session keys
    if "mba_level" not in st.session_state:
        st.session_state["mba_level"] = "Base Product (Clean)"
    if "mba_min_co" not in st.session_state:
        st.session_state["mba_min_co"] = 1

    st.markdown("### 🛒 Market Basket & Cross-Selling Intelligence")
    st.caption(
        "Discover customer co-purchase behaviors, frequent product bundles, basket size distribution, "
        "and association rules (Support, Confidence, Lift) to drive multi-item order growth."
    )

    # ── Level Selector & Filter Controls ─────────────────────────────────────
    level_col_map = {
        "Base Product (Clean)": "Clean_Product"
        if "Clean_Product" in m_df.columns
        else ("Product Name" if "Product Name" in m_df.columns else "Item Name"),
        "Full Product Name": "Product Name"
        if "Product Name" in m_df.columns
        else ("Item Name" if "Item Name" in m_df.columns else "Clean_Product"),
        "SKU": "SKU" if "SKU" in m_df.columns else None,
        "Category": "Category" if "Category" in m_df.columns else None,
    }
    # Filter out levels not available in the current dataframe
    available_levels = [
        lvl for lvl, col in level_col_map.items() if col and col in m_df.columns
    ]
    if not available_levels:
        available_levels = ["Base Product (Clean)"]

    c_ctrl1, c_ctrl2, c_ctrl3 = st.columns([2, 1, 1])
    with c_ctrl1:
        current_lvl = st.session_state.get("mba_level", available_levels[0])
        lvl_idx = (
            available_levels.index(current_lvl)
            if current_lvl in available_levels
            else 0
        )
        selected_level = st.selectbox(
            "Aggregation Level:",
            available_levels,
            index=lvl_idx,
            key="mba_level_selector",
            help="Choose product granularity: 'Base Product' aggregates sizes/variants together into the base item.",
        )
        st.session_state["mba_level"] = selected_level

    target_item_col = level_col_map.get(selected_level)
    id_col, _ = detect_id_and_item_cols(m_df, target_item_col)

    with c_ctrl2:
        min_co = st.number_input(
            "Min Co-Orders:",
            min_value=1,
            max_value=100,
            value=int(st.session_state.get("mba_min_co", 1)),
            step=1,
            key="mba_min_co_input",
            help="Filter out pairs with fewer than this many co-occurring orders.",
        )
        st.session_state["mba_min_co"] = min_co

    with c_ctrl3:
        lift_filter = st.selectbox(
            "Lift Affinity:",
            [
                "All Associations",
                "Positive Affinity (Lift ≥ 1.0)",
                "High Affinity (Lift ≥ 1.5)",
            ],
            index=0,
            key="mba_lift_filter",
            help="Lift > 1.0 indicates items are bought together more often than expected by chance.",
        )

    # ── Compute Summary Metrics ──────────────────────────────────────────────
    metrics = compute_basket_summary_metrics(
        m_df,
        id_col=id_col,
        item_col=target_item_col,
    )

    tot_orders = metrics["total_orders"]
    multi_cnt = metrics["multi_item_orders"]
    multi_rate = metrics["multi_item_rate"]
    avg_items = metrics["avg_basket_items"]
    max_items = metrics["max_basket_items"]
    top_pair = metrics["top_pair"]
    top_pair_cnt = metrics["top_pair_count"]

    # ── Hero KPI Cards ───────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.metric(
            "📦 Analyzed Orders",
            f"{tot_orders:,}",
            help="Total unique orders in the current active period",
        )
    with k2:
        st.metric(
            "🛍️ Multi-Item Rate",
            f"{multi_rate:.1f}%",
            delta=f"{multi_cnt:,} multi-item orders",
            help="Percentage of orders containing 2 or more distinct items",
        )
    with k3:
        st.metric(
            "🧺 Avg Basket Items",
            f"{avg_items:.2f}",
            delta=f"Max {max_items} in 1 order",
            help="Average distinct items per order",
        )
    with k4:
        pair_label = f"{top_pair[0]} + {top_pair[1]}" if top_pair else "N/A"
        st.metric(
            "🤝 Top Affinity Pair",
            f"{top_pair_cnt} orders" if top_pair else "None",
            delta=pair_label[:26] + "..." if len(pair_label) > 26 else pair_label,
            help="Most frequently co-purchased pair of products",
        )
    with k5:
        single_orders = metrics["single_item_orders"]
        single_pct = (single_orders / tot_orders * 100.0) if tot_orders > 0 else 0.0
        st.metric(
            "🎯 Single-Item Orders",
            f"{single_orders:,}",
            delta=f"{single_pct:.1f}% upsell target",
            delta_color="off",
            help="Orders with only 1 item — prime candidates for cross-selling recommendations",
        )

    # ── Mine Association Rules ───────────────────────────────────────────────
    rules_df = mine_association_rules(
        m_df,
        id_col=id_col,
        item_col=target_item_col,
        min_cooccurrence=min_co,
    )

    if lift_filter == "Positive Affinity (Lift ≥ 1.0)":
        filtered_rules = rules_df[rules_df["Lift"] >= 1.0].copy()
    elif lift_filter == "High Affinity (Lift ≥ 1.5)":
        filtered_rules = rules_df[rules_df["Lift"] >= 1.5].copy()
    else:
        filtered_rules = rules_df.copy()

    # ── Charts Section ───────────────────────────────────────────────────────
    c_ch1, c_ch2 = st.columns([1, 2])

    with c_ch1:
        st.markdown("##### 📊 Basket Size Distribution")
        dist_data = metrics["size_distribution"]
        dist_df = pd.DataFrame(
            [
                {
                    "Basket Size": k,
                    "Orders": v,
                    "Share": (v / tot_orders * 100.0) if tot_orders > 0 else 0.0,
                }
                for k, v in dist_data.items()
            ]
        )
        fig_dist = px.bar(
            dist_df,
            x="Basket Size",
            y="Orders",
            text="Orders",
            color="Basket Size",
            color_discrete_sequence=["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b"],
        )
        fig_dist.update_traces(
            texttemplate="%{text} (%{customdata[0]:.1f}%)",
            customdata=dist_df[["Share"]].values,
            textposition="outside",
        )
        fig_dist.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=320,
            showlegend=False,
            margin=dict(t=20, b=20, l=10, r=10),
            yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.15)"),
            xaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    with c_ch2:
        st.markdown("##### 🔗 Top Co-Purchased Bundles")
        if not filtered_rules.empty:
            top_pairs_chart = filtered_rules.head(10).iloc[
                ::-1
            ]  # Reverse for horizontal bar chart
            fig_pairs = px.bar(
                top_pairs_chart,
                x="Co_Orders",
                y="Pair",
                orientation="h",
                text="Co_Orders",
                color="Lift",
                color_continuous_scale="Purples",
            )
            fig_pairs.update_traces(
                texttemplate="  %{text} orders (Lift: %{customdata[0]:.2f}x)",
                customdata=top_pairs_chart[["Lift"]].values,
                textposition="inside",
            )
            fig_pairs.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=320,
                margin=dict(t=20, b=20, l=10, r=10),
                xaxis=dict(
                    showgrid=True, gridcolor="rgba(128,128,128,0.15)", title="Co-Orders"
                ),
                yaxis=dict(showgrid=False, title=""),
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig_pairs, use_container_width=True)
        else:
            st.info(
                f"No frequent product pairs met the threshold (Min Co-Orders = {min_co}). "
                "Try lowering the Min Co-Orders filter above."
            )

    # ── Association Rules Data Table ─────────────────────────────────────────
    st.markdown("##### 📋 Association Rules & Co-Occurrence Table")
    if not filtered_rules.empty:
        display_rules = filtered_rules.copy()
        display_rules["Support %"] = display_rules["Support_Pct"].apply(
            lambda v: f"{v:.2f}%"
        )
        display_rules["Conf A→B"] = display_rules["Confidence_A_to_B_Pct"].apply(
            lambda v: f"{v:.1f}%"
        )
        display_rules["Conf B→A"] = display_rules["Confidence_B_to_A_Pct"].apply(
            lambda v: f"{v:.1f}%"
        )
        display_rules["Lift"] = display_rules["Lift"].apply(lambda v: f"{v:.2f}x")

        table_cols = [
            "Item A",
            "Item B",
            "Co_Orders",
            "Support %",
            "Conf A→B",
            "Conf B→A",
            "Lift",
            "Affinity",
        ]
        st.dataframe(
            display_rules[table_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Co_Orders": st.column_config.NumberColumn(
                    "Co-Orders", help="Number of orders containing both items"
                ),
                "Support %": st.column_config.TextColumn(
                    "Support", help="% of all orders containing this pair"
                ),
                "Conf A→B": st.column_config.TextColumn(
                    "Conf (A→B)", help="% of Item A buyers who also bought Item B"
                ),
                "Conf B→A": st.column_config.TextColumn(
                    "Conf (B→A)", help="% of Item B buyers who also bought Item A"
                ),
                "Lift": st.column_config.TextColumn(
                    "Lift Score", help=">1.0 means positive association"
                ),
                "Affinity": st.column_config.TextColumn("Affinity Rating"),
            },
        )

        # CSV Export
        csv_bytes = filtered_rules.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Download Association Rules (CSV)",
            data=csv_bytes,
            file_name=f"market_basket_rules_{selected_level.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            key="mba_download_rules_csv",
        )
    else:
        st.info("No association pairs available with the current filter settings.")

    # ── Interactive "What Sells With This?" Cross-Sell Explorer ──────────────
    st.divider()
    st.markdown('##### 🔍 Cross-Sell Explorer: "What Sells With This?"')
    st.caption(
        "Select any product to see which items are most frequently added to the same cart."
    )

    all_products = sorted(
        m_df[target_item_col].dropna().astype(str).str.strip().unique().tolist()
    )
    all_products = [p for p in all_products if p]

    if all_products and not rules_df.empty:
        c_prod, c_empty = st.columns([2, 1])
        with c_prod:
            sel_product = st.selectbox(
                "Select Product to Analyze:",
                all_products,
                key="mba_selected_product_lookup",
            )

        if sel_product:
            cross_sells = get_product_cross_sells(rules_df, sel_product, top_n=8)
            if not cross_sells.empty:
                st.markdown(f"**Top Cross-Sell Recommendations for `{sel_product}`:**")
                cross_sells_disp = cross_sells.copy()
                cross_sells_disp["Confidence %"] = cross_sells_disp[
                    "Confidence_Pct"
                ].apply(lambda v: f"{v:.1f}%")
                cross_sells_disp["Lift"] = cross_sells_disp["Lift"].apply(
                    lambda v: f"{v:.2f}x"
                )
                cross_sells_disp["Recommendation Strategy"] = cross_sells_disp[
                    "Lift"
                ].apply(
                    lambda v: (
                        "🔥 Combo Bundle / Checkout Bump"
                        if float(str(v).replace("x", "")) >= 1.5
                        else "✨ Recommended Cross-Sell"
                    )
                )

                st.dataframe(
                    cross_sells_disp[
                        [
                            "Recommended_Item",
                            "Co_Orders",
                            "Confidence %",
                            "Lift",
                            "Affinity",
                            "Recommendation Strategy",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Recommended_Item": st.column_config.TextColumn(
                            "🛍️ Recommended Product"
                        ),
                        "Co_Orders": st.column_config.NumberColumn("Co-Orders"),
                        "Confidence %": st.column_config.TextColumn(
                            "Attachment Rate",
                            help="Probability customer buys this when buying selected product",
                        ),
                        "Lift": st.column_config.TextColumn("Lift"),
                    },
                )
            else:
                st.info(
                    f"No multi-item orders found containing `{sel_product}` with other products yet."
                )
    else:
        st.info("Product list not available or no multi-item orders in dataset.")

    # ── Category-to-Category Association (Expander) ──────────────────────────
    if "Category" in m_df.columns and m_df["Category"].nunique() > 1:
        with st.expander(
            "📁 Cross-Category Affinity (Department Combinations)", expanded=False
        ):
            st.caption(
                "See which distinct product categories customers frequently combine in single orders."
            )
            cat_rules = compute_category_associations(
                m_df, id_col=id_col, cat_col="Category", min_cooccurrence=1
            )
            if not cat_rules.empty:
                cat_display = cat_rules.head(15).copy()
                cat_display["Support %"] = cat_display["Support_Pct"].apply(
                    lambda v: f"{v:.2f}%"
                )
                cat_display["Conf A→B"] = cat_display["Confidence_A_to_B_Pct"].apply(
                    lambda v: f"{v:.1f}%"
                )
                cat_display["Lift"] = cat_display["Lift"].apply(lambda v: f"{v:.2f}x")
                st.dataframe(
                    cat_display[
                        [
                            "Item A",
                            "Item B",
                            "Co_Orders",
                            "Support %",
                            "Conf A→B",
                            "Lift",
                            "Affinity",
                        ]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No cross-category orders detected.")

    # ── Excluded Orders Banner / Info ────────────────────────────────────────
    if raw_df is not None and not raw_df.empty:
        raw_status_col = next(
            (c for c in ["Order Status", "Status"] if c in raw_df.columns), None
        )
        if raw_status_col:
            excl_mask = (
                raw_df[raw_status_col].astype(str).str.lower().isin(EXCLUDED_STATUSES)
            )
            excl_cnt = (
                int(raw_df[excl_mask]["Order ID"].nunique())
                if "Order ID" in raw_df.columns
                else int(excl_mask.sum())
            )
            if excl_cnt > 0:
                with st.expander(
                    f"🚫 Note on Excluded Orders ({excl_cnt:,} non-sales orders filtered)",
                    expanded=False,
                ):
                    st.caption(
                        "Orders with status `cancelled`, `failed`, `pending`, `on-hold`, or `refunded` "
                        "are excluded from Market Basket Analysis to ensure affinity patterns reflect actual confirmed customer demand."
                    )

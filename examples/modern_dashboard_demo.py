"""Example usage of the modern KPI dashboard component.

This demonstrates how to use the render_modern_kpi_cards function
in a Streamlit application following the five design principles:

1. Flat Accents, Not Gradients - Single accent color for meaning
2. Make the Number the Hero - No colored tiles, data is visual focus  
3. Clear Hierarchy - Primary metric larger, secondary metrics smaller
4. Refined Shadows/Corners - Hairline borders, 6px radii
5. Meaningful Data - Explicit time periods, tabular nums, sparkline trends
"""

import pandas as pd
import streamlit as st

from src.components.dashboard.modern_kpi import render_modern_kpi_cards


def create_sample_data():
    """Create sample order data for demonstration."""
    dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq="h")
    
    data = {
        "Order ID": [f"ORD-{i:05d}" for i in range(100)],
        "Order Date": dates,
        "Order Status": ["completed"] * 70 + ["pending"] * 20 + ["cancelled"] * 10,
        "Quantity": [1, 2, 3, 1, 2] * 20,
        "Item Cost": [100, 250, 150, 200, 300] * 20,
        "Gross Amount": [100, 500, 450, 200, 600] * 20,
        "Cashback Discount": [10, 50, 45, 20, 60] * 20,
        "Total Amount": [90, 450, 405, 180, 540] * 20,
        "Customer Phone": [f"017{str(i).zfill(8)}" for i in range(100)],
    }
    
    return pd.DataFrame(data)


def main():
    st.set_page_config(layout="wide", page_title="Modern Dashboard Demo")
    
    # Inject custom styles (includes the new KPI card styles)
    from src.components.ui.styles import inject_base_styles
    inject_base_styles()
    
    st.title("📊 Modern KPI Dashboard")
    st.markdown("""
    This dashboard demonstrates **five key design principles** for human-centric data visualization:
    
    1. **Flat Accents, Not Gradients** - Single accent color (#2563eb) conveys meaning, not decoration
    2. **Make the Number the Hero** - No colored tiles or decorative icons, data is the focus
    3. **Clear Hierarchy** - Revenue (primary) is larger than supporting metrics
    4. **Refined Shadows/Corners** - 6px border radius, hairline borders, shadows only on floating elements
    5. **Meaningful Data Displays** - Explicit time periods, tabular numbers, sparkline trends
    """)
    
    st.header("Live Metrics")
    
    # Create sample data
    m_df = create_sample_data()
    c_df = create_sample_data().head(50)  # Previous period comparison
    
    # Dummy mappings for demo
    dummy_mapping = {}
    wc_raw_mapping = {
        "date": "Order Date",
        "order_id": "Order ID",
        "status": "Order Status",
    }
    
    # Render the modern KPI cards
    drill, summ, top, basket = render_modern_kpi_cards(
        m_df=m_df,
        c_df=c_df,
        nav_mode="Today",
        dummy_mapping=dummy_mapping,
        wc_raw_mapping=wc_raw_mapping,
    )
    
    st.header("Design Details")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("✅ What We Avoided")
        st.markdown("""
        - ❌ Purple-to-blue gradient decorations
        - ❌ Icons inside pastel-colored tiles
        - ❌ All metrics same size/weight
        - ❌ 16px rounded corners everywhere
        - ❌ Generic "Welcome back!" greetings
        - ❌ Shapeless numbers without context
        """)
    
    with col2:
        st.subheader("✅ What We Implemented")
        st.markdown("""
        - ✅ Flat accent colors with semantic meaning
        - ✅ Numbers as visual heroes (tabular-nums)
        - ✅ Visual hierarchy (primary vs secondary)
        - ✅ 6px border radius, hairline borders
        - ✅ Explicit time period labels
        - ✅ Sparklines showing 36-hour trends
        """)
    
    st.divider()
    
    st.subheader("🎨 CSS Classes Available")
    st.code("""
/* Container */
.kpi-container

/* Card types */
.kpi-card              /* Base card */
.kpi-card-primary      /* Larger, prominent */
.kpi-card-secondary    /* Smaller, supporting */

/* Content elements */
.kpi-label             /* Metric label */
.kpi-value             /* Metric value */
.kpi-value-primary     /* Larger value */
.kpi-prev              /* Previous period badge */

/* Delta indicators */
.kpi-delta             /* Base delta */
.kpi-delta-up          /* Green positive */
.kpi-delta-down        /* Red negative */
.kpi-delta-warning     /* Amber warning */
""", language="css")


if __name__ == "__main__":
    main()

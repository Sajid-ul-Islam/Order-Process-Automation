"""Unit tests for executive briefing gross format and product listing summary row."""

import pandas as pd
from src.processing.data_processing import generate_executive_briefing


def test_generate_executive_briefing_gross_only():
    """Executive briefing must use Gross Revenue and exclude cashback/net realized text."""
    report = generate_executive_briefing(
        today_rev=100000,
        today_qty=50,
        today_orders=25,
        today_aov=4000,
        dm={"last_shipped_order": "1001", "last_pathao_print": "1001"},
        top=pd.DataFrame(
            [{"Clean_Product": "Product A", "Total Qty": 10, "Total Amount": 25000}]
        ),
        gross_rev=100000,
        cashback_disc=5000,
    )

    # Must contain Gross Revenue and Avg Basket Value
    assert "Gross Revenue" in report
    assert "Avg Basket Value" in report
    assert "৳100,000" in report

    # Must NOT contain Net Realized or Cashback mentions
    assert "NET REALIZED REVENUE" not in report
    assert "Net Realized" not in report
    assert "Cashback" not in report
    assert "Pre-Discount" not in report
    assert "Post-Cashback" not in report


def test_product_listing_summary_row_structure():
    """Verify summary row calculation logic for product listing."""
    df = pd.DataFrame(
        {
            "Item Name": ["Item 1", "Item 1", "Item 2"],
            "SKU": ["SKU-1", "SKU-1", "SKU-2"],
            "Quantity": [2, 3, 5],
            "Order ID": [101, 102, 103],
            "Order Date": [
                "2026-09-10 10:00:00",
                "2026-09-10 11:00:00",
                "2026-09-11 12:00:00",
            ],
        }
    )

    merged = (
        df.groupby(["Item Name", "SKU"], as_index=False)["Quantity"]
        .sum()
        .sort_values(by="Quantity", ascending=False)
        .reset_index(drop=True)
    )
    tot_units = int(merged["Quantity"].sum())
    unique_orders = df["Order ID"].nunique()
    last_order = str(
        df.sort_values(by="Order Date", ascending=False)["Order ID"].iloc[0]
    )
    latest_date = pd.to_datetime(df["Order Date"]).max().strftime("%d %b %Y")

    summary_row = {
        "Item Name": f"TOTAL: {unique_orders} Orders | Last Order: #{last_order}",
        "SKU": f"Date: {latest_date}",
        "Quantity": tot_units,
    }
    display_df = pd.concat([merged, pd.DataFrame([summary_row])], ignore_index=True)

    assert tot_units == 10
    last_row = display_df.iloc[-1]
    assert "TOTAL: 3 Orders" in str(last_row["Item Name"])
    assert "#103" in str(last_row["Item Name"])
    assert last_row["Quantity"] == 10


def test_product_listing_column_auto_detection():
    """Verify that product listing column autodetection identifies standard and variant headers."""
    from src.processing.column_detection import (
        DATE_COL_CANDIDATES,
        ITEM_NAME_COL_CANDIDATES,
        ORDER_ID_COL_CANDIDATES,
        QTY_COL_CANDIDATES,
        SKU_COL_CANDIDATES,
        detect_column,
        find_columns,
    )

    # Standard WooCommerce schema
    wc_df = pd.DataFrame(
        columns=[
            "Order ID",
            "Order Status",
            "Date",
            "Customer Name",
            "Phone (Billing)",
            "Item Name",
            "SKU",
            "Quantity",
            "Item Cost",
            "Total Amount",
        ]
    )
    det = find_columns(wc_df)
    assert (
        detect_column(wc_df, ITEM_NAME_COL_CANDIDATES)
        or det.get("item")
        or det.get("name")
    ) == "Item Name"
    assert (detect_column(wc_df, SKU_COL_CANDIDATES) or det.get("sku")) == "SKU"
    assert (detect_column(wc_df, QTY_COL_CANDIDATES) or det.get("qty")) == "Quantity"
    assert (
        detect_column(wc_df, ORDER_ID_COL_CANDIDATES) or det.get("order_id")
    ) == "Order ID"
    assert (detect_column(wc_df, DATE_COL_CANDIDATES) or det.get("date")) == "Date"

    # Exported warehouse picking CSV with custom header variations
    custom_df = pd.DataFrame(
        columns=[
            "invoice_number",
            "created_date",
            "product_title",
            "barcode",
            "item_quantity",
        ]
    )
    det_custom = find_columns(custom_df)
    assert (
        detect_column(custom_df, ITEM_NAME_COL_CANDIDATES)
        or det_custom.get("item")
        or det_custom.get("name")
    ) == "product_title"
    assert (
        detect_column(custom_df, SKU_COL_CANDIDATES) or det_custom.get("sku")
    ) == "barcode"
    assert (
        detect_column(custom_df, QTY_COL_CANDIDATES) or det_custom.get("qty")
    ) == "item_quantity"
    assert (
        detect_column(custom_df, ORDER_ID_COL_CANDIDATES) or det_custom.get("order_id")
    ) == "invoice_number"
    assert (
        detect_column(custom_df, DATE_COL_CANDIDATES) or det_custom.get("date")
    ) == "created_date"


def test_aggregate_data_and_donut_chart_handles_nan_quantity():
    """Verify that aggregate_data and category charts handle NaNs in Quantity and Total Amount without producing NaN Total Qty."""
    import numpy as np
    from src.processing.data_processing import aggregate_data

    df = pd.DataFrame(
        {
            "Product Name": ["Item A", "Item A", "Item B"],
            "SKU": ["A-1", "A-1", "B-1"],
            "Category": ["Shirt", "Shirt", "Panjabi"],
            "Sub-Category": ["Formal", "Formal", "Panjabi"],
            "Quantity": [2.0, np.nan, 3.0],
            "Total Amount": [2000.0, np.nan, 3500.0],
            "Item Cost": [1000.0, 1000.0, 1166.67],
            "Clean_Product": ["Item A", "Item A", "Item B"],
            "Is_Bundle_Combo": [False, False, False],
        }
    )

    drill, summ, top, basket = aggregate_data(df, {})
    assert summ is not None
    assert not summ["Total Qty"].isna().any(), "Total Qty in summ must not contain any NaN"
    assert not summ["Total Amount"].isna().any(), "Total Amount in summ must not contain any NaN"
    assert summ.loc[summ["Category"] == "Shirt", "Total Qty"].iloc[0] == 2.0
    assert summ.loc[summ["Category"] == "Shirt", "Total Amount"].iloc[0] == 2000.0

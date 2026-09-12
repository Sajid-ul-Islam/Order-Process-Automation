"""Unit tests for everyday product-wise shipped/completed order list export."""

import pandas as pd
from datetime import date, datetime
import pytest

from src.processing.completed_analytics import filter_shipped_order_items
from src.services.exports.excel_exporter import export_to_styled_excel


@pytest.fixture
def sample_orders_df():
    return pd.DataFrame(
        [
            # Order 1: Shipped today (2 distinct products)
            {
                "Order ID": 1001,
                "Order Status": "shipped",
                "Item Name": "Premium Panjabi Black",
                "SKU": "PAN-BLK-M",
                "Quantity": 2,
                "Item Cost": 1500.0,
                "mod_dt_parsed": "2026-09-12 11:30:00",
                "dt_parsed": "2026-09-12 09:00:00",
                "Full Name (Billing)": "Customer One",
                "Phone (Billing)": "01711111111",
                "Shipping City": "Dhaka",
                "Order Source": "Online",
            },
            {
                "Order ID": 1001,
                "Order Status": "shipped",
                "Item Name": "Cotton Pajama White",
                "SKU": "PAJ-WHT-L",
                "Quantity": 1,
                "Item Cost": 600.0,
                "mod_dt_parsed": "2026-09-12 11:30:00",
                "dt_parsed": "2026-09-12 09:00:00",
                "Full Name (Billing)": "Customer One",
                "Phone (Billing)": "01711111111",
                "Shipping City": "Dhaka",
                "Order Source": "Online",
            },
            # Order 2: Completed yesterday (1 product)
            {
                "Order ID": 1002,
                "Order Status": "completed",
                "Item Name": "Silk Attar 12ml",
                "SKU": "ATR-SLK-12",
                "Quantity": 3,
                "Item Cost": 450.0,
                "mod_dt_parsed": "2026-09-11 16:20:00",
                "dt_parsed": "2026-09-11 10:00:00",
                "Full Name (Billing)": "Customer Two",
                "Phone (Billing)": "01822222222",
                "Shipping City": "Chittagong",
                "Order Source": "Outlet",
            },
            # Order 3: Processing (should be excluded from shipped export)
            {
                "Order ID": 1003,
                "Order Status": "processing",
                "Item Name": "Prayer Cap Navy",
                "SKU": "CAP-NVY-S",
                "Quantity": 1,
                "Item Cost": 250.0,
                "mod_dt_parsed": "2026-09-12 12:00:00",
                "dt_parsed": "2026-09-12 08:30:00",
                "Full Name (Billing)": "Customer Three",
                "Phone (Billing)": "01933333333",
                "Shipping City": "Sylhet",
                "Order Source": "Online",
            },
            # Order 4: Cancelled (should be excluded)
            {
                "Order ID": 1004,
                "Order Status": "cancelled",
                "Item Name": "Kufi White",
                "SKU": "KUF-WHT-M",
                "Quantity": 1,
                "Item Cost": 200.0,
                "mod_dt_parsed": "2026-09-12 10:00:00",
                "dt_parsed": "2026-09-12 07:00:00",
                "Full Name (Billing)": "Customer Four",
                "Phone (Billing)": "01644444444",
                "Shipping City": "Khulna",
                "Order Source": "Online",
            },
        ]
    )


def test_filter_shipped_order_items_product_wise(sample_orders_df):
    """Verify that multiple line items for the same order are all preserved (product-wise)."""
    target_d = date(2026, 9, 12)
    filtered = filter_shipped_order_items(sample_orders_df, start_date=target_d, end_date=target_d)

    # Order 1001 has 2 items on 2026-09-12; Order 1003 is processing (excluded); Order 1004 is cancelled (excluded)
    assert len(filtered) == 2
    assert set(filtered["SKU"]) == {"PAN-BLK-M", "PAJ-WHT-L"}
    assert filtered["Order ID"].nunique() == 1
    assert filtered["Quantity"].sum() == 3


def test_filter_shipped_order_items_date_filtering(sample_orders_df):
    """Verify single date and date range selection."""
    # Yesterday only
    y_filtered = filter_shipped_order_items(
        sample_orders_df, start_date=date(2026, 9, 11), end_date=date(2026, 9, 11)
    )
    assert len(y_filtered) == 1
    assert y_filtered.iloc[0]["Order ID"] == 1002
    assert y_filtered.iloc[0]["SKU"] == "ATR-SLK-12"

    # 2-day date range (Sept 11 to Sept 12)
    range_filtered = filter_shipped_order_items(
        sample_orders_df, start_date=date(2026, 9, 11), end_date=date(2026, 9, 12)
    )
    assert len(range_filtered) == 3
    assert set(range_filtered["Order ID"]) == {1001, 1002}


def test_filter_shipped_order_items_source_filter(sample_orders_df):
    """Verify filtering by Online vs Outlet order source."""
    online_items = filter_shipped_order_items(
        sample_orders_df,
        start_date=date(2026, 9, 11),
        end_date=date(2026, 9, 12),
        source_filter="Online",
    )
    assert len(online_items) == 2
    assert all(online_items["Order ID"] == 1001)

    outlet_items = filter_shipped_order_items(
        sample_orders_df,
        start_date=date(2026, 9, 11),
        end_date=date(2026, 9, 12),
        source_filter="Outlet",
    )
    assert len(outlet_items) == 1
    assert outlet_items.iloc[0]["Order ID"] == 1002


def test_export_to_styled_excel_with_shipped_items(sample_orders_df):
    """Verify styled Excel export produces valid bytes with grouping by Order ID."""
    target_d = date(2026, 9, 12)
    filtered = filter_shipped_order_items(sample_orders_df, start_date=target_d, end_date=target_d)
    excel_bytes = export_to_styled_excel({"Shipped Items": filtered}, group_by_col="Order ID")
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 1000


def test_classify_order_source_checkout_vs_pos():
    """Verify that Online filter strictly isolates website checkout orders and excludes POS/outlet counter orders."""
    from src.processing.completed_analytics import classify_order_source

    # Website checkout orders
    online_row1 = pd.Series({"Payment Method Title": "Cash on delivery", "Order ID": "15001"})
    online_row2 = pd.Series({"Payment Method Title": "Pay Online(Credit/Debit Card/MobileBanking/NetBanking/bKash)", "Order ID": "15002"})
    online_row3 = pd.Series({"Created via": "checkout", "Payment Method Title": "bKash", "Order ID": "15003"})
    online_row4 = pd.Series({"Payment Method Title": "Ecom", "Order ID": "15004"})

    assert classify_order_source(online_row1) == "Online"
    assert classify_order_source(online_row2) == "Online"
    assert classify_order_source(online_row3) == "Online"
    assert classify_order_source(online_row4) == "Online"

    # Outlet / POS orders
    pos_row1 = pd.Series({"Payment Method Title": "Cash", "Order ID": "14248"})
    pos_row2 = pd.Series({"Payment Method Title": "UCB", "Order ID": "14241"})
    pos_row3 = pd.Series({"Payment Method Title": "City Bank", "Order ID": "14058"})
    pos_row4 = pd.Series({"Payment Method Title": "Split: bKash + Cash", "Order ID": "14022"})
    pos_row5 = pd.Series({"Order ID": "15005 c", "Payment Method Title": "Cash on delivery"})  # Cumilla outlet order ID
    pos_row6 = pd.Series({"Created via": "pos", "Order ID": "15006"})

    assert classify_order_source(pos_row1) == "Outlet"
    assert classify_order_source(pos_row2) == "Outlet"
    assert classify_order_source(pos_row3) == "Outlet"
    assert classify_order_source(pos_row4) == "Outlet"
    assert classify_order_source(pos_row5) == "Outlet"
    assert classify_order_source(pos_row6) == "Outlet"


def test_order_placed_any_date_shipped_target_date_exported():
    """Verify that an order placed on any past date is exported if it was shipped/completed on the target date."""
    backlog_order = pd.DataFrame(
        [
            {
                "Order ID": 8888,
                "Order Status": "shipped",
                "Item Name": "Classic Panjabi",
                "SKU": "PAN-CLS-L",
                "Quantity": 1,
                "Item Cost": 1800.0,
                # Placed 10 days ago:
                "dt_parsed": "2026-09-02 14:00:00",
                # Shipped today:
                "mod_dt_parsed": "2026-09-12 11:30:00",
                "Payment Method Title": "Cash on delivery",
            }
        ]
    )

    # 1. When querying for Today (2026-09-12), it MUST be included because it was shipped today
    today_export = filter_shipped_order_items(
        backlog_order, start_date=date(2026, 9, 12), end_date=date(2026, 9, 12)
    )
    assert len(today_export) == 1
    assert today_export.iloc[0]["Order ID"] == 8888
    assert today_export.iloc[0]["SKU"] == "PAN-CLS-L"

    # 2. When querying for the day it was placed (2026-09-02), it must NOT be included as shipped on that day
    placed_day_export = filter_shipped_order_items(
        backlog_order, start_date=date(2026, 9, 2), end_date=date(2026, 9, 2)
    )
    assert len(placed_day_export) == 0



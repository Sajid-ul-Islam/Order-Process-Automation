"""Unit tests for detect_active_campaign in src.processing.data_processing."""

import pandas as pd
from src.processing.data_processing import detect_active_campaign


def test_detect_campaign_none_or_empty():
    res = detect_active_campaign(None)
    assert res["is_active"] is False
    assert res["campaign_type"] == "none"

    res_empty = detect_active_campaign(pd.DataFrame())
    assert res_empty["is_active"] is False


def test_detect_flat_50_percent_sale():
    df = pd.DataFrame(
        {
            "Order ID": ["101", "102"],
            "Item Name": ["Product A", "Product B"],
            "Quantity": [1, 1],
            "Subtotal Cost": [1000.0, 2000.0],
            "Item Cost": [500.0, 1000.0],
            "Item Discount": [500.0, 1000.0],
            "Total Amount": [500.0, 1000.0],
            "Cashback Discount": [500.0, 1000.0],
            "Fee Notes": ["", ""],
            "Coupons": ["", ""],
        }
    )
    camp = detect_active_campaign(df)
    assert camp["is_active"] is True
    assert camp["campaign_type"] == "flat_sale"
    assert "Flat 50% Sale" in camp["campaign_name"]
    assert camp["total_discount"] == 1500.0
    assert camp["discount_rate_pct"] == 50.0


def test_detect_cashback_campaign():
    df = pd.DataFrame(
        {
            "Order ID": ["201", "202"],
            "Item Name": ["Item 1", "Item 2"],
            "Quantity": [1, 1],
            "Subtotal Cost": [1000.0, 1000.0],
            "Item Cost": [1000.0, 1000.0],
            "Item Discount": [0.0, 0.0],
            "Fee Discount Total": [100.0, 100.0],
            "Cashback Discount": [100.0, 100.0],
            "Fee Notes": ["Cashback Reward: -TK 100", "Cashback: -TK 100"],
            "Total Amount": [900.0, 900.0],
        }
    )
    camp = detect_active_campaign(df)
    assert camp["is_active"] is True
    assert camp["campaign_type"] == "cashback"
    assert "Cashback" in camp["campaign_name"]
    assert camp["total_discount"] == 200.0


def test_detect_coupon_sale():
    df = pd.DataFrame(
        {
            "Order ID": ["301"],
            "Item Name": ["Item 1"],
            "Quantity": [1],
            "Item Discount": [300.0],
            "Coupons": ["SUMMER20"],
            "Total Amount": [1200.0],
        }
    )
    camp = detect_active_campaign(df)
    assert camp["is_active"] is True
    assert camp["campaign_type"] == "coupon"
    assert "SUMMER20" in camp["campaign_name"]


def test_no_campaign_when_discounts_zero():
    df = pd.DataFrame(
        {
            "Order ID": ["401", "402"],
            "Item Name": ["Item 1", "Item 2"],
            "Quantity": [1, 1],
            "Subtotal Cost": [1000.0, 1000.0],
            "Item Cost": [1000.0, 1000.0],
            "Item Discount": [0.0, 0.0],
            "Total Amount": [1000.0, 1000.0],
            "Fee Notes": ["", ""],
            "Coupons": ["", ""],
        }
    )
    camp = detect_active_campaign(df)
    assert camp["is_active"] is False
    assert camp["total_discount"] == 0.0

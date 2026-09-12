"""Unit tests for Market Basket Analysis stateless processing engine."""

import pandas as pd
import pytest

from src.processing.market_basket import (
    compute_basket_summary_metrics,
    compute_category_associations,
    get_product_cross_sells,
    mine_association_rules,
)


@pytest.fixture
def sample_orders_df():
    # 5 Orders:
    # Order 101: Panjabi, Pajama, Perfume (3 items)
    # Order 102: Panjabi, Pajama (2 items)
    # Order 103: Shirt, Chino (2 items)
    # Order 104: Panjabi, Shirt (2 items)
    # Order 105: Panjabi (1 item)
    data = [
        {
            "Order ID": "101",
            "Clean_Product": "Panjabi",
            "Quantity": 1,
            "Category": "Ethnic",
        },
        {
            "Order ID": "101",
            "Clean_Product": "Pajama",
            "Quantity": 1,
            "Category": "Ethnic",
        },
        {
            "Order ID": "101",
            "Clean_Product": "Perfume",
            "Quantity": 1,
            "Category": "Fragrance",
        },
        {
            "Order ID": "102",
            "Clean_Product": "Panjabi",
            "Quantity": 2,
            "Category": "Ethnic",
        },
        {
            "Order ID": "102",
            "Clean_Product": "Pajama",
            "Quantity": 1,
            "Category": "Ethnic",
        },
        {
            "Order ID": "103",
            "Clean_Product": "Shirt",
            "Quantity": 1,
            "Category": "Casual",
        },
        {
            "Order ID": "103",
            "Clean_Product": "Chino",
            "Quantity": 1,
            "Category": "Bottoms",
        },
        {
            "Order ID": "104",
            "Clean_Product": "Panjabi",
            "Quantity": 1,
            "Category": "Ethnic",
        },
        {
            "Order ID": "104",
            "Clean_Product": "Shirt",
            "Quantity": 1,
            "Category": "Casual",
        },
        {
            "Order ID": "105",
            "Clean_Product": "Panjabi",
            "Quantity": 1,
            "Category": "Ethnic",
        },
    ]
    return pd.DataFrame(data)


def test_compute_basket_summary_metrics(sample_orders_df):
    metrics = compute_basket_summary_metrics(sample_orders_df)

    assert metrics["total_orders"] == 5
    # Multi-item orders: 101, 102, 103, 104 -> 4 out of 5 (80%)
    assert metrics["multi_item_orders"] == 4
    assert metrics["single_item_orders"] == 1
    assert metrics["multi_item_rate"] == 80.0
    assert metrics["max_basket_items"] == 3

    # Size distribution
    assert metrics["size_distribution"]["1 Item"] == 1
    assert metrics["size_distribution"]["2 Items"] == 3
    assert metrics["size_distribution"]["3 Items"] == 1
    assert metrics["size_distribution"]["4+ Items"] == 0

    # Top pair should be ('Pajama', 'Panjabi') appearing in orders 101 and 102 (count = 2)
    assert metrics["top_pair_count"] == 2
    assert set(metrics["top_pair"]) == {"Panjabi", "Pajama"}


def test_mine_association_rules(sample_orders_df):
    rules = mine_association_rules(sample_orders_df, min_cooccurrence=1)
    assert not rules.empty
    assert "Item A" in rules.columns
    assert "Item B" in rules.columns
    assert "Co_Orders" in rules.columns
    assert "Support_Pct" in rules.columns
    assert "Confidence_A_to_B_Pct" in rules.columns
    assert "Confidence_B_to_A_Pct" in rules.columns
    assert "Lift" in rules.columns
    assert "Affinity" in rules.columns

    # Pair (Pajama, Panjabi):
    # Co_Orders = 2
    # Total Orders = 5 -> Support = 2 / 5 = 40.0%
    # Panjabi is in 4 orders (101, 102, 104, 105)
    # Pajama is in 2 orders (101, 102)
    # Conf(Panjabi -> Pajama) = 2 / 4 = 50.0%
    # Conf(Pajama -> Panjabi) = 2 / 2 = 100.0%
    # Lift = 2 * 5 / (4 * 2) = 10 / 8 = 1.25
    panjabi_pajama = rules[
        ((rules["Item A"] == "Pajama") & (rules["Item B"] == "Panjabi"))
        | ((rules["Item A"] == "Panjabi") & (rules["Item B"] == "Pajama"))
    ]
    assert len(panjabi_pajama) == 1
    row = panjabi_pajama.iloc[0]
    assert row["Co_Orders"] == 2
    assert row["Support_Pct"] == 40.0
    assert row["Lift"] == 1.25


def test_get_product_cross_sells(sample_orders_df):
    rules = mine_association_rules(sample_orders_df, min_cooccurrence=1)
    pajama_cross = get_product_cross_sells(rules, "Pajama")
    assert not pajama_cross.empty
    # Top recommendation for Pajama should be Panjabi with 100% confidence
    top_rec = pajama_cross.iloc[0]
    assert top_rec["Recommended_Item"] == "Panjabi"
    assert top_rec["Confidence_Pct"] == 100.0


def test_compute_category_associations(sample_orders_df):
    cat_rules = compute_category_associations(sample_orders_df, cat_col="Category")
    assert not cat_rules.empty
    # Ethnic + Fragrance (Order 101), Casual + Bottoms (Order 103), Ethnic + Casual (Order 104)
    pairs = set(cat_rules["Pair"].tolist())
    assert any("Casual" in p for p in pairs)


def test_empty_and_edge_cases():
    empty_df = pd.DataFrame()
    assert compute_basket_summary_metrics(empty_df)["total_orders"] == 0
    assert mine_association_rules(empty_df).empty
    assert get_product_cross_sells(empty_df, "Item").empty

    single_item_df = pd.DataFrame(
        [
            {"Order ID": "1", "Clean_Product": "A"},
            {"Order ID": "2", "Clean_Product": "B"},
        ]
    )
    metrics = compute_basket_summary_metrics(single_item_df)
    assert metrics["total_orders"] == 2
    assert metrics["multi_item_orders"] == 0
    assert metrics["multi_item_rate"] == 0.0
    assert mine_association_rules(single_item_df).empty

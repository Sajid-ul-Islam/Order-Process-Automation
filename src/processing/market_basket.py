"""Market Basket Analysis (MBA) stateless processing module.

Provides algorithmic mining of itemsets, co-purchase frequencies, support,
confidence, lift, and basket-level distributions. Strictly adheres to DEEN-OPS
Layer Separation: pure pandas/python, zero Streamlit or UI dependencies.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
import typing

import pandas as pd


def detect_id_and_item_cols(
    df: pd.DataFrame,
    preferred_item_col: str | None = None,
) -> tuple[str | None, str | None]:
    """Identify the best order identifier and product/item column from dataframe."""
    if df is None or len(df.columns) == 0:
        return None, None

    # Candidate order ID columns in priority order
    id_candidates = ["Order ID", "Order Number", "order_id", "order_number", "ID"]
    id_col = next((col for col in id_candidates if col in df.columns), None)

    # Candidate item columns
    if preferred_item_col and preferred_item_col in df.columns:
        item_col = preferred_item_col
    else:
        item_candidates = [
            "Clean_Product",
            "Product Name",
            "Item Name",
            "product_name",
            "item_name",
            "SKU",
        ]
        item_col = next((col for col in item_candidates if col in df.columns), None)

    return id_col, item_col


def compute_basket_summary_metrics(
    df: pd.DataFrame,
    id_col: str | None = None,
    item_col: str | None = None,
    qty_col: str | None = None,
) -> dict[str, typing.Any]:
    """Compute basket-level summary statistics including multi-item rates and size distribution."""
    empty_result = {
        "total_orders": 0,
        "multi_item_orders": 0,
        "single_item_orders": 0,
        "multi_item_rate": 0.0,
        "avg_basket_items": 0.0,
        "avg_basket_qty": 0.0,
        "max_basket_items": 0,
        "top_pair": None,
        "top_pair_count": 0,
        "size_distribution": {
            "1 Item": 0,
            "2 Items": 0,
            "3 Items": 0,
            "4+ Items": 0,
        },
    }

    if df is None or df.empty or len(df.columns) == 0:
        return empty_result

    resolved_id, resolved_item = detect_id_and_item_cols(df, item_col)
    id_col = id_col or resolved_id
    item_col = item_col or resolved_item

    if not id_col or not item_col:
        return empty_result

    qty_col = qty_col or next(
        (c for c in ["Quantity", "qty", "item_quantity"] if c in df.columns), None
    )

    # Filter out empty or whitespace item names
    valid_df = df[df[item_col].notna() & (df[item_col].astype(str).str.strip() != "")]
    if valid_df.empty:
        return empty_result

    grouped = valid_df.groupby(id_col)
    total_orders = grouped.ngroups
    if total_orders == 0:
        return empty_result

    # Distinct items per order
    items_per_order = grouped[item_col].nunique()
    multi_item_orders = int((items_per_order > 1).sum())
    single_item_orders = int((items_per_order == 1).sum())
    multi_item_rate = (
        (multi_item_orders / total_orders * 100.0) if total_orders > 0 else 0.0
    )
    avg_basket_items = (
        float(items_per_order.mean()) if not items_per_order.empty else 0.0
    )
    max_basket_items = int(items_per_order.max()) if not items_per_order.empty else 0

    # Average quantity per order (if quantity column exists)
    if qty_col and qty_col in valid_df.columns:
        numeric_qty = pd.to_numeric(valid_df[qty_col], errors="coerce").fillna(1)
        qty_per_order = (
            valid_df.assign(_clean_qty=numeric_qty).groupby(id_col)["_clean_qty"].sum()
        )
        avg_basket_qty = (
            float(qty_per_order.mean()) if not qty_per_order.empty else avg_basket_items
        )
    else:
        avg_basket_qty = avg_basket_items

    # Size distribution
    size_1 = int((items_per_order == 1).sum())
    size_2 = int((items_per_order == 2).sum())
    size_3 = int((items_per_order == 3).sum())
    size_4_plus = int((items_per_order >= 4).sum())

    # Fast top pair calculation
    multi_baskets = (
        grouped[item_col]
        .apply(lambda s: sorted(set(s.astype(str).str.strip())))
        .loc[lambda s: s.str.len() > 1]
    )

    top_pair = None
    top_pair_count = 0
    if not multi_baskets.empty:
        pair_counter: Counter[tuple[str, str]] = Counter()
        for items in multi_baskets:
            if len(items) <= 35:
                for pair in combinations(items, 2):
                    pair_counter[pair] += 1
            else:
                for pair in combinations(items[:35], 2):
                    pair_counter[pair] += 1

        if pair_counter:
            most_common = pair_counter.most_common(1)[0]
            top_pair = most_common[0]
            top_pair_count = most_common[1]

    return {
        "total_orders": total_orders,
        "multi_item_orders": multi_item_orders,
        "single_item_orders": single_item_orders,
        "multi_item_rate": round(multi_item_rate, 2),
        "avg_basket_items": round(avg_basket_items, 2),
        "avg_basket_qty": round(avg_basket_qty, 2),
        "max_basket_items": max_basket_items,
        "top_pair": top_pair,
        "top_pair_count": top_pair_count,
        "size_distribution": {
            "1 Item": size_1,
            "2 Items": size_2,
            "3 Items": size_3,
            "4+ Items": size_4_plus,
        },
    }


def mine_association_rules(
    df: pd.DataFrame,
    id_col: str | None = None,
    item_col: str | None = None,
    min_cooccurrence: int = 1,
    max_items_per_order: int = 35,
) -> pd.DataFrame:
    """Mine frequent item pairs and compute Support, Confidence, and Lift.

    Args:
        df: Granular dataframe containing order lines.
        id_col: Name of order ID column. If None, auto-detected.
        item_col: Name of product/SKU column. If None, auto-detected.
        min_cooccurrence: Minimum number of co-occurring orders to include a pair.
        max_items_per_order: Cap on distinct items evaluated per order to prevent O(N^2) blowup.

    Returns:
        pd.DataFrame of association pairs sorted by Co_Orders descending, then Lift descending.
    """
    empty_cols = [
        "Item A",
        "Item B",
        "Pair",
        "Co_Orders",
        "Support_Pct",
        "Confidence_A_to_B_Pct",
        "Confidence_B_to_A_Pct",
        "Lift",
        "Affinity",
    ]
    if df is None or df.empty or len(df.columns) == 0:
        return pd.DataFrame(columns=empty_cols)

    resolved_id, resolved_item = detect_id_and_item_cols(df, item_col)
    id_col = id_col or resolved_id
    item_col = item_col or resolved_item

    if not id_col or not item_col:
        return pd.DataFrame(columns=empty_cols)

    valid_df = df[df[item_col].notna() & (df[item_col].astype(str).str.strip() != "")]
    if valid_df.empty:
        return pd.DataFrame(columns=empty_cols)

    grouped = valid_df.groupby(id_col)
    total_orders = grouped.ngroups
    if total_orders == 0:
        return pd.DataFrame(columns=empty_cols)

    # 1. Single item occurrence counts across all orders
    item_order_counts: Counter[str] = Counter()
    for _, items in grouped[item_col].unique().items():
        for item in items:
            item_order_counts[str(item).strip()] += 1

    # 2. Pairwise co-occurrences across multi-item orders
    pair_counter: Counter[tuple[str, str]] = Counter()
    for _, items in grouped[item_col].unique().items():
        cleaned_items = sorted(set(str(i).strip() for i in items if str(i).strip()))
        if len(cleaned_items) > 1:
            if len(cleaned_items) > max_items_per_order:
                cleaned_items = cleaned_items[:max_items_per_order]
            for p1, p2 in combinations(cleaned_items, 2):
                pair_counter[(p1, p2)] += 1

    if not pair_counter:
        return pd.DataFrame(columns=empty_cols)

    rows = []
    for (item_a, item_b), co_cnt in pair_counter.items():
        if co_cnt < min_cooccurrence:
            continue

        cnt_a = item_order_counts[item_a]
        cnt_b = item_order_counts[item_b]

        support = (co_cnt / total_orders) * 100.0
        conf_a_to_b = (co_cnt / cnt_a * 100.0) if cnt_a > 0 else 0.0
        conf_b_to_a = (co_cnt / cnt_b * 100.0) if cnt_b > 0 else 0.0

        # Lift = P(A and B) / (P(A) * P(B)) = (co_cnt * total_orders) / (cnt_a * cnt_b)
        lift = (
            (co_cnt * total_orders) / (cnt_a * cnt_b)
            if (cnt_a > 0 and cnt_b > 0)
            else 0.0
        )

        if lift >= 2.0:
            affinity = "🔥 High Affinity (>2x)"
        elif lift >= 1.2:
            affinity = "✨ Moderate Affinity"
        elif lift >= 0.8:
            affinity = "⚖️ Independent"
        else:
            affinity = "❄️ Weak / Substitute"

        rows.append(
            {
                "Item A": item_a,
                "Item B": item_b,
                "Pair": f"{item_a} + {item_b}",
                "Co_Orders": int(co_cnt),
                "Support_Pct": round(support, 2),
                "Confidence_A_to_B_Pct": round(conf_a_to_b, 1),
                "Confidence_B_to_A_Pct": round(conf_b_to_a, 1),
                "Lift": round(lift, 2),
                "Affinity": affinity,
            }
        )

    if not rows:
        return pd.DataFrame(columns=empty_cols)

    res_df = pd.DataFrame(rows)
    res_df = res_df.sort_values(
        by=["Co_Orders", "Lift"], ascending=[False, False]
    ).reset_index(drop=True)
    return res_df


def get_product_cross_sells(
    rules_df: pd.DataFrame,
    product_name: str,
    top_n: int = 10,
) -> pd.DataFrame:
    """Find top recommended cross-sell items for a given product."""
    empty_cols = [
        "Recommended_Item",
        "Co_Orders",
        "Support_Pct",
        "Confidence_Pct",
        "Lift",
        "Affinity",
    ]
    if rules_df is None or rules_df.empty or not product_name:
        return pd.DataFrame(columns=empty_cols)

    p_norm = str(product_name).strip().lower()

    recs = []
    for _, row in rules_df.iterrows():
        a = str(row["Item A"]).strip()
        b = str(row["Item B"]).strip()

        if a.lower() == p_norm:
            recs.append(
                {
                    "Recommended_Item": b,
                    "Co_Orders": int(row["Co_Orders"]),
                    "Support_Pct": float(row["Support_Pct"]),
                    "Confidence_Pct": float(row["Confidence_A_to_B_Pct"]),
                    "Lift": float(row["Lift"]),
                    "Affinity": str(row["Affinity"]),
                }
            )
        elif b.lower() == p_norm:
            recs.append(
                {
                    "Recommended_Item": a,
                    "Co_Orders": int(row["Co_Orders"]),
                    "Support_Pct": float(row["Support_Pct"]),
                    "Confidence_Pct": float(row["Confidence_B_to_A_Pct"]),
                    "Lift": float(row["Lift"]),
                    "Affinity": str(row["Affinity"]),
                }
            )

    if not recs:
        return pd.DataFrame(columns=empty_cols)

    rec_df = pd.DataFrame(recs)
    # Deduplicate in case symmetric pairs were present
    rec_df = (
        rec_df.sort_values(by=["Co_Orders", "Lift"], ascending=[False, False])
        .drop_duplicates(subset=["Recommended_Item"])
        .head(top_n)
        .reset_index(drop=True)
    )
    return rec_df


def compute_category_associations(
    df: pd.DataFrame,
    id_col: str | None = None,
    cat_col: str = "Category",
    min_cooccurrence: int = 1,
) -> pd.DataFrame:
    """Mine cross-category co-purchase frequencies (e.g. Panjabi + Pajama)."""
    if cat_col not in df.columns:
        return pd.DataFrame()
    return mine_association_rules(
        df=df,
        id_col=id_col,
        item_col=cat_col,
        min_cooccurrence=min_cooccurrence,
    )

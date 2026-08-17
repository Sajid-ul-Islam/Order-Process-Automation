import os

import pandas as pd

from src.config.constants import RESOURCES_DIR, SALES_SNAPSHOT_PATH, STOCK_SNAPSHOT_PATH
from src.utils.product import get_base_product_name


def load_stock_snapshot():
    """Load stock snapshot from local CSV with smart header detection."""
    paths = [STOCK_SNAPSHOT_PATH, os.path.join(RESOURCES_DIR, "stock_snapshot.csv")]
    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    first_line = f.readline()

                if "Category" in first_line and "Current Stock" in first_line:
                    df = pd.read_csv(path)
                    new_cols = []
                    for col in df.columns:
                        cleaned = col.replace("Current Stock Analytics", "").strip()
                        new_cols.append(cleaned if cleaned else "Category")
                    df.columns = new_cols
                else:
                    df = pd.read_csv(path)

                col_map = {
                    "Item Name": "Product",
                    "name": "Product",
                    "Title": "Product",
                    "Quantity": "Stock",
                    "item_stock": "Stock",
                    "Inventory": "Stock",
                }
                df = df.rename(
                    columns={k: v for k, v in col_map.items() if k in df.columns}
                )

                if not df.empty and "Stock" in df.columns:
                    df["Stock"] = pd.to_numeric(df["Stock"], errors="coerce").astype(
                        float
                    )
                    if "Price" in df.columns:
                        df["Price"] = (
                            pd.to_numeric(df["Price"], errors="coerce")
                            .fillna(0)
                            .astype(float)
                        )

                    if "Product" in df.columns:
                        df["Base_Product"] = df["Product"].apply(get_base_product_name)
                    return df
            except Exception:
                continue
    return None


def save_stock_snapshot(df):
    try:
        os.makedirs(RESOURCES_DIR, exist_ok=True)
        df.to_csv(STOCK_SNAPSHOT_PATH, index=False)
    except Exception:
        pass


def load_sales_snapshot():
    paths = [SALES_SNAPSHOT_PATH, os.path.join(RESOURCES_DIR, "sales_report.csv")]
    for path in paths:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                return df
            except Exception:
                continue
    return None


def save_sales_snapshot(df):
    try:
        os.makedirs(RESOURCES_DIR, exist_ok=True)
        df.to_csv(SALES_SNAPSHOT_PATH, index=False)
    except Exception:
        pass

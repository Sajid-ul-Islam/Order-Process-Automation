import pandas as pd
from src.utils.streamlit_runtime import cache_data

from src.utils.logging import log_system_event

# ── Canonical column-name candidates (single source of truth) ────────────────
# These lists are the exact-match candidates used by pick_column() across the
# app. Every module looking for a phone/email/date/name/city/order-id column
# must import from here instead of re-hardcoding its own list, so a new
# WooCommerce export header only needs to be added in one place.

PHONE_COL_CANDIDATES = [
    "Phone (Billing)",
    "Phone",
    "Billing Phone",
    "Customer Phone",
    "phone",
]

EMAIL_COL_CANDIDATES = ["Billing Email", "Email", "Customer Email", "email"]

DATE_COL_CANDIDATES = [
    "Date",
    "Order Date",
    "Date Created",
    "Created Date",
    "Created At",
    "Order_Date",
    "Date_Created",
    "Time",
    "created_at",
]

NAME_COL_CANDIDATES = [
    "Full Name (Billing)",
    "Full Name",
    "Customer Name",
    "name",
]

CITY_COL_CANDIDATES = ["Shipping City", "Billing City", "City", "city"]

ORDER_ID_COL_CANDIDATES = [
    "Order ID",
    "Order Number",
    "Order #",
    "Invoice Number",
    "Invoice #",
    "Order_ID",
    "ID",
    "Transaction ID",
    "order_id",
    "order_number",
]

ITEM_NAME_COL_CANDIDATES = [
    "Item Name",
    "Product Name",
    "Product",
    "Item",
    "Title",
    "Items",
    "Clean_Product",
    "Item_Name",
    "Product_Name",
    "description",
    "name",
]

SKU_COL_CANDIDATES = [
    "SKU",
    "Item SKU",
    "Product SKU",
    "SKU Code",
    "Sku",
    "sku",
    "Barcode",
    "Item_SKU",
    "Product_SKU",
]

QTY_COL_CANDIDATES = [
    "Quantity",
    "Qty",
    "Total Quantity",
    "Item Quantity",
    "Units",
    "Count",
    "quantity",
    "qty",
    "Quantity_Ordered",
]


def pick_column(
    df: pd.DataFrame, candidates: list[str], default: str | None = None
) -> str | None:
    """Return the first candidate column present in df, else `default`.

    Replaces the repeated ``next((c for c in [...] if c in df.columns), default)``
    idiom used across the codebase for finding the best matching column name.
    """
    if df is None:
        return default
    return next((c for c in candidates if c in df.columns), default)


def detect_column(
    df: pd.DataFrame, candidates: list[str], default: str | None = None
) -> str | None:
    """Find the best column in df matching candidates.

    1. First tries exact match against candidates.
    2. Then tries case-insensitive match (stripping whitespace).
    3. Then tries case-insensitive substring match for candidates with >= 3 characters.
    4. Falls back to default.
    """
    if df is None or len(df.columns) == 0:
        return default

    # 1. Exact match
    for c in candidates:
        if c in df.columns:
            return c

    # 2. Case-insensitive exact match
    col_map = {str(col).strip().lower(): col for col in df.columns}
    for c in candidates:
        c_clean = str(c).strip().lower()
        if c_clean in col_map:
            return col_map[c_clean]

    # 3. Normalized alphanumeric match (handling underscores, hyphens, spaces)
    def _norm(s: str) -> str:
        return "".join(ch for ch in str(s).lower() if ch.isalnum())

    norm_col_map = {_norm(col): col for col in df.columns}
    for c in candidates:
        c_norm = _norm(c)
        if c_norm and c_norm in norm_col_map:
            return norm_col_map[c_norm]

    # 4. Substring match for candidates with >= 3 characters
    for c in candidates:
        c_clean = str(c).strip().lower()
        if len(c_clean) < 3:
            continue
        for col_lower, orig_col in col_map.items():
            if c_clean in col_lower or (len(col_lower) >= 3 and col_lower in c_clean):
                return orig_col

    return default


@cache_data(show_spinner=False)
def find_columns(df: pd.DataFrame) -> dict[str, str]:
    """Detects primary columns using exact and then partial matching.

    Returns partial results on failure instead of an empty dict, logging
    any errors encountered during detection.

    Args:
        df: Input DataFrame to detect columns in.

    Returns:
        Dict mapping logical names (name, item, sku, cost, qty, date, order_id, phone)
        to actual column names found in the DataFrame.
    """
    mapping = {
        "name": [
            "item name",
            "product name",
            "product",
            "item",
            "title",
            "description",
            "name",
        ],
        "item": [
            "item name",
            "product name",
            "product",
            "item",
            "title",
            "description",
            "name",
        ],
        "sku": [
            "sku",
            "item sku",
            "product sku",
            "sku code",
            "barcode",
            "code",
        ],
        "cost": [
            "item cost",
            "price",
            "unit price",
            "cost",
            "rate",
            "mrp",
            "selling price",
        ],
        "qty": ["quantity", "qty", "units", "sold", "count", "total quantity"],
        "date": [
            "date",
            "order date",
            "date created",
            "created date",
            "month",
            "time",
            "created at",
        ],
        "order_id": [
            "order id",
            "order #",
            "invoice number",
            "invoice #",
            "order number",
            "transaction id",
            "id",
        ],
        "phone": [
            "phone",
            "contact",
            "mobile",
            "cell",
            "phone number",
            "customer phone",
        ],
    }

    found = {}
    try:
        actual_cols = [str(c).strip() for c in df.columns]
        lower_cols = [c.lower() for c in actual_cols]

        for key, aliases in mapping.items():
            for alias in aliases:
                if alias in lower_cols:
                    idx = lower_cols.index(alias)
                    found[key] = actual_cols[idx]
                    break

        for key, aliases in mapping.items():
            if key not in found:
                for col, l_col in zip(actual_cols, lower_cols, strict=True):
                    if any(alias in l_col for alias in aliases):
                        found[key] = col
                        break
    except Exception as e:
        log_system_event(
            "COLUMN_DETECT_ERROR",
            f"Partial detection returned {len(found)} columns: {e}",
        )

    return found


@cache_data(show_spinner=False)
def scrub_raw_dataframe(df):
    """Filters out dashboard analytics, empty rows, and summary tables from raw exports."""
    if df is None or df.empty:
        return df

    # 1. Drop completely empty rows
    df = df.dropna(how="all")

    # 2. Heuristic: Sparsity Check
    # Keep rows that have at least 30% of the columns filled
    min_threshold = max(1, int(len(df.columns) * 0.3))
    df = df.dropna(thresh=min_threshold)

    # 3. Optimized Summary Filter (Avoid stacking)
    # Target common text columns instead of the entire dataframe
    summary_keywords = [
        "total",
        "grand total",
        "summary",
        "analytics",
        "chart",
        "metric",
    ]
    pattern = "|".join(summary_keywords)

    # Check specifically for Order Number or ID being 'Total' or similar
    # If we find a column that looks like an ID, use it as a primary filter
    id_cols = [
        c
        for c in df.columns
        if any(k in c.lower() for k in ["id", "number", "invoice", "#"])
    ]
    if id_cols:
        col = id_cols[0]
        df = df[~df[col].astype(str).str.lower().str.contains(pattern, na=False)]

    return df

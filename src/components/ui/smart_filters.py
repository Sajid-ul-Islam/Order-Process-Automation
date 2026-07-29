"""Auto-detect filterable columns and render dynamic filter widgets."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from src.utils.safe_ops import safe_filter


def detect_filterable_columns(df: pd.DataFrame) -> dict[str, str]:
    """Classify DataFrame columns as 'date', 'categorical', or 'numeric'.

    Detection rules:
    - Date: datetime dtype or >70% parseable as dates.
    - Categorical: object/string dtype, nunique < min(50, 0.3*len(df)),
      and not likely IDs/phones/addresses.
    - Numeric: int/float dtype.

    Args:
        df: Input DataFrame to analyze.

    Returns:
        Dict mapping column names to their detected type string.
    """
    if df.empty:
        return {}

    result: dict[str, str] = {}
    n_rows = len(df)

    # Columns to skip — likely IDs, phones, addresses, URLs
    _skip_patterns = [
        "id", "phone", "mobile", "cell", "address", "street", "url",
        "email", "zip", "postal", "lat", "lon", "longitude", "latitude",
    ]

    for col in df.columns:
        col_lower = col.lower().strip()

        # Skip internal/derived columns
        if col_lower.startswith("_") or col_lower in ("filter_identity", "clean_product", "display_name", "label"):
            continue

        # Check date
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            result[col] = "date"
            continue

        # Check numeric
        if pd.api.types.is_numeric_dtype(df[col]):
            result[col] = "numeric"
            continue

        # For object/string columns — try date parse or categorical
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            # Skip likely IDs/phones/addresses
            if any(pat in col_lower for pat in _skip_patterns):
                continue

            # Try date detection: >70% parseable
            non_null = df[col].dropna()
            if not non_null.empty and len(non_null) > 0:
                parsed = pd.to_datetime(non_null, errors="coerce")
                parse_rate = parsed.notna().sum() / len(non_null)
                if parse_rate > 0.7:
                    result[col] = "date"
                    continue

            # Categorical check
            n_unique = df[col].nunique()
            if n_unique < min(50, max(2, int(0.3 * n_rows))):
                result[col] = "categorical"
                continue

    return result


def render_smart_filters(
    df: pd.DataFrame,
    key_prefix: str,
    known_columns: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Auto-render filter widgets based on column classification.

    For known columns (e.g. Category/Sub-Category from WooCommerce data),
    existing cascade logic is preserved. Smart detection fills in for
    unknown/uploaded data.

    Uses safe_filter() for graceful degradation on each filter.

    Args:
        df: DataFrame to filter.
        key_prefix: Unique prefix for Streamlit widget keys.
        known_columns: Optional dict overriding detection for specific columns.
            Maps column name to type ('date', 'categorical', 'numeric').

    Returns:
        Filtered DataFrame.
    """
    if df.empty:
        return df

    detected = detect_filterable_columns(df)
    if known_columns:
        detected.update(known_columns)

    if not detected:
        return df

    # Group by type
    date_cols = [c for c, t in detected.items() if t == "date" and c in df.columns]
    cat_cols = [c for c, t in detected.items() if t == "categorical" and c in df.columns]
    num_cols = [c for c, t in detected.items() if t == "numeric" and c in df.columns]

    # Determine number of filter columns needed
    n_filters = len(date_cols) + len(cat_cols) + len(num_cols)
    if n_filters == 0:
        return df

    working_df = df

    # Render date filters
    for col in date_cols[:2]:  # Limit to 2 date filters
        dt_series = pd.to_datetime(working_df[col], errors="coerce")
        valid = dt_series.dropna()
        if valid.empty:
            continue

        min_date = valid.min().date()
        max_date = valid.max().date()

        sel = st.date_input(
            f"Filter by {col}",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            key=f"{key_prefix}_date_{col}",
        )
        if isinstance(sel, tuple) and len(sel) == 2:
            s_d, e_d = pd.to_datetime(sel[0]), pd.to_datetime(sel[1]) + timedelta(days=1)
            working_df = safe_filter(
                working_df,
                lambda d, c=col, s=s_d, e=e_d: d[
                    pd.to_datetime(d[c], errors="coerce").between(s, e)
                ],
                f"Date: {col}",
            )

    # Render categorical filters
    cols = st.columns(max(1, len(cat_cols[:4]))) if cat_cols else []
    for i, col in enumerate(cat_cols[:4]):  # Limit to 4 categorical filters
        with cols[i]:
            options = sorted(working_df[col].dropna().unique().tolist())
            selected = st.multiselect(
                f"Select {col}",
                options,
                placeholder=f"All {col}",
                key=f"{key_prefix}_cat_{col}",
            )
            if selected:
                working_df = safe_filter(
                    working_df,
                    lambda d, c=col, s=selected: d[d[c].isin(s)],
                    col,
                )

    # Render numeric range filters
    for col in num_cols[:2]:  # Limit to 2 numeric filters
        num_series = pd.to_numeric(working_df[col], errors="coerce").dropna()
        if num_series.empty:
            continue

        col_min = float(num_series.min())
        col_max = float(num_series.max())
        if col_min == col_max:
            continue

        sel_range = st.slider(
            f"Range: {col}",
            min_value=col_min,
            max_value=col_max,
            value=(col_min, col_max),
            key=f"{key_prefix}_num_{col}",
        )
        if sel_range != (col_min, col_max):
            working_df = safe_filter(
                working_df,
                lambda d, c=col, lo=sel_range[0], hi=sel_range[1]: d[
                    pd.to_numeric(d[c], errors="coerce").between(lo, hi)
                ],
                col,
            )

    return working_df

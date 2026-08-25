"""Graceful failure utilities for Streamlit rendering and data filtering."""

from __future__ import annotations

from typing import Callable, TypeVar

import pandas as pd
import streamlit as st

T = TypeVar("T")


def safe_filter(
    df: pd.DataFrame,
    filter_fn: Callable[[pd.DataFrame], pd.DataFrame],
    filter_name: str = "filter",
) -> pd.DataFrame:
    """Apply a filter function safely.

    On failure or empty result, returns the original DataFrame with a warning.

    Args:
        df: Input DataFrame to filter.
        filter_fn: Callable that takes a DataFrame and returns a filtered DataFrame.
        filter_name: Human-readable name for the filter (shown in warnings).

    Returns:
        Filtered DataFrame, or original if the filter fails.
    """
    try:
        result = filter_fn(df)
        if result is None or (isinstance(result, pd.DataFrame) and result.empty):
            st.warning(f"Filter '{filter_name}' returned no results. Showing all data.")
            return df
        return result
    except Exception as e:
        st.warning(f"Filter '{filter_name}' failed: {e}. Showing unfiltered data.")
        return df

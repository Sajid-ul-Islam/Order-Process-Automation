"""Persistent customer lifetime history registry.

Stores a mapping of customer phone numbers and emails to their earliest known order date.
Accurately identifies returning customers even if their previous order was placed years ago.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from collections import defaultdict

import pandas as pd

from src.config.constants import RESOURCES_DIR
from src.processing.data_processing import safe_coerce_datetime_naive
from src.utils.logging import log_system_event

CUSTOMER_REGISTRY_PATH = os.path.join(RESOURCES_DIR, "customer_registry.json")


def load_customer_registry() -> dict[str, str]:
    """Load the customer registry mapping (customer_key -> ISO earliest_date_str)."""
    if os.path.exists(CUSTOMER_REGISTRY_PATH):
        try:
            with open(CUSTOMER_REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log_system_event("CUSTOMER_REGISTRY_LOAD_ERROR", f"Failed to load registry: {e}")
    return {}


def update_customer_registry(df: pd.DataFrame, wc_raw_mapping: dict | None = None) -> int:
    """Update persistent customer registry from a DataFrame.

    Scans phone & email columns and updates earliest order dates.
    Returns count of new/updated customer records.
    """
    if df is None or df.empty:
        return 0

    registry = load_customer_registry()
    updated_cnt = 0

    try:
        mapping = wc_raw_mapping or {}
        date_col = "Date" if "Date" in df.columns else mapping.get("date", "Order Date")
        if date_col not in df.columns:
            date_col = next((c for c in ["Order Date", "Date", "Created Date"] if c in df.columns), None)

        if not date_col:
            return 0

        phone_col = next((c for c in ["Phone (Billing)", "Phone", "Billing Phone", "Customer Phone", "phone"] if c in df.columns), None)
        email_col = next((c for c in ["Billing Email", "Email", "Customer Email", "email"] if c in df.columns), None)
        cust_col = phone_col or email_col

        if not cust_col:
            return 0

        t_df = df.copy()
        t_df["_dt"] = safe_coerce_datetime_naive(t_df[date_col])
        t_df["_cust"] = t_df[cust_col].astype(str).str.strip().str.lower()
        t_df = t_df.dropna(subset=["_dt", "_cust"])

        # Filter out generic or invalid phone placeholders
        t_df = t_df[~t_df["_cust"].isin(["nan", "none", "0", "null", "", "01700000000"])]

        if t_df.empty:
            return 0

        # Find earliest order date per customer in this DataFrame
        grouped = t_df.groupby("_cust")["_dt"].min()

        for cust_id, min_dt in grouped.items():
            if not cust_id:
                continue

            dt_str = min_dt.isoformat()
            if cust_id not in registry:
                registry[cust_id] = dt_str
                updated_cnt += 1
            else:
                existing_dt = pd.to_datetime(registry[cust_id], errors="coerce")
                if pd.notna(existing_dt) and existing_dt.tzinfo is not None:
                    existing_dt = existing_dt.tz_localize(None)
                if pd.isna(existing_dt) or min_dt < existing_dt:
                    registry[cust_id] = dt_str
                    updated_cnt += 1

        if updated_cnt > 0:
            os.makedirs(RESOURCES_DIR, exist_ok=True)
            with open(CUSTOMER_REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2, ensure_ascii=False)

    except Exception as e:
        log_system_event("CUSTOMER_REGISTRY_UPDATE_ERROR", f"Failed to update registry: {e}")

    return updated_cnt

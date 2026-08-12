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


def normalize_phone_key(cust_id: str | None) -> str:
    """Normalize phone numbers or email keys to a standard format.

    Unifies 017..., 17..., 88017..., +88017... to standard 11-digit 017... format.
    """
    if not cust_id or pd.isna(cust_id):
        return ""
    cust_str = str(cust_id).strip().lower()
    if not cust_str or cust_str in ["nan", "none", "0", "null", "n/a", "01700000000"]:
        return ""

    if "@" in cust_str:
        return cust_str

    digits = "".join(filter(str.isdigit, cust_str))
    if not digits:
        return cust_str

    if digits.startswith("880"):
        digits = "0" + digits[3:]
    elif digits.startswith("88"):
        digits = "0" + digits[2:]
    elif not digits.startswith("0") and len(digits) == 10:
        digits = "0" + digits

    return digits


def load_customer_registry() -> dict[str, str]:
    """Load the customer registry mapping (customer_key -> ISO earliest_date_str)."""
    if os.path.exists(CUSTOMER_REGISTRY_PATH):
        try:
            with open(CUSTOMER_REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log_system_event("CUSTOMER_REGISTRY_LOAD_ERROR", f"Failed to load registry: {e}")
    return {}


def get_customer_first_order_date(cust_id: str | None, registry: dict[str, str] | None = None) -> pd.Timestamp | None:
    """Lookup earliest known order date for a customer across all normalized key variations."""
    if not cust_id or pd.isna(cust_id):
        return None

    if registry is None:
        registry = load_customer_registry()

    raw_key = str(cust_id).strip().lower()
    clean_key = normalize_phone_key(cust_id)

    possible_keys = [clean_key, raw_key]
    if clean_key.startswith("0"):
        possible_keys.append(clean_key[1:])
    else:
        possible_keys.append("0" + clean_key)

    earliest_dt = None
    for k in possible_keys:
        if k and k in registry:
            dt_val = pd.to_datetime(registry[k], errors="coerce")
            if pd.notna(dt_val):
                if dt_val.tzinfo is not None:
                    dt_val = dt_val.tz_localize(None)
                if earliest_dt is None or dt_val < earliest_dt:
                    earliest_dt = dt_val

    return earliest_dt


def register_customer_history(cust_id: str, first_order_date: str | pd.Timestamp) -> bool:
    """Manually register or override a customer's earliest order date in history."""
    clean_key = normalize_phone_key(cust_id)
    if not clean_key:
        return False

    registry = load_customer_registry()
    dt_val = pd.to_datetime(first_order_date, errors="coerce")
    if pd.isna(dt_val):
        return False

    if dt_val.tzinfo is not None:
        dt_val = dt_val.tz_localize(None)

    dt_str = dt_val.isoformat()
    registry[clean_key] = dt_str

    if clean_key.startswith("0"):
        registry[clean_key[1:]] = dt_str

    try:
        os.makedirs(RESOURCES_DIR, exist_ok=True)
        with open(CUSTOMER_REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log_system_event("CUSTOMER_REGISTRY_SAVE_ERROR", f"Failed to save registry: {e}")
        return False


def update_customer_registry(df: pd.DataFrame, wc_raw_mapping: dict | None = None) -> int:
    """Update persistent customer registry from a DataFrame.

    Scans phone & email columns and updates earliest order dates using normalized keys.
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
        t_df["_norm_cust"] = t_df[cust_col].apply(normalize_phone_key)
        t_df = t_df.dropna(subset=["_dt"])
        t_df = t_df[t_df["_norm_cust"] != ""]

        if t_df.empty:
            return 0

        grouped = t_df.groupby("_norm_cust")["_dt"].min()

        for cust_key, min_dt in grouped.items():
            if not cust_key:
                continue

            dt_str = min_dt.isoformat()
            existing_dt = get_customer_first_order_date(cust_key, registry)

            if existing_dt is None or min_dt < existing_dt:
                registry[cust_key] = dt_str
                if cust_key.startswith("0"):
                    registry[cust_key[1:]] = dt_str
                updated_cnt += 1

        if updated_cnt > 0:
            os.makedirs(RESOURCES_DIR, exist_ok=True)
            with open(CUSTOMER_REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2, ensure_ascii=False)

    except Exception as e:
        log_system_event("CUSTOMER_REGISTRY_UPDATE_ERROR", f"Failed to update registry: {e}")

    return updated_cnt

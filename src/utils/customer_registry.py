"""Persistent customer lifetime history registry.

Stores a mapping of customer phone numbers and emails to their earliest known order date.
Accurately identifies returning customers even if their previous order was placed years ago.
"""

from __future__ import annotations

import json
import os

import pandas as pd

from src.config.constants import RESOURCES_DIR
from src.processing.column_detection import pick_column
from src.processing.data_processing import safe_coerce_datetime_naive
from src.utils.logging import log_system_event
from src.utils.text import normalize_phone_number

CUSTOMER_REGISTRY_PATH = os.path.join(RESOURCES_DIR, "customer_registry.json")

# Column-name candidates used across registry scans (same work, one definition).
_PHONE_COL_CANDIDATES = [
    "Phone (Billing)",
    "Phone",
    "Billing Phone",
    "Customer Phone",
    "phone",
]
_EMAIL_COL_CANDIDATES = ["Billing Email", "Email", "Customer Email", "email"]
_DATE_COL_CANDIDATES = ["Order Date", "Date", "Created Date"]


def normalize_phone_key(cust_id: str | None) -> str:
    """Normalize phone numbers or email keys to a standard format.

    Unifies 017..., 17..., 88017..., +88017... to standard 11-digit 017... format.
    """
    if not cust_id or pd.isna(cust_id):
        return ""
    return normalize_phone_number(cust_id)


def load_customer_registry() -> dict[str, str]:
    """Load the customer registry mapping (customer_key -> ISO earliest_date_str)."""
    if os.path.exists(CUSTOMER_REGISTRY_PATH):
        try:
            with open(CUSTOMER_REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log_system_event(
                "CUSTOMER_REGISTRY_LOAD_ERROR", f"Failed to load registry: {e}"
            )
    return {}


def get_customer_first_order_date(
    cust_id: str | None, registry: dict[str, str] | None = None
) -> pd.Timestamp | None:
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


def register_customer_history(
    cust_id: str, first_order_date: str | pd.Timestamp
) -> bool:
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
        log_system_event(
            "CUSTOMER_REGISTRY_SAVE_ERROR", f"Failed to save registry: {e}"
        )
        return False


def update_customer_registry(
    df: pd.DataFrame, wc_raw_mapping: dict | None = None
) -> int:
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
            date_col = pick_column(df, _DATE_COL_CANDIDATES)

        if not date_col:
            return 0

        phone_col = pick_column(df, _PHONE_COL_CANDIDATES)
        email_col = pick_column(df, _EMAIL_COL_CANDIDATES)
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
        log_system_event(
            "CUSTOMER_REGISTRY_UPDATE_ERROR", f"Failed to update registry: {e}"
        )

    return updated_cnt


def compute_new_vs_returning_counts(
    m_df: pd.DataFrame | None,
    full_df: pd.DataFrame | None = None,
    wc_raw_mapping: dict | None = None,
) -> tuple[int, int]:
    """Compute (new_customer_count, returning_customer_count) for a target DataFrame using lifetime customer registry."""
    if m_df is None or m_df.empty:
        return 0, 0

    if full_df is None or full_df.empty:
        full_df = m_df

    wc_raw_mapping = wc_raw_mapping or {}
    new_cnt, ret_cnt = 0, 0

    try:
        update_customer_registry(full_df, wc_raw_mapping)
        lifetime_registry = load_customer_registry()

        phone_col = pick_column(m_df, _PHONE_COL_CANDIDATES)
        email_col = pick_column(m_df, _EMAIL_COL_CANDIDATES)
        cust_col = phone_col or email_col

        if not cust_col:
            return 0, 0

        full_dt_col = (
            "Date"
            if "Date" in full_df.columns
            else wc_raw_mapping.get("date", "Order Date")
        )
        if full_dt_col not in full_df.columns:
            full_dt_col = pick_column(full_df, _DATE_COL_CANDIDATES, full_df.columns[0])

        f_df = full_df.copy()
        f_df["_dt"] = safe_coerce_datetime_naive(f_df[full_dt_col])
        f_df["_norm_cust"] = f_df[cust_col].apply(normalize_phone_key)
        f_df = f_df.dropna(subset=["_dt"])
        f_df = f_df[f_df["_norm_cust"] != ""]

        first_order_map = f_df.groupby("_norm_cust")["_dt"].min().to_dict()

        active_dt_col = (
            "Date"
            if "Date" in m_df.columns
            else wc_raw_mapping.get("date", "Order Date")
        )
        if active_dt_col not in m_df.columns:
            active_dt_col = pick_column(m_df, _DATE_COL_CANDIDATES, m_df.columns[0])

        t_act = m_df.copy()
        t_act["_dt"] = safe_coerce_datetime_naive(t_act[active_dt_col])
        t_act["_norm_cust"] = t_act[cust_col].apply(normalize_phone_key)

        order_id_col = wc_raw_mapping.get("order_id", "Order ID")
        if order_id_col not in t_act.columns:
            order_id_col = pick_column(
                t_act, ["Order ID", "Order Number"], t_act.columns[0]
            )

        act_uniq = t_act.drop_duplicates(subset=[order_id_col])
        for _, urow in act_uniq.iterrows():
            c_id = urow.get("_norm_cust")
            o_dt = urow.get("_dt")
            if not c_id:
                new_cnt += 1
                continue

            first_dt = first_order_map.get(c_id, o_dt)
            reg_dt = get_customer_first_order_date(c_id, lifetime_registry)
            if reg_dt and (pd.isna(first_dt) or reg_dt < first_dt):
                first_dt = reg_dt

            if pd.notna(first_dt) and pd.notna(o_dt) and first_dt < o_dt:
                ret_cnt += 1
            else:
                new_cnt += 1
    except Exception as e:
        log_system_event(
            "COMPUTE_CUSTOMER_MIX_ERROR", f"Failed to compute customer mix: {e}"
        )

    return new_cnt, ret_cnt

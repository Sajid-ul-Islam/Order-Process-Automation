import pandas as pd
import polars as pl
import streamlit as st
from src.processing.column_detection import find_columns, scrub_raw_dataframe
from src.processing.categorization import get_category_for_sales, get_sub_category_for_sales
from src.utils.product import get_base_product_name, get_size_from_name
from src.utils.logging import log_system_event


def filter_shipped_by_slot(df, nav_mode, is_comparison=False):
    """Filters a DataFrame to shipped statuses, narrowing strictly to orders shipped today for Today mode.

    Args:
        df: The order DataFrame to filter.
        nav_mode: Current navigation mode ('Today', 'Prev', 'Backlog').
        is_comparison: If True, applies the comparison slot.

    Returns:
        Filtered DataFrame containing only shipped orders within the relevant window.
    """
    import streamlit as st
    from datetime import datetime, timedelta, timezone
    from src.config.constants import SHIPPED_STATUSES

    if df is None or df.empty:
        return df

    status_col = "Order Status" if "Order Status" in df.columns else "Status" if "Status" in df.columns else None
    if status_col is None:
        return df

    has_consignment = pd.Series(False, index=df.index)
    for c_col in ["Pathao Consignment ID", "Consignment ID", "Tracking Code"]:
        if c_col in df.columns:
            p_val = df[c_col].astype(str).str.strip().str.lower()
            has_consignment = has_consignment | (~p_val.isin(["", "nan", "none", "n/a", "0", "null"]))

    shipped_mask = df[status_col].astype(str).str.lower().isin(SHIPPED_STATUSES) | has_consignment
    shipped_df = df[shipped_mask]

    if shipped_df.empty:
        return shipped_df

    mod_col = None
    if "mod_dt_parsed" in shipped_df.columns:
        mod_col = "mod_dt_parsed"
    elif "Order Date Modified" in shipped_df.columns:
        mod_col = "Order Date Modified"

    def _safe_tz_naive(series):
        return safe_coerce_datetime_naive(series)

    def _safe_dt_naive(val):
        dt_v = pd.to_datetime(val)
        return dt_v.tz_localize(None) if getattr(dt_v, "tz", None) is not None else dt_v

    custom_range = st.session_state.get("live_custom_range")
    tz_bd = timezone(timedelta(hours=6))
    today_bd = datetime.now(tz_bd).date()

    if not is_comparison and custom_range and isinstance(custom_range, (tuple, list)) and len(custom_range) == 2:
        start_d, end_d = custom_range[0], custom_range[1]
        if start_d != today_bd or end_d != today_bd:
            dt_series = _safe_tz_naive(shipped_df[mod_col]) if mod_col else pd.Series(pd.NaT, index=shipped_df.index)
            date_col = "dt_parsed" if "dt_parsed" in shipped_df.columns else "Order Date" if "Order Date" in shipped_df.columns else None
            dt_create = _safe_tz_naive(shipped_df[date_col]) if date_col else pd.Series(pd.NaT, index=shipped_df.index)

            mask = (
                ((dt_series.dt.date >= start_d) & (dt_series.dt.date <= end_d))
                | (dt_series.isna() & (dt_create.dt.date >= start_d) & (dt_create.dt.date <= end_d))
            )
            return shipped_df[mask]

    if nav_mode == "Today" and not is_comparison:
        # 1. First try filtering by operational shift slot boundaries if defined
        slot = st.session_state.get("wc_curr_slot")
        if slot:
            slot_start, slot_end = _safe_dt_naive(slot[0]), _safe_dt_naive(slot[1])
            dt_series = _safe_tz_naive(shipped_df[mod_col]) if mod_col else pd.Series(pd.NaT, index=shipped_df.index)
            date_col = "dt_parsed" if "dt_parsed" in shipped_df.columns else "Order Date" if "Order Date" in shipped_df.columns else None
            dt_create = _safe_tz_naive(shipped_df[date_col]) if date_col else pd.Series(pd.NaT, index=shipped_df.index)

            # Match mod_dt within slot OR (mod_dt is NaT and dt_create is within slot)
            in_slot_mask = (
                ((dt_series >= slot_start) & (dt_series <= slot_end))
                | (dt_series.isna() & (dt_create >= slot_start) & (dt_create <= slot_end))
            )
            shipped_in_slot = shipped_df[in_slot_mask]
            return shipped_in_slot

        # 2. Fallback to calendar date matching (BD Time UTC+6)
        tz_bd = timezone(timedelta(hours=6))
        today_bd = datetime.now(tz_bd).date()

        if mod_col:
            dt_series = _safe_tz_naive(shipped_df[mod_col])
            shipped_today = shipped_df[dt_series.dt.date == today_bd]
            return shipped_today

        # 3. Fallback to order creation date column
        date_col = "dt_parsed" if "dt_parsed" in shipped_df.columns else "Order Date" if "Order Date" in shipped_df.columns else None
        if date_col:
            dt_create = _safe_tz_naive(shipped_df[date_col])
            shipped_today = shipped_df[dt_create.dt.date == today_bd]
            return shipped_today

        return shipped_df.iloc[0:0]

    # ── Operational slot boundaries for Prev mode or comparison slots ──
    slot_key = "wc_curr_slot" if nav_mode == "Today" else "wc_prev_slot" if nav_mode == "Prev" else None
    if is_comparison:
        slot_key = "wc_prev_slot" if nav_mode == "Today" else "wc_curr_slot" if nav_mode == "Prev" else None

    slot = st.session_state.get(slot_key) if slot_key else None

    if slot and mod_col:
        slot_start, slot_end = _safe_dt_naive(slot[0]), _safe_dt_naive(slot[1])
        dt_series = _safe_tz_naive(shipped_df[mod_col])
        filtered = shipped_df[
            (dt_series >= slot_start) &
            (dt_series <= slot_end)
        ]
        return filtered

    return shipped_df.iloc[0:0]


def filter_all_orders_to_slot(df, nav_mode):
    """Scopes 'All Orders' view to only the relevant slot window and whitelisted statuses.

    For Today mode, keeps:
      - Active statuses (processing, on-hold, pending, waiting) placed within the slot window
      - Shipped/completed orders whose modification date falls within the slot window

    For other modes (Prev / Backlog), delegates to slot boundaries as defined in session state.

    Returns a filtered DataFrame — never falls back to the full unscoped dataset.
    """
    from datetime import datetime, timedelta, timezone
    from src.config.constants import SHIPPED_STATUSES

    ACTIVE_STATUSES  = {"processing", "on-hold", "pending", "waiting"}
    ALL_VALID        = ACTIVE_STATUSES | set(SHIPPED_STATUSES)

    if df is None or df.empty:
        return df

    status_col = (
        "Order Status" if "Order Status" in df.columns
        else "Status" if "Status" in df.columns
        else None
    )
    if status_col is None:
        return df

    # 1. Status whitelist — drop anything not in the allowed set
    status_lower = df[status_col].astype(str).str.lower()
    df = df[status_lower.isin(ALL_VALID)].copy()
    if df.empty:
        return df

    # Check for custom date range selected by user
    custom_range = st.session_state.get("live_custom_range")
    tz_bd = timezone(timedelta(hours=6))
    today_bd = datetime.now(tz_bd).date()

    if custom_range and isinstance(custom_range, (tuple, list)) and len(custom_range) == 2:
        start_d, end_d = custom_range[0], custom_range[1]
        if start_d != today_bd or end_d != today_bd:
            mod_col  = "mod_dt_parsed" if "mod_dt_parsed" in df.columns else "Order Date Modified" if "Order Date Modified" in df.columns else None
            date_col = "dt_parsed" if "dt_parsed" in df.columns else "Order Date" if "Order Date" in df.columns else None

            status_lower = df[status_col].astype(str).str.lower()
            is_active  = status_lower.isin(ACTIVE_STATUSES)
            is_shipped = status_lower.isin([s.lower() for s in SHIPPED_STATUSES])

            dt_mod = safe_coerce_datetime_naive(df[mod_col]) if mod_col else pd.Series(pd.NaT, index=df.index)
            dt_create = safe_coerce_datetime_naive(df[date_col]) if date_col else pd.Series(pd.NaT, index=df.index)

            active_mask = is_active & (dt_create.dt.date >= start_d) & (dt_create.dt.date <= end_d)
            shipped_mask = is_shipped & (
                ((dt_mod.dt.date >= start_d) & (dt_mod.dt.date <= end_d))
                | (dt_mod.isna() & (dt_create.dt.date >= start_d) & (dt_create.dt.date <= end_d))
            )
            return df[active_mask | shipped_mask]

    # 2. Choose the slot boundary key for the current nav mode
    if nav_mode == "Today":
        slot_key = "wc_curr_slot"
    elif nav_mode == "Prev":
        slot_key = "wc_prev_slot"
    else:
        slot_key = None

    slot = st.session_state.get(slot_key) if slot_key else None

    if slot:
        slot_start = pd.to_datetime(slot[0])
        slot_end   = pd.to_datetime(slot[1])

        mod_col  = "mod_dt_parsed" if "mod_dt_parsed" in df.columns else "Order Date Modified" if "Order Date Modified" in df.columns else None
        date_col = "dt_parsed" if "dt_parsed" in df.columns else "Order Date" if "Order Date" in df.columns else None

        has_consignment = pd.Series(False, index=df.index)
        for c_col in ["Pathao Consignment ID", "Consignment ID", "Tracking Code"]:
            if c_col in df.columns:
                p_val = df[c_col].astype(str).str.strip().str.lower()
                has_consignment = has_consignment | (~p_val.isin(["", "nan", "none", "n/a", "0", "null"]))

        status_lower = df[status_col].astype(str).str.lower()
        is_shipped = status_lower.isin([s.lower() for s in SHIPPED_STATUSES]) | has_consignment
        is_active  = status_lower.isin(ACTIVE_STATUSES) & (~has_consignment)

        # Active orders: scoped by creation date within slot
        if date_col:
            dt_create = safe_coerce_datetime_naive(df[date_col])
            active_mask = is_active & (dt_create >= slot_start) & (dt_create <= slot_end)
        else:
            active_mask = is_active  # can't scope further without a date column

        # Shipped orders: scoped by modification date within slot
        if mod_col:
            dt_mod = safe_coerce_datetime_naive(df[mod_col])
            shipped_mask = is_shipped & (dt_mod >= slot_start) & (dt_mod <= slot_end)
        else:
            shipped_mask = pd.Series(False, index=df.index)  # no mod date → exclude shipped

        combined = df[active_mask | shipped_mask]
        return combined

    # No slot boundaries — fall back to calendar day (BD UTC+6) for Today mode
    if nav_mode == "Today":
        tz_bd    = timezone(timedelta(hours=6))
        today_bd = datetime.now(tz_bd).date()

        date_col = "dt_parsed" if "dt_parsed" in df.columns else "Order Date" if "Order Date" in df.columns else None
        mod_col  = "mod_dt_parsed" if "mod_dt_parsed" in df.columns else "Order Date Modified" if "Order Date Modified" in df.columns else None

        status_lower = df[status_col].astype(str).str.lower()
        is_active  = status_lower.isin(ACTIVE_STATUSES)
        is_shipped = status_lower.isin([s.lower() for s in SHIPPED_STATUSES])

        if date_col:
            dt_create = safe_coerce_datetime_naive(df[date_col])
            active_mask = is_active & (dt_create.dt.date == today_bd)
        else:
            active_mask = is_active

        if mod_col:
            dt_mod = safe_coerce_datetime_naive(df[mod_col])
            shipped_mask = is_shipped & (dt_mod.dt.date == today_bd)
        else:
            shipped_mask = pd.Series(False, index=df.index)

        return df[active_mask | shipped_mask]

    # Prev/Backlog with no slot info — return status-filtered only
    return df



def process_data(df, selected_cols):
    """Main entry point for initial data processing. Returns granular sanitized data + aggregates."""
    df_standard, timeframe = prepare_granular_data(df, selected_cols)
    if df_standard.empty:
        return None, None, None, "", {}
    drill, summ, top, basket = aggregate_data(df_standard, selected_cols)
    return drill, summ, top, timeframe, basket

def safe_coerce_datetime_naive(series: pd.Series) -> pd.Series:
    """Safely converts a pandas Series to timezone-naive datetime64[ns].
    If timestamps are timezone-aware or contain explicit UTC ISO indicators (Z or offset),
    converts them to Asia/Dhaka local time (+6).
    Naive timestamps are preserved as local naive datetimes without double shift.
    """
    if series is None or series.empty:
        return pd.to_datetime(series, errors="coerce")

    # If series is already datetime64 dtype
    if pd.api.types.is_datetime64_any_dtype(series):
        if getattr(series.dt, "tz", None) is not None:
            return series.dt.tz_convert("Asia/Dhaka").dt.tz_localize(None)
        return series

    # Standard parsing first
    parsed = pd.to_datetime(series, errors="coerce")
    if getattr(parsed.dt, "tz", None) is not None:
        try:
            return parsed.dt.tz_convert("Asia/Dhaka").dt.tz_localize(None)
        except Exception:
            return parsed.dt.tz_localize(None)

    # If parsed result is naive string series, check if strings contain explicit UTC timezone designators ('Z', '+00:00')
    s_clean = series.dropna()
    if not s_clean.empty and isinstance(s_clean.iloc[0], str):
        first_val = str(s_clean.iloc[0])
        if "Z" in first_val or "+00" in first_val or "UTC" in first_val.upper():
            try:
                parsed_utc = pd.to_datetime(series, errors="coerce", utc=True)
                if getattr(parsed_utc.dt, "tz", None) is not None:
                    return parsed_utc.dt.tz_convert("Asia/Dhaka").dt.tz_localize(None)
            except Exception:
                pass

    return parsed


def prepare_granular_data(df, selected_cols):
    """Sanitizes and prepares granular columns with unified internal names."""
    try:
        df = df.copy()
        df = scrub_raw_dataframe(df)

        if df.empty:
            return df, ""

        # Mapping to Standard Names for easier internal logic
        df["Product Name"] = df[selected_cols["name"]].fillna("Unknown Product").astype(str)
        df = df[~df["Product Name"].str.contains("Choose Any", case=False, na=False)]

        df["Item Cost"] = pd.to_numeric(df[selected_cols["cost"]].astype(str).str.replace(r"[^\d.]", "", regex=True), errors="coerce").fillna(0)
        df["Quantity"] = pd.to_numeric(df[selected_cols["qty"]].astype(str).str.replace(r"[^\d.]", "", regex=True), errors="coerce").fillna(0)

        # v10.4 Standardized SKU support
        if "sku" in selected_cols and selected_cols["sku"] in df.columns:
             df["SKU"] = df[selected_cols["sku"]].fillna("N/A").astype(str)
        else:
             df["SKU"] = "N/A"


        timeframe_suffix = ""
        if "date" in selected_cols and selected_cols["date"] in df.columns:
            try:
                df["Date"] = safe_coerce_datetime_naive(df[selected_cols["date"]])
                dates_valid = df["Date"].dropna()
                if not dates_valid.empty:
                    if dates_valid.dt.to_period("M").nunique() == 1:
                        timeframe_suffix = dates_valid.iloc[0].strftime("%B_%Y")
                    else:
                        timeframe_suffix = f"{dates_valid.min().strftime('%d%b')}_to_{dates_valid.max().strftime('%d%b_%y')}"
                else:
                    log_system_event("DATE_PARSE_WARN", "No valid dates parsed from date column; proceeding without date filtering.")
            except Exception as date_err:
                log_system_event("DATE_PARSE_ERROR", f"Date parsing failed: {date_err}; proceeding without date column.")
                non_null = df[selected_cols["date"]].dropna()
                val = str(non_null.iloc[0]) if not non_null.empty else ""
                timeframe_suffix = val.replace("/", "-").replace(" ", "_")[:20]


        if (df["Quantity"] < 0).any():
            log_system_event("DATA_ISSUE", "Found negative quantities, converted to 0.")
            df.loc[df["Quantity"] < 0, "Quantity"] = 0

        # Optimized Categorization & Extraction (Vectorized Maps)
        from src.utils.product import is_bundle_or_combo

        unique_names = df["Product Name"].unique()
        name_cat_map = {}
        name_subcat_map = {}
        name_size_map = {}
        name_clean_map = {}
        name_bundle_map = {}

        for name in unique_names:
            cat = get_category_for_sales(name)
            name_cat_map[name] = cat
            name_subcat_map[name] = get_sub_category_for_sales(name, cat)
            name_size_map[name] = get_size_from_name(name)
            name_clean_map[name] = get_base_product_name(name)
            name_bundle_map[name] = is_bundle_or_combo(name, "", cat)

        df["Category"] = df["Product Name"].map(name_cat_map)
        df["Sub-Category"] = df["Product Name"].map(name_subcat_map)
        df["Size"] = df["Product Name"].map(name_size_map)
        df["Clean_Product"] = df["Product Name"].map(name_clean_map)
        df["Filter_Identity"] = df["Clean_Product"].astype(str) + " [" + df["SKU"].astype(str) + "]"
        df["Is_Bundle_Combo"] = df["Product Name"].map(name_bundle_map)

        if "Subtotal Cost" in df.columns:
            df["Subtotal Cost"] = pd.to_numeric(df["Subtotal Cost"].astype(str).str.replace(r"[^\d.]", "", regex=True), errors="coerce").fillna(df["Item Cost"])
        else:
            df["Subtotal Cost"] = df["Item Cost"]

        df["Gross Amount"] = df["Subtotal Cost"] * df["Quantity"]
        df["Total Amount"] = df["Item Cost"] * df["Quantity"]

        if "Cashback Discount" in df.columns:
            df["Cashback Discount"] = pd.to_numeric(df["Cashback Discount"].astype(str).str.replace(r"[^\d.]", "", regex=True), errors="coerce").fillna(0)
        else:
            df["Cashback Discount"] = (df["Gross Amount"] - df["Total Amount"]).clip(lower=0)

        # Handle negative fee lines (if negative sign '-' is present, it is a fee discount/cashback)
        fee_cols = [c for c in df.columns if c.lower() in ["extra fee", "fee", "fees", "fee discount total"]]
        for f_c in fee_cols:
            raw_fees = pd.to_numeric(df[f_c].astype(str).str.replace(r"[^\d.-]", "", regex=True), errors="coerce").fillna(0)
            neg_fees = raw_fees < 0
            if neg_fees.any():
                df.loc[neg_fees, "Cashback Discount"] = df.loc[neg_fees, "Cashback Discount"] + raw_fees[neg_fees].abs()


        # Ensure Order Status and other operational columns are present
        if "Order Status" not in df.columns:
            # Try to map status if not present (useful for manual uploads)
            status_col = find_columns(df).get("status")
            if status_col:
                df["Order Status"] = df[status_col].fillna("completed").astype(str).str.lower()
            else:
                df["Order Status"] = "completed"

        # Exclude pending payments, cancelled, and failed orders from all analytics
        df = df[~df["Order Status"].astype(str).str.lower().isin(["pending", "pending payment", "cancelled", "failed", "refunded", "trash"])]

        return df, timeframe_suffix
    except Exception as e:
        log_system_event("PREPARE_ERROR", str(e))
        return pd.DataFrame(), ""

def aggregate_data(df, selected_cols):
    """Generates dashboard aggregates from granular standardized data using Polars."""
    try:
        lazy_df = pl.from_pandas(df).lazy()
        
        # 1. Summary
        group_keys = ["Category"]
        if "Sub-Category" in df.columns:
            group_keys.append("Sub-Category")

        summary = (
            lazy_df.group_by(group_keys)
            .agg([
                pl.col("Quantity").sum().alias("Total Qty"),
                pl.col("Total Amount").sum().alias("Total Amount")
            ])
            .collect()
            .to_pandas()
        )

        total_rev = summary["Total Amount"].sum()
        total_qty = summary["Total Qty"].sum()
        if total_rev > 0:
            summary["Revenue Share (%)"] = (summary["Total Amount"] / total_rev * 100).round(2)
        if total_qty > 0:
            summary["Quantity Share (%)"] = (summary["Total Qty"] / total_qty * 100).round(2)

        # 2. Drilldown
        drill_keys = group_keys + ["Item Cost"]
        drilldown = (
            lazy_df.group_by(drill_keys)
            .agg([
                pl.col("Quantity").sum().alias("Total Qty"),
                pl.col("Total Amount").sum().alias("Total Amount")
            ])
            .collect()
            .to_pandas()
        )
        if "Sub-Category" in drilldown.columns:
            drilldown.columns = ["Category", "Sub-Category", "Price (TK)", "Total Qty", "Total Amount"]
        else:
            drilldown.columns = ["Category", "Price (TK)", "Total Qty", "Total Amount"]

        # 3. Top Items
        top_aggs = [
            pl.col("Quantity").sum().alias("Total Qty"),
            pl.col("Total Amount").sum().alias("Total Amount"),
            pl.col("Category").first().alias("Category"),
            pl.col("Clean_Product").first().alias("Clean_Product")
        ]
        if "Sub-Category" in df.columns:
            top_aggs.append(pl.col("Sub-Category").first().alias("Sub-Category"))

        top_items = (
            lazy_df.group_by(["Product Name", "SKU"])
            .agg(top_aggs)
            .collect()
            .to_pandas()
        )
        top_items = top_items.sort_values("Total Amount", ascending=False)

        # 4. Basket Metrics
        basket_metrics = {"avg_basket_qty": 0, "avg_basket_value": 0, "total_orders": 0, "attachment_rate": 0}
        group_cols = []
        if "order_id" in selected_cols and selected_cols["order_id"] in df.columns:
            group_cols.append(selected_cols["order_id"])
        elif "Order ID" in df.columns:
            group_cols.append("Order ID")

        if "phone" in selected_cols and selected_cols["phone"] in df.columns:
            group_cols.append(selected_cols["phone"])
        elif "Phone (Billing)" in df.columns:
            group_cols.append("Phone (Billing)")

        if group_cols:
            order_groups = (
                lazy_df.group_by(group_cols)
                .agg([
                    pl.col("Quantity").sum().alias("Quantity"),
                    pl.col("Total Amount").sum().alias("Total Amount"),
                    pl.when(~pl.col("Is_Bundle_Combo")).then(1).otherwise(0).sum().alias("Item Count")
                ])
                .collect()
                .to_pandas()
            )
            
            avg_qty = order_groups["Quantity"].mean()
            avg_val = order_groups["Total Amount"].mean()
            basket_metrics["avg_basket_qty"] = float(avg_qty) if pd.notna(avg_qty) else 0
            basket_metrics["avg_basket_value"] = float(avg_val) if pd.notna(avg_val) else 0
            basket_metrics["total_orders"] = len(order_groups)

            multi_item_orders = len(order_groups[order_groups["Item Count"] > 1])
            basket_metrics["attachment_rate"] = (multi_item_orders / len(order_groups) * 100) if len(order_groups) > 0 else 0

        phone_col = None
        if "phone" in selected_cols and selected_cols["phone"] in df.columns:
            phone_col = selected_cols["phone"]
        elif "Phone (Billing)" in df.columns:
            phone_col = "Phone (Billing)"
            
        if phone_col:
            order_col = group_cols[0] if group_cols else None
            if order_col:
                lazy_df = lazy_df.with_columns(
                    pl.when(
                        pl.col(phone_col).is_null() | 
                        pl.col(phone_col).cast(pl.String).is_in(["", "nan", "NaN", "None", "N/A", "0"])
                    )
                    .then(pl.col(order_col).cast(pl.String))
                    .otherwise(pl.col(phone_col).cast(pl.String))
                    .alias("_clean_phone")
                )
            else:
                lazy_df = lazy_df.with_columns(
                    pl.when(
                        pl.col(phone_col).is_null() | 
                        pl.col(phone_col).cast(pl.String).is_in(["", "nan", "NaN", "None", "N/A", "0"])
                    )
                    .then(pl.lit("Unknown"))
                    .otherwise(pl.col(phone_col).cast(pl.String))
                    .alias("_clean_phone")
                )
                
            customer_groups = (
                lazy_df.group_by("_clean_phone")
                .agg([pl.col("Total Amount").sum().alias("Total Amount")])
                .collect()
                .to_pandas()
            )
        else:
            basket_metrics["avg_customer_value"] = basket_metrics["avg_basket_value"]
            basket_metrics["unique_customers"] = basket_metrics["total_orders"]
            
        basket_metrics["total_gross_revenue"] = float(df["Gross Amount"].sum()) if "Gross Amount" in df.columns else float(df["Total Amount"].sum())
        basket_metrics["total_cashback_discount"] = float(df["Cashback Discount"].sum()) if "Cashback Discount" in df.columns else 0.0

        return drilldown, summary, top_items, basket_metrics
    except Exception as e:
        log_system_event("AGGREGATE_ERROR", str(e))
        return None, None, None, {}

def get_dispatch_metrics(active_df, total_orders=0):
    """Calculates dispatch, exchange, and freebie metrics from active shift data."""
    from src.config.constants import SHIPPED_STATUSES

    metrics = {
        "outlet_dispatch": 0,
        "exchange_dispatch": 0,
        "last_shipped_order": "N/A",
        "last_pathao_print": "N/A",
        "ecom_dispatch": 0,
        "pathao_count": 0,
        "other_count": 0,
        "pending": 0,
        "dispatched": 0,
        "dispatch_rate": 0.0
    }
    
    if active_df is not None and not active_df.empty:
        status_col = "Order Status" if "Order Status" in active_df.columns else "Status" if "Status" in active_df.columns else None
        order_col = "Order ID" if "Order ID" in active_df.columns else "Order Number" if "Order Number" in active_df.columns else None
        date_col = "Date" if "Date" in active_df.columns else "Order Date" if "Order Date" in active_df.columns else None
        pmt_col = "Payment Method Title" if "Payment Method Title" in active_df.columns else None

        if order_col:
            if status_col:
                metrics["exchange_dispatch"] = active_df[active_df[status_col].astype(str).str.lower().str.contains("exchange", na=False)][order_col].nunique()
                
                outlet_mask = active_df[status_col].astype(str).str.lower().str.contains("outlet", na=False)
                if pmt_col:
                    outlet_mask = outlet_mask | active_df[pmt_col].astype(str).str.lower().str.contains("outlet", na=False)
                metrics["outlet_dispatch"] = active_df[outlet_mask][order_col].nunique()

                # Pending orders
                pending_mask = active_df[status_col].astype(str).str.lower().isin(["processing", "on-hold", "pending", "waiting"])
                metrics["pending"] = active_df[pending_mask][order_col].nunique()

                # Dispatched orders using SHIPPED_STATUSES
                shipped_mask = active_df[status_col].astype(str).str.lower().isin(SHIPPED_STATUSES)
                shipped_df = active_df[shipped_mask]
                metrics["dispatched"] = shipped_df[order_col].nunique() if not shipped_df.empty else 0
            else:
                metrics["dispatched"] = active_df[order_col].nunique()
                shipped_df = active_df

            # Pathao Consignment ID check
            if "Pathao Consignment ID" in active_df.columns:
                p_col = active_df["Pathao Consignment ID"].astype(str).str.strip().str.lower()
                pathao_mask = (p_col != "") & (p_col != "nan") & (p_col != "none") & (p_col != "n/a")
                metrics["pathao_count"] = active_df[pathao_mask][order_col].nunique() if order_col else int(pathao_mask.sum())
            elif "Shipping Method Title" in active_df.columns:
                p_col = active_df["Shipping Method Title"].astype(str).str.lower()
                pathao_mask = p_col.str.contains("pathao", na=False)
                metrics["pathao_count"] = active_df[pathao_mask][order_col].nunique() if order_col else int(pathao_mask.sum())
            else:
                metrics["pathao_count"] = metrics["dispatched"]

            metrics["other_count"] = max(0, metrics["dispatched"] - metrics["pathao_count"])

            if not shipped_df.empty:
                latest_shipped = shipped_df.sort_values(date_col, ascending=False).iloc[0] if date_col and date_col in shipped_df.columns else shipped_df.iloc[0]
                metrics["last_shipped_order"] = str(latest_shipped[order_col])
                
                if "Pathao Consignment ID" in shipped_df.columns:
                    p_col_s = shipped_df["Pathao Consignment ID"].astype(str).str.strip().str.lower()
                    p_shipped = shipped_df[(p_col_s != "") & (p_col_s != "nan") & (p_col_s != "none") & (p_col_s != "n/a")]
                    if not p_shipped.empty:
                        latest_pathao = p_shipped.sort_values(date_col, ascending=False).iloc[0] if date_col and date_col in p_shipped.columns else p_shipped.iloc[0]
                        metrics["last_pathao_print"] = str(latest_pathao[order_col])
                    else:
                        metrics["last_pathao_print"] = str(latest_shipped[order_col])
                else:
                    metrics["last_pathao_print"] = str(latest_shipped[order_col])

    if total_orders > 0:
        metrics["dispatch_rate"] = (metrics["dispatched"] / total_orders) * 100.0
    metrics["ecom_dispatch"] = max(0, total_orders - metrics["outlet_dispatch"] - metrics["exchange_dispatch"])
    return metrics


def generate_executive_briefing(today_rev, today_qty, today_orders, today_aov, dm, top, prev_rev=None, prev_orders=None, forecast_str="", gross_rev=None, cashback_disc=None):
    """Generates the single source of truth narrative for the Executive Briefing."""
    from datetime import datetime, timedelta, timezone
    
    dm = dm or {}
    
    rev_trend = ""
    if prev_rev is not None:
        rev_trend = " 📈" if today_rev >= prev_rev else " 📉"
        
    net_rev = today_rev
    g_rev = gross_rev if gross_rev is not None else net_rev
    cb_disc = cashback_disc if cashback_disc is not None else max(0.0, g_rev - net_rev)
    loss_pct = (cb_disc / g_rev * 100) if g_rev > 0 else 0.0

    gross_aov = (g_rev / today_orders) if today_orders > 0 else today_aov
    net_aov = (net_rev / today_orders) if today_orders > 0 else today_aov
    cb_per_basket = (cb_disc / today_orders) if today_orders > 0 else 0.0
    pct_basket_lost = (cb_per_basket / gross_aov * 100) if gross_aov > 0 else 0.0

    rev_line = f"💵 *NET REALIZED REVENUE (After Cashback):* ৳{net_rev:,.0f}{rev_trend}" if prev_rev is not None else f"💵 *NET REALIZED REVENUE (After Cashback):* ৳{net_rev:,.0f}"

    report_lines = [
        f"📊 *DEEN-OPS Executive Briefing*",
        f"📅 {datetime.now(timezone(timedelta(hours=6))).strftime('%A, %d %B %Y')}",
        "",
        rev_line,
        f"🏷️ *Gross Revenue (Pre-Discount):* ৳{g_rev:,.0f}",
    ]

    if cb_disc > 0:
        report_lines.extend([
            f"💸 *Total Cashback & Fee Discounts:* -৳{cb_disc:,.0f} ({loss_pct:.1f}% revenue lost)",
        ])

    report_lines.extend([
        "",
        f"📦 *Shipped Items:* {today_qty:,.0f}",
        f"🛍️ *Net Basket Value (Post-Cashback):* ৳{net_aov:,.0f}",
    ])

    if cb_disc > 0:
        report_lines.extend([
            f"🛒 *Gross Basket Value (Pre-Discount):* ৳{gross_aov:,.0f}",
            f"📉 *Cashback Lost per Basket:* -৳{cb_per_basket:,.0f} ({pct_basket_lost:.1f}% lost/basket)",
        ])

    report_lines.extend([
        "",
        f"🚚 *Last Shipped Order:* {dm.get('last_shipped_order', 'N/A')}",
        f"🖨️ *Last Pathao Print:* {dm.get('last_pathao_print', 'N/A')}",
        "",
        f"🛒 *Total Orders:* {today_orders:,.0f}",
        f"🔄 *Exchange:* {dm.get('exchange_dispatch', 0):,.0f}",
        f"🚀 *Ecom Dispatch:* {dm.get('ecom_dispatch', 0):,.0f}",
        f"🏪 *Outlet Dispatch:* {dm.get('outlet_dispatch', 0):,.0f}",
    ])

    if prev_rev is not None:
        report_lines.extend(["", f"📉 *Yesterday's Net Shipped Revenue:* ৳{prev_rev:,.0f} ({prev_orders} orders)"])
        
    if forecast_str:
        report_lines.append(forecast_str)

    report_lines.extend(["", "🔥 *Top Performing Products:*"])

    if top is not None and not top.empty:
        if "Clean_Product" in top.columns:
            group_cols = ["Clean_Product", "SKU"] if "SKU" in top.columns else ["Clean_Product"]
            top_summary = top.groupby(group_cols, as_index=False).agg({"Total Qty": "sum", "Total Amount": "sum"})
            top_summary = top_summary.sort_values("Total Amount", ascending=False)
            top_3 = top_summary.head(3)
            for _, row in top_3.iterrows():
                sku_str = f" [{row['SKU']}]" if "SKU" in top.columns and str(row['SKU']) not in ['N/A', '', 'None', 'nan'] else ""
                report_lines.append(f"• {row['Clean_Product']}{sku_str} ({row['Total Qty']} pcs)")
        else:
            top_3 = top.head(3)
            for _, row in top_3.iterrows():
                report_lines.append(f"• {row['Product Name']} ({row['Total Qty']} pcs)")
    else:
        report_lines.append("No product data available.")

    report_lines.extend(["", "💻 _Access the full dashboard at your DEEN-OPS Terminal: https://deen-ops.streamlit.app/_"])
    
    return "\n".join(report_lines)

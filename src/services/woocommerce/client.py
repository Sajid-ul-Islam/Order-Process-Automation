import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
from requests.auth import HTTPBasicAuth

from src.config.constants import SHIPPED_STATUSES
from src.config.settings import get_woocommerce_config
from src.processing.column_detection import scrub_raw_dataframe
from src.utils.http import request_with_backoff
from src.utils.logging import log_system_event


# ── Data transformation helpers ──────────────────────────────────────────────


def _flatten_order(order: dict) -> list[dict]:
    """Flatten a single WooCommerce order JSON into one dict per line item."""
    oid = order.get("id")
    onum = order.get("number")
    d_val = order.get("date_created")
    status = order.get("status")
    m_val = order.get("date_modified")
    bill = order.get("billing", {})
    ship = order.get("shipping", {})
    c_name = f"{bill.get('first_name', '')} {bill.get('last_name', '')}".strip()
    pmt = order.get("payment_method_title", "")
    
    ptc_consignment_id = ""
    for meta in order.get("meta_data", []):
        if meta.get("key") == "ptc_consignment_id":
            ptc_consignment_id = meta.get("value", "")
            break

    if ptc_consignment_id and str(ptc_consignment_id).strip():
        status = "shipped"

    # Extract order level discounts, fee lines, & coupons
    ord_discount_total = float(order.get("discount_total", 0) or 0)
    coupons = [c.get("code") for c in order.get("coupon_lines", []) if isinstance(c, dict) and c.get("code")]
    coupon_str = ", ".join(coupons) if coupons else ""
    
    # Process fee_lines: Negative fees = discount/cashback, Positive fees = extra fee
    fee_lines = order.get("fee_lines", [])
    fee_discount_total = 0.0
    extra_fee_total = 0.0
    fee_notes = []
    
    for fee in fee_lines:
        if isinstance(fee, dict):
            f_val = float(fee.get("total", 0) or 0)
            f_name = fee.get("name", "Fee")
            if f_val < 0:
                fee_discount_total += abs(f_val)
                fee_notes.append(f"{f_name}: -TK {abs(f_val):,.0f}")
            elif f_val > 0:
                extra_fee_total += f_val
                fee_notes.append(f"{f_name}: +TK {f_val:,.0f}")

    line_items = order.get("line_items", [])
    num_items = len(line_items) if line_items else 1
    split_ord_discount = ord_discount_total / num_items if num_items > 0 else 0.0
    split_fee_discount = fee_discount_total / num_items if num_items > 0 else 0.0
    split_extra_fee = extra_fee_total / num_items if num_items > 0 else 0.0
    fee_notes_str = ", ".join(fee_notes) if fee_notes else ""

    flattened = []
    for item in line_items:
        qty_raw = item.get("quantity", 1)
        qty_num = float(str(qty_raw if qty_raw is not None else "1").replace(",", "")) if float(str(qty_raw if qty_raw is not None else "1").replace(",", "")) > 0 else 1.0
        
        tot_val = float(item.get("total", 0) or 0)
        sub_val = float(item.get("subtotal", tot_val) or tot_val)
        
        eff_unit_cost = tot_val / qty_num if tot_val > 0 else float(item.get("price", 0) or 0)
        std_unit_cost = sub_val / qty_num if sub_val > 0 else eff_unit_cost
        
        item_disc = max(0.0, sub_val - tot_val)
        total_cashback_disc = item_disc + split_ord_discount + split_fee_discount

        flattened.append({
            "Order ID": oid,
            "Order Number": onum,
            "Order Date": d_val,
            "Order Date Modified": m_val,
            "Order Status": status,
            "Full Name (Billing)": c_name,
            "Phone (Billing)": bill.get("phone", ""),
            "Shipping Address 1": ship.get("address_1", ""),
            "Shipping City": ship.get("city", ""),
            "State Name (Billing)": bill.get("state", ""),
            "Item Name": item.get("name"),
            "SKU": item.get("sku", ""),
            # Effective Unit Price (Net after line item discounts/cashback)
            "Item Cost": eff_unit_cost,
            # Standard Unit Price (Gross before line item discounts/cashback)
            "Subtotal Cost": std_unit_cost,
            "Item Discount": item_disc,
            "Order Discount Total": ord_discount_total,
            "Fee Discount Total": split_fee_discount,
            "Extra Fee": split_extra_fee,
            "Cashback Discount": total_cashback_disc,
            "Fee Notes": fee_notes_str,
            "Coupons": coupon_str,
            "Quantity": qty_num,
            "Order Total Amount": order.get("total"),
            "Payment Method Title": pmt,
            "Pathao Consignment ID": ptc_consignment_id,
        })
    return flattened


# ── API fetch helpers ────────────────────────────────────────────────────────


def _fetch_wc_page(url: str, params: dict, auth: HTTPBasicAuth, page: int):
    """Fetch a single page of WooCommerce orders.
    
    Returns (rows, total_pages) where rows is the flattened list of order item dicts.
    """
    res = request_with_backoff("GET", url, params={**params, "page": page}, auth=auth, timeout=15)
    res.raise_for_status()
    import json
    data = json.loads(res.content.decode("utf-8-sig"))
    rows = []
    for order in data:
        rows.extend(_flatten_order(order))
    total_pages = int(res.headers.get("X-WP-TotalPages", 1))
    return rows, total_pages


def _fetch_wc_batch(url: str, params: dict, auth: HTTPBasicAuth) -> list:
    """Fetch all pages of WooCommerce orders concurrently and return flattened rows."""
    fields = "id,number,date_created,date_modified,status,billing,shipping,payment_method_title,line_items,total,discount_total,shipping_total,fee_lines,coupon_lines,meta_data"
    params["_fields"] = fields


    try:
        rows, total_pages = _fetch_wc_page(url, params, auth, page=1)
    except Exception as e:
        log_system_event("WC_FETCH_INITIAL_ERROR", str(e))
        return []

    if total_pages <= 1:
        return rows

    # Fetch remaining pages concurrently
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=min(total_pages, 8)) as executor:
        futures = [executor.submit(_fetch_wc_page, url, params, auth, pg) for pg in range(2, total_pages + 1)]
        for future in futures:
            try:
                extra_rows, _ = future.result()
                rows.extend(extra_rows)
            except Exception as e:
                log_system_event("WC_FETCH_PAGE_ERROR", str(e))

    return rows


def get_woocommerce_shipped_orders_count(after_iso: str, before_iso: str) -> int:
    """Fetch the total count of shipped orders between two dates using X-WP-Total headers."""
    cfg = get_woocommerce_config()
    if not cfg:
        return 0

    url = f"{cfg.get('store_url', '').rstrip('/')}/wp-json/wc/v3/orders"
    auth = HTTPBasicAuth(cfg.get("consumer_key", ""), cfg.get("consumer_secret", ""))
    
    params = {
        "per_page": 1,
        "after": after_iso,
        "before": before_iso,
        "status": "shipped,completed,confirmed",
        "_fields": "id"
    }
    
    try:
        res = request_with_backoff("GET", url, params=params, auth=auth, timeout=10)
        if res.status_code == 200:
            return int(res.headers.get("X-WP-Total", 0))
    except Exception as e:
        log_system_event("WC_COUNT_FETCH_ERROR", str(e))
        
    return 0


# ── Sync parameter builders ─────────────────────────────────────────────────


def _get_operational_sync_params() -> dict:
    """Build API params for the Operational Cycle sync mode (3-day rolling window)."""
    tz_bd = timezone(timedelta(hours=6))
    now_bd = datetime.now(tz_bd)
    shift_h = st.session_state.get("shift_cutoff_hour", 18)
    shift_m = st.session_state.get("shift_cutoff_minute", 0)
    anchor = now_bd.replace(hour=shift_h, minute=shift_m, second=0, microsecond=0) - timedelta(days=3)

    return {
        "per_page": 100,
        "after": anchor.strftime("%Y-%m-%dT%H:%M:%S"),
        "before": now_bd.replace(hour=23, minute=59, second=59, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "processing,completed,shipped,on-hold,pending,waiting,confirmed",
        "orderby": "date",
        "order": "desc",
    }


def _get_today_modified_shipped_params() -> dict:
    """Build API params to fetch orders modified during today's operational shift with shipped status.

    This catches old orders (placed before the 3-day window) that were shipped in current shift.
    WooCommerce supports `modified_after` to filter by date_modified regardless of order date.
    Note: Subtract 6 hours from prev_cutoff (BD Time UTC+6) so WooCommerce API receives UTC ISO time.
    """
    tz_bd = timezone(timedelta(hours=6))
    _, prev_cutoff, _, _ = _compute_cutoff_times(tz_bd)
    prev_cutoff_utc = prev_cutoff - timedelta(hours=6)
    return {
        "per_page": 100,
        "modified_after": prev_cutoff_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "shipped",
        "orderby": "modified",
        "order": "desc",
    }






def _get_global_open_params() -> dict:
    """Build API params for fetching all open/hold orders."""
    return {
        "per_page": 100,
        "status": "on-hold,pending,waiting,confirmed",
        "orderby": "date",
        "order": "desc",
    }


def _get_custom_range_params() -> dict:
    """Build API params for the Custom Range sync mode."""
    start_date = st.session_state.get("wc_sync_start_date", datetime.now().date())
    start_time = st.session_state.get("wc_sync_start_time", (datetime.now() - timedelta(hours=12)).time())
    end_date = st.session_state.get("wc_sync_end_date", datetime.now().date())
    end_time = st.session_state.get("wc_sync_end_time", datetime.now().time())

    return {
        "per_page": 100,
        "after": f"{start_date}T{start_time.strftime('%H:%M:%S')}",
        "before": f"{end_date}T{end_time.strftime('%H:%M:%S')}",
        "status": "processing,completed,shipped,on-hold,pending,waiting,confirmed",
        "orderby": "date",
        "order": "desc",
    }


# ── Order merging ────────────────────────────────────────────────────────────


def _merge_deduplicated_orders(main_rows: list, extra_rows: list) -> list:
    """Merge two order lists, deduplicating by (Order ID, Item Name), preferring shipped status and latest date_modified."""
    order_map = {}
    for r in main_rows + extra_rows:
        key = (r["Order ID"], r["Item Name"])
        if key not in order_map:
            order_map[key] = r
        else:
            existing = order_map[key]
            new_st = str(r.get("Order Status")).lower()
            old_st = str(existing.get("Order Status")).lower()
            
            new_is_sh = new_st in SHIPPED_STATUSES
            old_is_sh = old_st in SHIPPED_STATUSES
            
            new_ptc = str(r.get("Pathao Consignment ID", "")).strip()
            old_ptc = str(existing.get("Pathao Consignment ID", "")).strip()

            new_mod = str(r.get("Order Date Modified", ""))
            old_mod = str(existing.get("Order Date Modified", ""))

            # Prefer shipped status over non-shipped status, or non-empty consignment ID, or later date_modified
            if (new_is_sh and not old_is_sh) or (new_ptc and not old_ptc) or (new_is_sh == old_is_sh and new_mod >= old_mod):
                order_map[key] = r

    return list(order_map.values())



# ── Operational partitioning ─────────────────────────────────────────────────


def _compute_cutoff_times(tz_bd):
    """Compute cutoff boundaries for operational cycle partitioning.
    
    Returns (cutoff_today, prev_cutoff, day_before_prev, shipped_limit).
    """
    now_bd = datetime.now(tz_bd)
    ref_now = now_bd.replace(tzinfo=None)
    shift_h = st.session_state.get("shift_cutoff_hour", 18)
    shift_m = st.session_state.get("shift_cutoff_minute", 0)
    cutoff_today = ref_now.replace(hour=shift_h, minute=shift_m, second=0, microsecond=0)

    holiday_list = st.session_state.get("operational_holidays", [])

    def _is_holiday(d):
        return d.weekday() == 4 or d.strftime("%Y-%m-%d") in holiday_list

    prev_cutoff = cutoff_today - timedelta(days=1)
    day_ending_today = (cutoff_today - timedelta(days=1)).date()
    if st.session_state.get("override_merge_current") or (_is_holiday(day_ending_today) and not st.session_state.get("override_24h_current")):
        prev_cutoff = cutoff_today - timedelta(days=2)

    day_before_prev = prev_cutoff - timedelta(days=1)
    day_ending_prev = (prev_cutoff - timedelta(days=1)).date()
    if st.session_state.get("override_merge_previous") or (_is_holiday(day_ending_prev) and not st.session_state.get("override_24h_previous")):
        day_before_prev = prev_cutoff - timedelta(days=2)

    shipped_limit = max(cutoff_today, ref_now + timedelta(hours=12))
    return cutoff_today, prev_cutoff, day_before_prev, shipped_limit


def _apply_shipped_history(df_full):
    if df_full.empty:
        return df_full
    df_full = df_full.copy()
    df_full["dt_parsed"] = pd.to_datetime(df_full["Order Date"], errors="coerce").dt.tz_localize(None)
    df_full["mod_dt_parsed"] = pd.to_datetime(df_full["Order Date Modified"], errors="coerce").dt.tz_localize(None)

    import os
    import json
    from src.config.constants import RESOURCES_DIR
    os.makedirs(RESOURCES_DIR, exist_ok=True)
    history_file = os.path.join(RESOURCES_DIR, "shipped_history.json")
    
    shipped_history = {}
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                shipped_history = json.load(f)
        except Exception:
            pass

    history_updated = False
    is_shipped_mask = df_full["Order Status"].astype(str).str.lower().isin(SHIPPED_STATUSES)
    
    for idx, row in df_full[is_shipped_mask].iterrows():
        oid = str(row["Order ID"])
        if oid in shipped_history:
            stored_dt = pd.to_datetime(shipped_history[oid], errors="coerce")
            actual_mod_dt = row["mod_dt_parsed"]
            if pd.notnull(actual_mod_dt) and (pd.isnull(stored_dt) or actual_mod_dt > stored_dt):
                shipped_history[oid] = str(actual_mod_dt)
                history_updated = True
            else:
                df_full.at[idx, "mod_dt_parsed"] = stored_dt
        else:
            if pd.notnull(row["mod_dt_parsed"]):
                shipped_history[oid] = str(row["mod_dt_parsed"])
                history_updated = True

    if history_updated:
        try:
            with open(history_file, "w") as f:
                json.dump(shipped_history, f)
        except Exception:
            pass
            
    return df_full

def _partition_operational_data(df_full):
    """Split a full DataFrame into Today, Prev, and Backlog partitions.
    
    Returns (df_live, df_prev, df_backlog, slot_label, slot_boundaries).
    slot_boundaries: (curr_slot, prev_slot, backlog_slot).
    """
    df_full = _apply_shipped_history(df_full)

    tz_bd = timezone(timedelta(hours=6))
    cutoff_today, prev_cutoff, day_before_prev, shipped_limit = _compute_cutoff_times(tz_bd)

    is_shipped = df_full["Order Status"].astype(str).str.lower().isin(SHIPPED_STATUSES)
    is_confirmed = df_full["Order Status"].astype(str).str.lower() == "confirmed"
    is_processing = df_full["Order Status"].astype(str).str.lower() == "processing"
    is_hold = df_full["Order Status"].astype(str).str.lower() == "on-hold"
    is_waiting = df_full["Order Status"].astype(str).str.lower().isin(["pending", "waiting"])

    shipped_recent = is_shipped & (
        df_full["mod_dt_parsed"].isna()
        | (df_full["mod_dt_parsed"] >= prev_cutoff)
        | (df_full["dt_parsed"] >= prev_cutoff)
    )

    df_live = df_full[
        ((~is_shipped) & (df_full["dt_parsed"] >= prev_cutoff))
        | shipped_recent
        | is_confirmed | is_processing
    ].copy()

    df_prev = df_full[
        (df_full["mod_dt_parsed"] >= day_before_prev) & 
        (df_full["mod_dt_parsed"] < prev_cutoff) & 
        is_shipped
    ].copy()

    df_backlog = df_full[is_hold | is_waiting].copy()

    now_bd = datetime.now(tz_bd)
    slot_label = "Today"

    # Today's slot extends until 6 AM next morning
    next_day_6am = (now_bd.replace(hour=6, minute=0, second=0, microsecond=0) + timedelta(days=1)) if now_bd.hour >= 6 else now_bd.replace(hour=6, minute=0, second=0, microsecond=0)

    slot_boundaries = {
        "wc_curr_slot": (prev_cutoff, next_day_6am.replace(tzinfo=None)),
        "wc_prev_slot": (day_before_prev, prev_cutoff),
        "wc_backlog_slot": (next_day_6am.replace(tzinfo=None), next_day_6am.replace(tzinfo=None) + timedelta(days=1)),
    }

    return df_live, df_prev, df_backlog, slot_label, slot_boundaries


def _build_result_payload(df_to_return, slot_label, modified_at, partitions, slots):
    """Build the standard results dictionary returned by load_from_woocommerce."""
    return {
        "df_to_return": df_to_return,
        "sync_desc": f"WooCommerce_{slot_label}_API_{len(df_to_return)}_Orders" if not df_to_return.empty else "woocommerce_api_empty",
        "modified_at": modified_at,
        "partitions": partitions,
        "slots": slots,
    }


# ── Main public functions ────────────────────────────────────────────────────


@st.cache_data(show_spinner=False)
def load_from_woocommerce():
    """Loads live data from WooCommerce REST API orders."""
    wc_info = get_woocommerce_config(required=False)
    wc_url = wc_info.get("store_url")
    wc_key = wc_info.get("consumer_key")
    wc_secret = wc_info.get("consumer_secret")

    if not wc_url or not wc_key or not wc_secret:
        raise ValueError(
            "WooCommerce integration requires WC_URL, WC_KEY, and WC_SECRET (or [woocommerce] table in secrets.toml)."
        )

    endpoint = f"{wc_url.rstrip('/')}/wp-json/wc/v3/orders"
    auth = HTTPBasicAuth(wc_key, wc_secret)
    tz_bd = timezone(timedelta(hours=6))

    try:
        sync_mode = st.session_state.get("wc_sync_mode", "Operational Cycle")

        if sync_mode == "Operational Cycle":
            params = _get_operational_sync_params()
            global_params = _get_global_open_params()
            today_shipped_params = _get_today_modified_shipped_params()

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=3) as executor:
                f_op = executor.submit(_fetch_wc_batch, endpoint, params, auth)
                f_global = executor.submit(_fetch_wc_batch, endpoint, global_params, auth)
                f_shipped = executor.submit(_fetch_wc_batch, endpoint, today_shipped_params, auth)

                rows = f_op.result()
                global_rows = f_global.result()
                today_shipped_rows = f_shipped.result()

            rows = _merge_deduplicated_orders(rows, global_rows)
            rows = _merge_deduplicated_orders(rows, today_shipped_rows)
        else:
            params = _get_custom_range_params()
            rows = _fetch_wc_batch(endpoint, params, auth)

        df_full = pd.DataFrame(rows)
        if df_full.empty:
            return _build_result_payload(
                pd.DataFrame(), "", "N/A", {}, {}
            )
            
        if sync_mode != "Operational Cycle":
            df_full = _apply_shipped_history(df_full)

        now_str = datetime.now(tz_bd).strftime("%Y-%m-%d %H:%M:%S")

        if sync_mode == "Operational Cycle":
            df_live, df_prev, df_backlog, slot_label, slots = _partition_operational_data(df_full)
            df_to_return = df_backlog if slot_label == "Backlog" else df_live
            partitions = {
                "wc_curr_df": scrub_raw_dataframe(df_live),
                "wc_prev_df": scrub_raw_dataframe(df_prev),
                "wc_backlog_df": scrub_raw_dataframe(df_backlog),
            }
        else:
            df_to_return = df_full
            slot_label = "Custom"
            partitions = {}
            slots = {}

        return _build_result_payload(
            scrub_raw_dataframe(df_to_return),
            slot_label,
            now_str,
            partitions,
            slots,
        )

    except Exception as e:
        log_system_event("WC_API_ERROR", str(e))
        raise RuntimeError(f"Failed to fetch data from WooCommerce: {e}")


def fetch_specific_woocommerce_orders(order_ids: list):
    """Fetches exact orders by their WooCommerce ID."""
    if not order_ids:
        return []

    wc_info = get_woocommerce_config(required=False)
    wc_url = wc_info.get("store_url")
    wc_key = wc_info.get("consumer_key")
    wc_secret = wc_info.get("consumer_secret")

    if not wc_url or not wc_key or not wc_secret:
        raise ValueError("WooCommerce integration missing.")

    endpoint = f"{wc_url.rstrip('/')}/wp-json/wc/v3/orders"
    auth = HTTPBasicAuth(wc_key, wc_secret)

    # Split order_ids into batches of 100 because WC REST API limits 'include'
    batches = [order_ids[i:i + 100] for i in range(0, len(order_ids), 100)]
    all_processed = []

    try:
        from concurrent.futures import ThreadPoolExecutor

        def _fetch_batch(batch_ids):
            include_str = ",".join(map(str, batch_ids))
            params = {"include": include_str, "_fields": "id,number,date_created,date_modified,status,billing,shipping,payment_method_title,line_items,total,meta_data", "per_page": 100}

            res = request_with_backoff("GET", endpoint, params=params, auth=auth, timeout=15)
            if res.status_code != 200:
                return []
            import json
            data = json.loads(res.content.decode("utf-8-sig"))
            rows = []
            for order in data:
                rows.extend(_flatten_order(order))
            return rows

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_fetch_batch, b) for b in batches]
            for future in futures:
                all_processed.extend(future.result())

    except Exception as e:
        log_system_event("WC_SPECIFIC_FETCH_ERROR", str(e))

    return all_processed


def _should_autorefresh() -> bool:
    """Check if the refresh interval has elapsed since last sync."""
    interval = st.session_state.get("wc_refresh_interval", 60)
    if interval <= 0:
        return False  # Manual mode
    last_sync = st.session_state.get("live_sync_time")
    if last_sync is None:
        return True
    elapsed = (datetime.now() - last_sync).total_seconds()
    return elapsed >= interval


def load_live_source(force_refresh=False):
    """Stateless fetch with stateful session update."""
    if force_refresh or _should_autorefresh():
        load_from_woocommerce.clear()
    results = load_from_woocommerce()

    if results and isinstance(results, dict):
        # 1. Update Partitioned State
        partitions = results.get("partitions", {})
        for key, df in partitions.items():
            if df is not None:
                st.session_state[key] = df

        # 2. Update Slot Metadata
        slots = results.get("slots", {})
        for key, val in slots.items():
            if val is not None:
                st.session_state[key] = val

        # 3. Update Sync Metadata
        st.session_state.live_sync_time = datetime.now()

        # 4. Update Full Context for Forecasting
        st.session_state["wc_full_df"] = results.get("df_to_return")

        # 4. Silent Autosave for Offline Mode Fallback
        try:
            from src.utils.snapshots import save_sales_snapshot
            if not results["df_to_return"].empty:
                save_sales_snapshot(results["df_to_return"])
        except Exception:
            pass

        # 5. Return tuple for legacy unpacking
        return results["df_to_return"], results["sync_desc"], results["modified_at"]

    # Handle legacy return if any (for safety)
    if results:
        st.session_state.live_sync_time = datetime.now()
        return results

    raise ValueError("Failed to load WooCommerce live data.")


def get_items_sold_label(last_updated):
    from datetime import datetime, timedelta, timezone

    tz_bd = timezone(timedelta(hours=6))
    try:
        if (
            isinstance(last_updated, str)
            and last_updated != "N/A"
            and "snapshot" not in last_updated.lower()
        ):
            dt = datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S")
            # Assume last updated time string is already in local tz
            if dt.hour < 16:
                return "Items to be sold"
    except Exception:
        pass

    if datetime.now(tz_bd).hour < 16:
        return "Items to be sold"
    return "Item sold"

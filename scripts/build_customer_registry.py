"""Rebuild / refresh the full 3-bucket customer registry from live WooCommerce orders.

This fulfils the contract described in src/utils/customer_registry_full.py: the
customer_registry_full.json is maintained from WooCommerce order history.

Because the store has >100k historical orders and the REST API key only has
order/read scope (the /customers endpoint is forbidden), we build the registry
from the ORDERS endpoint, which carries customer_id (0 for guest checkouts),
billing email, phone, name and date. We merge into the existing registry so the
script is safe to run repeatedly (idempotent: first_seen only ever moves earlier).

Usage:
    python scripts/build_customer_registry.py [--window-days N] [--max-pages M] [--dry-run]

    --window-days N   Only orders modified within the last N days (default: 30).
                      Use a large value (or --all) to sweep deeper history.
    --max-pages M     Hard cap on API pages pulled (default: 50) to avoid long runs.
    --all             Sweep the whole history (still capped by --max-pages).
    --dry-run         Fetch and count, but do not write the registry file.

The flattened order row uses the same column names the registry expects
(Order Date, Full Name (Billing), Billing Email, Phone (Billing), Shipping City,
Customer ID) so update_full_registry_from_df can consume it directly.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import pandas as pd
import requests
from requests.auth import HTTPBasicAuth  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.settings import get_woocommerce_config  # noqa: E402
from src.utils.customer_registry_full import (  # noqa: E402
    FULL_REGISTRY_PATH,
    update_full_registry_from_df,
)


def _flatten_order(o: dict) -> dict:
    """Extract the columns update_full_registry_from_df expects from a raw order."""
    billing = o.get("billing") or {}
    shipping = o.get("shipping") or {}
    cid = o.get("customer_id")
    return {
        "Order ID": o.get("id"),
        "Order Date": o.get("date_created") or o.get("date_modified"),
        "Full Name (Billing)": billing.get("first_name", "")
        + (" " + billing.get("last_name", "") if billing.get("last_name") else ""),
        "Billing Email": billing.get("email", ""),
        "Phone (Billing)": billing.get("phone", ""),
        "Shipping City": shipping.get("city", ""),
        "Customer ID": cid if cid not in (None, 0, "0") else "",
    }


def fetch_orders(cfg: dict, window_days: int | None, max_pages: int) -> list[dict]:
    auth = HTTPBasicAuth(cfg["consumer_key"], cfg["consumer_secret"])
    url = f"{cfg['store_url'].rstrip('/')}/wp-json/wc/v3/orders"
    params = {"per_page": 100, "orderby": "date", "order": "desc", "page": 1}
    if window_days:
        from datetime import datetime, timedelta, timezone

        since = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        params["after"] = since
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        params["page"] = page
        try:
            r = requests.get(url, params=params, auth=auth, timeout=60)
        except Exception as e:  # noqa: BLE001
            print(f"  request failed on page {page}: {e}")
            break
        if r.status_code != 200:
            print(f"  HTTP {r.status_code} on page {page}: {r.text[:120]}")
            break
        batch = r.json()
        if not batch:
            break
        out.extend(batch)
        # Stop early if windowed and we've passed the cutoff (orders are date-desc).
        if window_days and len(batch) < 100:
            break
        time.sleep(0.25)  # be gentle with the API
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--window-days", type=int, default=30)
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument(
        "--all", action="store_true", help="Sweep full history (ignores window)."
    )
    ap.add_argument("--dry-run", action="store_true", help="Do not write the registry.")
    args = ap.parse_args()

    cfg = get_woocommerce_config(required=True)
    window = None if args.all else args.window_days

    print(
        f"Pulling orders (window={'ALL' if args.all else f'{args.window_days}d'}, "
        f"max_pages={args.max_pages}) ..."
    )
    raw = fetch_orders(cfg, window, args.max_pages)
    print(f"  fetched {len(raw)} raw orders")

    if not raw:
        print("Nothing to process.")
        return 0

    rows = [_flatten_order(o) for o in raw]
    df = pd.DataFrame(rows)
    # Drop rows with no usable identity (no email, no phone, no customer_id).
    df = df[
        df["Billing Email"].astype(str).str.strip().ne("")
        | df["Phone (Billing)"].astype(str).str.strip().ne("")
        | df["Customer ID"].astype(str).str.strip().ne("")
    ]
    print(f"  {len(df)} rows with a resolvable identity")

    if args.dry_run:
        print("DRY RUN: not writing registry.")
        return 0

    updated = update_full_registry_from_df(df)
    print(f"  registry updated (+{updated} new/refreshed identities)")
    print(f"  wrote {FULL_REGISTRY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

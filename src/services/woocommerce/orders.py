"""Shared WooCommerce order helpers: status updates and order-ID extraction.

Consolidates logic that previously lived in `src/pages/pathao_orders.py` and
`src/pages/woocommerce_orders.py` so every caller uses one implementation.
"""

from __future__ import annotations

import re

from requests.auth import HTTPBasicAuth

from src.config.settings import get_woocommerce_config
from src.utils.http import request_with_backoff


def update_order_status(
    order_id: str | int, status: str, note: str | None = None
) -> tuple[bool, str]:
    """Update a WooCommerce order's status via the REST API.

    Returns ``(ok, message)``. A failure message carries the reason; on success
    the message is ``"Success"``. Attaching a note is best-effort — a failed
    note never fails the status update itself.
    """
    wc_info = get_woocommerce_config(required=False)
    wc_url = wc_info.get("store_url")
    wc_key = wc_info.get("consumer_key")
    wc_secret = wc_info.get("consumer_secret")

    if not all([wc_url, wc_key, wc_secret]):
        return False, "Missing WooCommerce credentials"

    url = f"{wc_url.rstrip('/')}/wp-json/wc/v3/orders/{order_id}"
    payload = {"status": status}

    try:
        auth = HTTPBasicAuth(wc_key, wc_secret)
        res = request_with_backoff("PUT", url, json=payload, auth=auth, timeout=10)
        res.raise_for_status()

        if note:
            try:
                note_url = f"{url}/notes"
                request_with_backoff(
                    "POST",
                    note_url,
                    json={"note": note, "customer_note": False},
                    auth=auth,
                    timeout=10,
                )
            except Exception:
                pass  # Best-effort note; never fail the status update.

        return True, "Success"
    except Exception as e:
        return False, str(e)


def extract_order_id(raw_value) -> str | None:
    """Strictly parse a WooCommerce order ID from an exported string.

    Accepts optional ``#`` / ``wc-`` / ``order-`` / ``invoice-`` prefixes and an
    optional trailing ``c``/``w``/``s`` marker (Pathao merchant-ID style).
    Returns ``None`` when the whole string is not a clean order ID.
    """
    text = str(raw_value).strip()
    if not text or text.lower() in {"nan", "none", "n/a", "null"}:
        return None

    match = re.fullmatch(
        r"(?:#|wc-|order-|invoice-|m-|d-)?(\d+)(?:\s*[cws])?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1)

    if text.isdigit():
        return text

    return None


def extract_merchant_order_id(merchant_id) -> str:
    """Leniently extract a base WooCommerce order ID from a Pathao merchant ID.

    Falls back to the cleaned input string when no digit group is found, so the
    result is always usable as a merge key.
    """
    text = str(merchant_id).strip()
    if not text or text.lower() in {"nan", "none", "n/a", "null"}:
        return ""

    match = re.search(r"(?:M-|D-)?(\d+)(?:\s*[cws])?", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return text

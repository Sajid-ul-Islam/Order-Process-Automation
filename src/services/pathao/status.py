"""Pathao order status and credential verification helpers with persistent disk caching."""

import json
import os
import time

from src.config.constants import RESOURCES_DIR
from src.config.settings import get_pathao_config
from src.services.pathao.client import PathaoClient
from src.utils.http import request_with_backoff

PATHAO_CACHE_FILE = os.path.join(RESOURCES_DIR, "pathao_status_cache.json")

TERMINAL_PATHAO_STATUSES = {
    "delivered",
    "returned",
    "return_delivered",
    "cancelled",
    "partial_delivered",
    "refunded",
    "failed",
    "status not found",
}


def _load_pathao_disk_cache() -> dict:
    """Load persistent Pathao status cache from disk."""
    if os.path.exists(PATHAO_CACHE_FILE):
        try:
            with open(PATHAO_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_pathao_disk_cache(cache: dict):
    """Save persistent Pathao status cache to disk."""
    try:
        os.makedirs(RESOURCES_DIR, exist_ok=True)
        with open(PATHAO_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_pathao_credentials() -> dict | None:
    """Extract Pathao credentials from supported config sources."""
    creds = get_pathao_config(required=False)
    required = ("base_url", "client_id", "client_secret", "username", "password")
    if not all(creds.get(key) for key in required):
        return None
    return creds


def _build_pathao_client() -> tuple[PathaoClient | None, str | None]:
    """Create a Pathao client from configured credentials."""
    creds = get_pathao_credentials()
    if not creds:
        return None, (
            "Pathao credentials are missing. Configure a complete [pathao] "
            "section in .streamlit/secrets.toml or set the PATHAO_* env vars."
        )

    try:
        return PathaoClient(**creds), None
    except Exception as exc:
        return None, f"Failed to initialize Pathao client: {exc}"


def verify_pathao_connection() -> tuple[bool, str]:
    """Verify if Pathao credentials are working by requesting an access token."""
    client, error = _build_pathao_client()
    if error:
        return False, error

    try:
        client.ensure_token()
        if client.access_token:
            return (
                True,
                "Successfully authenticated with Pathao API. Credentials are working.",
            )
        return False, "Authentication failed. Pathao did not return an access token."
    except Exception as exc:
        return False, f"Connection error: {exc}"


def get_pathao_order_status(
    consignment_id: str, force_refresh: bool = False, cache_ttl_seconds: int = 3600
) -> dict:
    """
    Fetch status of a Pathao order with persistent disk caching to prevent API rate limiting.

    Terminal statuses (Delivered, Returned, etc.) are served permanently from cache.
    Non-terminal statuses are cached for `cache_ttl_seconds` (default 1 hour).
    """
    if not consignment_id or not str(consignment_id).strip():
        return {"error": "Invalid consignment ID"}

    cid = str(consignment_id).strip()
    disk_cache = _load_pathao_disk_cache()

    if not force_refresh and cid in disk_cache:
        cached_entry = disk_cache[cid]
        cached_data = cached_entry.get("data", {})
        cached_ts = cached_entry.get("timestamp", 0)

        status_str = ""
        if isinstance(cached_data, dict):
            status_str = str(
                cached_data.get("data", {}).get("order_status", "")
                or cached_data.get("order_status", "")
            ).lower()

        # Terminal status -> Return permanently from cache
        if any(term in status_str for term in TERMINAL_PATHAO_STATUSES):
            return cached_data

        # Non-terminal status -> Check TTL (1 hour)
        if time.time() - cached_ts < cache_ttl_seconds:
            return cached_data

    # Fetch fresh status from Pathao API
    client, error = _build_pathao_client()
    if error:
        if cid in disk_cache:
            return disk_cache[cid].get("data", {})
        return {"error": error}

    try:
        headers = client._get_headers()
        if not client.access_token:
            if cid in disk_cache:
                return disk_cache[cid].get("data", {})
            return {
                "error": "Authentication failed. Pathao access token is unavailable."
            }

        status_url = f"{client.base_url}/aladdin/api/v1/orders/{cid}/info"
        status_response = request_with_backoff(
            "GET", status_url, headers=headers, timeout=10
        )

        if status_response.status_code == 200:
            resp_json = status_response.json()
            disk_cache[cid] = {
                "timestamp": time.time(),
                "data": resp_json,
            }
            _save_pathao_disk_cache(disk_cache)
            return resp_json

        if cid in disk_cache:
            return disk_cache[cid].get("data", {})

        return {
            "error": f"Failed to fetch status: {status_response.status_code} - {status_response.text}"
        }

    except Exception as exc:
        if cid in disk_cache:
            return disk_cache[cid].get("data", {})
        return {"error": f"Request failed: {exc}"}


def batch_get_pathao_order_statuses(
    consignment_ids: list, force_refresh: bool = False, max_workers: int = 3
) -> dict[str, str]:
    """
    Fetch statuses for a list of consignment IDs in batch, serving cached records first
    and only querying Pathao API for uncached orders to avoid blocking/rate-limiting.
    """
    if not consignment_ids:
        return {}

    unique_cids = list(
        set([str(c).strip() for c in consignment_ids if c and str(c).strip()])
    )
    results = {}
    missing_cids = []

    disk_cache = _load_pathao_disk_cache()

    for cid in unique_cids:
        if not force_refresh and cid in disk_cache:
            cached_entry = disk_cache[cid]
            cached_data = cached_entry.get("data", {})
            cached_ts = cached_entry.get("timestamp", 0)

            st_str = ""
            if isinstance(cached_data, dict):
                st_str = str(
                    cached_data.get("data", {}).get("order_status", "")
                    or cached_data.get("order_status", "")
                ).strip()

            st_lower = st_str.lower()
            if any(term in st_lower for term in TERMINAL_PATHAO_STATUSES) or (
                time.time() - cached_ts < 3600
            ):
                results[cid] = st_str if st_str else "Status Not Found"
                continue

        missing_cids.append(cid)

    if not missing_cids:
        return results

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _fetch_one(cid):
        res = get_pathao_order_status(cid, force_refresh=force_refresh)
        status_val = "Status Not Found"
        if isinstance(res, dict):
            if (
                "data" in res
                and isinstance(res["data"], dict)
                and "order_status" in res["data"]
            ):
                status_val = res["data"]["order_status"]
            elif "order_status" in res:
                status_val = res["order_status"]
        return cid, status_val

    with ThreadPoolExecutor(
        max_workers=min(len(missing_cids), max_workers)
    ) as executor:
        future_to_cid = {executor.submit(_fetch_one, cid): cid for cid in missing_cids}
        for future in as_completed(future_to_cid):
            cid = future_to_cid[future]
            try:
                _, status_val = future.result()
                results[cid] = status_val
            except Exception:
                results[cid] = "Status Not Found"

    return results

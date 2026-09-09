"""
Diagnostic tool for WooCommerce multi-warehouse inventory plugins.

Run this to detect which plugin is installed and how it stores outlet stock data.
"""

import json
import re
from typing import Any, Dict, List

from requests.auth import HTTPBasicAuth

from src.utils.http import request_with_backoff


def diagnose_woocommerce_outlets(
    store_url: str, consumer_key: str, consumer_secret: str
) -> Dict[str, Any]:
    """
    Diagnose which multi-warehouse plugin is installed and how it stores data.
    Returns a report dict with detection results.
    """
    auth = HTTPBasicAuth(consumer_key, consumer_secret)
    base_url = store_url.rstrip("/")
    report: Dict[str, Any] = {
        "detected_plugin": None,
        "storage_method": None,
        "locations": [],
        "sample_data": {},
        "meta_keys": [],
    }

    # ── Check for weLaunch Multi Inventory ──────────────────────────────────
    print("🔍 Checking for weLaunch Multi Inventory...")
    try:
        res = request_with_backoff(
            "GET",
            f"{base_url}/wp-json/wc/multi-inventory/v1/inventories",
            auth=auth,
            timeout=10,
        )
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                report["detected_plugin"] = "weLaunch Multi Inventory"
                report["storage_method"] = "custom_rest_api"
                report["locations"] = [
                    item.get("name", f"Location {item.get('id', i)}")
                    for i, item in enumerate(data)
                ]
                report["sample_data"]["inventories"] = data[:3]
                print(f"   ✅ Found {len(data)} inventory locations")
                return report
    except Exception as e:
        print(f"   ❌ Not found: {e}")

    # ── Check for Stock Locations for WooCommerce ──────────────────────────
    print("🔍 Checking for Stock Locations for WooCommerce...")
    try:
        # Check if the plugin's taxonomy is registered
        res = request_with_backoff(
            "GET",
            f"{base_url}/wp-json/wc/v3/products/categories",
            auth=auth,
            params={"per_page": 1},
            timeout=10,
        )
        # The plugin adds a custom taxonomy; we'll detect via product meta
    except Exception:
        pass

    # ── Scan product meta for known patterns ───────────────────────────────
    print("🔍 Scanning product meta for outlet stock patterns...")
    patterns = {
        "_stock_at_location": re.compile(r"^_stock_at_location_(?P<loc>.+)$"),
        "_location_stock": re.compile(r"^_location_(?P<loc>.+)_stock$"),
        "_outlet_qty": re.compile(r"^_outlet_(?P<loc>.+)_qty$"),
        "_outlet_stock": re.compile(r"^_outlet_(?P<loc>.+)_stock$"),
        "_warehouse_qty": re.compile(r"^_warehouse_(?P<loc>.+)_qty$"),
        "_warehouse_stock": re.compile(r"^_warehouse_(?P<loc>.+)_stock$"),
        "_stock_qty": re.compile(r"^_stock_(?P<loc>.+)_qty$"),
        "_stock_": re.compile(r"^_stock_(?P<loc>.+)$"),
        "_wms_outlet": re.compile(r"^_wms_(?P<loc>.+)$"),
        "stock_at_": re.compile(r"^stock_at_(?P<loc>.+)$"),
        "multi_location_stock": re.compile(r"^_multi_location_(?P<loc>.+)_stock$"),
    }

    found_meta_keys: Dict[str, List[str]] = {}
    location_names: List[str] = []

    try:
        # Fetch products with meta_data
        page = 1
        products_checked = 0
        while products_checked < 200:
            res = request_with_backoff(
                "GET",
                f"{base_url}/wp-json/wc/v3/products",
                auth=auth,
                params={
                    "per_page": 50,
                    "page": page,
                    "_fields": "id,name,sku,meta_data",
                },
                timeout=15,
            )
            if res.status_code != 200:
                break
            products = res.json()
            if not products:
                break

            for product in products:
                products_checked += 1
                for meta in product.get("meta_data", []):
                    key = meta.get("key", "")
                    for pattern_name, pattern in patterns.items():
                        match = pattern.match(key)
                        if match:
                            loc = match.group("loc").strip().title()
                            if loc not in location_names:
                                location_names.append(loc)
                            if pattern_name not in found_meta_keys:
                                found_meta_keys[pattern_name] = []
                            if key not in found_meta_keys[pattern_name]:
                                found_meta_keys[pattern_name].append(key)

            page += 1
            if len(products) < 50:
                break

    except Exception as e:
        print(f"   ❌ Error scanning: {e}")

    if found_meta_keys:
        report["detected_plugin"] = "Detected via meta pattern scan"
        report["storage_method"] = "product_meta"
        report["locations"] = location_names
        report["meta_keys"] = {
            pattern: keys[:5] for pattern, keys in found_meta_keys.items()
        }
        report["sample_data"]["found_patterns"] = {
            k: v[:3] for k, v in found_meta_keys.items()
        }
        print(f"   ✅ Found {len(location_names)} locations via meta scan")
        return report

    # ── Check for custom REST endpoints from other plugins ──────────────────
    print("🔍 Checking custom REST API endpoints...")
    custom_endpoints = [
        ("Multi Inventory", "/wp-json/wc/multi-inventory/v1/inventories"),
        ("Stock Locations", "/wp-json/stock-locations/v1/locations"),
        ("Custom Inventory", "/wp-json/custom-inventory/v1/outlet-stock"),
        ("WMS", "/wp-json/wms/v1/stock"),
    ]

    for plugin_name, endpoint in custom_endpoints:
        try:
            res = request_with_backoff(
                "GET",
                f"{base_url}{endpoint}",
                auth=auth,
                params={"per_page": 1},
                timeout=10,
            )
            if res.status_code == 200:
                report["detected_plugin"] = plugin_name
                report["storage_method"] = "custom_rest_api"
                print(f"   ✅ Found {plugin_name} at {endpoint}")
                return report
        except Exception:
            continue

    # ── Check WooCommerce settings for multi-location hints ────────────────
    print("🔍 Checking WooCommerce settings...")
    try:
        res = request_with_backoff(
            "GET",
            f"{base_url}/wp-json/wc/v3/settings/general",
            auth=auth,
            timeout=10,
        )
        if res.status_code == 200:
            settings = res.json()
            for setting in settings:
                if "location" in setting.get("id", "").lower():
                    report["sample_data"]["settings_hint"] = setting
    except Exception:
        pass

    # ── Check installed plugins (if WP debug/info available) ───────────────
    print("🔍 Checking for plugin hints...")
    try:
        res = request_with_backoff(
            "GET",
            f"{base_url}/wp-json/wp/v2/plugins",
            auth=auth,
            timeout=10,
        )
        if res.status_code == 200:
            plugins = res.json()
            relevant = [
                p
                for p in plugins
                if any(
                    kw in p.get("name", "").lower()
                    for kw in ["stock", "location", "warehouse", "inventory", "outlet"]
                )
            ]
            if relevant:
                report["sample_data"]["installed_plugins"] = [
                    p.get("name") for p in relevant
                ]
    except Exception:
        pass

    return report


if __name__ == "__main__":
    # Example usage
    report = diagnose_woocommerce_outlets(
        store_url="https://your-store.com",
        consumer_key="ck_xxxxx",
        consumer_secret="cs_xxxxx",
    )
    print(json.dumps(report, indent=2, default=str))

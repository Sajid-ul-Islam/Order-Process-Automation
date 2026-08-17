"""Shared helpers for the Pathao Processor page: highlighters, client, state, and data prep."""

from __future__ import annotations

import json
import os

import streamlit as st

from src.config.settings import get_pathao_config
from src.services.pathao.client import PathaoClient
from src.state.persistence import clear_state_keys

REQUIRED_COLUMNS = ["Phone (Billing)"]
SOURCE_WOOCOM = "WooCommerce Processing"
SOURCE_UPLOAD = "Upload / URL"


def _highlight_status(col):
    return [
        (
            "background-color: rgba(239, 68, 68, 0.15); color: #ef4444; font-weight: 600;"
            if any(x in str(v).lower() for x in ["return", "failed", "cancel", "error"])
            else (
                "color: #10b981; font-weight: 600;"
                if "delivered" in str(v).lower()
                else (
                    "color: #3b82f6; font-weight: 500;"
                    if any(
                        x in str(v).lower()
                        for x in ["transit", "processing", "assigned"]
                    )
                    else ""
                )
            )
        )
        for v in col
    ]


def _highlight_split_orders(row):
    spec_inst = str(row.get("SpecialInstruction", ""))
    if "PARTIAL ORDER" in spec_inst:
        return [
            "background-color: rgba(245, 158, 11, 0.15); color: #b45309; font-weight: bold;"
        ] * len(row)
    if "SPLIT " in spec_inst:
        return [
            "background-color: rgba(239, 68, 68, 0.15); color: #ef4444; font-weight: bold;"
        ] * len(row)
    return [""] * len(row)


def _get_pathao_client():
    try:
        return PathaoClient(**get_pathao_config(required=True))
    except ValueError as exc:
        st.error(str(exc))
        return None


def _reset_pathao_state():
    clear_state_keys(
        [
            "pathao_res_df",
            "pathao_preview_df",
            "pathao_preview_source",
            "pathao_vlink_df",
            "show_vlink_gen",
            "pathao_auto_process",
            "pathao_manual_items_df",
            "pathao_manual_desc",
        ]
    )


def _filter_processing_orders(df):
    status_col = (
        "Order Status"
        if "Order Status" in df.columns
        else "Status" if "Status" in df.columns else None
    )
    if not status_col:
        return df.copy(), False

    filtered_df = df[df[status_col].astype(str).str.lower() == "processing"].copy()
    return filtered_df, True


def _sync_pathao_map():
    with st.status("Connecting to Pathao API...", expanded=True) as status:
        try:
            client = _get_pathao_client()
            if client is None:
                status.update(label="Sync blocked", state="error")
                return
            st.write("Fetching cities...")
            cities, error = client.get_cities()

            if error:
                st.error(f"Sync failed: {error}")
                status.update(label="Sync failed", state="error")
                return

            if not cities:
                st.warning(
                    "Connected successfully, but Pathao returned an empty city list."
                )
                status.update(label="Sync complete (empty)", state="complete")
                return

            full_map = {}
            progress_bar = st.progress(0)
            for i, city in enumerate(cities):
                city_id = city["city_id"]
                city_name = city["city_name"]
                st.write(f"Syncing {city_name}...")
                zones, zone_error = client.get_zones(city_id)

                full_map[city_name] = {"city_id": city_id, "zones": {}}
                if not zone_error:
                    for zone in zones:
                        zone_id = zone["zone_id"]
                        zone_name = zone["zone_name"]
                        areas, area_error = client.get_areas(zone_id)
                        full_map[city_name]["zones"][zone_name] = {
                            "zone_id": zone_id,
                            "areas": areas if not area_error else [],
                        }

                progress_bar.progress((i + 1) / len(cities))

            os.makedirs("resources", exist_ok=True)
            with open("resources/pathao_map.json", "w", encoding="utf-8") as f:
                json.dump(full_map, f, indent=4)

                st.toast(
                    f"🌆 Successfully synced {len(cities)} cities and their areas."
                )
            status.update(label="Sync complete", state="complete")
        except Exception as exc:
            st.error(f"Sync failed: {exc}")
            status.update(label="Sync error", state="error")


def _load_processing_orders_from_woocommerce():
    if st.session_state.get("wc_curr_df") is not None:
        df_live = st.session_state.wc_curr_df
        st.info("Using the current operational WooCommerce snapshot.")
    else:
        from src.services.woocommerce.client import load_live_source

        with st.status("Connecting to WooCommerce API...", expanded=True) as status:
            st.write("📡 Fetching live orders...")
            df_live, _, _ = load_live_source()
            status.update(
                label="WooCommerce Sync Complete", state="complete", expanded=False
            )
            st.toast("✅ Orders pulled successfully!", icon="🎉")

    return _filter_processing_orders(df_live)

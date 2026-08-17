"""Auto-Dispatch tab: create Pathao consignments and update WooCommerce status."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.components.ui.dataframe_search import render_dataframe_search
from src.components.ui.widgets import section_card
from src.pages.pathao_orders.shared import _get_pathao_client
from src.services.woocommerce.orders import extract_order_id, update_order_status


def _render_auto_dispatch_tab():
    """Feature #1: Push processed Pathao orders directly via Pathao API (bulk create)."""
    section_card(
        "Auto-Dispatch to Pathao — One-Click API Push",
        "Automatically create consignments on Pathao for all processed orders without manual portal upload.",
    )

    result_df = st.session_state.get("pathao_res_df")
    if result_df is None or result_df.empty:
        st.info(
            "⚡ No processed orders found. Go to **Order Processing** tab first, pull orders and run 'Process orders'."
        )
        return

    with st.expander("📄 Preview Orders for Dispatch", expanded=False):
        dispatch_search = render_dataframe_search(
            result_df, "pathao_dispatch", height=400
        )
        st.dataframe(dispatch_search.head(20), use_container_width=True)

    with st.expander("⚙️ Dispatch Settings", expanded=True):
        dc1, dc2, dc3 = st.columns(3)
        with dc1:
            item_type = st.selectbox(
                "Item Type",
                [2, 1, 3],
                format_func=lambda x: {2: "Parcel", 1: "Document", 3: "Fragile"}[x],
            )
        with dc2:
            delivery_type = st.selectbox(
                "Delivery Type",
                [48, 12],
                format_func=lambda x: {48: "Normal (48h)", 12: "Express (12h)"}[x],
            )
        with dc3:
            special_instructions = st.text_input(
                "Special Instructions", placeholder="Handle with care..."
            )

    if st.button(
        "🚀 Push to Pathao API",
        type="primary",
        use_container_width=True,
        key="pathao_autodispatch_btn",
    ):
        client = _get_pathao_client()
        if client is None:
            return

        success_count = 0
        fail_count = 0
        fail_details = []
        wc_status_fails = []

        with st.status(
            f"Dispatching {len(result_df)} orders to Pathao...", expanded=True
        ) as dispatch_status:
            progress = st.progress(0)
            total = len(result_df)

            for i, (_, row) in enumerate(result_df.iterrows()):
                try:
                    # Build Pathao order payload from processed dataframe columns
                    payload = {
                        "merchant_order_id": str(row.get("Order ID", f"ORD-{i}")),
                        "recipient_name": str(row.get("Name", "Customer")),
                        "recipient_phone": str(row.get("Phone", "")).replace(" ", ""),
                        "recipient_address": str(row.get("Address", "")),
                        "recipient_city": int(row.get("CityId", 1)),
                        "recipient_zone": int(row.get("ZoneId", 1)),
                        "recipient_area": (
                            int(row.get("AreaId", 0)) if row.get("AreaId") else None
                        ),
                        "delivery_type": delivery_type,
                        "item_type": item_type,
                        "special_instruction": str(
                            row.get("SpecialInstruction", special_instructions)
                        ),
                        "item_quantity": int(row.get("Qty", 1)),
                        "item_weight": float(row.get("Weight", 0.5)),
                        "amount_to_collect": float(row.get("COD", row.get("Total", 0))),
                        "item_description": str(row.get("ItemDesc", "")),
                    }
                    # Remove None fields
                    payload = {
                        k: v for k, v in payload.items() if v is not None and v != ""
                    }

                    headers = client._get_headers()
                    from src.utils.http import request_with_backoff

                    res = request_with_backoff(
                        "POST",
                        f"{client.base_url}/aladdin/api/v1/orders",
                        json=payload,
                        headers=headers,
                        timeout=15,
                    )
                    res.raise_for_status()
                    resp_data = res.json().get("data", {})
                    consignment_id = resp_data.get("consignment_id", "Created")

                    # Update the WooCommerce order status so the dispatched order
                    # shows up in the dashboard's shipped views.
                    wc_order_id = extract_order_id(payload["merchant_order_id"])
                    if wc_order_id:
                        wc_ok, wc_msg = update_order_status(
                            wc_order_id,
                            "confirmed",
                            note=f"Dispatched via Pathao — Consignment {consignment_id}",
                        )
                        if not wc_ok:
                            wc_status_fails.append(
                                {
                                    "Order": wc_order_id,
                                    "Consignment": consignment_id,
                                    "Error": wc_msg,
                                }
                            )
                            st.write(
                                f"⚠️ Order {wc_order_id} dispatched, but WooCommerce status update failed ({wc_msg})"
                            )

                    st.write(
                        f"✅ Order {payload['merchant_order_id']} → Consignment: {consignment_id}"
                    )
                    success_count += 1
                except Exception as exc:
                    fail_count += 1
                    fail_details.append(
                        {"Order": str(row.get("Order ID", i)), "Error": str(exc)}
                    )
                    st.write(f"❌ Order {row.get('Order ID', i)}: {exc}")

                progress.progress((i + 1) / total)

            if fail_count == 0:
                dispatch_status.update(
                    label=f"✅ All {success_count} orders dispatched!",
                    state="complete",
                    expanded=False,
                )
            else:
                dispatch_status.update(
                    label=f"⚠️ {success_count} dispatched, {fail_count} failed",
                    state="error",
                    expanded=True,
                )

        if fail_details:
            with st.expander(f"❌ {fail_count} Failed Orders"):
                st.dataframe(pd.DataFrame(fail_details), use_container_width=True)

        if wc_status_fails:
            with st.expander(
                f"⚠️ {len(wc_status_fails)} WooCommerce Status Update Failures"
            ):
                st.caption(
                    "Orders were dispatched on Pathao, but their WooCommerce status could not be updated. Update them manually in WooCommerce Orders."
                )
                st.dataframe(pd.DataFrame(wc_status_fails), use_container_width=True)

"""Validate processed parcels and map them to Pathao's order API schema."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any


class PathaoOrderError(RuntimeError):
    """A dispatch failure, including whether Pathao might have created it."""

    def __init__(self, message: str, *, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


def _text(value: Any) -> str:
    if value is None:
        return ""
    result = str(value).strip()
    if result.lower() in {"nan", "none", "null", "<na>", "nat", "n/a"}:
        return ""
    return result


def _number(value: Any, field: str, *, positive=False, integer=False):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a valid number.")
    try:
        number = float(_text(value))
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{field} must be a valid number.") from None
    if not math.isfinite(number) or number < 0 or (positive and number == 0):
        qualifier = "greater than zero" if positive else "zero or greater"
        raise ValueError(f"{field} must be a finite number {qualifier}.")
    if integer:
        if not number.is_integer():
            raise ValueError(f"{field} must be a whole number.")
        return int(number)
    return number


def _phone(value: Any) -> str:
    raw = _text(value)
    # Numeric spreadsheet cells may arrive as floats with a trailing .0.
    if re.fullmatch(r"[0-9]+\.0+", raw):
        raw = raw.split(".")[0]
    raw = "".join(str(int(c)) if c.isdecimal() else c for c in raw)
    if not re.fullmatch(r"\+?[0-9\s()\-]+", raw):
        raise ValueError(
            "RecipientPhone(*) must contain a complete Bangladesh mobile number."
        )
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("880") and len(digits) in (13, 14):
        digits = digits[3:]
    if len(digits) == 10 and digits.startswith("1"):
        digits = "0" + digits
    if not re.fullmatch(r"01[3-9][0-9]{8}", digits) or digits[3:] == "00000000":
        raise ValueError(
            "RecipientPhone(*) must be a valid Bangladesh mobile number, "
            "not a placeholder."
        )
    return digits


def build_order_payload(
    row: Mapping[str, Any],
    store_id: Any,
    *,
    delivery_type: int = 48,
    item_type: int = 2,
    special_instructions: str = "",
) -> dict[str, Any]:
    """Build one API parcel from the processor's actual Excel column names.

    No customer, order identifier, or COD fallback is permitted. Pathao resolves
    delivery geography from the complete address; numeric location IDs are
    deliberately omitted, following its July 2025 auto-address API update.
    """
    store = _number(store_id, "Pickup store", positive=True, integer=True)
    merchant_id = _text(row.get("MerchantOrderId"))
    if not merchant_id or merchant_id.lower() in {"0", "0.0", "unknown"}:
        raise ValueError(
            "MerchantOrderId is required; correct the source order identifier."
        )
    if re.fullmatch(r"[0-9]+\.0+", merchant_id):
        merchant_id = merchant_id.split(".")[0]
    name = _text(row.get("RecipientName(*)"))
    if not name or name.lower() in {"customer", "unknown"}:
        raise ValueError("RecipientName(*) must contain the customer's name.")
    address = _text(row.get("RecipientAddress(*)"))
    if not address or address.lower() in {"address missing", "unknown", "missing"}:
        raise ValueError(
            "RecipientAddress(*) must contain the complete delivery address."
        )
    for field in ("RecipientArea", "RecipientZone(*)", "RecipientCity(*)"):
        location = _text(row.get(field))
        if location and location.casefold() not in address.casefold():
            address += f", {location}"

    instruction_parts = []
    for value in (row.get("SpecialInstruction"), special_instructions):
        instruction = _text(value)
        if instruction and instruction not in instruction_parts:
            instruction_parts.append(instruction)

    return {
        "store_id": store,
        "merchant_order_id": merchant_id,
        "recipient_name": name,
        "recipient_phone": _phone(row.get("RecipientPhone(*)")),
        "recipient_address": address,
        "delivery_type": _number(
            delivery_type, "Delivery type", positive=True, integer=True
        ),
        "item_type": _number(item_type, "Item type", positive=True, integer=True),
        "item_quantity": _number(
            row.get("ItemQuantity"), "ItemQuantity", positive=True, integer=True
        ),
        "item_weight": _number(row.get("ItemWeight"), "ItemWeight", positive=True),
        "amount_to_collect": _number(
            row.get("AmountToCollect(*)"), "AmountToCollect(*)"
        ),
        "item_description": _text(row.get("ItemDesc")),
        "special_instruction": " | ".join(instruction_parts),
    }

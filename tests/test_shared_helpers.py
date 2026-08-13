"""Regression tests for shared helpers introduced by the modularization refactor.

Covers the consolidated implementations so future edits to the shared functions
cannot silently drift from the behavior they replaced:
- `src/utils/text.normalize_phone_number` (canonical BD phone form)
- `src/utils/customer_registry.normalize_phone_key` (registry wrapper)
- `src/processing/whatsapp_processor.WhatsAppOrderProcessor.clean_phone_number`
- `src/config/constants.bd_now` / `bd_today` / `BD_TZ`
- `src/processing/column_detection.pick_column`
- `src/utils/file_io.read_uploaded`
"""

import pandas as pd
import pytest

from src.config.constants import BD_TZ, bd_now, bd_today
from src.processing.column_detection import pick_column
from src.processing.whatsapp_processor import WhatsAppOrderProcessor
from src.utils.customer_registry import normalize_phone_key
from src.utils.file_io import read_uploaded
from src.utils.text import normalize_phone_number


# ── Phone normalization ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("01712345678", "01712345678"),  # already canonical
        ("1712345678", "01712345678"),  # 10-digit without leading zero
        ("+8801712345678", "01712345678"),  # international with +
        ("8801712345678", "01712345678"),  # international without +
        ("88 0171 234 5678", "01712345678"),  # spaced
        ("+88-017-123-45678", "01712345678"),  # dashed
        ("01700000000", ""),  # placeholder number -> empty
        ("", ""),
        (None, ""),
        (float("nan"), ""),  # pandas NaN handled by wrappers
    ],
)
def test_normalize_phone_number_canonical(raw, expected):
    assert normalize_phone_number(raw) == expected


@pytest.mark.parametrize(
    "email",
    ["customer@gmail.com", "  Buyer@DEEN.Com "],
)
def test_normalize_phone_number_passthrough_emails(email):
    # Emails are keys, not phone numbers — returned as-is (stripped/lowercased).
    assert normalize_phone_number(email) == email.strip().lower()


def test_phone_normalizers_agree_across_consumers():
    """Registry + WhatsApp must produce the same canonical form."""
    wp = WhatsAppOrderProcessor()
    for raw in ["01712345678", "1712345678", "+8801712345678", "8801712345678"]:
        assert normalize_phone_key(raw) == normalize_phone_number(raw)
        assert wp.clean_phone_number(raw) == normalize_phone_number(raw)


def test_whatsapp_link_never_double_88():
    """wa.me links must not get a doubled country code for 88/880-prefixed inputs."""
    wp = WhatsAppOrderProcessor()
    for raw in ["01712345678", "+8801712345678", "8801712345678", "1712345678"]:
        phone = wp.clean_phone_number(raw)
        link = f"https://wa.me/+88{phone}"
        assert link == "https://wa.me/+8801712345678"


# ── BD time ───────────────────────────────────────────────────────────────────


def test_bd_tz_offset_is_utc_plus_6():
    assert BD_TZ.utcoffset(None).total_seconds() == 6 * 3600


def test_bd_now_is_aware_bd_time():
    now = bd_now()
    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 6 * 3600


def test_bd_today_matches_bd_now_date():
    assert bd_today() == bd_now().date()


# ── Column picking ────────────────────────────────────────────────────────────


def test_pick_column_returns_first_existing():
    df = pd.DataFrame(columns=["Phone", "Email", "Name"])
    assert pick_column(df, ["Phone (Billing)", "Phone", "phone"]) == "Phone"


def test_pick_column_default_when_absent():
    df = pd.DataFrame(columns=["Name"])
    assert pick_column(df, ["Phone", "Email"]) is None
    assert pick_column(df, ["Phone", "Email"], default="Name") == "Name"


def test_pick_column_none_dataframe():
    assert pick_column(None, ["Phone"]) is None


# ── File reading ──────────────────────────────────────────────────────────────


def test_read_uploaded_passthrough_dataframe():
    df = pd.DataFrame({"a": [1, 2]})
    assert read_uploaded(df) is df
    assert read_uploaded(None) is None


def test_compute_new_vs_returning_counts_refetch():
    from src.utils.customer_registry import compute_new_vs_returning_counts
    df = pd.DataFrame([
        {"Order ID": 100, "Phone": "01711111111", "Order Date": "2026-08-13 10:00:00"},
        {"Order ID": 101, "Phone": "01711111111", "Order Date": "2026-08-13 14:00:00"},
        {"Order ID": 102, "Phone": "01722222222", "Order Date": "2026-08-13 11:00:00"},
    ])
    new_cnt, ret_cnt = compute_new_vs_returning_counts(df, df)
    assert new_cnt == 2  # Order 100 (first for 01711111111) + Order 102 (01722222222)
    assert ret_cnt == 1  # Order 101 (repeat for 01711111111)

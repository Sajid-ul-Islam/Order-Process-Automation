"""Regression tests for stale-data detection in the WooCommerce live sync.

The store's REST API intermittently serves cached/older order data (the same
query returns different states minutes apart), so `load_live_source` retries
once with a cache-busting query param when a sync's data looks stale.

Rules locked in here for `_data_looks_stale`:

  - Empty / missing data is never "stale" (don't retry on nothing).
  - The newest order modification is compared against BD local time.
  - `mod_dt_parsed` is already BD-local naive.
  - The raw `Order Date Modified` column holds UTC/GMT values, so it is
    shifted +6h before comparing.
  - Default threshold: newest modification older than 45 minutes is stale.
"""

import pandas as pd
from datetime import timedelta

from src.services.woocommerce.client import _data_looks_stale, WC_STALE_MAX_AGE_MIN


def _now_bd():
    from datetime import datetime, timezone

    return datetime.now(timezone(timedelta(hours=6))).replace(tzinfo=None)


def test_empty_or_null_data_never_stale():
    assert _data_looks_stale(pd.DataFrame()) is False
    assert _data_looks_stale(None) is False
    assert _data_looks_stale(pd.DataFrame({"mod_dt_parsed": [None]})) is False
    assert _data_looks_stale(pd.DataFrame({"other": [1]})) is False


def test_parsed_mod_dt_within_threshold_is_fresh():
    now = _now_bd()
    df = pd.DataFrame({"mod_dt_parsed": [now - timedelta(minutes=30)]})
    assert _data_looks_stale(df) is False


def test_parsed_mod_dt_older_than_threshold_is_stale():
    now = _now_bd()
    df = pd.DataFrame(
        {"mod_dt_parsed": [now - timedelta(minutes=WC_STALE_MAX_AGE_MIN + 15)]}
    )
    assert _data_looks_stale(df) is True


def test_raw_utc_column_is_shifted_to_bd_before_comparing():
    now = _now_bd()
    # 30 min old in BD == (now - 6h30m) in UTC. After the +6h shift it must
    # read as 30 min old → fresh, not 6h30m old → stale.
    utc_30m = (now - timedelta(minutes=30) - timedelta(hours=6)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    df = pd.DataFrame({"Order Date Modified": [utc_30m]})
    assert _data_looks_stale(df) is False

    utc_2h = (now - timedelta(hours=2) - timedelta(hours=6)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    df2 = pd.DataFrame({"Order Date Modified": [utc_2h]})
    assert _data_looks_stale(df2) is True


def test_newest_mod_wins_when_mixed_ages():
    now = _now_bd()
    df = pd.DataFrame(
        {
            "mod_dt_parsed": [
                now - timedelta(hours=5),  # old line item
                now - timedelta(minutes=10),  # recent line item → fresh overall
            ]
        }
    )
    assert _data_looks_stale(df) is False


def test_load_stale_events_empty_and_non_stale_logs(tmp_path, monkeypatch):
    """Ensure _load_stale_events returns valid DataFrame and does not raise KeyError: 'ts'."""
    import json
    from src.pages.live_dashboard import _load_stale_events

    monkeypatch.setattr("src.config.constants.FEEDBACK_DIR", str(tmp_path))

    # 1. Non-existent file
    df = _load_stale_events()
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["ts", "type", "details"]
    assert df.empty

    # 2. File with unrelated events (e.g. WC_FETCH_INITIAL_ERROR)
    log_file = tmp_path / "system_logs.json"
    log_file.write_text(json.dumps([{"timestamp": "2026-08-28 08:33:20", "type": "WC_FETCH_INITIAL_ERROR", "details": "timeout"}]))
    df = _load_stale_events()
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["ts", "type", "details"]
    assert df.empty

    # 3. File with matching stale events
    log_file.write_text(json.dumps([{"timestamp": "2026-08-28 08:33:20", "type": "WC_STALE_DATA", "details": "cached"}]))
    df = _load_stale_events()
    assert len(df) == 1
    assert "ts" in df.columns
    assert df.iloc[0]["type"] == "WC_STALE_DATA"

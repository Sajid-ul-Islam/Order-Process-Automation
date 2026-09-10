"""Durable duplicate prevention without touching the runtime ledger."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest

from src.services.pathao.dispatch_ledger import DispatchLedger, ledger_key


@pytest.mark.parametrize("status", ["pending", "created", "uncertain"])
def test_unresolved_or_created_attempt_blocks_after_restart(tmp_path, status):
    path = tmp_path / "dispatch.sqlite3"
    key = ledger_key("account", "123", "Dhaka")
    with DispatchLedger(path) as ledger:
        assert ledger.get(key) is None
        assert ledger.reserve(key, "123")
        if status != "pending":
            ledger.finish(
                key, status, consignment_id="P123" if status == "created" else ""
            )

    with DispatchLedger(path) as restarted:
        assert not restarted.reserve(key, "123")
        record = restarted.get(key)
        assert record["status"] == status
        assert record["merchant_order_id"] == "123"
        assert datetime.fromisoformat(record["created_at"]).utcoffset() == timedelta(
            hours=6
        )
        if status == "created":
            assert record["consignment_id"] == "P123"


def test_explicit_failure_allows_retry_and_clears_previous_result(tmp_path):
    path = tmp_path / "dispatch.sqlite3"
    with DispatchLedger(path) as ledger:
        assert ledger.reserve("key", "123")
        ledger.finish("key", "failed", message="Rejected: invalid store")
        assert ledger.get("key")["message"] == "Rejected: invalid store"

    with DispatchLedger(path) as restarted:
        assert restarted.reserve("key", "123")
        assert restarted.get("key")["status"] == "pending"
        assert restarted.get("key")["message"] == ""
        assert not restarted.reserve("key", "123")
        restarted.finish("key", "created", consignment_id="NEW123")
        assert not restarted.reserve("key", "123")


@pytest.mark.parametrize("previous_failure", [False, True])
def test_concurrent_reservations_have_exactly_one_owner(tmp_path, previous_failure):
    path = tmp_path / "dispatch.sqlite3"
    with DispatchLedger(path) as ledger:
        if previous_failure:
            assert ledger.reserve("key", "123")
            ledger.finish("key", "failed")

    start = Barrier(8)

    def reserve():
        with DispatchLedger(path) as ledger:
            start.wait(timeout=10)
            return ledger.reserve("key", "123")

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(lambda _: reserve(), range(8)))
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 7


def test_exception_leaves_pending_attempt_durable(tmp_path):
    path = tmp_path / "dispatch.sqlite3"
    with pytest.raises(TimeoutError):
        with DispatchLedger(path) as ledger:
            assert ledger.reserve("key", "123")
            raise TimeoutError("Request may have reached Pathao")

    with DispatchLedger(path) as restarted:
        assert restarted.get("key")["status"] == "pending"
        assert not restarted.reserve("key", "123")


def test_final_result_cannot_be_overwritten_or_finished_without_reservation(tmp_path):
    with DispatchLedger(tmp_path / "dispatch.sqlite3") as ledger:
        with pytest.raises(ValueError, match="reserved pending"):
            ledger.finish("missing", "created")
        assert ledger.reserve("key", "123")
        ledger.finish("key", "created", consignment_id="P123")
        with pytest.raises(ValueError, match="reserved pending"):
            ledger.finish("key", "failed")
        assert ledger.get("key")["status"] == "created"
        assert ledger.get("key")["consignment_id"] == "P123"


def test_invalid_outcome_does_not_unblock_reservation(tmp_path):
    with DispatchLedger(tmp_path / "dispatch.sqlite3") as ledger:
        assert ledger.reserve("key", "123")
        with pytest.raises(ValueError, match="Outcome"):
            ledger.finish("key", "retry")
        assert not ledger.reserve("key", "123")


def test_failed_key_cannot_be_reused_for_different_merchant_order(tmp_path):
    with DispatchLedger(tmp_path / "dispatch.sqlite3") as ledger:
        assert ledger.reserve("key", "123")
        ledger.finish("key", "failed")
        assert not ledger.reserve("key", "456")
        assert ledger.get("key")["merchant_order_id"] == "123"


def test_identity_is_stable_and_separates_accounts_orders_and_split_parcels():
    original = ledger_key("account", "123", "Dhaka")
    assert original == ledger_key(" account ", " 123 ", " Dhaka ")
    assert len(original) == 64
    assert original != ledger_key("other-account", "123", "Dhaka")
    assert original != ledger_key("account", "456", "Dhaka")
    assert original != ledger_key("account", "123", "Chattogram")
    # A structured identity prevents collisions caused by joining delimiters.
    assert ledger_key("a|b", "c", "d") != ledger_key("a", "b|c", "d")


@pytest.mark.parametrize("account,order", [("", "123"), ("account", "")])
def test_identity_requires_account_and_merchant_order(account, order):
    with pytest.raises(ValueError, match="required"):
        ledger_key(account, order, "Dhaka")

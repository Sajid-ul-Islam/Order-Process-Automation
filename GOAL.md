# GOAL.md — Behavioral Contract & Acceptance Criteria

This file is the **source of truth** for the rules the Live Dashboard (and every
component that reads live WooCommerce data) must follow. The CI checks in
`.github/workflows/tests.yml` enforce these invariants — if a change breaks one,
CI fails before the code is merged.

## How to run the checks locally

```bash
make test        # runs: python -m pytest tests/ -q
```

## Core invariants

### 1. Processing orders are always visible

An order that is still in `processing` status must appear in the **Processing**
view **regardless of when it was placed** — including orders placed *before* the
operational shift cutoff (e.g. 18:00) or even on earlier days.

**Why:** a processing order is an open order that still needs action. Before this
rule, orders placed just before the shift cutoff were excluded from Today, and
since `Prev` only keeps shipped orders and `Backlog` only keeps
on-hold/pending/waiting, those processing orders vanished from **every** view.

Implementation notes:
- `_partition_operational_data` (Today partition) includes
  `created_recent | modified_recent | is_processing`.
- `filter_all_orders_to_slot` never date-scopes *active* orders — only shipped
  orders are date-scoped.

### 2. "All Orders" = open orders + shipped today

The **All Orders** view contains exactly:

- every open order (`processing`, `on-hold`, `pending`, `waiting`), and
- orders that were **shipped today** (shipped/completed whose modification date
  falls in today's window).

Orders shipped on an earlier day, and cancelled/failed/refunded orders, are
excluded from the Today view.

### 3. Shipped orders are scoped by dispatch date

`filter_shipped_by_slot` uses `mod_dt_parsed` (WooCommerce `date_modified`,
converted to BD UTC+6) as the authoritative "when was it shipped" signal, with
fallback to creation date only when the modification date is missing.

### 4. Backlog (Queue) = on-hold / pending / waiting

The **Backlog** partition only contains `on-hold`, `pending`, and `waiting`
orders. It is the home for un-shipped orders that are not `processing`.

### 5. Statuses are matched case-insensitively

All status comparisons must use `.astype(str).str.lower()` so `Processing`,
`PROCESSING`, `wc-processing`, etc. are treated as the same status. (`processing`
statuses may carry a `wc-` prefix from WooCommerce plugins.)

## What CI verifies

- The order-visibility invariants above (see `tests/test_order_visibility.py` and
  `tests/test_shipped_scoping.py`).
- Every check must pass on `main` and on pull requests (`.github/workflows/tests.yml`).

## Getting a change merged

1. Make the change.
2. Run `make test` locally — all tests must pass.
3. Push. CI re-runs the suite; the PR is only mergeable when it is green.

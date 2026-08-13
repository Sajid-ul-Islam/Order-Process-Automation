# Dead Code Report

Catalogue of removed, unused, and no-op code identified during the v1-to-v2 migration. Items listed here have either been deleted, replaced, or are candidates for future cleanup.

---

## Removed Constants and Functions

### `DEFAULT_GSHEET_URL` (removed from `src/config/ui_config.py`)

Previously held a hardcoded Google Sheets CSV export URL used as the default data source for Sales Ingestion. Removed because all ingestion now flows through WooCommerce API sync or file upload via the Smart Ingestion system. The constant was the only reference to a specific Google Sheet; no other code depends on it.

### `load_default_gsheet()` (removed)

A helper function that fetched a DataFrame from `DEFAULT_GSHEET_URL` using `pd.read_csv()`. It was called from the Sales Ingestion page as the "quick start" data source. Replaced by the unified `fetch_dataframe_from_url()` utility in `src/utils/url_fetch.py`, which auto-detects CSV vs XLSX format and works with any public URL.

### `src/services/google/sheets.py` (entire file deleted)

Contained Google Sheets-specific loading logic (public CSV export URL construction, caching wrapper). The file has been deleted; only the empty `__init__.py` remains in `src/services/google/`. All URL-based data fetching is now handled by `src/utils/url_fetch.py`.

---

## Removed UI Blocks

### GSheet Button Blocks (removed from 4 pages)

Each of the following pages previously contained a "Load from Google Sheet" button and associated URL input field. These blocks have been removed:

| Page | File | What Was Removed |
|------|------|-----------------|
| Sales Data Ingestion | `src/pages/sales_ingestion.py` | GSheet URL input + load button in the data source section |
| Bulk Order Processer | `src/pages/pathao_orders.py` | GSheet import option in the order source selector |
| WhatsApp Messaging | `src/pages/whatsapp_messaging.py` | GSheet URL input for loading order data |
| Inventory Distribution | `src/pages/inventory_distribution.py` | GSheet URL input for loading inventory data |

Replacement: Pages now use file upload and/or WooCommerce API sync. For URL-based loading, the generic `fetch_dataframe_from_url()` is available.

---

## No-Op / Unused Code (Still Present)

### `render_sidebar_branding()` in `src/components/sidebar.py` (removed)

**Status:** Removed.

The function loads the DEEN Commerce logo and encodes it to base64 but then does nothing with it. The final line is `pass` with a comment noting the user requested no title in the sidebar. The logo loading code above the `pass` still executes (wasting I/O) but produces no visible output.

**Resolution:** The function has been completely removed.

### `MORE_TOOLS` list in `src/config/ui_config.py` (removed)

**Status:** Removed.

```python
MORE_TOOLS = [
    "System Logs",
    "Dev Lab",
]
```

This list is defined at module level but is not referenced by `app.py` or any navigation logic. The sidebar's "Maintenance & Settings" section uses its own hardcoded options rather than reading from this list.

**Recommendation:** Either wire it into the sidebar navigation or remove it to avoid confusion.

---

## Replaced Logic

### Old PNG Snapshot Logic in `src/components/snapshot.py`

**Status:** Fully replaced by JSON metric snapshot.

The original implementation used `html2canvas` (via a Streamlit JS component) to take a PNG screenshot of the rendered dashboard. This was brittle, slow, and produced large files.

**Replacement:** `src/components/snapshot.py` now contains `compute_snapshot_metrics()` which extracts core KPIs (qty, revenue, orders, avg basket) and category breakdowns into a structured dict, and `render_snapshot_button()` which offers a JSON download. The persistence layer lives in `src/utils/metric_snapshots.py` (`save_metric_snapshot()` / `load_metric_snapshot()`).

The JSON snapshot is smaller, machine-readable, and suitable for trend comparison across snapshots.

---

## Dead Code Audit — June 2026

Comprehensive dead code sweep across the `src/` tree. All items below have been **removed** unless stated otherwise.

### Deleted Files (zero imports across the codebase)

| File | Contents | Evidence |
|------|----------|----------|
| `src/components/sidebar.py` | Empty placeholder — comments only, no code | Never imported |
| `src/components/data_display.py` | `render_numbered_dataframe()` | Zero imports; only defined |
| `src/components/live_banner.py` | `render_live_banner()` | Zero imports; only defined |
| `src/state/insights.py` | `get_business_insights()` | Zero imports; only defined |
| `src/services/llm/rag_engine.py` | `RAGEngine` class (DuckDB vector search) | Zero imports; only defined |

### Removed Functions

| Function | File | Reason |
|----------|------|--------|
| `render_performance_analysis()` | `src/pages/dashboard_output.py` | ~182-line function never called. `render_dashboard_output()` uses the private `_render_*` helpers instead. |
| `get_category_from_name()` | `src/utils/product.py` | Only consumer of `@lru_cache` in this file; never imported or called. |
| `classify_columns()` | `src/processing/column_detection.py` | Thin wrapper around `detect_filterable_columns`; never imported or called. |

### Removed Dead Imports (orphaned by the above deletions)

| Import | File | Reason |
|--------|------|--------|
| `from src.processing.forecasting import PredictiveIntelligence` | `src/pages/dashboard_output.py` | Only used by the removed `render_performance_analysis()`. |
| `import functools` | `src/utils/product.py` | Only used by the removed `@lru_cache` decorator on `get_category_from_name()`. |

### Removed Commented-Out Code

| File | Line | Code |
|------|------|------|
| `src/pages/delivery_parser.py` | 122 | `# section_card("Delivery Text Parser", "")` |
| `src/pages/whatsapp_messaging.py` | 48 | `# section_card("WhatsApp Verification", "")` |

### Deduplicated Excel Export

| Item | Before | After |
|------|--------|-------|
| Delivery Excel export | `df_to_excel_bytes()` in `src/processing/delivery_parser.py` (local duplicate with extra styling) | `to_excel_bytes()` from `src/utils/file_io.py` with `sheet_name="Deliveries"` |
| `BytesIO` import | `src/processing/delivery_parser.py` | Removed (only consumer was the deleted `df_to_excel_bytes`) |

**Note:** The removed `df_to_excel_bytes` had delivery-specific Excel styling (freeze panes, column widths, number formatting) that the shared utility does not provide. This is a minor visual regression in the downloaded `.xlsx` files.

---

## Component Reorganization & Dead Code Audit — July 2026

### Component Package Restructuring
Reorganized monolithic `src/components/` and `src/pages/` directories into structured modular packages:
- `src/components/layout/` (`header.py`, `footer.py`)
- `src/components/ui/` (`clock.py`, `smart_filters.py`, `widgets.py`, `bike_animation.py`, `clipboard.py`, `empty_state.py`, `status.py`, `styles.py`, `ui_components.py`, `dataframe_search.py`, `calendar_slots.py`, `snapshot.py`)
- `src/components/dashboard/` (`dashboard_metrics.py`, `dashboard_charts.py`, `dashboard_filters.py`, `dashboard_output.py`)
- `src/services/exports/` (`excel_exporter.py`)

### Removed Dead Files & Directories
- `src/2026-06-13.csv`: Removed unreferenced temporary 411-byte CSV file inside `src/`.
- `src/services/google/`: Removed orphaned directory containing only an empty `__init__.py`.
- `scratch/*.py`: Removed 16 temporary debug scripts (`fetch_wc.py`, `fix_history.py`, `test_*.py`) created during previous debugging sessions.

### Removed Dead Imports
- `import plotly.express as px` in `src/components/dashboard/dashboard_output.py` (unused).
- `from src.services.exports.excel_exporter import export_to_styled_excel` in `src/components/dashboard/dashboard_output.py` (unused).

---

## Dead Code Audit — August 2026

Full-codebase sweep (ruff F401/F541/F811/F841 + import-graph analysis + test run).

### Deleted Files
| File | Reason |
|------|--------|
| `src/pages/whatsapp_daily_report.py` | Empty 0-byte placeholder, never imported or referenced. |

### Relocated Files
| File | New Location | Reason |
|------|--------------|--------|
| `src/pages/executive_daily_report.py` | `scripts/executive_daily_report.py` | Standalone CLI script (not a routed page) — belongs with the other operational scripts. Docstring usage updated. |

### Untracked Runtime Artifacts
`data/error_logs.json` and `data/session_state.json` were tracked in git despite being regenerated on every run (machine-specific tracebacks / serialized session state). Both are now in `.gitignore` and removed from tracking; `data/feedback/system_logs.json` was already ignored.

### Removed Dead Functions
| Function | File | Reason |
|----------|------|--------|
| `apply_standard_dataframe()` | `src/components/ui/ui_components.py` | Never called anywhere in the codebase. |
| `customer_groups` computation (polars group-by on `_clean_phone`) | `src/processing/data_processing.py` | Result never used; removed along with the now-pointless `_clean_phone` enrichment branch (behavior-identical: `avg_customer_value`/`unique_customers` still only set when no phone column exists). |
| `render_performance_analysis()` | `src/components/dashboard/dashboard_output.py` | Already removed in the June 2026 audit (kept here for completeness). |

### Removed Unused Imports & Variables
- ~40 unused imports removed via `ruff check --fix` (including `plotly.express`, unused `ui_components` helpers, `BytesIO`, `typing` names, `requests`, `kaleido`, etc.).
- ~25 unused local variables removed (e.g. `is_confirmed`/`now_bd` in `woocommerce/client.py`, `range_sub` block in `dashboard_metrics.py` — computed but only referenced by a commented-out `st.caption`, `styled_df` in `pathao_orders.py`, `edited_df` in `woocommerce_orders.py`, `is_holiday_merge`/`p_20b` in `layout/header.py`, `success`/`now` in `llm/manager.py`).
- 2 f-strings without placeholders converted to plain strings (`F541`).
- 2 shadowing redefinitions fixed: `np` in `data_pilot.py` (local import kept), `io` in `inventory_distribution.py` (top-level import kept, redundant function-local `import io` removed).

### Follow-up Sweep (guarded by `tests/test_no_unused_imports.py`)
- 9 unused imports removed from `src/pages/data_pilot.py` (`os`, `typing.Dict`/`List`, `DATA_DIR`, `load_secrets_schema`, `TfidfVectorizer`, `cosine_similarity`, `NeuralBrain`, `PredictiveIntelligence`) — caught by the new F401 guard test.
- `scripts/check_imports.py` module list extended from 45 → 64 modules, covering every module in `src/` (including the new `llm/agent.py`, `woocommerce/orders.py`, `dashboard/svg.py`, `inventory/core.py`, the remaining pages/processing/services/ui modules).

### Not Touched (by design)
- `E701` compound statements (~94 one-liner `if ...: ...`) and `E722` bare `except`s (~10) — pre-existing style choices, not dead code; left for a dedicated formatting pass.
- `scripts/update_pathao_data.py`, `scripts/generate_requirements_lock.py`, `scripts/generate_snapshot.py` — operational utilities (referenced by `.claude/`, CI, or usable standalone).
- `BackEnd/cache/` — intentionally tracked: the nightly `data_crunch.yml` action commits regenerated snapshots.
- `resources/metric_snapshots/`, `resources/pathao_map.json`, etc. — persisted data the app reads/writes.

### Docs Updated
- `README.md`: removed stale `requirements/` package layout and `requirements.lock`/`_deprecated/` claims; structure tree now matches the real tree.
- `ARCHITECTURE.md`: layer diagram and tables now reference the current module locations (e.g. `components/dashboard/dashboard_output.py`); removed `services/google/sheets` and `state/insights`.
- `ERROR_HANDLING_GUIDE.md`: fixed stale `dashboard_output.py` path.
- `agent.md`: page list and operational-dashboard rules now reference `components/dashboard/` and the `pages/pathao_orders/` package.

**Verification:** `ruff check` clean for F-categories; `python -m compileall -q src app.py scripts/ tests/` passes; `pytest tests/ -q` → 16 passed; `scripts/check_imports.py` → 64/64 modules import cleanly.

---

## Modularization Pass — Duplicate Logic Consolidation

Same-work-done-in-many-places cleanup. No behavior change intended (one latent bug fixed, see below); every consolidation is covered by `tests/test_shared_helpers.py` (21 new tests, suite now 37).

### Shared BD time (`src/config/constants.py`)
- Added `BD_TZ`, `bd_now()`, `bd_today()` — the codebase re-derived `timezone(timedelta(hours=6))` in **18+ places** across `woocommerce/client.py` (6 sites), `data_processing.py` (4), `live_dashboard.py` (4), `metric_history.py`, `metric_snapshots.py`, `clock.py`, `snapshot.py`, `dashboard_output.py`, and `scripts/executive_daily_report.py`. All now use the shared helpers; per-function `from datetime import ...` shadowing imports removed.

### Shared phone normalization (`src/utils/text.py`)
- Added `normalize_phone_number()` — canonical BD 11-digit 0-prefixed form (017…, 17…, +88017…, 88017… → 017…).
- `customer_registry.normalize_phone_key()` and `WhatsAppOrderProcessor.clean_phone_number()` were two divergent re-implementations; both now delegate to the shared function. The registry wrapper keeps its `pd.isna` guard; the WhatsApp path keeps its `pd.isna` guard.
- **Bug fixed as a side effect:** the old WhatsApp implementation returned `88017…` untouched for `88`/`880`-prefixed inputs, producing broken `https://wa.me/+88880…` links (doubled country code). The shared canonicalizer now yields correct `+88017…` links. Standard `017…`/`17…` inputs are byte-identical to the old behavior.

### Shared column picking (`src/processing/column_detection.py`)
- Added `pick_column(df, candidates, default)` — replaces the repeated `next((c for c in [...] if c in df.columns), default)` idiom. `customer_registry.py` had **6 near-identical blocks** (phone/email/date/order-id column selection across `update_customer_registry` and `compute_new_vs_returning_counts`); candidate lists hoisted to module constants, all blocks now call `pick_column`.

### Shared file reading (`src/utils/file_io.py`)
- `inventory/core.py` had a private `_read_uploaded()` duplicating `file_io.read_uploaded()` (plus DataFrame passthrough). `read_uploaded()` now handles DataFrames and None, and inventory imports it instead of defining its own.

### Verification
- `pytest tests/` → 37 passed (21 new in `tests/test_shared_helpers.py`); `ruff check --select F` clean; `compileall` OK; `check_imports.py` → 64/64.


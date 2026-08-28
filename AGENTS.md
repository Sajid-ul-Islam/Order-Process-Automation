# AGENTS.md: DEEN-OPS Terminal Multi-Agent Directives & Context Guide

Welcome to **DEEN-OPS Terminal**. This file is the primary context boundary and architectural manual for all autonomous AI agents and human engineers working on this codebase.

---

## 1. Project Overview & Identity
- **Name**: DEEN-OPS Terminal (v10.0 LIVE)
- **Role**: Operational command center & analytics terminal for e-commerce operations in Bangladesh (WooCommerce store sync, Pathao courier logistics, outlet inventory rebalancing, return analytics, and AI Data Pilot).
- **Core Stack**: Streamlit, pandas, Polars, DuckDB, Plotly, Scikit-Learn, XGBoost, Requests (with exponential backoff).

---

## 2. Directory Architecture & Layer Boundaries

```text
DEEN-OPS/
├── app.py                      # Main Streamlit bootstrap wrapper
├── src/
│   ├── app_bootstrap.py        # Top-level shell, auth gate, sidebar navigation router
│   ├── config/                 # Centralized settings, secrets schema, constants (BD time)
│   ├── components/             # Reusable UI presentation layer
│   │   ├── layout/             # Header, footer, global banners
│   │   ├── ui/                 # Status badges, widgets, clock, calendar slots
│   │   └── dashboard/          # Metric cards, SVG sparklines, SKU reports, charts
│   ├── pages/                  # Routed feature page modules
│   │   ├── live_dashboard.py   # Shift tracking (Today / Prev / Backlog)
│   │   ├── pathao_orders/      # Package: processing, dispatch, tracking, health
│   │   ├── inventory_distribution.py # Multi-outlet stock balancing
│   │   ├── whatsapp_messaging.py     # Bulk customer order confirmations
│   │   ├── return_analytics.py       # Return reconciliation engine
│   │   └── data_pilot.py             # Multi-LLM AI operations assistant
│   ├── processing/             # Stateless data transformation & ETL algorithms
│   ├── services/               # External integration clients (WooCommerce, Pathao, LLM)
│   └── utils/                  # Stateless pure helpers (text, phone, http, snapshots)
├── deploy/                     # Production K8s, Ingress, HPA, and NGINX configs
├── resources/                  # Persistent runtime snapshots and customer registry
├── scripts/                    # CLI operational utilities & import verification
└── tests/                      # Automated pytest unit test suite
```

---

## 3. Strict Architectural Invariants (DO NOT BREAK)

1. **Layer Separation**:
   - `src/processing/` and `src/services/` must **NEVER** import from `src/components/` or `streamlit`.
   - All external HTTP calls must use `request_with_backoff()` from `src/utils/http.py`.
2. **Bangladesh Timezone Standard (UTC+6)**:
   - **NEVER** instantiate raw `datetime.now()` for shift calculations without timezone awareness. Always import and use `bd_now()` and `bd_today()` from `src/config/constants.py`.
3. **Strict Order Status Whitelist**:
   - Reverted orders (e.g. `on-hold`, `pending`, `cancelled`) must **NEVER** count towards dispatched or shipped revenue metrics, even if a courier tracking ID exists.
4. **Session State Invariants**:
   - Defensively initialize session keys at page entry: `if "key" not in st.session_state: st.session_state["key"] = default`.
5. **No Direct Secrets in Git**:
   - `.streamlit/secrets.toml`, `.env`, and token caches must remain 100% gitignored.

---

## 4. Verification & Testing Requirements

Before concluding any code change, an agent **MUST** run and pass:

```bash
# 1. Full Unit Test Suite (Must be 47+ passed, 0 failed)
PYTHONPATH=. .venv/bin/pytest tests/ -v

# 2. Module Import Verification across all 59 modules (Must be 59 OK, 0 FAILED)
.venv/bin/python scripts/check_imports.py
```

---

## 5. Feature Context Map for Targeted Agent Tasks

When assigned a specific domain, scope your file reading strictly to the relevant modules:

| Domain / Task | Read/Write Scope | Read-Only Dependency |
|---|---|---|
| **KPI & Dashboard** | `src/components/dashboard/`, `src/pages/live_dashboard.py` | `src/processing/data_processing.py` |
| **Pathao Logistics** | `src/pages/pathao_orders/`, `src/services/pathao/` | `src/processing/order_processor.py` |
| **WhatsApp Messages**| `src/pages/whatsapp_messaging.py`, `src/processing/whatsapp_processor.py` | `src/utils/text.py` |
| **Inventory Matrix** | `src/pages/inventory_distribution.py`, `src/inventory/` | `src/utils/file_io.py` |
| **Data Pilot AI**    | `src/pages/data_pilot.py`, `src/services/llm/` | `src/processing/hybrid_data_loader.py` |
| **DevOps / Deploy**  | `Dockerfile`, `deploy/`, `.streamlit/config.toml` | `scripts/healthcheck.py` |

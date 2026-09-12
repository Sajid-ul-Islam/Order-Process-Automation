# DEEN OPS Terminal

AI-assisted operations workspace for WooCommerce, Pathao courier logistics, inventory reconciliation, and shift analytics workflows.

## 🚀 Key Highlights

- **Live Operational Dashboard:**
  - Real-time shift tracking across **Today**, **Prev**, and **Backlog** operational windows.
  - Interactive KPI cards for **Gross Items**, **Actual Net Revenue** (with consolidated cashback breakdown), **Orders**, **Basket Size (AOV)**, and **Customer Mix**.
  - Integrated 36-hour hourly trend sparklines and 7-day new-customer acquisition curves with cubic Bézier smoothing and adaptive theme styling.
  - Shift Targets with goal progress bars, 30-Day snapshot history charts, and 1-click **Shift Handover Report** generation.
- **Strict Order Lifecycle & Shipped Tracking:**
  - Strict status whitelist enforcement ensuring only confirmed/completed orders count toward dispatch and revenue metrics.
  - Automatic protection against status reversions: orders changed back to `on-hold`, `waiting`, `pending`, or `processing` are never counted as shipped (even if a courier consignment ID was previously generated) and are kept in active/pending queues.
  - Persistent disk-cached shipped history with automatic cache purging for reverted orders.
- **Pathao Logistics & Dispatch Suite:**
  - Live consignment tracking, bulk label generation, and automated delivery health audits.
- **Return Analytics Engine:**
  - Concurrently reconciles returned parcels against live WooCommerce order statuses and Pathao delivery logs to flag prepaid refund risks and status mismatches.
- **Inventory & Outlet Stock Distribution:**
  - Monitors stock discrepancies between physical retail outlets and central E-commerce warehouses with instant CSV/Excel fallback support.
- **Lifetime Customer Identity Registry:**
  - Multi-tier identity matching (Phone ➔ Email ➔ Name/City) to calculate accurate new vs. returning customer retention rates.
- **Data Pilot AI Assistant:**
  - Natural-language business intelligence queries powered by multi-provider LLM routing (OpenRouter, Gemini, Groq, Ollama, Hugging Face).
- **Enterprise Resilience:**
  - Shared exponential backoff for external APIs, configuration validation ([src/config/secrets_schema.json](src/config/secrets_schema.json)), and container healthcheck support.

## 🛠️ Tech Stack

- **Frontend / UI:** Streamlit, Vanilla CSS, Plotly Express & Graph Objects, Pure SVG Sparklines
- **Data Engine:** pandas, Polars, numpy
- **Integrations:** WooCommerce REST API, Pathao Courier REST API
- **AI & LLM:** OpenRouter, Google Gemini, Groq, Ollama, Hugging Face
- **Quality & Testing:** pytest, pre-commit, Black, isort, Flake8, Ruff

## ⚡ Quick Start

```bash
git clone https://github.com/Sajid-ul-Islam/DEEN-OPS.git
cd DEEN-OPS
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.lock
pre-commit install
streamlit run app.py
```

Authentication fails closed by default. Configure the `[auth]` secrets block
for shared or production deployments. For local development only, explicitly
set `DEEN_OPS_ALLOW_UNAUTHENTICATED=true` in the shell before starting the app.

## ⚙️ Configuration

Configuration is managed via `.streamlit/secrets.toml` with environment variable fallbacks. The schema is validated at startup via [src/config/secrets_schema.json](src/config/secrets_schema.json).

Example `.streamlit/secrets.toml`:

```toml
[woocommerce]
store_url = "https://your-store.com"
consumer_key = "ck_..."
consumer_secret = "cs_..."

[pathao]
base_url = "https://courier-api.pathao.com"
client_id = "..."
client_secret = "..."
username = "..."
password = "..."

[llm]
openrouter_key = "..."
gemini_key = "..."
groq_key = "..."

[auth]
redirect_uri = "..."
cookie_secret = "..."

[auth.google]
client_id = "..."
client_secret = "..."
server_metadata_url = "..."
```

Supported Environment Variables:

- **WooCommerce:** `WC_URL`, `WC_KEY`, `WC_SECRET`
- **Pathao:** `PATHAO_BASE_URL`, `PATHAO_CLIENT_ID`, `PATHAO_CLIENT_SECRET`, `PATHAO_USERNAME`, `PATHAO_PASSWORD`
- **LLM APIs:** `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `HF_API_KEY`
- **Resilience:** `API_RETRY_MAX_ATTEMPTS`, `API_BACKOFF_FACTOR_SECONDS`, `API_BACKOFF_MAX_SECONDS`

## Pathao bulk order creation

Open **Orders & Fulfillment → Select Feature → Pathao Processor**.

1. In **Order Processing**, choose **WooCommerce Processing** and click **Pull Processing Orders**, or upload an Excel/CSV export. For uploads, map the columns and click **Confirm & Process**; this processes immediately, and the confirmed mapping remains available on subsequent clicks.
2. Review the processed parcel rows, especially recipient phone, complete address, COD, quantity, and split-parcel instructions. Correct problems in the source and process again. **Download repaired file** remains available for manual portal upload.
3. In **Auto-Dispatch**, click **Load pickup stores** and select a Pathao store for each warehouse/outlet. The stores come from the configured merchant account; no store ID needs to be added to secrets.
4. Choose parcel/document, delivery type, and any additional instructions. Review whether to update matching WooCommerce orders to `confirmed`; this is enabled by default only for a WooCommerce source. Imported merchant references must belong to the connected WooCommerce store before enabling it.
5. Click **Push to Pathao API**, then **Download dispatch results** to save the consignments and per-parcel outcomes. WooCommerce updates wait for all parcels of an order to succeed; a WooCommerce failure does not undo a Pathao creation.

Auto-Dispatch uses the processor's actual export fields and includes the selected pickup `store_id`. Following [Pathao's auto-address guidance](https://pathao.com/bn/blog/api-merchant-auto-address-feature/), it sends the complete recipient address without fabricated city/zone/area IDs.

Confirmed creations are saved in `data/pathao_dispatch.sqlite3` and skipped on subsequent attempts on this installation. A definite API rejection can be retried after correction. A timeout, interrupted request, or response without a consignment ID is marked **Check Pathao** and blocked from automatic resubmission: search the merchant order ID in **Order Tracking** or the merchant portal to reconcile it. Keep the ledger on persistent storage. It cannot detect orders created outside this application, on another installation, or before the ledger existed; review those in Pathao before submitting. Do not change merged order membership or warehouse assignments to bypass a recorded attempt.

Pathao API tests use synthetic data and mocked responses; passing them verifies the application flow, not the credentials or availability of a live merchant account.

## 📂 Project Structure

```text
DEEN-OPS/
|-- app.py
|-- assets/
|-- data/
|-- resources/
|-- scripts/
|-- src/
|   |-- components/
|   |   |-- dashboard/
|   |   |-- layout/
|   |   `-- ui/
|   |-- config/
|   |-- inventory/
|   |-- pages/
|   |-- processing/
|   |-- services/
|   |   |-- exports/
|   |   |-- llm/
|   |   |-- pathao/
|   |   `-- woocommerce/
|   |-- state/
|   `-- utils/
`-- tests/
```

## 🧪 Testing & CI

Run the automated test suite locally:

```bash
pytest tests/ -v
pytest tests/ --cov=src --cov-report=term-missing
pre-commit run --all-files
```

Continuous integration is enforced on `main` and pull requests via GitHub Actions ([.github/workflows/tests.yml](.github/workflows/tests.yml)).

## 🚢 Deployment

- **Local:** `streamlit run app.py`
- **Docker:** Build using the included `Dockerfile` with container health probes configured via [scripts/healthcheck.py](scripts/healthcheck.py).
- **Staging / Production:** Kubernetes or Docker Compose with environment-based secret injection and TLS ingress.

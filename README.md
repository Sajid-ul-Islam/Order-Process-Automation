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
pip install -r requirements.txt
pip install -r requirements_dev.txt
pre-commit install
streamlit run app.py
```

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
